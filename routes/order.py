from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import Item, Order, OrderItem, Restaurant, User

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


class OrderItemCreate(BaseModel):
    item_id: int
    quantity: int = 1


class OrderCreate(BaseModel):
    restaurant_id: int
    user_id: int
    items: list[OrderItemCreate] = []


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


def _to_order_response(order: Order) -> OrderResponse:
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


@router.get('/', tags=['get orders'], response_model=list[OrderResponse])
def get_orders(session: Session = Depends(get_session)):
    orders = session.query(Order).all()
    return [_to_order_response(order) for order in orders]


@router.get('/{order_id}', tags=['get order by id'], response_model=OrderResponse)
def get_order(order_id: int, session: Session = Depends(get_session)):
    order = _get_order_or_404(order_id, session)
    return _to_order_response(order)


@router.post('/', tags=['create order'], response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
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


@router.delete('/{order_id}', tags=['delete order'], status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: int, session: Session = Depends(get_session)):
    db_order = _get_order_or_404(order_id, session)

    session.delete(db_order)
    session.commit()