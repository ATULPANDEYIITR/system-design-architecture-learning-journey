/*
===============================================================================
API GATEWAY DATABASE
Routing | Authentication | Rate Limiting | Audit | Upstream Health

PostgreSQL 14+

Models:
1. API clients and credentials
2. Authentication scopes and permissions
3. Upstream services
4. API route definitions
5. Route authorization policies
6. Token-bucket rate-limit policies
7. Gateway requests and responses
8. Rate-limit consumption
9. Circuit-breaker state
10. Gateway reporting and eligibility evaluation

The script is designed to run in a dedicated database schema.
===============================================================================
*/

BEGIN;

DROP SCHEMA IF EXISTS api_gateway CASCADE;

CREATE SCHEMA api_gateway;

SET search_path TO api_gateway, public;

-- ============================================================================
-- 1. ENUM TYPES
-- ============================================================================

CREATE TYPE client_status AS ENUM (
    'ACTIVE',
    'DISABLED',
    'SUSPENDED'
);

CREATE TYPE route_status AS ENUM (
    'ACTIVE',
    'INACTIVE',
    'MAINTENANCE'
);

CREATE TYPE gateway_request_status AS ENUM (
    'RECEIVED',
    'AUTHENTICATED',
    'AUTHORIZED',
    'RATE_LIMITED',
    'FORWARDED',
    'COMPLETED',
    'FAILED'
);

CREATE TYPE circuit_state AS ENUM (
    'CLOSED',
    'OPEN',
    'HALF_OPEN'
);

CREATE TYPE upstream_health AS ENUM (
    'HEALTHY',
    'DEGRADED',
    'UNAVAILABLE'
);

-- ============================================================================
-- 2. API CLIENTS
-- ============================================================================

CREATE TABLE api_clients (
    client_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    client_code VARCHAR(60) NOT NULL UNIQUE,

    client_name VARCHAR(150) NOT NULL,

    status client_status NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Store only a cryptographic hash of API credentials.
-- Plaintext API secrets must never be persisted.

CREATE TABLE api_credentials (
    credential_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    client_id BIGINT NOT NULL
        REFERENCES api_clients(client_id),

    token_hash CHAR(64) NOT NULL UNIQUE,

    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    expires_at TIMESTAMPTZ,

    revoked_at TIMESTAMPTZ,

    CONSTRAINT valid_expiration
        CHECK (
            expires_at IS NULL OR expires_at > issued_at
        )
);

CREATE INDEX idx_credentials_client
    ON api_credentials(client_id);

CREATE INDEX idx_credentials_expiration
    ON api_credentials(expires_at)
    WHERE revoked_at IS NULL;

-- ============================================================================
-- 3. AUTHORIZATION SCOPES
-- ============================================================================

CREATE TABLE api_scopes (
    scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    scope_name VARCHAR(100) NOT NULL UNIQUE,

    description TEXT NOT NULL
);

CREATE TABLE client_scopes (
    client_id BIGINT NOT NULL
        REFERENCES api_clients(client_id)
        ON DELETE CASCADE,

    scope_id BIGINT NOT NULL
        REFERENCES api_scopes(scope_id)
        ON DELETE CASCADE,

    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (client_id, scope_id)
);

CREATE INDEX idx_client_scopes_scope
    ON client_scopes(scope_id);

-- ============================================================================
-- 4. UPSTREAM SERVICES
-- ============================================================================

CREATE TABLE upstream_services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_name VARCHAR(100) NOT NULL UNIQUE,

    base_url TEXT NOT NULL,

    health upstream_health NOT NULL DEFAULT 'HEALTHY',

    connection_timeout_ms INTEGER NOT NULL DEFAULT 2000,

    response_timeout_ms INTEGER NOT NULL DEFAULT 5000,

    circuit_status circuit_state NOT NULL DEFAULT 'CLOSED',

    consecutive_failures INTEGER NOT NULL DEFAULT 0,

    circuit_opened_at TIMESTAMPTZ,

    last_health_check TIMESTAMPTZ,

    CONSTRAINT valid_timeouts
        CHECK (
            connection_timeout_ms > 0
            AND response_timeout_ms > 0
        ),

    CONSTRAINT valid_failure_count
        CHECK (consecutive_failures >= 0)
);

-- ============================================================================
-- 5. ROUTES
-- ============================================================================

CREATE TABLE api_routes (
    route_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    route_code VARCHAR(100) NOT NULL UNIQUE,

    route_name VARCHAR(150) NOT NULL,

    http_method VARCHAR(10) NOT NULL,

    path_pattern VARCHAR(500) NOT NULL,

    service_id BIGINT NOT NULL
        REFERENCES upstream_services(service_id),

    required_scope_id BIGINT NOT NULL
        REFERENCES api_scopes(scope_id),

    status route_status NOT NULL DEFAULT 'ACTIVE',

    priority INTEGER NOT NULL DEFAULT 100,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_http_method
        CHECK (
            http_method IN (
                'GET',
                'POST',
                'PUT',
                'PATCH',
                'DELETE'
            )
        ),

    CONSTRAINT valid_route_path
        CHECK (
            path_pattern LIKE '/%'
            AND LENGTH(path_pattern) <= 500
        ),

    CONSTRAINT unique_route
        UNIQUE (http_method, path_pattern)
);

CREATE INDEX idx_routes_active
    ON api_routes(priority, http_method)
    WHERE status = 'ACTIVE';

CREATE INDEX idx_routes_service
    ON api_routes(service_id);

-- ============================================================================
-- 6. RATE LIMIT POLICIES
-- ============================================================================

CREATE TABLE rate_limit_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    route_id BIGINT NOT NULL UNIQUE
        REFERENCES api_routes(route_id)
        ON DELETE CASCADE,

    requests_per_second INTEGER NOT NULL,

    burst_capacity INTEGER NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT valid_rate
        CHECK (requests_per_second > 0),

    CONSTRAINT valid_burst
        CHECK (burst_capacity > 0)
);

-- Runtime bucket state is stored separately from policy configuration.

CREATE TABLE rate_limit_buckets (
    bucket_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    client_id BIGINT NOT NULL
        REFERENCES api_clients(client_id)
        ON DELETE CASCADE,

    route_id BIGINT NOT NULL
        REFERENCES api_routes(route_id)
        ON DELETE CASCADE,

    tokens NUMERIC(14, 4) NOT NULL,

    last_refill_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(client_id, route_id),

    CONSTRAINT valid_bucket_tokens
        CHECK (tokens >= 0)
);

CREATE INDEX idx_rate_buckets_updated
    ON rate_limit_buckets(updated_at);

-- ============================================================================
-- 7. REQUEST AUDIT
-- ============================================================================

CREATE TABLE gateway_requests (
    request_id UUID PRIMARY KEY,

    client_id BIGINT
        REFERENCES api_clients(client_id),

    route_id BIGINT
        REFERENCES api_routes(route_id),

    http_method VARCHAR(10) NOT NULL,

    request_path TEXT NOT NULL,

    source_ip INET,

    request_status gateway_request_status NOT NULL DEFAULT 'RECEIVED',

    response_status INTEGER,

    latency_ms INTEGER,

    error_code VARCHAR(100),

    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    CONSTRAINT valid_request_method
        CHECK (
            http_method IN (
                'GET',
                'POST',
                'PUT',
                'PATCH',
                'DELETE'
            )
        ),

    CONSTRAINT valid_latency
        CHECK (latency_ms IS NULL OR latency_ms >= 0),

    CONSTRAINT valid_response_status
        CHECK (
            response_status IS NULL
            OR response_status BETWEEN 100 AND 599
        )
);

CREATE INDEX idx_gateway_requests_client_time
    ON gateway_requests(client_id, received_at DESC);

CREATE INDEX idx_gateway_requests_route_time
    ON gateway_requests(route_id, received_at DESC);

CREATE INDEX idx_gateway_requests_errors
    ON gateway_requests(response_status, received_at DESC)
    WHERE response_status >= 400;

CREATE INDEX idx_gateway_requests_status
    ON gateway_requests(request_status, received_at DESC);

-- ============================================================================
-- 8. RATE LIMIT EVENT HISTORY
-- ============================================================================

CREATE TABLE rate_limit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    client_id BIGINT NOT NULL
        REFERENCES api_clients(client_id),

    route_id BIGINT NOT NULL
        REFERENCES api_routes(route_id),

    request_id UUID
        REFERENCES gateway_requests(request_id),

    allowed BOOLEAN NOT NULL,

    remaining_tokens NUMERIC(14, 4) NOT NULL,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rate_events_client_time
    ON rate_limit_events(client_id, occurred_at DESC);

CREATE INDEX idx_rate_events_denied
    ON rate_limit_events(occurred_at DESC)
    WHERE allowed = FALSE;

-- ============================================================================
-- 9. TRIGGERS
-- ============================================================================

CREATE FUNCTION update_modified_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_clients_updated
BEFORE UPDATE ON api_clients
FOR EACH ROW
EXECUTE FUNCTION update_modified_timestamp();

CREATE FUNCTION validate_request_completion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.request_status = 'COMPLETED'
       AND NEW.completed_at IS NULL THEN

        NEW.completed_at = NOW();

    END IF;

    IF NEW.request_status = 'FAILED'
       AND NEW.error_code IS NULL THEN

        RAISE EXCEPTION
            'Failed requests require an error code';

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_request_completion
BEFORE INSERT OR UPDATE ON gateway_requests
FOR EACH ROW
EXECUTE FUNCTION validate_request_completion();

-- ============================================================================
-- 10. AUTHENTICATION FUNCTION
-- ============================================================================

CREATE FUNCTION authenticate_api_client(
    p_token_hash CHAR(64)
)
RETURNS TABLE (
    authenticated_client_id BIGINT,
    authenticated_client_code VARCHAR(60)
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        c.client_id,
        c.client_code
    FROM api_credentials cred
    JOIN api_clients c
        ON c.client_id = cred.client_id
    WHERE cred.token_hash = p_token_hash
      AND cred.revoked_at IS NULL
      AND (
          cred.expires_at IS NULL
          OR cred.expires_at > NOW()
      )
      AND c.status = 'ACTIVE';
$$;

-- ============================================================================
-- 11. AUTHORIZATION FUNCTION
-- ============================================================================

CREATE FUNCTION client_has_scope(
    p_client_id BIGINT,
    p_scope_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM client_scopes cs
        JOIN api_clients c
            ON c.client_id = cs.client_id
        WHERE cs.client_id = p_client_id
          AND cs.scope_id = p_scope_id
          AND c.status = 'ACTIVE'
    );
$$;

-- ============================================================================
-- 12. TOKEN-BUCKET RATE LIMIT FUNCTION
-- ============================================================================

CREATE FUNCTION consume_rate_limit_token(
    p_client_id BIGINT,
    p_route_id BIGINT,
    p_request_id UUID DEFAULT NULL
)
RETURNS TABLE (
    allowed BOOLEAN,
    remaining_tokens NUMERIC(14, 4)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_policy rate_limit_policies%ROWTYPE;

    v_tokens NUMERIC(14, 4);

    v_last_refill TIMESTAMPTZ;

    v_now TIMESTAMPTZ := CLOCK_TIMESTAMP();

    v_elapsed NUMERIC;

    v_allowed BOOLEAN;
BEGIN

    SELECT *
    INTO v_policy
    FROM rate_limit_policies
    WHERE route_id = p_route_id
      AND enabled = TRUE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT TRUE, 0::NUMERIC(14, 4);
        RETURN;
    END IF;

    -- Create the initial bucket safely when concurrent requests
    -- attempt to access the same client and route.

    INSERT INTO rate_limit_buckets (
        client_id,
        route_id,
        tokens,
        last_refill_at
    )
    VALUES (
        p_client_id,
        p_route_id,
        v_policy.burst_capacity,
        v_now
    )
    ON CONFLICT (client_id, route_id)
    DO NOTHING;

    -- Locking serializes token consumption for this bucket.
    SELECT tokens, last_refill_at
    INTO v_tokens, v_last_refill
    FROM rate_limit_buckets
    WHERE client_id = p_client_id
      AND route_id = p_route_id
    FOR UPDATE;

    v_elapsed := GREATEST(
        0,
        EXTRACT(EPOCH FROM (v_now - v_last_refill))
    );

    v_tokens := LEAST(
        v_policy.burst_capacity,
        v_tokens +
        v_elapsed * v_policy.requests_per_second
    );

    v_allowed := v_tokens >= 1;

    IF v_allowed THEN
        v_tokens := v_tokens - 1;
    END IF;

    UPDATE rate_limit_buckets
    SET tokens = v_tokens,
        last_refill_at = v_now,
        updated_at = v_now
    WHERE client_id = p_client_id
      AND route_id = p_route_id;

    INSERT INTO rate_limit_events (
        client_id,
        route_id,
        request_id,
        allowed,
        remaining_tokens
    )
    VALUES (
        p_client_id,
        p_route_id,
        p_request_id,
        v_allowed,
        v_tokens
    );

    RETURN QUERY
    SELECT v_allowed, v_tokens;
END;
$$;

-- ============================================================================
-- 13. ROUTE RESOLUTION VIEW
-- ============================================================================

CREATE VIEW active_route_registry AS
SELECT
    r.route_id,
    r.route_code,
    r.http_method,
    r.path_pattern,
    r.priority,
    s.service_name,
    s.base_url,
    s.health,
    s.circuit_status,
    sc.scope_name,
    p.requests_per_second,
    p.burst_capacity,
    p.enabled AS rate_limiting_enabled
FROM api_routes r
JOIN upstream_services s
    ON s.service_id = r.service_id
JOIN api_scopes sc
    ON sc.scope_id = r.required_scope_id
LEFT JOIN rate_limit_policies p
    ON p.route_id = r.route_id
WHERE r.status = 'ACTIVE';

-- ============================================================================
-- 14. REQUEST PERFORMANCE REPORT
-- ============================================================================

CREATE VIEW gateway_performance_report AS
SELECT
    DATE_TRUNC('hour', received_at) AS request_hour,
    route_id,
    COUNT(*) AS total_requests,
    COUNT(*) FILTER (
        WHERE response_status BETWEEN 200 AND 299
    ) AS successful_requests,
    COUNT(*) FILTER (
        WHERE response_status = 429
    ) AS rate_limited_requests,
    COUNT(*) FILTER (
        WHERE response_status BETWEEN 400 AND 599
    ) AS failed_requests,
    ROUND(
        AVG(latency_ms)::NUMERIC,
        2
    ) AS average_latency_ms,
    MAX(latency_ms) AS maximum_latency_ms
FROM gateway_requests
GROUP BY
    DATE_TRUNC('hour', received_at),
    route_id;

-- ============================================================================
-- 15. MERGE-FREE ROUTE ELIGIBILITY EVALUATION
-- ============================================================================

CREATE FUNCTION evaluate_gateway_request(
    p_client_id BIGINT,
    p_route_id BIGINT
)
RETURNS TABLE (
    route_available BOOLEAN,
    client_active BOOLEAN,
    scope_granted BOOLEAN,
    upstream_healthy BOOLEAN,
    policy_enabled BOOLEAN,
    eligible BOOLEAN
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        r.status = 'ACTIVE',

        c.status = 'ACTIVE',

        EXISTS (
            SELECT 1
            FROM client_scopes cs
            WHERE cs.client_id = c.client_id
              AND cs.scope_id = r.required_scope_id
        ),

        s.health = 'HEALTHY'
            AND s.circuit_status <> 'OPEN',

        COALESCE(p.enabled, TRUE),

        (
            r.status = 'ACTIVE'
            AND c.status = 'ACTIVE'
            AND EXISTS (
                SELECT 1
                FROM client_scopes cs
                WHERE cs.client_id = c.client_id
                  AND cs.scope_id = r.required_scope_id
            )
            AND s.health = 'HEALTHY'
            AND s.circuit_status <> 'OPEN'
            AND COALESCE(p.enabled, TRUE)
        )

    FROM api_clients c
    CROSS JOIN api_routes r
    JOIN upstream_services s
        ON s.service_id = r.service_id
    LEFT JOIN rate_limit_policies p
        ON p.route_id = r.route_id
    WHERE c.client_id = p_client_id
      AND r.route_id = p_route_id;
$$;

-- ============================================================================
-- 16. SAMPLE DATA
-- ============================================================================

INSERT INTO api_scopes (
    scope_name,
    description
)
VALUES
    ('users:read', 'Read user records'),
    ('users:delete', 'Delete user records'),
    ('orders:create', 'Create orders'),
    ('orders:read', 'Read order records');

INSERT INTO api_clients (
    client_code,
    client_name,
    status
)
VALUES
    ('CLIENT_APP_001', 'Customer Application', 'ACTIVE'),
    ('CLIENT_APP_002', 'Administrative Application', 'ACTIVE'),
    ('CLIENT_APP_003', 'Suspended Application', 'SUSPENDED');

INSERT INTO api_credentials (
    client_id,
    token_hash,
    expires_at
)
SELECT
    client_id,
    REPEAT('a', 64),
    NOW() + INTERVAL '365 days'
FROM api_clients
WHERE client_code = 'CLIENT_APP_001';

INSERT INTO api_credentials (
    client_id,
    token_hash,
    expires_at
)
SELECT
    client_id,
    REPEAT('b', 64),
    NOW() + INTERVAL '365 days'
FROM api_clients
WHERE client_code = 'CLIENT_APP_002';

INSERT INTO api_credentials (
    client_id,
    token_hash,
    expires_at
)
SELECT
    client_id,
    REPEAT('c', 64),
    NOW() + INTERVAL '365 days'
FROM api_clients
WHERE client_code = 'CLIENT_APP_003';

INSERT INTO client_scopes (
    client_id,
    scope_id
)
SELECT c.client_id, s.scope_id
FROM api_clients c
CROSS JOIN api_scopes s
WHERE
    (
        c.client_code = 'CLIENT_APP_001'
        AND s.scope_name IN (
            'users:read',
            'orders:create'
        )
    )
    OR
    (
        c.client_code = 'CLIENT_APP_002'
        AND s.scope_name IN (
            'users:read',
            'users:delete',
            'orders:create',
            'orders:read'
        )
    );

INSERT INTO upstream_services (
    service_name,
    base_url,
    health,
    connection_timeout_ms,
    response_timeout_ms
)
VALUES
    (
        'user-service',
        'http://users.internal:8081',
        'HEALTHY',
        2000,
        5000
    ),
    (
        'order-service',
        'http://orders.internal:8082',
        'HEALTHY',
        2000,
        5000
    ),
    (
        'payment-service',
        'http://payments.internal:8083',
        'DEGRADED',
        2000,
        8000
    );

INSERT INTO api_routes (
    route_code,
    route_name,
    http_method,
    path_pattern,
    service_id,
    required_scope_id,
    priority
)
SELECT
    'GET_USER',
    'Retrieve User',
    'GET',
    '/api/v1/users/{userId}',
    s.service_id,
    sc.scope_id,
    10
FROM upstream_services s
JOIN api_scopes sc
    ON sc.scope_name = 'users:read'
WHERE s.service_name = 'user-service';

INSERT INTO api_routes (
    route_code,
    route_name,
    http_method,
    path_pattern,
    service_id,
    required_scope_id,
    priority
)
SELECT
    'CREATE_ORDER',
    'Create Order',
    'POST',
    '/api/v1/orders',
    s.service_id,
    sc.scope_id,
    20
FROM upstream_services s
JOIN api_scopes sc
    ON sc.scope_name = 'orders:create'
WHERE s.service_name = 'order-service';

INSERT INTO api_routes (
    route_code,
    route_name,
    http_method,
    path_pattern,
    service_id,
    required_scope_id,
    priority
)
SELECT
    'DELETE_USER',
    'Delete User',
    'DELETE',
    '/api/v1/users/{userId}',
    s.service_id,
    sc.scope_id,
    30
FROM upstream_services s
JOIN api_scopes sc
    ON sc.scope_name = 'users:delete'
WHERE s.service_name = 'user-service';

INSERT INTO rate_limit_policies (
    route_id,
    requests_per_second,
    burst_capacity
)
SELECT route_id, 3, 5
FROM api_routes
WHERE route_code = 'GET_USER';

INSERT INTO rate_limit_policies (
    route_id,
    requests_per_second,
    burst_capacity
)
SELECT route_id, 5, 10
FROM api_routes
WHERE route_code = 'CREATE_ORDER';

INSERT INTO rate_limit_policies (
    route_id,
    requests_per_second,
    burst_capacity
)
SELECT route_id, 2, 3
FROM api_routes
WHERE route_code = 'DELETE_USER';

-- ============================================================================
-- 17. SAMPLE REQUEST RECORDS
-- ============================================================================

INSERT INTO gateway_requests (
    request_id,
    client_id,
    route_id,
    http_method,
    request_path,
    source_ip,
    request_status,
    response_status,
    latency_ms,
    completed_at
)
SELECT
    '11111111-1111-4111-8111-111111111111',
    c.client_id,
    r.route_id,
    'GET',
    '/api/v1/users/101',
    '192.168.1.10',
    'COMPLETED',
    200,
    42,
    NOW()
FROM api_clients c
JOIN api_routes r
    ON r.route_code = 'GET_USER'
WHERE c.client_code = 'CLIENT_APP_001';

INSERT INTO gateway_requests (
    request_id,
    client_id,
    route_id,
    http_method,
    request_path,
    source_ip,
    request_status,
    response_status,
    latency_ms,
    completed_at
)
SELECT
    '22222222-2222-4222-8222-222222222222',
    c.client_id,
    r.route_id,
    'POST',
    '/api/v1/orders',
    '192.168.1.10',
    'COMPLETED',
    201,
    95,
    NOW()
FROM api_clients c
JOIN api_routes r
    ON r.route_code = 'CREATE_ORDER'
WHERE c.client_code = 'CLIENT_APP_001';

INSERT INTO gateway_requests (
    request_id,
    client_id,
    route_id,
    http_method,
    request_path,
    source_ip,
    request_status,
    response_status,
    latency_ms,
    error_code,
    completed_at
)
SELECT
    '33333333-3333-4333-8333-333333333333',
    c.client_id,
    r.route_id,
    'DELETE',
    '/api/v1/users/101',
    '192.168.1.20',
    'FAILED',
    403,
    3,
    'INSUFFICIENT_SCOPE',
    NOW()
FROM api_clients c
JOIN api_routes r
    ON r.route_code = 'DELETE_USER'
WHERE c.client_code = 'CLIENT_APP_001';

-- ============================================================================
-- 18. EXAMPLE TRANSACTION: RATE LIMIT CONSUMPTION
-- ============================================================================

DO $$
DECLARE
    v_client_id BIGINT;
    v_route_id BIGINT;
    v_request_id UUID :=
        '44444444-4444-4444-8444-444444444444';
    v_allowed BOOLEAN;
    v_remaining NUMERIC(14, 4);
BEGIN

    SELECT client_id
    INTO v_client_id
    FROM api_clients
    WHERE client_code = 'CLIENT_APP_001';

    SELECT route_id
    INTO v_route_id
    FROM api_routes
    WHERE route_code = 'GET_USER';

    INSERT INTO gateway_requests (
        request_id,
        client_id,
        route_id,
        http_method,
        request_path,
        request_status
    )
    VALUES (
        v_request_id,
        v_client_id,
        v_route_id,
        'GET',
        '/api/v1/users/102',
        'RECEIVED'
    );

    SELECT allowed, remaining_tokens
    INTO v_allowed, v_remaining
    FROM consume_rate_limit_token(
        v_client_id,
        v_route_id,
        v_request_id
    );

    UPDATE gateway_requests
    SET request_status =
            CASE
                WHEN v_allowed THEN 'AUTHORIZED'
                ELSE 'RATE_LIMITED'
            END,
        response_status =
            CASE
                WHEN v_allowed THEN NULL
                ELSE 429
            END
    WHERE request_id = v_request_id;

    RAISE NOTICE
        'Request allowed: %, remaining tokens: %',
        v_allowed,
        v_remaining;
END;
$$;

COMMIT;

-- ============================================================================
-- 19. RETRIEVAL: ACTIVE ROUTE REGISTRY
-- ============================================================================

SELECT
    route_code,
    http_method,
    path_pattern,
    service_name,
    scope_name,
    requests_per_second,
    burst_capacity
FROM active_route_registry
ORDER BY priority;

-- ============================================================================
-- 20. AUTHENTICATION VALIDATION
-- ============================================================================

SELECT *
FROM authenticate_api_client(REPEAT('a', 64)::CHAR(64));

-- Invalid or expired credentials return no rows.

SELECT *
FROM authenticate_api_client(REPEAT('z', 64)::CHAR(64));

-- ============================================================================
-- 21. AUTHORIZATION VALIDATION
-- ============================================================================

SELECT
    c.client_code,
    s.scope_name,
    client_has_scope(
        c.client_id,
        s.scope_id
    ) AS permission_granted
FROM api_clients c
CROSS JOIN api_scopes s
WHERE c.client_code IN (
    'CLIENT_APP_001',
    'CLIENT_APP_002'
)
ORDER BY c.client_code, s.scope_name;

-- ============================================================================
-- 22. ROUTE AND CLIENT ELIGIBILITY
-- ============================================================================

SELECT
    c.client_code,
    r.route_code,
    evaluation.*
FROM api_clients c
CROSS JOIN api_routes r
CROSS JOIN LATERAL evaluate_gateway_request(
    c.client_id,
    r.route_id
) AS evaluation
WHERE c.client_code IN (
    'CLIENT_APP_001',
    'CLIENT_APP_002',
    'CLIENT_APP_003'
)
ORDER BY c.client_code, r.route_code;

-- ============================================================================
-- 23. AGGREGATION: REQUEST COUNTS
-- ============================================================================

SELECT
    r.route_code,
    COUNT(g.request_id) AS total_requests,
    COUNT(*) FILTER (
        WHERE g.response_status BETWEEN 200 AND 299
    ) AS successful_requests,
    COUNT(*) FILTER (
        WHERE g.response_status = 403
    ) AS authorization_failures,
    COUNT(*) FILTER (
        WHERE g.response_status = 429
    ) AS rate_limit_failures,
    COUNT(*) FILTER (
        WHERE g.response_status >= 500
    ) AS upstream_failures,
    ROUND(
        AVG(g.latency_ms)::NUMERIC,
        2
    ) AS average_latency_ms
FROM api_routes r
LEFT JOIN gateway_requests g
    ON g.route_id = r.route_id
GROUP BY r.route_id, r.route_code
ORDER BY total_requests DESC;

-- ============================================================================
-- 24. REPORTING: HOURLY PERFORMANCE
-- ============================================================================

SELECT *
FROM gateway_performance_report
ORDER BY request_hour DESC, route_id;

-- ============================================================================
-- 25. RATE LIMIT REJECTION ANALYSIS
-- ============================================================================

SELECT
    c.client_code,
    r.route_code,
    COUNT(*) AS rejected_requests,
    MAX(e.occurred_at) AS last_rejection
FROM rate_limit_events e
JOIN api_clients c
    ON c.client_id = e.client_id
JOIN api_routes r
    ON r.route_id = e.route_id
WHERE e.allowed = FALSE
GROUP BY c.client_code, r.route_code
ORDER BY rejected_requests DESC;

-- ============================================================================
-- 26. UPSTREAM HEALTH MONITORING
-- ============================================================================

SELECT
    service_name,
    health,
    circuit_status,
    consecutive_failures,
    circuit_opened_at,
    last_health_check
FROM upstream_services
ORDER BY service_name;

-- ============================================================================
-- 27. WORKFLOW: REVOKE A CREDENTIAL
-- ============================================================================

BEGIN;

UPDATE api_credentials
SET revoked_at = NOW()
WHERE token_hash = REPEAT('c', 64)
  AND revoked_at IS NULL;

COMMIT;

-- Suspended clients and revoked credentials cannot authenticate.

-- ============================================================================
-- 28. WORKFLOW: TEMPORARILY DISABLE A ROUTE
-- ============================================================================

BEGIN;

UPDATE api_routes
SET status = 'MAINTENANCE'
WHERE route_code = 'CREATE_ORDER';

COMMIT;

-- Restore route availability when maintenance is complete.

BEGIN;

UPDATE api_routes
SET status = 'ACTIVE'
WHERE route_code = 'CREATE_ORDER';

COMMIT;

-- ============================================================================
-- 29. PERFORMANCE QUERY: RECENT FAILED REQUESTS
-- ============================================================================

SELECT
    request_id,
    request_path,
    response_status,
    error_code,
    received_at
FROM gateway_requests
WHERE response_status >= 400
ORDER BY received_at DESC
LIMIT 100;

-- ============================================================================
-- 30. PERFORMANCE QUERY: CLIENT REQUEST DISTRIBUTION
-- ============================================================================

WITH client_usage AS (
    SELECT
        client_id,
        COUNT(*) AS request_count,
        COUNT(*) FILTER (
            WHERE response_status >= 400
        ) AS error_count
    FROM gateway_requests
    WHERE received_at >= NOW() - INTERVAL '24 hours'
    GROUP BY client_id
)
SELECT
    c.client_code,
    COALESCE(u.request_count, 0) AS request_count,
    COALESCE(u.error_count, 0) AS error_count,
    ROUND(
        100.0 * COALESCE(u.error_count, 0)
        / NULLIF(u.request_count, 0),
        2
    ) AS error_percentage
FROM api_clients c
LEFT JOIN client_usage u
    ON u.client_id = c.client_id
ORDER BY request_count DESC;

-- ============================================================================
-- 31. DATABASE DESIGN NOTES
-- ============================================================================

COMMENT ON TABLE api_clients IS
'Registered API consumers and their operational status.';

COMMENT ON TABLE api_credentials IS
'Hashed API credentials, expiration and revocation metadata.';

COMMENT ON TABLE api_scopes IS
'Named authorization permissions assigned to API clients.';

COMMENT ON TABLE api_routes IS
'HTTP routing definitions and required authorization scopes.';

COMMENT ON TABLE rate_limit_policies IS
'Token-bucket refill rates and burst capacities per route.';

COMMENT ON TABLE rate_limit_buckets IS
'Runtime token balances maintained independently per client and route.';

COMMENT ON TABLE gateway_requests IS
'Request lifecycle and response audit records.';

COMMENT ON FUNCTION consume_rate_limit_token(
    BIGINT,
    BIGINT,
    UUID
) IS
'Atomically refills and consumes a token bucket under a row-level lock.';

COMMENT ON FUNCTION authenticate_api_client(CHAR) IS
'Validates a hashed credential, expiration, revocation and client status.';

COMMENT ON FUNCTION evaluate_gateway_request(BIGINT, BIGINT) IS
'Evaluates route availability, client status, scope, upstream health and policy state.';
