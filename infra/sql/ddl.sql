-- ============================================================
-- DijkFood — DDL PostgreSQL (baseado no diagrama do quadro)
-- ============================================================

-- -------------------- TIPOS ENUMERADOS ----------------------

CREATE TYPE veiculo_type AS ENUM ('BIKE', 'MOTO', 'CARRO');

CREATE TYPE order_status AS ENUM (
    'CONFIRMED',
    'PREPARING',
    'READY_FOR_PICKUP',
    'PICKED_UP',
    'IN_TRANSIT',
    'DELIVERED'
);

-- -------------------- TABELAS --------------------------------

-- Usuário (cliente)
CREATE TABLE usuario (
    email       VARCHAR(255) PRIMARY KEY,
    nome        VARCHAR(255) NOT NULL,
    house_lat   DOUBLE PRECISION NOT NULL,
    house_lon   DOUBLE PRECISION NOT NULL
);

-- Telefones do usuário (multivalorado)
CREATE TABLE telefone (
    user_email  VARCHAR(255) NOT NULL REFERENCES usuario(email) ON DELETE CASCADE,
    phone       VARCHAR(20)  NOT NULL,
    PRIMARY KEY (user_email, phone)
);

-- Tipo de cozinha
CREATE TABLE tipo_cozinha (
    id    SERIAL PRIMARY KEY,
    tipo  VARCHAR(100) NOT NULL UNIQUE
);

-- Restaurante
CREATE TABLE restaurante (
    id              SERIAL PRIMARY KEY,
    nome            VARCHAR(255)     NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    kitchen_type_id INTEGER          NOT NULL REFERENCES tipo_cozinha(id)
);

-- Item do cardápio
CREATE TABLE item (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(255)     NOT NULL,
    preco       NUMERIC(10,2)    NOT NULL CHECK (preco >= 0),
    restau_id   INTEGER          NOT NULL REFERENCES restaurante(id) ON DELETE CASCADE
);

-- Entregador (courier)
CREATE TABLE courier (
    id       SERIAL PRIMARY KEY,
    nome     VARCHAR(255)     NOT NULL,
    veiculo  veiculo_type     NOT NULL,
    lat      DOUBLE PRECISION NOT NULL,
    lon      DOUBLE PRECISION NOT NULL
);

-- Pedido
CREATE TABLE pedido (
    id          SERIAL PRIMARY KEY,
    rest_id     INTEGER      NOT NULL REFERENCES restaurante(id),
    user_email  VARCHAR(255) NOT NULL REFERENCES usuario(email),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Itens do pedido (relacionamento N:N entre pedido e item)
CREATE TABLE pedido_item (
    pedido_id  INTEGER NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES item(id),
    quantidade INTEGER NOT NULL DEFAULT 1 CHECK (quantidade > 0),
    PRIMARY KEY (pedido_id, item_id)
);

-- Entrega (vincula pedido ↔ courier)
CREATE TABLE entrega (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL UNIQUE REFERENCES pedido(id),
    courier_id  INTEGER NOT NULL REFERENCES courier(id)
);

-- Evento (ciclo de vida da entrega)
CREATE TABLE evento (
    id          SERIAL PRIMARY KEY,
    status      order_status    NOT NULL,
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT now(),
    order_id    INTEGER         NOT NULL REFERENCES pedido(id),
    courier_id  INTEGER         NOT NULL REFERENCES courier(id)
);

-- -------------------- ÍNDICES ÚTEIS --------------------------

CREATE INDEX idx_pedido_user   ON pedido(user_email, created_at DESC);
CREATE INDEX idx_evento_order  ON evento(order_id, updated_at ASC);
CREATE INDEX idx_entrega_courier ON entrega(courier_id);

