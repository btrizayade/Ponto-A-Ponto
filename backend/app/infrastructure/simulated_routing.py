from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from app.domain.polyline import codificar_polyline
from app.domain.routing import (
    Coordenada,
    ElementoMatriz,
    MatrizDistancias,
    RotaCalculada,
    ServicoRoteamento,
    TrechoRota,
    validar_partida,
    validar_pontos,
)


RAIO_TERRA_M = 6_371_000
FUSO_HORARIO = ZoneInfo("America/Bahia")

# A distancia pelas ruas e maior que a distancia em linha reta.
FATOR_SINUOSIDADE = 1.3
VELOCIDADE_MEDIA_KMH = 30.0

FATOR_TRANSITO_PICO = 1.6
FATOR_TRANSITO_NORMAL = 1.15
FATOR_TRANSITO_MADRUGADA = 1.0

HORARIOS_PICO = ((7, 9), (17, 19))


def calcular_distancia_haversine_m(
    origem: Coordenada,
    destino: Coordenada,
) -> float:
    """Distancia em linha reta entre dois pontos, em metros."""

    latitude_1 = radians(origem.latitude)
    latitude_2 = radians(destino.latitude)
    variacao_latitude = latitude_2 - latitude_1
    variacao_longitude = radians(destino.longitude - origem.longitude)

    termo = (
        sin(variacao_latitude / 2) ** 2
        + cos(latitude_1) * cos(latitude_2)
        * sin(variacao_longitude / 2) ** 2
    )

    return 2 * RAIO_TERRA_M * asin(sqrt(termo))


def fator_transito_por_horario(partida_em: datetime) -> float:
    """Fator de transito tipico de Salvador para o horario."""

    hora = partida_em.astimezone(FUSO_HORARIO).hour

    for inicio, fim in HORARIOS_PICO:
        if inicio <= hora < fim:
            return FATOR_TRANSITO_PICO

    if hora < 6 or hora >= 22:
        return FATOR_TRANSITO_MADRUGADA

    return FATOR_TRANSITO_NORMAL


class ServicoRoteamentoSimulado(ServicoRoteamento):
    """
    Provedor de rotas offline e deterministico.

    Usado em testes, no desenvolvimento sem chave de API e em
    cenarios que precisam controlar a intensidade do transito.
    """

    def __init__(
        self,
        velocidade_media_kmh: float = VELOCIDADE_MEDIA_KMH,
        fator_transito: float | None = None,
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        if velocidade_media_kmh <= 0:
            raise ValueError("A velocidade media deve ser positiva.")

        if fator_transito is not None and fator_transito < 1:
            raise ValueError(
                "O fator de transito nao pode ser menor que 1."
            )

        self._velocidade_m_s = velocidade_media_kmh * 1000 / 3600
        self._fator_transito = fator_transito
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))

    def calcular_matriz(
        self,
        origens: Sequence[Coordenada],
        destinos: Sequence[Coordenada],
        partida_em: datetime | None = None,
    ) -> MatrizDistancias:
        """Calcula a matriz usando distancia estimada pelas ruas."""

        validar_pontos(origens, "origem")
        validar_pontos(destinos, "destino")
        validar_partida(partida_em)

        fator = self._obter_fator(partida_em)
        matriz = MatrizDistancias(
            origens=list(origens),
            destinos=list(destinos),
        )

        for i, origem in enumerate(origens):
            for j, destino in enumerate(destinos):
                trecho = self._calcular_trecho(origem, destino, fator)
                matriz.elementos[(i, j)] = ElementoMatriz(
                    origem_indice=i,
                    destino_indice=j,
                    rota_existe=True,
                    distancia_m=trecho.distancia_m,
                    duracao_s=trecho.duracao_s,
                    duracao_sem_transito_s=trecho.duracao_sem_transito_s,
                )

        return matriz

    def calcular_rota(
        self,
        origem: Coordenada,
        destino: Coordenada,
        paradas: Sequence[Coordenada] = (),
        partida_em: datetime | None = None,
    ) -> RotaCalculada:
        """Calcula uma rota em linha reta entre as paradas."""

        pontos = [origem, *paradas, destino]
        validar_pontos(pontos, "parada")
        validar_partida(partida_em)

        fator = self._obter_fator(partida_em)
        trechos = [
            self._calcular_trecho(inicio, fim, fator)
            for inicio, fim in zip(pontos, pontos[1:])
        ]

        return RotaCalculada(
            distancia_m=sum(t.distancia_m for t in trechos),
            duracao_s=sum(t.duracao_s for t in trechos),
            duracao_sem_transito_s=sum(
                t.duracao_sem_transito_s for t in trechos
            ),
            polyline_codificada=codificar_polyline(pontos),
            trechos=trechos,
        )

    def _obter_fator(self, partida_em: datetime | None) -> float:
        """Usa o fator fixo do cenario ou o fator do horario."""

        if self._fator_transito is not None:
            return self._fator_transito

        return fator_transito_por_horario(partida_em or self._relogio())

    def _calcular_trecho(
        self,
        origem: Coordenada,
        destino: Coordenada,
        fator: float,
    ) -> TrechoRota:
        """Estima distancia e duracoes de um trecho."""

        distancia = (
            calcular_distancia_haversine_m(origem, destino)
            * FATOR_SINUOSIDADE
        )
        duracao_sem_transito = distancia / self._velocidade_m_s

        return TrechoRota(
            distancia_m=round(distancia),
            duracao_s=duracao_sem_transito * fator,
            duracao_sem_transito_s=duracao_sem_transito,
        )
