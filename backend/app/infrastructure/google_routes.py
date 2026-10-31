import os
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.domain.routing import (
    Coordenada,
    ElementoMatriz,
    ErroRoteamento,
    MatrizDistancias,
    RotaCalculada,
    RotaNaoEncontrada,
    ServicoRoteamento,
    TrechoRota,
    validar_partida,
    validar_pontos,
)
from app.infrastructure.controle_uso_api import (
    TIPO_ELEMENTOS_MATRIZ,
    TIPO_ROTAS,
    ControleUsoApi,
)


URL_COMPUTE_ROUTES = (
    "https://routes.googleapis.com/directions/v2:computeRoutes"
)
URL_COMPUTE_ROUTE_MATRIX = (
    "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
)

VARIAVEL_CHAVE_API = "GOOGLE_MAPS_API_KEY"

CAMPOS_MATRIZ = ",".join(
    [
        "originIndex",
        "destinationIndex",
        "status",
        "condition",
        "distanceMeters",
        "duration",
        "staticDuration",
    ]
)

CAMPOS_ROTA = ",".join(
    [
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
        "routes.polyline.encodedPolyline",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.staticDuration",
    ]
)

PREFERENCIAS_ROTEAMENTO = {
    "TRAFFIC_UNAWARE",
    "TRAFFIC_AWARE",
    "TRAFFIC_AWARE_OPTIMAL",
}

LIMITE_ELEMENTOS_MATRIZ = 625
LIMITE_ELEMENTOS_MATRIZ_OTIMA = 100
LIMITE_PARADAS_INTERMEDIARIAS = 25

# A API rejeita horarios de partida no passado.
MARGEM_PARTIDA_FUTURA = timedelta(seconds=30)


class ServicoRoteamentoGoogle(ServicoRoteamento):
    """
    Adaptador da Google Routes API.

    Usa computeRouteMatrix para a matriz de distancias e
    computeRoutes para obter a geometria do trajeto.
    """

    def __init__(
        self,
        chave_api: str | None = None,
        cliente_http: httpx.Client | None = None,
        preferencia_roteamento: str = "TRAFFIC_AWARE",
        timeout_s: float = 10.0,
        relogio: Callable[[], datetime] | None = None,
        controle_uso: ControleUsoApi | None = None,
    ) -> None:
        chave_api = chave_api or os.environ.get(VARIAVEL_CHAVE_API)

        if not chave_api or not chave_api.strip():
            raise ValueError(
                "Informe a chave da Google Routes API na variavel "
                f"de ambiente {VARIAVEL_CHAVE_API}."
            )

        if preferencia_roteamento not in PREFERENCIAS_ROTEAMENTO:
            raise ValueError(
                "Preferencia de roteamento invalida: "
                f"{preferencia_roteamento}."
            )

        self._chave_api = chave_api.strip()
        self._preferencia = preferencia_roteamento
        self._cliente = cliente_http or httpx.Client(timeout=timeout_s)
        self._cliente_proprio = cliente_http is None
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self._controle_uso = controle_uso

    def fechar(self) -> None:
        """Fecha o cliente HTTP criado pelo proprio servico."""

        if self._cliente_proprio:
            self._cliente.close()

    def __enter__(self) -> "ServicoRoteamentoGoogle":
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    def calcular_matriz(
        self,
        origens: Sequence[Coordenada],
        destinos: Sequence[Coordenada],
        partida_em: datetime | None = None,
    ) -> MatrizDistancias:
        """Consulta a matriz de distancias com transito."""

        validar_pontos(origens, "origem")
        validar_pontos(destinos, "destino")
        validar_partida(partida_em)

        limite = (
            LIMITE_ELEMENTOS_MATRIZ_OTIMA
            if self._preferencia == "TRAFFIC_AWARE_OPTIMAL"
            else LIMITE_ELEMENTOS_MATRIZ
        )
        total = len(origens) * len(destinos)

        if total > limite:
            raise ValueError(
                f"A matriz possui {total} elementos; o limite da "
                f"API e {limite}."
            )

        corpo: dict[str, Any] = {
            "origins": [
                {"waypoint": _montar_waypoint(ponto)}
                for ponto in origens
            ],
            "destinations": [
                {"waypoint": _montar_waypoint(ponto)}
                for ponto in destinos
            ],
            **self._opcoes_deslocamento(partida_em),
        }

        self._reservar_uso(TIPO_ELEMENTOS_MATRIZ, total)
        resposta = self._enviar(URL_COMPUTE_ROUTE_MATRIX, corpo, CAMPOS_MATRIZ)

        if not isinstance(resposta, list):
            raise ErroRoteamento(
                "Resposta inesperada da matriz de distancias."
            )

        matriz = MatrizDistancias(
            origens=list(origens),
            destinos=list(destinos),
        )

        for item in resposta:
            elemento = _converter_elemento_matriz(item)
            matriz.elementos[
                (elemento.origem_indice, elemento.destino_indice)
            ] = elemento

        if not matriz.esta_completa():
            raise ErroRoteamento(
                "A matriz de distancias retornou incompleta."
            )

        return matriz

    def calcular_rota(
        self,
        origem: Coordenada,
        destino: Coordenada,
        paradas: Sequence[Coordenada] = (),
        partida_em: datetime | None = None,
    ) -> RotaCalculada:
        """Consulta a rota e sua geometria passando pelas paradas."""

        validar_pontos([origem, *paradas, destino], "parada")
        validar_partida(partida_em)

        if len(paradas) > LIMITE_PARADAS_INTERMEDIARIAS:
            raise ValueError(
                "A rota aceita no maximo "
                f"{LIMITE_PARADAS_INTERMEDIARIAS} paradas intermediarias."
            )

        corpo: dict[str, Any] = {
            "origin": _montar_waypoint(origem),
            "destination": _montar_waypoint(destino),
            "computeAlternativeRoutes": False,
            "polylineQuality": "HIGH_QUALITY",
            "polylineEncoding": "ENCODED_POLYLINE",
            "languageCode": "pt-BR",
            "units": "METRIC",
            **self._opcoes_deslocamento(partida_em),
        }

        if paradas:
            corpo["intermediates"] = [
                _montar_waypoint(ponto) for ponto in paradas
            ]

        self._reservar_uso(TIPO_ROTAS, 1)
        resposta = self._enviar(URL_COMPUTE_ROUTES, corpo, CAMPOS_ROTA)
        rotas = resposta.get("routes") if isinstance(resposta, dict) else None

        if not rotas:
            raise RotaNaoEncontrada(
                "Nenhuma rota encontrada entre os pontos informados."
            )

        return _converter_rota(rotas[0])

    def _reservar_uso(self, tipo: str, quantidade: int) -> None:
        """Consome o limite diario do backend antes de chamar a API."""

        if self._controle_uso is not None:
            self._controle_uso.reservar(tipo, quantidade)

    def _opcoes_deslocamento(
        self,
        partida_em: datetime | None,
    ) -> dict[str, Any]:
        """Monta modo de viagem, preferencia e horario de partida."""

        opcoes: dict[str, Any] = {
            "travelMode": "DRIVE",
            "routingPreference": self._preferencia,
        }

        # Sem horario futuro, a API considera o momento da consulta.
        if (
            partida_em is not None
            and self._preferencia != "TRAFFIC_UNAWARE"
            and partida_em > self._relogio() + MARGEM_PARTIDA_FUTURA
        ):
            opcoes["departureTime"] = (
                partida_em.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )

        return opcoes

    def _enviar(
        self,
        url: str,
        corpo: dict[str, Any],
        campos: str,
    ) -> Any:
        """Envia a requisicao e converte falhas em ErroRoteamento."""

        cabecalhos = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._chave_api,
            "X-Goog-FieldMask": campos,
        }

        try:
            resposta = self._cliente.post(
                url,
                json=corpo,
                headers=cabecalhos,
            )
        except httpx.HTTPError as erro:
            raise ErroRoteamento(
                "Falha de comunicacao com a Google Routes API."
            ) from erro

        if resposta.is_error:
            raise ErroRoteamento(
                "A Google Routes API retornou o status "
                f"{resposta.status_code}: {_mensagem_erro(resposta)}"
            )

        try:
            return resposta.json()
        except ValueError as erro:
            raise ErroRoteamento(
                "A Google Routes API retornou um JSON invalido."
            ) from erro


def _montar_waypoint(ponto: Coordenada) -> dict[str, Any]:
    """Converte uma coordenada no formato de waypoint da API."""

    return {
        "location": {
            "latLng": {
                "latitude": ponto.latitude,
                "longitude": ponto.longitude,
            }
        }
    }


def converter_duracao_s(valor: str | None) -> float:
    """Converte duracoes no formato '123s' para segundos."""

    if not valor:
        return 0.0

    if not isinstance(valor, str) or not valor.endswith("s"):
        raise ErroRoteamento(f"Duracao em formato invalido: {valor!r}.")

    try:
        return float(valor[:-1])
    except ValueError as erro:
        raise ErroRoteamento(
            f"Duracao em formato invalido: {valor!r}."
        ) from erro


def _converter_elemento_matriz(item: dict[str, Any]) -> ElementoMatriz:
    """Converte um elemento da resposta de computeRouteMatrix."""

    # Campos com valor zero sao omitidos no JSON da API.
    status = item.get("status") or {}
    rota_existe = (
        item.get("condition") == "ROUTE_EXISTS"
        and not status.get("code")
    )
    duracao = converter_duracao_s(item.get("duration"))

    return ElementoMatriz(
        origem_indice=item.get("originIndex", 0),
        destino_indice=item.get("destinationIndex", 0),
        rota_existe=rota_existe,
        distancia_m=item.get("distanceMeters", 0),
        duracao_s=duracao,
        duracao_sem_transito_s=(
            converter_duracao_s(item.get("staticDuration")) or duracao
        ),
    )


def _converter_rota(rota: dict[str, Any]) -> RotaCalculada:
    """Converte a primeira rota da resposta de computeRoutes."""

    duracao = converter_duracao_s(rota.get("duration"))
    trechos = []

    for trecho in rota.get("legs", []):
        duracao_trecho = converter_duracao_s(trecho.get("duration"))
        trechos.append(
            TrechoRota(
                distancia_m=trecho.get("distanceMeters", 0),
                duracao_s=duracao_trecho,
                duracao_sem_transito_s=(
                    converter_duracao_s(trecho.get("staticDuration"))
                    or duracao_trecho
                ),
            )
        )

    return RotaCalculada(
        distancia_m=rota.get("distanceMeters", 0),
        duracao_s=duracao,
        duracao_sem_transito_s=(
            converter_duracao_s(rota.get("staticDuration")) or duracao
        ),
        polyline_codificada=(
            rota.get("polyline", {}).get("encodedPolyline", "")
        ),
        trechos=trechos,
    )


def _mensagem_erro(resposta: httpx.Response) -> str:
    """Extrai a mensagem de erro sem expor dados da requisicao."""

    try:
        dados = resposta.json()
    except ValueError:
        return "resposta sem detalhes."

    if isinstance(dados, list) and dados:
        dados = dados[0]

    if isinstance(dados, dict):
        erro = dados.get("error") or {}
        mensagem = erro.get("message")
        if mensagem:
            return mensagem

    return "resposta sem detalhes."
