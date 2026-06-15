from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from shared.database.models import Courier, VehicleType, Region


def list_couriers(session: Session) -> list[Courier]:
    return session.query(Courier).all()


def get_courier(session: Session, courier_id: int) -> Courier | None:
    return session.query(Courier).filter(Courier.id == courier_id).first()


def create_courier(session: Session, *, name: str, vehicle: str, lat: float, lon: float) -> Courier:
    v = VehicleType(vehicle)
    db_courier = Courier(name=name, vehicle=v, lat=lat, lon=lon)
    session.add(db_courier)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise
    session.refresh(db_courier)
    return db_courier


def update_courier(session: Session, courier: Courier, *, name: str | None = None, vehicle: str | None = None, lat: float | None = None, lon: float | None = None) -> Courier:

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