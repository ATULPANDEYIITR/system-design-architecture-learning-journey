/*
===============================================================================
EVENT SOURCING: EVENTS AS THE SOURCE OF TRUTH
PostgreSQL 14+

Demonstrates:
- Append-only event persistence
- Aggregate streams
- Event sequence numbers
- Command idempotency
- Optimistic concurrency
- JSONB event payloads
- Database-enforced event integrity
- Account balance projections
- Projection replay
- Snapshots
- Audit reporting
- Transactional command processing

Run this script in a dedicated database.
The script recreates only the event_sourcing_demo schema.
===============================================================================
*/

DROP SCHEMA IF EXISTS event_sourcing_demo CASCADE;
CREATE SCHEMA event_sourcing_demo;

SET search_path TO event_sourcing_demo, public;

-- ============================================================================
-- 1. DOMAIN IDENTITIES
-- ============================================================================

CREATE TABLE repositories_metadata (
    metadata_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO repositories_metadata(system_name)
VALUES ('Event Sourcing Banking System');

CREATE TABLE accounts (
    account_id UUID PRIMARY KEY,
    owner_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT owner_name_not_empty
        CHECK (length(trim(owner_name)) > 0)
);

-- Aggregate heads serialize concurrent writes to each stream.
CREATE TABLE aggregate_heads (
    aggregate_id UUID PRIMARY KEY
        REFERENCES accounts(account_id),
    current_version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT nonnegative_aggregate_version
        CHECK (current_version >= 0)
);

-- ============================================================================
-- 2. COMMAND DEDUPLICATION
-- ============================================================================

CREATE TABLE processed_commands (
    command_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL REFERENCES accounts(account_id),
    command_type VARCHAR(50) NOT NULL,
    request_fingerprint TEXT NOT NULL,
    result_event_id UUID,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 3. AUTHORITATIVE EVENT STORE
-- ============================================================================

CREATE TABLE event_store (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL REFERENCES accounts(account_id),
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(60) NOT NULL,
    event_payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    schema_version INTEGER NOT NULL DEFAULT 1,
    command_id UUID NOT NULL REFERENCES processed_commands(command_id),

    CONSTRAINT unique_aggregate_version
        UNIQUE (aggregate_id, aggregate_version),

    CONSTRAINT positive_event_version
        CHECK (aggregate_version > 0),

    CONSTRAINT valid_schema_version
        CHECK (schema_version > 0),

    CONSTRAINT valid_event_type CHECK (
        event_type IN (
            'AccountOpened',
            'MoneyDeposited',
            'MoneyWithdrawn',
            'AccountFrozen',
            'AccountUnfrozen'
        )
    ),

    CONSTRAINT payload_must_be_object
        CHECK (jsonb_typeof(event_payload) = 'object')
);

CREATE INDEX idx_event_stream
    ON event_store(aggregate_id, aggregate_version);

CREATE INDEX idx_event_type_time
    ON event_store(event_type, occurred_at DESC);

CREATE INDEX idx_event_payload
    ON event_store USING GIN(event_payload);

CREATE INDEX idx_event_command
    ON event_store(command_id);

-- ============================================================================
-- 4. READ MODEL
-- ============================================================================

CREATE TABLE account_projection (
    account_id UUID PRIMARY KEY REFERENCES accounts(account_id),
    owner_name VARCHAR(150) NOT NULL,
    balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    projection_version BIGINT NOT NULL DEFAULT 1,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT nonnegative_balance
        CHECK (balance >= 0),

    CONSTRAINT valid_account_status
        CHECK (account_status IN ('ACTIVE', 'FROZEN'))
);

CREATE INDEX idx_projection_status
    ON account_projection(account_status);

CREATE INDEX idx_projection_balance
    ON account_projection(balance DESC);

-- ============================================================================
-- 5. EVENT STORE IMMUTABILITY
-- ============================================================================

CREATE OR REPLACE FUNCTION prevent_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Event records are immutable. Append a compensating event instead.';
END;
$$;

CREATE TRIGGER trg_event_no_update
BEFORE UPDATE OR DELETE ON event_store
FOR EACH ROW
EXECUTE FUNCTION prevent_event_mutation();

-- ============================================================================
-- 6. EVENT VALIDATION
-- ============================================================================

CREATE OR REPLACE FUNCTION validate_domain_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    amount_value NUMERIC;
BEGIN
    IF NEW.event_type = 'AccountOpened' THEN
        IF NOT (NEW.event_payload ? 'owner') THEN
            RAISE EXCEPTION 'AccountOpened requires owner.';
        END IF;

        IF length(trim(NEW.event_payload->>'owner')) = 0 THEN
            RAISE EXCEPTION 'Owner cannot be empty.';
        END IF;

    ELSIF NEW.event_type IN (
        'MoneyDeposited',
        'MoneyWithdrawn'
    ) THEN

        IF NOT (NEW.event_payload ? 'amount') THEN
            RAISE EXCEPTION 'Financial event requires amount.';
        END IF;

        IF jsonb_typeof(NEW.event_payload->'amount') <> 'number' THEN
            RAISE EXCEPTION 'Amount must be numeric.';
        END IF;

        amount_value := (NEW.event_payload->>'amount')::NUMERIC;

        IF amount_value <= 0 THEN
            RAISE EXCEPTION 'Amount must be positive.';
        END IF;

        IF amount_value <> round(amount_value, 2) THEN
            RAISE EXCEPTION 'Amount supports at most two decimals.';
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_event
BEFORE INSERT ON event_store
FOR EACH ROW
EXECUTE FUNCTION validate_domain_event();

-- ============================================================================
-- 7. PROJECTION UPDATE MECHANISM
-- ============================================================================

CREATE OR REPLACE FUNCTION update_account_projection()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    amount_value NUMERIC(18, 2);
    current_status VARCHAR(20);
BEGIN
    IF NEW.event_type = 'AccountOpened' THEN

        INSERT INTO account_projection (
            account_id,
            owner_name,
            balance,
            account_status,
            projection_version
        )
        VALUES (
            NEW.aggregate_id,
            NEW.event_payload->>'owner',
            0,
            'ACTIVE',
            NEW.aggregate_version
        );

        RETURN NEW;
    END IF;

    SELECT account_status
    INTO current_status
    FROM account_projection
    WHERE account_id = NEW.aggregate_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Projection does not exist for aggregate %',
            NEW.aggregate_id;
    END IF;

    IF NEW.aggregate_version <> (
        SELECT projection_version + 1
        FROM account_projection
        WHERE account_id = NEW.aggregate_id
    ) THEN
        RAISE EXCEPTION 'Projection version mismatch.';
    END IF;

    IF NEW.event_type IN (
        'MoneyDeposited',
        'MoneyWithdrawn'
    ) AND current_status = 'FROZEN' THEN
        RAISE EXCEPTION 'Financial operation on frozen account.';
    END IF;

    IF NEW.event_type = 'MoneyDeposited' THEN

        amount_value :=
            (NEW.event_payload->>'amount')::NUMERIC(18, 2);

        UPDATE account_projection
        SET balance = balance + amount_value,
            projection_version = NEW.aggregate_version,
            last_updated = CURRENT_TIMESTAMP
        WHERE account_id = NEW.aggregate_id;

    ELSIF NEW.event_type = 'MoneyWithdrawn' THEN

        amount_value :=
            (NEW.event_payload->>'amount')::NUMERIC(18, 2);

        UPDATE account_projection
        SET balance = balance - amount_value,
            projection_version = NEW.aggregate_version,
            last_updated = CURRENT_TIMESTAMP
        WHERE account_id = NEW.aggregate_id
          AND balance >= amount_value;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Insufficient funds.';
        END IF;

    ELSIF NEW.event_type = 'AccountFrozen' THEN

        UPDATE account_projection
        SET account_status = 'FROZEN',
            projection_version = NEW.aggregate_version,
            last_updated = CURRENT_TIMESTAMP
        WHERE account_id = NEW.aggregate_id
          AND account_status = 'ACTIVE';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Account is already frozen.';
        END IF;

    ELSIF NEW.event_type = 'AccountUnfrozen' THEN

        UPDATE account_projection
        SET account_status = 'ACTIVE',
            projection_version = NEW.aggregate_version,
            last_updated = CURRENT_TIMESTAMP
        WHERE account_id = NEW.aggregate_id
          AND account_status = 'FROZEN';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Account is not frozen.';
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_update_projection
AFTER INSERT ON event_store
FOR EACH ROW
EXECUTE FUNCTION update_account_projection();

-- ============================================================================
-- 8. COMMAND PROCESSING FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION append_account_event(
    p_command_id UUID,
    p_account_id UUID,
    p_event_type VARCHAR(60),
    p_payload JSONB,
    p_expected_version BIGINT
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    current_version BIGINT;
    new_event_id UUID;
    existing_event_id UUID;
    existing_fingerprint TEXT;
    request_fingerprint TEXT;
    account_owner VARCHAR(150);
BEGIN
    IF p_command_id IS NULL OR p_account_id IS NULL THEN
        RAISE EXCEPTION 'Command and aggregate identifiers are required.';
    END IF;

    IF p_payload IS NULL OR jsonb_typeof(p_payload) <> 'object' THEN
        RAISE EXCEPTION 'Event payload must be a JSON object.';
    END IF;

    IF p_event_type NOT IN (
        'AccountOpened',
        'MoneyDeposited',
        'MoneyWithdrawn',
        'AccountFrozen',
        'AccountUnfrozen'
    ) THEN
        RAISE EXCEPTION 'Unsupported event type.';
    END IF;

    request_fingerprint := md5(
        p_account_id::TEXT || '|' ||
        p_event_type || '|' ||
        p_payload::TEXT
    );

    -- A repeated command returns its previous result.
    SELECT result_event_id, request_fingerprint
    INTO existing_event_id, existing_fingerprint
    FROM processed_commands
    WHERE command_id = p_command_id;

    IF FOUND THEN
        IF existing_fingerprint <> request_fingerprint THEN
            RAISE EXCEPTION
                'Command ID cannot be reused with different content.';
        END IF;

        RETURN existing_event_id;
    END IF;

    -- Lock the aggregate head to serialize writes to this stream.
    SELECT current_version
    INTO current_version
    FROM aggregate_heads
    WHERE aggregate_id = p_account_id
    FOR UPDATE;

    IF NOT FOUND THEN
        IF p_event_type <> 'AccountOpened' OR p_expected_version <> 0 THEN
            RAISE EXCEPTION 'Aggregate does not exist.';
        END IF;

        SELECT owner_name
        INTO account_owner
        FROM accounts
        WHERE account_id = p_account_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Account identity does not exist.';
        END IF;

        current_version := 0;

        INSERT INTO aggregate_heads (
            aggregate_id,
            current_version
        )
        VALUES (p_account_id, 0);
    END IF;

    IF current_version <> p_expected_version THEN
        RAISE EXCEPTION
            'Concurrency conflict: expected %, actual %',
            p_expected_version, current_version;
    END IF;

    IF p_event_type = 'AccountOpened' AND current_version <> 0 THEN
        RAISE EXCEPTION 'Account already opened.';
    END IF;

    IF p_event_type <> 'AccountOpened' AND current_version = 0 THEN
        RAISE EXCEPTION 'Account must be opened first.';
    END IF;

    new_event_id := gen_random_uuid();

    INSERT INTO processed_commands (
        command_id,
        aggregate_id,
        command_type,
        request_fingerprint
    )
    VALUES (
        p_command_id,
        p_account_id,
        p_event_type,
        request_fingerprint
    );

    -- Event insertion and projection updates share one transaction.
    INSERT INTO event_store (
        event_id,
        aggregate_id,
        aggregate_version,
        event_type,
        event_payload,
        schema_version,
        command_id
    )
    VALUES (
        new_event_id,
        p_account_id,
        current_version + 1,
        p_event_type,
        p_payload,
        1,
        p_command_id
    );

    UPDATE aggregate_heads
    SET current_version = current_version + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE aggregate_id = p_account_id;

    UPDATE processed_commands
    SET result_event_id = new_event_id
    WHERE command_id = p_command_id;

    RETURN new_event_id;
END;
$$;

-- ============================================================================
-- 9. EVENT REPLAY FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION replay_account(
    p_account_id UUID
)
RETURNS TABLE (
    event_version BIGINT,
    event_name VARCHAR,
    event_data JSONB,
    event_time TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        aggregate_version,
        event_type::VARCHAR,
        event_payload,
        occurred_at
    FROM event_store
    WHERE aggregate_id = p_account_id
    ORDER BY aggregate_version;
$$;

-- ============================================================================
-- 10. SNAPSHOT STORAGE
-- ============================================================================

CREATE TABLE account_snapshots (
    snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_id UUID NOT NULL REFERENCES accounts(account_id),
    aggregate_version BIGINT NOT NULL,
    snapshot_state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (aggregate_id, aggregate_version),

    CHECK (aggregate_version > 0),
    CHECK (jsonb_typeof(snapshot_state) = 'object')
);

CREATE INDEX idx_snapshot_latest
    ON account_snapshots(aggregate_id, aggregate_version DESC);

-- ============================================================================
-- 11. REPORTING VIEW
-- ============================================================================

CREATE OR REPLACE VIEW account_event_report AS
SELECT
    a.account_id,
    a.owner_name,
    ap.balance,
    ap.account_status,
    ap.projection_version,
    ah.current_version AS event_stream_version,
    COUNT(es.event_id) AS total_events,
    MAX(es.occurred_at) AS latest_event_time
FROM accounts a
JOIN aggregate_heads ah
    ON ah.aggregate_id = a.account_id
LEFT JOIN account_projection ap
    ON ap.account_id = a.account_id
LEFT JOIN event_store es
    ON es.aggregate_id = a.account_id
GROUP BY
    a.account_id,
    a.owner_name,
    ap.balance,
    ap.account_status,
    ap.projection_version,
    ah.current_version;

-- ============================================================================
-- 12. SAMPLE DATA
-- ============================================================================

BEGIN;

INSERT INTO accounts(account_id, owner_name)
VALUES
(
    '00000000-0000-0000-0000-000000000001',
    'Atul'
),
(
    '00000000-0000-0000-0000-000000000002',
    'Research Account'
);

-- Account 1: successful lifecycle.
SELECT append_account_event(
    '10000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'AccountOpened',
    '{"owner":"Atul"}',
    0
);

SELECT append_account_event(
    '10000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'MoneyDeposited',
    '{"amount":10000}',
    1
);

SELECT append_account_event(
    '10000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000001',
    'MoneyWithdrawn',
    '{"amount":2500}',
    2
);

SELECT append_account_event(
    '10000000-0000-0000-0000-000000000004',
    '00000000-0000-0000-0000-000000000001',
    'AccountFrozen',
    '{}',
    3
);

SELECT append_account_event(
    '10000000-0000-0000-0000-000000000005',
    '00000000-0000-0000-0000-000000000001',
    'AccountUnfrozen',
    '{}',
    4
);

SELECT append_account_event(
    '10000000-0000-0000-0000-000000000006',
    '00000000-0000-0000-0000-000000000001',
    'MoneyDeposited',
    '{"amount":500}',
    5
);

-- Account 2: separate independent aggregate stream.
SELECT append_account_event(
    '20000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    'AccountOpened',
    '{"owner":"Research Account"}',
    0
);

SELECT append_account_event(
    '20000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000002',
    'MoneyDeposited',
    '{"amount":50000}',
    1
);

COMMIT;

-- ============================================================================
-- 13. COMMAND IDEMPOTENCY DEMONSTRATION
-- ============================================================================

-- Repeating the original command returns its original event ID.
SELECT append_account_event(
    '10000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'MoneyDeposited',
    '{"amount":10000}',
    1
) AS repeated_command_result;

-- ============================================================================
-- 14. RETRIEVAL QUERIES
-- ============================================================================

-- Complete history of the first aggregate.
SELECT *
FROM replay_account(
    '00000000-0000-0000-0000-000000000001'
);

-- Current read-model state.
SELECT *
FROM account_projection
ORDER BY account_id;

-- ============================================================================
-- 15. VALIDATION AND CONSISTENCY QUERIES
-- ============================================================================

-- Identify differences between stream and projection versions.
SELECT
    ah.aggregate_id,
    ah.current_version,
    ap.projection_version,
    CASE
        WHEN ah.current_version = ap.projection_version
        THEN 'CONSISTENT'
        ELSE 'INCONSISTENT'
    END AS consistency_status
FROM aggregate_heads ah
JOIN account_projection ap
    ON ap.account_id = ah.aggregate_id;

-- Identify missing event sequence numbers.
WITH event_sequence AS (
    SELECT
        aggregate_id,
        aggregate_version,
        LAG(aggregate_version) OVER (
            PARTITION BY aggregate_id
            ORDER BY aggregate_version
        ) AS previous_version
    FROM event_store
)
SELECT *
FROM event_sequence
WHERE previous_version IS NOT NULL
  AND aggregate_version <> previous_version + 1;

-- ============================================================================
-- 16. AGGREGATION AND REPORTING
-- ============================================================================

SELECT
    COUNT(*) AS total_accounts,
    SUM(balance) AS combined_balance,
    AVG(balance) AS average_balance,
    COUNT(*) FILTER (
        WHERE account_status = 'FROZEN'
    ) AS frozen_accounts,
    COUNT(*) FILTER (
        WHERE account_status = 'ACTIVE'
    ) AS active_accounts
FROM account_projection;

-- Event distribution.
SELECT
    event_type,
    COUNT(*) AS event_count,
    MIN(occurred_at) AS first_occurrence,
    MAX(occurred_at) AS latest_occurrence
FROM event_store
GROUP BY event_type
ORDER BY event_count DESC;

-- Account-level reporting.
SELECT *
FROM account_event_report
ORDER BY total_events DESC;

-- ============================================================================
-- 17. ELIGIBILITY DETERMINATION
-- ============================================================================

-- Financial withdrawal eligibility is evaluated against the projection.
SELECT
    account_id,
    owner_name,
    balance,
    account_status,
    CASE
        WHEN account_status <> 'ACTIVE'
            THEN 'REJECTED: ACCOUNT FROZEN'
        WHEN balance < 1000
            THEN 'REJECTED: INSUFFICIENT BALANCE'
        ELSE 'ELIGIBLE'
    END AS withdrawal_eligibility
FROM account_projection;

-- ============================================================================
-- 18. SNAPSHOT CREATION
-- ============================================================================

INSERT INTO account_snapshots (
    aggregate_id,
    aggregate_version,
    snapshot_state
)
SELECT
    account_id,
    projection_version,
    jsonb_build_object(
        'owner', owner_name,
        'balance', balance,
        'status', account_status
    )
FROM account_projection
ON CONFLICT (aggregate_id, aggregate_version)
DO NOTHING;

-- Retrieve latest snapshots.
SELECT DISTINCT ON (aggregate_id)
    aggregate_id,
    aggregate_version,
    snapshot_state,
    created_at
FROM account_snapshots
ORDER BY aggregate_id, aggregate_version DESC;

-- ============================================================================
-- 19. EVENT REPLAY INTO A TEMPORARY PROJECTION
-- ============================================================================

CREATE TEMP TABLE replayed_accounts (
    account_id UUID PRIMARY KEY,
    owner_name VARCHAR(150),
    balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
    account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    version BIGINT NOT NULL DEFAULT 0
);

DO $$
DECLARE
    event_record RECORD;
    amount_value NUMERIC(18, 2);
BEGIN
    FOR event_record IN
        SELECT *
        FROM event_sourcing_demo.event_store
        ORDER BY aggregate_id, aggregate_version
    LOOP

        IF event_record.event_type = 'AccountOpened' THEN

            INSERT INTO replayed_accounts (
                account_id,
                owner_name,
                balance,
                account_status,
                version
            )
            VALUES (
                event_record.aggregate_id,
                event_record.event_payload->>'owner',
                0,
                'ACTIVE',
                1
            );

        ELSE

            amount_value := COALESCE(
                (event_record.event_payload->>'amount')::NUMERIC,
                0
            );

            UPDATE replayed_accounts
            SET
                balance = CASE
                    WHEN event_record.event_type = 'MoneyDeposited'
                        THEN balance + amount_value
                    WHEN event_record.event_type = 'MoneyWithdrawn'
                        THEN balance - amount_value
                    ELSE balance
                END,

                account_status = CASE
                    WHEN event_record.event_type = 'AccountFrozen'
                        THEN 'FROZEN'
                    WHEN event_record.event_type = 'AccountUnfrozen'
                        THEN 'ACTIVE'
                    ELSE account_status
                END,

                version = event_record.aggregate_version

            WHERE account_id = event_record.aggregate_id;

        END IF;

    END LOOP;
END;
$$;

-- Compare the independently rebuilt projection with the live projection.
SELECT
    a.account_id,
    a.balance AS replayed_balance,
    p.balance AS live_balance,
    a.version AS replayed_version,
    p.projection_version AS live_version,
    CASE
        WHEN a.balance = p.balance
         AND a.version = p.projection_version
        THEN 'MATCH'
        ELSE 'MISMATCH'
    END AS replay_result
FROM replayed_accounts a
JOIN account_projection p
    ON p.account_id = a.account_id;

-- ============================================================================
-- 20. WORKFLOW AND OPERATIONAL QUERIES
-- ============================================================================

-- Commands with missing event results.
SELECT *
FROM processed_commands
WHERE result_event_id IS NULL;

-- Aggregate streams requiring attention.
SELECT
    ah.aggregate_id,
    ah.current_version,
    ap.projection_version
FROM aggregate_heads ah
JOIN account_projection ap
    ON ap.account_id = ah.aggregate_id
WHERE ah.current_version <> ap.projection_version;

-- Event storage volume by aggregate.
SELECT
    aggregate_id,
    COUNT(*) AS stored_events,
    MAX(aggregate_version) AS latest_version
FROM event_store
GROUP BY aggregate_id
ORDER BY stored_events DESC;

-- ============================================================================
-- END OF EXECUTABLE DEMONSTRATION
-- ============================================================================
