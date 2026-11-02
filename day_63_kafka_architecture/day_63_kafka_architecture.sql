DROP SCHEMA IF EXISTS kafka_lab CASCADE;
CREATE SCHEMA kafka_lab;

SET search_path TO kafka_lab, public;

CREATE TYPE broker_state AS ENUM ('ONLINE', 'OFFLINE');
CREATE TYPE consumer_state AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TYPE review_status AS ENUM ('PENDING', 'PASS', 'FAIL');
CREATE TYPE message_status AS ENUM ('AVAILABLE', 'PROCESSED');

CREATE TABLE brokers (
    broker_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    broker_name text NOT NULL UNIQUE,
    host_name text NOT NULL UNIQUE,
    state broker_state NOT NULL DEFAULT 'ONLINE',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE topics (
    topic_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_name text NOT NULL UNIQUE,
    partition_count integer NOT NULL CHECK (partition_count > 0),
    replication_factor integer NOT NULL CHECK (replication_factor > 0),
    min_insync_replicas integer NOT NULL CHECK (min_insync_replicas > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (min_insync_replicas <= replication_factor)
);

CREATE TABLE topic_partitions (
    topic_id bigint NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    partition_id integer NOT NULL CHECK (partition_id >= 0),
    leader_broker_id integer NOT NULL REFERENCES brokers(broker_id),
    high_watermark bigint NOT NULL DEFAULT -1 CHECK (high_watermark >= -1),
    PRIMARY KEY (topic_id, partition_id)
);

CREATE TABLE partition_replicas (
    topic_id bigint NOT NULL,
    partition_id integer NOT NULL,
    broker_id integer NOT NULL REFERENCES brokers(broker_id),
    replica_order integer NOT NULL CHECK (replica_order >= 0),
    PRIMARY KEY (topic_id, partition_id, broker_id),
    UNIQUE (topic_id, partition_id, replica_order),
    FOREIGN KEY (topic_id, partition_id)
        REFERENCES topic_partitions(topic_id, partition_id)
        ON DELETE CASCADE
);

CREATE TABLE messages (
    message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id bigint NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    partition_id integer NOT NULL,
    message_offset bigint NOT NULL CHECK (message_offset >= 0),
    message_key text NOT NULL,
    message_value jsonb NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    leader_broker_id integer NOT NULL REFERENCES brokers(broker_id),
    UNIQUE (topic_id, partition_id, message_offset),
    FOREIGN KEY (topic_id, partition_id)
        REFERENCES topic_partitions(topic_id, partition_id)
        ON DELETE CASCADE
);

CREATE TABLE consumer_groups (
    group_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE consumers (
    consumer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    consumer_name text NOT NULL UNIQUE,
    group_id bigint NOT NULL REFERENCES consumer_groups(group_id) ON DELETE CASCADE,
    state consumer_state NOT NULL DEFAULT 'ACTIVE',
    joined_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE consumer_subscriptions (
    consumer_id bigint NOT NULL REFERENCES consumers(consumer_id) ON DELETE CASCADE,
    topic_id bigint NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    PRIMARY KEY (consumer_id, topic_id)
);

CREATE TABLE consumer_assignments (
    consumer_id bigint NOT NULL REFERENCES consumers(consumer_id) ON DELETE CASCADE,
    topic_id bigint NOT NULL,
    partition_id integer NOT NULL,
    next_offset bigint NOT NULL DEFAULT 0 CHECK (next_offset >= 0),
    assigned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_id, topic_id, partition_id),
    FOREIGN KEY (topic_id, partition_id)
        REFERENCES topic_partitions(topic_id, partition_id)
        ON DELETE CASCADE
);

CREATE TABLE committed_offsets (
    group_id bigint NOT NULL REFERENCES consumer_groups(group_id) ON DELETE CASCADE,
    topic_id bigint NOT NULL,
    partition_id integer NOT NULL,
    committed_offset bigint NOT NULL CHECK (committed_offset >= 0),
    committed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (group_id, topic_id, partition_id),
    FOREIGN KEY (topic_id, partition_id)
        REFERENCES topic_partitions(topic_id, partition_id)
        ON DELETE CASCADE
);

CREATE TABLE message_processing (
    consumer_id bigint NOT NULL REFERENCES consumers(consumer_id) ON DELETE CASCADE,
    message_id uuid NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    status message_status NOT NULL DEFAULT 'AVAILABLE',
    processed_at timestamptz,
    PRIMARY KEY (consumer_id, message_id)
);

CREATE TABLE status_checks (
    status_check_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_id bigint NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    partition_id integer NOT NULL,
    check_name text NOT NULL,
    status review_status NOT NULL DEFAULT 'PENDING',
    checked_at timestamptz,
    UNIQUE (topic_id, partition_id, check_name),
    FOREIGN KEY (topic_id, partition_id)
        REFERENCES topic_partitions(topic_id, partition_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_messages_topic_partition_offset
    ON messages(topic_id, partition_id, message_offset);

CREATE INDEX idx_messages_published_at
    ON messages(published_at);

CREATE INDEX idx_consumer_assignments_topic_partition
    ON consumer_assignments(topic_id, partition_id);

CREATE INDEX idx_replicas_broker
    ON partition_replicas(broker_id);

CREATE INDEX idx_committed_offsets_topic_partition
    ON committed_offsets(topic_id, partition_id);

CREATE OR REPLACE FUNCTION validate_topic_partition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    configured_partitions integer;
BEGIN
    SELECT partition_count
    INTO configured_partitions
    FROM topics
    WHERE topic_id = NEW.topic_id;

    IF configured_partitions IS NULL THEN
        RAISE EXCEPTION 'Topic % does not exist', NEW.topic_id;
    END IF;

    IF NEW.partition_id >= configured_partitions THEN
        RAISE EXCEPTION
            'Partition % exceeds topic partition count %',
            NEW.partition_id,
            configured_partitions;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_topic_partition
BEFORE INSERT OR UPDATE ON topic_partitions
FOR EACH ROW
EXECUTE FUNCTION validate_topic_partition();

CREATE OR REPLACE FUNCTION validate_replica()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM topic_partitions
        WHERE topic_id = NEW.topic_id
          AND partition_id = NEW.partition_id
    ) THEN
        RAISE EXCEPTION
            'Replica references missing partition %.%',
            NEW.topic_id,
            NEW.partition_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_replica
BEFORE INSERT OR UPDATE ON partition_replicas
FOR EACH ROW
EXECUTE FUNCTION validate_replica();

CREATE OR REPLACE FUNCTION update_partition_high_watermark()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE topic_partitions
    SET high_watermark =
        GREATEST(high_watermark, NEW.message_offset)
    WHERE topic_id = NEW.topic_id
      AND partition_id = NEW.partition_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_update_high_watermark
AFTER INSERT ON messages
FOR EACH ROW
EXECUTE FUNCTION update_partition_high_watermark();

CREATE OR REPLACE FUNCTION enforce_offset_monotonicity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    existing_offset bigint;
BEGIN
    SELECT committed_offset
    INTO existing_offset
    FROM committed_offsets
    WHERE group_id = NEW.group_id
      AND topic_id = NEW.topic_id
      AND partition_id = NEW.partition_id;

    IF existing_offset IS NOT NULL
       AND NEW.committed_offset < existing_offset THEN
        RAISE EXCEPTION
            'Offset regression from % to %',
            existing_offset,
            NEW.committed_offset;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_offset_monotonicity
BEFORE INSERT OR UPDATE ON committed_offsets
FOR EACH ROW
EXECUTE FUNCTION enforce_offset_monotonicity();

CREATE OR REPLACE FUNCTION in_sync_replica_count(
    requested_topic_id bigint,
    requested_partition_id integer
)
RETURNS integer
LANGUAGE sql
STABLE
AS $$
    SELECT count(*)::integer
    FROM partition_replicas pr
    JOIN brokers b
      ON b.broker_id = pr.broker_id
    WHERE pr.topic_id = requested_topic_id
      AND pr.partition_id = requested_partition_id
      AND b.state = 'ONLINE';
$$;

CREATE OR REPLACE FUNCTION publish_message(
    requested_topic_id bigint,
    requested_partition_id integer,
    requested_key text,
    requested_value jsonb,
    requested_leader_broker_id integer
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    required_isr integer;
    current_isr integer;
    next_offset bigint;
BEGIN
    IF requested_key IS NULL OR btrim(requested_key) = '' THEN
        RAISE EXCEPTION 'Message key cannot be empty';
    END IF;

    SELECT min_insync_replicas
    INTO required_isr
    FROM topics
    WHERE topic_id = requested_topic_id;

    IF required_isr IS NULL THEN
        RAISE EXCEPTION 'Unknown topic %', requested_topic_id;
    END IF;

    current_isr := in_sync_replica_count(
        requested_topic_id,
        requested_partition_id
    );

    IF current_isr < required_isr THEN
        RAISE EXCEPTION
            'Write rejected: ISR % is below required %',
            current_isr,
            required_isr;
    END IF;

    SELECT COALESCE(
        MAX(message_offset) + 1,
        0
    )
    INTO next_offset
    FROM messages
    WHERE topic_id = requested_topic_id
      AND partition_id = requested_partition_id;

    INSERT INTO messages (
        topic_id,
        partition_id,
        message_offset,
        message_key,
        message_value,
        leader_broker_id
    )
    VALUES (
        requested_topic_id,
        requested_partition_id,
        next_offset,
        requested_key,
        requested_value,
        requested_leader_broker_id
    );

    RETURN next_offset;
END;
$$;

INSERT INTO brokers (
    broker_name,
    host_name,
    state
)
VALUES
    ('broker-1', 'kafka-1.internal', 'ONLINE'),
    ('broker-2', 'kafka-2.internal', 'ONLINE'),
    ('broker-3', 'kafka-3.internal', 'ONLINE');

INSERT INTO topics (
    topic_name,
    partition_count,
    replication_factor,
    min_insync_replicas
)
VALUES
    ('orders', 3, 3, 2),
    ('payments', 2, 3, 2);

INSERT INTO topic_partitions (
    topic_id,
    partition_id,
    leader_broker_id
)
SELECT
    t.topic_id,
    p.partition_id,
    ((p.partition_id % 3) + 1)
FROM topics t
CROSS JOIN LATERAL generate_series(
    0,
    t.partition_count - 1
) AS p(partition_id);

INSERT INTO partition_replicas (
    topic_id,
    partition_id,
    broker_id,
    replica_order
)
SELECT
    tp.topic_id,
    tp.partition_id,
    ((tp.partition_id + r.replica_order) % 3) + 1,
    r.replica_order
FROM topic_partitions tp
CROSS JOIN LATERAL generate_series(
    0,
    (
        SELECT replication_factor - 1
        FROM topics t
        WHERE t.topic_id = tp.topic_id
    )
) AS r(replica_order);

INSERT INTO consumer_groups (
    group_name
)
VALUES
    ('order-processing'),
    ('payment-processing');

INSERT INTO consumers (
    consumer_name,
    group_id
)
SELECT
    'orders-worker-1',
    group_id
FROM consumer_groups
WHERE group_name = 'order-processing';

INSERT INTO consumers (
    consumer_name,
    group_id
)
SELECT
    'orders-worker-2',
    group_id
FROM consumer_groups
WHERE group_name = 'order-processing';

INSERT INTO consumers (
    consumer_name,
    group_id
)
SELECT
    'payments-worker-1',
    group_id
FROM consumer_groups
WHERE group_name = 'payment-processing';

INSERT INTO consumer_subscriptions (
    consumer_id,
    topic_id
)
SELECT
    c.consumer_id,
    t.topic_id
FROM consumers c
JOIN consumer_groups g
  ON g.group_id = c.group_id
JOIN topics t
  ON (
      g.group_name = 'order-processing'
      AND t.topic_name = 'orders'
  )
  OR (
      g.group_name = 'payment-processing'
      AND t.topic_name = 'payments'
  );

INSERT INTO consumer_assignments (
    consumer_id,
    topic_id,
    partition_id
)
SELECT
    c.consumer_id,
    t.topic_id,
    tp.partition_id
FROM consumers c
JOIN consumer_subscriptions cs
  ON cs.consumer_id = c.consumer_id
JOIN topics t
  ON t.topic_id = cs.topic_id
JOIN topic_partitions tp
  ON tp.topic_id = t.topic_id
WHERE c.consumer_name = 'orders-worker-1'
  AND tp.partition_id = 0;

INSERT INTO consumer_assignments (
    consumer_id,
    topic_id,
    partition_id
)
SELECT
    c.consumer_id,
    t.topic_id,
    tp.partition_id
FROM consumers c
JOIN consumer_subscriptions cs
  ON cs.consumer_id = c.consumer_id
JOIN topics t
  ON t.topic_id = cs.topic_id
JOIN topic_partitions tp
  ON tp.topic_id = t.topic_id
WHERE c.consumer_name = 'orders-worker-2'
  AND tp.partition_id IN (1, 2);

INSERT INTO status_checks (
    topic_id,
    partition_id,
    check_name,
    status,
    checked_at
)
SELECT
    t.topic_id,
    tp.partition_id,
    'replication-health',
    'PASS',
    now()
FROM topics t
JOIN topic_partitions tp
  ON tp.topic_id = t.topic_id;

INSERT INTO status_checks (
    topic_id,
    partition_id,
    check_name,
    status,
    checked_at
)
SELECT
    t.topic_id,
    tp.partition_id,
    'consumer-readiness',
    CASE
        WHEN tp.partition_id = 2
            THEN 'FAIL'::review_status
        ELSE 'PASS'::review_status
    END,
    now()
FROM topics t
JOIN topic_partitions tp
  ON tp.topic_id = t.topic_id
WHERE t.topic_name = 'orders';

BEGIN;

SELECT publish_message(
    (
        SELECT topic_id
        FROM topics
        WHERE topic_name = 'orders'
    ),
    0,
    'customer-100',
    '{"order_id":"O-100","amount":1250}'::jsonb,
    1
);

SELECT publish_message(
    (
        SELECT topic_id
        FROM topics
        WHERE topic_name = 'orders'
    ),
    1,
    'customer-101',
    '{"order_id":"O-101","amount":850}'::jsonb,
    2
);

SELECT publish_message(
    (
        SELECT topic_id
        FROM topics
        WHERE topic_name = 'orders'
    ),
    2,
    'customer-102',
    '{"order_id":"O-102","amount":2200}'::jsonb,
    3
);

COMMIT;

BEGIN;

UPDATE brokers
SET state = 'OFFLINE'
WHERE broker_id = 1;

UPDATE topic_partitions
SET leader_broker_id = 2
WHERE leader_broker_id = 1
  AND EXISTS (
      SELECT 1
      FROM partition_replicas pr
      JOIN brokers b
        ON b.broker_id = pr.broker_id
      WHERE pr.topic_id = topic_partitions.topic_id
        AND pr.partition_id = topic_partitions.partition_id
        AND pr.broker_id = 2
        AND b.state = 'ONLINE'
  );

COMMIT;

UPDATE brokers
SET state = 'ONLINE'
WHERE broker_id = 1;

INSERT INTO committed_offsets (
    group_id,
    topic_id,
    partition_id,
    committed_offset
)
SELECT
    g.group_id,
    t.topic_id,
    tp.partition_id,
    CASE
        WHEN tp.partition_id = 0 THEN 1
        WHEN tp.partition_id = 1 THEN 1
        ELSE 0
    END
FROM consumer_groups g
JOIN topics t
  ON t.topic_name = 'orders'
JOIN topic_partitions tp
  ON tp.topic_id = t.topic_id
WHERE g.group_name = 'order-processing'
ON CONFLICT (group_id, topic_id, partition_id)
DO UPDATE
SET committed_offset =
        GREATEST(
            committed_offsets.committed_offset,
            EXCLUDED.committed_offset
        ),
    committed_at = now();

INSERT INTO message_processing (
    consumer_id,
    message_id,
    status,
    processed_at
)
SELECT
    c.consumer_id,
    m.message_id,
    'PROCESSED',
    now()
FROM consumers c
JOIN messages m
  ON m.topic_id = (
      SELECT topic_id
      FROM topics
      WHERE topic_name = 'orders'
  )
WHERE c.consumer_name = 'orders-worker-1'
  AND m.partition_id = 0
  AND m.message_offset = 0
ON CONFLICT (consumer_id, message_id)
DO UPDATE
SET status = 'PROCESSED',
    processed_at = now();

SELECT
    t.topic_name,
    tp.partition_id,
    tp.leader_broker_id,
    tp.high_watermark,
    COUNT(pr.broker_id) AS replica_count,
    COUNT(*) FILTER (
        WHERE b.state = 'ONLINE'
    ) AS online_replica_count
FROM topics t
JOIN topic_partitions tp
  ON tp.topic_id = t.topic_id
JOIN partition_replicas pr
  ON pr.topic_id = tp.topic_id
 AND pr.partition_id = tp.partition_id
JOIN brokers b
  ON b.broker_id = pr.broker_id
GROUP BY
    t.topic_name,
    tp.partition_id,
    tp.leader_broker_id,
    tp.high_watermark
ORDER BY
    t.topic_name,
    tp.partition_id;

SELECT
    t.topic_name,
    m.partition_id,
    m.message_offset,
    m.message_key,
    m.message_value,
    m.published_at
FROM messages m
JOIN topics t
  ON t.topic_id = m.topic_id
WHERE t.topic_name = 'orders'
ORDER BY
    m.partition_id,
    m.message_offset;

SELECT
    g.group_name,
    t.topic_name,
    co.partition_id,
    co.committed_offset,
    tp.high_watermark,
    GREATEST(
        tp.high_watermark + 1 -
        co.committed_offset,
        0
    ) AS consumer_lag
FROM committed_offsets co
JOIN consumer_groups g
  ON g.group_id = co.group_id
JOIN topics t
  ON t.topic_id = co.topic_id
JOIN topic_partitions tp
  ON tp.topic_id = co.topic_id
 AND tp.partition_id = co.partition_id
ORDER BY
    g.group_name,
    t.topic_name,
    co.partition_id;

WITH partition_health AS (
    SELECT
        tp.topic_id,
        tp.partition_id,
        COUNT(*) FILTER (
            WHERE b.state = 'ONLINE'
        ) AS online_replicas,
        t.min_insync_replicas
    FROM topic_partitions tp
    JOIN topics t
      ON t.topic_id = tp.topic_id
    JOIN partition_replicas pr
      ON pr.topic_id = tp.topic_id
     AND pr.partition_id = tp.partition_id
    JOIN brokers b
      ON b.broker_id = pr.broker_id
    GROUP BY
        tp.topic_id,
        tp.partition_id,
        t.min_insync_replicas
)
SELECT
    t.topic_name,
    ph.partition_id,
    ph.online_replicas,
    ph.min_insync_replicas,
    CASE
        WHEN ph.online_replicas >= ph.min_insync_replicas
            THEN 'ELIGIBLE'
        ELSE 'BLOCKED'
    END AS write_eligibility
FROM partition_health ph
JOIN topics t
  ON t.topic_id = ph.topic_id
ORDER BY
    t.topic_name,
    ph.partition_id;

CREATE VIEW topic_partition_health AS
SELECT
    t.topic_name,
    tp.partition_id,
    tp.leader_broker_id,
    tp.high_watermark,
    COUNT(pr.broker_id) AS replication_factor,
    COUNT(*) FILTER (
        WHERE b.state = 'ONLINE'
    ) AS online_replicas,
    t.min_insync_replicas,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE b.state = 'ONLINE'
        ) >= t.min_insync_replicas
        THEN true
        ELSE false
    END AS write_eligible
FROM topics t
JOIN topic_partitions tp
  ON tp.topic_id = t.topic_id
JOIN partition_replicas pr
  ON pr.topic_id = tp.topic_id
 AND pr.partition_id = tp.partition_id
JOIN brokers b
  ON b.broker_id = pr.broker_id
GROUP BY
    t.topic_name,
    tp.partition_id,
    tp.leader_broker_id,
    tp.high_watermark,
    t.min_insync_replicas;

CREATE VIEW consumer_lag_report AS
SELECT
    g.group_name,
    t.topic_name,
    co.partition_id,
    co.committed_offset,
    tp.high_watermark,
    GREATEST(
        tp.high_watermark + 1 -
        co.committed_offset,
        0
    ) AS lag
FROM committed_offsets co
JOIN consumer_groups g
  ON g.group_id = co.group_id
JOIN topics t
  ON t.topic_id = co.topic_id
JOIN topic_partitions tp
  ON tp.topic_id = co.topic_id
 AND tp.partition_id = co.partition_id;

SELECT *
FROM topic_partition_health
ORDER BY topic_name, partition_id;

SELECT *
FROM consumer_lag_report
ORDER BY group_name, topic_name, partition_id;

SELECT
    t.topic_name,
    COUNT(m.message_id) AS total_messages,
    COUNT(DISTINCT m.partition_id) AS active_partitions,
    MIN(m.published_at) AS first_message,
    MAX(m.published_at) AS last_message
FROM topics t
LEFT JOIN messages m
  ON m.topic_id = t.topic_id
GROUP BY t.topic_name
ORDER BY t.topic_name;

SELECT
    c.consumer_name,
    g.group_name,
    c.state,
    COUNT(ca.partition_id) AS assigned_partitions
FROM consumers c
JOIN consumer_groups g
  ON g.group_id = c.group_id
LEFT JOIN consumer_assignments ca
  ON ca.consumer_id = c.consumer_id
GROUP BY
    c.consumer_name,
    g.group_name,
    c.state
ORDER BY
    g.group_name,
    c.consumer_name;

SELECT
    t.topic_name,
    tp.partition_id,
    sc.check_name,
    sc.status,
    sc.checked_at
FROM status_checks sc
JOIN topics t
  ON t.topic_id = sc.topic_id
JOIN topic_partitions tp
  ON tp.topic_id = sc.topic_id
 AND tp.partition_id = sc.partition_id
ORDER BY
    t.topic_name,
    tp.partition_id,
    sc.check_name;
