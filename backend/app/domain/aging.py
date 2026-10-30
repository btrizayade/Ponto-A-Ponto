from datetime import datetime, timezone


INTERVALO_AGING_HORAS = 4
PONTOS_POR_INTERVALO = 1
PONTUACAO_AGING_MAXIMA = 20


def calcular_pontuacao_aging(
    criado_em: datetime,
    agora: datetime | None = None,
) -> int:
    """
    Calcula a pontuacao adicional pelo tempo de espera.

    Considera horas corridas, incluindo noites e finais de semana.
    Adiciona 1 ponto a cada 4 horas, limitado a 20 pontos.
    """

    if not isinstance(criado_em, datetime):
        raise TypeError("A data de criacao deve ser um datetime.")

    if criado_em.tzinfo is None or criado_em.utcoffset() is None:
        raise ValueError(
            "A data de criacao deve possuir fuso horario."
        )

    if agora is None:
        agora = datetime.now(timezone.utc)

    if not isinstance(agora, datetime):
        raise TypeError("A data atual deve ser um datetime.")

    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError(
            "A data atual deve possuir fuso horario."
        )

    criacao_utc = criado_em.astimezone(timezone.utc)
    agora_utc = agora.astimezone(timezone.utc)

    segundos_espera = (
        agora_utc - criacao_utc
    ).total_seconds()

    intervalos_completos = max(
        0,
        int(
            segundos_espera
            // (INTERVALO_AGING_HORAS * 3600)
        ),
    )

    pontuacao = intervalos_completos * PONTOS_POR_INTERVALO

    return min(pontuacao, PONTUACAO_AGING_MAXIMA)