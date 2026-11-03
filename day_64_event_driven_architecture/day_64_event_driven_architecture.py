from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Callable, Any
import json
import uuid


class EventType(str, Enum):
    ORDER_CREATED = "order.created"
    PAYMENT_AUTHORIZED = "payment.authorized"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_CANCELLED = "order.cancelled"


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: EventType
    aggregate_id: str
    payload: dict[str, Any]
    occurred_at: str
    producer: str

    @staticmethod
    def create(
        event_type: EventType,
        aggregate_id: str,
        payload: dict[str, Any],
        producer: str,
    ) -> "Event":
        if not aggregate_id.strip():
            raise ValueError("aggregate_id cannot be empty")
        if not producer.strip():
            raise ValueError("producer cannot be empty")

        return Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=dict(payload),
            occurred_at=datetime.now(timezone.utc).isoformat(),
            producer=producer,
        )


@dataclass
class Subscription:
    consumer_name: str
    event_type: EventType
    handler: Callable[[Event], None]


class EventBus:
    """
    In-memory event broker demonstrating producer-consumer decoupling.

    Producers only publish events. They do not know which consumers
    receive or process those events.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[EventType, list[Subscription]] = defaultdict(list)
        self._queue: deque[Event] = deque()
        self._processed: set[tuple[str, str]] = set()
        self.dead_letter: list[tuple[Event, str]] = []

    def subscribe(
        self,
        consumer_name: str,
        event_type: EventType,
        handler: Callable[[Event], None],
    ) -> None:
        if not consumer_name.strip():
            raise ValueError("consumer_name cannot be empty")

        self._subscriptions[event_type].append(
            Subscription(consumer_name, event_type, handler)
        )

    def publish(self, event: Event) -> None:
        if not isinstance(event, Event):
            raise TypeError("Only Event objects can be published")
        self._queue.append(event)

    def process(self) -> None:
        while self._queue:
            event = self._queue.popleft()

            for subscription in self._subscriptions.get(event.event_type, []):
                delivery_key = (event.event_id, subscription.consumer_name)

                # Idempotency prevents duplicate side effects.
                if delivery_key in self._processed:
                    continue

                try:
                    subscription.handler(event)
                    self._processed.add(delivery_key)
                except Exception as exc:
                    self.dead_letter.append((event, str(exc)))

    def pending_count(self) -> int:
        return len(self._queue)


@dataclass
class Order:
    order_id: str
    customer_id: str
    amount: float
    status: str = "CREATED"


class OrderService:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.orders: dict[str, Order] = {}

    def create_order(self, customer_id: str, amount: float) -> str:
        if not customer_id.strip():
            raise ValueError("customer_id cannot be empty")
        if amount <= 0:
            raise ValueError("amount must be positive")

        order_id = str(uuid.uuid4())
        order = Order(order_id, customer_id, round(amount, 2))
        self.orders[order_id] = order

        self.bus.publish(
            Event.create(
                EventType.ORDER_CREATED,
                order_id,
                {
                    "customer_id": customer_id,
                    "amount": order.amount,
                },
                "order-service",
            )
        )

        return order_id


class PaymentConsumer:
    def __init__(self, bus: EventBus) -> None:
        self.authorized_orders: set[str] = set()
        bus.subscribe(
            "payment-service",
            EventType.ORDER_CREATED,
            self.handle_order_created,
        )

    def handle_order_created(self, event: Event) -> None:
        amount = event.payload.get("amount")

        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("Invalid payment amount")

        self.authorized_orders.add(event.aggregate_id)

        print(
            f"[payment-service] Authorized payment for "
            f"{event.aggregate_id}: {amount:.2f}"
        )


class NotificationConsumer:
    def __init__(self, bus: EventBus) -> None:
        self.notifications: list[str] = []

        bus.subscribe(
            "notification-service",
            EventType.ORDER_CREATED,
            self.handle_order_created,
        )
        bus.subscribe(
            "notification-service",
            EventType.ORDER_CONFIRMED,
            self.handle_order_confirmed,
        )

    def handle_order_created(self, event: Event) -> None:
        message = f"Order {event.aggregate_id} was created."
        self.notifications.append(message)
        print(f"[notification-service] {message}")

    def handle_order_confirmed(self, event: Event) -> None:
        message = f"Order {event.aggregate_id} was confirmed."
        self.notifications.append(message)
        print(f"[notification-service] {message}")


class AnalyticsConsumer:
    def __init__(self, bus: EventBus) -> None:
        self.event_counts: defaultdict[str, int] = defaultdict(int)

        for event_type in EventType:
            bus.subscribe(
                "analytics-service",
                event_type,
                self.handle_event,
            )

    def handle_event(self, event: Event) -> None:
        self.event_counts[event.event_type.value] += 1


def print_event(event: Event) -> None:
    print(
        json.dumps(
            {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "aggregate_id": event.aggregate_id,
                "producer": event.producer,
                "payload": event.payload,
            },
            indent=2,
        )
    )


def main() -> None:
    bus = EventBus()

    payment = PaymentConsumer(bus)
    notifications = NotificationConsumer(bus)
    analytics = AnalyticsConsumer(bus)

    order_service = OrderService(bus)

    order_id = order_service.create_order("customer-1001", 1499.50)

    print("\nPublished events are processed asynchronously:")
    print(f"Pending events before processing: {bus.pending_count()}")

    bus.process()

    print(f"Pending events after processing: {bus.pending_count()}")
    print(f"Authorized payments: {len(payment.authorized_orders)}")
    print(f"Notifications: {len(notifications.notifications)}")
    print(f"Analytics counts: {dict(analytics.event_counts)}")

    # Demonstrate another consumer being added without changing the producer.
    audit_log: list[str] = []

    bus.subscribe(
        "audit-service",
        EventType.ORDER_CREATED,
        lambda event: audit_log.append(
            f"{event.event_type.value}:{event.aggregate_id}"
        ),
    )

    second_order = order_service.create_order("customer-1002", 250.00)
    bus.process()

    print(f"Second order: {second_order}")
    print(f"Audit entries: {audit_log}")

    # Edge case: invalid input is rejected before an event is emitted.
    try:
        order_service.create_order("", 100)
    except ValueError as exc:
        print(f"Validation failure: {exc}")

    # Event serialization example.
    sample = Event.create(
        EventType.ORDER_CONFIRMED,
        order_id,
        {"confirmed_by": "workflow-service"},
        "workflow-service",
    )
    print("\nSample event:")
    print_event(sample)

    # Failure handling example.
    def failing_consumer(event: Event) -> None:
        raise RuntimeError("Downstream service unavailable")

    bus.subscribe(
        "unavailable-service",
        EventType.ORDER_CONFIRMED,
        failing_consumer,
    )
    bus.publish(sample)
    bus.process()

    print(f"Dead-lettered deliveries: {len(bus.dead_letter)}")

    # Production considerations:
    # - Persist events in an event store or durable broker.
    # - Use retries with exponential backoff.
    # - Add correlation IDs and tracing metadata.
    # - Encrypt sensitive payloads and avoid publishing secrets.
    # - Apply authentication and authorization to publishers and consumers.
    # - Monitor queue depth, consumer latency, failures, and dead letters.
    # - Partition events by aggregate ID when ordering is required.


if __name__ == "__main__":
    main()
