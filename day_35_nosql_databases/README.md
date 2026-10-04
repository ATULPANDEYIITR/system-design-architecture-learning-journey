# NoSQL Databases: Key-Value, Document, Column-Family, and Graph Models

## Scope

This repository presents four major NoSQL database families as distinct data-modeling approaches:

- **Key-value databases** store values behind application-controlled keys and are optimized for direct retrieval.
- **Document databases** store aggregate records such as JSON documents whose fields can vary between records.
- **Column-family databases** organize very large datasets around partition and clustering keys, making predictable high-volume reads the central design concern.
- **Graph databases** represent entities as nodes and relationships as edges, making connected-data traversal a primary query operation.

The implementations use the same broad business domain, products, users, sessions, activity, and relationships, but they do not force the same structure onto every database model. Each implementation is designed around the access pattern that makes its database family useful.

The SQL implementation models these structures inside PostgreSQL for examination and experimentation. It does not claim that PostgreSQL itself behaves like a distributed NoSQL database.

---

## Core Data-Model Distinctions

A database model is fundamentally a decision about how data is organized and how applications are expected to retrieve it.

A **key-value model** treats the key as the principal access path. A session service might store `session:u-501` and retrieve the entire session value without asking the database to understand individual fields.

A **document model** treats a document as an aggregate. A product can contain its name, price, tags, inventory, supplier information, and other related attributes in one document. Different documents can legitimately contain different fields when the application domain requires schema flexibility.

A **column-family model**, also called a wide-column model, organizes data around query-driven partitions. The application typically knows the partition key and retrieves rows within that partition according to a clustering or ordering key. This makes the physical distribution strategy closely connected to application queries.

A **graph model** makes relationships first-class data. A user can be connected to products through `PURCHASED`, to other users through `FOLLOWS`, or to entities through domain-specific relationships. A query can then traverse those relationships rather than repeatedly joining independent records.

These distinctions are important because all four systems can store information about a user or product, but the efficient representation and query strategy can be radically different.

---

## Key-Value Databases

### Data Model

The conceptual structure is:

`key -> value`

The value can be a string, number, binary object, JSON structure, session object, or another application-defined representation.

The key-value implementation uses a Python dictionary, JavaScript `Map`, C++ hash map, and Java `Map` to model this access pattern.

The Python implementation provides:

- exact-key retrieval;
- insertion and deletion;
- TTL-style expiration;
- integer counters;
- conditional updates through compare-and-set semantics.

The JavaScript implementation uses `Map` and demonstrates a Node.js-oriented in-memory service. It also uses `structuredClone` for data isolation and JavaScript's exception model for invalid keys and counter values.

The C++ implementation uses `std::unordered_map`, reflecting average constant-time hash-table lookup while making the key/value relationship explicit.

The Java implementation separates the storage behavior into `KeyValueService`. `Optional` is used for missing values, while `compareAndSet` models conditional state changes.

### Appropriate Workloads

Key-value storage is particularly suitable when the application already knows the key.

Typical workloads include:

- HTTP session state;
- authentication session metadata;
- shopping-cart state;
- feature flags;
- cache entries;
- rate-limit counters;
- short-lived application state;
- idempotency keys.

A request such as `get("session:u-501")` is fundamentally different from a query such as "find all sessions belonging to users in a particular region." The former is naturally key-value oriented. The latter requires a different indexing or data-model strategy.

### TTL and Expiration

The Python and JavaScript implementations include expiration behavior because temporary state is an important key-value workload.

A TTL allows an entry to become invalid after a defined period. Applications use this pattern for sessions, cached results, temporary locks, verification state, and rate-limiting data.

A real distributed key-value database may implement expiration internally across replicas. The in-memory implementations here only model the application-level behavior and should not be interpreted as distributed expiration mechanisms.

### Conditional Updates

The Python and JavaScript implementations include compare-and-set behavior.

The semantic rule is:

`replace value only if current value equals expected value`

This is useful when multiple operations can attempt to update the same state. Real databases provide product-specific atomic operations, optimistic concurrency primitives, or transactions. The small implementations model the concept without claiming distributed concurrency guarantees.

---

## Document Databases

### Aggregate-Oriented Storage

A document database represents an entity as a structured document.

The product example contains:

- product identity;
- name;
- category;
- price;
- tags;
- inventory by warehouse.

The document is therefore an aggregate that can be retrieved as a unit.

The Python implementation uses dictionaries and performs validation before insertion. It maintains a category index and demonstrates nested field updates.

The JavaScript implementation uses plain objects and `structuredClone`, with an explicit category index implemented through `Map` and `Set`.

The Java implementation uses immutable records such as `ProductDocument` and `Inventory`. The `ProductCatalog` service maintains a secondary category index while preserving domain validation.

The SQL implementation uses PostgreSQL `JSONB`. It creates a GIN index for document-oriented containment queries and expression indexes for frequently queried scalar fields such as category and price.

### Schema Flexibility

Document databases commonly allow records to evolve without requiring every attribute to be represented as a separate column.

For example, one product may contain:

`{"battery_life_hours": 20}`

while another may contain:

`{"screen_size_inches": 27}`

The application still treats both as product documents.

Schema flexibility does not mean the absence of structure. Production applications still need validation rules for required fields, valid data types, allowed values, document size, nested structures, and version compatibility.

The Python and JavaScript examples explicitly reject missing fields, invalid prices, and malformed tag structures.

### Embedding and Duplication

Embedding related data inside a document can reduce the need for joins when those fields are normally retrieved together.

The product document embeds warehouse inventory:

`inventory.warehouse_a`

This is useful when product retrieval normally requires the current inventory representation.

Embedding can also create duplication. If the same information is copied into thousands of documents, changing the source information can require many updates. A document design therefore depends on read frequency, update frequency, document size, and consistency requirements.

### Indexing

Document databases can provide indexes over fields inside documents.

The PostgreSQL implementation demonstrates three distinct approaches:

- a GIN index over the complete `JSONB` document;
- an expression index over `document->>'category'`;
- an expression index over the numeric price field.

The important design principle is that flexible document structure does not remove the need to understand query patterns. Indexes should correspond to actual workload requirements rather than being created indiscriminately.

---

## Column-Family Databases

### Wide-Column Data Model

A column-family database is not simply a relational table with many columns.

A common wide-column design starts from the query and chooses a partition key that determines where related data belongs.

The activity example uses a conceptual key:

`u-501 | 2026-10-05 | 00:05:00`

The user and date identify the logical partition, while the time identifies an ordered event within that partition.

The important distinction is that the partition structure is part of the data model rather than merely an implementation detail.

### Query-Driven Modeling

The column-family implementations deliberately avoid arbitrary filtering as the primary pattern.

The Python implementation exposes `scan_partition`, the JavaScript implementation provides `queryPartition`, the Java implementation provides `byPartition`, and the C++ implementation provides `partitionScan`.

The expected query is:

"Give me activity for user u-501 on this day."

The model therefore organizes the data around that query.

This differs from a general relational design where an application might normalize event attributes and create indexes independently of the logical partitioning strategy.

### Partition Keys

Partition-key design has major operational consequences.

A useful partition key should distribute workload adequately while keeping data that is commonly read together accessible within the same partition.

A poorly selected key can create a **hot partition**, where a disproportionate amount of traffic reaches one partition.

A partition that grows without bound can also create large reads, inefficient compaction behavior, or operational difficulty.

Time bucketing is therefore common in event-oriented designs. Instead of placing years of events for one user into one unlimited partition, an application can use a user-plus-day or user-plus-month partition depending on expected volume.

### Clustering and Ordering

The time component in the example acts as a clustering dimension.

Queries can retrieve:

`u-501 | 2026-10-05`

and then process events ordered by time.

This structure is especially useful for telemetry, activity streams, event histories, and other high-volume datasets with predictable partition access.

---

## Graph Databases

### Property-Graph Model

The graph implementation uses:

- nodes for entities;
- labels for node types;
- properties for node attributes;
- directed edges for relationships;
- relationship types to express semantic meaning.

The example contains `User` and `Product` nodes connected by `PURCHASED` relationships.

The graph is therefore not just storing product IDs. It explicitly represents the relationship between a particular user and product.

### Relationship-Centric Queries

A graph is useful when the relationship itself is central to the question.

The example asks for recommendations based on shared purchases:

`u-501 -> PURCHASED -> p-100`

followed by:

`u-502 -> PURCHASED -> p-100`

and then:

`u-502 -> PURCHASED -> p-102`

The resulting product can be recommended to `u-501`.

This is naturally a traversal problem.

The Python, JavaScript, C++, and Java implementations represent the graph using adjacency structures and implement traversal directly.

The SQL implementation represents nodes and edges as separate tables and expresses the same two-hop recommendation through common table expressions and joins.

### Breadth-First Search

The C++ and Java implementations demonstrate shortest-path discovery using breadth-first search.

The algorithm maintains:

- a queue of nodes to visit;
- a visited set;
- a parent map for reconstructing the path.

For an unweighted graph, breadth-first search finds a path with the minimum number of edges.

If the graph contains `V` reachable vertices and `E` reachable edges, the traversal is generally `O(V + E)` when adjacency lists are used.

Production graph systems may use specialized indexes, traversal engines, query languages, path constraints, and distributed execution strategies. The examples intentionally expose the core algorithm rather than reproducing a commercial graph database engine.

### Traversal Limits

Relationship queries can become expensive when traversal depth is not controlled.

A query that follows one or two relationship hops may be manageable, while an unrestricted traversal through a highly connected network can produce a very large result set.

Production graph applications should therefore define meaningful traversal depth, relationship filters, result limits, time constraints, and authorization boundaries.

---

## The Four Models Are Not Interchangeable

| Model | Primary structure | Natural access pattern | Strong fit |
| --- | --- | --- | --- |
| Key-value | Key and opaque value | Exact key | Sessions, cache, counters |
| Document | JSON-like aggregate | Document and field queries | Catalogs, profiles, content |
| Column-family | Partition plus clustering dimensions | Partition-oriented reads | Events, telemetry, large activity histories |
| Graph | Nodes and relationships | Traversal | Fraud, recommendations, social networks |

The distinction is about more than syntax.

A key-value design asks, "What key will the application know?"

A document design asks, "What aggregate should be retrieved and updated together?"

A column-family design asks, "What partition and ordering support the expected high-volume queries?"

A graph design asks, "What entities are connected, and how will those relationships be traversed?"

---

## Python Implementation

The Python script is the broadest executable laboratory.

`KeyValueStore` demonstrates exact-key state, TTL behavior, counters, and conditional updates.

`DocumentStore` demonstrates document validation, category indexing, nested updates, and field predicates.

`ColumnFamilyStore` models partition-oriented wide-column access using row keys containing user, date, and timestamp dimensions.

`GraphStore` implements nodes, edges, neighbor discovery, breadth-first shortest-path traversal, and two-hop product recommendations.

The script also demonstrates serialization with JSON and explicitly rejects invalid document structures. The final operational section connects each model to production concerns such as partition design, observability, security, backup, and capacity planning.

---

## JavaScript Implementation

The JavaScript implementation is intentionally event-oriented.

It uses `Map` for key-value and document indexes, `Set` for membership and graph traversal, and asynchronous generators for streaming column-family rows.

The `NoSqlWorkflow` class extends Node.js `EventEmitter`. Document changes and cache invalidations become application events, showing how a JavaScript service can connect persistence operations with asynchronous application workflows.

`structuredClone` is used when returning or storing mutable objects so callers do not accidentally share references with the internal store.

The graph implementation uses adjacency lists and breadth-first traversal rather than translating the Python class structure directly.

---

## C++ Case Study

The C++ program models a coherent product platform rather than providing isolated syntax examples.

The key-value subsystem represents session and rate-limit state with `std::unordered_map`.

The document subsystem represents products using `ProductDocument`. A secondary category index supports category retrieval while the document itself retains nested inventory.

The column-family subsystem models activity using a `WideRow` structure. The partition key is combined with a clustering-style time key, making the intended query path visible in the data structure.

The graph subsystem stores `GraphNode` objects and adjacency lists of `GraphEdge` objects. Breadth-first search is used to find a shortest relationship path, while a two-hop traversal produces product recommendations based on shared purchases.

The program also demonstrates C++ exception handling and `std::optional` for missing values. The explicit ownership and container choices make the memory and algorithmic characteristics visible.

---

## Java Enterprise Implementation

The Java program emphasizes domain modeling and service boundaries.

`KeyValueService` represents temporary application state and conditional updates.

`ProductDocument` and `Inventory` are Java records, making the document-oriented domain values immutable after construction. `ProductCatalog` owns document validation and maintains a category index.

`ActivityWideTable` models partition-oriented activity records.

`ProductGraph` uses explicit enums for relationships, records for graph values, adjacency lists for traversal, and breadth-first search for shortest-path discovery.

`AuditService` provides an enterprise-style audit layer using immutable `AuditEvent` records. This is particularly relevant when NoSQL operations participate in larger service workflows where changes need to be observable and attributable.

The design uses standard Java 17 facilities rather than third-party persistence libraries so the underlying data-model concepts remain visible.

---

## PostgreSQL SQL Model

The SQL script models all four database families relationally for inspection.

### Key-value tables

`kv_store` contains a primary key and a `JSONB` value. An optional expiration timestamp represents TTL-oriented application state.

The primary key directly supports exact-key lookup.

### Document tables

`product_documents` contains a document identifier and a `JSONB` payload.

Database constraints enforce:

- required document fields;
- numeric non-negative prices;
- array-shaped tags;
- non-empty identifiers.

The GIN document index and scalar expression indexes demonstrate different indexing strategies.

### Wide-column tables

`wide_column_rows` separates:

- column family;
- partition key;
- clustering key;
- variable column payload.

The composite primary key represents the intended partition-oriented lookup.

### Graph tables

`graph_nodes` stores entities and their properties.

`graph_edges` stores relationships between nodes.

Foreign keys prevent edges from referring to nonexistent nodes. A unique constraint prevents duplicate directed relationships of the same type between the same pair of nodes.

Indexes on source and target relationship columns support common traversal directions.

The recommendation query uses common table expressions to express a two-hop graph traversal through relational joins.

---

## Consistency and Integrity

"NoSQL" does not mean "no consistency."

Consistency behavior depends on the particular database product, deployment topology, replication configuration, transaction model, and application requirements.

Possible requirements include:

- strong consistency for critical state;
- eventual consistency for replicated read models;
- optimistic concurrency for documents;
- conditional writes for counters or state transitions;
- conflict resolution for replicated updates;
- idempotency for retried operations.

The examples deliberately distinguish application-level modeling from distributed-database guarantees.

The in-memory implementations do not provide distributed durability or replication. Their purpose is to expose the data structures and access patterns.

The PostgreSQL script provides transactional and constraint-based integrity because PostgreSQL is being used as an executable laboratory for the models, not as a claim that every NoSQL product provides the same semantics.

---

## Schema Evolution

Document flexibility can simplify evolution, but it does not eliminate compatibility problems.

A service may need to read:

- documents written by an older application version;
- documents containing newly introduced fields;
- documents missing optional fields;
- documents using an older representation of a field.

Version fields can help applications distinguish representations.

The SQL document example includes a `version` column. The Python, JavaScript, and Java implementations validate the structure they require rather than assuming every possible future document shape is valid.

Schema evolution should be treated as an application compatibility problem as well as a database problem.

---

## Performance Considerations

### Key-value

Exact-key access is normally the defining performance advantage. Hash-based access is efficient when keys are well distributed.

Performance can degrade when applications misuse a key-value store as a search engine or repeatedly retrieve very large values.

Counters and frequently updated keys can become hotspots in distributed systems if many clients target the same key.

### Document

Indexes should follow actual query patterns.

Large documents can increase network transfer and update cost. Embedding improves locality for related data but can increase duplication.

Unbounded document growth should be avoided because one logical entity can become disproportionately expensive to retrieve or update.

### Column-family

Partition design is critical.

A good partition strategy distributes load and keeps expected reads bounded. A poor strategy can create hot partitions or oversized partitions.

The clustering dimension should correspond to real query ordering requirements.

### Graph

Traversal cost depends heavily on graph topology and traversal depth.

Highly connected nodes can produce enormous intermediate result sets. Relationship filters and traversal limits therefore have direct performance value.

Graph indexes help locate starting nodes, but the cost of the traversal itself must also be considered.

---

## Security Considerations

The examples include basic validation, but production security requires more than validating data structures.

A real deployment should enforce:

- authentication for clients and services;
- authorization based on users, services, roles, and resources;
- TLS for data in transit;
- encryption at rest where required;
- secure secret storage;
- audit logging for sensitive operations;
- network segmentation;
- rate limiting;
- backup protection;
- controlled administrative access.

Document query features also require careful handling of user-controlled query structures. Applications should use allow-listed fields and validated operators rather than blindly passing arbitrary query expressions from clients to database engines.

Key-value keys should also be validated when they are constructed from external input. Control characters and untrusted prefixes can create logging, routing, or operational problems.

---

## Failure Modes

Different NoSQL models expose different failure risks.

A key-value application can fail because a required key is missing, expired, overwritten, or concentrated on a hot partition.

A document application can fail because documents have incompatible versions, become excessively large, or contain fields that no longer match application expectations.

A column-family application can fail because partition keys create hotspots, partitions become excessively large, or queries ignore the designed access path.

A graph application can fail because traversal depth is unrestricted, highly connected nodes produce huge result sets, or relationships are modeled too loosely to support meaningful filtering.

These failures are data-model failures as much as application failures.

---

## Common Modeling Mistakes

### Treating every NoSQL database as a schema-free key-value store

The four models have substantially different assumptions. A graph database is not merely a document store with IDs, and a wide-column database is not simply a relational table with more columns.

### Designing the database before understanding queries

This is particularly dangerous for column-family systems. Partition and clustering decisions should be derived from expected query patterns.

### Embedding everything in documents

Embedding is valuable when data belongs to an aggregate and is normally accessed together. Excessive embedding can cause duplication, large documents, and difficult updates.

### Creating unlimited graph traversals

Graph queries should have explicit traversal boundaries. A relationship that looks harmless at one hop can become expensive when recursively followed through a dense network.

### Ignoring consistency requirements

Choosing a NoSQL product because it scales horizontally is insufficient if the application requires a consistency guarantee that the chosen architecture cannot reliably provide.

### Treating indexes as free

Indexes consume storage and write resources. Each index should correspond to an important access pattern and be monitored for effectiveness.

---

## When to Choose Each Model

A **key-value database** is a strong candidate when the application predominantly retrieves state using known keys and values can be treated as application-owned objects.

A **document database** is a strong candidate when the application works with aggregate-shaped records, fields can evolve, and queries need to inspect selected document attributes.

A **column-family database** is a strong candidate when data volume is very large, access patterns are predictable, and the application can design efficient partition and clustering keys around those queries.

A **graph database** is a strong candidate when relationships are central to the business problem and useful queries require traversing those relationships across multiple hops.

A single enterprise system can legitimately use more than one model. A session service might use key-value storage while a product catalog uses documents, event analytics uses wide-column storage, and fraud analysis uses a graph.

The important architectural decision is not to choose one NoSQL family for every workload. It is to match the data model to the dominant access pattern, consistency requirement, scale characteristics, and operational constraints of each workload.
