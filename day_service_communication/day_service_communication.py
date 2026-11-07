#!/usr/bin/env python3
"""
Service Communication: REST, gRPC, and Messaging

Demonstrates:
- REST request/response communication using HTTP concepts.
- gRPC-style strongly typed RPC contracts and status codes.
- Asynchronous messaging with queues and topics.
- Message acknowledgements, retries, dead-letter queues, and idempotency.
- Transactional outbox and consumer deduplication.
- Validation, error handling, and communication security policies.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("service-communication")


# ============================================================
# 1. Shared Domain Models
# ============================================================

class CommunicationProtocol(Enum):
    REST = "REST"
    GRPC = "gRPC"
    MESSAGE = "MESSAGING"


class RpcStatus(Enum):
    OK = "OK"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True)
class ServiceResponse:
    status: int
    body: dict[str, Any]


@dataclass(frozen=True)
class RpcResponse:
    status: RpcStatus
    payload: dict[str, Any]
    message: str = ""


@dataclass
class Message:
    message_id: str
    topic: str
    payload: dict[str, Any]
    correlation_id: str
    attempts: int = 0
    created_at: float = field(default_factory=time.time)


# ============================================================
# 2. REST Communication
# ============================================================

class ProductService:
    """Domain service shared by REST and RPC interfaces."""

    def __init__(self):
        self._products = {
            101: {"id": 101, "name": "Laptop", "price": 75000.0},
            102: {"id": 102, "name": "Monitor", "price": 18000.0},
        }
        self._lock = threading.RLock()

    def get_product(self, product_id: int) -> dict[str, Any] | None:
        with self._lock:
            product = self._products.get(product_id)
            return dict(product) if product else None

    def create_product(self, data: dict[str, Any]) -> dict[str, Any]:
        name = data.get("name")
        price = data.get("price")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Product name is required")

        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError("Price must be numeric")

        if price <= 0:
            raise ValueError("Price must be positive")

        with self._lock:
            product_id = max(self._products, default=100) + 1
            product = {
                "id": product_id,
                "name": name.strip(),
                "price": float(price),
            }
            self._products[product_id] = product
            return dict(product)


class RestHandler(BaseHTTPRequestHandler):
    service: ProductService | None = None

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "healthy"})
            return

        if not self.path.startswith("/products/"):
            self._send_json(404, {"error": "Endpoint not found"})
            return

        try:
            product_id = int(self.path.rsplit("/", 1)[1])
            if product_id <= 0:
                raise ValueError("Invalid product ID")

            product = self.service.get_product(product_id)

            if product is None:
                self._send_json(404, {"error": "Product not found"})
            else:
                self._send_json(200, {"data": product})

        except ValueError:
            self._send_json(400, {"error": "Invalid product ID"})

    def do_POST(self):
        if self.path != "/products":
            self._send_json(404, {"error": "Endpoint not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))

            if content_length <= 0 or content_length > 16384:
                self._send_json(413, {"error": "Invalid request size"})
                return

            if self.headers.get_content_type() != "application/json":
                self._send_json(415, {"error": "JSON required"})
                return

            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")

            product = self.service.create_product(payload)
            self._send_json(201, {"data": product})

        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})

    def log_message(self, format, *args):
        logger.info("REST %s", format % args)


def start_rest_server(service: ProductService):
    RestHandler.service = service
    server = HTTPServer(("127.0.0.1", 0), RestHandler)
    server.timeout = 0.2

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    return server, thread


def rest_client(base_url: str, method: str, path: str,
                payload: dict | None = None) -> ServiceResponse:
    """REST client with bounded response timeout."""

    body = None if payload is None else json.dumps(payload).encode()

    request = Request(
        base_url + path,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=3) as response:
            return ServiceResponse(
                response.status,
                json.loads(response.read()),
            )

    except HTTPError as exc:
        return ServiceResponse(
            exc.code,
            json.loads(exc.read()),
        )

    except (URLError, TimeoutError) as exc:
        return ServiceResponse(
            503,
            {"error": str(exc)},
        )


# ============================================================
# 3. gRPC-Style Strongly Typed RPC
# ============================================================

@dataclass(frozen=True)
class GetProductRequest:
    product_id: int


@dataclass(frozen=True)
class GetProductReply:
    product_id: int
    name: str
    price: float


class ProductRpcService:
    """
    Models a typed RPC service contract.

    This is an executable RPC simulation, not a wire-compatible
    gRPC server. Real gRPC uses HTTP/2, Protocol Buffers,
    generated service stubs, and transport-level status codes.
    """

    def __init__(self, product_service: ProductService):
        self.product_service = product_service

    def get_product(self, request: GetProductRequest) -> RpcResponse:
        if isinstance(request.product_id, bool):
            return RpcResponse(
                RpcStatus.INVALID_ARGUMENT,
                {},
                "Product ID must be an integer",
            )

        if request.product_id <= 0:
            return RpcResponse(
                RpcStatus.INVALID_ARGUMENT,
                {},
                "Product ID must be positive",
            )

        product = self.product_service.get_product(request.product_id)

        if product is None:
            return RpcResponse(
                RpcStatus.NOT_FOUND,
                {},
                "Product not found",
            )

        reply = GetProductReply(
            product_id=product["id"],
            name=product["name"],
            price=product["price"],
        )

        return RpcResponse(
            RpcStatus.OK,
            {
                "product_id": reply.product_id,
                "name": reply.name,
                "price": reply.price,
            },
        )


class RpcClient:
    def __init__(self, service: ProductRpcService, timeout: float = 2.0):
        self.service = service
        self.timeout = timeout

    def get_product(self, product_id: int) -> RpcResponse:
        start = time.monotonic()

        try:
            response = self.service.get_product(
                GetProductRequest(product_id)
            )

            if time.monotonic() - start > self.timeout:
                return RpcResponse(
                    RpcStatus.UNAVAILABLE,
                    {},
                    "RPC deadline exceeded",
                )

            return response

        except Exception:
            logger.exception("RPC invocation failed")
            return RpcResponse(
                RpcStatus.INTERNAL,
                {},
                "Internal RPC error",
            )


# ============================================================
# 4. Asynchronous Messaging
# ============================================================

class DeliveryState(Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DEAD_LETTERED = "DEAD_LETTERED"


@dataclass
class MessageEnvelope:
    message: Message
    state: DeliveryState = DeliveryState.PENDING


class MessageBroker:
    """
    In-memory broker demonstrating queue-based delivery.

    A production broker must persist messages and coordinate
    acknowledgements across processes.
    """

    def __init__(self, max_retries: int = 3):
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        self.max_retries = max_retries
        self.queues: dict[str, deque] = defaultdict(deque)
        self.dead_letters: list[MessageEnvelope] = []
        self.subscribers: dict[str, list[Callable]] = defaultdict(list)
        self.processed_ids: set[str] = set()
        self.lock = threading.RLock()

    def subscribe(self, topic: str, handler: Callable) -> None:
        if not topic or not callable(handler):
            raise ValueError("Valid topic and handler required")

        with self.lock:
            self.subscribers[topic].append(handler)

    def publish(self, topic: str, payload: dict,
                correlation_id: str | None = None) -> str:
        if not topic or not isinstance(payload, dict):
            raise ValueError("Invalid message")

        message = Message(
            message_id=str(uuid.uuid4()),
            topic=topic,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )

        with self.lock:
            self.queues[topic].append(MessageEnvelope(message))

        logger.info("Published message %s", message.message_id)
        return message.message_id

    def consume_one(self, topic: str) -> bool:
        with self.lock:
            if not self.queues[topic]:
                return False

            envelope = self.queues[topic].popleft()
            message = envelope.message

            if message.message_id in self.processed_ids:
                envelope.state = DeliveryState.ACKNOWLEDGED
                return True

            handlers = list(self.subscribers[topic])

        if not handlers:
            with self.lock:
                self.queues[topic].appendleft(envelope)
            return False

        try:
            for handler in handlers:
                handler(message.payload)

            with self.lock:
                self.processed_ids.add(message.message_id)
                envelope.state = DeliveryState.ACKNOWLEDGED

            logger.info("Acknowledged %s", message.message_id)
            return True

        except Exception:
            message.attempts += 1
            logger.exception(
                "Message processing failed: attempt %s",
                message.attempts,
            )

            with self.lock:
                if message.attempts > self.max_retries:
                    envelope.state = DeliveryState.DEAD_LETTERED
                    self.dead_letters.append(envelope)
                else:
                    self.queues[topic].append(envelope)

            return False

    def consume_all(self, topic: str, limit: int = 100) -> int:
        if limit < 0:
            raise ValueError("Limit cannot be negative")

        processed = 0

        for _ in range(limit):
            if not self.consume_one(topic):
                break
            processed += 1

        return processed


# ============================================================
# 5. Transactional Outbox and Idempotent Consumer
# ============================================================

@dataclass
class OutboxEvent:
    event_id: str
    aggregate_id: int
    event_type: str
    payload: dict
    published: bool = False


class TransactionalOutbox:
    """
    Demonstrates atomic application-state and event recording.

    Both operations are protected by one lock in this simulation.
    A real implementation stores both in the same database
    transaction and publishes through a background dispatcher.
    """

    def __init__(self):
        self.products: dict[int, dict] = {}
        self.events: list[OutboxEvent] = []
        self.lock = threading.RLock()

    def create_product(self, product: dict) -> str:
        with self.lock:
            product_id = product["id"]

            if product_id in self.products:
                raise ValueError("Duplicate product ID")

            event = OutboxEvent(
                event_id=str(uuid.uuid4()),
                aggregate_id=product_id,
                event_type="ProductCreated",
                payload=dict(product),
            )

            self.products[product_id] = dict(product)
            self.events.append(event)

            return event.event_id

    def dispatch(self, broker: MessageBroker) -> int:
        published = 0

        with self.lock:
            for event in self.events:
                if event.published:
                    continue

                broker.publish(
                    "product.events",
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "data": event.payload,
                    },
                    correlation_id=event.event_id,
                )

                event.published = True
                published += 1

        return published


class IdempotentConsumer:
    def __init__(self):
        self.processed_events: set[str] = set()
        self.inventory_updates: dict[int, int] = defaultdict(int)
        self.lock = threading.Lock()

    def handle(self, payload: dict) -> None:
        event_id = payload.get("event_id")
        data = payload.get("data", {})

        if not event_id or not isinstance(data, dict):
            raise ValueError("Invalid event structure")

        product_id = data.get("id")

        if not isinstance(product_id, int) or isinstance(product_id, bool):
            raise ValueError("Invalid product identifier")

        with self.lock:
            if event_id in self.processed_events:
                return

            self.inventory_updates[product_id] += 1
            self.processed_events.add(event_id)


# ============================================================
# 6. Communication Policy and Validation
# ============================================================

@dataclass(frozen=True)
class CommunicationPolicy:
    protocol: CommunicationProtocol
    authenticated: bool
    encrypted: bool
    timeout_seconds: float
    max_payload_bytes: int

    def validate(self) -> None:
        if not self.authenticated or not self.encrypted:
            raise PermissionError(
                "Authentication and encryption are mandatory"
            )

        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")

        if self.max_payload_bytes <= 0:
            raise ValueError("Payload limit must be positive")


def retry_operation(operation: Callable, attempts: int = 3,
                    delay: float = 0.05):
    """
    Retries transient failures with exponential backoff.

    Only use automatic retries for operations whose semantics
    make repetition safe, normally idempotent operations.
    """

    if attempts < 1 or delay < 0:
        raise ValueError("Invalid retry configuration")

    for attempt in range(attempts):
        try:
            return operation()
        except (ConnectionError, TimeoutError):
            if attempt == attempts - 1:
                raise

            time.sleep(delay * (2 ** attempt))


# ============================================================
# 7. Executable Demonstration and Assertions
# ============================================================

def main():
    print("\n=== SERVICE COMMUNICATION ===")

    product_service = ProductService()

    # REST
    print("\n--- REST ---")

    server, thread = start_rest_server(product_service)
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        response = rest_client(
            base_url,
            "GET",
            "/products/101",
        )
        print("GET:", response.status, response.body)
        assert response.status == 200

        response = rest_client(
            base_url,
            "POST",
            "/products",
            {"name": "Keyboard", "price": 2500},
        )
        print("POST:", response.status, response.body)
        assert response.status == 201

        response = rest_client(
            base_url,
            "GET",
            "/products/999",
        )
        print("Missing product:", response.status)
        assert response.status == 404

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    # gRPC-style RPC
    print("\n--- gRPC-STYLE RPC ---")

    rpc_service = ProductRpcService(product_service)
    rpc_client = RpcClient(rpc_service)

    rpc_result = rpc_client.get_product(101)
    print("RPC:", rpc_result.status.value, rpc_result.payload)
    assert rpc_result.status == RpcStatus.OK

    missing_rpc = rpc_client.get_product(999)
    print("Missing RPC:", missing_rpc.status.value)
    assert missing_rpc.status == RpcStatus.NOT_FOUND

    invalid_rpc = rpc_client.get_product(-1)
    print("Invalid RPC:", invalid_rpc.status.value)
    assert invalid_rpc.status == RpcStatus.INVALID_ARGUMENT

    # Messaging
    print("\n--- ASYNCHRONOUS MESSAGING ---")

    broker = MessageBroker(max_retries=2)
    consumer = IdempotentConsumer()

    broker.subscribe(
        "product.events",
        consumer.handle,
    )

    outbox = TransactionalOutbox()

    event_id = outbox.create_product({
        "id": 201,
        "name": "Wireless Mouse",
        "price": 1500.0,
    })

    print("Outbox event:", event_id)

    dispatched = outbox.dispatch(broker)
    print("Dispatched:", dispatched)

    consumed = broker.consume_all("product.events")
    print("Consumed:", consumed)

    assert consumer.inventory_updates[201] == 1

    # Simulate duplicate event delivery.
    consumer.handle({
        "event_id": event_id,
        "event_type": "ProductCreated",
        "data": {"id": 201},
    })

    assert consumer.inventory_updates[201] == 1

    # Failure and dead-letter demonstration.
    failure_broker = MessageBroker(max_retries=1)

    def failing_handler(payload):
        raise RuntimeError("Temporary downstream failure")

    failure_broker.subscribe("orders", failing_handler)
    failure_broker.publish("orders", {"order_id": 5001})

    failure_broker.consume_one("orders")
    failure_broker.consume_one("orders")

    print(
        "Dead-letter count:",
        len(failure_broker.dead_letters),
    )
    assert len(failure_broker.dead_letters) == 1

    # Security policy
    print("\n--- COMMUNICATION POLICY ---")

    policy = CommunicationPolicy(
        protocol=CommunicationProtocol.REST,
        authenticated=True,
        encrypted=True,
        timeout_seconds=3,
        max_payload_bytes=16384,
    )

    policy.validate()
    print("Secure communication policy validated")

    try:
        insecure_policy = CommunicationPolicy(
            CommunicationProtocol.MESSAGE,
            authenticated=False,
            encrypted=True,
            timeout_seconds=3,
            max_payload_bytes=16384,
        )
        insecure_policy.validate()
    except PermissionError as exc:
        print("Security rejection:", exc)

    print("\nAll service communication assertions passed.")


if __name__ == "__main__":
    main()
