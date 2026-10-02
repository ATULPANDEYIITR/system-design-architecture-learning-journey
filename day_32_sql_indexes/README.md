# SQL Indexes: B-Tree Indexes and Query Performance

## Topic Scope

This repository studies SQL indexes through two closely related subjects:

- **B-Tree indexes**: the ordered index structure used by many relational database systems to support equality, range, ordering, and prefix-oriented access patterns.
- **Query performance**: the relationship between an index, data distribution, logical I/O, selectivity, base-table access, and the optimizer's choice between an indexed access path and a sequential scan.

The three implementations use an order-management workload so that indexing decisions are connected to realistic relational data rather than isolated data-structure exercises.

The implementations intentionally model database behavior rather than attempting to reproduce one particular database engine. Exact index syntax, optimizer cost formulas, page formats, concurrency behavior, and maintenance algorithms differ among PostgreSQL, MySQL, SQL Server, Oracle, and other systems.

## Core SQL Index Concept

A table without a useful index may require the database to inspect rows until it determines which records satisfy a predicate. A simplified query such as `SELECT * FROM orders WHERE customer_id = 10` can therefore become a table scan.

An index stores additional, ordered access information. Instead of searching the complete table, the database can locate the relevant index key and obtain references to matching rows.

The important distinction is that an index normally does not replace the table. It provides an alternative access path into the table.

For a non-covering index, a typical logical path is:

`query predicate → index navigation → matching row identifiers → base-table pages → result`

For an index-only operation, the required projected data may already exist in the index:

`query predicate → index navigation → required result`

The second path can avoid base-table lookups, but the additional index payload consumes storage and must be maintained when indexed data changes.

## B-Tree Indexes

A B-Tree keeps keys in sorted order and organizes them into balanced nodes. Internal nodes guide searches toward the relevant child. Leaf-level information identifies matching rows.

The important property is not simply that the structure is a tree. Its usefulness comes from keeping search paths short while allowing many keys to be stored in each node. Database B-Trees are generally page-oriented, so a node is designed around the amount of information that can be stored and accessed efficiently in a database page.

For an equality predicate such as `customer_id = 10`, the engine can navigate through the tree rather than testing every table row.

For a range predicate such as `order_date BETWEEN 20260101 AND 20260331`, the ordering of the keys becomes particularly useful. The engine can locate the relevant boundary and process the ordered range.

The exact physical implementation varies by database engine. Real systems also have buffer pools, page splits, logging, concurrency control, visibility rules, recovery mechanisms, and optimizer statistics that are intentionally outside the simplified tree model.

## Equality and Range Access

The Python and JavaScript implementations explicitly model equality and range lookup.

The C++ case study uses a B-Tree for customer identifiers, status codes, and order dates.

Equality lookup has a search target such as:

`customer_id = 10`

The index returns identifiers associated with that key. The simulated table then maps those identifiers to physical pages.

Range lookup has two ordered boundaries:

`20260101 <= order_date <= 20260331`

The B-Tree's ordering means the search is not equivalent to testing every possible date value independently.

This distinction explains why B-Trees are useful for more than exact equality. Ordered access is also relevant to ranges and, depending on the query and index ordering, operations involving sorted output.

## Table Pages and Query Cost

The examples model a table as pages containing a fixed number of rows.

This is important because database performance is strongly affected by I/O behavior. A query that examines fewer logical pages may be preferable even when the number of CPU comparisons is not dramatically different.

The simplified cost relationship used by the examples is conceptually:

`index navigation cost + required table-page accesses`

compared with:

`all table pages`

This is not a real database optimizer formula. It is an educational model for understanding why an index can be valuable for a selective query and less valuable for a query that returns a large portion of a table.

A database may also benefit from cached pages, sequential read-ahead, parallelism, visibility checks, compression, partitioning, and other engine-specific behavior. Therefore, actual performance should be evaluated using the target database's execution plans and measurements.

## Selectivity and Cardinality

Index usefulness depends partly on how much the predicate filters the table.

**Cardinality** describes the number of distinct values in a column or expression.

**Selectivity** describes how narrowly a predicate identifies rows. A predicate matching a small fraction of the table is generally more selective than one matching most of the table.

The sample workload deliberately makes order status values unevenly distributed. A predicate such as `status = 'PAID'` can match a large portion of the data because status has low cardinality.

An index on a low-cardinality column is not automatically useless. Its usefulness depends on the actual distribution, table size, query predicate, required columns, clustering or physical locality, cache state, and optimizer cost model.

This is why an index should not be justified solely by statements such as "this column appears in a WHERE clause."

## Composite B-Tree Indexes

The examples include an index conceptually equivalent to:

`(customer_id, order_date)`

Its logical ordering is:

`customer_id → order_date`

All entries for one customer are grouped, and within that customer group the dates are ordered.

This makes predicates involving both columns natural candidates for the index:

`customer_id = 10 AND order_date BETWEEN 20250101 AND 20251231`

A predicate on the leading column alone can also use the index:

`customer_id = 10`

The same does not automatically mean that a predicate only on the second column has equivalent access:

`order_date BETWEEN 20250101 AND 20251231`

The leading key determines the initial ordering. This is commonly described through the **leftmost-prefix principle** for composite B-Tree indexes, though exact optimizer behavior depends on the database engine and query.

Column order should therefore reflect actual query patterns. Reversing `(customer_id, order_date)` to `(order_date, customer_id)` changes which predicates naturally form contiguous ranges.

## Covering and Index-Only Access

The examples also model a covering index.

Suppose a query needs:

`customer_id`

as its search condition and needs only:

`order_id, status, total_amount`

in its result.

An index that stores the search key together with the required projected values can potentially answer the query without consulting the base table.

The Python implementation represents this with `CoveringCustomerIndex`. The JavaScript implementation uses a `Map` whose values contain the projected fields. The C++ implementation stores those projected fields as part of the index payload.

The performance advantage is the reduction in base-table page access.

The trade-off is that the index becomes larger and its payload must be maintained when the stored values change. A covering index should therefore be evaluated against actual query workload rather than treated as a universal optimization.

## Python Implementation

The Python program provides the most explicit educational simulation of the complete indexing workflow.

`OrdersTable` models a heap-like table divided into pages. Each order has a physical location represented by a page identifier and slot. This allows the program to distinguish index navigation from base-table page access.

`BTreeIndex` implements a simplified balanced B-Tree. Its nodes maintain ordered keys and child pointers. Duplicate keys are supported because SQL indexes do not necessarily require every indexed value to be unique.

The Python program demonstrates:

- Equality lookup through `customer_id`.
- Range lookup through `order_date`.
- Table-page comparison between an indexed access path and a full scan.
- A composite `(customer_id, order_date)` index.
- A covering index for index-only-style access.
- Selectivity and cardinality statistics.
- A simple query planner that compares estimated index work with table-scan work.
- Index maintenance when an indexed customer identifier changes.
- Missing-key searches and invalid range handling.
- Duplicate row validation.
- Discussion of write amplification caused by additional indexes.

The B-Tree deletion method is deliberately simplified by rebuilding the structure. Real storage engines implement structural deletion and node rebalancing. The example avoids presenting that simplified mechanism as a production database algorithm.

## JavaScript Implementation

The JavaScript program takes a complementary approach using Node.js mechanisms.

`EventEmitter` is used to expose query lifecycle events. A `QueryEngine` emits a `queryStarted` event before selecting an access path and a `queryFinished` event after execution. This makes query execution observable without turning the example into a browser application.

The JavaScript B-Tree uses binary-search helpers for lower and upper boundaries. These functions are important because the implementation needs both exact lookup and ordered range boundaries.

`CompositeIndex` uses an explicit lexicographic comparator for `(customerId, orderDate)`. JavaScript arrays do not provide the database-style value comparison required by a composite index, so the comparator explicitly compares the leading customer identifier before comparing the date.

`CoveringIndex` uses `Map` values containing projected fields, demonstrating the idea of index-only access without making a claim about a particular SQL engine's syntax.

The program also demonstrates how an asynchronous query interface can expose plan and execution telemetry with `async`/`await`, while keeping the indexing model deterministic and dependency-free.

## C++ Case Study

The C++ implementation models a commerce order database and a simplified query-planning layer.

The table stores orders in fixed-size pages. The physical location map connects an order identifier to its page and slot.

The B-Tree implementation uses explicit nodes, sorted keys, child pointers, node splitting, equality search, range search, and duplicate-key payloads. It uses C++ standard-library algorithms such as `std::lower_bound` and `std::upper_bound` for ordered key navigation.

The case study creates separate indexes for:

`customer_id`

`status`

`order_date`

The customer index represents a selective equality workload. The date index represents an ordered range workload. The status index demonstrates why low-cardinality columns require careful performance analysis.

The composite index stores `(customer_id, order_date)` as a lexicographically ordered pair. This models how column ordering changes the usable search space.

The covering index stores `order_id`, `status`, and `total_amount` alongside the customer grouping, allowing the case study to represent a result that does not require a base-table lookup.

The `QueryPlanner` compares a simplified indexed access cost with the number of table pages required by a full scan. Its decision is intentionally educational rather than a reproduction of PostgreSQL, MySQL, SQL Server, or another production optimizer.

The program also updates an indexed customer identifier and explicitly removes the old index entry before inserting the new key. This demonstrates that indexes accelerate some reads at the cost of additional write maintenance.

## Query Performance

Index performance should be understood through the complete execution path rather than through the index structure alone.

A query can use an index and still perform poorly if the predicate produces many rows and those rows are scattered across many table pages.

For example, an index may quickly identify thousands of matching row identifiers, but fetching thousands of unrelated base-table pages can eliminate the benefit of the initial index navigation.

This is why the examples count both B-Tree node visits and table pages touched.

A simplified comparison is:

| Access path | Typical work represented by the examples |
| --- | --- |
| Full table scan | Read all table pages and evaluate the predicate |
| Index seek | Navigate the B-Tree to a matching key |
| Index seek plus lookup | Navigate the index, then fetch required base-table pages |
| Index range scan | Navigate to a range boundary and process ordered index entries |
| Covering/index-only access | Navigate the index and obtain required projected values without base-table access |

Real optimizers consider substantially more information than this table represents.

## Why an Index Can Become a Bad Access Path

An index is not automatically faster than a table scan.

If a query returns a large fraction of the table, the engine may need to fetch many table pages after using the index. A sequential scan can then have better locality and lower overall cost.

Low-cardinality columns are a common example. A column containing only a few status values can have many rows per value.

An index can also be unattractive when:

- The table is very small, making a scan inexpensive.
- The predicate is insufficiently selective.
- The query requires many columns not present in the index.
- Matching rows are distributed across a large number of table pages.
- The index is too large for effective cache residency.
- The workload is write-heavy and index maintenance is expensive.
- Statistics are stale or inaccurate, causing the optimizer to estimate the query incorrectly.

These conditions are workload-dependent rather than universal rules.

## Index Maintenance

An index creates additional state that must remain synchronized with table data.

For an insert, an index entry must be created.

For a delete, the corresponding entry must be removed.

For an update to an indexed value, the old key must cease to represent the row and the new key must be represented.

An update that changes a non-indexed column may have different maintenance consequences depending on whether the column is stored as part of a covering index and depending on the database engine.

The examples make this visible by changing an order's `customer_id` and updating the corresponding index.

This is a central read/write trade-off:

`more index access paths → potentially faster reads`

but also:

`more index structures → more storage and write-maintenance work`

## B-Tree Height and Complexity

A balanced B-Tree has logarithmic search behavior with respect to its number of keys under the usual simplified model.

The exact constant factors matter greatly in databases because one B-Tree node generally corresponds conceptually to a database page or page-like storage unit.

A high fan-out tree can therefore contain a very large number of keys while maintaining a relatively small height.

The examples use deliberately small node capacities so that splitting and tree height remain observable. Production database B-Trees typically use much larger effective node capacities determined by page size, key width, tuple references, metadata, and engine-specific storage layout.

The practical cost of a B-Tree lookup is therefore better understood as a sequence of page accesses than as an abstract count of comparisons alone.

## Range Queries and Ordering

B-Trees preserve key order.

This supports range predicates and can also support ordered access when the query's requested order aligns with the index ordering.

A range such as:

`order_date >= 20260101 AND order_date < 20260401`

has a natural ordered representation.

Half-open ranges can be useful for timestamp data because they avoid assumptions about the maximum representable time within a day. The example uses integer dates for clarity rather than timestamp arithmetic.

Range performance depends on both the cost of reaching the first matching key and the amount of matching data that must be processed.

A range covering most of the index can approach the cost of scanning a large amount of data, so "uses a B-Tree" should not be confused with "is automatically fast."

## Index Design and Query Shape

Index design should begin with real query predicates and required result columns.

For an equality-heavy workload involving customer orders, an index beginning with `customer_id` may be appropriate.

For customer-specific reporting by date, `(customer_id, order_date)` creates a different access pattern because date ordering is nested within each customer.

For date-driven reporting across all customers, an index beginning with `order_date` represents a different workload.

The choice cannot be made from column names alone. The database's actual workload, selectivity, result size, ordering requirements, joins, and update frequency all affect the decision.

## EXPLAIN and Real Database Validation

The programs deliberately stop short of claiming to be real query optimizers.

In a production database, query plans should be inspected with the engine's execution-plan facilities, such as `EXPLAIN` or the corresponding engine-specific command.

A useful investigation compares:

- Estimated rows versus actual rows.
- Chosen access path.
- Index conditions and residual filters.
- Estimated versus actual page or row work.
- Sort operations.
- Join strategy where applicable.
- Whether an index-only or covering access path is actually achieved.
- Whether statistics appear consistent with the current data distribution.

A theoretical index design can look correct while real data distribution causes a different execution plan.

## Common Indexing Mistakes

### Indexing every filtered column

Adding an index to every column appearing in a `WHERE` clause can produce excessive storage and write-maintenance costs. Indexes should correspond to meaningful access patterns rather than individual syntax occurrences.

### Ignoring composite-column order

An index on `(customer_id, order_date)` is not equivalent to an index on `(order_date, customer_id)`. The leading key changes the ordered search space.

### Assuming low cardinality makes an index useless

A low-cardinality index can still be useful for some queries and distributions. Its value depends on result size, physical locality, cache behavior, and the rest of the query.

### Assuming an index guarantees a particular plan

The optimizer can legitimately choose a table scan even when a relevant index exists. An index is an available access path, not an unconditional command to the optimizer.

### Ignoring write cost

Every additional index creates maintenance work. A read-heavy workload and a write-heavy workload can have very different acceptable index strategies.

### Evaluating only execution time

Execution time is useful, but plan shape, logical reads, physical reads, row estimates, cache state, concurrency, and data distribution provide important context when diagnosing an index decision.

## Edge Cases

The implementations explicitly handle several indexing-specific failures.

A missing key returns no matching row identifiers while still requiring B-Tree navigation.

An invalid range where the lower boundary is greater than the upper boundary is rejected rather than silently producing misleading results.

Duplicate order identifiers are rejected by the table model.

Updating an indexed key requires corresponding index maintenance.

Composite-index access changes when the leading column is absent from the predicate.

Covering access is only possible when the index contains the information required by the query's projection and filtering requirements.

## Security and Operational Considerations

SQL indexes are performance structures, not substitutes for authorization or input validation.

Application input should still be parameterized when constructing SQL statements. An index does not prevent SQL injection.

Index metadata can also reveal aspects of database structure, so production systems should control access to database catalog information and operational diagnostics according to organizational security requirements.

Indexes should be monitored as part of database operations. Large or unused indexes consume storage and can increase maintenance work.

Changes to important indexes should be evaluated against production-like data distributions rather than a small development dataset.

## Limitations of the Implementations

These programs are educational simulations rather than database engines.

They do not reproduce:

- MVCC visibility rules.
- Transactions and rollback.
- WAL or redo logging.
- Buffer-pool replacement.
- Concurrent B-Tree page latching.
- Crash recovery.
- Vacuuming or garbage collection.
- Real database page formats.
- Database-specific collations.
- Histograms and multi-column statistics.
- Join-order optimization.
- Parallel query execution.
- Partition pruning.
- Engine-specific index-only visibility requirements.
- Production-grade B-Tree deletion and page reclamation.

The simplified cost model is therefore useful for understanding relationships between concepts but should not be used to predict production query performance.

## Practical Relationship Between the Concepts

The central relationship demonstrated by the three implementations is:

`relational table → additional ordered access structure → reduced search work for suitable predicates → possible reduction in base-table page access`

B-Tree ordering provides the physical mechanism for efficient navigation.

Selectivity and query shape determine how much of the index and table must actually be processed.

Composite key ordering determines which multi-column predicates naturally map to contiguous portions of the index.

Covering payload can reduce base-table lookups for suitable projections.

Index maintenance introduces additional work for writes.

The database optimizer evaluates these competing costs and chooses an access path based on statistics and engine-specific cost models.

The result is not a universal rule that indexes are faster. The technically important question is whether a particular index provides a lower-cost access path for a particular workload and data distribution.
