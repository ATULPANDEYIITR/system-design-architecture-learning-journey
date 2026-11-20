-- ============================================================
-- FAULT TOLERANCE: FAILURE DETECTION AND RECOVERY
-- PostgreSQL 18 compatible
--
-- Models:
-- 1. Distributed service clusters
-- 2. Service nodes and replicas
-- 3. Heartbeat monitoring
-- 4. Failure detection
-- 5. Recovery policies
-- 6. Recovery attempts
-- 7. Recovery scheduling
-- 8. Event auditing
-- 9. Availability reporting
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS fault_tolerance;

SET search_path TO fault_tolerance, public;

-- ------------------------------------------------------------
-- ENUMERATED DOMAIN STATES
-- ------------------------------------------------------------

CREATE TYPE node_state AS ENUM (
    'HEALTHY',
    'SUSPECT',
    'FAILED',
    'RECOVERING',
    'DISABLED'
);

CREATE TYPE recovery_state AS ENUM (
    'SCHEDULED',
    'RUNNING',
    'SUCCESS',
    'FAILURE',
    'EXHAUSTED',
    'CANCELLED'
);

CREATE TYPE event_type AS ENUM (
    'REGISTERED',
    'HEARTBEAT',
    'SUSPECT',
    'FAILED',
    'RECOVERY_SCHEDULED',
    'RECOVERY_STARTED',
    'RECOVERY_SUCCESS',
    'RECOVERY_FAILURE',
    'RECOVERY_EXHAUSTED',
    'DISABLED'
);

-- ------------------------------------------------------------
-- CLUSTER
-- ------------------------------------------------------------

CREATE TABLE clusters (
    cluster_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_name VARCHAR(100) NOT NULL UNIQUE,
    environment VARCHAR(30) NOT NULL,
    minimum_healthy_replicas INTEGER NOT NULL DEFAULT 2,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_minimum_replicas
        CHECK (minimum_healthy_replicas >= 1),

    CONSTRAINT valid_environment
        CHECK (environment IN (
            'DEVELOPMENT',
            'TESTING',
            'STAGING',
            'PRODUCTION'
        ))
);

-- ------------------------------------------------------------
-- RECOVERY POLICIES
-- ------------------------------------------------------------

CREATE TABLE recovery_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name VARCHAR(100) NOT NULL UNIQUE,
    heartbeat_timeout_seconds INTEGER NOT NULL,
    failure_threshold INTEGER NOT NULL,
    maximum_retries INTEGER NOT NULL,
    initial_backoff_seconds INTEGER NOT NULL,
    maximum_backoff_seconds INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT positive_timeout
        CHECK (heartbeat_timeout_seconds > 0),

    CONSTRAINT positive_failure_threshold
        CHECK (failure_threshold >= 1),

    CONSTRAINT nonnegative_retries
        CHECK (maximum_retries >= 0),

    CONSTRAINT valid_backoff
        CHECK (
            initial_backoff_seconds > 0
            AND maximum_backoff_seconds >= initial_backoff_seconds
        )
);

-- ------------------------------------------------------------
-- SERVICE NODES
-- ------------------------------------------------------------

CREATE TABLE service_nodes (
    node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    cluster_id BIGINT NOT NULL
        REFERENCES clusters(cluster_id),

    policy_id BIGINT NOT NULL
        REFERENCES recovery_policies(policy_id),

    node_name VARCHAR(100) NOT NULL UNIQUE,
    hostname VARCHAR(255) NOT NULL,
    state node_state NOT NULL DEFAULT 'HEALTHY',

    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    missed_heartbeats INTEGER NOT NULL DEFAULT 0,
    recovery_attempts INTEGER NOT NULL DEFAULT 0,

    next_recovery_at TIMESTAMPTZ,

    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_missed_heartbeats
        CHECK (missed_heartbeats >= 0),

    CONSTRAINT valid_recovery_attempts
        CHECK (recovery_attempts >= 0),

    UNIQUE (cluster_id, hostname)
);

CREATE INDEX idx_nodes_cluster_state
    ON service_nodes(cluster_id, state);

CREATE INDEX idx_nodes_heartbeat
    ON service_nodes(last_heartbeat);

CREATE INDEX idx_nodes_recovery_schedule
    ON service_nodes(next_recovery_at)
    WHERE state = 'FAILED';

-- ------------------------------------------------------------
-- HEARTBEAT HISTORY
-- ------------------------------------------------------------

CREATE TABLE heartbeat_history (
    heartbeat_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    node_id BIGINT NOT NULL
        REFERENCES service_nodes(node_id),

    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    sequence_number BIGINT NOT NULL,

    UNIQUE (node_id, sequence_number),

    CHECK (sequence_number >= 1)
);

CREATE INDEX idx_heartbeat_node_time
    ON heartbeat_history(node_id, received_at DESC);

-- ------------------------------------------------------------
-- RECOVERY ATTEMPTS
-- ------------------------------------------------------------

CREATE TABLE recovery_attempts (
    attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    node_id BIGINT NOT NULL
        REFERENCES service_nodes(node_id),

    attempt_number INTEGER NOT NULL,

    status recovery_state NOT NULL DEFAULT 'SCHEDULED',

    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    error_message TEXT,

    UNIQUE (node_id, attempt_number),

    CHECK (attempt_number >= 1),

    CHECK (
        completed_at IS NULL
        OR started_at IS NOT NULL
    ),

    CHECK (
        started_at IS NULL
        OR started_at >= scheduled_at
    ),

    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    ),

    CHECK (
        status NOT IN ('SUCCESS', 'FAILURE')
        OR completed_at IS NOT NULL
    )
);

CREATE INDEX idx_recovery_pending
    ON recovery_attempts(scheduled_at)
    WHERE status = 'SCHEDULED';

-- ------------------------------------------------------------
-- EVENT AUDIT LOG
-- ------------------------------------------------------------

CREATE TABLE cluster_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    node_id BIGINT
        REFERENCES service_nodes(node_id),

    event event_type NOT NULL,

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_node_time
    ON cluster_events(node_id, occurred_at DESC);

CREATE INDEX idx_events_type
    ON cluster_events(event);

-- ------------------------------------------------------------
-- AUDIT TRIGGER
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION record_node_state_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    detected_event event_type;
BEGIN
    IF NEW.state IS DISTINCT FROM OLD.state THEN

        detected_event := CASE NEW.state
            WHEN 'SUSPECT' THEN 'SUSPECT'
            WHEN 'FAILED' THEN 'FAILED'
            WHEN 'RECOVERING' THEN 'RECOVERY_STARTED'
            WHEN 'HEALTHY' THEN 'RECOVERY_SUCCESS'
            WHEN 'DISABLED' THEN 'DISABLED'
        END;

        INSERT INTO cluster_events (
            node_id,
            event,
            event_details
        )
        VALUES (
            NEW.node_id,
            detected_event,
            jsonb_build_object(
                'previous_state', OLD.state,
                'new_state', NEW.state
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_node_state_audit
AFTER UPDATE OF state ON service_nodes
FOR EACH ROW
EXECUTE FUNCTION record_node_state_change();

-- ------------------------------------------------------------
-- HEARTBEAT REGISTRATION FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION receive_heartbeat(
    p_node_id BIGINT,
    p_sequence_number BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    current_node service_nodes%ROWTYPE;
BEGIN
    SELECT *
    INTO current_node
    FROM service_nodes
    WHERE node_id = p_node_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown node: %', p_node_id;
    END IF;

    IF current_node.state = 'DISABLED' THEN
        RAISE EXCEPTION 'Disabled node cannot send heartbeat';
    END IF;

    IF p_sequence_number IS NULL OR p_sequence_number < 1 THEN
        RAISE EXCEPTION 'Invalid heartbeat sequence';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM heartbeat_history
        WHERE node_id = p_node_id
          AND sequence_number >= p_sequence_number
    ) THEN
        RAISE EXCEPTION 'Duplicate or stale heartbeat sequence';
    END IF;

    INSERT INTO heartbeat_history (
        node_id,
        sequence_number
    )
    VALUES (
        p_node_id,
        p_sequence_number
    );

    UPDATE service_nodes
    SET
        last_heartbeat = CURRENT_TIMESTAMP,
        missed_heartbeats = 0,
        recovery_attempts = 0,
        next_recovery_at = NULL,
        state = 'HEALTHY'
    WHERE node_id = p_node_id;

    INSERT INTO cluster_events (
        node_id,
        event,
        event_details
    )
    VALUES (
        p_node_id,
        'HEARTBEAT',
        jsonb_build_object(
            'sequence_number', p_sequence_number
        )
    );

    RETURN TRUE;
END;
$$;

-- ------------------------------------------------------------
-- FAILURE DETECTION FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION detect_node_failures()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    node_record RECORD;
    detected_count INTEGER := 0;
BEGIN
    FOR node_record IN
        SELECT
            n.node_id,
            n.state,
            n.missed_heartbeats,
            n.last_heartbeat,
            p.heartbeat_timeout_seconds,
            p.failure_threshold
        FROM service_nodes n
        JOIN recovery_policies p
            ON p.policy_id = n.policy_id
        WHERE n.state IN ('HEALTHY', 'SUSPECT')
          AND n.last_heartbeat <
              CURRENT_TIMESTAMP -
              make_interval(
                  secs => p.heartbeat_timeout_seconds
              )
        FOR UPDATE OF n
    LOOP
        UPDATE service_nodes
        SET
            missed_heartbeats = missed_heartbeats + 1,

            state = CASE
                WHEN missed_heartbeats + 1
                     >= node_record.failure_threshold
                THEN 'FAILED'::node_state

                ELSE 'SUSPECT'::node_state
            END

        WHERE node_id = node_record.node_id;

        detected_count := detected_count + 1;

    END LOOP;

    RETURN detected_count;
END;
$$;

-- ------------------------------------------------------------
-- RECOVERY SCHEDULING FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION schedule_node_recovery(
    p_node_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    node_record service_nodes%ROWTYPE;
    policy_record recovery_policies%ROWTYPE;

    healthy_count INTEGER;
    next_attempt INTEGER;
    delay_seconds INTEGER;

    new_attempt_id BIGINT;
BEGIN
    SELECT *
    INTO node_record
    FROM service_nodes
    WHERE node_id = p_node_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown node';
    END IF;

    IF node_record.state <> 'FAILED' THEN
        RAISE EXCEPTION 'Only failed nodes can be recovered';
    END IF;

    SELECT *
    INTO policy_record
    FROM recovery_policies
    WHERE policy_id = node_record.policy_id;

    IF node_record.recovery_attempts >=
       policy_record.maximum_retries THEN

        INSERT INTO cluster_events (
            node_id,
            event,
            event_details
        )
        VALUES (
            p_node_id,
            'RECOVERY_EXHAUSTED',
            '{"reason":"retry_limit_reached"}'::JSONB
        );

        RETURN NULL;
    END IF;

    SELECT COUNT(*)
    INTO healthy_count
    FROM service_nodes
    WHERE cluster_id = node_record.cluster_id
      AND state = 'HEALTHY'
      AND node_id <> p_node_id;

    IF healthy_count < (
        SELECT minimum_healthy_replicas
        FROM clusters
        WHERE cluster_id = node_record.cluster_id
    ) THEN
        RETURN NULL;
    END IF;

    next_attempt := node_record.recovery_attempts + 1;

    delay_seconds := LEAST(
        policy_record.initial_backoff_seconds::BIGINT
        * POWER(2::NUMERIC, next_attempt - 1)::BIGINT,
        policy_record.maximum_backoff_seconds
    );

    IF node_record.next_recovery_at IS NOT NULL
       AND node_record.next_recovery_at > CURRENT_TIMESTAMP THEN
        RETURN NULL;
    END IF;

    INSERT INTO recovery_attempts (
        node_id,
        attempt_number,
        status,
        scheduled_at
    )
    VALUES (
        p_node_id,
        next_attempt,
        'SCHEDULED',
        CURRENT_TIMESTAMP
            + make_interval(secs => delay_seconds)
    )
    RETURNING attempt_id INTO new_attempt_id;

    UPDATE service_nodes
    SET
        recovery_attempts = next_attempt,
        next_recovery_at = CURRENT_TIMESTAMP
            + make_interval(secs => delay_seconds)
    WHERE node_id = p_node_id;

    INSERT INTO cluster_events (
        node_id,
        event,
        event_details
    )
    VALUES (
        p_node_id,
        'RECOVERY_SCHEDULED',
        jsonb_build_object(
            'attempt', next_attempt,
            'delay_seconds', delay_seconds
        )
    );

    RETURN new_attempt_id;
END;
$$;

-- ------------------------------------------------------------
-- RECOVERY COMPLETION PROCEDURE
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE complete_recovery(
    p_attempt_id BIGINT,
    p_success BOOLEAN,
    p_error_message TEXT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    attempt_record recovery_attempts%ROWTYPE;
    node_record service_nodes%ROWTYPE;
BEGIN
    SELECT *
    INTO attempt_record
    FROM recovery_attempts
    WHERE attempt_id = p_attempt_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Recovery attempt not found';
    END IF;

    IF attempt_record.status <> 'SCHEDULED' THEN
        RAISE EXCEPTION 'Recovery attempt is not pending';
    END IF;

    SELECT *
    INTO node_record
    FROM service_nodes
    WHERE node_id = attempt_record.node_id
    FOR UPDATE;

    IF NOT FOUND OR node_record.state <> 'FAILED' THEN
        RAISE EXCEPTION 'Node is not eligible for recovery';
    END IF;

    IF attempt_record.scheduled_at > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'Recovery backoff has not expired';
    END IF;

    UPDATE recovery_attempts
    SET
        status = 'RUNNING',
        started_at = CURRENT_TIMESTAMP
    WHERE attempt_id = p_attempt_id;

    UPDATE service_nodes
    SET state = 'RECOVERING'
    WHERE node_id = node_record.node_id;

    IF p_success THEN

        UPDATE recovery_attempts
        SET
            status = 'SUCCESS',
            completed_at = CURRENT_TIMESTAMP
        WHERE attempt_id = p_attempt_id;

        UPDATE service_nodes
        SET
            state = 'HEALTHY',
            last_heartbeat = CURRENT_TIMESTAMP,
            missed_heartbeats = 0,
            recovery_attempts = 0,
            next_recovery_at = NULL
        WHERE node_id = node_record.node_id;

    ELSE

        UPDATE recovery_attempts
        SET
            status = 'FAILURE',
            completed_at = CURRENT_TIMESTAMP,
            error_message = LEFT(
                COALESCE(p_error_message, 'Restart unsuccessful'),
                2000
            )
        WHERE attempt_id = p_attempt_id;

        UPDATE service_nodes
        SET
            state = 'FAILED',
            next_recovery_at = NULL
        WHERE node_id = node_record.node_id;

    END IF;
END;
$$;

-- ------------------------------------------------------------
-- AVAILABILITY VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW cluster_availability AS
SELECT
    c.cluster_id,
    c.cluster_name,

    COUNT(n.node_id) AS total_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.state = 'HEALTHY'
    ) AS healthy_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.state = 'SUSPECT'
    ) AS suspect_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.state = 'FAILED'
    ) AS failed_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.state = 'RECOVERING'
    ) AS recovering_nodes,

    COUNT(n.node_id) FILTER (
        WHERE n.state = 'DISABLED'
    ) AS disabled_nodes,

    ROUND(
        100.0 * COUNT(n.node_id) FILTER (
            WHERE n.state = 'HEALTHY'
        ) / NULLIF(COUNT(n.node_id), 0),
        2
    ) AS availability_percent,

    CASE
        WHEN COUNT(n.node_id) FILTER (
            WHERE n.state = 'HEALTHY'
        ) >= c.minimum_healthy_replicas
        THEN TRUE
        ELSE FALSE
    END AS service_available

FROM clusters c
LEFT JOIN service_nodes n
    ON n.cluster_id = c.cluster_id

GROUP BY
    c.cluster_id,
    c.cluster_name,
    c.minimum_healthy_replicas;

-- ------------------------------------------------------------
-- RECOVERY REPORT VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW recovery_report AS
SELECT
    n.node_name,
    n.hostname,
    n.state,
    n.recovery_attempts,
    n.next_recovery_at,

    COUNT(r.attempt_id) AS total_recovery_attempts,

    COUNT(r.attempt_id) FILTER (
        WHERE r.status = 'SUCCESS'
    ) AS successful_recoveries,

    COUNT(r.attempt_id) FILTER (
        WHERE r.status = 'FAILURE'
    ) AS failed_recoveries

FROM service_nodes n
LEFT JOIN recovery_attempts r
    ON r.node_id = n.node_id

GROUP BY
    n.node_id,
    n.node_name,
    n.hostname,
    n.state,
    n.recovery_attempts,
    n.next_recovery_at;

-- ------------------------------------------------------------
-- SAMPLE CONFIGURATION
-- ------------------------------------------------------------

INSERT INTO clusters (
    cluster_name,
    environment,
    minimum_healthy_replicas
)
VALUES
    ('PAYMENT-CLUSTER', 'PRODUCTION', 2),
    ('ANALYTICS-CLUSTER', 'STAGING', 1);

INSERT INTO recovery_policies (
    policy_name,
    heartbeat_timeout_seconds,
    failure_threshold,
    maximum_retries,
    initial_backoff_seconds,
    maximum_backoff_seconds
)
VALUES
    ('PRODUCTION-POLICY', 30, 3, 5, 5, 60),
    ('STAGING-POLICY', 15, 2, 3, 2, 20);

INSERT INTO service_nodes (
    cluster_id,
    policy_id,
    node_name,
    hostname,
    state
)
VALUES
    (1, 1, 'PAYMENT-01', '10.0.0.11', 'HEALTHY'),
    (1, 1, 'PAYMENT-02', '10.0.0.12', 'HEALTHY'),
    (1, 1, 'PAYMENT-03', '10.0.0.13', 'FAILED'),
    (2, 2, 'ANALYTICS-01', '10.0.1.11', 'HEALTHY'),
    (2, 2, 'ANALYTICS-02', '10.0.1.12', 'SUSPECT');

INSERT INTO cluster_events (
    node_id,
    event,
    event_details
)
SELECT
    node_id,
    'REGISTERED',
    jsonb_build_object('hostname', hostname)
FROM service_nodes;

INSERT INTO cluster_events (
    node_id,
    event,
    event_details
)
SELECT
    node_id,
    'FAILED',
    '{"reason":"simulated_node_failure"}'::JSONB
FROM service_nodes
WHERE state = 'FAILED';

-- ------------------------------------------------------------
-- QUERY 1: CLUSTER AVAILABILITY
-- ------------------------------------------------------------

SELECT *
FROM cluster_availability
ORDER BY cluster_name;

-- ------------------------------------------------------------
-- QUERY 2: FAILURE RETRIEVAL
-- ------------------------------------------------------------

SELECT
    node_name,
    hostname,
    state,
    missed_heartbeats,
    last_heartbeat
FROM service_nodes
WHERE state IN ('SUSPECT', 'FAILED')
ORDER BY last_heartbeat;

-- ------------------------------------------------------------
-- QUERY 3: HEARTBEAT HISTORY
-- ------------------------------------------------------------

SELECT
    n.node_name,
    h.sequence_number,
    h.received_at
FROM heartbeat_history h
JOIN service_nodes n
    ON n.node_id = h.node_id
ORDER BY h.received_at DESC;

-- ------------------------------------------------------------
-- QUERY 4: FAILURE DETECTION
-- ------------------------------------------------------------

-- Execute periodically through an external scheduler.
SELECT detect_node_failures();

-- ------------------------------------------------------------
-- QUERY 5: RECOVERY SCHEDULING
-- ------------------------------------------------------------

SELECT schedule_node_recovery(
    (SELECT node_id
     FROM service_nodes
     WHERE node_name = 'PAYMENT-03')
);

-- ------------------------------------------------------------
-- QUERY 6: RECOVERY REPORTING
-- ------------------------------------------------------------

SELECT *
FROM recovery_report
ORDER BY node_name;

-- ------------------------------------------------------------
-- QUERY 7: EVENT AUDIT
-- ------------------------------------------------------------

SELECT
    n.node_name,
    e.event,
    e.event_details,
    e.occurred_at
FROM cluster_events e
LEFT JOIN service_nodes n
    ON n.node_id = e.node_id
ORDER BY e.occurred_at DESC, e.event_id DESC;

-- ------------------------------------------------------------
-- QUERY 8: RECOVERY SUCCESS RATE
-- ------------------------------------------------------------

SELECT
    COUNT(*) AS total_attempts,

    COUNT(*) FILTER (
        WHERE status = 'SUCCESS'
    ) AS successful_attempts,

    COUNT(*) FILTER (
        WHERE status = 'FAILURE'
    ) AS failed_attempts,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE status = 'SUCCESS'
        ) / NULLIF(
            COUNT(*) FILTER (
                WHERE status IN ('SUCCESS', 'FAILURE')
            ),
            0
        ),
        2
    ) AS success_percentage

FROM recovery_attempts;

COMMIT;
