
import {
  Truck,
  Package,
  MapPin
} from 'lucide-react'

import './EstadoOperacao.css'

function EstadoOperacao({ simulacao = null }) {
  // Dados reais retornados pelo backend
  const entregadores = simulacao?.entregadores || []
  const pedidos = simulacao?.pedidos || []

  return (
    <section className="estado-operacao">

      <div className="estado-cabecalho">
        <div>
          <h2>Estado da Operação</h2>
          <p>Acompanhamento dos entregadores e suas viagens</p>
        </div>

        <div className="estado-total">
          <Truck size={18} />
          <span>{entregadores.length} entregadores</span>
        </div>
      </div>

      <div className="lista-entregadores">

        {entregadores.map((entregador) => {

          // Conta apenas os pedidos que ainda não foram entregues
          const paradasRestantes = pedidos.filter(
            (pedido) =>
              pedido.entregador_codigo === entregador.codigo &&
              pedido.status !== 'entregue'
          ).length

          return (
            <div
              className="card-entregador"
              key={entregador.codigo}
            >

              <div className="entregador-identificacao">
                <div className="entregador-icone">
                  <Truck size={22} />
                </div>

                <div>
                  <strong>{entregador.codigo}</strong>
                  <span>
                    {entregador.situacao === 'em_viagem'
                      ? 'Em viagem'
                      : 'No centro'}
                  </span>
                </div>
              </div>

              <div className="entregador-dados">

                <div>
                  <Package size={17} />
                  <span>
                    {entregador.viagens_planejadas ?? 0} viagens
                  </span>
                </div>

                <div>
                  <MapPin size={17} />
                  <span>{paradasRestantes} paradas restantes</span>
                </div>

              </div>

            </div>
          )
        })}

      </div>

    </section>
  )
}

export default EstadoOperacao
