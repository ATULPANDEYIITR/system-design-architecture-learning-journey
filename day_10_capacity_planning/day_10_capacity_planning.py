"""
CAPACITY PLANNING
User growth, traffic projections, and infrastructure sizing

A standalone educational program that progresses from fundamental capacity
planning concepts to advanced forecasting, workload modeling, infrastructure
sizing, queueing concepts, headroom, failure scenarios, cost modeling,
autoscaling, and production-oriented capacity decisions.

The examples use only Python's standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import ceil, log, sqrt
from statistics import mean, median, stdev
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# =============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# =============================================================================

def print_section(title: str) -> None:
    """Print a readable study section heading."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def explain_fundamentals() -> None:
    """
    Capacity planning estimates the resources required to serve a workload
    while meeting defined performance, availability, and cost objectives.

    Important terms:
      - Workload: demand placed on a system.
      - Throughput: amount of work completed per unit of time.
      - RPS: requests per second.
      - QPS: queries per second.
      - TPS: transactions per second.
      - Concurrency: work being processed at the same time.
      - Latency: time required to complete an operation.
      - Utilization: percentage of available resource capacity being consumed.
      - Headroom: unused capacity deliberately retained for spikes and growth.
      - Capacity: sustainable workload a system can serve within its SLOs.
      - Saturation: condition where a resource approaches or reaches its limit.
      - SLO: service level objective, such as a latency or availability target.
      - Peak traffic: traffic during the busiest period.
      - Growth rate: rate at which workload changes over time.
      - Forecast horizon: future period for which capacity is planned.

    A critical distinction is that capacity planning is not simply:
        "How many servers do we need?"

    A useful capacity plan connects:
        users -> behavior -> workload -> resource consumption -> infrastructure
        -> performance -> reliability -> cost.
    """
    concepts = {
        "DAU": "Daily active users",
        "MAU": "Monthly active users",
        "RPS": "Requests per second",
        "QPS": "Queries per second",
        "TPS": "Transactions per second",
        "Concurrency": "Simultaneous active work",
        "Latency": "Time taken to complete an operation",
        "Utilization": "Used capacity divided by available capacity",
        "Headroom": "Reserved capacity above expected demand",
        "SLO": "Target level of service performance or availability",
        "Saturation": "Resource approaching its practical limit",
    }

    for term, meaning in concepts.items():
        print(f"{term:15} : {meaning}")


# =============================================================================
# 2. BASIC UNIT CONVERSIONS
# =============================================================================

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR


def daily_events_to_average_rps(events_per_day: float) -> float:
    """Convert daily event volume into average requests/events per second."""
    if events_per_day < 0:
        raise ValueError("Event volume cannot be negative.")
    return events_per_day / SECONDS_PER_DAY


def daily_events_to_average_qps(queries_per_day: float) -> float:
    """Alias demonstrating that QPS follows the same basic conversion."""
    return daily_events_to_average_rps(queries_per_day)


def monthly_users_to_daily_users(
    monthly_active_users: float,
    active_days_per_month: float = 30.0,
) -> float:
    """
    Estimate average daily active users from monthly active users.

    This is an approximation. Real DAU/MAU behavior must come from measured
    user activity distributions.
    """
    if monthly_active_users < 0:
        raise ValueError("MAU cannot be negative.")
    if active_days_per_month <= 0:
        raise ValueError("Active days per month must be positive.")
    return monthly_active_users * active_days_per_month / 30.0


def users_to_daily_requests(
    daily_active_users: float,
    requests_per_user_per_day: float,
) -> float:
    """Estimate daily request volume from user activity assumptions."""
    if daily_active_users < 0 or requests_per_user_per_day < 0:
        raise ValueError("User and request counts cannot be negative.")
    return daily_active_users * requests_per_user_per_day


def demonstrate_basic_units() -> None:
    print_section("2. Basic workload conversions")

    dau = 100_000
    requests_per_user = 40
    daily_requests = users_to_daily_requests(dau, requests_per_user)
    average_rps = daily_events_to_average_rps(daily_requests)

    print(f"Daily active users:       {dau:,}")
    print(f"Requests/user/day:       {requests_per_user}")
    print(f"Daily requests:          {daily_requests:,.0f}")
    print(f"Average RPS:              {average_rps:.2f}")


# =============================================================================
# 3. USER GROWTH MODELS
# =============================================================================

def linear_growth(
    initial_value: float,
    absolute_growth_per_period: float,
    periods: int,
) -> List[float]:
    """Forecast using a constant absolute increase."""
    if periods < 0:
        raise ValueError("Periods cannot be negative.")
    if initial_value < 0:
        raise ValueError("Initial value cannot be negative.")

    return [
        initial_value + absolute_growth_per_period * period
        for period in range(periods + 1)
    ]


def percentage_growth(
    initial_value: float,
    growth_rate: float,
    periods: int,
) -> List[float]:
    """Forecast using compound percentage growth."""
    if periods < 0:
        raise ValueError("Periods cannot be negative.")
    if initial_value < 0:
        raise ValueError("Initial value cannot be negative.")
    if growth_rate <= -1:
        raise ValueError("Growth rate must be greater than -100%.")

    values = []
    value = initial_value

    for _ in range(periods + 1):
        values.append(value)
        value *= 1 + growth_rate

    return values


def compound_annual_growth_rate(
    starting_value: float,
    ending_value: float,
    years: float,
) -> float:
    """Calculate CAGR."""
    if starting_value <= 0 or ending_value < 0 or years <= 0:
        raise ValueError("CAGR requires positive start and time values.")
    return (ending_value / starting_value) ** (1 / years) - 1


def forecast_from_cagr(
    current_value: float,
    annual_growth_rate: float,
    years: int,
) -> List[float]:
    """Forecast future values using annual compound growth."""
    return percentage_growth(current_value, annual_growth_rate, years)


def demonstrate_growth_models() -> None:
    print_section("3. User growth models")

    linear = linear_growth(100_000, 20_000, 5)
    compound = percentage_growth(100_000, 0.20, 5)

    print("Linear growth:")
    for year, value in enumerate(linear):
        print(f"Year {year}: {value:,.0f}")

    print("\n20% compound annual growth:")
    for year, value in enumerate(compound):
        print(f"Year {year}: {value:,.0f}")

    cagr = compound_annual_growth_rate(100_000, 248_832, 5)
    print(f"\nCAGR from 100,000 to 248,832 over five years: {cagr:.2%}")


# =============================================================================
# 4. USER FUNNEL TO WORKLOAD MODEL
# =============================================================================

@dataclass
class UserBehavior:
    """Behavioral assumptions connecting users to application workload."""

    dau: float
    sessions_per_user_per_day: float
    requests_per_session: float
    writes_per_request: float = 0.10
    reads_per_request: float = 1.0

    def validate(self) -> None:
        fields = [
            self.dau,
            self.sessions_per_user_per_day,
            self.requests_per_session,
            self.writes_per_request,
            self.reads_per_request,
        ]
        if any(value < 0 for value in fields):
            raise ValueError("User behavior values cannot be negative.")

    def daily_requests(self) -> float:
        self.validate()
        return (
            self.dau
            * self.sessions_per_user_per_day
            * self.requests_per_session
        )

    def average_rps(self) -> float:
        return daily_events_to_average_rps(self.daily_requests())

    def daily_writes(self) -> float:
        return self.daily_requests() * self.writes_per_request

    def daily_reads(self) -> float:
        return self.daily_requests() * self.reads_per_request


def demonstrate_behavior_model() -> None:
    print_section("4. Translating users into workload")

    behavior = UserBehavior(
        dau=250_000,
        sessions_per_user_per_day=2.0,
        requests_per_session=25,
        writes_per_request=0.15,
    )

    print(f"DAU:                 {behavior.dau:,.0f}")
    print(f"Daily requests:      {behavior.daily_requests():,.0f}")
    print(f"Average RPS:         {behavior.average_rps():,.2f}")
    print(f"Daily writes:        {behavior.daily_writes():,.0f}")
    print(f"Daily reads:         {behavior.daily_reads():,.0f}")


# =============================================================================
# 5. PEAK-TO-AVERAGE MODEL
# =============================================================================

def peak_rps_from_average(
    average_rps: float,
    peak_multiplier: float,
) -> float:
    """
    Convert average traffic to estimated peak traffic.

    The multiplier should be based on historical observations when possible.
    """
    if average_rps < 0:
        raise ValueError("Average RPS cannot be negative.")
    if peak_multiplier < 1:
        raise ValueError("Peak multiplier must be at least 1.")
    return average_rps * peak_multiplier


def percentile_from_samples(
    samples: Sequence[float],
    percentile: float,
) -> float:
    """
    Calculate a simple interpolated percentile.

    This is useful for educational workload analysis. Production monitoring
    systems may use streaming or histogram-based percentile estimators.
    """
    if not samples:
        raise ValueError("At least one sample is required.")
    if not 0 <= percentile <= 100:
        raise ValueError("Percentile must be between 0 and 100.")

    ordered = sorted(samples)
    if len(ordered) == 1:
        return float(ordered[0])

    rank = (len(ordered) - 1) * percentile / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower

    return ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * fraction


def demonstrate_peak_model() -> None:
    print_section("5. Average traffic versus peak traffic")

    average_rps = 1_000
    peak_multiplier = 4
    peak_rps = peak_rps_from_average(average_rps, peak_multiplier)

    print(f"Average RPS:     {average_rps:,}")
    print(f"Peak multiplier: {peak_multiplier}x")
    print(f"Estimated peak:  {peak_rps:,} RPS")

    observed = [800, 950, 1_050, 1_100, 1_400, 1_600, 1_800, 2_100]
    print(f"P50 traffic:     {percentile_from_samples(observed, 50):,.0f}")
    print(f"P95 traffic:     {percentile_from_samples(observed, 95):,.0f}")
    print(f"P99 traffic:     {percentile_from_samples(observed, 99):,.0f}")


# =============================================================================
# 6. REQUEST MIX AND RESOURCE MULTIPLIERS
# =============================================================================

@dataclass
class RequestType:
    name: str
    percentage: float
    cpu_millicores: float
    memory_mb: float
    database_queries: float
    cache_requests: float = 0.0

    def validate(self) -> None:
        if not self.name:
            raise ValueError("Request type requires a name.")
        if self.percentage < 0:
            raise ValueError("Percentage cannot be negative.")
        if self.cpu_millicores < 0:
            raise ValueError("CPU consumption cannot be negative.")
        if self.memory_mb < 0:
            raise ValueError("Memory consumption cannot be negative.")
        if self.database_queries < 0:
            raise ValueError("Database queries cannot be negative.")
        if self.cache_requests < 0:
            raise ValueError("Cache requests cannot be negative.")


def validate_request_mix(request_types: Sequence[RequestType]) -> None:
    for request_type in request_types:
        request_type.validate()

    total = sum(item.percentage for item in request_types)

    if abs(total - 100.0) > 1e-9:
        raise ValueError(
            f"Request mix must equal 100%; received {total:.2f}%."
        )


def weighted_request_cost(
    request_types: Sequence[RequestType],
    attribute: str,
) -> float:
    """Calculate a weighted average cost per request."""
    validate_request_mix(request_types)

    return sum(
        (item.percentage / 100) * getattr(item, attribute)
        for item in request_types
    )


def demonstrate_request_mix() -> None:
    print_section("6. Request mix and resource consumption")

    request_mix = [
        RequestType(
            "Read API",
            70,
            cpu_millicores=8,
            memory_mb=10,
            database_queries=1,
            cache_requests=1,
        ),
        RequestType(
            "Write API",
            20,
            cpu_millicores=18,
            memory_mb=14,
            database_queries=3,
        ),
        RequestType(
            "Search API",
            10,
            cpu_millicores=30,
            memory_mb=25,
            database_queries=5,
            cache_requests=2,
        ),
    ]

    average_cpu = weighted_request_cost(request_mix, "cpu_millicores")
    average_memory = weighted_request_cost(request_mix, "memory_mb")
    average_db_queries = weighted_request_cost(
        request_mix,
        "database_queries",
    )

    print(f"Weighted CPU/request:        {average_cpu:.2f} millicores")
    print(f"Weighted memory/request:     {average_memory:.2f} MB")
    print(f"Weighted DB queries/request: {average_db_queries:.2f}")


# =============================================================================
# 7. INFRASTRUCTURE SIZING
# =============================================================================

@dataclass
class InstanceType:
    name: str
    cpu_cores: float
    memory_gb: float
    sustainable_rps: float
    monthly_cost: float

    def validate(self) -> None:
        if self.cpu_cores <= 0:
            raise ValueError("CPU cores must be positive.")
        if self.memory_gb <= 0:
            raise ValueError("Memory must be positive.")
        if self.sustainable_rps <= 0:
            raise ValueError("Sustainable RPS must be positive.")
        if self.monthly_cost < 0:
            raise ValueError("Monthly cost cannot be negative.")


def instances_required(
    required_rps: float,
    sustainable_rps_per_instance: float,
    utilization_target: float = 0.70,
) -> int:
    """
    Size instances while preserving a utilization target.

    Example:
        1,000 required RPS
        250 RPS sustainable capacity per instance
        70% target utilization

        effective capacity = 250 * 0.70 = 175 RPS
        instances = ceil(1000 / 175) = 6
    """
    if required_rps < 0:
        raise ValueError("Required RPS cannot be negative.")
    if sustainable_rps_per_instance <= 0:
        raise ValueError("Instance capacity must be positive.")
    if not 0 < utilization_target <= 1:
        raise ValueError("Utilization target must be between 0 and 1.")

    if required_rps == 0:
        return 0

    effective_capacity = sustainable_rps_per_instance * utilization_target
    return ceil(required_rps / effective_capacity)


def size_service(
    peak_rps: float,
    instance: InstanceType,
    utilization_target: float = 0.70,
    minimum_instances: int = 2,
) -> Dict[str, float]:
    """
    Return a basic service sizing result.

    Minimum instances provide basic redundancy. A production design may use
    availability-zone failure assumptions rather than a simple minimum count.
    """
    instance.validate()

    if minimum_instances < 0:
        raise ValueError("Minimum instances cannot be negative.")

    calculated = instances_required(
        peak_rps,
        instance.sustainable_rps,
        utilization_target,
    )

    count = max(calculated, minimum_instances)

    return {
        "instances": count,
        "capacity_rps": count * instance.sustainable_rps * utilization_target,
        "monthly_cost": count * instance.monthly_cost,
    }


def demonstrate_infrastructure_sizing() -> None:
    print_section("7. Application infrastructure sizing")

    instance = InstanceType(
        name="application-medium",
        cpu_cores=4,
        memory_gb=16,
        sustainable_rps=250,
        monthly_cost=120,
    )

    result = size_service(
        peak_rps=2_000,
        instance=instance,
        utilization_target=0.70,
        minimum_instances=2,
    )

    for key, value in result.items():
        if key == "monthly_cost":
            print(f"{key:20}: ${value:,.2f}")
        elif key == "capacity_rps":
            print(f"{key:20}: {value:,.0f} RPS")
        else:
            print(f"{key:20}: {value}")


# =============================================================================
# 8. CPU-BASED AND MEMORY-BASED SIZING
# =============================================================================

@dataclass
class ResourceRequirement:
    cpu_cores: float
    memory_gb: float
    disk_gb: float
    network_mbps: float

    def validate(self) -> None:
        if any(
            value < 0
            for value in (
                self.cpu_cores,
                self.memory_gb,
                self.disk_gb,
                self.network_mbps,
            )
        ):
            raise ValueError("Resource requirements cannot be negative.")


@dataclass
class ResourceCapacity:
    cpu_cores: float
    memory_gb: float
    disk_gb: float
    network_mbps: float

    def validate(self) -> None:
        if any(
            value <= 0
            for value in (
                self.cpu_cores,
                self.memory_gb,
                self.disk_gb,
                self.network_mbps,
            )
        ):
            raise ValueError("Resource capacities must be positive.")


def nodes_required_by_resources(
    requirement: ResourceRequirement,
    node_capacity: ResourceCapacity,
) -> Dict[str, int]:
    """
    Size nodes independently by CPU, memory, disk, and network.

    The maximum determines the bottleneck dimension.
    """
    requirement.validate()
    node_capacity.validate()

    cpu_nodes = ceil(requirement.cpu_cores / node_capacity.cpu_cores)
    memory_nodes = ceil(requirement.memory_gb / node_capacity.memory_gb)
    disk_nodes = ceil(requirement.disk_gb / node_capacity.disk_gb)
    network_nodes = ceil(
        requirement.network_mbps / node_capacity.network_mbps
    )

    total = max(cpu_nodes, memory_nodes, disk_nodes, network_nodes)

    return {
        "cpu_nodes": cpu_nodes,
        "memory_nodes": memory_nodes,
        "disk_nodes": disk_nodes,
        "network_nodes": network_nodes,
        "required_nodes": total,
    }


def demonstrate_resource_bottlenecks() -> None:
    print_section("8. Resource bottlenecks")

    workload = ResourceRequirement(
        cpu_cores=31,
        memory_gb=180,
        disk_gb=500,
        network_mbps=3_000,
    )

    node = ResourceCapacity(
        cpu_cores=8,
        memory_gb=32,
        disk_gb=1_000,
        network_mbps=1_000,
    )

    result = nodes_required_by_resources(workload, node)

    for key, value in result.items():
        print(f"{key:20}: {value}")

    bottleneck = max(
        ("CPU", result["cpu_nodes"]),
        ("Memory", result["memory_nodes"]),
        ("Disk", result["disk_nodes"]),
        ("Network", result["network_nodes"]),
        key=lambda pair: pair[1],
    )[0]

    print(f"Bottleneck dimension: {bottleneck}")


# =============================================================================
# 9. HEADROOM
# =============================================================================

def add_headroom(
    expected_capacity: float,
    headroom_percentage: float,
) -> float:
    """Increase required capacity by a deliberate safety margin."""
    if expected_capacity < 0:
        raise ValueError("Expected capacity cannot be negative.")
    if headroom_percentage < 0:
        raise ValueError("Headroom cannot be negative.")

    return expected_capacity * (1 + headroom_percentage / 100)


def demonstrate_headroom() -> None:
    print_section("9. Capacity headroom")

    expected = 5_000
    for headroom in (10, 25, 50):
        planned = add_headroom(expected, headroom)
        print(
            f"{headroom:>3}% headroom -> "
            f"{planned:,.0f} planned capacity"
        )


# =============================================================================
# 10. TRAFFIC SEASONALITY
# =============================================================================

@dataclass
class TrafficObservation:
    period: str
    average_rps: float
    peak_rps: float


def calculate_peak_multiplier(
    observation: TrafficObservation,
) -> float:
    if observation.average_rps <= 0:
        raise ValueError("Average RPS must be positive.")
    if observation.peak_rps < observation.average_rps:
        raise ValueError("Peak RPS cannot be below average RPS.")
    return observation.peak_rps / observation.average_rps


def forecast_seasonal_rps(
    baseline_rps: float,
    growth_rate: float,
    seasonal_multiplier: float,
) -> float:
    if baseline_rps < 0:
        raise ValueError("Baseline RPS cannot be negative.")
    if growth_rate <= -1:
        raise ValueError("Growth rate cannot be -100% or lower.")
    if seasonal_multiplier < 0:
        raise ValueError("Seasonal multiplier cannot be negative.")

    return baseline_rps * (1 + growth_rate) * seasonal_multiplier


def demonstrate_seasonality() -> None:
    print_section("10. Seasonality and traffic spikes")

    historical = [
        TrafficObservation("January", 800, 1_500),
        TrafficObservation("February", 850, 1_600),
        TrafficObservation("March", 900, 1_800),
        TrafficObservation("Festival", 1_200, 4_000),
    ]

    for observation in historical:
        multiplier = calculate_peak_multiplier(observation)
        print(
            f"{observation.period:10} "
            f"peak multiplier = {multiplier:.2f}x"
        )

    future = forecast_seasonal_rps(
        baseline_rps=2_000,
        growth_rate=0.30,
        seasonal_multiplier=2.5,
    )

    print(f"\nFuture seasonal peak: {future:,.0f} RPS")


# =============================================================================
# 11. DATABASE CAPACITY
# =============================================================================

@dataclass
class DatabaseWorkload:
    application_rps: float
    queries_per_request: float
    writes_per_request: float
    read_cache_hit_rate: float

    def validate(self) -> None:
        if self.application_rps < 0:
            raise ValueError("Application RPS cannot be negative.")
        if self.queries_per_request < 0:
            raise ValueError("Queries/request cannot be negative.")
        if self.writes_per_request < 0:
            raise ValueError("Writes/request cannot be negative.")
        if not 0 <= self.read_cache_hit_rate <= 1:
            raise ValueError("Cache hit rate must be between 0 and 1.")

    def database_qps(self) -> float:
        self.validate()
        database_reads = (
            self.application_rps
            * self.queries_per_request
            * (1 - self.read_cache_hit_rate)
        )
        database_writes = self.application_rps * self.writes_per_request
        return database_reads + database_writes


def demonstrate_database_sizing() -> None:
    print_section("11. Database workload")

    workload = DatabaseWorkload(
        application_rps=5_000,
        queries_per_request=3,
        writes_per_request=0.20,
        read_cache_hit_rate=0.70,
    )

    print(f"Application RPS: {workload.application_rps:,.0f}")
    print(f"Database QPS:    {workload.database_qps():,.0f}")


# =============================================================================
# 12. CACHE CAPACITY
# =============================================================================

def estimate_cache_request_rate(
    application_rps: float,
    cache_requests_per_application_request: float,
) -> float:
    if application_rps < 0:
        raise ValueError("Application RPS cannot be negative.")
    if cache_requests_per_application_request < 0:
        raise ValueError("Cache request multiplier cannot be negative.")

    return application_rps * cache_requests_per_application_request


def estimate_cache_memory(
    objects: int,
    average_object_kb: float,
    replication_factor: int = 1,
    overhead_factor: float = 1.20,
) -> float:
    """
    Estimate cache memory in GB.

    overhead_factor accounts for metadata, fragmentation, and allocator
    overhead. Real systems should measure actual memory efficiency.
    """
    if objects < 0:
        raise ValueError("Object count cannot be negative.")
    if average_object_kb < 0:
        raise ValueError("Object size cannot be negative.")
    if replication_factor <= 0:
        raise ValueError("Replication factor must be positive.")
    if overhead_factor < 1:
        raise ValueError("Overhead factor must be at least 1.")

    total_kb = (
        objects
        * average_object_kb
        * replication_factor
        * overhead_factor
    )

    return total_kb / (1024 * 1024)


def demonstrate_cache_capacity() -> None:
    print_section("12. Cache sizing")

    cache_rps = estimate_cache_request_rate(5_000, 1.5)
    memory = estimate_cache_memory(
        objects=10_000_000,
        average_object_kb=4,
        replication_factor=2,
        overhead_factor=1.25,
    )

    print(f"Cache request rate: {cache_rps:,.0f} requests/sec")
    print(f"Estimated cache memory: {memory:,.2f} GB")


# =============================================================================
# 13. STORAGE CAPACITY
# =============================================================================

@dataclass
class StoragePlan:
    records_per_day: float
    average_record_kb: float
    retention_days: int
    replication_factor: int = 3
    compression_ratio: float = 1.0

    def validate(self) -> None:
        if self.records_per_day < 0:
            raise ValueError("Records/day cannot be negative.")
        if self.average_record_kb < 0:
            raise ValueError("Record size cannot be negative.")
        if self.retention_days < 0:
            raise ValueError("Retention cannot be negative.")
        if self.replication_factor <= 0:
            raise ValueError("Replication factor must be positive.")
        if self.compression_ratio <= 0:
            raise ValueError("Compression ratio must be positive.")


def estimate_storage_gb(plan: StoragePlan) -> float:
    plan.validate()

    logical_kb = (
        plan.records_per_day
        * plan.average_record_kb
        * plan.retention_days
    )

    physical_kb = (
        logical_kb
        * plan.replication_factor
        / plan.compression_ratio
    )

    return physical_kb / (1024 * 1024)


def demonstrate_storage() -> None:
    print_section("13. Storage planning")

    plan = StoragePlan(
        records_per_day=20_000_000,
        average_record_kb=2,
        retention_days=365,
        replication_factor=3,
        compression_ratio=2.5,
    )

    storage = estimate_storage_gb(plan)

    print(f"Estimated physical storage: {storage:,.0f} GB")
    print(f"Estimated physical storage: {storage / 1024:,.2f} TB")


# =============================================================================
# 14. BANDWIDTH CAPACITY
# =============================================================================

def estimate_bandwidth_mbps(
    requests_per_second: float,
    average_response_kb: float,
    average_request_kb: float = 0,
) -> float:
    """Estimate network bandwidth from request/response size."""
    if requests_per_second < 0:
        raise ValueError("RPS cannot be negative.")
    if average_response_kb < 0 or average_request_kb < 0:
        raise ValueError("Payload sizes cannot be negative.")

    total_kb_per_second = requests_per_second * (
        average_request_kb + average_response_kb
    )

    return total_kb_per_second * 8 / 1024


def demonstrate_bandwidth() -> None:
    print_section("14. Network bandwidth")

    bandwidth = estimate_bandwidth_mbps(
        requests_per_second=8_000,
        average_response_kb=12,
        average_request_kb=2,
    )

    print(f"Estimated bandwidth: {bandwidth:,.2f} Mbps")
    print(f"Estimated bandwidth: {bandwidth / 1_000:.2f} Gbps")


# =============================================================================
# 15. QUEUEING AND CONCURRENCY
# =============================================================================

def concurrency_from_rps_and_latency(
    rps: float,
    average_latency_seconds: float,
) -> float:
    """
    Little's Law for a stable system:
        L = lambda * W

    L = average items in the system
    lambda = arrival rate
    W = average time in system
    """
    if rps < 0:
        raise ValueError("RPS cannot be negative.")
    if average_latency_seconds < 0:
        raise ValueError("Latency cannot be negative.")

    return rps * average_latency_seconds


def demonstrate_littles_law() -> None:
    print_section("15. Concurrency and Little's Law")

    rps = 2_000
    latency = 0.150

    concurrency = concurrency_from_rps_and_latency(rps, latency)

    print(f"Throughput:          {rps:,.0f} RPS")
    print(f"Average latency:     {latency:.3f} seconds")
    print(f"Estimated concurrency: {concurrency:,.0f}")


# =============================================================================
# 16. CAPACITY FROM LOAD TEST RESULTS
# =============================================================================

@dataclass
class LoadTestPoint:
    rps: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    cpu_utilization: float
    memory_utilization: float
    error_rate: float


def is_within_slo(
    point: LoadTestPoint,
    max_p95_latency_ms: float,
    max_cpu_utilization: float,
    max_memory_utilization: float,
    max_error_rate: float,
) -> bool:
    """
    Determine whether a load test point satisfies operational constraints.
    """
    return (
        point.p95_latency_ms <= max_p95_latency_ms
        and point.cpu_utilization <= max_cpu_utilization
        and point.memory_utilization <= max_memory_utilization
        and point.error_rate <= max_error_rate
    )


def find_sustainable_load(
    points: Sequence[LoadTestPoint],
    max_p95_latency_ms: float,
    max_cpu_utilization: float,
    max_memory_utilization: float,
    max_error_rate: float,
) -> Optional[LoadTestPoint]:
    """Find the highest tested workload that remains within the defined SLO."""
    valid = [
        point
        for point in points
        if is_within_slo(
            point,
            max_p95_latency_ms,
            max_cpu_utilization,
            max_memory_utilization,
            max_error_rate,
        )
    ]

    if not valid:
        return None

    return max(valid, key=lambda point: point.rps)


def demonstrate_load_testing() -> None:
    print_section("16. Load testing and sustainable capacity")

    points = [
        LoadTestPoint(500, 20, 35, 60, 0.35, 0.40, 0.001),
        LoadTestPoint(1_000, 25, 45, 80, 0.52, 0.50, 0.001),
        LoadTestPoint(1_500, 35, 70, 120, 0.68, 0.60, 0.002),
        LoadTestPoint(2_000, 55, 130, 250, 0.82, 0.72, 0.008),
        LoadTestPoint(2_500, 90, 250, 500, 0.94, 0.88, 0.030),
    ]

    sustainable = find_sustainable_load(
        points,
        max_p95_latency_ms=100,
        max_cpu_utilization=0.80,
        max_memory_utilization=0.80,
        max_error_rate=0.01,
    )

    if sustainable:
        print(
            f"Sustainable tested capacity: "
            f"{sustainable.rps:,.0f} RPS"
        )
    else:
        print("No tested point satisfies all constraints.")


# =============================================================================
# 17. CAPACITY HEADROOM FROM LOAD TEST RESULTS
# =============================================================================

def safe_capacity_with_headroom(
    tested_capacity_rps: float,
    headroom_percentage: float,
) -> float:
    """
    Convert tested maximum capacity into planned operating capacity.

    Example:
        Tested maximum = 2,000 RPS
        Headroom = 25%
        Planned capacity = 1,600 RPS
    """
    if tested_capacity_rps <= 0:
        raise ValueError("Tested capacity must be positive.")
    if not 0 <= headroom_percentage < 100:
        raise ValueError("Headroom must be between 0% and 100%.")

    return tested_capacity_rps * (1 - headroom_percentage / 100)


def demonstrate_safe_capacity() -> None:
    print_section("17. Turning load-test capacity into operational capacity")

    tested = 2_000

    for headroom in (10, 20, 25, 30):
        safe = safe_capacity_with_headroom(tested, headroom)
        print(f"{headroom:>2}% reserve -> {safe:,.0f} RPS planned capacity")


# =============================================================================
# 18. AVAILABILITY-ZONE / FAILURE SIZING
# =============================================================================

def nodes_for_failure_tolerance(
    normal_nodes: int,
    failure_nodes: int,
) -> int:
    """
    Size a cluster so that it can lose failure_nodes and still have
    normal_nodes available.

    This simplified model demonstrates the principle:
        planned nodes = normal operating nodes + failure reserve.
    """
    if normal_nodes < 0 or failure_nodes < 0:
        raise ValueError("Node counts cannot be negative.")

    return normal_nodes + failure_nodes


def demonstrate_failure_tolerance() -> None:
    print_section("18. Failure-aware capacity planning")

    normal_nodes = 8
    failure_reserve = 2
    planned = nodes_for_failure_tolerance(
        normal_nodes,
        failure_reserve,
    )

    print(f"Normal nodes required: {normal_nodes}")
    print(f"Failure reserve:       {failure_reserve}")
    print(f"Planned nodes:         {planned}")


# =============================================================================
# 19. AUTOSCALING
# =============================================================================

@dataclass
class AutoscalingPolicy:
    min_instances: int
    max_instances: int
    target_rps_per_instance: float
    scale_up_threshold: float = 0.70
    scale_down_threshold: float = 0.40

    def validate(self) -> None:
        if self.min_instances < 1:
            raise ValueError("Minimum instances must be at least 1.")
        if self.max_instances < self.min_instances:
            raise ValueError("Maximum must be >= minimum.")
        if self.target_rps_per_instance <= 0:
            raise ValueError("Target RPS per instance must be positive.")
        if not 0 < self.scale_down_threshold < self.scale_up_threshold <= 1:
            raise ValueError(
                "Scaling thresholds must satisfy "
                "0 < down < up <= 1."
            )


def autoscaling_decision(
    current_instances: int,
    observed_rps: float,
    policy: AutoscalingPolicy,
) -> int:
    """
    Calculate a simple desired instance count.

    This is an educational approximation. Production autoscaling must account
    for startup time, cooldowns, stabilization, multiple metrics, and failure
    behavior.
    """
    policy.validate()

    if current_instances < policy.min_instances:
        current_instances = policy.min_instances

    current_capacity = (
        current_instances * policy.target_rps_per_instance
    )

    utilization = (
        observed_rps / current_capacity
        if current_capacity > 0
        else float("inf")
    )

    if utilization > policy.scale_up_threshold:
        desired = ceil(
            observed_rps / policy.target_rps_per_instance
        )
    elif utilization < policy.scale_down_threshold:
        desired = ceil(
            observed_rps / policy.target_rps_per_instance
        )
    else:
        desired = current_instances

    return max(
        policy.min_instances,
        min(policy.max_instances, desired),
    )


def demonstrate_autoscaling() -> None:
    print_section("19. Autoscaling")

    policy = AutoscalingPolicy(
        min_instances=3,
        max_instances=20,
        target_rps_per_instance=300,
    )

    current = 5

    for traffic in (500, 1_000, 1_500, 3_000, 5_000):
        desired = autoscaling_decision(
            current,
            traffic,
            policy,
        )
        print(
            f"Traffic={traffic:>5} RPS | "
            f"Current={current:>2} | Desired={desired:>2}"
        )
        current = desired


# =============================================================================
# 20. FORECASTING WITH MOVING AVERAGE
# =============================================================================

def moving_average(
    values: Sequence[float],
    window: int,
) -> List[float]:
    """
    Calculate trailing moving averages.

    The first values use all available observations until the full window
    becomes available.
    """
    if not values:
        return []
    if window <= 0:
        raise ValueError("Window must be positive.")

    result = []

    for index in range(len(values)):
        start = max(0, index - window + 1)
        result.append(mean(values[start:index + 1]))

    return result


def forecast_by_recent_average(
    historical_rps: Sequence[float],
    window: int,
    growth_rate: float = 0,
) -> float:
    """Forecast the next period from a recent moving average."""
    averages = moving_average(historical_rps, window)
    baseline = averages[-1]

    return baseline * (1 + growth_rate)


def demonstrate_moving_average() -> None:
    print_section("20. Moving-average forecasting")

    traffic = [
        900, 950, 1_000, 980, 1_100,
        1_200, 1_250, 1_300, 1_350,
    ]

    averages = moving_average(traffic, 3)

    for observed, average_value in zip(traffic, averages):
        print(
            f"Observed={observed:>5} | "
            f"3-period average={average_value:>7.2f}"
        )

    forecast = forecast_by_recent_average(
        traffic,
        window=3,
        growth_rate=0.15,
    )

    print(f"Forecast with 15% growth: {forecast:,.0f} RPS")


# =============================================================================
# 21. EXPONENTIAL FORECASTING
# =============================================================================

def exponential_smoothing(
    values: Sequence[float],
    alpha: float,
) -> List[float]:
    """
    Simple exponential smoothing.

    alpha close to 1 reacts strongly to recent observations.
    alpha close to 0 produces a smoother series.
    """
    if not values:
        return []
    if not 0 < alpha <= 1:
        raise ValueError("Alpha must be in (0, 1].")

    result = [float(values[0])]

    for value in values[1:]:
        smoothed = alpha * value + (1 - alpha) * result[-1]
        result.append(smoothed)

    return result


def demonstrate_exponential_smoothing() -> None:
    print_section("21. Exponential smoothing")

    traffic = [1000, 1050, 1100, 1300, 1250, 1500, 1450]

    for alpha in (0.2, 0.5, 0.8):
        smoothed = exponential_smoothing(traffic, alpha)
        print(
            f"alpha={alpha:.1f} -> "
            f"latest smoothed value={smoothed[-1]:,.2f}"
        )


# =============================================================================
# 22. SCENARIO PLANNING
# =============================================================================

@dataclass
class GrowthScenario:
    name: str
    user_growth: float
    traffic_per_user_growth: float
    peak_multiplier: float


def scenario_peak_rps(
    current_dau: float,
    current_requests_per_user_per_day: float,
    scenario: GrowthScenario,
) -> float:
    """
    Combine user growth and behavior growth.

    This is important because infrastructure demand may increase faster than
    user count when users also become more active.
    """
    if current_dau < 0 or current_requests_per_user_per_day < 0:
        raise ValueError("Current workload cannot be negative.")

    future_dau = current_dau * (1 + scenario.user_growth)
    future_requests_per_user = (
        current_requests_per_user_per_day
        * (1 + scenario.traffic_per_user_growth)
    )

    daily_requests = future_dau * future_requests_per_user
    average_rps = daily_events_to_average_rps(daily_requests)

    return average_rps * scenario.peak_multiplier


def demonstrate_scenarios() -> None:
    print_section("22. Scenario-based capacity planning")

    scenarios = [
        GrowthScenario("Conservative", 0.20, 0.05, 2.5),
        GrowthScenario("Expected", 0.40, 0.10, 3.0),
        GrowthScenario("Aggressive", 0.80, 0.25, 4.0),
    ]

    for scenario in scenarios:
        peak = scenario_peak_rps(
            current_dau=250_000,
            current_requests_per_user_per_day=50,
            scenario=scenario,
        )
        print(
            f"{scenario.name:12}: "
            f"{peak:,.0f} peak RPS"
        )


# =============================================================================
# 23. CAPACITY PLANNING WITH MULTIPLE RESOURCES
# =============================================================================

@dataclass
class CapacityDimension:
    name: str
    required: float
    available_per_instance: float
    utilization_target: float

    def required_instances(self) -> int:
        if self.required < 0:
            raise ValueError(
                f"{self.name}: requirement cannot be negative."
            )
        if self.available_per_instance <= 0:
            raise ValueError(
                f"{self.name}: available capacity must be positive."
            )
        if not 0 < self.utilization_target <= 1:
            raise ValueError(
                f"{self.name}: utilization target must be in (0, 1]."
            )

        effective = (
            self.available_per_instance
            * self.utilization_target
        )

        return ceil(self.required / effective)


def multi_resource_capacity(
    dimensions: Sequence[CapacityDimension],
) -> Tuple[int, str]:
    """Return required instances and the binding resource dimension."""
    if not dimensions:
        raise ValueError("At least one capacity dimension is required.")

    results = [
        (dimension.name, dimension.required_instances())
        for dimension in dimensions
    ]

    bottleneck_name, required_instances = max(
        results,
        key=lambda item: item[1],
    )

    return required_instances, bottleneck_name


def demonstrate_multi_resource_planning() -> None:
    print_section("23. Multi-resource capacity planning")

    dimensions = [
        CapacityDimension("CPU", 100, 8, 0.70),
        CapacityDimension("Memory", 250, 32, 0.75),
        CapacityDimension("Network", 8_000, 1_000, 0.70),
    ]

    required, bottleneck = multi_resource_capacity(dimensions)

    for dimension in dimensions:
        print(
            f"{dimension.name:10}: "
            f"{dimension.required_instances()} instances"
        )

    print(f"Required instances: {required}")
    print(f"Binding constraint:  {bottleneck}")


# =============================================================================
# 24. COST MODELING
# =============================================================================

@dataclass
class CostComponent:
    name: str
    monthly_unit_cost: float
    units: float

    @property
    def monthly_cost(self) -> float:
        return self.monthly_unit_cost * self.units


def total_monthly_cost(
    components: Sequence[CostComponent],
) -> float:
    if any(
        component.monthly_unit_cost < 0 or component.units < 0
        for component in components
    ):
        raise ValueError("Costs and units cannot be negative.")

    return sum(component.monthly_cost for component in components)


def demonstrate_cost_model() -> None:
    print_section("24. Infrastructure cost modeling")

    components = [
        CostComponent("Application instances", 120, 12),
        CostComponent("Database", 900, 2),
        CostComponent("Cache", 350, 3),
        CostComponent("Load balancer", 180, 2),
        CostComponent("Storage", 0.08, 5_000),
    ]

    total = total_monthly_cost(components)

    for component in components:
        print(
            f"{component.name:25}: "
            f"${component.monthly_cost:,.2f}"
        )

    print(f"{'Total monthly cost':25}: ${total:,.2f}")


# =============================================================================
# 25. COST PER USER AND COST PER REQUEST
# =============================================================================

def cost_per_active_user(
    monthly_cost: float,
    monthly_active_users: float,
) -> float:
    if monthly_cost < 0:
        raise ValueError("Monthly cost cannot be negative.")
    if monthly_active_users <= 0:
        raise ValueError("MAU must be positive.")

    return monthly_cost / monthly_active_users


def cost_per_million_requests(
    monthly_cost: float,
    monthly_requests: float,
) -> float:
    if monthly_cost < 0:
        raise ValueError("Monthly cost cannot be negative.")
    if monthly_requests <= 0:
        raise ValueError("Monthly requests must be positive.")

    return monthly_cost / monthly_requests * 1_000_000


def demonstrate_unit_economics() -> None:
    print_section("25. Capacity economics")

    monthly_cost = 8_500
    mau = 500_000
    monthly_requests = 400_000_000

    print(
        f"Cost per MAU: "
        f"${cost_per_active_user(monthly_cost, mau):.4f}"
    )
    print(
        f"Cost per million requests: "
        f"${cost_per_million_requests(monthly_cost, monthly_requests):.2f}"
    )


# =============================================================================
# 26. CAPACITY PLANNING WORKSHEET
# =============================================================================

@dataclass
class CapacityPlan:
    current_users: float
    user_growth_rate: float
    activity_growth_rate: float
    requests_per_user_per_day: float
    peak_multiplier: float
    utilization_target: float
    instance_capacity_rps: float
    minimum_instances: int
    failure_reserve_instances: int = 0
    additional_headroom_percentage: float = 0

    def validate(self) -> None:
        if self.current_users < 0:
            raise ValueError("Current users cannot be negative.")
        if self.user_growth_rate <= -1:
            raise ValueError("User growth rate must be above -100%.")
        if self.activity_growth_rate <= -1:
            raise ValueError(
                "Activity growth rate must be above -100%."
            )
        if self.requests_per_user_per_day < 0:
            raise ValueError("Requests/user/day cannot be negative.")
        if self.peak_multiplier < 1:
            raise ValueError("Peak multiplier must be at least 1.")
        if not 0 < self.utilization_target <= 1:
            raise ValueError("Utilization target must be in (0, 1].")
        if self.instance_capacity_rps <= 0:
            raise ValueError("Instance capacity must be positive.")
        if self.minimum_instances < 0:
            raise ValueError("Minimum instances cannot be negative.")
        if self.failure_reserve_instances < 0:
            raise ValueError("Failure reserve cannot be negative.")
        if self.additional_headroom_percentage < 0:
            raise ValueError("Headroom cannot be negative.")


def create_capacity_plan(
    plan: CapacityPlan,
    periods: int,
) -> List[Dict[str, float]]:
    """
    Build a multi-period capacity forecast.

    The model compounds both user growth and per-user activity growth.
    """
    plan.validate()

    if periods < 0:
        raise ValueError("Periods cannot be negative.")

    rows = []

    for period in range(periods + 1):
        users = plan.current_users * (
            1 + plan.user_growth_rate
        ) ** period

        requests_per_user = plan.requests_per_user_per_day * (
            1 + plan.activity_growth_rate
        ) ** period

        daily_requests = users * requests_per_user
        average_rps = daily_events_to_average_rps(daily_requests)
        peak_rps = average_rps * plan.peak_multiplier

        effective_instance_capacity = (
            plan.instance_capacity_rps
            * plan.utilization_target
        )

        service_instances = ceil(
            peak_rps / effective_instance_capacity
        ) if peak_rps > 0 else 0

        service_instances = max(
            service_instances,
            plan.minimum_instances,
        )

        total_instances = (
            service_instances
            + plan.failure_reserve_instances
        )

        planned_rps = (
            total_instances
            * effective_instance_capacity
        )

        planned_rps = add_headroom(
            planned_rps,
            plan.additional_headroom_percentage,
        )

        rows.append(
            {
                "period": period,
                "users": users,
                "requests_per_user_per_day": requests_per_user,
                "daily_requests": daily_requests,
                "average_rps": average_rps,
                "peak_rps": peak_rps,
                "service_instances": service_instances,
                "failure_reserve": plan.failure_reserve_instances,
                "total_instances": total_instances,
                "planned_capacity_rps": planned_rps,
            }
        )

    return rows


def demonstrate_capacity_worksheet() -> None:
    print_section("26. Complete multi-period capacity plan")

    plan = CapacityPlan(
        current_users=250_000,
        user_growth_rate=0.25,
        activity_growth_rate=0.05,
        requests_per_user_per_day=40,
        peak_multiplier=3.5,
        utilization_target=0.70,
        instance_capacity_rps=300,
        minimum_instances=3,
        failure_reserve_instances=2,
        additional_headroom_percentage=10,
    )

    forecast = create_capacity_plan(plan, periods=5)

    print(
        "Period | Users      | Avg RPS | Peak RPS | "
        "Service | Reserve | Total"
    )

    for row in forecast:
        print(
            f"{row['period']:>6} | "
            f"{row['users']:>10,.0f} | "
            f"{row['average_rps']:>7,.0f} | "
            f"{row['peak_rps']:>8,.0f} | "
            f"{row['service_instances']:>7} | "
            f"{row['failure_reserve']:>7} | "
            f"{row['total_instances']:>5}"
        )


# =============================================================================
# 27. FORECAST ERROR AND VALIDATION
# =============================================================================

def mean_absolute_percentage_error(
    actual: Sequence[float],
    forecast: Sequence[float],
) -> float:
    """
    Calculate MAPE.

    Zero actual values are excluded because percentage error is undefined
    for an actual value of zero.
    """
    if len(actual) != len(forecast):
        raise ValueError("Actual and forecast lengths must match.")

    errors = [
        abs((a - f) / a)
        for a, f in zip(actual, forecast)
        if a != 0
    ]

    if not errors:
        raise ValueError("No non-zero actual values available.")

    return mean(errors) * 100


def root_mean_squared_error(
    actual: Sequence[float],
    forecast: Sequence[float],
) -> float:
    """Calculate RMSE."""
    if len(actual) != len(forecast):
        raise ValueError("Actual and forecast lengths must match.")
    if not actual:
        raise ValueError("At least one observation is required.")

    squared_errors = [
        (a - f) ** 2
        for a, f in zip(actual, forecast)
    ]

    return sqrt(mean(squared_errors))


def demonstrate_forecast_accuracy() -> None:
    print_section("27. Forecast accuracy")

    actual = [1000, 1100, 1200, 1350, 1500]
    forecast = [980, 1120, 1180, 1300, 1450]

    print(
        f"MAPE: {mean_absolute_percentage_error(actual, forecast):.2f}%"
    )
    print(
        f"RMSE: {root_mean_squared_error(actual, forecast):.2f}"
    )


# =============================================================================
# 28. CONFIDENCE RANGES
# =============================================================================

def forecast_range(
    point_forecast: float,
    downside_percentage: float,
    upside_percentage: float,
) -> Tuple[float, float]:
    """
    Create a simple planning range.

    This is a scenario range, not a statistical confidence interval.
    """
    if point_forecast < 0:
        raise ValueError("Point forecast cannot be negative.")
    if downside_percentage < 0 or upside_percentage < 0:
        raise ValueError("Range percentages cannot be negative.")

    low = point_forecast * (1 - downside_percentage / 100)
    high = point_forecast * (1 + upside_percentage / 100)

    return low, high


def demonstrate_forecast_range() -> None:
    print_section("28. Forecast ranges")

    forecast = 10_000
    low, high = forecast_range(
        forecast,
        downside_percentage=20,
        upside_percentage=40,
    )

    print(f"Point forecast: {forecast:,.0f} RPS")
    print(f"Downside:       {low:,.0f} RPS")
    print(f"Upside:         {high:,.0f} RPS")


# =============================================================================
# 29. CAPACITY ALERT THRESHOLDS
# =============================================================================

def utilization(
    demand: float,
    capacity: float,
) -> float:
    """Return utilization as a fraction."""
    if demand < 0:
        raise ValueError("Demand cannot be negative.")
    if capacity <= 0:
        raise ValueError("Capacity must be positive.")

    return demand / capacity


def capacity_status(
    demand: float,
    capacity: float,
    warning_threshold: float = 0.70,
    critical_threshold: float = 0.90,
) -> str:
    """
    Classify current utilization.

    Production alerting should also consider duration and rate of change.
    """
    if not 0 < warning_threshold < critical_threshold <= 1:
        raise ValueError("Invalid thresholds.")

    current_utilization = utilization(demand, capacity)

    if current_utilization >= critical_threshold:
        return "CRITICAL"
    if current_utilization >= warning_threshold:
        return "WARNING"
    return "NORMAL"


def demonstrate_capacity_alerts() -> None:
    print_section("29. Capacity alerting")

    capacity = 10_000

    for demand in (3_000, 7_000, 8_500, 9_500, 11_000):
        print(
            f"Demand={demand:>6} | "
            f"Utilization={utilization(demand, capacity):>5.1%} | "
            f"Status={capacity_status(demand, capacity)}"
        )


# =============================================================================
# 30. QUEUEING THEORY: UTILIZATION AND INSTABILITY
# =============================================================================

def queue_utilization(
    arrival_rate: float,
    service_rate: float,
) -> float:
    """
    Basic single-server utilization:
        rho = lambda / mu

    If rho >= 1, a simple stable queue cannot keep up with arrivals.
    """
    if arrival_rate < 0:
        raise ValueError("Arrival rate cannot be negative.")
    if service_rate <= 0:
        raise ValueError("Service rate must be positive.")

    return arrival_rate / service_rate


def demonstrate_queue_stability() -> None:
    print_section("30. Queue stability")

    examples = [
        (80, 100),
        (95, 100),
        (100, 100),
        (120, 100),
    ]

    for arrival, service in examples:
        rho = queue_utilization(arrival, service)
        status = "stable" if rho < 1 else "unstable"
        print(
            f"Arrival={arrival:>3}/s | "
            f"Service={service:>3}/s | "
            f"Utilization={rho:.2f} | {status}"
        )


# =============================================================================
# 31. ERROR BUDGET AND CAPACITY
# =============================================================================

def monthly_error_budget(
    monthly_minutes: float,
    availability_slo: float,
) -> float:
    """
    Calculate allowed downtime from an availability SLO.

    Example:
        99.9% availability means 0.1% downtime budget.
    """
    if monthly_minutes <= 0:
        raise ValueError("Monthly minutes must be positive.")
    if not 0 < availability_slo <= 1:
        raise ValueError("Availability SLO must be in (0, 1].")

    return monthly_minutes * (1 - availability_slo)


def demonstrate_availability_capacity() -> None:
    print_section("31. Availability targets and capacity")

    monthly_minutes = 30 * 24 * 60

    for availability in (0.99, 0.999, 0.9999):
        budget = monthly_error_budget(
            monthly_minutes,
            availability,
        )

        print(
            f"{availability:.4%} availability -> "
            f"{budget:.2f} minutes/month"
        )


# =============================================================================
# 32. REDUNDANCY AND N+1
# =============================================================================

def n_plus_one_capacity(
    normal_components: int,
) -> int:
    """
    N+1 redundancy means one additional component is available beyond
    the number required under normal operation.
    """
    if normal_components < 1:
        raise ValueError("Normal component count must be positive.")

    return normal_components + 1


def n_plus_two_capacity(
    normal_components: int,
) -> int:
    """N+2 redundancy protects against two component losses."""
    if normal_components < 1:
        raise ValueError("Normal component count must be positive.")

    return normal_components + 2


def demonstrate_redundancy() -> None:
    print_section("32. N+1 and N+2 redundancy")

    normal = 10

    print(f"Normal capacity: {normal}")
    print(f"N+1 capacity:   {n_plus_one_capacity(normal)}")
    print(f"N+2 capacity:   {n_plus_two_capacity(normal)}")


# =============================================================================
# 33. TRAFFIC BURST MODEL
# =============================================================================

def burst_capacity(
    sustained_rps: float,
    burst_multiplier: float,
    burst_duration_seconds: float,
) -> Dict[str, float]:
    """
    Model a short traffic burst.

    The burst volume is useful for estimating queue depth, buffering, or
    downstream pressure.
    """
    if sustained_rps < 0:
        raise ValueError("Sustained RPS cannot be negative.")
    if burst_multiplier < 1:
        raise ValueError("Burst multiplier must be at least 1.")
    if burst_duration_seconds < 0:
        raise ValueError("Duration cannot be negative.")

    burst_rps = sustained_rps * burst_multiplier
    additional_rps = burst_rps - sustained_rps
    excess_requests = additional_rps * burst_duration_seconds

    return {
        "burst_rps": burst_rps,
        "additional_rps": additional_rps,
        "excess_requests": excess_requests,
    }


def demonstrate_bursts() -> None:
    print_section("33. Burst traffic")

    result = burst_capacity(
        sustained_rps=2_000,
        burst_multiplier=5,
        burst_duration_seconds=30,
    )

    for key, value in result.items():
        print(f"{key:20}: {value:,.0f}")


# =============================================================================
# 34. CAPACITY FOR ASYNCHRONOUS WORK
# =============================================================================

def workers_required(
    jobs_per_second: float,
    processing_time_seconds: float,
    utilization_target: float = 0.70,
) -> int:
    """
    Estimate worker concurrency using:
        required concurrency = arrival rate * processing time

    A utilization target adds operational headroom.
    """
    if jobs_per_second < 0:
        raise ValueError("Job rate cannot be negative.")
    if processing_time_seconds <= 0:
        raise ValueError("Processing time must be positive.")
    if not 0 < utilization_target <= 1:
        raise ValueError("Utilization target must be in (0, 1].")

    concurrency = (
        jobs_per_second
        * processing_time_seconds
        / utilization_target
    )

    return max(1, ceil(concurrency))


def demonstrate_worker_sizing() -> None:
    print_section("34. Background worker capacity")

    jobs = 150
    processing_time = 2.5

    workers = workers_required(
        jobs,
        processing_time,
        utilization_target=0.70,
    )

    print(f"Jobs/sec:          {jobs}")
    print(f"Processing time:   {processing_time:.2f} sec")
    print(f"Workers required:  {workers}")


# =============================================================================
# 35. API RATE LIMITING
# =============================================================================

def rate_limit_capacity(
    users: int,
    requests_per_user_per_minute: float,
) -> float:
    """Estimate total allowed request rate under a uniform rate limit."""
    if users < 0:
        raise ValueError("Users cannot be negative.")
    if requests_per_user_per_minute < 0:
        raise ValueError("Rate cannot be negative.")

    requests_per_second = (
        users
        * requests_per_user_per_minute
        / SECONDS_PER_MINUTE
    )

    return requests_per_second


def demonstrate_rate_limits() -> None:
    print_section("35. Rate limiting as a capacity control")

    allowed = rate_limit_capacity(
        users=50_000,
        requests_per_user_per_minute=20,
    )

    print(f"Maximum theoretical request rate: {allowed:,.0f} RPS")


# =============================================================================
# 36. CAPACITY PLAN FOR MULTI-TIER ARCHITECTURE
# =============================================================================

@dataclass
class TierPlan:
    name: str
    request_multiplier: float
    capacity_per_unit: float
    utilization_target: float
    minimum_units: int = 1
    monthly_cost_per_unit: float = 0

    def required_units(self, application_rps: float) -> int:
        if application_rps < 0:
            raise ValueError("Application RPS cannot be negative.")
        if self.request_multiplier < 0:
            raise ValueError("Request multiplier cannot be negative.")
        if self.capacity_per_unit <= 0:
            raise ValueError("Capacity per unit must be positive.")
        if not 0 < self.utilization_target <= 1:
            raise ValueError("Utilization target must be in (0, 1].")
        if self.minimum_units < 0:
            raise ValueError("Minimum units cannot be negative.")

        tier_load = application_rps * self.request_multiplier
        effective_capacity = (
            self.capacity_per_unit
            * self.utilization_target
        )

        calculated = ceil(
            tier_load / effective_capacity
        ) if tier_load > 0 else 0

        return max(calculated, self.minimum_units)


def demonstrate_multitier_sizing() -> None:
    print_section("36. Multi-tier architecture sizing")

    application_rps = 10_000

    tiers = [
        TierPlan(
            "API",
            request_multiplier=1,
            capacity_per_unit=400,
            utilization_target=0.70,
            minimum_units=3,
            monthly_cost_per_unit=120,
        ),
        TierPlan(
            "Database",
            request_multiplier=2,
            capacity_per_unit=1_000,
            utilization_target=0.60,
            minimum_units=2,
            monthly_cost_per_unit=900,
        ),
        TierPlan(
            "Cache",
            request_multiplier=1.5,
            capacity_per_unit=2_000,
            utilization_target=0.70,
            minimum_units=2,
            monthly_cost_per_unit=350,
        ),
        TierPlan(
            "Worker",
            request_multiplier=0.20,
            capacity_per_unit=100,
            utilization_target=0.70,
            minimum_units=2,
            monthly_cost_per_unit=100,
        ),
    ]

    total_cost = 0

    for tier in tiers:
        units = tier.required_units(application_rps)
        cost = units * tier.monthly_cost_per_unit
        total_cost += cost

        print(
            f"{tier.name:10}: "
            f"{units:>3} units | "
            f"${cost:,.2f}/month"
        )

    print(f"Total estimated tier cost: ${total_cost:,.2f}/month")


# =============================================================================
# 37. CAPACITY PLANNING WITH A TRAFFIC CURVE
# =============================================================================

def hourly_capacity_profile(
    hourly_rps: Sequence[float],
    capacity_per_instance_rps: float,
    utilization_target: float,
    minimum_instances: int,
) -> List[int]:
    """
    Convert an hourly traffic profile into hourly instance requirements.

    This helps distinguish average-day capacity from time-specific peaks.
    """
    if not hourly_rps:
        return []
    if capacity_per_instance_rps <= 0:
        raise ValueError("Capacity must be positive.")
    if not 0 < utilization_target <= 1:
        raise ValueError("Utilization target must be in (0, 1].")
    if minimum_instances < 0:
        raise ValueError("Minimum instances cannot be negative.")

    effective_capacity = (
        capacity_per_instance_rps * utilization_target
    )

    return [
        max(
            minimum_instances,
            ceil(rps / effective_capacity),
        )
        if rps > 0
        else minimum_instances
        for rps in hourly_rps
    ]


def demonstrate_hourly_profile() -> None:
    print_section("37. Hourly capacity profile")

    hourly_rps = [
        500, 450, 400, 350, 300, 350,
        500, 800, 1_200, 1_600, 1_900, 2_100,
        2_300, 2_500, 2_400, 2_200, 2_000, 1_800,
        1_700, 1_500, 1_300, 1_000, 800, 650,
    ]

    instances = hourly_capacity_profile(
        hourly_rps,
        capacity_per_instance_rps=500,
        utilization_target=0.70,
        minimum_instances=2,
    )

    for hour, (rps, count) in enumerate(
        zip(hourly_rps, instances)
    ):
        print(
            f"{hour:02d}:00 | "
            f"{rps:>4} RPS | "
            f"{count} instances"
        )


# =============================================================================
# 38. DATA VALIDATION AND OUTLIERS
# =============================================================================

def remove_non_positive_samples(
    samples: Sequence[float],
) -> List[float]:
    """Remove invalid non-positive observations from a workload series."""
    return [value for value in samples if value > 0]


def detect_outliers_iqr(
    values: Sequence[float],
) -> List[float]:
    """
    Detect IQR-based outliers.

    This is useful for exploratory analysis but should not automatically
    discard genuine production traffic spikes.
    """
    if len(values) < 4:
        return []

    ordered = sorted(values)
    q1 = percentile_from_samples(ordered, 25)
    q3 = percentile_from_samples(ordered, 75)
    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    return [
        value
        for value in values
        if value < lower or value > upper
    ]


def demonstrate_data_quality() -> None:
    print_section("38. Workload data quality")

    samples = [
        950, 1_000, 1_020, 980,
        1_050, 1_100, 1_080,
        15_000,
    ]

    outliers = detect_outliers_iqr(samples)

    print(f"Samples: {samples}")
    print(f"IQR outliers: {outliers}")

    print(
        "\nImportant: an outlier can represent either bad data "
        "or a genuine production event."
    )


# =============================================================================
# 39. CAPACITY PLANNING TESTS
# =============================================================================

def run_capacity_tests() -> None:
    print_section("39. Self-tests")

    assert daily_events_to_average_rps(86_400) == 1
    assert linear_growth(100, 10, 2) == [100, 110, 120]
    assert percentage_growth(100, 0.10, 2) == [
        100,
        110,
        121,
    ]

    assert instances_required(
        1_000,
        250,
        0.70,
    ) == 6

    assert safe_capacity_with_headroom(
        2_000,
        25,
    ) == 1_500

    assert concurrency_from_rps_and_latency(
        2_000,
        0.5,
    ) == 1_000

    assert n_plus_one_capacity(10) == 11
    assert n_plus_two_capacity(10) == 12

    assert capacity_status(
        500,
        1_000,
    ) == "NORMAL"

    assert capacity_status(
        750,
        1_000,
    ) == "WARNING"

    assert capacity_status(
        950,
        1_000,
    ) == "CRITICAL"

    try:
        instances_required(100, 0, 0.7)
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass

    try:
        UserBehavior(
            dau=-1,
            sessions_per_user_per_day=1,
            requests_per_session=1,
        ).validate()
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass

    print("All capacity planning tests passed.")


# =============================================================================
# 40. ADVANCED CAPACITY PLANNING: BOTTLENECK ANALYSIS
# =============================================================================

@dataclass
class BottleneckObservation:
    resource: str
    utilization: float
    saturation_threshold: float = 0.90

    @property
    def risk(self) -> str:
        if self.utilization >= self.saturation_threshold:
            return "HIGH"
        if self.utilization >= 0.70:
            return "MEDIUM"
        return "LOW"


def rank_bottlenecks(
    observations: Sequence[BottleneckObservation],
) -> List[BottleneckObservation]:
    """Rank resources by utilization."""
    return sorted(
        observations,
        key=lambda item: item.utilization,
        reverse=True,
    )


def demonstrate_bottleneck_analysis() -> None:
    print_section("40. Bottleneck analysis")

    observations = [
        BottleneckObservation("CPU", 0.72),
        BottleneckObservation("Memory", 0.84),
        BottleneckObservation("Database connections", 0.93),
        BottleneckObservation("Network", 0.55),
        BottleneckObservation("Disk I/O", 0.68),
    ]

    for item in rank_bottlenecks(observations):
        print(
            f"{item.resource:25} "
            f"{item.utilization:>6.1%} "
            f"risk={item.risk}"
        )


# =============================================================================
# 41. CAPACITY EFFICIENCY COMPARISON
# =============================================================================

def compare_instance_options(
    required_rps: float,
    instances: Sequence[InstanceType],
    utilization_target: float = 0.70,
) -> List[Dict[str, float]]:
    """Compare infrastructure choices by capacity and cost."""
    results = []

    for instance in instances:
        instance.validate()

        count = instances_required(
            required_rps,
            instance.sustainable_rps,
            utilization_target,
        )

        results.append(
            {
                "name": instance.name,
                "instances": count,
                "capacity_rps": (
                    count
                    * instance.sustainable_rps
                    * utilization_target
                ),
                "monthly_cost": count * instance.monthly_cost,
            }
        )

    return sorted(
        results,
        key=lambda row: row["monthly_cost"],
    )


def demonstrate_instance_comparison() -> None:
    print_section("41. Infrastructure option comparison")

    options = [
        InstanceType(
            "small",
            cpu_cores=2,
            memory_gb=8,
            sustainable_rps=100,
            monthly_cost=65,
        ),
        InstanceType(
            "medium",
            cpu_cores=4,
            memory_gb=16,
            sustainable_rps=240,
            monthly_cost=120,
        ),
        InstanceType(
            "large",
            cpu_cores=8,
            memory_gb=32,
            sustainable_rps=500,
            monthly_cost=230,
        ),
    ]

    results = compare_instance_options(
        required_rps=5_000,
        instances=options,
        utilization_target=0.70,
    )

    for result in results:
        print(
            f"{result['name']:8} | "
            f"{result['instances']:>3} instances | "
            f"${result['monthly_cost']:>8,.2f}/month | "
            f"{result['capacity_rps']:>6,.0f} RPS"
        )


# =============================================================================
# 42. CAPACITY PLANNING DECISION MATRIX
# =============================================================================

def decision_matrix(
    expected_rps: float,
    peak_rps: float,
    tested_capacity_rps: float,
    planned_capacity_rps: float,
) -> Dict[str, str]:
    """
    Translate capacity measurements into operational decisions.

    This is intentionally simple. Production decisions should include
    business criticality, SLOs, failure domains, cost, and lead time.
    """
    if any(
        value < 0
        for value in (
            expected_rps,
            peak_rps,
            tested_capacity_rps,
            planned_capacity_rps,
        )
    ):
        raise ValueError("RPS values cannot be negative.")

    return {
        "expected_demand": (
            "OK"
            if expected_rps <= planned_capacity_rps
            else "INSUFFICIENT"
        ),
        "peak_demand": (
            "OK"
            if peak_rps <= planned_capacity_rps
            else "INSUFFICIENT"
        ),
        "tested_limit": (
            "SAFE"
            if planned_capacity_rps <= tested_capacity_rps
            else "EXCEEDS TESTED LIMIT"
        ),
    }


def demonstrate_decision_matrix() -> None:
    print_section("42. Capacity decision matrix")

    result = decision_matrix(
        expected_rps=4_000,
        peak_rps=6_000,
        tested_capacity_rps=8_000,
        planned_capacity_rps=7_000,
    )

    for key, value in result.items():
        print(f"{key:20}: {value}")


# =============================================================================
# 43. ADVANCED PRODUCTION CHECKLIST
# =============================================================================

def production_capacity_checklist() -> List[str]:
    """
    Return a structured checklist of production capacity considerations.

    The checklist is executable data rather than prose so it can be adapted
    into operational tooling.
    """
    return [
        "Define workload metrics and units.",
        "Separate average, peak, burst, and sustained traffic.",
        "Measure request mix rather than treating all requests equally.",
        "Connect user growth to actual workload behavior.",
        "Use historical observations before relying on assumptions.",
        "Forecast multiple scenarios rather than one deterministic number.",
        "Load test the actual application and dependencies.",
        "Identify CPU, memory, disk, network, database, and connection bottlenecks.",
        "Define utilization targets below hard resource limits.",
        "Maintain headroom for uncertainty and sudden demand.",
        "Plan for failure of instances, zones, or dependency components.",
        "Account for startup time and autoscaling reaction time.",
        "Measure forecast error and revise assumptions.",
        "Model infrastructure cost alongside capacity.",
        "Review capacity before expected growth events.",
        "Monitor saturation indicators continuously.",
        "Document assumptions, confidence, and ownership.",
        "Test capacity changes before production rollout.",
        "Include data retention and storage growth.",
        "Include security controls that affect resource consumption.",
    ]


def demonstrate_production_checklist() -> None:
    print_section("43. Production capacity planning checklist")

    for number, item in enumerate(
        production_capacity_checklist(),
        start=1,
    ):
        print(f"{number:>2}. {item}")


# =============================================================================
# 44. SECURITY CONSIDERATIONS
# =============================================================================

def security_capacity_impacts() -> Dict[str, str]:
    """
    Security controls can materially change infrastructure requirements.
    """
    return {
        "TLS": (
            "Encryption increases CPU work and may change connection and "
            "throughput requirements."
        ),
        "WAF": (
            "Request inspection consumes compute and may add latency."
        ),
        "Authentication": (
            "Token validation, cryptographic operations, and identity "
            "lookups contribute to workload."
        ),
        "Rate limiting": (
            "Limits protect capacity by preventing uncontrolled request "
            "amplification."
        ),
        "Audit logging": (
            "Security logs increase storage, ingestion, and processing load."
        ),
        "DDoS protection": (
            "Traffic filtering changes where capacity must be provisioned "
            "and can protect application infrastructure from volumetric load."
        ),
        "Secrets management": (
            "External secret retrieval can introduce dependency traffic "
            "and availability considerations."
        ),
    }


def demonstrate_security_capacity() -> None:
    print_section("44. Security and capacity")

    for control, impact in security_capacity_impacts().items():
        print(f"{control:20}: {impact}")


# =============================================================================
# 45. CAPACITY PLANNING REPORT
# =============================================================================

def generate_capacity_report(
    current_dau: float,
    growth_rate: float,
    requests_per_user_per_day: float,
    peak_multiplier: float,
    years: int,
    instance_capacity_rps: float,
    utilization_target: float,
    monthly_cost_per_instance: float,
) -> List[Dict[str, float]]:
    """
    Generate a compact executive/engineering capacity table.

    The report intentionally keeps user growth and traffic-per-user growth
    separate in other models. Here the request rate per user is held constant.
    """
    users_forecast = percentage_growth(
        current_dau,
        growth_rate,
        years,
    )

    report = []

    for year, users in enumerate(users_forecast):
        daily_requests = users * requests_per_user_per_day
        average_rps = daily_events_to_average_rps(daily_requests)
        peak_rps = average_rps * peak_multiplier

        instances = instances_required(
            peak_rps,
            instance_capacity_rps,
            utilization_target,
        )

        report.append(
            {
                "year": year,
                "dau": users,
                "daily_requests": daily_requests,
                "average_rps": average_rps,
                "peak_rps": peak_rps,
                "instances": instances,
                "monthly_cost": (
                    instances * monthly_cost_per_instance
                ),
            }
        )

    return report


def demonstrate_capacity_report() -> None:
    print_section("45. Multi-year capacity report")

    report = generate_capacity_report(
        current_dau=500_000,
        growth_rate=0.30,
        requests_per_user_per_day=30,
        peak_multiplier=4,
        years=5,
        instance_capacity_rps=350,
        utilization_target=0.70,
        monthly_cost_per_instance=150,
    )

    print(
        "Year | DAU       | Avg RPS | Peak RPS | "
        "Instances | Monthly cost"
    )

    for row in report:
        print(
            f"{row['year']:>4} | "
            f"{row['dau']:>9,.0f} | "
            f"{row['average_rps']:>7,.0f} | "
            f"{row['peak_rps']:>8,.0f} | "
            f"{row['instances']:>9} | "
            f"${row['monthly_cost']:>11,.2f}"
        )


# =============================================================================
# 46. COMMON CAPACITY PLANNING MISTAKES
# =============================================================================

def common_capacity_mistakes() -> Dict[str, str]:
    """
    Provide concise explanations of frequent planning errors.
    """
    return {
        "Average-only planning": (
            "Sizing from average traffic can leave the system exposed to "
            "daily peaks and burst events."
        ),
        "Users equal requests": (
            "Users do not directly determine infrastructure demand. "
            "Behavior determines workload."
        ),
        "One request equals one cost": (
            "Different endpoints may have radically different CPU, memory, "
            "database, cache, and network costs."
        ),
        "Maximum hardware utilization": (
            "Running continuously near hard limits leaves little room for "
            "spikes, failures, and workload variance."
        ),
        "Ignoring dependencies": (
            "Application capacity is useless if databases, caches, queues, "
            "or external services saturate first."
        ),
        "Ignoring startup time": (
            "Autoscaling cannot instantly create capacity. Scaling delay must "
            "be considered against traffic growth speed."
        ),
        "Ignoring failures": (
            "Normal-state capacity is not necessarily sufficient after a "
            "node, zone, or dependency failure."
        ),
        "Treating forecasts as facts": (
            "Forecasts are assumptions with uncertainty. Scenario planning "
            "reduces the risk of false precision."
        ),
        "Deleting spikes as outliers": (
            "A large traffic event may be the exact event the capacity plan "
            "needs to survive."
        ),
        "Optimizing only for cost": (
            "Lower infrastructure cost can increase latency, incidents, or "
            "lost business if capacity becomes insufficient."
        ),
    }


def demonstrate_common_mistakes() -> None:
    print_section("46. Common capacity planning mistakes")

    for mistake, explanation in common_capacity_mistakes().items():
        print(f"\n{mistake}")
        print(f"  {explanation}")


# =============================================================================
# 47. EDGE CASES
# =============================================================================

def demonstrate_edge_cases() -> None:
    print_section("47. Important edge cases")

    examples = [
        ("Zero workload", lambda: instances_required(0, 100, 0.70)),
        ("Zero daily events", lambda: daily_events_to_average_rps(0)),
        ("One sample percentile", lambda: percentile_from_samples([10], 99)),
        (
            "Zero cache hit rate",
            lambda: DatabaseWorkload(
                application_rps=1_000,
                queries_per_request=2,
                writes_per_request=0.1,
                read_cache_hit_rate=0,
            ).database_qps(),
        ),
        (
            "100% cache hit rate",
            lambda: DatabaseWorkload(
                application_rps=1_000,
                queries_per_request=2,
                writes_per_request=0.1,
                read_cache_hit_rate=1,
            ).database_qps(),
        ),
    ]

    for name, operation in examples:
        try:
            print(f"{name:25}: {operation()}")
        except Exception as error:
            print(f"{name:25}: ERROR - {error}")

    invalid_examples = [
        (
            "Negative users",
            lambda: users_to_daily_requests(-1, 10),
        ),
        (
            "Invalid utilization",
            lambda: instances_required(1_000, 100, 1.5),
        ),
        (
            "Invalid request mix",
            lambda: validate_request_mix(
                [
                    RequestType(
                        "A",
                        60,
                        1,
                        1,
                        1,
                    )
                ]
            ),
        ),
    ]

    for name, operation in invalid_examples:
        try:
            operation()
            print(f"{name:25}: unexpectedly accepted")
        except ValueError as error:
            print(f"{name:25}: correctly rejected ({error})")


# =============================================================================
# 48. COMPLETE EXAMPLE
# =============================================================================

def run_end_to_end_capacity_case() -> None:
    """
    End-to-end example:

        1. Start with active users.
        2. Forecast users.
        3. Translate activity into requests.
        4. Convert requests to average RPS.
        5. Apply peak behavior.
        6. Add planning headroom.
        7. Size instances.
        8. Add failure reserve.
        9. Estimate monthly cost.
    """
    print_section("48. End-to-end capacity planning case")

    current_dau = 1_000_000
    annual_user_growth = 0.35
    years = 3

    sessions_per_user_per_day = 2.5
    requests_per_session = 20
    peak_multiplier = 3.5

    instance_capacity_rps = 500
    utilization_target = 0.65
    failure_reserve = 2
    monthly_cost_per_instance = 220

    forecast_users = percentage_growth(
        current_dau,
        annual_user_growth,
        years,
    )

    print(
        "Year | Users       | Daily reqs     | Avg RPS | "
        "Peak RPS | Instances | Cost"
    )

    for year, users in enumerate(forecast_users):
        daily_requests = (
            users
            * sessions_per_user_per_day
            * requests_per_session
        )

        average_rps = daily_events_to_average_rps(
            daily_requests
        )

        peak_rps = average_rps * peak_multiplier

        service_instances = instances_required(
            peak_rps,
            instance_capacity_rps,
            utilization_target,
        )

        total_instances = (
            service_instances + failure_reserve
        )

        monthly_cost = (
            total_instances * monthly_cost_per_instance
        )

        print(
            f"{year:>4} | "
            f"{users:>11,.0f} | "
            f"{daily_requests:>13,.0f} | "
            f"{average_rps:>7,.0f} | "
            f"{peak_rps:>8,.0f} | "
            f"{total_instances:>9} | "
            f"${monthly_cost:>8,.0f}"
        )

    print(
        "\nThe resulting plan should be validated with load tests and "
        "dependency-specific capacity measurements before production use."
    )


# =============================================================================
# 49. STUDY REFERENCE: KEY FORMULAS
# =============================================================================

def print_key_formulas() -> None:
    print_section("49. Key capacity planning formulas")

    formulas = [
        (
            "Daily requests",
            "DAU × sessions/user/day × requests/session",
        ),
        (
            "Average RPS",
            "daily requests ÷ 86,400",
        ),
        (
            "Peak RPS",
            "average RPS × peak multiplier",
        ),
        (
            "Effective instance capacity",
            "tested capacity × target utilization",
        ),
        (
            "Instance count",
            "ceil(required workload ÷ effective capacity)",
        ),
        (
            "Concurrency",
            "RPS × latency in seconds",
        ),
        (
            "Storage",
            "records/day × record size × retention × replication ÷ compression",
        ),
        (
            "Bandwidth",
            "requests/sec × payload size × 8",
        ),
        (
            "Queue utilization",
            "arrival rate ÷ service rate",
        ),
        (
            "CAGR",
            "(ending ÷ starting)^(1/years) − 1",
        ),
        (
            "Cost per request",
            "monthly infrastructure cost ÷ monthly requests",
        ),
    ]

    for name, formula in formulas:
        print(f"{name:25}: {formula}")


# =============================================================================
# 50. MAIN PROGRAM
# =============================================================================

def main() -> None:
    """
    Run the complete capacity planning study program.

    The program intentionally executes all demonstrations so the file can be
    used as a single study and experimentation script.
    """
    print_section("CAPACITY PLANNING STUDY PROGRAM")

    print(
        "Topic: User growth, traffic projections, and infrastructure sizing"
    )
    print(
        "Purpose: Build a practical understanding of capacity planning "
        "from workload fundamentals through production considerations."
    )

    explain_fundamentals()
    demonstrate_basic_units()
    demonstrate_growth_models()
    demonstrate_behavior_model()
    demonstrate_peak_model()
    demonstrate_request_mix()
    demonstrate_infrastructure_sizing()
    demonstrate_resource_bottlenecks()
    demonstrate_headroom()
    demonstrate_seasonality()
    demonstrate_database_sizing()
    demonstrate_cache_capacity()
    demonstrate_storage()
    demonstrate_bandwidth()
    demonstrate_littles_law()
    demonstrate_load_testing()
    demonstrate_safe_capacity()
    demonstrate_failure_tolerance()
    demonstrate_autoscaling()
    demonstrate_moving_average()
    demonstrate_exponential_smoothing()
    demonstrate_scenarios()
    demonstrate_multi_resource_planning()
    demonstrate_cost_model()
    demonstrate_unit_economics()
    demonstrate_capacity_worksheet()
    demonstrate_forecast_accuracy()
    demonstrate_forecast_range()
    demonstrate_capacity_alerts()
    demonstrate_queue_stability()
    demonstrate_availability_capacity()
    demonstrate_redundancy()
    demonstrate_bursts()
    demonstrate_worker_sizing()
    demonstrate_rate_limits()
    demonstrate_multitier_sizing()
    demonstrate_hourly_profile()
    demonstrate_data_quality()
    demonstrate_bottleneck_analysis()
    demonstrate_instance_comparison()
    demonstrate_decision_matrix()
    demonstrate_production_checklist()
    demonstrate_security_capacity()
    demonstrate_capacity_report()
    demonstrate_common_mistakes()
    demonstrate_edge_cases()
    run_end_to_end_capacity_case()
    print_key_formulas()
    run_capacity_tests()

    print_section("END OF CAPACITY PLANNING STUDY PROGRAM")
    print(
        "The demonstrations above form a complete progression from user "
        "growth assumptions to workload forecasting, infrastructure sizing, "
        "reliability, cost, and production capacity controls."
    )


if __name__ == "__main__":
    main()
