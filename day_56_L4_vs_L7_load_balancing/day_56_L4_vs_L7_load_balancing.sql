DROP SCHEMA IF EXISTS load_balancing CASCADE;
CREATE SCHEMA load_balancing;

SET search_path = load_balancing, public;

-- L4 and L7 are modeled separately at the policy level while sharing
-- the same repository-independent infrastructure entities.

CREATE TYPE backend_layer AS ENUM ('L4', 'L7');

CREATE TYPE backend_state AS ENUM ('healthy', 'unhealthy');

CREATE TYPE lb_protocol AS ENUM ('TCP', 'HTTP');

CREATE TYPE request_method AS ENUM
    ('GET', 'POST', 'PUT', 'PATCH', 'DELETE');

CREATE TYPE check_state AS ENUM ('passing', 'failing');

CREATE TYPE merge_decision AS ENUM ('eligible', 'blocked');

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    commit_hash TEXT NOT NULL,
    parent_commit_id BIGINT REFERENCES commits(commit_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repository_id, commit_hash)
);

CREATE TABLE load_balancers (
    load_balancer_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    name TEXT NOT NULL,
    layer backend_layer NOT NULL,
    protocol lb_protocol NOT NULL,
    UNIQUE (repository_id, name),
    CHECK (
        (layer = 'L4' AND protocol = 'TCP')
        OR
        (layer = 'L7' AND protocol = 'HTTP')
    )
);

CREATE TABLE backends (
    backend_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancers(load_balancer_id)
        ON DELETE CASCADE,
    backend_name TEXT NOT NULL,
    address INET NOT NULL,
    port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
    state backend_state NOT NULL DEFAULT 'healthy',
    weight INTEGER NOT NULL DEFAULT 1 CHECK (weight > 0),
    active_connections INTEGER NOT NULL DEFAULT 0
        CHECK (active_connections >= 0),
    requests_served BIGINT NOT NULL DEFAULT 0
        CHECK (requests_served >= 0),
    UNIQUE (load_balancer_id, backend_name)
);

CREATE TABLE http_routes (
    route_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancers(load_balancer_id)
        ON DELETE CASCADE,
    host_pattern TEXT,
    path_prefix TEXT,
    backend_id BIGINT NOT NULL
        REFERENCES backends(backend_id)
        ON DELETE CASCADE,
    priority INTEGER NOT NULL DEFAULT 100,
    CHECK (host_pattern IS NOT NULL OR path_prefix IS NOT NULL)
);

CREATE TABLE tcp_flows (
    flow_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancers(load_balancer_id)
        ON DELETE CASCADE,
    source_ip INET NOT NULL,
    source_port INTEGER NOT NULL CHECK (source_port BETWEEN 1 AND 65535),
    destination_ip INET NOT NULL,
    destination_port INTEGER NOT NULL
        CHECK (destination_port BETWEEN 1 AND 65535),
    backend_id BIGINT NOT NULL
        REFERENCES backends(backend_id),
    opened_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMPTZ,
    UNIQUE (
        load_balancer_id,
        source_ip,
        source_port,
        destination_ip,
        destination_port
    )
);

CREATE TABLE http_requests (
    request_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancers(load_balancer_id)
        ON DELETE CASCADE,
    client_ip INET NOT NULL,
    method request_method NOT NULL,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    session_id TEXT,
    backend_id BIGINT
        REFERENCES backends(backend_id),
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(host) BETWEEN 1 AND 253),
    CHECK (left(path, 1) = '/'),
    CHECK (length(path) <= 4096),
    CHECK (session_id IS NULL OR length(session_id) <= 128)
);

CREATE TABLE health_checks (
    health_check_id BIGSERIAL PRIMARY KEY,
    backend_id BIGINT NOT NULL
        REFERENCES backends(backend_id)
        ON DELETE CASCADE,
    check_type lb_protocol NOT NULL,
    state check_state NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    latency_ms INTEGER CHECK (latency_ms >= 0)
);

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    required_reviews INTEGER NOT NULL DEFAULT 0
        CHECK (required_reviews >= 0),
    required_status_checks INTEGER NOT NULL DEFAULT 0
        CHECK (required_status_checks >= 0),
    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_branch_deletion BOOLEAN NOT NULL DEFAULT FALSE,
    require_conversations_resolved BOOLEAN NOT NULL DEFAULT TRUE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    allow_administrator_bypass BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (branch_id)
);

CREATE TABLE repositories_security_events (
    event_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backends_state
    ON backends(load_balancer_id, state);

CREATE INDEX idx_http_requests_backend_time
    ON http_requests(backend_id, received_at);

CREATE INDEX idx_health_checks_backend_time
    ON health_checks(backend_id, checked_at DESC);

CREATE INDEX idx_tcp_flows_backend
    ON tcp_flows(backend_id);

CREATE INDEX idx_http_routes_priority
    ON http_routes(load_balancer_id, priority);

INSERT INTO repositories(repository_name)
VALUES ('commerce-platform');

INSERT INTO branches(
    repository_id,
    branch_name,
    is_protected
)
SELECT
    repository_id,
    'main',
    TRUE
FROM repositories
WHERE repository_name = 'commerce-platform';

INSERT INTO branches(
    repository_id,
    branch_name,
    is_protected
)
SELECT
    repository_id,
    'develop',
    FALSE
FROM repositories
WHERE repository_name = 'commerce-platform';

INSERT INTO load_balancers(
    repository_id,
    name,
    layer,
    protocol
)
SELECT repository_id, 'public-tcp-lb', 'L4', 'TCP'
FROM repositories
WHERE repository_name = 'commerce-platform';

INSERT INTO load_balancers(
    repository_id,
    name,
    layer,
    protocol
)
SELECT repository_id, 'application-http-lb', 'L7', 'HTTP'
FROM repositories
WHERE repository_name = 'commerce-platform';

INSERT INTO backends(
    load_balancer_id,
    backend_name,
    address,
    port
)
SELECT
    load_balancer_id,
    data.backend_name,
    data.address::inet,
    data.port
FROM load_balancers
CROSS JOIN (
    VALUES
        ('api-1', '10.0.0.11', 443),
        ('api-2', '10.0.0.12', 443),
        ('api-3', '10.0.0.13', 443)
) AS data(backend_name, address, port)
WHERE load_balancers.name = 'public-tcp-lb';

INSERT INTO backends(
    load_balancer_id,
    backend_name,
    address,
    port
)
SELECT
    load_balancer_id,
    data.backend_name,
    data.address::inet,
    data.port
FROM load_balancers
CROSS JOIN (
    VALUES
        ('api-1', '10.0.0.11', 8080),
        ('api-2', '10.0.0.12', 8080),
        ('static-1', '10.0.0.21', 8080)
) AS data(backend_name, address, port)
WHERE load_balancers.name = 'application-http-lb';

INSERT INTO http_routes(
    load_balancer_id,
    host_pattern,
    path_prefix,
    backend_id,
    priority
)
SELECT
    lb.load_balancer_id,
    'api.example.com',
    '/api',
    b.backend_id,
    10
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE lb.name = 'application-http-lb'
  AND b.backend_name IN ('api-1', 'api-2');

INSERT INTO http_routes(
    load_balancer_id,
    host_pattern,
    path_prefix,
    backend_id,
    priority
)
SELECT
    lb.load_balancer_id,
    'cdn.example.com',
    '/static',
    b.backend_id,
    10
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE lb.name = 'application-http-lb'
  AND b.backend_name = 'static-1';

INSERT INTO health_checks(
    backend_id,
    check_type,
    state,
    latency_ms
)
SELECT
    backend_id,
    'TCP',
    CASE
        WHEN backend_name = 'api-3' THEN 'failing'::check_state
        ELSE 'passing'::check_state
    END,
    CASE
        WHEN backend_name = 'api-3' THEN 0
        ELSE 12
    END
FROM backends
WHERE load_balancer_id = (
    SELECT load_balancer_id
    FROM load_balancers
    WHERE name = 'public-tcp-lb'
);

INSERT INTO health_checks(
    backend_id,
    check_type,
    state,
    latency_ms
)
SELECT
    backend_id,
    'HTTP',
    'passing',
    CASE
        WHEN backend_name = 'static-1' THEN 7
        ELSE 18
    END
FROM backends
WHERE load_balancer_id = (
    SELECT load_balancer_id
    FROM load_balancers
    WHERE name = 'application-http-lb'
);

-- A trigger prevents an unhealthy backend from accepting a newly recorded
-- request or flow. Existing records remain useful for historical analysis.
CREATE OR REPLACE FUNCTION enforce_healthy_backend()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_state backend_state;
BEGIN
    SELECT state
    INTO current_state
    FROM backends
    WHERE backend_id = NEW.backend_id;

    IF current_state IS DISTINCT FROM 'healthy'::backend_state THEN
        RAISE EXCEPTION
            'Backend % is not healthy and cannot receive traffic',
            NEW.backend_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tcp_flow_healthy_backend
BEFORE INSERT OR UPDATE OF backend_id
ON tcp_flows
FOR EACH ROW
EXECUTE FUNCTION enforce_healthy_backend();

CREATE TRIGGER trg_http_request_healthy_backend
BEFORE INSERT OR UPDATE OF backend_id
ON http_requests
FOR EACH ROW
EXECUTE FUNCTION enforce_healthy_backend();

-- Keep aggregate connection state synchronized with TCP flow lifecycle.
CREATE OR REPLACE FUNCTION update_backend_connection_count()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE backends
        SET active_connections = active_connections + 1
        WHERE backend_id = NEW.backend_id;
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.closed_at IS NULL
       AND NEW.closed_at IS NOT NULL THEN

        UPDATE backends
        SET active_connections = GREATEST(active_connections - 1, 0)
        WHERE backend_id = NEW.backend_id;

        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tcp_connection_state
AFTER INSERT OR UPDATE OF closed_at
ON tcp_flows
FOR EACH ROW
EXECUTE FUNCTION update_backend_connection_count();

-- Count application requests after the routing decision has been recorded.
CREATE OR REPLACE FUNCTION increment_request_counter()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE backends
    SET requests_served = requests_served + 1
    WHERE backend_id = NEW.backend_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_http_request_counter
AFTER INSERT
ON http_requests
FOR EACH ROW
EXECUTE FUNCTION increment_request_counter();

-- L4 flow distribution: the same TCP flow is represented by one backend.
INSERT INTO tcp_flows(
    load_balancer_id,
    source_ip,
    source_port,
    destination_ip,
    destination_port,
    backend_id
)
SELECT
    lb.load_balancer_id,
    '192.168.1.10'::inet,
    50001,
    '203.0.113.10'::inet,
    443,
    b.backend_id
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE lb.name = 'public-tcp-lb'
  AND b.backend_name = 'api-1';

-- L7 request routing is performed per HTTP request.
INSERT INTO http_requests(
    load_balancer_id,
    client_ip,
    method,
    host,
    path,
    session_id,
    backend_id
)
SELECT
    lb.load_balancer_id,
    '192.168.1.10'::inet,
    'GET',
    'api.example.com',
    '/api/orders',
    'customer-42',
    b.backend_id
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE lb.name = 'application-http-lb'
  AND b.backend_name = 'api-1';

INSERT INTO http_requests(
    load_balancer_id,
    client_ip,
    method,
    host,
    path,
    session_id,
    backend_id
)
SELECT
    lb.load_balancer_id,
    '192.168.1.10'::inet,
    'GET',
    'api.example.com',
    '/api/products',
    'customer-42',
    b.backend_id
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE lb.name = 'application-http-lb'
  AND b.backend_name = 'api-1';

INSERT INTO http_requests(
    load_balancer_id,
    client_ip,
    method,
    host,
    path,
    backend_id
)
SELECT
    lb.load_balancer_id,
    '192.168.1.20'::inet,
    'GET',
    'cdn.example.com',
    '/static/app.js',
    b.backend_id
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE lb.name = 'application-http-lb'
  AND b.backend_name = 'static-1';

-- Demonstrate the difference between transport and application routing.
SELECT
    lb.name,
    lb.layer,
    lb.protocol,
    b.backend_name,
    b.state,
    b.active_connections,
    b.requests_served
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
ORDER BY lb.name, b.backend_name;

-- L7 route evaluation by host and path.
SELECT
    r.route_id,
    r.host_pattern,
    r.path_prefix,
    r.priority,
    b.backend_name,
    b.state
FROM http_routes r
JOIN backends b
    ON b.backend_id = r.backend_id
WHERE r.load_balancer_id = (
    SELECT load_balancer_id
    FROM load_balancers
    WHERE name = 'application-http-lb'
)
ORDER BY r.priority, r.route_id;

-- Health report identifies backends that must not receive new traffic.
SELECT
    lb.name AS load_balancer,
    b.backend_name,
    b.state AS backend_state,
    hc.check_type,
    hc.state AS check_state,
    hc.latency_ms,
    hc.checked_at
FROM backends b
JOIN load_balancers lb
    ON lb.load_balancer_id = b.load_balancer_id
LEFT JOIN LATERAL (
    SELECT *
    FROM health_checks h
    WHERE h.backend_id = b.backend_id
    ORDER BY h.checked_at DESC
    LIMIT 1
) hc ON TRUE
ORDER BY lb.name, b.backend_name;

-- Compare request distribution across application backends.
SELECT
    b.backend_name,
    COUNT(hr.request_id) AS routed_requests,
    ROUND(
        100.0 * COUNT(hr.request_id)
        / NULLIF(SUM(COUNT(hr.request_id)) OVER (), 0),
        2
    ) AS traffic_percentage
FROM backends b
LEFT JOIN http_requests hr
    ON hr.backend_id = b.backend_id
WHERE b.load_balancer_id = (
    SELECT load_balancer_id
    FROM load_balancers
    WHERE name = 'application-http-lb'
)
GROUP BY b.backend_name
ORDER BY routed_requests DESC, b.backend_name;

-- Session affinity analysis shows that application-level state can keep
-- multiple HTTP requests on one backend.
SELECT
    session_id,
    COUNT(*) AS request_count,
    COUNT(DISTINCT backend_id) AS backend_count,
    ARRAY_AGG(DISTINCT backend_id ORDER BY backend_id) AS backend_ids
FROM http_requests
WHERE session_id IS NOT NULL
GROUP BY session_id;

-- Transactional failure example:
-- the entire routing record is committed atomically.
BEGIN;

WITH selected_backend AS (
    SELECT b.backend_id
    FROM backends b
    JOIN load_balancers lb
        ON lb.load_balancer_id = b.load_balancer_id
    WHERE lb.name = 'application-http-lb'
      AND b.backend_name = 'api-2'
      AND b.state = 'healthy'
    LIMIT 1
)
INSERT INTO http_requests(
    load_balancer_id,
    client_ip,
    method,
    host,
    path,
    backend_id
)
SELECT
    lb.load_balancer_id,
    '192.168.1.30'::inet,
    'GET',
    'api.example.com',
    '/api/health',
    sb.backend_id
FROM load_balancers lb
CROSS JOIN selected_backend sb
WHERE lb.name = 'application-http-lb';

COMMIT;

-- Security audit: detect traffic records that would violate the expected
-- application routing policy.
SELECT
    hr.request_id,
    hr.host,
    hr.path,
    b.backend_name,
    r.backend_id AS expected_backend
FROM http_requests hr
JOIN backends b
    ON b.backend_id = hr.backend_id
JOIN http_routes r
    ON r.load_balancer_id = hr.load_balancer_id
   AND r.host_pattern = hr.host
   AND hr.path LIKE r.path_prefix || '%'
WHERE hr.backend_id <> r.backend_id
  AND r.priority = (
      SELECT MIN(r2.priority)
      FROM http_routes r2
      WHERE r2.load_balancer_id = hr.load_balancer_id
        AND r2.host_pattern = hr.host
        AND hr.path LIKE r2.path_prefix || '%'
  );

-- L4 flow table shows transport-level stickiness.
SELECT
    source_ip,
    source_port,
    destination_ip,
    destination_port,
    b.backend_name,
    opened_at,
    closed_at
FROM tcp_flows tf
JOIN backends b
    ON b.backend_id = tf.backend_id
ORDER BY opened_at;

-- A backend failure can be explicitly recorded and then detected by the
-- application before another request is assigned to it.
UPDATE backends
SET state = 'unhealthy'
WHERE backend_name = 'api-2'
  AND load_balancer_id = (
      SELECT load_balancer_id
      FROM load_balancers
      WHERE name = 'application-http-lb'
  );

SELECT
    b.backend_name,
    b.state,
    COUNT(hr.request_id) AS historical_requests
FROM backends b
LEFT JOIN http_requests hr
    ON hr.backend_id = b.backend_id
GROUP BY b.backend_name, b.state
ORDER BY b.backend_name;
