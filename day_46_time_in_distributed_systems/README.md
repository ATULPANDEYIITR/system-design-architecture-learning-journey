# Time in Distributed Systems

## Scope

Distributed systems do not have a single clock that every process can read with identical accuracy. Each machine maintains a physical clock, messages experience variable delay, operating systems schedule processes independently, and clock sources can drift.

Three related mechanisms address different parts of this problem:

| Mechanism | Primary question | Main limitation |
|---|---|---|
| Physical timestamp | Approximately when did the event occur according to a local clock? | Clock skew and drift can make timestamps disagree |
| Lamport logical clock | Can one event be established as causally earlier than another? | It cannot identify all concurrent events |
| Vector clock | Which events are causally related, and which are concurrent? | Metadata grows with the number of tracked nodes |

The six files model these distinctions from different technical perspectives. They should not be interpreted as interchangeable timestamp implementations.

## Physical Time, Clock Skew, and Drift

A distributed node has a local physical clock that attempts to approximate real time. Two nodes can read different values at the same instant because their clocks have different offsets.

If node A reads

`12:00:00.100`

while node B reads

`11:59:59.900`

the 200 ms difference is clock skew. It does not mean that an event observed by A necessarily happened later than an event observed by B.

Clock drift is different. Drift describes how quickly a clock's rate differs from the desired reference rate. A clock with a positive drift gradually moves away from the reference even if it was synchronized correctly earlier.

A simplified observation model is:

`observed_time = reference_time + offset + drift_error`

Real clock behavior is more complicated because synchronization protocols, oscillator behavior, operating-system adjustments, virtualization, network delay, and time-source failures introduce additional uncertainty.

The Python `PhysicalClock` and the C++ and Java physical-clock models deliberately expose offset and drift as explicit parameters. This makes the distinction between a physical timestamp and a causal timestamp visible in executable behavior.

## Why Physical Timestamp Order Is Not Causal Order

Suppose service A creates an event and then sends a message to service B. The message establishes a causal relationship:

`A-send -> B-receive`

The wall-clock timestamps may not preserve that relationship if the clocks have sufficient skew.

This matters in production systems. A log aggregation system that sorts records exclusively by timestamp can display a receive event before its corresponding send event. The display order may be operationally useful, but it must not automatically be interpreted as causal truth.

Physical timestamps remain valuable. They are appropriate for log retention, incident investigation, latency measurement, audit records, expiration policies, scheduling, and human-readable observability. Their uncertainty needs to be considered when correctness depends on ordering.

## Lamport Logical Clocks

A Lamport clock assigns a monotonically increasing integer to events.

For a local event:

`L = L + 1`

For a message sent after the local clock has been advanced, the sender transmits its logical value.

When a receiver obtains a message carrying timestamp `R`, it updates its clock using:

`L = max(L, R) + 1`

The important property is:

`A -> B` implies `L(A) < L(B)`

where `A -> B` means that A causally precedes B.

This gives a compact representation of causal precedence. It does not give physical time, and the numerical distance between two Lamport values has no duration interpretation.

### The limitation of scalar logical clocks

Suppose service A independently performs event `A1` and service B independently performs event `B1`.

A Lamport implementation may assign:

`A1 = 4`

and

`B1 = 7`

The numbers provide an ordering, but they do not prove that `A1` caused `B1`.

Scalar Lamport timestamps therefore establish a useful ordering relation but cannot, by themselves, distinguish every concurrent pair.

The Python implementation demonstrates local, send, and receive operations. The JavaScript implementation places the same logical mechanism inside an event-driven service model, while the C++ and Java implementations use it as part of larger distributed timelines.

## Vector Clocks

A vector clock maintains one logical counter for each tracked node.

For three nodes:

`orders = 2`

`inventory = 1`

`payments = 0`

can be represented as:

`{orders: 2, inventory: 1, payments: 0}`

A local event increments the local component. A send operation advances the sender's vector and attaches it to the message. A receive operation takes the component-wise maximum of the local and remote vectors and then increments the receiver's own component.

For two vector timestamps A and B:

- A is before B when every component of A is less than or equal to the corresponding component of B and at least one component is strictly smaller.
- A is after B when the inverse condition holds.
- A and B are equal when all components match.
- A and B are concurrent when neither vector is component-wise less than or equal to the other.

Concurrency is the important distinction.

If:

`A = {node-a: 4, node-b: 1}`

and:

`B = {node-a: 3, node-b: 2}`

neither vector dominates the other. The events are concurrent according to the recorded causal history.

The Python `vector_compare`, JavaScript `compareVectors`, C++ `compareVectors`, and Java `compare` methods implement this relation explicitly.

## Python Implementation

The Python program builds a complete distributed-event model around three forms of time.

`PhysicalClock` models offset and drift. Its `read` method demonstrates that a node's physical observation can differ from the reference time.

`LamportClock` implements local, send, and receive operations. The receive rule uses the maximum of the local and received counters before incrementing.

`VectorClock` maintains a dictionary indexed by node identifier. Its `receive` method merges remote causal history component by component.

The `Event` data class keeps the three representations together:

- `physical_time` records the node's wall-clock observation.
- `logical_time` records the scalar causal timestamp.
- `vector_time` records the distributed causal history.

The distributed example models orders, inventory, and payments services. An order event produces messages to other services, and the receiving services update their logical clocks. The program then compares vector timestamps to distinguish causal events from independent events.

The synchronization example estimates clock offset from paired samples. This demonstrates an important operational distinction: estimating an offset improves physical-clock agreement but does not eliminate network delay or causal uncertainty.

The file also validates timestamp metadata before persisting events to JSON. Invalid negative logical values, incompatible vector dimensions, and timezone-naive physical timestamps are rejected.

## JavaScript Implementation

The JavaScript program emphasizes event-driven behavior.

`ServiceNode` combines a physical clock model, a `LamportClock`, and a `VectorClock`. The node can create local events, send events, and process received messages.

`EventBus` provides a JavaScript-specific event-processing layer. It demonstrates why distributed timing metadata is useful in asynchronous systems: a handler can consume an event without relying on the order in which independent callbacks happen to execute.

The `Date` type is used for physical timestamps. JavaScript's `Date` represents an instant as milliseconds from the Unix epoch, but that representation does not make distributed clocks synchronized.

The event workflow contains order creation, inventory communication, payment communication, authorization, and independent service activity. Vector comparison is then used to identify causal and concurrent relationships.

The file uses only Node.js standard APIs. Its JSON persistence uses `fs.writeFileSync`, making the resulting event metadata inspectable without a third-party package.

## C++ Case Study

The C++ program models a distributed enterprise timeline with `gateway`, `workflow`, and `audit` nodes.

`RepositoryGovernanceTimeline` is deliberately structured as a system rather than as isolated clock demonstrations. It owns Lamport clocks, vector clocks, physical-clock models, and the resulting event stream.

The `Event` structure contains all timing representations required to inspect the same event from different perspectives.

The physical-clock model includes offset and drift. This allows the case study to demonstrate why an apparently simple timestamp comparison can be misleading when different services have different clock characteristics.

The vector-clock implementation uses `std::map`, which provides deterministic node ordering and makes the causal state easy to inspect. The comparison algorithm checks both component-wise directions to determine whether one event precedes another or whether the pair is concurrent.

The enterprise workflow contains request creation, inter-service messages, receipt events, a review event, an audit message, and an independent audit decision. The resulting event stream is printed with physical time, Lamport time, and vector time together.

The C++ implementation also explicitly validates invalid Lamport values and incompatible vector dimensions. These checks are important because corrupted causal metadata can produce incorrect ordering decisions rather than merely malformed output.

## Java Enterprise Model

The Java implementation uses explicit domain types to separate physical, scalar logical, and vector timestamps.

`PhysicalTimestamp`, `LogicalTimestamp`, and `VectorTimestamp` are records. They make timestamp values immutable and validate their basic invariants when constructed.

`Node` represents an enterprise service with its own clock characteristics and logical state. Its `local`, `send`, and `receive` operations construct `DistributedEvent` records rather than returning unstructured primitive values.

The enterprise workflow contains a gateway, workflow service, and audit service. A request enters the system, crosses a service boundary, receives a decision, and produces an audit record. The same workflow can therefore be inspected through physical timestamps and causal metadata.

`EventStore` provides a small persistence abstraction. Its `byPhysicalTime` method deliberately sorts according to observed wall-clock time rather than causal order. This distinction demonstrates that a chronological display and a causal timeline answer different questions.

The Java implementation uses synchronized clock operations to make mutation of Lamport and vector state explicit. This does not turn the whole distributed system into a synchronized system. It only protects local mutable clock state when multiple Java threads interact with the same clock object.

## SQL Data Model

The PostgreSQL script represents distributed timing metadata relationally.

`nodes` stores service identity, configured clock offset, drift rate, and the most recent synchronization time.

`events` stores:

- event identity
- node identity
- event type
- event name
- physical observation timestamp
- Lamport timestamp
- structured payload

The check constraint on `logical_timestamp` prevents non-positive Lamport values from entering the table.

`event_messages` represents the relationship between a send event and its corresponding receive event. This relationship is separate from timestamp values because a message relationship itself is causal evidence.

`vector_entries` stores vector-clock components in normalized relational form. Each event can therefore have one row for every node represented in its vector.

The primary key `(event_id, node_id)` prevents duplicate vector components for the same event and node. The foreign keys ensure that both events and vector dimensions refer to real nodes.

The indexes serve different query purposes. `(node_id, observed_at)` supports time-oriented investigation within a node, while `(node_id, logical_timestamp)` supports logical-order queries. The GIN index on JSONB payload supports structured payload searches.

The `event_timeline` view produces an operational timeline using physical timestamps. The `vector_clock_state` view reconstructs each event's vector clock as JSON for inspection.

The pairwise vector query implements causal comparison using SQL aggregation. It checks whether every component of one event is less than or equal to the corresponding component of another event and also checks for strict inequality. When neither direction dominates, the events are classified as concurrent.

## Synchronization and Clock Uncertainty

Clock synchronization attempts to reduce disagreement between physical clocks.

An offset estimate can be represented as:

`offset = observed_clock - reference_clock`

Repeated samples can be summarized using a mean or median. The median can be useful when individual measurements contain outliers.

Synchronization does not eliminate uncertainty.

Network messages have transmission and queueing delays. The sender's timestamp is generated before transmission, while the receiver's timestamp is generated after arrival. A synchronization exchange itself therefore has timing uncertainty.

Clock adjustment also has operational consequences. Large corrections can make timestamps appear to move unexpectedly if an implementation steps the clock rather than applying a gradual correction.

Distributed applications should therefore define explicit assumptions about clock accuracy instead of treating synchronized wall clocks as mathematically identical clocks.

## Relationship Between the Three Mechanisms

Physical timestamps, Lamport clocks, and vector clocks solve different problems.

A physical timestamp answers an approximate temporal question:

> When did this node observe the event?

A Lamport timestamp answers a causal-ordering question:

> Can the event be placed after another causally related event?

A vector clock answers a richer causal-history question:

> Does one event causally precede the other, or are their recorded histories concurrent?

A production event record can contain all three. For example:

`observed_at = 2026-10-16T05:30:20.035Z`

`lamport = 17`

`vector = {orders: 8, inventory: 4, payments: 2}`

The physical value is useful for humans and operational tooling. The Lamport value is compact causal metadata. The vector value retains more information about distributed causal history.

## Edge Cases and Failure Modes

### Clock skew larger than event separation

If two events occur only a few milliseconds apart while node clocks differ by hundreds of milliseconds, physical ordering can be wrong.

A log viewer should not interpret that ordering as proof of causality.

### Clock drift after synchronization

A clock that was accurate during synchronization can gradually diverge because its oscillator runs at a slightly different rate.

Systems that require strong timing bounds need an explicit synchronization and error-bound strategy.

### Delayed messages

A message may arrive substantially later than expected. The receiver's logical clock must still merge the message's causal timestamp correctly.

A delayed message does not become less causally significant merely because its physical arrival time is late.

### Concurrent writes

Two services can independently modify related state before either has observed the other's operation. Vector clocks can expose this concurrency.

Applications such as replicated data stores may then need conflict-resolution policies rather than assuming one update is inherently correct because its wall-clock timestamp is larger.

### Missing vector dimensions

Vector clocks require a defined membership model. Comparing vectors that represent different node sets is unsafe because their components do not describe the same causal dimensions.

The Python, JavaScript, C++, Java, and SQL implementations validate vector membership rather than silently comparing incompatible metadata.

### Counter growth

Lamport clocks require an integer large enough for the expected event volume. Vector clocks have a more significant scalability issue because metadata grows with the number of tracked participants.

For a system with many dynamic participants, maintaining a full vector for every event can become expensive in storage, network bandwidth, and merge processing.

## Common Design Errors

Sorting distributed events by wall-clock timestamp and calling the resulting order causal is incorrect when clock uncertainty is material.

Treating a Lamport timestamp as a duration is also incorrect. The difference between Lamport values does not mean that a particular amount of physical time elapsed.

Another error is assuming that a higher Lamport value means that the event caused every event with a lower value. Lamport clocks preserve causal precedence but can assign values to concurrent events.

Using vector clocks without a clear membership strategy creates another problem. Dynamic node membership can make vectors difficult to compare and can increase metadata size substantially.

A synchronization protocol should also avoid treating a single clock reading as authoritative evidence of exact time. Multiple observations and explicit uncertainty bounds provide a more defensible operational model.

## Performance Considerations

A Lamport clock requires constant-time local and receive operations and constant-size metadata per event.

A vector clock requires work proportional to the number of tracked nodes during merge and comparison. Its metadata size is also proportional to that participant set.

Physical timestamps are compact, but their correctness depends on the quality of the underlying clock and synchronization assumptions.

The SQL design reflects these differences. Lamport timestamps are stored directly in the event row, while vector components are normalized into `vector_entries` because each event can contain multiple node-specific counters.

The choice between mechanisms should therefore be driven by the ordering information required by the application rather than by a preference for one timestamp format.

## Security and Reliability Considerations

Timing metadata can influence security-sensitive decisions. Expiration, replay detection, audit ordering, and incident reconstruction should not rely on an assumed clock accuracy that has not been established.

A malicious or malfunctioning node could emit unrealistic logical timestamps. Applications should validate ranges and ownership of causal metadata where untrusted nodes can participate.

Physical timestamps should be treated as evidence with known uncertainty rather than as unquestionable truth. Audit systems benefit from preserving the original node timestamp, the receiving timestamp, the node identity, and relevant logical metadata.

Logical clocks also do not provide authentication. A valid-looking Lamport or vector timestamp does not prove that a message came from the claimed node. Message authentication and authorization remain separate security mechanisms.

## Debugging Distributed Time

A useful event record should preserve enough information to reconstruct both physical and causal views.

The implementations store the node identifier, event identifier, physical timestamp, Lamport timestamp, vector timestamp, event type, and payload.

When investigating an incident, the physical timeline can reveal approximate latency and clock discrepancies. The causal metadata can then establish whether two records are actually related.

A discrepancy between physical order and causal order is not automatically a software defect. It can be the expected consequence of clock skew, network delay, or independent execution.

The key debugging question is therefore not simply "Which timestamp is larger?" It is "What ordering guarantee does this timestamp represent?"

## Practical Architectural Rule

A distributed application should choose time metadata according to the property it needs.

For observability, use well-defined UTC physical timestamps and record clock uncertainty when it matters.

For compact causal ordering, use Lamport clocks.

For concurrency detection, use vector clocks when the participant set and metadata cost are acceptable.

For systems that require both operational timestamps and causal correctness, store physical and logical metadata together rather than attempting to force one representation to answer every timing question.
