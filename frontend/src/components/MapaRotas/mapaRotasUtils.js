const PALETA_ENTREGADORES = [
  '#1769AA',
  '#C2410C',
  '#6B46A1',
  '#087F5B',
  '#B4235A',
  '#69512D',
  '#3657A6',
  '#A23B72',
  '#3F6B32',
  '#8C4A12',
]

export function obterCorEntregador(codigo) {
  const texto = String(codigo ?? '')
  let hash = 2166136261

  for (let indice = 0; indice < texto.length; indice += 1) {
    hash ^= texto.charCodeAt(indice)
    hash = Math.imul(hash, 16777619)
  }

  return PALETA_ENTREGADORES[(hash >>> 0) % PALETA_ENTREGADORES.length]
}

export function listarViagens(rotas) {
  return (rotas?.rotas ?? []).flatMap((rota) =>
    (rota.viagens ?? []).map((viagem) => ({
      entregadorCodigo: rota.entregador_codigo,
      viagem,
      cor: obterCorEntregador(rota.entregador_codigo),
    }))
  )
}

export function numeroMarcadorReferencia(codigo, ordem) {
  const sufixoNumerico = String(codigo ?? '').match(/(\d+)$/)?.[1]
  return sufixoNumerico === undefined ? String(ordem) : String(Number(sufixoNumerico))
}

export function sequenciasPedidosManuais(snapshotPedidos = []) {
  const manuais = (Array.isArray(snapshotPedidos) ? snapshotPedidos : [])
    .filter((pedido) => (
      pedido.origem === 'manual'
      && pedido.id !== null
      && pedido.id !== undefined
      && pedido.id !== ''
      && Number.isSafeInteger(Number(pedido.id))
    ))
    .slice()
    .sort((a, b) => Number(a.id) - Number(b.id))

  return new Map(manuais.map((pedido, indice) => [pedido.codigo, `M${indice + 1}`]))
}

export function deslocamentosVisuais(quantidade, espacamento = 40) {
  if (quantidade <= 1) return [[0, 0]]

  const colunas = Math.ceil(Math.sqrt(quantidade))
  const linhas = Math.ceil(quantidade / colunas)

  return Array.from({ length: quantidade }, (_, indice) => {
    const coluna = indice % colunas
    const linha = Math.floor(indice / colunas)
    return [
      (coluna - (colunas - 1) / 2) * espacamento,
      (linha - (linhas - 1) / 2) * espacamento,
    ]
  })
}

function compararParadasEstavelmente(a, b) {
  const idA = Number(a.snapshotId)
  const idB = Number(b.snapshotId)
  if (Number.isSafeInteger(idA) && Number.isSafeInteger(idB) && idA !== idB) {
    return idA - idB
  }

  const codigoA = String(a.pedido_codigo)
  const codigoB = String(b.pedido_codigo)
  if (codigoA !== codigoB) return codigoA < codigoB ? -1 : 1
  if (a.viagemNumero !== b.viagemNumero) return a.viagemNumero - b.viagemNumero
  return a.ordem - b.ordem
}

export function prepararMarcadores(rotas, snapshotPedidos = []) {
  const dadosSnapshot = Array.isArray(snapshotPedidos) ? snapshotPedidos : []
  const metadadosPorCodigo = new Map(
    dadosSnapshot.map((pedido) => [pedido.codigo, pedido])
  )
  const sequenciasManuais = sequenciasPedidosManuais(dadosSnapshot)
  const porCoordenada = new Map()

  for (const { entregadorCodigo, viagem, cor } of listarViagens(rotas)) {
    for (const parada of viagem.paradas ?? []) {
      const metadado = metadadosPorCodigo.get(parada.pedido_codigo)
      const origem = metadado?.origem ?? null
      const rotulo = origem === 'manual'
        ? sequenciasManuais.get(parada.pedido_codigo) ?? 'M?'
        : origem === 'referencia'
          ? numeroMarcadorReferencia(parada.pedido_codigo, parada.ordem)
          : String(parada.ordem)
      const coordenadas = [parada.latitude, parada.longitude]
      const chaveCoordenadas = JSON.stringify(coordenadas)
      const marcador = {
        ...parada,
        chave: `${chaveCoordenadas}:${entregadorCodigo}:${viagem.numero}:${parada.ordem}:${parada.pedido_codigo}`,
        position: coordenadas,
        rotulo,
        origem,
        idOrigem: origem === 'manual' ? rotulo : null,
        snapshotId: metadado?.id,
        entregadorCodigo,
        viagemNumero: viagem.numero,
        cor,
        deslocamento: [0, 0],
      }
      const grupo = porCoordenada.get(chaveCoordenadas) ?? []
      grupo.push(marcador)
      porCoordenada.set(chaveCoordenadas, grupo)
    }
  }

  return [...porCoordenada.values()].flatMap((grupo) => {
    grupo.sort(compararParadasEstavelmente)
    const deslocamentos = deslocamentosVisuais(grupo.length)
    return grupo.map((marcador, indice) => ({
      ...marcador,
      deslocamento: deslocamentos[indice],
    }))
  })
}

export function classeSituacaoViagem(situacao) {
  if (situacao === 'em_andamento') return 'em-andamento'
  if (situacao === 'concluida') return 'concluida'
  return 'outra'
}

export function textoSituacao(valor) {
  return String(valor ?? 'desconhecida').replaceAll('_', ' ')
}

export function coletarPontosEnquadramento(rotas) {
  const pontos = []

  if (rotas?.centro) {
    pontos.push([rotas.centro.latitude, rotas.centro.longitude])
  }

  for (const { viagem } of listarViagens(rotas)) {
    pontos.push(...(viagem.caminho ?? []))
    for (const parada of viagem.paradas ?? []) {
      pontos.push([parada.latitude, parada.longitude])
    }
  }

  return pontos
}

export function resumoEntregadores(rotas) {
  const codigos = new Set((rotas?.rotas ?? []).map((rota) => rota.entregador_codigo))
  return [...codigos].map((codigo) => ({
    codigo,
    cor: obterCorEntregador(codigo),
  }))
}
