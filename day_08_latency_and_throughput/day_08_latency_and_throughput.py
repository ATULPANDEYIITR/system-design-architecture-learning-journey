"""
Latency and Throughput
======================

A comprehensive, self-contained study script covering:

- Definitions and terminology
- Response time and latency decomposition
- Throughput and processing capacity
- Little's Law
- Sequential and parallel processing
- Bottlenecks and capacity limits
- Queueing and waiting time
- Percentiles and tail latency
- Load generation and benchmarking
- Concurrency and parallelism
- CPU-bound versus I/O-bound workloads
- Backpressure and overload
- Batching
- Caching
- Rate limiting
- Connection pools
- Horizontal and vertical scaling
- Amdahl's Law
- Load balancing
- Production monitoring and debugging
- Statistical analysis of latency measurements
- Common mistakes and edge cases

The examples use only the Python standard library.
"""

from __future__ import annotations

import concurrent.futures
import functools
import math
import queue
import random
import statistics
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Generic, Iterable, Optional, TypeVar


# =============================================================================
# 1. FUNDAMENTAL DEFINITIONS
# =============================================================================

# Latency:
# The time required for one operation or request to complete.
#
# Throughput:
# The amount of work completed per unit of time.
#
# Examples:
# - A web request takes 120 milliseconds -> latency = 120 ms.
# - A server completes 2,000 requests in one second ->
#   throughput = 2,000 requests/second.
#
# Capacity:
# The maximum sustainable throughput a system can provide while meeting
# acceptable performance and reliability requirements.
#
# Response time:
# Usually the total time observed by the requester. It may include:
# - Queue waiting
# - Network delay
# - Processing
# - Storage access
# - Serialization
# - Other dependencies
#
# Service time:
# Time during which the resource actively processes a request.
#
# Waiting time:
# Time spent waiting before processing begins.
#
# Response time = waiting time + service time
#
# Important distinction:
# Increasing throughput does not automatically reduce latency.
# A system can process many requests per second while individual requests
# experience long waiting times because of queues.


def measure_single_operation() -> None:
    """Demonstrate basic latency measurement."""

    start = time.perf_counter()

    # Simulate useful work.
    total = sum(i * i for i in range(100_000))

    elapsed_seconds = time.perf_counter() - start
    latency_ms = elapsed_seconds * 1_000

    print("\n1. BASIC LATENCY MEASUREMENT")
    print(f"Result: {total}")
    print(f"Latency: {latency_ms:.3f} ms")


# =============================================================================
# 2. WALL-CLOCK TIME VERSUS HIGH-RESOLUTION TIMERS
# =============================================================================

# time.time():
# - Represents wall-clock time.
# - Can be affected by system clock changes.
#
# time.perf_counter():
# - High-resolution monotonic timer.
# - Appropriate for performance measurement.
#
# For benchmarking durations, perf_counter() is generally preferable.


def timer_comparison() -> None:
    """Show two timing APIs."""

    wall_start = time.time()
    perf_start = time.perf_counter()

    sum(range(10_000))

    wall_elapsed = time.time() - wall_start
    perf_elapsed = time.perf_counter() - perf_start

    print("\n2. TIMER COMPARISON")
    print(f"time.time() elapsed:        {wall_elapsed:.9f} seconds")
    print(f"time.perf_counter() elapsed:{perf_elapsed:.9f} seconds")


# =============================================================================
# 3. THROUGHPUT CALCULATION
# =============================================================================


def calculate_throughput(completed_requests: int, duration_seconds: float) -> float:
    """
    Calculate throughput.

    Throughput = completed work / elapsed time
    """
    if completed_requests < 0:
        raise ValueError("completed_requests cannot be negative")

    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero")

    return completed_requests / duration_seconds


def throughput_example() -> None:
    completed_requests = 5_000
    duration_seconds = 2.5

    rps = calculate_throughput(completed_requests, duration_seconds)

    print("\n3. THROUGHPUT")
    print(f"Completed requests: {completed_requests}")
    print(f"Duration:           {duration_seconds:.2f} seconds")
    print(f"Throughput:         {rps:.2f} requests/second")


# =============================================================================
# 4. RESPONSE TIME DECOMPOSITION
# =============================================================================

@dataclass
class ResponseTimeBreakdown:
    """
    Represents components contributing to end-to-end response time.

    All values are represented in milliseconds.
    """

    queue_wait_ms: float
    network_ms: float
    processing_ms: float
    database_ms: float
    serialization_ms: float

    @property
    def total_ms(self) -> float:
        return (
            self.queue_wait_ms
            + self.network_ms
            + self.processing_ms
            + self.database_ms
            + self.serialization_ms
        )


def response_time_breakdown_example() -> None:
    breakdown = ResponseTimeBreakdown(
        queue_wait_ms=15.0,
        network_ms=10.0,
        processing_ms=25.0,
        database_ms=40.0,
        serialization_ms=5.0,
    )

    print("\n4. RESPONSE TIME BREAKDOWN")
    print(f"Queue wait:    {breakdown.queue_wait_ms:.1f} ms")
    print(f"Network:       {breakdown.network_ms:.1f} ms")
    print(f"Processing:    {breakdown.processing_ms:.1f} ms")
    print(f"Database:      {breakdown.database_ms:.1f} ms")
    print(f"Serialization: {breakdown.serialization_ms:.1f} ms")
    print(f"Total:         {breakdown.total_ms:.1f} ms")


# =============================================================================
# 5. LATENCY DISTRIBUTIONS AND PERCENTILES
# =============================================================================

# Average latency alone can hide important problems.
#
# Example:
# Nine requests take 10 ms and one request takes 1,000 ms.
#
# Average = 109 ms.
#
# Most users experienced 10 ms, but one experienced 1,000 ms.
#
# Percentiles describe the distribution:
#
# p50: median
# p90: 90% of observations are at or below this value.
# p95: 95% are at or below this value.
# p99: 99% are at or below this value.
#
# Tail latency commonly refers to high percentiles such as p95 or p99.


def percentile(values: Iterable[float], p: float) -> float:
    """
    Calculate a percentile using linear interpolation.

    p must be between 0 and 100 inclusive.
    """

    data = sorted(values)

    if not data:
        raise ValueError("values cannot be empty")

    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")

    if len(data) == 1:
        return data[0]

    position = (len(data) - 1) * p / 100
    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return data[lower_index]

    lower_value = data[lower_index]
    upper_value = data[upper_index]
    fraction = position - lower_index

    return lower_value + (upper_value - lower_value) * fraction


def latency_statistics(latencies_ms: list[float]) -> dict[str, float]:
    """Calculate useful latency metrics."""

    if not latencies_ms:
        raise ValueError("latencies_ms cannot be empty")

    return {
        "min": min(latencies_ms),
        "mean": statistics.mean(latencies_ms),
        "median_p50": percentile(latencies_ms, 50),
        "p90": percentile(latencies_ms, 90),
        "p95": percentile(latencies_ms, 95),
        "p99": percentile(latencies_ms, 99),
        "max": max(latencies_ms),
    }


def percentile_example() -> None:
    # Simulated workload with occasional slow requests.
    latencies = [
        8, 9, 10, 10, 11, 9, 12, 10, 8, 11,
        9, 10, 11, 12, 9, 10, 8, 9, 11, 10,
        12, 11, 10, 9, 8, 10, 12, 11, 9, 10,
        500, 800, 1_200,
    ]

    metrics = latency_statistics(latencies)

    print("\n5. LATENCY DISTRIBUTION")
    for name, value in metrics.items():
        print(f"{name:12}: {value:.2f} ms")


# =============================================================================
# 6. SEQUENTIAL PROCESSING
# =============================================================================

def simulated_request(request_id: int, service_time_ms: float) -> int:
    """Simulate one request."""

    time.sleep(service_time_ms / 1_000)
    return request_id


def sequential_processing_example() -> None:
    request_count = 5
    service_time_ms = 50

    start = time.perf_counter()

    for request_id in range(request_count):
        simulated_request(request_id, service_time_ms)

    elapsed = time.perf_counter() - start
    throughput = calculate_throughput(request_count, elapsed)

    print("\n6. SEQUENTIAL PROCESSING")
    print(f"Requests:   {request_count}")
    print(f"Elapsed:    {elapsed:.3f} seconds")
    print(f"Throughput: {throughput:.2f} requests/second")
    print(
        "Expected behavior: total execution time is approximately "
        "request_count * service_time."
    )


# =============================================================================
# 7. CONCURRENCY
# =============================================================================

# Concurrency means multiple tasks make progress during overlapping periods.
#
# For I/O-bound work, threads can improve throughput because one thread can wait
# while another performs useful work.
#
# Python's Global Interpreter Lock (GIL) limits simultaneous execution of Python
# bytecode in standard CPython threads, so threads generally do not provide the
# same benefit for CPU-bound pure Python calculations.


def concurrent_processing_example() -> None:
    request_count = 10
    service_time_ms = 100
    worker_count = 5

    start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:
        futures = [
            executor.submit(
                simulated_request,
                request_id,
                service_time_ms,
            )
            for request_id in range(request_count)
        ]

        for future in futures:
            future.result()

    elapsed = time.perf_counter() - start
    throughput = calculate_throughput(request_count, elapsed)

    print("\n7. CONCURRENT PROCESSING")
    print(f"Requests:   {request_count}")
    print(f"Workers:    {worker_count}")
    print(f"Elapsed:    {elapsed:.3f} seconds")
    print(f"Throughput: {throughput:.2f} requests/second")


# =============================================================================
# 8. LATENCY AND THROUGHPUT ARE RELATED BUT DIFFERENT
# =============================================================================

def latency_throughput_relationship() -> None:
    """
    Demonstrate an important distinction.

    Suppose every request requires 100 ms of service time.

    One sequential worker:
        Maximum ideal throughput ~= 10 requests/second.

    Ten independent workers:
        Each can process approximately 10 requests/second.
        Maximum ideal aggregate throughput ~= 100 requests/second.

    The service latency of an individual request can remain approximately
    100 ms while total throughput increases substantially.
    """

    service_time_seconds = 0.1

    one_worker_rps = 1 / service_time_seconds
    ten_worker_rps = 10 / service_time_seconds

    print("\n8. LATENCY VERSUS THROUGHPUT")
    print(f"Service latency:                 {service_time_seconds * 1000:.0f} ms")
    print(f"Ideal throughput with 1 worker:  {one_worker_rps:.0f} requests/second")
    print(f"Ideal throughput with 10 workers:{ten_worker_rps:.0f} requests/second")


# =============================================================================
# 9. PROCESSING CAPACITY
# =============================================================================

def capacity_from_service_rate(
    worker_count: int,
    average_service_time_seconds: float,
) -> float:
    """
    Estimate ideal capacity.

    capacity ~= number_of_workers / average_service_time

    This assumes:
    - work is evenly distributed
    - workers operate independently
    - there is no bottleneck elsewhere
    - there is sufficient incoming demand
    """

    if worker_count <= 0:
        raise ValueError("worker_count must be greater than zero")

    if average_service_time_seconds <= 0:
        raise ValueError("average_service_time_seconds must be greater than zero")

    return worker_count / average_service_time_seconds


def capacity_example() -> None:
    workers = 8
    service_time = 0.025

    estimated_capacity = capacity_from_service_rate(
        workers,
        service_time,
    )

    print("\n9. PROCESSING CAPACITY")
    print(f"Workers:             {workers}")
    print(f"Service time:        {service_time * 1000:.1f} ms")
    print(f"Ideal capacity:      {estimated_capacity:.1f} requests/second")


# =============================================================================
# 10. BOTTLENECKS
# =============================================================================

# A system is constrained by its slowest saturated resource.
#
# Example pipeline:
#
# API capacity       = 2,000 requests/sec
# Database capacity  =   500 requests/sec
# External API       =   800 requests/sec
#
# End-to-end sustainable throughput cannot exceed approximately 500 requests/sec
# unless the database bottleneck is changed.


def bottleneck_capacity(capacities: dict[str, float]) -> tuple[str, float]:
    """Return the lowest-capacity component."""

    if not capacities:
        raise ValueError("capacities cannot be empty")

    for component, capacity in capacities.items():
        if capacity <= 0:
            raise ValueError(
                f"capacity for {component!r} must be greater than zero"
            )

    bottleneck = min(capacities, key=capacities.get)
    return bottleneck, capacities[bottleneck]


def bottleneck_example() -> None:
    capacities = {
        "load_balancer": 10_000,
        "application": 2_000,
        "database": 500,
        "external_service": 800,
    }

    bottleneck, capacity = bottleneck_capacity(capacities)

    print("\n10. BOTTLENECK ANALYSIS")
    for component, component_capacity in capacities.items():
        print(f"{component:20}: {component_capacity:,.0f} requests/second")

    print(f"Bottleneck: {bottleneck}")
    print(f"System capacity estimate: {capacity:.0f} requests/second")


# =============================================================================
# 11. LITTLE'S LAW
# =============================================================================

# Little's Law:
#
# L = λW
#
# Where:
#
# L = average number of items in the system
# λ = average arrival rate / throughput
# W = average time spent in the system
#
# Rearrangements:
#
# W = L / λ
# λ = L / W
#
# Example:
#
# Average 200 requests are in a system.
# Throughput is 100 requests/second.
#
# W = 200 / 100 = 2 seconds average time in the system.


def littles_law_response_time(
    average_items_in_system: float,
    throughput_per_second: float,
) -> float:
    """Calculate average time in the system."""

    if average_items_in_system < 0:
        raise ValueError("average_items_in_system cannot be negative")

    if throughput_per_second <= 0:
        raise ValueError("throughput_per_second must be greater than zero")

    return average_items_in_system / throughput_per_second


def littles_law_example() -> None:
    average_requests = 200
    throughput = 100

    average_response_time = littles_law_response_time(
        average_requests,
        throughput,
    )

    print("\n11. LITTLE'S LAW")
    print(f"Average requests in system: {average_requests}")
    print(f"Throughput:                 {throughput} requests/second")
    print(f"Average time in system:     {average_response_time:.2f} seconds")


# =============================================================================
# 12. UTILIZATION
# =============================================================================

# Utilization measures how busy a resource is.
#
# utilization = arrival_rate / service_capacity
#
# Example:
#
# Incoming workload: 800 requests/sec
# Capacity:          1,000 requests/sec
#
# Utilization = 0.8 = 80%
#
# As utilization approaches 100%, queueing delay can increase sharply.


def utilization(arrival_rate: float, service_capacity: float) -> float:
    if arrival_rate < 0:
        raise ValueError("arrival_rate cannot be negative")

    if service_capacity <= 0:
        raise ValueError("service_capacity must be greater than zero")

    return arrival_rate / service_capacity


def utilization_example() -> None:
    capacity = 1_000

    print("\n12. UTILIZATION")
    for arrival_rate in [100, 500, 800, 950, 990, 1_000, 1_100]:
        u = utilization(arrival_rate, capacity)
        state = (
            "stable"
            if u < 1
            else "at capacity"
            if u == 1
            else "overloaded"
        )

        print(
            f"Arrival rate={arrival_rate:4d}/s | "
            f"Utilization={u:6.1%} | {state}"
        )


# =============================================================================
# 13. SIMPLE QUEUE SIMULATION
# =============================================================================

@dataclass
class Request:
    request_id: int
    arrival_time: float
    service_time: float
    start_time: Optional[float] = None
    completion_time: Optional[float] = None

    @property
    def waiting_time(self) -> Optional[float]:
        if self.start_time is None:
            return None
        return self.start_time - self.arrival_time

    @property
    def response_time(self) -> Optional[float]:
        if self.completion_time is None:
            return None
        return self.completion_time - self.arrival_time


def simulate_single_server_queue(
    arrival_times: list[float],
    service_times: list[float],
) -> list[Request]:
    """
    Simulate a single-server FIFO queue.

    Assumptions:
    - Requests arrive at specified times.
    - Only one request can be processed at a time.
    - Requests are processed in arrival order.
    """

    if len(arrival_times) != len(service_times):
        raise ValueError(
            "arrival_times and service_times must have equal lengths"
        )

    server_available_time = 0.0
    requests: list[Request] = []

    for request_id, (arrival, service) in enumerate(
        zip(arrival_times, service_times),
        start=1,
    ):
        if arrival < 0:
            raise ValueError("arrival time cannot be negative")

        if service < 0:
            raise ValueError("service time cannot be negative")

        request = Request(
            request_id=request_id,
            arrival_time=arrival,
            service_time=service,
        )

        request.start_time = max(
            request.arrival_time,
            server_available_time,
        )

        request.completion_time = (
            request.start_time + request.service_time
        )

        server_available_time = request.completion_time
        requests.append(request)

    return requests


def queue_simulation_example() -> None:
    # Times are measured in seconds from the beginning of the simulation.
    arrival_times = [0.0, 0.1, 0.2, 0.3, 0.4]
    service_times = [0.25, 0.25, 0.25, 0.25, 0.25]

    requests = simulate_single_server_queue(
        arrival_times,
        service_times,
    )

    print("\n13. SINGLE-SERVER QUEUE")
    print(
        "ID | Arrival | Start | Completion | Waiting | Response"
    )
    print("-" * 60)

    for request in requests:
        print(
            f"{request.request_id:2d} | "
            f"{request.arrival_time:7.2f} | "
            f"{request.start_time:5.2f} | "
            f"{request.completion_time:10.2f} | "
            f"{request.waiting_time:7.2f} | "
            f"{request.response_time:8.2f}"
        )


# =============================================================================
# 14. WHY QUEUES CAUSE LATENCY EXPLOSIONS
# =============================================================================

def queue_growth_example() -> None:
    """
    Demonstrate backlog growth.

    Arrival rate exceeds service rate.

    Example:
    - 120 requests arrive each second.
    - Server completes 100 requests each second.

    Backlog grows by approximately 20 requests every second.
    """

    arrival_rate = 120
    service_rate = 100
    duration_seconds = 10

    backlog = 0

    print("\n14. QUEUE GROWTH DURING OVERLOAD")
    print("Second | Backlog")

    for second in range(1, duration_seconds + 1):
        arrivals = arrival_rate
        completed = min(backlog + arrivals, service_rate)
        backlog = backlog + arrivals - completed

        print(f"{second:6d} | {backlog:7d}")


# =============================================================================
# 15. MULTI-SERVER CAPACITY SIMULATION
# =============================================================================

@dataclass(order=True)
class WorkerState:
    available_at: float
    worker_id: int = field(compare=False)


def simulate_multi_server_queue(
    arrival_times: list[float],
    service_times: list[float],
    worker_count: int,
) -> list[Request]:
    """
    Simulate FIFO requests processed by multiple workers.

    The next request is assigned to the worker that becomes available first.
    """

    if worker_count <= 0:
        raise ValueError("worker_count must be greater than zero")

    if len(arrival_times) != len(service_times):
        raise ValueError("arrival_times and service_times must match")

    workers = [
        WorkerState(available_at=0.0, worker_id=worker_id)
        for worker_id in range(worker_count)
    ]

    import heapq

    heapq.heapify(workers)

    requests: list[Request] = []

    for request_id, (arrival, service) in enumerate(
        zip(arrival_times, service_times),
        start=1,
    ):
        worker = heapq.heappop(workers)

        request = Request(
            request_id=request_id,
            arrival_time=arrival,
            service_time=service,
        )

        request.start_time = max(arrival, worker.available_at)
        request.completion_time = request.start_time + service

        worker.available_at = request.completion_time
        heapq.heappush(workers, worker)

        requests.append(request)

    return requests


def multi_server_example() -> None:
    arrivals = [index * 0.1 for index in range(12)]
    services = [0.25] * len(arrivals)

    one_worker = simulate_multi_server_queue(
        arrivals,
        services,
        worker_count=1,
    )

    three_workers = simulate_multi_server_queue(
        arrivals,
        services,
        worker_count=3,
    )

    one_worker_average_wait = statistics.mean(
        request.waiting_time for request in one_worker
        if request.waiting_time is not None
    )

    three_worker_average_wait = statistics.mean(
        request.waiting_time for request in three_workers
        if request.waiting_time is not None
    )

    print("\n15. MULTI-SERVER QUEUE")
    print(
        f"Average waiting time with 1 worker: "
        f"{one_worker_average_wait:.3f} seconds"
    )
    print(
        f"Average waiting time with 3 workers: "
        f"{three_worker_average_wait:.3f} seconds"
    )


# =============================================================================
# 16. AVERAGE LATENCY CAN BE MISLEADING
# =============================================================================

def average_vs_tail_example() -> None:
    fast_requests = [10.0] * 990
    slow_requests = [1_000.0] * 10

    measurements = fast_requests + slow_requests

    print("\n16. AVERAGE VERSUS TAIL LATENCY")
    print(f"Average: {statistics.mean(measurements):.2f} ms")
    print(f"p50:     {percentile(measurements, 50):.2f} ms")
    print(f"p95:     {percentile(measurements, 95):.2f} ms")
    print(f"p99:     {percentile(measurements, 99):.2f} ms")
    print(f"Maximum: {max(measurements):.2f} ms")


# =============================================================================
# 17. HISTOGRAMS
# =============================================================================

def histogram(
    values: Iterable[float],
    bucket_size: float,
) -> dict[tuple[float, float], int]:
    """Create a simple numeric histogram."""

    if bucket_size <= 0:
        raise ValueError("bucket_size must be greater than zero")

    buckets: dict[tuple[float, float], int] = {}

    for value in values:
        lower = math.floor(value / bucket_size) * bucket_size
        upper = lower + bucket_size
        key = (lower, upper)
        buckets[key] = buckets.get(key, 0) + 1

    return dict(sorted(buckets.items()))


def histogram_example() -> None:
    random.seed(42)

    values = [
        max(0.1, random.gauss(50, 10))
        for _ in range(100)
    ]

    # Add tail events.
    values.extend([200, 250, 300])

    buckets = histogram(values, bucket_size=25)

    print("\n17. LATENCY HISTOGRAM")

    for (lower, upper), count in buckets.items():
        print(
            f"{lower:6.0f}-{upper:6.0f} ms | "
            f"{'#' * count}"
        )


# =============================================================================
# 18. LOAD TESTING BASICS
# =============================================================================

def benchmark(
    operation: Callable[[], Any],
    iterations: int,
) -> dict[str, float]:
    """
    Benchmark repeated execution.

    The first few iterations can be treated as warm-up in environments where
    initialization, caching, or just-in-time compilation affects timing.
    """

    if iterations <= 0:
        raise ValueError("iterations must be greater than zero")

    latencies_ms: list[float] = []

    overall_start = time.perf_counter()

    for _ in range(iterations):
        start = time.perf_counter()
        operation()
        elapsed = time.perf_counter() - start
        latencies_ms.append(elapsed * 1_000)

    overall_elapsed = time.perf_counter() - overall_start

    metrics = latency_statistics(latencies_ms)
    metrics["throughput"] = calculate_throughput(
        iterations,
        overall_elapsed,
    )

    return metrics


def benchmark_example() -> None:
    result = benchmark(
        operation=lambda: sum(i * i for i in range(10_000)),
        iterations=50,
    )

    print("\n18. BENCHMARK")
    for metric, value in result.items():
        if metric == "throughput":
            print(f"{metric:12}: {value:.2f} operations/second")
        else:
            print(f"{metric:12}: {value:.4f} ms")


# =============================================================================
# 19. WARM-UP AND COLD-START EFFECTS
# =============================================================================

class LazyResource:
    """
    Simulates lazy initialization.

    The first request pays initialization cost.
    Later requests are faster.
    """

    def __init__(self) -> None:
        self.initialized = False

    def process(self) -> str:
        if not self.initialized:
            # Simulate loading configuration, opening a connection,
            # populating a cache, or initializing a resource.
            time.sleep(0.05)
            self.initialized = True

        return "processed"


def cold_start_example() -> None:
    resource = LazyResource()

    measurements = []

    for _ in range(5):
        start = time.perf_counter()
        resource.process()
        measurements.append(
            (time.perf_counter() - start) * 1_000
        )

    print("\n19. COLD START")
    for index, measurement in enumerate(measurements, start=1):
        print(f"Request {index}: {measurement:.2f} ms")


# =============================================================================
# 20. CPU-BOUND VERSUS I/O-BOUND WORK
# =============================================================================

def cpu_bound_work(iterations: int) -> int:
    """Pure CPU work."""

    total = 0
    for number in range(iterations):
        total += number * number
    return total


def io_bound_work(delay_seconds: float) -> None:
    """Simulated I/O wait."""

    time.sleep(delay_seconds)


def cpu_vs_io_example() -> None:
    print("\n20. CPU-BOUND VERSUS I/O-BOUND")

    cpu_start = time.perf_counter()
    cpu_bound_work(300_000)
    cpu_elapsed = time.perf_counter() - cpu_start

    io_start = time.perf_counter()
    io_bound_work(0.02)
    io_elapsed = time.perf_counter() - io_start

    print(f"CPU-bound operation: {cpu_elapsed * 1_000:.2f} ms")
    print(f"I/O-bound operation: {io_elapsed * 1_000:.2f} ms")


# =============================================================================
# 21. THREADS FOR I/O-BOUND WORK
# =============================================================================

def io_concurrency_example() -> None:
    task_count = 10
    delay_seconds = 0.05

    sequential_start = time.perf_counter()

    for _ in range(task_count):
        io_bound_work(delay_seconds)

    sequential_elapsed = (
        time.perf_counter() - sequential_start
    )

    concurrent_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=task_count
    ) as executor:
        futures = [
            executor.submit(io_bound_work, delay_seconds)
            for _ in range(task_count)
        ]

        for future in futures:
            future.result()

    concurrent_elapsed = (
        time.perf_counter() - concurrent_start
    )

    print("\n21. THREAD CONCURRENCY FOR I/O")
    print(f"Sequential: {sequential_elapsed:.3f} seconds")
    print(f"Concurrent: {concurrent_elapsed:.3f} seconds")


# =============================================================================
# 22. ASYNCHRONOUS CONCEPTS
# =============================================================================

# asyncio is appropriate for high-concurrency I/O workloads when operations
# cooperate with the event loop.
#
# This script does not require an asynchronous network dependency to demonstrate
# the fundamental idea.


def asynchronous_concept_example() -> None:
    print("\n22. ASYNCHRONOUS I/O CONCEPT")
    print(
        "Async systems can suspend an I/O-bound task while allowing "
        "other ready tasks to run."
    )
    print(
        "Blocking CPU-heavy work inside an event loop can harm latency "
        "for unrelated tasks."
    )


# =============================================================================
# 23. BATCHING
# =============================================================================

def process_items_individually(
    items: list[int],
    per_request_overhead_ms: float,
    processing_ms_per_item: float,
) -> float:
    """
    Estimate total time when each item is sent independently.
    """

    total_ms = 0.0

    for _ in items:
        total_ms += (
            per_request_overhead_ms
            + processing_ms_per_item
        )

    return total_ms


def process_items_in_batches(
    items: list[int],
    batch_size: int,
    per_request_overhead_ms: float,
    processing_ms_per_item: float,
) -> float:
    """
    Estimate total time when multiple items share request overhead.
    """

    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    total_ms = 0.0

    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]

        total_ms += per_request_overhead_ms
        total_ms += (
            len(batch) * processing_ms_per_item
        )

    return total_ms


def batching_example() -> None:
    items = list(range(100))
    overhead = 5.0
    processing = 1.0

    individual_time = process_items_individually(
        items,
        overhead,
        processing,
    )

    batched_time = process_items_in_batches(
        items,
        batch_size=20,
        per_request_overhead_ms=overhead,
        processing_ms_per_item=processing,
    )

    print("\n23. BATCHING")
    print(f"Individual processing estimate: {individual_time:.1f} ms")
    print(f"Batched processing estimate:    {batched_time:.1f} ms")

    # Trade-off:
    # Batching can increase throughput by amortizing fixed overhead.
    # It can also increase latency because an item may wait for the batch
    # to fill before processing starts.


# =============================================================================
# 24. CACHING
# =============================================================================

T = TypeVar("T")


class LRUCache(Generic[T]):
    """
    A small thread-safe Least Recently Used cache.

    Cache benefits:
    - Reduced repeated computation
    - Reduced database or network load
    - Lower latency for cache hits

    Cache risks:
    - Stale data
    - Memory consumption
    - Cache invalidation complexity
    - Cache stampedes
    """

    def __init__(self, max_size: int = 100) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be greater than zero")

        self.max_size = max_size
        self._data: OrderedDict[str, T] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            if key not in self._data:
                return None

            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: T) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)

            self._data[key] = value

            if len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


def expensive_lookup(value: int) -> int:
    """Simulate expensive work."""

    time.sleep(0.01)
    return value * value


def caching_example() -> None:
    cache: LRUCache[int] = LRUCache(max_size=10)

    def cached_lookup(value: int) -> tuple[int, bool]:
        key = str(value)
        cached = cache.get(key)

        if cached is not None:
            return cached, True

        result = expensive_lookup(value)
        cache.put(key, result)
        return result, False

    print("\n24. CACHING")

    for value in [5, 5, 5, 7, 7]:
        start = time.perf_counter()
        result, cache_hit = cached_lookup(value)
        elapsed_ms = (
            time.perf_counter() - start
        ) * 1_000

        print(
            f"Input={value}, Result={result}, "
            f"Cache hit={cache_hit}, "
            f"Latency={elapsed_ms:.3f} ms"
        )


# =============================================================================
# 25. CACHE STAMPEDE
# =============================================================================

# A cache stampede occurs when many requests simultaneously miss the same cache
# entry and all perform the expensive operation.
#
# A common mitigation is "single-flight" behavior:
# one request computes the value while others wait for the same result.


class SingleFlightCache:
    """Simplified cache that prevents duplicate concurrent computation."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._inflight: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def get_or_compute(
        self,
        key: str,
        compute: Callable[[], T],
    ) -> T:
        while True:
            with self._lock:
                if key in self._cache:
                    return self._cache[key]

                if key not in self._inflight:
                    event = threading.Event()
                    self._inflight[key] = event
                    leader = True
                else:
                    event = self._inflight[key]
                    leader = False

            if leader:
                try:
                    value = compute()
                    with self._lock:
                        self._cache[key] = value
                    return value
                finally:
                    with self._lock:
                        completed_event = self._inflight.pop(
                            key,
                            None,
                        )
                        if completed_event is not None:
                            completed_event.set()

            event.wait()


def cache_stampede_example() -> None:
    cache = SingleFlightCache()
    computation_count = 0
    computation_lock = threading.Lock()

    def compute() -> str:
        nonlocal computation_count

        with computation_lock:
            computation_count += 1

        time.sleep(0.02)
        return "expensive result"

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=10
    ) as executor:
        futures = [
            executor.submit(
                cache.get_or_compute,
                "shared-key",
                compute,
            )
            for _ in range(10)
        ]

        results = [future.result() for future in futures]

    print("\n25. CACHE STAMPEDE PROTECTION")
    print(f"Requests: {len(results)}")
    print(f"Actual expensive computations: {computation_count}")


# =============================================================================
# 26. BACKPRESSURE
# =============================================================================

# Backpressure prevents producers from generating work faster than consumers can
# safely process it.
#
# Without backpressure:
# - Queues can grow without bound.
# - Memory usage can grow.
# - Latency can become extreme.
# - Failure can spread across dependent systems.


def backpressure_example() -> None:
    work_queue: queue.Queue[int] = queue.Queue(maxsize=3)

    produced = 0
    rejected = 0

    print("\n26. BACKPRESSURE")

    for item in range(10):
        try:
            # put_nowait refuses work when the queue is full.
            work_queue.put_nowait(item)
            produced += 1
        except queue.Full:
            rejected += 1

    print(f"Accepted work items: {produced}")
    print(f"Rejected work items: {rejected}")
    print(f"Queue size:          {work_queue.qsize()}")


# =============================================================================
# 27. RATE LIMITING
# =============================================================================

class TokenBucket:
    """
    Token bucket rate limiter.

    Tokens are replenished over time.

    Advantages:
    - Supports controlled bursts.
    - Enforces average rate.

    Limitations:
    - Distributed systems require coordination or a shared implementation.
    """

    def __init__(
        self,
        capacity: float,
        refill_rate_per_second: float,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")

        if refill_rate_per_second <= 0:
            raise ValueError(
                "refill_rate_per_second must be greater than zero"
            )

        self.capacity = capacity
        self.refill_rate_per_second = refill_rate_per_second
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def allow(self, tokens_requested: float = 1.0) -> bool:
        if tokens_requested <= 0:
            raise ValueError(
                "tokens_requested must be greater than zero"
            )

        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill

            self.tokens = min(
                self.capacity,
                self.tokens
                + elapsed * self.refill_rate_per_second,
            )

            self.last_refill = now

            if self.tokens >= tokens_requested:
                self.tokens -= tokens_requested
                return True

            return False


def rate_limiting_example() -> None:
    limiter = TokenBucket(
        capacity=3,
        refill_rate_per_second=1,
    )

    print("\n27. RATE LIMITING")

    for request_number in range(6):
        allowed = limiter.allow()
        status = "ALLOWED" if allowed else "REJECTED"

        print(
            f"Request {request_number + 1}: {status}"
        )


# =============================================================================
# 28. CONNECTION POOLS
# =============================================================================

class ConnectionPool:
    """
    Simplified resource pool.

    Real connection pools commonly manage:
    - Connection creation
    - Maximum pool size
    - Idle timeouts
    - Health checks
    - Connection lifetime
    - Queueing for available connections
    """

    def __init__(self, size: int) -> None:
        if size <= 0:
            raise ValueError("size must be greater than zero")

        self._pool: queue.Queue[str] = queue.Queue(
            maxsize=size
        )

        for connection_id in range(size):
            self._pool.put(
                f"connection-{connection_id}"
            )

    def acquire(
        self,
        timeout: Optional[float] = None,
    ) -> str:
        return self._pool.get(timeout=timeout)

    def release(self, connection: str) -> None:
        self._pool.put(connection)


def connection_pool_example() -> None:
    pool = ConnectionPool(size=2)

    first = pool.acquire()
    second = pool.acquire()

    print("\n28. CONNECTION POOL")
    print(f"Acquired: {first}")
    print(f"Acquired: {second}")

    pool.release(first)
    pool.release(second)

    print("Connections returned to pool.")


# =============================================================================
# 29. AMDAHL'S LAW
# =============================================================================

# Amdahl's Law estimates the maximum speedup possible when only part of a
# workload can be parallelized.
#
# Speedup = 1 / ((1 - P) + P / N)
#
# P = parallelizable fraction
# N = number of workers
#
# Example:
# If 90% can be parallelized and 10% remains sequential,
# infinite workers cannot provide more than 10x speedup.


def amdahls_law(
    parallel_fraction: float,
    worker_count: int,
) -> float:
    if not 0 <= parallel_fraction <= 1:
        raise ValueError(
            "parallel_fraction must be between 0 and 1"
        )

    if worker_count <= 0:
        raise ValueError(
            "worker_count must be greater than zero"
        )

    sequential_fraction = 1 - parallel_fraction

    return 1 / (
        sequential_fraction
        + parallel_fraction / worker_count
    )


def amdahl_example() -> None:
    parallel_fraction = 0.90

    print("\n29. AMDAHL'S LAW")

    for workers in [1, 2, 4, 8, 16, 64]:
        speedup = amdahls_law(
            parallel_fraction,
            workers,
        )

        print(
            f"Workers={workers:2d}, "
            f"Theoretical speedup={speedup:.2f}x"
        )


# =============================================================================
# 30. HORIZONTAL AND VERTICAL SCALING
# =============================================================================

def scaling_concepts() -> None:
    print("\n30. SCALING")

    print(
        "Vertical scaling: increase resources of one machine "
        "(CPU, memory, storage performance)."
    )

    print(
        "Horizontal scaling: add more machines or service instances."
    )

    print(
        "Horizontal scaling requires coordination around shared state, "
        "load distribution, data consistency, and failure handling."
    )


# =============================================================================
# 31. LOAD BALANCING
# =============================================================================

class RoundRobinLoadBalancer:
    """Simple round-robin request distribution."""

    def __init__(self, servers: list[str]) -> None:
        if not servers:
            raise ValueError("servers cannot be empty")

        self.servers = servers
        self._index = 0
        self._lock = threading.Lock()

    def next_server(self) -> str:
        with self._lock:
            server = self.servers[self._index]
            self._index = (
                self._index + 1
            ) % len(self.servers)

            return server


def load_balancing_example() -> None:
    load_balancer = RoundRobinLoadBalancer(
        ["server-a", "server-b", "server-c"]
    )

    print("\n31. ROUND-ROBIN LOAD BALANCING")

    for request_id in range(9):
        server = load_balancer.next_server()

        print(
            f"Request {request_id + 1} -> {server}"
        )


# =============================================================================
# 32. LOAD BALANCING TRADE-OFFS
# =============================================================================

def load_balancing_tradeoffs() -> None:
    print("\n32. LOAD BALANCING TRADE-OFFS")
    print(
        "Round-robin works well when requests have similar costs."
    )
    print(
        "Least-connections can help when request durations vary."
    )
    print(
        "Weighted strategies help when servers have unequal capacity."
    )
    print(
        "Hash-based routing can preserve affinity but may create "
        "imbalanced load."
    )


# =============================================================================
# 33. HEAD-OF-LINE BLOCKING
# =============================================================================

def head_of_line_blocking_example() -> None:
    """
    One slow request can delay fast requests in a single FIFO worker.
    """

    arrivals = [0.0, 0.01, 0.02, 0.03]
    services = [1.0, 0.01, 0.01, 0.01]

    requests = simulate_single_server_queue(
        arrivals,
        services,
    )

    print("\n33. HEAD-OF-LINE BLOCKING")

    for request in requests:
        print(
            f"Request {request.request_id}: "
            f"service={request.service_time:.2f}s, "
            f"wait={request.waiting_time:.2f}s, "
            f"response={request.response_time:.2f}s"
        )


# =============================================================================
# 34. TIMEOUTS
# =============================================================================

def operation_with_timeout(
    operation: Callable[[], T],
    timeout_seconds: float,
) -> T:
    """
    Execute an operation with a thread-based timeout.

    Important production limitation:
    Timing out a Future does not necessarily stop the underlying operation.
    Real systems should support cancellation where possible.
    """

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be greater than zero"
        )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1
    ) as executor:
        future = executor.submit(operation)

        return future.result(
            timeout=timeout_seconds
        )


def timeout_example() -> None:
    print("\n34. TIMEOUTS")

    try:
        operation_with_timeout(
            lambda: (
                time.sleep(0.1),
                "finished",
            )[1],
            timeout_seconds=0.02,
        )
    except concurrent.futures.TimeoutError:
        print("Operation exceeded timeout.")


# =============================================================================
# 35. RETRIES AND RETRY AMPLIFICATION
# =============================================================================

def retry(
    operation: Callable[[], T],
    attempts: int,
    initial_delay_seconds: float = 0.01,
) -> T:
    """
    Retry with exponential backoff.

    Excessive retries can make overload worse.

    If an overloaded dependency causes failures:
    - Clients retry.
    - Traffic increases.
    - Dependency becomes even more overloaded.

    Production retry systems should often include:
    - Maximum attempts
    - Backoff
    - Jitter
    - Retry only for appropriate failures
    - Idempotency considerations
    """

    if attempts <= 0:
        raise ValueError("attempts must be greater than zero")

    delay = initial_delay_seconds
    last_exception: Optional[Exception] = None

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exception:
            last_exception = exception

            if attempt == attempts - 1:
                break

            # Random jitter reduces synchronized retry storms.
            jitter = random.uniform(
                0,
                delay * 0.1,
            )

            time.sleep(delay + jitter)
            delay *= 2

    assert last_exception is not None
    raise last_exception


def retry_example() -> None:
    failures_remaining = 2

    def unreliable_operation() -> str:
        nonlocal failures_remaining

        if failures_remaining > 0:
            failures_remaining -= 1
            raise RuntimeError("temporary failure")

        return "success"

    result = retry(
        unreliable_operation,
        attempts=4,
        initial_delay_seconds=0.001,
    )

    print("\n35. RETRIES")
    print(f"Final result: {result}")


# =============================================================================
# 36. CIRCUIT BREAKER CONCEPT
# =============================================================================

class CircuitBreaker:
    """
    Minimal circuit breaker.

    States:
    - CLOSED: requests are allowed.
    - OPEN: requests are rejected immediately.
    - HALF_OPEN: a real implementation may periodically test recovery.

    This simplified version focuses on the CLOSED -> OPEN transition.
    """

    def __init__(self, failure_threshold: int) -> None:
        if failure_threshold <= 0:
            raise ValueError(
                "failure_threshold must be greater than zero"
            )

        self.failure_threshold = failure_threshold
        self.failure_count = 0
        self.open = False

    def call(
        self,
        operation: Callable[[], T],
    ) -> T:
        if self.open:
            raise RuntimeError(
                "circuit breaker is open"
            )

        try:
            result = operation()
            self.failure_count = 0
            return result
        except Exception:
            self.failure_count += 1

            if (
                self.failure_count
                >= self.failure_threshold
            ):
                self.open = True

            raise


def circuit_breaker_example() -> None:
    breaker = CircuitBreaker(
        failure_threshold=2
    )

    def failing_operation() -> None:
        raise RuntimeError("dependency failure")

    print("\n36. CIRCUIT BREAKER")

    for attempt in range(4):
        try:
            breaker.call(failing_operation)
        except RuntimeError as error:
            print(
                f"Attempt {attempt + 1}: {error}"
            )


# =============================================================================
# 37. LATENCY BUDGETS
# =============================================================================

def latency_budget_example() -> None:
    """
    An end-to-end service-level objective may require:

        p99 response time <= 200 ms

    Internal components can receive budgets whose sum fits inside that target.
    """

    budget = {
        "network": 20,
        "authentication": 10,
        "application": 50,
        "database": 80,
        "serialization": 10,
        "buffer": 30,
    }

    total = sum(budget.values())

    print("\n37. LATENCY BUDGET")
    for component, milliseconds in budget.items():
        print(
            f"{component:15}: {milliseconds:3d} ms"
        )

    print(f"Total budget: {total} ms")


# =============================================================================
# 38. TAIL LATENCY AMPLIFICATION
# =============================================================================

def tail_latency_amplification_example() -> None:
    """
    A request depending on multiple services may be affected by the slowest
    dependency.

    Even if each dependency is usually fast, a fan-out request increases the
    probability that at least one dependency experiences a slow event.
    """

    random.seed(7)

    request_latencies = []

    for _ in range(1_000):
        dependency_latencies = []

        for _ in range(10):
            if random.random() < 0.01:
                dependency_latencies.append(
                    random.uniform(500, 1_000)
                )
            else:
                dependency_latencies.append(
                    random.uniform(10, 30)
                )

        # Parallel fan-out response is approximately constrained
        # by the slowest dependency.
        request_latencies.append(
            max(dependency_latencies)
        )

    print("\n38. TAIL LATENCY AMPLIFICATION")
    print(
        f"Fan-out request p50: "
        f"{percentile(request_latencies, 50):.2f} ms"
    )
    print(
        f"Fan-out request p99: "
        f"{percentile(request_latencies, 99):.2f} ms"
    )


# =============================================================================
# 39. SERIAL VERSUS PARALLEL DEPENDENCIES
# =============================================================================

def dependency_latency_example() -> None:
    dependencies_ms = [30, 50, 20]

    serial_latency = sum(dependencies_ms)
    parallel_latency = max(dependencies_ms)

    print("\n39. SERIAL VERSUS PARALLEL DEPENDENCIES")
    print(f"Dependency latencies: {dependencies_ms} ms")
    print(f"Serial total:         {serial_latency} ms")
    print(f"Parallel ideal total: {parallel_latency} ms")

    # Parallel execution can reduce response time.
    # It can also increase resource usage and downstream load.


# =============================================================================
# 40. COORDINATED OMISSION
# =============================================================================

def coordinated_omission_explanation() -> None:
    print("\n40. COORDINATED OMISSION")
    print(
        "A benchmark can underreport latency when it waits for each "
        "response before sending the next request."
    )
    print(
        "During a server pause, a closed-loop test may generate fewer "
        "requests and fail to represent work that would have arrived "
        "during the pause."
    )
    print(
        "Open-loop arrival models can better represent a fixed incoming "
        "request rate."
    )


# =============================================================================
# 41. CLOSED-LOOP AND OPEN-LOOP LOAD
# =============================================================================

def closed_loop_vs_open_loop() -> None:
    print("\n41. LOAD GENERATION MODELS")

    print(
        "Closed-loop: a client sends a request, waits for a response, "
        "then sends another."
    )

    print(
        "Open-loop: requests are scheduled according to an arrival rate "
        "independently of response completion."
    )

    print(
        "Closed-loop naturally reduces offered load when the system slows."
    )

    print(
        "Open-loop can reveal queue growth when arrival rate exceeds "
        "service capacity."
    )


# =============================================================================
# 42. SIMPLE OPEN-LOOP SIMULATION
# =============================================================================

def open_loop_simulation(
    arrival_rate_per_second: float,
    service_time_seconds: float,
    duration_seconds: float,
    worker_count: int,
) -> dict[str, float]:
    """
    Simulate deterministic arrivals and deterministic service times.

    This is intentionally simplified:
    - Fixed arrival interval
    - Fixed service time
    - FIFO queue
    - Worker assignment by earliest availability
    """

    if arrival_rate_per_second <= 0:
        raise ValueError(
            "arrival_rate_per_second must be greater than zero"
        )

    if service_time_seconds <= 0:
        raise ValueError(
            "service_time_seconds must be greater than zero"
        )

    if duration_seconds <= 0:
        raise ValueError(
            "duration_seconds must be greater than zero"
        )

    request_count = int(
        arrival_rate_per_second * duration_seconds
    )

    if request_count == 0:
        request_count = 1

    interval = 1 / arrival_rate_per_second

    arrivals = [
        index * interval
        for index in range(request_count)
    ]

    services = [
        service_time_seconds
    ] * request_count

    requests = simulate_multi_server_queue(
        arrivals,
        services,
        worker_count,
    )

    response_times = [
        request.response_time
        for request in requests
        if request.response_time is not None
    ]

    completion_time = max(
        request.completion_time
        for request in requests
        if request.completion_time is not None
    )

    return {
        "requests": float(request_count),
        "throughput": request_count / completion_time,
        "average_response_time": statistics.mean(
            response_times
        ),
        "p95_response_time": percentile(
            response_times,
            95,
        ),
        "max_response_time": max(
            response_times
        ),
    }


def open_loop_example() -> None:
    print("\n42. OPEN-LOOP SIMULATION")

    for arrival_rate in [10, 20, 30, 50]:
        metrics = open_loop_simulation(
            arrival_rate_per_second=arrival_rate,
            service_time_seconds=0.1,
            duration_seconds=2,
            worker_count=3,
        )

        print(
            f"Arrival={arrival_rate:2d}/s | "
            f"Average response="
            f"{metrics['average_response_time']:.3f}s | "
            f"p95="
            f"{metrics['p95_response_time']:.3f}s | "
            f"Max="
            f"{metrics['max_response_time']:.3f}s"
        )


# =============================================================================
# 43. MEMORY AND QUEUE SIZE
# =============================================================================

def memory_queue_consideration() -> None:
    print("\n43. QUEUE SIZE AND MEMORY")
    print(
        "An unbounded queue may protect producers temporarily but can "
        "consume increasing memory during sustained overload."
    )
    print(
        "A bounded queue makes overload visible and enables rejection "
        "or backpressure."
    )
    print(
        "Choosing a queue size is a latency-versus-buffering trade-off."
    )


# =============================================================================
# 44. PRIORITY QUEUES
# =============================================================================

@dataclass(order=True)
class PrioritizedRequest:
    priority: int
    sequence: int
    request_name: str = field(compare=False)


def priority_queue_example() -> None:
    priority_queue: queue.PriorityQueue[
        PrioritizedRequest
    ] = queue.PriorityQueue()

    priority_queue.put(
        PrioritizedRequest(
            priority=5,
            sequence=1,
            request_name="background job",
        )
    )

    priority_queue.put(
        PrioritizedRequest(
            priority=1,
            sequence=2,
            request_name="interactive request",
        )
    )

    priority_queue.put(
        PrioritizedRequest(
            priority=3,
            sequence=3,
            request_name="normal request",
        )
    )

    print("\n44. PRIORITY QUEUE")

    while not priority_queue.empty():
        request = priority_queue.get()

        print(
            f"Priority {request.priority}: "
            f"{request.request_name}"
        )

    # Lower numeric value means higher priority here.
    #
    # Priority queues reduce latency for high-priority work but can cause
    # starvation if lower-priority work is never scheduled.


# =============================================================================
# 45. FAIRNESS AND STARVATION
# =============================================================================

def fairness_example() -> None:
    print("\n45. FAIRNESS AND STARVATION")
    print(
        "FIFO scheduling tends to provide ordering fairness."
    )
    print(
        "Priority scheduling can improve critical request latency."
    )
    print(
        "Strict priority can starve low-priority requests."
    )
    print(
        "Weighted fair scheduling can balance importance and fairness."
    )


# =============================================================================
# 46. MEASURING CLIENT-SIDE AND SERVER-SIDE LATENCY
# =============================================================================

def measurement_boundaries() -> None:
    print("\n46. MEASUREMENT BOUNDARIES")

    print(
        "Client-observed latency may include DNS resolution, connection "
        "setup, network transmission, server processing, and response "
        "transfer."
    )

    print(
        "Server processing latency may exclude network time and therefore "
        "be much lower than end-to-end latency."
    )

    print(
        "Metrics should clearly define their measurement boundaries."
    )


# =============================================================================
# 47. CLOCK SKEW
# =============================================================================

def clock_skew_example() -> None:
    """
    Distributed latency calculations based on timestamps from different machines
    can be wrong if clocks are not synchronized.

    Duration measured by one monotonic clock is usually safer for local timing.
    """

    print("\n47. CLOCK SKEW")
    print(
        "Do not blindly subtract timestamps generated by machines with "
        "unsynchronized clocks."
    )
    print(
        "Distributed tracing systems require careful clock handling and "
        "time synchronization."
    )


# =============================================================================
# 48. PERFORMANCE REGRESSION TESTING
# =============================================================================

def performance_regression_example() -> None:
    baseline_p95_ms = 100
    candidate_p95_ms = 120

    regression_percent = (
        (
            candidate_p95_ms
            - baseline_p95_ms
        )
        / baseline_p95_ms
    ) * 100

    print("\n48. PERFORMANCE REGRESSION")
    print(f"Baseline p95:  {baseline_p95_ms} ms")
    print(f"Candidate p95: {candidate_p95_ms} ms")
    print(f"Regression:    {regression_percent:.1f}%")

    # Regression tests should compare workloads under similar conditions.
    # Noisy benchmarks can produce false positives and false negatives.


# =============================================================================
# 49. THROUGHPUT DOES NOT ALWAYS SCALE LINEARLY
# =============================================================================

def non_linear_scaling_example() -> None:
    """
    Illustrate a simplified scaling model with synchronization overhead.
    """

    base_capacity = 100

    print("\n49. NON-LINEAR SCALING")

    for workers in [1, 2, 4, 8, 16]:
        # Simplified synthetic efficiency model.
        efficiency = 1 / (
            1 + 0.08 * math.log2(workers)
        )

        capacity = (
            base_capacity
            * workers
            * efficiency
        )

        print(
            f"Workers={workers:2d} | "
            f"Efficiency={efficiency:.2%} | "
            f"Capacity={capacity:.1f}/s"
        )

    # Real scaling losses can come from:
    # - Lock contention
    # - Shared databases
    # - Network coordination
    # - Cache coherence
    # - Load imbalance
    # - Serialization
    # - Context switching


# =============================================================================
# 50. LOCK CONTENTION
# =============================================================================

class SharedCounter:
    """Thread-safe shared resource."""

    def __init__(self) -> None:
        self.value = 0
        self.lock = threading.Lock()

    def increment(self) -> None:
        with self.lock:
            self.value += 1


def lock_contention_example() -> None:
    counter = SharedCounter()
    operations_per_worker = 10_000
    worker_count = 4

    def worker() -> None:
        for _ in range(operations_per_worker):
            counter.increment()

    start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:
        futures = [
            executor.submit(worker)
            for _ in range(worker_count)
        ]

        for future in futures:
            future.result()

    elapsed = time.perf_counter() - start

    print("\n50. LOCK CONTENTION")
    print(f"Final counter: {counter.value}")
    print(f"Elapsed:       {elapsed:.4f} seconds")

    # A shared lock can become a bottleneck as concurrency increases.


# =============================================================================
# 51. BUFFERING TRADE-OFF
# =============================================================================

def buffering_tradeoff_example() -> None:
    print("\n51. BUFFERING TRADE-OFF")
    print(
        "Larger buffers can absorb short traffic bursts."
    )
    print(
        "Large buffers can also hide overload and increase queueing latency."
    )
    print(
        "Small buffers expose overload sooner but may reject work more often."
    )


# =============================================================================
# 52. SERVICE LEVEL INDICATORS AND OBJECTIVES
# =============================================================================

@dataclass
class ServiceLevelReport:
    total_requests: int
    successful_requests: int
    requests_within_latency_target: int
    latency_target_ms: float

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0

        return (
            self.successful_requests
            / self.total_requests
        )

    @property
    def latency_compliance_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0

        return (
            self.requests_within_latency_target
            / self.total_requests
        )


def service_level_example() -> None:
    report = ServiceLevelReport(
        total_requests=10_000,
        successful_requests=9_990,
        requests_within_latency_target=9_800,
        latency_target_ms=200,
    )

    print("\n52. SERVICE LEVEL METRICS")
    print(
        f"Success rate: "
        f"{report.success_rate:.3%}"
    )
    print(
        f"Requests within "
        f"{report.latency_target_ms:.0f} ms: "
        f"{report.latency_compliance_rate:.3%}"
    )


# =============================================================================
# 53. REQUEST SIZE AND THROUGHPUT
# =============================================================================

def data_throughput(
    bytes_processed: int,
    duration_seconds: float,
) -> float:
    """Calculate byte throughput."""

    if bytes_processed < 0:
        raise ValueError(
            "bytes_processed cannot be negative"
        )

    if duration_seconds <= 0:
        raise ValueError(
            "duration_seconds must be greater than zero"
        )

    return bytes_processed / duration_seconds


def request_size_example() -> None:
    small_request_capacity = 10_000
    small_request_size = 1_000

    large_request_capacity = 1_000
    large_request_size = 100_000

    small_data_rate = (
        small_request_capacity
        * small_request_size
    )

    large_data_rate = (
        large_request_capacity
        * large_request_size
    )

    print("\n53. REQUESTS/SECOND VERSUS DATA THROUGHPUT")
    print(
        f"Small requests: "
        f"{small_request_capacity:,} requests/s, "
        f"{small_data_rate / 1_000_000:.2f} MB/s"
    )
    print(
        f"Large requests: "
        f"{large_request_capacity:,} requests/s, "
        f"{large_data_rate / 1_000_000:.2f} MB/s"
    )

    # Requests per second alone does not completely describe capacity.
    # Request size, CPU cost, memory use, and downstream work also matter.


# =============================================================================
# 54. COST PER REQUEST
# =============================================================================

def cost_per_request(
    infrastructure_cost: float,
    requests_processed: int,
) -> float:
    if infrastructure_cost < 0:
        raise ValueError(
            "infrastructure_cost cannot be negative"
        )

    if requests_processed <= 0:
        raise ValueError(
            "requests_processed must be greater than zero"
        )

    return (
        infrastructure_cost
        / requests_processed
    )


def cost_example() -> None:
    cost = cost_per_request(
        infrastructure_cost=250.0,
        requests_processed=5_000_000,
    )

    print("\n54. COST PER REQUEST")
    print(
        f"Cost per request: ${cost:.8f}"
    )

    # Optimizing throughput can reduce cost per unit of work,
    # but aggressive utilization can worsen tail latency.


# =============================================================================
# 55. PERFORMANCE MEASUREMENT PITFALLS
# =============================================================================

def measurement_pitfalls() -> None:
    print("\n55. PERFORMANCE MEASUREMENT PITFALLS")

    pitfalls = [
        "Using only average latency.",
        "Ignoring warm-up behavior.",
        "Benchmarking with unrealistic request sizes.",
        "Testing without realistic concurrency.",
        "Ignoring network and dependency latency.",
        "Comparing measurements from different environments.",
        "Using wall-clock time for short benchmark durations.",
        "Treating maximum observed throughput as sustainable capacity.",
        "Increasing load without monitoring error rate.",
        "Ignoring queueing delay.",
    ]

    for number, pitfall in enumerate(
        pitfalls,
        start=1,
    ):
        print(f"{number}. {pitfall}")


# =============================================================================
# 56. SIMPLE LOAD TEST HARNESS
# =============================================================================

@dataclass
class LoadTestResult:
    attempted: int
    completed: int
    failed: int
    elapsed_seconds: float
    latencies_ms: list[float]

    @property
    def throughput(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0

        return (
            self.completed
            / self.elapsed_seconds
        )

    def metrics(self) -> dict[str, float]:
        if not self.latencies_ms:
            return {
                "throughput": self.throughput,
            }

        result = latency_statistics(
            self.latencies_ms
        )

        result["throughput"] = self.throughput
        result["error_rate"] = (
            self.failed
            / self.attempted
            if self.attempted
            else 0.0
        )

        return result


def run_load_test(
    operation: Callable[[], Any],
    total_requests: int,
    concurrency: int,
) -> LoadTestResult:
    """
    Run a simple closed-loop concurrent load test.

    Each worker receives requests through the executor.
    This is useful for demonstration but is not a complete production
    benchmarking framework.
    """

    if total_requests <= 0:
        raise ValueError(
            "total_requests must be greater than zero"
        )

    if concurrency <= 0:
        raise ValueError(
            "concurrency must be greater than zero"
        )

    latencies: list[float] = []
    completed = 0
    failed = 0

    result_lock = threading.Lock()

    def timed_operation() -> None:
        nonlocal completed, failed

        start = time.perf_counter()

        try:
            operation()
        except Exception:
            with result_lock:
                failed += 1
        else:
            elapsed_ms = (
                time.perf_counter() - start
            ) * 1_000

            with result_lock:
                completed += 1
                latencies.append(elapsed_ms)

    overall_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency
    ) as executor:
        futures = [
            executor.submit(timed_operation)
            for _ in range(total_requests)
        ]

        for future in futures:
            future.result()

    elapsed = (
        time.perf_counter()
        - overall_start
    )

    return LoadTestResult(
        attempted=total_requests,
        completed=completed,
        failed=failed,
        elapsed_seconds=elapsed,
        latencies_ms=latencies,
    )


def load_test_example() -> None:
    def service() -> None:
        # Simulate variable service time.
        time.sleep(
            random.uniform(0.001, 0.005)
        )

    random.seed(123)

    result = run_load_test(
        operation=service,
        total_requests=100,
        concurrency=10,
    )

    print("\n56. SIMPLE LOAD TEST")

    for name, value in result.metrics().items():
        if name == "throughput":
            print(
                f"{name:12}: "
                f"{value:.2f} requests/second"
            )
        elif name == "error_rate":
            print(
                f"{name:12}: "
                f"{value:.2%}"
            )
        else:
            print(
                f"{name:12}: "
                f"{value:.3f} ms"
            )


# =============================================================================
# 57. PRODUCTION MONITORING MODEL
# =============================================================================

@dataclass
class PerformanceSnapshot:
    timestamp: float
    requests: int
    errors: int
    average_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    queue_depth: int
    cpu_utilization: float
    memory_utilization: float


def production_monitoring_example() -> None:
    snapshot = PerformanceSnapshot(
        timestamp=time.time(),
        requests=12_000,
        errors=30,
        average_latency_ms=45,
        p95_latency_ms=110,
        p99_latency_ms=350,
        queue_depth=120,
        cpu_utilization=0.82,
        memory_utilization=0.65,
    )

    error_rate = (
        snapshot.errors
        / snapshot.requests
    )

    print("\n57. PRODUCTION MONITORING SNAPSHOT")
    print(
        f"Requests:       "
        f"{snapshot.requests:,}"
    )
    print(
        f"Error rate:     "
        f"{error_rate:.2%}"
    )
    print(
        f"Average latency:"
        f" {snapshot.average_latency_ms:.1f} ms"
    )
    print(
        f"p95 latency:    "
        f"{snapshot.p95_latency_ms:.1f} ms"
    )
    print(
        f"p99 latency:    "
        f"{snapshot.p99_latency_ms:.1f} ms"
    )
    print(
        f"Queue depth:    "
        f"{snapshot.queue_depth}"
    )
    print(
        f"CPU utilization:"
        f" {snapshot.cpu_utilization:.1%}"
    )
    print(
        f"Memory usage:   "
        f"{snapshot.memory_utilization:.1%}"
    )


# =============================================================================
# 58. DIAGNOSING COMMON PERFORMANCE PATTERNS
# =============================================================================

def diagnose_performance(
    cpu_utilization: float,
    queue_depth: int,
    error_rate: float,
    p99_latency_ms: float,
) -> str:
    """
    Very simplified diagnostic logic.

    Real diagnosis requires workload, dependency, host, network,
    storage, and application-level evidence.
    """

    if error_rate > 0.1:
        return (
            "High error rate: inspect failures, dependency health, "
            "timeouts, saturation, and overload behavior."
        )

    if queue_depth > 1_000:
        return (
            "Large queue: arrival rate may exceed service capacity."
        )

    if (
        cpu_utilization > 0.9
        and p99_latency_ms > 500
    ):
        return (
            "CPU saturation with high tail latency: inspect CPU-bound "
            "work, contention, inefficient algorithms, and scaling."
        )

    if (
        cpu_utilization < 0.5
        and p99_latency_ms > 500
    ):
        return (
            "High latency without local CPU saturation: inspect "
            "downstream dependencies, I/O waits, locks, and network delay."
        )

    return (
        "No simple diagnosis from these metrics alone."
    )


def diagnosis_example() -> None:
    diagnosis = diagnose_performance(
        cpu_utilization=0.35,
        queue_depth=80,
        error_rate=0.01,
        p99_latency_ms=900,
    )

    print("\n58. PERFORMANCE DIAGNOSIS")
    print(diagnosis)


# =============================================================================
# 59. SECURITY CONSIDERATIONS RELATED TO PERFORMANCE
# =============================================================================

def security_performance_considerations() -> None:
    print("\n59. SECURITY AND PERFORMANCE")

    considerations = [
        "Rate limiting can reduce abuse-driven overload.",
        "Input size limits can prevent excessive memory and CPU consumption.",
        "Timeouts reduce exposure to indefinitely slow dependencies.",
        "Bounded queues can reduce resource exhaustion.",
        "Authentication and encryption add processing overhead.",
        "Caching sensitive data requires access-control and freshness controls.",
        "Performance optimizations must not bypass authorization checks.",
    ]

    for item in considerations:
        print(f"- {item}")


# =============================================================================
# 60. END-TO-END SYSTEM SIMULATION
# =============================================================================

@dataclass
class ServiceStage:
    name: str
    service_time_ms: float
    capacity_rps: float


def end_to_end_system_example() -> None:
    """
    Model a simple request path.

    Serial latency is approximately the sum of service times.
    Throughput capacity is constrained by the lowest stage capacity.
    """

    stages = [
        ServiceStage(
            "API Gateway",
            service_time_ms=5,
            capacity_rps=5_000,
        ),
        ServiceStage(
            "Application",
            service_time_ms=20,
            capacity_rps=1_500,
        ),
        ServiceStage(
            "Database",
            service_time_ms=40,
            capacity_rps=800,
        ),
        ServiceStage(
            "Response Encoding",
            service_time_ms=5,
            capacity_rps=10_000,
        ),
    ]

    total_service_latency = sum(
        stage.service_time_ms
        for stage in stages
    )

    bottleneck = min(
        stages,
        key=lambda stage: stage.capacity_rps,
    )

    print("\n60. END-TO-END SYSTEM MODEL")

    for stage in stages:
        print(
            f"{stage.name:20} | "
            f"Latency={stage.service_time_ms:5.1f} ms | "
            f"Capacity={stage.capacity_rps:7.0f}/s"
        )

    print(
        f"Serial service latency: "
        f"{total_service_latency:.1f} ms"
    )

    print(
        f"Bottleneck: {bottleneck.name} "
        f"({bottleneck.capacity_rps:.0f}/s)"
    )


# =============================================================================
# 61. CAPACITY PLANNING
# =============================================================================

def required_workers(
    target_throughput: float,
    average_service_time_seconds: float,
    target_utilization: float = 0.7,
) -> int:
    """
    Estimate worker count while reserving utilization headroom.

    worker_count >= target_throughput * service_time / target_utilization
    """

    if target_throughput <= 0:
        raise ValueError(
            "target_throughput must be greater than zero"
        )

    if average_service_time_seconds <= 0:
        raise ValueError(
            "average_service_time_seconds must be greater than zero"
        )

    if not 0 < target_utilization <= 1:
        raise ValueError(
            "target_utilization must be in (0, 1]"
        )

    raw_workers = (
        target_throughput
        * average_service_time_seconds
        / target_utilization
    )

    return math.ceil(raw_workers)


def capacity_planning_example() -> None:
    workers = required_workers(
        target_throughput=1_000,
        average_service_time_seconds=0.02,
        target_utilization=0.7,
    )

    print("\n61. CAPACITY PLANNING")
    print(
        f"Estimated workers required: {workers}"
    )

    # This estimate assumes relatively uniform work.
    # Production capacity planning should also consider:
    # - p95/p99 service time
    # - traffic bursts
    # - failures
    # - uneven partitioning
    # - deployment capacity
    # - dependency limits
    # - redundancy requirements


# =============================================================================
# 62. COMMON MISTAKES
# =============================================================================

def common_mistakes() -> None:
    mistakes = [
        "Assuming lower average latency guarantees good user experience.",
        "Measuring only successful requests and ignoring failures.",
        "Calling peak benchmark throughput sustainable capacity.",
        "Increasing concurrency without checking bottlenecks.",
        "Using unbounded queues during overload.",
        "Ignoring p95 and p99 latency.",
        "Adding retries without backoff or limits.",
        "Scaling application servers while the database is the bottleneck.",
        "Assuming more threads always increase CPU-bound throughput.",
        "Comparing benchmark numbers from different workloads.",
        "Ignoring cold starts and cache state.",
        "Optimizing a component that is not on the critical path.",
    ]

    print("\n62. COMMON MISTAKES")

    for index, mistake in enumerate(
        mistakes,
        start=1,
    ):
        print(f"{index}. {mistake}")


# =============================================================================
# 63. FINAL COMPARISON TABLE
# =============================================================================

def comparison_table() -> None:
    print("\n63. KEY DISTINCTIONS")

    rows = [
        (
            "Latency",
            "Time required for one operation",
            "milliseconds or seconds",
        ),
        (
            "Throughput",
            "Completed work per unit time",
            "requests/second",
        ),
        (
            "Capacity",
            "Maximum sustainable throughput",
            "requests/second",
        ),
        (
            "Service time",
            "Active processing time",
            "milliseconds or seconds",
        ),
        (
            "Waiting time",
            "Time spent in queue",
            "milliseconds or seconds",
        ),
        (
            "Response time",
            "Waiting + service + other delays",
            "milliseconds or seconds",
        ),
        (
            "Utilization",
            "Fraction of resource capacity in use",
            "percentage",
        ),
    ]

    for concept, definition, unit in rows:
        print(
            f"{concept:15} | "
            f"{definition:42} | "
            f"{unit}"
        )


# =============================================================================
# 64. MAIN
# =============================================================================

def main() -> None:
    """
    Execute all demonstrations.

    Small sleep-based simulations intentionally create visible timing behavior.
    Actual values vary by machine, operating system, system load, and Python
    runtime conditions.
    """

    print("=" * 72)
    print("LATENCY AND THROUGHPUT: RESPONSE TIME, REQUESTS/SECOND, CAPACITY")
    print("=" * 72)

    measure_single_operation()
    timer_comparison()
    throughput_example()
    response_time_breakdown_example()
    percentile_example()
    sequential_processing_example()
    concurrent_processing_example()
    latency_throughput_relationship()
    capacity_example()
    bottleneck_example()
    littles_law_example()
    utilization_example()
    queue_simulation_example()
    queue_growth_example()
    multi_server_example()
    average_vs_tail_example()
    histogram_example()
    benchmark_example()
    cold_start_example()
    cpu_vs_io_example()
    io_concurrency_example()
    asynchronous_concept_example()
    batching_example()
    caching_example()
    cache_stampede_example()
    backpressure_example()
    rate_limiting_example()
    connection_pool_example()
    amdahl_example()
    scaling_concepts()
    load_balancing_example()
    load_balancing_tradeoffs()
    head_of_line_blocking_example()
    timeout_example()
    retry_example()
    circuit_breaker_example()
    latency_budget_example()
    tail_latency_amplification_example()
    dependency_latency_example()
    coordinated_omission_explanation()
    closed_loop_vs_open_loop()
    open_loop_example()
    memory_queue_consideration()
    priority_queue_example()
    fairness_example()
    measurement_boundaries()
    clock_skew_example()
    performance_regression_example()
    non_linear_scaling_example()
    lock_contention_example()
    buffering_tradeoff_example()
    service_level_example()
    request_size_example()
    cost_example()
    measurement_pitfalls()
    load_test_example()
    production_monitoring_example()
    diagnosis_example()
    security_performance_considerations()
    end_to_end_system_example()
    capacity_planning_example()
    common_mistakes()
    comparison_table()

    print("\n" + "=" * 72)
    print("END OF STUDY SCRIPT")
    print("=" * 72)


if __name__ == "__main__":
    main()
