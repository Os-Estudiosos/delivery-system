"""
seed.py — CidadeX delivery platform
Populates the local PostgreSQL database with realistic data for dashboard analytics.

Regions:   3 (São Paulo, Rio de Janeiro, Belo Horizonte)
Users:     ~30 (distributed across regions)
Couriers:  ~15 (3× users per region × 3 regions, mixed vehicles)
Kitchens:  8 types
Restaurants: 18 (6 per region)
Items:     ~90 (5 per restaurant)
Orders:    ~200 (spanning the last 90 days)
Events:    ~800 (lifecycle per order)

Usage (run from the repo root):
    cd analytics
    uv run seed.py
    # ou
    DB_URL=postgresql://user:pass@localhost:5432/dbname uv run seed.py
"""

import os
import sys
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# ── resolve shared/ from repo root ──────────────────────────────────────────
# analytics/seed.py  →  ../shared
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# ── models from shared/database/models.py ───────────────────────────────────
from shared.database.models import (
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
    Region,
    Restaurant,
    User,
    VehicleType,
)

load_dotenv()

# ── config ───────────────────────────────────────────────────────────────────
DB_URL = os.getenv(
    "DB_URL",
    "postgresql://postgres:postgres@localhost:5432/dijkfood",
)
SEED = 42
random.seed(SEED)
fake = Faker("pt_BR")
fake.seed_instance(SEED)

# ── geo bounding boxes (lat_min, lat_max, lon_min, lon_max) ──────────────────
GEO = {
    "São Paulo":       (-23.65, -23.48, -46.73, -46.57),
    "Rio de Janeiro":  (-23.02, -22.85, -43.45, -43.17),
    "Belo Horizonte":  (-20.05, -19.83, -44.05, -43.87),
}


def rand_coord(region_name: str) -> tuple[float, float]:
    lat_min, lat_max, lon_min, lon_max = GEO[region_name]
    return (
        round(random.uniform(lat_min, lat_max), 6),
        round(random.uniform(lon_min, lon_max), 6),
    )


def rand_ts(days_back: int = 90) -> datetime:
    """Random timezone-aware timestamp within the last N days."""
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return datetime.now(timezone.utc) - delta


# ── kitchen types ─────────────────────────────────────────────────────────────
KITCHEN_TYPES = [
    "Brasileira",
    "Japonesa",
    "Italiana",
    "Árabe",
    "Americana",
    "Mexicana",
    "Chinesa",
    "Vegana",
]

# ── restaurant templates per kitchen type ────────────────────────────────────
RESTAURANT_TEMPLATES: dict[str, list[dict]] = {
    "Brasileira": [
        {
            "name": "Churrascaria do Pedrão",
            "items": [
                ("Picanha 300g", 69.90),
                ("Costela Assada", 54.90),
                ("Frango Grelhado", 38.90),
                ("Feijão Tropeiro", 22.50),
                ("Farofa Especial", 12.00),
            ],
        },
        {
            "name": "Boteco da Dona Maria",
            "items": [
                ("Feijoada Completa", 49.90),
                ("Bolinho de Bacalhau (6un)", 28.00),
                ("Coxinha Caipira (4un)", 18.00),
                ("Pão de Queijo (6un)", 14.00),
                ("Caldo de Feijão", 16.50),
            ],
        },
    ],
    "Japonesa": [
        {
            "name": "Sushi Hanami",
            "items": [
                ("Combo Sashimi 20 peças", 89.90),
                ("Hot Philadelphia 8un", 42.00),
                ("Temaki Salmão", 35.00),
                ("Yakissoba de Frango", 38.50),
                ("Missoshiru", 12.00),
            ],
        },
        {
            "name": "Ramen do Kenji",
            "items": [
                ("Tonkotsu Ramen", 52.00),
                ("Shoyu Ramen", 48.00),
                ("Gyoza Frito (6un)", 28.00),
                ("Edamame", 18.00),
                ("Karaage de Frango", 36.00),
            ],
        },
    ],
    "Italiana": [
        {
            "name": "Trattoria Bella Napoli",
            "items": [
                ("Pizza Margherita (M)", 49.90),
                ("Pizza Calabresa (G)", 62.00),
                ("Lasanha à Bolonhesa", 44.00),
                ("Risoto de Funghi", 48.00),
                ("Tiramisù", 22.00),
            ],
        },
        {
            "name": "Pasta & Basta",
            "items": [
                ("Espaguete ao Alho e Óleo", 34.00),
                ("Fettuccine Carbonara", 42.00),
                ("Penne Arrabbiata", 36.00),
                ("Gnocchi ao Molho Rosa", 38.00),
                ("Panna Cotta", 18.00),
            ],
        },
    ],
    "Árabe": [
        {
            "name": "Habib's do Oriente",
            "items": [
                ("Esfiha de Carne (6un)", 24.00),
                ("Kibe Assado (4un)", 28.00),
                ("Homus com Pita", 22.00),
                ("Shawarma de Frango", 36.00),
                ("Baklava (4un)", 16.00),
            ],
        },
    ],
    "Americana": [
        {
            "name": "Big Smoke Burgers",
            "items": [
                ("Classic Smash Burger", 42.00),
                ("Bacon BBQ Burger", 48.00),
                ("Batata Frita Grande", 18.00),
                ("Onion Rings (8un)", 22.00),
                ("Milkshake Chocolate", 28.00),
            ],
        },
    ],
    "Mexicana": [
        {
            "name": "El Taco Loco",
            "items": [
                ("Tacos de Carnitas (3un)", 36.00),
                ("Burrito de Frango", 42.00),
                ("Nachos com Guacamole", 32.00),
                ("Quesadilla de Queijo", 28.00),
                ("Churros com Doce de Leite (4un)", 18.00),
            ],
        },
    ],
    "Chinesa": [
        {
            "name": "Dragão Dourado",
            "items": [
                ("Frango Xadrez", 38.00),
                ("Porco Agridoce", 42.00),
                ("Rolinho Primavera (4un)", 24.00),
                ("Chow Mein de Legumes", 32.00),
                ("Sopa Won Ton", 22.00),
            ],
        },
    ],
    "Vegana": [
        {
            "name": "Raízes Vivas",
            "items": [
                ("Bowl Buddha", 38.00),
                ("Hambúrguer de Grão-de-Bico", 36.00),
                ("Wrap de Tofu Grelhado", 32.00),
                ("Salada Quinoa Tropical", 28.00),
                ("Açaí 500ml com Granola", 24.00),
            ],
        },
    ],
}

# ── vehicle distribution weights ─────────────────────────────────────────────
VEHICLE_WEIGHTS = [
    (VehicleType.BIKE, 0.35),
    (VehicleType.MOTORCYCLE, 0.50),
    (VehicleType.CAR, 0.15),
]

# ── order status lifecycle ────────────────────────────────────────────────────
# Each tuple: (status, minutes_after_previous)
LIFECYCLE_FULL = [
    (OrderStatus.CONFIRMED,       0),
    (OrderStatus.PREPARING,       2),
    (OrderStatus.READY_FOR_PICKUP, 18),
    (OrderStatus.PICKED_UP,       25),
    (OrderStatus.IN_TRANSIT,      27),
    (OrderStatus.DELIVERED,       45),
]

LIFECYCLE_PARTIAL: dict[str, list] = {
    "confirmed_only":   LIFECYCLE_FULL[:1],
    "preparing":        LIFECYCLE_FULL[:2],
    "ready":            LIFECYCLE_FULL[:3],
    "picked_up":        LIFECYCLE_FULL[:4],
    "in_transit":       LIFECYCLE_FULL[:5],
    "delivered":        LIFECYCLE_FULL,
}

# weight for how far along orders are (older orders more likely to be delivered)
LIFECYCLE_CHOICES = [
    ("delivered",      0.70),
    ("in_transit",     0.08),
    ("picked_up",      0.05),
    ("ready",          0.05),
    ("preparing",      0.07),
    ("confirmed_only", 0.05),
]


def pick_lifecycle() -> list:
    r = random.random()
    cumulative = 0.0
    for name, w in LIFECYCLE_CHOICES:
        cumulative += w
        if r < cumulative:
            return LIFECYCLE_PARTIAL[name]
    return LIFECYCLE_FULL


def pick_vehicle() -> VehicleType:
    r = random.random()
    cumulative = 0.0
    for vtype, w in VEHICLE_WEIGHTS:
        cumulative += w
        if r < cumulative:
            return vtype
    return VehicleType.MOTORCYCLE


# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    engine = create_engine(DB_URL, echo=False)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # ── clean slate ──────────────────────────────────────────────────────
        print("🧹  Limpando dados existentes…")
        session.execute(text("TRUNCATE event, delivery, order_item, orders, courier, item, restaurant, kitchen_type, phones, users, region RESTART IDENTITY CASCADE"))
        session.commit()

        # ── regions ──────────────────────────────────────────────────────────
        print("📍  Criando regiões…")
        regions: dict[str, Region] = {}
        for region_name in GEO:
            r = Region(name=region_name)
            session.add(r)
            regions[region_name] = r
        session.flush()

        # ── kitchen types ────────────────────────────────────────────────────
        print("🍽️   Criando tipos de cozinha…")
        kitchen_map: dict[str, KitchenType] = {}
        for kt_name in KITCHEN_TYPES:
            kt = KitchenType(type=kt_name)
            session.add(kt)
            kitchen_map[kt_name] = kt
        session.flush()

        # ── restaurants + items ──────────────────────────────────────────────
        print("🏪  Criando restaurantes e itens…")
        all_restaurants: list[Restaurant] = []
        # Each region gets every kitchen type represented (round-robin if needed)
        for region_name, region_obj in regions.items():
            for kt_name, templates in RESTAURANT_TEMPLATES.items():
                template = random.choice(templates)
                lat, lon = rand_coord(region_name)
                rest = Restaurant(
                    name=f"{template['name']} — {region_name.split()[0]}",
                    lat=lat,
                    lon=lon,
                    kitchen_type_id=kitchen_map[kt_name].id,
                    region_id=region_obj.id,
                )
                session.add(rest)
                session.flush()

                for item_name, base_price in template["items"]:
                    # slight price variation per region
                    price = round(base_price * random.uniform(0.92, 1.12), 2)
                    item = Item(
                        name=item_name,
                        price=Decimal(str(price)),
                        restaurant_id=rest.id,
                    )
                    session.add(item)
                all_restaurants.append(rest)
        session.flush()

        # ── users ────────────────────────────────────────────────────────────
        print("👤  Criando usuários…")
        all_users: list[User] = []
        users_per_region = 10
        for region_name, region_obj in regions.items():
            for _ in range(users_per_region):
                lat, lon = rand_coord(region_name)
                user = User(
                    email=fake.unique.email(),
                    name=fake.name(),
                    house_lat=lat,
                    house_lon=lon,
                    region_id=region_obj.id,
                )
                session.add(user)
                session.flush()
                # 1–2 phones per user
                for _ in range(random.randint(1, 2)):
                    phone = Phone(
                        user_id=user.id,
                        phone=fake.msisdn()[:20],
                    )
                    session.add(phone)
                all_users.append(user)
        session.flush()

        # ── couriers (3× users per region) ───────────────────────────────────
        print("🛵  Criando entregadores…")
        all_couriers: list[Courier] = []
        couriers_per_region = users_per_region * 3  # 30 per region = 90 total
        for region_name, region_obj in regions.items():
            for _ in range(couriers_per_region):
                lat, lon = rand_coord(region_name)
                courier = Courier(
                    name=fake.name(),
                    vehicle=pick_vehicle(),
                    lat=lat,
                    lon=lon,
                    region_id=region_obj.id,
                )
                session.add(courier)
                all_couriers.append(courier)
        session.flush()

        # ── orders + order_items + deliveries + events ────────────────────────
        print("📦  Criando pedidos, entregas e eventos…")
        total_orders = 240

        # group restaurants and couriers by region for realistic matching
        rest_by_region: dict[int, list[Restaurant]] = {}
        courier_by_region: dict[int, list[Courier]] = {}
        for rest in all_restaurants:
            rest_by_region.setdefault(rest.region_id, []).append(rest)
        for courier in all_couriers:
            courier_by_region.setdefault(courier.region_id, []).append(courier)

        for i in range(total_orders):
            # pick a user and use their region for restaurant + courier
            user = random.choice(all_users)
            region_id = user.region_id

            restaurant = random.choice(rest_by_region.get(region_id, all_restaurants))

            # fetch items belonging to this restaurant
            items_in_rest = [it for it in session.query(Item).filter_by(restaurant_id=restaurant.id).all()]
            if not items_in_rest:
                continue

            order_ts = rand_ts(90)

            order = Order(
                restaurant_id=restaurant.id,
                user_id=user.id,
                created_at=order_ts,
            )
            session.add(order)
            session.flush()

            # 1–4 distinct items per order
            chosen_items = random.sample(items_in_rest, k=min(random.randint(1, 4), len(items_in_rest)))
            for it in chosen_items:
                oi = OrderItem(
                    order_id=order.id,
                    item_id=it.id,
                    quantity=random.randint(1, 3),
                )
                session.add(oi)

            # lifecycle
            lifecycle = pick_lifecycle()

            # orders that haven't been picked up yet skip the delivery record
            needs_delivery = lifecycle[0][0] not in (OrderStatus.CONFIRMED, OrderStatus.PREPARING)
            # actually: delivery is created at READY_FOR_PICKUP or later
            has_delivery = len(lifecycle) >= 3  # at least READY_FOR_PICKUP reached

            delivery = None
            if has_delivery:
                courier = random.choice(courier_by_region.get(region_id, all_couriers))
                delivery = Delivery(
                    order_id=order.id,
                    courier_id=courier.id,
                )
                session.add(delivery)
                session.flush()

            # events — only if delivery exists
            if delivery:
                event_ts = order_ts
                for status, minutes_offset in lifecycle:
                    event_ts = event_ts + timedelta(minutes=minutes_offset + random.randint(0, 3))
                    event = Event(
                        status=status,
                        updated_at=event_ts,
                        delivery_id=delivery.id,
                    )
                    session.add(event)
            # orders still in CONFIRMED/PREPARING have no delivery and no events

        session.commit()

    # ── summary ──────────────────────────────────────────────────────────────
    print("\n✅  Seed concluído!")
    print(f"   Regiões:      {len(GEO)}")
    print(f"   Cozinhas:     {len(KITCHEN_TYPES)}")
    print(f"   Restaurantes: {len(RESTAURANT_TEMPLATES)} tipos × {len(GEO)} regiões ≈ {sum(len(v) for v in RESTAURANT_TEMPLATES.values()) * len(GEO)} registros")
    print(f"   Usuários:     {users_per_region * len(GEO)}")
    print(f"   Entregadores: {couriers_per_region * len(GEO)}")
    print(f"   Pedidos:      ~{total_orders}")
    print(f"   Banco:        {DB_URL.split('@')[-1]}")


if __name__ == "__main__":
    main()