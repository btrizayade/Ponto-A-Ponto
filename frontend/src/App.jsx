import { useState, useCallback, useEffect, useRef } from 'react'

import Sidebar from './components/Sidebar/Sidebar'
import Header from './components/Header/Header'
import ControleSimulacao from './components/ControleSimulacao/ControleSimulacao'
import Indicadores from './components/Indicadores/Indicadores'
import FilaPedidos from './components/FilaPedidos/FilaPedidos'
import EstadoOperacao from './components/EstadoOperacao/EstadoOperacao'
import NovoPedido from './components/NovoPedido/NovoPedido'
import AcompanhamentoRotas from './components/AcompanhamentoRotas/AcompanhamentoRotas.jsx'
import { buscarSimulacao } from './services/api'
import { mensagemFalhaExecucao } from './utils/mensagemFalhaExecucao'
import { INTERVALO_ATUALIZACAO_SIMULACAO_MS } from './utils/pollingSimulacao.js'
import { criarUrlAcompanhamentoRotas } from './utils/rotasUrl.js'
import { criarSincronizadorAbasSimulacao } from './utils/sincronizacaoAbasSimulacao.js'

import './App.css'

const ROTULOS_ESTADO = {
  aguardando: 'Aguardando',
  executando: 'Em andamento',
  pausada: 'Pausada',
  concluida: 'Concluída',
  falhou: 'Falha na execução'
}

function PainelPrincipal() {
  const [paginaAtiva, setPaginaAtiva] = useState('Simulação')

  const [cenarioSelecionado, setCenarioSelecionado] = useState('')
  const [pedidos, setPedidos] = useState([])
  const [simulacao, setSimulacao] = useState(null)
  const [idSimulacao, setIdSimulacao] = useState(null)
  const [erroConsulta, setErroConsulta] = useState('')
  const [revisaoPedidos, setRevisaoPedidos] = useState(0)
  const [cenarioListaPedidos, setCenarioListaPedidos] = useState(null)
  const [nomeCenarioListaPedidos, setNomeCenarioListaPedidos] = useState('')
  const [inicioSimuladoSelecionado, setInicioSimuladoSelecionado] = useState(null)
  const revisaoEstado = useRef(0)
  const estadoSimulacaoRef = useRef(simulacao?.estado_execucao)
  const idSimulacaoRef = useRef(idSimulacao)
  const sincronizadorAbasRef = useRef(null)
  const ultimoEstadoPublicadoRef = useRef({ id: null, estado: null })

  useEffect(() => {
    const sincronizador = criarSincronizadorAbasSimulacao()
    sincronizadorAbasRef.current = sincronizador
    return () => {
      sincronizador.fechar()
      if (sincronizadorAbasRef.current === sincronizador) {
        sincronizadorAbasRef.current = null
      }
    }
  }, [])

  const publicarEstadoEntreAbas = useCallback((estado) => {
    if (!estado?.id || !estado.estado_execucao) {
      ultimoEstadoPublicadoRef.current = { id: null, estado: null }
      return
    }

    const anterior = ultimoEstadoPublicadoRef.current
    if (anterior.id === estado.id && anterior.estado === estado.estado_execucao) return

    ultimoEstadoPublicadoRef.current = {
      id: estado.id,
      estado: estado.estado_execucao,
    }
    sincronizadorAbasRef.current?.publicar({
      tipo: 'estado_alterado',
      simulacaoId: estado.id,
      estadoExecucao: estado.estado_execucao,
    })
  }, [])

  useEffect(() => {
    estadoSimulacaoRef.current = simulacao?.estado_execucao
  }, [simulacao?.estado_execucao])

  const atualizarSimulacao = useCallback((estado) => {
    revisaoEstado.current += 1
    estadoSimulacaoRef.current = estado?.estado_execucao
    setSimulacao(estado)
    setErroConsulta('')
    publicarEstadoEntreAbas(estado)
  }, [publicarEstadoEntreAbas])

  const atualizarIdSimulacao = useCallback((id) => {
    const anterior = idSimulacaoRef.current
    idSimulacaoRef.current = id
    setIdSimulacao(id)
    if (Number.isSafeInteger(id) && id > 0) {
      sincronizadorAbasRef.current?.publicar({
        tipo: 'simulacao_selecionada',
        simulacaoId: id,
      })
    } else if (Number.isSafeInteger(anterior) && anterior > 0) {
      sincronizadorAbasRef.current?.publicar({
        tipo: 'simulacao_limpa',
        simulacaoAnteriorId: anterior,
      })
      ultimoEstadoPublicadoRef.current = { id: null, estado: null }
    }
  }, [])

  const aoCadastrarPedido = useCallback((cenarioId, nomeCenario) => {
    setCenarioListaPedidos(cenarioId)
    setNomeCenarioListaPedidos(nomeCenario)
    setRevisaoPedidos((revisao) => revisao + 1)
  }, [])

  useEffect(() => {
    if (!idSimulacao || simulacao?.estado_execucao !== 'executando') {
      return undefined
    }

    let desmontado = false
    let temporizador
    let consultaAtual

    async function consultarEstado() {
      const revisaoDaConsulta = revisaoEstado.current
      consultaAtual = new AbortController()

      try {
        const estado = await buscarSimulacao(idSimulacao, {
          signal: consultaAtual.signal
        })
        if (!desmontado && revisaoDaConsulta === revisaoEstado.current) {
          estadoSimulacaoRef.current = estado.estado_execucao
          setSimulacao(estado)
          setErroConsulta('')
          publicarEstadoEntreAbas(estado)
        }
      } catch (erro) {
        if (desmontado) return
        setErroConsulta(erro.message)
        if (erro.message.includes('HTTP 410')) return
      }

      if (!desmontado) {
        temporizador = window.setTimeout(consultarEstado, INTERVALO_ATUALIZACAO_SIMULACAO_MS)
      }
    }

    temporizador = window.setTimeout(consultarEstado, INTERVALO_ATUALIZACAO_SIMULACAO_MS)
    return () => {
      desmontado = true
      window.clearTimeout(temporizador)
      consultaAtual?.abort()
    }
  }, [idSimulacao, simulacao?.estado_execucao, publicarEstadoEntreAbas])

  // Navega até a seção selecionada com rolagem suave
  function navegarParaSecao(nomeSecao) {
    setPaginaAtiva(nomeSecao)

    const secoes = {
      'Simulação': 'secao-simulacao',
      'Pedidos': 'secao-pedidos',
      'Entregadores': 'secao-entregadores'
    }

    const elemento = document.getElementById(secoes[nomeSecao])

    elemento?.scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    })
  }

  // Limpa os dados da simulação anterior ao trocar de cenário
  const trocarCenario = useCallback((novoCenario) => {
  if (['executando', 'pausada'].includes(estadoSimulacaoRef.current)) return

  setCenarioSelecionado(novoCenario)
  setCenarioListaPedidos(null)
  setNomeCenarioListaPedidos('')
  setInicioSimuladoSelecionado(null)
  atualizarIdSimulacao(null)
  atualizarSimulacao(null)
  setPedidos([])
  setRevisaoPedidos((revisao) => revisao + 1)
}, [atualizarIdSimulacao, atualizarSimulacao])

  // Calcula o tempo decorrido usando o relógio do backend
  function formatarTempoSimulado() {
    if (!simulacao?.inicio || !simulacao?.agora) {
      return '0h 00min 00s'
    }

    const inicio = new Date(simulacao.inicio).getTime()
    const agora = new Date(simulacao.agora).getTime()

    const diferencaSegundos = Math.max(
      0,
      Math.floor((agora - inicio) / 1000)
    )

    const horas = Math.floor(diferencaSegundos / 3600)
    const minutos = Math.floor((diferencaSegundos % 3600) / 60)
    const segundos = diferencaSegundos % 60

    return `${horas}h ${String(minutos).padStart(2, '0')}min ${String(segundos).padStart(2, '0')}s`
  }

  const tempoSimulacao = formatarTempoSimulado()
  const erroExecucao = mensagemFalhaExecucao(simulacao)

  return (
    <div className="app">

      <Sidebar
        paginaAtiva={paginaAtiva}
        aoNavegar={navegarParaSecao}
        urlRotas={criarUrlAcompanhamentoRotas(idSimulacao)}
      />

      <main className="conteudo-principal">

        {erroConsulta && (
          <p role="status" className="erro-atualizacao">
            Não foi possível atualizar a simulação: {erroConsulta}
          </p>
        )}
        {erroExecucao && (
          <p role="alert" className="erro-atualizacao">
            {erroExecucao}
          </p>
        )}

        <Header
          tempoSimulacao={tempoSimulacao}
          status={ROTULOS_ESTADO[simulacao?.estado_execucao] || 'Aguardando'}
        />

        <div id="secao-simulacao" className="secao-dashboard">
          <NovoPedido aoCadastrar={aoCadastrarPedido} />

          <ControleSimulacao
            cenarioSelecionado={cenarioSelecionado}
            aoTrocarCenario={trocarCenario}
            setIdSimulacao={atualizarIdSimulacao}
            setSimulacao={atualizarSimulacao}
            idSimulacao={idSimulacao}
            simulacao={simulacao}
            aoAlterarInicio={setInicioSimuladoSelecionado}
          />

          <Indicadores
            pedidos={pedidos}
            simulacao={simulacao}
          />
        </div>

        <div id="secao-pedidos" className="secao-dashboard">
          <FilaPedidos
            cenarioSelecionado={cenarioSelecionado}
            setPedidosCompartilhados={setPedidos}
            simulacao={simulacao}
            revisaoLista={revisaoPedidos}
            cenarioExibicao={cenarioListaPedidos || cenarioSelecionado}
            nomeCenarioExibicao={nomeCenarioListaPedidos}
            inicioSimuladoSelecionado={inicioSimuladoSelecionado}
          />
        </div>

        <div id="secao-entregadores" className="secao-dashboard">
          <EstadoOperacao
            simulacao={simulacao}
          />
        </div>

      </main>
    </div>
  )
}

function App() {
  if (typeof window !== 'undefined' && window.location.pathname.replace(/\/$/, '') === '/rotas') {
    return <AcompanhamentoRotas />
  }

  return <PainelPrincipal />
}

export default App
