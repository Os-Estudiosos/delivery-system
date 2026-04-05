import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from deploy import get_resource_and_client, TABLE_NAME
from botocore.exceptions import ClientError

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


def table_exists(client: object) -> bool:

    try:
        client.describe_table(TableName=TABLE_NAME)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def create_table(ddb_resource: object):

    try:
        table = ddb_resource.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "courier_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp",  "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "courier_id", "AttributeType": "S"},
                {"AttributeName": "timestamp",  "AttributeType": "S"},
                {"AttributeName": "delivery_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi-delivery",
                    "KeySchema": [
                        {"AttributeName": "delivery_id", "KeyType": "HASH"},
                        {"AttributeName": "timestamp",   "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        print("[DDB] Table created successfully")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceInUseException":
            print("[DDB] Table already exists")
            table = ddb_resource.Table(TABLE_NAME)
        else:
            raise
    return table


def get_session_dynamo():

    if not table_exists(ddb_client):
        create_table(ddb_resource)
    table = ddb_resource.Table(TABLE_NAME)
    try:
        yield table
    finally:
        pass