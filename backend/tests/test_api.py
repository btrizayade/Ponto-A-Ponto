import pytest
from fastapi.testclient import TestClient

from app.api.registro import registro
from app.domain.routing import ErroRoteamento
from app.infrastructure import database
from app.infrastructure.controle_uso_api import LimiteUsoExcedido
from app.infrastructure.google_routes import VARIAVEL_CHAVE_API
from app.infrastructure.routing_factory import VARIAVEL_PROVEDOR
from app.infrastructure.seed import (
    inicializar_bairros_cenario_01,
    inicializar_cenario_01,
    inicializar_pedidos_cenario_01,
)
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado
from app.main import app


# Sexta-feira, 30/10/2026, no horario de Salvador.
INICIO = "2026-10-30T09:00:00-03:00"
INICIO_TARDE = "2026-10-30T16:30:00-03:00"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """API com banco isolado, cenario do seed e provedor simulado."""

    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    monkeypatch.delenv(VARIAVEL_CHAVE_API, raising=False)
    monkeypatch.delenv(VARIAVEL_PROVEDOR, raising=False)
    monkeypatch.delenv("QUANTIDADE_ENTREGADORES", raising=False)

    database.inicializar_banco()
    cenario = inicializar_cenario_01()
    inicializar_pedidos_cenario_01(cenario, inicializar_bairros_cenario_01())
    registro.limpar()

    with TestClient(app) as cliente:
        cliente.cenario_id = cenario.id
        yield cliente

    registro.limpar()


def criar(cliente, **dados):
    resposta = cliente.post(
        "/api/simulacoes",
        json={"cenario_id": cliente.cenario_id, "inicio": INICIO, **dados},
    )
    assert resposta.status_code == 201, resposta.json()

    return resposta.json()


def acao(cliente, simulacao_id, nome, **corpo):
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/{nome}", json=corpo or None
    )
    assert resposta.status_code == 200, resposta.json()

    return resposta.json()


# Configuracao e cenarios


def test_health(cliente):
    assert cliente.get("/api/health").json()["status"] == "ok"


def test_configuracao_sem_chave_do_google(cliente):
    config = cliente.get("/api/configuracao").json()

    assert config["provedor_padrao"] == "simulado"
    assert {p["nome"]: p["disponivel"] for p in config["provedores"]} == {
        "google": False,
        "simulado": True,
    }
    assert config["estrategias"] == ["insercao_mais_barata", "ordem_da_fila"]
    assert config["quantidade_entregadores_padrao"] == 2
    assert config["expediente"] == {"inicio": "09:00", "fim": "17:00"}


def test_lista_cenarios_e_pedidos(cliente):
    cenarios = cliente.get("/api/cenarios").json()

    assert [c["codigo"] for c in cenarios] == ["NORMAL"]
    assert cenarios[0]["quantidade_pedidos"] == 10

    pedidos = cliente.get(f"/api/cenarios/{cliente.cenario_id}/pedidos").json()

    assert len(pedidos) == 10
    assert pedidos[0]["codigo"] == "PED-001"
    assert pedidos[0]["bairro"] == "Comercio"


def test_pedidos_de_cenario_inexistente(cliente):
    assert cliente.get("/api/cenarios/999/pedidos").status_code == 404


# Criacao


def test_simulacao_criada_comeca_parada(cliente):
    estado = criar(cliente)

    assert not estado["iniciada"]
    assert estado["agora"] == INICIO
    assert estado["provedor"] == "simulado"
    assert estado["estrategia"] == "insercao_mais_barata"
    assert estado["fila"] == []
    assert len(estado["entregadores"]) == 2
    assert estado["indicadores"]["por_status"]["pendente"] == 10

    gravadas = cliente.get("/api/simulacoes").json()

    assert gravadas[0]["id"] == estado["id"]
    assert gravadas[0]["ativa"]
    assert gravadas[0]["status"] == "em_andamento"


def test_parametros_da_criacao(cliente):
    estado = criar(
        cliente, quantidade_entregadores=3, estrategia="ordem_da_fila"
    )

    assert [e["codigo"] for e in estado["entregadores"]] == [
        "CAM-01",
        "CAM-02",
        "CAM-03",
    ]
    assert estado["estrategia"] == "ordem_da_fila"
    assert cliente.get("/api/simulacoes").json()[0]["estrategia"] == (
        "ordem_da_fila"
    )


def test_inicio_sem_fuso_usa_o_horario_de_salvador(cliente):
    estado = criar(cliente, inicio="2026-10-30T09:00:00")

    assert estado["agora"] == INICIO


def test_horarios_em_outro_fuso_sao_convertidos_para_salvador(cliente):
    simulacao_id = criar(cliente, inicio="2026-10-30T12:00:00Z")["id"]

    resultado = acao(cliente, simulacao_id, "proxima-etapa")
    gravados = cliente.get(f"/api/simulacoes/{simulacao_id}/eventos").json()

    assert resultado["estado"]["agora"] == INICIO
    assert resultado["eventos"] == gravados

    estado = acao(
        cliente, simulacao_id, "avancar", ate="2026-10-30T13:00:00Z"
    )["estado"]
    assert estado["agora"] == "2026-10-30T10:00:00-03:00"


@pytest.mark.parametrize(
    "dados, codigo",
    [
        ({"cenario_id": 999}, 404),
        ({"inicio": "2026-10-31T09:00:00-03:00"}, 400),  # sabado
        ({"inicio": "2026-10-30T18:00:00-03:00"}, 400),
        ({"provedor": "google"}, 400),  # sem chave
        ({"provedor": "outro"}, 422),
        ({"estrategia": "outra"}, 422),
        ({"quantidade_entregadores": 0}, 422),
    ],
)
def test_criacao_invalida(cliente, dados, codigo):
    resposta = cliente.post(
        "/api/simulacoes",
        json={"cenario_id": cliente.cenario_id, "inicio": INICIO, **dados},
    )

    assert resposta.status_code == codigo
    assert cliente.get("/api/simulacoes").json() == []


# Controle


def test_primeira_etapa_inicia_e_planeja(cliente):
    simulacao_id = criar(cliente)["id"]

    resultado = acao(cliente, simulacao_id, "proxima-etapa")
    estado = resultado["estado"]
    eventos = resultado["eventos"]

    assert eventos[0]["tipo"] == "simulacao_iniciada"
    assert estado["iniciada"]
    # As primeiras viagens saem no proprio instante do inicio.
    por_status = estado["indicadores"]["por_status"]
    assert por_status["atribuido"] + por_status["em_rota"] == 10
    assert por_status["em_rota"] > 0

    posicoes = sorted(p["posicao_fila"] for p in estado["pedidos"])
    assert posicoes == list(range(1, 11))

    for pedido in estado["pedidos"]:
        assert pedido["entregador_codigo"] in {"CAM-01", "CAM-02"}
        assert pedido["previsao_entrega_em"] is not None
        assert pedido["prioridade"] is not None


def test_avancar_por_minutos_e_ate_um_horario(cliente):
    simulacao_id = criar(cliente)["id"]

    estado = acao(cliente, simulacao_id, "avancar", minutos=30)["estado"]
    assert estado["agora"] == "2026-10-30T09:30:00-03:00"
    assert any(e["situacao"] == "em_viagem" for e in estado["entregadores"])

    estado = acao(
        cliente, simulacao_id, "avancar", ate="2026-10-30T10:00:00"
    )["estado"]
    assert estado["agora"] == "2026-10-30T10:00:00-03:00"


@pytest.mark.parametrize(
    "corpo, codigo",
    [
        ({}, 422),
        ({"minutos": 10, "ate": INICIO}, 422),
        ({"minutos": -1}, 422),
        ({"ate": "2026-10-30T08:00:00-03:00"}, 400),
    ],
)
def test_avanco_invalido(cliente, corpo, codigo):
    simulacao_id = criar(cliente)["id"]

    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/avancar", json=corpo
    )

    assert resposta.status_code == codigo


def test_executar_ate_o_fim(cliente):
    simulacao_id = criar(cliente)["id"]

    estado = acao(cliente, simulacao_id, "executar")["estado"]
    indicadores = estado["indicadores"]

    assert estado["concluida"]
    assert estado["proximo_instante"] is None
    assert indicadores["entregues"] == 10
    assert (
        indicadores["entregues_no_prazo"] + indicadores["entregues_atrasados"]
        == 10
    )
    assert indicadores["viagens_concluidas"] == indicadores[
        "viagens_planejadas"
    ]
    assert (
        indicadores["distancia_percorrida_m"]
        == indicadores["distancia_planejada_m"]
    )
    assert all(e["situacao"] == "no_centro" for e in estado["entregadores"])
    assert sum(e["entregas"] for e in estado["entregadores"]) == 10
    assert cliente.get("/api/simulacoes").json()[0]["status"] == "concluida"

    # Uma simulacao concluida nao processa mais nada.
    assert acao(cliente, simulacao_id, "proxima-etapa")["eventos"] == []


def test_viagem_cancelada_pelo_expediente(cliente):
    simulacao_id = criar(cliente, inicio=INICIO_TARDE)["id"]

    # Antes das 17h, a viagem que sairia depois nao tem previsao.
    estado = acao(cliente, simulacao_id, "proxima-etapa")["estado"]
    rotas = cliente.get(f"/api/simulacoes/{simulacao_id}/rotas").json()
    fora_do_expediente = {
        parada["pedido_codigo"]
        for rota in rotas["rotas"]
        for viagem in rota["viagens"]
        if viagem["partida_em"] > "2026-10-30T17:00:00-03:00"
        for parada in viagem["paradas"]
    }
    assert fora_do_expediente
    for pedido in estado["pedidos"]:
        if pedido["codigo"] in fora_do_expediente:
            assert pedido["status"] == "atribuido"
            assert pedido["previsao_entrega_em"] is None

    estado = acao(cliente, simulacao_id, "executar")["estado"]
    indicadores = estado["indicadores"]
    devolvidos = [p for p in estado["pedidos"] if p["status"] == "na_fila"]

    assert indicadores["viagens_canceladas"] == 1
    assert indicadores["devolvidos_a_fila"] == 1
    assert estado["fila"] == [p["codigo"] for p in devolvidos]
    assert devolvidos[0]["entregador_codigo"] is None
    assert devolvidos[0]["previsao_entrega_em"] is None
    assert "expediente" in devolvidos[0]["observacao"]


# Rotas, eventos e auditoria


def test_rotas_para_o_mapa(cliente):
    simulacao_id = criar(cliente)["id"]
    url = f"/api/simulacoes/{simulacao_id}/rotas"

    assert cliente.get(url).status_code == 409

    acao(cliente, simulacao_id, "proxima-etapa")
    rotas = cliente.get(url).json()
    viagens = [v for r in rotas["rotas"] for v in r["viagens"]]

    assert rotas["centro"]["nome"] == "Comercio"
    assert rotas["nao_atribuidos"] == []
    assert sum(len(v["paradas"]) for v in viagens) == 10

    assert {v["situacao"] for v in viagens} == {"planejada", "em_andamento"}

    for viagem in viagens:
        assert len(viagem["caminho"]) >= 2
        assert [p["ordem"] for p in viagem["paradas"]] == list(
            range(1, len(viagem["paradas"]) + 1)
        )

    acao(cliente, simulacao_id, "executar")
    viagens = [v for r in cliente.get(url).json()["rotas"] for v in r["viagens"]]

    assert all(v["situacao"] == "concluida" for v in viagens)
    assert all(
        p["status"] == "entregue" for v in viagens for p in v["paradas"]
    )


def test_eventos_gravados(cliente):
    simulacao_id = criar(cliente)["id"]
    url = f"/api/simulacoes/{simulacao_id}/eventos"

    processados = acao(cliente, simulacao_id, "executar")["eventos"]
    gravados = cliente.get(url).json()

    assert gravados == processados
    assert cliente.get(url, params={"apos": 40}).json() == gravados[40:]


def test_consultas_de_auditoria(cliente):
    simulacao_id = criar(cliente)["id"]
    acao(cliente, simulacao_id, "executar")
    url = f"/api/simulacoes/{simulacao_id}/auditoria"

    atrasos = cliente.get(f"{url}/atrasos").json()
    assert len(atrasos) == 3

    linha = cliente.get(
        f"{url}/linha_do_tempo_pedido", params={"pedido_codigo": "PED-001"}
    ).json()
    assert linha[-1]["status_novo"] == "entregue"

    assert cliente.get(f"{url}/linha_do_tempo_pedido").status_code == 400
    assert cliente.get(f"{url}/nao_existe").status_code == 404


def test_simulacao_fora_da_memoria(cliente):
    simulacao_id = criar(cliente)["id"]
    acao(cliente, simulacao_id, "executar")
    registro.limpar()

    assert cliente.get(f"/api/simulacoes/{simulacao_id}").status_code == 410
    assert (
        cliente.post(f"/api/simulacoes/{simulacao_id}/executar").status_code
        == 410
    )
    assert not cliente.get("/api/simulacoes").json()[0]["ativa"]

    # O historico continua disponivel pela auditoria.
    assert cliente.get(f"/api/simulacoes/{simulacao_id}/eventos").json()
    assert cliente.get(
        f"/api/simulacoes/{simulacao_id}/auditoria/atrasos"
    ).json()


def test_simulacao_inexistente(cliente):
    assert cliente.get("/api/simulacoes/999").status_code == 404
    assert cliente.get("/api/simulacoes/999/eventos").status_code == 404
    assert cliente.post("/api/simulacoes/999/executar").status_code == 404


@pytest.mark.parametrize(
    "erro, codigo",
    [
        (ErroRoteamento("servico indisponivel"), 502),
        (LimiteUsoExcedido("limite diario atingido"), 429),
    ],
)
def test_falha_do_servico_de_mapas(cliente, monkeypatch, erro, codigo):
    simulacao_id = criar(cliente)["id"]
    original = ServicoRoteamentoSimulado.calcular_matriz

    def falhar(*_, **__):
        raise erro

    monkeypatch.setattr(ServicoRoteamentoSimulado, "calcular_matriz", falhar)
    resposta = cliente.post(f"/api/simulacoes/{simulacao_id}/proxima-etapa")

    assert resposta.status_code == codigo
    assert str(erro) in resposta.json()["detail"]

    estado = cliente.get(f"/api/simulacoes/{simulacao_id}").json()
    assert not estado["iniciada"]
    assert all(p["posicao_fila"] is None for p in estado["pedidos"])

    # Depois que o servico volta, a mesma simulacao continua.
    monkeypatch.setattr(ServicoRoteamentoSimulado, "calcular_matriz", original)

    assert acao(cliente, simulacao_id, "proxima-etapa")["estado"]["iniciada"]
