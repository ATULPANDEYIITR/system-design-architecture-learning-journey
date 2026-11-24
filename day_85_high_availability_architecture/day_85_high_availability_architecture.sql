-- ============================================================
-- HIGH AVAILABILITY ARCHITECTURE
-- Eliminating Single Points of Failure
--
-- PostgreSQL 15+
--
-- Models:
--   Infrastructure nodes
--   Independent failure domains
--   Services and replicas
--   Health monitoring
--   Replication groups
--   Quorum membership
--   Leader elections and fencing terms
--   Failover events
--   Availability policies
--   Service-level availability evaluation
--
-- This database is a governance and simulation model.
-- It does not itself implement distributed consensus,
-- synchronous replication, or automatic infrastructure fencing.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ha;

SET search_path TO ha, public;

-- ------------------------------------------------------------
-- ENUMERATIONS
-- ------------------------------------------------------------

CREATE TYPE node_status AS ENUM (
    'HEALTHY',
    'FAILED',
    'MAINTENANCE'
);

CREATE TYPE service_status AS ENUM (
    'AVAILABLE',
    'DEGRADED',
    'UNAVAILABLE'
);

CREATE TYPE replication_mode AS ENUM (
    'SYNCHRONOUS',
    'ASYNCHRONOUS'
);

CREATE TYPE failover_status AS ENUM (
    'DETECTED',
    'IN_PROGRESS',
    'COMPLETED',
    'FAILED'
);

CREATE TYPE failure_severity AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

-- ------------------------------------------------------------
-- FAILURE DOMAINS
-- ------------------------------------------------------------

CREATE TABLE failure_domains (
    domain_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain_name VARCHAR(100) NOT NULL UNIQUE,
    domain_type VARCHAR(30) NOT NULL
        CHECK (
            domain_type IN (
                'AVAILABILITY_ZONE',
                'REGION',
                'DATA_CENTER',
                'POWER_DOMAIN',
                'NETWORK_DOMAIN'
            )
        ),
    region_name VARCHAR(100) NOT NULL,
    operational BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- INFRASTRUCTURE NODES
-- ------------------------------------------------------------

CREATE TABLE infrastructure_nodes (
    node_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_name VARCHAR(100) NOT NULL UNIQUE,
    node_role VARCHAR(30) NOT NULL
        CHECK (
            node_role IN (
                'APPLICATION',
                'DATABASE',
                'CONTROL_PLANE',
                'LOAD_BALANCER',
                'CACHE',
                'STORAGE'
            )
        ),
    domain_id BIGINT NOT NULL
        REFERENCES failure_domains(domain_id),
    status node_status NOT NULL DEFAULT 'HEALTHY',
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    current_load INTEGER NOT NULL DEFAULT 0
        CHECK (current_load >= 0 AND current_load <= capacity),
    last_heartbeat TIMESTAMPTZ,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nodes_domain_status
    ON infrastructure_nodes(domain_id, status);

CREATE INDEX idx_nodes_role_status
    ON infrastructure_nodes(node_role, status);

-- ------------------------------------------------------------
-- SERVICES
-- ------------------------------------------------------------

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL UNIQUE,
    service_description TEXT,
    critical BOOLEAN NOT NULL DEFAULT TRUE,
    minimum_healthy_replicas INTEGER NOT NULL DEFAULT 1
        CHECK (minimum_healthy_replicas >= 1),
    require_multiple_domains BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- SERVICE REPLICAS
-- ------------------------------------------------------------

CREATE TABLE service_replicas (
    replica_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL
        REFERENCES services(service_id) ON DELETE CASCADE,
    node_id BIGINT NOT NULL
        REFERENCES infrastructure_nodes(node_id),
    replica_role VARCHAR(20) NOT NULL
        CHECK (
            replica_role IN (
                'ACTIVE',
                'STANDBY',
                'READ_REPLICA'
            )
        ),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(service_id, node_id)
);

CREATE INDEX idx_replicas_service
    ON service_replicas(service_id);

CREATE INDEX idx_replicas_node
    ON service_replicas(node_id);

-- Ensure minimum healthy replica count does not exceed
-- the number of registered replicas.
CREATE OR REPLACE FUNCTION validate_service_replica_policy()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_service BIGINT;
    required_count INTEGER;
    actual_count INTEGER;
BEGIN
    target_service := COALESCE(NEW.service_id, OLD.service_id);

    SELECT minimum_healthy_replicas
    INTO required_count
    FROM services
    WHERE service_id = target_service;

    SELECT COUNT(*)
    INTO actual_count
    FROM service_replicas
    WHERE service_id = target_service;

    IF actual_count < required_count THEN
        RAISE EXCEPTION
            'Service % requires at least % registered replicas',
            target_service,
            required_count;
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_validate_replica_policy
AFTER INSERT OR UPDATE OR DELETE ON service_replicas
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION validate_service_replica_policy();

-- ------------------------------------------------------------
-- DATABASE REPLICATION GROUPS
-- ------------------------------------------------------------

CREATE TABLE replication_groups (
    replication_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL UNIQUE,
    replication_method replication_mode NOT NULL,
    synchronous_commit_required BOOLEAN NOT NULL DEFAULT FALSE,
    maximum_replica_lag_ms INTEGER NOT NULL DEFAULT 1000
        CHECK (maximum_replica_lag_ms >= 0),
    minimum_acknowledgements INTEGER NOT NULL DEFAULT 1
        CHECK (minimum_acknowledgements >= 1)
);

CREATE TABLE database_replication_members (
    replication_member_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    replication_group_id BIGINT NOT NULL
        REFERENCES replication_groups(replication_group_id)
        ON DELETE CASCADE,
    node_id BIGINT NOT NULL
        REFERENCES infrastructure_nodes(node_id),
    replication_role VARCHAR(20) NOT NULL
        CHECK (
            replication_role IN (
                'PRIMARY',
                'REPLICA',
                'WITNESS'
            )
        ),
    replication_lag_ms INTEGER NOT NULL DEFAULT 0
        CHECK (replication_lag_ms >= 0),
    last_replayed_at TIMESTAMPTZ,
    UNIQUE(replication_group_id, node_id)
);

CREATE INDEX idx_replication_members_group
    ON database_replication_members(replication_group_id);

-- ------------------------------------------------------------
-- CONTROL-PLANE QUORUM
-- ------------------------------------------------------------

CREATE TABLE quorum_clusters (
    quorum_cluster_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_name VARCHAR(100) NOT NULL UNIQUE,
    required_majority INTEGER NOT NULL CHECK (required_majority >= 2),
    current_term BIGINT NOT NULL DEFAULT 0 CHECK (current_term >= 0),
    leader_node_id BIGINT
        REFERENCES infrastructure_nodes(node_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE quorum_members (
    quorum_member_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quorum_cluster_id BIGINT NOT NULL
        REFERENCES quorum_clusters(quorum_cluster_id)
        ON DELETE CASCADE,
    node_id BIGINT NOT NULL
        REFERENCES infrastructure_nodes(node_id),
    voting_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(quorum_cluster_id, node_id)
);

-- ------------------------------------------------------------
-- HEALTH CHECK HISTORY
-- ------------------------------------------------------------

CREATE TABLE health_checks (
    health_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id BIGINT NOT NULL
        REFERENCES infrastructure_nodes(node_id),
    check_passed BOOLEAN NOT NULL,
    response_time_ms INTEGER
        CHECK (response_time_ms IS NULL OR response_time_ms >= 0),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
);

CREATE INDEX idx_health_checks_node_time
    ON health_checks(node_id, checked_at DESC);

-- ------------------------------------------------------------
-- FAILOVER HISTORY
-- ------------------------------------------------------------

CREATE TABLE failover_events (
    failover_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT REFERENCES services(service_id),
    failed_node_id BIGINT REFERENCES infrastructure_nodes(node_id),
    replacement_node_id BIGINT REFERENCES infrastructure_nodes(node_id),
    status failover_status NOT NULL DEFAULT 'DETECTED',
    fencing_token BIGINT NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    CHECK (
        replacement_node_id IS NULL
        OR failed_node_id IS DISTINCT FROM replacement_node_id
    ),
    CHECK (
        completed_at IS NULL
        OR completed_at >= detected_at
    )
);

CREATE INDEX idx_failover_service_time
    ON failover_events(service_id, detected_at DESC);

-- ------------------------------------------------------------
-- AVAILABILITY INCIDENTS
-- ------------------------------------------------------------

CREATE TABLE infrastructure_incidents (
    incident_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain_id BIGINT REFERENCES failure_domains(domain_id),
    severity failure_severity NOT NULL,
    description TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ,
    CHECK (
        resolved_at IS NULL
        OR resolved_at >= opened_at
    )
);

-- ------------------------------------------------------------
-- VALIDATION TRIGGERS
-- ------------------------------------------------------------

-- Prevent assigning an unhealthy node as a new active replica.
CREATE OR REPLACE FUNCTION validate_active_replica()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    node_health node_status;
BEGIN
    IF NEW.replica_role = 'ACTIVE' THEN
        SELECT status
        INTO node_health
        FROM infrastructure_nodes
        WHERE node_id = NEW.node_id;

        IF node_health IS DISTINCT FROM 'HEALTHY'::node_status THEN
            RAISE EXCEPTION
                'An active replica must reference a healthy node';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_active_replica
BEFORE INSERT OR UPDATE ON service_replicas
FOR EACH ROW
EXECUTE FUNCTION validate_active_replica();

-- ------------------------------------------------------------
-- SERVICE AVAILABILITY VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW service_availability AS
SELECT
    s.service_id,
    s.service_name,
    s.minimum_healthy_replicas,
    COUNT(sr.replica_id) AS total_replicas,
    COUNT(sr.replica_id) FILTER (
        WHERE n.status = 'HEALTHY'
    ) AS healthy_replicas,
    COUNT(DISTINCT fd.domain_id) FILTER (
        WHERE n.status = 'HEALTHY'
    ) AS active_failure_domains,
    CASE
        WHEN COUNT(sr.replica_id) FILTER (
            WHERE n.status = 'HEALTHY'
        ) < s.minimum_healthy_replicas
        THEN 'UNAVAILABLE'

        WHEN s.require_multiple_domains
         AND COUNT(DISTINCT fd.domain_id) FILTER (
             WHERE n.status = 'HEALTHY'
         ) < 2
        THEN 'UNAVAILABLE'

        WHEN COUNT(sr.replica_id) FILTER (
            WHERE n.status = 'HEALTHY'
        ) < COUNT(sr.replica_id)
        THEN 'DEGRADED'

        ELSE 'AVAILABLE'
    END AS availability_status
FROM services s
LEFT JOIN service_replicas sr
    ON sr.service_id = s.service_id
LEFT JOIN infrastructure_nodes n
    ON n.node_id = sr.node_id
LEFT JOIN failure_domains fd
    ON fd.domain_id = n.domain_id
GROUP BY
    s.service_id,
    s.service_name,
    s.minimum_healthy_replicas,
    s.require_multiple_domains;

-- ------------------------------------------------------------
-- QUORUM EVALUATION VIEW
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW quorum_availability AS
SELECT
    qc.quorum_cluster_id,
    qc.cluster_name,
    qc.required_majority,
    qc.leader_node_id,
    COUNT(qm.quorum_member_id) FILTER (
        WHERE qm.voting_enabled
          AND n.status = 'HEALTHY'
    ) AS available_votes,
    COUNT(qm.quorum_member_id) FILTER (
        WHERE qm.voting_enabled
    ) AS total_voters,
    COUNT(qm.quorum_member_id) FILTER (
        WHERE qm.voting_enabled
          AND n.status = 'HEALTHY'
    ) >= qc.required_majority AS quorum_available
FROM quorum_clusters qc
LEFT JOIN quorum_members qm
    ON qm.quorum_cluster_id = qc.quorum_cluster_id
LEFT JOIN infrastructure_nodes n
    ON n.node_id = qm.node_id
GROUP BY
    qc.quorum_cluster_id,
    qc.cluster_name,
    qc.required_majority,
    qc.leader_node_id;

-- ------------------------------------------------------------
-- FAILURE-DOMAIN ANALYSIS
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW failure_domain_analysis AS
SELECT
    s.service_id,
    s.service_name,
    failed_domain.domain_id AS hypothetical_failed_domain,
    failed_domain.domain_name,
    s.minimum_healthy_replicas,
    COUNT(sr.replica_id) FILTER (
        WHERE actual_node.status = 'HEALTHY'
          AND actual_node.domain_id <> failed_domain.domain_id
    ) AS surviving_replicas,
    CASE
        WHEN COUNT(sr.replica_id) FILTER (
            WHERE actual_node.status = 'HEALTHY'
              AND actual_node.domain_id <> failed_domain.domain_id
        ) < s.minimum_healthy_replicas
        THEN TRUE
        ELSE FALSE
    END AS violates_availability_policy
FROM services s
JOIN service_replicas sr
    ON sr.service_id = s.service_id
JOIN infrastructure_nodes actual_node
    ON actual_node.node_id = sr.node_id
CROSS JOIN failure_domains failed_domain
GROUP BY
    s.service_id,
    s.service_name,
    failed_domain.domain_id,
    failed_domain.domain_name,
    s.minimum_healthy_replicas;

-- ------------------------------------------------------------
-- AVAILABILITY EVALUATION FUNCTION
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_service(
    p_service_id BIGINT
)
RETURNS TABLE (
    service_name VARCHAR,
    service_state TEXT,
    healthy_replicas BIGINT,
    required_replicas INTEGER
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM services
        WHERE service_id = p_service_id
    ) THEN
        RAISE EXCEPTION 'Unknown service ID: %', p_service_id;
    END IF;

    RETURN QUERY
    SELECT
        sa.service_name::VARCHAR,
        sa.availability_status::TEXT,
        sa.healthy_replicas,
        sa.minimum_healthy_replicas
    FROM service_availability sa
    WHERE sa.service_id = p_service_id;
END;
$$;

-- ------------------------------------------------------------
-- ATOMIC FAILOVER PROCEDURE
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE execute_failover(
    p_event_id BIGINT,
    p_replacement_node_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    event_record failover_events%ROWTYPE;
    replacement_status node_status;
    existing_replica BOOLEAN;
    service_requirement INTEGER;
    active_domains BIGINT;
BEGIN
    -- Serialize concurrent operations on the same failover event.
    SELECT *
    INTO event_record
    FROM failover_events
    WHERE failover_event_id = p_event_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown failover event';
    END IF;

    IF event_record.status = 'COMPLETED' THEN
        RAISE EXCEPTION 'Failover already completed';
    END IF;

    IF event_record.status = 'FAILED' THEN
        RAISE EXCEPTION 'Failed event cannot be reused';
    END IF;

    IF event_record.service_id IS NULL THEN
        RAISE EXCEPTION 'Service must be specified for failover';
    END IF;

    IF p_replacement_node_id = event_record.failed_node_id THEN
        RAISE EXCEPTION 'Replacement cannot be the failed node';
    END IF;

    SELECT status
    INTO replacement_status
    FROM infrastructure_nodes
    WHERE node_id = p_replacement_node_id
    FOR UPDATE;

    IF replacement_status IS DISTINCT FROM 'HEALTHY'::node_status THEN
        RAISE EXCEPTION 'Replacement node is not healthy';
    END IF;

    SELECT minimum_healthy_replicas
    INTO service_requirement
    FROM services
    WHERE service_id = event_record.service_id
    FOR UPDATE;

    SELECT EXISTS (
        SELECT 1
        FROM service_replicas
        WHERE service_id = event_record.service_id
          AND node_id = p_replacement_node_id
    )
    INTO existing_replica;

    IF existing_replica THEN
        RAISE EXCEPTION 'Replacement is already registered';
    END IF;

    SELECT COUNT(DISTINCT n.domain_id)
    INTO active_domains
    FROM service_replicas sr
    JOIN infrastructure_nodes n
        ON n.node_id = sr.node_id
    WHERE sr.service_id = event_record.service_id
      AND n.status = 'HEALTHY';

    -- Avoid creating a replacement in the same failure domain
    -- as the failed node when alternative domains are available.
    IF EXISTS (
        SELECT 1
        FROM infrastructure_nodes failed
        JOIN infrastructure_nodes replacement
          ON replacement.node_id = p_replacement_node_id
        WHERE failed.node_id = event_record.failed_node_id
          AND failed.domain_id = replacement.domain_id
    ) AND active_domains > 1 THEN
        RAISE EXCEPTION
            'Replacement must use an independent failure domain';
    END IF;

    UPDATE failover_events
    SET status = 'IN_PROGRESS'
    WHERE failover_event_id = p_event_id;

    INSERT INTO service_replicas (
        service_id,
        node_id,
        replica_role
    )
    VALUES (
        event_record.service_id,
        p_replacement_node_id,
        'ACTIVE'
    );

    UPDATE failover_events
    SET
        replacement_node_id = p_replacement_node_id,
        status = 'COMPLETED',
        fencing_token = fencing_token + 1,
        completed_at = CURRENT_TIMESTAMP
    WHERE failover_event_id = p_event_id;

    -- The caller controls the surrounding transaction.
    -- All operations commit or roll back together.
END;
$$;

-- ------------------------------------------------------------
-- SAMPLE FAILURE DOMAINS
-- ------------------------------------------------------------

INSERT INTO failure_domains (
    domain_name,
    domain_type,
    region_name
)
VALUES
    ('zone-a', 'AVAILABILITY_ZONE', 'india-central'),
    ('zone-b', 'AVAILABILITY_ZONE', 'india-central'),
    ('zone-c', 'AVAILABILITY_ZONE', 'india-central'),
    ('zone-d', 'AVAILABILITY_ZONE', 'india-west');

-- ------------------------------------------------------------
-- SAMPLE INFRASTRUCTURE
-- ------------------------------------------------------------

INSERT INTO infrastructure_nodes (
    node_name,
    node_role,
    domain_id,
    status,
    capacity
)
SELECT
    data.node_name,
    data.node_role,
    fd.domain_id,
    data.status::node_status,
    data.capacity
FROM (
    VALUES
        ('app-1', 'APPLICATION', 'zone-a', 'HEALTHY', 100),
        ('app-2', 'APPLICATION', 'zone-b', 'HEALTHY', 100),
        ('app-3', 'APPLICATION', 'zone-c', 'HEALTHY', 100),
        ('app-4', 'APPLICATION', 'zone-d', 'HEALTHY', 100),

        ('db-1', 'DATABASE', 'zone-a', 'HEALTHY', 200),
        ('db-2', 'DATABASE', 'zone-b', 'HEALTHY', 200),
        ('db-3', 'DATABASE', 'zone-c', 'HEALTHY', 200),

        ('control-1', 'CONTROL_PLANE', 'zone-a', 'HEALTHY', 50),
        ('control-2', 'CONTROL_PLANE', 'zone-b', 'HEALTHY', 50),
        ('control-3', 'CONTROL_PLANE', 'zone-c', 'HEALTHY', 50),

        ('app-maintenance', 'APPLICATION', 'zone-d', 'MAINTENANCE', 100)
) AS data(node_name, node_role, domain_name, status, capacity)
JOIN failure_domains fd
    ON fd.domain_name = data.domain_name;

-- ------------------------------------------------------------
-- SAMPLE SERVICES
-- ------------------------------------------------------------

INSERT INTO services (
    service_name,
    service_description,
    critical,
    minimum_healthy_replicas,
    require_multiple_domains
)
VALUES
    (
        'customer-api',
        'Customer-facing application service',
        TRUE,
        2,
        TRUE
    ),
    (
        'transaction-database',
        'Replicated transactional database service',
        TRUE,
        2,
        TRUE
    );

-- ------------------------------------------------------------
-- SAMPLE SERVICE REPLICAS
-- ------------------------------------------------------------

INSERT INTO service_replicas (
    service_id,
    node_id,
    replica_role
)
SELECT
    s.service_id,
    n.node_id,
    'ACTIVE'
FROM (
    VALUES
        ('customer-api', 'app-1'),
        ('customer-api', 'app-2'),
        ('customer-api', 'app-3'),
        ('transaction-database', 'db-1'),
        ('transaction-database', 'db-2'),
        ('transaction-database', 'db-3')
) AS data(service_name, node_name)
JOIN services s
    ON s.service_name = data.service_name
JOIN infrastructure_nodes n
    ON n.node_name = data.node_name;

-- ------------------------------------------------------------
-- SAMPLE DATABASE REPLICATION
-- ------------------------------------------------------------

INSERT INTO replication_groups (
    group_name,
    replication_method,
    synchronous_commit_required,
    maximum_replica_lag_ms,
    minimum_acknowledgements
)
VALUES
    ('transaction-cluster', 'SYNCHRONOUS', TRUE, 100, 2),
    ('analytics-cluster', 'ASYNCHRONOUS', FALSE, 5000, 1);

INSERT INTO database_replication_members (
    replication_group_id,
    node_id,
    replication_role,
    replication_lag_ms
)
SELECT
    rg.replication_group_id,
    n.node_id,
    data.replication_role,
    data.replication_lag_ms
FROM (
    VALUES
        ('transaction-cluster', 'db-1', 'PRIMARY', 0),
        ('transaction-cluster', 'db-2', 'REPLICA', 10),
        ('transaction-cluster', 'db-3', 'REPLICA', 20),
        ('analytics-cluster', 'db-1', 'PRIMARY', 0),
        ('analytics-cluster', 'db-2', 'REPLICA', 300)
) AS data(group_name, node_name, replication_role, replication_lag_ms)
JOIN replication_groups rg
    ON rg.group_name = data.group_name
JOIN infrastructure_nodes n
    ON n.node_name = data.node_name;

-- ------------------------------------------------------------
-- SAMPLE CONTROL PLANE
-- ------------------------------------------------------------

INSERT INTO quorum_clusters (
    cluster_name,
    required_majority
)
VALUES ('production-control-plane', 2);

INSERT INTO quorum_members (
    quorum_cluster_id,
    node_id,
    voting_enabled
)
SELECT
    qc.quorum_cluster_id,
    n.node_id,
    TRUE
FROM quorum_clusters qc
CROSS JOIN infrastructure_nodes n
WHERE qc.cluster_name = 'production-control-plane'
  AND n.node_name IN (
      'control-1',
      'control-2',
      'control-3'
  );

UPDATE quorum_clusters qc
SET leader_node_id = n.node_id,
    current_term = 1
FROM infrastructure_nodes n
WHERE qc.cluster_name = 'production-control-plane'
  AND n.node_name = 'control-1';

-- ------------------------------------------------------------
-- SAMPLE HEALTH CHECKS
-- ------------------------------------------------------------

INSERT INTO health_checks (
    node_id,
    check_passed,
    response_time_ms,
    error_message
)
SELECT
    node_id,
    status = 'HEALTHY',
    CASE WHEN status = 'HEALTHY' THEN 15 ELSE NULL END,
    CASE WHEN status = 'HEALTHY' THEN NULL ELSE 'Node unavailable' END
FROM infrastructure_nodes;

-- ------------------------------------------------------------
-- SAMPLE FAILOVER EVENTS
-- ------------------------------------------------------------

INSERT INTO failover_events (
    service_id,
    failed_node_id,
    status,
    fencing_token,
    failure_reason
)
SELECT
    s.service_id,
    n.node_id,
    'DETECTED',
    0,
    'Application node heartbeat failure'
FROM services s
JOIN infrastructure_nodes n
    ON n.node_name = 'app-1'
WHERE s.service_name = 'customer-api';

-- ------------------------------------------------------------
-- SAMPLE INCIDENTS
-- ------------------------------------------------------------

INSERT INTO infrastructure_incidents (
    domain_id,
    severity,
    description
)
SELECT
    domain_id,
    'HIGH',
    'Simulated availability-zone degradation'
FROM failure_domains
WHERE domain_name = 'zone-d';

-- ------------------------------------------------------------
-- QUERY 1: SERVICE AVAILABILITY
-- ------------------------------------------------------------

SELECT *
FROM service_availability
ORDER BY service_name;

-- ------------------------------------------------------------
-- QUERY 2: SERVICE ELIGIBILITY
-- ------------------------------------------------------------

SELECT *
FROM evaluate_service(
    (SELECT service_id
     FROM services
     WHERE service_name = 'customer-api')
);

-- ------------------------------------------------------------
-- QUERY 3: QUORUM AVAILABILITY
-- ------------------------------------------------------------

SELECT *
FROM quorum_availability;

-- ------------------------------------------------------------
-- QUERY 4: FAILURE-DOMAIN RISK ANALYSIS
-- ------------------------------------------------------------

SELECT *
FROM failure_domain_analysis
WHERE violates_availability_policy = TRUE
ORDER BY service_name, domain_name;

-- ------------------------------------------------------------
-- QUERY 5: REPLICATION HEALTH
-- ------------------------------------------------------------

SELECT
    rg.group_name,
    rg.replication_method,
    rg.minimum_acknowledgements,
    COUNT(m.replication_member_id) AS member_count,
    COUNT(m.replication_member_id) FILTER (
        WHERE n.status = 'HEALTHY'
    ) AS healthy_members,
    MAX(m.replication_lag_ms) AS maximum_observed_lag_ms,
    BOOL_AND(
        m.replication_lag_ms <= rg.maximum_replica_lag_ms
    ) AS replication_lag_within_policy
FROM replication_groups rg
JOIN database_replication_members m
    ON m.replication_group_id = rg.replication_group_id
JOIN infrastructure_nodes n
    ON n.node_id = m.node_id
GROUP BY
    rg.replication_group_id,
    rg.group_name,
    rg.replication_method,
    rg.minimum_acknowledgements;

-- ------------------------------------------------------------
-- QUERY 6: HEALTH CHECK FAILURE HISTORY
-- ------------------------------------------------------------

SELECT
    n.node_name,
    h.checked_at,
    h.response_time_ms,
    h.error_message
FROM health_checks h
JOIN infrastructure_nodes n
    ON n.node_id = h.node_id
WHERE h.check_passed = FALSE
ORDER BY h.checked_at DESC;

-- ------------------------------------------------------------
-- QUERY 7: FAILOVER REPORT
-- ------------------------------------------------------------

SELECT
    s.service_name,
    failed.node_name AS failed_node,
    replacement.node_name AS replacement_node,
    fe.status,
    fe.fencing_token,
    fe.detected_at,
    fe.completed_at
FROM failover_events fe
LEFT JOIN services s
    ON s.service_id = fe.service_id
LEFT JOIN infrastructure_nodes failed
    ON failed.node_id = fe.failed_node_id
LEFT JOIN infrastructure_nodes replacement
    ON replacement.node_id = fe.replacement_node_id
ORDER BY fe.detected_at DESC;

-- ------------------------------------------------------------
-- QUERY 8: INCIDENT REPORT
-- ------------------------------------------------------------

SELECT
    fd.domain_name,
    i.severity,
    i.description,
    i.opened_at,
    i.resolved_at
FROM infrastructure_incidents i
LEFT JOIN failure_domains fd
    ON fd.domain_id = i.domain_id
ORDER BY i.opened_at DESC;

-- ------------------------------------------------------------
-- QUERY 9: AUTOMATIC FAILURE-DETECTION REPORT
-- ------------------------------------------------------------

SELECT
    n.node_name,
    n.status,
    n.last_heartbeat,
    MAX(h.checked_at) AS latest_check,
    COUNT(h.health_check_id) FILTER (
        WHERE NOT h.check_passed
    ) AS failed_checks
FROM infrastructure_nodes n
LEFT JOIN health_checks h
    ON h.node_id = n.node_id
GROUP BY n.node_id, n.node_name, n.status, n.last_heartbeat
ORDER BY n.node_name;

-- ------------------------------------------------------------
-- QUERY 10: AVAILABILITY BY FAILURE DOMAIN
-- ------------------------------------------------------------

SELECT
    fd.domain_name,
    fd.region_name,
    COUNT(n.node_id) AS registered_nodes,
    COUNT(n.node_id) FILTER (
        WHERE n.status = 'HEALTHY'
    ) AS healthy_nodes,
    COUNT(n.node_id) FILTER (
        WHERE n.status = 'FAILED'
    ) AS failed_nodes,
    COUNT(n.node_id) FILTER (
        WHERE n.status = 'MAINTENANCE'
    ) AS maintenance_nodes
FROM failure_domains fd
LEFT JOIN infrastructure_nodes n
    ON n.domain_id = fd.domain_id
GROUP BY fd.domain_id, fd.domain_name, fd.region_name
ORDER BY fd.domain_name;

COMMIT;

-- ============================================================
-- TRANSACTIONAL FAILOVER EXAMPLE
--
-- Execute separately when an actual replacement is required.
-- The replacement must be healthy and in an eligible domain.
--
-- BEGIN;
--
-- CALL ha.execute_failover(
--     (SELECT failover_event_id
--      FROM ha.failover_events
--      WHERE status = 'DETECTED'
--      ORDER BY failover_event_id
--      LIMIT 1),
--     (SELECT node_id
--      FROM ha.infrastructure_nodes
--      WHERE node_name = 'app-4')
-- );
--
-- COMMIT;
--
-- On any validation error, issue ROLLBACK.
-- ============================================================

-- ============================================================
-- OPERATIONAL LIMITATIONS
--
-- 1. PostgreSQL stores governance and simulation state.
-- 2. Health-check records require an external monitoring agent.
-- 3. Database replication requires actual database configuration.
-- 4. Quorum calculations do not implement a consensus protocol.
-- 5. Fencing tokens must be enforced by the real infrastructure.
-- 6. Network partitions require independent failure detection.
-- 7. A successful failover transaction does not prove that
--    the replacement application is operational.
-- 8. The database itself requires HA deployment and backups.
-- ============================================================
