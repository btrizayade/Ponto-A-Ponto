export function camposPedidoValidos(pedido) {
  return Boolean(
    pedido.cenario_id &&
    pedido.bairro_id &&
    pedido.data_criacao &&
    pedido.categoria_produto &&
    pedido.modalidade
  )
}

export function restricoesDataCriacao(cenario) {
  const temporalidade = cenario?.temporalidade
  const janela = temporalidade?.janela_criacao
  return {
    minimo: janela?.inicio || '',
    maximo: janela?.fim || '',
    valorInicial: temporalidade?.inicio_simulacao?.slice(0, 10) || ''
  }
}

export function montarPedidoRequest(pedido) {
  return {
    cenario_id: Number(pedido.cenario_id),
    bairro_id: Number(pedido.bairro_id),
    data_criacao: pedido.data_criacao,
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
