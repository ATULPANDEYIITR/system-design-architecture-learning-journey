# Database Partitioning: Horizontal and Vertical Partitioning

## Scope

Database partitioning divides a logical dataset into smaller physical or logical units while preserving the database's overall data model.

This implementation focuses on the two primary forms:

- **Horizontal partitioning** divides a table by rows. Each partition contains a different subset of records according to a partition key such as date, region, tenant, or hash.
- **Vertical partitioning** divides a table by columns. Related attributes remain connected through a common key, while frequently accessed, wide, sensitive, or infrequently used attributes can be stored separately.

The implementations also demonstrate LIST, HASH, and composite partitioning because these mechanisms show how horizontal partitioning can use different routing strategies.

The central distinction is simple:

| Technique | What is divided? | Typical partition key | Main benefit |
|---|---|---|---|
| Horizontal | Rows | Date, tenant, region, hash | Reduces the row population considered by eligible queries |
| Vertical | Columns | Shared primary key | Reduces row width and separates different access patterns |
| RANGE | Rows | Ordered value such as date | Strong locality for range predicates |
| LIST | Rows | Explicit category | Natural routing for finite business categories |
| HASH | Rows | Hash of a key | Distribution across partitions |
| Composite | Rows through multiple levels | Range + hash, list + hash, etc. | Combines locality and distribution |

Partitioning is not a replacement for indexes, appropriate data types, normalization, query optimization, or capacity planning. It is a physical data-layout decision that should match the workload.

## Horizontal Partitioning

Horizontal partitioning keeps the same columns in each partition but distributes different rows among those partitions.

A time-series order table is a natural example. Orders from January through March can occupy one partition, April through June another, and so on.

A RANGE partition normally defines a half-open interval:

`lower_bound <= partition_key < upper_bound`

This boundary model avoids ambiguity between adjacent partitions. If one partition ends at `2026-04-01` and the next begins at `2026-04-01`, the date belongs to the second partition.

The Python implementation models this behavior through `RowPartition` and `HorizontalPartitionManager`. The manager validates overlapping ranges, routes inserted orders, and identifies only partitions whose ranges overlap a requested date interval.

The JavaScript implementation uses `RangePartition` and `HorizontalPartitionStore`. It adds an event-driven insertion event so partition routing can be observed without coupling the storage model to a logging mechanism.

The C++ implementation treats the problem as an order-platform case study. `RangePartition` owns its rows and `OrderPartitionEngine` performs boundary validation and partition pruning.

The Java implementation represents the same domain with immutable records and a `RangePartitionService`. The service separates routing policy from the `Order` domain object.

The PostgreSQL implementation uses `PARTITION BY RANGE (order_date)` and creates quarterly partitions. PostgreSQL can use partition pruning when a query contains predicates that allow it to determine which partition boundaries can possibly contain matching rows.

## Partition Pruning

Partition pruning is one of the most important performance mechanisms associated with horizontal partitioning.

Suppose a table has quarterly partitions:

- `orders_2026_q1`
- `orders_2026_q2`
- `orders_2026_q3`
- `orders_2026_q4`

A query restricted to July through September does not logically require rows from January through June. A partition-aware optimizer can eliminate those partitions before scanning their rows.

The SQL script demonstrates this with an `EXPLAIN (COSTS OFF)` query using:

`order_date >= DATE '2026-04-01' AND order_date < DATE '2026-10-01'`

The Python, JavaScript, C++, and Java models explicitly calculate the overlapping partition intervals to make the pruning mechanism visible.

Partition pruning depends on the query exposing a useful relationship with the partition key. A query that applies an unrelated expression or lacks a selective partition-key condition may receive little benefit from partitioning.

Partition pruning is different from indexing. An index narrows the search within a table or partition, while partition pruning determines which partitions need to be considered at all.

## RANGE Partitioning

RANGE partitioning is appropriate when the partition key has meaningful ordering.

Dates are particularly suitable because applications frequently ask for:

- a month
- a quarter
- a financial year
- a recent time window
- historical records before a retention boundary

The PostgreSQL order table uses quarterly date partitions. A future partition is explicitly created for the first quarter of 2027.

Time-based RANGE partitioning also makes lifecycle operations easier to reason about. Historical data can be isolated into older partitions, and maintenance operations can target individual partitions instead of the complete logical table.

The primary operational risk is an incomplete partition boundary plan. If incoming data falls outside the defined ranges, inserts can fail unless a suitable DEFAULT partition or future partition exists.

The SQL example includes `orders_default` to demonstrate one approach. A strict production design may instead deliberately reject unexpected dates so that missing partition provisioning is discovered immediately.

## LIST Partitioning

LIST partitioning routes rows according to explicit discrete values.

The SQL implementation creates regional partitions:

`NORTH`, `SOUTH`, `EAST`, and `WEST`.

This is different from RANGE partitioning because the values do not represent a continuous interval. The partition definition expresses membership in a finite set.

LIST partitioning is useful when the routing categories have business meaning and are relatively stable.

The demonstration includes a DEFAULT partition for `CENTRAL`, which has no explicit regional partition.

LIST partitioning becomes operationally awkward when categories change frequently. Adding a new business category can require a schema change and potentially a redistribution strategy.

## HASH Partitioning

HASH partitioning distributes rows using a hash of a partition key.

The PostgreSQL example creates four hash partitions for customer events:

`customer_events_h0` through `customer_events_h3`.

The objective is distribution rather than range locality.

For example, a customer identifier can be routed to one of several buckets without requiring the identifiers themselves to have meaningful ranges.

Hash partitioning is useful when:

- write activity should be spread across partitions
- equality lookups dominate the workload
- there is no natural chronological or categorical partition boundary
- a large key space needs approximately distributed storage

Hash partitioning is poor for a query such as "all customers created between two identifier values" because the hash destroys the original ordering.

Changing the number of hash partitions can also have significant operational consequences because existing rows may need redistribution depending on the database implementation and partitioning strategy.

## Composite Partitioning

Composite partitioning applies multiple partitioning levels.

The PostgreSQL `event_archive` example uses:

`RANGE(event_date)`

at the first level and:

`HASH(customer_id)`

inside each monthly range partition.

This combines two different workload properties.

The date level provides temporal locality. A query restricted to September can eliminate other months.

The hash level distributes September's rows among several child partitions according to customer ID.

The same structure is modeled in the Python, JavaScript, C++, and Java programs.

Composite partitioning can improve scalability when a single partitioning dimension is insufficient, but it increases operational complexity. The team must understand both levels when creating partitions, inspecting data, troubleshooting queries, and planning capacity.

A composite design should therefore be justified by an actual workload rather than introduced merely because multiple partitioning dimensions are available.

## Vertical Partitioning

Vertical partitioning divides columns rather than rows.

The customer model separates attributes into two logical fragments:

`customer_operational`

and:

`customer_sensitive`

The operational fragment contains:

- customer ID
- name
- email
- phone
- account status

The sensitive fragment contains:

- customer ID
- postal address
- date of birth

The common `customer_id` acts as the relationship key.

A query that needs only customer name and email can access the operational fragment without reading the sensitive fragment.

A query requiring the complete customer record performs a join using the shared key.

Vertical partitioning is particularly useful when a table contains:

- frequently accessed narrow attributes
- rarely accessed wide attributes
- large text or binary attributes
- attributes with different access-control requirements
- columns that are expensive to load unnecessarily

Vertical partitioning is not the same as normalization, although the physical structures may resemble normalized tables. Normalization primarily addresses logical data dependencies and redundancy. Vertical partitioning is primarily concerned with physical access patterns and storage layout.

## Vertical Partition Integrity

A vertically partitioned entity requires strong key integrity.

The SQL implementation makes `customer_sensitive.customer_id` a foreign key referencing `customer_operational.customer_id`.

This prevents an orphan sensitive fragment from existing without its corresponding operational customer.

`ON DELETE CASCADE` ensures that deleting the parent operational record also removes the dependent sensitive fragment.

The application implementations perform equivalent integrity checks.

The Java implementation throws `PartitionIntegrityException` when a full customer lookup finds one fragment but not the other.

This is important because vertical partitioning introduces an additional physical relationship that the database or application must keep consistent.

## Horizontal and Vertical Partitioning Compared

Horizontal partitioning answers:

> Which rows should belong together physically?

Vertical partitioning answers:

> Which columns should be stored together physically?

For example, a large order history can be horizontally partitioned by `order_date`, while a wide customer table can be vertically separated into operational and sensitive attributes.

The two techniques can coexist.

A system could have:

`orders -> RANGE by date`

and separately:

`customer -> operational/sensitive vertical fragments`

There is no requirement that an entire database choose one partitioning strategy.

Different tables should use partitioning according to their own access patterns.

## Python Implementation

The Python program provides the broadest executable conceptual model.

`HorizontalPartitionManager` demonstrates range boundaries, routing, overlap validation, and partition pruning.

`VerticalCustomerStore` models two column groups connected by `customer_id`.

`HashPartitioner` demonstrates deterministic bucket selection, while `ListPartitioner` maps business categories to explicit partitions.

`CompositePartitionManager` combines a monthly range with customer hash routing.

The Python code also generates PostgreSQL DDL showing how the in-memory model maps to actual database structures.

The failure demonstrations are important because partitioning is not only about successful routing. The model also handles missing partition coverage, invalid range definitions, and broken vertical relationships.

## JavaScript Implementation

The JavaScript program treats partitioning as an event-driven application service.

`HorizontalPartitionStore` extends Node.js `EventEmitter`. After an order is routed, it emits a `rowInserted` event containing the selected partition. This demonstrates how partition-routing behavior can be observed without embedding logging directly into every domain operation.

The program uses `Map` for partition and vertical-fragment storage.

`async/await` is used for an asynchronous partition query, reflecting how a real Node.js database driver would normally perform database I/O asynchronously.

The hash router uses Node's built-in `crypto` module to create deterministic SHA-256-based bucket selection without an external package.

The JavaScript model therefore demonstrates application-level routing behavior while keeping the storage model independent of a specific npm database driver.

## C++ Case Study

The C++ program models an order repository as a partition-aware storage engine.

`RangePartition` owns the rows belonging to one date range.

`OrderPartitionEngine` validates that ranges do not overlap, routes incoming orders, and performs pruning before evaluating individual rows.

`RegionRouter` represents LIST-style routing.

`HashRouter` represents customer-based distribution.

`VerticalCustomerStore` maintains operational and sensitive customer fragments independently and validates that both use the same customer identifier.

`CompositePartitionEngine` creates a two-dimensional physical key based on the order month and a customer hash bucket.

The case study also exposes an important systems-level consideration: the in-memory hash function is appropriate for a demonstration but should not automatically be treated as a distributed database hashing contract. A distributed system requires a stable routing strategy across nodes and compatible implementations.

## Java Implementation

The Java implementation uses domain-oriented abstractions rather than treating partitioning as a collection of unrelated utility methods.

`Order` is an immutable record with constructor validation.

`OrderStatus` restricts order states to an explicit enum.

`PartitionRouter<K>` provides a generic routing abstraction.

`RangePartitionService` handles horizontal partition selection and pruning.

`VerticalCustomerRepository` models the two customer fragments and validates their shared identity.

`CompositePartitionRepository` combines a monthly key with a customer hash partition.

Java's collection APIs and immutable records make the state transitions explicit while keeping the domain objects small.

The implementation also uses custom exceptions to distinguish missing partitions from integrity failures.

## SQL Data Model

The PostgreSQL script is the most database-native implementation.

The main horizontally partitioned table is `orders`.

Its partition key is:

`order_date`

The quarterly child tables represent physical row groups.

The `orders_default` partition catches values outside the explicitly defined quarterly boundaries.

The table includes database-level constraints for:

- non-negative amounts
- valid order statuses
- valid regions
- primary-key integrity

The partitioned primary key includes `order_date` because PostgreSQL's uniqueness rules for partitioned tables require the partition key to participate in a unique constraint defined at the partitioned-table level.

The script also creates indexes on customer/date and region/date access patterns.

## SQL Vertical Model

The vertically partitioned customer model contains:

`customer_operational`

and:

`customer_sensitive`

The second table references the first through a foreign key.

The `customer_profile` view reconstructs the logical customer representation.

This demonstrates an important distinction: physical fragmentation does not require application consumers to know that the data has been split. A view or service layer can expose a logical representation while the physical storage remains separated.

## SQL Integrity and Failure Conditions

The database layer enforces rules that should not depend solely on application validation.

The SQL script deliberately attempts invalid operations inside exception-handling blocks.

A negative order amount violates `orders_amount_nonnegative`.

An unsupported status violates `orders_status_valid`.

An orphan sensitive customer fragment violates the foreign key.

These constraints are especially important in partitioned systems because an application-level routing error can otherwise create inconsistent physical state.

## Partition Maintenance

Partitioning creates an operational responsibility: partitions must match the expected data lifecycle.

For time-based data, future partitions should be provisioned before incoming data reaches their boundary.

The SQL script demonstrates transactional creation of a 2027 Q1 order partition.

A production process would normally automate this maintenance and monitor for unexpected inserts into a DEFAULT partition.

A DEFAULT partition can protect availability, but it can also hide a partition-provisioning mistake if it silently absorbs data that was expected to have a dedicated partition.

## Query Design

A partition-aware query should expose the partition key whenever possible.

For a date-partitioned order table, this is preferable:

`WHERE order_date >= DATE '2026-07-01' AND order_date < DATE '2026-10-01'`

because the database can reason directly about the relevant range.

Partitioning does not guarantee faster queries. A query that must inspect most partitions still has to process a large portion of the data.

Likewise, a query against a single partition may still need an index if many rows exist inside that partition.

The practical performance model is therefore:

**partition pruning + appropriate indexes + selective predicates + manageable partition sizes**

rather than partitioning alone.

## Partition-Key Selection

A useful horizontal partition key usually has at least one strong workload characteristic.

A date key works well when queries frequently use date ranges and data has a natural lifecycle.

A tenant key can work well when customers must be isolated or most queries operate within one tenant.

A region key can work well when regional workloads are naturally separated.

A hash key works well when distribution is more important than range locality.

A poor partition key can create severe skew.

For example, if almost all new records belong to one category, LIST partitioning by that category can create one oversized partition while the others remain almost empty.

The partition key should therefore be chosen from observed workload characteristics, not simply from a column with high cardinality.

## Partition Skew

Partition skew occurs when the distribution of rows or workload is significantly uneven.

A date partition can become skewed if one period receives far more activity than another.

A LIST partition can become skewed if one business category dominates.

A hash partition generally aims for better distribution, but the result still depends on the key distribution and implementation.

Skew affects storage capacity, maintenance duration, concurrency, and query performance.

Monitoring row counts and activity by partition is therefore part of operating a partitioned system.

The SQL script includes partition distribution queries using `tableoid` and PostgreSQL inheritance metadata.

## Partition Size

Too few partitions can make individual partitions large enough that maintenance and scans remain expensive.

Too many partitions can increase planning overhead, metadata management, maintenance complexity, and operational burden.

The correct partition count depends on:

- total data volume
- growth rate
- query patterns
- retention policy
- hardware
- database engine behavior
- maintenance frequency

Partition granularity should be chosen deliberately.

For example, a very large historical event table might justify monthly partitions, while a smaller dataset may not benefit from daily partitions.

## Security Considerations

Vertical partitioning can help isolate sensitive columns, but partitioning itself is not a security boundary.

Actual protection should be implemented with database privileges, roles, row-level security where appropriate, encryption, secure application access, and auditing.

The customer model separates address and date-of-birth attributes from operational attributes because they have a different access pattern and potentially different sensitivity.

The physical separation makes narrower access paths possible, but a user with permission to access both fragments can still reconstruct the complete customer.

Therefore:

**physical separation supports security architecture but does not replace authorization.**

## Common Design Mistakes

A common mistake is partitioning a table without a workload-based reason. Partitioning adds schema and operational complexity, so a partitioned design should provide a measurable benefit.

Another mistake is choosing a key that does not appear in important query predicates. If most queries do not constrain the partition key, pruning provides little benefit.

Another failure mode is allowing partitions to overlap or leaving gaps in a range scheme. Database-level partition constraints are preferable to relying entirely on application routing.

Another mistake is assuming partitioning replaces indexes. A query may reach one partition and still scan millions of rows if the partition lacks an appropriate index.

A vertical design can also fail when fragment relationships are not protected by foreign keys or equivalent application-level integrity rules.

## Performance Considerations

Horizontal partitioning can reduce the amount of data considered by a query through pruning.

Vertical partitioning can reduce row width for narrow workloads.

Hash partitioning can spread write and read activity across physical groups.

Composite partitioning can combine range locality with distribution.

The cost is additional planning and maintenance complexity.

Indexes may need to be created and maintained across many partitions.

Statistics must remain useful for the data distribution inside the partitions.

Bulk loading, vacuuming, analyzing, backup, retention, archival, and partition creation should all be considered at partition granularity.

## When Horizontal Partitioning Is Appropriate

Horizontal partitioning is particularly suitable when the table is large and rows naturally separate by a meaningful dimension.

Examples include:

- event histories partitioned by event date
- orders partitioned by order date
- multi-tenant data partitioned by tenant
- geographically separated records partitioned by region
- high-volume equality workloads distributed by hash

The strongest designs are those where the partition key appears naturally in the application's most expensive queries.

## When Vertical Partitioning Is Appropriate

Vertical partitioning is useful when a logical entity has columns with very different access characteristics.

Examples include:

- frequently queried customer identity attributes versus sensitive profile data
- transaction metadata versus large audit payloads
- frequently read product attributes versus large descriptions or documents
- operational records versus infrequently accessed historical metadata

The design should preserve a reliable common key and enforce integrity between fragments.

## Relationship Between the Techniques

Horizontal and vertical partitioning solve different physical-layout problems.

A large order table might use horizontal partitioning because queries are naturally time-based.

A wide customer table might use vertical partitioning because most queries need only a subset of columns.

A large event system might use composite horizontal partitioning because both time locality and customer distribution matter.

These strategies can coexist within one architecture.

The important design principle is to match each table's physical layout to its own workload rather than applying one partitioning technique uniformly across the database.
