from collections.abc import Mapping, Sequence
from datetime import datetime

from app.domain.distribution import (
    CentroDistribuicao,
    DistribuidorPedidos,
    EstrategiaDistribuicao,
)
from app.domain.models import Entregador, OrigemPedido
from app.domain.routing import ServicoRoteamento
from app.domain.simulation import (
    SEGUNDOS_REAIS_POR_HORA_SIMULADA,
    Simulacao,
)
from app.infrastructure.auditoria_repository import AuditoriaSimulacao
from app.infrastructure.distribution_config import (
    criar_entregadores_padrao,
    obter_centro_distribuicao,
)
from app.infrastructure.pedido_repository import listar_pedidos_por_cenario
from app.infrastructure.routing_factory import criar_servico_roteamento


def criar_simulacao_auditada(
    cenario_id: int,
    inicio: datetime,
    servico: ServicoRoteamento | None = None,
    centro: CentroDistribuicao | None = None,
    entregadores: Sequence[Entregador] | None = None,
    estrategia: EstrategiaDistribuicao | None = None,
    disponibilidade: Mapping[str, datetime] | None = None,
    provedor: str | None = None,
    fator_transito: float | None = None,
    segundos_reais_por_hora_simulada: int = int(
        SEGUNDOS_REAIS_POR_HORA_SIMULADA
    ),
) -> tuple[Simulacao, AuditoriaSimulacao]:
    """
    Cria uma simulacao dos pedidos de um cenario, gravada no SQLite.

    Sem parametros opcionais, usa o servico de mapas, o centro e os
    entregadores configurados no ambiente. `provedor` e
    `fator_transito` configuram a criacao do servico quando ele nao e
    injetado. A execucao e cadastrada antes do inicio, e cada evento
    e gravado assim que ocorre.
    """

    pedidos = listar_pedidos_por_cenario(cenario_id)

    if not pedidos:
        raise ValueError(f"O cenario {cenario_id} nao possui pedidos.")

    distribuidor = DistribuidorPedidos(
        (
            servico
            if servico is not None
            else criar_servico_roteamento(provedor, fator_transito)
        ),
        centro if centro is not None else obter_centro_distribuicao(),
        (
            entregadores
            if entregadores is not None
            else criar_entregadores_padrao()
        ),
        estrategia,
    )
    simulacao = Simulacao(pedidos, distribuidor, inicio, disponibilidade)
    if not simulacao.pedidos:
        raise ValueError(
            f"O cenario {cenario_id} nao possui pedidos para a simulacao."
        )
    auditoria = AuditoriaSimulacao.criar(
        inicio=inicio,
        centro=distribuidor.centro,
        entregadores=distribuidor.entregadores,
        estrategia=type(distribuidor.estrategia).__name__,
        cenario_id=cenario_id,
        limite_pedido_manual_id=max(
            (
                pedido.id
                for pedido in pedidos
                if pedido.origem == OrigemPedido.MANUAL
                and pedido.id is not None
            ),
            default=None,
        ),
        segundos_reais_por_hora_simulada=segundos_reais_por_hora_simulada,
    )
    simulacao.adicionar_observador(auditoria)

    return simulacao, auditoria
