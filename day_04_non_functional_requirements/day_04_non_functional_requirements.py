"""
Non-Functional Requirements: Scalability, Availability, Reliability, Latency, Security

This standalone study script teaches the major non-functional requirements that
shape production systems. It progresses from fundamental terminology to
quantitative reasoning, implementation patterns, simulations, trade-offs,
failure handling, observability, and production-oriented design.

The examples use only Python's standard library.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import random
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
from typing import Callable, Dict, Iterable, List, Optional, Tuple


# =============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# =============================================================================

def explain_basic_terminology() -> None:
    """
    Non-functional requirements describe qualities and operational constraints
    of a system rather than primarily describing business functionality.

    Functional requirement:
        "The system shall allow a customer to place an order."

    Non-functional requirement:
        "99.95% of order requests shall complete successfully each month,
        with p95 latency below 300 ms."

    The five dimensions demonstrated in this script are related but distinct:

    Scalability:
        How well capacity grows as workload or resources increase.

    Availability:
        The proportion of time a service is accessible and able to respond.

    Reliability:
        The probability that a system performs correctly and consistently
        for a specified period under specified conditions.

    Latency:
        The elapsed time between a request and its corresponding response.

    Security:
        Protection of confidentiality, integrity, availability, authenticity,
        authorization, and accountability.
    """

    requirements = {
        "scalability": "Ability to handle increasing workload by adding or improving capacity.",
        "availability": "Ability to remain accessible and operational when requested.",
        "reliability": "Ability to perform correctly and consistently over time.",
        "latency": "Time taken to complete an operation from the relevant measurement points.",
        "security": "Protection against unauthorized access, misuse, alteration, disclosure, and disruption.",
    }

    for name, definition in requirements.items():
        print(f"{name.title():15} -> {definition}")


# =============================================================================
# 2. MEASURABLE NON-FUNCTIONAL REQUIREMENTS
# =============================================================================

@dataclass
class Requirement:
    name: str
    metric: str
    target: str
    measurement_window: str
    scope: str


def create_measurable_requirements() -> List[Requirement]:
    """
    A useful NFR should be measurable.

    Weak:
        "The API should be fast."

    Strong:
        "For 99% of successful API requests, p99 latency shall be <= 500 ms
        during normal production load."

    Requirements should also identify scope and measurement period.
    """
    return [
        Requirement(
            name="Availability",
            metric="Successful service availability",
            target="99.95%",
            measurement_window="monthly",
            scope="public API",
        ),
        Requirement(
            name="Latency",
            metric="p95 response latency",
            target="<= 300 ms",
            measurement_window="5-minute rolling window",
            scope="read API",
        ),
        Requirement(
            name="Scalability",
            metric="sustainable throughput",
            target="10,000 requests/second",
            measurement_window="15 minutes",
            scope="API cluster",
        ),
        Requirement(
            name="Reliability",
            metric="successful transaction completion",
            target=">= 99.99%",
            measurement_window="monthly",
            scope="payment transactions",
        ),
        Requirement(
            name="Security",
            metric="unauthorized access",
            target="0 confirmed unauthorized successful accesses",
            measurement_window="continuous",
            scope="protected resources",
        ),
    ]


def print_requirements(requirements: Iterable[Requirement]) -> None:
    for requirement in requirements:
        print(
            f"{requirement.name}: "
            f"{requirement.metric} | "
            f"Target={requirement.target} | "
            f"Window={requirement.measurement_window} | "
            f"Scope={requirement.scope}"
        )


# =============================================================================
# 3. CAPACITY, THROUGHPUT, CONCURRENCY, AND UTILIZATION
# =============================================================================

@dataclass
class CapacityModel:
    worker_count: int
    requests_per_worker_per_second: float

    @property
    def theoretical_capacity(self) -> float:
        return self.worker_count * self.requests_per_worker_per_second

    def utilization(self, offered_load: float) -> float:
        if self.theoretical_capacity <= 0:
            raise ValueError("Capacity must be positive.")
        return offered_load / self.theoretical_capacity


def demonstrate_capacity() -> None:
    """
    Throughput is work completed per unit time.

    Concurrency is the number of operations in progress at a point in time.

    Capacity is the maximum sustainable workload under specified conditions.

    Utilization = offered load / capacity

    A system running at 100% utilization has little room for bursts.
    In real systems, latency frequently increases sharply as utilization
    approaches saturation.
    """
    model = CapacityModel(worker_count=8, requests_per_worker_per_second=250)

    for offered_load in [500, 1000, 1500, 1800, 1950]:
        utilization = model.utilization(offered_load)
        print(
            f"Load={offered_load:4} req/s | "
            f"Capacity={model.theoretical_capacity:4.0f} req/s | "
            f"Utilization={utilization:.1%}"
        )


# =============================================================================
# 4. LITTLE'S LAW
# =============================================================================

def littles_law(
    throughput_per_second: float,
    average_latency_seconds: float,
) -> float:
    """
    Little's Law:

        L = lambda * W

    L = average number of items in the system
    lambda = throughput
    W = average time spent in the system

    Example:
        100 requests/s * 0.2 seconds = 20 requests concurrently in flight.

    The relationship is useful for capacity planning, queue analysis,
    and understanding why latency and concurrency cannot be treated
    independently.
    """
    if throughput_per_second < 0 or average_latency_seconds < 0:
        raise ValueError("Throughput and latency cannot be negative.")

    return throughput_per_second * average_latency_seconds


def demonstrate_littles_law() -> None:
    throughput = 100
    latency = 0.2
    concurrency = littles_law(throughput, latency)

    print(
        f"Throughput={throughput} req/s, "
        f"Average latency={latency:.3f}s, "
        f"Estimated concurrency={concurrency:.1f}"
    )


# =============================================================================
# 5. SCALABILITY
# =============================================================================

class ScalingStrategy(Enum):
    VERTICAL = "vertical scaling"
    HORIZONTAL = "horizontal scaling"
    ELASTIC = "elastic scaling"


@dataclass
class ServiceCluster:
    instances: int
    capacity_per_instance: float

    @property
    def total_capacity(self) -> float:
        return self.instances * self.capacity_per_instance

    def add_instances(self, count: int) -> None:
        if count < 0:
            raise ValueError("Cannot add a negative number of instances.")
        self.instances += count


def demonstrate_scalability() -> None:
    """
    Vertical scaling:
        Increase resources of one machine.

    Horizontal scaling:
        Add more machines/instances.

    Elastic scaling:
        Dynamically add or remove capacity according to workload.

    Horizontal scaling normally requires the application to support:
        - stateless request processing
        - distributed state
        - load balancing
        - shared or partitioned data stores
        - idempotent operations
        - coordination where required
    """
    cluster = ServiceCluster(instances=2, capacity_per_instance=500)

    print("Initial capacity:", cluster.total_capacity)
    cluster.add_instances(4)
    print("After horizontal scaling:", cluster.total_capacity)

    strategies = [
        ScalingStrategy.VERTICAL,
        ScalingStrategy.HORIZONTAL,
        ScalingStrategy.ELASTIC,
    ]

    for strategy in strategies:
        print(strategy.value)


# =============================================================================
# 6. SCALE-UP VS SCALE-OUT
# =============================================================================

def compare_scaling_strategies() -> None:
    """
    Vertical scaling advantages:
        - simple architecture
        - fewer distributed-system concerns
        - potentially simpler state management

    Vertical scaling limitations:
        - physical or provider limits
        - expensive large instances
        - single-machine failure domain
        - maintenance can affect the whole service

    Horizontal scaling advantages:
        - larger aggregate capacity
        - redundancy
        - gradual capacity increases
        - suitable for cloud-native workloads

    Horizontal scaling challenges:
        - distributed state
        - network failures
        - coordination
        - load balancing
        - consistency issues
        - operational complexity
    """
    vertical = {
        "simplicity": 9,
        "maximum_scale": 5,
        "redundancy": 3,
        "distributed_complexity": 2,
    }

    horizontal = {
        "simplicity": 5,
        "maximum_scale": 9,
        "redundancy": 9,
        "distributed_complexity": 9,
    }

    print("Vertical scaling characteristics:", vertical)
    print("Horizontal scaling characteristics:", horizontal)


# =============================================================================
# 7. LOAD BALANCING
# =============================================================================

@dataclass
class Backend:
    name: str
    capacity: int
    active_requests: int = 0
    healthy: bool = True


class RoundRobinLoadBalancer:
    def __init__(self, backends: List[Backend]):
        if not backends:
            raise ValueError("At least one backend is required.")
        self.backends = backends
        self.index = 0

    def choose(self) -> Backend:
        healthy = [backend for backend in self.backends if backend.healthy]
        if not healthy:
            raise RuntimeError("No healthy backends available.")

        backend = healthy[self.index % len(healthy)]
        self.index += 1
        return backend


class LeastConnectionsLoadBalancer:
    def __init__(self, backends: List[Backend]):
        if not backends:
            raise ValueError("At least one backend is required.")
        self.backends = backends

    def choose(self) -> Backend:
        healthy = [backend for backend in self.backends if backend.healthy]
        if not healthy:
            raise RuntimeError("No healthy backends available.")

        return min(healthy, key=lambda backend: backend.active_requests)


def demonstrate_load_balancing() -> None:
    backends = [
        Backend("server-a", capacity=100),
        Backend("server-b", capacity=100),
        Backend("server-c", capacity=100),
    ]

    round_robin = RoundRobinLoadBalancer(backends)

    print("Round-robin routing:")
    for _ in range(6):
        print(round_robin.choose().name)

    backends[0].active_requests = 50
    backends[1].active_requests = 10
    backends[2].active_requests = 25

    least_connections = LeastConnectionsLoadBalancer(backends)
    print("Least-connections selection:", least_connections.choose().name)


# =============================================================================
# 8. STATELESSNESS
# =============================================================================

class StatelessRequestProcessor:
    """
    A stateless processor does not depend on local memory from a previous
    request to correctly process a later request.

    State may instead live in:
        - a database
        - a distributed cache
        - an object store
        - a message broker
        - a client-side token
    """

    def process(self, user_id: str, request: Dict[str, str]) -> Dict[str, str]:
        if not user_id:
            raise ValueError("user_id is required.")

        return {
            "user_id": user_id,
            "status": "processed",
            "operation": request.get("operation", "unknown"),
        }


def demonstrate_statelessness() -> None:
    processor = StatelessRequestProcessor()
    response = processor.process(
        user_id="user-123",
        request={"operation": "read_profile"},
    )
    print(response)


# =============================================================================
# 9. AVAILABILITY
# =============================================================================

def availability_percentage(
    total_seconds: float,
    downtime_seconds: float,
) -> float:
    """
    Availability:

        Availability = (Total Time - Downtime) / Total Time * 100

    This simple calculation does not by itself define what counts as downtime.
    Production availability definitions must specify:
        - monitored endpoints
        - excluded maintenance
        - dependency failures
        - partial outages
        - measurement location
        - time aggregation
    """
    if total_seconds <= 0:
        raise ValueError("Total time must be positive.")
    if downtime_seconds < 0:
        raise ValueError("Downtime cannot be negative.")
    if downtime_seconds > total_seconds:
        raise ValueError("Downtime cannot exceed total time.")

    return (total_seconds - downtime_seconds) / total_seconds * 100


def demonstrate_availability() -> None:
    month_seconds = 30 * 24 * 60 * 60

    for downtime_minutes in [43.2, 21.6, 4.32, 0.432]:
        availability = availability_percentage(
            month_seconds,
            downtime_minutes * 60,
        )
        print(
            f"Downtime={downtime_minutes:8.3f} minutes -> "
            f"Availability={availability:.5f}%"
        )


# =============================================================================
# 10. AVAILABILITY "NINES"
# =============================================================================

def allowed_downtime(
    total_seconds: float,
    availability_target: float,
) -> float:
    """
    Convert an availability percentage into an approximate downtime budget.

    Example:
        99.9% availability means 0.1% of the period may be unavailable.

    Availability targets:
        99%
        99.9%
        99.99%
        99.999%

    Each additional nine dramatically reduces the permitted downtime.
    """
    if not 0 <= availability_target <= 100:
        raise ValueError("Availability target must be between 0 and 100.")

    unavailable_fraction = 1 - availability_target / 100
    return total_seconds * unavailable_fraction


def demonstrate_nines() -> None:
    periods = {
        "day": 24 * 60 * 60,
        "month": 30 * 24 * 60 * 60,
        "year": 365 * 24 * 60 * 60,
    }

    targets = [99, 99.9, 99.99, 99.999]

    for target in targets:
        print(f"\nAvailability target: {target}%")
        for name, seconds in periods.items():
            downtime = allowed_downtime(seconds, target)
            print(f"  {name:5}: {downtime / 60:.3f} minutes")


# =============================================================================
# 11. HIGH AVAILABILITY ARCHITECTURE
# =============================================================================

@dataclass
class Replica:
    name: str
    healthy: bool = True


class FailoverService:
    """
    A simplified active/passive availability design.

    Real systems may use:
        - active/active replicas
        - active/passive replicas
        - health checks
        - leader election
        - replicated databases
        - multiple availability zones
        - multiple regions
    """

    def __init__(self, replicas: List[Replica]):
        if not replicas:
            raise ValueError("At least one replica is required.")
        self.replicas = replicas

    def select_healthy_replica(self) -> Replica:
        for replica in self.replicas:
            if replica.healthy:
                return replica

        raise RuntimeError("Service unavailable: all replicas are unhealthy.")


def demonstrate_failover() -> None:
    replicas = [
        Replica("primary"),
        Replica("secondary"),
    ]

    service = FailoverService(replicas)
    print("Selected:", service.select_healthy_replica().name)

    replicas[0].healthy = False
    print("After primary failure:", service.select_healthy_replica().name)

    replicas[1].healthy = False

    try:
        service.select_healthy_replica()
    except RuntimeError as error:
        print("Expected failure:", error)


# =============================================================================
# 12. RELIABILITY
# =============================================================================

@dataclass
class OperationResult:
    success: bool
    duration_seconds: float
    error: Optional[str] = None


def reliability_rate(results: Iterable[OperationResult]) -> float:
    """
    Reliability can be measured as successful operations / total operations
    for an explicitly defined workload and measurement period.

    Reliability is not identical to availability.

    A service can be available but unreliable:
        It responds to every request but frequently returns incorrect results.

    A service can be reliable but temporarily unavailable:
        It performs every request correctly whenever reachable but experiences
        a prolonged infrastructure outage.
    """
    results = list(results)
    if not results:
        raise ValueError("At least one operation result is required.")

    successful = sum(result.success for result in results)
    return successful / len(results)


def demonstrate_reliability() -> None:
    results = [
        OperationResult(True, 0.1),
        OperationResult(True, 0.2),
        OperationResult(False, 0.3, "database timeout"),
        OperationResult(True, 0.15),
        OperationResult(True, 0.12),
    ]

    print(f"Reliability: {reliability_rate(results):.2%}")


# =============================================================================
# 13. MTBF, MTTR, MTTD, MTTA
# =============================================================================

def availability_from_mtbf_mttr(
    mean_time_between_failures: float,
    mean_time_to_repair: float,
) -> float:
    """
    A simplified steady-state relationship:

        Availability ≈ MTBF / (MTBF + MTTR)

    MTBF:
        Mean Time Between Failures.

    MTTR:
        Mean Time To Repair or Restore.

    MTTD:
        Mean Time To Detect.

    MTTA:
        Mean Time To Acknowledge.

    Reducing MTTR can improve availability even when the failure frequency
    remains unchanged.
    """
    if mean_time_between_failures < 0:
        raise ValueError("MTBF cannot be negative.")
    if mean_time_to_repair < 0:
        raise ValueError("MTTR cannot be negative.")

    denominator = mean_time_between_failures + mean_time_to_repair

    if denominator == 0:
        return 0.0

    return mean_time_between_failures / denominator


def demonstrate_mtbf_mttr() -> None:
    examples = [
        (1000, 10),
        (1000, 5),
        (1000, 1),
        (500, 10),
    ]

    for mtbf, mttr in examples:
        availability = availability_from_mtbf_mttr(mtbf, mttr)
        print(
            f"MTBF={mtbf:4}h MTTR={mttr:3}h -> "
            f"Approx availability={availability:.4%}"
        )


# =============================================================================
# 14. LATENCY
# =============================================================================

@dataclass
class LatencySample:
    request_id: int
    latency_ms: float


def percentile(values: List[float], p: float) -> float:
    """
    Percentiles are more informative than averages for distributed systems.

    p50:
        Median.

    p95:
        95% of observations are at or below this value.

    p99:
        99% are at or below this value.

    p99.9:
        99.9% are at or below this value.

    Tail latency matters because users experience individual requests, not
    only the average request.
    """
    if not values:
        raise ValueError("values cannot be empty.")
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100.")

    sorted_values = sorted(values)

    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (p / 100) * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)

    if lower == upper:
        return sorted_values[lower]

    fraction = rank - lower
    return (
        sorted_values[lower]
        + (sorted_values[upper] - sorted_values[lower]) * fraction
    )


def demonstrate_latency_distribution() -> None:
    latencies = [
        10, 11, 12, 13, 14, 15, 16, 17, 18, 20,
        21, 22, 23, 24, 25, 30, 35, 50, 100, 500,
    ]

    print(f"Mean: {statistics.mean(latencies):.2f} ms")
    print(f"p50 : {percentile(latencies, 50):.2f} ms")
    print(f"p95 : {percentile(latencies, 95):.2f} ms")
    print(f"p99 : {percentile(latencies, 99):.2f} ms")


# =============================================================================
# 15. LATENCY BUDGETS
# =============================================================================

@dataclass
class LatencyBudget:
    dns_ms: float
    connection_ms: float
    application_ms: float
    database_ms: float
    serialization_ms: float

    @property
    def total_ms(self) -> float:
        return (
            self.dns_ms
            + self.connection_ms
            + self.application_ms
            + self.database_ms
            + self.serialization_ms
        )


def demonstrate_latency_budget() -> None:
    budget = LatencyBudget(
        dns_ms=10,
        connection_ms=20,
        application_ms=80,
        database_ms=100,
        serialization_ms=20,
    )

    print("Total latency budget:", budget.total_ms, "ms")


# =============================================================================
# 16. TIMEOUTS
# =============================================================================

def operation_with_timeout(
    operation: Callable[[], str],
    timeout_seconds: float,
) -> str:
    """
    A timeout prevents indefinite waiting.

    Every distributed call should be considered capable of:
        - being slow
        - failing
        - returning an error
        - becoming unreachable
        - partially completing

    A production implementation should propagate deadlines through dependent
    services rather than assigning unrelated independent timeouts everywhere.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")

    result_queue: Queue = Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put(("success", operation()))
        except Exception as error:
            result_queue.put(("error", error))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    try:
        status, result = result_queue.get(timeout=timeout_seconds)
    except Empty as error:
        raise TimeoutError("Operation exceeded timeout.") from error

    if status == "error":
        raise result

    return result


def demonstrate_timeout() -> None:
    def fast_operation() -> str:
        time.sleep(0.05)
        return "completed"

    def slow_operation() -> str:
        time.sleep(0.5)
        return "completed"

    print(
        "Fast operation:",
        operation_with_timeout(fast_operation, timeout_seconds=0.2),
    )

    try:
        operation_with_timeout(slow_operation, timeout_seconds=0.1)
    except TimeoutError as error:
        print("Expected timeout:", error)


# =============================================================================
# 17. RETRIES AND EXPONENTIAL BACKOFF
# =============================================================================

def exponential_backoff_delay(
    attempt: int,
    base_delay: float = 0.1,
    maximum_delay: float = 10.0,
    jitter: float = 0.1,
) -> float:
    """
    Exponential backoff:

        delay = base * 2^attempt

    Jitter adds randomness to avoid many clients retrying simultaneously.

    Retries are dangerous when:
        - the operation is not idempotent
        - the server is overloaded
        - the failure is permanent
        - retry volume creates a retry storm

    Retry only failures that are reasonably transient and safe to retry.
    """
    if attempt < 0:
        raise ValueError("attempt cannot be negative.")
    if base_delay < 0 or maximum_delay < 0 or jitter < 0:
        raise ValueError("Delay parameters cannot be negative.")

    exponential_delay = min(
        maximum_delay,
        base_delay * (2 ** attempt),
    )

    random_jitter = random.uniform(0, jitter)
    return min(maximum_delay, exponential_delay + random_jitter)


def retry(
    operation: Callable[[], str],
    max_attempts: int,
    base_delay: float = 0.01,
    maximum_delay: float = 0.2,
) -> str:
    """
    Demonstrates bounded retries.

    The implementation deliberately avoids retrying forever.
    """
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive.")

    last_error: Optional[Exception] = None

    for attempt in range(max_attempts):
        try:
            return operation()
        except Exception as error:
            last_error = error

            if attempt == max_attempts - 1:
                break

            delay = exponential_backoff_delay(
                attempt,
                base_delay=base_delay,
                maximum_delay=maximum_delay,
                jitter=0.01,
            )

            time.sleep(delay)

    raise RuntimeError("Operation failed after retries.") from last_error


def demonstrate_retries() -> None:
    state = {"attempts": 0}

    def flaky_operation() -> str:
        state["attempts"] += 1

        if state["attempts"] < 3:
            raise ConnectionError("Temporary failure.")

        return "success"

    print("Retry result:", retry(flaky_operation, max_attempts=5))


# =============================================================================
# 18. IDEMPOTENCY
# =============================================================================

class IdempotencyStore:
    """
    An idempotency key lets a service recognize duplicate submissions.

    This is particularly important for:
        - payments
        - order creation
        - account changes
        - message processing

    A client may retry because it did not receive a response even though the
    server successfully completed the operation.
    """

    def __init__(self):
        self._results: Dict[str, object] = {}

    def execute(
        self,
        key: str,
        operation: Callable[[], object],
    ) -> object:
        if not key:
            raise ValueError("Idempotency key is required.")

        if key in self._results:
            return self._results[key]

        result = operation()
        self._results[key] = result
        return result


def demonstrate_idempotency() -> None:
    store = IdempotencyStore()
    state = {"charges": 0}

    def charge_card() -> str:
        state["charges"] += 1
        return f"charge-{state['charges']}"

    first = store.execute("payment-abc", charge_card)
    second = store.execute("payment-abc", charge_card)

    print("First result :", first)
    print("Second result:", second)
    print("Actual charges:", state["charges"])


# =============================================================================
# 19. CIRCUIT BREAKER
# =============================================================================

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit breaker states:

    CLOSED:
        Calls are allowed.

    OPEN:
        Calls fail fast without contacting the unhealthy dependency.

    HALF_OPEN:
        A limited test call is allowed to determine whether recovery occurred.

    This protects a healthy caller from repeatedly waiting on a failing
    downstream dependency.
    """

    def __init__(
        self,
        failure_threshold: int,
        recovery_timeout: float,
    ):
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive.")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive.")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at: Optional[float] = None

    def call(self, operation: Callable[[], str]) -> str:
        now = time.monotonic()

        if self.state == CircuitState.OPEN:
            if self.opened_at is None:
                raise RuntimeError("Circuit is open.")

            if now - self.opened_at < self.recovery_timeout:
                raise RuntimeError("Circuit is open; failing fast.")

            self.state = CircuitState.HALF_OPEN

        try:
            result = operation()
        except Exception:
            self.failure_count += 1

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()

            raise
        else:
            self.failure_count = 0
            self.state = CircuitState.CLOSED
            self.opened_at = None
            return result


def demonstrate_circuit_breaker() -> None:
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=0.2,
    )

    def failing_service() -> str:
        raise ConnectionError("Downstream unavailable.")

    for attempt in range(4):
        try:
            breaker.call(failing_service)
        except Exception as error:
            print(
                f"Attempt {attempt + 1}: "
                f"state={breaker.state.value}, error={error}"
            )

    time.sleep(0.25)

    def recovered_service() -> str:
        return "recovered"

    print("Recovery:", breaker.call(recovered_service))


# =============================================================================
# 20. BULKHEAD PATTERN
# =============================================================================

class Bulkhead:
    """
    A bulkhead limits concurrency for a resource or dependency.

    Without isolation, a slow dependency can consume all worker capacity and
    prevent unrelated requests from making progress.
    """

    def __init__(self, max_concurrent: int):
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive.")

        self.semaphore = threading.BoundedSemaphore(max_concurrent)

    def execute(
        self,
        operation: Callable[[], str],
    ) -> str:
        acquired = self.semaphore.acquire(timeout=1)

        if not acquired:
            raise RuntimeError("Bulkhead capacity exhausted.")

        try:
            return operation()
        finally:
            self.semaphore.release()


def demonstrate_bulkhead() -> None:
    bulkhead = Bulkhead(max_concurrent=2)

    def operation() -> str:
        time.sleep(0.02)
        return "completed"

    print(bulkhead.execute(operation))


# =============================================================================
# 21. QUEUES AND ASYNCHRONOUS PROCESSING
# =============================================================================

@dataclass
class Job:
    id: int
    payload: str


class JobQueue:
    def __init__(self):
        self._queue: Queue[Job] = Queue()

    def submit(self, job: Job) -> None:
        self._queue.put(job)

    def process_one(self) -> Optional[Job]:
        try:
            return self._queue.get_nowait()
        except Empty:
            return None


def demonstrate_async_processing() -> None:
    """
    Queues can decouple producers from consumers.

    Benefits:
        - traffic smoothing
        - workload buffering
        - asynchronous processing
        - independent scaling

    Costs:
        - increased end-to-end latency
        - eventual consistency
        - duplicate processing risks
        - queue growth
        - operational complexity

    Queue depth is itself an important operational metric.
    """
    queue = JobQueue()

    for job_id in range(5):
        queue.submit(Job(job_id, f"payload-{job_id}"))

    while True:
        job = queue.process_one()

        if job is None:
            break

        print("Processed:", job)


# =============================================================================
# 22. BACKPRESSURE
# =============================================================================

class BoundedWorkQueue:
    """
    A bounded queue prevents unlimited memory growth.

    If producers consistently outrun consumers, an unbounded queue eventually
    becomes a reliability problem.
    """

    def __init__(self, maximum_size: int):
        if maximum_size <= 0:
            raise ValueError("maximum_size must be positive.")

        self.queue = Queue(maxsize=maximum_size)

    def submit(self, item: str, timeout: float = 0.05) -> bool:
        try:
            self.queue.put(item, timeout=timeout)
            return True
        except Exception:
            return False

    def consume(self, timeout: float = 0.05) -> Optional[str]:
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return None


def demonstrate_backpressure() -> None:
    queue = BoundedWorkQueue(maximum_size=2)

    print(queue.submit("job-1"))
    print(queue.submit("job-2"))
    print(queue.submit("job-3"))

    print("Consumed:", queue.consume())
    print("Consumed:", queue.consume())


# =============================================================================
# 23. CACHING
# =============================================================================

@dataclass
class CacheEntry:
    value: object
    expires_at: float


class TTLCache:
    """
    TTL means Time To Live.

    Caching can reduce:
        - database load
        - network calls
        - computation
        - latency

    Cache risks:
        - stale data
        - invalidation complexity
        - cache stampede
        - memory pressure
        - inconsistent views
    """

    def __init__(self):
        self._entries: Dict[str, CacheEntry] = {}

    def set(self, key: str, value: object, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            raise ValueError("TTL must be positive.")

        self._entries[key] = CacheEntry(
            value=value,
            expires_at=time.monotonic() + ttl_seconds,
        )

    def get(self, key: str) -> Optional[object]:
        entry = self._entries.get(key)

        if entry is None:
            return None

        if time.monotonic() >= entry.expires_at:
            del self._entries[key]
            return None

        return entry.value


def demonstrate_cache() -> None:
    cache = TTLCache()

    cache.set("product:123", {"price": 500}, ttl_seconds=0.05)

    print("Cached value:", cache.get("product:123"))

    time.sleep(0.06)

    print("After expiration:", cache.get("product:123"))


# =============================================================================
# 24. CACHE-ASIDE PATTERN
# =============================================================================

class FakeDatabase:
    def __init__(self):
        self.read_count = 0
        self.data = {
            "user:1": {"name": "Asha", "tier": "premium"},
        }

    def get(self, key: str) -> Optional[dict]:
        self.read_count += 1
        return self.data.get(key)


def cache_aside_get(
    key: str,
    cache: TTLCache,
    database: FakeDatabase,
) -> Optional[dict]:
    """
    Cache-aside:
        1. Read cache.
        2. If hit, return cached value.
        3. If miss, read database.
        4. Store result in cache.
        5. Return result.
    """
    cached = cache.get(key)

    if cached is not None:
        return cached

    value = database.get(key)

    if value is not None:
        cache.set(key, value, ttl_seconds=10)

    return value


def demonstrate_cache_aside() -> None:
    cache = TTLCache()
    database = FakeDatabase()

    print(cache_aside_get("user:1", cache, database))
    print(cache_aside_get("user:1", cache, database))
    print("Database reads:", database.read_count)


# =============================================================================
# 25. DATABASE SCALABILITY
# =============================================================================

def demonstrate_database_scaling_concepts() -> None:
    """
    Common database scaling techniques:

    Indexing:
        Reduce lookup work for supported access patterns.

    Read replicas:
        Offload read traffic.

    Partitioning:
        Divide data into partitions.

    Sharding:
        Distribute partitions across database nodes.

    Connection pooling:
        Reuse database connections.

    Denormalization:
        Duplicate selected data to optimize reads.

    Archiving:
        Move cold data out of hot operational tables.

    Each technique has costs and consistency implications.
    """
    concepts = {
        "indexing": "Improve lookup efficiency for suitable queries.",
        "read replicas": "Distribute read workloads.",
        "partitioning": "Split data into manageable logical partitions.",
        "sharding": "Distribute data across independent database nodes.",
        "connection pooling": "Reuse expensive database connections.",
        "denormalization": "Trade storage/write complexity for read performance.",
    }

    for name, explanation in concepts.items():
        print(f"{name}: {explanation}")


# =============================================================================
# 26. CONSISTENCY VS AVAILABILITY TRADE-OFFS
# =============================================================================

def compare_consistency_models() -> None:
    """
    Strong consistency:
        Reads reflect the most recent committed write according to the
        system's consistency guarantees.

    Eventual consistency:
        Replicas may temporarily disagree but converge when updates propagate.

    Stronger consistency can require:
        - coordination
        - quorum communication
        - increased latency
        - reduced availability under some network failures

    Eventual consistency can provide:
        - lower coordination overhead
        - greater availability in some architectures
        - better geographic scalability

    The correct model depends on the business invariant.
    """
    comparison = [
        ("Strong consistency", "simpler reads", "more coordination"),
        ("Eventual consistency", "high scalability", "stale reads possible"),
    ]

    for model, benefit, cost in comparison:
        print(f"{model}: benefit={benefit}; trade-off={cost}")


# =============================================================================
# 27. DISTRIBUTED SYSTEM FAILURE MODES
# =============================================================================

class FailureType(Enum):
    TIMEOUT = "timeout"
    CONNECTION_FAILURE = "connection failure"
    PARTIAL_FAILURE = "partial failure"
    OVERLOAD = "overload"
    DATA_CORRUPTION = "data corruption"
    DEPENDENCY_FAILURE = "dependency failure"


def demonstrate_failure_modes() -> None:
    """
    Distributed systems are especially difficult because failure is not binary.

    A dependency may be:
        - completely unavailable
        - intermittently available
        - reachable but slow
        - returning incorrect data
        - accepting writes but losing acknowledgements
        - available in one region but not another

    Correct designs define behavior for each important failure mode.
    """
    for failure in FailureType:
        print(failure.value)


# =============================================================================
# 28. FAULT INJECTION SIMULATION
# =============================================================================

@dataclass
class RequestSimulation:
    success: bool
    latency_ms: float
    failure: Optional[FailureType]


def simulate_requests(
    count: int,
    failure_probability: float,
) -> List[RequestSimulation]:
    """
    A small fault-injection simulation demonstrates why testing only the
    healthy path is insufficient.
    """
    if count <= 0:
        raise ValueError("count must be positive.")
    if not 0 <= failure_probability <= 1:
        raise ValueError("failure_probability must be between 0 and 1.")

    results: List[RequestSimulation] = []

    for _ in range(count):
        if random.random() < failure_probability:
            failure = random.choice(list(FailureType))
            results.append(
                RequestSimulation(
                    success=False,
                    latency_ms=random.uniform(50, 1000),
                    failure=failure,
                )
            )
        else:
            results.append(
                RequestSimulation(
                    success=True,
                    latency_ms=random.uniform(10, 100),
                    failure=None,
                )
            )

    return results


def summarize_simulation(results: List[RequestSimulation]) -> None:
    successful = sum(result.success for result in results)
    latencies = [result.latency_ms for result in results]

    print("Requests:", len(results))
    print("Success rate:", successful / len(results))
    print("p50 latency:", percentile(latencies, 50))
    print("p95 latency:", percentile(latencies, 95))
    print("p99 latency:", percentile(latencies, 99))


# =============================================================================
# 29. SECURITY FUNDAMENTALS
# =============================================================================

class SecurityPrinciple(Enum):
    CONFIDENTIALITY = "confidentiality"
    INTEGRITY = "integrity"
    AVAILABILITY = "availability"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ACCOUNTABILITY = "accountability"


def demonstrate_security_principles() -> None:
    """
    CIA:

    Confidentiality:
        Only authorized parties can access protected information.

    Integrity:
        Data and operations are protected from unauthorized alteration.

    Availability:
        Authorized users can access services when needed.

    Authentication:
        Establishing who an actor is.

    Authorization:
        Determining what an authenticated actor may do.

    Accountability:
        Maintaining evidence of security-relevant actions.
    """
    for principle in SecurityPrinciple:
        print(principle.value)


# =============================================================================
# 30. PASSWORD HASHING
# =============================================================================

def hash_secret(secret: str, salt: bytes) -> str:
    """
    This demonstration uses PBKDF2 from Python's standard library.

    Password storage should use a password-specific password hashing scheme
    such as Argon2id, scrypt, bcrypt, or PBKDF2 with an appropriate work factor.

    Never store plaintext passwords.

    A production system should also use:
        - unique salts
        - appropriate work factors
        - secure secret handling
        - rate limiting
        - account lockout or risk controls where appropriate
        - MFA for sensitive access
    """
    if not secret:
        raise ValueError("Secret cannot be empty.")

    derived = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        iterations=200_000,
    )

    return derived.hex()


def verify_secret(
    secret: str,
    salt: bytes,
    expected_hash: str,
) -> bool:
    actual_hash = hash_secret(secret, salt)

    return hmac.compare_digest(actual_hash, expected_hash)


def demonstrate_password_hashing() -> None:
    salt = b"unique-demo-salt"
    stored_hash = hash_secret("correct-password", salt)

    print(
        "Correct password:",
        verify_secret("correct-password", salt, stored_hash),
    )

    print(
        "Incorrect password:",
        verify_secret("wrong-password", salt, stored_hash),
    )


# =============================================================================
# 31. AUTHENTICATION AND AUTHORIZATION
# =============================================================================

@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: frozenset[str]


def authorize(
    principal: Principal,
    required_role: str,
) -> bool:
    """
    Authentication answers:
        "Who are you?"

    Authorization answers:
        "What are you allowed to do?"

    Authorization should be enforced server-side rather than trusting
    client-provided claims or UI restrictions.
    """
    return required_role in principal.roles


def demonstrate_authorization() -> None:
    user = Principal(
        user_id="user-42",
        roles=frozenset({"reader"}),
    )

    print("Can read:", authorize(user, "reader"))
    print("Can administer:", authorize(user, "admin"))


# =============================================================================
# 32. INPUT VALIDATION
# =============================================================================

def validate_username(username: str) -> str:
    """
    Validation should occur at trust boundaries.

    Good validation:
        - explicit
        - allowlist-oriented where practical
        - size-limited
        - type-aware
        - context-specific

    Validation is not a substitute for parameterized database queries,
    output encoding, authorization, or other security controls.
    """
    normalized = username.strip()

    if not normalized:
        raise ValueError("Username cannot be empty.")

    if len(normalized) > 50:
        raise ValueError("Username is too long.")

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_-"
    )

    if any(character not in allowed for character in normalized):
        raise ValueError("Username contains unsupported characters.")

    return normalized


def demonstrate_input_validation() -> None:
    valid_inputs = ["atul_123", "developer-42"]

    invalid_inputs = ["", "user@example.com", "a" * 51]

    for username in valid_inputs:
        print("Valid:", validate_username(username))

    for username in invalid_inputs:
        try:
            validate_username(username)
        except ValueError as error:
            print("Rejected:", repr(username), error)


# =============================================================================
# 33. RATE LIMITING
# =============================================================================

class TokenBucket:
    """
    Token bucket rate limiting:

    - tokens accumulate at a configured rate
    - the bucket has a maximum capacity
    - each request consumes tokens
    - bursts can be supported up to bucket capacity

    This is useful for protecting:
        - APIs
        - login endpoints
        - expensive operations
        - downstream dependencies
    """

    def __init__(
        self,
        capacity: float,
        refill_rate_per_second: float,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be positive.")
        if refill_rate_per_second <= 0:
            raise ValueError("refill rate must be positive.")

        self.capacity = capacity
        self.refill_rate = refill_rate_per_second
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill

        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate,
        )

        self.last_refill = now

    def allow(self, cost: float = 1) -> bool:
        if cost <= 0:
            raise ValueError("cost must be positive.")

        self._refill()

        if self.tokens < cost:
            return False

        self.tokens -= cost
        return True


def demonstrate_rate_limiting() -> None:
    limiter = TokenBucket(
        capacity=3,
        refill_rate_per_second=2,
    )

    decisions = [limiter.allow() for _ in range(5)]

    print("Immediate decisions:", decisions)

    time.sleep(0.6)

    print("After refill:", limiter.allow())


# =============================================================================
# 34. TLS AND DATA PROTECTION
# =============================================================================

def demonstrate_transport_security() -> None:
    """
    Sensitive network communication should normally use TLS.

    TLS protects communication against many forms of passive interception
    and tampering when configured correctly.

    Production considerations include:
        - certificate validation
        - trusted certificate authorities
        - modern protocol versions
        - private key protection
        - certificate rotation
        - hostname verification

    Application-level encryption may still be required for especially sensitive
    fields or end-to-end protection requirements.
    """
    controls = [
        "TLS for data in transit",
        "encryption at rest",
        "key management",
        "certificate rotation",
        "secret rotation",
        "access control",
    ]

    for control in controls:
        print(control)


# =============================================================================
# 35. OBSERVABILITY
# =============================================================================

@dataclass
class MetricSet:
    request_count: int = 0
    error_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        if self.request_count == 0:
            return 0.0

        return self.error_count / self.request_count

    @property
    def p95_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0

        return percentile(self.latencies_ms, 95)


def demonstrate_observability() -> None:
    """
    Observability is commonly discussed through:

    Metrics:
        Numeric time-series measurements.

    Logs:
        Structured or unstructured event records.

    Traces:
        End-to-end request paths through distributed components.

    Important metrics include:
        - request rate
        - error rate
        - latency percentiles
        - saturation
        - queue depth
        - CPU and memory utilization
        - dependency health
    """
    metrics = MetricSet(
        request_count=1000,
        error_count=7,
        latencies_ms=[
            random.uniform(20, 200)
            for _ in range(1000)
        ],
    )

    print("Error rate:", metrics.error_rate)
    print("p95 latency:", metrics.p95_latency)


# =============================================================================
# 36. THE FOUR GOLDEN SIGNALS
# =============================================================================

def demonstrate_four_golden_signals() -> None:
    """
    Four commonly used service-level signals:

    Latency:
        Time required to service requests.

    Traffic:
        Demand placed on the system.

    Errors:
        Rate of failed requests.

    Saturation:
        How close a resource is to its effective limit.
    """
    signals = {
        "latency": "p50/p95/p99 response duration",
        "traffic": "requests per second",
        "errors": "failed requests or failed operations",
        "saturation": "resource pressure and queueing",
    }

    for name, meaning in signals.items():
        print(f"{name}: {meaning}")


# =============================================================================
# 37. SLI, SLO, SLA
# =============================================================================

@dataclass
class ServiceObjective:
    sli: str
    slo: str
    sla: str


def demonstrate_sli_slo_sla() -> None:
    """
    SLI:
        Service Level Indicator.
        A measured quantity representing service behavior.

    SLO:
        Service Level Objective.
        The internal target for an SLI.

    SLA:
        Service Level Agreement.
        A contractual commitment that may include consequences or credits.

    Example:
        SLI = successful requests / valid requests
        SLO = 99.95%
        SLA = contractual availability commitment with defined terms
    """
    objective = ServiceObjective(
        sli="successful valid API requests / total valid API requests",
        slo=">= 99.95% monthly",
        sla="Contractual commitment with defined remedies",
    )

    print(objective)


# =============================================================================
# 38. ERROR BUDGET
# =============================================================================

def error_budget(availability_target: float) -> float:
    """
    Error budget:

        1 - SLO

    If the availability SLO is 99.9%, the error budget is 0.1%.

    Error budgets connect reliability engineering with delivery decisions.
    A team can use the budget to reason about whether additional risky changes
    are appropriate.
    """
    if not 0 <= availability_target <= 1:
        raise ValueError("Target must be a fraction between 0 and 1.")

    return 1 - availability_target


def demonstrate_error_budget() -> None:
    target = 0.999
    print(
        f"SLO={target:.3%}, "
        f"error budget={error_budget(target):.3%}"
    )


# =============================================================================
# 39. GRACEFUL DEGRADATION
# =============================================================================

def personalized_recommendations(
    user_id: str,
    recommendation_service: Callable[[str], List[str]],
) -> List[str]:
    """
    Graceful degradation means preserving essential functionality when
    optional functionality fails.

    If recommendations fail, the core product page can still be served.

    The fallback must not violate:
        - security
        - correctness
        - data integrity
        - critical business rules
    """
    try:
        recommendations = recommendation_service(user_id)

        if recommendations:
            return recommendations

    except Exception:
        pass

    return ["popular-item-1", "popular-item-2"]


def demonstrate_graceful_degradation() -> None:
    def unavailable_service(_: str) -> List[str]:
        raise ConnectionError("Recommendation service unavailable.")

    print(
        personalized_recommendations(
            "user-1",
            unavailable_service,
        )
    )


# =============================================================================
# 40. REDUNDANCY
# =============================================================================

@dataclass
class RedundantComponent:
    name: str
    healthy: bool = True


def service_available_with_redundancy(
    components: List[RedundantComponent],
) -> bool:
    """
    For an N+1 style conceptual model, spare capacity allows one component
    to fail while maintaining service.

    Real availability calculations must consider common-mode failures.
    Two replicas in the same failure domain do not provide the same resilience
    as independent replicas across failure domains.
    """
    return any(component.healthy for component in components)


def demonstrate_redundancy() -> None:
    components = [
        RedundantComponent("zone-a"),
        RedundantComponent("zone-b"),
        RedundantComponent("zone-c"),
    ]

    components[0].healthy = False

    print("Service available:", service_available_with_redundancy(components))


# =============================================================================
# 41. DEPENDENCY AVAILABILITY
# =============================================================================

def series_availability(component_availabilities: Iterable[float]) -> float:
    """
    For a simplified serial dependency model:

        A_total = A1 * A2 * ... * An

    If a request requires every dependency to succeed, every dependency
    contributes to the probability of success.

    Real systems may reduce dependency impact through:
        - caching
        - asynchronous processing
        - fallback behavior
        - redundancy
        - isolation
    """
    result = 1.0

    for availability in component_availabilities:
        if not 0 <= availability <= 1:
            raise ValueError("Availability must be between 0 and 1.")
        result *= availability

    return result


def demonstrate_dependency_availability() -> None:
    components = [0.999, 0.9995, 0.9999]

    print(
        "Simplified serial availability:",
        f"{series_availability(components):.5%}",
    )


# =============================================================================
# 42. QUEUEING AND TAIL LATENCY
# =============================================================================

def queueing_pressure(
    arrival_rate: float,
    service_rate: float,
) -> float:
    """
    Simplified utilization:

        rho = arrival rate / service rate

    As rho approaches 1, queueing delay can become substantial.

    If arrival rate exceeds service rate for a sustained period, backlog grows.
    """
    if service_rate <= 0:
        raise ValueError("service_rate must be positive.")

    return arrival_rate / service_rate


def demonstrate_queueing_pressure() -> None:
    for arrival_rate in [50, 80, 90, 95, 99, 105]:
        pressure = queueing_pressure(arrival_rate, 100)
        print(
            f"Arrival={arrival_rate:3} req/s -> "
            f"Utilization={pressure:.1%}"
        )


# =============================================================================
# 43. AUTOSCALING
# =============================================================================

@dataclass
class AutoScaler:
    minimum_instances: int
    maximum_instances: int
    target_utilization: float
    instances: int

    def scale(self, observed_utilization: float) -> int:
        if not 0 < self.target_utilization <= 1:
            raise ValueError("target_utilization must be between 0 and 1.")

        if observed_utilization > self.target_utilization * 1.1:
            self.instances = min(
                self.maximum_instances,
                self.instances + 1,
            )
        elif observed_utilization < self.target_utilization * 0.5:
            self.instances = max(
                self.minimum_instances,
                self.instances - 1,
            )

        return self.instances


def demonstrate_autoscaling() -> None:
    scaler = AutoScaler(
        minimum_instances=2,
        maximum_instances=10,
        target_utilization=0.65,
        instances=3,
    )

    observations = [0.7, 0.8, 0.9, 0.95, 0.4, 0.3, 0.2]

    for utilization in observations:
        instances = scaler.scale(utilization)
        print(
            f"Observed={utilization:.0%}, "
            f"instances={instances}"
        )


# =============================================================================
# 44. CAPACITY PLANNING
# =============================================================================

@dataclass
class CapacityPlan:
    expected_load: float
    peak_multiplier: float
    growth_factor: float
    safety_factor: float

    @property
    def required_capacity(self) -> float:
        return (
            self.expected_load
            * self.peak_multiplier
            * self.growth_factor
            * self.safety_factor
        )


def demonstrate_capacity_planning() -> None:
    plan = CapacityPlan(
        expected_load=5000,
        peak_multiplier=2,
        growth_factor=1.5,
        safety_factor=1.2,
    )

    print("Required planned capacity:", plan.required_capacity)


# =============================================================================
# 45. PERFORMANCE VS SCALABILITY
# =============================================================================

def compare_performance_and_scalability() -> None:
    """
    Performance:
        How efficiently one configuration performs.

    Scalability:
        How performance/capacity changes as workload or resources change.

    An application can be fast but poorly scalable.
    An application can scale horizontally but have poor single-instance
    efficiency.

    Performance optimization examples:
        - algorithm improvement
        - query optimization
        - caching
        - serialization optimization

    Scalability improvements:
        - horizontal replication
        - partitioning
        - asynchronous processing
        - load distribution
    """
    examples = {
        "performance": "Reduce one request from 200 ms to 100 ms.",
        "scalability": "Increase sustainable throughput from 1,000 to 10,000 req/s.",
    }

    for concept, example in examples.items():
        print(f"{concept}: {example}")


# =============================================================================
# 46. SECURITY AND AVAILABILITY TRADE-OFF
# =============================================================================

def demonstrate_security_availability_tradeoff() -> None:
    """
    Security controls can affect latency, availability, and operational
    complexity.

    Examples:
        - aggressive authentication checks add latency
        - strict rate limiting can reject legitimate traffic
        - encryption adds computational work
        - security monitoring consumes infrastructure
        - dependency on an external identity provider can create availability
          dependencies

    The answer is not to remove security. Controls should be designed,
    measured, isolated, and made resilient.
    """
    tradeoffs = [
        ("rate limiting", "protects capacity", "can reject legitimate bursts"),
        ("authentication", "protects access", "adds processing and dependency"),
        ("encryption", "protects confidentiality", "adds computational overhead"),
    ]

    for control, benefit, cost in tradeoffs:
        print(f"{control}: benefit={benefit}; cost={cost}")


# =============================================================================
# 47. DEFENSE IN DEPTH
# =============================================================================

def demonstrate_defense_in_depth() -> None:
    """
    Defense in depth avoids relying on a single security control.

    Example layers:
        1. network segmentation
        2. TLS
        3. authentication
        4. authorization
        5. input validation
        6. rate limiting
        7. secure database access
        8. audit logging
        9. monitoring and alerting
        10. incident response
    """
    layers = [
        "network controls",
        "transport encryption",
        "authentication",
        "authorization",
        "input validation",
        "rate limiting",
        "secure data access",
        "audit logging",
        "monitoring",
        "incident response",
    ]

    for position, layer in enumerate(layers, start=1):
        print(f"{position}. {layer}")


# =============================================================================
# 48. SECURE DATABASE ACCESS CONCEPT
# =============================================================================

def build_parameterized_query(user_id: str) -> Tuple[str, Tuple[str]]:
    """
    Parameterized queries separate code from data.

    This function only constructs the statement and parameters. It does not
    execute SQL because the script intentionally avoids an external database.

    Avoid constructing SQL by directly concatenating untrusted input.
    """
    query = "SELECT id, name FROM users WHERE id = ?"
    parameters = (user_id,)

    return query, parameters


def demonstrate_parameterized_query() -> None:
    query, parameters = build_parameterized_query("user-123")

    print("Query:", query)
    print("Parameters:", parameters)


# =============================================================================
# 49. DATA CLASSIFICATION
# =============================================================================

class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    HIGHLY_SENSITIVE = "highly sensitive"


def demonstrate_data_classification() -> None:
    """
    Security controls should be proportional to data sensitivity.

    Typical considerations:
        - access restrictions
        - encryption
        - retention
        - audit requirements
        - masking
        - tokenization
        - deletion
    """
    controls = {
        DataClassification.PUBLIC: "standard integrity controls",
        DataClassification.INTERNAL: "authenticated internal access",
        DataClassification.CONFIDENTIAL: "restricted access and encryption",
        DataClassification.HIGHLY_SENSITIVE: "strong access controls, encryption, auditing, and minimized exposure",
    }

    for classification, control in controls.items():
        print(f"{classification.value}: {control}")


# =============================================================================
# 50. DISASTER RECOVERY
# =============================================================================

@dataclass
class RecoveryObjectives:
    rpo_minutes: int
    rto_minutes: int


def demonstrate_rto_rpo() -> None:
    """
    RTO: Recovery Time Objective.
        Maximum targeted time to restore service after a disruptive event.

    RPO: Recovery Point Objective.
        Maximum targeted amount of data loss measured in time.

    Example:
        RTO = 30 minutes
        RPO = 5 minutes

    These objectives influence:
        - replication
        - backup frequency
        - infrastructure design
        - recovery automation
        - operational cost
    """
    objectives = RecoveryObjectives(
        rpo_minutes=5,
        rto_minutes=30,
    )

    print("RPO:", objectives.rpo_minutes, "minutes")
    print("RTO:", objectives.rto_minutes, "minutes")


# =============================================================================
# 51. BACKUPS
# =============================================================================

def backup_strategy() -> Dict[str, str]:
    """
    A backup is not a recovery strategy until restoration is tested.

    Important backup concepts:
        - full backup
        - incremental backup
        - differential backup
        - retention
        - encryption
        - immutability
        - geographic separation
        - restoration testing
    """
    return {
        "frequency": "defined by RPO",
        "retention": "defined by business and regulatory requirements",
        "security": "encrypted and access-controlled",
        "resilience": "stored independently from primary failure domain",
        "verification": "regular restoration tests",
    }


# =============================================================================
# 52. DEPLOYMENT STRATEGIES
# =============================================================================

class DeploymentStrategy(Enum):
    ROLLING = "rolling"
    BLUE_GREEN = "blue-green"
    CANARY = "canary"


def demonstrate_deployment_strategies() -> None:
    """
    Rolling deployment:
        Gradually replaces instances.

    Blue-green:
        Maintains two environments and shifts traffic between them.

    Canary:
        Sends a small percentage of traffic to the new version before
        increasing exposure.

    Deployment strategy affects:
        - availability
        - rollback speed
        - infrastructure cost
        - blast radius
        - observability requirements
    """
    for strategy in DeploymentStrategy:
        print(strategy.value)


# =============================================================================
# 53. BLAST RADIUS
# =============================================================================

@dataclass
class Deployment:
    affected_instances: int
    total_instances: int

    @property
    def blast_radius(self) -> float:
        if self.total_instances <= 0:
            raise ValueError("total_instances must be positive.")

        return self.affected_instances / self.total_instances


def demonstrate_blast_radius() -> None:
    deployment = Deployment(
        affected_instances=2,
        total_instances=20,
    )

    print("Blast radius:", f"{deployment.blast_radius:.1%}")


# =============================================================================
# 54. HEALTH CHECKS
# =============================================================================

class HealthChecker:
    def __init__(
        self,
        dependency_checks: Dict[str, Callable[[], bool]],
    ):
        self.dependency_checks = dependency_checks

    def check(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}

        for name, check in self.dependency_checks.items():
            try:
                results[name] = bool(check())
            except Exception:
                results[name] = False

        return results


def demonstrate_health_checks() -> None:
    checker = HealthChecker(
        {
            "database": lambda: True,
            "cache": lambda: True,
            "payment-provider": lambda: False,
        }
    )

    print(checker.check())


# =============================================================================
# 55. LIVENESS VS READINESS
# =============================================================================

def demonstrate_liveness_readiness() -> None:
    """
    Liveness:
        "Is the process alive?"

    Readiness:
        "Can this instance safely receive traffic?"

    A process may be alive but not ready because:
        - dependencies are unavailable
        - initialization is incomplete
        - it is draining connections
        - it is overloaded
    """
    print("Liveness: process is running.")
    print("Readiness: instance is capable of accepting work.")


# =============================================================================
# 56. TESTING NON-FUNCTIONAL REQUIREMENTS
# =============================================================================

class TestType(Enum):
    LOAD = "load testing"
    STRESS = "stress testing"
    SOAK = "soak testing"
    SPIKE = "spike testing"
    FAILOVER = "failover testing"
    RECOVERY = "recovery testing"
    SECURITY = "security testing"


def demonstrate_testing_types() -> None:
    """
    Load testing:
        Test expected workload.

    Stress testing:
        Push beyond expected capacity to identify failure behavior.

    Soak testing:
        Run sustained workload to reveal leaks and gradual degradation.

    Spike testing:
        Test sudden workload changes.

    Failover testing:
        Verify recovery from component failure.

    Recovery testing:
        Verify restoration after major disruption.

    Security testing:
        Identify vulnerabilities and validate controls.
    """
    for test_type in TestType:
        print(test_type.value)


# =============================================================================
# 57. SIMPLE LOAD TEST SIMULATION
# =============================================================================

@dataclass
class LoadTestResult:
    requests: int
    successes: int
    failures: int
    latencies_ms: List[float]

    @property
    def success_rate(self) -> float:
        return self.successes / self.requests

    @property
    def p95(self) -> float:
        return percentile(self.latencies_ms, 95)


def run_load_test(
    requests: int,
    capacity_per_second: float,
) -> LoadTestResult:
    """
    This is an educational simulation, not a substitute for a real load
    testing system.

    It models overload by increasing latency and failure probability when
    demand approaches or exceeds capacity.
    """
    if requests <= 0:
        raise ValueError("requests must be positive.")
    if capacity_per_second <= 0:
        raise ValueError("capacity_per_second must be positive.")

    load = requests
    utilization = load / capacity_per_second

    latencies: List[float] = []
    successes = 0
    failures = 0

    for _ in range(requests):
        if utilization <= 0.7:
            latency = random.uniform(20, 60)
            failure_probability = 0.001
        elif utilization <= 1.0:
            latency = random.uniform(40, 250)
            failure_probability = 0.01
        else:
            latency = random.uniform(100, 1000)
            failure_probability = min(
                0.5,
                0.05 + (utilization - 1.0) * 0.2,
            )

        latencies.append(latency)

        if random.random() < failure_probability:
            failures += 1
        else:
            successes += 1

    return LoadTestResult(
        requests=requests,
        successes=successes,
        failures=failures,
        latencies_ms=latencies,
    )


def demonstrate_load_testing() -> None:
    for requests in [500, 900, 1100]:
        result = run_load_test(
            requests=requests,
            capacity_per_second=1000,
        )

        print(
            f"Load={requests}, "
            f"success={result.success_rate:.2%}, "
            f"p95={result.p95:.2f} ms"
        )


# =============================================================================
# 58. REQUIREMENT TRACEABILITY
# =============================================================================

@dataclass
class RequirementTrace:
    requirement: str
    metric: str
    test: str
    dashboard: str
    owner: str


def demonstrate_traceability() -> None:
    """
    A production NFR should map to:

        requirement
            -> measurable metric
            -> test
            -> monitoring dashboard
            -> alert
            -> responsible owner
            -> operational response

    This prevents NFRs from remaining vague statements in documents.
    """
    traces = [
        RequirementTrace(
            requirement="p95 API latency <= 300 ms",
            metric="api_latency_p95",
            test="load test",
            dashboard="API latency dashboard",
            owner="API team",
        ),
        RequirementTrace(
            requirement="99.95% monthly availability",
            metric="successful_request_ratio",
            test="failover test",
            dashboard="availability dashboard",
            owner="platform team",
        ),
        RequirementTrace(
            requirement="zero unauthorized access",
            metric="security_events",
            test="security test",
            dashboard="security monitoring",
            owner="security team",
        ),
    ]

    for trace in traces:
        print(trace)


# =============================================================================
# 59. TRADE-OFF MATRIX
# =============================================================================

def demonstrate_tradeoff_matrix() -> None:
    """
    NFRs interact.

    Increasing redundancy can improve availability but increase cost.

    Increasing caching can reduce latency but introduce staleness.

    Increasing security checks can improve protection but add processing
    and dependency requirements.

    Increasing consistency can simplify correctness but require coordination.

    Increasing retries can improve success probability for transient failures
    but can amplify overload.
    """
    tradeoffs = [
        ("more replicas", "availability", "cost"),
        ("more caching", "latency", "staleness"),
        ("more retries", "transient success", "retry storms"),
        ("stronger consistency", "correctness", "latency/coordination"),
        ("strict rate limiting", "protection", "legitimate rejection"),
        ("larger instances", "performance", "cost"),
    ]

    for decision, benefit, cost in tradeoffs:
        print(f"{decision}: benefit={benefit}; cost={cost}")


# =============================================================================
# 60. REQUIREMENT QUALITY CHECK
# =============================================================================

def validate_requirement_quality(requirement: Requirement) -> List[str]:
    """
    A basic quality checker identifies obvious omissions.

    Good NFRs should generally be:
        - specific
        - measurable
        - testable
        - scoped
        - time-bounded where appropriate
        - tied to business impact
    """
    issues: List[str] = []

    if not requirement.name.strip():
        issues.append("Missing requirement name.")

    if not requirement.metric.strip():
        issues.append("Missing metric.")

    if not requirement.target.strip():
        issues.append("Missing target.")

    if not requirement.measurement_window.strip():
        issues.append("Missing measurement window.")

    if not requirement.scope.strip():
        issues.append("Missing scope.")

    return issues


def demonstrate_requirement_quality() -> None:
    requirement = Requirement(
        name="Latency",
        metric="p99 request latency",
        target="<= 500 ms",
        measurement_window="monthly",
        scope="checkout API",
    )

    print("Requirement issues:", validate_requirement_quality(requirement))


# =============================================================================
# 61. END-TO-END ARCHITECTURAL SIMULATION
# =============================================================================

@dataclass
class Request:
    request_id: int
    user_id: str
    operation: str


class ProductionLikeService:
    """
    A compact conceptual service combining several NFR techniques:

        - input validation
        - rate limiting
        - caching
        - authorization
        - timeout boundaries
        - fallback behavior
        - metrics

    This is intentionally simplified. A real production system would separate
    concerns into independently testable modules and infrastructure.
    """

    def __init__(self):
        self.cache = TTLCache()
        self.rate_limiter = TokenBucket(
            capacity=10,
            refill_rate_per_second=5,
        )
        self.metrics = MetricSet()

    def _database_read(self, user_id: str) -> Dict[str, str]:
        time.sleep(0.01)

        return {
            "user_id": user_id,
            "status": "active",
        }

    def handle(self, request: Request) -> Dict[str, str]:
        start = time.perf_counter()
        self.metrics.request_count += 1

        try:
            validate_username(request.user_id)

            if not self.rate_limiter.allow():
                raise RuntimeError("Rate limit exceeded.")

            principal = Principal(
                user_id=request.user_id,
                roles=frozenset({"reader"}),
            )

            if not authorize(principal, "reader"):
                raise PermissionError("Not authorized.")

            cache_key = f"profile:{request.user_id}"
            cached = self.cache.get(cache_key)

            if cached is not None:
                return cached

            result = operation_with_timeout(
                lambda: self._database_read(request.user_id),
                timeout_seconds=0.2,
            )

            self.cache.set(
                cache_key,
                result,
                ttl_seconds=10,
            )

            return result

        except Exception:
            self.metrics.error_count += 1
            raise

        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.metrics.latencies_ms.append(elapsed_ms)


def demonstrate_end_to_end_service() -> None:
    service = ProductionLikeService()

    for request_id in range(5):
        request = Request(
            request_id=request_id,
            user_id="user_1",
            operation="read_profile",
        )

        try:
            print("Response:", service.handle(request))
        except Exception as error:
            print("Request failed:", error)

    print("Request count:", service.metrics.request_count)
    print("Error count:", service.metrics.error_count)
    print("p95 latency:", service.metrics.p95_latency)


# =============================================================================
# 62. COMMON ARCHITECTURAL ANTI-PATTERNS
# =============================================================================

def demonstrate_anti_patterns() -> None:
    """
    Common NFR anti-patterns:

    1. "Make it highly available."
       Problem: no measurable target.

    2. "The system must be fast."
       Problem: no latency percentile or workload.

    3. Retry every failure.
       Problem: permanent failures and overload amplification.

    4. Scale only after users complain.
       Problem: no capacity forecast or early warning.

    5. Store sessions only in local memory.
       Problem: horizontal scaling becomes difficult.

    6. Treat average latency as the only latency metric.
       Problem: hides tail latency.

    7. Use one availability zone for all replicas.
       Problem: common failure domain.

    8. Trust client-side authorization.
       Problem: clients are not trusted enforcement boundaries.

    9. Create unlimited queues.
       Problem: eventual memory exhaustion.

    10. Back up data but never restore-test it.
        Problem: backup existence does not guarantee recoverability.
    """
    anti_patterns = [
        "vague availability target",
        "average-only latency measurement",
        "unbounded retries",
        "reactive capacity planning",
        "local-only state",
        "single failure domain",
        "client-side authorization",
        "unbounded queue",
        "untested backups",
    ]

    for anti_pattern in anti_patterns:
        print(anti_pattern)


# =============================================================================
# 63. PRODUCTION DESIGN CHECKLIST
# =============================================================================

def production_nfr_checklist() -> Dict[str, List[str]]:
    """
    A practical checklist for architecture and design reviews.
    """
    return {
        "scalability": [
            "Expected workload defined",
            "Peak workload defined",
            "Capacity per instance measured",
            "Horizontal scaling behavior tested",
            "Bottlenecks identified",
        ],
        "availability": [
            "Availability target defined",
            "Failure domains identified",
            "Redundancy implemented where justified",
            "Failover tested",
            "Health checks implemented",
        ],
        "reliability": [
            "Failure modes documented",
            "Timeouts configured",
            "Retries bounded",
            "Idempotency considered",
            "Recovery procedures tested",
        ],
        "latency": [
            "Latency target defined",
            "p50/p95/p99 monitored",
            "Latency budget allocated",
            "Slow dependencies identified",
            "Tail latency investigated",
        ],
        "security": [
            "Authentication defined",
            "Authorization enforced server-side",
            "Sensitive data classified",
            "Data encrypted appropriately",
            "Secrets protected and rotated",
            "Rate limits defined",
            "Security events monitored",
        ],
    }


def demonstrate_production_checklist() -> None:
    checklist = production_nfr_checklist()

    for category, checks in checklist.items():
        print(f"\n{category.upper()}")

        for check in checks:
            print(f"  [ ] {check}")


# =============================================================================
# 64. INTEGRATED CASE STUDY
# =============================================================================

def integrated_case_study() -> None:
    """
    Scenario:

        An e-commerce API currently serves 1,000 requests/second.
        Peak traffic is expected to reach 4,000 requests/second.
        The business requires 99.95% monthly availability.
        Checkout p95 latency must remain below 300 ms.
        Payment operations must not be duplicated.
        Customer data requires authentication and authorization.

    Design reasoning:

        Scalability:
            Use horizontally scalable stateless API instances behind a load
            balancer. Capacity-test instances and scale based on demand.

        Availability:
            Run instances across independent failure domains. Use health checks,
            automated replacement, and tested failover.

        Reliability:
            Use timeouts, bounded retries, idempotency keys, and circuit
            breakers for external dependencies.

        Latency:
            Define an end-to-end latency budget and monitor p50/p95/p99.
            Cache safe reads and optimize database access.

        Security:
            Authenticate users, authorize operations, encrypt network traffic,
            validate input, protect secrets, rate-limit sensitive endpoints,
            and audit security events.

        These qualities are not independent. Every design decision changes
        multiple dimensions.
    """
    print("E-commerce API NFR case study loaded.")


# =============================================================================
# 65. ADVANCED RELATIONSHIP: AVAILABILITY VS RELIABILITY
# =============================================================================

def compare_availability_reliability() -> None:
    scenarios = {
        "available_but_incorrect": (
            "Service responds quickly but returns incorrect account balances."
        ),
        "reliable_but_temporarily_unavailable": (
            "Service correctly processes every request when reachable but "
            "has a planned outage during maintenance."
        ),
        "available_and_reliable": (
            "Service remains reachable and produces correct results consistently."
        ),
    }

    for scenario, explanation in scenarios.items():
        print(f"{scenario}: {explanation}")


# =============================================================================
# 66. ADVANCED RELATIONSHIP: LATENCY VS THROUGHPUT
# =============================================================================

def compare_latency_throughput() -> None:
    """
    Latency and throughput are different.

    Latency:
        How long one operation takes.

    Throughput:
        How much work the system completes per unit time.

    Concurrency can allow high throughput even when individual operations
    are not especially fast.

    Conversely, a low-latency operation can still have low system throughput
    if the architecture has limited concurrency or capacity.
    """
    print("Latency: time per operation.")
    print("Throughput: operations completed per unit time.")


# =============================================================================
# 67. ADVANCED RELATIONSHIP: SECURITY VS PERFORMANCE
# =============================================================================

def security_performance_example() -> None:
    """
    Security decisions should be measured rather than treated as free or
    infinitely expensive.

    Example:
        Password verification intentionally consumes computational resources
        to make large-scale password guessing more expensive.

    This is a case where computational cost is part of the security design.
    """
    print("Security controls can intentionally consume resources.")
    print("The objective is controlled cost, not zero cost.")


# =============================================================================
# 68. FAILURE BUDGET THINKING
# =============================================================================

def calculate_failure_budget(
    total_requests: int,
    reliability_target: float,
) -> int:
    if total_requests < 0:
        raise ValueError("total_requests cannot be negative.")

    if not 0 <= reliability_target <= 1:
        raise ValueError("reliability_target must be between 0 and 1.")

    return math.floor(total_requests * (1 - reliability_target))


def demonstrate_failure_budget() -> None:
    total_requests = 1_000_000
    target = 0.9999

    budget = calculate_failure_budget(
        total_requests,
        target,
    )

    print(
        f"For {total_requests:,} operations at {target:.4%} reliability, "
        f"approximate failure budget={budget:,}"
    )


# =============================================================================
# 69. SECURITY RATE LIMIT DESIGN
# =============================================================================

def rate_limit_policy_examples() -> Dict[str, str]:
    """
    Different operations can require different limits.

    Login:
        Tight limit because credential attacks are possible.

    Read-only catalog:
        Higher limit because the operation may be inexpensive and common.

    Password reset:
        Tight limit because it can be abused for enumeration or messaging.

    Payment:
        Tight limit plus authentication, authorization, idempotency, and
        fraud/risk controls.
    """
    return {
        "login": "strict per-account and per-source limits",
        "catalog": "higher burst allowance with global protection",
        "password_reset": "strict limit with abuse monitoring",
        "payment": "strict limit plus authorization and idempotency",
    }


# =============================================================================
# 70. FINAL INTEGRATED DEMONSTRATION
# =============================================================================

def run_all_demos() -> None:
    print("\n" + "=" * 80)
    print("1. BASIC TERMINOLOGY")
    print("=" * 80)
    explain_basic_terminology()

    print("\n" + "=" * 80)
    print("2. MEASURABLE REQUIREMENTS")
    print("=" * 80)
    print_requirements(create_measurable_requirements())

    print("\n" + "=" * 80)
    print("3. CAPACITY")
    print("=" * 80)
    demonstrate_capacity()

    print("\n" + "=" * 80)
    print("4. LITTLE'S LAW")
    print("=" * 80)
    demonstrate_littles_law()

    print("\n" + "=" * 80)
    print("5. SCALABILITY")
    print("=" * 80)
    demonstrate_scalability()

    print("\n" + "=" * 80)
    print("6. SCALE-UP VS SCALE-OUT")
    print("=" * 80)
    compare_scaling_strategies()

    print("\n" + "=" * 80)
    print("7. LOAD BALANCING")
    print("=" * 80)
    demonstrate_load_balancing()

    print("\n" + "=" * 80)
    print("8. STATELESSNESS")
    print("=" * 80)
    demonstrate_statelessness()

    print("\n" + "=" * 80)
    print("9. AVAILABILITY")
    print("=" * 80)
    demonstrate_availability()

    print("\n" + "=" * 80)
    print("10. AVAILABILITY NINES")
    print("=" * 80)
    demonstrate_nines()

    print("\n" + "=" * 80)
    print("11. FAILOVER")
    print("=" * 80)
    demonstrate_failover()

    print("\n" + "=" * 80)
    print("12. RELIABILITY")
    print("=" * 80)
    demonstrate_reliability()

    print("\n" + "=" * 80)
    print("13. MTBF / MTTR")
    print("=" * 80)
    demonstrate_mtbf_mttr()

    print("\n" + "=" * 80)
    print("14. LATENCY DISTRIBUTION")
    print("=" * 80)
    demonstrate_latency_distribution()

    print("\n" + "=" * 80)
    print("15. LATENCY BUDGET")
    print("=" * 80)
    demonstrate_latency_budget()

    print("\n" + "=" * 80)
    print("16. TIMEOUT")
    print("=" * 80)
    demonstrate_timeout()

    print("\n" + "=" * 80)
    print("17. RETRIES")
    print("=" * 80)
    demonstrate_retries()

    print("\n" + "=" * 80)
    print("18. IDEMPOTENCY")
    print("=" * 80)
    demonstrate_idempotency()

    print("\n" + "=" * 80)
    print("19. CIRCUIT BREAKER")
    print("=" * 80)
    demonstrate_circuit_breaker()

    print("\n" + "=" * 80)
    print("20. BULKHEAD")
    print("=" * 80)
    demonstrate_bulkhead()

    print("\n" + "=" * 80)
    print("21. ASYNCHRONOUS QUEUE")
    print("=" * 80)
    demonstrate_async_processing()

    print("\n" + "=" * 80)
    print("22. BACKPRESSURE")
    print("=" * 80)
    demonstrate_backpressure()

    print("\n" + "=" * 80)
    print("23. CACHE")
    print("=" * 80)
    demonstrate_cache()

    print("\n" + "=" * 80)
    print("24. CACHE-ASIDE")
    print("=" * 80)
    demonstrate_cache_aside()

    print("\n" + "=" * 80)
    print("25. DATABASE SCALABILITY")
    print("=" * 80)
    demonstrate_database_scaling_concepts()

    print("\n" + "=" * 80)
    print("26. CONSISTENCY")
    print("=" * 80)
    compare_consistency_models()

    print("\n" + "=" * 80)
    print("27. FAILURE MODES")
    print("=" * 80)
    demonstrate_failure_modes()

    print("\n" + "=" * 80)
    print("28. FAULT INJECTION")
    print("=" * 80)
    results = simulate_requests(100, 0.05)
    summarize_simulation(results)

    print("\n" + "=" * 80)
    print("29. SECURITY PRINCIPLES")
    print("=" * 80)
    demonstrate_security_principles()

    print("\n" + "=" * 80)
    print("30. PASSWORD HASHING")
    print("=" * 80)
    demonstrate_password_hashing()

    print("\n" + "=" * 80)
    print("31. AUTHORIZATION")
    print("=" * 80)
    demonstrate_authorization()

    print("\n" + "=" * 80)
    print("32. INPUT VALIDATION")
    print("=" * 80)
    demonstrate_input_validation()

    print("\n" + "=" * 80)
    print("33. RATE LIMITING")
    print("=" * 80)
    demonstrate_rate_limiting()

    print("\n" + "=" * 80)
    print("34. TRANSPORT SECURITY")
    print("=" * 80)
    demonstrate_transport_security()

    print("\n" + "=" * 80)
    print("35. OBSERVABILITY")
    print("=" * 80)
    demonstrate_observability()

    print("\n" + "=" * 80)
    print("36. FOUR GOLDEN SIGNALS")
    print("=" * 80)
    demonstrate_four_golden_signals()

    print("\n" + "=" * 80)
    print("37. SLI / SLO / SLA")
    print("=" * 80)
    demonstrate_sli_slo_sla()

    print("\n" + "=" * 80)
    print("38. ERROR BUDGET")
    print("=" * 80)
    demonstrate_error_budget()

    print("\n" + "=" * 80)
    print("39. GRACEFUL DEGRADATION")
    print("=" * 80)
    demonstrate_graceful_degradation()

    print("\n" + "=" * 80)
    print("40. REDUNDANCY")
    print("=" * 80)
    demonstrate_redundancy()

    print("\n" + "=" * 80)
    print("41. DEPENDENCY AVAILABILITY")
    print("=" * 80)
    demonstrate_dependency_availability()

    print("\n" + "=" * 80)
    print("42. QUEUEING PRESSURE")
    print("=" * 80)
    demonstrate_queueing_pressure()

    print("\n" + "=" * 80)
    print("43. AUTOSCALING")
    print("=" * 80)
    demonstrate_autoscaling()

    print("\n" + "=" * 80)
    print("44. CAPACITY PLANNING")
    print("=" * 80)
    demonstrate_capacity_planning()

    print("\n" + "=" * 80)
    print("45. PERFORMANCE VS SCALABILITY")
    print("=" * 80)
    compare_performance_and_scalability()

    print("\n" + "=" * 80)
    print("46. SECURITY VS AVAILABILITY")
    print("=" * 80)
    demonstrate_security_availability_tradeoff()

    print("\n" + "=" * 80)
    print("47. DEFENSE IN DEPTH")
    print("=" * 80)
    demonstrate_defense_in_depth()

    print("\n" + "=" * 80)
    print("48. PARAMETERIZED DATABASE ACCESS")
    print("=" * 80)
    demonstrate_parameterized_query()

    print("\n" + "=" * 80)
    print("49. DATA CLASSIFICATION")
    print("=" * 80)
    demonstrate_data_classification()

    print("\n" + "=" * 80)
    print("50. RTO / RPO")
    print("=" * 80)
    demonstrate_rto_rpo()

    print("\n" + "=" * 80)
    print("51. BACKUP STRATEGY")
    print("=" * 80)
    print(backup_strategy())

    print("\n" + "=" * 80)
    print("52. DEPLOYMENT STRATEGIES")
    print("=" * 80)
    demonstrate_deployment_strategies()

    print("\n" + "=" * 80)
    print("53. BLAST RADIUS")
    print("=" * 80)
    demonstrate_blast_radius()

    print("\n" + "=" * 80)
    print("54. HEALTH CHECKS")
    print("=" * 80)
    demonstrate_health_checks()

    print("\n" + "=" * 80)
    print("55. LIVENESS VS READINESS")
    print("=" * 80)
    demonstrate_liveness_readiness()

    print("\n" + "=" * 80)
    print("56. NFR TESTING")
    print("=" * 80)
    demonstrate_testing_types()

    print("\n" + "=" * 80)
    print("57. LOAD TEST SIMULATION")
    print("=" * 80)
    demonstrate_load_testing()

    print("\n" + "=" * 80)
    print("58. REQUIREMENT TRACEABILITY")
    print("=" * 80)
    demonstrate_traceability()

    print("\n" + "=" * 80)
    print("59. TRADE-OFF MATRIX")
    print("=" * 80)
    demonstrate_tradeoff_matrix()

    print("\n" + "=" * 80)
    print("60. REQUIREMENT QUALITY")
    print("=" * 80)
    demonstrate_requirement_quality()

    print("\n" + "=" * 80)
    print("61. END-TO-END SERVICE")
    print("=" * 80)
    demonstrate_end_to_end_service()

    print("\n" + "=" * 80)
    print("62. ANTI-PATTERNS")
    print("=" * 80)
    demonstrate_anti_patterns()

    print("\n" + "=" * 80)
    print("63. PRODUCTION CHECKLIST")
    print("=" * 80)
    demonstrate_production_checklist()

    print("\n" + "=" * 80)
    print("64. INTEGRATED CASE STUDY")
    print("=" * 80)
    integrated_case_study()

    print("\n" + "=" * 80)
    print("65. AVAILABILITY VS RELIABILITY")
    print("=" * 80)
    compare_availability_reliability()

    print("\n" + "=" * 80)
    print("66. LATENCY VS THROUGHPUT")
    print("=" * 80)
    compare_latency_throughput()

    print("\n" + "=" * 80)
    print("67. SECURITY VS PERFORMANCE")
    print("=" * 80)
    security_performance_example()

    print("\n" + "=" * 80)
    print("68. FAILURE BUDGET")
    print("=" * 80)
    demonstrate_failure_budget()

    print("\n" + "=" * 80)
    print("69. RATE LIMIT POLICIES")
    print("=" * 80)

    for operation, policy in rate_limit_policy_examples().items():
        print(f"{operation}: {policy}")


# =============================================================================
# 71. UNIT-STYLE ASSERTIONS
# =============================================================================

def run_assertions() -> None:
    """
    Assertions provide lightweight executable verification of important
    formulas and behaviors.
    """
    assert abs(availability_percentage(100, 1) - 99) < 1e-9

    assert abs(
        littles_law(100, 0.2) - 20
    ) < 1e-9

    assert abs(
        availability_from_mtbf_mttr(100, 10)
        - (100 / 110)
    ) < 1e-9

    assert percentile([1, 2, 3, 4, 5], 50) == 3

    cache = TTLCache()
    cache.set("key", "value", 1)
    assert cache.get("key") == "value"

    store = IdempotencyStore()
    calls = {"count": 0}

    def operation() -> str:
        calls["count"] += 1
        return "done"

    assert store.execute("same-key", operation) == "done"
    assert store.execute("same-key", operation) == "done"
    assert calls["count"] == 1

    assert error_budget(0.999) == 0.001

    query, parameters = build_parameterized_query("abc")
    assert "?" in query
    assert parameters == ("abc",)

    print("All assertions passed.")


# =============================================================================
# 72. MAIN ENTRY POINT
# =============================================================================

def main() -> None:
    """
    Running this file executes the educational demonstrations.

    The random simulations intentionally produce different values between
    executions. Deterministic examples can be made reproducible by calling
    random.seed(...) before the relevant simulation.
    """
    random.seed(42)

    run_assertions()
    run_all_demos()


if __name__ == "__main__":
    main()
