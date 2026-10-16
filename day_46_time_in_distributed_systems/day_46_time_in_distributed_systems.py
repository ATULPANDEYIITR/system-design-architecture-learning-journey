from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple
import json
import random
import statistics


UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds")


def physical_seconds(value: datetime) -> float:
    return value.timestamp()


@dataclass(frozen=True)
class Event:
    event_id: str
    node_id: str
    kind: str
    physical_time: datetime
    logical_time: int
    vector_time: Dict[str, int]
    payload: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "node_id": self.node_id,
            "kind": self.kind,
            "physical_time": format_ts(self.physical_time),
            "logical_time": self.logical_time,
            "vector_time": self.vector_time,
            "payload": self.payload,
        }


class LamportClock:
    """Scalar logical clock.

    The clock does not estimate real time. It records causal ordering:
    if event A causally precedes event B, then L(A) < L(B).
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.value = 0

    def local_event(self) -> int:
        self.value += 1
        return self.value

    def send(self) -> int:
        self.value += 1
        return self.value

    def receive(self, received_timestamp: int) -> int:
        if received_timestamp < 0:
            raise ValueError("Lamport timestamps cannot be negative")
        self.value = max(self.value, received_timestamp) + 1
        return self.value


class VectorClock:
    """Vector clock for detecting causal relationships and concurrency."""

    def __init__(self, node_id: str, nodes: Iterable[str]):
        self.node_id = node_id
        self.clock = {node: 0 for node in sorted(set(nodes))}
        if node_id not in self.clock:
            raise ValueError("node_id must be present in the node set")

    def local_event(self) -> Dict[str, int]:
        self.clock[self.node_id] += 1
        return self.snapshot()

    def send(self) -> Dict[str, int]:
        return self.local_event()

    def receive(self, received: Dict[str, int]) -> Dict[str, int]:
        if set(received) != set(self.clock):
            raise ValueError("Vector clocks must use the same node membership")
        if any(value < 0 for value in received.values()):
            raise ValueError("Vector clock entries cannot be negative")

        for node in self.clock:
            self.clock[node] = max(self.clock[node], received[node])

        self.clock[self.node_id] += 1
        return self.snapshot()

    def snapshot(self) -> Dict[str, int]:
        return dict(self.clock)


def vector_compare(
    left: Dict[str, int], right: Dict[str, int]
) -> str:
    """Return BEFORE, AFTER, EQUAL, or CONCURRENT."""
    if set(left) != set(right):
        raise ValueError("Vector clocks must have identical dimensions")

    left_leq = all(left[node] <= right[node] for node in left)
    right_leq = all(right[node] <= left[node] for node in left)

    if left_leq and right_leq:
        return "EQUAL"
    if left_leq:
        return "BEFORE"
    if right_leq:
        return "AFTER"
    return "CONCURRENT"


@dataclass
class PhysicalClock:
    node_id: str
    offset: timedelta = timedelta(0)
    drift_rate_ppm: float = 0.0

    def read(self, reference: datetime) -> datetime:
        """Approximate a node's local wall clock.

        drift_rate_ppm represents a fractional rate error. A value of
        100 ppm means the local clock advances about 100 microseconds
        faster than an ideal clock per elapsed second.
        """
        elapsed = (reference - datetime(1970, 1, 1, tzinfo=UTC)).total_seconds()
        drift_seconds = elapsed * self.drift_rate_ppm / 1_000_000
        return reference + self.offset + timedelta(seconds=drift_seconds)


@dataclass
class DistributedNode:
    node_id: str
    physical_clock: PhysicalClock
    lamport: LamportClock
    vector: VectorClock
    events: List[Event] = field(default_factory=list)

    def local_event(self, event_id: str, kind: str, reference: datetime, payload: str = "") -> Event:
        physical = self.physical_clock.read(reference)
        logical = self.lamport.local_event()
        vector = self.vector.local_event()

        event = Event(
            event_id=event_id,
            node_id=self.node_id,
            kind=kind,
            physical_time=physical,
            logical_time=logical,
            vector_time=vector,
            payload=payload,
        )
        self.events.append(event)
        return event

    def send_event(
        self,
        event_id: str,
        reference: datetime,
        destination: str,
        payload: str = "",
    ) -> Tuple[Event, int, Dict[str, int]]:
        physical = self.physical_clock.read(reference)
        logical = self.lamport.send()
        vector = self.vector.send()

        event = Event(
            event_id=event_id,
            node_id=self.node_id,
            kind=f"SEND->{destination}",
            physical_time=physical,
            logical_time=logical,
            vector_time=vector,
            payload=payload,
        )
        self.events.append(event)
        return event, logical, vector

    def receive_event(
        self,
        event_id: str,
        reference: datetime,
        sender: str,
        sender_lamport: int,
        sender_vector: Dict[str, int],
        payload: str = "",
    ) -> Event:
        physical = self.physical_clock.read(reference)
        logical = self.lamport.receive(sender_lamport)
        vector = self.vector.receive(sender_vector)

        event = Event(
            event_id=event_id,
            node_id=self.node_id,
            kind=f"RECEIVE<-{sender}",
            physical_time=physical,
            logical_time=logical,
            vector_time=vector,
            payload=payload,
        )
        self.events.append(event)
        return event


def demonstrate_clock_skew() -> None:
    print("\n=== Physical Clock Skew ===")

    reference = datetime(2026, 10, 16, 5, 30, tzinfo=UTC)

    nodes = [
        PhysicalClock("api-a", timedelta(milliseconds=180), 12),
        PhysicalClock("api-b", timedelta(milliseconds=-95), -8),
        PhysicalClock("api-c", timedelta(milliseconds=40), 35),
    ]

    readings = [(clock.node_id, clock.read(reference)) for clock in nodes]

    for node_id, reading in readings:
        print(f"{node_id}: {format_ts(reading)}")

    earliest = min(readings, key=lambda item: item[1])
    latest = max(readings, key=lambda item: item[1])
    skew = latest[1] - earliest[1]

    print(f"Observed clock spread: {skew.total_seconds() * 1000:.3f} ms")
    print(
        "A wall-clock timestamp alone cannot prove causal ordering when "
        "the observed skew is comparable to the event separation."
    )


def demonstrate_lamport() -> None:
    print("\n=== Lamport Logical Clock ===")

    nodes = ["api-a", "api-b", "api-c"]

    clocks = {node: LamportClock(node) for node in nodes}

    a1 = clocks["api-a"].local_event()
    sent = clocks["api-a"].send()
    b1 = clocks["api-b"].receive(sent)
    c1 = clocks["api-c"].local_event()
    c2 = clocks["api-c"].receive(b1)

    print(f"api-a local event: L={a1}")
    print(f"api-a send event:   L={sent}")
    print(f"api-b receive:      L={b1}")
    print(f"api-c independent:  L={c1}")
    print(f"api-c receives:      L={c2}")

    print(
        "Lamport clocks preserve causal precedence, but two unrelated "
        "events can still have ordered scalar timestamps."
    )


def demonstrate_vector_clocks() -> None:
    print("\n=== Vector Clock Causality ===")

    nodes = ["api-a", "api-b"]

    a = VectorClock("api-a", nodes)
    b = VectorClock("api-b", nodes)

    a1 = a.local_event()
    message = a.send()
    b1 = b.receive(message)
    b2 = b.local_event()

    print(f"A local:      {a1}")
    print(f"A sends:      {message}")
    print(f"B receives:   {b1}")
    print(f"B local:      {b2}")

    print("A send vs B receive:", vector_compare(message, b1))

    concurrent_a = a.local_event()
    concurrent_b = b.local_event()

    print(f"A independent: {concurrent_a}")
    print(f"B independent: {concurrent_b}")
    print("Comparison:", vector_compare(concurrent_a, concurrent_b))

    if vector_compare(concurrent_a, concurrent_b) == "CONCURRENT":
        print(
            "The vector clocks correctly identify that neither independent "
            "event causally precedes the other."
        )


def demonstrate_timestamp_ordering() -> None:
    print("\n=== Timestamp Ordering and Skew ===")

    reference = datetime(2026, 10, 16, 5, 30, 10, tzinfo=UTC)

    node_a = PhysicalClock("writer-a", timedelta(milliseconds=80), 0)
    node_b = PhysicalClock("writer-b", timedelta(milliseconds=-80), 0)

    a_event = node_a.read(reference + timedelta(milliseconds=20))
    b_event = node_b.read(reference + timedelta(milliseconds=100))

    print("Actual event A reference time:", format_ts(reference + timedelta(milliseconds=20)))
    print("Actual event B reference time:", format_ts(reference + timedelta(milliseconds=100)))
    print("Observed A timestamp:", format_ts(a_event))
    print("Observed B timestamp:", format_ts(b_event))

    if a_event < b_event:
        print("Observed timestamps agree with the reference ordering.")
    else:
        print(
            "Observed wall-clock timestamps disagree with the reference "
            "ordering because clock offsets exceed the event separation."
        )


def simulate_ordered_event_log() -> List[Event]:
    print("\n=== Distributed Event Log ===")

    nodes = ["orders", "inventory", "payments"]

    distributed = {
        "orders": DistributedNode(
            "orders",
            PhysicalClock("orders", timedelta(milliseconds=35), 10),
            LamportClock("orders"),
            VectorClock("orders", nodes),
        ),
        "inventory": DistributedNode(
            "inventory",
            PhysicalClock("inventory", timedelta(milliseconds=-25), -4),
            LamportClock("inventory"),
            VectorClock("inventory", nodes),
        ),
        "payments": DistributedNode(
            "payments",
            PhysicalClock("payments", timedelta(milliseconds=60), 15),
            LamportClock("payments"),
            VectorClock("payments", nodes),
        ),
    }

    base = datetime(2026, 10, 16, 5, 30, 20, tzinfo=UTC)

    order_created = distributed["orders"].local_event(
        "evt-001",
        "ORDER_CREATED",
        base,
        "order=ORD-1001",
    )

    sent_to_inventory, lamport, vector = distributed["orders"].send_event(
        "evt-002",
        base + timedelta(milliseconds=4),
        "inventory",
        "reserve=SKU-9",
    )

    inventory_received = distributed["inventory"].receive_event(
        "evt-003",
        base + timedelta(milliseconds=8),
        "orders",
        lamport,
        vector,
        "reserve=SKU-9",
    )

    sent_to_payment, lamport, vector = distributed["orders"].send_event(
        "evt-004",
        base + timedelta(milliseconds=10),
        "payments",
        "capture=125.00",
    )

    payment_received = distributed["payments"].receive_event(
        "evt-005",
        base + timedelta(milliseconds=15),
        "orders",
        lamport,
        vector,
        "capture=125.00",
    )

    payment_authorized = distributed["payments"].local_event(
        "evt-006",
        "PAYMENT_AUTHORIZED",
        base + timedelta(milliseconds=20),
        "authorization=AUTH-77",
    )

    inventory_reserved = distributed["inventory"].local_event(
        "evt-007",
        "INVENTORY_RESERVED",
        base + timedelta(milliseconds=25),
        "SKU-9 quantity=1",
    )

    events = [
        order_created,
        sent_to_inventory,
        inventory_received,
        sent_to_payment,
        payment_received,
        payment_authorized,
        inventory_reserved,
    ]

    for event in events:
        print(
            f"{event.event_id:<8} "
            f"{event.node_id:<9} "
            f"{event.kind:<24} "
            f"wall={format_ts(event.physical_time)} "
            f"L={event.logical_time:<2} "
            f"V={event.vector_time}"
        )

    return events


def analyze_causality(events: List[Event]) -> None:
    print("\n=== Causality Analysis ===")

    by_id = {event.event_id: event for event in events}

    pairs = [
        ("evt-002", "evt-003"),
        ("evt-004", "evt-005"),
        ("evt-006", "evt-007"),
    ]

    for left_id, right_id in pairs:
        left = by_id[left_id]
        right = by_id[right_id]

        relation = vector_compare(left.vector_time, right.vector_time)

        print(
            f"{left_id} -> {right_id}: "
            f"vector={relation}, "
            f"Lamport=({left.logical_time},{right.logical_time}), "
            f"wall-clock-order={left.physical_time < right.physical_time}"
        )


def validate_clock_metadata(event: Event) -> None:
    if event.logical_time <= 0:
        raise ValueError(f"{event.event_id}: logical timestamp must be positive")

    if any(value < 0 for value in event.vector_time.values()):
        raise ValueError(f"{event.event_id}: vector timestamp contains a negative value")

    if event.physical_time.tzinfo is None:
        raise ValueError(f"{event.event_id}: physical timestamp must be timezone-aware")


def persist_event_log(events: List[Event], filename: str) -> None:
    for event in events:
        validate_clock_metadata(event)

    with open(filename, "w", encoding="utf-8") as handle:
        json.dump([event.to_dict() for event in events], handle, indent=2)

    print(f"\nPersisted {len(events)} events to {filename}")


def estimate_clock_skew(samples_a: List[float], samples_b: List[float]) -> dict:
    if not samples_a or not samples_b:
        raise ValueError("Both nodes require at least one synchronization sample")

    differences = [b - a for a, b in zip(samples_a, samples_b)]

    return {
        "samples": len(differences),
        "mean_offset_seconds": statistics.mean(differences),
        "median_offset_seconds": statistics.median(differences),
        "minimum_offset_seconds": min(differences),
        "maximum_offset_seconds": max(differences),
    }


def demonstrate_clock_synchronization() -> None:
    print("\n=== Offset Estimation ===")

    node_a = [100.000, 100.010, 100.020, 100.030]
    node_b = [100.075, 100.085, 100.095, 100.105]

    result = estimate_clock_skew(node_a, node_b)

    for key, value in result.items():
        if key == "samples":
            print(f"{key}: {value}")
        else:
            print(f"{key}: {value * 1000:.3f} ms")


def demonstrate_failure_conditions() -> None:
    print("\n=== Failure Conditions ===")

    clock = LamportClock("service-a")

    try:
        clock.receive(-1)
    except ValueError as exc:
        print("Rejected invalid Lamport timestamp:", exc)

    try:
        VectorClock("service-a", ["service-b"])
    except ValueError as exc:
        print("Rejected incomplete vector membership:", exc)

    try:
        vector_compare({"a": 1}, {"a": 1, "b": 2})
    except ValueError as exc:
        print("Rejected incompatible vector dimensions:", exc)


def main() -> None:
    demonstrate_clock_skew()
    demonstrate_lamport()
    demonstrate_vector_clocks()
    demonstrate_timestamp_ordering()

    events = simulate_ordered_event_log()
    analyze_causality(events)

    demonstrate_clock_synchronization()
    demonstrate_failure_conditions()

    persist_event_log(events, "distributed_events.json")

    print("\n=== Operational Guidance ===")
    print(
        "Use UTC-aware physical timestamps for observability and audit records, "
        "but do not treat wall-clock order as proof of causality."
    )
    print(
        "Use Lamport clocks when a compact causal ordering is sufficient. "
        "Use vector clocks when distinguishing concurrency is important."
    )
    print(
        "Clock synchronization reduces skew but does not eliminate network "
        "delay, scheduling delay, timestamp uncertainty, or clock failures."
    )


if __name__ == "__main__":
    main()
