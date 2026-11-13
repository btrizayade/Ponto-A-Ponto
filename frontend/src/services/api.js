
// URL do backend configurada por variável de ambiente
const API_URL = import.meta.env?.VITE_API_URL || 'http://127.0.0.1:8000'

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

// Busca as opções de formulário expostas pelo backend.
export async function buscarConfiguracao() {
  const resposta = await fetch(`${API_URL}/api/configuracao`)

  return tratarResposta(
    resposta,
    'Não foi possível carregar as opções de cadastro.'
  )
}

// Busca os bairros já cadastrados, sem manter uma lista duplicada no frontend.
export async function buscarBairros() {
  const resposta = await fetch(`${API_URL}/api/bairros`)

  return tratarResposta(resposta, 'Não foi possível carregar os bairros.')
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

// Cadastra um pedido em um único cenário.
export async function criarPedido(dadosPedido) {
  const resposta = await fetch(`${API_URL}/api/pedidos`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(dadosPedido)
  })

  return tratarResposta(resposta, 'Não foi possível cadastrar o pedido.')
}

// Busca o estado atual de uma simulação
export async function buscarSimulacao(idSimulacao, opcoes = {}) {
  const opcoesFetch = Object.keys(opcoes).length > 0 ? opcoes : undefined
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}`,
    opcoesFetch
  )

  return tratarResposta(
    resposta,
    'Não foi possível carregar a simulação.'
  )
}

// Busca as viagens e paradas com o status correspondente ao relógio atual.
export async function buscarRotas(idSimulacao, opcoes = {}) {
  const opcoesFetch = Object.keys(opcoes).length > 0 ? opcoes : undefined
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}/rotas`,
    opcoesFetch
  )

  return tratarResposta(resposta, 'Não foi possível carregar as rotas.')
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

  const dados = await tratarResposta(
    resposta,
    'Não foi possível criar a simulação.'
  )

  if (dados.indicadores?.total_pedidos === 0) {
    throw new Error(
      'A simulação foi criada sem pedidos. Confira o cenário selecionado e tente novamente.'
    )
  }

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

  return tratarResposta(
    resposta,
    'Não foi possível avançar a simulação.'
  )
}

// Solicita ao backend que pause a simulação.
export async function pausarSimulacao(idSimulacao) {
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}/pausar`,
    { method: 'POST' }
  )

  return tratarResposta(resposta, 'Não foi possível pausar a simulação.')
}

// Solicita ao backend que retome uma simulação pausada.
export async function retomarSimulacao(idSimulacao) {
  const resposta = await fetch(
    `${API_URL}/api/simulacoes/${idSimulacao}/retomar`,
    { method: 'POST' }
  )

  return tratarResposta(resposta, 'Não foi possível retomar a simulação.')
}
