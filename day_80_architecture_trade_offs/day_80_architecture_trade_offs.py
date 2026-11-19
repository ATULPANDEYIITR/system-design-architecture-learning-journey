#!/usr/bin/env python3
"""
Architecture Trade-offs: Cost, Complexity, Performance, and Reliability

A self-contained architecture decision simulator.

Models:
- Architecture alternatives
- Infrastructure and operational costs
- Computational performance
- System complexity
- Reliability and availability
- Scalability
- Failure scenarios
- Weighted decision analysis
- Sensitivity analysis
- Architecture decision records
- JSON report generation

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("architecture_tradeoffs")


class ArchitectureType(Enum):
    MONOLITH = "Monolith"
    MODULAR_MONOLITH = "Modular Monolith"
    MICROSERVICES = "Microservices"
    SERVERLESS = "Serverless"
    EVENT_DRIVEN = "Event-Driven"
    HYBRID = "Hybrid"


class RiskLevel(Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass(frozen=True)
class ArchitectureMetrics:
    monthly_infrastructure_cost: float
    monthly_operations_cost: float
    average_latency_ms: float
    throughput_rps: float
    availability_percent: float
    complexity_score: float
    scalability_score: float
    recovery_time_minutes: float
    deployment_frequency_per_month: float

    def validate(self) -> None:
        non_negative = {
            "monthly_infrastructure_cost": self.monthly_infrastructure_cost,
            "monthly_operations_cost": self.monthly_operations_cost,
            "average_latency_ms": self.average_latency_ms,
            "throughput_rps": self.throughput_rps,
            "recovery_time_minutes": self.recovery_time_minutes,
            "deployment_frequency_per_month": self.deployment_frequency_per_month,
        }

        for name, value in non_negative.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")

        if not 0 < self.availability_percent <= 100:
            raise ValueError("Availability must be greater than 0 and at most 100")

        for name, value in {
            "complexity_score": self.complexity_score,
            "scalability_score": self.scalability_score,
        }.items():
            if not math.isfinite(value) or not 1 <= value <= 10:
                raise ValueError(f"{name} must be between 1 and 10")


@dataclass
class Architecture:
    name: str
    architecture_type: ArchitectureType
    description: str
    metrics: ArchitectureMetrics
    operational_risks: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Architecture name cannot be empty")
        self.metrics.validate()

    @property
    def total_monthly_cost(self) -> float:
        return (
            self.metrics.monthly_infrastructure_cost
            + self.metrics.monthly_operations_cost
        )

    @property
    def annual_cost(self) -> float:
        return self.total_monthly_cost * 12


@dataclass(frozen=True)
class DecisionWeights:
    cost: float = 0.25
    performance: float = 0.20
    reliability: float = 0.25
    simplicity: float = 0.15
    scalability: float = 0.15

    def validate(self) -> None:
        values = [
            self.cost,
            self.performance,
            self.reliability,
            self.simplicity,
            self.scalability,
        ]

        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Weights must be finite and non-negative")

        if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
            raise ValueError("Decision weights must sum to 1")


@dataclass
class Evaluation:
    architecture_name: str
    cost_score: float
    performance_score: float
    reliability_score: float
    simplicity_score: float
    scalability_score: float
    weighted_score: float
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class ArchitectureDecisionEngine:
    """Evaluates architectures using normalized, weighted metrics."""

    def __init__(
        self,
        architectures: Iterable[Architecture],
        weights: DecisionWeights,
    ) -> None:
        self.architectures = list(architectures)
        self.weights = weights
        self.weights.validate()

        if not self.architectures:
            raise ValueError("At least one architecture is required")

        names = [a.name.casefold() for a in self.architectures]
        if len(names) != len(set(names)):
            raise ValueError("Architecture names must be unique")

    @staticmethod
    def _lower_is_better(value: float, maximum: float) -> float:
        if maximum <= 0:
            return 100.0
        return max(0.0, min(100.0, 100.0 * (1 - value / maximum)))

    @staticmethod
    def _higher_is_better(value: float, maximum: float) -> float:
        if maximum <= 0:
            return 100.0
        return max(0.0, min(100.0, 100.0 * value / maximum))

    def evaluate(self) -> list[Evaluation]:
        metrics = [a.metrics for a in self.architectures]

        max_cost = max(a.total_monthly_cost for a in self.architectures)
        max_latency = max(m.average_latency_ms for m in metrics)
        max_throughput = max(m.throughput_rps for m in metrics)
        max_complexity = max(m.complexity_score for m in metrics)
        max_scalability = max(m.scalability_score for m in metrics)

        results = []

        for architecture in self.architectures:
            m = architecture.metrics

            cost_score = self._lower_is_better(
                architecture.total_monthly_cost, max_cost
            )

            # Throughput and latency are both considered.
            latency_score = self._lower_is_better(
                m.average_latency_ms, max_latency
            )
            throughput_score = self._higher_is_better(
                m.throughput_rps, max_throughput
            )
            performance_score = (
                latency_score * 0.5 + throughput_score * 0.5
            )

            reliability_score = m.availability_percent

            simplicity_score = self._lower_is_better(
                m.complexity_score, max_complexity
            )

            scalability_score = self._higher_is_better(
                m.scalability_score, max_scalability
            )

            weighted_score = (
                cost_score * self.weights.cost
                + performance_score * self.weights.performance
                + reliability_score * self.weights.reliability
                + simplicity_score * self.weights.simplicity
                + scalability_score * self.weights.scalability
            )

            results.append(
                Evaluation(
                    architecture_name=architecture.name,
                    cost_score=round(cost_score, 2),
                    performance_score=round(performance_score, 2),
                    reliability_score=round(reliability_score, 2),
                    simplicity_score=round(simplicity_score, 2),
                    scalability_score=round(scalability_score, 2),
                    weighted_score=round(weighted_score, 2),
                )
            )

        results.sort(key=lambda result: result.weighted_score, reverse=True)

        for rank, result in enumerate(results, start=1):
            result.rank = rank

        return results


@dataclass
class FailureScenario:
    name: str
    probability_per_year: float
    impact_cost: float
    recovery_minutes: float

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Failure scenario name cannot be empty")

        if not 0 <= self.probability_per_year <= 1:
            raise ValueError("Probability must be between 0 and 1")

        if self.impact_cost < 0 or self.recovery_minutes < 0:
            raise ValueError("Failure impacts cannot be negative")


class ReliabilityAnalyzer:
    """Calculates basic availability and expected annual failure loss."""

    @staticmethod
    def annual_downtime_hours(availability_percent: float) -> float:
        if not 0 < availability_percent <= 100:
            raise ValueError("Invalid availability")
        return 8760 * (1 - availability_percent / 100)

    @staticmethod
    def expected_annual_failure_loss(
        scenarios: Iterable[FailureScenario],
    ) -> float:
        total = 0.0

        for scenario in scenarios:
            scenario.validate()
            total += scenario.probability_per_year * scenario.impact_cost

        return total

    @staticmethod
    def serial_component_availability(
        component_availabilities: Iterable[float],
    ) -> float:
        """Availability of independent serial dependencies."""
        result = 1.0

        for availability in component_availabilities:
            if not 0 < availability <= 1:
                raise ValueError("Component availability must be in (0, 1]")
            result *= availability

        return result * 100


@dataclass
class ArchitectureDecisionRecord:
    title: str
    context: str
    decision: str
    alternatives: list[str]
    consequences: list[str]
    status: str = "Accepted"

    def validate(self) -> None:
        if not all([
            self.title.strip(),
            self.context.strip(),
            self.decision.strip(),
        ]):
            raise ValueError("Decision record requires title, context and decision")

        if self.status not in {"Proposed", "Accepted", "Superseded", "Rejected"}:
            raise ValueError("Invalid decision status")


class ArchitectureRepository:
    """Stores evaluated architectures and exports decision evidence."""

    def __init__(self) -> None:
        self.architectures: dict[str, Architecture] = {}

    def add(self, architecture: Architecture) -> None:
        key = architecture.name.casefold()

        if key in self.architectures:
            raise ValueError(f"Duplicate architecture: {architecture.name}")

        self.architectures[key] = architecture

    def get(self, name: str) -> Architecture:
        try:
            return self.architectures[name.casefold()]
        except KeyError as exc:
            raise KeyError(f"Architecture not found: {name}") from exc

    def export_report(
        self,
        evaluations: list[Evaluation],
        path: Path,
        record: ArchitectureDecisionRecord,
    ) -> None:
        record.validate()

        payload = {
            "decision_record": asdict(record),
            "architectures": [
                {
                    "name": architecture.name,
                    "type": architecture.architecture_type.value,
                    "description": architecture.description,
                    "metrics": asdict(architecture.metrics),
                    "monthly_cost": architecture.total_monthly_cost,
                    "annual_cost": architecture.annual_cost,
                    "strengths": architecture.strengths,
                    "risks": architecture.operational_risks,
                }
                for architecture in self.architectures.values()
            ],
            "evaluations": [e.to_dict() for e in evaluations],
        }

        # Write to a temporary file before replacing the destination.
        temporary_path = path.with_suffix(path.suffix + ".tmp")

        try:
            temporary_path.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise


def build_sample_architectures() -> list[Architecture]:
    return [
        Architecture(
            name="Modular Commerce Platform",
            architecture_type=ArchitectureType.MODULAR_MONOLITH,
            description="Single deployment with independently maintained modules.",
            metrics=ArchitectureMetrics(
                1200, 800, 95, 1800, 99.95, 3.5, 6.5, 20, 8
            ),
            strengths=["Simple deployment", "Low operational overhead"],
            operational_risks=["Shared deployment boundary"],
        ),
        Architecture(
            name="Microservices Commerce Platform",
            architecture_type=ArchitectureType.MICROSERVICES,
            description="Distributed services with independent deployment.",
            metrics=ArchitectureMetrics(
                4200, 3500, 125, 3500, 99.90, 8.5, 9.5, 35, 25
            ),
            strengths=["Independent scaling", "Service isolation"],
            operational_risks=[
                "Network failures",
                "Distributed tracing complexity",
                "Data consistency challenges",
            ],
        ),
        Architecture(
            name="Serverless Order Processing",
            architecture_type=ArchitectureType.SERVERLESS,
            description="Managed functions and event-triggered execution.",
            metrics=ArchitectureMetrics(
                850, 1100, 160, 2200, 99.90, 5.5, 9.0, 15, 30
            ),
            strengths=["Automatic scaling", "Reduced server management"],
            operational_risks=["Cold starts", "Execution limits", "Vendor dependency"],
        ),
        Architecture(
            name="Event-Driven Commerce Platform",
            architecture_type=ArchitectureType.EVENT_DRIVEN,
            description="Asynchronous communication through durable events.",
            metrics=ArchitectureMetrics(
                2600, 2400, 140, 4200, 99.95, 7.5, 9.0, 25, 18
            ),
            strengths=["Loose coupling", "Asynchronous processing"],
            operational_risks=[
                "Eventual consistency",
                "Duplicate event delivery",
                "Event schema evolution",
            ],
        ),
    ]


def run_tests() -> None:
    assert math.isclose(
        ReliabilityAnalyzer.annual_downtime_hours(99.9),
        8.76,
        rel_tol=1e-9,
    )

    assert math.isclose(
        ReliabilityAnalyzer.serial_component_availability([0.99, 0.99]),
        98.01,
        rel_tol=1e-9,
    )

    scenarios = [
        FailureScenario("Database outage", 0.1, 50000, 60),
        FailureScenario("Region outage", 0.02, 150000, 180),
    ]

    assert ReliabilityAnalyzer.expected_annual_failure_loss(scenarios) == 8000

    try:
        ArchitectureMetrics(
            100, 100, 10, 100, 105, 5, 5, 10, 2
        ).validate()
        raise AssertionError("Invalid availability was accepted")
    except ValueError:
        pass


def main() -> None:
    run_tests()

    repository = ArchitectureRepository()

    for architecture in build_sample_architectures():
        repository.add(architecture)

    weights = DecisionWeights(
        cost=0.25,
        performance=0.20,
        reliability=0.25,
        simplicity=0.15,
        scalability=0.15,
    )

    engine = ArchitectureDecisionEngine(
        repository.architectures.values(),
        weights,
    )

    evaluations = engine.evaluate()

    print("\nARCHITECTURE TRADE-OFF EVALUATION")
    print("=" * 95)
    print(
        f"{'Rank':<6}{'Architecture':<36}"
        f"{'Cost':>9}{'Performance':>14}"
        f"{'Reliability':>13}{'Score':>10}"
    )

    for result in evaluations:
        print(
            f"{result.rank:<6}{result.architecture_name:<36}"
            f"{result.cost_score:>9.2f}"
            f"{result.performance_score:>14.2f}"
            f"{result.reliability_score:>13.2f}"
            f"{result.weighted_score:>10.2f}"
        )

    print("\nCOST AND RELIABILITY")
    for architecture in repository.architectures.values():
        downtime = ReliabilityAnalyzer.annual_downtime_hours(
            architecture.metrics.availability_percent
        )
        print(
            f"{architecture.name}: "
            f"monthly=${architecture.total_monthly_cost:,.2f}, "
            f"annual=${architecture.annual_cost:,.2f}, "
            f"estimated downtime={downtime:.2f} hours/year"
        )

    scenarios = [
        FailureScenario("Database failure", 0.10, 50000, 45),
        FailureScenario("Cloud region failure", 0.02, 150000, 180),
        FailureScenario("Deployment rollback", 0.25, 8000, 15),
    ]

    print(
        "\nExpected annual failure loss: "
        f"${ReliabilityAnalyzer.expected_annual_failure_loss(scenarios):,.2f}"
    )

    record = ArchitectureDecisionRecord(
        title="Commerce Platform Architecture Selection",
        context=(
            "A commerce platform must balance operational expenditure, "
            "development complexity, throughput and service reliability."
        ),
        decision=(
            f"Initial weighted evaluation ranks "
            f"{evaluations[0].architecture_name} first."
        ),
        alternatives=[
            architecture.name
            for architecture in repository.architectures.values()
        ],
        consequences=[
            "The weighted ranking depends on business priorities.",
            "Production selection requires workload-specific benchmarking.",
            "Availability estimates depend on actual dependency topology.",
        ],
    )

    output_path = Path("architecture_decision_report.json")
    repository.export_report(evaluations, output_path, record)

    print(f"\nReport written to: {output_path.resolve()}")
    logger.info("All validation tests passed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        logger.error("Execution failed: %s", error)
        raise SystemExit(1)
