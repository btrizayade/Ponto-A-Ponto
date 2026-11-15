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
from app.infrastructure.auditoria_experimental import (
    ServicoRoteamentoAuditavel,
    montar_parametros_efetivos,
    serializar_snapshot_pedidos,
)
from app.infrastructure.cenario_repository import obter_cenario
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
    intervalo_execucao_automatica_s: float | None = None,
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

    cenario = obter_cenario(cenario_id)
    if cenario is None:
        raise ValueError(f"O cenario {cenario_id} nao existe.")

    servico_efetivo = (
        servico
        if servico is not None
        else criar_servico_roteamento(provedor, fator_transito)
    )
    metadados_roteamento = servico_efetivo.parametros_auditoria()
    provedor_efetivo = str(
        metadados_roteamento.get("provedor")
        if metadados_roteamento.get("provedor") != "desconhecido"
        else (provedor or "desconhecido")
    )
    roteador_auditavel = ServicoRoteamentoAuditavel(
        servico_efetivo,
        provedor_efetivo,
    )
    centro_efetivo = (
        centro if centro is not None else obter_centro_distribuicao()
    )
    entregadores_efetivos = (
        list(entregadores)
        if entregadores is not None
        else criar_entregadores_padrao()
    )
    distribuidor = DistribuidorPedidos(
        roteador_auditavel,
        centro_efetivo,
        entregadores_efetivos,
        estrategia,
    )
    simulacao = Simulacao(pedidos, distribuidor, inicio, disponibilidade)
    if not simulacao.pedidos:
        raise ValueError(
            f"O cenario {cenario_id} nao possui pedidos para a simulacao."
        )

    estrategia_efetiva = distribuidor.estrategia
    parametros = montar_parametros_efetivos(
        inicio=inicio,
        centro=distribuidor.centro,
        entregadores=distribuidor.entregadores,
        estrategia=estrategia_efetiva,
        servico=roteador_auditavel,
        segundos_reais_por_hora_simulada=(
            segundos_reais_por_hora_simulada
        ),
        disponibilidade=disponibilidade,
        intervalo_execucao_automatica_s=(
            intervalo_execucao_automatica_s
        ),
    )
    parametros["cenario"] = {
        "id": cenario.id,
        "codigo": cenario.codigo,
        "nome": cenario.nome,
        "descricao": cenario.descricao,
    }
    snapshot_pedidos = serializar_snapshot_pedidos(
        cenario,
        pedidos,
        inicio,
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
        parametros=parametros,
        snapshot_pedidos=snapshot_pedidos,
    )
    roteador_auditavel.conectar_auditoria(
        auditoria.registrar_consulta_roteamento
    )
    simulacao.definir_observador_planejamento(auditoria)
    simulacao.adicionar_observador(auditoria)

    return simulacao, auditoria
