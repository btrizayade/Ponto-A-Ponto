
import { useState, useEffect } from 'react'

import {
  Play,
  Pause,
  SkipForward,
  RotateCcw
} from 'lucide-react'

import {
  buscarCenarios,
  criarSimulacao,
  avancarEtapa
} from '../../services/api'

import './ControleSimulacao.css'

function ControleSimulacao({
  cenarioSelecionado,
  aoTrocarCenario,
  setIdSimulacao,
  setSimulacao,
  idSimulacao
}) {
  
    // Obtém a data e o horário atuais para iniciar a simulação
  // Obtém a data e o horário atuais
function obterInicioSimulacao() {
  return new Date().toISOString()
}

  


  const [cenarios, setCenarios] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [criando, setCriando] = useState(false)
  const [avancando, setAvancando] = useState(false)
  const [reiniciando, setReiniciando] = useState(false)
  const [pausada, setPausada] = useState(false)
  const [quantidadeEntregadores, setQuantidadeEntregadores] = useState('2')

  // Busca os cenários quando o componente é carregado
  useEffect(() => {
    async function carregarCenarios() {
      try {
        setCarregando(true)

        const dados = await buscarCenarios()

        setCenarios(dados)

        if (dados.length > 0) {
          aoTrocarCenario(String(dados[0].id))
        }
      } catch (erro) {
        setErro(erro.message)
      } finally {
        setCarregando(false)
      }
    }

    carregarCenarios()
  }, [aoTrocarCenario])

  
  // Cria uma nova simulação
  async function iniciarSimulacao() {
    try {
      setCriando(true)
      setErro('')

      const dados = await criarSimulacao({
        cenario_id: Number(cenarioSelecionado),
        inicio: obterInicioSimulacao(),
        quantidade_entregadores: Number(quantidadeEntregadores),
        estrategia: 'insercao_mais_barata',
        provedor: 'simulado'
      })

      setIdSimulacao(dados.id)
      setSimulacao(dados)
      setPausada(false)

      console.log('Simulação criada:', dados)
    } catch (erro) {
      setErro(erro.message)
    } finally {
      setCriando(false)
    }
  }

  // Avança uma etapa da simulação
  async function avancarSimulacao() {
    if (pausada || !idSimulacao || avancando || reiniciando) {
      return
    }

    try {
      setAvancando(true)
      setErro('')

      const dados = await avancarEtapa(idSimulacao)

      setSimulacao(dados.estado)

      console.log('Etapa avançada:', dados)
    } catch (erro) {
      setErro(erro.message)
    } finally {
      setAvancando(false)
    }
  }

  // Cria uma nova execução da simulação
  async function reiniciarSimulacao() {
    try {
      setReiniciando(true)
      setErro('')

      const dados = await criarSimulacao({
        cenario_id: Number(cenarioSelecionado),
        inicio: obterInicioSimulacao(),
        quantidade_entregadores: Number(quantidadeEntregadores),
        estrategia: 'insercao_mais_barata',
        provedor: 'simulado'
      })

      setIdSimulacao(dados.id)
      setSimulacao(dados)
      setPausada(false)

      console.log('Nova simulação criada:', dados)
    } catch (erro) {
      setErro(erro.message)
    } finally {
      setReiniciando(false)
    }
  }

  // Alterna entre pausar e retomar a simulação
  function alternarPausa() {
    if (!idSimulacao || criando || reiniciando || avancando) {
      return
    }

    setPausada((estadoAtual) => !estadoAtual)
  }

  return (
    <section className="controle-simulacao">

      {/* Seleção de cenário */}
      <div className="selecao-cenario">
        <label htmlFor="cenario">Cenário:</label>

        <select
          id="cenario"
          value={cenarioSelecionado}
          onChange={(evento) => {
            aoTrocarCenario(evento.target.value)
            setPausada(false)
            setErro('')
          }}
          disabled={carregando || !!erro && !cenarioSelecionado || criando || reiniciando || avancando}
        >
          {carregando && (
            <option value="">Carregando cenários...</option>
          )}

          {!carregando && !erro && cenarios.map((cenario) => (
            <option key={cenario.id} value={cenario.id}>
              {cenario.nome}
            </option>
          ))}
        </select>

        {erro && <p>{erro}</p>}
      </div>

      {/* Seleção da quantidade de entregadores */}
      <div className="selecao-cenario">
        <label htmlFor="quantidade-entregadores">
          Entregadores:
        </label>

        <select
          id="quantidade-entregadores"
          value={quantidadeEntregadores}
          onChange={(evento) =>
            setQuantidadeEntregadores(evento.target.value)
          }
          disabled={criando || reiniciando}
        >
          <option value="1">1 entregador</option>
          <option value="2">2 entregadores</option>
          <option value="3">3 entregadores</option>
          <option value="4">4 entregadores</option>
          <option value="5">5 entregadores</option>
        </select>
      </div>

      {/* Botões de controle */}
      <div className="botoes-controle">

        <button
          className="botao-iniciar"
          onClick={iniciarSimulacao}
          disabled={
            criando ||
            reiniciando ||
            avancando ||
            !cenarioSelecionado
          }
        >
          <Play size={18} />
          {criando ? 'Criando...' : 'Iniciar'}
        </button>

        <button
          className="botao-pausar"
          onClick={alternarPausa}
          disabled={
            !idSimulacao ||
            reiniciando ||
            criando ||
            avancando
          }
        >
          {pausada ? <Play size={18} /> : <Pause size={18} />}
          {pausada ? 'Retomar' : 'Pausar'}
        </button>

        <button
          className="botao-avancar"
          onClick={avancarSimulacao}
          disabled={
            !idSimulacao ||
            avancando ||
            reiniciando ||
            criando ||
            pausada
          }
        >
          <SkipForward size={18} />
          {avancando ? 'Avançando...' : 'Avançar etapa'}
        </button>

        <button
          className="botao-reiniciar"
          onClick={reiniciarSimulacao}
          disabled={
            !idSimulacao ||
            avancando ||
            reiniciando ||
            criando
          }
        >
          <RotateCcw size={18} />
          {reiniciando ? 'Criando nova...' : 'Nova simulação'}
        </button>

      </div>

    </section>
  )
}

export default ControleSimulacao
