import { useEffect, useRef, useState } from 'react'

import MapaRotas from '../MapaRotas/MapaRotas.jsx'
import {
  buscarParametrosSimulacao,
  buscarRotas,
  buscarSimulacao,
} from '../../services/api.js'
import { INTERVALO_ATUALIZACAO_SIMULACAO_MS } from '../../utils/pollingSimulacao.js'
import {
  atualizarUrlAcompanhamentoRotas,
  obterIdSimulacaoDaBusca,
} from '../../utils/rotasUrl.js'
import {
  EVENTO_SELECAO_SIMULACAO,
  criarSincronizadorAbasSimulacao,
} from '../../utils/sincronizacaoAbasSimulacao.js'
import './AcompanhamentoRotas.css'

const ROTULOS_ESTADO = {
  aguardando: 'Aguardando',
  executando: 'Executando',
  pausada: 'Pausada',
  concluida: 'Concluída',
  falhou: 'Falhou',
}

function AcompanhamentoRotas() {
  const [idSimulacao, setIdSimulacao] = useState(
    () => obterIdSimulacaoDaBusca(window.location.search),
  )
  const idSimulacaoRef = useRef(idSimulacao)
  const selecaoAtualRef = useRef(null)
  const solicitarConsultaRef = useRef(null)
  const [simulacao, setSimulacao] = useState(null)
  const [rotas, setRotas] = useState(null)
  const [snapshotPedidos, setSnapshotPedidos] = useState(null)
  const [snapshotCarregando, setSnapshotCarregando] = useState(Boolean(idSimulacao))
  const [estadoAutoritativo, setEstadoAutoritativo] = useState(true)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(Boolean(idSimulacao))

  useEffect(() => {
    const limparDados = (aguardandoSimulacao = true) => {
      setSimulacao(null)
      setRotas(null)
      setSnapshotPedidos(null)
      setSnapshotCarregando(aguardandoSimulacao)
      setEstadoAutoritativo(true)
      setErro('')
      setCarregando(aguardandoSimulacao)
    }

    // A query inicial define o primeiro estado. Depois da inscrição, uma nova
    // seleção válida do painel prevalece; uma navegação explícita do navegador
    // ou via atualizarUrlAcompanhamentoRotas volta a controlar a página.
    const aplicarIdDaUrl = (busca) => {
      const novoId = obterIdSimulacaoDaBusca(busca)
      const idAtual = idSimulacaoRef.current
      selecaoAtualRef.current = null
      if (novoId === idAtual) {
        solicitarConsultaRef.current?.()
        return
      }
      idSimulacaoRef.current = novoId
      setIdSimulacao(novoId)
      limparDados(Boolean(novoId))
    }

    const aoPopstate = () => aplicarIdDaUrl(window.location.search)
    const aoAlterarUrlProgramaticamente = (evento) => {
      aplicarIdDaUrl(evento.detail?.search ?? window.location.search)
    }

    const sincronizador = criarSincronizadorAbasSimulacao({
      aoReceber: (mensagem) => {
        if (mensagem.tipo === 'simulacao_limpa') {
          selecaoAtualRef.current = null
          idSimulacaoRef.current = null
          setIdSimulacao(null)
          atualizarUrlAcompanhamentoRotas(null, window, { notificar: false })
          limparDados(false)
          return
        }

        if (mensagem.tipo === 'simulacao_selecionada') {
          const idAtual = idSimulacaoRef.current
          const selecaoAnterior = selecaoAtualRef.current
          const mudouSelecao = selecaoAnterior !== mensagem.selecao_id
          selecaoAtualRef.current = mensagem.selecao_id
          if (idAtual !== mensagem.simulacao_id) {
            idSimulacaoRef.current = mensagem.simulacao_id
            setIdSimulacao(mensagem.simulacao_id)
            limparDados()
          } else if (mudouSelecao) {
            solicitarConsultaRef.current?.()
          }
          atualizarUrlAcompanhamentoRotas(
            mensagem.simulacao_id,
            window,
            { notificar: false },
          )
          return
        }

        // Estado, relógio e rotas continuam vindo da API. A mensagem só
        // antecipa a consulta da seleção que continua sendo acompanhada.
        if (mensagem.simulacao_id === idSimulacaoRef.current) {
          solicitarConsultaRef.current?.()
        }
      },
    })

    window.addEventListener('popstate', aoPopstate)
    window.addEventListener(EVENTO_SELECAO_SIMULACAO, aoAlterarUrlProgramaticamente)

    return () => {
      sincronizador.fechar()
      window.removeEventListener('popstate', aoPopstate)
      window.removeEventListener(EVENTO_SELECAO_SIMULACAO, aoAlterarUrlProgramaticamente)
    }
  }, [])

  useEffect(() => {
    if (!idSimulacao) {
      solicitarConsultaRef.current = null
      return undefined
    }

    let desmontado = false
    let temporizador
    let consultaAtual
    let terminal = false
    let consultaEmAndamento = false
    let consultaPendente = false

    async function consultar() {
      if (desmontado || terminal) return
      if (consultaEmAndamento) {
        consultaPendente = true
        return
      }

      consultaEmAndamento = true
      consultaAtual = new AbortController()

      try {
        const estado = await buscarSimulacao(idSimulacao, {
          signal: consultaAtual.signal,
        })
        let rotasAtuais = null

        if (estado.iniciada) {
          try {
            rotasAtuais = await buscarRotas(idSimulacao, {
              signal: consultaAtual.signal,
            })
          } catch (erroRotas) {
            // 409 é esperado enquanto o planejamento ainda não disponibilizou
            // as rotas. O próximo polling tenta novamente.
            if (!erroRotas.message.includes('HTTP 409')) throw erroRotas
          }
        }

        if (!desmontado && idSimulacaoRef.current === idSimulacao) {
          setSimulacao(estado)
          setRotas(rotasAtuais)
          setEstadoAutoritativo(true)
          setErro('')
          setCarregando(false)
        }
        if (idSimulacaoRef.current !== idSimulacao) return
        terminal = estado.estado_execucao === 'concluida' || estado.concluida
      } catch (erroConsulta) {
        if (
          desmontado
          || idSimulacaoRef.current !== idSimulacao
          || erroConsulta.name === 'AbortError'
        ) {
          consultaEmAndamento = false
          return
        }
        setErro(erroConsulta.message)
        setCarregando(false)
        terminal = erroConsulta.message.includes('HTTP 404')
          || erroConsulta.message.includes('HTTP 410')
        if (terminal) setEstadoAutoritativo(false)
      } finally {
        consultaEmAndamento = false
      }

      if (desmontado || idSimulacaoRef.current !== idSimulacao || terminal) return
      if (consultaPendente) {
        consultaPendente = false
        temporizador = window.setTimeout(consultar, 0)
      } else {
        temporizador = window.setTimeout(consultar, INTERVALO_ATUALIZACAO_SIMULACAO_MS)
      }
    }

    function solicitarConsultaImediata() {
      if (desmontado || terminal) return
      window.clearTimeout(temporizador)
      if (consultaEmAndamento) {
        consultaPendente = true
        return
      }
      consultar()
    }

    solicitarConsultaRef.current = solicitarConsultaImediata
    consultar()
    return () => {
      desmontado = true
      window.clearTimeout(temporizador)
      consultaAtual?.abort()
      if (solicitarConsultaRef.current === solicitarConsultaImediata) {
        solicitarConsultaRef.current = null
      }
    }
  }, [idSimulacao])

  useEffect(() => {
    if (!idSimulacao) return undefined

    let desmontado = false
    const consulta = new AbortController()
    buscarParametrosSimulacao(idSimulacao, { signal: consulta.signal })
      .then((auditoria) => {
        if (desmontado || idSimulacaoRef.current !== idSimulacao) return
        const pedidos = auditoria.disponivel
          ? auditoria.snapshot_pedidos?.dados?.pedidos
          : null
        setSnapshotPedidos(Array.isArray(pedidos) ? pedidos : null)
      })
      .catch((erroParametros) => {
        if (
          !desmontado
          && idSimulacaoRef.current === idSimulacao
          && erroParametros.name !== 'AbortError'
        ) {
          setSnapshotPedidos(null)
        }
      })
      .finally(() => {
        if (!desmontado && idSimulacaoRef.current === idSimulacao) {
          setSnapshotCarregando(false)
        }
      })

    return () => {
      desmontado = true
      consulta.abort()
    }
  }, [idSimulacao])

  const entregadores = simulacao?.entregadores ?? []
  const entregadoresAtivos = entregadores.filter(
    (entregador) => entregador.situacao === 'em_viagem',
  ).length
  const estado = simulacao
    ? ROTULOS_ESTADO[simulacao.estado_execucao] ?? simulacao.estado_execucao
    : carregando
      ? 'Carregando'
      : 'Não disponível'

  return (
    <main className="pagina-acompanhamento-rotas">
      <header className="pagina-acompanhamento-rotas__cabecalho">
        <div>
          <p className="pagina-acompanhamento-rotas__sobretitulo">Ponto a Ponto</p>
          <h1>Acompanhamento de Rotas</h1>
          <p>
            {idSimulacao
              ? `Simulação #${idSimulacao} · ${estado}`
              : 'Nenhuma simulação foi selecionada para acompanhamento.'}
          </p>
        </div>
        <a className="pagina-acompanhamento-rotas__voltar" href="/">
          Voltar ao painel principal
        </a>
      </header>

      {idSimulacao && (
        <section className="pagina-acompanhamento-rotas__resumo" aria-label="Resumo da operação">
          <div>
            <span>Simulação</span>
            <strong>#{idSimulacao}</strong>
          </div>
          <div>
            <span>Estado</span>
            <strong>{estado}</strong>
          </div>
          <div>
            <span>Entregadores configurados</span>
            <strong>{entregadores.length}</strong>
          </div>
          <div>
            <span>Em viagem</span>
            <strong>{entregadoresAtivos}</strong>
          </div>
        </section>
      )}

      {erro && <p className="pagina-acompanhamento-rotas__erro" role="alert">{erro}</p>}

      {!idSimulacao ? (
        <p className="pagina-acompanhamento-rotas__mensagem">
          Abra Rotas pelo painel principal após criar uma simulação para acompanhar seu estado.
        </p>
      ) : (
        <>
          {!estadoAutoritativo && (
            <p className="pagina-acompanhamento-rotas__mensagem" role="status">
              Estado não disponível na API. A animação foi congelada no último estado recebido.
            </p>
          )}
          {simulacao && !simulacao.iniciada && (
            <p className="pagina-acompanhamento-rotas__mensagem" role="status">
              As rotas aparecerão aqui quando o planejamento começar.
            </p>
          )}
          <MapaRotas
            rotas={rotas}
            simulacao={simulacao}
            snapshotPedidos={snapshotPedidos}
            snapshotPedidosCarregando={snapshotCarregando}
            estadoAutoritativo={estadoAutoritativo}
          />
        </>
      )}
    </main>
  )
}

export default AcompanhamentoRotas
