
import { useState, useEffect } from 'react'

import {
  Package,
  Clock,
  MapPin,
  Award,
  ListOrdered
} from 'lucide-react'

import { buscarPedidos } from '../../services/api'
import './FilaPedidos.css'

function FilaPedidos({
  cenarioSelecionado,
  setPedidosCompartilhados,
  simulacao
}) {
  const [pedidos, setPedidos] = useState([])
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')

  // Verifica se a simulação já foi iniciada
  const simulacaoIniciada = Boolean(simulacao?.iniciada)

  // Usa os pedidos atualizados da simulação quando ela estiver iniciada
  const pedidosExibidos = simulacaoIniciada
    ? simulacao.pedidos || []
    : pedidos

  // Organiza pela posição somente durante a simulação
  const pedidosOrdenados = simulacaoIniciada
    ? [...pedidosExibidos].sort(
        (a, b) =>
          (a.posicao_fila ?? Infinity) -
          (b.posicao_fila ?? Infinity)
      )
    : pedidosExibidos

  // Busca os pedidos sempre que o cenário selecionado mudar
  useEffect(() => {
    async function carregarPedidos() {
      if (!cenarioSelecionado) {
        setPedidos([])
        setPedidosCompartilhados([])
        return
      }

      try {
        setCarregando(true)
        setErro('')

        const dados = await buscarPedidos(cenarioSelecionado)

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
  }, [cenarioSelecionado, setPedidosCompartilhados])

  // Traduz o status do pedido para exibição
  function obterTextoStatus(status) {
    const statusMapeados = {
      pendente: 'Pendente',
      na_fila: 'Na fila',
      atribuido: 'Atribuído',
      em_rota: 'Em rota',
      entregue: 'Entregue'
    }

    return statusMapeados[status] || 'Aguardando simulação'
  }

  return (
    <section className="fila-pedidos">

      <div className="fila-cabecalho">
        <div>
          <h2>
            {simulacaoIniciada
              ? 'Fila priorizada'
              : 'Pedidos cadastrados'}
          </h2>

          <p>
            {simulacaoIniciada
              ? 'Pedidos organizados pela prioridade de atendimento'
              : 'Pedidos registrados no cenário, aguardando a simulação'}
          </p>
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
          <div className="pedido-item" key={pedido.codigo}>

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

            <div className="pedido-prazo">
              <Clock size={16} />
              <span>
                {pedido.prazo_entrega_em
                  ? new Date(pedido.prazo_entrega_em).toLocaleString('pt-BR')
                  : 'Prazo não informado'}
              </span>
            </div>

          </div>
        ))}

      </div>

    </section>
  )
}

export default FilaPedidos
