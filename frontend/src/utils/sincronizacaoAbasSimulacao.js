export const NOME_CANAL_SIMULACAO = 'ponto-a-ponto-simulacao'
export const CHAVE_STORAGE_SIMULACAO = 'ponto-a-ponto:simulacao:mensagem'

const TIPOS_MENSAGEM = new Set([
  'simulacao_selecionada',
  'estado_alterado',
  'simulacao_limpa',
])

function idValido(valor) {
  return Number.isSafeInteger(valor) && valor > 0
}

export function mensagemSimulacaoValida(mensagem) {
  if (
    !mensagem
    || mensagem.aplicacao !== 'ponto-a-ponto'
    || mensagem.versao !== 1
    || !TIPOS_MENSAGEM.has(mensagem.tipo)
    || typeof mensagem.origem !== 'string'
    || mensagem.origem.length === 0
    || !Number.isSafeInteger(mensagem.sequencia)
    || mensagem.sequencia < 1
  ) return false

  if (mensagem.tipo === 'simulacao_limpa') {
    return idValido(mensagem.simulacao_anterior_id)
  }

  return idValido(mensagem.simulacao_id)
}

function criarIdOrigem() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** Canal entre abas; usa storage event como fallback se BroadcastChannel faltar. */
export function criarSincronizadorAbasSimulacao({
  aoReceber,
  BroadcastChannelConstructor,
  windowTarget,
  storageTarget,
  origem = criarIdOrigem(),
} = {}) {
  const alvoJanela = windowTarget
    ?? (typeof window === 'undefined' ? null : window)
  const ConstrutorCanal = BroadcastChannelConstructor === undefined
    ? globalThis.BroadcastChannel
    : BroadcastChannelConstructor
  let armazenamento = storageTarget
  if (armazenamento === undefined) {
    try {
      armazenamento = alvoJanela?.localStorage
    } catch {
      armazenamento = null
    }
  }

  let sequencia = 0
  let fechado = false
  let canal = null
  const sequenciasRecebidas = new Map()

  function entregar(mensagem) {
    if (fechado || !mensagemSimulacaoValida(mensagem)) return
    const ultimaSequencia = sequenciasRecebidas.get(mensagem.origem) ?? 0
    if (mensagem.sequencia <= ultimaSequencia) return

    sequenciasRecebidas.set(mensagem.origem, mensagem.sequencia)
    aoReceber?.(mensagem)
  }

  function aoMensagemStorage(evento) {
    if (evento.key !== CHAVE_STORAGE_SIMULACAO || !evento.newValue) return
    try {
      entregar(JSON.parse(evento.newValue))
    } catch {
      // Mensagens malformadas são ignoradas sem interromper a página.
    }
  }

  if (typeof ConstrutorCanal === 'function') {
    try {
      canal = new ConstrutorCanal(NOME_CANAL_SIMULACAO)
      canal.addEventListener('message', (evento) => entregar(evento.data))
    } catch {
      canal?.close?.()
      canal = null
    }
  }

  if (!canal) alvoJanela?.addEventListener('storage', aoMensagemStorage)

  return {
    publicar({ tipo, simulacaoId, simulacaoAnteriorId, estadoExecucao } = {}) {
      if (fechado || !TIPOS_MENSAGEM.has(tipo)) return false
      const mensagem = {
        aplicacao: 'ponto-a-ponto',
        versao: 1,
        origem,
        sequencia: ++sequencia,
        tipo,
      }

      if (tipo === 'simulacao_limpa') {
        mensagem.simulacao_anterior_id = simulacaoAnteriorId
      } else {
        mensagem.simulacao_id = simulacaoId
      }
      if (tipo === 'estado_alterado') mensagem.estado_execucao = estadoExecucao
      if (!mensagemSimulacaoValida(mensagem)) return false

      if (canal) {
        try {
          canal.postMessage(mensagem)
          return true
        } catch {
          // Tenta o fallback se o canal deixar de estar disponível.
        }
      }

      try {
        armazenamento?.setItem(CHAVE_STORAGE_SIMULACAO, JSON.stringify(mensagem))
        return Boolean(armazenamento)
      } catch {
        return false
      }
    },
    fechar() {
      if (fechado) return
      fechado = true
      canal?.close?.()
      if (!canal) alvoJanela?.removeEventListener('storage', aoMensagemStorage)
    },
  }
}
