import sqlite3
from datetime import datetime
from threading import Event
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api.registro import SimulacaoAtiva, registro
from app.domain.distribution import (
    CentroDistribuicao,
    DistribuidorPedidos,
)
from app.domain.models import Entregador
from app.domain.routing import Coordenada, ErroRoteamento
from app.domain.simulation import EstadoExecucao, Simulacao
from app.infrastructure import database
from app.infrastructure.auditoria_experimental import (
    FalhaPersistenciaAuditoriaExperimental,
)
from app.infrastructure.auditoria_repository import (
    AuditoriaSimulacao,
    obter_parametros_experimentais,
)
from app.infrastructure.seed import inicializar_todos_cenarios
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado
from app.main import app


FUSO = ZoneInfo("America/Bahia")
INICIO = datetime(2026, 10, 30, 10, 0, tzinfo=FUSO)
INICIO_API = INICIO.isoformat()
CENTRO = CentroDistribuicao("Comercio", Coordenada(-12.971, -38.501))


@pytest.fixture
def cliente_experimental(tmp_path, monkeypatch):
    diretorio = tmp_path / "auditoria_planejamento"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("PROVEDOR_MAPAS", raising=False)
    monkeypatch.delenv("QUANTIDADE_ENTREGADORES", raising=False)
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_NOME", "Comercio")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LATITUDE", "-12.971")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LONGITUDE", "-38.501")
    cenarios = inicializar_todos_cenarios()
    registro.limpar()

    with TestClient(app, raise_server_exceptions=False) as cliente:
        cliente.cenario_normal_id = next(
            cenario.id for cenario in cenarios if cenario.codigo == "NORMAL"
        )
        yield cliente

    registro.limpar()


def _criar_simulacao(cliente):
    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenario_normal_id,
            "inicio": INICIO_API,
            "provedor": "simulado",
        },
    )
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()


def _criar_auditoria():
    return AuditoriaSimulacao.criar(
        INICIO,
        CENTRO,
        [Entregador("CAM-01")],
        "Teste",
        parametros={"versao": 1},
        snapshot_pedidos={"versao": 1, "pedidos": []},
    )


def test_parametros_snapshot_e_consultas_sao_protegidos_sem_bloquear_status(
    cliente_experimental,
):
    cliente = cliente_experimental
    simulacao_id = _criar_simulacao(cliente)["id"]

    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                "UPDATE simulacoes SET parametros_json = '{}' WHERE id = ?",
                (simulacao_id,),
            )

    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                "DELETE FROM simulacao_pedidos_snapshot WHERE simulacao_id = ?",
                (simulacao_id,),
            )

    etapa = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert etapa.status_code == 200, etapa.json()
    with database.conectar() as conexao:
        consulta_id = conexao.execute(
            """
            SELECT id FROM consultas_roteamento_simulacao
            WHERE simulacao_id = ? ORDER BY sequencia LIMIT 1
            """,
            (simulacao_id,),
        ).fetchone()["id"]

    with pytest.raises(sqlite3.IntegrityError):
        with database.conectar() as conexao:
            conexao.execute(
                "DELETE FROM consultas_roteamento_simulacao WHERE id = ?",
                (consulta_id,),
            )

    # Status e horário final continuam sendo atualizáveis pelo ciclo normal.
    with database.conectar() as conexao:
        conexao.execute(
            "UPDATE simulacoes SET status = 'concluida', fim_simulado = ? WHERE id = ?",
            (INICIO_API, simulacao_id),
        )
        linha = conexao.execute(
            "SELECT status, parametros_json FROM simulacoes WHERE id = ?",
            (simulacao_id,),
        ).fetchone()
    assert linha["status"] == "concluida"
    assert linha["parametros_json"] is not None


def test_descarte_controlado_da_etapa_2_remove_simulacao_e_filhos(
    cliente_experimental,
):
    cliente = cliente_experimental
    simulacao_id = _criar_simulacao(cliente)["id"]
    auditoria = AuditoriaSimulacao(simulacao_id)
    auditoria.registrar_consulta_roteamento(
        tipo="rota",
        provedor="simulado",
        perfil="simulado",
        origem_resultado="provedor",
        partida_em=INICIO,
        consultada_em=INICIO,
        requisicao={"versao": 1},
        resposta={"distancia_m": 10, "duracao_s": 20},
    )

    assert auditoria.descartar_criacao_sem_eventos() is True
    with database.conectar() as conexao:
        assert conexao.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conexao.execute(
            "SELECT 1 FROM simulacoes WHERE id = ?", (simulacao_id,)
        ).fetchone() is None
        assert conexao.execute(
            "SELECT 1 FROM simulacao_pedidos_snapshot WHERE simulacao_id = ?",
            (simulacao_id,),
        ).fetchone() is None
        assert conexao.execute(
            "SELECT 1 FROM consultas_roteamento_simulacao WHERE simulacao_id = ?",
            (simulacao_id,),
        ).fetchone() is None


def test_exclusao_direta_de_simulacao_com_eventos_e_bloqueada(
    cliente_experimental,
):
    cliente = cliente_experimental
    simulacao_id = _criar_simulacao(cliente)["id"]
    etapa = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert etapa.status_code == 200, etapa.json()

    with database.conectar() as conexao:
        assert conexao.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conexao.execute(
            "SELECT COUNT(*) FROM eventos_simulacao WHERE simulacao_id = ?",
            (simulacao_id,),
        ).fetchone()[0] > 0

        # A tentativa de excluir primeiro os eventos não pode abrir caminho
        # para a remoção do registro pai.
        with pytest.raises(sqlite3.IntegrityError, match="Eventos de simulacoes"):
            conexao.execute(
                "DELETE FROM eventos_simulacao WHERE simulacao_id = ?",
                (simulacao_id,),
            )

        with pytest.raises(sqlite3.IntegrityError, match="com eventos"):
            conexao.execute(
                "DELETE FROM simulacoes WHERE id = ?", (simulacao_id,)
            )

        assert conexao.execute(
            "SELECT 1 FROM simulacoes WHERE id = ?", (simulacao_id,)
        ).fetchone() is not None
        assert conexao.execute(
            "SELECT 1 FROM eventos_simulacao WHERE simulacao_id = ? LIMIT 1",
            (simulacao_id,),
        ).fetchone() is not None
        assert conexao.execute(
            "SELECT 1 FROM simulacao_pedidos_snapshot WHERE simulacao_id = ?",
            (simulacao_id,),
        ).fetchone() is not None
        assert conexao.execute(
            "SELECT 1 FROM consultas_roteamento_simulacao WHERE simulacao_id = ?",
            (simulacao_id,),
        ).fetchone() is not None


def test_exclusao_direta_de_eventos_e_bloqueada(
    cliente_experimental,
):
    cliente = cliente_experimental
    simulacao_id = _criar_simulacao(cliente)["id"]
    etapa = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert etapa.status_code == 200, etapa.json()

    with database.conectar() as conexao:
        assert conexao.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        evento = conexao.execute(
            "SELECT id FROM eventos_simulacao WHERE simulacao_id = ? LIMIT 1",
            (simulacao_id,),
        ).fetchone()
        assert evento is not None

        with pytest.raises(
            sqlite3.IntegrityError, match="Eventos de simulacoes"
        ):
            conexao.execute(
                "DELETE FROM eventos_simulacao WHERE id = ?",
                (evento["id"],),
            )

        assert conexao.execute(
            "SELECT 1 FROM eventos_simulacao WHERE id = ?",
            (evento["id"],),
        ).fetchone() is not None


@pytest.mark.parametrize(
    ("endpoint", "corpo"),
    [
        ("proxima-etapa", None),
        ("avancar", {"minutos": 1}),
        ("executar", None),
    ],
)
def test_falha_sincrona_de_planejamento_sincroniza_estados(
    cliente_experimental, monkeypatch, endpoint, corpo
):
    cliente = cliente_experimental

    def falhar(_self, *_args, **_kwargs):
        raise ErroRoteamento("detalhe interno controlado")

    monkeypatch.setattr(DistribuidorPedidos, "planejar", falhar)
    simulacao_id = _criar_simulacao(cliente)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/{endpoint}",
        json=corpo,
    )

    assert resposta.status_code == 502, resposta.json()
    ativa = registro.obter(simulacao_id)
    assert ativa is not None
    assert ativa.estado_execucao == EstadoExecucao.FALHOU
    assert ativa.erro_execucao == (
        "Falha no serviço de roteamento durante o planejamento."
    )
    assert "detalhe interno controlado" not in ativa.erro_execucao

    estado = cliente.get(f"/api/simulacoes/{simulacao_id}")
    assert estado.status_code == 200
    assert estado.json()["estado_execucao"] == "falhou"
    assert estado.json()["erro_execucao"] == ativa.erro_execucao

    parametros = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    )
    assert parametros.status_code == 200
    assert parametros.json()["planejamento"]["estado"] == "falhou"


def test_falha_ao_registrar_mensagem_operacional_preserva_erro_original(
    cliente_experimental, monkeypatch, caplog
):
    cliente = cliente_experimental

    def falhar(_self, *_args, **_kwargs):
        raise ErroRoteamento("erro original do roteamento")

    monkeypatch.setattr(DistribuidorPedidos, "planejar", falhar)

    def obter_erro(self):
        return getattr(self, "_erro_execucao_teste", None)

    def definir_erro(self, valor):
        if valor is not None:
            raise RuntimeError("falha secundária do estado operacional")
        self._erro_execucao_teste = valor

    monkeypatch.setattr(
        SimulacaoAtiva,
        "erro_execucao",
        property(obter_erro, definir_erro),
    )

    simulacao_id = _criar_simulacao(cliente)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )

    assert resposta.status_code == 502, resposta.json()
    ativa = registro.obter(simulacao_id)
    assert ativa is not None
    assert ativa.estado_execucao == EstadoExecucao.FALHOU
    assert ativa.simulacao.erro_planejamento.__class__ is ErroRoteamento
    assert "falha secundária do estado operacional" in caplog.text
    with database.conectar() as conexao:
        estado_persistido = conexao.execute(
            "SELECT planejamento_status FROM simulacoes WHERE id = ?",
            (simulacao_id,),
        ).fetchone()["planejamento_status"]
    assert estado_persistido == "falhou"


def test_value_error_do_planejamento_em_avancar_nao_vira_erro_de_validacao(
    cliente_experimental, monkeypatch
):
    cliente = cliente_experimental

    def falhar_com_value_error(_self, *_args, **_kwargs):
        raise ValueError("erro interno controlado do planejador")

    monkeypatch.setattr(
        DistribuidorPedidos, "planejar", falhar_com_value_error
    )
    simulacao_id = _criar_simulacao(cliente)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/avancar",
        json={"minutos": 1},
    )

    assert resposta.status_code == 500, resposta.json()
    ativa = registro.obter(simulacao_id)
    assert ativa is not None
    assert ativa.estado_execucao == EstadoExecucao.FALHOU
    assert ativa.erro_execucao == (
        "O planejamento falhou. Consulte os logs do backend."
    )
    with database.conectar() as conexao:
        estado_persistido = conexao.execute(
            "SELECT planejamento_status FROM simulacoes WHERE id = ?",
            (simulacao_id,),
        ).fetchone()["planejamento_status"]
    assert estado_persistido == "falhou"


@pytest.mark.parametrize(
    ("endpoint", "corpo"),
    [
        ("proxima-etapa", None),
        ("avancar", {"minutos": 1}),
        ("executar", None),
    ],
)
def test_falha_ao_persistir_inicio_do_planejamento_nos_tres_handlers(
    cliente_experimental, monkeypatch, endpoint, corpo
):
    cliente = cliente_experimental

    def falhar_inicio(_self):
        raise FalhaPersistenciaAuditoriaExperimental(
            "falha controlada ao persistir início"
        )

    monkeypatch.setattr(
        AuditoriaSimulacao, "iniciar_planejamento", falhar_inicio
    )
    simulacao_id = _criar_simulacao(cliente)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/{endpoint}",
        json=corpo,
    )

    assert resposta.status_code == 503, resposta.json()
    ativa = registro.obter(simulacao_id)
    assert ativa is not None
    assert ativa.estado_execucao == EstadoExecucao.FALHOU
    assert ativa.erro_execucao == (
        "Falha ao persistir a auditoria do planejamento."
    )
    with database.conectar() as conexao:
        estado_persistido = conexao.execute(
            "SELECT planejamento_status FROM simulacoes WHERE id = ?",
            (simulacao_id,),
        ).fetchone()["planejamento_status"]
    assert estado_persistido == "falhou"


def test_retry_limpa_erro_operacional_somente_apos_sucesso(
    cliente_experimental, monkeypatch
):
    cliente = cliente_experimental
    planejar_original = DistribuidorPedidos.planejar
    tentativas = 0

    def falhar_duas_vezes_depois_planejar(self, *args, **kwargs):
        nonlocal tentativas
        tentativas += 1
        if tentativas <= 2:
            raise ErroRoteamento(f"falha controlada {tentativas}")
        return planejar_original(self, *args, **kwargs)

    monkeypatch.setattr(
        DistribuidorPedidos, "planejar", falhar_duas_vezes_depois_planejar
    )
    simulacao_id = _criar_simulacao(cliente)["id"]

    primeira = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert primeira.status_code == 502
    ativa = registro.obter(simulacao_id)
    assert ativa is not None
    assert ativa.estado_execucao == EstadoExecucao.FALHOU
    primeiro_erro = ativa.erro_execucao
    assert primeiro_erro is not None

    segunda = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert segunda.status_code == 502
    assert ativa.estado_execucao == EstadoExecucao.FALHOU
    assert ativa.erro_execucao == primeiro_erro

    terceira = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert terceira.status_code == 200, terceira.json()
    assert ativa.estado_execucao == EstadoExecucao.EXECUTANDO
    assert ativa.erro_execucao is None
    with database.conectar() as conexao:
        estado_persistido = conexao.execute(
            "SELECT planejamento_status FROM simulacoes WHERE id = ?",
            (simulacao_id,),
        ).fetchone()["planejamento_status"]
    assert estado_persistido == "concluido"


def test_planejamento_concluido_sem_consultas_e_com_integridade_completa(
    tmp_path, monkeypatch
):
    diretorio = tmp_path / "sem_consultas"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    database.inicializar_banco()
    auditoria = _criar_auditoria()
    distribuidor = DistribuidorPedidos(
        ServicoRoteamentoSimulado(), CENTRO, [Entregador("CAM-01")]
    )
    simulacao = Simulacao([], distribuidor, INICIO)
    simulacao.definir_observador_planejamento(auditoria)
    simulacao.adicionar_observador(auditoria)

    simulacao.executar_ate_o_fim()

    dados = obter_parametros_experimentais(auditoria.simulacao_id)
    assert dados["planejamento"] == {
        "estado": "concluido",
        "integridade": "completa",
        "consultas_esperadas": 0,
        "consultas_registradas": 0,
        "erro": None,
        "problemas": [],
    }
    assert dados["consultas_roteamento"] == []


def test_planejamento_concluido_com_consultas_e_contador_coerente(
    cliente_experimental,
):
    cliente = cliente_experimental
    simulacao_id = _criar_simulacao(cliente)["id"]
    etapa = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert etapa.status_code == 200, etapa.json()

    dados = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    ).json()
    assert dados["planejamento"]["estado"] == "concluido"
    assert dados["planejamento"]["integridade"] == "completa"
    assert dados["planejamento"]["consultas_registradas"] > 0
    assert (
        dados["planejamento"]["consultas_esperadas"]
        == len(dados["consultas_roteamento"])
    )


def test_falha_antes_da_primeira_consulta_fica_persistida(
    cliente_experimental, monkeypatch
):
    cliente = cliente_experimental

    def falhar_antes(_self, *_args, **_kwargs):
        raise ErroRoteamento("falha controlada antes da matriz")

    monkeypatch.setattr(DistribuidorPedidos, "planejar", falhar_antes)
    simulacao_id = _criar_simulacao(cliente)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert resposta.status_code == 502, resposta.json()
    dados = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    ).json()
    assert dados["planejamento"]["estado"] == "falhou"
    assert dados["planejamento"]["integridade"] == "incompleta"
    assert dados["planejamento"]["consultas_esperadas"] == 0
    assert dados["consultas_roteamento"] == []


def test_falha_depois_de_consulta_preserva_trilha_parcial(
    cliente_experimental, monkeypatch
):
    cliente = cliente_experimental
    planejar_original = DistribuidorPedidos.planejar

    def planejar_e_falhar(self, *args, **kwargs):
        planejar_original(self, *args, **kwargs)
        raise ErroRoteamento("falha controlada depois da matriz")

    monkeypatch.setattr(DistribuidorPedidos, "planejar", planejar_e_falhar)
    simulacao_id = _criar_simulacao(cliente)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert resposta.status_code == 502, resposta.json()
    dados = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    ).json()
    assert dados["planejamento"]["estado"] == "falhou"
    assert dados["planejamento"]["integridade"] == "incompleta"
    assert dados["planejamento"]["consultas_esperadas"] > 0
    assert dados["planejamento"]["consultas_registradas"] > 0
    assert dados["consultas_roteamento"]


def test_falha_da_persistencia_da_auditoria_interrompe_planejamento(
    cliente_experimental, monkeypatch
):
    cliente = cliente_experimental

    def falhar_persistencia(_self, **_kwargs):
        raise sqlite3.OperationalError("falha de escrita controlada")

    monkeypatch.setattr(
        AuditoriaSimulacao,
        "registrar_consulta_roteamento",
        falhar_persistencia,
    )
    simulacao_id = _criar_simulacao(cliente)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert resposta.status_code == 503, resposta.json()
    dados = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    ).json()
    assert dados["planejamento"]["estado"] == "falhou"
    assert dados["planejamento"]["consultas_esperadas"] == 0
    assert dados["planejamento"]["consultas_registradas"] == 0
    assert dados["consultas_roteamento"] == []


def test_reinicio_marca_planejamento_pendente_como_interrompido(
    tmp_path, monkeypatch
):
    diretorio = tmp_path / "reinicio_planejamento"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("PROVEDOR_MAPAS", raising=False)
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_NOME", "Comercio")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LATITUDE", "-12.971")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LONGITUDE", "-38.501")
    cenarios = inicializar_todos_cenarios()
    cenario = next(c for c in cenarios if c.codigo == "NORMAL")
    registro.limpar()

    with TestClient(app) as cliente:
        criada = _criar_simulacao_com_cenario(cliente, cenario.id)
        simulacao_id = criada["id"]
        with database.conectar() as conexao:
            conexao.execute(
                "UPDATE simulacoes SET planejamento_status = 'planejando' WHERE id = ?",
                (simulacao_id,),
            )

    registro.limpar()
    with TestClient(app) as reiniciado:
        dados = reiniciado.get(
            f"/api/simulacoes/{simulacao_id}/parametros"
        ).json()
        assert dados["planejamento"]["estado"] == "interrompido"
        assert dados["planejamento"]["integridade"] == "incompleta"
        assert dados["planejamento"]["erro"] == "ProcessoReiniciado"
    registro.limpar()


def _criar_simulacao_com_cenario(cliente, cenario_id):
    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario_id,
            "inicio": INICIO_API,
            "provedor": "simulado",
        },
    )
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()


@pytest.mark.parametrize(
    "defeito", ["sequencia", "contador", "resposta", "snapshot"]
)
def test_endpoint_detecta_lacuna_contador_divergente_e_resposta_ausente(
    cliente_experimental, defeito
):
    cliente = cliente_experimental
    simulacao_id = _criar_simulacao(cliente)["id"]
    etapa = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert etapa.status_code == 200, etapa.json()

    with database.conectar() as conexao:
        consultas = conexao.execute(
            """
            SELECT id, sequencia, resposta_id
            FROM consultas_roteamento_simulacao
            WHERE simulacao_id = ? ORDER BY sequencia
            """,
            (simulacao_id,),
        ).fetchall()
        assert consultas
        if defeito == "sequencia":
            conexao.execute(
                "DROP TRIGGER trg_consultas_roteamento_immutable"
            )
            conexao.execute(
                "UPDATE consultas_roteamento_simulacao SET sequencia = ? WHERE id = ?",
                (consultas[0]["sequencia"] + len(consultas) + 1, consultas[0]["id"]),
            )
        elif defeito == "contador":
            conexao.execute(
                "UPDATE simulacoes SET consultas_roteamento_contagem = consultas_roteamento_contagem + 1 WHERE id = ?",
                (simulacao_id,),
            )
        elif defeito == "snapshot":
            conexao.execute(
                "DROP TRIGGER trg_simulacao_pedidos_snapshot_no_delete"
            )
            conexao.execute(
                "DELETE FROM simulacao_pedidos_snapshot WHERE simulacao_id = ?",
                (simulacao_id,),
            )

    if defeito == "resposta":
        conexao = sqlite3.connect(database.DATABASE_PATH)
        try:
            conexao.execute("PRAGMA foreign_keys = OFF")
            conexao.execute(
                "DELETE FROM respostas_roteamento WHERE id = ?",
                (consultas[0]["resposta_id"],),
            )
            conexao.commit()
        finally:
            conexao.close()

    dados = cliente.get(
        f"/api/simulacoes/{simulacao_id}/parametros"
    ).json()
    assert dados["planejamento"]["integridade"] == "incompleta"
    problemas = dados["planejamento"]["problemas"]
    esperado = {
        "sequencia": "sequencia_com_lacuna_ou_desordenada",
        "contador": "contador_de_consultas_divergente",
        "resposta": "resposta_de_roteamento_ausente",
        "snapshot": "snapshot_ausente",
    }[defeito]
    assert esperado in problemas


def test_post_201_e_falha_automatica_de_planejamento_visivel_no_estado(
    tmp_path, monkeypatch
):
    diretorio = tmp_path / "falha_automatica"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "true")
    monkeypatch.setenv("INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS", "0.01")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("PROVEDOR_MAPAS", raising=False)
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_NOME", "Comercio")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LATITUDE", "-12.971")
    monkeypatch.setenv("CENTRO_DISTRIBUICAO_LONGITUDE", "-38.501")
    cenarios = inicializar_todos_cenarios()
    cenario = next(c for c in cenarios if c.codigo == "NORMAL")
    registro.limpar()
    entrou_no_planejamento = Event()
    liberar_falha = Event()

    def falhar_planejamento(_self, *_args, **_kwargs):
        entrou_no_planejamento.set()
        if not liberar_falha.wait(2):
            raise RuntimeError("o teste não liberou a falha controlada")
        raise ErroRoteamento("falha automática controlada no planejamento")

    monkeypatch.setattr(
        DistribuidorPedidos, "planejar", falhar_planejamento
    )

    with TestClient(app) as cliente:
        try:
            criada = _criar_simulacao_com_cenario(cliente, cenario.id)
            simulacao_id = criada["id"]
            assert criada["estado_execucao"] == "executando"
            assert entrou_no_planejamento.wait(2)

            tarefa = cliente.app.state.execucao_automatica._tarefas[
                simulacao_id
            ]
            liberar_falha.set()

            async def aguardar_tarefa():
                await tarefa

            cliente.portal.call(aguardar_tarefa)
            estado = cliente.get(f"/api/simulacoes/{simulacao_id}")
            assert estado.status_code == 200
            assert estado.json()["estado_execucao"] == "falhou"
            assert "falha automática controlada" in estado.json()[
                "erro_execucao"
            ]

            auditoria = cliente.get(
                f"/api/simulacoes/{simulacao_id}/parametros"
            ).json()
            assert auditoria["planejamento"]["estado"] == "falhou"
            assert auditoria["planejamento"]["integridade"] == "incompleta"
        finally:
            liberar_falha.set()
            registro.limpar()

