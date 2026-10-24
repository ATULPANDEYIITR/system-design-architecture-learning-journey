from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from typing import Iterable
import random


class Algorithm(str, Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"


@dataclass
class Backend:
    name: str
    weight: int = 1
    healthy: bool = True
    active_connections: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    total_requests: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Backend name cannot be empty")
        if self.weight <= 0:
            raise ValueError("Backend weight must be positive")

    def start_request(self) -> None:
        if not self.healthy:
            raise RuntimeError(f"{self.name} is unhealthy")
        self.active_connections += 1
        self.total_requests += 1

    def finish_request(self, success: bool = True) -> None:
        if self.active_connections <= 0:
            raise RuntimeError(
                f"Cannot finish a request on {self.name}: no active connection"
            )
        self.active_connections -= 1
        if success:
            self.completed_requests += 1
        else:
            self.failed_requests += 1


@dataclass
class Request:
    request_id: int
    duration: int = 1

    def __post_init__(self) -> None:
        if self.request_id <= 0:
            raise ValueError("Request ID must be positive")
        if self.duration <= 0:
            raise ValueError("Request duration must be positive")


class LoadBalancer:
    """
    Educational load-balancer model.

    Round robin:
        Each healthy backend receives the next request in sequence.

    Weighted round robin:
        Backends with larger weights receive proportionally more traffic.

    Least connections:
        The healthy backend with the fewest active connections is selected.
        Weight is used as a tie-breaker, favoring higher-capacity servers.
    """

    def __init__(
        self,
        backends: Iterable[Backend],
        algorithm: Algorithm,
    ) -> None:
        self.backends = list(backends)
        if not self.backends:
            raise ValueError("At least one backend is required")

        names = [backend.name for backend in self.backends]
        if len(names) != len(set(names)):
            raise ValueError("Backend names must be unique")

        self.algorithm = algorithm
        self._round_robin_index = 0
        self._weighted_sequence: list[Backend] = []
        self._weighted_index = 0

        self._rebuild_weighted_sequence()

    def _healthy_backends(self) -> list[Backend]:
        return [backend for backend in self.backends if backend.healthy]

    def _rebuild_weighted_sequence(self) -> None:
        self._weighted_sequence = [
            backend
            for backend in self.backends
            for _ in range(backend.weight)
        ]
        self._weighted_index = 0

    def set_health(self, backend_name: str, healthy: bool) -> None:
        backend = self._find_backend(backend_name)
        backend.healthy = healthy

        if not healthy and backend.active_connections:
            # Existing connections are allowed to drain.
            pass

        self._rebuild_weighted_sequence()

    def _find_backend(self, backend_name: str) -> Backend:
        for backend in self.backends:
            if backend.name == backend_name:
                return backend
        raise KeyError(f"Unknown backend: {backend_name}")

    def select_backend(self) -> Backend:
        healthy = self._healthy_backends()
        if not healthy:
            raise RuntimeError("No healthy backends are available")

        if self.algorithm == Algorithm.ROUND_ROBIN:
            return self._select_round_robin(healthy)

        if self.algorithm == Algorithm.WEIGHTED_ROUND_ROBIN:
            return self._select_weighted_round_robin(healthy)

        if self.algorithm == Algorithm.LEAST_CONNECTIONS:
            return min(
                healthy,
                key=lambda backend: (
                    backend.active_connections,
                    -backend.weight,
                    backend.name,
                ),
            )

        raise ValueError(f"Unsupported algorithm: {self.algorithm}")

    def _select_round_robin(self, healthy: list[Backend]) -> Backend:
        backend = healthy[self._round_robin_index % len(healthy)]
        self._round_robin_index = (self._round_robin_index + 1) % len(healthy)
        return backend

    def _select_weighted_round_robin(self, healthy: list[Backend]) -> Backend:
        healthy_names = {backend.name for backend in healthy}
        sequence = [
            backend
            for backend in self._weighted_sequence
            if backend.name in healthy_names
        ]

        if not sequence:
            raise RuntimeError("No healthy backend exists in weighted schedule")

        backend = sequence[self._weighted_index % len(sequence)]
        self._weighted_index = (self._weighted_index + 1) % len(sequence)
        return backend

    def dispatch(self, request: Request) -> Backend:
        backend = self.select_backend()
        backend.start_request()
        return backend

    def complete(self, backend_name: str, success: bool = True) -> None:
        self._find_backend(backend_name).finish_request(success)

    def statistics(self) -> dict[str, dict[str, int | bool]]:
        return {
            backend.name: {
                "healthy": backend.healthy,
                "weight": backend.weight,
                "active_connections": backend.active_connections,
                "total_requests": backend.total_requests,
                "completed_requests": backend.completed_requests,
                "failed_requests": backend.failed_requests,
            }
            for backend in self.backends
        }


def simulate_algorithm(
    algorithm: Algorithm,
    weights: tuple[int, int, int] = (1, 2, 3),
    requests: int = 60,
) -> dict[str, int]:
    backends = [
        Backend("server-a", weights[0]),
        Backend("server-b", weights[1]),
        Backend("server-c", weights[2]),
    ]
    balancer = LoadBalancer(backends, algorithm)

    for request_id in range(1, requests + 1):
        request = Request(request_id)
        backend = balancer.dispatch(request)

        # The simulation completes requests immediately for
        # round-robin and weighted distribution measurements.
        balancer.complete(backend.name)

    return {
        backend.name: backend.total_requests
        for backend in backends
    }


def simulate_least_connections() -> dict[str, dict[str, int | bool]]:
    backends = [
        Backend("api-1", weight=1),
        Backend("api-2", weight=2),
        Backend("api-3", weight=3),
    ]
    balancer = LoadBalancer(backends, Algorithm.LEAST_CONNECTIONS)

    active: list[str] = []

    for request_id in range(1, 10):
        backend = balancer.dispatch(Request(request_id, duration=2))
        active.append(backend.name)

        # Every third request completes the oldest active request.
        if request_id % 3 == 0:
            balancer.complete(active.pop(0))

    return balancer.statistics()


def demonstrate_failure_handling() -> None:
    backends = [
        Backend("primary", weight=2),
        Backend("secondary", weight=1),
    ]
    balancer = LoadBalancer(backends, Algorithm.WEIGHTED_ROUND_ROBIN)

    for request_id in range(1, 7):
        backend = balancer.dispatch(Request(request_id))
        balancer.complete(backend.name)

    balancer.set_health("primary", False)

    for request_id in range(7, 10):
        backend = balancer.dispatch(Request(request_id))
        balancer.complete(backend.name)

    print("After primary failure:")
    for name, stats in balancer.statistics().items():
        print(f"  {name}: {stats}")


def main() -> None:
    print("Round robin distribution:")
    print(simulate_algorithm(Algorithm.ROUND_ROBIN))

    print("\nWeighted round robin distribution:")
    print(simulate_algorithm(Algorithm.WEIGHTED_ROUND_ROBIN))

    print("\nLeast-connections simulation:")
    for name, stats in simulate_least_connections().items():
        print(f"  {name}: {stats}")

    print("\nFailure handling:")
    demonstrate_failure_handling()

    # Basic executable correctness checks.
    rr = simulate_algorithm(Algorithm.ROUND_ROBIN)
    assert rr == {"server-a": 20, "server-b": 20, "server-c": 20}

    weighted = simulate_algorithm(Algorithm.WEIGHTED_ROUND_ROBIN)
    assert weighted == {"server-a": 10, "server-b": 20, "server-c": 30}


if __name__ == "__main__":
    main()
