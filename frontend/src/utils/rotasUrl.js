import { EVENTO_SELECAO_SIMULACAO } from './sincronizacaoAbasSimulacao.js'

export function criarUrlAcompanhamentoRotas(idSimulacao) {
  const caminho = '/rotas'
  if (idSimulacao === null || idSimulacao === undefined || idSimulacao === '') {
    return caminho
  }

  return `${caminho}?simulacaoId=${encodeURIComponent(String(idSimulacao))}`
}

/** Altera a query da página e notifica a aplicação sobre a navegação programática. */
export function atualizarUrlAcompanhamentoRotas(
  idSimulacao,
  windowTarget = window,
  {
    substituir = true,
    notificar = true,
    CustomEventConstructor = globalThis.CustomEvent,
  } = {},
) {
  const url = new URL(windowTarget.location.href)
  url.pathname = '/rotas'
  if (idSimulacao === null || idSimulacao === undefined || idSimulacao === '') {
    url.searchParams.delete('simulacaoId')
  } else {
    url.searchParams.set('simulacaoId', String(idSimulacao))
  }

  const metodo = substituir ? 'replaceState' : 'pushState'
  windowTarget.history[metodo](windowTarget.history.state, '', url)
  if (notificar) {
    windowTarget.dispatchEvent(new CustomEventConstructor(
      EVENTO_SELECAO_SIMULACAO,
      { detail: { search: url.search } },
    ))
  }
}

export function obterIdSimulacaoDaBusca(busca) {
  const parametros = new URLSearchParams(busca ?? '')
  const valor = parametros.get('simulacaoId')
  if (!valor || !/^\d+$/.test(valor)) return null

  const id = Number(valor)
  return Number.isSafeInteger(id) && id > 0 ? id : null
}
