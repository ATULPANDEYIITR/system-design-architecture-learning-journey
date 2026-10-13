#!/usr/bin/env python3
"""
Consistency Models: Strong, Eventual, and Causal Consistency

A self-contained distributed key-value store simulator.

Demonstrates:
- Linearizable reads and writes through a single authoritative leader.
- Eventual consistency through asynchronous replica propagation.
- Causal consistency through version vectors and causal dependencies.
- Replica lag, concurrent writes, stale reads, partitions, retries, and recovery.
- Deterministic demonstrations and executable assertions.

Run:
    python consistency_models.py
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Iterable
import json
import time


class ConsistencyModel(Enum):
    STRONG = "strong"
    EVENTUAL = "eventual"
    CAUSAL = "causal"


class ConsistencyError(Exception):
    """Base exception for consistency-related failures."""


class QuorumUnavailable(ConsistencyError):
    """Raised when the required replicas cannot respond."""


class CausalDependencyMissing(ConsistencyError):
    """Raised when an operation's causal dependencies are unavailable."""


class VersionConflict(ConsistencyError):
    """Raised when a write attempts to reuse an operation identifier."""


@dataclass(frozen=True)
class VersionVector:
    """
    A version vector records the number of causally observed events
    produced by each replica.

    If A <= B componentwise, every event represented by A is included
    in B's causal history.
    """

    counters: tuple[tuple[str, int], ...] = ()

    @classmethod
    def from_dict(cls, counters: dict[str, int]) -> "VersionVector":
        return cls(tuple(sorted(
            (replica, counter)
            for replica, counter in counters.items()
            if counter > 0
        )))

    def as_dict(self) -> dict[str, int]:
        return dict(self.counters)

    def get(self, replica: str) -> int:
        return dict(self.counters).get(replica, 0)

    def merge(self, other: "VersionVector") -> "VersionVector":
        left = self.as_dict()
        right = other.as_dict()
        replicas = left.keys() | right.keys()
        return VersionVector.from_dict({
            replica: max(left.get(replica, 0), right.get(replica, 0))
            for replica in replicas
        })

    def dominates_or_equals(self, other: "VersionVector") -> bool:
        return all(self.get(replica) >= counter
                   for replica, counter in other.counters)

    def strictly_dominates(self, other: "VersionVector") -> bool:
        return (
            self.dominates_or_equals(other)
            and self != other
        )

    def increment(self, replica: str) -> "VersionVector":
        updated = self.as_dict()
        updated[replica] = updated.get(replica, 0) + 1
        return VersionVector.from_dict(updated)

    def concurrent_with(self, other: "VersionVector") -> bool:
        return (
            not self.dominates_or_equals(other)
            and not other.dominates_or_equals(self)
        )


@dataclass(frozen=True)
class Operation:
    operation_id: str
    key: str
    value: Any
    replica_id: str
    version: int
    vector: VersionVector
    dependencies: VersionVector
    timestamp: float
    tombstone: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "key": self.key,
            "value": self.value,
            "replica_id": self.replica_id,
            "version": self.version,
            "vector": self.vector.as_dict(),
            "dependencies": self.dependencies.as_dict(),
            "tombstone": self.tombstone,
        }


@dataclass
class Replica:
    replica_id: str
    data: dict[str, Operation] = field(default_factory=dict)
    causal_context: VersionVector = field(default_factory=VersionVector)
    applied_operations: set[str] = field(default_factory=set)
    available: bool = True

    def read(self, key: str) -> Any:
        operation = self.data.get(key)
        if operation is None or operation.tombstone:
            return None
        return operation.value

    def read_operation(self, key: str) -> Operation | None:
        return self.data.get(key)


def resolve_register_conflict(
    current: Operation | None,
    incoming: Operation,
) -> Operation:
    """
    Resolve concurrent writes deterministically for a last-writer-wins
    register.

    This policy provides convergence, not preservation of every update.
    Applications that cannot discard concurrent values should use a
    multi-value register or a domain-specific merge function.
    """
    if current is None:
        return incoming

    if incoming.vector.strictly_dominates(current.vector):
        return incoming

    if current.vector.strictly_dominates(incoming.vector):
        return current

    if incoming.vector == current.vector:
        return max(
            (current, incoming),
            key=lambda op: (op.timestamp, op.replica_id, op.operation_id),
        )

    if incoming.vector.concurrent_with(current.vector):
        return max(
            (current, incoming),
            key=lambda op: (op.timestamp, op.replica_id, op.operation_id),
        )

    return current


class DistributedStore:
    """
    Deterministic simulator for three consistency models.

    Strong consistency uses one authoritative leader and rejects writes
    when the leader or a required acknowledgment is unavailable.

    Eventual consistency permits local writes and explicitly queued
    propagation messages.

    Causal consistency permits writes whose declared dependencies are
    present and delays remote operations until their dependencies exist.
    """

    def __init__(
        self,
        model: ConsistencyModel,
        replica_ids: Iterable[str] = ("A", "B", "C"),
        leader_id: str = "A",
        required_acks: int | None = None,
    ) -> None:
        ids = tuple(replica_ids)
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Replica identifiers must be unique and nonempty.")
        if leader_id not in ids:
            raise ValueError("Leader must be one of the configured replicas.")

        self.model = model
        self.replicas = {replica_id: Replica(replica_id) for replica_id in ids}
        self.leader_id = leader_id
        self.required_acks = required_acks or len(ids)
        if not 1 <= self.required_acks <= len(ids):
            raise ValueError("required_acks must be between 1 and replica count.")

        self.pending_messages: Deque[Operation] = deque()
        self.operation_registry: dict[str, Operation] = {}
        self.replica_sequences: dict[str, int] = defaultdict(int)
        self.logical_clock = 0

    def set_available(self, replica_id: str, available: bool) -> None:
        self.replicas[replica_id].available = available

    def _next_timestamp(self) -> float:
        self.logical_clock += 1
        return float(self.logical_clock)

    def _make_operation(
        self,
        replica_id: str,
        key: str,
        value: Any,
        dependencies: VersionVector,
        operation_id: str,
        tombstone: bool = False,
    ) -> Operation:
        if not key:
            raise ValueError("Keys must be nonempty.")
        if not operation_id:
            raise ValueError("Operation identifiers must be nonempty.")

        existing = self.operation_registry.get(operation_id)
        if existing is not None:
            if (
                existing.key == key
                and existing.value == value
                and existing.replica_id == replica_id
                and existing.dependencies == dependencies
                and existing.tombstone == tombstone
            ):
                return existing
            raise VersionConflict(
                f"Operation ID {operation_id!r} was reused with different data."
            )

        self.replica_sequences[replica_id] += 1
        base_vector = self.replicas[replica_id].causal_context.merge(dependencies)
        vector = base_vector.increment(replica_id)

        operation = Operation(
            operation_id=operation_id,
            key=key,
            value=value,
            replica_id=replica_id,
            version=self.replica_sequences[replica_id],
            vector=vector,
            dependencies=dependencies,
            timestamp=self._next_timestamp(),
            tombstone=tombstone,
        )
        self.operation_registry[operation_id] = operation
        return operation

    def _apply(self, replica: Replica, operation: Operation) -> bool:
        if operation.operation_id in replica.applied_operations:
            return False

        if self.model == ConsistencyModel.CAUSAL:
            if not replica.causal_context.dominates_or_equals(
                operation.dependencies
            ):
                raise CausalDependencyMissing(
                    f"Replica {replica.replica_id} lacks dependencies for "
                    f"{operation.operation_id}."
                )

        current = replica.data.get(operation.key)
        replica.data[operation.key] = resolve_register_conflict(
            current, operation
        )
        replica.applied_operations.add(operation.operation_id)
        replica.causal_context = replica.causal_context.merge(operation.vector)
        return True

    def write(
        self,
        replica_id: str,
        key: str,
        value: Any,
        operation_id: str,
        dependencies: VersionVector | None = None,
        tombstone: bool = False,
    ) -> Operation:
        """
        Commit a write according to the configured consistency model.

        A retry using the same operation ID is idempotent. A reused ID
        with different content is rejected.
        """
        if replica_id not in self.replicas:
            raise ValueError(f"Unknown replica: {replica_id}")

        replica = self.replicas[replica_id]
        if not replica.available:
            raise QuorumUnavailable(f"Replica {replica_id} is unavailable.")

        dependencies = dependencies or VersionVector()

        if self.model == ConsistencyModel.STRONG:
            leader = self.replicas[self.leader_id]
            if not leader.available:
                raise QuorumUnavailable("The authoritative leader is unavailable.")

            active_count = sum(r.available for r in self.replicas.values())
            if active_count < self.required_acks:
                raise QuorumUnavailable(
                    f"Need {self.required_acks} acknowledgments; "
                    f"only {active_count} replicas are available."
                )

            operation = self._make_operation(
                self.leader_id, key, value, dependencies, operation_id, tombstone
            )

            # The leader serializes writes. In this simulator, all required
            # acknowledgments are applied atomically before success is returned.
            # Real systems must use a consensus protocol to provide this guarantee.
            available_replicas = [
                r for r in self.replicas.values() if r.available
            ]
            for target in available_replicas:
                self._apply(target, operation)

            return operation

        operation = self._make_operation(
            replica_id, key, value, dependencies, operation_id, tombstone
        )
        self._apply(replica, operation)

        # Local commit is independent of remote delivery. Messages may be
        # delivered later, duplicated, or temporarily blocked by partitions.
        self.pending_messages.append(operation)
        return operation

    def read(
        self,
        replica_id: str,
        key: str,
        minimum_context: VersionVector | None = None,
    ) -> Any:
        if replica_id not in self.replicas:
            raise ValueError(f"Unknown replica: {replica_id}")

        replica = self.replicas[replica_id]
        if not replica.available:
            raise QuorumUnavailable(f"Replica {replica_id} is unavailable.")

        if self.model == ConsistencyModel.STRONG:
            leader = self.replicas[self.leader_id]
            if not leader.available:
                raise QuorumUnavailable("The authoritative leader is unavailable.")
            # A strong read always consults the authoritative state.
            operation = leader.read_operation(key)
            return None if operation is None or operation.tombstone else operation.value

        if minimum_context is not None:
            if not replica.causal_context.dominates_or_equals(minimum_context):
                raise CausalDependencyMissing(
                    f"Replica {replica_id} has not observed the requested context."
                )

        return replica.read(key)

    def replicate_one(self, message_index: int = 0) -> bool:
        """Deliver one queued message to currently available replicas."""
        if not self.pending_messages:
            return False
        if not 0 <= message_index < len(self.pending_messages):
            raise IndexError("Message index is outside the pending queue.")

        message = self.pending_messages[message_index]
        del self.pending_messages[message_index]

        deferred = False
        for replica in self.replicas.values():
            if not replica.available or message.operation_id in replica.applied_operations:
                continue
            try:
                self._apply(replica, message)
            except CausalDependencyMissing:
                deferred = True

        if deferred:
            self.pending_messages.append(message)
        return True

    def drain_replication(self, max_steps: int = 1000) -> int:
        """
        Deliver messages until convergence or a safety limit is reached.

        Causal messages may need multiple passes because a dependent operation
        can arrive before its prerequisite.
        """
        steps = 0
        while self.pending_messages and steps < max_steps:
            before = len(self.pending_messages)
            self.replicate_one(0)
            steps += 1
            if len(self.pending_messages) == before:
                # Try other queued messages before concluding no progress.
                progressed = False
                for index in range(1, len(self.pending_messages)):
                    message = self.pending_messages[index]
                    if any(
                        replica.available
                        and replica.causal_context.dominates_or_equals(
                            message.dependencies
                        )
                        for replica in self.replicas.values()
                    ):
                        self.replicate_one(index)
                        progressed = True
                        break
                if not progressed:
                    break
        return steps

    def converge(self) -> None:
        """
        Anti-entropy repair for the simulator.

        Real deployments need durable logs, snapshots, membership management,
        tombstone retention, and conflict-resolution protocols.
        """
        operations = sorted(
            self.operation_registry.values(),
            key=lambda operation: (
                sum(counter for _, counter in operation.vector.counters),
                operation.timestamp,
                operation.operation_id,
            ),
        )

        made_progress = True
        while made_progress:
            made_progress = False
            for operation in operations:
                for replica in self.replicas.values():
                    if not replica.available:
                        continue
                    if operation.operation_id in replica.applied_operations:
                        continue
                    try:
                        self._apply(replica, operation)
                        made_progress = True
                    except CausalDependencyMissing:
                        continue

        # Remove messages that are already known to all available replicas.
        self.pending_messages = deque(
            operation for operation in self.pending_messages
            if any(
                replica.available
                and operation.operation_id not in replica.applied_operations
                for replica in self.replicas.values()
            )
        )

    def snapshot(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for replica_id, replica in self.replicas.items():
            result[replica_id] = {
                key: {
                    "value": operation.value,
                    "vector": operation.vector.as_dict(),
                    "deleted": operation.tombstone,
                }
                for key, operation in sorted(replica.data.items())
            }
        return result

    def describe(self) -> None:
        print(json.dumps(self.snapshot(), indent=2, default=str))


def demonstrate_strong_consistency() -> None:
    print("\n=== Strong consistency ===")
    store = DistributedStore(ConsistencyModel.STRONG)

    store.write("A", "inventory:router-17", 12, "strong-001")
    print("Read from B after acknowledged write:",
          store.read("B", "inventory:router-17"))

    store.set_available("C", False)
    store.write("A", "inventory:router-17", 11, "strong-002")
    print("Read from C while unavailable is rejected.")
    try:
        store.read("C", "inventory:router-17")
    except QuorumUnavailable as error:
        print(type(error).__name__, error)

    store.set_available("C", True)
    store.converge()
    print("Final authoritative value:",
          store.read("B", "inventory:router-17"))


def demonstrate_eventual_consistency() -> None:
    print("\n=== Eventual consistency ===")
    store = DistributedStore(ConsistencyModel.EVENTUAL)

    store.write("A", "service:maintenance-window", "02:00", "event-001")
    print("Immediately after local write:")
    print("A =", store.read("A", "service:maintenance-window"))
    print("B =", store.read("B", "service:maintenance-window"))

    store.drain_replication()
    print("After replication:")
    print("A =", store.read("A", "service:maintenance-window"))
    print("B =", store.read("B", "service:maintenance-window"))
    print("C =", store.read("C", "service:maintenance-window"))

    # Concurrent updates illustrate that convergence and preservation of
    # every write are different properties.
    store.write("A", "profile:theme", "dark", "event-002")
    store.write("B", "profile:theme", "light", "event-003")
    store.drain_replication()
    print("Resolved concurrent value:",
          store.read("A", "profile:theme"))
    print("All replicas converge to the same resolved value:")
    print(json.dumps(store.snapshot(), indent=2))


def demonstrate_causal_consistency() -> None:
    print("\n=== Causal consistency ===")
    store = DistributedStore(ConsistencyModel.CAUSAL)

    parent = store.write(
        "A", "incident:INC-804", "opened", "causal-001"
    )
    child = store.write(
        "A",
        "incident:INC-804:status",
        "assigned",
        "causal-002",
        dependencies=parent.vector,
    )

    # Deliver the dependent operation before the prerequisite.
    store.replicate_one(1)
    print("Dependent event is deferred when its prerequisite is missing.")
    print("Pending messages:", len(store.pending_messages))

    store.drain_replication()
    print("After causal delivery:")
    print("B incident =", store.read("B", "incident:INC-804"))
    print("B status =", store.read("B", "incident:INC-804:status"))

    # A client that has observed the child operation can carry its causal
    # context to another replica to prevent a read from going behind it.
    try:
        store.read("C", "incident:INC-804:status", child.vector)
        print("Replica C has observed the required causal context.")
    except CausalDependencyMissing:
        print("Replica C has not yet observed the required causal context.")

    print("Version vector:", child.vector.as_dict())


def demonstrate_edge_cases() -> None:
    print("\n=== Validation, deletion, and idempotency ===")
    store = DistributedStore(ConsistencyModel.EVENTUAL)

    operation = store.write("A", "ticket:105", "open", "edge-001")
    retry = store.write("A", "ticket:105", "open", "edge-001")
    assert operation == retry

    try:
        store.write("A", "ticket:105", "closed", "edge-001")
    except VersionConflict as error:
        print("Conflicting retry rejected:", error)

    store.write(
        "A",
        "ticket:105",
        None,
        "edge-002",
        dependencies=operation.vector,
        tombstone=True,
    )
    store.drain_replication()
    assert store.read("B", "ticket:105") is None
    print("Tombstone replicated; ticket is logically deleted.")

    try:
        store.write("A", "", "invalid", "edge-003")
    except ValueError as error:
        print("Invalid key rejected:", error)

    vector_a = VersionVector.from_dict({"A": 2, "B": 1})
    vector_b = VersionVector.from_dict({"A": 1, "B": 2})
    assert vector_a.concurrent_with(vector_b)
    print("Concurrent version vectors detected.")


def compare_models() -> None:
    print("\n=== Model comparison ===")
    rows = [
        ("Strong", "Latest committed authoritative state",
         "Higher coordination cost", "Cross-replica invariants"),
        ("Eventual", "Local replica state may be stale",
         "Low-latency local writes", "Caches and replicated read models"),
        ("Causal", "Includes observed causal predecessors",
         "Dependency tracking and buffering", "Collaborative workflows"),
    ]

    for name, read_behavior, tradeoff, example in rows:
        print(f"{name}:")
        print(f"  Read behavior: {read_behavior}")
        print(f"  Trade-off: {tradeoff}")
        print(f"  Example: {example}")


def main() -> None:
    demonstrate_strong_consistency()
    demonstrate_eventual_consistency()
    demonstrate_causal_consistency()
    demonstrate_edge_cases()
    compare_models()
    print("\nAll consistency demonstrations completed.")


if __name__ == "__main__":
    main()
