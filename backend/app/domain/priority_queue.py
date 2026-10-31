
from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import heapify, heappop, heappush
from itertools import count

from app.domain.models import Pedido
from app.domain.priority_scoring import calcular_prioridade
from app.domain.sla import calcular_minutos_operacionais

FATOR_COMPACTACAO = 2
MIN_ENTRADAS_COMPACTACAO = 64

ChavePedido = str
IdentificadorOrdenacao = tuple[int, int | str]

EntradaHeap = tuple[
    float,
    float,
    datetime,
    IdentificadorOrdenacao,
    int,
    int,
    ChavePedido,
    Pedido,
]


@dataclass
class _PedidoAtivo:
    pedido: Pedido
    prioridade: float
    atualizar_automaticamente: bool
    tempo_estimado_entrega_min: float | None
    ordem: int
    folga_sla_min: float
    versao: int = 0


class FilaPrioridadeHeap:
    """Fila heap que atende primeiro os pedidos de maior prioridade."""

    def __init__(self) -> None:
        self._itens: list[EntradaHeap] = []
        self._pedidos_ativos: dict[ChavePedido, _PedidoAtivo] = {}
        self._pedidos_processados: set[ChavePedido] = set()
        self._ordem = count()

    @staticmethod
    def _chave_pedido(pedido: Pedido) -> ChavePedido:
        """Identifica o pedido pelo codigo, unico dentro do cenario."""

        return pedido.codigo

    @staticmethod
    def _identificador_ordenacao(
        pedido: Pedido,
    ) -> IdentificadorOrdenacao:
        """Retorna o identificador usado no desempate."""

        if pedido.id is not None:
            return (0, pedido.id)

        return (1, pedido.codigo)

    @staticmethod
    def _calcular_folga_sla(
        pedido: Pedido,
        tempo_estimado_entrega_min: float | None,
        agora: datetime,
    ) -> float:
        """Calcula a folga operacional restante para a entrega."""

        prazo = pedido.prazo_entrega_em

        if prazo is None:
            return float("inf")

        if (
            agora.tzinfo is None
            or agora.utcoffset() is None
            or prazo.tzinfo is None
            or prazo.utcoffset() is None
        ):
            raise ValueError(
                "As datas precisam possuir fuso horario definido."
            )

        if agora <= prazo:
            minutos_ate_prazo = calcular_minutos_operacionais(
                agora,
                prazo,
            )
        else:
            minutos_ate_prazo = -calcular_minutos_operacionais(
                prazo,
                agora,
            )

        tempo_estimado = (
            tempo_estimado_entrega_min
            if tempo_estimado_entrega_min is not None
            else 0.0
        )

        return minutos_ate_prazo - tempo_estimado

    def _criar_entrada(
        self,
        chave: ChavePedido,
        estado: _PedidoAtivo,
    ) -> EntradaHeap:
        """Monta a chave de ordenacao e a entrada da heap."""

        pedido = estado.pedido

        return (
            -estado.prioridade,
            estado.folga_sla_min,
            pedido.criado_em,
            self._identificador_ordenacao(pedido),
            estado.ordem,
            estado.versao,
            chave,
            pedido,
        )

    def _inserir(
        self,
        pedido: Pedido,
        prioridade: float,
        atualizar_automaticamente: bool,
        tempo_estimado_entrega_min: float | None,
        agora: datetime,
    ) -> None:
        """Registra um pedido e insere sua entrada na heap."""

        chave = self._chave_pedido(pedido)

        if chave in self._pedidos_processados:
            raise ValueError(
                "Pedido ja foi processado e nao pode ser reinserido."
            )

        if chave in self._pedidos_ativos:
            raise ValueError("Pedido ja esta na fila.")

        estado = _PedidoAtivo(
            pedido=pedido,
            prioridade=prioridade,
            atualizar_automaticamente=atualizar_automaticamente,
            tempo_estimado_entrega_min=tempo_estimado_entrega_min,
            ordem=next(self._ordem),
            folga_sla_min=self._calcular_folga_sla(
                pedido,
                tempo_estimado_entrega_min,
                agora,
            ),
        )

        self._pedidos_ativos[chave] = estado

        heappush(
            self._itens,
            self._criar_entrada(chave, estado),
        )

    def adicionar_pedido(
        self,
        pedido: Pedido,
        agora: datetime | None = None,
        tempo_estimado_entrega_min: float | None = None,
    ) -> None:
        """Calcula a prioridade e adiciona um pedido a fila."""

        if agora is None:
            agora = datetime.now(timezone.utc)

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
            agora=agora,
        )

    def adicionar(
        self,
        pedido: Pedido,
        prioridade: float,
        agora: datetime | None = None,
    ) -> None:
        """Adiciona um pedido com prioridade manual e fixa."""

        if agora is None:
            agora = datetime.now(timezone.utc)

        self._inserir(
            pedido,
            prioridade,
            atualizar_automaticamente=False,
            tempo_estimado_entrega_min=None,
            agora=agora,
        )

    def atualizar_prioridades(
        self,
        agora: datetime | None = None,
    ) -> None:
        """
        Recalcula as prioridades automaticas e reconstrói a heap.

        Esta e uma operacao em lote, com custo O(n).
        Deve ser chamada quando o instante da simulacao mudar
        e for necessario atualizar aging e risco de SLA.
        """

        if agora is None:
            agora = datetime.now(timezone.utc)

        novas_entradas: list[EntradaHeap] = []

        for chave, estado in self._pedidos_ativos.items():
            if estado.atualizar_automaticamente:
                estado.prioridade = calcular_prioridade(
                    estado.pedido,
                    agora=agora,
                    tempo_estimado_entrega_min=(
                        estado.tempo_estimado_entrega_min
                    ),
                )

            estado.folga_sla_min = self._calcular_folga_sla(
                estado.pedido,
                estado.tempo_estimado_entrega_min,
                agora,
            )

            estado.versao += 1

            novas_entradas.append(
                self._criar_entrada(chave, estado)
            )

        self._itens = novas_entradas
        heapify(self._itens)

    def atualizar_estimativa_entrega(
        self,
        pedido: Pedido,
        tempo_estimado_entrega_min: float | None,
        agora: datetime | None = None,
    ) -> None:
        """Atualiza a estimativa e invalida a entrada anterior."""

        chave = self._chave_pedido(pedido)
        estado = self._pedidos_ativos.get(chave)

        if estado is None:
            raise ValueError("Pedido nao encontrado na fila.")

        if not estado.atualizar_automaticamente:
            raise ValueError(
                "Pedidos com prioridade manual nao podem "
                "ter estimativa atualizada."
            )

        if agora is None:
            agora = datetime.now(timezone.utc)

        prioridade = calcular_prioridade(
            estado.pedido,
            agora=agora,
            tempo_estimado_entrega_min=tempo_estimado_entrega_min,
        )

        folga_sla_min = self._calcular_folga_sla(
            estado.pedido,
            tempo_estimado_entrega_min,
            agora,
        )

        estado.tempo_estimado_entrega_min = (
            tempo_estimado_entrega_min
        )
        estado.prioridade = prioridade
        estado.folga_sla_min = folga_sla_min
        estado.versao += 1

        heappush(
            self._itens,
            self._criar_entrada(chave, estado),
        )

        self._compactar_se_necessario()

    def _entrada_valida(self, entrada: EntradaHeap) -> bool:
        """Verifica se a entrada ainda representa a versao ativa."""

        versao = entrada[5]
        chave = entrada[6]

        estado = self._pedidos_ativos.get(chave)

        return (
            estado is not None
            and estado.versao == versao
        )

    def _descartar_obsoletas(self) -> None:
        """Remove entradas antigas que chegaram ao topo da heap."""

        while self._itens and not self._entrada_valida(
            self._itens[0]
        ):
            heappop(self._itens)

    def _compactar_se_necessario(self) -> None:
        """Reconstrói a heap quando existem muitas entradas obsoletas."""

        limite = max(
            MIN_ENTRADAS_COMPACTACAO,
            FATOR_COMPACTACAO * len(self._pedidos_ativos),
        )

        if len(self._itens) <= limite:
            return

        self._itens = [
            self._criar_entrada(chave, estado)
            for chave, estado in self._pedidos_ativos.items()
        ]

        heapify(self._itens)

    def retirar_proximo(self) -> Pedido:
        """Retira o pedido valido de maior prioridade."""

        self._descartar_obsoletas()

        if not self._itens:
            raise IndexError("A fila de prioridade esta vazia.")

        entrada = heappop(self._itens)
        chave = entrada[6]

        estado = self._pedidos_ativos.pop(chave)
        self._pedidos_processados.add(chave)

        if not self._pedidos_ativos:
            self._itens.clear()

        return estado.pedido

    def proximo(self) -> Pedido | None:
        """Consulta o proximo pedido valido sem retira-lo."""

        self._descartar_obsoletas()

        if not self._itens:
            return None

        return self._itens[0][7]

    def esta_vazia(self) -> bool:
        """Indica se existem pedidos ativos na fila."""

        return len(self._pedidos_ativos) == 0

    def __len__(self) -> int:
        """Retorna a quantidade de pedidos ativos na fila."""

        return len(self._pedidos_ativos)
