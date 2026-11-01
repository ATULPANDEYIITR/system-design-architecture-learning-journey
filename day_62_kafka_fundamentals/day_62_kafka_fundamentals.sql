DROP SCHEMA IF EXISTS kafka_lab CASCADE;

CREATE SCHEMA kafka_lab;

SET search_path TO kafka_lab, public;

-- Kafka fundamentals are represented relationally:
-- brokers own partition leaders, partitions belong to topics,
-- records receive monotonically increasing offsets within partitions,
-- consumer groups maintain independent committed offsets,
-- and branch-like governance is represented here as cluster policies
-- controlling replication and operational state.

CREATE TYPE broker_state AS ENUM (
    'ONLINE',
    'OFFLINE'
);

CREATE TYPE topic_state AS ENUM (
    'ACTIVE',
    'PAUSED'
);

CREATE TYPE consumer_state AS ENUM (
    'ACTIVE',
    'REBALANCING',
    'STOPPED'
);

CREATE TYPE check_state AS ENUM (
    'PASS',
    'FAIL',
    'PENDING'
);

CREATE TABLE brokers (
    broker_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    broker_name TEXT NOT NULL UNIQUE,
    host_name TEXT NOT NULL UNIQUE,
    state broker_state NOT NULL DEFAULT 'ONLINE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(trim(broker_name)) > 0),
    CHECK (length(trim(host_name)) > 0)
);

CREATE TABLE topics (
    topic_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_name TEXT NOT NULL UNIQUE,
    partition_count INTEGER NOT NULL,
    replication_factor INTEGER NOT NULL,
    state topic_state NOT NULL DEFAULT 'ACTIVE',
    retention_seconds BIGINT NOT NULL DEFAULT 604800,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(trim(topic_name)) > 0),
    CHECK (partition_count > 0),
    CHECK (replication_factor > 0),
    CHECK (retention_seconds > 0)
);

CREATE TABLE topic_partitions (
    topic_id BIGINT NOT NULL
        REFERENCES topics(topic_id)
        ON DELETE CASCADE,
    partition_id INTEGER NOT NULL,
    leader_broker_id BIGINT NOT NULL
        REFERENCES brokers(broker_id),
    next_offset BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (topic_id, partition_id),
    CHECK (partition_id >= 0),
    CHECK (next_offset >= 0)
);

CREATE TABLE partition_replicas (
    topic_id BIGINT NOT NULL,
    partition_id INTEGER NOT NULL,
    broker_id BIGINT NOT NULL
        REFERENCES brokers(broker_id),
    replica_rank INTEGER NOT NULL,
    in_sync BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (
        topic_id,
        partition_id,
        broker_id
    ),
    UNIQUE (
        topic_id,
        partition_id,
        replica_rank
    ),
    FOREIGN KEY (
        topic_id,
        partition_id
    )
        REFERENCES topic_partitions(
            topic_id,
            partition_id
        )
        ON DELETE CASCADE,
    CHECK (replica_rank >= 0)
);

CREATE TABLE records (
    topic_id BIGINT NOT NULL,
    partition_id INTEGER NOT NULL,
    record_offset BIGINT NOT NULL,
    record_key TEXT NOT NULL,
    record_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (
        topic_id,
        partition_id,
        record_offset
    ),
    FOREIGN KEY (
        topic_id,
        partition_id
    )
        REFERENCES topic_partitions(
            topic_id,
            partition_id
        )
        ON DELETE CASCADE,
    CHECK (record_offset >= 0),
    CHECK (length(trim(record_key)) > 0)
);

CREATE TABLE consumer_groups (
    group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (length(trim(group_name)) > 0)
);

CREATE TABLE consumers (
    consumer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL
        REFERENCES consumer_groups(group_id)
        ON DELETE CASCADE,
    consumer_name TEXT NOT NULL,
    state consumer_state NOT NULL DEFAULT 'ACTIVE',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (group_id, consumer_name)
);

CREATE TABLE consumer_assignments (
    group_id BIGINT NOT NULL
        REFERENCES consumer_groups(group_id)
        ON DELETE CASCADE,
    consumer_id BIGINT NOT NULL
        REFERENCES consumers(consumer_id)
        ON DELETE CASCADE,
    topic_id BIGINT NOT NULL,
    partition_id INTEGER NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (
        group_id,
        topic_id,
        partition_id
    ),
    UNIQUE (
        group_id,
        consumer_id,
        topic_id,
        partition_id
    ),
    FOREIGN KEY (
        topic_id,
        partition_id
    )
        REFERENCES topic_partitions(
            topic_id,
            partition_id
        )
        ON DELETE CASCADE
);

CREATE TABLE committed_offsets (
    group_id BIGINT NOT NULL
        REFERENCES consumer_groups(group_id)
        ON DELETE CASCADE,
    topic_id BIGINT NOT NULL,
    partition_id INTEGER NOT NULL,
    committed_offset BIGINT NOT NULL DEFAULT 0,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (
        group_id,
        topic_id,
        partition_id
    ),
    FOREIGN KEY (
        topic_id,
        partition_id
    )
        REFERENCES topic_partitions(
            topic_id,
            partition_id
        )
        ON DELETE CASCADE,
    CHECK (committed_offset >= 0)
);

CREATE TABLE status_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_id BIGINT NOT NULL,
    partition_id INTEGER NOT NULL,
    check_name TEXT NOT NULL,
    state check_state NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (
        topic_id,
        partition_id
    )
        REFERENCES topic_partitions(
            topic_id,
            partition_id
        )
        ON DELETE CASCADE,
    UNIQUE (
        topic_id,
        partition_id,
        check_name
    )
);

CREATE TABLE cluster_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    policy_name TEXT NOT NULL UNIQUE,
    minimum_replication_factor INTEGER NOT NULL,
    require_in_sync_replica BOOLEAN NOT NULL DEFAULT TRUE,
    require_online_leader BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (minimum_replication_factor > 0)
);

CREATE INDEX idx_records_topic_partition_time
    ON records (
        topic_id,
        partition_id,
        created_at
    );

CREATE INDEX idx_assignments_consumer
    ON consumer_assignments (
        group_id,
        consumer_id
    );

CREATE INDEX idx_replicas_broker
    ON partition_replicas (
        broker_id,
        in_sync
    );

CREATE INDEX idx_checks_state
    ON status_checks (
        topic_id,
        partition_id,
        state
    );

INSERT INTO brokers (
    broker_name,
    host_name
)
VALUES
    ('broker-1', 'kafka-1.internal'),
    ('broker-2', 'kafka-2.internal'),
    ('broker-3', 'kafka-3.internal');

INSERT INTO topics (
    topic_name,
    partition_count,
    replication_factor,
    retention_seconds
)
VALUES
    ('orders', 3, 2, 604800),
    ('audit-events', 4, 2, 2592000);

INSERT INTO topic_partitions (
    topic_id,
    partition_id,
    leader_broker_id
)
SELECT
    t.topic_id,
    p.partition_id,
    CASE
        WHEN p.partition_id % 3 = 0 THEN 1
        WHEN p.partition_id % 3 = 1 THEN 2
        ELSE 3
    END
FROM topics t
CROSS JOIN LATERAL generate_series(
    0,
    t.partition_count - 1
) AS p(partition_id);

INSERT INTO partition_replicas (
    topic_id,
    partition_id,
    broker_id,
    replica_rank
)
SELECT
    tp.topic_id,
    tp.partition_id,
    CASE
        WHEN r.replica_rank = 0
            THEN tp.leader_broker_id
        ELSE
            ((tp.leader_broker_id + r.replica_rank - 1) % 3) + 1
    END,
    r.replica_rank
FROM topic_partitions tp
JOIN topics t
    ON t.topic_id = tp.topic_id
CROSS JOIN LATERAL generate_series(
    0,
    t.replication_factor - 1
) AS r(replica_rank);

INSERT INTO records (
    topic_id,
    partition_id,
    record_offset,
    record_key,
    record_value
)
SELECT
    t.topic_id,
    v.partition_id,
    v.record_offset,
    v.record_key,
    v.record_value
FROM topics t
JOIN (
    VALUES
        (0, 0, 'order-1001', 'CREATED'),
        (0, 1, 'order-1002', 'PAID'),
        (1, 0, 'order-1003', 'PACKED'),
        (1, 1, 'order-1004', 'SHIPPED'),
        (2, 0, 'order-1005', 'DELIVERED'),
        (2, 1, 'order-1006', 'RETURNED')
) AS v(
    partition_id,
    record_offset,
    record_key,
    record_value
)
    ON TRUE
WHERE t.topic_name = 'orders';

UPDATE topic_partitions tp
SET next_offset = x.max_offset + 1
FROM (
    SELECT
        topic_id,
        partition_id,
        MAX(record_offset) AS max_offset
    FROM records
    GROUP BY topic_id, partition_id
) x
WHERE tp.topic_id = x.topic_id
  AND tp.partition_id = x.partition_id;

INSERT INTO consumer_groups (
    group_name
)
VALUES
    ('order-workers'),
    ('audit-processors');

INSERT INTO consumers (
    group_id,
    consumer_name
)
SELECT
    cg.group_id,
    v.consumer_name
FROM consumer_groups cg
JOIN (
    VALUES
        ('order-workers', 'worker-a'),
        ('order-workers', 'worker-b'),
        ('audit-processors', 'audit-a'),
        ('audit-processors', 'audit-b')
) v(
    group_name,
    consumer_name
)
    ON cg.group_name = v.group_name;

INSERT INTO consumer_assignments (
    group_id,
    consumer_id,
    topic_id,
    partition_id
)
SELECT
    cg.group_id,
    c.consumer_id,
    t.topic_id,
    tp.partition_id
FROM consumer_groups cg
JOIN consumers c
    ON c.group_id = cg.group_id
JOIN topics t
    ON t.topic_name = 'orders'
JOIN topic_partitions tp
    ON tp.topic_id = t.topic_id
WHERE cg.group_name = 'order-workers'
  AND (
      (tp.partition_id % 2 = 0 AND c.consumer_name = 'worker-a')
      OR
      (tp.partition_id % 2 = 1 AND c.consumer_name = 'worker-b')
  );

INSERT INTO committed_offsets (
    group_id,
    topic_id,
    partition_id,
    committed_offset
)
SELECT
    cg.group_id,
    t.topic_id,
    tp.partition_id,
    CASE
        WHEN tp.partition_id = 0 THEN 1
        WHEN tp.partition_id = 1 THEN 2
        ELSE 0
    END
FROM consumer_groups cg
JOIN topics t
    ON t.topic_name = 'orders'
JOIN topic_partitions tp
    ON tp.topic_id = t.topic_id
WHERE cg.group_name = 'order-workers';

INSERT INTO status_checks (
    topic_id,
    partition_id,
    check_name,
    state
)
SELECT
    tp.topic_id,
    tp.partition_id,
    'replica-health',
    CASE
        WHEN COUNT(pr.broker_id) >= t.replication_factor
             AND BOOL_AND(pr.in_sync)
            THEN 'PASS'::check_state
        ELSE 'FAIL'::check_state
    END
FROM topic_partitions tp
JOIN topics t
    ON t.topic_id = tp.topic_id
JOIN partition_replicas pr
    ON pr.topic_id = tp.topic_id
   AND pr.partition_id = tp.partition_id
GROUP BY
    tp.topic_id,
    tp.partition_id,
    t.replication_factor;

INSERT INTO cluster_policies (
    policy_name,
    minimum_replication_factor,
    require_in_sync_replica,
    require_online_leader
)
VALUES
    ('production-default', 2, TRUE, TRUE);

CREATE OR REPLACE FUNCTION validate_record_offset()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_offset BIGINT;
BEGIN
    SELECT next_offset
    INTO expected_offset
    FROM topic_partitions
    WHERE topic_id = NEW.topic_id
      AND partition_id = NEW.partition_id
    FOR UPDATE;

    IF expected_offset IS NULL THEN
        RAISE EXCEPTION
            'Partition %-% does not exist',
            NEW.topic_id,
            NEW.partition_id;
    END IF;

    IF NEW.record_offset <> expected_offset THEN
        RAISE EXCEPTION
            'Expected offset %, received %',
            expected_offset,
            NEW.record_offset;
    END IF;

    UPDATE topic_partitions
    SET next_offset = next_offset + 1
    WHERE topic_id = NEW.topic_id
      AND partition_id = NEW.partition_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_record_offset
BEFORE INSERT ON records
FOR EACH ROW
EXECUTE FUNCTION validate_record_offset();

CREATE OR REPLACE FUNCTION validate_committed_offset()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    available_offset BIGINT;
BEGIN
    SELECT next_offset
    INTO available_offset
    FROM topic_partitions
    WHERE topic_id = NEW.topic_id
      AND partition_id = NEW.partition_id;

    IF NEW.committed_offset > available_offset THEN
        RAISE EXCEPTION
            'Committed offset % exceeds available offset %',
            NEW.committed_offset,
            available_offset;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_committed_offset
BEFORE INSERT OR UPDATE ON committed_offsets
FOR EACH ROW
EXECUTE FUNCTION validate_committed_offset();

CREATE OR REPLACE FUNCTION partition_leader_is_online()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    current_state broker_state;
BEGIN
    SELECT state
    INTO current_state
    FROM brokers
    WHERE broker_id = NEW.leader_broker_id;

    IF current_state <> 'ONLINE' THEN
        RAISE EXCEPTION
            'Partition leader broker % is not online',
            NEW.leader_broker_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_partition_leader_online
BEFORE INSERT OR UPDATE OF leader_broker_id
ON topic_partitions
FOR EACH ROW
EXECUTE FUNCTION partition_leader_is_online();

CREATE OR REPLACE VIEW partition_status AS
SELECT
    t.topic_name,
    tp.partition_id,
    b.broker_name AS leader,
    b.state AS leader_state,
    COUNT(pr.broker_id) AS replica_count,
    COUNT(pr.broker_id)
        FILTER (WHERE pr.in_sync) AS in_sync_replicas,
    tp.next_offset
FROM topic_partitions tp
JOIN topics t
    ON t.topic_id = tp.topic_id
JOIN brokers b
    ON b.broker_id = tp.leader_broker_id
LEFT JOIN partition_replicas pr
    ON pr.topic_id = tp.topic_id
   AND pr.partition_id = tp.partition_id
GROUP BY
    t.topic_name,
    tp.partition_id,
    b.broker_name,
    b.state,
    tp.next_offset;

CREATE OR REPLACE VIEW consumer_lag AS
SELECT
    cg.group_name,
    t.topic_name,
    co.partition_id,
    co.committed_offset,
    tp.next_offset,
    GREATEST(
        tp.next_offset - co.committed_offset,
        0
    ) AS lag
FROM committed_offsets co
JOIN consumer_groups cg
    ON cg.group_id = co.group_id
JOIN topics t
    ON t.topic_id = co.topic_id
JOIN topic_partitions tp
    ON tp.topic_id = co.topic_id
   AND tp.partition_id = co.partition_id;

CREATE OR REPLACE FUNCTION evaluate_topic_health(
    requested_topic TEXT
)
RETURNS TABLE (
    topic TEXT,
    partition_number INTEGER,
    leader_online BOOLEAN,
    replicas INTEGER,
    in_sync_replicas INTEGER,
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE sql
AS $$
    SELECT
        ps.topic_name,
        ps.partition_id,
        ps.leader_state = 'ONLINE',
        ps.replica_count::INTEGER,
        ps.in_sync_replicas::INTEGER,
        (
            ps.leader_state = 'ONLINE'
            AND ps.replica_count >= cp.minimum_replication_factor
            AND (
                NOT cp.require_in_sync_replica
                OR ps.in_sync_replicas >= cp.minimum_replication_factor
            )
        ) AS eligible,
        CASE
            WHEN ps.leader_state <> 'ONLINE'
                THEN 'Leader broker is offline'
            WHEN ps.replica_count < cp.minimum_replication_factor
                THEN 'Insufficient replicas'
            WHEN cp.require_in_sync_replica
                 AND ps.in_sync_replicas <
                     cp.minimum_replication_factor
                THEN 'Insufficient in-sync replicas'
            ELSE 'Eligible'
        END AS reason
    FROM partition_status ps
    CROSS JOIN cluster_policies cp
    WHERE ps.topic_name = requested_topic;
$$;

-- Retrieval: records in partition order.
SELECT
    t.topic_name,
    r.partition_id,
    r.record_offset,
    r.record_key,
    r.record_value,
    r.created_at
FROM records r
JOIN topics t
    ON t.topic_id = r.topic_id
WHERE t.topic_name = 'orders'
ORDER BY
    r.partition_id,
    r.record_offset;

-- Partition and leader report.
SELECT *
FROM partition_status
ORDER BY topic_name, partition_id;

-- Consumer lag report.
SELECT *
FROM consumer_lag
ORDER BY group_name, topic_name, partition_id;

-- Topic health and merge-style eligibility evaluation.
SELECT *
FROM evaluate_topic_health('orders')
ORDER BY partition_number;

-- Aggregation: records per topic and partition.
SELECT
    t.topic_name,
    r.partition_id,
    COUNT(*) AS record_count,
    MIN(r.record_offset) AS first_offset,
    MAX(r.record_offset) AS last_offset
FROM records r
JOIN topics t
    ON t.topic_id = r.topic_id
GROUP BY
    t.topic_name,
    r.partition_id
ORDER BY
    t.topic_name,
    r.partition_id;

-- Validation: detect assignments whose consumer belongs
-- to a different group than the assignment.
SELECT
    ca.group_id,
    ca.consumer_id,
    ca.topic_id,
    ca.partition_id
FROM consumer_assignments ca
JOIN consumers c
    ON c.consumer_id = ca.consumer_id
WHERE c.group_id <> ca.group_id;

-- Validation: detect partition leaders that are not online.
SELECT
    topic_name,
    partition_id,
    leader,
    leader_state
FROM partition_status
WHERE leader_state <> 'ONLINE';

-- Transactional example:
-- advance an order worker's committed offset only when the
-- target offset is known to exist.
BEGIN;

UPDATE committed_offsets co
SET
    committed_offset = LEAST(
        co.committed_offset + 1,
        tp.next_offset
    ),
    committed_at = clock_timestamp()
FROM topic_partitions tp
JOIN topics t
    ON t.topic_id = tp.topic_id
WHERE co.topic_id = tp.topic_id
  AND co.partition_id = tp.partition_id
  AND t.topic_name = 'orders'
  AND co.partition_id = 0
  AND co.group_id = (
      SELECT group_id
      FROM consumer_groups
      WHERE group_name = 'order-workers'
  );

COMMIT;

-- Failure simulation is represented by taking a broker offline.
-- Existing partition leaders can then be detected as unhealthy.
BEGIN;

UPDATE brokers
SET state = 'OFFLINE'
WHERE broker_name = 'broker-1';

COMMIT;

SELECT
    topic_name,
    partition_id,
    leader,
    leader_state,
    replica_count,
    in_sync_replicas
FROM partition_status
WHERE leader_state = 'OFFLINE'
ORDER BY topic_name, partition_id;

-- Recover the broker and restore normal health evaluation.
BEGIN;

UPDATE brokers
SET state = 'ONLINE'
WHERE broker_name = 'broker-1';

COMMIT;

SELECT *
FROM evaluate_topic_health('orders')
ORDER BY partition_number;
