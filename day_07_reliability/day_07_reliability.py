"""
Reliability Engineering: Faults, Failures, Recovery, and Fault Tolerance
=========================================================================

A self-contained educational script covering reliability fundamentals through
advanced implementation techniques.

The examples use only the Python standard library.
"""

from __future__ import annotations

import random
import statistics
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Generic, Optional, TypeVar


# =============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# =============================================================================

"""
Reliability is the probability that a system performs its intended function
without failure for a specified period under specified operating conditions.

Important distinctions:

Fault:
    A defect, abnormal condition, incorrect state, or underlying cause that can
    potentially lead to an error or failure.

Error:
    An incorrect internal system state caused by a fault.

Failure:
    Observable inability of a system to provide its required service.

Failure chain:

    FAULT  -->  ERROR  -->  FAILURE

Example:

    Fault:    Database connection configuration contains a wrong hostname.
    Error:    Application cannot establish a database connection.
    Failure:  Users receive failed requests.

A fault does not always cause a failure. A system may contain dormant faults
that remain hidden until particular conditions activate them.
"""


class ComponentState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"


@dataclass
class Component:
    """A simplified system component with a reliability-related state."""

    name: str
    state: ComponentState = ComponentState.HEALTHY

    def inject_fault(self) -> None:
        """Simulate a fault that may eventually produce failure."""
        if self.state == ComponentState.HEALTHY:
            self.state = ComponentState.DEGRADED

    def fail(self) -> None:
        """Transition to an observable failed state."""
        self.state = ComponentState.FAILED

    def recover(self) -> None:
        """Restore the component."""
        self.state = ComponentState.RECOVERING
        self.state = ComponentState.HEALTHY

    @property
    def available(self) -> bool:
        return self.state in {
            ComponentState.HEALTHY,
            ComponentState.DEGRADED,
        }


def demonstrate_fault_error_failure() -> None:
    print("\n=== Fault, Error, and Failure ===")

    database = Component("database")

    print(f"Initial state: {database.state.value}")

    # A fault may first cause degradation rather than immediate failure.
    database.inject_fault()
    print(f"After fault activation: {database.state.value}")

    # The component eventually enters an externally visible failed state.
    database.fail()
    print(f"After failure: {database.state.value}")

    database.recover()
    print(f"After recovery: {database.state.value}")


# =============================================================================
# 2. RELIABILITY, AVAILABILITY, AND MAINTAINABILITY
# =============================================================================

"""
Reliability:
    Probability of failure-free operation over time.

Availability:
    Probability that the system is operational when required.

Maintainability:
    Ability to restore a system efficiently after failure.

Common relationship:

    Availability = MTBF / (MTBF + MTTR)

where:

    MTBF = Mean Time Between Failures
    MTTR = Mean Time To Repair

This formula assumes a simplified repairable system with statistically stable
failure and repair behavior.
"""


def calculate_availability(mtbf_hours: float, mttr_hours: float) -> float:
    """Calculate steady-state availability for a simplified repairable system."""
    if mtbf_hours <= 0:
        raise ValueError("MTBF must be greater than zero.")
    if mttr_hours < 0:
        raise ValueError("MTTR cannot be negative.")

    return mtbf_hours / (mtbf_hours + mttr_hours)


def calculate_downtime_per_year(availability: float) -> float:
    """Estimate annual downtime in hours from an availability fraction."""
    if not 0 <= availability <= 1:
        raise ValueError("Availability must be between 0 and 1.")

    return (1 - availability) * 365 * 24


def demonstrate_availability() -> None:
    print("\n=== Reliability Metrics ===")

    mtbf = 1_000
    mttr = 2

    availability = calculate_availability(mtbf, mttr)
    downtime = calculate_downtime_per_year(availability)

    print(f"MTBF: {mtbf} hours")
    print(f"MTTR: {mttr} hours")
    print(f"Availability: {availability:.6%}")
    print(f"Estimated annual downtime: {downtime:.2f} hours")


# =============================================================================
# 3. RELIABILITY FUNCTIONS
# =============================================================================

"""
For a random failure time T:

Reliability function:

    R(t) = P(T > t)

Failure distribution function:

    F(t) = P(T <= t)

Relationship:

    R(t) = 1 - F(t)

For systems with a constant failure rate lambda:

    R(t) = exp(-lambda * t)

The exponential model is useful for demonstrating memoryless failures, although
real components may not always have constant failure rates.
"""

import math


def exponential_reliability(failure_rate: float, time_period: float) -> float:
    """Return reliability under a constant failure-rate exponential model."""
    if failure_rate < 0:
        raise ValueError("Failure rate cannot be negative.")
    if time_period < 0:
        raise ValueError("Time period cannot be negative.")

    return math.exp(-failure_rate * time_period)


def exponential_failure_probability(
    failure_rate: float,
    time_period: float,
) -> float:
    """Probability of at least one failure by the specified time."""
    return 1 - exponential_reliability(failure_rate, time_period)


def demonstrate_reliability_functions() -> None:
    print("\n=== Reliability Functions ===")

    failure_rate = 0.001
    hours = 100

    reliability = exponential_reliability(failure_rate, hours)
    failure_probability = exponential_failure_probability(
        failure_rate,
        hours,
    )

    print(f"Failure rate: {failure_rate} failures/hour")
    print(f"Time: {hours} hours")
    print(f"Reliability R(t): {reliability:.6f}")
    print(f"Failure probability F(t): {failure_probability:.6f}")


# =============================================================================
# 4. SERIES SYSTEMS
# =============================================================================

"""
A series system fails when any required component fails.

For independent components:

    R_series = R1 * R2 * ... * Rn

This explains why a distributed system with many dependencies may become less
reliable even when each dependency is individually highly reliable.
"""


def series_reliability(component_reliabilities: list[float]) -> float:
    """Calculate reliability for independent components arranged in series."""
    if not component_reliabilities:
        raise ValueError("At least one component reliability is required.")

    result = 1.0

    for reliability in component_reliabilities:
        if not 0 <= reliability <= 1:
            raise ValueError("Reliability values must be between 0 and 1.")
        result *= reliability

    return result


def demonstrate_series_system() -> None:
    print("\n=== Series System Reliability ===")

    reliabilities = [0.999, 0.998, 0.9995]
    result = series_reliability(reliabilities)

    print(f"Component reliabilities: {reliabilities}")
    print(f"Series reliability: {result:.6f}")


# =============================================================================
# 5. PARALLEL REDUNDANCY
# =============================================================================

"""
A parallel redundant system succeeds if at least one independent component works.

For independent components:

    R_parallel = 1 - product(1 - Ri)

Redundancy can improve reliability but introduces additional cost and complexity.

A critical limitation is the common-mode failure: multiple redundant components
can fail from the same underlying cause, such as:

    - power loss
    - shared network failure
    - software defect
    - incorrect deployment
    - common configuration
    - cloud-region outage
"""


def parallel_reliability(component_reliabilities: list[float]) -> float:
    """Calculate reliability when any component can successfully provide service."""
    if not component_reliabilities:
        raise ValueError("At least one component reliability is required.")

    probability_all_fail = 1.0

    for reliability in component_reliabilities:
        if not 0 <= reliability <= 1:
            raise ValueError("Reliability values must be between 0 and 1.")

        probability_all_fail *= 1 - reliability

    return 1 - probability_all_fail


def demonstrate_parallel_system() -> None:
    print("\n=== Parallel Redundancy ===")

    reliabilities = [0.99, 0.99]
    result = parallel_reliability(reliabilities)

    print(f"Component reliabilities: {reliabilities}")
    print(f"Parallel reliability: {result:.6f}")


# =============================================================================
# 6. K-OUT-OF-N REDUNDANCY
# =============================================================================

"""
A k-out-of-n system succeeds when at least k components work.

Examples:

    1-out-of-2:
        Either of two redundant servers can handle the service.

    2-out-of-3:
        A majority-voting architecture may require two agreeing components.

    3-out-of-5:
        A distributed system may require a quorum of three healthy replicas.
"""


def probability_at_least_k_successes(
    success_probability: float,
    total_components: int,
    minimum_successes: int,
) -> float:
    """Calculate a binomial probability for identical independent components."""
    if not 0 <= success_probability <= 1:
        raise ValueError("Success probability must be between 0 and 1.")
    if total_components <= 0:
        raise ValueError("Total components must be positive.")
    if not 1 <= minimum_successes <= total_components:
        raise ValueError("minimum_successes must be between 1 and total_components.")

    probability = 0.0

    for successful_components in range(
        minimum_successes,
        total_components + 1,
    ):
        combinations = math.comb(
            total_components,
            successful_components,
        )

        probability += (
            combinations
            * success_probability ** successful_components
            * (1 - success_probability)
            ** (total_components - successful_components)
        )

    return probability


def demonstrate_k_of_n() -> None:
    print("\n=== K-out-of-N Redundancy ===")

    probability = probability_at_least_k_successes(
        success_probability=0.9,
        total_components=3,
        minimum_successes=2,
    )

    print(f"Probability that at least 2 of 3 components work: {probability:.6f}")


# =============================================================================
# 7. FAILURE CLASSIFICATION
# =============================================================================

class FailureType(Enum):
    TRANSIENT = "transient"
    INTERMITTENT = "intermittent"
    PERMANENT = "permanent"
    SYSTEMATIC = "systematic"
    BYZANTINE = "byzantine"


@dataclass
class Failure:
    failure_type: FailureType
    message: str
    recoverable: bool


def demonstrate_failure_types() -> None:
    print("\n=== Failure Classification ===")

    failures = [
        Failure(
            FailureType.TRANSIENT,
            "Temporary network timeout.",
            True,
        ),
        Failure(
            FailureType.INTERMITTENT,
            "Connection fails occasionally.",
            True,
        ),
        Failure(
            FailureType.PERMANENT,
            "Storage device is unavailable.",
            False,
        ),
        Failure(
            FailureType.SYSTEMATIC,
            "Software defect causes invalid calculation.",
            False,
        ),
        Failure(
            FailureType.BYZANTINE,
            "Distributed node sends inconsistent responses.",
            False,
        ),
    ]

    for failure in failures:
        print(
            f"{failure.failure_type.value}: "
            f"{failure.message} "
            f"(recoverable={failure.recoverable})"
        )


# =============================================================================
# 8. EXCEPTIONS AS FAILURE SIGNALS
# =============================================================================

class TransientError(Exception):
    """Represents a temporary failure that may succeed when retried."""


class PermanentError(Exception):
    """Represents a failure that should not normally be retried."""


def unreliable_network_operation(
    transient_failure_probability: float = 0.3,
) -> str:
    """
    Simulate an operation that sometimes experiences a transient failure.

    Random simulation is used only for demonstration.
    """
    if random.random() < transient_failure_probability:
        raise TransientError("Temporary network failure.")

    return "Operation completed successfully."


def demonstrate_basic_error_handling() -> None:
    print("\n=== Failure Detection Through Exceptions ===")

    try:
        result = unreliable_network_operation()
        print(result)
    except TransientError as error:
        print(f"Detected transient failure: {error}")


# =============================================================================
# 9. RETRY MECHANISMS
# =============================================================================

"""
Retries are appropriate primarily for transient failures.

Blind retries can make outages worse through retry storms.

Important retry design factors:

    - maximum attempts
    - backoff delay
    - exponential growth
    - jitter
    - timeout
    - idempotency
    - failure classification
"""


def exponential_backoff_delay(
    attempt: int,
    base_delay: float = 0.1,
    maximum_delay: float = 5.0,
    jitter: bool = True,
) -> float:
    """Calculate exponential backoff with optional random jitter."""
    if attempt < 1:
        raise ValueError("Attempt number must start at 1.")

    delay = min(
        maximum_delay,
        base_delay * (2 ** (attempt - 1)),
    )

    if jitter:
        # Random jitter prevents many clients from retrying simultaneously.
        delay = random.uniform(0, delay)

    return delay


T = TypeVar("T")


def retry(
    max_attempts: int = 3,
    retry_exceptions: tuple[type[Exception], ...] = (TransientError,),
    base_delay: float = 0.1,
    maximum_delay: float = 1.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator implementing bounded retries with exponential backoff."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    def decorator(function: Callable[..., T]) -> Callable[..., T]:

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return function(*args, **kwargs)

                except retry_exceptions as error:
                    last_error = error

                    if attempt == max_attempts:
                        break

                    delay = exponential_backoff_delay(
                        attempt,
                        base_delay=base_delay,
                        maximum_delay=maximum_delay,
                        jitter=True,
                    )

                    print(
                        f"Attempt {attempt} failed: {error}. "
                        f"Retrying after {delay:.3f} seconds."
                    )

                    time.sleep(delay)

            assert last_error is not None
            raise last_error

        return wrapper

    return decorator


@retry(max_attempts=4)
def flaky_service_call() -> str:
    """Demonstrate a retryable operation."""
    return unreliable_network_operation(
        transient_failure_probability=0.5,
    )


def demonstrate_retry() -> None:
    print("\n=== Retry With Exponential Backoff ===")

    try:
        print(flaky_service_call())
    except TransientError as error:
        print(f"Operation failed after retries: {error}")


# =============================================================================
# 10. IDEMPOTENCY
# =============================================================================

"""
An operation is idempotent when repeating it produces the same effective result
as performing it once.

Examples:

    Idempotent:
        Set account status to "active".

    Potentially non-idempotent:
        Add 100 units to account balance.

Retries of non-idempotent operations can create duplicate effects.
"""


class IdempotentPaymentProcessor:
    """
    Demonstrates idempotency keys.

    A repeated request with the same key returns the original result instead of
    charging again.
    """

    def __init__(self) -> None:
        self._processed_requests: dict[str, float] = {}

    def charge(
        self,
        idempotency_key: str,
        amount: float,
    ) -> float:
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        if idempotency_key in self._processed_requests:
            print("Duplicate request detected. Returning previous result.")
            return self._processed_requests[idempotency_key]

        self._processed_requests[idempotency_key] = amount
        print("Payment processed once.")
        return amount


def demonstrate_idempotency() -> None:
    print("\n=== Idempotency ===")

    processor = IdempotentPaymentProcessor()

    first = processor.charge("payment-001", 100.0)
    second = processor.charge("payment-001", 100.0)

    print(f"First result: {first}")
    print(f"Repeated result: {second}")


# =============================================================================
# 11. TIMEOUTS
# =============================================================================

"""
Timeouts prevent indefinite waiting.

Without timeouts, resource exhaustion can occur:

    - threads remain blocked
    - connections remain occupied
    - request queues grow
    - upstream failures cascade

Timeout selection involves a trade-off:

    Too short:
        Healthy slow requests may be incorrectly abandoned.

    Too long:
        Failed requests consume resources for excessive periods.
"""


class TimeoutErrorForDemo(Exception):
    """Custom timeout exception for demonstration."""


def run_with_timeout(
    function: Callable[..., T],
    timeout_seconds: float,
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Run a function in a thread and wait for a bounded amount of time.

    Important limitation:
    Python threads cannot generally be forcefully terminated safely. If the
    timeout occurs, the underlying function may continue running.
    """
    if timeout_seconds <= 0:
        raise ValueError("Timeout must be greater than zero.")

    result_container: dict[str, Any] = {}
    error_container: dict[str, Exception] = {}

    def target() -> None:
        try:
            result_container["result"] = function(*args, **kwargs)
        except Exception as error:
            error_container["error"] = error

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise TimeoutErrorForDemo(
            f"Operation exceeded {timeout_seconds} seconds."
        )

    if "error" in error_container:
        raise error_container["error"]

    return result_container["result"]


def slow_operation(duration: float) -> str:
    """Simulate a slow dependency."""
    time.sleep(duration)
    return "Slow operation completed."


def demonstrate_timeout() -> None:
    print("\n=== Timeout ===")

    try:
        result = run_with_timeout(
            slow_operation,
            0.2,
            0.5,
        )
        print(result)

    except TimeoutErrorForDemo as error:
        print(f"Timeout detected: {error}")


# =============================================================================
# 12. CIRCUIT BREAKER
# =============================================================================

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker rejects requests."""


@dataclass
class CircuitBreaker:
    """
    Simplified circuit breaker.

    CLOSED:
        Requests are allowed.

    OPEN:
        Requests are rejected immediately.

    HALF_OPEN:
        A limited recovery attempt is allowed after the recovery timeout.
    """

    failure_threshold: int = 3
    recovery_timeout: float = 2.0
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: Optional[float] = None

    def before_call(self) -> None:
        if self.state == CircuitState.OPEN:
            assert self.opened_at is not None

            elapsed = time.monotonic() - self.opened_at

            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError(
                    "Circuit breaker is open."
                )

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1

        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()

    def call(
        self,
        function: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        self.before_call()

        try:
            result = function(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise

        self.record_success()
        return result


def always_failing_service() -> str:
    raise TransientError("Dependency is unavailable.")


def demonstrate_circuit_breaker() -> None:
    print("\n=== Circuit Breaker ===")

    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=0.5,
    )

    for attempt in range(1, 5):
        try:
            breaker.call(always_failing_service)
        except Exception as error:
            print(
                f"Attempt {attempt}: {type(error).__name__}, "
                f"state={breaker.state.value}"
            )


# =============================================================================
# 13. BULKHEAD ISOLATION
# =============================================================================

"""
Bulkheads isolate failures into separate resource pools.

The term comes from ship design: compartments limit flooding.

In software systems, isolation may separate:

    - thread pools
    - connection pools
    - queues
    - processes
    - services
    - tenants

Without isolation, one overloaded dependency may consume all resources.
"""


class BulkheadFullError(Exception):
    """Raised when a bulkhead has no remaining capacity."""


@dataclass
class Bulkhead:
    """Concurrency limiter using a bounded semaphore."""

    maximum_concurrent_operations: int
    _semaphore: threading.BoundedSemaphore = field(init=False)

    def __post_init__(self) -> None:
        if self.maximum_concurrent_operations <= 0:
            raise ValueError(
                "maximum_concurrent_operations must be positive."
            )

        self._semaphore = threading.BoundedSemaphore(
            self.maximum_concurrent_operations
        )

    def execute(
        self,
        function: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        acquired = self._semaphore.acquire(blocking=False)

        if not acquired:
            raise BulkheadFullError(
                "Bulkhead capacity has been reached."
            )

        try:
            return function(*args, **kwargs)
        finally:
            self._semaphore.release()


# =============================================================================
# 14. GRACEFUL DEGRADATION
# =============================================================================

@dataclass
class Product:
    product_id: int
    name: str


class RecommendationService:
    """Simulates an optional dependency."""

    def get_recommendations(
        self,
        product_id: int,
    ) -> list[str]:
        if random.random() < 0.7:
            raise TransientError(
                "Recommendation service unavailable."
            )

        return [
            f"Recommendation for product {product_id}"
        ]


def render_product_page(
    product: Product,
    recommendation_service: RecommendationService,
) -> dict[str, Any]:
    """
    Return core functionality even if optional functionality fails.
    """
    response: dict[str, Any] = {
        "product": product.name,
        "recommendations": [],
        "recommendations_available": False,
    }

    try:
        response["recommendations"] = (
            recommendation_service.get_recommendations(
                product.product_id
            )
        )
        response["recommendations_available"] = True

    except TransientError:
        # Graceful degradation preserves the essential product page.
        pass

    return response


def demonstrate_graceful_degradation() -> None:
    print("\n=== Graceful Degradation ===")

    page = render_product_page(
        Product(1, "Reliable Server"),
        RecommendationService(),
    )

    print(page)


# =============================================================================
# 15. FAILOVER
# =============================================================================

@dataclass
class ServiceEndpoint:
    name: str
    available: bool = True

    def request(self) -> str:
        if not self.available:
            raise TransientError(
                f"{self.name} is unavailable."
            )

        return f"Response from {self.name}"


def failover_request(
    endpoints: list[ServiceEndpoint],
) -> str:
    """
    Attempt endpoints sequentially.

    Ordering matters. In production systems, routing may use health checks,
    load balancing, latency measurements, geographic proximity, and capacity.
    """
    if not endpoints:
        raise ValueError("At least one endpoint is required.")

    errors: list[str] = []

    for endpoint in endpoints:
        try:
            return endpoint.request()
        except TransientError as error:
            errors.append(str(error))

    raise TransientError(
        "All endpoints failed: " + "; ".join(errors)
    )


def demonstrate_failover() -> None:
    print("\n=== Failover ===")

    endpoints = [
        ServiceEndpoint("primary", available=False),
        ServiceEndpoint("secondary", available=True),
    ]

    print(failover_request(endpoints))


# =============================================================================
# 16. HEALTH CHECKS
# =============================================================================

class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    name: str
    check: Callable[[], bool]


def evaluate_health_checks(
    checks: list[HealthCheck],
) -> dict[str, HealthStatus]:
    """Run multiple health checks."""
    results: dict[str, HealthStatus] = {}

    for health_check in checks:
        try:
            healthy = health_check.check()
        except Exception:
            healthy = False

        results[health_check.name] = (
            HealthStatus.HEALTHY
            if healthy
            else HealthStatus.UNHEALTHY
        )

    return results


def demonstrate_health_checks() -> None:
    print("\n=== Health Checks ===")

    checks = [
        HealthCheck(
            "application",
            lambda: True,
        ),
        HealthCheck(
            "database",
            lambda: False,
        ),
    ]

    results = evaluate_health_checks(checks)

    for name, status in results.items():
        print(f"{name}: {status.value}")


# =============================================================================
# 17. HEARTBEATS
# =============================================================================

@dataclass
class HeartbeatMonitor:
    timeout_seconds: float
    last_heartbeat: Optional[float] = None

    def receive_heartbeat(self) -> None:
        self.last_heartbeat = time.monotonic()

    def is_alive(self) -> bool:
        if self.last_heartbeat is None:
            return False

        return (
            time.monotonic() - self.last_heartbeat
            <= self.timeout_seconds
        )


def demonstrate_heartbeat() -> None:
    print("\n=== Heartbeat Monitoring ===")

    monitor = HeartbeatMonitor(timeout_seconds=1.0)

    print(f"Initially alive: {monitor.is_alive()}")

    monitor.receive_heartbeat()

    print(f"After heartbeat: {monitor.is_alive()}")


# =============================================================================
# 18. CHECKPOINTING AND RECOVERY
# =============================================================================

@dataclass
class Checkpoint:
    sequence_number: int
    state: dict[str, Any]


class CheckpointedProcessor:
    """
    Processes values while periodically storing recoverable state.

    A real production system would store checkpoints durably.
    """

    def __init__(self) -> None:
        self.total = 0
        self.sequence_number = 0
        self.checkpoints: list[Checkpoint] = []

    def process(self, value: int) -> None:
        self.total += value
        self.sequence_number += 1

    def create_checkpoint(self) -> Checkpoint:
        checkpoint = Checkpoint(
            sequence_number=self.sequence_number,
            state={
                "total": self.total,
            },
        )

        self.checkpoints.append(checkpoint)
        return checkpoint

    def restore(self, checkpoint: Checkpoint) -> None:
        self.sequence_number = checkpoint.sequence_number
        self.total = checkpoint.state["total"]


def demonstrate_checkpoint_recovery() -> None:
    print("\n=== Checkpoint Recovery ===")

    processor = CheckpointedProcessor()

    processor.process(10)
    processor.process(20)

    checkpoint = processor.create_checkpoint()

    processor.process(100)

    print(f"State before recovery: total={processor.total}")

    processor.restore(checkpoint)

    print(f"State after recovery: total={processor.total}")


# =============================================================================
# 19. TRANSACTIONS AND ATOMICITY
# =============================================================================

class SimpleAccount:
    """A small account model used to demonstrate rollback."""

    def __init__(self, name: str, balance: float) -> None:
        self.name = name
        self.balance = balance

    def __repr__(self) -> str:
        return (
            f"SimpleAccount(name={self.name!r}, "
            f"balance={self.balance})"
        )


def transfer_money(
    source: SimpleAccount,
    destination: SimpleAccount,
    amount: float,
    simulate_failure: bool = False,
) -> None:
    """
    Demonstrate compensating rollback.

    Production systems often use database transactions rather than manually
    restoring in-memory state.
    """
    if amount <= 0:
        raise ValueError("Transfer amount must be positive.")

    if source.balance < amount:
        raise ValueError("Insufficient funds.")

    original_source_balance = source.balance
    original_destination_balance = destination.balance

    try:
        source.balance -= amount

        if simulate_failure:
            raise RuntimeError(
                "Failure occurred during transfer."
            )

        destination.balance += amount

    except Exception:
        source.balance = original_source_balance
        destination.balance = original_destination_balance
        raise


def demonstrate_transaction_rollback() -> None:
    print("\n=== Atomicity and Recovery ===")

    source = SimpleAccount("Alice", 1_000)
    destination = SimpleAccount("Bob", 500)

    try:
        transfer_money(
            source,
            destination,
            100,
            simulate_failure=True,
        )
    except RuntimeError as error:
        print(f"Transaction failed: {error}")

    print(source)
    print(destination)


# =============================================================================
# 20. REPLICATION AND QUORUMS
# =============================================================================

@dataclass
class Replica:
    name: str
    available: bool = True
    data: dict[str, Any] = field(default_factory=dict)


class ReplicatedStore:
    """
    Simplified replicated data store.

    Demonstrates write quorum logic but does not implement a complete distributed
    consensus protocol.
    """

    def __init__(
        self,
        replicas: list[Replica],
        write_quorum: int,
    ) -> None:
        if not replicas:
            raise ValueError("At least one replica is required.")

        if not 1 <= write_quorum <= len(replicas):
            raise ValueError("Invalid write quorum.")

        self.replicas = replicas
        self.write_quorum = write_quorum

    def write(
        self,
        key: str,
        value: Any,
    ) -> int:
        successful_writes = 0

        for replica in self.replicas:
            if replica.available:
                replica.data[key] = value
                successful_writes += 1

        if successful_writes < self.write_quorum:
            raise TransientError(
                f"Write quorum not reached. "
                f"Successful writes: {successful_writes}"
            )

        return successful_writes


def demonstrate_replication() -> None:
    print("\n=== Replication and Quorum ===")

    store = ReplicatedStore(
        replicas=[
            Replica("replica-1", available=True),
            Replica("replica-2", available=True),
            Replica("replica-3", available=False),
        ],
        write_quorum=2,
    )

    writes = store.write("status", "active")

    print(f"Successful replica writes: {writes}")


# =============================================================================
# 21. N-VERSION REDUNDANCY
# =============================================================================

"""
N-version redundancy uses independently implemented versions of functionality.

The purpose is to reduce systematic common-mode failures.

Important limitation:
Independence is difficult to achieve. Teams can misunderstand requirements in
the same way, use identical assumptions, or inherit the same specification bug.
"""


def implementation_a(value: int) -> int:
    return value * value


def implementation_b(value: int) -> int:
    return pow(value, 2)


def majority_vote(
    results: list[Any],
) -> Any:
    """
    Return the value appearing most frequently.

    Raises an error when there is no strict majority.
    """
    if not results:
        raise ValueError("At least one result is required.")

    counts: dict[Any, int] = {}

    for result in results:
        counts[result] = counts.get(result, 0) + 1

    winner, count = max(
        counts.items(),
        key=lambda item: item[1],
    )

    if count <= len(results) // 2:
        raise ValueError("No strict majority.")

    return winner


def demonstrate_n_version_redundancy() -> None:
    print("\n=== N-Version Redundancy ===")

    value = 5

    results = [
        implementation_a(value),
        implementation_b(value),
        implementation_a(value),
    ]

    print(f"Independent results: {results}")
    print(f"Majority result: {majority_vote(results)}")


# =============================================================================
# 22. FAILURE DETECTION VERSUS FAILURE PREDICTION
# =============================================================================

@dataclass
class MetricWindow:
    values: list[float]

    def mean(self) -> float:
        if not self.values:
            raise ValueError("Metric window is empty.")

        return statistics.mean(self.values)

    def anomaly_score(
        self,
        current_value: float,
    ) -> float:
        """
        Simplified z-score anomaly detection.

        This is illustrative rather than a complete production monitoring system.
        """
        if len(self.values) < 2:
            raise ValueError(
                "At least two historical values are required."
            )

        deviation = statistics.pstdev(self.values)

        if deviation == 0:
            return (
                0.0
                if current_value == self.mean()
                else float("inf")
            )

        return abs(
            (current_value - self.mean())
            / deviation
        )


def demonstrate_anomaly_detection() -> None:
    print("\n=== Failure Detection and Anomalies ===")

    latency_history = MetricWindow(
        [100, 105, 98, 102, 101, 99]
    )

    current_latency = 300

    score = latency_history.anomaly_score(
        current_latency
    )

    print(f"Current latency: {current_latency} ms")
    print(f"Anomaly score: {score:.2f}")


# =============================================================================
# 23. OBSERVABILITY AND ERROR BUDGETS
# =============================================================================

@dataclass
class ServiceLevelObjective:
    """
    Simplified availability SLO.

    target:
        Required fraction of successful events.
    """

    target: float

    def __post_init__(self) -> None:
        if not 0 < self.target <= 1:
            raise ValueError(
                "SLO target must be greater than 0 and at most 1."
            )

    def error_budget(
        self,
        total_requests: int,
    ) -> float:
        if total_requests < 0:
            raise ValueError(
                "Total requests cannot be negative."
            )

        return total_requests * (1 - self.target)

    def compliance(
        self,
        successful_requests: int,
        total_requests: int,
    ) -> float:
        if total_requests <= 0:
            raise ValueError(
                "Total requests must be positive."
            )

        if not 0 <= successful_requests <= total_requests:
            raise ValueError(
                "Invalid successful request count."
            )

        return successful_requests / total_requests


def demonstrate_error_budget() -> None:
    print("\n=== SLO and Error Budget ===")

    slo = ServiceLevelObjective(target=0.999)

    total_requests = 1_000_000
    successful_requests = 998_900

    compliance = slo.compliance(
        successful_requests,
        total_requests,
    )

    budget = slo.error_budget(total_requests)

    failures = total_requests - successful_requests

    print(f"Availability target: {slo.target:.3%}")
    print(f"Observed availability: {compliance:.3%}")
    print(f"Permitted failures: {budget:.0f}")
    print(f"Observed failures: {failures}")


# =============================================================================
# 24. FAULT INJECTION
# =============================================================================

"""
Fault injection deliberately introduces failures to test system behavior.

Examples:

    - latency injection
    - connection failures
    - process termination
    - unavailable replicas
    - malformed messages
    - disk exhaustion

Controlled fault injection helps verify that recovery mechanisms actually work.
"""


class FaultInjector:
    """Controlled probabilistic fault injection for testing."""

    def __init__(
        self,
        failure_probability: float,
    ) -> None:
        if not 0 <= failure_probability <= 1:
            raise ValueError(
                "Failure probability must be between 0 and 1."
            )

        self.failure_probability = failure_probability

    def maybe_fail(self) -> None:
        if random.random() < self.failure_probability:
            raise TransientError(
                "Injected transient fault."
            )


def demonstrate_fault_injection() -> None:
    print("\n=== Fault Injection ===")

    injector = FaultInjector(0.5)

    for attempt in range(5):
        try:
            injector.maybe_fail()
            print(f"Attempt {attempt + 1}: success")
        except TransientError:
            print(f"Attempt {attempt + 1}: injected failure")


# =============================================================================
# 25. MONTE CARLO RELIABILITY SIMULATION
# =============================================================================

def simulate_series_system(
    component_failure_probabilities: list[float],
    trials: int,
) -> float:
    """
    Estimate series-system reliability using Monte Carlo simulation.

    A trial succeeds only when every component succeeds.
    """
    if trials <= 0:
        raise ValueError("Trials must be positive.")

    successes = 0

    for _ in range(trials):
        system_success = True

        for failure_probability in (
            component_failure_probabilities
        ):
            if not 0 <= failure_probability <= 1:
                raise ValueError(
                    "Failure probabilities must be between 0 and 1."
                )

            if random.random() < failure_probability:
                system_success = False
                break

        if system_success:
            successes += 1

    return successes / trials


def demonstrate_monte_carlo() -> None:
    print("\n=== Monte Carlo Reliability Simulation ===")

    failure_probabilities = [
        0.01,
        0.02,
        0.005,
    ]

    estimated_reliability = simulate_series_system(
        failure_probabilities,
        trials=10_000,
    )

    theoretical_reliability = series_reliability(
        [
            1 - probability
            for probability in failure_probabilities
        ]
    )

    print(
        f"Estimated reliability: "
        f"{estimated_reliability:.4f}"
    )

    print(
        f"Theoretical reliability: "
        f"{theoretical_reliability:.4f}"
    )


# =============================================================================
# 26. DEPENDENCY FAILURE AND CASCADING FAILURE
# =============================================================================

@dataclass
class Dependency:
    name: str
    capacity: int
    active_requests: int = 0
    healthy: bool = True

    def acquire(self) -> None:
        if not self.healthy:
            raise TransientError(
                f"{self.name} is unhealthy."
            )

        if self.active_requests >= self.capacity:
            raise TransientError(
                f"{self.name} is overloaded."
            )

        self.active_requests += 1

    def release(self) -> None:
        if self.active_requests > 0:
            self.active_requests -= 1


def demonstrate_cascading_failure_protection() -> None:
    print("\n=== Cascading Failure Protection ===")

    dependency = Dependency(
        name="database",
        capacity=2,
    )

    try:
        dependency.acquire()
        dependency.acquire()

        # This request exceeds capacity.
        dependency.acquire()

    except TransientError as error:
        print(f"Overload detected: {error}")

    finally:
        dependency.release()
        dependency.release()

    print(
        f"Active requests after cleanup: "
        f"{dependency.active_requests}"
    )


# =============================================================================
# 27. RECOVERY OBJECTIVES
# =============================================================================

"""
Recovery Point Objective (RPO):
    Maximum acceptable amount of data loss measured in time.

Recovery Time Objective (RTO):
    Maximum acceptable time required to restore service.

Example:

    RPO = 5 minutes:
        Losing up to five minutes of data is acceptable.

    RTO = 30 minutes:
        Service must be restored within thirty minutes.

These objectives influence:

    - backup frequency
    - replication
    - recovery architecture
    - storage cost
    - operational complexity
"""


@dataclass
class RecoveryObjectives:
    rpo_minutes: float
    rto_minutes: float

    def validate(self) -> None:
        if self.rpo_minutes < 0:
            raise ValueError("RPO cannot be negative.")

        if self.rto_minutes <= 0:
            raise ValueError(
                "RTO must be greater than zero."
            )


def demonstrate_recovery_objectives() -> None:
    print("\n=== Recovery Objectives ===")

    objectives = RecoveryObjectives(
        rpo_minutes=5,
        rto_minutes=30,
    )

    objectives.validate()

    print(
        f"RPO: {objectives.rpo_minutes} minutes"
    )
    print(
        f"RTO: {objectives.rto_minutes} minutes"
    )


# =============================================================================
# 28. DEFENSIVE INPUT VALIDATION
# =============================================================================

def divide_reliability_measurement(
    successful_events: int,
    total_events: int,
) -> float:
    """
    Demonstrates validation of edge cases.

    Division by zero and invalid counts should be detected before producing an
    unreliable metric.
    """
    if total_events <= 0:
        raise ValueError(
            "Total events must be greater than zero."
        )

    if successful_events < 0:
        raise ValueError(
            "Successful events cannot be negative."
        )

    if successful_events > total_events:
        raise ValueError(
            "Successful events cannot exceed total events."
        )

    return successful_events / total_events


def demonstrate_validation() -> None:
    print("\n=== Defensive Validation ===")

    print(
        divide_reliability_measurement(
            successful_events=99,
            total_events=100,
        )
    )

    try:
        divide_reliability_measurement(
            successful_events=10,
            total_events=0,
        )
    except ValueError as error:
        print(f"Invalid metric prevented: {error}")


# =============================================================================
# 29. SIMPLE TESTING OF RELIABILITY LOGIC
# =============================================================================

def run_basic_tests() -> None:
    """
    Small deterministic tests using assertions.

    Assertions are suitable for demonstrations. Production projects commonly use
    structured test frameworks and separate test suites.
    """
    print("\n=== Basic Reliability Tests ===")

    assert calculate_availability(100, 0) == 1.0

    assert math.isclose(
        series_reliability([0.9, 0.8]),
        0.72,
    )

    assert math.isclose(
        parallel_reliability([0.9, 0.9]),
        0.99,
    )

    assert math.isclose(
        probability_at_least_k_successes(
            success_probability=1.0,
            total_components=3,
            minimum_successes=2,
        ),
        1.0,
    )

    assert majority_vote(
        [1, 1, 2]
    ) == 1

    processor = IdempotentPaymentProcessor()

    assert processor.charge(
        "test-key",
        10,
    ) == 10

    assert processor.charge(
        "test-key",
        10,
    ) == 10

    print("All deterministic tests passed.")


# =============================================================================
# 30. INTEGRATED RESILIENT SERVICE
# =============================================================================

@dataclass
class ResilientService:
    """
    Combines several reliability patterns:

        - timeout
        - retry
        - circuit breaker
        - fallback
        - graceful degradation

    This is an educational composition rather than a production framework.
    """

    primary_service: Callable[[], str]
    fallback_service: Callable[[], str]
    circuit_breaker: CircuitBreaker

    def request(self) -> str:
        try:
            return self.circuit_breaker.call(
                self._retrying_primary_request
            )

        except (
            TransientError,
            TimeoutErrorForDemo,
            CircuitBreakerOpenError,
        ) as error:
            print(
                f"Primary path unavailable: {error}. "
                f"Using fallback."
            )

            return self.fallback_service()

    def _retrying_primary_request(self) -> str:
        max_attempts = 3
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return run_with_timeout(
                    self.primary_service,
                    0.3,
                )

            except (
                TransientError,
                TimeoutErrorForDemo,
            ) as error:
                last_error = error

                if attempt < max_attempts:
                    delay = exponential_backoff_delay(
                        attempt,
                        base_delay=0.05,
                        maximum_delay=0.2,
                    )

                    time.sleep(delay)

        assert last_error is not None
        raise last_error


def demonstrate_integrated_resilience() -> None:
    print("\n=== Integrated Resilient Service ===")

    failure_counter = {"calls": 0}

    def primary() -> str:
        failure_counter["calls"] += 1

        if failure_counter["calls"] < 3:
            raise TransientError(
                "Primary dependency temporarily failed."
            )

        return "Primary response"

    def fallback() -> str:
        return "Fallback response"

    service = ResilientService(
        primary_service=primary,
        fallback_service=fallback,
        circuit_breaker=CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=1,
        ),
    )

    print(service.request())


# =============================================================================
# 31. COMMON RELIABILITY ANTI-PATTERNS
# =============================================================================

def demonstrate_common_mistakes() -> None:
    print("\n=== Common Reliability Mistakes ===")

    mistakes = [
        "Retrying permanent failures.",
        "Using retries without exponential backoff.",
        "Retrying non-idempotent operations without deduplication.",
        "Using a single shared dependency as a hidden single point of failure.",
        "Adding redundancy without addressing common-mode failures.",
        "Using health checks that verify only process existence.",
        "Setting timeouts without considering downstream latency.",
        "Allowing unlimited queues and unbounded resource consumption.",
        "Suppressing exceptions without logging or monitoring them.",
        "Assuming backups are recoverable without restoration testing.",
        "Failing over automatically without validating data consistency.",
        "Treating availability as identical to reliability.",
    ]

    for number, mistake in enumerate(
        mistakes,
        start=1,
    ):
        print(f"{number}. {mistake}")


# =============================================================================
# 32. PERFORMANCE AND RELIABILITY TRADE-OFFS
# =============================================================================

def demonstrate_tradeoffs() -> None:
    print("\n=== Reliability Trade-Offs ===")

    tradeoffs = {
        "Retries": (
            "Improve transient-failure tolerance but can increase load."
        ),
        "Replication": (
            "Improves availability but increases consistency complexity."
        ),
        "Timeouts": (
            "Protect resources but can reject slow successful operations."
        ),
        "Circuit breakers": (
            "Prevent cascading failures but can temporarily reject recoverable requests."
        ),
        "Redundancy": (
            "Improves fault tolerance but increases cost and operational complexity."
        ),
        "Synchronous replication": (
            "Can reduce data loss but may increase latency."
        ),
        "Asynchronous replication": (
            "Improves write performance but can increase data-loss exposure."
        ),
    }

    for technique, explanation in tradeoffs.items():
        print(f"{technique}: {explanation}")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main() -> None:
    """
    Execute demonstrations in a progression from fundamentals to advanced
    resilience patterns.
    """
    random.seed(42)

    print("=" * 72)
    print("RELIABILITY ENGINEERING")
    print("Faults, Failures, Recovery, and Fault Tolerance")
    print("=" * 72)

    demonstrate_fault_error_failure()
    demonstrate_availability()
    demonstrate_reliability_functions()
    demonstrate_series_system()
    demonstrate_parallel_system()
    demonstrate_k_of_n()
    demonstrate_failure_types()
    demonstrate_basic_error_handling()
    demonstrate_retry()
    demonstrate_idempotency()
    demonstrate_timeout()
    demonstrate_circuit_breaker()
    demonstrate_graceful_degradation()
    demonstrate_failover()
    demonstrate_health_checks()
    demonstrate_heartbeat()
    demonstrate_checkpoint_recovery()
    demonstrate_transaction_rollback()
    demonstrate_replication()
    demonstrate_n_version_redundancy()
    demonstrate_anomaly_detection()
    demonstrate_error_budget()
    demonstrate_fault_injection()
    demonstrate_monte_carlo()
    demonstrate_cascading_failure_protection()
    demonstrate_recovery_objectives()
    demonstrate_validation()
    run_basic_tests()
    demonstrate_integrated_resilience()
    demonstrate_common_mistakes()
    demonstrate_tradeoffs()

    print("\n" + "=" * 72)
    print("Reliability demonstrations completed.")
    print("=" * 72)


if __name__ == "__main__":
    main()
