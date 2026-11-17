import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  combinarPedidosDaSimulacao,
  obterPedidosExibidos
} from './pedidosVisiveis.js'

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

test('resultado concluído usa o snapshot e mantém pedidos arquivados e eventos finais', () => {
  const entregues = [
    {
      codigo: 'PED-001',
      status: 'entregue',
      entregue_em: '2026-10-07T09:12:00-03:00',
      previsao_entrega_em: null,
      atualizado_em: '2026-10-07T09:12:00-03:00'
    },
    {
      codigo: 'PED-MAN-ARQUIVADO',
      status: 'entregue',
      entregue_em: '2026-10-07T10:25:00-03:00'
    }
  ]
  const persistidosAposConclusao = [
    { codigo: 'PED-001', status: 'pendente' },
    { codigo: 'PED-MAN-NOVO', status: 'pendente' }
  ]

  assert.deepEqual(obterPedidosExibidos({
    pedidosDaSimulacao: entregues,
    pedidosPersistidos: persistidosAposConclusao,
    simulacaoDoCenario: true,
    estadoExecucao: 'concluida'
  }), [
    ...entregues,
    { codigo: 'PED-MAN-NOVO', status: 'proxima_simulacao' }
  ])
})

test('simulação de outro cenário deixa visível somente a lista persistida selecionada', () => {
  const persistidos = [{ codigo: 'EQ-001', criado_em: '2026-10-12T09:00:00-03:00' }]

  assert.equal(obterPedidosExibidos({
    pedidosDaSimulacao: [{ codigo: 'PED-001', status: 'entregue' }],
    pedidosPersistidos: persistidos,
    simulacaoDoCenario: false
  }), persistidos)
})
