import boto3
import json
import logging
import os
from decimal import Decimal

logger = logging.getLogger(__name__)

env_name = os.getenv("ENV", "local").lower()
endpoint_url = os.getenv("SQS_ENDPOINT") or os.getenv("AWS_ENDPOINT")

sqs_kwargs = {
    "region_name": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
}
if env_name == "local" and endpoint_url:
    sqs_kwargs["endpoint_url"] = endpoint_url
    sqs_kwargs["aws_access_key_id"] = "test"
    sqs_kwargs["aws_secret_access_key"] = "test"

sqs = boto3.client("sqs", **sqs_kwargs)

BATCH_SIZE   = int(os.getenv("SQS_BATCH_SIZE", "10"))  # máx 10 por chamada no SQS
WAIT_SECONDS = int(os.getenv("SQS_WAIT_SECONDS", "5")) # long polling

_resolved_queue_url = None

def get_queue_url() -> str:
    global _resolved_queue_url
    if _resolved_queue_url:
        return _resolved_queue_url

    queue_url = os.getenv("SQS_QUEUE_URL")
    if queue_url:
        _resolved_queue_url = queue_url
        return queue_url

    try:
        resp = sqs.get_queue_url(QueueName="courier-locations")
        _resolved_queue_url = resp["QueueUrl"]
        return _resolved_queue_url
    except Exception as e:
        logger.warning(f"Could not resolve SQS queue URL by name: {e}")

    # Fallback to localstack URL structure if endpoint exists
    endpoint = os.getenv("SQS_ENDPOINT") or os.getenv("AWS_ENDPOINT")
    if endpoint:
        return f"{endpoint}/000000000000/courier-locations"
    return ""


def receive_batch() -> list[dict]:
    queue_url = get_queue_url()
    if not queue_url:
        logger.error("SQS queue URL is not set/resolved, cannot receive messages.")
        return []
    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=BATCH_SIZE,
        WaitTimeSeconds=WAIT_SECONDS,
    )
    return response.get("Messages", [])


def delete_batch(messages: list[dict]):
    if not messages:
        return
    queue_url = get_queue_url()
    if not queue_url:
        logger.error("SQS queue URL is not set/resolved, cannot delete messages.")
        return
    sqs.delete_message_batch(
        QueueUrl=queue_url,
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