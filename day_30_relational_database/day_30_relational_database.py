"""
Relational Databases: SQL, Relationships, and Constraints

A self-contained SQLite case study for a small order-management database.
The script progresses from relational concepts and SQL fundamentals to:

- Tables, rows, columns, primary keys, and foreign keys
- One-to-one, one-to-many, and many-to-many relationships
- NOT NULL, UNIQUE, CHECK, DEFAULT, and FOREIGN KEY constraints
- INSERT, SELECT, UPDATE, DELETE
- JOINs, aggregation, GROUP BY, HAVING, and subqueries
- Transactions and rollback
- Indexes and query planning
- Views and triggers
- Constraint failures and validation
- Referential actions
- Normalization-oriented schema design
- Parameterized SQL and safe application/database boundaries
- A small reporting workflow

Only Python's standard library is required.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


DATABASE_URI = "file:relational_learning?mode=memory&cache=shared"


@dataclass(frozen=True)
class Customer:
    customer_id: int
    name: str
    email: str


def connect_database() -> sqlite3.Connection:
    """Create an SQLite connection and enable foreign-key enforcement."""
    connection = sqlite3.connect(DATABASE_URI, uri=True)
    connection.row_factory = sqlite3.Row

    # SQLite does not enforce foreign keys unless this connection-level
    # setting is enabled. A schema containing REFERENCES is not enough.
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def execute_script(connection: sqlite3.Connection, sql: str) -> None:
    connection.executescript(sql)


def create_schema(connection: sqlite3.Connection) -> None:
    """
    Create a normalized order-management schema.

    Relationships:
        customers 1 ---- * orders
        orders    1 ---- * order_items
        products  1 ---- * order_items
        orders    * ---- * products through order_items
        customers 1 ---- 1 customer_profiles
    """
    schema = """
    PRAGMA foreign_keys = ON;

    DROP VIEW IF EXISTS customer_order_summary;
    DROP TRIGGER IF EXISTS prevent_negative_inventory;
    DROP TRIGGER IF EXISTS decrease_inventory_after_order_item;

    DROP TABLE IF EXISTS order_items;
    DROP TABLE IF EXISTS orders;
    DROP TABLE IF EXISTS customer_profiles;
    DROP TABLE IF EXISTS products;
    DROP TABLE IF EXISTS customers;

    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (length(trim(name)) >= 2)
    );

    CREATE TABLE customer_profiles (
        customer_id INTEGER PRIMARY KEY,
        phone TEXT UNIQUE,
        city TEXT NOT NULL,
        country TEXT NOT NULL DEFAULT 'India',
        FOREIGN KEY (customer_id)
            REFERENCES customers(customer_id)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    );

    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY,
        sku TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_price NUMERIC NOT NULL,
        inventory_quantity INTEGER NOT NULL DEFAULT 0,
        CHECK (unit_price >= 0),
        CHECK (inventory_quantity >= 0)
    );

    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        order_status TEXT NOT NULL DEFAULT 'PENDING',
        ordered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id)
            REFERENCES customers(customer_id)
            ON DELETE RESTRICT
            ON UPDATE CASCADE,
        CHECK (
            order_status IN (
                'PENDING',
                'PAID',
                'SHIPPED',
                'CANCELLED'
            )
        )
    );

    CREATE TABLE order_items (
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price NUMERIC NOT NULL,
        PRIMARY KEY (order_id, product_id),
        FOREIGN KEY (order_id)
            REFERENCES orders(order_id)
            ON DELETE CASCADE
            ON UPDATE CASCADE,
        FOREIGN KEY (product_id)
            REFERENCES products(product_id)
            ON DELETE RESTRICT
            ON UPDATE CASCADE,
        CHECK (quantity > 0),
        CHECK (unit_price >= 0)
    );

    CREATE INDEX idx_orders_customer_id
        ON orders(customer_id);

    CREATE INDEX idx_order_items_product_id
        ON order_items(product_id);

    CREATE INDEX idx_products_category
        ON products(category);

    CREATE VIEW customer_order_summary AS
    SELECT
        c.customer_id,
        c.name,
        c.email,
        COUNT(DISTINCT o.order_id) AS order_count,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS lifetime_value
    FROM customers AS c
    LEFT JOIN orders AS o
        ON o.customer_id = c.customer_id
        AND o.order_status <> 'CANCELLED'
    LEFT JOIN order_items AS oi
        ON oi.order_id = o.order_id
    GROUP BY c.customer_id, c.name, c.email;

    CREATE TRIGGER prevent_negative_inventory
    BEFORE UPDATE OF inventory_quantity ON products
    FOR EACH ROW
    WHEN NEW.inventory_quantity < 0
    BEGIN
        SELECT RAISE(ABORT, 'inventory quantity cannot be negative');
    END;
    """
    execute_script(connection, schema)


def seed_data(connection: sqlite3.Connection) -> None:
    """Insert realistic data while allowing the database to enforce rules."""
    customers = [
        (1, "Atul Pandey", "atul@example.com"),
        (2, "Priya Sharma", "priya@example.com"),
        (3, "Rahul Verma", "rahul@example.com"),
        (4, "Neha Singh", "neha@example.com"),
    ]

    profiles = [
        (1, "+91-9000000001", "Lucknow", "India"),
        (2, "+91-9000000002", "Delhi", "India"),
        (3, "+91-9000000003", "Pune", "India"),
        (4, "+91-9000000004", "Mumbai", "India"),
    ]

    products = [
        (1, "LAP-001", "Developer Laptop", "Computers", 85000, 12),
        (2, "MON-001", "27-inch Monitor", "Displays", 24000, 25),
        (3, "KEY-001", "Mechanical Keyboard", "Accessories", 6500, 40),
        (4, "SSD-001", "2TB NVMe SSD", "Storage", 14500, 30),
        (5, "DOC-001", "USB-C Dock", "Accessories", 9000, 18),
    ]

    orders = [
        (101, 1, "PAID"),
        (102, 1, "SHIPPED"),
        (103, 2, "PAID"),
        (104, 3, "CANCELLED"),
    ]

    order_items = [
        (101, 1, 1, 85000),
        (101, 3, 1, 6500),
        (102, 2, 2, 24000),
        (102, 5, 1, 9000),
        (103, 4, 2, 14500),
        (104, 1, 1, 85000),
    ]

    with connection:
        connection.executemany(
            """
            INSERT INTO customers(customer_id, name, email)
            VALUES (?, ?, ?)
            """,
            customers,
        )

        connection.executemany(
            """
            INSERT INTO customer_profiles(customer_id, phone, city, country)
            VALUES (?, ?, ?, ?)
            """,
            profiles,
        )

        connection.executemany(
            """
            INSERT INTO products(
                product_id, sku, name, category, unit_price, inventory_quantity
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            products,
        )

        connection.executemany(
            """
            INSERT INTO orders(order_id, customer_id, order_status)
            VALUES (?, ?, ?)
            """,
            orders,
        )

        connection.executemany(
            """
            INSERT INTO order_items(order_id, product_id, quantity, unit_price)
            VALUES (?, ?, ?, ?)
            """,
            order_items,
        )


def print_rows(rows: Iterable[sqlite3.Row]) -> None:
    """Print SQLite rows without depending on an external table package."""
    for row in rows:
        print(dict(row))


def demonstrate_basic_selects(connection: sqlite3.Connection) -> None:
    print("\n=== Basic relational queries ===")

    rows = connection.execute(
        """
        SELECT product_id, sku, name, unit_price
        FROM products
        WHERE unit_price >= ?
        ORDER BY unit_price DESC
        """,
        (10000,),
    ).fetchall()

    print("\nProducts costing at least 10,000:")
    print_rows(rows)

    row = connection.execute(
        """
        SELECT customer_id, name, email
        FROM customers
        WHERE email = ?
        """,
        ("atul@example.com",),
    ).fetchone()

    print("\nParameterized lookup:")
    print(dict(row) if row else "Customer not found")


def demonstrate_relationships(connection: sqlite3.Connection) -> None:
    print("\n=== Relationships and JOINs ===")

    print("\nOne-to-many: customers to orders")
    rows = connection.execute(
        """
        SELECT
            c.name AS customer,
            o.order_id,
            o.order_status
        FROM customers AS c
        INNER JOIN orders AS o
            ON o.customer_id = c.customer_id
        ORDER BY c.customer_id, o.order_id
        """
    ).fetchall()
    print_rows(rows)

    print("\nMany-to-many: orders to products through order_items")
    rows = connection.execute(
        """
        SELECT
            o.order_id,
            p.name AS product,
            oi.quantity,
            oi.unit_price,
            oi.quantity * oi.unit_price AS line_total
        FROM orders AS o
        INNER JOIN order_items AS oi
            ON oi.order_id = o.order_id
        INNER JOIN products AS p
            ON p.product_id = oi.product_id
        ORDER BY o.order_id, p.product_id
        """
    ).fetchall()
    print_rows(rows)

    print("\nOne-to-one: customer to customer_profiles")
    rows = connection.execute(
        """
        SELECT
            c.name,
            cp.phone,
            cp.city,
            cp.country
        FROM customers AS c
        INNER JOIN customer_profiles AS cp
            ON cp.customer_id = c.customer_id
        ORDER BY c.customer_id
        """
    ).fetchall()
    print_rows(rows)

    print("\nLEFT JOIN preserves customers with no orders:")
    rows = connection.execute(
        """
        SELECT
            c.customer_id,
            c.name,
            COUNT(o.order_id) AS orders
        FROM customers AS c
        LEFT JOIN orders AS o
            ON o.customer_id = c.customer_id
            AND o.order_status <> 'CANCELLED'
        GROUP BY c.customer_id, c.name
        ORDER BY c.customer_id
        """
    ).fetchall()
    print_rows(rows)


def demonstrate_aggregation(connection: sqlite3.Connection) -> None:
    print("\n=== Aggregation and relational analysis ===")

    rows = connection.execute(
        """
        SELECT
            p.category,
            COUNT(DISTINCT p.product_id) AS products,
            SUM(oi.quantity) AS units_sold,
            SUM(oi.quantity * oi.unit_price) AS revenue
        FROM products AS p
        INNER JOIN order_items AS oi
            ON oi.product_id = p.product_id
        INNER JOIN orders AS o
            ON o.order_id = oi.order_id
        WHERE o.order_status <> 'CANCELLED'
        GROUP BY p.category
        HAVING SUM(oi.quantity) > 0
        ORDER BY revenue DESC
        """
    ).fetchall()

    print_rows(rows)

    print("\nSubquery: products priced above the average product price")
    rows = connection.execute(
        """
        SELECT name, unit_price
        FROM products
        WHERE unit_price > (
            SELECT AVG(unit_price)
            FROM products
        )
        ORDER BY unit_price DESC
        """
    ).fetchall()
    print_rows(rows)

    print("\nCustomer reporting view:")
    rows = connection.execute(
        """
        SELECT *
        FROM customer_order_summary
        ORDER BY lifetime_value DESC
        """
    ).fetchall()
    print_rows(rows)


def demonstrate_update_and_delete(connection: sqlite3.Connection) -> None:
    print("\n=== UPDATE and DELETE with constraints ===")

    with connection:
        connection.execute(
            """
            UPDATE products
            SET unit_price = unit_price * 1.05
            WHERE category = ?
            """,
            ("Accessories",),
        )

    updated = connection.execute(
        """
        SELECT sku, name, unit_price
        FROM products
        WHERE category = ?
        ORDER BY product_id
        """,
        ("Accessories",),
    ).fetchall()

    print("\nAccessory prices after a 5% update:")
    print_rows(updated)

    with connection:
        connection.execute(
            """
            DELETE FROM customer_profiles
            WHERE customer_id = ?
            """,
            (4,),
        )

    remaining = connection.execute(
        """
        SELECT customer_id, phone, city
        FROM customer_profiles
        ORDER BY customer_id
        """
    ).fetchall()

    print("\nProfiles after deleting one profile:")
    print_rows(remaining)


def demonstrate_constraints(connection: sqlite3.Connection) -> None:
    print("\n=== Constraint enforcement ===")

    cases = [
        (
            "duplicate email",
            """
            INSERT INTO customers(customer_id, name, email)
            VALUES (?, ?, ?)
            """,
            (99, "Duplicate Person", "atul@example.com"),
        ),
        (
            "invalid order status",
            """
            INSERT INTO orders(order_id, customer_id, order_status)
            VALUES (?, ?, ?)
            """,
            (999, 1, "UNKNOWN"),
        ),
        (
            "missing referenced customer",
            """
            INSERT INTO orders(order_id, customer_id, order_status)
            VALUES (?, ?, ?)
            """,
            (998, 99999, "PENDING"),
        ),
        (
            "invalid quantity",
            """
            INSERT INTO order_items(order_id, product_id, quantity, unit_price)
            VALUES (?, ?, ?, ?)
            """,
            (101, 4, 0, 14500),
        ),
    ]

    for description, sql, parameters in cases:
        try:
            with connection:
                connection.execute(sql, parameters)
        except sqlite3.IntegrityError as exc:
            print(f"{description}: rejected -> {exc}")


def demonstrate_transactions(connection: sqlite3.Connection) -> None:
    print("\n=== Transaction and rollback ===")

    original_price = connection.execute(
        """
        SELECT unit_price
        FROM products
        WHERE product_id = ?
        """,
        (1,),
    ).fetchone()["unit_price"]

    try:
        connection.execute("BEGIN")

        connection.execute(
            """
            UPDATE products
            SET unit_price = unit_price + ?
            WHERE product_id = ?
            """,
            (1000, 1),
        )

        # This violates the foreign-key relationship intentionally.
        connection.execute(
            """
            INSERT INTO orders(order_id, customer_id, order_status)
            VALUES (?, ?, ?)
            """,
            (700, 123456, "PENDING"),
        )

        connection.commit()
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        print(f"Transaction failed and was rolled back: {exc}")

    current_price = connection.execute(
        """
        SELECT unit_price
        FROM products
        WHERE product_id = ?
        """,
        (1,),
    ).fetchone()["unit_price"]

    print(f"Original price: {original_price}")
    print(f"Price after rollback: {current_price}")


def demonstrate_atomic_order_creation(connection: sqlite3.Connection) -> None:
    """
    Create an order and its items atomically.

    An order without its required items would represent an incomplete
    business operation, so both inserts belong to one transaction.
    """
    print("\n=== Atomic order creation ===")

    try:
        with connection:
            connection.execute(
                """
                INSERT INTO orders(order_id, customer_id, order_status)
                VALUES (?, ?, ?)
                """,
                (105, 4, "PENDING"),
            )

            connection.executemany(
                """
                INSERT INTO order_items(
                    order_id, product_id, quantity, unit_price
                )
                SELECT ?, product_id, ?, unit_price
                FROM products
                WHERE product_id = ?
                """,
                [
                    (105, 1, 1),
                    (105, 5, 1),
                ],
            )
    except sqlite3.IntegrityError as exc:
        print(f"Order transaction failed: {exc}")

    row = connection.execute(
        """
        SELECT
            o.order_id,
            o.customer_id,
            COUNT(oi.product_id) AS item_types
        FROM orders AS o
        LEFT JOIN order_items AS oi
            ON oi.order_id = o.order_id
        WHERE o.order_id = ?
        GROUP BY o.order_id, o.customer_id
        """,
        (105,),
    ).fetchone()

    print(dict(row) if row else "Order was not created")


def demonstrate_index_and_query_plan(connection: sqlite3.Connection) -> None:
    print("\n=== Index and query-plan inspection ===")

    plan = connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT order_id, order_status
        FROM orders
        WHERE customer_id = ?
        """,
        (1,),
    ).fetchall()

    print("Query plan for customer-specific order lookup:")
    print_rows(plan)

    print(
        "\nThe customer_id index gives the database an indexed access path "
        "instead of requiring a full scan for this predicate."
    )


def demonstrate_schema_metadata(connection: sqlite3.Connection) -> None:
    print("\n=== Schema metadata ===")

    tables = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    print("Tables:")
    print_rows(tables)

    print("\nForeign keys on order_items:")
    foreign_keys = connection.execute(
        """
        PRAGMA foreign_key_list(order_items)
        """
    ).fetchall()
    print_rows(foreign_keys)


def calculate_order_total(
    connection: sqlite3.Connection, order_id: int
) -> Decimal:
    """Return an order total using Decimal at the Python application boundary."""
    row = connection.execute(
        """
        SELECT COALESCE(SUM(quantity * unit_price), 0) AS total
        FROM order_items
        WHERE order_id = ?
        """,
        (order_id,),
    ).fetchone()

    return Decimal(str(row["total"]))


def demonstrate_application_boundary(connection: sqlite3.Connection) -> None:
    print("\n=== Application/database boundary ===")

    order_id = 101
    total = calculate_order_total(connection, order_id)
    print(f"Order {order_id} total: {total}")

    unsafe_value = "101 OR 1=1"

    # Never construct SQL by concatenating untrusted values. Parameter binding
    # keeps the input as a value rather than allowing it to become SQL syntax.
    safe_row = connection.execute(
        """
        SELECT order_id, customer_id
        FROM orders
        WHERE order_id = ?
        """,
        (unsafe_value,),
    ).fetchone()

    print(
        "Malicious-looking input treated as a value:",
        dict(safe_row) if safe_row else "no matching order",
    )


def demonstrate_relationship_integrity(connection: sqlite3.Connection) -> None:
    print("\n=== Referential integrity ===")

    try:
        with connection:
            connection.execute(
                """
                DELETE FROM products
                WHERE product_id = ?
                """,
                (1,),
            )
    except sqlite3.IntegrityError as exc:
        print(
            "Product deletion rejected because existing order_items "
            f"reference it: {exc}"
        )

    with connection:
        connection.execute(
            """
            DELETE FROM orders
            WHERE order_id = ?
              AND order_status = 'CANCELLED'
            """,
            (104,),
        )

    cancelled_order = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM orders
        WHERE order_id = ?
        """,
        (104,),
    ).fetchone()["count"]

    cancelled_items = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM order_items
        WHERE order_id = ?
        """,
        (104,),
    ).fetchone()["count"]

    print(
        "After deleting cancelled order 104, "
        f"orders={cancelled_order}, order_items={cancelled_items}"
    )


def demonstrate_normalization_reasoning() -> None:
    print("\n=== Schema-design reasoning ===")
    print(
        "Customer identity is stored once in customers; contact/profile "
        "attributes belong to customer_profiles."
    )
    print(
        "Product identity and current inventory belong to products rather "
        "than being copied into every order."
    )
    print(
        "order_items resolves the many-to-many relationship between orders "
        "and products and carries relationship-specific quantity and price."
    )
    print(
        "The order_items.unit_price column intentionally records the price "
        "at purchase time. It is not redundant with the current products "
        "price because historical order values must remain stable."
    )


def main() -> None:
    connection = connect_database()

    try:
        create_schema(connection)
        seed_data(connection)

        demonstrate_basic_selects(connection)
        demonstrate_relationships(connection)
        demonstrate_aggregation(connection)
        demonstrate_update_and_delete(connection)
        demonstrate_constraints(connection)
        demonstrate_transactions(connection)
        demonstrate_atomic_order_creation(connection)
        demonstrate_index_and_query_plan(connection)
        demonstrate_schema_metadata(connection)
        demonstrate_application_boundary(connection)
        demonstrate_relationship_integrity(connection)
        demonstrate_normalization_reasoning()

        print("\n=== Completed relational database case study ===")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
