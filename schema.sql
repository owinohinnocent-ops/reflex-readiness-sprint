-- ============================================
-- REFLEX DELIVERY SYSTEM - DATABASE SCHEMA
-- PostgreSQL Database - Structure Only
-- ============================================

-- ============================================
-- STEP 1: CREATE THE DATABASE
-- ============================================

-- First, disconnect from any other database
-- Then create the reflex_db database
CREATE DATABASE reflex_db;

-- Connect to the new database (for psql command line)
-- \c reflex_db;

-- Note: If using pgAdmin, you'll need to reconnect to reflex_db
-- after running the CREATE DATABASE command

-- ============================================
-- STEP 2: CREATE TABLES
-- ============================================

-- TABLE: users
-- Stores all user accounts (retailers, dispatchers, riders)
CREATE TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL
        CHECK (role IN ('retailer', 'dispatcher', 'rider')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE riders (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    availability_status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE'
        CHECK (availability_status IN ('AVAILABLE', 'BUSY', 'OFFLINE')),
    location VARCHAR(255),
    vehicle_type VARCHAR(50),
    plate_number VARCHAR(20) UNIQUE,

    CONSTRAINT fk_rider_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);


CREATE TABLE deliveries (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer_id INTEGER NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    pickup_address TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    item_description TEXT NOT NULL,

    status VARCHAR(30) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'ASSIGNED', 'PICKED', 'DELIVERED')),

    assigned_rider_id INTEGER,
    assigned_by INTEGER,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_delivery_retailer
        FOREIGN KEY (retailer_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_delivery_rider
        FOREIGN KEY (assigned_rider_id)
        REFERENCES riders(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_delivery_assigned_by
        FOREIGN KEY (assigned_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);


CREATE TABLE delivery_status_history (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('OPEN', 'ASSIGNED', 'PICKED', 'DELIVERED')),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_status_delivery
        FOREIGN KEY (delivery_id)
        REFERENCES deliveries(id)
        ON DELETE CASCADE
);

-- ============================================
-- STEP 3: VERIFICATION QUERIES (optional)
--uncomment and run this after creating the database and tables.
-- ============================================

-- Check all tables exist
-- SELECT table_name 
-- FROM information_schema.tables 
-- WHERE table_schema = 'public'
-- ORDER BY table_name;

-- ============================================
-- END OF SCHEMA
-- ============================================