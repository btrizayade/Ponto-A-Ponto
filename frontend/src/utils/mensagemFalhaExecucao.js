export function mensagemFalhaExecucao(simulacao) {
  if (simulacao?.estado_execucao !== 'falhou') return null

  return `A execução automática falhou: ${simulacao.erro_execucao || 'consulte os logs do backend.'}`
}
