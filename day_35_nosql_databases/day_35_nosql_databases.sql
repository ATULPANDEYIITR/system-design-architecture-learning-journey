-- PostgreSQL-compatible NoSQL data-modeling laboratory.
--
-- The schema intentionally represents four NoSQL families inside a relational
-- environment so their structures and access patterns can be inspected with
-- SQL. This is a teaching model, not an attempt to turn PostgreSQL into a
-- distributed NoSQL engine.
--
-- JSONB is used for document-style records, a row-key/column-value structure
-- models wide-column data, ordinary key/value rows model cache state, and
-- node/edge tables model a property graph.

DROP SCHEMA IF EXISTS nosql_lab CASCADE;
CREATE SCHEMA nosql_lab;

SET search_path = nosql_lab, public;

-- ============================================================================
-- Key-value model
-- ============================================================================

CREATE TABLE kv_store (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT kv_key_not_blank CHECK (length(trim(key)) > 0)
);

CREATE INDEX idx_kv_expiration
    ON kv_store (expires_at)
    WHERE expires_at IS NOT NULL;

INSERT INTO kv_store (key, value, expires_at)
VALUES
(
    'session:u-501',
    '{"user_id":"u-501","role":"customer","cart_id":"cart-901"}'::jsonb,
    CURRENT_TIMESTAMP + INTERVAL '1 hour'
),
(
    'feature:recommendations',
    '{"enabled":true}'::jsonb,
    NULL
),
(
    'login-attempts:u-501',
    '{"count":3}'::jsonb,
    CURRENT_TIMESTAMP + INTERVAL '15 minutes'
);

-- Exact-key lookup is the defining access pattern of the key-value model.
SELECT key, value
FROM kv_store
WHERE key = 'session:u-501';

-- Expired records can be identified without scanning the value payload.
SELECT key, expires_at
FROM kv_store
WHERE expires_at IS NOT NULL
  AND expires_at <= CURRENT_TIMESTAMP;

-- Atomic-style counter update is protected by a row-level transaction.
BEGIN;

UPDATE kv_store
SET value = jsonb_set(
    value,
    '{count}',
    to_jsonb(COALESCE((value->>'count')::integer, 0) + 1)
)
WHERE key = 'login-attempts:u-501';

COMMIT;

-- ============================================================================
-- Document model
-- ============================================================================

CREATE TABLE product_documents (
    document_id TEXT PRIMARY KEY,
    document JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT document_id_not_blank
        CHECK (length(trim(document_id)) > 0),

    CONSTRAINT document_has_id
        CHECK (document ? 'id'),

    CONSTRAINT document_has_name
        CHECK (document ? 'name'),

    CONSTRAINT document_has_category
        CHECK (document ? 'category'),

    CONSTRAINT document_has_price
        CHECK (document ? 'price'),

    CONSTRAINT document_price_numeric
        CHECK (
            jsonb_typeof(document->'price') = 'number'
            AND (document->>'price')::numeric >= 0
        ),

    CONSTRAINT document_tags_array
        CHECK (
            document ? 'tags'
            AND jsonb_typeof(document->'tags') = 'array'
        )
);

-- GIN is useful for containment and key-oriented JSONB queries.
CREATE INDEX idx_product_documents_jsonb
    ON product_documents
    USING GIN (document);

-- B-tree expression indexes support frequent scalar predicates.
CREATE INDEX idx_product_documents_category
    ON product_documents ((document->>'category'));

CREATE INDEX idx_product_documents_price
    ON product_documents (((document->>'price')::numeric));

INSERT INTO product_documents (document_id, document)
VALUES
(
    'p-100',
    '{
        "id":"p-100",
        "name":"Mechanical Keyboard",
        "category":"electronics",
        "price":89,
        "tags":["keyboard","office"],
        "inventory":{
            "warehouse_a":20,
            "warehouse_b":12
        }
    }'::jsonb
),
(
    'p-101',
    '{
        "id":"p-101",
        "name":"Wireless Mouse",
        "category":"electronics",
        "price":39,
        "tags":["mouse","wireless"],
        "inventory":{
            "warehouse_a":35,
            "warehouse_b":18
        }
    }'::jsonb
),
(
    'p-102',
    '{
        "id":"p-102",
        "name":"USB-C Dock",
        "category":"electronics",
        "price":129,
        "tags":["dock","usb-c"],
        "inventory":{
            "warehouse_a":7,
            "warehouse_b":10
        }
    }'::jsonb
);

-- Aggregate-oriented document retrieval.
SELECT document_id, document
FROM product_documents
WHERE document->>'category' = 'electronics';

-- Query a nested field without decomposing the complete document.
SELECT
    document_id,
    document->'inventory'->>'warehouse_a' AS warehouse_a_quantity
FROM product_documents
WHERE document_id = 'p-100';

-- JSON containment demonstrates document-specific predicates.
SELECT document_id, document->>'name' AS product_name
FROM product_documents
WHERE document @> '{"tags":["wireless"]}'::jsonb;

-- A controlled nested update changes only one document attribute.
UPDATE product_documents
SET
    document = jsonb_set(
        document,
        '{inventory,warehouse_a}',
        '18'::jsonb
    ),
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE document_id = 'p-100';

-- ============================================================================
-- Column-family model
-- ============================================================================

CREATE TABLE wide_column_rows (
    column_family TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    clustering_key TEXT NOT NULL,
    columns JSONB NOT NULL DEFAULT '{}'::jsonb,

    PRIMARY KEY (
        column_family,
        partition_key,
        clustering_key
    ),

    CONSTRAINT wide_columns_object
        CHECK (jsonb_typeof(columns) = 'object')
);

CREATE INDEX idx_wide_partition
    ON wide_column_rows (
        column_family,
        partition_key,
        clustering_key
    );

INSERT INTO wide_column_rows
(
    column_family,
    partition_key,
    clustering_key,
    columns
)
VALUES
(
    'activity_by_user_day',
    'u-501|2026-10-05',
    '00:01:00',
    '{"event_type":"login","channel":"mobile"}'::jsonb
),
(
    'activity_by_user_day',
    'u-501|2026-10-05',
    '00:05:00',
    '{"event_type":"view","channel":"mobile"}'::jsonb
),
(
    'activity_by_user_day',
    'u-501|2026-10-05',
    '00:09:00',
    '{"event_type":"purchase","channel":"web"}'::jsonb
),
(
    'activity_by_user_day',
    'u-502|2026-10-05',
    '00:03:00',
    '{"event_type":"login","channel":"web"}'::jsonb
);

-- The query follows the partition-first access pattern.
SELECT
    partition_key,
    clustering_key,
    columns
FROM wide_column_rows
WHERE column_family = 'activity_by_user_day'
  AND partition_key = 'u-501|2026-10-05'
ORDER BY clustering_key;

-- Projection retrieves only the logical columns needed by the application.
SELECT
    clustering_key AS event_time,
    columns->>'event_type' AS event_type,
    columns->>'channel' AS channel
FROM wide_column_rows
WHERE column_family = 'activity_by_user_day'
  AND partition_key = 'u-501|2026-10-05'
ORDER BY clustering_key;

-- This query intentionally exposes why an unbounded scan is undesirable for
-- a wide-column workload: it ignores the partition key.
EXPLAIN
SELECT *
FROM wide_column_rows
WHERE columns->>'event_type' = 'purchase';

-- ============================================================================
-- Graph model
-- ============================================================================

CREATE TABLE graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_label TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT graph_node_label_not_blank
        CHECK (length(trim(node_label)) > 0),

    CONSTRAINT graph_properties_object
        CHECK (jsonb_typeof(properties) = 'object')
);

CREATE TABLE graph_edges (
    edge_id BIGSERIAL PRIMARY KEY,
    source_node_id TEXT NOT NULL
        REFERENCES graph_nodes(node_id)
        ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    target_node_id TEXT NOT NULL
        REFERENCES graph_nodes(node_id)
        ON DELETE CASCADE,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT relationship_not_blank
        CHECK (length(trim(relationship)) > 0),

    CONSTRAINT graph_edge_properties_object
        CHECK (jsonb_typeof(properties) = 'object'),

    CONSTRAINT no_self_relationship
        CHECK (source_node_id <> target_node_id),

    CONSTRAINT unique_directed_relationship
        UNIQUE (
            source_node_id,
            relationship,
            target_node_id
        )
);

CREATE INDEX idx_graph_edges_source_relationship
    ON graph_edges (source_node_id, relationship);

CREATE INDEX idx_graph_edges_target_relationship
    ON graph_edges (target_node_id, relationship);

CREATE INDEX idx_graph_node_properties
    ON graph_nodes
    USING GIN (properties);

INSERT INTO graph_nodes (node_id, node_label, properties)
VALUES
('u-501', 'User', '{"name":"Asha"}'::jsonb),
('u-502', 'User', '{"name":"Rahul"}'::jsonb),
('u-503', 'User', '{"name":"Meera"}'::jsonb),
('p-100', 'Product', '{"name":"Keyboard"}'::jsonb),
('p-101', 'Product', '{"name":"Mouse"}'::jsonb),
('p-102', 'Product', '{"name":"USB-C Dock"}'::jsonb);

INSERT INTO graph_edges
(source_node_id, relationship, target_node_id, properties)
VALUES
('u-501', 'PURCHASED', 'p-100', '{}'),
('u-501', 'PURCHASED', 'p-101', '{}'),
('u-502', 'PURCHASED', 'p-100', '{}'),
('u-502', 'PURCHASED', 'p-102', '{}'),
('u-503', 'PURCHASED', 'p-102', '{}');

-- Direct relationship lookup.
SELECT
    e.source_node_id,
    e.relationship,
    e.target_node_id,
    n.properties->>'name' AS target_name
FROM graph_edges e
JOIN graph_nodes n
    ON n.node_id = e.target_node_id
WHERE e.source_node_id = 'u-501'
  AND e.relationship = 'PURCHASED';

-- Two-hop recommendation:
-- u-501 -> PURCHASED -> p-100
-- another user -> PURCHASED -> p-100
-- another user -> PURCHASED -> p-102
--
-- The CTEs expose graph traversal as relational joins.
WITH my_products AS (
    SELECT target_node_id AS product_id
    FROM graph_edges
    WHERE source_node_id = 'u-501'
      AND relationship = 'PURCHASED'
),
similar_users AS (
    SELECT DISTINCT e.source_node_id AS user_id
    FROM graph_edges e
    JOIN my_products mp
        ON mp.product_id = e.target_node_id
    WHERE e.relationship = 'PURCHASED'
      AND e.source_node_id <> 'u-501'
),
recommendations AS (
    SELECT DISTINCT e.target_node_id AS product_id
    FROM graph_edges e
    JOIN similar_users su
        ON su.user_id = e.source_node_id
    WHERE e.relationship = 'PURCHASED'
)
SELECT
    r.product_id,
    n.properties->>'name' AS product_name
FROM recommendations r
JOIN graph_nodes n
    ON n.node_id = r.product_id
WHERE r.product_id NOT IN (
    SELECT product_id
    FROM my_products
)
ORDER BY r.product_id;

-- ============================================================================
-- Integrity and failure examples
-- ============================================================================

-- The following statements are intentionally transactional demonstrations.
-- The invalid insert is rolled back so the complete script remains usable.

BEGIN;

INSERT INTO graph_edges
(
    source_node_id,
    relationship,
    target_node_id
)
VALUES
(
    'u-501',
    'PURCHASED',
    'p-102'
);

ROLLBACK;

-- PostgreSQL prevents an edge to a nonexistent node because of the foreign
-- keys. The invalid operation is isolated in a savepoint so the session can
-- continue.
BEGIN;

SAVEPOINT invalid_edge;

DO $$
BEGIN
    BEGIN
        INSERT INTO graph_edges
        (
            source_node_id,
            relationship,
            target_node_id
        )
        VALUES
        (
            'u-501',
            'PURCHASED',
            'p-does-not-exist'
        );
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE
                'Rejected graph edge because target node does not exist';
    END;
END
$$;

ROLLBACK;

-- ============================================================================
-- Cross-model operational view
-- ============================================================================

CREATE VIEW model_access_patterns AS
SELECT
    'key-value' AS model,
    'Exact key lookup, counters, session/cache state' AS dominant_access
UNION ALL
SELECT
    'document',
    'Aggregate retrieval and field-based document queries'
UNION ALL
SELECT
    'column-family',
    'Partition-key and clustering-key reads over high-volume rows'
UNION ALL
SELECT
    'graph',
    'Relationship traversal and multi-hop queries';

SELECT *
FROM model_access_patterns
ORDER BY model;

-- ============================================================================
-- Capacity and consistency observations
-- ============================================================================

COMMENT ON TABLE kv_store IS
'Key-value model. Application access is centered on the exact key.';

COMMENT ON TABLE product_documents IS
'Document model. JSONB stores an aggregate with potentially variable fields.';

COMMENT ON TABLE wide_column_rows IS
'Wide-column model. Partition and clustering keys define the intended read path.';

COMMENT ON TABLE graph_nodes IS
'Property-graph node model. Nodes represent entities.';

COMMENT ON TABLE graph_edges IS
'Property-graph edge model. Edges represent directed relationships.';

-- A production NoSQL architecture must choose consistency and durability
-- intentionally. PostgreSQL transactions provide ACID semantics here, while
-- actual NoSQL products have product-specific consistency, replication,
-- partitioning, conflict-resolution, and availability behavior.
SELECT
    'Key-value' AS model,
    'Exact-key state and counters' AS primary_strength,
    'Poor fit for arbitrary relational-style search' AS primary_tradeoff
UNION ALL
SELECT
    'Document',
    'Flexible aggregate schema',
    'Large embedded documents can create update and duplication costs'
UNION ALL
SELECT
    'Column-family',
    'High-volume predictable partition reads',
    'Poor partition design can create hotspots or expensive scans'
UNION ALL
SELECT
    'Graph',
    'Relationship-centric traversal',
    'Unbounded traversals can become computationally expensive';
