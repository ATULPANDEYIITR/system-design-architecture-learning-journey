-- ============================================================
-- MODULAR MONOLITH
-- PostgreSQL 15+
--
-- Business domain: Enterprise order management
--
-- Logical modules:
--   shared      : Common identifiers and conventions
--   inventory   : Product catalog and stock reservations
--   payments    : Payment authorization and refunds
--   orders      : Order lifecycle and orchestration
--   notifications : Transactional event outbox
--   architecture: Module boundaries and migration tracking
--
-- Each business module owns its tables and operations.
-- Cross-module foreign keys are intentional and documented.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS shared;
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS payments;
CREATE SCHEMA IF NOT EXISTS orders;
CREATE SCHEMA IF NOT EXISTS notifications;
CREATE SCHEMA IF NOT EXISTS architecture;

-- ============================================================
-- SHARED MODULE
-- ============================================================

CREATE TABLE shared.customers (
    customer_id UUID PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT customer_name_not_empty
        CHECK (length(trim(customer_name)) > 0),

    CONSTRAINT customer_email_not_empty
        CHECK (length(trim(email)) > 0)
);

-- ============================================================
-- INVENTORY MODULE
-- ============================================================

CREATE TABLE inventory.products (
    product_id UUID PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    available_quantity INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT product_price_positive
        CHECK (unit_price > 0),

    CONSTRAINT product_stock_nonnegative
        CHECK (available_quantity >= 0),

    CONSTRAINT product_name_not_empty
        CHECK (length(trim(product_name)) > 0)
);

CREATE INDEX idx_products_active_sku
    ON inventory.products(sku)
    WHERE active = TRUE;

CREATE TABLE inventory.stock_reservations (
    reservation_id UUID PRIMARY KEY,
    product_id UUID NOT NULL
        REFERENCES inventory.products(product_id),
    quantity INTEGER NOT NULL,
    reservation_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT reservation_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT reservation_status_valid
        CHECK (
            reservation_status IN (
                'ACTIVE',
                'COMMITTED',
                'RELEASED',
                'EXPIRED'
            )
        )
);

CREATE INDEX idx_reservations_product_status
    ON inventory.stock_reservations(
        product_id,
        reservation_status
    );

CREATE INDEX idx_reservations_expiration
    ON inventory.stock_reservations(expires_at)
    WHERE reservation_status = 'ACTIVE';

-- ============================================================
-- PAYMENT MODULE
-- ============================================================

CREATE TABLE payments.payment_records (
    payment_id UUID PRIMARY KEY,
    order_id UUID NOT NULL UNIQUE,
    amount NUMERIC(14, 2) NOT NULL,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'AUTHORIZED',
    provider_reference VARCHAR(150) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    refunded_at TIMESTAMPTZ,

    CONSTRAINT payment_amount_positive
        CHECK (amount > 0),

    CONSTRAINT payment_status_valid
        CHECK (
            payment_status IN (
                'AUTHORIZED',
                'FAILED',
                'REFUNDED'
            )
        ),

    CONSTRAINT payment_refund_consistent
        CHECK (
            (payment_status = 'REFUNDED' AND refunded_at IS NOT NULL)
            OR
            (payment_status <> 'REFUNDED' AND refunded_at IS NULL)
        )
);

CREATE INDEX idx_payment_status_created
    ON payments.payment_records(payment_status, created_at DESC);

-- ============================================================
-- ORDERS MODULE
-- ============================================================

CREATE TABLE orders.order_records (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL
        REFERENCES shared.customers(customer_id),
    product_id UUID NOT NULL
        REFERENCES inventory.products(product_id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    total_amount NUMERIC(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,
    order_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT order_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT order_unit_price_positive
        CHECK (unit_price > 0),

    CONSTRAINT order_status_valid
        CHECK (
            order_status IN (
                'PENDING',
                'CONFIRMED',
                'CANCELLED'
            )
        )
);

CREATE INDEX idx_orders_customer_created
    ON orders.order_records(customer_id, created_at DESC);

CREATE INDEX idx_orders_status_created
    ON orders.order_records(order_status, created_at DESC);

CREATE TABLE orders.order_reservations (
    order_id UUID PRIMARY KEY
        REFERENCES orders.order_records(order_id),
    reservation_id UUID NOT NULL UNIQUE
        REFERENCES inventory.stock_reservations(reservation_id)
);

-- ============================================================
-- NOTIFICATION MODULE
-- Transactional outbox for reliable event publication.
-- ============================================================

CREATE TABLE notifications.event_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    event_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT outbox_status_valid
        CHECK (
            event_status IN (
                'PENDING',
                'PUBLISHED',
                'FAILED'
            )
        ),

    CONSTRAINT outbox_attempts_nonnegative
        CHECK (attempts >= 0),

    CONSTRAINT outbox_payload_object
        CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX idx_outbox_pending
    ON notifications.event_outbox(next_attempt_at, occurred_at)
    WHERE event_status = 'PENDING';

CREATE INDEX idx_outbox_aggregate
    ON notifications.event_outbox(aggregate_type, aggregate_id);

-- ============================================================
-- ARCHITECTURE GOVERNANCE MODULE
-- ============================================================

CREATE TABLE architecture.modules (
    module_id UUID PRIMARY KEY,
    module_name VARCHAR(80) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    migration_stage VARCHAR(30) NOT NULL DEFAULT 'MONOLITH',
    external_endpoint TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT module_stage_valid
        CHECK (
            migration_stage IN (
                'MONOLITH',
                'BOUNDARIES_DEFINED',
                'MODULE_ISOLATED',
                'CONTRACT_STABLE',
                'EXTERNALIZED'
            )
        ),

    CONSTRAINT externalized_endpoint_required
        CHECK (
            migration_stage <> 'EXTERNALIZED'
            OR external_endpoint LIKE 'https://%'
        )
);

CREATE TABLE architecture.module_dependencies (
    source_module UUID NOT NULL
        REFERENCES architecture.modules(module_id),
    target_module UUID NOT NULL
        REFERENCES architecture.modules(module_id),
    dependency_type VARCHAR(20) NOT NULL DEFAULT 'COMPILE_TIME',

    PRIMARY KEY (source_module, target_module),

    CONSTRAINT dependency_type_valid
        CHECK (
            dependency_type IN (
                'COMPILE_TIME',
                'RUNTIME',
                'EVENT'
            )
        ),

    CONSTRAINT no_self_dependency
        CHECK (source_module <> target_module)
);

CREATE INDEX idx_dependencies_target
    ON architecture.module_dependencies(target_module);

-- ============================================================
-- MODULE SEED DATA
-- ============================================================

INSERT INTO architecture.modules
    (module_id, module_name, description)
VALUES
    ('10000000-0000-0000-0000-000000000001',
     'shared', 'Common customer identities and shared types'),

    ('10000000-0000-0000-0000-000000000002',
     'inventory', 'Product catalog and stock ownership'),

    ('10000000-0000-0000-0000-000000000003',
     'payments', 'Payment authorization and refund ownership'),

    ('10000000-0000-0000-0000-000000000004',
     'orders', 'Order lifecycle and business orchestration'),

    ('10000000-0000-0000-0000-000000000005',
     'notifications', 'Event delivery and notifications');

INSERT INTO architecture.module_dependencies
    (source_module, target_module, dependency_type)
VALUES
    ('10000000-0000-0000-0000-000000000004',
     '10000000-0000-0000-0000-000000000002',
     'COMPILE_TIME'),

    ('10000000-0000-0000-0000-000000000004',
     '10000000-0000-0000-0000-000000000003',
     'COMPILE_TIME'),

    ('10000000-0000-0000-0000-000000000004',
     '10000000-0000-0000-0000-000000000001',
     'COMPILE_TIME'),

    ('10000000-0000-0000-0000-000000000005',
     '10000000-0000-0000-0000-000000000001',
     'COMPILE_TIME'),

    ('10000000-0000-0000-0000-000000000005',
     '10000000-0000-0000-0000-000000000004',
     'EVENT');

-- ============================================================
-- SAMPLE BUSINESS DATA
-- ============================================================

INSERT INTO shared.customers (
    customer_id,
    customer_name,
    email
)
VALUES
    (
        '20000000-0000-0000-0000-000000000001',
        'Enterprise Customer',
        'enterprise@example.com'
    ),
    (
        '20000000-0000-0000-0000-000000000002',
        'Retail Customer',
        'retail@example.com'
    );

INSERT INTO inventory.products (
    product_id,
    sku,
    product_name,
    unit_price,
    available_quantity
)
VALUES
    (
        '30000000-0000-0000-0000-000000000001',
        'LAPTOP-001',
        'Enterprise Laptop',
        75000.00,
        50
    ),
    (
        '30000000-0000-0000-0000-000000000002',
        'SERVER-001',
        'Application Server',
        180000.00,
        5
    );

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION orders.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_order_updated_at
BEFORE UPDATE ON orders.order_records
FOR EACH ROW
EXECUTE FUNCTION orders.set_updated_at();

-- ============================================================
-- ORDER STATE VALIDATION
-- Prevent invalid backward transitions.
-- ============================================================

CREATE OR REPLACE FUNCTION orders.validate_order_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.order_status = NEW.order_status THEN
        RETURN NEW;
    END IF;

    IF OLD.order_status = 'PENDING'
       AND NEW.order_status IN ('CONFIRMED', 'CANCELLED') THEN
        RETURN NEW;
    END IF;

    IF OLD.order_status = 'CONFIRMED'
       AND NEW.order_status = 'CANCELLED' THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'Invalid order transition: % -> %',
        OLD.order_status,
        NEW.order_status;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_order_transition
BEFORE UPDATE OF order_status ON orders.order_records
FOR EACH ROW
EXECUTE FUNCTION orders.validate_order_transition();

-- ============================================================
-- STOCK RESERVATION FUNCTION
--
-- SELECT FOR UPDATE prevents concurrent transactions from
-- reserving the same available stock.
-- ============================================================

CREATE OR REPLACE FUNCTION inventory.reserve_stock(
    p_product_id UUID,
    p_quantity INTEGER,
    p_ttl_minutes INTEGER DEFAULT 15
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_available INTEGER;
    v_reservation_id UUID := gen_random_uuid();
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive.';
    END IF;

    IF p_ttl_minutes <= 0 OR p_ttl_minutes > 1440 THEN
        RAISE EXCEPTION 'Reservation TTL must be between 1 and 1440 minutes.';
    END IF;

    SELECT available_quantity
    INTO v_available
    FROM inventory.products
    WHERE product_id = p_product_id
      AND active = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product does not exist or is inactive.';
    END IF;

    IF v_available < p_quantity THEN
        RAISE EXCEPTION
            'Insufficient stock. Available: %, requested: %',
            v_available,
            p_quantity;
    END IF;

    UPDATE inventory.products
    SET available_quantity = available_quantity - p_quantity
    WHERE product_id = p_product_id;

    INSERT INTO inventory.stock_reservations (
        reservation_id,
        product_id,
        quantity,
        expires_at
    )
    VALUES (
        v_reservation_id,
        p_product_id,
        p_quantity,
        NOW() + make_interval(mins => p_ttl_minutes)
    );

    RETURN v_reservation_id;
END;
$$;

-- ============================================================
-- RELEASE RESERVATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION inventory.release_stock(
    p_reservation_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_reservation inventory.stock_reservations%ROWTYPE;
BEGIN
    SELECT *
    INTO v_reservation
    FROM inventory.stock_reservations
    WHERE reservation_id = p_reservation_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Reservation not found.';
    END IF;

    IF v_reservation.reservation_status = 'RELEASED' THEN
        RETURN FALSE;
    END IF;

    IF v_reservation.reservation_status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Only active reservations can be released.';
    END IF;

    UPDATE inventory.products
    SET available_quantity =
        available_quantity + v_reservation.quantity
    WHERE product_id = v_reservation.product_id;

    UPDATE inventory.stock_reservations
    SET reservation_status = 'RELEASED'
    WHERE reservation_id = p_reservation_id;

    RETURN TRUE;
END;
$$;

-- ============================================================
-- CREATE ORDER PROCEDURE
--
-- All operations execute in the caller's transaction.
-- Payment authorization is simulated as a local database
-- operation. A real external payment provider requires a
-- durable workflow and compensation strategy.
-- ============================================================

CREATE OR REPLACE PROCEDURE orders.create_order(
    IN p_order_id UUID,
    IN p_customer_id UUID,
    IN p_product_id UUID,
    IN p_quantity INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_product inventory.products%ROWTYPE;
    v_reservation_id UUID;
    v_payment_id UUID;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Order quantity must be positive.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM shared.customers
        WHERE customer_id = p_customer_id
          AND active = TRUE
    ) THEN
        RAISE EXCEPTION 'Customer does not exist or is inactive.';
    END IF;

    SELECT *
    INTO v_product
    FROM inventory.products
    WHERE product_id = p_product_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found or inactive.';
    END IF;

    v_reservation_id := inventory.reserve_stock(
        p_product_id,
        p_quantity,
        15
    );

    INSERT INTO orders.order_records (
        order_id,
        customer_id,
        product_id,
        quantity,
        unit_price,
        order_status
    )
    VALUES (
        p_order_id,
        p_customer_id,
        p_product_id,
        p_quantity,
        v_product.unit_price,
        'PENDING'
    );

    v_payment_id := gen_random_uuid();

    INSERT INTO payments.payment_records (
        payment_id,
        order_id,
        amount,
        payment_status
    )
    VALUES (
        v_payment_id,
        p_order_id,
        v_product.unit_price * p_quantity,
        'AUTHORIZED'
    );

    UPDATE inventory.stock_reservations
    SET reservation_status = 'COMMITTED'
    WHERE reservation_id = v_reservation_id;

    INSERT INTO orders.order_reservations (
        order_id,
        reservation_id
    )
    VALUES (
        p_order_id,
        v_reservation_id
    );

    UPDATE orders.order_records
    SET order_status = 'CONFIRMED'
    WHERE order_id = p_order_id;

    INSERT INTO notifications.event_outbox (
        event_id,
        aggregate_type,
        aggregate_id,
        event_type,
        payload
    )
    VALUES (
        gen_random_uuid(),
        'ORDER',
        p_order_id,
        'ORDER_CONFIRMED',
        jsonb_build_object(
            'order_id', p_order_id,
            'customer_id', p_customer_id,
            'amount', v_product.unit_price * p_quantity
        )
    );
END;
$$;

-- ============================================================
-- PAYMENT REFUND PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE payments.refund_payment(
    IN p_order_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_payment_id UUID;
BEGIN
    SELECT payment_id
    INTO v_payment_id
    FROM payments.payment_records
    WHERE order_id = p_order_id
      AND payment_status = 'AUTHORIZED'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Authorized payment not found.';
    END IF;

    UPDATE payments.payment_records
    SET payment_status = 'REFUNDED',
        refunded_at = NOW()
    WHERE payment_id = v_payment_id;

    UPDATE orders.order_records
    SET order_status = 'CANCELLED'
    WHERE order_id = p_order_id
      AND order_status = 'CONFIRMED';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order is not eligible for cancellation.';
    END IF;

    INSERT INTO notifications.event_outbox (
        event_id,
        aggregate_type,
        aggregate_id,
        event_type,
        payload
    )
    VALUES (
        gen_random_uuid(),
        'ORDER',
        p_order_id,
        'ORDER_CANCELLED',
        jsonb_build_object('order_id', p_order_id)
    );
END;
$$;

-- ============================================================
-- MODULE MIGRATION STATE FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION architecture.advance_module(
    p_module_id UUID,
    p_endpoint TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_current TEXT;
    v_next TEXT;
BEGIN
    SELECT migration_stage
    INTO v_current
    FROM architecture.modules
    WHERE module_id = p_module_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Module not found.';
    END IF;

    v_next := CASE v_current
        WHEN 'MONOLITH' THEN 'BOUNDARIES_DEFINED'
        WHEN 'BOUNDARIES_DEFINED' THEN 'MODULE_ISOLATED'
        WHEN 'MODULE_ISOLATED' THEN 'CONTRACT_STABLE'
        WHEN 'CONTRACT_STABLE' THEN 'EXTERNALIZED'
        ELSE NULL
    END;

    IF v_next IS NULL THEN
        RAISE EXCEPTION 'Module migration is already complete.';
    END IF;

    IF v_next = 'EXTERNALIZED'
       AND (
           p_endpoint IS NULL
           OR p_endpoint NOT LIKE 'https://%'
       ) THEN
        RAISE EXCEPTION 'A valid HTTPS endpoint is required.';
    END IF;

    UPDATE architecture.modules
    SET migration_stage = v_next,
        external_endpoint = CASE
            WHEN v_next = 'EXTERNALIZED' THEN p_endpoint
            ELSE external_endpoint
        END
    WHERE module_id = p_module_id;

    RETURN v_next;
END;
$$;

-- ============================================================
-- ARCHITECTURE VALIDATION VIEW
-- ============================================================

CREATE OR REPLACE VIEW architecture.dependency_report AS
SELECT
    source.module_name AS source_module,
    target.module_name AS target_module,
    dependency.dependency_type,
    CASE
        WHEN source.module_name = 'orders'
             AND target.module_name IN (
                 'inventory', 'payments', 'shared'
             )
            THEN 'ALLOWED'

        WHEN source.module_name = 'inventory'
             AND target.module_name = 'shared'
            THEN 'ALLOWED'

        WHEN source.module_name = 'payments'
             AND target.module_name = 'shared'
            THEN 'ALLOWED'

        WHEN source.module_name = 'notifications'
             AND target.module_name IN ('shared', 'orders')
            THEN 'ALLOWED'

        ELSE 'VIOLATION'
    END AS dependency_status
FROM architecture.module_dependencies dependency
JOIN architecture.modules source
    ON source.module_id = dependency.source_module
JOIN architecture.modules target
    ON target.module_id = dependency.target_module;

-- ============================================================
-- REPORTING VIEW
-- ============================================================

CREATE OR REPLACE VIEW orders.order_summary AS
SELECT
    o.order_id,
    c.customer_name,
    p.product_name,
    o.quantity,
    o.unit_price,
    o.total_amount,
    o.order_status,
    payment.payment_status,
    o.created_at
FROM orders.order_records o
JOIN shared.customers c
    ON c.customer_id = o.customer_id
JOIN inventory.products p
    ON p.product_id = o.product_id
LEFT JOIN payments.payment_records payment
    ON payment.order_id = o.order_id;

-- ============================================================
-- WORKFLOW: CREATE A VALID ORDER
-- ============================================================

DO $$
BEGIN
    CALL orders.create_order(
        '40000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000001',
        '30000000-0000-0000-0000-000000000001',
        2
    );
END;
$$;

-- ============================================================
-- WORKFLOW: CREATE ANOTHER ORDER
-- ============================================================

DO $$
BEGIN
    CALL orders.create_order(
        '40000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000002',
        '30000000-0000-0000-0000-000000000002',
        1
    );
END;
$$;

-- ============================================================
-- RETRIEVAL
-- ============================================================

SELECT *
FROM orders.order_summary
ORDER BY created_at DESC;

-- ============================================================
-- VALIDATION: STOCK MUST REMAIN NONNEGATIVE
-- ============================================================

SELECT
    product_id,
    sku,
    product_name,
    available_quantity,
    CASE
        WHEN available_quantity >= 0 THEN 'VALID'
        ELSE 'INVALID'
    END AS stock_validation
FROM inventory.products;

-- ============================================================
-- AGGREGATION: REVENUE BY PRODUCT
-- ============================================================

SELECT
    p.sku,
    p.product_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.quantity), 0) AS units_ordered,
    COALESCE(
        SUM(o.total_amount)
        FILTER (WHERE o.order_status = 'CONFIRMED'),
        0
    ) AS confirmed_revenue
FROM inventory.products p
LEFT JOIN orders.order_records o
    ON o.product_id = p.product_id
GROUP BY p.product_id, p.sku, p.product_name
ORDER BY confirmed_revenue DESC;

-- ============================================================
-- CTE: MODULE DEPENDENCY EVALUATION
-- ============================================================

WITH dependency_evaluation AS (
    SELECT
        source_module,
        target_module,
        dependency_status
    FROM architecture.dependency_report
)
SELECT
    source_module,
    target_module,
    dependency_status
FROM dependency_evaluation
WHERE dependency_status = 'VIOLATION';

-- ============================================================
-- ELIGIBILITY: ORDERS AVAILABLE FOR CANCELLATION
-- ============================================================

SELECT
    o.order_id,
    o.total_amount,
    p.payment_status,
    CASE
        WHEN o.order_status = 'CONFIRMED'
             AND p.payment_status = 'AUTHORIZED'
            THEN TRUE
        ELSE FALSE
    END AS cancellation_eligible
FROM orders.order_records o
JOIN payments.payment_records p
    ON p.order_id = o.order_id;

-- ============================================================
-- TRANSACTION: CANCEL FIRST ORDER
-- ============================================================

BEGIN;

CALL payments.refund_payment(
    '40000000-0000-0000-0000-000000000001'
);

COMMIT;

-- ============================================================
-- REPORTING: ORDER STATUS DISTRIBUTION
-- ============================================================

SELECT
    order_status,
    COUNT(*) AS total_orders,
    SUM(total_amount) AS total_value
FROM orders.order_records
GROUP BY order_status
ORDER BY order_status;

-- ============================================================
-- TRANSACTIONAL OUTBOX PROCESSING
--
-- Workers should claim events using FOR UPDATE SKIP LOCKED.
-- The transaction commits before external delivery.
-- ============================================================

BEGIN;

WITH claimed_events AS (
    SELECT event_id
    FROM notifications.event_outbox
    WHERE event_status = 'PENDING'
      AND next_attempt_at <= NOW()
    ORDER BY occurred_at
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE notifications.event_outbox event
SET attempts = attempts + 1
FROM claimed_events
WHERE event.event_id = claimed_events.event_id
RETURNING event.event_id,
          event.event_type,
          event.payload,
          event.attempts;

COMMIT;

-- ============================================================
-- MARK A SUCCESSFULLY DELIVERED EVENT
-- ============================================================

UPDATE notifications.event_outbox
SET event_status = 'PUBLISHED',
    published_at = NOW()
WHERE event_id = (
    SELECT event_id
    FROM notifications.event_outbox
    WHERE event_status = 'PENDING'
    ORDER BY occurred_at
    LIMIT 1
);

-- ============================================================
-- MIGRATION WORKFLOW
-- ============================================================

SELECT architecture.advance_module(
    '10000000-0000-0000-0000-000000000005'
);

SELECT architecture.advance_module(
    '10000000-0000-0000-0000-000000000005'
);

SELECT architecture.advance_module(
    '10000000-0000-0000-0000-000000000005'
);

SELECT architecture.advance_module(
    '10000000-0000-0000-0000-000000000005',
    'https://notifications.example.com'
);

SELECT
    module_name,
    migration_stage,
    external_endpoint
FROM architecture.modules
ORDER BY module_name;

-- ============================================================
-- FINAL ARCHITECTURE REPORT
-- ============================================================

SELECT *
FROM architecture.dependency_report
ORDER BY source_module, target_module;

SELECT
    COUNT(*) FILTER (
        WHERE dependency_status = 'ALLOWED'
    ) AS allowed_dependencies,
    COUNT(*) FILTER (
        WHERE dependency_status = 'VIOLATION'
    ) AS dependency_violations
FROM architecture.dependency_report;

SELECT
    event_type,
    event_status,
    COUNT(*) AS event_count
FROM notifications.event_outbox
GROUP BY event_type, event_status
ORDER BY event_type, event_status;

COMMIT;
