from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite

from app.domain.models import Bairro, Pedido


class ErroRoteamento(Exception):
    """Falha ao consultar o servico de mapas e transito."""


class RotaNaoEncontrada(ErroRoteamento):
    """Nao existe rota entre os pontos informados."""


@dataclass(frozen=True)
class Coordenada:
    """Ponto geografico usado nas consultas de rota."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        """Valida os limites geograficos da coordenada."""

        for valor in (self.latitude, self.longitude):
            if (
                isinstance(valor, bool)
                or not isinstance(valor, (int, float))
                or not isfinite(valor)
            ):
                raise ValueError(
                    "Latitude e longitude devem ser numeros finitos."
                )

        if not -90 <= self.latitude <= 90:
            raise ValueError("A latitude deve estar entre -90 e 90.")

        if not -180 <= self.longitude <= 180:
            raise ValueError("A longitude deve estar entre -180 e 180.")

    @classmethod
    def do_bairro(cls, bairro: Bairro) -> "Coordenada":
        """Cria a coordenada de referencia de um bairro."""

        return cls(latitude=bairro.latitude, longitude=bairro.longitude)

    @classmethod
    def do_pedido(cls, pedido: Pedido) -> "Coordenada":
        """Cria a coordenada de destino de um pedido."""

        return cls.do_bairro(pedido.bairro)


@dataclass(frozen=True)
class ElementoMatriz:
    """Deslocamento entre uma origem e um destino da matriz."""

    origem_indice: int
    destino_indice: int
    rota_existe: bool
    distancia_m: int = 0
    duracao_s: float = 0.0
    duracao_sem_transito_s: float = 0.0

    @property
    def duracao_min(self) -> float:
        """Duracao considerando o transito, em minutos."""

        return self.duracao_s / 60

    @property
    def fator_transito(self) -> float:
        """Razao entre a duracao com e sem transito."""

        if self.duracao_sem_transito_s <= 0:
            return 1.0

        return self.duracao_s / self.duracao_sem_transito_s


@dataclass
class MatrizDistancias:
    """Matriz de distancias e duracoes entre origens e destinos."""

    origens: list[Coordenada]
    destinos: list[Coordenada]
    elementos: dict[tuple[int, int], ElementoMatriz] = field(
        default_factory=dict
    )

    def obter(self, origem: int, destino: int) -> ElementoMatriz:
        """Retorna o elemento da matriz para o par informado."""

        try:
            return self.elementos[(origem, destino)]
        except KeyError as erro:
            raise KeyError(
                f"Par ({origem}, {destino}) ausente na matriz."
            ) from erro

    def duracao_min(self, origem: int, destino: int) -> float:
        """Duracao com transito entre o par, em minutos."""

        elemento = self._elemento_com_rota(origem, destino)

        return elemento.duracao_min

    def distancia_m(self, origem: int, destino: int) -> int:
        """Distancia percorrida entre o par, em metros."""

        elemento = self._elemento_com_rota(origem, destino)

        return elemento.distancia_m

    def esta_completa(self) -> bool:
        """Indica se exatamente todos os pares esperados estao presentes."""

        esperados = {
            (origem, destino)
            for origem in range(len(self.origens))
            for destino in range(len(self.destinos))
        }

        return set(self.elementos) == esperados

    def _elemento_com_rota(
        self,
        origem: int,
        destino: int,
    ) -> ElementoMatriz:
        """Retorna o elemento ou falha se nao houver rota."""

        elemento = self.obter(origem, destino)

        if not elemento.rota_existe:
            raise RotaNaoEncontrada(
                f"Nao ha rota entre a origem {origem} "
                f"e o destino {destino}."
            )

        return elemento


@dataclass(frozen=True)
class TrechoRota:
    """Trecho entre duas paradas consecutivas de uma rota."""

    distancia_m: int
    duracao_s: float
    duracao_sem_transito_s: float

    @property
    def duracao_min(self) -> float:
        """Duracao do trecho com transito, em minutos."""

        return self.duracao_s / 60


@dataclass
class RotaCalculada:
    """Rota completa com estimativas e geometria do trajeto."""

    distancia_m: int
    duracao_s: float
    duracao_sem_transito_s: float
    polyline_codificada: str
    trechos: list[TrechoRota] = field(default_factory=list)

    @property
    def duracao_min(self) -> float:
        """Duracao total com transito, em minutos."""

        return self.duracao_s / 60

    @property
    def atraso_transito_min(self) -> float:
        """Tempo extra causado pelo transito, em minutos."""

        return max(0.0, self.duracao_s - self.duracao_sem_transito_s) / 60

    @property
    def pontos(self) -> list[Coordenada]:
        """Coordenadas da geometria da rota, para desenho no mapa."""

        from app.domain.polyline import decodificar_polyline

        return decodificar_polyline(self.polyline_codificada)


class ServicoRoteamento(ABC):
    """
    Porta de acesso ao provedor de mapas e transito.

    O dominio depende apenas desta abstracao. Implementacoes
    concretas (Google Routes API ou provedor simulado) ficam
    na camada de infraestrutura.

    Pode ser usada com `with`, que chama fechar() ao final.
    """

    @property
    def perfil_consulta(self) -> str:
        """
        Identifica o provedor e as opcoes que afetam o resultado.

        Usado pelo cache para nao misturar resultados de provedores
        ou preferencias de roteamento diferentes.
        """

        return type(self).__name__

    def fechar(self) -> None:
        """Libera recursos do provedor, como clientes HTTP."""

    def __enter__(self) -> "ServicoRoteamento":
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    @abstractmethod
    def calcular_matriz(
        self,
        origens: Sequence[Coordenada],
        destinos: Sequence[Coordenada],
        partida_em: datetime | None = None,
    ) -> MatrizDistancias:
        """Calcula distancias e duracoes entre origens e destinos."""

    @abstractmethod
    def calcular_rota(
        self,
        origem: Coordenada,
        destino: Coordenada,
        paradas: Sequence[Coordenada] = (),
        partida_em: datetime | None = None,
    ) -> RotaCalculada:
        """Calcula a rota passando pelas paradas na ordem informada."""


def estimar_tempo_entrega_min(
    servico: ServicoRoteamento,
    origem: Coordenada,
    pedido: Pedido,
    partida_em: datetime | None = None,
) -> float:
    """
    Estima o tempo ate a conclusao da entrega de um pedido.

    Soma o deslocamento com transito ate o bairro do pedido e o
    tempo de servico no local. O resultado pode ser usado como
    tempo_estimado_entrega_min no motor de prioridade (F02).
    """

    matriz = servico.calcular_matriz(
        [origem],
        [Coordenada.do_pedido(pedido)],
        partida_em=partida_em,
    )

    return matriz.duracao_min(0, 0) + pedido.tempo_servico_min


def validar_pontos(pontos: Sequence[Coordenada], descricao: str) -> None:
    """Garante que a lista de pontos seja valida para consulta."""

    if not pontos:
        raise ValueError(f"Informe ao menos uma {descricao}.")

    for ponto in pontos:
        if not isinstance(ponto, Coordenada):
            raise TypeError(
                f"Cada {descricao} deve ser uma Coordenada."
            )


def validar_partida(partida_em: datetime | None) -> None:
    """Garante que o horario de partida possua fuso horario."""

    if partida_em is None:
        return

    if not isinstance(partida_em, datetime):
        raise TypeError("O horario de partida deve ser um datetime.")

    if partida_em.tzinfo is None or partida_em.utcoffset() is None:
        raise ValueError(
            "O horario de partida deve possuir fuso horario."
        )
