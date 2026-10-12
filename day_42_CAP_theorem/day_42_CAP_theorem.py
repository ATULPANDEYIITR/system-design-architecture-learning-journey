from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
import random
import time


class CAPChoice(Enum):
    CP = "Consistency + Partition Tolerance"
    AP = "Availability + Partition Tolerance"


@dataclass
class Node:
    node_id: str
    region: str
    up: bool = True
    data: Dict[str, Tuple[int, str]] = field(default_factory=dict)
    logical_clock: int = 0

    def write(self, key: str, value: str) -> None:
        self.logical_clock += 1
        self.data[key] = (self.logical_clock, value)

    def read(self, key: str) -> Optional[str]:
        record = self.data.get(key)
        return record[1] if record else None


@dataclass
class WriteResult:
    committed: bool
    acknowledged_nodes: List[str]
    reason: str


@dataclass
class ReadResult:
    value: Optional[str]
    source_nodes: List[str]
    consistent: bool
    reason: str


class DistributedKVStore:
    """
    A small CAP-theorem simulator.

    The simulator models:
    - multiple replicas
    - network partitions
    - quorum-based CP writes
    - AP writes that accept locally available replicas
    - quorum reads
    - stale replicas
    - reconciliation after a partition heals

    This is intentionally a model of distributed-system behavior, not a
    production database.
    """

    def __init__(self, nodes: List[Node], mode: CAPChoice) -> None:
        if not nodes:
            raise ValueError("At least one node is required.")
        self.nodes = {node.node_id: node for node in nodes}
        self.mode = mode
        self.partition_groups: List[Set[str]] = [set(self.nodes)]
        self.network_latency_ms = 10

    def set_partition(self, groups: List[Set[str]]) -> None:
        all_nodes = set(self.nodes)
        flattened = set().union(*groups) if groups else set()

        if flattened != all_nodes:
            raise ValueError("Partition groups must contain every node exactly once.")

        if any(not group for group in groups):
            raise ValueError("Partition groups cannot be empty.")

        self.partition_groups = groups

    def heal_partition(self) -> None:
        self.partition_groups = [set(self.nodes)]

    def _same_partition(self, node_a: str, node_b: str) -> bool:
        return any(
            node_a in group and node_b in group
            for group in self.partition_groups
        )

    def _available_replicas(self, coordinator: str) -> List[Node]:
        coordinator_node = self.nodes[coordinator]

        return [
            node
            for node in self.nodes.values()
            if node.up
            and self._same_partition(coordinator, node.node_id)
        ]

    def write(
        self,
        coordinator: str,
        key: str,
        value: str,
        replication_factor: Optional[int] = None,
    ) -> WriteResult:
        if coordinator not in self.nodes:
            return WriteResult(False, [], "Unknown coordinator.")

        if not key:
            return WriteResult(False, [], "Key cannot be empty.")

        available = self._available_replicas(coordinator)
        if not available:
            return WriteResult(False, [], "No reachable replica is available.")

        rf = replication_factor or len(self.nodes)
        rf = min(rf, len(self.nodes))

        quorum = rf // 2 + 1
        acknowledged: List[str] = []

        if self.mode == CAPChoice.CP:
            if len(available) < quorum:
                return WriteResult(
                    False,
                    [],
                    (
                        f"CP write rejected: reachable replicas={len(available)}, "
                        f"required quorum={quorum}."
                    ),
                )

            for node in available[:rf]:
                node.write(key, value)
                acknowledged.append(node.node_id)

            return WriteResult(
                True,
                acknowledged,
                "CP write committed after satisfying the replica quorum.",
            )

        # AP mode deliberately favors accepting writes on the reachable side.
        # This means different partitions can independently accept conflicting
        # values, which demonstrates why availability during a partition can
        # require eventual rather than immediate consistency.
        target_count = min(rf, len(available))

        for node in available[:target_count]:
            node.write(key, value)
            acknowledged.append(node.node_id)

        return WriteResult(
            True,
            acknowledged,
            (
                "AP write accepted by reachable replicas. "
                "Other replicas may be stale until reconciliation."
            ),
        )

    def read(
        self,
        coordinator: str,
        key: str,
        require_quorum: bool = True,
    ) -> ReadResult:
        if coordinator not in self.nodes:
            return ReadResult(None, [], False, "Unknown coordinator.")

        available = self._available_replicas(coordinator)

        if not available:
            return ReadResult(None, [], False, "No reachable replica is available.")

        values: List[Tuple[str, Optional[str], int]] = []

        for node in available:
            record = node.data.get(key)
            if record:
                version, value = record
                values.append((node.node_id, value, version))

        if not values:
            return ReadResult(None, [n.node_id for n in available], True, "Key not found.")

        if require_quorum:
            quorum = len(self.nodes) // 2 + 1

            if len(available) < quorum:
                return ReadResult(
                    None,
                    [n.node_id for n in available],
                    False,
                    (
                        f"Quorum read unavailable: reachable replicas="
                        f"{len(available)}, required={quorum}."
                    ),
                )

        newest = max(values, key=lambda item: item[2])

        consistent = len({version for _, _, version in values}) == 1

        return ReadResult(
            newest[1],
            [node_id for node_id, _, _ in values],
            consistent,
            (
                "All participating replicas agree."
                if consistent
                else "Replicas disagree; newest logical version selected."
            ),
        )

    def reconcile(self, key: str) -> Optional[str]:
        """
        Last-write-wins reconciliation using the highest logical version.

        Real distributed databases may use timestamps, vector clocks,
        hybrid logical clocks, CRDTs, application-defined conflict
        resolution, or consensus protocols instead.
        """
        records = []

        for node in self.nodes.values():
            if key in node.data:
                version, value = node.data[key]
                records.append((version, node.node_id, value))

        if not records:
            return None

        winning_version, _, winning_value = max(records)

        for node in self.nodes.values():
            node.data[key] = (winning_version, winning_value)

        return winning_value

    def topology(self) -> Dict[str, Dict[str, object]]:
        return {
            node.node_id: {
                "region": node.region,
                "up": node.up,
                "keys": dict(node.data),
            }
            for node in self.nodes.values()
        }


def demonstrate_cap_relationship() -> None:
    print("\n=== CAP THEOREM: THREE PROPERTIES ===")
    print("Consistency: every successful read observes the same logical value.")
    print("Availability: every request to a non-failed node receives a response.")
    print("Partition tolerance: the system continues operating despite network splits.")
    print(
        "\nWhen a partition occurs, a distributed system cannot guarantee both "
        "strong consistency and availability across the separated sides."
    )


def demonstrate_cp_partition() -> None:
    print("\n=== CP SYSTEM DURING A PARTITION ===")

    nodes = [
        Node("node-a", "Delhi"),
        Node("node-b", "Mumbai"),
        Node("node-c", "Bengaluru"),
    ]

    store = DistributedKVStore(nodes, CAPChoice.CP)

    initial = store.write("node-a", "account:42", "balance=1000")
    print("Initial write:", initial)

    store.set_partition([
        {"node-a"},
        {"node-b", "node-c"},
    ])

    rejected = store.write("node-a", "account:42", "balance=700")
    print("Partitioned write:", rejected)

    read = store.read("node-a", "account:42")
    print("Partitioned read:", read)

    print(
        "\nThe isolated node refuses the write because it cannot establish "
        "the required quorum. The system sacrifices availability to preserve "
        "the consistency guarantee."
    )


def demonstrate_ap_partition() -> None:
    print("\n=== AP SYSTEM DURING A PARTITION ===")

    nodes = [
        Node("node-a", "Delhi"),
        Node("node-b", "Mumbai"),
        Node("node-c", "Bengaluru"),
    ]

    store = DistributedKVStore(nodes, CAPChoice.AP)

    store.write("node-a", "order:9001", "status=created")

    store.set_partition([
        {"node-a"},
        {"node-b", "node-c"},
    ])

    first = store.write("node-a", "order:9001", "status=cancelled")
    second = store.write("node-b", "order:9001", "status=shipped")

    print("Delhi partition:", first)
    print("Mumbai/Bengaluru partition:", second)

    print("\nReplica state before healing:")
    for node_id, state in store.topology().items():
        print(node_id, state)

    store.heal_partition()
    winning_value = store.reconcile("order:9001")

    print("\nAfter partition healing:")
    print("Reconciled value:", winning_value)

    for node_id, state in store.topology().items():
        print(node_id, state)


def demonstrate_quorum_math() -> None:
    print("\n=== QUORUM MATH ===")

    for replica_count in [3, 5, 7]:
        write_quorum = replica_count // 2 + 1
        print(
            f"replicas={replica_count}, "
            f"majority quorum={write_quorum}, "
            f"tolerated unavailable replicas={replica_count - write_quorum}"
        )


def demonstrate_edge_cases() -> None:
    print("\n=== EDGE CASES AND FAILURE CONDITIONS ===")

    nodes = [
        Node("node-a", "Delhi"),
        Node("node-b", "Mumbai"),
        Node("node-c", "Bengaluru"),
    ]

    store = DistributedKVStore(nodes, CAPChoice.CP)

    print(store.write("node-a", "", "invalid"))
    print(store.write("unknown", "key", "value"))

    nodes[0].up = False
    nodes[1].up = False

    print(
        store.write(
            "node-c",
            "service:status",
            "healthy",
        )
    )

    print(store.read("node-c", "service:status"))

    try:
        store.set_partition([
            {"node-a"},
            {"node-b"},
        ])
    except ValueError as exc:
        print("Partition validation error:", exc)


def demonstrate_performance_and_design_tradeoffs() -> None:
    print("\n=== PERFORMANCE AND DESIGN TRADE-OFFS ===")

    print(
        "Strongly consistent quorum operations usually require coordination "
        "among multiple replicas, increasing network latency."
    )
    print(
        "AP systems can acknowledge locally during a partition, reducing "
        "availability latency but shifting complexity into conflict resolution."
    )
    print(
        "Increasing replication improves failure tolerance but increases "
        "storage, network traffic, repair work, and coordination cost."
    )
    print(
        "A CAP classification describes behavior under partition, not every "
        "performance characteristic of a database."
    )


def demonstrate_realistic_scenario() -> None:
    print("\n=== REALISTIC REPOSITORY GOVERNANCE EXAMPLE ===")

    repositories = {
        "payments-api": {
            "branch": "main",
            "requires_ci": True,
            "required_approvals": 2,
        },
        "inventory-service": {
            "branch": "main",
            "requires_ci": True,
            "required_approvals": 1,
        },
    }

    print(
        "A distributed deployment platform might keep repository governance "
        "metadata in multiple regions."
    )
    print(
        "If a network partition prevents a region from confirming the current "
        "policy, a CP design can reject a governance decision rather than risk "
        "using divergent policy state."
    )
    print(
        "An AP design may allow a regional controller to continue operating, "
        "but policy conflicts must be reconciled after connectivity returns."
    )

    for repository, policy in repositories.items():
        print(repository, policy)


def main() -> None:
    random.seed(42)
    start = time.perf_counter()

    demonstrate_cap_relationship()
    demonstrate_quorum_math()
    demonstrate_cp_partition()
    demonstrate_ap_partition()
    demonstrate_edge_cases()
    demonstrate_performance_and_design_tradeoffs()
    demonstrate_realistic_scenario()

    elapsed = time.perf_counter() - start
    print(f"\nSimulation completed in {elapsed:.6f} seconds.")


if __name__ == "__main__":
    main()
