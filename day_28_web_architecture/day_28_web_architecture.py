"""
Web Architecture: Synchronous vs Asynchronous Communication
Blocking, Non-Blocking, and Asynchronous Workflows

A self-contained study and executable demonstration.

This file progresses from basic request/response concepts to:
- synchronous communication
- blocking execution
- non-blocking execution
- asynchronous workflows
- callbacks, futures, and coroutines
- concurrency versus parallelism
- timeouts and retries
- polling and long-running jobs
- queues and event-driven workflows
- dependency-aware workflow execution
- backpressure
- idempotency
- circuit breakers
- observability
- production design considerations

The examples use only Python's standard library.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import queue
import random
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# 1. FOUNDATIONS
# ---------------------------------------------------------------------------

def heading(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def pause(seconds: float) -> None:
    """Keep demonstrations fast while preserving the timing relationships."""
    time.sleep(seconds)


def synchronous_call(name: str, delay: float = 0.05) -> str:
    """
    A synchronous function does not return until its work has completed.

    The caller is waiting during the simulated I/O operation.
    """
    print(f"[sync] starting {name}")
    pause(delay)
    print(f"[sync] finished {name}")
    return f"{name}: completed"


def demonstrate_basic_synchronous_communication() -> None:
    heading("1. Synchronous communication")

    start = time.perf_counter()

    first = synchronous_call("service-A")
    second = synchronous_call("service-B")

    elapsed = time.perf_counter() - start
    print(first)
    print(second)
    print(f"Elapsed time: {elapsed:.3f}s")

    # If each independent operation takes about 0.05s, sequential execution
    # takes approximately 0.10s because the second call starts after the first.


# ---------------------------------------------------------------------------
# 2. BLOCKING VERSUS NON-BLOCKING
# ---------------------------------------------------------------------------

def blocking_operation(name: str, delay: float = 0.05) -> str:
    print(f"[blocking] {name} begins")
    pause(delay)
    print(f"[blocking] {name} ends")
    return name


def demonstrate_blocking() -> None:
    heading("2. Blocking execution")

    # The current thread cannot proceed through this function call until
    # blocking_operation returns.
    start = time.perf_counter()

    result = blocking_operation("database query")
    print(f"Caller received: {result}")

    elapsed = time.perf_counter() - start
    print(f"Caller was blocked for approximately {elapsed:.3f}s")


def non_blocking_operation(
    name: str,
    executor: concurrent.futures.Executor,
    delay: float = 0.05,
) -> concurrent.futures.Future[str]:
    """
    Submit work and immediately return a Future.

    The caller receives control before the simulated I/O completes.
    """
    return executor.submit(blocking_operation, name, delay)


def demonstrate_non_blocking_submission() -> None:
    heading("3. Non-blocking submission with Future")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        start = time.perf_counter()

        future = non_blocking_operation("remote API", executor)

        submission_time = time.perf_counter() - start
        print(f"Time required to submit work: {submission_time:.6f}s")
        print("The caller can perform other work while the task runs.")

        pause(0.01)
        print("Caller performed unrelated local work.")

        result = future.result()
        elapsed = time.perf_counter() - start

        print(f"Future result: {result}")
        print(f"Total elapsed time: {elapsed:.3f}s")


# ---------------------------------------------------------------------------
# 3. CONCURRENCY AND PARALLELISM
# ---------------------------------------------------------------------------

def demonstrate_thread_concurrency() -> None:
    heading("4. Concurrent I/O-style work")

    names = ["API-1", "API-2", "API-3", "API-4"]

    start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(blocking_operation, name, 0.05)
            for name in names
        ]
        results = [future.result() for future in futures]

    elapsed = time.perf_counter() - start

    print("Results:", results)
    print(
        "Independent waiting operations overlap because different worker "
        "threads can wait concurrently."
    )
    print(f"Elapsed time: {elapsed:.3f}s")


def cpu_work(value: int) -> int:
    """
    Deliberately small CPU workload.

    CPU-bound work may benefit from processes rather than Python threads,
    depending on the workload and interpreter/runtime.
    """
    total = 0
    for number in range(1, value):
        total += number * number
    return total


def demonstrate_process_parallelism() -> None:
    heading("5. Process-based parallelism")

    values = [30_000, 30_500, 31_000, 31_500]

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = [executor.submit(cpu_work, value) for value in values]
        results = [future.result() for future in futures]

    print("CPU results calculated in worker processes.")
    print("Result count:", len(results))


# ---------------------------------------------------------------------------
# 4. ASYNCIO COROUTINES
# ---------------------------------------------------------------------------

async def async_service(name: str, delay: float = 0.05) -> str:
    """
    asyncio.sleep suspends this coroutine instead of blocking the event loop.

    While this coroutine is waiting, another ready coroutine can execute.
    """
    print(f"[async] {name} started")
    await asyncio.sleep(delay)
    print(f"[async] {name} completed")
    return f"{name}: completed"


async def demonstrate_asyncio() -> None:
    heading("6. Asynchronous workflows with asyncio")

    start = time.perf_counter()

    results = await asyncio.gather(
        async_service("service-A"),
        async_service("service-B"),
        async_service("service-C"),
    )

    elapsed = time.perf_counter() - start

    print("Results:", results)
    print(f"Elapsed time: {elapsed:.3f}s")
    print(
        "The coroutines overlap their waiting periods without requiring one "
        "OS thread per coroutine."
    )


async def demonstrate_create_task() -> None:
    heading("7. Tasks and explicit workflow control")

    task = asyncio.create_task(async_service("background-task", 0.05))

    print("Task created. Other workflow logic can run first.")
    await asyncio.sleep(0.01)
    print("Foreground coroutine continues.")

    result = await task
    print("Collected background result:", result)


# ---------------------------------------------------------------------------
# 5. TIMEOUTS, ERRORS, AND CANCELLATION
# ---------------------------------------------------------------------------

async def unreliable_service(
    name: str,
    delay: float,
    should_fail: bool = False,
) -> str:
    await asyncio.sleep(delay)

    if should_fail:
        raise RuntimeError(f"{name} returned an application error")

    return f"{name}: success"


async def demonstrate_timeout_and_error_handling() -> None:
    heading("8. Timeouts and error handling")

    try:
        result = await asyncio.wait_for(
            unreliable_service("slow-service", 0.20),
            timeout=0.05,
        )
        print(result)
    except asyncio.TimeoutError:
        print("Timeout handled: the caller stopped waiting.")

    try:
        await unreliable_service("failing-service", 0.01, should_fail=True)
    except RuntimeError as error:
        print("Application failure handled:", error)

    task = asyncio.create_task(unreliable_service("cancelled-service", 0.20))
    await asyncio.sleep(0.01)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        print("Cancellation handled: unfinished task was cancelled.")


# ---------------------------------------------------------------------------
# 6. RETRIES AND BACKOFF
# ---------------------------------------------------------------------------

async def retry_async(
    operation: Callable[[], Any],
    attempts: int = 3,
    base_delay: float = 0.01,
) -> Any:
    """
    Retry transient failures with exponential backoff.

    Production systems should normally add jitter to reduce synchronized
    retry storms.
    """
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as error:
            last_error = error

            if attempt == attempts - 1:
                break

            delay = base_delay * (2 ** attempt)
            jitter = random.uniform(0, delay * 0.25)
            await asyncio.sleep(delay + jitter)

    assert last_error is not None
    raise last_error


async def demonstrate_retry() -> None:
    heading("9. Retry with exponential backoff")

    state = {"attempts": 0}

    async def transient_operation() -> str:
        state["attempts"] += 1

        if state["attempts"] < 3:
            raise ConnectionError("temporary network failure")

        return "operation succeeded"

    result = await retry_async(transient_operation, attempts=3)
    print(result)
    print("Attempts:", state["attempts"])


# ---------------------------------------------------------------------------
# 7. POLLING AND LONG-RUNNING JOBS
# ---------------------------------------------------------------------------

@dataclass
class Job:
    job_id: str
    status: str = "queued"
    result: str | None = None
    progress: int = 0


class JobService:
    """
    A simplified asynchronous job API.

    POST-like behavior creates a job immediately.
    A worker changes its state later.
    Clients can poll the job status.
    """

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}

    def submit(self) -> Job:
        job = Job(job_id=str(uuid.uuid4()))
        self.jobs[job.job_id] = job
        return job

    async def worker(self, job: Job) -> None:
        job.status = "running"

        for progress in range(0, 101, 25):
            await asyncio.sleep(0.02)
            job.progress = progress

        job.status = "completed"
        job.result = "Report generated successfully"

    def get_status(self, job_id: str) -> Job:
        return self.jobs[job_id]


async def demonstrate_job_polling() -> None:
    heading("10. Long-running asynchronous job")

    service = JobService()
    job = service.submit()

    worker_task = asyncio.create_task(service.worker(job))

    print("Job accepted:", job.job_id)

    while True:
        current = service.get_status(job.job_id)
        print(f"Status={current.status}, progress={current.progress}%")

        if current.status == "completed":
            print("Result:", current.result)
            break

        await asyncio.sleep(0.015)

    await worker_task


# ---------------------------------------------------------------------------
# 8. EVENT-DRIVEN COMMUNICATION
# ---------------------------------------------------------------------------

@dataclass
class Event:
    event_type: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class EventBus:
    """
    Minimal in-process publish/subscribe event bus.

    Real systems may use brokers or streaming platforms, but the same
    producer/consumer concepts remain important.
    """

    def __init__(self) -> None:
        self.subscribers: dict[str, list[Callable[[Event], Any]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        self.subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Event) -> None:
        handlers = self.subscribers.get(event.event_type, [])

        # Independent consumers can execute concurrently.
        await asyncio.gather(*(handler(event) for handler in handlers))


async def demonstrate_event_driven_architecture() -> None:
    heading("11. Event-driven asynchronous communication")

    bus = EventBus()

    async def audit_handler(event: Event) -> None:
        await asyncio.sleep(0.01)
        print("Audit service processed:", event.event_id)

    async def notification_handler(event: Event) -> None:
        await asyncio.sleep(0.02)
        print("Notification service processed:", event.event_id)

    bus.subscribe("order.created", audit_handler)
    bus.subscribe("order.created", notification_handler)

    event = Event(
        event_type="order.created",
        payload={"order_id": "ORD-1001", "amount": 2500},
    )

    await bus.publish(event)


# ---------------------------------------------------------------------------
# 9. QUEUES AND BACKPRESSURE
# ---------------------------------------------------------------------------

async def producer(
    work_queue: asyncio.Queue[str],
    items: Iterable[str],
) -> None:
    for item in items:
        # A bounded queue creates backpressure when consumers cannot keep up.
        await work_queue.put(item)
        print("Produced:", item)


async def consumer(
    work_queue: asyncio.Queue[str],
    consumer_name: str,
) -> None:
    while True:
        item = await work_queue.get()

        try:
            if item == "__STOP__":
                return

            await asyncio.sleep(0.015)
            print(f"{consumer_name} processed {item}")
        finally:
            work_queue.task_done()


async def demonstrate_backpressure() -> None:
    heading("12. Queue-based workflow and backpressure")

    work_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)

    consumer_tasks = [
        asyncio.create_task(consumer(work_queue, "worker-1")),
        asyncio.create_task(consumer(work_queue, "worker-2")),
    ]

    await producer(
        work_queue,
        [f"item-{number}" for number in range(1, 7)],
    )

    await work_queue.join()

    for _ in consumer_tasks:
        await work_queue.put("__STOP__")

    await asyncio.gather(*consumer_tasks)

    print(
        "A bounded queue prevents producers from continuously accumulating "
        "unlimited pending work."
    )


# ---------------------------------------------------------------------------
# 10. DEPENDENCY-AWARE ASYNCHRONOUS WORKFLOW
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStep:
    name: str
    dependencies: set[str]
    duration: float
    action: Callable[[], Any]


class WorkflowEngine:
    """
    Executes independent workflow steps concurrently while respecting
    dependency relationships.

    Example:

        validate
          |
       authorize
       /      \
    reserve  notify
       |
     charge
    """

    def __init__(self, steps: list[WorkflowStep]) -> None:
        self.steps = {step.name: step for step in steps}
        self.completed: set[str] = set()
        self.results: dict[str, Any] = {}

    async def run_step(self, step: WorkflowStep) -> Any:
        print(f"Workflow step started: {step.name}")
        result = await step.action()
        print(f"Workflow step completed: {step.name}")
        return result

    async def run(self) -> dict[str, Any]:
        pending = set(self.steps)

        while pending:
            ready = [
                self.steps[name]
                for name in pending
                if self.steps[name].dependencies <= self.completed
            ]

            if not ready:
                unresolved = ", ".join(sorted(pending))
                raise RuntimeError(
                    f"Workflow cannot progress. Unresolved dependency cycle "
                    f"or missing dependency involving: {unresolved}"
                )

            results = await asyncio.gather(
                *(self.run_step(step) for step in ready)
            )

            for step, result in zip(ready, results):
                self.results[step.name] = result
                self.completed.add(step.name)
                pending.remove(step.name)

        return self.results


async def demonstrate_workflow_engine() -> None:
    heading("13. Dependency-aware asynchronous workflow")

    async def action(name: str, duration: float) -> str:
        await asyncio.sleep(duration)
        return f"{name}: OK"

    steps = [
        WorkflowStep(
            "validate",
            set(),
            0.02,
            lambda: action("validate", 0.02),
        ),
        WorkflowStep(
            "authorize",
            {"validate"},
            0.02,
            lambda: action("authorize", 0.02),
        ),
        WorkflowStep(
            "reserve",
            {"authorize"},
            0.03,
            lambda: action("reserve", 0.03),
        ),
        WorkflowStep(
            "notify",
            {"authorize"},
            0.03,
            lambda: action("notify", 0.03),
        ),
        WorkflowStep(
            "charge",
            {"reserve"},
            0.02,
            lambda: action("charge", 0.02),
        ),
    ]

    engine = WorkflowEngine(steps)
    results = await engine.run()

    for name, result in results.items():
        print(name, "=>", result)


# ---------------------------------------------------------------------------
# 11. IDEMPOTENCY
# ---------------------------------------------------------------------------

class IdempotentPaymentProcessor:
    """
    Repeated requests carrying the same idempotency key produce the same
    stored result instead of charging the customer repeatedly.
    """

    def __init__(self) -> None:
        self.processed: dict[str, str] = {}

    async def charge(self, idempotency_key: str, amount: float) -> str:
        if idempotency_key in self.processed:
            return self.processed[idempotency_key]

        await asyncio.sleep(0.01)

        result = (
            f"payment accepted: key={idempotency_key}, "
            f"amount={amount:.2f}"
        )

        self.processed[idempotency_key] = result
        return result


async def demonstrate_idempotency() -> None:
    heading("14. Idempotency in asynchronous workflows")

    processor = IdempotentPaymentProcessor()

    key = "payment-request-123"

    first = await processor.charge(key, 500.00)
    second = await processor.charge(key, 500.00)

    print("First request :", first)
    print("Retry request :", second)
    print("Same stored result:", first == second)


# ---------------------------------------------------------------------------
# 12. CIRCUIT BREAKER
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Simplified circuit breaker.

    CLOSED  -> requests flow normally.
    OPEN    -> requests fail fast.
    HALF_OPEN -> one probe request tests recovery.
    """

    def __init__(self, failure_threshold: int = 3, recovery_time: float = 0.05):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.state = "CLOSED"
        self.opened_at = 0.0

    def allow_request(self) -> bool:
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if time.perf_counter() - self.opened_at >= self.recovery_time:
                self.state = "HALF_OPEN"
                return True
            return False

        return True

    def record_success(self) -> None:
        self.failures = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failures += 1

        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            self.opened_at = time.perf_counter()


async def demonstrate_circuit_breaker() -> None:
    heading("15. Circuit breaker")

    breaker = CircuitBreaker(failure_threshold=2, recovery_time=0.02)

    for attempt in range(1, 5):
        if not breaker.allow_request():
            print(f"Attempt {attempt}: rejected immediately; circuit OPEN")
            continue

        try:
            raise ConnectionError("remote service unavailable")
        except ConnectionError:
            breaker.record_failure()
            print(
                f"Attempt {attempt}: remote failure; "
                f"state={breaker.state}"
            )

    await asyncio.sleep(0.025)

    if breaker.allow_request():
        print("Recovery probe permitted.")
        breaker.record_success()
        print("Circuit state after recovery:", breaker.state)


# ---------------------------------------------------------------------------
# 13. OBSERVABILITY
# ---------------------------------------------------------------------------

@dataclass
class TraceRecord:
    operation: str
    started: float
    finished: float
    status: str

    @property
    def duration_ms(self) -> float:
        return (self.finished - self.started) * 1000


async def traced_operation(name: str, delay: float) -> TraceRecord:
    started = time.perf_counter()

    try:
        await asyncio.sleep(delay)
        status = "success"
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    finally:
        finished = time.perf_counter()

    return TraceRecord(name, started, finished, status)


async def demonstrate_observability() -> None:
    heading("16. Measuring asynchronous operations")

    records = await asyncio.gather(
        traced_operation("database", 0.02),
        traced_operation("cache", 0.01),
        traced_operation("external-api", 0.03),
    )

    for record in records:
        print(
            f"{record.operation}: "
            f"{record.duration_ms:.2f}ms, {record.status}"
        )


# ---------------------------------------------------------------------------
# 14. SYNCHRONOUS VS ASYNCHRONOUS COMPARISON
# ---------------------------------------------------------------------------

def synchronous_batch(count: int) -> float:
    start = time.perf_counter()

    for number in range(count):
        synchronous_call(f"sync-{number}", 0.02)

    return time.perf_counter() - start


async def asynchronous_batch(count: int) -> float:
    start = time.perf_counter()

    await asyncio.gather(
        *(async_service(f"async-{number}", 0.02) for number in range(count))
    )

    return time.perf_counter() - start


async def demonstrate_comparison() -> None:
    heading("17. Sequential versus concurrent I/O")

    sync_elapsed = synchronous_batch(4)
    async_elapsed = await asynchronous_batch(4)

    print(f"Sequential elapsed: {sync_elapsed:.3f}s")
    print(f"Concurrent async elapsed: {async_elapsed:.3f}s")

    print(
        "These timings are illustrative. Real performance depends on "
        "latency, connection pools, CPU cost, scheduler overhead, and load."
    )


# ---------------------------------------------------------------------------
# 15. EDGE CASES
# ---------------------------------------------------------------------------

async def demonstrate_edge_cases() -> None:
    heading("18. Important edge cases")

    # Zero-delay asynchronous work still has scheduling semantics.
    print(await async_service("zero-delay", 0))

    # Empty gather returns an empty list.
    empty_results = await asyncio.gather()
    print("Empty gather:", empty_results)

    # Timeout boundaries must be designed carefully because real systems
    # contain network and scheduling variability.
    try:
        await asyncio.wait_for(async_service("boundary", 0.001), timeout=0.000001)
    except asyncio.TimeoutError:
        print("Very short timeout handled.")

    # A failed task must be awaited or otherwise observed so its exception
    # is not silently lost.
    failed_task = asyncio.create_task(
        unreliable_service("edge-failure", 0.001, should_fail=True)
    )

    try:
        await failed_task
    except RuntimeError as error:
        print("Observed task exception:", error)


# ---------------------------------------------------------------------------
# 16. TESTABLE BUSINESS LOGIC
# ---------------------------------------------------------------------------

def validate_request(
    customer_id: str,
    amount: float,
) -> None:
    if not customer_id.strip():
        raise ValueError("customer_id must not be empty")

    if amount <= 0:
        raise ValueError("amount must be greater than zero")

    if amount > 1_000_000:
        raise ValueError("amount exceeds configured transaction limit")


def demonstrate_validation() -> None:
    heading("19. Validation before asynchronous work")

    valid_requests = [
        ("CUS-001", 100.0),
        ("CUS-002", 999_999.99),
    ]

    for customer_id, amount in valid_requests:
        validate_request(customer_id, amount)
        print("Accepted:", customer_id, amount)

    invalid_requests = [
        ("", 100.0),
        ("CUS-003", 0),
        ("CUS-004", 2_000_000),
    ]

    for customer_id, amount in invalid_requests:
        try:
            validate_request(customer_id, amount)
        except ValueError as error:
            print("Rejected:", error)


# ---------------------------------------------------------------------------
# 17. SECURITY DESIGN
# ---------------------------------------------------------------------------

def demonstrate_security_principles() -> None:
    heading("20. Security considerations")

    print("Secure asynchronous systems should:")
    principles = [
        "authenticate callers before protected operations",
        "authorize each requested action",
        "validate input at service boundaries",
        "use TLS for network communication",
        "avoid placing secrets in URLs or logs",
        "apply rate limits to expensive endpoints",
        "use bounded queues to reduce resource exhaustion",
        "use idempotency keys for retryable state-changing operations",
        "set connection and operation timeouts",
        "avoid logging credentials, tokens, or sensitive payloads",
    ]

    for number, principle in enumerate(principles, start=1):
        print(f"{number}. {principle}")


# ---------------------------------------------------------------------------
# 18. MAIN
# ---------------------------------------------------------------------------

async def main() -> None:
    demonstrate_basic_synchronous_communication()
    demonstrate_blocking()
    demonstrate_non_blocking_submission()
    demonstrate_thread_concurrency()
    demonstrate_process_parallelism()

    await demonstrate_asyncio()
    await demonstrate_create_task()
    await demonstrate_timeout_and_error_handling()
    await demonstrate_retry()
    await demonstrate_job_polling()
    await demonstrate_event_driven_architecture()
    await demonstrate_backpressure()
    await demonstrate_workflow_engine()
    await demonstrate_idempotency()
    await demonstrate_circuit_breaker()
    await demonstrate_observability()
    await demonstrate_comparison()
    await demonstrate_edge_cases()

    demonstrate_validation()
    demonstrate_security_principles()

    heading("21. Architectural principles demonstrated")
    principles = {
        "Synchronous": "The caller waits for the operation's response.",
        "Blocking": "The executing thread/task cannot make useful progress while blocked.",
        "Non-blocking": "The caller can continue before the operation completes.",
        "Asynchronous": "Completion is handled independently from immediate invocation.",
        "Concurrency": "Multiple activities make progress during overlapping time.",
        "Parallelism": "Multiple activities execute simultaneously on separate resources.",
        "Timeout": "A bounded waiting period prevents indefinite resource occupation.",
        "Retry": "Transient failures may be retried using controlled backoff.",
        "Queue": "Work can be decoupled between producers and consumers.",
        "Backpressure": "Consumers can regulate producers when capacity is limited.",
        "Idempotency": "Repeated equivalent requests do not duplicate a state-changing effect.",
        "Circuit breaker": "Repeated remote failures can trigger fast rejection.",
        "Observability": "Timing, status, and failures should be measurable.",
    }

    for concept, meaning in principles.items():
        print(f"{concept:18} {meaning}")


if __name__ == "__main__":
    asyncio.run(main())
