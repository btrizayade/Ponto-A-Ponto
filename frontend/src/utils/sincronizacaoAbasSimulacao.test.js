import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CHAVE_STORAGE_SIMULACAO,
  criarSincronizadorAbasSimulacao,
  mensagemSimulacaoValida,
  NOME_CANAL_SIMULACAO,
} from './sincronizacaoAbasSimulacao.js'

function criarBarramentoBroadcast() {
  const participantes = new Set()

  class BroadcastChannelFake {
    static instancias = []

    constructor(nome) {
      assert.equal(nome, NOME_CANAL_SIMULACAO)
      this.listeners = new Set()
      this.fechado = false
      participantes.add(this)
      BroadcastChannelFake.instancias.push(this)
    }

    addEventListener(tipo, listener) {
      if (tipo === 'message') this.listeners.add(listener)
    }

    postMessage(data) {
      for (const participante of participantes) {
        if (participante === this || participante.fechado) continue
        for (const listener of participante.listeners) listener({ data })
      }
    }

    close() {
      this.fechado = true
      participantes.delete(this)
    }
  }

  return BroadcastChannelFake
}

test('BroadcastChannel entrega a seleção e fecha listeners no encerramento', () => {
  const Barramento = criarBarramentoBroadcast()
  const recebidas = []
  const painel = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    origem: 'painel',
  })
  const rotas = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    origem: 'rotas',
    aoReceber: (mensagem) => recebidas.push(mensagem),
  })

  assert.equal(painel.publicar({ tipo: 'simulacao_selecionada', simulacaoId: 42 }), true)
  assert.equal(recebidas.length, 1)
  assert.equal(recebidas[0].simulacao_id, 42)
  assert.equal(recebidas[0].origem, 'painel')

  rotas.fechar()
  painel.publicar({ tipo: 'estado_alterado', simulacaoId: 42, estadoExecucao: 'pausada' })
  assert.equal(recebidas.length, 1)
  painel.fechar()
})

test('mensagens repetidas ou antigas do mesmo emissor são ignoradas', () => {
  const Barramento = criarBarramentoBroadcast()
  const recebidas = []
  const sync = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    origem: 'destino',
    aoReceber: (mensagem) => recebidas.push(mensagem),
  })
  const emissor = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    origem: 'painel',
  })

  emissor.publicar({ tipo: 'simulacao_selecionada', simulacaoId: 7 })
  emissor.publicar({ tipo: 'estado_alterado', simulacaoId: 7, estadoExecucao: 'pausada' })
  const mensagemAntiga = {
    aplicacao: 'ponto-a-ponto',
    versao: 1,
    origem: 'painel',
    sequencia: 1,
    tipo: 'simulacao_selecionada',
    simulacao_id: 6,
  }
  const canalEmissor = Barramento.instancias.at(-1)
  canalEmissor.postMessage(mensagemAntiga)

  assert.equal(recebidas.length, 2)
  assert.equal(recebidas[0].simulacao_id, 7)
  assert.equal(recebidas[1].estado_execucao, 'pausada')
  assert.equal(mensagemSimulacaoValida(mensagemAntiga), true)
  emissor.fechar()
  sync.fechar()
})

test('fallback por storage propaga a seleção entre abas e limpa o listener', () => {
  const eventos = new Set()
  const gravacoes = []
  const janela = {
    addEventListener: (tipo, callback) => eventos.add(callback),
    removeEventListener: (tipo, callback) => {
      if (tipo === 'storage') eventos.delete(callback)
    },
  }
  const storage = {
    setItem: (key, value) => gravacoes.push({ key, value }),
  }
  const recebidas = []
  const sync = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: null,
    windowTarget: janela,
    storageTarget: storage,
    origem: 'rotas',
    aoReceber: (mensagem) => recebidas.push(mensagem),
  })

  assert.equal(eventos.size, 1)
  const mensagem = {
    aplicacao: 'ponto-a-ponto',
    versao: 1,
    origem: 'painel',
    sequencia: 1,
    tipo: 'simulacao_selecionada',
    simulacao_id: 12,
  }
  for (const callback of eventos) {
    callback({ key: CHAVE_STORAGE_SIMULACAO, newValue: JSON.stringify(mensagem) })
  }
  assert.equal(recebidas[0].simulacao_id, 12)
  sync.publicar({ tipo: 'estado_alterado', simulacaoId: 12, estadoExecucao: 'pausada' })
  assert.equal(gravacoes[0].key, CHAVE_STORAGE_SIMULACAO)
  sync.fechar()
  assert.equal(eventos.size, 0)
})

test('payloads inválidos e IDs inválidos não passam pela validação', () => {
  assert.equal(mensagemSimulacaoValida({ tipo: 'simulacao_selecionada', simulacao_id: -1 }), false)
  assert.equal(mensagemSimulacaoValida({
    aplicacao: 'ponto-a-ponto', versao: 1, origem: 'x', sequencia: 1,
    tipo: 'simulacao_selecionada', simulacao_id: 3,
  }), true)
})
