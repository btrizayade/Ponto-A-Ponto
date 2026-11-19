import test from 'node:test'
import assert from 'node:assert/strict'

import {
  criarUrlAcompanhamentoRotas,
  obterIdSimulacaoDaBusca,
} from './rotasUrl.js'

test('URL de rotas transmite o ID da simulação e abre rota sem ID quando vazio', () => {
  assert.equal(criarUrlAcompanhamentoRotas(42), '/rotas?simulacaoId=42')
  assert.equal(criarUrlAcompanhamentoRotas(null), '/rotas')
})

test('extrai apenas IDs positivos inteiros da URL', () => {
  assert.equal(obterIdSimulacaoDaBusca('?simulacaoId=42'), 42)
  assert.equal(obterIdSimulacaoDaBusca('?outro=1'), null)
  assert.equal(obterIdSimulacaoDaBusca('?simulacaoId=0'), null)
  assert.equal(obterIdSimulacaoDaBusca('?simulacaoId=abc'), null)
  assert.equal(obterIdSimulacaoDaBusca('?simulacaoId=4.2'), null)
})
