import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const fonte = await readFile(new URL('./ControleSimulacao.jsx', import.meta.url), 'utf8')

test('controle mostra início da API sem inputs editáveis de data ou hora', () => {
  assert.match(fonte, /inicioCenario\?\.texto/)
  assert.doesNotMatch(fonte, /type=["'](?:date|time)["']/)
  assert.doesNotMatch(fonte, /sugerirInicioSimulado/)
})

test('controle não envia campo inicio na criação da simulação', () => {
  assert.match(fonte, /criarSimulacao\(criarDadosCriacaoSimulacao\(/)
  assert.doesNotMatch(fonte, /inicio:\s*criarInicioApi/)
})
