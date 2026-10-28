
import sqlite3

from app.domain.models import Cenario
from app.infrastructure.database import conectar


def cadastrar_cenario(cenario: Cenario) -> Cenario:
    """Salva um cenário e devolve seu ID gerado pelo banco."""

    try:
        with conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO cenarios (codigo, nome, descricao)
                VALUES (?, ?, ?)
                """,
                (
                    cenario.codigo.strip(),
                    cenario.nome.strip(),
                    cenario.descricao.strip(),
                ),
            )
            cenario.id = cursor.lastrowid

    except sqlite3.IntegrityError as erro:
        if "cenarios.codigo" in str(erro):
            raise ValueError(
                f"O cenário '{cenario.codigo}' já está cadastrado."
            ) from erro
        raise

    return cenario


def listar_cenarios() -> list[Cenario]:
    """Retorna os cenários cadastrados, ordenados pelo nome."""

    with conectar() as conexao:
        registros = conexao.execute(
            """
            SELECT id, codigo, nome, descricao
            FROM cenarios
            ORDER BY nome
            """
        ).fetchall()

    return [
        Cenario(
            id=registro["id"],
            codigo=registro["codigo"],
            nome=registro["nome"],
            descricao=registro["descricao"],
        )
        for registro in registros
    ]


def obter_ou_criar_cenario(cenario: Cenario) -> Cenario:
    """Retorna um cenario existente ou cadastra um novo."""

    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO cenarios (codigo, nome, descricao)
            VALUES (?, ?, ?)
            ON CONFLICT(codigo) DO NOTHING
            """,
            (
                cenario.codigo.strip(),
                cenario.nome.strip(),
                cenario.descricao.strip(),
            ),
        )

        registro = conexao.execute(
            """
            SELECT id, codigo, nome, descricao
            FROM cenarios
            WHERE codigo = ?
            """,
            (cenario.codigo.strip(),),
        ).fetchone()

    if registro is None:
        raise RuntimeError("Não foi possível recuperar o cenário.")

    return Cenario(
        id=registro["id"],
        codigo=registro["codigo"],
        nome=registro["nome"],
        descricao=registro["descricao"],
    )
