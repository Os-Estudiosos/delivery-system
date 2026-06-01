import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

load_dotenv()

# AWS Configs
TABLE_NAME = os.environ.get("DYNAMO_TABLE", "dynamo-dijsktra-food")

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
                {"AttributeName": "courier_id", "AttributeType": "N"},
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

# Destruindo a tabela
def destroy_table(ddb):
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