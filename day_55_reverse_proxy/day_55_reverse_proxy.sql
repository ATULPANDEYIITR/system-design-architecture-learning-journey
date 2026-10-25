DROP SCHEMA IF EXISTS reverse_proxy_demo CASCADE;
CREATE SCHEMA reverse_proxy_demo;

SET search_path TO reverse_proxy_demo, public;

-- A reverse proxy terminates the client connection and then creates
-- a separate upstream request. The schema deliberately keeps client
-- transport, routing, backend health, and policy information separate.

CREATE TYPE protocol_type AS ENUM ('http', 'https');
CREATE TYPE server_state AS ENUM ('healthy', 'unhealthy', 'draining');
CREATE TYPE request_state AS ENUM (
    'received',
    'routing',
    'forwarded',
    'completed',
    'rejected',
    'failed'
);
CREATE TYPE review_status AS ENUM (
    'pending',
    'passing',
    'failing',
    'unknown'
);

CREATE TABLE certificates (
    certificate_id BIGSERIAL PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,
    issuer TEXT NOT NULL,
    minimum_tls_version TEXT NOT NULL
        CHECK (minimum_tls_version IN ('TLS1.2', 'TLS1.3')),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE branches (
    branch_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE upstream_groups (
    upstream_group_id BIGSERIAL PRIMARY KEY,
    group_name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE upstream_servers (
    upstream_server_id BIGSERIAL PRIMARY KEY,
    upstream_group_id BIGINT NOT NULL
        REFERENCES upstream_groups(upstream_group_id)
        ON DELETE CASCADE,
    server_name TEXT NOT NULL,
    address INET NOT NULL,
    port INTEGER NOT NULL
        CHECK (port BETWEEN 1 AND 65535),
    weight INTEGER NOT NULL DEFAULT 1
        CHECK (weight > 0),
    state server_state NOT NULL DEFAULT 'healthy',
    active_connections INTEGER NOT NULL DEFAULT 0
        CHECK (active_connections >= 0),
    request_count BIGINT NOT NULL DEFAULT 0
        CHECK (request_count >= 0),
    UNIQUE (upstream_group_id, server_name)
);

CREATE TABLE routes (
    route_id BIGSERIAL PRIMARY KEY,
    hostname TEXT NOT NULL,
    path_prefix TEXT NOT NULL,
    upstream_group_id BIGINT NOT NULL
        REFERENCES upstream_groups(upstream_group_id),
    certificate_id BIGINT
        REFERENCES certificates(certificate_id),
    UNIQUE (hostname, path_prefix)
);

CREATE TABLE commits (
    commit_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    commit_sha CHAR(40) NOT NULL,
    author TEXT NOT NULL,
    message TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repository_id, commit_sha)
);

CREATE TABLE pull_requests (
    pull_request_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    source_head_commit_id BIGINT
        REFERENCES commits(commit_id),
    title TEXT NOT NULL,
    draft BOOLEAN NOT NULL DEFAULT FALSE,
    open BOOLEAN NOT NULL DEFAULT TRUE,
    mergeable BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMPTZ,
    merged_at TIMESTAMPTZ,
    CHECK (source_branch_id <> target_branch_id)
);

CREATE TABLE reviewers (
    reviewer_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE reviews (
    review_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id),
    state TEXT NOT NULL
        CHECK (
            state IN (
                'commented',
                'approved',
                'changes_requested',
                'dismissed'
            )
        ),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    stale BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE review_comments (
    comment_id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER
        CHECK (line_number > 0),
    body TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE conversations (
    conversation_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    topic TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE status_checks (
    status_check_id BIGSERIAL PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status review_status NOT NULL DEFAULT 'unknown',
    completed_at TIMESTAMPTZ,
    UNIQUE (pull_request_id, check_name)
);

CREATE TABLE branch_protection_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,
    require_pull_request BOOLEAN NOT NULL DEFAULT TRUE,
    required_approvals INTEGER NOT NULL DEFAULT 1
        CHECK (required_approvals >= 0),
    require_status_checks BOOLEAN NOT NULL DEFAULT TRUE,
    require_conversation_resolution BOOLEAN NOT NULL DEFAULT TRUE,
    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_branch_deletion BOOLEAN NOT NULL DEFAULT FALSE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    allow_admin_bypass BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE approval_requirements (
    requirement_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    role_name TEXT NOT NULL,
    minimum_approvals INTEGER NOT NULL
        CHECK (minimum_approvals > 0),
    UNIQUE (policy_id, role_name)
);

CREATE TABLE proxy_requests (
    request_id BIGSERIAL PRIMARY KEY,
    client_ip INET NOT NULL,
    hostname TEXT NOT NULL,
    method TEXT NOT NULL,
    request_path TEXT NOT NULL,
    protocol protocol_type NOT NULL,
    state request_state NOT NULL DEFAULT 'received',
    selected_route_id BIGINT REFERENCES routes(route_id),
    selected_upstream_id BIGINT
        REFERENCES upstream_servers(upstream_server_id),
    response_status INTEGER
        CHECK (response_status BETWEEN 100 AND 599),
    request_bytes INTEGER NOT NULL DEFAULT 0
        CHECK (request_bytes >= 0),
    duration_ms NUMERIC(12,3),
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_routes_hostname_path
    ON routes (hostname, path_prefix);

CREATE INDEX idx_upstream_group_state
    ON upstream_servers (upstream_group_id, state);

CREATE INDEX idx_pr_repository_target
    ON pull_requests (repository_id, target_branch_id, open);

CREATE INDEX idx_reviews_pr_state
    ON reviews (pull_request_id, state, stale);

CREATE INDEX idx_status_checks_pr_status
    ON status_checks (pull_request_id, status);

CREATE INDEX idx_proxy_requests_received
    ON proxy_requests (received_at);

CREATE OR REPLACE FUNCTION enforce_pull_request_target()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_is_protected BOOLEAN;
    policy_requires_pr BOOLEAN;
BEGIN
    SELECT b.protected
    INTO target_is_protected
    FROM branches b
    WHERE b.branch_id = NEW.target_branch_id;

    IF target_is_protected THEN
        SELECT p.require_pull_request
        INTO policy_requires_pr
        FROM branch_protection_policies p
        WHERE p.branch_id = NEW.target_branch_id;

        IF COALESCE(policy_requires_pr, TRUE) = FALSE THEN
            RETURN NEW;
        END IF;

        IF NEW.source_branch_id = NEW.target_branch_id THEN
            RAISE EXCEPTION
                'protected branch cannot be its own pull request source';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_pull_request_target
BEFORE INSERT OR UPDATE ON pull_requests
FOR EACH ROW
EXECUTE FUNCTION enforce_pull_request_target();

CREATE OR REPLACE FUNCTION prevent_invalid_review()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    reviewer_active BOOLEAN;
    pr_open BOOLEAN;
BEGIN
    SELECT active
    INTO reviewer_active
    FROM reviewers
    WHERE reviewer_id = NEW.reviewer_id;

    IF NOT COALESCE(reviewer_active, FALSE) THEN
        RAISE EXCEPTION 'inactive reviewer cannot submit a review';
    END IF;

    SELECT open
    INTO pr_open
    FROM pull_requests
    WHERE pull_request_id = NEW.pull_request_id;

    IF NOT COALESCE(pr_open, FALSE) THEN
        RAISE EXCEPTION 'closed pull request cannot receive a review';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_review
BEFORE INSERT OR UPDATE ON reviews
FOR EACH ROW
EXECUTE FUNCTION prevent_invalid_review();

CREATE OR REPLACE FUNCTION mark_approvals_stale()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE reviews
    SET stale = TRUE
    WHERE pull_request_id = NEW.pull_request_id
      AND state = 'approved';

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_new_commit_stales_approvals
AFTER UPDATE OF source_head_commit_id ON pull_requests
FOR EACH ROW
WHEN (
    OLD.source_head_commit_id IS DISTINCT FROM
    NEW.source_head_commit_id
)
EXECUTE FUNCTION mark_approvals_stale();

CREATE OR REPLACE FUNCTION merge_eligibility(
    p_pull_request_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    pr RECORD;
    policy RECORD;
    approval_count INTEGER;
    failing_checks INTEGER;
    unresolved INTEGER;
    required_checks INTEGER;
BEGIN
    SELECT *
    INTO pr
    FROM pull_requests
    WHERE pull_request_id = p_pull_request_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'pull request does not exist';
        RETURN;
    END IF;

    IF NOT pr.open THEN
        RETURN QUERY
        SELECT FALSE, 'pull request is closed';
        RETURN;
    END IF;

    IF pr.draft THEN
        RETURN QUERY
        SELECT FALSE, 'draft pull request cannot be merged';
        RETURN;
    END IF;

    SELECT p.*
    INTO policy
    FROM branch_protection_policies p
    WHERE p.branch_id = pr.target_branch_id;

    IF policy.require_pull_request IS NULL THEN
        RETURN QUERY
        SELECT TRUE, 'no branch protection policy requires additional checks';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO approval_count
    FROM reviews r
    JOIN reviewers rv
      ON rv.reviewer_id = r.reviewer_id
    WHERE r.pull_request_id = p_pull_request_id
      AND r.state = 'approved'
      AND NOT r.stale
      AND rv.active;

    IF approval_count < policy.required_approvals THEN
        RETURN QUERY
        SELECT FALSE,
               format(
                   'requires %s approvals but has %s',
                   policy.required_approvals,
                   approval_count
               );
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM reviews r
        WHERE r.pull_request_id = p_pull_request_id
          AND r.state = 'changes_requested'
          AND NOT r.stale
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'active changes-requested review exists';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO unresolved
    FROM conversations c
    WHERE c.pull_request_id = p_pull_request_id
      AND NOT c.resolved;

    IF policy.require_conversation_resolution
       AND unresolved > 0 THEN
        RETURN QUERY
        SELECT FALSE,
               format(
                   '%s unresolved conversations remain',
                   unresolved
               );
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO required_checks
    FROM status_checks
    WHERE pull_request_id = p_pull_request_id;

    SELECT COUNT(*)
    INTO failing_checks
    FROM status_checks
    WHERE pull_request_id = p_pull_request_id
      AND status <> 'passing';

    IF policy.require_status_checks
       AND (required_checks = 0 OR failing_checks > 0) THEN
        RETURN QUERY
        SELECT FALSE, 'required status checks are not passing';
        RETURN;
    END IF;

    IF NOT COALESCE(pr.mergeable, TRUE) THEN
        RETURN QUERY
        SELECT FALSE, 'source and target branches have a merge conflict';
        RETURN;
    END IF;

    RETURN QUERY
    SELECT TRUE, 'all branch protection conditions are satisfied';
END;
$$;

CREATE OR REPLACE VIEW merge_eligibility_report AS
SELECT
    pr.pull_request_id,
    r.repository_name,
    source_branch.branch_name AS source_branch,
    target_branch.branch_name AS target_branch,
    pr.title,
    pr.draft,
    pr.open,
    me.eligible,
    me.reason
FROM pull_requests pr
JOIN repositories r
  ON r.repository_id = pr.repository_id
JOIN branches source_branch
  ON source_branch.branch_id = pr.source_branch_id
JOIN branches target_branch
  ON target_branch.branch_id = pr.target_branch_id
CROSS JOIN LATERAL merge_eligibility(pr.pull_request_id) me;

CREATE OR REPLACE VIEW upstream_health_report AS
SELECT
    g.group_name,
    s.server_name,
    s.address,
    s.port,
    s.weight,
    s.state,
    s.active_connections,
    s.request_count
FROM upstream_groups g
JOIN upstream_servers s
  ON s.upstream_group_id = g.upstream_group_id
ORDER BY g.group_name, s.server_name;

CREATE OR REPLACE FUNCTION route_request(
    p_hostname TEXT,
    p_path TEXT
)
RETURNS TABLE (
    route_id BIGINT,
    upstream_group TEXT,
    server_name TEXT
)
LANGUAGE sql
AS $$
    SELECT
        r.route_id,
        g.group_name,
        s.server_name
    FROM routes r
    JOIN upstream_groups g
      ON g.upstream_group_id = r.upstream_group_id
    JOIN upstream_servers s
      ON s.upstream_group_id = g.upstream_group_id
    WHERE r.hostname = p_hostname
      AND p_path LIKE r.path_prefix || '%'
      AND s.state = 'healthy'
    ORDER BY length(r.path_prefix) DESC,
             s.server_name
    LIMIT 1;
$$;

BEGIN;

INSERT INTO certificates (
    hostname,
    issuer,
    minimum_tls_version,
    expires_at
)
VALUES (
    'api.example.com',
    'Example Internal CA',
    'TLS1.2',
    '2027-12-31 23:59:59+00'
);

INSERT INTO repositories (repository_name)
VALUES ('platform-api');

INSERT INTO branches (
    repository_id,
    branch_name,
    protected
)
SELECT repository_id, 'main', TRUE
FROM repositories
WHERE repository_name = 'platform-api';

INSERT INTO branches (
    repository_id,
    branch_name,
    protected
)
SELECT repository_id, 'feature/reverse-proxy', FALSE
FROM repositories
WHERE repository_name = 'platform-api';

INSERT INTO upstream_groups (
    group_name,
    description
)
VALUES
    ('api_backend', 'Application API servers'),
    ('web_backend', 'Web frontend servers');

INSERT INTO upstream_servers (
    upstream_group_id,
    server_name,
    address,
    port,
    weight
)
SELECT upstream_group_id, 'api-1', '10.0.1.10', 8080, 2
FROM upstream_groups
WHERE group_name = 'api_backend';

INSERT INTO upstream_servers (
    upstream_group_id,
    server_name,
    address,
    port,
    weight
)
SELECT upstream_group_id, 'api-2', '10.0.1.11', 8080, 1
FROM upstream_groups
WHERE group_name = 'api_backend';

INSERT INTO upstream_servers (
    upstream_group_id,
    server_name,
    address,
    port,
    weight
)
SELECT upstream_group_id, 'web-1', '10.0.2.10', 8080, 1
FROM upstream_groups
WHERE group_name = 'web_backend';

INSERT INTO upstream_servers (
    upstream_group_id,
    server_name,
    address,
    port,
    weight
)
SELECT upstream_group_id, 'web-2', '10.0.2.11', 8080, 1
FROM upstream_groups
WHERE group_name = 'web_backend';

INSERT INTO routes (
    hostname,
    path_prefix,
    upstream_group_id,
    certificate_id
)
SELECT
    'api.example.com',
    '/api/',
    g.upstream_group_id,
    c.certificate_id
FROM upstream_groups g
CROSS JOIN certificates c
WHERE g.group_name = 'api_backend'
  AND c.hostname = 'api.example.com';

INSERT INTO routes (
    hostname,
    path_prefix,
    upstream_group_id,
    certificate_id
)
SELECT
    'api.example.com',
    '/',
    g.upstream_group_id,
    c.certificate_id
FROM upstream_groups g
CROSS JOIN certificates c
WHERE g.group_name = 'web_backend'
  AND c.hostname = 'api.example.com';

INSERT INTO branch_protection_policies (
    branch_id,
    require_pull_request,
    required_approvals,
    require_status_checks,
    require_conversation_resolution,
    allow_direct_push,
    allow_force_push,
    allow_branch_deletion,
    require_linear_history,
    allow_admin_bypass
)
SELECT
    branch_id,
    TRUE,
    2,
    TRUE,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE,
    FALSE
FROM branches
WHERE branch_name = 'main';

INSERT INTO approval_requirements (
    policy_id,
    role_name,
    minimum_approvals
)
SELECT
    policy_id,
    'maintainer',
    2
FROM branch_protection_policies
WHERE required_approvals = 2;

INSERT INTO commits (
    repository_id,
    commit_sha,
    author,
    message
)
SELECT
    repository_id,
    '1111111111111111111111111111111111111111',
    'developer1',
    'Add reverse proxy configuration'
FROM repositories
WHERE repository_name = 'platform-api';

INSERT INTO commits (
    repository_id,
    commit_sha,
    author,
    message
)
SELECT
    repository_id,
    '2222222222222222222222222222222222222222',
    'developer1',
    'Add TLS termination tests'
FROM repositories
WHERE repository_name = 'platform-api';

INSERT INTO reviewers (username)
VALUES
    ('maintainer_a'),
    ('maintainer_b'),
    ('developer_reviewer');

INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    source_head_commit_id,
    title,
    draft,
    open,
    mergeable
)
SELECT
    r.repository_id,
    source_branch.branch_id,
    target_branch.branch_id,
    c.commit_id,
    'Introduce Nginx reverse proxy and TLS termination',
    FALSE,
    TRUE,
    TRUE
FROM repositories r
JOIN branches source_branch
  ON source_branch.repository_id = r.repository_id
 AND source_branch.branch_name = 'feature/reverse-proxy'
JOIN branches target_branch
  ON target_branch.repository_id = r.repository_id
 AND target_branch.branch_name = 'main'
JOIN commits c
  ON c.repository_id = r.repository_id
 AND c.commit_sha =
     '1111111111111111111111111111111111111111'
WHERE r.repository_name = 'platform-api';

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    status,
    completed_at
)
SELECT
    pull_request_id,
    'unit-tests',
    'passing',
    CURRENT_TIMESTAMP
FROM pull_requests;

INSERT INTO status_checks (
    pull_request_id,
    check_name,
    status,
    completed_at
)
SELECT
    pull_request_id,
    'nginx-config-validation',
    'passing',
    CURRENT_TIMESTAMP
FROM pull_requests;

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    state,
    stale
)
SELECT
    pr.pull_request_id,
    rv.reviewer_id,
    'approved',
    FALSE
FROM pull_requests pr
JOIN reviewers rv
  ON rv.username = 'maintainer_a';

INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    state,
    stale
)
SELECT
    pr.pull_request_id,
    rv.reviewer_id,
    'approved',
    FALSE
FROM pull_requests pr
JOIN reviewers rv
  ON rv.username = 'maintainer_b';

INSERT INTO conversations (
    pull_request_id,
    topic,
    resolved
)
SELECT
    pull_request_id,
    'TLS certificate renewal policy',
    TRUE
FROM pull_requests;

INSERT INTO review_comments (
    review_id,
    file_path,
    line_number,
    body,
    resolved
)
SELECT
    review_id,
    'nginx.conf',
    42,
    'Verify that the upstream receives the intended forwarded protocol.',
    TRUE
FROM reviews
WHERE state = 'approved'
LIMIT 1;

COMMIT;

-- Merge eligibility is a policy decision, not merely the presence
-- of one approval. The query evaluates all active conditions.
SELECT *
FROM merge_eligibility_report;

-- Longest-prefix routing chooses /api/ before /.
SELECT *
FROM route_request(
    'api.example.com',
    '/api/users'
);

-- A public request to the root path reaches the web pool.
SELECT *
FROM route_request(
    'api.example.com',
    '/dashboard'
);

-- Mark one upstream unhealthy and observe failover eligibility.
UPDATE upstream_servers
SET state = 'unhealthy'
WHERE server_name = 'api-1';

SELECT *
FROM upstream_health_report;

SELECT *
FROM route_request(
    'api.example.com',
    '/api/orders'
);

-- Simulate a newly pushed commit. Existing approvals become stale.
UPDATE pull_requests pr
SET source_head_commit_id = c.commit_id
FROM commits c
WHERE pr.title =
    'Introduce Nginx reverse proxy and TLS termination'
  AND c.commit_sha =
    '2222222222222222222222222222222222222222';

SELECT
    pull_request_id,
    reviewer_id,
    state,
    stale
FROM reviews
ORDER BY review_id;

-- Because approvals are stale, the same pull request is no longer
-- eligible until fresh approvals are submitted.
SELECT *
FROM merge_eligibility_report;

-- Demonstrate transactional request logging.
BEGIN;

INSERT INTO proxy_requests (
    client_ip,
    hostname,
    method,
    request_path,
    protocol,
    state,
    response_status,
    request_bytes,
    duration_ms,
    completed_at
)
VALUES (
    '203.0.113.10',
    'api.example.com',
    'GET',
    '/api/users',
    'https',
    'completed',
    200,
    0,
    4.25,
    CURRENT_TIMESTAMP
);

COMMIT;

SELECT
    hostname,
    request_path,
    protocol,
    state,
    response_status,
    duration_ms
FROM proxy_requests
ORDER BY received_at DESC;

-- Operational reporting: identify unhealthy backends.
SELECT
    group_name,
    COUNT(*) AS total_servers,
    COUNT(*) FILTER (
        WHERE state = 'healthy'
    ) AS healthy_servers,
    COUNT(*) FILTER (
        WHERE state = 'unhealthy'
    ) AS unhealthy_servers
FROM upstream_health_report
GROUP BY group_name
ORDER BY group_name;

-- Operational reporting: request success/failure distribution.
SELECT
    protocol,
    response_status,
    COUNT(*) AS request_count
FROM proxy_requests
GROUP BY protocol, response_status
ORDER BY protocol, response_status;
