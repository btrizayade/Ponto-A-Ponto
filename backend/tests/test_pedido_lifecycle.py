from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.models import OrigemPedido
from fastapi.testclient import TestClient
from app.api.registro import registro
from app.infrastructure import database
from app.infrastructure.auditoria_repository import (
    listar_eventos,
    obter_simulacao,
)
from app.infrastructure.bairro_repository import listar_bairros
from app.infrastructure.cenario_repository import listar_cenarios
from app.infrastructure.pedido_factory import criar_pedido_do_formulario
from app.infrastructure.pedido_repository import (
    listar_pedidos_por_cenario,
    obter_ou_criar_pedido,
)
from app.infrastructure.seed import inicializar_todos_cenarios
from app.infrastructure.simulated_routing import ServicoRoteamentoSimulado
from app.infrastructure.simulacao_factory import criar_simulacao_auditada
from app.main import app
from app.domain.models import CategoriaProduto, ModalidadeEntrega


FUSO = ZoneInfo("America/Bahia")
INICIO = datetime(2026, 10, 30, 10, 0, tzinfo=FUSO)


@pytest.fixture
def cenario_com_banco(tmp_path, monkeypatch):
    diretorio = tmp_path / "data"
    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", diretorio / "ciclo.db")
    cenarios = inicializar_todos_cenarios()
    return {cenario.codigo: cenario for cenario in cenarios}


def cadastrar_manual(cenario_id, codigo, bairro=None):
    bairro = bairro or listar_bairros()[0]
    pedido = criar_pedido_do_formulario(
        bairro,
        CategoriaProduto.ALIMENTO,
        ModalidadeEntrega.CONVENCIONAL,
    )
    pedido.codigo = codigo
    return obter_ou_criar_pedido(
        pedido, cenario_id, origem=OrigemPedido.MANUAL
    )


def simular(cenario_id):
    simulacao, auditoria = criar_simulacao_auditada(
        cenario_id,
        INICIO,
        servico=ServicoRoteamentoSimulado(fator_transito=1.0),
    )
    simulacao.executar_ate_o_fim()
    return simulacao, auditoria


@pytest.mark.parametrize(
    ("codigo", "quantidade_referencia"),
    [("NORMAL", 10), ("EQUIDADE", 15), ("ALTA_DEMANDA", 24)],
)
def test_conclusao_remove_pedidos_manuais_mas_preserva_referencias(
    cenario_com_banco, codigo, quantidade_referencia
):
    cenario = cenario_com_banco[codigo]
    cadastrar_manual(cenario.id, "MANUAL-REMOVER")

    assert len(listar_pedidos_por_cenario(cenario.id)) == quantidade_referencia + 1
    simulacao, auditoria = simular(cenario.id)
    simulacao_id = auditoria.simulacao_id

    pedidos_ativos = listar_pedidos_por_cenario(cenario.id)
    assert len(simulacao.pedidos) == quantidade_referencia + 1
    assert len(pedidos_ativos) == quantidade_referencia
    assert {pedido.origem for pedido in pedidos_ativos} == {
        OrigemPedido.REFERENCIA
    }
    assert obter_simulacao(simulacao_id)["status"] == "concluida"
    assert any(evento.tipo.value == "simulacao_concluida"
               for evento in listar_eventos(simulacao_id))

    with database.conectar() as conexao:
        manual = conexao.execute(
            "SELECT origem, ativo FROM pedidos WHERE codigo = ?",
            ("MANUAL-REMOVER",),
        ).fetchone()
    assert tuple(manual) == ("manual", 0)

    proxima, _ = simular(cenario.id)
    assert len(proxima.pedidos) == quantidade_referencia
    assert len(listar_pedidos_por_cenario(cenario.id)) == quantidade_referencia


def test_pedido_adicionado_apos_snapshot_fica_para_proxima_simulacao(
    cenario_com_banco,
):
    normal = cenario_com_banco["NORMAL"]
    cadastrar_manual(normal.id, "MANUAL-DO-SNAPSHOT")
    simulacao, _ = criar_simulacao_auditada(
        normal.id,
        INICIO,
        servico=ServicoRoteamentoSimulado(fator_transito=1.0),
    )
    cadastrar_manual(normal.id, "MANUAL-PROXIMA-SIMULACAO")

    simulacao.executar_ate_o_fim()
    ativos = listar_pedidos_por_cenario(normal.id)
    assert len(ativos) == 11
    assert {pedido.codigo for pedido in ativos} == {
        *(f"PED-{numero:03d}" for numero in range(1, 11)),
        "MANUAL-PROXIMA-SIMULACAO",
    }


def test_limpeza_e_isolada_por_cenario_e_arquivamento_e_idempotente(
    cenario_com_banco,
):
    normal = cenario_com_banco["NORMAL"]
    equidade = cenario_com_banco["EQUIDADE"]
    cadastrar_manual(normal.id, "MANUAL-NORMAL")
    cadastrar_manual(equidade.id, "MANUAL-EQUIDADE")

    simulacao, auditoria = simular(normal.id)
    simulacao_id = auditoria.simulacao_id
    assert len(listar_pedidos_por_cenario(normal.id)) == 10
    assert len(listar_pedidos_por_cenario(equidade.id)) == 16

    # Reenviar o evento final nao duplica auditoria nem muda outros cenarios.
    eventos_antes = listar_eventos(simulacao_id)
    auditoria.registrar(simulacao.historico[-1])
    assert listar_eventos(simulacao_id) == eventos_antes
    assert len(listar_pedidos_por_cenario(normal.id)) == 10
    assert len(listar_pedidos_por_cenario(equidade.id)) == 16


def test_pausa_e_execucao_em_andamento_nao_arquivam_pedidos(
    cenario_com_banco, monkeypatch
):
    normal = cenario_com_banco["NORMAL"]
    cadastrar_manual(normal.id, "MANUAL-PAUSA")
    monkeypatch.setenv("EXECUCAO_AUTOMATICA_ATIVA", "false")
    registro.limpar()

    with TestClient(app) as cliente:
        criada = cliente.post(
            "/api/simulacoes",
            json={
                "cenario_id": normal.id,
                "inicio": INICIO.isoformat(),
                "provedor": "simulado",
            },
        )
        assert criada.status_code == 201, criada.json()
        simulacao_id = criada.json()["id"]

        etapa = cliente.post(
            f"/api/simulacoes/{simulacao_id}/proxima-etapa"
        )
        assert etapa.status_code == 200, etapa.json()
        assert len(listar_pedidos_por_cenario(normal.id)) == 11

        pausa = cliente.post(f"/api/simulacoes/{simulacao_id}/pausar")
        assert pausa.status_code == 200, pausa.json()
        assert len(listar_pedidos_por_cenario(normal.id)) == 11

        retomada = cliente.post(f"/api/simulacoes/{simulacao_id}/retomar")
        assert retomada.status_code == 200, retomada.json()
        assert len(listar_pedidos_por_cenario(normal.id)) == 11

        concluida = cliente.post(f"/api/simulacoes/{simulacao_id}/executar")
        assert concluida.status_code == 200, concluida.json()
        assert concluida.json()["estado"]["concluida"] is True
        assert len(listar_pedidos_por_cenario(normal.id)) == 10

    registro.limpar()


def test_migracao_e_seed_mantem_15_referencias_no_equidade(cenario_com_banco):
    equidade = cenario_com_banco["EQUIDADE"]
    # Simula o registro excedente do banco legado anterior (seed de 16).
    with database.conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO pedidos (
                codigo, cenario_id, bairro_id, categoria_produto,
                cliente_clube, entrega_rapida, sla_dias_uteis, peso_kg,
                volume_l, tempo_servico_min, criado_em, prazo_entrega_em,
                status
            )
            SELECT
                'EQ-016', cenario_id, bairro_id, categoria_produto,
                cliente_clube, entrega_rapida, sla_dias_uteis, peso_kg,
                volume_l, tempo_servico_min, criado_em, prazo_entrega_em,
                status
            FROM pedidos
            WHERE cenario_id = ? AND codigo = 'EQ-015'
            """,
            (equidade.id,),
        )

    database.inicializar_banco()
    with database.conectar() as conexao:
        legado = conexao.execute(
            "SELECT origem, ativo FROM pedidos WHERE codigo = 'EQ-016'"
        ).fetchone()
    assert tuple(legado) == ("referencia", 0)

    pedidos = listar_pedidos_por_cenario(equidade.id)
    assert len(pedidos) == 15
    assert all(pedido.origem == OrigemPedido.REFERENCIA for pedido in pedidos)
    assert len({pedido.bairro.id for pedido in pedidos}) == 8
    assert equidade.descricao.startswith("15 pedidos próprios")

    inicializar_todos_cenarios()
    assert len(listar_pedidos_por_cenario(equidade.id)) == 15
