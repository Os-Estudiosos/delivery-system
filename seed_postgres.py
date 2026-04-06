import argparse
import os
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path

from dotenv import load_dotenv
import boto3
import osmnx as ox
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from database.create_graph import download_graph, load_graph_cache, save_graph_cache
from database.dynamo_table import TABLE_NAME, create_table, table_exists
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


STATUS_FLOW: list[OrderStatus] = [
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY_FOR_PICKUP,
    OrderStatus.PICKED_UP,
    OrderStatus.IN_TRANSIT,
    OrderStatus.DELIVERED,
]


def get_resource_and_client():
    region = os.environ.get("AWS_REGION", "us-east-1")
    project_env = os.environ.get("PROJECT_ENV", "production").lower()

    if project_env == "development":
        endpoint_url = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8001")
        local_key = os.environ.get("AWS_ACCESS_KEY_ID", "local")
        local_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "local")
        session = boto3.Session(
            region_name=region,
            aws_access_key_id=local_key,
            aws_secret_access_key=local_secret,
        )
        return (
            session.resource("dynamodb", endpoint_url=endpoint_url),
            session.client("dynamodb", endpoint_url=endpoint_url),
        )

    session = boto3.Session(
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )
    return session.resource("dynamodb"), session.client("dynamodb")


def build_dynamodb_endpoint(
    dydb_host: str | None = None,
    dydb_port: str | None = None,
) -> str:
    host = dydb_host or os.getenv("DYDB_HOST") or "localhost"
    port = dydb_port or os.getenv("DYDB_PORT") or "8001"
    return f"http://{host}:{port}"


def get_resource_and_client_for_seed(
    dydb_host: str | None = None,
    dydb_port: str | None = None,
):
    region = os.environ.get("AWS_REGION", "us-east-1")
    project_env = os.environ.get("PROJECT_ENV", "production").lower()

    if project_env == "development":
        if dydb_host or dydb_port:
            endpoint_url = build_dynamodb_endpoint(
                dydb_host=dydb_host,
                dydb_port=dydb_port,
            )
        else:
            endpoint_url = os.environ.get("DYNAMODB_ENDPOINT") or build_dynamodb_endpoint()
        local_key = os.environ.get("AWS_ACCESS_KEY_ID", "local")
        local_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "local")
        session = boto3.Session(
            region_name=region,
            aws_access_key_id=local_key,
            aws_secret_access_key=local_secret,
        )
        return (
            session.resource("dynamodb", endpoint_url=endpoint_url),
            session.client("dynamodb", endpoint_url=endpoint_url),
        )

    return get_resource_and_client()


def validate_delivery_event_flow(delivery_statuses: list[list[OrderStatus]]) -> None:
    for index, statuses in enumerate(delivery_statuses, start=1):
        if not statuses:
            raise ValueError(f"Delivery #{index} must have at least one event.")

        expected_prefix = STATUS_FLOW[: len(statuses)]
        if statuses != expected_prefix:
            raise ValueError(
                f"Delivery #{index} has an invalid event order: {statuses}. "
                f"Expected contiguous prefix: {expected_prefix}."
            )

        # A courier can only be associated once order reached READY_FOR_PICKUP.
        if OrderStatus.READY_FOR_PICKUP not in statuses:
            raise ValueError(
                f"Delivery #{index} cannot be assigned before READY_FOR_PICKUP is reached."
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
    graph = _load_graph_for_simulation()
    seed_nodes = list(islice(graph.nodes(data=True), 6))
    if len(seed_nodes) < 6:
        raise ValueError("Graph must contain at least 6 nodes to seed restaurants and couriers.")

    restaurant_positions = [
        (float(seed_nodes[0][1]["y"]), float(seed_nodes[0][1]["x"])),
        (float(seed_nodes[1][1]["y"]), float(seed_nodes[1][1]["x"])),
        (float(seed_nodes[2][1]["y"]), float(seed_nodes[2][1]["x"])),
    ]
    courier_positions = [
        (float(seed_nodes[3][1]["y"]), float(seed_nodes[3][1]["x"])),
        (float(seed_nodes[4][1]["y"]), float(seed_nodes[4][1]["x"])),
        (float(seed_nodes[5][1]["y"]), float(seed_nodes[5][1]["x"])),
    ]

    kitchens = [
        KitchenType(type="Italian"),
        KitchenType(type="Japanese"),
        KitchenType(type="Brazilian"),
    ]
    session.add_all(kitchens)
    session.flush()

    restaurants = [
        Restaurant(name="Pasta House", lat=restaurant_positions[0][0], lon=restaurant_positions[0][1], kitchen_type_id=kitchens[0].id),
        Restaurant(name="Sushi Place", lat=restaurant_positions[1][0], lon=restaurant_positions[1][1], kitchen_type_id=kitchens[1].id),
        Restaurant(name="Casa Sul", lat=restaurant_positions[2][0], lon=restaurant_positions[2][1], kitchen_type_id=kitchens[2].id),
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
        Courier(name="Carlos Rider", vehicle=VehicleType.BIKE, lat=courier_positions[0][0], lon=courier_positions[0][1]),
        Courier(name="Paula Moto", vehicle=VehicleType.MOTORCYCLE, lat=courier_positions[1][0], lon=courier_positions[1][1]),
        Courier(name="Rafael Car", vehicle=VehicleType.CAR, lat=courier_positions[2][0], lon=courier_positions[2][1]),
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

    delivery_event_flow = [
        [
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
        ],
        [
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
            OrderStatus.PICKED_UP,
            OrderStatus.IN_TRANSIT,
        ],
        [
            OrderStatus.CONFIRMED,
            OrderStatus.PREPARING,
            OrderStatus.READY_FOR_PICKUP,
            OrderStatus.PICKED_UP,
            OrderStatus.IN_TRANSIT,
            OrderStatus.DELIVERED,
        ],
    ]

    validate_delivery_event_flow(delivery_event_flow)

    events: list[Event] = []
    for delivery, statuses in zip(deliveries, delivery_event_flow):
        for status in statuses:
            events.append(Event(delivery_id=delivery.id, status=status))

    session.add_all(events)


def _load_graph_for_simulation():
    graph_cache_path = Path("cache/cache_graph.graphml")
    graph = load_graph_cache(graph_cache_path)
    if graph is None:
        graph = download_graph("Sao Paulo, Brazil", "drive")
        save_graph_cache(graph, graph_cache_path)
    return graph


def _delete_all_dynamo_items(table) -> None:
    scan_kwargs = {
        "ProjectionExpression": "courier_id, #ts",
        "ExpressionAttributeNames": {"#ts": "timestamp"},
    }

    while True:
        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])

        if items:
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(
                        Key={
                            "courier_id": item["courier_id"],
                            "timestamp": item["timestamp"],
                        }
                    )

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

        scan_kwargs["ExclusiveStartKey"] = last_evaluated_key


def seed_dynamo_positions(
    session: Session,
    should_reset: bool,
    dydb_host: str | None = None,
    dydb_port: str | None = None,
) -> None:
    ddb_resource, ddb_client = get_resource_and_client_for_seed(
        dydb_host=dydb_host,
        dydb_port=dydb_port,
    )

    if not table_exists(ddb_client):
        create_table(ddb_resource)

    table = ddb_resource.Table(TABLE_NAME)

    if should_reset:
        _delete_all_dynamo_items(table)

    graph = _load_graph_for_simulation()
    deliveries = session.query(Delivery).all()
    base_time = datetime.now(timezone.utc)

    with table.batch_writer() as batch:
        for delivery_index, delivery in enumerate(deliveries):
            order = delivery.order
            if not order:
                continue

            origin_node = ox.nearest_nodes(
                graph,
                X=order.restaurant.lon,
                Y=order.restaurant.lat,
            )
            destination_node = ox.nearest_nodes(
                graph,
                X=order.user.house_lon,
                Y=order.user.house_lat,
            )

            node_path = ox.shortest_path(graph, origin_node, destination_node, weight="length")
            if not node_path:
                node_path = [origin_node]

            for step_index, node_id in enumerate(node_path):
                node_data = graph.nodes[node_id]
                timestamp = (base_time + timedelta(seconds=(delivery_index * 1000) + step_index)).isoformat()
                batch.put_item(
                    Item={
                        "courier_id": int(delivery.courier_id),
                        "timestamp": timestamp,
                        "delivery_id": str(delivery.id),
                        "lat_courier": Decimal(str(node_data["y"])),
                        "lon_courier": Decimal(str(node_data["x"])),
                    }
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate Postgres tables with test data.")
    parser.add_argument("--db-user", dest="db_user", help="Database user. Defaults to DB_USER.")
    parser.add_argument("--db-password", dest="db_password", help="Database password. Defaults to DB_PASSWORD.")
    parser.add_argument("--db-host", dest="db_host", help="Database host. Defaults to DB_HOST.")
    parser.add_argument("--db-port", dest="db_port", help="Database port. Defaults to DB_PORT.")
    parser.add_argument("--db-name", dest="db_name", help="Database name. Defaults to DB_NAME.")
    parser.add_argument(
        "--dydb-host",
        dest="dydb_host",
        help="DynamoDB host for development runs. Defaults to DYDB_HOST or localhost.",
    )
    parser.add_argument(
        "--dydb-port",
        dest="dydb_port",
        help="DynamoDB port for development runs. Defaults to DYDB_PORT or 8001.",
    )
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

        seed_dynamo_positions(
            session,
            should_reset=not args.no_reset,
            dydb_host=args.dydb_host,
            dydb_port=args.dydb_port,
        )

    print("Postgres + DynamoDB seed completed successfully.")


if __name__ == "__main__":
    main()
