import boto3
import os
from decimal import Decimal
from botocore.exceptions import ClientError

# DynamoDB client and resource configuration
endpoint_url = os.getenv("DYNAMODB_ENDPOINT")
region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

dynamodb_kwargs = {"region_name": region_name}
if endpoint_url:
    dynamodb_kwargs["endpoint_url"] = endpoint_url
    dynamodb_kwargs["aws_access_key_id"] = "test"
    dynamodb_kwargs["aws_secret_access_key"] = "test"

dynamodb = boto3.resource("dynamodb", **dynamodb_kwargs)
table = dynamodb.Table("courier_positions")


def create_table_if_not_exists():
    try:
        # Check if table exists
        dynamodb.meta.client.describe_table(TableName="courier_positions")
        print("[DDB] Table 'courier_positions' already exists.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            print("[DDB] Table 'courier_positions' not found, creating...")
            try:
                new_table = dynamodb.create_table(
                    TableName="courier_positions",
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
                new_table.wait_until_exists()
                print("[DDB] Table 'courier_positions' created successfully.")
            except Exception as create_err:
                print(f"[DDB] Error creating table: {create_err}")
        else:
            print(f"[DDB] Describe table error: {e}")


def _to_decimal(value):
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def upsert_positions(positions: list[dict]):
    with table.batch_writer() as batch:
        for pos in positions:
            timestamp = pos["timestamp"]
            if not isinstance(timestamp, str):
                timestamp = str(timestamp)
                
            item = {
                "courier_id":  _to_decimal(pos["courier_id"]),
                "lat":         _to_decimal(pos["lat"]),
                "lng":         _to_decimal(pos["lng"]),
                "timestamp":   timestamp,
            }
            if "delivery_id" in pos and pos["delivery_id"]:
                item["delivery_id"] = str(pos["delivery_id"])
                
            batch.put_item(Item=item)