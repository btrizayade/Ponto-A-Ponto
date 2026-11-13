import assert from 'node:assert/strict'
import { test } from 'node:test'

import { obterConfiguracaoBaseNovaSimulacao } from './configuracaoNovaSimulacao.js'

test('nova simulação prepara defaults sem criar ou iniciar uma execução', async () => {
  const pedidos = [{ criado_em: '2026-10-30T09:00:00-03:00' }]
  const chamadas = []
  const configuracao = await obterConfiguracaoBaseNovaSimulacao({
    cenarios: [{ id: 8, nome: 'Operação normal' }],
    buscarPedidos: async (id) => {
      chamadas.push(['pedidos', id])
      return pedidos
    },
    quantidadeEntregadoresPadrao: 2
  })

  assert.deepEqual(configuracao, {
    cenarioId: '8',
    pedidos,
    inicio: { data: '2026-10-30', hora: '10:00' },
    quantidadeEntregadores: '2',
    velocidadeSimulacao: 15
  })
  assert.deepEqual(chamadas, [['pedidos', 8]])
})
