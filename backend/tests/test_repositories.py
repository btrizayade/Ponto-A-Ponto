
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
from app.infrastructure.pedido_repository import obter_ou_criar_pedido


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
