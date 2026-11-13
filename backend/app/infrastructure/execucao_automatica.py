"""Execucao automatica das simulacoes mantidas em memoria pelo backend."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.api.registro import SimulacaoAtiva
from app.domain.simulation import EstadoExecucao

logger = logging.getLogger(__name__)


IntervalWait = Callable[[float, asyncio.Event], Awaitable[bool]]


async def _aguardar_intervalo(
    intervalo_segundos: float,
    encerramento: asyncio.Event,
) -> bool:
    """Espera o intervalo ou retorna cedo quando o servidor encerra."""

    try:
        await asyncio.wait_for(
            encerramento.wait(),
            timeout=intervalo_segundos,
        )
    except TimeoutError:
        return False

    return True


class ExecucaoAutomatica:
    """Mantem no maximo uma tarefa automatica para cada simulacao."""

    def __init__(
        self,
        intervalo_segundos: float = 0.05,
        habilitada: bool = True,
        aguardar: IntervalWait = _aguardar_intervalo,
    ) -> None:
        if intervalo_segundos <= 0:
            raise ValueError("O intervalo de execução deve ser maior que zero.")

        self.intervalo_segundos = intervalo_segundos
        self.habilitada = habilitada
        self._aguardar = aguardar
        self._encerramento = asyncio.Event()
        self._trava = asyncio.Lock()
        self._tarefas: dict[int, asyncio.Task[None]] = {}

    async def iniciar(self, simulacao_id: int, ativa: SimulacaoAtiva) -> None:
        """Agenda uma execução; chamadas repetidas não criam outro executor."""

        if not self.habilitada:
            return

        async with self._trava:
            tarefa_existente = self._tarefas.get(simulacao_id)
            if tarefa_existente is not None and not tarefa_existente.done():
                return

            with ativa.trava:
                if ativa.simulacao.concluida:
                    ativa.estado_execucao = EstadoExecucao.CONCLUIDA
                    return

                ativa.estado_execucao = EstadoExecucao.EXECUTANDO
                ativa.marca_relogio_monotonic = ativa.relogio_monotonic()

            self._tarefas[simulacao_id] = asyncio.create_task(
                self._executar(simulacao_id, ativa),
                name=f"simulacao-{simulacao_id}",
            )

    async def encerrar(self) -> None:
        """Pede encerramento e aguarda as etapas síncronas em andamento."""

        self._encerramento.set()
        async with self._trava:
            tarefas = list(self._tarefas.values())

        if tarefas:
            await asyncio.gather(*tarefas, return_exceptions=True)

    @property
    def quantidade_tarefas_ativas(self) -> int:
        return sum(not tarefa.done() for tarefa in self._tarefas.values())

    async def _executar(
        self,
        simulacao_id: int,
        ativa: SimulacaoAtiva,
    ) -> None:
        try:
            while not self._encerramento.is_set():
                if await self._aguardar(
                    self.intervalo_segundos,
                    self._encerramento,
                ):
                    return

                with ativa.trava:
                    if ativa.simulacao.concluida:
                        ativa.estado_execucao = EstadoExecucao.CONCLUIDA
                        return
                    if ativa.estado_execucao == EstadoExecucao.PAUSADA:
                        continue
                    if ativa.estado_execucao != EstadoExecucao.EXECUTANDO:
                        return

                await asyncio.to_thread(self._avancar_relogio, ativa)

                with ativa.trava:
                    if ativa.simulacao.concluida:
                        ativa.estado_execucao = EstadoExecucao.CONCLUIDA
                        return
        except Exception as erro:
            logger.exception(
                "Falha na execução automática da simulação %s",
                simulacao_id,
            )
            with ativa.trava:
                ativa.estado_execucao = EstadoExecucao.FALHOU
                ativa.erro_execucao = str(erro)[:500]
        finally:
            async with self._trava:
                tarefa = self._tarefas.get(simulacao_id)
                if tarefa is asyncio.current_task():
                    self._tarefas.pop(simulacao_id, None)

    @staticmethod
    def _avancar_relogio(ativa: SimulacaoAtiva) -> None:
        """Atualiza relógio e eventos vencidos usando uma referência monotônica."""

        with ativa.trava:
            if ativa.estado_execucao != EstadoExecucao.EXECUTANDO:
                return

            sincronizar_relogio(ativa)
            if ativa.simulacao.concluida:
                ativa.estado_execucao = EstadoExecucao.CONCLUIDA


def sincronizar_relogio(
    ativa: SimulacaoAtiva,
    agora_monotonic: float | None = None,
) -> None:
    """Aplica o tempo real desde o último marco, sem contar pausas."""

    marca = ativa.marca_relogio_monotonic
    velocidade = ativa.segundos_reais_por_hora_simulada
    if (
        marca is None
        or velocidade is None
        or ativa.estado_execucao != EstadoExecucao.EXECUTANDO
    ):
        return

    agora = (
        ativa.relogio_monotonic()
        if agora_monotonic is None
        else agora_monotonic
    )
    decorrido = max(0.0, agora - marca)
    ativa.simulacao.avancar_tempo_real(decorrido, velocidade)
    ativa.marca_relogio_monotonic = agora
    if ativa.simulacao.concluida:
        ativa.estado_execucao = EstadoExecucao.CONCLUIDA
