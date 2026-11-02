-- Pedidos que terminaram a simulacao sem ser entregues, com o
-- ultimo status e o motivo registrado no ultimo evento.
-- Parametros: :simulacao_id

WITH ultimo_status AS (
    SELECT
        m.pedido_codigo,
        m.status_novo,
        m.evento_id,
        ROW_NUMBER() OVER (
            PARTITION BY m.pedido_codigo
            ORDER BY e.sequencia DESC
        ) AS ordem
    FROM mudancas_status_pedido AS m
    INNER JOIN eventos_simulacao AS e ON e.id = m.evento_id
    WHERE m.simulacao_id = :simulacao_id
),
ultimo_evento AS (
    SELECT
        e.pedido_codigo,
        e.tipo,
        e.detalhe,
        ROW_NUMBER() OVER (
            PARTITION BY e.pedido_codigo
            ORDER BY e.sequencia DESC
        ) AS ordem
    FROM eventos_simulacao AS e
    WHERE e.simulacao_id = :simulacao_id
      AND e.pedido_codigo IS NOT NULL
)
SELECT
    s.pedido_codigo,
    s.status_novo AS status_final,
    u.tipo AS ultimo_evento,
    u.detalhe AS motivo
FROM ultimo_status AS s
INNER JOIN ultimo_evento AS u
    ON u.pedido_codigo = s.pedido_codigo AND u.ordem = 1
WHERE s.ordem = 1
  AND s.status_novo <> 'entregue'
ORDER BY s.pedido_codigo;
