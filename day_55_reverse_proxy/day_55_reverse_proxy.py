#!/usr/bin/env python3
"""
Reverse Proxy Simulation
Topic: Reverse Proxy, Nginx, Proxying, TLS Termination

This self-contained program models the core behavior of a reverse proxy:
- client-to-proxy TLS termination
- HTTP request routing
- upstream selection
- health checks
- load balancing
- forwarded headers
- connection and request validation
- upstream failures
- retry behavior
- access logging
- security controls

It intentionally simulates network behavior rather than opening real sockets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import ipaddress
import random
import re
import time


class Protocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"


class UpstreamState(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class ProxyError(Exception):
    """Base exception for proxy-related failures."""


class BadRequestError(ProxyError):
    """Raised when a client request violates proxy policy."""


class TLSConfigurationError(ProxyError):
    """Raised when TLS termination cannot be completed."""


class UpstreamUnavailableError(ProxyError):
    """Raised when no usable upstream exists."""


@dataclass(frozen=True)
class TLSCertificate:
    hostname: str
    issuer: str
    minimum_tls_version: str = "TLS1.2"

    def validate(self, requested_host: str, tls_version: str) -> None:
        if requested_host != self.hostname:
            raise TLSConfigurationError(
                f"certificate does not match host {requested_host}"
            )

        allowed = {"TLS1.2", "TLS1.3"}
        if tls_version not in allowed:
            raise TLSConfigurationError(
                f"TLS version {tls_version} is not permitted"
            )


@dataclass
class Request:
    client_ip: str
    host: str
    method: str
    path: str
    protocol: Protocol
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    def validate(self) -> None:
        try:
            ipaddress.ip_address(self.client_ip)
        except ValueError as exc:
            raise BadRequestError("invalid client IP address") from exc

        if self.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise BadRequestError(f"unsupported HTTP method: {self.method}")

        if not self.path.startswith("/"):
            raise BadRequestError("path must start with '/'")

        if len(self.path) > 4096:
            raise BadRequestError("request URI is too long")

        if "\r" in self.path or "\n" in self.path:
            raise BadRequestError("request path contains invalid control characters")


@dataclass
class Response:
    status: int
    body: str
    upstream: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class UpstreamServer:
    name: str
    address: str
    port: int
    weight: int = 1
    state: UpstreamState = UpstreamState.HEALTHY
    active_connections: int = 0
    requests_served: int = 0

    def healthy(self) -> bool:
        return self.state == UpstreamState.HEALTHY


@dataclass(frozen=True)
class LocationRule:
    prefix: str
    upstream_group: str


@dataclass
class AccessLogEntry:
    timestamp: float
    client_ip: str
    method: str
    path: str
    status: int
    upstream: str | None
    duration_ms: float


class TLSManager:
    def __init__(self, certificates: list[TLSCertificate]):
        self.certificates = {cert.hostname: cert for cert in certificates}

    def terminate(self, host: str, tls_version: str) -> None:
        certificate = self.certificates.get(host)
        if certificate is None:
            raise TLSConfigurationError(f"no certificate configured for {host}")

        certificate.validate(host, tls_version)


class RoundRobinBalancer:
    def __init__(self):
        self.positions: dict[str, int] = defaultdict(int)

    def choose(
        self,
        group_name: str,
        servers: list[UpstreamServer],
    ) -> UpstreamServer:
        healthy = [
            server
            for server in servers
            if server.healthy() and server.weight > 0
        ]

        if not healthy:
            raise UpstreamUnavailableError(
                f"no healthy upstream servers in group {group_name}"
            )

        weighted: list[UpstreamServer] = []
        for server in healthy:
            weighted.extend([server] * server.weight)

        index = self.positions[group_name] % len(weighted)
        self.positions[group_name] += 1
        return weighted[index]


class ReverseProxy:
    def __init__(
        self,
        tls_manager: TLSManager,
        upstreams: dict[str, list[UpstreamServer]],
        routes: list[LocationRule],
        trusted_proxy_ranges: list[str] | None = None,
        max_body_size: int = 1_000_000,
    ):
        self.tls_manager = tls_manager
        self.upstreams = upstreams
        self.routes = routes
        self.balancer = RoundRobinBalancer()
        self.logs: list[AccessLogEntry] = []
        self.max_body_size = max_body_size
        self.trusted_proxy_ranges = [
            ipaddress.ip_network(value)
            for value in (trusted_proxy_ranges or [])
        ]

    def _find_route(self, path: str) -> LocationRule:
        matching = [
            route for route in self.routes
            if path.startswith(route.prefix)
        ]

        if not matching:
            raise BadRequestError(f"no route configured for {path}")

        # Longest-prefix matching mirrors the practical behavior expected
        # from path-based reverse proxy configuration.
        return max(matching, key=lambda route: len(route.prefix))

    def _validate_forwarded_headers(self, request: Request) -> None:
        forwarded = request.headers.get("X-Forwarded-For")

        # A client must not be allowed to impersonate a trusted proxy chain.
        if forwarded and not self._client_is_trusted(request.client_ip):
            raise BadRequestError(
                "untrusted client supplied X-Forwarded-For"
            )

    def _client_is_trusted(self, client_ip: str) -> bool:
        address = ipaddress.ip_address(client_ip)
        return any(address in network for network in self.trusted_proxy_ranges)

    def _build_upstream_headers(self, request: Request) -> dict[str, str]:
        existing = request.headers.get("X-Forwarded-For")

        if existing:
            forwarded_for = f"{existing}, {request.client_ip}"
        else:
            forwarded_for = request.client_ip

        return {
            "Host": request.host,
            "X-Real-IP": request.client_ip,
            "X-Forwarded-For": forwarded_for,
            "X-Forwarded-Proto": request.protocol.value,
        }

    def _send_upstream(
        self,
        server: UpstreamServer,
        request: Request,
        headers: dict[str, str],
    ) -> Response:
        if not server.healthy():
            raise UpstreamUnavailableError(
                f"upstream {server.name} is unhealthy"
            )

        server.active_connections += 1
        try:
            server.requests_served += 1

            # Simulated application failure.
            if request.path == "/api/failure":
                raise ConnectionError(
                    f"simulated connection failure at {server.name}"
                )

            body = (
                f"application response from {server.name}; "
                f"path={request.path}; "
                f"forwarded_for={headers['X-Forwarded-For']}"
            )

            return Response(
                status=200,
                body=body,
                upstream=server.name,
                headers={
                    "Content-Type": "text/plain",
                    "X-Upstream": server.name,
                },
            )
        finally:
            server.active_connections -= 1

    def handle(self, request: Request) -> Response:
        started = time.perf_counter()

        try:
            request.validate()

            if len(request.body.encode("utf-8")) > self.max_body_size:
                raise BadRequestError("request body exceeds configured limit")

            self._validate_forwarded_headers(request)

            if request.protocol == Protocol.HTTPS:
                tls_version = request.headers.get("X-TLS-Version", "TLS1.3")
                self.tls_manager.terminate(request.host, tls_version)

            route = self._find_route(request.path)
            servers = self.upstreams.get(route.upstream_group, [])

            if not servers:
                raise UpstreamUnavailableError(
                    f"upstream group {route.upstream_group} does not exist"
                )

            upstream_headers = self._build_upstream_headers(request)

            # Retry once against another healthy server if the first
            # upstream experiences a simulated transport failure.
            attempted: set[str] = set()
            last_error: Exception | None = None

            for _ in range(2):
                candidates = [
                    server
                    for server in servers
                    if server.name not in attempted and server.healthy()
                ]

                if not candidates:
                    break

                server = self.balancer.choose(route.upstream_group, candidates)
                attempted.add(server.name)

                try:
                    response = self._send_upstream(
                        server, request, upstream_headers
                    )
                    return response
                except ConnectionError as exc:
                    last_error = exc
                    continue

            if last_error:
                raise UpstreamUnavailableError(str(last_error))

            raise UpstreamUnavailableError(
                f"all upstream servers for {route.upstream_group} failed"
            )

        except BadRequestError as exc:
            return Response(400, f"Bad Request: {exc}")
        except TLSConfigurationError as exc:
            return Response(495, f"TLS Error: {exc}")
        except UpstreamUnavailableError as exc:
            return Response(503, f"Service Unavailable: {exc}")
        finally:
            duration = (time.perf_counter() - started) * 1000

            # The status is reconstructed when the operation raises before
            # a response exists. This keeps access logging deterministic.
            status = 200
            upstream = None

            if "response" in locals():
                status = response.status
                upstream = response.upstream
            elif "exc" in locals():
                if isinstance(exc, BadRequestError):
                    status = 400
                elif isinstance(exc, TLSConfigurationError):
                    status = 495
                else:
                    status = 503

            self.logs.append(
                AccessLogEntry(
                    timestamp=time.time(),
                    client_ip=request.client_ip,
                    method=request.method,
                    path=request.path,
                    status=status,
                    upstream=upstream,
                    duration_ms=duration,
                )
            )


def run_health_check(server: UpstreamServer, success: bool) -> None:
    """Simulate an active health check."""
    server.state = (
        UpstreamState.HEALTHY if success else UpstreamState.UNHEALTHY
    )


def print_response(label: str, response: Response) -> None:
    print(f"\n[{label}]")
    print(f"status={response.status}")
    print(f"upstream={response.upstream}")
    print(f"body={response.body}")


def main() -> None:
    certificates = [
        TLSCertificate(
            hostname="api.example.com",
            issuer="Example Internal CA",
        )
    ]

    tls_manager = TLSManager(certificates)

    api_servers = [
        UpstreamServer("api-1", "10.0.1.10", 8080, weight=2),
        UpstreamServer("api-2", "10.0.1.11", 8080, weight=1),
    ]

    web_servers = [
        UpstreamServer("web-1", "10.0.2.10", 8080),
        UpstreamServer("web-2", "10.0.2.11", 8080),
    ]

    proxy = ReverseProxy(
        tls_manager=tls_manager,
        upstreams={
            "api_backend": api_servers,
            "web_backend": web_servers,
        },
        routes=[
            LocationRule("/api/", "api_backend"),
            LocationRule("/", "web_backend"),
        ],
        trusted_proxy_ranges=["10.0.0.0/8"],
    )

    requests = [
        Request(
            client_ip="203.0.113.20",
            host="api.example.com",
            method="GET",
            path="/api/users",
            protocol=Protocol.HTTPS,
            headers={"X-TLS-Version": "TLS1.3"},
        ),
        Request(
            client_ip="203.0.113.21",
            host="api.example.com",
            method="GET",
            path="/",
            protocol=Protocol.HTTPS,
            headers={"X-TLS-Version": "TLS1.2"},
        ),
        Request(
            client_ip="203.0.113.22",
            host="api.example.com",
            method="GET",
            path="/api/failure",
            protocol=Protocol.HTTPS,
        ),
        Request(
            client_ip="203.0.113.23",
            host="api.example.com",
            method="GET",
            path="/api/users",
            protocol=Protocol.HTTPS,
            headers={"X-Forwarded-For": "198.51.100.4"},
        ),
    ]

    for index, request in enumerate(requests, start=1):
        response = proxy.handle(request)
        print_response(f"request-{index}", response)

    print("\n[health-check]")
    run_health_check(api_servers[0], False)
    print(f"{api_servers[0].name}: {api_servers[0].state.value}")

    response = proxy.handle(
        Request(
            client_ip="203.0.113.24",
            host="api.example.com",
            method="GET",
            path="/api/orders",
            protocol=Protocol.HTTPS,
        )
    )
    print_response("healthy-fallback", response)

    print("\n[statistics]")
    for group_name, servers in proxy.upstreams.items():
        print(f"{group_name}:")
        for server in servers:
            print(
                f"  {server.name}: state={server.state.value}, "
                f"requests={server.requests_served}, "
                f"active={server.active_connections}"
            )

    print("\n[access-log]")
    for entry in proxy.logs:
        print(
            f"{entry.client_ip} {entry.method} {entry.path} "
            f"{entry.status} upstream={entry.upstream} "
            f"{entry.duration_ms:.2f}ms"
        )


if __name__ == "__main__":
    random.seed(42)
    main()
