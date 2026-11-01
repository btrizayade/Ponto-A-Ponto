import os

import app.config  # noqa: F401  Carrega o backend/.env.
from app.domain.distribution import CentroDistribuicao
from app.domain.models import Entregador
from app.domain.routing import Coordenada


VARIAVEL_CENTRO_NOME = "CENTRO_DISTRIBUICAO_NOME"
VARIAVEL_CENTRO_LATITUDE = "CENTRO_DISTRIBUICAO_LATITUDE"
VARIAVEL_CENTRO_LONGITUDE = "CENTRO_DISTRIBUICAO_LONGITUDE"
VARIAVEL_QUANTIDADE_ENTREGADORES = "QUANTIDADE_ENTREGADORES"

# Comercio/Nazare: central em relacao aos bairros do cenario NORMAL.
CENTRO_PADRAO = CentroDistribuicao(
    nome="Comercio",
    coordenada=Coordenada(-12.971, -38.501),
)
QUANTIDADE_PADRAO_ENTREGADORES = 2


def obter_centro_distribuicao() -> CentroDistribuicao:
    """Le o centro de distribuicao do ambiente ou usa o padrao."""

    latitude = os.environ.get(VARIAVEL_CENTRO_LATITUDE, "").strip()
    longitude = os.environ.get(VARIAVEL_CENTRO_LONGITUDE, "").strip()

    if not latitude and not longitude:
        return CENTRO_PADRAO

    if not latitude or not longitude:
        raise ValueError(
            f"Defina {VARIAVEL_CENTRO_LATITUDE} e "
            f"{VARIAVEL_CENTRO_LONGITUDE} juntas."
        )

    try:
        coordenada = Coordenada(float(latitude), float(longitude))
    except ValueError as erro:
        raise ValueError(
            "Coordenadas do centro de distribuicao invalidas."
        ) from erro

    nome = os.environ.get(VARIAVEL_CENTRO_NOME, "").strip() or "Centro"

    return CentroDistribuicao(nome=nome, coordenada=coordenada)


def criar_entregadores_padrao(
    quantidade: int | None = None,
) -> list[Entregador]:
    """Cria os caminhoes CAM-01, CAM-02... com capacidade padrao."""

    if quantidade is None:
        valor = os.environ.get(VARIAVEL_QUANTIDADE_ENTREGADORES, "").strip()

        try:
            quantidade = int(valor) if valor else QUANTIDADE_PADRAO_ENTREGADORES
        except ValueError as erro:
            raise ValueError(
                f"A variavel {VARIAVEL_QUANTIDADE_ENTREGADORES} "
                "deve ser inteira."
            ) from erro

    if quantidade < 1:
        raise ValueError("A quantidade de entregadores deve ser positiva.")

    return [
        Entregador(codigo=f"CAM-{numero:02d}")
        for numero in range(1, quantidade + 1)
    ]
