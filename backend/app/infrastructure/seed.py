from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.models import (
    Bairro,
    CategoriaProduto,
    Cenario,
    OrigemPedido,
    Pedido,
)
from app.infrastructure.bairro_repository import obter_ou_criar_bairro
from app.infrastructure.cenario_repository import obter_ou_criar_cenario
from app.infrastructure.database import inicializar_banco
from app.infrastructure.pedido_repository import (
    desativar_referencias_fora_do_seed,
    listar_pedidos_por_cenario,
    obter_ou_criar_pedido,
)


FUSO_HORARIO = ZoneInfo("America/Bahia")


BAIRROS_CENARIO_01 = [
    ("Comercio", -12.963, -38.507),
    ("Barra", -13.006, -38.528),
    ("Brotas", -12.986, -38.482),
    ("Pituba", -12.999, -38.460),
    ("Rio Vermelho", -13.010, -38.490),
    ("Itapua", -12.940, -38.358),
    ("Boca do Rio", -12.976, -38.429),
    ("Pernambues", -12.971, -38.465),
]


# codigo, bairro, categoria, clube, entrega rapida, SLA,
# peso, volume, tempo de servico, data de criacao
PEDIDOS_CENARIO_01 = [
    (
        "PED-001", "Comercio", CategoriaProduto.MEDICAMENTO,
        True, True, 1, 1.2, 2.0, 7,
        datetime(2026, 10, 26, 9, 15, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-002", "Barra", CategoriaProduto.ROUPA,
        False, False, 5, 1.0, 4.0, 5,
        datetime(2026, 10, 26, 11, 30, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-003", "Brotas", CategoriaProduto.ALIMENTO,
        True, False, 3, 2.5, 5.0, 8,
        datetime(2026, 10, 26, 15, 10, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-004", "Pituba", CategoriaProduto.ELETRONICO,
        False, True, 1, 3.0, 8.0, 10,
        datetime(2026, 10, 27, 9, 40, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-005", "Rio Vermelho", CategoriaProduto.OUTRO,
        False, False, 10, 0.5, 1.0, 5,
        datetime(2026, 10, 27, 13, 20, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-006", "Itapua", CategoriaProduto.MEDICAMENTO,
        False, True, 2, 0.8, 1.5, 7,
        datetime(2026, 10, 28, 10, 5, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-007", "Boca do Rio", CategoriaProduto.ALIMENTO,
        True, False, 5, 1.5, 3.0, 6,
        datetime(2026, 10, 28, 15, 30, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-008", "Pernambues", CategoriaProduto.ROUPA,
        False, False, 7, 1.2, 4.0, 5,
        datetime(2026, 10, 29, 9, 20, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-009", "Comercio", CategoriaProduto.ELETRONICO,
        True, False, 3, 2.2, 6.0, 8,
        datetime(2026, 10, 29, 12, 45, tzinfo=FUSO_HORARIO),
    ),
    (
        "PED-010", "Barra", CategoriaProduto.ALIMENTO,
        False, False, 5, 1.0, 2.5, 6,
        datetime(2026, 10, 29, 16, 10, tzinfo=FUSO_HORARIO),
    ),
]


# Os cenarios adicionais compartilham os oito bairros de NORMAL, mas
# possuem codigos e massas de pedidos independentes. Cada linha de
# atributos fornece categoria, clube, entrega rapida, SLA, peso,
# volume e tempo de servico; o seed alterna essas combinacoes de forma
# deterministica para produzir dados variados e repetiveis.
_ATRIBUTOS_PEDIDO = (
    (CategoriaProduto.MEDICAMENTO, True, True, 1, 1.2, 2.0, 7),
    (CategoriaProduto.ALIMENTO, True, False, 2, 2.5, 5.0, 8),
    (CategoriaProduto.ROUPA, False, False, 4, 1.0, 4.0, 5),
    (CategoriaProduto.ELETRONICO, False, True, 1, 3.0, 8.0, 10),
    (CategoriaProduto.OUTRO, False, False, 3, 0.5, 1.0, 5),
    (CategoriaProduto.ALIMENTO, False, True, 2, 1.8, 3.5, 6),
)

DATA_CENARIOS_NOVOS = datetime(2026, 10, 30, 9, 0, tzinfo=FUSO_HORARIO)


def inicializar_cenario_01() -> Cenario:
    """Cadastra ou recupera o cenario de operacao normal."""

    cenario = Cenario(
        codigo="NORMAL",
        nome="Operacao normal",
        descricao=(
            "Condicoes normais de transito e "
            "10 pedidos predefinidos para simulacao."
        ),
    )

    return obter_ou_criar_cenario(cenario)


def inicializar_bairros_cenario_01() -> list[Bairro]:
    """Cadastra ou recupera os bairros iniciais."""

    bairros = []

    for nome, latitude, longitude in BAIRROS_CENARIO_01:
        bairro = Bairro(
            nome=nome,
            latitude=latitude,
            longitude=longitude,
        )

        bairros.append(obter_ou_criar_bairro(bairro))

    return bairros


def inicializar_pedidos_cenario_01(
    cenario: Cenario,
    bairros: list[Bairro],
) -> list[Pedido]:
    """Cadastra ou recupera os pedidos predefinidos."""

    if cenario.id is None:
        raise RuntimeError("O cenario precisa ter um ID.")

    bairros_por_nome = {
        bairro.nome: bairro
        for bairro in bairros
    }

    pedidos = []

    for dados in PEDIDOS_CENARIO_01:
        (
            codigo,
            nome_bairro,
            categoria,
            cliente_clube,
            entrega_rapida,
            sla,
            peso,
            volume,
            tempo_servico,
            criado_em,
        ) = dados

        pedido = Pedido(
            codigo=codigo,
            bairro=bairros_por_nome[nome_bairro],
            categoria_produto=categoria,
            cliente_clube=cliente_clube,
            entrega_rapida=entrega_rapida,
            sla_dias_uteis=sla,
            peso_kg=peso,
            volume_l=volume,
            tempo_servico_min=tempo_servico,
            criado_em=criado_em,
        )

        pedido_salvo = obter_ou_criar_pedido(
            pedido, cenario.id, origem=OrigemPedido.REFERENCIA
        )
        pedidos.append(pedido_salvo)

    desativar_referencias_fora_do_seed(
        cenario.id,
        [dados[0] for dados in PEDIDOS_CENARIO_01],
    )

    return pedidos


def _inicializar_cenario_com_pedidos(
    cenario: Cenario,
    bairros: list[Bairro],
    codigo_prefixo: str,
    pedidos_por_bairro: int,
    intervalo_minutos: int,
    total_pedidos: int | None = None,
) -> list[Pedido]:
    """Cadastra pedidos deterministicos e idempotentes de um cenario."""

    if cenario.id is None:
        raise RuntimeError("O cenario precisa ter um ID.")

    if len(bairros) != len(BAIRROS_CENARIO_01):
        raise ValueError("O cenario exige os oito bairros cadastrados.")

    pedidos = []
    ordem = 0

    for indice_bairro, bairro in enumerate(bairros):
        for numero_no_bairro in range(pedidos_por_bairro):
            if total_pedidos is not None and ordem >= total_pedidos:
                break
            ordem += 1
            atributos = _ATRIBUTOS_PEDIDO[
                (indice_bairro * 2 + numero_no_bairro) % len(_ATRIBUTOS_PEDIDO)
            ]
            categoria, clube, rapida, sla, peso, volume, servico = atributos
            criado_em = DATA_CENARIOS_NOVOS + timedelta(
                minutes=(ordem - 1) * intervalo_minutos
            )
            pedido = Pedido(
                codigo=f"{codigo_prefixo}-{ordem:03d}",
                bairro=bairro,
                categoria_produto=categoria,
                cliente_clube=clube,
                entrega_rapida=rapida,
                sla_dias_uteis=sla,
                criado_em=criado_em,
                peso_kg=peso,
                volume_l=volume,
                tempo_servico_min=servico,
            )
            pedidos.append(obter_ou_criar_pedido(
                pedido, cenario.id, origem=OrigemPedido.REFERENCIA
            ))

    desativar_referencias_fora_do_seed(
        cenario.id,
        [pedido.codigo for pedido in pedidos],
    )

    return pedidos


def inicializar_cenario_02(bairros: list[Bairro] | None = None) -> Cenario:
    """Cadastra ALTA_DEMANDA com 24 pedidos próprios, 3 por bairro."""

    cenario = obter_ou_criar_cenario(
        Cenario(
            codigo="ALTA_DEMANDA",
            nome="Alta Demanda e Trânsito Intenso",
            descricao=(
                "24 pedidos próprios, distribuídos em 3 pedidos por bairro "
                "nos oito bairros atendidos."
            ),
        )
    )
    _inicializar_cenario_com_pedidos(
        cenario,
        bairros if bairros is not None else inicializar_bairros_cenario_01(),
        "ALTA",
        pedidos_por_bairro=3,
        intervalo_minutos=1,
    )

    return cenario


def inicializar_cenario_03(bairros: list[Bairro] | None = None) -> Cenario:
    """Cadastra EQUIDADE com 15 pedidos próprios."""

    cenario = obter_ou_criar_cenario(
        Cenario(
            codigo="EQUIDADE",
            nome="Distribuição com Equidade",
            descricao=(
                "15 pedidos próprios, distribuídos de forma equilibrada "
                "pelos oito bairros atendidos."
            ),
        )
    )
    _inicializar_cenario_com_pedidos(
        cenario,
        bairros if bairros is not None else inicializar_bairros_cenario_01(),
        "EQ",
        pedidos_por_bairro=2,
        intervalo_minutos=3,
        total_pedidos=15,
    )

    return cenario


def inicializar_todos_cenarios() -> list[Cenario]:
    """Inicializa o banco e cadastra os tres cenarios predefinidos."""

    inicializar_banco()
    normal = inicializar_cenario_01()
    bairros = inicializar_bairros_cenario_01()
    inicializar_pedidos_cenario_01(normal, bairros)
    alta_demanda = inicializar_cenario_02(bairros)
    equidade = inicializar_cenario_03(bairros)

    return [normal, alta_demanda, equidade]


def main() -> None:
    cenarios = inicializar_todos_cenarios()

    for cenario in cenarios:
        pedidos = listar_pedidos_por_cenario(cenario.id)
        print(f"Cenario: {cenario.codigo} - {cenario.nome}")
        print(f"ID do cenario: {cenario.id}")
        print(f"Quantidade de pedidos: {len(pedidos)}")

        for pedido in pedidos:
            print(
                f"- {pedido.codigo}: ID {pedido.id} | "
                f"Bairro: {pedido.bairro.nome} | "
                f"Criado em: {pedido.criado_em.isoformat()} | "
                f"Prazo: {pedido.prazo_entrega_em.isoformat()}"
            )


if __name__ == "__main__":
    main()
