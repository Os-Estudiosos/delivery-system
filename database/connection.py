import os
import boto3
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

from database.dynamo_table import table_exists, create_table, TABLE_NAME
from database.create_graph import load_graph_cache, download_graph, save_graph_cache
from pathlib import Path
from utils.aws_credentials import configure_local_aws_credentials

configure_local_aws_credentials()
load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET")

def get_resource_and_client():
    session = boto3.Session(region_name=REGION)
    return session.resource("dynamodb"), session.client("dynamodb")

# Conexão com o RDS (usando .get para evitar Crash se a variável não existir no .env local)
_DB_USER = os.environ.get('DB_USER', 'postgres')
_DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres_admin_pwd')
_DB_HOST = os.environ.get('DB_HOST', 'localhost')
_DB_PORT = os.environ.get('DB_PORT', '5432')
_DB_NAME = os.environ.get('DB_NAME', 'dijkfood')

_DB_URL = f"postgresql+psycopg2://{_DB_USER}:{_DB_PASSWORD}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"

engine = create_engine(_DB_URL, echo=False, pool_size=100, max_overflow=200)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# DynamoDB
ddb_resource, ddb_client = get_resource_and_client()

def initialize_dynamo_table() -> None:
    if not table_exists(ddb_client):
        create_table(ddb_resource)

def get_session_dynamo():
    table = ddb_resource.Table(TABLE_NAME)
    try:
        yield table
    finally:
        pass

# --- LÓGICA DO GRAFO (S3) ---
def get_or_download_graph():
    graph_cache_path = Path("cache/cache_graph.graphml")
    graph_cache_path.parent.mkdir(exist_ok=True) # Garante que a pasta cache existe

    # 1. Tenta carregar local
    graph_obj = load_graph_cache(graph_cache_path)
    if graph_obj is not None:
        return graph_obj

    # 2. Se não tem local, tenta baixar do S3 (Muito mais rápido no ECS)
    if S3_BUCKET:
        s3 = boto3.client('s3', region_name=REGION)
        try:
            print(f"Baixando grafo do S3 ({S3_BUCKET})...")
            s3.download_file(S3_BUCKET, 'cache_graph.graphml', str(graph_cache_path))
            return load_graph_cache(graph_cache_path)
        except Exception as e:
            print(f"Grafo não encontrado no S3 ou erro ao baixar: {e}")

    # 3. Se não tem no S3 (ou rodando local pela 1ª vez), baixa do OSMnx e salva
    print("Baixando grafo do OpenStreetMap (Isso pode demorar)...")
    graph_obj = download_graph("São Paulo, Brazil", "drive")
    save_graph_cache(graph_obj, graph_cache_path)
    
    # Faz o upload pro S3 para os próximos containers usarem
    if S3_BUCKET:
        s3 = boto3.client('s3', region_name=REGION)
        try:
            s3.upload_file(str(graph_cache_path), S3_BUCKET, 'cache_graph.graphml')
            print("Grafo salvo no S3 para cache futuro!")
        except Exception as e:
            print(f"Aviso: Não foi possível salvar no S3: {e}")
            
    return graph_obj

# Inicializa o grafo no momento que o app sobe
graph = get_or_download_graph()

def get_graph():
    yield graph