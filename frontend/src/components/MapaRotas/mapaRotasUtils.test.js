import test from 'node:test'
import assert from 'node:assert/strict'

import {
  classeSituacaoViagem,
  coletarPontosEnquadramento,
  deslocamentosVisuais,
  listarViagens,
  numeroMarcadorReferencia,
  obterCorEntregador,
  prepararMarcadores,
  resumoEntregadores,
  sequenciasPedidosManuais,
  textoSituacao,
} from './mapaRotasUtils.js'

const rotasExemplo = {
  centro: { nome: 'Comercio', latitude: -12.971, longitude: -38.501 },
  rotas: [
    {
      entregador_codigo: 'CAM-01',
      viagens: [
        {
          numero: 1,
          situacao: 'em_andamento',
          caminho: [[-12.971, -38.501], [-12.963, -38.507]],
          paradas: [{ latitude: -12.963, longitude: -38.507 }],
        },
        { numero: 2, situacao: 'concluida', caminho: [], paradas: [] },
      ],
    },
    {
      entregador_codigo: 'CAM-02',
      viagens: [{ numero: 1, situacao: 'planejada', caminho: [], paradas: [] }],
    },
  ],
}

test('a cor do entregador é determinística e compartilhada entre suas viagens', () => {
  assert.equal(obterCorEntregador('CAM-01'), obterCorEntregador('CAM-01'))
  const viagens = listarViagens(rotasExemplo)
  assert.equal(viagens[0].cor, viagens[1].cor)
  assert.notEqual(viagens[0].cor, viagens[2].cor)
})

test('as viagens mantêm entregador, número e situação recebidos da API', () => {
  const viagens = listarViagens(rotasExemplo)
  assert.deepEqual(viagens.map(({ entregadorCodigo, viagem }) => [
    entregadorCodigo,
    viagem.numero,
    viagem.situacao,
  ]), [
    ['CAM-01', 1, 'em_andamento'],
    ['CAM-01', 2, 'concluida'],
    ['CAM-02', 1, 'planejada'],
  ])
})

test('situações conhecidas recebem classes próprias e valores restantes são preservados', () => {
  assert.equal(classeSituacaoViagem('em_andamento'), 'em-andamento')
  assert.equal(classeSituacaoViagem('concluida'), 'concluida')
  assert.equal(classeSituacaoViagem('cancelada'), 'outra')
  assert.equal(textoSituacao('em_andamento'), 'em andamento')
  assert.equal(textoSituacao('cancelada'), 'cancelada')
})

test('o enquadramento usa coordenadas originais do centro, caminho e paradas', () => {
  assert.deepEqual(coletarPontosEnquadramento(rotasExemplo), [
    [-12.971, -38.501],
    [-12.971, -38.501],
    [-12.963, -38.507],
    [-12.963, -38.507],
  ])
})

test('a legenda lista entregadores sem duplicar e mantém as cores do mapa', () => {
  const legenda = resumoEntregadores(rotasExemplo)
  assert.deepEqual(legenda.map(({ codigo }) => codigo), ['CAM-01', 'CAM-02'])
  assert.equal(legenda[0].cor, listarViagens(rotasExemplo)[0].cor)
})

test('a legenda preserva todos os entregadores configurados mesmo sem viagens', () => {
  const rotas = {
    centro: { nome: 'Comércio', latitude: -12.971, longitude: -38.501 },
    rotas: Array.from({ length: 5 }, (_, indice) => ({
      entregador_codigo: `CAM-${String(indice + 1).padStart(2, '0')}`,
      viagens: [],
    })),
  }

  assert.deepEqual(
    resumoEntregadores(rotas).map(({ codigo }) => codigo),
    ['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04', 'CAM-05'],
  )
})

test('dados ainda indisponíveis produzem coleções vazias nas funções auxiliares', () => {
  assert.deepEqual(listarViagens(null), [])
  assert.deepEqual(resumoEntregadores(null), [])
  assert.deepEqual(coletarPontosEnquadramento(null), [])
})

function rotaComParadas(paradasPorViagem) {
  return {
    centro: { nome: 'Comercio', latitude: -12.971, longitude: -38.501 },
    rotas: paradasPorViagem.map(({ entregador, numero, paradas }) => ({
      entregador_codigo: entregador,
      viagens: [{ numero, situacao: 'concluida', caminho: [], paradas }],
    })),
    nao_atribuidos: [],
  }
}

test('pedidos de referência usam os números extraídos do código', () => {
  assert.equal(numeroMarcadorReferencia('PED-001', 8), '1')
  assert.equal(numeroMarcadorReferencia('PED-010', 2), '10')

  const marcadores = prepararMarcadores(rotaComParadas([{
    entregador: 'CAM-01',
    numero: 1,
    paradas: [
      { latitude: 1, longitude: 1, ordem: 8, pedido_codigo: 'PED-001' },
      { latitude: 2, longitude: 2, ordem: 2, pedido_codigo: 'PED-010' },
    ],
  }]), [
    { id: 1, codigo: 'PED-001', origem: 'referencia' },
    { id: 2, codigo: 'PED-010', origem: 'referencia' },
  ])
  assert.deepEqual(marcadores.map(({ rotulo }) => rotulo), ['1', '10'])
})

test('pedidos manuais recebem M1, M2, M3 pela ordem crescente do ID do snapshot', () => {
  const snapshot = [
    { id: 32, codigo: 'manual-c', origem: 'manual' },
    { id: 28, codigo: 'manual-a', origem: 'manual' },
    { id: 30, codigo: 'manual-b', origem: 'manual' },
    { id: 12, codigo: 'PED-001', origem: 'referencia' },
  ]

  assert.deepEqual([...sequenciasPedidosManuais(snapshot)], [
    ['manual-a', 'M1'],
    ['manual-b', 'M2'],
    ['manual-c', 'M3'],
  ])

  const marcadores = prepararMarcadores(rotaComParadas([{
    entregador: 'CAM-01',
    numero: 1,
    paradas: snapshot
      .filter((pedido) => pedido.origem === 'manual')
      .map((pedido, indice) => ({
        latitude: -12.9 - indice / 100,
        longitude: -38.4,
        ordem: indice + 1,
        pedido_codigo: pedido.codigo,
      })),
  }]), snapshot)
  assert.deepEqual(
    marcadores.map((marcador) => [marcador.pedido_codigo, marcador.rotulo]),
    [['manual-c', 'M3'], ['manual-a', 'M1'], ['manual-b', 'M2']],
  )
})

test('a sequência manual reinicia quando uma nova simulação tem seu próprio snapshot', () => {
  const sequenciaA = sequenciasPedidosManuais([
    { id: 28, codigo: 'manual-a', origem: 'manual' },
    { id: 30, codigo: 'manual-b', origem: 'manual' },
  ])
  const sequenciaB = sequenciasPedidosManuais([
    { id: 32, codigo: 'manual-c', origem: 'manual' },
  ])

  assert.equal(sequenciaA.get('manual-a'), 'M1')
  assert.equal(sequenciaB.get('manual-c'), 'M1')
})

test('identificadores e posições visuais permanecem estáveis quando a ordem da rota muda no polling', () => {
  const snapshot = [
    { id: 31, codigo: 'manual-b', origem: 'manual' },
    { id: 29, codigo: 'manual-a', origem: 'manual' },
  ]
  const rota = (paradas) => rotaComParadas([{ entregador: 'CAM-01', numero: 1, paradas }])
  const paradas = [
    { latitude: -12.963, longitude: -38.507, ordem: 1, pedido_codigo: 'manual-a' },
    { latitude: -12.963, longitude: -38.507, ordem: 2, pedido_codigo: 'manual-b' },
  ]
  const antes = prepararMarcadores(rota(paradas), snapshot)
  const depois = prepararMarcadores(rota([...paradas].reverse()), snapshot)
  const indexar = (marcadores) => new Map(marcadores.map((marcador) => [
    marcador.pedido_codigo,
    { rotulo: marcador.rotulo, deslocamento: marcador.deslocamento },
  ]))

  assert.deepEqual(indexar(depois), indexar(antes))
})

test('coordenadas iguais em entregadores e viagens distintas geram marcadores separados e visíveis', () => {
  const coordenadas = { latitude: -13.006, longitude: -38.528 }
  const rotas = {
    rotas: [
      {
        entregador_codigo: 'CAM-01',
        viagens: [{
          numero: 1,
          paradas: [{ ...coordenadas, ordem: 5, pedido_codigo: 'PED-002' }],
        }],
      },
      {
        entregador_codigo: 'CAM-02',
        viagens: [{
          numero: 2,
          paradas: [{ ...coordenadas, ordem: 1, pedido_codigo: 'manual-z' }],
        }],
      },
    ],
  }
  const marcadores = prepararMarcadores(rotas, [
    { id: 3, codigo: 'PED-002', origem: 'referencia' },
    { id: 20, codigo: 'manual-z', origem: 'manual' },
  ])

  assert.equal(marcadores.length, 2)
  assert.deepEqual(marcadores.map(({ position }) => position), [
    [-13.006, -38.528],
    [-13.006, -38.528],
  ])
  assert.notDeepEqual(marcadores[0].deslocamento, marcadores[1].deslocamento)
  assert.deepEqual(marcadores.map(({ entregadorCodigo, viagemNumero }) => [
    entregadorCodigo,
    viagemNumero,
  ]), [['CAM-01', 1], ['CAM-02', 2]])
})

test('paradas coincidentes recebem posições visuais distintas sem mudar coordenadas geográficas', () => {
  const paradas = [
    { latitude: -13.006, longitude: -38.528, ordem: 1, pedido_codigo: 'PED-002' },
    { latitude: -13.006, longitude: -38.528, ordem: 2, pedido_codigo: 'PED-010' },
  ]
  const rotas = rotaComParadas([{ entregador: 'CAM-01', numero: 1, paradas }])
  const marcadores = prepararMarcadores(rotas, [
    { id: 1, codigo: 'PED-002', origem: 'referencia' },
    { id: 2, codigo: 'PED-010', origem: 'referencia' },
  ])

  assert.equal(marcadores.length, 2)
  assert.notDeepEqual(marcadores[0].deslocamento, marcadores[1].deslocamento)
  assert.deepEqual(marcadores.map(({ position }) => position), [
    [-13.006, -38.528],
    [-13.006, -38.528],
  ])
  assert.deepEqual(paradas.map(({ latitude, longitude }) => [latitude, longitude]), [
    [-13.006, -38.528],
    [-13.006, -38.528],
  ])
})

test('paradas com coordenadas diferentes permanecem na posição original e sem deslocamento', () => {
  const rotas = rotaComParadas([{
    entregador: 'CAM-01',
    numero: 1,
    paradas: [
      { latitude: -12.963, longitude: -38.507, ordem: 1, pedido_codigo: 'PED-001' },
      { latitude: -12.9630001, longitude: -38.507, ordem: 2, pedido_codigo: 'PED-009' },
    ],
  }])
  const marcadores = prepararMarcadores(rotas, [
    { id: 1, codigo: 'PED-001', origem: 'referencia' },
    { id: 2, codigo: 'PED-009', origem: 'referencia' },
  ])

  assert.equal(marcadores.length, 2)
  assert.deepEqual(marcadores.map(({ deslocamento }) => deslocamento), [[0, 0], [0, 0]])
  assert.deepEqual(marcadores.map(({ position }) => position), [
    [-12.963, -38.507],
    [-12.9630001, -38.507],
  ])
})

test('deslocamentos são determinísticos e espaçados para manter os marcadores lado a lado', () => {
  const primeiraExecucao = deslocamentosVisuais(5)
  const segundaExecucao = deslocamentosVisuais(5)

  assert.deepEqual(primeiraExecucao, segundaExecucao)
  assert.equal(new Set(primeiraExecucao.map((ponto) => ponto.join(','))).size, 5)
  for (let i = 0; i < primeiraExecucao.length; i += 1) {
    for (let j = i + 1; j < primeiraExecucao.length; j += 1) {
      assert.ok(
        Math.abs(primeiraExecucao[i][0] - primeiraExecucao[j][0]) >= 32
        || Math.abs(primeiraExecucao[i][1] - primeiraExecucao[j][1]) >= 32
      )
    }
  }
})

test('marcadores preservam todos os dados usados no popup', () => {
  const parada = {
    latitude: -13.006,
    longitude: -38.528,
    ordem: 4,
    pedido_codigo: 'manual-original-codigo',
    bairro: 'Barra',
    status: 'entregue',
    atrasada: true,
  }
  const [marcador] = prepararMarcadores(
    rotaComParadas([{ entregador: 'CAM-02', numero: 3, paradas: [parada] }]),
    [{ id: 40, codigo: parada.pedido_codigo, origem: 'manual' }],
  )

  assert.equal(marcador.pedido_codigo, 'manual-original-codigo')
  assert.equal(marcador.origem, 'manual')
  assert.equal(marcador.entregadorCodigo, 'CAM-02')
  assert.equal(marcador.viagemNumero, 3)
  assert.equal(marcador.ordem, 4)
  assert.equal(marcador.bairro, 'Barra')
  assert.equal(marcador.status, 'entregue')
  assert.equal(marcador.atrasada, true)
  assert.equal(marcador.rotulo, 'M1')
})

test('coordenadas originais da API não são modificadas ao preparar marcadores', () => {
  const paradas = [
    { latitude: -12.963, longitude: -38.507, ordem: 1, pedido_codigo: 'PED-001' },
    { latitude: -12.963, longitude: -38.507, ordem: 2, pedido_codigo: 'PED-009' },
  ]
  const original = structuredClone(paradas)
  const marcadores = prepararMarcadores(
    rotaComParadas([{ entregador: 'CAM-01', numero: 1, paradas }]),
    [
      { id: 1, codigo: 'PED-001', origem: 'referencia' },
      { id: 2, codigo: 'PED-009', origem: 'referencia' },
    ],
  )

  assert.deepEqual(paradas, original)
  assert.equal(marcadores.length, paradas.length)
})
