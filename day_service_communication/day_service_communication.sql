-- ============================================================
-- SERVICE COMMUNICATION: REST, gRPC, AND MESSAGING
-- PostgreSQL 15+
--
-- Enterprise scenario:
-- Product and order services communicate through:
-- 1. REST endpoint contracts and HTTP request records.
-- 2. Typed gRPC-style RPC contracts and invocation records.
-- 3. Asynchronous messaging with an outbox, inbox,
--    acknowledgements, retries, and dead-letter processing.
--
-- The database models communication contracts and operational
-- state. It does not implement HTTP or HTTP/2 transport.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS service_comm;

SET search_path TO service_comm, public;

-- ============================================================
-- 1. Enumerations
-- ============================================================

CREATE TYPE communication_protocol AS ENUM (
    'REST',
    'GRPC',
    'MESSAGING'
);

CREATE TYPE service_status AS ENUM (
    'ACTIVE',
    'DEGRADED',
    'OFFLINE',
    'MAINTENANCE'
);

CREATE TYPE request_status AS ENUM (
    'RECEIVED',
    'PROCESSING',
    'SUCCEEDED',
    'FAILED',
    'TIMED_OUT'
);

CREATE TYPE rpc_status AS ENUM (
    'OK',
    'INVALID_ARGUMENT',
    'NOT_FOUND',
    'UNAVAILABLE',
    'DEADLINE_EXCEEDED',
    'INTERNAL'
);

CREATE TYPE message_status AS ENUM (
    'PENDING',
    'PROCESSING',
    'ACKNOWLEDGED',
    'RETRY',
    'DEAD_LETTERED'
);

-- ============================================================
-- 2. Services
-- ============================================================

CREATE TABLE services (
    service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    status service_status NOT NULL DEFAULT 'ACTIVE',
    base_url TEXT,
    authentication_required BOOLEAN NOT NULL DEFAULT TRUE,
    encryption_required BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_service_url CHECK (
        base_url IS NULL OR base_url ~ '^https?://'
    )
);

INSERT INTO services (
    service_name,
    description,
    base_url
)
VALUES
(
    'product-service',
    'Owns product catalog and product resources',
    'https://products.internal'
),
(
    'order-service',
    'Coordinates order processing',
    'https://orders.internal'
),
(
    'inventory-service',
    'Manages stock reservations',
    'https://inventory.internal'
),
(
    'payment-service',
    'Processes payment requests',
    'https://payments.internal'
);

-- ============================================================
-- 3. REST Endpoint Contracts
-- ============================================================

CREATE TABLE rest_endpoints (
    endpoint_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL REFERENCES services(service_id),
    resource_path VARCHAR(300) NOT NULL,
    http_method VARCHAR(10) NOT NULL,
    api_version VARCHAR(20) NOT NULL,
    request_content_type VARCHAR(100) NOT NULL
        DEFAULT 'application/json',
    response_content_type VARCHAR(100) NOT NULL
        DEFAULT 'application/json',
    timeout_ms INTEGER NOT NULL DEFAULT 3000,
    maximum_payload_bytes INTEGER NOT NULL DEFAULT 16384,
    idempotent BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_http_method CHECK (
        http_method IN (
            'GET', 'POST', 'PUT', 'PATCH', 'DELETE'
        )
    ),

    CONSTRAINT valid_timeout CHECK (timeout_ms > 0),

    CONSTRAINT valid_payload_size CHECK (
        maximum_payload_bytes BETWEEN 1 AND 10485760
    ),

    CONSTRAINT unique_rest_contract UNIQUE (
        service_id,
        resource_path,
        http_method,
        api_version
    )
);

INSERT INTO rest_endpoints (
    service_id,
    resource_path,
    http_method,
    api_version,
    idempotent
)
SELECT
    service_id,
    '/products',
    'GET',
    'v1',
    TRUE
FROM services
WHERE service_name = 'product-service';

INSERT INTO rest_endpoints (
    service_id,
    resource_path,
    http_method,
    api_version,
    idempotent
)
SELECT
    service_id,
    '/products',
    'POST',
    'v1',
    FALSE
FROM services
WHERE service_name = 'product-service';

INSERT INTO rest_endpoints (
    service_id,
    resource_path,
    http_method,
    api_version,
    idempotent
)
SELECT
    service_id,
    '/orders',
    'POST',
    'v1',
    FALSE
FROM services
WHERE service_name = 'order-service';

-- ============================================================
-- 4. REST Request and Response Records
-- ============================================================

CREATE TABLE rest_requests (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id BIGINT NOT NULL
        REFERENCES rest_endpoints(endpoint_id),
    correlation_id UUID NOT NULL,
    idempotency_key VARCHAR(200),
    request_status request_status NOT NULL DEFAULT 'RECEIVED',
    http_status INTEGER,
    request_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    response_payload JSONB,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    CONSTRAINT valid_http_status CHECK (
        http_status IS NULL OR http_status BETWEEN 100 AND 599
    ),

    CONSTRAINT valid_latency CHECK (
        latency_ms IS NULL OR latency_ms >= 0
    ),

    CONSTRAINT valid_completion CHECK (
        completed_at IS NULL OR completed_at >= created_at
    )
);

CREATE UNIQUE INDEX unique_rest_idempotency
ON rest_requests(endpoint_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX idx_rest_requests_correlation
ON rest_requests(correlation_id);

CREATE INDEX idx_rest_requests_created
ON rest_requests(created_at DESC);

CREATE INDEX idx_rest_requests_failures
ON rest_requests(created_at DESC)
WHERE request_status IN ('FAILED', 'TIMED_OUT');

-- ============================================================
-- 5. gRPC Service and Method Contracts
-- ============================================================

CREATE TABLE grpc_services (
    grpc_service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_id BIGINT NOT NULL REFERENCES services(service_id),
    package_name VARCHAR(200) NOT NULL,
    service_name VARCHAR(150) NOT NULL,
    protocol_version VARCHAR(30) NOT NULL,
    protobuf_schema JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_grpc_service UNIQUE (
        service_id,
        package_name,
        service_name,
        protocol_version
    )
);

CREATE TABLE grpc_methods (
    method_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    grpc_service_id BIGINT NOT NULL
        REFERENCES grpc_services(grpc_service_id),
    method_name VARCHAR(150) NOT NULL,
    request_message_type VARCHAR(200) NOT NULL,
    response_message_type VARCHAR(200) NOT NULL,
    client_streaming BOOLEAN NOT NULL DEFAULT FALSE,
    server_streaming BOOLEAN NOT NULL DEFAULT FALSE,
    deadline_ms INTEGER NOT NULL DEFAULT 2000,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT valid_grpc_deadline CHECK (deadline_ms > 0),

    CONSTRAINT unique_grpc_method UNIQUE (
        grpc_service_id,
        method_name
    )
);

INSERT INTO grpc_services (
    service_id,
    package_name,
    service_name,
    protocol_version
)
SELECT
    service_id,
    'catalog.v1',
    'ProductService',
    'v1'
FROM services
WHERE service_name = 'product-service';

INSERT INTO grpc_methods (
    grpc_service_id,
    method_name,
    request_message_type,
    response_message_type,
    deadline_ms
)
SELECT
    grpc_service_id,
    'GetProduct',
    'GetProductRequest',
    'GetProductResponse',
    2000
FROM grpc_services
WHERE service_name = 'ProductService';

-- ============================================================
-- 6. RPC Invocation Records
-- ============================================================

CREATE TABLE grpc_invocations (
    invocation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    method_id BIGINT NOT NULL REFERENCES grpc_methods(method_id),
    correlation_id UUID NOT NULL,
    rpc_status rpc_status NOT NULL DEFAULT 'OK',
    request_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    response_payload JSONB,
    deadline_ms INTEGER NOT NULL,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_rpc_deadline CHECK (deadline_ms > 0),

    CONSTRAINT valid_rpc_latency CHECK (
        latency_ms IS NULL OR latency_ms >= 0
    )
);

CREATE INDEX idx_grpc_invocations_status
ON grpc_invocations(rpc_status, created_at DESC);

CREATE INDEX idx_grpc_invocations_correlation
ON grpc_invocations(correlation_id);

-- ============================================================
-- 7. Messaging Topics and Subscriptions
-- ============================================================

CREATE TABLE message_topics (
    topic_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_name VARCHAR(200) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    retention_hours INTEGER NOT NULL DEFAULT 72,
    maximum_attempts INTEGER NOT NULL DEFAULT 3,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_retention CHECK (retention_hours > 0),

    CONSTRAINT valid_attempts CHECK (
        maximum_attempts BETWEEN 0 AND 100
    )
);

INSERT INTO message_topics (
    topic_name,
    description,
    maximum_attempts
)
VALUES
(
    'product.events',
    'Product lifecycle events',
    3
),
(
    'order.events',
    'Order lifecycle events',
    5
),
(
    'inventory.events',
    'Inventory reservation events',
    3
),
(
    'payment.events',
    'Payment lifecycle events',
    5
);

CREATE TABLE message_subscriptions (
    subscription_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic_id BIGINT NOT NULL REFERENCES message_topics(topic_id),
    consumer_service_id BIGINT NOT NULL
        REFERENCES services(service_id),
    subscription_name VARCHAR(150) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_topic_consumer UNIQUE (
        topic_id,
        consumer_service_id,
        subscription_name
    )
);

INSERT INTO message_subscriptions (
    topic_id,
    consumer_service_id,
    subscription_name
)
SELECT
    t.topic_id,
    s.service_id,
    'inventory-product-consumer'
FROM message_topics t
CROSS JOIN services s
WHERE t.topic_name = 'product.events'
AND s.service_name = 'inventory-service';

-- ============================================================
-- 8. Transactional Outbox
-- ============================================================

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id BIGINT NOT NULL REFERENCES message_topics(topic_id),
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    event_version INTEGER NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    correlation_id UUID NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_event_version CHECK (event_version > 0),

    CONSTRAINT valid_publication_time CHECK (
        (published = FALSE AND published_at IS NULL)
        OR
        (published = TRUE AND published_at IS NOT NULL)
    )
);

CREATE INDEX idx_outbox_pending
ON outbox_events(created_at)
WHERE published = FALSE;

CREATE INDEX idx_outbox_aggregate
ON outbox_events(aggregate_type, aggregate_id);

-- ============================================================
-- 9. Message Delivery Queue
-- ============================================================

CREATE TABLE messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id BIGINT NOT NULL REFERENCES message_topics(topic_id),
    event_id UUID REFERENCES outbox_events(event_id),
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    correlation_id UUID NOT NULL,
    message_status message_status NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    maximum_attempts INTEGER NOT NULL,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_message_attempts CHECK (
        attempts >= 0 AND maximum_attempts >= 0
    ),

    CONSTRAINT valid_acknowledgement CHECK (
        message_status <> 'ACKNOWLEDGED'
        OR acknowledged_at IS NOT NULL
    )
);

CREATE INDEX idx_messages_pending
ON messages(topic_id, available_at)
WHERE message_status IN ('PENDING', 'RETRY');

CREATE INDEX idx_messages_correlation
ON messages(correlation_id);

CREATE INDEX idx_messages_dead_letters
ON messages(created_at DESC)
WHERE message_status = 'DEAD_LETTERED';

-- ============================================================
-- 10. Consumer Inbox for Idempotency
-- ============================================================

CREATE TABLE consumer_inbox (
    inbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    consumer_service_id BIGINT NOT NULL
        REFERENCES services(service_id),
    message_id UUID NOT NULL REFERENCES messages(message_id),
    processing_status VARCHAR(20) NOT NULL DEFAULT 'PROCESSED',
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_consumer_message UNIQUE (
        consumer_service_id,
        message_id
    ),

    CONSTRAINT valid_inbox_status CHECK (
        processing_status IN ('PROCESSING', 'PROCESSED', 'FAILED')
    )
);

CREATE INDEX idx_inbox_processed
ON consumer_inbox(consumer_service_id, processed_at DESC);

-- ============================================================
-- 11. Communication Audit
-- ============================================================

CREATE TABLE communication_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    protocol communication_protocol NOT NULL,
    source_service_id BIGINT NOT NULL REFERENCES services(service_id),
    destination_service_id BIGINT NOT NULL REFERENCES services(service_id),
    correlation_id UUID NOT NULL,
    operation_name VARCHAR(200) NOT NULL,
    success BOOLEAN NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_category VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_audit_duration CHECK (duration_ms >= 0)
);

CREATE INDEX idx_audit_protocol
ON communication_audit(protocol, created_at DESC);

CREATE INDEX idx_audit_correlation
ON communication_audit(correlation_id);

-- ============================================================
-- 12. Sample REST Requests
-- ============================================================

INSERT INTO rest_requests (
    endpoint_id,
    correlation_id,
    request_status,
    http_status,
    request_payload,
    response_payload,
    latency_ms,
    completed_at
)
SELECT
    endpoint_id,
    gen_random_uuid(),
    'SUCCEEDED',
    200,
    '{"product_id":101}'::JSONB,
    '{"id":101,"name":"Laptop","price":75000}'::JSONB,
    18,
    NOW()
FROM rest_endpoints
WHERE resource_path = '/products'
AND http_method = 'GET';

INSERT INTO rest_requests (
    endpoint_id,
    correlation_id,
    request_status,
    http_status,
    request_payload,
    response_payload,
    latency_ms,
    completed_at
)
SELECT
    endpoint_id,
    gen_random_uuid(),
    'FAILED',
    400,
    '{"price":-10}'::JSONB,
    '{"error":"Price must be positive"}'::JSONB,
    5,
    NOW()
FROM rest_endpoints
WHERE resource_path = '/products'
AND http_method = 'POST';

-- ============================================================
-- 13. Sample gRPC Invocations
-- ============================================================

INSERT INTO grpc_invocations (
    method_id,
    correlation_id,
    rpc_status,
    request_payload,
    response_payload,
    deadline_ms,
    latency_ms
)
SELECT
    method_id,
    gen_random_uuid(),
    'OK',
    '{"product_id":101}'::JSONB,
    '{"product_id":101,"name":"Laptop"}'::JSONB,
    2000,
    12
FROM grpc_methods
WHERE method_name = 'GetProduct';

INSERT INTO grpc_invocations (
    method_id,
    correlation_id,
    rpc_status,
    request_payload,
    deadline_ms,
    latency_ms,
    error_message
)
SELECT
    method_id,
    gen_random_uuid(),
    'DEADLINE_EXCEEDED',
    '{"product_id":102}'::JSONB,
    2000,
    2000,
    'Inventory dependency exceeded deadline'
FROM grpc_methods
WHERE method_name = 'GetProduct';

-- ============================================================
-- 14. Sample Outbox Events
-- ============================================================

INSERT INTO outbox_events (
    topic_id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    correlation_id
)
SELECT
    topic_id,
    'Product',
    '101',
    'ProductCreated',
    '{"product_id":101,"name":"Laptop","price":75000}'::JSONB,
    gen_random_uuid()
FROM message_topics
WHERE topic_name = 'product.events';

INSERT INTO outbox_events (
    topic_id,
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    correlation_id,
    published,
    published_at
)
SELECT
    topic_id,
    'Order',
    '5001',
    'OrderCreated',
    '{"order_id":5001,"product_id":101,"quantity":2}'::JSONB,
    gen_random_uuid(),
    TRUE,
    NOW()
FROM message_topics
WHERE topic_name = 'order.events';

-- ============================================================
-- 15. Outbox Dispatcher
-- ============================================================

CREATE OR REPLACE PROCEDURE dispatch_outbox(
    p_batch_size INTEGER DEFAULT 100
)
LANGUAGE plpgsql
AS $$
DECLARE
    event_record RECORD;
    new_message_id UUID;
BEGIN
    IF p_batch_size <= 0 OR p_batch_size > 10000 THEN
        RAISE EXCEPTION 'Invalid batch size';
    END IF;

    -- SKIP LOCKED permits multiple dispatcher workers
    -- without selecting the same pending outbox records.
    FOR event_record IN
        SELECT
            o.*,
            t.maximum_attempts
        FROM outbox_events o
        JOIN message_topics t
            ON t.topic_id = o.topic_id
        WHERE o.published = FALSE
        ORDER BY o.created_at
        LIMIT p_batch_size
        FOR UPDATE OF o SKIP LOCKED
    LOOP
        INSERT INTO messages (
            topic_id,
            event_id,
            event_type,
            payload,
            correlation_id,
            maximum_attempts
        )
        VALUES (
            event_record.topic_id,
            event_record.event_id,
            event_record.event_type,
            event_record.payload,
            event_record.correlation_id,
            event_record.maximum_attempts
        )
        RETURNING message_id INTO new_message_id;

        UPDATE outbox_events
        SET published = TRUE,
            published_at = NOW()
        WHERE event_id = event_record.event_id;
    END LOOP;
END;
$$;

-- ============================================================
-- 16. Message Acknowledgement
-- ============================================================

CREATE OR REPLACE FUNCTION acknowledge_message(
    p_message_id UUID,
    p_consumer_service_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    inserted_count INTEGER;
BEGIN
    INSERT INTO consumer_inbox (
        consumer_service_id,
        message_id,
        processing_status
    )
    VALUES (
        p_consumer_service_id,
        p_message_id,
        'PROCESSED'
    )
    ON CONFLICT (consumer_service_id, message_id)
    DO NOTHING;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;

    IF inserted_count = 0 THEN
        RETURN FALSE;
    END IF;

    UPDATE messages
    SET message_status = 'ACKNOWLEDGED',
        acknowledged_at = NOW()
    WHERE message_id = p_message_id
      AND message_status IN ('PENDING', 'PROCESSING', 'RETRY');

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Message is not eligible for acknowledgement';
    END IF;

    RETURN TRUE;
END;
$$;

-- ============================================================
-- 17. Failed Message Retry and Dead-Letter Processing
-- ============================================================

CREATE OR REPLACE FUNCTION fail_message(
    p_message_id UUID,
    p_error TEXT,
    p_retry_delay_seconds INTEGER DEFAULT 30
)
RETURNS message_status
LANGUAGE plpgsql
AS $$
DECLARE
    current_message messages%ROWTYPE;
    new_status message_status;
BEGIN
    IF p_retry_delay_seconds < 0 THEN
        RAISE EXCEPTION 'Retry delay cannot be negative';
    END IF;

    SELECT *
    INTO current_message
    FROM messages
    WHERE message_id = p_message_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Message not found';
    END IF;

    IF current_message.message_status = 'ACKNOWLEDGED'
       OR current_message.message_status = 'DEAD_LETTERED' THEN
        RAISE EXCEPTION 'Terminal message cannot be retried';
    END IF;

    IF current_message.attempts + 1 >
       current_message.maximum_attempts THEN

        new_status := 'DEAD_LETTERED';

    ELSE
        new_status := 'RETRY';
    END IF;

    UPDATE messages
    SET attempts = attempts + 1,
        message_status = new_status,
        last_error = LEFT(p_error, 2000),
        available_at = CASE
            WHEN new_status = 'RETRY'
            THEN NOW() + make_interval(
                secs => p_retry_delay_seconds
            )
            ELSE available_at
        END
    WHERE message_id = p_message_id;

    RETURN new_status;
END;
$$;

-- ============================================================
-- 18. Service Communication Health View
-- ============================================================

CREATE OR REPLACE VIEW service_health AS
SELECT
    service_id,
    service_name,
    status,
    authentication_required,
    encryption_required,
    updated_at
FROM services;

-- ============================================================
-- 19. Communication Performance Report
-- ============================================================

CREATE OR REPLACE VIEW communication_performance AS

SELECT
    'REST'::TEXT AS protocol,
    COUNT(*) AS total_calls,
    COUNT(*) FILTER (
        WHERE request_status = 'SUCCEEDED'
    ) AS successful_calls,
    COUNT(*) FILTER (
        WHERE request_status IN ('FAILED', 'TIMED_OUT')
    ) AS failed_calls,
    ROUND(AVG(latency_ms)::NUMERIC, 2) AS average_latency_ms
FROM rest_requests

UNION ALL

SELECT
    'gRPC',
    COUNT(*),
    COUNT(*) FILTER (
        WHERE rpc_status = 'OK'
    ),
    COUNT(*) FILTER (
        WHERE rpc_status <> 'OK'
    ),
    ROUND(AVG(latency_ms)::NUMERIC, 2)
FROM grpc_invocations;

-- ============================================================
-- 20. Validation Queries
-- ============================================================

-- A. REST endpoint contracts.
SELECT
    s.service_name,
    e.http_method,
    e.resource_path,
    e.api_version,
    e.timeout_ms,
    e.idempotent
FROM rest_endpoints e
JOIN services s USING (service_id)
ORDER BY s.service_name, e.resource_path;

-- B. gRPC method contracts.
SELECT
    gs.package_name,
    gs.service_name,
    gm.method_name,
    gm.request_message_type,
    gm.response_message_type,
    gm.deadline_ms
FROM grpc_methods gm
JOIN grpc_services gs USING (grpc_service_id);

-- C. Service availability.
SELECT *
FROM service_health
ORDER BY service_name;

-- D. REST request failures.
SELECT
    request_id,
    http_status,
    request_status,
    error_message,
    created_at
FROM rest_requests
WHERE request_status <> 'SUCCEEDED'
ORDER BY created_at DESC;

-- E. RPC status distribution.
SELECT
    rpc_status,
    COUNT(*) AS invocation_count,
    ROUND(AVG(latency_ms)::NUMERIC, 2) AS avg_latency
FROM grpc_invocations
GROUP BY rpc_status
ORDER BY invocation_count DESC;

-- F. Pending outbox records.
SELECT
    event_id,
    aggregate_type,
    aggregate_id,
    event_type,
    created_at
FROM outbox_events
WHERE published = FALSE
ORDER BY created_at;

-- G. Queue workload.
SELECT
    t.topic_name,
    m.message_status,
    COUNT(*) AS message_count
FROM messages m
JOIN message_topics t USING (topic_id)
GROUP BY t.topic_name, m.message_status
ORDER BY t.topic_name, m.message_status;

-- H. Consumer processing activity.
SELECT
    s.service_name,
    COUNT(*) AS processed_messages,
    MAX(i.processed_at) AS latest_processing
FROM consumer_inbox i
JOIN services s USING (service_id)
GROUP BY s.service_name;

-- I. Protocol performance.
SELECT *
FROM communication_performance
ORDER BY protocol;

-- ============================================================
-- 21. Eligibility Determination
-- ============================================================

-- Services are eligible for communication only when active
-- and both authentication and encryption are mandatory.
SELECT
    service_name,
    status,
    (
        status = 'ACTIVE'
        AND authentication_required
        AND encryption_required
    ) AS communication_eligible
FROM services
ORDER BY service_name;

-- ============================================================
-- 22. CTE-Based Message Processing Report
-- ============================================================

WITH topic_metrics AS (
    SELECT
        topic_id,
        COUNT(*) AS total_messages,
        COUNT(*) FILTER (
            WHERE message_status = 'ACKNOWLEDGED'
        ) AS acknowledged,
        COUNT(*) FILTER (
            WHERE message_status = 'RETRY'
        ) AS retrying,
        COUNT(*) FILTER (
            WHERE message_status = 'DEAD_LETTERED'
        ) AS dead_lettered
    FROM messages
    GROUP BY topic_id
)
SELECT
    t.topic_name,
    COALESCE(m.total_messages, 0) AS total_messages,
    COALESCE(m.acknowledged, 0) AS acknowledged,
    COALESCE(m.retrying, 0) AS retrying,
    COALESCE(m.dead_lettered, 0) AS dead_lettered
FROM message_topics t
LEFT JOIN topic_metrics m USING (topic_id)
ORDER BY t.topic_name;

-- ============================================================
-- 23. Transactional Demonstration
-- ============================================================

-- A production application should insert business data and
-- its outbox event inside the same database transaction.
--
-- This example creates an outbox event and then dispatches it.
-- Both operations are committed together.

DO $$
DECLARE
    selected_topic BIGINT;
BEGIN
    SELECT topic_id
    INTO selected_topic
    FROM message_topics
    WHERE topic_name = 'order.events';

    INSERT INTO outbox_events (
        topic_id,
        aggregate_type,
        aggregate_id,
        event_type,
        payload,
        correlation_id
    )
    VALUES (
        selected_topic,
        'Order',
        '5002',
        'OrderCreated',
        '{
            "order_id": 5002,
            "product_id": 101,
            "quantity": 3
        }'::JSONB,
        gen_random_uuid()
    );
END;
$$;

CALL dispatch_outbox(100);

COMMIT;

-- ============================================================
-- 24. Final Operational Reports
-- ============================================================

-- Message delivery failures.
SELECT
    message_id,
    event_type,
    attempts,
    maximum_attempts,
    last_error,
    message_status
FROM messages
WHERE message_status IN ('RETRY', 'DEAD_LETTERED')
ORDER BY created_at DESC;

-- Correlated communication trace.
SELECT
    protocol,
    source.service_name AS source_service,
    destination.service_name AS destination_service,
    operation_name,
    success,
    duration_ms,
    correlation_id,
    created_at
FROM communication_audit a
JOIN services source
    ON source.service_id = a.source_service_id
JOIN services destination
    ON destination.service_id = a.destination_service_id
ORDER BY a.created_at DESC;

-- Database objects created:
-- services
-- rest_endpoints
-- rest_requests
-- grpc_services
-- grpc_methods
-- grpc_invocations
-- message_topics
-- message_subscriptions
-- outbox_events
-- messages
-- consumer_inbox
-- communication_audit
--
-- Procedures:
-- dispatch_outbox
--
-- Functions:
-- acknowledge_message
-- fail_message
--
-- Views:
-- service_health
-- communication_performance
