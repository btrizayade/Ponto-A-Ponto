export function combinarPedidosDaSimulacao(pedidosDaSimulacao, pedidosSalvos) {
  const codigosDoSnapshot = new Set(
    pedidosDaSimulacao.map((pedido) => pedido.codigo)
  )
  const pedidosProximaSimulacao = pedidosSalvos
    .filter((pedido) => !codigosDoSnapshot.has(pedido.codigo))
    .map((pedido) => ({ ...pedido, status: 'proxima_simulacao' }))

  return [...pedidosDaSimulacao, ...pedidosProximaSimulacao]
}
