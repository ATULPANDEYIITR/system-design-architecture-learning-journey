DROP SCHEMA IF EXISTS cap_demo CASCADE;
CREATE SCHEMA cap_demo;

SET search_path TO cap_demo;

CREATE TYPE node_status AS ENUM ('ONLINE', 'OFFLINE');
CREATE TYPE cap_mode AS ENUM ('CP', 'AP');
CREATE TYPE review_state AS ENUM (
    'PENDING',
    'APPROVED',
    'CHANGES_REQUESTED',
    'COMMENTED'
);

CREATE TABLE repository (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    cap_mode cap_mode NOT NULL
);

CREATE TABLE branch (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE cluster_node (
    node_id BIGSERIAL PRIMARY KEY,
    node_name TEXT NOT NULL UNIQUE,
    region TEXT NOT NULL,
    status node_status NOT NULL DEFAULT 'ONLINE'
);

CREATE TABLE network_partition (
    partition_id BIGSERIAL PRIMARY KEY,
    partition_name TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE node_partition_membership (
    partition_id BIGINT NOT NULL
        REFERENCES network_partition(partition_id)
        ON DELETE CASCADE,
    node_id BIGINT NOT NULL
        REFERENCES cluster_node(node_id)
        ON DELETE CASCADE,
    PRIMARY KEY (partition_id, node_id)
);

CREATE TABLE pull_request (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repository(repository_id)
        ON DELETE CASCADE,
    source_branch TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('OPEN', 'CLOSED', 'MERGED', 'DRAFT')),
    head_commit TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reviewer (
    reviewer_id BIGSERIAL PRIMARY KEY,
    reviewer_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (reviewer_name)
);

CREATE TABLE review (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES reviewer(reviewer_id),
    state review_state NOT NULL,
    commit_sha TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (pull_request_id, reviewer_id, commit_sha)
);

CREATE TABLE review_comment (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES review(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL CHECK (line_number > 0),
    comment_text TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE status_check (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    observed_commit TEXT NOT NULL,
    UNIQUE (pull_request_id, check_name, observed_commit)
);

CREATE TABLE branch_protection (
    protection_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL
        REFERENCES branch(branch_id)
        ON DELETE CASCADE,
    required_approvals INTEGER NOT NULL
        CHECK (required_approvals >= 0),
    require_status_checks BOOLEAN NOT NULL DEFAULT TRUE,
    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_deletion BOOLEAN NOT NULL DEFAULT FALSE,
    require_conversation_resolution BOOLEAN NOT NULL DEFAULT TRUE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (branch_id)
);

CREATE TABLE merge_event (
    merge_event_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_request(pull_request_id)
        ON DELETE CASCADE,
    merged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    merge_strategy TEXT NOT NULL
        CHECK (merge_strategy IN ('MERGE_COMMIT', 'SQUASH', 'REBASE')),
    merge_commit TEXT NOT NULL
);

CREATE INDEX idx_pr_repository_target
    ON pull_request(repository_id, target_branch);

CREATE INDEX idx_review_pr_state
    ON review(pull_request_id, state);

CREATE INDEX idx_status_pr_commit
    ON status_check(pull_request_id, observed_commit);

CREATE INDEX idx_partition_membership_node
    ON node_partition_membership(node_id);

INSERT INTO repository(repository_name, cap_mode)
VALUES
    ('payments-api', 'CP'),
    ('inventory-service', 'AP');

INSERT INTO branch(
    repository_id,
    branch_name,
    protected
)
SELECT
    repository_id,
    'main',
    TRUE
FROM repository;

INSERT INTO cluster_node(node_name, region)
VALUES
    ('governance-delhi', 'Delhi'),
    ('governance-mumbai', 'Mumbai'),
    ('governance-bengaluru', 'Bengaluru');

INSERT INTO reviewer(reviewer_name)
VALUES
    ('Asha'),
    ('Rahul'),
    ('Meera'),
    ('Vikram');

INSERT INTO branch_protection(
    branch_id,
    required_approvals,
    require_status_checks,
    allow_direct_push,
    allow_force_push,
    allow_deletion,
    require_conversation_resolution,
    require_linear_history
)
SELECT
    branch_id,
    CASE
        WHEN repository_id =
            (SELECT repository_id
             FROM repository
             WHERE repository_name = 'payments-api')
        THEN 2
        ELSE 1
    END,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE,
    FALSE
FROM branch
WHERE branch_name = 'main';

INSERT INTO pull_request(
    repository_id,
    source_branch,
    target_branch,
    title,
    state,
    head_commit,
    base_commit
)
VALUES
(
    (SELECT repository_id
     FROM repository
     WHERE repository_name = 'payments-api'),
    'feature/payment-timeout',
    'main',
    'Add payment timeout handling',
    'OPEN',
    'abc123',
    'main789'
),
(
    (SELECT repository_id
     FROM repository
     WHERE repository_name = 'inventory-service'),
    'feature/inventory-reconciliation',
    'main',
    'Improve inventory reconciliation',
    'OPEN',
    'def456',
    'main456'
);

INSERT INTO review(
    pull_request_id,
    reviewer_id,
    state,
    commit_sha
)
VALUES
(
    1,
    (SELECT reviewer_id FROM reviewer WHERE reviewer_name = 'Asha'),
    'APPROVED',
    'abc123'
),
(
    1,
    (SELECT reviewer_id FROM reviewer WHERE reviewer_name = 'Rahul'),
    'APPROVED',
    'abc123'
),
(
    2,
    (SELECT reviewer_id FROM reviewer WHERE reviewer_name = 'Meera'),
    'APPROVED',
    'def456'
);

INSERT INTO review_comment(
    review_id,
    file_path,
    line_number,
    comment_text,
    resolved
)
VALUES
(
    1,
    'src/payment_service.py',
    84,
    'Validate the timeout boundary before retrying.',
    TRUE
),
(
    2,
    'src/payment_service.py',
    112,
    'Confirm that retry does not duplicate the payment.',
    TRUE
),
(
    3,
    'src/reconciliation.py',
    51,
    'Document behavior when a replica is stale.',
    FALSE
);

INSERT INTO status_check(
    pull_request_id,
    check_name,
    passed,
    observed_commit
)
VALUES
(1, 'ci', TRUE, 'abc123'),
(1, 'security', TRUE, 'abc123'),
(1, 'license', TRUE, 'abc123'),
(2, 'ci', TRUE, 'def456'),
(2, 'security', FALSE, 'def456');

-- A review is stale when its approval was made against an older commit.
-- Counting approvals only for the current head prevents an old approval
-- from silently authorizing a changed changeset.
WITH current_reviews AS (
    SELECT
        r.pull_request_id,
        r.reviewer_id,
        r.state
    FROM review r
    JOIN pull_request p
        ON p.pull_request_id = r.pull_request_id
    WHERE r.commit_sha = p.head_commit
)
SELECT
    p.pull_request_id,
    p.title,
    COUNT(
        cr.reviewer_id
    ) FILTER (
        WHERE cr.state = 'APPROVED'
    ) AS current_approvals,
    bp.required_approvals,
    (
        COUNT(cr.reviewer_id) FILTER (
            WHERE cr.state = 'APPROVED'
        ) >= bp.required_approvals
    ) AS approvals_satisfied
FROM pull_request p
JOIN branch b
    ON b.repository_id = p.repository_id
   AND b.branch_name = p.target_branch
JOIN branch_protection bp
    ON bp.branch_id = b.branch_id
LEFT JOIN current_reviews cr
    ON cr.pull_request_id = p.pull_request_id
GROUP BY
    p.pull_request_id,
    p.title,
    bp.required_approvals
ORDER BY p.pull_request_id;

-- Status-check evaluation is separated from approval evaluation.
-- This makes the database expose which exact condition blocks merging.
WITH check_summary AS (
    SELECT
        p.pull_request_id,
        COUNT(sc.status_check_id) AS check_count,
        COUNT(sc.status_check_id)
            FILTER (
                WHERE sc.passed
                  AND sc.observed_commit = p.head_commit
            ) AS passed_current_checks,
        COUNT(sc.status_check_id)
            FILTER (
                WHERE NOT sc.passed
                  AND sc.observed_commit = p.head_commit
            ) AS failed_current_checks
    FROM pull_request p
    LEFT JOIN status_check sc
        ON sc.pull_request_id = p.pull_request_id
    GROUP BY p.pull_request_id
)
SELECT
    pull_request_id,
    check_count,
    passed_current_checks,
    failed_current_checks,
    failed_current_checks = 0 AS checks_satisfied
FROM check_summary
ORDER BY pull_request_id;

-- Unresolved conversations are a distinct merge condition from approval.
SELECT
    p.pull_request_id,
    p.title,
    COUNT(rc.comment_id) FILTER (
        WHERE NOT rc.resolved
    ) AS unresolved_comments
FROM pull_request p
LEFT JOIN review r
    ON r.pull_request_id = p.pull_request_id
LEFT JOIN review_comment rc
    ON rc.review_id = r.review_id
GROUP BY p.pull_request_id, p.title
ORDER BY p.pull_request_id;

-- A governance-oriented merge eligibility query combines independent
-- database facts without treating approvals and branch protection as
-- interchangeable concepts.
WITH approvals AS (
    SELECT
        p.pull_request_id,
        COUNT(DISTINCT r.reviewer_id) FILTER (
            WHERE r.state = 'APPROVED'
              AND r.commit_sha = p.head_commit
        ) AS approval_count
    FROM pull_request p
    LEFT JOIN review r
        ON r.pull_request_id = p.pull_request_id
    GROUP BY p.pull_request_id
),
checks AS (
    SELECT
        p.pull_request_id,
        COUNT(sc.status_check_id) FILTER (
            WHERE sc.passed
              AND sc.observed_commit = p.head_commit
        ) AS passed_checks,
        COUNT(sc.status_check_id) FILTER (
            WHERE NOT sc.passed
              AND sc.observed_commit = p.head_commit
        ) AS failed_checks
    FROM pull_request p
    LEFT JOIN status_check sc
        ON sc.pull_request_id = p.pull_request_id
    GROUP BY p.pull_request_id
),
conversations AS (
    SELECT
        p.pull_request_id,
        COUNT(rc.comment_id) FILTER (
            WHERE NOT rc.resolved
        ) AS unresolved_comments
    FROM pull_request p
    LEFT JOIN review r
        ON r.pull_request_id = p.pull_request_id
    LEFT JOIN review_comment rc
        ON rc.review_id = r.review_id
    GROUP BY p.pull_request_id
)
SELECT
    p.pull_request_id,
    p.title,
    bp.required_approvals,
    a.approval_count,
    c.passed_checks,
    c.failed_checks,
    conv.unresolved_comments,
    (
        p.state = 'OPEN'
        AND a.approval_count >= bp.required_approvals
        AND c.failed_checks = 0
        AND conv.unresolved_comments = 0
    ) AS merge_eligible
FROM pull_request p
JOIN branch b
    ON b.repository_id = p.repository_id
   AND b.branch_name = p.target_branch
JOIN branch_protection bp
    ON bp.branch_id = b.branch_id
JOIN approvals a
    ON a.pull_request_id = p.pull_request_id
JOIN checks c
    ON c.pull_request_id = p.pull_request_id
JOIN conversations conv
    ON conv.pull_request_id = p.pull_request_id
ORDER BY p.pull_request_id;

-- The following transaction demonstrates how a merge can be guarded by
-- database state. In a real service, application-level authorization,
-- locking strategy, and Git hosting integration would also be required.
BEGIN;

SELECT
    p.pull_request_id,
    p.state,
    p.head_commit,
    bp.required_approvals
FROM pull_request p
JOIN branch b
    ON b.repository_id = p.repository_id
   AND b.branch_name = p.target_branch
JOIN branch_protection bp
    ON bp.branch_id = b.branch_id
WHERE p.pull_request_id = 1
FOR UPDATE;

INSERT INTO merge_event(
    pull_request_id,
    merge_strategy,
    merge_commit
)
SELECT
    p.pull_request_id,
    'SQUASH',
    'merge-abc123'
FROM pull_request p
WHERE p.pull_request_id = 1
  AND p.state = 'OPEN'
  AND EXISTS (
      SELECT 1
      FROM branch b
      JOIN branch_protection bp
        ON bp.branch_id = b.branch_id
      WHERE b.repository_id = p.repository_id
        AND b.branch_name = p.target_branch
        AND bp.required_approvals <= (
            SELECT COUNT(DISTINCT r.reviewer_id)
            FROM review r
            WHERE r.pull_request_id = p.pull_request_id
              AND r.state = 'APPROVED'
              AND r.commit_sha = p.head_commit
        )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM status_check sc
      WHERE sc.pull_request_id = p.pull_request_id
        AND sc.observed_commit = p.head_commit
        AND NOT sc.passed
  )
  AND NOT EXISTS (
      SELECT 1
      FROM review r
      JOIN review_comment rc
        ON rc.review_id = r.review_id
      WHERE r.pull_request_id = p.pull_request_id
        AND NOT rc.resolved
  );

UPDATE pull_request
SET state = 'MERGED'
WHERE pull_request_id = 1
  AND EXISTS (
      SELECT 1
      FROM merge_event me
      WHERE me.pull_request_id = pull_request.pull_request_id
  );

COMMIT;

-- CAP-specific observation:
-- The relational governance model above can represent authoritative policy
-- state, but distributed replicas of this database still require a
-- replication protocol. A transaction inside one PostgreSQL instance does
-- not by itself solve a cross-node partition. During a network partition,
-- the replication architecture determines whether the system refuses a
-- write to preserve a single authoritative state or accepts independent
-- regional state and reconciles it later.
