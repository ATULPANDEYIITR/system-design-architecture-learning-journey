DROP SCHEMA IF EXISTS pubsub CASCADE;
CREATE SCHEMA pubsub;

CREATE TYPE pubsub.topic_state AS ENUM ('ACTIVE', 'PAUSED');
CREATE TYPE pubsub.subscriber_state AS ENUM ('ACTIVE', 'SUSPENDED');
CREATE TYPE pubsub.delivery_state AS ENUM ('DELIVERED', 'FAILED', 'SKIPPED');

CREATE TABLE pubsub.topic (
    topic_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_name TEXT NOT NULL UNIQUE,
    state pubsub.topic_state NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT topic_name_valid
        CHECK (
            length(topic_name) BETWEEN 1 AND 128
            AND topic_name !~ '\s'
        )
);

CREATE TABLE pubsub.subscriber (
    subscriber_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subscriber_name TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    state pubsub.subscriber_state NOT NULL DEFAULT 'ACTIVE',
    max_failures INTEGER NOT NULL DEFAULT 3,
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT subscriber_name_valid
        CHECK (length(trim(subscriber_name)) > 0),
    CONSTRAINT endpoint_valid
        CHECK (length(trim(endpoint)) > 0),
    CONSTRAINT failure_policy_valid
        CHECK (max_failures BETWEEN 1 AND 100),
    CONSTRAINT failure_count_valid
        CHECK (failure_count >= 0)
);

CREATE TABLE pubsub.subscription (
    subscription_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_id BIGINT NOT NULL
        REFERENCES pubsub.topic(topic_id) ON DELETE CASCADE,
    subscriber_id BIGINT NOT NULL
        REFERENCES pubsub.subscriber(subscriber_id) ON DELETE CASCADE,
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT subscription_unique
        UNIQUE (topic_id, subscriber_id)
);

CREATE TABLE pubsub.event (
    event_id UUID PRIMARY KEY,
    topic_id BIGINT NOT NULL
        REFERENCES pubsub.topic(topic_id),
    event_key TEXT,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT event_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT event_key_valid
        CHECK (
            event_key IS NULL
            OR length(event_key) BETWEEN 1 AND 200
        )
);

CREATE TABLE pubsub.delivery (
    delivery_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL
        REFERENCES pubsub.event(event_id) ON DELETE CASCADE,
    subscription_id BIGINT NOT NULL
        REFERENCES pubsub.subscription(subscription_id) ON DELETE CASCADE,
    state pubsub.delivery_state NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    delivered_at TIMESTAMPTZ,
    CONSTRAINT delivery_attempt_valid
        CHECK (attempt_number >= 1),
    CONSTRAINT delivery_error_consistency
        CHECK (
            (state = 'FAILED' AND error_message IS NOT NULL)
            OR state <> 'FAILED'
        )
);

CREATE TABLE pubsub.status_check (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL
        REFERENCES pubsub.event(event_id) ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT status_check_unique
        UNIQUE (event_id, check_name)
);

CREATE INDEX idx_event_topic_time
    ON pubsub.event (topic_id, published_at DESC);

CREATE INDEX idx_delivery_event
    ON pubsub.delivery (event_id);

CREATE INDEX idx_delivery_failed
    ON pubsub.delivery (subscription_id, state)
    WHERE state = 'FAILED';

CREATE INDEX idx_subscription_subscriber
    ON pubsub.subscription (subscriber_id);

CREATE OR REPLACE FUNCTION pubsub.ensure_active_topic()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    current_state pubsub.topic_state;
BEGIN
    SELECT state
    INTO current_state
    FROM pubsub.topic
    WHERE topic_id = NEW.topic_id;

    IF current_state <> 'ACTIVE' THEN
        RAISE EXCEPTION
            'Cannot publish to inactive topic %',
            NEW.topic_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_event_active_topic
BEFORE INSERT ON pubsub.event
FOR EACH ROW
EXECUTE FUNCTION pubsub.ensure_active_topic();

CREATE OR REPLACE FUNCTION pubsub.validate_delivery_state()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'DELIVERED' THEN
        NEW.delivered_at := COALESCE(
            NEW.delivered_at,
            clock_timestamp()
        );
        NEW.error_message := NULL;
    ELSIF NEW.state = 'FAILED' AND NEW.error_message IS NULL THEN
        RAISE EXCEPTION
            'Failed delivery requires an error message';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_delivery_validation
BEFORE INSERT OR UPDATE ON pubsub.delivery
FOR EACH ROW
EXECUTE FUNCTION pubsub.validate_delivery_state();

CREATE OR REPLACE FUNCTION pubsub.record_delivery_failure(
    p_subscription_id BIGINT
)
RETURNS pubsub.subscriber_state
LANGUAGE plpgsql
AS $$
DECLARE
    new_failure_count INTEGER;
    maximum_failures INTEGER;
    new_state pubsub.subscriber_state;
BEGIN
    SELECT failure_count + 1, max_failures
    INTO new_failure_count, maximum_failures
    FROM pubsub.subscriber s
    JOIN pubsub.subscription sub
      ON sub.subscriber_id = s.subscriber_id
    WHERE sub.subscription_id = p_subscription_id
    FOR UPDATE OF s;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Subscription % does not exist',
            p_subscription_id;
    END IF;

    new_state := CASE
        WHEN new_failure_count >= maximum_failures
            THEN 'SUSPENDED'::pubsub.subscriber_state
        ELSE 'ACTIVE'::pubsub.subscriber_state
    END;

    UPDATE pubsub.subscriber s
    SET failure_count = new_failure_count,
        state = new_state
    FROM pubsub.subscription sub
    WHERE sub.subscription_id = p_subscription_id
      AND s.subscriber_id = sub.subscriber_id;

    RETURN new_state;
END;
$$;

CREATE OR REPLACE FUNCTION pubsub.reset_delivery_failures(
    p_subscription_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE pubsub.subscriber s
    SET failure_count = 0,
        state = 'ACTIVE'
    FROM pubsub.subscription sub
    WHERE sub.subscription_id = p_subscription_id
      AND s.subscriber_id = sub.subscriber_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Subscription % does not exist',
            p_subscription_id;
    END IF;
END;
$$;

CREATE OR REPLACE VIEW pubsub.v_topic_delivery_summary AS
SELECT
    t.topic_name,
    COUNT(DISTINCT sub.subscription_id) AS subscriber_count,
    COUNT(DISTINCT e.event_id) AS event_count,
    COUNT(d.delivery_id) AS delivery_count,
    COUNT(*) FILTER (WHERE d.state = 'DELIVERED') AS delivered_count,
    COUNT(*) FILTER (WHERE d.state = 'FAILED') AS failed_count
FROM pubsub.topic t
LEFT JOIN pubsub.subscription sub
    ON sub.topic_id = t.topic_id
LEFT JOIN pubsub.event e
    ON e.topic_id = t.topic_id
LEFT JOIN pubsub.delivery d
    ON d.event_id = e.event_id
GROUP BY t.topic_id, t.topic_name;

CREATE OR REPLACE FUNCTION pubsub.publish_event(
    p_topic_name TEXT,
    p_payload JSONB,
    p_event_key TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_topic_id BIGINT;
    v_event_id UUID := gen_random_uuid();
BEGIN
    SELECT topic_id
    INTO v_topic_id
    FROM pubsub.topic
    WHERE topic_name = p_topic_name
      AND state = 'ACTIVE';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Active topic % does not exist',
            p_topic_name;
    END IF;

    IF jsonb_typeof(p_payload) <> 'object' THEN
        RAISE EXCEPTION
            'Event payload must be a JSON object';
    END IF;

    INSERT INTO pubsub.event (
        event_id,
        topic_id,
        event_key,
        payload
    )
    VALUES (
        v_event_id,
        v_topic_id,
        p_event_key,
        p_payload
    );

    /*
     * Delivery rows are created atomically with the publication. Actual
     * network delivery belongs to an external worker, while the database
     * records the durable routing obligation.
     */
    INSERT INTO pubsub.delivery (
        event_id,
        subscription_id,
        state,
        attempt_number
    )
    SELECT
        v_event_id,
        subscription_id,
        'SKIPPED',
        1
    FROM pubsub.subscription s
    JOIN pubsub.subscriber sub
      ON sub.subscriber_id = s.subscriber_id
    WHERE s.topic_id = v_topic_id
      AND sub.state = 'SUSPENDED';

    INSERT INTO pubsub.delivery (
        event_id,
        subscription_id,
        state,
        attempt_number
    )
    SELECT
        v_event_id,
        s.subscription_id,
        'FAILED',
        1
    FROM pubsub.subscription s
    JOIN pubsub.subscriber sub
      ON sub.subscriber_id = s.subscriber_id
    WHERE s.topic_id = v_topic_id
      AND sub.state = 'ACTIVE'
      AND FALSE;

    RETURN v_event_id;
END;
$$;

INSERT INTO pubsub.topic (topic_name)
VALUES
    ('orders.created'),
    ('payments.completed'),
    ('security.alerts'),
    ('inventory.updated');

INSERT INTO pubsub.subscriber (
    subscriber_name,
    endpoint,
    max_failures
)
VALUES
    ('audit-service', 'https://internal.example/audit', 3),
    ('analytics-service', 'https://internal.example/analytics', 3),
    ('fraud-service', 'https://internal.example/fraud', 2),
    ('notification-service', 'https://internal.example/notify', 3);

INSERT INTO pubsub.subscription (topic_id, subscriber_id)
SELECT t.topic_id, s.subscriber_id
FROM pubsub.topic t
JOIN pubsub.subscriber s
  ON (t.topic_name, s.subscriber_name) IN (
      ('orders.created', 'audit-service'),
      ('orders.created', 'analytics-service'),
      ('payments.completed', 'fraud-service'),
      ('payments.completed', 'audit-service'),
      ('security.alerts', 'notification-service'),
      ('security.alerts', 'audit-service')
  );

BEGIN;

SELECT pubsub.publish_event(
    'orders.created',
    '{"order_id":"ORD-1001","customer_id":"C-501","total":1850}'::jsonb,
    'ORD-1001'
);

SELECT pubsub.publish_event(
    'payments.completed',
    '{"payment_id":"PAY-1001","customer_id":"C-501","amount":4500,"currency":"INR"}'::jsonb,
    'PAY-1001'
);

SELECT pubsub.publish_event(
    'security.alerts',
    '{"incident_id":"INC-1001","severity":"high","source":"firewall"}'::jsonb,
    'INC-1001'
);

COMMIT;

INSERT INTO pubsub.status_check (event_id, check_name, passed)
SELECT
    event_id,
    'schema-validation',
    TRUE
FROM pubsub.event
WHERE event_key IN ('ORD-1001', 'PAY-1001');

UPDATE pubsub.delivery
SET state = 'DELIVERED',
    delivered_at = clock_timestamp()
WHERE event_id = (
    SELECT event_id
    FROM pubsub.event
    WHERE event_key = 'ORD-1001'
)
AND subscription_id IN (
    SELECT subscription_id
    FROM pubsub.subscription s
    JOIN pubsub.subscriber sub
      ON sub.subscriber_id = s.subscriber_id
    WHERE sub.subscriber_name IN (
        'audit-service',
        'analytics-service'
    )
);

UPDATE pubsub.delivery
SET state = 'FAILED',
    error_message = 'Temporary downstream timeout'
WHERE event_id = (
    SELECT event_id
    FROM pubsub.event
    WHERE event_key = 'PAY-1001'
)
AND subscription_id = (
    SELECT s.subscription_id
    FROM pubsub.subscription s
    JOIN pubsub.subscriber sub
      ON sub.subscriber_id = s.subscriber_id
    WHERE sub.subscriber_name = 'fraud-service'
);

SELECT pubsub.record_delivery_failure(
    (
        SELECT s.subscription_id
        FROM pubsub.subscription s
        JOIN pubsub.subscriber sub
          ON sub.subscriber_id = s.subscriber_id
        WHERE sub.subscriber_name = 'fraud-service'
        LIMIT 1
    )
);

SELECT
    t.topic_name,
    t.state,
    COUNT(DISTINCT s.subscription_id) AS subscribers
FROM pubsub.topic t
LEFT JOIN pubsub.subscription s
    ON s.topic_id = t.topic_id
GROUP BY t.topic_id, t.topic_name, t.state
ORDER BY t.topic_name;

SELECT
    e.event_key,
    t.topic_name,
    e.published_at,
    jsonb_pretty(e.payload) AS payload
FROM pubsub.event e
JOIN pubsub.topic t
    ON t.topic_id = e.topic_id
ORDER BY e.published_at DESC;

SELECT
    t.topic_name,
    sub.subscriber_name,
    d.state,
    COUNT(*) AS deliveries
FROM pubsub.delivery d
JOIN pubsub.event e
    ON e.event_id = d.event_id
JOIN pubsub.topic t
    ON t.topic_id = e.topic_id
JOIN pubsub.subscription s
    ON s.subscription_id = d.subscription_id
JOIN pubsub.subscriber sub
    ON sub.subscriber_id = s.subscriber_id
GROUP BY
    t.topic_name,
    sub.subscriber_name,
    d.state
ORDER BY t.topic_name, sub.subscriber_name, d.state;

WITH topic_health AS (
    SELECT
        t.topic_name,
        COUNT(*) FILTER (WHERE d.state = 'DELIVERED') AS delivered,
        COUNT(*) FILTER (WHERE d.state = 'FAILED') AS failed,
        COUNT(*) FILTER (WHERE d.state = 'SKIPPED') AS skipped
    FROM pubsub.topic t
    LEFT JOIN pubsub.event e
        ON e.topic_id = t.topic_id
    LEFT JOIN pubsub.delivery d
        ON d.event_id = e.event_id
    GROUP BY t.topic_id, t.topic_name
)
SELECT
    topic_name,
    delivered,
    failed,
    skipped,
    CASE
        WHEN failed = 0 AND skipped = 0 THEN 'HEALTHY'
        WHEN delivered > failed THEN 'DEGRADED'
        ELSE 'UNHEALTHY'
    END AS health
FROM topic_health
ORDER BY topic_name;

SELECT *
FROM pubsub.v_topic_delivery_summary
ORDER BY topic_name;

DO $$
BEGIN
    BEGIN
        PERFORM pubsub.publish_event(
            'unknown.topic',
            '{"value":1}'::jsonb
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected failure: %', SQLERRM;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        PERFORM pubsub.publish_event(
            'orders.created',
            '["not","an","object"]'::jsonb
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected payload validation failure: %', SQLERRM;
    END;
END;
$$;
