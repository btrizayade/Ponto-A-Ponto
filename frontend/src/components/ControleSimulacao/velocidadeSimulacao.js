export const VELOCIDADES_SIMULACAO = [
  { segundos: 5, rotulo: '5 segundos reais = 1 hora simulada' },
  { segundos: 15, rotulo: '15 segundos reais = 1 hora simulada' },
  { segundos: 30, rotulo: '30 segundos reais = 1 hora simulada' },
  { segundos: 60, rotulo: '1 minuto real = 1 hora simulada' }
]

export const VELOCIDADE_SIMULACAO_PADRAO = 15

export function velocidadeBloqueada(estadoExecucao, carregando = false) {
  return carregando || ['executando', 'pausada'].includes(estadoExecucao)
}
