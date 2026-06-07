from fastapi import FastAPI, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List

from shared.database.connection import get_session
from shared.database import models
from sqlalchemy.orm import Session
import os
import requests


app = FastAPI(title="orders-service")


class OrderItemIn(BaseModel):
    item_id: int
    quantity: int = 1


class OrderIn(BaseModel):
    restaurant_id: int
    user_id: int
    items: List[OrderItemIn]


@app.get("/health")
def health():
    return {"status": "ok", "service": "orders"}


@app.post("/orders")
def create_order(
    order: OrderIn, background_tasks: BackgroundTasks, session: Session = Depends(get_session)
):
    """Cria um pedido simples e aciona matcher (se configurado via MATCHING_URL)."""
    # Valida existência de user e restaurant — operação atômica
    user = session.get(models.User, order.user_id)
    if user is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="user not found")

    restaurant = session.get(models.Restaurant, order.restaurant_id)
    if restaurant is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="restaurant not found")

    # Persistir Order e OrderItems dentro de transação explícita
    try:
        db_order = models.Order(restaurant_id=order.restaurant_id, user_id=order.user_id)
        session.add(db_order)
        session.flush()

        for it in order.items:
            db_item = models.OrderItem(order_id=db_order.id, item_id=it.item_id, quantity=it.quantity)
            session.add(db_item)

        session.commit()
    except Exception:
        session.rollback()
        raise

    # Chamar matching de forma assíncrona se variável estiver configurada
    matching_url = os.environ.get("MATCHING_URL")
    if matching_url:
        def call_match(order_id: int):
            try:
                requests.post(f"{matching_url}/match", json={"order_id": order_id}, timeout=5)
            except Exception:
                pass

        background_tasks.add_task(call_match, db_order.id)

    return {"order_id": db_order.id}


@app.get("/ready")
def ready():
    """Readiness probe: verifica conectividade com o banco."""
    try:
        # Sessão simples para verificar DB
        s = next(get_session())
        s.execute("SELECT 1")
        s.close()
        return {"ready": True}
    except Exception:
        return {"ready": False}
