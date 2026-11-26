-- ============================================================
-- BULKHEADS: RESOURCE ISOLATION AND FAILURE CONTAINMENT
-- PostgreSQL 14+
--
-- Models:
--   Applications
--   Independent resource pools
--   Requests and admission decisions
--   Execution attempts
--   Circuit breakers
--   Capacity policies
--   Failure events
--   Operational reporting
--
-- All sample data is synthetic.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS bulkhead;

SET search_path TO bulkhead, public;

-- ------------------------------------------------------------
-- 1. DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE pool_state AS ENUM (
    'HEALTHY',
    'DEGRADED',
    'OPEN',
    'DISABLED'
);

CREATE TYPE request_state AS ENUM (
    'SUBMITTED',
    'QUEUED',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'REJECTED',
    'TIMED_OUT',
    'CANCELLED'
);

CREATE TYPE failure_category AS ENUM (
    'DOWNSTREAM_ERROR',
    'TIMEOUT',
    'CAPACITY_EXCEEDED',
    'CIRCUIT_OPEN',
    'QUEUE_FULL',
    'DEPENDENCY_UNAVAILABLE',
    'ADMINISTRATIVE'
);

CREATE TYPE admission_decision AS ENUM (
    'ACCEPTED',
    'QUEUED',
    'REJECTED'
);

-- ------------------------------------------------------------
-- 2. APPLICATIONS
-- ------------------------------------------------------------

CREATE TABLE applications (
    application_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_name VARCHAR(100) NOT NULL UNIQUE,
    owner_team VARCHAR(100) NOT NULL,
    environment VARCHAR(20) NOT NULL
        CHECK (environment IN ('DEVELOPMENT', 'STAGING', 'PRODUCTION')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 3. RESOURCE POOLS
-- ------------------------------------------------------------

CREATE TABLE resource_pools (
    pool_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    pool_name VARCHAR(100) NOT NULL,
    dependency_name VARCHAR(150) NOT NULL,
    max_concurrent INTEGER NOT NULL CHECK (max_concurrent > 0),
    max_queue INTEGER NOT NULL DEFAULT 0 CHECK (max_queue >= 0),
    timeout_ms INTEGER NOT NULL CHECK (timeout_ms > 0),
    failure_threshold INTEGER NOT NULL DEFAULT 3
        CHECK (failure_threshold > 0),
    recovery_seconds INTEGER NOT NULL DEFAULT 30
        CHECK (recovery_seconds > 0),
    current_state pool_state NOT NULL DEFAULT 'HEALTHY',
    active_requests INTEGER NOT NULL DEFAULT 0
        CHECK (active_requests >= 0),
    queued_requests INTEGER NOT NULL DEFAULT 0
        CHECK (queued_requests >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(application_id, pool_name),

    CHECK (active_requests <= max_concurrent),
    CHECK (queued_requests <= max_queue)
);

CREATE INDEX idx_resource_pools_application
    ON resource_pools(application_id);

CREATE INDEX idx_resource_pools_state
    ON resource_pools(current_state)
    WHERE current_state IN ('OPEN', 'DEGRADED');

-- ------------------------------------------------------------
-- 4. RESOURCE POOL POLICIES
-- ------------------------------------------------------------

CREATE TABLE pool_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pool_id BIGINT NOT NULL UNIQUE
        REFERENCES resource_pools(pool_id),
    reject_when_full BOOLEAN NOT NULL DEFAULT TRUE,
    allow_half_open_probe BOOLEAN NOT NULL DEFAULT TRUE,
    recovery_probe_limit INTEGER NOT NULL DEFAULT 1
        CHECK (recovery_probe_limit > 0),
    enable_load_shedding BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- 5. REQUESTS
-- ------------------------------------------------------------

CREATE TABLE resource_requests (
    request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pool_id BIGINT NOT NULL
        REFERENCES resource_pools(pool_id),
    correlation_id UUID NOT NULL UNIQUE,
    operation_name VARCHAR(150) NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 5
        CHECK (priority BETWEEN 1 AND 10),
    current_status request_state NOT NULL DEFAULT 'SUBMITTED',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    idempotency_key VARCHAR(150),
    failure_reason TEXT,

    CHECK (
        completed_at IS NULL
        OR started_at IS NOT NULL
    ),

    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    ),

    UNIQUE(pool_id, idempotency_key)
);

CREATE INDEX idx_requests_pool_status
    ON resource_requests(pool_id, current_status);

CREATE INDEX idx_requests_submitted
    ON resource_requests(submitted_at DESC);

CREATE INDEX idx_requests_priority_queue
    ON resource_requests(pool_id, priority DESC, submitted_at)
    WHERE current_status = 'QUEUED';

CREATE INDEX idx_requests_correlation
    ON resource_requests(correlation_id);

-- ------------------------------------------------------------
-- 6. ADMISSION DECISIONS
-- ------------------------------------------------------------

CREATE TABLE admission_decisions (
    decision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id BIGINT NOT NULL UNIQUE
        REFERENCES resource_requests(request_id),
    decision admission_decision NOT NULL,
    reason VARCHAR(250) NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_admission_decisions_time
    ON admission_decisions(decided_at DESC);

-- ------------------------------------------------------------
-- 7. EXECUTION ATTEMPTS
-- ------------------------------------------------------------

CREATE TABLE execution_attempts (
    attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id BIGINT NOT NULL
        REFERENCES resource_requests(request_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    outcome request_state NOT NULL DEFAULT 'RUNNING',
    latency_ms INTEGER CHECK (latency_ms >= 0),
    error_message TEXT,

    UNIQUE(request_id, attempt_number),

    CHECK (
        finished_at IS NULL
        OR finished_at >= started_at
    )
);

CREATE INDEX idx_execution_attempts_request
    ON execution_attempts(request_id, attempt_number DESC);

-- ------------------------------------------------------------
-- 8. FAILURE EVENTS
-- ------------------------------------------------------------

CREATE TABLE failure_events (
    failure_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pool_id BIGINT NOT NULL
        REFERENCES resource_pools(pool_id),
    request_id BIGINT
        REFERENCES resource_requests(request_id),
    category failure_category NOT NULL,
    error_message TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_failure_events_pool_time
    ON failure_events(pool_id, occurred_at DESC);

CREATE INDEX idx_unresolved_failures
    ON failure_events(pool_id)
    WHERE resolved_at IS NULL;

-- ------------------------------------------------------------
-- 9. POOL STATE TRANSITIONS
-- ------------------------------------------------------------

CREATE TABLE pool_state_history (
    transition_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pool_id BIGINT NOT NULL
        REFERENCES resource_pools(pool_id),
    previous_state pool_state,
    new_state pool_state NOT NULL,
    reason VARCHAR(250) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pool_state_history
    ON pool_state_history(pool_id, changed_at DESC);

-- ------------------------------------------------------------
-- 10. STATE AUDIT TRIGGER
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION audit_pool_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.current_state IS DISTINCT FROM OLD.current_state THEN
        INSERT INTO pool_state_history (
            pool_id,
            previous_state,
            new_state,
            reason
        )
        VALUES (
            NEW.pool_id,
            OLD.current_state,
            NEW.current_state,
            'Resource pool state updated'
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_pool_state
AFTER UPDATE OF current_state ON resource_pools
FOR EACH ROW
EXECUTE FUNCTION audit_pool_state();

-- ------------------------------------------------------------
-- 11. REQUEST STATUS VALIDATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_request_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.current_status = OLD.current_status THEN
        RETURN NEW;
    END IF;

    IF OLD.current_status = 'SUBMITTED'
       AND NEW.current_status IN ('QUEUED', 'RUNNING', 'REJECTED',
                                  'CANCELLED') THEN
        RETURN NEW;
    END IF;

    IF OLD.current_status = 'QUEUED'
       AND NEW.current_status IN ('RUNNING', 'REJECTED', 'CANCELLED') THEN
        RETURN NEW;
    END IF;

    IF OLD.current_status = 'RUNNING'
       AND NEW.current_status IN ('COMPLETED', 'FAILED',
                                  'TIMED_OUT', 'CANCELLED') THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'Invalid request transition: % -> %',
        OLD.current_status,
        NEW.current_status;
END;
$$;

CREATE TRIGGER trg_validate_request_transition
BEFORE UPDATE OF current_status ON resource_requests
FOR EACH ROW
EXECUTE FUNCTION validate_request_transition();

-- ------------------------------------------------------------
-- 12. RESOURCE ADMISSION FUNCTION
--
-- Uses a row lock to serialize admission decisions for a pool.
-- This prevents concurrent transactions from independently
-- consuming the same remaining capacity.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION admit_request(
    p_request_id BIGINT
)
RETURNS admission_decision
LANGUAGE plpgsql
AS $$
DECLARE
    v_pool_id BIGINT;
    v_state pool_state;
    v_active INTEGER;
    v_queued INTEGER;
    v_max_concurrent INTEGER;
    v_max_queue INTEGER;
    v_status request_state;
    v_decision admission_decision;
    v_reason VARCHAR(250);
BEGIN
    SELECT pool_id, current_status
    INTO v_pool_id, v_status
    FROM resource_requests
    WHERE request_id = p_request_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown request: %', p_request_id;
    END IF;

    IF v_status <> 'SUBMITTED' THEN
        RAISE EXCEPTION
            'Only submitted requests can be admitted';
    END IF;

    SELECT
        current_state,
        active_requests,
        queued_requests,
        max_concurrent,
        max_queue
    INTO
        v_state,
        v_active,
        v_queued,
        v_max_concurrent,
        v_max_queue
    FROM resource_pools
    WHERE pool_id = v_pool_id
    FOR UPDATE;

    IF v_state IN ('OPEN', 'DISABLED') THEN
        v_decision := 'REJECTED';
        v_reason := 'Pool is unavailable';

    ELSIF v_active < v_max_concurrent THEN
        v_decision := 'ACCEPTED';
        v_reason := 'Execution capacity available';

        UPDATE resource_pools
        SET active_requests = active_requests + 1
        WHERE pool_id = v_pool_id;

        UPDATE resource_requests
        SET current_status = 'RUNNING',
            started_at = CURRENT_TIMESTAMP
        WHERE request_id = p_request_id;

    ELSIF v_queued < v_max_queue THEN
        v_decision := 'QUEUED';
        v_reason := 'Execution capacity full; queue available';

        UPDATE resource_pools
        SET queued_requests = queued_requests + 1
        WHERE pool_id = v_pool_id;

        UPDATE resource_requests
        SET current_status = 'QUEUED'
        WHERE request_id = p_request_id;

    ELSE
        v_decision := 'REJECTED';
        v_reason := 'Concurrency and queue capacity exhausted';
    END IF;

    IF v_decision = 'REJECTED' THEN
        UPDATE resource_requests
        SET current_status = 'REJECTED',
            failure_reason = v_reason
        WHERE request_id = p_request_id;
    END IF;

    INSERT INTO admission_decisions (
        request_id,
        decision,
        reason
    )
    VALUES (
        p_request_id,
        v_decision,
        v_reason
    );

    RETURN v_decision;
END;
$$;

-- ------------------------------------------------------------
-- 13. COMPLETE REQUEST FUNCTION
--
-- Releases capacity and records the terminal result.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION complete_request(
    p_request_id BIGINT,
    p_outcome request_state,
    p_error TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_pool_id BIGINT;
    v_status request_state;
    v_started TIMESTAMPTZ;
BEGIN
    IF p_outcome NOT IN ('COMPLETED', 'FAILED', 'TIMED_OUT') THEN
        RAISE EXCEPTION 'Invalid terminal outcome';
    END IF;

    SELECT pool_id, current_status, started_at
    INTO v_pool_id, v_status, v_started
    FROM resource_requests
    WHERE request_id = p_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown request';
    END IF;

    IF v_status <> 'RUNNING' THEN
        RAISE EXCEPTION
            'Only running requests can be completed';
    END IF;

    UPDATE resource_requests
    SET current_status = p_outcome,
        completed_at = CURRENT_TIMESTAMP,
        failure_reason = p_error
    WHERE request_id = p_request_id;

    UPDATE resource_pools
    SET active_requests = active_requests - 1
    WHERE pool_id = v_pool_id
      AND active_requests > 0;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Resource counter integrity violation';
    END IF;

    UPDATE execution_attempts
    SET finished_at = CURRENT_TIMESTAMP,
        outcome = p_outcome,
        latency_ms = GREATEST(
            0,
            (
                EXTRACT(
                    EPOCH FROM
                    (CURRENT_TIMESTAMP - v_started)
                ) * 1000
            )::INTEGER
        ),
        error_message = p_error
    WHERE request_id = p_request_id
      AND finished_at IS NULL;

    IF p_outcome IN ('FAILED', 'TIMED_OUT') THEN
        INSERT INTO failure_events (
            pool_id,
            request_id,
            category,
            error_message
        )
        VALUES (
            v_pool_id,
            p_request_id,
            CASE
                WHEN p_outcome = 'TIMED_OUT'
                    THEN 'TIMEOUT'::failure_category
                ELSE 'DOWNSTREAM_ERROR'::failure_category
            END,
            COALESCE(p_error, 'Unspecified execution failure')
        );
    END IF;
END;
$$;

-- ------------------------------------------------------------
-- 14. CIRCUIT BREAKER TRANSITION FUNCTION
--
-- Uses unresolved failures within a rolling time window.
-- Production systems should use a dedicated breaker window
-- and atomic state management for distributed deployments.
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_circuit_breaker(
    p_pool_id BIGINT,
    p_window_seconds INTEGER DEFAULT 60
)
RETURNS pool_state
LANGUAGE plpgsql
AS $$
DECLARE
    v_failures INTEGER;
    v_threshold INTEGER;
    v_state pool_state;
    v_recovery INTEGER;
    v_last_failure TIMESTAMPTZ;
BEGIN
    IF p_window_seconds <= 0 THEN
        RAISE EXCEPTION 'Window must be positive';
    END IF;

    SELECT failure_threshold, current_state, recovery_seconds
    INTO v_threshold, v_state, v_recovery
    FROM resource_pools
    WHERE pool_id = p_pool_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown pool';
    END IF;

    SELECT COUNT(*), MAX(occurred_at)
    INTO v_failures, v_last_failure
    FROM failure_events
    WHERE pool_id = p_pool_id
      AND occurred_at >=
          CURRENT_TIMESTAMP - make_interval(secs => p_window_seconds);

    IF v_state = 'DISABLED' THEN
        RETURN v_state;
    END IF;

    IF v_failures >= v_threshold THEN
        UPDATE resource_pools
        SET current_state = 'OPEN'
        WHERE pool_id = p_pool_id;

        RETURN 'OPEN';
    END IF;

    IF v_state = 'OPEN'
       AND v_last_failure IS NOT NULL
       AND v_last_failure <=
           CURRENT_TIMESTAMP - make_interval(secs => v_recovery) THEN

        UPDATE resource_pools
        SET current_state = 'DEGRADED'
        WHERE pool_id = p_pool_id;

        RETURN 'DEGRADED';
    END IF;

    IF v_state = 'DEGRADED' AND v_failures = 0 THEN
        UPDATE resource_pools
        SET current_state = 'HEALTHY'
        WHERE pool_id = p_pool_id;

        RETURN 'HEALTHY';
    END IF;

    RETURN v_state;
END;
$$;

-- ------------------------------------------------------------
-- 15. QUEUE PROMOTION PROCEDURE
--
-- Promotes queued work when capacity becomes available.
-- FOR UPDATE SKIP LOCKED supports concurrent workers.
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE promote_queued_requests(
    p_pool_id BIGINT,
    p_batch_size INTEGER DEFAULT 10
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_request RECORD;
    v_capacity INTEGER;
    v_promoted INTEGER := 0;
BEGIN
    IF p_batch_size <= 0 THEN
        RAISE EXCEPTION 'Batch size must be positive';
    END IF;

    SELECT max_concurrent - active_requests
    INTO v_capacity
    FROM resource_pools
    WHERE pool_id = p_pool_id
      AND current_state = 'HEALTHY'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pool not found or unavailable';
    END IF;

    v_capacity := LEAST(v_capacity, p_batch_size);

    FOR v_request IN
        SELECT request_id
        FROM resource_requests
        WHERE pool_id = p_pool_id
          AND current_status = 'QUEUED'
        ORDER BY priority DESC, submitted_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT v_capacity
    LOOP
        UPDATE resource_requests
        SET current_status = 'RUNNING',
            started_at = CURRENT_TIMESTAMP
        WHERE request_id = v_request.request_id;

        UPDATE resource_pools
        SET queued_requests = queued_requests - 1,
            active_requests = active_requests + 1
        WHERE pool_id = p_pool_id
          AND queued_requests > 0;

        v_promoted := v_promoted + 1;
    END LOOP;

    RAISE NOTICE 'Promoted % queued requests', v_promoted;
END;
$$;

-- ------------------------------------------------------------
-- 16. REPORTING VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW pool_operational_report AS
SELECT
    p.pool_id,
    a.application_name,
    p.pool_name,
    p.dependency_name,
    p.current_state,
    p.max_concurrent,
    p.max_queue,
    p.active_requests,
    p.queued_requests,
    COUNT(r.request_id) AS total_requests,
    COUNT(r.request_id) FILTER (
        WHERE r.current_status = 'COMPLETED'
    ) AS completed_requests,
    COUNT(r.request_id) FILTER (
        WHERE r.current_status = 'FAILED'
    ) AS failed_requests,
    COUNT(r.request_id) FILTER (
        WHERE r.current_status = 'REJECTED'
    ) AS rejected_requests,
    COUNT(r.request_id) FILTER (
        WHERE r.current_status = 'TIMED_OUT'
    ) AS timed_out_requests
FROM resource_pools p
JOIN applications a
    ON a.application_id = p.application_id
LEFT JOIN resource_requests r
    ON r.pool_id = p.pool_id
GROUP BY
    p.pool_id,
    a.application_name,
    p.pool_name,
    p.dependency_name,
    p.current_state,
    p.max_concurrent,
    p.max_queue,
    p.active_requests,
    p.queued_requests;

-- ------------------------------------------------------------
-- 17. SAMPLE APPLICATIONS
-- ------------------------------------------------------------

INSERT INTO applications (
    application_name,
    owner_team,
    environment
)
VALUES
    ('commerce-platform', 'Platform Engineering', 'PRODUCTION'),
    ('analytics-platform', 'Data Engineering', 'STAGING');

-- ------------------------------------------------------------
-- 18. SAMPLE RESOURCE POOLS
-- ------------------------------------------------------------

INSERT INTO resource_pools (
    application_id,
    pool_name,
    dependency_name,
    max_concurrent,
    max_queue,
    timeout_ms,
    failure_threshold,
    recovery_seconds
)
SELECT
    application_id,
    'payment',
    'Payment Gateway',
    2,
    3,
    1000,
    3,
    30
FROM applications
WHERE application_name = 'commerce-platform';

INSERT INTO resource_pools (
    application_id,
    pool_name,
    dependency_name,
    max_concurrent,
    max_queue,
    timeout_ms,
    failure_threshold,
    recovery_seconds
)
SELECT
    application_id,
    'inventory',
    'Inventory Database',
    3,
    4,
    1500,
    3,
    30
FROM applications
WHERE application_name = 'commerce-platform';

INSERT INTO resource_pools (
    application_id,
    pool_name,
    dependency_name,
    max_concurrent,
    max_queue,
    timeout_ms,
    failure_threshold,
    recovery_seconds
)
SELECT
    application_id,
    'notification',
    'Notification Provider',
    1,
    2,
    500,
    2,
    30
FROM applications
WHERE application_name = 'commerce-platform';

INSERT INTO pool_policies (pool_id)
SELECT pool_id
FROM resource_pools;

-- ------------------------------------------------------------
-- 19. SAMPLE REQUESTS
-- ------------------------------------------------------------

INSERT INTO resource_requests (
    pool_id,
    correlation_id,
    operation_name,
    priority,
    idempotency_key
)
SELECT
    pool_id,
    '00000000-0000-0000-0000-000000000001',
    'process-payment',
    10,
    'PAY-001'
FROM resource_pools
WHERE pool_name = 'payment';

INSERT INTO resource_requests (
    pool_id,
    correlation_id,
    operation_name,
    priority,
    idempotency_key
)
SELECT
    pool_id,
    '00000000-0000-0000-0000-000000000002',
    'reserve-inventory',
    8,
    'INV-001'
FROM resource_pools
WHERE pool_name = 'inventory';

INSERT INTO resource_requests (
    pool_id,
    correlation_id,
    operation_name,
    priority,
    idempotency_key
)
SELECT
    pool_id,
    '00000000-0000-0000-0000-000000000003',
    'send-notification',
    5,
    'NOT-001'
FROM resource_pools
WHERE pool_name = 'notification';

-- ------------------------------------------------------------
-- 20. DEMONSTRATE ADMISSION
-- ------------------------------------------------------------

SELECT admit_request(request_id)
FROM resource_requests
ORDER BY request_id;

-- Create an execution record for accepted requests.
INSERT INTO execution_attempts (
    request_id,
    attempt_number
)
SELECT
    request_id,
    1
FROM resource_requests
WHERE current_status = 'RUNNING';

-- ------------------------------------------------------------
-- 21. DEMONSTRATE COMPLETION
-- ------------------------------------------------------------

SELECT complete_request(
    request_id,
    'COMPLETED',
    NULL
)
FROM resource_requests
WHERE operation_name = 'process-payment'
  AND current_status = 'RUNNING';

-- ------------------------------------------------------------
-- 22. DEMONSTRATE A DOWNSTREAM FAILURE
-- ------------------------------------------------------------

SELECT complete_request(
    request_id,
    'FAILED',
    'Notification provider returned HTTP 503'
)
FROM resource_requests
WHERE operation_name = 'send-notification'
  AND current_status = 'RUNNING';

-- ------------------------------------------------------------
-- 23. INSERT ADDITIONAL FAILURE EVENTS
-- ------------------------------------------------------------

INSERT INTO failure_events (
    pool_id,
    category,
    error_message
)
SELECT
    pool_id,
    'DEPENDENCY_UNAVAILABLE',
    'Notification dependency health check failed'
FROM resource_pools
WHERE pool_name = 'notification';

INSERT INTO failure_events (
    pool_id,
    category,
    error_message
)
SELECT
    pool_id,
    'TIMEOUT',
    'Notification provider exceeded execution deadline'
FROM resource_pools
WHERE pool_name = 'notification';

-- Evaluate notification circuit state.
SELECT evaluate_circuit_breaker(
    pool_id,
    60
)
FROM resource_pools
WHERE pool_name = 'notification';

-- ------------------------------------------------------------
-- 24. ELIGIBILITY AND CAPACITY RETRIEVAL
-- ------------------------------------------------------------

SELECT
    pool_name,
    current_state,
    max_concurrent,
    active_requests,
    max_concurrent - active_requests AS available_capacity,
    max_queue,
    queued_requests,
    CASE
        WHEN current_state IN ('OPEN', 'DISABLED')
            THEN 'UNAVAILABLE'
        WHEN active_requests < max_concurrent
            THEN 'DIRECT_EXECUTION'
        WHEN queued_requests < max_queue
            THEN 'QUEUE_ELIGIBLE'
        ELSE 'LOAD_SHEDDING'
    END AS admission_status
FROM resource_pools
ORDER BY pool_name;

-- ------------------------------------------------------------
-- 25. AGGREGATED OPERATIONAL REPORT
-- ------------------------------------------------------------

SELECT *
FROM pool_operational_report
ORDER BY application_name, pool_name;

-- ------------------------------------------------------------
-- 26. FAILURE RATE ANALYSIS
-- ------------------------------------------------------------

SELECT
    p.pool_name,
    COUNT(r.request_id) AS total_requests,
    COUNT(r.request_id) FILTER (
        WHERE r.current_status IN ('FAILED', 'TIMED_OUT')
    ) AS unsuccessful_requests,
    ROUND(
        100.0 *
        COUNT(r.request_id) FILTER (
            WHERE r.current_status IN ('FAILED', 'TIMED_OUT')
        ) /
        NULLIF(COUNT(r.request_id), 0),
        2
    ) AS failure_percentage
FROM resource_pools p
LEFT JOIN resource_requests r
    ON r.pool_id = p.pool_id
GROUP BY p.pool_id, p.pool_name
ORDER BY failure_percentage DESC NULLS LAST;

-- ------------------------------------------------------------
-- 27. CTE: RESOURCE UTILIZATION
-- ------------------------------------------------------------

WITH utilization AS (
    SELECT
        pool_name,
        max_concurrent,
        active_requests,
        queued_requests,
        ROUND(
            100.0 * active_requests /
            NULLIF(max_concurrent, 0),
            2
        ) AS utilization_percentage
    FROM resource_pools
)
SELECT
    *,
    CASE
        WHEN utilization_percentage >= 90 THEN 'HIGH'
        WHEN utilization_percentage >= 60 THEN 'MODERATE'
        ELSE 'NORMAL'
    END AS utilization_status
FROM utilization
ORDER BY utilization_percentage DESC;

-- ------------------------------------------------------------
-- 28. CTE: RECENT FAILURE CONCENTRATION
-- ------------------------------------------------------------

WITH recent_failures AS (
    SELECT
        pool_id,
        COUNT(*) AS failure_count,
        MAX(occurred_at) AS last_failure
    FROM failure_events
    WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
    GROUP BY pool_id
)
SELECT
    p.pool_name,
    p.current_state,
    COALESCE(f.failure_count, 0) AS failure_count,
    f.last_failure
FROM resource_pools p
LEFT JOIN recent_failures f
    ON f.pool_id = p.pool_id
ORDER BY failure_count DESC;

-- ------------------------------------------------------------
-- 29. VALIDATION: RESOURCE COUNTER CONSISTENCY
-- ------------------------------------------------------------

SELECT
    p.pool_name,
    p.active_requests,
    COUNT(r.request_id) FILTER (
        WHERE r.current_status = 'RUNNING'
    ) AS actual_running,
    p.queued_requests,
    COUNT(r.request_id) FILTER (
        WHERE r.current_status = 'QUEUED'
    ) AS actual_queued,
    CASE
        WHEN p.active_requests =
            COUNT(r.request_id) FILTER (
                WHERE r.current_status = 'RUNNING'
            )
        AND p.queued_requests =
            COUNT(r.request_id) FILTER (
                WHERE r.current_status = 'QUEUED'
            )
        THEN 'CONSISTENT'
        ELSE 'REQUIRES_RECONCILIATION'
    END AS integrity_status
FROM resource_pools p
LEFT JOIN resource_requests r
    ON r.pool_id = p.pool_id
GROUP BY
    p.pool_id,
    p.pool_name,
    p.active_requests,
    p.queued_requests;

-- ------------------------------------------------------------
-- 30. DEMONSTRATE INVALID STATUS TRANSITION
--
-- The exception is caught inside a subtransaction.
-- ------------------------------------------------------------

DO $$
DECLARE
    v_request_id BIGINT;
BEGIN
    SELECT request_id
    INTO v_request_id
    FROM resource_requests
    WHERE operation_name = 'process-payment'
    LIMIT 1;

    BEGIN
        UPDATE resource_requests
        SET current_status = 'RUNNING'
        WHERE request_id = v_request_id
          AND current_status = 'COMPLETED';

    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Invalid transition correctly rejected: %',
                SQLERRM;
    END;
END;
$$;

-- ------------------------------------------------------------
-- 31. DEMONSTRATE TRANSACTION ROLLBACK
-- ------------------------------------------------------------

DO $$
DECLARE
    v_original_limit INTEGER;
    v_pool_id BIGINT;
BEGIN
    SELECT pool_id, max_concurrent
    INTO v_pool_id, v_original_limit
    FROM resource_pools
    WHERE pool_name = 'payment';

    BEGIN
        UPDATE resource_pools
        SET max_concurrent = 0
        WHERE pool_id = v_pool_id;

    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Invalid capacity change rolled back';
    END;

    ASSERT (
        SELECT max_concurrent = v_original_limit
        FROM resource_pools
        WHERE pool_id = v_pool_id
    ), 'Capacity rollback validation failed';
END;
$$;

COMMIT;

-- ------------------------------------------------------------
-- 32. FINAL REPORTING QUERIES
-- ------------------------------------------------------------

SELECT
    application_name,
    pool_name,
    current_state,
    max_concurrent,
    active_requests,
    queued_requests,
    total_requests,
    completed_requests,
    failed_requests,
    rejected_requests,
    timed_out_requests
FROM bulkhead.pool_operational_report
ORDER BY application_name, pool_name;

SELECT
    p.pool_name,
    h.previous_state,
    h.new_state,
    h.reason,
    h.changed_at
FROM bulkhead.pool_state_history h
JOIN bulkhead.resource_pools p
    ON p.pool_id = h.pool_id
ORDER BY h.changed_at DESC;

SELECT
    p.pool_name,
    f.category,
    f.error_message,
    f.occurred_at
FROM bulkhead.failure_events f
JOIN bulkhead.resource_pools p
    ON p.pool_id = f.pool_id
ORDER BY f.occurred_at DESC;
