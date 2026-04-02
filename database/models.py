import enum
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


## ENUMs
class VeiculoType(enum.Enum):
    BIKE = "BIKE"
    MOTO = "MOTO"
    CARRO = "CARRO"


class OrderStatus(enum.Enum):
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"


## TABELAS
class Usuario(Base):
    __tablename__ = "usuario"

    email     = Column(String(255), primary_key=True)
    nome      = Column(String(255), nullable=False)
    house_lat = Column(Double, nullable=False)
    house_lon = Column(Double, nullable=False)

    telefones = relationship("Telefone", back_populates="usuario", cascade="all, delete-orphan")
    pedidos   = relationship("Pedido", back_populates="usuario")


class Telefone(Base):
    __tablename__ = "telefone"

    user_email = Column(String(255), ForeignKey("usuario.email", ondelete="CASCADE"), primary_key=True)
    phone      = Column(String(20), primary_key=True)

    usuario = relationship("Usuario", back_populates="telefones")


class TipoCozinha(Base):
    __tablename__ = "tipo_cozinha"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    tipo = Column(String(100), nullable=False, unique=True)

    restaurantes = relationship("Restaurante", back_populates="tipo_cozinha")


class Restaurante(Base):
    __tablename__ = "restaurante"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    nome            = Column(String(255), nullable=False)
    lat             = Column(Double, nullable=False)
    lon             = Column(Double, nullable=False)
    kitchen_type_id = Column(Integer, ForeignKey("tipo_cozinha.id"), nullable=False)

    tipo_cozinha = relationship("TipoCozinha", back_populates="restaurantes")
    itens        = relationship("Item", back_populates="restaurante", cascade="all, delete-orphan")
    pedidos      = relationship("Pedido", back_populates="restaurante")


class Item(Base):
    __tablename__ = "item"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    nome      = Column(String(255), nullable=False)
    preco     = Column(Numeric(10, 2), nullable=False)
    restau_id = Column(Integer, ForeignKey("restaurante.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (CheckConstraint("preco >= 0", name="item_preco_nonneg"),)

    restaurante  = relationship("Restaurante", back_populates="itens")
    pedido_itens = relationship("PedidoItem", back_populates="item")


class Courier(Base):
    __tablename__ = "courier"

    id      = Column(Integer, primary_key=True, autoincrement=True)
    nome    = Column(String(255), nullable=False)
    veiculo = Column(Enum(VeiculoType, name="veiculo_type"), nullable=False)
    lat     = Column(Double, nullable=False)
    lon     = Column(Double, nullable=False)

    entregas = relationship("Entrega", back_populates="courier")
    eventos  = relationship("Evento", back_populates="courier")


class Pedido(Base):
    __tablename__ = "pedido"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    rest_id    = Column(Integer, ForeignKey("restaurante.id"), nullable=False)
    user_email = Column(String(255), ForeignKey("usuario.email"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    restaurante = relationship("Restaurante", back_populates="pedidos")
    usuario     = relationship("Usuario", back_populates="pedidos")
    itens       = relationship("PedidoItem", back_populates="pedido", cascade="all, delete-orphan")
    entrega     = relationship("Entrega", back_populates="pedido", uselist=False)
    eventos     = relationship("Evento", back_populates="pedido")


class PedidoItem(Base):
    __tablename__ = "pedido_item"

    pedido_id  = Column(Integer, ForeignKey("pedido.id", ondelete="CASCADE"), primary_key=True)
    item_id    = Column(Integer, ForeignKey("item.id"), primary_key=True)
    quantidade = Column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("quantidade > 0", name="pedido_item_qtd_pos"),)

    pedido = relationship("Pedido", back_populates="itens")
    item   = relationship("Item", back_populates="pedido_itens")


class Entrega(Base):
    __tablename__ = "entrega"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    order_id   = Column(Integer, ForeignKey("pedido.id"), nullable=False, unique=True)
    courier_id = Column(Integer, ForeignKey("courier.id"), nullable=False)

    pedido  = relationship("Pedido", back_populates="entrega")
    courier = relationship("Courier", back_populates="entregas")


class Evento(Base):
    __tablename__ = "evento"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    status     = Column(Enum(OrderStatus, name="order_status"), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    order_id   = Column(Integer, ForeignKey("pedido.id"), nullable=False)
    courier_id = Column(Integer, ForeignKey("courier.id"), nullable=False)

    pedido  = relationship("Pedido", back_populates="eventos")
    courier = relationship("Courier", back_populates="eventos")
