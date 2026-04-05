import argparse
import os
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from database.models import (
    Base,
    Courier,
    Delivery,
    Event,
    Item,
    KitchenType,
    Order,
    OrderItem,
    OrderStatus,
    Phone,
    Restaurant,
    User,
    VehicleType,
)


def build_database_url(
    db_user: str | None = None,
    db_password: str | None = None,
    db_host: str | None = None,
    db_port: str | None = None,
    db_name: str | None = None,
) -> str:
    db_user = db_user or os.getenv("DB_USER")
    db_password = db_password or os.getenv("DB_PASSWORD")
    db_host = db_host or os.getenv("DB_HOST")
    db_port = db_port or os.getenv("DB_PORT")
    db_name = db_name or os.getenv("DB_NAME")

    required = [db_user, db_password, db_host, db_port, db_name]
    if not all(required):
        raise ValueError("Missing DB settings. Set DB_USER, DB_PASSWORD, DB_HOST, DB_PORT and DB_NAME.")

    return f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def reset_tables(session: Session) -> None:
    # CASCADE handles FK dependencies; RESTART IDENTITY resets SERIAL counters.
    session.execute(
        text(
            """
            TRUNCATE TABLE
                event,
                delivery,
                order_item,
                orders,
                item,
                courier,
                restaurant,
                kitchen_type,
                phones,
                users
            RESTART IDENTITY CASCADE
            """
        )
    )


def seed_data(session: Session) -> None:
    kitchens = [
        KitchenType(type="Italian"),
        KitchenType(type="Japanese"),
        KitchenType(type="Brazilian"),
    ]
    session.add_all(kitchens)
    session.flush()

    restaurants = [
        Restaurant(name="Pasta House", lat=-23.5506, lon=-46.6333, kitchen_type_id=kitchens[0].id),
        Restaurant(name="Sushi Place", lat=-23.5580, lon=-46.6610, kitchen_type_id=kitchens[1].id),
        Restaurant(name="Casa Sul", lat=-30.0284, lon=-51.2287, kitchen_type_id=kitchens[2].id),
    ]
    session.add_all(restaurants)
    session.flush()

    users = [
        User(name="Joao Silva", email="joao@example.com", house_lat=-23.5700, house_lon=-46.6500),
        User(name="Maria Souza", email="maria@example.com", house_lat=-23.5400, house_lon=-46.6200),
        User(name="Ana Costa", email="ana@example.com", house_lat=-30.0350, house_lon=-51.2200),
    ]
    session.add_all(users)
    session.flush()

    phones = [
        Phone(user_id=users[0].id, phone="11999990001"),
        Phone(user_id=users[0].id, phone="11999990002"),
        Phone(user_id=users[1].id, phone="11999990003"),
        Phone(user_id=users[2].id, phone="51999990004"),
    ]
    session.add_all(phones)

    items = [
        Item(name="Spaghetti", price=Decimal("35.50"), restaurant_id=restaurants[0].id),
        Item(name="Lasagna", price=Decimal("42.00"), restaurant_id=restaurants[0].id),
        Item(name="Sushi Combo", price=Decimal("55.90"), restaurant_id=restaurants[1].id),
        Item(name="Temaki", price=Decimal("29.90"), restaurant_id=restaurants[1].id),
        Item(name="Churrasco", price=Decimal("64.90"), restaurant_id=restaurants[2].id),
        Item(name="Feijoada", price=Decimal("39.90"), restaurant_id=restaurants[2].id),
    ]
    session.add_all(items)
    session.flush()

    couriers = [
        Courier(name="Carlos Rider", vehicle=VehicleType.BIKE, lat=-23.5510, lon=-46.6340),
        Courier(name="Paula Moto", vehicle=VehicleType.MOTORCYCLE, lat=-23.5590, lon=-46.6600),
        Courier(name="Rafael Car", vehicle=VehicleType.CAR, lat=-30.0300, lon=-51.2300),
    ]
    session.add_all(couriers)
    session.flush()

    orders = [
        Order(restaurant_id=restaurants[0].id, user_id=users[0].id),
        Order(restaurant_id=restaurants[1].id, user_id=users[1].id),
        Order(restaurant_id=restaurants[2].id, user_id=users[2].id),
    ]
    session.add_all(orders)
    session.flush()

    order_items = [
        OrderItem(order_id=orders[0].id, item_id=items[0].id, quantity=2),
        OrderItem(order_id=orders[0].id, item_id=items[1].id, quantity=1),
        OrderItem(order_id=orders[1].id, item_id=items[2].id, quantity=1),
        OrderItem(order_id=orders[1].id, item_id=items[3].id, quantity=3),
        OrderItem(order_id=orders[2].id, item_id=items[4].id, quantity=1),
        OrderItem(order_id=orders[2].id, item_id=items[5].id, quantity=2),
    ]
    session.add_all(order_items)

    deliveries = [
        Delivery(order_id=orders[0].id, courier_id=couriers[0].id),
        Delivery(order_id=orders[1].id, courier_id=couriers[1].id),
        Delivery(order_id=orders[2].id, courier_id=couriers[2].id),
    ]
    session.add_all(deliveries)
    session.flush()

    events = [
        Event(delivery_id=deliveries[0].id, status=OrderStatus.CONFIRMED),
        Event(delivery_id=deliveries[0].id, status=OrderStatus.PREPARING),
        Event(delivery_id=deliveries[0].id, status=OrderStatus.READY_FOR_PICKUP),
        Event(delivery_id=deliveries[1].id, status=OrderStatus.CONFIRMED),
        Event(delivery_id=deliveries[1].id, status=OrderStatus.PICKED_UP),
        Event(delivery_id=deliveries[1].id, status=OrderStatus.IN_TRANSIT),
        Event(delivery_id=deliveries[2].id, status=OrderStatus.CONFIRMED),
        Event(delivery_id=deliveries[2].id, status=OrderStatus.DELIVERED),
    ]
    session.add_all(events)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate Postgres tables with test data.")
    parser.add_argument("--db-user", dest="db_user", help="Database user. Defaults to DB_USER.")
    parser.add_argument("--db-password", dest="db_password", help="Database password. Defaults to DB_PASSWORD.")
    parser.add_argument("--db-host", dest="db_host", help="Database host. Defaults to DB_HOST.")
    parser.add_argument("--db-port", dest="db_port", help="Database port. Defaults to DB_PORT.")
    parser.add_argument("--db-name", dest="db_name", help="Database name. Defaults to DB_NAME.")
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not clear existing rows before inserting seed data.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    database_url = build_database_url(
        db_user=args.db_user,
        db_password=args.db_password,
        db_host=args.db_host,
        db_port=args.db_port,
        db_name=args.db_name,
    )

    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        if not args.no_reset:
            reset_tables(session)
        seed_data(session)
        session.commit()

    print("Postgres seed completed successfully.")


if __name__ == "__main__":
    main()
