export const NOME_CANAL_SIMULACAO = 'ponto-a-ponto-simulacao'
export const CHAVE_STORAGE_SIMULACAO = 'ponto-a-ponto:simulacao:mensagem'
export const CHAVE_REVISAO_SELECAO = 'ponto-a-ponto:simulacao:revisao'
export const EVENTO_SELECAO_SIMULACAO = 'ponto-a-ponto:simulacao-selecionada'
export const VERSAO_MENSAGENS_SIMULACAO = 2

const ESTADOS_EXECUCAO = new Set([
  'aguardando',
  'executando',
  'pausada',
  'concluida',
  'falhou',
])

const CAMPOS_COMUNS = ['aplicacao', 'versao', 'origem', 'sequencia', 'tipo']
const CAMPOS_POR_TIPO = {
  simulacao_selecionada: [
    'simulacao_id',
    'selecao_id',
    'revisao_selecao',
  ],
  estado_alterado: [
    'simulacao_id',
    'selecao_id',
    'revisao_selecao',
    'estado_execucao',
  ],
  simulacao_limpa: [
    'simulacao_anterior_id',
    'selecao_anterior_id',
    'revisao_selecao',
  ],
}
const OPCOES_PUBLICACAO_POR_TIPO = {
  simulacao_selecionada: ['tipo', 'simulacaoId', 'selecaoId'],
  estado_alterado: ['tipo', 'simulacaoId', 'selecaoId', 'estadoExecucao'],
  simulacao_limpa: ['tipo', 'simulacaoAnteriorId', 'selecaoId'],
}

function idValido(valor) {
  return Number.isSafeInteger(valor) && valor > 0
}

function textoValido(valor) {
  return typeof valor === 'string' && valor.trim().length > 0 && valor.length <= 200
}

function camposExatos(mensagem, camposEspecificos) {
  const esperados = new Set([...CAMPOS_COMUNS, ...camposEspecificos])
  return Object.keys(mensagem).every((campo) => esperados.has(campo))
    && [...esperados].every((campo) => Object.hasOwn(mensagem, campo))
}

export function mensagemSimulacaoValida(mensagem) {
  if (
    !mensagem
    || typeof mensagem !== 'object'
    || Array.isArray(mensagem)
    || mensagem.aplicacao !== 'ponto-a-ponto'
    || mensagem.versao !== VERSAO_MENSAGENS_SIMULACAO
    || !Object.hasOwn(CAMPOS_POR_TIPO, mensagem.tipo)
    || !textoValido(mensagem.origem)
    || !Number.isSafeInteger(mensagem.sequencia)
    || mensagem.sequencia < 1
    || !Number.isSafeInteger(mensagem.revisao_selecao)
    || mensagem.revisao_selecao < 1
    || !camposExatos(mensagem, CAMPOS_POR_TIPO[mensagem.tipo])
  ) return false

  if (mensagem.tipo === 'simulacao_selecionada') {
    return idValido(mensagem.simulacao_id) && textoValido(mensagem.selecao_id)
  }
  if (mensagem.tipo === 'estado_alterado') {
    return idValido(mensagem.simulacao_id)
      && textoValido(mensagem.selecao_id)
      && ESTADOS_EXECUCAO.has(mensagem.estado_execucao)
  }

  return idValido(mensagem.simulacao_anterior_id)
    && textoValido(mensagem.selecao_anterior_id)
}

function criarId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function criarIdentificadorSelecao() {
  return criarId()
}

function comparacaoSelecao(a, b) {
  if (!b) return 1
  if (a.revisao_selecao !== b.revisao_selecao) {
    return a.revisao_selecao > b.revisao_selecao ? 1 : -1
  }
  if (a.origem === b.origem) return 0
  return a.origem > b.origem ? 1 : -1
}

/** Canal entre abas com ordenação Lamport e desempate estável por origem. */
export function criarSincronizadorAbasSimulacao({
  aoReceber,
  BroadcastChannelConstructor,
  windowTarget,
  storageTarget,
  relogio = Date.now,
  origem = criarId(),
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
  let revisaoSelecao = 0
  let fechado = false
  let canal = null
  let selecaoVencedora = null
  const sequenciasRecebidas = new Map()
  const revisoesPublicadasPorToken = new Map()

  function lerRevisaoPersistida() {
    try {
      if (typeof armazenamento?.getItem !== 'function') return null
      const armazenada = armazenamento.getItem(CHAVE_REVISAO_SELECAO)
      if (armazenada === null) return 0
      const valor = Number(armazenada)
      return Number.isSafeInteger(valor) && valor >= 0 ? valor : 0
    } catch {
      return null
    }
  }

  function persistirRevisao(valor) {
    try {
      armazenamento?.setItem(CHAVE_REVISAO_SELECAO, String(valor))
    } catch {
      // A ordenação entre abas continua funcionando por mensagens recebidas.
    }
  }

  function proximaRevisao() {
    const proxima = Math.max(
      revisaoSelecao,
      lerRevisaoPersistida() ?? 0,
      relogio(),
    ) + 1
    if (!Number.isSafeInteger(proxima)) return null
    revisaoSelecao = proxima
    persistirRevisao(proxima)
    return proxima
  }

  revisaoSelecao = lerRevisaoPersistida() ?? relogio()

  function entregar(mensagem) {
    if (fechado || !mensagemSimulacaoValida(mensagem)) return
    const ultimaSequencia = sequenciasRecebidas.get(mensagem.origem) ?? 0
    if (mensagem.sequencia <= ultimaSequencia) return
    sequenciasRecebidas.set(mensagem.origem, mensagem.sequencia)

    if (mensagem.tipo === 'estado_alterado') {
      const mesmaSelecao = selecaoVencedora !== null
        && selecaoVencedora.tipo === 'simulacao_selecionada'
        && selecaoVencedora.origem === mensagem.origem
        && selecaoVencedora.revisao_selecao === mensagem.revisao_selecao
        && selecaoVencedora.selecao_id === mensagem.selecao_id
        && selecaoVencedora.simulacao_id === mensagem.simulacao_id

      if (mesmaSelecao) aoReceber?.(mensagem)
      return
    }

    if (mensagem.revisao_selecao > revisaoSelecao) {
      revisaoSelecao = mensagem.revisao_selecao
      persistirRevisao(revisaoSelecao)
    }
    if (comparacaoSelecao(mensagem, selecaoVencedora) <= 0) return
    selecaoVencedora = mensagem
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

  function novaMensagem(tipo, especificos) {
    return {
      aplicacao: 'ponto-a-ponto',
      versao: VERSAO_MENSAGENS_SIMULACAO,
      origem,
      sequencia: sequencia + 1,
      tipo,
      ...especificos,
    }
  }

  function enviar(mensagem) {
    if (!mensagemSimulacaoValida(mensagem)) return false
    sequencia = mensagem.sequencia
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
  }

  return {
    publicar(opcoes = {}) {
      const { tipo, simulacaoId, simulacaoAnteriorId, selecaoId, estadoExecucao } = opcoes
      if (fechado || !Object.hasOwn(CAMPOS_POR_TIPO, tipo)) return false
      const opcoesPermitidas = new Set(OPCOES_PUBLICACAO_POR_TIPO[tipo])
      if (Object.keys(opcoes).some((campo) => !opcoesPermitidas.has(campo))) {
        return false
      }
      if ([...opcoesPermitidas].some((campo) => !Object.hasOwn(opcoes, campo))) {
        return false
      }
      let mensagem

      if (tipo === 'simulacao_selecionada') {
        if (!idValido(simulacaoId) || !textoValido(selecaoId)) return false
        const revisao = proximaRevisao()
        if (revisao === null) return false
        mensagem = novaMensagem(tipo, {
          simulacao_id: simulacaoId,
          selecao_id: selecaoId,
          revisao_selecao: revisao,
        })
        if (!enviar(mensagem)) return false
        revisoesPublicadasPorToken.clear()
        revisoesPublicadasPorToken.set(selecaoId, revisao)
        selecaoVencedora = mensagem
        return true
      }

      if (tipo === 'estado_alterado') {
        if (!idValido(simulacaoId) || !textoValido(selecaoId)
          || !ESTADOS_EXECUCAO.has(estadoExecucao)) return false
        const revisao = revisoesPublicadasPorToken.get(selecaoId)
        if (!revisao) return false
        if (selecaoVencedora && (
          selecaoVencedora.tipo !== 'simulacao_selecionada'
          || selecaoVencedora.origem !== origem
          || selecaoVencedora.revisao_selecao !== revisao
          || selecaoVencedora.selecao_id !== selecaoId
          || selecaoVencedora.simulacao_id !== simulacaoId
        )) return false
        mensagem = novaMensagem(tipo, {
          simulacao_id: simulacaoId,
          selecao_id: selecaoId,
          revisao_selecao: revisao,
          estado_execucao: estadoExecucao,
        })
        return enviar(mensagem)
      }

      if (!idValido(simulacaoAnteriorId) || !textoValido(selecaoId)) return false
      const revisao = proximaRevisao()
      if (revisao === null) return false
      mensagem = novaMensagem(tipo, {
        simulacao_anterior_id: simulacaoAnteriorId,
        selecao_anterior_id: selecaoId,
        revisao_selecao: revisao,
      })
      if (!enviar(mensagem)) return false
      revisoesPublicadasPorToken.delete(selecaoId)
      selecaoVencedora = mensagem
      return true
    },
    fechar() {
      if (fechado) return
      fechado = true
      canal?.close?.()
      if (!canal) alvoJanela?.removeEventListener('storage', aoMensagemStorage)
    },
  }
}
