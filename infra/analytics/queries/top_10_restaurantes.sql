-- top_10_restaurantes.sql
-- Os 10 restaurantes com maior volume de pedidos faturados

SELECT 
    restaurant_id,
    count(distinct order_id) AS total_orders
FROM 
    dijkfood_analytics.events
WHERE 
    status = 'CONFIRMED'
GROUP BY 
    1
ORDER BY 
    2 DESC
LIMIT 10;
