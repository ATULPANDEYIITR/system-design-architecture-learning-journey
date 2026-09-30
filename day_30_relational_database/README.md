# Relational Databases: SQL, Relationships, and Constraints

## Topic Scope

This project studies relational database design through three connected areas:

- SQL as the language used to define, query, modify, and analyze relational data.
- Relationships as the structural connections between entities.
- Constraints as database-enforced rules that preserve valid data and protect relationships.

The implementations use an order-management domain because it naturally contains customers, profiles, products, orders, and order items. This produces realistic one-to-one, one-to-many, and many-to-many relationships without introducing unrelated database concepts.

The Python implementation uses SQLite directly, making the SQL mechanisms executable. The JavaScript implementation models a database-service boundary with asynchronous behavior and event-driven operations. The C++ implementation presents a repository-style database engine with explicit relational validation, indexes, and transaction snapshots.

## Relational Model

A relational database stores information in relations, commonly represented as tables. A table contains rows representing records and columns representing attributes.

The schema used in this project separates business entities according to their responsibilities.

| Table | Primary key | Important relationships | Purpose |
|---|---|---|---|
| `customers` | `customer_id` | Parent of orders and profile | Stores customer identity |
| `customer_profiles` | `customer_id` | Foreign key to customers | Stores one profile per customer |
| `products` | `product_id` | Referenced by order items | Stores product and current inventory data |
| `orders` | `order_id` | Foreign key to customers | Represents a customer purchase |
| `order_items` | `(order_id, product_id)` | Foreign keys to orders and products | Resolves the order-product many-to-many relationship |

The separation is important because a product can appear in many orders, while an order can contain many products. Putting products directly into an order row would not represent that relationship cleanly.

## SQL and Data Definition

The Python program creates the schema using SQL `CREATE TABLE` statements.

A primary key provides a stable identity for a row. For example, `customers.customer_id` identifies a customer independently of the customer's name or email address.

The `order_items` table uses a composite primary key:

`PRIMARY KEY (order_id, product_id)`

This prevents the same product from appearing twice as separate rows in the same order. Quantity remains an attribute of the relationship between an order and a product.

Foreign keys explicitly connect tables:

`orders.customer_id REFERENCES customers(customer_id)`

and:

`order_items.product_id REFERENCES products(product_id)`

These references allow the database to reject an order that points to a nonexistent customer or an order item that points to a nonexistent product.

The Python program explicitly enables SQLite foreign-key enforcement with `PRAGMA foreign_keys = ON`. This matters because defining a foreign key and enforcing it are separate concerns in SQLite.

## Constraints

Constraints move important integrity rules into the database layer rather than relying exclusively on application code.

### `NOT NULL`

Required attributes such as a customer's name, email, or an order's customer identifier use `NOT NULL`.

This prevents a row from being stored without a value where the schema requires one.

### `UNIQUE`

Customer email addresses and product SKUs are unique.

The customer table contains:

`email TEXT NOT NULL UNIQUE`

The product table contains:

`sku TEXT NOT NULL UNIQUE`

A duplicate business identifier is therefore rejected by the database.

The Python program deliberately attempts duplicate insertion to demonstrate the resulting integrity error. The JavaScript and C++ implementations also enforce uniqueness at their persistence-model boundaries.

### `CHECK`

The schema uses checks such as:

`CHECK (unit_price >= 0)`

and:

`CHECK (quantity > 0)`

The order status is also restricted to a defined set of domain values.

These constraints prevent structurally valid SQL statements from creating semantically invalid business data.

### `DEFAULT`

Columns such as `created_at` and `order_status` have defaults.

A default provides a value when the caller does not explicitly supply one. It is useful for predictable creation behavior, but it should not be treated as a substitute for validation.

## Relationships

Relationships describe how records in different tables correspond to one another. The three major relationship forms represented in this project are deliberately implemented differently.

### One-to-one

A customer has one profile.

The `customer_profiles.customer_id` column is both a primary key and a foreign key to `customers`.

Because the same value cannot occur twice as a primary key, a customer cannot have two profile rows.

This structure is useful when profile information has a separate lifecycle or storage responsibility from the core customer record.

### One-to-many

One customer can have many orders.

The relationship is represented by:

`orders.customer_id -> customers.customer_id`

The customer is the parent and orders are the child records.

The Python program demonstrates this with an `INNER JOIN` between `customers` and `orders`. The C++ implementation represents the same relationship through `ordersByCustomerIndex`, allowing customer-specific order retrieval without scanning every order.

### Many-to-many

An order can contain multiple products, and a product can appear in multiple orders.

A direct foreign key from `orders` to `products` cannot represent that relationship because one order needs multiple product references.

`order_items` acts as the associative table:

`orders -> order_items <- products`

It contains the relationship-specific attributes `quantity` and `unit_price`.

This design is central to the project because it demonstrates that a many-to-many relationship normally requires a separate relation.

## Why `unit_price` Appears in `order_items`

The `products` table stores the current product price. The `order_items` table stores the price at the time of purchase.

These values intentionally have different meanings.

If a product currently costs 90,000 but an earlier customer purchased it for 85,000, historical order reporting must continue to use 85,000.

Therefore, `order_items.unit_price` is not accidental duplication. It represents historical state associated with the order-product relationship.

The Python, JavaScript, and C++ implementations all preserve this distinction in their order calculations.

## SQL Querying

The Python implementation demonstrates several relational query patterns.

### Filtering

A parameterized query selects products above a specified price:

`WHERE unit_price >= ?`

The parameter is passed separately from the SQL statement.

This is safer than concatenating user-provided text into SQL because the database driver treats the parameter as a value rather than as SQL syntax.

### Ordering

`ORDER BY unit_price DESC`

allows the result to be returned in descending price order.

Ordering changes result presentation rather than changing stored data.

### Inner joins

The customer-order query connects records whose foreign-key values match.

Conceptually:

`customers.customer_id = orders.customer_id`

An `INNER JOIN` returns only records satisfying the relationship condition.

### Left joins

The Python program uses a `LEFT JOIN` when customer reporting needs to preserve customers even when they have no matching orders.

This distinction matters because an inner join can remove parent rows that have no child rows, while a left join preserves the parent.

### Aggregation

The reporting queries use:

- `COUNT`
- `SUM`
- `AVG`
- `GROUP BY`
- `HAVING`

For example, category revenue is calculated from:

`quantity * unit_price`

and then grouped by product category.

`HAVING` filters groups after aggregation, whereas `WHERE` filters rows before grouping.

### Subqueries

The Python program identifies products whose prices are above the average:

`WHERE unit_price > (SELECT AVG(unit_price) FROM products)`

The inner query calculates a scalar value, and the outer query uses that value as a filtering condition.

## Views

The Python schema defines `customer_order_summary` as a view.

The view combines customer information with order and order-item data and exposes:

- customer identity
- order count
- lifetime value

A view stores a query definition rather than a second independent copy of the underlying result.

This provides a reusable reporting interface while keeping the source tables normalized.

## Referential Integrity

A foreign key is not simply a connection used by joins. It also establishes an integrity rule.

If an order references customer `1`, customer `1` must exist.

If an order item references product `5`, product `5` must exist.

The Python program demonstrates invalid foreign-key inserts and shows that SQLite rejects them.

The C++ program explicitly checks these references before inserting records, making the same integrity relationship visible in application-level code.

## Referential Actions

The Python schema uses different deletion policies according to the meaning of each relationship.

### `ON DELETE CASCADE`

Customer profiles use:

`ON DELETE CASCADE`

If the parent customer is deleted, the dependent profile is deleted with it.

The profile has no independent business identity in this model.

### `ON DELETE RESTRICT`

Orders use:

`ON DELETE RESTRICT`

for their customer reference, and order items use restriction for products.

This prevents deletion when doing so would destroy important historical relationships.

The C++ case study models these restrictions explicitly. Attempting to delete a customer with orders or a product referenced by order items produces a constraint violation.

The choice between cascade and restriction is a domain decision. It should reflect the meaning and retention requirements of the data rather than being applied mechanically.

## Transactions

A transaction groups related database operations into an atomic unit.

The Python implementation uses SQLite transactions when creating orders and their items. If a later operation violates a foreign key or another constraint, the transaction is rolled back.

The JavaScript implementation provides a transaction-like snapshot mechanism. Before mutation, the store captures its state. If an operation fails, the previous state is restored.

The C++ implementation uses the same principle through an explicit `Snapshot` structure.

The important invariant is that an order creation operation should not leave behind half of its intended state. Creating an order without its required items can represent an incomplete business operation.

## Transaction Failure Example

The implementations intentionally attempt a multi-step operation containing a valid insertion followed by an invalid product reference.

The expected behavior is:

- the first mutation occurs inside the transaction boundary;
- the later foreign-key operation fails;
- the transaction is rolled back;
- inventory modified by the failed transaction returns to its previous value;
- the partially created order does not remain as committed business data.

This illustrates why atomicity matters beyond individual SQL statements.

## Python Implementation

The Python file is an executable SQLite case study.

Its schema contains five related tables and demonstrates the actual SQL mechanisms used to operate them.

The implementation includes:

- schema creation through SQL;
- explicit SQLite foreign-key enforcement;
- realistic customer, profile, product, order, and order-item records;
- parameterized `SELECT` queries;
- inner and left joins;
- aggregate reporting;
- `GROUP BY` and `HAVING`;
- a subquery using `AVG`;
- a reusable SQL view;
- updates and deletes;
- deliberate constraint failures;
- transaction rollback;
- atomic order creation;
- index inspection through `EXPLAIN QUERY PLAN`;
- schema metadata inspection;
- application-side `Decimal` conversion for monetary reporting;
- protection against SQL injection through parameter binding;
- referential delete restrictions.

The schema itself carries most structural integrity rules. Python supplies the application workflow that invokes the database.

## JavaScript Implementation

The JavaScript implementation takes a different perspective.

Instead of translating the Python SQL statements line by line, it models a Node.js database service using JavaScript collections and an asynchronous execution boundary.

`RelationalStore` acts as a repository-like persistence layer.

JavaScript `Map` objects provide keyed record storage. The service maintains explicit indexes such as `customerEmailIndex` and `productSkuIndex` to make uniqueness and lookup behavior visible.

The program uses `EventEmitter` to represent events generated by database operations, such as customer creation, order creation, transaction commit, and rollback.

The asynchronous `execute()` method uses the Node.js event loop to create a Promise-based boundary similar to the asynchronous interface exposed by many database drivers.

The JavaScript implementation also demonstrates:

- application-side foreign-key checks;
- unique email and SKU enforcement;
- one-to-one profile enforcement;
- composite order-item keys;
- inventory validation;
- purchase-time price capture;
- transaction snapshots;
- rollback;
- customer reporting;
- referential deletion restrictions;
- structured error types.

This implementation emphasizes how a relational persistence layer interacts with an event-driven JavaScript application.

## C++ Case Study

The C++ program presents a repository-style database engine for the same order-management domain, but it uses C++ data structures and explicit invariants rather than reproducing the SQL implementation.

`RelationalDatabase` owns the logical tables and indexes.

`std::unordered_map` provides primary-key-oriented record access.

`std::map<std::pair<int, int>, OrderItem>` represents the composite primary key of `order_items`.

The pair `(order_id, product_id)` therefore uniquely identifies an order-item relationship.

Additional unordered indexes model access paths for:

- customer email;
- product SKU;
- orders by customer;
- order items by product.

The case study demonstrates relationship traversal through methods such as `ordersForCustomer()` and `itemsForOrder()`.

The aggregation method `printCategoryRevenue()` performs the equivalent of a grouped revenue report by collecting order-item values by product category.

The transaction system creates a complete snapshot of relevant database state. A failed operation restores the snapshot, demonstrating atomic rollback.

The program also shows why historical pricing belongs to the order-item record. Updating the current product price does not alter a completed order's calculated total.

## Constraints Versus Application Validation

A robust database application can validate data at more than one boundary, but the responsibilities are different.

Application validation can provide immediate and user-friendly feedback. For example, the JavaScript service checks whether a product quantity is an integer before attempting persistence.

Database constraints provide authoritative structural protection at the persistence layer. A `FOREIGN KEY`, `UNIQUE`, or `CHECK` rule remains relevant even when multiple application processes write to the same database.

Duplicating a validation rule in application code does not make the database constraint unnecessary.

For important integrity requirements, the database should enforce the invariant whenever the database technology supports the required rule.

## Normalization Decisions

The schema separates attributes according to their entities and relationships.

Customer identity is stored in `customers`, rather than being repeated in every order.

Customer profile attributes are separated into `customer_profiles`.

Product identity and current inventory are stored in `products`.

Orders contain the relationship to the customer but do not contain repeated product columns.

The many-to-many relationship between orders and products is represented by `order_items`.

This reduces update anomalies and avoids structures such as `product_1`, `product_2`, and `product_3` columns.

There is one deliberate historical value that might look redundant: `order_items.unit_price`.

It is retained because it describes the transaction at the time it occurred. Replacing it with the current `products.unit_price` would make historical financial reporting incorrect after a product price changes.

## SQL Versus Relationship Structure

SQL and relationships answer different questions.

SQL provides operations for working with the relational data, such as:

`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `JOIN`, `GROUP BY`, and subqueries.

Relationships describe how the data should connect.

A foreign key expresses one part of that relationship structurally, while joins use the relationship to retrieve related records.

For example, the customer-order relationship exists because `orders.customer_id` references `customers.customer_id`. A query can then use those columns to combine customer and order information.

## Constraints Versus Relationships

Relationships describe valid connections between records.

Constraints enforce rules that protect those connections and the values stored in the records.

A foreign key therefore has a dual role in this project:

- it identifies the relationship between parent and child tables;
- it prevents a child record from referring to a nonexistent parent.

A `CHECK` constraint does not create a relationship. It protects a value's domain.

A `UNIQUE` constraint does not describe a parent-child relationship. It prevents duplicate values for a column or combination of columns.

Keeping these roles distinct makes schema design easier to reason about.

## Common Failure Modes

### Orphaned child records

An order referencing a nonexistent customer violates referential integrity.

The foreign-key constraint prevents this state in the Python implementation, while the JavaScript and C++ models explicitly reject it.

### Duplicate business identifiers

Two products with the same SKU would make SKU-based identification ambiguous.

The `UNIQUE` rule prevents this condition.

### Invalid quantities

A zero or negative order quantity has no valid meaning in this model.

The `CHECK (quantity > 0)` rule and corresponding application validations reject it.

### Accidental historical-price changes

Using the current product price to calculate old orders would make historical totals change whenever the catalog price changes.

Storing purchase-time price in `order_items` avoids that problem.

### Partial transactions

Creating an order successfully and then failing while adding its items can leave inconsistent application state if the operations are not atomic.

The transaction examples show why all related mutations should share an appropriate transaction boundary.

### Deleting referenced records

Deleting a product that still appears in historical order items would break those relationships.

The restriction policy prevents the deletion.

### Unsafe SQL construction

Concatenating user-controlled input into SQL can allow the input to alter the intended SQL statement.

The Python program uses parameter binding instead. The SQL structure is fixed, while external values are transmitted separately.

## Performance Considerations

Relational correctness does not automatically guarantee efficient query execution.

The Python schema creates indexes for common foreign-key lookup columns such as `orders.customer_id` and `order_items.product_id`.

The program uses `EXPLAIN QUERY PLAN` to inspect how SQLite approaches a customer-specific order query.

Indexes can reduce lookup cost, but they also consume storage and create maintenance work during inserts, updates, and deletes.

A useful index should correspond to real query patterns. Adding indexes indiscriminately can increase write cost without providing meaningful read benefits.

Composite keys and indexes also need careful consideration. The column order in a composite index affects which predicates can use it efficiently.

## Query Correctness

Join queries can accidentally multiply rows when relationships contain multiple child records.

For example, joining customers to orders and then orders to order items produces one result row per matching order-item relationship, not necessarily one row per customer.

The Python reporting queries therefore use aggregation such as `COUNT(DISTINCT o.order_id)` where the desired metric is the number of orders rather than the number of order-item rows.

Understanding the grain of a query result is essential when using relational joins and aggregation.

## Data Integrity and Concurrency

The examples use transactions to illustrate atomicity, but a production database also has to address concurrent transactions.

Two independent application processes may attempt to update the same inventory simultaneously.

A robust production implementation should rely on the database's transaction isolation and locking mechanisms rather than assuming that application-level reads and writes are automatically atomic.

For inventory, payment, financial records, or other critical state, a design should ensure that the validation and mutation cannot be separated by an unsafe race condition.

The in-memory JavaScript and C++ transaction models are educational representations. They do not reproduce the complete concurrency, locking, durability, recovery, or isolation behavior of a production DBMS.

## Security Considerations

Parameterized SQL is a primary protection demonstrated by the Python program.

Values should be supplied through database-driver parameter binding rather than assembled into SQL strings.

Database credentials should not be embedded directly in application source code in production.

Database accounts should receive only the privileges required by the application. An application that only reads reporting data should not automatically receive schema-altering or unrestricted deletion privileges.

Constraints also contribute to security indirectly by limiting the set of states that malicious or faulty input can create.

Security is not achieved by constraints alone. Authentication, authorization, secret management, auditing, encryption, network controls, and operational monitoring belong to the broader database security architecture.

## Debugging and Diagnostics

The Python program exposes database behavior through deliberate failures and `EXPLAIN QUERY PLAN`.

Useful relational debugging questions include:

- Which table owns the data?
- What is the primary key?
- Which column represents the foreign-key relationship?
- At what grain does the query return rows?
- Which constraint rejected the mutation?
- Was the operation inside a transaction?
- Which indexes are available for the predicate?
- Is a value current state or historical state?

Schema metadata can also be inspected through SQLite's catalog and `PRAGMA foreign_key_list`.

These techniques are more useful than debugging SQL only by looking at the final result because they expose the database's structural assumptions.

## Production Considerations

A production relational system requires stronger operational guarantees than these educational in-memory demonstrations.

Important production concerns include transaction isolation, durable storage, backup and recovery procedures, migration management, connection pooling, access control, monitoring, slow-query analysis, schema versioning, and carefully designed indexes.

The exact implementation depends on the selected database engine. SQL syntax, constraint behavior, transaction semantics, indexing strategies, and administrative capabilities can differ between database systems.

The core relational principles remain useful across systems: model entities separately, represent relationships explicitly, enforce important invariants, use transactions for atomic operations, and design queries around the actual grain of the data.
