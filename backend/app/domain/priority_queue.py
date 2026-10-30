from datetime import datetime, timezone
from heapq import heapify, heappop, heappush
from itertools import count

from app.domain.models import Pedido
from app.domain.priority_scoring import calcular_prioridade


class FilaPrioridade:
    """Fila que atende primeiro os pedidos de maior prioridade."""

    def __init__(self) -> None:
        self._itens: list[
            tuple[float, int, Pedido, bool, float | None]
        ] = []
        self._ordem = count()

    def adicionar_pedido(
        self,
        pedido: Pedido,
        agora: datetime | None = None,
        tempo_estimado_entrega_min: float | None = None,
    ) -> None:
        """Calcula a prioridade e adiciona um pedido a fila."""

        prioridade = calcular_prioridade(
            pedido,
            agora=agora,
            tempo_estimado_entrega_min=tempo_estimado_entrega_min,
        )

        self._inserir(
            pedido,
            prioridade,
            atualizar_automaticamente=True,
            tempo_estimado_entrega_min=tempo_estimado_entrega_min,
        )

    def adicionar(self, pedido: Pedido, prioridade: float) -> None:
        """Adiciona um pedido com prioridade manual e fixa."""

        self._inserir(
            pedido,
            prioridade,
            atualizar_automaticamente=False,
            tempo_estimado_entrega_min=None,
        )

    def _inserir(
        self,
        pedido: Pedido,
        prioridade: float,
        atualizar_automaticamente: bool,
        tempo_estimado_entrega_min: float | None,
    ) -> None:
        """Insere um pedido preservando sua ordem de entrada."""

        heappush(
            self._itens,
            (
                -prioridade,
                next(self._ordem),
                pedido,
                atualizar_automaticamente,
                tempo_estimado_entrega_min,
            ),
        )

    def atualizar_prioridades(
        self,
        agora: datetime | None = None,
    ) -> None:
        """Recalcula as prioridades automaticas e reorganiza o heap."""

        if agora is None:
            agora = datetime.now(timezone.utc)

        itens_atualizados = []

        for (
            prioridade_negativa,
            ordem,
            pedido,
            automatica,
            tempo_estimado,
        ) in self._itens:

            if automatica:
                prioridade_negativa = -calcular_prioridade(
                    pedido,
                    agora=agora,
                    tempo_estimado_entrega_min=tempo_estimado,
                )

            itens_atualizados.append(
                (
                    prioridade_negativa,
                    ordem,
                    pedido,
                    automatica,
                    tempo_estimado,
                )
            )

        self._itens = itens_atualizados
        heapify(self._itens)

    def atualizar_estimativa_entrega(
        self,
        pedido: Pedido,
        tempo_estimado_entrega_min: float | None,
        agora: datetime | None = None,
    ) -> None:
        """Atualiza a estimativa de viagem de um pedido na fila."""

        for indice, item in enumerate(self._itens):
            _, ordem, pedido_atual, automatica, _ = item

            if pedido_atual is pedido:
                if not automatica:
                    raise ValueError(
                        "Pedidos com prioridade manual nao podem "
                        "ter estimativa atualizada."
                    )

                prioridade = calcular_prioridade(
                    pedido,
                    agora=agora,
                    tempo_estimado_entrega_min=tempo_estimado_entrega_min,
                )

                self._itens[indice] = (
                    -prioridade,
                    ordem,
                    pedido,
                    True,
                    tempo_estimado_entrega_min,
                )

                heapify(self._itens)
                return

        raise ValueError("Pedido nao encontrado na fila.")

    def retirar_proximo(
        self,
        agora: datetime | None = None,
    ) -> Pedido:
        """Atualiza as prioridades e retira o pedido mais prioritario."""

        self.atualizar_prioridades(agora)

        if self.esta_vazia():
            raise IndexError("A fila de prioridade esta vazia.")

        _, _, pedido, _, _ = heappop(self._itens)

        return pedido

    def proximo(
        self,
        agora: datetime | None = None,
    ) -> Pedido | None:
        """Atualiza as prioridades e consulta o proximo pedido."""

        self.atualizar_prioridades(agora)

        if self.esta_vazia():
            return None

        return self._itens[0][2]

    def esta_vazia(self) -> bool:
        """Indica se a fila esta vazia."""

        return len(self._itens) == 0

    def __len__(self) -> int:
        """Retorna a quantidade de pedidos na fila."""

        return len(self._itens)
