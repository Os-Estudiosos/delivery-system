-- tempo_medio_etapas.sql
-- Tempo médio decorrido em segundos em cada transição do ciclo de vida do pedido

WITH event_intervals AS (
  SELECT 
    order_id,
    status,
    from_iso8601_timestamp(timestamp) AS current_time,
    lead(from_iso8601_timestamp(timestamp)) OVER(PARTITION BY order_id ORDER BY timestamp) AS next_time,
    lead(status) OVER(PARTITION BY order_id ORDER BY timestamp) AS next_status
  FROM 
    dijkfood_analytics.events
)
SELECT 
  status AS from_status,
  next_status AS to_status,
  avg(date_diff('second', current_time, next_time)) AS avg_duration_seconds,
  count(*) AS total_transitions
FROM 
  event_intervals
WHERE 
  next_status IS NOT NULL
GROUP BY 
  1, 2
ORDER BY 
  3 DESC;
