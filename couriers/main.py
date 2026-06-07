from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal
from fastapi import HTTPException, Depends
from shared.database.connection import get_session
from shared.database import models
from sqlalchemy.orm import Session

app = FastAPI(title="couriers-service")


class NotifyRequest(BaseModel):
    courier_id: int
    order_id: int


class TransitionRequest(BaseModel):
    status: Literal[
        "PICKED_UP", "IN_TRANSIT", "DELIVERED"
    ]



class CourierCreate(BaseModel):
    name: str
    vehicle: Literal["BIKE", "MOTORCYCLE", "CAR"]
    lat: float
    lon: float
    region_id: int


class CourierResponse(BaseModel):
    id: int
    name: str
    vehicle: str
    lat: float
    lon: float
    region_id: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "couriers"}


@app.post("/notify")
def notify(req: NotifyRequest):
    # Endpoint simples que confirma recebimento da notificação. Em produção,
    # aqui poderia enviar push/socket/PN ao app do entregador.
    return {"status": "notified", "courier_id": req.courier_id, "order_id": req.order_id}


@app.post("/couriers", response_model=CourierResponse, status_code=201)
def create_courier(req: CourierCreate, session: Session = Depends(get_session)):
    # valida region
    region = session.get(models.Region, req.region_id)
    if not region:
        raise HTTPException(status_code=404, detail="region not found")

    try:
        courier = models.Courier(
            name=req.name,
            vehicle=models.VehicleType[req.vehicle],
            lat=req.lat,
            lon=req.lon,
            region_id=req.region_id,
        )
    except KeyError:
        raise HTTPException(status_code=400, detail="invalid vehicle type")

    session.add(courier)
    session.commit()
    session.refresh(courier)
    return CourierResponse(id=courier.id, name=courier.name, vehicle=courier.vehicle.name, lat=courier.lat, lon=courier.lon, region_id=courier.region_id)


@app.get("/couriers/{courier_id}", response_model=CourierResponse)
def get_courier(courier_id: int, session: Session = Depends(get_session)):
    c = session.get(models.Courier, courier_id)
    if not c:
        raise HTTPException(status_code=404, detail="courier not found")
    return CourierResponse(id=c.id, name=c.name, vehicle=c.vehicle.name, lat=c.lat, lon=c.lon, region_id=c.region_id)


@app.post("/delivery/{delivery_id}/transition")
def delivery_transition(delivery_id: int, req: TransitionRequest, session: Session = Depends(get_session)):
    # Validação de máquina de estados: permite apenas transições válidas
    delivery = session.get(models.Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="delivery not found")

    last_ev = (
        session.query(models.Event)
        .filter(models.Event.delivery_id == delivery.id)
        .order_by(models.Event.updated_at.desc())
        .first()
    )

    # Mapeamento de transições válidas
    allowed = {
        "PREPARING": ["READY_FOR_PICKUP"],
        "READY_FOR_PICKUP": ["PICKED_UP"],
        "PICKED_UP": ["IN_TRANSIT"],
        "IN_TRANSIT": ["DELIVERED"],
    }

    current = last_ev.status.name if last_ev is not None else None
    desired = req.status

    if current is None:
        raise HTTPException(status_code=400, detail="no current state for delivery")

    if desired not in allowed.get(current, []):
        raise HTTPException(status_code=400, detail=f"invalid transition from {current} to {desired}")

    # Criar novo evento
    new_ev = models.Event(status=models.OrderStatus[desired], delivery=delivery)
    session.add(new_ev)
    session.commit()

    return {"status": "ok", "delivery_id": delivery.id, "new_state": desired}
