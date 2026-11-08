
import { Truck, Clock } from 'lucide-react'
import './Header.css'

function Header({ tempoSimulacao = '00:00', status = 'Aguardando' }) {
  return (
    <header className="cabecalho">

      {/* Título e descrição */}
      <div className="cabecalho-esquerda">
        <div className="cabecalho-icone">
          <Truck size={34} strokeWidth={2} />
        </div>

        <div className="cabecalho-titulo">
          <h1>Simulação</h1>
          <p>
            Acompanhe a execução da simulação, a distribuição dos pedidos
            e as rotas dos entregadores.
          </p>
        </div>
      </div>

      {/* Tempo e status */}
      <div className="cabecalho-direita">

        <div className="tempo-simulacao">
          <Clock size={23} />

          <div>
            <span>Tempo da Simulação</span>
            <strong>{tempoSimulacao}</strong>
          </div>
        </div>

        <div className={`status-simulacao ${status.toLowerCase().replace(' ', '-')}`}>
          <span className="status-ponto"></span>
          <strong>{status}</strong>
        </div>

      </div>

    </header>
  )
}

export default Header
