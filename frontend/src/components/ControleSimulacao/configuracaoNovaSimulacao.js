import { VELOCIDADE_SIMULACAO_PADRAO } from './velocidadeSimulacao.js'

export async function obterConfiguracaoBaseNovaSimulacao({
  cenarios,
  quantidadeEntregadoresPadrao,
  quantidadeEntregadoresSelecionada
}) {
  const cenario = cenarios[0]
  if (!cenario) throw new Error('Não há cenários disponíveis.')

  const quantidadeSelecionada = Number(quantidadeEntregadoresSelecionada)
  const quantidadeEntregadores = Number.isInteger(quantidadeSelecionada)
    && quantidadeSelecionada >= 1
    && quantidadeSelecionada <= 5
    ? String(quantidadeSelecionada)
    : String(quantidadeEntregadoresPadrao)

  return {
    cenarioId: String(cenario.id),
    quantidadeEntregadores,
    velocidadeSimulacao: VELOCIDADE_SIMULACAO_PADRAO
  }
}

export function obterInicioFixoCenario(cenarios, cenarioId) {
  const cenario = cenarios.find(
    (item) => String(item.id) === String(cenarioId)
  )
  const temporalidade = cenario?.temporalidade
  const instante = temporalidade?.inicio_simulacao
  const dataHora = instante ? new Date(instante) : null

  if (!dataHora || Number.isNaN(dataHora.getTime())) return null

  const fuso = temporalidade.fuso_horario || 'America/Bahia'
  const partes = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: fuso,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23'
    })
      .formatToParts(dataHora)
      .filter(({ type }) => type !== 'literal')
      .map(({ type, value }) => [type, value])
  )

  const data = `${partes.year}-${partes.month}-${partes.day}`
  const hora = `${partes.hour}:${partes.minute}`
  const dataFormatada = `${partes.day}/${partes.month}/${partes.year}`

  return {
    data,
    hora,
    texto: `${dataFormatada} às ${hora} (${fuso})`
  }
}

export function criarDadosCriacaoSimulacao({
  cenarioId,
  quantidade_entregadores,
  segundosReaisPorHoraSimulada
}) {
  return {
    cenario_id: Number(cenarioId),
    quantidade_entregadores,
    provedor: 'simulado',
    segundos_reais_por_hora_simulada: segundosReaisPorHoraSimulada
  }
}
