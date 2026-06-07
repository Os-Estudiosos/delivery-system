"""
etl_rds_to_s3.py — Glue Job ETL: RDS PostgreSQL → S3 Parquet
=============================================================
Lê as tabelas do dijkfood do RDS e escreve Parquet particionado
no data lake S3, pronto para consulta via Athena.

Particionamento:
  analytics/orders/        year=YYYY/month=MM/day=DD/
  analytics/events/        year=YYYY/month=MM/day=DD/
  analytics/restaurants/   (sem partição — tabela pequena/estática)
  analytics/users/         region_id=N/
  analytics/couriers/      region_id=N/
  analytics/regions/       (sem partição)
  analytics/kitchen_types/ (sem partição)
  analytics/items/         restaurant_id=N/
  analytics/deliveries/    (sem partição — join pequeno)

Argumentos (passados pelo Glue via --default_arguments):
  --DATA_LAKE_BUCKET   nome do bucket S3 (sem s3://)
  --RDS_JDBC_URL       jdbc:postgresql://<host>:5432/dijkfood
  --RDS_USERNAME       usuário do RDS
  --RDS_PASSWORD       senha do RDS
  --GLUE_DB_NAME       nome do database no Glue Catalog
  --GLUE_CONNECTION    nome da Glue Connection JDBC
"""

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import TimestampType
import logging

# ── logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
logger.addHandler(handler)

# ── args ──────────────────────────────────────────────────────────────────────
args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "DATA_LAKE_BUCKET",
    "RDS_JDBC_URL",
    "RDS_USERNAME",
    "RDS_PASSWORD",
    "GLUE_DB_NAME",
    "GLUE_CONNECTION",
])

BUCKET        = args["DATA_LAKE_BUCKET"]
JDBC_URL      = args["RDS_JDBC_URL"]
DB_USER       = args["RDS_USERNAME"]
DB_PASS       = args["RDS_PASSWORD"]
GLUE_DB       = args["GLUE_DB_NAME"]
GLUE_CONN     = args["GLUE_CONNECTION"]
S3_BASE       = f"s3://{BUCKET}/analytics"

# ── contexto Glue / Spark ─────────────────────────────────────────────────────
sc          = SparkContext()
glueContext = GlueContext(sc)
spark       = glueContext.spark_session
job         = Job(glueContext)
job.init(args["JOB_NAME"], args)

# ── helpers ───────────────────────────────────────────────────────────────────
JDBC_OPTS = {
    "url":      JDBC_URL,
    "user":     DB_USER,
    "password": DB_PASS,
    "driver":   "org.postgresql.Driver",
}


def read_table(table: str):
    """Lê uma tabela inteira do RDS via JDBC."""
    logger.info(f"📥  Lendo tabela: {table}")
    return (
        spark.read
        .format("jdbc")
        .options(**JDBC_OPTS, dbtable=table)
        .load()
    )


def read_query(query: str, alias: str):
    """Lê o resultado de uma query via JDBC (subquery)."""
    logger.info(f"📥  Lendo query: {alias}")
    return (
        spark.read
        .format("jdbc")
        .options(**JDBC_OPTS, dbtable=f"({query}) AS {alias}")
        .load()
    )


def write_parquet(df, path: str, partition_cols: list = None):
    """Escreve DataFrame como Parquet no S3, sobrescrevendo a partição."""
    logger.info(f"📤  Escrevendo: {path}  partições={partition_cols}")
    writer = df.write.mode("overwrite").format("parquet")
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.save(path)
    logger.info(f"✅  Concluído: {path}")


def update_catalog(table_name: str, s3_path: str, partition_cols: list = None):
    """
    Registra/atualiza a tabela no Glue Catalog via DynamicFrame.
    O Crawler fará isso automaticamente depois, mas registrar aqui
    garante disponibilidade imediata no Athena.
    """
    try:
        dyf = glueContext.create_dynamic_frame.from_options(
            connection_type="s3",
            connection_options={"path": s3_path, "recurse": True},
            format="parquet",
        )
        sink = glueContext.getSink(
            connection_type="s3",
            path=s3_path,
            enableUpdateCatalog=True,
            updateBehavior="UPDATE_IN_DATABASE",
            partitionKeys=partition_cols or [],
        )
        sink.setCatalogInfo(catalogDatabase=GLUE_DB, catalogTableName=table_name)
        sink.setFormat("glueparquet", compression="snappy")
        sink.writeFrame(dyf)
        logger.info(f"📚  Catálogo atualizado: {GLUE_DB}.{table_name}")
    except Exception as e:
        logger.warning(f"⚠️  Falha ao atualizar catálogo para {table_name}: {e}")


# =============================================================================
# EXTRAÇÃO E CARGA
# =============================================================================

# ── 1. Tabelas de referência (pequenas, sem partição) ─────────────────────────
logger.info("=" * 60)
logger.info("1/9  Tabelas de referência")
logger.info("=" * 60)

df_regions = read_table("region")
write_parquet(df_regions, f"{S3_BASE}/regions/")

df_kitchen = read_table("kitchen_type")
write_parquet(df_kitchen, f"{S3_BASE}/kitchen_types/")

# ── 2. Restaurantes (particionado por region_id) ──────────────────────────────
logger.info("=" * 60)
logger.info("2/9  Restaurantes")
logger.info("=" * 60)

df_restaurants = read_table("restaurant")
write_parquet(df_restaurants, f"{S3_BASE}/restaurants/", partition_cols=["region_id"])

# ── 3. Itens (particionado por restaurant_id) ─────────────────────────────────
logger.info("=" * 60)
logger.info("3/9  Itens")
logger.info("=" * 60)

df_items = read_table("item")
write_parquet(df_items, f"{S3_BASE}/items/", partition_cols=["restaurant_id"])

# ── 4. Usuários (particionado por region_id) ──────────────────────────────────
logger.info("=" * 60)
logger.info("4/9  Usuários")
logger.info("=" * 60)

df_users = (
    read_table("users")
    .drop("house_lat", "house_lon")  # PII — não vai para o data lake
)
write_parquet(df_users, f"{S3_BASE}/users/", partition_cols=["region_id"])

# ── 5. Entregadores (particionado por region_id) ──────────────────────────────
logger.info("=" * 60)
logger.info("5/9  Entregadores")
logger.info("=" * 60)

df_couriers = (
    read_table("courier")
    .drop("lat", "lon")  # localização em tempo real fica no DynamoDB
)
write_parquet(df_couriers, f"{S3_BASE}/couriers/", partition_cols=["region_id"])

# ── 6. Pedidos (particionado por year/month/day) ──────────────────────────────
logger.info("=" * 60)
logger.info("6/9  Pedidos")
logger.info("=" * 60)

df_orders = (
    read_table("orders")
    .withColumn("created_at", F.col("created_at").cast(TimestampType()))
    .withColumn("year",  F.year("created_at").cast("string"))
    .withColumn("month", F.lpad(F.month("created_at").cast("string"), 2, "0"))
    .withColumn("day",   F.lpad(F.dayofmonth("created_at").cast("string"), 2, "0"))
)
write_parquet(
    df_orders,
    f"{S3_BASE}/orders/",
    partition_cols=["year", "month", "day"],
)

# ── 7. Itens de pedido ────────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("7/9  Itens de pedido")
logger.info("=" * 60)

df_order_items = read_table("order_item")
write_parquet(df_order_items, f"{S3_BASE}/order_items/")

# ── 8. Entregas ───────────────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("8/9  Entregas")
logger.info("=" * 60)

df_deliveries = read_table("delivery")
write_parquet(df_deliveries, f"{S3_BASE}/deliveries/")

# ── 9. Eventos (particionado por year/month/day via updated_at) ───────────────
logger.info("=" * 60)
logger.info("9/9  Eventos")
logger.info("=" * 60)

df_events = (
    read_table("event")
    .withColumn("updated_at", F.col("updated_at").cast(TimestampType()))
    .withColumn("year",  F.year("updated_at").cast("string"))
    .withColumn("month", F.lpad(F.month("updated_at").cast("string"), 2, "0"))
    .withColumn("day",   F.lpad(F.dayofmonth("updated_at").cast("string"), 2, "0"))
)
write_parquet(
    df_events,
    f"{S3_BASE}/events/",
    partition_cols=["year", "month", "day"],
)

# ── Commit do Job ─────────────────────────────────────────────────────────────
logger.info("=" * 60)
logger.info("🎉  ETL concluído com sucesso!")
logger.info(f"    Bucket: s3://{BUCKET}/analytics/")
logger.info(f"    Tabelas: regions, kitchen_types, restaurants, items,")
logger.info(f"             users, couriers, orders, order_items,")
logger.info(f"             deliveries, events")
logger.info("=" * 60)

job.commit()