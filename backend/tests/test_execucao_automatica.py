"""Testes do ciclo automatico usando intervalos curtos controlados."""

import asyncio
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.registro import registro
from app.infrastructure import database
from app.infrastructure.execucao_automatica import ExecucaoAutomatica
from app.infrastructure.seed import inicializar_todos_cenarios
from app.main import app


INICIO = "2026-10-30T10:00:00-03:00"


async def aguardar_teste(
    intervalo: float,
    encerramento: asyncio.Event,
) -> bool:
    """Espera pouco em tempo real e pode ser acordado no shutdown."""

    try:
        await asyncio.wait_for(encerramento.wait(), timeout=intervalo)
    except TimeoutError:
        return False

    return True


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "automatico.db")
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "true")
    monkeypatch.setenv("INTERVALO_EXECUCAO_AUTOMATICA_SEGUNDOS", "0.02")
    cenarios = inicializar_todos_cenarios()
    registro.limpar()

    with TestClient(app) as cliente:
        cliente.cenarios = {cenario.codigo: cenario.id for cenario in cenarios}
        cliente.cenario_id = cliente.cenarios["NORMAL"]
        yield cliente
        gerente = cliente.app.state.execucao_automatica

    assert gerente.quantidade_tarefas_ativas == 0
    registro.limpar()


def criar(cliente, velocidade=15):
    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenario_id,
            "inicio": INICIO,
            "provedor": "simulado",
            "segundos_reais_por_hora_simulada": velocidade,
        },
    )
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()


def aguardar(condicao, timeout=2.0):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        valor = condicao()
        if valor:
            return valor
        time.sleep(0.005)
    pytest.fail("A condição esperada não ocorreu dentro do prazo do teste.")


def esperar_estado(cliente, simulacao_id, predicado):
    def consultar():
        estado = cliente.get(f"/api/simulacoes/{simulacao_id}").json()
        return estado if predicado(estado) else None

    return aguardar(consultar)


def test_criacao_inicia_avanco_e_conclusao_automaticos(cliente, monkeypatch):
    gerente = cliente.app.state.execucao_automatica
    monkeypatch.setattr(
        gerente,
        "_avancar_relogio",
        lambda ativa: ativa.simulacao.executar_ate_o_fim(),
    )
    criada = criar(cliente)
    simulacao_id = criada["id"]

    assert criada["estado_execucao"] == "executando"
    assert criada["iniciada"] is False

    final = esperar_estado(cliente, simulacao_id, lambda estado: estado["concluida"])
    assert final["concluida"] is True
    assert final["estado_execucao"] == "concluida"
    assert final["iniciada"] is True
    eventos = cliente.get(f"/api/simulacoes/{simulacao_id}/eventos").json()
    assert len(eventos) > 1
    assert final["indicadores"]["entregues"] > 0


def test_executor_preserva_a_velocidade_escolhida_na_execucao(cliente):
    criada = criar(cliente, velocidade=30)
    ativa = registro.obter(criada["id"])
    assert criada["segundos_reais_por_hora_simulada"] == 30
    assert ativa.segundos_reais_por_hora_simulada == 30


def test_inicio_selecionado_pelo_frontend_inicia_execucao_automatica(
    cliente, monkeypatch
):
    gerente = cliente.app.state.execucao_automatica
    monkeypatch.setattr(
        gerente,
        "_avancar_relogio",
        lambda ativa: ativa.simulacao.executar_ate_o_fim(),
    )
    resposta = cliente.post(
        "/api/simulacoes",
        json={
            "cenario_id": cliente.cenario_id,
            "inicio": "2026-10-30T16:59:00",
            "provedor": "simulado",
            "segundos_reais_por_hora_simulada": 60,
        },
    )
    assert resposta.status_code == 201, resposta.json()
    criada = resposta.json()
    assert criada["inicio"] == "2026-10-30T16:59:00-03:00"
    assert criada["segundos_reais_por_hora_simulada"] == 60
    assert criada["estado_execucao"] == "executando"

    avancada = esperar_estado(
        cliente,
        criada["id"],
        lambda estado: estado["iniciada"] and estado["concluida"],
    )
    assert avancada["inicio"] == criada["inicio"]


@pytest.mark.parametrize(
    ("codigo", "estrategia"),
    [
        ("NORMAL", "insercao_mais_barata"),
        ("ALTA_DEMANDA", "insercao_mais_barata"),
        ("EQUIDADE", "equidade_sla"),
    ],
)
def test_execucao_automatica_avanca_os_tres_cenarios(cliente, codigo, estrategia):
    cliente.cenario_id = cliente.cenarios[codigo]
    criada = criar(cliente)
    gerente = cliente.app.state.execucao_automatica

    estado = esperar_estado(
        cliente,
        criada["id"],
        lambda atual: atual["iniciada"]
        and datetime.fromisoformat(atual["agora"])
        > datetime.fromisoformat(atual["inicio"]),
    )
    assert estado["estrategia"] == estrategia
    assert gerente.intervalo_segundos == 0.02
    assert estado["agora"] > estado["inicio"]


def test_pausa_interrompe_ciclo_e_retomada_continua(cliente):
    criada = criar(cliente)
    simulacao_id = criada["id"]
    ativa = registro.obter(simulacao_id)
    gerente = cliente.app.state.execucao_automatica

    assert gerente.quantidade_tarefas_ativas == 1
    resposta = cliente.post(f"/api/simulacoes/{simulacao_id}/pausar")
    assert resposta.status_code == 200
    estado_pausado = resposta.json()["simulacao"]
    eventos_pausados = cliente.get(
        f"/api/simulacoes/{simulacao_id}/eventos"
    ).json()
    time.sleep(0.08)
    assert ativa.simulacao.agora.isoformat() == estado_pausado["agora"]
    assert cliente.get(f"/api/simulacoes/{simulacao_id}/eventos").json() == eventos_pausados

    retomada = cliente.post(f"/api/simulacoes/{simulacao_id}/retomar")
    assert retomada.status_code == 200
    assert retomada.json()["estado_execucao"] == "executando"
    instante_pausado = datetime.fromisoformat(estado_pausado["agora"])
    aguardar(lambda: ativa.simulacao.agora > instante_pausado)


def test_chamadas_repetidas_nao_criam_executor_duplicado(cliente):
    criada = criar(cliente)
    simulacao_id = criada["id"]
    ativa = registro.obter(simulacao_id)
    gerente = cliente.app.state.execucao_automatica

    cliente.portal.call(gerente.iniciar, simulacao_id, ativa)
    cliente.portal.call(gerente.iniciar, simulacao_id, ativa)
    assert gerente.quantidade_tarefas_ativas == 1


def test_falha_da_etapa_fica_exposta_no_estado(cliente):
    gerente = cliente.app.state.execucao_automatica

    def falhar(_ativa):
        raise RuntimeError("erro controlado no executor")

    gerente._avancar_relogio = falhar
    criada = criar(cliente)
    estado = esperar_estado(
        cliente,
        criada["id"],
        lambda resultado: resultado["estado_execucao"] == "falhou",
    )

    assert estado["erro_execucao"] == "erro controlado no executor"
    assert cliente.post(f"/api/simulacoes/{criada['id']}/retomar").status_code == 409
    assert cliente.post(f"/api/simulacoes/{criada['id']}/executar").status_code == 409