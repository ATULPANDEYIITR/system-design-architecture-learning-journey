-- ============================================================
-- REDUNDANCY: ACTIVE-ACTIVE AND ACTIVE-PASSIVE ARCHITECTURES
-- PostgreSQL relational model and operational governance engine
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS redundancy;

SET search_path TO redundancy, public;

-- ------------------------------------------------------------
-- 1. DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE architecture_type AS ENUM (
    'ACTIVE_ACTIVE',
    'ACTIVE_PASSIVE'
);

CREATE TYPE node_role AS ENUM (
    'ACTIVE',
    'PASSIVE',
    'FAILED',
    'RECOVERING'
);

CREATE TYPE node_health AS ENUM (
    'HEALTHY',
    'DEGRADED',
    'DOWN'
);

CREATE TYPE replication_mode AS ENUM (
    'SYNCHRONOUS',
    'ASYNCHRONOUS'
);

CREATE TYPE cluster_state AS ENUM (
    'NORMAL',
    'DEGRADED',
    'FAILOVER_IN_PROGRESS',
    'FAILOVER_COMPLETED',
    'UNAVAILABLE'
);

CREATE TYPE failover_status AS ENUM (
    'REQUESTED',
    'PROMOTED',
    'REJECTED',
    'NO_STANDBY'
);

CREATE TYPE operation_type AS ENUM (
    'READ',
    'WRITE'
);

-- ------------------------------------------------------------
-- 2. CLUSTERS
-- ------------------------------------------------------------

CREATE TABLE clusters (
    cluster_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_name VARCHAR(120) NOT NULL UNIQUE,
    architecture architecture_type NOT NULL,
    replication replication_mode NOT NULL,
    cluster_status cluster_state NOT NULL DEFAULT 'NORMAL',
    required_active_nodes INTEGER NOT NULL DEFAULT 1,
    maximum_replication_lag BIGINT NOT NULL DEFAULT 0,
    automatic_failover BOOLEAN NOT NULL DEFAULT TRUE,
    allow_degraded_writes BOOLEAN NOT NULL DEFAULT FALSE,
    fencing_epoch BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT positive_required_nodes
        CHECK (required_active_nodes > 0),

    CONSTRAINT nonnegative_maximum_lag
        CHECK (maximum_replication_lag >= 0),

    CONSTRAINT nonnegative_fencing_epoch
        CHECK (fencing_epoch >= 0)
);

-- ------------------------------------------------------------
-- 3. NODES
-- ------------------------------------------------------------

CREATE TABLE cluster_nodes (
    node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id) ON DELETE CASCADE,

    node_name VARCHAR(120) NOT NULL,
    region VARCHAR(120) NOT NULL,
    role node_role NOT NULL,
    health node_health NOT NULL DEFAULT 'HEALTHY',

    capacity INTEGER NOT NULL,
    current_load INTEGER NOT NULL DEFAULT 0,

    last_applied_sequence BIGINT NOT NULL DEFAULT 0,
    replication_lag BIGINT NOT NULL DEFAULT 0,

    fencing_epoch BIGINT NOT NULL DEFAULT 0,

    last_heartbeat TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_node_name
        UNIQUE(cluster_id, node_name),

    CONSTRAINT positive_capacity
        CHECK (capacity > 0),

    CONSTRAINT valid_load
        CHECK (
            current_load >= 0
            AND current_load <= capacity
        ),

    CONSTRAINT nonnegative_node_sequence
        CHECK (last_applied_sequence >= 0),

    CONSTRAINT nonnegative_node_lag
        CHECK (replication_lag >= 0),

    CONSTRAINT nonnegative_node_epoch
        CHECK (fencing_epoch >= 0)
);

CREATE INDEX idx_nodes_cluster_role_health
ON cluster_nodes(cluster_id, role, health);

CREATE INDEX idx_nodes_replication_lag
ON cluster_nodes(cluster_id, replication_lag);

-- ------------------------------------------------------------
-- 4. WRITE LOG
-- ------------------------------------------------------------

CREATE TABLE replication_log (
    log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id) ON DELETE CASCADE,

    sequence_number BIGINT NOT NULL,
    source_node_id BIGINT NOT NULL
        REFERENCES cluster_nodes(node_id),

    record_key VARCHAR(255) NOT NULL,
    record_value JSONB NOT NULL,

    committed BOOLEAN NOT NULL DEFAULT FALSE,
    committed_at TIMESTAMPTZ,

    CONSTRAINT unique_cluster_sequence
        UNIQUE(cluster_id, sequence_number),

    CONSTRAINT positive_sequence
        CHECK (sequence_number > 0)
);

CREATE INDEX idx_replication_log_sequence
ON replication_log(cluster_id, sequence_number);

CREATE INDEX idx_replication_log_key
ON replication_log(cluster_id, record_key);

-- ------------------------------------------------------------
-- 5. COMMITTED APPLICATION DATA
-- ------------------------------------------------------------

CREATE TABLE cluster_data (
    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id) ON DELETE CASCADE,

    record_key VARCHAR(255) NOT NULL,
    record_value JSONB NOT NULL,

    sequence_number BIGINT NOT NULL,
    source_node_id BIGINT NOT NULL
        REFERENCES cluster_nodes(node_id),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY(cluster_id, record_key),

    CONSTRAINT positive_data_sequence
        CHECK (sequence_number > 0)
);

CREATE INDEX idx_cluster_data_sequence
ON cluster_data(cluster_id, sequence_number);

-- ------------------------------------------------------------
-- 6. FAILOVER HISTORY
-- ------------------------------------------------------------

CREATE TABLE failover_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    failed_node_id BIGINT
        REFERENCES cluster_nodes(node_id),

    promoted_node_id BIGINT
        REFERENCES cluster_nodes(node_id),

    status failover_status NOT NULL,
    fencing_epoch BIGINT NOT NULL,

    failure_reason TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    CONSTRAINT valid_failover_epoch
        CHECK (fencing_epoch >= 0),

    CONSTRAINT promoted_node_required
        CHECK (
            status <> 'PROMOTED'
            OR promoted_node_id IS NOT NULL
        )
);

CREATE INDEX idx_failover_cluster_time
ON failover_events(cluster_id, started_at DESC);

-- ------------------------------------------------------------
-- 7. OPERATION AUDIT
-- ------------------------------------------------------------

CREATE TABLE operation_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    node_id BIGINT
        REFERENCES cluster_nodes(node_id),

    operation operation_type NOT NULL,
    record_key VARCHAR(255) NOT NULL,

    success BOOLEAN NOT NULL,
    failure_reason TEXT,

    sequence_number BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_operation_audit_cluster_time
ON operation_audit(cluster_id, created_at DESC);

-- ------------------------------------------------------------
-- 8. DATA INTEGRITY TRIGGERS
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_node_role()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    architecture architecture_type;
BEGIN
    SELECT c.architecture
    INTO architecture
    FROM clusters c
    WHERE c.cluster_id = NEW.cluster_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cluster does not exist';
    END IF;

    IF architecture = 'ACTIVE_ACTIVE'
       AND NEW.role = 'PASSIVE' THEN
        RAISE EXCEPTION
            'Active-active nodes cannot be assigned PASSIVE role';
    END IF;

    IF NEW.role = 'FAILED'
       AND NEW.health <> 'DOWN' THEN
        RAISE EXCEPTION
            'A FAILED node must have DOWN health';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_node_role
BEFORE INSERT OR UPDATE OF role, health, cluster_id
ON cluster_nodes
FOR EACH ROW
EXECUTE FUNCTION validate_node_role();

-- ------------------------------------------------------------
-- 9. NODE INVENTORY AND ELIGIBILITY VIEWS
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW node_inventory AS
SELECT
    c.cluster_id,
    c.cluster_name,
    c.architecture,
    c.cluster_status,
    n.node_id,
    n.node_name,
    n.region,
    n.role,
    n.health,
    n.capacity,
    n.current_load,
    n.last_applied_sequence,
    n.replication_lag,
    n.fencing_epoch,
    CASE
        WHEN n.health = 'DOWN' THEN FALSE
        WHEN n.current_load >= n.capacity THEN FALSE
        ELSE TRUE
    END AS available
FROM clusters c
JOIN cluster_nodes n
    ON n.cluster_id = c.cluster_id;

CREATE OR REPLACE VIEW cluster_availability AS
SELECT
    c.cluster_id,
    c.cluster_name,
    c.architecture,
    c.required_active_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.role = 'ACTIVE'
          AND n.health <> 'DOWN'
          AND n.current_load < n.capacity
    ) AS available_active_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.role = 'PASSIVE'
          AND n.health = 'HEALTHY'
    ) AS healthy_standby_nodes,

    CASE
        WHEN COUNT(n.node_id) FILTER (
            WHERE n.role = 'ACTIVE'
              AND n.health <> 'DOWN'
              AND n.current_load < n.capacity
        ) >= c.required_active_nodes
        THEN TRUE
        ELSE FALSE
    END AS availability_requirement_met

FROM clusters c
LEFT JOIN cluster_nodes n
    ON n.cluster_id = c.cluster_id
GROUP BY
    c.cluster_id,
    c.cluster_name,
    c.architecture,
    c.required_active_nodes;

-- ------------------------------------------------------------
-- 10. CLUSTER INITIALIZATION VALIDATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_cluster_configuration(
    p_cluster_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_architecture architecture_type;
    v_required INTEGER;
    v_active INTEGER;
    v_passive INTEGER;
BEGIN
    SELECT architecture, required_active_nodes
    INTO v_architecture, v_required
    FROM clusters
    WHERE cluster_id = p_cluster_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown cluster: %', p_cluster_id;
    END IF;

    SELECT
        COUNT(*) FILTER (
            WHERE role = 'ACTIVE'
              AND health = 'HEALTHY'
        ),
        COUNT(*) FILTER (
            WHERE role = 'PASSIVE'
              AND health = 'HEALTHY'
        )
    INTO v_active, v_passive
    FROM cluster_nodes
    WHERE cluster_id = p_cluster_id;

    IF v_architecture = 'ACTIVE_ACTIVE'
       AND v_active < v_required THEN
        RAISE EXCEPTION
            'Active-active cluster requires % healthy active nodes',
            v_required;
    END IF;

    IF v_architecture = 'ACTIVE_PASSIVE'
       AND (v_active <> 1 OR v_passive < 1) THEN
        RAISE EXCEPTION
            'Active-passive cluster requires exactly one active node and at least one healthy standby';
    END IF;

    RETURN TRUE;
END;
$$;

-- ------------------------------------------------------------
-- 11. TRANSACTIONAL WRITE OPERATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION write_cluster_data(
    p_cluster_id BIGINT,
    p_node_id BIGINT,
    p_key VARCHAR(255),
    p_value JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_architecture architecture_type;
    v_replication replication_mode;
    v_degraded_writes BOOLEAN;

    v_node cluster_nodes%ROWTYPE;
    v_replica_count INTEGER;
    v_sequence BIGINT;
    v_epoch BIGINT;
BEGIN
    IF p_key IS NULL OR LENGTH(TRIM(p_key)) = 0 THEN
        RAISE EXCEPTION 'Record key is required';
    END IF;

    IF p_value IS NULL THEN
        RAISE EXCEPTION 'Record value cannot be NULL';
    END IF;

    SELECT
        architecture,
        replication,
        allow_degraded_writes
    INTO
        v_architecture,
        v_replication,
        v_degraded_writes
    FROM clusters
    WHERE cluster_id = p_cluster_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown cluster';
    END IF;

    SELECT *
    INTO v_node
    FROM cluster_nodes
    WHERE node_id = p_node_id
      AND cluster_id = p_cluster_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Node does not belong to cluster';
    END IF;

    IF v_node.role <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Only active nodes can accept writes';
    END IF;

    IF v_node.health = 'DOWN' THEN
        RAISE EXCEPTION 'Failed node cannot accept writes';
    END IF;

    IF v_node.health = 'DEGRADED'
       AND NOT v_degraded_writes THEN
        RAISE EXCEPTION 'Writes disabled for degraded node';
    END IF;

    IF v_node.current_load >= v_node.capacity THEN
        RAISE EXCEPTION 'Node capacity exceeded';
    END IF;

    -- Locking the cluster row serializes sequence allocation
    -- for this demonstration. Higher-throughput systems can
    -- use dedicated sequence allocation and partitioned logs.

    UPDATE clusters
    SET fencing_epoch = fencing_epoch
    WHERE cluster_id = p_cluster_id
    RETURNING fencing_epoch INTO v_epoch;

    IF v_replication = 'SYNCHRONOUS' THEN
        SELECT COUNT(*)
        INTO v_replica_count
        FROM cluster_nodes
        WHERE cluster_id = p_cluster_id
          AND node_id <> p_node_id
          AND health = 'HEALTHY'
          AND (
              v_architecture = 'ACTIVE_ACTIVE'
              OR role = 'PASSIVE'
          );

        IF v_replica_count = 0 THEN
            RAISE EXCEPTION
                'Synchronous replication requires an available replica';
        END IF;
    END IF;

    SELECT COALESCE(MAX(sequence_number), 0) + 1
    INTO v_sequence
    FROM replication_log
    WHERE cluster_id = p_cluster_id;

    INSERT INTO replication_log (
        cluster_id,
        sequence_number,
        source_node_id,
        record_key,
        record_value,
        committed
    )
    VALUES (
        p_cluster_id,
        v_sequence,
        p_node_id,
        p_key,
        p_value,
        FALSE
    );

    IF v_replication = 'SYNCHRONOUS' THEN
        UPDATE cluster_nodes
        SET last_applied_sequence = v_sequence,
            replication_lag = 0
        WHERE cluster_id = p_cluster_id
          AND node_id <> p_node_id
          AND health = 'HEALTHY'
          AND (
              v_architecture = 'ACTIVE_ACTIVE'
              OR role = 'PASSIVE'
          );
    ELSE
        UPDATE cluster_nodes
        SET replication_lag = replication_lag + 1
        WHERE cluster_id = p_cluster_id
          AND node_id <> p_node_id
          AND health <> 'DOWN'
          AND (
              v_architecture = 'ACTIVE_ACTIVE'
              OR role = 'PASSIVE'
          );
    END IF;

    INSERT INTO cluster_data (
        cluster_id,
        record_key,
        record_value,
        sequence_number,
        source_node_id
    )
    VALUES (
        p_cluster_id,
        p_key,
        p_value,
        v_sequence,
        p_node_id
    )
    ON CONFLICT (cluster_id, record_key)
    DO UPDATE SET
        record_value = EXCLUDED.record_value,
        sequence_number = EXCLUDED.sequence_number,
        source_node_id = EXCLUDED.source_node_id,
        updated_at = CURRENT_TIMESTAMP;

    UPDATE cluster_nodes
    SET last_applied_sequence = v_sequence
    WHERE node_id = p_node_id;

    UPDATE replication_log
    SET committed = TRUE,
        committed_at = CURRENT_TIMESTAMP
    WHERE cluster_id = p_cluster_id
      AND sequence_number = v_sequence;

    INSERT INTO operation_audit (
        cluster_id,
        node_id,
        operation,
        record_key,
        success,
        sequence_number
    )
    VALUES (
        p_cluster_id,
        p_node_id,
        'WRITE',
        p_key,
        TRUE,
        v_sequence
    );

    RETURN v_sequence;
END;
$$;

-- ------------------------------------------------------------
-- 12. REPLICA SYNCHRONIZATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION synchronize_replica(
    p_cluster_id BIGINT,
    p_node_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_node cluster_nodes%ROWTYPE;
    v_applied INTEGER;
    v_latest BIGINT;
BEGIN
    SELECT *
    INTO v_node
    FROM cluster_nodes
    WHERE cluster_id = p_cluster_id
      AND node_id = p_node_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown replica';
    END IF;

    IF v_node.health = 'DOWN' THEN
        RAISE EXCEPTION 'Cannot synchronize a failed node';
    END IF;

    INSERT INTO cluster_data (
        cluster_id,
        record_key,
        record_value,
        sequence_number,
        source_node_id
    )
    SELECT DISTINCT ON (record_key)
        cluster_id,
        record_key,
        record_value,
        sequence_number,
        source_node_id
    FROM replication_log
    WHERE cluster_id = p_cluster_id
      AND committed = TRUE
      AND sequence_number > v_node.last_applied_sequence
    ORDER BY record_key, sequence_number DESC

    ON CONFLICT (cluster_id, record_key)
    DO UPDATE SET
        record_value = EXCLUDED.record_value,
        sequence_number = EXCLUDED.sequence_number,
        source_node_id = EXCLUDED.source_node_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE cluster_data.sequence_number < EXCLUDED.sequence_number;

    GET DIAGNOSTICS v_applied = ROW_COUNT;

    SELECT COALESCE(MAX(sequence_number), 0)
    INTO v_latest
    FROM replication_log
    WHERE cluster_id = p_cluster_id
      AND committed = TRUE;

    UPDATE cluster_nodes
    SET last_applied_sequence = v_latest,
        replication_lag = 0,
        health = 'HEALTHY'
    WHERE node_id = p_node_id;

    RETURN v_applied;
END;
$$;

-- ------------------------------------------------------------
-- 13. FAILOVER PROCESSING
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION process_failover(
    p_cluster_id BIGINT,
    p_failed_node_id BIGINT
)
RETURNS TABLE (
    successful BOOLEAN,
    promoted_node BIGINT,
    message TEXT,
    new_epoch BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_cluster clusters%ROWTYPE;
    v_candidate cluster_nodes%ROWTYPE;
    v_latest BIGINT;
    v_epoch BIGINT;
BEGIN
    SELECT *
    INTO v_cluster
    FROM clusters
    WHERE cluster_id = p_cluster_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown cluster';
    END IF;

    PERFORM 1
    FROM cluster_nodes
    WHERE node_id = p_failed_node_id
      AND cluster_id = p_cluster_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Failed node does not belong to cluster';
    END IF;

    UPDATE cluster_nodes
    SET health = 'DOWN',
        role = 'FAILED',
        current_load = 0
    WHERE node_id = p_failed_node_id;

    IF v_cluster.architecture = 'ACTIVE_ACTIVE' THEN

        SELECT COUNT(*)
        INTO v_latest
        FROM cluster_nodes
        WHERE cluster_id = p_cluster_id
          AND role = 'ACTIVE'
          AND health <> 'DOWN'
          AND current_load < capacity;

        IF v_latest >= v_cluster.required_active_nodes THEN
            RETURN QUERY
            SELECT TRUE, NULL::BIGINT,
                   'Remaining active nodes satisfy policy',
                   v_cluster.fencing_epoch;
        ELSE
            UPDATE clusters
            SET cluster_status = 'UNAVAILABLE'
            WHERE cluster_id = p_cluster_id;

            RETURN QUERY
            SELECT FALSE, NULL::BIGINT,
                   'Active node requirement violated',
                   v_cluster.fencing_epoch;
        END IF;

        RETURN;
    END IF;

    IF NOT v_cluster.automatic_failover THEN
        UPDATE clusters
        SET cluster_status = 'UNAVAILABLE'
        WHERE cluster_id = p_cluster_id;

        INSERT INTO failover_events (
            cluster_id,
            failed_node_id,
            status,
            fencing_epoch,
            failure_reason
        )
        VALUES (
            p_cluster_id,
            p_failed_node_id,
            'REJECTED',
            v_cluster.fencing_epoch,
            'Automatic failover disabled'
        );

        RETURN QUERY
        SELECT FALSE, NULL::BIGINT,
               'Manual intervention required',
               v_cluster.fencing_epoch;

        RETURN;
    END IF;

    SELECT COALESCE(MAX(sequence_number), 0)
    INTO v_latest
    FROM replication_log
    WHERE cluster_id = p_cluster_id
      AND committed = TRUE;

    UPDATE clusters
    SET cluster_status = 'FAILOVER_IN_PROGRESS'
    WHERE cluster_id = p_cluster_id;

    SELECT *
    INTO v_candidate
    FROM cluster_nodes
    WHERE cluster_id = p_cluster_id
      AND role = 'PASSIVE'
      AND health = 'HEALTHY'
      AND replication_lag <= v_cluster.maximum_replication_lag
      AND (
          v_cluster.replication <> 'SYNCHRONOUS'
          OR last_applied_sequence = v_latest
      )
    ORDER BY
        last_applied_sequence DESC,
        capacity DESC
    LIMIT 1
    FOR UPDATE;

    IF NOT FOUND THEN
        UPDATE clusters
        SET cluster_status = 'UNAVAILABLE'
        WHERE cluster_id = p_cluster_id;

        INSERT INTO failover_events (
            cluster_id,
            failed_node_id,
            status,
            fencing_epoch,
            failure_reason
        )
        VALUES (
            p_cluster_id,
            p_failed_node_id,
            'NO_STANDBY',
            v_cluster.fencing_epoch,
            'No eligible standby node'
        );

        RETURN QUERY
        SELECT FALSE, NULL::BIGINT,
               'No eligible standby node',
               v_cluster.fencing_epoch;

        RETURN;
    END IF;

    v_epoch := v_cluster.fencing_epoch + 1;

    -- Updating the epoch invalidates the former primary's token.
    UPDATE clusters
    SET fencing_epoch = v_epoch,
        cluster_status = 'FAILOVER_COMPLETED'
    WHERE cluster_id = p_cluster_id;

    UPDATE cluster_nodes
    SET role = 'ACTIVE',
        fencing_epoch = v_epoch,
        replication_lag = 0
    WHERE node_id = v_candidate.node_id;

    INSERT INTO failover_events (
        cluster_id,
        failed_node_id,
        promoted_node_id,
        status,
        fencing_epoch,
        completed_at
    )
    VALUES (
        p_cluster_id,
        p_failed_node_id,
        v_candidate.node_id,
        'PROMOTED',
        v_epoch,
        CURRENT_TIMESTAMP
    );

    RETURN QUERY
    SELECT TRUE,
           v_candidate.node_id,
           'Standby successfully promoted',
           v_epoch;
END;
$$;

-- ------------------------------------------------------------
-- 14. MERGE-FREE REPLICA ELIGIBILITY REPORT
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW failover_eligibility AS
SELECT
    c.cluster_id,
    c.cluster_name,
    n.node_id,
    n.node_name,
    n.last_applied_sequence,
    n.replication_lag,
    c.maximum_replication_lag,

    CASE
        WHEN n.role <> 'PASSIVE' THEN FALSE
        WHEN n.health <> 'HEALTHY' THEN FALSE
        WHEN n.replication_lag > c.maximum_replication_lag THEN FALSE
        WHEN c.replication = 'SYNCHRONOUS'
             AND n.last_applied_sequence <>
                 COALESCE((
                     SELECT MAX(r.sequence_number)
                     FROM replication_log r
                     WHERE r.cluster_id = c.cluster_id
                       AND r.committed = TRUE
                 ), 0)
        THEN FALSE
        ELSE TRUE
    END AS eligible_for_promotion

FROM clusters c
JOIN cluster_nodes n
    ON n.cluster_id = c.cluster_id
WHERE c.architecture = 'ACTIVE_PASSIVE';

-- ------------------------------------------------------------
-- 15. OPERATIONAL REPORTING
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW cluster_performance_report AS
SELECT
    c.cluster_id,
    c.cluster_name,
    c.architecture,
    c.replication,
    c.cluster_status,

    COUNT(n.node_id) AS total_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.role = 'ACTIVE'
          AND n.health = 'HEALTHY'
    ) AS healthy_active_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.role = 'PASSIVE'
          AND n.health = 'HEALTHY'
    ) AS healthy_passive_nodes,

    MAX(n.replication_lag) AS maximum_observed_lag,

    COALESCE(
        AVG(n.current_load::NUMERIC / n.capacity),
        0
    ) AS average_capacity_utilization,

    COUNT(DISTINCT f.event_id) AS failover_events

FROM clusters c
LEFT JOIN cluster_nodes n
    ON n.cluster_id = c.cluster_id
LEFT JOIN failover_events f
    ON f.cluster_id = c.cluster_id
GROUP BY
    c.cluster_id,
    c.cluster_name,
    c.architecture,
    c.replication,
    c.cluster_status;

-- ------------------------------------------------------------
-- 16. SAMPLE CLUSTER CONFIGURATIONS
-- ------------------------------------------------------------

INSERT INTO clusters (
    cluster_name,
    architecture,
    replication,
    required_active_nodes,
    maximum_replication_lag,
    automatic_failover
)
VALUES
(
    'payment-active-active',
    'ACTIVE_ACTIVE',
    'ASYNCHRONOUS',
    2,
    5,
    TRUE
),
(
    'inventory-active-passive',
    'ACTIVE_PASSIVE',
    'SYNCHRONOUS',
    1,
    0,
    TRUE
),
(
    'reporting-active-passive',
    'ACTIVE_PASSIVE',
    'ASYNCHRONOUS',
    1,
    3,
    TRUE
);

-- ------------------------------------------------------------
-- 17. SAMPLE NODES
-- ------------------------------------------------------------

INSERT INTO cluster_nodes (
    cluster_id,
    node_name,
    region,
    role,
    health,
    capacity
)
SELECT
    c.cluster_id,
    n.node_name,
    n.region,
    n.role::node_role,
    'HEALTHY',
    n.capacity
FROM clusters c
CROSS JOIN (
    VALUES
    ('payment-active-active', 'AA-MUMBAI', 'Mumbai',
        'ACTIVE', 100),
    ('payment-active-active', 'AA-PUNE', 'Pune',
        'ACTIVE', 100),
    ('payment-active-active', 'AA-DELHI', 'Delhi',
        'ACTIVE', 100),

    ('inventory-active-passive', 'AP-MUMBAI', 'Mumbai',
        'ACTIVE', 200),
    ('inventory-active-passive', 'AP-PUNE', 'Pune',
        'PASSIVE', 200),
    ('inventory-active-passive', 'AP-DELHI', 'Delhi',
        'PASSIVE', 150),

    ('reporting-active-passive', 'RP-MUMBAI', 'Mumbai',
        'ACTIVE', 100),
    ('reporting-active-passive', 'RP-PUNE', 'Pune',
        'PASSIVE', 100)
) AS n(
    cluster_name,
    node_name,
    region,
    role,
    capacity
)
WHERE c.cluster_name = n.cluster_name;

-- ------------------------------------------------------------
-- 18. INITIAL CONFIGURATION VALIDATION
-- ------------------------------------------------------------

SELECT validate_cluster_configuration(cluster_id)
FROM clusters
ORDER BY cluster_id;

-- ------------------------------------------------------------
-- 19. SYNCHRONOUS ACTIVE-PASSIVE WRITES
-- ------------------------------------------------------------

DO $$
DECLARE
    v_cluster BIGINT;
    v_primary BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster
    FROM clusters
    WHERE cluster_name = 'inventory-active-passive';

    SELECT node_id
    INTO v_primary
    FROM cluster_nodes
    WHERE cluster_id = v_cluster
      AND role = 'ACTIVE';

    PERFORM write_cluster_data(
        v_cluster,
        v_primary,
        'product:1001',
        '{"quantity":500,"status":"AVAILABLE"}'::JSONB
    );

    PERFORM write_cluster_data(
        v_cluster,
        v_primary,
        'product:1002',
        '{"quantity":250,"status":"AVAILABLE"}'::JSONB
    );
END;
$$;

-- ------------------------------------------------------------
-- 20. ASYNCHRONOUS ACTIVE-ACTIVE WRITES
-- ------------------------------------------------------------

DO $$
DECLARE
    v_cluster BIGINT;
    v_node BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster
    FROM clusters
    WHERE cluster_name = 'payment-active-active';

    SELECT node_id
    INTO v_node
    FROM cluster_nodes
    WHERE cluster_id = v_cluster
      AND node_name = 'AA-MUMBAI';

    PERFORM write_cluster_data(
        v_cluster,
        v_node,
        'payment:5001',
        '{"amount":1500,"status":"CONFIRMED"}'::JSONB
    );
END;
$$;

-- ------------------------------------------------------------
-- 21. RETRIEVAL QUERIES
-- ------------------------------------------------------------

SELECT *
FROM node_inventory
ORDER BY cluster_name, node_name;

SELECT
    c.cluster_name,
    d.record_key,
    d.record_value,
    d.sequence_number,
    d.updated_at
FROM clusters c
JOIN cluster_data d
    ON d.cluster_id = c.cluster_id
ORDER BY c.cluster_name, d.record_key;

-- ------------------------------------------------------------
-- 22. REPLICATION LAG VALIDATION
-- ------------------------------------------------------------

SELECT
    cluster_name,
    node_name,
    last_applied_sequence,
    replication_lag,
    maximum_replication_lag,
    replication_lag <= maximum_replication_lag AS within_policy
FROM clusters c
JOIN cluster_nodes n
    ON n.cluster_id = c.cluster_id
ORDER BY cluster_name, node_name;

-- ------------------------------------------------------------
-- 23. ELIGIBILITY DETERMINATION
-- ------------------------------------------------------------

SELECT *
FROM failover_eligibility
ORDER BY cluster_name, node_name;

-- ------------------------------------------------------------
-- 24. SIMULATED PRIMARY FAILURE
-- ------------------------------------------------------------

DO $$
DECLARE
    v_cluster BIGINT;
    v_primary BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster
    FROM clusters
    WHERE cluster_name = 'inventory-active-passive';

    SELECT node_id
    INTO v_primary
    FROM cluster_nodes
    WHERE cluster_id = v_cluster
      AND node_name = 'AP-MUMBAI';

    -- The complete failover operation executes atomically.
    PERFORM *
    FROM process_failover(v_cluster, v_primary);
END;
$$;

-- ------------------------------------------------------------
-- 25. REPORT PROMOTED NODE
-- ------------------------------------------------------------

SELECT *
FROM node_inventory
WHERE cluster_name = 'inventory-active-passive'
ORDER BY node_name;

SELECT *
FROM failover_events
ORDER BY started_at DESC;

-- ------------------------------------------------------------
-- 26. RECOVERY AND REPLICATION
-- ------------------------------------------------------------

DO $$
DECLARE
    v_cluster BIGINT;
    v_recovered_node BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster
    FROM clusters
    WHERE cluster_name = 'inventory-active-passive';

    SELECT node_id
    INTO v_recovered_node
    FROM cluster_nodes
    WHERE cluster_id = v_cluster
      AND node_name = 'AP-MUMBAI';

    UPDATE cluster_nodes
    SET health = 'RECOVERING',
        role = 'RECOVERING'
    WHERE node_id = v_recovered_node;

    PERFORM synchronize_replica(
        v_cluster,
        v_recovered_node
    );

    -- A recovered former primary rejoins as passive.
    UPDATE cluster_nodes
    SET role = 'PASSIVE',
        health = 'HEALTHY'
    WHERE node_id = v_recovered_node;
END;
$$;

-- ------------------------------------------------------------
-- 27. AGGREGATION AND PERFORMANCE REPORTING
-- ------------------------------------------------------------

SELECT *
FROM cluster_performance_report
ORDER BY cluster_name;

SELECT
    c.cluster_name,
    COUNT(a.audit_id) AS total_operations,
    COUNT(a.audit_id) FILTER (
        WHERE a.operation = 'WRITE'
    ) AS write_operations,
    COUNT(a.audit_id) FILTER (
        WHERE a.success = TRUE
    ) AS successful_operations,
    COUNT(a.audit_id) FILTER (
        WHERE a.success = FALSE
    ) AS failed_operations
FROM clusters c
LEFT JOIN operation_audit a
    ON a.cluster_id = c.cluster_id
GROUP BY c.cluster_id, c.cluster_name
ORDER BY c.cluster_name;

-- ------------------------------------------------------------
-- 28. COMMON TABLE EXPRESSION: NODE CAPACITY ANALYSIS
-- ------------------------------------------------------------

WITH node_capacity AS (
    SELECT
        cluster_id,
        node_name,
        role,
        capacity,
        current_load,
        capacity - current_load AS remaining_capacity,
        ROUND(
            current_load::NUMERIC / capacity * 100,
            2
        ) AS utilization_percentage
    FROM cluster_nodes
)
SELECT
    c.cluster_name,
    nc.node_name,
    nc.role,
    nc.remaining_capacity,
    nc.utilization_percentage
FROM node_capacity nc
JOIN clusters c
    ON c.cluster_id = nc.cluster_id
ORDER BY
    c.cluster_name,
    nc.utilization_percentage DESC;

-- ------------------------------------------------------------
-- 29. FAILURE CASE: INVALID NODE LOAD
-- Demonstrates CHECK constraint enforcement.
-- ------------------------------------------------------------

-- The following statement is intentionally disabled:
-- UPDATE cluster_nodes
-- SET current_load = capacity + 1
-- WHERE node_name = 'AA-MUMBAI';

-- The database rejects the update through valid_load.

-- ------------------------------------------------------------
-- 30. FAILURE CASE: INELIGIBLE PROMOTION
-- A passive node with excessive replication lag must not
-- be promoted under the configured policy.
-- ------------------------------------------------------------

DO $$
DECLARE
    v_cluster BIGINT;
    v_node BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster
    FROM clusters
    WHERE cluster_name = 'reporting-active-passive';

    SELECT node_id
    INTO v_node
    FROM cluster_nodes
    WHERE cluster_id = v_cluster
      AND node_name = 'RP-PUNE';

    UPDATE cluster_nodes
    SET replication_lag = 100
    WHERE node_id = v_node;

    RAISE NOTICE
        'Promotion eligibility for RP-PUNE:';

    PERFORM *
    FROM failover_eligibility
    WHERE cluster_id = v_cluster;
END;
$$;

-- ------------------------------------------------------------
-- 31. TRANSACTION ROLLBACK DEMONSTRATION
-- ------------------------------------------------------------

BEGIN;

DO $$
DECLARE
    v_cluster BIGINT;
    v_primary BIGINT;
BEGIN
    SELECT cluster_id
    INTO v_cluster
    FROM clusters
    WHERE cluster_name = 'payment-active-active';

    SELECT node_id
    INTO v_primary
    FROM cluster_nodes
    WHERE cluster_id = v_cluster
      AND node_name = 'AA-MUMBAI';

    PERFORM write_cluster_data(
        v_cluster,
        v_primary,
        'payment:ROLLBACK-TEST',
        '{"status":"TEMPORARY"}'::JSONB
    );
END;
$$;

ROLLBACK;

-- ------------------------------------------------------------
-- 32. FINAL CONSISTENCY AND OPERATIONAL CHECKS
-- ------------------------------------------------------------

SELECT
    c.cluster_name,
    r.sequence_number,
    r.record_key,
    r.committed
FROM replication_log r
JOIN clusters c
    ON c.cluster_id = r.cluster_id
ORDER BY c.cluster_name, r.sequence_number;

SELECT *
FROM cluster_availability
ORDER BY cluster_name;

SELECT *
FROM cluster_performance_report
ORDER BY cluster_name;

COMMIT;
