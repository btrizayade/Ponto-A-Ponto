
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


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
