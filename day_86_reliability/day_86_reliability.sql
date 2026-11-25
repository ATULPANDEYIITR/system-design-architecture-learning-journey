-- ============================================================
-- GRACEFUL DEGRADATION AND SYSTEM RELIABILITY
-- PostgreSQL 15+
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS resilience;

SET search_path TO resilience, public;

-- ------------------------------------------------------------
-- 1. DOMAIN TYPES
-- ------------------------------------------------------------

CREATE TYPE component_state AS ENUM (
    'HEALTHY',
    'DEGRADED',
    'FAILED',
    'RECOVERING'
);

CREATE TYPE dependency_type AS ENUM (
    'REQUIRED',
    'OPTIONAL'
);

CREATE TYPE circuit_state AS ENUM (
    'CLOSED',
    'OPEN',
    'HALF_OPEN'
);

CREATE TYPE request_state AS ENUM (
    'SUCCESS',
    'DEGRADED',
    'FAILED'
);

CREATE TYPE fallback_strategy AS ENUM (
    'NONE',
    'CACHED_VALUE',
    'DEFAULT_VALUE',
    'READ_ONLY',
    'QUEUED_OPERATION'
);

-- ------------------------------------------------------------
-- 2. APPLICATIONS AND COMPONENTS
-- ------------------------------------------------------------

CREATE TABLE applications (
    application_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_name VARCHAR(120) NOT NULL UNIQUE,
    environment VARCHAR(20) NOT NULL
        CHECK (environment IN ('DEVELOPMENT', 'STAGING', 'PRODUCTION')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE components (
    component_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    component_name VARCHAR(120) NOT NULL,
    dependency dependency_type NOT NULL,
    state component_state NOT NULL DEFAULT 'HEALTHY',
    circuit circuit_state NOT NULL DEFAULT 'CLOSED',
    fallback fallback_strategy NOT NULL DEFAULT 'NONE',
    criticality SMALLINT NOT NULL
        CHECK (criticality BETWEEN 1 AND 5),
    failure_threshold INTEGER NOT NULL DEFAULT 3
        CHECK (failure_threshold > 0),
    recovery_timeout_seconds INTEGER NOT NULL DEFAULT 30
        CHECK (recovery_timeout_seconds > 0),
    failure_count INTEGER NOT NULL DEFAULT 0
        CHECK (failure_count >= 0),
    recovery_count INTEGER NOT NULL DEFAULT 0
        CHECK (recovery_count >= 0),
    last_error TEXT,
    last_failure_at TIMESTAMPTZ,
    last_recovery_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (application_id, component_name),
    CHECK (
        (dependency = 'REQUIRED' AND fallback = 'NONE')
        OR
        (dependency = 'OPTIONAL' AND fallback <> 'NONE')
    )
);

CREATE INDEX idx_components_application_state
    ON components(application_id, state);

CREATE INDEX idx_components_circuit_state
    ON components(circuit)
    WHERE circuit <> 'CLOSED';

-- ------------------------------------------------------------
-- 3. COMPONENT DEPENDENCY RELATIONSHIPS
-- ------------------------------------------------------------

CREATE TABLE component_dependencies (
    parent_component_id BIGINT NOT NULL
        REFERENCES components(component_id) ON DELETE CASCADE,
    child_component_id BIGINT NOT NULL
        REFERENCES components(component_id) ON DELETE CASCADE,
    relationship_type dependency_type NOT NULL,
    PRIMARY KEY (parent_component_id, child_component_id),
    CHECK (parent_component_id <> child_component_id)
);

-- ------------------------------------------------------------
-- 4. REQUEST EXECUTION RECORDS
-- ------------------------------------------------------------

CREATE TABLE service_requests (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id BIGINT NOT NULL
        REFERENCES applications(application_id),
    endpoint VARCHAR(200) NOT NULL,
    request_state request_state NOT NULL,
    response_code SMALLINT NOT NULL
        CHECK (response_code BETWEEN 100 AND 599),
    duration_ms NUMERIC(12, 3) NOT NULL
        CHECK (duration_ms >= 0),
    degraded_features TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_requests_application_time
    ON service_requests(application_id, created_at DESC);

CREATE INDEX idx_requests_degraded
    ON service_requests(created_at DESC)
    WHERE request_state = 'DEGRADED';

-- ------------------------------------------------------------
-- 5. COMPONENT EXECUTION EVENTS
-- ------------------------------------------------------------

CREATE TABLE component_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    component_id BIGINT NOT NULL
        REFERENCES components(component_id),
    request_id UUID
        REFERENCES service_requests(request_id),
    previous_state component_state,
    new_state component_state NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_component_events_history
    ON component_events(component_id, created_at DESC);

-- ------------------------------------------------------------
-- 6. CIRCUIT BREAKER CONFIGURATION
-- ------------------------------------------------------------

CREATE TABLE circuit_events (
    circuit_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    component_id BIGINT NOT NULL
        REFERENCES components(component_id),
    previous_circuit circuit_state,
    new_circuit circuit_state NOT NULL,
    failure_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 7. COMPONENT STATE AUDIT TRIGGER
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION record_component_state_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.state IS DISTINCT FROM NEW.state THEN
        INSERT INTO component_events (
            component_id,
            previous_state,
            new_state,
            event_type,
            message
        )
        VALUES (
            NEW.component_id,
            OLD.state,
            NEW.state,
            'STATE_TRANSITION',
            NEW.last_error
        );
    END IF;

    IF OLD.circuit IS DISTINCT FROM NEW.circuit THEN
        INSERT INTO circuit_events (
            component_id,
            previous_circuit,
            new_circuit,
            failure_count
        )
        VALUES (
            NEW.component_id,
            OLD.circuit,
            NEW.circuit,
            NEW.failure_count
        );
    END IF;

    NEW.updated_at = NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_component_state_audit
BEFORE UPDATE ON components
FOR EACH ROW
EXECUTE FUNCTION record_component_state_change();

-- ------------------------------------------------------------
-- 8. FAILURE REGISTRATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION register_component_failure(
    p_component_id BIGINT,
    p_error TEXT
)
RETURNS TABLE (
    resulting_state component_state,
    resulting_circuit circuit_state,
    resulting_failures INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_component components%ROWTYPE;
    v_new_circuit circuit_state;
    v_new_state component_state;
BEGIN
    SELECT *
    INTO v_component
    FROM components
    WHERE component_id = p_component_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Component % does not exist', p_component_id;
    END IF;

    IF v_component.circuit = 'OPEN'
       AND v_component.last_failure_at IS NOT NULL
       AND NOW() < (
           v_component.last_failure_at
           + MAKE_INTERVAL(secs => v_component.recovery_timeout_seconds)
       )
    THEN
        RAISE EXCEPTION 'Circuit breaker is open for component %',
            p_component_id;
    END IF;

    v_component.failure_count := v_component.failure_count + 1;

    IF v_component.circuit = 'HALF_OPEN'
       OR v_component.failure_count >= v_component.failure_threshold
    THEN
        v_new_circuit := 'OPEN';
        v_new_state := 'FAILED';
    ELSE
        v_new_circuit := v_component.circuit;
        v_new_state := 'DEGRADED';
    END IF;

    UPDATE components
    SET
        failure_count = v_component.failure_count,
        circuit = v_new_circuit,
        state = v_new_state,
        last_error = LEFT(COALESCE(p_error, 'Unknown failure'), 2000),
        last_failure_at = NOW()
    WHERE component_id = p_component_id;

    RETURN QUERY
    SELECT v_new_state, v_new_circuit, v_component.failure_count;
END;
$$;

-- ------------------------------------------------------------
-- 9. COMPONENT RECOVERY
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION recover_component(
    p_component_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_component components%ROWTYPE;
BEGIN
    SELECT *
    INTO v_component
    FROM components
    WHERE component_id = p_component_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown component %', p_component_id;
    END IF;

    IF v_component.circuit = 'OPEN'
       AND NOW() < (
           v_component.last_failure_at
           + MAKE_INTERVAL(secs => v_component.recovery_timeout_seconds)
       )
    THEN
        RAISE EXCEPTION 'Recovery timeout has not elapsed';
    END IF;

    UPDATE components
    SET
        state = 'HEALTHY',
        circuit = 'CLOSED',
        failure_count = 0,
        recovery_count = recovery_count + 1,
        last_error = NULL,
        last_recovery_at = NOW()
    WHERE component_id = p_component_id;

    RETURN TRUE;
END;
$$;

-- ------------------------------------------------------------
-- 10. APPLICATION HEALTH EVALUATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION get_application_health(
    p_application_id BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_state TEXT;
BEGIN
    SELECT
        CASE
            WHEN COUNT(*) FILTER (
                WHERE dependency = 'REQUIRED'
                AND state = 'FAILED'
            ) > 0
                THEN 'UNAVAILABLE'

            WHEN COUNT(*) FILTER (
                WHERE state <> 'HEALTHY'
            ) > 0
                THEN 'DEGRADED'

            ELSE 'HEALTHY'
        END
    INTO v_state
    FROM components
    WHERE application_id = p_application_id;

    RETURN COALESCE(v_state, 'UNAVAILABLE');
END;
$$;

-- ------------------------------------------------------------
-- 11. SAMPLE APPLICATION
-- ------------------------------------------------------------

INSERT INTO applications (
    application_name,
    environment
)
VALUES (
    'Enterprise Commerce Platform',
    'PRODUCTION'
);

INSERT INTO components (
    application_id,
    component_name,
    dependency,
    state,
    circuit,
    fallback,
    criticality,
    failure_threshold,
    recovery_timeout_seconds
)
SELECT
    application_id,
    data.component_name,
    data.dependency::dependency_type,
    data.state::component_state,
    data.circuit::circuit_state,
    data.fallback::fallback_strategy,
    data.criticality,
    data.failure_threshold,
    data.recovery_timeout
FROM applications
CROSS JOIN (
    VALUES
        ('catalog', 'REQUIRED', 'HEALTHY', 'CLOSED', 'NONE', 5, 3, 30),
        ('inventory', 'REQUIRED', 'HEALTHY', 'CLOSED', 'NONE', 5, 3, 30),
        ('recommendations', 'OPTIONAL', 'DEGRADED', 'CLOSED', 'DEFAULT_VALUE', 2, 3, 30),
        ('customer_profile', 'OPTIONAL', 'HEALTHY', 'CLOSED', 'CACHED_VALUE', 2, 3, 30),
        ('analytics', 'OPTIONAL', 'FAILED', 'OPEN', 'QUEUED_OPERATION', 1, 2, 60),
        ('payment_gateway', 'REQUIRED', 'HEALTHY', 'CLOSED', 'NONE', 5, 3, 30)
) AS data(
    component_name,
    dependency,
    state,
    circuit,
    fallback,
    criticality,
    failure_threshold,
    recovery_timeout
)
WHERE application_name = 'Enterprise Commerce Platform';

-- ------------------------------------------------------------
-- 12. COMPONENT DEPENDENCIES
-- ------------------------------------------------------------

INSERT INTO component_dependencies (
    parent_component_id,
    child_component_id,
    relationship_type
)
SELECT
    parent.component_id,
    child.component_id,
    'REQUIRED'
FROM components parent
JOIN components child
    ON parent.application_id = child.application_id
WHERE
    (parent.component_name = 'catalog'
     AND child.component_name = 'inventory')
    OR
    (parent.component_name = 'payment_gateway'
     AND child.component_name = 'inventory');

-- ------------------------------------------------------------
-- 13. REQUEST SAMPLES
-- ------------------------------------------------------------

INSERT INTO service_requests (
    application_id,
    endpoint,
    request_state,
    response_code,
    duration_ms,
    degraded_features
)
SELECT
    application_id,
    sample.endpoint,
    sample.state::request_state,
    sample.response_code,
    sample.duration_ms,
    sample.features
FROM applications
CROSS JOIN (
    VALUES
        ('/products/P-100', 'SUCCESS', 200, 45.2, ARRAY[]::TEXT[]),
        ('/products/P-101', 'DEGRADED', 200, 72.8, ARRAY['recommendations']),
        ('/products/P-102', 'DEGRADED', 200, 88.5, ARRAY['analytics', 'recommendations']),
        ('/checkout', 'FAILED', 503, 120.0, ARRAY[]::TEXT[]),
        ('/products/P-103', 'SUCCESS', 200, 39.1, ARRAY[]::TEXT[])
) AS sample(endpoint, state, response_code, duration_ms, features)
WHERE application_name = 'Enterprise Commerce Platform';

-- ------------------------------------------------------------
-- 14. FAILURE AND RECOVERY TRANSACTION EXAMPLES
-- ------------------------------------------------------------

-- These examples are isolated in a rollback transaction so that
-- the initial sample state remains reproducible.

SAVEPOINT before_failure_demo;

SELECT *
FROM register_component_failure(
    (
        SELECT component_id
        FROM components
        WHERE component_name = 'recommendations'
    ),
    'Recommendation database timeout'
);

ROLLBACK TO SAVEPOINT before_failure_demo;

-- ------------------------------------------------------------
-- 15. HEALTH MONITORING VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW application_component_health AS
SELECT
    a.application_name,
    a.environment,
    c.component_name,
    c.dependency,
    c.state,
    c.circuit,
    c.fallback,
    c.failure_count,
    c.recovery_count,
    c.last_error,
    c.updated_at
FROM applications a
JOIN components c
    ON c.application_id = a.application_id;

-- ------------------------------------------------------------
-- 16. REQUEST PERFORMANCE VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW request_reliability_report AS
SELECT
    a.application_name,
    COUNT(r.request_id) AS total_requests,
    COUNT(*) FILTER (
        WHERE r.request_state = 'SUCCESS'
    ) AS successful_requests,
    COUNT(*) FILTER (
        WHERE r.request_state = 'DEGRADED'
    ) AS degraded_requests,
    COUNT(*) FILTER (
        WHERE r.request_state = 'FAILED'
    ) AS failed_requests,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE r.request_state IN ('SUCCESS', 'DEGRADED')
        ) / NULLIF(COUNT(r.request_id), 0),
        2
    ) AS availability_percentage,
    ROUND(AVG(r.duration_ms), 2) AS average_latency_ms,
    ROUND(
        PERCENTILE_CONT(0.95)
        WITHIN GROUP (ORDER BY r.duration_ms)::NUMERIC,
        2
    ) AS p95_latency_ms
FROM applications a
LEFT JOIN service_requests r
    ON r.application_id = a.application_id
GROUP BY a.application_id, a.application_name;

-- ------------------------------------------------------------
-- 17. FEATURE DEGRADATION ANALYSIS
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW degraded_feature_report AS
SELECT
    a.application_name,
    feature.feature_name,
    COUNT(*) AS occurrence_count
FROM service_requests r
JOIN applications a
    ON a.application_id = r.application_id
CROSS JOIN LATERAL
    UNNEST(r.degraded_features) AS feature(feature_name)
GROUP BY a.application_name, feature.feature_name;

-- ------------------------------------------------------------
-- 18. CIRCUIT BREAKER REPORT
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW circuit_breaker_report AS
SELECT
    c.component_name,
    c.circuit,
    c.failure_count,
    c.failure_threshold,
    c.recovery_timeout_seconds,
    c.last_failure_at,
    CASE
        WHEN c.circuit = 'OPEN'
         AND NOW() >= (
             c.last_failure_at
             + MAKE_INTERVAL(secs => c.recovery_timeout_seconds)
         )
            THEN TRUE
        ELSE FALSE
    END AS recovery_probe_eligible
FROM components c;

-- ------------------------------------------------------------
-- 19. PERFORMANCE AND RELIABILITY QUERIES
-- ------------------------------------------------------------

-- Current application health.
SELECT
    application_name,
    get_application_health(application_id) AS system_health
FROM applications;

-- Component-level failure analysis.
SELECT
    component_name,
    dependency,
    state,
    circuit,
    failure_count,
    last_error
FROM application_component_health
ORDER BY criticality DESC NULLS LAST, component_name;

-- Request success and degraded-service performance.
SELECT *
FROM request_reliability_report;

-- Features most frequently operating through fallbacks.
SELECT *
FROM degraded_feature_report
ORDER BY occurrence_count DESC;

-- Circuit breakers eligible for recovery probes.
SELECT *
FROM circuit_breaker_report
WHERE recovery_probe_eligible;

-- CTE-based operational report.
WITH request_metrics AS (
    SELECT
        application_id,
        COUNT(*) AS total,
        COUNT(*) FILTER (
            WHERE request_state = 'DEGRADED'
        ) AS degraded,
        COUNT(*) FILTER (
            WHERE request_state = 'FAILED'
        ) AS failed
    FROM service_requests
    GROUP BY application_id
),
component_metrics AS (
    SELECT
        application_id,
        COUNT(*) FILTER (
            WHERE dependency = 'REQUIRED'
            AND state = 'FAILED'
        ) AS failed_required,
        COUNT(*) FILTER (
            WHERE state <> 'HEALTHY'
        ) AS unhealthy_components
    FROM components
    GROUP BY application_id
)
SELECT
    a.application_name,
    rm.total,
    rm.degraded,
    rm.failed,
    cm.failed_required,
    cm.unhealthy_components,
    get_application_health(a.application_id) AS health
FROM applications a
LEFT JOIN request_metrics rm
    ON rm.application_id = a.application_id
LEFT JOIN component_metrics cm
    ON cm.application_id = a.application_id;

-- ------------------------------------------------------------
-- 20. DATA VALIDATION QUERIES
-- ------------------------------------------------------------

-- Detect required components incorrectly configured with fallback.
SELECT *
FROM components
WHERE dependency = 'REQUIRED'
AND fallback <> 'NONE';

-- Detect optional dependencies without fallback.
SELECT *
FROM components
WHERE dependency = 'OPTIONAL'
AND fallback = 'NONE';

-- Detect open circuit breakers with no recorded failure timestamp.
SELECT *
FROM components
WHERE circuit = 'OPEN'
AND last_failure_at IS NULL;

-- ------------------------------------------------------------
-- 21. OPERATIONAL RECOVERY PROCEDURE
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE attempt_component_recovery(
    p_component_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT recover_component(p_component_id) THEN
        RAISE EXCEPTION 'Component recovery unsuccessful';
    END IF;

    RAISE NOTICE 'Component % recovered', p_component_id;
END;
$$;

-- The procedure can be invoked by a controlled monitoring worker:
-- CALL attempt_component_recovery(3);

-- ------------------------------------------------------------
-- 22. TRANSACTIONAL REQUEST REGISTRATION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION register_service_request(
    p_application_id BIGINT,
    p_endpoint TEXT,
    p_state request_state,
    p_response_code SMALLINT,
    p_duration_ms NUMERIC,
    p_degraded_features TEXT[] DEFAULT '{}'
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_request_id UUID;
BEGIN
    IF p_endpoint IS NULL OR LENGTH(TRIM(p_endpoint)) = 0 THEN
        RAISE EXCEPTION 'Endpoint cannot be empty';
    END IF;

    IF p_duration_ms < 0 OR p_duration_ms IS NULL THEN
        RAISE EXCEPTION 'Invalid request duration';
    END IF;

    IF p_state = 'FAILED' AND p_response_code < 500 THEN
        RAISE EXCEPTION 'Failed requests require a server error response';
    END IF;

    INSERT INTO service_requests (
        application_id,
        endpoint,
        request_state,
        response_code,
        duration_ms,
        degraded_features
    )
    VALUES (
        p_application_id,
        p_endpoint,
        p_state,
        p_response_code,
        p_duration_ms,
        COALESCE(p_degraded_features, '{}')
    )
    RETURNING request_id INTO v_request_id;

    RETURN v_request_id;
END;
$$;

-- Example:
-- SELECT register_service_request(
--     1, '/products/P-200', 'DEGRADED', 200, 65.5,
--     ARRAY['recommendations']
-- );

-- ------------------------------------------------------------
-- 23. FINAL INTEGRITY CHECKS
-- ------------------------------------------------------------

DO $$
DECLARE
    v_application_id BIGINT;
BEGIN
    SELECT application_id
    INTO v_application_id
    FROM applications
    WHERE application_name = 'Enterprise Commerce Platform';

    IF v_application_id IS NULL THEN
        RAISE EXCEPTION 'Sample application was not created';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM components
        WHERE application_id = v_application_id
        AND component_name = 'catalog'
        AND dependency = 'REQUIRED'
    ) THEN
        RAISE EXCEPTION 'Required catalog component missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM components
        WHERE application_id = v_application_id
        AND component_name = 'recommendations'
        AND dependency = 'OPTIONAL'
        AND fallback <> 'NONE'
    ) THEN
        RAISE EXCEPTION 'Optional fallback configuration missing';
    END IF;

    RAISE NOTICE 'Reliability schema and sample data validated';
END;
$$;

COMMIT;

-- ------------------------------------------------------------
-- OPERATIONAL NOTES
-- ------------------------------------------------------------
-- 1. Required dependencies do not receive silent fallbacks.
-- 2. Optional dependencies must define an explicit fallback.
-- 3. Component state and circuit state represent different concepts.
-- 4. State changes are recorded by the audit trigger.
-- 5. Row-level locking protects concurrent failure transitions.
-- 6. Recovery requires the configured timeout to elapse.
-- 7. Health views distinguish degraded operation from unavailability.
-- 8. Production deployments should restrict procedure execution
--    using database roles and least-privilege permissions.
-- 9. Request and event tables should have retention policies.
-- 10. Cross-service execution must use application-level
--     timeouts, retries, and idempotency controls.
