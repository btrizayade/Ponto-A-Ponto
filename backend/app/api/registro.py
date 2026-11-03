from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock

from app.domain.simulation import Simulacao
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
    rotas_montadas: bool = False
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

    def limpar(self) -> None:
        with self._trava:
            self._ativas.clear()


registro = RegistroSimulacoes()
