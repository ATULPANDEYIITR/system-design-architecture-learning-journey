DROP SCHEMA IF EXISTS load_balancing CASCADE;
CREATE SCHEMA load_balancing;

SET search_path = load_balancing, public;

CREATE TYPE backend_status AS ENUM ('healthy', 'unhealthy', 'draining');

CREATE TYPE balancing_algorithm AS ENUM (
    'round_robin',
    'weighted_round_robin',
    'least_connections'
);

CREATE TYPE request_status AS ENUM (
    'queued',
    'active',
    'completed',
    'failed'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE load_balancers (
    load_balancer_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    name TEXT NOT NULL,
    algorithm balancing_algorithm NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (repository_id, name)
);

CREATE TABLE backends (
    backend_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancers(load_balancer_id)
        ON DELETE CASCADE,
    backend_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1
        CHECK (weight > 0),
    status backend_status NOT NULL DEFAULT 'healthy',
    active_connections INTEGER NOT NULL DEFAULT 0
        CHECK (active_connections >= 0),
    total_requests BIGINT NOT NULL DEFAULT 0
        CHECK (total_requests >= 0),
    completed_requests BIGINT NOT NULL DEFAULT 0
        CHECK (completed_requests >= 0),
    failed_requests BIGINT NOT NULL DEFAULT 0
        CHECK (failed_requests >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (load_balancer_id, backend_name),
    UNIQUE (load_balancer_id, endpoint),
    CHECK (completed_requests + failed_requests <= total_requests)
);

CREATE TABLE requests (
    request_id BIGSERIAL PRIMARY KEY,
    load_balancer_id BIGINT NOT NULL
        REFERENCES load_balancers(load_balancer_id)
        ON DELETE CASCADE,
    backend_id BIGINT
        REFERENCES backends(backend_id)
        ON DELETE SET NULL,
    status request_status NOT NULL DEFAULT 'queued',
    duration_ms INTEGER
        CHECK (duration_ms IS NULL OR duration_ms > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK (
        completed_at IS NULL
        OR started_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE INDEX idx_backends_balancer_status
    ON backends (load_balancer_id, status);

CREATE INDEX idx_backends_least_connections
    ON backends (
        load_balancer_id,
        active_connections,
        weight
    )
    WHERE status = 'healthy';

CREATE INDEX idx_requests_balancer_status
    ON requests (load_balancer_id, status);

CREATE INDEX idx_requests_backend
    ON requests (backend_id);

INSERT INTO repositories (repository_name)
VALUES ('traffic-platform');

INSERT INTO load_balancers (
    repository_id,
    name,
    algorithm
)
SELECT
    repository_id,
    'public-api',
    'round_robin'
FROM repositories
WHERE repository_name = 'traffic-platform';

INSERT INTO load_balancers (
    repository_id,
    name,
    algorithm
)
SELECT
    repository_id,
    'weighted-api',
    'weighted_round_robin'
FROM repositories
WHERE repository_name = 'traffic-platform';

INSERT INTO load_balancers (
    repository_id,
    name,
    algorithm
)
SELECT
    repository_id,
    'connection-aware-api',
    'least_connections'
FROM repositories
WHERE repository_name = 'traffic-platform';

INSERT INTO backends (
    load_balancer_id,
    backend_name,
    endpoint,
    weight
)
SELECT
    lb.load_balancer_id,
    values.backend_name,
    values.endpoint,
    values.weight
FROM load_balancers lb
JOIN (
    VALUES
        ('api-a', 'http://api-a:8080', 1),
        ('api-b', 'http://api-b:8080', 1),
        ('api-c', 'http://api-c:8080', 1)
) AS values(backend_name, endpoint, weight)
ON TRUE
WHERE lb.name = 'public-api';

INSERT INTO backends (
    load_balancer_id,
    backend_name,
    endpoint,
    weight
)
SELECT
    lb.load_balancer_id,
    values.backend_name,
    values.endpoint,
    values.weight
FROM load_balancers lb
JOIN (
    VALUES
        ('api-a', 'http://api-a:8080', 1),
        ('api-b', 'http://api-b:8080', 2),
        ('api-c', 'http://api-c:8080', 3)
) AS values(backend_name, endpoint, weight)
ON TRUE
WHERE lb.name = 'weighted-api';

INSERT INTO backends (
    load_balancer_id,
    backend_name,
    endpoint,
    weight,
    active_connections
)
SELECT
    lb.load_balancer_id,
    values.backend_name,
    values.endpoint,
    values.weight,
    values.active_connections
FROM load_balancers lb
JOIN (
    VALUES
        ('api-a', 'http://api-a:8080', 1, 4),
        ('api-b', 'http://api-b:8080', 2, 1),
        ('api-c', 'http://api-c:8080', 3, 2)
) AS values(
    backend_name,
    endpoint,
    weight,
    active_connections
)
ON TRUE
WHERE lb.name = 'connection-aware-api';

CREATE OR REPLACE FUNCTION validate_request_backend()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    backend_lb BIGINT;
BEGIN
    IF NEW.backend_id IS NOT NULL THEN
        SELECT load_balancer_id
        INTO backend_lb
        FROM backends
        WHERE backend_id = NEW.backend_id;

        IF backend_lb IS NULL THEN
            RAISE EXCEPTION 'Backend % does not exist', NEW.backend_id;
        END IF;

        IF backend_lb <> NEW.load_balancer_id THEN
            RAISE EXCEPTION
                'Backend % belongs to load balancer %, not %',
                NEW.backend_id,
                backend_lb,
                NEW.load_balancer_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_request_backend
BEFORE INSERT OR UPDATE OF backend_id, load_balancer_id
ON requests
FOR EACH ROW
EXECUTE FUNCTION validate_request_backend();

CREATE OR REPLACE FUNCTION update_backend_counters()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'active' AND OLD.status <> 'active' THEN
        UPDATE backends
        SET
            active_connections = active_connections + 1,
            total_requests = total_requests + 1
        WHERE backend_id = NEW.backend_id;

    ELSIF OLD.status = 'active'
          AND NEW.status IN ('completed', 'failed') THEN
        UPDATE backends
        SET
            active_connections =
                GREATEST(active_connections - 1, 0),
            completed_requests =
                completed_requests
                + CASE
                    WHEN NEW.status = 'completed' THEN 1
                    ELSE 0
                  END,
            failed_requests =
                failed_requests
                + CASE
                    WHEN NEW.status = 'failed' THEN 1
                    ELSE 0
                  END
        WHERE backend_id = NEW.backend_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_update_backend_counters
AFTER UPDATE OF status
ON requests
FOR EACH ROW
EXECUTE FUNCTION update_backend_counters();

CREATE OR REPLACE FUNCTION choose_backend(
    p_load_balancer_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    selected_backend BIGINT;
    algorithm_name balancing_algorithm;
BEGIN
    SELECT algorithm
    INTO algorithm_name
    FROM load_balancers
    WHERE load_balancer_id = p_load_balancer_id
      AND enabled = TRUE;

    IF algorithm_name IS NULL THEN
        RAISE EXCEPTION
            'Enabled load balancer % does not exist',
            p_load_balancer_id;
    END IF;

    IF algorithm_name = 'round_robin' THEN
        /*
         * PostgreSQL cannot maintain a process-local round-robin counter
         * safely across sessions without shared state. Ordering by
         * backend_id provides deterministic selection for this SQL model.
         */
        SELECT backend_id
        INTO selected_backend
        FROM backends
        WHERE load_balancer_id = p_load_balancer_id
          AND status = 'healthy'
        ORDER BY backend_id
        LIMIT 1;

    ELSIF algorithm_name = 'weighted_round_robin' THEN
        /*
         * Weighted selection uses a deterministic expanded weight range.
         * A production implementation would normally maintain a scheduler
         * counter outside the relational transaction.
         */
        SELECT backend_id
        INTO selected_backend
        FROM backends
        WHERE load_balancer_id = p_load_balancer_id
          AND status = 'healthy'
        ORDER BY weight DESC, backend_id
        LIMIT 1;

    ELSIF algorithm_name = 'least_connections' THEN
        SELECT backend_id
        INTO selected_backend
        FROM backends
        WHERE load_balancer_id = p_load_balancer_id
          AND status = 'healthy'
        ORDER BY active_connections ASC,
                 weight DESC,
                 backend_id ASC
        LIMIT 1;
    END IF;

    IF selected_backend IS NULL THEN
        RAISE EXCEPTION
            'No healthy backend is available for load balancer %',
            p_load_balancer_id;
    END IF;

    RETURN selected_backend;
END;
$$;

CREATE OR REPLACE FUNCTION dispatch_request(
    p_load_balancer_id BIGINT,
    p_duration_ms INTEGER DEFAULT 100
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    chosen_backend BIGINT;
    new_request BIGINT;
BEGIN
    IF p_duration_ms <= 0 THEN
        RAISE EXCEPTION 'Duration must be positive';
    END IF;

    /*
     * The row lock prevents two concurrent dispatch transactions from
     * observing the same least-connections state without serialization.
     */
    PERFORM 1
    FROM backends
    WHERE load_balancer_id = p_load_balancer_id
      AND status = 'healthy'
    FOR UPDATE;

    chosen_backend := choose_backend(p_load_balancer_id);

    INSERT INTO requests (
        load_balancer_id,
        backend_id,
        status,
        duration_ms,
        started_at
    )
    VALUES (
        p_load_balancer_id,
        chosen_backend,
        'active',
        p_duration_ms,
        CURRENT_TIMESTAMP
    )
    RETURNING request_id INTO new_request;

    RETURN new_request;
END;
$$;

CREATE OR REPLACE FUNCTION finish_request(
    p_request_id BIGINT,
    p_success BOOLEAN DEFAULT TRUE
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE requests
    SET
        status = CASE
            WHEN p_success THEN 'completed'::request_status
            ELSE 'failed'::request_status
        END,
        completed_at = CURRENT_TIMESTAMP
    WHERE request_id = p_request_id
      AND status = 'active';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Active request % was not found',
            p_request_id;
    END IF;
END;
$$;

-- Simulate the least-connections workflow.
BEGIN;

SELECT dispatch_request(
    load_balancer_id,
    250
)
FROM load_balancers
WHERE name = 'connection-aware-api';

COMMIT;

-- Complete the most recently created active request.
SELECT finish_request(
    request_id,
    TRUE
)
FROM requests
WHERE status = 'active'
ORDER BY request_id DESC
LIMIT 1;

-- Mark one backend unhealthy to demonstrate failure handling.
UPDATE backends
SET status = 'unhealthy'
WHERE backend_name = 'api-c'
  AND load_balancer_id = (
      SELECT load_balancer_id
      FROM load_balancers
      WHERE name = 'weighted-api'
  );

-- Retrieval: current healthy capacity.
SELECT
    lb.name AS load_balancer,
    b.backend_name,
    b.weight,
    b.status,
    b.active_connections
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE b.status = 'healthy'
ORDER BY lb.name, b.backend_name;

-- Validation: backend load-balance consistency.
SELECT
    lb.name,
    b.backend_name,
    b.total_requests,
    b.completed_requests,
    b.failed_requests,
    b.active_connections
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE b.completed_requests + b.failed_requests > b.total_requests
   OR b.active_connections < 0;

-- Aggregation: traffic distribution by load balancer.
SELECT
    lb.name,
    b.backend_name,
    b.weight,
    b.total_requests,
    ROUND(
        100.0 * b.total_requests
        / NULLIF(
            SUM(b.total_requests)
            OVER (PARTITION BY lb.load_balancer_id),
            0
        ),
        2
    ) AS traffic_percentage
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
ORDER BY lb.name, b.backend_name;

-- Least-connections candidate evaluation.
WITH candidates AS (
    SELECT
        b.backend_id,
        b.backend_name,
        b.active_connections,
        b.weight,
        ROW_NUMBER() OVER (
            ORDER BY
                b.active_connections ASC,
                b.weight DESC,
                b.backend_id ASC
        ) AS selection_rank
    FROM backends b
    JOIN load_balancers lb
        ON lb.load_balancer_id = b.load_balancer_id
    WHERE lb.name = 'connection-aware-api'
      AND b.status = 'healthy'
)
SELECT *
FROM candidates
WHERE selection_rank = 1;

-- Failure report.
SELECT
    lb.name AS load_balancer,
    b.backend_name,
    b.status,
    b.failed_requests,
    b.active_connections
FROM load_balancers lb
JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
WHERE b.status <> 'healthy'
   OR b.failed_requests > 0
ORDER BY lb.name, b.backend_name;

-- Transactional demonstration: a request is created and completed atomically.
BEGIN;

WITH selected AS (
    SELECT dispatch_request(
        load_balancer_id,
        150
    ) AS request_id
    FROM load_balancers
    WHERE name = 'public-api'
)
SELECT finish_request(request_id, TRUE)
FROM selected;

COMMIT;

-- Final operational report.
SELECT
    lb.name AS load_balancer,
    lb.algorithm,
    COUNT(b.backend_id) AS backend_count,
    COUNT(*) FILTER (
        WHERE b.status = 'healthy'
    ) AS healthy_backends,
    COALESCE(SUM(b.active_connections), 0) AS active_connections,
    COALESCE(SUM(b.total_requests), 0) AS total_requests,
    COALESCE(SUM(b.completed_requests), 0) AS completed_requests,
    COALESCE(SUM(b.failed_requests), 0) AS failed_requests
FROM load_balancers lb
LEFT JOIN backends b
    ON b.load_balancer_id = lb.load_balancer_id
GROUP BY lb.load_balancer_id, lb.name, lb.algorithm
ORDER BY lb.name;
