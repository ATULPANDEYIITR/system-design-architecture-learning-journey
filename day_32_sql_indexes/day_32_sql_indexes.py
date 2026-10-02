#!/usr/bin/env python3
"""
SQL Indexes: B-Tree Indexes and Query Performance

A self-contained educational simulation of SQL indexing concepts.

This program does not require a database server or third-party packages.
It models:
- table rows and pages
- a simplified B-Tree index
- equality and range lookups
- composite indexes
- covering-index behavior
- index maintenance during inserts and updates
- selectivity and cardinality
- query-plan decisions
- estimated logical I/O
- full scans versus indexed access
- common indexing trade-offs

The implementation is deliberately database-oriented rather than a generic
Python data-structure tutorial. The B-Tree is simplified so that the
relationship between SQL indexes and query execution can be observed directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from math import ceil, log2
from random import Random
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Relational table model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Order:
    order_id: int
    customer_id: int
    status: str
    order_date: int
    total_amount: float


@dataclass
class TablePage:
    page_id: int
    rows: list[Order] = field(default_factory=list)


class OrdersTable:
    """
    A tiny heap-table model.

    Rows are stored in pages. An index stores keys pointing to row locations.
    This makes it possible to compare the number of pages touched by a full
    table scan with the pages visited through an index.
    """

    def __init__(self, rows_per_page: int = 8) -> None:
        if rows_per_page <= 0:
            raise ValueError("rows_per_page must be positive")

        self.rows_per_page = rows_per_page
        self.pages: list[TablePage] = []
        self.locations: dict[int, tuple[int, int]] = {}
        self.rows_by_id: dict[int, Order] = {}

    def insert(self, row: Order) -> tuple[int, int]:
        if row.order_id in self.rows_by_id:
            raise ValueError(f"Duplicate order_id: {row.order_id}")

        if not self.pages or len(self.pages[-1].rows) >= self.rows_per_page:
            self.pages.append(TablePage(page_id=len(self.pages)))

        page = self.pages[-1]
        slot = len(page.rows)
        page.rows.append(row)
        self.locations[row.order_id] = (page.page_id, slot)
        self.rows_by_id[row.order_id] = row
        return page.page_id, slot

    def update(self, order_id: int, **changes: Any) -> Order:
        if order_id not in self.rows_by_id:
            raise KeyError(f"Unknown order_id: {order_id}")

        old = self.rows_by_id[order_id]
        updated = Order(
            order_id=old.order_id,
            customer_id=changes.get("customer_id", old.customer_id),
            status=changes.get("status", old.status),
            order_date=changes.get("order_date", old.order_date),
            total_amount=changes.get("total_amount", old.total_amount),
        )

        page_id, slot = self.locations[order_id]
        self.pages[page_id].rows[slot] = updated
        self.rows_by_id[order_id] = updated
        return updated

    def full_scan(self, predicate) -> tuple[list[Order], int]:
        """
        A full scan must inspect every populated table page.

        The predicate itself is not counted as an I/O operation. The purpose is
        to model the page-access difference created by an index.
        """
        matches: list[Order] = []

        for page in self.pages:
            for row in page.rows:
                if predicate(row):
                    matches.append(row)

        return matches, len(self.pages)

    def fetch_rows(self, order_ids: Iterable[int]) -> tuple[list[Order], int]:
        """
        Fetch rows through their physical locations.

        Distinct pages are counted because several index entries can point to
        rows on the same table page.
        """
        unique_ids = list(dict.fromkeys(order_ids))
        pages_touched = {
            self.locations[order_id][0]
            for order_id in unique_ids
            if order_id in self.locations
        }

        rows = [
            self.rows_by_id[order_id]
            for order_id in unique_ids
            if order_id in self.rows_by_id
        ]
        return rows, len(pages_touched)

    def page_count(self) -> int:
        return len(self.pages)

    def row_count(self) -> int:
        return len(self.rows_by_id)


# ---------------------------------------------------------------------------
# Simplified B-Tree
# ---------------------------------------------------------------------------

@dataclass
class BTreeNode:
    leaf: bool
    keys: list[Any] = field(default_factory=list)
    values: list[list[int]] = field(default_factory=list)
    children: list["BTreeNode"] = field(default_factory=list)


class BTreeIndex:
    """
    A simplified B-Tree index.

    A real database B-Tree has engine-specific page formats, sibling links,
    latching, WAL interaction, concurrency controls, visibility rules, and
    buffer-cache behavior. This model focuses on the logical search structure.

    Each key maps to a list of order IDs. Duplicate keys therefore model a
    non-unique SQL index.
    """

    def __init__(self, name: str, key_function, max_keys: int = 4) -> None:
        if max_keys < 3:
            raise ValueError("max_keys must be at least 3")

        self.name = name
        self.key_function = key_function
        self.max_keys = max_keys
        self.root = BTreeNode(leaf=True)
        self.order_to_key: dict[int, Any] = {}
        self.entry_count = 0

    def insert(self, row: Order) -> None:
        key = self.key_function(row)
        order_id = row.order_id

        if order_id in self.order_to_key:
            self.delete(order_id)

        self.order_to_key[order_id] = key
        self.entry_count += 1

        if len(self.root.keys) >= self.max_keys:
            old_root = self.root
            self.root = BTreeNode(
                leaf=False,
                children=[old_root],
            )
            self._split_child(self.root, 0)

        self._insert_non_full(self.root, key, order_id)

    def delete(self, order_id: int) -> None:
        """
        Deletion is simplified by rebuilding the tree.

        Production B-Trees perform structural deletion and node rebalancing.
        Rebuilding here keeps the example focused on lookup and maintenance
        rather than reproducing an entire storage-engine implementation.
        """
        if order_id not in self.order_to_key:
            return

        remaining = [
            (existing_id, key)
            for existing_id, key in self.order_to_key.items()
            if existing_id != order_id
        ]

        self.order_to_key.pop(order_id)
        self.entry_count -= 1
        self.root = BTreeNode(leaf=True)

        for existing_id, key in remaining:
            if len(self.root.keys) >= self.max_keys:
                old_root = self.root
                self.root = BTreeNode(leaf=False, children=[old_root])
                self._split_child(self.root, 0)
            self._insert_non_full(self.root, key, existing_id)

    def _split_child(self, parent: BTreeNode, index: int) -> None:
        child = parent.children[index]
        midpoint = len(child.keys) // 2

        promoted_key = child.keys[midpoint]
        promoted_values = child.values[midpoint]

        right = BTreeNode(leaf=child.leaf)
        right.keys = child.keys[midpoint + 1 :]
        right.values = child.values[midpoint + 1 :]

        if not child.leaf:
            split_position = midpoint + 1
            right.children = child.children[split_position:]
            child.children = child.children[:split_position]

        child.keys = child.keys[:midpoint]
        child.values = child.values[:midpoint]

        parent.keys.insert(index, promoted_key)
        parent.values.insert(index, promoted_values)
        parent.children.insert(index + 1, right)

    def _insert_non_full(
        self,
        node: BTreeNode,
        key: Any,
        order_id: int,
    ) -> None:
        if node.leaf:
            position = bisect_left(node.keys, key)

            if position < len(node.keys) and node.keys[position] == key:
                node.values[position].append(order_id)
                return

            node.keys.insert(position, key)
            node.values.insert(position, [order_id])
            return

        position = bisect_right(node.keys, key)

        child = node.children[position]

        if len(child.keys) >= self.max_keys:
            self._split_child(node, position)

            if key > node.keys[position]:
                position += 1
            elif key == node.keys[position]:
                node.values[position].append(order_id)
                return

        self._insert_non_full(node.children[position], key, order_id)

    def _find_node(self, key: Any) -> tuple[Optional[BTreeNode], int, int]:
        """
        Returns the matching node, key position, and logical B-Tree node visits.
        """
        node = self.root
        visits = 0

        while True:
            visits += 1
            position = bisect_left(node.keys, key)

            if position < len(node.keys) and node.keys[position] == key:
                return node, position, visits

            if node.leaf:
                return None, -1, visits

            node = node.children[position]

    def equality_lookup(self, key: Any) -> tuple[list[int], int]:
        node, position, visits = self._find_node(key)

        if node is None:
            return [], visits

        return list(node.values[position]), visits

    def _range_lookup_node(
        self,
        node: BTreeNode,
        lower: Any,
        upper: Any,
        result: list[int],
        visits: list[int],
    ) -> None:
        visits[0] += 1

        if node.leaf:
            start = bisect_left(node.keys, lower)
            end = bisect_right(node.keys, upper)

            for values in node.values[start:end]:
                result.extend(values)
            return

        child_start = bisect_left(node.keys, lower)
        child_end = bisect_right(node.keys, upper)

        for child_index in range(child_start, child_end + 1):
            self._range_lookup_node(
                node.children[child_index],
                lower,
                upper,
                result,
                visits,
            )

        start = bisect_left(node.keys, lower)
        end = bisect_right(node.keys, upper)

        for values in node.values[start:end]:
            result.extend(values)

    def range_lookup(self, lower: Any, upper: Any) -> tuple[list[int], int]:
        if lower > upper:
            raise ValueError("lower bound cannot exceed upper bound")

        result: list[int] = []
        visits = [0]

        self._range_lookup_node(
            self.root,
            lower,
            upper,
            result,
            visits,
        )

        return result, visits[0]

    def all_keys(self) -> list[Any]:
        result: list[Any] = []

        def walk(node: BTreeNode) -> None:
            if node.leaf:
                result.extend(node.keys)
                return

            for index, key in enumerate(node.keys):
                walk(node.children[index])
                result.append(key)

            walk(node.children[-1])

        walk(self.root)
        return result

    def height(self) -> int:
        height = 1
        node = self.root

        while not node.leaf:
            height += 1
            node = node.children[0]

        return height

    def describe(self) -> str:
        return (
            f"{self.name}: entries={self.entry_count}, "
            f"height={self.height()}, max_keys_per_node={self.max_keys}"
        )


# ---------------------------------------------------------------------------
# Composite B-Tree
# ---------------------------------------------------------------------------

class CompositeBTreeIndex:
    """
    Models a composite SQL index such as:

        CREATE INDEX idx_customer_date
        ON orders(customer_id, order_date);

    The key ordering is lexicographic. This illustrates the leftmost-prefix
    property: customer_id can be searched efficiently by itself, and a
    customer_id + order_date predicate can use both columns as a contiguous
    key range. A predicate only on order_date does not form a leading range.
    """

    def __init__(self, name: str, columns: tuple[str, str]) -> None:
        self.name = name
        self.columns = columns
        self.entries: list[tuple[tuple[Any, Any], int]] = []

    def build(self, rows: Iterable[Order]) -> None:
        self.entries = sorted(
            (
                (
                    (
                        getattr(row, self.columns[0]),
                        getattr(row, self.columns[1]),
                    ),
                    row.order_id,
                )
            )
            for row in rows
        )

    def customer_date_range(
        self,
        customer_id: int,
        start_date: int,
        end_date: int,
    ) -> list[int]:
        lower = (customer_id, start_date)
        upper = (customer_id, end_date)

        keys = [key for key, _ in self.entries]
        start = bisect_left(keys, lower)
        end = bisect_right(keys, upper)

        return [order_id for _, order_id in self.entries[start:end]]

    def customer_lookup(self, customer_id: int) -> list[int]:
        lower = (customer_id, float("-inf"))
        upper = (customer_id, float("inf"))

        keys = [key for key, _ in self.entries]
        start = bisect_left(keys, lower)
        end = bisect_right(keys, upper)

        return [order_id for _, order_id in self.entries[start:end]]

    def order_date_only_lookup_is_not_leftmost(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Query planning model
# ---------------------------------------------------------------------------

@dataclass
class QueryPlan:
    access_path: str
    estimated_rows: int
    estimated_page_reads: int
    index_name: Optional[str]
    reason: str

    def display(self) -> str:
        index = self.index_name or "none"
        return (
            f"access={self.access_path}, index={index}, "
            f"estimated_rows={self.estimated_rows}, "
            f"estimated_page_reads={self.estimated_page_reads}, "
            f"reason={self.reason}"
        )


class QueryPlanner:
    """
    A teaching-oriented cost model.

    Real optimizers use statistics, histograms, correlation estimates,
    visibility information, cache effects, operator costs, join algorithms,
    parallelism, and engine-specific cost formulas. This planner deliberately
    exposes only the factors needed to understand why an index can help.
    """

    def __init__(
        self,
        table: OrdersTable,
        indexes: dict[str, BTreeIndex],
    ) -> None:
        self.table = table
        self.indexes = indexes

    def choose_customer_plan(self, customer_id: int) -> QueryPlan:
        row_count = self.table.row_count()
        page_count = self.table.page_count()

        index = self.indexes["idx_customer"]

        matching_ids, tree_visits = index.equality_lookup(customer_id)
        estimated_rows = len(matching_ids)

        if estimated_rows == 0:
            return QueryPlan(
                access_path="Index Seek",
                estimated_rows=0,
                estimated_page_reads=tree_visits,
                index_name=index.name,
                reason="The index can prove that no matching key exists.",
            )

        _, table_pages = self.table.fetch_rows(matching_ids)
        index_cost = tree_visits + table_pages
        scan_cost = page_count

        if index_cost < scan_cost:
            return QueryPlan(
                access_path="Index Seek + Row Lookup",
                estimated_rows=estimated_rows,
                estimated_page_reads=index_cost,
                index_name=index.name,
                reason=(
                    "The selective customer_id predicate reaches fewer "
                    "pages through the index than scanning the table."
                ),
            )

        return QueryPlan(
            access_path="Full Table Scan",
            estimated_rows=estimated_rows,
            estimated_page_reads=scan_cost,
            index_name=None,
            reason=(
                "The predicate matches enough rows that random table-page "
                "access is not cheaper than scanning all pages."
            ),
        )

    def choose_status_plan(self, status: str) -> QueryPlan:
        index = self.indexes["idx_status"]
        matching_ids, tree_visits = index.equality_lookup(status)
        _, table_pages = self.table.fetch_rows(matching_ids)

        scan_cost = self.table.page_count()
        index_cost = tree_visits + table_pages

        if index_cost < scan_cost:
            return QueryPlan(
                access_path="Index Seek + Row Lookup",
                estimated_rows=len(matching_ids),
                estimated_page_reads=index_cost,
                index_name=index.name,
                reason="Status is selective enough for this dataset.",
            )

        return QueryPlan(
            access_path="Full Table Scan",
            estimated_rows=len(matching_ids),
            estimated_page_reads=scan_cost,
            index_name=None,
            reason=(
                "Status has low selectivity in this dataset, so the index "
                "would still require many table pages."
            ),
        )


# ---------------------------------------------------------------------------
# Covering index model
# ---------------------------------------------------------------------------

class CoveringCustomerIndex:
    """
    Models an index whose leaf entries contain enough projected data to answer
    a query without visiting the base table.

    Conceptually similar to:

        CREATE INDEX idx_customer_covering
        ON orders(customer_id)
        INCLUDE (status, total_amount);

    The exact INCLUDE syntax differs among SQL engines, so the simulation
    describes the storage idea rather than claiming universal syntax.
    """

    def __init__(self) -> None:
        self.entries: dict[int, list[tuple[int, str, float]]] = defaultdict(list)

    def build(self, rows: Iterable[Order]) -> None:
        self.entries.clear()

        for row in rows:
            self.entries[row.customer_id].append(
                (row.order_id, row.status, row.total_amount)
            )

        for values in self.entries.values():
            values.sort()

    def query(self, customer_id: int) -> tuple[list[tuple[int, str, float]], int]:
        values = list(self.entries.get(customer_id, []))
        index_pages = max(1, ceil(len(values) / 6)) if values else 1
        return values, index_pages


# ---------------------------------------------------------------------------
# Index statistics and selectivity
# ---------------------------------------------------------------------------

def index_statistics(rows: Iterable[Order], field_name: str) -> dict[str, Any]:
    values = [getattr(row, field_name) for row in rows]
    counts = Counter(values)

    distinct = len(counts)
    total = len(values)

    return {
        "column": field_name,
        "rows": total,
        "distinct_values": distinct,
        "distinct_ratio": distinct / total if total else 0.0,
        "most_common": counts.most_common(5),
        "average_frequency": total / distinct if distinct else 0.0,
    }


def explain_selectivity(rows: list[Order], field_name: str, value: Any) -> str:
    total = len(rows)

    if total == 0:
        return "No rows exist, so selectivity cannot be measured."

    matches = sum(getattr(row, field_name) == value for row in rows)
    fraction = matches / total

    return (
        f"{field_name}={value!r}: {matches}/{total} rows match "
        f"({fraction:.2%}). Lower fractions generally provide stronger "
        f"filtering potential for equality predicates."
    )


# ---------------------------------------------------------------------------
# Query execution examples
# ---------------------------------------------------------------------------

def generate_orders(count: int, seed: int = 42) -> list[Order]:
    random = Random(seed)

    statuses = ["PAID", "PENDING", "SHIPPED", "CANCELLED"]

    rows: list[Order] = []

    for order_id in range(1, count + 1):
        customer_id = random.randint(1, max(10, count // 15))

        # The date is represented as an integer YYYYMMDD so the B-Tree
        # comparison remains simple and deterministic.
        year = random.choice([2024, 2025, 2026])
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        order_date = year * 10000 + month * 100 + day

        status = random.choices(
            statuses,
            weights=[55, 20, 20, 5],
            k=1,
        )[0]

        amount = round(random.uniform(25.0, 2500.0), 2)

        rows.append(
            Order(
                order_id=order_id,
                customer_id=customer_id,
                status=status,
                order_date=order_date,
                total_amount=amount,
            )
        )

    return rows


def build_indexes(
    table: OrdersTable,
    rows: list[Order],
) -> tuple[dict[str, BTreeIndex], CompositeBTreeIndex, CoveringCustomerIndex]:
    indexes = {
        "idx_customer": BTreeIndex(
            name="idx_customer",
            key_function=lambda row: row.customer_id,
            max_keys=8,
        ),
        "idx_status": BTreeIndex(
            name="idx_status",
            key_function=lambda row: row.status,
            max_keys=6,
        ),
        "idx_order_date": BTreeIndex(
            name="idx_order_date",
            key_function=lambda row: row.order_date,
            max_keys=8,
        ),
    }

    for row in rows:
        table.insert(row)

        for index in indexes.values():
            index.insert(row)

    composite = CompositeBTreeIndex(
        name="idx_customer_order_date",
        columns=("customer_id", "order_date"),
    )
    composite.build(rows)

    covering = CoveringCustomerIndex()
    covering.build(rows)

    return indexes, composite, covering


def print_heading(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def demonstrate_basic_btree(
    indexes: dict[str, BTreeIndex],
) -> None:
    print_heading("B-Tree equality lookup")

    index = indexes["idx_customer"]
    customer_id = 10

    order_ids, node_visits = index.equality_lookup(customer_id)

    print(index.describe())
    print(f"customer_id={customer_id}")
    print(f"matching order IDs: {order_ids[:12]}")
    print(f"matching row count: {len(order_ids)}")
    print(f"B-Tree nodes visited: {node_visits}")

    print(
        "\nA B-Tree avoids checking every row because its ordered keys "
        "discard large portions of the search space at each internal node."
    )


def demonstrate_full_scan_vs_index(
    table: OrdersTable,
    indexes: dict[str, BTreeIndex],
) -> None:
    print_heading("Full table scan versus indexed lookup")

    target_customer = 10

    scan_rows, scan_pages = table.full_scan(
        lambda row: row.customer_id == target_customer
    )

    index_ids, tree_visits = indexes["idx_customer"].equality_lookup(
        target_customer
    )
    index_rows, table_pages = table.fetch_rows(index_ids)

    print(f"Table rows: {table.row_count()}")
    print(f"Table pages: {table.page_count()}")
    print(f"Full scan matches: {len(scan_rows)}")
    print(f"Full scan table pages read: {scan_pages}")
    print(f"Index matches: {len(index_rows)}")
    print(f"B-Tree nodes visited: {tree_visits}")
    print(f"Table pages fetched after index lookup: {table_pages}")
    print(f"Approximate indexed page accesses: {tree_visits + table_pages}")

    if tree_visits + table_pages < scan_pages:
        print("For this predicate and dataset, the indexed path touches fewer pages.")
    else:
        print("For this predicate and dataset, the scan is competitive.")


def demonstrate_range_query(
    table: OrdersTable,
    indexes: dict[str, BTreeIndex],
) -> None:
    print_heading("B-Tree range query")

    lower = 20260101
    upper = 20260331

    order_ids, node_visits = indexes["idx_order_date"].range_lookup(
        lower,
        upper,
    )
    rows, table_pages = table.fetch_rows(order_ids)

    print(f"Date range: {lower} through {upper}")
    print(f"Matching rows: {len(rows)}")
    print(f"B-Tree nodes visited: {node_visits}")
    print(f"Table pages fetched: {table_pages}")

    # B-Trees are particularly useful for ordered ranges because their leaf
    # keys can be traversed in sorted order rather than testing every value.
    dates = sorted(row.order_date for row in rows)

    print(
        f"First returned date: {dates[0] if dates else 'none'}; "
        f"last returned date: {dates[-1] if dates else 'none'}"
    )


def demonstrate_composite_index(
    table: OrdersTable,
    composite: CompositeBTreeIndex,
) -> None:
    print_heading("Composite B-Tree and leftmost-prefix behavior")

    customer_id = 10
    start_date = 20250101
    end_date = 20251231

    ids = composite.customer_date_range(
        customer_id,
        start_date,
        end_date,
    )

    rows, pages = table.fetch_rows(ids)

    print(f"Index: {composite.name}")
    print(f"Predicate: customer_id={customer_id}")
    print(f"AND order_date BETWEEN {start_date} AND {end_date}")
    print(f"Matching rows: {len(rows)}")
    print(f"Base-table pages fetched: {pages}")

    customer_only_ids = composite.customer_lookup(customer_id)
    print(f"Customer-only lookup through same leading column: {len(customer_only_ids)} rows")

    print(
        "A predicate on order_date alone does not have customer_id as its "
        "leading key, so this composite ordering does not provide the same "
        "direct range access for that predicate."
    )


def demonstrate_covering_index(
    covering: CoveringCustomerIndex,
) -> None:
    print_heading("Covering index and index-only access")

    customer_id = 10
    results, estimated_index_pages = covering.query(customer_id)

    print(f"customer_id={customer_id}")
    print(f"Rows returned directly from index payload: {len(results)}")
    print(f"Estimated index pages touched: {estimated_index_pages}")

    for order_id, status, amount in results[:8]:
        print(
            f"order_id={order_id}, status={status}, "
            f"total_amount={amount:.2f}"
        )

    print(
        "\nBecause the simulated index stores the projected status and amount, "
        "the query does not need a base-table lookup for those columns."
    )


def demonstrate_query_plans(
    table: OrdersTable,
    indexes: dict[str, BTreeIndex],
) -> None:
    print_heading("Query-plan reasoning")

    planner = QueryPlanner(table, indexes)

    customer_plan = planner.choose_customer_plan(10)
    status_plan = planner.choose_status_plan("PAID")

    print("Customer predicate:")
    print(customer_plan.display())

    print("\nStatus predicate:")
    print(status_plan.display())

    print(
        "\nThe same index structure can have very different value depending "
        "on selectivity and the number of table pages ultimately required."
    )


def demonstrate_statistics(rows: list[Order]) -> None:
    print_heading("Cardinality and selectivity")

    for column in ["customer_id", "status", "order_date"]:
        stats = index_statistics(rows, column)

        print(f"\nColumn: {column}")
        print(f"Rows: {stats['rows']}")
        print(f"Distinct values: {stats['distinct_values']}")
        print(f"Distinct ratio: {stats['distinct_ratio']:.2%}")
        print(f"Average frequency: {stats['average_frequency']:.2f}")
        print(f"Most common values: {stats['most_common']}")

    print("\n" + explain_selectivity(rows, "status", "PAID"))
    print(explain_selectivity(rows, "status", "CANCELLED"))


def demonstrate_maintenance(
    table: OrdersTable,
    indexes: dict[str, BTreeIndex],
) -> None:
    print_heading("Index maintenance after an UPDATE")

    order_id = 7
    before = table.rows_by_id[order_id]

    print(
        f"Before update: order_id={order_id}, "
        f"customer_id={before.customer_id}, status={before.status}"
    )

    old_customer_ids, _ = indexes["idx_customer"].equality_lookup(
        before.customer_id
    )

    updated = table.update(
        order_id,
        customer_id=9999,
    )

    # An indexed column update changes the index key. Real databases perform
    # index maintenance as part of the transaction.
    indexes["idx_customer"].delete(order_id)
    indexes["idx_customer"].insert(updated)

    new_customer_ids, _ = indexes["idx_customer"].equality_lookup(9999)

    print(
        f"After update: order_id={order_id}, "
        f"customer_id={updated.customer_id}"
    )
    print(f"Old customer index still contains row: {order_id in old_customer_ids}")
    print(f"New customer index contains row: {order_id in new_customer_ids}")

    print(
        "\nThis demonstrates the core write trade-off: an index accelerates "
        "some reads, but changing an indexed column requires index maintenance."
    )


def demonstrate_edge_cases(
    table: OrdersTable,
    indexes: dict[str, BTreeIndex],
) -> None:
    print_heading("Edge cases and failure conditions")

    missing_key, visits = indexes["idx_customer"].equality_lookup(-12345)
    print(f"Missing key lookup returned {missing_key} after {visits} node visits.")

    try:
        indexes["idx_order_date"].range_lookup(20261231, 20260101)
    except ValueError as exc:
        print(f"Invalid range rejected: {exc}")

    duplicate_order = next(iter(table.rows_by_id.values()))

    try:
        table.insert(duplicate_order)
    except ValueError as exc:
        print(f"Duplicate primary identifier rejected: {exc}")

    try:
        OrdersTable(rows_per_page=0)
    except ValueError as exc:
        print(f"Invalid table configuration rejected: {exc}")


def discuss_performance() -> None:
    print_heading("Performance characteristics")

    print(
        "B-Tree search is approximately logarithmic in the number of indexed "
        "keys when the tree remains balanced. Database performance is not "
        "determined by CPU comparisons alone: page reads, cache residency, "
        "random versus sequential access, and result-set size matter."
    )

    print(
        "An index can be less useful when a predicate returns a large fraction "
        "of the table, when the indexed column has very low selectivity, or "
        "when the query needs many columns that force many base-table lookups."
    )

    print(
        "Indexes also consume storage and add write work. INSERT, DELETE, and "
        "UPDATE operations affecting indexed columns must maintain index "
        "entries. Excessive indexing can therefore increase write latency and "
        "maintenance cost."
    )

    print(
        "A composite index should reflect actual predicate and ordering "
        "patterns. Column order changes which predicates can form efficient "
        "leading ranges."
    )


def main() -> None:
    print_heading("SQL Indexes: B-Tree Indexes and Query Performance")

    rows = generate_orders(count=240, seed=42)
    table = OrdersTable(rows_per_page=8)

    indexes, composite, covering = build_indexes(table, rows)

    print(f"Loaded {table.row_count()} orders into {table.page_count()} table pages.")

    demonstrate_basic_btree(indexes)
    demonstrate_full_scan_vs_index(table, indexes)
    demonstrate_range_query(table, indexes)
    demonstrate_composite_index(table, composite)
    demonstrate_covering_index(covering)
    demonstrate_query_plans(table, indexes)
    demonstrate_statistics(rows)
    demonstrate_maintenance(table, indexes)
    demonstrate_edge_cases(table, indexes)
    discuss_performance()

    print_heading("Operational design considerations")

    print(
        "Index definitions should be driven by measured query patterns rather "
        "than by the assumption that every frequently queried column needs an "
        "index. Query plans should be inspected with the database engine's "
        "EXPLAIN facilities, and statistics should be kept current."
    )

    print(
        "The simulation intentionally omits transaction isolation, locking, "
        "MVCC visibility, WAL, buffer pools, page splits under concurrent "
        "writes, vacuuming, and engine-specific optimizer behavior. Those "
        "features influence production performance but are separate from the "
        "core B-Tree access pattern demonstrated here."
    )


if __name__ == "__main__":
    main()
