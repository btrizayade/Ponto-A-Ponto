from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.estado import montar_estado, montar_rotas, resultado_etapa
from app.api.registro import SimulacaoAtiva, registro
from app.api.schemas import (
    Avanco,
    EstadoSimulacao,
    EventoResposta,
    NovaSimulacao,
    ResultadoEtapa,
    RespostaControleExecucao,
    RotasSimulacao,
    SimulacaoGravada,
)
from app.domain.distribution import (
    DistribuicaoEquidadeSLA,
    DistribuicaoInsercaoMaisBarata,
    DistribuicaoOrdemDaFila,
)
from app.domain.sla import FUSO_HORARIO
from app.domain.simulation import EstadoExecucao
from app.infrastructure.auditoria_repository import (
    CONSULTAS_AUDITORIA_DIR,
    executar_consulta_auditoria,
    listar_eventos,
    listar_simulacoes,
    obter_simulacao,
)
from app.infrastructure.cenario_repository import obter_cenario
from app.infrastructure.distribution_config import criar_entregadores_padrao
from app.infrastructure.execucao_automatica import sincronizar_relogio
from app.infrastructure.routing_factory import (
    PROVEDOR_GOOGLE,
    PROVEDOR_SIMULADO,
    provedor_padrao,
)
from app.infrastructure.simulated_routing import (
    FATOR_TRANSITO_ALTA_DEMANDA,
)
from app.infrastructure.simulacao_factory import criar_simulacao_auditada


ESTRATEGIAS = {
    "insercao_mais_barata": DistribuicaoInsercaoMaisBarata,
    "ordem_da_fila": DistribuicaoOrdemDaFila,
    "equidade_sla": DistribuicaoEquidadeSLA,
}
ESTRATEGIA_PADRAO = "insercao_mais_barata"

# A auditoria grava o nome da classe; a API usa o nome curto.
_NOME_DA_CLASSE = {classe.__name__: nome for nome, classe in ESTRATEGIAS.items()}


router = APIRouter(prefix="/api/simulacoes", tags=["simulacoes"])


# Criacao e consulta


@router.post("", response_model=EstadoSimulacao, status_code=201)
async def criar(dados: NovaSimulacao, request: Request):
    """
    Cria uma simulacao de um cenario, gravada na auditoria.

    Esta chamada representa o início explícito de uma operação e agenda
    a execução automática após registrar sua configuração.
    """

    if registro.existe_operacao_em_andamento():
        raise HTTPException(
            409,
            "Já existe uma simulação executando ou pausada. "
            "Conclua a operação atual antes de iniciar outra.",
        )

    cenario = obter_cenario(dados.cenario_id)

    if cenario is None:
        raise HTTPException(404, f"Cenario {dados.cenario_id} nao encontrado.")

    fator_transito = None

    if cenario.codigo == "ALTA_DEMANDA":
        if dados.provedor == PROVEDOR_GOOGLE:
            raise HTTPException(
                400,
                "O cenário ALTA_DEMANDA exige o provedor simulado com "
                f"fator de trânsito {FATOR_TRANSITO_ALTA_DEMANDA:.1f}; "
                "Google Routes é incompatível com essa configuração.",
            )

        provedor = PROVEDOR_SIMULADO
        fator_transito = FATOR_TRANSITO_ALTA_DEMANDA
    else:
        provedor = dados.provedor or provedor_padrao()

    if dados.estrategia is not None:
        estrategia = dados.estrategia
    elif cenario.codigo == "EQUIDADE":
        estrategia = "equidade_sla"
    else:
        estrategia = ESTRATEGIA_PADRAO
    inicio = _com_fuso(dados.inicio)

    try:
        simulacao, auditoria = criar_simulacao_auditada(
            dados.cenario_id,
            inicio,
            entregadores=criar_entregadores_padrao(
                dados.quantidade_entregadores
            ),
            estrategia=ESTRATEGIAS[estrategia](),
            provedor=provedor,
            fator_transito=fator_transito,
            segundos_reais_por_hora_simulada=(
                dados.segundos_reais_por_hora_simulada
            ),
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
        segundos_reais_por_hora_simulada=(
            dados.segundos_reais_por_hora_simulada
        ),
    )
    registro.adicionar(ativa)
    await request.app.state.execucao_automatica.iniciar(ativa.id, ativa)

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
        sincronizar_relogio(ativa)
        _atualizar_estado_execucao(ativa)
        return montar_estado(ativa)


# Controle


@router.post("/{simulacao_id}/proxima-etapa", response_model=ResultadoEtapa)
def proxima_etapa(simulacao_id: int):
    """Avanca ate o proximo instante com eventos (ou inicia)."""

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        _exigir_nao_pausada(ativa)
        eventos = ativa.simulacao.proxima_etapa()
        _atualizar_estado_execucao(ativa)

        return resultado_etapa(ativa, eventos)


@router.post("/{simulacao_id}/avancar", response_model=ResultadoEtapa)
def avancar(simulacao_id: int, avanco: Avanco):
    """Avanca o relogio por alguns minutos ou ate um horario."""

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        _exigir_nao_pausada(ativa)
        try:
            if avanco.minutos is not None:
                eventos = ativa.simulacao.avancar(avanco.minutos)
            else:
                eventos = ativa.simulacao.avancar_ate(_com_fuso(avanco.ate))
        except ValueError as erro:
            raise HTTPException(400, str(erro)) from erro

        _atualizar_estado_execucao(ativa)
        return resultado_etapa(ativa, eventos)


@router.post("/{simulacao_id}/executar", response_model=ResultadoEtapa)
def executar(simulacao_id: int):
    """Processa os eventos restantes, cedendo o controle entre etapas."""

    ativa = _ativa(simulacao_id)
    eventos_processados = []

    while True:
        with ativa.trava:
            if ativa.estado_execucao == EstadoExecucao.FALHOU:
                if not eventos_processados:
                    raise HTTPException(
                        409,
                        "A simulação falhou e não pode avançar.",
                    )

                return resultado_etapa(ativa, eventos_processados)

            if ativa.estado_execucao == EstadoExecucao.PAUSADA:
                if not eventos_processados:
                    raise HTTPException(
                        409,
                        "A simulação está pausada. Retome antes de executá-la.",
                    )

                return resultado_etapa(ativa, eventos_processados)

            if ativa.simulacao.concluida:
                _atualizar_estado_execucao(ativa)
                return resultado_etapa(ativa, eventos_processados)

            eventos_processados.extend(ativa.simulacao.proxima_etapa())
            _atualizar_estado_execucao(ativa)

            if ativa.simulacao.concluida:
                return resultado_etapa(ativa, eventos_processados)


@router.post(
    "/{simulacao_id}/pausar",
    response_model=RespostaControleExecucao,
)
def pausar(simulacao_id: int):
    """Pausa a simulação sem permitir novas etapas."""

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        if ativa.simulacao.concluida:
            _atualizar_estado_execucao(ativa)
            raise HTTPException(
                409,
                "Uma simulação concluída não pode ser pausada.",
            )
        if ativa.estado_execucao == EstadoExecucao.FALHOU:
            raise HTTPException(409, "Uma simulação com falha não pode ser pausada.")
        if ativa.estado_execucao == EstadoExecucao.PAUSADA:
            raise HTTPException(409, "A simulação já está pausada.")
        if ativa.estado_execucao == EstadoExecucao.AGUARDANDO:
            raise HTTPException(
                409,
                "A simulação ainda não foi iniciada e não pode ser pausada.",
            )

        sincronizar_relogio(ativa)
        if ativa.simulacao.concluida:
            _atualizar_estado_execucao(ativa)
            raise HTTPException(
                409,
                "Uma simulação concluída não pode ser pausada.",
            )

        ativa.estado_execucao = EstadoExecucao.PAUSADA
        return _resposta_controle(ativa, "Simulação pausada.")


@router.post(
    "/{simulacao_id}/retomar",
    response_model=RespostaControleExecucao,
)
def retomar(simulacao_id: int):
    """Retoma uma simulação pausada no ponto em que parou."""

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        if ativa.simulacao.concluida:
            _atualizar_estado_execucao(ativa)
            raise HTTPException(
                409,
                "Uma simulação concluída não pode ser retomada.",
            )
        if ativa.estado_execucao != EstadoExecucao.PAUSADA:
            raise HTTPException(
                409,
                "A simulação não está pausada e não pode ser retomada.",
            )

        ativa.marca_relogio_monotonic = ativa.relogio_monotonic()
        ativa.estado_execucao = EstadoExecucao.EXECUTANDO
        return _resposta_controle(ativa, "Simulação retomada.")


# Mapa, eventos e auditoria


@router.get("/{simulacao_id}/rotas", response_model=RotasSimulacao)
def obter_rotas(simulacao_id: int):
    """
    Rotas planejadas com o trajeto de cada viagem, para o mapa.

    A geometria e calculada na primeira consulta e reaproveitada.
    """

    ativa = _ativa(simulacao_id)

    with ativa.trava:
        sincronizar_relogio(ativa)
        _atualizar_estado_execucao(ativa)
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

    ativa = registro.obter(simulacao_id)
    if ativa is not None:
        with ativa.trava:
            sincronizar_relogio(ativa)
            _atualizar_estado_execucao(ativa)

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


def _exigir_nao_pausada(ativa: SimulacaoAtiva) -> None:
    if ativa.estado_execucao == EstadoExecucao.FALHOU:
        raise HTTPException(
            409,
            "A simulação falhou e não pode avançar.",
        )
    if ativa.estado_execucao == EstadoExecucao.PAUSADA:
        raise HTTPException(
            409,
            "A simulação está pausada. Retome antes de avançar.",
        )


def _atualizar_estado_execucao(ativa: SimulacaoAtiva) -> None:
    if ativa.simulacao.concluida:
        ativa.estado_execucao = EstadoExecucao.CONCLUIDA
    elif (
        ativa.simulacao.iniciada
        and ativa.estado_execucao
        not in {EstadoExecucao.PAUSADA, EstadoExecucao.FALHOU}
    ):
        ativa.estado_execucao = EstadoExecucao.EXECUTANDO


def _resposta_controle(
    ativa: SimulacaoAtiva,
    mensagem: str,
) -> RespostaControleExecucao:
    return RespostaControleExecucao(
        id=ativa.id,
        estado_execucao=ativa.estado_execucao,
        mensagem=mensagem,
        simulacao=montar_estado(ativa),
    )


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
