import os
from dotenv import load_dotenv
import boto3
from database.dynamo_table import *

load_dotenv()




def get_resource_and_client():
    """Initialize AWS resources with credentials from environment."""
    session = boto3.Session(
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )
    return session.resource("dynamodb"), session.client("dynamodb")



if __name__ == "__main__":
    ddb_resource, ddb_client = get_resource_and_client()

    # Destroy existing table (if any)
    destroy_table(ddb_resource)

    # Create new table
    create_table(ddb_resource)