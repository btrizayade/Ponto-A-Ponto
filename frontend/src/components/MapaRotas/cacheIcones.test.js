import test from 'node:test'
import assert from 'node:assert/strict'

import { criarCacheIcones } from './cacheIcones.js'

test('cache mantém a mesma instância para chave repetida e separa chaves distintas', () => {
  const obter = criarCacheIcones()
  let criacoes = 0
  const criar = () => ({ sequencia: ++criacoes })

  const primeiro = obter('veiculo:#1769AA', criar)
  const repetido = obter('veiculo:#1769AA', criar)
  const outro = obter('veiculo:#C2410C', criar)

  assert.equal(primeiro, repetido)
  assert.notEqual(primeiro, outro)
  assert.equal(criacoes, 2)
})
