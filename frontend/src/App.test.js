import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const appUrl = new URL('./App.jsx', import.meta.url)

test('painel principal não carrega auditoria exclusiva da página de rotas', async () => {
  const fonte = await readFile(appUrl, 'utf8')

  assert.doesNotMatch(fonte, /buscarParametrosSimulacao|snapshot_pedidos|snapshotPedidos/)
  assert.match(fonte, /<FilaPedidos/)
  assert.match(fonte, /<EstadoOperacao[\s\S]*?simulacao=\{simulacao\}/)
})

test('App monta a página independente em /rotas sem substituir o painel principal em /', async () => {
  const fonte = await readFile(appUrl, 'utf8')

  assert.match(fonte, /window\.location\.pathname\.replace\(\/\\\/\$\/, ''\) === '\/rotas'/)
  assert.match(fonte, /return <AcompanhamentoRotas \/>/)
  assert.match(fonte, /return <PainelPrincipal \/>/)
  assert.match(fonte, /urlRotas=\{criarUrlAcompanhamentoRotas\(idSimulacao\)\}/)
})

test('App publica seleção e mudanças de estado para sincronizar a aba de rotas', async () => {
  const fonte = await readFile(appUrl, 'utf8')

  assert.match(fonte, /criarSincronizadorAbasSimulacao\(\)/)
  assert.match(fonte, /tipo: 'simulacao_selecionada'/)
  assert.match(fonte, /tipo: 'simulacao_limpa'/)
  assert.match(fonte, /tipo: 'estado_alterado'/)
  assert.match(fonte, /selecaoId: selecaoSimulacaoRef\.current/)
  assert.match(fonte, /selecaoId,/)
  assert.match(fonte, /criarIdentificadorSelecao\(\)/)
  assert.match(fonte, /publicarEstadoEntreAbas\(estado\)/)
  assert.match(fonte, /sincronizador\.fechar\(\)/)
})

test('painel preserva controles e cartões sem buscar ou renderizar rotas', async () => {
  const fonte = await readFile(appUrl, 'utf8')

  assert.match(fonte, /<ControleSimulacao/)
  assert.match(fonte, /<EstadoOperacao[\s\S]*?simulacao=\{simulacao\}/)
  assert.doesNotMatch(fonte, /buscarRotas|<MapaRotas|\[rotas, setRotas\]/)
  assert.match(fonte, /publicarEstadoEntreAbas\(estado\)/)
})
