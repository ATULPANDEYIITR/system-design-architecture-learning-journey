"""
gRPC, RPC, Protocol Buffers, and Service-to-Service Communication
==================================================================

This standalone study script teaches the conceptual foundations behind gRPC,
RPC, Protocol Buffers, and service-to-service communication.

The script intentionally implements the important mechanisms locally using
Python's standard library so that the educational examples do not require a
running gRPC server, generated protobuf files, or third-party packages.

It progresses through:
1. RPC fundamentals
2. Protocol Buffers concepts
3. Message serialization
4. Service contracts
5. Client/server architecture
6. Unary, streaming, and asynchronous RPC concepts
7. Deadlines, status, metadata, validation, retries, and idempotency
8. Service discovery and load balancing
9. Interceptors and observability
10. Security considerations
11. Performance and production design
12. A small in-process microservice simulation
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
import math
import random
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Tuple


# ============================================================================
# 1. RPC FUNDAMENTALS
# ============================================================================

print("=" * 78)
print("gRPC / RPC / PROTOCOL BUFFERS / SERVICE-TO-SERVICE COMMUNICATION")
print("=" * 78)


def add_numbers(first: int, second: int) -> int:
    """Ordinary local procedure call."""
    return first + second


print("\n[1] Ordinary local procedure call")
print("add_numbers(10, 20) =", add_numbers(10, 20))

# RPC means Remote Procedure Call.
#
# The conceptual difference is:
#
# Local:
#   application -> function
#
# Remote:
#   client -> RPC client stub -> network -> RPC server -> function
#
# gRPC standardizes much of the remote side:
#   - service contracts
#   - message schemas
#   - serialization
#   - transport
#   - status handling
#   - metadata
#   - streaming
#   - deadlines
#
# A real gRPC implementation normally uses HTTP/2 as its transport and
# Protocol Buffers as its common interface-definition and serialization format.


# ============================================================================
# 2. PROTOCOL BUFFERS: THE DATA MODEL
# ============================================================================

print("\n[2] Protocol Buffers concepts")


@dataclass
class UserMessage:
    """
    Python representation of a message that could conceptually correspond to:

        message User {
            int32 id = 1;
            string name = 2;
            string email = 3;
        }

    Protobuf uses numeric field tags rather than field names on the wire.
    """
    id: int = 0
    name: str = ""
    email: str = ""


user = UserMessage(101, "Atul", "atul@example.com")
print("Message:", user)

# Important protobuf design rule:
#
#   Field numbers are part of the serialized contract.
#
# Do not casually reuse a previously assigned field number for a different
# semantic field. A field can instead be deprecated/reserved.


# ============================================================================
# 3. A SMALL PROTOBUF-STYLE WIRE ENCODER
# ============================================================================

print("\n[3] Simplified Protocol Buffers wire encoding")


def encode_varint(value: int) -> bytes:
    """Encode a non-negative integer using protobuf-style base-128 varints."""
    if value < 0:
        raise ValueError("This educational encoder accepts non-negative integers.")

    output = bytearray()

    while True:
        current = value & 0x7F
        value >>= 7

        if value:
            output.append(current | 0x80)
        else:
            output.append(current)
            return bytes(output)


def decode_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decode a protobuf-style varint and return (value, next_offset)."""
    result = 0
    shift = 0

    while offset < len(data):
        byte = data[offset]
        offset += 1

        result |= (byte & 0x7F) << shift

        if not (byte & 0x80):
            return result, offset

        shift += 7

        if shift >= 64:
            raise ValueError("Malformed varint: too many bytes.")

    raise ValueError("Incomplete varint.")


def encode_string_field(field_number: int, value: str) -> bytes:
    """
    Encode a length-delimited protobuf field.

    Wire key:
        field_number << 3 | wire_type

    Strings use wire type 2.
    """
    if field_number <= 0:
        raise ValueError("Protobuf field numbers must be positive.")

    encoded_value = value.encode("utf-8")
    key = (field_number << 3) | 2

    return encode_varint(key) + encode_varint(len(encoded_value)) + encoded_value


def encode_int32_field(field_number: int, value: int) -> bytes:
    """Encode an integer field using protobuf wire type 0."""
    if field_number <= 0:
        raise ValueError("Field number must be positive.")

    key = (field_number << 3) | 0
    return encode_varint(key) + encode_varint(value)


def encode_user_message(user: UserMessage) -> bytes:
    """
    Simplified protobuf-compatible representation of our three fields.

    Real protobuf libraries handle many additional details:
    signed integers, repeated fields, maps, nested messages, enums,
    oneof, packed repeated fields, unknown fields, presence, and more.
    """
    encoded = bytearray()

    if user.id != 0:
        encoded.extend(encode_int32_field(1, user.id))

    if user.name:
        encoded.extend(encode_string_field(2, user.name))

    if user.email:
        encoded.extend(encode_string_field(3, user.email))

    return bytes(encoded)


encoded_user = encode_user_message(user)

print("Original:", user)
print("Encoded bytes:", encoded_user)
print("Encoded hexadecimal:", encoded_user.hex())


# ============================================================================
# 4. DECODING THE EDUCATIONAL MESSAGE
# ============================================================================

def decode_user_message(data: bytes) -> UserMessage:
    """Decode the limited message format implemented above."""
    result = UserMessage()
    offset = 0

    while offset < len(data):
        key, offset = decode_varint(data, offset)

        field_number = key >> 3
        wire_type = key & 0x07

        if field_number == 1 and wire_type == 0:
            result.id, offset = decode_varint(data, offset)

        elif field_number in (2, 3) and wire_type == 2:
            length, offset = decode_varint(data, offset)

            if offset + length > len(data):
                raise ValueError("Length-delimited field exceeds input.")

            text_value = data[offset:offset + length].decode("utf-8")
            offset += length

            if field_number == 2:
                result.name = text_value
            else:
                result.email = text_value

        else:
            raise ValueError(
                f"Unsupported field/wire type: {field_number}/{wire_type}"
            )

    return result


decoded_user = decode_user_message(encoded_user)
print("Decoded:", decoded_user)


# ============================================================================
# 5. PROTOBUF SCHEMA EVOLUTION
# ============================================================================

print("\n[4] Schema evolution")

# A compatible schema can add a new field without requiring old clients
# to understand it. Old clients generally ignore fields they do not know.
#
# Example conceptual schema:
#
# message User {
#     int32 id = 1;
#     string name = 2;
#     string email = 3;
#     string department = 4;   // newly added field
# }
#
# The field number 4 is new. Existing field numbers remain stable.
#
# Removing a field requires care. In a .proto file, a removed field number
# should normally be reserved so it is not accidentally reused:
#
#   reserved 4;
#   reserved "department";
#
# Other important protobuf types include:
#   bool
#   int32 / int64
#   uint32 / uint64
#   sint32 / sint64
#   fixed32 / fixed64
#   float / double
#   string
#   bytes
#   enum
#   message
#   repeated
#   map
#
# "oneof" allows mutually exclusive fields.
#
# Example:
#
#   oneof contact {
#       string email = 4;
#       string phone = 5;
#   }


# ============================================================================
# 6. RPC SERVICE CONTRACT
# ============================================================================

print("\n[5] Service contract")

@dataclass
class GetUserRequest:
    user_id: int


@dataclass
class GetUserResponse:
    user: Optional[UserMessage]
    found: bool
    message: str = ""


class RpcStatusCode(Enum):
    OK = "OK"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    UNAVAILABLE = "UNAVAILABLE"
    INTERNAL = "INTERNAL"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    PERMISSION_DENIED = "PERMISSION_DENIED"


class RpcError(Exception):
    """Exception representing a failed RPC."""

    def __init__(self, code: RpcStatusCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# A conceptual .proto contract could be:
#
# service UserService {
#     rpc GetUser(GetUserRequest) returns (GetUserResponse);
# }
#
# The .proto file acts as the interface contract between independently
# deployed services.


# ============================================================================
# 7. IN-PROCESS USER SERVICE
# ============================================================================

class UserService:
    """Server-side implementation of a small user service."""

    def __init__(self) -> None:
        self.users: Dict[int, UserMessage] = {
            1: UserMessage(1, "Ada", "ada@example.com"),
            2: UserMessage(2, "Grace", "grace@example.com"),
            3: UserMessage(3, "Alan", "alan@example.com"),
        }

    def get_user(self, request: GetUserRequest) -> GetUserResponse:
        if request.user_id <= 0:
            raise RpcError(
                RpcStatusCode.INVALID_ARGUMENT,
                "user_id must be positive",
            )

        user = self.users.get(request.user_id)

        if user is None:
            raise RpcError(
                RpcStatusCode.NOT_FOUND,
                f"User {request.user_id} does not exist",
            )

        return GetUserResponse(
            user=user,
            found=True,
            message="User retrieved successfully",
        )


server = UserService()

print("Server response:", server.get_user(GetUserRequest(1)))


# ============================================================================
# 8. CLIENT STUB
# ============================================================================

class UserServiceClient:
    """
    Client-side abstraction.

    A real generated gRPC stub would serialize the request, send it through
    the gRPC transport, receive the response, deserialize it, and expose a
    typed API to the application.
    """

    def __init__(self, service: UserService):
        self.service = service

    def get_user(self, user_id: int) -> GetUserResponse:
        request = GetUserRequest(user_id=user_id)
        return self.service.get_user(request)


client = UserServiceClient(server)

print("Client result:", client.get_user(2))

try:
    client.get_user(999)
except RpcError as error:
    print("RPC failure:", error.code.value, "-", error.message)


# ============================================================================
# 9. REQUEST/RESPONSE LIFECYCLE
# ============================================================================

print("\n[6] Conceptual unary RPC lifecycle")

lifecycle = [
    "1. Application constructs request message",
    "2. Generated client stub receives request",
    "3. Request is serialized",
    "4. gRPC transport sends the RPC",
    "5. Server receives and deserializes request",
    "6. Server interceptor/middleware may run",
    "7. Service implementation executes",
    "8. Response is serialized",
    "9. Client receives response and deserializes it",
    "10. Client application receives typed response or RPC error",
]

for step in lifecycle:
    print(step)


# ============================================================================
# 10. VALIDATION
# ============================================================================

print("\n[7] Validation and defensive programming")


def validate_user_id(user_id: Any) -> int:
    """Validate data at the service boundary."""
    if isinstance(user_id, bool):
        raise RpcError(
            RpcStatusCode.INVALID_ARGUMENT,
            "Boolean values are not valid user IDs.",
        )

    if not isinstance(user_id, int):
        raise RpcError(
            RpcStatusCode.INVALID_ARGUMENT,
            "user_id must be an integer.",
        )

    if user_id <= 0:
        raise RpcError(
            RpcStatusCode.INVALID_ARGUMENT,
            "user_id must be greater than zero.",
        )

    return user_id


for value in [1, 0, -5, "1", True]:
    try:
        print(value, "->", validate_user_id(value))
    except RpcError as error:
        print(value, "->", error.code.value, error.message)


# ============================================================================
# 11. DEADLINES
# ============================================================================

print("\n[8] Deadlines")

def perform_with_deadline(
    operation: Callable[[], Any],
    timeout_seconds: float,
) -> Any:
    """
    Demonstrate the idea of an RPC deadline.

    A deadline is preferable to an indefinite network wait because a
    downstream service that is already overloaded should not cause an
    unbounded chain of waiting requests.
    """
    if timeout_seconds <= 0:
        raise RpcError(
            RpcStatusCode.DEADLINE_EXCEEDED,
            "Deadline has already expired.",
        )

    started = time.monotonic()
    result = operation()
    elapsed = time.monotonic() - started

    if elapsed > timeout_seconds:
        raise RpcError(
            RpcStatusCode.DEADLINE_EXCEEDED,
            f"Operation exceeded deadline of {timeout_seconds:.3f}s.",
        )

    return result


def quick_operation() -> str:
    time.sleep(0.01)
    return "completed"


print(
    "Deadline result:",
    perform_with_deadline(quick_operation, timeout_seconds=0.1),
)


# ============================================================================
# 12. METADATA
# ============================================================================

print("\n[9] RPC metadata")

@dataclass
class RpcMetadata:
    """
    Metadata travels alongside the RPC.

    Typical examples:
      authorization information
      request IDs
      trace context
      tenant identifiers
      feature flags
    """
    values: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> Optional[str]:
        return self.values.get(key.lower())

    def set(self, key: str, value: str) -> None:
        self.values[key.lower()] = value


metadata = RpcMetadata()
metadata.set("x-request-id", str(uuid.uuid4()))
metadata.set("x-client", "study-client")

print("Request ID:", metadata.get("x-request-id"))
print("Client:", metadata.get("x-client"))


# ============================================================================
# 13. INTERCEPTORS
# ============================================================================

print("\n[10] Interceptor pattern")

def logging_interceptor(
    method_name: str,
    metadata: RpcMetadata,
    handler: Callable[[], Any],
) -> Any:
    started = time.monotonic()

    print(f"  -> RPC {method_name}")

    try:
        result = handler()
        elapsed_ms = (time.monotonic() - started) * 1000
        print(f"  <- RPC {method_name}: OK ({elapsed_ms:.2f} ms)")
        return result

    except RpcError as error:
        elapsed_ms = (time.monotonic() - started) * 1000
        print(
            f"  <- RPC {method_name}: "
            f"{error.code.value} ({elapsed_ms:.2f} ms)"
        )
        raise


request_metadata = RpcMetadata({"x-request-id": "request-123"})

logged_result = logging_interceptor(
    "UserService/GetUser",
    request_metadata,
    lambda: client.get_user(1),
)

print("Logged result:", logged_result)


# ============================================================================
# 14. AUTHENTICATION AND AUTHORIZATION
# ============================================================================

print("\n[11] Authentication and authorization")

@dataclass
class Identity:
    subject: str
    roles: set[str]


def require_role(identity: Identity, role: str) -> None:
    """
    Authentication answers "Who are you?"
    Authorization answers "What are you allowed to do?"
    """
    if role not in identity.roles:
        raise RpcError(
            RpcStatusCode.PERMISSION_DENIED,
            f"Required role '{role}' is missing.",
        )


admin = Identity("service-admin", {"reader", "writer", "admin"})
reader = Identity("service-reader", {"reader"})

require_role(admin, "reader")
print("Admin authorized to read.")

try:
    require_role(reader, "admin")
except RpcError as error:
    print("Authorization failure:", error.code.value, error.message)


# ============================================================================
# 15. IDEMPOTENCY
# ============================================================================

print("\n[12] Idempotency and retry safety")


class PaymentService:
    """
    A simplified payment service demonstrating an idempotency key.

    Network failures can make a client unsure whether a request was processed.
    Blindly retrying a non-idempotent operation can create duplicate effects.
    An idempotency key lets the server recognize repeated attempts.
    """

    def __init__(self) -> None:
        self.processed_keys: Dict[str, str] = {}
        self.total_received = 0.0

    def charge(self, amount: float, idempotency_key: str) -> str:
        if amount <= 0:
            raise RpcError(
                RpcStatusCode.INVALID_ARGUMENT,
                "Amount must be positive.",
            )

        if not idempotency_key:
            raise RpcError(
                RpcStatusCode.INVALID_ARGUMENT,
                "Idempotency key is required.",
            )

        if idempotency_key in self.processed_keys:
            return self.processed_keys[idempotency_key]

        self.total_received += amount

        receipt = f"payment-{len(self.processed_keys) + 1}"
        self.processed_keys[idempotency_key] = receipt

        return receipt


payment_service = PaymentService()

print("First charge:", payment_service.charge(100, "order-001"))
print("Retry charge:", payment_service.charge(100, "order-001"))
print("Total received:", payment_service.total_received)


# ============================================================================
# 16. RETRIES WITH EXPONENTIAL BACKOFF
# ============================================================================

print("\n[13] Retry strategy")

class TemporaryFailure(Exception):
    """Represents a transient downstream failure."""


def retry_with_exponential_backoff(
    operation: Callable[[], Any],
    attempts: int = 4,
    initial_delay: float = 0.01,
) -> Any:
    """
    Retry only failures that are explicitly classified as transient.

    Production retry systems also need:
      - maximum backoff
      - jitter
      - retry budgets
      - server-provided retry information where applicable
      - idempotency analysis
      - circuit-breaking considerations
    """
    if attempts <= 0:
        raise ValueError("attempts must be positive.")

    delay = initial_delay

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except TemporaryFailure:
            if attempt == attempts:
                raise

            jitter = random.uniform(0, delay * 0.25)
            time.sleep(delay + jitter)
            delay *= 2

    raise RuntimeError("Unreachable")


attempt_counter = {"value": 0}


def unreliable_operation() -> str:
    attempt_counter["value"] += 1

    if attempt_counter["value"] < 3:
        raise TemporaryFailure("Temporary downstream failure.")

    return "success"


print("Retry result:", retry_with_exponential_backoff(unreliable_operation))
print("Attempts:", attempt_counter["value"])


# ============================================================================
# 17. RPC ERROR CLASSIFICATION
# ============================================================================

print("\n[14] Status-code semantics")

status_meanings = {
    RpcStatusCode.OK: "Successful RPC.",
    RpcStatusCode.INVALID_ARGUMENT: "Caller supplied invalid input.",
    RpcStatusCode.NOT_FOUND: "Requested resource does not exist.",
    RpcStatusCode.DEADLINE_EXCEEDED: "Operation exceeded its deadline.",
    RpcStatusCode.UNAVAILABLE: "Service is temporarily unavailable.",
    RpcStatusCode.INTERNAL: "Unexpected server-side failure.",
    RpcStatusCode.UNAUTHENTICATED: "Caller identity was not established.",
    RpcStatusCode.PERMISSION_DENIED: "Caller is authenticated but lacks permission.",
}

for status, meaning in status_meanings.items():
    print(f"{status.value:20} {meaning}")


# ============================================================================
# 18. RPC COMMUNICATION PATTERNS
# ============================================================================

print("\n[15] RPC communication patterns")

# Four common gRPC RPC shapes:
#
# 1. Unary:
#       request -> response
#
# 2. Server streaming:
#       request -> response stream
#
# 3. Client streaming:
#       request stream -> response
#
# 4. Bidirectional streaming:
#       request stream <-> response stream
#
# The following functions model the shapes without requiring a network.


def unary_rpc(request: int) -> int:
    return request * 2


def server_streaming_rpc(limit: int) -> Generator[int, None, None]:
    for number in range(1, limit + 1):
        yield number * number


def client_streaming_rpc(values: Iterable[int]) -> int:
    return sum(values)


def bidirectional_streaming_rpc(
    values: Iterable[int],
) -> Generator[int, None, None]:
    for value in values:
        yield value * 10


print("Unary:", unary_rpc(5))
print("Server streaming:", list(server_streaming_rpc(5)))
print("Client streaming:", client_streaming_rpc([1, 2, 3, 4]))
print("Bidirectional:", list(bidirectional_streaming_rpc([2, 4, 6])))


# ============================================================================
# 19. STREAMING AND BACKPRESSURE
# ============================================================================

print("\n[16] Streaming and backpressure")

def producer(queue: Queue, values: Iterable[int]) -> None:
    for value in values:
        queue.put(value)

    queue.put(None)


def consumer(queue: Queue) -> List[int]:
    processed: List[int] = []

    while True:
        item = queue.get()

        if item is None:
            break

        # A real streaming service might perform database, network,
        # transformation, or analytical work here.
        processed.append(item * item)

    return processed


stream_queue: Queue[Optional[int]] = Queue(maxsize=2)

producer_thread = threading.Thread(
    target=producer,
    args=(stream_queue, range(1, 6)),
)

producer_thread.start()
processed_values = consumer(stream_queue)
producer_thread.join()

print("Processed stream:", processed_values)

# A bounded queue is important because an unlimited producer can consume
# memory when the consumer is slower. This is the core idea of backpressure.


# ============================================================================
# 20. ASYNCHRONOUS RPC
# ============================================================================

print("\n[17] Asynchronous RPC")

async def async_downstream_call(name: str, delay: float) -> str:
    await asyncio.sleep(delay)
    return f"{name} completed"


async def aggregate_services() -> List[str]:
    """
    Independent downstream calls can execute concurrently.

    This is useful for service aggregation APIs where the response depends
    on multiple independent services.
    """
    return await asyncio.gather(
        async_downstream_call("profile", 0.03),
        async_downstream_call("orders", 0.02),
        async_downstream_call("recommendations", 0.01),
    )


async_results = asyncio.run(aggregate_services())
print("Concurrent downstream results:", async_results)


# ============================================================================
# 21. SERVICE AGGREGATION
# ============================================================================

print("\n[18] Service aggregation")

@dataclass
class Dashboard:
    user: Optional[UserMessage]
    order_count: int
    recommendation_count: int


def build_dashboard(user_id: int) -> Dashboard:
    """
    An API gateway or backend-for-frontend can call multiple services and
    combine their responses into a client-oriented response.
    """
    user_response = client.get_user(user_id)

    # Simulated independent services.
    order_count = 4
    recommendation_count = 7

    return Dashboard(
        user=user_response.user,
        order_count=order_count,
        recommendation_count=recommendation_count,
    )


print("Dashboard:", build_dashboard(1))


# ============================================================================
# 22. SERVICE DISCOVERY
# ============================================================================

print("\n[19] Service discovery and load balancing")

@dataclass
class ServiceInstance:
    address: str
    healthy: bool = True
    active_requests: int = 0


class RoundRobinBalancer:
    """Very small round-robin load-balancer simulation."""

    def __init__(self, instances: List[ServiceInstance]):
        if not instances:
            raise ValueError("At least one instance is required.")

        self.instances = instances
        self.index = 0

    def choose(self) -> ServiceInstance:
        healthy_instances = [
            instance for instance in self.instances if instance.healthy
        ]

        if not healthy_instances:
            raise RpcError(
                RpcStatusCode.UNAVAILABLE,
                "No healthy service instances.",
            )

        selected = healthy_instances[self.index % len(healthy_instances)]
        self.index += 1
        selected.active_requests += 1
        return selected


instances = [
    ServiceInstance("user-service-1"),
    ServiceInstance("user-service-2"),
    ServiceInstance("user-service-3"),
]

balancer = RoundRobinBalancer(instances)

for _ in range(6):
    selected = balancer.choose()
    selected.active_requests -= 1
    print("Selected:", selected.address)


# ============================================================================
# 23. HEALTH CHECKING
# ============================================================================

print("\n[20] Health checking")

class HealthStatus(Enum):
    SERVING = "SERVING"
    NOT_SERVING = "NOT_SERVING"


@dataclass
class HealthResponse:
    status: HealthStatus
    service: str


class HealthService:
    def __init__(self) -> None:
        self.services: Dict[str, HealthStatus] = {}

    def set_status(self, service: str, status: HealthStatus) -> None:
        self.services[service] = status

    def check(self, service: str) -> HealthResponse:
        return HealthResponse(
            self.services.get(service, HealthStatus.NOT_SERVING),
            service,
        )


health = HealthService()
health.set_status("user-service", HealthStatus.SERVING)

print(health.check("user-service"))
print(health.check("missing-service"))


# ============================================================================
# 24. CACHING
# ============================================================================

print("\n[21] Client-side caching concept")

@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """Small in-memory TTL cache."""

    def __init__(self, ttl_seconds: float):
        if ttl_seconds <= 0:
            raise ValueError("TTL must be positive.")

        self.ttl_seconds = ttl_seconds
        self.entries: Dict[str, CacheEntry] = {}

    def put(self, key: str, value: Any) -> None:
        self.entries[key] = CacheEntry(
            value=value,
            expires_at=time.monotonic() + self.ttl_seconds,
        )

    def get(self, key: str) -> Optional[Any]:
        entry = self.entries.get(key)

        if entry is None:
            return None

        if time.monotonic() >= entry.expires_at:
            del self.entries[key]
            return None

        return entry.value


cache = TTLCache(0.1)
cache.put("user:1", user)

print("Cached value:", cache.get("user:1"))


# ============================================================================
# 25. BINARY VERSUS TEXT SERIALIZATION
# ============================================================================

print("\n[22] Serialization comparison")

sample_object = {
    "id": 1,
    "name": "Ada",
    "active": True,
}

json_bytes = json.dumps(
    sample_object,
    separators=(",", ":"),
).encode("utf-8")

protobuf_like_bytes = encode_user_message(
    UserMessage(1, "Ada", "ada@example.com")
)

print("JSON byte length:", len(json_bytes))
print("Protobuf-style byte length:", len(protobuf_like_bytes))
print("JSON:", json_bytes)
print("Binary representation:", protobuf_like_bytes.hex())

# Size is not the only consideration.
#
# Protocol Buffers provide:
#   - compact binary encoding
#   - explicit schemas
#   - generated types
#   - schema evolution mechanisms
#   - efficient parsing
#
# JSON provides:
#   - human readability
#   - broad browser/tool support
#   - easy manual inspection
#   - flexible ad-hoc interoperability
#
# The right choice depends on the communication boundary and operational
# requirements.


# ============================================================================
# 26. PERFORMANCE MEASUREMENT
# ============================================================================

print("\n[23] Basic performance measurement")

def benchmark(
    operation: Callable[[], Any],
    iterations: int = 1000,
) -> float:
    if iterations <= 0:
        raise ValueError("iterations must be positive.")

    started = time.perf_counter()

    for _ in range(iterations):
        operation()

    elapsed = time.perf_counter() - started
    return elapsed / iterations


average_encode_time = benchmark(
    lambda: encode_user_message(user),
    iterations=5000,
)

print(f"Average encoding time: {average_encode_time * 1_000_000:.2f} µs")


# ============================================================================
# 27. SECURITY CONSIDERATIONS
# ============================================================================

print("\n[24] Security considerations")

def fingerprint_token(token: str) -> str:
    """
    Never log raw credentials.

    This example produces a short fingerprint for correlation without
    printing the original secret.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


secret_token = "example-secret-token"
print("Token fingerprint:", fingerprint_token(secret_token))

# Production gRPC security commonly involves:
#   - TLS
#   - mutual TLS where appropriate
#   - authentication credentials
#   - authorization policies
#   - certificate lifecycle management
#   - input validation
#   - message size limits
#   - rate limiting
#   - safe secret storage
#   - careful logging
#   - dependency and supply-chain controls
#
# A service should never assume that an internal network is automatically
# trustworthy.


# ============================================================================
# 28. RESOURCE LIMITS
# ============================================================================

print("\n[25] Resource limits")

MAX_NAME_LENGTH = 100
MAX_REQUEST_BYTES = 1024


def validate_name(name: str) -> str:
    if not isinstance(name, str):
        raise RpcError(
            RpcStatusCode.INVALID_ARGUMENT,
            "Name must be a string.",
        )

    if not name.strip():
        raise RpcError(
            RpcStatusCode.INVALID_ARGUMENT,
            "Name cannot be empty.",
        )

    if len(name) > MAX_NAME_LENGTH:
        raise RpcError(
            RpcStatusCode.INVALID_ARGUMENT,
            "Name exceeds maximum length.",
        )

    return name.strip()


def validate_request_size(data: bytes) -> None:
    if len(data) > MAX_REQUEST_BYTES:
        raise RpcError(
            RpcStatusCode.INVALID_ARGUMENT,
            "Request exceeds configured size limit.",
        )


print("Valid name:", validate_name("Ada"))
validate_request_size(b"small request")

try:
    validate_name("x" * 101)
except RpcError as error:
    print("Validation failure:", error.message)


# ============================================================================
# 29. CONCURRENCY
# ============================================================================

print("\n[26] Concurrent request processing")

def compute_square(number: int) -> int:
    return number * number


with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [
        executor.submit(compute_square, number)
        for number in range(1, 9)
    ]

    concurrent_results = [future.result() for future in futures]

print("Concurrent results:", concurrent_results)

# Concurrency can improve throughput when requests spend time waiting on
# I/O. CPU-bound Python work is affected by interpreter implementation
# details and should be profiled before choosing a concurrency architecture.


# ============================================================================
# 30. DISTRIBUTED SYSTEM FAILURE
# ============================================================================

print("\n[27] Distributed-system failure model")

failure_modes = {
    "timeout": "The caller does not receive a response before its deadline.",
    "connection failure": "The transport connection cannot be established.",
    "service unavailable": "The destination cannot currently serve requests.",
    "partial failure": "Some downstream dependencies succeed while another fails.",
    "overload": "Traffic exceeds a service's sustainable capacity.",
    "duplicate request": "A retry may cause the same logical operation to execute twice.",
    "schema mismatch": "Client and server versions disagree about supported data.",
}

for failure, description in failure_modes.items():
    print(f"{failure:22} {description}")


# ============================================================================
# 31. PARTIAL FAILURE HANDLING
# ============================================================================

print("\n[28] Partial failure")

def safe_recommendation_service() -> List[str]:
    """
    A non-critical dependency can sometimes degrade gracefully.
    """
    try:
        # Simulated successful dependency.
        return ["item-1", "item-2", "item-3"]
    except Exception:
        return []


def resilient_dashboard(user_id: int) -> Dashboard:
    user_response = client.get_user(user_id)

    recommendations = safe_recommendation_service()

    return Dashboard(
        user=user_response.user,
        order_count=4,
        recommendation_count=len(recommendations),
    )


print("Resilient dashboard:", resilient_dashboard(1))


# ============================================================================
# 32. DISTRIBUTED TRACING
# ============================================================================

print("\n[29] Trace propagation")

@dataclass
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None


def create_child_span(parent: TraceContext) -> TraceContext:
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=uuid.uuid4().hex[:16],
        parent_span_id=parent.span_id,
    )


root_trace = TraceContext(
    trace_id=uuid.uuid4().hex,
    span_id=uuid.uuid4().hex[:16],
)

child_trace = create_child_span(root_trace)

print("Root trace:", root_trace)
print("Child trace:", child_trace)


# ============================================================================
# 33. PROTOBUF ENUMS AND ONEOF CONCEPTS
# ============================================================================

print("\n[30] Protobuf enum and oneof concepts")

class OrderState(Enum):
    CREATED = 0
    PAID = 1
    SHIPPED = 2
    CANCELLED = 3


@dataclass
class EmailContact:
    email: str


@dataclass
class PhoneContact:
    phone: str


Contact = EmailContact | PhoneContact

print("Enum:", OrderState.PAID)
print("Oneof-style value:", EmailContact("user@example.com"))


# ============================================================================
# 34. MAP AND REPEATED FIELDS
# ============================================================================

print("\n[31] Repeated and map concepts")

@dataclass
class Inventory:
    product_ids: List[int]
    quantities: Dict[str, int]


inventory = Inventory(
    product_ids=[101, 102, 103],
    quantities={
        "keyboard": 12,
        "mouse": 30,
        "monitor": 7,
    },
)

print("Repeated field:", inventory.product_ids)
print("Map field:", inventory.quantities)


# ============================================================================
# 35. NULLABILITY AND FIELD PRESENCE
# ============================================================================

print("\n[32] Field presence")

@dataclass
class ProfilePatch:
    display_name: Optional[str] = None
    timezone: Optional[str] = None


# In an update API, "not supplied" and "explicitly set to an empty value"
# can have different meanings. Protobuf's modern presence mechanisms,
# including optional fields and message fields, help APIs model that
# distinction explicitly.

patch = ProfilePatch(display_name=None)
print("Patch:", patch)


# ============================================================================
# 36. CONTRACT VERSIONING
# ============================================================================

print("\n[33] Contract versioning")

@dataclass(frozen=True)
class ApiVersion:
    major: int
    minor: int


def is_compatible(client_version: ApiVersion, server_version: ApiVersion) -> bool:
    """
    This is a simplified policy, not a universal protobuf compatibility rule.
    Real compatibility depends on exact schema and behavior changes.
    """
    return (
        client_version.major == server_version.major
        and client_version.minor <= server_version.minor
    )


print(
    "Version compatible:",
    is_compatible(ApiVersion(1, 2), ApiVersion(1, 4)),
)


# ============================================================================
# 37. BINARY FRAME CONCEPT
# ============================================================================

print("\n[34] Message framing concept")

def frame_message(payload: bytes) -> bytes:
    """
    A simplified length-prefixed frame.

    Actual gRPC framing has a defined wire format and compression handling.
    This function is only an educational model of the general idea:
        metadata/header -> payload length -> payload
    """
    return struct.pack("!I", len(payload)) + payload


def unframe_message(frame: bytes) -> bytes:
    if len(frame) < 4:
        raise ValueError("Frame is too short.")

    length = struct.unpack("!I", frame[:4])[0]

    if len(frame) != 4 + length:
        raise ValueError("Frame length does not match payload.")

    return frame[4:]


payload = b"hello-rpc"
frame = frame_message(payload)

print("Frame:", frame.hex())
print("Recovered payload:", unframe_message(frame))


# ============================================================================
# 38. BASE64 AND TEXT TRANSPORT
# ============================================================================

print("\n[35] Binary data and textual representations")

binary_data = b"\x00\x01\x02\xff"

encoded_base64 = base64.b64encode(binary_data).decode("ascii")
decoded_base64 = base64.b64decode(encoded_base64)

print("Base64:", encoded_base64)
print("Decoded:", decoded_base64)


# ============================================================================
# 39. SERVICE CONTRACT TESTING
# ============================================================================

print("\n[36] Contract-oriented testing")

def test_get_existing_user() -> None:
    response = server.get_user(GetUserRequest(1))

    assert response.found is True
    assert response.user is not None
    assert response.user.id == 1


def test_missing_user() -> None:
    try:
        server.get_user(GetUserRequest(9999))
    except RpcError as error:
        assert error.code == RpcStatusCode.NOT_FOUND
    else:
        raise AssertionError("Expected NOT_FOUND.")


def test_invalid_user() -> None:
    try:
        server.get_user(GetUserRequest(0))
    except RpcError as error:
        assert error.code == RpcStatusCode.INVALID_ARGUMENT
    else:
        raise AssertionError("Expected INVALID_ARGUMENT.")


test_get_existing_user()
test_missing_user()
test_invalid_user()

print("Contract tests passed.")


# ============================================================================
# 40. ADVANCED MICROSERVICE CASE STUDY
# ============================================================================

print("\n[37] Advanced service-to-service case study")


@dataclass
class Order:
    order_id: int
    user_id: int
    amount: float
    state: OrderState


class OrderService:
    """A stateful order service."""

    def __init__(self) -> None:
        self.orders: Dict[int, Order] = {
            5001: Order(5001, 1, 2499.0, OrderState.PAID),
            5002: Order(5002, 2, 1299.0, OrderState.CREATED),
            5003: Order(5003, 1, 5999.0, OrderState.SHIPPED),
        }

    def get_orders_for_user(self, user_id: int) -> List[Order]:
        validate_user_id(user_id)
        return [
            order
            for order in self.orders.values()
            if order.user_id == user_id
        ]


@dataclass
class UserDashboard:
    user: UserMessage
    orders: List[Order]
    total_value: float


class DashboardService:
    """
    Aggregating service.

    It depends on UserService and OrderService. This mirrors a common
    microservice architecture in which services have explicit contracts
    instead of sharing internal database tables.
    """

    def __init__(
        self,
        user_service: UserService,
        order_service: OrderService,
    ) -> None:
        self.user_service = user_service
        self.order_service = order_service

    def get_dashboard(self, user_id: int) -> UserDashboard:
        user_response = self.user_service.get_user(
            GetUserRequest(user_id)
        )

        if user_response.user is None:
            raise RpcError(
                RpcStatusCode.INTERNAL,
                "User response unexpectedly contained no user.",
            )

        orders = self.order_service.get_orders_for_user(user_id)
        total_value = sum(order.amount for order in orders)

        return UserDashboard(
            user=user_response.user,
            orders=orders,
            total_value=total_value,
        )


order_service = OrderService()
dashboard_service = DashboardService(server, order_service)

dashboard = dashboard_service.get_dashboard(1)

print("Dashboard user:", dashboard.user)
print("Orders:", dashboard.orders)
print("Total order value:", dashboard.total_value)


# ============================================================================
# 41. NESTED FAILURE PROPAGATION
# ============================================================================

print("\n[38] Failure propagation")

try:
    dashboard_service.get_dashboard(10000)
except RpcError as error:
    print("Aggregating service returned:", error.code.value, error.message)


# ============================================================================
# 42. RESOURCE OWNERSHIP AND TIMEOUT BUDGETS
# ============================================================================

print("\n[39] Timeout budgeting")

def remaining_budget(
    request_started: float,
    overall_deadline: float,
) -> float:
    elapsed = time.monotonic() - request_started
    return max(0.0, overall_deadline - elapsed)


request_started = time.monotonic()
overall_deadline = 0.2

time.sleep(0.01)

print(
    "Remaining downstream budget:",
    f"{remaining_budget(request_started, overall_deadline):.3f}s",
)


# ============================================================================
# 43. BULKHEAD CONCEPT
# ============================================================================

print("\n[40] Bulkhead isolation")

class Bulkhead:
    """
    Limits simultaneous work.

    If one dependency becomes slow, a bounded pool prevents it from consuming
    every worker available to the entire application.
    """

    def __init__(self, max_concurrent: int):
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive.")

        self.semaphore = threading.Semaphore(max_concurrent)

    def execute(self, operation: Callable[[], Any]) -> Any:
        acquired = self.semaphore.acquire(timeout=1)

        if not acquired:
            raise RpcError(
                RpcStatusCode.UNAVAILABLE,
                "Bulkhead capacity exhausted.",
            )

        try:
            return operation()
        finally:
            self.semaphore.release()


bulkhead = Bulkhead(max_concurrent=2)

print(
    "Bulkhead result:",
    bulkhead.execute(lambda: "isolated operation completed"),
)


# ============================================================================
# 44. CIRCUIT BREAKER
# ============================================================================

print("\n[41] Circuit breaker")

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Simplified circuit breaker.

    CLOSED:
        normal traffic

    OPEN:
        calls fail fast

    HALF_OPEN:
        limited test traffic determines whether recovery occurred
    """

    def __init__(self, failure_threshold: int = 3):
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive.")

        self.failure_threshold = failure_threshold
        self.failures = 0
        self.state = CircuitState.CLOSED

    def call(self, operation: Callable[[], Any]) -> Any:
        if self.state == CircuitState.OPEN:
            raise RpcError(
                RpcStatusCode.UNAVAILABLE,
                "Circuit is open.",
            )

        try:
            result = operation()
            self.failures = 0
            self.state = CircuitState.CLOSED
            return result

        except TemporaryFailure:
            self.failures += 1

            if self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN

            raise


breaker = CircuitBreaker(failure_threshold=2)

for _ in range(2):
    try:
        breaker.call(lambda: (_ for _ in ()).throw(TemporaryFailure()))
    except TemporaryFailure:
        print("Transient failure; circuit state:", breaker.state.value)

try:
    breaker.call(lambda: "should not execute")
except RpcError as error:
    print("Circuit breaker:", error.code.value, error.message)


# ============================================================================
# 45. DATA INTEGRITY
# ============================================================================

print("\n[42] Data integrity")

def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


message_bytes = encode_user_message(
    UserMessage(7, "Integrity Test", "integrity@example.com")
)

print("SHA-256:", checksum(message_bytes))


# ============================================================================
# 46. COMPLEXITY CONSIDERATIONS
# ============================================================================

print("\n[43] Complexity")

def find_user_linear(users: List[UserMessage], user_id: int) -> Optional[UserMessage]:
    for candidate in users:
        if candidate.id == user_id:
            return candidate

    return None


def build_user_index(
    users: Iterable[UserMessage],
) -> Dict[int, UserMessage]:
    return {candidate.id: candidate for candidate in users}


sample_users = [
    UserMessage(index, f"user-{index}", f"user-{index}@example.com")
    for index in range(10_000)
]

index = build_user_index(sample_users)

print("Linear lookup complexity: O(n)")
print("Indexed lookup average complexity: O(1)")
print("Indexed user:", index[9999])


# ============================================================================
# 47. MESSAGE SIZE AND MEMORY
# ============================================================================

print("\n[44] Message size considerations")

large_name = "A" * 100
large_message = UserMessage(
    id=42,
    name=large_name,
    email="large@example.com",
)

large_encoded = encode_user_message(large_message)

print("Large encoded message bytes:", len(large_encoded))

# Large messages can increase:
#   - network transfer time
#   - serialization cost
#   - memory consumption
#   - garbage collection pressure
#   - queue occupancy
#
# Prefer pagination, streaming, field selection, or specialized bulk APIs
# when an RPC would otherwise return an unnecessarily large payload.


# ============================================================================
# 48. API DESIGN PRINCIPLES
# ============================================================================

print("\n[45] API design principles")

api_principles = [
    "Design services around stable business capabilities.",
    "Keep message schemas explicit and versionable.",
    "Assign protobuf field numbers carefully.",
    "Do not reuse removed field numbers.",
    "Use deadlines for remote calls.",
    "Classify errors rather than returning arbitrary strings.",
    "Retry only failures that are safe and useful to retry.",
    "Use idempotency keys for retry-sensitive state changes.",
    "Propagate tracing and request context.",
    "Authenticate and authorize every relevant boundary.",
    "Set sensible message and resource limits.",
    "Measure latency, errors, throughput, and saturation.",
    "Avoid unnecessary synchronous dependency chains.",
]

for principle in api_principles:
    print("-", principle)


# ============================================================================
# 49. PRODUCTION OBSERVABILITY MODEL
# ============================================================================

print("\n[46] Observability")

@dataclass
class RpcMetrics:
    calls: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0

    @property
    def average_latency_ms(self) -> float:
        if self.calls == 0:
            return 0.0
        return self.total_latency_ms / self.calls


metrics = RpcMetrics()


def measured_rpc(operation: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    metrics.calls += 1

    try:
        return operation()
    except Exception:
        metrics.failures += 1
        raise
    finally:
        metrics.total_latency_ms += (
            time.perf_counter() - started
        ) * 1000


measured_rpc(lambda: client.get_user(1))
measured_rpc(lambda: client.get_user(2))

print("Calls:", metrics.calls)
print("Failures:", metrics.failures)
print("Average latency:", f"{metrics.average_latency_ms:.3f} ms")


# ============================================================================
# 50. PRACTICAL ARCHITECTURE
# ============================================================================

print("\n[47] Example production architecture")

architecture = """
Client Application
       |
       | HTTPS / gRPC
       v
API Gateway / Edge Service
       |
       +-------------------+
       |                   |
       v                   v
User Service          Order Service
       |                   |
       v                   v
 User Database        Order Database
       |
       +--------------------------+
                                  |
                                  v
                           Notification Service

Cross-cutting concerns:
- TLS
- authentication
- authorization
- deadlines
- retries
- load balancing
- health checks
- tracing
- metrics
- structured logging
- resource limits
"""

print(architecture)


# ============================================================================
# 51. COMMON MISTAKES
# ============================================================================

print("\n[48] Common mistakes")

mistakes = [
    "Treating a remote call as if it were a local function.",
    "Ignoring network latency and partial failure.",
    "Calling remote services without deadlines.",
    "Retrying every error indiscriminately.",
    "Retrying non-idempotent writes without protection.",
    "Reusing protobuf field numbers after deletion.",
    "Putting secrets into ordinary logs.",
    "Creating very large messages when streaming or pagination is appropriate.",
    "Ignoring schema compatibility.",
    "Creating long chains of synchronous service dependencies.",
    "Failing to propagate trace or request context.",
    "Assuming internal services require no authentication.",
]

for mistake in mistakes:
    print("-", mistake)


# ============================================================================
# 52. LIMITATIONS OF THIS STUDY IMPLEMENTATION
# ============================================================================

print("\n[49] Scope")

print(
    "This file models gRPC and protobuf mechanisms locally for learning. "
    "A production implementation normally uses generated code from .proto "
    "definitions, an actual gRPC runtime, HTTP/2 transport, TLS, service "
    "discovery/load balancing infrastructure, and operational observability."
)


# ============================================================================
# 53. FINAL INTEGRATED DEMONSTRATION
# ============================================================================

print("\n[50] Integrated demonstration")

def integrated_request(user_id: int) -> Dict[str, Any]:
    """
    Combines:
      - validation
      - metadata
      - tracing
      - service call
      - error classification
      - structured response
    """
    validate_user_id(user_id)

    request_id = uuid.uuid4().hex
    trace_id = uuid.uuid4().hex

    metadata = RpcMetadata({
        "x-request-id": request_id,
        "x-trace-id": trace_id,
    })

    try:
        response = logging_interceptor(
            "UserService/GetUser",
            metadata,
            lambda: client.get_user(user_id),
        )

        return {
            "request_id": request_id,
            "trace_id": trace_id,
            "status": RpcStatusCode.OK.value,
            "user": dataclasses.asdict(response.user)
            if response.user
            else None,
        }

    except RpcError as error:
        return {
            "request_id": request_id,
            "trace_id": trace_id,
            "status": error.code.value,
            "error": error.message,
        }


print(json.dumps(integrated_request(1), indent=2))
print(json.dumps(integrated_request(999), indent=2))

print("\nStudy script completed successfully.")
