"""
SYSTEM DESIGN FOUNDATIONS: AVAILABILITY
=======================================

Topic:
    Uptime, Downtime, SLA, SLO, and SLI

Purpose:
    A standalone study script that teaches availability from absolute beginner
    level through advanced system-design concepts.

The script combines:
    - Definitions and terminology
    - Availability mathematics
    - Uptime and downtime calculations
    - SLI design
    - SLO design
    - SLA design
    - Error budgets
    - Availability targets
    - Monthly/annual downtime budgets
    - Measurement windows
    - Request-based and time-based availability
    - Multi-component systems
    - Serial and redundant architectures
    - Dependency availability
    - Maintenance
    - Incident analysis
    - Monitoring
    - Burn-rate calculations
    - Alerting
    - Retry and timeout implications
    - Partial availability
    - Capacity and overload
    - Testing
    - Validation
    - Production-oriented design considerations
    - Edge cases and common mistakes

No third-party packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from math import prod
from statistics import mean
from typing import Callable, Iterable, Optional, Sequence
import random
import unittest


# High precision is useful when calculating very small error budgets.
getcontext().prec = 28


# =============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# =============================================================================

print("=" * 80)
print("SYSTEM DESIGN FOUNDATIONS: AVAILABILITY")
print("=" * 80)


def print_section(title: str) -> None:
    """Print a readable section heading."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


print_section("1. FUNDAMENTAL TERMINOLOGY")

print(
    """
Availability is the proportion of time, requests, or operations during which
a system is usable according to a defined criterion.

Uptime:
    Time during which a service is considered available.

Downtime:
    Time during which a service is considered unavailable.

SLA:
    Service Level Agreement. A contractual or commercial commitment made to
    customers about a measurable service level.

SLO:
    Service Level Objective. An internal or operational target for a service
    level, such as 99.9% successful requests over a calendar month.

SLI:
    Service Level Indicator. The actual measured quantity used to evaluate
    service behavior, such as successful requests divided by valid requests.

Error budget:
    The amount of unreliability permitted by an SLO.

A key distinction:

    SLI = measurement
    SLO = target
    SLA = external commitment
    Error budget = tolerated failure derived from the SLO
"""
)


# =============================================================================
# 2. BASIC AVAILABILITY CALCULATION
# =============================================================================

print_section("2. BASIC AVAILABILITY MATHEMATICS")


def availability_from_time(
    total_time_seconds: float,
    downtime_seconds: float,
) -> float:
    """
    Calculate time-based availability.

    Formula:
        Availability = (Total Time - Downtime) / Total Time
    """
    if total_time_seconds <= 0:
        raise ValueError("Total time must be greater than zero.")

    if downtime_seconds < 0:
        raise ValueError("Downtime cannot be negative.")

    if downtime_seconds > total_time_seconds:
        raise ValueError("Downtime cannot exceed total time.")

    return (total_time_seconds - downtime_seconds) / total_time_seconds


def availability_percentage(
    total_time_seconds: float,
    downtime_seconds: float,
) -> float:
    """Return availability as a percentage."""
    return availability_from_time(total_time_seconds, downtime_seconds) * 100


one_day = 24 * 60 * 60
one_hour = 60 * 60

print(f"One hour of downtime in one day: "
      f"{availability_percentage(one_day, one_hour):.4f}% availability")

print(f"Ten minutes of downtime in one day: "
      f"{availability_percentage(one_day, 10 * 60):.4f}% availability")

print(f"Five minutes of downtime in one month-sized 30-day period: "
      f"{availability_percentage(30 * one_day, 5 * 60):.6f}% availability")


# =============================================================================
# 3. AVAILABILITY AS A RATIO
# =============================================================================

print_section("3. AVAILABILITY RATIO")

total_requests = 1_000_000
successful_requests = 999_000

request_availability = successful_requests / total_requests

print(f"Total requests:       {total_requests:,}")
print(f"Successful requests:  {successful_requests:,}")
print(f"Availability:         {request_availability * 100:.4f}%")
print(f"Failed requests:      {total_requests - successful_requests:,}")


# =============================================================================
# 4. TIME-BASED VS REQUEST-BASED AVAILABILITY
# =============================================================================

print_section("4. TIME-BASED VS REQUEST-BASED AVAILABILITY")

print(
    """
Availability can be measured using different SLIs.

Time-based SLI:
    Available seconds / total eligible seconds

Request-based SLI:
    Good requests / total valid requests

Time-based measurement is useful when the service has a continuously
observable state.

Request-based measurement is often more meaningful for APIs because a server
may technically be reachable while returning errors for actual customer
requests.

Example:
    A website is reachable for 99.99% of the month but returns HTTP 500 for
    20% of checkout requests. A simple uptime monitor may report excellent
    availability while customers experience a severe outage.
"""
)


# =============================================================================
# 5. SLA / SLO / SLI RELATIONSHIP
# =============================================================================

print_section("5. SLI, SLO, SLA, AND ERROR BUDGET")

@dataclass(frozen=True)
class ServiceLevelDefinitions:
    """Represent the relationship between SLI, SLO, and SLA."""

    sli: str
    slo: float
    sla: float

    def validate(self) -> None:
        if not 0 <= self.slo <= 1:
            raise ValueError("SLO must be between 0 and 1.")

        if not 0 <= self.sla <= 1:
            raise ValueError("SLA must be between 0 and 1.")

    @property
    def error_budget(self) -> float:
        """Fraction of service behavior allowed to fall outside the SLO."""
        return 1 - self.slo


levels = ServiceLevelDefinitions(
    sli="successful valid API requests / total valid API requests",
    slo=0.999,
    sla=0.995,
)

levels.validate()

print("SLI:", levels.sli)
print("SLO:", f"{levels.slo * 100:.3f}%")
print("SLA:", f"{levels.sla * 100:.3f}%")
print("SLO error budget:", f"{levels.error_budget * 100:.3f}%")


# =============================================================================
# 6. COMMON AVAILABILITY TARGETS
# =============================================================================

print_section("6. AVAILABILITY TARGETS AND DOWNTIME BUDGETS")


def downtime_budget(
    period_seconds: float,
    availability_target: float,
) -> float:
    """
    Calculate permitted downtime for a target.

    Example:
        99.9% availability permits 0.1% unavailability.
    """
    if period_seconds < 0:
        raise ValueError("Period cannot be negative.")

    if not 0 <= availability_target <= 1:
        raise ValueError("Availability target must be between 0 and 1.")

    return period_seconds * (1 - availability_target)


targets = [
    Decimal("0.90"),
    Decimal("0.99"),
    Decimal("0.999"),
    Decimal("0.9999"),
    Decimal("0.99999"),
    Decimal("0.999999"),
]

thirty_days = 30 * 24 * 60 * 60
one_year = 365 * 24 * 60 * 60

print(f"{'Target':<12}{'30-day budget':<24}{'Annual budget'}")

for target in targets:
    monthly_seconds = Decimal(thirty_days) * (Decimal("1") - target)
    annual_seconds = Decimal(one_year) * (Decimal("1") - target)

    monthly_minutes = monthly_seconds / Decimal(60)
    annual_hours = annual_seconds / Decimal(3600)

    print(
        f"{target * 100:>7.5f}%   "
        f"{monthly_minutes:>10.2f} minutes       "
        f"{annual_hours:>10.2f} hours"
    )


# =============================================================================
# 7. HELPER FOR HUMAN-READABLE DURATIONS
# =============================================================================

print_section("7. HUMAN-READABLE TIME CONVERSION")


def format_duration(seconds: float) -> str:
    """Convert seconds to a readable duration."""
    if seconds < 0:
        raise ValueError("Duration cannot be negative.")

    total_seconds = int(round(seconds))

    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds_remaining = divmod(remainder, 60)

    parts = []

    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds_remaining or not parts:
        parts.append(f"{seconds_remaining}s")

    return " ".join(parts)


for target in [0.99, 0.999, 0.9999, 0.99999, 0.999999]:
    budget = downtime_budget(thirty_days, target)
    print(f"{target * 100:.5f}% -> {format_duration(budget)}")


# =============================================================================
# 8. SLA EXAMPLE
# =============================================================================

print_section("8. SLA EXAMPLE")

@dataclass
class SLA:
    """
    A simplified SLA model.

    Real commercial SLAs can include exclusions, measurement rules,
    maintenance windows, service credits, reporting rules, and legal terms.
    """

    name: str
    monthly_target: float
    measurement_window_seconds: int
    maintenance_excluded_seconds: int = 0

    def effective_measurement_time(self) -> int:
        eligible = (
            self.measurement_window_seconds
            - self.maintenance_excluded_seconds
        )

        if eligible < 0:
            raise ValueError("Excluded maintenance exceeds measurement window.")

        return eligible

    def allowed_downtime_seconds(self) -> float:
        return downtime_budget(
            self.effective_measurement_time(),
            self.monthly_target,
        )


example_sla = SLA(
    name="Public API SLA",
    monthly_target=0.999,
    measurement_window_seconds=30 * 24 * 60 * 60,
    maintenance_excluded_seconds=2 * 60 * 60,
)

print("SLA:", example_sla.name)
print("Target:", f"{example_sla.monthly_target * 100:.3f}%")
print(
    "Allowed downtime:",
    format_duration(example_sla.allowed_downtime_seconds()),
)


# =============================================================================
# 9. SLI IMPLEMENTATION
# =============================================================================

print_section("9. IMPLEMENTING A REQUEST-BASED SLI")


@dataclass
class Request:
    """Represent one service request."""

    status_code: int
    latency_ms: float
    valid: bool = True


def is_good_request(request: Request) -> bool:
    """
    Define the numerator of an availability SLI.

    This example considers HTTP 2xx and 3xx responses successful.
    The exact definition must match the service's user-visible behavior.
    """
    return request.valid and 200 <= request.status_code < 400


def request_availability_sli(requests: Sequence[Request]) -> float:
    """Calculate the request-based availability SLI."""
    valid_requests = [request for request in requests if request.valid]

    if not valid_requests:
        raise ValueError("No valid requests were available for measurement.")

    good_requests = sum(
        is_good_request(request)
        for request in valid_requests
    )

    return good_requests / len(valid_requests)


sample_requests = [
    Request(200, 120),
    Request(200, 90),
    Request(201, 150),
    Request(500, 220),
    Request(503, 400),
    Request(404, 70),
    Request(302, 50),
]

sli = request_availability_sli(sample_requests)

print(f"Availability SLI: {sli * 100:.4f}%")


# =============================================================================
# 10. EDGE CASE: VALID VS INVALID REQUESTS
# =============================================================================

print_section("10. VALID REQUESTS AND SLI BOUNDARIES")

print(
    """
A strong SLI must define which requests belong in the denominator.

Examples that may need explicit treatment:
    - Health checks
    - Internal traffic
    - Synthetic monitoring
    - Requests rejected before reaching the service
    - Invalid user input
    - Authentication failures
    - Rate-limited requests
    - Dependency failures
    - Client cancellations
    - Load-test traffic
    - Administrative requests

The denominator is not merely a technical detail. Changing the denominator can
materially change the reported availability.
"""
)


# =============================================================================
# 11. MULTIPLE SLIs
# =============================================================================

print_section("11. AVAILABILITY, LATENCY, AND CORRECTNESS SLIs")


@dataclass
class SLISet:
    """Represent several service-level indicators."""

    availability: float
    latency: float
    correctness: float

    def validate(self) -> None:
        for name, value in vars(self).items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")


slis = SLISet(
    availability=0.9995,
    latency=0.995,
    correctness=0.9998,
)

slis.validate()

print(
    f"Availability SLI: {slis.availability * 100:.3f}%\n"
    f"Latency SLI:      {slis.latency * 100:.3f}%\n"
    f"Correctness SLI:  {slis.correctness * 100:.3f}%"
)


# =============================================================================
# 12. COMPOSITE SLO
# =============================================================================

print_section("12. COMPOSITE SLO CONSIDERATIONS")

print(
    """
A service can have several independent objectives.

Example:
    Availability >= 99.9%
    99% of requests < 300 ms
    Correctness >= 99.99%

Meeting availability alone does not mean users are having a good experience.

An API that responds with HTTP 200 but returns incorrect data may be technically
available while operationally failing its purpose.
"""
)


# =============================================================================
# 13. ERROR BUDGET
# =============================================================================

print_section("13. ERROR BUDGET")


@dataclass
class ErrorBudget:
    """Track SLO allowance and actual consumption."""

    slo: float
    eligible_events: int
    bad_events: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.slo <= 1:
            raise ValueError("SLO must be between 0 and 1.")

        if self.eligible_events < 0:
            raise ValueError("Eligible events cannot be negative.")

        if self.bad_events < 0:
            raise ValueError("Bad events cannot be negative.")

    @property
    def allowed_bad_events(self) -> float:
        return self.eligible_events * (1 - self.slo)

    @property
    def consumed_fraction(self) -> float:
        budget = self.allowed_bad_events

        if budget == 0:
            return 0.0 if self.bad_events == 0 else float("inf")

        return self.bad_events / budget

    @property
    def remaining_bad_events(self) -> float:
        return max(self.allowed_bad_events - self.bad_events, 0)

    @property
    def within_budget(self) -> bool:
        return self.bad_events <= self.allowed_bad_events


budget = ErrorBudget(
    slo=0.999,
    eligible_events=1_000_000,
    bad_events=700,
)

print(f"Allowed bad requests: {budget.allowed_bad_events:.0f}")
print(f"Actual bad requests:  {budget.bad_events}")
print(f"Remaining budget:    {budget.remaining_bad_events:.0f}")
print(f"Within budget:       {budget.within_budget}")
print(f"Budget consumed:     {budget.consumed_fraction * 100:.2f}%")


# =============================================================================
# 14. ERROR BUDGET AS TIME
# =============================================================================

print_section("14. ERROR BUDGET AS TIME")


def error_budget_seconds(
    measurement_period_seconds: int,
    slo: float,
) -> float:
    return downtime_budget(measurement_period_seconds, slo)


for slo in [0.99, 0.999, 0.9999]:
    seconds = error_budget_seconds(thirty_days, slo)
    print(
        f"SLO {slo * 100:.4f}% -> "
        f"{format_duration(seconds)} error budget"
    )


# =============================================================================
# 15. SLO COMPLIANCE
# =============================================================================

print_section("15. SLO COMPLIANCE")


def meets_slo(actual_sli: float, target_slo: float) -> bool:
    if not 0 <= actual_sli <= 1:
        raise ValueError("Actual SLI must be between 0 and 1.")

    if not 0 <= target_slo <= 1:
        raise ValueError("SLO must be between 0 and 1.")

    return actual_sli >= target_slo


for actual in [0.998, 0.999, 0.9995, 1.0]:
    print(
        f"Actual={actual * 100:.3f}% | "
        f"SLO=99.900% | "
        f"Pass={meets_slo(actual, 0.999)}"
    )


# =============================================================================
# 16. AVAILABILITY OF A SINGLE COMPONENT
# =============================================================================

print_section("16. SINGLE COMPONENT AVAILABILITY")


@dataclass(frozen=True)
class Component:
    """Represent a system component with a stated availability."""

    name: str
    availability: float

    def __post_init__(self) -> None:
        if not 0 <= self.availability <= 1:
            raise ValueError("Availability must be between 0 and 1.")


database = Component("Database", 0.999)
cache = Component("Cache", 0.9999)
api = Component("API", 0.9995)

for component in [database, cache, api]:
    print(
        f"{component.name:<12} "
        f"{component.availability * 100:.4f}%"
    )


# =============================================================================
# 17. SERIAL DEPENDENCIES
# =============================================================================

print_section("17. SERIAL SYSTEMS AND MULTIPLICATIVE AVAILABILITY")

print(
    """
If a request requires multiple independent components to all be available,
the system's availability is approximately the product of the component
availabilities.

For components A and B:

    P(system available) = P(A available) * P(B available)

This is a simplified model. Real systems can have correlated failures,
shared infrastructure, retries, caching, failover, and other mechanisms.
"""

def serial_availability(components: Sequence[Component]) -> float:
    """Calculate availability when every component is required."""
    if not components:
        raise ValueError("At least one component is required.")

    return prod(component.availability for component in components)


serial_components = [
    Component("Load Balancer", 0.9999),
    Component("API", 0.999),
    Component("Database", 0.999),
]

system_availability = serial_availability(serial_components)

print(
    "Approximate serial availability:",
    f"{system_availability * 100:.5f}%"
)


# =============================================================================
# 18. REDUNDANCY
# =============================================================================

print_section("18. REDUNDANCY AND FAILOVER")

print(
    """
For two independent components in an active/active redundant configuration,
the system is available if at least one component is available.

If each component has availability A:

    Redundant availability = 1 - (1 - A)^2

This demonstrates why redundancy can dramatically improve availability.

The independence assumption is critical. Two servers in the same failed
availability zone do not provide the same protection as genuinely independent
failure domains.
"""


def redundant_availability(
    component_availability: float,
    replicas: int,
) -> float:
    """
    Calculate availability when at least one of N independent replicas works.
    """
    if not 0 <= component_availability <= 1:
        raise ValueError("Component availability must be between 0 and 1.")

    if replicas < 1:
        raise ValueError("There must be at least one replica.")

    failure_probability = 1 - component_availability

    return 1 - failure_probability ** replicas


for replicas in range(1, 6):
    result = redundant_availability(0.99, replicas)
    print(
        f"{replicas} independent replicas at 99% each -> "
        f"{result * 100:.6f}%"
    )


# =============================================================================
# 19. N+1 REDUNDANCY
# =============================================================================

print_section("19. N+1 REDUNDANCY CONCEPT")

print(
    """
N+1 redundancy means a system has enough capacity for N required units plus
one additional unit.

Availability engineering distinguishes between:
    - Component redundancy
    - Capacity redundancy
    - Network redundancy
    - Power redundancy
    - Storage redundancy
    - Geographic redundancy

Redundancy is useful only when the failure domains are sufficiently independent
and failover actually works.
"""


# =============================================================================
# 20. CORRELATED FAILURE
# =============================================================================

print_section("20. CORRELATED FAILURES")

print(
    """
Multiplying availability numbers can be misleading when components share
common dependencies.

Examples:
    - Two servers share one power source.
    - Two database replicas share one storage subsystem.
    - Multiple zones depend on one control plane.
    - Multiple regions depend on the same DNS provider.
    - All replicas use the same faulty software release.

If a common dependency fails, several apparently independent components may
fail together.

The real design question is therefore:

    "What are the failure domains?"

rather than merely:

    "How many replicas do we have?"
"""
)


# =============================================================================
# 21. AVAILABILITY TREE
# =============================================================================

print_section("21. AVAILABILITY TREE")

@dataclass
class AvailabilityNode:
    """
    Simple availability tree.

    mode="AND":
        Every child must be available.

    mode="OR":
        At least one child must be available.
    """

    name: str
    availability: Optional[float] = None
    mode: Optional[str] = None
    children: list["AvailabilityNode"] = field(default_factory=list)

    def calculate(self) -> float:
        if self.availability is not None:
            if not 0 <= self.availability <= 1:
                raise ValueError("Leaf availability must be between 0 and 1.")
            return self.availability

        if not self.children:
            raise ValueError("A non-leaf node needs children.")

        if self.mode == "AND":
            return prod(child.calculate() for child in self.children)

        if self.mode == "OR":
            failure_probability = prod(
                1 - child.calculate()
                for child in self.children
            )
            return 1 - failure_probability

        raise ValueError("mode must be AND or OR.")


architecture = AvailabilityNode(
    name="Service",
    mode="AND",
    children=[
        AvailabilityNode(
            name="Frontend",
            availability=0.999,
        ),
        AvailabilityNode(
            name="Backend",
            mode="OR",
            children=[
                AvailabilityNode("Backend A", availability=0.999),
                AvailabilityNode("Backend B", availability=0.999),
            ],
        ),
    ],
)

print(
    f"Estimated architecture availability: "
    f"{architecture.calculate() * 100:.6f}%"
)


# =============================================================================
# 22. MAINTENANCE WINDOWS
# =============================================================================

print_section("22. MAINTENANCE AND AVAILABILITY")

print(
    """
Maintenance must be defined explicitly in availability measurement.

Possible policies include:
    1. Count all maintenance as downtime.
    2. Exclude approved maintenance windows.
    3. Exclude only maintenance announced according to contract.
    4. Measure customer-visible availability regardless of maintenance.

There is no universally correct policy. The important requirement is that the
measurement rules are explicit and consistent.

Planned maintenance should not be used to hide avoidable service failures.
"""


# =============================================================================
# 23. INCIDENT MODEL
# =============================================================================

print_section("23. INCIDENT MODEL")

class IncidentSeverity(Enum):
    """Simplified incident severity classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Incident:
    """Represent a production incident affecting availability."""

    incident_id: str
    start: datetime
    end: datetime
    severity: IncidentSeverity
    customer_impact: str

    def duration_seconds(self) -> float:
        if self.end < self.start:
            raise ValueError("Incident end cannot precede start.")

        return (self.end - self.start).total_seconds()


incident = Incident(
    incident_id="INC-1001",
    start=datetime(2026, 9, 1, 10, 0, 0),
    end=datetime(2026, 9, 1, 10, 17, 30),
    severity=IncidentSeverity.HIGH,
    customer_impact="Checkout requests failed.",
)

print("Incident:", incident.incident_id)
print("Severity:", incident.severity.value)
print("Duration:", format_duration(incident.duration_seconds()))
print("Impact:", incident.customer_impact)


# =============================================================================
# 24. INCIDENTS AND MONTHLY AVAILABILITY
# =============================================================================

print_section("24. CALCULATING MONTHLY AVAILABILITY FROM INCIDENTS")


def aggregate_incident_downtime(incidents: Sequence[Incident]) -> float:
    """Sum incident durations."""
    return sum(incident.duration_seconds() for incident in incidents)


incidents = [
    Incident(
        "INC-1",
        datetime(2026, 9, 2, 9, 0),
        datetime(2026, 9, 2, 9, 4),
        IncidentSeverity.MEDIUM,
        "Elevated API errors",
    ),
    Incident(
        "INC-2",
        datetime(2026, 9, 10, 13, 0),
        datetime(2026, 9, 10, 13, 20),
        IncidentSeverity.HIGH,
        "Database outage",
    ),
    Incident(
        "INC-3",
        datetime(2026, 9, 20, 18, 30),
        datetime(2026, 9, 20, 18, 33),
        IncidentSeverity.LOW,
        "Brief network failure",
    ),
]

month_seconds = 30 * 24 * 60 * 60
downtime = aggregate_incident_downtime(incidents)
monthly_availability = availability_from_time(month_seconds, downtime)

print("Total incident downtime:", format_duration(downtime))
print("Monthly availability:", f"{monthly_availability * 100:.5f}%")


# =============================================================================
# 25. OVERLAPPING INCIDENTS
# =============================================================================

print_section("25. IMPORTANT EDGE CASE: OVERLAPPING INCIDENTS")

print(
    """
If two incidents overlap in time, simply adding their durations double-counts
the affected interval.

Example:
    Incident A: 10:00-10:20
    Incident B: 10:10-10:30

The union of downtime is 30 minutes, not 40 minutes.

Production availability systems should calculate the union of affected
intervals when the SLI is time-based.
"""


def merge_intervals(
    intervals: Sequence[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Merge overlapping time intervals."""
    if not intervals:
        return []

    normalized = []

    for start, end in intervals:
        if end < start:
            raise ValueError("Interval end cannot precede start.")
        normalized.append((start, end))

    normalized.sort(key=lambda item: item[0])

    merged = [normalized[0]]

    for start, end in normalized[1:]:
        previous_start, previous_end = merged[-1]

        if start <= previous_end:
            merged[-1] = (
                previous_start,
                max(previous_end, end),
            )
        else:
            merged.append((start, end))

    return merged


overlapping = [
    (
        datetime(2026, 9, 1, 10, 0),
        datetime(2026, 9, 1, 10, 20),
    ),
    (
        datetime(2026, 9, 1, 10, 10),
        datetime(2026, 9, 1, 10, 30),
    ),
]

merged = merge_intervals(overlapping)

print("Original intervals:", len(overlapping))
print("Merged intervals:", len(merged))

merged_seconds = sum(
    (end - start).total_seconds()
    for start, end in merged
)

print("Union duration:", format_duration(merged_seconds))


# =============================================================================
# 26. REQUEST ERROR RATE
# =============================================================================

print_section("26. ERROR RATE")

def error_rate(
    total_requests: int,
    failed_requests: int,
) -> float:
    """Calculate request error rate."""
    if total_requests <= 0:
        raise ValueError("Total requests must be greater than zero.")

    if failed_requests < 0:
        raise ValueError("Failed requests cannot be negative.")

    if failed_requests > total_requests:
        raise ValueError("Failed requests cannot exceed total requests.")

    return failed_requests / total_requests


rate = error_rate(2_000_000, 1_200)

print(f"Error rate: {rate * 100:.4f}%")
print(f"Availability: {(1 - rate) * 100:.4f}%")


# =============================================================================
# 27. PERCENTAGES AND PRECISION
# =============================================================================

print_section("27. PRECISION AND ROUNDING")

print(
    """
Availability targets are often extremely close to 100%.

For example:

    99.9%   means 0.1% unavailable
    99.99%  means 0.01% unavailable
    99.999% means 0.001% unavailable

Small percentage differences can represent substantial operational
differences at large scale.

Do not calculate or display availability with insufficient precision.
"""
)

for availability in [0.999, 0.9999, 0.99999]:
    print(
        f"{availability * 100:.5f}% -> "
        f"unavailability={(1 - availability) * 100:.5f}%"
    )


# =============================================================================
# 28. AVAILABILITY VS RELIABILITY
# =============================================================================

print_section("28. AVAILABILITY VS RELIABILITY")

print(
    """
Availability:
    Probability that a service is operational at a particular point in time
    or meets the defined service criterion over a measurement period.

Reliability:
    Probability that a system performs correctly without failure for a
    specified period.

A service can recover quickly from frequent failures and still have high
availability.

Example:
    Ten failures of 10 seconds each may produce high availability despite
    poor reliability characteristics.

Conversely, a system that rarely fails but takes hours to recover can have
poor availability.

Availability is strongly influenced by both:
    - Failure frequency
    - Recovery time
"""
)


# =============================================================================
# 29. MTBF, MTTR, AND AVAILABILITY
# =============================================================================

print_section("29. MTBF, MTTR, AND AVAILABILITY")

print(
    """
MTBF = Mean Time Between Failures
MTTR = Mean Time To Repair/Recover

A simplified steady-state relationship is:

    Availability ≈ MTBF / (MTBF + MTTR)

This is an approximation and depends on definitions and assumptions.
"""
)


def availability_from_mtbf_mttr(
    mtbf_seconds: float,
    mttr_seconds: float,
) -> float:
    if mtbf_seconds < 0 or mttr_seconds < 0:
        raise ValueError("MTBF and MTTR cannot be negative.")

    if mtbf_seconds + mttr_seconds == 0:
        raise ValueError("MTBF + MTTR must be greater than zero.")

    return mtbf_seconds / (mtbf_seconds + mttr_seconds)


mtbf = 30 * 24 * 60 * 60
mttr = 30 * 60

print(
    "Availability:",
    f"{availability_from_mtbf_mttr(mtbf, mttr) * 100:.5f}%"
)


# =============================================================================
# 30. AVAILABILITY IMPROVEMENT
# =============================================================================

print_section("30. TWO BASIC WAYS TO IMPROVE AVAILABILITY")

print(
    """
Availability engineering usually attacks two broad variables:

1. Reduce failure frequency.
   Examples:
       - Better testing
       - Safer deployments
       - Capacity planning
       - Fault isolation
       - Dependency management

2. Reduce recovery time.
   Examples:
       - Automated rollback
       - Health checks
       - Failover
       - Good observability
       - Runbooks
       - Automated remediation

Reducing MTTR can sometimes be cheaper and more effective than trying to
eliminate every possible failure.
"""
)


# =============================================================================
# 31. TIMEOUTS
# =============================================================================

print_section("31. TIMEOUTS AND AVAILABILITY")

@dataclass(frozen=True)
class TimeoutPolicy:
    """Represent a basic timeout policy."""

    connect_timeout_ms: int
    read_timeout_ms: int

    def validate(self) -> None:
        if self.connect_timeout_ms <= 0:
            raise ValueError("Connect timeout must be positive.")

        if self.read_timeout_ms <= 0:
            raise ValueError("Read timeout must be positive.")


timeout_policy = TimeoutPolicy(
    connect_timeout_ms=500,
    read_timeout_ms=2_000,
)

timeout_policy.validate()

print(timeout_policy)


# =============================================================================
# 32. RETRIES AND THE RETRY STORM PROBLEM
# =============================================================================

print_section("32. RETRIES, AVAILABILITY, AND RETRY STORMS")

print(
    """
Retries can improve apparent availability when failures are transient.

But retries can also reduce availability when a dependency is overloaded.

Potential failure pattern:

    Service becomes slow
        -> callers timeout
        -> callers retry
        -> traffic increases
        -> dependency becomes slower
        -> more timeouts
        -> more retries

This feedback loop is called a retry storm.

Production retry policies should usually consider:
    - Limited retry count
    - Exponential backoff
    - Jitter
    - Idempotency
    - Retryable vs non-retryable errors
    - Overall request deadline
    - Dependency load
    - Circuit breakers
"""
)


def exponential_backoff(
    initial_seconds: float,
    attempt: int,
    maximum_seconds: float,
    jitter_ratio: float = 0.0,
    random_source: Optional[random.Random] = None,
) -> float:
    """
    Calculate exponential backoff.

    attempt=0 -> initial delay
    attempt=1 -> 2 * initial delay
    attempt=2 -> 4 * initial delay

    Jitter prevents many clients from retrying simultaneously.
    """
    if initial_seconds <= 0:
        raise ValueError("Initial delay must be positive.")

    if attempt < 0:
        raise ValueError("Attempt cannot be negative.")

    if maximum_seconds <= 0:
        raise ValueError("Maximum delay must be positive.")

    if not 0 <= jitter_ratio <= 1:
        raise ValueError("Jitter ratio must be between 0 and 1.")

    delay = min(
        initial_seconds * (2 ** attempt),
        maximum_seconds,
    )

    if jitter_ratio == 0:
        return delay

    rng = random_source or random.Random()

    lower = delay * (1 - jitter_ratio)
    upper = delay * (1 + jitter_ratio)

    return min(rng.uniform(lower, upper), maximum_seconds)


rng = random.Random(42)

for attempt in range(5):
    print(
        f"Attempt {attempt}: "
        f"{exponential_backoff(1, attempt, 30, 0.2, rng):.3f}s"
    )


# =============================================================================
# 33. CIRCUIT BREAKER
# =============================================================================

print_section("33. CIRCUIT BREAKER")

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    """
    Minimal circuit breaker model.

    This is educational rather than production-ready.
    """

    failure_threshold: int = 3
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.consecutive_failures += 1

        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def allow_request(self) -> bool:
        return self.state != CircuitState.OPEN


breaker = CircuitBreaker(failure_threshold=3)

for _ in range(3):
    breaker.record_failure()
    print(
        "Failure recorded:",
        breaker.consecutive_failures,
        "state=",
        breaker.state.value,
    )

print("Request allowed:", breaker.allow_request())


# =============================================================================
# 34. GRACEFUL DEGRADATION
# =============================================================================

print_section("34. GRACEFUL DEGRADATION")

print(
    """
A system does not always have to be fully functional to remain available.

Examples:
    - Serve cached product information when the database is unavailable.
    - Disable recommendations while checkout remains functional.
    - Queue asynchronous work instead of failing immediately.
    - Return a reduced response rather than a complete failure.

This creates the concept of partial availability.

A good SLI should reflect what users actually consider successful.
"""
)


# =============================================================================
# 35. DEPENDENCY FAILURE CLASSIFICATION
# =============================================================================

print_section("35. DEPENDENCY FAILURE CLASSIFICATION")

class DependencyFailureMode(Enum):
    FAIL_FAST = "FAIL_FAST"
    RETRY = "RETRY"
    FALLBACK = "FALLBACK"
    CACHE = "CACHE"
    QUEUE = "QUEUE"


for mode in DependencyFailureMode:
    print(mode.value)


# =============================================================================
# 36. PARTIAL AVAILABILITY
# =============================================================================

print_section("36. PARTIAL AVAILABILITY")

@dataclass
class EndpointMeasurement:
    """Availability measurement for an endpoint."""

    endpoint: str
    total_requests: int
    successful_requests: int

    @property
    def availability(self) -> float:
        if self.total_requests <= 0:
            raise ValueError("Total requests must be positive.")

        if not 0 <= self.successful_requests <= self.total_requests:
            raise ValueError("Successful requests must be within range.")

        return self.successful_requests / self.total_requests


endpoint_measurements = [
    EndpointMeasurement("/login", 100_000, 99_990),
    EndpointMeasurement("/search", 500_000, 499_000),
    EndpointMeasurement("/checkout", 50_000, 49_990),
]

for measurement in endpoint_measurements:
    print(
        f"{measurement.endpoint:<12}"
        f"{measurement.availability * 100:.4f}%"
    )


# =============================================================================
# 37. WEIGHTED VS UNWEIGHTED SERVICE AVAILABILITY
# =============================================================================

print_section("37. WEIGHTED AGGREGATION")

print(
    """
Suppose:
    /search receives 1,000,000 requests
    /checkout receives 10,000 requests

A simple average of endpoint availability treats both endpoints equally.

A request-weighted SLI gives more influence to high-volume traffic.

The correct aggregation depends on what the SLO intends to represent.
"""
)


def weighted_average(
    values_and_weights: Iterable[tuple[float, float]],
) -> float:
    pairs = list(values_and_weights)

    if not pairs:
        raise ValueError("At least one value is required.")

    total_weight = sum(weight for _, weight in pairs)

    if total_weight <= 0:
        raise ValueError("Total weight must be positive.")

    return sum(value * weight for value, weight in pairs) / total_weight


weighted = weighted_average(
    [
        (0.999, 1_000_000),
        (0.9999, 10_000),
    ]
)

unweighted = mean([0.999, 0.9999])

print(f"Unweighted: {unweighted * 100:.5f}%")
print(f"Weighted:   {weighted * 100:.5f}%")


# =============================================================================
# 38. SCALING AND AVAILABILITY
# =============================================================================

print_section("38. SCALING AND AVAILABILITY")

print(
    """
Scaling can improve availability by reducing overload, but scaling alone is
not a complete availability strategy.

Potential bottlenecks include:
    - Database connections
    - CPU
    - Memory
    - Network bandwidth
    - File descriptors
    - Thread pools
    - Queues
    - External APIs
    - Storage IOPS
    - Rate limits

A horizontally scalable application can still fail if a non-scalable database
or dependency becomes the bottleneck.
"""


@dataclass
class CapacityModel:
    """Simple capacity model for educational purposes."""

    capacity_per_instance_rps: float
    instances: int
    traffic_rps: float
    target_utilization: float = 0.70

    @property
    def effective_capacity(self) -> float:
        return (
            self.capacity_per_instance_rps
            * self.instances
            * self.target_utilization
        )

    @property
    def overloaded(self) -> bool:
        return self.traffic_rps > self.effective_capacity


capacity = CapacityModel(
    capacity_per_instance_rps=500,
    instances=4,
    traffic_rps=1_200,
)

print("Effective capacity:", capacity.effective_capacity, "RPS")
print("Traffic:", capacity.traffic_rps, "RPS")
print("Overloaded:", capacity.overloaded)


# =============================================================================
# 39. HEALTH CHECKS
# =============================================================================

print_section("39. HEALTH CHECKS")

print(
    """
Health checks should distinguish between:

Liveness:
    Is the process alive?

Readiness:
    Can this instance safely receive traffic?

A process can be alive but unable to serve traffic because:
    - Database connectivity is broken
    - Required configuration is missing
    - Dependency is unavailable
    - It is still warming up
    - It is overloaded

Routing traffic to unhealthy instances can turn a local failure into a broader
availability incident.
"""


def liveness_check(process_running: bool) -> bool:
    return process_running


def readiness_check(
    process_running: bool,
    database_available: bool,
    initialization_complete: bool,
) -> bool:
    return (
        process_running
        and database_available
        and initialization_complete
    )


print("Liveness:", liveness_check(True))
print("Readiness:", readiness_check(True, False, True))


# =============================================================================
# 40. DEPLOYMENT AVAILABILITY
# =============================================================================

print_section("40. DEPLOYMENT STRATEGIES AND AVAILABILITY")

print(
    """
Deployment strategies affect availability risk.

Rolling deployment:
    Replace instances gradually.

Blue/green deployment:
    Maintain old and new environments and switch traffic.

Canary deployment:
    Expose a small portion of traffic to a new version before wider rollout.

A safe deployment strategy reduces blast radius and improves rollback speed.
"""
)


# =============================================================================
# 41. CANARY DECISION FUNCTION
# =============================================================================

print_section("41. CANARY VALIDATION")

@dataclass(frozen=True)
class CanaryMetrics:
    """Metrics used to make a simple canary decision."""

    availability: float
    error_rate: float
    p95_latency_ms: float


def canary_is_safe(
    metrics: CanaryMetrics,
    minimum_availability: float = 0.999,
    maximum_error_rate: float = 0.001,
    maximum_p95_latency_ms: float = 300,
) -> bool:
    return (
        metrics.availability >= minimum_availability
        and metrics.error_rate <= maximum_error_rate
        and metrics.p95_latency_ms <= maximum_p95_latency_ms
    )


canary = CanaryMetrics(
    availability=0.9995,
    error_rate=0.0005,
    p95_latency_ms=220,
)

print("Canary safe:", canary_is_safe(canary))


# =============================================================================
# 42. BURN RATE
# =============================================================================

print_section("42. ERROR-BUDGET BURN RATE")

print(
    """
Burn rate compares the rate at which error budget is being consumed with the
rate that would consume the entire budget exactly by the end of the SLO
window.

Interpretation:
    Burn rate = 1
        Budget is being consumed at the expected sustainable rate.

    Burn rate > 1
        Budget is being consumed too quickly.

    Burn rate >> 1
        The service is likely to exhaust its budget early.
"""


def burn_rate(
    observed_bad_fraction: float,
    allowed_bad_fraction: float,
) -> float:
    if not 0 <= observed_bad_fraction <= 1:
        raise ValueError("Observed bad fraction must be between 0 and 1.")

    if not 0 < allowed_bad_fraction <= 1:
        raise ValueError("Allowed bad fraction must be greater than zero.")

    return observed_bad_fraction / allowed_bad_fraction


slo = 0.999
allowed_bad_fraction = 1 - slo

for observed_error_rate in [0.0005, 0.001, 0.002, 0.01]:
    print(
        f"Observed error rate={observed_error_rate:.4%}, "
        f"burn rate={burn_rate(observed_error_rate, allowed_bad_fraction):.2f}x"
    )


# =============================================================================
# 43. MULTI-WINDOW BURN-RATE ALERTING
# =============================================================================

print_section("43. MULTI-WINDOW ALERTING")

@dataclass(frozen=True)
class BurnRateWindow:
    """Represent one burn-rate measurement window."""

    duration_minutes: int
    burn_rate: float


def severe_burn(
    windows: Sequence[BurnRateWindow],
    threshold: float,
) -> bool:
    """
    Require every supplied window to exceed the threshold.

    Real alert policies can use more sophisticated combinations.
    """
    if threshold <= 0:
        raise ValueError("Threshold must be positive.")

    if not windows:
        raise ValueError("At least one window is required.")

    return all(window.burn_rate >= threshold for window in windows)


windows = [
    BurnRateWindow(5, 20),
    BurnRateWindow(60, 15),
]

print("Severe burn:", severe_burn(windows, 10))


# =============================================================================
# 44. ALERT FATIGUE
# =============================================================================

print_section("44. ALERTING AND ALERT FATIGUE")

print(
    """
An availability monitoring system should not alert on every tiny fluctuation.

Poor alerting can create:
    - False positives
    - Alert fatigue
    - Ignored incidents
    - Operational overload

Useful alerts generally indicate actionable conditions.

Examples:
    - SLO burn is severe
    - Error budget is rapidly depleting
    - Customer-visible availability is below target
    - Critical dependency is failing
    - Capacity is approaching a dangerous limit
"""
)


# =============================================================================
# 45. SYNTHETIC MONITORING
# =============================================================================

print_section("45. SYNTHETIC MONITORING")

@dataclass
class SyntheticProbeResult:
    """Represent one synthetic availability probe."""

    timestamp: datetime
    successful: bool
    latency_ms: float
    region: str


probes = [
    SyntheticProbeResult(
        datetime(2026, 9, 1, 12, 0),
        True,
        100,
        "asia-south",
    ),
    SyntheticProbeResult(
        datetime(2026, 9, 1, 12, 1),
        False,
        3_000,
        "asia-south",
    ),
    SyntheticProbeResult(
        datetime(2026, 9, 1, 12, 2),
        True,
        120,
        "asia-south",
    ),
]

synthetic_availability = sum(
    probe.successful for probe in probes
) / len(probes)

print(
    "Synthetic availability:",
    f"{synthetic_availability * 100:.2f}%"
)


# =============================================================================
# 46. REGION-SPECIFIC AVAILABILITY
# =============================================================================

print_section("46. REGIONAL AVAILABILITY")

@dataclass(frozen=True)
class RegionalSLI:
    region: str
    availability: float
    request_count: int


regional_slis = [
    RegionalSLI("India", 0.9995, 500_000),
    RegionalSLI("Europe", 0.9999, 300_000),
    RegionalSLI("North America", 0.9985, 200_000),
]

global_availability = weighted_average(
    (item.availability, item.request_count)
    for item in regional_slis
)

print("Global weighted availability:",
      f"{global_availability * 100:.5f}%")

for item in regional_slis:
    print(
        f"{item.region:<18}"
        f"{item.availability * 100:.4f}%"
    )


# =============================================================================
# 47. AVAILABILITY ZONES AND REGIONS
# =============================================================================

print_section("47. FAILURE DOMAINS")

print(
    """
A failure domain is a group of infrastructure that can fail together.

Typical hierarchy:
    Process
        -> Host
            -> Rack
                -> Availability Zone
                    -> Region
                        -> Provider

High availability designs try to avoid placing all redundancy inside the same
failure domain.

Examples:
    Two replicas on one host provide little host-level resilience.
    Two replicas on separate hosts are stronger.
    Replicas across zones protect against zone-level failures.
    Multi-region deployments can protect against regional failures.

The larger the failure domain being protected against, the greater the
operational and financial complexity can become.
"""
)


# =============================================================================
# 48. DATABASE AVAILABILITY
# =============================================================================

print_section("48. DATABASE AVAILABILITY")

print(
    """
Database availability is often a critical constraint because application
servers can be replicated more easily than stateful storage.

Common techniques:
    - Primary/replica architecture
    - Synchronous replication
    - Asynchronous replication
    - Automatic failover
    - Backups
    - Point-in-time recovery
    - Read replicas
    - Sharding
    - Multi-zone placement

Important distinction:

Replication improves availability and durability in different ways, but they
are not identical properties.

A replicated system can still lose data or become unavailable if replication,
failover, quorum, networking, or shared dependencies fail.
"""
)


# =============================================================================
# 49. QUORUM
# =============================================================================

print_section("49. QUORUM AND AVAILABILITY")

def quorum_required(
    replicas: int,
    required_votes: int,
) -> bool:
    """Validate a quorum configuration."""
    if replicas <= 0:
        raise ValueError("Replicas must be positive.")

    if not 1 <= required_votes <= replicas:
        raise ValueError("Required votes must be within replica count.")

    return required_votes > replicas / 2


for replicas in [3, 5]:
    for votes in [2, 3]:
        if votes <= replicas:
            print(
                f"{replicas} replicas, {votes} votes -> "
                f"majority={quorum_required(replicas, votes)}"
            )


# =============================================================================
# 50. CAP-STYLE TRADE-OFF DISCUSSION
# =============================================================================

print_section("50. AVAILABILITY TRADE-OFFS IN DISTRIBUTED SYSTEMS")

print(
    """
Distributed systems frequently face trade-offs involving:
    - Consistency
    - Availability
    - Partition tolerance

During a network partition, a distributed system may have to choose behavior
that favors continued service or stronger consistency.

This does not mean a production system simply chooses one permanent label such
as "available" or "consistent." Real architectures define behavior for
specific operations and failure conditions.

Examples:
    - Reads may continue from replicas.
    - Writes may require quorum.
    - Some features may degrade.
    - Stale data may be acceptable for some use cases.
    - Financial operations may require stricter guarantees.
"""
)


# =============================================================================
# 51. DATA CENTER / REGION FAILOVER
# =============================================================================

print_section("51. FAILOVER")

@dataclass
class Region:
    """Simple regional failover model."""

    name: str
    available: bool
    capacity_rps: float


def total_available_capacity(regions: Sequence[Region]) -> float:
    return sum(
        region.capacity_rps
        for region in regions
        if region.available
    )


regions = [
    Region("Region-A", True, 10_000),
    Region("Region-B", True, 10_000),
    Region("Region-C", False, 10_000),
]

print(
    "Available capacity:",
    total_available_capacity(regions),
    "RPS"
)


# =============================================================================
# 52. FAILOVER PITFALLS
# =============================================================================

print_section("52. FAILOVER PITFALLS")

print(
    """
Failover can fail because:
    - Health checks are incorrect.
    - DNS caches old records.
    - The standby lacks capacity.
    - Replication lag is too high.
    - Configuration differs.
    - Secrets are unavailable.
    - Database promotion fails.
    - Clients cannot reach the backup region.
    - Automation itself depends on the failed region.
    - Failover has never been tested.

A failover design should therefore be validated through controlled testing.
"""
)


# =============================================================================
# 53. CHAOS AND FAILURE TESTING
# =============================================================================

print_section("53. FAILURE TESTING")

@dataclass(frozen=True)
class FailureScenario:
    name: str
    expected_recovery_seconds: int


failure_scenarios = [
    FailureScenario("Single API instance failure", 30),
    FailureScenario("Database primary failure", 60),
    FailureScenario("Availability-zone failure", 300),
    FailureScenario("External dependency timeout", 10),
]

for scenario in failure_scenarios:
    print(
        f"{scenario.name:<35} "
        f"expected recovery <= {scenario.expected_recovery_seconds}s"
    )


# =============================================================================
# 54. AVAILABILITY TESTING STRATEGY
# =============================================================================

print_section("54. TESTING AVAILABILITY")

print(
    """
Availability testing should include more than unit tests.

Useful test categories:
    - Health-check tests
    - Failover tests
    - Dependency failure tests
    - Load tests
    - Capacity tests
    - Deployment rollback tests
    - Network partition tests
    - Database failure tests
    - Recovery tests
    - Disaster recovery tests
    - Synthetic monitoring validation

A recovery mechanism that has never been exercised is an assumption rather
than demonstrated resilience.
"""
)


# =============================================================================
# 55. RTO AND RPO
# =============================================================================

print_section("55. RTO AND RPO")

print(
    """
RTO = Recovery Time Objective

    Maximum targeted time to restore service after a disruptive event.

RPO = Recovery Point Objective

    Maximum acceptable amount of data loss measured in time.

Example:
    RTO = 15 minutes
    RPO = 5 minutes

This means the organization targets service restoration within 15 minutes and
accepts at most approximately five minutes of data loss under the defined
recovery strategy.

RTO/RPO are related to availability and disaster recovery, but they are not
the same as an SLA, SLO, or SLI.
"""
)


# =============================================================================
# 56. AVAILABILITY VS DURABILITY
# =============================================================================

print_section("56. AVAILABILITY VS DURABILITY")

print(
    """
Availability:
    Can I use the service/data now?

Durability:
    Will my stored data survive failures?

A storage system can preserve data perfectly but be temporarily unavailable.

Conversely, a service can remain reachable while data is lost or corrupted.

System design should treat these as separate properties.
"""
)


# =============================================================================
# 57. AVAILABILITY VS PERFORMANCE
# =============================================================================

print_section("57. AVAILABILITY VS PERFORMANCE")

print(
    """
A service can be:
    - Available and fast
    - Available and slow
    - Unavailable
    - Technically reachable but functionally unusable

Therefore availability and latency should generally be measured separately.

For example:
    Availability SLO: 99.9%
    Latency SLO: 99% of requests under 300 ms
"""
)


# =============================================================================
# 58. TAIL LATENCY
# =============================================================================

print_section("58. TAIL LATENCY AND AVAILABILITY")

print(
    """
Average latency can hide severe user experiences.

Percentiles are commonly used:
    p50 = median
    p90 = 90th percentile
    p95 = 95th percentile
    p99 = 99th percentile
    p99.9 = 99.9th percentile

A request can be technically successful while taking so long that the user
experiences it as a failure.

The exact SLI should reflect the service contract and user experience.
"""
)


# =============================================================================
# 59. SIMPLE PERCENTILE
# =============================================================================

print_section("59. PERCENTILE IMPLEMENTATION")


def percentile(values: Sequence[float], p: float) -> float:
    """Calculate a simple linear-interpolation percentile."""
    if not values:
        raise ValueError("Values cannot be empty.")

    if not 0 <= p <= 100:
        raise ValueError("Percentile must be between 0 and 100.")

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * p / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower

    return (
        ordered[lower]
        + (ordered[upper] - ordered[lower]) * fraction
    )


latencies = [50, 70, 80, 90, 100, 110, 150, 200, 500, 1_000]

for p in [50, 90, 95, 99]:
    print(f"p{p}: {percentile(latencies, p):.2f} ms")


# =============================================================================
# 60. OBSERVABILITY
# =============================================================================

print_section("60. OBSERVABILITY FOR AVAILABILITY")

print(
    """
Availability engineering depends on observability.

Three commonly discussed pillars are:
    - Metrics
    - Logs
    - Traces

Useful availability metrics include:
    - Request count
    - Success count
    - Error count
    - Error rate
    - Latency
    - Saturation
    - Queue depth
    - Dependency errors
    - Availability by region
    - Availability by endpoint

Logs explain individual events.

Traces show how one request moves across services.

Metrics are especially useful for long-term SLO calculations and alerting.
"""
)


# =============================================================================
# 61. SLI RECORDING
# =============================================================================

print_section("61. SLI RECORDER")

@dataclass
class SLIRecorder:
    """Collect successful and total events."""

    good_events: int = 0
    total_events: int = 0

    def record(self, good: bool) -> None:
        self.total_events += 1

        if good:
            self.good_events += 1

    @property
    def sli(self) -> float:
        if self.total_events == 0:
            raise ValueError("No events recorded.")

        return self.good_events / self.total_events


recorder = SLIRecorder()

for outcome in [True, True, False, True, True, False, True]:
    recorder.record(outcome)

print("Good:", recorder.good_events)
print("Total:", recorder.total_events)
print("SLI:", f"{recorder.sli * 100:.2f}%")


# =============================================================================
# 62. WINDOWED SLI
# =============================================================================

print_section("62. WINDOWED SLI")

@dataclass
class TimeWindow:
    """A measurement window."""

    start: datetime
    end: datetime

    def duration_seconds(self) -> float:
        if self.end < self.start:
            raise ValueError("Window end cannot precede start.")

        return (self.end - self.start).total_seconds()


window = TimeWindow(
    datetime(2026, 9, 1),
    datetime(2026, 10, 1),
)

print("Window duration:", format_duration(window.duration_seconds()))


# =============================================================================
# 63. ROLLING WINDOWS
# =============================================================================

print_section("63. ROLLING WINDOWS VS CALENDAR WINDOWS")

print(
    """
Calendar window:
    Example: September 1 through September 30.

Rolling window:
    Example: the previous 30 days from the current moment.

Calendar windows are easy to communicate.

Rolling windows can provide more continuous measurement but can be more complex
to reason about operationally.

The SLO definition should state exactly which window is used.
"""
)


# =============================================================================
# 64. AVAILABILITY CALCULATOR
# =============================================================================

print_section("64. REUSABLE AVAILABILITY CALCULATOR")

@dataclass
class AvailabilityMeasurement:
    """Represent one measured availability period."""

    total_seconds: float
    downtime_seconds: float

    @property
    def uptime_seconds(self) -> float:
        if self.total_seconds < 0:
            raise ValueError("Total time cannot be negative.")

        if self.downtime_seconds < 0:
            raise ValueError("Downtime cannot be negative.")

        if self.downtime_seconds > self.total_seconds:
            raise ValueError("Downtime cannot exceed total time.")

        return self.total_seconds - self.downtime_seconds

    @property
    def availability(self) -> float:
        if self.total_seconds == 0:
            raise ValueError("Total time must be positive.")

        return self.uptime_seconds / self.total_seconds


measurement = AvailabilityMeasurement(
    total_seconds=30 * 24 * 60 * 60,
    downtime_seconds=13 * 60,
)

print("Uptime:", format_duration(measurement.uptime_seconds))
print("Downtime:", format_duration(measurement.downtime_seconds))
print("Availability:", f"{measurement.availability * 100:.6f}%")


# =============================================================================
# 65. SLA BREACH DETECTION
# =============================================================================

print_section("65. SLA BREACH DETECTION")

@dataclass
class SLAResult:
    target: float
    actual: float

    @property
    def breached(self) -> bool:
        return self.actual < self.target

    @property
    def difference_percentage_points(self) -> float:
        return (self.actual - self.target) * 100


sla_result = SLAResult(
    target=0.999,
    actual=0.9985,
)

print("Target:", f"{sla_result.target * 100:.4f}%")
print("Actual:", f"{sla_result.actual * 100:.4f}%")
print("Breach:", sla_result.breached)
print(
    "Difference:",
    f"{sla_result.difference_percentage_points:.4f} percentage points"
)


# =============================================================================
# 66. SLA VS SLO NUMERICAL DISTINCTION
# =============================================================================

print_section("66. SLA AND SLO CAN HAVE DIFFERENT TARGETS")

print(
    """
A company may define:

    Internal SLO = 99.95%
    External SLA = 99.9%

The internal target is stricter than the contractual commitment.

This creates operational headroom before the organization reaches the
contractual boundary.

The relationship depends on business requirements and contractual terms.
"""
)


# =============================================================================
# 67. AVAILABILITY BUDGET PLANNING
# =============================================================================

print_section("67. AVAILABILITY BUDGET PLANNING")


@dataclass(frozen=True)
class AvailabilityTarget:
    name: str
    target: float

    def monthly_budget_minutes(self, days: int = 30) -> float:
        seconds = days * 24 * 60 * 60
        return downtime_budget(seconds, self.target) / 60


availability_targets = [
    AvailabilityTarget("99%", 0.99),
    AvailabilityTarget("99.9%", 0.999),
    AvailabilityTarget("99.99%", 0.9999),
    AvailabilityTarget("99.999%", 0.99999),
]

for item in availability_targets:
    print(
        f"{item.name:<10} "
        f"{item.monthly_budget_minutes():.3f} minutes/month"
    )


# =============================================================================
# 68. THE COST OF NINES
# =============================================================================

print_section("68. COST OF ADDITIONAL NINES")

print(
    """
Moving from 99% to 99.9% does not represent a simple 0.9% improvement in
unavailability.

Unavailability changes from:

    1%  -> 0.1%

That is a 10x reduction in allowed unavailability.

Similarly:

    99.9% -> 99.99%

reduces allowed unavailability by another factor of 10.

Each additional nine generally requires more engineering effort, redundancy,
testing, monitoring, operational maturity, and often higher infrastructure
cost.
"""
)


# =============================================================================
# 69. AVAILABILITY REQUIREMENT BY BUSINESS FUNCTION
# =============================================================================

print_section("69. DIFFERENT SERVICES CAN HAVE DIFFERENT SLOs")

print(
    """
Not every component needs the same availability target.

Example:
    Marketing content: 99.0%
    Search:             99.9%
    Payments:           99.99%
    Internal analytics: 98.0%

The correct target depends on:
    - Customer impact
    - Revenue impact
    - Safety
    - Regulatory requirements
    - Recovery alternatives
    - Cost
    - Business criticality
"""
)


# =============================================================================
# 70. AVAILABILITY AND BUSINESS IMPACT
# =============================================================================

print_section("70. AVAILABILITY IS A BUSINESS PROPERTY")

print(
    """
A technically impressive availability target may be economically irrational.

Suppose improving availability from 99.99% to 99.999% requires:
    - More regions
    - More replicas
    - More operational staffing
    - More complex deployment
    - Higher testing costs
    - Higher data-transfer costs

The benefit should be evaluated against customer and business impact.

System design is therefore a trade-off among reliability, complexity, cost,
performance, consistency, and operational burden.
"""
)


# =============================================================================
# 71. AVAILABILITY ANTI-PATTERNS
# =============================================================================

print_section("71. COMMON AVAILABILITY ANTI-PATTERNS")

anti_patterns = [
    "Monitoring only ping or TCP reachability",
    "Ignoring HTTP/application-level failures",
    "Using averages that hide tail behavior",
    "Excluding too much traffic from the denominator",
    "Counting overlapping incidents twice",
    "Assuming replicas are independent",
    "Using retries without backoff or limits",
    "Failing open without considering safety",
    "Failing closed without considering availability",
    "Deploying globally without rollback capability",
    "Relying on untested failover",
    "Alerting on every small fluctuation",
    "Using a single region for a critical workload",
    "Treating uptime as equivalent to user success",
]

for number, anti_pattern in enumerate(anti_patterns, start=1):
    print(f"{number:02d}. {anti_pattern}")


# =============================================================================
# 72. BEST PRACTICES
# =============================================================================

print_section("72. AVAILABILITY BEST PRACTICES")

best_practices = [
    "Define customer-oriented SLIs.",
    "Make SLOs measurable and explicit.",
    "Keep contractual SLA rules separate from internal SLOs.",
    "Track error budgets continuously.",
    "Measure availability at the application level.",
    "Separate availability from latency and correctness.",
    "Use redundancy across meaningful failure domains.",
    "Automate health checks and failover where appropriate.",
    "Test failover instead of merely documenting it.",
    "Use controlled deployments and rapid rollback.",
    "Use bounded retries with backoff and jitter.",
    "Protect dependencies with timeouts and circuit breakers.",
    "Plan capacity before saturation occurs.",
    "Monitor by endpoint, region, customer path, and dependency.",
    "Calculate downtime intervals correctly.",
    "Design graceful degradation for non-critical features.",
    "Keep incident response and recovery procedures current.",
]

for number, practice in enumerate(best_practices, start=1):
    print(f"{number:02d}. {practice}")


# =============================================================================
# 73. SECURITY AND AVAILABILITY
# =============================================================================

print_section("73. SECURITY CONSIDERATIONS")

print(
    """
Security failures can directly affect availability.

Examples:
    - DDoS attacks
    - Credential compromise
    - Ransomware
    - Malicious configuration changes
    - Supply-chain compromise
    - Resource exhaustion
    - Unauthorized deletion
    - Abuse of public APIs

Availability architecture should therefore include:
    - Rate limiting
    - Authentication and authorization
    - Network controls
    - Resource quotas
    - Backups
    - Recovery procedures
    - Auditability
    - Secrets management
    - Safe administrative access

Security controls themselves can also affect availability if they are
misconfigured or depend on a failed external service.
"""
)


# =============================================================================
# 74. RATE LIMITING
# =============================================================================

print_section("74. RATE LIMITING")

@dataclass
class RateLimiter:
    """Simple fixed-window rate limiter."""

    limit: int
    window_seconds: int
    request_count: int = 0
    window_started_at: float = 0.0

    def allow(self, now: float) -> bool:
        if self.limit <= 0:
            raise ValueError("Limit must be positive.")

        if self.window_seconds <= 0:
            raise ValueError("Window must be positive.")

        if now - self.window_started_at >= self.window_seconds:
            self.window_started_at = now
            self.request_count = 0

        if self.request_count >= self.limit:
            return False

        self.request_count += 1
        return True


limiter = RateLimiter(limit=3, window_seconds=60)

for request_number in range(1, 6):
    print(
        f"Request {request_number}: "
        f"allowed={limiter.allow(10)}"
    )


# =============================================================================
# 75. AVAILABILITY AND BACKPRESSURE
# =============================================================================

print_section("75. BACKPRESSURE")

print(
    """
Backpressure prevents a system from accepting unlimited work when capacity is
insufficient.

Possible responses:
    - Queue work
    - Reject excess traffic
    - Rate-limit clients
    - Shed non-critical load
    - Prioritize critical operations

Returning an explicit controlled failure can preserve availability for
important traffic instead of allowing the entire system to collapse.
"""
)


# =============================================================================
# 76. LOAD SHEDDING
# =============================================================================

print_section("76. LOAD SHEDDING")

@dataclass(frozen=True)
class RequestClass:
    name: str
    priority: int


request_classes = [
    RequestClass("Payment", 100),
    RequestClass("Checkout", 90),
    RequestClass("Search", 60),
    RequestClass("Recommendations", 30),
]

sorted_classes = sorted(
    request_classes,
    key=lambda item: item.priority,
    reverse=True,
)

for request_class in sorted_classes:
    print(
        f"{request_class.name:<20} priority={request_class.priority}"
    )


# =============================================================================
# 77. DEPENDENCY BUDGETING
# =============================================================================

print_section("77. DEPENDENCY AVAILABILITY")

print(
    """
If a service depends on an external service, the dependency's availability
can constrain the caller's availability.

For example:

    Application -> Payment API

If payment authorization is required for checkout, payment dependency
availability directly affects checkout availability.

A strong design defines:
    - Timeout
    - Retry policy
    - Fallback behavior
    - Circuit breaking
    - Dependency SLO
    - Failure classification
    - Customer-visible behavior
"""
)


# =============================================================================
# 78. AVAILABILITY BUDGET ALLOCATION
# =============================================================================

print_section("78. AVAILABILITY BUDGET ALLOCATION")

print(
    """
Suppose an end-to-end system has an availability target of 99.9%.

The team can reason about how much reliability each major component needs.

This is not always as simple as dividing the percentage equally because
component dependencies may be serial, redundant, or conditionally required.

Availability budgeting is an architecture exercise, not merely arithmetic.
"""
)


# =============================================================================
# 79. END-TO-END AVAILABILITY
# =============================================================================

print_section("79. END-TO-END AVAILABILITY")

@dataclass
class UserJourney:
    """Represent required components in a customer journey."""

    name: str
    components: list[Component]

    def availability(self) -> float:
        return serial_availability(self.components)


checkout = UserJourney(
    name="Checkout",
    components=[
        Component("Web", 0.9999),
        Component("Order API", 0.9995),
        Component("Database", 0.999),
        Component("Payment", 0.9995),
    ],
)

print(
    f"{checkout.name} estimated availability:",
    f"{checkout.availability() * 100:.6f}%"
)


# =============================================================================
# 80. WHY END-TO-END AVAILABILITY IS LOWER
# =============================================================================

print_section("80. SERIAL DEPENDENCY EFFECT")

print(
    """
Even highly available components can produce a significantly lower end-to-end
availability when many components are required.

This is why distributed system architecture should minimize unnecessary
synchronous dependencies in critical user paths.

Moving non-critical work to asynchronous processing can reduce the number of
components that must be simultaneously healthy.
"""
)


# =============================================================================
# 81. SYNCHRONOUS VS ASYNCHRONOUS DEPENDENCIES
# =============================================================================

print_section("81. SYNCHRONOUS VS ASYNCHRONOUS")

print(
    """
Synchronous dependency:
    The caller waits for the dependency before completing the operation.

Asynchronous dependency:
    Work is accepted and processed later, usually through a queue or event
    mechanism.

Asynchronous designs can improve availability for workflows where immediate
completion is unnecessary.

Trade-offs include:
    - Eventual consistency
    - More complex state management
    - Duplicate messages
    - Ordering concerns
    - Retry handling
    - Monitoring complexity
"""
)


# =============================================================================
# 82. IDEMPOTENCY
# =============================================================================

print_section("82. IDEMPOTENCY AND RETRIES")

print(
    """
Retries are safer when operations are idempotent.

An idempotent operation can be repeated without changing the final intended
result beyond the effect of the first successful operation.

Example:
    Setting account status to ACTIVE is naturally idempotent.

Potentially non-idempotent:
    Charge a credit card $100.

Payment systems therefore often use idempotency keys or equivalent mechanisms
to avoid duplicate side effects caused by retries.
"""


@dataclass
class IdempotencyStore:
    """Minimal educational idempotency-key store."""

    results: dict[str, str] = field(default_factory=dict)

    def execute_once(
        self,
        key: str,
        operation: Callable[[], str],
    ) -> str:
        if not key:
            raise ValueError("Idempotency key cannot be empty.")

        if key in self.results:
            return self.results[key]

        result = operation()
        self.results[key] = result
        return result


store = IdempotencyStore()
execution_count = {"value": 0}


def charge_operation() -> str:
    execution_count["value"] += 1
    return "payment-created"


first = store.execute_once("payment-123", charge_operation)
second = store.execute_once("payment-123", charge_operation)

print("First result:", first)
print("Second result:", second)
print("Actual operation executions:", execution_count["value"])


# =============================================================================
# 83. TIMEOUT BUDGET
# =============================================================================

print_section("83. END-TO-END TIMEOUT BUDGET")

print(
    """
An end-to-end request deadline should be considered separately from individual
timeouts.

Example:
    User request deadline = 2 seconds

A service cannot safely spend:
    2 seconds on database
    + 2 seconds on payment
    + 2 seconds on cache

The total exceeds the user-visible deadline.

Timeouts should be coordinated across call chains.
"""
)


# =============================================================================
# 84. AVAILABILITY AND QUEUES
# =============================================================================

print_section("84. QUEUES AND AVAILABILITY")

@dataclass
class QueueState:
    """Simple queue capacity model."""

    queue_depth: int
    maximum_depth: int

    def healthy(self) -> bool:
        return (
            self.maximum_depth > 0
            and 0 <= self.queue_depth <= self.maximum_depth
        )

    def utilization(self) -> float:
        if self.maximum_depth <= 0:
            raise ValueError("Maximum queue depth must be positive.")

        return self.queue_depth / self.maximum_depth


queue = QueueState(
    queue_depth=7_000,
    maximum_depth=10_000,
)

print("Queue healthy:", queue.healthy())
print("Queue utilization:", f"{queue.utilization() * 100:.1f}%")


# =============================================================================
# 85. AVAILABILITY AND DATA CONSISTENCY
# =============================================================================

print_section("85. AVAILABILITY AND CONSISTENCY")

print(
    """
Serving stale cached data can preserve availability while weakening freshness.

For some use cases:
    stale product catalog = acceptable

For others:
    stale bank balance = potentially unacceptable

Therefore the availability design must be tied to business semantics.
"""
)


# =============================================================================
# 86. CUSTOMER-PERCEIVED AVAILABILITY
# =============================================================================

print_section("86. CUSTOMER-PERCEIVED AVAILABILITY")

print(
    """
Technical availability and customer-perceived availability can differ.

Examples:
    - DNS works, but login fails.
    - API returns 200, but the response is incorrect.
    - Homepage works, but checkout is broken.
    - Service responds, but p99 latency makes it unusable.

A mature SLO system therefore measures important user journeys and critical
operations, not only infrastructure health.
"""
)


# =============================================================================
# 87. USER JOURNEY SLI
# =============================================================================

print_section("87. USER JOURNEY SLI")

@dataclass(frozen=True)
class UserJourneyResult:
    journey: str
    total_attempts: int
    successful_attempts: int

    @property
    def availability(self) -> float:
        if self.total_attempts <= 0:
            raise ValueError("Total attempts must be positive.")

        if not 0 <= self.successful_attempts <= self.total_attempts:
            raise ValueError("Successful attempts out of range.")

        return self.successful_attempts / self.total_attempts


checkout_journey = UserJourneyResult(
    journey="Checkout",
    total_attempts=100_000,
    successful_attempts=99_950,
)

print(
    f"{checkout_journey.journey}: "
    f"{checkout_journey.availability * 100:.4f}%"
)


# =============================================================================
# 88. SLO DESIGN CHECKLIST
# =============================================================================

print_section("88. SLO DESIGN CHECKLIST")

slo_checklist = [
    "Is the SLI clearly defined?",
    "Is the denominator explicit?",
    "Is customer impact represented?",
    "Is the measurement window explicit?",
    "Are exclusions documented?",
    "Is the target realistic?",
    "Is the target meaningful?",
    "Can the metric be collected reliably?",
    "Can the team act when the budget is consumed?",
    "Does the SLO distinguish availability from latency and correctness?",
]

for item in slo_checklist:
    print("[ ]", item)


# =============================================================================
# 89. SLA DESIGN CHECKLIST
# =============================================================================

print_section("89. SLA DESIGN CHECKLIST")

sla_checklist = [
    "Target percentage is explicitly stated.",
    "Measurement period is defined.",
    "Measurement methodology is defined.",
    "Maintenance policy is defined.",
    "Exclusions are defined.",
    "Customer eligibility is defined.",
    "Service-credit policy is defined where applicable.",
    "Reporting process is defined.",
    "Time synchronization and data sources are understood.",
]

for item in sla_checklist:
    print("[ ]", item)


# =============================================================================
# 90. COMMON MISTAKES
# =============================================================================

print_section("90. COMMON MISTAKES")

mistakes = {
    "Mistake 1": "Treating uptime as the same thing as successful user operations.",
    "Mistake 2": "Using a vague SLI such as 'server health'.",
    "Mistake 3": "Not defining which requests are valid.",
    "Mistake 4": "Ignoring partial outages.",
    "Mistake 5": "Assuming redundancy means independent failure domains.",
    "Mistake 6": "Ignoring maintenance policy.",
    "Mistake 7": "Counting overlapping downtime twice.",
    "Mistake 8": "Using retries without deadlines.",
    "Mistake 9": "Setting an unrealistic availability target.",
    "Mistake 10": "Measuring availability without an actionable response plan.",
}

for name, description in mistakes.items():
    print(f"{name}: {description}")


# =============================================================================
# 91. AVAILABILITY REVIEW EXAMPLE
# =============================================================================

print_section("91. SYSTEM DESIGN AVAILABILITY REVIEW")

@dataclass
class AvailabilityReview:
    service_name: str
    sli_name: str
    slo: float
    current_sli: float
    error_budget_remaining_fraction: float

    @property
    def compliant(self) -> bool:
        return self.current_sli >= self.slo

    @property
    def budget_status(self) -> str:
        if self.error_budget_remaining_fraction <= 0:
            return "EXHAUSTED"

        if self.error_budget_remaining_fraction < 0.10:
            return "CRITICAL"

        if self.error_budget_remaining_fraction < 0.25:
            return "LOW"

        return "HEALTHY"


review = AvailabilityReview(
    service_name="Checkout API",
    sli_name="successful checkout attempts / valid checkout attempts",
    slo=0.999,
    current_sli=0.9992,
    error_budget_remaining_fraction=0.35,
)

print("Service:", review.service_name)
print("SLI:", review.sli_name)
print("SLO:", f"{review.slo * 100:.3f}%")
print("Current:", f"{review.current_sli * 100:.3f}%")
print("Compliant:", review.compliant)
print("Budget status:", review.budget_status)


# =============================================================================
# 92. PRODUCTION READINESS CHECK
# =============================================================================

print_section("92. PRODUCTION READINESS")

production_requirements = [
    "Customer-oriented availability SLI exists.",
    "SLO is documented.",
    "SLA requirements are understood.",
    "Error budget is calculated.",
    "Monitoring is available.",
    "SLO alerts are actionable.",
    "Health checks are implemented.",
    "Timeouts are bounded.",
    "Retries are controlled.",
    "Critical dependencies have failure handling.",
    "Capacity has safety margin.",
    "Deployments support rollback.",
    "Backups are tested.",
    "Failover has been exercised.",
    "Incident response procedures exist.",
    "Critical user journeys are monitored.",
]

for requirement in production_requirements:
    print("[ ]", requirement)


# =============================================================================
# 93. INTEGRATED AVAILABILITY MODEL
# =============================================================================

print_section("93. INTEGRATED AVAILABILITY MODEL")


@dataclass
class ServiceAvailabilityModel:
    """
    Integrate several concepts into one educational model.
    """

    service_name: str
    slo: float
    total_requests: int
    successful_requests: int
    total_time_seconds: float
    downtime_seconds: float

    def request_sli(self) -> float:
        if self.total_requests <= 0:
            raise ValueError("Total requests must be positive.")

        if not 0 <= self.successful_requests <= self.total_requests:
            raise ValueError("Successful requests out of range.")

        return self.successful_requests / self.total_requests

    def time_availability(self) -> float:
        return availability_from_time(
            self.total_time_seconds,
            self.downtime_seconds,
        )

    def meets_request_slo(self) -> bool:
        return self.request_sli() >= self.slo

    def error_budget_requests(self) -> float:
        return self.total_requests * (1 - self.slo)


integrated = ServiceAvailabilityModel(
    service_name="Order API",
    slo=0.999,
    total_requests=5_000_000,
    successful_requests=4_996_000,
    total_time_seconds=30 * 24 * 60 * 60,
    downtime_seconds=20 * 60,
)

print("Service:", integrated.service_name)
print("Request SLI:", f"{integrated.request_sli() * 100:.5f}%")
print("Time availability:",
      f"{integrated.time_availability() * 100:.5f}%")
print("Request SLO met:", integrated.meets_request_slo())
print(
    "Allowed bad requests:",
    f"{integrated.error_budget_requests():.0f}",
)


# =============================================================================
# 94. UNIT TESTS
# =============================================================================

print_section("94. BUILT-IN TESTS")


class AvailabilityTests(unittest.TestCase):
    """Tests for the core availability functions."""

    def test_perfect_availability(self) -> None:
        self.assertEqual(
            availability_from_time(100, 0),
            1.0,
        )

    def test_zero_availability(self) -> None:
        self.assertEqual(
            availability_from_time(100, 100),
            0.0,
        )

    def test_half_availability(self) -> None:
        self.assertEqual(
            availability_from_time(100, 50),
            0.5,
        )

    def test_invalid_total_time(self) -> None:
        with self.assertRaises(ValueError):
            availability_from_time(0, 0)

    def test_downtime_cannot_exceed_total(self) -> None:
        with self.assertRaises(ValueError):
            availability_from_time(10, 11)

    def test_request_sli(self) -> None:
        requests = [
            Request(200, 10),
            Request(200, 20),
            Request(500, 30),
        ]

        self.assertAlmostEqual(
            request_availability_sli(requests),
            2 / 3,
        )

    def test_serial_availability(self) -> None:
        components = [
            Component("A", 0.9),
            Component("B", 0.8),
        ]

        self.assertAlmostEqual(
            serial_availability(components),
            0.72,
        )

    def test_redundancy(self) -> None:
        self.assertAlmostEqual(
            redundant_availability(0.9, 2),
            0.99,
        )

    def test_interval_merge(self) -> None:
        intervals = [
            (
                datetime(2026, 1, 1, 10, 0),
                datetime(2026, 1, 1, 10, 20),
            ),
            (
                datetime(2026, 1, 1, 10, 10),
                datetime(2026, 1, 1, 10, 30),
            ),
        ]

        merged = merge_intervals(intervals)

        self.assertEqual(len(merged), 1)

    def test_error_rate(self) -> None:
        self.assertAlmostEqual(
            error_rate(100, 1),
            0.01,
        )

    def test_error_budget(self) -> None:
        budget = ErrorBudget(
            slo=0.99,
            eligible_events=10_000,
            bad_events=50,
        )

        self.assertEqual(
            budget.allowed_bad_events,
            100,
        )

        self.assertTrue(budget.within_budget)


test_result = unittest.TextTestRunner(
    verbosity=1,
).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(
        AvailabilityTests
    )
)

print(
    f"Tests run: {test_result.testsRun}, "
    f"failures: {len(test_result.failures)}, "
    f"errors: {len(test_result.errors)}"
)


# =============================================================================
# 95. PRACTICAL EXERCISE SIMULATION
# =============================================================================

print_section("95. AVAILABILITY SIMULATION")

print(
    """
The following simulation creates random request outcomes and estimates the
observed availability.

Random simulation is useful for understanding how measured availability
changes with sample size and failure probability.
"""


def simulate_requests(
    number_of_requests: int,
    failure_probability: float,
    random_source: Optional[random.Random] = None,
) -> float:
    if number_of_requests <= 0:
        raise ValueError("Number of requests must be positive.")

    if not 0 <= failure_probability <= 1:
        raise ValueError("Failure probability must be between 0 and 1.")

    rng = random_source or random.Random()

    successes = sum(
        rng.random() >= failure_probability
        for _ in range(number_of_requests)
    )

    return successes / number_of_requests


simulation_rng = random.Random(123)

for request_count in [100, 1_000, 10_000]:
    simulated = simulate_requests(
        request_count,
        failure_probability=0.001,
        random_source=simulation_rng,
    )

    print(
        f"{request_count:>6} requests -> "
        f"{simulated * 100:.4f}% observed availability"
    )


# =============================================================================
# 96. STATISTICAL INTERPRETATION
# =============================================================================

print_section("96. MEASUREMENT UNCERTAINTY")

print(
    """
An observed availability percentage is an estimate based on observed events.

For small samples, a few failures can cause a large percentage change.

Example:
    1 failure out of 100 requests = 99%
    1 failure out of 10,000 requests = 99.99%

Therefore:
    - Sample size matters.
    - Measurement windows matter.
    - Traffic distribution matters.
    - Rare failures may not appear in small samples.

SLO systems should use enough traffic or time to make measurements meaningful.
"""
)


# =============================================================================
# 97. AVAILABILITY AND INCIDENT RESPONSE
# =============================================================================

print_section("97. INCIDENT RESPONSE")

incident_response_steps = [
    "Detect customer-visible impact.",
    "Confirm the SLI and scope.",
    "Declare the incident at the appropriate severity.",
    "Stop harmful changes.",
    "Reduce blast radius.",
    "Restore service quickly.",
    "Communicate status.",
    "Verify recovery through customer-oriented signals.",
    "Measure actual SLO/error-budget impact.",
    "Perform a blameless post-incident review.",
    "Implement corrective actions.",
]

for number, step in enumerate(incident_response_steps, start=1):
    print(f"{number:02d}. {step}")


# =============================================================================
# 98. POST-INCIDENT ANALYSIS
# =============================================================================

print_section("98. POST-INCIDENT AVAILABILITY ANALYSIS")

@dataclass
class IncidentAnalysis:
    incident: Incident
    detection_seconds: float
    mitigation_seconds: float
    recovery_seconds: float

    def validate(self) -> None:
        for value in [
            self.detection_seconds,
            self.mitigation_seconds,
            self.recovery_seconds,
        ]:
            if value < 0:
                raise ValueError("Timing metrics cannot be negative.")


analysis = IncidentAnalysis(
    incident=incident,
    detection_seconds=90,
    mitigation_seconds=240,
    recovery_seconds=1_050,
)

analysis.validate()

print("Detection time:", format_duration(analysis.detection_seconds))
print("Mitigation time:", format_duration(analysis.mitigation_seconds))
print("Recovery time:", format_duration(analysis.recovery_seconds))


# =============================================================================
# 99. AVAILABILITY DESIGN DECISION FUNCTION
# =============================================================================

print_section("99. SIMPLE ARCHITECTURE DECISION MODEL")

@dataclass(frozen=True)
class AvailabilityDecision:
    criticality: str
    required_target: float
    budget_constraint: str
    recommendation: str


decisions = [
    AvailabilityDecision(
        "Low",
        0.99,
        "Low",
        "Single-region deployment with basic monitoring may be sufficient.",
    ),
    AvailabilityDecision(
        "Medium",
        0.999,
        "Moderate",
        "Use redundancy, health checks, controlled deployments, and tested recovery.",
    ),
    AvailabilityDecision(
        "High",
        0.9999,
        "High",
        "Use strong redundancy, failure-domain isolation, advanced observability, and tested failover.",
    ),
]

for decision in decisions:
    print(
        f"{decision.criticality:<8} "
        f"{decision.required_target * 100:.4f}% -> "
        f"{decision.recommendation}"
    )


# =============================================================================
# 100. FINAL CONCEPT MAP
# =============================================================================

print_section("100. CONCEPT MAP")

print(
    """
                         AVAILABILITY
                              |
        +---------------------+---------------------+
        |                     |                     |
      SLI                    SLO                   SLA
        |                     |                     |
    Measurement             Target            Contractual
        |                     |                 commitment
        +----------+----------+
                   |
             Error Budget
                   |
             Burn Rate
                   |
             Operational
               Decisions

Availability engineering also connects to:

    Failure frequency
        |
        +--> MTBF

    Recovery
        |
        +--> MTTR
        +--> Failover
        +--> Rollback
        +--> Incident response

    Architecture
        |
        +--> Redundancy
        +--> Replication
        +--> Failure domains
        +--> Graceful degradation
        +--> Async processing

    Traffic protection
        |
        +--> Timeouts
        +--> Retries
        +--> Backoff
        +--> Circuit breakers
        +--> Rate limiting
        +--> Load shedding

    Measurement
        |
        +--> Metrics
        +--> Logs
        +--> Traces
        +--> Synthetic monitoring

    Business requirements
        |
        +--> Criticality
        +--> Cost
        +--> Customer impact
        +--> SLA
        +--> RTO/RPO
"""
)


# =============================================================================
# 101. QUICK REFERENCE
# =============================================================================

print_section("101. QUICK REFERENCE")

quick_reference = {
    "Availability": "Fraction of eligible time/events that satisfy the service criterion.",
    "Uptime": "Time during which the service is considered available.",
    "Downtime": "Time during which the service is considered unavailable.",
    "SLI": "Measured indicator of service behavior.",
    "SLO": "Target for an SLI.",
    "SLA": "External contractual/service commitment.",
    "Error budget": "Allowed amount of SLO failure.",
    "Burn rate": "Rate at which error budget is being consumed.",
    "MTBF": "Mean time between failures.",
    "MTTR": "Mean time to repair/recover.",
    "RTO": "Target time to restore service.",
    "RPO": "Target maximum data-loss interval.",
}

for term, definition in quick_reference.items():
    print(f"{term:<18}: {definition}")


# =============================================================================
# 102. END-TO-END EXAMPLE
# =============================================================================

print_section("102. END-TO-END SYSTEM DESIGN EXAMPLE")

print(
    """
Scenario:

An e-commerce checkout service has:
    - 10,000,000 valid checkout attempts per month
    - SLO = 99.95%
    - 6,000 failed checkout attempts
    - 20 minutes of customer-visible downtime

Calculations:
    Allowed failed requests = 10,000,000 * 0.05% = 5,000

Actual failures = 6,000

Therefore the request-based SLO is breached.

The time-based SLI can still be above the target.

This illustrates an important principle:

    One SLI can meet its SLO while another SLI fails.

A service-level framework should therefore define the user experience carefully
rather than relying on one generic uptime number.
"""
)

example_requests = 10_000_000
example_failures = 6_000
example_slo = 0.9995

example_request_sli = (
    example_requests - example_failures
) / example_requests

example_allowed_failures = (
    example_requests * (1 - example_slo)
)

print("Request SLI:",
      f"{example_request_sli * 100:.5f}%")
print("SLO:",
      f"{example_slo * 100:.5f}%")
print("Allowed failures:",
      f"{example_allowed_failures:.0f}")
print("Actual failures:",
      f"{example_failures:,}")
print("SLO breached:",
      example_request_sli < example_slo)


# =============================================================================
# 103. EDUCATIONAL CHECK QUESTIONS
# =============================================================================

print_section("103. KNOWLEDGE CHECK")

questions_and_answers = [
    (
        "What does SLI stand for?",
        "Service Level Indicator.",
    ),
    (
        "What does SLO stand for?",
        "Service Level Objective.",
    ),
    (
        "What does SLA stand for?",
        "Service Level Agreement.",
    ),
    (
        "What is the error budget for a 99.9% SLO?",
        "0.1% of the eligible measurement budget.",
    ),
    (
        "What happens to allowed unavailability when moving from 99.9% to 99.99%?",
        "It decreases by a factor of 10.",
    ),
    (
        "Why can two 99% components result in roughly 98.01% availability?",
        "If both are required and independent, their availabilities multiply.",
    ),
    (
        "Why can redundancy fail to provide expected availability?",
        "Replicas may share a common failure domain or dependency.",
    ),
    (
        "Why can retries reduce availability?",
        "Retries can amplify load during dependency failures.",
    ),
]

for question, answer in questions_and_answers:
    print("Q:", question)
    print("A:", answer)
    print()


# =============================================================================
# 104. SCRIPT COMPLETION
# =============================================================================

print_section("104. SCRIPT EXECUTION COMPLETE")

print(
    """
This script demonstrated availability from basic arithmetic through
production-oriented system-design considerations.

Core formulas used:

    Availability
        = (Total Time - Downtime) / Total Time

    Request Availability
        = Good Requests / Valid Requests

    Error Budget
        = 1 - SLO

    Serial Availability
        = Product of required component availabilities

    Independent Redundant Availability
        = 1 - Product of component failure probabilities

    Approximate Steady-State Availability
        = MTBF / (MTBF + MTTR)

The most important design principle is that availability is not merely a
percentage. It is a defined property of a specific service, measured using a
specific SLI, against a specific SLO, within a defined measurement window,
supported by an architecture and operational process capable of meeting it.
"""
)
