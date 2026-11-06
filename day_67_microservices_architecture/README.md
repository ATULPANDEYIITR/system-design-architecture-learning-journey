# Microservices Architecture: Service Boundaries and Independent Deployment

## 1. Architecture Fundamentals

Microservices architecture organizes an application as a collection of independently deployable services. Each service implements a defined business capability and communicates with other services through explicit interfaces.

A microservice should have:

- A clearly defined business responsibility.
- An independently maintainable codebase.
- An explicit API or event contract.
- Its own deployment lifecycle.
- Defined ownership and operational monitoring.
- Controlled dependencies on other services.
- Appropriate data ownership.

The central design principle is **independent change**. A modification to payment processing should not automatically require rebuilding and deploying order management, inventory management, and customer notifications.

### Example business architecture

    Customer Application
           |
           v
      API Gateway
           |
     +-----+----------------+
     |          |           |
     v          v           v
    Order    Payment    Inventory
    Service  Service    Service
     |
     +----------+
                |
                v
         Event Broker
                |
                v
        Notification Service

Each service implements a separate business capability. The gateway provides an external entry point, while internal communication uses APIs or asynchronous events.

## 2. Service Boundaries

A service boundary determines which business responsibilities belong to a particular service.

Poor boundaries create tightly coupled services. Good boundaries establish clear ownership and minimize unnecessary dependencies.

### Business capability boundaries

| Service | Primary responsibility | Example operations |
|---|---|---|
| Order Service | Order lifecycle | Create, update and cancel orders |
| Payment Service | Payment processing | Authorize, capture and refund |
| Inventory Service | Stock management | Check availability and reserve stock |
| Notification Service | Customer communication | Send order and payment notifications |

Each service should own its internal business rules.

For example, the Order Service requests payment authorization but does not implement payment processing internally. The Payment Service owns authorization, transaction processing, and payment-specific validation.

### High cohesion and low coupling

**High cohesion** means that a service contains functionality related to one business capability.

**Low coupling** means that services require limited knowledge of one another's internal implementation.

A useful design distinction is:

- A service may depend on another service's public contract.
- A service should not depend directly on another service's private classes, database tables, or internal deployment structure.

### Service boundary design decisions

| Design concern | Appropriate approach |
|---|---|
| Business ownership | Assign one primary capability to each service |
| Data ownership | Keep service-specific data under its owner's control |
| Communication | Use APIs or asynchronous events |
| Internal changes | Avoid exposing implementation details |
| Dependencies | Keep the dependency graph manageable |
| Scaling | Scale services according to their workloads |
| Failure handling | Isolate failures across service boundaries |

### Database ownership

A service should normally control its own persistent data.

    Order Service
        |
        v
    Order Database

    Payment Service
        |
        v
    Payment Database

    Inventory Service
        |
        v
    Inventory Database

This model prevents one service from modifying another service's private database tables.

Separate databases do not necessarily require separate database servers. Logical database separation can be implemented on shared infrastructure, provided access controls and ownership boundaries remain enforced.

Cross-service queries should use APIs, events, or dedicated read models rather than unrestricted direct database access.

## 3. Independent Deployment

Independent deployment allows a service to be released without requiring every other service to be redeployed.

For example, Payment Service version `1.0.0` can be upgraded to `1.1.0` while Order Service remains at `1.0.0`.

### Deployment lifecycle

    Source Changes
          |
          v
    Build Artifact
          |
          v
    Automated Tests
          |
          v
    Contract Validation
          |
          v
    Deploy New Version
          |
          v
    Health Verification
          |
       +--+--+
       |     |
      Pass  Fail
       |     |
       v     v
    Activate  Rollback
    Version   Previous
       |
       v
    Monitor Service

A deployment changes the running implementation of a service. It does not automatically change the implementations of its consumers.

### Deployment responsibilities

| Stage | Responsibility |
|---|---|
| Build | Produce a versioned deployment artifact |
| Testing | Validate application behavior |
| Contract validation | Verify compatibility with consumers |
| Deployment | Release the selected service |
| Health verification | Validate readiness and operational health |
| Rollback | Restore a known working artifact |
| Monitoring | Observe latency, errors and availability |

### Versioning

Semantic versioning uses three numeric components:

`MAJOR.MINOR.PATCH`

| Component | Meaning |
|---|---|
| MAJOR | Breaking contract changes |
| MINOR | Backward-compatible functionality |
| PATCH | Backward-compatible corrections |

Example:

- `1.0.0`: Initial service release.
- `1.1.0`: Adds a payment-status endpoint.
- `1.1.1`: Corrects a payment calculation defect.
- `2.0.0`: Introduces a breaking API contract.

A semantic version increase alone does not prove compatibility. Actual contract changes must be evaluated.

## 4. Service Contracts and Compatibility

A service contract defines how other services interact with a provider.

It can include:

- Endpoint paths.
- HTTP methods.
- Request and response structures.
- Authentication requirements.
- Error formats.
- API versions.
- Event schemas.
- Timeout expectations.

### Backward-compatible changes

Examples include:

- Adding an optional response field.
- Adding a new independent endpoint.
- Adding an optional request parameter with a safe default.

Existing consumers can continue using the previous functionality.

### Breaking changes

Examples include:

- Removing an endpoint.
- Renaming a required field.
- Changing the meaning of an existing field.
- Making an optional parameter mandatory.
- Changing an established response structure incompatibly.

A breaking change should normally use a new major API version.

### Expand-and-contract migration

A safer migration approach avoids immediately removing an interface used by existing consumers.

    Phase 1: Add the new contract
             |
             v
    Phase 2: Support old and new contracts
             |
             v
    Phase 3: Migrate existing consumers
             |
             v
    Phase 4: Verify old contract is unused
             |
             v
    Phase 5: Remove old contract

This approach supports independent deployments because providers and consumers do not need to change simultaneously.

## 5. Synchronous Communication

Synchronous communication occurs when one service requests another service to perform an operation and waits for a response.

Example:

    Order Service
         |
         | POST /payments
         v
    Payment Service
         |
         | Authorization Result
         v
    Order Service

HTTP-based REST APIs are a common implementation.

### Advantages

- Immediate responses.
- Straightforward request-response behavior.
- Simple integration for operations requiring immediate results.
- Explicit request and response contracts.

### Limitations

- Network latency affects request duration.
- Provider unavailability affects consumers.
- Long dependency chains increase response time.
- Excessive synchronous dependencies reduce availability.

### Timeout and resilience controls

| Mechanism | Purpose |
|---|---|
| Timeout | Limits how long a consumer waits |
| Retry | Repeats an operation after a transient failure |
| Circuit breaker | Temporarily blocks calls to an unhealthy provider |
| Bulkhead | Isolates resource consumption |
| Rate limiting | Controls request volume |
| Idempotency key | Prevents duplicate business operations |

Retries must be designed carefully. A payment request may have succeeded even when the response was lost. Retrying without an idempotency mechanism can result in duplicate charges.

## 6. Asynchronous Communication

Asynchronous communication allows services to exchange events without requiring the receiving service to respond immediately.

Example:

    Order Service
         |
         | order.created
         v
      Event Broker
         |
         +------------------+
         |                  |
         v                  v
    Inventory Service   Notification Service

The Order Service publishes an event. Inventory and Notification services process it independently.

### Commands and events

| Concept | Meaning | Example |
|---|---|---|
| Command | Requests an action | ReserveInventory |
| Event | Describes something that happened | OrderCreated |
| Query | Requests information | GetOrderStatus |

Events should describe completed business facts rather than expose internal implementation details.

### Event envelope

The implementations use an event structure containing:

- Event identifier.
- Event type.
- Source service.
- Payload.
- Timestamp.

A unique event identifier supports duplicate detection.

### Idempotency

An idempotent consumer produces the same business result when processing the same event more than once.

This matters because message brokers can deliver events repeatedly.

A production consumer should track processing independently for each event and consumer. A single global processed-event flag is insufficient when multiple subscribers exist.

### Transactional outbox

The transactional outbox pattern solves a consistency problem between database updates and event publication.

Without an outbox:

1. A service commits a database transaction.
2. It attempts to publish an event.
3. The message broker becomes unavailable.
4. The business transaction succeeds, but the event is lost.

With an outbox:

1. The business update and event record are written in one database transaction.
2. A background publisher reads pending records.
3. The publisher sends events to the broker.
4. The record is marked published.
5. Failed deliveries are retried.

This provides durable event publication when combined with appropriate delivery and idempotency controls.

## 7. Dependency Management

Services form a directed dependency graph.

For example:

    Order Service
       |       |
       v       v
    Payment  Inventory
       |
       v
    External Payment Provider

A dependency graph helps identify:

- Deployment ordering.
- Critical service relationships.
- Circular dependencies.
- Failure propagation risks.
- Services affected by contract changes.

### Directed acyclic graph

A dependency graph should avoid circular dependencies.

For example:

    Order -> Payment -> Order

This creates a circular dependency and makes deployment and runtime behavior difficult to manage.

The Python, C++ and Java implementations use graph traversal to identify circular dependencies and determine a dependency-respecting deployment order.

The traversal uses:

- A visited set.
- An active recursion set.
- A result list.

Its time complexity is approximately:

\[
O(V+E)
\]

Where:

- \(V\) represents the number of services.
- \(E\) represents the number of dependency relationships.

A dependency order indicates logical prerequisites. It does not mean that every service must be redeployed whenever one dependency changes.

## 8. Service Discovery and Health Management

Service discovery identifies available instances of a service.

Instead of permanently storing a specific machine address, consumers resolve the service through a registry or discovery mechanism.

Example:

    order-service
          |
          v
    Service Discovery
          |
          +----------------+
          |                |
          v                v
    payment-instance-1  payment-instance-2

The implementations model:

- Service registration.
- Service names.
- Instance counts.
- Deployment versions.
- Service status.
- Dependency relationships.
- Health information.

### Health checks

| Check | Purpose |
|---|---|
| Liveness | Determines whether a process is running |
| Readiness | Determines whether an instance can accept traffic |
| Startup | Determines whether initialization has completed |

An instance that is running is not necessarily ready to receive production requests.

A health check should verify the conditions relevant to the service without creating excessive dependency checks or expensive operations.

## 9. Failure Isolation and Resilience

Distributed systems experience partial failures. One service can become unavailable while others remain operational.

For example:

- Payment Service becomes unavailable.
- Order Service cannot complete immediate payment authorization.
- Notification Service remains operational.
- Inventory Service can continue processing independent requests.

A resilient architecture avoids turning one failure into a system-wide outage.

### Circuit breaker states

    CLOSED
       |
       | Failure threshold reached
       v
     OPEN
       |
       | Recovery timeout
       v
    HALF-OPEN
       |
       +---------+
       |         |
     Success   Failure
       |         |
       v         v
     CLOSED    OPEN

The JavaScript implementation includes a circuit breaker with configurable failure thresholds and recovery timeout.

The other implementations demonstrate deployment rollback, health validation and dependency checks.

Production systems should also consider:

- Retry limits.
- Exponential backoff.
- Jitter.
- Request deadlines.
- Resource isolation.
- Dead-letter queues.
- Graceful degradation.
- Operational alerting.

## 10. Implementation Architecture

The five source files provide different engineering perspectives on the same subject.

| File | Primary implementation |
|---|---|
| Python | Service registry, contract validation, deployment simulation and event handling |
| JavaScript | Asynchronous deployment orchestration, event broker and circuit breaker |
| C++17 | Domain modeling, dependency graph traversal and deployment validation |
| Java 17 | Enterprise service registry, policy interfaces, immutable records and deployment services |
| PostgreSQL | Relational service registry, dependency relationships, artifacts, deployment transactions and event outbox |

### Python implementation

The Python program uses:

- Dataclasses for service and deployment records.
- Enums for lifecycle states.
- Dictionaries and sets for registry management.
- Topological sorting for dependency analysis.
- Contract validation for version changes.
- Deployment history for release tracking.
- An event bus for communication simulation.

The deployment manager retains the current contract if the health check fails.

The demonstration includes successful deployment, failed deployment, rollback, duplicate event handling and dependency validation.

### JavaScript implementation

The JavaScript program uses asynchronous capabilities to model distributed operations.

Important mechanisms include:

- `Map` for service and consumer registries.
- `Set` for dependency and idempotency tracking.
- `EventEmitter` for lifecycle notifications.
- Promises for health-check execution.
- `Promise.allSettled()` for independent event consumers.
- Private class fields for encapsulation.
- `structuredClone()` for payload isolation.

The circuit breaker models failure containment at the consumer boundary.

The event broker tracks delivery separately for each consumer.

### C++17 implementation

The C++ program emphasizes explicit domain structures and predictable state management.

It uses:

- Structs for service contracts and deployment records.
- Enums for lifecycle states.
- STL maps for deterministic registry storage.
- Sets for graph traversal.
- Algorithms for set differences and lookup.
- Exceptions for validation and failure handling.
- Function objects for event consumers.

The implementation demonstrates how graph-based validation can be performed without third-party dependencies.

The rollback demonstration deliberately distinguishes version metadata from deployable artifacts. Restoring a version number alone is not sufficient for a real production rollback.

### Java 17 implementation

The Java program provides an enterprise-oriented model.

Its design includes:

- Records for contracts, dependencies, events and deployment records.
- Interfaces for health checks and deployment policies.
- Immutable dependency and contract collections.
- Custom exception classes.
- Concurrent collections for registry access.
- Atomic counters for deployment statistics.
- Separate services for registration and deployment.
- Artifact-based rollback.

The `DeploymentPolicy` interface separates compatibility decisions from deployment execution.

This allows additional policies to be implemented without rewriting the deployment service.

### PostgreSQL implementation

The database implementation models the lifecycle of service registration and deployment.

Its principal entities are:

| Table | Responsibility |
|---|---|
| `services` | Service identity and ownership |
| `service_contracts` | Versioned API contracts |
| `service_endpoints` | Contract endpoint definitions |
| `service_dependencies` | Provider-consumer relationships |
| `environments` | Deployment environments |
| `deployment_artifacts` | Versioned deployment artifacts |
| `deployments` | Deployment history |
| `service_instances` | Runtime service instances |
| `health_checks` | Health observations |
| `event_outbox` | Durable outgoing events |
| `event_consumers` | Individual event delivery records |

The database uses foreign keys, unique constraints, checks, indexes, recursive CTEs, functions, procedures, views and triggers.

The `prevent_dependency_cycle()` trigger prevents the insertion of dependency edges that create circular relationships.

The `validate_deployment()` function checks artifact ownership, build verification and API compatibility.

The `deploy_service()` procedure records a deployment and changes the active contract only after successful health verification.

The event outbox and consumer tables represent durable asynchronous communication.

## 11. PostgreSQL Transaction and Deployment Semantics

The deployment procedure uses a transaction to protect service state.

Its workflow is:

1. Lock the service record using `FOR UPDATE`.
2. Retrieve and validate the deployment artifact.
3. Verify the associated contract.
4. Record the deployment attempt.
5. Evaluate the health-check result.
6. Activate the new contract on success.
7. Preserve the previous active version on failure.
8. Record the final deployment state.

The row lock serializes concurrent deployment attempts for the same service record.

The procedure does not independently perform an actual infrastructure deployment. The health-check result is supplied by the external deployment process.

Production deployment systems must coordinate the database record with the actual runtime release and account for failures between infrastructure operations and database commits.

## 12. Service Boundary and Deployment Security

Independent deployment increases operational flexibility but also introduces security responsibilities.

### Identity and authentication

Each service should have an identifiable workload identity.

Requests should be authenticated and authorized at service boundaries.

### Authorization

Use least-privilege permissions.

A service should access only the resources required for its business capability.

### Network security

- Encrypt service-to-service communication.
- Restrict unnecessary network access.
- Validate incoming requests.
- Apply rate limits.
- Avoid exposing internal management endpoints publicly.

### Secrets management

Credentials, database passwords and API tokens should not be embedded in source code or deployment artifacts.

### Supply-chain security

Deployment artifacts should be:

- Built through controlled pipelines.
- Identified by immutable digests.
- Verified before deployment.
- Associated with source revisions.
- Restricted to authorized deployment identities.

The PostgreSQL implementation stores artifact digests and source commit identifiers to establish deployment traceability.

## 13. Performance Considerations

Microservices introduce network and operational overhead that does not exist in a single-process application.

| Concern | Performance consideration |
|---|---|
| Network calls | Reduce unnecessary synchronous requests |
| Service discovery | Cache valid discovery information |
| Event processing | Use batching and controlled concurrency |
| Database access | Index frequent lookup and relationship columns |
| Deployment | Use health checks and staged rollout |
| Dependency graphs | Use adjacency structures for larger graphs |
| Logging | Use structured, correlated logs |
| Scaling | Scale according to service-specific workload |

The PostgreSQL indexes support common operational queries:

- Service dependency lookup.
- Deployment history retrieval.
- Health-check history.
- Pending event retrieval.
- Consumer event processing.

The graph implementations use sets and maps to avoid repeatedly scanning unrelated service relationships.

## 14. Edge Cases and Operational Limitations

| Scenario | Required behavior |
|---|---|
| Duplicate service registration | Reject registration |
| Missing required dependency | Reject dependency validation |
| Circular dependency | Reject the dependency graph |
| Breaking API change | Require a compatible migration strategy |
| Failed health check | Preserve the previous active contract |
| Duplicate event | Avoid duplicate business processing |
| Provider unavailable | Apply timeout and resilience controls |
| Missing deployment artifact | Reject rollback |
| Stale instance | Remove it from eligible routing |
| Concurrent deployments | Serialize conflicting updates |
| Event publication failure | Retain and retry the outbox record |
| Partial rollout | Monitor instance versions and health separately |

The implementations are educational domain simulations rather than complete production orchestration platforms.

In particular:

- The Python and C++ event brokers are in-memory demonstrations.
- The JavaScript event broker does not provide durable message storage.
- The Java event dispatcher requires stronger per-consumer delivery tracking for production use.
- The PostgreSQL procedure models deployment metadata and contract activation, not container or infrastructure operations.
- Actual distributed transactions are not implemented across service databases.
- Service discovery and API gateway routing are represented conceptually rather than implemented as network servers.

These distinctions matter because independent deployment requires coordination between application contracts, deployment infrastructure, runtime health, security controls and operational monitoring.

## 15. Architectural Trade-offs

| Dimension | Modular monolith | Microservices |
|---|---|---|
| Deployment | Usually application-wide | Per-service |
| Runtime | Often one application process | Multiple independently running services |
| Communication | Internal function calls | APIs and messaging |
| Data ownership | Often shared database | Service-owned data |
| Scaling | Application or module-level | Service-specific |
| Operational complexity | Lower | Higher |
| Failure isolation | Primarily process-level | Service and network boundaries |
| Testing | Simpler integration environment | Distributed contract and integration testing |
| Consistency | Easier local transactions | Distributed consistency mechanisms |
| Team ownership | Shared or modular teams | Often capability-oriented teams |

Microservices are most useful when service boundaries represent meaningful business capabilities and independent development, deployment or scaling provides measurable operational value.

Creating many small services without clear ownership increases network dependencies, deployment coordination, observability requirements and failure-handling complexity.
