import sqlite3
from datetime import datetime

from app.domain.models import Bairro, CategoriaProduto, Pedido, StatusPedido
from app.domain.sla import calcular_prazo_entrega
from app.infrastructure.database import conectar


COLUNAS_PEDIDO = """
    p.id AS pedido_id,
    p.codigo,
    p.categoria_produto,
    p.cliente_clube,
    p.entrega_rapida,
    p.sla_dias_uteis,
    p.peso_kg,
    p.volume_l,
    p.tempo_servico_min,
    p.criado_em,
    p.prazo_entrega_em,
    b.id AS bairro_id,
    b.nome AS bairro_nome,
    b.latitude,
    b.longitude
"""


def _buscar_registro_pedido(
    conexao: sqlite3.Connection,
    cenario_id: int,
    codigo: str,
) -> sqlite3.Row | None:
    """Busca um pedido persistido com seus dados de bairro."""

    return conexao.execute(
        f"""
        SELECT {COLUNAS_PEDIDO}
        FROM pedidos AS p
        INNER JOIN bairros AS b ON b.id = p.bairro_id
        WHERE p.cenario_id = ? AND p.codigo = ?
        """,
        (cenario_id, codigo),
    ).fetchone()


def _criar_pedido_do_registro(
    registro: sqlite3.Row,
) -> Pedido:
    """Converte um registro do banco em um objeto Pedido."""

    bairro = Bairro(
        id=registro["bairro_id"],
        nome=registro["bairro_nome"],
        latitude=registro["latitude"],
        longitude=registro["longitude"],
    )

    return Pedido(
        id=registro["pedido_id"],
        codigo=registro["codigo"],
        bairro=bairro,
        categoria_produto=CategoriaProduto(
            registro["categoria_produto"]
        ),
        cliente_clube=bool(registro["cliente_clube"]),
        entrega_rapida=bool(registro["entrega_rapida"]),
        sla_dias_uteis=registro["sla_dias_uteis"],
        peso_kg=registro["peso_kg"],
        volume_l=registro["volume_l"],
        tempo_servico_min=registro["tempo_servico_min"],
        criado_em=datetime.fromisoformat(registro["criado_em"]),
        prazo_entrega_em=(
            datetime.fromisoformat(registro["prazo_entrega_em"])
            if registro["prazo_entrega_em"] is not None
            else None
        ),
    )


def _sincronizar_pedido(
    destino: Pedido,
    origem: Pedido,
) -> None:
    """Atualiza o objeto recebido com os dados persistidos."""

    destino.id = origem.id
    destino.codigo = origem.codigo
    destino.bairro = origem.bairro
    destino.categoria_produto = origem.categoria_produto
    destino.cliente_clube = origem.cliente_clube
    destino.entrega_rapida = origem.entrega_rapida
    destino.sla_dias_uteis = origem.sla_dias_uteis
    destino.peso_kg = origem.peso_kg
    destino.volume_l = origem.volume_l
    destino.tempo_servico_min = origem.tempo_servico_min
    destino.criado_em = origem.criado_em
    destino.prazo_entrega_em = origem.prazo_entrega_em


def obter_ou_criar_pedido(
    pedido: Pedido,
    cenario_id: int,
) -> Pedido:
    """Retorna um pedido existente ou cadastra um novo."""

    if pedido.bairro.id is None:
        raise ValueError("O bairro deve ser cadastrado antes do pedido.")

    codigo = pedido.codigo.strip()

    try:
        with conectar() as conexao:
            registro = _buscar_registro_pedido(
                conexao,
                cenario_id,
                codigo,
            )

            if registro is None:
                if pedido.prazo_entrega_em is None:
                    pedido.prazo_entrega_em = calcular_prazo_entrega(
                        pedido.criado_em,
                        pedido.sla_dias_uteis,
                    )

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
                        criado_em,
                        prazo_entrega_em,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cenario_id, codigo) DO NOTHING
                    """,
                    (
                        codigo,
                        cenario_id,
                        pedido.bairro.id,
                        pedido.categoria_produto.value,
                        int(pedido.cliente_clube),
                        int(pedido.entrega_rapida),
                        pedido.sla_dias_uteis,
                        pedido.peso_kg,
                        pedido.volume_l,
                        pedido.tempo_servico_min,
                        pedido.criado_em.isoformat(),
                        pedido.prazo_entrega_em.isoformat(),
                        StatusPedido.PENDENTE.value,
                    ),
                )

                # Recupera os dados efetivamente armazenados.
                registro = _buscar_registro_pedido(
                    conexao,
                    cenario_id,
                    codigo,
                )

    except sqlite3.IntegrityError as erro:
        raise ValueError(
            "Nao foi possivel cadastrar o pedido. "
            "Verifique os dados inseridos e tente novamente."
        ) from erro

    if registro is None:
        raise RuntimeError("Nao foi possivel recuperar o pedido.")

    pedido_persistido = _criar_pedido_do_registro(registro)

    _sincronizar_pedido(pedido, pedido_persistido)

    return pedido


def listar_pedidos_por_cenario(
    cenario_id: int,
) -> list[Pedido]:
    """Recupera os pedidos de um cenario com seus bairros."""

    with conectar() as conexao:
        registros = conexao.execute(
            f"""
            SELECT {COLUNAS_PEDIDO}
            FROM pedidos AS p
            INNER JOIN bairros AS b ON b.id = p.bairro_id
            WHERE p.cenario_id = ?
            ORDER BY p.id
            """,
            (cenario_id,),
        ).fetchall()

    return [
        _criar_pedido_do_registro(registro)
        for registro in registros
    ]
