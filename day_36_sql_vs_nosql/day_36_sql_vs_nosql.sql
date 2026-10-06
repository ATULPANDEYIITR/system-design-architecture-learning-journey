-- SQL vs NoSQL: PostgreSQL relational model and workload laboratory.
--
-- PostgreSQL-compatible SQL.
--
-- The relational schema deliberately models entities that a document database
-- could instead store as one aggregate. Constraints demonstrate database-level
-- integrity that is central to relational systems.

DROP SCHEMA IF EXISTS database_comparison CASCADE;
CREATE SCHEMA database_comparison;
SET search_path TO database_comparison;

CREATE TYPE order_status AS ENUM (
    'PENDING',
    'PAID',
    'CANCELLED'
);

CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status order_status NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
);

CREATE INDEX idx_orders_customer
    ON orders(customer_id);

CREATE INDEX idx_orders_status_created
    ON orders(status, created_at);

CREATE INDEX idx_order_items_order
    ON order_items(order_id);

CREATE INDEX idx_products_category
    ON products(category);

CREATE INDEX idx_products_attributes
    ON products USING GIN(attributes);

INSERT INTO customers (full_name, email)
VALUES
    ('Asha Rao', 'asha@example.com'),
    ('Rohan Mehta', 'rohan@example.com');

INSERT INTO products (
    product_name,
    category,
    price,
    attributes
)
VALUES
    (
        'Laptop',
        'Computing',
        1200.00,
        '{"ram_gb":16,"cpu":"x86","screen_inches":14}'::jsonb
    ),
    (
        'Keyboard',
        'Accessories',
        80.00,
        '{"layout":"US","wireless":true}'::jsonb
    ),
    (
        'Monitor',
        'Computing',
        300.00,
        '{"resolution":"4K","screen_inches":27}'::jsonb
    );

INSERT INTO orders (customer_id, status)
SELECT customer_id, 'PAID'
FROM customers
WHERE email = 'asha@example.com';

INSERT INTO orders (customer_id, status)
SELECT customer_id, 'PENDING'
FROM customers
WHERE email = 'rohan@example.com';

INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
SELECT
    o.order_id,
    p.product_id,
    1,
    p.price
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
JOIN products p
    ON p.product_name = 'Laptop'
WHERE c.email = 'asha@example.com';

INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
SELECT
    o.order_id,
    p.product_id,
    2,
    p.price
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
JOIN products p
    ON p.product_name = 'Keyboard'
WHERE c.email = 'asha@example.com';

CREATE VIEW order_totals AS
SELECT
    o.order_id,
    o.status,
    c.full_name,
    c.email,
    COALESCE(
        SUM(
            oi.quantity * oi.unit_price
        ),
        0
    ) AS total
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
LEFT JOIN order_items oi
    ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.status,
    c.full_name,
    c.email;

-- A normalized relational query can reconstruct the complete order aggregate
-- through joins. The schema avoids repeating customer data in every order.
SELECT
    ot.order_id,
    ot.full_name,
    ot.status,
    ot.total
FROM order_totals ot
ORDER BY ot.order_id;

-- JSONB demonstrates that SQL and NoSQL are not mutually exclusive at the
-- feature level. PostgreSQL can store semi-structured attributes while still
-- retaining relational constraints for core entities.
SELECT
    product_name,
    attributes ->> 'resolution' AS resolution,
    attributes ->> 'ram_gb' AS ram_gb
FROM products
WHERE attributes ? 'resolution'
   OR attributes ? 'ram_gb';

-- The following query represents an access pattern where an index on category
-- and a GIN index on JSONB can help the planner select efficient access paths.
SELECT
    product_id,
    product_name,
    price
FROM products
WHERE category = 'Computing'
  AND attributes @> '{"screen_inches":27}'::jsonb;

-- Transactional behavior: the inventory reservation and order creation are
-- committed together. If either statement fails, PostgreSQL can roll back the
-- entire transaction.
BEGIN;

WITH selected_customer AS (
    SELECT customer_id
    FROM customers
    WHERE email = 'rohan@example.com'
),
new_order AS (
    INSERT INTO orders (customer_id, status)
    SELECT customer_id, 'PENDING'
    FROM selected_customer
    RETURNING order_id
)
INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
SELECT
    new_order.order_id,
    products.product_id,
    1,
    products.price
FROM new_order
CROSS JOIN products
WHERE products.product_name = 'Monitor';

COMMIT;

-- Database-level rejection example. The statement is intentionally wrapped in
-- a savepoint so the rest of the session remains usable. The foreign key
-- prevents an order item from referencing a nonexistent product.
BEGIN;

SAVEPOINT invalid_reference;

DO $$
BEGIN
    BEGIN
        INSERT INTO order_items (
            order_id,
            product_id,
            quantity,
            unit_price
        )
        VALUES (
            (SELECT MIN(order_id) FROM orders),
            999999,
            1,
            10.00
        );
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE
                'Invalid product reference rejected by foreign key';
            ROLLBACK TO SAVEPOINT invalid_reference;
    END;
END
$$;

COMMIT;

-- Analytical query: relational systems are particularly natural for
-- multi-entity aggregation and reporting.
SELECT
    c.full_name,
    p.category,
    SUM(oi.quantity) AS units,
    SUM(
        oi.quantity * oi.unit_price
    ) AS revenue
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
JOIN order_items oi
    ON oi.order_id = o.order_id
JOIN products p
    ON p.product_id = oi.product_id
WHERE o.status = 'PAID'
GROUP BY
    c.full_name,
    p.category
ORDER BY revenue DESC;

-- A common table expression compares customer spending with the overall
-- average. This is a relational analytical operation that would usually
-- require an application-side aggregation or specialized query mechanism in
-- a simple key-value store.
WITH customer_spend AS (
    SELECT
        c.customer_id,
        c.full_name,
        COALESCE(
            SUM(
                oi.quantity * oi.unit_price
            ),
            0
        ) AS total_spend
    FROM customers c
    LEFT JOIN orders o
        ON o.customer_id = c.customer_id
        AND o.status = 'PAID'
    LEFT JOIN order_items oi
        ON oi.order_id = o.order_id
    GROUP BY
        c.customer_id,
        c.full_name
)
SELECT
    full_name,
    total_spend,
    AVG(total_spend) OVER () AS average_customer_spend
FROM customer_spend
ORDER BY total_spend DESC;

-- The following table represents a NoSQL-style denormalized document inside
-- PostgreSQL only for comparison. It is not required by the normalized model.
-- In a document database, the complete order aggregate could naturally be
-- stored as one JSON document.
CREATE TABLE document_order_example (
    document_id TEXT PRIMARY KEY,
    document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO document_order_example (
    document_id,
    document
)
VALUES (
    'order-document-1001',
    '{
        "customer": {
            "id": 1,
            "name": "Asha Rao"
        },
        "status": "PAID",
        "items": [
            {
                "product_id": 1,
                "name": "Laptop",
                "quantity": 1,
                "unit_price": 1200
            },
            {
                "product_id": 2,
                "name": "Keyboard",
                "quantity": 2,
                "unit_price": 80
            }
        ],
        "shipping": {
            "country": "IN",
            "postal_code": "226001"
        }
    }'::jsonb
);

SELECT
    document_id,
    document -> 'customer' ->> 'name' AS customer_name,
    document ->> 'status' AS status,
    jsonb_array_length(
        document -> 'items'
    ) AS item_count
FROM document_order_example;

-- Workload-specific interpretation:
--
-- SQL is a strong fit when the workload requires:
--   * foreign-key integrity
--   * multi-row transactions
--   * joins and complex relational reporting
--   * strong consistency around financial state
--
-- Document NoSQL is often useful when:
--   * application objects map naturally to aggregate documents
--   * document structure changes frequently
--   * reads commonly retrieve a complete aggregate
--   * horizontal distribution is a primary architectural requirement
--
-- Key-value NoSQL is useful when:
--   * access is dominated by exact key lookup
--   * predictable low-latency access matters
--   * relationships and ad hoc joins are not the primary operation
--
-- These categories are architectural tendencies, not absolute restrictions.
-- Modern database products frequently combine multiple storage, indexing,
-- replication, partitioning, and consistency mechanisms.
