from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime
import enum


class VeiculoType(str, enum.Enum):
    BIKE = "BIKE"
    MOTO = "MOTO"
    CARRO = "CARRO"


class OrderStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"


class TelefoneBase(BaseModel):
    phone: str


class UsuarioBase(BaseModel):
    email: EmailStr
    nome: str
    house_lat: float
    house_lon: float


class UsuarioCreate(UsuarioBase):
    telefones: List[TelefoneBase]


class UsuarioResponse(UsuarioBase):
    telefones: List[TelefoneBase] = []
    class Config:
        from_attributes = True


class RestauranteBase(BaseModel):
    nome: str
    lat: float
    lon: float
    kitchen_type_id: int


class RestauranteCreate(RestauranteBase):
    pass


class RestauranteResponse(RestauranteBase):
    id: int
    class Config:
        from_attributes = True


class ItemBase(BaseModel):
    nome: str
    preco: float


class ItemCreate(ItemBase):
    restau_id: int


class ItemResponse(ItemBase):
    id: int

    class Config:
        from_attributes = True


class CourierBase(BaseModel):
    nome: str
    veiculo: VeiculoType
    lat: float
    lon: float


class CourierCreate(CourierBase):
    pass


class CourierResponse(CourierBase):
    id: int
    class Config:
        from_attributes = True


class PedidoItemCreate(BaseModel):
    item_id: int
    quantidade: int


class PedidoCreate(BaseModel):
    rest_id: int
    user_email: EmailStr
    itens: List[PedidoItemCreate]


class PedidoResponse(BaseModel):
    id: int
    rest_id: int
    user_email: EmailStr
    created_at: datetime
    class Config:
        from_attributes = True


class EntregaCreate(BaseModel):
    order_id: int
    courier_id: int


class EntregaResponse(BaseModel):
    id: int
    order_id: int
    courier_id: int
    class Config:
        from_attributes = True


class EventoCreate(BaseModel):
    order_id: int
    courier_id: int
    status: OrderStatus


class EventoResponse(BaseModel):
    id: int
    order_id: int
    courier_id: int
    status: OrderStatus
    updated_at: datetime
    class Config:
        from_attributes = True