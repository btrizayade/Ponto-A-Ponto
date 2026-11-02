from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.estado import montar_estado, montar_rotas, resultado_etapa
from app.api.registro import SimulacaoAtiva, registro
from app.api.schemas import (
    Avanco,
    EstadoSimulacao,
    EventoResposta,
    NovaSimulacao,
    ResultadoEtapa,
    RotasSimulacao,
    SimulacaoGravada,
)
from app.domain.distribution import (
    DistribuicaoInsercaoMaisBarata,
    DistribuicaoOrdemDaFila,
)
from app.domain.sla import FUSO_HORARIO
from app.infrastructure.auditoria_repository import (
    CONSULTAS_AUDITORIA_DIR,
    executar_consulta_auditoria,
    listar_eventos,
    listar_simulacoes,
    obter_simulacao,
)
from app.infrastructure.cenario_repository import obter_cenario
from app.infrastructure.distribution_config import criar_entregadores_padrao
from app.infrastructure.routing_factory import (
    criar_servico_roteamento,
    provedor_padrao,
)
from app.infrastructure.simulacao_factory import criar_simulacao_auditada


ESTRATEGIAS = {
    "insercao_mais_barata": DistribuicaoInsercaoMaisBarata,
    "ordem_da_fila": DistribuicaoOrdemDaFila,
}
ESTRATEGIA_PADRAO = "insercao_mais_barata"

# A auditoria grava o nome da classe; a API usa o nome curto.
_NOME_DA_CLASSE = {classe.__name__: nome for nome, classe in ESTRATEGIAS.items()}


router = APIRouter(prefix="/api/simulacoes", tags=["simulacoes"])


# Criacao e consulta


@router.post("", response_model=EstadoSimulacao, status_code=201)
def criar(dados: NovaSimulacao):
    """
    Cria uma simulacao de um cenario, gravada na auditoria.

    A simulacao comeca parada: a primeira etapa monta a fila e
    planeja as viagens.
    """

    if obter_cenario(dados.cenario_id) is None:
        raise HTTPException(404, f"Cenario {dados.cenario_id} nao encontrado.")

    provedor = dados.provedor or provedor_padrao()
    estrategia = dados.estrategia or ESTRATEGIA_PADRAO
    inicio = _com_fuso(dados.inicio)

    try:
        simulacao, auditoria = criar_simulacao_auditada(
            dados.cenario_id,
            inicio,
            servico=criar_servico_roteamento(provedor),
            entregadores=criar_entregadores_padrao(
                dados.quantidade_entregadores
            ),
            estrategia=ESTRATEGIAS[estrategia](),
        )
    except ValueError as erro:
        raise HTTPException(400, str(erro)) from erro

    ativa = SimulacaoAtiva(
        simulacao=simulacao,
        auditoria=auditoria,
        cenario_id=dados.cenario_id,
        inicio=inicio,
        provedor=provedor,
        estrategia=estrategia,
    )
    registro.adicionar(ativa)

    with ativa.trava:
        return montar_estado(ativa)


@router.get("", response_model=list[SimulacaoGravada])
def listar():
    """Simulacoes gravadas na auditoria, da mais recente para a antiga."""

    ativas = registro.ids()

    return [_simulacao_gravada(s, ativas) for s in listar_simulacoes()]


@router.get("/{simulacao_id}", response_model=EstadoSimulacao)
def obter_estado(simulacao_id: int):
    ativa = _ativa(simulacao_id)

    with ativa.trava:
        return montar_estado(ativa)


# Controle


@router.post("/{simulacao_id}/proxima-etapa", response_model=ResultadoEtapa)
def proxima_etapa(simulacao_id: int):
    """Avanca ate o proximo instante com eventos (ou inicia)."""

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        eventos = ativa.simulacao.proxima_etapa()

        return resultado_etapa(ativa, eventos)


@router.post("/{simulacao_id}/avancar", response_model=ResultadoEtapa)
def avancar(simulacao_id: int, avanco: Avanco):
    """Avanca o relogio por alguns minutos ou ate um horario."""

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        try:
            if avanco.minutos is not None:
                eventos = ativa.simulacao.avancar(avanco.minutos)
            else:
                eventos = ativa.simulacao.avancar_ate(_com_fuso(avanco.ate))
        except ValueError as erro:
            raise HTTPException(400, str(erro)) from erro

        return resultado_etapa(ativa, eventos)


@router.post("/{simulacao_id}/executar", response_model=ResultadoEtapa)
def executar(simulacao_id: int):
    """Processa todos os eventos restantes."""

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        eventos = ativa.simulacao.executar_ate_o_fim()

        return resultado_etapa(ativa, eventos)


# Mapa, eventos e auditoria


@router.get("/{simulacao_id}/rotas", response_model=RotasSimulacao)
def obter_rotas(simulacao_id: int):
    """
    Rotas planejadas com o trajeto de cada viagem, para o mapa.

    A geometria e calculada na primeira consulta e reaproveitada.
    """

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        if not ativa.simulacao.iniciada:
            raise HTTPException(
                409, "A simulacao ainda nao foi iniciada."
            )

        if not ativa.rotas_montadas:
            ativa.simulacao.distribuidor.montar_rotas(ativa.simulacao.plano)
            ativa.rotas_montadas = True

        return montar_rotas(ativa)


@router.get("/{simulacao_id}/eventos", response_model=list[EventoResposta])
def obter_eventos(
    simulacao_id: int,
    apos: int = Query(
        default=0, ge=0, description="Retorna eventos com sequencia maior."
    ),
):
    """Eventos gravados na auditoria; funciona para qualquer simulacao."""

    _gravada(simulacao_id)

    return [
        EventoResposta.model_validate(evento)
        for evento in listar_eventos(simulacao_id)
        if evento.sequencia > apos
    ]


@router.get("/{simulacao_id}/auditoria/{consulta}")
def consultar_auditoria(
    simulacao_id: int,
    consulta: str,
    pedido_codigo: str | None = None,
) -> list[dict[str, Any]]:
    """Executa uma das consultas prontas de sql/auditoria."""

    _gravada(simulacao_id)
    caminho = CONSULTAS_AUDITORIA_DIR / f"{consulta}.sql"

    if not consulta.replace("_", "").isalnum() or not caminho.is_file():
        raise HTTPException(404, f"Consulta {consulta} nao encontrada.")

    parametros = {"simulacao_id": simulacao_id}

    if ":pedido_codigo" in caminho.read_text(encoding="utf-8"):
        if not pedido_codigo:
            raise HTTPException(
                400, "Informe o parametro pedido_codigo para esta consulta."
            )

        parametros["pedido_codigo"] = pedido_codigo

    return executar_consulta_auditoria(consulta, parametros)


# Auxiliares


def _com_fuso(instante: datetime) -> datetime:
    """
    Converte o horario para o fuso de Salvador.

    Horarios sem fuso ja sao considerados de Salvador. Assim, as
    respostas usam sempre o mesmo fuso, como a auditoria.
    """

    if instante.tzinfo is None or instante.utcoffset() is None:
        return instante.replace(tzinfo=FUSO_HORARIO)

    return instante.astimezone(FUSO_HORARIO)


def _gravada(simulacao_id: int) -> dict[str, Any]:
    gravada = obter_simulacao(simulacao_id)

    if gravada is None:
        raise HTTPException(404, f"Simulacao {simulacao_id} nao encontrada.")

    return gravada


def _ativa(simulacao_id: int) -> SimulacaoAtiva:
    ativa = registro.obter(simulacao_id)

    if ativa is not None:
        return ativa

    _gravada(simulacao_id)

    raise HTTPException(
        410,
        f"Simulacao {simulacao_id} nao esta mais em memoria (o servidor "
        "foi reiniciado). Os eventos e a auditoria continuam disponiveis.",
    )


def _simulacao_gravada(
    dados: dict[str, Any],
    ativas: set[int],
) -> SimulacaoGravada:
    return SimulacaoGravada(
        **{
            **dados,
            "estrategia": _NOME_DA_CLASSE.get(
                dados["estrategia"], dados["estrategia"]
            ),
            "entregadores": dados["entregadores"].split(","),
        },
        ativa=dados["id"] in ativas,
    )
