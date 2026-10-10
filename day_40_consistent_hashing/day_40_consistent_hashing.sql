-- PostgreSQL 16+ compatible.
-- Consistent hashing data model for a distributed object-storage service.
--
-- The schema separates physical nodes, virtual ring positions, object keys,
-- ownership observations, membership state, and routing policy. Constraints
-- prevent duplicate virtual positions and invalid membership metadata.

DROP SCHEMA IF EXISTS consistent_hashing_demo CASCADE;
CREATE SCHEMA consistent_hashing_demo;
SET search_path TO consistent_hashing_demo;

CREATE TYPE node_state AS ENUM (
    'ACTIVE',
    'DRAINING',
    'REMOVED'
);

CREATE TABLE storage_nodes (
    node_id           BIGSERIAL PRIMARY KEY,
    node_name         TEXT NOT NULL UNIQUE,
    state             node_state NOT NULL DEFAULT 'ACTIVE',
    capacity_units    INTEGER NOT NULL CHECK (capacity_units > 0),
    virtual_node_count INTEGER NOT NULL CHECK (virtual_node_count > 0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(node_name)) > 0)
);

CREATE TABLE hash_ring (
    ring_position     NUMERIC(20, 0) PRIMARY KEY,
    node_id           BIGINT NOT NULL REFERENCES storage_nodes(node_id)
                       ON DELETE CASCADE,
    replica_index     INTEGER NOT NULL CHECK (replica_index >= 0),
    UNIQUE (node_id, replica_index)
);

CREATE TABLE objects (
    object_id         BIGSERIAL PRIMARY KEY,
    object_key        TEXT NOT NULL UNIQUE,
    hash_position     NUMERIC(20, 0) NOT NULL
                       CHECK (hash_position >= 0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(object_key)) > 0)
);

CREATE TABLE ownership_observations (
    observation_id    BIGSERIAL PRIMARY KEY,
    object_id         BIGINT NOT NULL REFERENCES objects(object_id)
                       ON DELETE CASCADE,
    node_id           BIGINT NOT NULL REFERENCES storage_nodes(node_id),
    observed_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    routing_epoch     BIGINT NOT NULL CHECK (routing_epoch > 0)
);

CREATE TABLE routing_epochs (
    routing_epoch     BIGSERIAL PRIMARY KEY,
    reason            TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(reason)) > 0)
);

CREATE INDEX idx_hash_ring_position
    ON hash_ring (ring_position);

CREATE INDEX idx_hash_ring_node
    ON hash_ring (node_id);

CREATE INDEX idx_objects_hash_position
    ON objects (hash_position);

CREATE INDEX idx_observations_epoch
    ON ownership_observations (routing_epoch);

CREATE INDEX idx_observations_node
    ON ownership_observations (node_id);

-- Physical nodes with different capacities. The large node receives more
-- virtual positions so its expected share of the ring is larger.
INSERT INTO storage_nodes
    (node_name, state, capacity_units, virtual_node_count)
VALUES
    ('storage-a', 'ACTIVE', 100, 64),
    ('storage-b', 'ACTIVE', 100, 64),
    ('storage-c', 'ACTIVE', 200, 128),
    ('storage-d', 'DRAINING', 100, 64);

-- The following positions are representative deterministic ring points.
-- Production systems would generate all positions in application or database
-- code using a stable hash algorithm. The schema itself enforces uniqueness.
INSERT INTO hash_ring (ring_position, node_id, replica_index)
SELECT 1000000000000000000, node_id, 0
FROM storage_nodes
WHERE node_name = 'storage-a';

INSERT INTO hash_ring (ring_position, node_id, replica_index)
SELECT 3000000000000000000, node_id, 1
FROM storage_nodes
WHERE node_name = 'storage-a';

INSERT INTO hash_ring (ring_position, node_id, replica_index)
SELECT 5000000000000000000, node_id, 0
FROM storage_nodes
WHERE node_name = 'storage-b';

INSERT INTO hash_ring (ring_position, node_id, replica_index)
SELECT 7000000000000000000, node_id, 1
FROM storage_nodes
WHERE node_name = 'storage-b';

INSERT INTO hash_ring (ring_position, node_id, replica_index)
SELECT 2000000000000000000, node_id, 0
FROM storage_nodes
WHERE node_name = 'storage-c';

INSERT INTO hash_ring (ring_position, node_id, replica_index)
SELECT 8000000000000000000, node_id, 1
FROM storage_nodes
WHERE node_name = 'storage-c';

-- Hash positions are supplied as precomputed 64-bit-space values.
INSERT INTO objects (object_key, hash_position)
VALUES
    ('tenant-001/object-0001', 1500000000000000000),
    ('tenant-001/object-0002', 2500000000000000000),
    ('tenant-002/object-0003', 4500000000000000000),
    ('tenant-003/object-0004', 6500000000000000000),
    ('tenant-004/object-0005', 9000000000000000000);

INSERT INTO routing_epochs (reason)
VALUES ('initial ring topology');

-- PostgreSQL's LEAD() identifies the clockwise interval ending at the next
-- virtual node. The final interval wraps around the ring boundary.
CREATE OR REPLACE VIEW active_ring_intervals AS
WITH ordered AS (
    SELECT
        hr.ring_position,
        hr.node_id,
        lead(hr.ring_position)
            OVER (ORDER BY hr.ring_position) AS next_position
    FROM hash_ring hr
    JOIN storage_nodes sn
      ON sn.node_id = hr.node_id
    WHERE sn.state = 'ACTIVE'
)
SELECT
    ring_position AS start_position,
    COALESCE(next_position, 10000000000000000000::NUMERIC)
        AS next_position,
    node_id
FROM ordered;

-- A direct clockwise lookup for each object. If no active virtual node is
-- greater than or equal to the object's position, the first active position
-- is selected, implementing wrap-around.
CREATE OR REPLACE VIEW object_primary_owners AS
SELECT
    o.object_id,
    o.object_key,
    o.hash_position,
    COALESCE(
        clockwise.node_id,
        first_active.node_id
    ) AS primary_node_id
FROM objects o
LEFT JOIN LATERAL (
    SELECT hr.node_id
    FROM hash_ring hr
    JOIN storage_nodes sn
      ON sn.node_id = hr.node_id
    WHERE sn.state = 'ACTIVE'
      AND hr.ring_position >= o.hash_position
    ORDER BY hr.ring_position
    LIMIT 1
) clockwise ON TRUE
LEFT JOIN LATERAL (
    SELECT hr.node_id
    FROM hash_ring hr
    JOIN storage_nodes sn
      ON sn.node_id = hr.node_id
    WHERE sn.state = 'ACTIVE'
    ORDER BY hr.ring_position
    LIMIT 1
) first_active ON TRUE;

-- Inspect primary ownership with physical node names.
SELECT
    opo.object_key,
    opo.hash_position,
    sn.node_name AS primary_node
FROM object_primary_owners opo
JOIN storage_nodes sn
  ON sn.node_id = opo.primary_node_id
ORDER BY opo.hash_position;

-- Distribution query. A healthy virtual-node layout should approximate the
-- capacity proportions over a sufficiently large key population.
SELECT
    sn.node_name,
    sn.capacity_units,
    COUNT(opo.object_id) AS object_count
FROM storage_nodes sn
LEFT JOIN object_primary_owners opo
  ON opo.primary_node_id = sn.node_id
WHERE sn.state = 'ACTIVE'
GROUP BY sn.node_id, sn.node_name, sn.capacity_units
ORDER BY sn.node_name;

-- Record an ownership epoch transactionally. The application can use the
-- returned epoch to correlate ownership changes with membership changes.
BEGIN;

INSERT INTO routing_epochs (reason)
VALUES ('storage-d remains draining; active ownership unchanged')
RETURNING routing_epoch;

COMMIT;

-- A draining node remains in metadata but is excluded from new ownership.
-- This allows an operational system to migrate its existing data before
-- changing its state to REMOVED.
UPDATE storage_nodes
SET state = 'REMOVED'
WHERE node_name = 'storage-d'
  AND state = 'DRAINING';

-- This query identifies virtual positions that belong to a removed node.
-- ON DELETE CASCADE is intentionally not used for state transitions, because
-- the ring history may need to remain auditable until a controlled rebuild.
SELECT
    sn.node_name,
    sn.state,
    COUNT(hr.ring_position) AS virtual_positions
FROM storage_nodes sn
LEFT JOIN hash_ring hr
  ON hr.node_id = sn.node_id
GROUP BY sn.node_id, sn.node_name, sn.state
ORDER BY sn.node_name;

-- Integrity test: duplicate (node, replica) combinations are rejected.
-- The statement below is intentionally commented out because it would fail
-- the UNIQUE(node_id, replica_index) constraint.
--
-- INSERT INTO hash_ring (ring_position, node_id, replica_index)
-- SELECT 9000000000000000001, node_id, 0
-- FROM storage_nodes
-- WHERE node_name = 'storage-a';

-- Integrity test: a negative capacity is rejected by CHECK constraints.
--
-- INSERT INTO storage_nodes
--     (node_name, capacity_units, virtual_node_count)
-- VALUES
--     ('invalid-node', -1, 32);

-- Find the objects whose owner changed after a new ring epoch has been
-- materialized in ownership_observations.
WITH latest AS (
    SELECT
        oo.object_id,
        oo.node_id,
        row_number() OVER (
            PARTITION BY oo.object_id
            ORDER BY oo.routing_epoch DESC
        ) AS rank_in_history
    FROM ownership_observations oo
)
SELECT
    o.object_key,
    old_node.node_name AS latest_recorded_owner,
    current_node.node_name AS current_calculated_owner
FROM latest l
JOIN objects o
  ON o.object_id = l.object_id
JOIN storage_nodes old_node
  ON old_node.node_id = l.node_id
JOIN object_primary_owners current_owner
  ON current_owner.object_id = o.object_id
JOIN storage_nodes current_node
  ON current_node.node_id = current_owner.primary_node_id
WHERE l.rank_in_history = 1
  AND l.node_id <> current_owner.primary_node_id;

-- Capacity-oriented governance report. Virtual-node count is compared with
-- declared capacity so operators can identify members whose ring share does
-- not reflect their intended capacity.
SELECT
    node_name,
    capacity_units,
    virtual_node_count,
    ROUND(
        virtual_node_count::NUMERIC
        / NULLIF(
            SUM(virtual_node_count)
                OVER (WHERE state = 'ACTIVE'),
            0
        ) * 100,
        2
    ) AS expected_ring_share_percent
FROM storage_nodes
WHERE state = 'ACTIVE'
ORDER BY virtual_node_count DESC;
