DROP SCHEMA IF EXISTS cache_invalidation_demo CASCADE;
CREATE SCHEMA cache_invalidation_demo;
SET search_path TO cache_invalidation_demo;

-- The authoritative relational data is deliberately separated from the
-- cache representation. PostgreSQL remains the source of truth.

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE cache_entries (
    cache_key TEXT PRIMARY KEY,
    product_id BIGINT REFERENCES products(product_id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    source_version BIGINT NOT NULL CHECK (source_version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ,
    CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE INDEX idx_cache_entries_product
    ON cache_entries (product_id);

CREATE INDEX idx_cache_entries_expiry
    ON cache_entries (expires_at)
    WHERE expires_at IS NOT NULL;

CREATE TABLE invalidation_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cache_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_version BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_invalidation_events_key_time
    ON invalidation_events (cache_key, created_at DESC);

INSERT INTO products (sku, product_name, price)
VALUES
    ('KB-001', 'Keyboard', 2400.00),
    ('MON-001', 'Monitor', 18500.00),
    ('MOU-001', 'Mouse', 1200.00);

-- PostgreSQL trigger-based versioning makes a successful update observable
-- as a newer representation even when application code forgets to increment
-- the version explicitly.
CREATE OR REPLACE FUNCTION bump_product_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.product_name IS DISTINCT FROM OLD.product_name
       OR NEW.price IS DISTINCT FROM OLD.price THEN
        NEW.version := OLD.version + 1;
        NEW.updated_at := clock_timestamp();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_products_version
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION bump_product_version();

-- Explicit invalidation records are useful for auditability and distributed
-- cache consumers. The database does not pretend to be a distributed cache.
CREATE OR REPLACE FUNCTION record_product_invalidation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.version <> OLD.version THEN
        INSERT INTO invalidation_events (
            cache_key,
            reason,
            source_version
        )
        VALUES (
            'product:' || NEW.product_id,
            'authoritative product changed',
            NEW.version
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_product_invalidation
AFTER UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION record_product_invalidation();

-- Cache-aside population. The cache stores a snapshot and the authoritative
-- row version that produced that snapshot.
CREATE OR REPLACE FUNCTION cache_product(
    p_product_id BIGINT,
    p_ttl INTERVAL DEFAULT INTERVAL '5 minutes'
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    p RECORD;
BEGIN
    SELECT *
    INTO p
    FROM products
    WHERE product_id = p_product_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'product % does not exist', p_product_id;
    END IF;

    INSERT INTO cache_entries (
        cache_key,
        product_id,
        payload,
        source_version,
        expires_at
    )
    VALUES (
        'product:' || p.product_id,
        p.product_id,
        jsonb_build_object(
            'product_id', p.product_id,
            'sku', p.sku,
            'product_name', p.product_name,
            'price', p.price
        ),
        p.version,
        clock_timestamp() + p_ttl
    )
    ON CONFLICT (cache_key)
    DO UPDATE SET
        payload = EXCLUDED.payload,
        source_version = EXCLUDED.source_version,
        created_at = clock_timestamp(),
        expires_at = EXCLUDED.expires_at;
END;
$$;

-- Invalidation is explicit and idempotent.
CREATE OR REPLACE FUNCTION invalidate_product_cache(
    p_product_id BIGINT,
    p_reason TEXT DEFAULT 'explicit invalidation'
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    removed BOOLEAN;
BEGIN
    DELETE FROM cache_entries
    WHERE cache_key = 'product:' || p_product_id;

    removed := FOUND;

    INSERT INTO invalidation_events (
        cache_key,
        reason,
        source_version
    )
    SELECT
        'product:' || p_product_id,
        p_reason,
        version
    FROM products
    WHERE product_id = p_product_id;

    RETURN removed;
END;
$$;

-- Stale cache entries are physically removed. Version mismatches are treated
-- as stale even if their TTL has not expired.
CREATE OR REPLACE FUNCTION remove_stale_cache_entries()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM cache_entries c
    USING products p
    WHERE c.product_id = p.product_id
      AND (
          c.expires_at <= clock_timestamp()
          OR c.source_version < p.version
      );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- Demonstrate cache population.
SELECT cache_product(product_id, INTERVAL '10 minutes')
FROM products
WHERE sku IN ('KB-001', 'MON-001');

-- A valid cache hit requires both an existing entry and a matching
-- authoritative version.
SELECT
    c.cache_key,
    c.payload,
    c.source_version,
    p.version AS authoritative_version,
    c.expires_at,
    CASE
        WHEN c.expires_at <= clock_timestamp() THEN 'expired'
        WHEN c.source_version < p.version THEN 'version-stale'
        ELSE 'fresh'
    END AS cache_state
FROM cache_entries c
JOIN products p ON p.product_id = c.product_id
ORDER BY c.cache_key;

-- Update the source of truth. The trigger advances the version and records
-- an invalidation event.
BEGIN;

UPDATE products
SET price = 2600.00
WHERE sku = 'KB-001';

-- The transaction has not committed yet. Consumers outside this transaction
-- must not observe an incomplete state.
COMMIT;

-- The existing cache entry is now stale by version even before its TTL ends.
SELECT
    c.cache_key,
    c.source_version,
    p.version,
    c.source_version < p.version AS stale_by_version
FROM cache_entries c
JOIN products p ON p.product_id = c.product_id
WHERE p.sku = 'KB-001';

-- Remove the stale snapshot and repopulate it from authoritative data.
SELECT remove_stale_cache_entries();
SELECT cache_product(
    product_id,
    INTERVAL '10 minutes'
)
FROM products
WHERE sku = 'KB-001';

-- Demonstrate an explicit invalidation transaction.
BEGIN;

SELECT invalidate_product_cache(
    product_id,
    'product correction'
)
FROM products
WHERE sku = 'MON-001';

COMMIT;

-- A missing cache entry is not an error in a cache-aside design.
SELECT
    p.product_id,
    p.sku,
    p.product_name,
    p.price,
    p.version,
    c.cache_key IS NOT NULL AS cached
FROM products p
LEFT JOIN cache_entries c
    ON c.product_id = p.product_id
ORDER BY p.product_id;

-- CTE-based freshness report for operational monitoring.
WITH freshness AS (
    SELECT
        c.cache_key,
        c.source_version,
        p.version AS authoritative_version,
        c.expires_at,
        CASE
            WHEN c.expires_at <= clock_timestamp() THEN 'expired'
            WHEN c.source_version < p.version THEN 'version-stale'
            ELSE 'fresh'
        END AS state
    FROM cache_entries c
    JOIN products p ON p.product_id = c.product_id
)
SELECT
    state,
    COUNT(*) AS entry_count
FROM freshness
GROUP BY state
ORDER BY state;

-- Review invalidation history. This can expose excessive invalidation,
-- unexpected write activity, or missing consumer processing.
SELECT
    event_id,
    cache_key,
    reason,
    source_version,
    created_at
FROM invalidation_events
ORDER BY created_at DESC, event_id DESC;

-- Failure case: a negative price is rejected at the database boundary.
DO $$
BEGIN
    BEGIN
        UPDATE products
        SET price = -1
        WHERE sku = 'KB-001';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Invalid price correctly rejected by CHECK constraint';
    END;
END;
$$;

-- TTL demonstration using a very short expiration period.
SELECT cache_product(product_id, INTERVAL '1 second')
FROM products
WHERE sku = 'MOU-001';

SELECT
    cache_key,
    expires_at > clock_timestamp() AS currently_within_ttl
FROM cache_entries
WHERE cache_key = (
    SELECT 'product:' || product_id
    FROM products
    WHERE sku = 'MOU-001'
);

-- Remove expired or version-stale entries as a maintenance operation.
SELECT remove_stale_cache_entries();

-- PostgreSQL LISTEN/NOTIFY can complement the audit table for low-latency
-- in-process or connection-level consumers. Durable consumers should rely
-- on a durable event mechanism rather than assuming NOTIFY is a queue.
CREATE OR REPLACE FUNCTION notify_product_invalidation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify(
        'product_cache_invalidation',
        json_build_object(
            'product_id', NEW.product_id,
            'version', NEW.version
        )::TEXT
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_notify_product_invalidation
AFTER UPDATE OF price, product_name ON products
FOR EACH ROW
WHEN (NEW.version <> OLD.version)
EXECUTE FUNCTION notify_product_invalidation();

-- Final authoritative state.
SELECT
    product_id,
    sku,
    product_name,
    price,
    version,
    updated_at
FROM products
ORDER BY product_id;
