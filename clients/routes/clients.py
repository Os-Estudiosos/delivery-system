import os
import datetime
import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from boto3.dynamodb.conditions import Key

from shared.database.connection import get_session
from shared.database.models import User, Region, Phone, Order, OrderStatus, VehicleType

router = APIRouter(tags=["client"]) 

# Env config
ENV = os.environ.get("ENV", "local").lower()
AWS_ENDPOINT = os.environ.get("AWS_ENDPOINT") or os.environ.get("LOCALSTACK_ENDPOINT")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
REGION_ID = int(os.environ.get("REGION_ID", "1"))

# DynamoDB
dynamodb_kwargs = {"region_name": AWS_REGION}
if ENV == "local" and AWS_ENDPOINT:
    dynamodb_kwargs["endpoint_url"] = AWS_ENDPOINT
    dynamodb_kwargs["aws_access_key_id"] = "test"
    dynamodb_kwargs["aws_secret_access_key"] = "test"

dynamodb_resource = boto3.resource("dynamodb", **dynamodb_kwargs)
dynamodb_table = dynamodb_resource.Table("courier_positions")

# -------------------- Schemas --------------------
class ClientCreate(BaseModel):
    email: str
    name: str
    house_lat: float
    house_lon: float
    region_id: int | None = None
    phones: list[str] = []


class ClientUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    house_lat: float | None = None
    house_lon: float | None = None
    region_id: int | None = None
    phones: list[str] | None = None


class ClientResponse(BaseModel):
    id: int
    email: str
    name: str
    house_lat: float
    house_lon: float
    region_id: int
    phones: list[str] = []


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
    created_at: datetime.datetime
    items: list[UserOrderItemResponse]
    courier: CourierReference | None
    status: OrderStatus | None
    courier_location: dict | None


# -------------------- DB Helpers --------------------
def list_clients(session: Session) -> list[User]:
    return session.query(User).all()


def get_client(session: Session, client_id: int) -> User | None:
    return session.query(User).filter(User.id == client_id).first()


def create_client(session: Session, *, email: str, name: str, house_lat: float, house_lon: float, region_id: int | None = None, phones: list[str] = []) -> User:
    if region_id is None:
        region_id = REGION_ID

    region = session.query(Region).filter(Region.id == region_id).first()
    if not region:
        return None

    db_user = User(email=email, name=name, house_lat=house_lat, house_lon=house_lon, region_id=region_id)
    for phone in phones:
        db_user.phones.append(Phone(phone=phone))
    session.add(db_user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise
    session.refresh(db_user)
    return db_user


def update_client(session: Session, client: User, *, email: str | None = None, name: str | None = None, house_lat: float | None = None, house_lon: float | None = None, region_id: int | None = None, phones: list[str] | None = None) -> User:
    if region_id is not None:
        region = session.query(Region).filter(Region.id == region_id).first()
        if not region:
            return None
        client.region_id = region_id

    if email is not None:
        client.email = email
    if name is not None:
        client.name = name
    if house_lat is not None:
        client.house_lat = house_lat
    if house_lon is not None:
        client.house_lon = house_lon

    if phones is not None:
        client.phones.clear()
        for p in phones:
            client.phones.append(Phone(phone=p))

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise

    session.refresh(client)
    return client




def delete_client(session: Session, client: User) -> None:
    session.delete(client)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise


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


def _to_user_order_response(order: Order) -> UserOrderResponse:
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
            _get_last_courier_location(order.delivery.courier.id)
            if order.delivery and order.delivery.courier
            else None
        ),
    )


# -------------------- Helpers --------------------
def _to_response(u: User) -> ClientResponse:
    return ClientResponse(
        id=u.id,
        email=u.email,
        name=u.name,
        house_lat=u.house_lat,
        house_lon=u.house_lon,
        region_id=u.region_id or REGION_ID,
        phones=[phone.phone for phone in u.phones],
    )


def _get_or_404(client_id: int, session: Session) -> User:
    db = get_client(session, client_id)
    if not db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return db


# -------------------- Endpoints --------------------
@router.get("/client", response_model=list[ClientResponse])
def list_all(session: Session = Depends(get_session)):
    return [_to_response(c) for c in list_clients(session)]


@router.get("/client/{client_id}", response_model=ClientResponse)
def get_one(client_id: int, session: Session = Depends(get_session)):
    c = _get_or_404(client_id, session)
    return _to_response(c)


@router.post("/client", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create(client: ClientCreate, session: Session = Depends(get_session)):
    try:
        db = create_client(
            session,
            email=client.email,
            name=client.name,
            house_lat=client.house_lat,
            house_lon=client.house_lon,
            region_id=client.region_id,
            phones=client.phones,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client already exists or payload violates constraints.",
        )
    if db is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(db)


@router.patch("/client/{client_id}", response_model=ClientResponse)
def patch(client_id: int, client: ClientUpdate, session: Session = Depends(get_session)):
    db = _get_or_404(client_id, session)
    try:
        updated = update_client(
            session,
            db,
            email=client.email,
            name=client.name,
            house_lat=client.house_lat,
            house_lon=client.house_lon,
            region_id=client.region_id,
            phones=client.phones,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client update violates unique or database constraints.",
        )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(updated)


@router.delete("/client/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(client_id: int, session: Session = Depends(get_session)):
    db = _get_or_404(client_id, session)
    try:
        delete_client(session, db)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client has associated orders and cannot be deleted.",
        )


# Monolith user routes compatibility
@router.post('/user', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, session: Session = Depends(get_session)):
    db_user = User(
        email=user.email,
        name=user.name,
        house_lat=user.house_lat,
        house_lon=user.house_lon,
        region_id=REGION_ID,
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


@router.get('/user/{user_id}/order', response_model=list[UserOrderResponse])
def get_user_orders(user_id: int, session: Session = Depends(get_session)):
    _get_or_404(user_id, session)
    orders = session.query(Order).filter(Order.user_id == user_id).order_by(desc(Order.created_at)).all()
    return [_to_user_order_response(order) for order in orders]


@router.get('/user/{user_id}/order/{order_id}', response_model=UserOrderResponse)
def get_user_order(user_id: int, order_id: int, session: Session = Depends(get_session)):
    _get_or_404(user_id, session)
    order = session.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Order not found for this user.',
        )
    return _to_user_order_response(order)
