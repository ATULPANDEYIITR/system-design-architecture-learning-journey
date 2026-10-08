"""
Database Partitioning: Horizontal and Vertical Partitioning

A self-contained executable demonstration of:
- Horizontal partitioning (row partitioning)
- Range, list, and hash partitioning concepts
- Vertical partitioning (column partitioning)
- Partition routing and pruning
- Composite partitioning
- Query locality
- Constraints and validation
- Operational trade-offs
- A small in-memory partition manager
- SQL DDL generation for PostgreSQL
- Performance and production considerations

The implementation uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from hashlib import sha256
from typing import Any, Iterable


class PartitioningType(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    COMPOSITE = "composite"


class PartitioningError(Exception):
    """Base exception for partitioning-related failures."""


class PartitionNotFoundError(PartitioningError):
    """Raised when a row cannot be routed to a partition."""


class PartitionConstraintError(PartitioningError):
    """Raised when a row violates a partition boundary."""


@dataclass(frozen=True)
class Order:
    order_id: int
    customer_id: int
    order_date: date
    region: str
    status: str
    total_amount: float
    payment_token: str
    shipping_address: str
    notes: str = ""


@dataclass
class RowPartition:
    name: str
    minimum: date | None = None
    maximum: date | None = None
    rows: list[Order] = field(default_factory=list)

    def accepts(self, order_date: date) -> bool:
        lower_ok = self.minimum is None or order_date >= self.minimum
        upper_ok = self.maximum is None or order_date < self.maximum
        return lower_ok and upper_ok

    def insert(self, order: Order) -> None:
        if not self.accepts(order.order_date):
            raise PartitionConstraintError(
                f"{order.order_id} does not belong to {self.name}"
            )
        self.rows.append(order)


class HorizontalPartitionManager:
    """
    Models range-partitioned orders.

    PostgreSQL-style RANGE semantics are used:
        lower bound <= value < upper bound

    This means adjacent partitions can meet without overlapping.
    """

    def __init__(self, partitions: Iterable[RowPartition]):
        self.partitions = list(partitions)
        self._validate_boundaries()

    def _validate_boundaries(self) -> None:
        ordered = sorted(
            self.partitions,
            key=lambda p: p.minimum or date.min,
        )

        previous_max: date | None = None

        for partition in ordered:
            if (
                partition.minimum is not None
                and partition.maximum is not None
                and partition.minimum >= partition.maximum
            ):
                raise PartitioningError(
                    f"Invalid range in {partition.name}"
                )

            if (
                previous_max is not None
                and partition.minimum is not None
                and partition.minimum < previous_max
            ):
                raise PartitioningError("Overlapping horizontal partitions")

            previous_max = partition.maximum

    def locate(self, order_date: date) -> RowPartition:
        for partition in self.partitions:
            if partition.accepts(order_date):
                return partition
        raise PartitionNotFoundError(
            f"No partition covers order date {order_date}"
        )

    def insert(self, order: Order) -> str:
        partition = self.locate(order.order_date)
        partition.insert(order)
        return partition.name

    def query_by_date_range(
        self,
        start: date,
        end: date,
    ) -> tuple[list[str], list[Order]]:
        """
        Demonstrates partition pruning.

        A real database optimizer can inspect partition boundaries and
        avoid scanning partitions that cannot contain matching rows.
        """
        if start >= end:
            raise ValueError("start must be earlier than end")

        selected: list[RowPartition] = []

        for partition in self.partitions:
            lower = partition.minimum or date.min
            upper = partition.maximum or date.max

            # Intervals [lower, upper) and [start, end) overlap when:
            if lower < end and start < upper:
                selected.append(partition)

        results: list[Order] = []

        for partition in selected:
            results.extend(
                order
                for order in partition.rows
                if start <= order.order_date < end
            )

        return [p.name for p in selected], results

    def count_rows(self) -> dict[str, int]:
        return {partition.name: len(partition.rows) for partition in self.partitions}


@dataclass(frozen=True)
class CustomerProfile:
    customer_id: int
    name: str
    email: str
    phone: str
    address: str
    date_of_birth: date


@dataclass(frozen=True)
class CustomerOperationalView:
    """
    A vertical partition containing frequently accessed operational columns.

    Sensitive or rarely accessed attributes remain in the other partition.
    """

    customer_id: int
    name: str
    email: str
    phone: str


@dataclass(frozen=True)
class CustomerSensitiveView:
    """
    A vertical partition containing less frequently accessed attributes.

    In a production system this physical separation can support narrower
    indexes, reduced I/O, independent access controls, and different
    storage strategies.
    """

    customer_id: int
    address: str
    date_of_birth: date


class VerticalCustomerStore:
    """
    Demonstrates vertical partitioning by physically modeling two column
    groups connected through the same primary key.
    """

    def __init__(self) -> None:
        self.operational: dict[int, CustomerOperationalView] = {}
        self.sensitive: dict[int, CustomerSensitiveView] = {}

    def insert(self, customer: CustomerProfile) -> None:
        if customer.customer_id in self.operational:
            raise PartitionConstraintError(
                f"Duplicate customer ID {customer.customer_id}"
            )

        self.operational[customer.customer_id] = CustomerOperationalView(
            customer.customer_id,
            customer.name,
            customer.email,
            customer.phone,
        )

        self.sensitive[customer.customer_id] = CustomerSensitiveView(
            customer.customer_id,
            customer.address,
            customer.date_of_birth,
        )

    def operational_lookup(self, customer_id: int) -> CustomerOperationalView:
        try:
            return self.operational[customer_id]
        except KeyError as exc:
            raise KeyError(f"Customer {customer_id} does not exist") from exc

    def full_lookup(self, customer_id: int) -> CustomerProfile:
        operational = self.operational_lookup(customer_id)

        try:
            sensitive = self.sensitive[customer_id]
        except KeyError as exc:
            raise PartitionConstraintError(
                f"Vertical partition integrity failure for customer {customer_id}"
            ) from exc

        return CustomerProfile(
            customer_id=operational.customer_id,
            name=operational.name,
            email=operational.email,
            phone=operational.phone,
            address=sensitive.address,
            date_of_birth=sensitive.date_of_birth,
        )

    def delete(self, customer_id: int) -> None:
        self.operational.pop(customer_id, None)
        self.sensitive.pop(customer_id, None)


class HashPartitioner:
    """
    Hash partitioning distributes rows according to a deterministic hash
    instead of a business range.

    It is useful when the workload benefits from spreading writes and reads
    across partitions without a natural range boundary.
    """

    def __init__(self, partition_count: int):
        if partition_count <= 0:
            raise ValueError("partition_count must be positive")
        self.partition_count = partition_count

    def partition_for(self, key: Any) -> int:
        digest = sha256(str(key).encode("utf-8")).digest()
        number = int.from_bytes(digest[:8], "big")
        return number % self.partition_count


class ListPartitioner:
    """
    Demonstrates list partitioning where explicit business categories map
    to partitions.
    """

    def __init__(self, mapping: dict[str, str], default: str | None = None):
        self.mapping = dict(mapping)
        self.default = default

    def partition_for(self, value: str) -> str:
        if value in self.mapping:
            return self.mapping[value]

        if self.default is not None:
            return self.default

        raise PartitionNotFoundError(
            f"No list partition exists for value {value!r}"
        )


@dataclass
class MonthlyOrderPartition:
    year: int
    month: int
    rows: list[Order] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"orders_{self.year}_{self.month:02d}"

    def accepts(self, value: date) -> bool:
        return value.year == self.year and value.month == self.month


class CompositePartitionManager:
    """
    Demonstrates two-level partitioning:
        first level: RANGE by order date
        second level: HASH by customer ID

    Composite partitioning is useful when a single partitioning dimension
    does not adequately distribute both time locality and workload.
    """

    def __init__(self, hash_buckets: int):
        if hash_buckets < 2:
            raise ValueError("Composite partitioning needs multiple buckets")

        self.hash_partitioner = HashPartitioner(hash_buckets)
        self.partitions: dict[tuple[int, int, int], list[Order]] = {}

    def insert(self, order: Order) -> tuple[int, int, int]:
        bucket = self.hash_partitioner.partition_for(order.customer_id)

        key = (
            order.order_date.year,
            order.order_date.month,
            bucket,
        )

        self.partitions.setdefault(key, []).append(order)
        return key

    def query(
        self,
        year: int,
        month: int,
        customer_id: int,
    ) -> list[Order]:
        bucket = self.hash_partitioner.partition_for(customer_id)

        return [
            order
            for order in self.partitions.get((year, month, bucket), [])
            if order.customer_id == customer_id
        ]


def demonstrate_range_partitioning() -> None:
    print("\n=== Horizontal RANGE Partitioning ===")

    manager = HorizontalPartitionManager(
        [
            RowPartition(
                "orders_2026_q1",
                date(2026, 1, 1),
                date(2026, 4, 1),
            ),
            RowPartition(
                "orders_2026_q2",
                date(2026, 4, 1),
                date(2026, 7, 1),
            ),
            RowPartition(
                "orders_2026_q3",
                date(2026, 7, 1),
                date(2026, 10, 1),
            ),
            RowPartition(
                "orders_2026_q4",
                date(2026, 10, 1),
                date(2027, 1, 1),
            ),
        ]
    )

    orders = [
        Order(
            1001,
            501,
            date(2026, 2, 15),
            "NORTH",
            "PAID",
            1250.50,
            "tok_a",
            "Lucknow",
        ),
        Order(
            1002,
            502,
            date(2026, 5, 20),
            "SOUTH",
            "SHIPPED",
            760.00,
            "tok_b",
            "Bengaluru",
        ),
        Order(
            1003,
            503,
            date(2026, 8, 12),
            "WEST",
            "PAID",
            2100.00,
            "tok_c",
            "Mumbai",
        ),
        Order(
            1004,
            504,
            date(2026, 11, 3),
            "EAST",
            "PENDING",
            450.00,
            "tok_d",
            "Kolkata",
        ),
    ]

    for order in orders:
        partition = manager.insert(order)
        print(f"Order {order.order_id} routed to {partition}")

    selected, results = manager.query_by_date_range(
        date(2026, 4, 1),
        date(2026, 10, 1),
    )

    print("Partitions touched by date-range query:", selected)
    print("Matching order IDs:", [order.order_id for order in results])
    print("Rows by partition:", manager.count_rows())


def demonstrate_vertical_partitioning() -> None:
    print("\n=== Vertical Partitioning ===")

    store = VerticalCustomerStore()

    customers = [
        CustomerProfile(
            501,
            "Asha Sharma",
            "asha@example.com",
            "+91-9000000001",
            "Lucknow",
            date(1992, 3, 14),
        ),
        CustomerProfile(
            502,
            "Rohan Mehta",
            "rohan@example.com",
            "+91-9000000002",
            "Bengaluru",
            date(1988, 8, 22),
        ),
    ]

    for customer in customers:
        store.insert(customer)

    # A frequent customer-support query can read only the narrow
    # operational partition rather than loading address and DOB columns.
    print("Operational lookup:", store.operational_lookup(501))

    # A request requiring all customer attributes performs a logical join
    # on the shared customer_id.
    print("Full lookup:", store.full_lookup(501))

    # Referential integrity between vertical partitions matters. Removing
    # only one side would create a broken logical row.
    store.delete(502)
    try:
        store.full_lookup(502)
    except KeyError as exc:
        print("Expected lookup failure:", exc)


def demonstrate_hash_partitioning() -> None:
    print("\n=== HASH Partitioning ===")

    partitioner = HashPartitioner(4)

    for customer_id in [501, 502, 503, 504, 505, 506]:
        print(
            f"Customer {customer_id} -> "
            f"bucket {partitioner.partition_for(customer_id)}"
        )

    print(
        "Hash partitioning deliberately avoids depending on chronological "
        "ranges, but changing the number of buckets can require data "
        "redistribution unless the database uses a compatible strategy."
    )


def demonstrate_list_partitioning() -> None:
    print("\n=== LIST Partitioning ===")

    partitioner = ListPartitioner(
        {
            "NORTH": "orders_north",
            "SOUTH": "orders_south",
            "EAST": "orders_east",
            "WEST": "orders_west",
        },
        default="orders_other",
    )

    for region in ["NORTH", "WEST", "CENTRAL"]:
        print(f"{region} -> {partitioner.partition_for(region)}")


def demonstrate_composite_partitioning() -> None:
    print("\n=== Composite RANGE + HASH Partitioning ===")

    manager = CompositePartitionManager(hash_buckets=4)

    orders = [
        Order(
            2001,
            701,
            date(2026, 9, 1),
            "NORTH",
            "PAID",
            100.00,
            "tok_x",
            "Delhi",
        ),
        Order(
            2002,
            702,
            date(2026, 9, 4),
            "NORTH",
            "PAID",
            200.00,
            "tok_y",
            "Delhi",
        ),
        Order(
            2003,
            701,
            date(2026, 9, 20),
            "NORTH",
            "SHIPPED",
            300.00,
            "tok_z",
            "Delhi",
        ),
    ]

    for order in orders:
        print(
            f"Order {order.order_id} -> "
            f"partition {manager.insert(order)}"
        )

    result = manager.query(2026, 9, 701)
    print("Customer 701 orders:", [order.order_id for order in result])


def generate_postgresql_partitioning_ddl() -> str:
    """
    Produces executable PostgreSQL DDL for a realistic range-partitioned
    order table and vertically partitioned customer data.
    """
    return """
CREATE TABLE IF NOT EXISTS orders (
    order_id       BIGINT NOT NULL,
    customer_id    BIGINT NOT NULL,
    order_date     DATE NOT NULL,
    region         TEXT NOT NULL,
    status         TEXT NOT NULL,
    total_amount   NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (order_id, order_date),
    CHECK (total_amount >= 0),
    CHECK (status IN ('PENDING', 'PAID', 'SHIPPED', 'CANCELLED'))
) PARTITION BY RANGE (order_date);

CREATE TABLE IF NOT EXISTS orders_2026_q3
    PARTITION OF orders
    FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');

CREATE TABLE IF NOT EXISTS orders_2026_q4
    PARTITION OF orders
    FOR VALUES FROM ('2026-10-01') TO ('2027-01-01');

CREATE INDEX IF NOT EXISTS idx_orders_customer_date
    ON orders (customer_id, order_date);

CREATE TABLE IF NOT EXISTS customer_operational (
    customer_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT
);

CREATE TABLE IF NOT EXISTS customer_sensitive (
    customer_id BIGINT PRIMARY KEY
        REFERENCES customer_operational(customer_id)
        ON DELETE CASCADE,
    address TEXT NOT NULL,
    date_of_birth DATE
);

CREATE VIEW customer_profile AS
SELECT
    o.customer_id,
    o.name,
    o.email,
    o.phone,
    s.address,
    s.date_of_birth
FROM customer_operational AS o
JOIN customer_sensitive AS s
    ON s.customer_id = o.customer_id;
""".strip()


def demonstrate_validation_and_failure() -> None:
    print("\n=== Boundary and Failure Conditions ===")

    manager = HorizontalPartitionManager(
        [
            RowPartition(
                "orders_before_april",
                date(2026, 1, 1),
                date(2026, 4, 1),
            ),
            RowPartition(
                "orders_after_april",
                date(2026, 4, 1),
                date(2027, 1, 1),
            ),
        ]
    )

    boundary_order = Order(
        9001,
        900,
        date(2026, 4, 1),
        "NORTH",
        "PENDING",
        10.0,
        "token",
        "Lucknow",
    )

    print(
        "Exact lower boundary routes to:",
        manager.insert(boundary_order),
    )

    try:
        manager.insert(
            Order(
                9002,
                901,
                date(2027, 1, 1),
                "NORTH",
                "PENDING",
                10.0,
                "token",
                "Lucknow",
            )
        )
    except PartitionNotFoundError as exc:
        print("Expected missing-partition failure:", exc)


def main() -> None:
    print("Database Partitioning Technical Demonstration")

    demonstrate_range_partitioning()
    demonstrate_vertical_partitioning()
    demonstrate_hash_partitioning()
    demonstrate_list_partitioning()
    demonstrate_composite_partitioning()
    demonstrate_validation_and_failure()

    print("\n=== PostgreSQL DDL Generated by the Model ===")
    print(generate_postgresql_partitioning_ddl())

    print("\n=== Production Design Notes ===")
    print(
        "Horizontal partitioning is primarily useful when rows can be "
        "isolated by a partition key such as time, tenant, region, or hash."
    )
    print(
        "Vertical partitioning separates columns so frequently accessed "
        "attributes can be read without loading wide or sensitive columns."
    )
    print(
        "Partitioning is not a substitute for indexing, normalization, "
        "query design, capacity planning, or appropriate data types."
    )


if __name__ == "__main__":
    main()
