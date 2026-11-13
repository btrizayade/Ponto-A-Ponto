
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.infrastructure.pedido_origem import CODIGOS_REFERENCIA_LEGADOS


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]

DATABASE_DIR = BACKEND_DIR / "data"
DATABASE_PATH = DATABASE_DIR / "pontoaponto.db"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Abre uma conexão com o banco e garante seu fechamento."""

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(DATABASE_PATH)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")

    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def inicializar_banco() -> None:
    """Cria as tabelas definidas no esquema SQL, se necessário."""

    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(
            f"Arquivo de esquema não encontrado: {SCHEMA_PATH}"
        )

    esquema = SCHEMA_PATH.read_text(encoding="utf-8")

    with conectar() as conexao:
        conexao.executescript(esquema)
        _migrar_origem_e_atividade_pedidos(conexao)


def _migrar_origem_e_atividade_pedidos(
    conexao: sqlite3.Connection,
) -> None:
    """Adiciona origem/atividade e classifica registros do seed legado."""

    colunas_pedidos = {
        registro["name"]
        for registro in conexao.execute("PRAGMA table_info(pedidos)")
    }
    if "origem" not in colunas_pedidos:
        conexao.execute(
            """
            ALTER TABLE pedidos
            ADD COLUMN origem TEXT NOT NULL DEFAULT 'manual'
                CHECK (origem IN ('referencia', 'manual'))
            """
        )
    if "ativo" not in colunas_pedidos:
        conexao.execute(
            """
            ALTER TABLE pedidos
            ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1
                CHECK (ativo IN (0, 1))
            """
        )

    colunas_simulacoes = {
        registro["name"]
        for registro in conexao.execute("PRAGMA table_info(simulacoes)")
    }
    if "segundos_reais_por_hora_simulada" not in colunas_simulacoes:
        conexao.execute(
            """
            ALTER TABLE simulacoes
            ADD COLUMN segundos_reais_por_hora_simulada INTEGER NOT NULL
                DEFAULT 15
                CHECK (segundos_reais_por_hora_simulada IN (5, 15, 30, 60))
            """
        )
    if "limite_pedido_manual_id" not in colunas_simulacoes:
        conexao.execute(
            "ALTER TABLE simulacoes ADD COLUMN limite_pedido_manual_id INTEGER"
        )

    for codigo_cenario, codigos in CODIGOS_REFERENCIA_LEGADOS.items():
        placeholders = ", ".join("?" for _ in codigos)
        conexao.execute(
            f"""
            UPDATE pedidos
            SET origem = 'referencia'
            WHERE cenario_id = (
                SELECT id FROM cenarios WHERE codigo = ?
            )
              AND codigo IN ({placeholders})
            """,
            (codigo_cenario, *codigos),
        )

    # EQ-016 é o 16º registro da versão anterior do seed. O novo manifesto
    # tem 15 itens; arquivá-lo conserva dados e histórico sem mantê-lo ativo.
    conexao.execute(
        """
        UPDATE pedidos
        SET ativo = 0
        WHERE origem = 'referencia'
          AND codigo = 'EQ-016'
          AND cenario_id = (SELECT id FROM cenarios WHERE codigo = 'EQUIDADE')
        """
    )
    conexao.execute(
        """
        UPDATE cenarios
        SET descricao = '15 pedidos próprios, distribuídos de forma equilibrada pelos oito bairros atendidos.'
        WHERE codigo = 'EQUIDADE'
        """
    )
    conexao.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pedidos_cenario_origem_ativo
        ON pedidos (cenario_id, origem, ativo)
        """
    )
