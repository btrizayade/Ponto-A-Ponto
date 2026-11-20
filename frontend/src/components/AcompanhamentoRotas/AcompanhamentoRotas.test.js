import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const pageUrl = new URL('./AcompanhamentoRotas.jsx', import.meta.url)
const cssUrl = new URL('./AcompanhamentoRotas.css', import.meta.url)

test('a página obtém o ID da URL e consulta os serviços de estado, rotas e snapshot', async () => {
  const fonte = await readFile(pageUrl, 'utf8')

  assert.match(fonte, /obterIdSimulacaoDaBusca\(window\.location\.search\)/)
  assert.match(fonte, /buscarSimulacao\(idSimulacao/)
  assert.match(fonte, /buscarRotas\(idSimulacao/)
  assert.match(fonte, /buscarParametrosSimulacao\(idSimulacao/)
  assert.match(fonte, /estado\.iniciada/)
})

test('a página mantém polling para refletir pausa e retomada e para ao concluir ou perder a simulação', async () => {
  const fonte = await readFile(pageUrl, 'utf8')

  assert.match(fonte, /if \(desmontado \|\| terminal\) return/)
  assert.match(fonte, /estado\.estado_execucao === 'concluida' \|\| estado\.concluida/)
  assert.match(fonte, /HTTP 404[\s\S]*HTTP 410/)
  assert.match(fonte, /window\.clearTimeout\(temporizador\)/)
  assert.match(fonte, /consultaAtual\?\.abort\(\)/)
  assert.doesNotMatch(fonte, /criarSimulacao|pausarSimulacao|retomarSimulacao/)
})

test('HTTP 404/410 marca o relógio como não autoritativo e informa que a animação congelou', async () => {
  const fonte = await readFile(pageUrl, 'utf8')
  const veiculos = await readFile(new URL('../MapaRotas/VeiculosAnimados.jsx', import.meta.url), 'utf8')
  const mapa = await readFile(new URL('../MapaRotas/MapaRotas.jsx', import.meta.url), 'utf8')

  assert.match(fonte, /if \(terminal\) setEstadoAutoritativo\(false\)/)
  assert.match(fonte, /Estado não disponível na API\. A animação foi congelada/)
  assert.match(fonte, /estadoAutoritativo=\{estadoAutoritativo\}/)
  assert.match(mapa, /estadoAutoritativo=\{estadoAutoritativo\}/)
  assert.match(veiculos, /if \(!estadoAutoritativo\) return/)
  assert.match(veiculos, /if \(!estadoAutoritativo \|\| simulacao\?\.estado_execucao !== 'executando'\)/)
})

test('a página acompanha seleções versionadas, limpa e estado apenas da seleção atual', async () => {
  const fonte = await readFile(pageUrl, 'utf8')

  assert.match(fonte, /useState\(\s*\(\) => obterIdSimulacaoDaBusca/)
  assert.match(fonte, /criarSincronizadorAbasSimulacao\(/)
  assert.match(fonte, /mensagem\.tipo === 'simulacao_limpa'/)
  assert.match(fonte, /mensagem\.tipo === 'simulacao_selecionada'/)
  assert.match(fonte, /if \(mensagem\.tipo === 'simulacao_limpa'\) \{[\s\S]*?setIdSimulacao\(null\)/)
  assert.doesNotMatch(fonte, /simulacao_anterior_id !== idSimulacaoRef\.current/)
  assert.match(fonte, /mensagem\.selecao_id/)
  assert.doesNotMatch(fonte, /novoId < idAtual/)
  assert.match(fonte, /solicitarConsultaRef\.current\?\.\(\)/)
  assert.match(fonte, /limparDados\(\)/)
  assert.match(fonte, /return \(\) => \{[\s\S]*?sincronizador\.fechar\(\)/)
})

test('a página sincroniza URL inicial, popstate e alterações programáticas e remove listeners', async () => {
  const fonte = await readFile(pageUrl, 'utf8')

  assert.match(fonte, /window\.addEventListener\('popstate', aoPopstate\)/)
  assert.match(fonte, /EVENTO_SELECAO_SIMULACAO, aoAlterarUrlProgramaticamente/)
  assert.match(fonte, /obterIdSimulacaoDaBusca\(busca\)/)
  assert.match(fonte, /atualizarUrlAcompanhamentoRotas\([\s\S]*?mensagem\.simulacao_id/)
  assert.match(fonte, /window\.removeEventListener\('popstate', aoPopstate\)/)
  assert.match(fonte, /consultaAtual\?\.abort\(\)/)
  assert.match(fonte, /consulta\.abort\(\)/)
})

test('a página sem ID permanece em espera e mantém a inscrição ativa', async () => {
  const fonte = await readFile(pageUrl, 'utf8')

  assert.match(fonte, /Nenhuma simulação foi selecionada para acompanhamento/)
  assert.match(fonte, /useEffect\(\(\) => \{[\s\S]*?criarSincronizadorAbasSimulacao/)
  assert.match(fonte, /\}, \[\]\)/)
})

test('antes do planejamento mostra orientação e passa os dados atuais para o mapa existente', async () => {
  const fonte = await readFile(pageUrl, 'utf8')

  assert.match(fonte, /As rotas aparecerão aqui quando o planejamento começar/)
  assert.match(fonte, /<MapaRotas[\s\S]*?rotas=\{rotas\}[\s\S]*?simulacao=\{simulacao\}/)
  assert.match(fonte, /snapshotPedidos=\{snapshotPedidos\}/)
})

test('a página independente mantém o mapa, rotas e dados para veículos animados', async () => {
  const fontePagina = await readFile(pageUrl, 'utf8')
  const fonteMapa = await readFile(new URL('../MapaRotas/MapaRotas.jsx', import.meta.url), 'utf8')

  assert.match(fontePagina, /<MapaRotas[\s\S]*?rotas=\{rotas\}/)
  assert.match(fonteMapa, /<Polyline[\s\S]*?viagem\.caminho/)
  assert.match(fonteMapa, /<VeiculosAnimados[\s\S]*?simulacao=\{simulacao\}[\s\S]*?rotas=\{rotas\}/)
  assert.match(fonteMapa, /<Marker/)
})

test('a página mostra a identificação, estado e contagens de entregadores', async () => {
  const fonte = await readFile(pageUrl, 'utf8')

  assert.match(fonte, /Acompanhamento de Rotas/)
  assert.match(fonte, /Simulação #\$\{idSimulacao\}/)
  assert.match(fonte, /Entregadores configurados/)
  assert.match(fonte, /entregador\.situacao === 'em_viagem'/)
  assert.match(fonte, /Voltar ao painel principal/)
})

test('o mapa recebe área ampliada e responsiva na página independente', async () => {
  const css = await readFile(cssUrl, 'utf8')
  assert.match(css, /height: calc\(100vh - 275px\)/)
  assert.match(css, /@media \(max-width: 700px\)/)
})
