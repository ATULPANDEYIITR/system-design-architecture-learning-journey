/*
===============================================================================
SERVICE DISCOVERY DATABASE
===============================================================================

PostgreSQL 15+

Domain:
    Service registration
    Service instance management
    Health monitoring
    Lease expiration
    Endpoint discovery
    Circuit-breaker state
    Weighted routing
    Graceful draining
    Registration authorization
    Discovery audit

The database stores registry state and evaluates discovery eligibility.
Network probes are performed by external health-monitoring workers.

Run:
    psql -v ON_ERROR_STOP=1 -d your_database -f service_discovery.sql

The schema is recreated when this script is executed.
*/

BEGIN;

DROP SCHEMA IF EXISTS service_discovery CASCADE;

CREATE SCHEMA service_discovery;

SET search_path TO service_discovery, public;

-- ============================================================================
-- DOMAIN TYPES
-- ============================================================================

CREATE TYPE environment_type AS ENUM (
    'DEVELOPMENT',
    'STAGING',
    'PRODUCTION'
);

CREATE TYPE instance_health AS ENUM (
    'UNKNOWN',
    'HEALTHY',
    'UNHEALTHY',
    'DRAINING'
);

CREATE TYPE registration_state AS ENUM (
    'PENDING',
    'ACTIVE',
    'REJECTED',
    'DEREGISTERED'
);

CREATE TYPE check_status AS ENUM (
    'PASS',
    'FAIL',
    'TIMEOUT',
    'UNKNOWN'
);

CREATE TYPE circuit_state AS ENUM (
    'CLOSED',
    'OPEN',
    'HALF_OPEN'
);

-- ============================================================================
-- REPOSITORY-LIKE SERVICE CATALOG
-- ============================================================================

CREATE TABLE service_owners (
    owner_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL UNIQUE,
    authorized_for_production BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_name VARCHAR(150) NOT NULL UNIQUE,

    description TEXT NOT NULL DEFAULT '',

    owner_id BIGINT NOT NULL
        REFERENCES service_owners(owner_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (length(trim(service_name)) > 0)
);

CREATE TABLE service_versions (
    version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    version VARCHAR(40) NOT NULL,

    environment environment_type NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (service_id, version, environment)
);

-- ============================================================================
-- INSTANCE REGISTRATION
-- ============================================================================

CREATE TABLE service_instances (
    instance_id UUID PRIMARY KEY,

    version_id BIGINT NOT NULL
        REFERENCES service_versions(version_id),

    host INET NOT NULL,

    port INTEGER NOT NULL,

    health instance_health NOT NULL DEFAULT 'UNKNOWN',

    registration registration_state NOT NULL DEFAULT 'PENDING',

    region VARCHAR(80) NOT NULL,

    availability_zone VARCHAR(100),

    weight INTEGER NOT NULL DEFAULT 1,

    lease_seconds INTEGER NOT NULL DEFAULT 30,

    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    deregistered_at TIMESTAMPTZ,

    generation BIGINT NOT NULL DEFAULT 1,

    UNIQUE (version_id, host, port),

    CHECK (port BETWEEN 1 AND 65535),

    CHECK (weight BETWEEN 1 AND 1000),

    CHECK (lease_seconds BETWEEN 1 AND 86400),

    CHECK (generation > 0),

    CHECK (length(trim(region)) > 0),

    CHECK (
        (registration = 'DEREGISTERED' AND deregistered_at IS NOT NULL)
        OR
        (registration <> 'DEREGISTERED' AND deregistered_at IS NULL)
    )
);

CREATE TABLE instance_metadata (
    instance_id UUID NOT NULL
        REFERENCES service_instances(instance_id)
        ON DELETE CASCADE,

    metadata_key VARCHAR(100) NOT NULL,

    metadata_value TEXT NOT NULL,

    PRIMARY KEY (instance_id, metadata_key),

    CHECK (length(trim(metadata_key)) > 0)
);

-- ============================================================================
-- HEALTH MONITORING
-- ============================================================================

CREATE TABLE health_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id)
        ON DELETE CASCADE,

    failure_threshold INTEGER NOT NULL DEFAULT 2,

    recovery_threshold INTEGER NOT NULL DEFAULT 2,

    check_interval_seconds INTEGER NOT NULL DEFAULT 10,

    timeout_ms INTEGER NOT NULL DEFAULT 2000,

    UNIQUE (service_id),

    CHECK (failure_threshold BETWEEN 1 AND 100),

    CHECK (recovery_threshold BETWEEN 1 AND 100),

    CHECK (check_interval_seconds > 0),

    CHECK (timeout_ms > 0)
);

CREATE TABLE health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    instance_id UUID NOT NULL
        REFERENCES service_instances(instance_id)
        ON DELETE CASCADE,

    checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    status check_status NOT NULL,

    response_time_ms INTEGER,

    failure_reason TEXT,

    checker_id VARCHAR(120) NOT NULL,

    CHECK (
        response_time_ms IS NULL OR response_time_ms >= 0
    ),

    CHECK (length(trim(checker_id)) > 0)
);

CREATE TABLE health_counters (
    instance_id UUID PRIMARY KEY
        REFERENCES service_instances(instance_id)
        ON DELETE CASCADE,

    consecutive_failures INTEGER NOT NULL DEFAULT 0,

    consecutive_successes INTEGER NOT NULL DEFAULT 0,

    CHECK (consecutive_failures >= 0),

    CHECK (consecutive_successes >= 0)
);

-- ============================================================================
-- CIRCUIT BREAKERS
-- ============================================================================

CREATE TABLE circuit_breakers (
    instance_id UUID PRIMARY KEY
        REFERENCES service_instances(instance_id)
        ON DELETE CASCADE,

    state circuit_state NOT NULL DEFAULT 'CLOSED',

    consecutive_failures INTEGER NOT NULL DEFAULT 0,

    failure_threshold INTEGER NOT NULL DEFAULT 3,

    opened_at TIMESTAMPTZ,

    reset_after_seconds INTEGER NOT NULL DEFAULT 5,

    CHECK (consecutive_failures >= 0),

    CHECK (failure_threshold > 0),

    CHECK (reset_after_seconds >= 0),

    CHECK (
        (state = 'CLOSED' AND opened_at IS NULL)
        OR
        (state <> 'CLOSED' AND opened_at IS NOT NULL)
    )
);

-- ============================================================================
-- REGISTRATION AUTHORIZATION
-- ============================================================================

CREATE TABLE registration_requests (
    request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    instance_id UUID NOT NULL UNIQUE,

    version_id BIGINT NOT NULL
        REFERENCES service_versions(version_id),

    requested_by VARCHAR(120) NOT NULL,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    state registration_state NOT NULL DEFAULT 'PENDING',

    decision_reason TEXT,

    CHECK (length(trim(requested_by)) > 0)
);

CREATE TABLE registration_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    instance_id UUID NOT NULL,

    event_type VARCHAR(60) NOT NULL,

    event_details JSONB NOT NULL DEFAULT '{}'::jsonb,

    actor VARCHAR(120) NOT NULL,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX idx_instances_service_version
ON service_instances(version_id, registration, health);

CREATE INDEX idx_instances_region
ON service_instances(region, health);

CREATE INDEX idx_instances_heartbeat
ON service_instances(last_heartbeat);

CREATE INDEX idx_health_checks_instance_time
ON health_checks(instance_id, checked_at DESC);

CREATE INDEX idx_health_checks_status
ON health_checks(status, checked_at DESC);

CREATE INDEX idx_audit_instance_time
ON registration_audit(instance_id, occurred_at DESC);

CREATE INDEX idx_metadata_lookup
ON instance_metadata(metadata_key, metadata_value, instance_id);

CREATE INDEX idx_pending_registrations
ON registration_requests(requested_at)
WHERE state = 'PENDING';

CREATE INDEX idx_discoverable_instances
ON service_instances(version_id, region)
WHERE registration = 'ACTIVE'
AND health = 'HEALTHY';

-- ============================================================================
-- AUDIT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION record_instance_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO registration_audit (
        instance_id,
        event_type,
        event_details,
        actor
    )
    VALUES (
        NEW.instance_id,
        'INSTANCE_STATE_CHANGED',
        jsonb_build_object(
            'old_health', OLD.health,
            'new_health', NEW.health,
            'old_registration', OLD.registration,
            'new_registration', NEW.registration
        ),
        current_user
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_instance_state_audit
AFTER UPDATE OF health, registration
ON service_instances
FOR EACH ROW
WHEN (
    OLD.health IS DISTINCT FROM NEW.health
    OR OLD.registration IS DISTINCT FROM NEW.registration
)
EXECUTE FUNCTION record_instance_change();

-- ============================================================================
-- REGISTRATION FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION register_instance(
    p_instance_id UUID,
    p_service_name VARCHAR,
    p_version VARCHAR,
    p_environment environment_type,
    p_host INET,
    p_port INTEGER,
    p_region VARCHAR,
    p_requested_by VARCHAR,
    p_weight INTEGER DEFAULT 1,
    p_lease_seconds INTEGER DEFAULT 30
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_service_id BIGINT;
    v_version_id BIGINT;
    v_owner_id BIGINT;
    v_authorized BOOLEAN;
BEGIN
    IF p_instance_id IS NULL THEN
        RAISE EXCEPTION 'Instance ID is required';
    END IF;

    IF p_port NOT BETWEEN 1 AND 65535 THEN
        RAISE EXCEPTION 'Invalid service port';
    END IF;

    IF p_weight NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'Invalid endpoint weight';
    END IF;

    IF p_lease_seconds NOT BETWEEN 1 AND 86400 THEN
        RAISE EXCEPTION 'Invalid lease duration';
    END IF;

    SELECT service_id, owner_id
    INTO v_service_id, v_owner_id
    FROM services
    WHERE service_name = p_service_name;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown service: %', p_service_name;
    END IF;

    SELECT authorized_for_production
    INTO v_authorized
    FROM service_owners
    WHERE owner_id = v_owner_id;

    IF p_environment = 'PRODUCTION'
       AND NOT v_authorized THEN
        RAISE EXCEPTION 'Owner is not authorized for production';
    END IF;

    SELECT version_id
    INTO v_version_id
    FROM service_versions
    WHERE service_id = v_service_id
      AND version = p_version
      AND environment = p_environment;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Service version is not registered';
    END IF;

    INSERT INTO service_instances (
        instance_id,
        version_id,
        host,
        port,
        region,
        weight,
        lease_seconds
    )
    VALUES (
        p_instance_id,
        v_version_id,
        p_host,
        p_port,
        p_region,
        p_weight,
        p_lease_seconds
    );

    INSERT INTO health_counters(instance_id)
    VALUES (p_instance_id);

    INSERT INTO circuit_breakers(instance_id)
    VALUES (p_instance_id);

    INSERT INTO registration_requests (
        instance_id,
        version_id,
        requested_by,
        state
    )
    VALUES (
        p_instance_id,
        v_version_id,
        p_requested_by,
        'ACTIVE'
    );

    UPDATE service_instances
    SET registration = 'ACTIVE'
    WHERE instance_id = p_instance_id;

    INSERT INTO registration_audit (
        instance_id,
        event_type,
        event_details,
        actor
    )
    VALUES (
        p_instance_id,
        'REGISTERED',
        jsonb_build_object(
            'service', p_service_name,
            'version', p_version,
            'region', p_region
        ),
        p_requested_by
    );

    RETURN p_instance_id;
END;
$$;

-- ============================================================================
-- HEALTH CHECK PROCESSING
-- ============================================================================

CREATE OR REPLACE FUNCTION process_health_check(
    p_instance_id UUID,
    p_status check_status,
    p_response_time_ms INTEGER,
    p_checker_id VARCHAR,
    p_failure_reason TEXT DEFAULT NULL
)
RETURNS instance_health
LANGUAGE plpgsql
AS $$
DECLARE
    v_service_id BIGINT;
    v_failure_threshold INTEGER;
    v_recovery_threshold INTEGER;
    v_failures INTEGER;
    v_successes INTEGER;
    v_health instance_health;
BEGIN
    SELECT sv.service_id
    INTO v_service_id
    FROM service_instances si
    JOIN service_versions sv
      ON sv.version_id = si.version_id
    WHERE si.instance_id = p_instance_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown instance: %', p_instance_id;
    END IF;

    SELECT failure_threshold, recovery_threshold
    INTO v_failure_threshold, v_recovery_threshold
    FROM health_policies
    WHERE service_id = v_service_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Health policy missing';
    END IF;

    -- Lock the instance counters to serialize concurrent health updates.
    SELECT consecutive_failures, consecutive_successes
    INTO v_failures, v_successes
    FROM health_counters
    WHERE instance_id = p_instance_id
    FOR UPDATE;

    SELECT health
    INTO v_health
    FROM service_instances
    WHERE instance_id = p_instance_id
    FOR UPDATE;

    IF v_health = 'DRAINING' THEN
        INSERT INTO health_checks (
            instance_id,
            status,
            response_time_ms,
            failure_reason,
            checker_id
        )
        VALUES (
            p_instance_id,
            p_status,
            p_response_time_ms,
            p_failure_reason,
            p_checker_id
        );

        RETURN v_health;
    END IF;

    IF p_status = 'PASS' THEN
        v_failures := 0;
        v_successes := v_successes + 1;

        IF v_successes >= v_recovery_threshold THEN
            v_health := 'HEALTHY';
        END IF;
    ELSE
        v_successes := 0;
        v_failures := v_failures + 1;

        IF v_failures >= v_failure_threshold THEN
            v_health := 'UNHEALTHY';
        END IF;
    END IF;

    UPDATE health_counters
    SET consecutive_failures = v_failures,
        consecutive_successes = v_successes
    WHERE instance_id = p_instance_id;

    UPDATE service_instances
    SET health = v_health
    WHERE instance_id = p_instance_id;

    INSERT INTO health_checks (
        instance_id,
        status,
        response_time_ms,
        failure_reason,
        checker_id
    )
    VALUES (
        p_instance_id,
        p_status,
        p_response_time_ms,
        p_failure_reason,
        p_checker_id
    );

    RETURN v_health;
END;
$$;

-- ============================================================================
-- HEARTBEAT FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION update_heartbeat(
    p_instance_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE service_instances
    SET last_heartbeat = CURRENT_TIMESTAMP
    WHERE instance_id = p_instance_id
      AND registration = 'ACTIVE'
      AND health <> 'DRAINING';

    RETURN FOUND;
END;
$$;

-- ============================================================================
-- DISCOVERY FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION discover_service(
    p_service_name VARCHAR,
    p_version VARCHAR DEFAULT NULL,
    p_region VARCHAR DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS TABLE (
    instance_id UUID,
    service_name VARCHAR,
    version VARCHAR,
    endpoint TEXT,
    region VARCHAR,
    weight INTEGER,
    health instance_health
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        si.instance_id,
        s.service_name,
        sv.version,
        host(si.host) || ':' || si.port::TEXT AS endpoint,
        si.region,
        si.weight,
        si.health
    FROM service_instances si
    JOIN service_versions sv
      ON sv.version_id = si.version_id
    JOIN services s
      ON s.service_id = sv.service_id
    WHERE s.service_name = p_service_name
      AND si.registration = 'ACTIVE'
      AND si.health = 'HEALTHY'
      AND si.last_heartbeat >
          CURRENT_TIMESTAMP -
          make_interval(secs => si.lease_seconds)
      AND (p_version IS NULL OR sv.version = p_version)
      AND (p_region IS NULL OR si.region = p_region)
      AND NOT EXISTS (
          SELECT 1
          FROM jsonb_each_text(
              COALESCE(p_metadata, '{}'::jsonb)
          ) AS required(key, value)
          WHERE NOT EXISTS (
              SELECT 1
              FROM instance_metadata md
              WHERE md.instance_id = si.instance_id
                AND md.metadata_key = required.key
                AND md.metadata_value = required.value
          )
      )
    ORDER BY si.instance_id;
$$;

-- ============================================================================
-- LEASE EXPIRATION
-- ============================================================================

CREATE OR REPLACE FUNCTION expire_instances()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    WITH expired AS (
        UPDATE service_instances
        SET registration = 'DEREGISTERED',
            deregistered_at = CURRENT_TIMESTAMP
        WHERE registration = 'ACTIVE'
          AND last_heartbeat <
              CURRENT_TIMESTAMP -
              make_interval(secs => lease_seconds)
        RETURNING instance_id
    )
    SELECT COUNT(*) INTO v_count
    FROM expired;

    RETURN v_count;
END;
$$;

-- ============================================================================
-- CIRCUIT BREAKER PROCESSING
-- ============================================================================

CREATE OR REPLACE FUNCTION record_request_result(
    p_instance_id UUID,
    p_success BOOLEAN
)
RETURNS circuit_state
LANGUAGE plpgsql
AS $$
DECLARE
    v_breaker circuit_breakers%ROWTYPE;
BEGIN
    SELECT *
    INTO v_breaker
    FROM circuit_breakers
    WHERE instance_id = p_instance_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Circuit breaker not found';
    END IF;

    IF p_success THEN
        UPDATE circuit_breakers
        SET state = 'CLOSED',
            consecutive_failures = 0,
            opened_at = NULL
        WHERE instance_id = p_instance_id;

        RETURN 'CLOSED';
    END IF;

    UPDATE circuit_breakers
    SET consecutive_failures = consecutive_failures + 1,
        state = CASE
            WHEN consecutive_failures + 1 >= failure_threshold
                THEN 'OPEN'::circuit_state
            ELSE state
        END,
        opened_at = CASE
            WHEN consecutive_failures + 1 >= failure_threshold
                THEN CURRENT_TIMESTAMP
            ELSE opened_at
        END
    WHERE instance_id = p_instance_id
    RETURNING state INTO v_breaker.state;

    RETURN v_breaker.state;
END;
$$;

-- ============================================================================
-- DISCOVERY REPORTING VIEW
-- ============================================================================

CREATE OR REPLACE VIEW service_discovery_report AS
SELECT
    s.service_name,
    sv.version,
    sv.environment,
    si.instance_id,
    host(si.host) AS host,
    si.port,
    si.region,
    si.health,
    si.registration,
    si.weight,
    si.last_heartbeat,
    si.lease_seconds,
    (
        si.registration = 'ACTIVE'
        AND si.health = 'HEALTHY'
        AND si.last_heartbeat >
            CURRENT_TIMESTAMP -
            make_interval(secs => si.lease_seconds)
    ) AS currently_discoverable
FROM service_instances si
JOIN service_versions sv
    ON sv.version_id = si.version_id
JOIN services s
    ON s.service_id = sv.service_id;

-- ============================================================================
-- SAMPLE DATA
-- ============================================================================

INSERT INTO service_owners (
    owner_name,
    authorized_for_production
)
VALUES
    ('payments-team', TRUE),
    ('inventory-team', TRUE),
    ('experimental-team', FALSE);

INSERT INTO services (
    service_name,
    description,
    owner_id
)
SELECT
    'payment-service',
    'Payment authorization and transaction processing',
    owner_id
FROM service_owners
WHERE owner_name = 'payments-team';

INSERT INTO services (
    service_name,
    description,
    owner_id
)
SELECT
    'inventory-service',
    'Inventory availability and reservation',
    owner_id
FROM service_owners
WHERE owner_name = 'inventory-team';

INSERT INTO services (
    service_name,
    description,
    owner_id
)
SELECT
    'experimental-service',
    'Development-only experimental service',
    owner_id
FROM service_owners
WHERE owner_name = 'experimental-team';

INSERT INTO service_versions (
    service_id,
    version,
    environment
)
SELECT service_id, '2.1.0', 'PRODUCTION'
FROM services
WHERE service_name = 'payment-service';

INSERT INTO service_versions (
    service_id,
    version,
    environment
)
SELECT service_id, '1.4.0', 'PRODUCTION'
FROM services
WHERE service_name = 'inventory-service';

INSERT INTO service_versions (
    service_id,
    version,
    environment
)
SELECT service_id, '0.9.0', 'DEVELOPMENT'
FROM services
WHERE service_name = 'experimental-service';

INSERT INTO health_policies (
    service_id,
    failure_threshold,
    recovery_threshold,
    check_interval_seconds,
    timeout_ms
)
SELECT service_id, 2, 2, 10, 2000
FROM services;

-- ============================================================================
-- REGISTER INSTANCES
-- ============================================================================

SELECT register_instance(
    '10000000-0000-4000-8000-000000000001',
    'payment-service',
    '2.1.0',
    'PRODUCTION',
    '10.0.1.10',
    8001,
    'ap-south-1',
    'payments-team',
    3,
    60
);

SELECT register_instance(
    '10000000-0000-4000-8000-000000000002',
    'payment-service',
    '2.1.0',
    'PRODUCTION',
    '10.0.1.11',
    8001,
    'ap-south-1',
    'payments-team',
    1,
    60
);

SELECT register_instance(
    '20000000-0000-4000-8000-000000000001',
    'inventory-service',
    '1.4.0',
    'PRODUCTION',
    '10.0.2.10',
    8002,
    'ap-south-1',
    'inventory-team',
    2,
    60
);

-- Development registration is allowed for the unauthorized owner.
SELECT register_instance(
    '30000000-0000-4000-8000-000000000001',
    'experimental-service',
    '0.9.0',
    'DEVELOPMENT',
    '10.0.3.10',
    8003,
    'ap-south-1',
    'experimental-team',
    1,
    60
);

-- Attach instance metadata.
INSERT INTO instance_metadata (
    instance_id,
    metadata_key,
    metadata_value
)
VALUES
    (
        '10000000-0000-4000-8000-000000000001',
        'environment',
        'production'
    ),
    (
        '10000000-0000-4000-8000-000000000001',
        'protocol',
        'http'
    ),
    (
        '10000000-0000-4000-8000-000000000002',
        'environment',
        'production'
    ),
    (
        '10000000-0000-4000-8000-000000000002',
        'protocol',
        'http'
    ),
    (
        '20000000-0000-4000-8000-000000000001',
        'environment',
        'production'
    );

-- ============================================================================
-- HEALTH CHECK EXAMPLES
-- ============================================================================

-- Two successful checks are required for HEALTHY status.
SELECT process_health_check(
    '10000000-0000-4000-8000-000000000001',
    'PASS',
    24,
    'health-worker-01'
);

SELECT process_health_check(
    '10000000-0000-4000-8000-000000000001',
    'PASS',
    21,
    'health-worker-01'
);

SELECT process_health_check(
    '10000000-0000-4000-8000-000000000002',
    'PASS',
    32,
    'health-worker-01'
);

SELECT process_health_check(
    '10000000-0000-4000-8000-000000000002',
    'PASS',
    28,
    'health-worker-01'
);

SELECT process_health_check(
    '20000000-0000-4000-8000-000000000001',
    'PASS',
    18,
    'health-worker-02'
);

SELECT process_health_check(
    '20000000-0000-4000-8000-000000000001',
    'PASS',
    19,
    'health-worker-02'
);

SELECT process_health_check(
    '30000000-0000-4000-8000-000000000001',
    'PASS',
    40,
    'health-worker-03'
);

SELECT process_health_check(
    '30000000-0000-4000-8000-000000000001',
    'PASS',
    38,
    'health-worker-03'
);

-- ============================================================================
-- FAILURE EXAMPLE
-- ============================================================================

SELECT process_health_check(
    '10000000-0000-4000-8000-000000000002',
    'FAIL',
    NULL,
    'health-worker-01',
    'Connection refused'
);

SELECT process_health_check(
    '10000000-0000-4000-8000-000000000002',
    'FAIL',
    NULL,
    'health-worker-01',
    'Connection timeout'
);

-- The second payment instance is now UNHEALTHY.

-- ============================================================================
-- DISCOVERY QUERIES
-- ============================================================================

-- Discover every healthy production payment endpoint.
SELECT *
FROM discover_service(
    'payment-service',
    '2.1.0',
    'ap-south-1',
    '{"environment":"production"}'::jsonb
);

-- Discover inventory endpoints.
SELECT *
FROM discover_service(
    'inventory-service',
    '1.4.0',
    'ap-south-1',
    '{}'::jsonb
);

-- Query service health and registration states.
SELECT *
FROM service_discovery_report
ORDER BY service_name, instance_id;

-- ============================================================================
-- RETRIEVAL AND AGGREGATION
-- ============================================================================

SELECT
    s.service_name,
    sv.environment,
    si.health,
    COUNT(*) AS instance_count
FROM service_instances si
JOIN service_versions sv
    ON sv.version_id = si.version_id
JOIN services s
    ON s.service_id = sv.service_id
GROUP BY
    s.service_name,
    sv.environment,
    si.health
ORDER BY
    s.service_name,
    si.health;

-- Health-check performance report.
SELECT
    instance_id,
    COUNT(*) AS total_checks,
    COUNT(*) FILTER (WHERE status = 'PASS') AS successful_checks,
    COUNT(*) FILTER (WHERE status = 'FAIL') AS failed_checks,
    ROUND(
        AVG(response_time_ms)::NUMERIC,
        2
    ) AS average_latency_ms
FROM health_checks
GROUP BY instance_id
ORDER BY instance_id;

-- ============================================================================
-- CTE-BASED ELIGIBILITY EVALUATION
-- ============================================================================

WITH candidates AS (
    SELECT
        s.service_name,
        si.instance_id,
        si.health,
        si.registration,
        si.region,
        si.last_heartbeat,
        si.lease_seconds,
        sv.version
    FROM service_instances si
    JOIN service_versions sv
        ON sv.version_id = si.version_id
    JOIN services s
        ON s.service_id = sv.service_id
),
evaluated AS (
    SELECT
        *,
        (
            health = 'HEALTHY'
            AND registration = 'ACTIVE'
            AND last_heartbeat >
                CURRENT_TIMESTAMP -
                make_interval(secs => lease_seconds)
        ) AS eligible
    FROM candidates
)
SELECT
    service_name,
    instance_id,
    version,
    region,
    eligible
FROM evaluated
ORDER BY service_name, instance_id;

-- ============================================================================
-- CIRCUIT BREAKER DEMONSTRATION
-- ============================================================================

SELECT record_request_result(
    '10000000-0000-4000-8000-000000000001',
    FALSE
);

SELECT record_request_result(
    '10000000-0000-4000-8000-000000000001',
    FALSE
);

SELECT record_request_result(
    '10000000-0000-4000-8000-000000000001',
    FALSE
);

SELECT
    instance_id,
    state,
    consecutive_failures,
    opened_at
FROM circuit_breakers
ORDER BY instance_id;

-- ============================================================================
-- GRACEFUL DRAINING
-- ============================================================================

UPDATE service_instances
SET health = 'DRAINING'
WHERE instance_id =
    '10000000-0000-4000-8000-000000000001';

-- Draining instances are excluded from discovery.

SELECT *
FROM discover_service(
    'payment-service',
    '2.1.0',
    'ap-south-1',
    '{}'::jsonb
);

-- ============================================================================
-- HEARTBEAT DEMONSTRATION
-- ============================================================================

SELECT update_heartbeat(
    '10000000-0000-4000-8000-000000000002'
);

-- ============================================================================
-- VALIDATION EXAMPLES
-- ============================================================================

-- The following statements are intentionally isolated in exception
-- handling so invalid examples do not abort the main transaction.

DO $$
BEGIN
    BEGIN
        PERFORM register_instance(
            '40000000-0000-4000-8000-000000000001',
            'payment-service',
            '2.1.0',
            'PRODUCTION',
            '10.0.1.20',
            70000,
            'ap-south-1',
            'payments-team'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Invalid port rejected: %', SQLERRM;
    END;

    BEGIN
        PERFORM register_instance(
            '40000000-0000-4000-8000-000000000002',
            'payment-service',
            '2.1.0',
            'PRODUCTION',
            '10.0.1.21',
            8001,
            'ap-south-1',
            'unauthorized-team'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Unknown owner rejected: %', SQLERRM;
    END;

    BEGIN
        PERFORM register_instance(
            '40000000-0000-4000-8000-000000000003',
            'experimental-service',
            '0.9.0',
            'PRODUCTION',
            '10.0.3.20',
            8003,
            'ap-south-1',
            'experimental-team'
        );
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Unauthorized production registration rejected: %',
                SQLERRM;
    END;
END;
$$;

-- ============================================================================
-- AUDIT REPORT
-- ============================================================================

SELECT
    instance_id,
    event_type,
    event_details,
    actor,
    occurred_at
FROM registration_audit
ORDER BY occurred_at, audit_id;

-- ============================================================================
-- LEASE EXPIRATION WORKFLOW
-- ============================================================================

-- Expiration is based on the last heartbeat and configured lease.
-- This operation can be scheduled by an external worker.
SELECT expire_instances();

-- ============================================================================
-- TRANSACTION AND FINAL INTEGRITY CHECK
-- ============================================================================

DO $$
DECLARE
    v_duplicate_count INTEGER;
    v_invalid_health_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_duplicate_count
    FROM (
        SELECT version_id, host, port
        FROM service_instances
        GROUP BY version_id, host, port
        HAVING COUNT(*) > 1
    ) duplicates;

    SELECT COUNT(*)
    INTO v_invalid_health_count
    FROM service_instances
    WHERE health IS NULL
       OR registration IS NULL;

    IF v_duplicate_count <> 0 THEN
        RAISE EXCEPTION 'Duplicate service endpoints detected';
    END IF;

    IF v_invalid_health_count <> 0 THEN
        RAISE EXCEPTION 'Invalid instance state detected';
    END IF;
END;
$$;

COMMIT;

-- ============================================================================
-- OPERATIONAL NOTES
-- ============================================================================
--
-- 1. Registration is transactional and checks service ownership.
-- 2. Health checks are recorded independently from registration.
-- 3. A successful registration does not imply a healthy instance.
-- 4. A healthy instance must also possess a valid lease.
-- 5. Draining prevents new discovery without immediately terminating
--    existing connections.
-- 6. Circuit breakers provide request-failure isolation.
-- 7. Discovery uses service/version indexes and metadata filtering.
-- 8. Health workers must perform actual network probes outside this schema.
-- 9. Production deployments should use role-based SQL permissions,
--    TLS, restricted network access and retention policies.
-- 10. For large registries, partition health_checks by time and archive
--     old records. Use a distributed coordination mechanism when multiple
--     registry writers need strongly coordinated ownership.
--
-- ============================================================================
