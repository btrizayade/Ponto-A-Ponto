import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  bloquearEnvioDuplicado,
  camposPedidoValidos,
  liberarEnvio,
  montarPedidoRequest,
  restricoesDataCriacao
} from './pedidoForm.js'

test('formulário exige os cinco campos antes de habilitar cadastro', () => {
  assert.equal(camposPedidoValidos({}), false)
  assert.equal(camposPedidoValidos({
    cenario_id: '1',
    bairro_id: '2',
    data_criacao: '2026-10-07',
    categoria_produto: 'alimento'
  }), false)
  assert.equal(camposPedidoValidos({
    cenario_id: '1',
    bairro_id: '2',
    data_criacao: '2026-10-07',
    categoria_produto: 'alimento',
    modalidade: 'entrega_rapida'
  }), true)
})

test('request envia ids numéricos e os valores de categoria e modalidade', () => {
  assert.deepEqual(montarPedidoRequest({
    cenario_id: '3',
    bairro_id: '8',
    data_criacao: '2026-10-16',
    categoria_produto: 'medicamento',
    modalidade: 'clube'
  }), {
    cenario_id: 3,
    bairro_id: 8,
    data_criacao: '2026-10-16',
    categoria_produto: 'medicamento',
    modalidade: 'clube'
  })
})

test('request aceita a modalidade convencional recebida da configuração', () => {
  assert.deepEqual(montarPedidoRequest({
    cenario_id: '3',
    bairro_id: '5',
    data_criacao: '2026-10-16',
    categoria_produto: 'roupa',
    modalidade: 'convencional'
  }), {
    cenario_id: 3,
    bairro_id: 5,
    data_criacao: '2026-10-16',
    categoria_produto: 'roupa',
    modalidade: 'convencional'
  })
})

test('data usa janela e data inicial retornadas pela API do cenário', () => {
  assert.deepEqual(restricoesDataCriacao({
    temporalidade: {
      janela_criacao: { inicio: '2026-10-12', fim: '2026-10-16' },
      inicio_simulacao: '2026-10-16T09:00:00-03:00'
    }
  }), {
    minimo: '2026-10-12',
    maximo: '2026-10-16',
    valorInicial: '2026-10-16'
  })
})

test('bloqueia submissão concorrente e libera nova tentativa após resposta', () => {
  const refSubmissao = { current: false }

  assert.equal(bloquearEnvioDuplicado(refSubmissao), true)
  assert.equal(bloquearEnvioDuplicado(refSubmissao), false)
  liberarEnvio(refSubmissao)
  assert.equal(bloquearEnvioDuplicado(refSubmissao), true)
})
