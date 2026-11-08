
import { useState } from 'react'
import {
  Play,
  ClipboardList,
  Users,
  Route,
  Package,
  History,
  Info
} from 'lucide-react'

import './Sidebar.css'
import logo from '../../assets/logotipo-pontoaponto.jpeg'

function Sidebar() {

  // Guarda o item selecionado no menu
  const [paginaAtiva, setPaginaAtiva] = useState('Simulação')

  // Itens principais do menu
  const itensMenu = [
    { nome: 'Simulação', icone: Play },
    { nome: 'Pedidos', icone: ClipboardList },
    { nome: 'Entregadores', icone: Users },
    { nome: 'Rotas', icone: Route },
    { nome: 'Cenários', icone: Package },
    { nome: 'Histórico', icone: History }
  ]

  return (
    <aside className="sidebar">

      {/* Logotipo */}
      <div className="sidebar-logo">
        <img src={logo} alt="Ponto-A-Ponto" />
      </div>

      {/* Navegação */}
      <nav className="sidebar-menu">

        <p className="menu-titulo">MENU PRINCIPAL</p>

        <ul>
          {itensMenu.map((item) => {
            const Icone = item.icone

            return (
              <li
                key={item.nome}
                className={paginaAtiva === item.nome ? 'ativo' : ''}
                onClick={() => setPaginaAtiva(item.nome)}
              >
                <Icone size={20} strokeWidth={1.8} />
                <span>{item.nome}</span>
              </li>
            )
          })}
        </ul>

        <div className="menu-outros">
          <p className="menu-titulo">OUTROS</p>

          <ul>
            <li
              className={paginaAtiva === 'Sobre o projeto' ? 'ativo' : ''}
              onClick={() => setPaginaAtiva('Sobre o projeto')}
            >
              <Info size={20} strokeWidth={1.8} />
              <span>Sobre o projeto</span>
            </li>
          </ul>
        </div>

      </nav>

    </aside>
  )
}

export default Sidebar
