-- Distributed Systems Fundamentals
-- PostgreSQL-compatible relational model.
--
-- The schema represents a small distributed order platform:
-- repositories are replaced by distributed services/nodes,
-- each request has replicated state, health information, logical versions,
-- idempotency keys, quorum policies, leader information, and operation events.
--
-- PostgreSQL-specific mechanisms used here include:
--   * generated identity keys
--   * CHECK constraints
--   * foreign keys
--   * partial indexes
--   * views
--   * CTEs
--   * PL/pgSQL trigger functions
--   * transactional updates
--
-- The database does not pretend to implement a complete consensus protocol.
-- Instead, it stores and enforces durable state needed by an application-level
-- distributed-system coordinator.

DROP SCHEMA IF EXISTS distributed_systems CASCADE;
CREATE SCHEMA distributed_systems;

SET search_path TO distributed_systems;

-- ---------------------------------------------------------------------------
-- Nodes and cluster membership
-- ---------------------------------------------------------------------------

CREATE TABLE cluster_nodes (
    node_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_name        TEXT NOT NULL UNIQUE,
    region           TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'ONLINE',
    node_priority    INTEGER NOT NULL,
    last_heartbeat   TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT node_status_chk
        CHECK (status IN ('ONLINE', 'OFFLINE', 'SUSPECTED')),

    CONSTRAINT node_priority_chk
        CHECK (node_priority > 0)
);

CREATE INDEX idx_cluster_nodes_status
    ON cluster_nodes(status);

CREATE INDEX idx_cluster_nodes_heartbeat
    ON cluster_nodes(last_heartbeat);

INSERT INTO cluster_nodes
    (node_name, region, status, node_priority, last_heartbeat)
VALUES
    ('node-a', 'ap-south-1', 'ONLINE', 100, CURRENT_TIMESTAMP),
    ('node-b', 'ap-south-2', 'ONLINE', 90,  CURRENT_TIMESTAMP),
    ('node-c', 'ap-south-3', 'ONLINE', 80,  CURRENT_TIMESTAMP);

-- ---------------------------------------------------------------------------
-- Leader elections
-- ---------------------------------------------------------------------------

CREATE TABLE leader_elections (
    election_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    elected_node_id   BIGINT NOT NULL REFERENCES cluster_nodes(node_id),
    term_number       BIGINT NOT NULL,
    elected_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at          TIMESTAMPTZ,

    CONSTRAINT election_term_chk
        CHECK (term_number > 0),

    CONSTRAINT election_period_chk
        CHECK (ended_at IS NULL OR ended_at >= elected_at),

    CONSTRAINT unique_election_term
        UNIQUE (term_number)
);

CREATE INDEX idx_leader_elections_current
    ON leader_elections(elected_node_id)
    WHERE ended_at IS NULL;

INSERT INTO leader_elections
    (elected_node_id, term_number)
SELECT node_id, 1
FROM cluster_nodes
WHERE node_name = 'node-a';

-- ---------------------------------------------------------------------------
-- Distributed operations
-- ---------------------------------------------------------------------------

CREATE TABLE operations (
    operation_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id         TEXT NOT NULL UNIQUE,
    operation_type     TEXT NOT NULL,
    client_id          TEXT NOT NULL,
    idempotency_key    TEXT NOT NULL UNIQUE,
    logical_version   BIGINT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'PENDING',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at       TIMESTAMPTZ,

    CONSTRAINT operation_type_chk
        CHECK (operation_type IN ('CREATE_ORDER', 'UPDATE_ORDER', 'CANCEL_ORDER')),

    CONSTRAINT operation_status_chk
        CHECK (status IN ('PENDING', 'COMMITTED', 'FAILED')),

    CONSTRAINT operation_version_chk
        CHECK (logical_version > 0)
);

CREATE INDEX idx_operations_status
    ON operations(status);

CREATE INDEX idx_operations_client
    ON operations(client_id);

-- ---------------------------------------------------------------------------
-- Orders
-- ---------------------------------------------------------------------------

CREATE TABLE orders (
    order_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_order_id  TEXT NOT NULL UNIQUE,
    customer_id        TEXT NOT NULL,
    amount_cents       BIGINT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'PENDING',
    version_number     BIGINT NOT NULL,
    writer_node_id     BIGINT NOT NULL REFERENCES cluster_nodes(node_id),
    operation_id       BIGINT NOT NULL REFERENCES operations(operation_id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT order_amount_chk
        CHECK (amount_cents > 0),

    CONSTRAINT order_status_chk
        CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),

    CONSTRAINT order_version_chk
        CHECK (version_number > 0)
);

CREATE INDEX idx_orders_customer
    ON orders(customer_id);

CREATE INDEX idx_orders_status_version
    ON orders(status, version_number DESC);

-- ---------------------------------------------------------------------------
-- Replicated order state
-- ---------------------------------------------------------------------------

CREATE TABLE order_replicas (
    replica_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id           BIGINT NOT NULL REFERENCES orders(order_id)
                       ON DELETE CASCADE,
    node_id            BIGINT NOT NULL REFERENCES cluster_nodes(node_id),
    replicated_version BIGINT NOT NULL,
    replica_status     TEXT NOT NULL DEFAULT 'CURRENT',
    replicated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT replica_version_chk
        CHECK (replicated_version > 0),

    CONSTRAINT replica_status_chk
        CHECK (replica_status IN ('CURRENT', 'STALE', 'FAILED')),

    CONSTRAINT unique_order_replica
        UNIQUE (order_id, node_id)
);

CREATE INDEX idx_order_replicas_node_status
    ON order_replicas(node_id, replica_status);

-- ---------------------------------------------------------------------------
-- Quorum policy
-- ---------------------------------------------------------------------------

CREATE TABLE quorum_policies (
    policy_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name           TEXT NOT NULL UNIQUE,
    replication_factor    INTEGER NOT NULL,
    write_quorum          INTEGER NOT NULL,
    read_quorum           INTEGER NOT NULL,
    active                BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT replication_factor_chk
        CHECK (replication_factor > 0),

    CONSTRAINT write_quorum_chk
        CHECK (
            write_quorum >= 1
            AND write_quorum <= replication_factor
        ),

    CONSTRAINT read_quorum_chk
        CHECK (
            read_quorum >= 1
            AND read_quorum <= replication_factor
        )
);

INSERT INTO quorum_policies
    (policy_name, replication_factor, write_quorum, read_quorum)
VALUES
    ('orders-majority', 3, 2, 2);

-- ---------------------------------------------------------------------------
-- Idempotency records
-- ---------------------------------------------------------------------------

CREATE TABLE idempotency_records (
    idempotency_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key   TEXT NOT NULL UNIQUE,
    operation_id      BIGINT NOT NULL UNIQUE REFERENCES operations(operation_id),
    result_reference  TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_idempotency_operation
    ON idempotency_records(operation_id);

-- ---------------------------------------------------------------------------
-- Logical event clocks
-- ---------------------------------------------------------------------------

CREATE TABLE distributed_events (
    event_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id              BIGINT NOT NULL REFERENCES cluster_nodes(node_id),
    operation_id         BIGINT REFERENCES operations(operation_id),
    event_type           TEXT NOT NULL,
    logical_clock        BIGINT NOT NULL,
    parent_event_id      BIGINT REFERENCES distributed_events(event_id),
    event_payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT logical_clock_chk
        CHECK (logical_clock > 0)
);

CREATE INDEX idx_distributed_events_operation
    ON distributed_events(operation_id, logical_clock);

CREATE INDEX idx_distributed_events_node_clock
    ON distributed_events(node_id, logical_clock);

-- ---------------------------------------------------------------------------
-- Failure detection
-- ---------------------------------------------------------------------------

CREATE TABLE heartbeat_events (
    heartbeat_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id            BIGINT NOT NULL REFERENCES cluster_nodes(node_id),
    heartbeat_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observed_status    TEXT NOT NULL,

    CONSTRAINT heartbeat_status_chk
        CHECK (observed_status IN ('ONLINE', 'SUSPECTED', 'OFFLINE'))
);

CREATE INDEX idx_heartbeat_node_time
    ON heartbeat_events(node_id, heartbeat_at DESC);

-- ---------------------------------------------------------------------------
-- Transactional order creation
-- ---------------------------------------------------------------------------
-- The transaction models a write coordinator:
-- operation registration, order creation, and initial replication records
-- become one atomic database transaction.

BEGIN;

INSERT INTO operations
    (
        request_id,
        operation_type,
        client_id,
        idempotency_key,
        logical_version,
        status
    )
VALUES
    (
        'REQ-1001',
        'CREATE_ORDER',
        'CLIENT-42',
        'IDEMP-1001',
        1,
        'COMMITTED'
    );

INSERT INTO orders
    (
        external_order_id,
        customer_id,
        amount_cents,
        status,
        version_number,
        writer_node_id,
        operation_id
    )
SELECT
    'ORD-1001',
    'CUSTOMER-42',
    250000,
    'CONFIRMED',
    1,
    n.node_id,
    o.operation_id
FROM cluster_nodes n
JOIN operations o
    ON o.request_id = 'REQ-1001'
WHERE n.node_name = 'node-a';

INSERT INTO idempotency_records
    (idempotency_key, operation_id, result_reference)
SELECT
    'IDEMP-1001',
    operation_id,
    'ORD-1001'
FROM operations
WHERE request_id = 'REQ-1001';

INSERT INTO order_replicas
    (order_id, node_id, replicated_version, replica_status)
SELECT
    o.order_id,
    n.node_id,
    1,
    'CURRENT'
FROM orders o
CROSS JOIN cluster_nodes n
WHERE o.external_order_id = 'ORD-1001';

COMMIT;

-- ---------------------------------------------------------------------------
-- More realistic distributed state
-- ---------------------------------------------------------------------------

INSERT INTO operations
    (
        request_id,
        operation_type,
        client_id,
        idempotency_key,
        logical_version,
        status
    )
VALUES
    (
        'REQ-1002',
        'CREATE_ORDER',
        'CLIENT-88',
        'IDEMP-1002',
        2,
        'COMMITTED'
    ),
    (
        'REQ-1003',
        'CREATE_ORDER',
        'CLIENT-91',
        'IDEMP-1003',
        3,
        'PENDING'
    );

INSERT INTO orders
    (
        external_order_id,
        customer_id,
        amount_cents,
        status,
        version_number,
        writer_node_id,
        operation_id
    )
SELECT
    'ORD-1002',
    'CUSTOMER-88',
    7500,
    'CONFIRMED',
    2,
    n.node_id,
    o.operation_id
FROM cluster_nodes n
JOIN operations o
    ON o.request_id = 'REQ-1002'
WHERE n.node_name = 'node-b';

INSERT INTO order_replicas
    (order_id, node_id, replicated_version, replica_status)
SELECT
    o.order_id,
    n.node_id,
    2,
    CASE
        WHEN n.node_name = 'node-c' THEN 'STALE'
        ELSE 'CURRENT'
    END
FROM orders o
CROSS JOIN cluster_nodes n
WHERE o.external_order_id = 'ORD-1002';

-- ---------------------------------------------------------------------------
-- Heartbeats and failure evidence
-- ---------------------------------------------------------------------------

INSERT INTO heartbeat_events
    (node_id, observed_status)
SELECT node_id, 'ONLINE'
FROM cluster_nodes
WHERE node_name IN ('node-a', 'node-b');

UPDATE cluster_nodes
SET
    status = 'SUSPECTED',
    last_heartbeat = CURRENT_TIMESTAMP - INTERVAL '10 minutes'
WHERE node_name = 'node-c';

INSERT INTO heartbeat_events
    (node_id, observed_status)
SELECT node_id, 'SUSPECTED'
FROM cluster_nodes
WHERE node_name = 'node-c';

-- ---------------------------------------------------------------------------
-- Distributed logical events
-- ---------------------------------------------------------------------------

INSERT INTO distributed_events
    (
        node_id,
        operation_id,
        event_type,
        logical_clock,
        event_payload
    )
SELECT
    n.node_id,
    o.operation_id,
    'ORDER_CREATED',
    1,
    jsonb_build_object(
        'order_id', 'ORD-1001',
        'replication_factor', 3
    )
FROM cluster_nodes n
JOIN operations o
    ON o.request_id = 'REQ-1001'
WHERE n.node_name = 'node-a';

INSERT INTO distributed_events
    (
        node_id,
        operation_id,
        event_type,
        logical_clock,
        event_payload
    )
SELECT
    n.node_id,
    o.operation_id,
    'ORDER_REPLICATED',
    2,
    jsonb_build_object(
        'order_id', 'ORD-1001',
        'target_region', 'ap-south-2'
    )
FROM cluster_nodes n
JOIN operations o
    ON o.request_id = 'REQ-1001'
WHERE n.node_name = 'node-b';

-- ---------------------------------------------------------------------------
-- Database-level timestamp maintenance
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_order_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_orders_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION update_order_timestamp();

-- ---------------------------------------------------------------------------
-- Governance and consistency views
-- ---------------------------------------------------------------------------

CREATE VIEW active_leader AS
SELECT
    e.term_number,
    n.node_id,
    n.node_name,
    n.region,
    n.status,
    e.elected_at
FROM leader_elections e
JOIN cluster_nodes n
    ON n.node_id = e.elected_node_id
WHERE e.ended_at IS NULL;

CREATE VIEW order_replication_health AS
SELECT
    o.external_order_id,
    o.version_number AS order_version,
    COUNT(r.replica_id) AS replica_count,
    COUNT(*) FILTER (
        WHERE r.replica_status = 'CURRENT'
    ) AS current_replica_count,
    COUNT(*) FILTER (
        WHERE n.status = 'ONLINE'
    ) AS online_nodes
FROM orders o
LEFT JOIN order_replicas r
    ON r.order_id = o.order_id
LEFT JOIN cluster_nodes n
    ON n.node_id = r.node_id
GROUP BY
    o.order_id,
    o.external_order_id,
    o.version_number;

CREATE VIEW quorum_eligibility AS
SELECT
    p.policy_name,
    p.replication_factor,
    p.read_quorum,
    p.write_quorum,
    COUNT(n.node_id) FILTER (
        WHERE n.status = 'ONLINE'
    ) AS online_nodes,
    (
        COUNT(n.node_id) FILTER (
            WHERE n.status = 'ONLINE'
        ) >= p.write_quorum
    ) AS writes_can_reach_quorum,
    (
        COUNT(n.node_id) FILTER (
            WHERE n.status = 'ONLINE'
        ) >= p.read_quorum
    ) AS reads_can_reach_quorum
FROM quorum_policies p
CROSS JOIN cluster_nodes n
WHERE p.active
GROUP BY
    p.policy_id,
    p.policy_name,
    p.replication_factor,
    p.read_quorum,
    p.write_quorum;

-- ---------------------------------------------------------------------------
-- Operational queries
-- ---------------------------------------------------------------------------

-- Identify nodes that may be suspected because of stale heartbeats.
SELECT
    node_name,
    region,
    status,
    last_heartbeat,
    CURRENT_TIMESTAMP - last_heartbeat AS heartbeat_age
FROM cluster_nodes
WHERE last_heartbeat < CURRENT_TIMESTAMP - INTERVAL '5 minutes'
ORDER BY heartbeat_age DESC;

-- Find orders whose replica state is not fully current.
SELECT
    external_order_id,
    order_version,
    replica_count,
    current_replica_count,
    online_nodes
FROM order_replication_health
WHERE current_replica_count < replica_count
ORDER BY external_order_id;

-- Determine whether the current cluster can satisfy configured quorums.
SELECT
    policy_name,
    online_nodes,
    read_quorum,
    write_quorum,
    reads_can_reach_quorum,
    writes_can_reach_quorum
FROM quorum_eligibility;

-- Inspect the logical event sequence for a request.
SELECT
    e.event_id,
    n.node_name,
    e.event_type,
    e.logical_clock,
    e.event_payload,
    e.created_at
FROM distributed_events e
JOIN cluster_nodes n
    ON n.node_id = e.node_id
JOIN operations o
    ON o.operation_id = e.operation_id
WHERE o.request_id = 'REQ-1001'
ORDER BY e.logical_clock, e.event_id;

-- Detect stale replicas relative to their order version.
SELECT
    o.external_order_id,
    n.node_name,
    o.version_number AS authoritative_version,
    r.replicated_version,
    r.replica_status
FROM order_replicas r
JOIN orders o
    ON o.order_id = r.order_id
JOIN cluster_nodes n
    ON n.node_id = r.node_id
WHERE r.replicated_version < o.version_number
   OR r.replica_status <> 'CURRENT'
ORDER BY o.external_order_id, n.node_name;

-- ---------------------------------------------------------------------------
-- Idempotency lookup
-- ---------------------------------------------------------------------------
-- An application receiving a retry can check this table before creating a
-- second operation.

SELECT
    i.idempotency_key,
    i.operation_id,
    i.result_reference,
    o.request_id,
    o.status
FROM idempotency_records i
JOIN operations o
    ON o.operation_id = i.operation_id
WHERE i.idempotency_key = 'IDEMP-1001';

-- ---------------------------------------------------------------------------
-- CTE for node availability and quorum calculation
-- ---------------------------------------------------------------------------

WITH online_nodes AS (
    SELECT COUNT(*) AS count
    FROM cluster_nodes
    WHERE status = 'ONLINE'
),
policy AS (
    SELECT
        replication_factor,
        write_quorum,
        read_quorum
    FROM quorum_policies
    WHERE policy_name = 'orders-majority'
      AND active
)
SELECT
    online_nodes.count AS online_nodes,
    policy.replication_factor,
    policy.write_quorum,
    policy.read_quorum,
    online_nodes.count >= policy.write_quorum
        AS write_quorum_available,
    online_nodes.count >= policy.read_quorum
        AS read_quorum_available
FROM online_nodes
CROSS JOIN policy;

-- ---------------------------------------------------------------------------
-- Transactional recovery example
-- ---------------------------------------------------------------------------
-- Bring node-c back online and mark its heartbeat current. Updating the node
-- and its heartbeat evidence in one transaction avoids exposing an intermediate
-- database state to other transactions using normal READ COMMITTED semantics.

BEGIN;

UPDATE cluster_nodes
SET
    status = 'ONLINE',
    last_heartbeat = CURRENT_TIMESTAMP
WHERE node_name = 'node-c';

INSERT INTO heartbeat_events
    (node_id, observed_status)
SELECT
    node_id,
    'ONLINE'
FROM cluster_nodes
WHERE node_name = 'node-c';

COMMIT;

-- ---------------------------------------------------------------------------
-- Final state inspection
-- ---------------------------------------------------------------------------

SELECT
    node_name,
    region,
    status,
    node_priority
FROM cluster_nodes
ORDER BY node_priority DESC;

SELECT
    external_order_id,
    customer_id,
    amount_cents,
    status,
    version_number
FROM orders
ORDER BY external_order_id;

SELECT
    policy_name,
    replication_factor,
    write_quorum,
    read_quorum,
    active
FROM quorum_policies;
