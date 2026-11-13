
import { useState, useEffect } from 'react'

import {
  Package,
  Clock,
  MapPin,
  Award,
  ListOrdered
} from 'lucide-react'

import { buscarPedidos } from '../../services/api'
import { combinarPedidosDaSimulacao } from './pedidosVisiveis'
import {
  formatarInicioSelecionado,
  obterTemposPedido
} from './pedidoTemporal'
import './FilaPedidos.css'

function TemposPedido({ pedido, simulacaoAtiva }) {
  const tempos = obterTemposPedido(pedido)

  return (
    <div className="pedido-tempos">
      <div>
        <Clock size={15} />
        <span>Pedido criado: <strong>{tempos.criadoEm || 'Não informado'}</strong></span>
      </div>
      <div>
        <Clock size={15} />
        <span>Prazo SLA: <strong>{tempos.prazoSla || 'Não informado'}</strong></span>
      </div>
      {simulacaoAtiva && (
        <>
          <div>
            <Clock size={15} />
            <span>Previsão do plano: <strong>{tempos.previsaoEntrega || 'Aguardando planejamento'}</strong></span>
          </div>
          <div>
            <Clock size={15} />
            <span>Entrega na simulação: <strong>{tempos.entregueEm || 'Ainda não entregue'}</strong></span>
          </div>
          <div>
            <Clock size={15} />
            <span>Última atualização: <strong>{tempos.atualizadoEm || 'Sem evento registrado'}</strong></span>
          </div>
        </>
      )}
    </div>
  )
}

function FilaPedidos({
  cenarioSelecionado,
  setPedidosCompartilhados,
  simulacao,
  revisaoLista = 0,
  cenarioExibicao,
  nomeCenarioExibicao = '',
  inicioSimuladoSelecionado = null
}) {
  const [pedidos, setPedidos] = useState([])
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')

  // Verifica se a simulação já foi iniciada
  const simulacaoIniciada = Boolean(simulacao?.iniciada)
  const simulacaoConcluida = simulacao?.estado_execucao === 'concluida'
  const cenarioPedidos = cenarioExibicao || cenarioSelecionado
  const simulacaoDaLista = simulacaoIniciada &&
    simulacao?.cenario_id === Number(cenarioPedidos)

  // Usa os pedidos atualizados da simulação quando ela estiver iniciada
  const pedidosDaSimulacao = simulacao?.pedidos || []
  const simulacaoDoCenario = simulacao?.cenario_id === Number(cenarioPedidos)
  const pedidosExibidos = simulacaoDoCenario && simulacaoConcluida
    ? pedidos
    : simulacaoDoCenario
    ? combinarPedidosDaSimulacao(pedidosDaSimulacao, pedidos)
    : simulacaoDaLista
      ? pedidosDaSimulacao
      : pedidos

  // Organiza pela posição somente durante a simulação
  const pedidosOrdenados = simulacaoDaLista
    ? [...pedidosExibidos].sort(
        (a, b) =>
          (a.posicao_fila ?? Infinity) -
          (b.posicao_fila ?? Infinity)
      )
    : pedidosExibidos
  const inicioSelecionadoTexto = formatarInicioSelecionado(
    inicioSimuladoSelecionado
  )
  const inicioSimulacaoTexto = simulacao?.cenario_id === Number(cenarioPedidos)
    ? obterTemposPedido({ criado_em: simulacao.inicio }).criadoEm
    : null

  // Busca os pedidos sempre que o cenário selecionado mudar
  useEffect(() => {
    async function carregarPedidos() {
      if (!cenarioPedidos) {
        setPedidos([])
        setPedidosCompartilhados([])
        return
      }

      try {
        setCarregando(true)
        setErro('')

        const dados = await buscarPedidos(cenarioPedidos)

        setPedidos(dados)
        setPedidosCompartilhados(dados)
      } catch (erro) {
        setErro(erro.message)
        setPedidos([])
        setPedidosCompartilhados([])
      } finally {
        setCarregando(false)
      }
    }

    carregarPedidos()
  }, [cenarioPedidos, revisaoLista, simulacao?.estado_execucao, setPedidosCompartilhados])

  // Traduz o status do pedido para exibição
  function obterTextoStatus(status) {
    const statusMapeados = {
      pendente: 'Pendente',
      na_fila: 'Na fila',
      atribuido: 'Atribuído',
      em_rota: 'Em rota',
      entregue: 'Entregue',
      proxima_simulacao: 'Próxima simulação'
    }

    return statusMapeados[status] || 'Aguardando simulação'
  }

  return (
    <section className="fila-pedidos">

      <div className="fila-cabecalho">
        <div>
          <h2>
            {simulacaoDaLista
              ? 'Fila priorizada'
              : 'Pedidos cadastrados'}
          </h2>

          <p>
            {nomeCenarioExibicao && `Cenário: ${nomeCenarioExibicao}. `}
            {simulacaoDaLista
              ? 'Pedidos organizados pela prioridade de atendimento'
              : 'Pedidos registrados no cenário, aguardando a simulação'}
          </p>
          {inicioSelecionadoTexto && (
            <p className="fila-inicio-simulado">
              Início operacional selecionado: <strong>{inicioSelecionadoTexto}</strong>
            </p>
          )}
          {simulacaoDaLista && inicioSimulacaoTexto && (
            <p className="fila-inicio-simulado">
              Previsões exibidas para o início da simulação atual: <strong>{inicioSimulacaoTexto}</strong>
            </p>
          )}
        </div>

        <div className="fila-total">
          <Package size={18} />
          <span>{pedidosExibidos.length} pedidos</span>
        </div>
      </div>

      <div className="lista-pedidos">

        {carregando && (
          <p>Carregando pedidos...</p>
        )}

        {erro && (
          <p>{erro}</p>
        )}

        {!carregando && !erro && pedidosExibidos.length === 0 && (
          <p>Nenhum pedido encontrado para este cenário.</p>
        )}

        {!carregando && !erro && pedidosOrdenados.map((pedido) => (
          <div
            className={`pedido-item${pedido.atualizado_em ? ' pedido-com-atualizacao' : ''}`}
            key={`${pedido.codigo}-${pedido.status || 'pendente'}-${pedido.atualizado_em || ''}`}
          >

            <div className="pedido-identificacao">
              <strong>{pedido.codigo}</strong>

              <span className={`pedido-status status-${pedido.status || 'pendente'}`}>
                {obterTextoStatus(pedido.status)}
              </span>
            </div>

            <div className="pedido-informacao">
              <MapPin size={16} />
              <span>{pedido.bairro}</span>
            </div>

            {simulacaoIniciada && (
              <>
                <div className="pedido-prioridade">
                  <Award size={16} />
                  <span>
                    Pontuação: <strong>{pedido.prioridade ?? '—'}</strong>
                  </span>
                </div>

                <div className="pedido-posicao">
                  <ListOrdered size={16} />
                  <span>
                    Posição: <strong>{pedido.posicao_fila ?? '—'}</strong>
                  </span>
                </div>
              </>
            )}

            <div className="pedido-entregador">
              <span className="pedido-entregador-label">Entregador:</span>
              <strong>
                {pedido.entregador_codigo || 'Não atribuído'}
              </strong>
            </div>

            <TemposPedido
              pedido={pedido}
              simulacaoAtiva={simulacaoDaLista}
            />

          </div>
        ))}

      </div>

    </section>
  )
}

export default FilaPedidos
