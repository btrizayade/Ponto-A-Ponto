import { useEffect, useRef, useState } from 'react'
import { Marker, Popup } from 'react-leaflet'

import { obterCorEntregador } from './mapaRotasUtils.js'
import { obterIconeVeiculo } from './iconesMapa.js'
import { calcularPosicoesEntregadores } from './movimentacaoEntregadores.js'
import { criarLoopAnimacao } from './loopAnimacao.js'

function mesmaPosicao(a, b) {
  if (a.length !== b.length) return false
  return a.every((item, indice) => (
    item.entregador_codigo === b[indice].entregador_codigo
    && item.viagem?.numero === b[indice].viagem?.numero
    && item.fase === b[indice].fase
    && item.pedido?.pedido_codigo === b[indice].pedido?.pedido_codigo
    && (
      item.coordenada === null && b[indice].coordenada === null
      || item.coordenada && b[indice].coordenada
        && Math.abs(item.coordenada[0] - b[indice].coordenada[0]) < 1e-8
        && Math.abs(item.coordenada[1] - b[indice].coordenada[1]) < 1e-8
    )
  ))
}

function textoFase(fase) {
  return String(fase ?? 'situação indisponível').replaceAll('_', ' ')
}

function calcular(simulacao, rotas, ancora, timestamp) {
  if (!simulacao || !rotas) return []
  const delta = simulacao.estado_execucao === 'executando' && ancora
    ? Math.max(0, timestamp - ancora.recebidaEm)
    : 0

  return calcularPosicoesEntregadores(simulacao, rotas, {
    segundosReaisPorHoraSimulada: simulacao.segundos_reais_por_hora_simulada,
    tempoRealDecorridoMs: delta,
  })
}

function VeiculosAnimados({ simulacao, rotas, estadoAutoritativo = true }) {
  const [posicoes, setPosicoes] = useState([])
  const entradaAtual = useRef({ simulacao, rotas })
  const ancoraRelogio = useRef(null)

  useEffect(() => {
    entradaAtual.current = { simulacao, rotas }
  }, [simulacao, rotas])

  useEffect(() => {
    if (!estadoAutoritativo) return

    const atual = entradaAtual.current.simulacao
    ancoraRelogio.current = atual
      ? { id: atual.id, agora: atual.agora, recebidaEm: performance.now() }
      : null

    const calculadas = calcular(
      atual,
      entradaAtual.current.rotas,
      ancoraRelogio.current,
      ancoraRelogio.current?.recebidaEm ?? 0,
    )
    setPosicoes((anteriores) => mesmaPosicao(anteriores, calculadas) ? anteriores : calculadas)
  }, [
    simulacao?.id,
    simulacao?.agora,
    simulacao?.estado_execucao,
    simulacao?.segundos_reais_por_hora_simulada,
    simulacao?.iniciada,
    simulacao?.concluida,
    rotas,
    estadoAutoritativo,
  ])

  useEffect(() => {
    if (!estadoAutoritativo || simulacao?.estado_execucao !== 'executando') return undefined

    const loop = criarLoopAnimacao({
      agendarFrame: (callback) => window.requestAnimationFrame(callback),
      cancelarFrame: (id) => window.cancelAnimationFrame(id),
      aoFrame: (timestamp) => {
        const atual = entradaAtual.current
        const ancora = ancoraRelogio.current
        const calculadas = calcular(atual.simulacao, atual.rotas, ancora, timestamp)
        setPosicoes((anteriores) => mesmaPosicao(anteriores, calculadas) ? anteriores : calculadas)
      },
    })

    loop.iniciar()
    return () => loop.parar()
  }, [simulacao?.id, simulacao?.estado_execucao, estadoAutoritativo])

  return posicoes
    .filter((posicao) => posicao.viagem && posicao.coordenada)
    .map((posicao) => {
      const codigo = posicao.entregador_codigo
      const cor = obterCorEntregador(codigo)
      const parada = posicao.pedido
      const chave = `${codigo}-${posicao.viagem.numero}`
      const fase = textoFase(posicao.fase)

      return (
        <Marker
          key={chave}
          position={posicao.coordenada}
          icon={obterIconeVeiculo(cor)}
          title={`${codigo}, viagem ${posicao.viagem.numero}: ${fase}`}
          zIndexOffset={1000}
          keyboard
        >
          <Popup>
            <strong>{codigo} — Viagem {posicao.viagem.numero}</strong>
            <br />
            Situação: {fase}
            {parada && (
              <>
                <br />
                Pedido relacionado: {parada.pedido_codigo}
              </>
            )}
          </Popup>
        </Marker>
      )
    })
}

export default VeiculosAnimados
