
import pytest

from datetime import datetime, timedelta, timezone

from app.domain.models import Bairro, CategoriaProduto, Pedido
from app.domain.priority_queue import FilaPrioridadeHeap
from app.domain.priority_scoring import calcular_prioridade


DATA_BASE = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def criar_pedido(
    codigo: str,
    *,
    criado_em: datetime = DATA_BASE,
    prazo_entrega_em: datetime | None = None,
    id: int | None = None,
) -> Pedido:
    bairro = Bairro(
        nome="Comercio",
        latitude=-12.963,
        longitude=-38.507,
    )

    return Pedido(
        id=id,
        codigo=codigo,
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=5,
        criado_em=criado_em,
        prazo_entrega_em=prazo_entrega_em,
    )


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


def test_pedido_com_maior_prioridade_sai_primeiro() -> None:
    fila = FilaPrioridadeHeap()

    fila.adicionar(criar_pedido("PED-001"), 3)
    fila.adicionar(criar_pedido("PED-002"), 10)
    fila.adicionar(criar_pedido("PED-003"), 5)

    assert fila.retirar_proximo().codigo == "PED-002"
    assert fila.retirar_proximo().codigo == "PED-003"
    assert fila.retirar_proximo().codigo == "PED-001"


def test_desempate_prioriza_prazo_mais_proximo() -> None:
    fila = FilaPrioridadeHeap()

    prazo_distante = DATA_BASE + timedelta(hours=5)
    prazo_proximo = DATA_BASE + timedelta(hours=2)

    pedido_distante = criar_pedido(
        "PED-001",
        prazo_entrega_em=prazo_distante,
    )

    pedido_proximo = criar_pedido(
        "PED-002",
        prazo_entrega_em=prazo_proximo,
    )

    fila.adicionar(pedido_distante, 10, agora=DATA_BASE)
    fila.adicionar(pedido_proximo, 10, agora=DATA_BASE)

    assert fila.retirar_proximo().codigo == "PED-002"
    assert fila.retirar_proximo().codigo == "PED-001"


def test_desempate_prioriza_pedido_criado_mais_antigamente() -> None:
    fila = FilaPrioridadeHeap()

    prazo = DATA_BASE + timedelta(hours=8)

    pedido_antigo = criar_pedido(
        "PED-ANTIGO",
        criado_em=DATA_BASE - timedelta(hours=5),
        prazo_entrega_em=prazo,
    )

    pedido_novo = criar_pedido(
        "PED-NOVO",
        criado_em=DATA_BASE - timedelta(hours=2),
        prazo_entrega_em=prazo,
    )

    # O pedido mais novo entra primeiro.
    fila.adicionar(pedido_novo, 10, agora=DATA_BASE)
    fila.adicionar(pedido_antigo, 10, agora=DATA_BASE)

    assert fila.retirar_proximo().codigo == "PED-ANTIGO"
    assert fila.retirar_proximo().codigo == "PED-NOVO"


def test_desempate_prioriza_identificador_menor() -> None:
    fila = FilaPrioridadeHeap()

    pedido_id_maior = criar_pedido(
        "PED-001",
        id=20,
    )

    pedido_id_menor = criar_pedido(
        "PED-002",
        id=10,
    )

    fila.adicionar(pedido_id_maior, 10)
    fila.adicionar(pedido_id_menor, 10)

    assert fila.retirar_proximo().id == 10
    assert fila.retirar_proximo().id == 20


def test_desempate_por_codigo_quando_nao_existe_id() -> None:
    fila = FilaPrioridadeHeap()

    segundo = criar_pedido("PED-002")
    primeiro = criar_pedido("PED-001")

    # A ordem de insercao e diferente da ordem dos codigos.
    fila.adicionar(segundo, 10)
    fila.adicionar(primeiro, 10)

    assert fila.retirar_proximo().codigo == "PED-001"
    assert fila.retirar_proximo().codigo == "PED-002"


def test_consultar_proximo_nao_remove_pedido() -> None:
    fila = FilaPrioridadeHeap()
    fila.adicionar(criar_pedido("PED-001"), 5)

    assert fila.proximo().codigo == "PED-001"
    assert len(fila) == 1


def test_fila_vazia_nao_tem_proximo_pedido() -> None:
    fila = FilaPrioridadeHeap()

    assert fila.esta_vazia() is True
    assert fila.proximo() is None
    assert len(fila) == 0


def test_remover_de_fila_vazia_gera_erro() -> None:
    fila = FilaPrioridadeHeap()

    with pytest.raises(IndexError):
        fila.retirar_proximo()


def test_adicionar_pedido_calcula_prioridade_automaticamente() -> None:
    fila = FilaPrioridadeHeap()

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
        criado_em=DATA_BASE,
    )

    pedido_clube = Pedido(
        codigo="PED-002",
        bairro=bairro,
        categoria_produto=CategoriaProduto.OUTRO,
        cliente_clube=True,
        entrega_rapida=False,
        sla_dias_uteis=10,
        criado_em=DATA_BASE,
    )

    pedido_urgente = Pedido(
        codigo="PED-003",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
        criado_em=DATA_BASE,
    )

    fila.adicionar_pedido(pedido_comum, agora=DATA_BASE)
    fila.adicionar_pedido(pedido_clube, agora=DATA_BASE)
    fila.adicionar_pedido(pedido_urgente, agora=DATA_BASE)

    assert fila.retirar_proximo().codigo == "PED-003"
    assert fila.retirar_proximo().codigo == "PED-002"
    assert fila.retirar_proximo().codigo == "PED-001"


def test_fila_atualiza_prioridade_com_passagem_do_tempo() -> None:
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

    fila = FilaPrioridadeHeap()

    fila.adicionar_pedido(pedido_antigo, agora=agora)
    fila.adicionar_pedido(pedido_urgente, agora=agora)

    assert fila.proximo().codigo == "PED-ANTIGO"

    novo_momento = agora + timedelta(hours=24)

    # A atualizacao temporal agora e explicita.
    fila.atualizar_prioridades(agora=novo_momento)

    assert fila.proximo().codigo == "PED-URGENTE"
    assert len(fila) == 2


def test_fila_preserva_desempate_apos_atualizacao() -> None:
    agora = DATA_BASE

    pedido_id_maior = criar_pedido(
        "PED-001",
        id=20,
    )

    pedido_id_menor = criar_pedido(
        "PED-002",
        id=10,
    )

    fila = FilaPrioridadeHeap()

    fila.adicionar_pedido(pedido_id_maior, agora=agora)
    fila.adicionar_pedido(pedido_id_menor, agora=agora)

    fila.atualizar_prioridades(
        agora=agora + timedelta(hours=12)
    )

    assert fila.retirar_proximo().id == 10
    assert fila.retirar_proximo().id == 20


def test_atualizar_estimativa_entrega_altera_ordem_da_fila() -> None:
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

    fila = FilaPrioridadeHeap()

    fila.adicionar_pedido(
        pedido_transito,
        agora=agora,
        tempo_estimado_entrega_min=30,
    )

    fila.adicionar_pedido(
        pedido_antigo,
        agora=agora,
    )

    assert fila.proximo().codigo == "PED-ANTIGO"

    fila.atualizar_estimativa_entrega(
        pedido_transito,
        tempo_estimado_entrega_min=300,
        agora=agora,
    )

    assert fila.proximo().codigo == "PED-TRANSITO"


def test_entrada_antiga_nao_provoca_despacho_duplicado() -> None:
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

    fila = FilaPrioridadeHeap()

    fila.adicionar_pedido(
        pedido_transito,
        agora=agora,
        tempo_estimado_entrega_min=30,
    )

    fila.adicionar_pedido(
        pedido_antigo,
        agora=agora,
    )

    # A atualizacao cria uma nova entrada para o pedido.
    fila.atualizar_estimativa_entrega(
        pedido_transito,
        tempo_estimado_entrega_min=300,
        agora=agora,
    )

    assert fila.proximo().codigo == "PED-TRANSITO"

    # A entrada atual deve ser retirada somente uma vez.
    assert fila.retirar_proximo().codigo == "PED-TRANSITO"

    # A entrada antiga deve ser descartada.
    assert fila.retirar_proximo().codigo == "PED-ANTIGO"

    assert fila.esta_vazia() is True

    with pytest.raises(IndexError):
        fila.retirar_proximo()


def test_nao_permite_adicionar_pedido_que_ja_esta_na_fila() -> None:
    fila = FilaPrioridadeHeap()
    pedido = criar_pedido("PED-001")

    fila.adicionar(pedido, 10)

    with pytest.raises(ValueError, match="ja esta na fila"):
        fila.adicionar(pedido, 15)

    assert len(fila) == 1


def test_nao_permite_reinserir_pedido_ja_retirado() -> None:
    fila = FilaPrioridadeHeap()
    pedido = criar_pedido("PED-001")

    fila.adicionar(pedido, 10)

    assert fila.retirar_proximo().codigo == "PED-001"

    with pytest.raises(ValueError, match="ja foi processado"):
        fila.adicionar(pedido, 15)

    assert fila.esta_vazia() is True


def test_atualizar_estimativa_rejeita_prioridade_manual() -> None:
    agora = DATA_BASE

    pedido = criar_pedido_para_teste_fila(
        "PED-MANUAL",
        agora,
    )

    fila = FilaPrioridadeHeap()
    fila.adicionar(pedido, prioridade=10)

    with pytest.raises(ValueError, match="prioridade manual"):
        fila.atualizar_estimativa_entrega(
            pedido,
            tempo_estimado_entrega_min=30,
            agora=agora,
        )


def test_atualizar_estimativa_rejeita_pedido_ausente() -> None:
    agora = DATA_BASE

    pedido = criar_pedido_para_teste_fila(
        "PED-AUSENTE",
        agora,
    )

    fila = FilaPrioridadeHeap()

    with pytest.raises(ValueError, match="nao encontrado"):
        fila.atualizar_estimativa_entrega(
            pedido,
            tempo_estimado_entrega_min=30,
            agora=agora,
        )

def test_desempate_prioriza_menor_folga_sla_com_estimativa() -> None:
    agora = DATA_BASE
    criado_em = agora - timedelta(hours=8)

    pedido_menor_folga = criar_pedido(
        "PED-MENOR-FOLGA",
        criado_em=criado_em,
        prazo_entrega_em=agora + timedelta(hours=2),
    )

    pedido_maior_folga = criar_pedido(
        "PED-MAIOR-FOLGA",
        criado_em=criado_em,
        prazo_entrega_em=agora + timedelta(hours=1),
    )

    eta_menor_folga = 110
    eta_maior_folga = 40

    prioridade_a = calcular_prioridade(
        pedido_menor_folga,
        agora=agora,
        tempo_estimado_entrega_min=eta_menor_folga,
    )

    prioridade_b = calcular_prioridade(
        pedido_maior_folga,
        agora=agora,
        tempo_estimado_entrega_min=eta_maior_folga,
    )

    # Ambos devem possuir a mesma prioridade efetiva.
    assert prioridade_a == prioridade_b

    fila = FilaPrioridadeHeap()

    fila.adicionar_pedido(
        pedido_menor_folga,
        agora=agora,
        tempo_estimado_entrega_min=eta_menor_folga,
    )

    fila.adicionar_pedido(
        pedido_maior_folga,
        agora=agora,
        tempo_estimado_entrega_min=eta_maior_folga,
    )

    # O primeiro possui apenas 10 minutos de folga.
    # O segundo possui 20 minutos de folga.
    # Mesmo com prazo mais distante, o primeiro deve sair antes.
    assert fila.retirar_proximo().codigo == "PED-MENOR-FOLGA"
    assert fila.retirar_proximo().codigo == "PED-MAIOR-FOLGA"

def test_compactacao_remove_entradas_obsoletas_sem_perder_pedidos() -> None:
    agora = DATA_BASE

    pedido_atualizado = criar_pedido_para_teste_fila(
        "PED-ATUALIZADO",
        agora,
        urgente=True,
    )
    pedido_atualizado.prazo_entrega_em = (
        agora + timedelta(hours=5)
    )

    pedido_outro = criar_pedido_para_teste_fila(
        "PED-OUTRO",
        agora,
    )

    fila = FilaPrioridadeHeap()

    fila.adicionar_pedido(
        pedido_atualizado,
        agora=agora,
        tempo_estimado_entrega_min=30,
    )

    fila.adicionar_pedido(
        pedido_outro,
        agora=agora,
    )

    # Atualizacoes sucessivas criam entradas obsoletas.
    for _ in range(63):
        fila.atualizar_estimativa_entrega(
            pedido_atualizado,
            tempo_estimado_entrega_min=30,
            agora=agora,
        )

    # A compactacao deve manter somente as entradas atuais.
    assert len(fila._itens) == 2
    assert len(fila) == 2

    # Os dois pedidos continuam presentes e ordenados corretamente.
    assert fila.proximo().codigo == "PED-ATUALIZADO"

    assert fila.retirar_proximo().codigo == "PED-ATUALIZADO"
    assert fila.retirar_proximo().codigo == "PED-OUTRO"

    assert fila.esta_vazia()
