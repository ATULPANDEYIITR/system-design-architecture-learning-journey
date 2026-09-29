"""
Database Fundamentals: Tables, Records, Schemas, and Queries

A standalone study script covering relational database fundamentals from
beginner concepts through advanced query design, validation, transactions,
indexes, normalization, constraints, and practical database patterns.

The script uses Python's standard library sqlite3 module, so it can run
without installing external packages.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


DATABASE_NAME = ":memory:"


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def show_rows(rows: Iterable[sqlite3.Row]) -> None:
    rows = list(rows)
    if not rows:
        print("(no rows)")
        return

    columns = rows[0].keys()
    print(" | ".join(columns))
    print("-" * (len(" | ".join(columns)) + 2))

    for row in rows:
        print(" | ".join(str(row[column]) for column in columns))


@contextmanager
def transaction(connection: sqlite3.Connection):
    """
    A transaction groups multiple database operations into one atomic unit.

    If an exception occurs, all changes inside the transaction are rolled
    back. Otherwise, they are committed.
    """
    try:
        yield
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def create_database(connection: sqlite3.Connection) -> None:
    section("1. DATABASE, SCHEMA, TABLES, AND RELATIONAL STRUCTURE")

    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE departments (
            department_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            budget REAL NOT NULL CHECK (budget >= 0)
        );

        CREATE TABLE employees (
            employee_id INTEGER PRIMARY KEY,
            department_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            salary REAL NOT NULL CHECK (salary >= 0),
            hire_date TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            FOREIGN KEY (department_id)
                REFERENCES departments(department_id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
        );

        CREATE TABLE projects (
            project_id INTEGER PRIMARY KEY,
            project_name TEXT NOT NULL UNIQUE,
            budget REAL NOT NULL CHECK (budget >= 0),
            status TEXT NOT NULL
                CHECK (status IN ('planned', 'active', 'completed'))
        );

        CREATE TABLE employee_projects (
            employee_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            assigned_on TEXT NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (employee_id, project_id),
            FOREIGN KEY (employee_id)
                REFERENCES employees(employee_id)
                ON DELETE CASCADE,
            FOREIGN KEY (project_id)
                REFERENCES projects(project_id)
                ON DELETE CASCADE
        );
        """
    )

    print(
        """
A database is an organized collection of data.

A schema describes the structure and rules of a database. In this example,
the schema contains departments, employees, projects, and the relationship
between employees and projects.

A table stores rows and columns:
  - table: a logical collection of related records
  - row/record: one instance of an entity
  - column/field: one attribute of that entity
  - primary key: uniquely identifies a row
  - foreign key: references a row in another table
  - constraint: a rule enforced by the database
"""
    )


def insert_sample_data(connection: sqlite3.Connection) -> None:
    section("2. INSERTING RECORDS")

    with transaction(connection):
        connection.executemany(
            """
            INSERT INTO departments (department_id, name, budget)
            VALUES (?, ?, ?)
            """,
            [
                (1, "Engineering", 2_000_000),
                (2, "Finance", 1_200_000),
                (3, "Operations", 900_000),
                (4, "Research", 1_500_000),
            ],
        )

        connection.executemany(
            """
            INSERT INTO employees
            (employee_id, department_id, first_name, last_name, email,
             salary, hire_date, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (101, 1, "Asha", "Sharma", "asha@example.com", 120000, "2022-01-15", 1),
                (102, 1, "Ravi", "Kumar", "ravi@example.com", 95000, "2023-04-10", 1),
                (103, 2, "Neha", "Singh", "neha@example.com", 110000, "2021-09-20", 1),
                (104, 2, "Arjun", "Mehta", "arjun@example.com", 85000, "2024-02-01", 1),
                (105, 3, "Priya", "Verma", "priya@example.com", 78000, "2020-06-11", 0),
                (106, 4, "Kabir", "Das", "kabir@example.com", 135000, "2022-11-05", 1),
            ],
        )

        connection.executemany(
            """
            INSERT INTO projects (project_id, project_name, budget, status)
            VALUES (?, ?, ?, ?)
            """,
            [
                (201, "Data Platform", 500000, "active"),
                (202, "Risk Engine", 350000, "active"),
                (203, "Automation", 180000, "completed"),
            ],
        )

        connection.executemany(
            """
            INSERT INTO employee_projects
            (employee_id, project_id, assigned_on, role)
            VALUES (?, ?, ?, ?)
            """,
            [
                (101, 201, "2025-01-10", "Architect"),
                (102, 201, "2025-02-01", "Developer"),
                (103, 202, "2025-03-15", "Analyst"),
                (106, 202, "2025-03-20", "Researcher"),
                (102, 203, "2024-01-01", "Developer"),
            ],
        )

    print("Sample records inserted successfully.")


def demonstrate_select(connection: sqlite3.Connection) -> None:
    section("3. SELECT, PROJECTION, AND FILTERING")

    print("\nAll employees:")
    show_rows(
        connection.execute(
            """
            SELECT employee_id, first_name, last_name, salary
            FROM employees
            ORDER BY employee_id
            """
        )
    )

    print("\nOnly active employees:")
    show_rows(
        connection.execute(
            """
            SELECT employee_id, first_name, last_name
            FROM employees
            WHERE active = 1
            ORDER BY last_name, first_name
            """
        )
    )

    print("\nEmployees earning at least 100,000:")
    show_rows(
        connection.execute(
            """
            SELECT first_name, last_name, salary
            FROM employees
            WHERE salary >= ?
            ORDER BY salary DESC
            """,
            (100000,),
        )
    )

    print("\nCalculated column:")
    show_rows(
        connection.execute(
            """
            SELECT
                first_name,
                salary,
                ROUND(salary * 0.10, 2) AS estimated_bonus
            FROM employees
            ORDER BY salary DESC
            """
        )
    )


def demonstrate_conditions(connection: sqlite3.Connection) -> None:
    section("4. SQL CONDITIONS AND EXPRESSIONS")

    queries = {
        "AND": """
            SELECT first_name, salary
            FROM employees
            WHERE active = 1 AND salary > 90000
            ORDER BY salary DESC
        """,
        "OR": """
            SELECT first_name, department_id
            FROM employees
            WHERE department_id = 1 OR department_id = 4
            ORDER BY employee_id
        """,
        "IN": """
            SELECT first_name, department_id
            FROM employees
            WHERE department_id IN (1, 4)
            ORDER BY employee_id
        """,
        "BETWEEN": """
            SELECT first_name, salary
            FROM employees
            WHERE salary BETWEEN 80000 AND 120000
            ORDER BY salary
        """,
        "LIKE": """
            SELECT first_name, email
            FROM employees
            WHERE email LIKE '%@example.com'
            ORDER BY first_name
        """,
        "IS": """
            SELECT first_name
            FROM employees
            WHERE hire_date IS NOT NULL
            ORDER BY first_name
        """,
    }

    for label, query in queries.items():
        print(f"\n{label}:")
        show_rows(connection.execute(query))


def demonstrate_aggregates(connection: sqlite3.Connection) -> None:
    section("5. AGGREGATION, GROUP BY, AND HAVING")

    print("\nOverall statistics:")
    show_rows(
        connection.execute(
            """
            SELECT
                COUNT(*) AS employee_count,
                ROUND(AVG(salary), 2) AS average_salary,
                MIN(salary) AS minimum_salary,
                MAX(salary) AS maximum_salary,
                ROUND(SUM(salary), 2) AS payroll
            FROM employees
            """
        )
    )

    print("\nStatistics by department:")
    show_rows(
        connection.execute(
            """
            SELECT
                department_id,
                COUNT(*) AS employee_count,
                ROUND(AVG(salary), 2) AS average_salary,
                ROUND(SUM(salary), 2) AS payroll
            FROM employees
            GROUP BY department_id
            ORDER BY average_salary DESC
            """
        )
    )

    print("\nDepartments with at least two employees:")
    show_rows(
        connection.execute(
            """
            SELECT department_id, COUNT(*) AS employee_count
            FROM employees
            GROUP BY department_id
            HAVING COUNT(*) >= 2
            """
        )
    )

    print(
        """
WHERE filters rows before grouping.
HAVING filters groups after GROUP BY.
COUNT, SUM, AVG, MIN, and MAX are common aggregate functions.
"""
    )


def demonstrate_joins(connection: sqlite3.Connection) -> None:
    section("6. JOINS")

    print("\nINNER JOIN:")
    show_rows(
        connection.execute(
            """
            SELECT
                e.first_name || ' ' || e.last_name AS employee,
                d.name AS department
            FROM employees AS e
            INNER JOIN departments AS d
                ON e.department_id = d.department_id
            ORDER BY d.name, employee
            """
        )
    )

    print("\nLEFT JOIN:")
    show_rows(
        connection.execute(
            """
            SELECT
                d.name AS department,
                COUNT(e.employee_id) AS employee_count
            FROM departments AS d
            LEFT JOIN employees AS e
                ON d.department_id = e.department_id
            GROUP BY d.department_id, d.name
            ORDER BY d.name
            """
        )
    )

    print("\nMany-to-many relationship:")
    show_rows(
        connection.execute(
            """
            SELECT
                e.first_name || ' ' || e.last_name AS employee,
                p.project_name,
                ep.role
            FROM employee_projects AS ep
            JOIN employees AS e
                ON ep.employee_id = e.employee_id
            JOIN projects AS p
                ON ep.project_id = p.project_id
            ORDER BY p.project_name, employee
            """
        )
    )

    print(
        """
A many-to-many relationship is commonly represented by a junction table.
Here employee_projects connects employees and projects.

JOIN condition quality matters. An accidental Cartesian product can
multiply rows dramatically and produce incorrect results.
"""
    )


def demonstrate_subqueries_and_ctes(connection: sqlite3.Connection) -> None:
    section("7. SUBQUERIES AND COMMON TABLE EXPRESSIONS")

    print("\nEmployees earning above the company average:")
    show_rows(
        connection.execute(
            """
            SELECT first_name, last_name, salary
            FROM employees
            WHERE salary > (
                SELECT AVG(salary)
                FROM employees
            )
            ORDER BY salary DESC
            """
        )
    )

    print("\nCTE for department salary analysis:")
    show_rows(
        connection.execute(
            """
            WITH department_stats AS (
                SELECT
                    department_id,
                    AVG(salary) AS average_salary
                FROM employees
                GROUP BY department_id
            )
            SELECT
                d.name,
                ROUND(ds.average_salary, 2) AS average_salary
            FROM department_stats AS ds
            JOIN departments AS d
                ON d.department_id = ds.department_id
            ORDER BY average_salary DESC
            """
        )
    )


def demonstrate_window_functions(connection: sqlite3.Connection) -> None:
    section("8. WINDOW FUNCTIONS")

    print("\nSalary ranking inside each department:")
    show_rows(
        connection.execute(
            """
            SELECT
                first_name,
                department_id,
                salary,
                RANK() OVER (
                    PARTITION BY department_id
                    ORDER BY salary DESC
                ) AS department_rank,
                ROUND(
                    AVG(salary) OVER (
                        PARTITION BY department_id
                    ),
                    2
                ) AS department_average
            FROM employees
            ORDER BY department_id, department_rank
            """
        )
    )

    print(
        """
Window functions calculate across related rows without collapsing them
into one row per group. This differs from GROUP BY, which normally reduces
each group to a single output row.
"""
    )


def demonstrate_insert_update_delete(connection: sqlite3.Connection) -> None:
    section("9. UPDATE AND DELETE")

    with transaction(connection):
        connection.execute(
            """
            UPDATE employees
            SET salary = salary * 1.05
            WHERE employee_id = ?
            """,
            (102,),
        )

    print("Updated Ravi's salary:")
    show_rows(
        connection.execute(
            """
            SELECT employee_id, first_name, salary
            FROM employees
            WHERE employee_id = 102
            """
        )
    )

    with transaction(connection):
        connection.execute(
            """
            INSERT INTO employees
            (employee_id, department_id, first_name, last_name, email,
             salary, hire_date, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (107, 3, "Isha", "Roy", "isha@example.com", 72000, "2026-01-10", 1),
        )

        connection.execute(
            """
            DELETE FROM employees
            WHERE employee_id = ?
            """,
            (107,),
        )

    print("Temporary record inserted and deleted successfully.")


def demonstrate_parameterized_queries(connection: sqlite3.Connection) -> None:
    section("10. PARAMETERIZED QUERIES AND SQL INJECTION")

    email = "asha@example.com"

    row = connection.execute(
        """
        SELECT employee_id, first_name, email
        FROM employees
        WHERE email = ?
        """,
        (email,),
    ).fetchone()

    print("Parameterized lookup:")
    print(dict(row) if row else "Not found")

    print(
        """
Never construct SQL by directly concatenating untrusted user input.

Unsafe conceptual pattern:
    SELECT ... WHERE email = '""" + email + """'

Preferred pattern:
    SELECT ... WHERE email = ?

The database driver sends the SQL structure and parameter value separately,
which prevents ordinary input from being interpreted as SQL syntax.
"""
    )


def demonstrate_constraints(connection: sqlite3.Connection) -> None:
    section("11. CONSTRAINTS AND DATA INTEGRITY")

    tests = [
        (
            "Duplicate unique email",
            """
            INSERT INTO employees
            (department_id, first_name, last_name, email, salary, hire_date)
            VALUES (1, 'Test', 'User', 'asha@example.com', 50000, '2026-01-01')
            """,
        ),
        (
            "Negative salary",
            """
            INSERT INTO employees
            (department_id, first_name, last_name, email, salary, hire_date)
            VALUES (1, 'Test', 'User', 'unique@example.com', -1, '2026-01-01')
            """,
        ),
        (
            "Unknown department",
            """
            INSERT INTO employees
            (department_id, first_name, last_name, email, salary, hire_date)
            VALUES (999, 'Test', 'User', 'unique2@example.com', 50000, '2026-01-01')
            """,
        ),
    ]

    for description, statement in tests:
        try:
            connection.execute(statement)
            connection.rollback()
            print(f"{description}: unexpectedly accepted")
        except sqlite3.IntegrityError as error:
            connection.rollback()
            print(f"{description}: rejected correctly -> {error}")


def demonstrate_indexes(connection: sqlite3.Connection) -> None:
    section("12. INDEXES AND QUERY PERFORMANCE")

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employees_department
        ON employees(department_id)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employees_salary
        ON employees(salary)
        """
    )

    print("Indexes created for common filtering and joining columns.")

    plan = connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT employee_id, first_name
        FROM employees
        WHERE department_id = ?
        """,
        (1,),
    ).fetchall()

    print("\nQuery plan:")
    show_rows(plan)

    print(
        """
Indexes can reduce lookup cost by avoiding a full table scan for suitable
queries. They also consume storage and make INSERT/UPDATE/DELETE operations
more expensive because index structures must be maintained.

Indexes should support actual access patterns rather than being added to
every column indiscriminately.
"""
    )


def demonstrate_transactions(connection: sqlite3.Connection) -> None:
    section("13. TRANSACTIONS AND ATOMICITY")

    connection.execute(
        """
        CREATE TABLE accounts (
            account_id INTEGER PRIMARY KEY,
            owner TEXT NOT NULL,
            balance REAL NOT NULL CHECK (balance >= 0)
        )
        """
    )

    connection.executemany(
        """
        INSERT INTO accounts (account_id, owner, balance)
        VALUES (?, ?, ?)
        """,
        [
            (1, "Alice", 1000),
            (2, "Bob", 500),
        ],
    )
    connection.commit()

    try:
        with transaction(connection):
            connection.execute(
                """
                UPDATE accounts
                SET balance = balance - ?
                WHERE account_id = ?
                """,
                (200, 1),
            )

            connection.execute(
                """
                UPDATE accounts
                SET balance = balance + ?
                WHERE account_id = ?
                """,
                (200, 2),
            )

            # A real system would perform business-rule validation here.
            sender_balance = connection.execute(
                """
                SELECT balance
                FROM accounts
                WHERE account_id = ?
                """,
                (1,),
            ).fetchone()[0]

            if sender_balance < 0:
                raise ValueError("Insufficient funds")

    except Exception as error:
        print(f"Transfer failed: {error}")

    print("\nAccount balances after successful transaction:")
    show_rows(
        connection.execute(
            """
            SELECT account_id, owner, balance
            FROM accounts
            ORDER BY account_id
            """
        )
    )

    print(
        """
Transactions are commonly discussed using ACID:

Atomicity    - all operations succeed or none do.
Consistency  - constraints and rules remain satisfied.
Isolation    - concurrent transactions should not incorrectly interfere.
Durability   - committed data survives appropriate system failures.

Exact isolation behavior depends on the database engine and configuration.
"""
    )


def demonstrate_normalization() -> None:
    section("14. NORMALIZATION")

    print(
        """
Consider an unnormalized conceptual table:

OrderID | CustomerName | CustomerEmail | Product1 | Product2

Problems:
  - repeating groups
  - duplicated customer information
  - difficult updates
  - awkward queries for an arbitrary number of products

A normalized relational design can separate the entities:

customers
  customer_id
  name
  email

orders
  order_id
  customer_id
  order_date

products
  product_id
  name
  price

order_items
  order_id
  product_id
  quantity

First Normal Form (1NF):
  Values should be atomic rather than storing repeating lists in one field.

Second Normal Form (2NF):
  Non-key attributes should depend on the whole candidate key, especially
  relevant when a table has a composite key.

Third Normal Form (3NF):
  Non-key attributes should not depend transitively on another non-key
  attribute.

Normalization reduces redundancy and update anomalies. Deliberate
denormalization can sometimes improve read performance, but it introduces
duplication that must be managed carefully.
"""
    )


def demonstrate_null_and_three_valued_logic(connection: sqlite3.Connection) -> None:
    section("15. NULL AND THREE-VALUED LOGIC")

    connection.execute(
        """
        CREATE TABLE nullable_examples (
            id INTEGER PRIMARY KEY,
            label TEXT,
            score INTEGER
        )
        """
    )

    connection.executemany(
        """
        INSERT INTO nullable_examples (id, label, score)
        VALUES (?, ?, ?)
        """,
        [
            (1, "complete", 90),
            (2, "missing", None),
            (3, "low", 20),
        ],
    )
    connection.commit()

    print("IS NULL:")
    show_rows(
        connection.execute(
            """
            SELECT id, label
            FROM nullable_examples
            WHERE score IS NULL
            """
        )
    )

    print("\nCOALESCE supplies a fallback:")
    show_rows(
        connection.execute(
            """
            SELECT
                id,
                label,
                COALESCE(score, 0) AS score_with_default
            FROM nullable_examples
            ORDER BY id
            """
        )
    )

    print(
        """
NULL does not mean zero, empty string, or false. It represents missing or
unknown information.

Comparisons involving NULL generally do not evaluate to TRUE. Use IS NULL
or IS NOT NULL when testing for NULL.
"""
    )


def demonstrate_views(connection: sqlite3.Connection) -> None:
    section("16. VIEWS")

    connection.execute(
        """
        CREATE VIEW active_employee_directory AS
        SELECT
            e.employee_id,
            e.first_name || ' ' || e.last_name AS employee,
            e.email,
            d.name AS department
        FROM employees AS e
        JOIN departments AS d
            ON e.department_id = d.department_id
        WHERE e.active = 1
        """
    )

    print("Querying a view:")
    show_rows(
        connection.execute(
            """
            SELECT *
            FROM active_employee_directory
            ORDER BY department, employee
            """
        )
    )

    print(
        """
A view stores a reusable query definition. It can simplify repeated
reporting logic and provide a controlled representation of underlying data.
The exact update behavior of views depends on the database system and view.
"""
    )


@dataclass
class Employee:
    employee_id: int
    name: str
    salary: float


def demonstrate_python_abstraction(connection: sqlite3.Connection) -> None:
    section("17. PYTHON APPLICATION LAYER")

    def find_employee(employee_id: int) -> Employee | None:
        row = connection.execute(
            """
            SELECT employee_id, first_name, last_name, salary
            FROM employees
            WHERE employee_id = ?
            """,
            (employee_id,),
        ).fetchone()

        if row is None:
            return None

        return Employee(
            employee_id=row["employee_id"],
            name=f"{row['first_name']} {row['last_name']}",
            salary=row["salary"],
        )

    employee = find_employee(101)
    print(employee)

    missing = find_employee(99999)
    print("Missing employee:", missing)


def demonstrate_testing_and_debugging(connection: sqlite3.Connection) -> None:
    section("18. VALIDATION, TESTING, AND DEBUGGING")

    def employee_exists(employee_id: int) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM employees
            WHERE employee_id = ?
            """,
            (employee_id,),
        ).fetchone()
        return row is not None

    assert employee_exists(101)
    assert not employee_exists(99999)

    count = connection.execute(
        "SELECT COUNT(*) FROM employees"
    ).fetchone()[0]

    assert count >= 1
    print("Database assertions passed.")
    print(
        """
Useful database debugging practices include:
  - inspect generated SQL
  - inspect parameter values without logging secrets
  - run EXPLAIN/EXPLAIN QUERY PLAN where supported
  - verify transaction boundaries
  - test constraints explicitly
  - test empty results
  - test duplicate data
  - test boundary values
  - test concurrent behavior in the production database
"""
    )


def demonstrate_security() -> None:
    section("19. DATABASE SECURITY")

    print(
        """
Important security principles:

1. Parameterize user-controlled values.
2. Use least-privilege database accounts.
3. Do not expose database credentials in source control.
4. Encrypt database connections where the deployment requires it.
5. Protect backups because backups contain sensitive data.
6. Restrict network access to database servers.
7. Validate authorization at the application layer.
8. Avoid returning unnecessary columns.
9. Log security-relevant events without logging passwords or secrets.
10. Patch the database engine and dependencies.
11. Use migrations to make schema changes controlled and repeatable.
12. Consider encryption at rest where the threat model requires it.

Authentication answers "who are you?".
Authorization answers "what are you allowed to do?".

A database constraint protects data integrity, while application
authorization protects business access rules. Production systems often need
both.
"""
    )


def demonstrate_schema_inspection(connection: sqlite3.Connection) -> None:
    section("20. INSPECTING DATABASE METADATA")

    print("Tables:")
    show_rows(
        connection.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view')
            ORDER BY type, name
            """
        )
    )

    print("\nEmployee columns:")
    show_rows(
        connection.execute(
            """
            PRAGMA table_info(employees)
            """
        )
    )


def main() -> None:
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row

    try:
        create_database(connection)
        insert_sample_data(connection)
        demonstrate_select(connection)
        demonstrate_conditions(connection)
        demonstrate_aggregates(connection)
        demonstrate_joins(connection)
        demonstrate_subqueries_and_ctes(connection)
        demonstrate_window_functions(connection)
        demonstrate_insert_update_delete(connection)
        demonstrate_parameterized_queries(connection)
        demonstrate_constraints(connection)
        demonstrate_indexes(connection)
        demonstrate_transactions(connection)
        demonstrate_normalization()
        demonstrate_null_and_three_valued_logic(connection)
        demonstrate_views(connection)
        demonstrate_python_abstraction(connection)
        demonstrate_testing_and_debugging(connection)
        demonstrate_security()
        demonstrate_schema_inspection(connection)

        section("21. COMPLETE")
        print(
            """
The examples covered database fundamentals from physical data concepts
through relational modeling, SQL querying, integrity, transactions,
performance, application integration, and production considerations.
"""
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
