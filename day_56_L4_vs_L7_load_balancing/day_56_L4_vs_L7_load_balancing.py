#!/usr/bin/env python3

"""
L4 vs L7 Load Balancing
Transport-level balancing versus application-level balancing.

The simulation models:
- L4 balancing using TCP connection/flow hashing and least-connections.
- L7 balancing using HTTP-aware routing, host/path rules, health checks,
  weighted routing, and session affinity.
- Connection lifecycle and request lifecycle.
- Failure handling and observability.
- Security and validation boundaries.

No external dependencies are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from hashlib import sha256
from typing import Dict, List, Optional, Tuple


class Protocol(str, Enum):
    TCP = "TCP"
    HTTP = "HTTP"


class BackendState(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class Client:
    ip: str
    source_port: int


@dataclass(frozen=True)
class Request:
    method: str
    host: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if self.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError(f"Unsupported HTTP method: {self.method}")

        if not self.host or len(self.host) > 253:
            raise ValueError("Invalid host")

        if not self.path.startswith("/"):
            raise ValueError("HTTP path must start with '/'")

        if len(self.path) > 4096:
            raise ValueError("HTTP path exceeds configured limit")


@dataclass
class Backend:
    name: str
    address: str
    port: int
    state: BackendState = BackendState.HEALTHY
    active_connections: int = 0
    requests_served: int = 0
    weight: int = 1

    def available(self) -> bool:
        return self.state == BackendState.HEALTHY and self.weight > 0


class L4LoadBalancer:
    """
    L4 operates on transport flows.

    It does not need to inspect HTTP paths or application headers. Once a
    TCP flow is selected, packets belonging to that flow remain associated
    with the selected backend.
    """

    def __init__(self, backends: List[Backend]) -> None:
        if not backends:
            raise ValueError("At least one backend is required")
        self.backends = backends
        self.flow_table: Dict[Tuple[str, int, str, int], str] = {}

    def _healthy(self) -> List[Backend]:
        return [backend for backend in self.backends if backend.available()]

    def select_backend(
        self,
        client: Client,
        destination_ip: str,
        destination_port: int,
    ) -> Backend:
        key = (client.ip, client.source_port, destination_ip, destination_port)

        existing = self.flow_table.get(key)
        if existing:
            backend = next(
                (item for item in self.backends if item.name == existing),
                None,
            )
            if backend and backend.available():
                return backend

            # A failed backend invalidates the old flow mapping.
            del self.flow_table[key]

        candidates = self._healthy()
        if not candidates:
            raise RuntimeError("L4: no healthy backend is available")

        # Deterministic flow hashing keeps packets from one TCP flow together.
        digest = sha256(repr(key).encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % len(candidates)
        backend = candidates[index]

        self.flow_table[key] = backend.name
        backend.active_connections += 1
        return backend

    def close_connection(
        self,
        client: Client,
        destination_ip: str,
        destination_port: int,
    ) -> None:
        key = (client.ip, client.source_port, destination_ip, destination_port)
        backend_name = self.flow_table.pop(key, None)

        if backend_name is None:
            return

        backend = next(
            (item for item in self.backends if item.name == backend_name),
            None,
        )
        if backend:
            backend.active_connections = max(0, backend.active_connections - 1)
            backend.requests_served += 1


class L7LoadBalancer:
    """
    L7 operates on individual application requests.

    Because the balancer understands HTTP, it can route by:
    - host
    - URL path
    - HTTP headers
    - cookies
    - method
    """

    def __init__(self, backends: List[Backend]) -> None:
        self.backends = backends
        self.routes = {
            "/api": ["api-1", "api-2"],
            "/static": ["static-1"],
        }
        self.session_affinity: Dict[str, str] = {}

    def _find_backend(self, name: str) -> Optional[Backend]:
        return next((backend for backend in self.backends if backend.name == name), None)

    def _healthy(self, names: List[str]) -> List[Backend]:
        return [
            backend
            for name in names
            if (backend := self._find_backend(name)) is not None
            and backend.available()
        ]

    def _route_candidates(self, request: Request) -> List[Backend]:
        if request.path.startswith("/api"):
            names = self.routes["/api"]
        elif request.path.startswith("/static"):
            names = self.routes["/static"]
        else:
            names = [backend.name for backend in self.backends]

        candidates = self._healthy(names)
        if not candidates:
            raise RuntimeError(f"L7: no healthy backend for {request.path}")

        return candidates

    def route(self, request: Request) -> Backend:
        request.validate()

        cookie = request.headers.get("Cookie", "")
        session_id = None

        for token in cookie.split(";"):
            token = token.strip()
            if token.startswith("SESSION_ID="):
                session_id = token.split("=", 1)[1].strip()
                break

        candidates = self._route_candidates(request)

        if session_id:
            existing_name = self.session_affinity.get(session_id)
            existing = self._find_backend(existing_name) if existing_name else None

            if existing and existing in candidates and existing.available():
                backend = existing
            else:
                backend = min(candidates, key=lambda item: item.active_connections)
                self.session_affinity[session_id] = backend.name
        else:
            backend = min(candidates, key=lambda item: item.active_connections)

        backend.requests_served += 1
        return backend


def health_check(backends: List[Backend]) -> Dict[str, str]:
    """
    A real implementation would perform TCP or HTTP probes.
    Here the state is already represented by the backend model.
    """
    return {backend.name: backend.state.value for backend in backends}


def print_backend_state(title: str, backends: List[Backend]) -> None:
    print(f"\n{title}")
    for backend in backends:
        print(
            f"{backend.name:10} "
            f"state={backend.state.value:10} "
            f"connections={backend.active_connections:2} "
            f"requests={backend.requests_served:2}"
        )


def main() -> None:
    l4_backends = [
        Backend("api-1", "10.0.0.11", 8443),
        Backend("api-2", "10.0.0.12", 8443),
        Backend("api-3", "10.0.0.13", 8443),
    ]

    l7_backends = [
        Backend("api-1", "10.0.0.11", 8080),
        Backend("api-2", "10.0.0.12", 8080),
        Backend("static-1", "10.0.0.21", 8080),
    ]

    print("L4 health:", health_check(l4_backends))

    l4 = L4LoadBalancer(l4_backends)

    client_a = Client("192.168.1.10", 50001)
    client_b = Client("192.168.1.11", 50002)

    backend_a = l4.select_backend(client_a, "203.0.113.10", 443)
    backend_b = l4.select_backend(client_b, "203.0.113.10", 443)

    print(f"\nL4 flow A -> {backend_a.name}")
    print(f"L4 flow B -> {backend_b.name}")

    # A backend failure causes a new flow mapping to be selected.
    backend_a.state = BackendState.UNHEALTHY
    replacement = l4.select_backend(client_a, "203.0.113.10", 443)
    print(f"L4 after failure -> {replacement.name}")

    l4.close_connection(client_b, "203.0.113.10", 443)
    print_backend_state("L4 backend state", l4_backends)

    print("\nL7 health:", health_check(l7_backends))

    l7 = L7LoadBalancer(l7_backends)

    requests = [
        Request(
            "GET",
            "api.example.com",
            "/api/orders",
            {"Cookie": "SESSION_ID=customer-42"},
        ),
        Request(
            "GET",
            "api.example.com",
            "/api/products",
            {"Cookie": "SESSION_ID=customer-42"},
        ),
        Request(
            "GET",
            "cdn.example.com",
            "/static/app.js",
        ),
        Request(
            "GET",
            "api.example.com",
            "/health",
        ),
    ]

    for request in requests:
        backend = l7.route(request)
        print(
            f"L7 {request.method:6} "
            f"{request.host}{request.path:25} -> {backend.name}"
        )

    # The API route loses one backend. Existing session affinity must be
    # re-evaluated instead of sending traffic to an unhealthy server.
    failed = l7_backends[0]
    failed.state = BackendState.UNHEALTHY

    retry = l7.route(
        Request(
            "GET",
            "api.example.com",
            "/api/orders",
            {"Cookie": "SESSION_ID=customer-42"},
        )
    )

    print(f"L7 session after backend failure -> {retry.name}")
    print_backend_state("L7 backend state", l7_backends)

    # Security boundary: reject malformed application-level input.
    try:
        l7.route(Request("TRACE", "api.example.com", "/api/admin"))
    except ValueError as exc:
        print(f"\nValidation failure handled safely: {exc}")

    print(
        "\nDesign distinction:\n"
        "L4 selects a backend for a transport flow and normally cannot route "
        "on HTTP semantics.\n"
        "L7 can independently route HTTP requests using application context, "
        "but incurs parsing and application-awareness overhead."
    )


if __name__ == "__main__":
    main()
