"""
System Design Foundations: Back-of-the-Envelope Estimation
============================================================

This standalone study script teaches the quantitative foundations used in
system design interviews and early-stage architecture decisions.

Primary focus:
    - QPS / RPS estimation
    - Average vs peak traffic
    - Read/write ratios
    - Storage estimation
    - Bandwidth estimation
    - Data growth estimation
    - Capacity planning
    - Replication and redundancy
    - Caching effects
    - Compression
    - Fan-out
    - Latency and concurrency
    - Availability
    - Headroom
    - Sensitivity analysis
    - Unit conversions
    - Sanity checks
    - Worked examples
    - A reusable estimation framework
    - Advanced system-design estimation patterns

The script uses only the Python standard library.

Run:
    python system_design_estimations.py

The examples are deterministic and intended to be read as executable notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil
from typing import Iterable, Sequence


# ============================================================================
# 1. FUNDAMENTAL UNITS AND CONVERSIONS
# ============================================================================

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
SECONDS_PER_WEEK = 7 * SECONDS_PER_DAY
SECONDS_PER_MONTH = 30 * SECONDS_PER_DAY
SECONDS_PER_YEAR = 365 * SECONDS_PER_DAY

BYTES_PER_KB = 1_000
BYTES_PER_MB = 1_000_000
BYTES_PER_GB = 1_000_000_000
BYTES_PER_TB = 1_000_000_000_000
BYTES_PER_PB = 1_000_000_000_000_000

BITS_PER_BYTE = 8


def bytes_to_kb(value: float) -> float:
    return value / BYTES_PER_KB


def bytes_to_mb(value: float) -> float:
    return value / BYTES_PER_MB


def bytes_to_gb(value: float) -> float:
    return value / BYTES_PER_GB


def bytes_to_tb(value: float) -> float:
    return value / BYTES_PER_TB


def bytes_to_pb(value: float) -> float:
    return value / BYTES_PER_PB


def gb_to_bytes(value: float) -> float:
    return value * BYTES_PER_GB


def tb_to_bytes(value: float) -> float:
    return value * BYTES_PER_TB


def bits_per_second_to_bytes_per_second(bits_per_second: float) -> float:
    return bits_per_second / BITS_PER_BYTE


def bytes_per_second_to_bits_per_second(bytes_per_second: float) -> float:
    return bytes_per_second * BITS_PER_BYTE


def human_bytes(value: float) -> str:
    """Format decimal storage units for readable capacity estimates."""
    units = [
        ("PB", BYTES_PER_PB),
        ("TB", BYTES_PER_TB),
        ("GB", BYTES_PER_GB),
        ("MB", BYTES_PER_MB),
        ("KB", BYTES_PER_KB),
        ("B", 1),
    ]

    absolute_value = abs(value)

    for name, multiplier in units:
        if absolute_value >= multiplier or multiplier == 1:
            return f"{value / multiplier:.2f} {name}"

    return f"{value:.2f} B"


def human_rate_per_second(value: float) -> str:
    """Format requests/events per second."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} M/s"
    if value >= 1_000:
        return f"{value / 1_000:.2f} K/s"
    return f"{value:.2f} /s"


def human_bits_per_second(bits_per_second: float) -> str:
    """Format network throughput using decimal SI units."""
    if bits_per_second >= 1_000_000_000:
        return f"{bits_per_second / 1_000_000_000:.2f} Gbps"
    if bits_per_second >= 1_000_000:
        return f"{bits_per_second / 1_000_000:.2f} Mbps"
    if bits_per_second >= 1_000:
        return f"{bits_per_second / 1_000:.2f} Kbps"
    return f"{bits_per_second:.2f} bps"


def human_seconds(seconds: float) -> str:
    """Convert a duration into an easy-to-read representation."""
    if seconds < 1:
        return f"{seconds * 1_000:.2f} ms"

    if seconds < SECONDS_PER_MINUTE:
        return f"{seconds:.2f} s"

    if seconds < SECONDS_PER_HOUR:
        minutes = int(seconds // SECONDS_PER_MINUTE)
        remaining = seconds % SECONDS_PER_MINUTE
        return f"{minutes} min {remaining:.1f} s"

    hours = int(seconds // SECONDS_PER_HOUR)
    remaining = seconds % SECONDS_PER_HOUR
    minutes = int(remaining // SECONDS_PER_MINUTE)
    return f"{hours} h {minutes} min"


def demonstrate_units() -> None:
    print("\n" + "=" * 78)
    print("1. UNITS AND CONVERSIONS")
    print("=" * 78)

    print(f"1 GB = {BYTES_PER_GB:,} bytes")
    print(f"1 TB = {BYTES_PER_TB:,} bytes")
    print(f"1 day = {SECONDS_PER_DAY:,} seconds")
    print(f"1 year = {SECONDS_PER_YEAR:,} seconds")

    network_mbps = 100
    bytes_per_second = bits_per_second_to_bytes_per_second(
        network_mbps * 1_000_000
    )

    print(
        f"{network_mbps} Mbps = "
        f"{bytes_per_second / 1_000_000:.2f} MB/s"
    )

    print("Important: 100 Mbps is approximately 12.5 MB/s, not 100 MB/s.")


# ============================================================================
# 2. BASIC ESTIMATION FORMULAS
# ============================================================================

def requests_per_second(
    requests_per_day: float,
    utilization_fraction: float = 1.0,
) -> float:
    """
    Convert daily request volume into average QPS.

    Formula:
        average QPS = requests_per_day / seconds_per_day

    utilization_fraction can model the fraction of a day during which
    traffic is actually concentrated. For example, 0.5 means the same
    daily traffic arrives during half the day.
    """
    if requests_per_day < 0:
        raise ValueError("requests_per_day cannot be negative.")

    if not 0 < utilization_fraction <= 1:
        raise ValueError("utilization_fraction must be in (0, 1].")

    active_seconds = SECONDS_PER_DAY * utilization_fraction
    return requests_per_day / active_seconds


def daily_requests_from_qps(qps: float) -> float:
    if qps < 0:
        raise ValueError("qps cannot be negative.")

    return qps * SECONDS_PER_DAY


def peak_qps_from_average(
    average_qps: float,
    peak_multiplier: float,
) -> float:
    if average_qps < 0:
        raise ValueError("average_qps cannot be negative.")

    if peak_multiplier < 1:
        raise ValueError("peak_multiplier must be at least 1.")

    return average_qps * peak_multiplier


def write_qps_from_total(
    total_qps: float,
    write_fraction: float,
) -> float:
    if total_qps < 0:
        raise ValueError("total_qps cannot be negative.")

    if not 0 <= write_fraction <= 1:
        raise ValueError("write_fraction must be between 0 and 1.")

    return total_qps * write_fraction


def read_qps_from_total(
    total_qps: float,
    write_fraction: float,
) -> float:
    return total_qps - write_qps_from_total(total_qps, write_fraction)


def storage_growth_per_day(
    writes_per_day: float,
    bytes_per_record: float,
) -> float:
    if writes_per_day < 0 or bytes_per_record < 0:
        raise ValueError("Inputs cannot be negative.")

    return writes_per_day * bytes_per_record


def storage_growth_per_year(
    daily_storage_bytes: float,
) -> float:
    if daily_storage_bytes < 0:
        raise ValueError("daily_storage_bytes cannot be negative.")

    return daily_storage_bytes * 365


def bandwidth_bytes_per_second(
    qps: float,
    bytes_per_request: float,
) -> float:
    if qps < 0 or bytes_per_request < 0:
        raise ValueError("Inputs cannot be negative.")

    return qps * bytes_per_request


def bandwidth_bits_per_second(
    qps: float,
    bytes_per_request: float,
) -> float:
    return bytes_per_second_to_bits_per_second(
        bandwidth_bytes_per_second(qps, bytes_per_request)
    )


def demonstrate_basic_formulas() -> None:
    print("\n" + "=" * 78)
    print("2. BASIC ESTIMATION FORMULAS")
    print("=" * 78)

    daily = 10_000_000
    qps = requests_per_second(daily)

    print(f"10 million requests/day -> {qps:.2f} average QPS")
    print(f"10 million requests/day -> {daily_requests_from_qps(qps):,.0f} requests/day")

    peak = peak_qps_from_average(qps, 5)
    print(f"At a 5x peak multiplier -> {peak:.2f} peak QPS")

    writes = write_qps_from_total(peak, 0.10)
    reads = read_qps_from_total(peak, 0.10)

    print(f"At 10% writes -> {writes:.2f} write QPS")
    print(f"At 90% reads -> {reads:.2f} read QPS")


# ============================================================================
# 3. ESTIMATION PRINCIPLES
# ============================================================================

def rule_of_72_doubling_years(growth_rate_percent: float) -> float:
    """
    Rule of 72 approximation.

    Doubling time in years ~= 72 / growth rate percentage.

    It is an approximation, not an exact compounding calculation.
    """
    if growth_rate_percent <= 0:
        raise ValueError("Growth rate must be positive.")

    return 72 / growth_rate_percent


def exact_doubling_years(growth_rate_percent: float) -> float:
    """
    Exact continuous-time-independent annual compounding approximation.

    Solve:
        (1 + r)^t = 2
    """
    if growth_rate_percent <= 0:
        raise ValueError("Growth rate must be positive.")

    from math import log

    rate = growth_rate_percent / 100
    return log(2) / log(1 + rate)


def compound_growth(
    initial_value: float,
    annual_growth_rate_percent: float,
    years: float,
) -> float:
    if initial_value < 0:
        raise ValueError("initial_value cannot be negative.")

    if annual_growth_rate_percent < -100:
        raise ValueError("Annual growth rate cannot be below -100%.")

    return initial_value * (
        1 + annual_growth_rate_percent / 100
    ) ** years


def demonstrate_growth() -> None:
    print("\n" + "=" * 78)
    print("3. GROWTH AND DOUBLING")
    print("=" * 78)

    growth = 20

    print(
        f"At {growth}% annual growth, Rule of 72 gives "
        f"approximately {rule_of_72_doubling_years(growth):.2f} years to double."
    )

    print(
        f"Exact compounding approximation: "
        f"{exact_doubling_years(growth):.2f} years."
    )

    initial_storage = 10
    after_five_years = compound_growth(initial_storage, 30, 5)

    print(
        f"{initial_storage} TB growing at 30% annually for 5 years -> "
        f"{after_five_years:.2f} TB"
    )


# ============================================================================
# 4. TRAFFIC MODEL
# ============================================================================

@dataclass
class TrafficModel:
    """
    Represents a basic workload.

    users:
        Number of users in the modeled population.

    requests_per_user_per_day:
        Average requests generated by one user per day.

    write_fraction:
        Fraction of requests that mutate state.

    peak_multiplier:
        Approximate peak/average multiplier.

    average_request_bytes:
        Average response/request payload size used for bandwidth estimation.
    """

    users: int
    requests_per_user_per_day: float
    write_fraction: float
    peak_multiplier: float
    average_request_bytes: float

    def __post_init__(self) -> None:
        if self.users < 0:
            raise ValueError("users cannot be negative.")
        if self.requests_per_user_per_day < 0:
            raise ValueError("requests_per_user_per_day cannot be negative.")
        if not 0 <= self.write_fraction <= 1:
            raise ValueError("write_fraction must be between 0 and 1.")
        if self.peak_multiplier < 1:
            raise ValueError("peak_multiplier must be at least 1.")
        if self.average_request_bytes < 0:
            raise ValueError("average_request_bytes cannot be negative.")

    @property
    def requests_per_day(self) -> float:
        return self.users * self.requests_per_user_per_day

    @property
    def average_qps(self) -> float:
        return requests_per_second(self.requests_per_day)

    @property
    def peak_qps(self) -> float:
        return peak_qps_from_average(
            self.average_qps,
            self.peak_multiplier,
        )

    @property
    def average_write_qps(self) -> float:
        return self.average_qps * self.write_fraction

    @property
    def peak_write_qps(self) -> float:
        return self.peak_qps * self.write_fraction

    @property
    def average_read_qps(self) -> float:
        return self.average_qps * (1 - self.write_fraction)

    @property
    def peak_read_qps(self) -> float:
        return self.peak_qps * (1 - self.write_fraction)

    @property
    def average_bandwidth(self) -> float:
        return bandwidth_bytes_per_second(
            self.average_qps,
            self.average_request_bytes,
        )

    @property
    def peak_bandwidth(self) -> float:
        return bandwidth_bytes_per_second(
            self.peak_qps,
            self.average_request_bytes,
        )

    def report(self) -> None:
        print(f"Users: {self.users:,}")
        print(
            f"Requests/user/day: "
            f"{self.requests_per_user_per_day:,.2f}"
        )
        print(f"Total requests/day: {self.requests_per_day:,.0f}")
        print(f"Average QPS: {self.average_qps:,.2f}")
        print(f"Peak QPS: {self.peak_qps:,.2f}")
        print(f"Average read QPS: {self.average_read_qps:,.2f}")
        print(f"Average write QPS: {self.average_write_qps:,.2f}")
        print(
            f"Average bandwidth: "
            f"{human_bytes(self.average_bandwidth)}/s"
        )
        print(
            f"Peak bandwidth: "
            f"{human_bytes(self.peak_bandwidth)}/s"
        )


def demonstrate_traffic_model() -> None:
    print("\n" + "=" * 78)
    print("4. TRAFFIC MODEL")
    print("=" * 78)

    model = TrafficModel(
        users=5_000_000,
        requests_per_user_per_day=20,
        write_fraction=0.05,
        peak_multiplier=6,
        average_request_bytes=20_000,
    )

    model.report()


# ============================================================================
# 5. ACTIVE USERS VS REGISTERED USERS
# ============================================================================

@dataclass
class UserFunnel:
    registered_users: int
    daily_active_fraction: float
    requests_per_active_user_per_day: float

    def __post_init__(self) -> None:
        if self.registered_users < 0:
            raise ValueError("registered_users cannot be negative.")
        if not 0 <= self.daily_active_fraction <= 1:
            raise ValueError("daily_active_fraction must be between 0 and 1.")
        if self.requests_per_active_user_per_day < 0:
            raise ValueError(
                "requests_per_active_user_per_day cannot be negative."
            )

    @property
    def daily_active_users(self) -> float:
        return self.registered_users * self.daily_active_fraction

    @property
    def daily_requests(self) -> float:
        return (
            self.daily_active_users
            * self.requests_per_active_user_per_day
        )

    @property
    def average_qps(self) -> float:
        return requests_per_second(self.daily_requests)


def demonstrate_user_funnel() -> None:
    print("\n" + "=" * 78)
    print("5. REGISTERED USERS VS ACTIVE USERS")
    print("=" * 78)

    funnel = UserFunnel(
        registered_users=100_000_000,
        daily_active_fraction=0.10,
        requests_per_active_user_per_day=30,
    )

    print(f"Registered users: {funnel.registered_users:,}")
    print(f"Daily active users: {funnel.daily_active_users:,.0f}")
    print(f"Requests/day: {funnel.daily_requests:,.0f}")
    print(f"Average QPS: {funnel.average_qps:,.2f}")

    print(
        "A system normally should not estimate request load by treating "
        "every registered account as active at the same time."
    )


# ============================================================================
# 6. PEAK TRAFFIC AND TRAFFIC DISTRIBUTION
# ============================================================================

@dataclass
class TrafficDistribution:
    average_qps: float
    peak_multiplier: float
    burst_multiplier: float

    @property
    def peak_qps(self) -> float:
        return self.average_qps * self.peak_multiplier

    @property
    def burst_qps(self) -> float:
        return self.average_qps * self.burst_multiplier


def demonstrate_peaks() -> None:
    print("\n" + "=" * 78)
    print("6. PEAKS, BURSTS, AND HEADROOM")
    print("=" * 78)

    distribution = TrafficDistribution(
        average_qps=2_000,
        peak_multiplier=5,
        burst_multiplier=10,
    )

    print(f"Average: {distribution.average_qps:,.0f} QPS")
    print(f"Peak: {distribution.peak_qps:,.0f} QPS")
    print(f"Short burst: {distribution.burst_qps:,.0f} QPS")

    print(
        "Average capacity can be insufficient even when the average load "
        "looks modest. Capacity planning should consider peak and burst behavior."
    )


# ============================================================================
# 7. READ/WRITE RATIOS
# ============================================================================

@dataclass
class ReadWriteWorkload:
    total_qps: float
    read_to_write_ratio: float

    @property
    def write_fraction(self) -> float:
        return 1 / (self.read_to_write_ratio + 1)

    @property
    def read_fraction(self) -> float:
        return self.read_to_write_ratio / (
            self.read_to_write_ratio + 1
        )

    @property
    def read_qps(self) -> float:
        return self.total_qps * self.read_fraction

    @property
    def write_qps(self) -> float:
        return self.total_qps * self.write_fraction


def demonstrate_read_write_ratio() -> None:
    print("\n" + "=" * 78)
    print("7. READ/WRITE RATIOS")
    print("=" * 78)

    workload = ReadWriteWorkload(
        total_qps=10_000,
        read_to_write_ratio=9,
    )

    print("Workload: 9 reads : 1 write")
    print(f"Read fraction: {workload.read_fraction:.2%}")
    print(f"Write fraction: {workload.write_fraction:.2%}")
    print(f"Read QPS: {workload.read_qps:,.0f}")
    print(f"Write QPS: {workload.write_qps:,.0f}")

    print(
        "A read-heavy workload may favor caching, replicas, and read scaling. "
        "Write-heavy workloads expose database write capacity and coordination costs."
    )


# ============================================================================
# 8. STORAGE ESTIMATION
# ============================================================================

@dataclass
class StorageModel:
    records_per_day: float
    average_record_bytes: float
    retention_days: int = 365
    replication_factor: int = 1
    metadata_multiplier: float = 1.0
    compression_ratio: float = 1.0

    def __post_init__(self) -> None:
        if self.records_per_day < 0:
            raise ValueError("records_per_day cannot be negative.")
        if self.average_record_bytes < 0:
            raise ValueError("average_record_bytes cannot be negative.")
        if self.retention_days < 0:
            raise ValueError("retention_days cannot be negative.")
        if self.replication_factor < 1:
            raise ValueError("replication_factor must be at least 1.")
        if self.metadata_multiplier < 1:
            raise ValueError("metadata_multiplier must be at least 1.")
        if self.compression_ratio <= 0:
            raise ValueError("compression_ratio must be positive.")

    @property
    def raw_daily_storage(self) -> float:
        return self.records_per_day * self.average_record_bytes

    @property
    def physical_daily_storage(self) -> float:
        """
        Metadata expands the logical record size.

        compression_ratio:
            1.0 means no compression.
            2.0 means compressed representation is half the original size.
        """
        return (
            self.raw_daily_storage
            * self.metadata_multiplier
            / self.compression_ratio
            * self.replication_factor
        )

    @property
    def logical_retained_storage(self) -> float:
        return self.raw_daily_storage * self.retention_days

    @property
    def physical_retained_storage(self) -> float:
        return self.physical_daily_storage * self.retention_days

    def report(self) -> None:
        print(f"Records/day: {self.records_per_day:,.0f}")
        print(
            f"Raw record size: "
            f"{human_bytes(self.average_record_bytes)}"
        )
        print(f"Retention: {self.retention_days} days")
        print(f"Replication factor: {self.replication_factor}")
        print(f"Metadata multiplier: {self.metadata_multiplier:.2f}x")
        print(f"Compression ratio: {self.compression_ratio:.2f}x")
        print(
            f"Raw daily storage: "
            f"{human_bytes(self.raw_daily_storage)}"
        )
        print(
            f"Physical daily storage: "
            f"{human_bytes(self.physical_daily_storage)}"
        )
        print(
            f"Logical retained storage: "
            f"{human_bytes(self.logical_retained_storage)}"
        )
        print(
            f"Physical retained storage: "
            f"{human_bytes(self.physical_retained_storage)}"
        )


def demonstrate_storage() -> None:
    print("\n" + "=" * 78)
    print("8. STORAGE ESTIMATION")
    print("=" * 78)

    storage = StorageModel(
        records_per_day=100_000_000,
        average_record_bytes=2_000,
        retention_days=365,
        replication_factor=3,
        metadata_multiplier=1.25,
        compression_ratio=2,
    )

    storage.report()


# ============================================================================
# 9. STORAGE FROM QPS
# ============================================================================

def storage_from_write_qps(
    write_qps: float,
    average_record_bytes: float,
    retention_days: float,
) -> float:
    """
    Convert sustained write QPS into retained logical bytes.

    Formula:
        writes/day = write_qps * 86,400
        storage = writes/day * record_size * retention_days
    """
    if write_qps < 0:
        raise ValueError("write_qps cannot be negative.")
    if average_record_bytes < 0:
        raise ValueError("average_record_bytes cannot be negative.")
    if retention_days < 0:
        raise ValueError("retention_days cannot be negative.")

    return (
        write_qps
        * SECONDS_PER_DAY
        * average_record_bytes
        * retention_days
    )


def demonstrate_storage_from_qps() -> None:
    print("\n" + "=" * 78)
    print("9. STORAGE FROM WRITE QPS")
    print("=" * 78)

    write_qps = 1_000
    record_size = 5_000
    retention = 365

    storage = storage_from_write_qps(
        write_qps,
        record_size,
        retention,
    )

    print(f"Write rate: {write_qps:,} writes/s")
    print(f"Record size: {human_bytes(record_size)}")
    print(f"Retention: {retention} days")
    print(f"Logical retained storage: {human_bytes(storage)}")


# ============================================================================
# 10. BANDWIDTH ESTIMATION
# ============================================================================

@dataclass
class BandwidthModel:
    qps: float
    average_payload_bytes: float
    response_overhead_multiplier: float = 1.0
    compression_ratio: float = 1.0

    def __post_init__(self) -> None:
        if self.qps < 0:
            raise ValueError("qps cannot be negative.")
        if self.average_payload_bytes < 0:
            raise ValueError("average_payload_bytes cannot be negative.")
        if self.response_overhead_multiplier < 1:
            raise ValueError("overhead multiplier must be >= 1.")
        if self.compression_ratio <= 0:
            raise ValueError("compression_ratio must be positive.")

    @property
    def bytes_per_second(self) -> float:
        return (
            self.qps
            * self.average_payload_bytes
            * self.response_overhead_multiplier
            / self.compression_ratio
        )

    @property
    def bits_per_second(self) -> float:
        return self.bytes_per_second * BITS_PER_BYTE

    @property
    def bytes_per_day(self) -> float:
        return self.bytes_per_second * SECONDS_PER_DAY

    def report(self) -> None:
        print(f"QPS: {self.qps:,.0f}")
        print(
            f"Payload: "
            f"{human_bytes(self.average_payload_bytes)}"
        )
        print(
            f"Effective throughput: "
            f"{human_bytes(self.bytes_per_second)}/s"
        )
        print(
            f"Network throughput: "
            f"{human_bits_per_second(self.bits_per_second)}"
        )
        print(
            f"Daily transfer: "
            f"{human_bytes(self.bytes_per_day)}"
        )


def demonstrate_bandwidth() -> None:
    print("\n" + "=" * 78)
    print("10. BANDWIDTH ESTIMATION")
    print("=" * 78)

    bandwidth = BandwidthModel(
        qps=50_000,
        average_payload_bytes=100_000,
        response_overhead_multiplier=1.10,
        compression_ratio=2,
    )

    bandwidth.report()


# ============================================================================
# 11. REQUEST VS RESPONSE BANDWIDTH
# ============================================================================

@dataclass
class NetworkTrafficModel:
    qps: float
    request_bytes: float
    response_bytes: float

    @property
    def request_bandwidth(self) -> float:
        return self.qps * self.request_bytes

    @property
    def response_bandwidth(self) -> float:
        return self.qps * self.response_bytes

    @property
    def total_bandwidth(self) -> float:
        return self.request_bandwidth + self.response_bandwidth


def demonstrate_request_response_bandwidth() -> None:
    print("\n" + "=" * 78)
    print("11. REQUEST VS RESPONSE BANDWIDTH")
    print("=" * 78)

    network = NetworkTrafficModel(
        qps=20_000,
        request_bytes=1_000,
        response_bytes=50_000,
    )

    print(
        f"Request bandwidth: "
        f"{human_bytes(network.request_bandwidth)}/s"
    )
    print(
        f"Response bandwidth: "
        f"{human_bytes(network.response_bandwidth)}/s"
    )
    print(
        f"Combined bandwidth: "
        f"{human_bytes(network.total_bandwidth)}/s"
    )

    print(
        "For read-heavy APIs, response bandwidth can dominate because "
        "responses are often much larger than requests."
    )


# ============================================================================
# 12. CACHE HIT RATE
# ============================================================================

@dataclass
class CacheModel:
    total_qps: float
    cache_hit_rate: float

    def __post_init__(self) -> None:
        if self.total_qps < 0:
            raise ValueError("total_qps cannot be negative.")
        if not 0 <= self.cache_hit_rate <= 1:
            raise ValueError("cache_hit_rate must be between 0 and 1.")

    @property
    def cache_qps(self) -> float:
        return self.total_qps * self.cache_hit_rate

    @property
    def backend_qps(self) -> float:
        return self.total_qps * (1 - self.cache_hit_rate)


def demonstrate_cache() -> None:
    print("\n" + "=" * 78)
    print("12. CACHE HIT RATE")
    print("=" * 78)

    cache = CacheModel(
        total_qps=100_000,
        cache_hit_rate=0.95,
    )

    print(f"Total application QPS: {cache.total_qps:,.0f}")
    print(f"Cache QPS: {cache.cache_qps:,.0f}")
    print(f"Backend QPS: {cache.backend_qps:,.0f}")

    print(
        "A 95% cache hit rate means only 5% of requests reach the backend "
        "for the modeled operation."
    )


# ============================================================================
# 13. CACHE SIZE ESTIMATION
# ============================================================================

@dataclass
class CacheSizeModel:
    hot_objects: int
    average_object_bytes: int
    metadata_multiplier: float = 1.20

    @property
    def raw_size(self) -> float:
        return self.hot_objects * self.average_object_bytes

    @property
    def required_size(self) -> float:
        return self.raw_size * self.metadata_multiplier


def demonstrate_cache_size() -> None:
    print("\n" + "=" * 78)
    print("13. CACHE SIZE")
    print("=" * 78)

    cache = CacheSizeModel(
        hot_objects=10_000_000,
        average_object_bytes=4_000,
        metadata_multiplier=1.25,
    )

    print(f"Hot objects: {cache.hot_objects:,}")
    print(
        f"Raw cache content: "
        f"{human_bytes(cache.raw_size)}"
    )
    print(
        f"Estimated cache allocation: "
        f"{human_bytes(cache.required_size)}"
    )


# ============================================================================
# 14. FAN-OUT
# ============================================================================

@dataclass
class FanOutModel:
    incoming_qps: float
    downstream_calls_per_request: float

    @property
    def downstream_qps(self) -> float:
        return self.incoming_qps * self.downstream_calls_per_request


def demonstrate_fanout() -> None:
    print("\n" + "=" * 78)
    print("14. FAN-OUT")
    print("=" * 78)

    fanout = FanOutModel(
        incoming_qps=10_000,
        downstream_calls_per_request=8,
    )

    print(f"Incoming QPS: {fanout.incoming_qps:,.0f}")
    print(
        f"Average downstream calls/request: "
        f"{fanout.downstream_calls_per_request:.1f}"
    )
    print(f"Downstream QPS: {fanout.downstream_qps:,.0f}")

    print(
        "Fan-out is multiplicative. A modest frontend request rate can become "
        "a much larger internal request rate."
    )


# ============================================================================
# 15. FAN-IN
# ============================================================================

@dataclass
class FanInModel:
    producer_count: int
    events_per_producer_per_second: float

    @property
    def aggregate_qps(self) -> float:
        return self.producer_count * self.events_per_producer_per_second


def demonstrate_fan_in() -> None:
    print("\n" + "=" * 78)
    print("15. FAN-IN")
    print("=" * 78)

    fanin = FanInModel(
        producer_count=100_000,
        events_per_producer_per_second=0.2,
    )

    print(f"Producers: {fanin.producer_count:,}")
    print(f"Aggregate event rate: {fanin.aggregate_qps:,.0f} events/s")


# ============================================================================
# 16. PUB/SUB AND BROADCAST AMPLIFICATION
# ============================================================================

@dataclass
class BroadcastModel:
    published_messages_per_second: float
    average_subscribers_per_message: float

    @property
    def delivered_messages_per_second(self) -> float:
        return (
            self.published_messages_per_second
            * self.average_subscribers_per_message
        )


def demonstrate_broadcast() -> None:
    print("\n" + "=" * 78)
    print("16. BROADCAST AMPLIFICATION")
    print("=" * 78)

    broadcast = BroadcastModel(
        published_messages_per_second=2_000,
        average_subscribers_per_message=500,
    )

    print(
        f"Published messages/s: "
        f"{broadcast.published_messages_per_second:,.0f}"
    )
    print(
        f"Average subscribers/message: "
        f"{broadcast.average_subscribers_per_message:,.0f}"
    )
    print(
        f"Delivered copies/s: "
        f"{broadcast.delivered_messages_per_second:,.0f}"
    )

    print(
        "A publish rate of 2,000/s can produce one million deliveries/s "
        "when each message reaches 500 subscribers."
    )


# ============================================================================
# 17. CONCURRENCY FROM LITTLE'S LAW
# ============================================================================

def concurrent_requests(
    throughput_per_second: float,
    average_latency_seconds: float,
) -> float:
    """
    Little's Law:

        L = λW

    L = average number of items in the system
    λ = arrival/throughput rate
    W = average time in the system

    For an approximately stable system, this gives a useful estimate of
    in-flight requests.
    """
    if throughput_per_second < 0:
        raise ValueError("throughput_per_second cannot be negative.")
    if average_latency_seconds < 0:
        raise ValueError("average_latency_seconds cannot be negative.")

    return throughput_per_second * average_latency_seconds


def demonstrate_littles_law() -> None:
    print("\n" + "=" * 78)
    print("17. LITTLE'S LAW AND CONCURRENCY")
    print("=" * 78)

    qps = 5_000
    latency_ms = 100
    latency_seconds = latency_ms / 1_000

    in_flight = concurrent_requests(qps, latency_seconds)

    print(f"Throughput: {qps:,} requests/s")
    print(f"Average latency: {latency_ms} ms")
    print(f"Estimated in-flight requests: {in_flight:,.0f}")

    print(
        "At 5,000 QPS and 100 ms average latency, approximately "
        "500 requests are simultaneously in flight."
    )


# ============================================================================
# 18. CPU CAPACITY ESTIMATION
# ============================================================================

@dataclass
class CpuCapacityModel:
    target_qps: float
    cpu_milliseconds_per_request: float
    usable_cpu_fraction: float = 0.70
    cores_per_machine: int = 8

    @property
    def cpu_seconds_per_second(self) -> float:
        return self.target_qps * (
            self.cpu_milliseconds_per_request / 1_000
        )

    @property
    def required_cores(self) -> float:
        return self.cpu_seconds_per_second / self.usable_cpu_fraction

    @property
    def machines(self) -> int:
        return ceil(self.required_cores / self.cores_per_machine)


def demonstrate_cpu_capacity() -> None:
    print("\n" + "=" * 78)
    print("18. CPU CAPACITY")
    print("=" * 78)

    cpu = CpuCapacityModel(
        target_qps=20_000,
        cpu_milliseconds_per_request=5,
        usable_cpu_fraction=0.65,
        cores_per_machine=8,
    )

    print(f"Target QPS: {cpu.target_qps:,}")
    print(
        f"CPU/request: "
        f"{cpu.cpu_milliseconds_per_request:.2f} ms"
    )
    print(
        f"CPU-seconds required each second: "
        f"{cpu.cpu_seconds_per_second:,.2f}"
    )
    print(f"Estimated usable cores required: {cpu.required_cores:,.2f}")
    print(f"Estimated 8-core machines: {cpu.machines}")

    print(
        "This is a first-order estimate. Real CPU capacity depends on "
        "CPU generation, code path, garbage collection, I/O waits, "
        "contention, batching, and workload distribution."
    )


# ============================================================================
# 19. DATABASE CAPACITY
# ============================================================================

@dataclass
class DatabaseCapacityModel:
    write_qps: float
    read_qps: float
    max_write_qps_per_node: float
    max_read_qps_per_replica: float
    target_utilization: float = 0.70

    @property
    def required_write_nodes(self) -> int:
        usable_write_capacity = (
            self.max_write_qps_per_node
            * self.target_utilization
        )
        return ceil(self.write_qps / usable_write_capacity)

    @property
    def required_read_replicas(self) -> int:
        usable_read_capacity = (
            self.max_read_qps_per_replica
            * self.target_utilization
        )
        return ceil(self.read_qps / usable_read_capacity)


def demonstrate_database_capacity() -> None:
    print("\n" + "=" * 78)
    print("19. DATABASE CAPACITY")
    print("=" * 78)

    database = DatabaseCapacityModel(
        write_qps=2_000,
        read_qps=20_000,
        max_write_qps_per_node=1_000,
        max_read_qps_per_replica=5_000,
        target_utilization=0.70,
    )

    print(
        f"Estimated write nodes: "
        f"{database.required_write_nodes}"
    )
    print(
        f"Estimated read replicas: "
        f"{database.required_read_replicas}"
    )

    print(
        "A real database's sustainable QPS is workload-dependent. "
        "A single benchmark number should never be treated as universal."
    )


# ============================================================================
# 20. STORAGE IOPS
# ============================================================================

@dataclass
class IopsModel:
    operations_per_second: float
    disk_capacity_iops: float
    usable_fraction: float = 0.70

    @property
    def usable_iops_per_disk(self) -> float:
        return self.disk_capacity_iops * self.usable_fraction

    @property
    def disks_required(self) -> int:
        return ceil(
            self.operations_per_second
            / self.usable_iops_per_disk
        )


def demonstrate_iops() -> None:
    print("\n" + "=" * 78)
    print("20. STORAGE IOPS")
    print("=" * 78)

    iops = IopsModel(
        operations_per_second=25_000,
        disk_capacity_iops=10_000,
        usable_fraction=0.70,
    )

    print(f"Required IOPS: {iops.operations_per_second:,}")
    print(f"Usable IOPS/disk: {iops.usable_iops_per_disk:,.0f}")
    print(f"Estimated disks: {iops.disks_required}")

    print(
        "IOPS and storage capacity are different constraints. "
        "A disk can have enough TB but insufficient IOPS, or enough IOPS "
        "but insufficient capacity."
    )


# ============================================================================
# 21. QUEUE BACKLOG GROWTH
# ============================================================================

@dataclass
class QueueModel:
    arrival_rate: float
    processing_rate: float
    initial_messages: int = 0

    def __post_init__(self) -> None:
        if self.arrival_rate < 0:
            raise ValueError("arrival_rate cannot be negative.")
        if self.processing_rate < 0:
            raise ValueError("processing_rate cannot be negative.")
        if self.initial_messages < 0:
            raise ValueError("initial_messages cannot be negative.")

    def backlog_after(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError("seconds cannot be negative.")

        net_change = self.arrival_rate - self.processing_rate

        if net_change <= 0:
            return max(
                0,
                self.initial_messages + net_change * seconds,
            )

        return self.initial_messages + net_change * seconds


def demonstrate_queue_backlog() -> None:
    print("\n" + "=" * 78)
    print("21. QUEUE BACKLOG")
    print("=" * 78)

    queue = QueueModel(
        arrival_rate=12_000,
        processing_rate=10_000,
    )

    backlog = queue.backlog_after(300)

    print(f"Arrival rate: {queue.arrival_rate:,}/s")
    print(f"Processing rate: {queue.processing_rate:,}/s")
    print(f"Backlog after 5 minutes: {backlog:,.0f}")

    print(
        "If arrival rate persistently exceeds processing rate, backlog "
        "grows linearly until another constraint intervenes."
    )


# ============================================================================
# 22. QUEUE DRAIN TIME
# ============================================================================

def queue_drain_time(
    backlog_messages: float,
    arrival_rate: float,
    processing_rate: float,
) -> float:
    """
    Drain time requires processing_rate > arrival_rate.

    Effective drain rate:
        processing_rate - arrival_rate
    """
    if backlog_messages < 0:
        raise ValueError("backlog_messages cannot be negative.")
    if arrival_rate < 0 or processing_rate < 0:
        raise ValueError("Rates cannot be negative.")

    net_drain_rate = processing_rate - arrival_rate

    if backlog_messages == 0:
        return 0.0

    if net_drain_rate <= 0:
        raise ValueError(
            "Queue cannot drain while arrival rate is >= processing rate."
        )

    return backlog_messages / net_drain_rate


def demonstrate_queue_drain() -> None:
    print("\n" + "=" * 78)
    print("22. QUEUE DRAIN TIME")
    print("=" * 78)

    backlog = 1_000_000
    arrival_rate = 8_000
    processing_rate = 12_000

    seconds = queue_drain_time(
        backlog,
        arrival_rate,
        processing_rate,
    )

    print(f"Backlog: {backlog:,}")
    print(f"Arrival rate: {arrival_rate:,}/s")
    print(f"Processing rate: {processing_rate:,}/s")
    print(f"Drain time: {human_seconds(seconds)}")


# ============================================================================
# 23. AVAILABILITY AND DOWNTIME BUDGETS
# ============================================================================

def downtime_per_year(availability_fraction: float) -> float:
    if not 0 <= availability_fraction <= 1:
        raise ValueError("Availability must be between 0 and 1.")

    return SECONDS_PER_YEAR * (1 - availability_fraction)


def demonstrate_availability() -> None:
    print("\n" + "=" * 78)
    print("23. AVAILABILITY AND DOWNTIME")
    print("=" * 78)

    for availability in (
        0.99,
        0.999,
        0.9999,
        0.99999,
        0.999999,
    ):
        seconds = downtime_per_year(availability)
        minutes = seconds / 60

        print(
            f"{availability * 100:.4f}% availability -> "
            f"{minutes:,.2f} minutes/year"
        )

    print(
        "The number of nines has a quantitative cost. Higher availability "
        "usually requires redundancy, failure isolation, monitoring, "
        "automated recovery, and operational maturity."
    )


# ============================================================================
# 24. REPLICATION
# ============================================================================

def replicated_storage(
    logical_storage_bytes: float,
    replication_factor: int,
) -> float:
    if logical_storage_bytes < 0:
        raise ValueError("logical_storage_bytes cannot be negative.")
    if replication_factor < 1:
        raise ValueError("replication_factor must be at least 1.")

    return logical_storage_bytes * replication_factor


def demonstrate_replication() -> None:
    print("\n" + "=" * 78)
    print("24. REPLICATION")
    print("=" * 78)

    logical = tb_to_bytes(20)
    physical = replicated_storage(logical, 3)

    print(f"Logical data: {human_bytes(logical)}")
    print(f"Replication factor: 3")
    print(f"Physical data: {human_bytes(physical)}")

    print(
        "Replication increases physical storage and can increase network "
        "traffic and write amplification, while improving availability "
        "and read scalability depending on the architecture."
    )


# ============================================================================
# 25. WRITE AMPLIFICATION
# ============================================================================

@dataclass
class WriteAmplificationModel:
    logical_write_qps: float
    replication_factor: int
    index_write_factor: float = 1.0
    journal_factor: float = 1.0

    @property
    def physical_write_qps(self) -> float:
        return (
            self.logical_write_qps
            * self.replication_factor
            * self.index_write_factor
            * self.journal_factor
        )


def demonstrate_write_amplification() -> None:
    print("\n" + "=" * 78)
    print("25. WRITE AMPLIFICATION")
    print("=" * 78)

    model = WriteAmplificationModel(
        logical_write_qps=1_000,
        replication_factor=3,
        index_write_factor=1.5,
        journal_factor=1.2,
    )

    print(f"Logical writes/s: {model.logical_write_qps:,}")
    print(f"Estimated physical write operations/s: {model.physical_write_qps:,.0f}")

    print(
        "One logical application write can produce multiple physical operations "
        "through replication, indexes, journals, compaction, or storage engines."
    )


# ============================================================================
# 26. RETENTION AND DELETION
# ============================================================================

@dataclass
class RetentionModel:
    daily_ingestion_bytes: float
    retention_days: int
    deletion_grace_days: int = 0

    @property
    def maximum_resident_storage(self) -> float:
        effective_days = self.retention_days + self.deletion_grace_days
        return self.daily_ingestion_bytes * effective_days


def demonstrate_retention() -> None:
    print("\n" + "=" * 78)
    print("26. RETENTION WINDOWS")
    print("=" * 78)

    retention = RetentionModel(
        daily_ingestion_bytes=gb_to_bytes(500),
        retention_days=30,
        deletion_grace_days=3,
    )

    print(
        f"Daily ingestion: "
        f"{human_bytes(retention.daily_ingestion_bytes)}"
    )
    print(f"Retention: {retention.retention_days} days")
    print(f"Deletion grace: {retention.deletion_grace_days} days")
    print(
        f"Estimated resident storage: "
        f"{human_bytes(retention.maximum_resident_storage)}"
    )

    print(
        "Retention policies directly influence storage cost. Deletion often "
        "is not instantaneous, so operational grace periods can matter."
    )


# ============================================================================
# 27. TIME-SERIES DATA
# ============================================================================

def time_series_storage(
    devices: int,
    samples_per_device_per_second: float,
    bytes_per_sample: int,
    retention_days: int,
    replication_factor: int = 1,
) -> float:
    if devices < 0:
        raise ValueError("devices cannot be negative.")
    if samples_per_device_per_second < 0:
        raise ValueError(
            "samples_per_device_per_second cannot be negative."
        )
    if bytes_per_sample < 0:
        raise ValueError("bytes_per_sample cannot be negative.")
    if retention_days < 0:
        raise ValueError("retention_days cannot be negative.")
    if replication_factor < 1:
        raise ValueError("replication_factor must be at least 1.")

    samples_per_day = (
        devices
        * samples_per_device_per_second
        * SECONDS_PER_DAY
    )

    return (
        samples_per_day
        * bytes_per_sample
        * retention_days
        * replication_factor
    )


def demonstrate_time_series() -> None:
    print("\n" + "=" * 78)
    print("27. TIME-SERIES STORAGE")
    print("=" * 78)

    storage = time_series_storage(
        devices=1_000_000,
        samples_per_device_per_second=1,
        bytes_per_sample=100,
        retention_days=30,
        replication_factor=3,
    )

    print(
        f"30-day physical storage: "
        f"{human_bytes(storage)}"
    )


# ============================================================================
# 28. LOGGING VOLUME
# ============================================================================

def logging_storage(
    application_qps: float,
    log_lines_per_request: float,
    average_log_line_bytes: int,
    retention_days: int,
    replication_factor: int = 1,
) -> float:
    lines_per_second = application_qps * log_lines_per_request

    return (
        lines_per_second
        * average_log_line_bytes
        * SECONDS_PER_DAY
        * retention_days
        * replication_factor
    )


def demonstrate_logging_storage() -> None:
    print("\n" + "=" * 78)
    print("28. LOGGING STORAGE")
    print("=" * 78)

    storage = logging_storage(
        application_qps=100_000,
        log_lines_per_request=5,
        average_log_line_bytes=500,
        retention_days=14,
        replication_factor=3,
    )

    print(
        f"Estimated physical log storage: "
        f"{human_bytes(storage)}"
    )

    print(
        "High-volume logs can become a major storage workload. "
        "Sampling, aggregation, compression, and retention policies "
        "can materially change the estimate."
    )


# ============================================================================
# 29. IMAGE / MEDIA STORAGE
# ============================================================================

@dataclass
class MediaStorageModel:
    uploads_per_day: int
    average_file_bytes: int
    retention_days: int
    replicas: int = 1
    thumbnail_multiplier: float = 0.10

    @property
    def primary_storage(self) -> float:
        return (
            self.uploads_per_day
            * self.average_file_bytes
            * self.retention_days
            * self.replicas
        )

    @property
    def thumbnail_storage(self) -> float:
        return self.primary_storage * self.thumbnail_multiplier

    @property
    def total_storage(self) -> float:
        return self.primary_storage + self.thumbnail_storage


def demonstrate_media_storage() -> None:
    print("\n" + "=" * 78)
    print("29. MEDIA STORAGE")
    print("=" * 78)

    media = MediaStorageModel(
        uploads_per_day=2_000_000,
        average_file_bytes=2_000_000,
        retention_days=365,
        replicas=2,
        thumbnail_multiplier=0.15,
    )

    print(
        f"Primary media: "
        f"{human_bytes(media.primary_storage)}"
    )
    print(
        f"Thumbnails: "
        f"{human_bytes(media.thumbnail_storage)}"
    )
    print(
        f"Total estimated storage: "
        f"{human_bytes(media.total_storage)}"
    )


# ============================================================================
# 30. API TRAFFIC AND CDN OFFLOAD
# ============================================================================

@dataclass
class CdnModel:
    total_content_qps: float
    cache_hit_rate: float

    @property
    def origin_qps(self) -> float:
        return self.total_content_qps * (1 - self.cache_hit_rate)

    @property
    def cdn_served_qps(self) -> float:
        return self.total_content_qps * self.cache_hit_rate


def demonstrate_cdn() -> None:
    print("\n" + "=" * 78)
    print("30. CDN OFFLOAD")
    print("=" * 78)

    cdn = CdnModel(
        total_content_qps=50_000,
        cache_hit_rate=0.90,
    )

    print(f"Total content QPS: {cdn.total_content_qps:,}")
    print(f"CDN-served QPS: {cdn.cdn_served_qps:,.0f}")
    print(f"Origin QPS: {cdn.origin_qps:,.0f}")

    print(
        "A CDN can move bandwidth and request load away from origin servers, "
        "but cacheability, TTLs, invalidation, geographic distribution, "
        "and content popularity determine the actual benefit."
    )


# ============================================================================
# 31. LOAD BALANCER CAPACITY
# ============================================================================

@dataclass
class LoadBalancerModel:
    incoming_qps: float
    max_qps_per_instance: float
    target_utilization: float = 0.70

    @property
    def instances_required(self) -> int:
        usable_qps = (
            self.max_qps_per_instance
            * self.target_utilization
        )
        return ceil(self.incoming_qps / usable_qps)


def demonstrate_load_balancer() -> None:
    print("\n" + "=" * 78)
    print("31. LOAD BALANCER CAPACITY")
    print("=" * 78)

    model = LoadBalancerModel(
        incoming_qps=80_000,
        max_qps_per_instance=30_000,
        target_utilization=0.70,
    )

    print(f"Incoming QPS: {model.incoming_qps:,}")
    print(
        f"Estimated instances: "
        f"{model.instances_required}"
    )


# ============================================================================
# 32. HEADROOM
# ============================================================================

def capacity_with_headroom(
    required_capacity: float,
    headroom_fraction: float,
) -> float:
    if required_capacity < 0:
        raise ValueError("required_capacity cannot be negative.")
    if headroom_fraction < 0:
        raise ValueError("headroom_fraction cannot be negative.")

    return required_capacity * (1 + headroom_fraction)


def demonstrate_headroom() -> None:
    print("\n" + "=" * 78)
    print("32. HEADROOM")
    print("=" * 78)

    peak_qps = 100_000

    for headroom in (0.10, 0.25, 0.50):
        capacity = capacity_with_headroom(
            peak_qps,
            headroom,
        )
        print(
            f"{headroom:.0%} headroom -> "
            f"{capacity:,.0f} QPS capacity"
        )

    print(
        "Headroom protects against estimation error, traffic variation, "
        "deployment effects, failures, noisy neighbors, and temporary bursts."
    )


# ============================================================================
# 33. N+1 CAPACITY
# ============================================================================

def nodes_for_n_plus_one(
    required_capacity: float,
    capacity_per_node: float,
) -> int:
    """
    N+1 means enough nodes to satisfy required capacity even after one
    node is lost.

    If N nodes provide capacity, use N+1 nodes physically.
    """
    if required_capacity < 0 or capacity_per_node <= 0:
        raise ValueError("Invalid capacity parameters.")

    minimum_nodes = ceil(required_capacity / capacity_per_node)
    return minimum_nodes + 1


def demonstrate_n_plus_one() -> None:
    print("\n" + "=" * 78)
    print("33. N+1 CAPACITY")
    print("=" * 78)

    required_qps = 100_000
    per_node = 30_000

    nodes = nodes_for_n_plus_one(
        required_qps,
        per_node,
    )

    print(f"Required capacity: {required_qps:,} QPS")
    print(f"Capacity/node: {per_node:,} QPS")
    print(f"N+1 node count: {nodes}")

    print(
        "The exact redundancy strategy depends on failure domains. "
        "N+1 within one rack is not equivalent to redundancy across zones."
    )


# ============================================================================
# 34. MULTI-AZ / FAILURE-DOMAIN CAPACITY
# ============================================================================

def nodes_across_failure_domains(
    total_nodes_required: int,
    failure_domains: int,
    survive_domain_loss: bool = True,
) -> int:
    """
    Simplified model for evenly distributed nodes.

    If the system must survive one complete domain loss and all domains
    should carry equal load, each surviving domain must have enough capacity
    for the full workload.

    This simplified calculation assumes symmetric domains and no partial
    failure behavior.
    """
    if total_nodes_required < 0:
        raise ValueError("total_nodes_required cannot be negative.")
    if failure_domains < 1:
        raise ValueError("failure_domains must be at least 1.")

    if not survive_domain_loss or failure_domains == 1:
        return total_nodes_required

    if failure_domains == 2:
        # With two domains, one-domain survival requires both domains to
        # independently carry the full workload.
        return total_nodes_required * 2

    per_domain = ceil(total_nodes_required / (failure_domains - 1))
    return per_domain * failure_domains


def demonstrate_failure_domains() -> None:
    print("\n" + "=" * 78)
    print("34. FAILURE DOMAINS")
    print("=" * 78)

    nodes = nodes_across_failure_domains(
        total_nodes_required=10,
        failure_domains=3,
        survive_domain_loss=True,
    )

    print(
        f"10 nodes of logical capacity across 3 domains, "
        f"surviving one domain loss -> "
        f"{nodes} physical node placements in this simplified model."
    )

    print(
        "Real placement planning must account for uneven traffic, "
        "anti-affinity, quorum requirements, storage replication, "
        "zone capacity, and correlated failures."
    )


# ============================================================================
# 35. ESTIMATING UNIQUE OBJECTS
# ============================================================================

def unique_objects_from_growth(
    new_objects_per_day: float,
    days: int,
    duplicate_fraction: float,
) -> float:
    if new_objects_per_day < 0:
        raise ValueError("new_objects_per_day cannot be negative.")
    if days < 0:
        raise ValueError("days cannot be negative.")
    if not 0 <= duplicate_fraction <= 1:
        raise ValueError("duplicate_fraction must be between 0 and 1.")

    return (
        new_objects_per_day
        * days
        * (1 - duplicate_fraction)
    )


def demonstrate_deduplication() -> None:
    print("\n" + "=" * 78)
    print("35. DEDUPLICATION")
    print("=" * 78)

    unique = unique_objects_from_growth(
        new_objects_per_day=1_000_000,
        days=365,
        duplicate_fraction=0.20,
    )

    print(
        f"Unique objects after one year: "
        f"{unique:,.0f}"
    )

    print(
        "Deduplication can reduce storage, but it may increase CPU, metadata, "
        "lookup traffic, and complexity."
    )


# ============================================================================
# 36. SENSITIVITY ANALYSIS
# ============================================================================

@dataclass
class SensitivityResult:
    parameter_name: str
    low_value: float
    base_value: float
    high_value: float
    low_output: float
    base_output: float
    high_output: float


def linear_storage_sensitivity(
    daily_records: float,
    record_size_bytes: float,
    retention_days: int,
) -> list[SensitivityResult]:
    base = daily_records * record_size_bytes * retention_days

    record_counts = (
        daily_records * 0.5,
        daily_records,
        daily_records * 2,
    )

    size_values = (
        record_size_bytes * 0.5,
        record_size_bytes,
        record_size_bytes * 2,
    )

    retention_values = (
        retention_days * 0.5,
        retention_days,
        retention_days * 2,
    )

    return [
        SensitivityResult(
            "daily_records",
            record_counts[0],
            record_counts[1],
            record_counts[2],
            record_counts[0] * record_size_bytes * retention_days,
            base,
            record_counts[2] * record_size_bytes * retention_days,
        ),
        SensitivityResult(
            "record_size",
            size_values[0],
            size_values[1],
            size_values[2],
            daily_records * size_values[0] * retention_days,
            base,
            daily_records * size_values[2] * retention_days,
        ),
        SensitivityResult(
            "retention_days",
            retention_values[0],
            retention_values[1],
            retention_values[2],
            daily_records * record_size_bytes * retention_values[0],
            base,
            daily_records * record_size_bytes * retention_values[2],
        ),
    ]


def demonstrate_sensitivity() -> None:
    print("\n" + "=" * 78)
    print("36. SENSITIVITY ANALYSIS")
    print("=" * 78)

    results = linear_storage_sensitivity(
        daily_records=10_000_000,
        record_size_bytes=2_000,
        retention_days=30,
    )

    for result in results:
        print(
            f"{result.parameter_name}: "
            f"0.5x -> {human_bytes(result.low_output)}, "
            f"1x -> {human_bytes(result.base_output)}, "
            f"2x -> {human_bytes(result.high_output)}"
        )

    print(
        "Sensitivity analysis identifies assumptions that materially affect "
        "the architecture. Those assumptions deserve better measurement."
    )


# ============================================================================
# 37. ERROR BOUNDS AND RANGE ESTIMATION
# ============================================================================

@dataclass
class EstimateRange:
    low: float
    expected: float
    high: float

    def __post_init__(self) -> None:
        if not (
            0 <= self.low <= self.expected <= self.high
        ):
            raise ValueError(
                "Expected range must satisfy low <= expected <= high."
            )

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2

    @property
    def multiplicative_uncertainty(self) -> float:
        if self.low == 0:
            return float("inf")

        return self.high / self.low


def demonstrate_ranges() -> None:
    print("\n" + "=" * 78)
    print("37. RANGES INSTEAD OF FALSE PRECISION")
    print("=" * 78)

    qps = EstimateRange(
        low=30_000,
        expected=50_000,
        high=100_000,
    )

    print(f"Low estimate: {qps.low:,} QPS")
    print(f"Expected estimate: {qps.expected:,} QPS")
    print(f"High estimate: {qps.high:,} QPS")
    print(
        f"High/low ratio: "
        f"{qps.multiplicative_uncertainty:.2f}x"
    )

    print(
        "Early architecture estimates should usually be treated as ranges "
        "because user behavior, payload sizes, traffic peaks, and system "
        "efficiency are uncertain."
    )


# ============================================================================
# 38. TRAFFIC MULTIPLIERS
# ============================================================================

def combined_multiplier(*multipliers: float) -> float:
    result = 1.0

    for multiplier in multipliers:
        if multiplier < 0:
            raise ValueError("Multipliers cannot be negative.")
        result *= multiplier

    return result


def demonstrate_multipliers() -> None:
    print("\n" + "=" * 78)
    print("38. COMBINING MULTIPLIERS")
    print("=" * 78)

    base = 10_000

    growth_multiplier = 2
    peak_multiplier = 5
    headroom_multiplier = 1.25

    total_multiplier = combined_multiplier(
        growth_multiplier,
        peak_multiplier,
        headroom_multiplier,
    )

    capacity = base * total_multiplier

    print(f"Base QPS: {base:,}")
    print(f"Growth: {growth_multiplier:.2f}x")
    print(f"Peak: {peak_multiplier:.2f}x")
    print(f"Headroom: {headroom_multiplier:.2f}x")
    print(f"Combined: {total_multiplier:.2f}x")
    print(f"Planning capacity: {capacity:,.0f} QPS")

    print(
        "Multipliers should represent distinct effects. Multiplying several "
        "uncertain factors can compound uncertainty, so each assumption "
        "should be documented."
    )


# ============================================================================
# 39. UNIT-SAFE ESTIMATION
# ============================================================================

def unit_safe_qps_from_monthly_requests(
    monthly_requests: float,
    days_per_month: int = 30,
) -> float:
    if monthly_requests < 0:
        raise ValueError("monthly_requests cannot be negative.")
    if days_per_month <= 0:
        raise ValueError("days_per_month must be positive.")

    return monthly_requests / (
        days_per_month * SECONDS_PER_DAY
    )


def demonstrate_unit_safe_estimation() -> None:
    print("\n" + "=" * 78)
    print("39. UNIT-SAFE ESTIMATION")
    print("=" * 78)

    monthly = 1_000_000_000
    qps = unit_safe_qps_from_monthly_requests(monthly)

    print(
        f"1 billion requests/month -> "
        f"{qps:,.2f} average QPS"
    )

    print(
        "Always write the unit next to an intermediate value when doing "
        "estimation manually. Dimensional consistency catches many mistakes."
    )


# ============================================================================
# 40. POWER-OF-TEN SHORTCUTS
# ============================================================================

def demonstrate_power_of_ten_shortcuts() -> None:
    print("\n" + "=" * 78)
    print("40. POWER-OF-TEN SHORTCUTS")
    print("=" * 78)

    examples = {
        "1 million/day": 1_000_000 / SECONDS_PER_DAY,
        "10 million/day": 10_000_000 / SECONDS_PER_DAY,
        "100 million/day": 100_000_000 / SECONDS_PER_DAY,
        "1 billion/day": 1_000_000_000 / SECONDS_PER_DAY,
        "10 billion/day": 10_000_000_000 / SECONDS_PER_DAY,
    }

    for label, qps in examples.items():
        print(f"{label:20s} -> {qps:,.2f} QPS")

    print(
        "Useful mental anchor: one day has about 86,400 seconds, so "
        "1 million events/day is roughly 12 events/s."
    )


# ============================================================================
# 41. ESTIMATION OF API CAPACITY FROM SERVER BENCHMARK
# ============================================================================

@dataclass
class ServerPoolModel:
    target_qps: float
    benchmark_qps_per_server: float
    efficiency_factor: float = 0.60
    redundancy_servers: int = 1

    @property
    def effective_qps_per_server(self) -> float:
        return self.benchmark_qps_per_server * self.efficiency_factor

    @property
    def serving_servers(self) -> int:
        return ceil(
            self.target_qps / self.effective_qps_per_server
        )

    @property
    def total_servers(self) -> int:
        return self.serving_servers + self.redundancy_servers


def demonstrate_server_pool() -> None:
    print("\n" + "=" * 78)
    print("41. SERVER POOL CAPACITY")
    print("=" * 78)

    pool = ServerPoolModel(
        target_qps=100_000,
        benchmark_qps_per_server=25_000,
        efficiency_factor=0.65,
        redundancy_servers=2,
    )

    print(
        f"Effective QPS/server: "
        f"{pool.effective_qps_per_server:,.0f}"
    )
    print(f"Serving servers: {pool.serving_servers}")
    print(f"Total servers: {pool.total_servers}")


# ============================================================================
# 42. LATENCY BUDGET
# ============================================================================

@dataclass
class LatencyBudget:
    client_network_ms: float
    load_balancer_ms: float
    application_ms: float
    cache_ms: float
    database_ms: float
    downstream_ms: float
    serialization_ms: float

    @property
    def total_ms(self) -> float:
        return sum(
            (
                self.client_network_ms,
                self.load_balancer_ms,
                self.application_ms,
                self.cache_ms,
                self.database_ms,
                self.downstream_ms,
                self.serialization_ms,
            )
        )

    def report(self) -> None:
        print(f"Network: {self.client_network_ms:.1f} ms")
        print(f"Load balancer: {self.load_balancer_ms:.1f} ms")
        print(f"Application: {self.application_ms:.1f} ms")
        print(f"Cache: {self.cache_ms:.1f} ms")
        print(f"Database: {self.database_ms:.1f} ms")
        print(f"Downstream: {self.downstream_ms:.1f} ms")
        print(f"Serialization: {self.serialization_ms:.1f} ms")
        print(f"Total: {self.total_ms:.1f} ms")


def demonstrate_latency_budget() -> None:
    print("\n" + "=" * 78)
    print("42. LATENCY BUDGET")
    print("=" * 78)

    budget = LatencyBudget(
        client_network_ms=30,
        load_balancer_ms=2,
        application_ms=15,
        cache_ms=2,
        database_ms=20,
        downstream_ms=25,
        serialization_ms=6,
    )

    budget.report()

    print(
        "Latency budgets are additive along a serial critical path. "
        "Parallel downstream operations change the calculation because "
        "their contribution is closer to the maximum branch latency."
    )


# ============================================================================
# 43. SERIAL VS PARALLEL DOWNSTREAM CALLS
# ============================================================================

def serial_latency_ms(latencies: Sequence[float]) -> float:
    return sum(latencies)


def parallel_latency_ms(latencies: Sequence[float]) -> float:
    if not latencies:
        return 0.0

    return max(latencies)


def demonstrate_serial_parallel_latency() -> None:
    print("\n" + "=" * 78)
    print("43. SERIAL VS PARALLEL LATENCY")
    print("=" * 78)

    downstream = [30, 40, 50]

    print(
        f"Serial calls: "
        f"{serial_latency_ms(downstream):.0f} ms"
    )
    print(
        f"Parallel calls, ignoring overhead: "
        f"{parallel_latency_ms(downstream):.0f} ms"
    )

    print(
        "Parallelism can reduce latency but can increase resource usage, "
        "connection count, downstream load, and failure surface."
    )


# ============================================================================
# 44. PERCENTILES AND TAIL LATENCY
# ============================================================================

def percentile(sorted_values: Sequence[float], p: float) -> float:
    """
    Simple linear-interpolation percentile.

    This is educational rather than a replacement for a production
    observability library's exact percentile implementation.
    """
    if not sorted_values:
        raise ValueError("sorted_values cannot be empty.")

    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100.")

    values = list(sorted_values)

    if any(values[index] > values[index + 1] for index in range(len(values) - 1)):
        raise ValueError("Values must be sorted.")

    if len(values) == 1:
        return float(values[0])

    position = (len(values) - 1) * p / 100
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower

    return values[lower] + (
        values[upper] - values[lower]
    ) * fraction


def demonstrate_percentiles() -> None:
    print("\n" + "=" * 78)
    print("44. PERCENTILES AND TAIL LATENCY")
    print("=" * 78)

    latency_ms = sorted(
        [20, 21, 22, 25, 27, 30, 35, 40, 50, 200]
    )

    for p in (50, 90, 95, 99):
        print(
            f"p{p}: "
            f"{percentile(latency_ms, p):.1f} ms"
        )

    print(
        "Averages can hide tail behavior. System design should account for "
        "p95, p99, or stricter latency objectives when user experience "
        "or downstream timeouts depend on tail latency."
    )


# ============================================================================
# 45. AVAILABILITY OF INDEPENDENT COMPONENTS
# ============================================================================

def serial_availability(availabilities: Iterable[float]) -> float:
    result = 1.0

    for availability in availabilities:
        if not 0 <= availability <= 1:
            raise ValueError("Availability must be between 0 and 1.")
        result *= availability

    return result


def demonstrate_component_availability() -> None:
    print("\n" + "=" * 78)
    print("45. COMPONENT AVAILABILITY")
    print("=" * 78)

    components = [0.999, 0.9995, 0.9999]

    total = serial_availability(components)

    print(
        "Three serial components with availability "
        f"{components} -> {total:.6%}"
    )

    print(
        "Serial dependencies multiply availability because the request "
        "requires every dependency to be available."
    )


# ============================================================================
# 46. PARALLEL REDUNDANCY AVAILABILITY
# ============================================================================

def parallel_availability(
    availability: float,
    replicas: int,
) -> float:
    if not 0 <= availability <= 1:
        raise ValueError("availability must be between 0 and 1.")
    if replicas < 1:
        raise ValueError("replicas must be at least 1.")

    failure_probability = 1 - availability

    return 1 - failure_probability ** replicas


def demonstrate_parallel_availability() -> None:
    print("\n" + "=" * 78)
    print("46. REDUNDANCY AND AVAILABILITY")
    print("=" * 78)

    single = 0.99

    for replicas in (1, 2, 3):
        result = parallel_availability(single, replicas)

        print(
            f"{replicas} independent replicas at 99% availability -> "
            f"{result:.4%}"
        )

    print(
        "The independence assumption is critical. Replicas sharing the same "
        "power, network, software defect, region, or deployment can fail together."
    )


# ============================================================================
# 47. TRAFFIC BY HOUR
# ============================================================================

def hourly_traffic_to_average_qps(
    hourly_requests: Sequence[float],
) -> float:
    if len(hourly_requests) != 24:
        raise ValueError("Exactly 24 hourly values are required.")

    if any(value < 0 for value in hourly_requests):
        raise ValueError("Hourly traffic cannot be negative.")

    return sum(hourly_requests) / SECONDS_PER_DAY


def demonstrate_hourly_traffic() -> None:
    print("\n" + "=" * 78)
    print("47. NON-UNIFORM DAILY TRAFFIC")
    print("=" * 78)

    hourly = [10_000_000] * 24

    # Simulate a daytime peak without pretending traffic is uniform.
    for hour in range(9, 18):
        hourly[hour] = 25_000_000

    average_qps = hourly_traffic_to_average_qps(hourly)
    peak_hourly_qps = max(hourly) / SECONDS_PER_HOUR

    print(f"Average QPS from hourly profile: {average_qps:,.2f}")
    print(f"Peak hourly QPS: {peak_hourly_qps:,.2f}")

    print(
        "The daily average alone does not reveal the shape of traffic. "
        "A system should be sized against the relevant peak interval."
    )


# ============================================================================
# 48. RPS VS QPS TERMINOLOGY
# ============================================================================

class RateTerminology(Enum):
    QPS = "Queries Per Second"
    RPS = "Requests Per Second"
    TPS = "Transactions Per Second"
    EPS = "Events Per Second"


def demonstrate_terminology() -> None:
    print("\n" + "=" * 78)
    print("48. RATE TERMINOLOGY")
    print("=" * 78)

    for item in RateTerminology:
        print(f"{item.name}: {item.value}")

    print(
        "These terms are related but not always interchangeable. "
        "A single HTTP request may trigger many internal database queries "
        "or transactions."
    )


# ============================================================================
# 49. REQUEST COUNT VS DATABASE QUERY COUNT
# ============================================================================

@dataclass
class QueryAmplificationModel:
    api_qps: float
    database_queries_per_api_request: float

    @property
    def database_qps(self) -> float:
        return (
            self.api_qps
            * self.database_queries_per_api_request
        )


def demonstrate_query_amplification() -> None:
    print("\n" + "=" * 78)
    print("49. REQUEST-TO-QUERY AMPLIFICATION")
    print("=" * 78)

    model = QueryAmplificationModel(
        api_qps=15_000,
        database_queries_per_api_request=4,
    )

    print(f"API QPS: {model.api_qps:,}")
    print(f"Database QPS: {model.database_qps:,}")

    print(
        "This is one reason system design should estimate load at each "
        "layer rather than stopping at external API traffic."
    )


# ============================================================================
# 50. N+1 QUERY PROBLEM
# ============================================================================

def n_plus_one_query_count(
    parent_records: int,
    base_query_count: int = 1,
) -> int:
    if parent_records < 0:
        raise ValueError("parent_records cannot be negative.")
    if base_query_count < 0:
        raise ValueError("base_query_count cannot be negative.")

    return base_query_count + parent_records


def demonstrate_n_plus_one_query_problem() -> None:
    print("\n" + "=" * 78)
    print("50. N+1 QUERY PATTERN")
    print("=" * 78)

    parents = 1_000

    queries = n_plus_one_query_count(parents)

    print(f"Parent records: {parents:,}")
    print(f"Database queries: {queries:,}")

    print(
        "A page that fetches one list and then performs one query per item "
        "can amplify database traffic. Batching, joins, prefetching, or "
        "different data-access patterns can reduce the amplification."
    )


# ============================================================================
# 51. ESTIMATING A COMPLETE SIMPLE SYSTEM
# ============================================================================

@dataclass
class SimpleSocialFeedEstimate:
    daily_active_users: int
    feed_requests_per_user_per_day: float
    posts_per_user_per_day: float
    average_post_bytes: int
    peak_multiplier: float
    cache_hit_rate: float
    replication_factor: int
    retention_days: int

    @property
    def feed_requests_per_day(self) -> float:
        return (
            self.daily_active_users
            * self.feed_requests_per_user_per_day
        )

    @property
    def average_feed_qps(self) -> float:
        return requests_per_second(self.feed_requests_per_day)

    @property
    def peak_feed_qps(self) -> float:
        return self.average_feed_qps * self.peak_multiplier

    @property
    def posts_per_day(self) -> float:
        return (
            self.daily_active_users
            * self.posts_per_user_per_day
        )

    @property
    def logical_post_storage(self) -> float:
        return (
            self.posts_per_day
            * self.average_post_bytes
            * self.retention_days
        )

    @property
    def physical_post_storage(self) -> float:
        return (
            self.logical_post_storage
            * self.replication_factor
        )

    @property
    def uncached_feed_qps(self) -> float:
        return self.peak_feed_qps * (
            1 - self.cache_hit_rate
        )

    def report(self) -> None:
        print(f"DAU: {self.daily_active_users:,}")
        print(
            f"Feed requests/day: "
            f"{self.feed_requests_per_day:,.0f}"
        )
        print(
            f"Average feed QPS: "
            f"{self.average_feed_qps:,.2f}"
        )
        print(
            f"Peak feed QPS: "
            f"{self.peak_feed_qps:,.2f}"
        )
        print(
            f"Posts/day: "
            f"{self.posts_per_day:,.0f}"
        )
        print(
            f"Logical post storage: "
            f"{human_bytes(self.logical_post_storage)}"
        )
        print(
            f"Physical post storage: "
            f"{human_bytes(self.physical_post_storage)}"
        )
        print(
            f"Peak feed QPS reaching origin after cache: "
            f"{self.uncached_feed_qps:,.2f}"
        )


def demonstrate_complete_social_feed() -> None:
    print("\n" + "=" * 78)
    print("51. COMPLETE SOCIAL FEED ESTIMATE")
    print("=" * 78)

    estimate = SimpleSocialFeedEstimate(
        daily_active_users=20_000_000,
        feed_requests_per_user_per_day=30,
        posts_per_user_per_day=0.5,
        average_post_bytes=5_000,
        peak_multiplier=5,
        cache_hit_rate=0.80,
        replication_factor=3,
        retention_days=365,
    )

    estimate.report()


# ============================================================================
# 52. COMPLETE URL SHORTENER ESTIMATE
# ============================================================================

@dataclass
class UrlShortenerEstimate:
    daily_active_users: int
    redirects_per_user_per_day: float
    creates_per_user_per_day: float
    average_record_bytes: int
    retention_days: int
    peak_multiplier: float

    @property
    def redirects_per_day(self) -> float:
        return (
            self.daily_active_users
            * self.redirects_per_user_per_day
        )

    @property
    def creates_per_day(self) -> float:
        return (
            self.daily_active_users
            * self.creates_per_user_per_day
        )

    @property
    def average_redirect_qps(self) -> float:
        return requests_per_second(self.redirects_per_day)

    @property
    def peak_redirect_qps(self) -> float:
        return self.average_redirect_qps * self.peak_multiplier

    @property
    def average_create_qps(self) -> float:
        return requests_per_second(self.creates_per_day)

    @property
    def storage(self) -> float:
        return (
            self.creates_per_day
            * self.average_record_bytes
            * self.retention_days
        )


def demonstrate_url_shortener() -> None:
    print("\n" + "=" * 78)
    print("52. COMPLETE URL SHORTENER ESTIMATE")
    print("=" * 78)

    estimate = UrlShortenerEstimate(
        daily_active_users=10_000_000,
        redirects_per_user_per_day=20,
        creates_per_user_per_day=0.2,
        average_record_bytes=1_000,
        retention_days=365 * 5,
        peak_multiplier=8,
    )

    print(f"Redirects/day: {estimate.redirects_per_day:,.0f}")
    print(f"Average redirect QPS: {estimate.average_redirect_qps:,.2f}")
    print(f"Peak redirect QPS: {estimate.peak_redirect_qps:,.2f}")
    print(f"Create QPS: {estimate.average_create_qps:,.2f}")
    print(f"5-year storage: {human_bytes(estimate.storage)}")

    print(
        "This illustrates why read/write separation matters: redirects "
        "can be many orders of magnitude more frequent than URL creation."
    )


# ============================================================================
# 53. FILE UPLOAD SYSTEM
# ============================================================================

@dataclass
class FileUploadEstimate:
    daily_uploads: int
    average_file_bytes: int
    download_multiplier: float
    retention_days: int
    storage_replication: int
    peak_multiplier: float

    @property
    def upload_qps(self) -> float:
        return requests_per_second(self.daily_uploads)

    @property
    def peak_upload_qps(self) -> float:
        return self.upload_qps * self.peak_multiplier

    @property
    def download_qps(self) -> float:
        return (
            self.upload_qps
            * self.download_multiplier
        )

    @property
    def storage(self) -> float:
        return (
            self.daily_uploads
            * self.average_file_bytes
            * self.retention_days
            * self.storage_replication
        )

    @property
    def download_bandwidth(self) -> float:
        return self.download_qps * self.average_file_bytes


def demonstrate_file_upload() -> None:
    print("\n" + "=" * 78)
    print("53. FILE UPLOAD SYSTEM")
    print("=" * 78)

    estimate = FileUploadEstimate(
        daily_uploads=1_000_000,
        average_file_bytes=10_000_000,
        download_multiplier=5,
        retention_days=365,
        storage_replication=3,
        peak_multiplier=4,
    )

    print(f"Upload QPS: {estimate.upload_qps:,.2f}")
    print(f"Peak upload QPS: {estimate.peak_upload_qps:,.2f}")
    print(f"Download QPS: {estimate.download_qps:,.2f}")
    print(f"Storage: {human_bytes(estimate.storage)}")
    print(
        f"Download bandwidth: "
        f"{human_bytes(estimate.download_bandwidth)}/s"
    )

    print(
        "Large media systems are often bandwidth/storage constrained rather "
        "than CPU constrained. Object storage and CDNs can separate these "
        "workloads from transactional databases."
    )


# ============================================================================
# 54. MESSAGE QUEUE THROUGHPUT
# ============================================================================

@dataclass
class MessageQueueEstimate:
    producers: int
    messages_per_producer_per_second: float
    average_message_bytes: int
    consumer_groups: int

    @property
    def ingress_qps(self) -> float:
        return (
            self.producers
            * self.messages_per_producer_per_second
        )

    @property
    def ingress_bandwidth(self) -> float:
        return self.ingress_qps * self.average_message_bytes

    @property
    def logical_consumer_delivery_qps(self) -> float:
        return self.ingress_qps * self.consumer_groups

    @property
    def consumer_bandwidth(self) -> float:
        return (
            self.logical_consumer_delivery_qps
            * self.average_message_bytes
        )


def demonstrate_message_queue() -> None:
    print("\n" + "=" * 78)
    print("54. MESSAGE QUEUE THROUGHPUT")
    print("=" * 78)

    queue = MessageQueueEstimate(
        producers=50_000,
        messages_per_producer_per_second=0.1,
        average_message_bytes=2_000,
        consumer_groups=5,
    )

    print(f"Ingress messages/s: {queue.ingress_qps:,.0f}")
    print(
        f"Ingress bandwidth: "
        f"{human_bytes(queue.ingress_bandwidth)}/s"
    )
    print(
        f"Logical consumer deliveries/s: "
        f"{queue.logical_consumer_delivery_qps:,.0f}"
    )
    print(
        f"Consumer bandwidth: "
        f"{human_bytes(queue.consumer_bandwidth)}/s"
    )


# ============================================================================
# 55. DATABASE STORAGE WITH INDEXES
# ============================================================================

@dataclass
class IndexedStorageEstimate:
    row_count: int
    row_size_bytes: int
    index_count: int
    average_index_bytes_per_row: int
    replication_factor: int

    @property
    def table_storage(self) -> float:
        return self.row_count * self.row_size_bytes

    @property
    def index_storage(self) -> float:
        return (
            self.row_count
            * self.index_count
            * self.average_index_bytes_per_row
        )

    @property
    def logical_storage(self) -> float:
        return self.table_storage + self.index_storage

    @property
    def physical_storage(self) -> float:
        return self.logical_storage * self.replication_factor


def demonstrate_index_storage() -> None:
    print("\n" + "=" * 78)
    print("55. INDEX STORAGE")
    print("=" * 78)

    database = IndexedStorageEstimate(
        row_count=1_000_000_000,
        row_size_bytes=500,
        index_count=4,
        average_index_bytes_per_row=80,
        replication_factor=3,
    )

    print(f"Table: {human_bytes(database.table_storage)}")
    print(f"Indexes: {human_bytes(database.index_storage)}")
    print(
        f"Logical storage: "
        f"{human_bytes(database.logical_storage)}"
    )
    print(
        f"Physical storage: "
        f"{human_bytes(database.physical_storage)}"
    )

    print(
        "Indexes can consume substantial storage and can amplify writes. "
        "Index choice is a trade-off between read efficiency and write/storage cost."
    )


# ============================================================================
# 56. STORAGE HEADROOM
# ============================================================================

def usable_storage_capacity(
    raw_capacity_bytes: float,
    target_utilization: float,
) -> float:
    if raw_capacity_bytes < 0:
        raise ValueError("raw_capacity_bytes cannot be negative.")
    if not 0 < target_utilization <= 1:
        raise ValueError(
            "target_utilization must be in (0, 1]."
        )

    return raw_capacity_bytes * target_utilization


def demonstrate_storage_headroom() -> None:
    print("\n" + "=" * 78)
    print("56. STORAGE HEADROOM")
    print("=" * 78)

    raw = tb_to_bytes(100)
    usable = usable_storage_capacity(raw, 0.70)

    print(f"Raw capacity: {human_bytes(raw)}")
    print(f"70% planning capacity: {human_bytes(usable)}")

    print(
        "Storage should not necessarily be planned to 100% utilization. "
        "Free space may be needed for compaction, replication, temporary files, "
        "rebalancing, recovery, and operational safety."
    )


# ============================================================================
# 57. NETWORK EGRESS
# ============================================================================

def monthly_network_transfer(
    bytes_per_second: float,
    days_per_month: int = 30,
) -> float:
    if bytes_per_second < 0:
        raise ValueError("bytes_per_second cannot be negative.")
    if days_per_month <= 0:
        raise ValueError("days_per_month must be positive.")

    return (
        bytes_per_second
        * SECONDS_PER_DAY
        * days_per_month
    )


def demonstrate_network_egress() -> None:
    print("\n" + "=" * 78)
    print("57. NETWORK EGRESS")
    print("=" * 78)

    throughput = 100 * BYTES_PER_GB

    monthly = monthly_network_transfer(
        throughput,
    )

    print(
        f"100 GB/s sustained for 30 days -> "
        f"{human_bytes(monthly)}"
    )

    print(
        "Bandwidth estimates become enormous quickly at high QPS and large "
        "payload sizes. Egress often becomes a major architecture and cost constraint."
    )


# ============================================================================
# 58. ESTIMATING DATABASE CONNECTIONS
# ============================================================================

def connections_from_qps_and_latency(
    qps: float,
    latency_seconds: float,
    connection_pool_utilization: float = 0.80,
) -> int:
    if qps < 0:
        raise ValueError("qps cannot be negative.")
    if latency_seconds < 0:
        raise ValueError("latency_seconds cannot be negative.")
    if not 0 < connection_pool_utilization <= 1:
        raise ValueError(
            "connection_pool_utilization must be in (0, 1]."
        )

    concurrent = concurrent_requests(
        qps,
        latency_seconds,
    )

    return ceil(
        concurrent / connection_pool_utilization
    )


def demonstrate_database_connections() -> None:
    print("\n" + "=" * 78)
    print("58. DATABASE CONNECTION POOLS")
    print("=" * 78)

    connections = connections_from_qps_and_latency(
        qps=5_000,
        latency_seconds=0.020,
        connection_pool_utilization=0.75,
    )

    print(f"Estimated pool size: {connections}")

    print(
        "A large application fleet can create a connection explosion. "
        "For example, 100 application instances each opening 100 database "
        "connections can produce 10,000 database connections."
    )


# ============================================================================
# 59. CONNECTION EXPLOSION
# ============================================================================

def total_connections(
    application_instances: int,
    connections_per_instance: int,
) -> int:
    if application_instances < 0:
        raise ValueError("application_instances cannot be negative.")
    if connections_per_instance < 0:
        raise ValueError(
            "connections_per_instance cannot be negative."
        )

    return (
        application_instances
        * connections_per_instance
    )


def demonstrate_connection_explosion() -> None:
    print("\n" + "=" * 78)
    print("59. CONNECTION EXPLOSION")
    print("=" * 78)

    connections = total_connections(
        application_instances=200,
        connections_per_instance=50,
    )

    print(f"Application instances: 200")
    print(f"Connections/instance: 50")
    print(f"Total connections: {connections:,}")


# ============================================================================
# 60. ESTIMATING BACKUP STORAGE
# ============================================================================

@dataclass
class BackupStorageModel:
    primary_storage_bytes: float
    full_backups: int
    incremental_daily_bytes: float
    incremental_days: int
    replication_factor: int = 1

    @property
    def full_backup_storage(self) -> float:
        return (
            self.primary_storage_bytes
            * self.full_backups
        )

    @property
    def incremental_storage(self) -> float:
        return (
            self.incremental_daily_bytes
            * self.incremental_days
        )

    @property
    def total_storage(self) -> float:
        return (
            self.full_backup_storage
            + self.incremental_storage
        ) * self.replication_factor


def demonstrate_backup_storage() -> None:
    print("\n" + "=" * 78)
    print("60. BACKUP STORAGE")
    print("=" * 78)

    backups = BackupStorageModel(
        primary_storage_bytes=tb_to_bytes(50),
        full_backups=4,
        incremental_daily_bytes=gb_to_bytes(500),
        incremental_days=30,
        replication_factor=2,
    )

    print(
        f"Full backups: "
        f"{human_bytes(backups.full_backup_storage)}"
    )
    print(
        f"Incrementals: "
        f"{human_bytes(backups.incremental_storage)}"
    )
    print(
        f"Physical backup storage: "
        f"{human_bytes(backups.total_storage)}"
    )


# ============================================================================
# 61. RECOVERY POINT OBJECTIVE AND RECOVERY TIME OBJECTIVE
# ============================================================================

@dataclass
class DisasterRecoveryModel:
    data_generation_bytes_per_second: float
    rpo_seconds: float
    backup_restore_bandwidth_bytes_per_second: float
    data_to_restore_bytes: float

    @property
    def maximum_unprotected_data(self) -> float:
        return (
            self.data_generation_bytes_per_second
            * self.rpo_seconds
        )

    @property
    def restore_time_seconds(self) -> float:
        if self.backup_restore_bandwidth_bytes_per_second <= 0:
            raise ValueError("Restore bandwidth must be positive.")

        return (
            self.data_to_restore_bytes
            / self.backup_restore_bandwidth_bytes_per_second
        )


def demonstrate_rpo_rto() -> None:
    print("\n" + "=" * 78)
    print("61. RPO AND RTO")
    print("=" * 78)

    dr = DisasterRecoveryModel(
        data_generation_bytes_per_second=10_000_000,
        rpo_seconds=60,
        backup_restore_bandwidth_bytes_per_second=500_000_000,
        data_to_restore_bytes=tb_to_bytes(20),
    )

    print(
        f"Maximum modeled data loss for 60-second RPO: "
        f"{human_bytes(dr.maximum_unprotected_data)}"
    )
    print(
        f"20 TB restore time at 500 MB/s: "
        f"{human_seconds(dr.restore_time_seconds)}"
    )

    print(
        "RPO measures tolerated data-loss interval. RTO measures tolerated "
        "recovery duration. They are distinct constraints."
    )


# ============================================================================
# 62. ESTIMATING RETRIES
# ============================================================================

@dataclass
class RetryAmplificationModel:
    incoming_qps: float
    retry_fraction: float
    average_attempts_for_retried_request: float

    @property
    def retrying_requests_qps(self) -> float:
        return self.incoming_qps * self.retry_fraction

    @property
    def extra_qps(self) -> float:
        return self.retrying_requests_qps * (
            self.average_attempts_for_retried_request - 1
        )

    @property
    def total_attempt_qps(self) -> float:
        return self.incoming_qps + self.extra_qps


def demonstrate_retry_amplification() -> None:
    print("\n" + "=" * 78)
    print("62. RETRY AMPLIFICATION")
    print("=" * 78)

    retries = RetryAmplificationModel(
        incoming_qps=50_000,
        retry_fraction=0.10,
        average_attempts_for_retried_request=2.5,
    )

    print(f"Original QPS: {retries.incoming_qps:,}")
    print(f"Retrying request QPS: {retries.retrying_requests_qps:,.0f}")
    print(f"Extra QPS from retries: {retries.extra_qps:,.0f}")
    print(f"Total attempt QPS: {retries.total_attempt_qps:,.0f}")

    print(
        "Retries can create positive feedback during overload. "
        "Backoff, jitter, deadlines, retry budgets, and idempotency "
        "are important safeguards."
    )


# ============================================================================
# 63. RETRY STORM WITH MULTIPLE LAYERS
# ============================================================================

def layered_retry_amplification(
    base_qps: float,
    retry_multipliers: Sequence[float],
) -> float:
    result = base_qps

    for multiplier in retry_multipliers:
        if multiplier < 1:
            raise ValueError("Retry multiplier must be >= 1.")
        result *= multiplier

    return result


def demonstrate_layered_retries() -> None:
    print("\n" + "=" * 78)
    print("63. LAYERED RETRY AMPLIFICATION")
    print("=" * 78)

    base = 10_000

    amplified = layered_retry_amplification(
        base,
        [1.2, 1.3, 1.1],
    )

    print(f"Base QPS: {base:,}")
    print(f"Amplified attempts: {amplified:,.0f}")

    print(
        "Retries at several independent layers can multiply. "
        "A service may receive much more load than the original user request rate."
    )


# ============================================================================
# 64. ASYNCHRONOUS PROCESSING
# ============================================================================

@dataclass
class AsyncProcessingModel:
    incoming_events_per_second: float
    processing_time_seconds: float
    workers: int

    @property
    def worker_capacity(self) -> float:
        if self.processing_time_seconds <= 0:
            raise ValueError("processing_time_seconds must be positive.")

        return self.workers / self.processing_time_seconds

    @property
    def utilization(self) -> float:
        return (
            self.incoming_events_per_second
            / self.worker_capacity
        )


def demonstrate_async_processing() -> None:
    print("\n" + "=" * 78)
    print("64. ASYNCHRONOUS PROCESSING")
    print("=" * 78)

    model = AsyncProcessingModel(
        incoming_events_per_second=2_000,
        processing_time_seconds=0.20,
        workers=500,
    )

    print(f"Worker capacity: {model.worker_capacity:,.0f} events/s")
    print(f"Estimated utilization: {model.utilization:.2%}")

    print(
        "Asynchronous queues decouple producers and consumers, allowing "
        "temporary bursts to be absorbed by backlog. They do not remove "
        "the requirement for long-term processing capacity."
    )


# ============================================================================
# 65. BATCHING
# ============================================================================

@dataclass
class BatchProcessingModel:
    records_per_second: float
    batch_size: int

    @property
    def batches_per_second(self) -> float:
        return self.records_per_second / self.batch_size


def demonstrate_batching() -> None:
    print("\n" + "=" * 78)
    print("65. BATCHING")
    print("=" * 78)

    model = BatchProcessingModel(
        records_per_second=100_000,
        batch_size=100,
    )

    print(f"Record rate: {model.records_per_second:,}/s")
    print(f"Batch size: {model.batch_size}")
    print(f"Batch operations/s: {model.batches_per_second:,.0f}")

    print(
        "Batching can reduce per-operation overhead, network round trips, "
        "and transaction costs, but can increase latency and make failure handling "
        "more complex."
    )


# ============================================================================
# 66. SHARDING
# ============================================================================

@dataclass
class ShardingModel:
    total_qps: float
    total_storage_bytes: float
    shards: int

    @property
    def qps_per_shard(self) -> float:
        return self.total_qps / self.shards

    @property
    def storage_per_shard(self) -> float:
        return self.total_storage_bytes / self.shards


def demonstrate_sharding() -> None:
    print("\n" + "=" * 78)
    print("66. SHARDING")
    print("=" * 78)

    model = ShardingModel(
        total_qps=100_000,
        total_storage_bytes=tb_to_bytes(100),
        shards=20,
    )

    print(f"QPS/shard: {model.qps_per_shard:,.0f}")
    print(
        f"Storage/shard: "
        f"{human_bytes(model.storage_per_shard)}"
    )

    print(
        "Sharding distributes load and storage, but introduces routing, "
        "rebalancing, hot-key, cross-shard query, transaction, and operational complexity."
    )


# ============================================================================
# 67. HOT PARTITIONS
# ============================================================================

@dataclass
class HotPartitionModel:
    total_qps: float
    partitions: int
    hot_partition_fraction: float
    hot_partition_load_fraction: float

    @property
    def average_qps_per_partition(self) -> float:
        return self.total_qps / self.partitions

    @property
    def hot_partition_qps(self) -> float:
        return self.total_qps * self.hot_partition_load_fraction


def demonstrate_hot_partitions() -> None:
    print("\n" + "=" * 78)
    print("67. HOT PARTITIONS")
    print("=" * 78)

    model = HotPartitionModel(
        total_qps=100_000,
        partitions=100,
        hot_partition_fraction=0.01,
        hot_partition_load_fraction=0.25,
    )

    print(
        f"Average QPS/partition: "
        f"{model.average_qps_per_partition:,.0f}"
    )
    print(
        f"Hot partition QPS: "
        f"{model.hot_partition_qps:,.0f}"
    )

    print(
        "Uniform division is only valid when traffic is reasonably uniform. "
        "A small number of popular keys can overload individual partitions."
    )


# ============================================================================
# 68. CONSISTENCY AND CROSS-REGION TRAFFIC
# ============================================================================

@dataclass
class CrossRegionReplicationModel:
    write_qps: float
    record_bytes: int
    regions: int

    @property
    def cross_region_replication_stream_qps(self) -> float:
        return self.write_qps * max(0, self.regions - 1)

    @property
    def cross_region_bandwidth(self) -> float:
        return (
            self.cross_region_replication_stream_qps
            * self.record_bytes
        )


def demonstrate_cross_region_replication() -> None:
    print("\n" + "=" * 78)
    print("68. CROSS-REGION REPLICATION")
    print("=" * 78)

    model = CrossRegionReplicationModel(
        write_qps=5_000,
        record_bytes=10_000,
        regions=3,
    )

    print(
        f"Replication streams: "
        f"{model.cross_region_replication_stream_qps:,.0f} writes/s"
    )
    print(
        f"Cross-region bandwidth: "
        f"{human_bytes(model.cross_region_bandwidth)}/s"
    )

    print(
        "Multi-region writes can add significant network traffic. "
        "The actual protocol may use logs, compression, batching, "
        "quorums, or asynchronous replication."
    )


# ============================================================================
# 69. EVENT RETENTION IN A QUEUE
# ============================================================================

def queue_storage(
    events_per_second: float,
    event_bytes: int,
    retention_seconds: float,
    replication_factor: int = 1,
) -> float:
    return (
        events_per_second
        * event_bytes
        * retention_seconds
        * replication_factor
    )


def demonstrate_queue_storage() -> None:
    print("\n" + "=" * 78)
    print("69. QUEUE STORAGE")
    print("=" * 78)

    storage = queue_storage(
        events_per_second=50_000,
        event_bytes=2_000,
        retention_seconds=86_400,
        replication_factor=3,
    )

    print(
        f"One day of physical queue storage: "
        f"{human_bytes(storage)}"
    )


# ============================================================================
# 70. ESTIMATION CHECKLIST AS CODE
# ============================================================================

@dataclass
class EstimationChecklist:
    user_population: str
    active_population: str
    action_frequency: str
    request_rate: str
    peak_factor: str
    read_write_ratio: str
    payload_size: str
    storage_retention: str
    replication: str
    bandwidth: str
    headroom: str
    failure_model: str

    def print_checklist(self) -> None:
        fields = [
            ("User population", self.user_population),
            ("Active population", self.active_population),
            ("Action frequency", self.action_frequency),
            ("Request rate", self.request_rate),
            ("Peak factor", self.peak_factor),
            ("Read/write ratio", self.read_write_ratio),
            ("Payload size", self.payload_size),
            ("Storage retention", self.storage_retention),
            ("Replication", self.replication),
            ("Bandwidth", self.bandwidth),
            ("Headroom", self.headroom),
            ("Failure model", self.failure_model),
        ]

        for name, value in fields:
            print(f"- {name}: {value}")


def demonstrate_checklist() -> None:
    print("\n" + "=" * 78)
    print("70. ESTIMATION CHECKLIST")
    print("=" * 78)

    checklist = EstimationChecklist(
        user_population="Who exists?",
        active_population="Who is active during the period?",
        action_frequency="How many actions/user/day?",
        request_rate="How does that become QPS?",
        peak_factor="How much larger is peak traffic?",
        read_write_ratio="How many reads versus writes?",
        payload_size="How large are requests/responses/records?",
        storage_retention="How long is data retained?",
        replication="How many physical copies exist?",
        bandwidth="How many bytes/sec cross each network boundary?",
        headroom="How much spare capacity is required?",
        failure_model="What failures must the system survive?",
    )

    checklist.print_checklist()


# ============================================================================
# 71. COMMON ESTIMATION MISTAKES
# ============================================================================

def demonstrate_common_mistakes() -> None:
    print("\n" + "=" * 78)
    print("71. COMMON ESTIMATION MISTAKES")
    print("=" * 78)

    mistakes = [
        (
            "Using registered users as concurrent users",
            "Estimate active users and activity frequency instead."
        ),
        (
            "Confusing bits with bytes",
            "Divide bits/s by 8 to obtain bytes/s."
        ),
        (
            "Using daily average as peak capacity",
            "Apply an explicit peak factor or model traffic by time interval."
        ),
        (
            "Ignoring replication",
            "Separate logical data from physical storage."
        ),
        (
            "Ignoring metadata and indexes",
            "Include storage-engine overhead where it materially matters."
        ),
        (
            "Assuming every request is one database operation",
            "Trace amplification through downstream dependencies."
        ),
        (
            "Assuming perfect cache hit rate",
            "Estimate realistic hit rates and cache-miss behavior."
        ),
        (
            "Sizing exactly to the estimate",
            "Add explicit headroom and account for failures."
        ),
        (
            "Treating benchmark QPS as universal",
            "Benchmark the actual workload and operating conditions."
        ),
        (
            "Ignoring tail latency",
            "Use percentile-based latency objectives."
        ),
        (
            "Ignoring retries",
            "Estimate attempt rate rather than only original request rate."
        ),
        (
            "Ignoring hot keys",
            "Check partition-level rather than only cluster-level load."
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\nMistake: {mistake}")
        print(f"Correction: {correction}")


# ============================================================================
# 72. SANITY CHECKS
# ============================================================================

def sanity_check_nonnegative(
    name: str,
    value: float,
) -> None:
    if value < 0:
        raise ValueError(
            f"Sanity check failed: {name} is negative."
        )


def sanity_check_order(
    lower_name: str,
    lower: float,
    upper_name: str,
    upper: float,
) -> None:
    if lower > upper:
        raise ValueError(
            f"Sanity check failed: {lower_name} > {upper_name}."
        )


def demonstrate_sanity_checks() -> None:
    print("\n" + "=" * 78)
    print("72. SANITY CHECKS")
    print("=" * 78)

    values = {
        "daily requests": 100_000_000,
        "average QPS": 100_000_000 / 86_400,
        "peak QPS": 20_000,
        "storage": tb_to_bytes(10),
    }

    for name, value in values.items():
        sanity_check_nonnegative(name, value)

    sanity_check_order(
        "average QPS",
        values["average QPS"],
        "peak QPS",
        values["peak QPS"],
    )

    print("All basic sanity checks passed.")

    print(
        "Sanity checks should ask whether the magnitude is plausible, "
        "whether units are correct, and whether relationships such as "
        "peak >= average are preserved."
    )


# ============================================================================
# 73. ESTIMATION WITH SIGNIFICANT FIGURES
# ============================================================================

def round_estimate(value: float) -> float:
    """
    Round a large estimate to approximately two significant digits.

    Back-of-the-envelope calculations should not communicate more precision
    than the assumptions justify.
    """
    if value == 0:
        return 0.0

    from math import log10, floor

    magnitude = floor(log10(abs(value)))
    decimals = max(0, 1 - magnitude)

    return round(value, decimals)


def demonstrate_significant_figures() -> None:
    print("\n" + "=" * 78)
    print("73. SIGNIFICANT FIGURES")
    print("=" * 78)

    precise = 123_456.789
    approximate = round_estimate(precise)

    print(f"Raw calculation: {precise}")
    print(f"Communicated estimate: {approximate}")

    print(
        "If user activity is only known approximately, reporting "
        "123,456.789 QPS creates false precision."
    )


# ============================================================================
# 74. ESTIMATION INTERVIEW METHOD
# ============================================================================

def estimate_system(
    users: int,
    active_fraction: float,
    actions_per_active_user_per_day: float,
    peak_multiplier: float,
    write_fraction: float,
    record_bytes: int,
    retention_days: int,
    replication_factor: int,
    response_bytes: int,
) -> dict[str, float]:
    """
    Reusable first-order system estimation.

    It returns quantities at several layers so an architecture can be
    reasoned about systematically.
    """
    active_users = users * active_fraction
    actions_per_day = (
        active_users
        * actions_per_active_user_per_day
    )

    average_qps = requests_per_second(actions_per_day)
    peak_qps = average_qps * peak_multiplier

    peak_read_qps = peak_qps * (1 - write_fraction)
    peak_write_qps = peak_qps * write_fraction

    logical_storage = storage_from_write_qps(
        peak_write_qps,
        record_bytes,
        retention_days,
    )

    physical_storage = logical_storage * replication_factor

    network_bytes_per_second = (
        peak_qps
        * response_bytes
    )

    return {
        "active_users": active_users,
        "actions_per_day": actions_per_day,
        "average_qps": average_qps,
        "peak_qps": peak_qps,
        "peak_read_qps": peak_read_qps,
        "peak_write_qps": peak_write_qps,
        "logical_storage_bytes": logical_storage,
        "physical_storage_bytes": physical_storage,
        "response_bandwidth_bytes_per_second": network_bytes_per_second,
        "response_bandwidth_bits_per_second": (
            network_bytes_per_second * BITS_PER_BYTE
        ),
    }


def demonstrate_reusable_estimator() -> None:
    print("\n" + "=" * 78)
    print("74. REUSABLE SYSTEM ESTIMATOR")
    print("=" * 78)

    result = estimate_system(
        users=100_000_000,
        active_fraction=0.10,
        actions_per_active_user_per_day=20,
        peak_multiplier=5,
        write_fraction=0.05,
        record_bytes=2_000,
        retention_days=365,
        replication_factor=3,
        response_bytes=20_000,
    )

    print(f"Active users: {result['active_users']:,.0f}")
    print(f"Actions/day: {result['actions_per_day']:,.0f}")
    print(f"Average QPS: {result['average_qps']:,.2f}")
    print(f"Peak QPS: {result['peak_qps']:,.2f}")
    print(f"Peak reads: {result['peak_read_qps']:,.2f} QPS")
    print(f"Peak writes: {result['peak_write_qps']:,.2f} QPS")
    print(
        f"Physical retained storage: "
        f"{human_bytes(result['physical_storage_bytes'])}"
    )
    print(
        f"Peak response bandwidth: "
        f"{human_bits_per_second(result['response_bandwidth_bits_per_second'])}"
    )


# ============================================================================
# 75. PRODUCTION CAPACITY MODEL
# ============================================================================

@dataclass
class ProductionCapacityModel:
    demand_qps: float
    per_instance_qps: float
    target_utilization: float
    availability_redundancy_instances: int
    growth_multiplier: float

    @property
    def future_demand(self) -> float:
        return self.demand_qps * self.growth_multiplier

    @property
    def usable_qps_per_instance(self) -> float:
        return (
            self.per_instance_qps
            * self.target_utilization
        )

    @property
    def instances_for_future_demand(self) -> int:
        return ceil(
            self.future_demand
            / self.usable_qps_per_instance
        )

    @property
    def production_instances(self) -> int:
        return (
            self.instances_for_future_demand
            + self.availability_redundancy_instances
        )

    def report(self) -> None:
        print(f"Current demand: {self.demand_qps:,.0f} QPS")
        print(f"Growth multiplier: {self.growth_multiplier:.2f}x")
        print(f"Future demand: {self.future_demand:,.0f} QPS")
        print(
            f"Usable capacity/instance: "
            f"{self.usable_qps_per_instance:,.0f} QPS"
        )
        print(
            f"Instances for future demand: "
            f"{self.instances_for_future_demand}"
        )
        print(
            f"Production instances with redundancy: "
            f"{self.production_instances}"
        )


def demonstrate_production_capacity() -> None:
    print("\n" + "=" * 78)
    print("75. PRODUCTION CAPACITY MODEL")
    print("=" * 78)

    model = ProductionCapacityModel(
        demand_qps=50_000,
        per_instance_qps=10_000,
        target_utilization=0.65,
        availability_redundancy_instances=2,
        growth_multiplier=2,
    )

    model.report()


# ============================================================================
# 76. COMPARING TWO ARCHITECTURES QUANTITATIVELY
# ============================================================================

@dataclass
class ArchitectureOption:
    name: str
    application_instances: int
    database_nodes: int
    cache_hit_rate: float
    storage_bytes: float
    network_bytes_per_second: float

    @property
    def backend_qps_multiplier(self) -> float:
        return 1 - self.cache_hit_rate


def compare_architectures(
    options: Sequence[ArchitectureOption],
) -> None:
    print("\n" + "=" * 78)
    print("76. QUANTITATIVE ARCHITECTURE COMPARISON")
    print("=" * 78)

    for option in options:
        print(f"\n{option.name}")
        print(f"  Application instances: {option.application_instances}")
        print(f"  Database nodes: {option.database_nodes}")
        print(f"  Cache hit rate: {option.cache_hit_rate:.0%}")
        print(f"  Storage: {human_bytes(option.storage_bytes)}")
        print(
            f"  Network: "
            f"{human_bytes(option.network_bytes_per_second)}/s"
        )
        print(
            f"  Backend traffic fraction: "
            f"{option.backend_qps_multiplier:.2%}"
        )


def demonstrate_architecture_comparison() -> None:
    options = [
        ArchitectureOption(
            name="Architecture A",
            application_instances=20,
            database_nodes=5,
            cache_hit_rate=0.80,
            storage_bytes=tb_to_bytes(30),
            network_bytes_per_second=gb_to_bytes(1),
        ),
        ArchitectureOption(
            name="Architecture B",
            application_instances=30,
            database_nodes=3,
            cache_hit_rate=0.95,
            storage_bytes=tb_to_bytes(40),
            network_bytes_per_second=gb_to_bytes(1.5),
        ),
    ]

    compare_architectures(options)


# ============================================================================
# 77. ESTIMATION TESTS
# ============================================================================

def test_unit_conversions() -> None:
    assert bytes_to_mb(1_000_000) == 1
    assert bits_per_second_to_bytes_per_second(80) == 10
    assert bytes_per_second_to_bits_per_second(10) == 80


def test_qps_conversion() -> None:
    assert abs(
        requests_per_second(86_400) - 1
    ) < 1e-12


def test_peak_qps() -> None:
    assert peak_qps_from_average(100, 5) == 500


def test_read_write_split() -> None:
    assert read_qps_from_total(1_000, 0.10) == 900
    assert write_qps_from_total(1_000, 0.10) == 100


def test_storage_growth() -> None:
    assert storage_growth_per_day(1_000, 100) == 100_000


def test_bandwidth() -> None:
    assert bandwidth_bytes_per_second(1_000, 1_000) == 1_000_000


def test_littles_law() -> None:
    assert concurrent_requests(1_000, 0.1) == 100


def test_queue_drain() -> None:
    assert queue_drain_time(1_000, 100, 200) == 10


def test_parallel_availability() -> None:
    result = parallel_availability(0.99, 2)
    assert abs(result - 0.9999) < 1e-12


def test_percentile() -> None:
    values = [1, 2, 3, 4, 5]
    assert percentile(values, 50) == 3


def test_storage_model() -> None:
    model = StorageModel(
        records_per_day=100,
        average_record_bytes=10,
        retention_days=10,
        replication_factor=2,
    )

    assert model.raw_daily_storage == 1_000
    assert model.physical_retained_storage == 20_000


def test_cache_model() -> None:
    model = CacheModel(
        total_qps=1_000,
        cache_hit_rate=0.90,
    )

    assert model.backend_qps == 100


def run_tests() -> None:
    print("\n" + "=" * 78)
    print("77. BUILT-IN TESTS")
    print("=" * 78)

    tests = [
        test_unit_conversions,
        test_qps_conversion,
        test_peak_qps,
        test_read_write_split,
        test_storage_growth,
        test_bandwidth,
        test_littles_law,
        test_queue_drain,
        test_parallel_availability,
        test_percentile,
        test_storage_model,
        test_cache_model,
    ]

    passed = 0

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
        passed += 1

    print(f"\n{passed}/{len(tests)} tests passed.")


# ============================================================================
# 78. EDGE CASES
# ============================================================================

def demonstrate_edge_cases() -> None:
    print("\n" + "=" * 78)
    print("78. EDGE CASES AND EXCEPTIONS")
    print("=" * 78)

    cases = [
        ("Zero requests", lambda: requests_per_second(0)),
        ("Zero storage writes", lambda: storage_growth_per_day(0, 100)),
        ("100% cache hit", lambda: CacheModel(10_000, 1.0).backend_qps),
        ("0% cache hit", lambda: CacheModel(10_000, 0.0).backend_qps),
        ("Zero latency", lambda: concurrent_requests(10_000, 0)),
    ]

    for name, operation in cases:
        try:
            result = operation()
            print(f"{name}: {result}")
        except ValueError as error:
            print(f"{name}: rejected safely -> {error}")

    invalid_cases = [
        ("Negative QPS", lambda: requests_per_second(-1)),
        ("Cache rate > 100%", lambda: CacheModel(1_000, 1.1)),
        ("Negative retention", lambda: StorageModel(1, 1, -1)),
        ("Queue cannot drain", lambda: queue_drain_time(1_000, 200, 100)),
    ]

    print("\nInvalid cases:")

    for name, operation in invalid_cases:
        try:
            operation()
            print(f"{name}: unexpected success")
        except ValueError as error:
            print(f"{name}: correctly rejected -> {error}")


# ============================================================================
# 79. A COMPLETE END-TO-END ESTIMATION WORKFLOW
# ============================================================================

def end_to_end_estimation() -> None:
    print("\n" + "=" * 78)
    print("79. END-TO-END ESTIMATION WORKFLOW")
    print("=" * 78)

    # Step 1: Start with a population.
    total_users = 200_000_000

    # Step 2: Estimate the active fraction.
    dau_fraction = 0.10
    daily_active_users = total_users * dau_fraction

    # Step 3: Estimate user activity.
    actions_per_user = 25
    daily_actions = daily_active_users * actions_per_user

    # Step 4: Convert daily traffic to average QPS.
    average_qps = requests_per_second(daily_actions)

    # Step 5: Account for peak behavior.
    peak_multiplier = 6
    peak_qps = average_qps * peak_multiplier

    # Step 6: Separate reads and writes.
    write_fraction = 0.05
    peak_write_qps = peak_qps * write_fraction
    peak_read_qps = peak_qps * (1 - write_fraction)

    # Step 7: Estimate downstream amplification.
    database_queries_per_request = 3
    peak_database_qps = peak_qps * database_queries_per_request

    # Step 8: Estimate cache effect.
    cache_hit_rate = 0.90
    database_qps_after_cache = (
        peak_database_qps
        * (1 - cache_hit_rate)
    )

    # Step 9: Estimate storage.
    record_bytes = 2_000
    retention_days = 365
    replication_factor = 3

    logical_storage = storage_from_write_qps(
        peak_write_qps,
        record_bytes,
        retention_days,
    )

    physical_storage = (
        logical_storage
        * replication_factor
    )

    # Step 10: Estimate network bandwidth.
    response_bytes = 30_000
    response_bandwidth = (
        peak_qps
        * response_bytes
    )

    # Step 11: Add capacity headroom.
    headroom = 0.25
    planned_peak_qps = peak_qps * (1 + headroom)

    print(f"Total registered users: {total_users:,}")
    print(f"Daily active users: {daily_active_users:,.0f}")
    print(f"Daily actions: {daily_actions:,.0f}")
    print(f"Average QPS: {average_qps:,.2f}")
    print(f"Peak QPS: {peak_qps:,.2f}")
    print(f"Peak read QPS: {peak_read_qps:,.2f}")
    print(f"Peak write QPS: {peak_write_qps:,.2f}")
    print(f"Peak database QPS before cache: {peak_database_qps:,.2f}")
    print(
        f"Database QPS after cache: "
        f"{database_qps_after_cache:,.2f}"
    )
    print(
        f"Logical storage: "
        f"{human_bytes(logical_storage)}"
    )
    print(
        f"Physical replicated storage: "
        f"{human_bytes(physical_storage)}"
    )
    print(
        f"Peak response bandwidth: "
        f"{human_bytes(response_bandwidth)}/s"
    )
    print(
        f"Planned peak QPS with 25% headroom: "
        f"{planned_peak_qps:,.2f}"
    )

    print(
        "\nThe important skill is not memorizing a particular result. "
        "The skill is tracing assumptions through the system and keeping "
        "the units consistent at every step."
    )


# ============================================================================
# 80. ADVANCED: CAPACITY AT EACH ARCHITECTURAL LAYER
# ============================================================================

@dataclass
class LayerCapacity:
    name: str
    incoming_qps: float
    amplification: float
    capacity_per_instance: float
    target_utilization: float = 0.70

    @property
    def effective_qps(self) -> float:
        return self.incoming_qps * self.amplification

    @property
    def usable_capacity_per_instance(self) -> float:
        return (
            self.capacity_per_instance
            * self.target_utilization
        )

    @property
    def instances_required(self) -> int:
        return ceil(
            self.effective_qps
            / self.usable_capacity_per_instance
        )

    def report(self) -> None:
        print(f"{self.name}")
        print(f"  Incoming: {self.incoming_qps:,.0f} QPS")
        print(f"  Amplification: {self.amplification:.2f}x")
        print(f"  Effective: {self.effective_qps:,.0f} QPS")
        print(
            f"  Instances: "
            f"{self.instances_required}"
        )


def demonstrate_layer_capacity() -> None:
    print("\n" + "=" * 78)
    print("80. CAPACITY AT EACH ARCHITECTURAL LAYER")
    print("=" * 78)

    layers = [
        LayerCapacity(
            name="API servers",
            incoming_qps=20_000,
            amplification=1,
            capacity_per_instance=5_000,
        ),
        LayerCapacity(
            name="Database queries",
            incoming_qps=20_000,
            amplification=4,
            capacity_per_instance=10_000,
        ),
        LayerCapacity(
            name="Event publishing",
            incoming_qps=20_000,
            amplification=0.2,
            capacity_per_instance=20_000,
        ),
    ]

    for layer in layers:
        layer.report()


# ============================================================================
# 81. ADVANCED: ERROR PROPAGATION
# ============================================================================

def relative_error(
    estimated: float,
    actual: float,
) -> float:
    if actual == 0:
        if estimated == 0:
            return 0.0
        return float("inf")

    return abs(estimated - actual) / abs(actual)


def demonstrate_error_propagation() -> None:
    print("\n" + "=" * 78)
    print("81. ESTIMATION ERROR")
    print("=" * 78)

    estimated_users = 10_000_000
    actual_users = 12_000_000

    estimated_record_size = 2_000
    actual_record_size = 3_000

    estimated_storage = (
        estimated_users
        * estimated_record_size
    )

    actual_storage = (
        actual_users
        * actual_record_size
    )

    user_error = relative_error(
        estimated_users,
        actual_users,
    )

    storage_error = relative_error(
        estimated_storage,
        actual_storage,
    )

    print(f"User estimate relative error: {user_error:.2%}")
    print(f"Storage estimate relative error: {storage_error:.2%}")

    print(
        "Independent multiplicative assumptions can compound. "
        "A 20% population error and 33% payload-size error can produce "
        "a substantially larger storage error."
    )


# ============================================================================
# 82. ADVANCED: COST-LIKE CAPACITY MODEL
# ============================================================================

@dataclass
class ResourceCostModel:
    application_instances: int
    monthly_cost_per_application_instance: float
    database_nodes: int
    monthly_cost_per_database_node: float
    storage_tb: float
    monthly_storage_cost_per_tb: float
    monthly_egress_gb: float
    egress_cost_per_gb: float

    @property
    def application_cost(self) -> float:
        return (
            self.application_instances
            * self.monthly_cost_per_application_instance
        )

    @property
    def database_cost(self) -> float:
        return (
            self.database_nodes
            * self.monthly_cost_per_database_node
        )

    @property
    def storage_cost(self) -> float:
        return (
            self.storage_tb
            * self.monthly_storage_cost_per_tb
        )

    @property
    def egress_cost(self) -> float:
        return (
            self.monthly_egress_gb
            * self.egress_cost_per_gb
        )

    @property
    def total_monthly_cost(self) -> float:
        return (
            self.application_cost
            + self.database_cost
            + self.storage_cost
            + self.egress_cost
        )


def demonstrate_resource_cost_model() -> None:
    print("\n" + "=" * 78)
    print("82. RESOURCE AND COST-LIKE CAPACITY MODEL")
    print("=" * 78)

    model = ResourceCostModel(
        application_instances=40,
        monthly_cost_per_application_instance=100,
        database_nodes=6,
        monthly_cost_per_database_node=1_000,
        storage_tb=200,
        monthly_storage_cost_per_tb=20,
        monthly_egress_gb=100_000,
        egress_cost_per_gb=0.05,
    )

    print(f"Application: ${model.application_cost:,.2f}/month")
    print(f"Database: ${model.database_cost:,.2f}/month")
    print(f"Storage: ${model.storage_cost:,.2f}/month")
    print(f"Egress: ${model.egress_cost:,.2f}/month")
    print(f"Total: ${model.total_monthly_cost:,.2f}/month")

    print(
        "Real cloud pricing varies by provider, region, commitment, "
        "instance type, storage class, transfer direction, and utilization. "
        "The model demonstrates how estimated quantities feed economic decisions."
    )


# ============================================================================
# 83. ADVANCED: ESTIMATION OF SEARCH INDEX STORAGE
# ============================================================================

@dataclass
class SearchIndexEstimate:
    documents: int
    source_bytes_per_document: int
    index_multiplier: float
    replicas: int

    @property
    def source_storage(self) -> float:
        return self.documents * self.source_bytes_per_document

    @property
    def primary_index_storage(self) -> float:
        return self.source_storage * self.index_multiplier

    @property
    def physical_index_storage(self) -> float:
        return (
            self.primary_index_storage
            * self.replicas
        )


def demonstrate_search_index() -> None:
    print("\n" + "=" * 78)
    print("83. SEARCH INDEX STORAGE")
    print("=" * 78)

    model = SearchIndexEstimate(
        documents=2_000_000_000,
        source_bytes_per_document=1_000,
        index_multiplier=1.8,
        replicas=2,
    )

    print(
        f"Source data: "
        f"{human_bytes(model.source_storage)}"
    )
    print(
        f"Primary index: "
        f"{human_bytes(model.primary_index_storage)}"
    )
    print(
        f"Physical index storage: "
        f"{human_bytes(model.physical_index_storage)}"
    )

    print(
        "An index can occupy more physical space than the original source "
        "records because it stores structures optimized for retrieval."
    )


# ============================================================================
# 84. ADVANCED: ESTIMATING UNIQUE REQUEST KEYS
# ============================================================================

def cache_memory_for_keys(
    unique_keys: int,
    key_bytes: int,
    value_bytes: int,
    overhead_multiplier: float = 1.20,
) -> float:
    return (
        unique_keys
        * (key_bytes + value_bytes)
        * overhead_multiplier
    )


def demonstrate_cache_key_memory() -> None:
    print("\n" + "=" * 78)
    print("84. CACHE KEY/VALUE MEMORY")
    print("=" * 78)

    memory = cache_memory_for_keys(
        unique_keys=20_000_000,
        key_bytes=100,
        value_bytes=2_000,
        overhead_multiplier=1.25,
    )

    print(
        f"Estimated cache memory: "
        f"{human_bytes(memory)}"
    )


# ============================================================================
# 85. ADVANCED: ESTIMATING RATE LIMITER STORAGE
# ============================================================================

@dataclass
class RateLimiterEstimate:
    active_keys: int
    bytes_per_key: int
    replicas: int

    @property
    def memory_bytes(self) -> float:
        return (
            self.active_keys
            * self.bytes_per_key
            * self.replicas
        )


def demonstrate_rate_limiter() -> None:
    print("\n" + "=" * 78)
    print("85. RATE LIMITER STATE")
    print("=" * 78)

    model = RateLimiterEstimate(
        active_keys=50_000_000,
        bytes_per_key=200,
        replicas=3,
    )

    print(
        f"Physical state: "
        f"{human_bytes(model.memory_bytes)}"
    )

    print(
        "A distributed rate limiter is constrained by key cardinality, "
        "state size, expiration behavior, replication, and update rate."
    )


# ============================================================================
# 86. ADVANCED: RATE LIMITING CAPACITY
# ============================================================================

def required_rate_limiter_updates(
    incoming_qps: float,
    decisions_per_request: float = 1.0,
) -> float:
    return incoming_qps * decisions_per_request


def demonstrate_rate_limiting_capacity() -> None:
    print("\n" + "=" * 78)
    print("86. RATE LIMITING UPDATE RATE")
    print("=" * 78)

    incoming_qps = 100_000
    updates = required_rate_limiter_updates(
        incoming_qps,
        decisions_per_request=1,
    )

    print(f"Incoming requests: {incoming_qps:,}/s")
    print(f"Rate-limiter decisions: {updates:,}/s")

    print(
        "If every request performs a stateful rate-limit update, "
        "the limiter itself becomes a high-QPS dependency."
    )


# ============================================================================
# 87. ADVANCED: ESTIMATING DATABASE LOG VOLUME
# ============================================================================

def database_log_bandwidth(
    write_qps: float,
    log_bytes_per_write: int,
    replication_streams: int,
) -> float:
    return (
        write_qps
        * log_bytes_per_write
        * replication_streams
    )


def demonstrate_database_logs() -> None:
    print("\n" + "=" * 78)
    print("87. DATABASE LOG BANDWIDTH")
    print("=" * 78)

    bandwidth = database_log_bandwidth(
        write_qps=10_000,
        log_bytes_per_write=3_000,
        replication_streams=2,
    )

    print(
        f"Estimated database log bandwidth: "
        f"{human_bytes(bandwidth)}/s"
    )


# ============================================================================
# 88. ADVANCED: ESTIMATING OBJECT STORE OPERATIONS
# ============================================================================

@dataclass
class ObjectStoreOperations:
    uploads_per_second: float
    downloads_per_second: float
    metadata_operations_per_upload: float

    @property
    def metadata_qps(self) -> float:
        return (
            self.uploads_per_second
            * self.metadata_operations_per_upload
        )

    @property
    def total_operations_qps(self) -> float:
        return (
            self.uploads_per_second
            + self.downloads_per_second
            + self.metadata_qps
        )


def demonstrate_object_store_operations() -> None:
    print("\n" + "=" * 78)
    print("88. OBJECT STORE OPERATIONS")
    print("=" * 78)

    model = ObjectStoreOperations(
        uploads_per_second=500,
        downloads_per_second=10_000,
        metadata_operations_per_upload=2,
    )

    print(f"Upload QPS: {model.uploads_per_second:,.0f}")
    print(f"Download QPS: {model.downloads_per_second:,.0f}")
    print(f"Metadata QPS: {model.metadata_qps:,.0f}")
    print(f"Total modeled operations: {model.total_operations_qps:,.0f}")


# ============================================================================
# 89. ADVANCED: ESTIMATING TELEMETRY
# ============================================================================

@dataclass
class TelemetryEstimate:
    services: int
    instances_per_service: int
    metrics_per_instance: int
    samples_per_metric_per_minute: int
    bytes_per_sample: int
    retention_days: int

    @property
    def instances(self) -> int:
        return self.services * self.instances_per_service

    @property
    def samples_per_minute(self) -> int:
        return (
            self.instances
            * self.metrics_per_instance
            * self.samples_per_metric_per_minute
        )

    @property
    def samples_per_second(self) -> float:
        return self.samples_per_minute / 60

    @property
    def storage(self) -> float:
        return (
            self.samples_per_second
            * self.bytes_per_sample
            * SECONDS_PER_DAY
            * self.retention_days
        )


def demonstrate_telemetry() -> None:
    print("\n" + "=" * 78)
    print("89. TELEMETRY VOLUME")
    print("=" * 78)

    telemetry = TelemetryEstimate(
        services=100,
        instances_per_service=50,
        metrics_per_instance=1_000,
        samples_per_metric_per_minute=1,
        bytes_per_sample=100,
        retention_days=30,
    )

    print(f"Instances: {telemetry.instances:,}")
    print(f"Samples/minute: {telemetry.samples_per_minute:,}")
    print(f"Samples/second: {telemetry.samples_per_second:,.2f}")
    print(f"30-day raw storage: {human_bytes(telemetry.storage)}")

    print(
        "Observability itself creates traffic and storage requirements. "
        "Metric cardinality is especially important because each unique "
        "label combination can create another time series."
    )


# ============================================================================
# 90. ADVANCED: CARDINALITY
# ============================================================================

def time_series_cardinality(
    services: int,
    instances: int,
    metrics_per_instance: int,
    environments: int,
    regions: int,
) -> int:
    return (
        services
        * instances
        * metrics_per_instance
        * environments
        * regions
    )


def demonstrate_cardinality() -> None:
    print("\n" + "=" * 78)
    print("90. METRIC CARDINALITY")
    print("=" * 78)

    series = time_series_cardinality(
        services=100,
        instances=100,
        metrics_per_instance=500,
        environments=3,
        regions=3,
    )

    print(f"Estimated time series: {series:,}")

    print(
        "Cardinality can grow multiplicatively across dimensions. "
        "Adding labels such as user ID or request ID can create extremely "
        "large series counts and should be treated carefully."
    )


# ============================================================================
# 91. ADVANCED: BACKPRESSURE
# ============================================================================

def sustainable_consumer_capacity(
    consumers: int,
    processing_rate_per_consumer: float,
) -> float:
    return consumers * processing_rate_per_consumer


def demonstrate_backpressure() -> None:
    print("\n" + "=" * 78)
    print("91. BACKPRESSURE")
    print("=" * 78)

    producer_rate = 50_000
    consumer_capacity = sustainable_consumer_capacity(
        consumers=8,
        processing_rate_per_consumer=7_000,
    )

    print(f"Producer rate: {producer_rate:,}/s")
    print(f"Consumer capacity: {consumer_capacity:,}/s")

    if producer_rate > consumer_capacity:
        print(
            "Backpressure is required because producers exceed "
            "sustainable consumer capacity."
        )
    else:
        print("Consumer capacity is sufficient for the modeled rate.")


# ============================================================================
# 92. ADVANCED: TRAFFIC SPIKES
# ============================================================================

def spike_load(
    baseline_qps: float,
    spike_multiplier: float,
    spike_duration_seconds: int,
) -> tuple[float, float]:
    if baseline_qps < 0:
        raise ValueError("baseline_qps cannot be negative.")
    if spike_multiplier < 1:
        raise ValueError("spike_multiplier must be >= 1.")
    if spike_duration_seconds < 0:
        raise ValueError("spike_duration_seconds cannot be negative.")

    spike_qps = baseline_qps * spike_multiplier

    extra_requests = (
        (spike_qps - baseline_qps)
        * spike_duration_seconds
    )

    return spike_qps, extra_requests


def demonstrate_spikes() -> None:
    print("\n" + "=" * 78)
    print("92. TRAFFIC SPIKES")
    print("=" * 78)

    spike_qps, extra_requests = spike_load(
        baseline_qps=20_000,
        spike_multiplier=5,
        spike_duration_seconds=300,
    )

    print(f"Spike QPS: {spike_qps:,}")
    print(f"Extra requests over 5 minutes: {extra_requests:,.0f}")

    print(
        "A burst affects both instantaneous capacity and accumulated work. "
        "Queues, autoscaling, caches, and rate limiting can change the behavior."
    )


# ============================================================================
# 93. ADVANCED: AUTOSCALING LAG
# ============================================================================

@dataclass
class AutoscalingLagModel:
    incoming_qps: float
    current_capacity_qps: float
    scaling_capacity_added_per_second: float
    duration_seconds: int

    def capacity_after(self) -> float:
        return (
            self.current_capacity_qps
            + self.scaling_capacity_added_per_second
            * self.duration_seconds
        )

    def unmet_work(self) -> float:
        """
        Approximate excess requests accumulated during a linear capacity ramp.

        This is a simplified model, not a production autoscaler simulator.
        """
        final_capacity = self.capacity_after()

        if final_capacity >= self.incoming_qps:
            average_capacity = (
                self.current_capacity_qps
                + final_capacity
            ) / 2

            return max(
                0,
                (
                    self.incoming_qps
                    - average_capacity
                )
                * self.duration_seconds,
            )

        return (
            self.incoming_qps
            - final_capacity
        ) * self.duration_seconds


def demonstrate_autoscaling_lag() -> None:
    print("\n" + "=" * 78)
    print("93. AUTOSCALING LAG")
    print("=" * 78)

    model = AutoscalingLagModel(
        incoming_qps=50_000,
        current_capacity_qps=20_000,
        scaling_capacity_added_per_second=2_000,
        duration_seconds=15,
    )

    print(
        f"Capacity after 15 seconds: "
        f"{model.capacity_after():,.0f} QPS"
    )
    print(
        f"Approximate accumulated unmet work: "
        f"{model.unmet_work():,.0f} requests"
    )

    print(
        "Autoscaling is not instantaneous. Capacity planning should consider "
        "startup time, scaling signals, cooldowns, workload burst duration, "
        "and the backlog that accumulates before new capacity becomes ready."
    )


# ============================================================================
# 94. ADVANCED: QUEUEING UTILIZATION
# ============================================================================

def utilization(
    arrival_rate: float,
    service_capacity: float,
) -> float:
    if arrival_rate < 0:
        raise ValueError("arrival_rate cannot be negative.")
    if service_capacity <= 0:
        raise ValueError("service_capacity must be positive.")

    return arrival_rate / service_capacity


def demonstrate_utilization() -> None:
    print("\n" + "=" * 78)
    print("94. CAPACITY UTILIZATION")
    print("=" * 78)

    for arrival, capacity in (
        (5_000, 10_000),
        (8_000, 10_000),
        (9_500, 10_000),
        (10_000, 10_000),
        (11_000, 10_000),
    ):
        print(
            f"{arrival:,}/{capacity:,} -> "
            f"{utilization(arrival, capacity):.0%}"
        )

    print(
        "As utilization approaches saturation, latency and queueing behavior "
        "can deteriorate sharply. Capacity planning is therefore not simply "
        "about avoiding 100% utilization."
    )


# ============================================================================
# 95. ADVANCED: ESTIMATING ACTIVE CONNECTIONS
# ============================================================================

def active_connections(
    connections_per_second: float,
    average_connection_seconds: float,
) -> float:
    return connections_per_second * average_connection_seconds


def demonstrate_active_connections() -> None:
    print("\n" + "=" * 78)
    print("95. ACTIVE CONNECTIONS")
    print("=" * 78)

    active = active_connections(
        connections_per_second=2_000,
        average_connection_seconds=30,
    )

    print(f"Estimated active connections: {active:,.0f}")

    print(
        "Long-lived connections such as WebSockets can create substantial "
        "concurrency even when message QPS is relatively low."
    )


# ============================================================================
# 96. WEBSOCKET MESSAGE BANDWIDTH
# ============================================================================

@dataclass
class WebSocketEstimate:
    connected_clients: int
    messages_per_client_per_second: float
    average_message_bytes: int

    @property
    def messages_per_second(self) -> float:
        return (
            self.connected_clients
            * self.messages_per_client_per_second
        )

    @property
    def bandwidth(self) -> float:
        return (
            self.messages_per_second
            * self.average_message_bytes
        )


def demonstrate_websocket() -> None:
    print("\n" + "=" * 78)
    print("96. WEBSOCKET ESTIMATION")
    print("=" * 78)

    model = WebSocketEstimate(
        connected_clients=1_000_000,
        messages_per_client_per_second=0.2,
        average_message_bytes=1_000,
    )

    print(
        f"Messages/s: "
        f"{model.messages_per_second:,.0f}"
    )
    print(
        f"Bandwidth: "
        f"{human_bytes(model.bandwidth)}/s"
    )

    print(
        "Persistent connections shift the problem from request-per-connection "
        "to connection concurrency, event rate, memory per connection, and "
        "network fan-out."
    )


# ============================================================================
# 97. ADVANCED: MEMORY PER CONNECTION
# ============================================================================

def connection_memory(
    connections: int,
    memory_per_connection_bytes: int,
) -> float:
    return connections * memory_per_connection_bytes


def demonstrate_connection_memory() -> None:
    print("\n" + "=" * 78)
    print("97. MEMORY PER CONNECTION")
    print("=" * 78)

    memory = connection_memory(
        connections=2_000_000,
        memory_per_connection_bytes=20_000,
    )

    print(
        f"Connection state memory: "
        f"{human_bytes(memory)}"
    )

    print(
        "Small per-connection state becomes large at millions of connections. "
        "Connection pooling, event-driven servers, compact state, and horizontal "
        "partitioning can become important."
    )


# ============================================================================
# 98. ADVANCED: DISTRIBUTED LOCK CONTENTION
# ============================================================================

@dataclass
class LockContentionModel:
    requests_per_second: float
    fraction_needing_lock: float
    lock_hold_time_seconds: float

    @property
    def lock_requests_per_second(self) -> float:
        return (
            self.requests_per_second
            * self.fraction_needing_lock
        )

    @property
    def concurrent_lock_holders(self) -> float:
        return (
            self.lock_requests_per_second
            * self.lock_hold_time_seconds
        )


def demonstrate_lock_contention() -> None:
    print("\n" + "=" * 78)
    print("98. LOCK CONTENTION")
    print("=" * 78)

    model = LockContentionModel(
        requests_per_second=10_000,
        fraction_needing_lock=0.20,
        lock_hold_time_seconds=0.005,
    )

    print(
        f"Lock acquisition rate: "
        f"{model.lock_requests_per_second:,.0f}/s"
    )
    print(
        f"Average concurrent lock holders: "
        f"{model.concurrent_lock_holders:.2f}"
    )

    print(
        "Locks can serialize otherwise parallel work. Estimation should "
        "consider contention when a shared resource becomes a bottleneck."
    )


# ============================================================================
# 99. ADVANCED: BATCHED NETWORK TRANSFER
# ============================================================================

@dataclass
class BatchedTransfer:
    records_per_second: float
    record_bytes: int
    batch_size: int
    batch_overhead_bytes: int

    @property
    def batches_per_second(self) -> float:
        return self.records_per_second / self.batch_size

    @property
    def payload_bandwidth(self) -> float:
        return (
            self.records_per_second
            * self.record_bytes
        )

    @property
    def overhead_bandwidth(self) -> float:
        return (
            self.batches_per_second
            * self.batch_overhead_bytes
        )

    @property
    def total_bandwidth(self) -> float:
        return (
            self.payload_bandwidth
            + self.overhead_bandwidth
        )


def demonstrate_batched_transfer() -> None:
    print("\n" + "=" * 78)
    print("99. BATCHED NETWORK TRANSFER")
    print("=" * 78)

    model = BatchedTransfer(
        records_per_second=100_000,
        record_bytes=1_000,
        batch_size=100,
        batch_overhead_bytes=500,
    )

    print(
        f"Payload bandwidth: "
        f"{human_bytes(model.payload_bandwidth)}/s"
    )
    print(
        f"Protocol overhead bandwidth: "
        f"{human_bytes(model.overhead_bandwidth)}/s"
    )
    print(
        f"Total bandwidth: "
        f"{human_bytes(model.total_bandwidth)}/s"
    )

    print(
        "Batching reduces fixed overhead per record but may increase buffering "
        "delay and recovery granularity."
    )


# ============================================================================
# 100. FINAL INTEGRATED STUDY EXAMPLE
# ============================================================================

def final_integrated_example() -> None:
    print("\n" + "=" * 78)
    print("100. FINAL INTEGRATED SYSTEM DESIGN ESTIMATE")
    print("=" * 78)

    print(
        """
Scenario:
    A global content application has 500 million registered users.
    Ten percent are active on a typical day.
    Each active user performs 40 content reads per day.
    Each active user creates 0.2 new records per day.
    Peak traffic is 8x the daily average.
    Five percent of content requests are writes.
    Each stored record averages 3 KB.
    Metadata/index overhead is estimated at 50%.
    Physical replication is 3x.
    Retention is 365 days.
    Average response payload is 25 KB.
    The application fans out to 2 downstream services per request.
    A cache serves 92% of downstream-readable requests.
    """
    )

    registered_users = 500_000_000
    active_fraction = 0.10
    active_users = registered_users * active_fraction

    reads_per_user_per_day = 40
    writes_per_user_per_day = 0.2

    read_requests_per_day = (
        active_users
        * reads_per_user_per_day
    )

    write_records_per_day = (
        active_users
        * writes_per_user_per_day
    )

    read_average_qps = requests_per_second(
        read_requests_per_day
    )

    write_average_qps = requests_per_second(
        write_records_per_day
    )

    peak_multiplier = 8

    peak_read_qps = (
        read_average_qps
        * peak_multiplier
    )

    peak_write_qps = (
        write_average_qps
        * peak_multiplier
    )

    total_peak_qps = (
        peak_read_qps
        + peak_write_qps
    )

    downstream_calls = 2

    raw_downstream_qps = (
        total_peak_qps
        * downstream_calls
    )

    cache_hit_rate = 0.92

    cache_miss_downstream_qps = (
        raw_downstream_qps
        * (1 - cache_hit_rate)
    )

    record_size = 3_000
    metadata_multiplier = 1.5
    replication = 3
    retention_days = 365

    daily_logical_storage = (
        write_records_per_day
        * record_size
        * metadata_multiplier
    )

    retained_logical_storage = (
        daily_logical_storage
        * retention_days
    )

    retained_physical_storage = (
        retained_logical_storage
        * replication
    )

    response_bytes = 25_000

    response_bandwidth = (
        total_peak_qps
        * response_bytes
    )

    print("TRAFFIC")
    print("-" * 78)
    print(f"Registered users: {registered_users:,}")
    print(f"Daily active users: {active_users:,.0f}")
    print(f"Read requests/day: {read_requests_per_day:,.0f}")
    print(f"Write records/day: {write_records_per_day:,.0f}")
    print(f"Average read QPS: {read_average_qps:,.2f}")
    print(f"Average write QPS: {write_average_qps:,.2f}")
    print(f"Peak read QPS: {peak_read_qps:,.2f}")
    print(f"Peak write QPS: {peak_write_qps:,.2f}")
    print(f"Total peak QPS: {total_peak_qps:,.2f}")

    print("\nDOWNSTREAM AMPLIFICATION")
    print("-" * 78)
    print(f"Calls/request: {downstream_calls}")
    print(f"Raw downstream QPS: {raw_downstream_qps:,.2f}")
    print(
        f"Cache hit rate: {cache_hit_rate:.0%}"
    )
    print(
        f"Cache-miss downstream QPS: "
        f"{cache_miss_downstream_qps:,.2f}"
    )

    print("\nSTORAGE")
    print("-" * 78)
    print(
        f"Daily logical storage: "
        f"{human_bytes(daily_logical_storage)}"
    )
    print(
        f"365-day logical storage: "
        f"{human_bytes(retained_logical_storage)}"
    )
    print(
        f"365-day physical replicated storage: "
        f"{human_bytes(retained_physical_storage)}"
    )

    print("\nNETWORK")
    print("-" * 78)
    print(
        f"Peak response bandwidth: "
        f"{human_bytes(response_bandwidth)}/s"
    )
    print(
        f"Peak response network rate: "
        f"{human_bits_per_second(response_bandwidth * 8)}"
    )

    print("\nSANITY CHECKS")
    print("-" * 78)

    sanity_check_order(
        "average read QPS",
        read_average_qps,
        "peak read QPS",
        peak_read_qps,
    )

    sanity_check_order(
        "average write QPS",
        write_average_qps,
        "peak write QPS",
        peak_write_qps,
    )

    sanity_check_nonnegative(
        "physical storage",
        retained_physical_storage,
    )

    print("Traffic ordering and storage sanity checks passed.")

    print(
        """
Architectural implications:
    1. The read path dominates request volume.
    2. Caching can substantially reduce downstream read load.
    3. Fan-out must be included when sizing internal services.
    4. Write traffic determines durable data growth.
    5. Metadata, indexes, and replication turn logical storage into larger
       physical storage.
    6. Large response payloads can make network capacity a first-class
       constraint.
    7. Peak traffic, not merely daily average traffic, influences capacity.
    8. Production sizing should add headroom and account for failures,
       retries, uneven traffic, and scaling lag.
    """
    )


# ============================================================================
# 101. MAIN PROGRAM
# ============================================================================

def main() -> None:
    """
    Execute all educational demonstrations in a logical progression.

    The script intentionally runs examples rather than merely defining
    functions. Reading the output alongside the source code makes the
    quantitative relationships easier to follow.
    """

    demonstrate_units()
    demonstrate_basic_formulas()
    demonstrate_growth()
    demonstrate_traffic_model()
    demonstrate_user_funnel()
    demonstrate_peaks()
    demonstrate_read_write_ratio()
    demonstrate_storage()
    demonstrate_storage_from_qps()
    demonstrate_bandwidth()
    demonstrate_request_response_bandwidth()
    demonstrate_cache()
    demonstrate_cache_size()
    demonstrate_fanout()
    demonstrate_fan_in()
    demonstrate_broadcast()
    demonstrate_littles_law()
    demonstrate_cpu_capacity()
    demonstrate_database_capacity()
    demonstrate_iops()
    demonstrate_queue_backlog()
    demonstrate_queue_drain()
    demonstrate_availability()
    demonstrate_replication()
    demonstrate_write_amplification()
    demonstrate_retention()
    demonstrate_time_series()
    demonstrate_logging_storage()
    demonstrate_media_storage()
    demonstrate_cdn()
    demonstrate_load_balancer()
    demonstrate_headroom()
    demonstrate_n_plus_one()
    demonstrate_failure_domains()
    demonstrate_deduplication()
    demonstrate_sensitivity()
    demonstrate_ranges()
    demonstrate_multipliers()
    demonstrate_unit_safe_estimation()
    demonstrate_power_of_ten_shortcuts()
    demonstrate_server_pool()
    demonstrate_latency_budget()
    demonstrate_serial_parallel_latency()
    demonstrate_percentiles()
    demonstrate_component_availability()
    demonstrate_parallel_availability()
    demonstrate_hourly_traffic()
    demonstrate_terminology()
    demonstrate_query_amplification()
    demonstrate_n_plus_one_query_problem()
    demonstrate_complete_social_feed()
    demonstrate_url_shortener()
    demonstrate_file_upload()
    demonstrate_message_queue()
    demonstrate_index_storage()
    demonstrate_storage_headroom()
    demonstrate_network_egress()
    demonstrate_database_connections()
    demonstrate_connection_explosion()
    demonstrate_backup_storage()
    demonstrate_rpo_rto()
    demonstrate_retry_amplification()
    demonstrate_layered_retries()
    demonstrate_async_processing()
    demonstrate_batching()
    demonstrate_sharding()
    demonstrate_hot_partitions()
    demonstrate_cross_region_replication()
    demonstrate_queue_storage()
    demonstrate_checklist()
    demonstrate_common_mistakes()
    demonstrate_sanity_checks()
    demonstrate_significant_figures()
    demonstrate_reusable_estimator()
    demonstrate_production_capacity()
    demonstrate_architecture_comparison()
    run_tests()
    demonstrate_edge_cases()
    end_to_end_estimation()
    demonstrate_layer_capacity()
    demonstrate_error_propagation()
    demonstrate_resource_cost_model()
    demonstrate_search_index()
    demonstrate_cache_key_memory()
    demonstrate_rate_limiter()
    demonstrate_rate_limiting_capacity()
    demonstrate_database_logs()
    demonstrate_object_store_operations()
    demonstrate_telemetry()
    demonstrate_cardinality()
    demonstrate_backpressure()
    demonstrate_spikes()
    demonstrate_autoscaling_lag()
    demonstrate_utilization()
    demonstrate_active_connections()
    demonstrate_websocket()
    demonstrate_connection_memory()
    demonstrate_lock_contention()
    demonstrate_batched_transfer()
    final_integrated_example()

    print("\n" + "=" * 78)
    print("END OF SYSTEM DESIGN ESTIMATION STUDY SCRIPT")
    print("=" * 78)


if __name__ == "__main__":
    main()
