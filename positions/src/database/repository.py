import boto3
import os
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource(
    "dynamodb",
    endpoint_url=os.getenv("DYNAMODB_ENDPOINT"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
)

table = dynamodb.Table("courier_positions")


def upsert_positions(positions: list[dict]):
    with table.batch_writer() as batch:
        for pos in positions:
            batch.put_item(Item={
                "courier_id":  pos["courier_id"],
                "lat":         pos["lat"],
                "lng":         pos["lng"],
                "timestamp":   pos["timestamp"],
            })