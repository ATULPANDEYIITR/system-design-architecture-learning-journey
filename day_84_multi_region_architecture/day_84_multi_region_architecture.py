#!/usr/bin/env python3
"""
Multi-Region Architecture: Regional Failover and Geographic Redundancy.

Demonstrates:
- Multi-region deployment modeling
- Active-passive regional architecture
- Regional health monitoring
- Replication lag and data consistency
- Automatic failover
- Recovery Time Objective (RTO)
- Recovery Point Objective (RPO)
- Traffic routing
- Failback and disaster recovery
- Failure simulation and validation

Run:
    python multi_region_architecture.py
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("multi_region")


class RegionStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RECOVERING = "recovering"


class DeploymentRole(Enum):
    PRIMARY = "primary"
    STANDBY = "standby"
    DISABLED = "disabled"


class ArchitectureMode(Enum):
    ACTIVE_PASSIVE = "active-passive"
    ACTIVE_ACTIVE = "active-active"


class FailoverStatus(Enum):
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class Region:
    region_id: str
    location: str
    availability_zone: str
    status: RegionStatus = RegionStatus.HEALTHY
    role: DeploymentRole = DeploymentRole.STANDBY
    replication_lag_seconds: float = 0.0
    latency_ms: float = 30.0
    capacity: int = 1000
    current_load: int = 0
    data_version: int = 0
    last_health_check: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def validate(self) -> None:
        if not self.region_id.strip():
            raise ValueError("Region ID cannot be empty.")

        if self.replication_lag_seconds < 0:
            raise ValueError("Replication lag cannot be negative.")

        if self.latency_ms < 0:
            raise ValueError("Latency cannot be negative.")

        if self.capacity <= 0:
            raise ValueError("Region capacity must be positive.")

        if not 0 <= self.current_load <= self.capacity:
            raise ValueError("Regional load exceeds capacity.")


@dataclass
class FailoverEvent:
    event_id: str
    source_region: str
    target_region: str
    status: FailoverStatus
    reason: str
    timestamp: datetime
    rpo_seconds: float
    estimated_rto_seconds: float


@dataclass
class FailoverPolicy:
    maximum_replication_lag: float = 5.0
    minimum_free_capacity: float = 0.20
    maximum_latency_ms: float = 250.0
    require_healthy_target: bool = True
    automatic_failover: bool = True

    def __post_init__(self):
        if self.maximum_replication_lag < 0:
            raise ValueError("Maximum replication lag cannot be negative.")

        if not 0 <= self.minimum_free_capacity < 1:
            raise ValueError("Invalid minimum free capacity.")

        if self.maximum_latency_ms <= 0:
            raise ValueError("Maximum latency must be positive.")


class MultiRegionManager:

    def __init__(
        self,
        mode: ArchitectureMode = ArchitectureMode.ACTIVE_PASSIVE,
        policy: Optional[FailoverPolicy] = None,
    ):
        self.mode = mode
        self.policy = policy or FailoverPolicy()
        self.regions: dict[str, Region] = {}
        self.events: list[FailoverEvent] = []
        self.primary_region: Optional[str] = None
        self.request_history: dict[str, dict] = {}
        self.routing_enabled = True

    def register_region(self, region: Region) -> None:
        region.validate()

        if region.region_id in self.regions:
            raise ValueError("Region already registered.")

        if region.role == DeploymentRole.PRIMARY:
            if self.primary_region is not None:
                raise ValueError("A primary region already exists.")

            self.primary_region = region.region_id

        self.regions[region.region_id] = region

        logger.info("Registered region: %s", region.region_id)

    def update_health(
        self,
        region_id: str,
        status: RegionStatus,
        latency_ms: Optional[float] = None,
        replication_lag: Optional[float] = None,
    ) -> None:
        region = self._get_region(region_id)

        if latency_ms is not None:
            if latency_ms < 0:
                raise ValueError("Latency cannot be negative.")
            region.latency_ms = latency_ms

        if replication_lag is not None:
            if replication_lag < 0:
                raise ValueError("Replication lag cannot be negative.")
            region.replication_lag_seconds = replication_lag

        region.status = status
        region.last_health_check = datetime.now(timezone.utc)

        logger.info(
            "Health updated: %s -> %s",
            region_id,
            status.value,
        )

    def _get_region(self, region_id: str) -> Region:
        if region_id not in self.regions:
            raise KeyError(f"Unknown region: {region_id}")

        return self.regions[region_id]

    def is_eligible(self, region: Region) -> tuple[bool, str]:
        if region.status != RegionStatus.HEALTHY:
            return False, "Region is not healthy."

        if region.latency_ms > self.policy.maximum_latency_ms:
            return False, "Regional latency exceeds policy."

        if region.replication_lag_seconds > (
            self.policy.maximum_replication_lag
        ):
            return False, "Replication lag exceeds the RPO threshold."

        free_capacity = (
            region.capacity - region.current_load
        ) / region.capacity

        if free_capacity < self.policy.minimum_free_capacity:
            return False, "Insufficient available capacity."

        return True, "Region satisfies failover policy."

    def available_targets(self) -> list[Region]:
        candidates = []

        for region in self.regions.values():
            if region.region_id == self.primary_region:
                continue

            eligible, _ = self.is_eligible(region)

            if eligible:
                candidates.append(region)

        return sorted(
            candidates,
            key=lambda region: (
                region.replication_lag_seconds,
                region.latency_ms,
                -(
                    region.capacity - region.current_load
                ),
            ),
        )

    def perform_failover(
        self,
        target_region_id: str,
        reason: str = "Regional failure",
    ) -> FailoverEvent:

        source_id = self.primary_region

        if source_id is None:
            raise RuntimeError("No primary region is configured.")

        source = self._get_region(source_id)
        target = self._get_region(target_region_id)

        if source_id == target_region_id:
            raise ValueError("Source and target must differ.")

        eligible, explanation = self.is_eligible(target)

        if not eligible:
            event = self._create_event(
                source_id,
                target_region_id,
                FailoverStatus.REJECTED,
                explanation,
                target.replication_lag_seconds,
                0.0,
            )
            self.events.append(event)
            return event

        if self.mode == ArchitectureMode.ACTIVE_PASSIVE:
            if target.role != DeploymentRole.STANDBY:
                raise RuntimeError(
                    "Target is not configured as a standby region."
                )

        # This is a local simulation. Production systems must use
        # distributed fencing, leader epochs and atomic promotion.
        estimated_rto = 2.0

        source.role = DeploymentRole.STANDBY
        target.role = DeploymentRole.PRIMARY
        self.primary_region = target_region_id

        event = self._create_event(
            source_id,
            target_region_id,
            FailoverStatus.SUCCESS,
            reason,
            target.replication_lag_seconds,
            estimated_rto,
        )

        self.events.append(event)

        logger.warning(
            "Failover completed: %s -> %s",
            source_id,
            target_region_id,
        )

        return event

    def _create_event(
        self,
        source: str,
        target: str,
        status: FailoverStatus,
        reason: str,
        rpo: float,
        rto: float,
    ) -> FailoverEvent:

        return FailoverEvent(
            event_id=str(uuid.uuid4()),
            source_region=source,
            target_region=target,
            status=status,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
            rpo_seconds=rpo,
            estimated_rto_seconds=rto,
        )

    def route_request(
        self,
        request_id: str,
        write: bool = False,
    ) -> dict:

        if not self.routing_enabled:
            raise RuntimeError("Traffic routing is disabled.")

        if not request_id.strip():
            raise ValueError("Request ID cannot be empty.")

        # Idempotency prevents duplicate processing in this simulation.
        if request_id in self.request_history:
            return self.request_history[request_id]

        if self.primary_region is None:
            raise RuntimeError("No active primary region.")

        region = self._get_region(self.primary_region)

        if region.status != RegionStatus.HEALTHY:
            raise RuntimeError("Primary region is unhealthy.")

        if region.current_load >= region.capacity:
            raise RuntimeError("Primary region has no available capacity.")

        region.current_load += 1

        if write:
            region.data_version += 1

        result = {
            "request_id": request_id,
            "region": region.region_id,
            "write": write,
            "data_version": region.data_version,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        self.request_history[request_id] = result

        return result

    def replicate_to_standby(self) -> None:
        if self.primary_region is None:
            raise RuntimeError("No primary region.")

        primary = self._get_region(self.primary_region)

        for region in self.regions.values():
            if region.region_id == self.primary_region:
                continue

            if region.status == RegionStatus.HEALTHY:
                region.data_version = max(
                    region.data_version,
                    primary.data_version,
                )

                region.replication_lag_seconds = 0.0

    def recover_region(self, region_id: str) -> None:
        region = self._get_region(region_id)

        region.status = RegionStatus.RECOVERING
        region.current_load = 0
        region.last_health_check = datetime.now(timezone.utc)

        logger.info("Region recovering: %s", region_id)

    def complete_recovery(
        self,
        region_id: str,
        synchronized_version: int,
    ) -> None:
        region = self._get_region(region_id)

        if synchronized_version < 0:
            raise ValueError("Invalid data version.")

        if self.primary_region is None:
            raise RuntimeError("No primary region.")

        primary = self._get_region(self.primary_region)

        if synchronized_version != primary.data_version:
            raise ValueError(
                "Recovery cannot complete before data synchronization."
            )

        region.data_version = synchronized_version
        region.replication_lag_seconds = 0.0
        region.status = RegionStatus.HEALTHY

        # Recovered regions remain standby until controlled failback.
        region.role = DeploymentRole.STANDBY

    def failback(self, original_region_id: str) -> FailoverEvent:
        target = self._get_region(original_region_id)

        if target.status != RegionStatus.HEALTHY:
            raise RuntimeError("Original region is not healthy.")

        if self.primary_region is None:
            raise RuntimeError("No active primary region.")

        current = self._get_region(self.primary_region)

        if target.data_version != current.data_version:
            raise RuntimeError(
                "Failback rejected: data synchronization incomplete."
            )

        return self.perform_failover(
            original_region_id,
            "Controlled regional failback",
        )

    def report(self) -> dict:
        return {
            "architecture": self.mode.value,
            "primary_region": self.primary_region,
            "regions": [
                {
                    "id": region.region_id,
                    "location": region.location,
                    "status": region.status.value,
                    "role": region.role.value,
                    "replication_lag": region.replication_lag_seconds,
                    "latency_ms": region.latency_ms,
                    "capacity": region.capacity,
                    "load": region.current_load,
                    "data_version": region.data_version,
                }
                for region in self.regions.values()
            ],
            "failover_events": len(self.events),
        }


def main() -> None:

    manager = MultiRegionManager(
        policy=FailoverPolicy(
            maximum_replication_lag=5.0,
            minimum_free_capacity=0.20,
            maximum_latency_ms=250.0,
        )
    )

    manager.register_region(
        Region(
            "ap-south-1",
            "Mumbai, India",
            "zone-a",
            role=DeploymentRole.PRIMARY,
        )
    )

    manager.register_region(
        Region(
            "ap-south-2",
            "Hyderabad, India",
            "zone-b",
            role=DeploymentRole.STANDBY,
            latency_ms=42,
        )
    )

    manager.register_region(
        Region(
            "eu-west-1",
            "Ireland",
            "zone-c",
            role=DeploymentRole.STANDBY,
            latency_ms=110,
        )
    )

    print("\nINITIAL ARCHITECTURE")

    print(json.dumps(manager.report(), indent=2))

    print("\nPROCESSING REQUESTS")

    print(manager.route_request("REQ-001", write=True))
    print(manager.route_request("REQ-002", write=True))

    manager.replicate_to_standby()

    print("\nSIMULATING PRIMARY REGION FAILURE")

    manager.update_health(
        "ap-south-1",
        RegionStatus.UNAVAILABLE,
    )

    candidates = manager.available_targets()

    print("Eligible failover targets:")

    for candidate in candidates:
        print(candidate.region_id)

    if not candidates:
        raise RuntimeError("No eligible failover region.")

    event = manager.perform_failover(
        candidates[0].region_id
    )

    print("\nFAILOVER EVENT")

    print(json.dumps({
        "event_id": event.event_id,
        "source": event.source_region,
        "target": event.target_region,
        "status": event.status.value,
        "rpo_seconds": event.rpo_seconds,
        "estimated_rto_seconds": event.estimated_rto_seconds,
    }, indent=2))

    print("\nPROCESSING AFTER FAILOVER")

    print(manager.route_request("REQ-003", write=True))

    print("\nRECOVERY AND FAILBACK")

    manager.recover_region("ap-south-1")

    current_primary = manager._get_region(
        manager.primary_region
    )

    manager.complete_recovery(
        "ap-south-1",
        current_primary.data_version,
    )

    manager.replicate_to_standby()

    failback_event = manager.failback("ap-south-1")

    print("Failback:", failback_event.status.value)

    print("\nFINAL ARCHITECTURE")

    print(json.dumps(manager.report(), indent=2))

    # Basic executable assertions.
    assert manager.primary_region == "ap-south-1"
    assert failback_event.status == FailoverStatus.SUCCESS
    assert len(manager.events) == 2

    print("\nAll validation checks passed.")


if __name__ == "__main__":
    main()
