import hashlib
import json
import logging
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app.domain.distribution import CentroDistribuicao
from app.domain.models import Entregador, StatusPedido
from app.domain.simulation import EventoSimulacao, TipoEvento
from app.domain.sla import FUSO_HORARIO
from app.infrastructure.auditoria_experimental import (
    FalhaPersistenciaAuditoriaExperimental,
    VERSAO_RESPOSTA_ROTEAMENTO,
)
from app.infrastructure.database import PROJECT_ROOT, conectar


CONSULTAS_AUDITORIA_DIR = PROJECT_ROOT / "sql" / "auditoria"
logger = logging.getLogger(__name__)


def _json_canonico(dados: Mapping[str, Any]) -> str:
    """JSON estavel usado para persistencia e deduplicacao por hash."""

    return json.dumps(
        dados,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


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
        limite_pedido_manual_id: int | None = None,
        segundos_reais_por_hora_simulada: int = 15,
        parametros: Mapping[str, Any] | None = None,
        snapshot_pedidos: Mapping[str, Any] | None = None,
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
                    entregadores,
                    parametros_json,
                    planejamento_status,
                    consultas_roteamento_contagem,
                    planejamento_erro,
                    limite_pedido_manual_id,
                    segundos_reais_por_hora_simulada
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cenario_id,
                    datetime.now(timezone.utc).isoformat(),
                    _formatar_instante(inicio),
                    centro.nome,
                    estrategia,
                    ",".join(e.codigo for e in entregadores),
                    (
                        _json_canonico(parametros)
                        if parametros is not None
                        else None
                    ),
                    "aguardando" if parametros is not None else None,
                    0 if parametros is not None else None,
                    None,
                    limite_pedido_manual_id,
                    segundos_reais_por_hora_simulada,
                ),
            )
            simulacao_id = cursor.lastrowid
            if snapshot_pedidos is not None:
                conexao.execute(
                    """
                    INSERT INTO simulacao_pedidos_snapshot (
                        simulacao_id, versao, dados_json
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        simulacao_id,
                        int(snapshot_pedidos["versao"]),
                        _json_canonico(snapshot_pedidos),
                    ),
                )

        return cls(simulacao_id)

    def registrar_consulta_roteamento(
        self,
        *,
        tipo: str,
        provedor: str,
        perfil: str,
        origem_resultado: str,
        partida_em: datetime | None,
        consultada_em: datetime,
        requisicao: Mapping[str, Any],
        resposta: Mapping[str, Any],
    ) -> None:
        """Grava consulta e resposta efetiva em uma transacao atomica."""

        versao = VERSAO_RESPOSTA_ROTEAMENTO
        dados_json = _json_canonico(resposta)
        envelope_hash = _json_canonico(
            {"tipo": tipo, "versao": versao, "dados": resposta}
        )
        hash_sha256 = hashlib.sha256(
            envelope_hash.encode("utf-8")
        ).hexdigest()
        requisicao_json = _json_canonico(requisicao)

        with conectar() as conexao:
            conexao.execute("BEGIN IMMEDIATE")
            sequencia = conexao.execute(
                """
                SELECT COALESCE(MAX(sequencia), 0) + 1
                FROM consultas_roteamento_simulacao
                WHERE simulacao_id = ?
                """,
                (self.simulacao_id,),
            ).fetchone()[0]

            conexao.execute(
                """
                INSERT INTO respostas_roteamento (
                    tipo, versao, hash_sha256, dados_json, criada_em
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(hash_sha256) DO NOTHING
                """,
                (
                    tipo,
                    versao,
                    hash_sha256,
                    dados_json,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            registro_resposta = conexao.execute(
                """
                SELECT id, tipo, versao
                FROM respostas_roteamento
                WHERE hash_sha256 = ?
                """,
                (hash_sha256,),
            ).fetchone()
            if (
                registro_resposta is None
                or registro_resposta["tipo"] != tipo
                or registro_resposta["versao"] != versao
            ):
                raise RuntimeError(
                    "A resposta deduplicada de roteamento é incompatível."
                )

            conexao.execute(
                """
                INSERT INTO consultas_roteamento_simulacao (
                    simulacao_id, sequencia, tipo, provedor, perfil,
                    origem_resultado, partida_em, consultada_em,
                    requisicao_json, resposta_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.simulacao_id,
                    sequencia,
                    tipo,
                    provedor,
                    perfil,
                    origem_resultado,
                    _formatar_instante(partida_em) if partida_em else None,
                    consultada_em.astimezone(timezone.utc).isoformat(),
                    requisicao_json,
                    registro_resposta["id"],
                ),
            )
            atualizacao = conexao.execute(
                """
                UPDATE simulacoes
                SET consultas_roteamento_contagem =
                        consultas_roteamento_contagem + 1,
                    planejamento_status = CASE
                        WHEN planejamento_status = 'aguardando'
                            THEN 'planejando'
                        ELSE planejamento_status
                    END
                WHERE id = ?
                  AND parametros_json IS NOT NULL
                  AND consultas_roteamento_contagem IS NOT NULL
                """,
                (self.simulacao_id,),
            )
            if atualizacao.rowcount != 1:
                raise RuntimeError(
                    "A consulta de roteamento não possui estado de auditoria."
                )

    def iniciar_planejamento(self) -> None:
        """Registra o início do planejamento antes de consultar rotas."""

        try:
            with conectar() as conexao:
                cursor = conexao.execute(
                    """
                    UPDATE simulacoes
                    SET planejamento_status = 'planejando',
                        planejamento_erro = NULL
                    WHERE id = ?
                      AND parametros_json IS NOT NULL
                      AND planejamento_status IN (
                          'aguardando', 'planejando', 'falhou', 'interrompido'
                      )
                    """,
                    (self.simulacao_id,),
                )
                if cursor.rowcount != 1:
                    raise FalhaPersistenciaAuditoriaExperimental(
                        "Não foi possível registrar o início do planejamento."
                    )
        except FalhaPersistenciaAuditoriaExperimental:
            raise
        except Exception as erro:
            raise FalhaPersistenciaAuditoriaExperimental(
                "Não foi possível persistir o início do planejamento."
            ) from erro

    def concluir_planejamento(self) -> None:
        """Marca planejamento concluído sem exigir consultas de roteamento."""

        try:
            with conectar() as conexao:
                cursor = conexao.execute(
                    """
                    UPDATE simulacoes
                    SET planejamento_status = 'concluido',
                        planejamento_erro = NULL
                    WHERE id = ? AND planejamento_status = 'planejando'
                    """,
                    (self.simulacao_id,),
                )
                if cursor.rowcount != 1:
                    raise FalhaPersistenciaAuditoriaExperimental(
                        "Não foi possível registrar a conclusão do planejamento."
                    )
        except FalhaPersistenciaAuditoriaExperimental:
            raise
        except Exception as erro:
            raise FalhaPersistenciaAuditoriaExperimental(
                "Não foi possível persistir a conclusão do planejamento."
            ) from erro

    def falhar_planejamento(self, erro: Exception) -> None:
        """Marca falha sem guardar mensagens que possam conter segredos."""

        try:
            with conectar() as conexao:
                conexao.execute(
                    """
                    UPDATE simulacoes
                    SET planejamento_status = 'falhou',
                        planejamento_erro = ?
                    WHERE id = ?
                      AND planejamento_status IN ('aguardando', 'planejando')
                    """,
                    (type(erro).__name__, self.simulacao_id),
                )
        except Exception:
            # A falha de gravação do estado não deve substituir a causa
            # original do planejamento; 'planejando' será reconciliado
            # como interrompido na próxima inicialização.
            logger.exception(
                "Falha ao persistir o estado do planejamento da simulação %s",
                self.simulacao_id,
            )

    @staticmethod
    def marcar_planejamentos_interrompidos() -> int:
        """Reconcilia tarefas não terminais perdidas ao reiniciar o backend."""

        with conectar() as conexao:
            cursor = conexao.execute(
                """
                UPDATE simulacoes
                SET planejamento_status = 'interrompido',
                    planejamento_erro = 'ProcessoReiniciado'
                WHERE planejamento_status IN ('aguardando', 'planejando')
                """
            )
            return cursor.rowcount

    def __call__(self, evento: EventoSimulacao) -> None:
        self.registrar(evento)

    def registrar(self, evento: EventoSimulacao) -> None:
        """
        Grava um evento emitido pela simulacao.

        Um evento ja gravado (mesma sequencia) e ignorado: a simulacao
        reenvia o evento quando outro observador falha.
        """

        instante = _formatar_instante(evento.instante)

        with conectar() as conexao:
            ja_gravado = conexao.execute(
                """
                SELECT 1 FROM eventos_simulacao
                WHERE simulacao_id = ? AND sequencia = ?
                """,
                (self.simulacao_id, evento.sequencia),
            ).fetchone()

            if ja_gravado:
                return

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
                conexao.execute(
                    """
                    UPDATE pedidos
                    SET ativo = 0
                    WHERE cenario_id = (
                        SELECT cenario_id FROM simulacoes WHERE id = ?
                    )
                      AND origem = 'manual'
                      AND ativo = 1
                      AND id <= COALESCE(
                          (SELECT limite_pedido_manual_id
                           FROM simulacoes WHERE id = ?),
                          -1
                      )
                    """,
                    (self.simulacao_id, self.simulacao_id),
                )

    def descartar_criacao_sem_eventos(self) -> bool:
        """Remove o registro se o executor falhou antes do primeiro evento.

        Uma criação que não chegou a iniciar não é uma execução histórica.
        A condição protege qualquer simulação que já tenha emitido eventos.
        """

        with conectar() as conexao:
            cursor = conexao.execute(
                """
                DELETE FROM simulacoes
                WHERE id = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM eventos_simulacao
                      WHERE simulacao_id = ?
                  )
                """,
                (self.simulacao_id, self.simulacao_id),
            )
            return cursor.rowcount == 1


_COLUNAS_SIMULACAO = """
    id,
    cenario_id,
    criada_em,
    inicio_simulado,
    fim_simulado,
    centro_nome,
    estrategia,
    entregadores,
    segundos_reais_por_hora_simulada,
    status
"""


def listar_simulacoes() -> list[dict[str, Any]]:
    """Execucoes gravadas, da mais recente para a mais antiga."""

    with conectar() as conexao:
        registros = conexao.execute(
            f"SELECT {_COLUNAS_SIMULACAO} FROM simulacoes ORDER BY id DESC"
        ).fetchall()

    return [dict(registro) for registro in registros]


def obter_simulacao(simulacao_id: int) -> dict[str, Any] | None:
    """Dados gravados de uma execucao, se existir."""

    with conectar() as conexao:
        registro = conexao.execute(
            f"SELECT {_COLUNAS_SIMULACAO} FROM simulacoes WHERE id = ?",
            (simulacao_id,),
        ).fetchone()

    return dict(registro) if registro else None


def obter_parametros_experimentais(
    simulacao_id: int,
) -> dict[str, Any] | None:
    """Retorna parametros, entradas e roteamentos de uma execucao gravada."""

    with conectar() as conexao:
        simulacao = conexao.execute(
            """
            SELECT parametros_json, planejamento_status,
                   consultas_roteamento_contagem, planejamento_erro
            FROM simulacoes WHERE id = ?
            """,
            (simulacao_id,),
        ).fetchone()
        if simulacao is None:
            return None

        if simulacao["parametros_json"] is None:
            return {
                "simulacao_id": simulacao_id,
                "disponivel": False,
                "parametros": None,
                "snapshot_pedidos": None,
                "consultas_roteamento": [],
                "planejamento": {
                    "estado": "desconhecido",
                    "integridade": "desconhecida",
                    "consultas_esperadas": None,
                    "consultas_registradas": 0,
                    "erro": None,
                    "problemas": [],
                },
            }

        snapshot = conexao.execute(
            """
            SELECT versao, dados_json
            FROM simulacao_pedidos_snapshot
            WHERE simulacao_id = ?
            """,
            (simulacao_id,),
        ).fetchone()
        consultas = conexao.execute(
            """
            SELECT
                c.sequencia,
                c.tipo,
                c.provedor,
                c.perfil,
                c.origem_resultado,
                c.partida_em,
                c.consultada_em,
                c.requisicao_json,
                r.id AS resposta_id,
                r.tipo AS resposta_tipo,
                r.versao AS resposta_versao,
                r.hash_sha256 AS resposta_hash_sha256,
                r.dados_json AS resposta_json
            FROM consultas_roteamento_simulacao AS c
            LEFT JOIN respostas_roteamento AS r ON r.id = c.resposta_id
            WHERE c.simulacao_id = ?
            ORDER BY c.sequencia
            """,
            (simulacao_id,),
        ).fetchall()

    sequencias = [consulta["sequencia"] for consulta in consultas]
    quantidade_consultas = len(consultas)
    problemas: list[str] = []
    estado = simulacao["planejamento_status"] or "desconhecido"
    contagem_esperada = simulacao["consultas_roteamento_contagem"]

    if snapshot is None:
        problemas.append("snapshot_ausente")
    if sequencias != list(range(1, quantidade_consultas + 1)):
        problemas.append("sequencia_com_lacuna_ou_desordenada")
    if any(consulta["resposta_id"] is None for consulta in consultas):
        problemas.append("resposta_de_roteamento_ausente")
    if any(
        consulta["resposta_id"] is not None
        and consulta["resposta_tipo"] != consulta["tipo"]
        for consulta in consultas
    ):
        problemas.append("tipo_de_resposta_incompativel")
    if (
        contagem_esperada is not None
        and contagem_esperada != quantidade_consultas
    ):
        problemas.append("contador_de_consultas_divergente")
    if (
        estado
        in {"aguardando", "planejando", "concluido", "falhou", "interrompido"}
        and contagem_esperada is None
    ):
        problemas.append("contador_de_consultas_ausente")
    if (
        estado == "aguardando"
        and (quantidade_consultas > 0 or contagem_esperada not in (0, None))
    ):
        problemas.append("consultas_incompativeis_com_estado_aguardando")

    if problemas or estado in {"falhou", "interrompido"}:
        integridade = "incompleta"
    elif estado == "concluido":
        integridade = "completa"
    elif estado == "planejando":
        integridade = "em_andamento"
    elif estado == "aguardando":
        integridade = "pendente"
    else:
        integridade = "desconhecida"

    return {
        "simulacao_id": simulacao_id,
        "disponivel": True,
        "parametros": json.loads(simulacao["parametros_json"]),
        "snapshot_pedidos": {
            "versao": snapshot["versao"],
            "dados": json.loads(snapshot["dados_json"]),
        } if snapshot is not None else None,
        "consultas_roteamento": [
            {
                "sequencia": consulta["sequencia"],
                "tipo": consulta["tipo"],
                "provedor": consulta["provedor"],
                "perfil": consulta["perfil"],
                "origem_resultado": consulta["origem_resultado"],
                "partida_em": consulta["partida_em"],
                "consultada_em": consulta["consultada_em"],
                "requisicao": json.loads(consulta["requisicao_json"]),
                "resposta": (
                    {
                        "versao": consulta["resposta_versao"],
                        "hash_sha256": consulta["resposta_hash_sha256"],
                        "dados": json.loads(consulta["resposta_json"]),
                    }
                    if consulta["resposta_id"] is not None
                    else None
                ),
            }
            for consulta in consultas
        ],
        "planejamento": {
            "estado": estado,
            "integridade": integridade,
            "consultas_esperadas": contagem_esperada,
            "consultas_registradas": quantidade_consultas,
            "erro": simulacao["planejamento_erro"],
            "problemas": problemas,
        },
    }


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
