export function criarCacheIcones() {
  const cache = new Map()

  return function obter(chave, criar) {
    if (!cache.has(chave)) cache.set(chave, criar())
    return cache.get(chave)
  }
}
