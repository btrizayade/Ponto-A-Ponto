from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from heapq import heappop, heappush
from itertools import count

from app.domain.distribution import (
    DistribuidorPedidos,
    Parada,
    PlanoDistribuicao,
    Viagem,
)
from app.domain.models import Entregador, Pedido, StatusPedido
from app.domain.priority_queue import FilaPrioridadeHeap
from app.domain.sla import FUSO_HORARIO, HORA_FIM, HORA_INICIO

SEGUNDOS_REAIS_POR_HORA_SIMULADA = 15.0


class TipoEvento(str, Enum):
    """Acontecimentos registrados durante a simulacao."""

    SIMULACAO_INICIADA = "simulacao_iniciada"
    PEDIDO_NA_FILA = "pedido_na_fila"
    PEDIDO_ATRIBUIDO = "pedido_atribuido"
    PEDIDO_NAO_ATRIBUIDO = "pedido_nao_atribuido"
    PEDIDO_ENTREGUE = "pedido_entregue"
    VIAGEM_CONCLUIDA = "viagem_concluida"
    VIAGEM_CANCELADA = "viagem_cancelada"
    PEDIDO_DEVOLVIDO_A_FILA = "pedido_devolvido_a_fila"
    VIAGEM_INICIADA = "viagem_iniciada"
    PEDIDO_EM_ROTA = "pedido_em_rota"
    SIMULACAO_CONCLUIDA = "simulacao_concluida"


class EstadoExecucao(str, Enum):
    """Estado operacional controlado pela API para uma simulacao ativa."""

    AGUARDANDO = "aguardando"
    EXECUTANDO = "executando"
    PAUSADA = "pausada"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"


# Ordem de processamento de eventos no mesmo instante: o caminhao
# conclui a entrega e retorna antes de iniciar a proxima viagem.
_ORDEM_NO_INSTANTE = {tipo: ordem for ordem, tipo in enumerate(TipoEvento)}


@dataclass(frozen=True)
class EventoSimulacao:
    """
    Registro de um acontecimento da simulacao.

    Eventos de pedido mudam o status de um unico pedido, informado
    em status_anterior e status_novo.
    """

    sequencia: int
    instante: datetime
    tipo: TipoEvento
    pedido_codigo: str | None = None
    entregador_codigo: str | None = None
    viagem_numero: int | None = None
    status_anterior: StatusPedido | None = None
    status_novo: StatusPedido | None = None
    atraso_min: float | None = None
    distancia_m: int | None = None
    detalhe: str = ""


Observador = Callable[[EventoSimulacao], None]


class RelogioSimulado:
    """Relogio da simulacao, que so avanca."""

    def __init__(self, inicio: datetime) -> None:
        _validar_instante(inicio, "inicio")
        self._agora = inicio

    @property
    def agora(self) -> datetime:
        return self._agora

    def avancar_para(self, instante: datetime) -> None:
        _validar_instante(instante, "instante")

        if instante < self._agora:
            raise ValueError("O relogio da simulacao nao pode voltar.")

        self._agora = instante


class Simulacao:
    """
    Executa um plano de distribuicao em etapas, com relogio simulado.

    Os pedidos recebidos formam o snapshot do cenario e entram juntos
    na fila inicial, independentemente de suas datas historicas de
    criacao. Essas datas e os prazos originais nao sao reescritos. O
    inicio escolhido define o relogio e o expediente da operacao.

    O expediente vai das 09h as 17h. Um caminhao pode iniciar uma
    viagem ate as 17h, mesmo que retorne depois. Viagens que sairiam
    depois disso sao canceladas e seus pedidos voltam para a fila.

    Cada mudanca de status e cada acontecimento geram um evento, que
    fica no historico e e enviado aos observadores, como a auditoria.
    """

    def __init__(
        self,
        pedidos: Sequence[Pedido],
        distribuidor: DistribuidorPedidos,
        inicio: datetime,
        disponibilidade: Mapping[str, datetime] | None = None,
        observadores: Sequence[Observador] = (),
    ) -> None:
        _validar_inicio_no_expediente(inicio)

        codigos = [p.codigo for p in pedidos]
        if len(set(codigos)) != len(codigos):
            raise ValueError("Os codigos dos pedidos devem ser unicos.")

        self._distribuidor = distribuidor
        self._disponibilidade = disponibilidade
        self._observadores = list(observadores)
        self._relogio = RelogioSimulado(inicio)
        self._fim_expediente = inicio.astimezone(FUSO_HORARIO).replace(
            hour=HORA_FIM.hour,
            minute=HORA_FIM.minute,
            second=0,
            microsecond=0,
        )
        self._pedidos = list(pedidos)

        self._status = {
            p.codigo: StatusPedido.PENDENTE for p in self._pedidos
        }
        self._historico: list[EventoSimulacao] = []
        self._agenda: list[tuple] = []
        self._desempate = count()
        self._plano: PlanoDistribuicao | None = None
        self._ordem_fila: list[Pedido] = []
        self._encerrada = False

    # Consulta do estado

    @property
    def agora(self) -> datetime:
        return self._relogio.agora

    @property
    def iniciada(self) -> bool:
        return self._plano is not None

    @property
    def concluida(self) -> bool:
        return self._encerrada

    @property
    def plano(self) -> PlanoDistribuicao | None:
        return self._plano

    @property
    def pedidos(self) -> list[Pedido]:
        """Pedidos que fazem parte da simulacao."""

        return list(self._pedidos)

    @property
    def distribuidor(self) -> DistribuidorPedidos:
        return self._distribuidor

    @property
    def ordem_fila(self) -> list[Pedido]:
        """Pedidos na ordem de prioridade usada no planejamento."""

        return list(self._ordem_fila)

    @property
    def historico(self) -> list[EventoSimulacao]:
        return list(self._historico)

    @property
    def proximo_instante(self) -> datetime | None:
        """Instante da proxima etapa, ou None se nao houver."""

        if self._encerrada:
            return None

        return self._agenda[0][0] if self._agenda else self.agora

    @property
    def fim_expediente(self) -> datetime:
        return self._fim_expediente

    def status_do_pedido(self, codigo: str) -> StatusPedido:
        if codigo not in self._status:
            raise KeyError(f"Pedido {codigo} nao faz parte da simulacao.")

        return self._status[codigo]

    def status_dos_pedidos(self) -> dict[str, StatusPedido]:
        return dict(self._status)

    def adicionar_observador(self, observador: Observador) -> None:
        self._observadores.append(observador)

    # Execucao

    def iniciar(self) -> list[EventoSimulacao]:
        """Monta a fila, planeja as viagens e agenda os eventos."""

        if self.iniciada:
            raise RuntimeError("A simulacao ja foi iniciada.")

        inicio = self.agora
        pedidos_do_snapshot = self._pedidos

        fila = FilaPrioridadeHeap()
        for pedido in pedidos_do_snapshot:
            fila.adicionar_pedido(pedido, agora=inicio)

        ordem_fila = [
            fila.retirar_proximo()
            for _ in range(len(pedidos_do_snapshot))
        ]
        # Se o planejamento falhar (servico de mapas), nada muda e
        # a simulacao pode ser iniciada de novo.
        self._plano = self._distribuidor.planejar(
            ordem_fila,
            inicio,
            self._disponibilidade,
        )
        self._ordem_fila = ordem_fila

        self._agendar_inicio(pedidos_do_snapshot)
        self._agendar_viagens()

        return self._processar_ate(inicio)

    def proxima_etapa(self) -> list[EventoSimulacao]:
        """Avanca ate o proximo instante com eventos e os processa."""

        if not self.iniciada:
            return self.iniciar()

        if self._encerrada:
            return []

        return self._processar_ate(self.proximo_instante)

    def avancar_ate(self, instante: datetime) -> list[EventoSimulacao]:
        """Processa todos os eventos ate o instante informado."""

        _validar_instante(instante, "instante")

        if instante < self.agora:
            raise ValueError("O relogio da simulacao nao pode voltar.")

        eventos = [] if self.iniciada else self.iniciar()

        return eventos + self._processar_ate(instante)

    def avancar(self, minutos: float) -> list[EventoSimulacao]:
        """Avanca o relogio pelo numero de minutos informado."""

        if minutos < 0:
            raise ValueError("Informe um numero de minutos nao negativo.")

        return self.avancar_ate(self.agora + timedelta(minutes=minutos))

    def avancar_tempo_real(
        self,
        segundos_reais: float,
        segundos_reais_por_hora_simulada: float = SEGUNDOS_REAIS_POR_HORA_SIMULADA,
    ) -> list[EventoSimulacao]:
        """Converte tempo monotônico real em avanço contínuo do relógio."""

        if segundos_reais < 0:
            raise ValueError("O tempo real decorrido nao pode ser negativo.")
        if segundos_reais_por_hora_simulada <= 0:
            raise ValueError(
                "A velocidade da simulacao deve ser maior que zero."
            )

        eventos = [] if self.iniciada else self.iniciar()
        if self._encerrada:
            return eventos

        horas_simuladas = segundos_reais / segundos_reais_por_hora_simulada
        alvo = self.agora + timedelta(hours=horas_simuladas)
        return eventos + self._processar_ate(alvo)

    def executar_ate_o_fim(self) -> list[EventoSimulacao]:
        """Processa todos os eventos restantes."""

        eventos = [] if self.iniciada else self.iniciar()

        while not self._encerrada:
            eventos += self._processar_ate(self.proximo_instante)

        return eventos

    # Agenda

    def _agendar(self, evento: EventoSimulacao) -> None:
        heappush(
            self._agenda,
            (
                evento.instante,
                _ORDEM_NO_INSTANTE[evento.tipo],
                next(self._desempate),
                evento,
            ),
        )

    def _agendar_inicio(
        self,
        pedidos: Sequence[Pedido],
    ) -> None:
        inicio = self.agora
        plano = self._plano
        posicao = {p.codigo: i for i, p in enumerate(self._ordem_fila, 1)}
        detalhe = (
            f"{len(pedidos)} pedidos na fila, "
            f"{len(self._distribuidor.entregadores)} entregadores, "
            f"centro {self._distribuidor.centro.nome}"
        )

        self._agendar(
            _evento(inicio, TipoEvento.SIMULACAO_INICIADA, detalhe=detalhe)
        )

        for pedido in self._ordem_fila:
            self._agendar(
                _evento(
                    inicio,
                    TipoEvento.PEDIDO_NA_FILA,
                    pedido=pedido,
                    status_novo=StatusPedido.NA_FILA,
                    detalhe=f"posicao {posicao[pedido.codigo]} na fila",
                )
            )

        for pedido in self._ordem_fila:
            try:
                entregador, viagem = plano.rota_do_pedido(pedido.codigo)
            except KeyError:
                continue

            self._agendar(
                _evento(
                    inicio,
                    TipoEvento.PEDIDO_ATRIBUIDO,
                    pedido=pedido,
                    entregador=entregador,
                    viagem=viagem,
                    status_novo=StatusPedido.ATRIBUIDO,
                )
            )

        for pedido in plano.nao_atribuidos:
            self._agendar(
                _evento(
                    inicio,
                    TipoEvento.PEDIDO_NAO_ATRIBUIDO,
                    pedido=pedido,
                    detalhe="sem caminhao com capacidade ou sem rota",
                )
            )

    def _agendar_viagens(self) -> None:
        for rota in self._plano.rotas:
            for viagem in rota.viagens:
                if viagem.partida_em > self._fim_expediente:
                    self._agendar_cancelamento(rota.entregador, viagem)
                else:
                    self._agendar_execucao(rota.entregador, viagem)

    def _agendar_execucao(
        self,
        entregador: Entregador,
        viagem: Viagem,
    ) -> None:
        codigos = ", ".join(p.codigo for p in viagem.pedidos)

        self._agendar(
            _evento(
                viagem.partida_em,
                TipoEvento.VIAGEM_INICIADA,
                entregador=entregador,
                viagem=viagem,
                detalhe=f"pedidos {codigos}",
            )
        )

        for pedido in viagem.pedidos:
            self._agendar(
                _evento(
                    viagem.partida_em,
                    TipoEvento.PEDIDO_EM_ROTA,
                    pedido=pedido,
                    entregador=entregador,
                    viagem=viagem,
                    status_novo=StatusPedido.EM_ROTA,
                )
            )

        for parada in viagem.paradas:
            self._agendar(
                _evento(
                    parada.saida_em,
                    TipoEvento.PEDIDO_ENTREGUE,
                    pedido=parada.pedido,
                    entregador=entregador,
                    viagem=viagem,
                    status_novo=StatusPedido.ENTREGUE,
                    atraso_min=_atraso_min(parada),
                    detalhe=_detalhe_entrega(parada),
                )
            )

        self._agendar(
            _evento(
                viagem.retorno_em,
                TipoEvento.VIAGEM_CONCLUIDA,
                entregador=entregador,
                viagem=viagem,
                distancia_m=viagem.distancia_m,
            )
        )

    def _agendar_cancelamento(
        self,
        entregador: Entregador,
        viagem: Viagem,
    ) -> None:
        # A viagem nao sai: o cancelamento ocorre no fim do expediente.
        instante = max(self._fim_expediente, self.agora)
        partida = viagem.partida_em.astimezone(FUSO_HORARIO)

        self._agendar(
            _evento(
                instante,
                TipoEvento.VIAGEM_CANCELADA,
                entregador=entregador,
                viagem=viagem,
                detalhe=(
                    f"sairia as {partida:%H:%M}, depois do fim do "
                    f"expediente ({HORA_FIM:%H:%M})"
                ),
            )
        )

        for pedido in viagem.pedidos:
            self._agendar(
                _evento(
                    instante,
                    TipoEvento.PEDIDO_DEVOLVIDO_A_FILA,
                    pedido=pedido,
                    entregador=entregador,
                    viagem=viagem,
                    status_novo=StatusPedido.NA_FILA,
                    detalhe="viagem cancelada pelo fim do expediente",
                )
            )

    # Processamento

    def _processar_ate(self, instante: datetime) -> list[EventoSimulacao]:
        processados = []

        while self._agenda and self._agenda[0][0] <= instante:
            processados.append(self._emitir(self._agenda[0][-1]))
            heappop(self._agenda)

        if not self._agenda and not self._encerrada:
            processados.append(
                self._emitir(
                    _evento(
                        self.agora,
                        TipoEvento.SIMULACAO_CONCLUIDA,
                        detalhe=self._resumo(),
                    )
                )
            )
            self._encerrada = True

        # Depois de concluida, o relogio para no instante da conclusao.
        if instante > self.agora and not self._encerrada:
            self._relogio.avancar_para(instante)

        return processados

    def _emitir(self, evento: EventoSimulacao) -> EventoSimulacao:
        """
        Notifica os observadores e so entao aplica o evento.

        Se um observador falhar (por exemplo, a auditoria nao gravar),
        o estado da simulacao nao muda e o evento continua na agenda,
        para que uma nova tentativa nao deixe lacunas no historico.
        Na nova tentativa, o mesmo evento (mesma sequencia) e enviado
        de novo a todos os observadores, inclusive aos que ja o tinham
        recebido; por isso, os observadores devem ignorar repeticoes.
        """

        anterior = (
            self._status[evento.pedido_codigo]
            if evento.status_novo is not None
            else None
        )
        evento = replace(
            evento,
            sequencia=len(self._historico) + 1,
            status_anterior=anterior,
        )

        for observador in self._observadores:
            observador(evento)

        self._relogio.avancar_para(evento.instante)

        if evento.status_novo is not None:
            self._status[evento.pedido_codigo] = evento.status_novo

        self._historico.append(evento)

        return evento

    def _resumo(self) -> str:
        totais = {status: 0 for status in StatusPedido}

        for status in self._status.values():
            totais[status] += 1

        return ", ".join(
            f"{status.value}: {quantidade}"
            for status, quantidade in totais.items()
            if quantidade
        )


def _evento(
    instante: datetime,
    tipo: TipoEvento,
    pedido: Pedido | None = None,
    entregador: Entregador | None = None,
    viagem: Viagem | None = None,
    status_novo: StatusPedido | None = None,
    atraso_min: float | None = None,
    distancia_m: int | None = None,
    detalhe: str = "",
) -> EventoSimulacao:
    """Cria um evento agendado; a sequencia e definida ao emitir."""

    return EventoSimulacao(
        sequencia=0,
        instante=instante,
        tipo=tipo,
        pedido_codigo=pedido.codigo if pedido else None,
        entregador_codigo=entregador.codigo if entregador else None,
        viagem_numero=viagem.numero if viagem else None,
        status_novo=status_novo,
        atraso_min=atraso_min,
        distancia_m=distancia_m,
        detalhe=detalhe,
    )


def _atraso_min(parada: Parada) -> float | None:
    """Minutos corridos de atraso na conclusao (0 se no prazo)."""

    folga = parada.folga_min

    if folga is None:
        return None

    return max(0.0, -folga)


def _detalhe_entrega(parada: Parada) -> str:
    if parada.pedido.prazo_entrega_em is None:
        return "sem prazo de entrega"

    if parada.atrasada:
        return f"atrasada em {-parada.folga_min:.0f} min"

    return "no prazo"


def _validar_instante(instante: datetime, nome: str) -> None:
    if not isinstance(instante, datetime):
        raise TypeError(f"O {nome} deve ser um datetime.")

    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError(f"O {nome} deve possuir fuso horario.")


def _validar_inicio_no_expediente(inicio: datetime) -> None:
    _validar_instante(inicio, "inicio")
    local = inicio.astimezone(FUSO_HORARIO)

    if local.weekday() >= 5:
        raise ValueError("A simulacao deve iniciar em um dia util.")

    if not HORA_INICIO <= local.time() < HORA_FIM:
        raise ValueError(
            f"A simulacao deve iniciar entre {HORA_INICIO:%H:%M} e "
            f"{HORA_FIM:%H:%M}."
        )
