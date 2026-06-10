from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from shared.database.models import User, Region


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
