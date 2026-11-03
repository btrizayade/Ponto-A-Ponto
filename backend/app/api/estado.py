"""Conversao da simulacao em memoria para as respostas da API."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.api.registro import SimulacaoAtiva
from app.api.schemas import (
    Centro,
    EntregadorSimulacao,
    EstadoSimulacao,
    EventoResposta,
    Indicadores,
    ParadaMapa,
    PedidoResposta,
    PedidoSimulacao,
    ResultadoEtapa,
    RotaMapa,
    RotasSimulacao,
    ViagemMapa,
)
from app.domain.distribution import CentroDistribuicao, Parada, Viagem
from app.domain.models import Pedido, StatusPedido
from app.domain.priority_scoring import calcular_prioridade
from app.domain.simulation import EventoSimulacao, TipoEvento


def centro_resposta(centro: CentroDistribuicao) -> Centro:
    return Centro(
        nome=centro.nome,
        latitude=centro.coordenada.latitude,
        longitude=centro.coordenada.longitude,
    )


def pedido_resposta(pedido: Pedido) -> PedidoResposta:
    return PedidoResposta(**_dados_pedido(pedido))


def resultado_etapa(
    ativa: SimulacaoAtiva,
    eventos: list[EventoSimulacao],
) -> ResultadoEtapa:
    return ResultadoEtapa(
        eventos=[EventoResposta.model_validate(e) for e in eventos],
        estado=montar_estado(ativa),
    )


@dataclass
class _ResumoPedido:
    entregador_codigo: str | None = None
    viagem_numero: int | None = None
    entregue_em: datetime | None = None
    atraso_min: float | None = None
    observacao: str = ""


@dataclass
class _ResumoEntregador:
    viagem_atual: int | None = None
    iniciadas: set[int] = field(default_factory=set)
    concluidas: set[int] = field(default_factory=set)
    canceladas: set[int] = field(default_factory=set)
    entregas: int = 0
    entregas_atrasadas: int = 0
    distancia_percorrida_m: int = 0


class _Historico:
    """Resumo do historico por pedido e por entregador."""

    def __init__(self, eventos: list[EventoSimulacao]) -> None:
        self.pedidos: dict[str, _ResumoPedido] = defaultdict(_ResumoPedido)
        self.entregadores: dict[str, _ResumoEntregador] = defaultdict(
            _ResumoEntregador
        )
        self.atrasos: list[float] = []
        self.entregues_no_prazo = 0
        self.nao_atribuidos = 0
        self.devolvidos = 0

        for evento in eventos:
            self._aplicar(evento)

    def _aplicar(self, evento: EventoSimulacao) -> None:
        tipo = evento.tipo
        entregador = (
            self.entregadores[evento.entregador_codigo]
            if evento.entregador_codigo
            else None
        )

        if evento.pedido_codigo:
            pedido = self.pedidos[evento.pedido_codigo]
            pedido.observacao = evento.detalhe

            if tipo == TipoEvento.PEDIDO_ATRIBUIDO:
                pedido.entregador_codigo = evento.entregador_codigo
                pedido.viagem_numero = evento.viagem_numero
            elif tipo == TipoEvento.PEDIDO_DEVOLVIDO_A_FILA:
                pedido.entregador_codigo = None
                pedido.viagem_numero = None
                self.devolvidos += 1
            elif tipo == TipoEvento.PEDIDO_NAO_ATRIBUIDO:
                self.nao_atribuidos += 1
            elif tipo == TipoEvento.PEDIDO_ENTREGUE:
                pedido.entregue_em = evento.instante
                pedido.atraso_min = evento.atraso_min
                entregador.entregas += 1

                if evento.atraso_min:
                    self.atrasos.append(evento.atraso_min)
                    entregador.entregas_atrasadas += 1
                else:
                    self.entregues_no_prazo += 1

        if tipo == TipoEvento.VIAGEM_INICIADA:
            entregador.iniciadas.add(evento.viagem_numero)
            entregador.viagem_atual = evento.viagem_numero
        elif tipo == TipoEvento.VIAGEM_CONCLUIDA:
            entregador.concluidas.add(evento.viagem_numero)
            entregador.viagem_atual = None
            entregador.distancia_percorrida_m += evento.distancia_m or 0
        elif tipo == TipoEvento.VIAGEM_CANCELADA:
            entregador.canceladas.add(evento.viagem_numero)

    def situacao_viagem(self, entregador: str, numero: int) -> str:
        resumo = self.entregadores[entregador]

        if numero in resumo.canceladas:
            return "cancelada"

        if numero in resumo.concluidas:
            return "concluida"

        if numero in resumo.iniciadas:
            return "em_andamento"

        return "planejada"


def montar_estado(ativa: SimulacaoAtiva) -> EstadoSimulacao:
    simulacao = ativa.simulacao
    plano = simulacao.plano
    historico = _Historico(simulacao.historico)
    status = simulacao.status_dos_pedidos()
    posicoes = {
        p.codigo: posicao
        for posicao, p in enumerate(simulacao.ordem_fila, 1)
    }
    paradas = _paradas_por_pedido(plano)

    pedidos = []

    for pedido in simulacao.pedidos:
        resumo = historico.pedidos[pedido.codigo]
        parada, viagem = paradas.get(pedido.codigo, (None, None))
        # Sem previsao se ja entregue, devolvido a fila ou se a viagem
        # sairia depois do expediente (sera cancelada).
        previsao = (
            parada.saida_em
            if parada
            and resumo.entregador_codigo
            and resumo.entregue_em is None
            and viagem.partida_em <= simulacao.fim_expediente
            else None
        )

        pedidos.append(
            PedidoSimulacao(
                **_dados_pedido(pedido),
                status=status[pedido.codigo],
                posicao_fila=posicoes.get(pedido.codigo),
                prioridade=(
                    calcular_prioridade(pedido, agora=ativa.inicio)
                    if pedido.codigo in posicoes
                    else None
                ),
                entregador_codigo=resumo.entregador_codigo,
                viagem_numero=resumo.viagem_numero,
                previsao_entrega_em=previsao,
                entregue_em=resumo.entregue_em,
                atraso_min=resumo.atraso_min,
                observacao=resumo.observacao,
            )
        )

    return EstadoSimulacao(
        id=ativa.id,
        cenario_id=ativa.cenario_id,
        provedor=ativa.provedor,
        estrategia=ativa.estrategia,
        inicio=ativa.inicio,
        agora=simulacao.agora,
        proximo_instante=simulacao.proximo_instante,
        fim_expediente=simulacao.fim_expediente,
        iniciada=simulacao.iniciada,
        concluida=simulacao.concluida,
        centro=centro_resposta(simulacao.distribuidor.centro),
        indicadores=_indicadores(simulacao, historico, status),
        fila=_fila(simulacao.pedidos, status, posicoes),
        pedidos=pedidos,
        entregadores=_entregadores(simulacao, historico),
    )


def montar_rotas(ativa: SimulacaoAtiva) -> RotasSimulacao:
    """Rotas do plano com a geometria de cada viagem."""

    simulacao = ativa.simulacao
    historico = _Historico(simulacao.historico)
    status = simulacao.status_dos_pedidos()
    rotas = []

    for rota in simulacao.plano.rotas:
        codigo = rota.entregador.codigo
        rotas.append(
            RotaMapa(
                entregador_codigo=codigo,
                viagens=[
                    _viagem_mapa(
                        viagem,
                        historico.situacao_viagem(codigo, viagem.numero),
                        status,
                    )
                    for viagem in rota.viagens
                ],
            )
        )

    return RotasSimulacao(
        centro=centro_resposta(simulacao.distribuidor.centro),
        rotas=rotas,
        nao_atribuidos=[p.codigo for p in simulacao.plano.nao_atribuidos],
    )


def _viagem_mapa(
    viagem: Viagem,
    situacao: str,
    status: dict[str, StatusPedido],
) -> ViagemMapa:
    caminho = (
        [(p.latitude, p.longitude) for p in viagem.rota.pontos]
        if viagem.rota
        else []
    )

    return ViagemMapa(
        numero=viagem.numero,
        situacao=situacao,
        partida_em=viagem.partida_em,
        retorno_em=viagem.retorno_em,
        distancia_m=viagem.distancia_m,
        caminho=caminho,
        paradas=[
            ParadaMapa(
                ordem=ordem,
                pedido_codigo=parada.pedido.codigo,
                bairro=parada.pedido.bairro.nome,
                latitude=parada.pedido.bairro.latitude,
                longitude=parada.pedido.bairro.longitude,
                chegada_em=parada.chegada_em,
                saida_em=parada.saida_em,
                status=status[parada.pedido.codigo],
                atrasada=parada.atrasada,
            )
            for ordem, parada in enumerate(viagem.paradas, 1)
        ],
    )


def _dados_pedido(pedido: Pedido) -> dict:
    return {
        "codigo": pedido.codigo,
        "bairro": pedido.bairro.nome,
        "latitude": pedido.bairro.latitude,
        "longitude": pedido.bairro.longitude,
        "categoria_produto": pedido.categoria_produto,
        "cliente_clube": pedido.cliente_clube,
        "entrega_rapida": pedido.entrega_rapida,
        "sla_dias_uteis": pedido.sla_dias_uteis,
        "criado_em": pedido.criado_em,
        "prazo_entrega_em": pedido.prazo_entrega_em,
        "peso_kg": pedido.peso_kg,
        "volume_l": pedido.volume_l,
        "tempo_servico_min": pedido.tempo_servico_min,
    }


def _paradas_por_pedido(plano) -> dict[str, tuple[Parada, Viagem]]:
    if plano is None:
        return {}

    return {
        parada.pedido.codigo: (parada, viagem)
        for rota in plano.rotas
        for viagem in rota.viagens
        for parada in viagem.paradas
    }


def _fila(
    pedidos: list[Pedido],
    status: dict[str, StatusPedido],
    posicoes: dict[str, int],
) -> list[str]:
    """
    Pedidos na fila: primeiro os da ordem de planejamento, depois os
    que entraram depois do inicio, pela data de criacao.
    """

    na_fila = [p for p in pedidos if status[p.codigo] == StatusPedido.NA_FILA]
    na_fila.sort(
        key=lambda p: (
            posicoes.get(p.codigo, len(posicoes) + 1),
            p.criado_em,
        )
    )

    return [p.codigo for p in na_fila]


def _indicadores(simulacao, historico: _Historico, status) -> Indicadores:
    plano = simulacao.plano
    viagens = (
        [v for rota in plano.rotas for v in rota.viagens] if plano else []
    )
    resumos = historico.entregadores.values()
    por_status = {s: 0 for s in StatusPedido}

    for valor in status.values():
        por_status[valor] += 1

    return Indicadores(
        total_pedidos=len(status),
        por_status=por_status,
        entregues=por_status[StatusPedido.ENTREGUE],
        entregues_no_prazo=historico.entregues_no_prazo,
        entregues_atrasados=len(historico.atrasos),
        atraso_medio_min=(
            round(sum(historico.atrasos) / len(historico.atrasos), 1)
            if historico.atrasos
            else None
        ),
        nao_atribuidos=historico.nao_atribuidos,
        devolvidos_a_fila=historico.devolvidos,
        viagens_planejadas=len(viagens),
        viagens_concluidas=sum(len(r.concluidas) for r in resumos),
        viagens_canceladas=sum(len(r.canceladas) for r in resumos),
        distancia_planejada_m=plano.distancia_total_m if plano else 0,
        distancia_percorrida_m=sum(
            r.distancia_percorrida_m for r in resumos
        ),
    )


def _entregadores(simulacao, historico: _Historico) -> list[EntregadorSimulacao]:
    plano = simulacao.plano
    viagens_por_entregador = (
        {rota.entregador.codigo: rota.viagens for rota in plano.rotas}
        if plano
        else {}
    )
    resposta = []

    for entregador in simulacao.distribuidor.entregadores:
        codigo = entregador.codigo
        resumo = historico.entregadores[codigo]
        viagens = viagens_por_entregador.get(codigo, [])
        atual = next(
            (v for v in viagens if v.numero == resumo.viagem_atual), None
        )
        proxima = next(
            (
                v
                for v in viagens
                if historico.situacao_viagem(codigo, v.numero) == "planejada"
                and v.partida_em <= simulacao.fim_expediente
            ),
            None,
        )

        resposta.append(
            EntregadorSimulacao(
                codigo=codigo,
                situacao="em_viagem" if atual else "no_centro",
                viagem_atual=atual.numero if atual else None,
                retorno_previsto_em=atual.retorno_em if atual else None,
                proxima_partida_em=proxima.partida_em if proxima else None,
                viagens_planejadas=len(viagens),
                viagens_concluidas=len(resumo.concluidas),
                viagens_canceladas=len(resumo.canceladas),
                entregas=resumo.entregas,
                entregas_atrasadas=resumo.entregas_atrasadas,
                distancia_percorrida_m=resumo.distancia_percorrida_m,
            )
        )

    return resposta
