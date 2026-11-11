-- ============================================================
-- RETRY AND TIMEOUT PATTERNS
-- PostgreSQL 15+
-- Backoff, jitter, retry budgets and retry storm monitoring.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS resilience;

SET search_path TO resilience, public;

-- ------------------------------------------------------------
-- 1. Domain types
-- ------------------------------------------------------------

CREATE TYPE failure_category AS ENUM (
    'transient',
    'rate_limited',
    'timeout',
    'permanent'
);

CREATE TYPE circuit_state AS ENUM (
    'closed',
    'open',
    'half_open'
);

CREATE TYPE jitter_strategy AS ENUM (
    'none',
    'full',
    'equal'
);

CREATE TYPE execution_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'retrying',
    'exhausted',
    'permanent_failure',
    'circuit_rejected',
    'cancelled'
);

-- ------------------------------------------------------------
-- 2. Services and retry policies
-- ------------------------------------------------------------

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name VARCHAR(120) NOT NULL UNIQUE,
    endpoint_name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE retry_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name VARCHAR(120) NOT NULL UNIQUE,
    max_attempts INTEGER NOT NULL CHECK (max_attempts >= 1),
    initial_delay_ms INTEGER NOT NULL CHECK (initial_delay_ms >= 0),
    multiplier NUMERIC(8,3) NOT NULL CHECK (multiplier >= 1),
    max_delay_ms INTEGER NOT NULL CHECK (max_delay_ms >= 0),
    timeout_ms INTEGER NOT NULL CHECK (timeout_ms > 0),
    max_elapsed_ms INTEGER NOT NULL CHECK (max_elapsed_ms > 0),
    jitter jitter_strategy NOT NULL DEFAULT 'full',
    retry_budget_capacity INTEGER NOT NULL
        CHECK (retry_budget_capacity >= 0),
    retry_budget_refill NUMERIC(12,3) NOT NULL
        CHECK (retry_budget_refill >= 0),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (max_delay_ms >= initial_delay_ms)
);

CREATE TABLE service_policy_assignments (
    service_id BIGINT NOT NULL REFERENCES services(service_id),
    policy_id BIGINT NOT NULL REFERENCES retry_policies(policy_id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (service_id, policy_id)
);

-- ------------------------------------------------------------
-- 3. Circuit breaker state
-- ------------------------------------------------------------

CREATE TABLE circuit_breakers (
    breaker_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL UNIQUE REFERENCES services(service_id),
    state circuit_state NOT NULL DEFAULT 'closed',
    failure_threshold INTEGER NOT NULL DEFAULT 3
        CHECK (failure_threshold >= 1),
    failure_count INTEGER NOT NULL DEFAULT 0
        CHECK (failure_count >= 0),
    recovery_timeout_ms INTEGER NOT NULL DEFAULT 3000
        CHECK (recovery_timeout_ms > 0),
    half_open_limit INTEGER NOT NULL DEFAULT 1
        CHECK (half_open_limit >= 1),
    half_open_in_flight INTEGER NOT NULL DEFAULT 0
        CHECK (half_open_in_flight >= 0),
    opened_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 4. Logical request execution
-- ------------------------------------------------------------

CREATE TABLE request_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id BIGINT NOT NULL REFERENCES services(service_id),
    policy_id BIGINT NOT NULL REFERENCES retry_policies(policy_id),
    idempotency_key VARCHAR(200),
    request_fingerprint VARCHAR(128) NOT NULL,
    status execution_status NOT NULL DEFAULT 'pending',
    current_attempt INTEGER NOT NULL DEFAULT 0
        CHECK (current_attempt >= 0),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    total_elapsed_ms NUMERIC(14,3),
    final_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        completed_at IS NULL OR started_at IS NOT NULL
    ),

    CHECK (
        total_elapsed_ms IS NULL OR total_elapsed_ms >= 0
    )
);

CREATE UNIQUE INDEX uq_execution_idempotency
ON request_executions(service_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX idx_execution_service_status
ON request_executions(service_id, status, created_at DESC);

-- ------------------------------------------------------------
-- 5. Individual attempts
-- ------------------------------------------------------------

CREATE TABLE retry_attempts (
    attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id UUID NOT NULL
        REFERENCES request_executions(execution_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    timeout_ms INTEGER NOT NULL CHECK (timeout_ms > 0),
    elapsed_ms NUMERIC(14,3),
    outcome VARCHAR(30) NOT NULL CHECK (
        outcome IN (
            'success',
            'transient_failure',
            'rate_limited',
            'timeout',
            'permanent_failure'
        )
    ),
    failure failure_category,
    planned_delay_ms NUMERIC(14,3) NOT NULL DEFAULT 0
        CHECK (planned_delay_ms >= 0),
    actual_delay_ms NUMERIC(14,3)
        CHECK (actual_delay_ms IS NULL OR actual_delay_ms >= 0),
    error_message TEXT,

    UNIQUE (execution_id, attempt_number),

    CHECK (
        completed_at IS NULL OR completed_at >= started_at
    )
);

CREATE INDEX idx_attempt_execution
ON retry_attempts(execution_id, attempt_number);

CREATE INDEX idx_attempt_failure_time
ON retry_attempts(failure, started_at DESC);

-- ------------------------------------------------------------
-- 6. Retry budget accounting
-- ------------------------------------------------------------

CREATE TABLE retry_budget_events (
    budget_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL REFERENCES services(service_id),
    execution_id UUID REFERENCES request_executions(execution_id),
    event_type VARCHAR(20) NOT NULL CHECK (
        event_type IN ('consumed', 'refilled', 'rejected')
    ),
    token_change NUMERIC(14,3) NOT NULL,
    tokens_remaining NUMERIC(14,3) NOT NULL
        CHECK (tokens_remaining >= 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_budget_service_time
ON retry_budget_events(service_id, recorded_at DESC);

-- ------------------------------------------------------------
-- 7. Circuit state history
-- ------------------------------------------------------------

CREATE TABLE circuit_state_history (
    history_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL REFERENCES services(service_id),
    previous_state circuit_state,
    new_state circuit_state NOT NULL,
    reason TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 8. Policy calculation function
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION calculate_backoff_ms(
    p_initial_ms INTEGER,
    p_multiplier NUMERIC,
    p_max_ms INTEGER,
    p_retry_number INTEGER,
    p_jitter jitter_strategy,
    p_random NUMERIC DEFAULT NULL
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_ceiling NUMERIC;
    v_random NUMERIC;
BEGIN
    IF p_initial_ms < 0 OR p_multiplier < 1
       OR p_max_ms < 0 OR p_retry_number < 0 THEN
        RAISE EXCEPTION 'Invalid backoff parameters';
    END IF;

    IF p_max_ms < p_initial_ms THEN
        RAISE EXCEPTION 'Maximum delay cannot be below initial delay';
    END IF;

    IF p_random IS NOT NULL
       AND (p_random < 0 OR p_random > 1) THEN
        RAISE EXCEPTION 'Random input must be between 0 and 1';
    END IF;

    v_ceiling := LEAST(
        p_max_ms::NUMERIC,
        p_initial_ms * POWER(p_multiplier, p_retry_number)
    );

    v_random := COALESCE(p_random, RANDOM());

    RETURN CASE p_jitter
        WHEN 'none' THEN v_ceiling
        WHEN 'full' THEN v_random * v_ceiling
        WHEN 'equal' THEN
            v_ceiling / 2 + v_random * v_ceiling / 2
    END;
END;
$$;

-- ------------------------------------------------------------
-- 9. Retry eligibility function
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION is_retryable(
    p_failure failure_category
)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT p_failure IN (
        'transient',
        'rate_limited',
        'timeout'
    );
$$;

-- ------------------------------------------------------------
-- 10. Execution audit trigger
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION audit_circuit_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.state IS DISTINCT FROM NEW.state THEN
        INSERT INTO circuit_state_history (
            service_id,
            previous_state,
            new_state,
            reason
        )
        VALUES (
            NEW.service_id,
            OLD.state,
            NEW.state,
            'Circuit breaker state transition'
        );
    END IF;

    NEW.updated_at := NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_circuit_transition
BEFORE UPDATE ON circuit_breakers
FOR EACH ROW
EXECUTE FUNCTION audit_circuit_transition();

-- ------------------------------------------------------------
-- 11. Atomic retry-budget consumption
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION consume_retry_token(
    p_service_id BIGINT,
    p_execution_id UUID,
    p_token_balance NUMERIC,
    p_capacity NUMERIC
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_remaining NUMERIC;
BEGIN
    IF p_token_balance < 0 OR p_capacity < 0 THEN
        RAISE EXCEPTION 'Invalid token balance';
    END IF;

    -- Serialize budget updates for the service.
    PERFORM 1
    FROM services
    WHERE service_id = p_service_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Service not found';
    END IF;

    IF p_token_balance < 1 THEN
        INSERT INTO retry_budget_events (
            service_id,
            execution_id,
            event_type,
            token_change,
            tokens_remaining
        )
        VALUES (
            p_service_id,
            p_execution_id,
            'rejected',
            0,
            p_token_balance
        );

        RETURN FALSE;
    END IF;

    v_remaining := LEAST(
        p_capacity,
        p_token_balance
    ) - 1;

    INSERT INTO retry_budget_events (
        service_id,
        execution_id,
        event_type,
        token_change,
        tokens_remaining
    )
    VALUES (
        p_service_id,
        p_execution_id,
        'consumed',
        -1,
        v_remaining
    );

    RETURN TRUE;
END;
$$;

-- ------------------------------------------------------------
-- 12. Start execution with idempotency protection
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION start_execution(
    p_service_id BIGINT,
    p_policy_id BIGINT,
    p_fingerprint VARCHAR,
    p_idempotency_key VARCHAR DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_execution_id UUID;
BEGIN
    IF LENGTH(TRIM(p_fingerprint)) = 0 THEN
        RAISE EXCEPTION 'Request fingerprint is required';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM service_policy_assignments
        WHERE service_id = p_service_id
          AND policy_id = p_policy_id
    ) THEN
        RAISE EXCEPTION 'Policy is not assigned to service';
    END IF;

    INSERT INTO request_executions (
        service_id,
        policy_id,
        request_fingerprint,
        idempotency_key,
        status,
        started_at
    )
    VALUES (
        p_service_id,
        p_policy_id,
        p_fingerprint,
        p_idempotency_key,
        'running',
        NOW()
    )
    ON CONFLICT (service_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL
    DO NOTHING
    RETURNING execution_id INTO v_execution_id;

    IF v_execution_id IS NULL THEN
        SELECT execution_id
        INTO v_execution_id
        FROM request_executions
        WHERE service_id = p_service_id
          AND idempotency_key = p_idempotency_key
          AND request_fingerprint = p_fingerprint;

        IF v_execution_id IS NULL THEN
            RAISE EXCEPTION
                'Idempotency key reused with different request';
        END IF;
    END IF;

    RETURN v_execution_id;
END;
$$;

-- ------------------------------------------------------------
-- 13. Finalize an execution
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE finalize_execution(
    p_execution_id UUID,
    p_status execution_status,
    p_error TEXT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_status NOT IN (
        'succeeded',
        'exhausted',
        'permanent_failure',
        'cancelled'
    ) THEN
        RAISE EXCEPTION 'Invalid final execution state';
    END IF;

    UPDATE request_executions
    SET
        status = p_status,
        completed_at = NOW(),
        total_elapsed_ms = EXTRACT(
            EPOCH FROM (NOW() - started_at)
        ) * 1000,
        final_error = p_error
    WHERE execution_id = p_execution_id
      AND status IN ('running', 'retrying');

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Execution missing or cannot be finalized';
    END IF;
END;
$$;

-- ------------------------------------------------------------
-- 14. Seed services and policies
-- ------------------------------------------------------------

INSERT INTO services (
    service_name,
    endpoint_name
)
VALUES
    ('payment_gateway', 'payments.internal'),
    ('inventory_service', 'inventory.internal'),
    ('notification_service', 'notifications.internal');

INSERT INTO retry_policies (
    policy_name,
    max_attempts,
    initial_delay_ms,
    multiplier,
    max_delay_ms,
    timeout_ms,
    max_elapsed_ms,
    jitter,
    retry_budget_capacity,
    retry_budget_refill
)
VALUES
    ('payment_policy', 4, 200, 2, 3000, 2000, 12000,
     'full', 20, 5),
    ('inventory_policy', 3, 100, 2, 2000, 1500, 7000,
     'equal', 30, 10),
    ('notification_policy', 5, 500, 2, 5000, 3000, 20000,
     'full', 50, 15);

INSERT INTO service_policy_assignments (
    service_id,
    policy_id
)
SELECT s.service_id, p.policy_id
FROM services s
JOIN retry_policies p ON
    (s.service_name, p.policy_name) IN (
        ('payment_gateway', 'payment_policy'),
        ('inventory_service', 'inventory_policy'),
        ('notification_service', 'notification_policy')
    );

INSERT INTO circuit_breakers (
    service_id,
    failure_threshold,
    recovery_timeout_ms,
    half_open_limit
)
SELECT service_id, 3, 3000, 1
FROM services;

-- ------------------------------------------------------------
-- 15. Example executions and failure records
-- ------------------------------------------------------------

DO $$
DECLARE
    v_execution UUID;
    v_payment BIGINT;
    v_policy BIGINT;
BEGIN
    SELECT service_id INTO v_payment
    FROM services
    WHERE service_name = 'payment_gateway';

    SELECT policy_id INTO v_policy
    FROM retry_policies
    WHERE policy_name = 'payment_policy';

    v_execution := start_execution(
        v_payment,
        v_policy,
        'payment-request-001',
        'payment-idempotency-001'
    );

    INSERT INTO retry_attempts (
        execution_id,
        attempt_number,
        timeout_ms,
        outcome,
        failure,
        planned_delay_ms,
        elapsed_ms,
        completed_at,
        error_message
    )
    VALUES
    (
        v_execution, 1, 2000,
        'transient_failure', 'transient',
        150, 100, NOW(),
        'Temporary connection reset'
    ),
    (
        v_execution, 2, 2000,
        'timeout', 'timeout',
        350, 2000, NOW(),
        'Gateway response deadline exceeded'
    ),
    (
        v_execution, 3, 2000,
        'success', NULL,
        0, 250, NOW(),
        NULL
    );

    UPDATE request_executions
    SET current_attempt = 3
    WHERE execution_id = v_execution;

    CALL finalize_execution(
        v_execution,
        'succeeded'
    );
END;
$$;

-- Simulated failed execution.

DO $$
DECLARE
    v_execution UUID;
    v_service BIGINT;
    v_policy BIGINT;
BEGIN
    SELECT service_id INTO v_service
    FROM services
    WHERE service_name = 'inventory_service';

    SELECT policy_id INTO v_policy
    FROM retry_policies
    WHERE policy_name = 'inventory_policy';

    v_execution := start_execution(
        v_service,
        v_policy,
        'inventory-request-002'
    );

    INSERT INTO retry_attempts (
        execution_id,
        attempt_number,
        timeout_ms,
        outcome,
        failure,
        planned_delay_ms,
        elapsed_ms,
        completed_at,
        error_message
    )
    VALUES
    (
        v_execution, 1, 1500,
        'transient_failure', 'transient',
        100, 100, NOW(),
        'Connection refused'
    ),
    (
        v_execution, 2, 1500,
        'transient_failure', 'transient',
        200, 150, NOW(),
        'Connection refused'
    ),
    (
        v_execution, 3, 1500,
        'timeout', 'timeout',
        0, 1500, NOW(),
        'Request deadline exceeded'
    );

    UPDATE request_executions
    SET current_attempt = 3
    WHERE execution_id = v_execution;

    CALL finalize_execution(
        v_execution,
        'exhausted',
        'Maximum attempts reached'
    );
END;
$$;

-- ------------------------------------------------------------
-- 16. Retrieval: execution history
-- ------------------------------------------------------------

SELECT
    e.execution_id,
    s.service_name,
    e.status,
    e.current_attempt,
    e.total_elapsed_ms,
    e.final_error
FROM request_executions e
JOIN services s USING (service_id)
ORDER BY e.created_at DESC;

-- ------------------------------------------------------------
-- 17. Retrieval: attempt-level history
-- ------------------------------------------------------------

SELECT
    e.execution_id,
    s.service_name,
    a.attempt_number,
    a.outcome,
    a.failure,
    a.timeout_ms,
    a.elapsed_ms,
    a.planned_delay_ms,
    a.error_message
FROM retry_attempts a
JOIN request_executions e USING (execution_id)
JOIN services s USING (service_id)
ORDER BY e.created_at, a.attempt_number;

-- ------------------------------------------------------------
-- 18. Evaluation: policy delay calculations
-- ------------------------------------------------------------

SELECT
    policy_name,
    calculate_backoff_ms(
        initial_delay_ms,
        multiplier,
        max_delay_ms,
        2,
        jitter,
        0.5
    ) AS example_retry_delay_ms
FROM retry_policies
ORDER BY policy_name;

-- ------------------------------------------------------------
-- 19. Validation: failure retry eligibility
-- ------------------------------------------------------------

SELECT
    failure_category,
    is_retryable(failure_category) AS can_retry
FROM unnest(enum_range(NULL::failure_category))
AS failure_category;

-- ------------------------------------------------------------
-- 20. Aggregation: retry success and failure statistics
-- ------------------------------------------------------------

SELECT
    s.service_name,
    COUNT(DISTINCT e.execution_id) AS total_executions,
    COUNT(a.attempt_id) AS total_attempts,
    COUNT(*) FILTER (
        WHERE a.outcome = 'success'
    ) AS successful_attempts,
    COUNT(*) FILTER (
        WHERE a.outcome <> 'success'
    ) AS failed_attempts,
    ROUND(
        AVG(a.elapsed_ms),
        2
    ) AS average_attempt_latency_ms
FROM services s
LEFT JOIN request_executions e USING (service_id)
LEFT JOIN retry_attempts a USING (execution_id)
GROUP BY s.service_name
ORDER BY s.service_name;

-- ------------------------------------------------------------
-- 21. Retry storm detection
-- Count attempts within one-second windows.
-- ------------------------------------------------------------

WITH retry_windows AS (
    SELECT
        service_id,
        DATE_TRUNC('second', started_at) AS window_start,
        COUNT(*) AS retry_count
    FROM retry_attempts
    WHERE attempt_number > 1
    GROUP BY
        service_id,
        DATE_TRUNC('second', started_at)
)
SELECT
    s.service_name,
    r.window_start,
    r.retry_count,
    CASE
        WHEN r.retry_count >= 50 THEN 'critical'
        WHEN r.retry_count >= 20 THEN 'warning'
        ELSE 'normal'
    END AS storm_level
FROM retry_windows r
JOIN services s USING (service_id)
ORDER BY r.retry_count DESC;

-- ------------------------------------------------------------
-- 22. Circuit breaker monitoring
-- ------------------------------------------------------------

SELECT
    s.service_name,
    c.state,
    c.failure_count,
    c.failure_threshold,
    c.recovery_timeout_ms,
    c.half_open_in_flight,
    c.updated_at
FROM circuit_breakers c
JOIN services s USING (service_id);

-- ------------------------------------------------------------
-- 23. Retry budget reporting
-- ------------------------------------------------------------

SELECT
    s.service_name,
    b.event_type,
    COUNT(*) AS event_count,
    SUM(b.token_change) AS net_token_change,
    MIN(b.tokens_remaining) AS minimum_tokens
FROM retry_budget_events b
JOIN services s USING (service_id)
GROUP BY s.service_name, b.event_type
ORDER BY s.service_name, b.event_type;

-- ------------------------------------------------------------
-- 24. Failed execution reporting
-- ------------------------------------------------------------

SELECT
    s.service_name,
    e.execution_id,
    e.status,
    e.current_attempt,
    e.total_elapsed_ms,
    e.final_error
FROM request_executions e
JOIN services s USING (service_id)
WHERE e.status IN (
    'exhausted',
    'permanent_failure',
    'circuit_rejected'
)
ORDER BY e.created_at DESC;

-- ------------------------------------------------------------
-- 25. Transactional circuit breaker transition example
-- ------------------------------------------------------------

BEGIN;

UPDATE circuit_breakers
SET
    state = 'open',
    failure_count = failure_threshold,
    opened_at = NOW()
WHERE service_id = (
    SELECT service_id
    FROM services
    WHERE service_name = 'notification_service'
);

COMMIT;

-- Trigger records the state transition automatically.

SELECT *
FROM circuit_state_history
ORDER BY changed_at DESC;

COMMIT;
