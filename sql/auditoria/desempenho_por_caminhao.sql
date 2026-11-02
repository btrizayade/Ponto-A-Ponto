-- Desempenho de cada caminhao em uma simulacao.
-- Parametros: :simulacao_id

SELECT
    e.entregador_codigo,
    SUM(e.tipo = 'viagem_concluida') AS viagens_concluidas,
    SUM(e.tipo = 'viagem_cancelada') AS viagens_canceladas,
    SUM(e.tipo = 'pedido_entregue') AS pedidos_entregues,
    SUM(e.tipo = 'pedido_entregue' AND e.atraso_min > 0) AS pedidos_atrasados,
    ROUND(
        COALESCE(
            SUM(CASE WHEN e.tipo = 'viagem_concluida' THEN e.distancia_m END),
            0
        ) / 1000.0,
        1
    ) AS distancia_km,
    MIN(CASE WHEN e.tipo = 'viagem_iniciada' THEN e.instante END)
        AS primeira_saida,
    MAX(CASE WHEN e.tipo = 'viagem_concluida' THEN e.instante END)
        AS ultimo_retorno
FROM eventos_simulacao AS e
WHERE e.simulacao_id = :simulacao_id
  AND e.entregador_codigo IS NOT NULL
GROUP BY e.entregador_codigo
ORDER BY e.entregador_codigo;
