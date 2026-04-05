import os
from dotenv import load_dotenv
from osmnx import graph
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from deploy import get_resource_and_client
from database.dynamo_table import table_exists, create_table, TABLE_NAME
from database.create_graph import load_graph_cache, download_graph, save_graph_cache
from pathlib import Path

load_dotenv()


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


def get_session_dynamo():

    if not table_exists(ddb_client):
        create_table(ddb_resource)
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
    return graph