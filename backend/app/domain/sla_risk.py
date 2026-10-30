from datetime import datetime, timezone
from math import isfinite

from app.domain.sla import calcular_minutos_operacionais


PONTOS_SLA_ATRASADO = 50
PONTOS_SLA_ATE_30_MIN = 40
PONTOS_SLA_ATE_1_HORA = 30
PONTOS_SLA_ATE_2_HORAS = 20
PONTOS_SLA_ATE_4_HORAS = 10


def calcular_pontuacao_risco_sla(
    prazo_entrega_em: datetime | None,
    tempo_estimado_entrega_min: float,
    agora: datetime | None = None,
) -> int:
    """
    Calcula a pontuacao de risco de descumprimento do SLA.

    A estimativa de entrega deve considerar o tempo necessario
    ate a conclusao da entrega, incluindo o impacto do transito.
    """

    if prazo_entrega_em is None:
        raise ValueError("O pedido deve possuir prazo de entrega.")

    if not isinstance(prazo_entrega_em, datetime):
        raise TypeError("O prazo de entrega deve ser um datetime.")

    if (
        prazo_entrega_em.tzinfo is None
        or prazo_entrega_em.utcoffset() is None
    ):
        raise ValueError(
            "O prazo de entrega deve possuir fuso horario."
        )

    if (
        isinstance(tempo_estimado_entrega_min, bool)
        or not isinstance(tempo_estimado_entrega_min, (int, float))
        or not isfinite(tempo_estimado_entrega_min)
        or tempo_estimado_entrega_min < 0
    ):
        raise ValueError(
            "O tempo estimado deve ser um numero nao negativo."
        )

    if agora is None:
        agora = datetime.now(timezone.utc)

    if not isinstance(agora, datetime):
        raise TypeError("A data atual deve ser um datetime.")

    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError(
            "A data atual deve possuir fuso horario."
        )

    minutos_disponiveis = calcular_minutos_operacionais(
        agora,
        prazo_entrega_em,
    )

    folga_minutos = (
        minutos_disponiveis - tempo_estimado_entrega_min
    )

    if folga_minutos <= 0:
        return PONTOS_SLA_ATRASADO

    if folga_minutos <= 30:
        return PONTOS_SLA_ATE_30_MIN

    if folga_minutos <= 60:
        return PONTOS_SLA_ATE_1_HORA

    if folga_minutos <= 120:
        return PONTOS_SLA_ATE_2_HORAS

    if folga_minutos <= 240:
        return PONTOS_SLA_ATE_4_HORAS

    return 0