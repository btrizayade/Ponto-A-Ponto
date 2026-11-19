import { useEffect, useMemo } from 'react'
import { latLngBounds } from 'leaflet'
import {
  MapContainer,
  Marker,
  Popup,
  Polyline,
  TileLayer,
  FeatureGroup,
  useMap,
} from 'react-leaflet'

import {
  classeSituacaoViagem,
  coletarPontosEnquadramento,
  listarViagens,
  prepararMarcadores,
  resumoEntregadores,
  textoSituacao,
} from './mapaRotasUtils.js'
import VeiculosAnimados from './VeiculosAnimados.jsx'
import { obterIconeCentro, obterIconeParada } from './iconesMapa.js'
import './MapaRotas.css'

const CENTRO_SALVADOR = [-12.971, -38.501]

function AjustarEnquadramento({ rotas }) {
  const mapa = useMap()
  const pontos = useMemo(() => coletarPontosEnquadramento(rotas), [rotas])
  const assinatura = JSON.stringify(pontos)

  useEffect(() => {
    const coordenadas = JSON.parse(assinatura)
    if (coordenadas.length > 1) {
      mapa.fitBounds(latLngBounds(coordenadas), { padding: [32, 32], maxZoom: 14 })
    } else if (coordenadas.length === 1) {
      mapa.setView(coordenadas[0], 13)
    }
  }, [assinatura, mapa])

  return null
}

function InformacoesPedidoParada({ parada }) {
  return (
    <div className="mapa-rotas__pedido-agrupado">
      <div className="mapa-rotas__pedido-entregador">
        <span
          className="mapa-rotas__pedido-cor"
          style={{ backgroundColor: parada.cor }}
          aria-hidden="true"
        />
        <strong>{parada.pedido_codigo}</strong>
        <span>· {parada.origem === 'manual'
          ? `Pedido manual ${parada.idOrigem ?? 'M?'}`
          : parada.origem === 'referencia'
            ? 'Pedido de referência'
            : 'Origem não disponível'}</span>
      </div>
      <span>Entregador: {parada.entregadorCodigo}</span>
      <span>Viagem {parada.viagemNumero} · Parada {parada.ordem}</span>
      <span>Bairro: {parada.bairro}</span>
      <span>Status: {textoSituacao(parada.status)}</span>
      {parada.atrasada && <span className="mapa-rotas__pedido-atrasado">Entrega atrasada</span>}
    </div>
  )
}

function MapaRotas({
  rotas,
  simulacao = null,
  snapshotPedidos = [],
  snapshotPedidosCarregando = false,
  estadoAutoritativo = true,
}) {
  if (!rotas) {
    return (
      <section className="mapa-rotas" aria-live="polite">
        <h2>Mapa das rotas</h2>
        <p className="mapa-rotas__mensagem">Aguardando o planejamento das rotas.</p>
      </section>
    )
  }

  const viagens = listarViagens(rotas)
  const marcadoresParadas = snapshotPedidosCarregando
    ? []
    : prepararMarcadores(rotas, snapshotPedidos)
  const entregadores = resumoEntregadores(rotas)
  const centro = rotas.centro
  const centroInicial = centro
    ? [centro.latitude, centro.longitude]
    : CENTRO_SALVADOR

  return (
    <section className="mapa-rotas" aria-label="Mapa das rotas da simulação">
      <div className="mapa-rotas__cabecalho">
        <div>
          <h2>Mapa das rotas</h2>
          <p>Trajetos e paradas retornados pelo planejamento da simulação.</p>
        </div>
      </div>

      {entregadores.length > 0 && (
        <ul className="mapa-rotas__legenda" aria-label="Legenda de entregadores">
          {entregadores.map(({ codigo, cor }) => (
            <li key={codigo}>
              <span className="mapa-rotas__amostra-cor" style={{ backgroundColor: cor }} aria-hidden="true" />
              <span>{codigo}</span>
            </li>
          ))}
        </ul>
      )}

      {viagens.length === 0 && (
        <p className="mapa-rotas__mensagem">Ainda não há viagens planejadas para exibir.</p>
      )}

      {(rotas.nao_atribuidos ?? []).length > 0 && (
        <p className="mapa-rotas__aviso" role="status">
          {rotas.nao_atribuidos.length} pedido(s) não atribuído(s). Não há localização de rota para esses pedidos.
        </p>
      )}

      {snapshotPedidosCarregando && (
        <p className="mapa-rotas__mensagem" role="status">
          Carregando a identificação dos pedidos desta simulação.
        </p>
      )}

      <div className="mapa-rotas__mapa" role="region" aria-label="Mapa interativo de Salvador">
        <MapContainer center={centroInicial} zoom={12} scrollWheelZoom className="mapa-rotas__leaflet">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <AjustarEnquadramento rotas={rotas} />

          {centro && (
            <Marker position={[centro.latitude, centro.longitude]} icon={obterIconeCentro()}>
              <Popup>
                <strong>Centro de distribuição</strong>
                <br />
                {centro.nome}
              </Popup>
            </Marker>
          )}

          {viagens.map(({ entregadorCodigo, viagem, cor }) => {
            const classeSituacao = classeSituacaoViagem(viagem.situacao)
            const estilo = {
              color: cor,
              weight: classeSituacao === 'em-andamento' ? 6 : 4,
              opacity: classeSituacao === 'concluida' ? 0.62 : 0.88,
              dashArray: classeSituacao === 'outra' ? '8 8' : undefined,
            }

            return (
              <FeatureGroup key={`${entregadorCodigo}-${viagem.numero}`}>
                {viagem.caminho?.length > 0 && (
                  <Polyline
                    positions={viagem.caminho}
                    pathOptions={estilo}
                    className={`mapa-rotas__linha mapa-rotas__linha--${classeSituacao}`}
                  >
                    <Popup>
                      <strong>{entregadorCodigo} — Viagem {viagem.numero}</strong>
                      <br />
                      Situação: {textoSituacao(viagem.situacao)}
                    </Popup>
                  </Polyline>
                )}

              </FeatureGroup>
            )
          })}

          {marcadoresParadas.map((parada) => (
            <Marker
              key={parada.chave}
              position={parada.position}
              icon={obterIconeParada(parada.rotulo, parada.status, parada.deslocamento)}
              title={`${parada.rotulo}: ${parada.origem === 'manual' ? 'pedido manual' : parada.origem === 'referencia' ? 'pedido de referência' : 'origem não disponível'} · ${parada.entregadorCodigo} · Viagem ${parada.viagemNumero}`}
            >
              <Popup>
                <InformacoesPedidoParada parada={parada} />
              </Popup>
            </Marker>
          ))}

          {simulacao && rotas && (
            <VeiculosAnimados
              key={`veiculos-${simulacao.id}`}
              simulacao={simulacao}
              rotas={rotas}
              estadoAutoritativo={estadoAutoritativo}
            />
          )}
        </MapContainer>
      </div>
    </section>
  )
}

export default MapaRotas
