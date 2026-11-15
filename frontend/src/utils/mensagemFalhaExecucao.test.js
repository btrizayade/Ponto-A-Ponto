import test from 'node:test'
import assert from 'node:assert/strict'

import { mensagemFalhaExecucao } from './mensagemFalhaExecucao.js'

test('informa a falha automática recebida no estado da simulação', () => {
  assert.equal(
    mensagemFalhaExecucao({
      estado_execucao: 'falhou',
      erro_execucao: 'FalhaPersistenciaAuditoriaRoteamento'
    }),
    'A execução automática falhou: FalhaPersistenciaAuditoriaRoteamento'
  )
})

test('usa orientação clara quando a API não envia o detalhe da falha', () => {
  assert.equal(
    mensagemFalhaExecucao({ estado_execucao: 'falhou' }),
    'A execução automática falhou: consulte os logs do backend.'
  )
})

test('não mostra alerta quando a execução não falhou', () => {
  assert.equal(
    mensagemFalhaExecucao({ estado_execucao: 'executando' }),
    null
  )
})
