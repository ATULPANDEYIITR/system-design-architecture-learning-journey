/*
============================================================
CQRS: COMMAND QUERY RESPONSIBILITY SEGREGATION
PostgreSQL 15+

Domain: Enterprise Banking Transaction Platform

Architecture:
    COMMAND API
         |
         v
    Command Processing
         |
         v
    Write Model / Account Aggregate
         |
         v
    Event Store
         |
         v
    Projection Worker
         |
         v
    Read Models
         |
         v
    Query API

Features:
- Separate write and read schemas
- Append-only event history
- Optimistic concurrency
- Command idempotency
- Transactional event persistence
- Transactional outbox
- Projection checkpoints
- Duplicate event protection
- Read-model rebuilding
- Reporting and aggregation
- Database-level integrity controls
============================================================
*/

-- =========================================================
-- 1. SCHEMAS
-- =========================================================

CREATE SCHEMA IF NOT EXISTS cqrs_write;
CREATE SCHEMA IF NOT EXISTS cqrs_read;

-- =========================================================
-- 2. ENUM TYPES
-- =========================================================

CREATE TYPE cqrs_write.account_status AS ENUM (
    'ACTIVE',
    'SUSPENDED',
    'CLOSED'
);

CREATE TYPE cqrs_write.command_type AS ENUM (
    'CREATE_ACCOUNT',
    'DEPOSIT',
    'WITHDRAW'
);

CREATE TYPE cqrs_write.event_type AS ENUM (
    'ACCOUNT_CREATED',
    'MONEY_DEPOSITED',
    'MONEY_WITHDRAWN'
);

CREATE TYPE cqrs_write.command_status AS ENUM (
    'RECEIVED',
    'PROCESSED',
    'REJECTED'
);

CREATE TYPE cqrs_write.projection_status AS ENUM (
    'PENDING',
    'PROCESSING',
    'PROCESSED',
    'FAILED'
);

-- =========================================================
-- 3. WRITE MODEL: ACCOUNTS
-- =========================================================

CREATE TABLE cqrs_write.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    account_number VARCHAR(30) NOT NULL UNIQUE,

    owner_name VARCHAR(150) NOT NULL,

    balance NUMERIC(19,2) NOT NULL DEFAULT 0,

    account_status cqrs_write.account_status
        NOT NULL DEFAULT 'ACTIVE',

    aggregate_version BIGINT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT positive_or_zero_balance
        CHECK (balance >= 0),

    CONSTRAINT valid_aggregate_version
        CHECK (aggregate_version >= 0),

    CONSTRAINT valid_account_number
        CHECK (account_number ~ '^[A-Z0-9-]{4,30}$'),

    CONSTRAINT valid_owner_name
        CHECK (LENGTH(TRIM(owner_name)) > 0)
);

CREATE INDEX idx_accounts_status
    ON cqrs_write.accounts(account_status);

-- =========================================================
-- 4. COMMAND REGISTRY
-- =========================================================

CREATE TABLE cqrs_write.commands (
    command_id UUID PRIMARY KEY,

    command_type cqrs_write.command_type NOT NULL,

    account_id BIGINT
        REFERENCES cqrs_write.accounts(account_id),

    amount NUMERIC(19,2),

    expected_version BIGINT,

    command_status cqrs_write.command_status
        NOT NULL DEFAULT 'RECEIVED',

    result JSONB,

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_at TIMESTAMPTZ,

    CONSTRAINT valid_command_amount
        CHECK (amount IS NULL OR amount > 0),

    CONSTRAINT valid_expected_version
        CHECK (expected_version IS NULL OR expected_version >= 0)
);

CREATE INDEX idx_commands_status
    ON cqrs_write.commands(command_status, created_at);

CREATE INDEX idx_commands_account
    ON cqrs_write.commands(account_id, created_at DESC);

-- =========================================================
-- 5. APPEND-ONLY EVENT STORE
-- =========================================================

CREATE TABLE cqrs_write.event_store (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    aggregate_type VARCHAR(50) NOT NULL,

    aggregate_id BIGINT NOT NULL,

    aggregate_version BIGINT NOT NULL,

    event_type cqrs_write.event_type NOT NULL,

    event_payload JSONB NOT NULL,

    command_id UUID
        REFERENCES cqrs_write.commands(command_id),

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT positive_event_version
        CHECK (aggregate_version > 0),

    CONSTRAINT unique_aggregate_version
        UNIQUE (aggregate_type, aggregate_id, aggregate_version),

    CONSTRAINT valid_event_payload
        CHECK (jsonb_typeof(event_payload) = 'object')
);

CREATE INDEX idx_event_aggregate
    ON cqrs_write.event_store(
        aggregate_type,
        aggregate_id,
        aggregate_version
    );

CREATE INDEX idx_event_type_time
    ON cqrs_write.event_store(event_type, occurred_at DESC);

CREATE INDEX idx_event_command
    ON cqrs_write.event_store(command_id);

CREATE INDEX idx_event_payload_gin
    ON cqrs_write.event_store USING GIN(event_payload);

-- =========================================================
-- 6. TRANSACTIONAL OUTBOX
-- =========================================================

CREATE TABLE cqrs_write.outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_id UUID NOT NULL UNIQUE
        REFERENCES cqrs_write.event_store(event_id),

    delivery_status cqrs_write.projection_status
        NOT NULL DEFAULT 'PENDING',

    attempts INTEGER NOT NULL DEFAULT 0,

    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    locked_at TIMESTAMPTZ,

    processed_at TIMESTAMPTZ,

    last_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT nonnegative_attempts
        CHECK (attempts >= 0)
);

CREATE INDEX idx_outbox_pending
    ON cqrs_write.outbox(available_at, outbox_id)
    WHERE delivery_status IN ('PENDING', 'FAILED');

-- =========================================================
-- 7. READ MODEL: ACCOUNT SUMMARY
-- =========================================================

CREATE TABLE cqrs_read.account_summary (
    account_id BIGINT PRIMARY KEY,

    account_number VARCHAR(30) NOT NULL UNIQUE,

    owner_name VARCHAR(150) NOT NULL,

    balance NUMERIC(19,2) NOT NULL DEFAULT 0,

    account_status cqrs_write.account_status NOT NULL,

    projection_version BIGINT NOT NULL DEFAULT 0,

    transaction_count BIGINT NOT NULL DEFAULT 0,

    last_event_at TIMESTAMPTZ,

    projected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT read_balance_nonnegative
        CHECK (balance >= 0),

    CONSTRAINT valid_projection_version
        CHECK (projection_version >= 0),

    CONSTRAINT valid_transaction_count
        CHECK (transaction_count >= 0)
);

CREATE INDEX idx_read_balance
    ON cqrs_read.account_summary(balance DESC);

CREATE INDEX idx_read_owner
    ON cqrs_read.account_summary(owner_name);

CREATE INDEX idx_read_status_balance
    ON cqrs_read.account_summary(account_status, balance DESC);

-- =========================================================
-- 8. READ MODEL: TRANSACTION HISTORY
-- =========================================================

CREATE TABLE cqrs_read.transaction_history (
    event_id UUID PRIMARY KEY,

    account_id BIGINT NOT NULL,

    account_number VARCHAR(30) NOT NULL,

    event_type cqrs_write.event_type NOT NULL,

    amount NUMERIC(19,2) NOT NULL,

    aggregate_version BIGINT NOT NULL,

    transaction_time TIMESTAMPTZ NOT NULL,

    CONSTRAINT history_positive_amount
        CHECK (amount > 0)
);

CREATE INDEX idx_history_account_time
    ON cqrs_read.transaction_history(
        account_id,
        transaction_time DESC
    );

CREATE INDEX idx_history_event_type
    ON cqrs_read.transaction_history(event_type);

-- =========================================================
-- 9. PROJECTION CHECKPOINTS
-- =========================================================

CREATE TABLE cqrs_read.projection_checkpoints (
    projection_name VARCHAR(100) PRIMARY KEY,

    last_processed_event_id UUID,

    last_processed_at TIMESTAMPTZ,

    events_processed BIGINT NOT NULL DEFAULT 0,

    projection_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT valid_processed_count
        CHECK (events_processed >= 0),

    CONSTRAINT valid_projection_status
        CHECK (
            projection_status IN (
                'ACTIVE',
                'PAUSED',
                'FAILED',
                'REBUILDING'
            )
        )
);

INSERT INTO cqrs_read.projection_checkpoints (
    projection_name
)
VALUES ('ACCOUNT_SUMMARY')
ON CONFLICT DO NOTHING;

INSERT INTO cqrs_read.projection_checkpoints (
    projection_name
)
VALUES ('TRANSACTION_HISTORY')
ON CONFLICT DO NOTHING;

-- =========================================================
-- 10. UPDATED_AT TRIGGER
-- =========================================================

CREATE OR REPLACE FUNCTION cqrs_write.update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_accounts_updated_at
BEFORE UPDATE ON cqrs_write.accounts
FOR EACH ROW
EXECUTE FUNCTION cqrs_write.update_timestamp();

-- =========================================================
-- 11. APPEND-ONLY EVENT ENFORCEMENT
-- =========================================================

CREATE OR REPLACE FUNCTION cqrs_write.prevent_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Event records are append-only and cannot be modified or deleted.';
END;
$$;

CREATE TRIGGER trg_event_no_update
BEFORE UPDATE OR DELETE ON cqrs_write.event_store
FOR EACH ROW
EXECUTE FUNCTION cqrs_write.prevent_event_mutation();

-- =========================================================
-- 12. COMMAND: CREATE ACCOUNT
-- =========================================================

CREATE OR REPLACE PROCEDURE cqrs_write.create_account(
    p_command_id UUID,
    p_account_number VARCHAR(30),
    p_owner_name VARCHAR(150)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_account_id BIGINT;
    v_event_id UUID;
BEGIN
    IF p_command_id IS NULL THEN
        RAISE EXCEPTION 'Command ID is required.';
    END IF;

    IF NULLIF(TRIM(p_account_number), '') IS NULL THEN
        RAISE EXCEPTION 'Account number is required.';
    END IF;

    IF NULLIF(TRIM(p_owner_name), '') IS NULL THEN
        RAISE EXCEPTION 'Owner name is required.';
    END IF;

    -- Command idempotency.
    INSERT INTO cqrs_write.commands (
        command_id,
        command_type
    )
    VALUES (
        p_command_id,
        'CREATE_ACCOUNT'
    )
    ON CONFLICT (command_id) DO NOTHING;

    IF NOT FOUND THEN
        IF EXISTS (
            SELECT 1
            FROM cqrs_write.commands
            WHERE command_id = p_command_id
              AND command_type = 'CREATE_ACCOUNT'
              AND command_status = 'PROCESSED'
        ) THEN
            RETURN;
        END IF;

        RAISE EXCEPTION 'Command already exists or is incomplete.';
    END IF;

    INSERT INTO cqrs_write.accounts (
        account_number,
        owner_name,
        balance,
        aggregate_version
    )
    VALUES (
        p_account_number,
        p_owner_name,
        0,
        0
    )
    RETURNING account_id INTO v_account_id;

    v_event_id := gen_random_uuid();

    UPDATE cqrs_write.accounts
    SET aggregate_version = 1
    WHERE account_id = v_account_id;

    INSERT INTO cqrs_write.event_store (
        event_id,
        aggregate_type,
        aggregate_id,
        aggregate_version,
        event_type,
        event_payload,
        command_id
    )
    VALUES (
        v_event_id,
        'BANK_ACCOUNT',
        v_account_id,
        1,
        'ACCOUNT_CREATED',
        jsonb_build_object(
            'account_number', p_account_number,
            'owner_name', p_owner_name,
            'initial_balance', 0
        ),
        p_command_id
    );

    INSERT INTO cqrs_write.outbox(event_id)
    VALUES (v_event_id);

    UPDATE cqrs_write.commands
    SET command_status = 'PROCESSED',
        result = jsonb_build_object(
            'account_id', v_account_id,
            'event_id', v_event_id
        ),
        completed_at = NOW()
    WHERE command_id = p_command_id;

END;
$$;

-- =========================================================
-- 13. COMMAND: DEPOSIT OR WITHDRAW
-- =========================================================

CREATE OR REPLACE PROCEDURE cqrs_write.process_transaction(
    p_command_id UUID,
    p_account_id BIGINT,
    p_command_type cqrs_write.command_type,
    p_amount NUMERIC(19,2),
    p_expected_version BIGINT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_account cqrs_write.accounts%ROWTYPE;
    v_event_type cqrs_write.event_type;
    v_new_balance NUMERIC(19,2);
    v_new_version BIGINT;
    v_event_id UUID;
BEGIN
    IF p_command_id IS NULL THEN
        RAISE EXCEPTION 'Command ID is required.';
    END IF;

    IF p_command_type NOT IN ('DEPOSIT', 'WITHDRAW') THEN
        RAISE EXCEPTION 'Unsupported transaction command.';
    END IF;

    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be positive.';
    END IF;

    IF p_expected_version IS NOT NULL
       AND p_expected_version < 0 THEN
        RAISE EXCEPTION 'Invalid expected version.';
    END IF;

    -- Lock the aggregate to prevent concurrent balance changes.
    SELECT *
    INTO v_account
    FROM cqrs_write.accounts
    WHERE account_id = p_account_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Account does not exist.';
    END IF;

    IF v_account.account_status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Account is not active.';
    END IF;

    -- Reject stale commands.
    IF p_expected_version IS NOT NULL
       AND p_expected_version <> v_account.aggregate_version THEN
        RAISE EXCEPTION
            'Concurrency conflict. Expected %, actual %.',
            p_expected_version,
            v_account.aggregate_version;
    END IF;

    -- Register the command inside the same transaction.
    INSERT INTO cqrs_write.commands (
        command_id,
        command_type,
        account_id,
        amount,
        expected_version
    )
    VALUES (
        p_command_id,
        p_command_type,
        p_account_id,
        p_amount,
        p_expected_version
    )
    ON CONFLICT (command_id) DO NOTHING;

    IF NOT FOUND THEN
        IF EXISTS (
            SELECT 1
            FROM cqrs_write.commands
            WHERE command_id = p_command_id
              AND account_id = p_account_id
              AND command_type = p_command_type
              AND amount = p_amount
              AND command_status = 'PROCESSED'
        ) THEN
            RETURN;
        END IF;

        RAISE EXCEPTION 'Duplicate or conflicting command ID.';
    END IF;

    IF p_command_type = 'DEPOSIT' THEN
        v_event_type := 'MONEY_DEPOSITED';
        v_new_balance := v_account.balance + p_amount;
    ELSE
        v_event_type := 'MONEY_WITHDRAWN';

        IF v_account.balance < p_amount THEN
            RAISE EXCEPTION 'Insufficient funds.';
        END IF;

        v_new_balance := v_account.balance - p_amount;
    END IF;

    v_new_version := v_account.aggregate_version + 1;
    v_event_id := gen_random_uuid();

    -- Update write model.
    UPDATE cqrs_write.accounts
    SET balance = v_new_balance,
        aggregate_version = v_new_version
    WHERE account_id = p_account_id;

    -- Append immutable event.
    INSERT INTO cqrs_write.event_store (
        event_id,
        aggregate_type,
        aggregate_id,
        aggregate_version,
        event_type,
        event_payload,
        command_id
    )
    VALUES (
        v_event_id,
        'BANK_ACCOUNT',
        p_account_id,
        v_new_version,
        v_event_type,
        jsonb_build_object(
            'amount', p_amount,
            'balance_after', v_new_balance
        ),
        p_command_id
    );

    -- Event publication is recorded transactionally.
    INSERT INTO cqrs_write.outbox(event_id)
    VALUES (v_event_id);

    UPDATE cqrs_write.commands
    SET command_status = 'PROCESSED',
        result = jsonb_build_object(
            'event_id', v_event_id,
            'balance', v_new_balance,
            'version', v_new_version
        ),
        completed_at = NOW()
    WHERE command_id = p_command_id;

END;
$$;

-- =========================================================
-- 14. READ PROJECTION FUNCTION
-- =========================================================

CREATE OR REPLACE FUNCTION cqrs_read.project_event(
    p_event_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_event cqrs_write.event_store%ROWTYPE;
    v_account cqrs_write.accounts%ROWTYPE;
    v_current_version BIGINT;
    v_amount NUMERIC(19,2);
BEGIN
    SELECT *
    INTO v_event
    FROM cqrs_write.event_store
    WHERE event_id = p_event_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Event does not exist.';
    END IF;

    -- Read projection is updated in the caller's transaction.
    SELECT *
    INTO v_account
    FROM cqrs_write.accounts
    WHERE account_id = v_event.aggregate_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Source account not found.';
    END IF;

    -- Duplicate delivery is safe.
    IF EXISTS (
        SELECT 1
        FROM cqrs_read.transaction_history
        WHERE event_id = p_event_id
    ) THEN
        RETURN FALSE;
    END IF;

    SELECT projection_version
    INTO v_current_version
    FROM cqrs_read.account_summary
    WHERE account_id = v_event.aggregate_id
    FOR UPDATE;

    IF v_event.event_type = 'ACCOUNT_CREATED' THEN

        IF FOUND THEN
            RAISE EXCEPTION 'Duplicate account creation projection.';
        END IF;

        INSERT INTO cqrs_read.account_summary (
            account_id,
            account_number,
            owner_name,
            balance,
            account_status,
            projection_version,
            transaction_count,
            last_event_at
        )
        VALUES (
            v_account.account_id,
            v_account.account_number,
            v_account.owner_name,
            0,
            v_account.account_status,
            1,
            0,
            v_event.occurred_at
        );

        RETURN TRUE;
    END IF;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Account read model does not exist.';
    END IF;

    IF v_event.aggregate_version <> v_current_version + 1 THEN
        RAISE EXCEPTION
            'Projection gap. Current %, incoming %.',
            v_current_version,
            v_event.aggregate_version;
    END IF;

    v_amount := (v_event.event_payload ->> 'amount')::NUMERIC;

    IF v_amount IS NULL OR v_amount <= 0 THEN
        RAISE EXCEPTION 'Invalid event amount.';
    END IF;

    IF v_event.event_type = 'MONEY_DEPOSITED' THEN

        UPDATE cqrs_read.account_summary
        SET balance = balance + v_amount,
            projection_version = v_event.aggregate_version,
            transaction_count = transaction_count + 1,
            last_event_at = v_event.occurred_at,
            projected_at = NOW()
        WHERE account_id = v_event.aggregate_id;

    ELSIF v_event.event_type = 'MONEY_WITHDRAWN' THEN

        UPDATE cqrs_read.account_summary
        SET balance = balance - v_amount,
            projection_version = v_event.aggregate_version,
            transaction_count = transaction_count + 1,
            last_event_at = v_event.occurred_at,
            projected_at = NOW()
        WHERE account_id = v_event.aggregate_id;

    END IF;

    INSERT INTO cqrs_read.transaction_history (
        event_id,
        account_id,
        account_number,
        event_type,
        amount,
        aggregate_version,
        transaction_time
    )
    VALUES (
        v_event.event_id,
        v_event.aggregate_id,
        v_account.account_number,
        v_event.event_type,
        v_amount,
        v_event.aggregate_version,
        v_event.occurred_at
    );

    RETURN TRUE;
END;
$$;

-- =========================================================
-- 15. OUTBOX PROCESSING PROCEDURE
-- =========================================================

CREATE OR REPLACE PROCEDURE cqrs_write.process_outbox(
    p_batch_size INTEGER DEFAULT 100
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_record RECORD;
    v_processed INTEGER := 0;
BEGIN
    IF p_batch_size <= 0 OR p_batch_size > 10000 THEN
        RAISE EXCEPTION 'Invalid batch size.';
    END IF;

    FOR v_record IN
        SELECT outbox_id, event_id
        FROM cqrs_write.outbox
        WHERE delivery_status IN ('PENDING', 'FAILED')
          AND available_at <= NOW()
        ORDER BY outbox_id
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    LOOP
        BEGIN
            UPDATE cqrs_write.outbox
            SET delivery_status = 'PROCESSING',
                attempts = attempts + 1,
                locked_at = NOW()
            WHERE outbox_id = v_record.outbox_id;

            PERFORM cqrs_read.project_event(v_record.event_id);

            UPDATE cqrs_write.outbox
            SET delivery_status = 'PROCESSED',
                processed_at = NOW(),
                last_error = NULL
            WHERE outbox_id = v_record.outbox_id;

            v_processed := v_processed + 1;

        EXCEPTION WHEN OTHERS THEN

            UPDATE cqrs_write.outbox
            SET delivery_status = 'FAILED',
                last_error = SQLERRM,
                available_at = NOW() + INTERVAL '1 minute'
            WHERE outbox_id = v_record.outbox_id;

            RAISE WARNING
                'Projection failed for event %: %',
                v_record.event_id,
                SQLERRM;
        END;
    END LOOP;

    RAISE NOTICE 'Processed % outbox records.', v_processed;
END;
$$;

-- =========================================================
-- 16. READ MODEL REPORTING VIEW
-- =========================================================

CREATE OR REPLACE VIEW cqrs_read.account_report AS
SELECT
    account_id,
    account_number,
    owner_name,
    balance,
    account_status,
    projection_version,
    transaction_count,
    last_event_at,
    projected_at
FROM cqrs_read.account_summary;

-- =========================================================
-- 17. ACCOUNT TRANSACTION AGGREGATION
-- =========================================================

CREATE OR REPLACE VIEW cqrs_read.transaction_analytics AS
SELECT
    account_id,
    account_number,

    COUNT(*) AS transaction_count,

    COUNT(*) FILTER (
        WHERE event_type = 'MONEY_DEPOSITED'
    ) AS deposit_count,

    COUNT(*) FILTER (
        WHERE event_type = 'MONEY_WITHDRAWN'
    ) AS withdrawal_count,

    SUM(amount) FILTER (
        WHERE event_type = 'MONEY_DEPOSITED'
    ) AS total_deposits,

    SUM(amount) FILTER (
        WHERE event_type = 'MONEY_WITHDRAWN'
    ) AS total_withdrawals,

    MAX(transaction_time) AS last_transaction

FROM cqrs_read.transaction_history
GROUP BY account_id, account_number;

-- =========================================================
-- 18. RECONCILIATION QUERY
-- =========================================================

CREATE OR REPLACE VIEW cqrs_read.account_reconciliation AS
SELECT
    write_account.account_id,
    write_account.account_number,
    write_account.balance AS write_balance,
    read_account.balance AS read_balance,

    write_account.aggregate_version AS write_version,
    read_account.projection_version AS read_version,

    write_account.balance - read_account.balance
        AS balance_difference,

    CASE
        WHEN read_account.account_id IS NULL
            THEN 'MISSING_READ_MODEL'

        WHEN write_account.aggregate_version
             <> read_account.projection_version
            THEN 'PROJECTION_LAG'

        WHEN write_account.balance <> read_account.balance
            THEN 'BALANCE_MISMATCH'

        ELSE 'CONSISTENT'
    END AS reconciliation_status

FROM cqrs_write.accounts write_account

LEFT JOIN cqrs_read.account_summary read_account
    ON write_account.account_id = read_account.account_id;

-- =========================================================
-- 19. ELIGIBILITY DETERMINATION
-- =========================================================

CREATE OR REPLACE FUNCTION cqrs_read.account_eligibility(
    p_account_id BIGINT
)
RETURNS TABLE (
    account_id BIGINT,
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        a.account_id,

        (
            a.account_status = 'ACTIVE'
            AND a.balance >= 0
            AND r.account_id IS NOT NULL
            AND r.projection_version = a.aggregate_version
            AND r.balance = a.balance
        ) AS eligible,

        CASE
            WHEN a.account_status <> 'ACTIVE'
                THEN 'ACCOUNT_NOT_ACTIVE'

            WHEN r.account_id IS NULL
                THEN 'READ_MODEL_NOT_AVAILABLE'

            WHEN r.projection_version <> a.aggregate_version
                THEN 'PROJECTION_NOT_SYNCHRONIZED'

            WHEN r.balance <> a.balance
                THEN 'BALANCE_MISMATCH'

            ELSE 'ELIGIBLE'
        END AS reason

    FROM cqrs_write.accounts a

    LEFT JOIN cqrs_read.account_summary r
        ON r.account_id = a.account_id

    WHERE a.account_id = p_account_id;
$$;

-- =========================================================
-- 20. SAMPLE DATA AND TRANSACTIONAL WORKFLOW
-- =========================================================

BEGIN;

CALL cqrs_write.create_account(
    '10000000-0000-0000-0000-000000000001',
    'ACC-5001',
    'Ananya Sharma'
);

CALL cqrs_write.create_account(
    '10000000-0000-0000-0000-000000000002',
    'ACC-5002',
    'Rohan Mehta'
);

CALL cqrs_write.process_transaction(
    '20000000-0000-0000-0000-000000000001',
    1,
    'DEPOSIT',
    15000.00,
    1
);

CALL cqrs_write.process_transaction(
    '20000000-0000-0000-0000-000000000002',
    1,
    'DEPOSIT',
    5000.00,
    2
);

CALL cqrs_write.process_transaction(
    '20000000-0000-0000-0000-000000000003',
    1,
    'WITHDRAW',
    3000.00,
    3
);

CALL cqrs_write.process_transaction(
    '20000000-0000-0000-0000-000000000004',
    2,
    'DEPOSIT',
    8000.00,
    1
);

COMMIT;

-- =========================================================
-- 21. PROJECT EVENTS INTO READ MODELS
-- =========================================================

CALL cqrs_write.process_outbox(100);

-- =========================================================
-- 22. QUERY: ACCOUNT RETRIEVAL
-- =========================================================

SELECT *
FROM cqrs_read.account_report
ORDER BY account_id;

-- =========================================================
-- 23. QUERY: TRANSACTION HISTORY
-- =========================================================

SELECT
    account_number,
    event_type,
    amount,
    aggregate_version,
    transaction_time
FROM cqrs_read.transaction_history
WHERE account_id = 1
ORDER BY aggregate_version;

-- =========================================================
-- 24. QUERY: AGGREGATION
-- =========================================================

SELECT *
FROM cqrs_read.transaction_analytics
ORDER BY total_deposits DESC;

-- =========================================================
-- 25. QUERY: ELIGIBILITY
-- =========================================================

SELECT *
FROM cqrs_read.account_eligibility(1);

-- =========================================================
-- 26. QUERY: RECONCILIATION
-- =========================================================

SELECT *
FROM cqrs_read.account_reconciliation
ORDER BY account_id;

-- =========================================================
-- 27. QUERY: EVENT HISTORY
-- =========================================================

SELECT
    aggregate_id,
    aggregate_version,
    event_type,
    event_payload,
    occurred_at
FROM cqrs_write.event_store
ORDER BY aggregate_id, aggregate_version;

-- =========================================================
-- 28. QUERY: COMMAND PROCESSING STATUS
-- =========================================================

SELECT
    command_id,
    command_type,
    account_id,
    command_status,
    result,
    error_message,
    created_at,
    completed_at
FROM cqrs_write.commands
ORDER BY created_at;

-- =========================================================
-- 29. QUERY: OUTBOX HEALTH
-- =========================================================

SELECT
    delivery_status,
    COUNT(*) AS event_count,
    SUM(attempts) AS total_attempts
FROM cqrs_write.outbox
GROUP BY delivery_status
ORDER BY delivery_status;

-- =========================================================
-- 30. QUERY: PROJECTION LAG
-- =========================================================

SELECT
    a.account_number,
    a.aggregate_version,
    r.projection_version,
    a.aggregate_version - COALESCE(r.projection_version, 0)
        AS version_lag
FROM cqrs_write.accounts a
LEFT JOIN cqrs_read.account_summary r
    ON r.account_id = a.account_id
ORDER BY version_lag DESC;

-- =========================================================
-- 31. VALIDATION: INSUFFICIENT FUNDS
-- =========================================================

DO $$
BEGIN
    BEGIN
        CALL cqrs_write.process_transaction(
            '30000000-0000-0000-0000-000000000001',
            1,
            'WITHDRAW',
            999999.00,
            4
        );

        RAISE EXCEPTION
            'Expected insufficient-funds rejection did not occur.';

    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM LIKE 'Expected insufficient-funds%' THEN
            RAISE;
        END IF;

        RAISE NOTICE
            'Invalid withdrawal rejected: %',
            SQLERRM;
    END;
END;
$$;

-- =========================================================
-- 32. VALIDATION: STALE VERSION
-- =========================================================

DO $$
BEGIN
    BEGIN
        CALL cqrs_write.process_transaction(
            '30000000-0000-0000-0000-000000000002',
            1,
            'DEPOSIT',
            100.00,
            1
        );

        RAISE EXCEPTION
            'Expected concurrency rejection did not occur.';

    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM LIKE 'Expected concurrency rejection%' THEN
            RAISE;
        END IF;

        RAISE NOTICE
            'Stale command rejected: %',
            SQLERRM;
    END;
END;
$$;

-- =========================================================
-- 33. IDEMPOTENCY VALIDATION
-- =========================================================

-- Repeating the same processed command returns without
-- creating another event.

CALL cqrs_write.process_transaction(
    '20000000-0000-0000-0000-000000000001',
    1,
    'DEPOSIT',
    15000.00,
    1
);

-- =========================================================
-- 34. PROJECTION REBUILD
-- =========================================================

-- Full rebuild is performed transactionally.
-- In production, use a shadow projection table and switch
-- readers after successful validation.

BEGIN;

TRUNCATE TABLE cqrs_read.transaction_history;

TRUNCATE TABLE cqrs_read.account_summary;

INSERT INTO cqrs_read.account_summary (
    account_id,
    account_number,
    owner_name,
    balance,
    account_status,
    projection_version,
    transaction_count,
    last_event_at
)
SELECT
    account_id,
    account_number,
    owner_name,
    0,
    account_status,
    1,
    0,
    created_at
FROM cqrs_write.accounts
WHERE EXISTS (
    SELECT 1
    FROM cqrs_write.event_store e
    WHERE e.aggregate_id = accounts.account_id
      AND e.event_type = 'ACCOUNT_CREATED'
      AND e.aggregate_version = 1
);

-- Replay monetary events in aggregate order.
WITH event_balances AS (
    SELECT
        event_id,
        aggregate_id,
        aggregate_version,
        event_type,
        (event_payload ->> 'amount')::NUMERIC AS amount,
        occurred_at,

        SUM(
            CASE
                WHEN event_type = 'MONEY_DEPOSITED'
                    THEN (event_payload ->> 'amount')::NUMERIC
                WHEN event_type = 'MONEY_WITHDRAWN'
                    THEN -(event_payload ->> 'amount')::NUMERIC
                ELSE 0
            END
        ) OVER (
            PARTITION BY aggregate_id
            ORDER BY aggregate_version
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_balance

    FROM cqrs_write.event_store
    WHERE event_type IN (
        'MONEY_DEPOSITED',
        'MONEY_WITHDRAWN'
    )
)
INSERT INTO cqrs_read.transaction_history (
    event_id,
    account_id,
    account_number,
    event_type,
    amount,
    aggregate_version,
    transaction_time
)
SELECT
    e.event_id,
    e.aggregate_id,
    a.account_number,
    e.event_type,
    e.amount,
    e.aggregate_version,
    e.occurred_at
FROM event_balances e
JOIN cqrs_write.accounts a
    ON a.account_id = e.aggregate_id;

UPDATE cqrs_read.account_summary summary
SET balance = source.balance,
    projection_version = source.aggregate_version,
    transaction_count = source.transaction_count,
    last_event_at = source.last_event_at,
    projected_at = NOW()
FROM (
    SELECT
        a.account_id,
        a.balance,
        a.aggregate_version,
        COUNT(h.event_id) AS transaction_count,
        MAX(h.transaction_time) AS last_event_at
    FROM cqrs_write.accounts a
    LEFT JOIN cqrs_read.transaction_history h
        ON h.account_id = a.account_id
    GROUP BY
        a.account_id,
        a.balance,
        a.aggregate_version
) source
WHERE summary.account_id = source.account_id;

UPDATE cqrs_read.projection_checkpoints
SET projection_status = 'ACTIVE',
    events_processed = (
        SELECT COUNT(*)
        FROM cqrs_write.event_store
    ),
    last_processed_at = NOW()
WHERE projection_name = 'ACCOUNT_SUMMARY';

UPDATE cqrs_read.projection_checkpoints
SET projection_status = 'ACTIVE',
    events_processed = (
        SELECT COUNT(*)
        FROM cqrs_read.transaction_history
    ),
    last_processed_at = NOW()
WHERE projection_name = 'TRANSACTION_HISTORY';

COMMIT;

-- =========================================================
-- 35. FINAL INTEGRITY REPORT
-- =========================================================

SELECT
    COUNT(*) AS total_accounts,
    SUM(balance) AS total_balance,
    SUM(transaction_count) AS total_transactions,
    COUNT(*) FILTER (
        WHERE projection_version = 0
    ) AS uninitialized_projections
FROM cqrs_read.account_summary;

SELECT *
FROM cqrs_read.account_reconciliation
WHERE reconciliation_status <> 'CONSISTENT';

-- =========================================================
-- END OF CQRS POSTGRESQL IMPLEMENTATION
-- =========================================================
