#!/usr/bin/env python3
"""
Load balancer traffic distribution and health-check simulation.

The model represents a small production-style service pool. It supports:
- Round-robin, weighted round-robin, and least-connections routing.
- Active health checks with consecutive failure/success thresholds.
- Passive failure reporting.
- Connection lifecycle tracking.
- Automatic removal and recovery of unhealthy backends.
- Base request validation and routing diagnostics.
- A deterministic simulation suitable for learning and testing.

The implementation uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
import time
from typing import Iterable


class BackendState(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class DistributionStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"


@dataclass
class HealthCheckResult:
    backend_id: str
    success: bool
    latency_ms: float
    detail: str


@dataclass
class Backend:
    backend_id: str
    host: str
    port: int
    weight: int = 1
    max_connections: int = 100
    simulated_health: bool = True
    state: BackendState = BackendState.HEALTHY
    active_connections: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    health_checks: int = 0
    health_check_failures: int = 0
    response_latency_ms: float = 25.0

    def __post_init__(self) -> None:
        if not self.backend_id.strip():
            raise ValueError("backend_id cannot be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.weight <= 0:
            raise ValueError("weight must be positive")
        if self.max_connections <= 0:
            raise ValueError("max_connections must be positive")

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def capacity_available(self) -> bool:
        return self.active_connections < self.max_connections

    def can_receive(self) -> bool:
        return self.state is BackendState.HEALTHY and self.capacity_available

    def open_connection(self) -> None:
        if not self.can_receive():
            raise RuntimeError(
                f"backend {self.backend_id} cannot accept another connection"
            )
        self.active_connections += 1
        self.total_requests += 1

    def close_connection(self) -> None:
        if self.active_connections <= 0:
            raise RuntimeError(
                f"backend {self.backend_id} has no active connection to close"
            )
        self.active_connections -= 1


@dataclass
class HealthChecker:
    failure_threshold: int = 2
    recovery_threshold: int = 2
    timeout_ms: float = 1000.0

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.recovery_threshold <= 0:
            raise ValueError("recovery_threshold must be positive")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")

    def check(self, backend: Backend) -> HealthCheckResult:
        # A real implementation would perform an HTTP/TCP probe. The simulation
        # uses simulated_health so the result remains deterministic.
        backend.health_checks += 1

        if backend.simulated_health:
            backend.consecutive_failures = 0
            backend.consecutive_successes += 1

            if (
                backend.state is BackendState.UNHEALTHY
                and backend.consecutive_successes >= self.recovery_threshold
            ):
                backend.state = BackendState.HEALTHY

            return HealthCheckResult(
                backend.backend_id,
                True,
                backend.response_latency_ms,
                "health probe succeeded",
            )

        backend.consecutive_successes = 0
        backend.consecutive_failures += 1
        backend.health_check_failures += 1

        if backend.consecutive_failures >= self.failure_threshold:
            backend.state = BackendState.UNHEALTHY

        return HealthCheckResult(
            backend.backend_id,
            False,
            self.timeout_ms,
            "health probe failed",
        )


class LoadBalancer:
    def __init__(
        self,
        backends: Iterable[Backend],
        strategy: DistributionStrategy = DistributionStrategy.ROUND_ROBIN,
        health_checker: HealthChecker | None = None,
    ) -> None:
        self.backends = list(backends)
        if not self.backends:
            raise ValueError("at least one backend is required")

        self.strategy = strategy
        self.health_checker = health_checker or HealthChecker()
        self._round_robin_index = 0

        self.request_count = 0
        self.rejected_requests = 0
        self.routing_failures = 0

        self._validate_unique_backend_ids()

    def _validate_unique_backend_ids(self) -> None:
        ids = [backend.backend_id for backend in self.backends]
        if len(ids) != len(set(ids)):
            raise ValueError("backend IDs must be unique")

    def run_health_checks(self) -> list[HealthCheckResult]:
        return [self.health_checker.check(backend) for backend in self.backends]

    def _available_backends(self) -> list[Backend]:
        return [backend for backend in self.backends if backend.can_receive()]

    def _choose_round_robin(self, candidates: list[Backend]) -> Backend:
        candidate_ids = {backend.backend_id for backend in candidates}

        for offset in range(len(self.backends)):
            index = (self._round_robin_index + offset) % len(self.backends)
            backend = self.backends[index]
            if backend.backend_id in candidate_ids:
                self._round_robin_index = (index + 1) % len(self.backends)
                return backend

        raise RuntimeError("no round-robin candidate exists")

    def _choose_weighted_round_robin(self, candidates: list[Backend]) -> Backend:
        # Smooth weighted selection is unnecessary for this compact simulation;
        # expanding the candidate set gives deterministic proportional routing.
        weighted: list[Backend] = []
        for backend in candidates:
            weighted.extend([backend] * backend.weight)

        if not weighted:
            raise RuntimeError("no weighted candidate exists")

        backend = weighted[self.request_count % len(weighted)]
        return backend

    @staticmethod
    def _choose_least_connections(candidates: list[Backend]) -> Backend:
        return min(
            candidates,
            key=lambda backend: (
                backend.active_connections,
                -backend.weight,
                backend.backend_id,
            ),
        )

    def choose_backend(self) -> Backend:
        candidates = self._available_backends()

        if not candidates:
            self.routing_failures += 1
            raise RuntimeError("no healthy backend with available capacity")

        if self.strategy is DistributionStrategy.ROUND_ROBIN:
            return self._choose_round_robin(candidates)

        if self.strategy is DistributionStrategy.WEIGHTED_ROUND_ROBIN:
            return self._choose_weighted_round_robin(candidates)

        return self._choose_least_connections(candidates)

    def route_request(self, request_id: str) -> str:
        request_id = request_id.strip()
        if not request_id:
            raise ValueError("request_id cannot be empty")

        self.request_count += 1

        try:
            backend = self.choose_backend()
            backend.open_connection()
            return backend.backend_id
        except RuntimeError:
            self.rejected_requests += 1
            raise

    def complete_request(self, backend_id: str) -> None:
        backend = self.get_backend(backend_id)
        backend.close_connection()

    def record_passive_failure(self, backend_id: str) -> None:
        backend = self.get_backend(backend_id)
        backend.failed_requests += 1
        backend.consecutive_failures += 1
        backend.consecutive_successes = 0

        if backend.consecutive_failures >= self.health_checker.failure_threshold:
            backend.state = BackendState.UNHEALTHY

    def get_backend(self, backend_id: str) -> Backend:
        for backend in self.backends:
            if backend.backend_id == backend_id:
                return backend
        raise KeyError(f"unknown backend: {backend_id}")

    def snapshot(self) -> list[dict[str, object]]:
        return [
            {
                "id": backend.backend_id,
                "address": backend.address,
                "state": backend.state.value,
                "weight": backend.weight,
                "connections": backend.active_connections,
                "requests": backend.total_requests,
                "health_failures": backend.health_check_failures,
            }
            for backend in self.backends
        ]


def print_snapshot(load_balancer: LoadBalancer, title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))

    for row in load_balancer.snapshot():
        print(
            f"{row['id']:>8}  "
            f"{row['address']:<22}  "
            f"state={row['state']:<9}  "
            f"weight={row['weight']}  "
            f"connections={row['connections']}  "
            f"requests={row['requests']}  "
            f"health_failures={row['health_failures']}"
        )


def demonstrate_round_robin() -> None:
    backends = [
        Backend("app-01", "10.0.0.11", 8080),
        Backend("app-02", "10.0.0.12", 8080),
        Backend("app-03", "10.0.0.13", 8080),
    ]

    lb = LoadBalancer(backends, DistributionStrategy.ROUND_ROBIN)

    print("Round-robin routing:")
    for request_number in range(1, 7):
        backend_id = lb.route_request(f"rr-{request_number}")
        print(f"request rr-{request_number} -> {backend_id}")
        lb.complete_request(backend_id)

    print_snapshot(lb, "Round-robin state")


def demonstrate_health_failover() -> None:
    backends = [
        Backend("primary", "10.0.1.11", 8080),
        Backend("secondary", "10.0.1.12", 8080),
        Backend("tertiary", "10.0.1.13", 8080),
    ]

    lb = LoadBalancer(
        backends,
        DistributionStrategy.ROUND_ROBIN,
        HealthChecker(failure_threshold=2, recovery_threshold=2),
    )

    print("\nHealth-check failover:")

    backends[0].simulated_health = False

    for attempt in range(1, 3):
        results = lb.run_health_checks()
        primary_result = next(
            result for result in results if result.backend_id == "primary"
        )
        print(
            f"probe {attempt}: primary success={primary_result.success}, "
            f"state={backends[0].state.value}"
        )

    for request_number in range(1, 5):
        backend_id = lb.route_request(f"failover-{request_number}")
        print(f"request failover-{request_number} -> {backend_id}")
        lb.complete_request(backend_id)

    print_snapshot(lb, "Failover state")

    # Recovery requires two consecutive successful probes.
    backends[0].simulated_health = True

    for attempt in range(1, 3):
        results = lb.run_health_checks()
        primary_result = next(
            result for result in results if result.backend_id == "primary"
        )
        print(
            f"recovery probe {attempt}: primary success={primary_result.success}, "
            f"state={backends[0].state.value}"
        )

    print_snapshot(lb, "Recovered state")


def demonstrate_weighted_routing() -> None:
    backends = [
        Backend("small", "10.0.2.11", 8080, weight=1),
        Backend("large", "10.0.2.12", 8080, weight=3),
    ]

    lb = LoadBalancer(backends, DistributionStrategy.WEIGHTED_ROUND_ROBIN)
    counts = {backend.backend_id: 0 for backend in backends}

    for request_number in range(8):
        backend_id = lb.route_request(f"weighted-{request_number}")
        counts[backend_id] += 1
        lb.complete_request(backend_id)

    print("\nWeighted distribution:")
    for backend_id, count in counts.items():
        print(f"{backend_id}: {count} requests")


def demonstrate_least_connections() -> None:
    backends = [
        Backend("lc-01", "10.0.3.11", 8080),
        Backend("lc-02", "10.0.3.12", 8080),
        Backend("lc-03", "10.0.3.13", 8080),
    ]

    lb = LoadBalancer(backends, DistributionStrategy.LEAST_CONNECTIONS)

    # Existing long-lived connections make least-connections choose another node.
    backends[0].open_connection()
    backends[0].open_connection()
    backends[1].open_connection()

    print("\nLeast-connections routing:")
    for request_number in range(3):
        backend_id = lb.route_request(f"least-{request_number}")
        print(f"request least-{request_number} -> {backend_id}")

    # Clean up every connection opened by the demonstration.
    for backend in backends:
        while backend.active_connections:
            backend.close_connection()

    print_snapshot(lb, "Least-connections state")


def demonstrate_capacity_failure() -> None:
    backend = Backend(
        "limited",
        "10.0.4.11",
        8080,
        max_connections=1,
    )

    lb = LoadBalancer([backend])

    first = lb.route_request("capacity-1")
    print(f"\nFirst request -> {first}")

    try:
        lb.route_request("capacity-2")
    except RuntimeError as exc:
        print(f"Expected capacity failure: {exc}")

    lb.complete_request(first)


def main() -> None:
    random.seed(7)
    demonstrate_round_robin()
    demonstrate_health_failover()
    demonstrate_weighted_routing()
    demonstrate_least_connections()
    demonstrate_capacity_failure()


if __name__ == "__main__":
    main()
