
import sqlite3

from app.domain.models import Pedido, StatusPedido
from app.infrastructure.database import conectar


def obter_ou_criar_pedido(pedido: Pedido, cenario_id: int) -> Pedido:
    """Retorna um pedido existente ou cadastra um novo."""

    if pedido.bairro.id is None:
        raise ValueError("O bairro deve ser cadastrado antes do pedido.")

    try:
        with conectar() as conexao:
            conexao.execute(
                """
                INSERT INTO pedidos (
                    codigo,
                    cenario_id,
                    bairro_id,
                    categoria_produto,
                    cliente_clube,
                    entrega_rapida,
                    sla_dias_uteis,
                    peso_kg,
                    volume_l,
                    tempo_servico_min,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cenario_id, codigo) DO NOTHING
                """,
                (
                    pedido.codigo.strip(),
                    cenario_id,
                    pedido.bairro.id,
                    pedido.categoria_produto.value,
                    int(pedido.cliente_clube),
                    int(pedido.entrega_rapida),
                    pedido.sla_dias_uteis,
                    pedido.peso_kg,
                    pedido.volume_l,
                    pedido.tempo_servico_min,
                    StatusPedido.PENDENTE.value,
                ),
            )

            registro = conexao.execute(
                """
                SELECT id
                FROM pedidos
                WHERE cenario_id = ? AND codigo = ?
                """,
                (cenario_id, pedido.codigo.strip()),
            ).fetchone()

    except sqlite3.IntegrityError as erro:
        raise ValueError(
            "Não foi possível cadastrar o pedido. "
            "Verifique os dados inseridos e tente novamente."
        ) from erro

    if registro is None:
        raise RuntimeError("Não foi possível recuperar o pedido.")

    pedido.id = registro["id"]
    return pedido
