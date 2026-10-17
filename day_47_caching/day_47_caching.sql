DROP SCHEMA IF EXISTS caching_demo CASCADE;
CREATE SCHEMA caching_demo;
SET search_path TO caching_demo;

-- PostgreSQL model for a repository platform whose expensive merge-eligibility
-- evaluations can be cached. The database remains authoritative for repository
-- state; cached decisions are represented separately with explicit validity
-- metadata rather than being mistaken for source-of-truth records.

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,
    head_commit_sha TEXT NOT NULL,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE contributors (
    contributor_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    sha TEXT NOT NULL,
    author_id BIGINT NOT NULL REFERENCES contributors(contributor_id),
    parent_sha TEXT,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repository_id, sha)
);

CREATE TABLE pull_requests (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    number INTEGER NOT NULL,
    author_id BIGINT NOT NULL REFERENCES contributors(contributor_id),
    source_branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    head_commit_id BIGINT NOT NULL REFERENCES commits(commit_id),
    state TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (state IN ('DRAFT', 'OPEN', 'CLOSED', 'MERGED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repository_id, number)
);

CREATE TABLE reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES contributors(contributor_id),
    state TEXT NOT NULL
        CHECK (
            state IN (
                'COMMENTED',
                'CHANGES_REQUESTED',
                'APPROVED',
                'DISMISSED'
            )
        ),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE review_comments (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL REFERENCES reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER CHECK (line_number > 0),
    body TEXT NOT NULL CHECK (length(trim(body)) > 0),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('PENDING', 'PASSED', 'FAILED')),
    completed_at TIMESTAMPTZ,
    UNIQUE (pull_request_id, check_name)
);

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    policy_version INTEGER NOT NULL DEFAULT 1
        CHECK (policy_version > 0),
    required_approvals INTEGER NOT NULL DEFAULT 0
        CHECK (required_approvals >= 0),
    require_conversation_resolution BOOLEAN NOT NULL DEFAULT FALSE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    prohibit_direct_push BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_force_push BOOLEAN NOT NULL DEFAULT TRUE,
    prohibit_deletion BOOLEAN NOT NULL DEFAULT TRUE,
    allow_administrator_bypass BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (branch_id, policy_version)
);

CREATE TABLE required_checks (
    policy_id BIGINT NOT NULL REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    PRIMARY KEY (policy_id, check_name)
);

CREATE TABLE merge_decision_cache (
    cache_key TEXT PRIMARY KEY,
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    policy_version INTEGER NOT NULL,
    head_commit_id BIGINT NOT NULL REFERENCES commits(commit_id),
    decision TEXT NOT NULL CHECK (decision IN ('ELIGIBLE', 'BLOCKED')),
    reason JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    invalidated_at TIMESTAMPTZ
);

CREATE INDEX idx_pull_requests_target_state
    ON pull_requests(target_branch_id, state);

CREATE INDEX idx_reviews_pr_state
    ON reviews(pull_request_id, state);

CREATE INDEX idx_status_checks_pr_state
    ON status_checks(pull_request_id, state);

CREATE INDEX idx_cache_validity
    ON merge_decision_cache(pull_request_id, expires_at)
    WHERE invalidated_at IS NULL;

INSERT INTO repositories (repository_name)
VALUES ('platform-governance');

INSERT INTO contributors (username)
VALUES
    ('alice'),
    ('bob'),
    ('carol'),
    ('dave');

INSERT INTO branches (
    repository_id,
    branch_name,
    is_protected,
    head_commit_sha
)
SELECT
    repository_id,
    'main',
    TRUE,
    '0000001'
FROM repositories
WHERE repository_name = 'platform-governance';

INSERT INTO branches (
    repository_id,
    branch_name,
    is_protected,
    head_commit_sha
)
SELECT
    repository_id,
    'feature/cache-policy',
    FALSE,
    'abc1234'
FROM repositories
WHERE repository_name = 'platform-governance';

INSERT INTO commits (
    repository_id,
    sha,
    author_id,
    parent_sha
)
SELECT
    r.repository_id,
    'abc1234',
    c.contributor_id,
    NULL
FROM repositories r
JOIN contributors c ON c.username = 'alice'
WHERE r.repository_name = 'platform-governance';

INSERT INTO commits (
    repository_id,
    sha,
    author_id,
    parent_sha
)
SELECT
    r.repository_id,
    '0000001',
    c.contributor_id,
    NULL
FROM repositories r
JOIN contributors c ON c.username = 'dave'
WHERE r.repository_name = 'platform-governance';

INSERT INTO pull_requests (
    repository_id,
    number,
    author_id,
    source_branch_id,
    target_branch_id,
    head_commit_id,
    state
)
SELECT
    r.repository_id,
    42,
    author.contributor_id,
    source.branch_id,
    target.branch_id,
    commit_row.commit_id,
    'OPEN'
FROM repositories r
JOIN contributors author
    ON author.username = 'alice'
JOIN branches source
    ON source.repository_id = r.repository_id
    AND source.branch_name = 'feature/cache-policy'
JOIN branches target
    ON target.repository_id = r.repository_id
    AND target.branch_name = 'main'
JOIN commits commit_row
    ON commit_row.repository_id = r.repository_id
    AND commit_row.sha = 'abc1234'
WHERE r.repository_name = 'platform-governance';

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    state
)
SELECT
    pr.pull_request_id,
    c.contributor_id,
    'APPROVED'
FROM pull_requests pr
JOIN contributors c
    ON c.username IN ('bob', 'carol')
WHERE pr.number = 42;

INSERT INTO review_comments (
    review_id,
    file_path,
    line_number,
    body,
    resolved
)
SELECT
    r.review_id,
    'src/cache_policy.cpp',
    48,
    'The invalidation path must run after policy mutations.',
    TRUE
FROM reviews r
JOIN contributors c
    ON c.contributor_id = r.reviewer_id
WHERE r.pull_request_id = (
    SELECT pull_request_id
    FROM pull_requests
    WHERE number = 42
)
AND c.username = 'bob';

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    state,
    completed_at
)
SELECT
    pull_request_id,
    check_name,
    'PASSED',
    CURRENT_TIMESTAMP
FROM pull_requests
CROSS JOIN (
    VALUES
        ('build'),
        ('security-scan')
) AS checks(check_name)
WHERE number = 42;

INSERT INTO branch_protection_policies (
    branch_id,
    policy_version,
    required_approvals,
    require_conversation_resolution,
    require_linear_history,
    prohibit_direct_push,
    prohibit_force_push,
    prohibit_deletion,
    allow_administrator_bypass
)
SELECT
    branch_id,
    1,
    2,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE
FROM branches
WHERE branch_name = 'main';

INSERT INTO required_checks (policy_id, check_name)
SELECT policy_id, 'build'
FROM branch_protection_policies
WHERE policy_version = 1;

INSERT INTO required_checks (policy_id, check_name)
SELECT policy_id, 'security-scan'
FROM branch_protection_policies
WHERE policy_version = 1;

-- The authoritative merge-eligibility query separates Pull Request state,
-- approval state, unresolved review discussions, and required status checks.
-- A cache entry must only be trusted while its policy version and head commit
-- still match the authoritative state.

WITH active_policy AS (
    SELECT
        b.branch_id,
        b.branch_name,
        p.policy_id,
        p.policy_version,
        p.required_approvals,
        p.require_conversation_resolution
    FROM branches b
    JOIN branch_protection_policies p
        ON p.branch_id = b.branch_id
    WHERE b.branch_name = 'main'
      AND p.policy_version = (
          SELECT MAX(p2.policy_version)
          FROM branch_protection_policies p2
          WHERE p2.branch_id = b.branch_id
      )
),
approval_count AS (
    SELECT
        pr.pull_request_id,
        COUNT(*) FILTER (
            WHERE r.state = 'APPROVED'
        ) AS approvals
    FROM pull_requests pr
    LEFT JOIN reviews r
        ON r.pull_request_id = pr.pull_request_id
    WHERE pr.number = 42
    GROUP BY pr.pull_request_id
),
unresolved_comments AS (
    SELECT
        pr.pull_request_id,
        COUNT(rc.comment_id) AS unresolved_count
    FROM pull_requests pr
    LEFT JOIN reviews r
        ON r.pull_request_id = pr.pull_request_id
    LEFT JOIN review_comments rc
        ON rc.review_id = r.review_id
        AND rc.resolved = FALSE
    WHERE pr.number = 42
    GROUP BY pr.pull_request_id
),
check_state AS (
    SELECT
        pr.pull_request_id,
        COUNT(*) FILTER (WHERE sc.state = 'PASSED') AS passed_checks,
        COUNT(*) FILTER (WHERE sc.state <> 'PASSED') AS non_passing_checks
    FROM pull_requests pr
    LEFT JOIN status_checks sc
        ON sc.pull_request_id = pr.pull_request_id
    WHERE pr.number = 42
    GROUP BY pr.pull_request_id
)
SELECT
    pr.number,
    pr.state,
    ap.policy_version,
    ac.approvals,
    ap.required_approvals,
    uc.unresolved_count,
    cs.passed_checks,
    cs.non_passing_checks,
    CASE
        WHEN pr.state <> 'OPEN'
            THEN 'BLOCKED'
        WHEN ac.approvals < ap.required_approvals
            THEN 'BLOCKED'
        WHEN ap.require_conversation_resolution
             AND uc.unresolved_count > 0
            THEN 'BLOCKED'
        WHEN cs.non_passing_checks > 0
            THEN 'BLOCKED'
        ELSE 'ELIGIBLE'
    END AS merge_eligibility
FROM pull_requests pr
JOIN active_policy ap
    ON ap.branch_id = pr.target_branch_id
JOIN approval_count ac
    ON ac.pull_request_id = pr.pull_request_id
JOIN unresolved_comments uc
    ON uc.pull_request_id = pr.pull_request_id
JOIN check_state cs
    ON cs.pull_request_id = pr.pull_request_id
WHERE pr.number = 42;

-- Cache write: the key includes policy version and head commit identity.
-- This prevents a cached decision produced under an older policy or older
-- Pull Request revision from being silently reused.

INSERT INTO merge_decision_cache (
    cache_key,
    pull_request_id,
    policy_version,
    head_commit_id,
    decision,
    reason,
    expires_at
)
SELECT
    'pr:42:policy:1:commit:' || pr.head_commit_id,
    pr.pull_request_id,
    bp.policy_version,
    pr.head_commit_id,
    'ELIGIBLE',
    '[]'::jsonb,
    CURRENT_TIMESTAMP + INTERVAL '30 seconds'
FROM pull_requests pr
JOIN branch_protection_policies bp
    ON bp.branch_id = pr.target_branch_id
WHERE pr.number = 42
ON CONFLICT (cache_key)
DO UPDATE SET
    decision = EXCLUDED.decision,
    reason = EXCLUDED.reason,
    expires_at = EXCLUDED.expires_at,
    invalidated_at = NULL;

-- A valid cache lookup requires all freshness dimensions to agree.
SELECT
    cache_key,
    decision,
    reason,
    created_at,
    expires_at
FROM merge_decision_cache
WHERE pull_request_id = (
    SELECT pull_request_id
    FROM pull_requests
    WHERE number = 42
)
AND invalidated_at IS NULL
AND expires_at > CURRENT_TIMESTAMP
AND policy_version = (
    SELECT MAX(policy_version)
    FROM branch_protection_policies bp
    JOIN pull_requests pr2
        ON pr2.target_branch_id = bp.branch_id
    WHERE pr2.number = 42
)
AND head_commit_id = (
    SELECT head_commit_id
    FROM pull_requests
    WHERE number = 42
);

-- Approval dismissal is a correctness-sensitive mutation. The cached merge
-- decision is explicitly invalidated rather than waiting for TTL expiration.

BEGIN;

UPDATE reviews
SET state = 'DISMISSED',
    submitted_at = CURRENT_TIMESTAMP
WHERE pull_request_id = (
    SELECT pull_request_id
    FROM pull_requests
    WHERE number = 42
)
AND reviewer_id = (
    SELECT contributor_id
    FROM contributors
    WHERE username = 'bob'
)
AND state = 'APPROVED';

UPDATE merge_decision_cache
SET invalidated_at = CURRENT_TIMESTAMP
WHERE pull_request_id = (
    SELECT pull_request_id
    FROM pull_requests
    WHERE number = 42
)
AND invalidated_at IS NULL;

COMMIT;

-- After the mutation, the database exposes the new authoritative state.
SELECT
    pr.number,
    COUNT(*) FILTER (WHERE r.state = 'APPROVED') AS current_approvals,
    COUNT(*) FILTER (WHERE r.state = 'DISMISSED') AS dismissed_reviews
FROM pull_requests pr
LEFT JOIN reviews r
    ON r.pull_request_id = pr.pull_request_id
WHERE pr.number = 42
GROUP BY pr.number;

-- Demonstrate why a cache should not contain an authorization decision forever.
-- Expired or explicitly invalidated entries are visible for operational cleanup.
DELETE FROM merge_decision_cache
WHERE expires_at <= CURRENT_TIMESTAMP
   OR invalidated_at IS NOT NULL;

SELECT
    COUNT(*) AS active_cache_entries
FROM merge_decision_cache
WHERE invalidated_at IS NULL;
