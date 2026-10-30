
from app.domain.models import Pedido


BONUS_CLIENTE_CLUBE = 5
BONUS_ENTREGA_RAPIDA = 5
BONUS_PRODUTO_PRIORITARIO = 2
BONUS_CLIENTE_COMUM_SLA_LONGO = 1


def calcular_prioridade(pedido: Pedido) -> int:
    """Calcula a pontuacao de prioridade de um pedido."""

    prioridade = 0

    if pedido.cliente_clube:
        prioridade += BONUS_CLIENTE_CLUBE

    if pedido.entrega_rapida:
        prioridade += BONUS_ENTREGA_RAPIDA

    if pedido.produto_prioritario:
        prioridade += BONUS_PRODUTO_PRIORITARIO

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

    return prioridade
