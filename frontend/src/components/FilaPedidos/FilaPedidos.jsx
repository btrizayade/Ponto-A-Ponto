
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
  // Estados
  const [pedidos, setPedidos] = useState([])
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')

  // Usa os pedidos atualizados da simulação quando ela estiver iniciada
  const pedidosExibidos = simulacao?.iniciada
    ? simulacao.pedidos || []
    : pedidos

    // Organiza os pedidos pela posição na fila
const pedidosOrdenados = [...pedidosExibidos].sort((a, b) => {
   return (a.posicao_fila ?? Infinity) - (b.posicao_fila ?? Infinity)
  })

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

    return statusMapeados[status] || 'Não informado'
  }

  return (
    <section className="fila-pedidos">

      <div className="fila-cabecalho">
        <div>
          <h2>Fila de Pedidos</h2>
          <p>Pedidos cadastrados no cenário</p>
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

              <span className={`pedido-status status-${pedido.status}`}>
                {obterTextoStatus(pedido.status)}
              </span>
            </div>

            <div className="pedido-informacao">
              <MapPin size={16} />
              <span>{pedido.bairro}</span>
            </div>

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
