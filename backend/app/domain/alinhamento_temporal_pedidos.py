"""Datas efetivas determinísticas dos pedidos de referência por cenário."""

from dataclasses import replace
from datetime import date, datetime
from types import MappingProxyType
from typing import Mapping, Sequence

from app.domain.configuracao_temporal import (
    CONFIGURACOES_TEMPORAIS_CENARIOS,
    ConfiguracaoTemporalCenario,
)
from app.domain.models import OrigemPedido, Pedido
from app.domain.sla import FUSO_HORARIO, calcular_prazo_entrega


VERSAO_REGRA_TEMPORAL_PEDIDOS = 1


def _criar_manifesto(
    grupos: Sequence[tuple[datetime, Sequence[str]]],
) -> Mapping[str, datetime]:
    manifesto: dict[str, datetime] = {}
    for instante, codigos in grupos:
        for codigo in codigos:
            if codigo in manifesto:
                raise ValueError(f"Código duplicado no manifesto: {codigo}.")
            manifesto[codigo] = instante
    return MappingProxyType(manifesto)


MANIFESTO_TEMPORAL_PEDIDOS: Mapping[str, Mapping[str, datetime]] = (
    MappingProxyType(
        {
            "NORMAL": _criar_manifesto(
                [
                    (
                        datetime(2026, 10, 5, 9, tzinfo=FUSO_HORARIO),
                        ("PED-001", "PED-005", "PED-006", "PED-009"),
                    ),
                    (datetime(2026, 10, 5, 13, tzinfo=FUSO_HORARIO), ("PED-002",)),
                    (
                        datetime(2026, 10, 6, 9, tzinfo=FUSO_HORARIO),
                        ("PED-003", "PED-004", "PED-007"),
                    ),
                    (
                        datetime(2026, 10, 6, 13, tzinfo=FUSO_HORARIO),
                        ("PED-008", "PED-010"),
                    ),
                ]
            ),
            "EQUIDADE": _criar_manifesto(
                [
                    (
                        datetime(2026, 10, 12, 9, tzinfo=FUSO_HORARIO),
                        ("EQ-001", "EQ-009"),
                    ),
                    (
                        datetime(2026, 10, 12, 13, tzinfo=FUSO_HORARIO),
                        ("EQ-002", "EQ-010"),
                    ),
                    (
                        datetime(2026, 10, 13, 9, tzinfo=FUSO_HORARIO),
                        ("EQ-003", "EQ-011"),
                    ),
                    (
                        datetime(2026, 10, 13, 13, tzinfo=FUSO_HORARIO),
                        ("EQ-004", "EQ-012"),
                    ),
                    (
                        datetime(2026, 10, 14, 9, tzinfo=FUSO_HORARIO),
                        ("EQ-005", "EQ-013"),
                    ),
                    (
                        datetime(2026, 10, 14, 13, tzinfo=FUSO_HORARIO),
                        ("EQ-006", "EQ-014"),
                    ),
                    (
                        datetime(2026, 10, 15, 9, tzinfo=FUSO_HORARIO),
                        ("EQ-007", "EQ-015"),
                    ),
                    (datetime(2026, 10, 15, 13, tzinfo=FUSO_HORARIO), ("EQ-008",)),
                ]
            ),
            "ALTA_DEMANDA": _criar_manifesto(
                [
                    (
                        datetime(2026, 10, 26, 9, tzinfo=FUSO_HORARIO),
                        ("ALTA-001", "ALTA-009", "ALTA-017"),
                    ),
                    (
                        datetime(2026, 10, 26, 13, tzinfo=FUSO_HORARIO),
                        ("ALTA-002", "ALTA-010", "ALTA-018"),
                    ),
                    (
                        datetime(2026, 10, 27, 9, tzinfo=FUSO_HORARIO),
                        ("ALTA-003", "ALTA-011", "ALTA-019"),
                    ),
                    (
                        datetime(2026, 10, 27, 13, tzinfo=FUSO_HORARIO),
                        ("ALTA-004", "ALTA-012", "ALTA-020"),
                    ),
                    (
                        datetime(2026, 10, 28, 9, tzinfo=FUSO_HORARIO),
                        ("ALTA-005", "ALTA-013", "ALTA-021"),
                    ),
                    (
                        datetime(2026, 10, 28, 13, tzinfo=FUSO_HORARIO),
                        ("ALTA-006", "ALTA-014", "ALTA-022"),
                    ),
                    (
                        datetime(2026, 10, 29, 9, tzinfo=FUSO_HORARIO),
                        ("ALTA-007", "ALTA-015", "ALTA-023"),
                    ),
                    (
                        datetime(2026, 10, 29, 13, tzinfo=FUSO_HORARIO),
                        ("ALTA-008", "ALTA-016", "ALTA-024"),
                    ),
                ]
            ),
        }
    )
)


def alinhar_pedidos_do_cenario(
    codigo_cenario: str,
    pedidos: Sequence[Pedido],
    inicio_simulacao: datetime,
) -> tuple[list[Pedido], list[Pedido]]:
    """Retorna cópias efetivas para o motor e a massa original do snapshot.

    Pedidos manuais são preservados sem transformação. Pedidos cuja criação
    está no futuro do relógio inicial ficam fora do snapshot. Referências
    ativas exigem uma entrada explícita no manifesto.
    """

    configuracao = CONFIGURACOES_TEMPORAIS_CENARIOS.get(codigo_cenario)
    if configuracao is None:
        raise ValueError(
            f"Não há configuração temporal para o cenário {codigo_cenario}."
        )

    manifesto = MANIFESTO_TEMPORAL_PEDIDOS[codigo_cenario]
    historicos: list[Pedido] = []
    efetivos: list[Pedido] = []
    vistos: set[str] = set()

    for pedido in pedidos:
        if not pedido.ativo:
            continue
        if pedido.origem == OrigemPedido.REFERENCIA:
            if pedido.codigo in vistos:
                raise ValueError(
                    f"Pedido de referência duplicado no cenário: {pedido.codigo}."
                )
            vistos.add(pedido.codigo)
            criado_efetivo = manifesto.get(pedido.codigo)
            if criado_efetivo is None:
                raise ValueError(
                    "Pedido de referência ativo sem data no manifesto "
                    f"temporal de {codigo_cenario}: {pedido.codigo}."
                )
            if not (
                configuracao.data_inicial_janela
                <= criado_efetivo.date()
                <= configuracao.data_final_janela
            ):
                raise ValueError(
                    f"Data do manifesto fora da janela para {pedido.codigo}."
                )
            if criado_efetivo > inicio_simulacao:
                raise ValueError(
                    f"Pedido {pedido.codigo} tem criação posterior ao início."
                )
            pedido_efetivo = replace(
                pedido,
                criado_em=criado_efetivo,
                prazo_entrega_em=calcular_prazo_entrega(
                    criado_efetivo, pedido.sla_dias_uteis
                ),
            )
        else:
            if pedido.criado_em > inicio_simulacao:
                continue
            pedido_efetivo = replace(pedido)

        historicos.append(pedido)
        efetivos.append(pedido_efetivo)

    return historicos, efetivos


def validar_data_criacao_manual(
    configuracao: ConfiguracaoTemporalCenario,
    data_criacao: date,
) -> datetime:
    """Valida a data informada e fixa o horário operacional às 09:00."""

    if type(data_criacao) is not date:
        raise ValueError("A data de criação deve ser informada sem horário.")
    if not (
        configuracao.data_inicial_janela
        <= data_criacao
        <= configuracao.data_final_janela
    ):
        raise ValueError(
            "A data de criação deve estar dentro da janela do cenário "
            f"({configuracao.data_inicial_janela.isoformat()} a "
            f"{configuracao.data_final_janela.isoformat()})."
        )
    if data_criacao.weekday() >= 5:
        raise ValueError("A data de criação deve ser um dia útil.")
    if data_criacao > configuracao.inicio_simulacao.date():
        raise ValueError(
            "A data de criação não pode ser posterior à data da simulação."
        )
    return datetime(
        data_criacao.year,
        data_criacao.month,
        data_criacao.day,
        9,
        0,
        tzinfo=FUSO_HORARIO,
    )

