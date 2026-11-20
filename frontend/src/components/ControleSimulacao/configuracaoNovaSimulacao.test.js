import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'

import {
  criarDadosCriacaoSimulacao,
  obterConfiguracaoBaseNovaSimulacao,
  obterInicioFixoCenario
} from './configuracaoNovaSimulacao.js'

test('nova simulação prepara defaults sem criar ou iniciar uma execução', async () => {
  const configuracao = await obterConfiguracaoBaseNovaSimulacao({
    cenarios: [{ id: 8, nome: 'Operação normal' }],
    quantidadeEntregadoresPadrao: 2
  })

  assert.deepEqual(configuracao, {
    cenarioId: '8',
    quantidadeEntregadores: '2',
    velocidadeSimulacao: 15
  })
})

test('nova simulação preserva a quantidade escolhida antes de preparar a próxima operação', async () => {
  for (const quantidade of [1, 2, 3, 4, 5]) {
    const configuracao = await obterConfiguracaoBaseNovaSimulacao({
      cenarios: [{ id: 8, nome: 'Operação normal' }],
      quantidadeEntregadoresPadrao: 2,
      quantidadeEntregadoresSelecionada: String(quantidade)
    })

    assert.equal(configuracao.quantidadeEntregadores, String(quantidade))
  }
})

test('a configuração de criação preserva exatamente as opções de 1 a 5', () => {
  for (const quantidade of [1, 2, 3, 4, 5]) {
    assert.equal(criarDadosCriacaoSimulacao({
      cenarioId: '1',
      quantidade_entregadores: quantidade,
      segundosReaisPorHoraSimulada: 15
    }).quantidade_entregadores, quantidade)
  }
})

test('controle oferece 1 a 5 e envia o valor selecionado, sem restringir para dois', async () => {
  const fonte = await readFile(new URL('./ControleSimulacao.jsx', import.meta.url), 'utf8')

  for (const quantidade of [1, 2, 3, 4, 5]) {
    assert.match(fonte, new RegExp(`<option value="${quantidade}">`))
  }
  assert.match(fonte, /quantidade_entregadores: Number\(quantidadeEntregadores\)/)
  assert.match(fonte, /quantidadeEntregadoresSelecionada: quantidadeEntregadores/)
})

test('apresenta os inícios oficiais retornados para os três cenários', () => {
  const cenarios = [
    { id: 1, temporalidade: { inicio_simulacao: '2026-10-07T09:00:00-03:00', fuso_horario: 'America/Bahia' } },
    { id: 2, temporalidade: { inicio_simulacao: '2026-10-16T09:00:00-03:00', fuso_horario: 'America/Bahia' } },
    { id: 3, temporalidade: { inicio_simulacao: '2026-10-30T09:00:00-03:00', fuso_horario: 'America/Bahia' } }
  ]

  assert.deepEqual(cenarios.map(({ id }) => obterInicioFixoCenario(cenarios, id)), [
    { data: '2026-10-07', hora: '09:00', texto: '07/10/2026 às 09:00 (America/Bahia)' },
    { data: '2026-10-16', hora: '09:00', texto: '16/10/2026 às 09:00 (America/Bahia)' },
    { data: '2026-10-30', hora: '09:00', texto: '30/10/2026 às 09:00 (America/Bahia)' }
  ])
})

test('criação envia velocidade e cenário sem mandar início escolhido pelo usuário', () => {
  assert.deepEqual(criarDadosCriacaoSimulacao({
    cenarioId: '2',
    quantidade_entregadores: 2,
    segundosReaisPorHoraSimulada: 30
  }), {
    cenario_id: 2,
    quantidade_entregadores: 2,
    provedor: 'simulado',
    segundos_reais_por_hora_simulada: 30
  })
})

test('cenário sem início temporal não produz data inventada', () => {
  assert.equal(obterInicioFixoCenario([{ id: 7 }], 7), null)
})
