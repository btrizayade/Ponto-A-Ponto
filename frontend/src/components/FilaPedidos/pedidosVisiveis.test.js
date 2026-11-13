import assert from 'node:assert/strict'
import { test } from 'node:test'

import { combinarPedidosDaSimulacao } from './pedidosVisiveis.js'

test('lista conserva o snapshot e marca pedidos novos para a próxima simulação', () => {
  const snapshot = [{ codigo: 'PED-001', status: 'em_rota' }]
  const persistidos = [
    { codigo: 'PED-001', bairro: 'Barra' },
    { codigo: 'PED-MAN-1', bairro: 'Brotas' }
  ]

  assert.deepEqual(
    combinarPedidosDaSimulacao(snapshot, persistidos),
    [
      { codigo: 'PED-001', status: 'em_rota' },
      { codigo: 'PED-MAN-1', bairro: 'Brotas', status: 'proxima_simulacao' }
    ]
  )
})
