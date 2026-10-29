DROP SCHEMA IF EXISTS messaging CASCADE;

CREATE SCHEMA messaging;

CREATE TYPE messaging.message_state AS ENUM (
    'ready',
    'in_flight',
    'acked',
    'dead_lettered'
);

CREATE TYPE messaging.consumer_state AS ENUM (
    'active',
    'paused',
    'disabled'
);

CREATE TYPE messaging.delivery_result AS ENUM (
    'ack',
    'retry',
    'reject'
);

CREATE TABLE messaging.broker (
    broker_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    broker_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE messaging.producer (
    producer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    broker_id BIGINT NOT NULL REFERENCES messaging.broker(broker_id),
    producer_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (broker_id, producer_name)
);

CREATE TABLE messaging.queue (
    queue_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    broker_id BIGINT NOT NULL REFERENCES messaging.broker(broker_id),
    queue_name TEXT NOT NULL,
    durable BOOLEAN NOT NULL DEFAULT TRUE,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(trim(queue_name)) > 0),
    CHECK (max_attempts BETWEEN 1 AND 100),
    UNIQUE (broker_id, queue_name)
);

CREATE TABLE messaging.consumer (
    consumer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    queue_id BIGINT NOT NULL REFERENCES messaging.queue(queue_id),
    consumer_name TEXT NOT NULL,
    state messaging.consumer_state NOT NULL DEFAULT 'active',
    prefetch_count INTEGER NOT NULL DEFAULT 1,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (prefetch_count BETWEEN 1 AND 1000),
    UNIQUE (queue_id, consumer_name)
);

CREATE TABLE messaging.message (
    message_id UUID PRIMARY KEY,
    queue_id BIGINT NOT NULL REFERENCES messaging.queue(queue_id),
    producer_id BIGINT NOT NULL REFERENCES messaging.producer(producer_id),
    payload JSONB NOT NULL,
    message_key TEXT,
    state messaging.message_state NOT NULL DEFAULT 'ready',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    delivered_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    CHECK (attempts >= 0),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE TABLE messaging.delivery (
    delivery_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES messaging.message(message_id),
    consumer_id BIGINT NOT NULL REFERENCES messaging.consumer(consumer_id),
    delivery_attempt INTEGER NOT NULL,
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    settled_at TIMESTAMPTZ,
    result messaging.delivery_result,
    CHECK (delivery_attempt > 0),
    UNIQUE (message_id, delivery_attempt)
);

CREATE TABLE messaging.review_event (
    review_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id BIGINT NOT NULL REFERENCES messaging.delivery(delivery_id),
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(trim(event_type)) > 0)
);

CREATE TABLE messaging.dead_letter (
    dead_letter_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id UUID NOT NULL UNIQUE REFERENCES messaging.message(message_id),
    queue_id BIGINT NOT NULL REFERENCES messaging.queue(queue_id),
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_message_queue_state
    ON messaging.message(queue_id, state, created_at);

CREATE INDEX idx_delivery_consumer_open
    ON messaging.delivery(consumer_id, settled_at)
    WHERE settled_at IS NULL;

CREATE INDEX idx_review_event_delivery
    ON messaging.review_event(delivery_id, created_at);

CREATE INDEX idx_dead_letter_queue_created
    ON messaging.dead_letter(queue_id, created_at);

CREATE OR REPLACE FUNCTION messaging.validate_message_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'acked' AND NEW.acknowledged_at IS NULL THEN
        RAISE EXCEPTION
            'Acknowledged message % must have acknowledged_at',
            NEW.message_id;
    END IF;

    IF NEW.attempts < 0 THEN
        RAISE EXCEPTION
            'Message attempts cannot be negative';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_message_state
BEFORE INSERT OR UPDATE ON messaging.message
FOR EACH ROW
EXECUTE FUNCTION messaging.validate_message_state();

CREATE OR REPLACE FUNCTION messaging.publish_message(
    p_queue_name TEXT,
    p_producer_name TEXT,
    p_payload JSONB,
    p_message_key TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_queue_id BIGINT;
    v_producer_id BIGINT;
    v_message_id UUID := gen_random_uuid();
BEGIN
    SELECT q.queue_id
    INTO v_queue_id
    FROM messaging.queue q
    JOIN messaging.broker b
      ON b.broker_id = q.broker_id
    WHERE q.queue_name = p_queue_name
    ORDER BY q.queue_id
    LIMIT 1;

    IF v_queue_id IS NULL THEN
        RAISE EXCEPTION 'Queue % does not exist', p_queue_name;
    END IF;

    SELECT p.producer_id
    INTO v_producer_id
    FROM messaging.producer p
    JOIN messaging.queue q
      ON q.broker_id = p.broker_id
    WHERE q.queue_id = v_queue_id
      AND p.producer_name = p_producer_name
      AND p.active = TRUE
    LIMIT 1;

    IF v_producer_id IS NULL THEN
        RAISE EXCEPTION
            'Active producer % does not belong to the queue broker',
            p_producer_name;
    END IF;

    IF p_payload IS NULL
       OR jsonb_typeof(p_payload) <> 'object' THEN
        RAISE EXCEPTION
            'Message payload must be a JSON object';
    END IF;

    INSERT INTO messaging.message (
        message_id,
        queue_id,
        producer_id,
        payload,
        message_key
    )
    VALUES (
        v_message_id,
        v_queue_id,
        v_producer_id,
        p_payload,
        p_message_key
    );

    RETURN v_message_id;
END;
$$;

CREATE OR REPLACE FUNCTION messaging.deliver_message(
    p_consumer_id BIGINT
)
RETURNS TABLE (
    message_id UUID,
    payload JSONB,
    delivery_attempt INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_queue_id BIGINT;
    v_message_id UUID;
    v_attempt INTEGER;
BEGIN
    SELECT c.queue_id
    INTO v_queue_id
    FROM messaging.consumer c
    WHERE c.consumer_id = p_consumer_id
      AND c.state = 'active';

    IF v_queue_id IS NULL THEN
        RAISE EXCEPTION
            'Consumer % is missing or inactive',
            p_consumer_id;
    END IF;

    /*
     * FOR UPDATE SKIP LOCKED allows multiple workers to compete for
     * ready messages without blocking each other.
     */
    SELECT m.message_id
    INTO v_message_id
    FROM messaging.message m
    WHERE m.queue_id = v_queue_id
      AND m.state = 'ready'
    ORDER BY m.created_at, m.message_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF v_message_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE messaging.message
    SET
        state = 'in_flight',
        attempts = attempts + 1,
        delivered_at = clock_timestamp()
    WHERE message.message_id = v_message_id
    RETURNING
        message.attempts
    INTO v_attempt;

    INSERT INTO messaging.delivery (
        message_id,
        consumer_id,
        delivery_attempt
    )
    VALUES (
        v_message_id,
        p_consumer_id,
        v_attempt
    );

    RETURN QUERY
    SELECT
        m.message_id,
        m.payload,
        v_attempt
    FROM messaging.message m
    WHERE m.message_id = v_message_id;
END;
$$;

CREATE OR REPLACE FUNCTION messaging.settle_message(
    p_consumer_id BIGINT,
    p_message_id UUID,
    p_result messaging.delivery_result,
    p_reason TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_queue_id BIGINT;
    v_attempts INTEGER;
    v_max_attempts INTEGER;
    v_delivery_id BIGINT;
BEGIN
    SELECT
        c.queue_id,
        q.max_attempts
    INTO
        v_queue_id,
        v_max_attempts
    FROM messaging.consumer c
    JOIN messaging.queue q
      ON q.queue_id = c.queue_id
    WHERE c.consumer_id = p_consumer_id;

    IF v_queue_id IS NULL THEN
        RAISE EXCEPTION
            'Consumer % does not exist',
            p_consumer_id;
    END IF;

    SELECT
        m.attempts
    INTO v_attempts
    FROM messaging.message m
    WHERE m.message_id = p_message_id
      AND m.queue_id = v_queue_id
      AND m.state = 'in_flight'
    FOR UPDATE;

    IF v_attempts IS NULL THEN
        RAISE EXCEPTION
            'Message % is not an in-flight message for consumer queue',
            p_message_id;
    END IF;

    SELECT d.delivery_id
    INTO v_delivery_id
    FROM messaging.delivery d
    WHERE d.message_id = p_message_id
      AND d.consumer_id = p_consumer_id
      AND d.settled_at IS NULL
    ORDER BY d.delivery_id DESC
    LIMIT 1
    FOR UPDATE;

    IF v_delivery_id IS NULL THEN
        RAISE EXCEPTION
            'No open delivery exists for message %',
            p_message_id;
    END IF;

    IF p_result = 'ack' THEN
        UPDATE messaging.message
        SET
            state = 'acked',
            acknowledged_at = clock_timestamp()
        WHERE message_id = p_message_id;

    ELSIF p_result = 'retry' AND v_attempts < v_max_attempts THEN
        UPDATE messaging.message
        SET state = 'ready'
        WHERE message_id = p_message_id;

    ELSE
        UPDATE messaging.message
        SET state = 'dead_lettered'
        WHERE message_id = p_message_id;

        INSERT INTO messaging.dead_letter (
            message_id,
            queue_id,
            reason
        )
        VALUES (
            p_message_id,
            v_queue_id,
            COALESCE(
                p_reason,
                CASE
                    WHEN p_result = 'reject'
                    THEN 'consumer_rejected'
                    ELSE 'maximum_attempts_exceeded'
                END
            )
        )
        ON CONFLICT (message_id) DO NOTHING;
    END IF;

    UPDATE messaging.delivery
    SET
        settled_at = clock_timestamp(),
        result = p_result
    WHERE delivery_id = v_delivery_id;

    INSERT INTO messaging.review_event (
        delivery_id,
        event_type,
        event_payload
    )
    VALUES (
        v_delivery_id,
        'message_settled',
        jsonb_build_object(
            'result', p_result,
            'reason', p_reason
        )
    );
END;
$$;

CREATE OR REPLACE VIEW messaging.queue_status AS
SELECT
    q.queue_id,
    q.queue_name,
    q.durable,
    q.max_attempts,
    COUNT(m.message_id)
        FILTER (WHERE m.state = 'ready') AS ready_messages,
    COUNT(m.message_id)
        FILTER (WHERE m.state = 'in_flight') AS in_flight_messages,
    COUNT(m.message_id)
        FILTER (WHERE m.state = 'acked') AS acknowledged_messages,
    COUNT(m.message_id)
        FILTER (WHERE m.state = 'dead_lettered') AS dead_lettered_messages
FROM messaging.queue q
LEFT JOIN messaging.message m
    ON m.queue_id = q.queue_id
GROUP BY
    q.queue_id,
    q.queue_name,
    q.durable,
    q.max_attempts;

INSERT INTO messaging.broker (broker_name)
VALUES ('orders-broker');

INSERT INTO messaging.producer (
    broker_id,
    producer_name
)
SELECT
    broker_id,
    'checkout-service'
FROM messaging.broker
WHERE broker_name = 'orders-broker';

INSERT INTO messaging.queue (
    broker_id,
    queue_name,
    durable,
    max_attempts
)
SELECT
    broker_id,
    'orders',
    TRUE,
    3
FROM messaging.broker
WHERE broker_name = 'orders-broker';

INSERT INTO messaging.consumer (
    queue_id,
    consumer_name,
    state,
    prefetch_count
)
SELECT
    queue_id,
    'fulfillment-worker-1',
    'active',
    2
FROM messaging.queue
WHERE queue_name = 'orders';

BEGIN;

SELECT messaging.publish_message(
    'orders',
    'checkout-service',
    '{"order_id":"ORD-1001","event":"order.created","amount":1250}'::jsonb,
    'ORD-1001'
);

SELECT messaging.publish_message(
    'orders',
    'checkout-service',
    '{"order_id":"ORD-1002","event":"order.created","amount":850}'::jsonb,
    'ORD-1002'
);

SELECT messaging.publish_message(
    'orders',
    'checkout-service',
    '{"order_id":"ORD-FAIL","event":"order.created","amount":430}'::jsonb,
    'ORD-FAIL'
);

COMMIT;

SELECT *
FROM messaging.queue_status;

BEGIN;

SELECT *
FROM messaging.deliver_message(
    (
        SELECT consumer_id
        FROM messaging.consumer
        WHERE consumer_name = 'fulfillment-worker-1'
    )
);

COMMIT;

BEGIN;

WITH delivery AS (
    SELECT
        d.delivery_id,
        d.message_id,
        d.consumer_id
    FROM messaging.delivery d
    JOIN messaging.message m
      ON m.message_id = d.message_id
    WHERE m.message_key = 'ORD-1001'
      AND d.settled_at IS NULL
    ORDER BY d.delivery_id DESC
    LIMIT 1
)
SELECT messaging.settle_message(
    consumer_id,
    message_id,
    'ack',
    'Order processed successfully'
)
FROM delivery;

COMMIT;

BEGIN;

WITH delivery AS (
    SELECT
        d.message_id,
        d.consumer_id
    FROM messaging.delivery d
    JOIN messaging.message m
      ON m.message_id = d.message_id
    WHERE m.message_key = 'ORD-FAIL'
      AND d.settled_at IS NULL
    ORDER BY d.delivery_id DESC
    LIMIT 1
)
SELECT messaging.settle_message(
    consumer_id,
    message_id,
    'retry',
    'Temporary downstream service failure'
)
FROM delivery;

COMMIT;

-- Repeated delivery of a failing message eventually creates a
-- dead-letter record after the queue's max_attempts threshold.
DO $$
DECLARE
    v_consumer_id BIGINT;
    v_message_id UUID;
    v_attempt INTEGER;
BEGIN
    SELECT consumer_id
    INTO v_consumer_id
    FROM messaging.consumer
    WHERE consumer_name = 'fulfillment-worker-1';

    FOR i IN 1..3 LOOP
        SELECT
            d.message_id,
            d.delivery_attempt
        INTO
            v_message_id,
            v_attempt
        FROM messaging.delivery d
        JOIN messaging.message m
          ON m.message_id = d.message_id
        WHERE m.message_key = 'ORD-FAIL'
          AND d.consumer_id = v_consumer_id
          AND d.settled_at IS NULL
        ORDER BY d.delivery_id DESC
        LIMIT 1;

        IF v_message_id IS NULL THEN
            SELECT message_id
            INTO v_message_id
            FROM messaging.message
            WHERE message_key = 'ORD-FAIL'
            LIMIT 1;
        END IF;

        PERFORM messaging.settle_message(
            v_consumer_id,
            v_message_id,
            'retry',
            'Downstream payment service unavailable'
        );

        IF NOT EXISTS (
            SELECT 1
            FROM messaging.message
            WHERE message_id = v_message_id
              AND state = 'ready'
        ) THEN
            EXIT;
        END IF;

        PERFORM messaging.deliver_message(v_consumer_id);
    END LOOP;
END;
$$;

SELECT *
FROM messaging.queue_status
ORDER BY queue_name;

-- CTE-based operational report.
WITH message_metrics AS (
    SELECT
        q.queue_name,
        m.state,
        COUNT(*) AS message_count,
        AVG(m.attempts)::numeric(10,2) AS average_attempts
    FROM messaging.queue q
    JOIN messaging.message m
      ON m.queue_id = q.queue_id
    GROUP BY q.queue_name, m.state
)
SELECT
    queue_name,
    state,
    message_count,
    average_attempts
FROM message_metrics
ORDER BY queue_name, state;

-- Consumer workload report.
SELECT
    c.consumer_name,
    q.queue_name,
    COUNT(d.delivery_id) AS deliveries,
    COUNT(d.delivery_id)
        FILTER (WHERE d.result = 'ack') AS acknowledgements,
    COUNT(d.delivery_id)
        FILTER (WHERE d.result = 'retry') AS retries,
    COUNT(d.delivery_id)
        FILTER (WHERE d.result = 'reject') AS rejections
FROM messaging.consumer c
JOIN messaging.queue q
  ON q.queue_id = c.queue_id
LEFT JOIN messaging.delivery d
  ON d.consumer_id = c.consumer_id
GROUP BY
    c.consumer_name,
    q.queue_name
ORDER BY c.consumer_name;

-- Dead-letter inspection.
SELECT
    dl.dead_letter_id,
    q.queue_name,
    dl.message_id,
    dl.reason,
    dl.created_at
FROM messaging.dead_letter dl
JOIN messaging.queue q
  ON q.queue_id = dl.queue_id
ORDER BY dl.created_at;
