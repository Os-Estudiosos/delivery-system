from fastapi import FastAPI
from routes.models import (
    UsuarioCreate, UsuarioResponse,
    CourierCreate, CourierResponse,
    PedidoCreate, PedidoResponse,
    RestauranteCreate, RestauranteResponse,
    ItemCreate, ItemResponse,
    EntregaCreate, EntregaResponse,
    EventoCreate, EventoResponse
)

app = FastAPI()

@app.get("/")
def root():
    return {"Saudação": "Bem vindo a API da DijskFood!"}


@app.post("/user", response_model=UsuarioResponse)
def post_user(user:UsuarioCreate):
    pass


@app.post("/restaurant", response_model=RestauranteResponse)
def post_restaurant(restaurant: RestauranteCreate):
    pass


@app.post("/courier", response_model=CourierResponse)
def post_courier(courier: CourierCreate):
    pass


@app.post("/order", response_model=PedidoResponse)
def post_order(order: PedidoCreate):
    pass


@app.put("/courier/{courier_id}/position", response_model=CourierResponse)
def put_courier_position(courier_id: int):
    pass


@app.patch("/delivery/{delivery_id}/status", response_model=EntregaResponse)
def patch_delivery_status(delivery_id: int):
    pass


@app.get("/user/{user_id}/order/{order_id}", response_model=PedidoResponse)
def get_user_order(user_id: int, order_id: int):
    pass


@app.get("/user/{user_id}/order", response_model=list[PedidoResponse])
def get_user_orders(user_id: int):
    pass


@app.get("/order/{order_id}/events", response_model=list[EventoResponse])
def get_order_events(order_id: int):
    pass