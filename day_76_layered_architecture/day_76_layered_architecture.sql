/*
 * LAYERED ARCHITECTURE: POSTGRESQL IMPLEMENTATION
 *
 * Layers:
 *   Presentation  -> External clients and reporting views
 *   Application   -> Functions and procedures
 *   Domain        -> Business entities, rules and constraints
 *   Infrastructure -> PostgreSQL storage, indexes, audit and transactions
 *
 * Domain scenario:
 *   Enterprise order management
 *
 * Run using PostgreSQL 15 or later.
 *
 * The script is designed to be rerunnable in a dedicated
 * learning database. It creates its own schema.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS layered_app;

SET search_path TO layered_app, public;

-- ============================================================
-- DOMAIN LAYER: ENUMERATED BUSINESS STATES
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'order_status'
          AND n.nspname = 'layered_app'
    ) THEN
        CREATE TYPE order_status AS ENUM (
            'PENDING',
            'CONFIRMED',
            'CANCELLED'
        );
    END IF;
END
$$;

-- ============================================================
-- DOMAIN LAYER: MASTER DATA
-- ============================================================

CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL UNIQUE,
    customer_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT customers_code_not_empty
        CHECK (LENGTH(TRIM(customer_code)) > 0),

    CONSTRAINT customers_name_not_empty
        CHECK (LENGTH(TRIM(customer_name)) > 0)
);

CREATE TABLE IF NOT EXISTS products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code VARCHAR(40) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT products_price_positive
        CHECK (unit_price > 0),

    CONSTRAINT products_code_not_empty
        CHECK (LENGTH(TRIM(product_code)) > 0)
);

-- ============================================================
-- DOMAIN LAYER: ORDER AGGREGATES
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_number VARCHAR(50) NOT NULL UNIQUE,

    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),

    status order_status NOT NULL DEFAULT 'PENDING',

    total_amount NUMERIC(16, 2) NOT NULL DEFAULT 0,

    version INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT orders_total_nonnegative
        CHECK (total_amount >= 0),

    CONSTRAINT orders_version_nonnegative
        CHECK (version >= 0)
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_id BIGINT NOT NULL
        REFERENCES orders(order_id) ON DELETE RESTRICT,

    product_id BIGINT NOT NULL
        REFERENCES products(product_id) ON DELETE RESTRICT,

    quantity INTEGER NOT NULL,

    unit_price NUMERIC(14, 2) NOT NULL,

    line_total NUMERIC(16, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,

    CONSTRAINT order_items_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT order_items_price_positive
        CHECK (unit_price > 0),

    CONSTRAINT order_items_unique_product
        UNIQUE (order_id, product_id)
);

-- ============================================================
-- INFRASTRUCTURE LAYER: AUDIT AND OUTBOX
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_type VARCHAR(80) NOT NULL,

    aggregate_type VARCHAR(80) NOT NULL,

    aggregate_id BIGINT NOT NULL,

    event_data JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outbox_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_type VARCHAR(80) NOT NULL,

    aggregate_id BIGINT NOT NULL,

    payload JSONB NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    published_at TIMESTAMPTZ,

    attempts INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT outbox_attempts_nonnegative
        CHECK (attempts >= 0)
);

-- ============================================================
-- APPLICATION LAYER: USER AND ROLE MODEL
-- ============================================================

CREATE TABLE IF NOT EXISTS app_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    username VARCHAR(80) NOT NULL UNIQUE,

    role VARCHAR(30) NOT NULL,

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_user_role
        CHECK (
            role IN (
                'CUSTOMER',
                'ORDER_MANAGER',
                'ADMIN',
                'AUDITOR'
            )
        )
);

-- ============================================================
-- INFRASTRUCTURE LAYER: INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_orders_customer
    ON orders(customer_id);

CREATE INDEX IF NOT EXISTS idx_orders_status_created
    ON orders(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_order_items_order
    ON order_items(order_id);

CREATE INDEX IF NOT EXISTS idx_audit_aggregate
    ON audit_events(aggregate_type, aggregate_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox_events(created_at)
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_products_active
    ON products(product_code)
    WHERE active = TRUE;

-- ============================================================
-- INFRASTRUCTURE LAYER: UPDATED TIMESTAMP TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_orders_updated
    ON orders;

CREATE TRIGGER trg_orders_updated
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

-- ============================================================
-- DOMAIN LAYER: PROTECT ORDER STATE TRANSITIONS
-- ============================================================

CREATE OR REPLACE FUNCTION enforce_order_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'CONFIRMED'
       AND NEW.status <> 'CONFIRMED' THEN
        RAISE EXCEPTION
            'Confirmed orders cannot be changed to another state.';
    END IF;

    IF OLD.status = 'CANCELLED'
       AND NEW.status <> 'CANCELLED' THEN
        RAISE EXCEPTION
            'Cancelled orders cannot be reopened.';
    END IF;

    IF NEW.status <> OLD.status THEN
        NEW.version := OLD.version + 1;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_order_transition
    ON orders;

CREATE TRIGGER trg_order_transition
BEFORE UPDATE OF status ON orders
FOR EACH ROW
EXECUTE FUNCTION enforce_order_transition();

-- ============================================================
-- APPLICATION LAYER: AUDIT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION audit_order_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_type VARCHAR(80);
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_event_type := 'ORDER_CREATED';

        INSERT INTO audit_events (
            event_type,
            aggregate_type,
            aggregate_id,
            event_data
        )
        VALUES (
            v_event_type,
            'ORDER',
            NEW.order_id,
            jsonb_build_object(
                'order_number', NEW.order_number,
                'status', NEW.status,
                'total', NEW.total_amount
            )
        );

        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF OLD.status IS DISTINCT FROM NEW.status THEN
            v_event_type := 'ORDER_STATUS_CHANGED';
        ELSE
            v_event_type := 'ORDER_UPDATED';
        END IF;

        INSERT INTO audit_events (
            event_type,
            aggregate_type,
            aggregate_id,
            event_data
        )
        VALUES (
            v_event_type,
            'ORDER',
            NEW.order_id,
            jsonb_build_object(
                'old_status', OLD.status,
                'new_status', NEW.status,
                'old_total', OLD.total_amount,
                'new_total', NEW.total_amount,
                'version', NEW.version
            )
        );

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_order_audit
    ON orders;

CREATE TRIGGER trg_order_audit
AFTER INSERT OR UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION audit_order_changes();

-- ============================================================
-- APPLICATION LAYER: OUTBOX EVENT CREATION
-- ============================================================

CREATE OR REPLACE FUNCTION create_order_outbox_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO outbox_events (
        event_type,
        aggregate_id,
        payload
    )
    VALUES (
        CASE
            WHEN TG_OP = 'INSERT' THEN 'ORDER_CREATED'
            ELSE 'ORDER_STATUS_CHANGED'
        END,
        NEW.order_id,
        jsonb_build_object(
            'order_id', NEW.order_id,
            'order_number', NEW.order_number,
            'status', NEW.status,
            'total', NEW.total_amount,
            'version', NEW.version
        )
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_order_outbox
    ON orders;

CREATE TRIGGER trg_order_outbox
AFTER INSERT OR UPDATE OF status ON orders
FOR EACH ROW
EXECUTE FUNCTION create_order_outbox_event();

-- ============================================================
-- APPLICATION LAYER: ORDER CREATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE create_order(
    p_order_number VARCHAR,
    p_customer_id BIGINT,
    p_items JSONB,
    INOUT p_created_order_id BIGINT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id BIGINT;
    v_item JSONB;
    v_product_id BIGINT;
    v_quantity INTEGER;
    v_price NUMERIC(14, 2);
    v_total NUMERIC(16, 2) := 0;
BEGIN
    IF p_order_number IS NULL
       OR LENGTH(TRIM(p_order_number)) = 0 THEN
        RAISE EXCEPTION 'Order number is required.';
    END IF;

    IF jsonb_typeof(p_items) <> 'array'
       OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'At least one order item is required.';
    END IF;

    PERFORM 1
    FROM customers
    WHERE customer_id = p_customer_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active customer not found.';
    END IF;

    INSERT INTO orders (
        order_number,
        customer_id
    )
    VALUES (
        p_order_number,
        p_customer_id
    )
    RETURNING order_id INTO v_order_id;

    FOR v_item IN
        SELECT value FROM jsonb_array_elements(p_items)
    LOOP
        v_product_id := (v_item ->> 'product_id')::BIGINT;
        v_quantity := (v_item ->> 'quantity')::INTEGER;

        IF v_quantity <= 0 THEN
            RAISE EXCEPTION 'Quantity must be positive.';
        END IF;

        SELECT unit_price
        INTO v_price
        FROM products
        WHERE product_id = v_product_id
          AND active = TRUE
        FOR SHARE;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Product % is unavailable.',
                v_product_id;
        END IF;

        INSERT INTO order_items (
            order_id,
            product_id,
            quantity,
            unit_price
        )
        VALUES (
            v_order_id,
            v_product_id,
            v_quantity,
            v_price
        );

        v_total := v_total + (v_quantity * v_price);
    END LOOP;

    UPDATE orders
    SET total_amount = v_total
    WHERE order_id = v_order_id;

    p_created_order_id := v_order_id;
END;
$$;

-- ============================================================
-- APPLICATION LAYER: CONFIRMATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE confirm_order(
    p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_status order_status;
BEGIN
    SELECT status
    INTO v_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order not found.';
    END IF;

    IF v_status <> 'PENDING' THEN
        RAISE EXCEPTION
            'Only pending orders can be confirmed.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM order_items
        WHERE order_id = p_order_id
    ) THEN
        RAISE EXCEPTION 'Orders without items cannot be confirmed.';
    END IF;

    UPDATE orders
    SET status = 'CONFIRMED'
    WHERE order_id = p_order_id;
END;
$$;

-- ============================================================
-- PRESENTATION LAYER: REPORTING VIEWS
-- ============================================================

CREATE OR REPLACE VIEW order_details AS
SELECT
    o.order_id,
    o.order_number,
    c.customer_code,
    c.customer_name,
    o.status,
    o.total_amount,
    o.version,
    o.created_at,
    COUNT(oi.order_item_id) AS item_count,
    COALESCE(SUM(oi.quantity), 0) AS total_units
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    c.customer_code,
    c.customer_name,
    o.status,
    o.total_amount,
    o.version,
    o.created_at;

CREATE OR REPLACE VIEW customer_order_summary AS
SELECT
    c.customer_id,
    c.customer_code,
    c.customer_name,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'CONFIRMED'
    ) AS confirmed_orders,
    COALESCE(
        SUM(o.total_amount) FILTER (
            WHERE o.status = 'CONFIRMED'
        ),
        0
    ) AS confirmed_revenue
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
GROUP BY
    c.customer_id,
    c.customer_code,
    c.customer_name;

-- ============================================================
-- INFRASTRUCTURE LAYER: SAMPLE DATA
-- ============================================================

INSERT INTO customers (
    customer_code,
    customer_name,
    email
)
VALUES
    (
        'CUST-001',
        'Northstar Technologies',
        'procurement@northstar.example'
    ),
    (
        'CUST-002',
        'Apex Systems',
        'orders@apex.example'
    ),
    (
        'CUST-003',
        'Inactive Enterprise',
        'inactive@example.test'
    )
ON CONFLICT (customer_code) DO NOTHING;

UPDATE customers
SET active = FALSE
WHERE customer_code = 'CUST-003';

INSERT INTO products (
    product_code,
    product_name,
    unit_price
)
VALUES
    ('PROD-001', 'Enterprise Laptop', 75000.00),
    ('PROD-002', 'Wireless Mouse', 1200.00),
    ('PROD-003', 'Docking Station', 8500.00),
    ('PROD-004', 'Server Rack', 45000.00)
ON CONFLICT (product_code) DO NOTHING;

INSERT INTO app_users (username, role)
VALUES
    ('order.manager', 'ORDER_MANAGER'),
    ('repository.admin', 'ADMIN'),
    ('audit.reader', 'AUDITOR')
ON CONFLICT (username) DO NOTHING;

-- ============================================================
-- TRANSACTIONAL WORKFLOW
-- ============================================================

DO $$
DECLARE
    v_customer BIGINT;
    v_laptop BIGINT;
    v_mouse BIGINT;
    v_order BIGINT;
BEGIN
    SELECT customer_id INTO v_customer
    FROM customers
    WHERE customer_code = 'CUST-001';

    SELECT product_id INTO v_laptop
    FROM products
    WHERE product_code = 'PROD-001';

    SELECT product_id INTO v_mouse
    FROM products
    WHERE product_code = 'PROD-002';

    IF NOT EXISTS (
        SELECT 1
        FROM orders
        WHERE order_number = 'ORD-LAYERED-001'
    ) THEN

        CALL create_order(
            'ORD-LAYERED-001',
            v_customer,
            jsonb_build_array(
                jsonb_build_object(
                    'product_id', v_laptop,
                    'quantity', 2
                ),
                jsonb_build_object(
                    'product_id', v_mouse,
                    'quantity', 3
                )
            ),
            v_order
        );

        CALL confirm_order(v_order);
    END IF;
END;
$$;

-- ============================================================
-- VALIDATION QUERIES
-- ============================================================

-- 1. Retrieve complete order information.
SELECT *
FROM order_details
ORDER BY created_at DESC;

-- 2. Customer order aggregation.
SELECT *
FROM customer_order_summary
ORDER BY confirmed_revenue DESC;

-- 3. Check order totals against their line items.
SELECT
    o.order_id,
    o.order_number,
    o.total_amount,
    COALESCE(SUM(oi.line_total), 0) AS calculated_total,
    o.total_amount =
        COALESCE(SUM(oi.line_total), 0) AS total_is_valid
FROM orders o
LEFT JOIN order_items oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;

-- 4. Business-rule validation.
SELECT
    order_number,
    status,
    CASE
        WHEN total_amount > 0
         AND EXISTS (
            SELECT 1
            FROM order_items oi
            WHERE oi.order_id = orders.order_id
         )
        THEN 'VALID'
        ELSE 'INVALID'
    END AS validation_result
FROM orders;

-- 5. Audit history.
SELECT
    event_id,
    event_type,
    aggregate_type,
    aggregate_id,
    event_data,
    created_at
FROM audit_events
ORDER BY event_id;

-- 6. Pending integration events.
SELECT *
FROM outbox_events
WHERE published_at IS NULL
ORDER BY created_at;

-- 7. CTE-based customer revenue ranking.
WITH revenue AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status = 'CONFIRMED'
    GROUP BY customer_id
),
ranked AS (
    SELECT
        customer_id,
        revenue,
        DENSE_RANK() OVER (
            ORDER BY revenue DESC
        ) AS revenue_rank
    FROM revenue
)
SELECT
    c.customer_code,
    c.customer_name,
    r.revenue,
    r.revenue_rank
FROM ranked r
JOIN customers c
    ON c.customer_id = r.customer_id
ORDER BY r.revenue_rank;

-- ============================================================
-- FAILURE-CASE VALIDATION
-- ============================================================

-- Invalid order transitions are rejected by the database trigger.
-- Execute independently when testing because the exception aborts
-- the current transaction:
--
-- UPDATE layered_app.orders
-- SET status = 'CANCELLED'
-- WHERE order_number = 'ORD-LAYERED-001';

-- A duplicate product in the same order violates UNIQUE.
--
-- INSERT INTO layered_app.order_items (
--     order_id, product_id, quantity, unit_price
-- )
-- SELECT
--     o.order_id, oi.product_id, 1, oi.unit_price
-- FROM layered_app.orders o
-- JOIN layered_app.order_items oi
--     ON oi.order_id = o.order_id
-- WHERE o.order_number = 'ORD-LAYERED-001'
-- LIMIT 1;

-- ============================================================
-- APPLICATION TRANSACTION EXAMPLE
-- ============================================================

-- PostgreSQL transaction boundaries guarantee atomicity for
-- order creation, item insertion, audit events and outbox events.
--
-- Example:
--
-- BEGIN;
-- UPDATE orders
-- SET status = 'CANCELLED'
-- WHERE order_number = 'ORD-PENDING-001'
--   AND status = 'PENDING';
-- COMMIT;
--
-- Use ROLLBACK if any operation fails.

COMMIT;
