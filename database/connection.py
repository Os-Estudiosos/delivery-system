import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from deploy import get_resource_and_client
from database.dynamo_table import table_exists, create_table, TABLE_NAME

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