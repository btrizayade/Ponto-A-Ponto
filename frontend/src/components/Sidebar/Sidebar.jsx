
import {
  Play,
  ClipboardList,
  Users,
  Route
} from 'lucide-react'

import './Sidebar.css'
import logo from '../../assets/logotipo-pontoaponto.jpeg'

function Sidebar({ paginaAtiva, aoNavegar }) {

  const itensMenu = [
    { nome: 'Simulação', icone: Play, disponivel: true },
    { nome: 'Pedidos', icone: ClipboardList, disponivel: true },
    { nome: 'Entregadores', icone: Users, disponivel: true },
    { nome: 'Rotas', icone: Route, disponivel: false }
  ]

  return (
    <aside className="sidebar">

      <div className="sidebar-logo">
        <img src={logo} alt="Ponto-A-Ponto" />
      </div>

      <nav className="sidebar-menu">

        <p className="menu-titulo">MENU PRINCIPAL</p>

        <ul>
          {itensMenu.map((item) => {
            const Icone = item.icone

            return (
              <li
                key={item.nome}
                className={`
                  ${paginaAtiva === item.nome ? 'ativo' : ''}
                  ${!item.disponivel ? 'desabilitado' : ''}
                `}
                onClick={() => {
                  if (item.disponivel) {
                    aoNavegar(item.nome)
                  }
                }}
                aria-disabled={!item.disponivel}
              >
                <Icone size={20} strokeWidth={1.8} />
                <span>{item.nome}</span>
              </li>
            )
          })}
        </ul>

      </nav>

    </aside>
  )
}

export default Sidebar
