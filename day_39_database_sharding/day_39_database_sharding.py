#!/usr/bin/env python3
"""
Database Sharding: shard keys, routing, and distributed storage.

A self-contained simulation of a horizontally partitioned customer-order
database. It covers deterministic key selection, virtual shards, routing,
replicated shard metadata, cross-shard queries, migration, failure handling,
and operational validation.

Run:
    python database_sharding.py

The implementation uses only the Python standard library. Its in-memory
storage models logical behavior rather than production durability,
replication, or distributed transactions.
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
import threading
import time
import unittest

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional


class ShardingError(Exception):
    """Base exception for sharding-related failures."""


class InvalidShardKey(ShardingError):
    """Raised when a record does not have a valid routing key."""


class ShardUnavailable(ShardingError):
    """Raised when the selected shard cannot serve a request."""


class DuplicateRecord(ShardingError):
    """Raised when a primary key already exists."""


class RecordNotFound(ShardingError):
    """Raised when a requested record does not exist."""


class MigrationError(ShardingError):
    """Raised when a shard migration cannot be completed safely."""


class RoutingStrategy(str, Enum):
    HASH = "hash"
    RANGE = "range"


@dataclass(frozen=True)
class Customer:
    customer_id: str
    region: str
    email: str


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_id: str
    amount_cents: int
    created_at: str
    status: str = "pending"

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise ValueError("order_id cannot be empty")
        if not self.customer_id.strip():
            raise ValueError("customer_id cannot be empty")
        if self.amount_cents < 0:
            raise ValueError("amount_cents cannot be negative")


@dataclass
class Shard:
    """A logical storage partition with independent availability."""

    shard_id: str
    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    available: bool = True
    version: int = 0

    def put(self, key: str, value: dict[str, Any]) -> None:
        if not self.available:
            raise ShardUnavailable(f"{self.shard_id} is unavailable")
        self.records[key] = value
        self.version += 1

    def get(self, key: str) -> Optional[dict[str, Any]]:
        if not self.available:
            raise ShardUnavailable(f"{self.shard_id} is unavailable")
        return self.records.get(key)

    def delete(self, key: str) -> bool:
        if not self.available:
            raise ShardUnavailable(f"{self.shard_id} is unavailable")
        if key not in self.records:
            return False
        del self.records[key]
        self.version += 1
        return True


class ConsistentHashRing:
    """
    Map arbitrary keys to virtual nodes.

    A stable digest prevents Python's randomized built-in hash() from
    producing different placements between interpreter processes.
    """

    def __init__(self, virtual_nodes: int = 64) -> None:
        if virtual_nodes < 1:
            raise ValueError("virtual_nodes must be positive")
        self.virtual_nodes = virtual_nodes
        self._ring: list[tuple[int, str]] = []
        self._points: list[int] = []

    @staticmethod
    def _digest(value: str) -> int:
        return int.from_bytes(
            hashlib.sha256(value.encode("utf-8")).digest()[:8],
            byteorder="big",
        )

    def rebuild(self, shard_ids: Iterable[str]) -> None:
        ring = []
        for shard_id in sorted(set(shard_ids)):
            for replica in range(self.virtual_nodes):
                point = self._digest(f"{shard_id}:virtual:{replica}")
                ring.append((point, shard_id))
        ring.sort()
        self._ring = ring
        self._points = [point for point, _ in ring]

    def route(self, key: str) -> str:
        if not self._ring:
            raise ShardingError("The hash ring contains no shards")
        import bisect

        point = self._digest(key)
        index = bisect.bisect_left(self._points, point)
        if index == len(self._ring):
            index = 0
        return self._ring[index][1]


class RangeRouter:
    """Route integer keys using half-open ranges [start, end)."""

    def __init__(self, ranges: list[tuple[int, int, str]]) -> None:
        self.ranges = sorted(ranges, key=lambda item: item[0])
        previous_end: Optional[int] = None

        for start, end, shard_id in self.ranges:
            if start >= end:
                raise ValueError("Each range must have start < end")
            if previous_end is not None and start < previous_end:
                raise ValueError("Shard ranges cannot overlap")
            if not shard_id:
                raise ValueError("shard_id cannot be empty")
            previous_end = end

    def route(self, key: int) -> str:
        for start, end, shard_id in self.ranges:
            if start <= key < end:
                return shard_id
        raise InvalidShardKey(f"No shard range contains key {key}")


class ShardDirectory:
    """
    Maintain the routing directory.

    In production, directory updates require durable, coordinated metadata
    changes. This simulation protects local mutations with a reentrant lock.
    """

    def __init__(self, shards: Iterable[Shard]) -> None:
        shard_list = list(shards)
        if not shard_list:
            raise ValueError("At least one shard is required")
        if len({shard.shard_id for shard in shard_list}) != len(shard_list):
            raise ValueError("Shard identifiers must be unique")

        self.shards = {shard.shard_id: shard for shard in shard_list}
        self.ring = ConsistentHashRing()
        self.ring.rebuild(self.shards)
        self.epoch = 1
        self._lock = threading.RLock()

    def route(self, key: str) -> Shard:
        if not isinstance(key, str) or not key.strip():
            raise InvalidShardKey("A non-empty string key is required")
        with self._lock:
            shard_id = self.ring.route(key)
            return self.shards[shard_id]

    def add_shard(self, shard: Shard) -> None:
        with self._lock:
            if shard.shard_id in self.shards:
                raise ValueError("Shard already exists")
            self.shards[shard.shard_id] = shard
            self.ring.rebuild(self.shards)
            self.epoch += 1

    def remove_shard_from_ring(self, shard_id: str) -> None:
        with self._lock:
            if shard_id not in self.shards:
                raise KeyError(shard_id)
            if len(self.shards) == 1:
                raise ValueError("Cannot remove the final shard")
            del self.shards[shard_id]
            self.ring.rebuild(self.shards)
            self.epoch += 1


class ShardedDatabase:
    """
    A small database facade that routes customer and order records.

    Orders are partitioned by customer_id to support customer-centric
    queries. order_id remains the record key within a shard.
    """

    def __init__(self, shard_count: int = 4) -> None:
        if shard_count < 1:
            raise ValueError("shard_count must be positive")

        shards = [Shard(f"shard-{index:02d}") for index in range(shard_count)]
        self.directory = ShardDirectory(shards)
        self.customer_index: dict[str, str] = {}
        self.order_index: dict[str, str] = {}
        self._lock = threading.RLock()

    def shard_for_customer(self, customer_id: str) -> Shard:
        return self.directory.route(customer_id)

    def create_customer(self, customer: Customer) -> str:
        if not customer.customer_id.strip():
            raise InvalidShardKey("customer_id cannot be empty")

        with self._lock:
            if customer.customer_id in self.customer_index:
                raise DuplicateRecord(customer.customer_id)

            shard = self.shard_for_customer(customer.customer_id)
            shard.put(
                f"customer:{customer.customer_id}",
                {
                    "type": "customer",
                    **asdict(customer),
                },
            )
            self.customer_index[customer.customer_id] = shard.shard_id
            return shard.shard_id

    def get_customer(self, customer_id: str) -> Customer:
        shard_id = self.customer_index.get(customer_id)
        if shard_id is None:
            raise RecordNotFound(customer_id)

        shard = self.directory.shards.get(shard_id)
        if shard is None:
            raise ShardUnavailable(f"Shard {shard_id} is not in the directory")

        row = shard.get(f"customer:{customer_id}")
        if row is None:
            raise RecordNotFound(customer_id)

        return Customer(
            customer_id=row["customer_id"],
            region=row["region"],
            email=row["email"],
        )

    def create_order(self, order: Order) -> str:
        with self._lock:
            if order.order_id in self.order_index:
                raise DuplicateRecord(order.order_id)

            # Validate the parent before placing an order on its shard.
            self.get_customer(order.customer_id)
            shard_id = self.customer_index[order.customer_id]
            shard = self.directory.shards[shard_id]

            shard.put(f"order:{order.order_id}", {
                "type": "order",
                **asdict(order),
            })
            self.order_index[order.order_id] = shard_id
            return shard_id

    def get_order(self, order_id: str) -> Order:
        shard_id = self.order_index.get(order_id)
        if shard_id is None:
            raise RecordNotFound(order_id)

        shard = self.directory.shards.get(shard_id)
        if shard is None:
            raise ShardUnavailable(f"Shard {shard_id} is missing")

        row = shard.get(f"order:{order_id}")
        if row is None:
            raise RecordNotFound(order_id)

        return Order(
            order_id=row["order_id"],
            customer_id=row["customer_id"],
            amount_cents=row["amount_cents"],
            created_at=row["created_at"],
            status=row["status"],
        )

    def orders_for_customer(self, customer_id: str) -> list[Order]:
        shard_id = self.customer_index.get(customer_id)
        if shard_id is None:
            return []

        shard = self.directory.shards[shard_id]
        prefix = "order:"
        orders = []

        for key, row in shard.records.items():
            if key.startswith(prefix) and row["customer_id"] == customer_id:
                orders.append(Order(
                    order_id=row["order_id"],
                    customer_id=row["customer_id"],
                    amount_cents=row["amount_cents"],
                    created_at=row["created_at"],
                    status=row["status"],
                ))

        return sorted(orders, key=lambda order: order.created_at)

    def all_orders(self) -> list[Order]:
        """
        Scatter-gather query.

        Every shard must respond in this simple implementation. A production
        API should define partial-result semantics and query timeouts.
        """
        results = []
        for shard in self.directory.shards.values():
            if not shard.available:
                raise ShardUnavailable(
                    f"Cannot complete scatter-gather: {shard.shard_id} unavailable"
                )
            for key, row in shard.records.items():
                if key.startswith("order:"):
                    results.append(Order(
                        order_id=row["order_id"],
                        customer_id=row["customer_id"],
                        amount_cents=row["amount_cents"],
                        created_at=row["created_at"],
                        status=row["status"],
                    ))
        return sorted(results, key=lambda order: order.order_id)

    def revenue_by_customer(self) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for order in self.all_orders():
            totals[order.customer_id] += order.amount_cents
        return dict(sorted(totals.items()))

    def health_report(self) -> dict[str, Any]:
        report = {}
        for shard_id, shard in sorted(self.directory.shards.items()):
            customer_count = sum(
                row["type"] == "customer" for row in shard.records.values()
            )
            order_count = sum(
                row["type"] == "order" for row in shard.records.values()
            )
            report[shard_id] = {
                "available": shard.available,
                "records": len(shard.records),
                "customers": customer_count,
                "orders": order_count,
                "version": shard.version,
            }
        return report

    def validate_indexes(self) -> list[str]:
        """Find metadata-to-storage inconsistencies."""
        errors = []

        for customer_id, shard_id in self.customer_index.items():
            shard = self.directory.shards.get(shard_id)
            if shard is None:
                errors.append(f"Customer {customer_id}: missing shard {shard_id}")
            elif f"customer:{customer_id}" not in shard.records:
                errors.append(f"Customer {customer_id}: record missing from {shard_id}")

        for order_id, shard_id in self.order_index.items():
            shard = self.directory.shards.get(shard_id)
            if shard is None:
                errors.append(f"Order {order_id}: missing shard {shard_id}")
            elif f"order:{order_id}" not in shard.records:
                errors.append(f"Order {order_id}: record missing from {shard_id}")

        return errors


@dataclass
class MigrationPlan:
    source_shard: str
    target_shard: str
    record_keys: list[str]
    expected_source_version: int


def prepare_migration(
    database: ShardedDatabase,
    source_shard: str,
    target_shard: str,
) -> MigrationPlan:
    """
    Prepare a copy plan without changing the live routing metadata.

    This is an educational snapshot. Real online migration also captures
    concurrent writes, performs change-log replay, and verifies checksums.
    """
    if source_shard == target_shard:
        raise MigrationError("Source and target must differ")

    source = database.directory.shards.get(source_shard)
    target = database.directory.shards.get(target_shard)

    if source is None or target is None:
        raise MigrationError("Both shards must exist")
    if not source.available or not target.available:
        raise ShardUnavailable("Both migration shards must be available")

    return MigrationPlan(
        source_shard=source_shard,
        target_shard=target_shard,
        record_keys=sorted(source.records),
        expected_source_version=source.version,
    )


def execute_migration(
    database: ShardedDatabase,
    plan: MigrationPlan,
) -> int:
    """
    Copy records, verify the copy, and then update index ownership.

    The lock prevents mutations through this database facade while the
    migration runs. It is not a substitute for a distributed transaction.
    """
    with database._lock:
        source = database.directory.shards[plan.source_shard]
        target = database.directory.shards[plan.target_shard]

        if not source.available or not target.available:
            raise ShardUnavailable("A migration shard is unavailable")

        if source.version != plan.expected_source_version:
            raise MigrationError("Source changed after the migration snapshot")

        staged: dict[str, dict[str, Any]] = {}
        for key in plan.record_keys:
            if key not in source.records:
                raise MigrationError(f"Source record disappeared: {key}")
            if key in target.records:
                raise MigrationError(f"Target already contains {key}")
            staged[key] = dict(source.records[key])

        # Verify copied values before removing source records.
        for key, value in staged.items():
            if value != source.records[key]:
                raise MigrationError(f"Copy verification failed for {key}")

        target.records.update(staged)
        target.version += len(staged)

        # Change ownership only after the target copy is complete.
        for key in staged:
            if key.startswith("customer:"):
                customer_id = key.removeprefix("customer:")
                database.customer_index[customer_id] = target.shard_id
            elif key.startswith("order:"):
                order_id = key.removeprefix("order:")
                database.order_index[order_id] = target.shard_id

        for key in staged:
            del source.records[key]
        source.version += len(staged)

        return len(staged)


def demonstrate_hash_distribution() -> dict[str, int]:
    ring = ConsistentHashRing(virtual_nodes=128)
    shard_ids = ["east", "central", "west", "south"]
    ring.rebuild(shard_ids)

    distribution = Counter(
        ring.route(f"customer-{index:05d}") for index in range(5000)
    )
    return dict(sorted(distribution.items()))


def demonstrate_remapping() -> tuple[int, int]:
    """Measure how many keys move after adding a shard."""
    keys = [f"account-{index}" for index in range(2000)]

    original = ConsistentHashRing(virtual_nodes=128)
    original.rebuild(["shard-a", "shard-b", "shard-c"])

    expanded = ConsistentHashRing(virtual_nodes=128)
    expanded.rebuild(["shard-a", "shard-b", "shard-c", "shard-d"])

    moved = sum(
        original.route(key) != expanded.route(key) for key in keys
    )
    return moved, len(keys)


def demonstrate_range_routing() -> dict[int, str]:
    router = RangeRouter([
        (0, 1000, "orders-000"),
        (1000, 2000, "orders-001"),
        (2000, 3000, "orders-002"),
    ])
    return {
        key: router.route(key)
        for key in (0, 999, 1000, 1999, 2000, 2999)
    }


def build_sample_database() -> ShardedDatabase:
    database = ShardedDatabase(shard_count=4)

    customers = [
        Customer("cust-100", "north", "a@example.test"),
        Customer("cust-200", "south", "b@example.test"),
        Customer("cust-300", "west", "c@example.test"),
        Customer("cust-400", "east", "d@example.test"),
    ]

    for customer in customers:
        database.create_customer(customer)

    orders = [
        Order("ord-001", "cust-100", 1299, "2026-10-01T09:00:00Z"),
        Order("ord-002", "cust-100", 4599, "2026-10-02T11:30:00Z"),
        Order("ord-003", "cust-200", 899, "2026-10-03T15:15:00Z"),
        Order("ord-004", "cust-300", 2599, "2026-10-04T10:20:00Z"),
        Order("ord-005", "cust-400", 7999, "2026-10-05T16:45:00Z"),
    ]

    for order in orders:
        database.create_order(order)

    return database


class ShardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = build_sample_database()

    def test_customer_routes_to_one_shard(self) -> None:
        customer = self.database.get_customer("cust-100")
        self.assertEqual(customer.customer_id, "cust-100")

    def test_customer_orders_are_co_located(self) -> None:
        orders = self.database.orders_for_customer("cust-100")
        self.assertEqual(len(orders), 2)
        self.assertEqual(
            len({self.database.order_index[o.order_id] for o in orders}),
            1,
        )

    def test_duplicate_order_is_rejected(self) -> None:
        with self.assertRaises(DuplicateRecord):
            self.database.create_order(
                Order("ord-001", "cust-100", 500, "2026-10-06T00:00:00Z")
            )

    def test_unknown_customer_is_rejected(self) -> None:
        with self.assertRaises(RecordNotFound):
            self.database.create_order(
                Order("ord-999", "cust-missing", 100, "2026-10-06T00:00:00Z")
            )

    def test_scatter_gather_detects_unavailable_shard(self) -> None:
        next(iter(self.database.directory.shards.values())).available = False
        with self.assertRaises(ShardUnavailable):
            self.database.all_orders()

    def test_indexes_match_storage(self) -> None:
        self.assertEqual(self.database.validate_indexes(), [])

    def test_range_boundaries(self) -> None:
        router = RangeRouter([(0, 10, "a"), (10, 20, "b")])
        self.assertEqual(router.route(9), "a")
        self.assertEqual(router.route(10), "b")
        with self.assertRaises(InvalidShardKey):
            router.route(20)

    def test_successful_snapshot_migration(self) -> None:
        database = ShardedDatabase(shard_count=2)
        customer = Customer("move-me", "north", "move@example.test")
        source_id = database.create_customer(customer)
        target_id = next(
            shard_id
            for shard_id in database.directory.shards
            if shard_id != source_id
        )

        plan = prepare_migration(database, source_id, target_id)
        moved = execute_migration(database, plan)

        self.assertEqual(moved, 1)
        self.assertEqual(database.customer_index["move-me"], target_id)
        self.assertEqual(database.get_customer("move-me"), customer)
        self.assertEqual(database.validate_indexes(), [])


def main() -> None:
    random.seed(42)

    print("HASH SHARD DISTRIBUTION")
    print(json.dumps(demonstrate_hash_distribution(), indent=2))

    moved, total = demonstrate_remapping()
    print("\nCONSISTENT HASHING REMAPPING")
    print(f"Keys moved after adding one shard: {moved}/{total}")
    print(f"Remapping percentage: {moved / total:.2%}")

    print("\nRANGE ROUTING")
    print(json.dumps(demonstrate_range_routing(), indent=2))

    database = build_sample_database()

    print("\nCUSTOMER-LOCAL QUERY")
    for order in database.orders_for_customer("cust-100"):
        print(asdict(order))

    print("\nSCATTER-GATHER REVENUE")
    print(json.dumps(database.revenue_by_customer(), indent=2))

    print("\nSHARD HEALTH")
    print(json.dumps(database.health_report(), indent=2))

    print("\nINDEX CONSISTENCY")
    errors = database.validate_indexes()
    print("Consistent" if not errors else errors)

    print("\nFAILURE SIMULATION")
    first_shard = next(iter(database.directory.shards.values()))
    first_shard.available = False
    try:
        database.all_orders()
    except ShardUnavailable as exc:
        print(f"Query correctly failed: {exc}")
    finally:
        first_shard.available = True

    print("\nUNIT TESTS")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ShardingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
