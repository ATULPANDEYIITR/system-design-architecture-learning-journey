#!/usr/bin/env python3
"""
Service Discovery: Registration, Discovery, and Health Checks

A self-contained service registry demonstrating:
- Service registration and deregistration
- Instance identity and metadata
- TTL-based leases and expiration
- Service discovery and filtering
- Active and passive health monitoring
- Health-state transitions
- Round-robin load balancing
- Concurrent registry access
- Retry and failure handling
- JSON persistence
- Automated assertions
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import uuid

from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("service-discovery")


class ServiceError(Exception):
    """Base exception for registry operations."""


class RegistrationError(ServiceError):
    pass


class ServiceNotFoundError(ServiceError):
    pass


class InvalidTransitionError(ServiceError):
    pass


class HealthStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DRAINING = "DRAINING"


@dataclass
class ServiceInstance:
    instance_id: str
    service_name: str
    host: str
    port: int
    version: str
    metadata: dict[str, str] = field(default_factory=dict)
    status: HealthStatus = HealthStatus.UNKNOWN
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    lease_seconds: int = 30
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    def __post_init__(self):
        if not self.service_name.strip():
            raise ValueError("Service name cannot be empty")

        if not self.host.strip():
            raise ValueError("Host cannot be empty")

        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")

        if self.lease_seconds <= 0:
            raise ValueError("Lease duration must be positive")

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def is_expired(self, now: float) -> bool:
        return now - self.last_heartbeat > self.lease_seconds


class HealthMonitor:
    """Applies consecutive-success and failure thresholds."""

    def __init__(
        self,
        failure_threshold: int = 2,
        recovery_threshold: int = 2,
    ):
        if failure_threshold < 1 or recovery_threshold < 1:
            raise ValueError("Health thresholds must be positive")

        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold

    def record_result(
        self,
        instance: ServiceInstance,
        healthy: bool,
    ) -> HealthStatus:

        if instance.status == HealthStatus.DRAINING:
            return instance.status

        if healthy:
            instance.consecutive_failures = 0
            instance.consecutive_successes += 1

            if instance.consecutive_successes >= self.recovery_threshold:
                instance.status = HealthStatus.HEALTHY
        else:
            instance.consecutive_successes = 0
            instance.consecutive_failures += 1

            if instance.consecutive_failures >= self.failure_threshold:
                instance.status = HealthStatus.UNHEALTHY

        return instance.status


class ServiceRegistry:
    """
    Thread-safe in-memory service registry.

    Registration:
        service_name + instance_id -> instance

    Discovery:
        service_name -> healthy, non-expired instances
    """

    def __init__(self):
        self._instances: dict[str, ServiceInstance] = {}
        self._lock = threading.RLock()
        self._round_robin: dict[str, int] = {}
        self.health_monitor = HealthMonitor()

    def register(self, instance: ServiceInstance) -> None:
        with self._lock:
            existing = self._instances.get(instance.instance_id)

            if existing and existing.service_name != instance.service_name:
                raise RegistrationError(
                    "Instance ID already belongs to another service"
                )

            instance.last_heartbeat = time.time()
            self._instances[instance.instance_id] = instance

            logger.info(
                "Registered %s at %s",
                instance.service_name,
                instance.endpoint,
            )

    def deregister(self, instance_id: str) -> bool:
        with self._lock:
            instance = self._instances.pop(instance_id, None)

            if instance is None:
                return False

            logger.info("Deregistered %s", instance_id)
            return True

    def heartbeat(self, instance_id: str) -> None:
        with self._lock:
            instance = self._instances.get(instance_id)

            if instance is None:
                raise ServiceNotFoundError(instance_id)

            instance.last_heartbeat = time.time()

    def record_health(
        self,
        instance_id: str,
        healthy: bool,
    ) -> HealthStatus:
        with self._lock:
            instance = self._instances.get(instance_id)

            if instance is None:
                raise ServiceNotFoundError(instance_id)

            result = self.health_monitor.record_result(
                instance,
                healthy,
            )

            logger.info(
                "Health update: %s -> %s",
                instance_id,
                result.value,
            )

            return result

    def set_draining(self, instance_id: str) -> None:
        with self._lock:
            instance = self._instances.get(instance_id)

            if instance is None:
                raise ServiceNotFoundError(instance_id)

            instance.status = HealthStatus.DRAINING

    def remove_expired(self, now: Optional[float] = None) -> list[str]:
        now = time.time() if now is None else now

        with self._lock:
            expired = [
                key
                for key, instance in self._instances.items()
                if instance.is_expired(now)
            ]

            for key in expired:
                del self._instances[key]

            if expired:
                logger.warning("Removed %d expired instances", len(expired))

            return expired

    def discover(
        self,
        service_name: str,
        version: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> list[ServiceInstance]:

        now = time.time()

        with self._lock:
            results = [
                instance
                for instance in self._instances.values()
                if instance.service_name == service_name
                and instance.status == HealthStatus.HEALTHY
                and not instance.is_expired(now)
                and (
                    version is None
                    or instance.version == version
                )
                and (
                    metadata is None
                    or all(
                        instance.metadata.get(key) == value
                        for key, value in metadata.items()
                    )
                )
            ]

            return sorted(results, key=lambda item: item.instance_id)

    def select_instance(
        self,
        service_name: str,
    ) -> ServiceInstance:

        with self._lock:
            available = self.discover(service_name)

            if not available:
                raise ServiceNotFoundError(
                    f"No healthy instance available: {service_name}"
                )

            index = self._round_robin.get(service_name, 0)
            selected = available[index % len(available)]

            self._round_robin[service_name] = (
                index + 1
            ) % len(available)

            return selected

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [
                {
                    **asdict(instance),
                    "status": instance.status.value,
                }
                for instance in self._instances.values()
            ]

    def save(self, filename: str) -> None:
        """Persist a registry snapshot using atomic replacement."""
        path = Path(filename)
        temporary = path.with_suffix(path.suffix + ".tmp")

        with self._lock:
            payload = self.snapshot()

        try:
            temporary.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def load(self, filename: str) -> None:
        path = Path(filename)

        payload = json.loads(path.read_text(encoding="utf-8"))

        restored = {}

        for record in payload:
            record["status"] = HealthStatus(record["status"])
            instance = ServiceInstance(**record)
            restored[instance.instance_id] = instance

        with self._lock:
            self._instances.update(restored)


class ServiceClient:
    """Discovers service instances and performs simulated requests."""

    def __init__(self, registry: ServiceRegistry):
        self.registry = registry

    def request(
        self,
        service_name: str,
        attempts: int = 3,
    ) -> str:

        if attempts < 1:
            raise ValueError("At least one attempt is required")

        for attempt in range(1, attempts + 1):
            try:
                instance = self.registry.select_instance(service_name)

                logger.info(
                    "Request attempt %d -> %s",
                    attempt,
                    instance.endpoint,
                )

                # Simulate a network response.
                if random.random() < 0.1:
                    raise ConnectionError("Simulated connection failure")

                return (
                    f"Response from {service_name} "
                    f"at {instance.endpoint}"
                )

            except (ServiceNotFoundError, ConnectionError) as error:
                logger.warning("Attempt %d failed: %s", attempt, error)

                if attempt == attempts:
                    raise ServiceError(
                        f"Request failed after {attempts} attempts"
                    ) from error

        raise ServiceError("Unexpected request failure")


def create_instance(
    service_name: str,
    host: str,
    port: int,
    version: str,
    metadata: Optional[dict[str, str]] = None,
) -> ServiceInstance:

    return ServiceInstance(
        instance_id=str(uuid.uuid4()),
        service_name=service_name,
        host=host,
        port=port,
        version=version,
        metadata=metadata or {},
        lease_seconds=60,
    )


def run_tests(registry: ServiceRegistry) -> None:
    """Verify registration, health transitions and expiration."""

    test_instance = create_instance(
        "test-service",
        "127.0.0.1",
        9090,
        "1.0.0",
    )

    registry.register(test_instance)

    assert registry.discover("test-service") == []

    registry.record_health(test_instance.instance_id, True)
    registry.record_health(test_instance.instance_id, True)

    assert len(registry.discover("test-service")) == 1

    registry.record_health(test_instance.instance_id, False)
    registry.record_health(test_instance.instance_id, False)

    assert registry.discover("test-service") == []

    registry.heartbeat(test_instance.instance_id)

    assert registry.deregister(test_instance.instance_id)
    assert not registry.deregister(test_instance.instance_id)

    expired = create_instance(
        "expired-service",
        "127.0.0.1",
        9091,
        "1.0.0",
    )

    registry.register(expired)

    removed = registry.remove_expired(
        now=expired.last_heartbeat + expired.lease_seconds + 1
    )

    assert expired.instance_id in removed

    try:
        registry.select_instance("missing-service")
    except ServiceNotFoundError:
        pass
    else:
        raise AssertionError("Missing service should not be selectable")

    print("All registry tests passed.")


def main():
    registry = ServiceRegistry()

    services = [
        create_instance(
            "payment-service",
            "10.0.1.10",
            8001,
            "2.1.0",
            {"region": "ap-south-1", "environment": "production"},
        ),
        create_instance(
            "payment-service",
            "10.0.1.11",
            8001,
            "2.1.0",
            {"region": "ap-south-1", "environment": "production"},
        ),
        create_instance(
            "inventory-service",
            "10.0.2.10",
            8002,
            "1.4.0",
            {"region": "ap-south-1", "environment": "production"},
        ),
    ]

    for instance in services:
        registry.register(instance)

        registry.record_health(instance.instance_id, True)
        registry.record_health(instance.instance_id, True)

    print("\nDISCOVERED PAYMENT INSTANCES")

    for instance in registry.discover(
        "payment-service",
        version="2.1.0",
        metadata={"environment": "production"},
    ):
        print(instance.endpoint, instance.status.value)

    client = ServiceClient(registry)

    print("\nSERVICE REQUEST")

    try:
        print(client.request("payment-service"))
    except ServiceError as error:
        logger.error("%s", error)

    print("\nROUND-ROBIN SELECTION")

    for _ in range(4):
        print(registry.select_instance("payment-service").endpoint)

    print("\nDRAINING INSTANCE")

    registry.set_draining(services[0].instance_id)

    print(
        "Available:",
        len(registry.discover("payment-service")),
    )

    print("\nREGISTRY SNAPSHOT")

    print(json.dumps(registry.snapshot(), indent=2))

    run_tests(registry)


if __name__ == "__main__":
    main()
