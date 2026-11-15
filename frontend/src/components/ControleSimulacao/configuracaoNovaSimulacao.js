import { sugerirInicioSimulado } from './inicioSimulado.js'
import { VELOCIDADE_SIMULACAO_PADRAO } from './velocidadeSimulacao.js'

export async function obterConfiguracaoBaseNovaSimulacao({
  cenarios,
  buscarPedidos,
  quantidadeEntregadoresPadrao
}) {
  const cenario = cenarios[0]
  if (!cenario) throw new Error('Não há cenários disponíveis.')

  const pedidos = await buscarPedidos(cenario.id)
  const inicio = sugerirInicioSimulado(pedidos)

  return {
    cenarioId: String(cenario.id),
    pedidos,
    inicio,
    quantidadeEntregadores: String(quantidadeEntregadoresPadrao),
    velocidadeSimulacao: VELOCIDADE_SIMULACAO_PADRAO
  }
}
