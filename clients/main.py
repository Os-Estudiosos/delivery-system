from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.database.connection import get_session
from shared.database import models


app = FastAPI(title="clients-service")


class ClientCreate(BaseModel):
    email: str
    name: str
    house_lat: float
    house_lon: float
    region_id: int
    phones: List[str] = []


class ClientResponse(BaseModel):
    id: int
    email: str
    name: str
    house_lat: float
    house_lon: float
    region_id: int
    phones: List[str] = []


@app.get("/health")
def health():
    return {"status": "ok", "service": "clients"}


@app.post("/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(client: ClientCreate, session: Session = Depends(get_session)):
    # valida existência de region
    region = session.get(models.Region, client.region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="region not found")

    db_user = models.User(
        email=client.email,
        name=client.name,
        house_lat=client.house_lat,
        house_lon=client.house_lon,
        region_id=client.region_id,
    )
    session.add(db_user)
    try:
        session.flush()
        for ph in client.phones:
            db_phone = models.Phone(user_id=db_user.id, phone=ph)
            session.add(db_phone)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="user already exists or constraint violated")

    session.refresh(db_user)
    phones = [p.phone for p in db_user.phones]
    return ClientResponse(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name,
        house_lat=db_user.house_lat,
        house_lon=db_user.house_lon,
        region_id=db_user.region_id,
        phones=phones,
    )


@app.get("/clients/{client_id}", response_model=ClientResponse)
def get_client(client_id: int, session: Session = Depends(get_session)):
    db_user = session.get(models.User, client_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="client not found")
    phones = [p.phone for p in db_user.phones]
    return ClientResponse(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name,
        house_lat=db_user.house_lat,
        house_lon=db_user.house_lon,
        region_id=db_user.region_id,
        phones=phones,
    )
