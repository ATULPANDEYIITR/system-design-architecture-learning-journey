# Database Sharding: Shard Keys, Routing, and Distributed Storage

## Scope

Database sharding distributes a logical dataset across multiple independently managed storage partitions. Each partition, called a shard, owns a subset of the records. Applications or a routing layer determine which shard should process a request.

Sharding differs from replication. Sharding divides data ownership across partitions, while replication maintains additional copies of data for availability, read scaling, or disaster recovery. A production architecture may combine both techniques by replicating each shard independently.

This project examines three connected mechanisms:

- **Shard keys** determine which records belong together and provide the input for placement decisions.
- **Routing** translates a shard key into a destination and maintains the relationship between logical records and physical storage.
- **Distributed storage** handles partition ownership, queries spanning multiple partitions, shard failures, and data movement as the system grows.

The implementations use a customer-order platform as the main domain. Customer records and their orders are assigned to the same shard so that customer-centric operations can access related data without contacting every partition.

## Core architecture

The system separates the application-facing storage interface from the routing algorithm and physical partition model.

    Application request
          |
          v
    Validate the shard key
          |
          v
    Router or shard directory
          |
          v
    Selected shard
          |
          v
    Local read or write

A request containing a known customer ID can be routed directly to the customer's assigned shard. A request that aggregates orders across every customer may require a scatter-gather operation: each shard computes a partial result, and a coordinator combines those results.

The distinction is important because local and distributed queries have different costs. A customer-local query can usually avoid network communication with unrelated shards. A global aggregation introduces fan-out, coordination, network transfer, and additional failure opportunities.

The code models these architectural responsibilities in memory. It does not implement a distributed database cluster, persistent replication, consensus, or a production-grade transaction protocol.

## Shard keys and data locality

A shard key is the attribute or combination of attributes used to determine data placement. The choice influences distribution, query performance, storage balance, and operational complexity.

### Customer-based partitioning

The principal model uses `customer_id` as the shard key. All orders for a customer follow that customer's current shard ownership.

This arrangement is useful when common requests include:

- Retrieving a customer's order history.
- Creating an order after validating its customer.
- Computing totals for one customer.
- Updating related customer and order records.

The relationship improves data locality because these operations can usually access one shard. It also introduces a constraint: moving a customer to another shard requires moving the associated orders and updating the routing metadata consistently.

The design is not universally optimal. A global order search by `order_id`, an analytics query by region, or a time-based retention operation may require a different access path. Secondary indexes and replicated analytical datasets can address some of these workloads, but they add storage and synchronization costs.

### Properties of a good shard key

A useful key should distribute the workload reasonably evenly, have stable semantics, and appear frequently in operations that benefit from targeted routing.

Key cardinality matters. A key with very few distinct values can create large, uneven partitions. Write concentration matters as well: a single highly active tenant may overload one shard even if the total record distribution appears balanced.

The key should not change casually. A key change can relocate records, invalidate cached routing decisions, and complicate uniqueness enforcement.

A compound key can be appropriate when a tenant alone does not distribute data sufficiently. For example, `(customer_id, order_month)` can divide a customer's historical orders into time-based partitions. That design can improve retention and archival operations, but it may prevent an unqualified customer-history query from reaching only one partition.

## Routing strategies

### Hash-based routing

Hash routing applies a deterministic function to the shard key and maps the resulting value to a partition.

A simple modulo router calculates `hash(key) % shard_count`. It is straightforward and inexpensive, but changing the shard count can remap many keys. Moving large amounts of data during scaling can overwhelm the system.

The Python, JavaScript, C++, and Java implementations use consistent-hashing rings with virtual nodes. A virtual node represents a logical position for a physical shard. Routing selects the first ring position at or after the hashed key and wraps around at the end.

Virtual nodes spread each physical shard across multiple parts of the ring. This generally improves balance compared with assigning only one position per shard. Consistent hashing also limits the number of keys that need new owners when the ring changes, although the exact distribution depends on the hash function, ring construction, and workload.

Stable routing requires more than choosing a hash function. Every routing participant must agree on the hash algorithm, key encoding, virtual-node count, shard identifiers, and metadata version. The C++ example explicitly identifies its FNV-1a hash as a compact demonstration rather than a production placement contract.

### Range-based routing

Range routing maps intervals of key values to specific shards. The implementations use half-open intervals of the form `[start, end)`.

For example, a numeric range from `0` through `999` belongs to one shard, while the interval beginning at `1000` belongs to the next. This convention makes adjacent intervals unambiguous.

Range routing supports ordered scans and can make time-based or numeric queries efficient. It also has limitations. Sequential keys can concentrate new writes on the newest range, producing a hot shard. Gaps in range ownership cause routing failures, and overlapping ranges can make placement ambiguous.

The Python and Java implementations reject overlapping ranges. The SQL implementation uses a PostgreSQL exclusion constraint to prevent overlapping interval assignments.

### Directory-based routing

A routing directory explicitly records the shard that owns a key. It is useful when placement must support controlled migration, manual reassignment, or policies that cannot be represented by a simple hash function.

Directory-based routing requires metadata lifecycle management. Updates must be durable, concurrent writers must use the correct owner, and stale clients must not continue writing to a former shard. Version numbers and epochs help detect stale routing state, but a version counter alone does not provide distributed consistency.

The Java implementation models a directory epoch, and the PostgreSQL schema stores mapping versions. These values represent the metadata state that a production routing service would need to distribute and validate.

## Python implementation

The Python script combines routing, storage, operational inspection, and executable tests.

`ConsistentHashRing` builds a ring of virtual nodes using SHA-256-derived positions. It uses binary search to locate the destination, avoiding a full scan of all ring entries for each request.

`ShardDirectory` maintains the registered shard objects and the current ring. It increments an epoch when its membership changes. The directory lock protects its local mutations, but it does not coordinate independent processes or database servers.

`ShardedDatabase` provides the application-facing operations. Customers are stored under customer-specific keys, and orders are assigned using the customer's recorded location. The separate customer and order indexes allow direct lookup by logical identifier without scanning all shards.

The customer-order relationship is validated before an order is created. Duplicate customer and order identifiers are rejected, missing customers cannot receive orders, and unavailable shards produce explicit failures.

The global `all_orders` method implements scatter-gather semantics by reading each shard and combining its orders. The simulation deliberately rejects the whole query when a shard is unavailable. Production systems must decide whether to fail the entire request, return explicitly marked partial results, or use another policy.

`health_report` exposes per-shard record counts, availability, and local version counters. `validate_indexes` compares routing metadata against stored records, providing a basic consistency diagnostic.

The migration functions model a controlled snapshot copy. They capture the source version, stage records, verify the copied values, update ownership metadata, and remove the source records. The lock protects this particular in-memory workflow from mutations through the same facade.

This migration is not a general online migration protocol. It does not capture writes from other processes, replay a change log, coordinate replica lag, or recover from every possible crash boundary. Those requirements need durable state transitions and an explicit consistency protocol.

The unit tests exercise customer locality, duplicate detection, missing-parent rejection, unavailable-shard behavior, index validation, range boundaries, and a controlled migration.

## JavaScript implementation

The JavaScript file presents sharding as an event-driven Node.js service.

`VirtualShardRouter` uses Node's cryptographic hashing support and binary search. The implementation does not depend on JavaScript's general-purpose object hashing or a third-party package.

`ShardedOrderService` extends `EventEmitter` and publishes audit events when customers, orders, and shards are created. The events separate operational observation from the core write methods, making it possible to connect logging or monitoring consumers without embedding every reporting action in the storage interface.

The storage layer uses `Map` objects for explicit key-value ownership and clones records at its boundaries. The example uses `structuredClone`, which is available in modern Node.js runtimes. This avoids exposing mutable references to stored objects, although cloning alone is not a complete security or concurrency mechanism.

`ordersForCustomer` demonstrates targeted routing. `allOrders` demonstrates bounded asynchronous fan-out using worker functions, promises, and timeouts. Its concurrency limit prevents the coordinator from starting an unbounded number of shard operations at once.

The timeout protects callers from waiting indefinitely, but it cannot cancel arbitrary underlying remote work. A production client should use transport-level cancellation and distinguish timeout, connection failure, and a shard that is known to be offline.

The event listener collects audit records, and assertions validate expected outcomes. Error paths cover invalid keys, duplicate records, missing customers, negative amounts, and unavailable shards.

## C++ case study

The C++ program models a storage gateway for a multi-tenant order service. Its primary design concern is separating routing policy from the structures that hold customer and order data.

`StableHasher` defines an interface for key placement. `Fnv1aHasher` supplies a deterministic implementation for the case study, while `ConsistentHashRouter` builds the virtual-node ring and uses binary search for lookups.

The router does not directly own the data. `OrderStorageGateway` maintains the shard collection and the location indexes that connect customer and order identifiers to their owners. The distinction allows routing and storage responsibilities to be tested independently.

The gateway rejects duplicate identifiers, missing customers, negative monetary amounts, and inconsistent directory entries. Monetary amounts use integer cents to avoid floating-point rounding in financial totals.

The customer-local query reads only the customer's owner shard. The revenue query iterates across every shard and aggregates totals by customer. This demonstrates the operational distinction between targeted requests and scatter-gather operations.

The migration method moves one customer's record and associated orders as a unit within the controlled model. It stages the target records and validates their existence before changing the location indexes and deleting the source copies.

The method demonstrates the ordering of a migration, not a distributed atomic commit. A production gateway would need write fencing, durable progress records, retry-safe operations, and a recovery procedure for interruptions between copying data and changing ownership.

The range router provides a second placement strategy. It validates overlapping intervals during configuration and rejects keys outside the configured ranges.

The hash implementation is intentionally modest. FNV-1a is used for deterministic educational placement, not as a security boundary or a universal production hash. A deployed routing system should select a stable algorithm appropriate to its threat model and compatibility requirements.

## Java enterprise model

The Java program uses explicit domain classes and services to separate business rules from storage placement.

`Customer` and `Order` validate their required fields at construction. Orders use `Instant` for timestamps and integer cents for monetary amounts. These choices avoid ambiguous timestamps and floating-point errors in the modeled order values.

`ShardRouter` defines a common routing interface. `HashRouter` uses SHA-256-derived positions and virtual nodes, while `RangeRouter` validates non-overlapping ranges and accepts numeric keys. This makes the routing policy replaceable without changing the domain model.

`ShardDirectory` owns shard registration and the maps from customer and order identifiers to their current owners. Its epoch records local metadata changes. The synchronized methods protect the in-process model, but Java synchronization does not coordinate multiple service instances or remote databases.

`OrderService` implements the domain workflow. Creating an order requires an existing customer and uses the customer's recorded owner rather than independently guessing a destination from a potentially stale mapping. This helps preserve customer-order locality.

The revenue service aggregates records across shards and uses `Math.addExact` to detect integer overflow instead of silently wrapping a total.

Customer migration stages the destination records, checks for conflicts, changes the ownership metadata, and removes the source copies. This illustrates why migration is more than recalculating a hash: the stored records and their directory entries must remain consistent throughout the operation.

The validation method checks that every stored customer and order agrees with the directory. A production implementation should also detect directory entries pointing to absent records, persist changes atomically where possible, and report replica divergence.

## PostgreSQL relational model

The SQL script uses a dedicated `sharding_lab` schema and PostgreSQL-specific features.

### Shard and directory metadata

`shards` stores logical shard identifiers, endpoints, lifecycle state, and capacity weights. `shard_map` associates routing keys with their current owners and records a mapping version.

The routing directory is explicit because a relational database cannot infer a distributed placement policy merely from the existence of multiple storage servers. An application-side router or distributed query layer must interpret the mapping.

The `routing_directory` view joins ownership metadata with shard endpoints and state. This is useful for inspecting the current logical destination without duplicating endpoint information in every mapping.

### Customers and orders

The `customers` table stores customer attributes and their shard assignment. The `orders` table stores each order's shard, customer, monetary amount, status, and timestamp.

The composite unique key on `(shard_id, customer_id)` supports a composite foreign key from orders. This enforces the co-location rule in the logical relational model: an order cannot reference a customer assigned to another shard.

The database constraints also reject blank identifiers and negative order amounts. The customer-time index supports customer-specific order history, while the status-time index supports operational queries that filter orders by state and creation time.

These indexes improve access within the modeled database. A single PostgreSQL server containing a `shard_id` column is not, by itself, a distributed sharding deployment. The schema represents the relationships that a coordinator or distributed database would need to maintain.

### Range assignments

`range_assignments` stores the start-inclusive and end-exclusive bounds of numeric partitions. PostgreSQL's `int8range` and GiST exclusion constraint prevent overlapping intervals.

The exclusion constraint requires the `btree_gist` extension in the target database. A PostgreSQL installation without permission to create this extension must provision it administratively before running the schema.

Gaps remain possible because a gap may be intentional. The script includes a query that detects discontinuities between adjacent ranges so that administrators can distinguish deliberate gaps from missing assignments.

### Migration workflow

`migration_jobs` records the source shard, target shard, routing key, progress state, copied-record count, verification result, and completion time. Its constraints prevent a job from targeting the same shard as its source and prevent an unverified job from being marked committed.

The demonstration moves a customer's orders and customer row inside a transaction, updates the routing directory, and records the migration state. The order foreign key is deferred so that the child rows and parent can change ownership within the same transaction.

This works only for the records visible to this PostgreSQL transaction. It does not atomically move data between independent database clusters. Cross-cluster migrations need a protocol that handles concurrent writes, retries, partial failures, routing cutover, and recovery.

### Operational queries

The SQL examples inspect customer-local order history, per-shard order totals, customer revenue, range routing, and directory consistency. The operational aggregation identifies uneven record placement, although record counts alone do not measure workload: request frequency, data size, and query cost also matter.

The `EXPLAIN` statement exposes the query plan for a shard-key access pattern. Production diagnostics should examine actual execution plans, index usage, query latency, shard skew, network transfer, and the volume of cross-shard traffic.

## Cross-shard queries and consistency

A query restricted to one shard is generally easier to optimize and recover than a query involving every shard. Scatter-gather aggregation requires coordination, and the slowest participating shard can dominate response time.

Cross-shard joins can be particularly expensive because related records may require remote reads and large intermediate results. Co-locating records around the main access pattern reduces this cost but cannot eliminate every global query.

Distributed writes raise a separate issue. A transaction that updates records on multiple independent shards cannot assume that a local database transaction provides global atomicity. Systems may use distributed transactions, sagas, idempotent operations, or application-specific consistency rules. Each approach has different latency, recovery, and failure trade-offs.

The examples intentionally fail global queries when a participating shard is unavailable. Returning partial data can be appropriate for some analytics workloads, but it is dangerous when callers mistake incomplete results for complete totals.

## Resharding and operational risks

Adding a shard changes placement decisions. With simple modulo routing, this can move a large fraction of keys. Consistent hashing generally limits remapping, but moved records still have to be copied, verified, and made available at the new destination.

A controlled migration needs to coordinate several states:

- The source owns the records before copying begins.
- The destination receives a consistent snapshot and verifies it.
- Concurrent changes are captured or blocked during cutover.
- Routing metadata changes only when the destination can serve the records.
- The old copy is removed only after the new owner is established safely.
- Interrupted jobs can resume or roll back without duplicating or losing data.

The migration examples model only part of this lifecycle. They do not provide crash-safe distributed transactions or continuous replication during an online move.

Hot shards remain possible even when hashing distributes keys evenly. A single large tenant, highly active customer, or concentrated write pattern can overload one partition. Monitoring should include request rate, latency, storage size, queue depth, lock contention, and replication lag, not just the number of records.

## Performance considerations

Hash routing provides predictable targeted lookup when the shard key is available. A consistent-hash lookup over a sorted virtual-node ring has logarithmic search complexity in the number of ring positions, while routing through a direct directory generally requires a metadata lookup.

Range routing supports ordered access but requires careful management of boundaries and write distribution. It is often useful when query patterns align with a numeric or temporal range.

Scatter-gather operations scale their coordination work with the number of participating shards. Concurrency limits reduce excessive fan-out, but overly restrictive limits increase latency. Caching can reduce directory traffic, provided that stale ownership information is handled safely.

The right shard count depends on the workload, storage limits, operational capacity, and acceptable coordination cost. More shards can increase parallelism while also increasing metadata, monitoring, migration, and failure-management complexity.

## Security and correctness boundaries

Shard identifiers and endpoint metadata should be treated as trusted configuration rather than accepted directly from untrusted clients. Applications should validate logical keys, authenticate storage connections, authorize tenant access, and avoid exposing internal endpoint details unnecessarily.

A shard key is a placement mechanism, not an authorization mechanism. A request routed to the correct tenant shard must still verify that the caller is allowed to access the requested customer or order.

Stable hashing must also be distinguished from encryption. Hashing determines placement; it does not conceal record contents or protect data in transit. Production deployments require appropriate transport security, access controls, secrets management, backups, and audit logging.

Finally, routing metadata is part of the data correctness model. A stale directory, partially completed migration, or inconsistent secondary index can direct a valid request to a shard that no longer owns its record. Monitoring and repair procedures must treat metadata consistency as a first-class operational requirement.
