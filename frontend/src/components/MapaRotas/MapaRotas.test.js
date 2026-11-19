import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const jsxUrl = new URL('./MapaRotas.jsx', import.meta.url)
const vehiclesUrl = new URL('./VeiculosAnimados.jsx', import.meta.url)

test('o popup renderiza código, origem, entregador, viagem, ordem, bairro, status e atraso', async () => {
  const fonte = await readFile(jsxUrl, 'utf8')

  assert.match(fonte, /\{parada\.pedido_codigo\}/)
  assert.match(fonte, /Pedido manual/)
  assert.match(fonte, /Pedido de referência/)
  assert.match(fonte, /Origem não disponível/)
  assert.match(fonte, /Entregador: \{parada\.entregadorCodigo\}/)
  assert.match(fonte, /Viagem \{parada\.viagemNumero\} · Parada \{parada\.ordem\}/)
  assert.match(fonte, /Bairro: \{parada\.bairro\}/)
  assert.match(fonte, /Status: \{textoSituacao\(parada\.status\)\}/)
  assert.match(fonte, /parada\.atrasada &&/)
})

test('a posição Leaflet recebe as coordenadas originais; o ajuste visual fica no iconAnchor', async () => {
  const fonte = await readFile(jsxUrl, 'utf8')
  const icones = await readFile(new URL('./iconesMapa.js', import.meta.url), 'utf8')

  assert.match(fonte, /position=\{parada\.position\}/)
  assert.match(icones, /iconAnchor: \[16 - deslocamento\[0\], 16 - deslocamento\[1\]\]/)
})

test('ícones do centro, paradas e veículos vêm de fábricas memoizadas', async () => {
  const mapa = await readFile(jsxUrl, 'utf8')
  const veiculos = await readFile(vehiclesUrl, 'utf8')
  const icones = await readFile(new URL('./iconesMapa.js', import.meta.url), 'utf8')

  assert.match(mapa, /icon=\{obterIconeCentro\(\)\}/)
  assert.match(mapa, /icon=\{obterIconeParada\(/)
  assert.match(veiculos, /icon=\{obterIconeVeiculo\(cor\)\}/)
  assert.match(icones, /const obterOuCriar = criarCacheIcones\(\)/)
  const cache = await readFile(new URL('./cacheIcones.js', import.meta.url), 'utf8')
  assert.match(cache, /cache\.set\(chave, criar\(\)\)/)
})

test('MapaRotas integra a camada de veículos com simulação e rotas atuais', async () => {
  const fonte = await readFile(jsxUrl, 'utf8')

  assert.match(fonte, /import VeiculosAnimados from ['"]\.\/VeiculosAnimados\.jsx['"]?/)
  assert.match(fonte, /<VeiculosAnimados[\s\S]*?simulacao=\{simulacao\}[\s\S]*?rotas=\{rotas\}/)
  assert.match(fonte, /key=\{`veiculos-\$\{simulacao\.id\}`\}/)
})

test('a camada usa a função de posição, RAF e cancela a animação ao limpar o efeito', async () => {
  const fonte = await readFile(vehiclesUrl, 'utf8')

  assert.match(fonte, /calcularPosicoesEntregadores\(/)
  assert.match(fonte, /window\.requestAnimationFrame/)
  assert.match(fonte, /window\.cancelAnimationFrame/)
  assert.match(fonte, /return \(\) => loop\.parar\(\)/)
  assert.doesNotMatch(fonte, /Date\.now\(/)
})

test('ícones dos veículos usam a cor estável do entregador e mantêm popup identificável', async () => {
  const fonte = await readFile(vehiclesUrl, 'utf8')

  assert.match(fonte, /obterCorEntregador\(codigo\)/)
  assert.match(fonte, /position=\{posicao\.coordenada\}/)
  assert.match(fonte, /title=\{`\$\{codigo\}, viagem/)
  assert.match(fonte, /Pedido relacionado: \{parada\.pedido_codigo\}/)
})
