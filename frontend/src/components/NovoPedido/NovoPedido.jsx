import { useEffect, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'

import {
  buscarBairros,
  buscarCenarios,
  buscarConfiguracao,
  criarPedido
} from '../../services/api'
import {
  bloquearEnvioDuplicado,
  camposPedidoValidos,
  liberarEnvio,
  montarPedidoRequest,
  restricoesDataCriacao
} from './pedidoForm'
import './NovoPedido.css'

const ROTULOS_CATEGORIA = {
  alimento: 'Alimento',
  medicamento: 'Medicamento',
  roupa: 'Roupa',
  eletronico: 'Eletrônico',
  outro: 'Outro'
}

const ROTULOS_MODALIDADE = {
  entrega_rapida: 'Entrega rápida',
  clube: 'Clube de entrega',
  convencional: 'Entrega convencional'
}

const ROTULOS_BAIRRO = {
  Comercio: 'Comércio',
  Itapua: 'Itapuã',
  Pernambues: 'Pernambués'
}

function NovoPedido({ aoCadastrar }) {
  const [aberto, setAberto] = useState(false)
  const [carregandoOpcoes, setCarregandoOpcoes] = useState(true)
  const [cenarios, setCenarios] = useState([])
  const [bairros, setBairros] = useState([])
  const [categorias, setCategorias] = useState([])
  const [modalidades, setModalidades] = useState([])
  const [pedido, setPedido] = useState({
    cenario_id: '',
    bairro_id: '',
    data_criacao: '',
    categoria_produto: '',
    modalidade: ''
  })
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const submissaoAtiva = useRef(false)

  useEffect(() => {
    let desmontado = false

    async function carregarOpcoes() {
      try {
        setCarregandoOpcoes(true)
        const [opcoesCenarios, opcoesBairros, configuracao] = await Promise.all([
          buscarCenarios(),
          buscarBairros(),
          buscarConfiguracao()
        ])

        if (desmontado) return
        setCenarios(opcoesCenarios)
        setBairros(opcoesBairros)
        setCategorias(configuracao.categorias_produto)
        setModalidades(configuracao.modalidades_entrega)
      } catch (falha) {
        if (!desmontado) setErro(falha.message)
      } finally {
        if (!desmontado) setCarregandoOpcoes(false)
      }
    }

    carregarOpcoes()
    return () => {
      desmontado = true
    }
  }, [])

  function alterarCampo(evento) {
    const { name, value } = evento.target
    setPedido((atual) => {
      if (name !== 'cenario_id') return { ...atual, [name]: value }
      const cenario = cenarios.find((item) => item.id === Number(value))
      const restricoes = restricoesDataCriacao(cenario)
      return {
        ...atual,
        cenario_id: value,
        data_criacao: restricoes.valorInicial
      }
    })
    setErro('')
    setSucesso('')
  }

  function limparFormulario() {
    setPedido({
      cenario_id: '',
      bairro_id: '',
      data_criacao: '',
      categoria_produto: '',
      modalidade: ''
    })
  }

  async function cadastrar(evento) {
    evento.preventDefault()
    if (!camposPedidoValidos(pedido) || !bloquearEnvioDuplicado(submissaoAtiva)) return

    setEnviando(true)
    setErro('')
    setSucesso('')

    try {
      const criado = await criarPedido(montarPedidoRequest(pedido))
      const cenarioId = Number(pedido.cenario_id)
      setSucesso(`Pedido ${criado.codigo} cadastrado com sucesso.`)
      setCenarios((atuais) => atuais.map((cenario) => (
        cenario.id === cenarioId
          ? { ...cenario, quantidade_pedidos: cenario.quantidade_pedidos + 1 }
          : cenario
      )))
      limparFormulario()
      const nomeCenario = cenarios.find((cenario) => cenario.id === cenarioId)?.nome
      aoCadastrar?.(cenarioId, nomeCenario)
    } catch (falha) {
      setErro(falha.message)
    } finally {
      liberarEnvio(submissaoAtiva)
      setEnviando(false)
    }
  }

  function cancelar() {
    limparFormulario()
    setErro('')
    setSucesso('')
    setAberto(false)
  }

  const camposValidos = camposPedidoValidos(pedido)

  return (
    <section className="novo-pedido">
      <div className="novo-pedido-cabecalho">
        <div>
          <h2>Adicionar novo pedido</h2>
          <p>Para adicionar um novo pedido, insira os dados em + Adicionar pedido.</p>
        </div>
        <button
          type="button"
          className="novo-pedido-abrir"
          aria-expanded={aberto}
          onClick={() => setAberto((valor) => !valor)}
          disabled={
            carregandoOpcoes ||
            enviando ||
            !cenarios.length ||
            !bairros.length ||
            !categorias.length ||
            !modalidades.length
          }
        >
          {aberto ? <X size={18} /> : <Plus size={18} />}
          {aberto ? 'Fechar formulário' : 'Adicionar pedido'}
        </button>
      </div>

      <p className="novo-pedido-aviso">
        Pedidos cadastrados durante uma simulação em andamento ficam disponíveis apenas na próxima execução.
      </p>

      {carregandoOpcoes && <p role="status">Carregando opções do cadastro...</p>}
      {erro && <p role="alert" className="novo-pedido-erro">{erro}</p>}
      {sucesso && <p role="status" className="novo-pedido-sucesso">{sucesso}</p>}

      {aberto && !carregandoOpcoes && (
        <form className="novo-pedido-formulario" onSubmit={cadastrar}>
          <label>
            Cenário
            <select
              name="cenario_id"
              value={pedido.cenario_id}
              onChange={alterarCampo}
              required
              disabled={enviando}
            >
              <option value="">Selecione um cenário</option>
              {cenarios.map((cenario) => (
                <option key={cenario.id} value={cenario.id}>
                  {cenario.nome}
                </option>
              ))}
            </select>
          </label>

          {(() => {
            const cenarioSelecionado = cenarios.find(
              (item) => item.id === Number(pedido.cenario_id)
            )
            const restricoes = restricoesDataCriacao(cenarioSelecionado)
            return (
              <label>
                Data de criação
                <input
                  type="date"
                  name="data_criacao"
                  value={pedido.data_criacao}
                  min={restricoes.minimo}
                  max={restricoes.maximo}
                  onChange={alterarCampo}
                  required
                  disabled={!restricoes.minimo || enviando}
                />
                <small>O horário será definido pelo sistema como 09:00 (America/Bahia).</small>
              </label>
            )
          })()}

          <label>
            Bairro de destino
            <select
              name="bairro_id"
              value={pedido.bairro_id}
              onChange={alterarCampo}
              required
              disabled={enviando}
            >
              <option value="">Selecione um bairro</option>
              {bairros.map((bairro) => (
                <option key={bairro.id} value={bairro.id}>
                  {ROTULOS_BAIRRO[bairro.nome] || bairro.nome}
                </option>
              ))}
            </select>
          </label>

          <label>
            Categoria do produto
            <select
              name="categoria_produto"
              value={pedido.categoria_produto}
              onChange={alterarCampo}
              required
              disabled={enviando}
            >
              <option value="">Selecione uma categoria</option>
              {categorias.map((categoria) => (
                <option key={categoria} value={categoria}>
                  {ROTULOS_CATEGORIA[categoria] || categoria}
                </option>
              ))}
            </select>
          </label>

          <fieldset disabled={enviando}>
            <legend>Modalidade de entrega</legend>
            <div className="novo-pedido-modalidades">
              {modalidades.map((modalidade) => (
                <label key={modalidade}>
                  <input
                    type="radio"
                    name="modalidade"
                    value={modalidade}
                    checked={pedido.modalidade === modalidade}
                    onChange={alterarCampo}
                    required
                  />
                  <span>{ROTULOS_MODALIDADE[modalidade] || modalidade}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="novo-pedido-acoes">
            <button type="button" onClick={cancelar} disabled={enviando}>
              Cancelar
            </button>
            <button
              type="submit"
              className="novo-pedido-enviar"
              disabled={!camposValidos || enviando}
            >
              {enviando ? 'Cadastrando...' : 'Cadastrar pedido'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

export default NovoPedido
