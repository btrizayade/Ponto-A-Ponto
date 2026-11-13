from collections import Counter

import pytest

from app.infrastructure import database
from app.infrastructure.bairro_repository import listar_bairros
from app.infrastructure.cenario_repository import listar_cenarios
from app.infrastructure.pedido_repository import listar_pedidos_por_cenario
from app.infrastructure.seed import (
    inicializar_bairros_cenario_01,
    inicializar_cenario_01,
    inicializar_pedidos_cenario_01,
    inicializar_todos_cenarios,
)


@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "teste.db")
    database.inicializar_banco()


def _snapshot_pedidos(cenario_id):
    with database.conectar() as conexao:
        return [
            tuple(registro)
            for registro in conexao.execute(
                """
                SELECT id, codigo, cenario_id, bairro_id, categoria_produto,
                       cliente_clube, entrega_rapida, sla_dias_uteis,
                       criado_em, prazo_entrega_em, peso_kg, volume_l,
                       tempo_servico_min, status
                FROM pedidos
                WHERE cenario_id = ?
                ORDER BY id
                """,
                (cenario_id,),
            )
        ]


def test_seed_cadastra_tres_cenarios_com_pedidos_por_bairro(
    banco_temporario,
):
    cenarios = inicializar_todos_cenarios()
    por_codigo = {cenario.codigo: cenario for cenario in cenarios}

    assert set(por_codigo) == {"NORMAL", "ALTA_DEMANDA", "EQUIDADE"}
    assert por_codigo["ALTA_DEMANDA"].nome == (
        "Alta Demanda e Trânsito Intenso"
    )
    assert por_codigo["EQUIDADE"].nome == "Distribuição com Equidade"
    assert len(listar_bairros()) == 8

    quantidades = {"NORMAL": 10, "ALTA_DEMANDA": 24, "EQUIDADE": 15}
    for codigo, quantidade in quantidades.items():
        pedidos = listar_pedidos_por_cenario(por_codigo[codigo].id)
        assert len(pedidos) == quantidade
        assert len({pedido.codigo for pedido in pedidos}) == quantidade

    pedidos_alta = listar_pedidos_por_cenario(
        por_codigo["ALTA_DEMANDA"].id
    )
    pedidos_equidade = listar_pedidos_por_cenario(por_codigo["EQUIDADE"].id)

    assert set(Counter(p.bairro.nome for p in pedidos_alta).values()) == {3}
    assert Counter(Counter(p.bairro.nome for p in pedidos_equidade).values()) == {
        2: 7,
        1: 1,
    }
    assert Counter(p.bairro.nome for p in pedidos_equidade)["Pernambues"] == 1
    assert not {p.codigo for p in pedidos_alta} & {
        p.codigo for p in pedidos_equidade
    }


def test_seed_e_idempotente_e_preserva_integralmente_normal(
    banco_temporario,
):
    normal = inicializar_cenario_01()
    bairros = inicializar_bairros_cenario_01()
    inicializar_pedidos_cenario_01(normal, bairros)
    pedidos_normal_antes = _snapshot_pedidos(normal.id)

    inicializar_todos_cenarios()
    snapshot_primeira_execucao = {
        cenario.codigo: _snapshot_pedidos(cenario.id)
        for cenario in listar_cenarios()
    }
    inicializar_todos_cenarios()

    cenarios = listar_cenarios()
    assert len(cenarios) == 3
    assert len(listar_bairros()) == 8
    assert _snapshot_pedidos(normal.id) == pedidos_normal_antes
    assert {
        cenario.codigo: _snapshot_pedidos(cenario.id)
        for cenario in cenarios
    } == snapshot_primeira_execucao


def test_pedidos_novos_tem_atributos_variados_e_datas_deterministicas(
    banco_temporario,
):
    cenarios = {c.codigo: c for c in inicializar_todos_cenarios()}

    for codigo in ("ALTA_DEMANDA", "EQUIDADE"):
        pedidos = listar_pedidos_por_cenario(cenarios[codigo].id)
        assert len({p.categoria_produto for p in pedidos}) > 1
        assert len({p.sla_dias_uteis for p in pedidos}) > 1
        assert len({p.peso_kg for p in pedidos}) > 1
        assert len({p.volume_l for p in pedidos}) > 1
        assert len({p.criado_em for p in pedidos}) == len(pedidos)
        assert all(p.prazo_entrega_em > p.criado_em for p in pedidos)
