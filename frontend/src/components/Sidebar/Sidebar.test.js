import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const sidebarUrl = new URL('./Sidebar.jsx', import.meta.url)
const cssUrl = new URL('./Sidebar.css', import.meta.url)

test('Rotas é um link acessível que abre a página independente em nova aba', async () => {
  const fonte = await readFile(sidebarUrl, 'utf8')

  assert.match(fonte, /nome: 'Rotas', icone: Route, disponivel: true/)
  assert.match(fonte, /href=\{urlRotas\}/)
  assert.match(fonte, /target="_blank"/)
  assert.match(fonte, /rel="noopener noreferrer"/)
  assert.match(fonte, /Abrir acompanhamento de rotas em uma nova aba/)
})

test('a logo é ampliada e centralizada no cartão sem editar a imagem original', async () => {
  const fonte = await readFile(sidebarUrl, 'utf8')
  const css = await readFile(cssUrl, 'utf8')

  assert.match(fonte, /sidebar-logo__recorte/)
  assert.match(fonte, /<img src=\{logo\} alt="Ponto-A-Ponto" \/>/)
  assert.match(css, /\.sidebar-logo__recorte[\s\S]*?overflow: hidden/)
  assert.match(css, /\.sidebar-logo img[\s\S]*?width: 130%[\s\S]*?height: auto/)
  assert.match(css, /justify-content: center/)
  assert.match(css, /align-items: center/)
  assert.match(css, /border-radius: 12px/)
})
