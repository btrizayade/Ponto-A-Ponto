from datetime import date, datetime

import pytest

from app.domain.configuracao_temporal import (
    CONFIGURACOES_TEMPORAIS_CENARIOS,
    obter_configuracao_temporal_cenario,
)
from app.domain.sla import FUSO_HORARIO
from app.domain.simulation import _validar_inicio_no_expediente


@pytest.mark.parametrize(
    ("codigo", "inicio_janela", "fim_janela", "inicio_simulacao"),
    [
        (
            "NORMAL",
            date(2026, 10, 5),
            date(2026, 10, 7),
            datetime(2026, 10, 7, 9, 0, tzinfo=FUSO_HORARIO),
        ),
        (
            "EQUIDADE",
            date(2026, 10, 12),
            date(2026, 10, 16),
            datetime(2026, 10, 16, 9, 0, tzinfo=FUSO_HORARIO),
        ),
        (
            "ALTA_DEMANDA",
            date(2026, 10, 26),
            date(2026, 10, 30),
            datetime(2026, 10, 30, 9, 0, tzinfo=FUSO_HORARIO),
        ),
    ],
)
def test_configuracao_temporal_oficial_por_cenario(
    codigo, inicio_janela, fim_janela, inicio_simulacao
):
    configuracao = obter_configuracao_temporal_cenario(codigo)

    assert configuracao is not None
    assert configuracao.codigo_cenario == codigo
    assert configuracao.data_inicial_janela == inicio_janela
    assert configuracao.data_final_janela == fim_janela
    assert configuracao.inicio_simulacao == inicio_simulacao
    assert configuracao.inicio_simulacao.tzinfo is FUSO_HORARIO
    assert configuracao.fuso_horario == "America/Bahia"
    assert inicio_janela <= inicio_simulacao.date() <= fim_janela
    assert inicio_simulacao.weekday() < 5
    assert inicio_simulacao.hour == 9
    _validar_inicio_no_expediente(configuracao.inicio_simulacao)


def test_configuracao_contem_exatamente_tres_cenarios():
    assert set(CONFIGURACOES_TEMPORAIS_CENARIOS) == {
        "NORMAL",
        "EQUIDADE",
        "ALTA_DEMANDA",
    }


def test_cenario_desconhecido_nao_recebe_data_inferida():
    assert obter_configuracao_temporal_cenario("OUTRO") is None


@pytest.mark.parametrize(
    "inicio_invalido",
    [
        datetime(2026, 10, 10, 9, 0, tzinfo=FUSO_HORARIO),
        datetime(2026, 10, 7, 8, 59, tzinfo=FUSO_HORARIO),
        datetime(2026, 10, 7, 17, 0, tzinfo=FUSO_HORARIO),
    ],
)
def test_validacao_atual_rejeita_inicio_fora_do_expediente(inicio_invalido):
    with pytest.raises(ValueError):
        _validar_inicio_no_expediente(inicio_invalido)
