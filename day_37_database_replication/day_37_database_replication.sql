/*
 * Database Replication Laboratory
 *
 * PostgreSQL-compatible logical model for studying primary-replica,
 * synchronous, and asynchronous replication.
 *
 * Important distinction:
 * PostgreSQL physical streaming replication is configured outside normal
 * application SQL using server configuration, WAL settings, replication
 * roles, pg_hba.conf, and standby configuration. This script therefore
 * models the replication control plane and transaction/replay behavior in
 * ordinary relational tables. It is executable as application SQL without
 * requiring superuser-only physical replication configuration.
 *
 * The model represents:
 *   primary database nodes
 *   replica database nodes
 *   replication modes
 *   WAL-like change records
 *   delivery and replay positions
 *   synchronous acknowledgement requirements
 *   replica health and lag
 *   failover generations
 *   consistency checks
 *
 * The tables deliberately separate "received" from "replayed" positions.
 * A replica can therefore be online while still being behind the primary.
 */

DROP SCHEMA IF EXISTS replication_lab CASCADE;

CREATE SCHEMA replication_lab;

SET search_path TO replication_lab;

CREATE TYPE node_role AS ENUM (
    'primary',
    'replica'
);

CREATE TYPE node_state AS ENUM (
    'up',
    'down'
);

CREATE TYPE replication_mode AS ENUM (
    'asynchronous',
    'synchronous'
);

CREATE TYPE change_operation AS ENUM (
    'set',
    'delete'
);

CREATE TABLE database_cluster (
    cluster_id BIGSERIAL PRIMARY KEY,
    cluster_name TEXT NOT NULL UNIQUE,
    replication_mode replication_mode NOT NULL,
    synchronous_replicas INTEGER NOT NULL DEFAULT 0,
    generation BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT positive_generation
        CHECK (generation > 0),

    CONSTRAINT valid_sync_requirement
        CHECK (
            synchronous_replicas >= 0
            AND (
                replication_mode = 'asynchronous'
                OR synchronous_replicas > 0
            )
        )
);

CREATE TABLE database_node (
    node_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id)
        ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    role node_role NOT NULL,
    state node_state NOT NULL DEFAULT 'up',
    generation BIGINT NOT NULL DEFAULT 1,
    received_lsn BIGINT NOT NULL DEFAULT 0,
    replayed_lsn BIGINT NOT NULL DEFAULT 0,
    last_heartbeat_at TIMESTAMPTZ,

    CONSTRAINT unique_node_per_cluster
        UNIQUE (cluster_id, node_name),

    CONSTRAINT non_negative_positions
        CHECK (
            received_lsn >= 0
            AND replayed_lsn >= 0
        ),

    CONSTRAINT replay_cannot_exceed_received
        CHECK (replayed_lsn <= received_lsn),

    CONSTRAINT primary_generation_positive
        CHECK (generation > 0)
);

CREATE UNIQUE INDEX one_primary_per_cluster
    ON database_node(cluster_id)
    WHERE role = 'primary';

CREATE INDEX database_node_replica_health_idx
    ON database_node(cluster_id, role, state, replayed_lsn);

CREATE TABLE replicated_entity (
    entity_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id)
        ON DELETE CASCADE,
    entity_key TEXT NOT NULL,
    entity_value TEXT,
    updated_lsn BIGINT NOT NULL,

    CONSTRAINT unique_entity_per_cluster
        UNIQUE (cluster_id, entity_key),

    CONSTRAINT valid_entity_lsn
        CHECK (updated_lsn > 0)
);

CREATE TABLE wal_change (
    change_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id)
        ON DELETE CASCADE,
    lsn BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL,
    generation BIGINT NOT NULL,
    operation change_operation NOT NULL,
    entity_key TEXT NOT NULL,
    entity_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT unique_lsn_per_cluster
        UNIQUE (cluster_id, lsn),

    CONSTRAINT positive_wal_position
        CHECK (lsn > 0),

    CONSTRAINT positive_transaction
        CHECK (transaction_id > 0),

    CONSTRAINT valid_change_value
        CHECK (
            (operation = 'set' AND entity_value IS NOT NULL)
            OR
            (operation = 'delete')
        )
);

CREATE INDEX wal_change_replay_idx
    ON wal_change(cluster_id, lsn);

CREATE INDEX wal_change_transaction_idx
    ON wal_change(cluster_id, transaction_id);

CREATE TABLE replication_delivery (
    delivery_id BIGSERIAL PRIMARY KEY,
    change_id BIGINT NOT NULL
        REFERENCES wal_change(change_id)
        ON DELETE CASCADE,
    replica_id BIGINT NOT NULL
        REFERENCES database_node(node_id)
        ON DELETE CASCADE,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    replayed_at TIMESTAMPTZ,

    CONSTRAINT unique_change_delivery
        UNIQUE (change_id, replica_id)
);

CREATE INDEX replication_delivery_replay_idx
    ON replication_delivery(replica_id, replayed_at, change_id);

CREATE TABLE replication_event (
    event_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES database_cluster(cluster_id)
        ON DELETE CASCADE,
    node_id BIGINT
        REFERENCES database_node(node_id)
        ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    lsn BIGINT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX replication_event_cluster_time_idx
    ON replication_event(cluster_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION record_replication_event(
    p_cluster_id BIGINT,
    p_node_id BIGINT,
    p_event_type TEXT,
    p_lsn BIGINT,
    p_details JSONB DEFAULT '{}'::jsonb
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO replication_event (
        cluster_id,
        node_id,
        event_type,
        lsn,
        details
    )
    VALUES (
        p_cluster_id,
        p_node_id,
        p_event_type,
        p_lsn,
        COALESCE(p_details, '{}'::jsonb)
    );
END;
$$;

CREATE OR REPLACE FUNCTION apply_wal_change(
    p_change_id BIGINT,
    p_replica_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_change wal_change%ROWTYPE;
    v_cluster_id BIGINT;
    v_replica database_node%ROWTYPE;
    v_existing_delivery replication_delivery%ROWTYPE;
BEGIN
    SELECT *
    INTO v_change
    FROM wal_change
    WHERE change_id = p_change_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown WAL change %', p_change_id;
    END IF;

    SELECT *
    INTO v_replica
    FROM database_node
    WHERE node_id = p_replica_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown replica %', p_replica_id;
    END IF;

    IF v_replica.role <> 'replica' THEN
        RAISE EXCEPTION 'Node % is not a replica', p_replica_id;
    END IF;

    IF v_replica.state <> 'up' THEN
        RAISE EXCEPTION 'Replica % is down', p_replica_id;
    END IF;

    IF v_replica.cluster_id <> v_change.cluster_id THEN
        RAISE EXCEPTION
            'Replica and WAL change belong to different clusters';
    END IF;

    /*
     * Replay must be ordered. This protects the simulated replica from
     * applying LSN 20 when LSN 19 has not yet been replayed.
     */
    IF v_change.lsn <> v_replica.replayed_lsn + 1 THEN
        RAISE EXCEPTION
            'Replay gap for replica %: expected LSN %, received %',
            p_replica_id,
            v_replica.replayed_lsn + 1,
            v_change.lsn;
    END IF;

    INSERT INTO replication_delivery (
        change_id,
        replica_id,
        received_at
    )
    VALUES (
        p_change_id,
        p_replica_id,
        clock_timestamp()
    )
    ON CONFLICT (change_id, replica_id) DO NOTHING;

    SELECT *
    INTO v_existing_delivery
    FROM replication_delivery
    WHERE change_id = p_change_id
      AND replica_id = p_replica_id
    FOR UPDATE;

    /*
     * The replicated entity table represents the data state on this logical
     * replica. Physical databases would maintain the actual table pages
     * through WAL replay instead.
     */
    IF v_change.operation = 'set' THEN
        INSERT INTO replicated_entity (
            cluster_id,
            entity_key,
            entity_value,
            updated_lsn
        )
        VALUES (
            v_change.cluster_id,
            v_change.entity_key,
            v_change.entity_value,
            v_change.lsn
        )
        ON CONFLICT (cluster_id, entity_key)
        DO UPDATE SET
            entity_value = EXCLUDED.entity_value,
            updated_lsn = EXCLUDED.updated_lsn;
    ELSE
        DELETE FROM replicated_entity
        WHERE cluster_id = v_change.cluster_id
          AND entity_key = v_change.entity_key;
    END IF;

    UPDATE replication_delivery
    SET replayed_at = clock_timestamp()
    WHERE change_id = p_change_id
      AND replica_id = p_replica_id;

    UPDATE database_node
    SET
        received_lsn = GREATEST(received_lsn, v_change.lsn),
        replayed_lsn = v_change.lsn,
        last_heartbeat_at = clock_timestamp()
    WHERE node_id = p_replica_id;

    PERFORM record_replication_event(
        v_change.cluster_id,
        p_replica_id,
        'replay',
        v_change.lsn,
        jsonb_build_object(
            'entity_key', v_change.entity_key,
            'operation', v_change.operation
        )
    );
END;
$$;

CREATE OR REPLACE FUNCTION create_wal_change(
    p_cluster_id BIGINT,
    p_operation change_operation,
    p_entity_key TEXT,
    p_entity_value TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_primary database_node%ROWTYPE;
    v_lsn BIGINT;
    v_transaction_id BIGINT;
    v_change_id BIGINT;
    v_next_lsn BIGINT;
BEGIN
    IF p_entity_key IS NULL OR btrim(p_entity_key) = '' THEN
        RAISE EXCEPTION 'Entity key cannot be empty';
    END IF;

    IF p_operation = 'set' AND p_entity_value IS NULL THEN
        RAISE EXCEPTION 'SET operation requires a value';
    END IF;

    SELECT *
    INTO v_primary
    FROM database_node
    WHERE cluster_id = p_cluster_id
      AND role = 'primary'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Cluster % does not have a primary',
            p_cluster_id;
    END IF;

    IF v_primary.state <> 'up' THEN
        RAISE EXCEPTION
            'Primary node % is down',
            v_primary.node_id;
    END IF;

    SELECT COALESCE(MAX(lsn), 0) + 1
    INTO v_next_lsn
    FROM wal_change
    WHERE cluster_id = p_cluster_id;

    v_lsn := v_next_lsn;

    /*
     * PostgreSQL sequences or the database engine's own WAL machinery would
     * normally provide durable ordering. The simulation uses MAX(lsn)+1
     * because the purpose here is to expose the replication workflow.
     */
    SELECT COALESCE(MAX(transaction_id), 0) + 1
    INTO v_transaction_id
    FROM wal_change
    WHERE cluster_id = p_cluster_id;

    INSERT INTO wal_change (
        cluster_id,
        lsn,
        transaction_id,
        generation,
        operation,
        entity_key,
        entity_value
    )
    VALUES (
        p_cluster_id,
        v_lsn,
        v_transaction_id,
        v_primary.generation,
        p_operation,
        p_entity_key,
        p_entity_value
    )
    RETURNING change_id INTO v_change_id;

    UPDATE database_node
    SET received_lsn = v_lsn,
        last_heartbeat_at = clock_timestamp()
    WHERE node_id = v_primary.node_id;

    PERFORM record_replication_event(
        p_cluster_id,
        v_primary.node_id,
        'primary_write',
        v_lsn,
        jsonb_build_object(
            'operation', p_operation,
            'entity_key', p_entity_key
        )
    );

    RETURN v_change_id;
END;
$$;

CREATE OR REPLACE VIEW replica_health AS
SELECT
    n.node_id,
    c.cluster_name,
    n.node_name,
    n.state,
    n.received_lsn,
    n.replayed_lsn,
    n.received_lsn - n.replayed_lsn AS replay_lag,
    n.last_heartbeat_at
FROM database_node n
JOIN database_cluster c
    ON c.cluster_id = n.cluster_id
WHERE n.role = 'replica';

CREATE OR REPLACE VIEW synchronous_acknowledgement AS
SELECT
    c.cluster_id,
    c.cluster_name,
    c.replication_mode,
    c.synchronous_replicas,
    wc.lsn,
    COUNT(r.node_id) FILTER (
        WHERE r.state = 'up'
          AND r.replayed_lsn >= wc.lsn
    ) AS acknowledged_replicas,
    (
        c.replication_mode = 'asynchronous'
        OR
        COUNT(r.node_id) FILTER (
            WHERE r.state = 'up'
              AND r.replayed_lsn >= wc.lsn
        ) >= c.synchronous_replicas
    ) AS merge_like_commit_eligible
FROM database_cluster c
JOIN wal_change wc
    ON wc.cluster_id = c.cluster_id
LEFT JOIN database_node r
    ON r.cluster_id = c.cluster_id
   AND r.role = 'replica'
GROUP BY
    c.cluster_id,
    c.cluster_name,
    c.replication_mode,
    c.synchronous_replicas,
    wc.lsn;

CREATE OR REPLACE VIEW replication_consistency AS
SELECT
    c.cluster_name,
    n.node_name,
    n.replayed_lsn,
    p.received_lsn AS primary_received_lsn,
    n.replayed_lsn = p.received_lsn AS fully_replayed
FROM database_cluster c
JOIN database_node n
    ON n.cluster_id = c.cluster_id
   AND n.role = 'replica'
JOIN database_node p
    ON p.cluster_id = c.cluster_id
   AND p.role = 'primary';

INSERT INTO database_cluster (
    cluster_name,
    replication_mode,
    synchronous_replicas,
    generation
)
VALUES
    ('orders-cluster', 'asynchronous', 0, 1),
    ('payments-cluster', 'synchronous', 1, 1);

INSERT INTO database_node (
    cluster_id,
    node_name,
    role,
    state,
    generation
)
SELECT
    cluster_id,
    'orders-primary',
    'primary',
    'up',
    generation
FROM database_cluster
WHERE cluster_name = 'orders-cluster';

INSERT INTO database_node (
    cluster_id,
    node_name,
    role,
    state,
    generation
)
SELECT
    cluster_id,
    'orders-replica-a',
    'replica',
    'up',
    generation
FROM database_cluster
WHERE cluster_name = 'orders-cluster';

INSERT INTO database_node (
    cluster_id,
    node_name,
    role,
    state,
    generation
)
SELECT
    cluster_id,
    'orders-replica-b',
    'replica',
    'up',
    generation
FROM database_cluster
WHERE cluster_name = 'orders-cluster';

INSERT INTO database_node (
    cluster_id,
    node_name,
    role,
    state,
    generation
)
SELECT
    cluster_id,
    'payments-primary',
    'primary',
    'up',
    generation
FROM database_cluster
WHERE cluster_name = 'payments-cluster';

INSERT INTO database_node (
    cluster_id,
    node_name,
    role,
    state,
    generation
)
SELECT
    cluster_id,
    'payments-replica-a',
    'replica',
    'up',
    generation
FROM database_cluster
WHERE cluster_name = 'payments-cluster';

DO $$
DECLARE
    v_cluster_id BIGINT;
    v_change_id BIGINT;
    v_replica_a BIGINT;
    v_replica_b BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster_id
    FROM database_cluster
    WHERE cluster_name = 'orders-cluster';

    SELECT node_id INTO v_replica_a
    FROM database_node
    WHERE node_name = 'orders-replica-a';

    SELECT node_id INTO v_replica_b
    FROM database_node
    WHERE node_name = 'orders-replica-b';

    /*
     * Asynchronous example:
     * the primary creates WAL records without requiring immediate replay.
     */
    v_change_id := create_wal_change(
        v_cluster_id,
        'set',
        'order:1001',
        'PAID'
    );

    PERFORM apply_wal_change(v_change_id, v_replica_a);

    v_change_id := create_wal_change(
        v_cluster_id,
        'set',
        'order:1002',
        'SHIPPED'
    );

    /*
     * Replica-b is deliberately not caught up yet, exposing measurable lag.
     */
    PERFORM apply_wal_change(
        v_change_id,
        v_replica_a
    );

    /*
     * Once the replica is ready, it replays the remaining ordered records.
     */
    FOR v_change_id IN
        SELECT wc.change_id
        FROM wal_change wc
        WHERE wc.cluster_id = v_cluster_id
        ORDER BY wc.lsn
    LOOP
        BEGIN
            PERFORM apply_wal_change(v_change_id, v_replica_b);
        EXCEPTION
            WHEN unique_violation THEN
                NULL;
        END;
    END LOOP;
END;
$$;

DO $$
DECLARE
    v_cluster_id BIGINT;
    v_primary BIGINT;
    v_replica BIGINT;
    v_change_id BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster_id
    FROM database_cluster
    WHERE cluster_name = 'payments-cluster';

    SELECT node_id
    INTO v_primary
    FROM database_node
    WHERE cluster_id = v_cluster_id
      AND role = 'primary';

    SELECT node_id
    INTO v_replica
    FROM database_node
    WHERE cluster_id = v_cluster_id
      AND role = 'replica';

    /*
     * Synchronous semantics are represented by replaying the same WAL record
     * before the transaction is considered acknowledged.
     */
    v_change_id := create_wal_change(
        v_cluster_id,
        'set',
        'payment:9001',
        'SETTLED'
    );

    PERFORM apply_wal_change(
        v_change_id,
        v_replica
    );

    IF (
        SELECT replayed_lsn
        FROM database_node
        WHERE node_id = v_replica
    ) <
    (
        SELECT lsn
        FROM wal_change
        WHERE change_id = v_change_id
    ) THEN
        RAISE EXCEPTION
            'Synchronous acknowledgement condition was not met';
    END IF;

    PERFORM record_replication_event(
        v_cluster_id,
        v_primary,
        'synchronous_commit_acknowledged',
        (
            SELECT lsn
            FROM wal_change
            WHERE change_id = v_change_id
        ),
        jsonb_build_object(
            'required_replicas', 1,
            'acknowledged_replicas', 1
        )
    );
END;
$$;

SELECT
    cluster_name,
    replication_mode,
    synchronous_replicas,
    generation
FROM database_cluster
ORDER BY cluster_name;

SELECT *
FROM replica_health
ORDER BY cluster_name, node_name;

SELECT
    cluster_name,
    lsn,
    acknowledged_replicas,
    merge_like_commit_eligible
FROM synchronous_acknowledgement
ORDER BY cluster_name, lsn;

SELECT *
FROM replication_consistency
ORDER BY cluster_name, node_name;

SELECT
    cluster_name,
    node_name,
    received_lsn,
    replayed_lsn,
    replay_lag,
    CASE
        WHEN state = 'down' THEN 'OUTAGE'
        WHEN replay_lag = 0 THEN 'CAUGHT_UP'
        WHEN replay_lag <= 2 THEN 'LOW_LAG'
        ELSE 'HIGH_LAG'
    END AS health_classification
FROM replica_health
ORDER BY cluster_name, node_name;

SELECT
    c.cluster_name,
    wc.lsn,
    wc.transaction_id,
    wc.operation,
    wc.entity_key,
    wc.entity_value,
    wc.generation
FROM wal_change wc
JOIN database_cluster c
    ON c.cluster_id = wc.cluster_id
ORDER BY c.cluster_name, wc.lsn;

SELECT
    c.cluster_name,
    n.node_name,
    e.event_type,
    e.lsn,
    e.details,
    e.occurred_at
FROM replication_event e
JOIN database_cluster c
    ON c.cluster_id = e.cluster_id
LEFT JOIN database_node n
    ON n.node_id = e.node_id
ORDER BY e.occurred_at DESC;
