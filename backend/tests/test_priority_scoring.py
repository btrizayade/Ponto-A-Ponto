
import pytest

from app.domain.models import Bairro, CategoriaProduto, Pedido
from app.domain.priority_scoring import calcular_prioridade


@pytest.fixture
def bairro() -> Bairro:
    return Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )


def criar_pedido(
    bairro: Bairro,
    *,
    categoria: CategoriaProduto = CategoriaProduto.OUTRO,
    clube: bool = False,
    entrega_rapida: bool = False,
    sla: int = 5,
) -> Pedido:
    return Pedido(
        codigo="PED-TESTE",
        bairro=bairro,
        categoria_produto=categoria,
        cliente_clube=clube,
        entrega_rapida=entrega_rapida,
        sla_dias_uteis=sla,
    )


def test_cliente_clube_recebe_bonus(bairro: Bairro) -> None:
    pedido = criar_pedido(bairro, clube=True, sla=10)
    assert calcular_prioridade(pedido) == 5


def test_entrega_rapida_recebe_bonus(bairro: Bairro) -> None:
    pedido = criar_pedido(bairro, entrega_rapida=True, sla=10)
    assert calcular_prioridade(pedido) == 5



@pytest.mark.parametrize(
    "categoria",
    [CategoriaProduto.ALIMENTO, CategoriaProduto.MEDICAMENTO],
)
def test_produto_prioritario_recebe_bonus(
    bairro: Bairro,
    categoria: CategoriaProduto,
) -> None:
    pedido_prioritario = criar_pedido(
        bairro,
        categoria=categoria,
        sla=10,
    )

    pedido_comum = criar_pedido(
        bairro,
        categoria=CategoriaProduto.OUTRO,
        sla=10,
    )

    diferenca = (
        calcular_prioridade(pedido_prioritario)
        - calcular_prioridade(pedido_comum)
    )

    assert diferenca == 2


@pytest.mark.parametrize(
    ("sla", "pontuacao_esperada"),
    [(1, 5), (2, 3), (3, 3), (4, 1), (5, 2), (10, 1)],
)
def test_pontuacao_por_sla(
    bairro: Bairro,
    sla: int,
    pontuacao_esperada: int,
) -> None:
    pedido = criar_pedido(bairro, sla=sla)
    assert calcular_prioridade(pedido) == pontuacao_esperada


def test_beneficios_sao_acumulados(bairro: Bairro) -> None:
    pedido = criar_pedido(
        bairro,
        categoria=CategoriaProduto.MEDICAMENTO,
        clube=True,
        entrega_rapida=True,
        sla=1,
    )

    assert calcular_prioridade(pedido) == 17


def test_cliente_comum_com_sla_longo_recebe_bonus(
    bairro: Bairro,
) -> None:
    pedido = criar_pedido(
        bairro,
        clube=False,
        entrega_rapida=False,
        sla=7,
    )

    assert calcular_prioridade(pedido) == 1
