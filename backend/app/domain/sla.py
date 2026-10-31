from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


FUSO_HORARIO = ZoneInfo("America/Bahia")

HORA_INICIO = time(9, 0)
HORA_FIM = time(17, 0)

HORAS_POR_DIA_UTIL = 8


def _proximo_dia_util(data: date) -> date:
    """Retorna o proximo dia de segunda a sexta."""

    proxima_data = data + timedelta(days=1)

    while proxima_data.weekday() >= 5:
        proxima_data += timedelta(days=1)

    return proxima_data


def _ajustar_inicio_operacional(momento: datetime) -> datetime:
    """Ajusta o horario para o inicio de um periodo operacional."""

    local = momento.astimezone(FUSO_HORARIO)

    if local.weekday() >= 5:
        data = local.date()

        while data.weekday() >= 5:
            data += timedelta(days=1)

        return datetime(
            data.year,
            data.month,
            data.day,
            HORA_INICIO.hour,
            HORA_INICIO.minute,
            tzinfo=FUSO_HORARIO,
        )

    if local.time() < HORA_INICIO:
        return local.replace(
            hour=HORA_INICIO.hour,
            minute=HORA_INICIO.minute,
            second=0,
            microsecond=0,
        )

    if local.time() >= HORA_FIM:
        proxima_data = _proximo_dia_util(local.date())

        return datetime(
            proxima_data.year,
            proxima_data.month,
            proxima_data.day,
            HORA_INICIO.hour,
            HORA_INICIO.minute,
            tzinfo=FUSO_HORARIO,
        )

    return local


def calcular_minutos_operacionais(
    inicio: datetime,
    fim: datetime,
) -> float:
    """
    Calcula os minutos disponiveis dentro do expediente operacional.

    Considera segunda a sexta, das 09h as 17h.
    Ignora noites e finais de semana.
    """

    for nome, momento in (
        ("inicio", inicio),
        ("fim", fim),
    ):
        if not isinstance(momento, datetime):
            raise TypeError(f"A data de {nome} deve ser um datetime.")

        if momento.tzinfo is None or momento.utcoffset() is None:
            raise ValueError(
                f"A data de {nome} deve possuir fuso horario."
            )

    inicio_utc = inicio.astimezone(timezone.utc)
    fim_utc = fim.astimezone(timezone.utc)

    if fim_utc <= inicio_utc:
        return 0.0

    inicio_local = inicio_utc.astimezone(FUSO_HORARIO)
    fim_local = fim_utc.astimezone(FUSO_HORARIO)

    total_segundos = 0.0
    data_atual = inicio_local.date()

    while data_atual <= fim_local.date():
        if data_atual.weekday() < 5:
            abertura = datetime(
                data_atual.year,
                data_atual.month,
                data_atual.day,
                HORA_INICIO.hour,
                HORA_INICIO.minute,
                tzinfo=FUSO_HORARIO,
            ).astimezone(timezone.utc)

            fechamento = datetime(
                data_atual.year,
                data_atual.month,
                data_atual.day,
                HORA_FIM.hour,
                HORA_FIM.minute,
                tzinfo=FUSO_HORARIO,
            ).astimezone(timezone.utc)

            inicio_intervalo = max(inicio_utc, abertura)
            fim_intervalo = min(fim_utc, fechamento)

            if fim_intervalo > inicio_intervalo:
                total_segundos += (
                    fim_intervalo - inicio_intervalo
                ).total_seconds()

        data_atual += timedelta(days=1)

    return total_segundos / 60


def calcular_prazo_entrega(
    criado_em: datetime,
    sla_dias_uteis: int,
) -> datetime:
    """
    Calcula o prazo de entrega considerando horas operacionais.

    A operacao funciona de segunda a sexta, das 09h as 17h.
    Feriados nao sao considerados nesta versao.
    """

    if not isinstance(criado_em, datetime):
        raise TypeError("A data de criacao deve ser um datetime.")

    if (
        criado_em.tzinfo is None
        or criado_em.utcoffset() is None
    ):
        raise ValueError(
            "A data de criacao deve possuir fuso horario."
        )

    if (
        not isinstance(sla_dias_uteis, int)
        or isinstance(sla_dias_uteis, bool)
        or sla_dias_uteis <= 0
    ):
        raise ValueError("O SLA deve ser um inteiro maior que zero.")

    restante = timedelta(
        hours=sla_dias_uteis * HORAS_POR_DIA_UTIL
    )

    momento_atual = _ajustar_inicio_operacional(criado_em)

    while restante > timedelta(0):
        fim_do_expediente = momento_atual.replace(
            hour=HORA_FIM.hour,
            minute=HORA_FIM.minute,
            second=0,
            microsecond=0,
        )

        horas_disponiveis = fim_do_expediente - momento_atual

        if restante <= horas_disponiveis:
            return momento_atual + restante

        restante -= horas_disponiveis

        proxima_data = _proximo_dia_util(momento_atual.date())

        momento_atual = datetime(
            proxima_data.year,
            proxima_data.month,
            proxima_data.day,
            HORA_INICIO.hour,
            HORA_INICIO.minute,
            tzinfo=FUSO_HORARIO,
        )

    return momento_atual
