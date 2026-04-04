import random
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError


# AWS Configs
REGION     = "us-east-1"
TABLE_NAME = "dynamo-dijsktra-food"
GSI_TYPE   = "gsi-type"
GSI_STATUS = "gsi-status"
N_COURIERS = 500
N_ITEMS    = 100_000


# ─────────────────────────────────────────────────────────────────────────────
# 1. ALOCAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def get_resource_and_client():

    session = boto3.Session(region_name=REGION)
    return session.resource("dynamodb"), session.client("dynamodb")


def create_table(ddb):
    try:
        table = ddb.create_table(
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
                    # Buscar por entrega específica
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
        print("[DDB] Table active")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceInUseException":
            print("[DDB] Table already exists.")
            table = ddb.Table(TABLE_NAME)
        else:
            raise
    return table


# ─────────────────────────────────────────────────────────────────────────────
# 2. POPULAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def populate(table, n=10000):
    print(f"[DDB] Inserting {n:,} items ...")

    base_ts = datetime.now()

    with table.batch_writer() as batch:
        for i in range(n):
            ts = base_ts + timedelta(seconds=i)

            batch.put_item(Item={
                "courier_id": f"{random.randint(1, 100):04d}",
                "timestamp": ts.isoformat(),
                "delivery_id": f"{random.randint(1, 1000):05d}",
                # Coordenadas aleatórias dentro de um retângulo aproximando a área do Rio de Janeiro
                "lat_courier": Decimal(str(random.uniform(-23.7, -22.8))),
                "lon_courier": Decimal(str(random.uniform(-43.8, -43.1))),
            })


# Destruindo a tabela
def destroy_table(ddb):
    print("\n── Teardown " + "─" * 55)
    print(f"[DDB] Deleting table '{TABLE_NAME}' ...")
    try:
        table = ddb.Table(TABLE_NAME)
        table.delete()
        table.wait_until_not_exists()
        print("[DDB] Table deleted.")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            print("[DDB] Table not found, skipping.")
        else:
            raise