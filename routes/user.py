from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import Phone, User

router = APIRouter()

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    house_lat: float
    house_lon: float
    phones: list[str] = []


class UserResponse(BaseModel):
    name: str
    email: str
    house_lat: float
    house_lon: float
    phones: list[str]


@router.post('/user', tags=['user'])
def create_user(user: UserCreate, session: Session = Depends(get_session)):
    db_user = User(
        email=user.email,
        name=user.name,
        house_lat=user.house_lat,
        house_lon=user.house_lon,
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
        name=db_user.name,
        email=db_user.email,
        house_lat=db_user.house_lat,
        house_lon=db_user.house_lon,
        phones=[phone.phone for phone in db_user.phones],
    )
