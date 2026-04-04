from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key

from dynamo.table import get_resource_and_client, create_table, TABLE_NAME

router = APIRouter()

dynamodb, dynamodb_client = get_resource_and_client()
table = dynamodb.Table(TABLE_NAME)


class CourierLocationCreate(BaseModel):
    delivery_id: str
    lat_courier: float
    lon_courier: float


class CourierLocationResponse(BaseModel):
    courier_id: str
    delivery_id: str
    lat_courier: float
    lon_courier: float
    timestamp: str


@router.post("/courier/{courier_id}/location")
def update_location(data: CourierLocationCreate):
    timestamp = datetime.utcnow().isoformat()

    table.put_item(Item={
        "courier_id": data.courier_id,
        "timestamp": timestamp,
        "delivery_id": data.delivery_id,
        "lat_courier": Decimal(str(data.lat_courier)),
        "lon_courier": Decimal(str(data.lon_courier)),
    })

    return {
        "message": "Location updated",
        "timestamp": timestamp
    }

@router.get("/courier/{courier_id}", response_model=CourierLocationResponse)
def get_last_location(courier_id: str):
    response = table.query(
        KeyConditionExpression=Key("courier_id").eq(courier_id),
        ScanIndexForward=False,  # mais recente primeiro
        Limit=1
    )

    items = response.get("Items")

    if not items:
        return {"error": "Courier not found"}

    item = items[0]

    return {
        "courier_id": item["courier_id"],
        "delivery_id": item["delivery_id"],
        "lat_courier": float(item["lat_courier"]),
        "lon_courier": float(item["lon_courier"]),
        "timestamp": item["timestamp"]
    }