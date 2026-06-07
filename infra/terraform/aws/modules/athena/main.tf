terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ── Bucket dedicado para resultados do Athena ─────────────────────────────────
resource "aws_s3_bucket" "athena_results" {
  bucket        = var.athena_results_bucket
  force_destroy = true

  tags = var.common_tags
}

resource "aws_s3_bucket_ownership_controls" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    id     = "expire-query-results"
    status = "Enabled"

    filter { prefix = "" }

    expiration {
      days = 30
    }
  }
}

# ── Workgroup ─────────────────────────────────────────────────────────────────
resource "aws_athena_workgroup" "dijkfood" {
  name        = var.workgroup_name
  description = "Workgroup analítico do dijkfood"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/query-results/"
    }

    engine_version {
      selected_engine_version = "Athena engine version 3"
    }

    bytes_scanned_cutoff_per_query = var.bytes_scanned_limit
  }

  tags = var.common_tags
}

# ── Named Queries (os 6 indicadores do dashboard) ─────────────────────────────
resource "aws_athena_named_query" "volume_pedidos" {
  name      = "01_volume_pedidos_no_tempo"
  workgroup = aws_athena_workgroup.dijkfood.name
  database  = var.glue_db_name
  description = "Volume diário de pedidos"

  query = <<-SQL
    SELECT
        DATE(created_at) AS dia,
        COUNT(*)         AS total_pedidos
    FROM orders
    GROUP BY DATE(created_at)
    ORDER BY dia;
  SQL
}

resource "aws_athena_named_query" "tempo_por_estado" {
  name      = "02_tempo_medio_por_estado"
  workgroup = aws_athena_workgroup.dijkfood.name
  database  = var.glue_db_name
  description = "Tempo médio em minutos em cada estado do ciclo de vida"

  query = <<-SQL
    WITH eventos_com_anterior AS (
        SELECT
            status,
            updated_at,
            LAG(updated_at) OVER (
                PARTITION BY delivery_id
                ORDER BY updated_at
            ) AS ts_anterior
        FROM event
    )
    SELECT
        status,
        ROUND(AVG(date_diff('second', ts_anterior, updated_at)) / 60.0, 2) AS tempo_medio_minutos
    FROM eventos_com_anterior
    WHERE ts_anterior IS NOT NULL
    GROUP BY status
    ORDER BY MIN(updated_at);
  SQL
}

resource "aws_athena_named_query" "distribuicao_regiao" {
  name      = "03_distribuicao_por_regiao"
  workgroup = aws_athena_workgroup.dijkfood.name
  database  = var.glue_db_name
  description = "Distribuição de pedidos por região"

  query = <<-SQL
    SELECT
        r.name                                                        AS regiao,
        COUNT(o.id)                                                   AS total_pedidos,
        ROUND(COUNT(o.id) * 100.0 / SUM(COUNT(o.id)) OVER (), 2)    AS percentual
    FROM orders o
    JOIN users  u ON u.id = o.user_id
    JOIN region r ON r.id = u.region_id
    GROUP BY r.name
    ORDER BY total_pedidos DESC;
  SQL
}

resource "aws_athena_named_query" "heatmap_demanda" {
  name      = "04_heatmap_horario_dia_semana"
  workgroup = aws_athena_workgroup.dijkfood.name
  database  = var.glue_db_name
  description = "Heatmap de demanda por horário e dia da semana"

  query = <<-SQL
    SELECT
        day_of_week(created_at)  AS dow_ordem,
        hour(created_at)         AS hora,
        COUNT(*)                 AS total_pedidos
    FROM orders
    GROUP BY day_of_week(created_at), hour(created_at)
    ORDER BY dow_ordem, hora;
  SQL
}

resource "aws_athena_named_query" "top10_restaurantes" {
  name      = "05_top10_restaurantes"
  workgroup = aws_athena_workgroup.dijkfood.name
  database  = var.glue_db_name
  description = "Top 10 restaurantes por volume de pedidos"

  query = <<-SQL
    SELECT
        r.name      AS restaurante,
        reg.name    AS regiao,
        kt.type     AS cozinha,
        COUNT(o.id) AS total_pedidos
    FROM orders o
    JOIN restaurant   r   ON r.id   = o.restaurant_id
    JOIN region       reg ON reg.id = r.region_id
    JOIN kitchen_type kt  ON kt.id  = r.kitchen_type_id
    GROUP BY r.name, reg.name, kt.type
    ORDER BY total_pedidos DESC
    LIMIT 10;
  SQL
}

resource "aws_athena_named_query" "histograma_entrega" {
  name      = "06_histograma_tempo_entrega"
  workgroup = aws_athena_workgroup.dijkfood.name
  database  = var.glue_db_name
  description = "Histograma do tempo total de entrega em buckets de 10 min"

  query = <<-SQL
    WITH tempos AS (
        SELECT
            d.id AS delivery_id,
            MIN(CASE WHEN e.status = 'CONFIRMED' THEN e.updated_at END) AS ts_confirmed,
            MAX(CASE WHEN e.status = 'DELIVERED' THEN e.updated_at END) AS ts_delivered
        FROM delivery d
        JOIN event e ON e.delivery_id = d.id
        GROUP BY d.id
        HAVING
            MIN(CASE WHEN e.status = 'CONFIRMED' THEN e.updated_at END) IS NOT NULL
            AND MAX(CASE WHEN e.status = 'DELIVERED' THEN e.updated_at END) IS NOT NULL
    ),
    duracoes AS (
        SELECT
            CAST(date_diff('minute', ts_confirmed, ts_delivered) AS INTEGER) AS minutos
        FROM tempos
    )
    SELECT
        (minutos / 10) * 10      AS bucket_inicio,
        (minutos / 10) * 10 + 9  AS bucket_fim,
        COUNT(*)                 AS total_entregas
    FROM duracoes
    GROUP BY (minutos / 10) * 10
    ORDER BY bucket_inicio;
  SQL
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "workgroup_name" {
  value = aws_athena_workgroup.dijkfood.name
}

output "athena_results_bucket" {
  value = aws_s3_bucket.athena_results.bucket
}

output "glue_db_name" {
  value = var.glue_db_name
}
