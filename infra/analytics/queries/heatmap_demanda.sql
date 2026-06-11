-- heatmap_demanda.sql
-- Dados de demanda agregados por dia da semana e hora do dia (Heatmap)

SELECT 
    day_of_week(from_iso8601_timestamp(timestamp)) AS day_of_week_num, -- 1 (Segunda) a 7 (Domingo)
    hour(from_iso8601_timestamp(timestamp)) AS hour_of_day,            -- 0 a 23
    count(distinct order_id) AS total_orders
FROM 
    dijkfood_analytics.events
WHERE 
    status = 'CONFIRMED'
GROUP BY 
    1, 2
ORDER BY 
    1, 2;
