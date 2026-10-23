DROP SCHEMA IF EXISTS load_balancer_lab CASCADE;
CREATE SCHEMA load_balancer_lab;
SET search_path TO load_balancer_lab;

-- The model separates service registration, health state, routing policy,
-- health observations, requests, and routing decisions. This allows the
-- routing layer to make decisions from persistent operational evidence.

CREATE TYPE backend_state AS ENUM ('healthy', 'unhealthy', 'draining');
CREATE TYPE routing_strategy AS ENUM (
    'round_robin',
    'weighted_round_robin',
    'least_connections'
);
CREATE TYPE check_status AS ENUM ('passed', 'failed', 'timed_out');
CREATE TYPE request_status AS ENUM ('routed', 'completed', 'rejected');
CREATE TYPE rejection_reason AS ENUM (
    'no_healthy_backend',
    'capacity_exhausted',
    'invalid_request'
);

CREATE TABLE load_balancer (
    load_balancer_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    strategy routing_strategy NOT NULL,
    failure_threshold INTEGER NOT NULL DEFAULT 2,
    recovery_threshold INTEGER NOT NULL DEFAULT 2,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (failure_threshold > 0),
    CHECK (recovery_threshold > 0)
);

CREATE TABLE backend (
    backend_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancer(load_balancer_id)
        ON DELETE CASCADE,
    backend_name TEXT NOT NULL,
    host INET NOT NULL,
    port INTEGER NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    max_connections INTEGER NOT NULL DEFAULT 100,
    active_connections INTEGER NOT NULL DEFAULT 0,
    state backend_state NOT NULL DEFAULT 'healthy',
    simulated_health BOOLEAN NOT NULL DEFAULT TRUE,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    consecutive_successes INTEGER NOT NULL DEFAULT 0,
    total_requests BIGINT NOT NULL DEFAULT 0,
    failed_requests BIGINT NOT NULL DEFAULT 0,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (load_balancer_id, backend_name),
    CHECK (port BETWEEN 1 AND 65535),
    CHECK (weight > 0),
    CHECK (max_connections > 0),
    CHECK (active_connections >= 0),
    CHECK (active_connections <= max_connections),
    CHECK (consecutive_failures >= 0),
    CHECK (consecutive_successes >= 0),
    CHECK (total_requests >= 0),
    CHECK (failed_requests >= 0)
);

CREATE TABLE health_check (
    health_check_id BIGSERIAL PRIMARY KEY,
    backend_id BIGINT NOT NULL
        REFERENCES backend(backend_id)
        ON DELETE CASCADE,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status check_status NOT NULL,
    latency_ms NUMERIC(10, 2),
    detail TEXT NOT NULL,
    CHECK (latency_ms IS NULL OR latency_ms >= 0)
);

CREATE TABLE client_request (
    request_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancer(load_balancer_id)
        ON DELETE RESTRICT,
    request_key TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status request_status NOT NULL,
    rejection_reason rejection_reason,
    CHECK (
        (status = 'rejected' AND rejection_reason IS NOT NULL)
        OR
        (status <> 'rejected' AND rejection_reason IS NULL)
    ),
    UNIQUE (load_balancer_id, request_key)
);

CREATE TABLE routing_decision (
    routing_decision_id BIGSERIAL PRIMARY KEY,
    request_id BIGINT NOT NULL
        REFERENCES client_request(request_id)
        ON DELETE CASCADE,
    backend_id BIGINT
        REFERENCES backend(backend_id)
        ON DELETE SET NULL,
    decision_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_connections_at_decision INTEGER,
    decision_detail TEXT NOT NULL,
    CHECK (
        active_connections_at_decision IS NULL
        OR active_connections_at_decision >= 0
    )
);

CREATE INDEX idx_backend_available
    ON backend (load_balancer_id, state, active_connections);

CREATE INDEX idx_health_check_backend_time
    ON health_check (backend_id, checked_at DESC);

CREATE INDEX idx_routing_decision_backend
    ON routing_decision (backend_id, decision_at DESC);

CREATE VIEW healthy_backend_capacity AS
SELECT
    b.backend_id,
    b.load_balancer_id,
    b.backend_name,
    b.host,
    b.port,
    b.weight,
    b.active_connections,
    b.max_connections,
    b.max_connections - b.active_connections AS free_connections
FROM backend AS b
WHERE b.state = 'healthy'
  AND b.active_connections < b.max_connections;

CREATE VIEW backend_health_summary AS
SELECT
    b.backend_id,
    b.backend_name,
    b.state,
    b.consecutive_failures,
    b.consecutive_successes,
    COUNT(h.health_check_id) AS checks,
    COUNT(*) FILTER (
        WHERE h.status IN ('failed', 'timed_out')
    ) AS failed_checks
FROM backend AS b
LEFT JOIN health_check AS h
    ON h.backend_id = b.backend_id
GROUP BY
    b.backend_id,
    b.backend_name,
    b.state,
    b.consecutive_failures,
    b.consecutive_successes;

CREATE OR REPLACE FUNCTION validate_backend_capacity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.active_connections > NEW.max_connections THEN
        RAISE EXCEPTION
            'backend % exceeds maximum connection capacity',
            NEW.backend_name;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_backend_capacity
BEFORE INSERT OR UPDATE OF active_connections, max_connections
ON backend
FOR EACH ROW
EXECUTE FUNCTION validate_backend_capacity();

CREATE OR REPLACE FUNCTION record_health_check(
    p_backend_id BIGINT,
    p_status check_status,
    p_latency_ms NUMERIC,
    p_detail TEXT
)
RETURNS backend_state
LANGUAGE plpgsql
AS $$
DECLARE
    v_backend backend%ROWTYPE;
    v_new_state backend_state;
BEGIN
    SELECT *
    INTO v_backend
    FROM backend
    WHERE backend_id = p_backend_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'backend % does not exist',
            p_backend_id;
    END IF;

    INSERT INTO health_check (
        backend_id,
        status,
        latency_ms,
        detail
    )
    VALUES (
        p_backend_id,
        p_status,
        p_latency_ms,
        p_detail
    );

    IF p_status = 'passed' THEN
        v_backend.consecutive_failures := 0;
        v_backend.consecutive_successes :=
            v_backend.consecutive_successes + 1;

        IF
            v_backend.state = 'unhealthy'
            AND v_backend.consecutive_successes >= (
                SELECT recovery_threshold
                FROM load_balancer
                WHERE load_balancer_id = v_backend.load_balancer_id
            )
        THEN
            v_backend.state := 'healthy';
        END IF;
    ELSE
        v_backend.consecutive_successes := 0;
        v_backend.consecutive_failures :=
            v_backend.consecutive_failures + 1;

        IF
            v_backend.consecutive_failures >= (
                SELECT failure_threshold
                FROM load_balancer
                WHERE load_balancer_id = v_backend.load_balancer_id
            )
        THEN
            v_backend.state := 'unhealthy';
        END IF;
    END IF;

    UPDATE backend
    SET
        state = v_backend.state,
        consecutive_failures = v_backend.consecutive_failures,
        consecutive_successes = v_backend.consecutive_successes
    WHERE backend_id = p_backend_id;

    RETURN v_backend.state;
END;
$$;

CREATE OR REPLACE FUNCTION route_request(
    p_load_balancer_id BIGINT,
    p_request_key TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_request_id BIGINT;
    v_backend_id BIGINT;
    v_strategy routing_strategy;
    v_candidate_count INTEGER;
BEGIN
    IF p_request_key IS NULL OR btrim(p_request_key) = '' THEN
        RAISE EXCEPTION 'request key cannot be empty';
    END IF;

    SELECT strategy
    INTO v_strategy
    FROM load_balancer
    WHERE load_balancer_id = p_load_balancer_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'load balancer % does not exist',
            p_load_balancer_id;
    END IF;

    INSERT INTO client_request (
        load_balancer_id,
        request_key,
        status
    )
    VALUES (
        p_load_balancer_id,
        p_request_key,
        'routed'
    )
    RETURNING request_id INTO v_request_id;

    SELECT COUNT(*)
    INTO v_candidate_count
    FROM healthy_backend_capacity
    WHERE load_balancer_id = p_load_balancer_id;

    IF v_candidate_count = 0 THEN
        UPDATE client_request
        SET
            status = 'rejected',
            rejection_reason = 'no_healthy_backend'
        WHERE request_id = v_request_id;

        RAISE EXCEPTION
            'no healthy backend has routing capacity';
    END IF;

    IF v_strategy = 'least_connections' THEN
        SELECT backend_id
        INTO v_backend_id
        FROM healthy_backend_capacity
        WHERE load_balancer_id = p_load_balancer_id
        ORDER BY
            active_connections ASC,
            weight DESC,
            backend_id ASC
        LIMIT 1;
    ELSIF v_strategy = 'weighted_round_robin' THEN
        SELECT backend_id
        INTO v_backend_id
        FROM healthy_backend_capacity
        WHERE load_balancer_id = p_load_balancer_id
        ORDER BY
            backend_id
        LIMIT 1;
    ELSE
        SELECT backend_id
        INTO v_backend_id
        FROM healthy_backend_capacity
        WHERE load_balancer_id = p_load_balancer_id
        ORDER BY
            backend_id
        LIMIT 1;
    END IF;

    UPDATE backend
    SET
        active_connections = active_connections + 1,
        total_requests = total_requests + 1
    WHERE backend_id = v_backend_id;

    INSERT INTO routing_decision (
        request_id,
        backend_id,
        active_connections_at_decision,
        decision_detail
    )
    SELECT
        v_request_id,
        backend_id,
        active_connections,
        CASE
            WHEN v_strategy = 'least_connections'
                THEN 'least-connections candidate'
            WHEN v_strategy = 'weighted_round_robin'
                THEN 'weighted routing candidate'
            ELSE
                'round-robin candidate'
        END
    FROM backend
    WHERE backend_id = v_backend_id;

    RETURN v_request_id;
END;
$$;

CREATE OR REPLACE FUNCTION complete_request(
    p_request_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_backend_id BIGINT;
BEGIN
    SELECT backend_id
    INTO v_backend_id
    FROM routing_decision
    WHERE request_id = p_request_id
    ORDER BY routing_decision_id DESC
    LIMIT 1;

    IF v_backend_id IS NULL THEN
        RAISE EXCEPTION
            'request % has no routing decision',
            p_request_id;
    END IF;

    UPDATE backend
    SET active_connections = active_connections - 1
    WHERE backend_id = v_backend_id
      AND active_connections > 0;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'backend % has no active connection',
            v_backend_id;
    END IF;

    UPDATE client_request
    SET status = 'completed'
    WHERE request_id = p_request_id;
END;
$$;

INSERT INTO load_balancer (
    name,
    strategy,
    failure_threshold,
    recovery_threshold
)
VALUES
    ('payments-edge', 'least_connections', 2, 2),
    ('catalog-edge', 'round_robin', 2, 2);

INSERT INTO backend (
    load_balancer_id,
    backend_name,
    host,
    port,
    weight,
    max_connections
)
SELECT
    lb.load_balancer_id,
    data.backend_name,
    data.host::INET,
    data.port,
    data.weight,
    data.max_connections
FROM load_balancer AS lb
JOIN (
    VALUES
        ('payments-edge', 'payments-01', '10.60.0.11', 8080, 1, 100),
        ('payments-edge', 'payments-02', '10.60.0.12', 8080, 2, 100),
        ('payments-edge', 'payments-03', '10.60.0.13', 8080, 1, 100),
        ('catalog-edge', 'catalog-01', '10.60.1.11', 8080, 1, 50),
        ('catalog-edge', 'catalog-02', '10.60.1.12', 8080, 1, 50)
) AS data(
    lb_name,
    backend_name,
    host,
    port,
    weight,
    max_connections
)
ON lb.name = data.lb_name;

SELECT record_health_check(
    backend_id,
    'passed',
    18.50,
    'HTTP readiness probe returned 200'
)
FROM backend
WHERE backend_name IN (
    'payments-01',
    'payments-02',
    'payments-03'
);

SELECT record_health_check(
    backend_id,
    'passed',
    21.10,
    'HTTP readiness probe returned 200'
)
FROM backend
WHERE backend_name IN (
    'catalog-01',
    'catalog-02'
);

-- Two consecutive failures transition payments-03 to unhealthy.
SELECT record_health_check(
    backend_id,
    'failed',
    NULL,
    'connection refused'
)
FROM backend
WHERE backend_name = 'payments-03';

SELECT record_health_check(
    backend_id,
    'failed',
    NULL,
    'connection refused'
)
FROM backend
WHERE backend_name = 'payments-03';

-- A healthy backend remains routable while the failed node is isolated.
BEGIN;

SELECT route_request(
    load_balancer_id,
    'payment-request-001'
)
FROM load_balancer
WHERE name = 'payments-edge';

COMMIT;

BEGIN;

SELECT route_request(
    load_balancer_id,
    'payment-request-002'
)
FROM load_balancer
WHERE name = 'payments-edge';

COMMIT;

-- Reporting query: current capacity and health state.
SELECT
    lb.name AS load_balancer,
    b.backend_name,
    b.state,
    b.weight,
    b.active_connections,
    b.max_connections,
    b.max_connections - b.active_connections AS free_connections,
    b.consecutive_failures,
    b.consecutive_successes
FROM load_balancer AS lb
JOIN backend AS b
    ON b.load_balancer_id = lb.load_balancer_id
ORDER BY lb.name, b.backend_name;

-- Health quality report.
SELECT
    backend_name,
    state,
    checks,
    failed_checks,
    consecutive_failures,
    consecutive_successes
FROM backend_health_summary
ORDER BY backend_name;

-- CTE-based capacity ranking.
WITH ranked_backends AS (
    SELECT
        backend_id,
        backend_name,
        load_balancer_id,
        active_connections,
        max_connections,
        ROW_NUMBER() OVER (
            PARTITION BY load_balancer_id
            ORDER BY
                active_connections,
                weight DESC,
                backend_id
        ) AS routing_rank
    FROM backend
    WHERE state = 'healthy'
      AND active_connections < max_connections
)
SELECT
    lb.name AS load_balancer,
    rb.backend_name,
    rb.active_connections,
    rb.max_connections,
    rb.routing_rank
FROM ranked_backends AS rb
JOIN load_balancer AS lb
    ON lb.load_balancer_id = rb.load_balancer_id
ORDER BY lb.name, rb.routing_rank;

-- Recover payments-03 after two successful checks.
SELECT record_health_check(
    backend_id,
    'passed',
    19.20,
    'HTTP readiness probe returned 200'
)
FROM backend
WHERE backend_name = 'payments-03';

SELECT record_health_check(
    backend_id,
    'passed',
    19.00,
    'HTTP readiness probe returned 200'
)
FROM backend
WHERE backend_name = 'payments-03';

-- Demonstrate completion of an earlier routed request.
SELECT complete_request(
    request_id
)
FROM client_request
WHERE request_key = 'payment-request-001';

-- Transactional validation of an invalid request.
BEGIN;

DO $$
DECLARE
    v_request_id BIGINT;
BEGIN
    INSERT INTO client_request (
        load_balancer_id,
        request_key,
        status,
        rejection_reason
    )
    SELECT
        load_balancer_id,
        'invalid-request-demo',
        'rejected',
        'invalid_request'
    FROM load_balancer
    WHERE name = 'payments-edge'
    RETURNING request_id INTO v_request_id;

    IF v_request_id IS NULL THEN
        RAISE EXCEPTION 'invalid request could not be recorded';
    END IF;
END;
$$;

COMMIT;

-- Final operational report.
SELECT
    lb.name AS load_balancer,
    COUNT(b.backend_id) AS backend_count,
    COUNT(*) FILTER (WHERE b.state = 'healthy') AS healthy_backends,
    COUNT(*) FILTER (WHERE b.state = 'unhealthy') AS unhealthy_backends,
    COALESCE(SUM(b.active_connections), 0) AS active_connections,
    COALESCE(SUM(b.total_requests), 0) AS total_requests
FROM load_balancer AS lb
LEFT JOIN backend AS b
    ON b.load_balancer_id = lb.load_balancer_id
GROUP BY lb.load_balancer_id, lb.name
ORDER BY lb.name;
