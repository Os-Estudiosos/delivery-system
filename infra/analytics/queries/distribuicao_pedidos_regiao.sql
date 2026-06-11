-- distribuicao_pedidos_regiao.sql
-- Distribuição de volume de pedidos por região geográfica

SELECT 
    region_id,
    count(distinct order_id) AS total_orders
FROM 
    dijkfood_analytics.events
WHERE 
    status = 'CONFIRMED'
GROUP BY 
    1
ORDER BY 
    2 DESC;
