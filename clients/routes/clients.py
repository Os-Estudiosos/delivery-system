from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.database.connection import get_session
from shared.database.models import User
from clients import repository

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
    db = repository.get_client(session, client_id)
    if not db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    return db


@router.get("/", response_model=list[ClientResponse])
def list_all(session: Session = Depends(get_session)):
    return [_to_response(c) for c in repository.list_clients(session)]


@router.get("/{client_id}", response_model=ClientResponse)
def get_one(client_id: int, session: Session = Depends(get_session)):
    c = _get_or_404(client_id, session)
    return _to_response(c)


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create(client: ClientCreate, session: Session = Depends(get_session)):
    db = repository.create_client(
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
    updated = repository.update_client(
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
    repository.delete_client(session, db)
