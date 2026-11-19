import { divIcon } from 'leaflet'
import { criarCacheIcones } from './cacheIcones.js'

const obterOuCriar = criarCacheIcones()

export function obterIconeCentro() {
  return obterOuCriar('centro', () => divIcon({
    className: 'mapa-rotas__icone-centro',
    html: '<span aria-hidden="true">CD</span>',
    iconSize: [38, 38],
    iconAnchor: [19, 19],
  }))
}

export function obterIconeParada(rotulo, status, deslocamento = [0, 0]) {
  const estado = String(status ?? 'desconhecido').replace(/[^a-zA-Z0-9_-]/g, '-')
  const valores = [String(rotulo), estado, ...deslocamento]
  const chave = JSON.stringify(['parada', ...valores])

  return obterOuCriar(chave, () => divIcon({
    className: 'mapa-rotas__icone-parada',
    html: `<span class="mapa-rotas__numero status-${estado}">${rotulo}</span>`,
    iconSize: [32, 32],
    iconAnchor: [16 - deslocamento[0], 16 - deslocamento[1]],
  }))
}

export function obterIconeVeiculo(cor) {
  return obterOuCriar(`veiculo:${cor}`, () => divIcon({
    className: 'mapa-rotas__icone-veiculo',
    html: `<span style="--cor-veiculo:${cor}" aria-hidden="true">🚚</span>`,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
  }))
}
