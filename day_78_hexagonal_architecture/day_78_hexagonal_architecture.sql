-- ============================================================
-- HEXAGONAL ARCHITECTURE: PORTS AND ADAPTERS
-- PostgreSQL 15+
--
-- Order processing bounded context.
--
-- Relational components:
--   Domain entities
--   Input and output ports
--   Adapter registrations
--   Use cases
--   Adapter executions
--   Inventory reservations
--   Payment transactions
--   Integration events
--   Transactional outbox
--   Audit records
--
-- The database acts as a secondary persistence adapter.
-- Application services remain responsible for coordinating
-- external payment and inventory capabilities.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS hexagonal;

SET search_path TO hexagonal, public;

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE order_status AS ENUM (
    'PENDING',
    'CONFIRMED',
    'CANCELLED'
);

CREATE TYPE adapter_direction AS ENUM (
    'PRIMARY',
    'SECONDARY'
);

CREATE TYPE adapter_type AS ENUM (
    'HTTP',
    'CLI',
    'DATABASE',
    'INVENTORY',
    'PAYMENT',
    'EVENT_BUS',
    'MESSAGE_QUEUE'
);

CREATE TYPE execution_status AS ENUM (
    'STARTED',
    'SUCCEEDED',
    'FAILED',
    'COMPENSATED'
);

CREATE TYPE payment_status AS ENUM (
    'CHARGED',
    'REFUNDED',
    'FAILED'
);

CREATE TYPE reservation_status AS ENUM (
    'RESERVED',
    'RELEASED',
    'CONSUMED'
);

-- ============================================================
-- DOMAIN TABLES
-- ============================================================

CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_reference VARCHAR(100) NOT NULL UNIQUE,
    customer_name VARCHAR(150) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT customer_reference_not_empty
        CHECK (LENGTH(TRIM(external_reference)) > 0),

    CONSTRAINT customer_name_not_empty
        CHECK (LENGTH(TRIM(customer_name)) > 0)
);

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT product_price_positive
        CHECK (unit_price > 0),

    CONSTRAINT product_currency_valid
        CHECK (currency ~ '^[A-Z]{3}$')
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_reference UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    status order_status NOT NULL DEFAULT 'PENDING',
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT order_version_nonnegative
        CHECK (version >= 0),

    CONSTRAINT order_currency_valid
        CHECK (currency ~ '^[A-Z]{3}$')
);

CREATE TABLE order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,

    CONSTRAINT item_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT item_price_positive
        CHECK (unit_price > 0),

    CONSTRAINT unique_order_product
        UNIQUE (order_id, product_id)
);

-- ============================================================
-- PORT AND ADAPTER REGISTRY
-- ============================================================

CREATE TABLE architecture_ports (
    port_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    port_name VARCHAR(120) NOT NULL UNIQUE,
    direction adapter_direction NOT NULL,
    description TEXT NOT NULL,
    contract_version INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT port_version_positive
        CHECK (contract_version > 0)
);

CREATE TABLE adapters (
    adapter_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    adapter_name VARCHAR(120) NOT NULL UNIQUE,
    adapter_kind adapter_type NOT NULL,
    description TEXT NOT NULL,
    implementation_version VARCHAR(40) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE adapter_port_bindings (
    binding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    port_id BIGINT NOT NULL
        REFERENCES architecture_ports(port_id),
    adapter_id BIGINT NOT NULL
        REFERENCES adapters(adapter_id),
    priority INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    bound_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_port_adapter
        UNIQUE (port_id, adapter_id),

    CONSTRAINT priority_positive
        CHECK (priority > 0)
);

CREATE INDEX idx_active_port_bindings
    ON adapter_port_bindings(port_id, priority)
    WHERE active = TRUE;

-- ============================================================
-- APPLICATION USE CASES
-- ============================================================

CREATE TABLE use_cases (
    use_case_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    use_case_name VARCHAR(120) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE use_case_port_dependencies (
    use_case_id BIGINT NOT NULL
        REFERENCES use_cases(use_case_id),
    port_id BIGINT NOT NULL
        REFERENCES architecture_ports(port_id),
    required BOOLEAN NOT NULL DEFAULT TRUE,

    PRIMARY KEY (use_case_id, port_id)
);

CREATE TABLE use_case_executions (
    execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    use_case_id BIGINT NOT NULL
        REFERENCES use_cases(use_case_id),
    adapter_id BIGINT
        REFERENCES adapters(adapter_id),
    order_id BIGINT
        REFERENCES orders(order_id),
    execution_status execution_status NOT NULL DEFAULT 'STARTED',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_code VARCHAR(80),
    error_message TEXT,

    CONSTRAINT execution_completion_valid
        CHECK (
            completed_at IS NULL
            OR completed_at >= started_at
        )
);

CREATE INDEX idx_use_case_execution_status
    ON use_case_executions(execution_status, started_at DESC);

-- ============================================================
-- SECONDARY ADAPTER DATA
-- ============================================================

CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY
        REFERENCES products(product_id),
    available_quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT inventory_available_nonnegative
        CHECK (available_quantity >= 0),

    CONSTRAINT inventory_reserved_nonnegative
        CHECK (reserved_quantity >= 0)
);

CREATE TABLE inventory_reservations (
    reservation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES orders(order_id),
    product_id BIGINT NOT NULL
        REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    status reservation_status NOT NULL DEFAULT 'RESERVED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT reservation_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT unique_order_product_reservation
        UNIQUE (order_id, product_id)
);

CREATE INDEX idx_active_reservations
    ON inventory_reservations(order_id, status);

CREATE TABLE payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE
        REFERENCES orders(order_id),
    external_payment_reference VARCHAR(150) NOT NULL UNIQUE,
    amount NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status payment_status NOT NULL,
    idempotency_key UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT payment_amount_positive
        CHECK (amount > 0)
);

-- ============================================================
-- EVENT OUTBOX
-- ============================================================

CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,

    CONSTRAINT outbox_publication_consistent
        CHECK (
            (published = FALSE AND published_at IS NULL)
            OR
            (published = TRUE AND published_at IS NOT NULL)
        )
);

CREATE INDEX idx_unpublished_outbox
    ON integration_outbox(created_at)
    WHERE published = FALSE;

-- ============================================================
-- AUDIT TABLE
-- ============================================================

CREATE TABLE domain_audit_log (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type VARCHAR(80) NOT NULL,
    entity_id BIGINT NOT NULL,
    operation VARCHAR(40) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_domain_audit_entity
    ON domain_audit_log(entity_type, entity_id, recorded_at DESC);

-- ============================================================
-- DOMAIN FUNCTIONS
-- ============================================================

CREATE OR REPLACE FUNCTION calculate_order_total(
    p_order_id BIGINT
)
RETURNS NUMERIC(14, 2)
LANGUAGE SQL
STABLE
AS $$
    SELECT COALESCE(
        SUM(quantity * unit_price),
        0
    )::NUMERIC(14, 2)
    FROM order_items
    WHERE order_id = p_order_id;
$$;

CREATE OR REPLACE FUNCTION validate_order_currency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_currency CHAR(3);
    v_product_currency CHAR(3);
BEGIN
    SELECT currency
    INTO v_order_currency
    FROM orders
    WHERE order_id = NEW.order_id;

    SELECT currency
    INTO v_product_currency
    FROM products
    WHERE product_id = NEW.product_id;

    IF v_order_currency IS DISTINCT FROM v_product_currency THEN
        RAISE EXCEPTION
            'Order currency % differs from product currency %',
            v_order_currency,
            v_product_currency;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_order_currency
BEFORE INSERT OR UPDATE ON order_items
FOR EACH ROW
EXECUTE FUNCTION validate_order_currency();

-- ============================================================
-- STATE TRANSITION ENFORCEMENT
-- ============================================================

CREATE OR REPLACE FUNCTION enforce_order_state_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status <> NEW.status THEN

        IF NOT (
            (OLD.status = 'PENDING' AND
             NEW.status IN ('CONFIRMED', 'CANCELLED'))
        ) THEN
            RAISE EXCEPTION
                'Invalid order transition: % to %',
                OLD.status,
                NEW.status;
        END IF;

        NEW.version := OLD.version + 1;
    END IF;

    NEW.updated_at := NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_order_state_transition
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION enforce_order_state_transition();

-- ============================================================
-- AUDIT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION audit_order_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO domain_audit_log (
        entity_type,
        entity_id,
        operation,
        old_values,
        new_values
    )
    VALUES (
        'ORDER',
        NEW.order_id,
        TG_OP,
        CASE
            WHEN TG_OP = 'UPDATE'
            THEN to_jsonb(OLD)
            ELSE NULL
        END,
        to_jsonb(NEW)
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_order
AFTER INSERT OR UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION audit_order_changes();

-- ============================================================
-- INVENTORY RESERVATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE reserve_inventory(
    p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    item RECORD;
BEGIN
    FOR item IN
        SELECT product_id, quantity
        FROM order_items
        WHERE order_id = p_order_id
        ORDER BY product_id
    LOOP
        -- Lock rows to prevent concurrent over-reservation.
        UPDATE inventory
        SET
            available_quantity = available_quantity - item.quantity,
            reserved_quantity = reserved_quantity + item.quantity,
            updated_at = NOW()
        WHERE product_id = item.product_id
          AND available_quantity >= item.quantity;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Insufficient inventory for product %',
                item.product_id;
        END IF;

        INSERT INTO inventory_reservations (
            order_id,
            product_id,
            quantity
        )
        VALUES (
            p_order_id,
            item.product_id,
            item.quantity
        );
    END LOOP;
END;
$$;

-- ============================================================
-- RELEASE INVENTORY PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE release_inventory(
    p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    reservation RECORD;
BEGIN
    FOR reservation IN
        SELECT reservation_id, product_id, quantity
        FROM inventory_reservations
        WHERE order_id = p_order_id
          AND status = 'RESERVED'
        FOR UPDATE
    LOOP
        UPDATE inventory
        SET
            available_quantity =
                available_quantity + reservation.quantity,
            reserved_quantity =
                reserved_quantity - reservation.quantity,
            updated_at = NOW()
        WHERE product_id = reservation.product_id
          AND reserved_quantity >= reservation.quantity;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Inventory reservation consistency failure';
        END IF;

        UPDATE inventory_reservations
        SET
            status = 'RELEASED',
            updated_at = NOW()
        WHERE reservation_id = reservation.reservation_id;
    END LOOP;
END;
$$;

-- ============================================================
-- OUTBOX CREATION
-- ============================================================

CREATE OR REPLACE FUNCTION publish_order_event_to_outbox()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'CONFIRMED'
       AND OLD.status = 'PENDING' THEN

        INSERT INTO integration_outbox (
            aggregate_type,
            aggregate_id,
            event_type,
            payload
        )
        VALUES (
            'ORDER',
            NEW.order_id,
            'OrderConfirmed',
            jsonb_build_object(
                'order_id', NEW.order_id,
                'order_reference', NEW.order_reference,
                'customer_id', NEW.customer_id,
                'currency', NEW.currency,
                'occurred_at', NOW()
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_order_outbox
AFTER UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION publish_order_event_to_outbox();

-- ============================================================
-- REPORTING VIEWS
-- ============================================================

CREATE OR REPLACE VIEW order_summary AS
SELECT
    o.order_id,
    o.order_reference,
    c.external_reference AS customer_reference,
    c.customer_name,
    o.status,
    o.currency,
    COUNT(oi.order_item_id) AS line_count,
    COALESCE(
        SUM(oi.quantity),
        0
    ) AS total_units,
    COALESCE(
        SUM(oi.quantity * oi.unit_price),
        0
    )::NUMERIC(14, 2) AS order_total,
    o.created_at
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    c.external_reference,
    c.customer_name;

CREATE OR REPLACE VIEW architecture_adapter_matrix AS
SELECT
    p.port_name,
    p.direction,
    p.contract_version,
    a.adapter_name,
    a.adapter_kind,
    a.implementation_version,
    b.priority,
    b.active AS binding_active
FROM architecture_ports p
LEFT JOIN adapter_port_bindings b
    ON b.port_id = p.port_id
LEFT JOIN adapters a
    ON a.adapter_id = b.adapter_id
ORDER BY
    p.port_name,
    b.priority;

-- ============================================================
-- ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION order_is_mergeable(
    p_order_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_status order_status;
    v_payment_exists BOOLEAN;
    v_reservations_valid BOOLEAN;
BEGIN
    SELECT status
    INTO v_status
    FROM orders
    WHERE order_id = p_order_id;

    IF NOT FOUND OR v_status <> 'CONFIRMED' THEN
        RETURN FALSE;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM payments
        WHERE order_id = p_order_id
          AND status = 'CHARGED'
    )
    INTO v_payment_exists;

    SELECT NOT EXISTS (
        SELECT 1
        FROM inventory_reservations
        WHERE order_id = p_order_id
          AND status <> 'RESERVED'
    )
    AND EXISTS (
        SELECT 1
        FROM inventory_reservations
        WHERE order_id = p_order_id
    )
    INTO v_reservations_valid;

    RETURN v_payment_exists AND v_reservations_valid;
END;
$$;

-- ============================================================
-- SAMPLE DATA
-- ============================================================

INSERT INTO customers (
    external_reference,
    customer_name
)
VALUES
    ('CUST-5001', 'Enterprise Technology Services'),
    ('CUST-5002', 'Research Infrastructure Unit');

INSERT INTO products (
    sku,
    product_name,
    unit_price
)
VALUES
    ('SERVER-500', 'Application Server', 85000.00),
    ('SWITCH-500', 'Network Switch', 25000.00),
    ('CABLE-500', 'Network Cable', 500.00);

INSERT INTO inventory (
    product_id,
    available_quantity,
    reserved_quantity
)
SELECT
    product_id,
    CASE sku
        WHEN 'SERVER-500' THEN 20
        WHEN 'SWITCH-500' THEN 30
        WHEN 'CABLE-500' THEN 200
    END,
    0
FROM products;

-- Port definitions.

INSERT INTO architecture_ports (
    port_name,
    direction,
    description,
    contract_version
)
VALUES
    (
        'PlaceOrderPort',
        'PRIMARY',
        'Accepts order commands from external delivery adapters',
        1
    ),
    (
        'OrderRepositoryPort',
        'SECONDARY',
        'Persists and retrieves order aggregates',
        1
    ),
    (
        'InventoryPort',
        'SECONDARY',
        'Reserves and releases inventory',
        1
    ),
    (
        'PaymentPort',
        'SECONDARY',
        'Charges and refunds customer payments',
        1
    ),
    (
        'EventPublisherPort',
        'SECONDARY',
        'Publishes integration events',
        1
    );

INSERT INTO adapters (
    adapter_name,
    adapter_kind,
    description,
    implementation_version
)
VALUES
    (
        'REST API Adapter',
        'HTTP',
        'External HTTP delivery mechanism',
        '1.0.0'
    ),
    (
        'Console Adapter',
        'CLI',
        'Administrative command-line adapter',
        '1.0.0'
    ),
    (
        'PostgreSQL Repository',
        'DATABASE',
        'Relational persistence adapter',
        '1.0.0'
    ),
    (
        'Warehouse Adapter',
        'INVENTORY',
        'Inventory service adapter',
        '1.0.0'
    ),
    (
        'Payment Gateway Adapter',
        'PAYMENT',
        'Payment integration adapter',
        '1.0.0'
    ),
    (
        'Outbox Publisher',
        'EVENT_BUS',
        'Transactional event publisher',
        '1.0.0'
    );

INSERT INTO adapter_port_bindings (
    port_id,
    adapter_id,
    priority
)
SELECT
    p.port_id,
    a.adapter_id,
    1
FROM architecture_ports p
CROSS JOIN adapters a
WHERE
    (p.port_name = 'PlaceOrderPort'
        AND a.adapter_kind IN ('HTTP', 'CLI'))
    OR
    (p.port_name = 'OrderRepositoryPort'
        AND a.adapter_kind = 'DATABASE')
    OR
    (p.port_name = 'InventoryPort'
        AND a.adapter_kind = 'INVENTORY')
    OR
    (p.port_name = 'PaymentPort'
        AND a.adapter_kind = 'PAYMENT')
    OR
    (p.port_name = 'EventPublisherPort'
        AND a.adapter_kind = 'EVENT_BUS');

INSERT INTO use_cases (
    use_case_name,
    description
)
VALUES (
    'PlaceOrder',
    'Validates, reserves inventory, charges payment, persists and publishes an order'
);

INSERT INTO use_case_port_dependencies (
    use_case_id,
    port_id,
    required
)
SELECT
    u.use_case_id,
    p.port_id,
    TRUE
FROM use_cases u
CROSS JOIN architecture_ports p
WHERE u.use_case_name = 'PlaceOrder'
  AND p.port_name IN (
      'OrderRepositoryPort',
      'InventoryPort',
      'PaymentPort',
      'EventPublisherPort'
  );

-- ============================================================
-- EXECUTABLE WORKFLOW
-- ============================================================

DO $$
DECLARE
    v_customer BIGINT;
    v_server BIGINT;
    v_cable BIGINT;
    v_order BIGINT;
    v_total NUMERIC(14, 2);
    v_payment_id BIGINT;
BEGIN
    SELECT customer_id
    INTO v_customer
    FROM customers
    WHERE external_reference = 'CUST-5001';

    SELECT product_id
    INTO v_server
    FROM products
    WHERE sku = 'SERVER-500';

    SELECT product_id
    INTO v_cable
    FROM products
    WHERE sku = 'CABLE-500';

    INSERT INTO orders (
        customer_id,
        currency
    )
    VALUES (
        v_customer,
        'INR'
    )
    RETURNING order_id INTO v_order;

    INSERT INTO order_items (
        order_id,
        product_id,
        quantity,
        unit_price
    )
    SELECT
        v_order,
        product_id,
        1,
        unit_price
    FROM products
    WHERE product_id = v_server;

    INSERT INTO order_items (
        order_id,
        product_id,
        quantity,
        unit_price
    )
    SELECT
        v_order,
        product_id,
        5,
        unit_price
    FROM products
    WHERE product_id = v_cable;

    v_total := calculate_order_total(v_order);

    -- Record application execution.
    INSERT INTO use_case_executions (
        use_case_id,
        execution_status
    )
    SELECT
        use_case_id,
        'STARTED'
    FROM use_cases
    WHERE use_case_name = 'PlaceOrder';

    -- Inventory changes are transactional.
    CALL reserve_inventory(v_order);

    INSERT INTO payments (
        order_id,
        external_payment_reference,
        amount,
        currency,
        status,
        idempotency_key
    )
    VALUES (
        v_order,
        'PAYMENT-EXT-5001',
        v_total,
        'INR',
        'CHARGED',
        gen_random_uuid()
    )
    RETURNING payment_id INTO v_payment_id;

    UPDATE orders
    SET status = 'CONFIRMED'
    WHERE order_id = v_order;

    UPDATE inventory_reservations
    SET
        status = 'CONSUMED',
        updated_at = NOW()
    WHERE order_id = v_order
      AND status = 'RESERVED';

    -- The outbox event is inserted by the order trigger.
    UPDATE use_case_executions
    SET
        execution_status = 'SUCCEEDED',
        completed_at = NOW(),
        order_id = v_order
    WHERE execution_id = (
        SELECT MAX(execution_id)
        FROM use_case_executions
    );

    RAISE NOTICE
        'Order % created with total INR % and payment %',
        v_order,
        v_total,
        v_payment_id;
END;
$$;

-- ============================================================
-- FAILURE SCENARIO
-- ============================================================

-- A deliberately invalid order transition must be rejected.
DO $$
DECLARE
    v_order BIGINT;
BEGIN
    SELECT order_id
    INTO v_order
    FROM orders
    ORDER BY order_id
    LIMIT 1;

    BEGIN
        UPDATE orders
        SET status = 'CANCELLED'
        WHERE order_id = v_order;

        RAISE EXCEPTION
            'Expected invalid state transition was not rejected';

    EXCEPTION
        WHEN raise_exception THEN
            -- The domain trigger correctly rejects the transition.
            RAISE NOTICE 'Invalid order transition rejected';
    END;
END;
$$;

-- ============================================================
-- RETRIEVAL QUERIES
-- ============================================================

SELECT *
FROM order_summary
ORDER BY created_at DESC;

SELECT
    p.port_name,
    p.direction,
    a.adapter_name,
    a.adapter_kind
FROM architecture_ports p
LEFT JOIN adapter_port_bindings b
    ON b.port_id = p.port_id
LEFT JOIN adapters a
    ON a.adapter_id = b.adapter_id
WHERE p.active = TRUE
ORDER BY p.port_name;

-- ============================================================
-- VALIDATION QUERIES
-- ============================================================

-- Ports without an active adapter.
SELECT
    p.port_name,
    p.direction
FROM architecture_ports p
LEFT JOIN adapter_port_bindings b
    ON b.port_id = p.port_id
   AND b.active = TRUE
LEFT JOIN adapters a
    ON a.adapter_id = b.adapter_id
   AND a.active = TRUE
WHERE p.active = TRUE
GROUP BY p.port_id, p.port_name, p.direction
HAVING COUNT(a.adapter_id) = 0;

-- Required dependencies without active bindings.
SELECT
    u.use_case_name,
    p.port_name
FROM use_case_port_dependencies d
JOIN use_cases u
    ON u.use_case_id = d.use_case_id
JOIN architecture_ports p
    ON p.port_id = d.port_id
WHERE d.required = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM adapter_port_bindings b
      JOIN adapters a
          ON a.adapter_id = b.adapter_id
      WHERE b.port_id = p.port_id
        AND b.active = TRUE
        AND a.active = TRUE
  );

-- ============================================================
-- AGGREGATION AND EVALUATION
-- ============================================================

SELECT
    status,
    COUNT(*) AS order_count,
    SUM(order_total) AS total_value
FROM order_summary
GROUP BY status
ORDER BY status;

SELECT
    a.adapter_kind,
    COUNT(*) AS execution_count,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'SUCCEEDED'
    ) AS successful_count,
    COUNT(*) FILTER (
        WHERE e.execution_status = 'FAILED'
    ) AS failed_count
FROM use_case_executions e
LEFT JOIN adapters a
    ON a.adapter_id = e.adapter_id
GROUP BY a.adapter_kind;

-- ============================================================
-- ELIGIBILITY DETERMINATION
-- ============================================================

SELECT
    o.order_id,
    o.status,
    order_is_mergeable(o.order_id) AS workflow_eligible
FROM orders o
ORDER BY o.order_id;

-- ============================================================
-- CTE REPORTING
-- ============================================================

WITH port_coverage AS (
    SELECT
        p.port_id,
        p.port_name,
        COUNT(b.binding_id) FILTER (
            WHERE b.active = TRUE AND a.active = TRUE
        ) AS active_adapters
    FROM architecture_ports p
    LEFT JOIN adapter_port_bindings b
        ON b.port_id = p.port_id
    LEFT JOIN adapters a
        ON a.adapter_id = b.adapter_id
    GROUP BY p.port_id, p.port_name
)
SELECT
    port_name,
    active_adapters,
    CASE
        WHEN active_adapters = 0 THEN 'UNBOUND'
        WHEN active_adapters = 1 THEN 'SINGLE ADAPTER'
        ELSE 'MULTIPLE ADAPTERS'
    END AS coverage_status
FROM port_coverage
ORDER BY port_name;

-- ============================================================
-- OUTBOX WORKFLOW
-- ============================================================

-- Claim unpublished events using row-level locking.
-- In a production publisher, process and acknowledge events
-- in separate controlled transactions.

SELECT
    event_id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    created_at
FROM integration_outbox
WHERE published = FALSE
ORDER BY created_at
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- ============================================================
-- PERFORMANCE AND OPERATIONAL QUERIES
-- ============================================================

CREATE INDEX idx_orders_customer_created
    ON orders(customer_id, created_at DESC);

CREATE INDEX idx_order_items_order
    ON order_items(order_id);

CREATE INDEX idx_payments_status_created
    ON payments(status, created_at DESC);

CREATE INDEX idx_execution_use_case
    ON use_case_executions(use_case_id, started_at DESC);

-- Inspect expensive query plans during operational tuning:
EXPLAIN
SELECT
    order_id,
    SUM(quantity * unit_price)
FROM order_items
GROUP BY order_id;

-- ============================================================
-- TRANSACTIONAL CONSISTENCY NOTES
-- ============================================================

-- PostgreSQL transactions provide atomicity for database changes.
-- They cannot atomically commit an external payment gateway call.
-- A real application must use:
--   1. Idempotency keys.
--   2. Durable payment operation records.
--   3. Compensation or a saga.
--   4. Transactional outbox publishing.
--   5. Retry-safe consumers.
--   6. Authorization and restricted database roles.
--
-- Database constraints protect data integrity, not the complete
-- application-level port contract.

COMMIT;
