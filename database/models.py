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
import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv

load_dotenv()


class Base(DeclarativeBase):
    pass


## ENUMs
class VehicleType(enum.Enum):
    BIKE = "BIKE"
    MOTORCYCLE = "MOTORCYCLE"
    CAR = "CAR"


class OrderStatus(enum.Enum):
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"


## TABLES
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    house_lat = Column(Double, nullable=False)
    house_lon = Column(Double, nullable=False)

    phones = relationship("Phone", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user")


class Phone(Base):
    __tablename__ = "phones"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    phone = Column(String(20), primary_key=True)

    user = relationship("User", back_populates="phones")


class KitchenType(Base):
    __tablename__ = "kitchen_type"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(100), nullable=False, unique=True)

    restaurants = relationship("Restaurant", back_populates="kitchen_type")


class Restaurant(Base):
    __tablename__ = "restaurant"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(255), nullable=False)
    lat             = Column(Double, nullable=False)
    lon             = Column(Double, nullable=False)
    kitchen_type_id = Column(Integer, ForeignKey("kitchen_type.id"), nullable=False)

    kitchen_type = relationship("KitchenType", back_populates="restaurants")
    items = relationship("Item", back_populates="restaurant", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="restaurant")


class Item(Base):
    __tablename__ = "item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    restaurant_id = Column(Integer, ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (CheckConstraint("price >= 0", name="item_price_nonneg"),)

    restaurant = relationship("Restaurant", back_populates="items")
    order_items = relationship("OrderItem", back_populates="item")


class Courier(Base):
    __tablename__ = "courier"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    vehicle = Column(Enum(VehicleType, name="vehicle_type"), nullable=False)
    lat = Column(Double, nullable=False)
    lon = Column(Double, nullable=False)

    deliveries = relationship("Delivery", back_populates="courier")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    restaurant_id = Column(Integer, ForeignKey("restaurant.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    restaurant = relationship("Restaurant", back_populates="orders")
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    delivery = relationship("Delivery", back_populates="order", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_item"

    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)
    item_id = Column(Integer, ForeignKey("item.id"), primary_key=True)
    quantity = Column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("quantity > 0", name="order_item_qty_pos"),)

    order = relationship("Order", back_populates="items")
    item = relationship("Item", back_populates="order_items")


class Delivery(Base):
    __tablename__ = "delivery"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, unique=True)
    courier_id = Column(Integer, ForeignKey("courier.id"), nullable=False)

    order = relationship("Order", back_populates="delivery")
    courier = relationship("Courier", back_populates="deliveries")
    events = relationship("Event", back_populates="delivery", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status     = Column(Enum(OrderStatus, name="order_status"), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    delivery_id = Column(Integer, ForeignKey("delivery.id", ondelete="CASCADE"), nullable=False)

    delivery = relationship("Delivery", back_populates="events")