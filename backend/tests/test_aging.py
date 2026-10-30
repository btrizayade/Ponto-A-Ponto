from datetime import datetime, timedelta, timezone

import pytest

from app.domain.aging import calcular_pontuacao_aging


def test_aging_abaixo_de_quatro_horas():
    criado_em = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
    agora = criado_em + timedelta(hours=3, minutes=59)

    assert calcular_pontuacao_aging(criado_em, agora) == 0


@pytest.mark.parametrize(
    ("horas_espera", "pontuacao_esperada"),
    [
        (4, 1),
        (8, 2),
        (12, 3),
        (24, 6),
        (48, 12),
        (80, 20),
        (120, 20),
    ],
)
def test_pontuacao_por_tempo_de_espera(
    horas_espera,
    pontuacao_esperada,
):
    criado_em = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
    agora = criado_em + timedelta(hours=horas_espera)

    resultado = calcular_pontuacao_aging(criado_em, agora)

    assert resultado == pontuacao_esperada


def test_aging_considera_final_de_semana():
    criado_em = datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc)
    agora = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)

    resultado = calcular_pontuacao_aging(criado_em, agora)

    assert resultado == 18


def test_aging_nao_calcula_tempo_negativo():
    criado_em = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    agora = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)

    assert calcular_pontuacao_aging(criado_em, agora) == 0


def test_aging_rejeita_data_de_criacao_sem_fuso():
    criado_em = datetime(2026, 10, 26, 9, 0)
    agora = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="fuso horario"):
        calcular_pontuacao_aging(criado_em, agora)


def test_aging_rejeita_data_atual_sem_fuso():
    criado_em = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
    agora = datetime(2026, 10, 27, 9, 0)

    with pytest.raises(ValueError, match="fuso horario"):
        calcular_pontuacao_aging(criado_em, agora)