
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

    try:
        conexao.execute("PRAGMA foreign_keys = ON")
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
        # executescript nao abre uma transacao por conta propria. Inicie uma
        # explicitamente para que o schema e as alteracoes abaixo sejam
        # confirmados juntos pelo context manager ou revertidos em caso de erro.
        # conectar ja habilitou as chaves estrangeiras antes deste BEGIN.
        conexao.executescript(f"BEGIN IMMEDIATE;\n{esquema}")
        _migrar_origem_e_atividade_pedidos(conexao)


def _migrar_origem_e_atividade_pedidos(
    conexao: sqlite3.Connection,
) -> None:
    """Adiciona origem/atividade e classifica registros do seed legado."""

    colunas_pedidos = {
        registro["name"]
        for registro in conexao.execute("PRAGMA table_info(pedidos)")
    }
    colunas_simulacoes = {
        registro["name"]
        for registro in conexao.execute("PRAGMA table_info(simulacoes)")
    }
    origem_adicionada = "origem" not in colunas_pedidos
    recuperar_classificacao_interrompida = (
        "origem" in colunas_pedidos and "ativo" not in colunas_pedidos
    )

    if origem_adicionada:
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

    if origem_adicionada or recuperar_classificacao_interrompida:
        # Antes da F09 o schema nao distinguia pedidos manuais e os caminhos
        # de producao gravavam os pedidos pelo seed. A migracao antiga adicionava
        # origem imediatamente antes de ativo. Se origem existe e ativo falta,
        # ela parou entre esses DDLs, antes de o lifespan liberar a API. A falta
        # apenas de colunas de simulacao nao e marcador seguro: pode haver
        # pedidos manuais de uma versao valida anterior. Bancos completos ou
        # com estado ambiguo nao recebem esta reclassificacao em massa.
        conexao.execute(
            "UPDATE pedidos SET origem = 'referencia'"
        )

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
    if "parametros_json" not in colunas_simulacoes:
        # Simulações anteriores à auditoria experimental não têm como ter
        # seus parâmetros reconstruídos com segurança. NULL representa essa
        # ausência histórica explicitamente.
        conexao.execute(
            "ALTER TABLE simulacoes ADD COLUMN parametros_json TEXT"
        )
    if "planejamento_status" not in colunas_simulacoes:
        # NULL preserva a incerteza histórica; não inferimos se o plano
        # chegou a iniciar em simulações anteriores a este marcador.
        conexao.execute(
            """
            ALTER TABLE simulacoes
            ADD COLUMN planejamento_status TEXT
                CHECK (
                    planejamento_status IS NULL
                    OR planejamento_status IN (
                        'aguardando', 'planejando', 'concluido', 'falhou',
                        'interrompido'
                    )
                )
            """
        )
    if "consultas_roteamento_contagem" not in colunas_simulacoes:
        conexao.execute(
            """
            ALTER TABLE simulacoes
            ADD COLUMN consultas_roteamento_contagem INTEGER
                CHECK (
                    consultas_roteamento_contagem IS NULL
                    OR consultas_roteamento_contagem >= 0
                )
            """
        )
    if "planejamento_erro" not in colunas_simulacoes:
        conexao.execute(
            "ALTER TABLE simulacoes ADD COLUMN planejamento_erro TEXT"
        )

    # Em bancos legados, o schema pode ter encontrado uma tabela simulacoes
    # sem parametros_json quando seus triggers foram compilados. Recrie-os
    # depois da adicao das colunas para garantir que protejam o campo novo.
    conexao.execute(
        "DROP TRIGGER IF EXISTS trg_simulacoes_parametros_immutable"
    )
    conexao.execute(
        """
        CREATE TRIGGER trg_simulacoes_parametros_immutable
        BEFORE UPDATE OF parametros_json ON simulacoes
        WHEN OLD.parametros_json IS NOT NEW.parametros_json
        BEGIN
            SELECT RAISE(ABORT, 'Os parametros experimentais sao imutaveis.');
        END
        """
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
