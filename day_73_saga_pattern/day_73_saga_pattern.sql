-- ============================================================
-- SAGA PATTERN: DISTRIBUTED TRANSACTION MANAGEMENT
-- PostgreSQL 15+
--
-- Demonstrates:
-- 1. Distributed business transaction modeling.
-- 2. Saga orchestration.
-- 3. Forward transaction execution.
-- 4. Compensating operations.
-- 5. Retry tracking.
-- 6. Idempotency.
-- 7. Transaction event auditing.
-- 8. Recovery and operational reporting.
--
-- Database transactions protect local database operations.
-- They do not create a global ACID transaction across services.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS saga_demo;

SET search_path TO saga_demo, public;

-- ------------------------------------------------------------
-- 1. ENUM TYPES
-- ------------------------------------------------------------

CREATE TYPE saga_status AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPENSATING',
    'COMPLETED',
    'COMPENSATED',
    'FAILED'
);

CREATE TYPE step_status AS ENUM (
    'PENDING',
    'COMPLETED',
    'COMPENSATING',
    'COMPENSATED',
    'FAILED'
);

CREATE TYPE operation_type AS ENUM (
    'FORWARD',
    'COMPENSATION'
);

-- ------------------------------------------------------------
-- 2. SERVICES
-- ------------------------------------------------------------

CREATE TABLE service_registry (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL UNIQUE,
    service_type VARCHAR(50) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO service_registry (service_name, service_type)
VALUES
    ('Inventory Service', 'INVENTORY'),
    ('Payment Service', 'PAYMENT'),
    ('Shipping Service', 'SHIPPING');

-- ------------------------------------------------------------
-- 3. BUSINESS ORDERS
-- ------------------------------------------------------------

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_order_id VARCHAR(100) NOT NULL UNIQUE,
    customer_id VARCHAR(100) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO orders (
    external_order_id,
    customer_id,
    amount,
    currency
)
VALUES
    ('ORDER-5001', 'CUSTOMER-101', 1500.00, 'INR'),
    ('ORDER-5002', 'CUSTOMER-102', 2400.00, 'INR'),
    ('ORDER-5003', 'CUSTOMER-103', 3200.00, 'INR');

-- ------------------------------------------------------------
-- 4. SAGA INSTANCES
-- ------------------------------------------------------------

CREATE TABLE sagas (
    saga_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    order_id BIGINT NOT NULL UNIQUE
        REFERENCES orders(order_id),

    status saga_status NOT NULL DEFAULT 'PENDING',

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    version BIGINT NOT NULL DEFAULT 0,

    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        completed_at IS NULL
        OR status IN ('COMPLETED', 'COMPENSATED', 'FAILED')
    )
);

CREATE INDEX idx_sagas_status
ON sagas(status, created_at);

-- ------------------------------------------------------------
-- 5. SAGA STEP DEFINITIONS
-- ------------------------------------------------------------

CREATE TABLE saga_steps (
    step_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    saga_id UUID NOT NULL
        REFERENCES sagas(saga_id),

    service_id BIGINT NOT NULL
        REFERENCES service_registry(service_id),

    step_name VARCHAR(120) NOT NULL,

    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),

    forward_operation VARCHAR(120) NOT NULL,

    compensation_operation VARCHAR(120) NOT NULL,

    status step_status NOT NULL DEFAULT 'PENDING',

    retry_count INTEGER NOT NULL DEFAULT 0
        CHECK (retry_count >= 0),

    max_retries INTEGER NOT NULL DEFAULT 3
        CHECK (max_retries BETWEEN 0 AND 10),

    last_error TEXT,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    UNIQUE (saga_id, sequence_number),
    UNIQUE (saga_id, step_name)
);

CREATE INDEX idx_saga_steps_execution
ON saga_steps(saga_id, sequence_number, status);

-- ------------------------------------------------------------
-- 6. IDEMPOTENCY RECORDS
-- ------------------------------------------------------------

CREATE TABLE idempotency_records (
    idempotency_key VARCHAR(200) PRIMARY KEY,

    saga_id UUID NOT NULL REFERENCES sagas(saga_id),

    step_id BIGINT NOT NULL REFERENCES saga_steps(step_id),

    operation operation_type NOT NULL,

    result JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (saga_id, step_id, operation)
);

-- ------------------------------------------------------------
-- 7. LOCAL SERVICE EFFECTS
-- ------------------------------------------------------------

CREATE TABLE inventory_reservations (
    reservation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_id BIGINT NOT NULL REFERENCES orders(order_id),

    quantity INTEGER NOT NULL CHECK (quantity > 0),

    reserved BOOLEAN NOT NULL DEFAULT TRUE,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (order_id)
);

CREATE TABLE payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_id BIGINT NOT NULL REFERENCES orders(order_id),

    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),

    payment_status VARCHAR(20) NOT NULL
        CHECK (payment_status IN ('CHARGED', 'REFUNDED')),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (order_id)
);

CREATE TABLE shipments (
    shipment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    order_id BIGINT NOT NULL REFERENCES orders(order_id),

    shipment_status VARCHAR(20) NOT NULL
        CHECK (
            shipment_status IN ('CREATED', 'CANCELLED')
        ),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (order_id)
);

-- ------------------------------------------------------------
-- 8. TRANSACTION OUTBOX
-- ------------------------------------------------------------

CREATE TABLE saga_outbox (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    saga_id UUID NOT NULL REFERENCES sagas(saga_id),

    event_type VARCHAR(100) NOT NULL,

    payload JSONB NOT NULL,

    published BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    published_at TIMESTAMPTZ
);

CREATE INDEX idx_saga_outbox_pending
ON saga_outbox(created_at)
WHERE published = FALSE;

-- ------------------------------------------------------------
-- 9. SAGA EVENT AUDIT
-- ------------------------------------------------------------

CREATE TABLE saga_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    saga_id UUID NOT NULL REFERENCES sagas(saga_id),

    step_id BIGINT REFERENCES saga_steps(step_id),

    event_type VARCHAR(100) NOT NULL,

    details JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_saga_events_history
ON saga_events(saga_id, created_at);

-- ------------------------------------------------------------
-- 10. EVENT LOGGING FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION record_saga_event(
    p_saga_id UUID,
    p_event_type VARCHAR,
    p_step_id BIGINT DEFAULT NULL,
    p_details JSONB DEFAULT '{}'::JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    INSERT INTO saga_events (
        saga_id,
        step_id,
        event_type,
        details
    )
    VALUES (
        p_saga_id,
        p_step_id,
        p_event_type,
        COALESCE(p_details, '{}'::JSONB)
    )
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;
END;
$$;

-- ------------------------------------------------------------
-- 11. CREATE SAGA AND ITS THREE STEPS
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION create_order_saga(
    p_external_order_id VARCHAR
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id BIGINT;
    v_saga_id UUID;

    v_inventory BIGINT;
    v_payment BIGINT;
    v_shipping BIGINT;
BEGIN
    SELECT order_id
    INTO v_order_id
    FROM orders
    WHERE external_order_id = p_external_order_id;

    IF v_order_id IS NULL THEN
        RAISE EXCEPTION 'Order not found: %',
            p_external_order_id;
    END IF;

    SELECT service_id INTO v_inventory
    FROM service_registry
    WHERE service_name = 'Inventory Service';

    SELECT service_id INTO v_payment
    FROM service_registry
    WHERE service_name = 'Payment Service';

    SELECT service_id INTO v_shipping
    FROM service_registry
    WHERE service_name = 'Shipping Service';

    IF v_inventory IS NULL
       OR v_payment IS NULL
       OR v_shipping IS NULL THEN
        RAISE EXCEPTION 'Required service registration missing';
    END IF;

    INSERT INTO sagas(order_id)
    VALUES (v_order_id)
    RETURNING saga_id INTO v_saga_id;

    INSERT INTO saga_steps (
        saga_id,
        service_id,
        step_name,
        sequence_number,
        forward_operation,
        compensation_operation
    )
    VALUES
    (
        v_saga_id,
        v_inventory,
        'Reserve Inventory',
        1,
        'RESERVE_INVENTORY',
        'RELEASE_INVENTORY'
    ),
    (
        v_saga_id,
        v_payment,
        'Charge Payment',
        2,
        'CHARGE_PAYMENT',
        'REFUND_PAYMENT'
    ),
    (
        v_saga_id,
        v_shipping,
        'Create Shipment',
        3,
        'CREATE_SHIPMENT',
        'CANCEL_SHIPMENT'
    );

    PERFORM record_saga_event(
        v_saga_id,
        'SAGA_CREATED'
    );

    RETURN v_saga_id;
END;
$$;

-- ------------------------------------------------------------
-- 12. EXECUTE ONE FORWARD STEP
--
-- Each invocation performs one local database transaction.
-- The idempotency key prevents duplicate local effects.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION execute_saga_step(
    p_saga_id UUID,
    p_step_name VARCHAR,
    p_should_fail BOOLEAN DEFAULT FALSE
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_step saga_steps%ROWTYPE;
    v_order orders%ROWTYPE;
    v_key VARCHAR(200);
BEGIN
    SELECT *
    INTO v_step
    FROM saga_steps
    WHERE saga_id = p_saga_id
      AND step_name = p_step_name
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Saga step not found: %', p_step_name;
    END IF;

    IF v_step.status = 'COMPLETED' THEN
        RETURN 'ALREADY_COMPLETED';
    END IF;

    IF v_step.status <> 'PENDING'
       AND v_step.status <> 'FAILED' THEN
        RAISE EXCEPTION 'Invalid step state: %', v_step.status;
    END IF;

    IF v_step.retry_count >= v_step.max_retries + 1 THEN
        RAISE EXCEPTION 'Retry limit reached for %', p_step_name;
    END IF;

    SELECT o.*
    INTO v_order
    FROM orders o
    JOIN sagas s ON s.order_id = o.order_id
    WHERE s.saga_id = p_saga_id;

    UPDATE sagas
    SET status = 'RUNNING',
        started_at = COALESCE(started_at, NOW()),
        version = version + 1
    WHERE saga_id = p_saga_id
      AND status IN ('PENDING', 'RUNNING');

    UPDATE saga_steps
    SET retry_count = retry_count + 1,
        started_at = COALESCE(started_at, NOW()),
        last_error = NULL
    WHERE step_id = v_step.step_id;

    IF p_should_fail THEN
        UPDATE saga_steps
        SET status = 'FAILED',
            last_error = 'Simulated service failure'
        WHERE step_id = v_step.step_id;

        PERFORM record_saga_event(
            p_saga_id,
            'STEP_FAILED',
            v_step.step_id,
            jsonb_build_object(
                'step', p_step_name,
                'reason', 'Simulated service failure'
            )
        );

        RETURN 'FAILED';
    END IF;

    v_key := p_saga_id::TEXT
        || ':'
        || v_step.step_id::TEXT
        || ':FORWARD';

    IF EXISTS (
        SELECT 1
        FROM idempotency_records
        WHERE idempotency_key = v_key
    ) THEN
        RETURN 'ALREADY_PROCESSED';
    END IF;

    CASE v_step.forward_operation

        WHEN 'RESERVE_INVENTORY' THEN

            INSERT INTO inventory_reservations (
                order_id,
                quantity,
                reserved
            )
            VALUES (
                v_order.order_id,
                1,
                TRUE
            )
            ON CONFLICT (order_id)
            DO UPDATE SET
                reserved = TRUE,
                updated_at = NOW();

        WHEN 'CHARGE_PAYMENT' THEN

            INSERT INTO payments (
                order_id,
                amount,
                payment_status
            )
            VALUES (
                v_order.order_id,
                v_order.amount,
                'CHARGED'
            )
            ON CONFLICT (order_id)
            DO UPDATE SET
                payment_status = 'CHARGED',
                updated_at = NOW()
            WHERE payments.payment_status = 'REFUNDED';

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Payment operation rejected';
            END IF;

        WHEN 'CREATE_SHIPMENT' THEN

            INSERT INTO shipments (
                order_id,
                shipment_status
            )
            VALUES (
                v_order.order_id,
                'CREATED'
            )
            ON CONFLICT (order_id)
            DO UPDATE SET
                shipment_status = 'CREATED',
                updated_at = NOW()
            WHERE shipments.shipment_status = 'CANCELLED';

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Shipment operation rejected';
            END IF;

        ELSE
            RAISE EXCEPTION 'Unsupported operation: %',
                v_step.forward_operation;

    END CASE;

    INSERT INTO idempotency_records (
        idempotency_key,
        saga_id,
        step_id,
        operation,
        result
    )
    VALUES (
        v_key,
        p_saga_id,
        v_step.step_id,
        'FORWARD',
        jsonb_build_object('result', 'SUCCESS')
    );

    UPDATE saga_steps
    SET status = 'COMPLETED',
        completed_at = NOW()
    WHERE step_id = v_step.step_id;

    PERFORM record_saga_event(
        p_saga_id,
        'STEP_COMPLETED',
        v_step.step_id,
        jsonb_build_object('step', p_step_name)
    );

    INSERT INTO saga_outbox (
        saga_id,
        event_type,
        payload
    )
    VALUES (
        p_saga_id,
        'SAGA_STEP_COMPLETED',
        jsonb_build_object(
            'step', p_step_name,
            'order_id', v_order.external_order_id
        )
    );

    RETURN 'COMPLETED';
END;
$$;

-- ------------------------------------------------------------
-- 13. COMPLETE OR COMPENSATE THE SAGA
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE finalize_saga(
    p_saga_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_status saga_status;
    v_total INTEGER;
    v_completed INTEGER;
    v_failed INTEGER;
BEGIN
    SELECT status
    INTO v_status
    FROM sagas
    WHERE saga_id = p_saga_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Saga does not exist';
    END IF;

    SELECT
        COUNT(*),
        COUNT(*) FILTER (WHERE status = 'COMPLETED'),
        COUNT(*) FILTER (WHERE status = 'FAILED')
    INTO v_total, v_completed, v_failed
    FROM saga_steps
    WHERE saga_id = p_saga_id;

    IF v_failed > 0 THEN
        UPDATE sagas
        SET status = 'COMPENSATING',
            failure_reason = 'One or more steps failed',
            version = version + 1
        WHERE saga_id = p_saga_id;

        PERFORM record_saga_event(
            p_saga_id,
            'COMPENSATION_REQUIRED'
        );

        RETURN;
    END IF;

    IF v_completed = v_total AND v_total > 0 THEN
        UPDATE sagas
        SET status = 'COMPLETED',
            completed_at = NOW(),
            version = version + 1
        WHERE saga_id = p_saga_id;

        PERFORM record_saga_event(
            p_saga_id,
            'SAGA_COMPLETED'
        );
    END IF;
END;
$$;

-- ------------------------------------------------------------
-- 14. EXECUTE COMPENSATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION compensate_saga_step(
    p_saga_id UUID,
    p_step_name VARCHAR
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_step saga_steps%ROWTYPE;
    v_order_id BIGINT;
    v_key VARCHAR(200);
BEGIN
    SELECT *
    INTO v_step
    FROM saga_steps
    WHERE saga_id = p_saga_id
      AND step_name = p_step_name
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Step not found';
    END IF;

    IF v_step.status = 'COMPENSATED' THEN
        RETURN 'ALREADY_COMPENSATED';
    END IF;

    IF v_step.status <> 'COMPLETED' THEN
        RETURN 'NOT_ELIGIBLE_FOR_COMPENSATION';
    END IF;

    SELECT order_id
    INTO v_order_id
    FROM sagas
    WHERE saga_id = p_saga_id;

    v_key := p_saga_id::TEXT
        || ':'
        || v_step.step_id::TEXT
        || ':COMPENSATION';

    IF EXISTS (
        SELECT 1
        FROM idempotency_records
        WHERE idempotency_key = v_key
    ) THEN
        RETURN 'ALREADY_PROCESSED';
    END IF;

    CASE v_step.compensation_operation

        WHEN 'RELEASE_INVENTORY' THEN
            UPDATE inventory_reservations
            SET reserved = FALSE,
                updated_at = NOW()
            WHERE order_id = v_order_id;

        WHEN 'REFUND_PAYMENT' THEN
            UPDATE payments
            SET payment_status = 'REFUNDED',
                updated_at = NOW()
            WHERE order_id = v_order_id
              AND payment_status = 'CHARGED';

        WHEN 'CANCEL_SHIPMENT' THEN
            UPDATE shipments
            SET shipment_status = 'CANCELLED',
                updated_at = NOW()
            WHERE order_id = v_order_id
              AND shipment_status = 'CREATED';

        ELSE
            RAISE EXCEPTION 'Unsupported compensation: %',
                v_step.compensation_operation;

    END CASE;

    INSERT INTO idempotency_records (
        idempotency_key,
        saga_id,
        step_id,
        operation,
        result
    )
    VALUES (
        v_key,
        p_saga_id,
        v_step.step_id,
        'COMPENSATION',
        jsonb_build_object('result', 'SUCCESS')
    );

    UPDATE saga_steps
    SET status = 'COMPENSATED'
    WHERE step_id = v_step.step_id;

    PERFORM record_saga_event(
        p_saga_id,
        'STEP_COMPENSATED',
        v_step.step_id
    );

    RETURN 'COMPENSATED';
END;
$$;

-- ------------------------------------------------------------
-- 15. FINALIZE COMPENSATION
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE finalize_compensation(
    p_saga_id UUID
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_remaining
    FROM saga_steps
    WHERE saga_id = p_saga_id
      AND status = 'COMPLETED';

    IF v_remaining = 0 THEN
        UPDATE sagas
        SET status = 'COMPENSATED',
            completed_at = NOW(),
            version = version + 1
        WHERE saga_id = p_saga_id
          AND status = 'COMPENSATING';

        PERFORM record_saga_event(
            p_saga_id,
            'SAGA_COMPENSATED'
        );
    ELSE
        UPDATE sagas
        SET status = 'FAILED',
            failure_reason =
                'Compensation incomplete; manual recovery required',
            version = version + 1
        WHERE saga_id = p_saga_id;

        PERFORM record_saga_event(
            p_saga_id,
            'MANUAL_RECOVERY_REQUIRED',
            NULL,
            jsonb_build_object(
                'uncompensated_steps',
                v_remaining
            )
        );
    END IF;
END;
$$;

-- ------------------------------------------------------------
-- 16. REPORTING VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW saga_execution_report AS
SELECT
    s.saga_id,
    o.external_order_id,
    s.status AS saga_status,
    COUNT(st.step_id) AS total_steps,
    COUNT(*) FILTER (
        WHERE st.status = 'COMPLETED'
    ) AS completed_steps,
    COUNT(*) FILTER (
        WHERE st.status = 'COMPENSATED'
    ) AS compensated_steps,
    COUNT(*) FILTER (
        WHERE st.status = 'FAILED'
    ) AS failed_steps,
    SUM(st.retry_count) AS total_attempts,
    s.failure_reason,
    s.created_at,
    s.completed_at
FROM sagas s
JOIN orders o ON o.order_id = s.order_id
LEFT JOIN saga_steps st ON st.saga_id = s.saga_id
GROUP BY
    s.saga_id,
    o.external_order_id,
    s.status,
    s.failure_reason,
    s.created_at,
    s.completed_at;

COMMIT;

-- ============================================================
-- 17. EXECUTION SCENARIO 1: SUCCESSFUL ORDER
-- ============================================================

BEGIN;

SELECT create_order_saga('ORDER-5001') AS successful_saga_id
\gset

SELECT execute_saga_step(
    :'successful_saga_id'::UUID,
    'Reserve Inventory'
);

SELECT execute_saga_step(
    :'successful_saga_id'::UUID,
    'Charge Payment'
);

SELECT execute_saga_step(
    :'successful_saga_id'::UUID,
    'Create Shipment'
);

CALL finalize_saga(:'successful_saga_id'::UUID);

COMMIT;

-- ============================================================
-- 18. EXECUTION SCENARIO 2: FAILURE AND COMPENSATION
-- ============================================================

BEGIN;

SELECT create_order_saga('ORDER-5002') AS failed_saga_id
\gset

SELECT execute_saga_step(
    :'failed_saga_id'::UUID,
    'Reserve Inventory'
);

SELECT execute_saga_step(
    :'failed_saga_id'::UUID,
    'Charge Payment'
);

SELECT execute_saga_step(
    :'failed_saga_id'::UUID,
    'Create Shipment',
    TRUE
);

CALL finalize_saga(:'failed_saga_id'::UUID);

COMMIT;

-- Compensation must execute in reverse order.
-- Shipment was not completed, so only payment and inventory
-- require compensation.

BEGIN;

SELECT compensate_saga_step(
    :'failed_saga_id'::UUID,
    'Charge Payment'
);

SELECT compensate_saga_step(
    :'failed_saga_id'::UUID,
    'Reserve Inventory'
);

CALL finalize_compensation(:'failed_saga_id'::UUID);

COMMIT;

-- ============================================================
-- 19. IDEMPOTENCY VALIDATION
-- ============================================================

SELECT execute_saga_step(
    :'successful_saga_id'::UUID,
    'Reserve Inventory'
) AS repeated_execution_result;

-- ============================================================
-- 20. REPORTING AND ANALYTICS
-- ============================================================

-- Saga execution overview.

SELECT *
FROM saga_execution_report
ORDER BY created_at;

-- Individual saga execution history.

SELECT
    s.saga_id,
    e.event_type,
    e.details,
    e.created_at
FROM saga_events e
JOIN sagas s ON s.saga_id = e.saga_id
ORDER BY e.created_at;

-- Step-level operational status.

SELECT
    s.saga_id,
    o.external_order_id,
    st.sequence_number,
    st.step_name,
    st.status,
    st.retry_count,
    st.last_error
FROM saga_steps st
JOIN sagas s ON s.saga_id = st.saga_id
JOIN orders o ON o.order_id = s.order_id
ORDER BY s.created_at, st.sequence_number;

-- Compensation effectiveness.

SELECT
    COUNT(*) FILTER (
        WHERE status = 'COMPENSATED'
    ) AS compensated_steps,
    COUNT(*) FILTER (
        WHERE status = 'COMPLETED'
    ) AS uncompensated_completed_steps,
    COUNT(*) FILTER (
        WHERE status = 'FAILED'
    ) AS failed_steps
FROM saga_steps;

-- Identify sagas requiring operational intervention.

SELECT
    saga_id,
    order_id,
    status,
    failure_reason
FROM sagas
WHERE status = 'FAILED'
   OR status = 'COMPENSATING';

-- Identify unpublished outbox events.

SELECT
    event_id,
    saga_id,
    event_type,
    payload,
    created_at
FROM saga_outbox
WHERE published = FALSE
ORDER BY created_at;

-- ============================================================
-- 21. ELIGIBILITY AND CONSISTENCY VALIDATION
-- ============================================================

SELECT
    s.saga_id,
    o.external_order_id,
    s.status,
    CASE
        WHEN s.status = 'COMPLETED'
         AND (
             NOT EXISTS (
                 SELECT 1
                 FROM inventory_reservations ir
                 WHERE ir.order_id = o.order_id
                   AND ir.reserved = TRUE
             )
             OR NOT EXISTS (
                 SELECT 1
                 FROM payments p
                 WHERE p.order_id = o.order_id
                   AND p.payment_status = 'CHARGED'
             )
             OR NOT EXISTS (
                 SELECT 1
                 FROM shipments sh
                 WHERE sh.order_id = o.order_id
                   AND sh.shipment_status = 'CREATED'
             )
         )
        THEN 'INCONSISTENT'

        WHEN s.status = 'COMPENSATED'
         AND (
             EXISTS (
                 SELECT 1
                 FROM inventory_reservations ir
                 WHERE ir.order_id = o.order_id
                   AND ir.reserved = TRUE
             )
             OR EXISTS (
                 SELECT 1
                 FROM payments p
                 WHERE p.order_id = o.order_id
                   AND p.payment_status = 'CHARGED'
             )
         )
        THEN 'COMPENSATION_INCOMPLETE'

        ELSE 'VALID'
    END AS consistency_result
FROM sagas s
JOIN orders o ON o.order_id = s.order_id;

-- ============================================================
-- END OF SAGA DEMONSTRATION
--
-- Production systems additionally require:
-- - Durable service-side idempotency.
-- - Transactional outbox publishing.
-- - Consumer deduplication.
-- - Distributed locking or optimistic concurrency.
-- - Dead-letter queues.
-- - Retry scheduling.
-- - Monitoring and alerting.
-- - Manual recovery procedures.
-- - Reconciliation with external payment providers.
-- ============================================================
