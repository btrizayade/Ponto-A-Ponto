"""Valores operacionais para pedidos criados a partir do formulario."""

from datetime import datetime
from uuid import uuid4

from app.domain.models import (
    Bairro,
    CategoriaProduto,
    ModalidadeEntrega,
    Pedido,
)
from app.domain.sla import FUSO_HORARIO


# Perfis reaproveitam combinações de peso, volume e serviço já usadas
# pelos pedidos de referência dos cenários.
PERFIL_CATEGORIA = {
    CategoriaProduto.ALIMENTO: (2.5, 5.0, 8),
    CategoriaProduto.MEDICAMENTO: (1.2, 2.0, 7),
    CategoriaProduto.ROUPA: (1.0, 4.0, 5),
    CategoriaProduto.ELETRONICO: (3.0, 8.0, 10),
    CategoriaProduto.OUTRO: (0.5, 1.0, 5),
}
SLA_MODALIDADE_DIAS_UTEIS: dict[ModalidadeEntrega, int] = {
    ModalidadeEntrega.ENTREGA_RAPIDA: 1,
    ModalidadeEntrega.CLUBE: 3,
    # PED-002 e PED-010 usam modalidade convencional com SLA de cinco dias.
    ModalidadeEntrega.CONVENCIONAL: 5,
}


def criar_pedido_do_formulario(
    bairro: Bairro,
    categoria: CategoriaProduto,
    modalidade: ModalidadeEntrega,
) -> Pedido:
    """Gera código e dados operacionais sem exigir campos técnicos no UI."""

    peso_kg, volume_l, tempo_servico_min = PERFIL_CATEGORIA[categoria]
    entrega_rapida = modalidade == ModalidadeEntrega.ENTREGA_RAPIDA
    cliente_clube = modalidade == ModalidadeEntrega.CLUBE

    return Pedido(
        codigo=f"PED-MAN-{uuid4().hex.upper()}",
        bairro=bairro,
        categoria_produto=categoria,
        cliente_clube=cliente_clube,
        entrega_rapida=entrega_rapida,
        sla_dias_uteis=SLA_MODALIDADE_DIAS_UTEIS[modalidade],
        criado_em=datetime.now(FUSO_HORARIO),
        peso_kg=peso_kg,
        volume_l=volume_l,
        tempo_servico_min=tempo_servico_min,
    )
