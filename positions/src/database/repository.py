import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource(
    "dynamodb",
    endpoint_url=os.getenv("DYNAMODB_ENDPOINT"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
)

table = dynamodb.Table("courier_positions")


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
            batch.put_item(Item={
                "courier_id":  _to_decimal(pos["courier_id"]),
                "lat":         _to_decimal(pos["lat"]),
                "lng":         _to_decimal(pos["lng"]),
                "timestamp":   timestamp,
            })