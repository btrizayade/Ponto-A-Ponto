from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.models import Bairro, CategoriaProduto, Cenario, Pedido
from app.infrastructure.bairro_repository import obter_ou_criar_bairro
from app.infrastructure.cenario_repository import obter_ou_criar_cenario
from app.infrastructure.database import inicializar_banco
from app.infrastructure.pedido_repository import obter_ou_criar_pedido


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

        pedido_salvo = obter_ou_criar_pedido(pedido, cenario.id)
        pedidos.append(pedido_salvo)

    return pedidos


def main() -> None:
    inicializar_banco()

    cenario = inicializar_cenario_01()
    bairros = inicializar_bairros_cenario_01()
    pedidos = inicializar_pedidos_cenario_01(cenario, bairros)

    print(f"Cenario: {cenario.codigo} - {cenario.nome}")
    print(f"ID do cenario: {cenario.id}")
    print(f"Quantidade de bairros: {len(bairros)}")
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
