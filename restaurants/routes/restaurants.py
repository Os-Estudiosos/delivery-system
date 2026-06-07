from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from shared.database.connection import get_session
from shared.database.models import KitchenType, Restaurant, Item, Region
from restaurants.routes.kitchen import KitchenResponse

router = APIRouter(prefix="/restaurant", tags=["restaurant"])


# -----------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------

class ItemResponse(BaseModel):
    id: int
    name: str
    price: float


class RestaurantCreate(BaseModel):
    name: str
    lat: float
    lon: float
    kitchen_type_id: int
    region_id: int


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


class RestaurantDetailResponse(RestaurantResponse):
    """Extended response that includes the restaurant's menu items."""
    items: list[ItemResponse]


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _to_response(restaurant: Restaurant) -> RestaurantResponse:
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


def _to_detail_response(restaurant: Restaurant) -> RestaurantDetailResponse:
    return RestaurantDetailResponse(
        id=restaurant.id,
        name=restaurant.name,
        lat=restaurant.lat,
        lon=restaurant.lon,
        kitchen_type=KitchenResponse(
            id=restaurant.kitchen_type.id,
            type=restaurant.kitchen_type.type,
        ),
        items=[
            ItemResponse(id=item.id, name=item.name, price=float(item.price))
            for item in restaurant.items
        ],
    )


def _get_restaurant_or_404(restaurant_id: int, session: Session) -> Restaurant:
    restaurant = (
        session.query(Restaurant)
        .options(joinedload(Restaurant.kitchen_type), joinedload(Restaurant.items))
        .filter(Restaurant.id == restaurant_id)
        .first()
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found.",
        )
    return restaurant


def _get_kitchen_or_404(kitchen_type_id: int, session: Session) -> KitchenType:
    db_kitchen = session.query(KitchenType).filter(KitchenType.id == kitchen_type_id).first()
    if not db_kitchen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kitchen type not found.",
        )
    return db_kitchen


def _get_region_or_404(region_id: int, session: Session) -> Region:
    db_region = session.query(Region).filter(Region.id == region_id).first()
    if not db_region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Region not found.",
        )
    return db_region


# -----------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------

@router.get(
    "/",
    summary="List restaurants",
    response_model=list[RestaurantResponse],
)
def get_restaurants(
    kitchen_type_id: int | None = Query(default=None, description="Filter by kitchen type"),
    session: Session = Depends(get_session),
):
    """Returns all restaurants. Optionally filter by `kitchen_type_id`."""
    query = session.query(Restaurant).options(joinedload(Restaurant.kitchen_type))

    if kitchen_type_id is not None:
        query = query.filter(Restaurant.kitchen_type_id == kitchen_type_id)

    return [_to_response(r) for r in query.all()]


@router.get(
    "/{restaurant_id}",
    summary="Get restaurant by ID (includes menu items)",
    response_model=RestaurantDetailResponse,
)
def get_restaurant(
    restaurant_id: int,
    session: Session = Depends(get_session),
):
    """Returns a single restaurant with its full menu."""
    restaurant = _get_restaurant_or_404(restaurant_id, session)
    return _to_detail_response(restaurant)


@router.post(
    "/",
    summary="Create restaurant",
    response_model=RestaurantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_restaurant(
    restaurant: RestaurantCreate,
    session: Session = Depends(get_session),
):
    db_kitchen = _get_kitchen_or_404(restaurant.kitchen_type_id, session)
    db_region = _get_region_or_404(restaurant.region_id, session)

    db_restaurant = Restaurant(
        name=restaurant.name,
        lat=restaurant.lat,
        lon=restaurant.lon,
        kitchen_type=db_kitchen,
        region=db_region,
    )

    session.add(db_restaurant)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Restaurant already exists or payload violates constraints.",
        )

    session.refresh(db_restaurant)
    return _to_response(db_restaurant)


@router.patch(
    "/{restaurant_id}",
    summary="Update restaurant",
    response_model=RestaurantResponse,
)
def update_restaurant(
    restaurant_id: int,
    restaurant: RestaurantUpdate,
    session: Session = Depends(get_session),
):
    db_restaurant = _get_restaurant_or_404(restaurant_id, session)

    if restaurant.kitchen_type_id is not None:
        db_restaurant.kitchen_type = _get_kitchen_or_404(restaurant.kitchen_type_id, session)

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
            detail="Restaurant already exists or payload violates constraints.",
        )

    session.refresh(db_restaurant)
    return _to_response(db_restaurant)


@router.delete(
    "/{restaurant_id}",
    summary="Delete restaurant",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_restaurant(
    restaurant_id: int,
    session: Session = Depends(get_session),
):
    db_restaurant = _get_restaurant_or_404(restaurant_id, session)
    session.delete(db_restaurant)
    session.commit()


class ItemCreate(BaseModel):
    name: str
    price: float


@router.post("/{restaurant_id}/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(restaurant_id: int, item: ItemCreate, session: Session = Depends(get_session)):
    restaurant = _get_restaurant_or_404(restaurant_id, session)

    db_item = Item(name=item.name, price=item.price, restaurant_id=restaurant.id)
    session.add(db_item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item conflict")

    session.refresh(db_item)
    return ItemResponse(id=db_item.id, name=db_item.name, price=float(db_item.price))


@router.get("/{restaurant_id}/items", response_model=list[ItemResponse])
def list_items(restaurant_id: int, session: Session = Depends(get_session)):
    restaurant = _get_restaurant_or_404(restaurant_id, session)
    return [ItemResponse(id=i.id, name=i.name, price=float(i.price)) for i in restaurant.items]
