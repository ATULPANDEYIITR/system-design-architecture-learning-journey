DROP SCHEMA IF EXISTS cache_strategy_demo CASCADE;

CREATE SCHEMA cache_strategy_demo;

SET search_path TO cache_strategy_demo;

-- PostgreSQL model:
-- the database is the source of truth while cache_entries represents a
-- materialized cache view whose freshness is governed by expiration and
-- invalidation rules.

CREATE TYPE cache_strategy AS ENUM (
    'cache_aside',
    'read_through',
    'write_through'
);

CREATE TYPE cache_event_type AS ENUM (
    'hit',
    'miss',
    'populate',
    'invalidate',
    'expire',
    'write_through'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL
);

CREATE TABLE products (
    product_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL
        CHECK (price >= 0),
    stock INTEGER NOT NULL
        CHECK (stock >= 0),
    version BIGINT NOT NULL DEFAULT 1
        CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cache_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    strategy cache_strategy NOT NULL,
    ttl_seconds INTEGER
        CHECK (ttl_seconds IS NULL OR ttl_seconds > 0),
    cache_missing_values BOOLEAN NOT NULL DEFAULT FALSE,
    invalidate_on_write BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (repository_id)
);

CREATE TABLE cache_entries (
    cache_entry_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES cache_policies(policy_id)
        ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES products(product_id)
        ON DELETE CASCADE,
    cached_version BIGINT NOT NULL
        CHECK (cached_version > 0),
    cached_price NUMERIC(12, 2) NOT NULL
        CHECK (cached_price >= 0),
    cached_stock INTEGER NOT NULL
        CHECK (cached_stock >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    last_accessed_at TIMESTAMPTZ,
    UNIQUE (policy_id, product_id)
);

CREATE TABLE cache_events (
    event_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES cache_policies(policy_id)
        ON DELETE CASCADE,
    product_id BIGINT
        REFERENCES products(product_id)
        ON DELETE SET NULL,
    event_type cache_event_type NOT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detail TEXT
);

CREATE INDEX idx_products_repository
    ON products(repository_id);

CREATE INDEX idx_products_updated_at
    ON products(updated_at);

CREATE INDEX idx_cache_entries_expiration
    ON cache_entries(expires_at);

CREATE INDEX idx_cache_events_policy_time
    ON cache_events(policy_id, event_time DESC);

CREATE INDEX idx_cache_events_product
    ON cache_events(product_id, event_time DESC);

CREATE OR REPLACE FUNCTION validate_cache_entry_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_version BIGINT;
BEGIN
    SELECT version
    INTO source_version
    FROM products
    WHERE product_id = NEW.product_id;

    IF source_version IS NULL THEN
        RAISE EXCEPTION
            'Cannot cache product % because it does not exist',
            NEW.product_id;
    END IF;

    IF NEW.cached_version > source_version THEN
        RAISE EXCEPTION
            'Cache version % cannot be newer than source version %',
            NEW.cached_version,
            source_version;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_cache_version
BEFORE INSERT OR UPDATE
ON cache_entries
FOR EACH ROW
EXECUTE FUNCTION validate_cache_entry_version();

CREATE OR REPLACE FUNCTION bump_product_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.price IS DISTINCT FROM OLD.price
       OR NEW.stock IS DISTINCT FROM OLD.stock
       OR NEW.product_name IS DISTINCT FROM OLD.product_name
    THEN
        NEW.version := OLD.version + 1;
    ELSE
        NEW.version := OLD.version;
    END IF;

    NEW.updated_at := CURRENT_TIMESTAMP;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_product_version
BEFORE UPDATE
ON products
FOR EACH ROW
EXECUTE FUNCTION bump_product_version();

INSERT INTO repositories (
    repository_name,
    description
)
VALUES
    (
        'catalog-cache-aside',
        'Product catalog using application-managed cache-aside reads'
    ),
    (
        'catalog-read-through',
        'Product catalog whose cache layer loads source values on misses'
    ),
    (
        'catalog-write-through',
        'Product catalog whose successful writes update cache immediately'
    );

INSERT INTO products (
    repository_id,
    product_name,
    price,
    stock
)
SELECT
    r.repository_id,
    v.product_name,
    v.price,
    v.stock
FROM repositories r
JOIN (
    VALUES
        (
            'catalog-cache-aside',
            'Mechanical Keyboard',
            89.99::NUMERIC,
            42
        ),
        (
            'catalog-read-through',
            'USB-C Dock',
            129.50::NUMERIC,
            17
        ),
        (
            'catalog-write-through',
            'Noise-Cancelling Headphones',
            199.00::NUMERIC,
            9
        )
) AS v(
    repository_name,
    product_name,
    price,
    stock
)
ON r.repository_name = v.repository_name;

INSERT INTO cache_policies (
    repository_id,
    strategy,
    ttl_seconds,
    cache_missing_values,
    invalidate_on_write
)
SELECT
    repository_id,
    CASE repository_name
        WHEN 'catalog-cache-aside'
            THEN 'cache_aside'::cache_strategy
        WHEN 'catalog-read-through'
            THEN 'read_through'::cache_strategy
        WHEN 'catalog-write-through'
            THEN 'write_through'::cache_strategy
    END,
    60,
    FALSE,
    TRUE
FROM repositories;

-- Cache-aside population:
-- the application first checks cache_entries, then loads products after a
-- miss and explicitly inserts the resulting representation.

INSERT INTO cache_entries (
    policy_id,
    product_id,
    cached_version,
    cached_price,
    cached_stock,
    expires_at,
    last_accessed_at
)
SELECT
    cp.policy_id,
    p.product_id,
    p.version,
    p.price,
    p.stock,
    CURRENT_TIMESTAMP + make_interval(
        secs => cp.ttl_seconds
    ),
    CURRENT_TIMESTAMP
FROM cache_policies cp
JOIN repositories r
    ON r.repository_id = cp.repository_id
JOIN products p
    ON p.repository_id = r.repository_id
WHERE cp.strategy = 'cache_aside';

INSERT INTO cache_events (
    policy_id,
    product_id,
    event_type,
    detail
)
SELECT
    cp.policy_id,
    p.product_id,
    'populate',
    'Cache-aside application populated entry after source read'
FROM cache_policies cp
JOIN products p
    ON p.repository_id = cp.repository_id
WHERE cp.strategy = 'cache_aside';

-- Read-through evaluation:
-- the query below exposes a source fallback whenever the cache has no valid
-- entry. In an application, this fallback is normally performed by the
-- cache layer rather than manually by each caller.

WITH valid_cache AS (
    SELECT
        ce.policy_id,
        ce.product_id,
        ce.cached_version,
        ce.cached_price,
        ce.cached_stock
    FROM cache_entries ce
    WHERE ce.expires_at IS NULL
       OR ce.expires_at > CURRENT_TIMESTAMP
),
read_through_result AS (
    SELECT
        cp.policy_id,
        p.product_id,
        COALESCE(vc.cached_version, p.version) AS visible_version,
        COALESCE(vc.cached_price, p.price) AS visible_price,
        COALESCE(vc.cached_stock, p.stock) AS visible_stock,
        CASE
            WHEN vc.product_id IS NULL THEN 'source_fallback'
            ELSE 'cache_hit'
        END AS read_path
    FROM cache_policies cp
    JOIN products p
        ON p.repository_id = cp.repository_id
    LEFT JOIN valid_cache vc
        ON vc.policy_id = cp.policy_id
       AND vc.product_id = p.product_id
    WHERE cp.strategy = 'read_through'
)
SELECT *
FROM read_through_result
ORDER BY product_id;

-- Record a read-through miss and subsequent population for the existing
-- USB-C Dock entry.
INSERT INTO cache_events (
    policy_id,
    product_id,
    event_type,
    detail
)
SELECT
    cp.policy_id,
    p.product_id,
    'miss',
    'Read-through cache did not contain a valid entry'
FROM cache_policies cp
JOIN products p
    ON p.repository_id = cp.repository_id
WHERE cp.strategy = 'read_through';

INSERT INTO cache_entries (
    policy_id,
    product_id,
    cached_version,
    cached_price,
    cached_stock,
    expires_at,
    last_accessed_at
)
SELECT
    cp.policy_id,
    p.product_id,
    p.version,
    p.price,
    p.stock,
    CURRENT_TIMESTAMP + make_interval(
        secs => cp.ttl_seconds
    ),
    CURRENT_TIMESTAMP
FROM cache_policies cp
JOIN products p
    ON p.repository_id = cp.repository_id
WHERE cp.strategy = 'read_through'
ON CONFLICT (policy_id, product_id)
DO UPDATE SET
    cached_version = EXCLUDED.cached_version,
    cached_price = EXCLUDED.cached_price,
    cached_stock = EXCLUDED.cached_stock,
    created_at = CURRENT_TIMESTAMP,
    expires_at = EXCLUDED.expires_at,
    last_accessed_at = CURRENT_TIMESTAMP;

-- Write-through operation.
-- The transaction makes the source update and cache refresh part of one
-- database transaction. If either statement fails, the transaction can be
-- rolled back so a new cache representation is not committed independently.
BEGIN;

UPDATE products
SET
    price = 184.00,
    stock = 8
WHERE product_id = (
    SELECT p.product_id
    FROM products p
    JOIN repositories r
        ON r.repository_id = p.repository_id
    WHERE r.repository_name = 'catalog-write-through'
);

INSERT INTO cache_entries (
    policy_id,
    product_id,
    cached_version,
    cached_price,
    cached_stock,
    expires_at,
    last_accessed_at
)
SELECT
    cp.policy_id,
    p.product_id,
    p.version,
    p.price,
    p.stock,
    CURRENT_TIMESTAMP + make_interval(
        secs => cp.ttl_seconds
    ),
    CURRENT_TIMESTAMP
FROM cache_policies cp
JOIN repositories r
    ON r.repository_id = cp.repository_id
JOIN products p
    ON p.repository_id = r.repository_id
WHERE cp.strategy = 'write_through'
ON CONFLICT (policy_id, product_id)
DO UPDATE SET
    cached_version = EXCLUDED.cached_version,
    cached_price = EXCLUDED.cached_price,
    cached_stock = EXCLUDED.cached_stock,
    expires_at = EXCLUDED.expires_at,
    last_accessed_at = CURRENT_TIMESTAMP;

INSERT INTO cache_events (
    policy_id,
    product_id,
    event_type,
    detail
)
SELECT
    cp.policy_id,
    p.product_id,
    'write_through',
    'Source row and cache entry updated in the same transaction'
FROM cache_policies cp
JOIN products p
    ON p.repository_id = cp.repository_id
WHERE cp.strategy = 'write_through';

COMMIT;

-- Detect stale cache entries by comparing cached version with source version.
SELECT
    r.repository_name,
    p.product_id,
    p.product_name,
    p.version AS source_version,
    ce.cached_version,
    p.version - ce.cached_version AS version_lag
FROM cache_entries ce
JOIN cache_policies cp
    ON cp.policy_id = ce.policy_id
JOIN repositories r
    ON r.repository_id = cp.repository_id
JOIN products p
    ON p.product_id = ce.product_id
WHERE ce.cached_version < p.version
ORDER BY version_lag DESC;

-- Detect entries that should no longer be served because their TTL expired.
SELECT
    r.repository_name,
    p.product_name,
    ce.created_at,
    ce.expires_at
FROM cache_entries ce
JOIN cache_policies cp
    ON cp.policy_id = ce.policy_id
JOIN repositories r
    ON r.repository_id = cp.repository_id
JOIN products p
    ON p.product_id = ce.product_id
WHERE ce.expires_at IS NOT NULL
  AND ce.expires_at <= CURRENT_TIMESTAMP
ORDER BY ce.expires_at;

-- Explicit invalidation for a cache-aside write.
-- The source remains authoritative; the next application read will repopulate
-- the cache from the new source representation.
BEGIN;

UPDATE products
SET price = 99.00
WHERE product_id = (
    SELECT p.product_id
    FROM products p
    JOIN repositories r
        ON r.repository_id = p.repository_id
    WHERE r.repository_name = 'catalog-cache-aside'
);

DELETE FROM cache_entries
WHERE policy_id = (
    SELECT cp.policy_id
    FROM cache_policies cp
    JOIN repositories r
        ON r.repository_id = cp.repository_id
    WHERE r.repository_name = 'catalog-cache-aside'
)
AND product_id = (
    SELECT p.product_id
    FROM products p
    JOIN repositories r
        ON r.repository_id = p.repository_id
    WHERE r.repository_name = 'catalog-cache-aside'
);

INSERT INTO cache_events (
    policy_id,
    product_id,
    event_type,
    detail
)
SELECT
    cp.policy_id,
    p.product_id,
    'invalidate',
    'Cache-aside write invalidated cached representation'
FROM cache_policies cp
JOIN repositories r
    ON r.repository_id = cp.repository_id
JOIN products p
    ON p.repository_id = r.repository_id
WHERE r.repository_name = 'catalog-cache-aside';

COMMIT;

-- A policy-oriented operational report combines strategy, cache state, and
-- source freshness without pretending that the cache itself is authoritative.
SELECT
    r.repository_name,
    cp.strategy,
    cp.ttl_seconds,
    p.product_name,
    p.version AS source_version,
    ce.cached_version,
    CASE
        WHEN ce.product_id IS NULL THEN 'not_cached'
        WHEN ce.expires_at IS NOT NULL
             AND ce.expires_at <= CURRENT_TIMESTAMP
            THEN 'expired'
        WHEN ce.cached_version < p.version
            THEN 'stale'
        ELSE 'fresh'
    END AS cache_state
FROM repositories r
JOIN cache_policies cp
    ON cp.repository_id = r.repository_id
JOIN products p
    ON p.repository_id = r.repository_id
LEFT JOIN cache_entries ce
    ON ce.policy_id = cp.policy_id
   AND ce.product_id = p.product_id
ORDER BY r.repository_name;

-- Operational metrics distinguish cache hits, misses, population, invalidation,
-- expiration, and write-through activity rather than treating every cache
-- operation as the same event.
SELECT
    r.repository_name,
    cp.strategy,
    ce.event_type,
    COUNT(*) AS event_count
FROM cache_events ce
JOIN cache_policies cp
    ON cp.policy_id = ce.policy_id
JOIN repositories r
    ON r.repository_id = cp.repository_id
GROUP BY
    r.repository_name,
    cp.strategy,
    ce.event_type
ORDER BY
    r.repository_name,
    ce.event_type;
