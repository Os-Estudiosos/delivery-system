from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from boto3.dynamodb.conditions import Key

from database.connection import get_session, get_session_dynamo
from database.models import Order, OrderStatus, Phone, User, VehicleType

router = APIRouter()

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    house_lat: float
    house_lon: float
    phones: list[str] = []


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    house_lat: float
    house_lon: float
    phones: list[str]


class RestaurantReference(BaseModel):
    id: int
    name: str


class ItemReference(BaseModel):
    id: int
    name: str
    price: float


class CourierReference(BaseModel):
    id: int
    name: str
    vehicle: VehicleType


class UserOrderItemResponse(BaseModel):
    item: ItemReference
    quantity: int


class UserOrderResponse(BaseModel):
    id: int
    restaurant: RestaurantReference
    created_at: datetime
    items: list[UserOrderItemResponse]
    courier: CourierReference | None
    status: OrderStatus | None
    courier_location: dict | None


def _get_user_or_404(user_id: int, session: Session) -> User:
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found.',
        )

    return user


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


def _to_user_order_response(order: Order, table=None) -> UserOrderResponse:
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

    return UserOrderResponse(
        id=order.id,
        restaurant=RestaurantReference(
            id=order.restaurant.id,
            name=order.restaurant.name,
        ),
        created_at=order.created_at,
        items=[
            UserOrderItemResponse(
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


@router.post('/user', tags=['user'])
def create_user(user: UserCreate, session: Session = Depends(get_session)):
    db_user = User(
        email=user.email,
        name=user.name,
        house_lat=user.house_lat,
        house_lon=user.house_lon,
    )

    for phone in user.phones:
        db_user.phones.append(Phone(phone=phone))

    session.add(db_user)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='User already exists or payload violates constraints.',
        )

    session.refresh(db_user)

    return UserResponse(
        id=db_user.id,
        name=db_user.name,
        email=db_user.email,
        house_lat=db_user.house_lat,
        house_lon=db_user.house_lon,
        phones=[phone.phone for phone in db_user.phones],
    )


@router.get('/user/{user_id}/order', tags=['get user orders'], response_model=list[UserOrderResponse])
def get_user_orders(user_id: int, session: Session = Depends(get_session), table=Depends(get_session_dynamo)):
    _get_user_or_404(user_id, session)

    orders = session.query(Order).filter(Order.user_id == user_id).order_by(desc(Order.created_at)).all()
    return [_to_user_order_response(order, table) for order in orders]


@router.get('/user/{user_id}/order/{order_id}', tags=['get user order by id'], response_model=UserOrderResponse)
def get_user_order(user_id: int, order_id: int, session: Session = Depends(get_session), table=Depends(get_session_dynamo)):
    _get_user_or_404(user_id, session)

    order = session.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Order not found for this user.',
        )

    return _to_user_order_response(order, table)
