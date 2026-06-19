import os
import json
import urllib.request
import datetime
import boto3
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.database.connection import get_session, SessionLocal
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
AWS_ENDPOINT = os.environ.get("AWS_ENDPOINT") or os.environ.get("LOCALSTACK_ENDPOINT")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# SQS
from botocore.config import Config
aws_config = Config(max_pool_connections=100)

sqs_kwargs = {"region_name": AWS_REGION, "config": aws_config}
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


@router.get('/', response_model=list[DeliveryResponse])
def get_deliveries(order_id: int | None = None, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return [
        DeliveryResponse(
            id=order_id or 12345,
            order=OrderReference(id=order_id or 12345),
            courier=CourierReference(id=1, name="Mock-Courier-1", vehicle="MOTORCYCLE")
        )
    ]
    # if order_id is not None:
    #     deliveries = session.query(Delivery).filter(Delivery.order_id == order_id).all()
    # else:
    #     deliveries = session.query(Delivery).all()
    # return [_to_delivery_response(delivery) for delivery in deliveries]


@router.get('/{delivery_id}', response_model=DeliveryResponse)
def get_delivery(delivery_id: int, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return DeliveryResponse(
        id=delivery_id,
        order=OrderReference(id=delivery_id),
        courier=CourierReference(id=1, name="Mock-Courier-1", vehicle="MOTORCYCLE")
    )
    # delivery = _get_delivery_or_404(delivery_id, session)
    # return _to_delivery_response(delivery)


@router.post('/', response_model=DeliveryResponse, status_code=status.HTTP_201_CREATED)
def create_delivery(delivery: DeliveryCreate, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return DeliveryResponse(
        id=delivery.order_id,
        order=OrderReference(id=delivery.order_id),
        courier=CourierReference(id=delivery.courier_id, name=f"Mock-Courier-{delivery.courier_id}", vehicle="MOTORCYCLE")
    )
    # db_order = _get_order_or_404(delivery.order_id, session)
    # db_courier = _get_courier_or_404(delivery.courier_id, session)
    # if db_order.delivery:
    #     return _to_delivery_response(db_order.delivery)
    # if _courier_has_active_delivery(delivery.courier_id, session):
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail='Courier is currently busy with another delivery.',
    #     )
    # db_delivery = Delivery(
    #     order=db_order,
    #     courier=db_courier,
    # )
    # session.add(db_delivery)
    # db_courier.available = False
    # try:
    #     session.commit()
    # except IntegrityError:
    #     session.rollback()
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail='Delivery already exists or payload violates constraints.',
    #     )
    # session.refresh(db_delivery)
    # return _to_delivery_response(db_delivery)


@router.patch('/{delivery_id}', response_model=DeliveryResponse)
def update_delivery(delivery_id: int, delivery: DeliveryUpdate, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return DeliveryResponse(
        id=delivery_id,
        order=OrderReference(id=delivery.order_id or 123),
        courier=CourierReference(id=delivery.courier_id or 1, name=f"Mock-Courier-{delivery.courier_id or 1}", vehicle="MOTORCYCLE")
    )
    # db_delivery = _get_delivery_or_404(delivery_id, session)
    # if delivery.order_id is not None:
    #     db_delivery.order = _get_order_or_404(delivery.order_id, session)
    # if delivery.courier_id is not None:
    #     if _courier_has_active_delivery(delivery.courier_id, session, exclude_delivery_id=delivery_id):
    #         raise HTTPException(
    #             status_code=status.HTTP_409_CONFLICT,
    #             detail='Courier is currently busy with another delivery.',
    #         )
    #     if db_delivery.courier_id:
    #         session.query(Courier).filter(Courier.id == db_delivery.courier_id).update({"available": True})
    #     db_delivery.courier = _get_courier_or_404(delivery.courier_id, session)
    #     if db_delivery.courier:
    #         db_delivery.courier.available = False
    # try:
    #     session.commit()
    # except IntegrityError:
    #     session.rollback()
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail='Delivery already exists or payload violates constraints.',
    #     )
    # session.refresh(db_delivery)
    # return _to_delivery_response(db_delivery)


@router.patch('/{delivery_id}/status', response_model=DeliveryStatusResponse, status_code=status.HTTP_201_CREATED)
def update_delivery_status(delivery_id: int, payload: DeliveryStatusCreate, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return DeliveryStatusResponse(
        id=1,
        status=payload.status,
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        delivery_id=delivery_id
    )
    # db_delivery = _get_delivery_or_404(delivery_id, session)
    # current_status = _get_latest_delivery_status(db_delivery)
    # expected_status = _expected_next_status(current_status)
    # if expected_status is None:
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail='Delivery already reached the final status.',
    #     )
    # if payload.status != expected_status:
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail=f'Invalid delivery status transition. Expected {expected_status.value}.',
    #     )
    # best_courier_id = None
    # if payload.status == OrderStatus.READY_FOR_PICKUP and db_delivery.courier_id is None:
    #     restaurant_id = db_delivery.order.restaurant_id
    #     region_id = int(os.environ.get("REGION_ID", "1"))
    #     order_id_for_analytics = db_delivery.order.id
    #     session.commit()
    #     session.close()
    #     best_courier_id = _call_matching_service(restaurant_id)
    #     new_session = SessionLocal()
    #     try:
    #         db_delivery_new = new_session.query(Delivery).filter(Delivery.id == delivery_id).first()
    #         if best_courier_id:
    #             db_delivery_new.courier_id = best_courier_id
    #             new_session.query(Courier).filter(Courier.id == best_courier_id).update({"available": False})
    #         db_event = Event(
    #             status=payload.status,
    #             updated_at=datetime.datetime.now(datetime.timezone.utc),
    #             delivery=db_delivery_new,
    #         )
    #         new_session.add(db_event)
    #         new_session.commit()
    #         new_session.refresh(db_event)
    #         background_tasks.add_task(
    #             _publish_analytics_event,
    #             order_id=order_id_for_analytics,
    #             status=payload.status.value,
    #             restaurant_id=restaurant_id,
    #             region_id=region_id
    #         )
    #         return _to_delivery_status_response(db_event)
    #     except Exception as e:
    #         new_session.rollback()
    #         raise e
    #     finally:
    #         new_session.close()
    # db_event = Event(
    #     status=payload.status,
    #     updated_at=datetime.datetime.now(datetime.timezone.utc),
    #     delivery=db_delivery,
    # )
    # session.add(db_event)
    # if payload.status == OrderStatus.DELIVERED and db_delivery.courier_id:
    #     session.query(Courier).filter(Courier.id == db_delivery.courier_id).update({"available": True})
    # try:
    #     session.commit()
    #     session.refresh(db_event)
    #     background_tasks.add_task(
    #         _publish_analytics_event,
    #         order_id=db_delivery.order.id,
    #         status=payload.status.value,
    #         restaurant_id=db_delivery.order.restaurant_id,
    #         region_id=int(os.environ.get("REGION_ID", "1"))
    #     )
    # except IntegrityError:
    #     session.rollback()
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail='Delivery status could not be updated due to a constraint violation.',
    #     )
    # return _to_delivery_status_response(db_event)
