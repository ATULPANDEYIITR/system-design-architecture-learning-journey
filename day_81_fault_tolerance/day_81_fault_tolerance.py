#!/usr/bin/env python3
"""
Fault Tolerance: Failure Detection and Recovery

Models a distributed service cluster with:
- Heartbeat-based failure detection
- SUSPECT and FAILED states
- Timeout and consecutive-miss detection
- Automatic recovery and retry limits
- Exponential backoff
- Replica health monitoring
- Recovery event logging
- JSON persistence
- Unit-style assertions
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("fault-tolerance")


class NodeState(str, Enum):
    HEALTHY = "HEALTHY"
    SUSPECT = "SUSPECT"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    DISABLED = "DISABLED"


class RecoveryStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    EXHAUSTED = "EXHAUSTED"


class FaultToleranceError(Exception):
    pass


@dataclass
class RecoveryPolicy:
    heartbeat_timeout: float = 10.0
    failure_threshold: int = 3
    recovery_threshold: int = 2
    max_retries: int = 3
    initial_backoff: float = 2.0
    max_backoff: float = 30.0

    def __post_init__(self):
        if self.heartbeat_timeout <= 0:
            raise ValueError("Heartbeat timeout must be positive")
        if self.failure_threshold < 1:
            raise ValueError("Failure threshold must be at least one")
        if self.recovery_threshold < 1:
            raise ValueError("Recovery threshold must be at least one")
        if self.max_retries < 0:
            raise ValueError("Maximum retries cannot be negative")
        if self.initial_backoff <= 0 or self.max_backoff < self.initial_backoff:
            raise ValueError("Invalid backoff configuration")

    def backoff(self, attempt: int) -> float:
        return min(
            self.initial_backoff * (2 ** max(0, attempt - 1)),
            self.max_backoff,
        )


@dataclass
class Node:
    node_id: str
    hostname: str
    state: NodeState = NodeState.HEALTHY
    last_heartbeat: float = field(default_factory=time.monotonic)
    missed_heartbeats: int = 0
    successful_heartbeats: int = 0
    recovery_attempts: int = 0
    next_recovery_at: float = 0.0
    failure_reason: Optional[str] = None

    def __post_init__(self):
        if not self.node_id.strip():
            raise ValueError("Node ID cannot be empty")
        if not self.hostname.strip():
            raise ValueError("Hostname cannot be empty")


@dataclass
class Event:
    timestamp: float
    node_id: str
    event_type: str
    details: str


class ClusterMonitor:
    def __init__(self, policy: RecoveryPolicy):
        self.policy = policy
        self.nodes: dict[str, Node] = {}
        self.events: list[Event] = []

    def register_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise FaultToleranceError("Duplicate node registration")

        self.nodes[node.node_id] = node
        self._log(node.node_id, "REGISTERED", node.hostname)

    def _log(self, node_id: str, event_type: str, details: str):
        self.events.append(
            Event(time.time(), node_id, event_type, details)
        )

    def receive_heartbeat(
        self,
        node_id: str,
        timestamp: Optional[float] = None,
    ) -> None:
        node = self.nodes.get(node_id)

        if node is None:
            raise FaultToleranceError(f"Unknown node: {node_id}")

        if node.state == NodeState.DISABLED:
            raise FaultToleranceError("Disabled node cannot send heartbeats")

        now = time.monotonic() if timestamp is None else timestamp

        if now > time.monotonic() + 60:
            raise ValueError("Heartbeat timestamp is in the future")

        if now < node.last_heartbeat:
            raise ValueError("Out-of-order heartbeat rejected")

        node.last_heartbeat = now
        node.missed_heartbeats = 0
        node.successful_heartbeats += 1

        if node.state in (NodeState.SUSPECT, NodeState.HEALTHY):
            previous_state = node.state
            node.state = NodeState.HEALTHY

            if previous_state == NodeState.SUSPECT:
                self._log(node_id, "RECOVERED", "Heartbeat restored before failure")

        elif node.state in (NodeState.FAILED, NodeState.RECOVERING):
            node.state = NodeState.HEALTHY
            node.recovery_attempts = 0
            node.failure_reason = None
            self._log(node_id, "RECOVERED", "Node became healthy")

        self._log(node_id, "HEARTBEAT", "Heartbeat received")

    def detect_failures(self, now: Optional[float] = None) -> None:
        current_time = time.monotonic() if now is None else now

        for node in self.nodes.values():
            if node.state in (NodeState.DISABLED, NodeState.FAILED):
                continue

            if node.state == NodeState.RECOVERING:
                continue

            elapsed = current_time - node.last_heartbeat

            if elapsed < 0:
                continue

            if elapsed >= self.policy.heartbeat_timeout:
                node.missed_heartbeats += 1

                if node.state == NodeState.HEALTHY:
                    node.state = NodeState.SUSPECT
                    self._log(node.node_id, "SUSPECT", "Heartbeat timeout detected")

                if node.missed_heartbeats >= self.policy.failure_threshold:
                    node.state = NodeState.FAILED
                    node.failure_reason = "Heartbeat threshold exceeded"
                    node.next_recovery_at = current_time
                    self._log(
                        node.node_id,
                        "FAILED",
                        node.failure_reason,
                    )

    def recover_node(
        self,
        node_id: str,
        now: Optional[float] = None,
        simulated_success: bool = True,
    ) -> RecoveryStatus:
        node = self.nodes.get(node_id)

        if node is None:
            raise FaultToleranceError("Unknown node")

        current_time = time.monotonic() if now is None else now

        if node.state not in (NodeState.FAILED, NodeState.RECOVERING):
            raise FaultToleranceError("Node is not eligible for recovery")

        if current_time < node.next_recovery_at:
            raise FaultToleranceError("Recovery backoff is still active")

        if node.recovery_attempts >= self.policy.max_retries:
            self._log(node_id, "RECOVERY_EXHAUSTED", "Retry limit reached")
            return RecoveryStatus.EXHAUSTED

        node.recovery_attempts += 1
        node.state = NodeState.RECOVERING

        self._log(
            node_id,
            "RECOVERY_STARTED",
            f"Attempt {node.recovery_attempts}",
        )

        if simulated_success:
            node.state = NodeState.HEALTHY
            node.missed_heartbeats = 0
            node.successful_heartbeats = 0
            node.last_heartbeat = current_time
            node.failure_reason = None
            node.recovery_attempts = 0

            self._log(node_id, "RECOVERY_SUCCESS", "Service restarted")
            return RecoveryStatus.SUCCESS

        node.state = NodeState.FAILED
        delay = self.policy.backoff(node.recovery_attempts)
        node.next_recovery_at = current_time + delay

        self._log(
            node_id,
            "RECOVERY_FAILURE",
            f"Next attempt after {delay:.1f} seconds",
        )

        return RecoveryStatus.FAILURE

    def disable_node(self, node_id: str):
        node = self.nodes.get(node_id)

        if node is None:
            raise FaultToleranceError("Unknown node")

        node.state = NodeState.DISABLED
        self._log(node_id, "DISABLED", "Node administratively disabled")

    def cluster_health(self) -> dict:
        counts = {state.value: 0 for state in NodeState}

        for node in self.nodes.values():
            counts[node.state.value] += 1

        total = len(self.nodes)
        healthy = counts[NodeState.HEALTHY.value]

        return {
            "total_nodes": total,
            "healthy_nodes": healthy,
            "failed_nodes": counts[NodeState.FAILED.value],
            "suspected_nodes": counts[NodeState.SUSPECT.value],
            "recovering_nodes": counts[NodeState.RECOVERING.value],
            "disabled_nodes": counts[NodeState.DISABLED.value],
            "availability_percent": round(
                healthy / total * 100, 2
            ) if total else 0.0,
            "states": counts,
        }

    def export_events(self, filename: str = "fault_tolerance_events.json"):
        path = Path(filename)

        data = [
            {
                **asdict(event),
                "timestamp": event.timestamp,
            }
            for event in self.events
        ]

        temporary = path.with_suffix(path.suffix + ".tmp")

        try:
            temporary.write_text(
                json.dumps(data, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def display_status(self):
        print("\nCLUSTER HEALTH")
        print("-" * 65)

        for node in self.nodes.values():
            print(
                f"{node.node_id:10} "
                f"{node.hostname:20} "
                f"{node.state.value:12} "
                f"Missed={node.missed_heartbeats} "
                f"Retries={node.recovery_attempts}"
            )

        print("\n", json.dumps(self.cluster_health(), indent=2))


def run_demo():
    policy = RecoveryPolicy(
        heartbeat_timeout=5,
        failure_threshold=3,
        max_retries=3,
        initial_backoff=2,
        max_backoff=8,
    )

    cluster = ClusterMonitor(policy)

    cluster.register_node(Node("NODE-01", "server-01"))
    cluster.register_node(Node("NODE-02", "server-02"))
    cluster.register_node(Node("NODE-03", "server-03"))

    base = time.monotonic()

    # Simulate successful heartbeats.
    cluster.receive_heartbeat("NODE-01", base + 1)
    cluster.receive_heartbeat("NODE-02", base + 1)

    # Simulate repeated timeout observations.
    cluster.detect_failures(base + 7)
    cluster.detect_failures(base + 13)
    cluster.detect_failures(base + 19)

    assert cluster.nodes["NODE-03"].state == NodeState.FAILED

    print("\nAfter failure detection:")
    cluster.display_status()

    # Simulate an unsuccessful recovery.
    result = cluster.recover_node(
        "NODE-03",
        now=base + 19,
        simulated_success=False,
    )

    assert result == RecoveryStatus.FAILURE

    # Retry after the configured backoff.
    result = cluster.recover_node(
        "NODE-03",
        now=base + 22,
        simulated_success=True,
    )

    assert result == RecoveryStatus.SUCCESS
    assert cluster.nodes["NODE-03"].state == NodeState.HEALTHY

    print("\nAfter recovery:")
    cluster.display_status()

    cluster.export_events()
    print("\nEvent log exported successfully.")

    # Verify failure detection and recovery invariants.
    assert cluster.cluster_health()["healthy_nodes"] == 3

    print("All fault-tolerance assertions passed.")


if __name__ == "__main__":
    try:
        run_demo()
    except (FaultToleranceError, ValueError, OSError) as error:
        logger.exception("Fault-tolerance simulation failed: %s", error)
        raise SystemExit(1)
