-- Consistency Models: Strong, Eventual, and Causal Consistency
-- PostgreSQL 15+.
--
-- This schema models a regional incident-management service. The database
-- stores operations and causal metadata so application services can evaluate
-- visibility, detect missing dependencies, and audit replication.
--
-- Important distinction:
-- PostgreSQL transactions provide ACID guarantees within a database.
-- This schema does not itself implement distributed consensus between
-- independent PostgreSQL clusters. Strong consistency across regions requires
-- a correctly configured consensus or synchronous replication protocol.

BEGIN;

DROP SCHEMA IF EXISTS consistency_lab CASCADE;
CREATE SCHEMA consistency_lab;
SET search_path TO consistency_lab, public;

CREATE TYPE consistency_model AS ENUM (
    'strong',
    'eventual',
    'causal'
);

CREATE TYPE operation_status AS ENUM (
    'accepted',
    'pending',
    'applied',
    'rejected'
);

CREATE TYPE replica_status AS ENUM (
    'available',
    'partitioned',
    'recovering'
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    consistency consistency_model NOT NULL,
    authoritative_region TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        consistency <> 'strong'
        OR authoritative_region IS NOT NULL
    )
);

CREATE TABLE replicas (
    replica_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    region_code TEXT NOT NULL,
    status replica_status NOT NULL DEFAULT 'available',
    applied_sequence BIGINT NOT NULL DEFAULT 0,
    last_heartbeat TIMESTAMPTZ,
    UNIQUE (repository_id, region_code),
    CHECK (applied_sequence >= 0)
);

CREATE TABLE consistency_operations (
    operation_id UUID PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    origin_replica_id BIGINT NOT NULL
        REFERENCES replicas(replica_id),
    entity_key TEXT NOT NULL,
    entity_value JSONB,
    is_tombstone BOOLEAN NOT NULL DEFAULT FALSE,
    operation_sequence BIGINT NOT NULL,
    vector_clock JSONB NOT NULL DEFAULT '{}'::jsonb,
    causal_dependencies JSONB NOT NULL DEFAULT '{}'::jsonb,
    status operation_status NOT NULL DEFAULT 'accepted',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (origin_replica_id, operation_sequence),
    CHECK (operation_sequence > 0),
    CHECK (jsonb_typeof(vector_clock) = 'object'),
    CHECK (jsonb_typeof(causal_dependencies) = 'object'),
    CHECK (
        NOT is_tombstone OR entity_value IS NULL
    )
);

CREATE INDEX idx_operations_repository_key_time
    ON consistency_operations (
        repository_id, entity_key, created_at DESC
    );

CREATE INDEX idx_operations_pending
    ON consistency_operations (repository_id, created_at)
    WHERE status = 'pending';

CREATE INDEX idx_operations_vector_clock
    ON consistency_operations USING GIN (vector_clock jsonb_path_ops);

CREATE TABLE replica_operation_receipts (
    replica_id BIGINT NOT NULL
        REFERENCES replicas(replica_id) ON DELETE CASCADE,
    operation_id UUID NOT NULL
        REFERENCES consistency_operations(operation_id) ON DELETE CASCADE,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    apply_error TEXT,
    PRIMARY KEY (replica_id, operation_id),
    CHECK (
        applied_at IS NULL OR apply_error IS NULL
    )
);

CREATE INDEX idx_receipts_unapplied
    ON replica_operation_receipts (replica_id, received_at)
    WHERE applied_at IS NULL;

CREATE TABLE entity_versions (
    replica_id BIGINT NOT NULL
        REFERENCES replicas(replica_id) ON DELETE CASCADE,
    entity_key TEXT NOT NULL,
    operation_id UUID NOT NULL
        REFERENCES consistency_operations(operation_id),
    entity_value JSONB,
    is_tombstone BOOLEAN NOT NULL DEFAULT FALSE,
    vector_clock JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (replica_id, entity_key),
    CHECK (
        NOT is_tombstone OR entity_value IS NULL
    )
);

CREATE TABLE causal_dependencies (
    operation_id UUID NOT NULL
        REFERENCES consistency_operations(operation_id) ON DELETE CASCADE,
    depends_on_operation_id UUID NOT NULL
        REFERENCES consistency_operations(operation_id),
    PRIMARY KEY (operation_id, depends_on_operation_id),
    CHECK (operation_id <> depends_on_operation_id)
);

CREATE INDEX idx_causal_dependency_parent
    ON causal_dependencies (depends_on_operation_id);

CREATE TABLE consistency_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,
    replica_id BIGINT REFERENCES replicas(replica_id),
    operation_id UUID REFERENCES consistency_operations(operation_id),
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_consistency_events_repository_time
    ON consistency_events (repository_id, occurred_at DESC);

-- Vector-clock comparison is componentwise. Missing counters are treated
-- as zero. Invalid nonnumeric counters are rejected by the function.
CREATE FUNCTION vector_dominates_or_equals(
    observed JSONB,
    required JSONB
)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    item RECORD;
    observed_count BIGINT;
    required_count BIGINT;
BEGIN
    IF jsonb_typeof(observed) <> 'object'
       OR jsonb_typeof(required) <> 'object' THEN
        RAISE EXCEPTION 'Vector clocks must be JSON objects';
    END IF;

    FOR item IN SELECT key, value FROM jsonb_each(required)
    LOOP
        IF jsonb_typeof(item.value) <> 'number' THEN
            RAISE EXCEPTION 'Vector clock counter for % is not numeric', item.key;
        END IF;

        required_count := (item.value #>> '{}')::BIGINT;
        IF required_count < 0 THEN
            RAISE EXCEPTION 'Vector clock counters cannot be negative';
        END IF;

        IF NOT (observed ? item.key) THEN
            observed_count := 0;
        ELSE
            IF jsonb_typeof(observed -> item.key) <> 'number' THEN
                RAISE EXCEPTION 'Observed counter for % is not numeric', item.key;
            END IF;
            observed_count := ((observed -> item.key) #>> '{}')::BIGINT;
        END IF;

        IF observed_count < required_count THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    RETURN TRUE;
END;
$$;

CREATE FUNCTION vector_merge(left_clock JSONB, right_clock JSONB)
RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    merged JSONB := '{}'::jsonb;
    item RECORD;
    left_count BIGINT;
    right_count BIGINT;
BEGIN
    IF jsonb_typeof(left_clock) <> 'object'
       OR jsonb_typeof(right_clock) <> 'object' THEN
        RAISE EXCEPTION 'Vector clocks must be JSON objects';
    END IF;

    FOR item IN
        SELECT key FROM jsonb_each(left_clock)
        UNION
        SELECT key FROM jsonb_each(right_clock)
    LOOP
        left_count := COALESCE((left_clock ->> item.key)::BIGINT, 0);
        right_count := COALESCE((right_clock ->> item.key)::BIGINT, 0);

        IF left_count < 0 OR right_count < 0 THEN
            RAISE EXCEPTION 'Vector clock counters cannot be negative';
        END IF;

        merged := merged || jsonb_build_object(
            item.key, GREATEST(left_count, right_count)
        );
    END LOOP;

    RETURN merged;
END;
$$;

-- Seed independent consistency configurations.
INSERT INTO repositories (
    repository_name, consistency, authoritative_region
)
VALUES
    ('incident-control-strong', 'strong', 'IN-NORTH'),
    ('telemetry-dashboard-eventual', 'eventual', NULL),
    ('incident-workflow-causal', 'causal', NULL);

INSERT INTO replicas (repository_id, region_code, status)
SELECT repository_id, region_code, 'available'
FROM repositories
CROSS JOIN (
    VALUES ('IN-NORTH'), ('IN-SOUTH'), ('EU-WEST')
) AS regions(region_code);

-- Simulate a temporary partition in the eventual-consistency deployment.
UPDATE replicas
SET status = 'partitioned'
WHERE repository_id = (
    SELECT repository_id
    FROM repositories
    WHERE repository_name = 'telemetry-dashboard-eventual'
)
AND region_code = 'EU-WEST';

-- Insert a strong-model operation. A real application would perform the
-- leader commit and durable acknowledgments in its replication protocol.
WITH target AS (
    SELECT r.repository_id, p.replica_id
    FROM repositories r
    JOIN replicas p USING (repository_id)
    WHERE r.repository_name = 'incident-control-strong'
      AND p.region_code = 'IN-NORTH'
)
INSERT INTO consistency_operations (
    operation_id,
    repository_id,
    origin_replica_id,
    entity_key,
    entity_value,
    operation_sequence,
    vector_clock,
    causal_dependencies,
    status
)
SELECT
    '10000000-0000-0000-0000-000000000001'::uuid,
    repository_id,
    replica_id,
    'incident:INC-804',
    '{"state":"opened","severity":"high"}'::jsonb,
    1,
    '{"IN-NORTH":1}'::jsonb,
    '{}'::jsonb,
    'applied'
FROM target;

-- Eventual write committed locally in the origin region.
WITH target AS (
    SELECT r.repository_id, p.replica_id
    FROM repositories r
    JOIN replicas p USING (repository_id)
    WHERE r.repository_name = 'telemetry-dashboard-eventual'
      AND p.region_code = 'IN-NORTH'
)
INSERT INTO consistency_operations (
    operation_id,
    repository_id,
    origin_replica_id,
    entity_key,
    entity_value,
    operation_sequence,
    vector_clock,
    causal_dependencies,
    status
)
SELECT
    '20000000-0000-0000-0000-000000000001'::uuid,
    repository_id,
    replica_id,
    'telemetry:plant-4:temperature',
    '{"celsius":37.2}'::jsonb,
    1,
    '{"IN-NORTH":1}'::jsonb,
    '{}'::jsonb,
    'pending'
FROM target;

-- The incident assignment depends on the incident creation. The dependency
-- edge records the semantic order independently of message arrival order.
WITH target AS (
    SELECT r.repository_id, p.replica_id
    FROM repositories r
    JOIN replicas p USING (repository_id)
    WHERE r.repository_name = 'incident-workflow-causal'
      AND p.region_code = 'IN-NORTH'
)
INSERT INTO consistency_operations (
    operation_id,
    repository_id,
    origin_replica_id,
    entity_key,
    entity_value,
    operation_sequence,
    vector_clock,
    causal_dependencies,
    status
)
SELECT
    '30000000-0000-0000-0000-000000000001'::uuid,
    repository_id,
    replica_id,
    'incident:INC-804',
    '{"state":"opened"}'::jsonb,
    1,
    '{"IN-NORTH":1}'::jsonb,
    '{}'::jsonb,
    'applied'
FROM target;

WITH target AS (
    SELECT r.repository_id, p.replica_id
    FROM repositories r
    JOIN replicas p USING (repository_id)
    WHERE r.repository_name = 'incident-workflow-causal'
      AND p.region_code = 'IN-NORTH'
)
INSERT INTO consistency_operations (
    operation_id,
    repository_id,
    origin_replica_id,
    entity_key,
    entity_value,
    operation_sequence,
    vector_clock,
    causal_dependencies,
    status
)
SELECT
    '30000000-0000-0000-0000-000000000002'::uuid,
    repository_id,
    replica_id,
    'incident:INC-804:assignment',
    '{"team":"network-operations"}'::jsonb,
    2,
    '{"IN-NORTH":2}'::jsonb,
    '{"IN-NORTH":1}'::jsonb,
    'pending'
FROM target;

INSERT INTO causal_dependencies (
    operation_id,
    depends_on_operation_id
)
VALUES (
    '30000000-0000-0000-0000-000000000002'::uuid,
    '30000000-0000-0000-0000-000000000001'::uuid
);

-- Determine whether a replica has observed the dependencies of every
-- pending operation. This identifies events safe to attempt next.
CREATE VIEW causally_ready_operations AS
SELECT
    op.operation_id,
    op.repository_id,
    op.entity_key,
    op.status,
    op.causal_dependencies,
    rep.replica_id,
    rep.region_code,
    rep.status AS replica_status,
    COALESCE(context.observed_clock, '{}'::jsonb) AS observed_clock,
    vector_dominates_or_equals(
        COALESCE(context.observed_clock, '{}'::jsonb),
        op.causal_dependencies
    ) AS dependencies_satisfied
FROM consistency_operations op
JOIN replicas rep
    ON rep.repository_id = op.repository_id
LEFT JOIN LATERAL (
    SELECT COALESCE(
        vector_merge_aggregate(ev.vector_clock),
        '{}'::jsonb
    ) AS observed_clock
    FROM entity_versions ev
    WHERE ev.replica_id = rep.replica_id
) context ON TRUE;

-- Aggregate version clocks across the replica's materialized entity versions.
CREATE AGGREGATE vector_merge_aggregate(JSONB) (
    SFUNC = vector_merge,
    STYPE = JSONB,
    INITCOND = '{}'
);

-- A receipt records attempted propagation. A partitioned replica is not
-- marked applied merely because an operation exists in the central ledger.
INSERT INTO replica_operation_receipts (
    replica_id, operation_id, apply_error
)
SELECT
    rep.replica_id,
    op.operation_id,
    CASE
        WHEN rep.status = 'partitioned' THEN 'Replica is partitioned'
        ELSE NULL
    END
FROM consistency_operations op
JOIN replicas rep USING (repository_id)
WHERE op.repository_id = (
    SELECT repository_id
    FROM repositories
    WHERE repository_name = 'telemetry-dashboard-eventual'
);

-- A materialized read model can expose the latest known record per region.
-- Each row remains explicitly associated with the replica that produced it.
CREATE VIEW regional_entity_state AS
SELECT
    repo.repository_name,
    repo.consistency,
    rep.region_code,
    rep.status AS replica_status,
    ev.entity_key,
    ev.entity_value,
    ev.is_tombstone,
    ev.vector_clock,
    ev.updated_at
FROM entity_versions ev
JOIN replicas rep USING (replica_id)
JOIN repositories repo USING (repository_id);

-- Inspect pending operations and partition status.
SELECT
    repo.repository_name,
    op.entity_key,
    op.status AS operation_status,
    rep.region_code,
    rep.status AS replica_status
FROM consistency_operations op
JOIN repositories repo USING (repository_id)
JOIN replicas rep USING (repository_id)
ORDER BY repo.repository_name, op.created_at, rep.region_code;

-- Identify causally ready operations. A production worker must still claim
-- work transactionally, validate authorization, and update receipts safely.
SELECT
    repository_id,
    operation_id,
    entity_key,
    region_code,
    dependencies_satisfied
FROM causally_ready_operations
WHERE replica_status = 'available'
ORDER BY repository_id, operation_id, region_code;

-- Check convergence for an entity by comparing the canonical materialized
-- value and causal context observed at available replicas.
SELECT
    repo.repository_name,
    ev.entity_key,
    COUNT(DISTINCT ev.entity_value) AS distinct_values,
    COUNT(DISTINCT ev.vector_clock) AS distinct_contexts,
    COUNT(*) FILTER (WHERE NOT ev.is_tombstone) AS visible_copies
FROM entity_versions ev
JOIN replicas rep USING (replica_id)
JOIN repositories repo USING (repository_id)
WHERE rep.status = 'available'
GROUP BY repo.repository_name, ev.entity_key
ORDER BY repo.repository_name, ev.entity_key;

-- Transactional receipt update example: the operation can be acknowledged
-- as applied only after its materialized state and receipt are committed
-- together. Application-level locking or idempotency is still required.
BEGIN;

UPDATE replica_operation_receipts
SET applied_at = now(),
    apply_error = NULL
WHERE replica_id = (
    SELECT rep.replica_id
    FROM replicas rep
    JOIN repositories repo USING (repository_id)
    WHERE repo.repository_name = 'incident-control-strong'
      AND rep.region_code = 'IN-NORTH'
)
AND operation_id = '10000000-0000-0000-0000-000000000001'::uuid;

COMMIT;

-- Demonstrate vector-clock comparisons without mutating persistent data.
SELECT
    vector_dominates_or_equals(
        '{"IN-NORTH":2,"EU-WEST":1}'::jsonb,
        '{"IN-NORTH":1}'::jsonb
    ) AS has_observed_north_predecessor,
    vector_dominates_or_equals(
        '{"IN-NORTH":1}'::jsonb,
        '{"IN-NORTH":2}'::jsonb
    ) AS has_observed_future_north_event,
    vector_merge(
        '{"IN-NORTH":2}'::jsonb,
        '{"EU-WEST":3}'::jsonb
    ) AS merged_causal_context;

ROLLBACK;
