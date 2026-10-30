
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.models import (
    Bairro,
    CategoriaProduto,
    Cenario,
    Entregador,
    Pedido,
)


@pytest.fixture
def bairro() -> Bairro:
    return Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )


@pytest.fixture
def pedido(bairro: Bairro) -> Pedido:
    return Pedido(
        codigo="PED-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
    )


def test_bairro_valido(bairro: Bairro) -> None:
    assert bairro.nome == "Comercio"
    assert -90 <= bairro.latitude <= 90
    assert -180 <= bairro.longitude <= 180


def test_bairro_rejeita_nome_vazio() -> None:
    with pytest.raises(ValueError):
        Bairro(nome=" ", latitude=-12.963, longitude=-38.507)


def test_bairro_rejeita_latitude_invalida() -> None:
    with pytest.raises(ValueError):
        Bairro(nome="Comercio", latitude=91, longitude=-38.507)


def test_pedido_valido(pedido: Pedido) -> None:
    assert pedido.codigo == "PED-001"
    assert pedido.bairro.nome == "Comercio"
    assert pedido.produto_prioritario is True


@pytest.mark.parametrize(
    "categoria",
    [
        CategoriaProduto.ALIMENTO,
        CategoriaProduto.MEDICAMENTO,
    ],
)
def test_produtos_prioritarios(
    bairro: Bairro,
    categoria: CategoriaProduto,
) -> None:
    pedido = Pedido(
        codigo="PED-002",
        bairro=bairro,
        categoria_produto=categoria,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=3,
    )

    assert pedido.produto_prioritario is True


def test_produto_comum_nao_e_prioritario(bairro: Bairro) -> None:
    pedido = Pedido(
        codigo="PED-003",
        bairro=bairro,
        categoria_produto=CategoriaProduto.ROUPA,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=5,
    )

    assert pedido.produto_prioritario is False


@pytest.mark.parametrize("sla", [0, -1])
def test_pedido_rejeita_sla_invalido(
    bairro: Bairro,
    sla: int,
) -> None:
    with pytest.raises(ValueError):
        Pedido(
            codigo="PED-004",
            bairro=bairro,
            categoria_produto=CategoriaProduto.OUTRO,
            cliente_clube=False,
            entrega_rapida=False,
            sla_dias_uteis=sla,
        )


def test_pedido_rejeita_peso_negativo(bairro: Bairro) -> None:
    with pytest.raises(ValueError):
        Pedido(
            codigo="PED-005",
            bairro=bairro,
            categoria_produto=CategoriaProduto.OUTRO,
            cliente_clube=False,
            entrega_rapida=False,
            sla_dias_uteis=5,
            peso_kg=-1,
        )


def test_entregador_valido() -> None:
    entregador = Entregador(codigo="ENT-001")
    assert entregador.codigo == "ENT-001"
    assert entregador.id is None


def test_entregador_rejeita_codigo_vazio() -> None:
    with pytest.raises(ValueError):
        Entregador(codigo=" ")


def test_cenario_valido() -> None:
    cenario = Cenario(
        codigo="NORMAL",
        nome="Operacao normal",
    )

    assert cenario.codigo == "NORMAL"
    assert cenario.id is None


def test_cenario_rejeita_codigo_vazio() -> None:
    with pytest.raises(ValueError):
        Cenario(codigo=" ", nome="Teste")


def test_cenario_rejeita_nome_vazio() -> None:
    with pytest.raises(ValueError):
        Cenario(codigo="TESTE", nome=" ")


def test_pedido_tem_data_de_criacao_com_fuso_horario():
    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    pedido = Pedido(
        codigo="PED-TEMPO-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
    )

    assert pedido.criado_em.tzinfo is not None
    assert pedido.criado_em.utcoffset() is not None
    assert pedido.prazo_entrega_em is None


def test_pedido_rejeita_prazo_anterior_a_criacao():
    criado_em = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    prazo_entrega_em = criado_em - timedelta(hours=1)

    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    with pytest.raises(ValueError, match="posterior a criacao"):
        Pedido(
            codigo="PED-TEMPO-002",
            bairro=bairro,
            categoria_produto=CategoriaProduto.MEDICAMENTO,
            cliente_clube=True,
            entrega_rapida=True,
            sla_dias_uteis=1,
            criado_em=criado_em,
            prazo_entrega_em=prazo_entrega_em,
        )


def test_pedido_rejeita_prazo_sem_fuso_horario():
    criado_em = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    prazo_entrega_em = datetime(2026, 10, 30, 12, 0)

    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    with pytest.raises(ValueError, match="fuso horario"):
        Pedido(
            codigo="PED-TEMPO-003",
            bairro=bairro,
            categoria_produto=CategoriaProduto.MEDICAMENTO,
            cliente_clube=True,
            entrega_rapida=True,
            sla_dias_uteis=1,
            criado_em=criado_em,
            prazo_entrega_em=prazo_entrega_em,
        )