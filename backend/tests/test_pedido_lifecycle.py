from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import sqlite3
from threading import Event
from zoneinfo import ZoneInfo

import pytest

from app.domain.models import OrigemPedido
from fastapi.testclient import TestClient
from app.api.registro import registro
from app.infrastructure import database
from app.infrastructure import auditoria_repository, pedido_repository
from app.infrastructure.auditoria_repository import (
    listar_eventos,
    obter_simulacao,
)
from app.infrastructure.bairro_repository import listar_bairros
from app.infrastructure.cenario_repository import listar_cenarios
from app.infrastructure.pedido_factory import criar_pedido_do_formulario
from app.infrastructure.pedido_repository import (
    listar_pedidos_por_cenario,
    obter_ou_criar_pedido,
)
from app.infrastructure.seed import inicializar_todos_cenarios
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado
from app.infrastructure.simulacao_factory import criar_simulacao_auditada
from app.main import app
from app.domain.models import CategoriaProduto, ModalidadeEntrega


FUSO = ZoneInfo("America/Bahia")
INICIO = datetime(2026, 10, 30, 10, 0, tzinfo=FUSO)
INICIO_NORMAL = datetime(2026, 10, 7, 9, 0, tzinfo=FUSO)


@pytest.fixture
def cenario_com_banco(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "ciclo.db")
    cenarios = inicializar_todos_cenarios()
    return {cenario.codigo: cenario for cenario in cenarios}


def cadastrar_manual(cenario_id, codigo, bairro=None, criado_em=None):
    bairro = bairro or listar_bairros()[0]
    pedido = criar_pedido_do_formulario(
        bairro,
        CategoriaProduto.ALIMENTO,
        ModalidadeEntrega.CONVENCIONAL,
        criado_em=criado_em or datetime(2026, 10, 30, 9, 0, tzinfo=FUSO),
    )
    pedido.codigo = codigo
    return obter_ou_criar_pedido(
        pedido, cenario_id, origem=OrigemPedido.MANUAL
    )


def simular(cenario_id):
    simulacao, auditoria = criar_simulacao_auditada(
        cenario_id,
        INICIO,
        servico=ServicoRoteamentoSimulado(fator_transito=1.0),
    )
    simulacao.executar_ate_o_fim()
    return simulacao, auditoria


@pytest.mark.parametrize(
    ("codigo", "quantidade_referencia"),
    [("NORMAL", 10), ("EQUIDADE", 15), ("ALTA_DEMANDA", 24)],
)
def test_conclusao_remove_pedidos_manuais_mas_preserva_referencias(
    cenario_com_banco, codigo, quantidade_referencia
):
    cenario = cenario_com_banco[codigo]
    cadastrar_manual(cenario.id, "MANUAL-REMOVER")

    assert len(listar_pedidos_por_cenario(cenario.id)) == quantidade_referencia + 1
    simulacao, auditoria = simular(cenario.id)
    simulacao_id = auditoria.simulacao_id

    pedidos_ativos = listar_pedidos_por_cenario(cenario.id)
    assert len(simulacao.pedidos) == quantidade_referencia + 1
    assert len(pedidos_ativos) == quantidade_referencia
    assert {pedido.origem for pedido in pedidos_ativos} == {
        OrigemPedido.REFERENCIA
    }
    assert obter_simulacao(simulacao_id)["status"] == "concluida"
    assert any(evento.tipo.value == "simulacao_concluida"
               for evento in listar_eventos(simulacao_id))

    with database.conectar() as conexao:
        manual = conexao.execute(
            "SELECT origem, ativo FROM pedidos WHERE codigo = ?",
            ("MANUAL-REMOVER",),
        ).fetchone()
    assert tuple(manual) == ("manual", 0)

    proxima, _ = simular(cenario.id)
    assert len(proxima.pedidos) == quantidade_referencia
    assert len(listar_pedidos_por_cenario(cenario.id)) == quantidade_referencia


def test_pedido_adicionado_apos_snapshot_fica_para_proxima_simulacao(
    cenario_com_banco,
):
    normal = cenario_com_banco["NORMAL"]
    cadastrar_manual(normal.id, "MANUAL-DO-SNAPSHOT")
    simulacao, _ = criar_simulacao_auditada(
        normal.id,
        INICIO,
        servico=ServicoRoteamentoSimulado(fator_transito=1.0),
    )
    cadastrar_manual(normal.id, "MANUAL-PROXIMA-SIMULACAO")

    simulacao.executar_ate_o_fim()
    ativos = listar_pedidos_por_cenario(normal.id)
    assert len(ativos) == 11
    assert {pedido.codigo for pedido in ativos} == {
        *(f"PED-{numero:03d}" for numero in range(1, 11)),
        "MANUAL-PROXIMA-SIMULACAO",
    }


def test_manual_futuro_mais_antigo_que_manual_do_snapshot_permanece_ativo(
    cenario_com_banco,
):
    normal = cenario_com_banco["NORMAL"]
    futuro = cadastrar_manual(
        normal.id,
        "MANUAL-FUTURO-ANTIGO",
        criado_em=datetime(2026, 10, 8, 9, 0, tzinfo=FUSO),
    )
    incluido = cadastrar_manual(
        normal.id,
        "MANUAL-INCLUIDO-SNAPSHOT",
        criado_em=INICIO_NORMAL,
    )
    assert futuro.id < incluido.id

    simulacao, auditoria = criar_simulacao_auditada(
        normal.id,
        INICIO_NORMAL,
        servico=ServicoRoteamentoSimulado(fator_transito=1.0),
    )
    codigos_snapshot = {pedido.codigo for pedido in simulacao.pedidos}
    assert "MANUAL-FUTURO-ANTIGO" not in codigos_snapshot
    assert "MANUAL-INCLUIDO-SNAPSHOT" in codigos_snapshot

    simulacao.executar_ate_o_fim()

    with database.conectar() as conexao:
        registros = conexao.execute(
            """
            SELECT codigo, ativo
            FROM pedidos
            WHERE id IN (?, ?)
            ORDER BY id
            """,
            (futuro.id, incluido.id),
        ).fetchall()

    assert [(registro["codigo"], registro["ativo"]) for registro in registros] == [
        ("MANUAL-FUTURO-ANTIGO", 1),
        ("MANUAL-INCLUIDO-SNAPSHOT", 0),
    ]
    assert obter_simulacao(auditoria.simulacao_id)["status"] == "concluida"


def test_cadastro_durante_arquivamento_preserva_pedido_fora_do_snapshot(
    cenario_com_banco, monkeypatch
):
    normal = cenario_com_banco["NORMAL"]
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    registro.limpar()

    conclusao_no_arquivamento = Event()
    liberar_arquivamento = Event()
    liberar_retentativa_insercao = Event()
    insercao_bloqueada_pelo_sqlite = Event()

    class ConexaoInterceptada:
        def __init__(
            self,
            conexao,
            interceptar,
            bloqueio=None,
            aguardar_retentativa=None,
        ):
            self._conexao = conexao
            self._interceptar = interceptar
            self._bloqueio = bloqueio
            self._aguardar_retentativa = aguardar_retentativa

        def execute(self, sql, parametros=()):
            consulta = sql.lstrip().upper()
            if self._interceptar(consulta):
                if self._bloqueio is not None:
                    assert self._bloqueio.wait(5), (
                        "O teste não liberou a operação SQLite suspensa."
                    )
                try:
                    return self._conexao.execute(sql, parametros)
                except sqlite3.OperationalError as erro:
                    if (
                        self._aguardar_retentativa is None
                        or "locked" not in str(erro).lower()
                    ):
                        raise
                    insercao_bloqueada_pelo_sqlite.set()
                    assert self._aguardar_retentativa.wait(5), (
                        "A conclusão não liberou o lock SQLite para o "
                        "cadastro concorrente."
                    )
                    self._conexao.rollback()
                    return self._conexao.execute(sql, parametros)
            return self._conexao.execute(sql, parametros)

    conexao_auditoria_original = auditoria_repository.conectar

    def interceptar_arquivamento(consulta):
        if (
            consulta.startswith("UPDATE PEDIDOS")
            and "ORIGEM = 'MANUAL'" in consulta
        ):
            conclusao_no_arquivamento.set()
            return True
        return False

    def interceptar_insercao(consulta):
        if consulta.startswith("INSERT INTO PEDIDOS"):
            return True
        return False

    @contextmanager
    def conectar_auditoria_controlada():
        with conexao_auditoria_original() as conexao:
            yield ConexaoInterceptada(
                conexao,
                interceptar_arquivamento,
                bloqueio=liberar_arquivamento,
            )

    @contextmanager
    def conectar_pedidos_controlada():
        conexao = sqlite3.connect(database.DATABASE_PATH, timeout=0)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        try:
            yield ConexaoInterceptada(
                conexao,
                interceptar_insercao,
                aguardar_retentativa=liberar_retentativa_insercao,
            )
            conexao.commit()
        except Exception:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    monkeypatch.setattr(
        auditoria_repository, "conectar", conectar_auditoria_controlada
    )
    monkeypatch.setattr(
        pedido_repository, "conectar", conectar_pedidos_controlada
    )

    try:
        with TestClient(app) as cliente:
            bairro_id = listar_bairros()[0].id
            corpo_pedido = {
                "cenario_id": normal.id,
                "bairro_id": bairro_id,
                "data_criacao": "2026-10-07",
                "categoria_produto": "alimento",
                "modalidade": "convencional",
            }
            pedido_snapshot = cliente.post("/api/pedidos", json=corpo_pedido)
            assert pedido_snapshot.status_code == 201, pedido_snapshot.json()
            codigo_snapshot = pedido_snapshot.json()["codigo"]

            criada = cliente.post(
                "/api/simulacoes",
                json={
                    "cenario_id": normal.id,
                    "inicio": INICIO.isoformat(),
                    "provedor": "simulado",
                },
            )
            assert criada.status_code == 201, criada.json()
            simulacao_id = criada.json()["id"]
            assert codigo_snapshot in {
                pedido.codigo
                for pedido in registro.obter(simulacao_id).simulacao.pedidos
            }

            with ThreadPoolExecutor(max_workers=2) as executor:
                futuro_conclusao = executor.submit(
                    cliente.post, f"/api/simulacoes/{simulacao_id}/executar"
                )
                futuro_cadastro = None
                try:
                    assert conclusao_no_arquivamento.wait(5), (
                        "A conclusão não chegou ao comando de arquivamento."
                    )
                    futuro_cadastro = executor.submit(
                        cliente.post, "/api/pedidos", json=corpo_pedido
                    )
                    assert insercao_bloqueada_pelo_sqlite.wait(5), (
                        "O INSERT independente não encontrou o lock SQLite "
                        "da transação de conclusão."
                    )
                    liberar_arquivamento.set()
                    resposta_conclusao = futuro_conclusao.result(timeout=5)
                finally:
                    liberar_arquivamento.set()
                    liberar_retentativa_insercao.set()

                assert futuro_cadastro is not None
                resposta_cadastro = futuro_cadastro.result(timeout=5)

            assert resposta_conclusao.status_code == 200
            assert resposta_conclusao.json()["estado"]["concluida"] is True
            assert resposta_cadastro.status_code == 201, resposta_cadastro.json()
            codigo_novo = resposta_cadastro.json()["codigo"]
            assert codigo_novo != codigo_snapshot

            pedidos_ativos = listar_pedidos_por_cenario(normal.id)
            codigos_ativos = [pedido.codigo for pedido in pedidos_ativos]
            assert codigos_ativos.count(codigo_snapshot) == 0
            assert codigos_ativos.count(codigo_novo) == 1
            assert len(codigos_ativos) == 11

            with database.conectar() as conexao:
                registros = conexao.execute(
                    """
                    SELECT codigo, origem, ativo
                    FROM pedidos
                    WHERE codigo IN (?, ?)
                    ORDER BY codigo
                    """,
                    (codigo_snapshot, codigo_novo),
                ).fetchall()
            por_codigo = {linha["codigo"]: linha for linha in registros}
            assert len(registros) == 2
            assert (por_codigo[codigo_snapshot]["origem"],
                    por_codigo[codigo_snapshot]["ativo"]) == ("manual", 0)
            assert (por_codigo[codigo_novo]["origem"],
                    por_codigo[codigo_novo]["ativo"]) == ("manual", 1)

            eventos = listar_eventos(simulacao_id)
            assert any(
                evento.pedido_codigo == codigo_snapshot
                for evento in eventos
            )
            assert any(
                evento.tipo.value == "simulacao_concluida"
                for evento in eventos
            )
    finally:
        liberar_arquivamento.set()
        registro.limpar()


def test_limpeza_e_isolada_por_cenario_e_arquivamento_e_idempotente(
    cenario_com_banco,
):
    normal = cenario_com_banco["NORMAL"]
    equidade = cenario_com_banco["EQUIDADE"]
    cadastrar_manual(normal.id, "MANUAL-NORMAL")
    cadastrar_manual(equidade.id, "MANUAL-EQUIDADE")

    simulacao, auditoria = simular(normal.id)
    simulacao_id = auditoria.simulacao_id
    assert len(listar_pedidos_por_cenario(normal.id)) == 10
    assert len(listar_pedidos_por_cenario(equidade.id)) == 16

    # Reenviar o evento final nao duplica auditoria nem muda outros cenarios.
    eventos_antes = listar_eventos(simulacao_id)
    auditoria.registrar(simulacao.historico[-1])
    assert listar_eventos(simulacao_id) == eventos_antes
    assert len(listar_pedidos_por_cenario(normal.id)) == 10
    assert len(listar_pedidos_por_cenario(equidade.id)) == 16


def test_pausa_e_execucao_em_andamento_nao_arquivam_pedidos(
    cenario_com_banco, monkeypatch
):
    normal = cenario_com_banco["NORMAL"]
    cadastrar_manual(
        normal.id,
        "MANUAL-PAUSA",
        criado_em=datetime(2026, 10, 7, 9, 0, tzinfo=FUSO),
    )
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    registro.limpar()

    with TestClient(app) as cliente:
        criada = cliente.post(
            "/api/simulacoes",
            json={
                "cenario_id": normal.id,
                "inicio": INICIO.isoformat(),
                "provedor": "simulado",
            },
        )
        assert criada.status_code == 201, criada.json()
        simulacao_id = criada.json()["id"]

        etapa = cliente.post(
            f"/api/simulacoes/{simulacao_id}/proxima-etapa"
        )
        assert etapa.status_code == 200, etapa.json()
        assert len(listar_pedidos_por_cenario(normal.id)) == 11

        pausa = cliente.post(f"/api/simulacoes/{simulacao_id}/pausar")
        assert pausa.status_code == 200, pausa.json()
        assert len(listar_pedidos_por_cenario(normal.id)) == 11

        retomada = cliente.post(f"/api/simulacoes/{simulacao_id}/retomar")
        assert retomada.status_code == 200, retomada.json()
        assert len(listar_pedidos_por_cenario(normal.id)) == 11

        concluida = cliente.post(f"/api/simulacoes/{simulacao_id}/executar")
        assert concluida.status_code == 200, concluida.json()
        assert concluida.json()["estado"]["concluida"] is True
        assert len(listar_pedidos_por_cenario(normal.id)) == 10

    registro.limpar()


def test_migracao_e_seed_mantem_15_referencias_no_equidade(cenario_com_banco):
    equidade = cenario_com_banco["EQUIDADE"]
    # Simula o registro excedente do banco legado anterior (seed de 16).
    with database.conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO pedidos (
                codigo, cenario_id, bairro_id, categoria_produto,
                cliente_clube, entrega_rapida, sla_dias_uteis, peso_kg,
                volume_l, tempo_servico_min, criado_em, prazo_entrega_em,
                    status, origem, ativo
            )
            SELECT
                'EQ-016', cenario_id, bairro_id, categoria_produto,
                cliente_clube, entrega_rapida, sla_dias_uteis, peso_kg,
                volume_l, tempo_servico_min, criado_em, prazo_entrega_em,
                    status, 'referencia', 1
            FROM pedidos
            WHERE cenario_id = ? AND codigo = 'EQ-015'
            """,
            (equidade.id,),
        )

    database.inicializar_banco()
    with database.conectar() as conexao:
        legado = conexao.execute(
            "SELECT origem, ativo FROM pedidos WHERE codigo = 'EQ-016'"
        ).fetchone()
    assert tuple(legado) == ("referencia", 0)

    pedidos = listar_pedidos_por_cenario(equidade.id)
    assert len(pedidos) == 15
    assert all(pedido.origem == OrigemPedido.REFERENCIA for pedido in pedidos)
    assert len({pedido.bairro.id for pedido in pedidos}) == 8
    assert equidade.descricao.startswith("15 pedidos próprios")

    inicializar_todos_cenarios()
    assert len(listar_pedidos_por_cenario(equidade.id)) == 15
