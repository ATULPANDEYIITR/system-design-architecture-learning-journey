# Database Fundamentals: Tables, Records, Schemas, and Queries

## 1. Topic Introduction

A database is an organized system for storing, managing, retrieving, and protecting data.

Database fundamentals provide the foundation for application development, analytics, reporting, information systems, financial systems, enterprise software, and data engineering.

This study set focuses on relational database fundamentals:

- databases
- schemas
- tables
- columns
- rows and records
- primary keys
- foreign keys
- constraints
- relationships
- SQL queries
- filtering
- sorting
- aggregation
- grouping
- joins
- subqueries
- common table expressions
- window functions
- transactions
- indexes
- normalization
- NULL values
- views
- application integration
- validation
- security
- performance
- production architecture

The three implementations approach the subject differently:

- Python demonstrates database concepts through a real SQLite database.
- JavaScript builds an educational relational engine with native JavaScript data structures to make database mechanisms explicit.
- C++ presents an industry-style employee and project management case study using strongly typed structures, validation, indexing, joins, aggregation, and transactions.

---

## 2. Database Fundamentals

A database stores related information in a structured form.

A relational database organizes information primarily through tables.

For example, an employee table might conceptually contain:

| employee_id | first_name | last_name | department_id | salary |
|---|---|---|---:|---:|
| 101 | Asha | Sharma | 1 | 120000 |
| 102 | Ravi | Kumar | 1 | 95000 |
| 103 | Neha | Singh | 2 | 110000 |

Each row represents one employee.

Each column represents one attribute of an employee.

The table itself represents a collection of employee records.

A relational database adds formal rules around these records so that relationships and data integrity can be maintained.

---

## 3. Important Terminology

### Database

A database is a managed collection of related data.

Examples include:

- employee databases
- banking databases
- inventory databases
- customer databases
- hospital databases
- university databases
- financial market databases

### Database Management System

A Database Management System, or DBMS, is software that manages databases.

Common relational DBMS products include:

- PostgreSQL
- MySQL
- MariaDB
- Microsoft SQL Server
- Oracle Database
- SQLite

A DBMS provides capabilities such as:

- data storage
- querying
- transactions
- constraints
- concurrency control
- recovery
- indexing
- authentication
- authorization
- backup and recovery

### Relational Database

A relational database organizes data using relations, commonly represented as tables.

Tables can be connected through keys.

### Schema

A schema describes the structure and rules of database objects.

A schema can define:

- tables
- columns
- data types
- keys
- constraints
- indexes
- views
- relationships

For example, an employee table can specify that `employee_id` is an integer primary key and `email` must be unique.

### Table

A table is a structured collection of records.

An employee table stores employee records.

A project table stores project records.

A department table stores department records.

### Record

A record is one row in a table.

One employee is one employee record.

### Column

A column represents an attribute.

Examples:

- employee ID
- employee name
- salary
- department ID
- hire date

### Field

The term field is often used informally for an individual value or attribute in a record.

---

## 4. Relational Model

The relational model represents data using relations.

In practical SQL systems, a relation is generally represented as a table.

A table has:

- a name
- columns
- rows
- constraints

A simplified employee relation could be represented as:

`employees(employee_id, department_id, first_name, last_name, email, salary, active)`

The relation structure is different from the individual data values stored inside it.

This distinction is important because the schema defines what data is allowed to exist, while records represent the actual stored data.

---

## 5. Data Types

Database systems provide data types to describe valid values.

Typical relational data types include:

- integer
- decimal
- numeric
- floating-point
- character strings
- dates
- timestamps
- Boolean values
- binary data

The exact types differ between database engines.

For example:

`employee_id INTEGER`

means the column stores integer values.

`email TEXT`

means the column stores text.

`salary DECIMAL`

can be used for exact numeric values in systems that support the type.

For financial applications, exact decimal or numeric types are normally preferable to binary floating-point for monetary calculations.

---

## 6. Primary Keys

A primary key uniquely identifies a record.

Example:

`employee_id`

can identify each employee.

A primary key should provide stable and unique identity for a record.

In the Python implementation, the employees table uses:

`employee_id INTEGER PRIMARY KEY`

The C++ implementation models the same concept using the employee ID and an index.

Primary-key properties generally include:

- uniqueness
- non-null identity
- stable record identification

A table normally has one primary key constraint, although the key itself can consist of multiple columns.

---

## 7. Composite Keys

A composite key contains multiple columns.

The employee-project relationship is a common example.

An employee can work on many projects.

A project can have many employees.

The pair:

`employee_id + project_id`

can identify one assignment.

The Python schema implements:

`PRIMARY KEY (employee_id, project_id)`

This prevents the same employee from being assigned to the same project twice.

---

## 8. Foreign Keys

A foreign key connects records between tables.

For example:

`employees.department_id`

references:

`departments.department_id`

This establishes a relationship between employees and departments.

A foreign key can prevent invalid references.

For example, an employee should not normally reference department `999` if department `999` does not exist.

The Python implementation enables SQLite foreign-key enforcement with:

`PRAGMA foreign_keys = ON;`

The C++ implementation performs the corresponding validation in application code.

A database-level foreign key is generally preferable when the database supports it because the integrity rule remains enforced independently of application code.

---

## 9. Database Relationships

### One-to-One

One record corresponds to one record in another table.

This relationship is less common than one-to-many.

### One-to-Many

One department can contain many employees.

The relationship can be represented as:

`departments 1 -> many employees`

The employee stores the foreign key.

### Many-to-Many

An employee can work on multiple projects.

A project can contain multiple employees.

This requires an intermediate junction table:

`employee_projects`

Conceptually:

`employees -> employee_projects <- projects`

The junction table stores the two foreign keys.

---

## 10. Constraints

Constraints are rules enforced against database data.

Important constraints include:

### NOT NULL

Requires a value.

Example:

`email TEXT NOT NULL`

### UNIQUE

Prevents duplicate values.

Example:

`email TEXT UNIQUE`

### PRIMARY KEY

Provides unique row identity.

### FOREIGN KEY

Maintains relationships between tables.

### CHECK

Enforces a condition.

Example:

`salary >= 0`

The Python implementation uses all of these constraint types.

The JavaScript and C++ implementations also perform explicit validation to demonstrate how these rules work conceptually.

Constraints are important because application validation alone is not always sufficient.

Multiple applications may write to the same database, and the database should protect critical integrity rules itself.

---

## 11. CRUD

CRUD represents four fundamental operations:

- Create
- Read
- Update
- Delete

### Create

SQL uses `INSERT`.

Example:

`INSERT INTO employees (...) VALUES (...)`

### Read

SQL uses `SELECT`.

Example:

`SELECT first_name, salary FROM employees`

### Update

SQL uses `UPDATE`.

Example:

`UPDATE employees SET salary = salary * 1.05`

### Delete

SQL uses `DELETE`.

Example:

`DELETE FROM employees WHERE employee_id = 107`

The Python implementation executes these operations against SQLite.

The JavaScript implementation models them through `insert`, `select`, `update`, and `delete`.

The C++ implementation exposes corresponding typed methods.

---

## 12. SELECT Queries

A basic query has the conceptual form:

`SELECT columns FROM table`

For example:

`SELECT first_name, last_name, salary FROM employees`

The selected columns are called the projection.

Selecting only required columns is usually preferable to retrieving unnecessary data.

Avoid indiscriminate use of:

`SELECT *`

in production application queries when the application only needs a subset of columns.

This reduces unnecessary data transfer and makes application dependencies clearer.

---

## 13. WHERE

`WHERE` filters rows.

Example:

`WHERE salary >= 100000`

Only records satisfying the condition are returned.

Multiple conditions can be combined.

Example:

`WHERE active = 1 AND salary > 90000`

Other operators include:

- `=`
- `<>`
- `!=`
- `<`
- `>`
- `<=`
- `>=`
- `IN`
- `BETWEEN`
- `LIKE`
- `IS NULL`
- `IS NOT NULL`

---

## 14. AND, OR, and NOT

Boolean operators allow complex conditions.

Example:

`WHERE active = 1 AND salary > 100000`

requires both conditions to be true.

Example:

`WHERE department_id = 1 OR department_id = 4`

accepts either department.

Example:

`WHERE NOT active = 1`

can be used to express the opposite condition, although explicit comparisons are often clearer.

Parentheses are important when combining multiple logical operators because precedence can affect interpretation.

For example:

`A OR B AND C`

is not necessarily equivalent to:

`(A OR B) AND C`

Use parentheses when the intended logic needs to be made explicit.

---

## 15. IN

`IN` compares a value against a set.

Example:

`WHERE department_id IN (1, 4)`

This can be clearer than repeatedly writing multiple equality conditions.

Parameterized applications should still pass dynamic values safely rather than constructing SQL by concatenating user input.

---

## 16. BETWEEN

`BETWEEN` checks whether a value falls within a range.

Example:

`WHERE salary BETWEEN 80000 AND 120000`

The boundary behavior should be understood for the particular data type and database engine.

For date and timestamp filtering, explicit half-open ranges such as:

`date >= start AND date < end`

can often be safer when dealing with time intervals.

---

## 17. LIKE

`LIKE` performs pattern matching in SQL.

Example:

`email LIKE '%@example.com'`

The `%` wildcard represents zero or more characters in standard SQL pattern matching.

The exact behavior of case sensitivity and pattern matching can vary between database systems and configurations.

For large-scale text search, ordinary `LIKE` may not be sufficient and specialized indexing or full-text search may be more appropriate.

---

## 18. ORDER BY

`ORDER BY` sorts query results.

Example:

`ORDER BY salary DESC`

sorts from highest salary to lowest.

`ASC` represents ascending order.

`DESC` represents descending order.

Sorting is performed after the relevant result set has been produced according to the query plan.

If ordering is important to application behavior, specify it explicitly rather than relying on accidental physical row order.

---

## 19. LIMIT

`LIMIT` restricts the number of returned rows in systems such as SQLite and PostgreSQL.

Example:

`LIMIT 10`

can retrieve a small result set.

Pagination should be designed carefully for large datasets.

Offset-based pagination can become expensive at high offsets.

Keyset or cursor-based pagination can often provide more stable performance for large ordered datasets.

---

## 20. Aggregate Functions

Common aggregate functions include:

- `COUNT`
- `SUM`
- `AVG`
- `MIN`
- `MAX`

Example:

`SELECT COUNT(*) FROM employees`

counts rows.

Example:

`SELECT AVG(salary) FROM employees`

calculates average salary.

Example:

`SELECT SUM(salary) FROM employees`

calculates total payroll.

Aggregate functions typically operate over a set of rows and return a summarized result.

---

## 21. GROUP BY

`GROUP BY` divides rows into groups.

Example:

`GROUP BY department_id`

allows statistics to be calculated separately for each department.

A query can calculate:

- employee count per department
- average salary per department
- total payroll per department

The Python and JavaScript implementations demonstrate equivalent grouping logic.

The C++ case study uses a map keyed by department ID to represent grouped aggregation.

---

## 22. HAVING

`HAVING` filters groups.

This differs from `WHERE`.

`WHERE` filters individual rows before aggregation.

`HAVING` filters groups after grouping.

Conceptually:

`WHERE salary > 50000`

filters employee rows.

`HAVING COUNT(*) >= 2`

filters department groups.

Understanding this distinction is important for aggregate queries.

---

## 23. JOINs

A join combines related rows.

### INNER JOIN

Returns matching rows from both sides.

Example:

`employees JOIN departments ON employees.department_id = departments.department_id`

### LEFT JOIN

Returns all rows from the left table and matching rows from the right table.

This is useful when the absence of a related record must still be represented.

The Python implementation demonstrates both inner and left joins.

The JavaScript implementation manually performs equivalent relationship traversal.

The C++ implementation uses typed structures and indexes to produce joined records.

---

## 24. Cartesian Products

A join without an appropriate relationship condition can create a Cartesian product.

If table A has 100 rows and table B has 100 rows, an unrestricted Cartesian combination can produce up to 10,000 combinations.

Accidental Cartesian products are a common query-design problem.

Always verify join conditions and result cardinality.

---

## 25. Subqueries

A subquery is a query nested inside another query.

The Python implementation demonstrates:

`salary > (SELECT AVG(salary) FROM employees)`

This finds employees whose salary is above the company average.

Subqueries can appear in:

- `WHERE`
- `FROM`
- `SELECT`
- `HAVING`

The optimizer may transform a query internally, so the syntactic presence of a subquery does not by itself determine performance.

---

## 26. Common Table Expressions

A Common Table Expression, or CTE, is introduced using `WITH`.

The Python implementation creates department statistics in a CTE and then queries those results.

CTEs can improve readability for complex transformations.

They are useful for:

- multi-stage queries
- recursive relationships
- reusable intermediate result definitions
- reporting logic

Performance behavior depends on the database engine and query.

---

## 27. Window Functions

Window functions calculate information across related rows while preserving individual rows.

The Python implementation uses:

`RANK() OVER (PARTITION BY department_id ORDER BY salary DESC)`

This ranks employees inside each department.

It also calculates department averages while keeping one row per employee.

This differs from `GROUP BY`.

`GROUP BY` usually collapses each group into fewer rows.

A window function can calculate a group-level value while retaining the original row structure.

Common window functions include:

- `ROW_NUMBER`
- `RANK`
- `DENSE_RANK`
- `LAG`
- `LEAD`
- `SUM() OVER`
- `AVG() OVER`

Window functions are particularly useful in analytics and reporting.

---

## 28. NULL

`NULL` represents missing, unknown, or inapplicable information depending on the context.

It is not equivalent to:

- zero
- false
- empty string

This distinction is important.

Incorrect conceptual pattern:

`WHERE score = NULL`

Correct pattern:

`WHERE score IS NULL`

The Python implementation demonstrates `IS NULL` and `COALESCE`.

`COALESCE` returns the first non-null expression.

Example:

`COALESCE(score, 0)`

can provide a fallback value.

NULL introduces three-valued logic:

- TRUE
- FALSE
- UNKNOWN

This is an important source of subtle SQL behavior.

---

## 29. Views

A view is a named query definition.

The Python implementation creates an `active_employee_directory` view.

A view can:

- simplify repeated queries
- hide query complexity
- expose selected data
- provide a stable logical interface

View capabilities vary by database system.

Some views can be updated directly under certain conditions, while complex views may require special mechanisms.

---

## 30. Transactions

A transaction groups related database operations into one logical unit.

The Python implementation demonstrates a transaction for account transfers.

The C++ implementation models transactions by saving state and restoring it during rollback.

The major ACID properties are:

### Atomicity

All operations in the transaction succeed, or the transaction is rolled back.

### Consistency

Database constraints and rules remain satisfied.

### Isolation

Concurrent transactions should not produce incorrect interference according to the configured isolation model.

### Durability

Committed changes survive appropriate system failures.

The exact implementation of these properties depends on the database engine, storage system, configuration, and transaction isolation level.

---

## 31. Transaction Example

A bank transfer can require:

1. subtract money from account A
2. add money to account B

These operations should not be treated as two unrelated writes.

If the first succeeds and the second fails, the database must not leave the system with money removed from A without being added to B.

A transaction provides the atomic boundary.

This is a central database design principle.

---

## 32. Rollback

Rollback reverses changes made within an unsuccessful transaction.

Typical reasons for rollback include:

- constraint failure
- insufficient balance
- application exception
- serialization failure
- deadlock handling
- business-rule failure

The exact behavior is database-specific.

The C++ case study intentionally implements a simplified snapshot-based rollback to make the mechanism visible.

A production database normally provides transaction management internally rather than requiring an application to copy the entire database state.

---

## 33. Parameterized Queries

Parameterized queries separate SQL structure from user-controlled values.

Conceptually:

`SELECT employee_id FROM employees WHERE email = ?`

The email value is supplied separately.

This is important for preventing SQL injection.

Unsafe application design often looks conceptually like:

`"SELECT ... WHERE email = '" + userInput + "'"`

A malicious input can change the meaning of the SQL statement.

The Python implementation uses SQLite parameters throughout important queries.

The JavaScript implementation explains the same principle even though it does not depend on an external SQL driver.

The C++ application would use parameter binding when connected to a production database driver.

---

## 34. SQL Injection

SQL injection occurs when untrusted input becomes part of executable SQL syntax.

Potential consequences can include:

- unauthorized data access
- data modification
- data deletion
- authentication bypass
- database compromise

Parameterized queries are one of the primary defenses.

Other security controls include:

- least privilege
- input validation
- authorization
- secure database configuration
- restricted network access
- safe error handling

Input validation is not a substitute for parameterized SQL.

---

## 35. Normalization

Normalization organizes data to reduce unnecessary duplication and dependency problems.

### First Normal Form

1NF generally requires atomic values and eliminates repeating groups.

Poor design:

`product1`, `product2`, `product3`

Better design:

`order_items`

with one row per product associated with an order.

### Second Normal Form

2NF addresses partial dependencies on part of a composite key.

This is most relevant when a relation has a composite candidate key.

### Third Normal Form

3NF addresses transitive dependencies between non-key attributes.

For example, if:

`employee_id -> department_id`

and:

`department_id -> department_name`

then storing department name redundantly in every employee record can create update anomalies.

A separate department table avoids unnecessary duplication.

---

## 36. Normalization Trade-Offs

Normalization can provide:

- reduced redundancy
- improved consistency
- fewer update anomalies
- clearer entity boundaries

It can also increase the number of joins needed for some queries.

Denormalization can sometimes improve read performance by storing derived or repeated information.

Denormalization introduces consistency responsibilities.

It should generally be a deliberate design decision based on actual workload requirements rather than an automatic optimization.

---

## 37. Anomalies

Poor database design can cause three common anomalies.

### Insert anomaly

It may be impossible to add information without unrelated information.

### Update anomaly

The same fact may have to be updated in multiple rows.

If one copy is missed, inconsistent data results.

### Delete anomaly

Deleting one record may accidentally remove the only stored copy of an unrelated fact.

Normalization helps reduce these problems.

---

## 38. Indexes

An index is an auxiliary data structure that helps the database locate rows efficiently.

The Python implementation creates indexes on:

- department ID
- salary

The JavaScript implementation creates an index map for department lookup.

The C++ case study uses `unordered_map` indexes for primary-key lookup.

An index can significantly reduce lookup work for suitable queries.

Without an index, an equality search may require a full scan:

`O(n)`

With a hash-like index, average lookup can approach:

`O(1)`

A balanced tree index often provides:

`O(log n)`

lookup characteristics.

Actual database behavior depends on the engine and index implementation.

---

## 39. Index Trade-Offs

Indexes consume resources.

Costs include:

- storage
- memory
- index maintenance
- slower writes
- additional complexity

A table with many indexes can become expensive to update.

Indexes should be based on real access patterns.

Common index candidates include columns used frequently for:

- filtering
- joining
- sorting
- uniqueness
- foreign-key lookups

Not every column needs an index.

---

## 40. Composite Indexes

A composite index contains multiple columns.

For example:

`(department_id, salary)`

may support queries that filter or order by those columns.

Column order matters.

An index on:

`(department_id, salary)`

is not automatically equivalent to:

`(salary, department_id)`

because the database can exploit the indexed ordering differently.

Index design should reflect actual query patterns.

---

## 41. Query Performance

Database performance depends on:

- table size
- indexes
- data distribution
- query structure
- join strategy
- sorting
- aggregation
- network latency
- disk I/O
- memory
- concurrency
- database configuration
- query optimizer decisions

A query that performs well on 1,000 rows may perform poorly on 100 million rows.

Performance testing should use representative data volumes.

---

## 42. Query Plans

Database systems can expose query plans.

The Python implementation uses SQLite's:

`EXPLAIN QUERY PLAN`

Query plans can reveal whether the database is:

- scanning a table
- using an index
- sorting
- joining through an index
- creating temporary structures

Query-plan analysis is more reliable than guessing about performance.

---

## 43. Python Implementation

The Python implementation uses SQLite through the standard-library `sqlite3` module.

This makes the implementation executable without installing a third-party package.

The implementation creates four primary tables:

- `departments`
- `employees`
- `projects`
- `employee_projects`

It demonstrates a real relational schema rather than simply storing records in Python lists.

Important Python features include:

- `sqlite3.Connection`
- parameterized queries
- transactions
- `sqlite3.Row`
- `executemany`
- constraint exceptions
- query-plan inspection
- views
- CTEs
- window functions

The use of SQLite makes the SQL examples directly executable.

---

## 44. Python Schema Design

The employee table contains:

- employee ID
- department ID
- first name
- last name
- email
- salary
- hire date
- active status

The department table contains:

- department ID
- name
- budget

The project table contains:

- project ID
- project name
- budget
- status

The employee-project table resolves the many-to-many relationship.

This demonstrates entity separation and relationship modeling.

---

## 45. Python Parameter Binding

The Python code uses statements such as:

`WHERE employee_id = ?`

with values supplied separately.

For example, a query can pass:

`(employee_id,)`

as its parameter tuple.

This prevents the value from being treated as SQL syntax.

It is one of the most important practical database security patterns demonstrated by the script.

---

## 46. Python Transactions

The `transaction` context manager demonstrates application-level transaction handling.

Its structure is:

1. execute operations
2. commit if successful
3. rollback if an exception occurs

This makes transaction boundaries explicit.

A production application should also consider:

- isolation level
- deadlocks
- retry behavior
- connection management
- transaction duration
- locking
- concurrency

---

## 47. JavaScript Implementation

The JavaScript implementation intentionally does not require an external npm package.

Instead, it builds a small educational relational engine.

This is useful because the mechanisms behind database operations become visible.

The `Table` class models:

- columns
- primary keys
- unique constraints
- NOT NULL constraints
- foreign keys
- CHECK constraints
- rows
- indexes

The `Database` class models:

- tables
- schema registration
- foreign-key validation
- transactions
- commit
- rollback

This is not intended to replace a production database engine.

It is a conceptual implementation demonstrating how database features can be represented programmatically.

---

## 48. JavaScript Query Model

The JavaScript `select` method supports:

- filtering
- column selection
- sorting
- limiting

For example, a query can conceptually perform:

`WHERE active = 1`

through a JavaScript predicate.

This corresponds to relational filtering.

Projection is represented by selecting specific columns.

Sorting is represented through a comparison function.

The example demonstrates that SQL is not merely a syntax collection. It expresses operations over sets of relational data.

---

## 49. JavaScript Joins

The JavaScript implementation performs join-like operations by looking up related records.

For example:

- employee department IDs are matched against department IDs
- employee project assignments are matched against employees and projects

This exposes the core mechanism behind a relational join.

A production database performs such operations using optimized query execution strategies rather than simple JavaScript array scans.

---

## 50. JavaScript Indexes

The JavaScript `Table` class supports a simple index structure using `Map`.

For a department ID index:

`departmentId -> matching rows`

This demonstrates the conceptual difference between:

- scanning every row
- using an auxiliary lookup structure

The example makes the performance trade-off explicit.

---

## 51. C++ Case Study

The C++ implementation models an employee operations database.

The system contains:

- departments
- employees
- projects
- employee-project assignments
- accounts

The case study provides a more strongly typed representation of database records.

C++ structures such as `Employee`, `Department`, `Project`, and `EmployeeProject` represent schema entities.

The `EmployeeDatabase` class acts as the persistence and validation layer for the educational system.

---

## 52. C++ Data Structures

The implementation uses:

- `vector` for stored records
- `unordered_map` for primary-key indexes
- `map` for grouped department statistics
- `set` for allowed status values
- `optional` for potentially missing lookup results
- exceptions for validation and transaction failures

These structures illustrate how database-like mechanisms can be represented in an application.

---

## 53. C++ Primary-Key Index

The employee database maintains:

`unordered_map<int, size_t> employeeIndex`

This maps an employee ID to its location in the employee vector.

Without the index, a lookup would scan the vector.

With the index, primary-key lookup has approximately constant average complexity under typical hash-table assumptions.

The implementation rebuilds indexes when records are inserted or deleted.

A production database maintains its indexes internally and uses much more sophisticated storage and concurrency mechanisms.

---

## 54. C++ Validation

The case study validates:

- positive identifiers
- non-empty names
- unique emails
- non-negative salaries
- valid department references
- valid project statuses
- valid project references
- unique employee-project assignments

This demonstrates a key principle:

Data validation should exist at the correct architectural layers.

Application validation provides immediate feedback.

Database constraints provide durable integrity protection.

Both can be valuable.

---

## 55. C++ Transactions

The C++ case study implements a simplified transaction system.

Before the transaction:

- database state is copied

During the transaction:

- operations execute

On success:

- changes are retained

On failure:

- saved state is restored

This demonstrates atomicity conceptually.

It is not a substitute for a production transaction manager.

Real database engines must handle:

- concurrent connections
- locking
- isolation
- logging
- crash recovery
- durability
- deadlocks
- serialization conflicts

Those concerns are significantly more complex than copying application data structures.

---

## 56. Account Transfer Case Study

The C++ program models a financial transfer.

The transfer contains two related operations:

1. subtract money from the sender
2. add money to the receiver

If the sender does not have sufficient funds, the operation fails.

The transaction wrapper prevents the unsuccessful operation from leaving a partial state.

This is a classic example of why transactions are important.

---

## 57. Error Handling

Database operations can fail for many reasons.

Examples include:

- invalid input
- duplicate keys
- foreign-key violations
- constraint violations
- unavailable connections
- transaction conflicts
- deadlocks
- timeouts
- malformed queries
- permission errors

The Python implementation handles SQLite exceptions.

The JavaScript implementation defines database-specific error classes.

The C++ implementation uses typed exceptions such as `ConstraintError` and `TransactionError`.

Error handling should distinguish expected validation failures from infrastructure failures where appropriate.

---

## 58. Testing Database Code

Database tests should verify:

- successful inserts
- invalid inserts
- duplicate keys
- foreign-key violations
- updates
- deletes
- empty result sets
- boundary values
- NULL behavior
- transaction rollback
- transaction commit
- authorization behavior
- query results
- migration behavior

The Python implementation contains assertions for basic lookup behavior.

A production test suite should use isolated test databases and deterministic test data.

---

## 59. Edge Cases

Important database edge cases include:

### Empty tables

Queries must handle zero matching records.

### Duplicate values

Unique constraints should reject duplicates.

### Missing references

Foreign keys should reject invalid references.

### NULL

Queries must distinguish NULL from ordinary values.

### Zero

Zero is a legitimate numeric value and should not be confused with missing data.

### Negative values

Business constraints may prohibit them.

### Large values

Numeric precision and integer ranges should be considered.

### Large result sets

Applications should use pagination or streaming where appropriate.

### Concurrent updates

Applications must account for transactions and isolation behavior.

### Failed transactions

Partial changes must not violate business invariants.

---

## 60. Common Mistakes

### Mistake 1: No primary key

Without reliable row identity, updates and relationships become difficult.

### Mistake 2: Storing multiple values in one column

For example:

`project_ids = "201,202,203"`

This complicates filtering, validation, joins, and indexing.

A junction table is normally more appropriate for many-to-many relationships.

### Mistake 3: Duplicating entity data

Repeatedly storing department names in employee rows creates update anomalies.

### Mistake 4: Building SQL with string concatenation

This creates SQL injection risk.

Use parameterized queries.

### Mistake 5: Ignoring transactions

Related operations can leave inconsistent data if one operation fails.

### Mistake 6: Assuming row order

Without an explicit `ORDER BY`, applications should not assume a particular result ordering.

### Mistake 7: Indexing everything

Indexes improve some queries but increase write and storage costs.

### Mistake 8: Ignoring NULL semantics

NULL does not behave like an ordinary value.

### Mistake 9: Returning unnecessary data

Selecting excessive columns can increase memory, network, and processing costs.

### Mistake 10: Trusting application validation alone

Critical integrity rules should be enforced by the database where possible.

---

## 61. Security Considerations

Database security involves multiple layers.

### Authentication

Determines who is connecting.

### Authorization

Determines what the identity is allowed to do.

### Least Privilege

A database account should receive only the permissions required for its responsibilities.

An application that only reads data does not normally need unrestricted write or administrative permissions.

### SQL Injection Prevention

Use parameterized queries.

### Secret Management

Database passwords and connection secrets should not be committed to source control.

### Network Security

Database services should not be exposed unnecessarily to untrusted networks.

### Encryption

Sensitive database connections may require encryption in transit.

Sensitive stored data may require encryption at rest depending on the threat model and regulatory environment.

### Backup Security

Backups contain database information and therefore require appropriate access controls.

### Logging

Security-relevant events should be recorded while avoiding sensitive information such as passwords and authentication tokens.

---

## 62. Application Architecture

A practical application can separate database responsibilities into layers.

### API or Presentation Layer

Receives user requests.

### Service Layer

Applies business rules.

### Repository Layer

Encapsulates database access.

### Database Layer

Provides:

- persistence
- constraints
- transactions
- indexes
- queries

### Migration Layer

Manages schema changes over time.

This separation reduces coupling and makes testing easier.

The JavaScript implementation demonstrates this concept through the `EmployeeRepository` example.

The C++ case study describes the same architecture conceptually.

---

## 63. Schema Evolution

Database schemas change over time.

Examples include:

- adding a column
- creating a new table
- adding an index
- changing a constraint
- renaming an entity
- introducing a relationship

Production systems should use controlled migrations rather than manually modifying production schemas without tracking the change.

A migration should be:

- versioned
- reviewable
- repeatable where appropriate
- tested
- compatible with deployment strategy

Schema changes can require special care when old and new application versions temporarily coexist.

---

## 64. Production Considerations

A production relational database commonly requires attention to:

- connection pooling
- transactions
- concurrency
- isolation levels
- indexes
- query plans
- backups
- disaster recovery
- monitoring
- auditing
- security
- schema migrations
- replication where needed
- high availability where required
- capacity planning

The Python SQLite implementation is intentionally simple.

The JavaScript implementation is educational.

The C++ case study is an architectural model.

A production system should rely on a mature database engine for persistence and concurrency management.

---

## 65. Python, JavaScript, and C++ Comparison

| Aspect | Python | JavaScript | C++ |
|---|---|---|---|
| Main purpose | Real SQL database demonstration | Mechanism-level educational model | Typed industry-style case study |
| Database technology | SQLite | In-memory custom model | In-memory custom model |
| External dependency | None beyond standard library | None | C++ standard library |
| SQL execution | Yes | No external SQL engine | No external SQL engine |
| Schema constraints | Database-enforced | Application model | Application model |
| Transactions | SQLite transaction handling | Snapshot model | Snapshot model |
| Index demonstration | SQLite query plan | JavaScript Map | unordered_map |
| Typing | Dynamic | Dynamic | Static |
| Joins | Actual SQL | Explicit relationship traversal | Typed relationship traversal |
| Aggregation | SQL aggregate functions | JavaScript iteration | C++ grouping |
| Best educational focus | SQL and real DB behavior | Internal concepts | Systems design and typed implementation |

Each implementation highlights a different aspect of database fundamentals.

---

## 66. Why SQLite Is Useful for the Python Implementation

SQLite provides:

- relational tables
- SQL
- constraints
- transactions
- indexes
- views
- CTEs
- window functions
- query-plan inspection

It is embedded and requires no separate database server for basic use.

This makes it useful for demonstrating actual relational database behavior in a self-contained Python program.

---

## 67. Why JavaScript Uses an Educational Engine

A real database driver would hide many mechanisms behind APIs.

The custom JavaScript implementation intentionally exposes concepts such as:

- table storage
- uniqueness validation
- foreign-key validation
- indexing
- filtering
- sorting
- transactions

This helps demonstrate that a database system is more than a collection of arrays.

A real DBMS also has sophisticated:

- query parsing
- query optimization
- storage engines
- transaction logs
- locking
- concurrency control
- recovery mechanisms

The educational engine does not attempt to reproduce those production features.

---

## 68. Why C++ Is Used for the Case Study

C++ makes data structures and resource-oriented implementation decisions explicit.

The case study uses:

- structures for records
- containers for tables
- hash maps for indexes
- exceptions for failures
- optional values for missing records
- typed transaction operations

This makes the connection between database concepts and systems programming visible.

It also illustrates why a database should normally be treated as a specialized persistence system rather than replaced casually by application data structures.

---

## 69. Performance Comparison

A full table scan commonly has:

`O(n)`

time complexity.

Sorting is commonly:

`O(n log n)`

A hash-based lookup can have approximately:

`O(1)`

average lookup complexity.

A balanced tree index often provides:

`O(log n)`

lookup complexity.

For joins, possible strategies include:

- nested-loop joins
- indexed nested-loop joins
- hash joins
- merge joins

The best strategy depends on:

- table sizes
- indexes
- data distribution
- join predicates
- available memory
- database optimizer
- concurrency

Complexity estimates are useful, but actual database performance must be measured with representative workloads.

---

## 70. Database Design Principles Demonstrated

The implementations demonstrate several important principles:

1. Give important entities stable identifiers.
2. Model relationships explicitly.
3. Use constraints to protect data integrity.
4. Keep repeated entity information under control.
5. Use parameterized queries.
6. Group related changes into transactions.
7. Add indexes based on actual access patterns.
8. Inspect query plans when performance matters.
9. Handle NULL deliberately.
10. Separate application logic from persistence logic.
11. Test both successful and failing operations.
12. Treat database security as a system-level concern.
13. Design schemas for correctness before optimizing them.
14. Measure production workloads rather than relying only on theoretical assumptions.

---

## 71. Practical Applications

The same concepts apply to many real systems.

### Banking

Tables can represent:

- customers
- accounts
- transactions
- branches

Transactions are essential for atomic financial operations.

### E-Commerce

Tables can represent:

- customers
- products
- orders
- order items
- payments
- shipments

The order-item relationship is a common many-to-many-style association between orders and products.

### Human Resources

Tables can represent:

- employees
- departments
- roles
- salaries
- projects

The C++ case study follows this pattern.

### Education

Tables can represent:

- students
- courses
- instructors
- enrollments

Student-course enrollment is naturally modeled through a junction table.

### Inventory

Tables can represent:

- products
- warehouses
- stock levels
- suppliers
- purchase orders

### Analytics

Database queries can calculate:

- counts
- averages
- rankings
- trends
- totals
- grouped statistics

Window functions are particularly useful for analytical reporting.

---

## 72. Important Distinctions

### Database vs Table

A database contains tables and other database objects.

A table is one structured collection inside the database.

### Row vs Column

A row represents one record.

A column represents an attribute.

### Primary Key vs Foreign Key

A primary key identifies a record.

A foreign key references a record in another table.

### WHERE vs HAVING

`WHERE` filters rows.

`HAVING` filters groups.

### GROUP BY vs Window Function

`GROUP BY` generally collapses rows into groups.

Window functions calculate across groups while retaining individual rows.

### NULL vs Zero

NULL means missing or unknown information.

Zero is a numeric value.

### Constraint vs Application Validation

A constraint is enforced by the database.

Application validation occurs before or around database operations.

Reliable systems may use both.

### Index vs Table

A table stores the primary records.

An index is an auxiliary structure that helps locate records efficiently.

---

## 73. Implementation Checklist

A sound relational design should consider:

- [x] entities
- [x] tables
- [x] columns
- [x] data types
- [x] primary keys
- [x] foreign keys
- [x] uniqueness
- [x] required values
- [x] business constraints
- [x] one-to-many relationships
- [x] many-to-many relationships
- [x] CRUD
- [x] filtering
- [x] sorting
- [x] aggregation
- [x] joins
- [x] subqueries
- [x] CTEs
- [x] window functions
- [x] transactions
- [x] rollback
- [x] indexes
- [x] query plans
- [x] normalization
- [x] NULL handling
- [x] views
- [x] validation
- [x] testing
- [x] SQL injection prevention
- [x] application architecture
- [x] production considerations

---

## 74. Relationship Between the Three Implementations

The Python implementation is the closest to actual SQL database development because it uses SQLite.

The JavaScript implementation focuses on understanding the mechanisms behind database operations. Its `Table` and `Database` classes make concepts such as constraints, indexes, and transactions explicit.

The C++ implementation focuses on a realistic system design. It demonstrates how strongly typed structures, indexes, validation, transactions, relationships, and application architecture can work together.

Together, the implementations distinguish three useful perspectives:

1. using a database;
2. understanding database mechanisms;
3. designing software around database concepts.

The implementations intentionally remain self-contained while modeling the core behavior required to understand relational database fundamentals.
