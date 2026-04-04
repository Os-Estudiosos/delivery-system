-- ============================================================
-- DijkFood - PostgreSQL DDL
-- ============================================================

-- -------------------- ENUM TYPES -----------------------------

CREATE TYPE vehicle_type AS ENUM ('BIKE', 'MOTORCYCLE', 'CAR');

CREATE TYPE order_status AS ENUM (
    'CONFIRMED',
    'PREPARING',
    'READY_FOR_PICKUP',
    'PICKED_UP',
    'IN_TRANSIT',
    'DELIVERED'
);

-- -------------------- TABLES ---------------------------------

-- User (customer)
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL,
    house_lat   DOUBLE PRECISION NOT NULL,
    house_lon   DOUBLE PRECISION NOT NULL
);

-- User phones (multivalued)
CREATE TABLE phones (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    phone       VARCHAR(20)  NOT NULL,
    PRIMARY KEY (user_id, phone)
);

-- Kitchen type
CREATE TABLE kitchen_type (
    id    SERIAL PRIMARY KEY,
    type  VARCHAR(100) NOT NULL UNIQUE
);

-- Restaurant
CREATE TABLE restaurant (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255)     NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    kitchen_type_id INTEGER          NOT NULL REFERENCES kitchen_type(id)
);

-- Menu item
CREATE TABLE item (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255)     NOT NULL,
    price       NUMERIC(10,2)    NOT NULL CHECK (price >= 0),
    restaurant_id INTEGER        NOT NULL REFERENCES restaurant(id) ON DELETE CASCADE
);

-- Courier
CREATE TABLE courier (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR(255)     NOT NULL,
    vehicle  vehicle_type     NOT NULL,
    lat      DOUBLE PRECISION NOT NULL,
    lon      DOUBLE PRECISION NOT NULL
);

-- Order
CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    restaurant_id INTEGER    NOT NULL REFERENCES restaurant(id),
    user_id     INTEGER      NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Order items (N:N relation between order and item)
CREATE TABLE order_item (
    order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES item(id),
    quantity   INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    PRIMARY KEY (order_id, item_id)
);

-- Delivery (links order to courier)
CREATE TABLE delivery (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    courier_id  INTEGER NOT NULL REFERENCES courier(id)
);

-- Event (delivery lifecycle)
CREATE TABLE event (
    id          SERIAL PRIMARY KEY,
    status      order_status    NOT NULL,
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT now(),
    order_id    INTEGER         NOT NULL REFERENCES orders(id),
    courier_id  INTEGER         NOT NULL REFERENCES courier(id)
);

-- -------------------- USEFUL INDEXES -------------------------

CREATE INDEX idx_orders_user ON orders(user_id, created_at DESC);
CREATE INDEX idx_event_order ON event(order_id, updated_at ASC);
CREATE INDEX idx_delivery_courier ON delivery(courier_id);

