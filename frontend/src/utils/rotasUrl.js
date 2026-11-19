export function criarUrlAcompanhamentoRotas(idSimulacao) {
  const caminho = '/rotas'
  if (idSimulacao === null || idSimulacao === undefined || idSimulacao === '') {
    return caminho
  }

  return `${caminho}?simulacaoId=${encodeURIComponent(String(idSimulacao))}`
}

export function obterIdSimulacaoDaBusca(busca) {
  const parametros = new URLSearchParams(busca ?? '')
  const valor = parametros.get('simulacaoId')
  if (!valor || !/^\d+$/.test(valor)) return null

  const id = Number(valor)
  return Number.isSafeInteger(id) && id > 0 ? id : null
}
