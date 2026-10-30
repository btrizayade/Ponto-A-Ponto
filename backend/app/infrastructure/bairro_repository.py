
import sqlite3

from app.domain.models import Bairro
from app.infrastructure.database import conectar


def cadastrar_bairro(bairro: Bairro) -> Bairro:
    """Salva um novo bairro e devolve seu ID gerado pelo banco."""

    try:
        with conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO bairros (nome, latitude, longitude)
                VALUES (?, ?, ?)
                """,
                (bairro.nome.strip(), bairro.latitude, bairro.longitude),
            )
            bairro.id = cursor.lastrowid

    except sqlite3.IntegrityError as erro:
        if "bairros.nome" in str(erro):
            raise ValueError(
                f"O bairro '{bairro.nome}' já está cadastrado."
            ) from erro
        raise

    return bairro


def listar_bairros() -> list[Bairro]:
    """Retorna os bairros cadastrados, ordenados pelo nome."""

    with conectar() as conexao:
        registros = conexao.execute(
            """
            SELECT id, nome, latitude, longitude
            FROM bairros
            ORDER BY nome
            """
        ).fetchall()

    return [
        Bairro(
            id=registro["id"],
            nome=registro["nome"],
            latitude=registro["latitude"],
            longitude=registro["longitude"],
        )
        for registro in registros
    ]


def obter_ou_criar_bairro(bairro: Bairro) -> Bairro:
    """Retorna um bairro existente ou cadastra um novo."""

    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO bairros (nome, latitude, longitude)
            VALUES (?, ?, ?)
            ON CONFLICT(nome) DO NOTHING
            """,
            (
                bairro.nome.strip(),
                bairro.latitude,
                bairro.longitude,
            ),
        )

        registro = conexao.execute(
            """
            SELECT id, nome, latitude, longitude
            FROM bairros
            WHERE nome = ?
            """,
            (bairro.nome.strip(),),
        ).fetchone()

    if registro is None:
        raise RuntimeError("Não foi possível recuperar o bairro.")

    return Bairro(
        id=registro["id"],
        nome=registro["nome"],
        latitude=registro["latitude"],
        longitude=registro["longitude"],
    )
