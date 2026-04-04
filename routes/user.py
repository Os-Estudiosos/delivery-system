from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import Order, Phone, User

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


class UserOrderItemResponse(BaseModel):
    item: ItemReference
    quantity: int


class UserOrderResponse(BaseModel):
    id: int
    restaurant: RestaurantReference
    created_at: datetime
    items: list[UserOrderItemResponse]


def _get_user_or_404(user_id: int, session: Session) -> User:
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found.',
        )

    return user


def _to_user_order_response(order: Order) -> UserOrderResponse:
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
def get_user_orders(user_id: int, session: Session = Depends(get_session)):
    _get_user_or_404(user_id, session)

    orders = session.query(Order).filter(Order.user_id == user_id).all()
    return [_to_user_order_response(order) for order in orders]


@router.get('/user/{user_id}/order/{order_id}', tags=['get user order by id'], response_model=UserOrderResponse)
def get_user_order(user_id: int, order_id: int, session: Session = Depends(get_session)):
    _get_user_or_404(user_id, session)

    order = session.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Order not found for this user.',
        )

    return _to_user_order_response(order)
