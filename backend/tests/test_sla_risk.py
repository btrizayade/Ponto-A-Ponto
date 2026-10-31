from datetime import datetime, timedelta, timezone

import pytest

from app.domain.sla_risk import calcular_pontuacao_risco_sla
from zoneinfo import ZoneInfo

AGORA = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("minutos_restantes", "tempo_estimado", "esperado"),
    [
        (60, 61, 50),
        (60, 60, 50),
        (60, 30, 40),
        (90, 30, 30),
        (150, 30, 20),
        (270, 30, 10),
        (300, 30, 0),
    ],
)
def test_pontuacao_por_folga_do_sla(
    minutos_restantes,
    tempo_estimado,
    esperado,
):
    prazo = AGORA + timedelta(minutes=minutos_restantes)

    resultado = calcular_pontuacao_risco_sla(
        prazo,
        tempo_estimado,
        agora=AGORA,
    )

    assert resultado == esperado


def test_transito_aumenta_risco_de_atraso():
    prazo = AGORA + timedelta(minutes=120)

    tempo_sem_congestionamento = calcular_pontuacao_risco_sla(
        prazo,
        30,
        agora=AGORA,
    )

    tempo_com_congestionamento = calcular_pontuacao_risco_sla(
        prazo,
        100,
        agora=AGORA,
    )

    assert tempo_sem_congestionamento == 20
    assert tempo_com_congestionamento == 40


def test_prazo_vencido_recebe_pontuacao_maxima():
    prazo = AGORA - timedelta(minutes=30)

    resultado = calcular_pontuacao_risco_sla(
        prazo,
        10,
        agora=AGORA,
    )

    assert resultado == 50


def test_rejeita_prazo_sem_fuso_horario():
    prazo = datetime(2026, 10, 30, 15, 0)

    with pytest.raises(ValueError, match="fuso horario"):
        calcular_pontuacao_risco_sla(
            prazo,
            30,
            agora=AGORA,
        )


def test_rejeita_tempo_estimado_negativo():
    prazo = AGORA + timedelta(hours=2)

    with pytest.raises(ValueError, match="tempo estimado"):
        calcular_pontuacao_risco_sla(
            prazo,
            -10,
            agora=AGORA,
        )


def test_rejeita_pedido_sem_prazo():
    with pytest.raises(ValueError, match="prazo de entrega"):
        calcular_pontuacao_risco_sla(
            None,
            30,
            agora=AGORA,
        )


def test_rejeita_data_atual_sem_fuso_horario():
    prazo = AGORA + timedelta(hours=2)
    agora_sem_fuso = datetime(2026, 10, 30, 12, 0)

    with pytest.raises(ValueError, match="fuso horario"):
        calcular_pontuacao_risco_sla(
            prazo,
            30,
            agora=agora_sem_fuso,
        )

def test_risco_considera_somente_horas_operacionais():
    fuso = ZoneInfo("America/Bahia")

    agora = datetime(
        2026, 10, 30, 16, 0, tzinfo=fuso
    )

    prazo = datetime(
        2026, 11, 2, 10, 0, tzinfo=fuso
    )

    resultado = calcular_pontuacao_risco_sla(
        prazo,
        90,
        agora=agora,
    )

    # Disponivel: 120 minutos de expediente.
    # Viagem: 90 minutos.
    # Folga: 30 minutos.
    assert resultado == 40

@pytest.mark.parametrize(
    "tempo_estimado",
    [
        True,
        -1,
        float("inf"),
        float("-inf"),
        float("nan"),
        "30",
    ],
)
def test_rejeita_tempo_estimado_invalido(tempo_estimado):
    prazo = AGORA + timedelta(hours=2)

    with pytest.raises(ValueError, match="tempo estimado"):
        calcular_pontuacao_risco_sla(
            prazo,
            tempo_estimado,
            agora=AGORA,
        )