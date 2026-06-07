from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
import os
import requests
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.database.connection import get_session
from shared.database.models import KitchenType, Event, OrderStatus
from shared.database import models

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


@router.post('/{order_id}/ready', tags=['order ready'])
def mark_order_ready(order_id: int, session: Session = Depends(get_session)):
    """Marca o pedido como READY_FOR_PICKUP criando um Event para a Delivery associada."""
    delivery = session.query(models.Delivery).filter(models.Delivery.order_id == order_id).first()
    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Delivery for order not found')

    # Validação da máquina de estados: último evento deve ser PREPARING
    last_ev = (
        session.query(models.Event)
        .filter(models.Event.delivery_id == delivery.id)
        .order_by(models.Event.updated_at.desc())
        .first()
    )
    if last_ev is None or last_ev.status != OrderStatus.PREPARING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid state transition: expected PREPARING",
        )

    ev = Event(status=OrderStatus.READY_FOR_PICKUP, delivery=delivery)
    session.add(ev)
    session.commit()

    # Notificação assíncrona ao serviço de couriers (se configurado)
    courier_id = delivery.courier_id
    courier_url = os.environ.get("COURIER_URL")

    def _notify_courier(courier_url: str, courier_id: int, order_id: int):
        if not courier_url:
            return
        try:
            requests.post(
                f"{courier_url.rstrip('/')}/notify",
                json={"courier_id": courier_id, "order_id": order_id},
                timeout=3,
            )
        except Exception:
            # Não falhar a operação principal por conta da notificação
            return

    # Agendar notificação em background
    try:
        bg: BackgroundTasks = BackgroundTasks()
        bg.add_task(_notify_courier, courier_url, courier_id, order_id)
    except Exception:
        pass

    return {"status": "ok", "order_id": order_id, "delivery_id": delivery.id}


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
