#!/usr/bin/env python3
"""
Circuit Breaker: Failure Isolation and Graceful Degradation

Implements:
- CLOSED, OPEN, and HALF_OPEN states
- Consecutive failure threshold
- Recovery timeout
- Single half-open recovery probe
- Thread-safe execution
- Configurable exception handling
- Fallback responses
- Failure metrics and event history
- Service isolation and graceful degradation
- Retry-safe demonstration and automated assertions

Python 3.10+
"""

from __future__ import annotations

import logging
import threading
import time

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TypeVar


T = TypeVar("T")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(RuntimeError):
    """Raised when execution is rejected by an open circuit."""


class CircuitConfigurationError(ValueError):
    """Raised when circuit configuration is invalid."""


@dataclass(frozen=True)
class CircuitConfig:
    failure_threshold: int = 3
    recovery_timeout: float = 2.0
    half_open_max_calls: int = 1
    history_size: int = 100

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise CircuitConfigurationError(
                "Failure threshold must be positive."
            )
        if self.recovery_timeout <= 0:
            raise CircuitConfigurationError(
                "Recovery timeout must be positive."
            )
        if self.half_open_max_calls < 1:
            raise CircuitConfigurationError(
                "Half-open call limit must be positive."
            )
        if self.history_size < 1:
            raise CircuitConfigurationError(
                "History size must be positive."
            )


@dataclass
class CircuitMetrics:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    fallback_calls: int = 0
    state_transitions: int = 0

    @property
    def success_rate(self) -> float:
        completed = self.successful_calls + self.failed_calls
        if completed == 0:
            return 0.0
        return self.successful_calls / completed * 100


@dataclass(frozen=True)
class CircuitEvent:
    timestamp: float
    event: str
    state: CircuitState
    details: str


class CircuitBreaker:
    """
    Thread-safe circuit breaker.

    CLOSED:
        Calls reach the dependency. Consecutive failures are counted.

    OPEN:
        Calls are rejected immediately until recovery_timeout expires.

    HALF_OPEN:
        Limited recovery probes are permitted. A successful probe closes
        the circuit; a failed probe reopens it.

    The lock protects state transitions and half-open probe admission.
    Dependency execution occurs outside the lock.
    """

    def __init__(
        self,
        name: str,
        config: CircuitConfig,
        expected_exceptions: tuple[type[Exception], ...] = (
            Exception,
        ),
    ) -> None:
        if not name.strip():
            raise ValueError("Circuit name cannot be empty.")

        self.name = name
        self.config = config
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: Optional[float] = None
        self._half_open_inflight = 0

        self._lock = threading.RLock()
        self.metrics = CircuitMetrics()
        self.history: deque[CircuitEvent] = deque(
            maxlen=config.history_size
        )

        self._record("INITIALIZED", "Circuit created.")

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def _record(self, event: str, details: str) -> None:
        self.history.append(
            CircuitEvent(
                timestamp=time.time(),
                event=event,
                state=self._state,
                details=details,
            )
        )

    def _transition(self, new_state: CircuitState, reason: str) -> None:
        if self._state == new_state:
            return

        previous = self._state
        self._state = new_state
        self.metrics.state_transitions += 1

        self._record(
            "STATE_TRANSITION",
            f"{previous.value} -> {new_state.value}: {reason}",
        )

        logging.info(
            "%s: %s -> %s (%s)",
            self.name,
            previous.value,
            new_state.value,
            reason,
        )

    def _refresh_state(self) -> None:
        if self._state != CircuitState.OPEN:
            return

        assert self._opened_at is not None

        elapsed = time.monotonic() - self._opened_at

        if elapsed >= self.config.recovery_timeout:
            self._half_open_inflight = 0
            self._transition(
                CircuitState.HALF_OPEN,
                "Recovery timeout elapsed.",
            )

    def _acquire_permission(self) -> CircuitState:
        with self._lock:
            self._refresh_state()

            if self._state == CircuitState.OPEN:
                self.metrics.rejected_calls += 1
                self._record(
                    "CALL_REJECTED",
                    "Circuit remains open.",
                )
                raise CircuitOpenError(
                    f"{self.name} circuit is OPEN."
                )

            if self._state == CircuitState.HALF_OPEN:
                if (
                    self._half_open_inflight
                    >= self.config.half_open_max_calls
                ):
                    self.metrics.rejected_calls += 1
                    self._record(
                        "PROBE_REJECTED",
                        "Half-open probe capacity exhausted.",
                    )
                    raise CircuitOpenError(
                        f"{self.name} recovery probe capacity exhausted."
                    )

                self._half_open_inflight += 1
                self._record(
                    "RECOVERY_PROBE",
                    "Half-open probe admitted.",
                )

            self.metrics.total_calls += 1
            return self._state

    def _on_success(self, admitted_state: CircuitState) -> None:
        with self._lock:
            self.metrics.successful_calls += 1

            if admitted_state == CircuitState.HALF_OPEN:
                self._half_open_inflight -= 1
                self._failure_count = 0
                self._opened_at = None

                self._transition(
                    CircuitState.CLOSED,
                    "Recovery probe succeeded.",
                )

            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

            self._record("CALL_SUCCESS", "Dependency responded successfully.")

    def _on_failure(
        self,
        admitted_state: CircuitState,
        error: Exception,
    ) -> None:
        with self._lock:
            self.metrics.failed_calls += 1

            if admitted_state == CircuitState.HALF_OPEN:
                self._half_open_inflight -= 1
                self._open("Recovery probe failed.")
            elif (
                admitted_state == CircuitState.CLOSED
                and self._state == CircuitState.CLOSED
            ):
                self._failure_count += 1

                if self._failure_count >= self.config.failure_threshold:
                    self._open("Failure threshold reached.")

            self._record(
                "CALL_FAILURE",
                f"{type(error).__name__}: {error}",
            )

    def _open(self, reason: str) -> None:
        self._opened_at = time.monotonic()
        self._half_open_inflight = 0
        self._transition(CircuitState.OPEN, reason)

    def execute(
        self,
        operation: Callable[[], T],
        fallback: Optional[Callable[[], T]] = None,
    ) -> T:
        """
        Execute an operation with optional fallback.

        Only configured exceptions affect circuit health.
        Unexpected BaseException subclasses are not swallowed.
        """
        admitted_state: Optional[CircuitState] = None

        try:
            admitted_state = self._acquire_permission()
            result = operation()
            self._on_success(admitted_state)
            return result

        except CircuitOpenError:
            if fallback is not None:
                with self._lock:
                    self.metrics.fallback_calls += 1
                return fallback()
            raise

        except self.expected_exceptions as error:
            if admitted_state is None:
                raise

            self._on_failure(admitted_state, error)

            if fallback is not None:
                with self._lock:
                    self.metrics.fallback_calls += 1
                return fallback()

            raise

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "consecutive_failures": self._failure_count,
                "metrics": {
                    "total_calls": self.metrics.total_calls,
                    "successful_calls": self.metrics.successful_calls,
                    "failed_calls": self.metrics.failed_calls,
                    "rejected_calls": self.metrics.rejected_calls,
                    "fallback_calls": self.metrics.fallback_calls,
                    "state_transitions": self.metrics.state_transitions,
                    "success_rate_percent": round(
                        self.metrics.success_rate, 2
                    ),
                },
                "events": [
                    {
                        "event": event.event,
                        "state": event.state.value,
                        "details": event.details,
                    }
                    for event in self.history
                ],
            }


class PaymentService:
    """Simulates a payment dependency with a local degradation response."""

    def __init__(self) -> None:
        self.available = True
        self.breaker = CircuitBreaker(
            "payment-provider",
            CircuitConfig(
                failure_threshold=3,
                recovery_timeout=1.0,
                half_open_max_calls=1,
            ),
        )

    def process_payment(self, amount: float) -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("Payment amount must be positive.")

        def remote_payment() -> dict[str, Any]:
            if not self.available:
                raise ConnectionError("Payment provider unavailable.")

            return {
                "status": "PROCESSED",
                "amount": amount,
                "provider": "remote",
            }

        def degraded_payment() -> dict[str, Any]:
            return {
                "status": "PENDING",
                "amount": amount,
                "provider": "local-queue",
                "message": "Payment queued for later processing.",
            }

        return self.breaker.execute(
            remote_payment,
            fallback=degraded_payment,
        )


class ProductCatalog:
    """Read-only cached dependency with graceful degradation."""

    def __init__(self) -> None:
        self.cache = {
            101: {"name": "Laptop", "price": 75000},
            102: {"name": "Keyboard", "price": 2500},
        }

        self.breaker = CircuitBreaker(
            "product-catalog",
            CircuitConfig(failure_threshold=2, recovery_timeout=1.5),
        )

        self.available = True

    def get_product(self, product_id: int) -> dict[str, Any]:
        def remote_read() -> dict[str, Any]:
            if not self.available:
                raise TimeoutError("Catalog request timed out.")

            if product_id not in self.cache:
                raise KeyError("Product does not exist.")

            return {
                **self.cache[product_id],
                "source": "remote",
            }

        def cached_read() -> dict[str, Any]:
            if product_id not in self.cache:
                return {
                    "status": "UNAVAILABLE",
                    "message": "Product is not present in local cache.",
                }

            return {
                **self.cache[product_id],
                "source": "cache",
                "stale": True,
            }

        return self.breaker.execute(
            remote_read,
            fallback=cached_read,
        )


def run_tests() -> None:
    """Verify state transitions, fallback behavior, and validation."""

    breaker = CircuitBreaker(
        "test-service",
        CircuitConfig(
            failure_threshold=2,
            recovery_timeout=0.05,
        ),
    )

    failing = lambda: (_ for _ in ()).throw(
        ConnectionError("Simulated outage.")
    )

    assert breaker.state == CircuitState.CLOSED

    for _ in range(2):
        try:
            breaker.execute(failing)
        except ConnectionError:
            pass

    assert breaker.state == CircuitState.OPEN

    result = breaker.execute(
        lambda: "remote",
        fallback=lambda: "fallback",
    )

    assert result == "fallback"

    time.sleep(0.06)

    result = breaker.execute(lambda: "recovered")

    assert result == "recovered"
    assert breaker.state == CircuitState.CLOSED

    try:
        CircuitConfig(failure_threshold=0)
        raise AssertionError("Invalid configuration was accepted.")
    except CircuitConfigurationError:
        pass

    print("All circuit breaker tests passed.")


def main() -> None:
    print("\nCIRCUIT BREAKER DEMONSTRATION")

    payment = PaymentService()

    payment.available = False

    for amount in (500, 750, 1000, 1250):
        result = payment.process_payment(amount)
        print("Payment:", result)

    print("\nPayment circuit metrics:")
    print(payment.breaker.snapshot())

    catalog = ProductCatalog()
    catalog.available = False

    print("\nCatalog graceful degradation:")
    print(catalog.get_product(101))
    print(catalog.get_product(102))

    print("\nAutomated validation:")
    run_tests()


if __name__ == "__main__":
    main()
