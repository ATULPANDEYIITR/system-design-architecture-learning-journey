-- PostgreSQL 15+
-- Distributed transaction coordination and two-phase commit model.
--
-- This schema simulates the coordinator protocol in ordinary application
-- tables. It is not PostgreSQL's native PREPARE TRANSACTION facility.
-- Native prepared transactions are managed with PREPARE TRANSACTION,
-- COMMIT PREPARED, and ROLLBACK PREPARED across independent database sessions.
--
-- Run in a dedicated learning database. The schema is recreated on each run.

DROP SCHEMA IF EXISTS distributed_tx_demo CASCADE;
CREATE SCHEMA distributed_tx_demo;
SET search_path TO distributed_tx_demo, public;

CREATE TYPE transaction_state AS ENUM (
    'NEW',
    'PREPARING',
    'COMMIT_DECIDED',
    'ABORT_DECIDED',
    'COMMITTED',
    'ABORTED',
    'IN_DOUBT'
);

CREATE TYPE participant_state AS ENUM (
    'ACTIVE',
    'PREPARED',
    'COMMITTED',
    'ABORTED'
);

CREATE TYPE global_decision AS ENUM ('COMMIT', 'ABORT');

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE,
    coordinator_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(trim(repository_name)) > 0)
);

CREATE TABLE participants (
    participant_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    participant_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    last_heartbeat_at TIMESTAMPTZ,
    UNIQUE (repository_id, participant_name),
    CHECK (length(trim(participant_name)) > 0)
);

CREATE TABLE accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    participant_id BIGINT NOT NULL REFERENCES participants(participant_id),
    account_name TEXT NOT NULL,
    balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    UNIQUE (participant_id, account_name),
    CHECK (balance >= 0),
    CHECK (version >= 0)
);

CREATE TABLE distributed_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    operation_key UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    state transaction_state NOT NULL DEFAULT 'NEW',
    decision global_decision,
    decision_reason TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    decision_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    coordinator_epoch BIGINT NOT NULL DEFAULT 1,
    CHECK (coordinator_epoch > 0),
    CHECK (
        (decision IS NULL AND decision_at IS NULL)
        OR
        (decision IS NOT NULL AND decision_at IS NOT NULL)
    ),
    CHECK (
        completed_at IS NULL
        OR state IN ('COMMITTED', 'ABORTED')
    )
);

CREATE TABLE transaction_participants (
    transaction_id UUID NOT NULL
        REFERENCES distributed_transactions(transaction_id),
    participant_id BIGINT NOT NULL REFERENCES participants(participant_id),
    state participant_state NOT NULL DEFAULT 'ACTIVE',
    vote_yes BOOLEAN,
    vote_reason TEXT,
    prepared_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (transaction_id, participant_id),
    CHECK (attempt_count >= 0),
    CHECK (
        (state = 'PREPARED' AND vote_yes IS TRUE AND prepared_at IS NOT NULL)
        OR state <> 'PREPARED'
        OR vote_yes IS TRUE
    )
);

CREATE TABLE transaction_entries (
    transaction_id UUID NOT NULL
        REFERENCES distributed_transactions(transaction_id),
    entry_number INTEGER NOT NULL,
    account_id BIGINT NOT NULL REFERENCES accounts(account_id),
    delta NUMERIC(18, 2) NOT NULL,
    applied BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (transaction_id, entry_number),
    UNIQUE (transaction_id, account_id),
    CHECK (delta <> 0)
);

CREATE TABLE transaction_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id UUID NOT NULL
        REFERENCES distributed_transactions(transaction_id),
    participant_id BIGINT REFERENCES participants(participant_id),
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (length(trim(event_type)) > 0)
);

CREATE TABLE transaction_outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id UUID NOT NULL
        REFERENCES distributed_transactions(transaction_id),
    participant_id BIGINT NOT NULL REFERENCES participants(participant_id),
    decision global_decision NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    delivered_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    UNIQUE (transaction_id, participant_id),
    CHECK (attempts >= 0)
);

CREATE INDEX idx_transactions_state_started
    ON distributed_transactions(state, started_at);

CREATE INDEX idx_transaction_participants_state
    ON transaction_participants(state, transaction_id);

CREATE INDEX idx_transaction_events_history
    ON transaction_events(transaction_id, event_time, event_id);

CREATE INDEX idx_outbox_pending
    ON transaction_outbox(created_at)
    WHERE delivered_at IS NULL;

CREATE INDEX idx_accounts_participant
    ON accounts(participant_id, account_id);

INSERT INTO repositories (repository_name, coordinator_name)
VALUES ('marketplace-settlement', 'settlement-coordinator');

INSERT INTO participants (
    repository_id, participant_name, endpoint, is_available, last_heartbeat_at
)
SELECT
    repository_id,
    seed.participant_name,
    seed.endpoint,
    seed.is_available,
    clock_timestamp()
FROM repositories
CROSS JOIN (
    VALUES
        ('customer-ledger', 'ledger://customer', TRUE),
        ('merchant-ledger', 'ledger://merchant', TRUE),
        ('fee-ledger', 'ledger://fees', TRUE),
        ('offline-ledger', 'ledger://offline', FALSE)
) AS seed(participant_name, endpoint, is_available)
WHERE repository_name = 'marketplace-settlement';

INSERT INTO accounts (participant_id, account_name, balance)
SELECT participant_id, seed.account_name, seed.balance
FROM participants
JOIN (
    VALUES
        ('customer-ledger', 'customer-001', 1000.00::NUMERIC),
        ('merchant-ledger', 'merchant-001', 200.00::NUMERIC),
        ('fee-ledger', 'platform-fees', 0.00::NUMERIC),
        ('offline-ledger', 'offline-account', 75.00::NUMERIC)
) AS seed(participant_name, account_name, balance)
USING (participant_name);

-- Start a sample transaction with a balanced transfer.
BEGIN;

INSERT INTO distributed_transactions (
    repository_id, operation_key, state
)
SELECT
    repository_id,
    '00000000-0000-0000-0000-000000000101'::UUID,
    'NEW'
FROM repositories
WHERE repository_name = 'marketplace-settlement'
ON CONFLICT (operation_key) DO NOTHING;

UPDATE distributed_transactions
SET state = 'PREPARING'
WHERE operation_key = '00000000-0000-0000-0000-000000000101'
  AND state = 'NEW';

INSERT INTO transaction_participants (transaction_id, participant_id)
SELECT
    t.transaction_id,
    p.participant_id
FROM distributed_transactions AS t
JOIN repositories AS r ON r.repository_id = t.repository_id
JOIN participants AS p ON p.repository_id = r.repository_id
WHERE t.operation_key = '00000000-0000-0000-0000-000000000101'
  AND p.participant_name IN (
      'customer-ledger', 'merchant-ledger', 'fee-ledger'
  )
ON CONFLICT DO NOTHING;

INSERT INTO transaction_entries (
    transaction_id, entry_number, account_id, delta
)
SELECT
    t.transaction_id,
    seed.entry_number,
    a.account_id,
    seed.delta
FROM distributed_transactions AS t
JOIN repositories AS r ON r.repository_id = t.repository_id
JOIN (
    VALUES
        ('customer-001', 1, -125.00::NUMERIC),
        ('merchant-001', 2, 120.00::NUMERIC),
        ('platform-fees', 3, 5.00::NUMERIC)
) AS seed(account_name, entry_number, delta) ON TRUE
JOIN accounts AS a
    ON a.account_name = seed.account_name
JOIN participants AS p
    ON p.participant_id = a.participant_id
   AND p.repository_id = r.repository_id
WHERE t.operation_key = '00000000-0000-0000-0000-000000000101'
ON CONFLICT DO NOTHING;

-- Every participant votes YES only after validating its local work.
UPDATE transaction_participants
SET
    vote_yes = TRUE,
    vote_reason = 'Local validation passed',
    state = 'PREPARED',
    prepared_at = clock_timestamp()
WHERE transaction_id = (
    SELECT transaction_id
    FROM distributed_transactions
    WHERE operation_key = '00000000-0000-0000-0000-000000000101'
)
AND participant_id IN (
    SELECT p.participant_id
    FROM participants AS p
    WHERE p.participant_name IN (
        'customer-ledger', 'merchant-ledger', 'fee-ledger'
    )
);

INSERT INTO transaction_events (transaction_id, event_type, details)
SELECT
    transaction_id,
    'ALL_PARTICIPANTS_PREPARED',
    jsonb_build_object('participant_count', 3)
FROM distributed_transactions
WHERE operation_key = '00000000-0000-0000-0000-000000000101';

-- This local SQL transaction atomically records the global decision and
-- durable delivery work. A real coordinator sends outbox messages after commit.
UPDATE distributed_transactions
SET
    decision = 'COMMIT',
    decision_at = clock_timestamp(),
    state = 'COMMIT_DECIDED',
    decision_reason = 'All participants voted YES'
WHERE operation_key = '00000000-0000-0000-0000-000000000101'
  AND state = 'PREPARING'
  AND NOT EXISTS (
      SELECT 1
      FROM transaction_participants AS tp
      WHERE tp.transaction_id = distributed_transactions.transaction_id
        AND (tp.vote_yes IS DISTINCT FROM TRUE)
  );

INSERT INTO transaction_outbox (transaction_id, participant_id, decision)
SELECT
    t.transaction_id,
    tp.participant_id,
    t.decision
FROM distributed_transactions AS t
JOIN transaction_participants AS tp
    ON tp.transaction_id = t.transaction_id
WHERE t.operation_key = '00000000-0000-0000-0000-000000000101'
  AND t.decision = 'COMMIT'
ON CONFLICT DO NOTHING;

INSERT INTO transaction_events (transaction_id, event_type, details)
SELECT
    transaction_id,
    'GLOBAL_COMMIT',
    jsonb_build_object('reason', decision_reason)
FROM distributed_transactions
WHERE operation_key = '00000000-0000-0000-0000-000000000101'
  AND decision = 'COMMIT';

COMMIT;

-- Simulate delivery of the commit decision in a single database transaction.
-- The account mutations, participant states, and completion records are atomic
-- within this database. They do not create an atomic transaction across remote
-- databases; remote participants require their own idempotent handlers.

BEGIN;

WITH target AS (
    SELECT transaction_id
    FROM distributed_transactions
    WHERE operation_key = '00000000-0000-0000-0000-000000000101'
      AND decision = 'COMMIT'
),
changes AS (
    SELECT e.account_id, SUM(e.delta) AS delta
    FROM transaction_entries AS e
    JOIN target AS t USING (transaction_id)
    WHERE NOT e.applied
    GROUP BY e.account_id
),
updated_accounts AS (
    UPDATE accounts AS a
    SET
        balance = a.balance + c.delta,
        version = a.version + 1
    FROM changes AS c
    WHERE a.account_id = c.account_id
      AND a.balance + c.delta >= 0
    RETURNING a.account_id
)
UPDATE transaction_entries AS e
SET applied = TRUE
FROM target AS t
WHERE e.transaction_id = t.transaction_id
  AND e.account_id IN (SELECT account_id FROM updated_accounts)
  AND NOT e.applied;

UPDATE transaction_participants AS tp
SET
    state = 'COMMITTED',
    completed_at = clock_timestamp(),
    attempt_count = attempt_count + 1
FROM distributed_transactions AS t
WHERE tp.transaction_id = t.transaction_id
  AND t.operation_key = '00000000-0000-0000-0000-000000000101'
  AND t.decision = 'COMMIT'
  AND tp.state = 'PREPARED';

UPDATE transaction_outbox
SET
    delivered_at = clock_timestamp(),
    attempts = attempts + 1,
    last_error = NULL
WHERE transaction_id = (
    SELECT transaction_id
    FROM distributed_transactions
    WHERE operation_key = '00000000-0000-0000-0000-000000000101'
)
AND delivered_at IS NULL;

UPDATE distributed_transactions AS t
SET
    state = 'COMMITTED',
    completed_at = clock_timestamp()
WHERE t.operation_key = '00000000-0000-0000-0000-000000000101'
  AND t.decision = 'COMMIT'
  AND NOT EXISTS (
      SELECT 1
      FROM transaction_entries AS e
      WHERE e.transaction_id = t.transaction_id
        AND NOT e.applied
  );

INSERT INTO transaction_events (transaction_id, event_type, details)
SELECT
    transaction_id,
    'TRANSACTION_COMPLETE',
    jsonb_build_object('state', state)
FROM distributed_transactions
WHERE operation_key = '00000000-0000-0000-0000-000000000101'
  AND state = 'COMMITTED';

COMMIT;

-- A second transaction demonstrates a negative vote and a global abort.
INSERT INTO distributed_transactions (
    repository_id, operation_key, state
)
SELECT
    repository_id,
    '00000000-0000-0000-0000-000000000102'::UUID,
    'PREPARING'
FROM repositories
WHERE repository_name = 'marketplace-settlement'
ON CONFLICT (operation_key) DO NOTHING;

INSERT INTO transaction_participants (transaction_id, participant_id)
SELECT t.transaction_id, p.participant_id
FROM distributed_transactions AS t
JOIN repositories AS r ON r.repository_id = t.repository_id
JOIN participants AS p ON p.repository_id = r.repository_id
WHERE t.operation_key = '00000000-0000-0000-0000-000000000102'
  AND p.participant_name IN ('customer-ledger', 'merchant-ledger')
ON CONFLICT DO NOTHING;

UPDATE transaction_participants AS tp
SET
    vote_yes = CASE
        WHEN p.participant_name = 'customer-ledger' THEN FALSE
        ELSE NULL
    END,
    vote_reason = CASE
        WHEN p.participant_name = 'customer-ledger' THEN 'Insufficient funds'
        ELSE 'Vote not received'
    END
FROM participants AS p
WHERE tp.participant_id = p.participant_id
  AND tp.transaction_id = (
      SELECT transaction_id
      FROM distributed_transactions
      WHERE operation_key = '00000000-0000-0000-0000-000000000102'
  );

UPDATE distributed_transactions AS t
SET
    decision = 'ABORT',
    decision_at = clock_timestamp(),
    state = 'ABORT_DECIDED',
    decision_reason = 'At least one participant did not vote YES'
WHERE t.operation_key = '00000000-0000-0000-0000-000000000102'
  AND t.state = 'PREPARING'
  AND EXISTS (
      SELECT 1
      FROM transaction_participants AS tp
      WHERE tp.transaction_id = t.transaction_id
        AND tp.vote_yes IS DISTINCT FROM TRUE
  );

INSERT INTO transaction_outbox (transaction_id, participant_id, decision)
SELECT t.transaction_id, tp.participant_id, t.decision
FROM distributed_transactions AS t
JOIN transaction_participants AS tp
    ON tp.transaction_id = t.transaction_id
WHERE t.operation_key = '00000000-0000-0000-0000-000000000102'
  AND t.decision = 'ABORT'
ON CONFLICT DO NOTHING;

UPDATE transaction_participants AS tp
SET
    state = 'ABORTED',
    completed_at = clock_timestamp()
FROM distributed_transactions AS t
WHERE tp.transaction_id = t.transaction_id
  AND t.operation_key = '00000000-0000-0000-0000-000000000102'
  AND t.decision = 'ABORT'
  AND tp.state <> 'COMMITTED';

UPDATE distributed_transactions
SET
    state = 'ABORTED',
    completed_at = clock_timestamp()
WHERE operation_key = '00000000-0000-0000-0000-000000000102'
  AND decision = 'ABORT';

INSERT INTO transaction_events (transaction_id, event_type, details)
SELECT
    transaction_id,
    'GLOBAL_ABORT',
    jsonb_build_object('reason', decision_reason)
FROM distributed_transactions
WHERE operation_key = '00000000-0000-0000-0000-000000000102'
  AND decision = 'ABORT';

-- Operational view: global decision and participant completion must be
-- examined separately. A global COMMIT can coexist temporarily with pending
-- participant delivery while recovery is in progress.
CREATE VIEW transaction_recovery_status AS
SELECT
    t.transaction_id,
    r.repository_name,
    t.state,
    t.decision,
    t.started_at,
    t.decision_at,
    t.completed_at,
    COUNT(tp.participant_id) AS participant_count,
    COUNT(*) FILTER (WHERE tp.vote_yes IS TRUE) AS yes_votes,
    COUNT(*) FILTER (WHERE tp.vote_yes IS FALSE) AS no_votes,
    COUNT(*) FILTER (WHERE tp.vote_yes IS NULL) AS missing_votes,
    COUNT(*) FILTER (WHERE tp.state = 'PREPARED') AS prepared_count,
    COUNT(*) FILTER (WHERE tp.state = 'COMMITTED') AS committed_count,
    COUNT(*) FILTER (WHERE tp.state = 'ABORTED') AS aborted_count,
    COUNT(o.outbox_id) FILTER (WHERE o.delivered_at IS NULL) AS pending_messages
FROM distributed_transactions AS t
JOIN repositories AS r ON r.repository_id = t.repository_id
LEFT JOIN transaction_participants AS tp
    ON tp.transaction_id = t.transaction_id
LEFT JOIN transaction_outbox AS o
    ON o.transaction_id = t.transaction_id
   AND o.participant_id = tp.participant_id
GROUP BY
    t.transaction_id,
    r.repository_name,
    t.state,
    t.decision,
    t.started_at,
    t.decision_at,
    t.completed_at;

-- Inspect transaction outcomes.
SELECT *
FROM transaction_recovery_status
ORDER BY started_at;

-- Verify ledger conservation for the successful transaction.
SELECT
    SUM(e.delta) AS total_delta,
    SUM(a.balance) AS total_current_balance
FROM transaction_entries AS e
JOIN accounts AS a ON a.account_id = e.account_id
WHERE e.transaction_id = (
    SELECT transaction_id
    FROM distributed_transactions
    WHERE operation_key = '00000000-0000-0000-0000-000000000101'
)
GROUP BY e.transaction_id;

-- Inspect the ordered coordinator event history.
SELECT
    e.transaction_id,
    e.event_time,
    e.event_type,
    e.participant_id,
    e.details
FROM transaction_events AS e
ORDER BY e.event_time, e.event_id;

-- Identify transactions that need recovery or operator attention.
SELECT *
FROM transaction_recovery_status
WHERE state = 'IN_DOUBT'
   OR prepared_count > 0
   OR pending_messages > 0
ORDER BY started_at;

-- Database-level constraints prevent negative account balances and duplicate
-- operation keys. Application-level protocol logic must still guarantee:
-- * global COMMIT is durable before commit delivery;
-- * prepared participants retain enough state for recovery;
-- * commit and abort handlers are idempotent;
-- * retries do not apply a ledger entry twice;
-- * a coordinator epoch or equivalent fencing mechanism prevents stale
--   coordinator instances from issuing conflicting decisions.
