from collections.abc import Mapping, Sequence
from datetime import datetime

from app.domain.distribution import (
    CentroDistribuicao,
    DistribuidorPedidos,
    EstrategiaDistribuicao,
)
from app.domain.models import Entregador
from app.domain.routing import ServicoRoteamento
from app.domain.simulation import Simulacao
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
) -> tuple[Simulacao, AuditoriaSimulacao]:
    """
    Cria uma simulacao dos pedidos de um cenario, gravada no SQLite.

    Sem parametros opcionais, usa o servico de mapas, o centro e os
    entregadores configurados no ambiente. A execucao e cadastrada
    antes do inicio, e cada evento e gravado assim que ocorre.
    """

    pedidos = listar_pedidos_por_cenario(cenario_id)

    if not pedidos:
        raise ValueError(f"O cenario {cenario_id} nao possui pedidos.")

    distribuidor = DistribuidorPedidos(
        servico if servico is not None else criar_servico_roteamento(),
        centro if centro is not None else obter_centro_distribuicao(),
        (
            entregadores
            if entregadores is not None
            else criar_entregadores_padrao()
        ),
        estrategia,
    )
    simulacao = Simulacao(pedidos, distribuidor, inicio, disponibilidade)
    auditoria = AuditoriaSimulacao.criar(
        inicio=inicio,
        centro=distribuidor.centro,
        entregadores=distribuidor.entregadores,
        estrategia=type(distribuidor.estrategia).__name__,
        cenario_id=cenario_id,
    )
    simulacao.adicionar_observador(auditoria)

    return simulacao, auditoria
