from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from shared.database.models import Courier, VehicleType, Region


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