import os
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

load_dotenv()


# AWS Configs
REGION     = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMO_TABLE_NAME", "dynamo-dijsktra-food")
GSI_TYPE   = "gsi-type"
GSI_STATUS = "gsi-status"
N_COURIERS = 500
N_ITEMS    = 100


def get_resource_and_client():
    """Initialize AWS resources with credentials from environment."""
    session = boto3.Session(
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    return session.resource("dynamodb"), session.client("dynamodb")

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