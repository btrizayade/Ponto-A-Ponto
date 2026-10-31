
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.domain.models import Bairro, CategoriaProduto, Cenario, Pedido
from app.infrastructure import database
from app.infrastructure.bairro_repository import (
    listar_bairros,
    obter_ou_criar_bairro,
)
from app.infrastructure.cenario_repository import (
    listar_cenarios,
    obter_ou_criar_cenario,
)
from app.infrastructure.pedido_repository import (
    listar_pedidos_por_cenario,
    obter_ou_criar_pedido,
)

@pytest.fixture
def banco_temporario(tmp_path, monkeypatch):
    """Prepara um banco isolado para cada teste."""

    diretorio = tmp_path / "data"
    caminho_banco = diretorio / "teste.db"

    monkeypatch.setattr(database, "DATABASE_DIR", diretorio)
    monkeypatch.setattr(database, "DATABASE_PATH", caminho_banco)

    database.inicializar_banco()


def test_cenario_nao_e_duplicado(banco_temporario):
    cenario = Cenario(
        codigo="TESTE",
        nome="Cenario de teste",
    )

    primeiro = obter_ou_criar_cenario(cenario)
    segundo = obter_ou_criar_cenario(cenario)

    assert primeiro.id == segundo.id
    assert len(listar_cenarios()) == 1


def test_bairro_nao_e_duplicado(banco_temporario):
    bairro = Bairro(
        nome="Bairro de teste",
        latitude=-12.963,
        longitude=-38.507,
    )

    primeiro = obter_ou_criar_bairro(bairro)
    segundo = obter_ou_criar_bairro(bairro)

    assert primeiro.id == segundo.id
    assert len(listar_bairros()) == 1


def test_pedido_nao_e_duplicado(banco_temporario):
    cenario = obter_ou_criar_cenario(
        Cenario(
            codigo="NORMAL",
            nome="Operacao normal",
        )
    )

    bairro = obter_ou_criar_bairro(
        Bairro(
            nome="Comercio",
            latitude=-12.963,
            longitude=-38.507,
        )
    )

    pedido = Pedido(
        codigo="PED-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
    )

    primeiro = obter_ou_criar_pedido(pedido, cenario.id)
    segundo = obter_ou_criar_pedido(pedido, cenario.id)

    assert primeiro.id == segundo.id

    with database.conectar() as conexao:
        registros = conexao.execute(
            """
            SELECT id, status
            FROM pedidos
            WHERE cenario_id = ? AND codigo = ?
            """,
            (cenario.id, "PED-001"),
        ).fetchall()

    assert len(registros) == 1
    assert registros[0]["status"] == "pendente"


def test_listar_pedidos_por_cenario_recupera_dados(banco_temporario):
    cenario = obter_ou_criar_cenario(
        Cenario(
            codigo="NORMAL",
            nome="Operacao normal",
        )
    )

    bairro = obter_ou_criar_bairro(
        Bairro(
            nome="Comercio",
            latitude=-12.963,
            longitude=-38.507,
        )
    )

    criado_em = datetime(
        2026, 10, 29, 12, 0, tzinfo=timezone.utc
    )

    prazo_entrega_em = datetime(
        2026, 10, 30, 18, 0, tzinfo=timezone.utc
    )

    pedido = Pedido(
        codigo="PED-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
        criado_em=criado_em,
        prazo_entrega_em=prazo_entrega_em,
    )

    obter_ou_criar_pedido(pedido, cenario.id)

    pedidos = listar_pedidos_por_cenario(cenario.id)

    assert len(pedidos) == 1

    recuperado = pedidos[0]

    assert recuperado.codigo == "PED-001"
    assert recuperado.bairro.nome == "Comercio"
    assert recuperado.categoria_produto == CategoriaProduto.MEDICAMENTO
    assert recuperado.cliente_clube is True
    assert recuperado.entrega_rapida is True
    assert recuperado.sla_dias_uteis == 1
    assert recuperado.criado_em == criado_em
    assert recuperado.prazo_entrega_em == prazo_entrega_em


def test_cadastro_pedido_calcula_e_persiste_prazo(banco_temporario):
    cenario = obter_ou_criar_cenario(
        Cenario(codigo="NORMAL", nome="Operacao normal")
    )

    bairro = obter_ou_criar_bairro(
        Bairro(nome="Comercio", latitude=-12.963, longitude=-38.507)
    )

    criado_em = datetime(
        2026, 10, 26, 13, 0, tzinfo=timezone.utc
    )

    pedido = Pedido(
        codigo="PED-SLA-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
        criado_em=criado_em,
    )

    obter_ou_criar_pedido(pedido, cenario.id)

    esperado = datetime(
        2026, 10, 27, 10, 0,
        tzinfo=ZoneInfo("America/Bahia"),
    )

    assert pedido.prazo_entrega_em == esperado

    recuperados = listar_pedidos_por_cenario(cenario.id)

    assert len(recuperados) == 1
    assert recuperados[0].prazo_entrega_em == esperado

def test_pedido_duplicado_retorna_dados_ja_persistidos(banco_temporario):
    cenario = obter_ou_criar_cenario(
        Cenario(
            codigo="NORMAL",
            nome="Operacao normal",
        )
    )

    bairro = obter_ou_criar_bairro(
        Bairro(
            nome="Comercio",
            latitude=-12.963,
            longitude=-38.507,
        )
    )

    criado_em_original = datetime(
        2026, 10, 26, 13, 0,
        tzinfo=ZoneInfo("America/Bahia"),
    )

    pedido_original = Pedido(
        codigo="PED-DUP-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.MEDICAMENTO,
        cliente_clube=True,
        entrega_rapida=True,
        sla_dias_uteis=1,
        criado_em=criado_em_original,
    )

    obter_ou_criar_pedido(pedido_original, cenario.id)

    prazo_original = pedido_original.prazo_entrega_em

    pedido_duplicado = Pedido(
        codigo="PED-DUP-001",
        bairro=bairro,
        categoria_produto=CategoriaProduto.ALIMENTO,
        cliente_clube=False,
        entrega_rapida=False,
        sla_dias_uteis=3,
        criado_em=datetime(
            2026, 10, 28, 15, 0,
            tzinfo=ZoneInfo("America/Bahia"),
        ),
    )

    resultado = obter_ou_criar_pedido(
        pedido_duplicado,
        cenario.id,
    )

    assert resultado is pedido_duplicado
    assert resultado.id == pedido_original.id

    # O objeto recebido deve refletir os dados ja persistidos.
    assert resultado.categoria_produto == CategoriaProduto.MEDICAMENTO
    assert resultado.cliente_clube is True
    assert resultado.entrega_rapida is True
    assert resultado.sla_dias_uteis == 1
    assert resultado.criado_em == criado_em_original
    assert resultado.prazo_entrega_em == prazo_original

    # O banco deve continuar contendo apenas um pedido.
    pedidos = listar_pedidos_por_cenario(cenario.id)

    assert len(pedidos) == 1
    assert pedidos[0].categoria_produto == CategoriaProduto.MEDICAMENTO
    assert pedidos[0].criado_em == criado_em_original
    assert pedidos[0].prazo_entrega_em == prazo_original