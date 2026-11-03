DROP SCHEMA IF EXISTS event_demo CASCADE;

CREATE SCHEMA event_demo;

SET search_path TO event_demo;

CREATE TYPE event_status AS ENUM (
    'PUBLISHED',
    'PROCESSING',
    'PROCESSED',
    'FAILED',
    'DEAD_LETTERED'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE event_types (
    event_type_id SMALLSERIAL PRIMARY KEY,
    event_name TEXT NOT NULL UNIQUE
);

CREATE TABLE producers (
    producer_id BIGSERIAL PRIMARY KEY,
    producer_name TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE consumers (
    consumer_id BIGSERIAL PRIMARY KEY,
    consumer_name TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    customer_id TEXT NOT NULL CHECK (length(trim(customer_id)) > 0),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    status TEXT NOT NULL CHECK (
        status IN ('CREATED', 'CONFIRMED', 'CANCELLED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE events (
    event_id UUID PRIMARY KEY,
    event_type_id SMALLINT NOT NULL REFERENCES event_types(event_type_id),
    producer_id BIGINT NOT NULL REFERENCES producers(producer_id),
    aggregate_id UUID NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    status event_status NOT NULL DEFAULT 'PUBLISHED',
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    UNIQUE (aggregate_id, version)
);

CREATE TABLE subscriptions (
    consumer_id BIGINT NOT NULL REFERENCES consumers(consumer_id),
    event_type_id SMALLINT NOT NULL REFERENCES event_types(event_type_id),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (consumer_id, event_type_id)
);

CREATE TABLE event_deliveries (
    event_id UUID NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    consumer_id BIGINT NOT NULL REFERENCES consumers(consumer_id),
    status event_status NOT NULL DEFAULT 'PUBLISHED',
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    first_attempt_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (event_id, consumer_id)
);

CREATE INDEX idx_events_type_status
    ON events(event_type_id, status, occurred_at);

CREATE INDEX idx_events_aggregate
    ON events(aggregate_id, version);

CREATE INDEX idx_events_payload
    ON events USING GIN (payload);

CREATE INDEX idx_deliveries_consumer_status
    ON event_deliveries(consumer_id, status);

CREATE INDEX idx_orders_status
    ON orders(status, created_at);

CREATE OR REPLACE FUNCTION validate_event_payload()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.payload IS NULL
       OR jsonb_typeof(NEW.payload) <> 'object' THEN
        RAISE EXCEPTION 'Event payload must be a JSON object';
    END IF;

    IF NEW.aggregate_id IS NULL THEN
        RAISE EXCEPTION 'aggregate_id is required';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_event_payload
BEFORE INSERT OR UPDATE ON events
FOR EACH ROW
EXECUTE FUNCTION validate_event_payload();

CREATE OR REPLACE FUNCTION create_deliveries_for_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO event_deliveries (
        event_id,
        consumer_id
    )
    SELECT
        NEW.event_id,
        s.consumer_id
    FROM subscriptions s
    JOIN consumers c
      ON c.consumer_id = s.consumer_id
    WHERE s.event_type_id = NEW.event_type_id
      AND s.enabled
      AND c.active
    ON CONFLICT (event_id, consumer_id) DO NOTHING;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_create_deliveries
AFTER INSERT ON events
FOR EACH ROW
EXECUTE FUNCTION create_deliveries_for_event();

CREATE OR REPLACE FUNCTION publish_event(
    p_event_type TEXT,
    p_producer TEXT,
    p_aggregate_id UUID,
    p_payload JSONB,
    p_version INTEGER DEFAULT 1
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_id UUID := gen_random_uuid();
    v_event_type_id SMALLINT;
    v_producer_id BIGINT;
BEGIN
    SELECT event_type_id
    INTO v_event_type_id
    FROM event_types
    WHERE event_name = p_event_type;

    IF v_event_type_id IS NULL THEN
        RAISE EXCEPTION 'Unknown event type: %', p_event_type;
    END IF;

    SELECT producer_id
    INTO v_producer_id
    FROM producers
    WHERE producer_name = p_producer
      AND active;

    IF v_producer_id IS NULL THEN
        RAISE EXCEPTION 'Inactive or unknown producer: %', p_producer;
    END IF;

    INSERT INTO events (
        event_id,
        event_type_id,
        producer_id,
        aggregate_id,
        payload,
        version
    )
    VALUES (
        v_event_id,
        v_event_type_id,
        v_producer_id,
        p_aggregate_id,
        p_payload,
        p_version
    );

    RETURN v_event_id;
END;
$$;

CREATE OR REPLACE FUNCTION process_delivery(
    p_event_id UUID,
    p_consumer_name TEXT,
    p_success BOOLEAN,
    p_error TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_consumer_id BIGINT;
BEGIN
    SELECT consumer_id
    INTO v_consumer_id
    FROM consumers
    WHERE consumer_name = p_consumer_name;

    IF v_consumer_id IS NULL THEN
        RAISE EXCEPTION 'Unknown consumer: %', p_consumer_name;
    END IF;

    UPDATE event_deliveries
    SET
        attempts = attempts + 1,
        first_attempt_at = COALESCE(
            first_attempt_at,
            clock_timestamp()
        ),
        status = CASE
            WHEN p_success THEN 'PROCESSED'::event_status
            ELSE 'FAILED'::event_status
        END,
        last_error = CASE
            WHEN p_success THEN NULL
            ELSE p_error
        END,
        processed_at = CASE
            WHEN p_success THEN clock_timestamp()
            ELSE NULL
        END
    WHERE event_id = p_event_id
      AND consumer_id = v_consumer_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Delivery does not exist for event % and consumer %',
            p_event_id,
            p_consumer_name;
    END IF;
END;
$$;

INSERT INTO repositories (repository_name)
VALUES
    ('order-platform');

INSERT INTO event_types (event_name)
VALUES
    ('order.created'),
    ('payment.authorized'),
    ('order.confirmed'),
    ('order.cancelled');

INSERT INTO producers (producer_name)
VALUES
    ('order-service'),
    ('payment-service'),
    ('workflow-service');

INSERT INTO consumers (consumer_name)
VALUES
    ('payment-service'),
    ('notification-service'),
    ('analytics-service'),
    ('audit-service');

INSERT INTO subscriptions (
    consumer_id,
    event_type_id
)
SELECT
    c.consumer_id,
    e.event_type_id
FROM consumers c
CROSS JOIN event_types e
WHERE
    (c.consumer_name = 'payment-service'
     AND e.event_name = 'order.created')
 OR (c.consumer_name = 'notification-service'
     AND e.event_name IN ('order.created', 'order.confirmed'))
 OR (c.consumer_name = 'analytics-service')
 OR (c.consumer_name = 'audit-service'
     AND e.event_name = 'order.created');

INSERT INTO orders (
    order_id,
    repository_id,
    customer_id,
    amount,
    status
)
VALUES
    (
        '11111111-1111-1111-1111-111111111111',
        1,
        'customer-1001',
        1499.50,
        'CREATED'
    ),
    (
        '22222222-2222-2222-2222-222222222222',
        1,
        'customer-1002',
        250.00,
        'CONFIRMED'
    ),
    (
        '33333333-3333-3333-3333-333333333333',
        1,
        'customer-1003',
        75.00,
        'CANCELLED'
    );

BEGIN;

SELECT publish_event(
    'order.created',
    'order-service',
    '11111111-1111-1111-1111-111111111111',
    jsonb_build_object(
        'customer_id', 'customer-1001',
        'amount', 1499.50
    ),
    1
);

SELECT publish_event(
    'order.confirmed',
    'workflow-service',
    '22222222-2222-2222-2222-222222222222',
    jsonb_build_object(
        'confirmed_by', 'workflow-service'
    ),
    1
);

COMMIT;

BEGIN;

SELECT process_delivery(
    event_id,
    'payment-service',
    TRUE
)
FROM events
WHERE aggregate_id =
    '11111111-1111-1111-1111-111111111111'
  AND event_type_id = (
      SELECT event_type_id
      FROM event_types
      WHERE event_name = 'order.created'
  );

COMMIT;

-- Retrieve the event stream for one aggregate.
SELECT
    e.event_id,
    t.event_name,
    p.producer_name,
    e.aggregate_id,
    e.payload,
    e.status,
    e.occurred_at
FROM events e
JOIN event_types t
  ON t.event_type_id = e.event_type_id
JOIN producers p
  ON p.producer_id = e.producer_id
WHERE e.aggregate_id =
    '11111111-1111-1111-1111-111111111111'
ORDER BY e.version;

-- Show consumers waiting for processing.
SELECT
    c.consumer_name,
    COUNT(*) AS pending_deliveries
FROM event_deliveries d
JOIN consumers c
  ON c.consumer_id = d.consumer_id
WHERE d.status IN ('PUBLISHED', 'FAILED')
GROUP BY c.consumer_name
ORDER BY pending_deliveries DESC;

-- Aggregate event volume by type.
SELECT
    t.event_name,
    COUNT(*) AS event_count
FROM events e
JOIN event_types t
  ON t.event_type_id = e.event_type_id
GROUP BY t.event_name
ORDER BY event_count DESC, t.event_name;

-- Validate that every active subscription has corresponding deliveries.
SELECT
    c.consumer_name,
    t.event_name,
    COUNT(d.event_id) AS delivery_count
FROM subscriptions s
JOIN consumers c
  ON c.consumer_id = s.consumer_id
JOIN event_types t
  ON t.event_type_id = s.event_type_id
LEFT JOIN event_deliveries d
  ON d.consumer_id = s.consumer_id
GROUP BY c.consumer_name, t.event_name
ORDER BY c.consumer_name, t.event_name;

-- Identify failed deliveries requiring operational attention.
SELECT
    d.event_id,
    c.consumer_name,
    d.attempts,
    d.last_error,
    d.first_attempt_at
FROM event_deliveries d
JOIN consumers c
  ON c.consumer_id = d.consumer_id
WHERE d.status = 'FAILED'
ORDER BY d.first_attempt_at;

-- Determine whether an event has been successfully processed
-- by every active consumer subscribed to its event type.
WITH required_deliveries AS (
    SELECT
        e.event_id,
        COUNT(s.consumer_id) AS required_count
    FROM events e
    JOIN subscriptions s
      ON s.event_type_id = e.event_type_id
     AND s.enabled
    JOIN consumers c
      ON c.consumer_id = s.consumer_id
     AND c.active
    GROUP BY e.event_id
),
completed_deliveries AS (
    SELECT
        event_id,
        COUNT(*) FILTER (
            WHERE status = 'PROCESSED'
        ) AS processed_count
    FROM event_deliveries
    GROUP BY event_id
)
SELECT
    r.event_id,
    r.required_count,
    COALESCE(c.processed_count, 0) AS processed_count,
    CASE
        WHEN COALESCE(c.processed_count, 0) = r.required_count
        THEN 'ELIGIBLE'
        ELSE 'WAITING'
    END AS delivery_state
FROM required_deliveries r
LEFT JOIN completed_deliveries c
  ON c.event_id = r.event_id
ORDER BY r.event_id;

-- Transactional state change plus event publication.
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id =
    '11111111-1111-1111-1111-111111111111'
  AND status = 'CREATED';

SELECT publish_event(
    'order.confirmed',
    'workflow-service',
    '11111111-1111-1111-1111-111111111111',
    jsonb_build_object(
        'confirmed_by', 'workflow-service'
    ),
    2
);

COMMIT;

-- Demonstrate JSONB-based event analysis.
SELECT
    e.aggregate_id,
    e.payload ->> 'customer_id' AS customer_id,
    (e.payload ->> 'amount')::NUMERIC AS amount
FROM events e
JOIN event_types t
  ON t.event_type_id = e.event_type_id
WHERE t.event_name = 'order.created'
  AND e.payload ? 'amount'
ORDER BY amount DESC;

-- Event-driven systems require explicit operational boundaries:
-- 1. Database transactions protect local state changes.
-- 2. Durable brokers protect events from process failure.
-- 3. Consumers must be idempotent because duplicate delivery is possible.
-- 4. Failed deliveries require retry limits and dead-letter handling.
-- 5. Payloads should avoid secrets and unnecessary sensitive information.
