const VELOCIDADES_PERMITIDAS = new Set([5, 15, 30, 60])
const RAIO_TERRA_M = 6_371_000

export const FASES_ENTREGADOR = Object.freeze({
  AGUARDANDO_PARTIDA: 'aguardando_partida_no_centro',
  DESLOCANDO_PARA_PARADA: 'em_deslocamento_para_parada',
  ATENDENDO_PARADA: 'parado_durante_atendimento',
  DESLOCANDO_PARA_PROXIMA: 'em_deslocamento_para_proxima_parada',
  RETORNANDO_AO_CENTRO: 'retornando_ao_centro',
  VIAGEM_CONCLUIDA: 'viagem_concluida_no_centro',
  VIAGEM_CANCELADA: 'viagem_cancelada_sem_movimentacao',
})

function instanteMs(valor) {
  if (typeof valor !== 'string' && !(valor instanceof Date)) return null
  if (
    typeof valor === 'string'
    && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(valor)
  ) return null
  const instante = new Date(valor).getTime()
  return Number.isFinite(instante) ? instante : null
}

function coordenadaValida(ponto) {
  return Array.isArray(ponto)
    && ponto.length >= 2
    && Number.isFinite(Number(ponto[0]))
    && Number.isFinite(Number(ponto[1]))
}

function distanciaMetros(a, b) {
  const rad = (graus) => (graus * Math.PI) / 180
  const latitudeA = rad(a[0])
  const latitudeB = rad(b[0])
  const deltaLatitude = latitudeB - latitudeA
  const deltaLongitude = rad(b[1] - a[1])
  const haversine = Math.sin(deltaLatitude / 2) ** 2
    + Math.cos(latitudeA) * Math.cos(latitudeB)
      * Math.sin(deltaLongitude / 2) ** 2

  return 2 * RAIO_TERRA_M * Math.asin(Math.sqrt(Math.min(1, haversine)))
}

function projetarEmSegmento(ponto, inicio, fim) {
  // Projeção local equiretangular para escolher o ponto mais próximo da
  // polyline. As distâncias percorridas continuam sendo medidas em metros.
  const latitudeMedia = ((inicio[0] + fim[0] + ponto[0]) / 3) * Math.PI / 180
  const escalaX = Math.cos(latitudeMedia)
  const vetor = [
    (fim[1] - inicio[1]) * escalaX,
    fim[0] - inicio[0],
  ]
  const relativo = [
    (ponto[1] - inicio[1]) * escalaX,
    ponto[0] - inicio[0],
  ]
  const comprimento2 = vetor[0] ** 2 + vetor[1] ** 2
  const fracao = comprimento2 === 0
    ? 0
    : Math.max(0, Math.min(1, (relativo[0] * vetor[0] + relativo[1] * vetor[1]) / comprimento2))
  const coordenada = [
    inicio[0] + (fim[0] - inicio[0]) * fracao,
    inicio[1] + (fim[1] - inicio[1]) * fracao,
  ]

  return {
    fracao,
    coordenada,
    distancia: distanciaMetros(ponto, coordenada),
  }
}

function prepararGeometria(viagem) {
  const caminho = (viagem.caminho ?? [])
    .filter(coordenadaValida)
    .map((ponto) => [Number(ponto[0]), Number(ponto[1])])
  if (caminho.length < 2) return null

  const comprimentos = []
  const acumuladas = [0]
  for (let indice = 0; indice < caminho.length - 1; indice += 1) {
    const comprimento = distanciaMetros(caminho[indice], caminho[indice + 1])
    comprimentos.push(comprimento)
    acumuladas.push(acumuladas.at(-1) + comprimento)
  }

  const total = acumuladas.at(-1)
  if (!Number.isFinite(total) || total === 0) {
    return { caminho, comprimentos, acumuladas, total: 0, paradas: [] }
  }

  let indiceMinimo = 0
  let distanciaAnterior = 0
  let coordenadaAnterior = caminho[0]
  const paradas = []

  for (const parada of viagem.paradas ?? []) {
    const alvo = [Number(parada.latitude), Number(parada.longitude)]
    const repetida = coordenadaAnterior
      && Math.abs(alvo[0] - coordenadaAnterior[0]) < 1e-10
      && Math.abs(alvo[1] - coordenadaAnterior[1]) < 1e-10

    if (repetida && paradas.length > 0) {
      paradas.push({ distancia: distanciaAnterior, coordenada: alvo })
      continue
    }

    let melhor = null
    for (let indice = indiceMinimo; indice < caminho.length - 1; indice += 1) {
      const projecao = projetarEmSegmento(alvo, caminho[indice], caminho[indice + 1])
      const distancia = acumuladas[indice] + comprimentos[indice] * projecao.fracao
      if (distancia + 1e-6 < distanciaAnterior) continue

      if (
        melhor === null
        || projecao.distancia < melhor.erro - 1e-6
        || (Math.abs(projecao.distancia - melhor.erro) <= 1e-6 && distancia < melhor.distancia)
      ) {
        melhor = {
          erro: projecao.distancia,
          distancia,
          coordenada: projecao.coordenada,
          indice,
        }
      }
    }

    if (melhor) {
      indiceMinimo = melhor.indice
      distanciaAnterior = melhor.distancia
      coordenadaAnterior = alvo
      paradas.push({ distancia: melhor.distancia, coordenada: alvo })
    } else {
      // A API pode retornar uma polyline que não passe exatamente sobre a
      // coordenada de um waypoint. Nesse caso, mantemos a ordem sem inventar
      // um ponto fora da geometria durante o deslocamento.
      paradas.push({ distancia: distanciaAnterior, coordenada: alvo })
    }
  }

  return { caminho, comprimentos, acumuladas, total, paradas }
}

function pontoNaDistancia(geometria, distancia) {
  if (!geometria || geometria.caminho.length === 0) return null
  if (geometria.total === 0) return geometria.caminho[0]

  const alvo = Math.max(0, Math.min(geometria.total, distancia))
  for (let indice = 0; indice < geometria.comprimentos.length; indice += 1) {
    const comprimento = geometria.comprimentos[indice]
    const inicioDistancia = geometria.acumuladas[indice]
    const fimDistancia = geometria.acumuladas[indice + 1]
    if (alvo <= fimDistancia || indice === geometria.comprimentos.length - 1) {
      const fracao = comprimento === 0
        ? 0
        : Math.max(0, Math.min(1, (alvo - inicioDistancia) / comprimento))
      const inicio = geometria.caminho[indice]
      const fim = geometria.caminho[indice + 1]
      return [
        inicio[0] + (fim[0] - inicio[0]) * fracao,
        inicio[1] + (fim[1] - inicio[1]) * fracao,
      ]
    }
  }

  return geometria.caminho.at(-1)
}

function interpolar(geometria, distanciaInicio, distanciaFim, tempo, tempoInicio, tempoFim) {
  const fracao = tempoFim <= tempoInicio
    ? 1
    : Math.max(0, Math.min(1, (tempo - tempoInicio) / (tempoFim - tempoInicio)))
  return pontoNaDistancia(
    geometria,
    distanciaInicio + (distanciaFim - distanciaInicio) * fracao,
  )
}

function resultado(entregadorCodigo, viagem, fase, coordenada, pedido = null, emDeslocamento = false) {
  return {
    entregador_codigo: entregadorCodigo,
    viagem: viagem ?? null,
    fase,
    coordenada,
    pedido,
    em_deslocamento: emDeslocamento,
    parado: !emDeslocamento,
  }
}

function faseDaViagem(viagem, agora, centro, fimExpediente) {
  const partida = instanteMs(viagem.partida_em)
  const retorno = instanteMs(viagem.retorno_em)
  if (partida === null || retorno === null) return null

  const paradas = viagem.paradas ?? []
  const chegadas = paradas.map((parada) => instanteMs(parada.chegada_em))
  const saidas = paradas.map((parada) => instanteMs(parada.saida_em))
  if (chegadas.some((valor) => valor === null) || saidas.some((valor) => valor === null)) return null

  const caminho = prepararGeometria(viagem)
  if (!caminho) {
    return resultado(
      null,
      viagem,
      FASES_ENTREGADOR.DESLOCANDO_PARA_PARADA,
      null,
      paradas[0] ?? null,
      true,
    )
  }

  if (viagem.situacao === 'cancelada') {
    return resultado(null, viagem, FASES_ENTREGADOR.VIAGEM_CANCELADA, centro)
  }

  const partidaForaExpediente = fimExpediente !== null && partida > fimExpediente
  if (partidaForaExpediente) {
    return resultado(null, viagem, FASES_ENTREGADOR.AGUARDANDO_PARTIDA, centro)
  }

  if (agora < partida) {
    return resultado(null, viagem, FASES_ENTREGADOR.AGUARDANDO_PARTIDA, centro)
  }

  const ancoraParadas = caminho.paradas
  for (let indice = 0; indice < paradas.length; indice += 1) {
    const parada = paradas[indice]
    const chegada = chegadas[indice]
    const saida = saidas[indice]
    const distanciaOrigem = indice === 0 ? 0 : ancoraParadas[indice - 1]?.distancia ?? 0
    const distanciaDestino = ancoraParadas[indice]?.distancia ?? distanciaOrigem
    const tempoOrigem = indice === 0 ? partida : saidas[indice - 1]

    if (agora < chegada) {
      return resultado(
        null,
        viagem,
        indice === 0
          ? FASES_ENTREGADOR.DESLOCANDO_PARA_PARADA
          : FASES_ENTREGADOR.DESLOCANDO_PARA_PROXIMA,
        interpolar(caminho, distanciaOrigem, distanciaDestino, agora, tempoOrigem, chegada),
        parada,
        true,
      )
    }

    if (agora < saida) {
      return resultado(
        null,
        viagem,
        FASES_ENTREGADOR.ATENDENDO_PARADA,
        [Number(parada.latitude), Number(parada.longitude)],
        parada,
      )
    }
  }

  if (agora < retorno) {
    const ultimaDistancia = ancoraParadas.at(-1)?.distancia ?? 0
    const inicioRetorno = paradas.length > 0 ? saidas.at(-1) : partida
    return resultado(
      null,
      viagem,
      FASES_ENTREGADOR.RETORNANDO_AO_CENTRO,
      interpolar(caminho, ultimaDistancia, caminho.total, agora, inicioRetorno, retorno),
      null,
      true,
    )
  }

  return resultado(null, viagem, FASES_ENTREGADOR.VIAGEM_CONCLUIDA, centro)
}

/**
 * Calcula, sem efeitos colaterais, a posição visual de cada entregador.
 * `tempoRealDecorridoMs` é um delta monotônico fornecido pelo chamador
 * (por exemplo, entre frames de requestAnimationFrame); o delta deve ser
 * reiniciado a cada nova amostra de `agora`. Nunca se consulta o relógio
 * civil do computador. O estado e `simulacao.agora` são a âncora.
 */
export function calcularPosicoesEntregadores(
  simulacao,
  rotas,
  {
    segundosReaisPorHoraSimulada = simulacao?.segundos_reais_por_hora_simulada ?? 15,
    tempoRealDecorridoMs = 0,
  } = {},
) {
  const agoraBase = instanteMs(simulacao?.agora)
  const centro = rotas?.centro
    && Number.isFinite(Number(rotas.centro.latitude))
    && Number.isFinite(Number(rotas.centro.longitude))
    ? [Number(rotas.centro.latitude), Number(rotas.centro.longitude)]
    : null
  if (agoraBase === null || !Array.isArray(rotas?.rotas)) return []

  if (!VELOCIDADES_PERMITIDAS.has(Number(segundosReaisPorHoraSimulada))) {
    throw new RangeError('Velocidade deve ser 5, 15, 30 ou 60 segundos por hora simulada.')
  }
  if (!Number.isFinite(tempoRealDecorridoMs) || tempoRealDecorridoMs < 0) {
    throw new RangeError('O tempo real decorrido deve ser um número não negativo.')
  }

  const executando = simulacao.estado_execucao === 'executando'
  const agora = agoraBase + (executando
    ? tempoRealDecorridoMs * 3600 / Number(segundosReaisPorHoraSimulada)
    : 0)
  const fimExpediente = instanteMs(simulacao.fim_expediente)
  const concluida = simulacao.estado_execucao === 'concluida' || simulacao.concluida === true
  const aguardandoInicio = simulacao.iniciada === false

  return rotas.rotas.map((rota) => {
    const viagens = [...(rota.viagens ?? [])].sort((a, b) => (
      (instanteMs(a.partida_em) ?? 0) - (instanteMs(b.partida_em) ?? 0)
      || Number(a.numero) - Number(b.numero)
    ))
    const ultimaViagem = viagens.at(-1) ?? null

    if (aguardandoInicio) {
      return resultado(
        rota.entregador_codigo,
        viagens[0] ?? null,
        FASES_ENTREGADOR.AGUARDANDO_PARTIDA,
        centro,
      )
    }

    if (concluida) {
      const cancelada = [...viagens].reverse().find((viagem) => viagem.situacao === 'cancelada')
      return resultado(
        rota.entregador_codigo,
        cancelada ?? ultimaViagem,
        cancelada
          ? FASES_ENTREGADOR.VIAGEM_CANCELADA
          : FASES_ENTREGADOR.VIAGEM_CONCLUIDA,
        centro,
      )
    }

    let ultimoConcluido = null
    for (const viagem of viagens) {
      const partida = instanteMs(viagem.partida_em)
      const retorno = instanteMs(viagem.retorno_em)
      if (partida === null || retorno === null) continue

      if (viagem.situacao === 'cancelada') {
        const cancelamento = fimExpediente ?? partida
        if (agora >= cancelamento) {
          ultimoConcluido = viagem
          continue
        }
        return resultado(
          rota.entregador_codigo,
          viagem,
          FASES_ENTREGADOR.AGUARDANDO_PARTIDA,
          centro,
        )
      }

      if (fimExpediente !== null && partida > fimExpediente) {
        if (agora >= fimExpediente) {
          return resultado(
            rota.entregador_codigo,
            viagem,
            FASES_ENTREGADOR.VIAGEM_CANCELADA,
            centro,
          )
        }
        return resultado(
          rota.entregador_codigo,
          viagem,
          FASES_ENTREGADOR.AGUARDANDO_PARTIDA,
          centro,
        )
      }

      if (agora < partida) {
        return resultado(
          rota.entregador_codigo,
          viagem,
          FASES_ENTREGADOR.AGUARDANDO_PARTIDA,
          centro,
        )
      }

      if (agora < retorno) {
        const movimento = faseDaViagem(viagem, agora, centro, fimExpediente)
        return movimento
          ? { ...movimento, entregador_codigo: rota.entregador_codigo }
          : resultado(rota.entregador_codigo, viagem, FASES_ENTREGADOR.AGUARDANDO_PARTIDA, centro)
      }

      ultimoConcluido = viagem
    }

    const ultimaCancelada = ultimoConcluido?.situacao === 'cancelada'
    return resultado(
      rota.entregador_codigo,
      ultimoConcluido ?? ultimaViagem,
      ultimaCancelada
        ? FASES_ENTREGADOR.VIAGEM_CANCELADA
        : viagens.length > 0
          ? FASES_ENTREGADOR.VIAGEM_CONCLUIDA
          : FASES_ENTREGADOR.AGUARDANDO_PARTIDA,
      centro,
    )
  })
}
