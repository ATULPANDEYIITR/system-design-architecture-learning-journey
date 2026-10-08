/*
Database Partitioning: Horizontal and Vertical Partitioning
PostgreSQL-compatible demonstration.

The schema deliberately separates:
  - horizontal partitioning: rows distributed by order date
  - vertical partitioning: customer columns split by access sensitivity
  - list partitioning: explicit regional routing
  - hash partitioning: deterministic customer distribution
  - composite partitioning: RANGE by month followed by HASH by customer

The script is designed to be executable in PostgreSQL.
*/

DROP SCHEMA IF EXISTS partitioning_demo CASCADE;

CREATE SCHEMA partitioning_demo;

SET search_path TO partitioning_demo;

/*
 * ================================================================
 * Horizontal RANGE Partitioning
 * ================================================================
 *
 * The partition key is order_date.
 *
 * PostgreSQL uses half-open intervals:
 *     FROM lower TO upper
 *
 * Therefore 2026-04-01 belongs to Q2, not Q1.
 */

CREATE TABLE orders (
    order_id        BIGINT NOT NULL,
    customer_id     BIGINT NOT NULL,
    order_date      DATE NOT NULL,
    region          TEXT NOT NULL,
    status          TEXT NOT NULL,
    total_amount    NUMERIC(14, 2) NOT NULL,
    payment_token   TEXT,
    shipping_city   TEXT,

    CONSTRAINT orders_amount_nonnegative
        CHECK (total_amount >= 0),

    CONSTRAINT orders_status_valid
        CHECK (
            status IN (
                'PENDING',
                'PAID',
                'SHIPPED',
                'CANCELLED'
            )
        ),

    CONSTRAINT orders_region_valid
        CHECK (
            region IN (
                'NORTH',
                'SOUTH',
                'EAST',
                'WEST'
            )
        ),

    /*
     * A partitioned primary key must include the partition key because
     * PostgreSQL needs uniqueness to be enforceable across partitions.
     */
    CONSTRAINT orders_pk
        PRIMARY KEY (order_id, order_date)
)
PARTITION BY RANGE (order_date);

CREATE TABLE orders_2026_q1
    PARTITION OF orders
    FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');

CREATE TABLE orders_2026_q2
    PARTITION OF orders
    FOR VALUES FROM ('2026-04-01') TO ('2026-07-01');

CREATE TABLE orders_2026_q3
    PARTITION OF orders
    FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');

CREATE TABLE orders_2026_q4
    PARTITION OF orders
    FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');

/*
 * A default partition makes the table robust against dates outside
 * the explicitly provisioned range. In a strict operational design,
 * a team may instead prefer an intentional insert failure until a
 * future partition is created.
 */
CREATE TABLE orders_default
    PARTITION OF orders DEFAULT;

/*
 * Indexes defined on a partitioned table create corresponding indexes
 * on its partitions and support customer/date lookup patterns.
 */
CREATE INDEX idx_orders_customer_date
    ON orders (customer_id, order_date);

CREATE INDEX idx_orders_region_date
    ON orders (region, order_date);

/*
 * ================================================================
 * Horizontal Partition Data
 * ================================================================
 */

INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    region,
    status,
    total_amount,
    payment_token,
    shipping_city
)
VALUES
    (
        1001, 501, '2026-02-15', 'NORTH',
        'PAID', 1250.50, 'tok_a', 'Lucknow'
    ),
    (
        1002, 502, '2026-05-20', 'SOUTH',
        'SHIPPED', 760.00, 'tok_b', 'Bengaluru'
    ),
    (
        1003, 503, '2026-08-12', 'WEST',
        'PAID', 2100.00, 'tok_c', 'Mumbai'
    ),
    (
        1004, 504, '2026-11-03', 'EAST',
        'PENDING', 450.00, 'tok_d', 'Kolkata'
    );

/*
 * The exact partition containing each row can be inspected through
 * tableoid. This is useful when validating routing during operations.
 */
SELECT
    order_id,
    order_date,
    tableoid::regclass AS physical_partition
FROM orders
ORDER BY order_date;

/*
 * This predicate allows PostgreSQL to prune partitions whose date
 * ranges cannot satisfy the condition.
 */
EXPLAIN (COSTS OFF)
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE order_date >= DATE '2026-04-01'
  AND order_date < DATE '2026-10-01';

/*
 * ================================================================
 * Vertical Partitioning
 * ================================================================
 *
 * A vertically partitioned customer entity is split into:
 *   customer_operational
 *   customer_sensitive
 *
 * The common primary key reconstructs the logical customer.
 *
 * This can reduce I/O for queries that need operational attributes
 * but do not need address or date-of-birth data.
 */

CREATE TABLE customer_operational (
    customer_id     BIGINT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    phone           TEXT,
    account_status  TEXT NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT customer_operational_status_valid
        CHECK (
            account_status IN (
                'ACTIVE',
                'SUSPENDED',
                'CLOSED'
            )
        )
);

CREATE TABLE customer_sensitive (
    customer_id     BIGINT PRIMARY KEY,
    postal_address  TEXT NOT NULL,
    date_of_birth   DATE,

    CONSTRAINT customer_sensitive_fk
        FOREIGN KEY (customer_id)
        REFERENCES customer_operational(customer_id)
        ON DELETE CASCADE
);

INSERT INTO customer_operational (
    customer_id,
    full_name,
    email,
    phone,
    account_status
)
VALUES
    (
        501,
        'Asha Sharma',
        'asha@example.com',
        '+91-9000000001',
        'ACTIVE'
    ),
    (
        502,
        'Rohan Mehta',
        'rohan@example.com',
        '+91-9000000002',
        'ACTIVE'
    ),
    (
        503,
        'Neha Singh',
        'neha@example.com',
        '+91-9000000003',
        'SUSPENDED'
    );

INSERT INTO customer_sensitive (
    customer_id,
    postal_address,
    date_of_birth
)
VALUES
    (
        501,
        'Lucknow',
        DATE '1992-03-14'
    ),
    (
        502,
        'Bengaluru',
        DATE '1988-08-22'
    ),
    (
        503,
        'Mumbai',
        DATE '1990-11-08'
    );

/*
 * A narrow query reads only the operational vertical fragment.
 */
SELECT
    customer_id,
    full_name,
    email,
    phone
FROM customer_operational
WHERE customer_id = 501;

/*
 * A full logical customer requires a join across the vertical
 * fragments. The shared primary key preserves entity identity.
 */
SELECT
    o.customer_id,
    o.full_name,
    o.email,
    o.phone,
    o.account_status,
    s.postal_address,
    s.date_of_birth
FROM customer_operational AS o
JOIN customer_sensitive AS s
    ON s.customer_id = o.customer_id
WHERE o.customer_id = 501;

/*
 * Encapsulating the logical reconstruction in a view prevents every
 * application query from repeating the join definition.
 */
CREATE VIEW customer_profile AS
SELECT
    o.customer_id,
    o.full_name,
    o.email,
    o.phone,
    o.account_status,
    s.postal_address,
    s.date_of_birth
FROM customer_operational AS o
JOIN customer_sensitive AS s
    ON s.customer_id = o.customer_id;

/*
 * ================================================================
 * LIST Partitioning
 * ================================================================
 *
 * LIST partitioning is appropriate when a finite business category
 * such as region is itself the routing dimension.
 */

CREATE TABLE regional_orders (
    order_id        BIGINT NOT NULL,
    customer_id     BIGINT NOT NULL,
    region          TEXT NOT NULL,
    order_date      DATE NOT NULL,
    total_amount    NUMERIC(14, 2) NOT NULL,

    CONSTRAINT regional_orders_pk
        PRIMARY KEY (order_id, region)
)
PARTITION BY LIST (region);

CREATE TABLE regional_orders_north
    PARTITION OF regional_orders
    FOR VALUES IN ('NORTH');

CREATE TABLE regional_orders_south
    PARTITION OF regional_orders
    FOR VALUES IN ('SOUTH');

CREATE TABLE regional_orders_east
    PARTITION OF regional_orders
    FOR VALUES IN ('EAST');

CREATE TABLE regional_orders_west
    PARTITION OF regional_orders
    FOR VALUES IN ('WEST');

CREATE TABLE regional_orders_other
    PARTITION OF regional_orders DEFAULT;

INSERT INTO regional_orders (
    order_id,
    customer_id,
    region,
    order_date,
    total_amount
)
VALUES
    (2001, 601, 'NORTH', '2026-09-01', 500.00),
    (2002, 602, 'WEST', '2026-09-02', 750.00),
    (2003, 603, 'CENTRAL', '2026-09-03', 300.00);

/*
 * The CENTRAL row goes to the DEFAULT partition because no explicit
 * list partition contains CENTRAL.
 */
SELECT
    order_id,
    region,
    tableoid::regclass AS physical_partition
FROM regional_orders
ORDER BY order_id;

/*
 * ================================================================
 * HASH Partitioning
 * ================================================================
 *
 * Hash partitioning is useful when even distribution by an identifier
 * matters more than range locality.
 */

CREATE TABLE customer_events (
    event_id        BIGINT NOT NULL,
    customer_id     BIGINT NOT NULL,
    event_type      TEXT NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    payload         JSONB NOT NULL,

    PRIMARY KEY (event_id, customer_id)
)
PARTITION BY HASH (customer_id);

CREATE TABLE customer_events_h0
    PARTITION OF customer_events
    FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE customer_events_h1
    PARTITION OF customer_events
    FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE customer_events_h2
    PARTITION OF customer_events
    FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE customer_events_h3
    PARTITION OF customer_events
    FOR VALUES WITH (MODULUS 4, REMAINDER 3);

INSERT INTO customer_events (
    event_id,
    customer_id,
    event_type,
    occurred_at,
    payload
)
VALUES
    (
        1, 501, 'LOGIN',
        TIMESTAMPTZ '2026-10-08 08:00:00+05:30',
        '{"source":"web"}'
    ),
    (
        2, 502, 'PURCHASE',
        TIMESTAMPTZ '2026-10-08 08:02:00+05:30',
        '{"amount":760}'
    ),
    (
        3, 503, 'LOGIN',
        TIMESTAMPTZ '2026-10-08 08:05:00+05:30',
        '{"source":"mobile"}'
    );

/*
 * ================================================================
 * Composite Partitioning
 * ================================================================
 *
 * The event_archive table uses:
 *   first level  = RANGE by event date
 *   second level = HASH by customer ID
 *
 * This combines time-based pruning with distribution among child
 * partitions.
 */

CREATE TABLE event_archive (
    event_id        BIGINT NOT NULL,
    customer_id     BIGINT NOT NULL,
    event_date      DATE NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,

    PRIMARY KEY (event_id, event_date)
)
PARTITION BY RANGE (event_date);

CREATE TABLE event_archive_2026_09
    PARTITION OF event_archive
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01')
    PARTITION BY HASH (customer_id);

CREATE TABLE event_archive_2026_09_h0
    PARTITION OF event_archive_2026_09
    FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE event_archive_2026_09_h1
    PARTITION OF event_archive_2026_09
    FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE event_archive_2026_09_h2
    PARTITION OF event_archive_2026_09
    FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE event_archive_2026_09_h3
    PARTITION OF event_archive_2026_09
    FOR VALUES WITH (MODULUS 4, REMAINDER 3);

INSERT INTO event_archive (
    event_id,
    customer_id,
    event_date,
    event_type,
    payload
)
VALUES
    (
        10001,
        701,
        '2026-09-01',
        'LOGIN',
        '{"device":"desktop"}'
    ),
    (
        10002,
        702,
        'PURCHASE',
        '2026-09-04',
        '{"amount":200}'
    ),
    (
        10003,
        701,
        'PURCHASE',
        '2026-09-20',
        '{"amount":300}'
    );

/*
 * This query supplies both dimensions:
 * date pruning can eliminate other months, while customer_id can
 * allow the hash hierarchy to narrow the second-level scan.
 */
EXPLAIN (COSTS OFF)
SELECT
    event_id,
    customer_id,
    event_type
FROM event_archive
WHERE event_date >= DATE '2026-09-01'
  AND event_date < DATE '2026-10-01'
  AND customer_id = 701;

/*
 * ================================================================
 * Integrity and Edge Cases
 * ================================================================
 */

/*
 * Negative monetary values are rejected by CHECK constraints.
 */
DO $$
BEGIN
    BEGIN
        INSERT INTO orders (
            order_id,
            customer_id,
            order_date,
            region,
            status,
            total_amount
        )
        VALUES (
            9991,
            900,
            '2026-09-10',
            'NORTH',
            'PAID',
            -10.00
        );
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE
                'Expected rejection: negative order amount';
    END;
END;
$$;

/*
 * An invalid status is rejected before the row can enter a partition.
 */
DO $$
BEGIN
    BEGIN
        INSERT INTO orders (
            order_id,
            customer_id,
            order_date,
            region,
            status,
            total_amount
        )
        VALUES (
            9992,
            901,
            '2026-09-11',
            'NORTH',
            'UNKNOWN',
            100.00
        );
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE
                'Expected rejection: invalid order status';
    END;
END;
$$;

/*
 * A vertical fragment cannot exist without its parent operational row.
 */
DO $$
BEGIN
    BEGIN
        INSERT INTO customer_sensitive (
            customer_id,
            postal_address,
            date_of_birth
        )
        VALUES (
            9999,
            'Unknown',
            DATE '1990-01-01'
        );
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE
                'Expected rejection: orphan vertical fragment';
    END;
END;
$$;

/*
 * ================================================================
 * Transactional Partition Maintenance Example
 * ================================================================
 *
 * Creating a future partition should be treated as schema maintenance,
 * not as an ad-hoc application operation. The transaction groups the
 * DDL so failure can be rolled back by PostgreSQL.
 */

BEGIN;

CREATE TABLE orders_2027_q1
    PARTITION OF orders
    FOR VALUES FROM ('2027-01-01') TO ('2027-04-01');

COMMIT;

/*
 * ================================================================
 * Partition Distribution and Operational Inspection
 * ================================================================
 */

SELECT
    tableoid::regclass AS partition_name,
    count(*) AS row_count
FROM orders
GROUP BY tableoid
ORDER BY partition_name;

SELECT
    inhrelid::regclass AS child_partition
FROM pg_inherits
WHERE inhparent = 'partitioning_demo.orders'::regclass
ORDER BY child_partition;

/*
 * ================================================================
 * Comparison Queries
 * ================================================================
 *
 * Horizontal:
 *   The physical row is selected by order_date.
 *
 * Vertical:
 *   The logical customer is reconstructed from column groups.
 *
 * LIST:
 *   The physical row is selected by a finite business category.
 *
 * HASH:
 *   The physical row is distributed by a deterministic hash.
 *
 * Composite:
 *   Multiple partitioning dimensions are applied hierarchically.
 */

SELECT
    order_id,
    order_date,
    total_amount
FROM orders
WHERE order_date >= DATE '2026-07-01'
  AND order_date < DATE '2026-10-01';

SELECT
    customer_id,
    full_name,
    email,
    account_status
FROM customer_operational
WHERE account_status = 'ACTIVE';

SELECT
    customer_id,
    full_name,
    postal_address
FROM customer_profile
WHERE customer_id = 501;

SELECT
    order_id,
    region,
    tableoid::regclass
FROM regional_orders
WHERE region = 'WEST';

SELECT
    event_id,
    customer_id,
    occurred_at
FROM customer_events
WHERE customer_id = 501;

SELECT
    event_id,
    customer_id,
    event_type
FROM event_archive
WHERE event_date >= DATE '2026-09-01'
  AND event_date < DATE '2026-10-01'
  AND customer_id = 701;
