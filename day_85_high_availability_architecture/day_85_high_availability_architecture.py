#!/usr/bin/env python3
"""
High Availability Architecture: Eliminating Single Points of Failure

A self-contained simulation of:
- Redundant application and database nodes
- Independent failure domains
- Active-active traffic distribution
- Health monitoring and automatic failover
- Quorum-based control-plane availability
- Recovery and failback
- Capacity-aware routing
- Single-point-of-failure detection
- Availability and recovery metrics

Python 3.10+
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


class ServiceState(Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ArchitectureError(Exception):
    pass


class CapacityError(ArchitectureError):
    pass


@dataclass
class Node:
    node_id: str
    role: str
    failure_domain: str
    capacity: int
    state: NodeState = NodeState.HEALTHY
    current_load: int = 0
    last_health_check: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("Node ID cannot be empty")
        if self.capacity <= 0:
            raise ValueError("Node capacity must be positive")
        if not self.failure_domain.strip():
            raise ValueError("Failure domain cannot be empty")

    @property
    def available_capacity(self) -> int:
        if self.state != NodeState.HEALTHY:
            return 0
        return max(0, self.capacity - self.current_load)

    @property
    def is_healthy(self) -> bool:
        return self.state == NodeState.HEALTHY

    def health_check(self) -> bool:
        self.last_health_check = time.time()
        return self.is_healthy

    def fail(self) -> None:
        self.state = NodeState.FAILED
        self.current_load = 0

    def recover(self) -> None:
        self.state = NodeState.HEALTHY
        self.current_load = 0

    def enter_maintenance(self) -> None:
        self.state = NodeState.MAINTENANCE
        self.current_load = 0


@dataclass
class Service:
    service_id: str
    replica_ids: list[str]
    minimum_healthy_replicas: int
    critical: bool = True

    def __post_init__(self) -> None:
        if not self.replica_ids:
            raise ValueError("A service requires at least one replica")
        if len(set(self.replica_ids)) != len(self.replica_ids):
            raise ValueError("Duplicate replica IDs")
        if not 1 <= self.minimum_healthy_replicas <= len(self.replica_ids):
            raise ValueError("Invalid minimum replica count")


@dataclass
class QuorumCluster:
    member_ids: list[str]
    leader_id: Optional[str] = None
    term: int = 0

    def __post_init__(self) -> None:
        if len(self.member_ids) < 3 or len(self.member_ids) % 2 == 0:
            raise ValueError("Quorum cluster requires an odd number of members")
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("Quorum member IDs must be unique")

    @property
    def required_votes(self) -> int:
        return len(self.member_ids) // 2 + 1

    def elect_leader(self, nodes: dict[str, Node]) -> Optional[str]:
        healthy = [
            member_id
            for member_id in self.member_ids
            if member_id in nodes and nodes[member_id].is_healthy
        ]

        if len(healthy) < self.required_votes:
            self.leader_id = None
            return None

        # A new term invalidates leadership from an earlier election.
        self.term += 1
        self.leader_id = healthy[0]
        return self.leader_id

    def has_quorum(self, nodes: dict[str, Node]) -> bool:
        votes = sum(
            1 for member_id in self.member_ids
            if member_id in nodes and nodes[member_id].is_healthy
        )
        return votes >= self.required_votes


class HighAvailabilityPlatform:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.services: dict[str, Service] = {}
        self.events: list[str] = []
        self.request_count = 0
        self.failed_requests = 0
        self.quorum: Optional[QuorumCluster] = None

    def log(self, message: str) -> None:
        self.events.append(message)
        print(f"[HA] {message}")

    def register_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise ArchitectureError(f"Duplicate node: {node.node_id}")
        self.nodes[node.node_id] = node

    def register_service(self, service: Service) -> None:
        if service.service_id in self.services:
            raise ArchitectureError("Duplicate service")
        missing = set(service.replica_ids) - self.nodes.keys()
        if missing:
            raise ArchitectureError(f"Unknown nodes: {missing}")
        self.services[service.service_id] = service

    def configure_quorum(self, cluster: QuorumCluster) -> None:
        missing = set(cluster.member_ids) - self.nodes.keys()
        if missing:
            raise ArchitectureError(f"Unknown quorum nodes: {missing}")
        self.quorum = cluster

    def healthy_replicas(self, service_id: str) -> list[Node]:
        service = self.services[service_id]
        return [
            self.nodes[node_id]
            for node_id in service.replica_ids
            if self.nodes[node_id].is_healthy
        ]

    def service_state(self, service_id: str) -> ServiceState:
        service = self.services[service_id]
        count = len(self.healthy_replicas(service_id))

        if count == 0 or count < service.minimum_healthy_replicas:
            return ServiceState.UNAVAILABLE

        if count < len(service.replica_ids):
            return ServiceState.DEGRADED

        return ServiceState.AVAILABLE

    def route_request(self, service_id: str) -> Optional[str]:
        self.request_count += 1

        candidates = self.healthy_replicas(service_id)

        # Least-loaded routing with deterministic tie-breaking.
        candidates.sort(
            key=lambda node: (
                node.current_load / node.capacity,
                node.current_load,
                node.node_id,
            )
        )

        for node in candidates:
            if node.available_capacity > 0:
                node.current_load += 1
                self.log(f"Request routed to {node.node_id}")
                return node.node_id

        self.failed_requests += 1
        self.log(f"Request rejected: {service_id} has no available capacity")
        return None

    def release_request(self, node_id: str) -> None:
        node = self.nodes[node_id]
        if node.current_load > 0:
            node.current_load -= 1

    def simulate_node_failure(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise ArchitectureError("Unknown node")

        self.nodes[node_id].fail()
        self.log(f"Node failure detected: {node_id}")

        affected_services = [
            service_id
            for service_id, service in self.services.items()
            if node_id in service.replica_ids
        ]

        for service_id in affected_services:
            state = self.service_state(service_id)
            self.log(f"{service_id} state: {state.value}")

        if self.quorum:
            if not self.quorum.has_quorum(self.nodes):
                self.log("WARNING: Control-plane quorum lost")
            elif self.quorum.leader_id == node_id:
                new_leader = self.quorum.elect_leader(self.nodes)
                self.log(f"Leader failover: {new_leader}")

    def recover_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise ArchitectureError("Unknown node")

        self.nodes[node_id].recover()
        self.log(f"Node recovered: {node_id}")

        if self.quorum and self.quorum.leader_id is None:
            leader = self.quorum.elect_leader(self.nodes)
            self.log(f"Recovered quorum leader: {leader}")

    def detect_single_points_of_failure(self) -> list[str]:
        """
        Identify services whose replicas cannot tolerate the
        simultaneous loss of an individual failure domain.
        """
        risks = []

        for service_id, service in self.services.items():
            domains = {
                self.nodes[node_id].failure_domain
                for node_id in service.replica_ids
            }

            for domain in domains:
                surviving = sum(
                    1
                    for node_id in service.replica_ids
                    if self.nodes[node_id].failure_domain != domain
                    and self.nodes[node_id].is_healthy
                )

                if surviving < service.minimum_healthy_replicas:
                    risks.append(
                        f"{service_id}: failure of domain {domain} "
                        "violates minimum replica requirement"
                    )

        if self.quorum:
            domains = {
                self.nodes[node_id].failure_domain
                for node_id in self.quorum.member_ids
            }

            for domain in domains:
                surviving_votes = sum(
                    1
                    for node_id in self.quorum.member_ids
                    if self.nodes[node_id].failure_domain != domain
                    and self.nodes[node_id].is_healthy
                )

                if surviving_votes < self.quorum.required_votes:
                    risks.append(
                        f"Control plane: loss of {domain} "
                        "destroys quorum"
                    )

        return risks

    def simulate_domain_failure(self, domain: str) -> None:
        affected = [
            node for node in self.nodes.values()
            if node.failure_domain == domain and node.is_healthy
        ]

        if not affected:
            raise ArchitectureError("Failure domain has no healthy nodes")

        self.log(f"Simulating complete domain failure: {domain}")

        for node in affected:
            self.simulate_node_failure(node.node_id)

    def report(self) -> None:
        print("\n========== AVAILABILITY REPORT ==========")

        for service_id in self.services:
            healthy = self.healthy_replicas(service_id)
            state = self.service_state(service_id)

            print(
                f"{service_id}: {state.value} | "
                f"healthy replicas: {len(healthy)}"
            )

        if self.quorum:
            print(
                f"Control-plane quorum: "
                f"{self.quorum.has_quorum(self.nodes)}"
            )
            print(f"Leader: {self.quorum.leader_id}")

        successful = self.request_count - self.failed_requests
        availability = (
            successful / self.request_count * 100
            if self.request_count else 100.0
        )

        print(f"Requests: {self.request_count}")
        print(f"Failed requests: {self.failed_requests}")
        print(f"Simulation success ratio: {availability:.2f}%")

        risks = self.detect_single_points_of_failure()

        print("\nFailure-domain risks:")
        if risks:
            for risk in risks:
                print(f"  - {risk}")
        else:
            print("  No modeled single-domain failure violates policy.")


def build_platform() -> HighAvailabilityPlatform:
    platform = HighAvailabilityPlatform()

    # Three independent availability zones.
    definitions = [
        ("app-1", "application", "zone-a", 100),
        ("app-2", "application", "zone-b", 100),
        ("app-3", "application", "zone-c", 100),
        ("db-1", "database", "zone-a", 200),
        ("db-2", "database", "zone-b", 200),
        ("db-3", "database", "zone-c", 200),
        ("control-1", "control", "zone-a", 50),
        ("control-2", "control", "zone-b", 50),
        ("control-3", "control", "zone-c", 50),
    ]

    for node_id, role, domain, capacity in definitions:
        platform.register_node(
            Node(node_id, role, domain, capacity)
        )

    platform.register_service(
        Service("application", ["app-1", "app-2", "app-3"], 2)
    )

    platform.register_service(
        Service("database", ["db-1", "db-2", "db-3"], 2)
    )

    platform.configure_quorum(
        QuorumCluster(["control-1", "control-2", "control-3"])
    )

    platform.quorum.elect_leader(platform.nodes)

    return platform


def main() -> None:
    random.seed(42)

    platform = build_platform()

    print("\n1. Initial architecture")
    platform.report()

    print("\n2. Normal request distribution")
    for _ in range(6):
        node_id = platform.route_request("application")
        if node_id:
            platform.release_request(node_id)

    print("\n3. Individual node failure")
    platform.simulate_node_failure("app-1")

    for _ in range(4):
        node_id = platform.route_request("application")
        if node_id:
            platform.release_request(node_id)

    print("\n4. Recovery")
    platform.recover_node("app-1")

    print("\n5. Complete availability-zone failure")
    platform.simulate_domain_failure("zone-a")

    print("\n6. Final report")
    platform.report()

    # Assertions verify the fundamental HA guarantees.
    assert platform.service_state("application") == ServiceState.DEGRADED
    assert platform.quorum is not None
    assert platform.quorum.has_quorum(platform.nodes)

    print("\nAll architecture validation assertions passed.")


if __name__ == "__main__":
    main()
