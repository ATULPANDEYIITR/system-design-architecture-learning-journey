#!/usr/bin/env python3
"""
Bulkheads: Resource Isolation and Failure Containment

Simulates independent resource pools, bounded concurrency, queue limits,
timeouts, circuit breakers, load shedding, health monitoring, and recovery.

Python 3.10+
Standard-library only.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("bulkheads")


class PoolState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class BulkheadError(Exception):
    pass


class CapacityExceeded(BulkheadError):
    pass


class QueueFull(BulkheadError):
    pass


class CircuitOpen(BulkheadError):
    pass


class OperationTimeout(BulkheadError):
    pass


class ServiceFailure(BulkheadError):
    pass


@dataclass(frozen=True)
class PoolConfig:
    name: str
    max_concurrent: int
    max_queue: int
    timeout_seconds: float
    failure_threshold: int = 3
    recovery_seconds: float = 2.0

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Pool name cannot be empty")
        if self.max_concurrent < 1:
            raise ValueError("Concurrency must be positive")
        if self.max_queue < 0:
            raise ValueError("Queue capacity cannot be negative")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")
        if self.failure_threshold < 1:
            raise ValueError("Failure threshold must be positive")
        if self.recovery_seconds <= 0:
            raise ValueError("Recovery interval must be positive")


@dataclass
class PoolMetrics:
    accepted: int = 0
    rejected: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0
    active: int = 0
    queued: int = 0
    consecutive_failures: int = 0
    total_latency: float = 0.0

    @property
    def average_latency(self) -> float:
        if self.completed == 0:
            return 0.0
        return self.total_latency / self.completed


class CircuitBreaker:
    """Three-state circuit breaker: CLOSED, OPEN, HALF_OPEN."""

    def __init__(self, threshold: int, recovery_seconds: float):
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self.state = PoolState.HEALTHY
        self.failures = 0
        self.opened_at = 0.0
        self.probe_in_progress = False

    def allow_request(self) -> bool:
        if self.state == PoolState.HEALTHY:
            return True

        if self.state == PoolState.OPEN:
            if time.monotonic() - self.opened_at >= self.recovery_seconds:
                self.state = PoolState.DEGRADED
                self.probe_in_progress = False
            else:
                return False

        if self.state == PoolState.DEGRADED:
            if self.probe_in_progress:
                return False
            self.probe_in_progress = True
            return True

        return False

    def record_success(self):
        self.failures = 0
        self.probe_in_progress = False
        self.state = PoolState.HEALTHY

    def record_failure(self):
        self.failures += 1
        self.probe_in_progress = False

        if self.failures >= self.threshold:
            self.state = PoolState.OPEN
            self.opened_at = time.monotonic()


@dataclass
class BulkheadPool:
    config: PoolConfig
    semaphore: asyncio.Semaphore = field(init=False)
    metrics: PoolMetrics = field(default_factory=PoolMetrics)
    breaker: CircuitBreaker = field(init=False)
    waiting: int = 0
    waiting_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self):
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self.breaker = CircuitBreaker(
            self.config.failure_threshold,
            self.config.recovery_seconds,
        )

    async def execute(
        self,
        operation: Callable[[], object],
        simulate_failure: bool = False,
    ):
        if not self.breaker.allow_request():
            self.metrics.rejected += 1
            raise CircuitOpen(f"{self.config.name}: circuit is open")

        # Queue admission is checked independently from execution capacity.
        async with self.waiting_lock:
            if self.semaphore.locked() and self.waiting >= self.config.max_queue:
                self.metrics.rejected += 1
                raise QueueFull(f"{self.config.name}: queue is full")

            self.waiting += 1
            self.metrics.queued = self.waiting

        acquired = False
        started = time.monotonic()

        try:
            await asyncio.wait_for(
                self.semaphore.acquire(),
                timeout=self.config.timeout_seconds,
            )
            acquired = True

            async with self.waiting_lock:
                self.waiting -= 1
                self.metrics.queued = self.waiting

            self.metrics.active += 1
            self.metrics.accepted += 1

            # The timeout includes execution, not merely queue waiting.
            async def run_operation():
                if simulate_failure:
                    raise ServiceFailure("Simulated downstream failure")

                result = operation()
                if asyncio.iscoroutine(result):
                    return await result
                return result

            try:
                result = await asyncio.wait_for(
                    run_operation(),
                    timeout=self.config.timeout_seconds,
                )

                self.metrics.completed += 1
                self.metrics.total_latency += time.monotonic() - started
                self.metrics.consecutive_failures = 0
                self.breaker.record_success()
                return result

            except asyncio.TimeoutError as exc:
                self.metrics.timed_out += 1
                self.metrics.failed += 1
                self.metrics.consecutive_failures += 1
                self.breaker.record_failure()
                raise OperationTimeout(
                    f"{self.config.name}: operation timed out"
                ) from exc

            except Exception:
                self.metrics.failed += 1
                self.metrics.consecutive_failures += 1
                self.breaker.record_failure()
                raise

        except asyncio.TimeoutError as exc:
            self.metrics.rejected += 1
            raise CapacityExceeded(
                f"{self.config.name}: waiting for capacity timed out"
            ) from exc

        finally:
            if acquired:
                self.metrics.active -= 1
                self.semaphore.release()
            else:
                async with self.waiting_lock:
                    self.waiting -= 1
                    self.metrics.queued = self.waiting


class BulkheadManager:
    """Maintains independent resource pools for separate dependencies."""

    def __init__(self):
        self.pools: dict[str, BulkheadPool] = {}

    def register(self, config: PoolConfig):
        if config.name in self.pools:
            raise ValueError(f"Duplicate pool: {config.name}")
        self.pools[config.name] = BulkheadPool(config)

    def get_pool(self, name: str) -> BulkheadPool:
        try:
            return self.pools[name]
        except KeyError as exc:
            raise ValueError(f"Unknown resource pool: {name}") from exc

    async def execute(self, pool_name: str, operation, **kwargs):
        return await self.get_pool(pool_name).execute(
            operation,
            **kwargs,
        )

    def report(self):
        print("\nRESOURCE ISOLATION REPORT")
        print("-" * 90)

        for name, pool in self.pools.items():
            m = pool.metrics
            print(
                f"{name:15} "
                f"state={pool.breaker.state.value:9} "
                f"active={m.active:2} "
                f"queued={m.queued:2} "
                f"accepted={m.accepted:3} "
                f"completed={m.completed:3} "
                f"failed={m.failed:3} "
                f"rejected={m.rejected:3} "
                f"avg_latency={m.average_latency:.4f}s"
            )


async def payment_service():
    await asyncio.sleep(0.08)
    return {"service": "payment", "status": "processed"}


async def inventory_service():
    await asyncio.sleep(0.12)
    return {"service": "inventory", "status": "reserved"}


async def notification_service():
    await asyncio.sleep(0.04)
    return {"service": "notification", "status": "sent"}


async def run_request(
    manager: BulkheadManager,
    service: str,
    operation,
    failure: bool = False,
):
    try:
        result = await manager.execute(
            service,
            operation,
            simulate_failure=failure,
        )
        logger.info("SUCCESS %s: %s", service, result)
    except BulkheadError as exc:
        logger.warning("ISOLATED FAILURE %s: %s", service, exc)


async def demonstrate_bulkheads():
    manager = BulkheadManager()

    manager.register(
        PoolConfig(
            name="payment",
            max_concurrent=2,
            max_queue=3,
            timeout_seconds=1.0,
            failure_threshold=3,
        )
    )

    manager.register(
        PoolConfig(
            name="inventory",
            max_concurrent=3,
            max_queue=4,
            timeout_seconds=1.0,
            failure_threshold=3,
        )
    )

    manager.register(
        PoolConfig(
            name="notification",
            max_concurrent=1,
            max_queue=2,
            timeout_seconds=1.0,
            failure_threshold=2,
        )
    )

    print("SCENARIO 1: Independent resource pools")

    tasks = []

    for _ in range(6):
        tasks.append(
            run_request(manager, "payment", payment_service)
        )

    for _ in range(5):
        tasks.append(
            run_request(manager, "inventory", inventory_service)
        )

    for _ in range(4):
        tasks.append(
            run_request(manager, "notification", notification_service)
        )

    await asyncio.gather(*tasks)

    print("\nSCENARIO 2: Notification dependency failures")

    for _ in range(3):
        await run_request(
            manager,
            "notification",
            notification_service,
            failure=True,
        )

    print("\nSCENARIO 3: Verify other pools remain operational")

    await run_request(manager, "payment", payment_service)
    await run_request(manager, "inventory", inventory_service)

    print("\nSCENARIO 4: Circuit breaker recovery")

    await asyncio.sleep(2.1)

    await run_request(
        manager,
        "notification",
        notification_service,
    )

    print("\nSCENARIO 5: Invalid pool")

    try:
        manager.get_pool("unknown")
    except ValueError as exc:
        logger.warning("VALIDATION: %s", exc)

    manager.report()

    # Basic correctness checks.
    assert len(manager.pools) == 3
    assert manager.get_pool("payment").metrics.completed > 0
    assert manager.get_pool("inventory").metrics.completed > 0
    assert manager.get_pool("notification").metrics.failed >= 2

    print("\nAll demonstration assertions passed.")


if __name__ == "__main__":
    try:
        asyncio.run(demonstrate_bulkheads())
    except KeyboardInterrupt:
        logger.warning("Execution interrupted")
