-- Pedidos entregues depois do prazo, do maior para o menor atraso.
-- O atraso e medido na conclusao da entrega, em minutos corridos.
-- Parametros: :simulacao_id

SELECT
    e.pedido_codigo,
    e.entregador_codigo,
    e.viagem_numero,
    e.instante AS concluido_em,
    ROUND(e.atraso_min, 1) AS atraso_min
FROM eventos_simulacao AS e
WHERE e.simulacao_id = :simulacao_id
  AND e.tipo = 'pedido_entregue'
  AND e.atraso_min > 0
ORDER BY e.atraso_min DESC, e.pedido_codigo;
