import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

import {
  buscarBairros,
  buscarCenarios,
  buscarConfiguracao,
  buscarRotas,
  buscarSimulacao,
  criarPedido,
  criarSimulacao,
  pausarSimulacao,
  retomarSimulacao
} from './api.js'


const fetchOriginal = globalThis.fetch

afterEach(() => {
  globalThis.fetch = fetchOriginal
})

test('pausar chama o endpoint e devolve a confirmação do backend', async () => {
  const respostaApi = {
    id: 42,
    estado_execucao: 'pausada',
    mensagem: 'Simulação pausada.',
    simulacao: { id: 42, estado_execucao: 'pausada' }
  }
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify(respostaApi), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  }

  const resultado = await pausarSimulacao(42)

  assert.equal(
    chamada.url,
    'http://127.0.0.1:8000/api/simulacoes/42/pausar'
  )
  assert.deepEqual(chamada.opcoes, { method: 'POST' })
  assert.deepEqual(resultado, respostaApi)
})

test('retomar chama o endpoint correto e devolve o estado confirmado', async () => {
  const respostaApi = {
    id: 7,
    estado_execucao: 'executando',
    mensagem: 'Simulação retomada.',
    simulacao: { id: 7, estado_execucao: 'executando' }
  }
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify(respostaApi), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  }

  const resultado = await retomarSimulacao(7)

  assert.equal(
    chamada.url,
    'http://127.0.0.1:8000/api/simulacoes/7/retomar'
  )
  assert.deepEqual(chamada.opcoes, { method: 'POST' })
  assert.deepEqual(resultado, respostaApi)
})

test('erro de transição da API vira mensagem compreensível', async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: 'A simulação já está pausada.' }),
    {
      status: 409,
      headers: { 'Content-Type': 'application/json' }
    }
  )

  await assert.rejects(
    pausarSimulacao(42),
    /A simulação já está pausada\. \(HTTP 409\)/
  )
})

test('consulta o estado atual no endpoint usado pelo acompanhamento automático', async () => {
  const estado = { id: 15, estado_execucao: 'executando', agora: '2026-10-30T10:05:00-03:00' }
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify(estado), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  }

  assert.deepEqual(await buscarSimulacao(15), estado)
  assert.equal(chamada.url, 'http://127.0.0.1:8000/api/simulacoes/15')
  assert.equal(chamada.opcoes, undefined)
})

test('consulta as rotas para atualizar viagens e paradas durante o polling', async () => {
  const rotas = { rotas: [{ entregador_codigo: 'CAM-01', viagens: [] }] }
  let chamada
  globalThis.fetch = async (url) => {
    chamada = url
    return new Response(JSON.stringify(rotas), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  }

  assert.deepEqual(await buscarRotas(15), rotas)
  assert.equal(chamada, 'http://127.0.0.1:8000/api/simulacoes/15/rotas')
})

test('envia o relógio simulado selecionado sem conversão para UTC', async () => {
  const dadosSimulacao = {
    cenario_id: 2,
    inicio: '2026-10-30T16:59:00',
    quantidade_entregadores: 2,
    provedor: 'simulado',
    segundos_reais_por_hora_simulada: 30
  }
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify({ id: 39, inicio: '2026-10-30T16:59:00-03:00' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' }
    })
  }

  const criada = await criarSimulacao(dadosSimulacao)

  assert.equal(criada.inicio, '2026-10-30T16:59:00-03:00')
  assert.equal(chamada.url, 'http://127.0.0.1:8000/api/simulacoes')
  assert.deepEqual(JSON.parse(chamada.opcoes.body), dadosSimulacao)
})

test('rejeita estado de criação sem pedidos com mensagem clara', async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({ indicadores: { total_pedidos: 0 } }),
    {
      status: 201,
      headers: { 'Content-Type': 'application/json' }
    }
  )

  await assert.rejects(
    criarSimulacao({ cenario_id: 1, inicio: '2026-10-30T10:00:00' }),
    /A simulação foi criada sem pedidos\. Confira o cenário selecionado/
  )
})

test('carrega cenários, bairros e opções diretamente dos endpoints da API', async () => {
  const respostas = {
    '/api/cenarios': [{ id: 2, codigo: 'ALTA_DEMANDA', nome: 'Alta demanda' }],
    '/api/bairros': [{ id: 8, nome: 'Pernambues', latitude: -12.971, longitude: -38.465 }],
    '/api/configuracao': {
      categorias_produto: ['alimento', 'medicamento', 'roupa', 'eletronico', 'outro'],
      modalidades_entrega: ['entrega_rapida', 'clube', 'convencional']
    }
  }
  const chamadas = []
  globalThis.fetch = async (url) => {
    chamadas.push(url)
    const caminho = new URL(url).pathname
    return new Response(JSON.stringify(respostas[caminho]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  }

  const [cenarios, bairros, configuracao] = await Promise.all([
    buscarCenarios(),
    buscarBairros(),
    buscarConfiguracao()
  ])

  assert.equal(cenarios[0].id, 2)
  assert.equal(bairros[0].id, 8)
  assert.deepEqual(configuracao.categorias_produto, respostas['/api/configuracao'].categorias_produto)
  assert.deepEqual(chamadas.sort(), [
    'http://127.0.0.1:8000/api/bairros',
    'http://127.0.0.1:8000/api/cenarios',
    'http://127.0.0.1:8000/api/configuracao'
  ])
})

test('envia apenas cenário, bairro, categoria e modalidade ao cadastrar', async () => {
  const dados = {
    cenario_id: 3,
    bairro_id: 5,
    categoria_produto: 'roupa',
    modalidade: 'clube'
  }
  let chamada
  globalThis.fetch = async (url, opcoes) => {
    chamada = { url, opcoes }
    return new Response(JSON.stringify({ id: 88, codigo: 'PED-MAN-X' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' }
    })
  }

  const pedido = await criarPedido(dados)

  assert.equal(pedido.id, 88)
  assert.equal(chamada.url, 'http://127.0.0.1:8000/api/pedidos')
  assert.equal(chamada.opcoes.method, 'POST')
  assert.deepEqual(JSON.parse(chamada.opcoes.body), dados)
})

test('erro de cadastro preserva uma mensagem clara da API', async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: 'Bairro não encontrado.' }),
    {
      status: 404,
      headers: { 'Content-Type': 'application/json' }
    }
  )

  await assert.rejects(
    criarPedido({
      cenario_id: 1,
      bairro_id: 999,
      categoria_produto: 'roupa',
      modalidade: 'clube'
    }),
    /Bairro não encontrado\. \(HTTP 404\)/
  )
})
