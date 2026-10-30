
from heapq import heappop, heappush
from itertools import count

from app.domain.models import Pedido
from app.domain.priority_scoring import calcular_prioridade


class FilaPrioridade:
    """Fila que atende primeiro os pedidos de maior prioridade."""

    def __init__(self) -> None:
        self._itens: list[tuple[float, int, Pedido]] = []
        self._ordem = count()

    def adicionar_pedido(self, pedido: Pedido) -> None:
        """Calcula a prioridade e adiciona o pedido a fila."""

        prioridade = calcular_prioridade(pedido)
        self.adicionar(pedido, prioridade)

    def adicionar(self, pedido: Pedido, prioridade: float) -> None:
        """Adiciona um pedido com sua pontuacao de prioridade."""

        heappush(
            self._itens,
            (-prioridade, next(self._ordem), pedido),
        )

    def retirar_proximo(self) -> Pedido:
        """Retira e retorna o pedido de maior prioridade."""

        if self.esta_vazia():
            raise IndexError("A fila de prioridade esta vazia.")

        _, _, pedido = heappop(self._itens)
        return pedido

    def proximo(self) -> Pedido | None:
        """Consulta o proximo pedido sem remove-lo da fila."""

        if self.esta_vazia():
            return None

        return self._itens[0][2]

    def esta_vazia(self) -> bool:
        """Indica se a fila esta vazia."""

        return len(self._itens) == 0

    def __len__(self) -> int:
        """Retorna a quantidade de pedidos na fila."""

        return len(self._itens)
