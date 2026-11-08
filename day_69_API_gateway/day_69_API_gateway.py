#!/usr/bin/env python3
"""
API Gateway: Routing, Authentication, and Rate Limiting

A self-contained API Gateway simulator using Python's standard library.

Features:
- HTTP method and path-based routing
- Bearer-token authentication
- API key validation
- Per-client token-bucket rate limiting
- Route-specific authorization scopes
- Request validation
- Upstream service simulation
- Structured request logging
- Error handling and automated tests
- JSON configuration export
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("api_gateway")


# ---------------------------------------------------------
# HTTP domain types
# ---------------------------------------------------------

class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class GatewayStatus(str, Enum):
    SUCCESS = "SUCCESS"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    client_ip: str = "127.0.0.1"

    def validate(self) -> None:
        if self.method.upper() not in HTTPMethod._value2member_map_:
            raise ValueError("Unsupported HTTP method")

        if not self.path.startswith("/") or len(self.path) > 2048:
            raise ValueError("Invalid request path")

        if ".." in self.path.split("/"):
            raise ValueError("Path traversal is not allowed")


@dataclass
class Response:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class APIClient:
    client_id: str
    token: str
    scopes: frozenset[str]
    enabled: bool = True


@dataclass(frozen=True)
class Route:
    route_id: str
    method: str
    path_pattern: str
    upstream_service: str
    required_scope: str
    rate_limit: int = 5
    burst_capacity: int = 10


@dataclass
class RateLimitState:
    tokens: float
    last_updated: float


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------

class AuthenticationError(Exception):
    pass


class AuthorizationError(Exception):
    pass


class Authenticator:

    def __init__(self, clients: list[APIClient]):
        self.clients = {
            client.token: client
            for client in clients
        }

    def authenticate(self, headers: dict[str, str]) -> APIClient:

        authorization = headers.get("Authorization", "")

        if not authorization.startswith("Bearer "):
            raise AuthenticationError("Bearer token required")

        token = authorization[7:].strip()

        if not token:
            raise AuthenticationError("Empty bearer token")

        client = self.clients.get(token)

        if client is None or not client.enabled:
            raise AuthenticationError("Invalid or disabled credentials")

        return client

    @staticmethod
    def authorize(client: APIClient, required_scope: str) -> None:

        if required_scope not in client.scopes:
            raise AuthorizationError(
                f"Missing required scope: {required_scope}"
            )


# ---------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------

class TokenBucketRateLimiter:
    """
    Token bucket algorithm.

    Tokens refill continuously at the configured rate.
    Requests consume one token.
    Excess requests receive HTTP 429.

    State is maintained per client and route.
    """

    def __init__(self):
        self.buckets: dict[
            tuple[str, str], RateLimitState
        ] = {}

    def allow(
        self,
        client_id: str,
        route: Route,
        now: float | None = None
    ) -> tuple[bool, int]:

        current_time = time.monotonic() if now is None else now

        if route.rate_limit <= 0 or route.burst_capacity <= 0:
            raise ValueError("Rate limits must be positive")

        key = (client_id, route.route_id)

        state = self.buckets.get(key)

        if state is None:
            state = RateLimitState(
                tokens=float(route.burst_capacity),
                last_updated=current_time
            )
            self.buckets[key] = state

        elapsed = max(0.0, current_time - state.last_updated)

        state.tokens = min(
            float(route.burst_capacity),
            state.tokens + elapsed * route.rate_limit
        )

        state.last_updated = max(
            state.last_updated,
            current_time
        )

        if state.tokens >= 1:
            state.tokens -= 1
            remaining = int(state.tokens)
            return True, remaining

        return False, 0


# ---------------------------------------------------------
# Route registry
# ---------------------------------------------------------

class Router:

    def __init__(self):
        self.routes: list[Route] = []

    def register(self, route: Route) -> None:

        if route.method not in HTTPMethod._value2member_map_:
            raise ValueError("Invalid route method")

        if not route.path_pattern.startswith("/"):
            raise ValueError("Route must start with /")

        if any(
            existing.method == route.method
            and existing.path_pattern == route.path_pattern
            for existing in self.routes
        ):
            raise ValueError("Duplicate route registration")

        if route.rate_limit <= 0 or route.burst_capacity <= 0:
            raise ValueError("Invalid rate-limit configuration")

        self.routes.append(route)

        # Prefer more specific routes over parameterized routes.
        self.routes.sort(
            key=lambda r: (
                -len(r.path_pattern.split("/")),
                -len(r.path_pattern)
            )
        )

    def resolve(
        self,
        method: str,
        path: str
    ) -> tuple[Route, dict[str, str]] | None:

        for route in self.routes:

            if route.method != method.upper():
                continue

            pattern = re.sub(
                r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}",
                r"(?P<\1>[^/]+)",
                route.path_pattern
            )

            match = re.fullmatch(pattern, path)

            if match:
                return route, match.groupdict()

        return None


# ---------------------------------------------------------
# Upstream services
# ---------------------------------------------------------

class UpstreamServiceRegistry:

    def __init__(self):
        self.services: dict[
            str,
            Callable[[Request, dict[str, str]], Response]
        ] = {}

    def register(
        self,
        service_name: str,
        handler: Callable[[Request, dict[str, str]], Response]
    ) -> None:

        if service_name in self.services:
            raise ValueError("Service already registered")

        self.services[service_name] = handler

    def forward(
        self,
        service_name: str,
        request: Request,
        parameters: dict[str, str]
    ) -> Response:

        handler = self.services.get(service_name)

        if handler is None:
            raise RuntimeError("Upstream service unavailable")

        return handler(request, parameters)


# ---------------------------------------------------------
# Request audit
# ---------------------------------------------------------

@dataclass
class AuditRecord:
    request_id: str
    client_id: str
    method: str
    path: str
    status_code: int
    timestamp: float


class AuditLogger:

    def __init__(self):
        self.records: list[AuditRecord] = []

    def record(
        self,
        request_id: str,
        client_id: str,
        request: Request,
        status_code: int
    ) -> None:

        self.records.append(
            AuditRecord(
                request_id=request_id,
                client_id=client_id,
                method=request.method.upper(),
                path=request.path,
                status_code=status_code,
                timestamp=time.time()
            )
        )

    def export_json(self, filename: str) -> None:

        data = [
            {
                "request_id": r.request_id,
                "client_id": r.client_id,
                "method": r.method,
                "path": r.path,
                "status_code": r.status_code,
                "timestamp": r.timestamp
            }
            for r in self.records
        ]

        Path(filename).write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )


# ---------------------------------------------------------
# API Gateway
# ---------------------------------------------------------

class APIGateway:

    def __init__(
        self,
        authenticator: Authenticator,
        router: Router,
        limiter: TokenBucketRateLimiter,
        upstreams: UpstreamServiceRegistry
    ):

        self.authenticator = authenticator
        self.router = router
        self.limiter = limiter
        self.upstreams = upstreams
        self.audit = AuditLogger()

    def handle(self, request: Request) -> Response:

        request_id = str(uuid.uuid4())
        client_id = "anonymous"

        headers = {
            key.lower(): value
            for key, value in request.headers.items()
        }

        request.headers = headers

        def respond(status: int, message: str) -> Response:
            response = Response(
                status,
                {
                    "request_id": request_id,
                    "status": GatewayStatus.SUCCESS.value
                    if status < 400 else "ERROR",
                    "message": message
                },
                {"X-Request-ID": request_id}
            )

            self.audit.record(
                request_id,
                client_id,
                request,
                status
            )

            return response

        try:

            request.validate()

            # Step 1: Resolve route.
            result = self.router.resolve(
                request.method,
                request.path
            )

            if result is None:
                return respond(404, "Route not found")

            route, parameters = result

            # Step 2: Authenticate.
            client = self.authenticator.authenticate(
                request.headers
            )

            client_id = client.client_id

            # Step 3: Authorize.
            self.authenticator.authorize(
                client,
                route.required_scope
            )

            # Step 4: Apply rate limiting.
            allowed, remaining = self.limiter.allow(
                client.client_id,
                route
            )

            if not allowed:

                response = respond(
                    429,
                    "Rate limit exceeded"
                )

                response.headers.update({
                    "Retry-After": str(
                        max(1, (1 + route.rate_limit - 1)
                            // route.rate_limit)
                    ),
                    "X-RateLimit-Remaining": "0"
                })

                return response

            # Step 5: Forward to upstream service.
            response = self.upstreams.forward(
                route.upstream_service,
                request,
                parameters
            )

            response.headers.update({
                "X-Request-ID": request_id,
                "X-RateLimit-Remaining": str(remaining)
            })

            self.audit.record(
                request_id,
                client_id,
                request,
                response.status_code
            )

            return response

        except ValueError as exc:
            return respond(400, str(exc))

        except AuthenticationError:
            return respond(401, "Authentication failed")

        except AuthorizationError:
            return respond(403, "Insufficient permissions")

        except RuntimeError:
            logger.exception("Upstream service failure")
            return respond(502, "Bad gateway")

        except Exception:
            logger.exception("Unexpected gateway failure")
            return respond(500, "Internal gateway error")


# ---------------------------------------------------------
# Example upstream services
# ---------------------------------------------------------

def user_service(
    request: Request,
    parameters: dict[str, str]
) -> Response:

    user_id = parameters["user_id"]

    if request.method == "GET":

        return Response(
            200,
            {
                "service": "user-service",
                "user_id": user_id,
                "name": "Example User"
            }
        )

    if request.method == "DELETE":

        return Response(
            200,
            {
                "message": f"User {user_id} deleted"
            }
        )

    return Response(405, {"error": "Method not supported"})


def order_service(
    request: Request,
    parameters: dict[str, str]
) -> Response:

    if request.method == "POST":

        order_id = str(uuid.uuid4())

        return Response(
            201,
            {
                "service": "order-service",
                "order_id": order_id,
                "amount": request.body.get("amount", 0),
                "status": "CREATED"
            }
        )

    return Response(405, {"error": "Method not supported"})


# ---------------------------------------------------------
# Gateway configuration
# ---------------------------------------------------------

def build_gateway() -> APIGateway:

    clients = [
        APIClient(
            "client-001",
            "demo-user-token",
            frozenset({"users:read", "orders:create"})
        ),
        APIClient(
            "client-002",
            "demo-admin-token",
            frozenset({
                "users:read",
                "users:delete",
                "orders:create"
            })
        )
    ]

    authenticator = Authenticator(clients)

    router = Router()

    router.register(
        Route(
            "user-get",
            "GET",
            "/api/v1/users/{user_id}",
            "users",
            "users:read",
            3,
            5
        )
    )

    router.register(
        Route(
            "user-delete",
            "DELETE",
            "/api/v1/users/{user_id}",
            "users",
            "users:delete",
            2,
            3
        )
    )

    router.register(
        Route(
            "order-create",
            "POST",
            "/api/v1/orders",
            "orders",
            "orders:create",
            5,
            10
        )
    )

    upstreams = UpstreamServiceRegistry()

    upstreams.register("users", user_service)
    upstreams.register("orders", order_service)

    return APIGateway(
        authenticator,
        router,
        TokenBucketRateLimiter(),
        upstreams
    )


# ---------------------------------------------------------
# Demonstration and tests
# ---------------------------------------------------------

def run_tests() -> None:

    gateway = build_gateway()

    def send(
        method: str,
        path: str,
        token: str | None = None,
        body: dict[str, Any] | None = None
    ) -> Response:

        headers = {}

        if token:
            headers["Authorization"] = f"Bearer {token}"

        return gateway.handle(
            Request(
                method,
                path,
                headers,
                body or {}
            )
        )

    # Successful routing and authentication.
    response = send(
        "GET",
        "/api/v1/users/101",
        "demo-user-token"
    )

    assert response.status_code == 200
    assert response.body["user_id"] == "101"

    # Authentication failure.
    assert send(
        "GET",
        "/api/v1/users/101"
    ).status_code == 401

    # Authorization failure.
    assert send(
        "DELETE",
        "/api/v1/users/101",
        "demo-user-token"
    ).status_code == 403

    # Successful authorization.
    assert send(
        "DELETE",
        "/api/v1/users/101",
        "demo-admin-token"
    ).status_code == 200

    # Route not found.
    assert send(
        "GET",
        "/api/v1/unknown",
        "demo-user-token"
    ).status_code == 404

    # Request validation.
    assert send(
        "INVALID",
        "/api/v1/users/101",
        "demo-user-token"
    ).status_code == 400

    # Order creation.
    response = send(
        "POST",
        "/api/v1/orders",
        "demo-user-token",
        {"amount": 2500}
    )

    assert response.status_code == 201

    # Isolated limiter test.
    limiter = TokenBucketRateLimiter()

    test_route = Route(
        "test",
        "GET",
        "/test",
        "test",
        "test:read",
        rate_limit=1,
        burst_capacity=2
    )

    assert limiter.allow("client", test_route, 100)[0]
    assert limiter.allow("client", test_route, 100)[0]
    assert not limiter.allow("client", test_route, 100)[0]

    # Refill after one second.
    assert limiter.allow("client", test_route, 101)[0]

    # Disabled client.
    disabled_gateway = APIGateway(
        Authenticator([
            APIClient(
                "disabled",
                "disabled-token",
                frozenset({"users:read"}),
                enabled=False
            )
        ]),
        gateway.router,
        TokenBucketRateLimiter(),
        gateway.upstreams
    )

    assert disabled_gateway.handle(
        Request(
            "GET",
            "/api/v1/users/101",
            {"Authorization": "Bearer disabled-token"}
        )
    ).status_code == 401

    gateway.audit.export_json("gateway_audit.json")

    print("All API Gateway tests passed.")
    print("\nRequest audit:")

    for record in gateway.audit.records:
        print(
            record.method,
            record.path,
            record.status_code,
            record.client_id
        )


if __name__ == "__main__":
    run_tests()
