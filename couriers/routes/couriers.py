from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from shared.database.connection import get_session
from shared.database.models import Courier, VehicleType, Region

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


def list_couriers(session: Session) -> list[Courier]:
    return session.query(Courier).all()


def get_courier(session: Session, courier_id: int) -> Courier | None:
    return session.query(Courier).filter(Courier.id == courier_id).first()


def create_courier(session: Session, *, name: str, vehicle: str, lat: float, lon: float, region_id: int) -> Courier:
    # ensure region exists
    region = session.query(Region).filter(Region.id == region_id).first()
    if not region:
        return None

    v = VehicleType(vehicle)
    db_courier = Courier(name=name, vehicle=v, lat=lat, lon=lon, region_id=region_id)
    session.add(db_courier)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise
    session.refresh(db_courier)
    return db_courier


def update_courier(session: Session, courier: Courier, *, name: str | None = None, vehicle: str | None = None, lat: float | None = None, lon: float | None = None, region_id: int | None = None) -> Courier:
    if region_id is not None:
        region = session.query(Region).filter(Region.id == region_id).first()
        if not region:
            return None
        courier.region_id = region_id

    if name is not None:
        courier.name = name
    if vehicle is not None:
        courier.vehicle = VehicleType(vehicle)
    if lat is not None:
        courier.lat = lat
    if lon is not None:
        courier.lon = lon

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise

    session.refresh(courier)
    return courier


def delete_courier(session: Session, courier: Courier) -> None:
    session.delete(courier)
    session.commit()


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
    db_courier = get_courier(session, courier_id)
    if not db_courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found.")
    return db_courier


# -------------------- Endpoints --------------------
@router.get("/", response_model=list[CourierResponse])
def list_all(session: Session = Depends(get_session)):
    return [_to_response(c) for c in list_couriers(session)]


@router.get("/{courier_id}", response_model=CourierResponse)
def get_one(courier_id: int, session: Session = Depends(get_session)):
    c = _get_or_404(courier_id, session)
    return _to_response(c)


@router.post("/", response_model=CourierResponse, status_code=status.HTTP_201_CREATED)
def create(courier: CourierCreate, session: Session = Depends(get_session)):
    db_c = create_courier(
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
    updated = update_courier(
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
    delete_courier(session, db_c)
