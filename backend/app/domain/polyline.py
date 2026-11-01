from app.domain.routing import Coordenada


PRECISAO_PADRAO = 5


def codificar_polyline(
    pontos: list[Coordenada],
    precisao: int = PRECISAO_PADRAO,
) -> str:
    """
    Codifica uma lista de coordenadas no formato Encoded Polyline.

    E o mesmo formato devolvido pela Google Routes API e aceito
    pelas bibliotecas de mapa do frontend.
    """

    fator = 10 ** precisao
    resultado = []
    latitude_anterior = 0
    longitude_anterior = 0

    for ponto in pontos:
        latitude = round(ponto.latitude * fator)
        longitude = round(ponto.longitude * fator)

        resultado.append(_codificar_valor(latitude - latitude_anterior))
        resultado.append(_codificar_valor(longitude - longitude_anterior))

        latitude_anterior = latitude
        longitude_anterior = longitude

    return "".join(resultado)


def decodificar_polyline(
    polyline: str,
    precisao: int = PRECISAO_PADRAO,
) -> list[Coordenada]:
    """Converte uma Encoded Polyline em uma lista de coordenadas."""

    fator = 10 ** precisao
    pontos = []
    indice = 0
    latitude = 0
    longitude = 0

    while indice < len(polyline):
        variacao_latitude, indice = _decodificar_valor(polyline, indice)
        variacao_longitude, indice = _decodificar_valor(polyline, indice)

        latitude += variacao_latitude
        longitude += variacao_longitude

        pontos.append(
            Coordenada(
                latitude=latitude / fator,
                longitude=longitude / fator,
            )
        )

    return pontos


def _codificar_valor(valor: int) -> str:
    """Codifica um inteiro com sinal em blocos de 5 bits."""

    valor = ~(valor << 1) if valor < 0 else valor << 1
    caracteres = []

    while valor >= 0x20:
        caracteres.append(chr((0x20 | (valor & 0x1F)) + 63))
        valor >>= 5

    caracteres.append(chr(valor + 63))

    return "".join(caracteres)


def _decodificar_valor(polyline: str, indice: int) -> tuple[int, int]:
    """Le um inteiro codificado a partir da posicao informada."""

    resultado = 0
    deslocamento = 0

    while True:
        if indice >= len(polyline):
            raise ValueError("Polyline codificada invalida.")

        bloco = ord(polyline[indice]) - 63
        indice += 1

        if bloco < 0:
            raise ValueError("Polyline codificada invalida.")

        resultado |= (bloco & 0x1F) << deslocamento
        deslocamento += 5

        if bloco < 0x20:
            break

    valor = ~(resultado >> 1) if resultado & 1 else resultado >> 1

    return valor, indice
