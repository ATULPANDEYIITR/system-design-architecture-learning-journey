-- ============================================================
-- DISASTER RECOVERY MANAGEMENT DATABASE
-- PostgreSQL 15+
--
-- Domain:
--   Backup management
--   Backup verification
--   Full, incremental and differential backups
--   Disaster incidents
--   Recovery authorization
--   Restore operations
--   RPO and RTO compliance
--   Retention management
--   Recovery reporting
--
-- Run in a dedicated development database.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS disaster_recovery;

SET search_path TO disaster_recovery, public;

-- ============================================================
-- 1. ENUMERATIONS
-- ============================================================

CREATE TYPE backup_type AS ENUM (
    'FULL',
    'INCREMENTAL',
    'DIFFERENTIAL'
);

CREATE TYPE backup_status AS ENUM (
    'CREATED',
    'VERIFIED',
    'FAILED',
    'RESTORED'
);

CREATE TYPE incident_severity AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

CREATE TYPE incident_status AS ENUM (
    'OPEN',
    'ASSESSING',
    'RECOVERING',
    'RECOVERED',
    'FAILED',
    'CLOSED'
);

CREATE TYPE recovery_action AS ENUM (
    'RESTORE',
    'FAILOVER',
    'POINT_IN_TIME_RECOVERY'
);

CREATE TYPE recovery_status AS ENUM (
    'PENDING',
    'IN_PROGRESS',
    'SUCCESS',
    'FAILED'
);

CREATE TYPE storage_class AS ENUM (
    'LOCAL',
    'OFFSITE',
    'IMMUTABLE',
    'CLOUD'
);

-- ============================================================
-- 2. REPOSITORY OF PROTECTED SYSTEMS
-- ============================================================

CREATE TABLE protected_systems (
    system_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_name VARCHAR(150) NOT NULL UNIQUE,
    business_owner VARCHAR(150) NOT NULL,
    criticality VARCHAR(20) NOT NULL,
    data_classification VARCHAR(30) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_criticality CHECK (
        criticality IN (
            'LOW',
            'MEDIUM',
            'HIGH',
            'CRITICAL'
        )
    ),

    CONSTRAINT valid_classification CHECK (
        data_classification IN (
            'PUBLIC',
            'INTERNAL',
            'CONFIDENTIAL',
            'RESTRICTED'
        )
    )
);

-- ============================================================
-- 3. RECOVERY POLICIES
-- ============================================================

CREATE TABLE recovery_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_id BIGINT NOT NULL UNIQUE
        REFERENCES protected_systems(system_id),

    policy_name VARCHAR(150) NOT NULL,
    rpo_minutes INTEGER NOT NULL,
    rto_minutes INTEGER NOT NULL,
    retention_days INTEGER NOT NULL,

    require_offsite BOOLEAN NOT NULL DEFAULT TRUE,
    require_integrity_check BOOLEAN NOT NULL DEFAULT TRUE,
    minimum_approvals INTEGER NOT NULL DEFAULT 2,
    allow_point_in_time_recovery BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_rpo CHECK (rpo_minutes >= 0),
    CONSTRAINT valid_rto CHECK (rto_minutes > 0),
    CONSTRAINT valid_retention CHECK (retention_days > 0),
    CONSTRAINT valid_approvals CHECK (minimum_approvals >= 1)
);

-- ============================================================
-- 4. BACKUP STORAGE LOCATIONS
-- ============================================================

CREATE TABLE backup_storage (
    storage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    storage_name VARCHAR(150) NOT NULL UNIQUE,
    storage_type storage_class NOT NULL,
    region VARCHAR(100) NOT NULL,
    encrypted BOOLEAN NOT NULL DEFAULT TRUE,
    immutable BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT immutable_storage_rule CHECK (
        NOT immutable OR storage_type = 'IMMUTABLE'
    )
);

-- ============================================================
-- 5. BACKUP INVENTORY
-- ============================================================

CREATE TABLE backups (
    backup_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    system_id BIGINT NOT NULL
        REFERENCES protected_systems(system_id),

    storage_id BIGINT NOT NULL
        REFERENCES backup_storage(storage_id),

    parent_backup_id BIGINT
        REFERENCES backups(backup_id),

    backup_name VARCHAR(200) NOT NULL,
    backup_kind backup_type NOT NULL,
    status backup_status NOT NULL DEFAULT 'CREATED',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_timestamp TIMESTAMPTZ NOT NULL,

    size_bytes BIGINT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,

    encrypted BOOLEAN NOT NULL DEFAULT TRUE,
    verified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,

    CONSTRAINT positive_size CHECK (size_bytes > 0),

    CONSTRAINT valid_checksum CHECK (
        checksum_sha256 ~ '^[0-9a-fA-F]{64}$'
    ),

    CONSTRAINT valid_parent_relationship CHECK (
        parent_backup_id IS NULL OR
        parent_backup_id <> backup_id
    ),

    CONSTRAINT valid_expiration CHECK (
        expires_at IS NULL OR expires_at > created_at
    )
);

CREATE INDEX idx_backups_system_time
ON backups(system_id, data_timestamp DESC);

CREATE INDEX idx_backups_verified
ON backups(system_id, data_timestamp DESC)
WHERE status = 'VERIFIED';

CREATE INDEX idx_backups_parent
ON backups(parent_backup_id)
WHERE parent_backup_id IS NOT NULL;

CREATE INDEX idx_backups_expiration
ON backups(expires_at)
WHERE expires_at IS NOT NULL;

-- ============================================================
-- 6. BACKUP INTEGRITY AUDIT
-- ============================================================

CREATE TABLE backup_verifications (
    verification_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    backup_id BIGINT NOT NULL
        REFERENCES backups(backup_id),

    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expected_checksum VARCHAR(64) NOT NULL,
    observed_checksum VARCHAR(64) NOT NULL,

    passed BOOLEAN NOT NULL,
    verification_method VARCHAR(50) NOT NULL,
    verified_by VARCHAR(150) NOT NULL,

    CONSTRAINT valid_verification_method CHECK (
        verification_method IN (
            'CHECKSUM',
            'RESTORE_TEST',
            'APPLICATION_VALIDATION'
        )
    )
);

CREATE INDEX idx_verification_backup
ON backup_verifications(backup_id, verified_at DESC);

-- ============================================================
-- 7. RECOVERY PERSONNEL
-- ============================================================

CREATE TABLE recovery_personnel (
    personnel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    personnel_name VARCHAR(150) NOT NULL,
    email VARCHAR(200) NOT NULL UNIQUE,
    role_name VARCHAR(60) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT valid_recovery_role CHECK (
        role_name IN (
            'OPERATIONS_MANAGER',
            'SECURITY_MANAGER',
            'DR_MANAGER',
            'DATABASE_ADMIN',
            'AUDITOR',
            'SYSTEM_ADMIN'
        )
    )
);

-- ============================================================
-- 8. DISASTER INCIDENTS
-- ============================================================

CREATE TABLE disaster_incidents (
    incident_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    system_id BIGINT NOT NULL
        REFERENCES protected_systems(system_id),

    incident_title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,

    severity incident_severity NOT NULL,
    status incident_status NOT NULL DEFAULT 'OPEN',

    occurred_at TIMESTAMPTZ NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,

    CONSTRAINT valid_incident_timestamps CHECK (
        detected_at >= occurred_at
    ),

    CONSTRAINT valid_resolution_timestamp CHECK (
        resolved_at IS NULL OR resolved_at >= occurred_at
    )
);

CREATE INDEX idx_incidents_system
ON disaster_incidents(system_id, occurred_at DESC);

CREATE INDEX idx_incidents_open
ON disaster_incidents(status, severity)
WHERE status NOT IN ('RECOVERED', 'CLOSED');

-- ============================================================
-- 9. RECOVERY APPROVALS
-- ============================================================

CREATE TABLE recovery_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    incident_id BIGINT NOT NULL
        REFERENCES disaster_incidents(incident_id),

    personnel_id BIGINT NOT NULL
        REFERENCES recovery_personnel(personnel_id),

    approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decision BOOLEAN NOT NULL,
    comments TEXT,

    UNIQUE (incident_id, personnel_id)
);

CREATE INDEX idx_recovery_approvals_incident
ON recovery_approvals(incident_id, decision);

-- ============================================================
-- 10. RESTORE OPERATIONS
-- ============================================================

CREATE TABLE recovery_operations (
    recovery_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    incident_id BIGINT NOT NULL
        REFERENCES disaster_incidents(incident_id),

    backup_id BIGINT NOT NULL
        REFERENCES backups(backup_id),

    action recovery_action NOT NULL,
    status recovery_status NOT NULL DEFAULT 'PENDING',

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    actual_rpo_minutes NUMERIC(14,4),
    actual_rto_minutes NUMERIC(14,4),

    rpo_met BOOLEAN,
    rto_met BOOLEAN,

    initiated_by BIGINT
        REFERENCES recovery_personnel(personnel_id),

    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_recovery_duration CHECK (
        actual_rto_minutes IS NULL OR
        actual_rto_minutes >= 0
    ),

    CONSTRAINT valid_recovery_rpo CHECK (
        actual_rpo_minutes IS NULL OR
        actual_rpo_minutes >= 0
    ),

    CONSTRAINT valid_operation_timestamps CHECK (
        completed_at IS NULL OR
        (
            started_at IS NOT NULL AND
            completed_at >= started_at
        )
    ),

    CONSTRAINT successful_operation_metrics CHECK (
        status <> 'SUCCESS' OR
        (
            started_at IS NOT NULL AND
            completed_at IS NOT NULL AND
            actual_rpo_minutes IS NOT NULL AND
            actual_rto_minutes IS NOT NULL
        )
    )
);

CREATE INDEX idx_recovery_incident
ON recovery_operations(incident_id, created_at DESC);

CREATE INDEX idx_recovery_status
ON recovery_operations(status, created_at DESC);

-- ============================================================
-- 11. BACKUP VALIDATION TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION validate_backup_insert()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_system_active BOOLEAN;
    v_storage_active BOOLEAN;
    v_storage_type storage_class;
    v_require_offsite BOOLEAN;
    v_parent_system BIGINT;
    v_parent_status backup_status;
    v_parent_timestamp TIMESTAMPTZ;
BEGIN
    SELECT active
    INTO v_system_active
    FROM protected_systems
    WHERE system_id = NEW.system_id;

    IF NOT COALESCE(v_system_active, FALSE) THEN
        RAISE EXCEPTION 'Protected system is inactive';
    END IF;

    SELECT active, storage_type
    INTO v_storage_active, v_storage_type
    FROM backup_storage
    WHERE storage_id = NEW.storage_id;

    IF NOT COALESCE(v_storage_active, FALSE) THEN
        RAISE EXCEPTION 'Backup storage is inactive';
    END IF;

    SELECT require_offsite
    INTO v_require_offsite
    FROM recovery_policies
    WHERE system_id = NEW.system_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active recovery policy is required';
    END IF;

    IF v_require_offsite AND v_storage_type = 'LOCAL' THEN
        RAISE EXCEPTION 'Offsite backup policy violated';
    END IF;

    IF NEW.backup_kind = 'FULL' AND
       NEW.parent_backup_id IS NOT NULL THEN
        RAISE EXCEPTION 'Full backups cannot have a parent';
    END IF;

    IF NEW.backup_kind IN ('INCREMENTAL', 'DIFFERENTIAL') THEN
        IF NEW.parent_backup_id IS NULL THEN
            RAISE EXCEPTION 'Dependent backup requires a parent';
        END IF;

        SELECT system_id, status, data_timestamp
        INTO v_parent_system, v_parent_status, v_parent_timestamp
        FROM backups
        WHERE backup_id = NEW.parent_backup_id
        FOR KEY SHARE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Parent backup does not exist';
        END IF;

        IF v_parent_system <> NEW.system_id THEN
            RAISE EXCEPTION 'Parent backup belongs to another system';
        END IF;

        IF v_parent_status NOT IN ('VERIFIED', 'RESTORED') THEN
            RAISE EXCEPTION 'Parent backup is not verified';
        END IF;

        IF NEW.data_timestamp < v_parent_timestamp THEN
            RAISE EXCEPTION 'Backup timestamp precedes parent';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_backup_insert
BEFORE INSERT ON backups
FOR EACH ROW
EXECUTE FUNCTION validate_backup_insert();

-- ============================================================
-- 12. BACKUP STATUS TRANSITION TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION validate_backup_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'RESTORED' AND NEW.status <> 'RESTORED' THEN
        RAISE EXCEPTION 'Restored backup state is terminal';
    END IF;

    IF OLD.status = 'FAILED' AND NEW.status <> 'FAILED' THEN
        RAISE EXCEPTION 'Failed backup cannot be reused';
    END IF;

    IF NEW.status = 'VERIFIED' AND
       NEW.verified_at IS NULL THEN
        NEW.verified_at = NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_backup_status_transition
BEFORE UPDATE OF status ON backups
FOR EACH ROW
EXECUTE FUNCTION validate_backup_transition();

-- ============================================================
-- 13. INCIDENT STATUS TRANSITION TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION validate_incident_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('RECOVERED', 'CLOSED', 'FAILED') AND
       NEW.status NOT IN ('CLOSED') THEN
        RAISE EXCEPTION 'Invalid terminal incident transition';
    END IF;

    IF NEW.status = 'CLOSED' AND
       OLD.status NOT IN ('RECOVERED', 'FAILED') THEN
        RAISE EXCEPTION 'Incident must be recovered or failed before closure';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_incident_status_transition
BEFORE UPDATE OF status ON disaster_incidents
FOR EACH ROW
EXECUTE FUNCTION validate_incident_transition();

-- ============================================================
-- 14. RECOVERY ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_recovery_eligibility(
    p_incident_id BIGINT,
    p_backup_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    selected_backup_id BIGINT,
    actual_rpo_minutes NUMERIC,
    rpo_met BOOLEAN,
    violation TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_system_id BIGINT;
    v_occurred_at TIMESTAMPTZ;
    v_incident_status incident_status;
    v_rpo INTEGER;
    v_require_offsite BOOLEAN;
    v_storage_type storage_class;
    v_backup_status backup_status;
    v_backup_system BIGINT;
    v_data_timestamp TIMESTAMPTZ;
    v_actual_rpo NUMERIC;
    v_approvals INTEGER;
    v_required INTEGER;
    v_offsite_valid BOOLEAN;
BEGIN
    SELECT system_id, occurred_at, status
    INTO v_system_id, v_occurred_at, v_incident_status
    FROM disaster_incidents
    WHERE incident_id = p_incident_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Incident not found';
        RETURN;
    END IF;

    IF v_incident_status <> 'OPEN' THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Incident is not open';
        RETURN;
    END IF;

    SELECT rpo_minutes, require_offsite, minimum_approvals
    INTO v_rpo, v_require_offsite, v_required
    FROM recovery_policies
    WHERE system_id = v_system_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Active recovery policy not found';
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO v_approvals
    FROM recovery_approvals
    WHERE incident_id = p_incident_id
      AND decision = TRUE;

    IF v_approvals < v_required THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Insufficient recovery approvals';
        RETURN;
    END IF;

    SELECT
        b.status,
        b.system_id,
        b.data_timestamp,
        s.storage_type
    INTO
        v_backup_status,
        v_backup_system,
        v_data_timestamp,
        v_storage_type
    FROM backups b
    JOIN backup_storage s
      ON s.storage_id = b.storage_id
    WHERE b.backup_id = p_backup_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Backup not found';
        RETURN;
    END IF;

    IF v_backup_system <> v_system_id THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Backup belongs to another system';
        RETURN;
    END IF;

    IF v_backup_status <> 'VERIFIED' THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Backup is not verified';
        RETURN;
    END IF;

    IF v_data_timestamp > v_occurred_at THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Backup contains a future recovery point';
        RETURN;
    END IF;

    v_offsite_valid :=
        NOT v_require_offsite OR
        v_storage_type <> 'LOCAL';

    IF NOT v_offsite_valid THEN
        RETURN QUERY SELECT
            FALSE, NULL::BIGINT, NULL::NUMERIC,
            FALSE, 'Offsite storage requirement violated';
        RETURN;
    END IF;

    v_actual_rpo :=
        EXTRACT(EPOCH FROM (
            v_occurred_at - v_data_timestamp
        )) / 60;

    RETURN QUERY SELECT
        v_actual_rpo <= v_rpo,
        p_backup_id,
        v_actual_rpo,
        v_actual_rpo <= v_rpo,
        CASE
            WHEN v_actual_rpo > v_rpo
            THEN 'RPO requirement violated'
            ELSE NULL
        END;
END;
$$;

-- ============================================================
-- 15. RECOVERY EXECUTION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE execute_recovery(
    p_incident_id BIGINT,
    p_backup_id BIGINT,
    p_personnel_id BIGINT,
    p_action recovery_action DEFAULT 'RESTORE'
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_system_id BIGINT;
    v_incident_time TIMESTAMPTZ;
    v_incident_status incident_status;

    v_policy_id BIGINT;
    v_rpo INTEGER;
    v_rto INTEGER;
    v_minimum_approvals INTEGER;

    v_approval_count INTEGER;
    v_backup_timestamp TIMESTAMPTZ;
    v_backup_status backup_status;

    v_actual_rpo NUMERIC;
    v_actual_rto NUMERIC;

    v_recovery_id BIGINT;
    v_started TIMESTAMPTZ;
    v_completed TIMESTAMPTZ;

    v_eligibility RECORD;
BEGIN
    -- Locks prevent concurrent recovery attempts for one incident.
    SELECT system_id, occurred_at, status
    INTO v_system_id, v_incident_time, v_incident_status
    FROM disaster_incidents
    WHERE incident_id = p_incident_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Incident does not exist';
    END IF;

    IF v_incident_status <> 'OPEN' THEN
        RAISE EXCEPTION 'Incident is not open';
    END IF;

    SELECT policy_id, rpo_minutes, rto_minutes,
           minimum_approvals
    INTO v_policy_id, v_rpo, v_rto, v_minimum_approvals
    FROM recovery_policies
    WHERE system_id = v_system_id
      AND active = TRUE
    FOR SHARE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active recovery policy not found';
    END IF;

    SELECT COUNT(*)
    INTO v_approval_count
    FROM recovery_approvals a
    JOIN recovery_personnel p
      ON p.personnel_id = a.personnel_id
    WHERE a.incident_id = p_incident_id
      AND a.decision = TRUE
      AND p.active = TRUE
      AND p.role_name IN (
          'OPERATIONS_MANAGER',
          'SECURITY_MANAGER',
          'DR_MANAGER'
      );

    IF v_approval_count < v_minimum_approvals THEN
        RAISE EXCEPTION 'Recovery approval requirement not met';
    END IF;

    PERFORM 1
    FROM recovery_personnel
    WHERE personnel_id = p_personnel_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Recovery initiator is inactive or unknown';
    END IF;

    SELECT *
    INTO v_eligibility
    FROM evaluate_recovery_eligibility(
        p_incident_id,
        p_backup_id
    );

    IF NOT v_eligibility.eligible THEN
        RAISE EXCEPTION 'Recovery ineligible: %',
            v_eligibility.violation;
    END IF;

    SELECT data_timestamp, status
    INTO v_backup_timestamp, v_backup_status
    FROM backups
    WHERE backup_id = p_backup_id
    FOR UPDATE;

    IF v_backup_status <> 'VERIFIED' THEN
        RAISE EXCEPTION 'Backup changed during eligibility evaluation';
    END IF;

    v_started := clock_timestamp();

    INSERT INTO recovery_operations (
        incident_id,
        backup_id,
        action,
        status,
        started_at,
        actual_rpo_minutes,
        initiated_by
    )
    VALUES (
        p_incident_id,
        p_backup_id,
        p_action,
        'IN_PROGRESS',
        v_started,
        v_eligibility.actual_rpo_minutes,
        p_personnel_id
    )
    RETURNING recovery_id INTO v_recovery_id;

    UPDATE disaster_incidents
    SET status = 'RECOVERING'
    WHERE incident_id = p_incident_id;

    /*
     * This procedure records and governs the recovery operation.
     * Physical restoration of files, database pages, encryption
     * keys, and application services must be performed by the
     * corresponding infrastructure recovery system.
     */

    v_completed := clock_timestamp();

    v_actual_rto :=
        EXTRACT(EPOCH FROM (v_completed - v_started)) / 60;

    UPDATE recovery_operations
    SET
        status = 'SUCCESS',
        completed_at = v_completed,
        actual_rto_minutes = v_actual_rto,
        rpo_met = v_eligibility.actual_rpo_minutes <= v_rpo,
        rto_met = v_actual_rto <= v_rto
    WHERE recovery_id = v_recovery_id;

    UPDATE backups
    SET status = 'RESTORED'
    WHERE backup_id = p_backup_id;

    UPDATE disaster_incidents
    SET
        status = 'RECOVERED',
        resolved_at = v_completed
    WHERE incident_id = p_incident_id;

EXCEPTION
    WHEN OTHERS THEN
        /*
         * The surrounding transaction rolls back database state.
         * External restore operations need independent compensation
         * and idempotency handling.
         */
        RAISE;
END;
$$;

-- ============================================================
-- 16. BACKUP VERIFICATION REGISTRATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE register_backup_verification(
    p_backup_id BIGINT,
    p_expected_checksum VARCHAR(64),
    p_observed_checksum VARCHAR(64),
    p_method VARCHAR(50),
    p_verified_by VARCHAR(150)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_passed BOOLEAN;
BEGIN
    v_passed := lower(p_expected_checksum) =
                lower(p_observed_checksum);

    INSERT INTO backup_verifications (
        backup_id,
        expected_checksum,
        observed_checksum,
        passed,
        verification_method,
        verified_by
    )
    VALUES (
        p_backup_id,
        p_expected_checksum,
        p_observed_checksum,
        v_passed,
        p_method,
        p_verified_by
    );

    UPDATE backups
    SET
        status = CASE
            WHEN v_passed THEN 'VERIFIED'::backup_status
            ELSE 'FAILED'::backup_status
        END,
        verified_at = CASE
            WHEN v_passed THEN NOW()
            ELSE verified_at
        END
    WHERE backup_id = p_backup_id
      AND status = 'CREATED';

    IF NOT v_passed THEN
        RAISE WARNING 'Backup integrity verification failed: %',
            p_backup_id;
    END IF;
END;
$$;

-- ============================================================
-- 17. RECOVERY ELIGIBILITY VIEW
-- ============================================================

CREATE OR REPLACE VIEW recovery_eligibility_report AS
SELECT
    i.incident_id,
    i.incident_title,
    i.system_id,
    i.severity,
    i.occurred_at,

    b.backup_id,
    b.backup_name,
    b.backup_kind,
    b.data_timestamp,

    p.rpo_minutes,
    p.rto_minutes,

    ROUND(
        (
            EXTRACT(EPOCH FROM (
                i.occurred_at - b.data_timestamp
            )) / 60
        )::NUMERIC,
        2
    ) AS actual_rpo_minutes,

    COUNT(DISTINCT a.approval_id) AS approval_count,

    (
        b.status = 'VERIFIED'
        AND b.data_timestamp <= i.occurred_at
        AND (
            NOT p.require_offsite
            OR s.storage_type <> 'LOCAL'
        )
        AND (
            EXTRACT(EPOCH FROM (
                i.occurred_at - b.data_timestamp
            )) / 60
        ) <= p.rpo_minutes
    ) AS rpo_eligible

FROM disaster_incidents i

JOIN recovery_policies p
  ON p.system_id = i.system_id
 AND p.active = TRUE

JOIN backups b
  ON b.system_id = i.system_id

JOIN backup_storage s
  ON s.storage_id = b.storage_id

LEFT JOIN recovery_approvals a
  ON a.incident_id = i.incident_id
 AND a.decision = TRUE

GROUP BY
    i.incident_id,
    i.incident_title,
    i.system_id,
    i.severity,
    i.occurred_at,
    b.backup_id,
    b.backup_name,
    b.backup_kind,
    b.data_timestamp,
    b.status,
    p.rpo_minutes,
    p.rto_minutes,
    p.require_offsite,
    s.storage_type;

-- ============================================================
-- 18. RECOVERY PERFORMANCE REPORT
-- ============================================================

CREATE OR REPLACE VIEW recovery_performance_report AS
SELECT
    ps.system_name,
    rp.policy_name,

    COUNT(ro.recovery_id) AS total_recoveries,

    COUNT(*) FILTER (
        WHERE ro.status = 'SUCCESS'
    ) AS successful_recoveries,

    ROUND(
        AVG(ro.actual_rpo_minutes)
            FILTER (WHERE ro.status = 'SUCCESS'),
        2
    ) AS average_actual_rpo_minutes,

    ROUND(
        AVG(ro.actual_rto_minutes)
            FILTER (WHERE ro.status = 'SUCCESS'),
        2
    ) AS average_actual_rto_minutes,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE ro.status = 'SUCCESS'
              AND ro.rpo_met = TRUE
        ) / NULLIF(
            COUNT(*) FILTER (
                WHERE ro.status = 'SUCCESS'
            ),
            0
        ),
        2
    ) AS rpo_compliance_percent,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE ro.status = 'SUCCESS'
              AND ro.rto_met = TRUE
        ) / NULLIF(
            COUNT(*) FILTER (
                WHERE ro.status = 'SUCCESS'
            ),
            0
        ),
        2
    ) AS rto_compliance_percent

FROM protected_systems ps

JOIN recovery_policies rp
  ON rp.system_id = ps.system_id

LEFT JOIN disaster_incidents i
  ON i.system_id = ps.system_id

LEFT JOIN recovery_operations ro
  ON ro.incident_id = i.incident_id

GROUP BY
    ps.system_name,
    rp.policy_name;

-- ============================================================
-- 19. SAMPLE BUSINESS DATA
-- ============================================================

INSERT INTO protected_systems (
    system_name,
    business_owner,
    criticality,
    data_classification
)
VALUES
(
    'Banking Production Database',
    'Chief Technology Officer',
    'CRITICAL',
    'RESTRICTED'
),
(
    'Customer Analytics Platform',
    'Head of Data Analytics',
    'HIGH',
    'CONFIDENTIAL'
),
(
    'Internal Document Repository',
    'IT Operations',
    'MEDIUM',
    'INTERNAL'
);

INSERT INTO recovery_policies (
    system_id,
    policy_name,
    rpo_minutes,
    rto_minutes,
    retention_days,
    require_offsite,
    require_integrity_check,
    minimum_approvals,
    allow_point_in_time_recovery
)
SELECT
    system_id,
    CASE system_name
        WHEN 'Banking Production Database'
            THEN 'Critical Banking Policy'
        WHEN 'Customer Analytics Platform'
            THEN 'Analytics Recovery Policy'
        ELSE 'Internal Repository Policy'
    END,
    CASE system_name
        WHEN 'Banking Production Database' THEN 15
        WHEN 'Customer Analytics Platform' THEN 60
        ELSE 1440
    END,
    CASE system_name
        WHEN 'Banking Production Database' THEN 30
        WHEN 'Customer Analytics Platform' THEN 120
        ELSE 480
    END,
    CASE system_name
        WHEN 'Banking Production Database' THEN 90
        ELSE 30
    END,
    TRUE,
    TRUE,
    2,
    TRUE
FROM protected_systems;

INSERT INTO backup_storage (
    storage_name,
    storage_type,
    region,
    encrypted,
    immutable
)
VALUES
(
    'Primary Data Center',
    'LOCAL',
    'Mumbai',
    TRUE,
    FALSE
),
(
    'Offsite Disaster Recovery Center',
    'OFFSITE',
    'Hyderabad',
    TRUE,
    FALSE
),
(
    'Immutable Backup Vault',
    'IMMUTABLE',
    'Delhi',
    TRUE,
    TRUE
),
(
    'Cloud Archive',
    'CLOUD',
    'India',
    TRUE,
    FALSE
);

INSERT INTO recovery_personnel (
    personnel_name,
    email,
    role_name
)
VALUES
(
    'Operations Manager',
    'operations@example.com',
    'OPERATIONS_MANAGER'
),
(
    'Security Manager',
    'security@example.com',
    'SECURITY_MANAGER'
),
(
    'Database Administrator',
    'dba@example.com',
    'DATABASE_ADMIN'
),
(
    'Disaster Recovery Manager',
    'drmanager@example.com',
    'DR_MANAGER'
),
(
    'Internal Auditor',
    'audit@example.com',
    'AUDITOR'
);

-- ============================================================
-- 20. SAMPLE BACKUPS
-- ============================================================

INSERT INTO backups (
    system_id,
    storage_id,
    backup_name,
    backup_kind,
    data_timestamp,
    size_bytes,
    checksum_sha256,
    encrypted,
    expires_at
)
SELECT
    ps.system_id,
    st.storage_id,
    'Banking Full Backup',
    'FULL',
    NOW() - INTERVAL '20 minutes',
    500000000,
    repeat('a', 64),
    TRUE,
    NOW() + INTERVAL '90 days'
FROM protected_systems ps
JOIN backup_storage st
  ON st.storage_type = 'IMMUTABLE'
WHERE ps.system_name = 'Banking Production Database';

UPDATE backups
SET
    status = 'VERIFIED',
    verified_at = NOW()
WHERE backup_name = 'Banking Full Backup';

INSERT INTO backups (
    system_id,
    storage_id,
    parent_backup_id,
    backup_name,
    backup_kind,
    data_timestamp,
    size_bytes,
    checksum_sha256,
    encrypted,
    expires_at
)
SELECT
    b.system_id,
    b.storage_id,
    b.backup_id,
    'Banking Incremental Backup',
    'INCREMENTAL',
    NOW() - INTERVAL '5 minutes',
    50000000,
    repeat('b', 64),
    TRUE,
    NOW() + INTERVAL '90 days'
FROM backups b
WHERE b.backup_name = 'Banking Full Backup';

UPDATE backups
SET
    status = 'VERIFIED',
    verified_at = NOW()
WHERE backup_name = 'Banking Incremental Backup';

-- Sample backup that is deliberately unverified.
INSERT INTO backups (
    system_id,
    storage_id,
    backup_name,
    backup_kind,
    data_timestamp,
    size_bytes,
    checksum_sha256,
    encrypted
)
SELECT
    ps.system_id,
    st.storage_id,
    'Unverified Banking Backup',
    'FULL',
    NOW() - INTERVAL '2 minutes',
    10000000,
    repeat('c', 64),
    TRUE
FROM protected_systems ps
JOIN backup_storage st
  ON st.storage_type = 'OFFSITE'
WHERE ps.system_name = 'Banking Production Database';

-- ============================================================
-- 21. SAMPLE INCIDENT
-- ============================================================

INSERT INTO disaster_incidents (
    system_id,
    incident_title,
    description,
    severity,
    status,
    occurred_at,
    detected_at
)
SELECT
    system_id,
    'Primary database storage failure',
    'Primary production database storage became unavailable.',
    'CRITICAL',
    'OPEN',
    NOW() - INTERVAL '1 minute',
    NOW()
FROM protected_systems
WHERE system_name = 'Banking Production Database';

-- ============================================================
-- 22. SAMPLE RECOVERY APPROVALS
-- ============================================================

INSERT INTO recovery_approvals (
    incident_id,
    personnel_id,
    decision,
    comments
)
SELECT
    i.incident_id,
    p.personnel_id,
    TRUE,
    'Authorized emergency restoration'
FROM disaster_incidents i
CROSS JOIN recovery_personnel p
WHERE i.incident_title =
    'Primary database storage failure'
  AND p.role_name IN (
      'OPERATIONS_MANAGER',
      'SECURITY_MANAGER'
  );

-- ============================================================
-- 23. RETRIEVAL QUERIES
-- ============================================================

-- All backups for a protected system.
SELECT
    b.backup_id,
    b.backup_name,
    b.backup_kind,
    b.status,
    b.data_timestamp,
    b.size_bytes,
    s.storage_name,
    s.storage_type
FROM backups b
JOIN protected_systems ps
  ON ps.system_id = b.system_id
JOIN backup_storage s
  ON s.storage_id = b.storage_id
WHERE ps.system_name = 'Banking Production Database'
ORDER BY b.data_timestamp DESC;

-- Active recovery policies.
SELECT
    ps.system_name,
    rp.policy_name,
    rp.rpo_minutes,
    rp.rto_minutes,
    rp.retention_days
FROM protected_systems ps
JOIN recovery_policies rp
  ON rp.system_id = ps.system_id
WHERE rp.active = TRUE;

-- ============================================================
-- 24. VALIDATION QUERIES
-- ============================================================

-- Identify backups that have not been verified.
SELECT
    backup_id,
    backup_name,
    status,
    created_at
FROM backups
WHERE status <> 'VERIFIED';

-- Identify policy violations involving local-only backups.
SELECT
    b.backup_id,
    b.backup_name,
    ps.system_name
FROM backups b
JOIN protected_systems ps
  ON ps.system_id = b.system_id
JOIN recovery_policies rp
  ON rp.system_id = ps.system_id
JOIN backup_storage st
  ON st.storage_id = b.storage_id
WHERE rp.require_offsite = TRUE
  AND st.storage_type = 'LOCAL';

-- ============================================================
-- 25. ELIGIBILITY EVALUATION
-- ============================================================

SELECT *
FROM recovery_eligibility_report
ORDER BY incident_id, actual_rpo_minutes;

-- ============================================================
-- 26. RECOVERY EXECUTION
-- ============================================================

/*
 * The procedure models governance and records an operation.
 * It does not copy real database files or restore application
 * infrastructure. Such actions require an infrastructure adapter.
 *
 * Execute the sample operation inside its own transaction.
 */

DO $$
DECLARE
    v_incident BIGINT;
    v_backup BIGINT;
    v_personnel BIGINT;
BEGIN
    SELECT incident_id
    INTO v_incident
    FROM disaster_incidents
    WHERE incident_title =
        'Primary database storage failure';

    SELECT backup_id
    INTO v_backup
    FROM backups
    WHERE backup_name = 'Banking Incremental Backup';

    SELECT personnel_id
    INTO v_personnel
    FROM recovery_personnel
    WHERE role_name = 'DR_MANAGER';

    CALL execute_recovery(
        v_incident,
        v_backup,
        v_personnel,
        'RESTORE'
    );
END;
$$;

-- ============================================================
-- 27. REPORTING AND AGGREGATION
-- ============================================================

SELECT *
FROM recovery_performance_report;

-- Backup volume by system and storage class.
SELECT
    ps.system_name,
    st.storage_type,
    COUNT(*) AS backup_count,
    SUM(b.size_bytes) AS total_bytes,
    ROUND(
        SUM(b.size_bytes)::NUMERIC / 1024 / 1024,
        2
    ) AS total_megabytes
FROM backups b
JOIN protected_systems ps
  ON ps.system_id = b.system_id
JOIN backup_storage st
  ON st.storage_id = b.storage_id
GROUP BY
    ps.system_name,
    st.storage_type
ORDER BY
    ps.system_name,
    st.storage_type;

-- RPO and RTO violations.
SELECT
    i.incident_title,
    ps.system_name,
    ro.actual_rpo_minutes,
    rp.rpo_minutes AS target_rpo_minutes,
    ro.actual_rto_minutes,
    rp.rto_minutes AS target_rto_minutes,
    ro.rpo_met,
    ro.rto_met
FROM recovery_operations ro
JOIN disaster_incidents i
  ON i.incident_id = ro.incident_id
JOIN protected_systems ps
  ON ps.system_id = i.system_id
JOIN recovery_policies rp
  ON rp.system_id = ps.system_id
WHERE ro.status = 'SUCCESS'
  AND (
      ro.rpo_met = FALSE
      OR ro.rto_met = FALSE
  );

-- ============================================================
-- 28. BACKUP RETENTION PROCESSING
-- ============================================================

/*
 * Delete only expired backup records that are not referenced
 * as parents by retained dependent backups.
 *
 * Physical object deletion must be coordinated with storage
 * lifecycle policies and an audited deletion workflow.
 */

WITH RECURSIVE retained_backup_chain AS (
    SELECT backup_id
    FROM backups
    WHERE expires_at IS NULL
       OR expires_at >= NOW()

    UNION

    SELECT b.parent_backup_id
    FROM backups b
    JOIN retained_backup_chain r
      ON r.backup_id = b.backup_id
    WHERE b.parent_backup_id IS NOT NULL
),
deletion_candidates AS (
    SELECT b.backup_id
    FROM backups b
    WHERE b.expires_at < NOW()
      AND NOT EXISTS (
          SELECT 1
          FROM retained_backup_chain r
          WHERE r.backup_id = b.backup_id
      )
)
SELECT
    backup_id AS eligible_for_retention_deletion
FROM deletion_candidates;

-- ============================================================
-- 29. TRANSACTIONAL RECOVERY AUDIT
-- ============================================================

/*
 * Demonstrate transaction isolation and rollback safety.
 * This transaction intentionally performs no recovery.
 */

SAVEPOINT before_audit_check;

SELECT
    COUNT(*) AS open_incidents
FROM disaster_incidents
WHERE status = 'OPEN';

SELECT
    COUNT(*) AS failed_backups
FROM backups
WHERE status = 'FAILED';

ROLLBACK TO SAVEPOINT before_audit_check;

-- ============================================================
-- 30. FINAL OPERATIONAL INVENTORY
-- ============================================================

SELECT
    ps.system_name,
    ps.criticality,
    rp.rpo_minutes,
    rp.rto_minutes,
    COUNT(b.backup_id) AS total_backups,
    COUNT(b.backup_id) FILTER (
        WHERE b.status IN ('VERIFIED', 'RESTORED')
    ) AS usable_backups,
    COUNT(b.backup_id) FILTER (
        WHERE b.status = 'FAILED'
    ) AS failed_backups
FROM protected_systems ps
JOIN recovery_policies rp
  ON rp.system_id = ps.system_id
LEFT JOIN backups b
  ON b.system_id = ps.system_id
GROUP BY
    ps.system_id,
    ps.system_name,
    ps.criticality,
    rp.rpo_minutes,
    rp.rto_minutes
ORDER BY
    CASE ps.criticality
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END;

COMMIT;
