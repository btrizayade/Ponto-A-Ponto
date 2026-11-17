"""Calendario temporal oficial dos cenarios de simulacao."""

from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType

from app.domain.sla import FUSO_HORARIO


VERSAO_CONFIGURACAO_TEMPORAL_CENARIO = 1


@dataclass(frozen=True)
class ConfiguracaoTemporalCenario:
    codigo_cenario: str
    data_inicial_janela: date
    data_final_janela: date
    inicio_simulacao: datetime
    fuso_horario: str


CONFIGURACOES_TEMPORAIS_CENARIOS = MappingProxyType(
    {
        "NORMAL": ConfiguracaoTemporalCenario(
            codigo_cenario="NORMAL",
            data_inicial_janela=date(2026, 10, 5),
            data_final_janela=date(2026, 10, 7),
            inicio_simulacao=datetime(
                2026, 10, 7, 9, 0, tzinfo=FUSO_HORARIO
            ),
            fuso_horario="America/Bahia",
        ),
        "EQUIDADE": ConfiguracaoTemporalCenario(
            codigo_cenario="EQUIDADE",
            data_inicial_janela=date(2026, 10, 12),
            data_final_janela=date(2026, 10, 16),
            inicio_simulacao=datetime(
                2026, 10, 16, 9, 0, tzinfo=FUSO_HORARIO
            ),
            fuso_horario="America/Bahia",
        ),
        "ALTA_DEMANDA": ConfiguracaoTemporalCenario(
            codigo_cenario="ALTA_DEMANDA",
            data_inicial_janela=date(2026, 10, 26),
            data_final_janela=date(2026, 10, 30),
            inicio_simulacao=datetime(
                2026, 10, 30, 9, 0, tzinfo=FUSO_HORARIO
            ),
            fuso_horario="America/Bahia",
        ),
    }
)


def obter_configuracao_temporal_cenario(
    codigo_cenario: str,
) -> ConfiguracaoTemporalCenario | None:
    """Retorna a configuração oficial ou None para códigos desconhecidos."""

    return CONFIGURACOES_TEMPORAIS_CENARIOS.get(codigo_cenario)
