-- ============================================================
-- DOMAIN-DRIVEN DESIGN
-- BOUNDED CONTEXTS, AGGREGATES AND ENTITIES
-- PostgreSQL 18 compatible
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ddd;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 1. SHARED DOMAIN TYPES
-- ============================================================

CREATE TYPE ddd.order_status AS ENUM (
    'draft',
    'submitted',
    'confirmed',
    'cancelled'
);

CREATE TYPE ddd.invoice_status AS ENUM (
    'unpaid',
    'paid',
    'void'
);

CREATE TYPE ddd.event_status AS ENUM (
    'pending',
    'processed',
    'failed'
);

-- ============================================================
-- 2. CATALOG BOUNDED CONTEXT
-- ============================================================

CREATE TABLE ddd.catalog_products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku VARCHAR(60) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    description TEXT,
    unit_price NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT catalog_name_not_empty
        CHECK (LENGTH(TRIM(product_name)) > 0),

    CONSTRAINT catalog_price_nonnegative
        CHECK (unit_price >= 0),

    CONSTRAINT catalog_currency_valid
        CHECK (currency ~ '^[A-Z]{3}$'),

    CONSTRAINT catalog_version_nonnegative
        CHECK (version >= 0)
);

CREATE INDEX idx_catalog_active_products
ON ddd.catalog_products(product_name)
WHERE is_active = TRUE;

-- Catalog changes increment the entity version.
CREATE OR REPLACE FUNCTION ddd.update_catalog_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.version := OLD.version + 1;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_catalog_version
BEFORE UPDATE ON ddd.catalog_products
FOR EACH ROW
EXECUTE FUNCTION ddd.update_catalog_version();

-- ============================================================
-- 3. CUSTOMER CONTEXT
-- ============================================================

CREATE TABLE ddd.customers (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_code VARCHAR(50) NOT NULL UNIQUE,
    customer_name VARCHAR(200) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT customer_name_valid
        CHECK (LENGTH(TRIM(customer_name)) > 0),

    CONSTRAINT customer_email_valid
        CHECK (email ~* '^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$')
);

-- ============================================================
-- 4. INVENTORY BOUNDED CONTEXT
-- ============================================================

CREATE TABLE ddd.inventory_items (
    product_id UUID PRIMARY KEY,
    available_quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT inventory_product_fk
        FOREIGN KEY (product_id)
        REFERENCES ddd.catalog_products(product_id)
        ON DELETE RESTRICT,

    CONSTRAINT inventory_available_nonnegative
        CHECK (available_quantity >= 0),

    CONSTRAINT inventory_reserved_nonnegative
        CHECK (reserved_quantity >= 0),

    CONSTRAINT inventory_version_nonnegative
        CHECK (version >= 0)
);

-- ============================================================
-- 5. ORDER MANAGEMENT BOUNDED CONTEXT
-- ============================================================

CREATE TABLE ddd.orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(50) NOT NULL UNIQUE,
    customer_id UUID NOT NULL,
    status ddd.order_status NOT NULL DEFAULT 'draft',
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    total_amount NUMERIC(16, 2) NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES ddd.customers(customer_id)
        ON DELETE RESTRICT,

    CONSTRAINT orders_currency_valid
        CHECK (currency ~ '^[A-Z]{3}$'),

    CONSTRAINT orders_amount_nonnegative
        CHECK (total_amount >= 0),

    CONSTRAINT orders_version_nonnegative
        CHECK (version >= 0),

    CONSTRAINT submitted_order_has_timestamp
        CHECK (
            status NOT IN ('submitted', 'confirmed')
            OR submitted_at IS NOT NULL
        )
);

CREATE INDEX idx_orders_customer_date
ON ddd.orders(customer_id, created_at DESC);

CREATE INDEX idx_orders_processing
ON ddd.orders(status, created_at)
WHERE status IN ('draft', 'submitted');

-- Order lines are child entities inside the Order aggregate.
CREATE TABLE ddd.order_lines (
    order_id UUID NOT NULL,
    line_number INTEGER NOT NULL,
    product_id UUID NOT NULL,
    product_name_snapshot VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_snapshot NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    line_total NUMERIC(16, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_snapshot
        ) STORED,

    PRIMARY KEY (order_id, line_number),

    CONSTRAINT order_lines_order_fk
        FOREIGN KEY (order_id)
        REFERENCES ddd.orders(order_id)
        ON DELETE CASCADE,

    CONSTRAINT order_lines_product_fk
        FOREIGN KEY (product_id)
        REFERENCES ddd.catalog_products(product_id)
        ON DELETE RESTRICT,

    CONSTRAINT order_line_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT order_line_price_nonnegative
        CHECK (unit_price_snapshot >= 0),

    CONSTRAINT order_line_currency_valid
        CHECK (currency ~ '^[A-Z]{3}$'),

    CONSTRAINT order_line_name_valid
        CHECK (LENGTH(TRIM(product_name_snapshot)) > 0)
);

CREATE INDEX idx_order_lines_product
ON ddd.order_lines(product_id);

-- ============================================================
-- 6. AGGREGATE INTEGRITY
-- ============================================================

-- Order lines cannot be modified after submission.
CREATE OR REPLACE FUNCTION ddd.validate_order_line_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_status ddd.order_status;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.order_id <> OLD.order_id THEN
        RAISE EXCEPTION 'An order line cannot change its parent aggregate';
    END IF;

    IF TG_OP = 'DELETE' THEN
        SELECT status INTO current_status
        FROM ddd.orders
        WHERE order_id = OLD.order_id
        FOR UPDATE;

        IF current_status <> 'draft' THEN
            RAISE EXCEPTION
                'Lines of a non-draft order cannot be deleted';
        END IF;

        RETURN OLD;
    END IF;

    SELECT status INTO current_status
    FROM ddd.orders
    WHERE order_id = NEW.order_id
    FOR UPDATE;

    IF current_status <> 'draft' THEN
        RAISE EXCEPTION
            'Lines can only be changed in draft orders';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM ddd.catalog_products p
        WHERE p.product_id = NEW.product_id
    ) THEN
        RAISE EXCEPTION 'Product does not exist';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_order_line_integrity
BEFORE INSERT OR UPDATE OR DELETE
ON ddd.order_lines
FOR EACH ROW
EXECUTE FUNCTION ddd.validate_order_line_change();

-- All order lines must use the aggregate's currency.
CREATE OR REPLACE FUNCTION ddd.validate_order_line_currency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    order_currency CHAR(3);
BEGIN
    SELECT currency INTO order_currency
    FROM ddd.orders
    WHERE order_id = NEW.order_id;

    IF NEW.currency <> order_currency THEN
        RAISE EXCEPTION 'Order and order-line currencies must match';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_order_line_currency
BEFORE INSERT OR UPDATE
ON ddd.order_lines
FOR EACH ROW
EXECUTE FUNCTION ddd.validate_order_line_currency();

-- Recalculate the aggregate total when a child changes.
CREATE OR REPLACE FUNCTION ddd.recalculate_order_total()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_order UUID;
BEGIN
    target_order := CASE
        WHEN TG_OP = 'DELETE' THEN OLD.order_id
        ELSE NEW.order_id
    END;

    UPDATE ddd.orders
    SET total_amount = COALESCE(
        (
            SELECT SUM(line_total)
            FROM ddd.order_lines
            WHERE order_id = target_order
        ),
        0
    ),
    version = version + 1,
    updated_at = NOW()
    WHERE order_id = target_order;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_recalculate_order_total
AFTER INSERT OR UPDATE OR DELETE
ON ddd.order_lines
FOR EACH ROW
EXECUTE FUNCTION ddd.recalculate_order_total();

-- ============================================================
-- 7. ORDER STATE TRANSITIONS
-- ============================================================

CREATE OR REPLACE FUNCTION ddd.validate_order_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = OLD.status THEN
        RETURN NEW;
    END IF;

    IF OLD.status = 'draft' AND
       NEW.status IN ('submitted', 'cancelled') THEN
        NULL;

    ELSIF OLD.status = 'submitted' AND
          NEW.status IN ('confirmed', 'cancelled') THEN
        NULL;

    ELSE
        RAISE EXCEPTION
            'Invalid order transition: % to %',
            OLD.status,
            NEW.status;
    END IF;

    IF NEW.status = 'submitted' THEN
        IF NOT EXISTS (
            SELECT 1
            FROM ddd.order_lines
            WHERE order_id = NEW.order_id
        ) THEN
            RAISE EXCEPTION 'Empty orders cannot be submitted';
        END IF;

        NEW.submitted_at := NOW();
    END IF;

    NEW.version := OLD.version + 1;
    NEW.updated_at := NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_order_state_transition
BEFORE UPDATE OF status
ON ddd.orders
FOR EACH ROW
EXECUTE FUNCTION ddd.validate_order_transition();

-- ============================================================
-- 8. BILLING BOUNDED CONTEXT
-- ============================================================

CREATE TABLE ddd.invoices (
    invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    order_id UUID NOT NULL UNIQUE,
    amount NUMERIC(16, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status ddd.invoice_status NOT NULL DEFAULT 'unpaid',
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ,

    CONSTRAINT invoice_order_fk
        FOREIGN KEY (order_id)
        REFERENCES ddd.orders(order_id)
        ON DELETE RESTRICT,

    CONSTRAINT invoice_amount_nonnegative
        CHECK (amount >= 0),

    CONSTRAINT invoice_currency_valid
        CHECK (currency ~ '^[A-Z]{3}$'),

    CONSTRAINT invoice_paid_timestamp
        CHECK (
            (status = 'paid' AND paid_at IS NOT NULL)
            OR
            (status <> 'paid' AND paid_at IS NULL)
        )
);

-- Invoice can only be created for a submitted or confirmed order.
CREATE OR REPLACE FUNCTION ddd.validate_invoice_creation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_status ddd.order_status;
    expected_amount NUMERIC(16, 2);
    expected_currency CHAR(3);
BEGIN
    SELECT status, total_amount, currency
    INTO current_status, expected_amount, expected_currency
    FROM ddd.orders
    WHERE order_id = NEW.order_id;

    IF current_status NOT IN ('submitted', 'confirmed') THEN
        RAISE EXCEPTION 'Invoice requires a submitted order';
    END IF;

    IF NEW.amount <> expected_amount OR
       NEW.currency <> expected_currency THEN
        RAISE EXCEPTION 'Invoice amount differs from order aggregate';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_invoice_validation
BEFORE INSERT
ON ddd.invoices
FOR EACH ROW
EXECUTE FUNCTION ddd.validate_invoice_creation();

-- ============================================================
-- 9. DOMAIN EVENT OUTBOX
-- ============================================================

CREATE TABLE ddd.domain_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    event_version BIGINT NOT NULL,
    payload JSONB NOT NULL,
    status ddd.event_status NOT NULL DEFAULT 'pending',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,

    CONSTRAINT event_version_positive
        CHECK (event_version > 0),

    CONSTRAINT event_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),

    CONSTRAINT event_processed_timestamp
        CHECK (
            (status = 'processed' AND processed_at IS NOT NULL)
            OR
            (status <> 'processed' AND processed_at IS NULL)
        ),

    CONSTRAINT event_aggregate_sequence_unique
        UNIQUE (
            aggregate_type,
            aggregate_id,
            event_version
        )
);

CREATE INDEX idx_pending_domain_events
ON ddd.domain_events(occurred_at)
WHERE status = 'pending';

-- ============================================================
-- 10. APPROVAL AND APPLICATION SERVICE FUNCTIONS
-- ============================================================

CREATE OR REPLACE FUNCTION ddd.submit_order(
    p_order_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    order_record ddd.orders%ROWTYPE;
    event_payload JSONB;
BEGIN
    SELECT *
    INTO order_record
    FROM ddd.orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order not found';
    END IF;

    IF order_record.status <> 'draft' THEN
        RAISE EXCEPTION 'Only draft orders can be submitted';
    END IF;

    IF order_record.total_amount <= 0 THEN
        RAISE EXCEPTION 'Order must have a positive total';
    END IF;

    UPDATE ddd.orders
    SET status = 'submitted'
    WHERE order_id = p_order_id;

    SELECT jsonb_build_object(
        'order_id', p_order_id,
        'customer_id', order_record.customer_id,
        'total_amount', order_record.total_amount,
        'currency', order_record.currency,
        'line_count', (
            SELECT COUNT(*)
            FROM ddd.order_lines
            WHERE order_id = p_order_id
        )
    )
    INTO event_payload;

    INSERT INTO ddd.domain_events (
        aggregate_type,
        aggregate_id,
        event_type,
        event_version,
        payload
    )
    SELECT
        'Order',
        p_order_id,
        'OrderSubmitted',
        version,
        event_payload
    FROM ddd.orders
    WHERE order_id = p_order_id;
END;
$$;

CREATE OR REPLACE FUNCTION ddd.confirm_order(
    p_order_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE ddd.orders
    SET status = 'confirmed'
    WHERE order_id = p_order_id
      AND status = 'submitted';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order not found or cannot be confirmed';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION ddd.cancel_order(
    p_order_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE ddd.orders
    SET status = 'cancelled'
    WHERE order_id = p_order_id
      AND status IN ('draft', 'submitted');

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order not found or cannot be cancelled';
    END IF;
END;
$$;

-- ============================================================
-- 11. INVENTORY RESERVATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION ddd.reserve_inventory(
    p_product_id UUID,
    p_quantity INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Reservation quantity must be positive';
    END IF;

    UPDATE ddd.inventory_items
    SET available_quantity = available_quantity - p_quantity,
        reserved_quantity = reserved_quantity + p_quantity,
        version = version + 1,
        updated_at = NOW()
    WHERE product_id = p_product_id
      AND available_quantity >= p_quantity;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Inventory missing or insufficient stock';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION ddd.release_inventory(
    p_product_id UUID,
    p_quantity INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Release quantity must be positive';
    END IF;

    UPDATE ddd.inventory_items
    SET available_quantity = available_quantity + p_quantity,
        reserved_quantity = reserved_quantity - p_quantity,
        version = version + 1,
        updated_at = NOW()
    WHERE product_id = p_product_id
      AND reserved_quantity >= p_quantity;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Insufficient reserved stock';
    END IF;
END;
$$;

-- ============================================================
-- 12. BILLING FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION ddd.create_invoice(
    p_order_id UUID,
    p_invoice_number VARCHAR(50)
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    result_id UUID;
BEGIN
    INSERT INTO ddd.invoices (
        invoice_number,
        order_id,
        amount,
        currency
    )
    SELECT
        p_invoice_number,
        order_id,
        total_amount,
        currency
    FROM ddd.orders
    WHERE order_id = p_order_id
      AND status IN ('submitted', 'confirmed')
    RETURNING invoice_id INTO result_id;

    IF result_id IS NULL THEN
        RAISE EXCEPTION 'Eligible order not found';
    END IF;

    RETURN result_id;
END;
$$;

-- ============================================================
-- 13. WORKFLOW PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE ddd.process_order(
    p_order_id UUID,
    p_invoice_number VARCHAR(50)
)
LANGUAGE plpgsql
AS $$
DECLARE
    line_record RECORD;
    reservation_count INTEGER := 0;
    created_invoice UUID;
BEGIN
    -- All operations execute within the caller's transaction.
    PERFORM ddd.submit_order(p_order_id);

    FOR line_record IN
        SELECT product_id, quantity
        FROM ddd.order_lines
        WHERE order_id = p_order_id
        ORDER BY product_id
    LOOP
        PERFORM ddd.reserve_inventory(
            line_record.product_id,
            line_record.quantity
        );

        reservation_count := reservation_count + 1;
    END LOOP;

    created_invoice := ddd.create_invoice(
        p_order_id,
        p_invoice_number
    );

    RAISE NOTICE
        'Order % processed. Invoice %. Reservations: %',
        p_order_id,
        created_invoice,
        reservation_count;
END;
$$;

-- ============================================================
-- 14. REPORTING VIEWS
-- ============================================================

CREATE OR REPLACE VIEW ddd.order_summary AS
SELECT
    o.order_id,
    o.order_number,
    c.customer_code,
    c.customer_name,
    o.status,
    o.total_amount,
    o.currency,
    COUNT(ol.line_number) AS line_count,
    COALESCE(SUM(ol.quantity), 0) AS total_units,
    o.created_at,
    o.submitted_at
FROM ddd.orders o
JOIN ddd.customers c
    ON c.customer_id = o.customer_id
LEFT JOIN ddd.order_lines ol
    ON ol.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    c.customer_code,
    c.customer_name,
    o.status,
    o.total_amount,
    o.currency,
    o.created_at,
    o.submitted_at;

CREATE OR REPLACE VIEW ddd.context_inventory_report AS
SELECT
    p.sku,
    p.product_name,
    p.is_active,
    i.available_quantity,
    i.reserved_quantity,
    i.version
FROM ddd.catalog_products p
LEFT JOIN ddd.inventory_items i
    ON i.product_id = p.product_id;

CREATE OR REPLACE VIEW ddd.billing_report AS
SELECT
    i.invoice_number,
    o.order_number,
    c.customer_name,
    i.amount,
    i.currency,
    i.status,
    i.issued_at,
    i.paid_at
FROM ddd.invoices i
JOIN ddd.orders o ON o.order_id = i.order_id
JOIN ddd.customers c ON c.customer_id = o.customer_id;

-- ============================================================
-- 15. SAMPLE DOMAIN DATA
-- ============================================================

INSERT INTO ddd.customers (
    customer_id,
    customer_code,
    customer_name,
    email
)
VALUES
(
    '10000000-0000-0000-0000-000000000001',
    'CUST-001',
    'National Technology Services',
    'procurement@example.in'
),
(
    '10000000-0000-0000-0000-000000000002',
    'CUST-002',
    'Enterprise Systems Limited',
    'operations@example.in'
);

INSERT INTO ddd.catalog_products (
    product_id,
    sku,
    product_name,
    description,
    unit_price,
    currency
)
VALUES
(
    '20000000-0000-0000-0000-000000000001',
    'SEC-100',
    'Enterprise Security Appliance',
    'Network security hardware',
    45000.00,
    'INR'
),
(
    '20000000-0000-0000-0000-000000000002',
    'DB-200',
    'Database Server',
    'Enterprise database server',
    125000.00,
    'INR'
),
(
    '20000000-0000-0000-0000-000000000003',
    'LEG-300',
    'Legacy Network Appliance',
    'Inactive demonstration product',
    25000.00,
    'INR'
);

UPDATE ddd.catalog_products
SET is_active = FALSE
WHERE sku = 'LEG-300';

INSERT INTO ddd.inventory_items (
    product_id,
    available_quantity,
    reserved_quantity
)
VALUES
(
    '20000000-0000-0000-0000-000000000001',
    20,
    0
),
(
    '20000000-0000-0000-0000-000000000002',
    8,
    0
);

INSERT INTO ddd.orders (
    order_id,
    order_number,
    customer_id,
    currency
)
VALUES
(
    '30000000-0000-0000-0000-000000000001',
    'ORD-1001',
    '10000000-0000-0000-0000-000000000001',
    'INR'
),
(
    '30000000-0000-0000-0000-000000000002',
    'ORD-1002',
    '10000000-0000-0000-0000-000000000002',
    'INR'
);

INSERT INTO ddd.order_lines (
    order_id,
    line_number,
    product_id,
    product_name_snapshot,
    quantity,
    unit_price_snapshot,
    currency
)
VALUES
(
    '30000000-0000-0000-0000-000000000001',
    1,
    '20000000-0000-0000-0000-000000000001',
    'Enterprise Security Appliance',
    2,
    45000.00,
    'INR'
),
(
    '30000000-0000-0000-0000-000000000001',
    2,
    '20000000-0000-0000-0000-000000000002',
    'Database Server',
    1,
    125000.00,
    'INR'
),
(
    '30000000-0000-0000-0000-000000000002',
    1,
    '20000000-0000-0000-0000-000000000001',
    'Enterprise Security Appliance',
    1,
    45000.00,
    'INR'
);

COMMIT;

-- ============================================================
-- 16. WORKFLOW TRANSACTION
-- ============================================================

BEGIN;

CALL ddd.process_order(
    '30000000-0000-0000-0000-000000000001',
    'INV-1001'
);

COMMIT;

-- ============================================================
-- 17. VALIDATION QUERIES
-- ============================================================

-- Order aggregate and its children.
SELECT
    o.order_number,
    o.status,
    o.total_amount,
    ol.line_number,
    ol.product_name_snapshot,
    ol.quantity,
    ol.line_total
FROM ddd.orders o
LEFT JOIN ddd.order_lines ol
    ON ol.order_id = o.order_id
ORDER BY o.order_number, ol.line_number;

-- Inventory availability and reservations.
SELECT *
FROM ddd.context_inventory_report
ORDER BY sku;

-- Cross-context reporting.
SELECT *
FROM ddd.order_summary
ORDER BY created_at;

-- Billing results.
SELECT *
FROM ddd.billing_report;

-- ============================================================
-- 18. CTE: DOMAIN AGGREGATE ANALYSIS
-- ============================================================

WITH order_metrics AS (
    SELECT
        o.customer_id,
        o.status,
        COUNT(*) AS order_count,
        SUM(o.total_amount) AS order_value
    FROM ddd.orders o
    GROUP BY o.customer_id, o.status
),
customer_metrics AS (
    SELECT
        c.customer_code,
        c.customer_name,
        COALESCE(SUM(m.order_count), 0) AS total_orders,
        COALESCE(SUM(m.order_value), 0) AS total_value
    FROM ddd.customers c
    LEFT JOIN order_metrics m
        ON m.customer_id = c.customer_id
    GROUP BY c.customer_code, c.customer_name
)
SELECT *
FROM customer_metrics
ORDER BY total_value DESC;

-- ============================================================
-- 19. ELIGIBILITY DETERMINATION
-- ============================================================

-- This query evaluates whether a draft order has enough stock.
-- It does not reserve stock or change order state.

SELECT
    o.order_number,
    o.status,
    COUNT(ol.line_number) AS line_count,
    BOOL_AND(
        p.is_active
        AND COALESCE(i.available_quantity >= ol.quantity, FALSE)
    ) AS inventory_eligible,
    CASE
        WHEN o.status <> 'draft' THEN 'NOT_DRAFT'
        WHEN COUNT(ol.line_number) = 0 THEN 'EMPTY_ORDER'
        WHEN BOOL_AND(
            p.is_active
            AND COALESCE(i.available_quantity >= ol.quantity, FALSE)
        ) THEN 'ELIGIBLE'
        ELSE 'NOT_ELIGIBLE'
    END AS eligibility
FROM ddd.orders o
LEFT JOIN ddd.order_lines ol
    ON ol.order_id = o.order_id
LEFT JOIN ddd.catalog_products p
    ON p.product_id = ol.product_id
LEFT JOIN ddd.inventory_items i
    ON i.product_id = ol.product_id
GROUP BY o.order_id, o.order_number, o.status;

-- ============================================================
-- 20. DOMAIN EVENT PROCESSING
-- ============================================================

-- Select pending events using row locks.
BEGIN;

WITH selected_events AS (
    SELECT event_id
    FROM ddd.domain_events
    WHERE status = 'pending'
    ORDER BY occurred_at
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE ddd.domain_events e
SET status = 'processed',
    processed_at = NOW()
FROM selected_events s
WHERE e.event_id = s.event_id
RETURNING e.event_id, e.event_type, e.aggregate_id;

COMMIT;

-- ============================================================
-- 21. EDGE-CASE VALIDATION EXAMPLES
-- ============================================================

-- Expected failure: a submitted order cannot receive another line.
-- Run independently to observe the exception.
--
-- INSERT INTO ddd.order_lines (
--     order_id, line_number, product_id,
--     product_name_snapshot, quantity,
--     unit_price_snapshot, currency
-- )
-- VALUES (
--     '30000000-0000-0000-0000-000000000001',
--     3,
--     '20000000-0000-0000-0000-000000000001',
--     'Enterprise Security Appliance',
--     1, 45000.00, 'INR'
-- );

-- Expected failure: a duplicate invoice for the same order.
-- The UNIQUE constraint on order_id rejects it.

-- Expected failure: a negative quantity.
-- The CHECK constraint on order_lines rejects it.

-- Expected failure: an invalid order transition.
-- A confirmed order cannot return to draft.

-- ============================================================
-- 22. SECURITY AND OPERATIONAL CONSIDERATIONS
-- ============================================================

-- Application users should receive only the permissions required
-- by their bounded context. Do not grant unrestricted schema access.
--
-- Example context-level permissions:
--
-- CREATE ROLE ddd_catalog_reader NOLOGIN;
-- GRANT USAGE ON SCHEMA ddd TO ddd_catalog_reader;
-- GRANT SELECT ON ddd.catalog_products TO ddd_catalog_reader;
--
-- CREATE ROLE ddd_order_operator NOLOGIN;
-- GRANT USAGE ON SCHEMA ddd TO ddd_order_operator;
-- GRANT SELECT, INSERT, UPDATE ON ddd.orders TO ddd_order_operator;
-- GRANT SELECT, INSERT, UPDATE, DELETE
--     ON ddd.order_lines TO ddd_order_operator;
--
-- In production, use separate roles for each context.
-- Execute application transactions with least privilege.
-- Protect customer information and restrict event payload contents.
-- Use an outbox publisher with retry, monitoring and idempotency.
-- Apply explicit transaction isolation and retry policies where needed.

-- ============================================================
-- 23. FINAL DOMAIN REPORT
-- ============================================================

SELECT
    'CATALOG' AS bounded_context,
    COUNT(*) AS records
FROM ddd.catalog_products

UNION ALL

SELECT
    'CUSTOMER',
    COUNT(*)
FROM ddd.customers

UNION ALL

SELECT
    'INVENTORY',
    COUNT(*)
FROM ddd.inventory_items

UNION ALL

SELECT
    'ORDER',
    COUNT(*)
FROM ddd.orders

UNION ALL

SELECT
    'ORDER_LINE',
    COUNT(*)
FROM ddd.order_lines

UNION ALL

SELECT
    'BILLING',
    COUNT(*)
FROM ddd.invoices

UNION ALL

SELECT
    'DOMAIN_EVENT',
    COUNT(*)
FROM ddd.domain_events;
