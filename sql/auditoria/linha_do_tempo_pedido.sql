-- Linha do tempo de um pedido em uma simulacao.
-- Parametros: :simulacao_id, :pedido_codigo

SELECT
    e.sequencia,
    e.instante,
    e.tipo,
    m.status_anterior,
    m.status_novo,
    e.entregador_codigo,
    e.viagem_numero,
    e.atraso_min,
    e.detalhe
FROM eventos_simulacao AS e
LEFT JOIN mudancas_status_pedido AS m ON m.evento_id = e.id
WHERE e.simulacao_id = :simulacao_id
  AND e.pedido_codigo = :pedido_codigo
ORDER BY e.sequencia;
