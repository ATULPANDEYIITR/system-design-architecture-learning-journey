from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Optional, Set
import time
import uuid


class MessageState(Enum):
    READY = "ready"
    IN_FLIGHT = "in_flight"
    ACKED = "acked"
    DEAD_LETTERED = "dead_lettered"


class QueueError(Exception):
    pass


class QueueNotFoundError(QueueError):
    pass


class ConsumerError(QueueError):
    pass


@dataclass
class Message:
    message_id: str
    payload: str
    created_at: float
    attempts: int = 0
    state: MessageState = MessageState.READY
    producer_id: str = ""
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class Queue:
    name: str
    durable: bool = True
    max_attempts: int = 3
    messages: Deque[str] = field(default_factory=deque)
    dead_letters: Deque[str] = field(default_factory=deque)


@dataclass
class Consumer:
    consumer_id: str
    queue_name: str
    handler: Callable[[Message], bool]
    prefetch: int = 1
    in_flight: Set[str] = field(default_factory=set)


class Broker:
    """
    In-memory message broker.

    The broker owns message lifecycle and queue state. Producers publish
    messages; consumers receive them and explicitly acknowledge success.
    Failed messages are requeued until max_attempts is reached.
    """

    def __init__(self) -> None:
        self.queues: Dict[str, Queue] = {}
        self.messages: Dict[str, Message] = {}
        self.consumers: Dict[str, Consumer] = {}

    def declare_queue(
        self,
        name: str,
        durable: bool = True,
        max_attempts: int = 3,
    ) -> None:
        if not name.strip():
            raise ValueError("Queue name cannot be empty")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")

        existing = self.queues.get(name)
        if existing:
            if existing.durable != durable:
                raise QueueError("Queue durability conflicts with existing queue")
            return

        self.queues[name] = Queue(
            name=name,
            durable=durable,
            max_attempts=max_attempts,
        )

    def publish(
        self,
        queue_name: str,
        payload: str,
        producer_id: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        if queue_name not in self.queues:
            raise QueueNotFoundError(queue_name)
        if not payload:
            raise ValueError("Message payload cannot be empty")
        if not producer_id:
            raise ValueError("producer_id is required")

        message_id = str(uuid.uuid4())
        message = Message(
            message_id=message_id,
            payload=payload,
            created_at=time.time(),
            producer_id=producer_id,
            headers=headers or {},
        )

        self.messages[message_id] = message
        self.queues[queue_name].messages.append(message_id)
        return message_id

    def consume(self, consumer_id: str) -> Optional[Message]:
        consumer = self.consumers.get(consumer_id)
        if consumer is None:
            raise ConsumerError(f"Unknown consumer: {consumer_id}")

        if len(consumer.in_flight) >= consumer.prefetch:
            return None

        queue = self.queues.get(consumer.queue_name)
        if queue is None:
            raise QueueNotFoundError(consumer.queue_name)

        while queue.messages:
            message_id = queue.messages.popleft()
            message = self.messages[message_id]

            if message.state != MessageState.READY:
                continue

            message.attempts += 1
            message.state = MessageState.IN_FLIGHT
            consumer.in_flight.add(message_id)
            return message

        return None

    def acknowledge(self, consumer_id: str, message_id: str) -> None:
        consumer = self.consumers.get(consumer_id)
        if consumer is None:
            raise ConsumerError(f"Unknown consumer: {consumer_id}")

        if message_id not in consumer.in_flight:
            raise ConsumerError("Message is not owned by this consumer")

        message = self.messages.get(message_id)
        if message is None:
            raise QueueError("Unknown message")

        message.state = MessageState.ACKED
        consumer.in_flight.remove(message_id)

    def reject(self, consumer_id: str, message_id: str) -> None:
        consumer = self.consumers.get(consumer_id)
        if consumer is None:
            raise ConsumerError(f"Unknown consumer: {consumer_id}")

        if message_id not in consumer.in_flight:
            raise ConsumerError("Message is not owned by this consumer")

        message = self.messages[message_id]
        queue = self.queues[consumer.queue_name]

        consumer.in_flight.remove(message_id)

        if message.attempts >= queue.max_attempts:
            message.state = MessageState.DEAD_LETTERED
            queue.dead_letters.append(message_id)
        else:
            message.state = MessageState.READY
            queue.messages.append(message_id)

    def register_consumer(
        self,
        consumer_id: str,
        queue_name: str,
        handler: Callable[[Message], bool],
        prefetch: int = 1,
    ) -> None:
        if consumer_id in self.consumers:
            raise ConsumerError("Consumer already exists")
        if queue_name not in self.queues:
            raise QueueNotFoundError(queue_name)
        if prefetch < 1:
            raise ValueError("prefetch must be positive")

        self.consumers[consumer_id] = Consumer(
            consumer_id=consumer_id,
            queue_name=queue_name,
            handler=handler,
            prefetch=prefetch,
        )

    def poll_consumer(self, consumer_id: str) -> int:
        """
        Pull messages until the consumer's prefetch limit is reached.

        A handler returning True means ACK.
        A handler returning False means reject/requeue or dead-letter.
        """
        consumer = self.consumers[consumer_id]
        processed = 0

        while len(consumer.in_flight) < consumer.prefetch:
            message = self.consume(consumer_id)
            if message is None:
                break

            try:
                success = consumer.handler(message)
            except Exception as exc:
                print(
                    f"[ERROR] consumer={consumer_id} "
                    f"message={message.message_id}: {exc}"
                )
                success = False

            if success:
                self.acknowledge(consumer_id, message.message_id)
            else:
                self.reject(consumer_id, message.message_id)

            processed += 1

        return processed

    def queue_stats(self, queue_name: str) -> Dict[str, int]:
        if queue_name not in self.queues:
            raise QueueNotFoundError(queue_name)

        queue = self.queues[queue_name]
        ready = sum(
            1
            for message_id in queue.messages
            if self.messages[message_id].state == MessageState.READY
        )
        in_flight = sum(
            1
            for message in self.messages.values()
            if message.state == MessageState.IN_FLIGHT
            and any(
                message.message_id in consumer.in_flight
                for consumer in self.consumers.values()
            )
        )
        dead = len(queue.dead_letters)

        return {
            "ready": ready,
            "in_flight": in_flight,
            "dead_lettered": dead,
        }


def build_order_handler(failing_order_ids: Set[str]) -> Callable[[Message], bool]:
    processed_orders: Set[str] = set()

    def handle(message: Message) -> bool:
        order_id = message.headers.get("order_id", "")
        if not order_id:
            print(f"[REJECT] {message.message_id}: missing order_id")
            return False

        # Idempotency prevents duplicate delivery from causing duplicate work.
        if order_id in processed_orders:
            print(f"[IDEMPOTENT] order={order_id}")
            return True

        if order_id in failing_order_ids:
            print(
                f"[TEMPORARY FAILURE] order={order_id}, "
                f"attempt={message.attempts}"
            )
            return False

        processed_orders.add(order_id)
        print(f"[PROCESSED] order={order_id}: {message.payload}")
        return True

    return handle


def main() -> None:
    broker = Broker()

    broker.declare_queue(
        "orders",
        durable=True,
        max_attempts=3,
    )

    broker.publish(
        "orders",
        "Process payment and reserve inventory",
        producer_id="checkout-service",
        headers={"order_id": "ORD-1001", "event": "order.created"},
    )

    broker.publish(
        "orders",
        "Send order confirmation",
        producer_id="checkout-service",
        headers={"order_id": "ORD-1002", "event": "order.created"},
    )

    broker.publish(
        "orders",
        "Create shipping label",
        producer_id="checkout-service",
        headers={"order_id": "ORD-1003", "event": "order.created"},
    )

    handler = build_order_handler({"ORD-1003"})

    broker.register_consumer(
        consumer_id="fulfillment-worker-1",
        queue_name="orders",
        handler=handler,
        prefetch=2,
    )

    print("Initial:", broker.queue_stats("orders"))

    for attempt in range(1, 5):
        processed = broker.poll_consumer("fulfillment-worker-1")
        print(
            f"Poll {attempt}: processed={processed}, "
            f"stats={broker.queue_stats('orders')}"
        )
        if processed == 0:
            break

    # Demonstrate validation and failure handling.
    try:
        broker.publish("unknown", "invalid", "producer")
    except QueueError as exc:
        print(f"[VALIDATION] {exc}")

    # The failed ORD-1003 eventually reaches the dead-letter queue.
    stats = broker.queue_stats("orders")
    assert stats["dead_lettered"] == 1
    assert stats["ready"] == 0

    # Acknowledged messages are terminal and cannot be accidentally rejected.
    acknowledged = [
        message
        for message in broker.messages.values()
        if message.state == MessageState.ACKED
    ]
    assert len(acknowledged) == 2

    print("Final:", stats)
    print("Simulation completed successfully.")


if __name__ == "__main__":
    main()
