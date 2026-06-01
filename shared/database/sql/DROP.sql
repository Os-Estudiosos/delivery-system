-- =============================================================
-- DROP — dijkfood delivery system
-- Drops all objects in reverse FK dependency order.
-- Safe to run multiple times (IF EXISTS everywhere).
-- =============================================================

-- Indexes are dropped automatically with their tables,
-- but listed here for explicitness when doing partial resets.

-- -----------------------------------------------------------------
-- Tables (reverse FK order)
-- -----------------------------------------------------------------
DROP TABLE IF EXISTS event        CASCADE;
DROP TABLE IF EXISTS delivery     CASCADE;
DROP TABLE IF EXISTS order_item   CASCADE;
DROP TABLE IF EXISTS orders       CASCADE;
DROP TABLE IF EXISTS courier      CASCADE;
DROP TABLE IF EXISTS item         CASCADE;
DROP TABLE IF EXISTS restaurant   CASCADE;
DROP TABLE IF EXISTS kitchen_type CASCADE;
DROP TABLE IF EXISTS phones       CASCADE;
DROP TABLE IF EXISTS users        CASCADE;

-- -----------------------------------------------------------------
-- ENUMs
-- -----------------------------------------------------------------
DROP TYPE IF EXISTS order_status CASCADE;
DROP TYPE IF EXISTS vehicle_type CASCADE;