# Architecture Trade-offs: Cost, Complexity, Performance, and Reliability

## 1. Architecture Decision Problem

Software architecture determines how an application is divided into components, how those components communicate, where they execute, and how they are deployed, maintained, and recovered.

Architecture selection is a multi-dimensional engineering decision. An architecture that performs well under heavy workloads may require greater infrastructure expenditure and operational expertise. A simpler design may reduce development and maintenance costs but introduce constraints on independent scaling and deployment.

This project implements an architecture evaluation system across five technical perspectives:

| Implementation | Engineering focus |
|---|---|
| Python | Architecture simulation, weighted evaluation, reliability analysis, and JSON reporting |
| JavaScript | Event-driven evaluation, workload modeling, policy enforcement, and Pareto analysis |
| C++17 | Efficient domain modeling, governance constraints, dependency validation, and eligibility evaluation |
| Java 17 | Enterprise architecture policies, immutable domain objects, evaluation services, and decision auditing |
| PostgreSQL | Relational architecture registry, cost and performance records, evaluation procedures, and reporting |

The evaluation considers five principal dimensions:

1. Cost
2. Complexity
3. Performance
4. Reliability
5. Scalability

The purpose is not to identify one universally superior architecture. It is to establish a repeatable method for evaluating alternatives against explicit business and engineering requirements.

## 2. Architecture Models

### 2.1 Monolithic Architecture

A monolithic application is deployed as one application unit. Its components may have internal separation, but deployment and runtime execution share a common application boundary.

Characteristics:

- Centralized application execution.
- Shared deployment lifecycle.
- Direct function or module communication.
- Relatively straightforward local debugging.
- Potentially simpler infrastructure management.
- Shared scaling and failure boundaries.

Advantages:

- Lower initial infrastructure complexity.
- Straightforward transactional operations.
- Easier development and deployment for small teams.
- Reduced distributed communication overhead.

Trade-offs:

- Independent component scaling is difficult.
- A faulty component may affect the entire application.
- Large codebases can develop tightly coupled modules.
- Deployment changes may affect unrelated functionality.

A monolith is not inherently unreliable or poorly scalable. Its suitability depends on workload, internal modularity, deployment practices, and available infrastructure.

### 2.2 Modular Monolith

A modular monolith maintains explicit internal boundaries while retaining a single deployment unit.

Typical modules include:

- Authentication
- Orders
- Inventory
- Payments
- Reporting

Modules communicate through defined interfaces rather than unrestricted access to internal implementation details.

Its principal benefit is separation of development responsibilities without introducing distributed-system communication.

The Python, C++, and Java examples use a modular monolith as a comparatively inexpensive architecture with moderate complexity.

Important limitations include shared runtime resources and the inability to independently deploy or scale individual modules.

### 2.3 Microservices Architecture

Microservices divide an application into independently deployable services.

Each service owns a defined business capability and communicates through APIs, messaging systems, or other network protocols.

Characteristics:

- Independent deployment.
- Service-level scaling.
- Explicit service ownership.
- Distributed monitoring.
- Network communication.
- Independent failure and recovery boundaries.

Advantages:

- Independent scaling of high-demand services.
- Smaller deployment units.
- Better organizational separation.
- Independent technology choices where justified.
- Potentially improved fault isolation.

Trade-offs:

- Network latency and communication failures.
- Distributed tracing requirements.
- Service discovery and configuration management.
- More complex security boundaries.
- Data consistency challenges.
- Greater infrastructure and operational expenditure.

A microservices design is useful when independent deployment and scaling provide sufficient value to justify its distributed-system costs.

### 2.4 Serverless Architecture

Serverless computing uses managed execution environments and event-triggered workloads.

Infrastructure provisioning, execution capacity, and parts of the scaling process are handled by the cloud provider.

Characteristics:

- Managed execution.
- Event-triggered processing.
- Elastic resource allocation.
- Usage-based billing.
- Reduced server administration.

Advantages:

- Limited infrastructure administration.
- Automatic scaling for supported workloads.
- Cost efficiency for intermittent workloads.
- Convenient integration with managed services.

Trade-offs:

- Cold-start latency.
- Execution duration and resource limits.
- Provider-specific service dependencies.
- Distributed observability requirements.
- Potentially unpredictable expenditure under high request volumes.

Serverless is not automatically the least expensive choice. Cost depends on execution frequency, duration, memory allocation, network usage, and managed-service charges.

### 2.5 Event-Driven Architecture

Event-driven systems communicate through events representing facts about business or system activity.

For example:

`OrderCreated → PaymentRequested → PaymentCompleted → InventoryReserved`

Producers publish events, and consumers process them independently.

Characteristics:

- Asynchronous communication.
- Event-based integration.
- Independent consumer execution.
- Potentially loose coupling.
- Eventual consistency.

Advantages:

- Independent event processing.
- High-throughput asynchronous workloads.
- Reduced direct dependency between producers and consumers.
- Better support for background processing.

Trade-offs:

- Duplicate message delivery.
- Event ordering challenges.
- Event schema evolution.
- Delayed consistency.
- Dead-letter queue management.
- More complicated end-to-end debugging.

Event-driven architecture is a communication and processing model. It can be implemented within a monolith, across microservices, or through managed serverless components.

It should not automatically be treated as a separate deployment architecture.

### 2.6 Hybrid Architecture

Hybrid architecture combines architectural approaches according to workload and business requirements.

For example:

- A modular monolith manages core transactions.
- Serverless functions process scheduled tasks.
- An event broker handles asynchronous integration.
- Selected high-demand capabilities operate as independent services.

A hybrid design can preserve simplicity in stable business domains while introducing distributed components only where they offer measurable benefits.

Its main challenge is maintaining clear ownership and consistent operational practices across different execution models.

## 3. The Five Architecture Evaluation Dimensions

### 3.1 Cost

Architecture cost includes more than infrastructure expenditure.

A useful financial model is:

\[
C_{monthly} =
C_{compute} +
C_{storage} +
C_{network} +
C_{platform} +
C_{operations} +
C_{support}
\]

Annual recurring cost is:

\[
C_{annual} = 12 \times C_{monthly}
\]

A more complete lifecycle model includes initial implementation, migration, training, and eventual retirement:

\[
TCO =
C_{development}
+
C_{migration}
+
C_{infrastructure}
+
C_{operations}
+
C_{maintenance}
+
C_{risk}
\]

Where TCO represents total cost of ownership over a defined period.

**Infrastructure cost** includes:

- Compute instances.
- Memory and storage.
- Network transfer.
- Databases.
- Load balancing.
- Message brokers.
- Managed services.

**Operational cost** includes:

- Engineering maintenance.
- Monitoring.
- Incident response.
- Security operations.
- Deployment management.
- On-call responsibilities.
- Platform administration.

The code examples separate infrastructure and operational expenditure.

The PostgreSQL model further separates compute, storage, network, platform, operations, and support costs.

This distinction is important because an architecture with inexpensive infrastructure may still require substantial engineering effort.

#### Cost normalization

The implementations use different normalization approaches.

Python uses relative cost:

\[
S_{cost} =
100\left(1-\frac{C_i}{C_{max}}\right)
\]

JavaScript and Java use a budget-relative scoring function:

\[
S_{cost} =
\frac{100}{1+C_i/B}
\]

Where:

- \(C_i\) is the architecture's monthly cost.
- \(C_{max}\) is the highest evaluated cost.
- \(B\) is the approved monthly budget.

These scoring methods support comparison, but they do not replace a complete financial business case.

### 3.2 Complexity

Complexity affects development speed, maintainability, deployment, debugging, and operational risk.

Relevant dimensions include:

| Complexity dimension | Engineering consideration |
|---|---|
| Code complexity | Internal dependencies and module boundaries |
| Deployment complexity | Number of deployment units and release coordination |
| Operational complexity | Monitoring, incidents, configuration, and recovery |
| Data complexity | Ownership, synchronization, and consistency |
| Security complexity | Authentication and authorization boundaries |
| Organizational complexity | Team responsibilities and coordination |

A monolith may have low infrastructure complexity but high internal code complexity if its modules are tightly coupled.

Microservices may reduce the size of individual codebases while increasing deployment, network, security, and observability complexity.

Complexity should therefore be evaluated across the entire system rather than by counting source files or services.

The implementations use a normalized complexity rating from 1 to 10.

A lower rating represents simpler operational and engineering management.

### 3.3 Performance

Performance measures how effectively an architecture handles its workload.

Important measurements include:

- Average response latency.
- P95 latency.
- P99 latency.
- Requests per second.
- Concurrent users.
- Error rate.
- Resource utilization.
- Network throughput.
- Queue processing delay.

Average latency alone is insufficient.

For example, a system may have an average response time of 100 milliseconds while a significant proportion of requests take considerably longer.

Percentile measurements help identify these tail-latency problems.

#### Throughput

Throughput represents the amount of work processed during a time interval.

\[
Throughput =
\frac{CompletedRequests}{Time}
\]

The workload model uses:

\[
R_{peak} =
R_{average} \times PeakMultiplier
\]

For an average workload of 1,200 requests per second and a peak multiplier of 2:

\[
R_{peak}=2,400
\]

#### Network estimation

Approximate network ingress is:

\[
Ingress_{Mbps} =
\frac{R_{peak}\times Payload_{KB}\times 8}{1024}
\]

This estimates payload ingress only. It does not account for protocol overhead, retries, response payloads, compression, or additional internal network traffic.

#### Latency considerations

Architecture decisions affect latency through:

- Network hops.
- Serialization and deserialization.
- Database access.
- Remote service calls.
- Queue processing.
- Resource contention.
- Cold starts.

A monolith may reduce network overhead through direct internal calls.

Microservices may introduce additional network latency but permit independent capacity allocation.

Event-driven systems may reduce synchronous request latency while increasing the time required for an entire business process to complete.

The distinction between request-response latency and end-to-end workflow completion time is important.

### 3.4 Reliability

Reliability describes the ability of a system to perform its intended functions consistently under expected operating conditions.

Important measurements include:

- Availability.
- Mean Time Between Failures.
- Mean Time To Recovery.
- Failure frequency.
- Recovery objectives.
- Error rate.
- Dependency reliability.

#### Availability

Availability is expressed as:

\[
Availability =
\frac{Uptime}{TotalTime}\times100
\]

Annual downtime can be estimated using:

\[
Downtime_{hours} =
8760 \times
\left(1-\frac{Availability}{100}\right)
\]

| Availability | Approximate annual downtime |
|---|---:|
| 99% | 87.60 hours |
| 99.9% | 8.76 hours |
| 99.95% | 4.38 hours |
| 99.99% | 0.876 hours |
| 99.999% | 0.0876 hours |

These figures assume a 365-day year and represent mathematical availability targets, not guaranteed operational results.

#### Serial dependency reliability

For independent components that must all work for a service to function:

\[
A_{system} =
A_1 \times A_2 \times \cdots \times A_n
\]

For two components with availability of 99%:

\[
A_{system}=0.99\times0.99=98.01\%
\]

This explains why adding dependencies can reduce end-to-end availability.

The formula assumes independent failures and a serial dependency relationship.

Real systems may have correlated failures, retries, caching, failover, redundancy, and partial operation. These require more detailed reliability models.

#### Failure recovery

Recovery considerations include:

- Automated health checks.
- Replication.
- Backup restoration.
- Failover.
- Circuit breakers.
- Retry policies.
- Disaster recovery.
- Rollback procedures.

Mean Time to Recovery is not the same as service availability. Recovery procedures, incident frequency, and system topology must be considered together.

### 3.5 Scalability

Scalability describes the ability to support increasing demand while maintaining acceptable service characteristics.

**Vertical scaling** increases the capacity of an existing machine or instance.

Examples:

- More CPU.
- More memory.
- Faster storage.

**Horizontal scaling** increases the number of execution instances.

Examples:

- Multiple application replicas.
- Independently scaled services.
- Additional event consumers.

| Approach | Main benefit | Main limitation |
|---|---|---|
| Vertical scaling | Simpler capacity expansion | Hardware and instance limits |
| Horizontal scaling | Increased aggregate capacity | Coordination and distributed-state requirements |
| Automatic scaling | Dynamic capacity adjustment | Configuration and scaling delay |
| Partitioning | Distributes workload | Data distribution complexity |

Scalability is not identical to performance.

A system may provide excellent latency at its current workload but have limited ability to scale.

The implementations use a relative scalability rating from 1 to 10. A production assessment should supplement this rating with measured scaling curves and capacity limits.

## 4. Architecture Trade-off Relationships

The five evaluation dimensions interact.

| Decision | Potential benefit | Potential cost |
|---|---|---|
| Introduce microservices | Independent deployment and scaling | Distributed operations |
| Adopt serverless | Reduced infrastructure administration | Provider dependency and execution constraints |
| Introduce asynchronous events | Lower direct coupling | Eventual consistency and observability complexity |
| Add redundancy | Improved failure tolerance | Infrastructure and synchronization costs |
| Use a modular monolith | Clear internal boundaries | Shared deployment lifecycle |
| Introduce caching | Lower database load and latency | Invalidation and consistency challenges |
| Add database replicas | Improved read capacity and availability options | Replication lag and operational overhead |

A design decision should be assessed by its impact on the complete system.

For example, introducing a message broker may improve asynchronous throughput, but it also adds another infrastructure dependency.

The improvement should be measured against the new operational and reliability requirements.

## 5. Weighted Decision Analysis

Weighted decision analysis converts different architecture measurements into a common scoring framework.

The general equation is:

\[
S_{total} =
\sum_{i=1}^{n} w_i S_i
\]

Where:

- \(S_i\) is the normalized score for a criterion.
- \(w_i\) is the criterion's assigned weight.
- The weights sum to 1.

The example decision profile uses:

| Criterion | Weight |
|---|---:|
| Cost | 0.25 |
| Performance | 0.20 |
| Reliability | 0.25 |
| Complexity | 0.15 |
| Scalability | 0.15 |
| **Total** | **1.00** |

These values represent a sample commerce-platform decision policy.

Weights should reflect the business environment.

A financial transaction system may prioritize reliability and security.

A high-volume analytical processing platform may prioritize throughput and scalability.

A small internal application may prioritize implementation cost and maintainability.

### 5.1 Hard constraints versus weighted scores

A high weighted score does not automatically make an architecture suitable for production.

For example, an architecture may score well on cost and scalability but fail a mandatory availability requirement.

The implementations distinguish:

- Weighted ranking.
- Hard policy requirements.
- Final eligibility.

Typical hard requirements include:

- Maximum approved monthly expenditure.
- Minimum throughput.
- Maximum permitted latency.
- Minimum availability.
- Disaster recovery requirements.

An architecture that violates a mandatory requirement is marked ineligible.

This prevents a favorable score in one category from compensating for an unacceptable result in another.

### 5.2 Sensitivity analysis

Decision rankings depend on the selected weights.

Suppose the cost weight increases while reliability weight decreases.

A less expensive architecture may become the highest-ranked alternative.

This does not mean its technical characteristics have improved. Only the evaluation priorities have changed.

A proper sensitivity analysis should:

1. Establish a baseline weight profile.
2. Change one or more weights.
3. Recalculate rankings.
4. Record architectures that change position.
5. Identify decisions that remain stable.
6. Document the business implications.

The Python implementation supports changing `DecisionWeights` without changing architecture definitions.

The same separation exists in the JavaScript and Java policy models.

## 6. Pareto Optimality

Weighted scores produce a single ranking. Pareto analysis identifies alternatives that cannot be improved in one objective without sacrificing at least one other objective.

For this project, four objectives are considered:

- Minimize monthly cost.
- Minimize latency.
- Maximize throughput.
- Maximize availability.

Architecture A dominates architecture B when A is no worse in every objective and strictly better in at least one.

A Pareto-optimal architecture is not dominated by another evaluated architecture.

This is useful when multiple alternatives have different strengths.

For example:

- Architecture A may be less expensive.
- Architecture B may provide higher throughput.
- Architecture C may provide better availability.

All three may remain on the Pareto frontier.

A Pareto frontier does not select the final architecture. It identifies alternatives worth considering before business priorities are applied.

## 7. Python Implementation

The Python script provides a domain-oriented simulation and reporting system.

### 7.1 Main components

| Component | Responsibility |
|---|---|
| `ArchitectureType` | Defines architecture categories |
| `ArchitectureMetrics` | Validates architecture measurements |
| `Architecture` | Represents an architecture alternative |
| `DecisionWeights` | Stores evaluation priorities |
| `ArchitectureDecisionEngine` | Calculates normalized scores |
| `ReliabilityAnalyzer` | Calculates downtime and expected failure loss |
| `FailureScenario` | Represents operational failure conditions |
| `ArchitectureDecisionRecord` | Stores the decision rationale |
| `ArchitectureRepository` | Manages architecture records and reports |

### 7.2 Evaluation workflow

The workflow is:

`Architecture Profiles → Metric Validation → Normalization → Weighted Scoring → Ranking → Reliability Analysis → Decision Record → JSON Report`

The evaluation engine calculates:

- Relative cost score.
- Combined latency and throughput score.
- Availability score.
- Complexity score.
- Scalability score.

It sorts architectures by weighted score.

### 7.3 Reliability analysis

The reliability analyzer includes:

- Annual downtime estimation.
- Expected annual financial loss.
- Serial component availability.

Expected annual financial loss is:

\[
E(L)=\sum_{i=1}^{n}P_i\times I_i
\]

Where:

- \(P_i\) is the annual probability of a failure scenario.
- \(I_i\) is its financial impact.

The calculation assumes the supplied probabilities and impacts are meaningful estimates.

### 7.4 Persistence

The script exports:

`architecture_decision_report.json`

The report contains:

- Architecture profiles.
- Metrics.
- Monthly and annual costs.
- Evaluation results.
- Decision context.
- Alternatives.
- Consequences.

Writing through a temporary file before replacement reduces the risk of leaving a partially written report after an ordinary write failure.

The script uses Python standard-library facilities and does not require third-party packages.

## 8. JavaScript Implementation

The JavaScript implementation emphasizes event-driven execution and policy evaluation.

### 8.1 Architecture registry

`ArchitectureRegistry` uses a `Map` to manage architecture profiles.

It provides:

- Unique architecture identifiers.
- Profile validation.
- Immutable profile snapshots.
- Controlled retrieval.

This separates architecture registration from evaluation logic.

### 8.2 Workload modeling

The `Workload` class represents:

- Average request rate.
- Peak multiplier.
- Payload size.
- Concurrent users.
- Latency target.

It calculates peak request rate and approximate network ingress.

### 8.3 Policy evaluation

`DecisionPolicy` defines hard constraints and scoring weights.

`ArchitectureEvaluator` applies the policy to registered alternatives.

The result includes:

- Monthly and annual cost.
- Effective availability.
- Annual downtime.
- Dimension scores.
- Weighted score.
- Eligibility.
- Violation codes.

### 8.4 Event-driven execution

The evaluator extends `EventEmitter`.

An `evaluated` event is emitted after each architecture evaluation.

This allows other application components to respond without becoming tightly coupled to the evaluation process.

For example, a reporting component can listen for completed evaluations while an audit component records decisions.

### 8.5 Asynchronous evaluation

`evaluateAll()` uses asynchronous workers and a configurable concurrency limit.

The implementation uses `setImmediate()` to yield execution to the event loop between evaluations.

This demonstrates controlled asynchronous processing.

The calculations are CPU-light, so concurrency does not provide a meaningful CPU-parallel speedup. Actual CPU-intensive workloads would require worker threads or separate processes.

### 8.6 Dependency validation

`DependencyAnalyzer` checks dependency graphs for:

- Missing components.
- Circular dependencies.
- Invalid availability values.

Depth-first traversal uses a visited set and an active recursion set.

Its graph validation complexity is:

\[
O(V+E)
\]

Where V is the number of nodes and E is the number of dependency edges.

### 8.7 Pareto analysis

`ParetoAnalyzer` compares architecture profiles across four objectives.

Its direct implementation uses pairwise comparison:

\[
O(n^2)
\]

This is acceptable for a small architecture catalog. Larger catalogs may require specialized multi-objective optimization techniques.

## 9. C++17 Implementation

The C++ implementation focuses on domain modeling and a governance-oriented evaluation engine.

### 9.1 Data structures

| Structure | Purpose |
|---|---|
| `Metrics` | Architecture measurements |
| `Architecture` | Architecture identity and dependencies |
| `Workload` | Traffic and capacity requirements |
| `DecisionWeights` | Evaluation priorities |
| `EvaluationPolicy` | Mandatory constraints |
| `Evaluation` | Evaluation results |

The architecture registry uses `std::map` to provide deterministic identifier-based storage.

### 9.2 Validation

The engine checks:

- Required architecture identifiers.
- Finite numerical values.
- Non-negative costs.
- Availability bounds.
- Complexity bounds.
- Scalability bounds.
- Dependency existence.
- Dependency cycles.
- Valid decision weights.

Invalid domain objects are rejected before evaluation.

### 9.3 Dependency analysis

The engine uses depth-first search with three states:

- Unvisited.
- Visiting.
- Visited.

Encountering a node already in the Visiting state indicates a cycle.

This prevents invalid dependency graphs from entering the evaluation process.

### 9.4 Eligibility engine

The C++ engine distinguishes weighted evaluation from hard policy enforcement.

Its mandatory conditions include:

- Monthly budget.
- Minimum availability.
- Minimum throughput.
- Peak workload capacity.
- Maximum latency.

An architecture that violates any mandatory condition is marked ineligible.

### 9.5 Performance characteristics

| Operation | Expected complexity |
|---|---|
| Architecture insertion | \(O(\log n)\) |
| Identifier lookup | \(O(\log n)\) |
| Dependency validation | \(O(V+E)\) |
| Weighted evaluation | \(O(n)\), excluding dependency traversal |
| Ranking | \(O(n\log n)\) |
| Pareto frontier | \(O(n^2)\) |

The implementation uses standard C++ containers and algorithms without external dependencies.

## 10. Java 17 Implementation

The Java implementation represents an enterprise architecture decision process.

Its design emphasizes immutable domain data, explicit policies, service separation, and decision auditing.

### 10.1 Domain records

Java records represent:

- `ArchitectureMetrics`
- `WorkloadProfile`
- `Architecture`
- `DecisionWeights`
- `GovernancePolicy`
- `Risk`
- `ArchitectureEvaluation`
- `ArchitectureDecision`

Records reduce mutable state and make the structure of domain information explicit.

The architecture dependency set and decision lists are copied into immutable collections.

### 10.2 Evaluation rules

The implementation separates mandatory rules into individual classes:

| Rule | Responsibility |
|---|---|
| `BudgetRule` | Enforces expenditure limits |
| `AvailabilityRule` | Enforces availability requirements |
| `CapacityRule` | Checks workload capacity |
| `LatencyRule` | Enforces response-time requirements |

The `EvaluationRule` interface allows the evaluation service to apply multiple independent policy checks.

This design makes policy changes easier to isolate and test.

### 10.3 Service responsibilities

| Service | Responsibility |
|---|---|
| `ArchitectureCatalog` | Registers and validates architectures |
| `ReliabilityService` | Calculates availability and risk exposure |
| `ArchitectureEvaluationService` | Applies policies and scoring |
| `ParetoService` | Identifies non-dominated alternatives |
| `DecisionAuditService` | Maintains decision history |

This separation prevents the architecture data model from becoming responsible for every business operation.

### 10.4 Enterprise decision auditing

An architecture decision contains:

- Unique decision identifier.
- Decision title.
- Business and technical context.
- Selected architecture.
- Considered alternatives.
- Consequences.
- Decision status.

Decision statuses are:

- Proposed.
- Accepted.
- Rejected.
- Superseded.

A decision record preserves the reasoning behind architecture selection.

The example stores decisions in memory. A production implementation would persist these records in a transactional database and enforce appropriate authorization and audit-retention policies.

## 11. PostgreSQL Implementation

The PostgreSQL implementation provides a relational foundation for architecture evaluation.

### 11.1 Relational model

The principal relationships are:

`Architecture Catalog → Components → Dependencies`

`Architecture Catalog → Cost Profiles`

`Architecture Catalog → Performance Measurements`

`Architecture Catalog → Reliability Profiles`

`Architecture Catalog → Failure Scenarios`

`Decision Profiles → Decision Weights → Decision Criteria`

`Architecture Evaluations → Architecture Decisions`

### 11.2 Core tables

| Table | Purpose |
|---|---|
| `architecture_catalog` | Architecture alternatives |
| `architecture_components` | Internal architecture components |
| `architecture_dependencies` | Relationships between architectures |
| `cost_profiles` | Infrastructure and operational expenditure |
| `workload_profiles` | Expected traffic characteristics |
| `performance_measurements` | Benchmark measurements |
| `reliability_profiles` | Availability and recovery measurements |
| `failure_scenarios` | Operational failure and financial exposure |
| `decision_criteria` | Evaluation dimensions |
| `decision_profiles` | Mandatory policy thresholds |
| `decision_weights` | Criterion importance |
| `architecture_evaluations` | Evaluation results |
| `architecture_decisions` | Recorded architecture decisions |
| `architecture_audit` | Cost profile change history |

Foreign keys enforce valid relationships between architecture records, workloads, profiles, and evaluation results.

Check constraints enforce numerical boundaries and permitted domain values.

### 11.3 Cost aggregation

The `v_architecture_costs` view aggregates the current effective cost profile.

The calculation separates:

- Compute.
- Storage.
- Network.
- Platform.
- Operations.
- Support.

The view derives monthly and annual expenditure.

Its effective-date conditions prevent expired cost records from being included in current cost reporting.

The view assumes that overlapping effective cost profiles are prevented by data-management controls. A production schema should enforce non-overlapping effective-date ranges.

### 11.4 Performance measurements

Performance records include:

- Average latency.
- P95 latency.
- P99 latency.
- Throughput.
- Error rate.
- Sample size.
- Environment.
- Measurement timestamp.

The `v_latest_performance` view retrieves the latest recorded measurement for each architecture and workload.

Benchmark measurements should always be associated with a workload and execution environment. Measurements collected under different workload conditions should not be treated as directly comparable.

### 11.5 Reliability and failure exposure

The `reliability_profiles` table records availability and recovery characteristics.

The `failure_scenarios` table stores:

- Failure category.
- Annual probability.
- Financial impact.
- Recovery duration.
- Mitigation strategy.

The `v_expected_failure_loss` view calculates expected annual financial loss.

These values support risk comparison but do not represent a complete probabilistic reliability model.

### 11.6 Decision weights

The `decision_criteria` table stores the five evaluation dimensions.

The `decision_weights` table associates criteria with individual decision profiles.

The `validate_decision_weights()` function enforces:

- Exactly five criteria.
- Non-negative weights.
- A total weight of 1.

The validation function is called before evaluation.

### 11.7 Evaluation procedure

`evaluate_architectures()` performs the principal database evaluation workflow.

It:

1. Retrieves the decision policy.
2. Retrieves the selected workload.
3. Validates the decision weights.
4. Retrieves the current architecture costs.
5. Retrieves the latest benchmark measurements.
6. Retrieves reliability measurements.
7. Applies hard constraints.
8. Calculates normalized scores.
9. Calculates the weighted score.
10. Persists eligibility and policy violations.

The evaluation procedure uses a transaction so that an unsuccessful execution does not leave a partially committed evaluation.

The sample implementation uses fixed neutral complexity and scalability scores because the SQL sample schema does not yet contain independently measured complexity and scalability fields. These values must not be interpreted as measured architecture characteristics.

A production implementation should introduce validated assessment records for those dimensions.

### 11.8 Triggers and audit records

The cost profile trigger records:

- Entity identity.
- Operation type.
- Previous values.
- New values.
- Database user.
- Timestamp.

This creates an audit trail for cost changes.

The audit table should have controlled access because it may contain commercially sensitive architecture information.

### 11.9 Indexing

The database includes indexes for:

- Architecture and effective cost date.
- Architecture and workload benchmark history.
- Reliability history.
- Failure scenarios.
- Decision profile and evaluation ranking.
- JSONB evaluation violations.
- Decision status and date.

The indexes support the principal retrieval and reporting operations.

Indexes also increase storage requirements and write overhead. Additional indexes should be justified by actual query patterns and execution plans.

## 12. End-to-End Architecture Decision Workflow

The complete workflow is:

`Business Requirements`

`↓`

`Workload Definition`

`↓`

`Architecture Alternatives`

`↓`

`Cost and Operational Assessment`

`↓`

`Performance Benchmarking`

`↓`

`Reliability and Failure Analysis`

`↓`

`Complexity and Scalability Assessment`

`↓`

`Hard Constraint Validation`

`↓`

`Weighted Evaluation`

`↓`

`Pareto Analysis`

`↓`

`Architecture Decision Record`

`↓`

`Production Validation and Monitoring`

Each stage provides evidence for the subsequent decision.

The architecture should not be approved solely because it receives the highest numerical score.

The decision must also account for organizational capabilities, security requirements, regulatory obligations, migration constraints, and the cost of future change.

## 13. Security and Operational Considerations

Architecture decisions influence the system's security boundaries and operational responsibilities.

Important controls include:

- Least-privilege access.
- Strong service authentication.
- Authorization at service boundaries.
- Encryption in transit and at rest.
- Secret management.
- Centralized security logging.
- Dependency vulnerability monitoring.
- Backup protection.
- Recovery testing.
- Change management.
- Resource quotas.
- Cost monitoring.

Distributed architectures increase the number of communication boundaries that must be secured.

Serverless systems introduce provider-specific execution and permission models.

Event-driven systems require careful validation of event producers, consumers, message permissions, and replay operations.

Monolithic systems still require secure module boundaries, access controls, dependency management, and protection against application-wide failures.

Security cannot be represented adequately by a single architecture complexity score.

It should be evaluated through separate security requirements and threat analysis.

## 14. Limitations and Interpretation

The five implementations are educational architecture decision models rather than production benchmarking platforms.

Their limitations are important.

### Synthetic measurements

The architecture profiles contain illustrative values.

They do not represent measured performance or independently verified cloud pricing.

### Simplified availability

The serial availability calculations assume independent failures.

Real-world dependencies may share infrastructure, networks, identity services, regions, and control planes.

### Simplified cost models

The examples use monthly recurring expenditure.

They do not fully model:

- Initial engineering investment.
- Migration.
- Data transfer.
- Licensing changes.
- Contractual commitments.
- Variable traffic.
- Disaster recovery infrastructure.
- Opportunity cost.

### Weighted score limitations

A weighted score depends on normalization and business priorities.

Different scoring functions can produce different rankings.

Hard constraints should be applied before selecting a preferred architecture.

### Incomplete operational assessment

The examples do not model every operational factor, such as:

- Staff availability.
- Incident frequency distributions.
- Deployment lead time.
- Mean time to detect.
- Data sovereignty.
- Vendor exit costs.
- Regulatory compliance.
- Organizational readiness.

### Implementation differences

The language implementations deliberately use different evaluation designs.

Python emphasizes simulation and reporting.

JavaScript emphasizes events, asynchronous evaluation, and dependency graphs.

C++ emphasizes efficient domain evaluation and governance checks.

Java emphasizes enterprise policies, immutable domain objects, and service separation.

PostgreSQL emphasizes persistent records, relational integrity, procedures, and reporting.

Their numerical results should not be assumed to be identical because their scoring functions and measurement inputs are not completely equivalent.

## 15. Practical Evaluation Checklist

| Evaluation area | Required evidence |
|---|---|
| Business requirements | Defined business capabilities and constraints |
| Cost | Infrastructure and operational cost estimates |
| Complexity | Development and operational assessment |
| Performance | Representative load tests and percentile latency |
| Reliability | Availability targets and failure analysis |
| Scalability | Capacity tests and scaling behavior |
| Security | Threat analysis and security controls |
| Data | Ownership, consistency, and recovery strategy |
| Operations | Monitoring, deployment, and incident procedures |
| Governance | Decision criteria and documented approval |
| Validation | Production-like benchmark and recovery testing |

The final architecture decision should identify the selected design, rejected alternatives, evaluation assumptions, accepted risks, measurable requirements, and conditions that would justify reconsideration.

An architecture is appropriate when its operational and technical characteristics satisfy the system's actual requirements at an acceptable total cost of ownership.
