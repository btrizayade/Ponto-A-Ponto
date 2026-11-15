const FUSO_SIMULACAO = 'America/Bahia'

export function formatarInstanteSalvador(instante) {
  if (!instante) return null

  const data = new Date(instante)
  if (Number.isNaN(data.getTime())) return null

  return new Intl.DateTimeFormat('pt-BR', {
    timeZone: FUSO_SIMULACAO,
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(data)
}

export function formatarInicioSelecionado(inicio) {
  if (!inicio?.data && !inicio?.hora) return null
  if (inicio.data && inicio.hora) {
    const [ano, mes, dia] = inicio.data.split('-')
    return `${dia}/${mes}/${ano}, ${inicio.hora}`
  }

  return [inicio.data, inicio.hora].filter(Boolean).join(' ')
}

export function obterTemposPedido(pedido) {
  return {
    criadoEm: formatarInstanteSalvador(pedido.criado_em),
    prazoSla: formatarInstanteSalvador(pedido.prazo_entrega_em),
    previsaoEntrega: formatarInstanteSalvador(pedido.previsao_entrega_em),
    entregueEm: formatarInstanteSalvador(pedido.entregue_em),
    atualizadoEm: formatarInstanteSalvador(pedido.atualizado_em)
  }
}
