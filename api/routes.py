from fastapi import FastAPI, Depends, HTTPException
from api.models import (
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
    # db_restaurant = Restaurante(
    #     nome=restaurant.nome,
    #     lat=restaurant.lat,
    #     lon=restaurant.lon,
    #     kitchen_type_id=restaurant.kitchen_type_id
    # )

    # db.add(db_restaurant)
    # db.commit()
    # db.refresh(db_restaurant)

    # return db_restaurant
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
def get_user_order(user_email: str, order_id: int):
    # pedido = db.query(Pedido).filter(
    #     Pedido.id == order_id,
    #     Pedido.user_email == user_email
    # ).first()

    # if not pedido:
    #     raise HTTPException(status_code=404, detail="Pedido não encontrado")

    # return pedido
    pass


@app.get("/user/{user_id}/order", response_model=list[PedidoResponse])
def get_user_orders(user_email: str):
    pass


@app.get("/order/{order_id}/events", response_model=list[EventoResponse])
def get_order_events(order_id: int):
    pass