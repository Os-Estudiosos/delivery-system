from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key

from database.connection import get_session, get_session_dynamo
from database.models import Courier, VehicleType


router = APIRouter(prefix='/courier', tags=['courier'])


class CourierCreate(BaseModel):
    name: str
    vehicle: VehicleType
    lat: float
    lon: float


class CourierUpdate(BaseModel):
    name: str | None = None
    vehicle: VehicleType | None = None
    lat: float | None = None
    lon: float | None = None


class CourierResponse(BaseModel):
    id: int
    name: str
    vehicle: VehicleType
    lat: float
    lon: float


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


def _to_courier_response(courier: Courier) -> CourierResponse:
    return CourierResponse(
        id=courier.id,
        name=courier.name,
        vehicle=courier.vehicle,
        lat=courier.lat,
        lon=courier.lon,
    )


def _get_courier_or_404(courier_id: int, session: Session) -> Courier:
    courier = session.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Courier not found.',
        )

    return courier


@router.get('/', tags=['get couriers'], response_model=list[CourierResponse])
def get_couriers(session: Session = Depends(get_session)):
    couriers = session.query(Courier).all()
    return [_to_courier_response(courier) for courier in couriers]


@router.get('/{courier_id}', tags=['get courier by id'], response_model=CourierResponse)
def get_courier(courier_id: int, session: Session = Depends(get_session)):
    courier = _get_courier_or_404(courier_id, session)
    return _to_courier_response(courier)


@router.post('/', tags=['create courier'], response_model=CourierResponse, status_code=status.HTTP_201_CREATED)
def create_courier(courier: CourierCreate, session: Session = Depends(get_session)):
    db_courier = Courier(
        name=courier.name,
        vehicle=courier.vehicle,
        lat=courier.lat,
        lon=courier.lon,
    )

    session.add(db_courier)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Courier already exists or payload violates constraints.',
        )

    session.refresh(db_courier)
    return _to_courier_response(db_courier)


@router.patch('/{courier_id}', tags=['update courier'], response_model=CourierResponse)
def update_courier(courier_id: int, courier: CourierUpdate, session: Session = Depends(get_session)):
    db_courier = _get_courier_or_404(courier_id, session)

    if courier.name is not None:
        db_courier.name = courier.name
    if courier.vehicle is not None:
        db_courier.vehicle = courier.vehicle
    if courier.lat is not None:
        db_courier.lat = courier.lat
    if courier.lon is not None:
        db_courier.lon = courier.lon

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Courier already exists or payload violates constraints.',
        )

    session.refresh(db_courier)
    return _to_courier_response(db_courier)


@router.delete('/{courier_id}', tags=['delete courier'], status_code=status.HTTP_204_NO_CONTENT)
def delete_courier(courier_id: int, session: Session = Depends(get_session)):
    db_courier = _get_courier_or_404(courier_id, session)

    session.delete(db_courier)
    session.commit()


@router.put('/{courier_id}/position', tags=['update courier position'])
def update_courier_position(
    courier_id: int,
    data: CourierPositionUpdate,
    session: Session = Depends(get_session),
    table=Depends(get_session_dynamo),
):
    _get_courier_or_404(courier_id, session)

    timestamp = datetime.datetime.utcnow().isoformat()

    table.put_item(Item={
        "courier_id": courier_id,
        "timestamp": timestamp,
        "delivery_id": data.delivery_id,
        "lat_courier": Decimal(str(data.lat_courier)),
        "lon_courier": Decimal(str(data.lon_courier)),
    })

    return {
        "message": "Location updated",
        "timestamp": timestamp,
    }


@router.get('/{courier_id}/location', tags=['get courier location'], response_model=CourierLocationResponse)
def get_last_location(courier_id: int, table=Depends(get_session_dynamo)):
    response = table.query(
        KeyConditionExpression=Key("courier_id").eq(courier_id),
        ScanIndexForward=False,  # mais recente primeiro
        Limit=1,
    )

    items = response.get("Items", [])

    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Courier location not found.',
        )

    item = items[0]
    return CourierLocationResponse(
        courier_id=int(item["courier_id"]),
        delivery_id=item["delivery_id"],
        lat_courier=float(item["lat_courier"]),
        lon_courier=float(item["lon_courier"]),
        timestamp=item["timestamp"],
    )