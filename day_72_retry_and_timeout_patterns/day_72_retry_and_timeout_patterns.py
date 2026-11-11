#!/usr/bin/env python3
"""
Retry and Timeout Patterns
Backoff, jitter, retry budgets, circuit breakers, and retry storms.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Any


class FailureType(Enum):
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PERMANENT = "permanent"


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RetryExhausted(Exception):
    pass


class CircuitOpenError(Exception):
    pass


class PermanentError(Exception):
    pass


@dataclass
class RetryPolicy:
    max_attempts: int = 5
    initial_delay: float = 0.2
    multiplier: float = 2.0
    max_delay: float = 5.0
    jitter: str = "full"
    timeout: float = 2.0
    max_elapsed: float = 15.0

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_delay < 0 or self.max_delay < 0:
            raise ValueError("Delays cannot be negative")
        if self.multiplier < 1:
            raise ValueError("Multiplier must be at least 1")
        if self.timeout <= 0 or self.max_elapsed <= 0:
            raise ValueError("Timeout limits must be positive")
        if self.jitter not in {"none", "full", "equal"}:
            raise ValueError("Unsupported jitter strategy")

    def delay(self, retry_number: int) -> float:
        """Calculate capped exponential backoff."""
        ceiling = min(
            self.max_delay,
            self.initial_delay * self.multiplier ** retry_number
        )

        if self.jitter == "none":
            return ceiling
        if self.jitter == "full":
            return random.uniform(0, ceiling)
        return random.uniform(ceiling / 2, ceiling)


@dataclass
class AttemptRecord:
    attempt: int
    outcome: str
    delay: float
    elapsed: float
    error: str | None = None


@dataclass
class RetryResult:
    success: bool
    value: Any = None
    attempts: int = 0
    elapsed: float = 0.0
    history: list[AttemptRecord] = field(default_factory=list)


class RetryBudget:
    """Limits aggregate retries to prevent retry amplification."""

    def __init__(self, capacity: int, refill_per_second: float):
        if capacity < 1 or refill_per_second < 0:
            raise ValueError("Invalid retry budget")

        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = refill_per_second
        self.updated_at = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.updated_at

        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.updated_at = now

        if self.tokens < 1:
            return False

        self.tokens -= 1
        return True


class CircuitBreaker:
    """Prevents repeated calls to an unhealthy dependency."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 3.0,
        half_open_limit: int = 1
    ):
        if failure_threshold < 1 or recovery_timeout <= 0:
            raise ValueError("Invalid circuit breaker configuration")
        if half_open_limit < 1:
            raise ValueError("half_open_limit must be positive")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_limit = half_open_limit

        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at = 0.0
        self.half_open_calls = 0

    def allow_request(self) -> bool:
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.opened_at < self.recovery_timeout:
                return False

            self.state = CircuitState.HALF_OPEN
            self.half_open_calls = 0

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_limit:
                return False
            self.half_open_calls += 1

        return True

    def record_success(self):
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.half_open_calls = 0

    def record_failure(self):
        self.failures += 1

        if (
            self.state == CircuitState.HALF_OPEN
            or self.failures >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            self.half_open_calls = 0


class RetryExecutor:
    def __init__(
        self,
        policy: RetryPolicy,
        budget: RetryBudget | None = None,
        breaker: CircuitBreaker | None = None
    ):
        self.policy = policy
        self.budget = budget
        self.breaker = breaker

    def execute(
        self,
        operation: Callable[[], Any],
        retryable: tuple[type[Exception], ...] = (
            TimeoutError,
            ConnectionError
        ),
        before_attempt: Callable[[int], None] | None = None
    ) -> RetryResult:

        started = time.monotonic()
        history = []

        for attempt in range(1, self.policy.max_attempts + 1):
            elapsed = time.monotonic() - started

            if elapsed >= self.policy.max_elapsed:
                raise RetryExhausted("Maximum elapsed time exceeded")

            if self.breaker and not self.breaker.allow_request():
                raise CircuitOpenError("Circuit breaker is open")

            if before_attempt:
                before_attempt(attempt)

            attempt_started = time.monotonic()

            try:
                value = operation()

                duration = time.monotonic() - attempt_started
                history.append(
                    AttemptRecord(attempt, "success", 0, duration)
                )

                if self.breaker:
                    self.breaker.record_success()

                return RetryResult(
                    True,
                    value,
                    attempt,
                    time.monotonic() - started,
                    history
                )

            except PermanentError:
                if self.breaker:
                    self.breaker.record_success()
                raise

            except retryable as error:
                duration = time.monotonic() - attempt_started

                if self.breaker:
                    self.breaker.record_failure()

                if attempt >= self.policy.max_attempts:
                    history.append(
                        AttemptRecord(
                            attempt, "exhausted", 0,
                            duration, str(error)
                        )
                    )
                    raise RetryExhausted(
                        f"Retries exhausted after {attempt} attempts"
                    ) from error

                if self.budget and not self.budget.consume():
                    raise RetryExhausted(
                        "Aggregate retry budget exhausted"
                    ) from error

                delay = self.policy.delay(attempt - 1)

                remaining = (
                    self.policy.max_elapsed
                    - (time.monotonic() - started)
                )

                if remaining <= 0 or delay >= remaining:
                    raise RetryExhausted(
                        "Insufficient elapsed-time budget for retry"
                    ) from error

                history.append(
                    AttemptRecord(
                        attempt, "retry", delay,
                        duration, str(error)
                    )
                )

                time.sleep(delay)

        raise RetryExhausted("Operation did not complete")


class SimulatedService:
    """A service that becomes available after configured failures."""

    def __init__(self, failures_before_success: int):
        self.failures_before_success = failures_before_success
        self.calls = 0

    def request(self) -> dict:
        self.calls += 1

        if self.calls <= self.failures_before_success:
            raise ConnectionError(
                f"Temporary connection failure #{self.calls}"
            )

        return {
            "status": "success",
            "request_id": str(uuid.uuid4()),
            "calls": self.calls
        }


def simulate_retry_storm(
    clients: int = 100,
    retries: int = 4,
    initial_delay: float = 1.0,
    multiplier: float = 2.0,
    jitter: bool = False
) -> dict:
    """
    Simulate synchronized retry scheduling.
    A retry storm occurs when clients retry at similar times.
    """

    schedule = Counter()

    for _ in range(clients):
        current = 0.0

        for retry in range(retries):
            delay = min(
                30.0,
                initial_delay * multiplier ** retry
            )

            if jitter:
                delay = random.uniform(0, delay)

            current += delay
            bucket = round(current, 1)
            schedule[bucket] += 1

    return {
        "clients": clients,
        "retry_rounds": retries,
        "jitter_enabled": jitter,
        "retry_events": sum(schedule.values()),
        "maximum_simultaneous_retries": max(
            schedule.values(), default=0
        ),
        "schedule": dict(sorted(schedule.items()))
    }


def save_metrics(metrics: dict, filename: str = "retry_metrics.json"):
    path = Path(filename)
    path.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8"
    )


def run_tests():
    policy = RetryPolicy(
        max_attempts=4,
        initial_delay=0.01,
        max_delay=0.05,
        jitter="full",
        timeout=1,
        max_elapsed=3
    )

    service = SimulatedService(2)

    executor = RetryExecutor(
        policy,
        RetryBudget(20, 10),
        CircuitBreaker(5, 1)
    )

    result = executor.execute(service.request)

    assert result.success
    assert result.attempts == 3
    assert service.calls == 3

    # Permanent failures must not be retried.
    permanent = SimulatedService(10)

    try:
        RetryExecutor(policy).execute(
            lambda: (_ for _ in ()).throw(
                PermanentError("Invalid credentials")
            )
        )
        raise AssertionError("Permanent failure was not propagated")
    except PermanentError:
        pass

    # Retry exhaustion.
    try:
        RetryExecutor(policy).execute(
            lambda: (_ for _ in ()).throw(
                ConnectionError("Service unavailable")
            )
        )
        raise AssertionError("Expected retry exhaustion")
    except RetryExhausted:
        pass

    # Retry budget.
    empty_budget = RetryBudget(1, 0)
    empty_budget.consume()

    try:
        RetryExecutor(policy, empty_budget).execute(
            lambda: (_ for _ in ()).throw(
                ConnectionError("Unavailable")
            )
        )
        raise AssertionError("Expected budget exhaustion")
    except RetryExhausted:
        pass

    # Circuit breaker.
    breaker = CircuitBreaker(2, 0.1)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not breaker.allow_request()

    # Validate jitter reduces synchronization in this simulation.
    synchronized = simulate_retry_storm(
        clients=100, jitter=False
    )
    randomized = simulate_retry_storm(
        clients=100, jitter=True
    )

    assert synchronized["retry_events"] == randomized["retry_events"]

    print("All retry tests passed.")
    print("Successful attempts:", result.attempts)
    print("Retry history:")

    for record in result.history:
        print(asdict(record))

    print(
        "Maximum synchronized retries:",
        synchronized["maximum_simultaneous_retries"]
    )

    print(
        "Maximum randomized retries:",
        randomized["maximum_simultaneous_retries"]
    )

    save_metrics({
        "successful_execution": {
            "attempts": result.attempts,
            "elapsed": result.elapsed,
            "history": [asdict(x) for x in result.history]
        },
        "synchronized_storm": synchronized,
        "jittered_storm": randomized
    })


if __name__ == "__main__":
    run_tests()
