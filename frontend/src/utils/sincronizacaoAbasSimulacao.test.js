import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CHAVE_STORAGE_SIMULACAO,
  CHAVE_REVISAO_SELECAO,
  criarSincronizadorAbasSimulacao,
  mensagemSimulacaoValida,
  NOME_CANAL_SIMULACAO,
  VERSAO_MENSAGENS_SIMULACAO,
} from './sincronizacaoAbasSimulacao.js'

function criarBarramentoBroadcast({ deferir = false } = {}) {
  const participantes = new Set()
  const fila = []

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
      if (deferir) {
        fila.push({ remetente: this, data })
        return
      }
      entregar(this, data)
    }

    close() {
      this.fechado = true
      participantes.delete(this)
    }

    static descarregarFila() {
      while (fila.length) {
        const mensagem = fila.shift()
        entregar(mensagem.remetente, mensagem.data)
      }
    }
  }

  function entregar(remetente, data) {
    for (const participante of participantes) {
      if (participante === remetente || participante.fechado) continue
      for (const listener of participante.listeners) listener({ data })
    }
  }

  return BroadcastChannelFake
}

function mensagemBase(overrides = {}) {
  return {
    aplicacao: 'ponto-a-ponto',
    versao: VERSAO_MENSAGENS_SIMULACAO,
    origem: 'painel',
    sequencia: 1,
    tipo: 'simulacao_selecionada',
    simulacao_id: 42,
    selecao_id: 'selecao-a',
    revisao_selecao: 1,
    ...overrides,
  }
}

test('publica seleção e estados válidos; limpa usa contrato próprio', () => {
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

  assert.equal(painel.publicar({
    tipo: 'simulacao_selecionada',
    simulacaoId: 42,
    selecaoId: 'selecao-a',
  }), true)
  for (const estadoExecucao of ['aguardando', 'executando', 'pausada', 'concluida', 'falhou']) {
    assert.equal(painel.publicar({
      tipo: 'estado_alterado',
      simulacaoId: 42,
      selecaoId: 'selecao-a',
      estadoExecucao,
    }), true)
  }
  assert.equal(painel.publicar({
    tipo: 'simulacao_limpa',
    simulacaoAnteriorId: 42,
    selecaoId: 'selecao-a',
  }), true)

  assert.equal(recebidas.length, 7)
  assert.equal(recebidas[0].simulacao_id, 42)
  assert.equal(recebidas[0].origem, 'painel')
  assert.deepEqual(recebidas.slice(1, 6).map(({ estado_execucao }) => estado_execucao), [
    'aguardando', 'executando', 'pausada', 'concluida', 'falhou',
  ])
  assert.equal(recebidas[6].simulacao_anterior_id, 42)
  rotas.fechar()
  painel.fechar()
})

test('valida campos exatos e obrigatórios por tipo e rejeita estados ausentes ou desconhecidos', () => {
  assert.equal(mensagemSimulacaoValida(mensagemBase()), true)
  assert.equal(mensagemSimulacaoValida(mensagemBase({ simulacao_id: 0 })), false)
  assert.equal(mensagemSimulacaoValida(mensagemBase({ origem: '' })), false)
  assert.equal(mensagemSimulacaoValida(mensagemBase({ versao: 1 })), false)
  assert.equal(mensagemSimulacaoValida(mensagemBase({ estado_execucao: 'pausada' })), false)

  const estadoValido = mensagemBase({
    tipo: 'estado_alterado',
    estado_execucao: 'pausada',
  })
  assert.equal(mensagemSimulacaoValida(estadoValido), true)
  assert.equal(mensagemSimulacaoValida({ ...estadoValido, estado_execucao: undefined }), false)
  assert.equal(mensagemSimulacaoValida({ ...estadoValido, estado_execucao: 'parada' }), false)
  assert.equal(mensagemSimulacaoValida({ ...estadoValido, campo_extra: true }), false)

  const limpaValida = mensagemBase({
    tipo: 'simulacao_limpa',
    simulacao_anterior_id: 42,
    selecao_anterior_id: 'selecao-a',
  })
  delete limpaValida.simulacao_id
  delete limpaValida.selecao_id
  assert.equal(mensagemSimulacaoValida(limpaValida), true)
  assert.equal(mensagemSimulacaoValida({ ...limpaValida, simulacao_id: 42 }), false)
  assert.equal(mensagemSimulacaoValida({ ...limpaValida, selecao_anterior_id: '' }), false)
})

test('a publicação rejeita payload inválido sem propagar mensagem', () => {
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

  assert.equal(painel.publicar({ tipo: 'estado_alterado', simulacaoId: 42, selecaoId: 'x' }), false)
  assert.equal(painel.publicar({
    tipo: 'simulacao_selecionada', simulacaoId: 42, selecaoId: 'x', estadoExecucao: 'pausada',
  }), false)
  assert.equal(painel.publicar({ tipo: 'simulacao_selecionada', simulacaoId: 42 }), false)
  assert.equal(painel.publicar({
    tipo: 'simulacao_selecionada', simulacaoId: 42, selecaoId: 'x',
  }), true)
  assert.equal(painel.publicar({
    tipo: 'estado_alterado', simulacaoId: 42, selecaoId: 'x', estadoExecucao: 'desconhecido',
  }), false)
  assert.equal(recebidas.length, 1)
  rotas.fechar()
  painel.fechar()
})

test('o recebimento também descarta estados e campos que violem o contrato', () => {
  const Barramento = criarBarramentoBroadcast()
  const recebidas = []
  const destino = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    relogio: () => 100,
    origem: 'rotas',
    aoReceber: (mensagem) => recebidas.push(mensagem),
  })
  const emissorBruto = new Barramento(NOME_CANAL_SIMULACAO)

  const semEstado = mensagemBase({ tipo: 'estado_alterado' })
  delete semEstado.estado_execucao
  emissorBruto.postMessage(semEstado)
  emissorBruto.postMessage(mensagemBase({
    tipo: 'estado_alterado',
    estado_execucao: 'qualquer',
  }))
  emissorBruto.postMessage(mensagemBase({ campo_inesperado: true }))

  assert.equal(recebidas.length, 0)
  emissorBruto.close()
  destino.fechar()
})

test('não entrega estado_alterado estruturalmente válido antes de receber uma seleção', () => {
  const Barramento = criarBarramentoBroadcast()
  const recebidas = []
  const destino = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    origem: 'rotas',
    aoReceber: (mensagem) => recebidas.push(mensagem),
  })
  const emissorBruto = new Barramento(NOME_CANAL_SIMULACAO)
  const estadoSemSelecao = mensagemBase({
    tipo: 'estado_alterado',
    estado_execucao: 'executando',
  })

  assert.equal(mensagemSimulacaoValida(estadoSemSelecao), true)
  emissorBruto.postMessage(estadoSemSelecao)

  assert.deepEqual(recebidas, [])
  emissorBruto.close()
  destino.fechar()
})

test('IDs menores são seleções válidas e mensagens antigas/repetidas do emissor são ignoradas', () => {
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

  painel.publicar({ tipo: 'simulacao_selecionada', simulacaoId: 100, selecaoId: 's-100' })
  painel.publicar({ tipo: 'simulacao_selecionada', simulacaoId: 5, selecaoId: 's-5' })
  const canalEmissor = Barramento.instancias[0]
  canalEmissor.postMessage(mensagemBase({
    simulacao_id: 100,
    selecao_id: 's-100',
    sequencia: 1,
  }))

  assert.deepEqual(recebidas.map(({ simulacao_id }) => simulacao_id), [100, 5])
  rotas.fechar()
  painel.fechar()
})

test('seleções concorrentes empatadas convergem pelo identificador de origem', () => {
  const Barramento = criarBarramentoBroadcast({ deferir: true })
  const recebidas = []
  const destino = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    origem: 'rotas',
    aoReceber: (mensagem) => recebidas.push(mensagem),
  })
  const painelA = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    relogio: () => 100,
    origem: 'alfa',
  })
  const painelB = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: Barramento,
    relogio: () => 100,
    origem: 'zeta',
  })

  painelA.publicar({ tipo: 'simulacao_selecionada', simulacaoId: 90, selecaoId: 'a' })
  painelB.publicar({ tipo: 'simulacao_selecionada', simulacaoId: 3, selecaoId: 'b' })
  Barramento.descarregarFila()

  assert.deepEqual(recebidas.map(({ origem, simulacao_id }) => [origem, simulacao_id]), [
    ['alfa', 90],
    ['zeta', 3],
  ])
  assert.equal(recebidas.at(-1).origem, 'zeta')

  painelA.publicar({
    tipo: 'estado_alterado',
    simulacaoId: 90,
    selecaoId: 'a',
    estadoExecucao: 'executando',
  })
  Barramento.descarregarFila()
  assert.equal(recebidas.length, 2, 'estado da seleção perdedora não é aplicado')

  destino.fechar()
  painelA.fechar()
  painelB.fechar()
})

test('uma nova aba continua a revisão persistida sem depender do ID da simulação', () => {
  const valores = new Map()
  const storage = {
    getItem: (key) => valores.get(key) ?? null,
    setItem: (key, value) => valores.set(key, value),
  }
  const painelAntigo = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: null,
    storageTarget: storage,
    relogio: () => 100,
    origem: 'painel-antigo',
  })
  assert.equal(painelAntigo.publicar({
    tipo: 'simulacao_selecionada', simulacaoId: 90, selecaoId: 'antiga',
  }), true)
  const primeiraRevisao = Number(valores.get(CHAVE_REVISAO_SELECAO))
  painelAntigo.fechar()

  const painelNovo = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: null,
    storageTarget: storage,
    relogio: () => 100,
    origem: 'painel-novo',
  })
  assert.equal(painelNovo.publicar({
    tipo: 'simulacao_selecionada', simulacaoId: 3, selecaoId: 'nova',
  }), true)
  const mensagemPublicada = JSON.parse(valores.get(CHAVE_STORAGE_SIMULACAO))

  assert.equal(mensagemPublicada.simulacao_id, 3)
  assert.ok(mensagemPublicada.revisao_selecao > primeiraRevisao)
  assert.equal(Number(valores.get(CHAVE_REVISAO_SELECAO)), mensagemPublicada.revisao_selecao)
  painelNovo.fechar()
})

test('fallback por storage propaga seleção validada e remove o listener ao fechar', () => {
  const eventos = new Map()
  const gravacoes = []
  const janela = {
    addEventListener: (tipo, callback) => eventos.set(tipo, callback),
    removeEventListener: (tipo) => eventos.delete(tipo),
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
  const mensagem = mensagemBase({ origem: 'painel' })
  eventos.get('storage')({ key: CHAVE_STORAGE_SIMULACAO, newValue: JSON.stringify(mensagem) })
  assert.equal(recebidas[0].simulacao_id, 42)
  assert.equal(sync.publicar({
    tipo: 'estado_alterado', simulacaoId: 42, selecaoId: 'nao-local', estadoExecucao: 'pausada',
  }), false)
  sync.fechar()
  assert.equal(eventos.size, 0)

  const painel = criarSincronizadorAbasSimulacao({
    BroadcastChannelConstructor: null,
    windowTarget: janela,
    storageTarget: storage,
    origem: 'painel-local',
  })
  assert.equal(painel.publicar({
    tipo: 'simulacao_selecionada', simulacaoId: 12, selecaoId: 'local',
  }), true)
  const mensagemGravada = gravacoes.find(({ key }) => key === CHAVE_STORAGE_SIMULACAO)
  assert.ok(mensagemGravada)
  assert.equal(JSON.parse(mensagemGravada.value).versao, VERSAO_MENSAGENS_SIMULACAO)
  painel.fechar()
})
