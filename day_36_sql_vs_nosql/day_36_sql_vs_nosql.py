"""
SQL vs NoSQL: data models, scalability, consistency, and use cases.

This executable program builds a small comparison laboratory. It models the same
business domain in relational and document/key-value-oriented forms, then
demonstrates normalization, joins, denormalization, indexing concepts,
partitioning, replication consistency, transactions, optimistic concurrency,
and workload-oriented database selection.

No external packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable
import json
import random
import time


class ConsistencyModel(Enum):
    STRONG = "strong"
    EVENTUAL = "eventual"


class DatabaseFamily(Enum):
    SQL = "SQL"
    DOCUMENT = "Document NoSQL"
    KEY_VALUE = "Key-Value NoSQL"


@dataclass
class Customer:
    customer_id: int
    name: str
    email: str


@dataclass
class Product:
    product_id: int
    name: str
    price: float
    category: str


@dataclass
class Order:
    order_id: int
    customer_id: int
    status: str
    total: float = 0.0


@dataclass
class OrderItem:
    order_id: int
    product_id: int
    quantity: int
    unit_price: float


@dataclass
class SQLStore:
    """
    Normalized relational-style storage.

    Separate collections represent tables. Foreign-key-like validation is
    performed explicitly because this is an educational in-memory model.
    """

    customers: dict[int, Customer] = field(default_factory=dict)
    products: dict[int, Product] = field(default_factory=dict)
    orders: dict[int, Order] = field(default_factory=dict)
    order_items: list[OrderItem] = field(default_factory=list)

    def add_customer(self, customer: Customer) -> None:
        if customer.customer_id in self.customers:
            raise ValueError("Duplicate customer primary key")
        if any(c.email == customer.email for c in self.customers.values()):
            raise ValueError("Customer email must be unique")
        self.customers[customer.customer_id] = customer

    def add_product(self, product: Product) -> None:
        if product.product_id in self.products:
            raise ValueError("Duplicate product primary key")
        if product.price < 0:
            raise ValueError("Product price cannot be negative")
        self.products[product.product_id] = product

    def add_order(self, order: Order) -> None:
        if order.order_id in self.orders:
            raise ValueError("Duplicate order primary key")
        if order.customer_id not in self.customers:
            raise ValueError("Foreign-key violation: customer does not exist")
        self.orders[order.order_id] = order

    def add_item(self, item: OrderItem) -> None:
        if item.order_id not in self.orders:
            raise ValueError("Foreign-key violation: order does not exist")
        if item.product_id not in self.products:
            raise ValueError("Foreign-key violation: product does not exist")
        if item.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if item.unit_price < 0:
            raise ValueError("Unit price cannot be negative")

        self.order_items.append(item)
        self.recalculate_order_total(item.order_id)

    def recalculate_order_total(self, order_id: int) -> None:
        order = self.orders[order_id]
        order.total = sum(
            item.quantity * item.unit_price
            for item in self.order_items
            if item.order_id == order_id
        )

    def customer_order_report(self, customer_id: int) -> list[dict[str, Any]]:
        """
        Simulates a SQL JOIN across customers, orders, order_items and products.
        """
        if customer_id not in self.customers:
            return []

        result = []
        customer = self.customers[customer_id]

        for order in self.orders.values():
            if order.customer_id != customer_id:
                continue

            for item in self.order_items:
                if item.order_id != order.order_id:
                    continue

                product = self.products[item.product_id]
                result.append(
                    {
                        "customer": customer.name,
                        "order_id": order.order_id,
                        "status": order.status,
                        "product": product.name,
                        "category": product.category,
                        "quantity": item.quantity,
                        "line_total": item.quantity * item.unit_price,
                    }
                )
        return result

    def transaction(self, operations: Iterable) -> None:
        """
        A simple transaction simulation.

        The snapshot provides atomic rollback for this in-memory model.
        Real SQL databases use transaction logs, locks/MVCC, isolation
        levels, and recovery mechanisms rather than deepcopy snapshots.
        """
        snapshot = deepcopy(self)
        try:
            for operation in operations:
                operation()
        except Exception:
            self.customers = snapshot.customers
            self.products = snapshot.products
            self.orders = snapshot.orders
            self.order_items = snapshot.order_items
            raise


@dataclass
class DocumentStore:
    """
    Document-oriented representation of the same order domain.

    Customer and product information can be embedded where the read workload
    benefits from retrieving a complete aggregate with one document lookup.
    """

    orders: dict[str, dict[str, Any]] = field(default_factory=dict)

    def insert_order(self, document: dict[str, Any]) -> None:
        order_id = document.get("order_id")
        if not order_id:
            raise ValueError("Document requires order_id")
        if order_id in self.orders:
            raise ValueError("Duplicate document identifier")
        if not isinstance(document.get("items"), list):
            raise ValueError("Order document requires an items array")
        self.orders[order_id] = deepcopy(document)

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        return deepcopy(self.orders.get(order_id))

    def update_status(self, order_id: str, status: str) -> None:
        if order_id not in self.orders:
            raise KeyError("Order document not found")
        self.orders[order_id]["status"] = status


@dataclass
class KeyValueStore:
    """
    Key-value storage models the simplest NoSQL access pattern:
    direct lookup by a known key.

    It deliberately does not pretend that arbitrary relational joins are a
    natural operation for a basic key-value database.
    """

    values: dict[str, Any] = field(default_factory=dict)

    def put(self, key: str, value: Any) -> None:
        if not key:
            raise ValueError("Key cannot be empty")
        self.values[key] = deepcopy(value)

    def get(self, key: str) -> Any:
        return deepcopy(self.values.get(key))


@dataclass
class Replica:
    name: str
    data: dict[str, Any] = field(default_factory=dict)
    version: int = 0


class EventualConsistencyCluster:
    """
    A tiny asynchronous replication simulation.

    Writes go to the primary immediately. Replica synchronization occurs
    explicitly, making the temporary stale-read window observable.
    """

    def __init__(self) -> None:
        self.primary = Replica("primary")
        self.replicas = [Replica("replica-a"), Replica("replica-b")]
        self.version = 0

    def write(self, key: str, value: Any) -> int:
        self.version += 1
        self.primary.data[key] = value
        self.primary.version = self.version
        return self.version

    def read(self, replica_name: str, key: str) -> Any:
        nodes = [self.primary, *self.replicas]
        for node in nodes:
            if node.name == replica_name:
                return node.data.get(key)
        raise KeyError(f"Unknown replica: {replica_name}")

    def replicate(self) -> None:
        for replica in self.replicas:
            replica.data = deepcopy(self.primary.data)
            replica.version = self.primary.version


class StrongConsistencyStore:
    """
    A single authoritative state model.

    This does not reproduce the internals of a production distributed SQL
    system. It demonstrates the semantic property that reads are served from
    the authoritative committed state.
    """

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def write(self, key: str, value: Any) -> None:
        self.data[key] = value

    def read(self, key: str) -> Any:
        return self.data.get(key)


@dataclass
class VersionedRecord:
    value: dict[str, Any]
    version: int


class OptimisticDocumentRepository:
    """
    Demonstrates optimistic concurrency control.

    A client must provide the version it originally read. A stale update is
    rejected instead of silently overwriting another writer's modification.
    """

    def __init__(self) -> None:
        self.records: dict[str, VersionedRecord] = {}

    def create(self, key: str, value: dict[str, Any]) -> None:
        if key in self.records:
            raise ValueError("Record already exists")
        self.records[key] = VersionedRecord(deepcopy(value), 1)

    def read(self, key: str) -> VersionedRecord:
        if key not in self.records:
            raise KeyError(key)
        record = self.records[key]
        return VersionedRecord(deepcopy(record.value), record.version)

    def update(
        self,
        key: str,
        new_value: dict[str, Any],
        expected_version: int,
    ) -> None:
        record = self.records[key]
        if record.version != expected_version:
            raise RuntimeError(
                "Optimistic concurrency conflict: record changed since it was read"
            )
        record.value = deepcopy(new_value)
        record.version += 1


def build_sample_sql_store() -> SQLStore:
    store = SQLStore()

    store.add_customer(Customer(1, "Asha Rao", "asha@example.com"))
    store.add_customer(Customer(2, "Rohan Mehta", "rohan@example.com"))

    store.add_product(Product(10, "Laptop", 1200.0, "Computing"))
    store.add_product(Product(11, "Monitor", 300.0, "Computing"))
    store.add_product(Product(12, "Keyboard", 80.0, "Accessories"))

    store.add_order(Order(1001, 1, "PAID"))
    store.add_item(OrderItem(1001, 10, 1, 1200.0))
    store.add_item(OrderItem(1001, 12, 2, 80.0))

    store.add_order(Order(1002, 2, "PENDING"))
    store.add_item(OrderItem(1002, 11, 2, 300.0))

    return store


def build_document_store() -> DocumentStore:
    store = DocumentStore()

    store.insert_order(
        {
            "order_id": "1001",
            "customer": {
                "id": 1,
                "name": "Asha Rao",
                "email": "asha@example.com",
            },
            "status": "PAID",
            "items": [
                {
                    "product_id": 10,
                    "name": "Laptop",
                    "category": "Computing",
                    "quantity": 1,
                    "unit_price": 1200.0,
                },
                {
                    "product_id": 12,
                    "name": "Keyboard",
                    "category": "Accessories",
                    "quantity": 2,
                    "unit_price": 80.0,
                },
            ],
        }
    )

    return store


def demonstrate_data_models() -> None:
    print("\n=== DATA MODEL COMPARISON ===")

    sql_store = build_sample_sql_store()
    document_store = build_document_store()

    print("SQL-style normalized rows:")
    for row in sql_store.customer_order_report(1):
        print(json.dumps(row, indent=2))

    print("\nDocument-style aggregate:")
    print(json.dumps(document_store.get_order("1001"), indent=2))

    key_value = KeyValueStore()
    key_value.put("session:user:1", {"user_id": 1, "expires_in": 1800})

    print("\nKey-value lookup:")
    print(key_value.get("session:user:1"))


def demonstrate_sql_constraints() -> None:
    print("\n=== RELATIONAL INTEGRITY ===")
    store = build_sample_sql_store()

    try:
        store.add_item(OrderItem(9999, 10, 1, 1200.0))
    except ValueError as exc:
        print(f"Rejected invalid relational reference: {exc}")

    try:
        store.add_product(Product(13, "Invalid", -10.0, "Invalid"))
    except ValueError as exc:
        print(f"Rejected invalid domain value: {exc}")


def demonstrate_transaction() -> None:
    print("\n=== TRANSACTION AND ROLLBACK ===")
    store = build_sample_sql_store()

    def create_valid_order() -> None:
        store.add_order(Order(1003, 1, "PENDING"))
        store.add_item(OrderItem(1003, 10, 1, 1200.0))

    store.transaction([create_valid_order])
    print(f"Committed order total: {store.orders[1003].total:.2f}")

    def create_invalid_order() -> None:
        store.add_order(Order(1004, 1, "PENDING"))
        store.add_item(OrderItem(1004, 999, 1, 50.0))

    try:
        store.transaction([create_invalid_order])
    except ValueError as exc:
        print(f"Transaction rolled back: {exc}")

    print(f"Order 1004 exists after rollback: {1004 in store.orders}")


def demonstrate_consistency() -> None:
    print("\n=== CONSISTENCY MODELS ===")

    strong = StrongConsistencyStore()
    strong.write("inventory:laptop", 9)
    print(f"Strong read after write: {strong.read('inventory:laptop')}")

    eventual = EventualConsistencyCluster()
    eventual.write("inventory:laptop", 9)

    print(
        "Replica before synchronization:",
        eventual.read("replica-a", "inventory:laptop"),
    )

    eventual.replicate()

    print(
        "Replica after synchronization:",
        eventual.read("replica-a", "inventory:laptop"),
    )


def demonstrate_optimistic_concurrency() -> None:
    print("\n=== OPTIMISTIC CONCURRENCY ===")

    repository = OptimisticDocumentRepository()
    repository.create("order-1001", {"status": "PENDING", "total": 1200})

    client_a = repository.read("order-1001")
    client_b = repository.read("order-1001")

    repository.update(
        "order-1001",
        {"status": "PAID", "total": 1200},
        client_a.version,
    )

    try:
        repository.update(
            "order-1001",
            {"status": "CANCELLED", "total": 1200},
            client_b.version,
        )
    except RuntimeError as exc:
        print(exc)

    print(repository.read("order-1001"))


def estimate_storage_tradeoff() -> None:
    """
    Demonstrates why normalization and denormalization produce different
    storage patterns.

    Normalization reduces repeated customer/product attributes. Denormalization
    can reduce read-time joins but increases update complexity and duplicate data.
    """
    print("\n=== NORMALIZATION VS DENORMALIZATION ===")

    normalized = {
        "customer": {"id": 1, "name": "Asha Rao"},
        "orders": [
            {"id": 1001, "customer_id": 1},
            {"id": 1002, "customer_id": 1},
            {"id": 1003, "customer_id": 1},
        ],
    }

    denormalized = [
        {
            "id": 1001,
            "customer": {"id": 1, "name": "Asha Rao"},
        },
        {
            "id": 1002,
            "customer": {"id": 1, "name": "Asha Rao"},
        },
        {
            "id": 1003,
            "customer": {"id": 1, "name": "Asha Rao"},
        },
    ]

    normalized_size = len(json.dumps(normalized))
    denormalized_size = len(json.dumps(denormalized))

    print(f"Approximate normalized representation: {normalized_size} bytes")
    print(f"Approximate denormalized representation: {denormalized_size} bytes")
    print("The trade-off is read simplicity and locality versus duplication.")


def choose_database(
    workload: str,
    strong_transactions: bool,
    relational_queries: bool,
    extreme_horizontal_scale: bool,
    flexible_schema: bool,
) -> str:
    """
    Workload-driven selection heuristic.

    Real architecture decisions require measured workload characteristics,
    operational requirements, team expertise, cost, managed-service features,
    failure models, and compliance requirements.
    """
    if strong_transactions and relational_queries:
        return "SQL"
    if flexible_schema and extreme_horizontal_scale and not strong_transactions:
        return "Document NoSQL"
    if workload == "session_lookup":
        return "Key-Value NoSQL"
    if relational_queries:
        return "SQL"
    if extreme_horizontal_scale:
        return "NoSQL, with the specific model selected from the access pattern"
    return "Evaluate both with representative workload benchmarks"


def demonstrate_workload_selection() -> None:
    print("\n=== WORKLOAD-DRIVEN SELECTION ===")

    scenarios = [
        (
            "Bank transfer",
            choose_database(
                "financial_transaction",
                True,
                True,
                False,
                False,
            ),
        ),
        (
            "Product catalog with evolving attributes",
            choose_database(
                "catalog",
                False,
                False,
                True,
                True,
            ),
        ),
        (
            "User session lookup",
            choose_database(
                "session_lookup",
                False,
                False,
                True,
                False,
            ),
        ),
        (
            "Financial reporting",
            choose_database(
                "analytics",
                True,
                True,
                False,
                False,
            ),
        ),
    ]

    for scenario, database in scenarios:
        print(f"{scenario}: {database}")


def benchmark_lookup_structures() -> None:
    """
    A small algorithmic demonstration rather than a database benchmark.

    Dictionary lookup is approximately O(1) average-case, while scanning a
    list is O(n). Database indexes provide an analogous principle: an index
    changes the access path rather than merely making the underlying storage
    intrinsically faster.
    """
    print("\n=== ACCESS-PATH PERFORMANCE ===")

    size = 100_000
    rows = list(range(size))
    indexed = {value: value for value in rows}
    target = size - 1

    start = time.perf_counter()
    _ = next(value for value in rows if value == target)
    scan_time = time.perf_counter() - start

    start = time.perf_counter()
    _ = indexed[target]
    indexed_time = time.perf_counter() - start

    print(f"Linear scan time: {scan_time:.8f}s")
    print(f"Indexed dictionary lookup time: {indexed_time:.8f}s")
    print("This illustrates access-path complexity, not a SQL-vs-NoSQL benchmark.")


def demonstrate_partitioning_concept() -> None:
    """
    Hash partitioning distributes records by a deterministic partition key.

    Partitioning is different from merely choosing SQL or NoSQL. Both database
    families can use partitioning or sharding depending on the product.
    """
    print("\n=== HASH PARTITIONING ===")

    partition_count = 4
    orders = [1001, 1002, 1003, 1004, 1005, 1006]

    partitions: dict[int, list[int]] = defaultdict(list)
    for order_id in orders:
        partition = hash(order_id) % partition_count
        partitions[partition].append(order_id)

    for partition, records in sorted(partitions.items()):
        print(f"Partition {partition}: {records}")


def demonstrate_failure_and_recovery() -> None:
    print("\n=== FAILURE MODEL ===")

    cluster = EventualConsistencyCluster()
    cluster.write("profile:1", {"name": "Asha", "tier": "gold"})

    cluster.replicate()

    cluster.write("profile:1", {"name": "Asha", "tier": "platinum"})

    stale_value = cluster.read("replica-a", "profile:1")
    print(f"Stale replica value: {stale_value}")

    cluster.replicate()

    recovered_value = cluster.read("replica-a", "profile:1")
    print(f"Replica after recovery: {recovered_value}")


def demonstrate_document_evolution() -> None:
    print("\n=== SCHEMA EVOLUTION IN DOCUMENT STORAGE ===")

    store = DocumentStore()

    store.insert_order(
        {
            "order_id": "2001",
            "customer_id": 1,
            "status": "PAID",
            "items": [],
        }
    )

    store.insert_order(
        {
            "order_id": "2002",
            "customer_id": 1,
            "status": "PAID",
            "items": [],
            "shipping": {
                "country": "IN",
                "postal_code": "226001",
            },
        }
    )

    print("Older document:", store.get_order("2001"))
    print("Newer document:", store.get_order("2002"))
    print(
        "Document flexibility can accommodate optional fields, but application "
        "validation must still control semantic consistency."
    )


def run() -> None:
    random.seed(42)

    demonstrate_data_models()
    demonstrate_sql_constraints()
    demonstrate_transaction()
    demonstrate_consistency()
    demonstrate_optimistic_concurrency()
    estimate_storage_tradeoff()
    demonstrate_workload_selection()
    benchmark_lookup_structures()
    demonstrate_partitioning_concept()
    demonstrate_failure_and_recovery()
    demonstrate_document_evolution()

    print("\n=== DATABASE SELECTION PRINCIPLE ===")
    print(
        "Choose based on access patterns, transaction requirements, consistency "
        "needs, relationship complexity, scale, schema behavior, operational "
        "constraints, and measured workload characteristics rather than the "
        "assumption that SQL or NoSQL is universally superior."
    )


if __name__ == "__main__":
    run()
