-- PostgreSQL 13+.
-- The script creates an isolated queue_lab schema.
-- It models point-to-point delivery, competing consumers, visibility leases,
-- acknowledgements, retries, capacity, idempotency keys, and dead-lettering.

DROP SCHEMA IF EXISTS queue_lab CASCADE;
CREATE SCHEMA queue_lab;

SET search_path TO queue_lab, public;

-- ============================================================
-- 1. QUEUE CONFIGURATION
-- ============================================================

CREATE TABLE queue_definition (
    queue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_name TEXT NOT NULL UNIQUE,
    max_delivery_attempts INTEGER NOT NULL DEFAULT 3,
    visibility_timeout INTERVAL NOT NULL DEFAULT INTERVAL '30 seconds',
    max_outstanding INTEGER NOT NULL DEFAULT 1000,
    dead_letter_queue_id UUID REFERENCES queue_definition(queue_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT queue_name_not_blank
        CHECK (length(trim(queue_name)) > 0),

    CONSTRAINT positive_delivery_attempts
        CHECK (max_delivery_attempts >= 1),

    CONSTRAINT positive_visibility_timeout
        CHECK (visibility_timeout > INTERVAL '0 seconds'),

    CONSTRAINT positive_queue_capacity
        CHECK (max_outstanding >= 1),

    CONSTRAINT no_self_dead_letter_queue
        CHECK (
            dead_letter_queue_id IS NULL
            OR dead_letter_queue_id <> queue_id
        )
);

COMMENT ON TABLE queue_definition IS
'Stores queue-level delivery, visibility, capacity, and dead-letter policies.';

COMMENT ON COLUMN queue_definition.max_delivery_attempts IS
'Maximum number of deliveries, including the first delivery.';

COMMENT ON COLUMN queue_definition.visibility_timeout IS
'Duration during which a delivered message is invisible to other consumers.';

-- ============================================================
-- 2. MESSAGE STORAGE
-- ============================================================

CREATE TABLE queue_message (
    sequence_id BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id UUID NOT NULL REFERENCES queue_definition(queue_id),
    body JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'READY',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    deduplication_key TEXT,
    source_message_id UUID REFERENCES queue_message(message_id),
    enqueued_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    available_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_error TEXT,

    CONSTRAINT valid_message_status
        CHECK (
            status IN (
                'READY',
                'IN_FLIGHT',
                'ACKNOWLEDGED',
                'DEAD_LETTERED'
            )
        ),

    CONSTRAINT nonnegative_attempt_count
        CHECK (attempt_count >= 0),

    CONSTRAINT message_body_must_be_object
        CHECK (jsonb_typeof(body) = 'object')
);

COMMENT ON TABLE queue_message IS
'Stores one logical message and its current queue-processing state.';

COMMENT ON COLUMN queue_message.attempt_count IS
'Number of times this message has been delivered to a consumer.';

COMMENT ON COLUMN queue_message.source_message_id IS
'Original message identifier for a message copied into a dead-letter queue.';

CREATE UNIQUE INDEX uq_message_deduplication_key
    ON queue_message(queue_id, deduplication_key)
    WHERE deduplication_key IS NOT NULL;

CREATE INDEX idx_queue_ready_messages
    ON queue_message(queue_id, enqueued_at, sequence_id)
    WHERE status = 'READY';

CREATE INDEX idx_queue_message_status
    ON queue_message(queue_id, status);

-- ============================================================
-- 3. DELIVERY HISTORY
-- ============================================================

CREATE TABLE queue_delivery (
    delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES queue_message(message_id),
    consumer_name TEXT NOT NULL,
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    lease_until TIMESTAMPTZ NOT NULL,
    settled_at TIMESTAMPTZ,
    outcome TEXT NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT nonblank_consumer_name
        CHECK (length(trim(consumer_name)) > 0),

    CONSTRAINT valid_delivery_outcome
        CHECK (
            outcome IN (
                'ACTIVE',
                'ACKNOWLEDGED',
                'REQUEUED',
                'EXPIRED',
                'DEAD_LETTERED'
            )
        ),

    CONSTRAINT valid_settlement_timestamp
        CHECK (
            (outcome = 'ACTIVE' AND settled_at IS NULL)
            OR
            (outcome <> 'ACTIVE' AND settled_at IS NOT NULL)
        )
);

COMMENT ON TABLE queue_delivery IS
'Records individual delivery attempts, leases, consumers, and settlement outcomes.';

CREATE UNIQUE INDEX uq_one_active_delivery_per_message
    ON queue_delivery(message_id)
    WHERE outcome = 'ACTIVE';

CREATE INDEX idx_active_delivery_expiry
    ON queue_delivery(lease_until)
    WHERE outcome = 'ACTIVE';

CREATE INDEX idx_delivery_consumer_history
    ON queue_delivery(consumer_name, delivered_at DESC);

-- ============================================================
-- 4. MESSAGE STATE VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_message_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status <> OLD.status THEN
        IF NOT (
            (OLD.status = 'READY'
                AND NEW.status = 'IN_FLIGHT')
            OR
            (OLD.status = 'IN_FLIGHT'
                AND NEW.status IN (
                    'READY',
                    'ACKNOWLEDGED',
                    'DEAD_LETTERED'
                ))
        ) THEN
            RAISE EXCEPTION
                'Invalid message transition from % to %',
                OLD.status,
                NEW.status;
        END IF;
    END IF;

    IF jsonb_typeof(NEW.body) <> 'object' THEN
        RAISE EXCEPTION 'Message body must be a JSON object.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_message_transition
BEFORE INSERT OR UPDATE ON queue_message
FOR EACH ROW
EXECUTE FUNCTION validate_message_transition();

-- ============================================================
-- 5. ENQUEUE WITH CAPACITY AND DEDUPLICATION
-- ============================================================

CREATE OR REPLACE FUNCTION enqueue_message(
    p_queue_name TEXT,
    p_body JSONB,
    p_deduplication_key TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_queue_id UUID;
    v_capacity INTEGER;
    v_outstanding BIGINT;
    v_message_id UUID;
BEGIN
    IF p_body IS NULL OR jsonb_typeof(p_body) <> 'object' THEN
        RAISE EXCEPTION 'Message body must be a non-null JSON object.';
    END IF;

    IF p_deduplication_key IS NOT NULL
       AND length(trim(p_deduplication_key)) = 0 THEN
        RAISE EXCEPTION 'Deduplication key cannot be blank.';
    END IF;

    -- Serialize capacity checks for one queue. This prevents concurrent
    -- publishers from exceeding its configured outstanding-message limit.
    SELECT queue_id, max_outstanding
    INTO v_queue_id, v_capacity
    FROM queue_definition
    WHERE queue_name = p_queue_name
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown queue: %', p_queue_name;
    END IF;

    IF p_deduplication_key IS NOT NULL THEN
        SELECT message_id
        INTO v_message_id
        FROM queue_message
        WHERE queue_id = v_queue_id
          AND deduplication_key = p_deduplication_key;

        IF FOUND THEN
            RETURN v_message_id;
        END IF;
    END IF;

    SELECT count(*)
    INTO v_outstanding
    FROM queue_message
    WHERE queue_id = v_queue_id
      AND status IN ('READY', 'IN_FLIGHT');

    IF v_outstanding >= v_capacity THEN
        RAISE EXCEPTION 'Queue % has reached its capacity.', p_queue_name;
    END IF;

    INSERT INTO queue_message (
        queue_id,
        body,
        deduplication_key
    )
    VALUES (
        v_queue_id,
        p_body,
        p_deduplication_key
    )
    ON CONFLICT (queue_id, deduplication_key)
        WHERE deduplication_key IS NOT NULL
        DO NOTHING
    RETURNING message_id INTO v_message_id;

    IF v_message_id IS NULL THEN
        SELECT message_id
        INTO v_message_id
        FROM queue_message
        WHERE queue_id = v_queue_id
          AND deduplication_key = p_deduplication_key;
    END IF;

    RETURN v_message_id;
END;
$$;

COMMENT ON FUNCTION enqueue_message(TEXT, JSONB, TEXT) IS
'Enqueues a JSON message while enforcing capacity and optional deduplication.';

-- ============================================================
-- 6. CLAIM ONE MESSAGE
-- ============================================================

CREATE OR REPLACE FUNCTION claim_message(
    p_queue_name TEXT,
    p_consumer_name TEXT,
    p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TABLE (
    message_id UUID,
    delivery_id UUID,
    body JSONB,
    attempt_count INTEGER,
    lease_until TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_queue_id UUID;
    v_visibility_timeout INTERVAL;
    v_message_id UUID;
    v_delivery_id UUID;
    v_attempt_count INTEGER;
    v_body JSONB;
    v_lease_until TIMESTAMPTZ;
BEGIN
    IF p_consumer_name IS NULL OR length(trim(p_consumer_name)) = 0 THEN
        RAISE EXCEPTION 'Consumer name cannot be blank.';
    END IF;

    SELECT q.queue_id, q.visibility_timeout
    INTO v_queue_id, v_visibility_timeout
    FROM queue_definition AS q
    WHERE q.queue_name = p_queue_name;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown queue: %', p_queue_name;
    END IF;

    -- SKIP LOCKED allows concurrent consumers to claim different rows
    -- without waiting for another consumer's message lock.
    SELECT m.message_id
    INTO v_message_id
    FROM queue_message AS m
    WHERE m.queue_id = v_queue_id
      AND m.status = 'READY'
      AND m.available_at <= p_now
    ORDER BY m.enqueued_at, m.sequence_id
    LIMIT 1
    FOR UPDATE OF m SKIP LOCKED;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    UPDATE queue_message AS m
    SET status = 'IN_FLIGHT',
        attempt_count = m.attempt_count + 1
    WHERE m.message_id = v_message_id
    RETURNING m.body, m.attempt_count
    INTO v_body, v_attempt_count;

    v_delivery_id := gen_random_uuid();
    v_lease_until := p_now + v_visibility_timeout;

    INSERT INTO queue_delivery (
        delivery_id,
        message_id,
        consumer_name,
        delivered_at,
        lease_until
    )
    VALUES (
        v_delivery_id,
        v_message_id,
        p_consumer_name,
        p_now,
        v_lease_until
    );

    RETURN QUERY
    SELECT
        v_message_id,
        v_delivery_id,
        v_body,
        v_attempt_count,
        v_lease_until;
END;
$$;

COMMENT ON FUNCTION claim_message(TEXT, TEXT, TIMESTAMPTZ) IS
'Atomically claims one ready message using row-level locking and SKIP LOCKED.';

-- ============================================================
-- 7. ACKNOWLEDGE A DELIVERY
-- ============================================================

CREATE OR REPLACE FUNCTION acknowledge_delivery(
    p_delivery_id UUID,
    p_consumer_name TEXT,
    p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_message_id UUID;
BEGIN
    SELECT d.message_id
    INTO v_message_id
    FROM queue_delivery AS d
    JOIN queue_message AS m
      ON m.message_id = d.message_id
    WHERE d.delivery_id = p_delivery_id
      AND d.consumer_name = p_consumer_name
      AND d.outcome = 'ACTIVE'
      AND m.status = 'IN_FLIGHT'
      AND d.lease_until > p_now
    FOR UPDATE OF d, m;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Delivery is invalid, expired, settled, or owned by another consumer.';
    END IF;

    UPDATE queue_delivery
    SET outcome = 'ACKNOWLEDGED',
        settled_at = p_now
    WHERE delivery_id = p_delivery_id;

    UPDATE queue_message
    SET status = 'ACKNOWLEDGED'
    WHERE message_id = v_message_id;
END;
$$;

-- ============================================================
-- 8. NEGATIVE ACKNOWLEDGEMENT AND DEAD-LETTER ROUTING
-- ============================================================

CREATE OR REPLACE FUNCTION nack_delivery(
    p_delivery_id UUID,
    p_consumer_name TEXT,
    p_requeue BOOLEAN DEFAULT TRUE,
    p_error TEXT DEFAULT 'Consumer rejected the message.',
    p_now TIMESTAMPTZ DEFAULT clock_timestamp(),
    p_expiry_recovery BOOLEAN DEFAULT FALSE
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_message_id UUID;
    v_queue_id UUID;
    v_body JSONB;
    v_attempt_count INTEGER;
    v_max_attempts INTEGER;
    v_dead_letter_queue_id UUID;
    v_lease_until TIMESTAMPTZ;
    v_dead BOOLEAN;
    v_outcome TEXT;
    v_reason TEXT;
BEGIN
    SELECT
        d.message_id,
        d.lease_until,
        m.queue_id,
        m.body,
        m.attempt_count,
        q.max_delivery_attempts,
        q.dead_letter_queue_id
    INTO
        v_message_id,
        v_lease_until,
        v_queue_id,
        v_body,
        v_attempt_count,
        v_max_attempts,
        v_dead_letter_queue_id
    FROM queue_delivery AS d
    JOIN queue_message AS m
      ON m.message_id = d.message_id
    JOIN queue_definition AS q
      ON q.queue_id = m.queue_id
    WHERE d.delivery_id = p_delivery_id
      AND d.consumer_name = p_consumer_name
      AND d.outcome = 'ACTIVE'
      AND m.status = 'IN_FLIGHT'
    FOR UPDATE OF d, m;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Delivery is unknown, already settled, or owned by another consumer.';
    END IF;

    IF p_expiry_recovery AND v_lease_until > p_now THEN
        RAISE EXCEPTION 'Cannot recover a lease that has not expired.';
    END IF;

    IF NOT p_expiry_recovery AND v_lease_until <= p_now THEN
        RAISE EXCEPTION 'Delivery lease has expired; recovery is required.';
    END IF;

    v_dead := NOT p_requeue
              OR v_attempt_count >= v_max_attempts;

    v_reason := COALESCE(
        NULLIF(trim(p_error), ''),
        'Consumer rejected the message.'
    );

    IF v_dead THEN
        IF p_expiry_recovery THEN
            v_outcome := 'EXPIRED';
        ELSIF NOT p_requeue THEN
            v_outcome := 'DEAD_LETTERED';
        ELSE
            v_outcome := 'DEAD_LETTERED';
        END IF;

        UPDATE queue_message
        SET status = 'DEAD_LETTERED',
            last_error = v_reason
        WHERE message_id = v_message_id;

        -- The original remains in its source queue for audit purposes.
        -- A separate ready message is created in the configured DLQ.
        IF v_dead_letter_queue_id IS NOT NULL THEN
            INSERT INTO queue_message (
                queue_id,
                body,
                status,
                attempt_count,
                source_message_id,
                enqueued_at,
                available_at,
                last_error
            )
            VALUES (
                v_dead_letter_queue_id,
                v_body,
                'READY',
                0,
                v_message_id,
                p_now,
                p_now,
                v_reason
            )
            ON CONFLICT (source_message_id) DO NOTHING;
        END IF;
    ELSE
        IF p_expiry_recovery THEN
            v_outcome := 'EXPIRED';
        ELSE
            v_outcome := 'REQUEUED';
        END IF;

        UPDATE queue_message
        SET status = 'READY',
            available_at = p_now,
            last_error = v_reason
        WHERE message_id = v_message_id;
    END IF;

    UPDATE queue_delivery
    SET outcome = v_outcome,
        settled_at = p_now
    WHERE delivery_id = p_delivery_id;

    RETURN CASE
        WHEN v_dead THEN 'DEAD_LETTERED'
        ELSE 'REQUEUED'
    END;
END;
$$;

-- ============================================================
-- 9. VISIBILITY-TIMEOUT RECOVERY
-- ============================================================

CREATE OR REPLACE FUNCTION recover_expired_deliveries(
    p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_delivery RECORD;
    v_recovered INTEGER := 0;
BEGIN
    FOR v_delivery IN
        SELECT delivery_id, consumer_name
        FROM queue_delivery
        WHERE outcome = 'ACTIVE'
          AND lease_until <= p_now
        ORDER BY lease_until
        FOR UPDATE SKIP LOCKED
    LOOP
        PERFORM nack_delivery(
            v_delivery.delivery_id,
            v_delivery.consumer_name,
            TRUE,
            'Visibility timeout expired.',
            p_now,
            TRUE
        );

        v_recovered := v_recovered + 1;
    END LOOP;

    RETURN v_recovered;
END;
$$;

-- ============================================================
-- 10. REPORTING VIEW
-- ============================================================

CREATE OR REPLACE VIEW queue_metrics AS
SELECT
    q.queue_id,
    q.queue_name,
    q.max_delivery_attempts,
    q.visibility_timeout,
    q.max_outstanding,
    COUNT(m.message_id) FILTER (
        WHERE m.status = 'READY'
    ) AS ready_count,
    COUNT(m.message_id) FILTER (
        WHERE m.status = 'IN_FLIGHT'
    ) AS in_flight_count,
    COUNT(m.message_id) FILTER (
        WHERE m.status = 'ACKNOWLEDGED'
    ) AS acknowledged_count,
    COUNT(m.message_id) FILTER (
        WHERE m.status = 'DEAD_LETTERED'
    ) AS dead_lettered_count,
    MIN(m.enqueued_at) FILTER (
        WHERE m.status = 'READY'
    ) AS oldest_ready_message_at
FROM queue_definition AS q
LEFT JOIN queue_message AS m
    ON m.queue_id = q.queue_id
GROUP BY
    q.queue_id,
    q.queue_name,
    q.max_delivery_attempts,
    q.visibility_timeout,
    q.max_outstanding;

-- ============================================================
-- 11. SAMPLE QUEUES AND POLICIES
-- ============================================================

INSERT INTO queue_definition (
    queue_name,
    max_delivery_attempts,
    visibility_timeout,
    max_outstanding
)
VALUES
    ('orders', 3, INTERVAL '30 seconds', 100),
    ('orders-dlq', 5, INTERVAL '5 minutes', 1000);

UPDATE queue_definition
SET dead_letter_queue_id = (
    SELECT queue_id
    FROM queue_definition
    WHERE queue_name = 'orders-dlq'
)
WHERE queue_name = 'orders';

-- ============================================================
-- 12. SAMPLE MESSAGE PUBLICATION
-- ============================================================

BEGIN;

SELECT enqueue_message(
    'orders',
    '{"order_id":"ORD-1001","amount":4500,"region":"north"}'::JSONB,
    'order-event-1001'
);

SELECT enqueue_message(
    'orders',
    '{"order_id":"ORD-1002","amount":2800,"region":"west"}'::JSONB,
    'order-event-1002'
);

SELECT enqueue_message(
    'orders',
    '{"order_id":"ORD-1003","amount":9900,"region":"south","invalid":true}'::JSONB,
    'order-event-1003'
);

-- A repeated deduplication key returns the existing message identifier.
SELECT enqueue_message(
    'orders',
    '{"order_id":"ORD-1001","amount":4500,"region":"north"}'::JSONB,
    'order-event-1001'
);

COMMIT;

-- ============================================================
-- 13. COMPETING-CONSUMER CLAIMS
-- ============================================================

-- These two claims represent separate consumer transactions.
-- SKIP LOCKED prevents them from claiming the same active row.

CREATE TEMP TABLE demonstration_deliveries (
    scenario TEXT PRIMARY KEY,
    message_id UUID,
    delivery_id UUID,
    body JSONB,
    attempt_count INTEGER,
    lease_until TIMESTAMPTZ,
    consumer_name TEXT NOT NULL
);

DO $$
DECLARE
    v_delivery RECORD;
BEGIN
    SELECT *
    INTO v_delivery
    FROM claim_message('orders', 'worker-1');

    INSERT INTO demonstration_deliveries (
        scenario,
        message_id,
        delivery_id,
        body,
        attempt_count,
        lease_until,
        consumer_name
    )
    VALUES (
        'worker-1-first',
        v_delivery.message_id,
        v_delivery.delivery_id,
        v_delivery.body,
        v_delivery.attempt_count,
        v_delivery.lease_until,
        'worker-1'
    );

    SELECT *
    INTO v_delivery
    FROM claim_message('orders', 'worker-2');

    INSERT INTO demonstration_deliveries (
        scenario,
        message_id,
        delivery_id,
        body,
        attempt_count,
        lease_until,
        consumer_name
    )
    VALUES (
        'worker-2-first',
        v_delivery.message_id,
        v_delivery.delivery_id,
        v_delivery.body,
        v_delivery.attempt_count,
        v_delivery.lease_until,
        'worker-2'
    );
END;
$$;

-- Inspect the separate assignments.
SELECT
    scenario,
    consumer_name,
    message_id,
    attempt_count,
    body
FROM demonstration_deliveries
ORDER BY scenario;

-- ============================================================
-- 14. SUCCESSFUL ACKNOWLEDGEMENT
-- ============================================================

SELECT acknowledge_delivery(
    delivery_id,
    consumer_name
)
FROM demonstration_deliveries
WHERE scenario = 'worker-1-first';

-- ============================================================
-- 15. TRANSIENT FAILURE AND REDELIVERY
-- ============================================================

DO $$
DECLARE
    v_first RECORD;
    v_second RECORD;
BEGIN
    SELECT *
    INTO v_first
    FROM demonstration_deliveries
    WHERE scenario = 'worker-2-first';

    PERFORM nack_delivery(
        v_first.delivery_id,
        'worker-2',
        TRUE,
        'Temporary downstream payment-service failure.'
    );

    -- The requeued message becomes available to another consumer.
    SELECT *
    INTO v_second
    FROM claim_message('orders', 'worker-3');

    INSERT INTO demonstration_deliveries (
        scenario,
        message_id,
        delivery_id,
        body,
        attempt_count,
        lease_until,
        consumer_name
    )
    VALUES (
        'worker-3-retry',
        v_second.message_id,
        v_second.delivery_id,
        v_second.body,
        v_second.attempt_count,
        v_second.lease_until,
        'worker-3'
    );

    IF v_second.message_id <> v_first.message_id THEN
        RAISE EXCEPTION 'Expected the failed message to be redelivered.';
    END IF;

    IF v_second.attempt_count <> 2 THEN
        RAISE EXCEPTION 'Expected delivery attempt number two.';
    END IF;

    PERFORM acknowledge_delivery(
        v_second.delivery_id,
        'worker-3'
    );
END;
$$;

-- ============================================================
-- 16. POISON MESSAGE AND DEAD-LETTER ROUTING
-- ============================================================

DO $$
DECLARE
    v_delivery RECORD;
    v_attempt INTEGER;
    v_message_id UUID;
BEGIN
    -- Find the message identified by the sample order event.
    SELECT message_id
    INTO v_message_id
    FROM queue_message
    WHERE queue_id = (
        SELECT queue_id
        FROM queue_definition
        WHERE queue_name = 'orders'
    )
      AND deduplication_key = 'order-event-1003';

    FOR v_attempt IN 1..3 LOOP
        SELECT *
        INTO v_delivery
        FROM claim_message(
            'orders',
            'poison-worker-' || v_attempt
        );

        IF NOT FOUND THEN
            RAISE EXCEPTION 'No message available for poison-message test.';
        END IF;

        IF v_delivery.message_id <> v_message_id THEN
            RAISE EXCEPTION 'Unexpected message claimed in poison test.';
        END IF;

        PERFORM nack_delivery(
            v_delivery.delivery_id,
            'poison-worker-' || v_attempt,
            TRUE,
            'Order failed business validation.'
        );
    END LOOP;
END;
$$;

-- ============================================================
-- 17. DELIVERY LEASE RECOVERY EXAMPLE
-- ============================================================

-- A separate message is claimed with an artificial timestamp.
-- This makes the expiry workflow reproducible without waiting for the
-- configured real visibility timeout.

DO $$
DECLARE
    v_message_id UUID;
    v_delivery RECORD;
    v_future TIMESTAMPTZ;
BEGIN
    v_message_id := enqueue_message(
        'orders',
        '{"order_id":"ORD-1004","amount":5100,"region":"east"}'::JSONB,
        'order-event-1004'
    );

    SELECT *
    INTO v_delivery
    FROM claim_message(
        'orders',
        'lease-test-worker'
    );

    IF v_delivery.message_id <> v_message_id THEN
        -- Other messages may be available in the queue. The claim function
        -- remains deterministic by insertion order in this demonstration.
        RAISE EXCEPTION 'Unexpected message claimed during lease test.';
    END IF;

    v_future := v_delivery.lease_until + INTERVAL '1 second';

    PERFORM recover_expired_deliveries(v_future);
END;
$$;

-- ============================================================
-- 18. RETRIEVAL AND REPORTING QUERIES
-- ============================================================

-- Current queue counts and policy.
SELECT *
FROM queue_metrics
ORDER BY queue_name;

-- Message state by queue.
SELECT
    q.queue_name,
    m.status,
    COUNT(*) AS message_count
FROM queue_message AS m
JOIN queue_definition AS q
    ON q.queue_id = m.queue_id
GROUP BY q.queue_name, m.status
ORDER BY q.queue_name, m.status;

-- Delivery history by consumer.
SELECT
    d.consumer_name,
    d.outcome,
    COUNT(*) AS delivery_count,
    MIN(d.delivered_at) AS first_delivery,
    MAX(d.delivered_at) AS latest_delivery
FROM queue_delivery AS d
GROUP BY d.consumer_name, d.outcome
ORDER BY d.consumer_name, d.outcome;

-- Identify repeated delivery attempts.
SELECT
    q.queue_name,
    m.message_id,
    m.body,
    m.attempt_count,
    m.status,
    m.last_error
FROM queue_message AS m
JOIN queue_definition AS q
    ON q.queue_id = m.queue_id
WHERE m.attempt_count > 1
ORDER BY m.attempt_count DESC, m.enqueued_at;

-- Inspect the dead-letter queue and its source messages.
SELECT
    dlq.queue_name AS destination_queue,
    m.message_id AS dead_letter_message_id,
    m.source_message_id,
    m.body,
    m.enqueued_at,
    m.last_error
FROM queue_message AS m
JOIN queue_definition AS dlq
    ON dlq.queue_id = m.queue_id
WHERE dlq.queue_name = 'orders-dlq'
ORDER BY m.enqueued_at;

-- CTE-based operational view of ready messages and queue age.
WITH ready_messages AS (
    SELECT
        q.queue_name,
        m.message_id,
        m.enqueued_at,
        m.available_at,
        m.attempt_count,
        ROW_NUMBER() OVER (
            PARTITION BY q.queue_name
            ORDER BY m.enqueued_at, m.sequence_id
        ) AS queue_position
    FROM queue_message AS m
    JOIN queue_definition AS q
        ON q.queue_id = m.queue_id
    WHERE m.status = 'READY'
)
SELECT
    queue_name,
    message_id,
    queue_position,
    attempt_count,
    clock_timestamp() - enqueued_at AS queue_age
FROM ready_messages
ORDER BY queue_name, queue_position;

-- Operational inspection of messages whose processing may need attention.
SELECT
    m.message_id,
    q.queue_name,
    m.status,
    m.attempt_count,
    m.last_error
FROM queue_message AS m
JOIN queue_definition AS q
    ON q.queue_id = m.queue_id
WHERE m.status IN ('IN_FLIGHT', 'DEAD_LETTERED')
ORDER BY q.queue_name, m.enqueued_at;

-- The following query should return no active delivery without an
-- in-flight message.
SELECT
    d.delivery_id,
    d.message_id,
    d.consumer_name,
    m.status AS message_status
FROM queue_delivery AS d
JOIN queue_message AS m
    ON m.message_id = d.message_id
WHERE d.outcome = 'ACTIVE'
  AND m.status <> 'IN_FLIGHT';

-- ============================================================
-- 19. POLICY AND FAILURE-CASE VALIDATION
-- ============================================================

DO $$
BEGIN
    -- An invalid state transition must be rejected by the trigger.
    BEGIN
        UPDATE queue_message
        SET status = 'ACKNOWLEDGED'
        WHERE status = 'READY'
        LIMIT 1;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Invalid transition correctly rejected: %',
                SQLERRM;
    END;

    -- Invalid payload types are rejected by the database constraint.
    BEGIN
        PERFORM enqueue_message(
            'orders',
            '[]'::JSONB,
            'invalid-array-payload'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Invalid payload correctly rejected: %',
                SQLERRM;
    END;
END;
$$;

-- ============================================================
-- 20. FINAL QUEUE AND DELIVERY REPORT
-- ============================================================

SELECT
    queue_name,
    ready_count,
    in_flight_count,
    acknowledged_count,
    dead_lettered_count,
    oldest_ready_message_at
FROM queue_metrics
ORDER BY queue_name;
