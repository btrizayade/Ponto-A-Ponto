from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.api import simulacoes as api_simulacoes
from app.api.registro import registro
from app.infrastructure import database
from app.infrastructure.routing_factory import VARIAVEL_PROVEDOR
from app.infrastructure.seed import inicializar_todos_cenarios
from app.main import app


INICIO = "2026-10-30T10:00:00-03:00"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "pausa.db")
    monkeypatch.delenv(VARIAVEL_PROVEDOR, raising=False)
    monkeypatch.delenv("QUANTIDADE_ENTREGADORES", raising=False)
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    cenarios = inicializar_todos_cenarios()
    registro.limpar()

    with TestClient(app) as cliente:
        cliente.cenario_ids = {
            cenario.codigo: cenario.id for cenario in cenarios
        }
        yield cliente

    registro.limpar()


def criar(cliente, codigo="NORMAL", velocidade=15):
    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenario_ids[codigo],
            "inicio": INICIO,
            "provedor": "simulado",
            "segundos_reais_por_hora_simulada": velocidade,
        },
    )
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()


def avancar(cliente, simulacao_id):
    resposta = cliente.post(
        f"/api/simulacoes/{simulacao_id}/proxima-etapa"
    )
    assert resposta.status_code == 200, resposta.json()
    return resposta.json()


@pytest.mark.parametrize("velocidade", [5, 15, 30, 60])
def test_criacao_pausa_bloqueia_avanco_e_retomada_preserva_estado(
    cliente, velocidade
):
    criada = criar(cliente, "EQUIDADE", velocidade)
    simulacao_id = criada["id"]

    assert criada["estado_execucao"] == "aguardando"
    assert criada["estrategia"] == "equidade_sla"
    assert criada["segundos_reais_por_hora_simulada"] == velocidade
    assert criada["agora"] == INICIO

    iniciada = avancar(cliente, simulacao_id)
    estado_em_execucao = iniciada["estado"]
    ativa = registro.obter(simulacao_id)
    plano = ativa.simulacao.plano
    pedidos_antes = [
        (pedido.codigo, ativa.simulacao.status_do_pedido(pedido.codigo))
        for pedido in ativa.simulacao.pedidos
    ]
    assert estado_em_execucao["estado_execucao"] == "executando"

    pausa = cliente.post(f"/api/simulacoes/{simulacao_id}/pausar")
    assert pausa.status_code == 200, pausa.json()
    dados_pausa = pausa.json()
    estado_pausado = dados_pausa["simulacao"]
    assert dados_pausa["id"] == simulacao_id
    assert dados_pausa["estado_execucao"] == "pausada"
    assert dados_pausa["mensagem"] == "Simulação pausada."
    assert estado_pausado["estado_execucao"] == "pausada"
    assert estado_pausado["agora"] == estado_em_execucao["agora"]

    eventos_antes = cliente.get(
        f"/api/simulacoes/{simulacao_id}/eventos"
    ).json()
    pedidos_pausados = [
        (pedido.codigo, ativa.simulacao.status_do_pedido(pedido.codigo))
        for pedido in ativa.simulacao.pedidos
    ]
    assert pedidos_pausados == pedidos_antes

    for endpoint, corpo in (
        ("proxima-etapa", None),
        ("avancar", {"minutos": 15}),
        ("executar", None),
    ):
        bloqueado = cliente.post(
            f"/api/simulacoes/{simulacao_id}/{endpoint}", json=corpo
        )
        assert bloqueado.status_code == 409

    estado_sem_avanco = cliente.get(
        f"/api/simulacoes/{simulacao_id}"
    ).json()
    eventos_sem_avanco = cliente.get(
        f"/api/simulacoes/{simulacao_id}/eventos"
    ).json()
    assert estado_sem_avanco["agora"] == estado_pausado["agora"]
    assert estado_sem_avanco["indicadores"] == estado_pausado["indicadores"]
    assert eventos_sem_avanco == eventos_antes
    assert ativa.simulacao.plano is plano

    retomada = cliente.post(f"/api/simulacoes/{simulacao_id}/retomar")
    assert retomada.status_code == 200, retomada.json()
    dados_retomada = retomada.json()
    assert dados_retomada["estado_execucao"] == "executando"
    assert dados_retomada["simulacao"]["agora"] == estado_pausado["agora"]
    assert dados_retomada["simulacao"][
        "segundos_reais_por_hora_simulada"
    ] == velocidade
    assert ativa.segundos_reais_por_hora_simulada == velocidade
    assert ativa.simulacao.plano is plano

    proxima = avancar(cliente, simulacao_id)
    assert proxima["estado"]["estado_execucao"] == "executando"
    assert proxima["estado"]["agora"] >= estado_pausado["agora"]
    assert len(
        cliente.get(f"/api/simulacoes/{simulacao_id}/eventos").json()
    ) >= len(eventos_antes)


def test_transicoes_invalidas_e_simulacao_inexistente(cliente):
    for endpoint in ("pausar", "retomar"):
        assert cliente.post(f"/api/simulacoes/999/{endpoint}").status_code == 404

    criada = criar(cliente)
    simulacao_id = criada["id"]
    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/pausar"
    ).status_code == 409
    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/retomar"
    ).status_code == 409

    avancar(cliente, simulacao_id)
    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/retomar"
    ).status_code == 409

    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/pausar"
    ).status_code == 200
    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/pausar"
    ).status_code == 409
    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/retomar"
    ).status_code == 200

    final = cliente.post(f"/api/simulacoes/{simulacao_id}/executar")
    assert final.status_code == 200
    assert final.json()["estado"]["estado_execucao"] == "concluida"
    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/pausar"
    ).status_code == 409
    assert cliente.post(
        f"/api/simulacoes/{simulacao_id}/retomar"
    ).status_code == 409


def test_pausa_concorrente_espera_etapa_em_andamento(cliente, monkeypatch):
    simulacao_id = criar(cliente)["id"]
    avancar(cliente, simulacao_id)
    ativa = registro.obter(simulacao_id)
    original = ativa.simulacao.proxima_etapa
    iniciou_etapa = Event()
    liberar_etapa = Event()

    def etapa_lenta():
        iniciou_etapa.set()
        if not liberar_etapa.wait(timeout=3):
            raise TimeoutError("A etapa de teste não foi liberada.")
        return original()

    monkeypatch.setattr(ativa.simulacao, "proxima_etapa", etapa_lenta)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuro_avanco = executor.submit(
            api_simulacoes.proxima_etapa,
            simulacao_id,
        )
        assert iniciou_etapa.wait(timeout=2)
        futuro_pausa = executor.submit(api_simulacoes.pausar, simulacao_id)

        with pytest.raises(TimeoutError):
            futuro_pausa.result(timeout=0.05)

        liberar_etapa.set()
        futuro_avanco.result(timeout=3)
        resultado_pausa = futuro_pausa.result(timeout=3)

    assert resultado_pausa.estado_execucao.value == "pausada"
    assert ativa.estado_execucao.value == "pausada"
    assert ativa.simulacao.agora > datetime.fromisoformat(INICIO)


@pytest.mark.parametrize(
    ("codigo", "estrategia"),
    [
        ("NORMAL", "insercao_mais_barata"),
        ("ALTA_DEMANDA", "insercao_mais_barata"),
        ("EQUIDADE", "equidade_sla"),
    ],
)
def test_estado_de_execucao_e_pausa_funcionam_nos_tres_cenarios(
    cliente,
    codigo,
    estrategia,
):
    criada = criar(cliente, codigo)
    assert criada["estrategia"] == estrategia
    assert criada["estado_execucao"] == "aguardando"

    avancar(cliente, criada["id"])
    pausa = cliente.post(f"/api/simulacoes/{criada['id']}/pausar")
    assert pausa.status_code == 200
    assert pausa.json()["estado_execucao"] == "pausada"
    assert pausa.json()["simulacao"]["estado_execucao"] == "pausada"
