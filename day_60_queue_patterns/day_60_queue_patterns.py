from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class QueueError(Exception):
    """Base exception for queue operations."""


class QueueFullError(QueueError):
    pass


class InvalidDeliveryError(QueueError):
    pass


class StaleDeliveryError(InvalidDeliveryError):
    pass


class QueueClosedError(QueueError):
    pass


class MessageState(Enum):
    READY = "READY"
    IN_FLIGHT = "IN_FLIGHT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DEAD_LETTERED = "DEAD_LETTERED"


@dataclass
class Message:
    message_id: str
    payload: dict[str, Any]
    state: MessageState
    created_at: float
    attempts: int = 0
    consumer_id: str | None = None
    receipt: str | None = None
    lease_deadline: float | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class Delivery:
    message_id: str
    payload: dict[str, Any]
    consumer_id: str
    receipt: str
    attempt: int
    lease_deadline: float


@dataclass(frozen=True)
class QueueStatistics:
    ready: int
    in_flight: int
    acknowledged: int
    dead_lettered: int

    @property
    def outstanding(self) -> int:
        return self.ready + self.in_flight


class FakeClock:
    """Deterministic clock for testing lease expiration."""

    def __init__(self, initial: float = 1000.0) -> None:
        self._current = initial

    def __call__(self) -> float:
        return self._current

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("Clock cannot move backwards.")
        self._current += seconds


class PointToPointQueue:
    """
    In-memory point-to-point queue.

    Each delivery is leased to one consumer. A receipt identifies one
    particular delivery attempt, not merely the underlying message.
    """

    def __init__(
        self,
        name: str,
        *,
        visibility_timeout: float = 30.0,
        max_attempts: int = 3,
        max_outstanding: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not name.strip():
            raise ValueError("Queue name cannot be empty.")
        if visibility_timeout <= 0:
            raise ValueError("Visibility timeout must be positive.")
        if max_attempts < 1:
            raise ValueError("Maximum attempts must be at least one.")
        if max_outstanding < 1:
            raise ValueError("Queue capacity must be at least one.")

        self.name = name
        self.visibility_timeout = visibility_timeout
        self.max_attempts = max_attempts
        self.max_outstanding = max_outstanding
        self._clock = clock

        self._messages: dict[str, Message] = {}
        self._ready: deque[str] = deque()
        self._dead_letters: list[str] = []
        self._lock = threading.RLock()
        self._closed = False

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Message payload must be a dictionary.")

        try:
            serialized = json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Payload must contain valid JSON values.") from exc

        if len(serialized.encode("utf-8")) > 1_048_576:
            raise ValueError("Payload exceeds the 1 MiB size limit.")

        return copy.deepcopy(payload)

    def _expire_leases(self, now: float) -> None:
        """Recover messages whose consumers did not settle their deliveries."""
        for message in self._messages.values():
            if (
                message.state is MessageState.IN_FLIGHT
                and message.lease_deadline is not None
                and message.lease_deadline <= now
            ):
                message.consumer_id = None
                message.receipt = None
                message.lease_deadline = None
                message.last_error = "Visibility timeout expired."

                if message.attempts >= self.max_attempts:
                    message.state = MessageState.DEAD_LETTERED
                    self._dead_letters.append(message.message_id)
                else:
                    message.state = MessageState.READY
                    self._ready.append(message.message_id)

    def publish(
        self,
        payload: dict[str, Any],
        message_id: str | None = None,
    ) -> str:
        validated_payload = self._validate_payload(payload)
        identifier = message_id or str(uuid.uuid4())

        if not identifier.strip():
            raise ValueError("Message identifier cannot be empty.")

        with self._lock:
            if self._closed:
                raise QueueClosedError("Cannot publish to a closed queue.")

            self._expire_leases(self._clock())

            if identifier in self._messages:
                raise ValueError(f"Duplicate message identifier: {identifier}")

            outstanding = sum(
                message.state in {
                    MessageState.READY,
                    MessageState.IN_FLIGHT,
                }
                for message in self._messages.values()
            )

            if outstanding >= self.max_outstanding:
                raise QueueFullError(f"Queue {self.name} is at capacity.")

            message = Message(
                message_id=identifier,
                payload=validated_payload,
                state=MessageState.READY,
                created_at=self._clock(),
            )

            self._messages[identifier] = message
            self._ready.append(identifier)
            return identifier

    def receive(self, consumer_id: str) -> Delivery | None:
        if not consumer_id.strip():
            raise ValueError("Consumer identifier cannot be empty.")

        with self._lock:
            now = self._clock()
            self._expire_leases(now)

            while self._ready:
                message_id = self._ready.popleft()
                message = self._messages[message_id]

                # Ignore obsolete queue entries left by state transitions.
                if message.state is not MessageState.READY:
                    continue

                message.state = MessageState.IN_FLIGHT
                message.attempts += 1
                message.consumer_id = consumer_id
                message.receipt = str(uuid.uuid4())
                message.lease_deadline = now + self.visibility_timeout

                return Delivery(
                    message_id=message.message_id,
                    payload=copy.deepcopy(message.payload),
                    consumer_id=consumer_id,
                    receipt=message.receipt,
                    attempt=message.attempts,
                    lease_deadline=message.lease_deadline,
                )

            return None

    def _get_active_message(self, delivery: Delivery) -> Message:
        message = self._messages.get(delivery.message_id)

        if message is None:
            raise InvalidDeliveryError("Unknown message identifier.")

        if message.state is MessageState.ACKNOWLEDGED:
            raise InvalidDeliveryError("Message has already been acknowledged.")

        if message.state is not MessageState.IN_FLIGHT:
            raise StaleDeliveryError("Message is not currently in flight.")

        if (
            message.receipt != delivery.receipt
            or message.consumer_id != delivery.consumer_id
        ):
            raise StaleDeliveryError(
                "Delivery receipt is invalid or belongs to an older attempt."
            )

        if message.lease_deadline is None:
            raise StaleDeliveryError("Delivery lease is missing.")

        if self._clock() >= message.lease_deadline:
            self._expire_leases(self._clock())
            raise StaleDeliveryError("Delivery lease has expired.")

        return message

    def acknowledge(self, delivery: Delivery) -> bool:
        """Confirm successful processing of the current delivery."""
        with self._lock:
            message = self._get_active_message(delivery)

            message.state = MessageState.ACKNOWLEDGED
            message.consumer_id = None
            message.receipt = None
            message.lease_deadline = None
            return True

    def reject(
        self,
        delivery: Delivery,
        *,
        requeue: bool = True,
        reason: str = "Consumer rejected the message.",
    ) -> MessageState:
        """
        Negative acknowledgement.

        A failed message is requeued until its delivery-attempt limit is
        reached. Non-requeued and exhausted messages enter the dead-letter set.
        """
        with self._lock:
            message = self._get_active_message(delivery)

            message.consumer_id = None
            message.receipt = None
            message.lease_deadline = None
            message.last_error = reason

            if requeue and message.attempts < self.max_attempts:
                message.state = MessageState.READY
                self._ready.append(message.message_id)
            else:
                message.state = MessageState.DEAD_LETTERED
                self._dead_letters.append(message.message_id)

            return message.state

    def statistics(self) -> QueueStatistics:
        with self._lock:
            counts = {
                state: 0
                for state in MessageState
            }

            for message in self._messages.values():
                counts[message.state] += 1

            return QueueStatistics(
                ready=counts[MessageState.READY],
                in_flight=counts[MessageState.IN_FLIGHT],
                acknowledged=counts[MessageState.ACKNOWLEDGED],
                dead_lettered=counts[MessageState.DEAD_LETTERED],
            )

    def dead_letters(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "message_id": message_id,
                    "payload": copy.deepcopy(
                        self._messages[message_id].payload
                    ),
                    "attempts": self._messages[message_id].attempts,
                    "last_error": self._messages[message_id].last_error,
                }
                for message_id in self._dead_letters
            ]

    def close(self) -> None:
        """Prevent new publications while allowing existing messages to drain."""
        with self._lock:
            self._closed = True


class IdempotencyLedger:
    """
    Represents a durable business-operation deduplication store.

    A real application should commit the business update and its idempotency
    record in the same database transaction.
    """

    def __init__(self) -> None:
        self._processed: set[str] = set()
        self._lock = threading.Lock()

    def apply_once(self, message_id: str, payload: dict[str, Any]) -> bool:
        with self._lock:
            if message_id in self._processed:
                return False

            # The example records successful business processing.
            self._processed.add(message_id)
            return True


def process_delivery(
    queue: PointToPointQueue,
    delivery: Delivery,
    ledger: IdempotencyLedger,
) -> None:
    applied = ledger.apply_once(delivery.message_id, delivery.payload)

    if applied:
        print(
            f"{delivery.consumer_id}: processed "
            f"{delivery.message_id} on attempt {delivery.attempt}"
        )
    else:
        print(
            f"{delivery.consumer_id}: skipped duplicate business operation "
            f"for {delivery.message_id}"
        )

    queue.acknowledge(delivery)


def run_demonstration() -> None:
    clock = FakeClock()
    queue = PointToPointQueue(
        "orders",
        visibility_timeout=5.0,
        max_attempts=3,
        max_outstanding=10,
        clock=clock,
    )
    ledger = IdempotencyLedger()

    queue.publish({"order_id": "ORD-1001", "amount": 4500}, "order-1")
    queue.publish({"order_id": "ORD-1002", "amount": 2800}, "order-2")
    queue.publish({"order_id": "ORD-1003", "amount": 9900}, "poison-order")

    # Simulate a worker completing the business operation but crashing
    # before sending its acknowledgement.
    first_delivery = queue.receive("consumer-A")
    assert first_delivery is not None
    assert ledger.apply_once(
        first_delivery.message_id,
        first_delivery.payload,
    )
    print("consumer-A: business operation committed; acknowledgement lost")

    # The lease expires. Another competing consumer receives the same message.
    clock.advance(6)
    redelivery = queue.receive("consumer-B")
    assert redelivery is not None
    assert redelivery.message_id == first_delivery.message_id
    assert redelivery.attempt == 2

    process_delivery(queue, redelivery, ledger)

    # A transient processing failure is requeued for another attempt.
    transient = queue.receive("consumer-A")
    assert transient is not None
    assert transient.message_id == "order-2"

    queue.reject(
        transient,
        requeue=True,
        reason="Temporary downstream payment-service failure.",
    )

    retried = queue.receive("consumer-B")
    assert retried is not None
    assert retried.message_id == "order-2"
    process_delivery(queue, retried, ledger)

    # A poison message exceeds the configured delivery limit.
    for consumer in ("consumer-A", "consumer-B", "consumer-A"):
        delivery = queue.receive(consumer)
        assert delivery is not None
        assert delivery.message_id == "poison-order"

        state = queue.reject(
            delivery,
            requeue=True,
            reason="Invalid order data rejected by validation.",
        )
        print(
            f"{consumer}: rejected attempt {delivery.attempt}; "
            f"state={state.value}"
        )

    stats = queue.statistics()

    print("\nQueue statistics")
    print(f"Ready:         {stats.ready}")
    print(f"In flight:     {stats.in_flight}")
    print(f"Acknowledged:  {stats.acknowledged}")
    print(f"Dead-lettered: {stats.dead_lettered}")

    print("\nDead-letter messages")
    for item in queue.dead_letters():
        print(item)


def run_assertions() -> None:
    clock = FakeClock()
    queue = PointToPointQueue(
        "test-queue",
        visibility_timeout=2,
        max_attempts=2,
        max_outstanding=1,
        clock=clock,
    )

    queue.publish({"task": "reconcile"}, "task-1")

    try:
        queue.publish({"task": "overflow"}, "task-2")
        raise AssertionError("Capacity validation failed.")
    except QueueFullError:
        pass

    original = queue.receive("worker-1")
    assert original is not None

    clock.advance(3)

    redelivery = queue.receive("worker-2")
    assert redelivery is not None
    assert redelivery.attempt == 2

    try:
        queue.acknowledge(original)
        raise AssertionError("A stale receipt was accepted.")
    except StaleDeliveryError:
        pass

    queue.reject(redelivery, requeue=True, reason="Repeated failure.")

    stats = queue.statistics()
    assert stats.dead_lettered == 1
    assert stats.in_flight == 0
    assert stats.ready == 0

    # Acknowledgement of a message that is no longer in flight is rejected.
    assert queue.dead_letters()[0]["message_id"] == "task-1"


if __name__ == "__main__":
    run_assertions()
    run_demonstration()
