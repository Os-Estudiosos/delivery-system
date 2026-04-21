from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session, get_graph
from database.models import Courier, Delivery, Event, Order, OrderStatus
from utils.cheapest_path import dijkstra

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


class DeliveryStatusCreate(BaseModel):
    status: OrderStatus


class DeliveryStatusResponse(BaseModel):
    id: int
    status: OrderStatus
    updated_at: datetime
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

    return status_flow[current_status]


def _to_delivery_status_response(event: Event) -> DeliveryStatusResponse:
    return DeliveryStatusResponse(
        id=event.id,
        status=event.status,
        updated_at=event.updated_at,
        delivery_id=event.delivery_id,
    )

def _is_courier_available(courier: Courier) -> bool:
    return all(
        _get_latest_delivery_status(delivery) == OrderStatus.DELIVERED
        for delivery in courier.deliveries
    )


def _assign_delivery_to_nearest_courier(delivery: Delivery, graph) -> None:
    order = delivery.order
    couriers = delivery.courier.session.query(Courier).all()

    restaurant_node = graph.get_closest_node(order.restaurant.lat, order.restaurant.lon)
    dists = dijkstra(graph, restaurant_node)

    best_courier = None
    best_dist = float("inf")

    for courier in couriers:
        if not _is_courier_available(courier):
            continue

        courier_node = graph.get_closest_node(courier.lat, courier.lon)
        dist = dists.get(courier_node, float("inf"))

        if dist < best_dist:
            best_dist = dist
            best_courier = courier

    if best_courier:
        delivery.courier = best_courier
        delivery.status = OrderStatus.PICKED_UP


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

    # Verifica se o entregador já tem uma entrega em andamento
    active_delivery = session.query(Delivery).join(Event).filter(
        Delivery.courier_id == delivery.courier_id,
        Event.status.notin_([OrderStatus.DELIVERED])
    ).first()

    if active_delivery:
        raise HTTPException(status_code=400, detail="Courier is currently busy with another delivery.")

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


@router.patch('/{delivery_id}/status', tags=['update delivery status'], response_model=DeliveryStatusResponse, status_code=status.HTTP_201_CREATED)
def update_delivery_status(delivery_id: int, payload: DeliveryStatusCreate, session: Session = Depends(get_session), graph = Depends(get_graph)):
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
        _assign_delivery_to_nearest_courier(db_delivery, graph)

    db_event = Event(
        status=payload.status,
        updated_at=datetime.now(timezone.utc),
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