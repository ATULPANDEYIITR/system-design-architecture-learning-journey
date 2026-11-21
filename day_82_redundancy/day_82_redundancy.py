from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import json
import logging
import uuid


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s"
)
logger = logging.getLogger("redundancy")


class Architecture(Enum):
    ACTIVE_ACTIVE = "active-active"
    ACTIVE_PASSIVE = "active-passive"


class NodeRole(Enum):
    ACTIVE = "active"
    PASSIVE = "passive"
    FAILED = "failed"
    RECOVERING = "recovering"


class NodeStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class ReplicationMode(Enum):
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


class FailoverState(Enum):
    NORMAL = "normal"
    DETECTED = "detected"
    PROMOTING = "promoting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Node:
    node_id: str
    region: str
    capacity: int
    role: NodeRole
    status: NodeStatus = NodeStatus.HEALTHY
    current_load: int = 0
    last_applied_sequence: int = 0
    replication_lag: int = 0

    def available_capacity(self) -> int:
        if self.status == NodeStatus.DOWN:
            return 0
        return max(0, self.capacity - self.current_load)

    def is_available(self) -> bool:
        return (
            self.status != NodeStatus.DOWN
            and self.available_capacity() > 0
        )


@dataclass
class ReplicatedWrite:
    sequence: int
    key: str
    value: str
    timestamp: datetime
    acknowledged: bool = False


@dataclass
class Request:
    request_id: str
    operation: str
    key: str
    value: Optional[str] = None


@dataclass
class FailoverEvent:
    event_id: str
    previous_node: str
    promoted_node: str
    timestamp: datetime
    successful: bool
    reason: str


@dataclass
class RedundancyConfiguration:
    architecture: Architecture
    replication_mode: ReplicationMode
    required_active_nodes: int = 1
    max_replication_lag: int = 0
    automatic_failover: bool = True
    allow_write_during_degraded_state: bool = False


class RedundancyError(Exception):
    pass


class CapacityError(RedundancyError):
    pass


class ConsistencyError(RedundancyError):
    pass


class QuorumError(RedundancyError):
    pass


class Repository:
    """
    Simulates a distributed service with replicated nodes.

    Active-active:
        Multiple nodes accept requests.

    Active-passive:
        One node accepts requests while another waits
        for promotion during a failure.
    """

    def __init__(
        self,
        name: str,
        configuration: RedundancyConfiguration,
        nodes: list[Node]
    ):
        if not name.strip():
            raise ValueError("Repository name cannot be empty")

        if len(nodes) < 2:
            raise ValueError("At least two nodes are required")

        identifiers = [node.node_id for node in nodes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Node identifiers must be unique")

        if configuration.required_active_nodes < 1:
            raise ValueError("At least one active node is required")

        self.name = name
        self.config = configuration
        self.nodes = {node.node_id: node for node in nodes}
        self.data: dict[str, str] = {}
        self.write_log: list[ReplicatedWrite] = []
        self.failover_events: list[FailoverEvent] = []
        self.sequence = 0
        self.failover_state = FailoverState.NORMAL

        self._initialize_roles()

    def _initialize_roles(self) -> None:
        healthy = [
            node for node in self.nodes.values()
            if node.status == NodeStatus.HEALTHY
        ]

        if self.config.architecture == Architecture.ACTIVE_ACTIVE:
            if len(healthy) < self.config.required_active_nodes:
                raise ValueError("Insufficient healthy active nodes")

            for node in self.nodes.values():
                node.role = (
                    NodeRole.ACTIVE
                    if node.status != NodeStatus.DOWN
                    else NodeRole.FAILED
                )

        else:
            if not healthy:
                raise ValueError("No healthy node available")

            primary = healthy[0]
            primary.role = NodeRole.ACTIVE

            for node in healthy[1:]:
                node.role = NodeRole.PASSIVE

            for node in self.nodes.values():
                if node.status == NodeStatus.DOWN:
                    node.role = NodeRole.FAILED

    def active_nodes(self) -> list[Node]:
        return [
            node for node in self.nodes.values()
            if node.role == NodeRole.ACTIVE and node.is_available()
        ]

    def passive_nodes(self) -> list[Node]:
        return [
            node for node in self.nodes.values()
            if node.role == NodeRole.PASSIVE
            and node.status != NodeStatus.DOWN
        ]

    def select_node(self) -> Node:
        active = self.active_nodes()

        if not active:
            raise RedundancyError("No active node is available")

        # Select the least-loaded healthy node.
        selected = min(
            active,
            key=lambda node: (
                node.current_load / node.capacity,
                node.replication_lag,
                node.node_id
            )
        )

        return selected

    def process_request(self, request: Request) -> dict:
        if request.operation not in {"READ", "WRITE"}:
            raise ValueError("Unsupported operation")

        node = self.select_node()

        if node.current_load >= node.capacity:
            raise CapacityError(f"Node {node.node_id} is overloaded")

        node.current_load += 1

        try:
            if request.operation == "READ":
                return {
                    "request_id": request.request_id,
                    "node": node.node_id,
                    "value": self.data.get(request.key),
                    "operation": "READ"
                }

            if request.value is None:
                raise ValueError("WRITE requires a value")

            return self._write(request, node)

        finally:
            node.current_load -= 1

    def _write(self, request: Request, source: Node) -> dict:
        self.sequence += 1

        record = ReplicatedWrite(
            sequence=self.sequence,
            key=request.key,
            value=request.value,
            timestamp=datetime.now(timezone.utc)
        )

        replicas = [
            node for node in self.nodes.values()
            if node.node_id != source.node_id
            and node.status != NodeStatus.DOWN
        ]

        if self.config.architecture == Architecture.ACTIVE_PASSIVE:
            replicas = [
                node for node in replicas
                if node.role == NodeRole.PASSIVE
            ]

        if self.config.replication_mode == ReplicationMode.SYNCHRONOUS:
            if not replicas:
                raise ConsistencyError(
                    "Synchronous replication has no available replica"
                )

            for replica in replicas:
                if replica.status != NodeStatus.HEALTHY:
                    raise ConsistencyError(
                        f"Replica {replica.node_id} is not healthy"
                    )

                replica.last_applied_sequence = record.sequence
                replica.replication_lag = 0

            record.acknowledged = True

        else:
            record.acknowledged = True

            for replica in replicas:
                replica.replication_lag += 1

        self.data[request.key] = request.value
        source.last_applied_sequence = record.sequence
        self.write_log.append(record)

        return {
            "request_id": request.request_id,
            "node": source.node_id,
            "sequence": record.sequence,
            "acknowledged": record.acknowledged,
            "replicated_nodes": [node.node_id for node in replicas],
            "operation": "WRITE"
        }

    def synchronize_replica(self, node_id: str) -> int:
        node = self.nodes.get(node_id)

        if node is None:
            raise ValueError("Unknown node")

        if node.status == NodeStatus.DOWN:
            raise RedundancyError("Cannot synchronize a failed node")

        pending = [
            record for record in self.write_log
            if record.sequence > node.last_applied_sequence
        ]

        for record in pending:
            self.data[record.key] = record.value
            node.last_applied_sequence = record.sequence

        node.replication_lag = max(
            0,
            self.sequence - node.last_applied_sequence
        )

        logger.info(
            "Node %s synchronized through sequence %d",
            node_id,
            node.last_applied_sequence
        )

        return len(pending)

    def fail_node(self, node_id: str) -> None:
        node = self.nodes.get(node_id)

        if node is None:
            raise ValueError("Unknown node")

        node.status = NodeStatus.DOWN
        node.role = NodeRole.FAILED

        logger.warning("Node %s failed", node_id)

        if self.config.architecture == Architecture.ACTIVE_ACTIVE:
            self._evaluate_active_active()
        elif node_id:
            self._failover_active_passive(node)

    def _evaluate_active_active(self) -> None:
        available = self.active_nodes()

        if len(available) < self.config.required_active_nodes:
            self.failover_state = FailoverState.FAILED
            logger.error("Active-active availability requirement violated")
        else:
            self.failover_state = FailoverState.NORMAL

    def _failover_active_passive(self, failed_node: Node) -> None:
        self.failover_state = FailoverState.DETECTED

        if not self.config.automatic_failover:
            self.failover_state = FailoverState.FAILED
            return

        candidates = [
            node for node in self.passive_nodes()
            if node.status == NodeStatus.HEALTHY
        ]

        if not candidates:
            self.failover_state = FailoverState.FAILED
            logger.error("No eligible passive node for promotion")
            return

        candidate = max(
            candidates,
            key=lambda node: (
                node.last_applied_sequence,
                node.capacity,
                node.node_id
            )
        )

        if (
            self.config.replication_mode == ReplicationMode.SYNCHRONOUS
            and candidate.last_applied_sequence < self.sequence
        ):
            self.failover_state = FailoverState.FAILED
            logger.error("Promotion rejected because replica is stale")
            return

        if (
            candidate.replication_lag
            > self.config.max_replication_lag
        ):
            self.failover_state = FailoverState.FAILED
            logger.error("Replication lag exceeds promotion policy")
            return

        self.failover_state = FailoverState.PROMOTING

        candidate.role = NodeRole.ACTIVE
        candidate.replication_lag = 0

        self.failover_state = FailoverState.COMPLETED

        self.failover_events.append(
            FailoverEvent(
                event_id=str(uuid.uuid4()),
                previous_node=failed_node.node_id,
                promoted_node=candidate.node_id,
                timestamp=datetime.now(timezone.utc),
                successful=True,
                reason="Automatic failover"
            )
        )

        logger.info(
            "Node %s promoted after failure of %s",
            candidate.node_id,
            failed_node.node_id
        )

    def recover_node(self, node_id: str) -> None:
        node = self.nodes.get(node_id)

        if node is None:
            raise ValueError("Unknown node")

        if node.status != NodeStatus.DOWN:
            raise RedundancyError("Node is not in a failed state")

        node.status = NodeStatus.HEALTHY
        node.role = NodeRole.RECOVERING
        node.current_load = 0

        self.synchronize_replica(node_id)

        if self.config.architecture == Architecture.ACTIVE_ACTIVE:
            node.role = NodeRole.ACTIVE
        else:
            # The recovered former primary rejoins as passive.
            node.role = NodeRole.PASSIVE

        logger.info("Node %s recovered", node_id)

    def status_report(self) -> dict:
        return {
            "repository": self.name,
            "architecture": self.config.architecture.value,
            "failover_state": self.failover_state.value,
            "sequence": self.sequence,
            "nodes": [
                {
                    "id": node.node_id,
                    "region": node.region,
                    "role": node.role.value,
                    "status": node.status.value,
                    "capacity": node.capacity,
                    "load": node.current_load,
                    "last_sequence": node.last_applied_sequence,
                    "replication_lag": node.replication_lag
                }
                for node in self.nodes.values()
            ]
        }


def create_request(
    operation: str,
    key: str,
    value: Optional[str] = None
) -> Request:
    return Request(
        request_id=str(uuid.uuid4()),
        operation=operation.upper(),
        key=key,
        value=value
    )


def demonstrate_active_active() -> None:
    print("\n=== ACTIVE-ACTIVE ARCHITECTURE ===")

    nodes = [
        Node("AA-1", "Mumbai", 100, NodeRole.ACTIVE),
        Node("AA-2", "Pune", 100, NodeRole.ACTIVE),
        Node("AA-3", "Delhi", 100, NodeRole.ACTIVE)
    ]

    service = Repository(
        "payment-service",
        RedundancyConfiguration(
            architecture=Architecture.ACTIVE_ACTIVE,
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            required_active_nodes=2
        ),
        nodes
    )

    for index in range(5):
        result = service.process_request(
            create_request("WRITE", f"payment:{index}", str(index * 100))
        )
        print(result)

    print("Before failure:")
    print(json.dumps(service.status_report(), indent=2))

    service.fail_node("AA-1")

    print("After failure:")
    print(json.dumps(service.status_report(), indent=2))

    print("Read after failure:")
    print(
        service.process_request(
            create_request("READ", "payment:1")
        )
    )

    service.recover_node("AA-1")

    print("After recovery:")
    print(json.dumps(service.status_report(), indent=2))


def demonstrate_active_passive() -> None:
    print("\n=== ACTIVE-PASSIVE ARCHITECTURE ===")

    nodes = [
        Node("AP-PRIMARY", "Mumbai", 200, NodeRole.ACTIVE),
        Node("AP-STANDBY-1", "Pune", 200, NodeRole.PASSIVE),
        Node("AP-STANDBY-2", "Delhi", 150, NodeRole.PASSIVE)
    ]

    service = Repository(
        "inventory-service",
        RedundancyConfiguration(
            architecture=Architecture.ACTIVE_PASSIVE,
            replication_mode=ReplicationMode.SYNCHRONOUS,
            max_replication_lag=0,
            automatic_failover=True
        ),
        nodes
    )

    service.process_request(
        create_request("WRITE", "inventory:product-1", "500")
    )

    service.process_request(
        create_request("WRITE", "inventory:product-2", "250")
    )

    print("Before failure:")
    print(json.dumps(service.status_report(), indent=2))

    service.fail_node("AP-PRIMARY")

    print("After failover:")
    print(json.dumps(service.status_report(), indent=2))

    print("Write through promoted node:")
    print(
        service.process_request(
            create_request("WRITE", "inventory:product-3", "750")
        )
    )

    service.recover_node("AP-PRIMARY")

    print("After primary recovery:")
    print(json.dumps(service.status_report(), indent=2))


def demonstrate_failure_conditions() -> None:
    print("\n=== FAILURE CONDITIONS ===")

    service = Repository(
        "critical-service",
        RedundancyConfiguration(
            architecture=Architecture.ACTIVE_PASSIVE,
            replication_mode=ReplicationMode.SYNCHRONOUS,
            automatic_failover=True
        ),
        [
            Node("P1", "Region-A", 50, NodeRole.ACTIVE),
            Node("P2", "Region-B", 50, NodeRole.PASSIVE)
        ]
    )

    service.fail_node("P1")

    try:
        service.fail_node("P2")
        service.process_request(
            create_request("READ", "unknown")
        )
    except RedundancyError as error:
        logger.error("Expected availability failure: %s", error)

    try:
        service.process_request(
            create_request("DELETE", "unknown")
        )
    except ValueError as error:
        logger.error("Expected validation failure: %s", error)


def main() -> None:
    demonstrate_active_active()
    demonstrate_active_passive()
    demonstrate_failure_conditions()


if __name__ == "__main__":
    main()
