/*
===============================================================================
MULTI-REGION ARCHITECTURE
Regional Failover and Geographic Redundancy
PostgreSQL 15+

Implements:
- Regional infrastructure inventory
- Geographic deployment
- Primary and standby assignments
- Service deployments
- Regional health monitoring
- Replication relationships
- Replication lag and RPO validation
- Failover policies
- Approval and promotion workflow
- Failover audit history
- Recovery and failback
- Operational reporting

Important:
This database models and coordinates a regional failover workflow.
It does not itself replicate application databases or provide
distributed leader fencing across independent database clusters.
===============================================================================
*/

DROP SCHEMA IF EXISTS multi_region CASCADE;

CREATE SCHEMA multi_region;

SET search_path TO multi_region, public;


/* ============================================================================
   1. DOMAIN TYPES
============================================================================ */

CREATE TYPE region_state AS ENUM (
    'healthy',
    'degraded',
    'unavailable',
    'recovering'
);

CREATE TYPE deployment_role AS ENUM (
    'primary',
    'standby',
    'disabled'
);

CREATE TYPE failover_status AS ENUM (
    'requested',
    'approved',
    'rejected',
    'completed',
    'failed'
);

CREATE TYPE replication_mode AS ENUM (
    'synchronous',
    'asynchronous'
);


/* ============================================================================
   2. REGIONAL INFRASTRUCTURE
============================================================================ */

CREATE TABLE regions (
    region_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    region_code VARCHAR(30) NOT NULL UNIQUE,

    region_name VARCHAR(100) NOT NULL,

    geographic_area VARCHAR(100) NOT NULL,

    country_code CHAR(2) NOT NULL,

    availability_zone_count INTEGER NOT NULL DEFAULT 3,

    state region_state NOT NULL DEFAULT 'healthy',

    capacity_units INTEGER NOT NULL DEFAULT 1000,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_region_code
        CHECK (region_code ~ '^[a-z0-9-]+$'),

    CONSTRAINT positive_zone_count
        CHECK (availability_zone_count > 0),

    CONSTRAINT positive_capacity
        CHECK (capacity_units > 0)
);


/* ============================================================================
   3. APPLICATION SERVICES
============================================================================ */

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_name VARCHAR(100) NOT NULL UNIQUE,

    architecture VARCHAR(30) NOT NULL DEFAULT 'active-passive',

    rpo_seconds NUMERIC(12,3) NOT NULL DEFAULT 5,

    rto_seconds NUMERIC(12,3) NOT NULL DEFAULT 120,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_architecture
        CHECK (
            architecture IN (
                'active-active',
                'active-passive'
            )
        ),

    CONSTRAINT nonnegative_rpo
        CHECK (rpo_seconds >= 0),

    CONSTRAINT positive_rto
        CHECK (rto_seconds > 0)
);


/* ============================================================================
   4. REGIONAL SERVICE DEPLOYMENTS
============================================================================ */

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id),

    region_id BIGINT NOT NULL
        REFERENCES regions(region_id),

    role deployment_role NOT NULL DEFAULT 'standby',

    application_version VARCHAR(50) NOT NULL,

    active_load INTEGER NOT NULL DEFAULT 0,

    deployment_capacity INTEGER NOT NULL DEFAULT 1000,

    data_version BIGINT NOT NULL DEFAULT 0,

    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_service_region
        UNIQUE(service_id, region_id),

    CONSTRAINT valid_load
        CHECK (
            active_load >= 0
            AND deployment_capacity > 0
            AND active_load <= deployment_capacity
        ),

    CONSTRAINT nonnegative_data_version
        CHECK (data_version >= 0)
);


/*
A partial unique index ensures that an active-passive service
cannot have multiple primary deployments.

Active-active services require a different coordination model.
*/

CREATE UNIQUE INDEX one_primary_per_service
ON deployments(service_id)
WHERE role = 'primary';


CREATE INDEX deployments_region_role_idx
ON deployments(region_id, role);


CREATE INDEX deployments_service_region_idx
ON deployments(service_id, region_id);


/* ============================================================================
   5. REGIONAL HEALTH MONITORING
============================================================================ */

CREATE TABLE regional_health (
    health_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),

    state region_state NOT NULL,

    latency_ms NUMERIC(12,3) NOT NULL,

    error_rate NUMERIC(8,5) NOT NULL DEFAULT 0,

    cpu_utilization NUMERIC(6,3) NOT NULL DEFAULT 0,

    memory_utilization NUMERIC(6,3) NOT NULL DEFAULT 0,

    observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT nonnegative_latency
        CHECK (latency_ms >= 0),

    CONSTRAINT valid_error_rate
        CHECK (error_rate BETWEEN 0 AND 1),

    CONSTRAINT valid_cpu
        CHECK (cpu_utilization BETWEEN 0 AND 100),

    CONSTRAINT valid_memory
        CHECK (memory_utilization BETWEEN 0 AND 100)
);


CREATE INDEX regional_health_latest_idx
ON regional_health(deployment_id, observed_at DESC);


/* ============================================================================
   6. REPLICATION RELATIONSHIPS
============================================================================ */

CREATE TABLE replication_links (
    replication_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id),

    source_deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),

    target_deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),

    mode replication_mode NOT NULL DEFAULT 'asynchronous',

    lag_seconds NUMERIC(12,3) NOT NULL DEFAULT 0,

    last_replicated_version BIGINT NOT NULL DEFAULT 0,

    last_replicated_at TIMESTAMPTZ,

    replication_healthy BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT unique_replication_pair
        UNIQUE(source_deployment_id, target_deployment_id),

    CONSTRAINT distinct_replication_endpoints
        CHECK (
            source_deployment_id <> target_deployment_id
        ),

    CONSTRAINT valid_replication_lag
        CHECK (lag_seconds >= 0),

    CONSTRAINT valid_replicated_version
        CHECK (last_replicated_version >= 0)
);


CREATE INDEX replication_target_idx
ON replication_links(service_id, target_deployment_id);


/* ============================================================================
   7. FAILOVER POLICIES
============================================================================ */

CREATE TABLE failover_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL UNIQUE
        REFERENCES services(service_id),

    maximum_replication_lag NUMERIC(12,3) NOT NULL,

    maximum_latency_ms NUMERIC(12,3) NOT NULL,

    minimum_free_capacity NUMERIC(6,3) NOT NULL DEFAULT 20,

    require_healthy_region BOOLEAN NOT NULL DEFAULT TRUE,

    require_synchronized_replica BOOLEAN NOT NULL DEFAULT TRUE,

    automatic_failover_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    prevent_automatic_failback BOOLEAN NOT NULL DEFAULT TRUE,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_policy_lag
        CHECK (maximum_replication_lag >= 0),

    CONSTRAINT valid_policy_latency
        CHECK (maximum_latency_ms > 0),

    CONSTRAINT valid_free_capacity
        CHECK (
            minimum_free_capacity BETWEEN 0 AND 100
        )
);


/* ============================================================================
   8. FAILOVER REQUESTS AND AUDIT HISTORY
============================================================================ */

CREATE TABLE failover_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    service_id BIGINT NOT NULL
        REFERENCES services(service_id),

    source_deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),

    target_deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id),

    status failover_status NOT NULL DEFAULT 'requested',

    reason TEXT NOT NULL,

    rpo_seconds NUMERIC(12,3) NOT NULL DEFAULT 0,

    estimated_rto_seconds NUMERIC(12,3) NOT NULL DEFAULT 0,

    leader_epoch BIGINT NOT NULL DEFAULT 1,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    CONSTRAINT different_failover_endpoints
        CHECK (
            source_deployment_id <> target_deployment_id
        ),

    CONSTRAINT nonnegative_event_rpo
        CHECK (rpo_seconds >= 0),

    CONSTRAINT nonnegative_event_rto
        CHECK (estimated_rto_seconds >= 0),

    CONSTRAINT positive_leader_epoch
        CHECK (leader_epoch > 0)
);


CREATE INDEX failover_history_idx
ON failover_events(service_id, requested_at DESC);


/* ============================================================================
   9. DEPLOYMENT UPDATED_AT TRIGGER
============================================================================ */

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


CREATE TRIGGER deployments_timestamp_trigger
BEFORE UPDATE ON deployments
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();


CREATE TRIGGER policy_timestamp_trigger
BEFORE UPDATE ON failover_policies
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();


/* ============================================================================
   10. REGIONAL ELIGIBILITY FUNCTION
============================================================================ */

CREATE OR REPLACE FUNCTION evaluate_region_eligibility(
    p_service_id BIGINT,
    p_target_deployment_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    explanation TEXT,
    replication_lag NUMERIC,
    regional_latency NUMERIC,
    available_capacity NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_policy failover_policies%ROWTYPE;

    v_service services%ROWTYPE;

    v_target deployments%ROWTYPE;

    v_health regional_health%ROWTYPE;

    v_replication replication_links%ROWTYPE;

    v_free_capacity NUMERIC;

BEGIN

    SELECT *
    INTO v_policy
    FROM failover_policies
    WHERE service_id = p_service_id;

    IF NOT FOUND THEN

        RETURN QUERY
        SELECT FALSE,
               'Failover policy does not exist.'::TEXT,
               NULL::NUMERIC,
               NULL::NUMERIC,
               NULL::NUMERIC;

        RETURN;
    END IF;


    SELECT *
    INTO v_service
    FROM services
    WHERE service_id = p_service_id;

    SELECT *
    INTO v_target
    FROM deployments
    WHERE deployment_id = p_target_deployment_id
      AND service_id = p_service_id;

    IF NOT FOUND THEN

        RETURN QUERY
        SELECT FALSE,
               'Target deployment does not belong to service.'::TEXT,
               NULL::NUMERIC,
               NULL::NUMERIC,
               NULL::NUMERIC;

        RETURN;
    END IF;


    SELECT *
    INTO v_health
    FROM regional_health
    WHERE deployment_id = p_target_deployment_id
    ORDER BY observed_at DESC
    LIMIT 1;

    IF NOT FOUND THEN

        RETURN QUERY
        SELECT FALSE,
               'No health observation available.'::TEXT,
               NULL::NUMERIC,
               NULL::NUMERIC,
               NULL::NUMERIC;

        RETURN;
    END IF;


    SELECT *
    INTO v_replication
    FROM replication_links
    WHERE service_id = p_service_id
      AND target_deployment_id = p_target_deployment_id
      AND source_deployment_id = (
          SELECT deployment_id
          FROM deployments
          WHERE service_id = p_service_id
            AND role = 'primary'
      )
    ORDER BY lag_seconds
    LIMIT 1;

    IF NOT FOUND THEN

        RETURN QUERY
        SELECT FALSE,
               'No replication relationship from current primary.'::TEXT,
               NULL::NUMERIC,
               v_health.latency_ms,
               NULL::NUMERIC;

        RETURN;
    END IF;


    v_free_capacity :=
        (
            v_target.deployment_capacity -
            v_target.active_load
        )::NUMERIC
        / v_target.deployment_capacity * 100;


    IF v_service.architecture = 'active-passive'
       AND v_target.role <> 'standby' THEN

        RETURN QUERY
        SELECT FALSE,
               'Active-passive target must be standby.'::TEXT,
               v_replication.lag_seconds,
               v_health.latency_ms,
               v_free_capacity;

        RETURN;
    END IF;


    IF v_policy.require_healthy_region
       AND (
           v_health.state <> 'healthy'
           OR v_health.observed_at <
              CURRENT_TIMESTAMP - INTERVAL '2 minutes'
       ) THEN

        RETURN QUERY
        SELECT FALSE,
               'Target health is unhealthy or stale.'::TEXT,
               v_replication.lag_seconds,
               v_health.latency_ms,
               v_free_capacity;

        RETURN;
    END IF;


    IF NOT v_replication.replication_healthy THEN

        RETURN QUERY
        SELECT FALSE,
               'Replication process is unhealthy.'::TEXT,
               v_replication.lag_seconds,
               v_health.latency_ms,
               v_free_capacity;

        RETURN;
    END IF;


    IF v_policy.require_synchronized_replica
       AND v_replication.last_replicated_version
           < (
               SELECT data_version
               FROM deployments
               WHERE deployment_id =
                     v_replication.source_deployment_id
           ) THEN

        RETURN QUERY
        SELECT FALSE,
               'Replica has not received the latest data version.'::TEXT,
               v_replication.lag_seconds,
               v_health.latency_ms,
               v_free_capacity;

        RETURN;
    END IF;


    IF v_replication.lag_seconds >
       v_policy.maximum_replication_lag THEN

        RETURN QUERY
        SELECT FALSE,
               'Replication lag exceeds RPO policy.'::TEXT,
               v_replication.lag_seconds,
               v_health.latency_ms,
               v_free_capacity;

        RETURN;
    END IF;


    IF v_health.latency_ms >
       v_policy.maximum_latency_ms THEN

        RETURN QUERY
        SELECT FALSE,
               'Regional latency exceeds policy.'::TEXT,
               v_replication.lag_seconds,
               v_health.latency_ms,
               v_free_capacity;

        RETURN;
    END IF;


    IF v_free_capacity < v_policy.minimum_free_capacity THEN

        RETURN QUERY
        SELECT FALSE,
               'Insufficient regional capacity.'::TEXT,
               v_replication.lag_seconds,
               v_health.latency_ms,
               v_free_capacity;

        RETURN;
    END IF;


    RETURN QUERY
    SELECT TRUE,
           'Target satisfies all failover policies.'::TEXT,
           v_replication.lag_seconds,
           v_health.latency_ms,
           v_free_capacity;

END;
$$;


/* ============================================================================
   11. FAILOVER PROCESSING PROCEDURE
============================================================================ */

CREATE OR REPLACE PROCEDURE execute_failover(
    p_service_id BIGINT,
    p_target_deployment_id BIGINT,
    p_reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_source deployments%ROWTYPE;

    v_target deployments%ROWTYPE;

    v_result RECORD;

    v_epoch BIGINT;

    v_event_id BIGINT;

BEGIN

    IF NULLIF(TRIM(p_reason), '') IS NULL THEN
        RAISE EXCEPTION 'Failover reason is required.';
    END IF;


    -- Serialize failover operations for the same service.
    PERFORM pg_advisory_xact_lock(p_service_id);


    SELECT *
    INTO v_source
    FROM deployments
    WHERE service_id = p_service_id
      AND role = 'primary'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No primary deployment found.';
    END IF;


    SELECT *
    INTO v_target
    FROM deployments
    WHERE deployment_id = p_target_deployment_id
      AND service_id = p_service_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target deployment not found.';
    END IF;


    IF v_source.deployment_id = v_target.deployment_id THEN
        RAISE EXCEPTION 'Source and target must differ.';
    END IF;


    SELECT *
    INTO v_result
    FROM evaluate_region_eligibility(
        p_service_id,
        p_target_deployment_id
    );


    IF NOT v_result.eligible THEN

        INSERT INTO failover_events (
            service_id,
            source_deployment_id,
            target_deployment_id,
            status,
            reason,
            rpo_seconds
        )
        VALUES (
            p_service_id,
            v_source.deployment_id,
            p_target_deployment_id,
            'rejected',
            v_result.explanation,
            COALESCE(v_result.replication_lag, 0)
        );

        RAISE EXCEPTION
            'Failover rejected: %',
            v_result.explanation;
    END IF;


    SELECT COALESCE(MAX(leader_epoch), 0) + 1
    INTO v_epoch
    FROM failover_events
    WHERE service_id = p_service_id;


    INSERT INTO failover_events (
        service_id,
        source_deployment_id,
        target_deployment_id,
        status,
        reason,
        rpo_seconds,
        estimated_rto_seconds,
        leader_epoch
    )
    VALUES (
        p_service_id,
        v_source.deployment_id,
        p_target_deployment_id,
        'approved',
        p_reason,
        COALESCE(v_result.replication_lag, 0),
        2,
        v_epoch
    )
    RETURNING event_id INTO v_event_id;


    -- The partial unique index requires removing the old primary
    -- designation before assigning the new primary designation.
    UPDATE deployments
    SET role = 'standby'
    WHERE deployment_id = v_source.deployment_id;


    UPDATE deployments
    SET role = 'primary'
    WHERE deployment_id = p_target_deployment_id;


    UPDATE failover_events
    SET status = 'completed',
        completed_at = CURRENT_TIMESTAMP
    WHERE event_id = v_event_id;

    RAISE NOTICE
        'Failover completed. Source %, target %, epoch %',
        v_source.region_id,
        v_target.region_id,
        v_epoch;

END;
$$;


/* ============================================================================
   12. OPERATIONAL VIEWS
============================================================================ */

CREATE OR REPLACE VIEW regional_deployment_status AS
SELECT
    s.service_name,
    s.architecture,
    r.region_code,
    r.region_name,
    r.geographic_area,
    r.country_code,
    r.state AS infrastructure_state,
    d.role,
    d.application_version,
    d.active_load,
    d.deployment_capacity,
    d.data_version,
    h.state AS latest_health_state,
    h.latency_ms,
    h.error_rate,
    h.observed_at AS health_observed_at

FROM deployments d

JOIN services s
    ON s.service_id = d.service_id

JOIN regions r
    ON r.region_id = d.region_id

LEFT JOIN LATERAL (
    SELECT *
    FROM regional_health rh
    WHERE rh.deployment_id = d.deployment_id
    ORDER BY rh.observed_at DESC
    LIMIT 1
) h ON TRUE;


CREATE OR REPLACE VIEW failover_candidate_report AS
SELECT
    s.service_name,
    d.deployment_id,
    r.region_code,
    r.geographic_area,
    d.role,
    d.data_version,
    h.state AS health_state,
    h.latency_ms,
    rl.lag_seconds,
    rl.replication_healthy,
    ROUND(
        (
            d.deployment_capacity - d.active_load
        )::NUMERIC / d.deployment_capacity * 100,
        2
    ) AS free_capacity_percentage

FROM deployments d

JOIN services s
    ON s.service_id = d.service_id

JOIN regions r
    ON r.region_id = d.region_id

LEFT JOIN LATERAL (
    SELECT *
    FROM regional_health rh
    WHERE rh.deployment_id = d.deployment_id
    ORDER BY rh.observed_at DESC
    LIMIT 1
) h ON TRUE

LEFT JOIN replication_links rl
    ON rl.target_deployment_id = d.deployment_id
   AND rl.service_id = d.service_id;


/* ============================================================================
   13. SAMPLE REGIONAL INFRASTRUCTURE
============================================================================ */

INSERT INTO regions (
    region_code,
    region_name,
    geographic_area,
    country_code,
    availability_zone_count,
    capacity_units
)
VALUES
(
    'ap-south-1',
    'Mumbai Primary',
    'South Asia',
    'IN',
    3,
    2000
),
(
    'ap-south-2',
    'Hyderabad Secondary',
    'South Asia',
    'IN',
    3,
    2000
),
(
    'eu-west-1',
    'Ireland Disaster Recovery',
    'Western Europe',
    'IE',
    3,
    2500
);


/* ============================================================================
   14. SAMPLE APPLICATION
============================================================================ */

INSERT INTO services (
    service_name,
    architecture,
    rpo_seconds,
    rto_seconds
)
VALUES (
    'payment-processing',
    'active-passive',
    5,
    120
);


INSERT INTO deployments (
    service_id,
    region_id,
    role,
    application_version,
    active_load,
    deployment_capacity,
    data_version
)
SELECT
    s.service_id,
    r.region_id,
    data.role::deployment_role,
    '3.2.0',
    data.active_load,
    data.capacity,
    100

FROM services s

CROSS JOIN (
    VALUES
        ('ap-south-1', 'primary', 500, 2000),
        ('ap-south-2', 'standby', 200, 2000),
        ('eu-west-1', 'standby', 250, 2500)
) AS data(region_code, role, active_load, capacity)

JOIN regions r
    ON r.region_code = data.region_code

WHERE s.service_name = 'payment-processing';


INSERT INTO failover_policies (
    service_id,
    maximum_replication_lag,
    maximum_latency_ms,
    minimum_free_capacity
)
SELECT
    service_id,
    5,
    250,
    20
FROM services
WHERE service_name = 'payment-processing';


/* ============================================================================
   15. SAMPLE HEALTH OBSERVATIONS
============================================================================ */

INSERT INTO regional_health (
    deployment_id,
    state,
    latency_ms,
    error_rate,
    cpu_utilization,
    memory_utilization
)
SELECT
    d.deployment_id,
    'healthy',
    CASE r.region_code
        WHEN 'ap-south-1' THEN 30
        WHEN 'ap-south-2' THEN 45
        ELSE 130
    END,
    0.001,
    45,
    55

FROM deployments d

JOIN regions r
    ON r.region_id = d.region_id;


/* ============================================================================
   16. SAMPLE REPLICATION LINKS
============================================================================ */

INSERT INTO replication_links (
    service_id,
    source_deployment_id,
    target_deployment_id,
    mode,
    lag_seconds,
    last_replicated_version,
    last_replicated_at,
    replication_healthy
)
SELECT
    primary_d.service_id,
    primary_d.deployment_id,
    standby_d.deployment_id,
    'asynchronous',
    CASE target_r.region_code
        WHEN 'ap-south-2' THEN 1
        ELSE 2
    END,
    100,
    CURRENT_TIMESTAMP,
    TRUE

FROM deployments primary_d

JOIN deployments standby_d
    ON standby_d.service_id = primary_d.service_id
   AND standby_d.role = 'standby'

JOIN regions target_r
    ON target_r.region_id = standby_d.region_id

WHERE primary_d.role = 'primary';


/* ============================================================================
   17. RETRIEVAL QUERIES
============================================================================ */

-- All regional deployments and current health information.

SELECT *
FROM regional_deployment_status
ORDER BY service_name, region_code;


-- Regional replication relationships.

SELECT
    s.service_name,
    source_r.region_code AS source_region,
    target_r.region_code AS target_region,
    rl.mode,
    rl.lag_seconds,
    rl.last_replicated_version,
    rl.replication_healthy

FROM replication_links rl

JOIN services s
    ON s.service_id = rl.service_id

JOIN deployments source_d
    ON source_d.deployment_id = rl.source_deployment_id

JOIN deployments target_d
    ON target_d.deployment_id = rl.target_deployment_id

JOIN regions source_r
    ON source_r.region_id = source_d.region_id

JOIN regions target_r
    ON target_r.region_id = target_d.region_id;


/* ============================================================================
   18. VALIDATION AND ELIGIBILITY QUERIES
============================================================================ */

-- Evaluate the Hyderabad standby.

SELECT
    d.deployment_id,
    r.region_code,
    e.*

FROM deployments d

JOIN regions r
    ON r.region_id = d.region_id

CROSS JOIN LATERAL evaluate_region_eligibility(
    d.service_id,
    d.deployment_id
) e

WHERE r.region_code = 'ap-south-2';


-- Identify deployments exceeding replication requirements.

SELECT
    s.service_name,
    target_r.region_code,
    rl.lag_seconds,
    s.rpo_seconds

FROM replication_links rl

JOIN services s
    ON s.service_id = rl.service_id

JOIN deployments target_d
    ON target_d.deployment_id = rl.target_deployment_id

JOIN regions target_r
    ON target_r.region_id = target_d.region_id

WHERE rl.lag_seconds > s.rpo_seconds;


/* ============================================================================
   19. AGGREGATION AND CAPACITY REPORTING
============================================================================ */

SELECT
    geographic_area,
    COUNT(*) AS regional_deployments,
    SUM(active_load) AS total_active_load,
    SUM(deployment_capacity) AS total_capacity,
    ROUND(
        SUM(active_load)::NUMERIC /
        NULLIF(SUM(deployment_capacity), 0) * 100,
        2
    ) AS utilization_percentage

FROM deployments d

JOIN regions r
    ON r.region_id = d.region_id

GROUP BY geographic_area

ORDER BY geographic_area;


/* ============================================================================
   20. REGIONAL HEALTH FAILURE SIMULATION
============================================================================ */

BEGIN;

-- Make the primary region unavailable.

UPDATE regions
SET state = 'unavailable'
WHERE region_code = 'ap-south-1';

UPDATE regional_health
SET state = 'unavailable',
    latency_ms = 1000,
    error_rate = 0.95
WHERE deployment_id = (
    SELECT deployment_id
    FROM deployments
    WHERE role = 'primary'
      AND service_id = (
          SELECT service_id
          FROM services
          WHERE service_name = 'payment-processing'
      )
);

COMMIT;


/* ============================================================================
   21. FAILOVER EXECUTION
============================================================================ */

-- The target must satisfy all policy and replication checks.
-- This transaction promotes Hyderabad.

BEGIN;

CALL execute_failover(
    (
        SELECT service_id
        FROM services
        WHERE service_name = 'payment-processing'
    ),
    (
        SELECT d.deployment_id
        FROM deployments d
        JOIN regions r
            ON r.region_id = d.region_id
        WHERE r.region_code = 'ap-south-2'
          AND d.service_id = (
              SELECT service_id
              FROM services
              WHERE service_name = 'payment-processing'
          )
    ),
    'Primary regional outage in Mumbai'
);

COMMIT;


/* ============================================================================
   22. POST-FAILOVER VALIDATION
============================================================================ */

SELECT
    s.service_name,
    r.region_code,
    d.role,
    d.data_version,
    r.state

FROM deployments d

JOIN services s
    ON s.service_id = d.service_id

JOIN regions r
    ON r.region_id = d.region_id

WHERE s.service_name = 'payment-processing'

ORDER BY d.role, r.region_code;


-- The current primary should be Hyderabad.

SELECT
    s.service_name,
    r.region_code,
    d.role

FROM deployments d

JOIN services s
    ON s.service_id = d.service_id

JOIN regions r
    ON r.region_id = d.region_id

WHERE d.role = 'primary';


/* ============================================================================
   23. RECOVERY AND REPLICATION SYNCHRONIZATION
============================================================================ */

BEGIN;

-- Restore Mumbai infrastructure health.

UPDATE regions
SET state = 'recovering'
WHERE region_code = 'ap-south-1';

UPDATE regional_health
SET state = 'recovering',
    latency_ms = 40,
    error_rate = 0.002
WHERE deployment_id = (
    SELECT deployment_id
    FROM deployments d
    JOIN regions r
        ON r.region_id = d.region_id
    WHERE r.region_code = 'ap-south-1'
);

-- Synchronize recovered deployment with current primary.

UPDATE deployments recovered
SET data_version = primary_d.data_version,
    active_load = 0

FROM deployments primary_d

JOIN regions primary_r
    ON primary_r.region_id = primary_d.region_id

JOIN regions recovered_r
    ON recovered_r.region_code = 'ap-south-1'

WHERE primary_d.service_id = recovered.service_id
  AND primary_d.role = 'primary'
  AND recovered.region_id = recovered_r.region_id;

UPDATE regions
SET state = 'healthy'
WHERE region_code = 'ap-south-1';

UPDATE regional_health
SET state = 'healthy',
    observed_at = CURRENT_TIMESTAMP
WHERE deployment_id = (
    SELECT d.deployment_id
    FROM deployments d
    JOIN regions r
        ON r.region_id = d.region_id
    WHERE r.region_code = 'ap-south-1'
);

-- Refresh the replication relationship to the recovered standby.

UPDATE replication_links rl
SET last_replicated_version = recovered.data_version,
    lag_seconds = 0,
    last_replicated_at = CURRENT_TIMESTAMP,
    replication_healthy = TRUE

FROM deployments recovered

JOIN regions recovered_r
    ON recovered_r.region_id = recovered.region_id

WHERE rl.target_deployment_id = recovered.deployment_id
  AND recovered_r.region_code = 'ap-south-1';

COMMIT;


/* ============================================================================
   24. CONTROLLED FAILBACK
============================================================================ */

-- Failback is a deliberate operation.
-- The recovered region must be a synchronized standby.

BEGIN;

CALL execute_failover(
    (
        SELECT service_id
        FROM services
        WHERE service_name = 'payment-processing'
    ),
    (
        SELECT d.deployment_id
        FROM deployments d
        JOIN regions r
            ON r.region_id = d.region_id
        WHERE r.region_code = 'ap-south-1'
          AND d.service_id = (
              SELECT service_id
              FROM services
              WHERE service_name = 'payment-processing'
          )
    ),
    'Controlled failback after disaster recovery'
);

COMMIT;


/* ============================================================================
   25. FAILOVER HISTORY REPORTING
============================================================================ */

SELECT
    e.event_id,
    s.service_name,
    source_r.region_code AS source_region,
    target_r.region_code AS target_region,
    e.status,
    e.reason,
    e.rpo_seconds,
    e.estimated_rto_seconds,
    e.leader_epoch,
    e.requested_at,
    e.completed_at

FROM failover_events e

JOIN services s
    ON s.service_id = e.service_id

JOIN deployments source_d
    ON source_d.deployment_id = e.source_deployment_id

JOIN deployments target_d
    ON target_d.deployment_id = e.target_deployment_id

JOIN regions source_r
    ON source_r.region_id = source_d.region_id

JOIN regions target_r
    ON target_r.region_id = target_d.region_id

ORDER BY e.requested_at DESC;


/* ============================================================================
   26. OPERATIONAL SUMMARY
============================================================================ */

SELECT
    s.service_name,

    COUNT(d.deployment_id) AS deployment_count,

    COUNT(*) FILTER (
        WHERE d.role = 'primary'
    ) AS primary_count,

    COUNT(*) FILTER (
        WHERE d.role = 'standby'
    ) AS standby_count,

    MAX(d.data_version) AS highest_data_version,

    COUNT(*) FILTER (
        WHERE r.state = 'unavailable'
    ) AS unavailable_regions

FROM services s

JOIN deployments d
    ON d.service_id = s.service_id

JOIN regions r
    ON r.region_id = d.region_id

GROUP BY s.service_name;


/*
===============================================================================
END OF MULTI-REGION ARCHITECTURE WORKFLOW

Operational boundaries:

1. Regional infrastructure status is not the same as application health.
2. Replication lag is not a guarantee of zero data loss.
3. Database transactions serialize operations within this database.
4. Cross-region leader fencing requires a distributed coordination system.
5. DNS and global traffic management require independent configuration.
6. RTO must be measured using actual recovery exercises.
7. Asynchronous replication can lose acknowledged writes during a failure.
8. Geographic redundancy must account for shared infrastructure failures.
===============================================================================
*/
