# CAP Theorem: Consistency, Availability and Partition Tolerance

## Scope

The CAP theorem describes a fundamental trade-off in distributed systems. Its central concern is what a distributed system can guarantee when communication between participating nodes is disrupted.

The three properties are:

| Property | Meaning in a distributed system | Key question |
|---|---|---|
| Consistency | A successful read observes a coherent logical state according to the system's consistency model | Can different replicas expose conflicting authoritative values? |
| Availability | Every request received by a reachable, non-failed node receives a response | Will the system continue responding when coordination is unavailable? |
| Partition tolerance | The system continues to operate despite communication failures between groups of nodes | What happens when replicas cannot communicate? |

The important CAP decision occurs during a network partition. A system that must tolerate that partition cannot simultaneously guarantee both strong consistency and availability across the separated sides.

This does not mean that a distributed system permanently possesses only two of the three properties. Under normal network conditions, replicas can communicate and a system can provide both strong consistency and high availability. CAP becomes a design constraint when the network itself fails.

## Consistency

In the context of CAP, consistency concerns the logical state observed by clients after an operation completes successfully.

Suppose three replicas hold the state of a payment:

`payment:100 = approved`

If a client successfully changes the value to:

`payment:100 = reversed`

a strongly consistent operation should not allow another successful read to treat the old value as the authoritative current state merely because that read reached a different replica.

The Python implementation models this using versioned values and quorum-based operations. A CP write requires a majority of reachable replicas before it is accepted. If a coordinator becomes isolated during a partition, the write is rejected rather than allowing the isolated replica to establish an independently authoritative value.

Consistency is therefore a property of the distributed protocol, not simply a property of the local data structure.

## Availability

Availability in CAP means that requests sent to a non-failed node continue receiving responses.

Availability does not mean that the returned value is necessarily the newest value known anywhere in the system. This distinction is important.

The JavaScript implementation demonstrates an AP-style operation in which each reachable side of a partition can continue accepting a write. The isolated region does not wait indefinitely for a replica that it cannot contact.

The benefit is continued service.

The cost is that two sides of the partition can temporarily hold different values.

For example, one partition may record:

`inventory:sku-77 = stock=8`

while another records:

`inventory:sku-77 = stock=5`

Both operations can be accepted locally because the AP behavior prioritizes continued operation during the communication failure.

Availability therefore moves part of the problem from immediate coordination to later reconciliation.

## Partition Tolerance

A partition is a communication failure between nodes or groups of nodes.

Consider three replicas:

`Delhi <-> Mumbai <-> Bengaluru`

A network failure can produce:

`Delhi`

and:

`Mumbai <-> Bengaluru`

The Delhi node is still running. The Mumbai and Bengaluru nodes are also still running. The failure is the communication path between them.

Partition tolerance means the distributed architecture has an explicit behavior for this condition rather than assuming that all replicas can always communicate.

The practical design question becomes:

> When the replicas cannot coordinate, should the system reject an operation or accept it locally?

A CP-oriented system commonly rejects an operation that cannot satisfy its consistency protocol.

An AP-oriented system commonly accepts an operation using the reachable portion of the system and repairs divergent state later.

## The CAP Relationship

The relationship can be represented as:

`Normal connectivity -> replicas coordinate -> consistency and availability can coexist`

`Network partition -> coordination is unavailable`

`Network partition + strong consistency -> some operations may be rejected`

`Network partition + continued availability -> temporary divergence may occur`

Partition tolerance is therefore not normally treated as an optional property for systems operating across unreliable networks. The practical trade-off is what the system does with consistency and availability when a partition occurs.

## Quorum Reasoning

For a cluster containing `N` replicas, a simple majority quorum is:

`floor(N / 2) + 1`

For three replicas:

`floor(3 / 2) + 1 = 2`

For five replicas:

`floor(5 / 2) + 1 = 3`

A majority requirement makes it impossible for two independent majority groups to exist simultaneously in an odd-sized cluster.

The Python simulator uses this reasoning to demonstrate why a CP write fails when only one member of a three-node cluster is reachable.

The quorum itself is not the entire definition of CAP. Real distributed systems may use consensus algorithms, leader-based replication, leases, quorum reads and writes, logical clocks, hybrid logical clocks, vector clocks, or application-specific conflict resolution.

## CP Behavior in the Python Implementation

The Python program implements a compact distributed key-value model.

Each `Node` stores versioned records and maintains a logical clock. `DistributedKVStore` manages replicas and network partitions.

The CP path checks the number of reachable replicas before modifying state. With three replicas, two reachable replicas are required. If the coordinator is isolated, the operation returns a failed `WriteResult`.

This is an intentional availability sacrifice.

The node could technically write the value locally, but doing so would allow an isolated partition to establish a state without confirming the majority. The CP model therefore treats refusal as preferable to potentially inconsistent authoritative state.

The Python implementation also includes reconciliation for the AP scenario. It uses the highest logical version as a deliberately simple conflict-resolution rule. Production systems may use considerably stronger mechanisms.

## AP Behavior in the Python Implementation

The AP path does not require a majority before accepting a write.

During a partition, the reachable replicas can therefore continue operating. Two independent partitions can accept different values for the same logical key.

When the network is restored, the example applies a last-write-wins style reconciliation based on logical versions.

This is useful for demonstrating the CAP trade-off, but the conflict-resolution algorithm should not be interpreted as universally correct.

For some domains, last-write-wins can destroy meaningful business state.

A financial transaction, inventory reservation, seat booking, or security policy may require a domain-specific conflict model rather than simply choosing the newest record.

## JavaScript: Event-Driven Distributed Behavior

The JavaScript implementation approaches CAP through asynchronous execution.

`PartitionNetwork` determines which replicas can communicate. `CAPCluster` uses asynchronous methods so that network coordination is represented as an event-driven operation rather than as a purely synchronous function call.

The AP example shows two partition sides independently updating the same inventory record.

The event-processing example represents partition detection, a write request, quorum failure, and partition healing as separate events. This reflects an important property of distributed software: failures are often observed as asynchronous events rather than as one clean local exception.

The implementation also explicitly handles unknown events instead of silently ignoring them.

## C++ Case Study: Governance State

The C++ program models a repository governance service whose distributed nodes store policy state.

A policy can define requirements such as:

- required approvals
- required CI checks
- security checks
- whether direct changes are allowed

The purpose of this scenario is not to turn CAP into a repository-management tutorial. It demonstrates how distributed consistency decisions affect an authoritative policy service.

In CP mode, a governance policy update is rejected if the coordinator cannot reach a majority.

In AP mode, the reachable partition can accept policy changes independently. After connectivity is restored, the example reconciles the divergent policy state.

The C++ implementation uses `std::map` for replica state, `std::set` for partition membership, `std::optional` for potentially absent records, and explicit result structures for successful and rejected operations.

These structures make the distinction between a missing value, an unavailable operation, and a successful operation explicit.

## Java: Enterprise Domain Modeling

The Java implementation represents distributed governance using explicit domain types.

`RepositoryPolicy` encapsulates repository-level policy state. Validation occurs in the constructor so an invalid approval requirement cannot create an invalid policy object.

`GovernanceNode` represents a distributed policy replica.

`NetworkPartition` represents communication topology rather than mixing network logic directly into policy state.

`GovernanceService` coordinates the domain objects and implements CP and AP behavior.

This separation matters because consistency policy, network topology, replica state, and repository policy are different concepts. Keeping them separate makes the behavior easier to reason about and test.

Java records are used for immutable result values such as `VersionedValue` and `WriteDecision`. Enums model bounded state such as `CAPMode` and `NodeStatus`.

## SQL Data Model

The PostgreSQL implementation models a repository governance environment with distributed infrastructure.

The principal entities are:

| Entity | Purpose |
|---|---|
| `repository` | Stores repositories and their selected distributed behavior |
| `branch` | Represents repository branches |
| `cluster_node` | Represents distributed service nodes |
| `network_partition` | Represents a partitioned communication topology |
| `node_partition_membership` | Associates nodes with network partitions |
| `pull_request` | Represents proposed repository changes |
| `reviewer` | Represents reviewers |
| `review` | Stores review decisions |
| `review_comment` | Stores individual review discussions |
| `status_check` | Stores commit-specific automated checks |
| `branch_protection` | Stores merge restrictions |
| `merge_event` | Records successful merge operations |

The SQL model deliberately separates these concerns because an approval, a status check, and a branch-protection policy represent different facts.

## Database Integrity

The schema uses primary keys to identify entities and foreign keys to preserve relationships.

For example, a review references a Pull Request and a reviewer. A review comment references a review. A status check references a Pull Request.

The database also uses constraints for values that must remain valid regardless of application behavior.

Examples include:

`required_approvals >= 0`

and:

`line_number > 0`

The `review_state` and `node_status` enumerations restrict state values to defined domain states.

These constraints demonstrate a general distributed-systems principle: correctness rules should be enforced at the strongest appropriate layer rather than relying entirely on application assumptions.

## Stale State and Commit-Specific Observations

A review approval is associated with a specific commit SHA.

This matters because the contents of a Pull Request can change after a review.

An approval for commit `abc123` cannot automatically be treated as an approval for an unrelated later commit such as `xyz789`.

The SQL queries therefore compare the review's `commit_sha` with the Pull Request's current `head_commit`.

The same principle applies to status checks.

A successful check for an old commit is not automatically evidence that the current changeset passes the same check.

This is an example of maintaining consistency around the exact version of data being evaluated.

## CAP and Repository Governance

A repository governance system can illustrate the difference between local correctness and distributed correctness.

Suppose a protected branch requires two approvals and successful security checks.

If a distributed governance service has multiple regional replicas and one region loses communication with the others, a CP design can refuse to make an authoritative policy change until it can establish the required coordination.

An AP design may allow the isolated region to continue processing according to locally available policy information.

The AP behavior may improve operational availability, but it creates a reconciliation requirement.

This distinction is important:

`Pull Request workflow -> proposes a changeset`

`Code review -> evaluates the changeset`

`Approval -> records a review decision`

`Branch protection -> enforces repository-level merge conditions`

`CAP protocol -> determines how distributed replicas behave when coordination fails`

These are related concerns but they are not interchangeable.

## Pull Requests and CAP

A Pull Request is a workflow object representing proposed changes between a source branch and a target branch.

Its state can change as new commits are pushed, reviews are submitted, checks complete, conflicts appear, or the Pull Request is merged or closed.

A distributed Pull Request service may replicate information about the Pull Request across regions.

During normal connectivity, replicas can coordinate updates.

During a partition, the system needs a defined policy for conflicting updates. For example, one side might record a state transition while another side does not yet observe it.

The CAP issue exists at the distributed service layer rather than in the conceptual definition of a Pull Request itself.

## Code Review and CAP

Code review evaluates a proposed changeset.

Review comments can be attached to specific files and lines. A reviewer can approve the current state, request changes, or provide non-blocking comments.

Review state and Pull Request state are separate.

A Pull Request can remain open while a review requests changes. A subsequent commit can address the concern, after which another review may evaluate the updated changeset.

In a distributed review service, conflicting review events may require careful ordering and reconciliation.

The identity of the reviewed commit is therefore important.

## Approvals and CAP

An approval is a review decision associated with a particular Pull Request state.

Approval eligibility can depend on repository policy, reviewer permissions, review ownership rules, and whether the approval remains valid for the current changeset.

A distributed system must avoid treating a stale or conflicting approval as automatically authoritative.

The SQL implementation represents approval state separately from branch protection and evaluates approvals against the current Pull Request commit.

This separation makes the relationship explicit without confusing an approval with the policy that requires it.

## Branch Protection and CAP

Branch protection expresses repository-level restrictions.

Examples include required reviews, required status checks, restrictions on direct pushes, restrictions on force pushes, deletion restrictions, conversation requirements, and linear-history requirements.

These are policy conditions.

They do not themselves solve distributed replication.

If branch-protection configuration is replicated across multiple governance nodes, CAP becomes relevant to how those nodes maintain authoritative policy state.

A CP approach can refuse policy changes when the required coordination is unavailable.

An AP approach can permit local operation but must eventually determine which policy state is authoritative.

## Failure Modes

### Network Partition

The most important CAP failure mode is communication loss between replicas.

A process can remain healthy while its network path to another process is unavailable. Treating this as merely a process failure can lead to incorrect recovery decisions.

### Stale Replica

A replica can remain operational while holding an older state.

Availability may therefore be high even when information is not current.

### Conflicting Writes

Two partitioned sides can independently accept changes to the same logical entity.

A system must have an explicit conflict-resolution mechanism if it allows this behavior.

### Lost Coordination

A CP system can intentionally reject operations when coordination is unavailable.

The rejection is not necessarily a system defect. It may be the mechanism through which the consistency guarantee is preserved.

### Unsafe Reconciliation

Reconciliation can itself be dangerous if the chosen conflict-resolution rule is inappropriate.

Selecting the highest timestamp or logical version is easy to implement but may be semantically wrong for business operations that cannot safely be overwritten.

## Logical Clocks

The examples use simple logical versions to make ordering visible.

A logical clock does not prove that two operations occurred in real-world chronological order. It provides an ordering mechanism within the model.

Real distributed systems can require more sophisticated mechanisms when concurrent updates must be distinguished.

Vector clocks can represent causal relationships between versions.

Hybrid logical clocks combine physical-time information with logical ordering.

Consensus systems can establish an authoritative ordering through a coordinated protocol.

The appropriate mechanism depends on the consistency and failure requirements of the application.

## Why CP Does Not Mean "No Availability"

A CP system can remain highly available under normal conditions.

The CAP distinction concerns availability during a partition.

If all replicas can communicate, a CP system may successfully process requests through its normal replication or consensus protocol.

When a partition prevents the required coordination, the system may reject some operations.

Therefore, describing a system simply as "CP means unavailable" is inaccurate. The more precise statement is that the system gives priority to consistency over availability for operations that cannot safely complete during the partition.

## Why AP Does Not Mean "No Consistency"

AP does not mean that the system intentionally produces arbitrary data.

Many AP-oriented systems provide strong consistency during normal operation and use eventual consistency or conflict-resolution techniques when partitions occur.

The key distinction is what guarantees remain available during the partition.

An AP design can continue serving requests, while replicas may temporarily disagree.

The system then needs a convergence mechanism.

## Eventual Consistency

Eventual consistency means that, provided updates stop and communication is eventually restored, replicas can converge toward a common state.

The convergence process can use replication, repair, anti-entropy, conflict resolution, hinted handoff, read repair, CRDTs, or other mechanisms depending on the architecture.

The Python, C++, and Java demonstrations use a deliberately simple reconciliation rule so the CAP trade-off can be observed directly.

Production systems require domain-specific decisions about whether concurrent updates can be merged, overwritten, rejected, or transformed.

## Performance Considerations

Strong coordination usually introduces communication overhead.

A quorum-based operation may require messages between replicas before the client receives confirmation.

This can increase latency, particularly when replicas are geographically distributed.

Replication also increases storage and network costs.

AP behavior can reduce the amount of immediate coordination required for a write, but it does not eliminate complexity. Conflict detection, reconciliation, repair, duplicate handling, and stale reads become part of the system's operational cost.

Therefore, CAP decisions should be evaluated together with latency, consistency requirements, failure recovery, storage cost, network topology, and business semantics.

## Security Considerations

Distributed consistency mechanisms can become security boundaries.

An isolated node must not be allowed to invent an authoritative security policy merely because it cannot reach other replicas.

This is especially important for access-control policies, authentication configuration, financial authorization, and repository governance.

A reconciliation process must also authenticate state received from other replicas. Otherwise, an attacker could attempt to inject a seemingly newer version and win a naive last-write-wins conflict rule.

Audit records should preserve enough information to determine which node produced an update, which version was observed, and how a conflict was resolved.

## Debugging Distributed CAP Behavior

Distributed failures are difficult to diagnose because local observations can be correct while the global state is inconsistent.

Useful diagnostic information includes:

- replica identifier and region
- logical or commit version
- operation identifier
- coordinator
- observed partition topology
- acknowledgement set
- quorum requirement
- operation outcome
- conflict-resolution decision
- reconciliation timestamp

The Python, JavaScript, C++, and Java programs expose these concepts through explicit result objects and state-printing operations.

This is preferable to returning only a generic success or failure message because distributed failures often require understanding why a decision was made.

## Common Design Mistakes

### Treating Network Failure as an Ordinary Application Error

A timeout between replicas can mean that the remote node is unavailable, the network is partitioned, or the response is delayed. These conditions can have different consistency implications.

### Accepting Local State Without Defining Authority

An AP design can continue operating during a partition, but it needs a documented rule for what happens when conflicting states meet.

### Treating Timestamps as Perfect Ordering

Wall-clock time can move, differ between machines, and fail to represent causal relationships. A timestamp-based conflict rule therefore has limitations.

### Ignoring Version Identity

Reviews, checks, policies, and other decisions can become stale when the underlying object changes. A decision should often be tied to the exact version it evaluated.

### Assuming a Database Transaction Solves Distributed CAP

A transaction inside one database instance can enforce local atomicity and consistency rules. It does not automatically provide a cross-region distributed consensus protocol.

## Practical Decision Boundary

The central architectural question can be expressed as:

`Can this operation safely complete without confirming the other replicas?`

If the answer is no, a CP-oriented system may reject or delay the operation during a partition.

If the answer is yes, an AP-oriented system may continue locally and reconcile later.

The answer depends on the business meaning of the data.

A shopping recommendation can often tolerate temporary divergence.

An authorization policy may require much stronger coordination.

An inventory reservation can require careful conflict handling because two independent reservations may exceed available stock.

A financial ledger generally cannot treat conflicting transactions as simple last-write-wins records.

## Relationship Between the Five Implementations

The implementations deliberately approach CAP from different technical perspectives.

The Python program focuses on a distributed key-value model, quorum reasoning, partitions, reads, writes, and reconciliation.

The JavaScript program focuses on asynchronous and event-driven behavior, showing how partition events and local operations can be processed without synchronous global coordination.

The C++ program models a repository governance service and demonstrates CP and AP behavior through explicit replica state, partition membership, and reconciliation.

The Java program uses enterprise-oriented domain types to separate policy state, node state, network topology, and distributed service behavior.

The PostgreSQL implementation models the surrounding repository governance domain relationally and demonstrates how approvals, status checks, branch protection, and version-specific decisions can be represented with database constraints and queries.

Together, these perspectives distinguish the CAP properties from the application mechanisms built on top of distributed infrastructure.
