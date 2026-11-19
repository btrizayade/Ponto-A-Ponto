import { useEffect, useRef, useState } from 'react'

import MapaRotas from '../MapaRotas/MapaRotas.jsx'
import {
  buscarParametrosSimulacao,
  buscarRotas,
  buscarSimulacao,
} from '../../services/api.js'
import { INTERVALO_ATUALIZACAO_SIMULACAO_MS } from '../../utils/pollingSimulacao.js'
import { obterIdSimulacaoDaBusca } from '../../utils/rotasUrl.js'
import { criarSincronizadorAbasSimulacao } from '../../utils/sincronizacaoAbasSimulacao.js'
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

    const sincronizador = criarSincronizadorAbasSimulacao({
      aoReceber: (mensagem) => {
        const idAtual = idSimulacaoRef.current

        if (mensagem.tipo === 'simulacao_limpa') {
          if (mensagem.simulacao_anterior_id !== idAtual) return
          idSimulacaoRef.current = null
          setIdSimulacao(null)
          limparDados(false)
          return
        }

        const novoId = mensagem.simulacao_id
        // IDs SQLite são crescentes: mensagens atrasadas de uma execução
        // anterior não podem substituir a simulação mais recente.
        if (idAtual !== null && novoId < idAtual) return

        if (novoId !== idAtual) {
          idSimulacaoRef.current = novoId
          setIdSimulacao(novoId)
          limparDados()
          return
        }

        // O evento informa que algo mudou, mas estado e relógio continuam
        // vindo da API. A consulta imediata evita esperar o próximo polling.
        solicitarConsultaRef.current?.()
      },
    })

    return () => sincronizador.fechar()
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

        if (!desmontado) {
          setSimulacao(estado)
          setRotas(rotasAtuais)
          setEstadoAutoritativo(true)
          setErro('')
          setCarregando(false)
        }
        terminal = estado.estado_execucao === 'concluida' || estado.concluida
      } catch (erroConsulta) {
        if (desmontado || erroConsulta.name === 'AbortError') {
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

      if (desmontado || terminal) return
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
        if (desmontado) return
        const pedidos = auditoria.disponivel
          ? auditoria.snapshot_pedidos?.dados?.pedidos
          : null
        setSnapshotPedidos(Array.isArray(pedidos) ? pedidos : null)
      })
      .catch((erroParametros) => {
        if (!desmontado && erroParametros.name !== 'AbortError') {
          setSnapshotPedidos(null)
        }
      })
      .finally(() => {
        if (!desmontado) setSnapshotCarregando(false)
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
