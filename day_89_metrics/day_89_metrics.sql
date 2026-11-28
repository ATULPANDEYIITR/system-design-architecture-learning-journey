-- ============================================================
-- METRICS ENGINEERING DATABASE
-- Counters, Gauges, Histograms, SLIs, SLOs and Error Budgets
-- PostgreSQL 15+
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS observability;

SET search_path TO observability, public;

-- ------------------------------------------------------------
-- 1. Metric definitions
-- ------------------------------------------------------------

CREATE TYPE metric_type AS ENUM (
    'counter',
    'gauge',
    'histogram'
);

CREATE TYPE sli_state AS ENUM (
    'healthy',
    'breached',
    'no_data'
);

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name VARCHAR(120) NOT NULL UNIQUE,
    environment VARCHAR(30) NOT NULL,
    owner_team VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_environment CHECK (
        environment IN ('development', 'staging', 'production')
    )
);

CREATE TABLE metric_definitions (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL REFERENCES services(service_id),
    metric_name VARCHAR(180) NOT NULL,
    metric_type metric_type NOT NULL,
    description TEXT NOT NULL,
    unit VARCHAR(40) NOT NULL,
    label_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(service_id, metric_name),

    CONSTRAINT valid_metric_name CHECK (
        metric_name ~ '^[a-zA-Z_:][a-zA-Z0-9_:]*$'
    ),

    CONSTRAINT valid_label_schema CHECK (
        jsonb_typeof(label_schema) = 'object'
    )
);

-- ------------------------------------------------------------
-- 2. Metric observations
-- ------------------------------------------------------------

CREATE TABLE metric_samples (
    sample_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metric_id BIGINT NOT NULL
        REFERENCES metric_definitions(metric_id),
    label_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    sample_value DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_sample_value CHECK (
        sample_value >= 0
        AND sample_value < 'Infinity'::DOUBLE PRECISION
    ),

    CONSTRAINT valid_sample_labels CHECK (
        jsonb_typeof(label_values) = 'object'
    )
);

CREATE INDEX idx_samples_metric_time
ON metric_samples(metric_id, observed_at DESC);

CREATE INDEX idx_samples_metric_labels
ON metric_samples USING GIN(label_values);

CREATE INDEX idx_samples_time
ON metric_samples(observed_at DESC);

-- ------------------------------------------------------------
-- 3. Histogram bucket definitions
-- ------------------------------------------------------------

CREATE TABLE histogram_buckets (
    bucket_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metric_id BIGINT NOT NULL
        REFERENCES metric_definitions(metric_id),
    upper_bound DOUBLE PRECISION NOT NULL,
    bucket_order INTEGER NOT NULL,

    UNIQUE(metric_id, upper_bound),
    UNIQUE(metric_id, bucket_order),

    CHECK (upper_bound > 0),
    CHECK (bucket_order >= 1)
);

-- ------------------------------------------------------------
-- 4. SLI and SLO governance
-- ------------------------------------------------------------

CREATE TABLE sli_definitions (
    sli_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL
        REFERENCES services(service_id),
    sli_name VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    numerator_metric_id BIGINT NOT NULL
        REFERENCES metric_definitions(metric_id),
    denominator_metric_id BIGINT NOT NULL
        REFERENCES metric_definitions(metric_id),
    comparison_operator VARCHAR(2) NOT NULL DEFAULT '>=',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(service_id, sli_name),

    CHECK (comparison_operator IN ('>=', '>'))
);

CREATE TABLE slo_policies (
    slo_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sli_id BIGINT NOT NULL REFERENCES sli_definitions(sli_id),
    target_ratio NUMERIC(10, 8) NOT NULL,
    evaluation_window INTERVAL NOT NULL,
    policy_version INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (target_ratio > 0 AND target_ratio <= 1),
    CHECK (evaluation_window > INTERVAL '0 seconds'),
    CHECK (policy_version > 0),

    UNIQUE(sli_id, policy_version)
);

CREATE INDEX idx_active_slo
ON slo_policies(sli_id)
WHERE active = TRUE;

-- ------------------------------------------------------------
-- 5. SLI evaluation history
-- ------------------------------------------------------------

CREATE TABLE sli_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slo_id BIGINT NOT NULL REFERENCES slo_policies(slo_id),
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    good_events BIGINT NOT NULL,
    total_events BIGINT NOT NULL,
    actual_ratio NUMERIC(12, 10),
    target_ratio NUMERIC(10, 8) NOT NULL,
    state sli_state NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (window_end > window_start),
    CHECK (good_events >= 0),
    CHECK (total_events >= 0),
    CHECK (good_events <= total_events),
    CHECK (
        actual_ratio IS NULL
        OR actual_ratio BETWEEN 0 AND 1
    ),

    CHECK (
        (state = 'no_data' AND total_events = 0
         AND actual_ratio IS NULL)
        OR
        (state <> 'no_data' AND total_events > 0
         AND actual_ratio IS NOT NULL)
    )
);

CREATE INDEX idx_sli_evaluations_history
ON sli_evaluations(slo_id, evaluated_at DESC);

-- ------------------------------------------------------------
-- 6. Validate metric samples against metric definitions
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_metric_sample()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_type metric_type;
    v_schema JSONB;
    v_required TEXT[];
    v_actual TEXT[];
BEGIN
    SELECT metric_type, label_schema
    INTO v_type, v_schema
    FROM metric_definitions
    WHERE metric_id = NEW.metric_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Metric definition does not exist';
    END IF;

    IF v_type = 'counter' AND NEW.sample_value < 0 THEN
        RAISE EXCEPTION 'Counter samples cannot be negative';
    END IF;

    SELECT COALESCE(
        array_agg(key ORDER BY key),
        ARRAY[]::TEXT[]
    )
    INTO v_required
    FROM jsonb_object_keys(v_schema) AS key;

    SELECT COALESCE(
        array_agg(key ORDER BY key),
        ARRAY[]::TEXT[]
    )
    INTO v_actual
    FROM jsonb_object_keys(NEW.label_values) AS key;

    IF v_required <> v_actual THEN
        RAISE EXCEPTION
            'Metric label schema mismatch. Required %, received %',
            v_required, v_actual;
    END IF;

    IF v_type = 'histogram' AND NEW.sample_value < 0 THEN
        RAISE EXCEPTION 'Invalid histogram observation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_metric_sample
BEFORE INSERT OR UPDATE ON metric_samples
FOR EACH ROW
EXECUTE FUNCTION validate_metric_sample();

-- ------------------------------------------------------------
-- 7. Enforce histogram-only bucket definitions
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_histogram_bucket()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_type metric_type;
    v_previous DOUBLE PRECISION;
BEGIN
    SELECT metric_type
    INTO v_type
    FROM metric_definitions
    WHERE metric_id = NEW.metric_id;

    IF v_type <> 'histogram' THEN
        RAISE EXCEPTION
            'Buckets can only be assigned to histogram metrics';
    END IF;

    SELECT MAX(upper_bound)
    INTO v_previous
    FROM histogram_buckets
    WHERE metric_id = NEW.metric_id
      AND bucket_id <> COALESCE(NEW.bucket_id, -1);

    IF v_previous IS NOT NULL
       AND NEW.upper_bound <= v_previous THEN
        RAISE EXCEPTION
            'Histogram boundaries must be strictly increasing';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_histogram_bucket
BEFORE INSERT OR UPDATE ON histogram_buckets
FOR EACH ROW
EXECUTE FUNCTION validate_histogram_bucket();

-- ------------------------------------------------------------
-- 8. Metric insertion procedure
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE record_metric(
    p_metric_id BIGINT,
    p_value DOUBLE PRECISION,
    p_labels JSONB,
    p_timestamp TIMESTAMPTZ DEFAULT now()
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value IS NULL OR
       p_value < 0 OR
       p_value = 'Infinity'::DOUBLE PRECISION OR
       p_value = 'NaN'::DOUBLE PRECISION THEN
        RAISE EXCEPTION 'Invalid metric value';
    END IF;

    INSERT INTO metric_samples(
        metric_id,
        sample_value,
        label_values,
        observed_at
    )
    VALUES (
        p_metric_id,
        p_value,
        COALESCE(p_labels, '{}'::JSONB),
        p_timestamp
    );
END;
$$;

-- ------------------------------------------------------------
-- 9. Counter aggregation
-- Counter samples represent increments, not cumulative snapshots.
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW counter_totals AS
SELECT
    d.metric_id,
    d.metric_name,
    s.service_name,
    m.label_values,
    SUM(m.sample_value) AS counter_total,
    COUNT(*) AS increment_count,
    MAX(m.observed_at) AS last_observed
FROM metric_samples m
JOIN metric_definitions d
    ON d.metric_id = m.metric_id
JOIN services s
    ON s.service_id = d.service_id
WHERE d.metric_type = 'counter'
GROUP BY
    d.metric_id,
    d.metric_name,
    s.service_name,
    m.label_values;

-- ------------------------------------------------------------
-- 10. Gauge latest-value retrieval
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW latest_gauges AS
SELECT DISTINCT ON (
    m.metric_id,
    m.label_values
)
    m.metric_id,
    d.metric_name,
    s.service_name,
    m.label_values,
    m.sample_value,
    m.observed_at
FROM metric_samples m
JOIN metric_definitions d
    ON d.metric_id = m.metric_id
JOIN services s
    ON s.service_id = d.service_id
WHERE d.metric_type = 'gauge'
ORDER BY
    m.metric_id,
    m.label_values,
    m.observed_at DESC,
    m.sample_id DESC;

-- ------------------------------------------------------------
-- 11. Histogram aggregation
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW histogram_summary AS
SELECT
    d.metric_id,
    d.metric_name,
    m.label_values,
    COUNT(*) AS observation_count,
    SUM(m.sample_value) AS observation_sum,
    AVG(m.sample_value) AS average_value,
    MIN(m.sample_value) AS minimum_value,
    MAX(m.sample_value) AS maximum_value
FROM metric_samples m
JOIN metric_definitions d
    ON d.metric_id = m.metric_id
WHERE d.metric_type = 'histogram'
GROUP BY
    d.metric_id,
    d.metric_name,
    m.label_values;

-- ------------------------------------------------------------
-- 12. Histogram bucket evaluation
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION histogram_bucket_counts(
    p_metric_id BIGINT,
    p_start TIMESTAMPTZ,
    p_end TIMESTAMPTZ
)
RETURNS TABLE (
    upper_bound DOUBLE PRECISION,
    cumulative_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        b.upper_bound,
        COUNT(m.sample_id) FILTER (
            WHERE m.sample_value <= b.upper_bound
        ) AS cumulative_count
    FROM histogram_buckets b
    LEFT JOIN metric_samples m
        ON m.metric_id = b.metric_id
       AND m.observed_at >= p_start
       AND m.observed_at < p_end
    WHERE b.metric_id = p_metric_id
    GROUP BY b.bucket_id, b.upper_bound, b.bucket_order
    ORDER BY b.bucket_order;
$$;

-- ------------------------------------------------------------
-- 13. SLI evaluation function
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_sli(
    p_slo_id BIGINT,
    p_window_start TIMESTAMPTZ,
    p_window_end TIMESTAMPTZ
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_slo slo_policies%ROWTYPE;
    v_sli sli_definitions%ROWTYPE;

    v_good BIGINT;
    v_total BIGINT;
    v_ratio NUMERIC(12, 10);
    v_state sli_state;
    v_evaluation_id BIGINT;
BEGIN
    IF p_window_end <= p_window_start THEN
        RAISE EXCEPTION 'Invalid evaluation window';
    END IF;

    SELECT *
    INTO v_slo
    FROM slo_policies
    WHERE slo_id = p_slo_id
      AND active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active SLO not found';
    END IF;

    SELECT *
    INTO v_sli
    FROM sli_definitions
    WHERE sli_id = v_slo.sli_id;

    SELECT
        COALESCE(SUM(g.sample_value), 0)::BIGINT,
        COALESCE(SUM(t.sample_value), 0)::BIGINT
    INTO v_good, v_total
    FROM metric_samples g
    JOIN metric_samples t
      ON t.observed_at = g.observed_at
     AND t.label_values = g.label_values
    WHERE g.metric_id = v_sli.numerator_metric_id
      AND t.metric_id = v_sli.denominator_metric_id
      AND g.observed_at >= p_window_start
      AND g.observed_at < p_window_end;

    IF v_total = 0 THEN
        v_ratio := NULL;
        v_state := 'no_data';
    ELSE
        IF v_good > v_total THEN
            RAISE EXCEPTION
                'SLI numerator exceeds denominator';
        END IF;

        v_ratio := v_good::NUMERIC / v_total;

        IF (
            v_sli.comparison_operator = '>='
            AND v_ratio >= v_slo.target_ratio
        ) OR (
            v_sli.comparison_operator = '>'
            AND v_ratio > v_slo.target_ratio
        ) THEN
            v_state := 'healthy';
        ELSE
            v_state := 'breached';
        END IF;
    END IF;

    INSERT INTO sli_evaluations(
        slo_id,
        window_start,
        window_end,
        good_events,
        total_events,
        actual_ratio,
        target_ratio,
        state
    )
    VALUES (
        p_slo_id,
        p_window_start,
        p_window_end,
        v_good,
        v_total,
        v_ratio,
        v_slo.target_ratio,
        v_state
    )
    RETURNING evaluation_id INTO v_evaluation_id;

    RETURN v_evaluation_id;
END;
$$;

-- ------------------------------------------------------------
-- 14. SLO error budget report
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW slo_error_budget AS
SELECT
    e.evaluation_id,
    s.slo_id,
    d.sli_name,
    e.actual_ratio,
    e.target_ratio,
    1 - e.target_ratio AS error_budget_ratio,
    CASE
        WHEN e.actual_ratio IS NULL THEN NULL
        ELSE GREATEST(
            0,
            (1 - e.target_ratio) -
            GREATEST(0, e.target_ratio - e.actual_ratio)
        )
    END AS remaining_error_budget,
    e.state,
    e.window_start,
    e.window_end,
    e.evaluated_at
FROM sli_evaluations e
JOIN slo_policies s ON s.slo_id = e.slo_id
JOIN sli_definitions d ON d.sli_id = s.sli_id;

-- ------------------------------------------------------------
-- 15. Sample production-like records
-- ------------------------------------------------------------

INSERT INTO services(
    service_name,
    environment,
    owner_team
)
VALUES
    ('payment-api', 'production', 'payments'),
    ('identity-api', 'production', 'identity'),
    ('analytics-api', 'staging', 'analytics');

INSERT INTO metric_definitions(
    service_id,
    metric_name,
    metric_type,
    description,
    unit,
    label_schema
)
SELECT
    service_id,
    'http_requests_total',
    'counter',
    'HTTP request increments',
    'requests',
    '{"method":"string","status":"string"}'::JSONB
FROM services
WHERE service_name = 'payment-api';

INSERT INTO metric_definitions(
    service_id,
    metric_name,
    metric_type,
    description,
    unit,
    label_schema
)
SELECT
    service_id,
    'http_active_requests',
    'gauge',
    'Currently active HTTP requests',
    'requests',
    '{}'::JSONB
FROM services
WHERE service_name = 'payment-api';

INSERT INTO metric_definitions(
    service_id,
    metric_name,
    metric_type,
    description,
    unit,
    label_schema
)
SELECT
    service_id,
    'http_request_duration_seconds',
    'histogram',
    'HTTP request duration',
    'seconds',
    '{"method":"string"}'::JSONB
FROM services
WHERE service_name = 'payment-api';

INSERT INTO metric_definitions(
    service_id,
    metric_name,
    metric_type,
    description,
    unit,
    label_schema
)
SELECT
    service_id,
    'http_good_requests_total',
    'counter',
    'Requests satisfying availability criteria',
    'requests',
    '{}'::JSONB
FROM services
WHERE service_name = 'payment-api';

INSERT INTO metric_definitions(
    service_id,
    metric_name,
    metric_type,
    description,
    unit,
    label_schema
)
SELECT
    service_id,
    'http_eligible_requests_total',
    'counter',
    'Requests eligible for availability measurement',
    'requests',
    '{}'::JSONB
FROM services
WHERE service_name = 'payment-api';

-- Histogram boundaries.
INSERT INTO histogram_buckets(
    metric_id,
    upper_bound,
    bucket_order
)
SELECT
    metric_id,
    bucket_value,
    bucket_order
FROM metric_definitions
CROSS JOIN (
    VALUES
        (0.05::DOUBLE PRECISION, 1),
        (0.10::DOUBLE PRECISION, 2),
        (0.25::DOUBLE PRECISION, 3),
        (0.50::DOUBLE PRECISION, 4),
        (1.00::DOUBLE PRECISION, 5),
        (2.00::DOUBLE PRECISION, 6),
        (5.00::DOUBLE PRECISION, 7)
) AS buckets(bucket_value, bucket_order)
WHERE metric_name = 'http_request_duration_seconds';

-- Insert counter increments and gauge measurements.
DO $$
DECLARE
    v_requests BIGINT;
    v_gauge BIGINT;
    v_latency BIGINT;
    v_good BIGINT;
    v_eligible BIGINT;
BEGIN
    SELECT metric_id INTO v_requests
    FROM metric_definitions
    WHERE metric_name = 'http_requests_total';

    SELECT metric_id INTO v_gauge
    FROM metric_definitions
    WHERE metric_name = 'http_active_requests';

    SELECT metric_id INTO v_latency
    FROM metric_definitions
    WHERE metric_name = 'http_request_duration_seconds';

    SELECT metric_id INTO v_good
    FROM metric_definitions
    WHERE metric_name = 'http_good_requests_total';

    SELECT metric_id INTO v_eligible
    FROM metric_definitions
    WHERE metric_name = 'http_eligible_requests_total';

    CALL record_metric(
        v_requests, 1,
        '{"method":"GET","status":"200"}'
    );

    CALL record_metric(
        v_requests, 1,
        '{"method":"GET","status":"200"}'
    );

    CALL record_metric(
        v_requests, 1,
        '{"method":"POST","status":"201"}'
    );

    CALL record_metric(
        v_requests, 1,
        '{"method":"GET","status":"500"}'
    );

    CALL record_metric(v_gauge, 12, '{}');
    CALL record_metric(v_gauge, 8, '{}');
    CALL record_metric(v_gauge, 15, '{}');

    CALL record_metric(
        v_latency, 0.045, '{"method":"GET"}'
    );

    CALL record_metric(
        v_latency, 0.120, '{"method":"GET"}'
    );

    CALL record_metric(
        v_latency, 0.250, '{"method":"POST"}'
    );

    CALL record_metric(v_good, 9990, '{}');
    CALL record_metric(v_eligible, 10000, '{}');
END;
$$;

-- ------------------------------------------------------------
-- 16. Create an availability SLI and SLO
-- ------------------------------------------------------------

INSERT INTO sli_definitions(
    service_id,
    sli_name,
    description,
    numerator_metric_id,
    denominator_metric_id
)
SELECT
    s.service_id,
    'request_availability',
    'Ratio of successful eligible HTTP requests',
    good.metric_id,
    eligible.metric_id
FROM services s
JOIN metric_definitions good
    ON good.service_id = s.service_id
   AND good.metric_name = 'http_good_requests_total'
JOIN metric_definitions eligible
    ON eligible.service_id = s.service_id
   AND eligible.metric_name = 'http_eligible_requests_total'
WHERE s.service_name = 'payment-api';

INSERT INTO slo_policies(
    sli_id,
    target_ratio,
    evaluation_window
)
SELECT
    sli_id,
    0.999,
    INTERVAL '30 days'
FROM sli_definitions
WHERE sli_name = 'request_availability';

-- ------------------------------------------------------------
-- 17. Execute SLI evaluation transactionally
-- ------------------------------------------------------------

DO $$
DECLARE
    v_slo_id BIGINT;
    v_evaluation_id BIGINT;
BEGIN
    SELECT slo_id INTO v_slo_id
    FROM slo_policies
    WHERE active = TRUE
    ORDER BY slo_id
    LIMIT 1;

    v_evaluation_id := evaluate_sli(
        v_slo_id,
        now() - INTERVAL '1 day',
        now() + INTERVAL '1 second'
    );

    RAISE NOTICE 'Created SLI evaluation %', v_evaluation_id;
END;
$$;

COMMIT;

-- ============================================================
-- 18. Operational queries
-- ============================================================

-- Retrieve counter totals.
SELECT *
FROM counter_totals
ORDER BY metric_name;

-- Retrieve current gauge values.
SELECT *
FROM latest_gauges
ORDER BY metric_name;

-- Histogram descriptive statistics.
SELECT *
FROM histogram_summary
ORDER BY metric_name;

-- Retrieve cumulative histogram buckets.
SELECT histogram_bucket_counts(
    (
        SELECT metric_id
        FROM metric_definitions
        WHERE metric_name = 'http_request_duration_seconds'
    ),
    now() - INTERVAL '1 day',
    now() + INTERVAL '1 second'
);

-- SLI evaluation history.
SELECT
    d.sli_name,
    e.good_events,
    e.total_events,
    e.actual_ratio,
    e.target_ratio,
    e.state,
    e.evaluated_at
FROM sli_evaluations e
JOIN slo_policies p ON p.slo_id = e.slo_id
JOIN sli_definitions d ON d.sli_id = p.sli_id
ORDER BY e.evaluated_at DESC;

-- Error budget consumption.
SELECT *
FROM slo_error_budget
ORDER BY evaluated_at DESC;

-- Find breached SLOs.
SELECT *
FROM slo_error_budget
WHERE state = 'breached';

-- Find metrics without observations.
SELECT
    d.metric_name,
    s.service_name
FROM metric_definitions d
JOIN services s ON s.service_id = d.service_id
LEFT JOIN metric_samples m ON m.metric_id = d.metric_id
GROUP BY d.metric_id, d.metric_name, s.service_name
HAVING COUNT(m.sample_id) = 0;

-- Recent metric volume by service.
SELECT
    s.service_name,
    d.metric_name,
    COUNT(m.sample_id) AS observations,
    MIN(m.observed_at) AS first_observation,
    MAX(m.observed_at) AS last_observation
FROM services s
JOIN metric_definitions d ON d.service_id = s.service_id
LEFT JOIN metric_samples m
    ON m.metric_id = d.metric_id
   AND m.observed_at >= now() - INTERVAL '24 hours'
GROUP BY s.service_name, d.metric_name
ORDER BY s.service_name, d.metric_name;

-- ============================================================
-- 19. Example transactional rollback
-- ============================================================

BEGIN;

-- This invalid counter increment violates the sample constraint.
-- The exception aborts the transaction.
-- Execute this test separately if rollback behavior is required.

ROLLBACK;
