from dataclasses import dataclass, field
from collections.abc import Callable
from datetime import datetime
from threading import Lock
from time import monotonic

from app.domain.simulation import (
    SEGUNDOS_REAIS_POR_HORA_SIMULADA,
    EstadoExecucao,
    Simulacao,
)
from app.infrastructure.auditoria_repository import AuditoriaSimulacao


@dataclass
class SimulacaoAtiva:
    """
    Simulacao em andamento controlada pela API.

    A trava garante que duas requisicoes nao avancem ou leiam a
    mesma simulacao ao mesmo tempo.
    """

    simulacao: Simulacao
    auditoria: AuditoriaSimulacao
    cenario_id: int
    inicio: datetime
    provedor: str
    estrategia: str
    estado_execucao: EstadoExecucao = EstadoExecucao.AGUARDANDO
    erro_execucao: str | None = None
    rotas_montadas: bool = False
    marca_relogio_monotonic: float | None = None
    segundos_reais_por_hora_simulada: int = int(
        SEGUNDOS_REAIS_POR_HORA_SIMULADA
    )
    relogio_monotonic: Callable[[], float] = monotonic
    trava: Lock = field(default_factory=Lock, repr=False)

    @property
    def id(self) -> int:
        return self.auditoria.simulacao_id


class RegistroSimulacoes:
    """
    Simulacoes ativas, mantidas em memoria pelo servidor.

    Se o servidor reiniciar, as simulacoes ativas se perdem, mas o
    historico de qualquer simulacao continua na auditoria do SQLite.
    """

    def __init__(self) -> None:
        self._ativas: dict[int, SimulacaoAtiva] = {}
        self._trava = Lock()
        self._reserva_criacao: object | None = None

    def reservar_criacao(self) -> object | None:
        """Reserva atomicamente o início de uma operação.

        A reserva é um token, não um lock mantido durante a criação ou a
        execução. Ela continua válida enquanto o chamador prepara e agenda
        o executor, impedindo outra requisição de atravessar esse intervalo.
        """

        with self._trava:
            if self._reserva_criacao is not None or self._ha_operacao_ativa():
                return None

            reserva = object()
            self._reserva_criacao = reserva
            return reserva

    def adicionar_reservada(
        self,
        reserva: object,
        ativa: SimulacaoAtiva,
    ) -> None:
        """Registra a simulação somente para quem possui a reserva atual."""

        with self._trava:
            if self._reserva_criacao is not reserva:
                raise RuntimeError("A reserva de criação não é mais válida.")
            self._ativas[ativa.id] = ativa

    def liberar_reserva(self, reserva: object) -> None:
        """Libera a reserva, sem afetar uma reserva posterior."""

        with self._trava:
            if self._reserva_criacao is reserva:
                self._reserva_criacao = None

    def remover(self, simulacao_id: int) -> SimulacaoAtiva | None:
        """Remove uma instância que não chegou a iniciar o executor."""

        with self._trava:
            return self._ativas.pop(simulacao_id, None)

    def adicionar(self, ativa: SimulacaoAtiva) -> None:
        with self._trava:
            self._ativas[ativa.id] = ativa

    def obter(self, simulacao_id: int) -> SimulacaoAtiva | None:
        with self._trava:
            return self._ativas.get(simulacao_id)

    def ids(self) -> set[int]:
        with self._trava:
            return set(self._ativas)

    def existe_operacao_em_andamento(self) -> bool:
        """Indica se alguma execução precisa ser preservada em memória."""

        with self._trava:
            return (
                self._reserva_criacao is not None
                or self._ha_operacao_ativa()
            )

    def _ha_operacao_ativa(self) -> bool:
        return any(
            ativa.estado_execucao
            in {EstadoExecucao.EXECUTANDO, EstadoExecucao.PAUSADA}
            and not ativa.simulacao.concluida
            for ativa in self._ativas.values()
        )

    def limpar(self) -> None:
        with self._trava:
            self._ativas.clear()
            self._reserva_criacao = None


registro = RegistroSimulacoes()
