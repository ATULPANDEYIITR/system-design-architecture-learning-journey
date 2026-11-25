from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("resilience")


class ComponentState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"


class DependencyPolicy(Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class FailureMode(Enum):
    FAIL_FAST = "fail_fast"
    FALLBACK = "fallback"
    SKIP = "skip"


@dataclass
class Component:
    name: str
    critical: bool
    state: ComponentState = ComponentState.HEALTHY
    failure_count: int = 0
    recovery_count: int = 0
    last_error: str | None = None

    def fail(self, reason: str) -> None:
        self.failure_count += 1
        self.state = ComponentState.FAILED
        self.last_error = reason

    def degrade(self, reason: str) -> None:
        self.state = ComponentState.DEGRADED
        self.last_error = reason

    def recover(self) -> None:
        self.state = ComponentState.HEALTHY
        self.last_error = None
        self.recovery_count += 1


@dataclass
class Dependency:
    name: str
    policy: DependencyPolicy
    fallback_value: Any = None


@dataclass
class OperationResult:
    operation_id: str
    success: bool
    mode: str
    data: Any
    unavailable_features: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class ResilienceError(Exception):
    pass


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Prevents repeated calls to a dependency that is failing."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 5.0,
    ):
        if failure_threshold < 1 or recovery_timeout <= 0:
            raise ValueError("Invalid circuit breaker configuration")

        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if (
                self.opened_at is not None
                and time.monotonic() - self.opened_at >= self.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
                return True
            return False

        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1

        if (
            self.state == CircuitState.HALF_OPEN
            or self.failure_count >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()


class DependencyManager:
    def __init__(self):
        self.components: dict[str, Component] = {}
        self.dependencies: dict[str, Dependency] = {}
        self.breakers: dict[str, CircuitBreaker] = {}

    def register(
        self,
        name: str,
        critical: bool,
        policy: DependencyPolicy,
        fallback_value: Any = None,
    ) -> None:
        if not name or name in self.components:
            raise ValueError(f"Invalid or duplicate component: {name}")

        self.components[name] = Component(name, critical)
        self.dependencies[name] = Dependency(
            name, policy, fallback_value
        )
        self.breakers[name] = CircuitBreaker()

    def execute(
        self,
        name: str,
        operation: Callable[[], Any],
        failure_mode: FailureMode = FailureMode.FAIL_FAST,
    ) -> Any:
        if name not in self.components:
            raise ResilienceError(f"Unknown component: {name}")

        component = self.components[name]
        breaker = self.breakers[name]
        dependency = self.dependencies[name]

        if not breaker.allow_request():
            component.degrade("Circuit breaker is open")
            raise ResilienceError(f"{name} is temporarily unavailable")

        try:
            result = operation()
            breaker.record_success()
            component.recover()
            return result

        except Exception as exc:
            breaker.record_failure()
            component.fail(str(exc))
            logger.warning("%s failed: %s", name, exc)

            if failure_mode == FailureMode.FALLBACK:
                if dependency.policy == DependencyPolicy.REQUIRED:
                    raise ResilienceError(
                        f"Fallback prohibited for required dependency: {name}"
                    ) from exc
                component.degrade(str(exc))
                return dependency.fallback_value

            if failure_mode == FailureMode.SKIP:
                if dependency.policy == DependencyPolicy.REQUIRED:
                    raise ResilienceError(
                        f"Cannot skip required dependency: {name}"
                    ) from exc
                component.degrade(str(exc))
                return None

            raise ResilienceError(f"{name} operation failed") from exc

    def health_report(self) -> dict[str, Any]:
        return {
            name: {
                "state": component.state.value,
                "critical": component.critical,
                "failures": component.failure_count,
                "recoveries": component.recovery_count,
                "last_error": component.last_error,
                "circuit": self.breakers[name].state.value,
            }
            for name, component in self.components.items()
        }

    def system_state(self) -> str:
        states = [c.state for c in self.components.values()]

        if any(
            c.critical and c.state == ComponentState.FAILED
            for c in self.components.values()
        ):
            return "UNAVAILABLE"

        if ComponentState.FAILED in states or ComponentState.DEGRADED in states:
            return "DEGRADED"

        return "HEALTHY"


class Service:
    """Simulates an e-commerce service with independent capabilities."""

    def __init__(self):
        self.manager = DependencyManager()

        self.manager.register(
            "product_catalog",
            critical=True,
            policy=DependencyPolicy.REQUIRED,
        )
        self.manager.register(
            "inventory",
            critical=True,
            policy=DependencyPolicy.REQUIRED,
        )
        self.manager.register(
            "recommendations",
            critical=False,
            policy=DependencyPolicy.OPTIONAL,
            fallback_value=[],
        )
        self.manager.register(
            "personalization",
            critical=False,
            policy=DependencyPolicy.OPTIONAL,
            fallback_value={"mode": "default"},
        )
        self.manager.register(
            "analytics",
            critical=False,
            policy=DependencyPolicy.OPTIONAL,
            fallback_value={"queued": False},
        )

    def browse(
        self,
        product_id: str,
        failures: set[str] | None = None,
    ) -> OperationResult:
        started = time.perf_counter()
        failures = failures or set()
        errors: list[str] = []
        unavailable: list[str] = []

        def simulated(name: str, value: Any) -> Callable[[], Any]:
            def execute():
                if name in failures:
                    raise ConnectionError(f"{name} service unavailable")
                return value
            return execute

        try:
            product = self.manager.execute(
                "product_catalog",
                simulated(
                    "product_catalog",
                    {"id": product_id, "name": "Enterprise Laptop"},
                ),
            )

            inventory = self.manager.execute(
                "inventory",
                simulated("inventory", {"available": 12}),
            )

        except ResilienceError as exc:
            errors.append(str(exc))
            return OperationResult(
                operation_id=str(uuid.uuid4()),
                success=False,
                mode=self.manager.system_state(),
                data=None,
                errors=errors,
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        recommendations = self.manager.execute(
            "recommendations",
            simulated("recommendations", ["Laptop Stand", "USB Hub"]),
            FailureMode.FALLBACK,
        )

        if "recommendations" in failures:
            unavailable.append("recommendations")

        personalization = self.manager.execute(
            "personalization",
            simulated("personalization", {"mode": "customer-specific"}),
            FailureMode.FALLBACK,
        )

        if "personalization" in failures:
            unavailable.append("personalization")

        analytics = self.manager.execute(
            "analytics",
            simulated("analytics", {"event_recorded": True}),
            FailureMode.FALLBACK,
        )

        if "analytics" in failures:
            unavailable.append("analytics")

        return OperationResult(
            operation_id=str(uuid.uuid4()),
            success=True,
            mode=self.manager.system_state(),
            data={
                "product": product,
                "inventory": inventory,
                "recommendations": recommendations,
                "personalization": personalization,
                "analytics": analytics,
            },
            unavailable_features=unavailable,
            duration_ms=(time.perf_counter() - started) * 1000,
        )


def demonstrate_circuit_breaker() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state == CircuitState.OPEN
    assert not breaker.allow_request()

    time.sleep(0.11)

    assert breaker.allow_request()
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


def save_report(
    report: dict[str, Any],
    destination: str = "resilience_report.json",
) -> None:
    path = Path(destination)

    # Do not overwrite a directory or write outside the selected location.
    if path.exists() and path.is_dir():
        raise IsADirectoryError(destination)

    temporary = path.with_suffix(path.suffix + ".tmp")

    try:
        temporary.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    service = Service()

    print("\nSCENARIO 1: Normal operation")
    normal = service.browse("PROD-1001")
    print(json.dumps(asdict(normal), indent=2))

    print("\nSCENARIO 2: Optional services unavailable")
    degraded = service.browse(
        "PROD-1002",
        failures={"recommendations", "personalization", "analytics"},
    )
    print(json.dumps(asdict(degraded), indent=2))

    assert degraded.success
    assert degraded.mode == "DEGRADED"
    assert len(degraded.unavailable_features) == 3
    assert degraded.data["recommendations"] == []

    print("\nSCENARIO 3: Required inventory service unavailable")
    unavailable = service.browse(
        "PROD-1003",
        failures={"inventory"},
    )
    print(json.dumps(asdict(unavailable), indent=2))

    assert not unavailable.success

    print("\nSCENARIO 4: Recovery")
    recovered = service.browse("PROD-1004")
    assert recovered.success

    print("\nCOMPONENT HEALTH")
    health = service.manager.health_report()
    print(json.dumps(health, indent=2))

    save_report(health)
    demonstrate_circuit_breaker()

    print("\nAll resilience assertions passed.")


if __name__ == "__main__":
    main()
