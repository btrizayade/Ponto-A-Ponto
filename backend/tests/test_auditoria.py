from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.distribution import CentroDistribuicao, DistribuidorPedidos
from app.domain.models import Bairro, CategoriaProduto, Entregador, Pedido
from app.domain.models import StatusPedido as S
from app.domain.routing import Coordenada
from app.domain.simulation import Simulacao, TipoEvento as T
from app.infrastructure import database
from app.infrastructure.auditoria_repository import (
    AuditoriaSimulacao,
    executar_consulta_auditoria,
    listar_eventos,
    obter_status_dos_pedidos,
)
from app.infrastructure.seed import (
    inicializar_bairros_cenario_01,
    inicializar_cenario_01,
    inicializar_pedidos_cenario_01,
)
from app.infrastructure.simulacao_factory import criar_simulacao_auditada
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


FUSO = ZoneInfo("America/Bahia")
INICIO = datetime(2026, 10, 30, 16, 0, tzinfo=FUSO)
CRIADO_EM = datetime(2026, 10, 29, 9, 0, tzinfo=FUSO)
CENTRO = CentroDistribuicao("Comercio", Coordenada(-12.971, -38.501))

BARRA = Bairro("Barra", -13.006, -38.528)
PITUBA = Bairro("Pituba", -12.999, -38.460)
ITAPUA = Bairro("Itapua", -12.940, -38.358)


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    """Prepara um banco isolado para cada teste."""

    diretorio = tmp_path / "data"

    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")

    database.inicializar_banco()


def criar_pedido(codigo, bairro, prazo=None, peso_kg=1.0):
    return Pedido(
        codigo=codigo,
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=1,
        criado_em=CRIADO_EM,
        prazo_entrega_em=prazo or INICIO + timedelta(days=3),
        peso_kg=peso_kg,
    )


@pytest.fixture
def simulacao_auditada(banco_temporario):
    """
    Simulacao das 16h com uma parada por viagem, para haver entrega
    atrasada, viagem cancelada pelo expediente e pedido sem caminhao.
    """

    pedidos = [
        criar_pedido("P1", BARRA),
        criar_pedido("P2", ITAPUA, prazo=INICIO + timedelta(minutes=20)),
        criar_pedido("P3", PITUBA),
        criar_pedido("P4", BARRA),
        criar_pedido("PESADO", PITUBA, peso_kg=900),
    ]
    entregadores = [
        Entregador("CAM-01", max_paradas_por_viagem=1),
        Entregador("CAM-02", max_paradas_por_viagem=1),
    ]
    distribuidor = DistribuidorPedidos(
        ServicoRoteamentoSimulado(fator_transito=1.0), CENTRO, entregadores
    )
    auditoria = AuditoriaSimulacao.criar(
        INICIO, CENTRO, entregadores, "DistribuicaoInsercaoMaisBarata"
    )
    simulacao = Simulacao(
        pedidos, distribuidor, INICIO, observadores=[auditoria]
    )
    simulacao.executar_ate_o_fim()

    return simulacao, auditoria.simulacao_id


def consultar(nome, simulacao_id, **parametros):
    return executar_consulta_auditoria(
        nome, {"simulacao_id": simulacao_id, **parametros}
    )


# Gravacao


def test_eventos_gravados_iguais_ao_historico(simulacao_auditada):
    simulacao, simulacao_id = simulacao_auditada

    gravados = listar_eventos(simulacao_id)

    assert gravados == simulacao.historico


def test_status_gravado_igual_ao_da_simulacao(simulacao_auditada):
    simulacao, simulacao_id = simulacao_auditada

    assert obter_status_dos_pedidos(simulacao_id) == (
        simulacao.status_dos_pedidos()
    )


def test_execucao_fica_concluida_com_o_fim_simulado(simulacao_auditada):
    simulacao, simulacao_id = simulacao_auditada

    with database.conectar() as conexao:
        registro = conexao.execute(
            "SELECT * FROM simulacoes WHERE id = ?", (simulacao_id,)
        ).fetchone()

    assert registro["status"] == "concluida"
    assert datetime.fromisoformat(registro["fim_simulado"]) == (
        simulacao.agora
    )
    assert registro["entregadores"] == "CAM-01,CAM-02"


def test_execucao_em_andamento_ate_o_ultimo_evento(banco_temporario):
    auditoria = AuditoriaSimulacao.criar(
        INICIO, CENTRO, [Entregador("CAM-01")], "Teste"
    )
    distribuidor = DistribuidorPedidos(
        ServicoRoteamentoSimulado(fator_transito=1.0),
        CENTRO,
        [Entregador("CAM-01")],
    )
    simulacao = Simulacao(
        [criar_pedido("P1", BARRA)],
        distribuidor,
        INICIO,
        observadores=[auditoria],
    )

    simulacao.iniciar()

    with database.conectar() as conexao:
        status = conexao.execute(
            "SELECT status FROM simulacoes WHERE id = ?",
            (auditoria.simulacao_id,),
        ).fetchone()["status"]

    assert status == "em_andamento"
    assert len(listar_eventos(auditoria.simulacao_id)) == len(
        simulacao.historico
    )


def test_simulacoes_do_mesmo_cenario_ficam_separadas(simulacao_auditada):
    _, primeira = simulacao_auditada
    auditoria = AuditoriaSimulacao.criar(
        INICIO, CENTRO, [Entregador("CAM-01")], "Teste"
    )

    assert auditoria.simulacao_id != primeira
    assert listar_eventos(auditoria.simulacao_id) == []


# Consultas de sql/auditoria


def test_linha_do_tempo_do_pedido(simulacao_auditada):
    _, simulacao_id = simulacao_auditada

    linhas = consultar(
        "linha_do_tempo_pedido", simulacao_id, pedido_codigo="P1"
    )

    assert [(l["status_anterior"], l["status_novo"]) for l in linhas] == [
        ("pendente", "na_fila"),
        ("na_fila", "atribuido"),
        ("atribuido", "em_rota"),
        ("em_rota", "entregue"),
    ]
    assert [l["sequencia"] for l in linhas] == sorted(
        l["sequencia"] for l in linhas
    )


def test_consulta_de_atrasos(simulacao_auditada):
    simulacao, simulacao_id = simulacao_auditada
    atrasadas = {
        e.pedido_codigo: e.atraso_min
        for e in simulacao.historico
        if e.tipo == T.PEDIDO_ENTREGUE and e.atraso_min > 0
    }

    linhas = consultar("atrasos", simulacao_id)

    assert "P2" in atrasadas
    assert {l["pedido_codigo"] for l in linhas} == set(atrasadas)
    assert linhas[0]["atraso_min"] == round(max(atrasadas.values()), 1)


def test_consulta_de_desempenho_por_caminhao(simulacao_auditada):
    simulacao, simulacao_id = simulacao_auditada
    historico = simulacao.historico

    linhas = consultar("desempenho_por_caminhao", simulacao_id)

    assert [l["entregador_codigo"] for l in linhas] == ["CAM-01", "CAM-02"]

    for linha in linhas:
        do_caminhao = [
            e for e in historico
            if e.entregador_codigo == linha["entregador_codigo"]
        ]
        concluidas = [e for e in do_caminhao if e.tipo == T.VIAGEM_CONCLUIDA]

        assert linha["viagens_concluidas"] == len(concluidas)
        assert linha["viagens_canceladas"] == sum(
            e.tipo == T.VIAGEM_CANCELADA for e in do_caminhao
        )
        assert linha["pedidos_entregues"] == sum(
            e.tipo == T.PEDIDO_ENTREGUE for e in do_caminhao
        )
        assert linha["distancia_km"] == round(
            sum(e.distancia_m for e in concluidas) / 1000, 1
        )

    assert sum(l["viagens_canceladas"] for l in linhas) > 0


def test_consulta_de_pedidos_nao_entregues(simulacao_auditada):
    simulacao, simulacao_id = simulacao_auditada
    nao_entregues = {
        codigo
        for codigo, status in simulacao.status_dos_pedidos().items()
        if status != S.ENTREGUE
    }

    linhas = {l["pedido_codigo"]: l for l in consultar(
        "pedidos_nao_entregues", simulacao_id
    )}

    assert set(linhas) == nao_entregues
    assert linhas["PESADO"]["ultimo_evento"] == "pedido_nao_atribuido"
    assert any(
        l["ultimo_evento"] == "pedido_devolvido_a_fila"
        and "expediente" in l["motivo"]
        for l in linhas.values()
    )
    assert all(l["status_final"] == "na_fila" for l in linhas.values())


@pytest.mark.parametrize("nome", ["nao_existe", "../schema", "atrasos.sql"])
def test_consulta_desconhecida_e_rejeitada(banco_temporario, nome):
    with pytest.raises(ValueError):
        executar_consulta_auditoria(nome, {"simulacao_id": 1})


# Fabrica


def test_simulacao_auditada_do_cenario_do_seed(banco_temporario):
    cenario = inicializar_cenario_01()
    pedidos = inicializar_pedidos_cenario_01(
        cenario, inicializar_bairros_cenario_01()
    )

    simulacao, auditoria = criar_simulacao_auditada(
        cenario.id,
        datetime(2026, 10, 30, 9, 0, tzinfo=FUSO),
        servico=ServicoRoteamentoSimulado(fator_transito=1.0),
        centro=CENTRO,
        entregadores=[Entregador("CAM-01"), Entregador("CAM-02")],
    )
    simulacao.executar_ate_o_fim()

    with database.conectar() as conexao:
        registro = conexao.execute(
            "SELECT * FROM simulacoes WHERE id = ?",
            (auditoria.simulacao_id,),
        ).fetchone()

    assert registro["cenario_id"] == cenario.id
    assert registro["estrategia"] == "DistribuicaoInsercaoMaisBarata"
    assert registro["status"] == "concluida"
    assert listar_eventos(auditoria.simulacao_id) == simulacao.historico
    assert set(obter_status_dos_pedidos(auditoria.simulacao_id)) == {
        p.codigo for p in pedidos
    }


def test_simulacao_de_cenario_sem_pedidos_e_rejeitada(banco_temporario):
    cenario = inicializar_cenario_01()

    with pytest.raises(ValueError):
        criar_simulacao_auditada(
            cenario.id,
            datetime(2026, 10, 30, 9, 0, tzinfo=FUSO),
            servico=ServicoRoteamentoSimulado(fator_transito=1.0),
        )


def test_schema_aceita_todos_os_tipos_de_evento():
    esquema = database.SCHEMA_PATH.read_text(encoding="utf-8")
    trecho = esquema[esquema.index("CREATE TABLE IF NOT EXISTS eventos_simulacao"):]
    trecho = trecho[:trecho.index(");\n")]

    for tipo in T:
        assert f"'{tipo.value}'" in trecho


def test_fabrica_rejeita_lista_vazia_de_entregadores(banco_temporario):
    cenario = inicializar_cenario_01()
    inicializar_pedidos_cenario_01(cenario, inicializar_bairros_cenario_01())

    with pytest.raises(ValueError, match="entregador"):
        criar_simulacao_auditada(
            cenario.id,
            datetime(2026, 10, 30, 9, 0, tzinfo=FUSO),
            servico=ServicoRoteamentoSimulado(fator_transito=1.0),
            entregadores=[],
        )
