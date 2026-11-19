/** Cria um loop RAF idempotente, encerrável e independente do React. */
export function criarLoopAnimacao({ agendarFrame, cancelarFrame, aoFrame }) {
  let ativo = false
  let framePendente = null

  function executar(timestamp) {
    framePendente = null
    if (!ativo) return

    aoFrame(timestamp)
    if (ativo) framePendente = agendarFrame(executar)
  }

  return {
    iniciar() {
      if (ativo) return
      ativo = true
      framePendente = agendarFrame(executar)
    },
    parar() {
      if (!ativo) return
      ativo = false
      if (framePendente !== null) cancelarFrame(framePendente)
      framePendente = null
    },
  }
}
