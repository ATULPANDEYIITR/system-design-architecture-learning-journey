#!/usr/bin/env python3
"""
Consistent hashing demonstration.

This executable module builds a hash ring, places physical nodes and virtual
nodes on the ring, routes keys to owners, measures distribution, and compares
consistent hashing with ordinary modulo partitioning when nodes are added or
removed.

The implementation uses only Python's standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from statistics import mean, pstdev
from typing import Iterable


RING_SIZE = 2**64


def stable_hash(value: str) -> int:
    """Map a string deterministically into the unsigned 64-bit hash space."""
    digest = sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


@dataclass(frozen=True)
class VirtualNode:
    """One point owned by a physical node on the hash ring."""

    position: int
    physical_node: str
    replica_index: int


@dataclass
class ConsistentHashRing:
    """
    Hash ring supporting physical nodes and virtual nodes.

    A key is hashed to a position. Ownership is determined by the first
    virtual-node position at or clockwise after that position. If the search
    reaches the end of the ring, ownership wraps to position zero.
    """

    virtual_nodes_per_node: int = 128
    _ring: list[VirtualNode] = field(default_factory=list, init=False)
    _nodes: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if self.virtual_nodes_per_node < 1:
            raise ValueError("virtual_nodes_per_node must be positive")

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(sorted(self._nodes))

    @property
    def ring(self) -> tuple[VirtualNode, ...]:
        return tuple(self._ring)

    def _virtual_node_position(self, node: str, replica_index: int) -> int:
        return stable_hash(f"{node}#vn:{replica_index}")

    def add_node(self, node: str) -> None:
        """Add a physical node and all of its virtual positions."""
        if not node or not node.strip():
            raise ValueError("node name cannot be empty")
        if node in self._nodes:
            raise ValueError(f"node already exists: {node}")

        positions = [
            VirtualNode(
                position=self._virtual_node_position(node, replica),
                physical_node=node,
                replica_index=replica,
            )
            for replica in range(self.virtual_nodes_per_node)
        ]

        # Hash collisions are rare with 64 bits, but explicitly handling them
        # makes the data structure deterministic rather than silently ambiguous.
        existing_positions = {item.position for item in self._ring}
        collisions = [item.position for item in positions if item.position in existing_positions]
        if collisions:
            raise RuntimeError(f"hash collision detected for node {node}")

        self._ring.extend(positions)
        self._ring.sort(key=lambda item: item.position)
        self._nodes.add(node)

    def remove_node(self, node: str) -> None:
        """Remove a physical node and every virtual position it owns."""
        if node not in self._nodes:
            raise KeyError(f"node does not exist: {node}")

        self._ring = [
            item for item in self._ring if item.physical_node != node
        ]
        self._nodes.remove(node)

    def owner_for_hash(self, hash_value: int) -> str:
        """Return the clockwise owner for an already computed hash value."""
        if not self._ring:
            raise RuntimeError("cannot route without nodes")

        # Binary search avoids scanning the entire ring for every key.
        low = 0
        high = len(self._ring)

        while low < high:
            middle = (low + high) // 2
            if self._ring[middle].position >= hash_value:
                high = middle
            else:
                low = middle + 1

        if low == len(self._ring):
            low = 0

        return self._ring[low].physical_node

    def owner_for_key(self, key: str) -> str:
        if not key:
            raise ValueError("key cannot be empty")
        return self.owner_for_hash(stable_hash(key))

    def distribution(self, keys: Iterable[str]) -> dict[str, int]:
        """Count how many supplied keys are assigned to each physical node."""
        counts = {node: 0 for node in self._nodes}
        for key in keys:
            counts[self.owner_for_key(key)] += 1
        return counts

    def ring_snapshot(self, limit: int = 20) -> list[dict[str, object]]:
        """Return a readable sample of ring positions."""
        if limit < 1:
            raise ValueError("limit must be positive")

        return [
            {
                "position": item.position,
                "physical_node": item.physical_node,
                "replica_index": item.replica_index,
            }
            for item in self._ring[:limit]
        ]


def modulo_owner(key: str, nodes: list[str]) -> str:
    """
    Traditional modulo partitioning.

    Adding or removing a node changes the divisor, so many existing keys
    acquire different owners.
    """
    if not nodes:
        raise ValueError("nodes cannot be empty")
    return nodes[stable_hash(key) % len(nodes)]


def compare_key_movement(
    before: dict[str, str],
    after: dict[str, str],
) -> tuple[int, int]:
    """
    Return moved-key count and total-key count.

    The comparison is meaningful when the same key set is evaluated before
    and after a topology change.
    """
    if before.keys() != after.keys():
        raise ValueError("before and after must contain the same keys")

    moved = sum(before[key] != after[key] for key in before)
    return moved, len(before)


def distribution_stats(distribution: dict[str, int]) -> dict[str, float]:
    """Calculate simple load-balance indicators."""
    values = list(distribution.values())
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "max_to_min": 0.0}

    minimum = min(values)
    maximum = max(values)

    return {
        "mean": mean(values),
        "stddev": pstdev(values) if len(values) > 1 else 0.0,
        "max_to_min": float("inf") if minimum == 0 else maximum / minimum,
    }


def demonstrate_basic_ring() -> None:
    print("\n=== Basic hash ring ===")

    ring = ConsistentHashRing(virtual_nodes_per_node=64)

    for node in ("cache-a", "cache-b", "cache-c"):
        ring.add_node(node)

    for key in ("user:1001", "user:1002", "session:9f20", "cart:771"):
        print(f"{key:16} -> {ring.owner_for_key(key)}")

    print(f"Physical nodes: {ring.nodes}")
    print(f"Ring positions: {len(ring.ring)}")
    print("Sample positions:")
    for entry in ring.ring_snapshot(6):
        print(entry)


def demonstrate_virtual_nodes() -> None:
    print("\n=== Virtual-node distribution ===")

    keys = [f"user:{number}" for number in range(100_000)]

    for replicas in (1, 8, 32, 128):
        ring = ConsistentHashRing(virtual_nodes_per_node=replicas)
        for node in ("cache-a", "cache-b", "cache-c", "cache-d"):
            ring.add_node(node)

        distribution = ring.distribution(keys)
        stats = distribution_stats(distribution)

        print(
            f"replicas={replicas:3} "
            f"distribution={distribution} "
            f"stddev={stats['stddev']:.2f}"
        )


def demonstrate_node_addition() -> None:
    print("\n=== Node addition and key movement ===")

    keys = [f"object:{number}" for number in range(50_000)]

    ring = ConsistentHashRing(virtual_nodes_per_node=128)
    for node in ("storage-a", "storage-b", "storage-c"):
        ring.add_node(node)

    before = {key: ring.owner_for_key(key) for key in keys}
    before_distribution = ring.distribution(keys)

    ring.add_node("storage-d")

    after = {key: ring.owner_for_key(key) for key in keys}
    after_distribution = ring.distribution(keys)

    moved, total = compare_key_movement(before, after)

    print(f"Before: {before_distribution}")
    print(f"After:  {after_distribution}")
    print(f"Moved:  {moved}/{total} ({moved / total:.2%})")

    # With N evenly used nodes, adding one node ideally moves approximately
    # 1/(N+1) of the key space rather than almost the entire key set.
    print("Expected rough movement for four balanced nodes: ~25%")


def demonstrate_node_removal() -> None:
    print("\n=== Node removal and failover ownership ===")

    keys = [f"document:{number}" for number in range(20_000)]

    ring = ConsistentHashRing(virtual_nodes_per_node=96)
    for node in ("node-a", "node-b", "node-c", "node-d"):
        ring.add_node(node)

    before = {key: ring.owner_for_key(key) for key in keys}
    ring.remove_node("node-c")
    after = {key: ring.owner_for_key(key) for key in keys}

    moved, total = compare_key_movement(before, after)

    print(f"Moved after node-c removal: {moved}/{total} ({moved / total:.2%})")
    print(f"Remaining nodes: {ring.nodes}")

    # A removed node's keys are remapped to the next clockwise surviving
    # virtual node. Application-level replication can provide the actual data.
    for key in keys[:8]:
        print(f"{key:18} -> {before[key]} -> {after[key]}")


def demonstrate_modulo_comparison() -> None:
    print("\n=== Consistent hashing versus modulo partitioning ===")

    keys = [f"record:{number}" for number in range(50_000)]
    nodes_before = ["db-a", "db-b", "db-c"]
    nodes_after = ["db-a", "db-b", "db-c", "db-d"]

    modulo_before = {
        key: modulo_owner(key, nodes_before)
        for key in keys
    }
    modulo_after = {
        key: modulo_owner(key, nodes_after)
        for key in keys
    }

    modulo_moved, total = compare_key_movement(modulo_before, modulo_after)

    ring = ConsistentHashRing(virtual_nodes_per_node=128)
    for node in nodes_before:
        ring.add_node(node)

    ring_before = {key: ring.owner_for_key(key) for key in keys}
    ring.add_node("db-d")
    ring_after = {key: ring.owner_for_key(key) for key in keys}

    ring_moved, _ = compare_key_movement(ring_before, ring_after)

    print(f"Modulo moved:              {modulo_moved}/{total} ({modulo_moved / total:.2%})")
    print(f"Consistent hashing moved:  {ring_moved}/{total} ({ring_moved / total:.2%})")


def demonstrate_weighted_capacity() -> None:
    print("\n=== Weighted capacity using virtual-node counts ===")

    # A larger virtual-node count gives a node a larger share of the ring.
    ring = ConsistentHashRing(virtual_nodes_per_node=1)

    capacities = {
        "cache-small": 64,
        "cache-medium": 128,
        "cache-large": 256,
    }

    for node, replicas in capacities.items():
        original = ring.virtual_nodes_per_node
        ring.virtual_nodes_per_node = replicas
        ring.add_node(node)
        ring.virtual_nodes_per_node = original

    keys = [f"item:{number}" for number in range(100_000)]
    distribution = ring.distribution(keys)

    for node, count in distribution.items():
        print(f"{node:14} {count:7} ({count / len(keys):.2%})")

    # Weighted rings need operational validation because more virtual nodes
    # increase ring size, memory consumption, and lookup metadata.


def validate_ring() -> None:
    print("\n=== Validation and failure behavior ===")

    ring = ConsistentHashRing(virtual_nodes_per_node=16)

    operations = [
        ("empty route", lambda: ring.owner_for_key("user:1")),
        ("empty node", lambda: ring.add_node("")),
        ("add valid", lambda: ring.add_node("api-a")),
        ("duplicate node", lambda: ring.add_node("api-a")),
        ("remove missing", lambda: ring.remove_node("api-z")),
    ]

    for name, operation in operations:
        try:
            operation()
        except (ValueError, RuntimeError, KeyError) as exc:
            print(f"{name:16} -> rejected: {exc}")
        else:
            print(f"{name:16} -> accepted")


def production_notes() -> None:
    print("\n=== Operational considerations ===")
    print("Hash stability: node identifiers and key encoding must remain stable.")
    print("Virtual nodes: increase balance but also increase ring metadata.")
    print("Replication: ownership selects a primary; replication needs separate policy.")
    print("Hot keys: a perfectly balanced ring cannot prevent one extremely popular key.")
    print("Capacity changes: weighted virtual nodes can represent heterogeneous servers.")
    print("Failure handling: membership changes should be coordinated to avoid flapping.")
    print("Security: untrusted identifiers should not be allowed to control routing metadata.")
    print("Observability: record ownership changes, load distribution, and membership events.")


def main() -> None:
    demonstrate_basic_ring()
    demonstrate_virtual_nodes()
    demonstrate_node_addition()
    demonstrate_node_removal()
    demonstrate_modulo_comparison()
    demonstrate_weighted_capacity()
    validate_ring()
    production_notes()


if __name__ == "__main__":
    main()
