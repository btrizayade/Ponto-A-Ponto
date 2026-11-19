import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const jsxUrl = new URL('./EstadoOperacao.jsx', import.meta.url)
const cssUrl = new URL('./EstadoOperacao.css', import.meta.url)

test('EstadoOperacao não renderiza mapa nem recebe dados exclusivos de rotas', async () => {
  const fonte = await readFile(jsxUrl, 'utf8')

  assert.doesNotMatch(fonte, /MapaRotas|snapshotPedidosCarregando|snapshotPedidos=/)
  assert.doesNotMatch(fonte, /lista-viagens|viagem\.paradas/)
  assert.doesNotMatch(fonte, /fetch\s*\(|buscarRotas\s*\(/)
})

test('os cartões aparecem após o cabeçalho, sem espaço reservado ao mapa', async () => {
  const fonte = await readFile(jsxUrl, 'utf8')
  const css = await readFile(cssUrl, 'utf8')
  const indiceCabecalho = fonte.indexOf('className="estado-cabecalho"')
  const indiceCartoes = fonte.indexOf('className="lista-entregadores"')

  assert.ok(indiceCabecalho >= 0)
  assert.ok(indiceCartoes > indiceCabecalho)
  assert.equal(fonte.indexOf('<MapaRotas'), -1)
  assert.doesNotMatch(css, /mapa-rotas|lista-viagens/)
})

test('os cartões e resumos operacionais dos entregadores permanecem disponíveis', async () => {
  const fonte = await readFile(jsxUrl, 'utf8')

  assert.match(fonte, /className="card-entregador"/)
  assert.match(fonte, /entregador\.viagens_planejadas/)
  assert.match(fonte, /paradasRestantes/)
  assert.match(fonte, /entregadores\.map\(/)
})
