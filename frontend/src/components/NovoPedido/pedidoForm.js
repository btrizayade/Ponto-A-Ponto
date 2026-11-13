export function camposPedidoValidos(pedido) {
  return Boolean(
    pedido.cenario_id &&
    pedido.bairro_id &&
    pedido.categoria_produto &&
    pedido.modalidade
  )
}

export function montarPedidoRequest(pedido) {
  return {
    cenario_id: Number(pedido.cenario_id),
    bairro_id: Number(pedido.bairro_id),
    categoria_produto: pedido.categoria_produto,
    modalidade: pedido.modalidade
  }
}

export function bloquearEnvioDuplicado(refSubmissao) {
  if (refSubmissao.current) return false
  refSubmissao.current = true
  return true
}

export function liberarEnvio(refSubmissao) {
  refSubmissao.current = false
}
