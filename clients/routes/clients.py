from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from shared.database.connection import get_session
from shared.database.models import User, Region

router = APIRouter(prefix="/client", tags=["client"])


class ClientCreate(BaseModel):
    email: str
    name: str
    house_lat: float
    house_lon: float
    region_id: int


class ClientUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    house_lat: float | None = None
    house_lon: float | None = None
    region_id: int | None = None


class ClientResponse(BaseModel):
    id: int
    email: str
    name: str
    house_lat: float
    house_lon: float
    region_id: int

def list_clients(session: Session) -> list[User]:
    return session.query(User).all()


def get_client(session: Session, client_id: int) -> User | None:
    return session.query(User).filter(User.id == client_id).first()


def create_client(session: Session, *, email: str, name: str, house_lat: float, house_lon: float, region_id: int) -> User:
    region = session.query(Region).filter(Region.id == region_id).first()
    if not region:
        return None

    db_user = User(email=email, name=name, house_lat=house_lat, house_lon=house_lon, region_id=region_id)
    session.add(db_user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise
    session.refresh(db_user)
    return db_user


def update_client(session: Session, client: User, *, email: str | None = None, name: str | None = None, house_lat: float | None = None, house_lon: float | None = None, region_id: int | None = None) -> User:
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

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise

    session.refresh(client)
    return client


def delete_client(session: Session, client: User) -> None:
    session.delete(client)
    session.commit()


def _to_response(u: User) -> ClientResponse:
    return ClientResponse(
        id=u.id,
        email=u.email,
        name=u.name,
        house_lat=u.house_lat,
        house_lon=u.house_lon,
        region_id=u.region_id,
    )


def _get_or_404(client_id: int, session: Session) -> User:
    db = get_client(session, client_id)
    if not db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    return db


@router.get("/", response_model=list[ClientResponse])
def list_all(session: Session = Depends(get_session)):
    return [_to_response(c) for c in list_clients(session)]


@router.get("/{client_id}", response_model=ClientResponse)
def get_one(client_id: int, session: Session = Depends(get_session)):
    c = _get_or_404(client_id, session)
    return _to_response(c)


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create(client: ClientCreate, session: Session = Depends(get_session)):
    db = create_client(
        session,
        email=client.email,
        name=client.name,
        house_lat=client.house_lat,
        house_lon=client.house_lon,
        region_id=client.region_id,
    )
    if db is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(db)


@router.patch("/{client_id}", response_model=ClientResponse)
def patch(client_id: int, client: ClientUpdate, session: Session = Depends(get_session)):
    db = _get_or_404(client_id, session)
    updated = update_client(
        session,
        db,
        email=client.email,
        name=client.name,
        house_lat=client.house_lat,
        house_lon=client.house_lon,
        region_id=client.region_id,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(updated)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(client_id: int, session: Session = Depends(get_session)):
    db = _get_or_404(client_id, session)
    delete_client(session, db)
