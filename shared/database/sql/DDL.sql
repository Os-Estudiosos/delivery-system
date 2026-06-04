-- =============================================================
-- DDL — dijkfood delivery system
-- Compatible: PostgreSQL 16
-- Execution order respects FK dependencies
-- =============================================================

-- -----------------------------------------------------------------
-- ENUMs
-- -----------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE vehicle_type AS ENUM ('BIKE', 'MOTORCYCLE', 'CAR');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE order_status AS ENUM (
        'CONFIRMED',
        'PREPARING',
        'READY_FOR_PICKUP',
        'PICKED_UP',
        'IN_TRANSIT',
        'DELIVERED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- -----------------------------------------------------------------
-- users
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id        SERIAL       PRIMARY KEY,
    email     VARCHAR(255) NOT NULL UNIQUE,
    name      VARCHAR(255) NOT NULL,
    house_lat DOUBLE PRECISION NOT NULL,
    house_lon DOUBLE PRECISION NOT NULL
);

-- -----------------------------------------------------------------
-- phones  (composite PK: user_id + phone)
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS phones (
    user_id INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    phone   VARCHAR(20) NOT NULL,
    PRIMARY KEY (user_id, phone)
);

-- -----------------------------------------------------------------
-- kitchen_type
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kitchen_type (
    id   SERIAL       PRIMARY KEY,
    type VARCHAR(100) NOT NULL UNIQUE
);

-- -----------------------------------------------------------------
-- restaurant
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS restaurant (
    id              SERIAL           PRIMARY KEY,
    name            VARCHAR(255)     NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    kitchen_type_id INTEGER          NOT NULL REFERENCES kitchen_type(id)
);

-- -----------------------------------------------------------------
-- item
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS item (
    id            SERIAL         PRIMARY KEY,
    name          VARCHAR(255)   NOT NULL,
    price         NUMERIC(10, 2) NOT NULL,
    restaurant_id INTEGER        NOT NULL REFERENCES restaurant(id) ON DELETE CASCADE,
    CONSTRAINT item_price_nonneg CHECK (price >= 0)
);

-- -----------------------------------------------------------------
-- courier
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS courier (
    id      SERIAL           PRIMARY KEY,
    name    VARCHAR(255)     NOT NULL,
    vehicle vehicle_type     NOT NULL,
    lat     DOUBLE PRECISION NOT NULL,
    lon     DOUBLE PRECISION NOT NULL
);

-- -----------------------------------------------------------------
-- orders
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id            SERIAL                      PRIMARY KEY,
    restaurant_id INTEGER                     NOT NULL REFERENCES restaurant(id),
    user_id       INTEGER                     NOT NULL REFERENCES users(id),
    created_at    TIMESTAMP WITH TIME ZONE    NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------
-- order_item  (composite PK: order_id + item_id)
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_item (
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_id  INTEGER NOT NULL REFERENCES item(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (order_id, item_id),
    CONSTRAINT order_item_qty_pos CHECK (quantity > 0)
);

-- -----------------------------------------------------------------
-- delivery
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery (
    id         SERIAL  PRIMARY KEY,
    order_id   INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    courier_id INTEGER NOT NULL REFERENCES courier(id)
);

-- -----------------------------------------------------------------
-- event
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event (
    id          SERIAL                   PRIMARY KEY,
    status      order_status             NOT NULL,
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    delivery_id INTEGER                  NOT NULL REFERENCES delivery(id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------
-- Indexes for common query patterns
-- -----------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_phones_user_id          ON phones(user_id);
CREATE INDEX IF NOT EXISTS idx_restaurant_kitchen_type ON restaurant(kitchen_type_id);
CREATE INDEX IF NOT EXISTS idx_item_restaurant         ON item(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_orders_user             ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_restaurant       ON orders(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_order_item_order        ON order_item(order_id);
CREATE INDEX IF NOT EXISTS idx_delivery_courier        ON delivery(courier_id);
CREATE INDEX IF NOT EXISTS idx_event_delivery          ON event(delivery_id);
CREATE INDEX IF NOT EXISTS idx_event_status            ON event(status);