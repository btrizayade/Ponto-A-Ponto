"""
Compara estrategias de distribuicao e centros de distribuicao.

Usa o cenario NORMAL do seed e o provedor de rotas simulado, sem
consumir a Google Routes API. Execute a partir de backend/:

    python -m scripts.analisar_distribuicao
    python -m scripts.analisar_distribuicao --inicio 2026-10-30T09:00 \
        --centro "Porto Seco:-12.905,-38.462" --entregadores 1
"""

import argparse
from datetime import datetime

from app.domain.distribution import (
    CentroDistribuicao,
    DistribuicaoInsercaoMaisBarata,
    DistribuicaoOrdemDaFila,
    DistribuidorPedidos,
    PlanoDistribuicao,
)
from app.domain.models import Bairro, Pedido
from app.domain.priority_queue import FilaPrioridadeHeap
from app.domain.routing import Coordenada
from app.domain.sla import calcular_prazo_entrega
from app.infrastructure.distribution_config import (
    CENTRO_PADRAO,
    criar_entregadores_padrao,
)
from app.infrastructure.seed import (
    BAIRROS_CENARIO_01,
    FUSO_HORARIO,
    PEDIDOS_CENARIO_01,
)
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


ESTRATEGIAS = {
    "Insercao mais barata": DistribuicaoInsercaoMaisBarata,
    "Ordem da fila": DistribuicaoOrdemDaFila,
}


def carregar_pedidos() -> list[Pedido]:
    """Monta os pedidos do cenario NORMAL sem acessar o banco."""

    bairros = {
        nome: Bairro(nome, latitude, longitude)
        for nome, latitude, longitude in BAIRROS_CENARIO_01
    }
    pedidos = []

    for (
        codigo, bairro, categoria, clube, rapida,
        sla, peso, volume, servico, criado_em,
    ) in PEDIDOS_CENARIO_01:
        pedidos.append(
            Pedido(
                codigo=codigo,
                bairro=bairros[bairro],
                categoria_produto=categoria,
                cliente_clube=clube,
                entrega_rapida=rapida,
                sla_dias_uteis=sla,
                peso_kg=peso,
                volume_l=volume,
                tempo_servico_min=servico,
                criado_em=criado_em,
                prazo_entrega_em=calcular_prazo_entrega(criado_em, sla),
            )
        )

    return pedidos


def ordenar_por_prioridade(
    pedidos: list[Pedido],
    agora: datetime,
) -> list[Pedido]:
    """Usa a fila da F03 para obter a ordem de prioridade."""

    fila = FilaPrioridadeHeap()

    for pedido in pedidos:
        fila.adicionar_pedido(pedido, agora=agora)

    return [fila.retirar_proximo() for _ in range(len(fila))]


def resumir(plano: PlanoDistribuicao, ordem: list[Pedido]) -> str:
    chegadas = {p.pedido.codigo: p.chegada_em for p in plano.paradas}
    top3 = max(chegadas[p.codigo] for p in ordem[:3]) - plano.partida_em
    atrasados = ", ".join(p.codigo for p in plano.pedidos_atrasados) or "-"
    cargas = "/".join(str(len(r.pedidos)) for r in plano.rotas)
    viagens = "/".join(str(len(r.viagens)) for r in plano.rotas)

    return (
        f"{plano.distancia_total_m / 1000:6.1f} km | "
        f"termino {plano.termino_em:%H:%M} | "
        f"3 mais prioritarios em {top3.total_seconds() / 60:4.0f} min | "
        f"pedidos {cargas} | viagens {viagens} | atrasados: {atrasados}"
    )


def ler_centro(valor: str) -> CentroDistribuicao:
    nome, coordenadas = valor.split(":")
    latitude, longitude = (float(v) for v in coordenadas.split(","))

    return CentroDistribuicao(nome, Coordenada(latitude, longitude))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--inicio",
        default="2026-10-30T09:00",
        help="Inicio da operacao, no horario de Salvador.",
    )
    parser.add_argument(
        "--centro",
        action="append",
        type=ler_centro,
        help='Centro no formato "Nome:lat,lng". Pode repetir.',
    )
    parser.add_argument("--entregadores", type=int, default=2)
    parser.add_argument(
        "--transito",
        type=float,
        default=None,
        help="Fator de transito fixo (padrao: pelo horario).",
    )
    argumentos = parser.parse_args()

    inicio = datetime.fromisoformat(argumentos.inicio).replace(
        tzinfo=FUSO_HORARIO
    )
    centros = argumentos.centro or [
        CENTRO_PADRAO,
        ler_centro("Porto Seco Piraja:-12.905,-38.462"),
    ]
    servico = ServicoRoteamentoSimulado(fator_transito=argumentos.transito)
    entregadores = criar_entregadores_padrao(argumentos.entregadores)
    ordem = ordenar_por_prioridade(carregar_pedidos(), inicio)

    print(f"Inicio: {inicio:%d/%m %H:%M} | entregadores: {len(entregadores)}")
    print("Ordem da fila:", ", ".join(
        f"{p.codigo} ({p.bairro.nome})" for p in ordem
    ))

    for centro in centros:
        print(f"\nCentro: {centro.nome}")

        for nome, estrategia in ESTRATEGIAS.items():
            distribuidor = DistribuidorPedidos(
                servico, centro, entregadores, estrategia()
            )
            plano = distribuidor.planejar(ordem, inicio)
            print(f"  {nome:22s} {resumir(plano, ordem)}")


if __name__ == "__main__":
    main()
