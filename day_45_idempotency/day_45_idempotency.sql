-- PostgreSQL-compatible demonstration of idempotency for an order API.
--
-- The database is responsible for:
--   * identifying a logical request by its idempotency key
--   * binding that key to a request fingerprint
--   * preventing conflicting reuse
--   * storing the original response
--   * protecting business records with relational constraints
--   * supporting atomic insertion and completion
--
-- The schema intentionally keeps idempotency records separate from orders.
-- This allows the API layer to replay the original response without creating
-- another order.

DROP SCHEMA IF EXISTS idempotency_demo CASCADE;
CREATE SCHEMA idempotency_demo;

SET search_path TO idempotency_demo;

CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_reference TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    currency CHAR(3) NOT NULL CHECK (currency = upper(currency)),
    order_status TEXT NOT NULL
        CHECK (order_status IN ('CREATED', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at DESC);

CREATE TABLE idempotency_requests (
    idempotency_key TEXT PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('PROCESSING', 'COMPLETED')),
    response_status INTEGER,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,

    CHECK (
        (state = 'PROCESSING'
            AND response_status IS NULL
            AND response_body IS NULL
            AND completed_at IS NULL)
        OR
        (state = 'COMPLETED'
            AND response_status IS NOT NULL
            AND response_body IS NOT NULL
            AND completed_at IS NOT NULL)
    )
);

CREATE INDEX idx_idempotency_expiration
    ON idempotency_requests (expires_at);

CREATE TABLE api_status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key TEXT NOT NULL
        REFERENCES idempotency_requests(idempotency_key),
    check_name TEXT NOT NULL,
    check_state TEXT NOT NULL
        CHECK (check_state IN ('PASS', 'FAIL', 'UNKNOWN')),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (idempotency_key, check_name)
);

INSERT INTO customers (
    external_reference,
    customer_name
)
VALUES
    ('cust-100', 'Acme Industrial'),
    ('cust-200', 'Northwind Research'),
    ('cust-300', 'Delta Logistics');

-- A stable fingerprint should normally be produced by the application from
-- canonical request data. The values below are deterministic demonstration
-- fingerprints rather than cryptographic hashes of arbitrary JSON text.
INSERT INTO idempotency_requests (
    idempotency_key,
    request_fingerprint,
    state,
    expires_at
)
VALUES
    (
        'order-key-001',
        'fingerprint-cust100-2500-INR',
        'PROCESSING',
        clock_timestamp() + interval '1 hour'
    ),
    (
        'order-key-002',
        'fingerprint-cust200-7800-INR',
        'PROCESSING',
        clock_timestamp() + interval '1 hour'
    );

INSERT INTO api_status_checks (
    idempotency_key,
    check_name,
    check_state
)
VALUES
    ('order-key-001', 'fraud-screen', 'PASS'),
    ('order-key-001', 'inventory', 'PASS'),
    ('order-key-002', 'fraud-screen', 'PASS'),
    ('order-key-002', 'inventory', 'FAIL');

-- The application should execute the following transaction after validation.
-- The idempotency row is locked so competing transactions cannot both decide
-- that they own the same logical request.

BEGIN;

SELECT
    idempotency_key,
    request_fingerprint,
    state,
    response_status,
    response_body
FROM idempotency_requests
WHERE idempotency_key = 'order-key-001'
FOR UPDATE;

-- Business-side effect.
INSERT INTO orders (
    customer_id,
    amount_cents,
    currency,
    order_status
)
SELECT
    customer_id,
    2500,
    'INR',
    'CONFIRMED'
FROM customers
WHERE external_reference = 'cust-100';

-- Store the response generated from the newly created order.
UPDATE idempotency_requests AS i
SET
    state = 'COMPLETED',
    response_status = 201,
    response_body = jsonb_build_object(
        'message', 'order created',
        'idempotency_key', i.idempotency_key,
        'customer_reference', 'cust-100',
        'amount_cents', 2500,
        'currency', 'INR'
    ),
    completed_at = clock_timestamp()
WHERE i.idempotency_key = 'order-key-001';

COMMIT;

-- A retry does not create another order. The stored response is returned.
SELECT
    idempotency_key,
    state,
    response_status,
    response_body
FROM idempotency_requests
WHERE idempotency_key = 'order-key-001';

-- This query confirms that only one business record exists for the request.
SELECT
    c.external_reference,
    COUNT(*) AS order_count,
    SUM(o.amount_cents) AS total_amount_cents
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE c.external_reference = 'cust-100'
GROUP BY c.external_reference;

-- A conflicting retry must compare the supplied request fingerprint with the
-- stored fingerprint. The application should reject this request with HTTP
-- 409 rather than silently treating it as the original operation.
SELECT
    idempotency_key,
    request_fingerprint,
    CASE
        WHEN request_fingerprint = 'fingerprint-cust100-2500-INR'
            THEN 'REPLAY_ALLOWED'
        ELSE 'CONFLICT'
    END AS retry_decision
FROM idempotency_requests
WHERE idempotency_key = 'order-key-001';

-- A processing request can be inspected without claiming that it succeeded.
SELECT
    i.idempotency_key,
    i.state,
    COUNT(*) FILTER (
        WHERE s.check_state = 'PASS'
    ) AS passed_checks,
    COUNT(*) FILTER (
        WHERE s.check_state = 'FAIL'
    ) AS failed_checks
FROM idempotency_requests AS i
LEFT JOIN api_status_checks AS s
    ON s.idempotency_key = i.idempotency_key
WHERE i.idempotency_key = 'order-key-002'
GROUP BY i.idempotency_key, i.state;

-- The following database-level test demonstrates a relational invariant:
-- a completed record cannot omit its response data.
--
-- It is intentionally executed inside a savepoint so the demonstration does
-- not terminate the remainder of the script.
BEGIN;

SAVEPOINT invalid_state_test;

UPDATE idempotency_requests
SET
    state = 'COMPLETED',
    response_status = NULL,
    response_body = NULL,
    completed_at = NULL
WHERE idempotency_key = 'order-key-001';

ROLLBACK TO SAVEPOINT invalid_state_test;
RELEASE SAVEPOINT invalid_state_test;

COMMIT;

-- Expired idempotency records can be removed after their retention period.
-- Retention must be long enough to cover the client's retry window.
DELETE FROM idempotency_requests
WHERE expires_at <= clock_timestamp();

-- Operational query: identify processing records that have remained active
-- longer than an application-defined threshold.
SELECT
    idempotency_key,
    created_at,
    clock_timestamp() - created_at AS processing_duration
FROM idempotency_requests
WHERE state = 'PROCESSING'
  AND created_at < clock_timestamp() - interval '5 minutes'
ORDER BY created_at;

-- Operational query: identify completed responses available for replay.
SELECT
    idempotency_key,
    response_status,
    completed_at,
    response_body
FROM idempotency_requests
WHERE state = 'COMPLETED'
ORDER BY completed_at DESC;
