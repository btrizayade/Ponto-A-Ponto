from datetime import datetime, timezone

from app.domain.aging import calcular_pontuacao_aging
from app.domain.models import Pedido
from app.domain.sla_risk import calcular_pontuacao_risco_sla


BONUS_CLIENTE_CLUBE = 5
BONUS_ENTREGA_RAPIDA = 5
BONUS_PRODUTO_PRIORITARIO = 2
BONUS_CLIENTE_COMUM_SLA_LONGO = 1


def calcular_prioridade(
    pedido: Pedido,
    agora: datetime | None = None,
    tempo_estimado_entrega_min: float | None = None,
) -> int:
    """
    Calcula a prioridade combinando urgencia, aging e risco de SLA.

    O risco de SLA e incluido somente quando existe uma estimativa
    de tempo para concluir a entrega.
    """

    if agora is None:
        agora = datetime.now(timezone.utc)

    prioridade = 0

    # Caracteristicas do pedido.
    if pedido.cliente_clube:
        prioridade += BONUS_CLIENTE_CLUBE

    if pedido.entrega_rapida:
        prioridade += BONUS_ENTREGA_RAPIDA

    if pedido.produto_prioritario:
        prioridade += BONUS_PRODUTO_PRIORITARIO

    # Pontuacao inicial baseada no SLA contratado.
    if pedido.sla_dias_uteis == 1:
        prioridade += 5
    elif pedido.sla_dias_uteis <= 3:
        prioridade += 3
    elif pedido.sla_dias_uteis <= 5:
        prioridade += 1

    if (
        not pedido.cliente_clube
        and not pedido.entrega_rapida
        and pedido.sla_dias_uteis >= 5
    ):
        prioridade += BONUS_CLIENTE_COMUM_SLA_LONGO

    # Tempo de espera.
    prioridade += calcular_pontuacao_aging(
        pedido.criado_em,
        agora,
    )

    # Risco de descumprimento do SLA.
    if tempo_estimado_entrega_min is not None:
        prioridade += calcular_pontuacao_risco_sla(
            prazo_entrega_em=pedido.prazo_entrega_em,
            tempo_estimado_entrega_min=tempo_estimado_entrega_min,
            agora=agora,
        )

    return prioridade