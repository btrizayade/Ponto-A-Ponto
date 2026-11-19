import test from 'node:test'
import assert from 'node:assert/strict'

import {
  atualizarUrlAcompanhamentoRotas,
  criarUrlAcompanhamentoRotas,
  obterIdSimulacaoDaBusca,
} from './rotasUrl.js'
import { EVENTO_SELECAO_SIMULACAO } from './sincronizacaoAbasSimulacao.js'

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

test('mudança programática de URL mantém a query e notifica a página para sincronizar estado', () => {
  const chamadas = []
  const eventos = []
  class CustomEventFake {
    constructor(type, options) {
      this.type = type
      this.detail = options.detail
    }
  }
  const alvo = {
    location: { href: 'http://localhost:5173/rotas?simulacaoId=2&origem=painel#mapa' },
    history: {
      state: { marcador: true },
      replaceState: (...args) => chamadas.push(['replaceState', ...args]),
      pushState: (...args) => chamadas.push(['pushState', ...args]),
    },
    dispatchEvent: (evento) => eventos.push(evento),
  }

  atualizarUrlAcompanhamentoRotas(42, alvo, { CustomEventConstructor: CustomEventFake })

  assert.equal(chamadas[0][0], 'replaceState')
  assert.equal(chamadas[0][1], alvo.history.state)
  assert.equal(String(chamadas[0][3]), 'http://localhost:5173/rotas?simulacaoId=42&origem=painel#mapa')
  assert.equal(eventos[0].type, EVENTO_SELECAO_SIMULACAO)
  assert.equal(eventos[0].detail.search, '?simulacaoId=42&origem=painel')
})

test('limpar URL remove apenas o ID e permite registrar navegação no histórico', () => {
  const chamadas = []
  const alvo = {
    location: { href: 'http://localhost:5173/rotas?simulacaoId=42' },
    history: {
      state: null,
      pushState: (...args) => chamadas.push(args),
    },
    dispatchEvent: () => {},
  }

  atualizarUrlAcompanhamentoRotas(null, alvo, {
    substituir: false,
    notificar: false,
  })

  assert.equal(String(chamadas[0][2]), 'http://localhost:5173/rotas')
})
