/*
 * CIRCUIT BREAKER
 * Failure Isolation and Graceful Degradation
 *
 * PostgreSQL 15+
 *
 * Models:
 * - Services and external dependencies
 * - Circuit configuration
 * - CLOSED / OPEN / HALF_OPEN states
 * - Dependency calls and failures
 * - Recovery probes
 * - Fallback execution
 * - Operational metrics
 * - State transition audit history
 * - Graceful degradation policies
 * - Recovery and merge-like atomic state transitions
 *
 * The database stores operational state and audit records.
 * Distributed request admission should additionally use an
 * application-level atomic mechanism or a centralized coordinator.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS resilience;

SET search_path TO resilience, public;

-- ============================================================
-- 1. DOMAIN TYPES
-- ============================================================

CREATE TYPE circuit_state AS ENUM (
    'CLOSED',
    'OPEN',
    'HALF_OPEN'
);

CREATE TYPE dependency_category AS ENUM (
    'PAYMENT',
    'INVENTORY',
    'RECOMMENDATION',
    'IDENTITY',
    'NOTIFICATION'
);

CREATE TYPE execution_outcome AS ENUM (
    'SUCCESS',
    'FAILURE',
    'REJECTED',
    'FALLBACK'
);

CREATE TYPE fallback_strategy AS ENUM (
    'NONE',
    'CACHE',
    'QUEUE',
    'DEFAULT_RESPONSE',
    'REJECT_REQUEST'
);

-- ============================================================
-- 2. SERVICE REGISTRY
-- ============================================================

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_name VARCHAR(120) NOT NULL UNIQUE,

    description TEXT NOT NULL,

    criticality SMALLINT NOT NULL
        CHECK (criticality BETWEEN 1 AND 5),

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id),

    dependency_name VARCHAR(150) NOT NULL,

    category dependency_category NOT NULL,

    endpoint_identifier VARCHAR(200) NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (service_id, dependency_name)
);

-- ============================================================
-- 3. CIRCUIT CONFIGURATION
-- ============================================================

CREATE TABLE circuit_configurations (
    configuration_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    dependency_id BIGINT NOT NULL UNIQUE
        REFERENCES dependencies(dependency_id),

    failure_threshold INTEGER NOT NULL DEFAULT 3
        CHECK (failure_threshold > 0),

    recovery_timeout_seconds INTEGER NOT NULL DEFAULT 30
        CHECK (recovery_timeout_seconds > 0),

    half_open_max_calls INTEGER NOT NULL DEFAULT 1
        CHECK (half_open_max_calls > 0),

    request_timeout_ms INTEGER NOT NULL DEFAULT 3000
        CHECK (request_timeout_ms > 0),

    fallback_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    fallback_mode fallback_strategy NOT NULL
        DEFAULT 'DEFAULT_RESPONSE',

    failure_rate_threshold NUMERIC(5,2)
        CHECK (
            failure_rate_threshold IS NULL
            OR failure_rate_threshold BETWEEN 0 AND 100
        ),

    minimum_sample_size INTEGER NOT NULL DEFAULT 10
        CHECK (minimum_sample_size > 0),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 4. CURRENT CIRCUIT STATE
-- ============================================================

CREATE TABLE circuit_instances (
    circuit_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    dependency_id BIGINT NOT NULL UNIQUE
        REFERENCES dependencies(dependency_id),

    state circuit_state NOT NULL DEFAULT 'CLOSED',

    consecutive_failures INTEGER NOT NULL DEFAULT 0
        CHECK (consecutive_failures >= 0),

    opened_at TIMESTAMPTZ,

    last_state_change TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    last_success_at TIMESTAMPTZ,

    last_failure_at TIMESTAMPTZ,

    half_open_inflight INTEGER NOT NULL DEFAULT 0
        CHECK (half_open_inflight >= 0),

    total_calls BIGINT NOT NULL DEFAULT 0
        CHECK (total_calls >= 0),

    successful_calls BIGINT NOT NULL DEFAULT 0
        CHECK (successful_calls >= 0),

    failed_calls BIGINT NOT NULL DEFAULT 0
        CHECK (failed_calls >= 0),

    rejected_calls BIGINT NOT NULL DEFAULT 0
        CHECK (rejected_calls >= 0),

    fallback_calls BIGINT NOT NULL DEFAULT 0
        CHECK (fallback_calls >= 0),

    CHECK (
        successful_calls + failed_calls <= total_calls
    ),

    CHECK (
        (state = 'OPEN' AND opened_at IS NOT NULL)
        OR
        (state <> 'OPEN')
    )
);

-- ============================================================
-- 5. STATE TRANSITION AUDIT
-- ============================================================

CREATE TABLE circuit_events (
    event_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    circuit_id BIGINT NOT NULL
        REFERENCES circuit_instances(circuit_id),

    previous_state circuit_state,

    new_state circuit_state NOT NULL,

    event_type VARCHAR(50) NOT NULL,

    reason TEXT NOT NULL,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

-- ============================================================
-- 6. DEPENDENCY EXECUTION LOG
-- ============================================================

CREATE TABLE dependency_calls (
    call_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    circuit_id BIGINT NOT NULL
        REFERENCES circuit_instances(circuit_id),

    request_identifier UUID NOT NULL,

    outcome execution_outcome NOT NULL,

    latency_ms NUMERIC(12,3)
        CHECK (latency_ms IS NULL OR latency_ms >= 0),

    error_category VARCHAR(80),

    error_message TEXT,

    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,

    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        (outcome = 'FALLBACK' AND fallback_used = TRUE)
        OR
        (outcome <> 'FALLBACK' AND fallback_used = FALSE)
    )
);

CREATE INDEX idx_dependency_calls_circuit_time
    ON dependency_calls(circuit_id, executed_at DESC);

CREATE INDEX idx_dependency_calls_outcome_time
    ON dependency_calls(outcome, executed_at DESC);

CREATE INDEX idx_circuit_events_history
    ON circuit_events(circuit_id, occurred_at DESC);

-- ============================================================
-- 7. FALLBACK POLICIES
-- ============================================================

CREATE TABLE fallback_policies (
    fallback_policy_id BIGINT
        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    dependency_id BIGINT NOT NULL UNIQUE
        REFERENCES dependencies(dependency_id),

    strategy fallback_strategy NOT NULL,

    response_payload JSONB NOT NULL DEFAULT '{}'::JSONB,

    maximum_staleness_seconds INTEGER
        CHECK (
            maximum_staleness_seconds IS NULL
            OR maximum_staleness_seconds >= 0
        ),

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 8. STATE CHANGE TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION audit_circuit_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state IS DISTINCT FROM OLD.state THEN

        NEW.last_state_change := NOW();

        INSERT INTO circuit_events (
            circuit_id,
            previous_state,
            new_state,
            event_type,
            reason
        )
        VALUES (
            NEW.circuit_id,
            OLD.state,
            NEW.state,
            'STATE_TRANSITION',
            'Circuit state changed.'
        );

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_circuit_state_audit
BEFORE UPDATE OF state
ON circuit_instances
FOR EACH ROW
EXECUTE FUNCTION audit_circuit_transition();

-- ============================================================
-- 9. CREATE CIRCUIT FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION create_circuit(
    p_dependency_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_circuit_id BIGINT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM dependencies
        WHERE dependency_id = p_dependency_id
          AND enabled = TRUE
    ) THEN
        RAISE EXCEPTION
            'Dependency % does not exist or is disabled.',
            p_dependency_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM circuit_configurations
        WHERE dependency_id = p_dependency_id
    ) THEN
        RAISE EXCEPTION
            'Circuit configuration missing for dependency %.',
            p_dependency_id;
    END IF;

    INSERT INTO circuit_instances (
        dependency_id
    )
    VALUES (
        p_dependency_id
    )
    ON CONFLICT (dependency_id)
    DO UPDATE SET
        dependency_id = EXCLUDED.dependency_id
    RETURNING circuit_id INTO v_circuit_id;

    RETURN v_circuit_id;
END;
$$;

-- ============================================================
-- 10. ATOMIC REQUEST ADMISSION
-- ============================================================

CREATE OR REPLACE FUNCTION acquire_circuit_permission(
    p_circuit_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_state circuit_state;
    v_opened_at TIMESTAMPTZ;
    v_timeout INTEGER;
    v_max_probes INTEGER;
    v_current_probes INTEGER;
    v_dependency_id BIGINT;
BEGIN
    SELECT
        ci.state,
        ci.opened_at,
        ci.half_open_inflight,
        ci.dependency_id,
        cc.recovery_timeout_seconds,
        cc.half_open_max_calls
    INTO
        v_state,
        v_opened_at,
        v_current_probes,
        v_dependency_id,
        v_timeout,
        v_max_probes
    FROM circuit_instances ci
    JOIN circuit_configurations cc
        ON cc.dependency_id = ci.dependency_id
    WHERE ci.circuit_id = p_circuit_id
    FOR UPDATE OF ci;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Circuit % not found.',
            p_circuit_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM dependencies
        WHERE dependency_id = v_dependency_id
          AND enabled = TRUE
    ) THEN
        UPDATE circuit_instances
        SET rejected_calls = rejected_calls + 1
        WHERE circuit_id = p_circuit_id;

        RETURN FALSE;
    END IF;

    -- OPEN transitions to HALF_OPEN only after recovery timeout.
    IF v_state = 'OPEN'
       AND v_opened_at + make_interval(secs => v_timeout) <= NOW()
    THEN
        UPDATE circuit_instances
        SET
            state = 'HALF_OPEN',
            opened_at = NULL,
            half_open_inflight = 0
        WHERE circuit_id = p_circuit_id;

        v_state := 'HALF_OPEN';
        v_current_probes := 0;
    END IF;

    IF v_state = 'OPEN' THEN
        UPDATE circuit_instances
        SET rejected_calls = rejected_calls + 1
        WHERE circuit_id = p_circuit_id;

        RETURN FALSE;
    END IF;

    IF v_state = 'HALF_OPEN' THEN

        IF v_current_probes >= v_max_probes THEN
            UPDATE circuit_instances
            SET rejected_calls = rejected_calls + 1
            WHERE circuit_id = p_circuit_id;

            RETURN FALSE;
        END IF;

        UPDATE circuit_instances
        SET half_open_inflight = half_open_inflight + 1
        WHERE circuit_id = p_circuit_id;

    END IF;

    UPDATE circuit_instances
    SET total_calls = total_calls + 1
    WHERE circuit_id = p_circuit_id;

    RETURN TRUE;
END;
$$;

-- ============================================================
-- 11. RECORD SUCCESS
-- ============================================================

CREATE OR REPLACE FUNCTION record_circuit_success(
    p_circuit_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_state circuit_state;
BEGIN
    SELECT state
    INTO v_state
    FROM circuit_instances
    WHERE circuit_id = p_circuit_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown circuit.';
    END IF;

    UPDATE circuit_instances
    SET
        successful_calls = successful_calls + 1,
        consecutive_failures = 0,
        last_success_at = NOW(),
        state = 'CLOSED',
        opened_at = NULL,
        half_open_inflight = CASE
            WHEN v_state = 'HALF_OPEN'
            THEN GREATEST(half_open_inflight - 1, 0)
            ELSE half_open_inflight
        END
    WHERE circuit_id = p_circuit_id;

    INSERT INTO circuit_events (
        circuit_id,
        previous_state,
        new_state,
        event_type,
        reason
    )
    VALUES (
        p_circuit_id,
        v_state,
        'CLOSED',
        'CALL_SUCCESS',
        'Dependency operation succeeded.'
    );
END;
$$;

-- ============================================================
-- 12. RECORD FAILURE AND OPEN CIRCUIT
-- ============================================================

CREATE OR REPLACE FUNCTION record_circuit_failure(
    p_circuit_id BIGINT,
    p_error_message TEXT
)
RETURNS circuit_state
LANGUAGE plpgsql
AS $$
DECLARE
    v_state circuit_state;
    v_threshold INTEGER;
    v_failure_count INTEGER;
    v_next_state circuit_state;
BEGIN
    SELECT
        ci.state,
        ci.consecutive_failures,
        cc.failure_threshold
    INTO
        v_state,
        v_failure_count,
        v_threshold
    FROM circuit_instances ci
    JOIN circuit_configurations cc
        ON cc.dependency_id = ci.dependency_id
    WHERE ci.circuit_id = p_circuit_id
    FOR UPDATE OF ci;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown circuit.';
    END IF;

    IF v_state = 'HALF_OPEN' THEN
        v_next_state := 'OPEN';
        v_failure_count := v_failure_count + 1;

    ELSIF v_state = 'CLOSED' THEN
        v_failure_count := v_failure_count + 1;

        IF v_failure_count >= v_threshold THEN
            v_next_state := 'OPEN';
        ELSE
            v_next_state := 'CLOSED';
        END IF;

    ELSE
        RAISE EXCEPTION
            'Cannot record an admitted failure for an OPEN circuit.';
    END IF;

    UPDATE circuit_instances
    SET
        failed_calls = failed_calls + 1,
        consecutive_failures = v_failure_count,
        last_failure_at = NOW(),
        state = v_next_state,
        opened_at = CASE
            WHEN v_next_state = 'OPEN' THEN NOW()
            ELSE NULL
        END,
        half_open_inflight = CASE
            WHEN v_state = 'HALF_OPEN' THEN 0
            ELSE half_open_inflight
        END
    WHERE circuit_id = p_circuit_id;

    INSERT INTO circuit_events (
        circuit_id,
        previous_state,
        new_state,
        event_type,
        reason,
        metadata
    )
    VALUES (
        p_circuit_id,
        v_state,
        v_next_state,
        'CALL_FAILURE',
        COALESCE(p_error_message, 'Dependency failure.'),
        jsonb_build_object(
            'consecutive_failures',
            v_failure_count
        )
    );

    RETURN v_next_state;
END;
$$;

-- ============================================================
-- 13. RECORD FALLBACK
-- ============================================================

CREATE OR REPLACE FUNCTION record_fallback(
    p_circuit_id BIGINT,
    p_request_identifier UUID,
    p_reason TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE circuit_instances
    SET fallback_calls = fallback_calls + 1
    WHERE circuit_id = p_circuit_id;

    INSERT INTO dependency_calls (
        circuit_id,
        request_identifier,
        outcome,
        fallback_used,
        error_message
    )
    VALUES (
        p_circuit_id,
        p_request_identifier,
        'FALLBACK',
        TRUE,
        p_reason
    );
END;
$$;

-- ============================================================
-- 14. OPERATIONAL VIEW
-- ============================================================

CREATE OR REPLACE VIEW circuit_health AS
SELECT
    s.service_name,
    d.dependency_name,
    d.category,
    ci.circuit_id,
    ci.state,
    ci.consecutive_failures,
    cc.failure_threshold,
    cc.recovery_timeout_seconds,
    cc.request_timeout_ms,
    ci.total_calls,
    ci.successful_calls,
    ci.failed_calls,
    ci.rejected_calls,
    ci.fallback_calls,

    ROUND(
        100.0 * ci.successful_calls /
        NULLIF(
            ci.successful_calls + ci.failed_calls,
            0
        ),
        2
    ) AS success_rate_percent,

    ci.opened_at,
    ci.last_success_at,
    ci.last_failure_at

FROM circuit_instances ci
JOIN dependencies d
    ON d.dependency_id = ci.dependency_id
JOIN services s
    ON s.service_id = d.service_id
JOIN circuit_configurations cc
    ON cc.dependency_id = d.dependency_id;

-- ============================================================
-- 15. FAILURE RATE REPORTING
-- ============================================================

CREATE OR REPLACE FUNCTION dependency_failure_report(
    p_since TIMESTAMPTZ
)
RETURNS TABLE (
    dependency_name VARCHAR,
    total_requests BIGINT,
    failures BIGINT,
    rejected BIGINT,
    fallbacks BIGINT,
    failure_percentage NUMERIC
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        d.dependency_name,

        COUNT(dc.call_id),

        COUNT(*) FILTER (
            WHERE dc.outcome = 'FAILURE'
        ),

        COUNT(*) FILTER (
            WHERE dc.outcome = 'REJECTED'
        ),

        COUNT(*) FILTER (
            WHERE dc.outcome = 'FALLBACK'
        ),

        ROUND(
            100.0 *
            COUNT(*) FILTER (
                WHERE dc.outcome = 'FAILURE'
            ) /
            NULLIF(COUNT(dc.call_id), 0),
            2
        )

    FROM dependencies d

    LEFT JOIN circuit_instances ci
        ON ci.dependency_id = d.dependency_id

    LEFT JOIN dependency_calls dc
        ON dc.circuit_id = ci.circuit_id
       AND dc.executed_at >= p_since

    GROUP BY d.dependency_name
    ORDER BY failures DESC;
$$;

-- ============================================================
-- 16. SAMPLE SERVICES
-- ============================================================

INSERT INTO services (
    service_name,
    description,
    criticality
)
VALUES
(
    'checkout-service',
    'Coordinates customer checkout and payment processing.',
    5
),
(
    'product-service',
    'Provides product and inventory information.',
    4
),
(
    'discovery-service',
    'Provides personalized product recommendations.',
    2
);

INSERT INTO dependencies (
    service_id,
    dependency_name,
    category,
    endpoint_identifier
)
SELECT
    s.service_id,
    x.dependency_name,
    x.category,
    x.endpoint
FROM services s
CROSS JOIN (
    VALUES
    (
        'payment-provider',
        'PAYMENT'::dependency_category,
        'payment.internal'
    ),
    (
        'inventory-provider',
        'INVENTORY'::dependency_category,
        'inventory.internal'
    ),
    (
        'recommendation-provider',
        'RECOMMENDATION'::dependency_category,
        'recommendation.internal'
    )
) AS x(dependency_name, category, endpoint)
WHERE
    (s.service_name = 'checkout-service'
        AND x.dependency_name = 'payment-provider')
    OR
    (s.service_name = 'product-service'
        AND x.dependency_name = 'inventory-provider')
    OR
    (s.service_name = 'discovery-service'
        AND x.dependency_name = 'recommendation-provider');

INSERT INTO circuit_configurations (
    dependency_id,
    failure_threshold,
    recovery_timeout_seconds,
    half_open_max_calls,
    request_timeout_ms,
    fallback_enabled,
    fallback_mode
)
SELECT
    dependency_id,
    CASE category
        WHEN 'PAYMENT' THEN 3
        WHEN 'INVENTORY' THEN 2
        ELSE 3
    END,
    30,
    1,
    2500,
    TRUE,
    CASE category
        WHEN 'PAYMENT' THEN 'QUEUE'
        WHEN 'INVENTORY' THEN 'CACHE'
        ELSE 'DEFAULT_RESPONSE'
    END
FROM dependencies;

INSERT INTO fallback_policies (
    dependency_id,
    strategy,
    response_payload,
    maximum_staleness_seconds
)
SELECT
    dependency_id,
    CASE category
        WHEN 'PAYMENT' THEN 'QUEUE'
        WHEN 'INVENTORY' THEN 'CACHE'
        ELSE 'DEFAULT_RESPONSE'
    END,
    CASE category
        WHEN 'PAYMENT' THEN
            '{"status":"PENDING","message":"Queued for reconciliation"}'
            ::JSONB
        WHEN 'INVENTORY' THEN
            '{"status":"DEGRADED","source":"LOCAL_CACHE"}'::JSONB
        ELSE
            '{"status":"DEGRADED","recommendations":[]}'::JSONB
    END,
    CASE category
        WHEN 'INVENTORY' THEN 300
        ELSE NULL
    END
FROM dependencies;

SELECT create_circuit(dependency_id)
FROM dependencies;

-- ============================================================
-- 17. SIMULATED REQUEST PROCESSING
-- ============================================================

-- Successful payment dependency call.
DO $$
DECLARE
    v_circuit BIGINT;
BEGIN
    SELECT ci.circuit_id
    INTO v_circuit
    FROM circuit_instances ci
    JOIN dependencies d
        ON d.dependency_id = ci.dependency_id
    WHERE d.dependency_name = 'payment-provider';

    IF acquire_circuit_permission(v_circuit) THEN

        PERFORM record_circuit_success(v_circuit);

        INSERT INTO dependency_calls (
            circuit_id,
            request_identifier,
            outcome,
            latency_ms
        )
        VALUES (
            v_circuit,
            '11111111-1111-4111-8111-111111111111',
            'SUCCESS',
            125.5
        );

    END IF;
END;
$$;

-- Three consecutive payment failures open the circuit.
DO $$
DECLARE
    v_circuit BIGINT;
    v_request UUID;
    i INTEGER;
BEGIN
    SELECT ci.circuit_id
    INTO v_circuit
    FROM circuit_instances ci
    JOIN dependencies d
        ON d.dependency_id = ci.dependency_id
    WHERE d.dependency_name = 'payment-provider';

    FOR i IN 1..3 LOOP

        IF acquire_circuit_permission(v_circuit) THEN

            PERFORM record_circuit_failure(
                v_circuit,
                'Payment provider connection refused.'
            );

            v_request := md5(
                'payment-failure-' || i::TEXT
            )::UUID;

            INSERT INTO dependency_calls (
                circuit_id,
                request_identifier,
                outcome,
                latency_ms,
                error_category,
                error_message
            )
            VALUES (
                v_circuit,
                v_request,
                'FAILURE',
                2500,
                'NETWORK',
                'Payment provider connection refused.'
            );

        END IF;

    END LOOP;

    -- Subsequent requests are rejected by the open circuit.
    IF NOT acquire_circuit_permission(v_circuit) THEN

        UPDATE circuit_instances
        SET fallback_calls = fallback_calls + 1
        WHERE circuit_id = v_circuit;

        INSERT INTO dependency_calls (
            circuit_id,
            request_identifier,
            outcome,
            fallback_used,
            error_message
        )
        VALUES (
            v_circuit,
            '22222222-2222-4222-8222-222222222222',
            'FALLBACK',
            TRUE,
            'Payment placed in local reconciliation queue.'
        );

    END IF;
END;
$$;

-- Inventory demonstrates independent dependency health.
DO $$
DECLARE
    v_circuit BIGINT;
BEGIN
    SELECT ci.circuit_id
    INTO v_circuit
    FROM circuit_instances ci
    JOIN dependencies d
        ON d.dependency_id = ci.dependency_id
    WHERE d.dependency_name = 'inventory-provider';

    IF acquire_circuit_permission(v_circuit) THEN
        PERFORM record_circuit_failure(
            v_circuit,
            'Inventory service timeout.'
        );
    END IF;
END;
$$;

-- ============================================================
-- 18. RETRIEVAL AND REPORTING QUERIES
-- ============================================================

-- Current health of every registered dependency.
SELECT *
FROM circuit_health
ORDER BY service_name, dependency_name;

-- Current circuit state and recovery information.
SELECT
    d.dependency_name,
    ci.state,
    ci.opened_at,
    cc.recovery_timeout_seconds,
    CASE
        WHEN ci.state = 'OPEN'
        THEN GREATEST(
            0,
            EXTRACT(
                EPOCH FROM (
                    ci.opened_at
                    + make_interval(
                        secs => cc.recovery_timeout_seconds
                    )
                    - NOW()
                )
            )
        )
        ELSE NULL
    END AS seconds_until_recovery_probe
FROM circuit_instances ci
JOIN dependencies d
    ON d.dependency_id = ci.dependency_id
JOIN circuit_configurations cc
    ON cc.dependency_id = d.dependency_id;

-- Aggregated execution outcomes.
SELECT
    d.dependency_name,
    dc.outcome,
    COUNT(*) AS request_count,
    ROUND(AVG(dc.latency_ms), 2) AS average_latency_ms
FROM dependency_calls dc
JOIN circuit_instances ci
    ON ci.circuit_id = dc.circuit_id
JOIN dependencies d
    ON d.dependency_id = ci.dependency_id
GROUP BY
    d.dependency_name,
    dc.outcome
ORDER BY
    d.dependency_name,
    dc.outcome;

-- Event audit.
SELECT
    d.dependency_name,
    ce.previous_state,
    ce.new_state,
    ce.event_type,
    ce.reason,
    ce.occurred_at
FROM circuit_events ce
JOIN circuit_instances ci
    ON ci.circuit_id = ce.circuit_id
JOIN dependencies d
    ON d.dependency_id = ci.dependency_id
ORDER BY ce.occurred_at DESC;

-- Failure reporting.
SELECT *
FROM dependency_failure_report(
    NOW() - INTERVAL '24 hours'
);

-- ============================================================
-- 19. ELIGIBILITY AND VALIDATION
-- ============================================================

-- Determine whether a circuit is eligible for a recovery probe.
SELECT
    d.dependency_name,
    ci.state,
    CASE
        WHEN ci.state = 'CLOSED' THEN TRUE
        WHEN ci.state = 'OPEN'
             AND ci.opened_at
                 + make_interval(
                     secs => cc.recovery_timeout_seconds
                 ) <= NOW()
        THEN TRUE
        WHEN ci.state = 'HALF_OPEN'
             AND ci.half_open_inflight
                 < cc.half_open_max_calls
        THEN TRUE
        ELSE FALSE
    END AS recovery_probe_eligible
FROM circuit_instances ci
JOIN dependencies d
    ON d.dependency_id = ci.dependency_id
JOIN circuit_configurations cc
    ON cc.dependency_id = d.dependency_id;

-- Find circuits whose failure count has reached the threshold.
SELECT
    d.dependency_name,
    ci.consecutive_failures,
    cc.failure_threshold
FROM circuit_instances ci
JOIN dependencies d
    ON d.dependency_id = ci.dependency_id
JOIN circuit_configurations cc
    ON cc.dependency_id = d.dependency_id
WHERE ci.consecutive_failures >= cc.failure_threshold;

-- ============================================================
-- 20. TRANSACTIONAL RECOVERY EXAMPLE
-- ============================================================

-- A production recovery probe must be admitted atomically.
-- This example performs a state reset for an explicitly
-- selected operational recovery after external verification.

BEGIN;

UPDATE circuit_instances ci
SET
    state = 'CLOSED',
    consecutive_failures = 0,
    opened_at = NULL,
    half_open_inflight = 0
FROM dependencies d
WHERE d.dependency_id = ci.dependency_id
  AND d.dependency_name = 'inventory-provider'
  AND ci.state = 'HALF_OPEN';

COMMIT;

-- ============================================================
-- 21. CONFIGURATION VALIDATION
-- ============================================================

-- Find dependencies missing a circuit configuration or instance.
SELECT
    d.dependency_name,
    CASE
        WHEN cc.configuration_id IS NULL
            THEN 'MISSING_CONFIGURATION'
        WHEN ci.circuit_id IS NULL
            THEN 'MISSING_CIRCUIT_INSTANCE'
        ELSE 'VALID'
    END AS validation_status
FROM dependencies d
LEFT JOIN circuit_configurations cc
    ON cc.dependency_id = d.dependency_id
LEFT JOIN circuit_instances ci
    ON ci.dependency_id = d.dependency_id;

COMMIT;
