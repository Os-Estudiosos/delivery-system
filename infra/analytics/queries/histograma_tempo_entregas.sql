-- histograma_tempo_entregas.sql
-- Histograma de tempo total das entregas (tempo total decorrido entre CONFIRMED e DELIVERED) em minutos

WITH delivery_times AS (
  SELECT 
    order_id,
    min(from_iso8601_timestamp(timestamp)) AS confirmed_at,
    max(from_iso8601_timestamp(timestamp)) AS delivered_at,
    date_diff('minute', min(from_iso8601_timestamp(timestamp)), max(from_iso8601_timestamp(timestamp))) AS delivery_duration_minutes
  FROM 
    dijkfood_analytics.events
  WHERE 
    status IN ('CONFIRMED', 'DELIVERED')
  GROUP BY 
    order_id
  HAVING 
    count(distinct status) = 2
)
SELECT 
  (delivery_duration_minutes / 5) * 5 AS duration_bucket_start_mins,
  ((delivery_duration_minutes / 5) * 5) + 5 AS duration_bucket_end_mins,
  count(*) AS total_orders
FROM 
  delivery_times
GROUP BY 
  1, 2
ORDER BY 
  1 ASC;
