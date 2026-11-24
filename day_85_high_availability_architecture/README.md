# High Availability Architecture: Eliminating Single Points of Failure

## 1. Architectural Foundations

High Availability (HA) is the ability of an infrastructure or application to continue providing an acceptable level of service when individual components fail.

An HA architecture assumes that hardware failures, software defects, network interruptions, power failures, configuration errors, and maintenance operations will occur. Its objective is to prevent an individual failure from becoming a complete service outage.

A Single Point of Failure (SPOF) is a component, dependency, or operational mechanism whose failure causes a critical service to become unavailable because no effective alternative exists.

Examples include:

- One application server handling all customer requests.
- One database server without a usable replica.
- One load balancer without redundancy.
- One network connection serving an entire data centre.
- One DNS service without an independent recovery mechanism.
- One control-plane node responsible for all cluster decisions.
- One power supply serving multiple supposedly independent servers.

Eliminating SPOFs requires architectural redundancy, independent failure domains, automatic detection, controlled failover, sufficient spare capacity, and tested recovery procedures.

### 1.1 Availability and Reliability

Reliability measures the probability that a component operates without failure during a specified period.

Availability measures the proportion of time that a service is operational and accessible.

For a repairable component:

\[
A=\frac{MTBF}{MTBF+MTTR}
\]

Where:

- MTBF: Mean Time Between Failures.
- MTTR: Mean Time To Repair or Restore.

A system can have components with relatively low reliability and still achieve high availability when failures are detected quickly and service is transferred to healthy alternatives.

Availability targets are often expressed in terms of annual downtime.

| Availability | Approximate annual downtime |
|---|---:|
| 99% | 87.60 hours |
| 99.9% | 8.76 hours |
| 99.95% | 4.38 hours |
| 99.99% | 52.56 minutes |
| 99.999% | 5.26 minutes |

These values assume continuous operation over a 365-day year. Actual service-level calculations depend on measurement boundaries, maintenance exclusions, and incident definitions.

## 2. Redundancy Architecture

Redundancy provides alternative components that can assume workloads when another component becomes unavailable.

The quality of redundancy depends on whether the alternatives are genuinely independent.

### 2.1 Active-Active Architecture

In an active-active configuration, multiple instances simultaneously serve production traffic.

Characteristics:

- Requests are distributed across healthy instances.
- Every active instance can perform its assigned workload.
- A failed instance is removed from traffic.
- Remaining instances continue serving requests.
- Recovery allows the instance to rejoin the cluster.

Advantages:

- Efficient use of installed infrastructure.
- Continuous workload distribution.
- No requirement to activate an entirely idle standby.
- Potentially lower recovery time.

Limitations:

- Requires appropriate data consistency mechanisms.
- Distributed sessions require shared or replicated state.
- Concurrent writes require conflict management.
- Remaining instances must have sufficient capacity.

The Python and JavaScript implementations use active-active application replicas with capacity-aware request routing.

### 2.2 Active-Passive Architecture

An active-passive architecture uses one active instance and one or more standby instances.

The standby instance takes over when the active instance fails.

The standby can be:

- Hot: Running and continuously synchronized.
- Warm: Running with limited readiness or partially synchronized state.
- Cold: Provisioned or started after failure.

Active-passive systems are useful when concurrent active processing would create consistency problems or when software licensing and resource costs favour standby infrastructure.

The primary risk is an incorrectly configured or outdated standby that cannot take over successfully.

### 2.3 N+1 Redundancy

N+1 architecture provides one additional component beyond the number required for normal operation.

For example, if three servers are required to handle normal production demand, four servers provide one additional server.

N+1 is useful only when the remaining infrastructure can sustain the required workload after a failure.

It does not automatically guarantee survival of multiple simultaneous failures.

### 2.4 N+2 Redundancy

N+2 architecture provides two additional components beyond the required operating capacity.

It increases tolerance for simultaneous failures but requires greater infrastructure investment.

The appropriate redundancy level depends on:

- Business criticality.
- Failure probability.
- Recovery objectives.
- Infrastructure cost.
- Expected workload.
- Correlation between failure events.

## 3. Failure Domains

A failure domain is a group of infrastructure components that can be affected by a common failure.

Distributing replicas across failure domains prevents a localized failure from removing every replica.

| Failure domain | Example failure |
|---|---|
| Server | Hardware failure |
| Rack | Power distribution failure |
| Network segment | Switch or routing failure |
| Availability zone | Data-centre infrastructure interruption |
| Region | Regional infrastructure outage |
| Cloud account | Account-level configuration or access failure |
| Power domain | Shared electrical supply failure |

### 3.1 Availability-Zone Distribution

Consider three application instances:

| Instance | Availability zone |
|---|---|
| app-1 | zone-a |
| app-2 | zone-b |
| app-3 | zone-c |

If zone-a becomes unavailable, app-2 and app-3 remain operational.

This architecture provides protection against a single-zone failure, provided that shared dependencies also remain available.

A deployment with three servers in the same physical rack does not provide equivalent resilience.

### 3.2 Correlated Failures

Redundant components may fail together when they share dependencies.

Examples:

- Multiple servers connected to one network switch.
- Multiple database replicas using one storage system.
- Replicas deployed in the same availability zone.
- Several services depending on one DNS resolver.
- Multiple clusters using one identity provider.

This is why counting replicas alone is insufficient.

The failure-domain analysis in the implementations evaluates whether the surviving replicas still satisfy the minimum availability requirement after a domain failure.

## 4. Load Balancing and Traffic Distribution

A load balancer distributes incoming requests across multiple service instances.

Its responsibilities can include:

- Request distribution.
- Health-based backend selection.
- Connection management.
- Capacity-aware routing.
- Removal of failed instances.
- Restoration of recovered instances.

### 4.1 Health-Based Routing

A backend should receive production traffic only when it passes the required health checks.

Two common health-check types are:

**Liveness check**

Determines whether a process is running and should continue executing.

**Readiness check**

Determines whether a process can currently accept production traffic.

A running process may fail readiness checks because its database connection, required configuration, or critical dependency is unavailable.

### 4.2 Load-Distribution Algorithms

| Algorithm | Mechanism |
|---|---|
| Round Robin | Distributes requests sequentially |
| Weighted Round Robin | Uses configured backend weights |
| Least Connections | Selects the backend with fewer active connections |
| Weighted Least Connections | Considers backend capacity |
| Consistent Hashing | Maps requests to selected instances using a hash |
| Random Selection | Selects a backend randomly |

The Python, C++, and Java examples use capacity-aware least-loaded routing.

The JavaScript implementation combines least-utilization selection with asynchronous request execution.

### 4.3 Load Balancer Redundancy

A load balancer can itself become a SPOF.

Production designs can use:

- Multiple load-balancer instances.
- Redundant network paths.
- Virtual IP failover.
- Anycast routing.
- Managed load-balancing services deployed across availability zones.

The load-balancing control mechanism and the data path must both be considered.

## 5. Database High Availability

Database availability is more complex than application-server redundancy because database replicas must maintain acceptable data consistency.

### 5.1 Primary-Replica Architecture

A primary database accepts write operations and replicates changes to one or more replicas.

Replicas can provide:

- Read scaling.
- Standby recovery.
- Disaster recovery.
- Reporting workloads.

Replication can be synchronous or asynchronous.

### 5.2 Synchronous Replication

A transaction waits for the required acknowledgement from the configured replica set before being acknowledged to the client.

Advantages:

- Stronger durability guarantees against certain failures.
- Reduced risk of losing acknowledged transactions during an eligible failover.

Limitations:

- Increased write latency.
- Dependence on replica responsiveness.
- Potential write unavailability when required acknowledgements cannot be obtained.

The exact guarantees depend on the database implementation and commit configuration.

### 5.3 Asynchronous Replication

The primary acknowledges a transaction before all replicas have applied the change.

Advantages:

- Lower write latency.
- Greater tolerance for network delays.
- More flexible geographic distribution.

Limitations:

- Replica lag.
- Potential loss of recently acknowledged transactions during failover.
- Risk of stale reads.

### 5.4 Replication Lag

Replication lag represents the delay between a change occurring on the primary and becoming available on a replica.

It is important when determining whether a replica is safe to promote.

A database failover controller must evaluate:

- Replica health.
- Replication position.
- Data freshness.
- Promotion eligibility.
- Previous primary status.
- Network partition conditions.

Promoting an outdated replica can cause data loss.

### 5.5 Split-Brain Prevention

Split-brain occurs when multiple nodes independently believe they are the authoritative primary.

This can result in conflicting writes and inconsistent data.

Controls include:

- Quorum-based leadership.
- Fencing tokens.
- Storage-level fencing.
- Lease mechanisms.
- Controlled promotion.
- Network partition detection.

Fencing prevents an older leader from continuing to modify protected resources after a new leader has been elected.

A new leadership term alone is not sufficient unless the storage or resource-access layer enforces the fencing decision.

## 6. Quorum and Leader Election

A quorum is the minimum number of participating members required to make an authoritative cluster decision.

For a cluster containing an odd number of voting members:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

Where:

- \(N\) is the total number of voting members.
- \(Q\) is the required majority.

| Voting members | Required quorum | Tolerated unavailable members |
|---:|---:|---:|
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |
| 9 | 5 | 4 |

A three-member cluster distributed across three independent zones can continue making quorum decisions after one member becomes unavailable.

A two-member cluster cannot tolerate one unavailable member while maintaining a majority of two.

### 6.1 Leader Election

A leader is selected to coordinate operations that require a single authoritative decision-maker.

Leader election generally involves:

1. Detecting an unavailable or expired leader.
2. Determining whether a quorum exists.
3. Selecting an eligible candidate.
4. Establishing a new leadership term.
5. Preventing stale leaders from modifying protected resources.
6. Resuming controlled operations.

The JavaScript, C++, Java, and Python implementations demonstrate simplified majority-based leader selection.

They are educational models rather than implementations of Raft, Paxos, or another production consensus protocol.

## 7. Health Monitoring and Automatic Failover

Monitoring detects failures and provides information required for recovery decisions.

A monitoring system should observe:

- Node availability.
- Application responsiveness.
- Network connectivity.
- Database connections.
- Replication lag.
- CPU and memory utilisation.
- Disk capacity.
- Request latency.
- Error rates.
- Quorum status.

### 7.1 Failure Detection

A heartbeat is a periodic signal indicating that a component is responding.

If expected heartbeats are missing beyond an established threshold, the monitoring system can mark the component as suspected or failed.

A missing heartbeat does not always prove that a node has failed. Network partitions can produce similar symptoms.

Failure detectors should therefore consider multiple signals and use appropriate timeouts.

### 7.2 Failover Workflow

The operational workflow is:

1. Monitor infrastructure health.
2. Detect an unhealthy component.
3. Verify failure conditions.
4. Remove the component from traffic.
5. Determine whether service redundancy remains sufficient.
6. Elect a new leader when required.
7. Select an eligible replacement.
8. Enforce fencing against the previous leader.
9. Restore traffic.
10. Record the incident and recovery metrics.

### 7.3 Recovery and Failback

Recovery means returning a failed component to an operational state.

Failback means transferring responsibilities back to a preferred or recovered component.

Recovery does not automatically justify immediate failback.

Before reintroducing a component, verify:

- Hardware and process health.
- Data synchronization.
- Replication status.
- Configuration consistency.
- Network connectivity.
- Application readiness.
- Capacity availability.

Uncontrolled failback can cause repeated switching, known as failover flapping.

## 8. Circuit Breakers and Fault Isolation

A circuit breaker prevents repeated calls to an unhealthy dependency.

It has three principal states.

| State | Behaviour |
|---|---|
| CLOSED | Requests are permitted |
| OPEN | Requests are rejected or redirected |
| HALF_OPEN | Limited test requests determine recovery |

The JavaScript implementation includes a circuit-breaker model.

When repeated operations fail, the circuit opens. After a configured interval, it enters the half-open state.

A successful test closes the circuit. Another failure opens it again.

Circuit breakers reduce cascading failures when one service becomes unavailable.

They do not replace redundancy, health monitoring, or dependency recovery.

## 9. Service Dependencies and Cascading Failures

An application may depend on multiple infrastructure services.

For example:

    Customer Request
          |
          v
    Load Balancer
          |
          v
    Application Tier
          |
          +------ Database
          |
          +------ Cache
          |
          +------ Identity Service
          |
          +------ Message Broker

A failure in a critical dependency can make the application unavailable even when every application server is healthy.

This distinction is essential.

Application availability is not equivalent to infrastructure-node availability.

Production architectures should:

- Identify critical dependencies.
- Avoid shared dependency SPOFs.
- Apply timeouts.
- Use bounded retries.
- Introduce circuit breakers.
- Separate critical and non-critical workloads.
- Define graceful degradation behaviour.
- Test dependency failure scenarios.

Retries should use bounded limits and backoff to avoid amplifying failures during an outage.

## 10. Disaster Recovery and Business Continuity

High availability and disaster recovery are related but different concepts.

High availability primarily addresses continued service operation during component and localized infrastructure failures.

Disaster recovery addresses restoration following major disruptive events, potentially including complete regional failure.

Two important measures are:

**Recovery Time Objective (RTO)**

The maximum acceptable duration of service interruption.

**Recovery Point Objective (RPO)**

The maximum acceptable amount of data loss measured in time.

| Scenario | Main concern |
|---|---|
| Server failure | Local failover |
| Availability-zone failure | Cross-zone redundancy |
| Regional outage | Cross-region recovery |
| Data corruption | Point-in-time recovery |
| Accidental deletion | Backup restoration |
| Security compromise | Isolated recovery environment |

A replicated database is not a replacement for independent backups. Replication can reproduce accidental deletions and logical corruption.

## 11. Implementation Architecture

The five source files demonstrate different engineering approaches to the same availability problem.

### 11.1 Python: Infrastructure Simulation

The Python script uses dataclasses, enums, dictionaries, and object-oriented domain models.

Principal components:

| Component | Responsibility |
|---|---|
| `Node` | Infrastructure state, capacity and health |
| `Service` | Replica membership and minimum availability |
| `QuorumCluster` | Majority voting and leader election |
| `HighAvailabilityPlatform` | Monitoring, routing, failover and reporting |

The simulation demonstrates:

- Registration of infrastructure nodes.
- Active-active application replicas.
- Database replica distribution.
- Health-based routing.
- Individual node failure.
- Availability-zone failure.
- Recovery.
- Quorum evaluation.
- Failure-domain analysis.

The least-loaded routing mechanism sorts available nodes by utilization.

For \(R\) replicas, its sorting cost is:

\[
O(R\log R)
\]

A larger production implementation could use a priority queue or load-balancer data structure to reduce selection overhead.

### 11.2 JavaScript: Event-Driven Availability

The JavaScript implementation uses Node.js event handling, asynchronous operations, Maps, Promises, and circuit breakers.

Principal components:

| Component | Responsibility |
|---|---|
| `InfrastructureNode` | Capacity and health state |
| `CircuitBreaker` | Failure isolation |
| `QuorumManager` | Leadership and majority |
| `AvailabilityPlatform` | Event-driven infrastructure management |

Important events include:

- `node:failed`
- `node:recovered`
- `service:failover`
- `leader:changed`
- `quorum:lost`
- `request:completed`
- `request:failed`

Event-driven architecture separates failure detection from the components that respond to it.

The asynchronous execution model demonstrates how service operations can be monitored without requiring a synchronous application workflow.

The sample does not implement a distributed event bus or persistent event delivery. Production event handling requires durable records, retry policies, and idempotent consumers.

### 11.3 C++17: Governance and Capacity Engine

The C++ implementation focuses on efficient infrastructure modelling and deterministic evaluation.

Principal components:

| Component | Responsibility |
|---|---|
| `InfrastructureNode` | Node state and capacity |
| `ServiceDefinition` | Replica and availability rules |
| `QuorumCluster` | Majority evaluation |
| `HighAvailabilityEngine` | Routing and infrastructure assessment |

The implementation uses:

- STL maps for infrastructure lookup.
- Sets for uniqueness and domain analysis.
- Vectors for replica collections.
- Algorithms for traffic selection.
- Exceptions for invalid infrastructure operations.
- Explicit enums for state modelling.

Ordered-map lookups have logarithmic complexity.

For \(N\) registered infrastructure nodes, node lookup is approximately:

\[
O(\log N)
\]

The implementation separates infrastructure state from the evaluation logic.

This is useful for building infrastructure assessment engines where predictable behaviour and explicit state transitions are important.

### 11.4 Java 17: Enterprise Availability Management

The Java implementation uses records, immutable collections, enums, service classes, and domain-oriented validation.

Principal components:

| Component | Responsibility |
|---|---|
| `NodeConfiguration` | Immutable node configuration |
| `InfrastructureNode` | Runtime infrastructure state |
| `ApplicationService` | Service and replica definition |
| `AvailabilityPolicy` | Minimum availability rules |
| `QuorumService` | Majority and leadership |
| `AvailabilityEvaluator` | Policy evaluation |
| `TrafficManager` | Capacity-aware selection |
| `RepositoryGovernanceService` | Enterprise orchestration |

The design separates:

- Infrastructure configuration.
- Runtime node state.
- Availability policy.
- Quorum decisions.
- Traffic management.
- Enterprise service operations.

Immutable configuration records reduce accidental configuration changes.

Service policies can enforce both minimum replica counts and distribution across independent failure domains.

### 11.5 PostgreSQL: Relational Infrastructure Governance

The PostgreSQL script models availability architecture using relational entities and integrity constraints.

Principal tables:

| Table | Purpose |
|---|---|
| `failure_domains` | Independent infrastructure failure boundaries |
| `infrastructure_nodes` | Servers and infrastructure resources |
| `services` | Logical application services |
| `service_replicas` | Service-to-node relationships |
| `replication_groups` | Database replication configuration |
| `database_replication_members` | Database replica membership |
| `quorum_clusters` | Consensus cluster definitions |
| `quorum_members` | Voting membership |
| `health_checks` | Historical monitoring results |
| `failover_events` | Failover lifecycle |
| `infrastructure_incidents` | Infrastructure incidents |

The schema includes:

- Primary and foreign keys.
- Unique constraints.
- Check constraints.
- Enum types.
- Performance-oriented indexes.
- Constraint triggers.
- Availability views.
- Quorum evaluation.
- Failure-domain analysis.
- An availability evaluation function.
- A transactional failover procedure.

The `service_availability` view evaluates whether a service satisfies its configured replica and failure-domain requirements.

The `quorum_availability` view calculates whether the number of healthy voting members satisfies the required majority.

The `failure_domain_analysis` view evaluates hypothetical failure of individual domains.

The `execute_failover` procedure validates a replacement and records the failover operation within a transaction.

## 12. Architectural Relationships and Operational Workflow

The following relationship describes the major availability mechanisms:

    Business Availability Requirements
                    |
                    v
           Availability Policies
                    |
                    v
           Infrastructure Design
                    |
          +---------+---------+
          |                   |
          v                   v
      Redundancy         Failure Domains
          |                   |
          +---------+---------+
                    |
                    v
             Health Monitoring
                    |
                    v
              Failure Detection
                    |
                    v
              Failover Decision
                    |
          +---------+---------+
          |                   |
          v                   v
      Load Routing       Quorum Election
          |                   |
          +---------+---------+
                    |
                    v
             Service Recovery
                    |
                    v
           Availability Reporting

The architecture separates physical redundancy, runtime health, distributed coordination, traffic management, and policy evaluation.

These mechanisms work together but do not provide interchangeable guarantees.

For example, three healthy application servers cannot compensate for a database that is completely unavailable.

Similarly, a healthy database cluster cannot guarantee application availability if every application instance shares an unavailable network dependency.

## 13. Failure Scenarios and Expected Behaviour

| Failure scenario | Detection | Expected response |
|---|---|---|
| Application node failure | Health monitoring | Route traffic to other replicas |
| Database primary failure | Database monitoring | Validate and promote eligible replica |
| Load balancer failure | Endpoint monitoring | Activate redundant load balancer |
| Availability-zone failure | Domain monitoring | Continue through surviving zones |
| Quorum loss | Voting-member evaluation | Stop unsafe leadership decisions |
| Network partition | Connectivity and consensus monitoring | Prevent conflicting leadership |
| Replica lag | Replication monitoring | Restrict unsafe promotion |
| Capacity exhaustion | Utilization monitoring | Reject, queue, or shed workload |
| Recovered node | Readiness verification | Controlled re-entry |
| Regional failure | Regional monitoring | Execute disaster recovery |

## 14. Design Limitations and Production Considerations

The implementations are intentionally focused on architecture modelling, state management, policy evaluation, and infrastructure simulation.

They do not automatically configure cloud infrastructure or implement production-grade distributed consensus.

A production deployment requires additional controls.

### 14.1 Security

Infrastructure availability mechanisms must be protected against unauthorized changes.

Important controls include:

- Role-based access control.
- Mutual TLS between infrastructure components.
- Encrypted communication.
- Protected management interfaces.
- Restricted failover permissions.
- Audit trails.
- Secure secrets management.
- Authenticated health checks.
- Fencing enforcement.

An attacker who can manipulate health checks or trigger failover operations can disrupt otherwise redundant infrastructure.

### 14.2 Capacity Planning

Redundant servers must have sufficient spare capacity.

A system that distributes workload evenly during normal operation may fail after a node outage if surviving nodes cannot handle the increased workload.

Capacity planning should evaluate:

- Peak request volume.
- CPU utilisation.
- Memory consumption.
- Storage throughput.
- Network bandwidth.
- Database connection limits.
- Replication overhead.
- Failure-induced traffic redistribution.

### 14.3 Monitoring Quality

A monitoring system should avoid false positives and delayed failure detection.

Very short timeouts can cause unnecessary failovers.

Very long timeouts increase service recovery time.

Monitoring should distinguish between:

- Process failure.
- Network failure.
- Dependency failure.
- Performance degradation.
- Complete infrastructure failure.

### 14.4 Operational Testing

HA architecture must be tested through controlled failure scenarios.

Relevant testing includes:

- Application instance termination.
- Database primary interruption.
- Replica promotion.
- Network partition simulation.
- Availability-zone isolation.
- Storage interruption.
- Load-balancer failure.
- Recovery and failback.
- Backup restoration.
- Regional recovery.

Testing should measure actual RTO, RPO, service errors, data consistency, and recovery correctness.

## 15. Technical Validation Matrix

| Requirement | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Infrastructure nodes | Yes | Yes | Yes | Yes | Yes |
| Multiple replicas | Yes | Yes | Yes | Yes | Yes |
| Failure domains | Yes | Yes | Yes | Yes | Yes |
| Health monitoring | Yes | Yes | Yes | Yes | Yes |
| Active-active routing | Yes | Yes | Yes | Yes | Evaluated |
| Quorum | Yes | Yes | Yes | Yes | Yes |
| Leader election | Yes | Yes | Yes | Yes | Modelled |
| Failure simulation | Yes | Yes | Yes | Yes | Records |
| Node recovery | Yes | Yes | Yes | Yes | Status model |
| Capacity management | Yes | Yes | Yes | Yes | Yes |
| Circuit breaker | No | Yes | No | No | No |
| Failure-risk analysis | Yes | Yes | Yes | Yes | Yes |
| Transactional failover | No | No | No | No | Yes |
| Persistent audit records | No | No | No | No | Yes |

## 16. Execution Requirements

| File | Requirement |
|---|---|
| Python | Python 3.10 or newer |
| JavaScript | Node.js 18 or newer |
| C++17 | Compiler with C++17 support |
| Java | JDK 17 |
| PostgreSQL | PostgreSQL 15 or newer |

The Python, JavaScript, C++, and Java programs use standard-library capabilities and do not require third-party packages.

The PostgreSQL script creates its own `ha` schema, infrastructure tables, constraints, views, functions, procedures, indexes, and demonstration records.

The SQL script should be executed against a database where the executing role has permission to create schemas, tables, functions, procedures, and triggers.

The examples are simulations of infrastructure behaviour. They do not establish actual cloud availability, guarantee data durability, or replace operational testing.

## 17. Key Technical Distinctions

| Concept | Primary responsibility |
|---|---|
| High Availability | Maintain service availability during failures |
| Redundancy | Provide alternative components |
| Fault Tolerance | Continue operation despite defined failures |
| Load Balancing | Distribute workload |
| Failover | Transfer responsibilities after failure |
| Failback | Return responsibilities to a preferred component |
| Replication | Maintain copies of data or state |
| Quorum | Establish majority-based decision authority |
| Leader Election | Select an authoritative cluster member |
| Fencing | Prevent obsolete leaders from modifying protected resources |
| Disaster Recovery | Restore services after major disruption |
| Circuit Breaker | Limit repeated calls to failing dependencies |
| RTO | Maximum acceptable recovery duration |
| RPO | Maximum acceptable data-loss interval |

The central architectural principle is that redundancy must extend beyond individual servers to every critical dependency, including networking, storage, databases, control planes, power, identity, and operational management. A system eliminates a single point of failure only when the failure of an individual component or defined failure domain does not violate its required service-availability policy.
