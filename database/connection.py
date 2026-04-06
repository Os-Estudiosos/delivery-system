import os
import boto3
from dotenv import load_dotenv
from osmnx import graph
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.dynamo_table import table_exists, create_table, TABLE_NAME
from database.create_graph import load_graph_cache, download_graph, save_graph_cache
from pathlib import Path
from utils.aws_credentials import configure_local_aws_credentials

configure_local_aws_credentials()
load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")


def get_resource_and_client():
    """Initialize DynamoDB resource/client using local endpoint in development and AWS otherwise."""
    project_env = os.environ.get("PROJECT_ENV", "production").lower()

    if project_env == "development":
        endpoint_url = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8001")
        local_key = os.environ.get("AWS_ACCESS_KEY_ID", "local")
        local_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "local")
        session = boto3.Session(
            region_name=REGION,
            aws_access_key_id=local_key,
            aws_secret_access_key=local_secret,
        )
        return (
            session.resource("dynamodb", endpoint_url=endpoint_url),
            session.client("dynamodb", endpoint_url=endpoint_url),
        )

    session = boto3.Session(
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )
    return session.resource("dynamodb"), session.client("dynamodb")


_DB_URL = (
    "postgresql+psycopg2://"
    f"{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
    f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}"
    f"/{os.environ['DB_NAME']}"
)

engine = create_engine(_DB_URL, echo=False)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Criação da tabela DynamoDB (se necessário)
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


# Criando o grafo pelo OSMnx
graph_cache_path = Path("cache/cache_graph.graphml")

graph = load_graph_cache(graph_cache_path)
if graph is None:
    graph = download_graph("São Paulo, Brazil", "drive")
    save_graph_cache(graph, graph_cache_path)


def get_graph():
    yield graph