-- volume_pedidos_tempo.sql
-- Volume de pedidos agrupados por hora/dia no tempo

SELECT 
    date_trunc('hour', from_iso8601_timestamp(timestamp)) AS order_hour,
    count(distinct order_id) AS total_orders
FROM 
    dijkfood_analytics.events
WHERE 
    status = 'CONFIRMED'
GROUP BY 
    1
ORDER BY 
    1 ASC;
