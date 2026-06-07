from fastapi import FastAPI, Depends, HTTPException
import os
import logging
from pydantic import BaseModel

from shared.database.connection import get_session
from shared.database import models
from shared import graph
from sqlalchemy.orm import Session


app = FastAPI(title="matching-service")

# Grafo carregado na inicialização (por cidade)
GRAPH = None


@app.on_event("startup")
def load_graph_on_startup():
    global GRAPH
    city = os.environ.get("CITY", "São Paulo, Brazil")
    mode = os.environ.get("GRAPH_MODE", "drive")
    logging.info("loading graph for %s (mode=%s)", city, mode)
    GRAPH = graph.get_or_download_graph(city=city, mode=mode)
    if GRAPH is None:
        logging.warning("graph not available for %s; matching will return 503 until graph is prepared", city)


class MatchRequest(BaseModel):
    order_id: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "matching"}


@app.post("/match")
def match(req: MatchRequest, session: Session = Depends(get_session)):
    """Atribuição simples: encontra o primeiro courier na mesma região do restaurante ou cria um courier 'auto'."""
    order = session.get(models.Order, req.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")

    restaurant = order.restaurant
    region_id = getattr(restaurant, "region_id", None)

    # Selecionar courier disponível (sem entregas ativas)
    # Um courier está indisponível se existe uma Delivery associada cuja última Event.status != DELIVERED
    subq = (
        session.query(models.Delivery.courier_id)
        .join(models.Event)
        .group_by(models.Delivery.courier_id)
        .having(models.Event.status != models.OrderStatus.DELIVERED)
        .subquery()
    )

    courier = (
        session.query(models.Courier)
        .filter(models.Courier.region_id == region_id)
        .filter(~models.Courier.id.in_(subq))
        .first()
    )
    if courier is None:
        courier = models.Courier(
            name="auto-courier",
            vehicle=models.VehicleType.BIKE,
            lat=restaurant.lat,
            lon=restaurant.lon,
            region_id=region_id,
        )
        session.add(courier)
        session.flush()

    delivery = models.Delivery(order_id=order.id, courier_id=courier.id)
    session.add(delivery)
    session.flush()

    # Criar evento inicial PREPARING associado à delivery
    ev = models.Event(status=models.OrderStatus.PREPARING, delivery=delivery)
    session.add(ev)
    # Antes de calcular rota, garantir que o grafo esteja carregado
    if GRAPH is None:
        raise HTTPException(status_code=503, detail="graph unavailable")

    # Calcular rota (placeholder) entre courier -> restaurant -> user
    try:
        route = graph.compute_route(
            start=(courier.lat, courier.lon),
            via=(restaurant.lat, restaurant.lon),
            end=(order.user.house_lat, order.user.house_lon),
        )
    except Exception:
        logging.exception("route compute failed")
        route = []

    session.commit()

    return {"delivery_id": delivery.id, "courier_id": courier.id, "route": route}


@app.get("/ready")
def ready():
    """Readiness probe: verifica conectividade com o banco."""
    try:
        s = next(get_session())
        s.execute("SELECT 1")
        s.close()
        return {"ready": True}
    except Exception:
        return {"ready": False}
