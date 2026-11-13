import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  criarInicioApi,
  existemPedidosPosteriores,
  obterPedidoMaisRecenteLocal,
  sugerirInicioSimulado,
  validarInicioSimulado
} from './inicioSimulado.js'

const pedidosReferencia = [
  { criado_em: '2026-10-30T09:23:00-03:00' },
  { criado_em: '2026-10-30T09:45:00-03:00' }
]

test('sugere horário após o pedido mais recente do cenário', () => {
  assert.deepEqual(sugerirInicioSimulado(pedidosReferencia), {
    data: '2026-10-30',
    hora: '10:00'
  })
})

test('converte a criação mais recente ao relógio de Salvador', () => {
  assert.equal(
    obterPedidoMaisRecenteLocal([{ criado_em: '2026-10-30T12:45:00Z' }]),
    '2026-10-30T09:45:00'
  )
})

test('valida dia útil, horário inclusivo às 09h e exclusivo às 17h', () => {
  assert.equal(validarInicioSimulado('2026-10-30', '09:00'), '')
  assert.equal(validarInicioSimulado('2026-10-30', '16:59'), '')
  assert.match(validarInicioSimulado('2026-10-30', '08:59'), /entre 09:00/)
  assert.match(validarInicioSimulado('2026-10-30', '17:00'), /entre 09:00/)
  assert.match(validarInicioSimulado('2026-10-31', '10:00'), /dia útil/)
})

test('envia o relógio simulado sem converter para o fuso do computador', () => {
  assert.equal(criarInicioApi('2026-10-30', '09:15'), '2026-10-30T09:15:00')
})

test('avisa quando o início escolhido antecede pedidos do cenário', () => {
  assert.equal(existemPedidosPosteriores(pedidosReferencia, '2026-10-30', '09:30'), true)
  assert.equal(existemPedidosPosteriores(pedidosReferencia, '2026-10-30', '10:00'), false)
})

test('pedidos dos três cenários recebem a mesma sugestão coerente com suas datas', () => {
  const cenarios = [
    [{ criado_em: '2026-10-29T16:10:00-03:00' }],
    [{ criado_em: '2026-10-30T09:23:00-03:00' }],
    [{ criado_em: '2026-10-30T09:45:00-03:00' }]
  ]

  assert.deepEqual(cenarios.map((pedidos) => sugerirInicioSimulado(pedidos)), [
    { data: '2026-10-30', hora: '10:00' },
    { data: '2026-10-30', hora: '10:00' },
    { data: '2026-10-30', hora: '10:00' }
  ])
})
