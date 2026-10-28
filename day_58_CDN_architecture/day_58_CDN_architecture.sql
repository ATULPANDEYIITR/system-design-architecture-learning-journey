-- CDN architecture relational model and operational workflow.
-- PostgreSQL 14+ is sufficient for the features used here.

DROP SCHEMA IF EXISTS cdn CASCADE;
CREATE SCHEMA cdn;

CREATE TYPE cdn.cache_status AS ENUM (
    'HIT',
    'MISS',
    'STALE',
    'REVALIDATED',
    'BYPASS'
);

CREATE TYPE cdn.edge_status AS ENUM (
    'ACTIVE',
    'DEGRADED',
    'OFFLINE'
);

CREATE TYPE cdn.request_method AS ENUM (
    'GET',
    'HEAD',
    'POST',
    'PUT',
    'PATCH',
    'DELETE'
);

CREATE TYPE cdn.check_status AS ENUM (
    'PENDING',
    'PASS',
    'FAIL'
);

CREATE TYPE cdn.review_state AS ENUM (
    'COMMENTED',
    'APPROVED',
    'CHANGES_REQUESTED',
    'DISMISSED'
);

CREATE TABLE cdn.origin_servers (
    origin_id BIGSERIAL PRIMARY KEY,
    origin_name TEXT NOT NULL UNIQUE,
    hostname TEXT NOT NULL UNIQUE,
    healthy BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cdn.repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    origin_id BIGINT NOT NULL REFERENCES cdn.origin_servers(origin_id)
);

CREATE TABLE cdn.edge_locations (
    edge_id BIGSERIAL PRIMARY KEY,
    edge_code TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL,
    region TEXT NOT NULL,
    status cdn.edge_status NOT NULL DEFAULT 'ACTIVE',
    cache_capacity INTEGER NOT NULL CHECK (cache_capacity > 0),
    UNIQUE (city, region)
);

CREATE TABLE cdn.cache_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    policy_name TEXT NOT NULL UNIQUE,
    default_ttl_seconds INTEGER NOT NULL CHECK (default_ttl_seconds >= 0),
    min_ttl_seconds INTEGER NOT NULL DEFAULT 0
        CHECK (min_ttl_seconds >= 0),
    max_ttl_seconds INTEGER NOT NULL
        CHECK (max_ttl_seconds >= default_ttl_seconds),
    respect_no_store BOOLEAN NOT NULL DEFAULT TRUE,
    respect_private BOOLEAN NOT NULL DEFAULT TRUE,
    cache_authenticated BOOLEAN NOT NULL DEFAULT FALSE,
    ignore_tracking_parameters BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE cdn.repository_cache_policies (
    repository_id BIGINT PRIMARY KEY
        REFERENCES cdn.repositories(repository_id)
        ON DELETE CASCADE,
    policy_id BIGINT NOT NULL
        REFERENCES cdn.cache_policies(policy_id)
);

CREATE TABLE cdn.branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES cdn.repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE cdn.commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES cdn.repositories(repository_id)
        ON DELETE CASCADE,
    commit_sha CHAR(40) NOT NULL,
    parent_sha CHAR(40),
    author_name TEXT NOT NULL,
    message TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (repository_id, commit_sha)
);

CREATE TABLE cdn.pull_requests (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES cdn.repositories(repository_id)
        ON DELETE CASCADE,
    source_branch_id BIGINT NOT NULL
        REFERENCES cdn.branches(branch_id),
    target_branch_id BIGINT NOT NULL
        REFERENCES cdn.branches(branch_id),
    source_commit_id BIGINT NOT NULL
        REFERENCES cdn.commits(commit_id),
    target_commit_id BIGINT NOT NULL
        REFERENCES cdn.commits(commit_id),
    title TEXT NOT NULL,
    is_draft BOOLEAN NOT NULL DEFAULT TRUE,
    is_open BOOLEAN NOT NULL DEFAULT TRUE,
    has_conflict BOOLEAN NOT NULL DEFAULT FALSE,
    conversations_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    CHECK (source_branch_id <> target_branch_id)
);

CREATE TABLE cdn.reviewers (
    reviewer_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE cdn.reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES cdn.pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES cdn.reviewers(reviewer_id),
    state cdn.review_state NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE cdn.review_comments (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES cdn.reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER CHECK (line_number > 0),
    body TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cdn.conversations (
    conversation_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES cdn.pull_requests(pull_request_id)
        ON DELETE CASCADE,
    subject TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cdn.status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES cdn.pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status cdn.check_status NOT NULL DEFAULT 'PENDING',
    required BOOLEAN NOT NULL DEFAULT TRUE,
    completed_at TIMESTAMPTZ,
    UNIQUE (pull_request_id, check_name)
);

CREATE TABLE cdn.branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES cdn.repositories(repository_id)
        ON DELETE CASCADE,
    branch_id BIGINT NOT NULL
        REFERENCES cdn.branches(branch_id)
        ON DELETE CASCADE,
    required_reviews INTEGER NOT NULL DEFAULT 0
        CHECK (required_reviews >= 0),
    require_status_checks BOOLEAN NOT NULL DEFAULT TRUE,
    restrict_direct_push BOOLEAN NOT NULL DEFAULT TRUE,
    restrict_force_push BOOLEAN NOT NULL DEFAULT TRUE,
    restrict_branch_deletion BOOLEAN NOT NULL DEFAULT TRUE,
    require_conversation_resolution BOOLEAN NOT NULL DEFAULT TRUE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_id)
);

CREATE TABLE cdn.approval_requirements (
    requirement_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES cdn.branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    role_name TEXT NOT NULL,
    minimum_approvals INTEGER NOT NULL CHECK (minimum_approvals > 0),
    UNIQUE (policy_id, role_name)
);

CREATE TABLE cdn.edge_cache_entries (
    cache_entry_id BIGSERIAL PRIMARY KEY,
    edge_id BIGINT NOT NULL
        REFERENCES cdn.edge_locations(edge_id)
        ON DELETE CASCADE,
    cache_key TEXT NOT NULL,
    request_path TEXT NOT NULL,
    response_etag TEXT NOT NULL,
    content_type TEXT NOT NULL,
    cache_control TEXT NOT NULL,
    stored_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_accessed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (edge_id, cache_key)
);

CREATE TABLE cdn.request_log (
    request_id BIGSERIAL PRIMARY KEY,
    edge_id BIGINT REFERENCES cdn.edge_locations(edge_id),
    origin_id BIGINT REFERENCES cdn.origin_servers(origin_id),
    method cdn.request_method NOT NULL,
    host TEXT NOT NULL,
    request_path TEXT NOT NULL,
    cache_key TEXT,
    cache_status cdn.cache_status NOT NULL,
    response_status INTEGER NOT NULL CHECK (response_status BETWEEN 100 AND 599),
    authenticated BOOLEAN NOT NULL DEFAULT FALSE,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_request_log_path_time
    ON cdn.request_log (request_path, requested_at DESC);

CREATE INDEX idx_request_log_edge_status
    ON cdn.request_log (edge_id, cache_status);

CREATE INDEX idx_cache_entries_expiry
    ON cdn.edge_cache_entries (expires_at);

CREATE INDEX idx_reviews_pr_state
    ON cdn.reviews (pull_request_id, state, stale, dismissed);

CREATE INDEX idx_status_checks_pr_status
    ON cdn.status_checks (pull_request_id, status, required);

CREATE OR REPLACE FUNCTION cdn.validate_pull_request()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_repository BIGINT;
    target_repository BIGINT;
BEGIN
    SELECT repository_id
      INTO source_repository
      FROM cdn.branches
     WHERE branch_id = NEW.source_branch_id;

    SELECT repository_id
      INTO target_repository
      FROM cdn.branches
     WHERE branch_id = NEW.target_branch_id;

    IF source_repository IS NULL
       OR target_repository IS NULL THEN
        RAISE EXCEPTION 'Pull Request references a missing branch';
    END IF;

    IF source_repository <> target_repository
       OR source_repository <> NEW.repository_id THEN
        RAISE EXCEPTION
            'Source, target, and Pull Request repositories must match';
    END IF;

    IF NEW.closed_at IS NOT NULL AND NEW.is_open THEN
        RAISE EXCEPTION
            'An open Pull Request cannot have closed_at set';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_pull_request
BEFORE INSERT OR UPDATE
ON cdn.pull_requests
FOR EACH ROW
EXECUTE FUNCTION cdn.validate_pull_request();

CREATE OR REPLACE FUNCTION cdn.prevent_invalid_cache_entry()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.expires_at < NEW.stored_at THEN
        RAISE EXCEPTION 'Cache expiration cannot precede storage time';
    END IF;

    IF NEW.last_accessed_at < NEW.stored_at THEN
        RAISE EXCEPTION 'Last access cannot precede storage time';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_cache_entry
BEFORE INSERT OR UPDATE
ON cdn.edge_cache_entries
FOR EACH ROW
EXECUTE FUNCTION cdn.prevent_invalid_cache_entry();

CREATE OR REPLACE FUNCTION cdn.merge_eligibility(
    p_pull_request_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT,
    valid_approvals INTEGER,
    failed_required_checks INTEGER,
    unresolved_conversations INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    pr RECORD;
    policy RECORD;
BEGIN
    SELECT *
      INTO pr
      FROM cdn.pull_requests
     WHERE pull_request_id = p_pull_request_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request does not exist', 0, 0, 0;
        RETURN;
    END IF;

    SELECT bp.*
      INTO policy
      FROM cdn.branch_protection_policies bp
     WHERE bp.repository_id = pr.repository_id
       AND bp.branch_id = pr.target_branch_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Target branch has no protection policy', 0, 0, 0;
        RETURN;
    END IF;

    SELECT
        COUNT(*) FILTER (
            WHERE r.state = 'APPROVED'
              AND NOT r.stale
              AND NOT r.dismissed
              AND rv.active
        ),
        0
      INTO valid_approvals, failed_required_checks
      FROM cdn.reviews r
      JOIN cdn.reviewers rv
        ON rv.reviewer_id = r.reviewer_id
     WHERE r.pull_request_id = p_pull_request_id;

    SELECT COUNT(*)
      INTO failed_required_checks
      FROM cdn.status_checks sc
     WHERE sc.pull_request_id = p_pull_request_id
       AND sc.required
       AND sc.status <> 'PASS';

    SELECT COUNT(*)
      INTO unresolved_conversations
      FROM cdn.conversations c
     WHERE c.pull_request_id = p_pull_request_id
       AND NOT c.resolved;

    IF NOT pr.is_open THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request is closed',
               valid_approvals,
               failed_required_checks,
               unresolved_conversations;
        RETURN;
    END IF;

    IF pr.is_draft THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request is still a draft',
               valid_approvals,
               failed_required_checks,
               unresolved_conversations;
        RETURN;
    END IF;

    IF pr.has_conflict THEN
        RETURN QUERY
        SELECT FALSE, 'Merge conflict must be resolved',
               valid_approvals,
               failed_required_checks,
               unresolved_conversations;
        RETURN;
    END IF;

    IF policy.require_status_checks
       AND failed_required_checks > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'Required status checks are not passing',
               valid_approvals,
               failed_required_checks,
               unresolved_conversations;
        RETURN;
    END IF;

    IF policy.require_conversation_resolution
       AND unresolved_conversations > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'Unresolved review conversations remain',
               valid_approvals,
               failed_required_checks,
               unresolved_conversations;
        RETURN;
    END IF;

    IF valid_approvals < policy.required_reviews THEN
        RETURN QUERY
        SELECT FALSE, 'Required approvals are not satisfied',
               valid_approvals,
               failed_required_checks,
               unresolved_conversations;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT TRUE, 'Merge eligible',
           valid_approvals,
           failed_required_checks,
           unresolved_conversations;
END;
$$;

CREATE VIEW cdn.edge_cache_health AS
SELECT
    e.edge_code,
    e.city,
    e.region,
    e.status,
    e.cache_capacity,
    COUNT(ce.cache_entry_id) AS cached_objects,
    COUNT(ce.cache_entry_id)
        FILTER (WHERE ce.expires_at <= now()) AS stale_objects
FROM cdn.edge_locations e
LEFT JOIN cdn.edge_cache_entries ce
       ON ce.edge_id = e.edge_id
GROUP BY
    e.edge_id,
    e.edge_code,
    e.city,
    e.region,
    e.status,
    e.cache_capacity;

CREATE VIEW cdn.cache_performance AS
SELECT
    e.edge_code,
    COUNT(*) AS requests,
    COUNT(*) FILTER (
        WHERE rl.cache_status = 'HIT'
    ) AS hits,
    COUNT(*) FILTER (
        WHERE rl.cache_status = 'MISS'
    ) AS misses,
    COUNT(*) FILTER (
        WHERE rl.cache_status = 'REVALIDATED'
    ) AS revalidations,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE rl.cache_status = 'HIT'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS hit_percentage
FROM cdn.request_log rl
JOIN cdn.edge_locations e
  ON e.edge_id = rl.edge_id
GROUP BY e.edge_code;

INSERT INTO cdn.origin_servers (
    origin_name,
    hostname
)
VALUES (
    'primary-origin',
    'origin.internal.example'
);

INSERT INTO cdn.repositories (
    repository_name,
    default_branch,
    origin_id
)
SELECT
    'cdn-platform',
    'main',
    origin_id
FROM cdn.origin_servers
WHERE origin_name = 'primary-origin';

INSERT INTO cdn.edge_locations (
    edge_code,
    city,
    region,
    cache_capacity
)
VALUES
    ('blr', 'Bengaluru', 'India', 1000),
    ('fra', 'Frankfurt', 'Europe', 1000),
    ('iad', 'Ashburn', 'North America', 1000);

INSERT INTO cdn.cache_policies (
    policy_name,
    default_ttl_seconds,
    min_ttl_seconds,
    max_ttl_seconds,
    cache_authenticated
)
VALUES (
    'static-assets',
    60,
    0,
    3600,
    FALSE
);

INSERT INTO cdn.repository_cache_policies (
    repository_id,
    policy_id
)
SELECT
    r.repository_id,
    cp.policy_id
FROM cdn.repositories r
CROSS JOIN cdn.cache_policies cp
WHERE r.repository_name = 'cdn-platform'
  AND cp.policy_name = 'static-assets';

INSERT INTO cdn.branches (
    repository_id,
    branch_name,
    protected
)
SELECT repository_id, branch_name, protected
FROM (
    SELECT
        repository_id,
        'main'::TEXT AS branch_name,
        TRUE AS protected
    FROM cdn.repositories
    WHERE repository_name = 'cdn-platform'

    UNION ALL

    SELECT
        repository_id,
        'feature/cache-policy'::TEXT,
        FALSE
    FROM cdn.repositories
    WHERE repository_name = 'cdn-platform'
) branches;

INSERT INTO cdn.commits (
    repository_id,
    commit_sha,
    parent_sha,
    author_name,
    message,
    committed_at
)
SELECT
    repository_id,
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    NULL,
    'release-engineer',
    'Initial CDN configuration',
    now() - INTERVAL '2 days'
FROM cdn.repositories
WHERE repository_name = 'cdn-platform';

INSERT INTO cdn.commits (
    repository_id,
    commit_sha,
    parent_sha,
    author_name,
    message,
    committed_at
)
SELECT
    r.repository_id,
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'developer',
    'Add cache policy validation',
    now() - INTERVAL '1 hour'
FROM cdn.repositories r
WHERE r.repository_name = 'cdn-platform';

INSERT INTO cdn.pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    source_commit_id,
    target_commit_id,
    title,
    is_draft,
    is_open,
    has_conflict,
    conversations_resolved
)
SELECT
    r.repository_id,
    source.branch_id,
    target.branch_id,
    source_commit.commit_id,
    target_commit.commit_id,
    'Implement CDN cache policy',
    FALSE,
    TRUE,
    FALSE,
    TRUE
FROM cdn.repositories r
JOIN cdn.branches source
  ON source.repository_id = r.repository_id
 AND source.branch_name = 'feature/cache-policy'
JOIN cdn.branches target
  ON target.repository_id = r.repository_id
 AND target.branch_name = 'main'
JOIN cdn.commits source_commit
  ON source_commit.commit_sha =
     'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
JOIN cdn.commits target_commit
  ON target_commit.commit_sha =
     'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
WHERE r.repository_name = 'cdn-platform';

INSERT INTO cdn.reviewers (username)
VALUES
    ('reviewer-a'),
    ('reviewer-b'),
    ('reviewer-c');

INSERT INTO cdn.reviews (
    pull_request_id,
    reviewer_id,
    state,
    stale,
    dismissed
)
SELECT
    pr.pull_request_id,
    rv.reviewer_id,
    CASE rv.username
        WHEN 'reviewer-a' THEN 'APPROVED'::cdn.review_state
        WHEN 'reviewer-b' THEN 'APPROVED'::cdn.review_state
        ELSE 'COMMENTED'::cdn.review_state
    END,
    FALSE,
    FALSE
FROM cdn.pull_requests pr
CROSS JOIN cdn.reviewers rv
WHERE pr.title = 'Implement CDN cache policy';

INSERT INTO cdn.review_comments (
    review_id,
    file_path,
    line_number,
    body,
    resolved
)
SELECT
    r.review_id,
    'cdn/cache-policy.yaml',
    42,
    'Cache key must ignore known tracking parameters.',
    TRUE
FROM cdn.reviews r
JOIN cdn.reviewers rv
  ON rv.reviewer_id = r.reviewer_id
WHERE rv.username = 'reviewer-a';

INSERT INTO cdn.conversations (
    pull_request_id,
    subject,
    resolved
)
SELECT
    pull_request_id,
    'Cache key normalization',
    TRUE
FROM cdn.pull_requests
WHERE title = 'Implement CDN cache policy';

INSERT INTO cdn.status_checks (
    pull_request_id,
    check_name,
    status,
    required,
    completed_at
)
SELECT
    pull_request_id,
    check_name,
    'PASS',
    TRUE,
    now()
FROM cdn.pull_requests
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('security-scan'),
        ('cdn-integration')
) checks(check_name)
WHERE title = 'Implement CDN cache policy';

INSERT INTO cdn.branch_protection_policies (
    repository_id,
    branch_id,
    required_reviews,
    require_status_checks,
    restrict_direct_push,
    restrict_force_push,
    restrict_branch_deletion,
    require_conversation_resolution,
    require_linear_history
)
SELECT
    r.repository_id,
    b.branch_id,
    2,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE
FROM cdn.repositories r
JOIN cdn.branches b
  ON b.repository_id = r.repository_id
 AND b.branch_name = 'main'
WHERE r.repository_name = 'cdn-platform';

INSERT INTO cdn.approval_requirements (
    policy_id,
    role_name,
    minimum_approvals
)
SELECT
    policy_id,
    'maintainer',
    2
FROM cdn.branch_protection_policies;

INSERT INTO cdn.edge_cache_entries (
    edge_id,
    cache_key,
    request_path,
    response_etag,
    content_type,
    cache_control,
    stored_at,
    expires_at,
    last_accessed_at
)
SELECT
    e.edge_id,
    'example.test|GET|/assets/app.js|',
    '/assets/app.js',
    'etag-app-42',
    'application/javascript',
    'public, max-age=120',
    now() - INTERVAL '20 seconds',
    now() + INTERVAL '100 seconds',
    now()
FROM cdn.edge_locations e
WHERE e.edge_code = 'blr';

INSERT INTO cdn.request_log (
    edge_id,
    origin_id,
    method,
    host,
    request_path,
    cache_key,
    cache_status,
    response_status,
    authenticated
)
SELECT
    e.edge_id,
    o.origin_id,
    'GET',
    'example.test',
    '/assets/app.js',
    'example.test|GET|/assets/app.js|',
    'HIT',
    200,
    FALSE
FROM cdn.edge_locations e
CROSS JOIN cdn.origin_servers o
WHERE e.edge_code = 'blr'
  AND o.origin_name = 'primary-origin';

INSERT INTO cdn.request_log (
    edge_id,
    origin_id,
    method,
    host,
    request_path,
    cache_key,
    cache_status,
    response_status,
    authenticated
)
SELECT
    e.edge_id,
    o.origin_id,
    'GET',
    'example.test',
    '/assets/missing.js',
    'example.test|GET|/assets/missing.js|',
    'MISS',
    404,
    FALSE
FROM cdn.edge_locations e
CROSS JOIN cdn.origin_servers o
WHERE e.edge_code = 'blr'
  AND o.origin_name = 'primary-origin';

-- Transactional update representing an atomic cache purge.
BEGIN;

DELETE FROM cdn.edge_cache_entries
WHERE request_path = '/assets/app.js';

COMMIT;

-- Operational retrieval.
SELECT
    edge_code,
    city,
    region,
    status,
    cache_capacity,
    cached_objects,
    stale_objects
FROM cdn.edge_cache_health
ORDER BY region, city;

-- Cache hit-rate reporting.
SELECT
    edge_code,
    requests,
    hits,
    misses,
    revalidations,
    hit_percentage
FROM cdn.cache_performance
ORDER BY hit_percentage DESC;

-- Review and approval evaluation.
SELECT
    pr.pull_request_id,
    pr.title,
    me.eligible,
    me.reason,
    me.valid_approvals,
    me.failed_required_checks,
    me.unresolved_conversations
FROM cdn.pull_requests pr
CROSS JOIN LATERAL cdn.merge_eligibility(
    pr.pull_request_id
) me
ORDER BY pr.pull_request_id;

-- Find expired cache objects that can be evicted or revalidated.
SELECT
    e.edge_code,
    ce.cache_key,
    ce.request_path,
    ce.expires_at
FROM cdn.edge_cache_entries ce
JOIN cdn.edge_locations e
  ON e.edge_id = ce.edge_id
WHERE ce.expires_at <= now()
ORDER BY ce.expires_at;

-- Identify origin pressure caused by cache misses.
SELECT
    date_trunc('hour', requested_at) AS hour,
    COUNT(*) AS requests,
    COUNT(*) FILTER (
        WHERE cache_status = 'MISS'
    ) AS misses,
    COUNT(*) FILTER (
        WHERE cache_status = 'BYPASS'
    ) AS bypasses,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE cache_status = 'MISS'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS miss_percentage
FROM cdn.request_log
GROUP BY date_trunc('hour', requested_at)
ORDER BY hour;
