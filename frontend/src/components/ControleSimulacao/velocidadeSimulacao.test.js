import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  VELOCIDADES_SIMULACAO,
  VELOCIDADE_SIMULACAO_PADRAO,
  velocidadeBloqueada
} from './velocidadeSimulacao.js'

test('oferece exatamente as quatro velocidades com rótulos claros', () => {
  assert.deepEqual(VELOCIDADES_SIMULACAO, [
    { segundos: 5, rotulo: '5 segundos reais = 1 hora simulada' },
    { segundos: 15, rotulo: '15 segundos reais = 1 hora simulada' },
    { segundos: 30, rotulo: '30 segundos reais = 1 hora simulada' },
    { segundos: 60, rotulo: '1 minuto real = 1 hora simulada' }
  ])
})

test('velocidade inicial é 15 segundos por hora simulada', () => {
  assert.equal(VELOCIDADE_SIMULACAO_PADRAO, 15)
})

test('seletor bloqueia em execução e pausa, e libera no estado concluído', () => {
  assert.equal(velocidadeBloqueada('executando'), true)
  assert.equal(velocidadeBloqueada('pausada'), true)
  assert.equal(velocidadeBloqueada('concluida'), false)
  assert.equal(velocidadeBloqueada('aguardando'), false)
  assert.equal(velocidadeBloqueada('concluida', true), true)
})
