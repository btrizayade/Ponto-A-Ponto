const API_URL = 'http://127.0.0.1:8000'

// Busca os cenários cadastrados no backend
export async function buscarCenarios() {
  const resposta = await fetch(`${API_URL}/api/cenarios`)

  if (!resposta.ok) {
    throw new Error('Não foi possível carregar os cenários.')
  }

  const dados = await resposta.json()

  return dados
}

// Busca os pedidos de um cenário específico
export async function buscarPedidos(idCenario) {
  const resposta = await fetch(
    `${API_URL}/api/cenarios/${idCenario}/pedidos`
  )

  if (!resposta.ok) {
    throw new Error('Não foi possível carregar os pedidos.')
  }

  const dados = await resposta.json()

  return dados
}

// Busca o estado atual de uma simulação
export async function buscarSimulacao(idSimulacao) {
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}`
  )

  if (!resposta.ok) {
    throw new Error('Não foi possível carregar a simulação.')
  }

  const dados = await resposta.json()

  return dados
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

  if (!resposta.ok) {
    const erro = await resposta.json()
    throw new Error(erro.detail || 'Não foi possível criar a simulação.')
  }

  const dados = await resposta.json()

  return dados
}

// Avança uma etapa da simulação
export async function avancarEtapa(idSimulacao) {
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}/proxima-etapa`,
    {
      method: 'POST'
    }
  )

  if (!resposta.ok) {
    throw new Error('Não foi possível avançar a simulação.')
  }

  const dados = await resposta.json()

  return dados
}
