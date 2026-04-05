from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import Item, Restaurant

router = APIRouter(prefix='/item', tags=['item'])


class RestaurantReference(BaseModel):
    id: int
    name: str


class ItemCreate(BaseModel):
    name: str
    price: float
    restaurant_id: int


class ItemUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    restaurant_id: int | None = None


class ItemResponse(BaseModel):
    id: int
    name: str
    price: float
    restaurant: RestaurantReference


def _to_item_response(item: Item) -> ItemResponse:
    return ItemResponse(
        id=item.id,
        name=item.name,
        price=float(item.price),
        restaurant=RestaurantReference(
            id=item.restaurant.id,
            name=item.restaurant.name,
        ),
    )


def _get_item_or_404(item_id: int, session: Session) -> Item:
    item = session.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Item not found.',
        )

    return item


def _get_restaurant_or_404(restaurant_id: int, session: Session) -> Restaurant:
    restaurant = session.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Restaurant not found.',
        )

    return restaurant


@router.get('/', tags=['get items'], response_model=list[ItemResponse])
def get_items(session: Session = Depends(get_session)):
    items = session.query(Item).all()
    return [_to_item_response(item) for item in items]


@router.get('/{item_id}', tags=['get item by id'], response_model=ItemResponse)
def get_item(item_id: int, session: Session = Depends(get_session)):
    item = _get_item_or_404(item_id, session)
    return _to_item_response(item)


@router.post('/', tags=['create item'], response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate, session: Session = Depends(get_session)):
    db_restaurant = _get_restaurant_or_404(item.restaurant_id, session)

    db_item = Item(
        name=item.name,
        price=item.price,
        restaurant=db_restaurant,
    )

    session.add(db_item)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Item already exists or payload violates constraints.',
        )

    session.refresh(db_item)
    return _to_item_response(db_item)


@router.patch('/{item_id}', tags=['update item'], response_model=ItemResponse)
def update_item(item_id: int, item: ItemUpdate, session: Session = Depends(get_session)):
    db_item = _get_item_or_404(item_id, session)

    if item.restaurant_id is not None:
        db_restaurant = _get_restaurant_or_404(item.restaurant_id, session)
        db_item.restaurant = db_restaurant

    if item.name is not None:
        db_item.name = item.name
    if item.price is not None:
        db_item.price = item.price

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Item already exists or payload violates constraints.',
        )

    session.refresh(db_item)
    return _to_item_response(db_item)


@router.delete('/{item_id}', tags=['delete item'], status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, session: Session = Depends(get_session)):
    db_item = _get_item_or_404(item_id, session)

    session.delete(db_item)
    session.commit()
