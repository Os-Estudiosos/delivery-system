import boto3
import json
import logging
import os
from decimal import Decimal

logger = logging.getLogger(__name__)

sqs = boto3.client(
    "sqs",
    endpoint_url=os.getenv("SQS_ENDPOINT"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
)

QUEUE_URL    = os.getenv("SQS_QUEUE_URL")
BATCH_SIZE   = int(os.getenv("SQS_BATCH_SIZE", "10"))  # máx 10 por chamada no SQS
WAIT_SECONDS = int(os.getenv("SQS_WAIT_SECONDS", "5")) # long polling


def receive_batch() -> list[dict]:
    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=BATCH_SIZE,
        WaitTimeSeconds=WAIT_SECONDS,
    )
    return response.get("Messages", [])


def delete_batch(messages: list[dict]):
    if not messages:
        return
    sqs.delete_message_batch(
        QueueUrl=QUEUE_URL,
        Entries=[
            {"Id": m["MessageId"], "ReceiptHandle": m["ReceiptHandle"]}
            for m in messages
        ],
    )


def deduplicate(messages: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for msg in messages:
        body = json.loads(msg["Body"], parse_float=Decimal)
        cid  = body["courier_id"]
        if cid not in latest or body["timestamp"] > latest[cid]["timestamp"]:
            latest[cid] = body
    return list(latest.values())