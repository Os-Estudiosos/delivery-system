import os
import json
import urllib.request
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.database.connection import get_session
from shared.database.models import (
    Courier,
    Delivery,
    Event,
    Order,
    OrderStatus,
)

router = APIRouter(prefix='/delivery', tags=['delivery'])

# Env config
ENV = os.environ.get("ENV", "local").lower()
MATCHING_ENDPOINT = os.environ.get("MATCHING_ENDPOINT", "http://matching:4003")

# Schemas
class OrderReference(BaseModel):
    id: int

class CourierReference(BaseModel):
    id: int
    name: str
    vehicle: str

class DeliveryCreate(BaseModel):
    order_id: int
    courier_id: int

class DeliveryUpdate(BaseModel):
    order_id: int | None = None
    courier_id: int | None = None

class DeliveryResponse(BaseModel):
    id: int
    order: OrderReference
    courier: CourierReference

class DeliveryStatusCreate(BaseModel):
    status: OrderStatus

class DeliveryStatusResponse(BaseModel):
    id: int
    status: OrderStatus
    updated_at: datetime.datetime
    delivery_id: int


def _to_delivery_response(delivery: Delivery) -> DeliveryResponse:
    return DeliveryResponse(
        id=delivery.id,
        order=OrderReference(id=delivery.order.id),
        courier=CourierReference(
            id=delivery.courier.id,
            name=delivery.courier.name,
            vehicle=delivery.courier.vehicle.value,
        ),
    )


def _get_delivery_or_404(delivery_id: int, session: Session) -> Delivery:
    delivery = session.query(Delivery).filter(Delivery.id == delivery_id).first()
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Delivery not found.',
        )
    return delivery


def _get_order_or_404(order_id: int, session: Session) -> Order:
    order = session.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Order not found.',
        )
    return order


def _get_courier_or_404(courier_id: int, session: Session) -> Courier:
    courier = session.query(Courier).filter(Courier.id == courier_id).first()
    if not courier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Courier not found.',
        )
    return courier


def _get_latest_delivery_status(delivery: Delivery) -> OrderStatus | None:
    if not delivery.events:
        return None
    latest_event = max(delivery.events, key=lambda event: (event.updated_at, event.id))
    return latest_event.status


def _expected_next_status(current_status: OrderStatus | None) -> OrderStatus | None:
    status_flow = {
        None: OrderStatus.CONFIRMED,
        OrderStatus.CONFIRMED: OrderStatus.PREPARING,
        OrderStatus.PREPARING: OrderStatus.READY_FOR_PICKUP,
        OrderStatus.READY_FOR_PICKUP: OrderStatus.PICKED_UP,
        OrderStatus.PICKED_UP: OrderStatus.IN_TRANSIT,
        OrderStatus.IN_TRANSIT: OrderStatus.DELIVERED,
        OrderStatus.DELIVERED: None,
    }
    return status_flow.get(current_status)


def _to_delivery_status_response(event: Event) -> DeliveryStatusResponse:
    return DeliveryStatusResponse(
        id=event.id,
        status=event.status,
        updated_at=event.updated_at,
        delivery_id=event.delivery_id,
    )


def _courier_has_active_delivery(courier_id: int, session: Session, exclude_delivery_id: int | None = None) -> bool:
    deliveries = session.query(Delivery).filter(Delivery.courier_id == courier_id).all()
    for delivery in deliveries:
        if exclude_delivery_id is not None and delivery.id == exclude_delivery_id:
            continue
        latest_status = _get_latest_delivery_status(delivery)
        if latest_status != OrderStatus.DELIVERED:
            return True
    return False


def _call_matching_service(restaurant_id: int, region_id: int) -> int | None:
    url = f"{MATCHING_ENDPOINT}/match"
    payload = {"restaurant_id": restaurant_id, "region_id": region_id}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                resp_data = json.loads(response.read().decode("utf-8"))
                return resp_data.get("courier_id")
    except Exception as e:
        print(f"Error calling matching service: {e}")
    return None


@router.get('/', response_model=list[DeliveryResponse])
def get_deliveries(session: Session = Depends(get_session)):
    deliveries = session.query(Delivery).all()
    return [_to_delivery_response(delivery) for delivery in deliveries]


@router.get('/{delivery_id}', response_model=DeliveryResponse)
def get_delivery(delivery_id: int, session: Session = Depends(get_session)):
    delivery = _get_delivery_or_404(delivery_id, session)
    return _to_delivery_response(delivery)


@router.post('/', response_model=DeliveryResponse, status_code=status.HTTP_201_CREATED)
def create_delivery(delivery: DeliveryCreate, session: Session = Depends(get_session)):
    db_order = _get_order_or_404(delivery.order_id, session)
    db_courier = _get_courier_or_404(delivery.courier_id, session)

    if db_order.delivery:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Order already has an associated delivery.',
        )

    if _courier_has_active_delivery(delivery.courier_id, session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Courier is currently busy with another delivery.',
        )

    db_delivery = Delivery(
        order=db_order,
        courier=db_courier,
    )

    session.add(db_delivery)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Delivery already exists or payload violates constraints.',
        )

    session.refresh(db_delivery)
    return _to_delivery_response(db_delivery)


@router.patch('/{delivery_id}', response_model=DeliveryResponse)
def update_delivery(delivery_id: int, delivery: DeliveryUpdate, session: Session = Depends(get_session)):
    db_delivery = _get_delivery_or_404(delivery_id, session)

    if delivery.order_id is not None:
        db_delivery.order = _get_order_or_404(delivery.order_id, session)

    if delivery.courier_id is not None:
        if _courier_has_active_delivery(delivery.courier_id, session, exclude_delivery_id=delivery_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Courier is currently busy with another delivery.',
            )
        db_delivery.courier = _get_courier_or_404(delivery.courier_id, session)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Delivery already exists or payload violates constraints.',
        )

    session.refresh(db_delivery)
    return _to_delivery_response(db_delivery)


@router.patch('/{delivery_id}/status', response_model=DeliveryStatusResponse, status_code=status.HTTP_201_CREATED)
def update_delivery_status(delivery_id: int, payload: DeliveryStatusCreate, session: Session = Depends(get_session)):
    db_delivery = _get_delivery_or_404(delivery_id, session)
    current_status = _get_latest_delivery_status(db_delivery)
    expected_status = _expected_next_status(current_status)

    if expected_status is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Delivery already reached the final status.',
        )

    if payload.status != expected_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Invalid delivery status transition. Expected {expected_status.value}.',
        )

    if payload.status == OrderStatus.READY_FOR_PICKUP:
        best_courier_id = _call_matching_service(db_delivery.order.restaurant_id, db_delivery.order.restaurant.region_id)
        if best_courier_id:
            db_delivery.courier_id = best_courier_id

    db_event = Event(
        status=payload.status,
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        delivery=db_delivery,
    )

    session.add(db_event)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Delivery status could not be updated due to a constraint violation.',
        )

    session.refresh(db_event)
    return _to_delivery_status_response(db_event)
