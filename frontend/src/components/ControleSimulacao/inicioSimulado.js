const FUSO_SIMULACAO = 'America/Bahia'

function componentesEmSalvador(instante) {
  const partes = new Intl.DateTimeFormat('en-CA', {
    timeZone: FUSO_SIMULACAO,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(instante)

  return Object.fromEntries(partes.map(({ type, value }) => [type, value]))
}

function chaveData({ year, month, day }) {
  return `${year}-${month}-${day}`
}

function diaDaSemana(data) {
  return new Date(`${data}T12:00:00Z`).getUTCDay()
}

function proximoDiaUtil(data) {
  const diaSeguinte = new Date(`${data}T12:00:00Z`)
  diaSeguinte.setUTCDate(diaSeguinte.getUTCDate() + 1)

  let candidato = diaSeguinte.toISOString().slice(0, 10)
  while ([0, 6].includes(diaDaSemana(candidato))) {
    diaSeguinte.setUTCDate(diaSeguinte.getUTCDate() + 1)
    candidato = diaSeguinte.toISOString().slice(0, 10)
  }

  return candidato
}

function localBahia(instante) {
  const partes = componentesEmSalvador(instante)
  return `${chaveData(partes)}T${partes.hour}:${partes.minute}:${partes.second}`
}

export function obterPedidoMaisRecenteLocal(pedidos) {
  const instantes = pedidos
    .map((pedido) => Date.parse(pedido.criado_em))
    .filter(Number.isFinite)

  if (!instantes.length) return null
  return localBahia(new Date(Math.max(...instantes)))
}

export function sugerirInicioSimulado(pedidos, agora = new Date()) {
  const maisRecente = obterPedidoMaisRecenteLocal(pedidos)
  const partes = maisRecente
    ? {
        year: maisRecente.slice(0, 4),
        month: maisRecente.slice(5, 7),
        day: maisRecente.slice(8, 10),
        hour: maisRecente.slice(11, 13)
      }
    : componentesEmSalvador(agora)
  let data = chaveData(partes)

  if ([0, 6].includes(diaDaSemana(data)) || partes.hour >= '10') {
    data = proximoDiaUtil(data)
  }

  return { data, hora: '10:00' }
}

export function validarInicioSimulado(data, hora) {
  if (!data || !hora) return 'Informe a data e o horário de início.'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data) || !/^\d{2}:\d{2}$/.test(hora)) {
    return 'Informe uma data e um horário válidos.'
  }

  const dataConvertida = new Date(`${data}T12:00:00Z`)
  if (dataConvertida.toISOString().slice(0, 10) !== data) {
    return 'Informe uma data válida.'
  }
  if ([0, 6].includes(dataConvertida.getUTCDay())) {
    return 'A simulação deve iniciar em um dia útil.'
  }
  if (hora < '09:00' || hora >= '17:00') {
    return 'Escolha um horário entre 09:00 e antes das 17:00.'
  }

  return ''
}

export function criarInicioApi(data, hora) {
  return `${data}T${hora}:00`
}

export function existemPedidosPosteriores(pedidos, data, hora) {
  const maisRecente = obterPedidoMaisRecenteLocal(pedidos)
  if (!maisRecente || !data || !hora) return false
  return maisRecente > `${data}T${hora}:00`
}
