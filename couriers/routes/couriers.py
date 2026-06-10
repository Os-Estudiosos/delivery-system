from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.database.connection import get_session
from shared.database.models import Courier, VehicleType
from couriers import repository

router = APIRouter(prefix="/courier", tags=["courier"]) 


# -------------------- Schemas --------------------
class CourierCreate(BaseModel):
    name: str
    vehicle: str
    lat: float
    lon: float
    region_id: int


class CourierUpdate(BaseModel):
    name: str | None = None
    vehicle: str | None = None
    lat: float | None = None
    lon: float | None = None
    region_id: int | None = None


class CourierResponse(BaseModel):
    id: int
    name: str
    vehicle: str
    lat: float
    lon: float
    region_id: int


# -------------------- Helpers --------------------
def _to_response(c: Courier) -> CourierResponse:
    return CourierResponse(
        id=c.id,
        name=c.name,
        vehicle=c.vehicle.value if isinstance(c.vehicle, VehicleType) else str(c.vehicle),
        lat=c.lat,
        lon=c.lon,
        region_id=c.region_id,
    )


def _get_or_404(courier_id: int, session: Session) -> Courier:
    db_courier = repository.get_courier(session, courier_id)
    if not db_courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found.")
    return db_courier


# -------------------- Endpoints --------------------
@router.get("/", response_model=list[CourierResponse])
def list_all(session: Session = Depends(get_session)):
    return [_to_response(c) for c in repository.list_couriers(session)]


@router.get("/{courier_id}", response_model=CourierResponse)
def get_one(courier_id: int, session: Session = Depends(get_session)):
    c = _get_or_404(courier_id, session)
    return _to_response(c)


@router.post("/", response_model=CourierResponse, status_code=status.HTTP_201_CREATED)
def create(courier: CourierCreate, session: Session = Depends(get_session)):
    db_c = repository.create_courier(
        session,
        name=courier.name,
        vehicle=courier.vehicle,
        lat=courier.lat,
        lon=courier.lon,
        region_id=courier.region_id,
    )
    if db_c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(db_c)


@router.patch("/{courier_id}", response_model=CourierResponse)
def patch(courier_id: int, courier: CourierUpdate, session: Session = Depends(get_session)):
    db_c = _get_or_404(courier_id, session)
    updated = repository.update_courier(
        session,
        db_c,
        name=courier.name,
        vehicle=courier.vehicle,
        lat=courier.lat,
        lon=courier.lon,
        region_id=courier.region_id,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found.")
    return _to_response(updated)


@router.delete("/{courier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(courier_id: int, session: Session = Depends(get_session)):
    db_c = _get_or_404(courier_id, session)
    repository.delete_courier(session, db_c)
