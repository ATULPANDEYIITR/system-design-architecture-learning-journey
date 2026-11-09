# Service Discovery: Registration, Discovery, and Health Checks

## 1. Introduction

Service Discovery is a mechanism through which applications identify available service instances without maintaining fixed network addresses for every dependency.

In a distributed application, services may run across multiple virtual machines, containers, availability zones, or physical servers. Instances can start, stop, restart, change addresses, become unhealthy, or move between deployment environments.

Service Discovery maintains information about these instances and makes eligible endpoints available to service consumers.

A service registry is the central logical component responsible for maintaining service-instance information.

The implementations in this project demonstrate service registration, endpoint discovery, health monitoring, lease expiration, load balancing, circuit breakers, registration authorization, and graceful deregistration.

## 2. Fundamental Concepts

### 2.1 Service

A service is a logical application capability exposed through a network interface.

Examples include:

- Payment processing
- Inventory management
- Authentication
- Order management
- Notification delivery
- Customer account management

A service name identifies the logical capability rather than a particular machine.

For example, `payment-service` can have several running instances.

### 2.2 Service Instance

A service instance is one running deployment of a service.

An instance normally contains:

| Attribute | Description |
|---|---|
| Instance ID | Unique identifier for the running instance |
| Service name | Logical service identifier |
| Host | IP address or hostname |
| Port | Network port |
| Version | Deployed service version |
| Region | Geographic deployment region |
| Metadata | Additional discovery attributes |
| Health | Current health state |
| Lease | Maximum permitted heartbeat interval |
| Weight | Relative routing preference |

Two instances can implement the same service while running on different hosts.

For example:

| Service | Instance | Endpoint |
|---|---|---|
| payment-service | pay-001 | 10.0.1.10:8001 |
| payment-service | pay-002 | 10.0.1.11:8001 |
| inventory-service | inv-001 | 10.0.2.10:8002 |

The service name identifies the capability. The instance identifier distinguishes individual deployments.

### 2.3 Service Registry

A service registry stores information about registered instances.

It supports:

- Instance registration
- Instance updates
- Heartbeat processing
- Health-state management
- Instance deregistration
- Lease expiration
- Service lookup
- Endpoint selection

A registry can be implemented using an in-memory data structure, a relational database, a distributed key-value store, or a dedicated discovery platform.

The Python implementation uses dictionaries and a reentrant lock. JavaScript uses Maps and Sets. C++ uses unordered maps and ordered sets. Java uses concurrent collections. PostgreSQL uses normalized relational tables.

### 2.4 Service Consumer

A service consumer is an application that needs to communicate with another service.

Instead of depending on a fixed endpoint, the consumer queries the registry for eligible instances.

For example:

1. An order service needs payment processing.
2. It requests available payment-service instances.
3. The registry filters instances using health, version, region, and lease information.
4. The consumer selects an eligible endpoint.
5. The consumer sends its request to that endpoint.

The consumer should not assume that an endpoint remains available indefinitely. Discovery results can become stale after retrieval.

## 3. Service Registration

Registration is the process through which a running instance announces its availability and publishes its identifying information.

### 3.1 Registration Workflow

The registration process follows these stages:

1. A service instance starts.
2. It generates or receives a unique instance identifier.
3. It provides its service name and network endpoint.
4. It supplies its version and deployment metadata.
5. The registry validates the registration.
6. The registry creates an instance record.
7. The instance begins sending heartbeats.
8. Health monitoring evaluates the instance.
9. The instance becomes discoverable after satisfying health requirements.

Registration and health are separate operations.

A successfully registered instance is not automatically healthy. It may still be starting, initializing its dependencies, or waiting for its first successful health checks.

### 3.2 Registration Validation

A registry should validate:

- Non-empty service names
- Valid host addresses
- Valid network ports
- Unique instance identifiers
- Supported versions
- Positive lease durations
- Valid endpoint weights
- Authorized production registrations
- Valid metadata

The Java implementation uses an explicit registration policy to restrict production registration to authorized service owners.

The PostgreSQL implementation performs authorization checks through the service ownership relationship.

### 3.3 Registration Models

Two common registration approaches are used in distributed systems.

| Model | Description | Responsibility |
|---|---|---|
| Self-registration | The service registers itself | Service instance |
| Third-party registration | An external controller registers instances | Deployment platform or registry agent |

Self-registration gives an application direct control over its lifecycle. Third-party registration centralizes registration responsibilities and can integrate with container orchestration.

The implementations primarily demonstrate explicit registration through registry operations.

## 4. Service Discovery

Service Discovery is the process of locating eligible service instances using their logical service identity.

A consumer requests a service name rather than a fixed machine address.

### 4.1 Discovery Workflow

The discovery operation applies several filters:

- Service identity
- Registration state
- Health state
- Lease validity
- Version compatibility
- Region
- Deployment environment
- Metadata requirements

Only instances satisfying the discovery policy are returned.

For example, a production order-processing application may require:

| Attribute | Required value |
|---|---|
| Service | payment-service |
| Version | 2.1.0 |
| Region | ap-south-1 |
| Environment | production |
| Health | HEALTHY |
| Registration | ACTIVE |
| Lease | Not expired |

An instance with an incorrect version or expired lease must not be returned merely because it has the correct service name.

### 4.2 Metadata-Based Discovery

Metadata provides additional information about service instances.

Examples include:

- Deployment environment
- Availability zone
- Region
- Protocol
- Release identifier
- Deployment identifier
- Hardware class

Metadata filtering allows consumers to locate instances according to deployment requirements.

For example, an application can request instances in a particular region without knowing their IP addresses.

Metadata should remain controlled and validated. Arbitrary metadata must not be interpreted as trusted authorization information.

### 4.3 Client-Side Discovery

In client-side discovery, the consumer communicates with the registry and selects an instance.

Workflow:

Consumer → Registry → Eligible Instances → Consumer Selection → Service Instance

Advantages:

- Direct control over endpoint selection
- Flexible load-balancing algorithms
- Reduced dependence on a separate routing proxy

Limitations:

- Consumers require discovery integration.
- Different clients may implement inconsistent selection policies.
- Discovery results can become stale.
- Endpoint retry and connection handling must be implemented correctly.

The Python, C++, and Java implementations demonstrate client-side endpoint selection.

### 4.4 Server-Side Discovery

In server-side discovery, the consumer sends a request to an intermediary such as a load balancer or service proxy.

Workflow:

Consumer → Load Balancer or Proxy → Registry or Endpoint Catalog → Service Instance

The intermediary handles endpoint selection and forwarding.

Advantages:

- Consumers do not need direct registry integration.
- Routing policies can be centralized.
- Endpoint selection can be standardized.

Limitations:

- The intermediary introduces another operational dependency.
- Routing infrastructure must remain highly available.
- Additional network hops can affect latency.

Server-side routing is not implemented as a network proxy in this project. The registry and endpoint-selection components provide the underlying decision logic.

## 5. Health Checks

Health checks determine whether a registered service instance can safely receive new requests.

Registration confirms that an instance has been announced. Health monitoring evaluates its operational condition.

### 5.1 Types of Health Checks

| Check type | Purpose |
|---|---|
| Liveness | Determines whether the application process is running |
| Readiness | Determines whether the instance can accept requests |
| Startup | Determines whether initialization has completed |
| Dependency health | Evaluates required external dependencies |
| Active health check | An external monitor sends a probe |
| Passive health check | Request failures contribute to health evaluation |

Liveness and readiness must not be treated as interchangeable.

A process can be alive while being unable to serve requests because its database connection pool is unavailable or initialization remains incomplete.

A dependency failure should also be interpreted carefully. An optional dependency should not necessarily make the entire service unavailable.

### 5.2 Active Health Monitoring

An active health monitor periodically sends a request to an instance.

The response is evaluated according to a configured policy.

Possible outcomes include:

- Successful response
- Failed response
- Connection timeout
- Invalid response
- Network error

A health check should use a bounded timeout. Otherwise, slow or unreachable instances can consume monitoring resources indefinitely.

The JavaScript implementation supports asynchronous health probes with configurable concurrency.

The PostgreSQL implementation records individual health-check results and processing timestamps.

### 5.3 Passive Health Monitoring

Passive monitoring evaluates the results of actual service requests.

For example, repeated connection failures can indicate that an endpoint should temporarily stop receiving traffic.

Passive monitoring provides information from real request traffic, but it must distinguish infrastructure failures from application-level errors.

A rejected business request does not necessarily mean that an instance is unhealthy.

### 5.4 Health-State Model

The project uses four health states.

| State | Meaning | Discoverable |
|---|---|---|
| UNKNOWN | No sufficient health evidence | No |
| HEALTHY | Passed configured recovery requirements | Yes |
| UNHEALTHY | Failed configured failure requirements | No |
| DRAINING | Preparing for removal from service | No |

The health-state transition model is:

UNKNOWN → HEALTHY

HEALTHY → UNHEALTHY

UNHEALTHY → HEALTHY

HEALTHY → DRAINING

UNKNOWN → UNHEALTHY

DRAINING is a controlled operational state. It should not automatically transition back to HEALTHY through ordinary probe processing.

### 5.5 Consecutive Success and Failure Thresholds

A single successful health check may not provide enough evidence that a previously unhealthy service has recovered.

Similarly, one failed check may be caused by a temporary network interruption.

The implementations use configurable thresholds.

Example:

- Failure threshold: 2
- Recovery threshold: 2

Two consecutive successful checks allow an instance to become healthy.

Two consecutive unsuccessful checks cause an instance to become unhealthy.

A successful result resets the failure counter. A failed result resets the success counter.

This reduces unnecessary state changes caused by transient failures.

The thresholds must be selected according to the service's expected response time and monitoring interval.

## 6. Heartbeats and Lease Expiration

A heartbeat is a periodic signal indicating that an instance remains registered and responsive to the registry's liveness protocol.

A lease defines the period for which the registry considers the last heartbeat valid.

For example:

- Lease duration: 30 seconds
- Heartbeat interval: 10 seconds

If the registry does not receive another heartbeat before the lease expires, the instance is no longer eligible for discovery.

### 6.1 Lease Expiration

The expiration condition is:

`current_time > last_heartbeat + lease_duration`

The registry can remove expired instances or mark them as inactive.

The implementations demonstrate automatic expiration and cleanup.

The PostgreSQL implementation provides an expiration function that identifies expired active registrations and changes their registration state.

### 6.2 Heartbeat Versus Health Check

These mechanisms measure different properties.

| Mechanism | What it establishes |
|---|---|
| Heartbeat | The instance continues communicating with the registry |
| Health check | The instance satisfies an operational health condition |
| Lease | The validity period of the last heartbeat |
| Readiness | The instance can accept application traffic |

A heartbeat alone does not prove that an application can successfully process business requests.

A healthy result also does not eliminate the need for lease validation.

### 6.3 Clock Considerations

Distributed systems should avoid relying on unsynchronized wall clocks for lease ownership and timeout decisions.

Monotonic clocks are preferable for measuring elapsed time within a process.

The Python implementation uses elapsed-time calculations. The C++ implementation uses `std::chrono::steady_clock`.

The JavaScript and Java implementations use timestamps for their simplified lease simulations. Production systems should account for clock synchronization and distributed coordination requirements.

## 7. Endpoint Selection and Load Balancing

Discovery identifies eligible endpoints. Load balancing determines which eligible endpoint receives a particular request.

These are separate operations.

A registry can correctly return three healthy endpoints while a consumer still makes poor routing decisions.

### 7.1 Round-Robin Selection

Round-robin distributes requests across available endpoints in sequence.

Example:

| Request | Selected instance |
|---|---|
| 1 | pay-001 |
| 2 | pay-002 |
| 3 | pay-003 |
| 4 | pay-001 |
| 5 | pay-002 |

The Python and C++ implementations use round-robin selection.

Its advantages include simplicity and predictable distribution when instances have similar capacity.

Its limitation is that it does not account for differences in processing capacity or current load.

### 7.2 Weighted Selection

Weighted selection assigns a relative weight to each endpoint.

For example:

| Instance | Weight |
|---|---:|
| pay-001 | 3 |
| pay-002 | 1 |

The first instance receives approximately three times the selection probability of the second instance when both are eligible.

The JavaScript, C++, and Java implementations demonstrate weighted random selection.

Weights represent configured routing preference, not measured utilization.

Dynamic load-aware routing requires additional metrics and an update mechanism.

### 7.3 Filtering Before Selection

Load balancing must occur after discovery eligibility filtering.

The correct sequence is:

1. Identify instances belonging to the requested service.
2. Check registration state.
3. Check health.
4. Check lease validity.
5. Apply version and metadata constraints.
6. Apply circuit-breaker restrictions.
7. Select an endpoint.

Selecting an unhealthy endpoint and then attempting to reject it during request processing wastes resources and can increase failure rates.

## 8. Circuit Breakers

A circuit breaker prevents repeated requests to an endpoint that is experiencing failures.

It is a request-protection mechanism rather than a replacement for health monitoring.

### 8.1 Circuit States

| State | Behavior |
|---|---|
| CLOSED | Requests are allowed |
| OPEN | Requests are temporarily blocked |
| HALF_OPEN | A limited recovery request is allowed |

The transition model is:

CLOSED → OPEN → HALF_OPEN → CLOSED

A configured failure threshold opens the circuit.

After the reset period, the circuit becomes eligible for a recovery attempt.

A successful recovery closes the circuit. A failed recovery should reopen it.

### 8.2 Circuit Breaker Versus Health Monitoring

Health monitoring evaluates whether an instance is suitable for service traffic.

A circuit breaker limits requests after repeated failures.

These mechanisms can operate independently.

An instance can be registered and report a healthy probe while its circuit breaker remains open because recent application requests failed.

The implementations demonstrate circuit-breaker state and request-result recording.

The simplified implementations do not include every production concern, such as single-probe ownership during half-open recovery or distributed breaker coordination.

## 9. Graceful Deregistration and Draining

Immediate termination of a service instance can interrupt requests already in progress.

Graceful draining allows an instance to stop receiving new requests before it is terminated.

Typical workflow:

1. The deployment controller initiates draining.
2. The registry changes the instance state to DRAINING.
3. Discovery excludes the instance.
4. Existing connections are allowed to complete.
5. The application stops accepting new work.
6. The instance is deregistered.
7. The process terminates.

Deregistration removes an instance from the registry.

Draining is a transitional operational state. It should not be confused with deregistration.

The implementations preserve this distinction.

## 10. Python Implementation

The Python program models service registration and discovery using standard-library components.

### 10.1 Architecture

| Component | Responsibility |
|---|---|
| `ServiceInstance` | Stores service-instance attributes |
| `HealthMonitor` | Evaluates consecutive health results |
| `ServiceRegistry` | Manages registrations and discovery |
| `ServiceClient` | Selects endpoints and simulates requests |
| `ServiceError` | Represents operational failures |

### 10.2 Data Structures

The main registry uses a dictionary keyed by instance identifier.

This provides average O(1) lookup, registration, and deletion.

A second dictionary stores round-robin positions for each service.

A reentrant lock protects shared registry state against concurrent updates.

### 10.3 Persistence

The registry supports JSON snapshot persistence.

The snapshot is written to a temporary file and then moved into place using atomic replacement.

This reduces the possibility of exposing a partially written snapshot.

The persistence mechanism is intended for demonstration and recovery exercises. It is not a distributed registry replication protocol.

### 10.4 Failure Handling

The implementation covers:

- Duplicate instance identifiers
- Invalid endpoints
- Missing services
- Expired leases
- Unhealthy instances
- Invalid health thresholds
- Connection failures
- Retry exhaustion

The assertions validate registration, health transitions, expiration, deregistration, and missing-service handling.

## 11. JavaScript Implementation

The JavaScript program emphasizes event-driven registry operations and asynchronous monitoring.

### 11.1 Architecture

| Component | Responsibility |
|---|---|
| `ServiceRegistry` | Maintains instance records and discovery |
| `CircuitBreaker` | Evaluates endpoint request failures |
| `validateInstance` | Validates registration input |
| `EventEmitter` | Publishes registry lifecycle events |

### 11.2 Event-Driven Operations

The registry publishes events for:

- Registration
- Deregistration
- Heartbeats
- Health transitions
- Draining
- Request results

Consumers of these events can maintain metrics, generate audit records, or trigger additional operational workflows.

### 11.3 Asynchronous Health Monitoring

The `probeAll` method executes asynchronous health probes.

Its concurrency parameter limits the number of simultaneous probes.

This avoids starting an unrestricted number of asynchronous operations when monitoring a large registry.

Each probe produces an individual result that updates the corresponding instance.

### 11.4 Discovery Cache

The implementation maintains a short-lived discovery cache.

Registration, deregistration, draining, and health transitions invalidate cached service results.

The cache also distinguishes version and metadata filters.

Caching improves repeated discovery performance but introduces a freshness trade-off.

Production systems must define an acceptable maximum staleness period and ensure all registry mutation paths invalidate or version cached results.

### 11.5 Weighted Routing

The JavaScript implementation uses weighted random selection.

An endpoint's probability is proportional to its configured weight among eligible candidates.

The implementation also uses circuit-breaker state to exclude endpoints whose circuits are open.

## 12. C++17 Implementation

The C++ program provides a strongly typed service registry and endpoint-selection engine.

### 12.1 Domain Model

The principal structures are:

- `ServiceInstance`
- `HealthPolicy`
- `CircuitBreaker`
- `ServiceRegistry`

Enumerations represent health and circuit-breaker states.

The registry uses STL containers to manage instance identity, service membership, routing counters, and endpoint metadata.

### 12.2 Container Selection

| Container | Purpose |
|---|---|
| `unordered_map` | Fast instance and circuit-breaker lookup |
| `set` | Ordered instance identifiers within a service |
| `map` | Metadata key-value pairs |
| `vector` | Deployment records and discovery results |
| `optional` | Optional version filters |

### 12.3 Endpoint Selection

The program implements both round-robin and weighted random selection.

The weighted implementation uses `std::mt19937` and `std::uniform_int_distribution`.

The random generator is supplied to the selection method, making the selection mechanism explicit.

### 12.4 Complexity

For a registry containing N instances:

| Operation | Expected complexity |
|---|---|
| Registration | O(1) average plus index insertion |
| Instance lookup | O(1) average |
| Deregistration | O(1) average plus index maintenance |
| Heartbeat | O(1) average |
| Discovery | O(K + F) |
| Round-robin selection | O(K) |
| Weighted selection | O(K) |

Here, K represents instances associated with the requested service, while F represents the number of metadata filters applied across the candidates.

The implementation prioritizes understandable domain behavior over distributed coordination.

Its containers are not internally synchronized. A production multithreaded implementation requires locks, immutable snapshots, or a carefully designed concurrent data structure.

## 13. Java 17 Implementation

The Java implementation models an enterprise service catalog with explicit registration policies and concurrent data structures.

### 13.1 Enterprise Domain Types

The program uses:

- Records for immutable descriptors and registration requests
- Enums for lifecycle and health states
- Interfaces for registration policies
- Concurrent maps for shared registry data
- Atomic integers for endpoint selection counters
- Streams for discovery filtering
- Custom exceptions for domain failures

### 13.2 Registration Authorization

Production registration is subject to owner authorization.

The registration policy verifies that:

1. The service owner is authorized.
2. Required production deployment metadata is present.
3. The registration request satisfies endpoint validation.

This separates business authorization from registry storage.

A valid endpoint does not automatically imply that its owner is authorized to register it in a production environment.

### 13.3 Concurrent Registry

The implementation uses `ConcurrentHashMap` for shared service data.

`putIfAbsent` prevents duplicate instance identifiers during registration.

Concurrent collections simplify access to shared registry state, but they do not automatically make multi-step operations fully atomic.

For a production registry, registration and deregistration should use a transaction or coordination mechanism that protects all related indexes and records.

### 13.4 Immutable Data

Service descriptors and registration requests are represented by records.

Metadata is copied into an immutable map.

This reduces accidental modification of registration attributes after the request has been accepted.

Mutable operational fields, such as health and heartbeat timestamps, remain encapsulated inside the service instance.

## 14. PostgreSQL Implementation

The PostgreSQL implementation models a persistent service registry using normalized relational tables.

### 14.1 Relational Structure

The database relationship is:

Service Owners
    |
    v
Services
    |
    v
Service Versions
    |
    v
Service Instances
    |
    +---- Instance Metadata
    |
    +---- Health Counters
    |
    +---- Health Checks
    |
    +---- Circuit Breakers
    |
    +---- Registration Audit

Health policies belong to services and define their health-evaluation thresholds.

### 14.2 Table Responsibilities

| Table | Purpose |
|---|---|
| `service_owners` | Stores service ownership and authorization |
| `services` | Stores logical service definitions |
| `service_versions` | Stores version and environment combinations |
| `service_instances` | Stores endpoint and lifecycle information |
| `instance_metadata` | Stores discovery attributes |
| `health_policies` | Stores health thresholds |
| `health_checks` | Stores individual monitoring results |
| `health_counters` | Stores consecutive health results |
| `circuit_breakers` | Stores endpoint failure-protection state |
| `registration_requests` | Records registration decisions |
| `registration_audit` | Stores operational events |

### 14.3 Constraints and Referential Integrity

Primary keys identify records.

Foreign keys preserve relationships between service owners, services, versions, and instances.

Unique constraints prevent duplicate service definitions, version-environment combinations, and endpoint registrations.

Check constraints validate ports, weights, lease durations, and lifecycle timestamp consistency.

These constraints enforce data integrity independently of the application code.

### 14.4 Health Processing Function

The `process_health_check` function:

1. Identifies the service associated with the instance.
2. Retrieves its health policy.
3. Locks the health counters.
4. Reads the current health state.
5. Evaluates the new check result.
6. Updates consecutive success or failure counters.
7. Updates the instance health state.
8. Records the check result.

The row-level lock prevents concurrent health workers from independently updating the same counters without serialization.

### 14.5 Discovery Function

The `discover_service` function returns instances matching the requested service.

It evaluates:

- Service name
- Version
- Region
- Registration state
- Health state
- Lease validity
- Metadata requirements

The function uses relational joins and indexed lookup conditions.

The query excludes instances that have expired leases even when their last recorded health state remains HEALTHY.

### 14.6 Triggers and Audit

The `trg_instance_state_audit` trigger records changes to instance health and registration state.

Audit information supports operational investigation.

The audit mechanism records state changes rather than attempting to infer every external network event.

### 14.7 Performance Design

Indexes support:

- Service-version lookup
- Region filtering
- Heartbeat expiration
- Health-history retrieval
- Metadata matching
- Pending registration retrieval
- Discoverable endpoint selection

The partial index on active, healthy instances reduces the indexed population for common discovery operations.

For large deployments, health-check history can be partitioned by time.

Registry reads can also be served from a cache when the application can tolerate bounded staleness.

## 15. Registration, Discovery, and Health: Important Distinctions

These mechanisms work together but represent different operational responsibilities.

| Mechanism | Primary question |
|---|---|
| Registration | Has the instance announced its identity and endpoint? |
| Discovery | Which instances satisfy the consumer's requirements? |
| Health check | Can the instance currently provide its service? |
| Heartbeat | Is the instance still communicating with the registry? |
| Lease | Is the last heartbeat still valid? |
| Load balancing | Which eligible instance should receive the request? |
| Circuit breaker | Should requests to a failing endpoint be temporarily blocked? |
| Draining | Should new requests stop reaching this instance? |
| Deregistration | Should the instance be removed from the active registry? |

A correct discovery decision must consider these mechanisms without treating them as interchangeable.

## 16. End-to-End Operational Workflow

Consider a payment-processing application with two service instances.

Initial deployment:

| Instance | Endpoint | Version | Initial state |
|---|---|---|---|
| pay-001 | 10.0.1.10:8001 | 2.1.0 | UNKNOWN |
| pay-002 | 10.0.1.11:8001 | 2.1.0 | UNKNOWN |

Operational sequence:

1. Both instances register with the registry.
2. Registration validation confirms their identity and endpoints.
3. Both instances begin sending heartbeats.
4. Health monitors perform readiness checks.
5. Each instance passes the required consecutive checks.
6. Both instances become HEALTHY.
7. A consumer requests payment-service version 2.1.0.
8. Discovery returns both instances.
9. The consumer selects an endpoint.
10. A network failure occurs on pay-001.
11. Health monitoring records repeated failures.
12. pay-001 becomes UNHEALTHY.
13. Discovery excludes pay-001.
14. Requests are routed to pay-002.
15. pay-001 is restarted and recovers.
16. Successful health checks restore its HEALTHY state.
17. Both instances become discoverable again.

If pay-002 must be removed during a deployment, it enters DRAINING before deregistration.

This workflow reduces unnecessary service interruption during instance replacement.

## 17. Security and Reliability Considerations

### 17.1 Registry Access Control

Registration and modification operations should require authenticated identities.

Authorization should restrict which service owners can register instances under particular service names and deployment environments.

Read permissions should be separated from administrative permissions.

### 17.2 Endpoint Validation

Registry inputs should be validated before they are stored or used.

Host addresses, ports, service names, metadata, and versions must follow defined validation rules.

A registry should not blindly connect to arbitrary addresses supplied by untrusted registration requests.

Network-level restrictions are important to prevent unauthorized internal endpoint access.

### 17.3 Authentication and Transport Security

Production registry communication should use authenticated transport.

TLS protects data in transit.

Mutual TLS can provide service identity verification between registry clients and registry infrastructure.

Credentials and private keys should not be stored in ordinary service metadata.

### 17.4 Health Check Abuse

Health endpoints should expose only the operational information required by authorized monitoring systems.

They should not reveal secrets, internal configuration, credentials, or sensitive application data.

Monitoring traffic should have rate limits and bounded timeouts.

### 17.5 Registry Availability

The registry can become a critical dependency if every service request requires a fresh discovery lookup.

Caching, redundant registry nodes, health-aware failover, and controlled stale-data policies can reduce this dependency.

A distributed registry must also define how concurrent registration changes are coordinated.

### 17.6 Stale Discovery Results

A discovery response represents a snapshot of registry state.

An instance can fail immediately after being returned to a consumer.

Consumers should therefore implement:

- Connection timeouts
- Bounded retries
- Retry backoff
- Endpoint exclusion after repeated failures
- Circuit-breaker policies
- Idempotency for retried operations

Retries must not automatically repeat non-idempotent business operations.

## 18. Performance and Scalability

Registry performance depends on the number of services, instances, health checks, metadata filters, and consumers.

Important considerations include:

- Indexing service identity and instance state
- Avoiding unrestricted health-probe concurrency
- Limiting metadata complexity
- Expiring stale registrations
- Using bounded discovery caches
- Retaining health history according to operational requirements
- Avoiding full-registry scans for frequent lookups
- Separating health-check processing from request routing

For a large deployment, discovery should primarily operate on instances belonging to the requested service rather than scanning every registered endpoint.

The in-memory implementations use service indexes to reduce unnecessary scans.

The PostgreSQL implementation uses relational indexes and partial indexes for common discovery conditions.

## 19. Limitations of the Implementations

The implementations are educational service-registry models rather than complete distributed infrastructure products.

| Area | Current implementation | Production requirement |
|---|---|---|
| Registration | Local registry operations | Distributed registration coordination |
| Discovery | In-memory or SQL filtering | Highly available discovery infrastructure |
| Health monitoring | Simulated or externally supplied results | Real network probes and readiness checks |
| Heartbeats | Local timestamps | Coordinated lease management |
| Load balancing | Round-robin and weighted selection | Traffic-aware routing |
| Circuit breakers | Basic failure thresholds | Controlled half-open recovery |
| Persistence | JSON snapshot or PostgreSQL | Replication, backup, and recovery |
| Security | Input validation and authorization examples | Authentication, authorization, TLS, and network policies |
| Observability | Logs and audit records | Metrics, tracing, alerting, and retention |
| Consistency | Local registry state | Explicit distributed consistency guarantees |

The PostgreSQL database provides persistent state and transactional integrity, but a relational database alone does not solve distributed registry coordination.

The implementations also do not include real HTTP service communication, DNS-based discovery, container orchestration integration, or distributed consensus.

These limitations are important when translating the models into production infrastructure.

## 20. Execution and Compilation

### Python

File: `service_discovery.py`

Runtime: Python 3.10+

Command: `python service_discovery.py`

Uses only the Python standard library.

### JavaScript

File: `service-discovery.js`

Runtime: Node.js 18+

Command: `node service-discovery.js`

Uses only Node.js built-in modules.

The program writes a registry snapshot to `service-registry.json`.

### C++17

File: `service_discovery.cpp`

Compile:

`g++ -std=c++17 -O2 -Wall -Wextra -pedantic service_discovery.cpp -o service_discovery`

Run:

`./service_discovery`

### Java 17

File: `ServiceDiscoveryEnterprise.java`

Compile:

`javac ServiceDiscoveryEnterprise.java`

Run:

`java ServiceDiscoveryEnterprise`

Uses Java 17 standard-library features without third-party dependencies.

### PostgreSQL

File: `service_discovery.sql`

Execution:

`psql -v ON_ERROR_STOP=1 -d your_database -f service_discovery.sql`

The script recreates the `service_discovery` schema, defines the relational model, creates functions and triggers, inserts sample data, and executes operational queries.

The database account requires permission to create schemas, tables, functions, triggers, and indexes.

## 21. Technical Coverage Matrix

| Capability | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Registration | Yes | Yes | Yes | Yes | Yes |
| Deregistration | Yes | Yes | Yes | Yes | Yes |
| Health transitions | Yes | Yes | Yes | Yes | Yes |
| Heartbeats | Yes | Yes | Yes | Yes | Yes |
| Lease expiration | Yes | Yes | Yes | Yes | Yes |
| Metadata filtering | Yes | Yes | Yes | Yes | Yes |
| Version filtering | Yes | Yes | Yes | Yes | Yes |
| Round-robin | Yes | No | Yes | Yes | No |
| Weighted routing | No | Yes | Yes | Yes | No |
| Circuit breaker | No | Yes | Yes | Yes | Yes |
| Asynchronous health probes | No | Yes | No | No | No |
| Event-driven operations | Logging | Yes | No | Audit | Triggers |
| Registration authorization | No | No | No | Yes | Yes |
| Persistent storage | JSON | JSON | No | No | Yes |
| Concurrent data structures | Lock | Event loop | No | Yes | Transactions |

The implementations emphasize different engineering approaches while maintaining a common service-discovery domain model.
