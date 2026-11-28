#!/usr/bin/env python3
"""
Metrics, Counters, Gauges, Histograms, and Service Level Indicators (SLIs).

A self-contained metrics collection and evaluation system using only
the Python standard library.
"""

from __future__ import annotations

import json
import math
import threading
import time
import unittest

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


class MetricError(Exception):
    pass


class MetricValidationError(MetricError):
    pass


class MetricNotFoundError(MetricError):
    pass


def validate_name(name: str) -> None:
    if not name or not isinstance(name, str):
        raise MetricValidationError("Metric name cannot be empty.")

    if not all(c.isalnum() or c in "_:" for c in name):
        raise MetricValidationError(f"Invalid metric name: {name}")


def validate_labels(labels: dict[str, str]) -> tuple:
    if len(labels) > 10:
        raise MetricValidationError("Maximum of 10 labels allowed.")

    for key, value in labels.items():
        validate_name(key)
        if not isinstance(value, str) or len(value) > 128:
            raise MetricValidationError("Invalid label value.")

    return tuple(sorted(labels.items()))


@dataclass
class Metric:
    name: str
    description: str
    metric_type: MetricType
    label_names: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)

    def validate_labels(self, labels: dict) -> tuple:
        if set(labels) != set(self.label_names):
            raise MetricValidationError(
                f"{self.name} requires labels {self.label_names}"
            )
        return validate_labels(labels)


class Counter(Metric):
    def __init__(self, name, description="", label_names=()):
        super().__init__(
            name, description, MetricType.COUNTER, tuple(label_names)
        )
        self.values = defaultdict(float)
        self.lock = threading.Lock()

    def inc(self, amount=1.0, labels=None):
        labels = labels or {}

        if not math.isfinite(amount) or amount <= 0:
            raise MetricValidationError(
                "Counter increments must be finite and positive."
            )

        key = self.validate_labels(labels)

        with self.lock:
            self.values[key] += amount
            return self.values[key]

    def get(self, labels=None):
        key = self.validate_labels(labels or {})
        with self.lock:
            return self.values[key]


class Gauge(Metric):
    def __init__(self, name, description="", label_names=()):
        super().__init__(
            name, description, MetricType.GAUGE, tuple(label_names)
        )
        self.values = defaultdict(float)
        self.lock = threading.Lock()

    def set(self, value, labels=None):
        if not math.isfinite(value):
            raise MetricValidationError("Gauge value must be finite.")

        key = self.validate_labels(labels or {})

        with self.lock:
            self.values[key] = value
            return value

    def inc(self, amount=1.0, labels=None):
        if not math.isfinite(amount):
            raise MetricValidationError("Invalid gauge increment.")

        key = self.validate_labels(labels or {})

        with self.lock:
            self.values[key] += amount
            return self.values[key]

    def dec(self, amount=1.0, labels=None):
        if not math.isfinite(amount):
            raise MetricValidationError("Invalid gauge decrement.")

        key = self.validate_labels(labels or {})

        with self.lock:
            self.values[key] -= amount
            return self.values[key]

    def get(self, labels=None):
        key = self.validate_labels(labels or {})
        with self.lock:
            return self.values[key]


class Histogram(Metric):
    def __init__(
        self,
        name,
        description="",
        buckets=(0.1, 0.3, 0.5, 1.0, 2.5, 5.0),
        label_names=(),
    ):
        super().__init__(
            name, description, MetricType.HISTOGRAM, tuple(label_names)
        )

        if not buckets:
            raise MetricValidationError("Histogram requires buckets.")

        if any(not math.isfinite(x) or x <= 0 for x in buckets):
            raise MetricValidationError("Buckets must be finite and positive.")

        if tuple(sorted(set(buckets))) != tuple(buckets):
            raise MetricValidationError("Buckets must be unique and sorted.")

        self.buckets = tuple(buckets)
        self.observations = defaultdict(list)
        self.lock = threading.Lock()

    def observe(self, value, labels=None):
        if not math.isfinite(value) or value < 0:
            raise MetricValidationError(
                "Histogram observations must be finite and non-negative."
            )

        key = self.validate_labels(labels or {})

        with self.lock:
            self.observations[key].append(value)

    def snapshot(self, labels=None):
        key = self.validate_labels(labels or {})

        with self.lock:
            values = tuple(self.observations[key])

        return {
            "count": len(values),
            "sum": sum(values),
            "buckets": {
                str(bound): sum(v <= bound for v in values)
                for bound in self.buckets
            },
            "infinity": len(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }

    def percentile(self, quantile, labels=None):
        if not 0 <= quantile <= 1:
            raise MetricValidationError("Quantile must be between 0 and 1.")

        key = self.validate_labels(labels or {})

        with self.lock:
            values = sorted(self.observations[key])

        if not values:
            return None

        # Nearest-rank percentile.
        index = max(0, math.ceil(quantile * len(values)) - 1)
        return values[index]


class MetricsRegistry:
    def __init__(self):
        self.metrics: dict[str, Metric] = {}
        self.lock = threading.RLock()

    def register(self, metric: Metric):
        validate_name(metric.name)

        with self.lock:
            if metric.name in self.metrics:
                raise MetricValidationError(
                    f"Metric already registered: {metric.name}"
                )

            self.metrics[metric.name] = metric

        return metric

    def get(self, name):
        with self.lock:
            if name not in self.metrics:
                raise MetricNotFoundError(name)
            return self.metrics[name]

    def snapshot(self):
        result = {}

        with self.lock:
            metrics = list(self.metrics.values())

        for metric in metrics:
            if isinstance(metric, Counter):
                with metric.lock:
                    result[metric.name] = {
                        str(k): v for k, v in metric.values.items()
                    }

            elif isinstance(metric, Gauge):
                with metric.lock:
                    result[metric.name] = {
                        str(k): v for k, v in metric.values.items()
                    }

            elif isinstance(metric, Histogram):
                with metric.lock:
                    keys = list(metric.observations.keys())

                result[metric.name] = {
                    str(k): metric.snapshot(dict(k)) for k in keys
                }

        return result

    def export_json(self, destination: str | Path):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary = destination.with_suffix(destination.suffix + ".tmp")

        temporary.write_text(
            json.dumps(self.snapshot(), indent=2),
            encoding="utf-8",
        )

        temporary.replace(destination)


@dataclass(frozen=True)
class SLIResult:
    name: str
    numerator: float
    denominator: float
    value: float | None
    target: float
    passed: bool | None


class SLI:
    """Evaluates a ratio-based service-level indicator."""

    def __init__(self, name, target, unit="ratio"):
        if not 0 <= target <= 1:
            raise ValueError("Target must be between 0 and 1.")

        self.name = name
        self.target = target
        self.unit = unit

    def evaluate(self, numerator, denominator):
        if (
            not math.isfinite(numerator)
            or not math.isfinite(denominator)
            or denominator < 0
            or numerator < 0
            or numerator > denominator
        ):
            raise ValueError("Invalid SLI numerator or denominator.")

        if denominator == 0:
            return SLIResult(
                self.name, numerator, denominator, None,
                self.target, None
            )

        value = numerator / denominator

        return SLIResult(
            self.name,
            numerator,
            denominator,
            value,
            self.target,
            value >= self.target,
        )


class ServiceMetrics:
    """Example HTTP service instrumentation."""

    def __init__(self):
        self.registry = MetricsRegistry()

        self.requests = self.registry.register(
            Counter(
                "http_requests_total",
                "Total HTTP requests.",
                ("method", "status"),
            )
        )

        self.active = self.registry.register(
            Gauge(
                "http_active_requests",
                "Currently active HTTP requests.",
            )
        )

        self.duration = self.registry.register(
            Histogram(
                "http_request_duration_seconds",
                "HTTP request duration.",
                buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
                label_names=("method",),
            )
        )

    def handle_request(self, method, status, operation: Callable):
        if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            raise ValueError("Unsupported HTTP method.")

        self.active.inc()

        start = time.perf_counter()

        try:
            return operation()
        finally:
            elapsed = time.perf_counter() - start

            self.requests.inc(
                labels={"method": method, "status": str(status)}
            )

            self.duration.observe(
                elapsed,
                labels={"method": method},
            )

            self.active.dec()


def main():
    service = ServiceMetrics()

    def database_operation():
        time.sleep(0.02)
        return {"database": "available"}

    service.handle_request("GET", 200, database_operation)
    service.handle_request("POST", 201, database_operation)

    service.requests.inc(
        labels={"method": "GET", "status": "500"}
    )

    service.active.set(4)

    latency = service.duration.percentile(
        0.95, labels={"method": "GET"}
    )

    sli = SLI("availability", target=0.999)

    result = sli.evaluate(
        numerator=9990,
        denominator=10000,
    )

    print("METRIC SNAPSHOT")
    print(json.dumps(service.registry.snapshot(), indent=2))

    print("\nLATENCY P95")
    print(latency)

    print("\nAVAILABILITY SLI")
    print(result)

    service.registry.export_json("metrics_snapshot.json")


class MetricsTests(unittest.TestCase):
    def test_counter(self):
        counter = Counter("test_counter")
        counter.inc()
        counter.inc(2)
        self.assertEqual(counter.get(), 3)

    def test_counter_rejects_decrement(self):
        counter = Counter("test_counter")
        with self.assertRaises(MetricValidationError):
            counter.inc(-1)

    def test_gauge(self):
        gauge = Gauge("test_gauge")
        gauge.set(10)
        gauge.dec(3)
        self.assertEqual(gauge.get(), 7)

    def test_histogram(self):
        histogram = Histogram("test_histogram", buckets=(1, 2, 5))
        for value in (0.5, 1.5, 3.0, 4.0):
            histogram.observe(value)

        snapshot = histogram.snapshot()
        self.assertEqual(snapshot["count"], 4)
        self.assertEqual(snapshot["buckets"]["2"], 2)

    def test_percentile(self):
        histogram = Histogram("test_percentile")
        for value in range(1, 101):
            histogram.observe(float(value))

        self.assertEqual(histogram.percentile(0.95), 95)

    def test_sli(self):
        sli = SLI("availability", 0.99)
        result = sli.evaluate(995, 1000)
        self.assertTrue(result.passed)

    def test_empty_sli(self):
        result = SLI("availability", 0.99).evaluate(0, 0)
        self.assertIsNone(result.passed)

    def test_invalid_sli(self):
        with self.assertRaises(ValueError):
            SLI("availability", 0.99).evaluate(101, 100)

    def test_registry_duplicate(self):
        registry = MetricsRegistry()
        registry.register(Counter("requests"))

        with self.assertRaises(MetricValidationError):
            registry.register(Counter("requests"))


if __name__ == "__main__":
    main()
    unittest.main(argv=["metrics.py"], exit=False)
