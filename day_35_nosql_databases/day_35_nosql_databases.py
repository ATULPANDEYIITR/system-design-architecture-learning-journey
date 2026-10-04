#!/usr/bin/env python3
"""
NoSQL Database Concepts: key-value, document, column-family, and graph databases.

This self-contained program builds four in-memory database models and uses them
to demonstrate the data-modeling choices, access patterns, consistency rules,
validation, indexing, traversal, aggregation, and trade-offs associated with
each NoSQL family.

No external packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
import json
import re
import time
import uuid


def heading(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def pretty(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str, sort_keys=True))


# ---------------------------------------------------------------------------
# Shared domain data
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


PRODUCTS = [
    {
        "id": "p-100",
        "name": "Mechanical Keyboard",
        "category": "electronics",
        "price": 89.00,
        "tags": ["keyboard", "usb", "office"],
        "supplier": "supplier-a",
    },
    {
        "id": "p-101",
        "name": "Wireless Mouse",
        "category": "electronics",
        "price": 39.00,
        "tags": ["mouse", "wireless", "office"],
        "supplier": "supplier-b",
    },
    {
        "id": "p-102",
        "name": "USB-C Dock",
        "category": "electronics",
        "price": 129.00,
        "tags": ["usb-c", "dock", "laptop"],
        "supplier": "supplier-a",
    },
]


# ---------------------------------------------------------------------------
# Key-value database
# ---------------------------------------------------------------------------

class KeyValueStore:
    """
    A simplified key-value store.

    The fundamental operation is key -> opaque value. The store does not need
    to understand the internal structure of the value to retrieve it.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}

    def put(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        if not key or not isinstance(key, str):
            raise ValueError("Key must be a non-empty string")

        self._data[key] = value

        if ttl_seconds is None:
            self._expiry.pop(key, None)
        elif ttl_seconds <= 0:
            self.delete(key)
        else:
            self._expiry[key] = time.monotonic() + ttl_seconds

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._data:
            return default

        expiry = self._expiry.get(key)
        if expiry is not None and time.monotonic() >= expiry:
            self.delete(key)
            return default

        return self._data[key]

    def delete(self, key: str) -> bool:
        existed = key in self._data
        self._data.pop(key, None)
        self._expiry.pop(key, None)
        return existed

    def increment(self, key: str, amount: int = 1) -> int:
        current = self.get(key, 0)

        if not isinstance(current, int):
            raise TypeError("Increment requires an integer value")

        updated = current + amount
        self.put(key, updated)
        return updated

    def compare_and_set(self, key: str, expected: Any, replacement: Any) -> bool:
        """
        Demonstrates an atomic-style conditional update.

        Real distributed stores provide their own concurrency primitives.
        This in-memory implementation is intentionally single-process.
        """
        current = self.get(key)

        if current != expected:
            return False

        self.put(key, replacement)
        return True


def demonstrate_key_value() -> None:
    heading("Key-Value Database")

    store = KeyValueStore()

    session = {
        "user_id": "u-501",
        "role": "customer",
        "cart_count": 2,
    }

    store.put("session:u-501", session, ttl_seconds=60)
    store.put("feature:recommendations", True)
    store.put("login-attempts:u-501", 0)

    print("Session lookup:")
    pretty(store.get("session:u-501"))

    attempts = store.increment("login-attempts:u-501")
    print(f"Failed login counter after increment: {attempts}")

    changed = store.compare_and_set(
        "feature:recommendations",
        True,
        False,
    )
    print(f"Conditional feature update succeeded: {changed}")

    print(f"Feature flag: {store.get('feature:recommendations')}")
    print(f"Missing key: {store.get('unknown:key', 'NOT_FOUND')}")

    # A key-value design is efficient when the application already knows the
    # exact key. Searching arbitrary fields is not the core access pattern.
    print("\nBest-fit access pattern: exact-key retrieval and atomic counters.")


# ---------------------------------------------------------------------------
# Document database
# ---------------------------------------------------------------------------

class DocumentValidationError(ValueError):
    pass


class DocumentStore:
    """
    A simplified document database.

    Documents are JSON-like dictionaries identified by a unique document ID.
    A secondary index on category demonstrates why document databases can
    support richer queries than pure key-value stores.
    """

    REQUIRED_FIELDS = {"id", "name", "category", "price"}

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}
        self._category_index: dict[str, set[str]] = defaultdict(set)

    def _validate(self, document: dict[str, Any]) -> None:
        missing = self.REQUIRED_FIELDS - document.keys()

        if missing:
            raise DocumentValidationError(
                f"Missing required fields: {sorted(missing)}"
            )

        if not isinstance(document["price"], (int, float)):
            raise DocumentValidationError("price must be numeric")

        if document["price"] < 0:
            raise DocumentValidationError("price cannot be negative")

        if not isinstance(document["tags"], list):
            raise DocumentValidationError("tags must be a list")

    def insert(self, document: dict[str, Any]) -> None:
        self._validate(document)

        document_id = str(document["id"])

        if document_id in self._documents:
            raise DocumentValidationError(
                f"Document {document_id} already exists"
            )

        self._documents[document_id] = json.loads(json.dumps(document))
        self._category_index[document["category"]].add(document_id)

    def replace(self, document_id: str, replacement: dict[str, Any]) -> None:
        self._validate(replacement)

        if document_id not in self._documents:
            raise KeyError(document_id)

        old = self._documents[document_id]

        if str(replacement["id"]) != document_id:
            raise DocumentValidationError("Document ID cannot change during replace")

        self._category_index[old["category"]].discard(document_id)
        self._category_index[replacement["category"]].add(document_id)
        self._documents[document_id] = json.loads(json.dumps(replacement))

    def get(self, document_id: str) -> dict[str, Any] | None:
        document = self._documents.get(document_id)
        return json.loads(json.dumps(document)) if document else None

    def find_by_category(self, category: str) -> list[dict[str, Any]]:
        ids = self._category_index.get(category, set())
        return [self.get(document_id) for document_id in sorted(ids)]

    def find(
        self,
        predicate,
    ) -> list[dict[str, Any]]:
        return [
            self.get(document_id)
            for document_id, document in self._documents.items()
            if predicate(document)
        ]

    def update_nested(
        self,
        document_id: str,
        path: tuple[str, ...],
        value: Any,
    ) -> None:
        if document_id not in self._documents:
            raise KeyError(document_id)

        document = self._documents[document_id]
        target = document

        for key in path[:-1]:
            child = target.get(key)

            if not isinstance(child, dict):
                raise DocumentValidationError(
                    f"Cannot traverse non-object field: {key}"
                )

            target = child

        target[path[-1]] = value
        self._validate(document)


def demonstrate_document_database() -> None:
    heading("Document Database")

    store = DocumentStore()

    for product in PRODUCTS:
        product_copy = dict(product)
        product_copy["inventory"] = {
            "warehouse_a": 20 if product["id"] != "p-102" else 7,
            "warehouse_b": 12,
        }
        store.insert(product_copy)

    print("Electronics indexed query:")
    pretty(store.find_by_category("electronics"))

    print("\nDocuments cheaper than $100:")
    cheap = store.find(lambda d: d["price"] < 100)
    pretty(cheap)

    store.update_nested(
        "p-100",
        ("inventory", "warehouse_a"),
        18,
    )

    print("\nAfter nested document update:")
    pretty(store.get("p-100"))

    try:
        store.insert(
            {
                "id": "p-invalid",
                "name": "Invalid Product",
                "category": "electronics",
                "price": -10,
                "tags": [],
            }
        )
    except DocumentValidationError as exc:
        print(f"\nValidation rejected document: {exc}")

    print(
        "\nBest-fit access pattern: aggregate-oriented records where related "
        "fields are naturally retrieved together."
    )


# ---------------------------------------------------------------------------
# Column-family database
# ---------------------------------------------------------------------------

@dataclass
class ColumnFamilyRow:
    """
    A row in a wide-column model.

    Columns can vary between rows. The row key is the primary lookup path.
    """
    row_key: str
    columns: dict[str, Any] = field(default_factory=dict)


class ColumnFamilyStore:
    """
    Simplified wide-column store.

    A production database such as Cassandra typically designs tables around
    known query patterns and partitions data by a partition key. This class
    models that principle without pretending to reproduce Cassandra's
    distributed storage engine.
    """

    def __init__(self) -> None:
        self._families: dict[str, dict[str, ColumnFamilyRow]] = defaultdict(dict)

    def put(
        self,
        family: str,
        row_key: str,
        columns: dict[str, Any],
    ) -> None:
        if not family or not row_key:
            raise ValueError("Family and row key are required")

        existing = self._families[family].get(
            row_key,
            ColumnFamilyRow(row_key),
        )

        existing.columns.update(columns)
        self._families[family][row_key] = existing

    def get(
        self,
        family: str,
        row_key: str,
        columns: Iterable[str] | None = None,
    ) -> dict[str, Any] | None:
        row = self._families.get(family, {}).get(row_key)

        if row is None:
            return None

        if columns is None:
            selected = dict(row.columns)
        else:
            selected = {
                column: row.columns[column]
                for column in columns
                if column in row.columns
            }

        return {
            "row_key": row.row_key,
            "columns": selected,
        }

    def scan_partition(
        self,
        family: str,
        prefix: str,
    ) -> list[dict[str, Any]]:
        rows = self._families.get(family, {})
        return [
            {
                "row_key": row.row_key,
                "columns": dict(row.columns),
            }
            for key, row in sorted(rows.items())
            if key.startswith(prefix)
        ]


def demonstrate_column_family_database() -> None:
    heading("Column-Family Database")

    store = ColumnFamilyStore()

    # The key embeds the partition and time-bucket dimensions. This mirrors
    # query-driven modeling used by wide-column systems.
    events = [
        ("u-501", "2026-10-05T00:01:00Z", "login", "mobile"),
        ("u-501", "2026-10-05T00:05:00Z", "view", "mobile"),
        ("u-501", "2026-10-05T00:09:00Z", "purchase", "web"),
        ("u-502", "2026-10-05T00:03:00Z", "login", "web"),
    ]

    for user_id, timestamp, event_type, channel in events:
        row_key = f"{user_id}|2026-10-05|{timestamp}"
        store.put(
            "activity_by_user_day",
            row_key,
            {
                "event_type": event_type,
                "channel": channel,
                "received_at": utc_now(),
            },
        )

    print("Single-row wide-column lookup:")
    pretty(
        store.get(
            "activity_by_user_day",
            "u-501|2026-10-05|2026-10-05T00:05:00Z",
        )
    )

    print("\nPartition-oriented query for user u-501:")
    pretty(store.scan_partition("activity_by_user_day", "u-501|2026-10-05|"))

    print(
        "\nThe model favors predictable partition-key queries rather than "
        "arbitrary relational joins."
    )


# ---------------------------------------------------------------------------
# Graph database
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Node:
    node_id: str
    label: str
    properties: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class Edge:
    source: str
    relationship: str
    target: str
    properties: tuple[tuple[str, Any], ...] = ()


class GraphStore:
    """
    Property-graph model with directed edges.

    Nodes represent entities and edges represent relationships. The graph
    traversal operations make relationship-centric queries explicit.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.outgoing: dict[str, list[Edge]] = defaultdict(list)

    def add_node(
        self,
        node_id: str,
        label: str,
        properties: dict[str, Any],
    ) -> None:
        if node_id in self.nodes:
            raise ValueError(f"Duplicate node: {node_id}")

        self.nodes[node_id] = Node(
            node_id,
            label,
            tuple(sorted(properties.items())),
        )

    def add_edge(
        self,
        source: str,
        relationship: str,
        target: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        if source not in self.nodes or target not in self.nodes:
            raise ValueError("Both edge endpoints must exist")

        edge = Edge(
            source,
            relationship,
            target,
            tuple(sorted((properties or {}).items())),
        )

        self.edges.append(edge)
        self.outgoing[source].append(edge)

    def neighbors(
        self,
        node_id: str,
        relationship: str | None = None,
    ) -> list[str]:
        return [
            edge.target
            for edge in self.outgoing.get(node_id, [])
            if relationship is None or edge.relationship == relationship
        ]

    def shortest_path(
        self,
        start: str,
        target: str,
    ) -> list[str] | None:
        if start not in self.nodes or target not in self.nodes:
            return None

        queue = [start]
        parent: dict[str, str | None] = {start: None}

        for current in queue:
            if current == target:
                break

            for neighbor in self.neighbors(current):
                if neighbor not in parent:
                    parent[neighbor] = current
                    queue.append(neighbor)

        if target not in parent:
            return None

        path: list[str] = []
        current: str | None = target

        while current is not None:
            path.append(current)
            current = parent[current]

        return list(reversed(path))

    def two_hop_recommendations(self, user_id: str) -> list[str]:
        """
        Recommend products bought by users who bought products purchased by
        the requested user.

        This relationship-heavy query is naturally expressed as traversal.
        """
        first_products = set(self.neighbors(user_id, "PURCHASED"))

        similar_users = {
            edge.source
            for edge in self.edges
            if edge.relationship == "PURCHASED"
            and edge.target in first_products
            and edge.source != user_id
        }

        recommendations = {
            product
            for other_user in similar_users
            for product in self.neighbors(other_user, "PURCHASED")
        }

        return sorted(recommendations - first_products)


def demonstrate_graph_database() -> None:
    heading("Graph Database")

    graph = GraphStore()

    graph.add_node("u-501", "User", {"name": "Asha"})
    graph.add_node("u-502", "User", {"name": "Rahul"})
    graph.add_node("u-503", "User", {"name": "Meera"})

    graph.add_node("p-100", "Product", {"name": "Mechanical Keyboard"})
    graph.add_node("p-101", "Product", {"name": "Wireless Mouse"})
    graph.add_node("p-102", "Product", {"name": "USB-C Dock"})

    graph.add_edge("u-501", "PURCHASED", "p-100")
    graph.add_edge("u-501", "PURCHASED", "p-101")
    graph.add_edge("u-502", "PURCHASED", "p-100")
    graph.add_edge("u-502", "PURCHASED", "p-102")
    graph.add_edge("u-503", "PURCHASED", "p-102")

    print("Products purchased by u-501:")
    pretty(graph.neighbors("u-501", "PURCHASED"))

    print("\nProduct recommendations derived from shared purchases:")
    pretty(graph.two_hop_recommendations("u-501"))

    print("\nShortest relationship path:")
    pretty(graph.shortest_path("u-501", "p-102"))

    print(
        "\nBest-fit access pattern: multi-hop relationship queries where the "
        "connections themselves carry business meaning."
    )


# ---------------------------------------------------------------------------
# Comparative workload
# ---------------------------------------------------------------------------

def compare_models() -> None:
    heading("Choosing a NoSQL Model by Access Pattern")

    workload = {
        "session lookup": "key-value",
        "shopping-cart state": "key-value",
        "product catalog with variable attributes": "document",
        "content metadata": "document",
        "very high-volume user event timeline": "column-family",
        "time-series-style partitioned events": "column-family",
        "fraud rings and relationship traversal": "graph",
        "social connections": "graph",
    }

    for workload_name, model in workload.items():
        print(f"{workload_name:<48} -> {model}")

    print(
        "\nThe correct choice follows the dominant access pattern, data shape, "
        "scaling requirement, and consistency model rather than the label "
        "'NoSQL' alone."
    )


# ---------------------------------------------------------------------------
# Validation, serialization, and failure handling
# ---------------------------------------------------------------------------

def demonstrate_validation_and_serialization() -> None:
    heading("Validation, Serialization, and Failure Handling")

    store = DocumentStore()

    valid = {
        "id": "p-200",
        "name": "Laptop Stand",
        "category": "office",
        "price": 49.50,
        "tags": ["ergonomic", "desk"],
    }

    store.insert(valid)

    encoded = json.dumps(store.get("p-200"), separators=(",", ":"))
    decoded = json.loads(encoded)

    print("JSON representation:")
    print(encoded)

    print("\nRound-tripped document:")
    pretty(decoded)

    failure_cases = [
        {
            "id": "bad-1",
            "name": "Missing Price",
            "category": "office",
            "tags": [],
        },
        {
            "id": "bad-2",
            "name": "Wrong Tags",
            "category": "office",
            "price": 10,
            "tags": "office",
        },
    ]

    for document in failure_cases:
        try:
            store.insert(document)
        except DocumentValidationError as exc:
            print(f"Rejected invalid document: {exc}")


def demonstrate_performance_principles() -> None:
    heading("Performance and Production Design Principles")

    principles = [
        (
            "Key-value",
            "Design keys around the hottest exact-lookup paths; avoid pretending "
            "the store is a general-purpose query engine."
        ),
        (
            "Document",
            "Use embedding for data commonly read together and secondary indexes "
            "for important query fields."
        ),
        (
            "Column-family",
            "Choose partition keys carefully; a poor partition can create hot "
            "partitions or force expensive scans."
        ),
        (
            "Graph",
            "Keep relationship-heavy traversals local to the graph and control "
            "unbounded traversals to prevent expensive path exploration."
        ),
    ]

    for model, principle in principles:
        print(f"{model}: {principle}")

    print(
        "\nProduction systems also require backup strategy, observability, "
        "authentication, authorization, encryption, schema/version management, "
        "capacity planning, replication policy, failure recovery, and explicit "
        "consistency expectations."
    )


def main() -> None:
    heading("NoSQL Database Laboratory")

    demonstrate_key_value()
    demonstrate_document_database()
    demonstrate_column_family_database()
    demonstrate_graph_database()
    compare_models()
    demonstrate_validation_and_serialization()
    demonstrate_performance_principles()

    heading("Laboratory Complete")
    print(
        "Four NoSQL data models were exercised using distinct access patterns: "
        "exact-key retrieval, document queries, partition-oriented reads, "
        "and relationship traversal."
    )


if __name__ == "__main__":
    main()
