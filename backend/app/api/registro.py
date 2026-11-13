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
            return any(
                ativa.estado_execucao
                in {EstadoExecucao.EXECUTANDO, EstadoExecucao.PAUSADA}
                and not ativa.simulacao.concluida
                for ativa in self._ativas.values()
            )

    def limpar(self) -> None:
        with self._trava:
            self._ativas.clear()


registro = RegistroSimulacoes()
