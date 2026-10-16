DROP SCHEMA IF EXISTS distributed_time_lab CASCADE;
CREATE SCHEMA distributed_time_lab;
SET search_path = distributed_time_lab;

-- Physical timestamps describe observations made by individual nodes.
-- Logical timestamps describe causal history independently of wall-clock accuracy.
-- Vector clocks retain per-node causal counters so concurrent events can be detected.

CREATE TYPE event_kind AS ENUM (
    'LOCAL',
    'SEND',
    'RECEIVE'
);

CREATE TYPE causality_relation AS ENUM (
    'BEFORE',
    'AFTER',
    'EQUAL',
    'CONCURRENT'
);

CREATE TABLE nodes (
    node_id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_name            TEXT NOT NULL UNIQUE,
    clock_offset_ms      NUMERIC(14,3) NOT NULL DEFAULT 0,
    drift_ppm            NUMERIC(12,3) NOT NULL DEFAULT 0,
    last_sync_at         TIMESTAMPTZ,
    CHECK (clock_offset_ms BETWEEN -86400000 AND 86400000),
    CHECK (drift_ppm BETWEEN -1000000 AND 1000000)
);

CREATE TABLE events (
    event_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key            TEXT NOT NULL UNIQUE,
    node_id              BIGINT NOT NULL REFERENCES nodes(node_id),
    event_kind            event_kind NOT NULL,
    event_name            TEXT NOT NULL,
    observed_at           TIMESTAMPTZ NOT NULL,
    logical_timestamp     BIGINT NOT NULL,
    payload               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (logical_timestamp > 0)
);

CREATE TABLE event_messages (
    message_id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    send_event_id         BIGINT NOT NULL UNIQUE REFERENCES events(event_id),
    receive_event_id      BIGINT NOT NULL UNIQUE REFERENCES events(event_id),
    CHECK (send_event_id <> receive_event_id)
);

CREATE TABLE vector_entries (
    event_id              BIGINT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    node_id               BIGINT NOT NULL REFERENCES nodes(node_id),
    counter               BIGINT NOT NULL,
    PRIMARY KEY (event_id, node_id),
    CHECK (counter >= 0)
);

CREATE INDEX idx_events_node_observed
    ON events (node_id, observed_at);

CREATE INDEX idx_events_logical
    ON events (node_id, logical_timestamp);

CREATE INDEX idx_vector_entries_node_counter
    ON vector_entries (node_id, counter);

CREATE INDEX idx_events_payload
    ON events USING GIN (payload);

INSERT INTO nodes (
    node_name,
    clock_offset_ms,
    drift_ppm,
    last_sync_at
)
VALUES
    ('orders', 35.000, 10.000, '2026-10-16 05:29:55+00'),
    ('inventory', -25.000, -4.000, '2026-10-16 05:29:56+00'),
    ('payments', 60.000, 15.000, '2026-10-16 05:29:57+00');

-- The event timestamps intentionally come from different node clocks.
-- The logical counters represent causal progression and are not wall-clock durations.

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-001',
    node_id,
    'LOCAL',
    'ORDER_CREATED',
    '2026-10-16 05:30:20.035+00',
    1,
    '{"order_id":"ORD-1001"}'
FROM nodes
WHERE node_name = 'orders';

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-002',
    node_id,
    'SEND',
    'RESERVATION_REQUEST_SENT',
    '2026-10-16 05:30:20.039+00',
    2,
    '{"destination":"inventory","sku":"SKU-9","quantity":1}'
FROM nodes
WHERE node_name = 'orders';

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-003',
    node_id,
    'RECEIVE',
    'RESERVATION_REQUEST_RECEIVED',
    '2026-10-16 05:30:19.983+00',
    3,
    '{"source":"orders","sku":"SKU-9","quantity":1}'
FROM nodes
WHERE node_name = 'inventory';

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-004',
    node_id,
    'SEND',
    'PAYMENT_REQUEST_SENT',
    '2026-10-16 05:30:20.070+00',
    3,
    '{"destination":"payments","amount":125.00,"currency":"USD"}'
FROM nodes
WHERE node_name = 'orders';

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-005',
    node_id,
    'RECEIVE',
    'PAYMENT_REQUEST_RECEIVED',
    '2026-10-16 05:30:20.075+00',
    4,
    '{"source":"orders","amount":125.00,"currency":"USD"}'
FROM nodes
WHERE node_name = 'payments';

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-006',
    node_id,
    'LOCAL',
    'PAYMENT_AUTHORIZED',
    '2026-10-16 05:30:20.080+00',
    5,
    '{"authorization":"AUTH-77"}'
FROM nodes
WHERE node_name = 'payments';

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-007',
    node_id,
    'LOCAL',
    'INVENTORY_RESERVED',
    '2026-10-16 05:30:20.025+00',
    4,
    '{"sku":"SKU-9","quantity":1}'
FROM nodes
WHERE node_name = 'inventory';

INSERT INTO event_messages (
    send_event_id,
    receive_event_id
)
SELECT
    sender.event_id,
    receiver.event_id
FROM events sender
JOIN events receiver
  ON receiver.event_key = 'evt-003'
WHERE sender.event_key = 'evt-002';

INSERT INTO event_messages (
    send_event_id,
    receive_event_id
)
SELECT
    sender.event_id,
    receiver.event_id
FROM events sender
JOIN events receiver
  ON receiver.event_key = 'evt-005'
WHERE sender.event_key = 'evt-004';

INSERT INTO vector_entries (event_id, node_id, counter)
SELECT
    event_id,
    nodes.node_id,
    CASE
        WHEN nodes.node_name = 'orders' THEN 1
        ELSE 0
    END
FROM events
CROSS JOIN nodes
WHERE event_key = 'evt-001';

INSERT INTO vector_entries (event_id, node_id, counter)
SELECT
    event_id,
    nodes.node_id,
    CASE
        WHEN nodes.node_name = 'orders' THEN 2
        ELSE 0
    END
FROM events
CROSS JOIN nodes
WHERE event_key = 'evt-002';

INSERT INTO vector_entries (event_id, node_id, counter)
SELECT
    event_id,
    nodes.node_id,
    CASE
        WHEN nodes.node_name = 'orders' THEN 2
        WHEN nodes.node_name = 'inventory' THEN 1
        ELSE 0
    END
FROM events
CROSS JOIN nodes
WHERE event_key = 'evt-003';

INSERT INTO vector_entries (event_id, node_id, counter)
SELECT
    event_id,
    nodes.node_id,
    CASE
        WHEN nodes.node_name = 'orders' THEN 3
        ELSE 0
    END
FROM events
CROSS JOIN nodes
WHERE event_key = 'evt-004';

INSERT INTO vector_entries (event_id, node_id, counter)
SELECT
    event_id,
    nodes.node_id,
    CASE
        WHEN nodes.node_name = 'orders' THEN 3
        WHEN nodes.node_name = 'payments' THEN 1
        ELSE 0
    END
FROM events
CROSS JOIN nodes
WHERE event_key = 'evt-005';

INSERT INTO vector_entries (event_id, node_id, counter)
SELECT
    event_id,
    nodes.node_id,
    CASE
        WHEN nodes.node_name = 'orders' THEN 3
        WHEN nodes.node_name = 'payments' THEN 2
        ELSE 0
    END
FROM events
CROSS JOIN nodes
WHERE event_key = 'evt-006';

INSERT INTO vector_entries (event_id, node_id, counter)
SELECT
    event_id,
    nodes.node_id,
    CASE
        WHEN nodes.node_name = 'inventory' THEN 2
        ELSE 0
    END
FROM events
CROSS JOIN nodes
WHERE event_key = 'evt-007';

CREATE OR REPLACE VIEW event_timeline AS
SELECT
    e.event_key,
    n.node_name,
    e.event_kind,
    e.event_name,
    e.observed_at,
    e.logical_timestamp,
    e.payload
FROM events e
JOIN nodes n ON n.node_id = e.node_id
ORDER BY e.observed_at, e.event_id;

CREATE OR REPLACE VIEW vector_clock_state AS
SELECT
    e.event_key,
    jsonb_object_agg(
        n.node_name,
        ve.counter
        ORDER BY n.node_name
    ) AS vector_clock
FROM events e
JOIN vector_entries ve
  ON ve.event_id = e.event_id
JOIN nodes n
  ON n.node_id = ve.node_id
GROUP BY e.event_key;

-- Physical ordering is useful for operational investigation but does not establish
-- causal ordering because independent node clocks may have different offsets.

SELECT
    event_key,
    node_name,
    event_name,
    observed_at,
    logical_timestamp
FROM event_timeline;

-- This query finds cases where a later Lamport value is observed at an earlier
-- physical timestamp. Such a result is expected when node clocks are skewed.

SELECT
    earlier.event_key AS physical_first,
    later.event_key AS physical_second,
    earlier.logical_timestamp AS first_logical,
    later.logical_timestamp AS second_logical
FROM events earlier
JOIN events later
  ON earlier.observed_at < later.observed_at
WHERE earlier.logical_timestamp > later.logical_timestamp
ORDER BY earlier.observed_at;

-- Retrieve the vector representation used for causal analysis.

SELECT
    e.event_key,
    vcs.vector_clock
FROM events e
JOIN vector_clock_state vcs
  ON vcs.event_key = e.event_key
ORDER BY e.event_id;

-- Detect pairs whose vectors are concurrent.
-- For two events A and B, concurrency means:
-- neither A <= B nor B <= A across every vector dimension.

WITH pairwise AS (
    SELECT
        a.event_key AS event_a,
        b.event_key AS event_b,
        a.event_id AS id_a,
        b.event_id AS id_b,
        a.node_id AS node_a,
        b.node_id AS node_b
    FROM events a
    JOIN events b
      ON a.event_id < b.event_id
),
comparisons AS (
    SELECT
        p.*,
        bool_and(va.counter <= vb.counter) AS a_le_b,
        bool_and(vb.counter <= va.counter) AS b_le_a,
        bool_or(va.counter < vb.counter) AS a_strict,
        bool_or(vb.counter < va.counter) AS b_strict
    FROM pairwise p
    JOIN vector_entries va
      ON va.event_id = p.id_a
    JOIN vector_entries vb
      ON vb.event_id = p.id_b
     AND vb.node_id = va.node_id
    GROUP BY
        p.event_a,
        p.event_b,
        p.id_a,
        p.id_b,
        p.node_a,
        p.node_b
)
SELECT
    event_a,
    event_b,
    CASE
        WHEN a_le_b AND b_le_a THEN 'EQUAL'
        WHEN a_le_b AND a_strict THEN 'BEFORE'
        WHEN b_le_a AND b_strict THEN 'AFTER'
        ELSE 'CONCURRENT'
    END AS relation
FROM comparisons
WHERE NOT (a_le_b AND a_strict)
   OR NOT (b_le_a AND b_strict)
ORDER BY id_a, id_b;

-- Calculate observed clock spread among nodes. This is an operational metric,
-- not a causal-ordering mechanism.

SELECT
    max(clock_offset_ms) - min(clock_offset_ms)
        AS configured_offset_spread_ms,
    avg(clock_offset_ms)
        AS average_configured_offset_ms,
    max(abs(drift_ppm))
        AS maximum_absolute_drift_ppm
FROM nodes;

-- Find events whose physical timestamps are close enough that clock uncertainty
-- could make ordering unreliable. Here the threshold is 100 milliseconds.

SELECT
    a.event_key AS event_a,
    b.event_key AS event_b,
    abs(
        extract(
            epoch FROM (
                a.observed_at - b.observed_at
            )
        ) * 1000
    ) AS observed_difference_ms
FROM events a
JOIN events b
  ON a.event_id < b.event_id
WHERE abs(
    extract(
        epoch FROM (
            a.observed_at - b.observed_at
        )
    ) * 1000
) <= 100
ORDER BY observed_difference_ms;

-- Database constraints reject invalid logical timestamps.

DO $$
BEGIN
    BEGIN
        INSERT INTO events (
            event_key,
            node_id,
            event_kind,
            event_name,
            observed_at,
            logical_timestamp
        )
        VALUES (
            'invalid-negative-logical-time',
            (SELECT node_id FROM nodes WHERE node_name = 'orders'),
            'LOCAL',
            'INVALID_EVENT',
            CURRENT_TIMESTAMP,
            -1
        );
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Rejected negative logical timestamp as expected';
    END;
END;
$$;

-- A transaction models a synchronized metadata update. Both the physical
-- synchronization record and the observed event are committed together.

BEGIN;

UPDATE nodes
SET
    last_sync_at = '2026-10-16 05:31:00+00',
    clock_offset_ms = 32.500
WHERE node_name = 'orders';

INSERT INTO events (
    event_key,
    node_id,
    event_kind,
    event_name,
    observed_at,
    logical_timestamp,
    payload
)
SELECT
    'evt-008',
    node_id,
    'LOCAL',
    'CLOCK_SYNCHRONIZED',
    '2026-10-16 05:31:00.0325+00',
    5,
    jsonb_build_object(
        'method', 'offset-estimation',
        'estimated_offset_ms', 32.5
    )
FROM nodes
WHERE node_name = 'orders';

COMMIT;

SELECT
    node_name,
    clock_offset_ms,
    drift_ppm,
    last_sync_at
FROM nodes
ORDER BY node_name;
