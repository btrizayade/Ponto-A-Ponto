import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('fábricas de Leaflet usam cache com identidade semântica e parâmetros completos', async () => {
  const fonte = await readFile(new URL('./iconesMapa.js', import.meta.url), 'utf8')

  assert.match(fonte, /obterOuCriar\('centro'/)
  assert.match(fonte, /obterOuCriar\(`veiculo:\$\{cor\}`/)
  assert.match(fonte, /JSON\.stringify\(\['parada', \.\.\.valores\]\)/)
})
