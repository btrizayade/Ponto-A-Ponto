
import pytest

from datetime import datetime, timedelta, timezone
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

def criar_pedido_para_teste_fila(
    codigo: str,
    criado_em: datetime,
    urgente: bool = False,
) -> Pedido:
    """Cria pedidos para testar a atualizacao dinamica da fila."""

    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    if urgente:
        categoria = CategoriaProduto.MEDICAMENTO
        cliente_clube = True
        entrega_rapida = True
        sla = 1
    else:
        categoria = CategoriaProduto.OUTRO
        cliente_clube = False
        entrega_rapida = False
        sla = 10

    return Pedido(
        codigo=codigo,
        bairro=bairro,
        categoria_produto=categoria,
        cliente_clube=cliente_clube,
        entrega_rapida=entrega_rapida,
        sla_dias_uteis=sla,
        criado_em=criado_em,
    )


def test_fila_atualiza_prioridade_com_passagem_do_tempo():
    agora = datetime(
        2026, 10, 29, 12, 0, tzinfo=timezone.utc
    )

    pedido_antigo = criar_pedido_para_teste_fila(
        "PED-ANTIGO",
        agora - timedelta(hours=80),
    )

    pedido_urgente = criar_pedido_para_teste_fila(
        "PED-URGENTE",
        agora,
        urgente=True,
    )

    fila = FilaPrioridade()

    fila.adicionar_pedido(pedido_antigo, agora=agora)
    fila.adicionar_pedido(pedido_urgente, agora=agora)

    # Inicialmente, o aging faz o pedido antigo ter maior prioridade.
    assert fila.proximo(agora=agora).codigo == "PED-ANTIGO"

    # Depois de 24 horas, o pedido urgente acumula mais pontos.
    novo_momento = agora + timedelta(hours=24)

    assert fila.proximo(agora=novo_momento).codigo == "PED-URGENTE"

    # Consultar o proximo pedido nao deve remover elementos.
    assert len(fila) == 2


def test_fila_preserva_ordem_de_entrada_apos_atualizacao():
    agora = datetime(
        2026, 10, 29, 12, 0, tzinfo=timezone.utc
    )

    primeiro = criar_pedido_para_teste_fila(
        "PED-PRIMEIRO",
        agora,
    )

    segundo = criar_pedido_para_teste_fila(
        "PED-SEGUNDO",
        agora,
    )

    fila = FilaPrioridade()

    fila.adicionar_pedido(primeiro, agora=agora)
    fila.adicionar_pedido(segundo, agora=agora)

    fila.atualizar_prioridades(
        agora=agora + timedelta(hours=12)
    )

    assert fila.retirar_proximo(
        agora=agora + timedelta(hours=12)
    ).codigo == "PED-PRIMEIRO"

    assert fila.retirar_proximo(
        agora=agora + timedelta(hours=12)
    ).codigo == "PED-SEGUNDO"

def test_atualizar_estimativa_entrega_altera_ordem_da_fila():
    agora = datetime(
        2026, 10, 30, 12, 0, tzinfo=timezone.utc
    )

    pedido_transito = criar_pedido_para_teste_fila(
        "PED-TRANSITO",
        agora,
        urgente=True,
    )

    pedido_transito.prazo_entrega_em = (
        agora + timedelta(minutes=300)
    )

    pedido_antigo = criar_pedido_para_teste_fila(
        "PED-ANTIGO",
        agora - timedelta(hours=24),
        urgente=True,
    )

    fila = FilaPrioridade()

    fila.adicionar_pedido(
        pedido_transito,
        agora=agora,
        tempo_estimado_entrega_min=30,
    )

    fila.adicionar_pedido(
        pedido_antigo,
        agora=agora,
    )

    # Inicialmente, o pedido antigo tem maior prioridade.
    assert fila.proximo(agora=agora).codigo == "PED-ANTIGO"

    # O transito piora e a estimativa aumenta para 300 minutos.
    fila.atualizar_estimativa_entrega(
        pedido_transito,
        tempo_estimado_entrega_min=300,
        agora=agora,
    )

    # O risco de SLA aumenta e altera a ordem.
    assert fila.proximo(agora=agora).codigo == "PED-TRANSITO"


def test_atualizar_estimativa_rejeita_prioridade_manual():
    agora = datetime(
        2026, 10, 30, 12, 0, tzinfo=timezone.utc
    )

    pedido = criar_pedido_para_teste_fila(
        "PED-MANUAL",
        agora,
    )

    fila = FilaPrioridade()
    fila.adicionar(pedido, prioridade=10)

    with pytest.raises(ValueError, match="prioridade manual"):
        fila.atualizar_estimativa_entrega(
            pedido,
            tempo_estimado_entrega_min=30,
            agora=agora,
        )


def test_atualizar_estimativa_rejeita_pedido_ausente():
    agora = datetime(
        2026, 10, 30, 12, 0, tzinfo=timezone.utc
    )

    pedido = criar_pedido_para_teste_fila(
        "PED-AUSENTE",
        agora,
    )

    fila = FilaPrioridade()

    with pytest.raises(ValueError, match="nao encontrado"):
        fila.atualizar_estimativa_entrega(
            pedido,
            tempo_estimado_entrega_min=30,
            agora=agora,
        )
