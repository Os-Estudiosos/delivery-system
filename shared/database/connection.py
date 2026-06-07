import os
from pathlib import Path

import boto3
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# from create_graph import download_graph, load_graph_cache, save_graph_cache

load_dotenv()

# -----------------------------------------------------------------
# Ambiente
# -----------------------------------------------------------------
IS_LOCAL = os.environ.get("ENV", "local").lower() == "local"

REGION     = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET  = os.environ.get("S3_BUCKET")

# LocalStack expõe todos os serviços AWS num único endpoint
LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")

# -----------------------------------------------------------------
# PostgreSQL
# -----------------------------------------------------------------
_DB_URL = "postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}".format(
    user     = os.environ.get("DB_USER",     "postgres"),
    password = os.environ.get("DB_PASSWORD", "postgres"),
    host     = os.environ.get("DB_HOST",     "localhost"),
    port     = os.environ.get("DB_PORT",     "5432"),
    name     = os.environ.get("DB_NAME",     "dijkfood"),
)

engine       = create_engine(_DB_URL, echo=False, pool_size=100, max_overflow=200)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -----------------------------------------------------------------
# boto3 — aponta para LocalStack se ENV=local
# -----------------------------------------------------------------
def _boto3_kwargs() -> dict:
    """Returns extra kwargs so boto3 hits LocalStack when running locally."""
    if not IS_LOCAL:
        return {}
    return {
        "endpoint_url":          LOCALSTACK_ENDPOINT,
        "aws_access_key_id":     "test",
        "aws_secret_access_key": "test",
    }


def get_resource_and_client():
    kwargs  = _boto3_kwargs()
    session = boto3.Session(region_name=REGION)
    return (
        session.resource("dynamodb", **kwargs),
        session.client( "dynamodb", **kwargs),
    )


# -----------------------------------------------------------------
# DynamoDB
# -----------------------------------------------------------------
ddb_resource, ddb_client = get_resource_and_client()



# -----------------------------------------------------------------
# Grafo (S3 / OSMnx)
# -----------------------------------------------------------------
def _s3_client():
    return boto3.client("s3", region_name=REGION, **_boto3_kwargs())


# def get_or_download_graph():
#     graph_cache_path = Path("cache/cache_graph.graphml")
#     graph_cache_path.parent.mkdir(exist_ok=True)

#     # 1. Cache local
#     graph_obj = load_graph_cache(graph_cache_path)
#     if graph_obj is not None:
#         return graph_obj

#     # 2. S3 / LocalStack
#     if S3_BUCKET:
#         s3 = _s3_client()
#         try:
#             print(f"Baixando grafo do S3 ({S3_BUCKET})...")
#             s3.download_file(S3_BUCKET, "cache_graph.graphml", str(graph_cache_path))
#             graph_obj = load_graph_cache(graph_cache_path)
#             if graph_obj is not None:
#                 return graph_obj
#         except Exception as e:
#             print(f"Grafo não encontrado no S3 ou erro ao baixar: {e}")

#     # 3. OpenStreetMap (primeiro boot local)
#     print("Baixando grafo do OpenStreetMap (isso pode demorar)...")
#     graph_obj = download_graph("São Paulo, Brazil", "drive")
#     save_graph_cache(graph_obj, graph_cache_path)

#     if S3_BUCKET:
#         s3 = _s3_client()
#         try:
#             s3.upload_file(str(graph_cache_path), S3_BUCKET, "cache_graph.graphml")
#             print("Grafo salvo no S3 para cache futuro!")
#         except Exception as e:
#             print(f"Aviso: não foi possível salvar no S3: {e}")

#     return graph_obj


# # Grafo inicializado na subida do app
# graph = get_or_download_graph()


# def get_graph():
#     yield graph