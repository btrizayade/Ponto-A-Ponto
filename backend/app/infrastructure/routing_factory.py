import os

import app.config  # noqa: F401  Carrega o backend/.env.
from app.domain.routing import ServicoRoteamento
from app.infrastructure.cache_roteamento import ServicoRoteamentoComCache
from app.infrastructure.controle_uso_api import ControleUsoApi
from app.infrastructure.google_routes import (
    VARIAVEL_CHAVE_API,
    ServicoRoteamentoGoogle,
)
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado


VARIAVEL_PROVEDOR = "PROVEDOR_MAPAS"
PROVEDOR_GOOGLE = "google"
PROVEDOR_SIMULADO = "simulado"


PROVEDORES = (PROVEDOR_GOOGLE, PROVEDOR_SIMULADO)


def google_disponivel() -> bool:
    """Indica se a chave da Google Routes API esta configurada."""

    return bool(os.environ.get(VARIAVEL_CHAVE_API, "").strip())


def provedor_padrao() -> str:
    """
    Provedor usado quando nenhum e informado.

    Sem configuracao explicita, usa a Google Routes API quando a
    chave estiver definida e o provedor simulado caso contrario.
    """

    provedor = os.environ.get(VARIAVEL_PROVEDOR, "").strip().lower()

    if provedor:
        return provedor

    return PROVEDOR_GOOGLE if google_disponivel() else PROVEDOR_SIMULADO


def criar_servico_roteamento(
    provedor: str | None = None,
) -> ServicoRoteamento:
    """Cria o servico de roteamento informado ou o padrao do ambiente."""

    provedor = (provedor or "").strip().lower() or provedor_padrao()

    if provedor == PROVEDOR_GOOGLE:
        # Consultas repetidas saem do cache e nao consomem o limite diario.
        return ServicoRoteamentoComCache.do_ambiente(
            ServicoRoteamentoGoogle(
                controle_uso=ControleUsoApi.do_ambiente(),
            )
        )

    if provedor == PROVEDOR_SIMULADO:
        return ServicoRoteamentoSimulado()

    raise ValueError(f"Provedor de mapas desconhecido: {provedor}.")
