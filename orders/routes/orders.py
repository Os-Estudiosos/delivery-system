import os
import json
import urllib.request
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
import boto3
from boto3.dynamodb.conditions import Key

from shared.database.connection import get_session, SessionLocal
from shared.database.models import (
    Courier,
    Delivery,
    Event,
    Item,
    Order,
    OrderItem,
    OrderStatus,
    Restaurant,
    User,
    VehicleType,
)

router = APIRouter(prefix='/order', tags=['order'])

# Env config
ENV = os.environ.get("ENV", "local").lower()
AWS_ENDPOINT = os.environ.get("AWS_ENDPOINT") or os.environ.get("LOCALSTACK_ENDPOINT")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
MATCHING_ENDPOINT = os.environ.get("MATCHING_ENDPOINT", "http://matching:4003")

# DynamoDB
dynamodb_kwargs = {"region_name": AWS_REGION}
if ENV == "local" and AWS_ENDPOINT:
    dynamodb_kwargs["endpoint_url"] = AWS_ENDPOINT
    dynamodb_kwargs["aws_access_key_id"] = "test"
    dynamodb_kwargs["aws_secret_access_key"] = "test"

dynamodb_resource = boto3.resource("dynamodb", **dynamodb_kwargs)
dynamodb_table = dynamodb_resource.Table("courier_positions")

# SQS
sqs_kwargs = {"region_name": AWS_REGION}
if ENV == "local" and AWS_ENDPOINT:
    sqs_kwargs["endpoint_url"] = AWS_ENDPOINT
    sqs_kwargs["aws_access_key_id"] = "test"
    sqs_kwargs["aws_secret_access_key"] = "test"

sqs_client = boto3.client("sqs", **sqs_kwargs)


_cached_analytics_queue_url = None


def _get_analytics_queue_url():
    global _cached_analytics_queue_url
    if _cached_analytics_queue_url:
        return _cached_analytics_queue_url

    queue_url = os.environ.get("ANALYTICS_SQS_QUEUE_URL")
    if queue_url:
        _cached_analytics_queue_url = queue_url
        return queue_url
    try:
        resp = sqs_client.get_queue_url(QueueName="analytics-events")
        _cached_analytics_queue_url = resp["QueueUrl"]
        return _cached_analytics_queue_url
    except Exception:
        if AWS_ENDPOINT:
            _cached_analytics_queue_url = f"{AWS_ENDPOINT}/000000000000/analytics-events"
            return _cached_analytics_queue_url
        return ""



def _publish_analytics_event(order_id: int, status: str, restaurant_id: int, region_id: int):
    queue_url = _get_analytics_queue_url()
    if not queue_url:
        print("Analytics SQS queue URL could not be resolved, skipping publish.")
        return

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    message_body = {
        "order_id": order_id,
        "status": status,
        "restaurant_id": restaurant_id,
        "region_id": region_id,
        "timestamp": timestamp,
    }
    try:
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body)
        )
    except Exception as e:
        print(f"Error sending analytics event to SQS: {e}")

# Schemas
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
    created_at: datetime.datetime
    items: list[OrderItemResponse]
    courier: CourierReference | None
    status: OrderStatus | None
    courier_location: dict | None

class OrderEventResponse(BaseModel):
    id: int
    status: OrderStatus
    updated_at: datetime.datetime
    delivery_id: int


def _get_last_courier_location(courier_id: int) -> dict | None:
    try:
        response = dynamodb_table.query(
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
            "delivery_id": item.get("delivery_id", ""),
            "lat_courier": float(item.get("lat") or item.get("lat_courier") or 0.0),
            "lon_courier": float(item.get("lng") or item.get("lon_courier") or 0.0),
            "timestamp": item["timestamp"],
        }
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return None


def _to_order_response(order: Order) -> OrderResponse:
    latest_event = (
        max(order.delivery.events, key=lambda event: (event.updated_at, event.id))
        if order.delivery and order.delivery.events
        else None
    )

    courier = None
    if order.delivery and order.delivery.courier:
        courier = CourierReference(
            id=order.delivery.courier.id,
            name=order.delivery.courier.name,
            vehicle=order.delivery.courier.vehicle,
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
            _get_last_courier_location(order.delivery.courier.id)
            if order.delivery and order.delivery.courier
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


def _call_matching_service(restaurant_id: int) -> int | None:
    url = f"{MATCHING_ENDPOINT}/match"
    payload = {"restaurant_id": restaurant_id}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                resp_data = json.loads(response.read().decode("utf-8"))
                return resp_data.get("courier_id")
    except Exception as e:
        print(f"Error calling matching service: {e}")
    return None


@router.get('/', response_model=list[OrderResponse])
def get_orders(session: Session = Depends(get_session)):
    orders = (
        session.query(Order)
        .options(
            joinedload(Order.restaurant),
            joinedload(Order.user),
            joinedload(Order.items).joinedload(OrderItem.item),
            joinedload(Order.delivery).joinedload(Delivery.events),
            joinedload(Order.delivery).joinedload(Delivery.courier),
        )
        .all()
    )
    return [_to_order_response(order) for order in orders]


@router.get('/{order_id}', response_model=OrderResponse)
def get_order(order_id: int, session: Session = Depends(get_session)):
    order = _get_order_or_404(order_id, session)
    return _to_order_response(order)


@router.post('/', response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(order: OrderCreate, session: Session = Depends(get_session)):
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

    session.add(db_order)

    try:
        session.flush()
        order_id = db_order.id
        restaurant_id = db_restaurant.id
        region_id = int(os.environ.get("REGION_ID", "1"))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Order already exists or payload violates constraints.',
        )

    # Call matching service
    # NO database connection is held here because the transaction was committed!
    best_courier_id = _call_matching_service(restaurant_id)

    try:
        if best_courier_id:
            # This silently acquires a new connection
            db_delivery = Delivery(order_id=order_id, courier_id=best_courier_id)
            session.add(db_delivery)
            session.flush()

            db_event = Event(status=OrderStatus.CONFIRMED, delivery_id=db_delivery.id)
            session.add(db_event)
            session.commit()
            
            _publish_analytics_event(
                order_id=order_id,
                status=OrderStatus.CONFIRMED.value,
                restaurant_id=restaurant_id,
                region_id=region_id
            )
        else:
            pass # No commit needed
        
        # Now refresh db_order
        # We need to re-fetch it because it might be expired and we want to return it
        db_order = session.query(Order).filter(Order.id == order_id).first()
        return _to_order_response(db_order)
    except Exception as e:
        print(f"Failed to assign delivery on order create: {e}")
        session.rollback()
        session.refresh(db_order)
        return _to_order_response(db_order)


@router.patch('/{order_id}', response_model=OrderResponse)
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


@router.get('/{order_id}/event', response_model=list[OrderEventResponse])
def get_order_events(order_id: int, session: Session = Depends(get_session)):
    order = _get_order_or_404(order_id, session)

    if not order.delivery:
        return []

    events = sorted(order.delivery.events, key=lambda e: e.updated_at, reverse=True)
    return [
        OrderEventResponse(
            id=event.id,
            status=event.status,
            updated_at=event.updated_at,
            delivery_id=event.delivery_id,
        )
        for event in events
    ]
