from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import KitchenType

router = APIRouter(prefix='/kitchen', tags=['kitchen'])

class KitchenCreate(BaseModel):
    type: str


class KitchenResponse(BaseModel):
    id: int
    type: str


@router.get('/', tags=['get kitchens'])
def get_kitchens(session: Session = Depends(get_session)):
    kitchens = session.query(KitchenType).all()
    return [KitchenResponse(id=kitchen.id, type=kitchen.type) for kitchen in kitchens]


@router.get('/{kitchen_id}', tags=['get kitchen by id'])
def get_kitchen(kitchen_id: int, session: Session = Depends(get_session)):
    kitchen = session.query(KitchenType).filter(KitchenType.id == kitchen_id).first()
    if not kitchen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Kitchen not found.',
        )
    return KitchenResponse(id=kitchen.id, type=kitchen.type)


@router.post('/', tags=['create kitchen'])
def create_kitchen(kitchen: KitchenCreate, session: Session = Depends(get_session)):
    db_kitchen = KitchenType(
        type=kitchen.type,
    )

    session.add(db_kitchen)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Kitchen already exists or payload violates constraints.',
        )

    session.refresh(db_kitchen)

    return KitchenResponse(
        id=db_kitchen.id,
        type=db_kitchen.type,
    )


@router.patch('/{kitchen_id}', tags=['update kitchen'])
def update_kitchen(kitchen_id: int, kitchen: KitchenCreate, session: Session = Depends(get_session)):
    db_kitchen = session.query(KitchenType).filter(KitchenType.id == kitchen_id).first()
    if not db_kitchen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Kitchen not found.',
        )

    db_kitchen.type = kitchen.type

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Kitchen already exists or payload violates constraints.',
        )

    session.refresh(db_kitchen)

    return KitchenResponse(
        id=db_kitchen.id,
        type=db_kitchen.type,
    )
