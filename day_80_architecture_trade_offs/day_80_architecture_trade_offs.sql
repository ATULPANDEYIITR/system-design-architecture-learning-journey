/*
===============================================================================
ARCHITECTURE TRADE-OFF MANAGEMENT DATABASE
PostgreSQL 15+

Domain:
- Architecture alternatives
- Architecture components and dependencies
- Infrastructure and operational costs
- Workload definitions
- Performance measurements
- Availability and reliability
- Failure scenarios
- Decision criteria and weights
- Hard governance constraints
- Weighted evaluations
- Pareto analysis
- Architecture decisions and audit history

Run as a database role with schema and table creation privileges.

The script is repeatable and uses a dedicated schema.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS architecture_mgmt;

SET search_path TO architecture_mgmt, public;

CREATE TABLE IF NOT EXISTS architecture_catalog (
    architecture_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    architecture_code VARCHAR(60) NOT NULL UNIQUE,
    architecture_name VARCHAR(150) NOT NULL,
    architecture_type VARCHAR(30) NOT NULL
        CHECK (architecture_type IN (
            'MONOLITH',
            'MODULAR_MONOLITH',
            'MICROSERVICES',
            'SERVERLESS',
            'EVENT_DRIVEN',
            'HYBRID'
        )),
    deployment_model VARCHAR(40) NOT NULL
        CHECK (deployment_model IN (
            'SINGLE_DEPLOYMENT',
            'DISTRIBUTED_DEPLOYMENT',
            'MANAGED_EXECUTION',
            'ASYNCHRONOUS_PIPELINE',
            'HYBRID_DEPLOYMENT'
        )),
    description TEXT NOT NULL,
    lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (lifecycle_status IN (
            'ACTIVE',
            'DEPRECATED',
            'RETIRED'
        )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (architecture_name)
);

CREATE TABLE IF NOT EXISTS architecture_components (
    component_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    component_name VARCHAR(120) NOT NULL,
    component_type VARCHAR(50) NOT NULL,
    criticality VARCHAR(15) NOT NULL
        CHECK (criticality IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    availability_percent NUMERIC(7,4) NOT NULL
        CHECK (availability_percent > 0 AND availability_percent <= 100),
    recovery_time_minutes NUMERIC(12,2) NOT NULL DEFAULT 0
        CHECK (recovery_time_minutes >= 0),
    UNIQUE (architecture_id, component_name)
);

CREATE TABLE IF NOT EXISTS architecture_dependencies (
    architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    dependency_architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    dependency_type VARCHAR(20) NOT NULL
        CHECK (dependency_type IN ('SERIAL', 'OPTIONAL', 'REDUNDANT')),
    description TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (architecture_id, dependency_architecture_id),
    CHECK (architecture_id <> dependency_architecture_id)
);

CREATE TABLE IF NOT EXISTS cost_profiles (
    cost_profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    currency_code CHAR(3) NOT NULL DEFAULT 'USD',
    monthly_compute_cost NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (monthly_compute_cost >= 0),
    monthly_storage_cost NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (monthly_storage_cost >= 0),
    monthly_network_cost NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (monthly_network_cost >= 0),
    monthly_platform_cost NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (monthly_platform_cost >= 0),
    monthly_operations_cost NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (monthly_operations_cost >= 0),
    monthly_support_cost NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (monthly_support_cost >= 0),
    effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
    effective_until DATE,
    CHECK (
        effective_until IS NULL OR effective_until > effective_from
    ),
    UNIQUE (architecture_id, effective_from)
);

CREATE TABLE IF NOT EXISTS workload_profiles (
    workload_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workload_name VARCHAR(120) NOT NULL UNIQUE,
    average_requests_per_second NUMERIC(14,2) NOT NULL
        CHECK (average_requests_per_second >= 0),
    peak_multiplier NUMERIC(8,3) NOT NULL
        CHECK (peak_multiplier >= 1),
    payload_kb NUMERIC(12,3) NOT NULL
        CHECK (payload_kb >= 0),
    concurrent_users INTEGER NOT NULL
        CHECK (concurrent_users >= 0),
    latency_sla_ms NUMERIC(12,3) NOT NULL
        CHECK (latency_sla_ms > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS performance_measurements (
    measurement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    workload_id BIGINT NOT NULL
        REFERENCES workload_profiles(workload_id),
    environment VARCHAR(20) NOT NULL
        CHECK (environment IN ('TEST', 'STAGING', 'PRODUCTION')),
    sample_size BIGINT NOT NULL
        CHECK (sample_size > 0),
    average_latency_ms NUMERIC(12,3) NOT NULL
        CHECK (average_latency_ms >= 0),
    p95_latency_ms NUMERIC(12,3) NOT NULL
        CHECK (p95_latency_ms >= 0),
    p99_latency_ms NUMERIC(12,3) NOT NULL
        CHECK (p99_latency_ms >= 0),
    throughput_rps NUMERIC(14,2) NOT NULL
        CHECK (throughput_rps >= 0),
    error_rate_percent NUMERIC(7,4) NOT NULL
        CHECK (error_rate_percent BETWEEN 0 AND 100),
    measured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (p95_latency_ms >= average_latency_ms),
    CHECK (p99_latency_ms >= p95_latency_ms)
);

CREATE TABLE IF NOT EXISTS reliability_profiles (
    reliability_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    availability_percent NUMERIC(7,4) NOT NULL
        CHECK (availability_percent > 0 AND availability_percent <= 100),
    mttr_minutes NUMERIC(12,2) NOT NULL
        CHECK (mttr_minutes >= 0),
    mtbf_hours NUMERIC(14,2)
        CHECK (mtbf_hours IS NULL OR mtbf_hours > 0),
    recovery_strategy VARCHAR(50) NOT NULL,
    disaster_recovery_tested BOOLEAN NOT NULL DEFAULT FALSE,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS failure_scenarios (
    failure_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    failure_name VARCHAR(150) NOT NULL,
    failure_category VARCHAR(40) NOT NULL
        CHECK (failure_category IN (
            'INFRASTRUCTURE',
            'NETWORK',
            'DATABASE',
            'APPLICATION',
            'SECURITY',
            'DEPLOYMENT',
            'HUMAN_ERROR',
            'PROVIDER'
        )),
    annual_probability NUMERIC(8,6) NOT NULL
        CHECK (annual_probability BETWEEN 0 AND 1),
    financial_impact NUMERIC(16,2) NOT NULL
        CHECK (financial_impact >= 0),
    recovery_minutes NUMERIC(12,2) NOT NULL
        CHECK (recovery_minutes >= 0),
    mitigation TEXT NOT NULL,
    UNIQUE (architecture_id, failure_name)
);

CREATE TABLE IF NOT EXISTS decision_criteria (
    criterion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    criterion_code VARCHAR(40) NOT NULL UNIQUE,
    criterion_name VARCHAR(100) NOT NULL,
    evaluation_direction VARCHAR(15) NOT NULL
        CHECK (evaluation_direction IN ('MINIMIZE', 'MAXIMIZE')),
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_profiles (
    decision_profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_name VARCHAR(120) NOT NULL UNIQUE,
    monthly_budget NUMERIC(14,2) NOT NULL
        CHECK (monthly_budget >= 0),
    minimum_availability NUMERIC(7,4) NOT NULL
        CHECK (minimum_availability > 0 AND minimum_availability <= 100),
    minimum_throughput_rps NUMERIC(14,2) NOT NULL
        CHECK (minimum_throughput_rps >= 0),
    maximum_latency_ms NUMERIC(12,3) NOT NULL
        CHECK (maximum_latency_ms > 0),
    require_disaster_recovery BOOLEAN NOT NULL DEFAULT FALSE,
    require_production_benchmark BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS decision_weights (
    decision_profile_id BIGINT NOT NULL
        REFERENCES decision_profiles(decision_profile_id)
        ON DELETE CASCADE,
    criterion_id BIGINT NOT NULL
        REFERENCES decision_criteria(criterion_id),
    weight NUMERIC(8,6) NOT NULL
        CHECK (weight BETWEEN 0 AND 1),
    PRIMARY KEY (decision_profile_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS architecture_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    architecture_id BIGINT NOT NULL
        REFERENCES architecture_catalog(architecture_id),
    decision_profile_id BIGINT NOT NULL
        REFERENCES decision_profiles(decision_profile_id),
    workload_id BIGINT NOT NULL
        REFERENCES workload_profiles(workload_id),
    monthly_cost NUMERIC(14,2) NOT NULL,
    annual_cost NUMERIC(16,2) NOT NULL,
    effective_availability NUMERIC(9,6) NOT NULL,
    annual_downtime_hours NUMERIC(12,4) NOT NULL,
    cost_score NUMERIC(8,3) NOT NULL,
    performance_score NUMERIC(8,3) NOT NULL,
    reliability_score NUMERIC(8,3) NOT NULL,
    complexity_score NUMERIC(8,3) NOT NULL,
    scalability_score NUMERIC(8,3) NOT NULL,
    weighted_score NUMERIC(8,3) NOT NULL,
    eligible BOOLEAN NOT NULL,
    violations JSONB NOT NULL DEFAULT '[]'::JSONB,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (annual_cost >= 0),
    CHECK (effective_availability > 0 AND effective_availability <= 100),
    CHECK (annual_downtime_hours >= 0),
    CHECK (weighted_score BETWEEN 0 AND 100)
);

CREATE TABLE IF NOT EXISTS architecture_decisions (
    decision_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decision_code UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    decision_title VARCHAR(180) NOT NULL,
    context TEXT NOT NULL,
    selected_architecture_id BIGINT
        REFERENCES architecture_catalog(architecture_id),
    selected_evaluation_id BIGINT
        REFERENCES architecture_evaluations(evaluation_id),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('PROPOSED', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')),
    decision_owner VARCHAR(120) NOT NULL,
    decision_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consequences JSONB NOT NULL DEFAULT '[]'::JSONB
);

CREATE TABLE IF NOT EXISTS architecture_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_name VARCHAR(80) NOT NULL,
    entity_id BIGINT NOT NULL,
    operation VARCHAR(10) NOT NULL
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    database_user_name TEXT NOT NULL DEFAULT CURRENT_USER,
    old_values JSONB,
    new_values JSONB
);

CREATE INDEX IF NOT EXISTS idx_cost_architecture_effective
    ON cost_profiles(architecture_id, effective_from DESC);

CREATE INDEX IF NOT EXISTS idx_performance_architecture_workload
    ON performance_measurements(
        architecture_id,
        workload_id,
        measured_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_reliability_architecture_date
    ON reliability_profiles(architecture_id, measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_failures_architecture
    ON failure_scenarios(architecture_id);

CREATE INDEX IF NOT EXISTS idx_evaluation_profile_score
    ON architecture_evaluations(
        decision_profile_id,
        eligible,
        weighted_score DESC
    );

CREATE INDEX IF NOT EXISTS idx_evaluation_violations
    ON architecture_evaluations USING GIN(violations);

CREATE INDEX IF NOT EXISTS idx_decisions_status_date
    ON architecture_decisions(status, decision_date DESC);

-- Audit changes to cost profiles without exposing secrets or credentials.
CREATE OR REPLACE FUNCTION audit_cost_profile_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO architecture_audit(
            entity_name, entity_id, operation, new_values
        )
        VALUES (
            'cost_profiles',
            NEW.cost_profile_id,
            'INSERT',
            to_jsonb(NEW)
        );

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO architecture_audit(
            entity_name, entity_id, operation,
            old_values, new_values
        )
        VALUES (
            'cost_profiles',
            NEW.cost_profile_id,
            'UPDATE',
            to_jsonb(OLD),
            to_jsonb(NEW)
        );

        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO architecture_audit(
            entity_name, entity_id, operation, old_values
        )
        VALUES (
            'cost_profiles',
            OLD.cost_profile_id,
            'DELETE',
            to_jsonb(OLD)
        );

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_cost_profile_audit ON cost_profiles;

CREATE TRIGGER trg_cost_profile_audit
AFTER INSERT OR UPDATE OR DELETE ON cost_profiles
FOR EACH ROW
EXECUTE FUNCTION audit_cost_profile_changes();

-- Enforce decision weight completeness and normalization before evaluation.
CREATE OR REPLACE FUNCTION validate_decision_weights(
    p_profile_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    total_weight NUMERIC;
    criterion_count INTEGER;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(weight), 0)
    INTO criterion_count, total_weight
    FROM decision_weights
    WHERE decision_profile_id = p_profile_id;

    IF criterion_count <> 5 THEN
        RAISE EXCEPTION
            'Decision profile % requires exactly five criteria',
            p_profile_id;
    END IF;

    IF ABS(total_weight - 1.0) > 0.000001 THEN
        RAISE EXCEPTION
            'Decision profile % weights sum to %, expected 1',
            p_profile_id, total_weight;
    END IF;

    RETURN TRUE;
END;
$$;

-- A report view calculates the current effective monthly costs.
CREATE OR REPLACE VIEW v_architecture_costs AS
SELECT
    a.architecture_id,
    a.architecture_name,
    a.architecture_type,
    COALESCE(SUM(
        c.monthly_compute_cost +
        c.monthly_storage_cost +
        c.monthly_network_cost +
        c.monthly_platform_cost +
        c.monthly_operations_cost +
        c.monthly_support_cost
    ), 0)::NUMERIC(14,2) AS monthly_total_cost,
    (
        COALESCE(SUM(
            c.monthly_compute_cost +
            c.monthly_storage_cost +
            c.monthly_network_cost +
            c.monthly_platform_cost +
            c.monthly_operations_cost +
            c.monthly_support_cost
        ), 0) * 12
    )::NUMERIC(16,2) AS annual_total_cost
FROM architecture_catalog a
LEFT JOIN cost_profiles c
    ON c.architecture_id = a.architecture_id
   AND CURRENT_DATE >= c.effective_from
   AND (
       c.effective_until IS NULL
       OR CURRENT_DATE < c.effective_until
   )
GROUP BY
    a.architecture_id,
    a.architecture_name,
    a.architecture_type;

-- Annual expected failure loss is the sum of probability times impact.
CREATE OR REPLACE VIEW v_expected_failure_loss AS
SELECT
    a.architecture_id,
    a.architecture_name,
    COALESCE(
        SUM(f.annual_probability * f.financial_impact),
        0
    )::NUMERIC(16,2) AS expected_annual_failure_loss
FROM architecture_catalog a
LEFT JOIN failure_scenarios f
    ON f.architecture_id = a.architecture_id
GROUP BY a.architecture_id, a.architecture_name;

-- Retrieve the latest performance result for each architecture/workload.
CREATE OR REPLACE VIEW v_latest_performance AS
SELECT DISTINCT ON (architecture_id, workload_id)
    architecture_id,
    workload_id,
    environment,
    average_latency_ms,
    p95_latency_ms,
    p99_latency_ms,
    throughput_rps,
    error_rate_percent,
    measured_at
FROM performance_measurements
ORDER BY
    architecture_id,
    workload_id,
    measured_at DESC;

-- Function to calculate serial dependency availability.
CREATE OR REPLACE FUNCTION serial_availability(
    p_availabilities NUMERIC[]
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    result NUMERIC := 1;
    component_availability NUMERIC;
BEGIN
    IF p_availabilities IS NULL OR cardinality(p_availabilities) = 0 THEN
        RAISE EXCEPTION 'At least one availability value is required';
    END IF;

    FOREACH component_availability IN ARRAY p_availabilities
    LOOP
        IF component_availability <= 0 OR
           component_availability > 1 THEN
            RAISE EXCEPTION
                'Availability must be in (0, 1]: %',
                component_availability;
        END IF;

        result := result * component_availability;
    END LOOP;

    RETURN result;
END;
$$;

-- Evaluation procedure: applies hard constraints before weighted scoring.
CREATE OR REPLACE PROCEDURE evaluate_architectures(
    p_profile_id BIGINT,
    p_workload_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    profile_row decision_profiles%ROWTYPE;
    workload_row workload_profiles%ROWTYPE;
    architecture_row RECORD;
    score_cost NUMERIC;
    score_performance NUMERIC;
    score_reliability NUMERIC;
    score_complexity NUMERIC;
    score_scalability NUMERIC;
    final_score NUMERIC;
    monthly_cost NUMERIC;
    effective_availability NUMERIC;
    downtime NUMERIC;
    violations JSONB;
    eligible_value BOOLEAN;
    weights_json JSONB;
    cost_weight NUMERIC;
    performance_weight NUMERIC;
    reliability_weight NUMERIC;
    complexity_weight NUMERIC;
    scalability_weight NUMERIC;
BEGIN
    SELECT *
    INTO profile_row
    FROM decision_profiles
    WHERE decision_profile_id = p_profile_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Decision profile % does not exist', p_profile_id;
    END IF;

    SELECT *
    INTO workload_row
    FROM workload_profiles
    WHERE workload_id = p_workload_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Workload % does not exist', p_workload_id;
    END IF;

    PERFORM validate_decision_weights(p_profile_id);

    SELECT jsonb_object_agg(
        criterion_code,
        weight
    )
    INTO weights_json
    FROM decision_weights dw
    JOIN decision_criteria dc
        ON dc.criterion_id = dw.criterion_id
    WHERE dw.decision_profile_id = p_profile_id;

    cost_weight := (weights_json->>'COST')::NUMERIC;
    performance_weight := (weights_json->>'PERFORMANCE')::NUMERIC;
    reliability_weight := (weights_json->>'RELIABILITY')::NUMERIC;
    complexity_weight := (weights_json->>'COMPLEXITY')::NUMERIC;
    scalability_weight := (weights_json->>'SCALABILITY')::NUMERIC;

    DELETE FROM architecture_evaluations
    WHERE decision_profile_id = p_profile_id
      AND workload_id = p_workload_id;

    FOR architecture_row IN
        SELECT
            a.architecture_id,
            a.architecture_name,
            a.lifecycle_status,
            c.monthly_total_cost,
            p.average_latency_ms,
            p.throughput_rps,
            r.availability_percent,
            r.disaster_recovery_tested,
            r.mttr_minutes
        FROM architecture_catalog a
        LEFT JOIN v_architecture_costs c
            ON c.architecture_id = a.architecture_id
        LEFT JOIN LATERAL (
            SELECT *
            FROM v_latest_performance lp
            WHERE lp.architecture_id = a.architecture_id
              AND lp.workload_id = p_workload_id
            ORDER BY lp.measured_at DESC
            LIMIT 1
        ) p ON TRUE
        LEFT JOIN LATERAL (
            SELECT *
            FROM reliability_profiles rp
            WHERE rp.architecture_id = a.architecture_id
            ORDER BY rp.measured_at DESC
            LIMIT 1
        ) r ON TRUE
        WHERE a.lifecycle_status = 'ACTIVE'
    LOOP
        monthly_cost := COALESCE(
            architecture_row.monthly_total_cost,
            0
        );

        effective_availability := COALESCE(
            architecture_row.availability_percent,
            0
        );

        violations := '[]'::JSONB;

        IF monthly_cost > profile_row.monthly_budget THEN
            violations := violations ||
                jsonb_build_array('BUDGET_EXCEEDED');
        END IF;

        IF architecture_row.average_latency_ms IS NULL OR
           architecture_row.throughput_rps IS NULL THEN
            violations := violations ||
                jsonb_build_array('PERFORMANCE_BENCHMARK_MISSING');
        ELSE
            IF architecture_row.average_latency_ms >
                LEAST(
                    profile_row.maximum_latency_ms,
                    workload_row.latency_sla_ms
                ) THEN
                violations := violations ||
                    jsonb_build_array('LATENCY_SLA_VIOLATION');
            END IF;

            IF architecture_row.throughput_rps <
                GREATEST(
                    profile_row.minimum_throughput_rps,
                    workload_row.average_requests_per_second *
                    workload_row.peak_multiplier
                ) THEN
                violations := violations ||
                    jsonb_build_array('CAPACITY_REQUIREMENT_NOT_MET');
            END IF;
        END IF;

        IF effective_availability <
            profile_row.minimum_availability THEN
            violations := violations ||
                jsonb_build_array('AVAILABILITY_REQUIREMENT_NOT_MET');
        END IF;

        IF profile_row.require_disaster_recovery AND
           NOT COALESCE(
               architecture_row.disaster_recovery_tested,
               FALSE
           ) THEN
            violations := violations ||
                jsonb_build_array('DISASTER_RECOVERY_NOT_TESTED');
        END IF;

        IF architecture_row.average_latency_ms IS NULL OR
           architecture_row.throughput_rps IS NULL OR
           effective_availability <= 0 THEN
            score_cost := 0;
            score_performance := 0;
            score_reliability := 0;
            score_complexity := 0;
            score_scalability := 0;
            final_score := 0;
            downtime := 8760;
        ELSE
            score_cost := CASE
                WHEN profile_row.monthly_budget = 0 THEN
                    CASE WHEN monthly_cost = 0 THEN 100 ELSE 0 END
                ELSE
                    100 / (
                        1 + monthly_cost /
                        profile_row.monthly_budget
                    )
            END;

            score_performance := (
                LEAST(
                    100,
                    100 * profile_row.maximum_latency_ms /
                    GREATEST(
                        profile_row.maximum_latency_ms,
                        architecture_row.average_latency_ms
                    )
                ) +
                LEAST(
                    100,
                    100 * architecture_row.throughput_rps /
                    GREATEST(
                        1,
                        workload_row.average_requests_per_second *
                        workload_row.peak_multiplier
                    )
                )
            ) / 2;

            score_reliability := effective_availability;

            score_complexity := 50;
            score_scalability := 50;

            downtime := 8760 *
                (1 - effective_availability / 100);

            final_score :=
                score_cost * cost_weight +
                score_performance * performance_weight +
                score_reliability * reliability_weight +
                score_complexity * complexity_weight +
                score_scalability * scalability_weight;
        END IF;

        eligible_value := jsonb_array_length(violations) = 0;

        INSERT INTO architecture_evaluations(
            architecture_id,
            decision_profile_id,
            workload_id,
            monthly_cost,
            annual_cost,
            effective_availability,
            annual_downtime_hours,
            cost_score,
            performance_score,
            reliability_score,
            complexity_score,
            scalability_score,
            weighted_score,
            eligible,
            violations
        )
        VALUES (
            architecture_row.architecture_id,
            p_profile_id,
            p_workload_id,
            monthly_cost,
            monthly_cost * 12,
            GREATEST(effective_availability, 0.000001),
            downtime,
            score_cost,
            score_performance,
            score_reliability,
            score_complexity,
            score_scalability,
            LEAST(100, GREATEST(0, final_score)),
            eligible_value,
            violations
        );
    END LOOP;
END;
$$;

-- Initial catalog.
INSERT INTO architecture_catalog(
    architecture_code,
    architecture_name,
    architecture_type,
    deployment_model,
    description
)
VALUES
(
    'MODULAR',
    'Modular Monolith',
    'MODULAR_MONOLITH',
    'SINGLE_DEPLOYMENT',
    'Single deployment with explicit internal module boundaries.'
),
(
    'MICROSERVICES',
    'Microservices',
    'MICROSERVICES',
    'DISTRIBUTED_DEPLOYMENT',
    'Independently deployed services communicating over networks.'
),
(
    'SERVERLESS',
    'Serverless',
    'SERVERLESS',
    'MANAGED_EXECUTION',
    'Managed execution with event-triggered scaling.'
),
(
    'EVENT_DRIVEN',
    'Event-Driven',
    'EVENT_DRIVEN',
    'ASYNCHRONOUS_PIPELINE',
    'Asynchronous event communication with independent consumers.'
)
ON CONFLICT (architecture_code) DO NOTHING;

INSERT INTO cost_profiles(
    architecture_id,
    monthly_compute_cost,
    monthly_storage_cost,
    monthly_network_cost,
    monthly_platform_cost,
    monthly_operations_cost,
    monthly_support_cost
)
SELECT
    a.architecture_id,
    v.compute,
    v.storage,
    v.network,
    v.platform,
    v.operations,
    v.support
FROM (
    VALUES
        ('MODULAR', 600, 100, 100, 100, 700, 400),
        ('MICROSERVICES', 2200, 400, 500, 1100, 2200, 1300),
        ('SERVERLESS', 350, 100, 100, 300, 750, 350),
        ('EVENT_DRIVEN', 1200, 350, 300, 750, 1600, 800)
) AS v(code, compute, storage, network, platform, operations, support)
JOIN architecture_catalog a
    ON a.architecture_code = v.code
ON CONFLICT (architecture_id, effective_from) DO NOTHING;

INSERT INTO workload_profiles(
    workload_name,
    average_requests_per_second,
    peak_multiplier,
    payload_kb,
    concurrent_users,
    latency_sla_ms
)
VALUES
(
    'Commerce Peak Workload',
    1200,
    2,
    32,
    10000,
    200
)
ON CONFLICT (workload_name) DO NOTHING;

INSERT INTO reliability_profiles(
    architecture_id,
    availability_percent,
    mttr_minutes,
    mtbf_hours,
    recovery_strategy,
    disaster_recovery_tested
)
SELECT
    architecture_id,
    CASE architecture_code
        WHEN 'MODULAR' THEN 99.95
        WHEN 'MICROSERVICES' THEN 99.90
        WHEN 'SERVERLESS' THEN 99.90
        WHEN 'EVENT_DRIVEN' THEN 99.95
    END,
    CASE architecture_code
        WHEN 'MODULAR' THEN 20
        WHEN 'MICROSERVICES' THEN 35
        WHEN 'SERVERLESS' THEN 15
        WHEN 'EVENT_DRIVEN' THEN 25
    END,
    CASE architecture_code
        WHEN 'MODULAR' THEN 1500
        WHEN 'MICROSERVICES' THEN 1200
        WHEN 'SERVERLESS' THEN 1400
        WHEN 'EVENT_DRIVEN' THEN 1600
    END,
    'Automated recovery and monitoring',
    TRUE
FROM architecture_catalog
WHERE architecture_code IN (
    'MODULAR',
    'MICROSERVICES',
    'SERVERLESS',
    'EVENT_DRIVEN'
)
AND NOT EXISTS (
    SELECT 1
    FROM reliability_profiles rp
    WHERE rp.architecture_id = architecture_catalog.architecture_id
);

INSERT INTO performance_measurements(
    architecture_id,
    workload_id,
    environment,
    sample_size,
    average_latency_ms,
    p95_latency_ms,
    p99_latency_ms,
    throughput_rps,
    error_rate_percent
)
SELECT
    a.architecture_id,
    w.workload_id,
    'STAGING',
    100000,
    v.avg_latency,
    v.p95,
    v.p99,
    v.throughput,
    v.error_rate
FROM (
    VALUES
        ('MODULAR', 95, 160, 195, 1800, 0.10),
        ('MICROSERVICES', 125, 210, 280, 3500, 0.15),
        ('SERVERLESS', 160, 230, 310, 2200, 0.20),
        ('EVENT_DRIVEN', 140, 220, 300, 4200, 0.12)
) AS v(code, avg_latency, p95, p99, throughput, error_rate)
JOIN architecture_catalog a
    ON a.architecture_code = v.code
CROSS JOIN workload_profiles w
WHERE w.workload_name = 'Commerce Peak Workload'
AND NOT EXISTS (
    SELECT 1
    FROM performance_measurements pm
    WHERE pm.architecture_id = a.architecture_id
      AND pm.workload_id = w.workload_id
);

INSERT INTO failure_scenarios(
    architecture_id,
    failure_name,
    failure_category,
    annual_probability,
    financial_impact,
    recovery_minutes,
    mitigation
)
SELECT
    a.architecture_id,
    v.failure_name,
    v.category,
    v.probability,
    v.impact,
    v.recovery,
    v.mitigation
FROM (
    VALUES
        ('MODULAR', 'Database outage', 'DATABASE', 0.10, 50000, 45,
         'Database replication and tested backups'),
        ('MODULAR', 'Deployment rollback', 'DEPLOYMENT', 0.20, 8000, 15,
         'Automated rollback and release verification'),
        ('MICROSERVICES', 'Network partition', 'NETWORK', 0.15, 60000, 35,
         'Timeouts, retries, circuit breakers and isolation'),
        ('MICROSERVICES', 'Service dependency outage', 'APPLICATION', 0.12, 40000, 30,
         'Bulkheads and degraded operation'),
        ('SERVERLESS', 'Provider regional outage', 'PROVIDER', 0.03, 100000, 90,
         'Multi-region recovery strategy'),
        ('EVENT_DRIVEN', 'Message delivery backlog', 'INFRASTRUCTURE', 0.10, 25000, 25,
         'Queue monitoring and consumer scaling')
) AS v(code, failure_name, category, probability, impact, recovery, mitigation)
JOIN architecture_catalog a
    ON a.architecture_code = v.code
ON CONFLICT (architecture_id, failure_name) DO NOTHING;

INSERT INTO decision_criteria(
    criterion_code,
    criterion_name,
    evaluation_direction,
    description
)
VALUES
('COST', 'Cost Efficiency', 'MINIMIZE',
 'Infrastructure and recurring operational expenditure.'),
('PERFORMANCE', 'Performance', 'MAXIMIZE',
 'Latency and workload throughput.'),
('RELIABILITY', 'Reliability', 'MAXIMIZE',
 'Service availability and operational recovery.'),
('COMPLEXITY', 'Operational Simplicity', 'MINIMIZE',
 'Development, deployment and operational complexity.'),
('SCALABILITY', 'Scalability', 'MAXIMIZE',
 'Ability to support increasing workload.')
ON CONFLICT (criterion_code) DO NOTHING;

INSERT INTO decision_profiles(
    profile_name,
    monthly_budget,
    minimum_availability,
    minimum_throughput_rps,
    maximum_latency_ms,
    require_disaster_recovery,
    require_production_benchmark
)
VALUES (
    'Commerce Production Policy',
    6000,
    99.9,
    1500,
    200,
    TRUE,
    FALSE
)
ON CONFLICT (profile_name) DO NOTHING;

INSERT INTO decision_weights(
    decision_profile_id,
    criterion_id,
    weight
)
SELECT
    dp.decision_profile_id,
    dc.criterion_id,
    v.weight
FROM (
    VALUES
        ('COST', 0.25),
        ('PERFORMANCE', 0.20),
        ('RELIABILITY', 0.25),
        ('COMPLEXITY', 0.15),
        ('SCALABILITY', 0.15)
) AS v(code, weight)
JOIN decision_profiles dp
    ON dp.profile_name = 'Commerce Production Policy'
JOIN decision_criteria dc
    ON dc.criterion_code = v.code
ON CONFLICT (decision_profile_id, criterion_id)
DO UPDATE SET weight = EXCLUDED.weight;

COMMIT;

-- Execute the complete architecture evaluation as one transaction.
BEGIN;

CALL evaluate_architectures(
    (
        SELECT decision_profile_id
        FROM decision_profiles
        WHERE profile_name = 'Commerce Production Policy'
    ),
    (
        SELECT workload_id
        FROM workload_profiles
        WHERE workload_name = 'Commerce Peak Workload'
    )
);

COMMIT;

-- 1. Architecture and annual cost retrieval.
SELECT *
FROM v_architecture_costs
ORDER BY monthly_total_cost;

-- 2. Performance comparison.
SELECT
    a.architecture_name,
    p.average_latency_ms,
    p.p95_latency_ms,
    p.p99_latency_ms,
    p.throughput_rps,
    p.error_rate_percent
FROM v_latest_performance p
JOIN architecture_catalog a USING (architecture_id)
ORDER BY p.throughput_rps DESC;

-- 3. Reliability and estimated downtime.
SELECT
    a.architecture_name,
    r.availability_percent,
    8760 * (1 - r.availability_percent / 100)
        AS annual_downtime_hours,
    r.mttr_minutes,
    r.disaster_recovery_tested
FROM reliability_profiles r
JOIN architecture_catalog a USING (architecture_id)
ORDER BY r.availability_percent DESC;

-- 4. Expected annual financial loss from identified failures.
SELECT *
FROM v_expected_failure_loss
ORDER BY expected_annual_failure_loss DESC;

-- 5. Weighted evaluation and hard eligibility.
SELECT
    a.architecture_name,
    e.monthly_cost,
    e.annual_cost,
    e.effective_availability,
    e.annual_downtime_hours,
    e.weighted_score,
    e.eligible,
    e.violations
FROM architecture_evaluations e
JOIN architecture_catalog a USING (architecture_id)
ORDER BY e.eligible DESC, e.weighted_score DESC;

-- 6. Failure scenarios ranked by expected financial exposure.
SELECT
    a.architecture_name,
    f.failure_name,
    f.annual_probability,
    f.financial_impact,
    f.annual_probability * f.financial_impact
        AS expected_annual_loss,
    f.mitigation
FROM failure_scenarios f
JOIN architecture_catalog a USING (architecture_id)
ORDER BY expected_annual_loss DESC;

-- 7. Pareto frontier:
-- An architecture is excluded if another is no worse in all four
-- dimensions and strictly better in at least one.
WITH candidates AS (
    SELECT
        a.architecture_id,
        a.architecture_name,
        c.monthly_total_cost,
        p.average_latency_ms,
        p.throughput_rps,
        r.availability_percent
    FROM architecture_catalog a
    JOIN v_architecture_costs c USING (architecture_id)
    JOIN v_latest_performance p USING (architecture_id)
    JOIN reliability_profiles r USING (architecture_id)
),
frontier AS (
    SELECT candidate.*
    FROM candidates candidate
    WHERE NOT EXISTS (
        SELECT 1
        FROM candidates other
        WHERE other.architecture_id <> candidate.architecture_id
          AND other.monthly_total_cost <= candidate.monthly_total_cost
          AND other.average_latency_ms <= candidate.average_latency_ms
          AND other.throughput_rps >= candidate.throughput_rps
          AND other.availability_percent >= candidate.availability_percent
          AND (
              other.monthly_total_cost < candidate.monthly_total_cost
              OR other.average_latency_ms < candidate.average_latency_ms
              OR other.throughput_rps > candidate.throughput_rps
              OR other.availability_percent > candidate.availability_percent
          )
    )
)
SELECT *
FROM frontier
ORDER BY monthly_total_cost;

-- 8. Workload network ingress estimate.
SELECT
    workload_name,
    average_requests_per_second,
    peak_multiplier,
    average_requests_per_second * peak_multiplier
        AS peak_requests_per_second,
    (
        average_requests_per_second *
        peak_multiplier *
        payload_kb *
        8 / 1024
    ) AS approximate_ingress_mbps
FROM workload_profiles;

-- 9. Validate the normalized decision weights.
SELECT validate_decision_weights(
    decision_profile_id
)
FROM decision_profiles
WHERE profile_name = 'Commerce Production Policy';

-- 10. Transactional architecture decision recording.
BEGIN;

INSERT INTO architecture_decisions(
    decision_title,
    context,
    selected_architecture_id,
    selected_evaluation_id,
    status,
    decision_owner,
    consequences
)
SELECT
    'Commerce platform architecture evaluation',
    'Initial selection based on cost, performance, reliability, complexity and scalability.',
    a.architecture_id,
    e.evaluation_id,
    'PROPOSED',
    'Architecture Review Board',
    jsonb_build_array(
        'Weighted results depend on decision priorities.',
        'Production performance must be verified under representative workloads.',
        'Reliability depends on actual dependency topology.'
    )
FROM architecture_evaluations e
JOIN architecture_catalog a USING (architecture_id)
JOIN decision_profiles dp USING (decision_profile_id)
WHERE dp.profile_name = 'Commerce Production Policy'
  AND e.eligible = TRUE
ORDER BY e.weighted_score DESC
LIMIT 1;

COMMIT;

-- 11. Audit history for cost-profile changes.
SELECT
    audit_id,
    entity_name,
    entity_id,
    operation,
    changed_at,
    database_user_name
FROM architecture_audit
ORDER BY changed_at DESC;

-- 12. Operational risk report.
SELECT
    a.architecture_name,
    COUNT(f.failure_id) AS known_failure_scenarios,
    COALESCE(
        SUM(f.annual_probability * f.financial_impact),
        0
    ) AS annual_expected_loss,
    MAX(f.recovery_minutes) AS worst_recorded_recovery_minutes
FROM architecture_catalog a
LEFT JOIN failure_scenarios f USING (architecture_id)
GROUP BY a.architecture_id, a.architecture_name
ORDER BY annual_expected_loss DESC;
