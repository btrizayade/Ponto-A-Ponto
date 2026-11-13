import { useState, useCallback, useEffect, useRef } from 'react'

import Sidebar from './components/Sidebar/Sidebar'
import Header from './components/Header/Header'
import ControleSimulacao from './components/ControleSimulacao/ControleSimulacao'
import Indicadores from './components/Indicadores/Indicadores'
import FilaPedidos from './components/FilaPedidos/FilaPedidos'
import EstadoOperacao from './components/EstadoOperacao/EstadoOperacao'
import NovoPedido from './components/NovoPedido/NovoPedido'
import { buscarRotas, buscarSimulacao } from './services/api'

import './App.css'

const ROTULOS_ESTADO = {
  aguardando: 'Aguardando',
  executando: 'Em andamento',
  pausada: 'Pausada',
  concluida: 'Concluída',
  falhou: 'Falha na execução'
}

const intervaloConfigurado = Number(
  import.meta.env?.VITE_INTERVALO_ATUALIZACAO_SIMULACAO_MS || 100
)
const INTERVALO_ATUALIZACAO_MS = Number.isFinite(intervaloConfigurado) && intervaloConfigurado > 0
  ? intervaloConfigurado
  : 100

function App() {
  const [paginaAtiva, setPaginaAtiva] = useState('Simulação')

  const [cenarioSelecionado, setCenarioSelecionado] = useState('')
  const [pedidos, setPedidos] = useState([])
  const [simulacao, setSimulacao] = useState(null)
  const [rotas, setRotas] = useState(null)
  const [idSimulacao, setIdSimulacao] = useState(null)
  const [erroConsulta, setErroConsulta] = useState('')
  const [revisaoPedidos, setRevisaoPedidos] = useState(0)
  const [cenarioListaPedidos, setCenarioListaPedidos] = useState(null)
  const [nomeCenarioListaPedidos, setNomeCenarioListaPedidos] = useState('')
  const [inicioSimuladoSelecionado, setInicioSimuladoSelecionado] = useState(null)
  const revisaoEstado = useRef(0)
  const estadoSimulacaoRef = useRef(simulacao?.estado_execucao)

  useEffect(() => {
    estadoSimulacaoRef.current = simulacao?.estado_execucao
  }, [simulacao?.estado_execucao])

  const atualizarSimulacao = useCallback((estado) => {
    revisaoEstado.current += 1
    setSimulacao(estado)
    setErroConsulta('')
  }, [])

  const atualizarIdSimulacao = useCallback((id) => {
    setIdSimulacao(id)
    setRotas(null)
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
        const rotasAtuais = estado.iniciada
          ? await buscarRotas(idSimulacao, { signal: consultaAtual.signal })
          : null
        if (!desmontado && revisaoDaConsulta === revisaoEstado.current) {
          setSimulacao(estado)
          setRotas(rotasAtuais)
          setErroConsulta('')
        }
      } catch (erro) {
        if (desmontado) return
        setErroConsulta(erro.message)
        if (erro.message.includes('HTTP 410')) return
      }

      if (!desmontado) {
        temporizador = window.setTimeout(consultarEstado, INTERVALO_ATUALIZACAO_MS)
      }
    }

    temporizador = window.setTimeout(consultarEstado, INTERVALO_ATUALIZACAO_MS)
    return () => {
      desmontado = true
      window.clearTimeout(temporizador)
      consultaAtual?.abort()
    }
  }, [idSimulacao, simulacao?.estado_execucao])

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
  setIdSimulacao(null)
  atualizarSimulacao(null)
  setRotas(null)
  setPedidos([])
  setRevisaoPedidos((revisao) => revisao + 1)
}, [atualizarSimulacao])

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

  return (
    <div className="app">

      <Sidebar
        paginaAtiva={paginaAtiva}
        aoNavegar={navegarParaSecao}
      />

      <main className="conteudo-principal">

        {erroConsulta && (
          <p role="status" className="erro-atualizacao">
            Não foi possível atualizar a simulação: {erroConsulta}
          </p>
        )}
        {simulacao?.estado_execucao === 'falhou' && (
          <p role="alert" className="erro-atualizacao">
            A execução automática falhou: {simulacao.erro_execucao || 'consulte os logs do backend.'}
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
          <EstadoOperacao simulacao={simulacao} rotas={rotas} />
        </div>

      </main>
    </div>
  )
}

export default App
