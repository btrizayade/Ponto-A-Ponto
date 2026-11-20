import test from 'node:test'
import assert from 'node:assert/strict'

import {
  calcularPosicoesEntregadores,
  FASES_ENTREGADOR,
} from './movimentacaoEntregadores.js'

const CENTRO = { nome: 'Comércio', latitude: 0, longitude: 0 }
const AGORA = '2026-10-30T09:00:00-03:00'
const FIM = '2026-10-30T17:00:00-03:00'

function parada({ ordem = 1, latitude = 0, longitude = 1, chegada = '09:10', saida = '09:20', codigo = `PED-${ordem}` } = {}) {
  return {
    ordem,
    pedido_codigo: codigo,
    latitude,
    longitude,
    chegada_em: `2026-10-30T${chegada}:00-03:00`,
    saida_em: `2026-10-30T${saida}:00-03:00`,
    status: 'em_rota',
  }
}

function viagem({
  numero = 1,
  partida = '09:00',
  retorno = '10:00',
  caminho = [[0, 0], [0, 1], [0, 3], [0, 0]],
  paradas = [parada()],
  situacao = 'em_andamento',
} = {}) {
  return {
    numero,
    situacao,
    partida_em: `2026-10-30T${partida}:00-03:00`,
    retorno_em: `2026-10-30T${retorno}:00-03:00`,
    caminho,
    paradas,
  }
}

function sim({ agora = AGORA, estado = 'executando', concluida = false } = {}) {
  return {
    agora,
    fim_expediente: FIM,
    estado_execucao: estado,
    concluida,
    segundos_reais_por_hora_simulada: 15,
  }
}

function rotas(...entregadores) {
  return {
    centro: CENTRO,
    rotas: entregadores.map(([codigo, viagens]) => ({
      entregador_codigo: codigo,
      viagens,
    })),
  }
}

function posicao(resultado, codigo) {
  return resultado.find((item) => item.entregador_codigo === codigo)
}

test('antes da partida o entregador aguarda no centro', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T08:59:00-03:00' }),
    rotas(['CAM-01', [viagem()]]),
  )

  assert.deepEqual(resultado[0].coordenada, [0, 0])
  assert.equal(resultado[0].fase, FASES_ENTREGADOR.AGUARDANDO_PARTIDA)
  assert.equal(resultado[0].parado, true)
})

test('simulação ainda não iniciada mantém veículos no centro mesmo no horário de partida', () => {
  const resultado = calcularPosicoesEntregadores(
    { ...sim(), iniciada: false },
    rotas(['CAM-01', [viagem()]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.AGUARDANDO_PARTIDA)
  assert.deepEqual(resultado.coordenada, [0, 0])
})

test('durante o deslocamento interpola por distância acumulada da polyline', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:05:00-03:00' }),
    rotas(['CAM-01', [viagem()]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.DESLOCANDO_PARA_PARADA)
  assert.ok(Math.abs(resultado.coordenada[1] - 0.5) < 0.01)
  assert.equal(resultado.em_deslocamento, true)
  assert.equal(resultado.pedido.pedido_codigo, 'PED-1')
})

test('durante o atendimento mantém a coordenada exata da parada', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:15:00-03:00' }),
    rotas(['CAM-01', [viagem()]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.ATENDENDO_PARADA)
  assert.deepEqual(resultado.coordenada, [0, 1])
  assert.equal(resultado.parado, true)
})

test('entre paradas interpola no segundo trecho, cuja extensão é diferente', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:30:00-03:00' }),
    rotas(['CAM-01', [viagem({
      retorno: '10:30',
      paradas: [
        parada({ ordem: 1, longitude: 1, chegada: '09:10', saida: '09:20' }),
        parada({ ordem: 2, longitude: 3, chegada: '09:40', saida: '09:50' }),
      ],
    })]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.DESLOCANDO_PARA_PROXIMA)
  assert.ok(Math.abs(resultado.coordenada[1] - 2) < 0.01)
  assert.equal(resultado.pedido.pedido_codigo, 'PED-2')
})

test('depois da última parada o entregador retorna ao centro', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:40:00-03:00' }),
    rotas(['CAM-01', [viagem({ retorno: '10:00' })]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.RETORNANDO_AO_CENTRO)
  assert.ok(resultado.coordenada[1] > 1 && resultado.coordenada[1] < 3)
  assert.equal(resultado.pedido, null)
})

test('viagem concluída e simulação concluída mantêm o veículo no centro', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T10:00:00-03:00', estado: 'concluida', concluida: true }),
    rotas(['CAM-01', [viagem({ retorno: '10:00', situacao: 'concluida' })]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.VIAGEM_CONCLUIDA)
  assert.deepEqual(resultado.coordenada, [0, 0])
  assert.equal(resultado.parado, true)
})

test('viagem cancelada nunca movimenta o entregador', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T17:00:00-03:00' }),
    rotas(['CAM-01', [viagem({ partida: '17:30', retorno: '18:00', situacao: 'cancelada' })]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.VIAGEM_CANCELADA)
  assert.deepEqual(resultado.coordenada, [0, 0])
  assert.equal(resultado.em_deslocamento, false)
})

test('dois entregadores são calculados simultaneamente e sem compartilhar posição', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:05:00-03:00' }),
    rotas(
      ['CAM-01', [viagem()]],
      ['CAM-02', [viagem({ paradas: [parada({ longitude: 2 })] })]],
    ),
  )

  assert.equal(resultado.length, 2)
  assert.notDeepEqual(posicao(resultado, 'CAM-01').coordenada, posicao(resultado, 'CAM-02').coordenada)
})

test('cinco entregadores são mantidos na movimentação simultânea', () => {
  const rotasComCinco = rotas(...Array.from({ length: 5 }, (_, indice) => [
    `CAM-${String(indice + 1).padStart(2, '0')}`,
    [viagem({ paradas: [parada({ codigo: `PED-${indice + 1}` })] })],
  ]))

  const resultado = calcularPosicoesEntregadores(sim(), rotasComCinco)

  assert.equal(resultado.length, 5)
  assert.deepEqual(
    resultado.map(({ entregador_codigo }) => entregador_codigo),
    ['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04', 'CAM-05'],
  )
})

test('múltiplas viagens do entregador selecionam a viagem vigente ou a próxima', () => {
  const viagens = [
    viagem({ numero: 1, partida: '09:00', retorno: '10:00', situacao: 'concluida' }),
    viagem({ numero: 2, partida: '10:30', retorno: '11:30', paradas: [parada({ chegada: '10:40', saida: '10:50' })] }),
  ]
  const intervalo = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T10:15:00-03:00' }),
    rotas(['CAM-01', viagens]),
  )[0]
  const segunda = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T10:35:00-03:00' }),
    rotas(['CAM-01', viagens]),
  )[0]

  assert.equal(intervalo.fase, FASES_ENTREGADOR.AGUARDANDO_PARTIDA)
  assert.equal(intervalo.viagem.numero, 2)
  assert.deepEqual(intervalo.coordenada, [0, 0])
  assert.equal(segunda.viagem.numero, 2)
  assert.equal(segunda.fase, FASES_ENTREGADOR.DESLOCANDO_PARA_PARADA)
})

test('paradas coincidentes mantêm a sequência e a mesma posição geográfica', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:30:00-03:00' }),
    rotas(['CAM-01', [viagem({
      retorno: '10:20',
      paradas: [
        parada({ ordem: 1, longitude: 1, chegada: '09:10', saida: '09:20' }),
        parada({ ordem: 2, longitude: 1, chegada: '09:20', saida: '09:40' }),
      ],
    })]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.ATENDENDO_PARADA)
  assert.deepEqual(resultado.coordenada, [0, 1])
  assert.equal(resultado.pedido.pedido_codigo, 'PED-2')
})

test('pausa congela a posição e retomada usa a nova âncora sem salto', () => {
  const viagens = rotas(['CAM-01', [viagem()]])
  const durante = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:05:00-03:00' }),
    viagens,
    { segundosReaisPorHoraSimulada: 15, tempoRealDecorridoMs: 1000 },
  )[0]
  const pausada = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:17:00-03:00', estado: 'pausada' }),
    viagens,
    { segundosReaisPorHoraSimulada: 15, tempoRealDecorridoMs: 5000 },
  )[0]
  const retomadaSemDelta = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:17:00-03:00', estado: 'executando' }),
    viagens,
    { segundosReaisPorHoraSimulada: 15, tempoRealDecorridoMs: 0 },
  )[0]

  assert.deepEqual(pausada.coordenada, [0, 1])
  assert.deepEqual(retomadaSemDelta.coordenada, pausada.coordenada)
  assert.notDeepEqual(durante.coordenada, pausada.coordenada)
})

test('as quatro velocidades convertem o mesmo delta real em avanço simulado', () => {
  const rotasTeste = rotas(['CAM-01', [viagem()]])
  const longitudes = new Map()
  for (const velocidade of [5, 15, 30, 60]) {
    const resultado = calcularPosicoesEntregadores(
      sim(),
      rotasTeste,
      { segundosReaisPorHoraSimulada: velocidade, tempoRealDecorridoMs: 1000 },
    )[0]
    longitudes.set(velocidade, resultado.coordenada[1])
  }

  assert.ok(longitudes.get(5) > longitudes.get(15))
  assert.ok(longitudes.get(15) > longitudes.get(30))
  assert.ok(longitudes.get(30) > longitudes.get(60))
  assert.equal(longitudes.get(5), 1)
  assert.ok(Math.abs(longitudes.get(15) - 0.4) < 0.01)
  assert.ok(Math.abs(longitudes.get(30) - 0.2) < 0.01)
  assert.ok(Math.abs(longitudes.get(60) - 0.1) < 0.01)
})

test('não usa delta local enquanto pausada ou concluída', () => {
  const rotasTeste = rotas(['CAM-01', [viagem()]])
  for (const estado of ['pausada', 'concluida']) {
    const base = calcularPosicoesEntregadores(
      sim({ agora: '2026-10-30T09:05:00-03:00', estado }),
      rotasTeste,
    )[0]
    const comDelta = calcularPosicoesEntregadores(
      sim({ agora: '2026-10-30T09:05:00-03:00', estado }),
      rotasTeste,
      { tempoRealDecorridoMs: 60_000 },
    )[0]
    assert.deepEqual(comDelta.coordenada, base.coordenada)
  }
})

test('rejeita velocidade e delta real inválidos', () => {
  const rotasTeste = rotas(['CAM-01', [viagem()]])
  assert.throws(
    () => calcularPosicoesEntregadores(sim(), rotasTeste, { segundosReaisPorHoraSimulada: 10 }),
    RangeError,
  )
  assert.throws(
    () => calcularPosicoesEntregadores(sim(), rotasTeste, { tempoRealDecorridoMs: -1 }),
    RangeError,
  )
})

test('associa paradas em ordem mesmo quando o caminho passa perto de si mesmo', () => {
  const resultado = calcularPosicoesEntregadores(
    sim({ agora: '2026-10-30T09:30:00-03:00' }),
    rotas(['CAM-01', [viagem({
      retorno: '11:00',
      caminho: [[0, 0], [0, 1], [1, 1], [0, 1.001], [0, 2], [0, 0]],
      paradas: [
        parada({ ordem: 1, longitude: 1, chegada: '09:10', saida: '09:20' }),
        parada({ ordem: 2, longitude: 2, chegada: '09:40', saida: '09:50' }),
      ],
    })]]),
  )[0]

  assert.equal(resultado.fase, FASES_ENTREGADOR.DESLOCANDO_PARA_PROXIMA)
  assert.equal(resultado.pedido.pedido_codigo, 'PED-2')
  assert.ok(resultado.coordenada[0] > 0.3 && resultado.coordenada[0] < 0.7)
})
