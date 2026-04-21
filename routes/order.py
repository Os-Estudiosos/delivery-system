from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from boto3.dynamodb.conditions import Key
import osmnx as ox

from database.connection import get_graph, get_session, get_session_dynamo
from database.models import Courier, Delivery, Event, Item, Order, OrderItem, OrderStatus, Restaurant, User, VehicleType
from utils.cheapest_path import dijkstra

router = APIRouter(prefix='/order', tags=['order'])


class RestaurantReference(BaseModel):
    id: int
    name: str


class UserReference(BaseModel):
    id: int
    email: str
    name: str


class ItemReference(BaseModel):
    id: int
    name: str
    price: float


class CourierReference(BaseModel):
    id: int
    name: str
    vehicle: VehicleType


class OrderItemCreate(BaseModel):
    item_id: int
    quantity: int = Field(default=1, ge=1)


class OrderCreate(BaseModel):
    restaurant_id: int
    user_id: int
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderUpdate(BaseModel):
    restaurant_id: int | None = None
    user_id: int | None = None
    items: list[OrderItemCreate] | None = None


class OrderItemResponse(BaseModel):
    item: ItemReference
    quantity: int


class OrderResponse(BaseModel):
    id: int
    restaurant: RestaurantReference
    user: UserReference
    created_at: datetime
    items: list[OrderItemResponse]
    courier: CourierReference | None
    status: OrderStatus | None
    courier_location: dict | None


class OrderEventResponse(BaseModel):
    id: int
    status: OrderStatus
    updated_at: datetime
    delivery_id: int


def _get_latest_delivery_status(delivery: Delivery) -> OrderStatus | None:
    if not delivery.events:
        return None

    latest_event = max(delivery.events, key=lambda event: (event.updated_at, event.id))
    return latest_event.status


def _is_courier_available(courier: Courier) -> bool:
    return all(
        _get_latest_delivery_status(delivery) == OrderStatus.DELIVERED
        for delivery in courier.deliveries
    )


def _pick_nearest_available_courier(order: Order, graph, session: Session) -> Courier | None:
    couriers = session.query(Courier).all()
    if not couriers:
        return None

    restaurant_node = ox.distance.nearest_nodes(graph, order.restaurant.lon, order.restaurant.lat)
    dists = dijkstra(graph, restaurant_node)

    best_courier = None
    best_dist = float("inf")

    for courier in couriers:
        if not _is_courier_available(courier):
            continue

        courier_node = ox.distance.nearest_nodes(graph, courier.lon, courier.lat)
        dist = dists.get(courier_node, float("inf"))

        if dist < best_dist:
            best_dist = dist
            best_courier = courier

    return best_courier


def _get_last_courier_location(courier_id: int, table) -> dict | None:
    if table is None:
        return None

    response = table.query(
        KeyConditionExpression=Key("courier_id").eq(courier_id),
        ScanIndexForward=False,
        Limit=1,
    )

    items = response.get("Items", [])
    if not items:
        return None

    item = items[0]
    return {
        "courier_id": int(item["courier_id"]),
        "delivery_id": item["delivery_id"],
        "lat_courier": float(item["lat_courier"]),
        "lon_courier": float(item["lon_courier"]),
        "timestamp": item["timestamp"],
    }


def _to_order_response(order: Order, table=None) -> OrderResponse:
    latest_event = (
        max(order.delivery.events, key=lambda event: (event.updated_at, event.id))
        if order.delivery and order.delivery.events
        else None
    )

    courier = (
        CourierReference(
            id=order.delivery.courier.id,
            name=order.delivery.courier.name,
            vehicle=order.delivery.courier.vehicle,
        )
        if order.delivery
        else None
    )

    return OrderResponse(
        id=order.id,
        restaurant=RestaurantReference(
            id=order.restaurant.id,
            name=order.restaurant.name,
        ),
        user=UserReference(
            id=order.user.id,
            email=order.user.email,
            name=order.user.name,
        ),
        created_at=order.created_at,
        items=[
            OrderItemResponse(
                item=ItemReference(
                    id=order_item.item.id,
                    name=order_item.item.name,
                    price=float(order_item.item.price),
                ),
                quantity=order_item.quantity,
            )
            for order_item in order.items
        ],
        courier=courier,
        status=latest_event.status if latest_event else None,
        courier_location=(
            _get_last_courier_location(order.delivery.courier.id, table)
            if order.delivery
            else None
        ),
    )


def _get_order_or_404(order_id: int, session: Session) -> Order:
    order = session.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Order not found.',
        )

    return order


def _get_restaurant_or_404(restaurant_id: int, session: Session) -> Restaurant:
    restaurant = session.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Restaurant not found.',
        )

    return restaurant


def _get_user_or_404(user_id: int, session: Session) -> User:
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found.',
        )

    return user


def _validate_order_items(item_payloads: list[OrderItemCreate], restaurant_id: int, session: Session) -> list[tuple[Item, int]]:
    items: list[tuple[Item, int]] = []
    item_ids: set[int] = set()

    for order_item in item_payloads:
        if order_item.item_id in item_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Duplicated item in order payload.',
            )

        item_ids.add(order_item.item_id)

        db_item = session.query(Item).filter(Item.id == order_item.item_id).first()
        if not db_item or db_item.restaurant_id != restaurant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Item not found for the informed restaurant.',
            )

        items.append((db_item, order_item.quantity))

    return items


def _to_order_event_response(event) -> OrderEventResponse:
    return OrderEventResponse(
        id=event.id,
        status=event.status,
        updated_at=event.updated_at,
        delivery_id=event.delivery_id,
    )


@router.get('/', tags=['get orders'], response_model=list[OrderResponse])
def get_orders(session: Session = Depends(get_session)):
    orders = session.query(Order).all()
    return [_to_order_response(order) for order in orders]


@router.get('/{order_id}', tags=['get order by id'], response_model=OrderResponse)
def get_order(order_id: int, session: Session = Depends(get_session), table=Depends(get_session_dynamo)):
    order = _get_order_or_404(order_id, session)
    return _to_order_response(order, table)


@router.post('/', tags=['create order'], response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(order: OrderCreate, session: Session = Depends(get_session), graph=Depends(get_graph)):
    db_restaurant = _get_restaurant_or_404(order.restaurant_id, session)
    db_user = _get_user_or_404(order.user_id, session)
    valid_items = _validate_order_items(order.items, db_restaurant.id, session)

    db_order = Order(
        restaurant=db_restaurant,
        user=db_user,
    )

    for db_item, quantity in valid_items:
        db_order.items.append(
            OrderItem(item=db_item, quantity=quantity)
        )

    best_courier = _pick_nearest_available_courier(db_order, graph, session)
    if best_courier:
        db_delivery = Delivery(order=db_order, courier=best_courier)
        db_order.delivery = db_delivery
        db_event = Event(status=OrderStatus.CONFIRMED, delivery=db_delivery)
        session.add(db_event)

    session.add(db_order)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Order already exists or payload violates constraints.',
        )

    session.refresh(db_order)
    return _to_order_response(db_order)


@router.patch('/{order_id}', tags=['update order'], response_model=OrderResponse)
def update_order(order_id: int, order: OrderUpdate, session: Session = Depends(get_session)):
    db_order = _get_order_or_404(order_id, session)

    next_restaurant_id = db_order.restaurant_id

    if order.restaurant_id is not None:
        db_order.restaurant = _get_restaurant_or_404(order.restaurant_id, session)
        next_restaurant_id = order.restaurant_id

    if order.user_id is not None:
        db_order.user = _get_user_or_404(order.user_id, session)

    if order.items is not None:
        valid_items = _validate_order_items(order.items, next_restaurant_id, session)
        db_order.items.clear()

        for db_item, quantity in valid_items:
            db_order.items.append(
                OrderItem(item=db_item, quantity=quantity)
            )

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Order already exists or payload violates constraints.',
        )

    session.refresh(db_order)
    return _to_order_response(db_order)


@router.get('/{order_id}/event', tags=['get order events'], response_model=list[OrderEventResponse])
def get_order_events(order_id: int, session: Session = Depends(get_session)):
    order = _get_order_or_404(order_id, session)

    if not order.delivery:
        return []

    events = sorted(order.delivery.events, key=lambda e: e.updated_at, reverse=True)
    return [_to_order_event_response(event) for event in events]