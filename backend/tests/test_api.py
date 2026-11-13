from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.registro import registro
from app.domain.distribution import calcular_indice_equidade_sla
from app.domain.routing import Coordenada, ErroRoteamento
from app.domain.simulation import EstadoExecucao
from app.infrastructure import database
from app.infrastructure.controle_uso_api import LimiteUsoExcedido
from app.infrastructure.google_routes import VARIAVEL_CHAVE_API
from app.infrastructure.routing_factory import VARIAVEL_PROVEDOR
from app.infrastructure.seed import (
    inicializar_bairros_cenario_01,
    inicializar_cenario_01,
    inicializar_cenario_02,
    inicializar_cenario_03,
    inicializar_pedidos_cenario_01,
)
from app.infrastructure.simulated_routing import (
    FATOR_TRANSITO_NORMAL,
    ServicoRoteamentoSimulado,
)
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
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")

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


@pytest.mark.parametrize("velocidade", [5, 15, 30, 60])
def test_velocidades_permitidas_sao_retorna_e_persistidas(cliente, velocidade):
    estado = criar(
        cliente,
        segundos_reais_por_hora_simulada=velocidade,
    )

    assert estado["segundos_reais_por_hora_simulada"] == velocidade
    registrada = cliente.get("/api/simulacoes").json()[0]
    assert registrada["segundos_reais_por_hora_simulada"] == velocidade


@pytest.mark.parametrize("velocidade", [0, 1, 10, 45, 120])
def test_velocidades_nao_permitidas_sao_rejeitadas(cliente, velocidade):
    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenario_id,
            "inicio": INICIO,
            "segundos_reais_por_hora_simulada": velocidade,
        },
    )

    assert resposta.status_code == 422


def test_velocidade_padrao_e_15_e_uma_nova_execucao_nao_altera_a_anterior(
    cliente,
):
    primeira = criar(cliente)
    ativa_primeira = registro.obter(primeira["id"])
    assert primeira["segundos_reais_por_hora_simulada"] == 15

    segunda = criar(cliente, segundos_reais_por_hora_simulada=60)
    ativa_segunda = registro.obter(segunda["id"])

    assert ativa_primeira.segundos_reais_por_hora_simulada == 15
    assert ativa_segunda.segundos_reais_por_hora_simulada == 60
    assert cliente.get("/api/simulacoes").json()[0][
        "segundos_reais_por_hora_simulada"
    ] == 60


def test_migracao_preenche_velocidade_padrao_em_auditoria_legada(cliente):
    with database.conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO simulacoes (
                cenario_id, criada_em, inicio_simulado, centro_nome,
                estrategia, entregadores
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                cliente.cenario_id,
                "2026-11-13T12:00:00+00:00",
                INICIO,
                "Comercio",
                "DistribuicaoInsercaoMaisBarata",
                "CAM-01,CAM-02",
            ),
        )
        conexao.execute(
            "ALTER TABLE simulacoes DROP COLUMN segundos_reais_por_hora_simulada"
        )

    database.inicializar_banco()

    with database.conectar() as conexao:
        velocidade = conexao.execute(
            "SELECT segundos_reais_por_hora_simulada FROM simulacoes"
        ).fetchone()[0]
    assert velocidade == 15


@pytest.mark.parametrize(
    "estado", [EstadoExecucao.EXECUTANDO, EstadoExecucao.PAUSADA]
)
def test_nao_cria_outra_operacao_enquanto_ha_uma_ativa(cliente, estado):
    atual = criar(cliente)
    registro.obter(atual["id"]).estado_execucao = estado

    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenario_id,
            "inicio": INICIO,
            "segundos_reais_por_hora_simulada": 30,
        },
    )

    assert resposta.status_code == 409
    assert "Conclua a operação atual" in resposta.json()["detail"]
    assert len(cliente.get("/api/simulacoes").json()) == 1


def test_nova_execucao_preserva_eventos_da_execucao_concluida(cliente):
    anterior = criar(cliente)
    encerrada = cliente.post(
        f"/api/simulacoes/{anterior['id']}/executar"
    )
    assert encerrada.status_code == 200, encerrada.json()
    eventos_anteriores = cliente.get(
        f"/api/simulacoes/{anterior['id']}/eventos"
    ).json()
    assert eventos_anteriores

    nova = criar(cliente, segundos_reais_por_hora_simulada=30)

    assert nova["id"] != anterior["id"]
    assert cliente.get(
        f"/api/simulacoes/{anterior['id']}/eventos"
    ).json() == eventos_anteriores
    assert {s["id"] for s in cliente.get("/api/simulacoes").json()} == {
        anterior["id"], nova["id"]
    }


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
    assert config["estrategias"] == [
        "insercao_mais_barata",
        "ordem_da_fila",
        "equidade_sla",
    ]
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


def test_indicadores_territoriais_estao_disponiveis_nos_tres_cenarios(
    cliente,
):
    cenarios = [
        (cliente.cenario_id, 10, None),
        (inicializar_cenario_02().id, 24, 3),
        (inicializar_cenario_03().id, 15, 2),
    ]

    for cenario_id, total_esperado, pedidos_por_bairro in cenarios:
        resposta = cliente.post(
            "/api/simulacoes",
            json={
                "cenario_id": cenario_id,
                "inicio": "2026-10-30T10:00:00-03:00",
            },
        )

        assert resposta.status_code == 201, resposta.json()
        indicadores = resposta.json()["indicadores"]
        bairros = indicadores["por_bairro"]

        assert len(bairros) == 8
        assert sum(item["total_pedidos"] for item in bairros) == total_esperado
        assert indicadores["equidade_territorial"][
            "indice_equidade_territorial_real"
        ] is None

        if pedidos_por_bairro is not None:
            if total_esperado == 15:
                assert {item["total_pedidos"] for item in bairros} == {1, 2}
                assert sum(
                    item["total_pedidos"] == 2 for item in bairros
                ) == 7
            else:
                assert {item["total_pedidos"] for item in bairros} == {
                    pedidos_por_bairro
                }


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
    bairros = estado["indicadores"]["por_bairro"]
    assert len(bairros) == 8
    assert sum(b["total_pedidos"] for b in bairros) == 10
    assert sum(b["pendentes"] for b in bairros) == 10
    assert all(b["entregues"] == 0 for b in bairros)
    assert all(b["tempo_medio_entrega_min"] is None for b in bairros)
    assert all(b["percentual_cumprimento_sla"] is None for b in bairros)
    assert estado["indicadores"]["equidade_territorial"][
        "indice_equidade_territorial_real"
    ] is None

    gravadas = cliente.get("/api/simulacoes").json()

    assert gravadas[0]["id"] == estado["id"]
    assert gravadas[0]["ativa"]
    assert gravadas[0]["status"] == "em_andamento"


def test_cenario_alta_demanda_forca_simulado_com_fator_dois(
    cliente, monkeypatch
):
    cenario = inicializar_cenario_02()
    monkeypatch.setenv(VARIAVEL_PROVEDOR, "google")

    resposta = cliente.post(
        "/api/simulacoes",
        json={"cenario_id": cenario.id, "inicio": INICIO},
    )

    assert resposta.status_code == 201, resposta.json()
    estado = resposta.json()
    assert estado["provedor"] == "simulado"

    ativa = registro.obter(estado["id"])
    servico = ativa.simulacao.distribuidor._servico
    assert isinstance(servico, ServicoRoteamentoSimulado)
    assert servico.perfil_consulta.endswith(":2.0")

    matriz = servico.calcular_matriz(
        [ativa.simulacao.distribuidor.centro.coordenada],
        [Coordenada.do_pedido(ativa.simulacao.pedidos[0])],
        partida_em=ativa.inicio,
    )
    trecho = matriz.obter(0, 0)
    assert trecho.fator_transito == pytest.approx(2.0)
    assert trecho.duracao_s == pytest.approx(
        trecho.duracao_sem_transito_s * 2.0
    )


def test_google_explicitamente_solicitado_e_rejeitado_em_alta_demanda(
    cliente,
):
    cenario = inicializar_cenario_02()

    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario.id,
            "inicio": INICIO,
            "provedor": "google",
        },
    )

    assert resposta.status_code == 400
    assert "ALTA_DEMANDA" in resposta.json()["detail"]
    assert "Google Routes" in resposta.json()["detail"]
    assert cliente.get("/api/simulacoes").json() == []


def test_cenarios_normal_e_equidade_mantem_transito_por_horario(cliente):
    for cenario_id in (
        cliente.cenario_id,
        inicializar_cenario_03().id,
    ):
        resposta = cliente.post(
            "/api/simulacoes",
            json={"cenario_id": cenario_id, "inicio": INICIO},
        )

        assert resposta.status_code == 201, resposta.json()
        ativa = registro.obter(resposta.json()["id"])
        servico = ativa.simulacao.distribuidor._servico
        assert isinstance(servico, ServicoRoteamentoSimulado)
        assert servico.perfil_consulta.endswith(":horario")
        matriz = servico.calcular_matriz(
            [ativa.simulacao.distribuidor.centro.coordenada],
            [Coordenada.do_pedido(ativa.simulacao.pedidos[0])],
            partida_em=ativa.inicio,
        )
        assert matriz.obter(0, 0).fator_transito == pytest.approx(
            FATOR_TRANSITO_NORMAL
        )


def test_equidade_seleciona_estrategia_automaticamente(cliente):
    cenario = inicializar_cenario_03()

    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario.id,
            "inicio": "2026-10-30T10:00:00-03:00",
        },
    )

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["estrategia"] == "equidade_sla"
    simulacao_id = resposta.json()["id"]

    inicio = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert inicio.status_code == 200, inicio.json()
    assert inicio.json()["estado"]["iniciada"]
    assert inicio.json()["estado"]["indicadores"]["total_pedidos"] == 15
    assert len(inicio.json()["estado"]["indicadores"]["por_bairro"]) == 8

    assert cliente.get("/api/simulacoes").json()[0]["estrategia"] == (
        "equidade_sla"
    )


def test_equidade_respeita_estrategia_valida_informada(cliente):
    cenario = inicializar_cenario_03()

    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario.id,
            "inicio": INICIO,
            "estrategia": "ordem_da_fila",
        },
    )

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["estrategia"] == "ordem_da_fila"


def test_nova_estrategia_pode_ser_selecionada_explicitamente(cliente):
    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenario_id,
            "inicio": INICIO,
            "estrategia": "equidade_sla",
        },
    )

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["estrategia"] == "equidade_sla"


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


def test_inicio_selecionado_as_1659_e_preservado_no_fuso_de_salvador(cliente):
    estado = criar(cliente, inicio="2026-10-30T16:59:00")

    assert estado["inicio"] == "2026-10-30T16:59:00-03:00"
    assert estado["agora"] == estado["inicio"]


def test_pedido_expoe_separadamente_datas_originais_e_simuladas(cliente):
    origem = cliente.get(
        f"/api/cenarios/{cliente.cenario_id}/pedidos"
    ).json()
    simulacao_id = criar(cliente, inicio=INICIO)["id"]
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert resposta.status_code == 200, resposta.json()

    estado = resposta.json()["estado"]
    por_codigo_origem = {pedido["codigo"]: pedido for pedido in origem}
    por_codigo_simulacao = {pedido["codigo"]: pedido for pedido in estado["pedidos"]}
    pedido = next(iter(por_codigo_simulacao.values()))
    original = por_codigo_origem[pedido["codigo"]]

    assert pedido["criado_em"] == original["criado_em"]
    assert pedido["prazo_entrega_em"] == original["prazo_entrega_em"]
    assert pedido["atualizado_em"] == estado["inicio"]
    assert any(item["previsao_entrega_em"] for item in estado["pedidos"])
    assert all(item["entregue_em"] is None for item in estado["pedidos"])


def test_horario_real_de_entrega_e_ultima_atualizacao_vem_dos_eventos(cliente):
    simulacao_id = criar(cliente, inicio=INICIO)["id"]
    estado = None
    while estado is None or not estado["concluida"]:
        resposta = cliente.post(
            f"/api/simulacoes/{simulacao_id}/proxima-etapa"
        )
        assert resposta.status_code == 200, resposta.json()
        estado = resposta.json()["estado"]

    pedidos_entregues = [
        pedido for pedido in estado["pedidos"]
        if pedido["entregue_em"] is not None
    ]
    assert pedidos_entregues
    assert all(
        pedido["atualizado_em"] == pedido["entregue_em"]
        for pedido in pedidos_entregues
    )


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
        ({"inicio": "2026-10-30T08:59:00-03:00"}, 400),
        ({"inicio": "2026-10-30T17:00:00-03:00"}, 400),
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

    por_bairro = {
        item["bairro"]: item for item in indicadores["por_bairro"]
    }
    assert len(por_bairro) == 8
    pedidos_por_bairro = {}
    amostras_normalizadas = {}

    for pedido in estado["pedidos"]:
        pedidos_por_bairro.setdefault(pedido["bairro"], []).append(pedido)

    for nome, pedidos in pedidos_por_bairro.items():
        item = por_bairro[nome]
        entregues = [p for p in pedidos if p["entregue_em"] is not None]
        com_sla = [
            p for p in entregues
            if p["prazo_entrega_em"] is not None
            and datetime.fromisoformat(p["prazo_entrega_em"])
            > datetime.fromisoformat(p["criado_em"])
        ]
        atrasados = [
            p for p in com_sla
            if datetime.fromisoformat(p["entregue_em"])
            > datetime.fromisoformat(p["prazo_entrega_em"])
        ]
        no_prazo = len(com_sla) - len(atrasados)
        tempos = [
            (
                datetime.fromisoformat(p["entregue_em"])
                - datetime.fromisoformat(p["criado_em"])
            ).total_seconds() / 60
            for p in entregues
        ]

        assert item["total_pedidos"] == len(pedidos)
        assert item["entregues"] == len(entregues)
        assert item["entregues_com_sla_valido"] == len(com_sla)
        assert item["entregues_atrasados"] == len(atrasados)
        assert item["entregues_no_prazo"] == no_prazo
        assert item["tempo_medio_entrega_min"] == pytest.approx(
            round(sum(tempos) / len(tempos), 1)
        )
        assert item["percentual_cumprimento_sla"] == pytest.approx(
            round(100 * no_prazo / len(com_sla), 1)
        )

        amostras_normalizadas[nome] = [
            max(
                0.0,
                (
                    datetime.fromisoformat(p["entregue_em"])
                    - datetime.fromisoformat(p["prazo_entrega_em"])
                ).total_seconds() / 60,
            )
            / (
                datetime.fromisoformat(p["prazo_entrega_em"])
                - datetime.fromisoformat(p["criado_em"])
            ).total_seconds()
            * 60
            for p in com_sla
        ]

    indice_real_esperado = round(
        calcular_indice_equidade_sla(amostras_normalizadas), 4
    )
    assert indicadores["equidade_territorial"][
        "indice_equidade_territorial_real"
    ] == pytest.approx(indice_real_esperado)

    eventos_entrega = {
        evento["pedido_codigo"]: evento["instante"]
        for evento in cliente.get(
            f"/api/simulacoes/{simulacao_id}/eventos"
        ).json()
        if evento["tipo"] == "pedido_entregue"
    }
    assert all(
        pedido["entregue_em"] == eventos_entrega[pedido["codigo"]]
        for pedido in estado["pedidos"]
    )

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
