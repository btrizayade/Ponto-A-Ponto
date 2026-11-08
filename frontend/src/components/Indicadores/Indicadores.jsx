
import {
  Package,
  Users,
  CheckCircle,
  Clock
} from 'lucide-react'

import './Indicadores.css'

function Indicadores({ pedidos = [], simulacao = null }) {
  const dadosIndicadores = simulacao?.indicadores
  const entregadores = simulacao?.entregadores || []
  const totalPedidos = dadosIndicadores?.total_pedidos ?? pedidos.length
  const entregues = dadosIndicadores?.entregues ?? 0
  const pendentes = totalPedidos - entregues


  const indicadores = [
    {
      titulo: 'Total de pedidos',
      valor: totalPedidos,
      descricao: 'Pedidos no cenário',
      icone: Package,
      cor: 'laranja'
    },
    {
      titulo: 'Entregadores',
      valor: entregadores.length,
      descricao: 'Na operação',
      icone: Users,
      cor: 'azul'
    },
    {
      titulo: 'Entregues',
      valor: entregues,
      descricao: 'Pedidos concluídos',
      icone: CheckCircle,
      cor: 'verde'
    },
    {
      titulo: 'Não entregues',
      valor: pendentes,
      descricao: 'Pedidos ainda em andamento',
      icone: Clock,
      cor: 'amarelo'
    }
  ]

  return (
    <section className="indicadores">
      {indicadores.map((item) => {
        const Icone = item.icone

        return (
          <div className="card-indicador" key={item.titulo}>
            <div className="indicador-cabecalho">
              <span>{item.titulo}</span>

              <div className={`indicador-icone ${item.cor}`}>
                <Icone size={22} />
              </div>
            </div>

            <strong>{item.valor}</strong>

            <p>{item.descricao}</p>
          </div>
        )
      })}
    </section>
  )
}

export default Indicadores
