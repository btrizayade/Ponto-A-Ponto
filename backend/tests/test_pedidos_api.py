from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.registro import registro
from app.infrastructure import database
from app.infrastructure.bairro_repository import listar_bairros
from app.infrastructure.cenario_repository import listar_cenarios
from app.infrastructure.pedido_repository import listar_pedidos_por_cenario
from app.domain.models import OrigemPedido
from app.infrastructure.seed import inicializar_todos_cenarios
from app.main import app


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "pedidos.db")
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    cenarios = inicializar_todos_cenarios()
    registro.limpar()

    with TestClient(app) as test_client:
        test_client.cenarios = {cenario.codigo: cenario.id for cenario in cenarios}
        test_client.bairros = {bairro.id: bairro for bairro in listar_bairros()}
        yield test_client

    registro.limpar()


def payload(cliente, *, cenario="NORMAL", bairro=None, categoria="alimento", modalidade="entrega_rapida"):
    return {
        "cenario_id": cliente.cenarios[cenario],
        "bairro_id": bairro or next(iter(cliente.bairros)),
        "categoria_produto": categoria,
        "modalidade": modalidade,
    }


def test_lista_bairros_usa_ids_e_cadastros_existentes(cliente):
    resposta = cliente.get("/api/bairros")

    assert resposta.status_code == 200
    bairros = resposta.json()
    assert len(bairros) == 8
    assert {bairro["id"] for bairro in bairros} == set(cliente.bairros)
    assert {bairro["nome"] for bairro in bairros} == {
        "Comercio",
        "Barra",
        "Brotas",
        "Pituba",
        "Rio Vermelho",
        "Itapua",
        "Boca do Rio",
        "Pernambues",
    }

    configuracao = cliente.get("/api/configuracao").json()
    assert configuracao["categorias_produto"] == [
        "alimento",
        "medicamento",
        "roupa",
        "eletronico",
        "outro",
    ]
    assert configuracao["modalidades_entrega"] == [
        "entrega_rapida",
        "clube",
        "convencional",
    ]


def test_pedido_e_persistido_somente_no_cenario_escolhido(cliente):
    antes = {c.codigo: len(listar_pedidos_por_cenario(c.id)) for c in listar_cenarios()}
    escolhido = payload(cliente, cenario="EQUIDADE", modalidade="clube")
    resposta = cliente.post("/api/pedidos", json=escolhido)

    assert resposta.status_code == 201, resposta.json()
    pedido = resposta.json()
    assert pedido["id"] > 0
    assert pedido["codigo"].startswith("PED-MAN-")
    assert pedido["bairro"] == cliente.bairros[escolhido["bairro_id"]].nome
    assert pedido["categoria_produto"] == "alimento"
    assert pedido["cliente_clube"] is True
    assert pedido["entrega_rapida"] is False
    assert pedido["sla_dias_uteis"] == 3
    assert pedido["prazo_entrega_em"] is not None
    assert pedido["criado_em"] is not None
    assert pedido["peso_kg"] == 2.5
    assert pedido["volume_l"] == 5.0
    assert pedido["tempo_servico_min"] == 8
    assert pedido["prioridade_inicial"] > 0

    depois = {c.codigo: len(listar_pedidos_por_cenario(c.id)) for c in listar_cenarios()}
    assert depois == {"NORMAL": antes["NORMAL"], "ALTA_DEMANDA": antes["ALTA_DEMANDA"], "EQUIDADE": antes["EQUIDADE"] + 1}
    assert len(listar_pedidos_por_cenario(cliente.cenarios["EQUIDADE"])) == 16
    criado_persistido = next(
        item
        for item in listar_pedidos_por_cenario(
            cliente.cenarios["EQUIDADE"]
        )
        if item.id == pedido["id"]
    )
    assert criado_persistido.origem == OrigemPedido.MANUAL


@pytest.mark.parametrize(
    ("categoria", "peso", "volume", "servico"),
    [
        ("alimento", 2.5, 5.0, 8),
        ("medicamento", 1.2, 2.0, 7),
        ("roupa", 1.0, 4.0, 5),
        ("eletronico", 3.0, 8.0, 10),
        ("outro", 0.5, 1.0, 5),
    ],
)
def test_categoria_define_perfil_operacional_do_backend(
    cliente,
    categoria,
    peso,
    volume,
    servico,
):
    resposta = cliente.post(
        "/api/pedidos",
        json=payload(cliente, categoria=categoria),
    )

    assert resposta.status_code == 201
    pedido = resposta.json()
    assert (pedido["peso_kg"], pedido["volume_l"], pedido["tempo_servico_min"]) == (
        peso,
        volume,
        servico,
    )
    assert datetime.fromisoformat(pedido["prazo_entrega_em"]) > datetime.fromisoformat(
        pedido["criado_em"]
    )


@pytest.mark.parametrize(
    ("modalidade", "clube", "rapida", "sla"),
    [
        ("entrega_rapida", False, True, 1),
        ("clube", True, False, 3),
        ("convencional", False, False, 5),
    ],
)
def test_modalidade_define_flags_e_sla(
    cliente,
    modalidade,
    clube,
    rapida,
    sla,
):
    resposta = cliente.post(
        "/api/pedidos",
        json=payload(cliente, modalidade=modalidade),
    )

    assert resposta.status_code == 201
    pedido = resposta.json()
    assert pedido["cliente_clube"] is clube
    assert pedido["entrega_rapida"] is rapida
    assert pedido["sla_dias_uteis"] == sla

    persistido = next(
        pedido_salvo
        for pedido_salvo in listar_pedidos_por_cenario(
            cliente.cenarios["NORMAL"]
        )
        if pedido_salvo.id == pedido["id"]
    )
    assert persistido.cliente_clube is clube
    assert persistido.entrega_rapida is rapida
    assert persistido.sla_dias_uteis == sla


def test_cenario_bairro_categoria_e_modalidade_invalidos_sao_rejeitados(cliente):
    invalido = payload(cliente)
    invalido["cenario_id"] = 9999
    assert cliente.post("/api/pedidos", json=invalido).status_code == 404

    invalido = payload(cliente)
    invalido["bairro_id"] = 9999
    assert cliente.post("/api/pedidos", json=invalido).status_code == 404

    invalido = payload(cliente)
    invalido["categoria_produto"] = "brinquedo"
    assert cliente.post("/api/pedidos", json=invalido).status_code == 422

    invalido = payload(cliente)
    invalido["modalidade"] = "normal"
    assert cliente.post("/api/pedidos", json=invalido).status_code == 422


def test_pedido_cadastrado_antes_da_simulacao_entra_na_massa_inicial(
    cliente,
    monkeypatch,
):
    horario_inicial = datetime.fromisoformat("2026-10-30T10:00:00-03:00")

    class RelogioCongelado(datetime):
        @classmethod
        def now(cls, tz=None):
            return horario_inicial.astimezone(tz)

    monkeypatch.setattr("app.infrastructure.pedido_factory.datetime", RelogioCongelado)
    cadastro = cliente.post(
        "/api/pedidos",
        json=payload(cliente, categoria="medicamento"),
    )
    assert cadastro.status_code == 201, cadastro.json()
    codigo = cadastro.json()["codigo"]

    simulacao = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenarios["NORMAL"],
            "inicio": horario_inicial.isoformat(),
            "provedor": "simulado",
        },
    )

    assert simulacao.status_code == 201, simulacao.json()
    assert codigo in {pedido["codigo"] for pedido in simulacao.json()["pedidos"]}


def test_pedido_criado_depois_do_snapshot_fica_para_proxima_simulacao(
    cliente,
    monkeypatch,
):
    horario_inicial = datetime.fromisoformat("2026-10-30T10:00:00-03:00")

    class RelogioCongelado(datetime):
        @classmethod
        def now(cls, tz=None):
            return horario_inicial.astimezone(tz)

    monkeypatch.setattr("app.infrastructure.pedido_factory.datetime", RelogioCongelado)
    simulacao = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenarios["NORMAL"],
            "inicio": horario_inicial.isoformat(),
            "provedor": "simulado",
        },
    )
    assert simulacao.status_code == 201, simulacao.json()

    cadastro = cliente.post(
        "/api/pedidos",
        json=payload(cliente, categoria="roupa"),
    )
    assert cadastro.status_code == 201, cadastro.json()
    codigo = cadastro.json()["codigo"]

    estado_ativo = cliente.get(
        f"/api/simulacoes/{simulacao.json()['id']}"
    ).json()
    pedidos_cenario = cliente.get(
        f"/api/cenarios/{cliente.cenarios['NORMAL']}/pedidos"
    ).json()

    assert codigo not in {pedido["codigo"] for pedido in estado_ativo["pedidos"]}
    assert codigo in {pedido["codigo"] for pedido in pedidos_cenario}
