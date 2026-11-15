
import { useState, useEffect } from 'react'

import {
  Play,
  Pause,
  RotateCcw
} from 'lucide-react'

import {
  buscarCenarios,
  buscarConfiguracao,
  buscarPedidos,
  criarSimulacao,
  pausarSimulacao,
  retomarSimulacao
} from '../../services/api'

import './ControleSimulacao.css'
import {
  criarInicioApi,
  existemPedidosPosteriores,
  sugerirInicioSimulado,
  validarInicioSimulado
} from './inicioSimulado'
import {
  VELOCIDADES_SIMULACAO,
  VELOCIDADE_SIMULACAO_PADRAO,
  velocidadeBloqueada
} from './velocidadeSimulacao'
import { obterConfiguracaoBaseNovaSimulacao } from './configuracaoNovaSimulacao'

function ControleSimulacao({
  cenarioSelecionado,
  aoTrocarCenario,
  setIdSimulacao,
  setSimulacao,
  aoAlterarInicio,
  idSimulacao,
  simulacao
}) {
  const [cenarios, setCenarios] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [criando, setCriando] = useState(false)
  const [reiniciando, setReiniciando] = useState(false)
  const [controlandoPausa, setControlandoPausa] = useState(false)
  const [quantidadeEntregadores, setQuantidadeEntregadores] = useState('2')
  const [quantidadeEntregadoresPadrao, setQuantidadeEntregadoresPadrao] = useState(2)
  const [pedidosCenario, setPedidosCenario] = useState([])
  const [carregandoPedidosCenario, setCarregandoPedidosCenario] = useState(false)
  const [dataInicio, setDataInicio] = useState('')
  const [horaInicio, setHoraInicio] = useState('')
  const [velocidadeSimulacao, setVelocidadeSimulacao] = useState(
    VELOCIDADE_SIMULACAO_PADRAO
  )
  const estadoExecucao = simulacao?.estado_execucao || 'aguardando'
  const pausada = estadoExecucao === 'pausada'
  const concluida = estadoExecucao === 'concluida'
  const simulacaoProtegida = ['executando', 'pausada'].includes(estadoExecucao)

  // Busca os cenários quando o componente é carregado
  useEffect(() => {
    async function carregarCenarios() {
      try {
        setCarregando(true)

        const [dados, configuracao] = await Promise.all([
          buscarCenarios(),
          buscarConfiguracao()
        ])

        setCenarios(dados)
        const quantidadePadrao = configuracao.quantidade_entregadores_padrao
        setQuantidadeEntregadoresPadrao(quantidadePadrao)
        setQuantidadeEntregadores(String(quantidadePadrao))

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

  useEffect(() => {
    if (!cenarioSelecionado) return undefined

    let desmontado = false

    async function carregarPedidosCenario() {
      try {
        setCarregandoPedidosCenario(true)
        const pedidos = await buscarPedidos(cenarioSelecionado)
        if (desmontado) return

        setPedidosCenario(pedidos)
        const sugerido = sugerirInicioSimulado(pedidos)
        setDataInicio(sugerido.data)
        setHoraInicio(sugerido.hora)
        aoAlterarInicio?.({ data: sugerido.data, hora: sugerido.hora })
      } catch (falha) {
        if (desmontado) return
        setPedidosCenario([])
        setErro(`Não foi possível conferir as datas dos pedidos: ${falha.message}`)
      } finally {
        if (!desmontado) setCarregandoPedidosCenario(false)
      }
    }

    carregarPedidosCenario()
    return () => {
      desmontado = true
    }
  }, [cenarioSelecionado, aoAlterarInicio])

  const erroInicio = dataInicio && horaInicio
    ? validarInicioSimulado(dataInicio, horaInicio)
    : ''
  const haPedidosPosteriores = existemPedidosPosteriores(
    pedidosCenario,
    dataInicio,
    horaInicio
  )

  // Cria uma nova simulação
  async function iniciarSimulacao() {
    const erroDataHora = validarInicioSimulado(dataInicio, horaInicio)
    if (erroDataHora) {
      setErro(erroDataHora)
      return
    }

    try {
      setCriando(true)
      setErro('')

      const dados = await criarSimulacao({
        cenario_id: Number(cenarioSelecionado),
        inicio: criarInicioApi(dataInicio, horaInicio),
        quantidade_entregadores: Number(quantidadeEntregadores),
        provedor: 'simulado',
        segundos_reais_por_hora_simulada: Number(velocidadeSimulacao)
      })

      setIdSimulacao(dados.id)
      setSimulacao(dados)

      console.log('Simulação criada:', dados)
    } catch (erro) {
      setErro(erro.message)
    } finally {
      setCriando(false)
    }
  }

  // Apenas restaura o formulário; a execução começa exclusivamente pelo botão Iniciar.
  async function reiniciarSimulacao() {
    if (simulacaoProtegida) {
      setErro('Conclua a simulação atual antes de preparar uma nova operação.')
      return
    }

    try {
      setReiniciando(true)
      setErro('')

      const configuracao = await obterConfiguracaoBaseNovaSimulacao({
        cenarios,
        buscarPedidos,
        quantidadeEntregadoresPadrao
      })

      aoTrocarCenario(configuracao.cenarioId)
      setPedidosCenario(configuracao.pedidos)
      setDataInicio(configuracao.inicio.data)
      setHoraInicio(configuracao.inicio.hora)
      aoAlterarInicio?.(configuracao.inicio)
      setQuantidadeEntregadores(configuracao.quantidadeEntregadores)
      setVelocidadeSimulacao(configuracao.velocidadeSimulacao)
      setIdSimulacao(null)
      setSimulacao(null)
    } catch (erro) {
      setErro(erro.message)
    } finally {
      setReiniciando(false)
    }
  }

  // O estado só muda quando chega a confirmação do backend.
  async function alternarPausa() {
    if (
      !idSimulacao ||
      criando ||
      reiniciando ||
      controlandoPausa ||
      !['executando', 'pausada'].includes(estadoExecucao)
    ) {
      return
    }

    try {
      setControlandoPausa(true)
      setErro('')

      const resposta = pausada
        ? await retomarSimulacao(idSimulacao)
        : await pausarSimulacao(idSimulacao)

      setSimulacao(resposta.simulacao)
    } catch (erro) {
      const acao = pausada ? 'retomar' : 'pausar'
      setErro(`Não foi possível ${acao} a simulação: ${erro.message}`)
    } finally {
      setControlandoPausa(false)
    }
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
            setErro('')
          }}
          disabled={carregando || !!erro && !cenarioSelecionado || criando || reiniciando || simulacaoProtegida}
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

        {erro && <p role="alert">{erro}</p>}
      </div>

      <div className="selecao-cenario inicio-simulacao">
        <label htmlFor="data-inicio-simulacao">Data simulada:</label>
        <input
          id="data-inicio-simulacao"
          type="date"
          value={dataInicio}
          onChange={(evento) => {
            const data = evento.target.value
            setDataInicio(data)
            aoAlterarInicio?.({ data, hora: horaInicio })
            setErro('')
          }}
          disabled={carregandoPedidosCenario || criando || reiniciando || simulacaoProtegida}
          required
        />
        <label htmlFor="hora-inicio-simulacao">Horário:</label>
        <input
          id="hora-inicio-simulacao"
          type="time"
          min="09:00"
          max="16:59"
          step="60"
          value={horaInicio}
          onChange={(evento) => {
            const hora = evento.target.value
            setHoraInicio(hora)
            aoAlterarInicio?.({ data: dataInicio, hora })
            setErro('')
          }}
          disabled={carregandoPedidosCenario || criando || reiniciando || simulacaoProtegida}
          required
        />
        {carregandoPedidosCenario && <span>Conferindo os pedidos do cenário...</span>}
        {erroInicio && <span className="erro-inicio-simulacao">{erroInicio}</span>}
        {!erroInicio && haPedidosPosteriores && (
          <span className="aviso-inicio-simulacao">
            Há pedidos criados depois deste início; eles não participarão do plano desta execução.
          </span>
        )}
      </div>

      <div className="selecao-cenario velocidade-simulacao">
        <label htmlFor="velocidade-simulacao">Velocidade da simulação:</label>
        <select
          id="velocidade-simulacao"
          value={velocidadeSimulacao}
          onChange={(evento) => setVelocidadeSimulacao(evento.target.value)}
          disabled={velocidadeBloqueada(
            estadoExecucao,
            criando || reiniciando
          )}
        >
          {VELOCIDADES_SIMULACAO.map(({ segundos, rotulo }) => (
            <option key={segundos} value={segundos}>
              {rotulo}
            </option>
          ))}
        </select>
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
          disabled={criando || reiniciando || simulacaoProtegida}
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
            !cenarioSelecionado ||
            Boolean(idSimulacao) ||
            simulacaoProtegida ||
            carregandoPedidosCenario ||
            !dataInicio ||
            !horaInicio ||
            Boolean(erroInicio)
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
            controlandoPausa ||
            !['executando', 'pausada'].includes(estadoExecucao) ||
            concluida
          }
        >
          {pausada ? <Play size={18} /> : <Pause size={18} />}
          {controlandoPausa
            ? pausada ? 'Retomando...' : 'Pausando...'
            : pausada ? 'Continuar' : 'Pausar'}
        </button>

        <button
          className="botao-reiniciar"
          onClick={reiniciarSimulacao}
          disabled={
            !idSimulacao ||
            reiniciando ||
            criando ||
            simulacaoProtegida ||
            carregandoPedidosCenario ||
            !dataInicio ||
            !horaInicio ||
            Boolean(erroInicio)
          }
        >
          <RotateCcw size={18} />
          {reiniciando ? 'Preparando...' : 'Nova simulação'}
        </button>

        {simulacaoProtegida && (
          <p role="status" className="aviso-inicio-simulacao">
            Conclua a operação atual antes de preparar outra simulação.
          </p>
        )}

      </div>

    </section>
  )
}

export default ControleSimulacao
