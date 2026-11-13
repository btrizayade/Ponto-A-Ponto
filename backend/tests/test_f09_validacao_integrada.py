"""Validacao integrada e comparativa dos cenarios F09."""

from datetime import datetime
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.api.registro import registro
from app.domain.routing import Coordenada
from app.infrastructure import database
from app.infrastructure.routing_factory import VARIAVEL_PROVEDOR
from app.infrastructure.seed import inicializar_todos_cenarios
from app.infrastructure.simulated_routing import (
    FATOR_TRANSITO_ALTA_DEMANDA,
    FATOR_TRANSITO_NORMAL,
    ServicoRoteamentoSimulado,
)
from app.main import app


INICIO_COMPARACAO = "2026-10-30T10:00:00-03:00"
ESTRATEGIAS = (
    "insercao_mais_barata",
    "ordem_da_fila",
    "equidade_sla",
)


@pytest.fixture
def cliente_tres_cenarios(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "f09.db")
    monkeypatch.delenv(VARIAVEL_PROVEDOR, raising=False)
    monkeypatch.delenv("QUANTIDADE_ENTREGADORES", raising=False)
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    cenarios = inicializar_todos_cenarios()
    registro.limpar()

    with TestClient(app) as cliente:
        cliente.cenarios_por_codigo = {
            cenario.codigo: cenario.id for cenario in cenarios
        }
        yield cliente

    registro.limpar()


def executar(cliente, cenario_id, **opcoes):
    criada = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario_id,
            "inicio": INICIO_COMPARACAO,
            "provedor": "simulado",
            "quantidade_entregadores": 2,
            **opcoes,
        },
    )
    assert criada.status_code == 201, criada.json()
    resultado = cliente.post(
        f"/api/simulacoes/{criada.json()['id']}/executar"
    )
    assert resultado.status_code == 200, resultado.json()
    return criada.json(), resultado.json()["estado"]


def assert_limites_operacionais(ativa):
    for rota in ativa.simulacao.plano.rotas:
        entregador = rota.entregador
        for viagem in rota.viagens:
            pedidos = [parada.pedido for parada in viagem.paradas]
            assert len(pedidos) <= entregador.max_paradas_por_viagem
            assert sum(p.peso_kg for p in pedidos) <= entregador.capacidade_peso_kg
            assert sum(p.volume_l for p in pedidos) <= entregador.capacidade_volume_l


def test_cadastro_consulta_e_execucao_dos_tres_cenarios(cliente_tres_cenarios):
    cliente = cliente_tres_cenarios
    ids = cliente.cenarios_por_codigo
    lista = cliente.get("/api/cenarios")

    assert lista.status_code == 200
    assert {
        item["codigo"]: item["quantidade_pedidos"]
        for item in lista.json()
    } == {"NORMAL": 10, "ALTA_DEMANDA": 24, "EQUIDADE": 15}

    estrategias = {
        "NORMAL": "insercao_mais_barata",
        "ALTA_DEMANDA": "insercao_mais_barata",
        "EQUIDADE": "equidade_sla",
    }
    ultima_simulacao_id = None
    for codigo, quantidade in (
        ("NORMAL", 10),
        ("ALTA_DEMANDA", 24),
        ("EQUIDADE", 15),
    ):
        pedidos = cliente.get(
            f"/api/cenarios/{ids[codigo]}/pedidos"
        ).json()
        assert len(pedidos) == quantidade

        criada, estado = executar(cliente, ids[codigo])
        assert criada["estrategia"] == estrategias[codigo]
        assert estado["concluida"]
        assert estado["indicadores"]["total_pedidos"] == quantidade
        assert estado["indicadores"]["entregues"] == quantidade
        assert estado["indicadores"]["por_status"]["pendente"] == 0
        assert sum(estado["indicadores"]["por_status"].values()) == quantidade
        assert (
            estado["indicadores"]["distancia_percorrida_m"]
            == estado["indicadores"]["distancia_planejada_m"]
        )
        assert len(estado["indicadores"]["por_bairro"]) == 8
        assert sum(
            bairro["total_pedidos"]
            for bairro in estado["indicadores"]["por_bairro"]
        ) == quantidade
        assert sum(
            bairro["entregues"]
            for bairro in estado["indicadores"]["por_bairro"]
        ) == quantidade
        assert estado["indicadores"]["equidade_territorial"][
            "bairros_com_amostras_validas"
        ] > 0

        ultima_simulacao_id = criada["id"]
        eventos = cliente.get(
            f"/api/simulacoes/{ultima_simulacao_id}/eventos"
        )
        assert eventos.status_code == 200
        entregas_eventos = {
            evento["pedido_codigo"]: evento["instante"]
            for evento in eventos.json()
            if evento["tipo"] == "pedido_entregue"
        }
        assert len(entregas_eventos) == quantidade
        assert all(
            pedido["entregue_em"] == entregas_eventos[pedido["codigo"]]
            for pedido in estado["pedidos"]
        )

        ativa = registro.obter(criada["id"])
        assert_limites_operacionais(ativa)
        servico = ativa.simulacao.distribuidor._servico
        assert isinstance(servico, ServicoRoteamentoSimulado)
        fator_esperado = (
            FATOR_TRANSITO_ALTA_DEMANDA
            if codigo == "ALTA_DEMANDA"
            else FATOR_TRANSITO_NORMAL
        )
        assert servico.perfil_consulta.endswith(
            f":{fator_esperado:.1f}"
            if codigo == "ALTA_DEMANDA"
            else ":horario"
        )
        matriz = servico.calcular_matriz(
            [ativa.simulacao.distribuidor.centro.coordenada],
            [Coordenada.do_pedido(ativa.simulacao.pedidos[0])],
            partida_em=ativa.inicio,
        )
        assert matriz.obter(0, 0).fator_transito == pytest.approx(
            fator_esperado
        )
        trecho = matriz.obter(0, 0)
        assert trecho.duracao_s == pytest.approx(
            trecho.duracao_sem_transito_s * fator_esperado
        )

    # A resposta e os eventos entregues já foram usados pelos experimentos.
    # O estado não é reconstruído depois que a simulação sai da memória.
    registro.limpar()
    assert cliente.get(
        f"/api/simulacoes/{ultima_simulacao_id}"
    ).status_code == 410
    assert cliente.get(
        f"/api/simulacoes/{ultima_simulacao_id}/eventos"
    ).status_code == 200


@pytest.mark.parametrize(
    "inicio",
    [
        "2026-10-29T10:00:00-03:00",
        "2026-10-30T09:00:00-03:00",
        INICIO_COMPARACAO,
        "2026-11-02T16:30:00-03:00",
    ],
)
@pytest.mark.parametrize(
    ("codigo", "quantidade"),
    [("NORMAL", 10), ("ALTA_DEMANDA", 24), ("EQUIDADE", 15)],
)
def test_datas_da_operacao_nao_excluem_pedidos_do_cenario(
    cliente_tres_cenarios,
    inicio,
    codigo,
    quantidade,
):
    cliente = cliente_tres_cenarios
    cenario_id = cliente.cenarios_por_codigo[codigo]
    pedidos_antes = cliente.get(
        f"/api/cenarios/{cenario_id}/pedidos"
    ).json()

    criada = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cenario_id,
            "inicio": inicio,
            "provedor": "simulado",
        },
    )
    assert criada.status_code == 201, criada.json()
    estado_inicial = criada.json()
    assert estado_inicial["indicadores"]["total_pedidos"] == quantidade
    assert len(estado_inicial["pedidos"]) == quantidade

    etapa = cliente.post(
        f"/api/simulacoes/{estado_inicial['id']}/proxima-etapa"
    )
    assert etapa.status_code == 200, etapa.json()
    estado_planejado = etapa.json()["estado"]
    ativa = registro.obter(estado_inicial["id"])
    codigos_planejados = {
        parada.pedido.codigo
        for rota in ativa.simulacao.plano.rotas
        for viagem in rota.viagens
        for parada in viagem.paradas
    }
    codigos_nao_atribuidos = {
        pedido.codigo for pedido in ativa.simulacao.plano.nao_atribuidos
    }

    assert codigos_planejados | codigos_nao_atribuidos == {
        pedido["codigo"] for pedido in pedidos_antes
    }
    assert estado_planejado["indicadores"]["total_pedidos"] == quantidade
    assert sum(estado_planejado["indicadores"]["por_status"].values()) == quantidade
    assert cliente.get(
        f"/api/cenarios/{cenario_id}/pedidos"
    ).json() == pedidos_antes


def _metricas_reais(estado):
    indicadores = estado["indicadores"]
    entregues = [
        pedido for pedido in estado["pedidos"]
        if pedido["entregue_em"] is not None
    ]
    tempos = [
        (
            datetime.fromisoformat(pedido["entregue_em"])
            - datetime.fromisoformat(pedido["criado_em"])
        ).total_seconds() / 60
        for pedido in entregues
    ]
    atrasos = [
        pedido["atraso_min"]
        for pedido in entregues
        if pedido["atraso_min"] is not None and pedido["atraso_min"] > 0
    ]
    territoriais = indicadores["por_bairro"]
    atrasos_bairro = {
        bairro["bairro"]: bairro["atraso_medio_normalizado_sla"]
        for bairro in territoriais
        if bairro["atraso_medio_normalizado_sla"] is not None
    }
    entregadores = [
        {
            "codigo": entregador["codigo"],
            "entregas": entregador["entregas"],
            "entregas_atrasadas": entregador["entregas_atrasadas"],
            "distancia_percorrida_m": entregador["distancia_percorrida_m"],
        }
        for entregador in estado["entregadores"]
    ]
    validos = sum(
        bairro["entregues_com_sla_valido"] for bairro in territoriais
    )

    return {
        "pedidos_entregues": indicadores["entregues"],
        "pedidos_atrasados": indicadores["entregues_atrasados"],
        "cumprimento_sla_pct": (
            100 * indicadores["entregues_no_prazo"] / validos
            if validos else None
        ),
        "tempo_medio_entrega_min": sum(tempos) / len(tempos) if tempos else None,
        "atraso_medio_min": (
            sum(atrasos) / len(atrasos) if atrasos else None
        ),
        "atraso_normalizado_por_bairro": atrasos_bairro,
        "indice_equidade_territorial": indicadores["equidade_territorial"][
            "indice_equidade_territorial_real"
        ],
        "distancia_total_m": indicadores["distancia_percorrida_m"],
        "desempenho_entregadores": entregadores,
    }


def test_comparacao_estrategias_usa_condicoes_identicas_e_resultados_reais(
    tmp_path,
    monkeypatch,
):
    configuracoes = []
    resultados = {}
    fingerprints = set()

    for indice, estrategia in enumerate(ESTRATEGIAS):
        diretorio = tmp_path / f"execucao-{indice}"
        monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
        monkeypatch.setattr(
            database,
            "DATABASE_PATH",
            diretorio / "equidade.db",
        )
        cenarios = inicializar_todos_cenarios()
        cenario_id = next(
            cenario.id for cenario in cenarios
            if cenario.codigo == "EQUIDADE"
        )
        registro.limpar()
        with TestClient(app) as cliente:
            pedidos = cliente.get(
                f"/api/cenarios/{cenario_id}/pedidos"
            ).json()
            fingerprints.add(
                hashlib.sha256(
                    json.dumps(
                        pedidos,
                        sort_keys=True,
                        ensure_ascii=False,
                    ).encode()
                ).hexdigest()
            )
            criada, estado = executar(
                cliente,
                cenario_id,
                estrategia=estrategia,
            )
            assert estado["concluida"]
            assert estado["indicadores"]["entregues"] == 15
            assert sum(e["entregas"] for e in estado["entregadores"]) == 15
            assert_limites_operacionais(registro.obter(criada["id"]))
            resultados[estrategia] = _metricas_reais(estado)
            configuracoes.append(
                (
                    criada["cenario_id"],
                    criada["inicio"],
                    criada["provedor"],
                    criada["estrategia"],
                    len(criada["entregadores"]),
                )
            )
        registro.limpar()

    assert len({item[:3] + item[4:] for item in configuracoes}) == 1
    assert len(fingerprints) == 1
    assert {item[3] for item in configuracoes} == set(ESTRATEGIAS)
    assert set(resultados) == set(ESTRATEGIAS)
    for metricas in resultados.values():
        assert metricas["pedidos_entregues"] == 15
        assert metricas["cumprimento_sla_pct"] is not None
        assert metricas["tempo_medio_entrega_min"] is not None
        assert metricas["atraso_medio_min"] is None
        assert metricas["indice_equidade_territorial"] is not None
        assert metricas["distancia_total_m"] > 0
        assert len(metricas["desempenho_entregadores"]) == 2