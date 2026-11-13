import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  formatarInicioSelecionado,
  obterTemposPedido
} from './pedidoTemporal.js'

const pedidoBase = {
  criado_em: '2026-10-29T13:10:00Z',
  prazo_entrega_em: '2026-11-05T20:00:00Z',
  previsao_entrega_em: null,
  entregue_em: null,
  atualizado_em: null
}

test('mantém datas históricas e exibe o início operacional selecionado', () => {
  const tempos = obterTemposPedido(pedidoBase)

  assert.equal(tempos.criadoEm, '29/10/2026, 10:10')
  assert.equal(tempos.prazoSla, '05/11/2026, 17:00')
  assert.equal(tempos.previsaoEntrega, null)
  assert.equal(formatarInicioSelecionado({ data: '2026-10-30', hora: '11:30' }),
    '30/10/2026, 11:30')
})

test('separa previsão do plano, entrega real e última atualização', () => {
  const tempos = obterTemposPedido({
    ...pedidoBase,
    previsao_entrega_em: '2026-10-30T14:30:00Z',
    entregue_em: '2026-10-30T14:32:00Z',
    atualizado_em: '2026-10-30T14:32:00Z'
  })

  assert.equal(tempos.criadoEm, '29/10/2026, 10:10')
  assert.equal(tempos.previsaoEntrega, '30/10/2026, 11:30')
  assert.equal(tempos.entregueEm, '30/10/2026, 11:32')
  assert.equal(tempos.atualizadoEm, '30/10/2026, 11:32')
})
