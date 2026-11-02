import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.domain.distribution import CentroDistribuicao
from app.domain.models import Entregador, StatusPedido
from app.domain.simulation import EventoSimulacao, TipoEvento
from app.domain.sla import FUSO_HORARIO
from app.infrastructure.database import PROJECT_ROOT, conectar


CONSULTAS_AUDITORIA_DIR = PROJECT_ROOT / "sql" / "auditoria"


def _formatar_instante(instante: datetime) -> str:
    """Grava instantes no horario de Salvador, ordenaveis como texto."""

    return instante.astimezone(FUSO_HORARIO).isoformat()


class AuditoriaSimulacao:
    """
    Registra uma execucao da simulacao e seus eventos no SQLite.

    Deve ser adicionada como observador da Simulacao: cada evento
    emitido e gravado em eventos_simulacao e, quando muda o status de
    um pedido, tambem em mudancas_status_pedido.
    """

    def __init__(self, simulacao_id: int) -> None:
        self.simulacao_id = simulacao_id

    @classmethod
    def criar(
        cls,
        inicio: datetime,
        centro: CentroDistribuicao,
        entregadores: Sequence[Entregador],
        estrategia: str,
        cenario_id: int | None = None,
    ) -> "AuditoriaSimulacao":
        """Cadastra uma nova execucao da simulacao."""

        with conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO simulacoes (
                    cenario_id,
                    criada_em,
                    inicio_simulado,
                    centro_nome,
                    estrategia,
                    entregadores
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cenario_id,
                    datetime.now(timezone.utc).isoformat(),
                    _formatar_instante(inicio),
                    centro.nome,
                    estrategia,
                    ",".join(e.codigo for e in entregadores),
                ),
            )

        return cls(cursor.lastrowid)

    def __call__(self, evento: EventoSimulacao) -> None:
        self.registrar(evento)

    def registrar(self, evento: EventoSimulacao) -> None:
        """Grava um evento emitido pela simulacao."""

        instante = _formatar_instante(evento.instante)

        with conectar() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO eventos_simulacao (
                    simulacao_id,
                    sequencia,
                    instante,
                    tipo,
                    pedido_codigo,
                    entregador_codigo,
                    viagem_numero,
                    atraso_min,
                    distancia_m,
                    detalhe
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.simulacao_id,
                    evento.sequencia,
                    instante,
                    evento.tipo.value,
                    evento.pedido_codigo,
                    evento.entregador_codigo,
                    evento.viagem_numero,
                    evento.atraso_min,
                    evento.distancia_m,
                    evento.detalhe,
                ),
            )

            if evento.status_novo is not None:
                conexao.execute(
                    """
                    INSERT INTO mudancas_status_pedido (
                        simulacao_id,
                        evento_id,
                        pedido_codigo,
                        instante,
                        status_anterior,
                        status_novo
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.simulacao_id,
                        cursor.lastrowid,
                        evento.pedido_codigo,
                        instante,
                        (
                            evento.status_anterior.value
                            if evento.status_anterior
                            else None
                        ),
                        evento.status_novo.value,
                    ),
                )

            if evento.tipo == TipoEvento.SIMULACAO_CONCLUIDA:
                conexao.execute(
                    """
                    UPDATE simulacoes
                    SET status = 'concluida', fim_simulado = ?
                    WHERE id = ?
                    """,
                    (instante, self.simulacao_id),
                )


def listar_eventos(simulacao_id: int) -> list[EventoSimulacao]:
    """Recupera os eventos gravados de uma simulacao, em ordem."""

    with conectar() as conexao:
        registros = conexao.execute(
            """
            SELECT e.*, m.status_anterior, m.status_novo
            FROM eventos_simulacao AS e
            LEFT JOIN mudancas_status_pedido AS m ON m.evento_id = e.id
            WHERE e.simulacao_id = ?
            ORDER BY e.sequencia
            """,
            (simulacao_id,),
        ).fetchall()

    return [_criar_evento(registro) for registro in registros]


def obter_status_dos_pedidos(simulacao_id: int) -> dict[str, StatusPedido]:
    """Ultimo status gravado de cada pedido da simulacao."""

    with conectar() as conexao:
        registros = conexao.execute(
            """
            SELECT m.pedido_codigo, m.status_novo
            FROM mudancas_status_pedido AS m
            INNER JOIN eventos_simulacao AS e ON e.id = m.evento_id
            WHERE m.simulacao_id = ?
            ORDER BY e.sequencia
            """,
            (simulacao_id,),
        ).fetchall()

    return {
        registro["pedido_codigo"]: StatusPedido(registro["status_novo"])
        for registro in registros
    }


def executar_consulta_auditoria(
    nome: str,
    parametros: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Executa uma consulta pronta de sql/auditoria pelo nome do arquivo.

    Exemplo: executar_consulta_auditoria("atrasos", {"simulacao_id": 1})
    """

    caminho = CONSULTAS_AUDITORIA_DIR / f"{nome}.sql"

    if (
        not nome.replace("_", "").isalnum()
        or not caminho.is_file()
    ):
        raise ValueError(f"Consulta de auditoria desconhecida: {nome}.")

    with conectar() as conexao:
        registros = conexao.execute(
            caminho.read_text(encoding="utf-8"),
            dict(parametros),
        ).fetchall()

    return [dict(registro) for registro in registros]


def _criar_evento(registro: sqlite3.Row) -> EventoSimulacao:
    return EventoSimulacao(
        sequencia=registro["sequencia"],
        instante=datetime.fromisoformat(registro["instante"]),
        tipo=TipoEvento(registro["tipo"]),
        pedido_codigo=registro["pedido_codigo"],
        entregador_codigo=registro["entregador_codigo"],
        viagem_numero=registro["viagem_numero"],
        status_anterior=(
            StatusPedido(registro["status_anterior"])
            if registro["status_anterior"]
            else None
        ),
        status_novo=(
            StatusPedido(registro["status_novo"])
            if registro["status_novo"]
            else None
        ),
        atraso_min=registro["atraso_min"],
        distancia_m=registro["distancia_m"],
        detalhe=registro["detalhe"],
    )
