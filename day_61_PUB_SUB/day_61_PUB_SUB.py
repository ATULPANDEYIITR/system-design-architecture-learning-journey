from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Optional, Set
import json
import threading
import time
import uuid


class DeliveryStatus(Enum):
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Event:
    topic: str
    payload: dict
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)


@dataclass
class DeliveryResult:
    event_id: str
    subscriber_id: str
    status: DeliveryStatus
    error: Optional[str] = None


class SubscriptionError(ValueError):
    pass


class PublishError(ValueError):
    pass


class Subscriber:
    def __init__(
        self,
        subscriber_id: str,
        handler: Callable[[Event], None],
        max_failures: int = 3,
    ) -> None:
        if not subscriber_id.strip():
            raise SubscriptionError("Subscriber ID cannot be empty.")
        if not callable(handler):
            raise SubscriptionError("Subscriber handler must be callable.")
        if max_failures < 1:
            raise SubscriptionError("max_failures must be positive.")

        self.subscriber_id = subscriber_id
        self.handler = handler
        self.max_failures = max_failures
        self.failure_count = 0
        self.active = True
        self._lock = threading.Lock()

    def deliver(self, event: Event) -> DeliveryResult:
        with self._lock:
            if not self.active:
                return DeliveryResult(
                    event.event_id,
                    self.subscriber_id,
                    DeliveryStatus.SKIPPED,
                    "Subscriber is inactive.",
                )

        try:
            self.handler(event)
            with self._lock:
                self.failure_count = 0
            return DeliveryResult(
                event.event_id,
                self.subscriber_id,
                DeliveryStatus.DELIVERED,
            )
        except Exception as exc:
            with self._lock:
                self.failure_count += 1
                if self.failure_count >= self.max_failures:
                    self.active = False

            return DeliveryResult(
                event.event_id,
                self.subscriber_id,
                DeliveryStatus.FAILED,
                str(exc),
            )


class PubSubBroker:
    """
    In-memory publish/subscribe broker.

    Topics are independent routing channels. A publication is delivered to
    every active subscriber registered for the topic. Delivery failures are
    isolated so one subscriber cannot prevent other subscribers from receiving
    the same event.
    """

    def __init__(self, history_limit: int = 1000) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive.")

        self._subscriptions: Dict[str, Dict[str, Subscriber]] = defaultdict(dict)
        self._history: Deque[Event] = deque(maxlen=history_limit)
        self._lock = threading.RLock()

    @staticmethod
    def validate_topic(topic: str) -> None:
        if not topic or not topic.strip():
            raise PublishError("Topic cannot be empty.")
        if len(topic) > 128:
            raise PublishError("Topic cannot exceed 128 characters.")
        if any(ch.isspace() for ch in topic):
            raise PublishError("Topic cannot contain whitespace.")

    def subscribe(
        self,
        topic: str,
        subscriber_id: str,
        handler: Callable[[Event], None],
        max_failures: int = 3,
    ) -> None:
        self.validate_topic(topic)

        subscriber = Subscriber(subscriber_id, handler, max_failures)

        with self._lock:
            if subscriber_id in self._subscriptions[topic]:
                raise SubscriptionError(
                    f"Subscriber '{subscriber_id}' is already subscribed to '{topic}'."
                )
            self._subscriptions[topic][subscriber_id] = subscriber

    def unsubscribe(self, topic: str, subscriber_id: str) -> bool:
        self.validate_topic(topic)

        with self._lock:
            subscribers = self._subscriptions.get(topic)
            if not subscribers or subscriber_id not in subscribers:
                return False

            del subscribers[subscriber_id]
            if not subscribers:
                self._subscriptions.pop(topic, None)
            return True

    def publish(self, topic: str, payload: dict) -> List[DeliveryResult]:
        self.validate_topic(topic)

        if not isinstance(payload, dict):
            raise PublishError("Payload must be a dictionary.")

        # Copy the subscriber list before invoking user handlers. This avoids
        # holding the broker lock while arbitrary application code executes.
        event = Event(topic=topic, payload=dict(payload))

        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscriptions.get(topic, {}).values())

        results: List[DeliveryResult] = []
        for subscriber in subscribers:
            results.append(subscriber.deliver(event))

        return results

    def replay(self, topic: str, subscriber_id: str) -> List[DeliveryResult]:
        self.validate_topic(topic)

        with self._lock:
            subscriber = self._subscriptions.get(topic, {}).get(subscriber_id)
            if subscriber is None:
                raise SubscriptionError(
                    f"Subscriber '{subscriber_id}' is not subscribed to '{topic}'."
                )
            events = [event for event in self._history if event.topic == topic]

        return [subscriber.deliver(event) for event in events]

    def subscriber_count(self, topic: str) -> int:
        self.validate_topic(topic)
        with self._lock:
            return len(self._subscriptions.get(topic, {}))

    def topic_statistics(self) -> dict:
        with self._lock:
            return {
                topic: {
                    "subscribers": len(subscribers),
                    "active": sum(
                        1 for subscriber in subscribers.values() if subscriber.active
                    ),
                }
                for topic, subscribers in self._subscriptions.items()
            }


def audit_handler(event: Event) -> None:
    print(
        f"[AUDIT] {event.topic}: "
        f"{json.dumps(event.payload, sort_keys=True)}"
    )


def analytics_handler(event: Event) -> None:
    amount = event.payload.get("amount", 0)
    print(f"[ANALYTICS] observed transaction amount={amount}")


def unreliable_handler(event: Event) -> None:
    if event.payload.get("amount", 0) > 5000:
        raise RuntimeError("Risk service temporarily unavailable.")
    print("[RISK] transaction accepted for inspection")


def run_demo() -> None:
    broker = PubSubBroker(history_limit=100)

    broker.subscribe("transactions.created", "audit-service", audit_handler)
    broker.subscribe("transactions.created", "analytics-service", analytics_handler)
    broker.subscribe(
        "transactions.created",
        "risk-service",
        unreliable_handler,
        max_failures=2,
    )

    event_payloads = [
        {
            "transaction_id": "TX-1001",
            "customer_id": "C-501",
            "amount": 1200,
            "currency": "INR",
        },
        {
            "transaction_id": "TX-1002",
            "customer_id": "C-502",
            "amount": 8500,
            "currency": "INR",
        },
    ]

    for payload in event_payloads:
        results = broker.publish("transactions.created", payload)
        print("\nDelivery results:")
        for result in results:
            print(
                result.subscriber_id,
                result.status.value,
                result.error or "",
            )

    print("\nStatistics:")
    print(json.dumps(broker.topic_statistics(), indent=2))

    assert broker.subscriber_count("transactions.created") == 3

    assert broker.unsubscribe(
        "transactions.created",
        "analytics-service",
    )

    assert not broker.unsubscribe(
        "transactions.created",
        "unknown-service",
    )

    print("\nAfter unsubscribe:")
    print(json.dumps(broker.topic_statistics(), indent=2))

    # Demonstrate retained-event replay for a currently subscribed consumer.
    replay_results = broker.replay("transactions.created", "audit-service")
    print(f"\nReplayed events: {len(replay_results)}")

    # Invalid input is rejected before routing.
    try:
        broker.publish("invalid topic", {"value": 1})
    except PublishError as exc:
        print(f"\nValidation error: {exc}")


if __name__ == "__main__":
    run_demo()
