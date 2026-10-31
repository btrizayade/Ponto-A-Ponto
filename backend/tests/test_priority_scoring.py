
import pytest

from datetime import datetime, timedelta, timezone
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

def criar_pedido_para_teste_aging(criado_em: datetime) -> Pedido:
    """Cria um pedido com pontuacao inicial conhecida."""

    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    return Pedido(
        codigo="PED-AGING-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
        criado_em=criado_em,
    )


def test_prioridade_soma_pontuacao_do_aging():
    criado_em = datetime(
        2026, 10, 26, 9, 0, tzinfo=timezone.utc
    )

    agora = criado_em + timedelta(hours=24)
    pedido = criar_pedido_para_teste_aging(criado_em)

    # Pontuacao inicial: 17.
    # Aging de 24 horas: 6 pontos.
    assert calcular_prioridade(pedido, agora=agora) == 23


def test_prioridade_sem_aging_antes_de_quatro_horas():
    criado_em = datetime(
        2026, 10, 26, 9, 0, tzinfo=timezone.utc
    )

    agora = criado_em + timedelta(hours=3, minutes=59)
    pedido = criar_pedido_para_teste_aging(criado_em)

    assert calcular_prioridade(pedido, agora=agora) == 17


def test_prioridade_respeita_limite_maximo_do_aging():
    criado_em = datetime(
        2026, 10, 26, 9, 0, tzinfo=timezone.utc
    )

    agora = criado_em + timedelta(hours=100)
    pedido = criar_pedido_para_teste_aging(criado_em)

    # Pontuacao inicial: 17.
    # Aging limitado a 20 pontos.
    assert calcular_prioridade(pedido, agora=agora) == 37

def test_prioridade_inclui_risco_de_sla():
    agora = datetime(
        2026, 10, 30, 12, 0, tzinfo=timezone.utc
    )

    pedido = criar_pedido_para_teste_aging(
        agora - timedelta(hours=4)
    )

    pedido.prazo_entrega_em = agora + timedelta(minutes=60)

    prioridade = calcular_prioridade(
        pedido,
        agora=agora,
        tempo_estimado_entrega_min=30,
    )

    # Base: 17, aging: 1, risco de SLA: 40.
    assert prioridade == 58


def test_prioridade_sem_risco_quando_estimativa_tem_folga():
    agora = datetime(
        2026, 10, 30, 12, 0, tzinfo=timezone.utc
    )

    pedido = criar_pedido_para_teste_aging(
        agora - timedelta(hours=4)
    )

    pedido.prazo_entrega_em = agora + timedelta(minutes=300)

    prioridade = calcular_prioridade(
        pedido,
        agora=agora,
        tempo_estimado_entrega_min=30,
    )

    # Base: 17, aging: 1, risco de SLA: 0.
    assert prioridade == 18