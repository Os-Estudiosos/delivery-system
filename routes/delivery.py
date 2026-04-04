from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import Courier, Delivery, Order

router = APIRouter(prefix='/delivery', tags=['delivery'])


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


@router.get('/', tags=['get deliveries'], response_model=list[DeliveryResponse])
def get_deliveries(session: Session = Depends(get_session)):
    deliveries = session.query(Delivery).all()
    return [_to_delivery_response(delivery) for delivery in deliveries]


@router.get('/{delivery_id}', tags=['get delivery by id'], response_model=DeliveryResponse)
def get_delivery(delivery_id: int, session: Session = Depends(get_session)):
    delivery = _get_delivery_or_404(delivery_id, session)
    return _to_delivery_response(delivery)


@router.post('/', tags=['create delivery'], response_model=DeliveryResponse, status_code=status.HTTP_201_CREATED)
def create_delivery(delivery: DeliveryCreate, session: Session = Depends(get_session)):
    db_order = _get_order_or_404(delivery.order_id, session)
    db_courier = _get_courier_or_404(delivery.courier_id, session)

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


@router.patch('/{delivery_id}', tags=['update delivery'], response_model=DeliveryResponse)
def update_delivery(delivery_id: int, delivery: DeliveryUpdate, session: Session = Depends(get_session)):
    db_delivery = _get_delivery_or_404(delivery_id, session)

    if delivery.order_id is not None:
        db_delivery.order = _get_order_or_404(delivery.order_id, session)

    if delivery.courier_id is not None:
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