-- ================================================================
-- MONOLITH ARCHITECTURE
-- PostgreSQL relational implementation
--
-- Demonstrates:
-- 1. One application with internally separated business modules.
-- 2. Shared relational database.
-- 3. Transactional order processing.
-- 4. Inventory and payment workflows.
-- 5. Application deployment and scaling records.
-- 6. Operational metrics.
--
-- PostgreSQL 14+
-- ================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS monolith;

SET search_path TO monolith, public;

-- ------------------------------------------------
-- ENUM TYPES
-- ------------------------------------------------

CREATE TYPE module_name AS ENUM (
    'USERS',
    'CATALOG',
    'INVENTORY',
    'ORDERS',
    'PAYMENTS',
    'REPORTING'
);

CREATE TYPE order_status AS ENUM (
    'CREATED',
    'PAID',
    'FAILED',
    'CANCELLED'
);

CREATE TYPE payment_status AS ENUM (
    'PENDING',
    'COMPLETED',
    'FAILED',
    'REFUNDED'
);

CREATE TYPE deployment_status AS ENUM (
    'RUNNING',
    'STOPPED',
    'DEGRADED',
    'FAILED'
);

CREATE TYPE scaling_type AS ENUM (
    'VERTICAL',
    'HORIZONTAL'
);

-- ------------------------------------------------
-- APPLICATION AND MODULE REGISTRY
-- ------------------------------------------------

CREATE TABLE applications (
    application_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_name VARCHAR(120) NOT NULL UNIQUE,
    architecture VARCHAR(30) NOT NULL DEFAULT 'MONOLITH',
    version VARCHAR(30) NOT NULL,
    environment VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_architecture
        CHECK (architecture IN ('MONOLITH')),

    CONSTRAINT valid_environment
        CHECK (environment IN ('DEVELOPMENT', 'STAGING', 'PRODUCTION'))
);

CREATE TABLE application_modules (
    module_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id) ON DELETE CASCADE,
    module module_name NOT NULL,
    description TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT unique_application_module
        UNIQUE (application_id, module)
);

-- ------------------------------------------------
-- APPLICATION INSTANCES
-- ------------------------------------------------

CREATE TABLE application_instances (
    instance_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    instance_name VARCHAR(100) NOT NULL UNIQUE,
    deployment_state deployment_status NOT NULL DEFAULT 'RUNNING',
    cpu_cores INTEGER NOT NULL DEFAULT 2,
    memory_mb INTEGER NOT NULL DEFAULT 2048,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_health_check TIMESTAMPTZ,

    CONSTRAINT valid_cpu CHECK (cpu_cores > 0),
    CONSTRAINT valid_memory CHECK (memory_mb >= 256)
);

-- ------------------------------------------------
-- USERS
-- ------------------------------------------------

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_email
        CHECK (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')
);

-- ------------------------------------------------
-- PRODUCT CATALOG AND INVENTORY
-- ------------------------------------------------

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT positive_or_zero_price CHECK (unit_price >= 0)
);

CREATE TABLE inventory (
    inventory_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL UNIQUE
        REFERENCES products(product_id),
    available_quantity INTEGER NOT NULL DEFAULT 0,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT nonnegative_available
        CHECK (available_quantity >= 0),

    CONSTRAINT nonnegative_reserved
        CHECK (reserved_quantity >= 0)
);

-- ------------------------------------------------
-- ORDERS
-- ------------------------------------------------

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    order_status order_status NOT NULL DEFAULT 'CREATED',
    total_amount NUMERIC(14, 2) NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT nonnegative_order_amount CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,

    CONSTRAINT positive_order_quantity CHECK (quantity > 0),
    CONSTRAINT nonnegative_item_price CHECK (unit_price >= 0),
    CONSTRAINT unique_order_product UNIQUE (order_id, product_id)
);

-- ------------------------------------------------
-- PAYMENTS
-- ------------------------------------------------

CREATE TABLE payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE REFERENCES orders(order_id),
    payment_reference VARCHAR(120) NOT NULL UNIQUE,
    amount NUMERIC(14, 2) NOT NULL,
    payment_status payment_status NOT NULL DEFAULT 'PENDING',
    processed_at TIMESTAMPTZ,

    CONSTRAINT positive_payment_amount CHECK (amount > 0)
);

-- ------------------------------------------------
-- INTERNAL MODULE EVENTS
-- ------------------------------------------------

CREATE TABLE module_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    module module_name NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    aggregate_id BIGINT,
    event_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_event_payload
        CHECK (jsonb_typeof(event_payload) = 'object')
);

-- ------------------------------------------------
-- DEPLOYMENT AND SCALING
-- ------------------------------------------------

CREATE TABLE deployment_history (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    version VARCHAR(30) NOT NULL,
    deployment_status VARCHAR(30) NOT NULL,
    deployed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    deployment_notes TEXT,

    CONSTRAINT valid_deployment_status
        CHECK (
            deployment_status IN (
                'STARTED',
                'SUCCEEDED',
                'FAILED',
                'ROLLED_BACK'
            )
        ),

    CONSTRAINT valid_deployment_dates
        CHECK (completed_at IS NULL OR completed_at >= deployed_at)
);

CREATE TABLE scaling_events (
    scaling_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    scaling_mode scaling_type NOT NULL,
    previous_instances INTEGER NOT NULL,
    current_instances INTEGER NOT NULL,
    previous_cpu_cores INTEGER NOT NULL,
    current_cpu_cores INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_instance_counts
        CHECK (
            previous_instances > 0
            AND current_instances > 0
        ),

    CONSTRAINT valid_cpu_counts
        CHECK (
            previous_cpu_cores > 0
            AND current_cpu_cores > 0
        )
);

-- ------------------------------------------------
-- OPERATIONAL METRICS
-- ------------------------------------------------

CREATE TABLE application_metrics (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instance_id BIGINT NOT NULL
        REFERENCES application_instances(instance_id),
    cpu_percent NUMERIC(5, 2) NOT NULL,
    memory_percent NUMERIC(5, 2) NOT NULL,
    request_count BIGINT NOT NULL DEFAULT 0,
    error_count BIGINT NOT NULL DEFAULT 0,
    average_latency_ms NUMERIC(12, 3) NOT NULL DEFAULT 0,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_cpu_percent
        CHECK (cpu_percent BETWEEN 0 AND 100),

    CONSTRAINT valid_memory_percent
        CHECK (memory_percent BETWEEN 0 AND 100),

    CONSTRAINT valid_request_counts
        CHECK (
            request_count >= 0
            AND error_count >= 0
            AND error_count <= request_count
        ),

    CONSTRAINT valid_latency
        CHECK (average_latency_ms >= 0)
);

-- ------------------------------------------------
-- INDEXES
-- ------------------------------------------------

CREATE INDEX idx_orders_user_created
    ON orders(user_id, created_at DESC);

CREATE INDEX idx_orders_status_created
    ON orders(order_status, created_at DESC);

CREATE INDEX idx_order_items_product
    ON order_items(product_id);

CREATE INDEX idx_payments_status
    ON payments(payment_status);

CREATE INDEX idx_events_module_created
    ON module_events(module, created_at DESC);

CREATE INDEX idx_metrics_instance_recorded
    ON application_metrics(instance_id, recorded_at DESC);

CREATE INDEX idx_instances_application_state
    ON application_instances(application_id, deployment_state);

CREATE INDEX idx_products_active
    ON products(product_id) WHERE active = TRUE;

CREATE INDEX idx_event_payload
    ON module_events USING GIN(event_payload);

-- ------------------------------------------------
-- TRIGGER: UPDATE TIMESTAMPS
-- ------------------------------------------------

CREATE FUNCTION update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER orders_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER inventory_updated_at
BEFORE UPDATE ON inventory
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();

-- ------------------------------------------------
-- TRIGGER: PROTECT PAID ORDERS
-- ------------------------------------------------

CREATE FUNCTION protect_paid_order()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.order_status = 'PAID'
       AND NEW.order_status NOT IN ('PAID', 'CANCELLED') THEN
        RAISE EXCEPTION
            'A paid order cannot transition to %',
            NEW.order_status;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER enforce_paid_order_transition
BEFORE UPDATE OF order_status ON orders
FOR EACH ROW
EXECUTE FUNCTION protect_paid_order();

-- ------------------------------------------------
-- VIEWS
-- ------------------------------------------------

CREATE VIEW order_details AS
SELECT
    o.order_id,
    u.full_name,
    u.email,
    o.order_status,
    o.total_amount,
    COUNT(oi.order_item_id) AS item_count,
    o.created_at
FROM orders o
JOIN users u ON u.user_id = o.user_id
LEFT JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    u.full_name,
    u.email,
    o.order_status,
    o.total_amount,
    o.created_at;

CREATE VIEW application_health AS
SELECT
    a.application_name,
    i.instance_name,
    i.deployment_state,
    i.cpu_cores,
    i.memory_mb,
    m.cpu_percent,
    m.memory_percent,
    m.average_latency_ms,
    m.request_count,
    m.error_count,
    m.recorded_at
FROM application_instances i
JOIN applications a
    ON a.application_id = i.application_id
LEFT JOIN LATERAL (
    SELECT *
    FROM application_metrics am
    WHERE am.instance_id = i.instance_id
    ORDER BY am.recorded_at DESC
    LIMIT 1
) m ON TRUE;

-- ------------------------------------------------
-- FUNCTION: CALCULATE ORDER TOTAL
-- ------------------------------------------------

CREATE FUNCTION calculate_order_total(p_order_id BIGINT)
RETURNS NUMERIC(14, 2)
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        SUM(quantity * unit_price),
        0
    )::NUMERIC(14, 2)
    FROM order_items
    WHERE order_id = p_order_id;
$$;

-- ------------------------------------------------
-- FUNCTION: CHECK INVENTORY AVAILABILITY
-- ------------------------------------------------

CREATE FUNCTION has_sufficient_inventory(
    p_product_id BIGINT,
    p_quantity INTEGER
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM inventory
        WHERE product_id = p_product_id
          AND available_quantity >= p_quantity
          AND p_quantity > 0
    );
$$;

-- ------------------------------------------------
-- PROCEDURE: PROCESS ORDER
--
-- A database transaction ensures that stock reservation,
-- order creation, order items, and payment records commit
-- together or roll back together.
--
-- The caller should use a unique idempotency key for retries.
-- External payment providers require a separate outbox and
-- reconciliation workflow in a production deployment.
-- ------------------------------------------------

CREATE PROCEDURE process_order(
    IN p_user_id BIGINT,
    IN p_product_id BIGINT,
    IN p_quantity INTEGER,
    IN p_idempotency_key VARCHAR(100),
    IN p_payment_reference VARCHAR(120)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_product products%ROWTYPE;
    v_order_id BIGINT;
    v_total NUMERIC(14, 2);
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive';
    END IF;

    IF p_idempotency_key IS NULL
       OR LENGTH(TRIM(p_idempotency_key)) = 0 THEN
        RAISE EXCEPTION 'Idempotency key is required';
    END IF;

    IF p_payment_reference IS NULL
       OR LENGTH(TRIM(p_payment_reference)) = 0 THEN
        RAISE EXCEPTION 'Payment reference is required';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM users
        WHERE user_id = p_user_id
          AND active = TRUE
    ) THEN
        RAISE EXCEPTION 'Active user not found';
    END IF;

    -- Return the existing result for a repeated request.
    IF EXISTS (
        SELECT 1
        FROM orders
        WHERE idempotency_key = p_idempotency_key
    ) THEN
        RAISE NOTICE 'Order already processed for key %',
            p_idempotency_key;
        RETURN;
    END IF;

    SELECT *
    INTO v_product
    FROM products
    WHERE product_id = p_product_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active product not found';
    END IF;

    -- Lock the inventory row to prevent concurrent overselling.
    UPDATE inventory
    SET available_quantity = available_quantity - p_quantity,
        reserved_quantity = reserved_quantity + p_quantity
    WHERE product_id = p_product_id
      AND available_quantity >= p_quantity;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Insufficient inventory';
    END IF;

    v_total := v_product.unit_price * p_quantity;

    INSERT INTO orders (
        user_id,
        order_status,
        total_amount,
        idempotency_key
    )
    VALUES (
        p_user_id,
        'CREATED',
        v_total,
        p_idempotency_key
    )
    RETURNING order_id INTO v_order_id;

    INSERT INTO order_items (
        order_id,
        product_id,
        quantity,
        unit_price
    )
    VALUES (
        v_order_id,
        p_product_id,
        p_quantity,
        v_product.unit_price
    );

    INSERT INTO payments (
        order_id,
        payment_reference,
        amount,
        payment_status,
        processed_at
    )
    VALUES (
        v_order_id,
        p_payment_reference,
        v_total,
        'COMPLETED',
        CURRENT_TIMESTAMP
    );

    UPDATE inventory
    SET reserved_quantity = reserved_quantity - p_quantity
    WHERE product_id = p_product_id;

    UPDATE orders
    SET order_status = 'PAID'
    WHERE order_id = v_order_id;

    RAISE NOTICE 'Order % processed successfully', v_order_id;
END;
$$;

-- ------------------------------------------------
-- SAMPLE DATA
-- ------------------------------------------------

INSERT INTO applications (
    application_name,
    version,
    environment
)
VALUES (
    'Enterprise Business Platform',
    '2.4.0',
    'PRODUCTION'
);

INSERT INTO application_modules (
    application_id,
    module,
    description
)
SELECT
    application_id,
    module,
    description
FROM applications
CROSS JOIN (
    VALUES
        ('USERS'::module_name, 'User registration and access'),
        ('CATALOG'::module_name, 'Product catalog management'),
        ('INVENTORY'::module_name, 'Inventory reservation'),
        ('ORDERS'::module_name, 'Order lifecycle management'),
        ('PAYMENTS'::module_name, 'Payment processing'),
        ('REPORTING'::module_name, 'Operational and business reporting')
) AS modules(module, description)
WHERE application_name = 'Enterprise Business Platform';

INSERT INTO application_instances (
    application_id,
    instance_name,
    deployment_state,
    cpu_cores,
    memory_mb,
    last_health_check
)
SELECT
    application_id,
    'monolith-production-01',
    'RUNNING',
    8,
    16384,
    CURRENT_TIMESTAMP
FROM applications
WHERE application_name = 'Enterprise Business Platform';

INSERT INTO users (full_name, email)
VALUES
    ('Aarav Sharma', 'aarav@example.com'),
    ('Priya Verma', 'priya@example.com'),
    ('Rahul Singh', 'rahul@example.com');

INSERT INTO products (sku, product_name, unit_price)
VALUES
    ('DB-SERVER-001', 'Enterprise Database Server', 5000.00),
    ('CACHE-NODE-001', 'Cache Infrastructure Node', 2500.00),
    ('STORAGE-001', 'Enterprise Storage Unit', 7500.00);

INSERT INTO inventory (
    product_id,
    available_quantity,
    reserved_quantity
)
SELECT product_id, 20, 0
FROM products;

INSERT INTO module_events (
    application_id,
    module,
    event_type,
    event_payload
)
SELECT
    application_id,
    'USERS',
    'USER_REGISTRATION',
    '{"source":"web_application","result":"success"}'::JSONB
FROM applications
WHERE application_name = 'Enterprise Business Platform';

INSERT INTO deployment_history (
    application_id,
    version,
    deployment_status,
    completed_at,
    deployment_notes
)
SELECT
    application_id,
    '2.4.0',
    'SUCCEEDED',
    CURRENT_TIMESTAMP,
    'Production deployment completed'
FROM applications
WHERE application_name = 'Enterprise Business Platform';

INSERT INTO application_metrics (
    instance_id,
    cpu_percent,
    memory_percent,
    request_count,
    error_count,
    average_latency_ms
)
SELECT
    instance_id,
    58.5,
    67.2,
    12000,
    42,
    135.500
FROM application_instances
WHERE instance_name = 'monolith-production-01';

-- ------------------------------------------------
-- PROCESS VALID TRANSACTIONS
-- ------------------------------------------------

CALL process_order(
    1,
    1,
    2,
    'ORDER-REQUEST-1001',
    'PAYMENT-REFERENCE-1001'
);

CALL process_order(
    2,
    2,
    1,
    'ORDER-REQUEST-1002',
    'PAYMENT-REFERENCE-1002'
);

-- ------------------------------------------------
-- INVALID CASE DEMONSTRATION
-- ------------------------------------------------

DO $$
BEGIN
    BEGIN
        CALL process_order(
            1,
            1,
            1000,
            'ORDER-REQUEST-INVALID',
            'PAYMENT-REFERENCE-INVALID'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected transaction failure: %', SQLERRM;
    END;
END;
$$;

-- ------------------------------------------------
-- QUERY 1: APPLICATION MODULE RETRIEVAL
-- ------------------------------------------------

SELECT
    a.application_name,
    a.version,
    am.module,
    am.enabled
FROM applications a
JOIN application_modules am
    ON am.application_id = a.application_id
ORDER BY am.module;

-- ------------------------------------------------
-- QUERY 2: ORDER RETRIEVAL
-- ------------------------------------------------

SELECT *
FROM order_details
ORDER BY created_at DESC;

-- ------------------------------------------------
-- QUERY 3: INVENTORY VALIDATION
-- ------------------------------------------------

SELECT
    p.product_name,
    i.available_quantity,
    i.reserved_quantity,
    has_sufficient_inventory(p.product_id, 5) AS can_reserve_five
FROM products p
JOIN inventory i
    ON i.product_id = p.product_id;

-- ------------------------------------------------
-- QUERY 4: BUSINESS AGGREGATION
-- ------------------------------------------------

SELECT
    order_status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_value,
    AVG(total_amount) AS average_order_value
FROM orders
GROUP BY order_status
ORDER BY order_status;

-- ------------------------------------------------
-- QUERY 5: MODULE EVENT REPORT
-- ------------------------------------------------

SELECT
    module,
    event_type,
    COUNT(*) AS event_count,
    MAX(created_at) AS latest_event
FROM module_events
GROUP BY module, event_type
ORDER BY module;

-- ------------------------------------------------
-- QUERY 6: APPLICATION HEALTH REPORT
-- ------------------------------------------------

SELECT
    application_name,
    instance_name,
    deployment_state,
    cpu_percent,
    memory_percent,
    average_latency_ms,
    request_count,
    error_count,
    ROUND(
        100.0 * error_count / NULLIF(request_count, 0),
        2
    ) AS error_percentage
FROM application_health;

-- ------------------------------------------------
-- QUERY 7: SCALING ELIGIBILITY
--
-- Database saturation must be evaluated separately.
-- Adding application instances does not resolve a saturated
-- shared database.
-- ------------------------------------------------

WITH latest_metrics AS (
    SELECT DISTINCT ON (instance_id)
        instance_id,
        cpu_percent,
        memory_percent,
        average_latency_ms
    FROM application_metrics
    ORDER BY instance_id, recorded_at DESC
),
assessment AS (
    SELECT
        i.instance_name,
        m.cpu_percent,
        m.memory_percent,
        m.average_latency_ms,
        CASE
            WHEN m.memory_percent >= 85
                 OR m.cpu_percent >= 90
                THEN 'VERTICAL_SCALE_CANDIDATE'
            WHEN m.cpu_percent >= 70
                 OR m.average_latency_ms >= 500
                THEN 'HORIZONTAL_SCALE_CANDIDATE'
            ELSE 'CAPACITY_SUFFICIENT'
        END AS scaling_decision
    FROM application_instances i
    JOIN latest_metrics m
        ON m.instance_id = i.instance_id
)
SELECT *
FROM assessment;

-- ------------------------------------------------
-- QUERY 8: DEPLOYMENT HISTORY
-- ------------------------------------------------

SELECT
    a.application_name,
    d.version,
    d.deployment_status,
    d.deployed_at,
    d.completed_at
FROM deployment_history d
JOIN applications a
    ON a.application_id = d.application_id
ORDER BY d.deployed_at DESC;

-- ------------------------------------------------
-- QUERY 9: MODULE AVAILABILITY
-- ------------------------------------------------

SELECT
    module,
    COUNT(*) FILTER (WHERE enabled) AS enabled_modules,
    COUNT(*) FILTER (WHERE NOT enabled) AS disabled_modules
FROM application_modules
GROUP BY module;

-- ------------------------------------------------
-- QUERY 10: DATA INTEGRITY EVALUATION
-- ------------------------------------------------

SELECT
    o.order_id,
    o.total_amount AS recorded_total,
    calculate_order_total(o.order_id) AS calculated_total,
    o.total_amount = calculate_order_total(o.order_id)
        AS amount_consistent
FROM orders o;

-- ------------------------------------------------
-- QUERY 11: DATABASE CONTENTION INDICATOR
-- ------------------------------------------------

SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE order_status = 'CREATED'
    ) AS pending_orders,
    COUNT(*) FILTER (
        WHERE order_status = 'FAILED'
    ) AS failed_orders,
    COUNT(*) FILTER (
        WHERE order_status = 'PAID'
    ) AS paid_orders
FROM orders;

-- ------------------------------------------------
-- QUERY 12: APPLICATION INSTANCE CAPACITY
-- ------------------------------------------------

SELECT
    a.application_name,
    COUNT(i.instance_id) AS running_instances,
    SUM(i.cpu_cores) AS total_cpu_cores,
    SUM(i.memory_mb) AS total_memory_mb
FROM applications a
LEFT JOIN application_instances i
    ON i.application_id = a.application_id
   AND i.deployment_state = 'RUNNING'
GROUP BY a.application_id, a.application_name;

COMMIT;

-- ================================================================
-- OPERATIONAL NOTES
--
-- 1. The schema represents one logical application database.
-- 2. Tables are separated by business responsibility.
-- 3. Modules still participate in one deployment lifecycle.
-- 4. Multiple application instances can access the same database.
-- 5. Row-level inventory updates prevent concurrent overselling.
-- 6. Unique idempotency keys protect repeated order submissions.
-- 7. Database transactions cannot automatically roll back an
--    external payment provider operation.
-- 8. Production payment integrations should use an outbox,
--    idempotent provider requests, and reconciliation.
-- 9. Read replicas can improve read throughput but introduce
--    replication lag and consistency considerations.
-- 10. Shared database saturation can limit horizontal scaling.
-- ================================================================
