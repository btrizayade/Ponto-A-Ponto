from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.sla import calcular_prazo_entrega, calcular_minutos_operacionais


FUSO = ZoneInfo("America/Bahia")


@pytest.mark.parametrize(
    ("criado_em", "sla", "esperado"),
    [
        # Segunda-feira as 09h, um dia util.
        (
            datetime(2026, 10, 26, 9, 0, tzinfo=FUSO),
            1,
            datetime(2026, 10, 26, 17, 0, tzinfo=FUSO),
        ),

        # Segunda-feira as 10h, um dia util.
        (
            datetime(2026, 10, 26, 10, 0, tzinfo=FUSO),
            1,
            datetime(2026, 10, 27, 10, 0, tzinfo=FUSO),
        ),

        # Sexta-feira as 14h, atravessando o fim de semana.
        (
            datetime(2026, 10, 30, 14, 0, tzinfo=FUSO),
            1,
            datetime(2026, 11, 2, 14, 0, tzinfo=FUSO),
        ),

        # Sabado: a contagem comeca na segunda-feira.
        (
            datetime(2026, 10, 31, 11, 0, tzinfo=FUSO),
            1,
            datetime(2026, 11, 2, 17, 0, tzinfo=FUSO),
        ),

        # Antes do expediente.
        (
            datetime(2026, 10, 26, 8, 0, tzinfo=FUSO),
            1,
            datetime(2026, 10, 26, 17, 0, tzinfo=FUSO),
        ),

        # Exatamente no encerramento do expediente.
        (
            datetime(2026, 10, 26, 17, 0, tzinfo=FUSO),
            1,
            datetime(2026, 10, 27, 17, 0, tzinfo=FUSO),
        ),

        # Dois dias uteis a partir de segunda-feira as 10h.
        (
            datetime(2026, 10, 26, 10, 0, tzinfo=FUSO),
            2,
            datetime(2026, 10, 28, 10, 0, tzinfo=FUSO),
        ),
    ],
)
def test_calcular_prazo_entrega(criado_em, sla, esperado):
    resultado = calcular_prazo_entrega(criado_em, sla)

    assert resultado == esperado
    assert resultado.tzinfo == FUSO


def test_calcular_prazo_recebe_data_em_utc():
    criado_em = datetime(
        2026, 10, 26, 13, 0, tzinfo=ZoneInfo("UTC")
    )

    resultado = calcular_prazo_entrega(criado_em, 1)

    esperado = datetime(
        2026, 10, 27, 10, 0, tzinfo=FUSO
    )

    assert resultado == esperado
    assert resultado.tzinfo == FUSO


def test_rejeitar_data_sem_fuso_horario():
    criado_em = datetime(2026, 10, 26, 10, 0)

    with pytest.raises(ValueError, match="fuso horario"):
        calcular_prazo_entrega(criado_em, 1)


@pytest.mark.parametrize("sla", [0, -1, 1.5, True])
def test_rejeitar_sla_invalido(sla):
    criado_em = datetime(
        2026, 10, 26, 10, 0, tzinfo=FUSO
    )

    with pytest.raises(ValueError, match="SLA"):
        calcular_prazo_entrega(criado_em, sla)

def test_minutos_operacionais_ignoram_noites_e_finais_de_semana():
    inicio = datetime(
        2026, 10, 30, 16, 0, tzinfo=FUSO
    )

    fim = datetime(
        2026, 11, 2, 10, 0, tzinfo=FUSO
    )

    resultado = calcular_minutos_operacionais(inicio, fim)

    # Sexta: 1 hora.
    # Sabado e domingo: 0 horas.
    # Segunda: 1 hora.
    assert resultado == 120


def test_minutos_operacionais_consideram_apenas_expediente():
    inicio = datetime(
        2026, 10, 26, 8, 0, tzinfo=FUSO
    )

    fim = datetime(
        2026, 10, 26, 18, 0, tzinfo=FUSO
    )

    resultado = calcular_minutos_operacionais(inicio, fim)

    assert resultado == 480
