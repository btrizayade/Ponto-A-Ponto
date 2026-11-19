import test from 'node:test'
import assert from 'node:assert/strict'

import { criarLoopAnimacao } from './loopAnimacao.js'

function criarAgendadorFake() {
  let proximoId = 1
  const pendentes = new Map()
  const cancelados = []

  return {
    pendentes,
    cancelados,
    agendarFrame(callback) {
      const id = proximoId++
      pendentes.set(id, callback)
      return id
    },
    cancelarFrame(id) {
      cancelados.push(id)
      pendentes.delete(id)
    },
    executarProximo(timestamp) {
      const [id, callback] = pendentes.entries().next().value ?? []
      if (id === undefined) return null
      pendentes.delete(id)
      callback(timestamp)
      return callback
    },
  }
}

test('iniciar repetidamente mantém somente um loop RAF', () => {
  const scheduler = criarAgendadorFake()
  let quadros = 0
  const loop = criarLoopAnimacao({
    agendarFrame: scheduler.agendarFrame,
    cancelarFrame: scheduler.cancelarFrame,
    aoFrame: () => { quadros += 1 },
  })

  loop.iniciar()
  loop.iniciar()
  assert.equal(scheduler.pendentes.size, 1)

  scheduler.executarProximo(16)
  assert.equal(quadros, 1)
  assert.equal(scheduler.pendentes.size, 1)

  loop.parar()
  assert.equal(scheduler.pendentes.size, 0)
})

test('parar cancela o frame pendente e impede atualizações posteriores', () => {
  const scheduler = criarAgendadorFake()
  let quadros = 0
  const loop = criarLoopAnimacao({
    agendarFrame: scheduler.agendarFrame,
    cancelarFrame: scheduler.cancelarFrame,
    aoFrame: () => { quadros += 1 },
  })

  loop.iniciar()
  const callbackPendente = scheduler.pendentes.values().next().value
  const idPendente = scheduler.pendentes.keys().next().value
  loop.parar()

  assert.deepEqual(scheduler.cancelados, [idPendente])
  assert.equal(scheduler.pendentes.size, 0)
  callbackPendente(32)
  assert.equal(quadros, 0)

  loop.parar()
  assert.equal(scheduler.cancelados.length, 1)
})
