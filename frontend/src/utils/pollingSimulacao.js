const intervaloConfigurado = Number(
  import.meta.env?.VITE_INTERVALO_ATUALIZACAO_SIMULACAO_MS || 100
)

export const INTERVALO_ATUALIZACAO_SIMULACAO_MS = Number.isFinite(intervaloConfigurado)
  && intervaloConfigurado > 0
  ? intervaloConfigurado
  : 100
