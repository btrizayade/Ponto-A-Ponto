from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import inf, isfinite

from app.domain.models import Entregador, Pedido
from app.domain.priority_queue import FilaPrioridadeHeap
from app.domain.routing import (
    Coordenada,
    MatrizDistancias,
    RotaCalculada,
    ServicoRoteamento,
    validar_partida,
)


# Pesos da funcao de custo, em minutos equivalentes.
PENALIDADE_ATRASO_MIN = 240.0
PESO_MINUTO_ATRASO = 2.0
PESO_PRIORIDADE = 0.5
PESO_TERMINO = 1.0

MAX_RODADAS_MELHORIA = 50
TOLERANCIA_MELHORIA = 1e-9


@dataclass(frozen=True)
class CentroDistribuicao:
    """Ponto de saida e retorno dos entregadores."""

    nome: str
    coordenada: Coordenada

    def __post_init__(self) -> None:
        if not self.nome.strip():
            raise ValueError(
                "O nome do centro de distribuicao nao pode ser vazio."
            )

        if not isinstance(self.coordenada, Coordenada):
            raise TypeError(
                "O centro de distribuicao deve ter uma Coordenada."
            )


@dataclass
class Parada:
    """Entrega de um pedido dentro de uma viagem."""

    pedido: Pedido
    chegada_em: datetime
    saida_em: datetime

    @property
    def folga_min(self) -> float | None:
        """Minutos entre a chegada e o prazo (negativo se atrasada)."""

        if self.pedido.prazo_entrega_em is None:
            return None

        return (
            self.pedido.prazo_entrega_em - self.chegada_em
        ).total_seconds() / 60

    @property
    def atrasada(self) -> bool:
        """Indica se a chegada ocorre depois do prazo de entrega."""

        folga = self.folga_min

        return folga is not None and folga < 0


@dataclass
class Viagem:
    """Saida do centro, sequencia de paradas e retorno ao centro."""

    numero: int
    partida_em: datetime
    retorno_em: datetime
    distancia_m: int
    paradas: list[Parada]
    rota: RotaCalculada | None = None

    @property
    def pedidos(self) -> list[Pedido]:
        return [parada.pedido for parada in self.paradas]

    @property
    def peso_kg(self) -> float:
        return sum(pedido.peso_kg for pedido in self.pedidos)

    @property
    def volume_l(self) -> float:
        return sum(pedido.volume_l for pedido in self.pedidos)

    @property
    def duracao_min(self) -> float:
        return (self.retorno_em - self.partida_em).total_seconds() / 60


@dataclass
class RotaEntregador:
    """Viagens atribuidas a um entregador, em ordem de execucao."""

    entregador: Entregador
    viagens: list[Viagem] = field(default_factory=list)

    @property
    def pedidos(self) -> list[Pedido]:
        return [p for viagem in self.viagens for p in viagem.pedidos]

    @property
    def distancia_m(self) -> int:
        return sum(viagem.distancia_m for viagem in self.viagens)

    @property
    def termino_em(self) -> datetime | None:
        if not self.viagens:
            return None

        return self.viagens[-1].retorno_em


@dataclass
class PlanoDistribuicao:
    """Resultado da distribuicao dos pedidos entre os entregadores."""

    centro: CentroDistribuicao
    partida_em: datetime
    rotas: list[RotaEntregador]
    nao_atribuidos: list[Pedido] = field(default_factory=list)

    @property
    def paradas(self) -> list[Parada]:
        return [
            parada
            for rota in self.rotas
            for viagem in rota.viagens
            for parada in viagem.paradas
        ]

    @property
    def distancia_total_m(self) -> int:
        return sum(rota.distancia_m for rota in self.rotas)

    @property
    def termino_em(self) -> datetime | None:
        terminos = [r.termino_em for r in self.rotas if r.termino_em]

        return max(terminos) if terminos else None

    @property
    def pedidos_atrasados(self) -> list[Pedido]:
        return [p.pedido for p in self.paradas if p.atrasada]

    def rota_do_pedido(self, codigo: str) -> tuple[Entregador, Viagem]:
        """Localiza o entregador e a viagem que atendem um pedido."""

        for rota in self.rotas:
            for viagem in rota.viagens:
                if any(p.codigo == codigo for p in viagem.pedidos):
                    return rota.entregador, viagem

        raise KeyError(f"Pedido {codigo} nao foi atribuido.")


class MapaDeslocamentos:
    """
    Tempos e distancias entre o centro e os pedidos.

    Usa uma unica matriz da F04. Pedidos no mesmo ponto
    compartilham o mesmo indice da matriz. Quando nao existe rota
    entre dois pontos, a duracao e infinita e o trecho e evitado.
    """

    def __init__(
        self,
        matriz: MatrizDistancias,
        indices: Mapping[str, int],
    ) -> None:
        self._matriz = matriz
        self._indices = dict(indices)

    @classmethod
    def calcular(
        cls,
        servico: ServicoRoteamento,
        centro: CentroDistribuicao,
        pedidos: Sequence[Pedido],
        partida_em: datetime | None = None,
    ) -> "MapaDeslocamentos":
        """Consulta a matriz entre o centro e os pontos dos pedidos."""

        pontos = [centro.coordenada]
        indices = {}

        for pedido in pedidos:
            ponto = Coordenada.do_pedido(pedido)

            if ponto not in pontos:
                pontos.append(ponto)

            indices[pedido.codigo] = pontos.index(ponto)

        matriz = servico.calcular_matriz(
            pontos,
            pontos,
            partida_em=partida_em,
        )

        return cls(matriz, indices)

    def duracao_min(
        self,
        origem: Pedido | None,
        destino: Pedido | None,
    ) -> float:
        """Duracao entre dois pedidos; None representa o centro."""

        elemento = self._matriz.obter(
            self._indice(origem),
            self._indice(destino),
        )

        return elemento.duracao_min if elemento.rota_existe else inf

    def distancia_m(
        self,
        origem: Pedido | None,
        destino: Pedido | None,
    ) -> int:
        """Distancia entre dois pedidos; None representa o centro."""

        return self._matriz.obter(
            self._indice(origem),
            self._indice(destino),
        ).distancia_m

    def _indice(self, pedido: Pedido | None) -> int:
        if pedido is None:
            return 0

        return self._indices[pedido.codigo]


class EstrategiaDistribuicao(ABC):
    """Regra que decide o entregador e a ordem de cada pedido."""

    @abstractmethod
    def distribuir(
        self,
        pedidos: Sequence[Pedido],
        entregadores: Sequence[Entregador],
        centro: CentroDistribuicao,
        mapa: MapaDeslocamentos,
        partida_em: datetime,
        disponibilidade: Mapping[str, datetime] | None = None,
    ) -> PlanoDistribuicao:
        """
        Distribui os pedidos, recebidos em ordem de prioridade.

        disponibilidade informa quando cada entregador (pelo codigo)
        pode sair; sem ela, todos saem em partida_em.
        """


# Cada entregador e representado por uma lista de viagens, e cada
# viagem por uma lista de pedidos na ordem das paradas.
Viagens = list[list[Pedido]]


class _Avaliador:
    """Calcula o custo das viagens de um entregador, em minutos."""

    def __init__(
        self,
        pedidos: Sequence[Pedido],
        mapa: MapaDeslocamentos,
        partida_em: datetime,
    ) -> None:
        total = len(pedidos)
        self._mapa = mapa
        self._peso_prioridade = {
            p.codigo: (total - posicao) / total
            for posicao, p in enumerate(pedidos)
        }
        self._prazo_min = {
            p.codigo: (
                (p.prazo_entrega_em - partida_em).total_seconds() / 60
                if p.prazo_entrega_em is not None
                else inf
            )
            for p in pedidos
        }

    def custo(self, viagens: Viagens, inicio_min: float) -> tuple[float, float]:
        """Retorna o custo e o instante de termino das viagens."""

        if not viagens:
            return 0.0, inicio_min

        instante = inicio_min
        penalidades = 0.0

        for viagem in viagens:
            anterior = None

            for pedido in viagem:
                instante += self._mapa.duracao_min(anterior, pedido)
                atraso = instante - self._prazo_min[pedido.codigo]

                if atraso > 0:
                    penalidades += (
                        PENALIDADE_ATRASO_MIN + PESO_MINUTO_ATRASO * atraso
                    )

                penalidades += (
                    PESO_PRIORIDADE
                    * self._peso_prioridade[pedido.codigo]
                    * instante
                )

                instante += pedido.tempo_servico_min
                anterior = pedido

            instante += self._mapa.duracao_min(anterior, None)

        return (instante - inicio_min) + penalidades, instante


def _cabe_no_entregador(pedido: Pedido, entregador: Entregador) -> bool:
    return (
        pedido.peso_kg <= entregador.capacidade_peso_kg
        and pedido.volume_l <= entregador.capacidade_volume_l
    )


def _cabe_na_viagem(
    pedido: Pedido,
    viagem: list[Pedido],
    entregador: Entregador,
) -> bool:
    return (
        len(viagem) < entregador.max_paradas_por_viagem
        and sum(p.peso_kg for p in viagem) + pedido.peso_kg
        <= entregador.capacidade_peso_kg
        and sum(p.volume_l for p in viagem) + pedido.volume_l
        <= entregador.capacidade_volume_l
    )


def _validar_entrada(
    pedidos: Sequence[Pedido],
    entregadores: Sequence[Entregador],
) -> None:
    if not entregadores:
        raise ValueError("Informe ao menos um entregador.")

    codigos = [e.codigo for e in entregadores]
    if len(set(codigos)) != len(codigos):
        raise ValueError("Os codigos dos entregadores devem ser unicos.")

    codigos = [p.codigo for p in pedidos]
    if len(set(codigos)) != len(codigos):
        raise ValueError("Os codigos dos pedidos devem ser unicos.")


def _inicios_min(
    entregadores: Sequence[Entregador],
    partida_em: datetime,
    disponibilidade: Mapping[str, datetime] | None,
) -> list[float]:
    """Minutos apos a partida em que cada entregador pode sair."""

    disponibilidade = disponibilidade or {}
    inicios = []

    for entregador in entregadores:
        momento = disponibilidade.get(entregador.codigo, partida_em)
        validar_partida(momento)
        inicios.append(
            max(0.0, (momento - partida_em).total_seconds() / 60)
        )

    return inicios


def montar_plano(
    estado: list[Viagens],
    entregadores: Sequence[Entregador],
    centro: CentroDistribuicao,
    mapa: MapaDeslocamentos,
    partida_em: datetime,
    inicios_min: Sequence[float],
    nao_atribuidos: Sequence[Pedido] = (),
) -> PlanoDistribuicao:
    """Converte as viagens em horarios, distancias e paradas."""

    rotas = []

    for entregador, viagens, inicio in zip(entregadores, estado, inicios_min):
        rota = RotaEntregador(entregador=entregador)
        instante = partida_em + timedelta(minutes=inicio)

        for numero, pedidos_viagem in enumerate(viagens, start=1):
            saida = instante
            distancia = 0
            paradas = []
            anterior = None

            for pedido in pedidos_viagem:
                instante += timedelta(
                    minutes=mapa.duracao_min(anterior, pedido)
                )
                distancia += mapa.distancia_m(anterior, pedido)
                chegada = instante
                instante += timedelta(minutes=pedido.tempo_servico_min)
                paradas.append(Parada(pedido, chegada, instante))
                anterior = pedido

            instante += timedelta(minutes=mapa.duracao_min(anterior, None))
            distancia += mapa.distancia_m(anterior, None)

            rota.viagens.append(
                Viagem(
                    numero=numero,
                    partida_em=saida,
                    retorno_em=instante,
                    distancia_m=distancia,
                    paradas=paradas,
                )
            )

        rotas.append(rota)

    return PlanoDistribuicao(
        centro=centro,
        partida_em=partida_em,
        rotas=rotas,
        nao_atribuidos=list(nao_atribuidos),
    )


class DistribuicaoInsercaoMaisBarata(EstrategiaDistribuicao):
    """
    Insere cada pedido onde ele menos aumenta o custo total.

    Os pedidos chegam na ordem da fila de prioridade (F03). Cada um
    e testado em todos os entregadores, viagens e posicoes, e tambem
    em uma nova viagem. Pedidos que nao cabem em nenhum entregador
    ou que nao possuem rota a partir do centro ficam sem atribuicao. O custo soma a duracao das viagens, o termino
    da operacao, penalidades por atraso de SLA e um peso que favorece
    entregar antes os pedidos mais prioritarios. Ao final, uma etapa
    de melhoria realoca pedidos enquanto o custo diminuir.
    """

    def distribuir(
        self,
        pedidos: Sequence[Pedido],
        entregadores: Sequence[Entregador],
        centro: CentroDistribuicao,
        mapa: MapaDeslocamentos,
        partida_em: datetime,
        disponibilidade: Mapping[str, datetime] | None = None,
    ) -> PlanoDistribuicao:
        _validar_entrada(pedidos, entregadores)
        inicios = _inicios_min(entregadores, partida_em, disponibilidade)

        avaliador = _Avaliador(pedidos, mapa, partida_em)
        estado: list[Viagens] = [[] for _ in entregadores]
        nao_atribuidos = []

        for pedido in pedidos:
            melhor = self._melhor_insercao(
                pedido, estado, entregadores, inicios, avaliador
            )

            if melhor is None:
                nao_atribuidos.append(pedido)
                continue

            _, indice, viagens = melhor
            estado[indice] = viagens

        self._melhorar(estado, entregadores, inicios, avaliador)

        return montar_plano(
            estado, entregadores, centro, mapa,
            partida_em, inicios, nao_atribuidos,
        )

    def _melhor_insercao(
        self,
        pedido: Pedido,
        estado: list[Viagens],
        entregadores: Sequence[Entregador],
        inicios: Sequence[float],
        avaliador: _Avaliador,
    ) -> tuple[float, int, Viagens] | None:
        """Retorna (custo global, entregador, viagens) da melhor opcao."""

        avaliacoes = [
            avaliador.custo(viagens, inicio)
            for viagens, inicio in zip(estado, inicios)
        ]
        melhor = None

        for indice, entregador in enumerate(entregadores):
            if not _cabe_no_entregador(pedido, entregador):
                continue

            outros_custos = sum(
                custo for i, (custo, _) in enumerate(avaliacoes)
                if i != indice
            )
            outros_terminos = [
                termino for i, (_, termino) in enumerate(avaliacoes)
                if i != indice
            ]

            for viagens in _candidatos(pedido, estado[indice], entregador):
                custo, termino = avaliador.custo(viagens, inicios[indice])
                total = (
                    outros_custos
                    + custo
                    + PESO_TERMINO * max([termino, *outros_terminos])
                )

                # Trechos sem rota tornam a opcao inviavel.
                if not isfinite(total):
                    continue

                if melhor is None or total < melhor[0]:
                    melhor = (total, indice, viagens)

        return melhor

    def _melhorar(
        self,
        estado: list[Viagens],
        entregadores: Sequence[Entregador],
        inicios: Sequence[float],
        avaliador: _Avaliador,
    ) -> None:
        """Realoca pedidos individualmente enquanto o custo cair."""

        def custo_global() -> float:
            avaliacoes = [
                avaliador.custo(v, i) for v, i in zip(estado, inicios)
            ]
            return sum(c for c, _ in avaliacoes) + PESO_TERMINO * max(
                t for _, t in avaliacoes
            )

        for _ in range(MAX_RODADAS_MELHORIA):
            houve_melhoria = False

            for indice_origem in range(len(estado)):
                for pedido in [
                    p for viagem in estado[indice_origem] for p in viagem
                ]:
                    atual = custo_global()
                    original = estado[indice_origem]
                    estado[indice_origem] = _remover(original, pedido)

                    melhor = self._melhor_insercao(
                        pedido, estado, entregadores, inicios, avaliador
                    )

                    if (
                        melhor is not None
                        and melhor[0] < atual - TOLERANCIA_MELHORIA
                    ):
                        _, indice, viagens = melhor
                        estado[indice] = viagens
                        houve_melhoria = True
                    else:
                        estado[indice_origem] = original

            if not houve_melhoria:
                return


def _candidatos(
    pedido: Pedido,
    viagens: Viagens,
    entregador: Entregador,
) -> list[Viagens]:
    """Todas as formas validas de incluir o pedido nas viagens."""

    candidatos = []

    for indice, viagem in enumerate(viagens):
        if not _cabe_na_viagem(pedido, viagem, entregador):
            continue

        for posicao in range(len(viagem) + 1):
            nova = viagem[:posicao] + [pedido] + viagem[posicao:]
            candidatos.append(viagens[:indice] + [nova] + viagens[indice + 1:])

    candidatos.append([*viagens, [pedido]])

    return candidatos


def _remover(viagens: Viagens, pedido: Pedido) -> Viagens:
    """Remove o pedido e descarta viagens que ficarem vazias."""

    resultado = []

    for viagem in viagens:
        restante = [p for p in viagem if p.codigo != pedido.codigo]

        if restante:
            resultado.append(restante)

    return resultado


class DistribuicaoOrdemDaFila(EstrategiaDistribuicao):
    """
    Distribui alternando os entregadores na ordem da fila.

    Cada entregador entrega exatamente na ordem de prioridade, sem
    otimizar o trajeto. Serve como referencia de comparacao.
    """

    def distribuir(
        self,
        pedidos: Sequence[Pedido],
        entregadores: Sequence[Entregador],
        centro: CentroDistribuicao,
        mapa: MapaDeslocamentos,
        partida_em: datetime,
        disponibilidade: Mapping[str, datetime] | None = None,
    ) -> PlanoDistribuicao:
        _validar_entrada(pedidos, entregadores)
        inicios = _inicios_min(entregadores, partida_em, disponibilidade)

        estado: list[Viagens] = [[] for _ in entregadores]
        nao_atribuidos = []
        proximo = 0

        for pedido in pedidos:
            for tentativa in range(len(entregadores)):
                indice = (proximo + tentativa) % len(entregadores)
                entregador = entregadores[indice]

                if not _cabe_no_entregador(pedido, entregador):
                    continue

                viagens = estado[indice]

                if viagens and _cabe_na_viagem(
                    pedido, viagens[-1], entregador
                ):
                    viagens[-1].append(pedido)
                else:
                    viagens.append([pedido])

                proximo = indice + 1
                break
            else:
                nao_atribuidos.append(pedido)

        return montar_plano(
            estado, entregadores, centro, mapa,
            partida_em, inicios, nao_atribuidos,
        )


class DistribuidorPedidos:
    """
    Planeja a distribuicao dos pedidos e monta as rotas.

    Combina a fila de prioridade (F03), o servico de mapas (F04)
    e uma estrategia de distribuicao.
    """

    def __init__(
        self,
        servico: ServicoRoteamento,
        centro: CentroDistribuicao,
        entregadores: Sequence[Entregador],
        estrategia: EstrategiaDistribuicao | None = None,
    ) -> None:
        if not entregadores:
            raise ValueError("Informe ao menos um entregador.")

        self._servico = servico
        self._centro = centro
        self._entregadores = list(entregadores)
        self._estrategia = estrategia or DistribuicaoInsercaoMaisBarata()

    def planejar(
        self,
        pedidos: Sequence[Pedido],
        partida_em: datetime,
        disponibilidade: Mapping[str, datetime] | None = None,
    ) -> PlanoDistribuicao:
        """Distribui pedidos ja ordenados por prioridade."""

        if partida_em is None:
            raise ValueError("Informe o horario de partida.")

        validar_partida(partida_em)

        if not pedidos:
            return PlanoDistribuicao(
                centro=self._centro,
                partida_em=partida_em,
                rotas=[RotaEntregador(e) for e in self._entregadores],
            )

        mapa = MapaDeslocamentos.calcular(
            self._servico,
            self._centro,
            pedidos,
            partida_em=partida_em,
        )

        return self._estrategia.distribuir(
            pedidos,
            self._entregadores,
            self._centro,
            mapa,
            partida_em,
            disponibilidade,
        )

    def planejar_da_fila(
        self,
        fila: FilaPrioridadeHeap,
        partida_em: datetime,
        disponibilidade: Mapping[str, datetime] | None = None,
    ) -> PlanoDistribuicao:
        """Retira todos os pedidos da fila, em ordem, e os distribui."""

        pedidos = []

        while not fila.esta_vazia():
            pedidos.append(fila.retirar_proximo())

        return self.planejar(pedidos, partida_em, disponibilidade)

    def montar_rotas(self, plano: PlanoDistribuicao) -> None:
        """Calcula a geometria de cada viagem com suas paradas."""

        origem = self._centro.coordenada

        for rota in plano.rotas:
            for viagem in rota.viagens:
                paradas = []

                for pedido in viagem.pedidos:
                    ponto = Coordenada.do_pedido(pedido)

                    # Pedidos seguidos no mesmo ponto viram uma parada.
                    if not paradas or paradas[-1] != ponto:
                        paradas.append(ponto)

                viagem.rota = self._servico.calcular_rota(
                    origem,
                    origem,
                    paradas=paradas,
                    partida_em=viagem.partida_em,
                )
