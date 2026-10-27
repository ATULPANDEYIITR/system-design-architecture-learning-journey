DROP SCHEMA IF EXISTS cdn CASCADE;
CREATE SCHEMA cdn;

SET search_path TO cdn, public;

-- Geographic points used by the routing layer.
CREATE TABLE regions (
    region_code text PRIMARY KEY,
    region_name text NOT NULL UNIQUE
);

CREATE TABLE origins (
    origin_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin_name text NOT NULL UNIQUE,
    region_code text NOT NULL REFERENCES regions(region_code),
    available boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE edge_servers (
    edge_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    edge_name text NOT NULL UNIQUE,
    region_code text NOT NULL REFERENCES regions(region_code),
    state text NOT NULL DEFAULT 'HEALTHY'
        CHECK (state IN ('HEALTHY', 'DEGRADED', 'OFFLINE')),
    cache_capacity integer NOT NULL CHECK (cache_capacity > 0),
    base_latency_ms integer NOT NULL CHECK (base_latency_ms >= 0)
);

CREATE TABLE geographic_latency (
    source_region text NOT NULL REFERENCES regions(region_code),
    target_region text NOT NULL REFERENCES regions(region_code),
    latency_ms integer NOT NULL CHECK (latency_ms >= 0),
    PRIMARY KEY (source_region, target_region)
);

CREATE TABLE objects (
    object_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin_id bigint NOT NULL REFERENCES origins(origin_id),
    path text NOT NULL,
    content_type text NOT NULL,
    body text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    cacheable boolean NOT NULL DEFAULT true,
    ttl_seconds integer NOT NULL CHECK (ttl_seconds >= 0),
    etag text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (origin_id, path, version),
    UNIQUE (origin_id, path, etag),
    CHECK (path LIKE '/%'),
    CHECK (position('..' in path) = 0)
);

CREATE TABLE cache_entries (
    edge_id bigint NOT NULL REFERENCES edge_servers(edge_id)
        ON DELETE CASCADE,
    object_id bigint NOT NULL REFERENCES objects(object_id)
        ON DELETE CASCADE,
    stored_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (edge_id, object_id),
    CHECK (expires_at >= stored_at)
);

CREATE TABLE repositories (
    repository_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name text NOT NULL UNIQUE,
    default_branch text NOT NULL DEFAULT 'main'
);

CREATE TABLE cdn_requests (
    request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_region text NOT NULL REFERENCES regions(region_code),
    edge_id bigint REFERENCES edge_servers(edge_id),
    object_id bigint REFERENCES objects(object_id),
    path text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('HIT', 'MISS', 'STALE', 'BYPASS', 'ORIGIN_ERROR')
    ),
    latency_ms integer NOT NULL CHECK (latency_ms >= 0),
    requested_at timestamptz NOT NULL DEFAULT now(),
    authenticated boolean NOT NULL DEFAULT false
);

CREATE TABLE invalidations (
    invalidation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    path text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL,
    completed boolean NOT NULL DEFAULT false
);

CREATE INDEX idx_objects_origin_path
    ON objects (origin_id, path, version DESC);

CREATE INDEX idx_cache_entries_expiry
    ON cache_entries (expires_at);

CREATE INDEX idx_requests_time_status
    ON cdn_requests (requested_at, status);

CREATE INDEX idx_requests_edge_time
    ON cdn_requests (edge_id, requested_at);

INSERT INTO regions (region_code, region_name) VALUES
    ('DEL', 'Delhi'),
    ('BOM', 'Mumbai'),
    ('SIN', 'Singapore'),
    ('LON', 'London');

INSERT INTO origins (origin_name, region_code) VALUES
    ('primary-origin', 'DEL');

INSERT INTO edge_servers
    (edge_name, region_code, state, cache_capacity, base_latency_ms)
VALUES
    ('edge-delhi', 'DEL', 'HEALTHY', 3, 8),
    ('edge-mumbai', 'BOM', 'HEALTHY', 3, 12),
    ('edge-singapore', 'SIN', 'HEALTHY', 3, 10),
    ('edge-london', 'LON', 'DEGRADED', 3, 18);

INSERT INTO geographic_latency
    (source_region, target_region, latency_ms)
VALUES
    ('DEL', 'DEL', 0),
    ('BOM', 'BOM', 0),
    ('SIN', 'SIN', 0),
    ('LON', 'LON', 0),
    ('DEL', 'BOM', 18),
    ('BOM', 'DEL', 18),
    ('DEL', 'SIN', 65),
    ('SIN', 'DEL', 65),
    ('DEL', 'LON', 120),
    ('LON', 'DEL', 120),
    ('BOM', 'SIN', 55),
    ('SIN', 'BOM', 55),
    ('BOM', 'LON', 130),
    ('LON', 'BOM', 130),
    ('SIN', 'LON', 160),
    ('LON', 'SIN', 160);

-- SHA-256 is computed with PostgreSQL's pgcrypto extension in production.
-- This script instead stores deterministic example ETags so the database
-- remains executable on a standard PostgreSQL installation.
INSERT INTO objects
    (origin_id, path, content_type, body, version, cacheable, ttl_seconds, etag)
SELECT
    o.origin_id,
    '/static/app.js',
    'application/javascript',
    'console.log(''release-1'');',
    1,
    true,
    30,
    'etag-app-v1'
FROM origins o
WHERE o.origin_name = 'primary-origin';

INSERT INTO objects
    (origin_id, path, content_type, body, version, cacheable, ttl_seconds, etag)
SELECT
    o.origin_id,
    '/static/app.js',
    'application/javascript',
    'console.log(''release-2'');',
    2,
    true,
    30,
    'etag-app-v2'
FROM origins o
WHERE o.origin_name = 'primary-origin';

INSERT INTO objects
    (origin_id, path, content_type, body, version, cacheable, ttl_seconds, etag)
SELECT
    o.origin_id,
    '/static/logo.svg',
    'image/svg+xml',
    '<svg>logo</svg>',
    1,
    true,
    60,
    'etag-logo-v1'
FROM origins o
WHERE o.origin_name = 'primary-origin';

INSERT INTO objects
    (origin_id, path, content_type, body, version, cacheable, ttl_seconds, etag)
SELECT
    o.origin_id,
    '/private/audit.json',
    'application/json',
    '{"classification":"internal"}',
    1,
    false,
    0,
    'etag-audit-v1'
FROM origins o
WHERE o.origin_name = 'primary-origin';

-- Cache only the latest version of the public application object.
INSERT INTO cache_entries
    (edge_id, object_id, stored_at, expires_at)
SELECT
    e.edge_id,
    o.object_id,
    now() - interval '5 seconds',
    now() + interval '25 seconds'
FROM edge_servers e
JOIN objects o
  ON o.path = '/static/app.js'
 AND o.version = 2
WHERE e.edge_name = 'edge-delhi';

-- One deliberately stale object demonstrates expiration handling.
INSERT INTO cache_entries
    (edge_id, object_id, stored_at, expires_at)
SELECT
    e.edge_id,
    o.object_id,
    now() - interval '120 seconds',
    now() - interval '60 seconds'
FROM edge_servers e
JOIN objects o
  ON o.path = '/static/logo.svg'
WHERE e.edge_name = 'edge-singapore';

-- Shared-cache invariant: private objects must never enter cache_entries.
CREATE OR REPLACE FUNCTION prevent_private_cache()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    object_path text;
    object_cacheable boolean;
BEGIN
    SELECT path, cacheable
    INTO object_path, object_cacheable
    FROM objects
    WHERE object_id = NEW.object_id;

    IF object_path LIKE '/private/%' OR object_cacheable = false THEN
        RAISE EXCEPTION
            'Private or non-cacheable object % cannot be cached',
            NEW.object_id;
    END IF;

    IF NEW.expires_at <= NEW.stored_at THEN
        RAISE EXCEPTION
            'Cache expiry must be after storage time';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_private_cache
BEFORE INSERT OR UPDATE ON cache_entries
FOR EACH ROW
EXECUTE FUNCTION prevent_private_cache();

-- A request for a private object must be authenticated.
CREATE OR REPLACE FUNCTION validate_request_security()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.path LIKE '/private/%' AND NEW.authenticated = false THEN
        RAISE EXCEPTION
            'Unauthenticated private-content request rejected';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_request_security
BEFORE INSERT OR UPDATE ON cdn_requests
FOR EACH ROW
EXECUTE FUNCTION validate_request_security();

-- Select the lowest-latency healthy edge for a client region.
CREATE OR REPLACE FUNCTION select_edge(
    p_client_region text
)
RETURNS TABLE (
    edge_id bigint,
    edge_name text,
    region_code text,
    effective_latency_ms integer
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        e.edge_id,
        e.edge_name,
        e.region_code,
        gl.latency_ms + e.base_latency_ms
        + CASE WHEN e.state = 'DEGRADED' THEN 1000 ELSE 0 END
            AS effective_latency_ms
    FROM edge_servers e
    JOIN geographic_latency gl
      ON gl.source_region = p_client_region
     AND gl.target_region = e.region_code
    WHERE e.state <> 'OFFLINE'
    ORDER BY effective_latency_ms, e.edge_id
    LIMIT 1;
$$;

-- Resolve the currently active origin version for a path.
CREATE OR REPLACE FUNCTION current_object(
    p_path text
)
RETURNS TABLE (
    object_id bigint,
    version integer,
    etag text,
    ttl_seconds integer,
    cacheable boolean
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        o.object_id,
        o.version,
        o.etag,
        o.ttl_seconds,
        o.cacheable
    FROM objects o
    JOIN origins origin
      ON origin.origin_id = o.origin_id
    WHERE o.path = p_path
      AND origin.available = true
    ORDER BY o.version DESC
    LIMIT 1;
$$;

-- Cache eligibility query:
-- a fresh entry is eligible for a cache hit only when it has not expired.
SELECT
    e.edge_name,
    o.path,
    o.version,
    ce.stored_at,
    ce.expires_at,
    CASE
        WHEN ce.expires_at > now() THEN 'FRESH'
        ELSE 'STALE'
    END AS cache_state
FROM cache_entries ce
JOIN edge_servers e ON e.edge_id = ce.edge_id
JOIN objects o ON o.object_id = ce.object_id
ORDER BY e.edge_name, o.path;

-- Geographic routing decision for a Delhi client.
SELECT *
FROM select_edge('DEL');

-- Aggregate cache performance by edge.
SELECT
    e.edge_name,
    count(*) AS requests,
    count(*) FILTER (WHERE r.status = 'HIT') AS hits,
    count(*) FILTER (WHERE r.status = 'MISS') AS misses,
    round(
        100.0 * count(*) FILTER (WHERE r.status = 'HIT')
        / NULLIF(count(*), 0),
        2
    ) AS hit_percentage,
    round(avg(r.latency_ms), 2) AS average_latency_ms
FROM edge_servers e
LEFT JOIN cdn_requests r ON r.edge_id = e.edge_id
GROUP BY e.edge_id, e.edge_name
ORDER BY e.edge_name;

-- CTE-based report identifies stale cache entries that require refresh.
WITH stale_entries AS (
    SELECT
        ce.edge_id,
        ce.object_id,
        ce.expires_at
    FROM cache_entries ce
    WHERE ce.expires_at <= now()
)
SELECT
    e.edge_name,
    o.path,
    o.version,
    s.expires_at
FROM stale_entries s
JOIN edge_servers e ON e.edge_id = s.edge_id
JOIN objects o ON o.object_id = s.object_id
ORDER BY s.expires_at;

-- Populate representative request history.
INSERT INTO cdn_requests
    (client_region, edge_id, object_id, path, status, latency_ms, authenticated)
SELECT
    'DEL',
    e.edge_id,
    o.object_id,
    '/static/app.js',
    'HIT',
    8,
    false
FROM edge_servers e
JOIN objects o
  ON o.path = '/static/app.js'
 AND o.version = 2
WHERE e.edge_name = 'edge-delhi';

INSERT INTO cdn_requests
    (client_region, edge_id, object_id, path, status, latency_ms, authenticated)
SELECT
    'SIN',
    e.edge_id,
    o.object_id,
    '/static/logo.svg',
    'STALE',
    20,
    false
FROM edge_servers e
JOIN objects o ON o.path = '/static/logo.svg'
WHERE e.edge_name = 'edge-singapore';

INSERT INTO cdn_requests
    (client_region, edge_id, object_id, path, status, latency_ms, authenticated)
SELECT
    'DEL',
    e.edge_id,
    o.object_id,
    '/private/audit.json',
    'BYPASS',
    90,
    true
FROM edge_servers e
JOIN objects o ON o.path = '/private/audit.json'
WHERE e.edge_name = 'edge-delhi';

-- Transactional invalidation:
-- invalidate an object path atomically and record the operation.
BEGIN;

INSERT INTO invalidations (path, reason, completed)
VALUES (
    '/static/app.js',
    'Release propagation',
    false
);

DELETE FROM cache_entries
WHERE object_id IN (
    SELECT object_id
    FROM objects
    WHERE path = '/static/app.js'
);

UPDATE invalidations
SET completed = true
WHERE invalidation_id = (
    SELECT max(invalidation_id)
    FROM invalidations
    WHERE path = '/static/app.js'
);

COMMIT;

-- The latest object is now available for future cache population.
SELECT *
FROM current_object('/static/app.js');

-- Governance report across routing, cache, and origin state.
WITH latest_objects AS (
    SELECT DISTINCT ON (path)
        object_id,
        path,
        version,
        cacheable,
        ttl_seconds
    FROM objects
    ORDER BY path, version DESC
),
edge_capacity AS (
    SELECT
        state,
        count(*) AS edge_count,
        sum(cache_capacity) AS total_cache_capacity
    FROM edge_servers
    GROUP BY state
)
SELECT
    lo.path,
    lo.version,
    lo.cacheable,
    lo.ttl_seconds,
    ec.state,
    ec.edge_count,
    ec.total_cache_capacity
FROM latest_objects lo
CROSS JOIN edge_capacity ec
ORDER BY lo.path, ec.state;
