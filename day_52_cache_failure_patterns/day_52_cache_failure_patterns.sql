DROP SCHEMA IF EXISTS cache_failure_patterns CASCADE;
CREATE SCHEMA cache_failure_patterns;
SET search_path TO cache_failure_patterns;

-- PostgreSQL model:
-- A cache failure is treated as an operational state rather than merely
-- as a cache miss. The schema records keys, source objects, cache entries,
-- refresh coordination, status checks, and policy decisions.

CREATE TYPE cache_state AS ENUM (
    'FRESH',
    'STALE',
    'NEGATIVE',
    'EXPIRED'
);

CREATE TYPE refresh_state AS ENUM (
    'PENDING',
    'RUNNING',
    'SUCCEEDED',
    'FAILED'
);

CREATE TYPE failure_pattern AS ENUM (
    'STAMPede',
    'PENETRATION',
    'AVALANCHE'
);

CREATE TABLE repository (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    environment TEXT NOT NULL
        CHECK (environment IN ('development', 'staging', 'production')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE cache_namespace (
    namespace_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id) ON DELETE CASCADE,
    namespace_name TEXT NOT NULL,
    default_ttl_seconds INTEGER NOT NULL
        CHECK (default_ttl_seconds > 0),
    negative_ttl_seconds INTEGER NOT NULL
        CHECK (negative_ttl_seconds > 0),
    jitter_ratio NUMERIC(5,4) NOT NULL
        CHECK (jitter_ratio >= 0 AND jitter_ratio <= 1),
    stale_grace_seconds INTEGER NOT NULL
        CHECK (stale_grace_seconds >= 0),
    reject_unknown_keys BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (repository_id, namespace_name)
);

CREATE TABLE source_object (
    source_object_id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL
        REFERENCES cache_namespace(namespace_id) ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    payload JSONB,
    exists_in_source BOOLEAN NOT NULL DEFAULT TRUE,
    version BIGINT NOT NULL DEFAULT 1
        CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (namespace_id, cache_key)
);

CREATE TABLE cache_entry (
    cache_entry_id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL
        REFERENCES cache_namespace(namespace_id) ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    source_version BIGINT,
    state cache_state NOT NULL,
    payload JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    stale_until TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    refreshed_at TIMESTAMPTZ,
    CHECK (stale_until >= expires_at),
    UNIQUE (namespace_id, cache_key)
);

CREATE TABLE refresh_request (
    refresh_request_id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL
        REFERENCES cache_namespace(namespace_id) ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    state refresh_state NOT NULL,
    failure_reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK (
        (state = 'FAILED' AND failure_reason IS NOT NULL)
        OR state <> 'FAILED'
    )
);

CREATE TABLE failure_event (
    failure_event_id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL
        REFERENCES cache_namespace(namespace_id) ON DELETE CASCADE,
    pattern failure_pattern NOT NULL,
    cache_key TEXT,
    request_count INTEGER NOT NULL
        CHECK (request_count >= 0),
    backend_read_count INTEGER NOT NULL
        CHECK (backend_read_count >= 0),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE cache_request (
    request_id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL
        REFERENCES cache_namespace(namespace_id) ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    outcome cache_state NOT NULL,
    backend_called BOOLEAN NOT NULL,
    latency_ms NUMERIC(12,3) NOT NULL
        CHECK (latency_ms >= 0),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_cache_entry_expiry
    ON cache_entry(namespace_id, expires_at);

CREATE INDEX idx_cache_request_key_time
    ON cache_request(namespace_id, cache_key, requested_at DESC);

CREATE INDEX idx_failure_event_pattern_time
    ON failure_event(pattern, observed_at DESC);

-- Source lookup is the primary backend simulation operation.
CREATE OR REPLACE FUNCTION load_source_object(
    p_namespace_id BIGINT,
    p_cache_key TEXT
)
RETURNS JSONB
LANGUAGE SQL
STABLE
AS $$
    SELECT payload
    FROM source_object
    WHERE namespace_id = p_namespace_id
      AND cache_key = p_cache_key
      AND exists_in_source = TRUE;
$$;

-- Jittered expiration prevents many keys from sharing exactly the same
-- expiration timestamp.
CREATE OR REPLACE FUNCTION calculate_expiration(
    p_base_seconds INTEGER,
    p_jitter_ratio NUMERIC,
    p_now TIMESTAMPTZ DEFAULT clock_timestamp()
)
RETURNS TIMESTAMPTZ
LANGUAGE plpgsql
AS $$
DECLARE
    v_jitter NUMERIC;
    v_seconds NUMERIC;
BEGIN
    v_jitter :=
        (random() * 2.0 - 1.0)
        * p_base_seconds
        * p_jitter_ratio;

    v_seconds := GREATEST(1.0, p_base_seconds + v_jitter);

    RETURN p_now + make_interval(secs => v_seconds);
END;
$$;

-- This function models a cache refresh with negative caching.
-- SELECT ... FOR UPDATE prevents two database workers from independently
-- deciding that the same cache entry needs initialization.
CREATE OR REPLACE FUNCTION refresh_cache_entry(
    p_namespace_id BIGINT,
    p_cache_key TEXT
)
RETURNS cache_state
LANGUAGE plpgsql
AS $$
DECLARE
    v_namespace cache_namespace%ROWTYPE;
    v_source JSONB;
    v_exists BOOLEAN;
    v_expires TIMESTAMPTZ;
    v_stale_until TIMESTAMPTZ;
    v_state cache_state;
BEGIN
    SELECT *
    INTO v_namespace
    FROM cache_namespace
    WHERE namespace_id = p_namespace_id
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown cache namespace %', p_namespace_id;
    END IF;

    SELECT payload, exists_in_source
    INTO v_source, v_exists
    FROM source_object
    WHERE namespace_id = p_namespace_id
      AND cache_key = p_cache_key;

    IF COALESCE(v_exists, FALSE) THEN
        v_state := 'FRESH';

        v_expires := calculate_expiration(
            v_namespace.default_ttl_seconds,
            v_namespace.jitter_ratio
        );

        v_stale_until :=
            v_expires
            + make_interval(
                secs => v_namespace.stale_grace_seconds
            );
    ELSE
        -- Negative caching prevents repeated requests for a missing key
        -- from becoming sustained backend traffic.
        v_state := 'NEGATIVE';

        v_expires :=
            clock_timestamp()
            + make_interval(
                secs => v_namespace.negative_ttl_seconds
            );

        v_stale_until := v_expires;
        v_source := NULL;
    END IF;

    INSERT INTO cache_entry (
        namespace_id,
        cache_key,
        source_version,
        state,
        payload,
        expires_at,
        stale_until,
        refreshed_at
    )
    SELECT
        p_namespace_id,
        p_cache_key,
        version,
        v_state,
        v_source,
        v_expires,
        v_stale_until,
        clock_timestamp()
    FROM source_object
    WHERE namespace_id = p_namespace_id
      AND cache_key = p_cache_key
    ON CONFLICT (namespace_id, cache_key)
    DO UPDATE SET
        source_version = EXCLUDED.source_version,
        state = EXCLUDED.state,
        payload = EXCLUDED.payload,
        expires_at = EXCLUDED.expires_at,
        stale_until = EXCLUDED.stale_until,
        refreshed_at = EXCLUDED.refreshed_at;

    IF NOT FOUND THEN
        INSERT INTO cache_entry (
            namespace_id,
            cache_key,
            state,
            payload,
            expires_at,
            stale_until,
            refreshed_at
        )
        VALUES (
            p_namespace_id,
            p_cache_key,
            'NEGATIVE',
            NULL,
            v_expires,
            v_stale_until,
            clock_timestamp()
        )
        ON CONFLICT (namespace_id, cache_key)
        DO UPDATE SET
            state = EXCLUDED.state,
            payload = NULL,
            expires_at = EXCLUDED.expires_at,
            stale_until = EXCLUDED.stale_until,
            refreshed_at = EXCLUDED.refreshed_at;
    END IF;

    RETURN v_state;
END;
$$;

CREATE OR REPLACE FUNCTION evaluate_cache_key(
    p_namespace_id BIGINT,
    p_cache_key TEXT
)
RETURNS TABLE (
    key_name TEXT,
    state cache_state,
    should_call_backend BOOLEAN,
    serve_stale BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_policy cache_namespace%ROWTYPE;
    v_entry cache_entry%ROWTYPE;
    v_valid_key BOOLEAN;
BEGIN
    SELECT *
    INTO v_policy
    FROM cache_namespace
    WHERE namespace_id = p_namespace_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown namespace %', p_namespace_id;
    END IF;

    v_valid_key :=
        p_cache_key ~ '^[A-Za-z0-9:_-]{1,100}$';

    IF NOT v_valid_key THEN
        RETURN QUERY
        SELECT
            p_cache_key,
            'EXPIRED'::cache_state,
            FALSE,
            FALSE,
            'Rejected by key-admission validation';
        RETURN;
    END IF;

    IF v_policy.reject_unknown_keys
       AND NOT EXISTS (
            SELECT 1
            FROM source_object
            WHERE namespace_id = p_namespace_id
              AND cache_key = p_cache_key
       )
       AND NOT EXISTS (
            SELECT 1
            FROM cache_entry
            WHERE namespace_id = p_namespace_id
              AND cache_key = p_cache_key
              AND state = 'NEGATIVE'
       )
    THEN
        RETURN QUERY
        SELECT
            p_cache_key,
            'EXPIRED'::cache_state,
            FALSE,
            FALSE,
            'Rejected as unknown key';
        RETURN;
    END IF;

    SELECT *
    INTO v_entry
    FROM cache_entry
    WHERE namespace_id = p_namespace_id
      AND cache_key = p_cache_key;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            p_cache_key,
            'EXPIRED'::cache_state,
            TRUE,
            FALSE,
            'Cache entry does not exist';
        RETURN;
    END IF;

    IF v_entry.expires_at > clock_timestamp() THEN
        RETURN QUERY
        SELECT
            p_cache_key,
            v_entry.state,
            FALSE,
            FALSE,
            'Fresh cache entry';
        RETURN;
    END IF;

    IF v_entry.stale_until > clock_timestamp() THEN
        RETURN QUERY
        SELECT
            p_cache_key,
            'STALE'::cache_state,
            FALSE,
            TRUE,
            'Serve stale while refresh occurs';
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        p_cache_key,
        'EXPIRED'::cache_state,
        TRUE,
        FALSE,
        'Cache entry expired';
END;
$$;

CREATE OR REPLACE VIEW cache_health_report AS
WITH request_stats AS (
    SELECT
        namespace_id,
        cache_key,
        count(*) AS requests,
        count(*) FILTER (
            WHERE backend_called
        ) AS backend_calls,
        avg(latency_ms) AS avg_latency_ms
    FROM cache_request
    WHERE requested_at >= clock_timestamp() - interval '15 minutes'
    GROUP BY namespace_id, cache_key
),
event_stats AS (
    SELECT
        namespace_id,
        pattern,
        sum(request_count) AS affected_requests,
        sum(backend_read_count) AS affected_backend_reads
    FROM failure_event
    WHERE observed_at >= clock_timestamp() - interval '15 minutes'
    GROUP BY namespace_id, pattern
)
SELECT
    n.namespace_name,
    rs.cache_key,
    rs.requests,
    rs.backend_calls,
    round(rs.avg_latency_ms, 2) AS avg_latency_ms,
    es.pattern,
    es.affected_requests,
    es.affected_backend_reads
FROM request_stats rs
JOIN cache_namespace n
    ON n.namespace_id = rs.namespace_id
LEFT JOIN event_stats es
    ON es.namespace_id = rs.namespace_id
ORDER BY rs.requests DESC;

INSERT INTO repository (
    repository_name,
    environment
)
VALUES
    ('checkout-service', 'production'),
    ('catalog-service', 'production');

INSERT INTO cache_namespace (
    repository_id,
    namespace_name,
    default_ttl_seconds,
    negative_ttl_seconds,
    jitter_ratio,
    stale_grace_seconds,
    reject_unknown_keys
)
SELECT
    repository_id,
    'product-cache',
    60,
    10,
    0.20,
    30,
    TRUE
FROM repository
WHERE repository_name = 'catalog-service';

INSERT INTO source_object (
    namespace_id,
    cache_key,
    payload,
    exists_in_source
)
SELECT
    namespace_id,
    'product:100',
    '{"name":"Keyboard","price":49.00}'::jsonb,
    TRUE
FROM cache_namespace
WHERE namespace_name = 'product-cache';

INSERT INTO source_object (
    namespace_id,
    cache_key,
    payload,
    exists_in_source
)
SELECT
    namespace_id,
    'product:101',
    '{"name":"Mouse","price":29.00}'::jsonb,
    TRUE
FROM cache_namespace
WHERE namespace_name = 'product-cache';

-- Missing objects are represented explicitly to make negative-cache behavior
-- observable and auditable.
INSERT INTO source_object (
    namespace_id,
    cache_key,
    payload,
    exists_in_source
)
SELECT
    namespace_id,
    'product:404',
    NULL,
    FALSE
FROM cache_namespace
WHERE namespace_name = 'product-cache';

-- Initial population.
SELECT refresh_cache_entry(
    namespace_id,
    'product:100'
)
FROM cache_namespace
WHERE namespace_name = 'product-cache';

SELECT refresh_cache_entry(
    namespace_id,
    'product:101'
)
FROM cache_namespace
WHERE namespace_name = 'product-cache';

SELECT refresh_cache_entry(
    namespace_id,
    'product:404'
)
FROM cache_namespace
WHERE namespace_name = 'product-cache';

-- Penetration evaluation.
SELECT *
FROM evaluate_cache_key(
    (
        SELECT namespace_id
        FROM cache_namespace
        WHERE namespace_name = 'product-cache'
    ),
    'product:404'
);

SELECT *
FROM evaluate_cache_key(
    (
        SELECT namespace_id
        FROM cache_namespace
        WHERE namespace_name = 'product-cache'
    ),
    '../system-table'
);

-- Stampede evidence: many requests for one expired hot key.
INSERT INTO cache_request (
    namespace_id,
    cache_key,
    outcome,
    backend_called,
    latency_ms
)
SELECT
    namespace_id,
    'product:100',
    'EXPIRED',
    TRUE,
    85.0
FROM cache_namespace
WHERE namespace_name = 'product-cache';

INSERT INTO failure_event (
    namespace_id,
    pattern,
    cache_key,
    request_count,
    backend_read_count,
    details
)
SELECT
    namespace_id,
    'STAMPede',
    'product:100',
    250,
    250,
    '{"cause":"synchronized expiry","mitigation":"single-flight"}'::jsonb
FROM cache_namespace
WHERE namespace_name = 'product-cache';

-- Avalanche evidence: many different keys expire in one observation window.
INSERT INTO failure_event (
    namespace_id,
    pattern,
    cache_key,
    request_count,
    backend_read_count,
    details
)
SELECT
    namespace_id,
    'AVALANCHE',
    NULL,
    5000,
    4300,
    '{"cause":"correlated expiration","mitigation":"TTL jitter and stale grace"}'::jsonb
FROM cache_namespace
WHERE namespace_name = 'product-cache';

-- Penetration evidence records repeated misses that reached the source.
INSERT INTO failure_event (
    namespace_id,
    pattern,
    cache_key,
    request_count,
    backend_read_count,
    details
)
SELECT
    namespace_id,
    'PENETRATION',
    'product:404',
    1000,
    1,
    '{"cause":"nonexistent object","mitigation":"negative caching"}'::jsonb
FROM cache_namespace
WHERE namespace_name = 'product-cache';

-- Transactional invalidation after a source-of-truth update.
BEGIN;

UPDATE source_object
SET
    payload = '{"name":"Keyboard Pro","price":59.00}'::jsonb,
    version = version + 1,
    updated_at = clock_timestamp()
WHERE cache_key = 'product:100'
  AND namespace_id = (
      SELECT namespace_id
      FROM cache_namespace
      WHERE namespace_name = 'product-cache'
  );

UPDATE cache_entry
SET
    state = 'EXPIRED',
    expires_at = clock_timestamp(),
    stale_until = clock_timestamp()
WHERE cache_key = 'product:100'
  AND namespace_id = (
      SELECT namespace_id
      FROM cache_namespace
      WHERE namespace_name = 'product-cache'
  );

COMMIT;

-- Refresh after invalidation.
SELECT refresh_cache_entry(
    namespace_id,
    'product:100'
)
FROM cache_namespace
WHERE namespace_name = 'product-cache';

-- CTE identifies keys with unusually high origin traffic relative to request
-- volume, which can indicate a stampede or ineffective caching.
WITH traffic AS (
    SELECT
        namespace_id,
        cache_key,
        count(*) AS request_count,
        count(*) FILTER (
            WHERE backend_called
        ) AS backend_count
    FROM cache_request
    GROUP BY namespace_id, cache_key
)
SELECT
    n.namespace_name,
    traffic.cache_key,
    traffic.request_count,
    traffic.backend_count,
    round(
        traffic.backend_count::NUMERIC
        / NULLIF(traffic.request_count, 0),
        4
    ) AS backend_ratio
FROM traffic
JOIN cache_namespace n
    ON n.namespace_id = traffic.namespace_id
WHERE traffic.backend_count > 0
ORDER BY backend_ratio DESC;

-- Final operational report.
SELECT *
FROM cache_health_report;
