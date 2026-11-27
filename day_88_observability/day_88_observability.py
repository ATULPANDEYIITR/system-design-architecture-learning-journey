#!/usr/bin/env python3
"""
Observability, Structured Logging, and Centralized Logging
A self-contained repository-independent observability simulation.

Demonstrates:
- Structured JSON logging
- Log levels and severity filtering
- Correlation and trace identifiers
- Context propagation
- Centralized log ingestion
- Sensitive-data redaction
- Event aggregation and alert evaluation
- Retention and querying
- Failure handling and auditability
"""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
import time
import uuid

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import IntEnum
from typing import Any, Optional


# ---------------------------------------------------------
# 1. Domain types and configuration
# ---------------------------------------------------------

class Severity(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass(frozen=True)
class LogContext:
    service: str
    environment: str
    version: str
    trace_id: str
    correlation_id: str
    request_id: str
    user_id: Optional[str] = None


@dataclass
class LogEvent:
    timestamp: str
    severity: str
    severity_number: int
    service: str
    environment: str
    version: str
    event_name: str
    message: str
    trace_id: str
    correlation_id: str
    request_id: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )


# ---------------------------------------------------------
# 2. Sensitive-data protection
# ---------------------------------------------------------

class SensitiveDataRedactor:
    SENSITIVE_KEYS = {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "secret",
        "credit_card",
    }

    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )

    def redact(self, value: Any, key: str = "") -> Any:
        if key.lower() in self.SENSITIVE_KEYS:
            return "[REDACTED]"

        if isinstance(value, dict):
            return {
                str(k): self.redact(v, str(k))
                for k, v in value.items()
            }

        if isinstance(value, list):
            return [self.redact(item) for item in value]

        if isinstance(value, str):
            return self.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)

        return value


# ---------------------------------------------------------
# 3. Structured event creation
# ---------------------------------------------------------

class StructuredLogger:
    def __init__(
        self,
        service: str,
        environment: str = "development",
        version: str = "1.0.0",
        minimum_level: Severity = Severity.DEBUG,
    ):
        self.service = service
        self.environment = environment
        self.version = version
        self.minimum_level = minimum_level
        self.redactor = SensitiveDataRedactor()

    def create_context(
        self,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> LogContext:
        return LogContext(
            service=self.service,
            environment=self.environment,
            version=self.version,
            trace_id=trace_id or uuid.uuid4().hex,
            correlation_id=correlation_id or uuid.uuid4().hex,
            request_id=request_id or uuid.uuid4().hex,
            user_id=user_id,
        )

    def emit(
        self,
        severity: Severity,
        event_name: str,
        message: str,
        context: LogContext,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Optional[LogEvent]:
        if severity < self.minimum_level:
            return None

        if not event_name or not event_name.strip():
            raise ValueError("Event name cannot be empty")

        safe_attributes = self.redactor.redact(attributes or {})

        if context.user_id:
            safe_attributes["user_id"] = context.user_id

        return LogEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            severity=severity.name,
            severity_number=int(severity),
            service=context.service,
            environment=context.environment,
            version=context.version,
            event_name=event_name,
            message=self.redactor.redact(message),
            trace_id=context.trace_id,
            correlation_id=context.correlation_id,
            request_id=context.request_id,
            attributes=safe_attributes,
        )


# ---------------------------------------------------------
# 4. Centralized log storage
# ---------------------------------------------------------

class CentralLogCollector:
    def __init__(self, maximum_events: int = 10000):
        if maximum_events <= 0:
            raise ValueError("Maximum events must be positive")

        self.events: deque[LogEvent] = deque(maxlen=maximum_events)
        self.lock = threading.RLock()
        self.rejected_events = 0

    def ingest(self, event: LogEvent) -> bool:
        try:
            # Serialization verifies that the event is JSON-compatible.
            json.loads(event.to_json())

            with self.lock:
                self.events.append(event)

            return True

        except (TypeError, ValueError):
            with self.lock:
                self.rejected_events += 1
            return False

    def query(
        self,
        service: Optional[str] = None,
        severity: Optional[Severity] = None,
        trace_id: Optional[str] = None,
        event_name: Optional[str] = None,
    ) -> list[LogEvent]:
        with self.lock:
            snapshot = list(self.events)

        return [
            event
            for event in snapshot
            if (service is None or event.service == service)
            and (
                severity is None
                or event.severity_number >= int(severity)
            )
            and (trace_id is None or event.trace_id == trace_id)
            and (
                event_name is None
                or event.event_name == event_name
            )
        ]

    def export_json_lines(self) -> str:
        with self.lock:
            return "\n".join(event.to_json() for event in self.events)

    def expire_before(self, cutoff: datetime) -> int:
        removed = 0

        with self.lock:
            retained = [
                event
                for event in self.events
                if datetime.fromisoformat(event.timestamp) >= cutoff
            ]

            removed = len(self.events) - len(retained)
            self.events = deque(
                retained,
                maxlen=self.events.maxlen,
            )

        return removed


# ---------------------------------------------------------
# 5. Application instrumentation
# ---------------------------------------------------------

class InstrumentedService:
    def __init__(
        self,
        logger: StructuredLogger,
        collector: CentralLogCollector,
    ):
        self.logger = logger
        self.collector = collector

    def process_payment(
        self,
        amount: float,
        context: LogContext,
        fail: bool = False,
    ) -> dict[str, Any]:

        start = time.perf_counter()

        self._log(
            Severity.INFO,
            "payment.started",
            "Payment processing started",
            context,
            {"amount": amount},
        )

        try:
            if amount <= 0:
                raise ValueError("Payment amount must be positive")

            if fail:
                raise RuntimeError("Payment gateway unavailable")

            result = {
                "payment_id": uuid.uuid4().hex,
                "status": "completed",
                "amount": amount,
            }

            self._log(
                Severity.INFO,
                "payment.completed",
                "Payment completed successfully",
                context,
                {
                    "payment_id": result["payment_id"],
                    "amount": amount,
                    "duration_ms": round(
                        (time.perf_counter() - start) * 1000,
                        3,
                    ),
                },
            )

            return result

        except Exception as exc:
            self._log(
                Severity.ERROR,
                "payment.failed",
                "Payment processing failed",
                context,
                {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "duration_ms": round(
                        (time.perf_counter() - start) * 1000,
                        3,
                    ),
                },
            )
            raise

    def _log(
        self,
        severity: Severity,
        event_name: str,
        message: str,
        context: LogContext,
        attributes: dict[str, Any],
    ) -> None:
        event = self.logger.emit(
            severity,
            event_name,
            message,
            context,
            attributes,
        )

        if event:
            self.collector.ingest(event)


# ---------------------------------------------------------
# 6. Operational metrics derived from logs
# ---------------------------------------------------------

class LogAnalytics:
    def __init__(self, collector: CentralLogCollector):
        self.collector = collector

    def error_rate(self, service: str) -> float:
        events = self.collector.query(service=service)

        if not events:
            return 0.0

        errors = sum(
            event.severity_number >= Severity.ERROR
            for event in events
        )

        return errors / len(events)

    def event_distribution(self) -> dict[str, int]:
        events = self.collector.query()

        return dict(
            Counter(event.event_name for event in events)
        )

    def service_health(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[LogEvent]] = defaultdict(list)

        for event in self.collector.query():
            grouped[event.service].append(event)

        results = []

        for service, events in grouped.items():
            errors = sum(
                event.severity_number >= Severity.ERROR
                for event in events
            )

            results.append({
                "service": service,
                "total_events": len(events),
                "errors": errors,
                "error_rate": round(errors / len(events), 4),
                "health": "DEGRADED" if errors else "HEALTHY",
            })

        return results


# ---------------------------------------------------------
# 7. Alert evaluation
# ---------------------------------------------------------

@dataclass(frozen=True)
class AlertRule:
    name: str
    service: str
    minimum_error_rate: float
    minimum_events: int

    def __post_init__(self):
        if not 0 <= self.minimum_error_rate <= 1:
            raise ValueError("Error rate must be between 0 and 1")

        if self.minimum_events <= 0:
            raise ValueError("Minimum events must be positive")


class AlertEngine:
    def __init__(self, collector: CentralLogCollector):
        self.collector = collector

    def evaluate(self, rule: AlertRule) -> dict[str, Any]:
        events = self.collector.query(service=rule.service)

        errors = sum(
            event.severity_number >= Severity.ERROR
            for event in events
        )

        rate = errors / len(events) if events else 0.0

        triggered = (
            len(events) >= rule.minimum_events
            and rate >= rule.minimum_error_rate
        )

        return {
            "rule": rule.name,
            "service": rule.service,
            "events": len(events),
            "errors": errors,
            "error_rate": round(rate, 4),
            "triggered": triggered,
            "status": "FIRING" if triggered else "NORMAL",
        }


# ---------------------------------------------------------
# 8. Operational demonstration
# ---------------------------------------------------------

def main() -> None:
    collector = CentralLogCollector(maximum_events=5000)

    payment_logger = StructuredLogger(
        service="payment-service",
        environment="production",
        version="2.4.1",
    )

    service = InstrumentedService(
        payment_logger,
        collector,
    )

    context = payment_logger.create_context(
        correlation_id="order-2026-001",
        user_id="user-1042",
    )

    print("=== Structured Logging Demonstration ===")

    service.process_payment(1250.50, context)

    try:
        service.process_payment(
            500.00,
            context,
            fail=True,
        )
    except RuntimeError:
        print("Expected gateway failure captured.")

    try:
        service.process_payment(0, context)
    except ValueError:
        print("Expected validation failure captured.")

    # Demonstrate automatic redaction.
    security_event = payment_logger.emit(
        Severity.WARNING,
        "authentication.failure",
        "Authentication failed for customer@example.com",
        context,
        {
            "username": "customer",
            "password": "unsafe-example",
            "access_token": "secret-token",
        },
    )

    if security_event:
        collector.ingest(security_event)

    print("\n=== Centralized JSON Events ===")

    for event in collector.query(service="payment-service"):
        print(event.to_json())

    print("\n=== Trace Correlation ===")

    trace_events = collector.query(
        trace_id=context.trace_id
    )

    print(f"Trace ID: {context.trace_id}")
    print(f"Related events: {len(trace_events)}")

    print("\n=== Operational Analytics ===")

    analytics = LogAnalytics(collector)

    print(json.dumps(
        analytics.service_health(),
        indent=2,
    ))

    print("\n=== Alert Evaluation ===")

    alert_engine = AlertEngine(collector)

    rule = AlertRule(
        name="payment-error-rate",
        service="payment-service",
        minimum_error_rate=0.30,
        minimum_events=3,
    )

    print(json.dumps(
        alert_engine.evaluate(rule),
        indent=2,
    ))

    print("\n=== Event Distribution ===")

    print(json.dumps(
        analytics.event_distribution(),
        indent=2,
    ))

    # Validate important security and processing behavior.
    assert len(trace_events) == 4
    assert all(
        event.attributes.get("password") != "unsafe-example"
        for event in collector.query()
    )

    redacted_event = collector.query(
        event_name="authentication.failure"
    )[0]

    assert redacted_event.attributes["password"] == "[REDACTED]"
    assert redacted_event.attributes["access_token"] == "[REDACTED]"
    assert "[REDACTED_EMAIL]" in redacted_event.message

    assert alert_engine.evaluate(rule)["triggered"]

    print("\nAll validation assertions passed.")

    print("\n=== JSON Lines Export ===")
    print(collector.export_json_lines())


if __name__ == "__main__":
    main()
