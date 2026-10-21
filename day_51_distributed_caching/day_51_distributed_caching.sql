DROP SCHEMA IF EXISTS distributed_cache_demo CASCADE;
CREATE SCHEMA distributed_cache_demo;
SET search_path TO distributed_cache_demo;

-- The relational model separates cache infrastructure, application data,
-- cache policy, and operational observations.

CREATE TYPE backend_type AS ENUM ('redis', 'memcached');
CREATE TYPE node_state AS ENUM ('healthy', 'failed', 'draining');
CREATE TYPE cache_policy AS ENUM ('cache_aside', 'write_through');
CREATE TYPE pr_status AS ENUM ('draft', 'open', 'closed', 'merged');

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (repository_name <> ''),
    CHECK (default_branch <> '')
);

CREATE TABLE cache_clusters (
    cluster_id BIGSERIAL PRIMARY KEY,
    cluster_name TEXT NOT NULL UNIQUE,
    policy cache_policy NOT NULL,
    hash_algorithm TEXT NOT NULL DEFAULT 'consistent_hash',
    virtual_nodes INTEGER NOT NULL DEFAULT 128,
    replication_factor INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (virtual_nodes > 0),
    CHECK (replication_factor > 0)
);

CREATE TABLE cache_nodes (
    node_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES cache_clusters(cluster_id)
        ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    backend backend_type NOT NULL,
    endpoint TEXT NOT NULL,
    state node_state NOT NULL DEFAULT 'healthy',
    capacity_entries INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cluster_id, node_name),
    UNIQUE (cluster_id, endpoint),
    CHECK (node_name <> ''),
    CHECK (endpoint <> ''),
    CHECK (capacity_entries > 0)
);

CREATE TABLE applications (
    application_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    application_name TEXT NOT NULL UNIQUE,
    source_of_truth TEXT NOT NULL,
    UNIQUE (repository_id, application_name),
    CHECK (source_of_truth <> '')
);

CREATE TABLE cache_keys (
    cache_key_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES cache_clusters(cluster_id)
        ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    owner_node_id BIGINT REFERENCES cache_nodes(node_id)
        ON DELETE SET NULL,
    version BIGINT NOT NULL DEFAULT 1,
    value_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    UNIQUE (cluster_id, cache_key),
    CHECK (version > 0),
    CHECK (value_hash <> ''),
    CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE TABLE cache_operations (
    operation_id BIGSERIAL PRIMARY KEY,
    cache_key_id BIGINT REFERENCES cache_keys(cache_key_id)
        ON DELETE SET NULL,
    node_id BIGINT REFERENCES cache_nodes(node_id)
        ON DELETE SET NULL,
    operation TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    latency_ms NUMERIC(12,3),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    failure_reason TEXT,
    CHECK (operation IN (
        'get',
        'set',
        'delete',
        'invalidate',
        'load',
        'refresh'
    )),
    CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CHECK (success OR failure_reason IS NOT NULL)
);

CREATE TABLE cache_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    cluster_id BIGINT NOT NULL REFERENCES cache_clusters(cluster_id)
        ON DELETE CASCADE,
    policy_name TEXT NOT NULL,
    default_ttl_seconds INTEGER NOT NULL,
    stale_read_allowed BOOLEAN NOT NULL DEFAULT false,
    negative_caching_allowed BOOLEAN NOT NULL DEFAULT false,
    max_key_length INTEGER NOT NULL DEFAULT 512,
    UNIQUE (cluster_id, policy_name),
    CHECK (default_ttl_seconds > 0),
    CHECK (max_key_length BETWEEN 1 AND 4096)
);

-- Redis-style clusters commonly use multiple logical nodes and virtual
-- positions. Memcached is represented separately because its typical model
-- is an application-side distributed key/value cache without persistence.
INSERT INTO repositories (repository_name, default_branch)
VALUES
    ('commerce-platform', 'main'),
    ('analytics-platform', 'main');

INSERT INTO cache_clusters (
    cluster_name,
    policy,
    virtual_nodes,
    replication_factor
)
VALUES
    ('commerce-redis', 'cache_aside', 128, 2),
    ('analytics-memcached', 'cache_aside', 128, 1);

INSERT INTO cache_nodes (
    cluster_id,
    node_name,
    backend,
    endpoint,
    state,
    capacity_entries
)
VALUES
    (1, 'redis-a', 'redis', 'redis-a.internal:6379', 'healthy', 100000),
    (1, 'redis-b', 'redis', 'redis-b.internal:6379', 'healthy', 100000),
    (1, 'redis-c', 'redis', 'redis-c.internal:6379', 'draining', 100000),
    (2, 'memcached-a', 'memcached', 'memcached-a.internal:11211', 'healthy', 200000),
    (2, 'memcached-b', 'memcached', 'memcached-b.internal:11211', 'failed', 200000);

INSERT INTO applications (
    repository_id,
    application_name,
    source_of_truth
)
VALUES
    (1, 'commerce-api', 'postgresql'),
    (2, 'analytics-api', 'postgresql');

INSERT INTO cache_policies (
    cluster_id,
    policy_name,
    default_ttl_seconds,
    stale_read_allowed,
    negative_caching_allowed,
    max_key_length
)
VALUES
    (1, 'product-cache', 60, false, false, 512),
    (2, 'analytics-summary', 300, true, false, 512);

INSERT INTO cache_keys (
    cluster_id,
    cache_key,
    owner_node_id,
    version,
    value_hash,
    expires_at
)
VALUES
    (
        1,
        'product:p100',
        1,
        7,
        'sha256-product-p100-v7',
        now() + interval '60 seconds'
    ),
    (
        1,
        'product:p200',
        2,
        4,
        'sha256-product-p200-v4',
        now() + interval '60 seconds'
    ),
    (
        2,
        'analytics:daily:2026-10-21',
        4,
        3,
        'sha256-daily-summary-v3',
        now() + interval '5 minutes'
    ),
    (
        1,
        'product:p300',
        3,
        2,
        'sha256-product-p300-v2',
        now() + interval '60 seconds'
    );

-- A failed node should not be considered a valid owner for new writes.
CREATE OR REPLACE FUNCTION prevent_failed_node_assignment()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    target_state node_state;
BEGIN
    IF NEW.owner_node_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT state
    INTO target_state
    FROM cache_nodes
    WHERE node_id = NEW.owner_node_id;

    IF target_state IN ('failed', 'draining') THEN
        RAISE EXCEPTION
            'Cache key % cannot be assigned to % node %',
            NEW.cache_key,
            target_state,
            NEW.owner_node_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER validate_cache_owner
BEFORE INSERT OR UPDATE OF owner_node_id
ON cache_keys
FOR EACH ROW
EXECUTE FUNCTION prevent_failed_node_assignment();

-- Prevent successful cache operations against failed nodes.
CREATE OR REPLACE FUNCTION validate_cache_operation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    current_state node_state;
BEGIN
    IF NEW.node_id IS NULL OR NOT NEW.success THEN
        RETURN NEW;
    END IF;

    SELECT state
    INTO current_state
    FROM cache_nodes
    WHERE node_id = NEW.node_id;

    IF current_state <> 'healthy' THEN
        RAISE EXCEPTION
            'Successful operation cannot target node % in state %',
            NEW.node_id,
            current_state;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER validate_operation_node
BEFORE INSERT OR UPDATE
ON cache_operations
FOR EACH ROW
EXECUTE FUNCTION validate_cache_operation();

-- Useful indexes support operational lookups rather than every possible query.
CREATE INDEX idx_cache_keys_active_expiry
ON cache_keys (cluster_id, expires_at)
WHERE invalidated_at IS NULL;

CREATE INDEX idx_cache_operations_time
ON cache_operations (occurred_at DESC);

CREATE INDEX idx_cache_operations_node_operation
ON cache_operations (node_id, operation, occurred_at DESC);

CREATE INDEX idx_cache_nodes_cluster_state
ON cache_nodes (cluster_id, state);

INSERT INTO cache_operations (
    cache_key_id,
    node_id,
    operation,
    success,
    latency_ms
)
SELECT
    cache_key_id,
    owner_node_id,
    'get',
    true,
    1.42
FROM cache_keys
WHERE cache_key = 'product:p100';

INSERT INTO cache_operations (
    cache_key_id,
    node_id,
    operation,
    success,
    latency_ms
)
SELECT
    cache_key_id,
    owner_node_id,
    'set',
    true,
    2.17
FROM cache_keys
WHERE cache_key = 'product:p200';

INSERT INTO cache_operations (
    cache_key_id,
    node_id,
    operation,
    success,
    latency_ms,
    failure_reason
)
SELECT
    cache_key_id,
    5,
    'get',
    false,
    25.30,
    'Node unavailable; request fell back to PostgreSQL'
FROM cache_keys
WHERE cache_key = 'analytics:daily:2026-10-21';

INSERT INTO cache_operations (
    cache_key_id,
    node_id,
    operation,
    success,
    latency_ms
)
SELECT
    cache_key_id,
    owner_node_id,
    'invalidate',
    true,
    1.10
FROM cache_keys
WHERE cache_key = 'product:p100';

-- Explicit transaction demonstrates atomic source-of-truth update followed
-- by cache invalidation metadata. A real application would update the
-- authoritative database and cache service according to its consistency
-- strategy rather than relying on one database transaction to span Redis.
BEGIN;

UPDATE cache_keys
SET
    version = version + 1,
    invalidated_at = now()
WHERE cluster_id = 1
  AND cache_key = 'product:p100';

INSERT INTO cache_operations (
    cache_key_id,
    node_id,
    operation,
    success,
    latency_ms
)
SELECT
    cache_key_id,
    owner_node_id,
    'invalidate',
    true,
    1.05
FROM cache_keys
WHERE cluster_id = 1
  AND cache_key = 'product:p100';

COMMIT;

-- Active, non-expired cache entries.
SELECT
    c.cluster_name,
    k.cache_key,
    n.node_name,
    n.backend,
    k.version,
    k.expires_at
FROM cache_keys AS k
JOIN cache_clusters AS c
    ON c.cluster_id = k.cluster_id
LEFT JOIN cache_nodes AS n
    ON n.node_id = k.owner_node_id
WHERE k.invalidated_at IS NULL
  AND (k.expires_at IS NULL OR k.expires_at > now())
ORDER BY c.cluster_name, k.cache_key;

-- Hit/miss rates by node.
WITH operation_counts AS (
    SELECT
        node_id,
        COUNT(*) FILTER (
            WHERE operation = 'get' AND success
        ) AS successful_gets,
        COUNT(*) FILTER (
            WHERE operation = 'get' AND NOT success
        ) AS failed_gets
    FROM cache_operations
    GROUP BY node_id
)
SELECT
    n.node_name,
    n.backend,
    COALESCE(o.successful_gets, 0) AS successful_gets,
    COALESCE(o.failed_gets, 0) AS failed_gets,
    CASE
        WHEN COALESCE(o.successful_gets, 0)
           + COALESCE(o.failed_gets, 0) = 0
        THEN 0
        ELSE ROUND(
            100.0 * o.successful_gets /
            (
                o.successful_gets
                + o.failed_gets
            ),
            2
        )
    END AS success_percentage
FROM cache_nodes AS n
LEFT JOIN operation_counts AS o
    ON o.node_id = n.node_id
ORDER BY n.node_name;

-- Detect keys that are expired but have not yet been invalidated.
SELECT
    c.cluster_name,
    k.cache_key,
    k.owner_node_id,
    k.expires_at
FROM cache_keys AS k
JOIN cache_clusters AS c
    ON c.cluster_id = k.cluster_id
WHERE k.invalidated_at IS NULL
  AND k.expires_at IS NOT NULL
  AND k.expires_at <= now()
ORDER BY k.expires_at;

-- Identify failed nodes that still have assigned cache keys.
SELECT
    n.node_name,
    n.backend,
    n.state,
    COUNT(k.cache_key_id) AS assigned_keys
FROM cache_nodes AS n
LEFT JOIN cache_keys AS k
    ON k.owner_node_id = n.node_id
    AND k.invalidated_at IS NULL
WHERE n.state = 'failed'
GROUP BY n.node_id, n.node_name, n.backend, n.state
ORDER BY assigned_keys DESC;

-- Average latency by operation and backend.
SELECT
    n.backend,
    o.operation,
    COUNT(*) AS operations,
    ROUND(AVG(o.latency_ms), 2) AS average_latency_ms
FROM cache_operations AS o
JOIN cache_nodes AS n
    ON n.node_id = o.node_id
WHERE o.latency_ms IS NOT NULL
GROUP BY n.backend, o.operation
ORDER BY n.backend, o.operation;

-- Policy report combines cluster configuration with operational state.
SELECT
    c.cluster_name,
    c.policy,
    c.hash_algorithm,
    c.virtual_nodes,
    c.replication_factor,
    p.policy_name,
    p.default_ttl_seconds,
    p.stale_read_allowed,
    COUNT(n.node_id) AS node_count,
    COUNT(*) FILTER (WHERE n.state = 'healthy') AS healthy_nodes,
    COUNT(*) FILTER (WHERE n.state = 'failed') AS failed_nodes
FROM cache_clusters AS c
JOIN cache_policies AS p
    ON p.cluster_id = c.cluster_id
LEFT JOIN cache_nodes AS n
    ON n.cluster_id = c.cluster_id
GROUP BY
    c.cluster_id,
    c.cluster_name,
    c.policy,
    c.hash_algorithm,
    c.virtual_nodes,
    c.replication_factor,
    p.policy_id,
    p.policy_name,
    p.default_ttl_seconds,
    p.stale_read_allowed
ORDER BY c.cluster_name;
