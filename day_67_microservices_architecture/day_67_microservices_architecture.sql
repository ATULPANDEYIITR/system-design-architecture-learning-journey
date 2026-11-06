-- ============================================================
-- MICROSERVICES ARCHITECTURE
-- Service boundaries, dependency management and deployment
-- PostgreSQL 15+
-- ============================================================

DROP SCHEMA IF EXISTS microservices CASCADE;

CREATE SCHEMA microservices;

SET search_path TO microservices, public;

-- ============================================================
-- 1. DOMAIN TYPES
-- ============================================================

CREATE TYPE service_status AS ENUM (
    'registered',
    'deploying',
    'healthy',
    'degraded',
    'unavailable'
);

CREATE TYPE dependency_type AS ENUM (
    'synchronous',
    'asynchronous'
);

CREATE TYPE deployment_status AS ENUM (
    'pending',
    'successful',
    'failed',
    'rolled_back'
);

CREATE TYPE event_status AS ENUM (
    'pending',
    'processing',
    'published',
    'failed'
);

-- ============================================================
-- 2. SERVICE REGISTRY
-- ============================================================

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_name VARCHAR(50) NOT NULL UNIQUE,

    description TEXT NOT NULL,

    business_capability VARCHAR(100) NOT NULL,

    owner_team VARCHAR(100) NOT NULL,

    current_version VARCHAR(30) NOT NULL,

    api_version INTEGER NOT NULL DEFAULT 1,

    status service_status NOT NULL DEFAULT 'registered',

    instance_count INTEGER NOT NULL DEFAULT 1,

    deployment_count INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_service_name CHECK (
        service_name ~ '^[a-z][a-z0-9-]{1,48}$'
    ),

    CONSTRAINT valid_semantic_version CHECK (
        current_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),

    CONSTRAINT positive_api_version CHECK (
        api_version >= 1
    ),

    CONSTRAINT positive_instances CHECK (
        instance_count >= 1
    ),

    CONSTRAINT nonnegative_deployments CHECK (
        deployment_count >= 0
    ),

    CONSTRAINT valid_description CHECK (
        LENGTH(TRIM(description)) > 0
    )
);

CREATE TABLE service_contracts (
    contract_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL REFERENCES services(service_id),

    version VARCHAR(30) NOT NULL,

    api_version INTEGER NOT NULL,

    backward_compatible BOOLEAN NOT NULL DEFAULT TRUE,

    contract_document JSONB NOT NULL DEFAULT '{}'::JSONB,

    is_active BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(service_id, version),

    CONSTRAINT valid_contract_version CHECK (
        version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),

    CONSTRAINT valid_contract_api CHECK (
        api_version >= 1
    )
);

CREATE UNIQUE INDEX one_active_contract_per_service
ON service_contracts(service_id)
WHERE is_active = TRUE;

CREATE TABLE service_endpoints (
    endpoint_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    contract_id BIGINT NOT NULL
        REFERENCES service_contracts(contract_id) ON DELETE CASCADE,

    endpoint_path VARCHAR(300) NOT NULL,

    http_method VARCHAR(10) NOT NULL,

    description TEXT NOT NULL DEFAULT '',

    UNIQUE(contract_id, endpoint_path, http_method),

    CONSTRAINT valid_http_method CHECK (
        http_method IN (
            'GET', 'POST', 'PUT', 'PATCH', 'DELETE'
        )
    ),

    CONSTRAINT valid_endpoint_path CHECK (
        endpoint_path LIKE '/%'
    )
);

-- ============================================================
-- 3. SERVICE DEPENDENCY GRAPH
-- ============================================================

CREATE TABLE service_dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    consumer_service_id BIGINT NOT NULL
        REFERENCES services(service_id) ON DELETE RESTRICT,

    provider_service_id BIGINT NOT NULL
        REFERENCES services(service_id) ON DELETE RESTRICT,

    communication dependency_type NOT NULL,

    required BOOLEAN NOT NULL DEFAULT TRUE,

    expected_api_version INTEGER NOT NULL DEFAULT 1,

    timeout_ms INTEGER NOT NULL DEFAULT 3000,

    description TEXT NOT NULL DEFAULT '',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(consumer_service_id, provider_service_id),

    CONSTRAINT no_self_dependency CHECK (
        consumer_service_id <> provider_service_id
    ),

    CONSTRAINT valid_timeout CHECK (
        timeout_ms > 0
    ),

    CONSTRAINT valid_expected_api CHECK (
        expected_api_version >= 1
    )
);

CREATE INDEX idx_dependencies_provider
ON service_dependencies(provider_service_id);

CREATE INDEX idx_dependencies_consumer
ON service_dependencies(consumer_service_id);

-- ============================================================
-- 4. DEPLOYMENT ENVIRONMENTS AND ARTIFACTS
-- ============================================================

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    environment_name VARCHAR(30) NOT NULL UNIQUE,

    is_production BOOLEAN NOT NULL DEFAULT FALSE,

    deployment_approval_required BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE deployment_artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL REFERENCES services(service_id),

    version VARCHAR(30) NOT NULL,

    image_repository VARCHAR(300) NOT NULL,

    image_digest VARCHAR(100) NOT NULL,

    source_commit VARCHAR(100) NOT NULL,

    contract_id BIGINT REFERENCES service_contracts(contract_id),

    build_status VARCHAR(20) NOT NULL DEFAULT 'built',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(service_id, version),

    CONSTRAINT valid_build_status CHECK (
        build_status IN ('built', 'verified', 'rejected')
    ),

    CONSTRAINT valid_image_digest CHECK (
        LENGTH(TRIM(image_digest)) > 0
    )
);

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL REFERENCES services(service_id),

    artifact_id BIGINT NOT NULL
        REFERENCES deployment_artifacts(artifact_id),

    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),

    previous_version VARCHAR(30),

    target_version VARCHAR(30) NOT NULL,

    status deployment_status NOT NULL DEFAULT 'pending',

    initiated_by VARCHAR(100) NOT NULL,

    health_check_passed BOOLEAN,

    error_message TEXT,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    CONSTRAINT valid_deployment_duration CHECK (
        completed_at IS NULL OR completed_at >= started_at
    )
);

CREATE INDEX idx_deployments_service_time
ON deployments(service_id, started_at DESC);

CREATE INDEX idx_deployments_status
ON deployments(status, environment_id);

-- ============================================================
-- 5. HEALTH CHECKS AND SERVICE INSTANCES
-- ============================================================

CREATE TABLE service_instances (
    instance_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL REFERENCES services(service_id),

    instance_identifier VARCHAR(150) NOT NULL UNIQUE,

    host_name VARCHAR(200) NOT NULL,

    port INTEGER NOT NULL,

    status service_status NOT NULL DEFAULT 'registered',

    version VARCHAR(30) NOT NULL,

    last_heartbeat TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_port CHECK (
        port BETWEEN 1 AND 65535
    )
);

CREATE TABLE health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    instance_id BIGINT NOT NULL
        REFERENCES service_instances(instance_id) ON DELETE CASCADE,

    check_type VARCHAR(30) NOT NULL,

    is_healthy BOOLEAN NOT NULL,

    response_time_ms INTEGER NOT NULL,

    details JSONB NOT NULL DEFAULT '{}'::JSONB,

    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_response_time CHECK (
        response_time_ms >= 0
    )
);

CREATE INDEX idx_health_instance_time
ON health_checks(instance_id, checked_at DESC);

-- ============================================================
-- 6. EVENT-DRIVEN COMMUNICATION AND OUTBOX
-- ============================================================

CREATE TABLE event_outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_service_id BIGINT NOT NULL REFERENCES services(service_id),

    event_type VARCHAR(120) NOT NULL,

    aggregate_id VARCHAR(100) NOT NULL,

    payload JSONB NOT NULL,

    status event_status NOT NULL DEFAULT 'pending',

    retry_count INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    published_at TIMESTAMPTZ,

    CONSTRAINT valid_retry_count CHECK (
        retry_count >= 0
    )
);

CREATE INDEX idx_outbox_pending
ON event_outbox(created_at)
WHERE status = 'pending';

CREATE TABLE event_consumers (
    consumer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_id UUID NOT NULL REFERENCES event_outbox(event_id),

    consumer_service_id BIGINT NOT NULL REFERENCES services(service_id),

    status event_status NOT NULL DEFAULT 'pending',

    retry_count INTEGER NOT NULL DEFAULT 0,

    processed_at TIMESTAMPTZ,

    error_message TEXT,

    UNIQUE(event_id, consumer_service_id)
);

CREATE INDEX idx_event_consumer_pending
ON event_consumers(consumer_service_id, status);

-- ============================================================
-- 7. SERVICE REGISTRATION AND VALIDATION
-- ============================================================

CREATE FUNCTION register_service(
    p_name VARCHAR,
    p_description TEXT,
    p_capability VARCHAR,
    p_owner VARCHAR,
    p_version VARCHAR,
    p_api_version INTEGER
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_service_id BIGINT;
BEGIN
    IF p_name !~ '^[a-z][a-z0-9-]{1,48}$' THEN
        RAISE EXCEPTION 'Invalid service name: %', p_name;
    END IF;

    IF p_version !~ '^[0-9]+\.[0-9]+\.[0-9]+$' THEN
        RAISE EXCEPTION 'Invalid semantic version: %', p_version;
    END IF;

    IF p_api_version < 1 THEN
        RAISE EXCEPTION 'API version must be positive';
    END IF;

    IF LENGTH(TRIM(p_description)) = 0 THEN
        RAISE EXCEPTION 'Service description is required';
    END IF;

    INSERT INTO services (
        service_name,
        description,
        business_capability,
        owner_team,
        current_version,
        api_version
    )
    VALUES (
        p_name,
        p_description,
        p_capability,
        p_owner,
        p_version,
        p_api_version
    )
    RETURNING service_id INTO v_service_id;

    RETURN v_service_id;
END;
$$;

-- Prevent circular dependencies when registering dependency edges.
CREATE FUNCTION prevent_dependency_cycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_cycle BOOLEAN;
BEGIN
    IF NEW.consumer_service_id = NEW.provider_service_id THEN
        RAISE EXCEPTION 'Self-dependency is prohibited';
    END IF;

    WITH RECURSIVE reachable(service_id) AS (
        SELECT NEW.provider_service_id

        UNION

        SELECT d.provider_service_id
        FROM service_dependencies d
        JOIN reachable r
          ON d.consumer_service_id = r.service_id
    )
    SELECT EXISTS (
        SELECT 1
        FROM reachable
        WHERE service_id = NEW.consumer_service_id
    )
    INTO v_cycle;

    IF v_cycle THEN
        RAISE EXCEPTION
            'Dependency would create a circular service graph';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_dependency_cycle
BEFORE INSERT OR UPDATE ON service_dependencies
FOR EACH ROW
EXECUTE FUNCTION prevent_dependency_cycle();

-- ============================================================
-- 8. DEPLOYMENT CONTRACT VALIDATION
-- ============================================================

CREATE FUNCTION validate_deployment(
    p_service_id BIGINT,
    p_artifact_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_artifact deployment_artifacts%ROWTYPE;
    v_service services%ROWTYPE;
    v_old_api INTEGER;
    v_new_api INTEGER;
    v_old_version VARCHAR(30);
    v_new_version VARCHAR(30);
    v_removed_count INTEGER;
BEGIN
    SELECT * INTO v_service
    FROM services
    WHERE service_id = p_service_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Service does not exist';
    END IF;

    SELECT * INTO v_artifact
    FROM deployment_artifacts
    WHERE artifact_id = p_artifact_id
      AND service_id = p_service_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Artifact does not belong to service';
    END IF;

    IF v_artifact.build_status <> 'verified' THEN
        RAISE EXCEPTION 'Artifact must be verified before deployment';
    END IF;

    IF v_artifact.contract_id IS NULL THEN
        RAISE EXCEPTION 'Artifact has no associated service contract';
    END IF;

    SELECT api_version
    INTO v_new_api
    FROM service_contracts
    WHERE contract_id = v_artifact.contract_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'New service contract does not exist';
    END IF;

    v_old_api := v_service.api_version;
    v_old_version := v_service.current_version;
    v_new_version := v_artifact.version;

    IF v_new_version !~ '^[0-9]+\.[0-9]+\.[0-9]+$' THEN
        RAISE EXCEPTION 'Invalid deployment version';
    END IF;

    IF v_new_api < v_old_api THEN
        RAISE EXCEPTION 'API version downgrade is prohibited';
    END IF;

    SELECT COUNT(*)
    INTO v_removed_count
    FROM service_endpoints old_endpoint
    JOIN service_contracts old_contract
      ON old_contract.contract_id = old_endpoint.contract_id
    WHERE old_contract.service_id = p_service_id
      AND old_contract.is_active = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM service_endpoints new_endpoint
          WHERE new_endpoint.contract_id = v_artifact.contract_id
            AND new_endpoint.endpoint_path =
                old_endpoint.endpoint_path
            AND new_endpoint.http_method =
                old_endpoint.http_method
      );

    IF v_removed_count > 0 AND v_new_api <= v_old_api THEN
        RAISE EXCEPTION
            'Breaking contract requires an API version increase';
    END IF;

    RETURN TRUE;
END;
$$;

-- ============================================================
-- 9. ATOMIC DEPLOYMENT WORKFLOW
-- ============================================================

CREATE PROCEDURE deploy_service(
    p_service_id BIGINT,
    p_artifact_id BIGINT,
    p_environment_id BIGINT,
    p_actor VARCHAR,
    p_health_check_passed BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_service services%ROWTYPE;
    v_artifact deployment_artifacts%ROWTYPE;
    v_previous_version VARCHAR(30);
    v_deployment_id BIGINT;
BEGIN
    SELECT * INTO v_service
    FROM services
    WHERE service_id = p_service_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown service';
    END IF;

    SELECT * INTO v_artifact
    FROM deployment_artifacts
    WHERE artifact_id = p_artifact_id
      AND service_id = p_service_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid deployment artifact';
    END IF;

    PERFORM validate_deployment(
        p_service_id,
        p_artifact_id
    );

    IF NOT EXISTS (
        SELECT 1
        FROM environments
        WHERE environment_id = p_environment_id
    ) THEN
        RAISE EXCEPTION 'Unknown environment';
    END IF;

    v_previous_version := v_service.current_version;

    UPDATE services
    SET status = 'deploying',
        updated_at = NOW()
    WHERE service_id = p_service_id;

    INSERT INTO deployments (
        service_id,
        artifact_id,
        environment_id,
        previous_version,
        target_version,
        status,
        initiated_by
    )
    VALUES (
        p_service_id,
        p_artifact_id,
        p_environment_id,
        v_previous_version,
        v_artifact.version,
        'pending',
        p_actor
    )
    RETURNING deployment_id INTO v_deployment_id;

    IF p_health_check_passed THEN

        UPDATE service_contracts
        SET is_active = FALSE
        WHERE service_id = p_service_id
          AND is_active = TRUE;

        UPDATE service_contracts
        SET is_active = TRUE
        WHERE contract_id = v_artifact.contract_id;

        UPDATE services
        SET current_version = v_artifact.version,
            api_version = (
                SELECT api_version
                FROM service_contracts
                WHERE contract_id = v_artifact.contract_id
            ),
            status = 'healthy',
            deployment_count = deployment_count + 1,
            updated_at = NOW()
        WHERE service_id = p_service_id;

        UPDATE deployments
        SET status = 'successful',
            health_check_passed = TRUE,
            completed_at = NOW()
        WHERE deployment_id = v_deployment_id;

    ELSE

        UPDATE services
        SET status = 'healthy',
            updated_at = NOW()
        WHERE service_id = p_service_id;

        UPDATE deployments
        SET status = 'rolled_back',
            health_check_passed = FALSE,
            error_message = 'Post-deployment health check failed',
            completed_at = NOW()
        WHERE deployment_id = v_deployment_id;

    END IF;

END;
$$;

-- ============================================================
-- 10. EVENT OUTBOX PROCESSING
-- ============================================================

CREATE FUNCTION create_service_event(
    p_service_name VARCHAR,
    p_event_type VARCHAR,
    p_aggregate_id VARCHAR,
    p_payload JSONB
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_service_id BIGINT;
    v_event_id UUID;
BEGIN
    SELECT service_id
    INTO v_service_id
    FROM services
    WHERE service_name = p_service_name;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown event source service';
    END IF;

    INSERT INTO event_outbox (
        source_service_id,
        event_type,
        aggregate_id,
        payload
    )
    VALUES (
        v_service_id,
        p_event_type,
        p_aggregate_id,
        p_payload
    )
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;
END;
$$;

-- Insert delivery records for dependent services.
CREATE PROCEDURE enqueue_event_consumers()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO event_consumers (
        event_id,
        consumer_service_id
    )
    SELECT
        e.event_id,
        d.consumer_service_id
    FROM event_outbox e
    JOIN service_dependencies d
      ON d.provider_service_id = e.source_service_id
    WHERE d.communication = 'asynchronous'
      AND NOT EXISTS (
          SELECT 1
          FROM event_consumers ec
          WHERE ec.event_id = e.event_id
            AND ec.consumer_service_id = d.consumer_service_id
      )
    ON CONFLICT (event_id, consumer_service_id) DO NOTHING;
END;
$$;

-- ============================================================
-- 11. VIEWS
-- ============================================================

CREATE VIEW service_inventory AS
SELECT
    s.service_id,
    s.service_name,
    s.business_capability,
    s.owner_team,
    s.current_version,
    s.api_version,
    s.status,
    s.instance_count,
    s.deployment_count,
    COUNT(DISTINCT d.dependency_id) AS dependency_count
FROM services s
LEFT JOIN service_dependencies d
    ON d.consumer_service_id = s.service_id
GROUP BY s.service_id;

CREATE VIEW service_dependency_report AS
SELECT
    consumer.service_name AS consumer,
    provider.service_name AS provider,
    d.communication,
    d.required,
    d.expected_api_version,
    d.timeout_ms
FROM service_dependencies d
JOIN services consumer
    ON consumer.service_id = d.consumer_service_id
JOIN services provider
    ON provider.service_id = d.provider_service_id;

CREATE VIEW deployment_report AS
SELECT
    s.service_name,
    e.environment_name,
    d.previous_version,
    d.target_version,
    d.status,
    d.health_check_passed,
    d.initiated_by,
    d.started_at,
    d.completed_at,
    d.error_message
FROM deployments d
JOIN services s
    ON s.service_id = d.service_id
JOIN environments e
    ON e.environment_id = d.environment_id;

CREATE VIEW service_health_report AS
SELECT
    s.service_name,
    COUNT(h.health_check_id) AS total_checks,
    COUNT(h.health_check_id) FILTER (
        WHERE h.is_healthy
    ) AS successful_checks,
    ROUND(
        AVG(h.response_time_ms)::NUMERIC,
        2
    ) AS average_response_ms
FROM services s
LEFT JOIN service_instances i
    ON i.service_id = s.service_id
LEFT JOIN health_checks h
    ON h.instance_id = i.instance_id
GROUP BY s.service_id;

-- ============================================================
-- 12. SAMPLE DATA
-- ============================================================

INSERT INTO environments (
    environment_name,
    is_production,
    deployment_approval_required
)
VALUES
    ('development', FALSE, FALSE),
    ('staging', FALSE, FALSE),
    ('production', TRUE, TRUE);

INSERT INTO services (
    service_name,
    description,
    business_capability,
    owner_team,
    current_version,
    api_version,
    status,
    instance_count
)
VALUES
(
    'payment-service',
    'Processes customer payments.',
    'Payment Processing',
    'Payments Team',
    '1.0.0',
    1,
    'healthy',
    3
),
(
    'inventory-service',
    'Manages stock and reservations.',
    'Inventory Management',
    'Supply Team',
    '1.0.0',
    1,
    'healthy',
    2
),
(
    'order-service',
    'Coordinates customer orders.',
    'Order Management',
    'Commerce Team',
    '1.0.0',
    1,
    'healthy',
    3
),
(
    'notification-service',
    'Sends customer notifications.',
    'Customer Communication',
    'Platform Team',
    '1.0.0',
    1,
    'healthy',
    2
);

INSERT INTO service_contracts (
    service_id,
    version,
    api_version,
    backward_compatible,
    contract_document,
    is_active
)
SELECT
    service_id,
    '1.0.0',
    1,
    TRUE,
    '{"format":"REST","authentication":"JWT"}'::JSONB,
    TRUE
FROM services;

INSERT INTO service_endpoints (
    contract_id,
    endpoint_path,
    http_method,
    description
)
SELECT
    contract_id,
    '/health',
    'GET',
    'Service health endpoint'
FROM service_contracts;

INSERT INTO service_endpoints (
    contract_id,
    endpoint_path,
    http_method,
    description
)
SELECT
    contract_id,
    '/api',
    'GET',
    'Primary service API'
FROM service_contracts;

INSERT INTO service_dependencies (
    consumer_service_id,
    provider_service_id,
    communication,
    required,
    expected_api_version,
    timeout_ms,
    description
)
SELECT
    consumer.service_id,
    provider.service_id,
    'synchronous',
    TRUE,
    1,
    3000,
    'Order service requires payment processing'
FROM services consumer
CROSS JOIN services provider
WHERE consumer.service_name = 'order-service'
  AND provider.service_name = 'payment-service';

INSERT INTO service_dependencies (
    consumer_service_id,
    provider_service_id,
    communication,
    required,
    expected_api_version,
    timeout_ms,
    description
)
SELECT
    consumer.service_id,
    provider.service_id,
    'asynchronous',
    TRUE,
    1,
    5000,
    'Order service receives inventory events'
FROM services consumer
CROSS JOIN services provider
WHERE consumer.service_name = 'order-service'
  AND provider.service_name = 'inventory-service';

INSERT INTO service_dependencies (
    consumer_service_id,
    provider_service_id,
    communication,
    required,
    expected_api_version,
    timeout_ms,
    description
)
SELECT
    consumer.service_id,
    provider.service_id,
    'asynchronous',
    FALSE,
    1,
    5000,
    'Notification service consumes order events'
FROM services consumer
CROSS JOIN services provider
WHERE consumer.service_name = 'notification-service'
  AND provider.service_name = 'order-service';

-- ============================================================
-- 13. SERVICE INSTANCES AND HEALTH DATA
-- ============================================================

INSERT INTO service_instances (
    service_id,
    instance_identifier,
    host_name,
    port,
    status,
    version,
    last_heartbeat
)
SELECT
    service_id,
    service_name || '-instance-1',
    service_name || '.internal',
    8080,
    'healthy',
    current_version,
    NOW()
FROM services;

INSERT INTO health_checks (
    instance_id,
    check_type,
    is_healthy,
    response_time_ms,
    details
)
SELECT
    instance_id,
    'readiness',
    TRUE,
    45,
    '{"database":"connected","cache":"available"}'::JSONB
FROM service_instances;

-- ============================================================
-- 14. DEPLOYMENT ARTIFACTS
-- ============================================================

INSERT INTO service_contracts (
    service_id,
    version,
    api_version,
    backward_compatible,
    contract_document,
    is_active
)
SELECT
    service_id,
    '1.1.0',
    1,
    TRUE,
    '{"format":"REST","authentication":"JWT","change":"new endpoint"}'::JSONB,
    FALSE
FROM services
WHERE service_name = 'payment-service';

INSERT INTO service_endpoints (
    contract_id,
    endpoint_path,
    http_method,
    description
)
SELECT
    contract_id,
    '/api/payment-status',
    'GET',
    'Retrieves payment status'
FROM service_contracts
WHERE version = '1.1.0'
AND service_id = (
    SELECT service_id
    FROM services
    WHERE service_name = 'payment-service'
);

INSERT INTO deployment_artifacts (
    service_id,
    version,
    image_repository,
    image_digest,
    source_commit,
    contract_id,
    build_status
)
SELECT
    s.service_id,
    '1.1.0',
    'registry.internal/payment-service',
    'sha256:abcdef1234567890',
    'commit-payment-110',
    c.contract_id,
    'verified'
FROM services s
JOIN service_contracts c
    ON c.service_id = s.service_id
WHERE s.service_name = 'payment-service'
  AND c.version = '1.1.0';

-- ============================================================
-- 15. TRANSACTIONAL DEPLOYMENT
-- ============================================================

BEGIN;

CALL deploy_service(
    (
        SELECT service_id
        FROM services
        WHERE service_name = 'payment-service'
    ),
    (
        SELECT artifact_id
        FROM deployment_artifacts
        WHERE version = '1.1.0'
          AND service_id = (
              SELECT service_id
              FROM services
              WHERE service_name = 'payment-service'
          )
    ),
    (
        SELECT environment_id
        FROM environments
        WHERE environment_name = 'staging'
    ),
    'release-engine',
    TRUE
);

COMMIT;

-- ============================================================
-- 16. FAILED DEPLOYMENT EXAMPLE
-- ============================================================

INSERT INTO deployment_artifacts (
    service_id,
    version,
    image_repository,
    image_digest,
    source_commit,
    contract_id,
    build_status
)
SELECT
    s.service_id,
    '1.2.0',
    'registry.internal/payment-service',
    'sha256:failedartifact123',
    'commit-payment-120',
    c.contract_id,
    'verified'
FROM services s
JOIN service_contracts c
    ON c.service_id = s.service_id
WHERE s.service_name = 'payment-service'
  AND c.version = '1.1.0'
ON CONFLICT (service_id, version) DO NOTHING;

-- This transaction records a failed deployment without changing
-- the currently active service version.

BEGIN;

CALL deploy_service(
    (
        SELECT service_id
        FROM services
        WHERE service_name = 'payment-service'
    ),
    (
        SELECT artifact_id
        FROM deployment_artifacts
        WHERE version = '1.2.0'
          AND service_id = (
              SELECT service_id
              FROM services
              WHERE service_name = 'payment-service'
          )
    ),
    (
        SELECT environment_id
        FROM environments
        WHERE environment_name = 'staging'
    ),
    'release-engine',
    FALSE
);

COMMIT;

-- ============================================================
-- 17. EVENT PUBLICATION AND CONSUMER ENQUEUEING
-- ============================================================

SELECT create_service_event(
    'order-service',
    'order.created',
    'ORD-5001',
    '{
        "order_id":"ORD-5001",
        "customer_id":"CUST-100",
        "total":2500,
        "currency":"INR"
    }'::JSONB
);

CALL enqueue_event_consumers();

-- ============================================================
-- 18. RETRIEVAL AND VALIDATION QUERIES
-- ============================================================

-- Current service inventory.
SELECT *
FROM service_inventory
ORDER BY service_name;

-- Direct dependencies and communication methods.
SELECT *
FROM service_dependency_report
ORDER BY consumer, provider;

-- Find consumers of payment-service.
SELECT consumer
FROM service_dependency_report
WHERE provider = 'payment-service';

-- Detect missing or outdated API requirements.
SELECT
    consumer.service_name AS consumer,
    provider.service_name AS provider,
    d.expected_api_version,
    provider.api_version AS current_api_version
FROM service_dependencies d
JOIN services consumer
    ON consumer.service_id = d.consumer_service_id
JOIN services provider
    ON provider.service_id = d.provider_service_id
WHERE d.expected_api_version <> provider.api_version;

-- ============================================================
-- 19. AGGREGATION AND REPORTING
-- ============================================================

SELECT
    status,
    COUNT(*) AS service_count,
    SUM(instance_count) AS total_instances,
    SUM(deployment_count) AS total_deployments
FROM services
GROUP BY status
ORDER BY status;

SELECT
    service_name,
    COUNT(*) AS deployments,
    COUNT(*) FILTER (
        WHERE status = 'successful'
    ) AS successful,
    COUNT(*) FILTER (
        WHERE status = 'failed'
    ) AS failed,
    COUNT(*) FILTER (
        WHERE status = 'rolled_back'
    ) AS rolled_back
FROM deployment_report
GROUP BY service_name
ORDER BY service_name;

SELECT *
FROM service_health_report
ORDER BY service_name;

SELECT *
FROM deployment_report
ORDER BY started_at DESC;

-- ============================================================
-- 20. RECURSIVE DEPENDENCY ANALYSIS
-- ============================================================

WITH RECURSIVE dependency_tree AS (
    SELECT
        s.service_id,
        s.service_name,
        0 AS depth,
        ARRAY[s.service_id] AS visited
    FROM services s
    WHERE s.service_name = 'order-service'

    UNION ALL

    SELECT
        provider.service_id,
        provider.service_name,
        tree.depth + 1,
        tree.visited || provider.service_id
    FROM dependency_tree tree
    JOIN service_dependencies d
        ON d.consumer_service_id = tree.service_id
    JOIN services provider
        ON provider.service_id = d.provider_service_id
    WHERE NOT provider.service_id = ANY(tree.visited)
)
SELECT
    service_name,
    depth
FROM dependency_tree
ORDER BY depth, service_name;

-- ============================================================
-- 21. DEPLOYMENT ELIGIBILITY REPORT
-- ============================================================

SELECT
    s.service_name,
    a.version AS candidate_version,
    a.build_status,
    CASE
        WHEN a.build_status <> 'verified'
            THEN 'INELIGIBLE: Artifact not verified'

        WHEN c.api_version < s.api_version
            THEN 'INELIGIBLE: API downgrade'

        WHEN c.contract_id IS NULL
            THEN 'INELIGIBLE: Missing contract'

        ELSE 'ELIGIBLE FOR CONTRACT AND BUILD VALIDATION'
    END AS eligibility
FROM deployment_artifacts a
JOIN services s
    ON s.service_id = a.service_id
LEFT JOIN service_contracts c
    ON c.contract_id = a.contract_id
ORDER BY s.service_name, a.version;

-- ============================================================
-- 22. EVENT DELIVERY REPORT
-- ============================================================

SELECT
    e.event_type,
    e.aggregate_id,
    e.status AS publication_status,
    consumer.service_name,
    ec.status AS delivery_status,
    ec.retry_count
FROM event_outbox e
LEFT JOIN event_consumers ec
    ON ec.event_id = e.event_id
LEFT JOIN services consumer
    ON consumer.service_id = ec.consumer_service_id
ORDER BY e.created_at DESC;

-- ============================================================
-- 23. PERFORMANCE AND OPERATIONAL QUERIES
-- ============================================================

-- Pending events available for asynchronous processing.
SELECT event_id, event_type, payload, created_at
FROM event_outbox
WHERE status = 'pending'
ORDER BY created_at
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Services with stale instance heartbeats.
SELECT
    s.service_name,
    i.instance_identifier,
    i.last_heartbeat
FROM service_instances i
JOIN services s
    ON s.service_id = i.service_id
WHERE i.last_heartbeat IS NULL
   OR i.last_heartbeat < NOW() - INTERVAL '2 minutes';

-- Production deployment history.
SELECT *
FROM deployment_report
WHERE environment_name = 'production'
ORDER BY started_at DESC;

-- ============================================================
-- END OF MICROSERVICES ARCHITECTURE DATABASE
-- ============================================================
