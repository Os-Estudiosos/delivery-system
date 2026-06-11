import os
import json
import datetime
import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from boto3.dynamodb.conditions import Key

from shared.database.connection import get_session
from shared.database.models import Courier, VehicleType, Region

router = APIRouter(prefix="/courier", tags=["courier"]) 

# Env config
ENV = os.environ.get("ENV", "local").lower()
AWS_ENDPOINT = os.environ.get("AWS_ENDPOINT") or os.environ.get("LOCALSTACK_ENDPOINT")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
REGION_ID = int(os.environ.get("REGION_ID", "1"))

# SQS client setup
sqs_kwargs = {"region_name": AWS_REGION}
if ENV == "local" and AWS_ENDPOINT:
    sqs_kwargs["endpoint_url"] = AWS_ENDPOINT
    sqs_kwargs["aws_access_key_id"] = "test"
    sqs_kwargs["aws_secret_access_key"] = "test"

sqs_client = boto3.client("sqs", **sqs_kwargs)

# DynamoDB setup
dynamodb_kwargs = {"region_name": AWS_REGION}
if ENV == "local" and AWS_ENDPOINT:
    dynamodb_kwargs["endpoint_url"] = AWS_ENDPOINT
    dynamodb_kwargs["aws_access_key_id"] = "test"
    dynamodb_kwargs["aws_secret_access_key"] = "test"

dynamodb_resource = boto3.resource("dynamodb", **dynamodb_kwargs)
dynamodb_table = dynamodb_resource.Table("courier_positions")

# Helper to get SQS Queue URL
def get_queue_url():
    queue_url = os.environ.get("SQS_QUEUE_URL")
    if queue_url:
        return queue_url
    try:
        resp = sqs_client.get_queue_url(QueueName="courier-locations")
        return resp["QueueUrl"]
    except Exception:
        if AWS_ENDPOINT:
            return f"{AWS_ENDPOINT}/000000000000/courier-locations"
        return ""


# -------------------- Schemas --------------------
class CourierCreate(BaseModel):
    name: str
    vehicle: str
    lat: float
    lon: float
    region_id: int | None = None


class CourierUpdate(BaseModel):
    name: str | None = None
    vehicle: str | None = None
    lat: float | None = None
    lon: float | None = None
    region_id: int | None = None


class CourierResponse(BaseModel):
    id: int
    name: str
    vehicle: str
    lat: float
    lon: float
    region_id: int


class CourierPositionUpdate(BaseModel):
    delivery_id: str
    lat_courier: float
    lon_courier: float


class CourierLocationResponse(BaseModel):
    courier_id: int
    delivery_id: str
    lat_courier: float
    lon_courier: float
    timestamp: str


def list_couriers(session: Session) -> list[Courier]:
    return session.query(Courier).all()


def get_courier(session: Session, courier_id: int) -> Courier | None:
    return session.query(Courier).filter(Courier.id == courier_id).first()


def create_courier(session: Session, *, name: str, vehicle: str, lat: float, lon: float, region_id: int | None = None) -> Courier:
    if region_id is None:
        region_id = REGION_ID

    # ensure region exists
    region = session.query(Region).filter(Region.id == region_id).first()
    if not region:
        return None

    v = VehicleType(vehicle)
    db_courier = Courier(name=name, vehicle=v, lat=lat, lon=lon, region_id=region_id)
    session.add(db_courier)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise
    session.refresh(db_courier)
    return db_courier


def update_courier(session: Session, courier: Courier, *, name: str | None = None, vehicle: str | None = None, lat: float | None = None, lon: float | None = None, region_id: int | None = None) -> Courier:
    if region_id is not None:
        region = session.query(Region).filter(Region.id == region_id).first()
        if not region:
            return None
        courier.region_id = region_id

    if name is not None:
        courier.name = name
    if vehicle is not None:
        courier.vehicle = VehicleType(vehicle)
    if lat is not None:
        courier.lat = lat
    if lon is not None:
        courier.lon = lon

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise

    session.refresh(courier)
    return courier


def delete_courier(session: Session, courier: Courier) -> None:
    session.delete(courier)
    session.commit()


# -------------------- Helpers --------------------
def _to_response(c: Courier) -> CourierResponse:
    return CourierResponse(
        id=c.id,
        name=c.name,
        vehicle=c.vehicle.value if isinstance(c.vehicle, VehicleType) else str(c.vehicle),
        lat=c.lat,
        lon=c.lon,
        region_id=c.region_id or REGION_ID,
    )


def _get_or_404(courier_id: int, session: Session) -> Courier:
    db_courier = get_courier(session, courier_id)
    if not db_courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found.")
    return db_courier


# -------------------- Endpoints --------------------
@router.get("/", response_model=list[CourierResponse])
def list_all(session: Session = Depends(get_session)):
    return [_to_response(c) for c in list_couriers(session)]


@router.get("/{courier_id}", response_model=CourierResponse)
def get_one(courier_id: int, session: Session = Depends(get_session)):
    c = _get_or_404(courier_id, session)
    return _to_response(c)


@router.post("/", response_model=CourierResponse, status_code=status.HTTP_201_CREATED)
def create(courier: CourierCreate, session: Session = Depends(get_session)):
    db_c = create_courier(
        session,
        name=courier.name,
        vehicle=courier.vehicle,
        lat=courier.lat,
        lon=courier.lon,
        region_id=courier.region_id,
    )
    if db_c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(db_c)


@router.patch("/{courier_id}", response_model=CourierResponse)
def patch(courier_id: int, courier: CourierUpdate, session: Session = Depends(get_session)):
    db_c = _get_or_404(courier_id, session)
    updated = update_courier(
        session,
        db_c,
        name=courier.name,
        vehicle=courier.vehicle,
        lat=courier.lat,
        lon=courier.lon,
        region_id=courier.region_id,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(updated)


@router.delete("/{courier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(courier_id: int, session: Session = Depends(get_session)):
    db_c = _get_or_404(courier_id, session)
    delete_courier(session, db_c)


@router.put('/{courier_id}/position', tags=['update courier position'])
def update_courier_position(
    courier_id: int,
    data: CourierPositionUpdate,
    session: Session = Depends(get_session),
):
    _get_or_404(courier_id, session)
    timestamp = datetime.datetime.utcnow().isoformat()
    
    message_body = {
        "courier_id": courier_id,
        "delivery_id": data.delivery_id,
        "lat": data.lat_courier,
        "lng": data.lon_courier,
        "timestamp": timestamp,
    }
    
    queue_url = get_queue_url()
    if queue_url:
        try:
            sqs_client.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message_body)
            )
        except Exception as e:
            print(f"Error sending message to SQS: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error sending message to SQS: {str(e)}"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SQS queue URL could not be resolved"
        )
            
    return {
        "message": "Location updated",
        "timestamp": timestamp,
    }


@router.get('/{courier_id}/location', response_model=CourierLocationResponse)
def get_last_location(courier_id: int, session: Session = Depends(get_session)):
    _get_or_404(courier_id, session)
    try:
        response = dynamodb_table.query(
            KeyConditionExpression=Key("courier_id").eq(courier_id),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying DynamoDB: {str(e)}"
        )

    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Courier location not found.',
        )

    item = items[0]
    return CourierLocationResponse(
        courier_id=int(item["courier_id"]),
        delivery_id=item.get("delivery_id", ""),
        lat_courier=float(item.get("lat") or item.get("lat_courier") or 0.0),
        lon_courier=float(item.get("lng") or item.get("lon_courier") or 0.0),
        timestamp=item["timestamp"],
    )
