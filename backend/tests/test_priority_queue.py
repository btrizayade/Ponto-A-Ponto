
import pytest

from app.domain.models import Bairro, CategoriaProduto, Pedido
from app.domain.priority_queue import FilaPrioridade

def criar_pedido(codigo: str) -> Pedido:
    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    return Pedido(
        codigo=codigo,
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=5,
    )


def test_pedido_com_maior_prioridade_sai_primeiro() -> None:
    fila = FilaPrioridade()

    fila.adicionar(criar_pedido("PED-001"), 3)
    fila.adicionar(criar_pedido("PED-002"), 10)
    fila.adicionar(criar_pedido("PED-003"), 5)

    assert fila.retirar_proximo().codigo == "PED-002"
    assert fila.retirar_proximo().codigo == "PED-003"
    assert fila.retirar_proximo().codigo == "PED-001"


def test_empate_respeita_ordem_de_entrada() -> None:
    fila = FilaPrioridade()

    fila.adicionar(criar_pedido("PED-001"), 5)
    fila.adicionar(criar_pedido("PED-002"), 5)
    fila.adicionar(criar_pedido("PED-003"), 5)

    assert fila.retirar_proximo().codigo == "PED-001"
    assert fila.retirar_proximo().codigo == "PED-002"
    assert fila.retirar_proximo().codigo == "PED-003"


def test_consultar_proximo_nao_remove_pedido() -> None:
    fila = FilaPrioridade()
    fila.adicionar(criar_pedido("PED-001"), 5)

    assert fila.proximo().codigo == "PED-001"
    assert len(fila) == 1


def test_fila_vazia_nao_tem_proximo_pedido() -> None:
    fila = FilaPrioridade()

    assert fila.esta_vazia() is True
    assert fila.proximo() is None
    assert len(fila) == 0


def test_remover_de_fila_vazia_gera_erro() -> None:
    fila = FilaPrioridade()

    with pytest.raises(IndexError):
        fila.retirar_proximo()


def test_adicionar_pedido_calcula_prioridade_automaticamente() -> None:
    fila = FilaPrioridade()

    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    pedido_comum = Pedido(
        codigo="PED-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=10,
    )

    pedido_clube = Pedido(
        codigo="PED-002",
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=True,
        entrega_rapida=False,
        sla_dias_uteis=10,
    )

    pedido_urgente = Pedido(
        codigo="PED-003",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
    )

    fila.adicionar_pedido(pedido_comum)
    fila.adicionar_pedido(pedido_clube)
    fila.adicionar_pedido(pedido_urgente)

    assert fila.retirar_proximo().codigo == "PED-003"
    assert fila.retirar_proximo().codigo == "PED-002"
    assert fila.retirar_proximo().codigo == "PED-001"


def test_adicionar_pedido_preserva_ordem_em_empates() -> None:
    fila = FilaPrioridade()

    primeiro = criar_pedido("PED-001")
    segundo = criar_pedido("PED-002")

    fila.adicionar_pedido(primeiro)
    fila.adicionar_pedido(segundo)

    assert fila.retirar_proximo().codigo == "PED-001"
    assert fila.retirar_proximo().codigo == "PED-002"
