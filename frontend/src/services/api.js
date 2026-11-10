
// URL do backend configurada por variável de ambiente
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

// Verifica a resposta da API e apresenta mensagens de erro
async function tratarResposta(resposta, mensagemPadrao) {
  let dados = {}

  try {
    dados = await resposta.json()
  } catch {
    // Mantém um objeto vazio caso a resposta não tenha JSON
  }

  if (!resposta.ok) {
    const detalhe =
      typeof dados.detail === 'string'
        ? dados.detail
        : mensagemPadrao

    throw new Error(`${detalhe} (HTTP ${resposta.status})`)
  }

  return dados
}

// Busca os cenários cadastrados no backend
export async function buscarCenarios() {
  const resposta = await fetch(`${API_URL}/api/cenarios`)

  return tratarResposta(
    resposta,
    'Não foi possível carregar os cenários.'
  )
}

// Busca os pedidos de um cenário específico
export async function buscarPedidos(idCenario) {
  const resposta = await fetch(
    `${API_URL}/api/cenarios/${idCenario}/pedidos`
  )

  return tratarResposta(
    resposta,
    'Não foi possível carregar os pedidos.'
  )
}

// Busca o estado atual de uma simulação
export async function buscarSimulacao(idSimulacao) {
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}`
  )

  return tratarResposta(
    resposta,
    'Não foi possível carregar a simulação.'
  )
}

// Cria uma nova simulação
export async function criarSimulacao(dadosSimulacao) {
  const resposta = await fetch(`${API_URL}/api/simulacoes`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(dadosSimulacao)
  })

  return tratarResposta(
    resposta,
    'Não foi possível criar a simulação.'
  )
}

// Avança uma etapa da simulação
export async function avancarEtapa(idSimulacao) {
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}/proxima-etapa`,
    {
      method: 'POST'
    }
  )

  return tratarResposta(
    resposta,
    'Não foi possível avançar a simulação.'
  )
}
