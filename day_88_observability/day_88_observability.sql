/*
    OBSERVABILITY, STRUCTURED LOGGING AND CENTRALIZED LOGGING

    PostgreSQL 15+

    Implements:
    - Service and environment registration
    - Trace and correlation identifiers
    - Structured JSONB events
    - Centralized event ingestion
    - Severity filtering
    - Sensitive-data redaction
    - Ingestion validation
    - Duplicate detection
    - Alert rules and evaluations
    - Retention and reporting
    - Operational views and indexes
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS observability;

SET search_path TO observability, public;

-- ---------------------------------------------------------
-- 1. Enumerated domain types
-- ---------------------------------------------------------

CREATE TYPE log_severity AS ENUM (
    'DEBUG',
    'INFO',
    'WARNING',
    'ERROR',
    'CRITICAL'
);

CREATE TYPE pipeline_status AS ENUM (
    'ACCEPTED',
    'REJECTED',
    'DUPLICATE'
);

CREATE TYPE alert_status AS ENUM (
    'NORMAL',
    'FIRING',
    'INSUFFICIENT_DATA'
);

-- ---------------------------------------------------------
-- 2. Service registry
-- ---------------------------------------------------------

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name VARCHAR(150) NOT NULL UNIQUE,
    owner_team VARCHAR(120) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT service_name_not_empty
        CHECK (length(trim(service_name)) > 0)
);

CREATE TABLE service_environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL
        REFERENCES services(service_id) ON DELETE RESTRICT,

    environment_name VARCHAR(30) NOT NULL,
    version VARCHAR(50) NOT NULL,
    minimum_severity log_severity NOT NULL DEFAULT 'INFO',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE (service_id, environment_name),

    CHECK (
        environment_name IN (
            'development',
            'testing',
            'staging',
            'production'
        )
    )
);

-- ---------------------------------------------------------
-- 3. Trace and request context
-- ---------------------------------------------------------

CREATE TABLE trace_contexts (
    trace_id UUID PRIMARY KEY,
    correlation_id VARCHAR(150) NOT NULL,
    root_span_id UUID NOT NULL,
    request_id UUID NOT NULL,
    tenant_id VARCHAR(100),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_correlation_id
        CHECK (length(trim(correlation_id)) > 0)
);

CREATE INDEX idx_trace_correlation
    ON trace_contexts(correlation_id);

CREATE INDEX idx_trace_request
    ON trace_contexts(request_id);

-- ---------------------------------------------------------
-- 4. Central structured event store
-- ---------------------------------------------------------

CREATE TABLE log_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id) ON DELETE RESTRICT,

    environment_id BIGINT NOT NULL
        REFERENCES service_environments(environment_id)
        ON DELETE RESTRICT,

    trace_id UUID NOT NULL
        REFERENCES trace_contexts(trace_id) ON DELETE RESTRICT,

    span_id UUID NOT NULL,

    event_key UUID NOT NULL,

    event_timestamp TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    severity log_severity NOT NULL,

    event_name VARCHAR(180) NOT NULL,
    message TEXT NOT NULL,

    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,

    source_host VARCHAR(150),

    CONSTRAINT event_name_not_empty
        CHECK (length(trim(event_name)) > 0),

    CONSTRAINT attributes_must_be_object
        CHECK (jsonb_typeof(attributes) = 'object'),

    UNIQUE (service_id, event_key)
);

-- Indexes support the most common operational searches.
CREATE INDEX idx_logs_service_timestamp
    ON log_events(service_id, event_timestamp DESC);

CREATE INDEX idx_logs_severity_timestamp
    ON log_events(severity, event_timestamp DESC);

CREATE INDEX idx_logs_trace
    ON log_events(trace_id, event_timestamp);

CREATE INDEX idx_logs_event_name
    ON log_events(event_name, event_timestamp DESC);

CREATE INDEX idx_logs_attributes
    ON log_events USING GIN(attributes);

CREATE INDEX idx_logs_errors
    ON log_events(service_id, event_timestamp DESC)
    WHERE severity IN ('ERROR', 'CRITICAL');

-- ---------------------------------------------------------
-- 5. Sensitive attribute protection
-- ---------------------------------------------------------

CREATE OR REPLACE FUNCTION redact_sensitive_attributes(
    p_attributes JSONB
)
RETURNS JSONB
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT COALESCE(
        jsonb_object_agg(
            key,
            CASE
                WHEN lower(key) IN (
                    'password',
                    'token',
                    'access_token',
                    'refresh_token',
                    'authorization',
                    'api_key',
                    'secret',
                    'credit_card'
                )
                THEN '"[REDACTED]"'::jsonb
                ELSE value
            END
        ),
        '{}'::jsonb
    )
    FROM jsonb_each(p_attributes);
$$;

CREATE OR REPLACE FUNCTION protect_log_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_service_id BIGINT;
    v_minimum_severity log_severity;
    v_service_enabled BOOLEAN;
    v_environment_enabled BOOLEAN;
    v_environment_service BIGINT;
    v_severity_rank INTEGER;
    v_minimum_rank INTEGER;
BEGIN
    SELECT
        se.service_id,
        se.minimum_severity,
        se.enabled
    INTO
        v_environment_service,
        v_minimum_severity,
        v_environment_enabled
    FROM service_environments se
    WHERE se.environment_id = NEW.environment_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown environment';
    END IF;

    IF v_environment_service <> NEW.service_id THEN
        RAISE EXCEPTION
            'Environment does not belong to supplied service';
    END IF;

    SELECT enabled
    INTO v_service_enabled
    FROM service_environments
    WHERE environment_id = NEW.environment_id;

    IF NOT v_environment_enabled OR NOT v_service_enabled THEN
        RAISE EXCEPTION 'Logging environment is disabled';
    END IF;

    SELECT
        CASE severity
            WHEN 'DEBUG' THEN 10
            WHEN 'INFO' THEN 20
            WHEN 'WARNING' THEN 30
            WHEN 'ERROR' THEN 40
            WHEN 'CRITICAL' THEN 50
        END
    INTO v_severity_rank
    FROM (SELECT NEW.severity AS severity) s;

    SELECT
        CASE v_minimum_severity
            WHEN 'DEBUG' THEN 10
            WHEN 'INFO' THEN 20
            WHEN 'WARNING' THEN 30
            WHEN 'ERROR' THEN 40
            WHEN 'CRITICAL' THEN 50
        END
    INTO v_minimum_rank;

    IF v_severity_rank < v_minimum_rank THEN
        RAISE EXCEPTION
            'Event severity is below configured service threshold';
    END IF;

    NEW.attributes :=
        redact_sensitive_attributes(NEW.attributes);

    NEW.message := regexp_replace(
        NEW.message,
        '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
        '[REDACTED_EMAIL]',
        'gi'
    );

    NEW.ingested_at := NOW();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_protect_log_event
BEFORE INSERT ON log_events
FOR EACH ROW
EXECUTE FUNCTION protect_log_event();

-- ---------------------------------------------------------
-- 6. Ingestion audit
-- ---------------------------------------------------------

CREATE TABLE ingestion_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT
        REFERENCES services(service_id) ON DELETE SET NULL,

    event_key UUID,
    status pipeline_status NOT NULL,
    reason TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ingestion_audit_status
    ON ingestion_audit(status, processed_at DESC);

-- ---------------------------------------------------------
-- 7. Centralized ingestion procedure
-- ---------------------------------------------------------

CREATE OR REPLACE FUNCTION ingest_log_event(
    p_service_id BIGINT,
    p_environment_id BIGINT,
    p_trace_id UUID,
    p_span_id UUID,
    p_event_key UUID,
    p_event_timestamp TIMESTAMPTZ,
    p_severity log_severity,
    p_event_name VARCHAR,
    p_message TEXT,
    p_attributes JSONB DEFAULT '{}'::jsonb,
    p_source_host VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    result_status pipeline_status,
    result_event_id BIGINT,
    result_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    IF p_attributes IS NULL
       OR jsonb_typeof(p_attributes) <> 'object' THEN

        INSERT INTO ingestion_audit(
            service_id,
            event_key,
            status,
            reason
        )
        VALUES (
            p_service_id,
            p_event_key,
            'REJECTED',
            'Attributes must be a JSON object'
        );

        RETURN QUERY SELECT
            'REJECTED'::pipeline_status,
            NULL::BIGINT,
            'Invalid structured attributes'::TEXT;

        RETURN;
    END IF;

    IF p_event_name IS NULL
       OR length(trim(p_event_name)) = 0
       OR p_message IS NULL
       OR p_trace_id IS NULL
       OR p_span_id IS NULL
       OR p_event_key IS NULL
       OR p_event_timestamp IS NULL THEN

        INSERT INTO ingestion_audit(
            service_id,
            event_key,
            status,
            reason
        )
        VALUES (
            p_service_id,
            p_event_key,
            'REJECTED',
            'Required event field is missing'
        );

        RETURN QUERY SELECT
            'REJECTED'::pipeline_status,
            NULL::BIGINT,
            'Missing required event field'::TEXT;

        RETURN;
    END IF;

    INSERT INTO log_events(
        service_id,
        environment_id,
        trace_id,
        span_id,
        event_key,
        event_timestamp,
        severity,
        event_name,
        message,
        attributes,
        source_host
    )
    VALUES (
        p_service_id,
        p_environment_id,
        p_trace_id,
        p_span_id,
        p_event_key,
        p_event_timestamp,
        p_severity,
        p_event_name,
        p_message,
        p_attributes,
        p_source_host
    )
    ON CONFLICT (service_id, event_key)
    DO NOTHING
    RETURNING event_id INTO v_event_id;

    IF v_event_id IS NULL THEN
        INSERT INTO ingestion_audit(
            service_id,
            event_key,
            status,
            reason
        )
        VALUES (
            p_service_id,
            p_event_key,
            'DUPLICATE',
            'Event identifier already ingested'
        );

        RETURN QUERY SELECT
            'DUPLICATE'::pipeline_status,
            NULL::BIGINT,
            'Duplicate event ignored'::TEXT;
    ELSE
        INSERT INTO ingestion_audit(
            service_id,
            event_key,
            status,
            reason
        )
        VALUES (
            p_service_id,
            p_event_key,
            'ACCEPTED',
            'Event stored successfully'
        );

        RETURN QUERY SELECT
            'ACCEPTED'::pipeline_status,
            v_event_id,
            'Event accepted'::TEXT;
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        -- Constraint, trigger, and referential-integrity failures
        -- are recorded without leaving a partially inserted event.
        INSERT INTO ingestion_audit(
            service_id,
            event_key,
            status,
            reason
        )
        VALUES (
            p_service_id,
            p_event_key,
            'REJECTED',
            SQLSTATE || ': ' || SQLERRM
        );

        RETURN QUERY SELECT
            'REJECTED'::pipeline_status,
            NULL::BIGINT,
            SQLERRM;
END;
$$;

-- ---------------------------------------------------------
-- 8. Alert policies
-- ---------------------------------------------------------

CREATE TABLE alert_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id) ON DELETE CASCADE,

    rule_name VARCHAR(150) NOT NULL,

    minimum_error_rate NUMERIC(5,4) NOT NULL,
    minimum_events INTEGER NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(service_id, rule_name),

    CHECK (
        minimum_error_rate >= 0
        AND minimum_error_rate <= 1
    ),

    CHECK (minimum_events > 0)
);

CREATE TABLE alert_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    rule_id BIGINT NOT NULL
        REFERENCES alert_rules(rule_id) ON DELETE CASCADE,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    total_events INTEGER NOT NULL,
    error_events INTEGER NOT NULL,

    error_rate NUMERIC(7,5) NOT NULL,

    status alert_status NOT NULL,

    CHECK (total_events >= 0),
    CHECK (error_events >= 0),
    CHECK (error_events <= total_events),
    CHECK (error_rate >= 0 AND error_rate <= 1)
);

CREATE INDEX idx_alert_evaluations_rule_time
    ON alert_evaluations(rule_id, evaluated_at DESC);

-- ---------------------------------------------------------
-- 9. Reporting views
-- ---------------------------------------------------------

CREATE OR REPLACE VIEW v_log_event_details AS
SELECT
    e.event_id,
    s.service_name,
    s.owner_team,
    se.environment_name,
    se.version,
    e.event_timestamp,
    e.ingested_at,
    e.severity,
    e.event_name,
    e.message,
    e.trace_id,
    tc.correlation_id,
    tc.request_id,
    e.attributes,
    e.source_host
FROM log_events e
JOIN services s
    ON s.service_id = e.service_id
JOIN service_environments se
    ON se.environment_id = e.environment_id
JOIN trace_contexts tc
    ON tc.trace_id = e.trace_id;

CREATE OR REPLACE VIEW v_service_health AS
SELECT
    s.service_id,
    s.service_name,
    COUNT(e.event_id) AS total_events,

    COUNT(e.event_id) FILTER (
        WHERE e.severity IN ('ERROR', 'CRITICAL')
    ) AS error_events,

    ROUND(
        COALESCE(
            COUNT(e.event_id) FILTER (
                WHERE e.severity IN ('ERROR', 'CRITICAL')
            )::NUMERIC /
            NULLIF(COUNT(e.event_id), 0),
            0
        ),
        4
    ) AS error_rate,

    CASE
        WHEN COUNT(e.event_id) = 0 THEN 'NO_DATA'
        WHEN COUNT(e.event_id) FILTER (
            WHERE e.severity IN ('ERROR', 'CRITICAL')
        ) > 0 THEN 'DEGRADED'
        ELSE 'HEALTHY'
    END AS health_status

FROM services s
LEFT JOIN log_events e
    ON e.service_id = s.service_id
GROUP BY s.service_id, s.service_name;

CREATE OR REPLACE VIEW v_trace_timeline AS
SELECT
    trace_id,
    correlation_id,
    request_id,
    service_name,
    event_timestamp,
    severity,
    event_name,
    message,
    span_id
FROM v_log_event_details
ORDER BY trace_id, event_timestamp;

-- ---------------------------------------------------------
-- 10. Alert evaluation function
-- ---------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_alert_rule(
    p_rule_id BIGINT
)
RETURNS alert_evaluations
LANGUAGE plpgsql
AS $$
DECLARE
    v_rule alert_rules%ROWTYPE;
    v_total INTEGER;
    v_errors INTEGER;
    v_rate NUMERIC(7,5);
    v_status alert_status;
    v_result alert_evaluations%ROWTYPE;
BEGIN
    SELECT *
    INTO v_rule
    FROM alert_rules
    WHERE rule_id = p_rule_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Alert rule % does not exist', p_rule_id;
    END IF;

    IF NOT v_rule.enabled THEN
        RAISE EXCEPTION 'Alert rule is disabled';
    END IF;

    SELECT
        COUNT(*)::INTEGER,
        COUNT(*) FILTER (
            WHERE severity IN ('ERROR', 'CRITICAL')
        )::INTEGER
    INTO v_total, v_errors
    FROM log_events
    WHERE service_id = v_rule.service_id;

    v_rate := COALESCE(
        v_errors::NUMERIC / NULLIF(v_total, 0),
        0
    );

    IF v_total < v_rule.minimum_events THEN
        v_status := 'INSUFFICIENT_DATA';
    ELSIF v_rate >= v_rule.minimum_error_rate THEN
        v_status := 'FIRING';
    ELSE
        v_status := 'NORMAL';
    END IF;

    INSERT INTO alert_evaluations(
        rule_id,
        total_events,
        error_events,
        error_rate,
        status
    )
    VALUES (
        p_rule_id,
        v_total,
        v_errors,
        v_rate,
        v_status
    )
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$;

-- ---------------------------------------------------------
-- 11. Retention procedure
-- ---------------------------------------------------------

CREATE OR REPLACE PROCEDURE purge_old_log_events(
    p_retention_days INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_retention_days <= 0 THEN
        RAISE EXCEPTION 'Retention must be positive';
    END IF;

    DELETE FROM log_events
    WHERE event_timestamp <
        NOW() - make_interval(days => p_retention_days);
END;
$$;

-- ---------------------------------------------------------
-- 12. Representative service records
-- ---------------------------------------------------------

INSERT INTO services(
    service_name,
    owner_team,
    description
)
VALUES
(
    'payment-service',
    'Payments Engineering',
    'Processes customer payment transactions'
),
(
    'identity-service',
    'Identity Engineering',
    'Handles authentication and authorization'
),
(
    'notification-service',
    'Platform Engineering',
    'Dispatches transactional notifications'
);

INSERT INTO service_environments(
    service_id,
    environment_name,
    version,
    minimum_severity
)
SELECT
    service_id,
    'production',
    CASE service_name
        WHEN 'payment-service' THEN '2.4.1'
        WHEN 'identity-service' THEN '3.1.0'
        ELSE '1.8.0'
    END,
    'DEBUG'
FROM services;

-- ---------------------------------------------------------
-- 13. Trace records
-- ---------------------------------------------------------

INSERT INTO trace_contexts(
    trace_id,
    correlation_id,
    root_span_id,
    request_id,
    tenant_id
)
VALUES
(
    '10000000-0000-0000-0000-000000000001',
    'order-2026-001',
    '20000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000001',
    'tenant-a'
),
(
    '10000000-0000-0000-0000-000000000002',
    'order-2026-002',
    '20000000-0000-0000-0000-000000000002',
    '30000000-0000-0000-0000-000000000002',
    'tenant-b'
);

-- ---------------------------------------------------------
-- 14. Sample centralized events
-- ---------------------------------------------------------

DO $$
DECLARE
    v_payment BIGINT;
    v_identity BIGINT;
    v_environment BIGINT;
BEGIN
    SELECT service_id INTO v_payment
    FROM services
    WHERE service_name = 'payment-service';

    SELECT service_id INTO v_identity
    FROM services
    WHERE service_name = 'identity-service';

    SELECT environment_id INTO v_environment
    FROM service_environments
    WHERE service_id = v_payment
      AND environment_name = 'production';

    PERFORM ingest_log_event(
        v_payment,
        v_environment,
        '10000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000011',
        '40000000-0000-0000-0000-000000000001',
        NOW() - INTERVAL '5 minutes',
        'INFO',
        'payment.started',
        'Payment processing started',
        '{"amount": 1250.50, "operation": "charge"}'
    );

    PERFORM ingest_log_event(
        v_payment,
        v_environment,
        '10000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000012',
        '40000000-0000-0000-0000-000000000002',
        NOW() - INTERVAL '4 minutes',
        'INFO',
        'payment.completed',
        'Payment completed',
        '{"amount": 1250.50, "status": "COMPLETED"}'
    );

    PERFORM ingest_log_event(
        v_payment,
        v_environment,
        '10000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000013',
        '40000000-0000-0000-0000-000000000003',
        NOW() - INTERVAL '3 minutes',
        'ERROR',
        'payment.failed',
        'Payment gateway unavailable',
        '{"error_type": "GatewayTimeout", "amount": 500}'
    );

    PERFORM ingest_log_event(
        v_payment,
        v_environment,
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000021',
        '40000000-0000-0000-0000-000000000004',
        NOW() - INTERVAL '2 minutes',
        'ERROR',
        'payment.failed',
        'Transaction processing failed',
        '{"error_type": "DatabaseError", "amount": 800}'
    );

    PERFORM ingest_log_event(
        v_payment,
        v_environment,
        '10000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000022',
        '40000000-0000-0000-0000-000000000005',
        NOW() - INTERVAL '1 minute',
        'WARNING',
        'authentication.failure',
        'Login failed for analyst@example.com',
        '{
            "username": "analyst",
            "password": "example-password",
            "access_token": "sensitive-token"
        }'
    );

    SELECT environment_id INTO v_environment
    FROM service_environments
    WHERE service_id = v_identity
      AND environment_name = 'production';

    PERFORM ingest_log_event(
        v_identity,
        v_environment,
        '10000000-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000031',
        '40000000-0000-0000-0000-000000000006',
        NOW(),
        'INFO',
        'authentication.success',
        'User authenticated successfully',
        '{"operation": "login", "status": "SUCCESS"}'
    );
END;
$$;

-- ---------------------------------------------------------
-- 15. Demonstrate duplicate event handling
-- ---------------------------------------------------------

SELECT *
FROM ingest_log_event(
    (
        SELECT service_id
        FROM services
        WHERE service_name = 'payment-service'
    ),
    (
        SELECT environment_id
        FROM service_environments se
        JOIN services s USING (service_id)
        WHERE s.service_name = 'payment-service'
          AND se.environment_name = 'production'
    ),
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000011',
    '40000000-0000-0000-0000-000000000001',
    NOW(),
    'INFO',
    'payment.started',
    'Duplicate event',
    '{"amount": 1250.50}'
);

-- ---------------------------------------------------------
-- 16. Configure alert policies
-- ---------------------------------------------------------

INSERT INTO alert_rules(
    service_id,
    rule_name,
    minimum_error_rate,
    minimum_events
)
SELECT
    service_id,
    'payment-error-rate',
    0.30,
    3
FROM services
WHERE service_name = 'payment-service';

INSERT INTO alert_rules(
    service_id,
    rule_name,
    minimum_error_rate,
    minimum_events
)
SELECT
    service_id,
    'identity-error-rate',
    0.20,
    5
FROM services
WHERE service_name = 'identity-service';

-- ---------------------------------------------------------
-- 17. Execute alert evaluations
-- ---------------------------------------------------------

SELECT evaluate_alert_rule(rule_id)
FROM alert_rules
WHERE enabled = TRUE;

COMMIT;

-- =========================================================
-- 18. Retrieval and operational reporting
-- =========================================================

-- Recent events across centralized services.
SELECT
    service_name,
    severity,
    event_name,
    event_timestamp,
    trace_id,
    attributes
FROM v_log_event_details
ORDER BY event_timestamp DESC;

-- Trace-specific investigation.
SELECT
    trace_id,
    correlation_id,
    service_name,
    event_timestamp,
    event_name,
    severity,
    message
FROM v_trace_timeline
WHERE trace_id =
    '10000000-0000-0000-0000-000000000001'
ORDER BY event_timestamp;

-- Error events for incident investigation.
SELECT *
FROM v_log_event_details
WHERE severity IN ('ERROR', 'CRITICAL')
ORDER BY event_timestamp DESC;

-- JSON attribute search.
SELECT
    event_id,
    event_name,
    attributes
FROM log_events
WHERE attributes @> '{"error_type": "GatewayTimeout"}'::jsonb;

-- Service-level health.
SELECT *
FROM v_service_health
ORDER BY error_rate DESC;

-- Event frequency by service and event name.
SELECT
    service_name,
    event_name,
    COUNT(*) AS occurrence_count,
    COUNT(*) FILTER (
        WHERE severity IN ('ERROR', 'CRITICAL')
    ) AS error_count
FROM v_log_event_details
GROUP BY service_name, event_name
ORDER BY occurrence_count DESC;

-- Severity distribution.
SELECT
    severity,
    COUNT(*) AS event_count
FROM log_events
GROUP BY severity
ORDER BY severity;

-- Ingestion reliability.
SELECT
    status,
    COUNT(*) AS total,
    MAX(processed_at) AS latest_processing
FROM ingestion_audit
GROUP BY status
ORDER BY status;

-- Alert evaluation history.
SELECT
    ar.rule_name,
    ae.evaluated_at,
    ae.total_events,
    ae.error_events,
    ae.error_rate,
    ae.status
FROM alert_evaluations ae
JOIN alert_rules ar
    ON ar.rule_id = ae.rule_id
ORDER BY ae.evaluated_at DESC;

-- Eligibility for an operational alert.
SELECT
    ar.rule_name,
    ar.minimum_error_rate,
    ar.minimum_events,
    sh.total_events,
    sh.error_rate,
    CASE
        WHEN sh.total_events < ar.minimum_events
            THEN 'INSUFFICIENT_DATA'
        WHEN sh.error_rate >= ar.minimum_error_rate
            THEN 'FIRING'
        ELSE 'NORMAL'
    END AS calculated_status
FROM alert_rules ar
JOIN v_service_health sh
    ON sh.service_id = ar.service_id
WHERE ar.enabled = TRUE;

-- Redaction verification.
SELECT
    event_name,
    attributes
FROM log_events
WHERE event_name = 'authentication.failure';

-- =========================================================
-- 19. Retention execution example
-- =========================================================

-- Execute explicitly when the retention policy requires it.
-- CALL purge_old_log_events(90);

-- =========================================================
-- 20. Transactional workflow example
-- =========================================================

BEGIN;

UPDATE service_environments
SET minimum_severity = 'WARNING'
WHERE environment_name = 'production'
  AND service_id = (
      SELECT service_id
      FROM services
      WHERE service_name = 'notification-service'
  );

-- Inspect the policy change before committing.
SELECT
    s.service_name,
    se.environment_name,
    se.minimum_severity
FROM service_environments se
JOIN services s USING (service_id)
WHERE s.service_name = 'notification-service';

COMMIT;
