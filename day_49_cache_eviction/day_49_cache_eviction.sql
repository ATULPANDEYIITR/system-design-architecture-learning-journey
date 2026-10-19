DROP SCHEMA IF EXISTS cache_eviction_lab CASCADE;
CREATE SCHEMA cache_eviction_lab;
SET search_path TO cache_eviction_lab;

-- PostgreSQL model for evaluating LRU, LFU, FIFO and TTL cache behavior.
-- The cache is intentionally represented as data so eviction decisions,
-- access frequency and expiration can be inspected with relational queries.

CREATE TYPE eviction_policy AS ENUM ('LRU', 'LFU', 'FIFO', 'TTL');

CREATE TYPE cache_state AS ENUM ('ACTIVE', 'EXPIRED', 'EVICTED');

CREATE TABLE cache_profiles (
    profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_name TEXT NOT NULL UNIQUE,
    policy eviction_policy NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    default_ttl_seconds INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (
        (policy = 'TTL' AND default_ttl_seconds IS NOT NULL
         AND default_ttl_seconds > 0)
        OR
        (policy <> 'TTL')
    )
);

CREATE TABLE cache_entries (
    entry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES cache_profiles(profile_id),
    cache_key TEXT NOT NULL,
    cache_value JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    access_count BIGINT NOT NULL DEFAULT 1 CHECK (access_count > 0),
    insertion_sequence BIGINT NOT NULL,
    expires_at TIMESTAMPTZ,
    state cache_state NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (profile_id, cache_key),
    CHECK (expires_at IS NULL OR expires_at > inserted_at)
);

CREATE TABLE cache_access_log (
    access_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id BIGINT REFERENCES cache_entries(entry_id),
    profile_id BIGINT NOT NULL REFERENCES cache_profiles(profile_id),
    cache_key TEXT NOT NULL,
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    hit BOOLEAN NOT NULL,
    access_count_after BIGINT CHECK (access_count_after IS NULL OR access_count_after > 0)
);

CREATE INDEX idx_cache_entries_lru
    ON cache_entries (profile_id, last_accessed_at, insertion_sequence)
    WHERE state = 'ACTIVE';

CREATE INDEX idx_cache_entries_lfu
    ON cache_entries (profile_id, access_count, last_accessed_at)
    WHERE state = 'ACTIVE';

CREATE INDEX idx_cache_entries_fifo
    ON cache_entries (profile_id, insertion_sequence)
    WHERE state = 'ACTIVE';

CREATE INDEX idx_cache_entries_ttl
    ON cache_entries (profile_id, expires_at)
    WHERE state = 'ACTIVE' AND expires_at IS NOT NULL;

CREATE INDEX idx_access_log_profile_time
    ON cache_access_log (profile_id, accessed_at DESC);

CREATE OR REPLACE FUNCTION expire_cache_entries()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    changed_count INTEGER;
BEGIN
    UPDATE cache_entries
    SET state = 'EXPIRED'
    WHERE state = 'ACTIVE'
      AND expires_at IS NOT NULL
      AND expires_at <= clock_timestamp();

    GET DIAGNOSTICS changed_count = ROW_COUNT;
    RETURN changed_count;
END;
$$;

CREATE OR REPLACE FUNCTION register_cache_access(
    p_profile_id BIGINT,
    p_cache_key TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    current_entry cache_entries%ROWTYPE;
BEGIN
    PERFORM expire_cache_entries();

    SELECT *
    INTO current_entry
    FROM cache_entries
    WHERE profile_id = p_profile_id
      AND cache_key = p_cache_key
      AND state = 'ACTIVE'
    FOR UPDATE;

    IF NOT FOUND THEN
        INSERT INTO cache_access_log (
            profile_id,
            cache_key,
            hit
        )
        VALUES (
            p_profile_id,
            p_cache_key,
            FALSE
        );

        RETURN FALSE;
    END IF;

    UPDATE cache_entries
    SET last_accessed_at = clock_timestamp(),
        access_count = access_count + 1
    WHERE entry_id = current_entry.entry_id;

    INSERT INTO cache_access_log (
        entry_id,
        profile_id,
        cache_key,
        hit,
        access_count_after
    )
    VALUES (
        current_entry.entry_id,
        p_profile_id,
        p_cache_key,
        TRUE,
        current_entry.access_count + 1
    );

    RETURN TRUE;
END;
$$;

INSERT INTO cache_profiles (
    profile_name,
    policy,
    capacity,
    default_ttl_seconds
)
VALUES
    ('catalog-lru', 'LRU', 3, NULL),
    ('catalog-lfu', 'LFU', 3, NULL),
    ('catalog-fifo', 'FIFO', 3, NULL),
    ('session-ttl', 'TTL', 3, 30);

INSERT INTO cache_entries (
    profile_id,
    cache_key,
    cache_value,
    insertion_sequence,
    expires_at
)
SELECT
    profile_id,
    'product:101',
    '{"name":"Database Engine","version":"18"}'::jsonb,
    1,
    CASE WHEN policy = 'TTL'
         THEN clock_timestamp() + INTERVAL '30 seconds'
         ELSE NULL
    END
FROM cache_profiles;

INSERT INTO cache_entries (
    profile_id,
    cache_key,
    cache_value,
    insertion_sequence,
    expires_at
)
SELECT
    profile_id,
    'product:102',
    '{"name":"API Gateway","version":"4"}'::jsonb,
    2,
    CASE WHEN policy = 'TTL'
         THEN clock_timestamp() + INTERVAL '20 seconds'
         ELSE NULL
    END
FROM cache_profiles;

INSERT INTO cache_entries (
    profile_id,
    cache_key,
    cache_value,
    insertion_sequence,
    expires_at
)
SELECT
    profile_id,
    'product:103',
    '{"name":"Worker Service","version":"8"}'::jsonb,
    3,
    CASE WHEN policy = 'TTL'
         THEN clock_timestamp() + INTERVAL '10 seconds'
         ELSE NULL
    END
FROM cache_profiles;

-- Access history deliberately creates different LFU and LRU rankings.
SELECT register_cache_access(
    profile_id,
    'product:101'
)
FROM cache_profiles
WHERE profile_name IN ('catalog-lru', 'catalog-lfu');

SELECT register_cache_access(
    profile_id,
    'product:101'
)
FROM cache_profiles
WHERE profile_name = 'catalog-lfu';

SELECT register_cache_access(
    profile_id,
    'product:102'
)
FROM cache_profiles
WHERE profile_name IN ('catalog-lru', 'catalog-lfu');

-- The following query identifies the LRU victim.
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.profile_id
            ORDER BY e.last_accessed_at, e.insertion_sequence
        ) AS victim_rank
    FROM cache_entries e
    JOIN cache_profiles p
      ON p.profile_id = e.profile_id
    WHERE e.state = 'ACTIVE'
      AND p.policy = 'LRU'
)
SELECT profile_id, cache_key, last_accessed_at
FROM ranked
WHERE victim_rank = 1;

-- LFU uses access_count first, then recency to resolve a frequency tie.
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.profile_id
            ORDER BY e.access_count,
                     e.last_accessed_at,
                     e.insertion_sequence
        ) AS victim_rank
    FROM cache_entries e
    JOIN cache_profiles p
      ON p.profile_id = e.profile_id
    WHERE e.state = 'ACTIVE'
      AND p.policy = 'LFU'
)
SELECT profile_id, cache_key, access_count
FROM ranked
WHERE victim_rank = 1;

-- FIFO ignores access activity and selects the earliest insertion sequence.
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.profile_id
            ORDER BY e.insertion_sequence
        ) AS victim_rank
    FROM cache_entries e
    JOIN cache_profiles p
      ON p.profile_id = e.profile_id
    WHERE e.state = 'ACTIVE'
      AND p.policy = 'FIFO'
)
SELECT profile_id, cache_key, insertion_sequence
FROM ranked
WHERE victim_rank = 1;

-- TTL selects the active item whose expiration is nearest.
SELECT
    e.profile_id,
    e.cache_key,
    e.expires_at,
    e.expires_at - clock_timestamp() AS remaining_lifetime
FROM cache_entries e
JOIN cache_profiles p
  ON p.profile_id = e.profile_id
WHERE p.policy = 'TTL'
  AND e.state = 'ACTIVE'
ORDER BY e.expires_at NULLS LAST
LIMIT 1;

-- Transactional eviction keeps state changes atomic with respect to
-- application-level capacity enforcement.
BEGIN;

SELECT expire_cache_entries();

WITH target AS (
    SELECT e.entry_id
    FROM cache_entries e
    JOIN cache_profiles p
      ON p.profile_id = e.profile_id
    WHERE e.profile_id = (
        SELECT profile_id
        FROM cache_profiles
        WHERE profile_name = 'catalog-lru'
    )
      AND e.state = 'ACTIVE'
    ORDER BY e.last_accessed_at, e.insertion_sequence
    LIMIT 1
)
UPDATE cache_entries e
SET state = 'EVICTED'
FROM target
WHERE e.entry_id = target.entry_id;

COMMIT;

-- Capacity diagnostics expose profiles whose active entries exceed policy.
SELECT
    p.profile_name,
    p.policy,
    p.capacity,
    COUNT(e.entry_id) AS active_entries,
    p.capacity - COUNT(e.entry_id) AS remaining_capacity
FROM cache_profiles p
LEFT JOIN cache_entries e
  ON e.profile_id = p.profile_id
 AND e.state = 'ACTIVE'
GROUP BY p.profile_id
ORDER BY p.profile_name;

-- The access log provides hit-rate evidence without confusing a cache
-- access with an eviction decision.
SELECT
    p.profile_name,
    COUNT(*) FILTER (WHERE l.hit) AS hits,
    COUNT(*) FILTER (WHERE NOT l.hit) AS misses,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE l.hit) / NULLIF(COUNT(*), 0),
        2
    ) AS hit_rate_percent
FROM cache_profiles p
LEFT JOIN cache_access_log l
  ON l.profile_id = p.profile_id
GROUP BY p.profile_id
ORDER BY p.profile_name;
