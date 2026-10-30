from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.priority_queue import FilaPrioridade
from app.domain.priority_scoring import calcular_prioridade
from app.infrastructure import database
from app.infrastructure.cenario_repository import listar_cenarios
from app.infrastructure.pedido_repository import listar_pedidos_por_cenario
from app.infrastructure.seed import (
    inicializar_bairros_cenario_01,
    inicializar_cenario_01,
    inicializar_pedidos_cenario_01,
)


def test_motor_prioridade_classifica_cenario_normal_completo(
    tmp_path,
    monkeypatch,
):
    """Valida a classificacao integrada dos dez pedidos do cenario NORMAL."""

    diretorio = tmp_path / "data"
    caminho_banco = diretorio / "teste.db"

    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", caminho_banco)

    database.inicializar_banco()

    cenario = inicializar_cenario_01()
    bairros = inicializar_bairros_cenario_01()

    inicializar_pedidos_cenario_01(cenario, bairros)

    cenarios = listar_cenarios()
    cenario_recuperado = next(
        item for item in cenarios if item.codigo == "NORMAL"
    )

    pedidos = listar_pedidos_por_cenario(cenario_recuperado.id)

    assert len(pedidos) == 10

    fuso = ZoneInfo("America/Bahia")

    agora = datetime(
        2026, 10, 30, 9, 0, tzinfo=fuso
    )

    tempos_viagem = {
        "PED-001": 25,
        "PED-002": 50,
        "PED-003": 35,
        "PED-004": 40,
        "PED-005": 25,
        "PED-006": 70,
        "PED-007": 45,
        "PED-008": 55,
        "PED-009": 30,
        "PED-010": 60,
    }

    pontuacoes_esperadas = {
        "PED-001": 87,
        "PED-003": 80,
        "PED-004": 77,
        "PED-006": 71,
        "PED-002": 22,
        "PED-007": 18,
        "PED-005": 17,
        "PED-009": 13,
        "PED-010": 8,
        "PED-008": 6,
    }

    fila = FilaPrioridade()
    pontuacoes_obtidas = {}

    for pedido in pedidos:
        tempo_viagem = tempos_viagem[pedido.codigo]

        prioridade = calcular_prioridade(
            pedido,
            agora=agora,
            tempo_estimado_entrega_min=tempo_viagem,
        )

        pontuacoes_obtidas[pedido.codigo] = prioridade

        fila.adicionar_pedido(
            pedido,
            agora=agora,
            tempo_estimado_entrega_min=tempo_viagem,
        )

    assert pontuacoes_obtidas == {
        codigo: pontuacoes_esperadas[codigo]
        for codigo in sorted(pontuacoes_esperadas)
    }

    ordem_obtida = []

    while not fila.esta_vazia():
        pedido = fila.retirar_proximo(agora=agora)
        ordem_obtida.append(pedido.codigo)

    ordem_esperada = [
        "PED-001",
        "PED-003",
        "PED-004",
        "PED-006",
        "PED-002",
        "PED-007",
        "PED-005",
        "PED-009",
        "PED-010",
        "PED-008",
    ]

    assert ordem_obtida == ordem_esperada
    assert len(ordem_obtida) == 10