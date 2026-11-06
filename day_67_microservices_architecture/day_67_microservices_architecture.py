from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s"
)
logger = logging.getLogger("microservices")


class ServiceStatus(str, Enum):
    REGISTERED = "registered"
    DEPLOYING = "deploying"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CompatibilityError(Exception):
    pass


class DeploymentError(Exception):
    pass


class DependencyError(Exception):
    pass


def validate_name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{1,48}", value
    ):
        raise ValueError(f"Invalid service name: {value!r}")
    return value


def validate_version(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d+\.\d+\.\d+", value
    ):
        raise ValueError(f"Invalid semantic version: {value!r}")
    return value


def version_tuple(version: str) -> tuple[int, int, int]:
    return tuple(map(int, validate_version(version).split(".")))


@dataclass(frozen=True)
class ServiceContract:
    service_name: str
    version: str
    api_version: int
    endpoints: tuple[str, ...]
    backward_compatible: bool = True

    def __post_init__(self):
        validate_name(self.service_name)
        validate_version(self.version)

        if self.api_version < 1:
            raise ValueError("API version must be positive.")

        if not self.endpoints:
            raise ValueError("A service must expose at least one endpoint.")

        if len(set(self.endpoints)) != len(self.endpoints):
            raise ValueError("Duplicate endpoints are not allowed.")

        for endpoint in self.endpoints:
            if not endpoint.startswith("/"):
                raise ValueError("Endpoints must start with '/'.")


@dataclass
class Service:
    name: str
    description: str
    contract: ServiceContract
    dependencies: set[str] = field(default_factory=set)
    status: ServiceStatus = ServiceStatus.REGISTERED
    deployment_count: int = 0
    instance_count: int = 1

    def __post_init__(self):
        validate_name(self.name)

        if self.contract.service_name != self.name:
            raise ValueError("Contract service name mismatch.")

        if not self.description.strip():
            raise ValueError("Service description cannot be empty.")

        if self.instance_count < 1:
            raise ValueError("At least one instance is required.")

        for dependency in self.dependencies:
            validate_name(dependency)


@dataclass
class Deployment:
    deployment_id: str
    service_name: str
    version: str
    status: DeploymentStatus
    timestamp: str
    previous_version: str | None = None
    message: str = ""


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    source_service: str
    payload: dict[str, Any]
    timestamp: str


class ServiceRegistry:
    """Maintains service metadata and dependency relationships."""

    def __init__(self):
        self.services: dict[str, Service] = {}

    def register(self, service: Service) -> None:
        if service.name in self.services:
            raise ValueError(f"{service.name} already registered.")

        self.services[service.name] = service
        logger.info("Registered service: %s", service.name)

    def get(self, name: str) -> Service:
        if name not in self.services:
            raise KeyError(f"Unknown service: {name}")
        return self.services[name]

    def validate_dependencies(self, name: str) -> None:
        service = self.get(name)

        missing = service.dependencies - self.services.keys()

        if missing:
            raise DependencyError(
                f"Missing dependencies for {name}: {sorted(missing)}"
            )

        self.dependency_order()

    def dependency_order(self) -> list[str]:
        """Topological ordering also detects circular dependencies."""
        visited: set[str] = set()
        active: set[str] = set()
        result: list[str] = []

        def visit(name: str):
            if name in active:
                raise DependencyError(
                    f"Circular dependency detected at {name}"
                )

            if name in visited:
                return

            active.add(name)

            service = self.get(name)

            for dependency in sorted(service.dependencies):
                if dependency not in self.services:
                    raise DependencyError(
                        f"{name} depends on missing {dependency}"
                    )
                visit(dependency)

            active.remove(name)
            visited.add(name)
            result.append(name)

        for name in sorted(self.services):
            visit(name)

        return result

    def consumers(self, name: str) -> list[str]:
        self.get(name)
        return sorted(
            service.name
            for service in self.services.values()
            if name in service.dependencies
        )

    def inventory(self) -> list[dict[str, Any]]:
        return [
            {
                "name": service.name,
                "version": service.contract.version,
                "api_version": service.contract.api_version,
                "status": service.status.value,
                "dependencies": sorted(service.dependencies),
                "instances": service.instance_count,
                "deployments": service.deployment_count
            }
            for service in sorted(
                self.services.values(), key=lambda item: item.name
            )
        ]


class ContractValidator:
    """Checks whether consumers can continue using a provider contract."""

    @staticmethod
    def validate_upgrade(
        old: ServiceContract,
        new: ServiceContract
    ) -> None:
        if old.service_name != new.service_name:
            raise CompatibilityError("Service identity cannot change.")

        if new.api_version < old.api_version:
            raise CompatibilityError("API version cannot move backwards.")

        removed = set(old.endpoints) - set(new.endpoints)

        if removed and new.api_version <= old.api_version:
            raise CompatibilityError(
                f"Breaking endpoint removal without API version change: "
                f"{sorted(removed)}"
            )

        if (
            removed
            and new.api_version > old.api_version
            and new.backward_compatible
        ):
            raise CompatibilityError(
                "A breaking API change cannot be marked backward compatible."
            )


class DeploymentManager:
    """Deploys one service without requiring application-wide deployment."""

    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self.history: list[Deployment] = []

    def deploy(
        self,
        service_name: str,
        new_contract: ServiceContract,
        health_check_passed: bool = True
    ) -> Deployment:
        service = self.registry.get(service_name)

        self.registry.validate_dependencies(service_name)

        if new_contract.service_name != service_name:
            raise DeploymentError("Deployment identity mismatch.")

        ContractValidator.validate_upgrade(
            service.contract, new_contract
        )

        previous_version = service.contract.version

        deployment = Deployment(
            deployment_id=str(uuid.uuid4()),
            service_name=service_name,
            version=new_contract.version,
            status=DeploymentStatus.PENDING,
            timestamp=datetime.now(timezone.utc).isoformat(),
            previous_version=previous_version
        )

        service.status = ServiceStatus.DEPLOYING

        try:
            if not health_check_passed:
                raise DeploymentError(
                    "Health check failed after deployment."
                )

            service.contract = new_contract
            service.deployment_count += 1
            service.status = ServiceStatus.HEALTHY

            deployment.status = DeploymentStatus.SUCCESS
            deployment.message = "Deployment completed successfully."

        except Exception as exc:
            service.status = ServiceStatus.HEALTHY
            deployment.status = DeploymentStatus.ROLLED_BACK
            deployment.message = str(exc)

            logger.error(
                "Deployment rolled back for %s: %s",
                service_name,
                exc
            )

        self.history.append(deployment)
        return deployment

    def rollback(
        self,
        service_name: str,
        target_version: str
    ) -> Deployment:
        service = self.registry.get(service_name)
        validate_version(target_version)

        previous = next(
            (
                item for item in reversed(self.history)
                if item.service_name == service_name
                and item.version == target_version
                and item.status == DeploymentStatus.SUCCESS
            ),
            None
        )

        if previous is None:
            raise DeploymentError(
                f"No successful deployment found for {target_version}"
            )

        old_contract = next(
            (
                contract for contract in getattr(
                    self, "_contract_history", []
                )
                if contract.service_name == service_name
                and contract.version == target_version
            ),
            None
        )

        if old_contract is None:
            raise DeploymentError(
                "Contract history is unavailable for this rollback."
            )

        service.contract = old_contract
        service.status = ServiceStatus.HEALTHY

        rollback = Deployment(
            deployment_id=str(uuid.uuid4()),
            service_name=service_name,
            version=target_version,
            status=DeploymentStatus.SUCCESS,
            timestamp=datetime.now(timezone.utc).isoformat(),
            message="Rollback completed."
        )

        self.history.append(rollback)
        return rollback

    def enable_contract_history(self):
        self._contract_history = []


class EventBus:
    """In-memory demonstration of asynchronous event-driven communication."""

    def __init__(self):
        self.subscribers: dict[
            str, list[tuple[str, Any]]
        ] = {}
        self.processed_events: set[str] = set()
        self.dead_letters: list[Event] = []

    def subscribe(self, event_type: str, handler) -> None:
        if not callable(handler):
            raise TypeError("Handler must be callable.")

        self.subscribers.setdefault(event_type, []).append(
            (str(uuid.uuid4()), handler)
        )

    def publish(self, event: Event) -> int:
        if not event.event_id or not event.event_type:
            raise ValueError("Invalid event.")

        if event.event_id in self.processed_events:
            logger.info("Duplicate event ignored: %s", event.event_id)
            return 0

        handlers = self.subscribers.get(event.event_type, [])
        successful = 0
        failures = 0

        for _, handler in handlers:
            try:
                handler(event)
                successful += 1
            except Exception:
                failures += 1
                logger.exception("Event handler failed.")

        # This in-memory implementation is illustrative. A production
        # consumer must track delivery independently for each subscriber.
        if failures:
            self.dead_letters.append(event)

        self.processed_events.add(event.event_id)
        return successful


def create_contract(
    name: str,
    version: str,
    api_version: int,
    endpoints: tuple[str, ...]
) -> ServiceContract:
    return ServiceContract(
        service_name=name,
        version=version,
        api_version=api_version,
        endpoints=endpoints
    )


def run_demonstration():
    print("\nMICROSERVICES ARCHITECTURE SIMULATOR")
    print("=" * 55)

    registry = ServiceRegistry()

    # Independent business capabilities form separate service boundaries.
    payment = Service(
        name="payment-service",
        description="Processes customer payments.",
        contract=create_contract(
            "payment-service", "1.0.0", 1,
            ("/payments", "/payments/{id}")
        )
    )

    inventory = Service(
        name="inventory-service",
        description="Maintains stock availability.",
        contract=create_contract(
            "inventory-service", "1.0.0", 1,
            ("/inventory", "/inventory/{id}")
        )
    )

    order = Service(
        name="order-service",
        description="Coordinates customer orders.",
        contract=create_contract(
            "order-service", "1.0.0", 1,
            ("/orders", "/orders/{id}")
        ),
        dependencies={"payment-service", "inventory-service"}
    )

    for service in (payment, inventory, order):
        registry.register(service)

    print("\nDEPENDENCY ORDER")
    print(" -> ".join(registry.dependency_order()))

    print("\nSERVICE INVENTORY")
    print(json.dumps(registry.inventory(), indent=2))

    print("\nINDEPENDENT DEPLOYMENT")

    manager = DeploymentManager(registry)
    manager.enable_contract_history()

    # Preserve the previous contract for a rollback demonstration.
    manager._contract_history.append(payment.contract)

    new_payment_contract = create_contract(
        "payment-service",
        "1.1.0",
        1,
        (
            "/payments",
            "/payments/{id}",
            "/payments/{id}/status"
        )
    )

    deployment = manager.deploy(
        "payment-service",
        new_payment_contract
    )

    print(asdict(deployment))

    print("\nFAILED DEPLOYMENT")

    failed_contract = create_contract(
        "inventory-service",
        "1.1.0",
        1,
        ("/inventory", "/inventory/{id}")
    )

    failed = manager.deploy(
        "inventory-service",
        failed_contract,
        health_check_passed=False
    )

    print(asdict(failed))

    print("\nROLLBACK")

    rollback = manager.rollback(
        "payment-service", "1.0.0"
    )

    print(asdict(rollback))

    print("\nEVENT-DRIVEN COMMUNICATION")

    event_bus = EventBus()
    received_events = []

    def reserve_inventory(event: Event):
        received_events.append(event.payload["order_id"])
        print(
            "Inventory received order:",
            event.payload["order_id"]
        )

    event_bus.subscribe(
        "order.created",
        reserve_inventory
    )

    event = Event(
        event_id=str(uuid.uuid4()),
        event_type="order.created",
        source_service="order-service",
        payload={"order_id": "ORD-1001"},
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    event_bus.publish(event)

    # Duplicate delivery must not execute a handler twice.
    event_bus.publish(event)

    assert received_events == ["ORD-1001"]

    print("\nDEPENDENCY VALIDATION")

    try:
        registry.register(
            Service(
                name="notification-service",
                description="Sends customer notifications.",
                contract=create_contract(
                    "notification-service", "1.0.0", 1,
                    ("/notifications",)
                ),
                dependencies={"missing-service"}
            )
        )

        registry.validate_dependencies("notification-service")

    except DependencyError as exc:
        print("Expected dependency error:", exc)

    print("\nCONTRACT VALIDATION")

    try:
        breaking_contract = create_contract(
            "payment-service",
            "2.0.0",
            1,
            ("/payments",)
        )

        ContractValidator.validate_upgrade(
            payment.contract,
            breaking_contract
        )

    except CompatibilityError as exc:
        print("Expected compatibility error:", exc)

    print("\nFINAL SERVICE INVENTORY")
    print(json.dumps(registry.inventory(), indent=2))

    print("\nDEPLOYMENT HISTORY")

    for item in manager.history:
        print(
            item.service_name,
            item.version,
            item.status.value,
            item.message
        )


if __name__ == "__main__":
    run_demonstration()
