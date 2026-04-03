from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import Restaurant, KitchenType
from routes.kitchen import KitchenResponse

router = APIRouter(prefix='/restaurant', tags=['restaurant'])

class RestaurantCreate(BaseModel):
    name: str
    lat: float
    lon: float
    kitchen_type_id: int


class RestaurantUpdate(BaseModel):
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    kitchen_type_id: int | None = None


class RestaurantResponse(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    kitchen_type: KitchenResponse


def _to_restaurant_response(restaurant: Restaurant) -> RestaurantResponse:
    return RestaurantResponse(
        id=restaurant.id,
        name=restaurant.name,
        lat=restaurant.lat,
        lon=restaurant.lon,
        kitchen_type=KitchenResponse(
            id=restaurant.kitchen_type.id,
            type=restaurant.kitchen_type.type,
        ),
    )


def _get_restaurant_or_404(restaurant_id: int, session: Session) -> Restaurant:
    restaurant = session.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Restaurant not found.',
        )

    return restaurant


@router.get('/', tags=['get restaurants'], response_model=list[RestaurantResponse])
def get_restaurants(session: Session = Depends(get_session)):
    restaurants = session.query(Restaurant).all()
    return [_to_restaurant_response(restaurant) for restaurant in restaurants]


@router.get('/{restaurant_id}', tags=['get restaurant by id'], response_model=RestaurantResponse)
def get_restaurant(restaurant_id: int, session: Session = Depends(get_session)):
    restaurant = _get_restaurant_or_404(restaurant_id, session)
    return _to_restaurant_response(restaurant)


@router.post('/', tags=['create restaurant'], response_model=RestaurantResponse, status_code=status.HTTP_201_CREATED)
def create_restaurant(restaurant: RestaurantCreate, session: Session = Depends(get_session)):
    db_kitchen_type = session.query(KitchenType).filter(KitchenType.id == restaurant.kitchen_type_id).first()
    if not db_kitchen_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Kitchen type not found.',
        )

    db_restaurant = Restaurant(
        name=restaurant.name,
        lat=restaurant.lat,
        lon=restaurant.lon,
        kitchen_type=db_kitchen_type
    )

    session.add(db_restaurant)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Restaurant already exists or payload violates constraints.',
        )

    session.refresh(db_restaurant)

    return _to_restaurant_response(db_restaurant)


@router.patch('/{restaurant_id}', tags=['update restaurant'], response_model=RestaurantResponse)
def update_restaurant(restaurant_id: int, restaurant: RestaurantUpdate, session: Session = Depends(get_session)):
    db_restaurant = _get_restaurant_or_404(restaurant_id, session)

    if restaurant.kitchen_type_id is not None:
        db_kitchen_type = session.query(KitchenType).filter(KitchenType.id == restaurant.kitchen_type_id).first()
        if not db_kitchen_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Kitchen type not found.',
            )
        db_restaurant.kitchen_type = db_kitchen_type

    if restaurant.name is not None:
        db_restaurant.name = restaurant.name
    if restaurant.lat is not None:
        db_restaurant.lat = restaurant.lat
    if restaurant.lon is not None:
        db_restaurant.lon = restaurant.lon

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Restaurant already exists or payload violates constraints.',
        )

    session.refresh(db_restaurant)
    return _to_restaurant_response(db_restaurant)


@router.delete('/{restaurant_id}', tags=['delete restaurant'], status_code=status.HTTP_204_NO_CONTENT)
def delete_restaurant(restaurant_id: int, session: Session = Depends(get_session)):
    db_restaurant = _get_restaurant_or_404(restaurant_id, session)

    session.delete(db_restaurant)
    session.commit()
