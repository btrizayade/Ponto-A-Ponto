
import Sidebar from './components/Sidebar/Sidebar'
import Header from './components/Header/Header'
import ControleSimulacao from './components/ControleSimulacao/ControleSimulacao'
import Indicadores from './components/Indicadores/Indicadores'
import FilaPedidos from './components/FilaPedidos/FilaPedidos'
import EstadoOperacao from './components/EstadoOperacao/EstadoOperacao'

import { useState, useEffect } from 'react'
import { buscarSimulacao } from './services/api'

import './App.css'

function App() {
  const [cenarioSelecionado, setCenarioSelecionado] = useState('')
  const [pedidos, setPedidos] = useState([])
  const [simulacao, setSimulacao] = useState(null)
  const [idSimulacao, setIdSimulacao] = useState(null)

  // Busca os dados da simulação quando o ID é atualizado
  useEffect(() => {
    async function carregarSimulacao() {
      if (!idSimulacao) return

      try {
        const dados = await buscarSimulacao(idSimulacao)
        setSimulacao(dados)

        console.log('Dados da simulação carregados:', dados)
      } catch (erro) {
        console.error('Erro ao carregar simulação:', erro)
      }
    }

    carregarSimulacao()
  }, [idSimulacao])

  // Calcula o tempo decorrido usando o relógio do backend
  function formatarTempoSimulado() {
    if (!simulacao?.inicio || !simulacao?.agora) {
      return '00:00'
    }

    const inicio = new Date(simulacao.inicio).getTime()
    const agora = new Date(simulacao.agora).getTime()

    const diferencaSegundos = Math.max(
      0,
      Math.floor((agora - inicio) / 1000)
    )

    const minutos = Math.floor(diferencaSegundos / 60)
    const segundos = diferencaSegundos % 60

    return `${String(minutos).padStart(2, '0')}:${String(segundos).padStart(2, '0')}`
  }

  const tempoSimulacao = formatarTempoSimulado()

  return (
    <div className="app">
      <Sidebar />

      <main className="conteudo-principal">
        <Header
          tempoSimulacao={tempoSimulacao}
          status={simulacao?.concluida
            ? 'Concluída'
            : simulacao?.iniciada
              ? 'Em andamento'
              : 'Aguardando'}
        />

        <ControleSimulacao
          cenarioSelecionado={cenarioSelecionado}
          setCenarioSelecionado={setCenarioSelecionado}
          setIdSimulacao={setIdSimulacao}
          setSimulacao={setSimulacao}
          idSimulacao={idSimulacao}
        />

        <Indicadores
          pedidos={pedidos}
          simulacao={simulacao}
        />

        <FilaPedidos
          cenarioSelecionado={cenarioSelecionado}
          setPedidosCompartilhados={setPedidos}
          simulacao={simulacao}
        />

        <EstadoOperacao simulacao={simulacao} />
      </main>
    </div>
  )
}

export default App
