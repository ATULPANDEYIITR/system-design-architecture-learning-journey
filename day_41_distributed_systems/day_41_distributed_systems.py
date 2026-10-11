#!/usr/bin/env python3
"""
Distributed Systems Fundamentals
A self-contained executable study and simulation program.

The program demonstrates:
- distributed nodes and network communication
- logical clocks
- Lamport ordering
- vector clocks
- leader election
- replication
- quorum reads and writes
- eventual consistency
- retries and idempotency
- failure detection
- heartbeats
- partition behavior
- consistent hashing
- a small distributed key-value service
- request tracing and operational metrics

The simulations intentionally use in-memory objects instead of real sockets so that
the distributed-systems mechanisms remain deterministic and easy to inspect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any, Optional
import hashlib
import random
import time


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def heading(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def stable_hash(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16)


# ---------------------------------------------------------------------------
# Fundamental distributed node model
# ---------------------------------------------------------------------------

@dataclass
class Message:
    sender: str
    receiver: str
    kind: str
    payload: dict[str, Any]
    message_id: str


@dataclass
class Node:
    node_id: str
    logical_clock: int = 0
    online: bool = True
    inbox: list[Message] = field(default_factory=list)

    def tick(self) -> int:
        self.logical_clock += 1
        return self.logical_clock

    def send(self, receiver: "Node", kind: str, payload: dict[str, Any]) -> Message:
        if not self.online:
            raise RuntimeError(f"{self.node_id} is offline and cannot send messages")

        timestamp = self.tick()
        message = Message(
            sender=self.node_id,
            receiver=receiver.node_id,
            kind=kind,
            payload={**payload, "sender_clock": timestamp},
            message_id=f"{self.node_id}-{timestamp}-{receiver.node_id}",
        )
        receiver.inbox.append(message)
        return message

    def receive(self) -> list[Message]:
        messages = list(self.inbox)
        self.inbox.clear()

        for message in messages:
            remote_clock = int(message.payload.get("sender_clock", 0))
            self.logical_clock = max(self.logical_clock, remote_clock) + 1

        return messages


def demonstrate_basic_message_passing() -> None:
    heading("Basic Distributed Message Passing")

    orders = Node("orders")
    inventory = Node("inventory")

    message = orders.send(
        inventory,
        "reserve_stock",
        {"order_id": "ORD-1001", "sku": "LAPTOP-15", "quantity": 2},
    )

    print(f"Message: {message.kind}")
    print(f"From: {message.sender} -> {message.receiver}")
    print(f"Inventory clock before receive: {inventory.logical_clock}")

    received = inventory.receive()
    print(f"Messages processed: {len(received)}")
    print(f"Inventory clock after receive: {inventory.logical_clock}")


# ---------------------------------------------------------------------------
# Lamport logical clocks
# ---------------------------------------------------------------------------

@dataclass
class LamportNode:
    node_id: str
    clock: int = 0

    def local_event(self) -> int:
        self.clock += 1
        return self.clock

    def send_event(self) -> int:
        return self.local_event()

    def receive_event(self, remote_clock: int) -> int:
        self.clock = max(self.clock, remote_clock) + 1
        return self.clock


def demonstrate_lamport_clocks() -> None:
    heading("Lamport Logical Clocks")

    service_a = LamportNode("service-A")
    service_b = LamportNode("service-B")

    a1 = service_a.local_event()
    a2 = service_a.send_event()
    b1 = service_b.local_event()

    b2 = service_b.receive_event(a2)
    a3 = service_a.receive_event(b2)

    print(f"{service_a.node_id}: local={a1}, send={a2}, after-reply={a3}")
    print(f"{service_b.node_id}: local={b1}, receive={b2}")
    print("Lamport clocks provide a causal ordering signal, not physical time.")


# ---------------------------------------------------------------------------
# Vector clocks
# ---------------------------------------------------------------------------

class VectorClock:
    def __init__(self, node_ids: list[str]):
        self.clock = {node_id: 0 for node_id in node_ids}

    def copy(self) -> "VectorClock":
        result = VectorClock(list(self.clock))
        result.clock = dict(self.clock)
        return result

    def tick(self, node_id: str) -> None:
        self.clock[node_id] += 1

    def merge(self, other: "VectorClock") -> None:
        for node_id in self.clock:
            self.clock[node_id] = max(
                self.clock[node_id],
                other.clock.get(node_id, 0),
            )

    def happens_before(self, other: "VectorClock") -> bool:
        less_or_equal = all(
            self.clock[node_id] <= other.clock.get(node_id, 0)
            for node_id in self.clock
        )
        strictly_less = any(
            self.clock[node_id] < other.clock.get(node_id, 0)
            for node_id in self.clock
        )
        return less_or_equal and strictly_less

    def concurrent_with(self, other: "VectorClock") -> bool:
        return not self.happens_before(other) and not other.happens_before(self)

    def __repr__(self) -> str:
        return str(self.clock)


def demonstrate_vector_clocks() -> None:
    heading("Vector Clocks and Concurrent Updates")

    nodes = ["A", "B"]
    a = VectorClock(nodes)
    b = VectorClock(nodes)

    a.tick("A")
    update_a = a.copy()

    b.tick("B")
    update_b = b.copy()

    print(f"Update A: {update_a}")
    print(f"Update B: {update_b}")
    print(f"A happens before B: {update_a.happens_before(update_b)}")
    print(f"A and B concurrent: {update_a.concurrent_with(update_b)}")

    merged = update_a.copy()
    merged.merge(update_b)
    print(f"Merged causal state: {merged}")


# ---------------------------------------------------------------------------
# Failure detection and heartbeats
# ---------------------------------------------------------------------------

@dataclass
class FailureDetector:
    timeout_seconds: float = 5.0
    last_heartbeat: dict[str, float] = field(default_factory=dict)

    def heartbeat(self, node_id: str, now: float) -> None:
        self.last_heartbeat[node_id] = now

    def is_suspected(self, node_id: str, now: float) -> bool:
        last_seen = self.last_heartbeat.get(node_id)
        if last_seen is None:
            return True
        return now - last_seen > self.timeout_seconds


def demonstrate_failure_detection() -> None:
    heading("Failure Detection Through Heartbeats")

    detector = FailureDetector(timeout_seconds=5)
    detector.heartbeat("node-1", 100.0)

    print("At t=103:", detector.is_suspected("node-1", 103.0))
    print("At t=107:", detector.is_suspected("node-1", 107.0))

    print(
        "A timeout is evidence of suspected failure, not proof of failure. "
        "A slow network can look identical to a crashed node."
    )


# ---------------------------------------------------------------------------
# Leader election
# ---------------------------------------------------------------------------

class BullyElection:
    """
    Simplified Bully-style election.

    The highest-ID live node becomes leader. Real production systems need
    stronger coordination semantics than this educational model.
    """

    def __init__(self, node_ids: list[int]):
        self.nodes = {node_id: True for node_id in node_ids}
        self.leader: Optional[int] = None

    def fail(self, node_id: int) -> None:
        self.nodes[node_id] = False
        if self.leader == node_id:
            self.leader = None

    def recover(self, node_id: int) -> None:
        self.nodes[node_id] = True

    def elect(self) -> int:
        live_nodes = [node_id for node_id, live in self.nodes.items() if live]
        if not live_nodes:
            raise RuntimeError("Election failed: no live nodes")

        self.leader = max(live_nodes)
        return self.leader


def demonstrate_leader_election() -> None:
    heading("Leader Election")

    election = BullyElection([1, 2, 3, 4, 5])
    print("Initial leader:", election.elect())

    election.fail(5)
    print("Leader after node 5 fails:", election.elect())

    election.fail(4)
    print("Leader after node 4 fails:", election.elect())

    election.recover(5)
    print("Leader after node 5 recovers and election runs:", election.elect())


# ---------------------------------------------------------------------------
# Replicated key-value store
# ---------------------------------------------------------------------------

@dataclass
class VersionedValue:
    value: Any
    version: int
    writer: str


class Replica:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.online = True
        self.data: dict[str, VersionedValue] = {}

    def write(self, key: str, value: Any, version: int, writer: str) -> None:
        current = self.data.get(key)
        if current is None or version >= current.version:
            self.data[key] = VersionedValue(value, version, writer)

    def read(self, key: str) -> Optional[VersionedValue]:
        return self.data.get(key)


class QuorumStore:
    def __init__(self, replica_ids: list[str]):
        self.replicas = {node_id: Replica(node_id) for node_id in replica_ids}
        self.version = 0

    @property
    def quorum_size(self) -> int:
        return len(self.replicas) // 2 + 1

    def set_online(self, node_id: str, online: bool) -> None:
        self.replicas[node_id].online = online

    def write(self, key: str, value: Any, writer: str) -> dict[str, Any]:
        self.version += 1
        acknowledgements = 0

        for replica in self.replicas.values():
            if replica.online:
                replica.write(key, value, self.version, writer)
                acknowledgements += 1

        if acknowledgements < self.quorum_size:
            raise ConnectionError(
                f"Write quorum unavailable: {acknowledgements}/{self.quorum_size}"
            )

        return {
            "key": key,
            "version": self.version,
            "acknowledgements": acknowledgements,
        }

    def read(self, key: str) -> VersionedValue:
        responses = [
            replica.read(key)
            for replica in self.replicas.values()
            if replica.online and replica.read(key) is not None
        ]

        if len(responses) < self.quorum_size:
            raise ConnectionError(
                f"Read quorum unavailable: {len(responses)}/{self.quorum_size}"
            )

        latest = max(responses, key=lambda item: item.version)
        return latest


def demonstrate_quorum_replication() -> None:
    heading("Replication and Quorum Reads/Writes")

    store = QuorumStore(["replica-1", "replica-2", "replica-3"])

    result = store.write("customer:42", {"tier": "gold"}, "api-service")
    print("Write result:", result)

    print("Quorum read:", store.read("customer:42"))

    store.set_online("replica-3", False)
    print("Read with one replica unavailable:", store.read("customer:42"))

    store.set_online("replica-2", False)

    try:
        store.write("customer:42", {"tier": "platinum"}, "api-service")
    except ConnectionError as exc:
        print("Expected quorum failure:", exc)


# ---------------------------------------------------------------------------
# Idempotency and retry behavior
# ---------------------------------------------------------------------------

class PaymentService:
    def __init__(self):
        self.processed_requests: dict[str, str] = {}
        self.balance = 1000

    def charge(self, request_id: str, amount: int) -> str:
        if amount <= 0:
            raise ValueError("Charge amount must be positive")

        if request_id in self.processed_requests:
            return self.processed_requests[request_id]

        if amount > self.balance:
            raise ValueError("Insufficient funds")

        self.balance -= amount
        receipt = f"receipt-{request_id}"
        self.processed_requests[request_id] = receipt
        return receipt


def demonstrate_idempotent_retry() -> None:
    heading("Retries and Idempotency")

    payment = PaymentService()

    first = payment.charge("req-100", 250)
    retry = payment.charge("req-100", 250)

    print("First result:", first)
    print("Retry result:", retry)
    print("Remaining balance:", payment.balance)

    print(
        "The request identifier prevents a network retry from charging the "
        "same operation twice."
    )


# ---------------------------------------------------------------------------
# Consistent hashing
# ---------------------------------------------------------------------------

class ConsistentHashRing:
    def __init__(self, nodes: list[str], virtual_nodes: int = 20):
        if not nodes:
            raise ValueError("At least one node is required")
        if virtual_nodes <= 0:
            raise ValueError("virtual_nodes must be positive")

        self.virtual_nodes = virtual_nodes
        self.ring: dict[int, str] = {}

        for node in nodes:
            self.add_node(node)

    def add_node(self, node: str) -> None:
        for index in range(self.virtual_nodes):
            token = stable_hash(f"{node}#{index}")
            self.ring[token] = node

    def remove_node(self, node: str) -> None:
        self.ring = {
            token: owner
            for token, owner in self.ring.items()
            if owner != node
        }

        if not self.ring:
            raise RuntimeError("Cannot remove the final node")

    def owner(self, key: str) -> str:
        if not self.ring:
            raise RuntimeError("Hash ring is empty")

        token = stable_hash(key)
        candidates = [position for position in self.ring if position >= token]

        if candidates:
            selected = min(candidates)
        else:
            selected = min(self.ring)

        return self.ring[selected]


def demonstrate_consistent_hashing() -> None:
    heading("Consistent Hashing")

    ring = ConsistentHashRing(["cache-a", "cache-b", "cache-c"])

    keys = ["user:100", "user:101", "order:500", "order:501"]
    for key in keys:
        print(f"{key:12} -> {ring.owner(key)}")

    ring.add_node("cache-d")
    print("\nAfter adding cache-d:")
    for key in keys:
        print(f"{key:12} -> {ring.owner(key)}")


# ---------------------------------------------------------------------------
# Distributed request tracing
# ---------------------------------------------------------------------------

@dataclass
class TraceSpan:
    service: str
    operation: str
    trace_id: str
    parent_id: Optional[str]
    span_id: str
    duration_ms: float


class Tracer:
    def __init__(self):
        self.spans: list[TraceSpan] = []
        self.sequence = 0

    def span(
        self,
        service: str,
        operation: str,
        trace_id: str,
        parent_id: Optional[str],
        duration_ms: float,
    ) -> TraceSpan:
        self.sequence += 1
        result = TraceSpan(
            service=service,
            operation=operation,
            trace_id=trace_id,
            parent_id=parent_id,
            span_id=f"span-{self.sequence}",
            duration_ms=duration_ms,
        )
        self.spans.append(result)
        return result


def demonstrate_distributed_tracing() -> None:
    heading("Distributed Request Tracing")

    tracer = Tracer()
    trace_id = "trace-7f3a"

    gateway = tracer.span(
        "api-gateway", "POST /orders", trace_id, None, 8.5
    )
    order_service = tracer.span(
        "order-service", "create-order", trace_id, gateway.span_id, 18.2
    )
    inventory_service = tracer.span(
        "inventory-service", "reserve-stock", trace_id, order_service.span_id, 6.4
    )
    payment_service = tracer.span(
        "payment-service", "authorize", trace_id, order_service.span_id, 12.1
    )

    for span in tracer.spans:
        print(
            f"{span.span_id:8} {span.service:18} "
            f"parent={span.parent_id!s:8} duration={span.duration_ms:.1f}ms"
        )

    total = sum(span.duration_ms for span in tracer.spans)
    print(f"Recorded span-duration sum: {total:.1f}ms")


# ---------------------------------------------------------------------------
# Network partition simulation
# ---------------------------------------------------------------------------

class PartitionedCluster:
    def __init__(self, node_ids: list[str]):
        self.nodes = set(node_ids)
        self.links: set[frozenset[str]] = set()

        for left in node_ids:
            for right in node_ids:
                if left != right:
                    self.links.add(frozenset((left, right)))

    def partition(self, left_group: set[str], right_group: set[str]) -> None:
        for left in left_group:
            for right in right_group:
                self.links.discard(frozenset((left, right)))

    def can_communicate(self, left: str, right: str) -> bool:
        return frozenset((left, right)) in self.links


def demonstrate_partition() -> None:
    heading("Network Partition")

    cluster = PartitionedCluster(["A", "B", "C", "D"])
    print("A -> B:", cluster.can_communicate("A", "B"))

    cluster.partition({"A", "B"}, {"C", "D"})

    print("A -> B after partition:", cluster.can_communicate("A", "B"))
    print("A -> C after partition:", cluster.can_communicate("A", "C"))
    print("C -> D after partition:", cluster.can_communicate("C", "D"))

    print(
        "The partition separates communication paths. A production consensus "
        "system must define which side may continue safely."
    )


# ---------------------------------------------------------------------------
# Mini distributed order service
# ---------------------------------------------------------------------------

@dataclass
class Order:
    order_id: str
    customer_id: str
    amount: float
    status: str = "PENDING"


class DistributedOrderService:
    """
    Combines several fundamentals:
    - leader selection
    - replicated order state
    - idempotent request handling
    - failure-aware writes
    """

    def __init__(self):
        self.leader_election = BullyElection([1, 2, 3])
        self.leader = self.leader_election.elect()
        self.replicas = {
            1: {},
            2: {},
            3: {},
        }
        self.completed_requests: set[str] = set()
        self.sequence = 0

    def fail_leader(self) -> None:
        self.leader_election.fail(self.leader)
        self.leader = self.leader_election.elect()

    def create_order(
        self,
        request_id: str,
        customer_id: str,
        amount: float,
    ) -> Order:
        if request_id in self.completed_requests:
            for replica in self.replicas.values():
                for order in replica.values():
                    if order.order_id == request_id:
                        return order
            raise RuntimeError("Idempotency record exists without order state")

        if amount <= 0:
            raise ValueError("Order amount must be positive")

        self.sequence += 1
        order = Order(
            order_id=request_id,
            customer_id=customer_id,
            amount=amount,
            status="CONFIRMED",
        )

        acknowledgements = 0
        for node_id, replica in self.replicas.items():
            if self.leader_election.nodes[node_id]:
                replica[order.order_id] = order
                acknowledgements += 1

        quorum = len(self.replicas) // 2 + 1
        if acknowledgements < quorum:
            raise ConnectionError("Order replication quorum was not reached")

        self.completed_requests.add(request_id)
        return order


def demonstrate_integrated_service() -> None:
    heading("Integrated Distributed Order Service")

    service = DistributedOrderService()

    order = service.create_order("ORD-9001", "CUST-77", 1499.00)
    print("Leader:", service.leader)
    print("Created:", order)

    duplicate = service.create_order("ORD-9001", "CUST-77", 1499.00)
    print("Idempotent retry:", duplicate)

    service.fail_leader()
    print("New leader after failure:", service.leader)

    second = service.create_order("ORD-9002", "CUST-77", 399.00)
    print("Created after leader failover:", second)


# ---------------------------------------------------------------------------
# Operational metrics
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    requests: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0

    def record(self, success: bool, latency_ms: float) -> None:
        self.requests += 1
        self.total_latency_ms += latency_ms
        if success:
            self.successes += 1
        else:
            self.failures += 1

    def report(self) -> dict[str, float]:
        average = (
            self.total_latency_ms / self.requests
            if self.requests
            else 0.0
        )
        availability = (
            self.successes / self.requests
            if self.requests
            else 0.0
        )
        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "average_latency_ms": round(average, 2),
            "success_ratio": round(availability, 4),
        }


def demonstrate_metrics() -> None:
    heading("Distributed Service Metrics")

    metrics = Metrics()
    samples = [
        (True, 12.0),
        (True, 18.0),
        (False, 70.0),
        (True, 21.0),
        (True, 14.0),
    ]

    for success, latency in samples:
        metrics.record(success, latency)

    print(metrics.report())


# ---------------------------------------------------------------------------
# Production-oriented validation
# ---------------------------------------------------------------------------

def validate_distributed_configuration(
    node_count: int,
    replication_factor: int,
    write_quorum: int,
    read_quorum: int,
) -> None:
    if node_count < 1:
        raise ValueError("node_count must be positive")

    if replication_factor < 1 or replication_factor > node_count:
        raise ValueError(
            "replication_factor must be between 1 and node_count"
        )

    if not 1 <= write_quorum <= replication_factor:
        raise ValueError("write_quorum must be within replication factor")

    if not 1 <= read_quorum <= replication_factor:
        raise ValueError("read_quorum must be within replication factor")


def demonstrate_configuration_validation() -> None:
    heading("Configuration Validation")

    validate_distributed_configuration(
        node_count=5,
        replication_factor=3,
        write_quorum=2,
        read_quorum=2,
    )

    print("Valid configuration accepted.")

    try:
        validate_distributed_configuration(
            node_count=3,
            replication_factor=4,
            write_quorum=2,
            read_quorum=2,
        )
    except ValueError as exc:
        print("Invalid configuration rejected:", exc)


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("Distributed Systems Fundamentals")
    print("Executable in-memory simulations of core distributed mechanisms.")

    demonstrate_basic_message_passing()
    demonstrate_lamport_clocks()
    demonstrate_vector_clocks()
    demonstrate_failure_detection()
    demonstrate_leader_election()
    demonstrate_quorum_replication()
    demonstrate_idempotent_retry()
    demonstrate_consistent_hashing()
    demonstrate_distributed_tracing()
    demonstrate_partition()
    demonstrate_integrated_service()
    demonstrate_metrics()
    demonstrate_configuration_validation()

    heading("Key Engineering Properties")
    print("• Partial failure: one component can fail while others remain alive.")
    print("• No shared global clock: logical clocks help reason about ordering.")
    print("• Network uncertainty: timeout means suspicion, not certainty.")
    print("• Replication: multiple copies improve availability but create consistency concerns.")
    print("• Quorums: read/write thresholds can balance availability and consistency.")
    print("• Idempotency: retries can be made safe for operations that may be delivered twice.")
    print("• Partition tolerance: communication failures must be handled explicitly.")
    print("• Observability: traces and metrics are necessary to diagnose distributed behavior.")


if __name__ == "__main__":
    main()
