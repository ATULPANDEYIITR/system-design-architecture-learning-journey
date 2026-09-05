"""
SCALABILITY FUNDAMENTALS
========================

A comprehensive, self-contained Python study program covering:

1. Scalability terminology and fundamentals
2. Vertical scaling
3. Horizontal scaling
4. Scaling bottlenecks
5. Capacity, throughput, latency, concurrency, and utilization
6. Little's Law
7. Load testing concepts and simulation
8. Stateless and stateful application design
9. Load balancing
10. Database scaling
11. Caching
12. Connection pooling
13. Queues and asynchronous processing
14. Backpressure
15. Rate limiting
16. Sharding and partitioning
17. Replication
18. Read/write scaling
19. Hotspots
20. Idempotency
21. Autoscaling
22. Fault tolerance and graceful degradation
23. Cost and scaling trade-offs
24. Performance modeling
25. Capacity planning
26. Bottleneck detection
27. Architecture comparison
28. Testing and validation
29. Security considerations
30. Production design principles

The script intentionally uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from random import Random
from statistics import mean, median
from time import perf_counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ============================================================================
# 1. BASIC TERMINOLOGY
# ============================================================================

def explain_scalability_terms() -> None:
    """
    Introduce the measurements that are repeatedly used when reasoning about
    scalable systems.
    """
    print("\n" + "=" * 80)
    print("1. SCALABILITY FUNDAMENTALS")
    print("=" * 80)

    terms = {
        "Scalability":
            "The ability of a system to handle increasing workload by adding resources.",
        "Throughput":
            "The amount of work completed per unit of time, such as requests/second.",
        "Latency":
            "The time required to complete an individual operation.",
        "Concurrency":
            "The number of operations that are in progress at the same time.",
        "Capacity":
            "The maximum sustainable workload under specified constraints.",
        "Utilization":
            "The proportion of a resource's available capacity currently being used.",
        "Bottleneck":
            "The constrained component that limits system performance or capacity.",
        "Availability":
            "The proportion of time a system is operational and accessible.",
        "Elasticity":
            "The ability to dynamically add or remove resources as workload changes.",
        "Load":
            "The work imposed on a system, such as requests, jobs, users, or data volume.",
    }

    for name, definition in terms.items():
        print(f"{name:15}: {definition}")


# ============================================================================
# 2. WORKLOAD MODEL
# ============================================================================

@dataclass
class Workload:
    """
    Represents a simplified application workload.

    request_rate:
        Incoming requests per second.

    average_service_time:
        Average processing time for one request in seconds.

    concurrency:
        Number of simultaneously active requests.

    This is deliberately simplified so that the relationships between
    scalability metrics remain visible.
    """

    request_rate: float
    average_service_time: float
    concurrency: int = 1

    def __post_init__(self) -> None:
        if self.request_rate < 0:
            raise ValueError("Request rate cannot be negative.")

        if self.average_service_time < 0:
            raise ValueError("Service time cannot be negative.")

        if self.concurrency < 0:
            raise ValueError("Concurrency cannot be negative.")

    @property
    def offered_work(self) -> float:
        """Return CPU-like service demand in seconds of work per second."""
        return self.request_rate * self.average_service_time


def demonstrate_workload() -> None:
    print("\n2. WORKLOAD MODEL")

    workload = Workload(
        request_rate=500,
        average_service_time=0.020,
        concurrency=10,
    )

    print(f"Request rate: {workload.request_rate} requests/s")
    print(f"Average service time: {workload.average_service_time:.3f} s")
    print(f"Concurrency: {workload.concurrency}")
    print(f"Offered service demand: {workload.offered_work:.2f} CPU-seconds/s")


# ============================================================================
# 3. VERTICAL SCALING
# ============================================================================

@dataclass
class Server:
    """
    A simplified server capacity model.

    capacity_rps represents sustainable throughput at the selected hardware
    configuration.
    """

    name: str
    cpu_cores: int
    memory_gb: float
    capacity_rps: float

    def __post_init__(self) -> None:
        if self.cpu_cores <= 0:
            raise ValueError("CPU cores must be positive.")

        if self.memory_gb <= 0:
            raise ValueError("Memory must be positive.")

        if self.capacity_rps <= 0:
            raise ValueError("Capacity must be positive.")


def vertical_scale(
    server: Server,
    cpu_multiplier: float,
    memory_multiplier: float,
    capacity_multiplier: float,
) -> Server:
    """
    Simulate vertical scaling.

    Vertical scaling means increasing the resources of an existing machine.

    Example:
        4 CPU cores -> 8 CPU cores
        16 GB RAM -> 32 GB RAM

    Real systems rarely scale linearly because applications encounter
    bottlenecks in CPUs, memory bandwidth, disks, network interfaces,
    software locks, databases, or external dependencies.
    """
    if min(cpu_multiplier, memory_multiplier, capacity_multiplier) <= 0:
        raise ValueError("Scaling multipliers must be positive.")

    return Server(
        name=server.name,
        cpu_cores=ceil(server.cpu_cores * cpu_multiplier),
        memory_gb=server.memory_gb * memory_multiplier,
        capacity_rps=server.capacity_rps * capacity_multiplier,
    )


def demonstrate_vertical_scaling() -> None:
    print("\n3. VERTICAL SCALING")

    original = Server(
        name="application-server-01",
        cpu_cores=4,
        memory_gb=16,
        capacity_rps=1000,
    )

    scaled = vertical_scale(
        original,
        cpu_multiplier=2,
        memory_multiplier=2,
        capacity_multiplier=1.8,
    )

    print("Before:")
    print(original)

    print("\nAfter vertical scaling:")
    print(scaled)

    print(
        "\nVertical scaling increases the capacity of an existing machine "
        "rather than increasing the number of machines."
    )


# ============================================================================
# 4. HORIZONTAL SCALING
# ============================================================================

def horizontal_capacity(
    server_capacity_rps: float,
    server_count: int,
) -> float:
    """
    Estimate total capacity for independent servers.

    This assumes perfect distribution and no coordination overhead.

    Real systems normally achieve less than perfect linear scaling.
    """
    if server_capacity_rps <= 0:
        raise ValueError("Server capacity must be positive.")

    if server_count <= 0:
        raise ValueError("Server count must be positive.")

    return server_capacity_rps * server_count


def demonstrate_horizontal_scaling() -> None:
    print("\n4. HORIZONTAL SCALING")

    capacity_per_server = 1000

    for server_count in [1, 2, 4, 8]:
        capacity = horizontal_capacity(
            capacity_per_server,
            server_count,
        )

        print(
            f"{server_count} servers -> theoretical capacity "
            f"{capacity:.0f} requests/s"
        )


# ============================================================================
# 5. SCALING EFFICIENCY
# ============================================================================

def horizontal_scaling_efficiency(
    actual_capacity: float,
    baseline_capacity: float,
    server_count: int,
) -> float:
    """
    Measure horizontal scaling efficiency.

    Ideal capacity after N servers:

        baseline_capacity * N

    Efficiency:

        actual_capacity / ideal_capacity

    An efficiency of 1.0 means perfect linear scaling.
    """
    if baseline_capacity <= 0 or server_count <= 0:
        raise ValueError("Baseline capacity and server count must be positive.")

    ideal_capacity = baseline_capacity * server_count

    return actual_capacity / ideal_capacity


def demonstrate_scaling_efficiency() -> None:
    print("\n5. HORIZONTAL SCALING EFFICIENCY")

    baseline = 1000
    actual = 7200
    servers = 8

    efficiency = horizontal_scaling_efficiency(
        actual,
        baseline,
        servers,
    )

    print(f"Baseline capacity: {baseline} requests/s")
    print(f"Servers: {servers}")
    print(f"Actual capacity: {actual} requests/s")
    print(f"Scaling efficiency: {efficiency:.1%}")


# ============================================================================
# 6. THROUGHPUT AND UTILIZATION
# ============================================================================

def utilization(
    incoming_rate: float,
    sustainable_capacity: float,
) -> float:
    """
    Calculate resource/system utilization.

    Values above 1.0 indicate that incoming demand exceeds sustainable
    capacity.

    High utilization can cause queue growth and rapidly increasing latency.
    """
    if incoming_rate < 0:
        raise ValueError("Incoming rate cannot be negative.")

    if sustainable_capacity <= 0:
        raise ValueError("Capacity must be positive.")

    return incoming_rate / sustainable_capacity


def demonstrate_utilization() -> None:
    print("\n6. UTILIZATION")

    capacity = 1000

    for rate in [300, 700, 900, 1000, 1200]:
        u = utilization(rate, capacity)

        print(
            f"Load={rate:4} req/s | utilization={u:5.1%} | "
            f"status={'OVER CAPACITY' if u > 1 else 'within capacity'}"
        )


# ============================================================================
# 7. LATENCY AND QUEUING
# ============================================================================

def approximate_latency(
    service_time: float,
    utilization_ratio: float,
) -> float:
    """
    Provide a simple queueing-inspired latency approximation.

    As utilization approaches 100%, waiting time can increase sharply.

    This is not a universal production latency equation. It is a teaching
    model illustrating why operating near maximum capacity can be dangerous.
    """
    if service_time <= 0:
        raise ValueError("Service time must be positive.")

    if utilization_ratio < 0:
        raise ValueError("Utilization cannot be negative.")

    if utilization_ratio >= 1:
        return float("inf")

    return service_time / (1 - utilization_ratio)


def demonstrate_latency_growth() -> None:
    print("\n7. LATENCY GROWTH AS CAPACITY IS APPROACHED")

    service_time = 0.010

    for ratio in [0.50, 0.70, 0.80, 0.90, 0.95, 0.99]:
        latency = approximate_latency(service_time, ratio)

        print(
            f"Utilization={ratio:.0%} -> "
            f"approximate latency={latency * 1000:.2f} ms"
        )


# ============================================================================
# 8. LITTLE'S LAW
# ============================================================================

def littles_law(
    throughput: float,
    average_latency: float,
) -> float:
    """
    Apply Little's Law:

        L = λW

    where:

        L = average number of items in the system
        λ = throughput
        W = average time spent in the system

    In request-processing systems this gives an approximation of average
    concurrent requests.
    """
    if throughput < 0:
        raise ValueError("Throughput cannot be negative.")

    if average_latency < 0:
        raise ValueError("Latency cannot be negative.")

    return throughput * average_latency


def demonstrate_littles_law() -> None:
    print("\n8. LITTLE'S LAW")

    throughput = 2000
    latency = 0.025

    concurrency = littles_law(
        throughput,
        latency,
    )

    print(f"Throughput: {throughput} requests/s")
    print(f"Average latency: {latency:.3f} s")
    print(f"Estimated concurrency: {concurrency:.1f}")


# ============================================================================
# 9. BOTTLENECK MODEL
# ============================================================================

@dataclass
class ComponentCapacity:
    """
    Represents the sustainable throughput of one system component.
    """

    name: str
    capacity_rps: float

    def __post_init__(self) -> None:
        if self.capacity_rps <= 0:
            raise ValueError("Capacity must be positive.")


def find_bottleneck(
    components: Sequence[ComponentCapacity],
) -> ComponentCapacity:
    """
    Return the component with the smallest sustainable capacity.

    In a simple serial pipeline, the slowest component limits end-to-end
    throughput.
    """
    if not components:
        raise ValueError("At least one component is required.")

    return min(
        components,
        key=lambda component: component.capacity_rps,
    )


def demonstrate_bottleneck_detection() -> None:
    print("\n9. BOTTLENECK DETECTION")

    components = [
        ComponentCapacity("API servers", 5000),
        ComponentCapacity("Cache", 10000),
        ComponentCapacity("Database", 1800),
        ComponentCapacity("Payment service", 2500),
    ]

    bottleneck = find_bottleneck(components)

    for component in components:
        print(
            f"{component.name:20} "
            f"{component.capacity_rps:7.0f} requests/s"
        )

    print(
        f"Bottleneck: {bottleneck.name} "
        f"({bottleneck.capacity_rps:.0f} requests/s)"
    )


# ============================================================================
# 10. BOTTLENECK TYPES
# ============================================================================

class BottleneckType(Enum):
    CPU = "CPU"
    MEMORY = "Memory"
    STORAGE = "Storage"
    NETWORK = "Network"
    DATABASE = "Database"
    LOCKING = "Locking"
    EXTERNAL_SERVICE = "External service"
    CONNECTION_POOL = "Connection pool"
    QUEUE = "Queue"
    SINGLE_THREADED_COMPONENT = "Single-threaded component"


def demonstrate_bottleneck_types() -> None:
    print("\n10. COMMON BOTTLENECK TYPES")

    for bottleneck_type in BottleneckType:
        print(f"- {bottleneck_type.value}")


# ============================================================================
# 11. LOAD BALANCING
# ============================================================================

@dataclass
class Backend:
    """
    A backend server participating in load balancing.
    """

    name: str
    capacity: float
    active_requests: int = 0

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("Backend capacity must be positive.")


class RoundRobinLoadBalancer:
    """
    Basic round-robin load balancer.

    Real load balancers can use health checks, weighted routing, least
    connections, latency-aware routing, consistent hashing, locality, and
    many other policies.
    """

    def __init__(self, backends: Sequence[Backend]) -> None:
        if not backends:
            raise ValueError("At least one backend is required.")

        self.backends = list(backends)
        self.next_index = 0

    def choose_backend(self) -> Backend:
        """
        Choose the next healthy backend in round-robin order.

        This simple implementation assumes all backends are healthy.
        """
        backend = self.backends[self.next_index]

        self.next_index = (
            self.next_index + 1
        ) % len(self.backends)

        return backend


def demonstrate_load_balancing() -> None:
    print("\n11. LOAD BALANCING")

    backends = [
        Backend("server-1", 1000),
        Backend("server-2", 1000),
        Backend("server-3", 1000),
    ]

    load_balancer = RoundRobinLoadBalancer(backends)

    assignments: Dict[str, int] = {
        backend.name: 0 for backend in backends
    }

    for _ in range(12):
        backend = load_balancer.choose_backend()
        assignments[backend.name] += 1

    print("Request distribution:")
    for name, count in assignments.items():
        print(f"{name}: {count} requests")


# ============================================================================
# 12. WEIGHTED LOAD BALANCING
# ============================================================================

class WeightedRoundRobin:
    """
    Simple deterministic weighted scheduler.

    A backend with weight 3 receives approximately three times as many
    scheduling opportunities as a backend with weight 1.
    """

    def __init__(self, weighted_backends: Sequence[Tuple[Backend, int]]) -> None:
        if not weighted_backends:
            raise ValueError("At least one backend is required.")

        for _, weight in weighted_backends:
            if weight <= 0:
                raise ValueError("Weights must be positive.")

        self.schedule: List[Backend] = []

        for backend, weight in weighted_backends:
            self.schedule.extend([backend] * weight)

        self.index = 0

    def choose(self) -> Backend:
        backend = self.schedule[self.index]
        self.index = (self.index + 1) % len(self.schedule)
        return backend


def demonstrate_weighted_load_balancing() -> None:
    print("\n12. WEIGHTED LOAD BALANCING")

    servers = [
        (Backend("small", 500), 1),
        (Backend("medium", 1000), 2),
        (Backend("large", 2000), 4),
    ]

    balancer = WeightedRoundRobin(servers)

    distribution: Dict[str, int] = {
        backend.name: 0
        for backend, _ in servers
    }

    for _ in range(70):
        distribution[balancer.choose().name] += 1

    for name, count in distribution.items():
        print(f"{name:10}: {count} assignments")


# ============================================================================
# 13. STATELESS APPLICATION DESIGN
# ============================================================================

@dataclass
class Request:
    """
    Simplified request object.
    """

    request_id: str
    user_id: str
    payload: str


class StatelessApplication:
    """
    A stateless application does not require local process memory to retain
    user session state between requests.

    State can instead live in shared systems such as a database or distributed
    cache, making requests easier to route to any healthy application server.
    """

    def process(self, request: Request, shared_store: Dict[str, str]) -> str:
        shared_store[request.user_id] = request.payload

        return (
            f"Processed request {request.request_id} "
            f"for user {request.user_id}"
        )


def demonstrate_stateless_design() -> None:
    print("\n13. STATELESS APPLICATION DESIGN")

    shared_store: Dict[str, str] = {}

    application_a = StatelessApplication()
    application_b = StatelessApplication()

    request_1 = Request("r1", "user-42", "first payload")
    request_2 = Request("r2", "user-42", "second payload")

    print(application_a.process(request_1, shared_store))
    print(application_b.process(request_2, shared_store))

    print(f"Shared state: {shared_store}")


# ============================================================================
# 14. STATEFUL APPLICATION DESIGN AND STICKY SESSIONS
# ============================================================================

class StatefulApplication:
    """
    A simplified stateful server that keeps session data locally.

    This design can be easy to build but introduces routing and failover
    considerations when multiple instances are used.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.sessions: Dict[str, str] = {}

    def set_session(self, user_id: str, value: str) -> None:
        self.sessions[user_id] = value

    def get_session(self, user_id: str) -> Optional[str]:
        return self.sessions.get(user_id)


def demonstrate_stateful_tradeoff() -> None:
    print("\n14. STATEFUL APPLICATION TRADE-OFF")

    server_a = StatefulApplication("server-a")
    server_b = StatefulApplication("server-b")

    server_a.set_session("user-1", "shopping-cart")

    print(
        "Session on server A:",
        server_a.get_session("user-1"),
    )

    print(
        "Same session on server B:",
        server_b.get_session("user-1"),
    )

    print(
        "A load balancer could use sticky sessions, "
        "but shared session storage is often more flexible."
    )


# ============================================================================
# 15. SIMPLE CACHE
# ============================================================================

@dataclass
class CacheEntry:
    value: object
    expires_at: Optional[float] = None


class SimpleCache:
    """
    Small in-memory cache supporting TTL expiration.

    Caching can reduce database load and improve latency, but introduces
    consistency and invalidation concerns.
    """

    def __init__(self) -> None:
        self.entries: Dict[str, CacheEntry] = {}

    def set(
        self,
        key: str,
        value: object,
        now: float,
        ttl: Optional[float] = None,
    ) -> None:
        if ttl is not None and ttl < 0:
            raise ValueError("TTL cannot be negative.")

        expiration = None if ttl is None else now + ttl

        self.entries[key] = CacheEntry(
            value=value,
            expires_at=expiration,
        )

    def get(
        self,
        key: str,
        now: float,
    ) -> Optional[object]:
        entry = self.entries.get(key)

        if entry is None:
            return None

        if (
            entry.expires_at is not None
            and now >= entry.expires_at
        ):
            del self.entries[key]
            return None

        return entry.value

    def delete(self, key: str) -> None:
        self.entries.pop(key, None)


def demonstrate_cache() -> None:
    print("\n15. CACHING")

    cache = SimpleCache()

    cache.set(
        "product:100",
        {"name": "Laptop", "price": 75000},
        now=0,
        ttl=30,
    )

    print("At t=10:", cache.get("product:100", now=10))
    print("At t=29:", cache.get("product:100", now=29))
    print("At t=30:", cache.get("product:100", now=30))

    print(
        "\nThe example demonstrates TTL expiration. "
        "Real caches also require an eviction policy and invalidation strategy."
    )


# ============================================================================
# 16. CACHE HIT RATE
# ============================================================================

def cache_hit_rate(
    hits: int,
    misses: int,
) -> float:
    """
    Calculate cache hit rate.

        hit rate = hits / (hits + misses)
    """
    if hits < 0 or misses < 0:
        raise ValueError("Hits and misses cannot be negative.")

    total = hits + misses

    if total == 0:
        return 0.0

    return hits / total


def demonstrate_cache_hit_rate() -> None:
    print("\n16. CACHE HIT RATE")

    hits = 9200
    misses = 800

    print(f"Hits: {hits}")
    print(f"Misses: {misses}")
    print(f"Hit rate: {cache_hit_rate(hits, misses):.2%}")


# ============================================================================
# 17. CACHE STRATEGIES
# ============================================================================

def demonstrate_cache_strategies() -> None:
    print("\n17. CACHE STRATEGIES")

    strategies = {
        "Cache-aside":
            "Application reads cache first and loads missing values from the database.",
        "Read-through":
            "Cache layer loads missing values on behalf of the application.",
        "Write-through":
            "Writes update the cache and backing store synchronously.",
        "Write-back":
            "Writes initially update the cache and are persisted later.",
        "Refresh-ahead":
            "Frequently accessed entries are refreshed before expiration.",
    }

    for strategy, explanation in strategies.items():
        print(f"{strategy:15}: {explanation}")


# ============================================================================
# 18. DATABASE CONNECTION POOLING
# ============================================================================

@dataclass
class ConnectionPool:
    """
    A conceptual database connection pool.

    Creating a new database connection for every request can be expensive.
    A pool reuses a bounded number of existing connections.
    """

    max_connections: int
    active_connections: int = 0

    def __post_init__(self) -> None:
        if self.max_connections <= 0:
            raise ValueError("Maximum connections must be positive.")

    def acquire(self) -> bool:
        if self.active_connections >= self.max_connections:
            return False

        self.active_connections += 1
        return True

    def release(self) -> None:
        if self.active_connections <= 0:
            raise RuntimeError("No active connection to release.")

        self.active_connections -= 1


def demonstrate_connection_pooling() -> None:
    print("\n18. DATABASE CONNECTION POOLING")

    pool = ConnectionPool(max_connections=3)

    for request_number in range(5):
        acquired = pool.acquire()

        print(
            f"Request {request_number + 1}: "
            f"{'connection acquired' if acquired else 'pool exhausted'}"
        )

    print(f"Active connections: {pool.active_connections}")

    while pool.active_connections:
        pool.release()

    print(f"Active connections after release: {pool.active_connections}")


# ============================================================================
# 19. DATABASE READ REPLICAS
# ============================================================================

@dataclass
class DatabaseNode:
    name: str
    role: str
    capacity_rps: int


def demonstrate_read_replication() -> None:
    print("\n19. DATABASE READ REPLICATION")

    nodes = [
        DatabaseNode("db-primary", "primary", 2000),
        DatabaseNode("db-replica-1", "read replica", 2000),
        DatabaseNode("db-replica-2", "read replica", 2000),
    ]

    for node in nodes:
        print(
            f"{node.name:15} | "
            f"{node.role:12} | "
            f"{node.capacity_rps} reads/s"
        )

    print(
        "\nRead replicas can distribute read workload, but replication "
        "lag can create stale-read behavior."
    )


# ============================================================================
# 20. REPLICATION LAG
# ============================================================================

@dataclass
class Replica:
    name: str
    replication_lag_seconds: float

    def is_fresh(self, maximum_allowed_lag: float) -> bool:
        return self.replication_lag_seconds <= maximum_allowed_lag


def demonstrate_replication_lag() -> None:
    print("\n20. REPLICATION LAG")

    replicas = [
        Replica("replica-1", 0.2),
        Replica("replica-2", 1.8),
        Replica("replica-3", 4.5),
    ]

    allowed_lag = 2.0

    for replica in replicas:
        print(
            f"{replica.name}: "
            f"lag={replica.replication_lag_seconds:.1f}s, "
            f"fresh={replica.is_fresh(allowed_lag)}"
        )


# ============================================================================
# 21. DATABASE SHARDING
# ============================================================================

def shard_by_modulo(
    key: int,
    shard_count: int,
) -> int:
    """
    Simple modulo-based sharding.

    shard = key % shard_count

    This is easy to understand but changing the number of shards can cause
    many keys to move. Consistent hashing can reduce movement in some
    architectures.
    """
    if shard_count <= 0:
        raise ValueError("Shard count must be positive.")

    return key % shard_count


def demonstrate_sharding() -> None:
    print("\n21. DATABASE SHARDING")

    shard_count = 4

    for user_id in range(1001, 1011):
        shard = shard_by_modulo(user_id, shard_count)

        print(
            f"user_id={user_id} -> shard-{shard}"
        )


# ============================================================================
# 22. HOT PARTITIONS
# ============================================================================

def identify_hot_shards(
    shard_loads: Dict[int, int],
    threshold: int,
) -> List[int]:
    """
    Identify shards whose load exceeds a specified threshold.
    """
    if threshold < 0:
        raise ValueError("Threshold cannot be negative.")

    return [
        shard
        for shard, load in shard_loads.items()
        if load > threshold
    ]


def demonstrate_hot_shards() -> None:
    print("\n22. HOT PARTITIONS")

    shard_loads = {
        0: 1000,
        1: 1100,
        2: 9800,
        3: 1050,
    }

    hot = identify_hot_shards(
        shard_loads,
        threshold=3000,
    )

    print(f"Shard loads: {shard_loads}")
    print(f"Hot shards: {hot}")

    print(
        "A hot shard can limit the capacity of an otherwise large "
        "distributed database."
    )


# ============================================================================
# 23. QUEUES AND ASYNCHRONOUS PROCESSING
# ============================================================================

@dataclass
class Job:
    job_id: str
    payload: str


class JobQueue:
    """
    Minimal FIFO queue abstraction.

    Queues allow request handling and expensive background work to be
    separated, which can improve responsiveness and absorb temporary bursts.
    """

    def __init__(self) -> None:
        self.jobs: List[Job] = []

    def enqueue(self, job: Job) -> None:
        self.jobs.append(job)

    def dequeue(self) -> Optional[Job]:
        if not self.jobs:
            return None

        return self.jobs.pop(0)

    def depth(self) -> int:
        return len(self.jobs)


def demonstrate_queue() -> None:
    print("\n23. QUEUES AND ASYNCHRONOUS PROCESSING")

    queue = JobQueue()

    for number in range(1, 6):
        queue.enqueue(
            Job(
                job_id=f"job-{number}",
                payload=f"process-{number}",
            )
        )

    print(f"Queue depth: {queue.depth()}")

    while queue.depth():
        job = queue.dequeue()
        print(f"Worker processing: {job.job_id}")


# ============================================================================
# 24. QUEUE BACKLOG
# ============================================================================

def queue_backlog_after_interval(
    incoming_jobs_per_second: float,
    processing_jobs_per_second: float,
    seconds: float,
) -> float:
    """
    Estimate backlog growth under a constant arrival and processing rate.

    backlog_change = (arrival_rate - processing_rate) * time

    This simplified model ignores retries, priority, batching, variable
    service times, and failures.
    """
    if min(
        incoming_jobs_per_second,
        processing_jobs_per_second,
        seconds,
    ) < 0:
        raise ValueError("Rates and time cannot be negative.")

    return max(
        0.0,
        (
            incoming_jobs_per_second
            - processing_jobs_per_second
        ) * seconds,
    )


def demonstrate_queue_backlog() -> None:
    print("\n24. QUEUE BACKLOG")

    backlog = queue_backlog_after_interval(
        incoming_jobs_per_second=1200,
        processing_jobs_per_second=1000,
        seconds=30,
    )

    print(f"Backlog after 30 seconds: {backlog:.0f} jobs")

    print(
        "If arrivals continuously exceed processing capacity, "
        "the queue grows until a resource limit is reached."
    )


# ============================================================================
# 25. BACKPRESSURE
# ============================================================================

class BackpressureController:
    """
    Simple backpressure model.

    When the queue exceeds a threshold, producers should slow down,
    reject work, shed optional work, or otherwise prevent unbounded growth.
    """

    def __init__(self, maximum_queue_depth: int) -> None:
        if maximum_queue_depth <= 0:
            raise ValueError("Maximum queue depth must be positive.")

        self.maximum_queue_depth = maximum_queue_depth

    def accept(self, queue_depth: int) -> bool:
        if queue_depth < 0:
            raise ValueError("Queue depth cannot be negative.")

        return queue_depth < self.maximum_queue_depth


def demonstrate_backpressure() -> None:
    print("\n25. BACKPRESSURE")

    controller = BackpressureController(
        maximum_queue_depth=1000
    )

    for depth in [100, 700, 999, 1000, 1500]:
        print(
            f"Queue depth={depth:4} -> "
            f"accept new work={controller.accept(depth)}"
        )


# ============================================================================
# 26. RATE LIMITING
# ============================================================================

@dataclass
class FixedWindowRateLimiter:
    """
    Simple fixed-window rate limiter.

    This implementation is intentionally deterministic and conceptual.
    Distributed rate limiting requires shared state and careful clock and
    consistency handling.
    """

    limit: int
    window_seconds: int
    current_window: int = 0
    requests_in_window: int = 0

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("Limit must be positive.")

        if self.window_seconds <= 0:
            raise ValueError("Window must be positive.")

    def allow(self, timestamp: int) -> bool:
        window = timestamp // self.window_seconds

        if window != self.current_window:
            self.current_window = window
            self.requests_in_window = 0

        if self.requests_in_window >= self.limit:
            return False

        self.requests_in_window += 1
        return True


def demonstrate_rate_limiting() -> None:
    print("\n26. RATE LIMITING")

    limiter = FixedWindowRateLimiter(
        limit=3,
        window_seconds=10,
    )

    for timestamp in [1, 2, 3, 4, 5, 11, 12]:
        print(
            f"t={timestamp:2}: "
            f"allowed={limiter.allow(timestamp)}"
        )


# ============================================================================
# 27. TOKEN BUCKET RATE LIMITING
# ============================================================================

class TokenBucket:
    """
    Token-bucket rate limiter.

    Tokens accumulate at a configured refill rate up to a maximum capacity.
    Each request consumes tokens.

    This allows controlled bursts while maintaining a long-term rate limit.
    """

    def __init__(
        self,
        capacity: float,
        refill_rate: float,
    ) -> None:
        if capacity <= 0:
            raise ValueError("Capacity must be positive.")

        if refill_rate <= 0:
            raise ValueError("Refill rate must be positive.")

        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_time = 0.0

    def allow(
        self,
        now: float,
        cost: float = 1.0,
    ) -> bool:
        if cost <= 0:
            raise ValueError("Token cost must be positive.")

        if now < self.last_time:
            raise ValueError("Time cannot move backward.")

        elapsed = now - self.last_time

        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate,
        )

        self.last_time = now

        if self.tokens < cost:
            return False

        self.tokens -= cost
        return True


def demonstrate_token_bucket() -> None:
    print("\n27. TOKEN BUCKET")

    bucket = TokenBucket(
        capacity=5,
        refill_rate=1,
    )

    for second in [0, 0, 0, 0, 0, 0, 0, 1, 2, 3]:
        print(
            f"t={second}: allowed={bucket.allow(second)} "
            f"remaining={bucket.tokens:.2f}"
        )


# ============================================================================
# 28. IDEMPOTENCY
# ============================================================================

class IdempotencyStore:
    """
    Store completed operation identifiers.

    Idempotency is important when distributed systems retry requests.
    """

    def __init__(self) -> None:
        self.completed: Dict[str, object] = {}

    def execute_once(
        self,
        operation_id: str,
        operation,
    ) -> object:
        if operation_id in self.completed:
            return self.completed[operation_id]

        result = operation()
        self.completed[operation_id] = result

        return result


def demonstrate_idempotency() -> None:
    print("\n28. IDEMPOTENCY")

    store = IdempotencyStore()
    counter = {"value": 0}

    def charge_customer() -> str:
        counter["value"] += 1
        return f"charge-{counter['value']}"

    first = store.execute_once("payment-123", charge_customer)
    second = store.execute_once("payment-123", charge_customer)

    print(f"First attempt:  {first}")
    print(f"Retry attempt:  {second}")
    print(f"Actual executions: {counter['value']}")

    print(
        "The same idempotency key prevents a retry from creating "
        "a duplicate logical operation."
    )


# ============================================================================
# 29. AUTOSCALING
# ============================================================================

@dataclass
class AutoScaler:
    """
    Simple target-utilization autoscaler.

    The model estimates how many instances are needed to keep utilization
    near a target.
    """

    per_instance_capacity: float
    target_utilization: float
    minimum_instances: int
    maximum_instances: int

    def __post_init__(self) -> None:
        if self.per_instance_capacity <= 0:
            raise ValueError("Instance capacity must be positive.")

        if not 0 < self.target_utilization <= 1:
            raise ValueError("Target utilization must be in (0, 1].")

        if self.minimum_instances <= 0:
            raise ValueError("Minimum instances must be positive.")

        if self.maximum_instances < self.minimum_instances:
            raise ValueError("Maximum must be >= minimum.")

    def required_instances(self, incoming_rate: float) -> int:
        if incoming_rate < 0:
            raise ValueError("Incoming rate cannot be negative.")

        effective_capacity = (
            self.per_instance_capacity
            * self.target_utilization
        )

        required = ceil(
            incoming_rate / effective_capacity
        )

        return min(
            self.maximum_instances,
            max(self.minimum_instances, required),
        )


def demonstrate_autoscaling() -> None:
    print("\n29. AUTOSCALING")

    scaler = AutoScaler(
        per_instance_capacity=1000,
        target_utilization=0.70,
        minimum_instances=2,
        maximum_instances=20,
    )

    for rate in [500, 1000, 2000, 5000, 10000, 20000]:
        instances = scaler.required_instances(rate)

        print(
            f"{rate:5} req/s -> {instances:2} instances"
        )


# ============================================================================
# 30. AUTOSCALING LIMITATIONS
# ============================================================================

def demonstrate_autoscaling_limitations() -> None:
    print("\n30. AUTOSCALING LIMITATIONS")

    limitations = [
        "New instances take time to start.",
        "Metrics can lag behind real workload changes.",
        "Scaling too aggressively can create cost spikes.",
        "Scaling too slowly can produce latency and availability problems.",
        "A downstream database may not scale at the same rate.",
        "Maximum instance limits can become hard capacity ceilings.",
        "Autoscaling cannot repair a fundamentally inefficient architecture.",
    ]

    for limitation in limitations:
        print(f"- {limitation}")


# ============================================================================
# 31. Amdahl's Law
# ============================================================================

def amdahl_speedup(
    parallel_fraction: float,
    workers: int,
) -> float:
    """
    Apply Amdahl's Law:

        Speedup = 1 / ((1-P) + P/N)

    P:
        Fraction of work that can be parallelized.

    N:
        Number of parallel workers.

    The serial fraction places an upper bound on scalability.
    """
    if not 0 <= parallel_fraction <= 1:
        raise ValueError("Parallel fraction must be between 0 and 1.")

    if workers <= 0:
        raise ValueError("Workers must be positive.")

    serial_fraction = 1 - parallel_fraction

    return 1 / (
        serial_fraction
        + parallel_fraction / workers
    )


def demonstrate_amdahl() -> None:
    print("\n31. AMDAHL'S LAW")

    parallel_fraction = 0.90

    for workers in [1, 2, 4, 8, 16, 64, 1000]:
        speedup = amdahl_speedup(
            parallel_fraction,
            workers,
        )

        print(
            f"Workers={workers:4} -> speedup={speedup:.3f}x"
        )

    print(
        "Even with unlimited workers, a 10% serial fraction "
        "limits maximum speedup to 10x."
    )


# ============================================================================
# 32. GUSTAFSON'S LAW
# ============================================================================

def gustafson_scaled_speedup(
    serial_fraction: float,
    workers: int,
) -> float:
    """
    Apply Gustafson's Law:

        Scaled speedup = N - s(N-1)

    where s is the serial fraction.

    Gustafson's perspective considers scaling the problem size with available
    parallel resources rather than holding the problem size fixed.
    """
    if not 0 <= serial_fraction <= 1:
        raise ValueError("Serial fraction must be between 0 and 1.")

    if workers <= 0:
        raise ValueError("Workers must be positive.")

    return workers - serial_fraction * (workers - 1)


def demonstrate_gustafson() -> None:
    print("\n32. GUSTAFSON'S LAW")

    for workers in [1, 2, 4, 8, 16]:
        speedup = gustafson_scaled_speedup(
            serial_fraction=0.10,
            workers=workers,
        )

        print(
            f"Workers={workers:2} -> scaled speedup={speedup:.2f}x"
        )


# ============================================================================
# 33. CAPACITY PLANNING
# ============================================================================

def required_instances_for_slo(
    peak_request_rate: float,
    instance_capacity: float,
    target_utilization: float,
    safety_factor: float = 1.0,
) -> int:
    """
    Estimate instance count for a capacity target.

    capacity_per_instance =
        instance_capacity * target_utilization

    required capacity =
        peak_request_rate * safety_factor
    """
    if peak_request_rate < 0:
        raise ValueError("Peak rate cannot be negative.")

    if instance_capacity <= 0:
        raise ValueError("Instance capacity must be positive.")

    if not 0 < target_utilization <= 1:
        raise ValueError("Target utilization must be in (0,1].")

    if safety_factor < 1:
        raise ValueError("Safety factor should be at least 1.")

    usable_capacity = (
        instance_capacity
        * target_utilization
    )

    required_capacity = (
        peak_request_rate
        * safety_factor
    )

    return max(
        1,
        ceil(required_capacity / usable_capacity),
    )


def demonstrate_capacity_planning() -> None:
    print("\n33. CAPACITY PLANNING")

    instances = required_instances_for_slo(
        peak_request_rate=8000,
        instance_capacity=1500,
        target_utilization=0.65,
        safety_factor=1.25,
    )

    print(f"Required instances: {instances}")


# ============================================================================
# 34. ERROR BUDGET / AVAILABILITY
# ============================================================================

def annual_downtime_minutes(
    availability_target: float,
) -> float:
    """
    Convert availability percentage into approximate annual downtime.

    Example:
        99.9% availability leaves approximately 525.6 minutes/year.
    """
    if not 0 < availability_target <= 1:
        raise ValueError("Availability must be between 0 and 1.")

    minutes_per_year = 365 * 24 * 60

    return (1 - availability_target) * minutes_per_year


def demonstrate_availability() -> None:
    print("\n34. AVAILABILITY TARGETS")

    for availability in [0.99, 0.999, 0.9999, 0.99999]:
        downtime = annual_downtime_minutes(availability)

        print(
            f"{availability:.5%} availability -> "
            f"{downtime:.2f} minutes/year"
        )


# ============================================================================
# 35. GRACEFUL DEGRADATION
# ============================================================================

class ServiceResponsePolicy:
    """
    Demonstrate a simplified graceful-degradation policy.
    """

    def response_for_dependency(
        self,
        dependency_available: bool,
        cached_value: Optional[str],
    ) -> str:
        if dependency_available:
            return "Return fresh dependency data."

        if cached_value is not None:
            return "Return cached data and mark it as potentially stale."

        return "Return a reduced response without optional dependency data."


def demonstrate_graceful_degradation() -> None:
    print("\n35. GRACEFUL DEGRADATION")

    policy = ServiceResponsePolicy()

    scenarios = [
        (True, "fresh"),
        (False, "cached"),
        (False, None),
    ]

    for available, cached in scenarios:
        print(
            policy.response_for_dependency(
                available,
                cached,
            )
        )


# ============================================================================
# 36. CIRCUIT BREAKER
# ============================================================================

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class CircuitBreaker:
    """
    Simplified circuit breaker.

    The breaker opens after a configured number of consecutive failures,
    preventing continuous traffic from overwhelming a failing dependency.

    A real implementation would also include timers, half-open probing,
    metrics, distributed considerations, and carefully defined failure types.
    """

    def __init__(self, failure_threshold: int) -> None:
        if failure_threshold <= 0:
            raise ValueError("Failure threshold must be positive.")

        self.failure_threshold = failure_threshold
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.consecutive_failures += 1

        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def allow_request(self) -> bool:
        return self.state != CircuitState.OPEN


def demonstrate_circuit_breaker() -> None:
    print("\n36. CIRCUIT BREAKER")

    breaker = CircuitBreaker(
        failure_threshold=3
    )

    for attempt in range(1, 6):
        if not breaker.allow_request():
            print(
                f"Attempt {attempt}: rejected by open circuit"
            )
            continue

        breaker.record_failure()

        print(
            f"Attempt {attempt}: dependency failed, "
            f"circuit={breaker.state.value}"
        )


# ============================================================================
# 37. RETRIES AND RETRY STORMS
# ============================================================================

def exponential_backoff(
    attempt: int,
    base_delay: float = 0.5,
    maximum_delay: float = 30.0,
) -> float:
    """
    Calculate exponential backoff:

        delay = min(maximum_delay, base_delay * 2^attempt)

    Exponential backoff reduces synchronized retry pressure.

    Production systems commonly add jitter to avoid many clients retrying
    at exactly the same time.
    """
    if attempt < 0:
        raise ValueError("Attempt cannot be negative.")

    if base_delay <= 0 or maximum_delay <= 0:
        raise ValueError("Delays must be positive.")

    return min(
        maximum_delay,
        base_delay * (2 ** attempt),
    )


def demonstrate_retry_backoff() -> None:
    print("\n37. RETRIES AND EXPONENTIAL BACKOFF")

    for attempt in range(6):
        print(
            f"Attempt {attempt}: "
            f"delay={exponential_backoff(attempt):.2f}s"
        )

    print(
        "Retries without limits, backoff, jitter, and idempotency can "
        "amplify failures into retry storms."
    )


# ============================================================================
# 38. JITTER
# ============================================================================

def full_jitter_backoff(
    attempt: int,
    base_delay: float,
    maximum_delay: float,
    random_generator: Random,
) -> float:
    """
    Full-jitter strategy:

        random value between 0 and exponential cap.

    Jitter reduces synchronization among many independent clients.
    """
    cap = exponential_backoff(
        attempt,
        base_delay,
        maximum_delay,
    )

    return random_generator.uniform(0, cap)


def demonstrate_jitter() -> None:
    print("\n38. RETRY JITTER")

    generator = Random(42)

    for attempt in range(5):
        delay = full_jitter_backoff(
            attempt,
            base_delay=0.5,
            maximum_delay=20,
            random_generator=generator,
        )

        print(
            f"Attempt {attempt}: randomized delay={delay:.3f}s"
        )


# ============================================================================
# 39. FAN-OUT AND FAN-IN
# ============================================================================

def fan_out_latency(
    downstream_latencies: Sequence[float],
    parallel: bool,
) -> float:
    """
    Estimate aggregate latency.

    Sequential fan-out:
        total latency is approximately the sum.

    Parallel fan-out:
        total latency is approximately the maximum.

    Real distributed systems also pay coordination, serialization, network,
    scheduling, and retry costs.
    """
    if not downstream_latencies:
        return 0.0

    if any(latency < 0 for latency in downstream_latencies):
        raise ValueError("Latency cannot be negative.")

    if parallel:
        return max(downstream_latencies)

    return sum(downstream_latencies)


def demonstrate_fanout() -> None:
    print("\n39. FAN-OUT AND FAN-IN")

    downstream = [0.020, 0.030, 0.015, 0.040]

    print(
        f"Sequential estimated latency: "
        f"{fan_out_latency(downstream, False) * 1000:.1f} ms"
    )

    print(
        f"Parallel estimated latency: "
        f"{fan_out_latency(downstream, True) * 1000:.1f} ms"
    )


# ============================================================================
# 40. PARTIAL FAILURE
# ============================================================================

def calculate_successful_capacity(
    component_capacities: Sequence[float],
    required_components: int,
) -> float:
    """
    Model a simple service requiring a specified number of independent
    components.

    This is deliberately abstract. Real redundancy analysis depends on
    topology and failure independence.
    """
    if not component_capacities:
        raise ValueError("At least one capacity is required.")

    if required_components <= 0:
        raise ValueError("Required component count must be positive.")

    if required_components > len(component_capacities):
        raise ValueError("Not enough components.")

    sorted_capacities = sorted(
        component_capacities,
        reverse=True,
    )

    return sum(sorted_capacities[:required_components])


def demonstrate_redundancy() -> None:
    print("\n40. REDUNDANCY AND PARTIAL FAILURE")

    capacities = [1000, 1000, 1000]

    print(
        "Capacity with any two components:",
        calculate_successful_capacity(capacities, 2),
    )

    print(
        "Redundancy allows capacity or availability to survive "
        "some individual failures."
    )


# ============================================================================
# 41. SCALE-UP VERSUS SCALE-OUT
# ============================================================================

def compare_scaling_strategies() -> None:
    print("\n41. VERTICAL VERSUS HORIZONTAL SCALING")

    comparison = [
        ("Resource change", "Bigger machine", "More machines"),
        ("Implementation", "Often simpler initially", "Requires distributed design"),
        ("Upper bound", "Hardware limits", "Potentially much larger"),
        ("Failure domain", "Large single-machine dependency", "Can distribute failure"),
        ("Coordination", "Lower", "Higher"),
        ("Operational complexity", "Usually lower", "Usually higher"),
        ("Cost model", "Large machine pricing", "Multiple machine pricing"),
        ("Elasticity", "Usually limited", "Often stronger"),
    ]

    print(
        f"{'Dimension':20} {'Vertical':30} {'Horizontal':35}"
    )
    print("-" * 90)

    for dimension, vertical, horizontal in comparison:
        print(
            f"{dimension:20} "
            f"{vertical:30} "
            f"{horizontal:35}"
        )


# ============================================================================
# 42. SCALING BOTTLENECK EXAMPLE
# ============================================================================

@dataclass
class Architecture:
    """
    Simplified architecture with several serial bottlenecks.
    """

    api_capacity: float
    cache_capacity: float
    database_capacity: float
    external_service_capacity: float

    def maximum_throughput(self) -> float:
        return min(
            self.api_capacity,
            self.cache_capacity,
            self.database_capacity,
            self.external_service_capacity,
        )


def demonstrate_bottleneck_architecture() -> None:
    print("\n42. END-TO-END SCALING BOTTLENECK")

    architecture = Architecture(
        api_capacity=10000,
        cache_capacity=15000,
        database_capacity=2500,
        external_service_capacity=6000,
    )

    print(f"API capacity: {architecture.api_capacity}")
    print(f"Cache capacity: {architecture.cache_capacity}")
    print(f"Database capacity: {architecture.database_capacity}")
    print(
        f"External service capacity: "
        f"{architecture.external_service_capacity}"
    )
    print(
        f"System throughput ceiling: "
        f"{architecture.maximum_throughput()}"
    )

    print(
        "Adding API servers alone does not remove the database bottleneck."
    )


# ============================================================================
# 43. BOTTLENECK REMOVAL SIMULATION
# ============================================================================

def optimize_architecture(
    architecture: Architecture,
    *,
    database_multiplier: float = 1.0,
    external_multiplier: float = 1.0,
    cache_multiplier: float = 1.0,
) -> Architecture:
    """
    Return a modified architecture after scaling selected components.
    """
    if min(
        database_multiplier,
        external_multiplier,
        cache_multiplier,
    ) <= 0:
        raise ValueError("Multipliers must be positive.")

    return Architecture(
        api_capacity=architecture.api_capacity,
        cache_capacity=architecture.cache_capacity * cache_multiplier,
        database_capacity=architecture.database_capacity * database_multiplier,
        external_service_capacity=(
            architecture.external_service_capacity
            * external_multiplier
        ),
    )


def demonstrate_bottleneck_removal() -> None:
    print("\n43. REMOVING BOTTLENECKS")

    architecture = Architecture(
        api_capacity=10000,
        cache_capacity=15000,
        database_capacity=2500,
        external_service_capacity=6000,
    )

    for database_multiplier in [1, 2, 4]:
        optimized = optimize_architecture(
            architecture,
            database_multiplier=database_multiplier,
        )

        print(
            f"Database x{database_multiplier}: "
            f"system capacity={optimized.maximum_throughput():.0f}"
        )


# ============================================================================
# 44. COST MODEL
# ============================================================================

@dataclass
class CostModel:
    """
    Simplified cost model for comparing scaling strategies.
    """

    base_server_cost: float
    large_server_multiplier: float
    operational_cost_per_server: float

    def vertical_monthly_cost(self) -> float:
        return (
            self.base_server_cost
            * self.large_server_multiplier
        )

    def horizontal_monthly_cost(
        self,
        server_count: int,
    ) -> float:
        if server_count <= 0:
            raise ValueError("Server count must be positive.")

        return server_count * (
            self.base_server_cost
            + self.operational_cost_per_server
        )


def demonstrate_cost_tradeoff() -> None:
    print("\n44. SCALING COST TRADE-OFF")

    cost_model = CostModel(
        base_server_cost=500,
        large_server_multiplier=4,
        operational_cost_per_server=75,
    )

    vertical = cost_model.vertical_monthly_cost()
    horizontal = cost_model.horizontal_monthly_cost(8)

    print(f"Large vertical instance cost: ${vertical:.2f}/month")
    print(f"Eight horizontal instances: ${horizontal:.2f}/month")

    print(
        "Cost alone does not determine architecture. "
        "Availability, operational complexity, performance, and failure "
        "isolation also matter."
    )


# ============================================================================
# 45. LATENCY DISTRIBUTION
# ============================================================================

@dataclass
class LatencyReport:
    values: List[float]

    @property
    def average(self) -> float:
        return mean(self.values)

    @property
    def median(self) -> float:
        return median(self.values)

    def percentile(self, percentile: float) -> float:
        """
        Calculate a simple nearest-rank-style percentile.

        This is sufficient for demonstration. Production observability
        systems may use more sophisticated histogram or streaming methods.
        """
        if not 0 <= percentile <= 100:
            raise ValueError("Percentile must be between 0 and 100.")

        if not self.values:
            raise ValueError("No latency observations.")

        ordered = sorted(self.values)

        index = ceil(
            (percentile / 100) * len(ordered)
        ) - 1

        index = max(0, min(index, len(ordered) - 1))

        return ordered[index]


def demonstrate_latency_percentiles() -> None:
    print("\n45. LATENCY DISTRIBUTIONS AND TAIL LATENCY")

    latencies = [
        20, 21, 19, 25, 22, 23, 24, 21, 20,
        22, 23, 24, 28, 30, 35, 40, 50, 70,
    ]

    report = LatencyReport(latencies)

    print(f"Mean latency:   {report.average:.1f} ms")
    print(f"Median latency: {report.median:.1f} ms")
    print(f"P90 latency:    {report.percentile(90):.1f} ms")
    print(f"P99 latency:    {report.percentile(99):.1f} ms")

    print(
        "Tail latency matters because a small percentage of slow requests "
        "can affect user experience and upstream services."
    )


# ============================================================================
# 46. LOAD TEST SIMULATION
# ============================================================================

@dataclass
class LoadTestResult:
    requested_rate: float
    capacity: float
    successful_requests: float
    rejected_requests: float
    utilization: float
    estimated_latency_seconds: float


def simulate_load_test(
    request_rate: float,
    capacity: float,
    duration_seconds: float,
    service_time: float,
) -> LoadTestResult:
    """
    Simplified load-test model.

    Requests above capacity are treated as rejected rather than queued.
    A real load test should measure actual response distributions and
    resource utilization over time.
    """
    if request_rate < 0:
        raise ValueError("Request rate cannot be negative.")

    if capacity <= 0:
        raise ValueError("Capacity must be positive.")

    if duration_seconds <= 0:
        raise ValueError("Duration must be positive.")

    if service_time <= 0:
        raise ValueError("Service time must be positive.")

    total_requests = request_rate * duration_seconds
    successful_rate = min(request_rate, capacity)
    successful_requests = successful_rate * duration_seconds
    rejected_requests = total_requests - successful_requests

    current_utilization = min(
        1.0,
        request_rate / capacity,
    )

    latency = approximate_latency(
        service_time,
        current_utilization,
    )

    return LoadTestResult(
        requested_rate=request_rate,
        capacity=capacity,
        successful_requests=successful_requests,
        rejected_requests=rejected_requests,
        utilization=current_utilization,
        estimated_latency_seconds=latency,
    )


def demonstrate_load_test() -> None:
    print("\n46. LOAD TEST SIMULATION")

    for rate in [500, 1000, 1500]:
        result = simulate_load_test(
            request_rate=rate,
            capacity=1000,
            duration_seconds=10,
            service_time=0.005,
        )

        print(
            f"Load={rate:4} req/s | "
            f"success={result.successful_requests:7.0f} | "
            f"rejected={result.rejected_requests:7.0f} | "
            f"latency={result.estimated_latency_seconds * 1000}"
        )


# ============================================================================
# 47. SCALABILITY TESTING
# ============================================================================

def scalability_test(
    instance_counts: Sequence[int],
    capacity_per_instance: float,
    efficiency_function,
) -> List[Tuple[int, float, float]]:
    """
    Evaluate actual capacity and scaling efficiency across instance counts.

    efficiency_function receives instance count and returns an efficiency
    between 0 and 1.
    """
    if capacity_per_instance <= 0:
        raise ValueError("Capacity must be positive.")

    results = []

    for count in instance_counts:
        if count <= 0:
            raise ValueError("Instance counts must be positive.")

        efficiency = efficiency_function(count)
        actual_capacity = (
            capacity_per_instance
            * count
            * efficiency
        )

        results.append(
            (count, actual_capacity, efficiency)
        )

    return results


def demonstrate_scalability_test() -> None:
    print("\n47. SCALABILITY TESTING")

    def efficiency(number_of_instances: int) -> float:
        """
        Simulate coordination overhead increasing with instance count.
        """
        return max(
            0.55,
            1.0 - 0.03 * (number_of_instances - 1),
        )

    results = scalability_test(
        [1, 2, 4, 8, 16],
        capacity_per_instance=1000,
        efficiency_function=efficiency,
    )

    for count, capacity, efficiency_value in results:
        print(
            f"{count:2} instances | "
            f"capacity={capacity:7.0f} | "
            f"efficiency={efficiency_value:.1%}"
        )


# ============================================================================
# 48. DATA PARTITIONING STRATEGIES
# ============================================================================

def demonstrate_partitioning_strategies() -> None:
    print("\n48. DATA PARTITIONING STRATEGIES")

    strategies = {
        "Hash partitioning":
            "Distributes records according to a hash function.",
        "Range partitioning":
            "Distributes records according to ordered ranges.",
        "List partitioning":
            "Maps predefined categories to partitions.",
        "Geographic partitioning":
            "Places data according to region or locality.",
        "Time partitioning":
            "Separates records by time periods.",
    }

    for name, explanation in strategies.items():
        print(f"{name:25}: {explanation}")


# ============================================================================
# 49. CONSISTENT HASHING
# ============================================================================

def consistent_hash_position(
    key: str,
    virtual_nodes: int,
) -> int:
    """
    Map a key to a deterministic integer ring position.

    This function illustrates the hashing concept, not a complete consistent
    hashing ring implementation.
    """
    if virtual_nodes <= 0:
        raise ValueError("Virtual node count must be positive.")

    return hash(key) % virtual_nodes


def demonstrate_hashing() -> None:
    print("\n49. HASH-BASED DISTRIBUTION")

    for key in ["user:1", "user:2", "user:3", "user:4"]:
        print(
            f"{key:10} -> position "
            f"{consistent_hash_position(key, 16)}"
        )

    print(
        "Python's built-in hash is intentionally not stable across "
        "processes by default, so production distributed hashing requires "
        "a stable hashing strategy."
    )


# ============================================================================
# 50. DATA HOTSPOT MITIGATION
# ============================================================================

def distribute_hot_key(
    logical_key: str,
    bucket_count: int,
    request_number: int,
) -> str:
    """
    Spread requests for a very hot logical key across sub-buckets.

    This is a conceptual technique often called key salting.

    It changes access distribution but complicates reads because all relevant
    buckets may need to be queried.
    """
    if bucket_count <= 0:
        raise ValueError("Bucket count must be positive.")

    bucket = request_number % bucket_count

    return f"{logical_key}#{bucket}"


def demonstrate_hot_key_splitting() -> None:
    print("\n50. HOT-KEY MITIGATION")

    for request_number in range(12):
        print(
            distribute_hot_key(
                "celebrity-profile",
                bucket_count=4,
                request_number=request_number,
            )
        )


# ============================================================================
# 51. BATCHING
# ============================================================================

def batch_items(
    items: Sequence[object],
    batch_size: int,
) -> List[List[object]]:
    """
    Group items into batches.

    Batching can reduce per-operation overhead, but excessively large batches
    can increase latency, memory usage, and failure blast radius.
    """
    if batch_size <= 0:
        raise ValueError("Batch size must be positive.")

    return [
        list(items[index:index + batch_size])
        for index in range(0, len(items), batch_size)
    ]


def demonstrate_batching() -> None:
    print("\n51. BATCHING")

    records = list(range(1, 11))

    for batch_size in [1, 3, 5]:
        batches = batch_items(
            records,
            batch_size,
        )

        print(
            f"Batch size {batch_size}: {batches}"
        )


# ============================================================================
# 52. ASYNCHRONOUS WORKER SCALING
# ============================================================================

def worker_capacity(
    workers: int,
    jobs_per_worker_per_second: float,
) -> float:
    """
    Calculate ideal worker throughput.
    """
    if workers <= 0:
        raise ValueError("Workers must be positive.")

    if jobs_per_worker_per_second <= 0:
        raise ValueError("Worker rate must be positive.")

    return workers * jobs_per_worker_per_second


def required_workers(
    incoming_jobs_per_second: float,
    jobs_per_worker_per_second: float,
    target_utilization: float,
) -> int:
    """
    Estimate worker count using a target utilization.
    """
    if incoming_jobs_per_second < 0:
        raise ValueError("Incoming rate cannot be negative.")

    if jobs_per_worker_per_second <= 0:
        raise ValueError("Worker capacity must be positive.")

    if not 0 < target_utilization <= 1:
        raise ValueError("Target utilization must be in (0,1].")

    effective_capacity = (
        jobs_per_worker_per_second
        * target_utilization
    )

    return max(
        1,
        ceil(incoming_jobs_per_second / effective_capacity),
    )


def demonstrate_worker_scaling() -> None:
    print("\n52. WORKER SCALING")

    incoming_rate = 5000

    workers = required_workers(
        incoming_rate,
        jobs_per_worker_per_second=400,
        target_utilization=0.70,
    )

    print(f"Incoming jobs/s: {incoming_rate}")
    print(f"Required workers: {workers}")
    print(
        f"Ideal capacity: "
        f"{worker_capacity(workers, 400):.0f} jobs/s"
    )


# ============================================================================
# 53. SERIAL BOTTLENECK VERSUS PARALLEL CAPACITY
# ============================================================================

def serial_pipeline_capacity(
    capacities: Sequence[float],
) -> float:
    """
    In a serial pipeline, throughput is constrained by the smallest capacity.
    """
    if not capacities:
        raise ValueError("At least one capacity is required.")

    return min(capacities)


def parallel_pool_capacity(
    capacities: Sequence[float],
) -> float:
    """
    If independent workers can process separate requests in parallel,
    capacities can be approximately additive.
    """
    if not capacities:
        raise ValueError("At least one capacity is required.")

    return sum(capacities)


def demonstrate_serial_parallel_capacity() -> None:
    print("\n53. SERIAL VERSUS PARALLEL CAPACITY")

    capacities = [1000, 2000, 1500]

    print(
        f"Serial pipeline capacity: "
        f"{serial_pipeline_capacity(capacities)}"
    )

    print(
        f"Independent parallel capacity: "
        f"{parallel_pool_capacity(capacities)}"
    )


# ============================================================================
# 54. RESOURCE UTILIZATION VECTOR
# ============================================================================

@dataclass
class ResourceUtilization:
    cpu: float
    memory: float
    storage_io: float
    network: float

    def highest_utilized(self) -> Tuple[str, float]:
        resources = {
            "CPU": self.cpu,
            "Memory": self.memory,
            "Storage I/O": self.storage_io,
            "Network": self.network,
        }

        return max(
            resources.items(),
            key=lambda item: item[1],
        )


def demonstrate_resource_profile() -> None:
    print("\n54. RESOURCE PROFILE")

    profile = ResourceUtilization(
        cpu=0.72,
        memory=0.55,
        storage_io=0.93,
        network=0.48,
    )

    resource, utilization_value = profile.highest_utilized()

    print(f"CPU: {profile.cpu:.0%}")
    print(f"Memory: {profile.memory:.0%}")
    print(f"Storage I/O: {profile.storage_io:.0%}")
    print(f"Network: {profile.network:.0%}")
    print(
        f"Highest utilized resource: "
        f"{resource} ({utilization_value:.0%})"
    )


# ============================================================================
# 55. OBSERVABILITY
# ============================================================================

def demonstrate_observability_signals() -> None:
    print("\n55. OBSERVABILITY FOR SCALABILITY")

    signals = {
        "Traffic":
            "Requests per second, jobs per second, active users.",
        "Errors":
            "Error rate, failed requests, retries, timeouts.",
        "Latency":
            "Average and percentile latency such as P50, P95, P99.",
        "Saturation":
            "CPU, memory, queue depth, connection pools, disk, network.",
        "Capacity":
            "Current throughput relative to sustainable limits.",
        "Dependency health":
            "Latency and errors from databases and external services.",
    }

    for signal, meaning in signals.items():
        print(f"{signal:20}: {meaning}")


# ============================================================================
# 56. DEBUGGING A SCALING INCIDENT
# ============================================================================

def diagnose_scaling_incident(
    cpu_utilization: float,
    database_utilization: float,
    queue_depth: int,
    error_rate: float,
) -> List[str]:
    """
    Produce simple diagnostic hypotheses.

    Production diagnosis should use time-series evidence and causal
    investigation rather than relying on a single metric.
    """
    if not 0 <= cpu_utilization <= 1:
        raise ValueError("CPU utilization must be between 0 and 1.")

    if not 0 <= database_utilization <= 1:
        raise ValueError("Database utilization must be between 0 and 1.")

    if queue_depth < 0:
        raise ValueError("Queue depth cannot be negative.")

    if not 0 <= error_rate <= 1:
        raise ValueError("Error rate must be between 0 and 1.")

    diagnoses = []

    if cpu_utilization > 0.85:
        diagnoses.append("Application CPU may be saturated.")

    if database_utilization > 0.85:
        diagnoses.append("Database may be the primary bottleneck.")

    if queue_depth > 10000:
        diagnoses.append("Asynchronous workload is accumulating.")

    if error_rate > 0.05:
        diagnoses.append("Failure rate is elevated and may be causing retries.")

    if not diagnoses:
        diagnoses.append(
            "No obvious threshold breach; inspect latency, dependencies, "
            "traffic shape, and resource contention."
        )

    return diagnoses


def demonstrate_incident_diagnosis() -> None:
    print("\n56. DEBUGGING A SCALABILITY INCIDENT")

    diagnoses = diagnose_scaling_incident(
        cpu_utilization=0.60,
        database_utilization=0.95,
        queue_depth=15000,
        error_rate=0.08,
    )

    for diagnosis in diagnoses:
        print(f"- {diagnosis}")


# ============================================================================
# 57. SECURITY AND SCALABILITY
# ============================================================================

def demonstrate_security_considerations() -> None:
    print("\n57. SECURITY CONSIDERATIONS")

    considerations = [
        "Rate limiting prevents abusive traffic from consuming shared capacity.",
        "Authentication and authorization must remain correct across all replicas.",
        "Distributed caches require appropriate access controls and data isolation.",
        "Secrets must not be replicated or logged insecurely.",
        "Autoscaling policies can become expensive if attackers generate artificial load.",
        "Input validation prevents expensive pathological requests.",
        "Resource quotas limit noisy-neighbor effects in shared infrastructure.",
        "Idempotency protects retryable operations from duplicate side effects.",
        "Distributed tracing and logs must avoid exposing sensitive data.",
    ]

    for consideration in considerations:
        print(f"- {consideration}")


# ============================================================================
# 58. NOISY NEIGHBOR PROBLEM
# ============================================================================

@dataclass
class Tenant:
    name: str
    requested_capacity: float


def allocate_fair_share(
    tenants: Sequence[Tenant],
    total_capacity: float,
) -> Dict[str, float]:
    """
    Allocate capacity proportionally to requested demand.

    This is a simplified model. Production multi-tenant systems may use
    weighted quotas, priority, reservations, admission control, and isolation.
    """
    if total_capacity < 0:
        raise ValueError("Capacity cannot be negative.")

    if not tenants:
        return {}

    total_requested = sum(
        tenant.requested_capacity
        for tenant in tenants
    )

    if total_requested == 0:
        return {
            tenant.name: 0.0
            for tenant in tenants
        }

    return {
        tenant.name:
            total_capacity
            * tenant.requested_capacity
            / total_requested
        for tenant in tenants
    }


def demonstrate_noisy_neighbor() -> None:
    print("\n58. NOISY NEIGHBOR AND FAIRNESS")

    tenants = [
        Tenant("tenant-A", 100),
        Tenant("tenant-B", 300),
        Tenant("tenant-C", 600),
    ]

    allocation = allocate_fair_share(
        tenants,
        total_capacity=500,
    )

    for tenant, capacity in allocation.items():
        print(
            f"{tenant}: allocated {capacity:.1f} capacity units"
        )


# ============================================================================
# 59. FAILURE BLAST RADIUS
# ============================================================================

def estimate_failure_blast_radius(
    total_capacity: float,
    failed_capacity: float,
) -> float:
    """
    Return the percentage of total capacity lost when a component fails.
    """
    if total_capacity <= 0:
        raise ValueError("Total capacity must be positive.")

    if not 0 <= failed_capacity <= total_capacity:
        raise ValueError(
            "Failed capacity must be within total capacity."
        )

    return failed_capacity / total_capacity


def demonstrate_failure_domains() -> None:
    print("\n59. FAILURE DOMAINS")

    print(
        f"One failed 1000-capacity server in a 10000-capacity fleet "
        f"removes "
        f"{estimate_failure_blast_radius(10000, 1000):.1%} of capacity."
    )

    print(
        "Horizontal distribution can reduce the capacity lost from a single "
        "machine failure, assuming the workload and dependencies are also "
        "distributed."
    )


# ============================================================================
# 60. SCALE LIMITS
# ============================================================================

def demonstrate_scale_limits() -> None:
    print("\n60. COMMON SCALING LIMITS")

    limits = [
        "Maximum machine size",
        "Database write serialization",
        "Global locks",
        "Single-threaded components",
        "Network bandwidth",
        "Storage throughput",
        "Connection limits",
        "External API quotas",
        "Hot partitions",
        "Coordination overhead",
        "Cross-region latency",
        "Consistency requirements",
        "Operational complexity",
        "Cost constraints",
    ]

    for limit in limits:
        print(f"- {limit}")


# ============================================================================
# 61. SCALING DECISION MODEL
# ============================================================================

@dataclass
class ScalingDecision:
    """
    Simple decision record for documenting an architectural scaling choice.
    """

    workload_growth: str
    latency_requirement: str
    statefulness: str
    primary_bottleneck: str
    failure_requirement: str
    cost_constraint: str


def evaluate_scaling_decision(
    decision: ScalingDecision,
) -> str:
    """
    Produce a qualitative recommendation based on explicit constraints.

    This is not a universal architecture selector. It demonstrates that
    scaling decisions should be driven by workload and constraints.
    """
    if decision.primary_bottleneck.lower() == "cpu":
        if decision.statefulness.lower() == "stateless":
            return "Horizontal application scaling is a strong candidate."

        return (
            "Consider horizontal scaling, but first address state "
            "management and session routing."
        )

    if decision.primary_bottleneck.lower() == "database reads":
        return (
            "Consider caching, read replicas, query optimization, "
            "and workload separation."
        )

    if decision.primary_bottleneck.lower() == "database writes":
        return (
            "Investigate write optimization, batching, partitioning, "
            "data-model changes, and workload decomposition."
        )

    if decision.primary_bottleneck.lower() == "external service":
        return (
            "Scale application workers only if the dependency quota also "
            "permits increased throughput; use caching, batching, "
            "rate limiting, and asynchronous processing where appropriate."
        )

    return (
        "Measure the limiting resource and scale the actual bottleneck "
        "rather than increasing unrelated resources."
    )


def demonstrate_scaling_decision() -> None:
    print("\n61. SCALING DECISION MODEL")

    decisions = [
        ScalingDecision(
            workload_growth="high",
            latency_requirement="strict",
            statefulness="stateless",
            primary_bottleneck="CPU",
            failure_requirement="high",
            cost_constraint="moderate",
        ),
        ScalingDecision(
            workload_growth="moderate",
            latency_requirement="strict",
            statefulness="stateless",
            primary_bottleneck="database reads",
            failure_requirement="high",
            cost_constraint="moderate",
        ),
        ScalingDecision(
            workload_growth="high",
            latency_requirement="relaxed",
            statefulness="stateless",
            primary_bottleneck="external service",
            failure_requirement="high",
            cost_constraint="strict",
        ),
    ]

    for decision in decisions:
        print(
            f"Bottleneck={decision.primary_bottleneck}: "
            f"{evaluate_scaling_decision(decision)}"
        )


# ============================================================================
# 62. EDGE CASES
# ============================================================================

def demonstrate_scaling_edge_cases() -> None:
    print("\n62. EDGE CASES")

    edge_cases = [
        "Zero incoming traffic",
        "Sudden traffic spike",
        "Traffic falling to zero",
        "One extremely hot customer or key",
        "All database reads hitting one replica",
        "Database unavailable while application remains healthy",
        "Queue growing without bound",
        "Autoscaler reaching its maximum",
        "A dependency imposing a fixed rate limit",
        "A single machine containing irreplaceable state",
        "Cross-region requests with high latency",
        "Retries multiplying already-failing traffic",
    ]

    for case in edge_cases:
        print(f"- {case}")


# ============================================================================
# 63. COMMON MISTAKES
# ============================================================================

def demonstrate_common_scalability_mistakes() -> None:
    print("\n63. COMMON SCALABILITY MISTAKES")

    mistakes = {
        "Scaling the wrong layer":
            "Adding application servers while the database remains saturated.",
        "Assuming linear scaling":
            "Ignoring coordination, network, synchronization, and shared dependencies.",
        "Ignoring tail latency":
            "Using only average latency to evaluate user experience.",
        "Unlimited retries":
            "Turning dependency failures into a retry storm.",
        "Unbounded queues":
            "Allowing memory or storage consumption to grow indefinitely.",
        "Stateful application instances":
            "Making requests depend on a particular server without a deliberate strategy.",
        "No capacity headroom":
            "Operating continuously at the theoretical maximum.",
        "Ignoring hot keys":
            "Assuming hashing always creates perfectly balanced traffic.",
        "Scaling without observability":
            "Adding resources without identifying the actual bottleneck.",
        "Ignoring cost":
            "Treating capacity as unlimited and free.",
    }

    for mistake, explanation in mistakes.items():
        print(f"\n{mistake}")
        print(f"  {explanation}")


# ============================================================================
# 64. BEST PRACTICES
# ============================================================================

def demonstrate_best_practices() -> None:
    print("\n64. SCALABILITY BEST PRACTICES")

    practices = [
        "Measure before scaling.",
        "Identify the actual bottleneck.",
        "Keep stateless application tiers when practical.",
        "Separate synchronous user-facing work from long-running background jobs.",
        "Use caching for appropriate read-heavy workloads.",
        "Protect dependencies with timeouts, rate limits, and circuit breakers.",
        "Make retryable operations idempotent.",
        "Use bounded queues and explicit backpressure.",
        "Design databases for the dominant access pattern.",
        "Monitor percentile latency rather than only averages.",
        "Leave capacity headroom for bursts and failures.",
        "Test beyond expected peak load.",
        "Design failure domains deliberately.",
        "Treat autoscaling as a control system with lag and limits.",
        "Consider operational complexity and cost alongside raw throughput.",
    ]

    for practice in practices:
        print(f"- {practice}")


# ============================================================================
# 65. PERFORMANCE VERSUS SCALABILITY
# ============================================================================

def compare_performance_and_scalability() -> None:
    print("\n65. PERFORMANCE VERSUS SCALABILITY")

    comparison = [
        (
            "Performance",
            "How efficiently one system configuration performs.",
            "Reduce latency or increase throughput on the existing configuration.",
        ),
        (
            "Scalability",
            "How system capacity changes as resources or workload increase.",
            "Add or enlarge resources while preserving acceptable behavior.",
        ),
    ]

    for concept, definition, focus in comparison:
        print(f"\n{concept}")
        print(f"Definition: {definition}")
        print(f"Typical focus: {focus}")


# ============================================================================
# 66. AVAILABILITY VERSUS SCALABILITY
# ============================================================================

def compare_availability_and_scalability() -> None:
    print("\n66. AVAILABILITY VERSUS SCALABILITY")

    print(
        "Scalability concerns handling increasing workload."
    )

    print(
        "Availability concerns whether the service remains operational."
    )

    print(
        "They interact: horizontal redundancy can improve both capacity "
        "and availability, but additional machines do not automatically "
        "produce a highly available system."
    )


# ============================================================================
# 67. CONSISTENCY VERSUS SCALABILITY
# ============================================================================

def compare_consistency_tradeoffs() -> None:
    print("\n67. CONSISTENCY AND SCALABILITY")

    concepts = [
        "Strong consistency can require coordination between replicas.",
        "Coordination can add latency and reduce throughput.",
        "Eventual consistency can reduce coordination for some workloads.",
        "The correct consistency model depends on business semantics.",
        "Financial balances and inventory may require stronger guarantees than analytics caches.",
    ]

    for concept in concepts:
        print(f"- {concept}")


# ============================================================================
# 68. PRODUCTION READINESS CHECK
# ============================================================================

def production_scalability_checklist() -> Dict[str, bool]:
    """
    Return a representative production readiness checklist.

    This is intentionally a checklist data structure rather than a claim
    that every system needs every item.
    """
    return {
        "Capacity measured": True,
        "Bottleneck identified": True,
        "Load test performed": True,
        "Percentile latency monitored": True,
        "Rate limiting implemented": True,
        "Dependency timeouts configured": True,
        "Retry policy bounded": True,
        "Idempotency considered": True,
        "Queue limits defined": True,
        "Autoscaling limits defined": True,
        "Failure behavior tested": True,
        "Cost monitored": True,
        "Security controls reviewed": True,
    }


def demonstrate_production_checklist() -> None:
    print("\n68. PRODUCTION SCALABILITY CHECKLIST")

    checklist = production_scalability_checklist()

    for item, status in checklist.items():
        print(
            f"[{'PASS' if status else 'FAIL'}] {item}"
        )


# ============================================================================
# 69. UNIT TESTS
# ============================================================================

def run_unit_tests() -> None:
    """
    Verify core calculations and edge-case handling.
    """
    print("\n69. UNIT TESTS")

    assert horizontal_capacity(100, 4) == 400

    assert abs(
        horizontal_scaling_efficiency(800, 100, 8) - 1.0
    ) < 1e-9

    assert utilization(500, 1000) == 0.5

    assert littles_law(1000, 0.01) == 10

    assert approximate_latency(0.01, 0.0) == 0.01

    assert amdahl_speedup(1.0, 4) == 4

    assert gustafson_scaled_speedup(0.0, 8) == 8

    assert batch_items([1, 2, 3, 4, 5], 2) == [
        [1, 2],
        [3, 4],
        [5],
    ]

    assert shard_by_modulo(10, 4) == 2

    assert cache_hit_rate(90, 10) == 0.9

    assert queue_backlog_after_interval(
        100,
        100,
        10,
    ) == 0

    assert exponential_backoff(3) == 4

    assert annual_downtime_minutes(0.999) > 0

    print("All unit tests passed.")


# ============================================================================
# 70. ERROR HANDLING TESTS
# ============================================================================

def run_error_handling_tests() -> None:
    print("\n70. ERROR HANDLING TESTS")

    expected_errors = 0

    tests = [
        lambda: Workload(-1, 0.1),
        lambda: Server("x", 0, 1, 1),
        lambda: horizontal_capacity(1, 0),
        lambda: utilization(1, 0),
        lambda: TokenBucket(0, 1),
        lambda: AutoScaler(100, 0, 1, 2),
        lambda: batch_items([1], 0),
        lambda: shard_by_modulo(1, 0),
        lambda: annual_downtime_minutes(1.1),
    ]

    for test in tests:
        try:
            test()
        except (ValueError, RuntimeError):
            expected_errors += 1

    print(
        f"Handled expected invalid-input cases: "
        f"{expected_errors}/{len(tests)}"
    )

    assert expected_errors == len(tests)


# ============================================================================
# 71. INTEGRATED SCALING SCENARIO
# ============================================================================

@dataclass
class ScalingScenario:
    """
    Represents a simplified production scaling scenario.
    """

    request_rate: float
    api_instance_capacity: float
    database_capacity: float
    cache_hit_rate: float
    database_request_fraction: float

    def database_load(self) -> float:
        """
        Estimate database request rate after caching.

        Only cache misses reach the database.
        """
        if not 0 <= self.cache_hit_rate <= 1:
            raise ValueError("Cache hit rate must be between 0 and 1.")

        if not 0 <= self.database_request_fraction <= 1:
            raise ValueError(
                "Database request fraction must be between 0 and 1."
            )

        cache_miss_fraction = 1 - self.cache_hit_rate

        return (
            self.request_rate
            * self.database_request_fraction
            * cache_miss_fraction
        )

    def required_api_instances(
        self,
        target_utilization: float,
    ) -> int:
        return required_instances_for_slo(
            peak_request_rate=self.request_rate,
            instance_capacity=self.api_instance_capacity,
            target_utilization=target_utilization,
        )


def demonstrate_integrated_scenario() -> None:
    print("\n71. INTEGRATED SCALING SCENARIO")

    scenario = ScalingScenario(
        request_rate=12000,
        api_instance_capacity=2000,
        database_capacity=3000,
        cache_hit_rate=0.80,
        database_request_fraction=0.60,
    )

    database_load = scenario.database_load()

    api_instances = scenario.required_api_instances(
        target_utilization=0.70
    )

    print(f"Incoming traffic: {scenario.request_rate} req/s")
    print(f"API instances required: {api_instances}")
    print(f"Estimated database load: {database_load:.0f} req/s")
    print(f"Database capacity: {scenario.database_capacity} req/s")

    if database_load > scenario.database_capacity:
        print("Diagnosis: database is a bottleneck.")
    else:
        print("Diagnosis: database capacity is sufficient in this model.")

    print(
        "This demonstrates why scaling the API tier alone may not solve "
        "an end-to-end capacity problem."
    )


# ============================================================================
# 72. ARCHITECTURE PATTERN COMPARISON
# ============================================================================

def architecture_pattern_comparison() -> None:
    print("\n72. ARCHITECTURE PATTERN COMPARISON")

    patterns = [
        (
            "Single large server",
            "Simple deployment",
            "Hardware ceiling and larger failure domain",
        ),
        (
            "Stateless horizontal fleet",
            "Strong application-tier scaling",
            "Requires distributed state and load balancing",
        ),
        (
            "Cached read-heavy service",
            "Lower backend load and latency",
            "Cache invalidation and staleness",
        ),
        (
            "Queue + workers",
            "Absorbs bursts and decouples processing",
            "Introduces asynchronous semantics and backlog management",
        ),
        (
            "Sharded database",
            "Distributes data and write/read capacity",
            "More complex queries, operations, and rebalancing",
        ),
        (
            "Read replicas",
            "Scales read workload",
            "Replication lag and read consistency concerns",
        ),
    ]

    print(
        f"{'Pattern':25} {'Strength':40} {'Trade-off'}"
    )
    print("-" * 120)

    for pattern, strength, tradeoff in patterns:
        print(
            f"{pattern:25} "
            f"{strength:40} "
            f"{tradeoff}"
        )


# ============================================================================
# 73. SCALING PHASES
# ============================================================================

def demonstrate_scaling_phases() -> None:
    print("\n73. TYPICAL SCALING PHASES")

    phases = [
        "Optimize obvious inefficient code and queries.",
        "Introduce caching where access patterns justify it.",
        "Separate synchronous and asynchronous workloads.",
        "Scale application instances horizontally.",
        "Scale database reads through replicas where appropriate.",
        "Partition or shard data when a single database becomes limiting.",
        "Distribute across failure domains or geographic regions when required.",
        "Continuously measure capacity, latency, failures, and cost.",
    ]

    for number, phase in enumerate(phases, start=1):
        print(f"{number}. {phase}")


# ============================================================================
# 74. FINAL INTEGRATION EXERCISE
# ============================================================================

def final_integration_exercise() -> None:
    """
    Evaluate a fictional service and show how several scalability concepts
    interact.
    """
    print("\n74. FINAL INTEGRATION EXERCISE")

    request_rate = 18000
    instance_capacity = 2500
    target_utilization = 0.65

    instances = required_instances_for_slo(
        peak_request_rate=request_rate,
        instance_capacity=instance_capacity,
        target_utilization=target_utilization,
        safety_factor=1.20,
    )

    api_capacity = instances * instance_capacity

    cache_hit = 0.85
    backend_fraction = 0.70

    backend_load = (
        request_rate
        * backend_fraction
        * (1 - cache_hit)
    )

    backend_capacity = 3500

    print(f"Peak request rate: {request_rate} req/s")
    print(f"Required API instances: {instances}")
    print(f"API theoretical capacity: {api_capacity} req/s")
    print(f"Cache hit rate: {cache_hit:.0%}")
    print(f"Estimated backend load: {backend_load:.0f} req/s")
    print(f"Backend capacity: {backend_capacity} req/s")

    if backend_load > backend_capacity:
        print(
            "Primary finding: backend capacity must be addressed; "
            "adding API instances alone is insufficient."
        )
    else:
        print(
            "Primary finding: backend capacity is sufficient under "
            "this simplified workload model."
        )

    print(
        "\nThe exercise illustrates the central scaling principle: "
        "the system must be evaluated as a chain of interacting resources, "
        "not as a single server-count problem."
    )


# ============================================================================
# 75. MAIN PROGRAM
# ============================================================================

def main() -> None:
    """
    Execute the complete scalability fundamentals curriculum.
    """

    explain_scalability_terms()
    demonstrate_workload()
    demonstrate_vertical_scaling()
    demonstrate_horizontal_scaling()
    demonstrate_scaling_efficiency()
    demonstrate_utilization()
    demonstrate_latency_growth()
    demonstrate_littles_law()
    demonstrate_bottleneck_detection()
    demonstrate_bottleneck_types()
    demonstrate_load_balancing()
    demonstrate_weighted_load_balancing()
    demonstrate_stateless_design()
    demonstrate_stateful_tradeoff()
    demonstrate_cache()
    demonstrate_cache_hit_rate()
    demonstrate_cache_strategies()
    demonstrate_connection_pooling()
    demonstrate_read_replication()
    demonstrate_replication_lag()
    demonstrate_sharding()
    demonstrate_hot_shards()
    demonstrate_queue()
    demonstrate_queue_backlog()
    demonstrate_backpressure()
    demonstrate_rate_limiting()
    demonstrate_token_bucket()
    demonstrate_idempotency()
    demonstrate_autoscaling()
    demonstrate_autoscaling_limitations()
    demonstrate_amdahl()
    demonstrate_gustafson()
    demonstrate_capacity_planning()
    demonstrate_availability()
    demonstrate_graceful_degradation()
    demonstrate_circuit_breaker()
    demonstrate_retry_backoff()
    demonstrate_jitter()
    demonstrate_fanout()
    demonstrate_redundancy()
    compare_scaling_strategies()
    demonstrate_bottleneck_architecture()
    demonstrate_bottleneck_removal()
    demonstrate_cost_tradeoff()
    demonstrate_latency_percentiles()
    demonstrate_load_test()
    demonstrate_scalability_test()
    demonstrate_partitioning_strategies()
    demonstrate_hashing()
    demonstrate_hot_key_splitting()
    demonstrate_batching()
    demonstrate_worker_scaling()
    demonstrate_serial_parallel_capacity()
    demonstrate_resource_profile()
    demonstrate_observability_signals()
    demonstrate_incident_diagnosis()
    demonstrate_security_considerations()
    demonstrate_noisy_neighbor()
    demonstrate_failure_domains()
    demonstrate_scale_limits()
    demonstrate_scaling_decision()
    demonstrate_scaling_edge_cases()
    demonstrate_common_scalability_mistakes()
    demonstrate_best_practices()
    compare_performance_and_scalability()
    compare_availability_and_scalability()
    compare_consistency_tradeoffs()
    demonstrate_production_checklist()

    run_unit_tests()
    run_error_handling_tests()

    demonstrate_integrated_scenario()
    architecture_pattern_comparison()
    demonstrate_scaling_phases()
    final_integration_exercise()

    print("\n" + "=" * 80)
    print("SCALABILITY FUNDAMENTALS STUDY PROGRAM COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
