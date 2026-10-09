-- Database sharding laboratory for PostgreSQL 15+.
--
-- The schema models an order platform partitioned by customer_id.
-- It distinguishes logical shard metadata from physical storage.
-- A production deployment would map each shard to an independently managed
-- PostgreSQL cluster or database and coordinate metadata across services.
--
-- Run in a disposable PostgreSQL database because the schema is recreated.

BEGIN;

DROP SCHEMA IF EXISTS sharding_lab CASCADE;
CREATE SCHEMA sharding_lab;
SET search_path TO sharding_lab, public;

CREATE TYPE shard_state AS ENUM (
    'active',
    'draining',
    'offline'
);

CREATE TYPE order_state AS ENUM (
    'pending',
    'paid',
    'cancelled',
    'refunded'
);

CREATE TABLE shards (
    shard_id        text PRIMARY KEY,
    endpoint        text NOT NULL,
    state           shard_state NOT NULL DEFAULT 'active',
    capacity_weight integer NOT NULL DEFAULT 100,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT shard_id_not_blank CHECK (btrim(shard_id) <> ''),
    CONSTRAINT positive_capacity CHECK (capacity_weight > 0)
);

CREATE TABLE shard_map (
    routing_key     text PRIMARY KEY,
    shard_id        text NOT NULL REFERENCES shards(shard_id),
    mapping_version bigint NOT NULL DEFAULT 1,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT routing_key_not_blank CHECK (btrim(routing_key) <> ''),
    CONSTRAINT positive_mapping_version CHECK (mapping_version > 0)
);

CREATE INDEX shard_map_owner_idx
    ON shard_map (shard_id, routing_key);

CREATE TABLE customers (
    customer_id text PRIMARY KEY,
    shard_id    text NOT NULL REFERENCES shards(shard_id),
    region      text NOT NULL,
    email       text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT customer_id_not_blank CHECK (btrim(customer_id) <> ''),
    CONSTRAINT customer_email_not_blank CHECK (btrim(email) <> ''),
    CONSTRAINT customer_shard_identity UNIQUE (shard_id, customer_id)
);

CREATE INDEX customers_region_idx
    ON customers (region);

CREATE INDEX customers_shard_region_idx
    ON customers (shard_id, region);

CREATE TABLE orders (
    order_id     text PRIMARY KEY,
    shard_id     text NOT NULL REFERENCES shards(shard_id),
    customer_id  text NOT NULL,
    amount_cents bigint NOT NULL,
    status       order_state NOT NULL DEFAULT 'pending',
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT order_id_not_blank CHECK (btrim(order_id) <> ''),
    CONSTRAINT nonnegative_order_amount CHECK (amount_cents >= 0),

    -- This composite foreign key enforces co-location in the logical model:
    -- an order cannot reference a customer assigned to a different shard.
    CONSTRAINT order_customer_same_shard
        FOREIGN KEY (shard_id, customer_id)
        REFERENCES customers (shard_id, customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
);

CREATE INDEX orders_customer_time_idx
    ON orders (shard_id, customer_id, created_at DESC);

CREATE INDEX orders_status_time_idx
    ON orders (status, created_at DESC);

CREATE TABLE range_assignments (
    range_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    start_inclusive bigint NOT NULL,
    end_exclusive   bigint NOT NULL,
    shard_id        text NOT NULL REFERENCES shards(shard_id),
    CONSTRAINT valid_range CHECK (start_inclusive < end_exclusive),
    CONSTRAINT unique_range_start UNIQUE (start_inclusive)
);

-- PostgreSQL exclusion constraints can prevent overlapping range ownership.
-- btree_gist provides GiST equality support for text shard identifiers.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE range_assignments
    ADD CONSTRAINT range_ownership_no_overlap
    EXCLUDE USING gist (
        int8range(start_inclusive, end_exclusive, '[)') WITH &&
    );

CREATE TABLE migration_jobs (
    migration_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    routing_key    text NOT NULL,
    source_shard   text NOT NULL REFERENCES shards(shard_id),
    target_shard   text NOT NULL REFERENCES shards(shard_id),
    state          text NOT NULL DEFAULT 'planned',
    copied_records bigint NOT NULL DEFAULT 0,
    verified       boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    completed_at   timestamptz,
    CONSTRAINT distinct_migration_shards
        CHECK (source_shard <> target_shard),
    CONSTRAINT valid_migration_state
        CHECK (state IN ('planned', 'copying', 'verified',
                         'committed', 'failed')),
    CONSTRAINT nonnegative_copied_records CHECK (copied_records >= 0),
    CONSTRAINT migration_completion_consistency
        CHECK (
            state <> 'committed'
            OR (verified AND completed_at IS NOT NULL)
        )
);

CREATE TABLE shard_events (
    event_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shard_id    text REFERENCES shards(shard_id),
    event_type  text NOT NULL,
    details     jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT event_type_not_blank CHECK (btrim(event_type) <> '')
);

CREATE INDEX shard_events_recent_idx
    ON shard_events (shard_id, occurred_at DESC);

-- Register logical shards.
INSERT INTO shards (shard_id, endpoint, capacity_weight)
VALUES
    ('shard-east', 'postgres-east.internal:5432', 100),
    ('shard-central', 'postgres-central.internal:5432', 100),
    ('shard-west', 'postgres-west.internal:5432', 100),
    ('shard-overflow', 'postgres-overflow.internal:5432', 50);

-- These assignments model a directory after an application has calculated
-- stable hash placements. PostgreSQL does not calculate the hash-ring mapping
-- implicitly; the routing service owns that algorithm.
INSERT INTO shard_map (routing_key, shard_id, mapping_version)
VALUES
    ('cust-100', 'shard-east', 1),
    ('cust-200', 'shard-central', 1),
    ('cust-300', 'shard-west', 1),
    ('cust-400', 'shard-east', 1),
    ('cust-500', 'shard-central', 1);

INSERT INTO customers (customer_id, shard_id, region, email)
VALUES
    ('cust-100', 'shard-east', 'north', 'a@example.test'),
    ('cust-200', 'shard-central', 'south', 'b@example.test'),
    ('cust-300', 'shard-west', 'west', 'c@example.test'),
    ('cust-400', 'shard-east', 'east', 'd@example.test'),
    ('cust-500', 'shard-central', 'north', 'e@example.test');

INSERT INTO orders (
    order_id, shard_id, customer_id, amount_cents, status, created_at
)
VALUES
    ('ord-001', 'shard-east', 'cust-100', 1299, 'paid',
     '2026-10-01 09:00:00+00'),
    ('ord-002', 'shard-east', 'cust-100', 4599, 'pending',
     '2026-10-02 11:30:00+00'),
    ('ord-003', 'shard-central', 'cust-200', 899, 'paid',
     '2026-10-03 15:15:00+00'),
    ('ord-004', 'shard-west', 'cust-300', 2599, 'paid',
     '2026-10-04 10:20:00+00'),
    ('ord-005', 'shard-east', 'cust-400', 7999, 'refunded',
     '2026-10-05 16:45:00+00'),
    ('ord-006', 'shard-central', 'cust-500', 1799, 'pending',
     '2026-10-06 12:00:00+00');

INSERT INTO range_assignments (
    start_inclusive, end_exclusive, shard_id
)
VALUES
    (0, 1000000, 'shard-east'),
    (1000000, 2000000, 'shard-central'),
    (2000000, 3000000, 'shard-west');

INSERT INTO shard_events (shard_id, event_type, details)
VALUES
    ('shard-east', 'shard.registered',
     '{"routing": "hash", "replicas": 3}'),
    ('shard-central', 'shard.registered',
     '{"routing": "hash", "replicas": 3}'),
    ('shard-west', 'shard.registered',
     '{"routing": "hash", "replicas": 3}');

-- A customer-local query uses the shard key and a matching composite index.
PREPARE customer_orders(text) AS
SELECT order_id, customer_id, amount_cents, status, created_at
FROM orders
WHERE customer_id = $1
ORDER BY created_at DESC;

EXECUTE customer_orders('cust-100');

-- Scatter-gather equivalent: the coordinator combines shard-local aggregates.
-- A distributed query engine would execute each partial aggregate remotely.
SELECT shard_id,
       count(*) AS order_count,
       sum(amount_cents) AS gross_cents
FROM orders
GROUP BY shard_id
ORDER BY shard_id;

SELECT customer_id,
       count(*) AS order_count,
       sum(amount_cents) AS total_cents
FROM orders
GROUP BY customer_id
ORDER BY customer_id;

-- The directory view exposes current routing metadata for application clients.
CREATE VIEW routing_directory AS
SELECT m.routing_key,
       m.shard_id,
       s.endpoint,
       s.state,
       m.mapping_version,
       m.updated_at
FROM shard_map AS m
JOIN shards AS s USING (shard_id);

SELECT * FROM routing_directory ORDER BY routing_key;

-- A range-routing lookup uses half-open interval semantics.
PREPARE range_route(bigint) AS
SELECT shard_id
FROM range_assignments
WHERE start_inclusive <= $1
  AND $1 < end_exclusive;

EXECUTE range_route(1000000);

-- Invalid records are rejected by database constraints.
DO $$
BEGIN
    BEGIN
        INSERT INTO orders (
            order_id, shard_id, customer_id, amount_cents
        )
        VALUES (
            'ord-invalid', 'shard-central', 'cust-100', -50
        );
        RAISE EXCEPTION 'Expected a constraint violation';
    EXCEPTION
        WHEN check_violation OR foreign_key_violation THEN
            RAISE NOTICE 'Invalid order correctly rejected: %', SQLERRM;
    END;
END;
$$;

-- Migration preparation records intent without changing live ownership.
INSERT INTO migration_jobs (
    routing_key, source_shard, target_shard, state
)
VALUES (
    'cust-100', 'shard-east', 'shard-overflow', 'planned'
)
RETURNING migration_id;

-- Demonstrate an atomic ownership change for a controlled offline migration.
-- The transaction locks the relevant metadata and moves customer records
-- together with their orders. Concurrent writers require application-level
-- fencing or a distributed migration protocol.
BEGIN;

SELECT shard_id
FROM shard_map
WHERE routing_key = 'cust-100'
FOR UPDATE;

-- Preserve referential integrity by moving child rows first only after
-- temporarily deferring the foreign key within this transaction.
SET CONSTRAINTS order_customer_same_shard DEFERRED;

UPDATE orders
SET shard_id = 'shard-overflow'
WHERE customer_id = 'cust-100'
  AND shard_id = 'shard-east';

UPDATE customers
SET shard_id = 'shard-overflow'
WHERE customer_id = 'cust-100'
  AND shard_id = 'shard-east';

UPDATE shard_map
SET shard_id = 'shard-overflow',
    mapping_version = mapping_version + 1,
    updated_at = now()
WHERE routing_key = 'cust-100'
  AND shard_id = 'shard-east';

UPDATE migration_jobs
SET state = 'verified',
    copied_records = (
        SELECT count(*)
        FROM orders
        WHERE customer_id = 'cust-100'
          AND shard_id = 'shard-overflow'
    ) + 1,
    verified = true
WHERE routing_key = 'cust-100'
  AND source_shard = 'shard-east'
  AND target_shard = 'shard-overflow'
  AND state = 'planned';

UPDATE migration_jobs
SET state = 'committed',
    completed_at = now()
WHERE routing_key = 'cust-100'
  AND source_shard = 'shard-east'
  AND target_shard = 'shard-overflow'
  AND state = 'verified'
  AND verified = true;

INSERT INTO shard_events (shard_id, event_type, details)
VALUES (
    'shard-overflow',
    'migration.committed',
    '{"routing_key": "cust-100", "source": "shard-east"}'
);

COMMIT;

-- Check that customer records and their orders now share the same owner.
SELECT c.customer_id,
       c.shard_id AS customer_shard,
       o.order_id,
       o.shard_id AS order_shard,
       c.shard_id = o.shard_id AS colocated
FROM customers AS c
LEFT JOIN orders AS o USING (customer_id)
WHERE c.customer_id = 'cust-100'
ORDER BY o.order_id;

-- Detect routing metadata that disagrees with the customer table.
SELECT m.routing_key, m.shard_id AS directory_shard,
       c.shard_id AS customer_shard
FROM shard_map AS m
LEFT JOIN customers AS c ON c.customer_id = m.routing_key
WHERE c.customer_id IS NULL OR m.shard_id <> c.shard_id;

-- Operational view: identify uneven record distribution.
SELECT s.shard_id,
       s.state,
       count(DISTINCT c.customer_id) AS customer_count,
       count(DISTINCT o.order_id) AS order_count,
       coalesce(sum(o.amount_cents), 0) AS stored_amount_cents
FROM shards AS s
LEFT JOIN customers AS c ON c.shard_id = s.shard_id
LEFT JOIN orders AS o ON o.shard_id = s.shard_id
GROUP BY s.shard_id, s.state
ORDER BY order_count DESC, s.shard_id;

-- Range gaps are not automatically invalid, but should be deliberate.
WITH ordered_ranges AS (
    SELECT range_id,
           start_inclusive,
           end_exclusive,
           lag(end_exclusive) OVER (ORDER BY start_inclusive) AS previous_end
    FROM range_assignments
)
SELECT range_id,
       previous_end,
       start_inclusive,
       previous_end IS NOT NULL
           AND previous_end <> start_inclusive AS has_gap
FROM ordered_ranges
ORDER BY start_inclusive;

-- Check migration jobs that have been left incomplete.
SELECT migration_id, routing_key, source_shard, target_shard,
       state, copied_records, verified, created_at
FROM migration_jobs
WHERE state IN ('planned', 'copying', 'failed')
ORDER BY created_at;

-- Show query planning for the shard-key access path.
EXPLAIN
SELECT order_id, amount_cents, created_at
FROM orders
WHERE shard_id = 'shard-overflow'
  AND customer_id = 'cust-100'
ORDER BY created_at DESC;

COMMIT;
