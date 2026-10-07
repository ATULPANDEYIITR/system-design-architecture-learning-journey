#!/usr/bin/env python3
"""
Database Replication: primary-replica, synchronous, and asynchronous replication.

This self-contained program builds an executable in-memory replication laboratory.
It demonstrates:

- Primary and replica roles
- Write-ahead-log-like change records
- Asynchronous replication
- Synchronous replication
- Replica replay position
- Commit acknowledgement rules
- Replication lag
- Replica failure and recovery
- WAL/change ordering
- Conflict prevention by separating write authority from read replicas
- Quorum-style synchronous acknowledgement
- Idempotent replay
- Data consistency checks
- Failover promotion and epoch changes
- Monitoring and operational diagnostics

The simulation intentionally models replication semantics rather than pretending
that a Python process is a database server. Real PostgreSQL, MySQL, or another
database engine supplies the actual WAL/binlog/storage machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from copy import deepcopy
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple


class ReplicationMode(Enum):
    ASYNCHRONOUS = "asynchronous"
    SYNCHRONOUS = "synchronous"


class NodeRole(Enum):
    PRIMARY = "primary"
    REPLICA = "replica"


class NodeState(Enum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class Change:
    lsn: int
    transaction_id: int
    operation: str
    key: str
    value: Optional[str]
    epoch: int

    def describe(self) -> str:
        return (
            f"LSN={self.lsn} TX={self.transaction_id} "
            f"{self.operation} {self.key}={self.value!r} epoch={self.epoch}"
        )


@dataclass
class Replica:
    name: str
    state: NodeState = NodeState.UP
    data: Dict[str, str] = field(default_factory=dict)
    received_lsn: int = 0
    replayed_lsn: int = 0
    pending: Deque[Change] = field(default_factory=deque)
    replayed_lsns: Set[int] = field(default_factory=set)

    def receive(self, changes: Iterable[Change]) -> None:
        if self.state is NodeState.DOWN:
            return

        for change in changes:
            if change.lsn > self.received_lsn:
                self.pending.append(change)
                self.received_lsn = change.lsn

    def replay(self, maximum: Optional[int] = None) -> int:
        """
        Replay pending changes in LSN order.

        The LSN is the ordering mechanism. Replaying a previously applied LSN
        is ignored, which models idempotent application behavior expected from
        robust replication consumers.
        """
        if self.state is NodeState.DOWN:
            return 0

        applied = 0

        while self.pending and (maximum is None or applied < maximum):
            change = self.pending.popleft()

            if change.lsn in self.replayed_lsns:
                continue

            if change.operation == "SET":
                assert change.value is not None
                self.data[change.key] = change.value
            elif change.operation == "DELETE":
                self.data.pop(change.key, None)
            else:
                raise ValueError(f"Unsupported operation: {change.operation}")

            self.replayed_lsns.add(change.lsn)
            self.replayed_lsn = max(self.replayed_lsn, change.lsn)
            applied += 1

        return applied

    @property
    def lag(self) -> int:
        return max(0, self.received_lsn - self.replayed_lsn)


class Primary:
    def __init__(self, name: str, epoch: int = 1) -> None:
        self.name = name
        self.role = NodeRole.PRIMARY
        self.state = NodeState.UP
        self.epoch = epoch
        self.data: Dict[str, str] = {}
        self.wal: List[Change] = []
        self.next_lsn = 1
        self.next_transaction_id = 1

    def execute(self, operation: str, key: str, value: Optional[str] = None) -> Change:
        if self.state is NodeState.DOWN:
            raise RuntimeError("Primary is unavailable")

        if operation == "SET":
            if value is None:
                raise ValueError("SET requires a value")
            self.data[key] = value
        elif operation == "DELETE":
            self.data.pop(key, None)
        else:
            raise ValueError(f"Unsupported operation: {operation}")

        change = Change(
            lsn=self.next_lsn,
            transaction_id=self.next_transaction_id,
            operation=operation,
            key=key,
            value=value,
            epoch=self.epoch,
        )

        self.next_lsn += 1
        self.next_transaction_id += 1
        self.wal.append(change)
        return change


class ReplicationCluster:
    def __init__(
        self,
        primary_name: str,
        mode: ReplicationMode,
        synchronous_replicas: int = 0,
    ) -> None:
        if synchronous_replicas < 0:
            raise ValueError("synchronous_replicas cannot be negative")

        self.primary = Primary(primary_name)
        self.replicas: Dict[str, Replica] = {}
        self.mode = mode
        self.synchronous_replicas = synchronous_replicas

    def add_replica(self, replica: Replica) -> None:
        if replica.name == self.primary.name:
            raise ValueError("Replica name conflicts with primary")
        if replica.name in self.replicas:
            raise ValueError(f"Replica already exists: {replica.name}")

        self.replicas[replica.name] = replica

    def _current_replicas(self) -> List[Replica]:
        return [
            replica
            for replica in self.replicas.values()
            if replica.state is NodeState.UP
        ]

    def _synchronous_ack_count(self, change: Change) -> int:
        """
        In this simulation an acknowledgement means the replica has replayed
        the change, not merely received it. This represents a stronger
        synchronous durability condition.
        """
        return sum(
            replica.replayed_lsn >= change.lsn
            for replica in self._current_replicas()
        )

    def commit(
        self,
        operation: str,
        key: str,
        value: Optional[str] = None,
        auto_replay: bool = True,
    ) -> Change:
        """
        Execute a primary write and deliver its WAL record to replicas.

        Asynchronous mode returns after primary WAL persistence in this model.
        Synchronous mode requires the configured number of replicas to replay
        the change before the commit is acknowledged.
        """
        change = self.primary.execute(operation, key, value)

        for replica in self._current_replicas():
            replica.receive([change])

        if auto_replay:
            for replica in self._current_replicas():
                replica.replay()

        if self.mode is ReplicationMode.SYNCHRONOUS:
            if self.synchronous_replicas == 0:
                return change

            acknowledged = self._synchronous_ack_count(change)
            if acknowledged < self.synchronous_replicas:
                raise RuntimeError(
                    f"Synchronous commit {change.lsn} cannot be acknowledged: "
                    f"required={self.synchronous_replicas}, acknowledged={acknowledged}"
                )

        return change

    def replicate_pending(self, replica_name: Optional[str] = None) -> None:
        targets = (
            [self.replicas[replica_name]]
            if replica_name
            else list(self.replicas.values())
        )

        for replica in targets:
            replica.replay()

    def compare_data(self, replica_name: str) -> Tuple[bool, Dict[str, object]]:
        replica = self.replicas[replica_name]
        primary_snapshot = deepcopy(self.primary.data)
        replica_snapshot = deepcopy(replica.data)

        differences: Dict[str, object] = {}

        for key in sorted(set(primary_snapshot) | set(replica_snapshot)):
            if primary_snapshot.get(key) != replica_snapshot.get(key):
                differences[key] = {
                    "primary": primary_snapshot.get(key),
                    "replica": replica_snapshot.get(key),
                }

        return not differences, differences

    def status(self) -> List[Dict[str, object]]:
        result = []

        for replica in self.replicas.values():
            result.append(
                {
                    "replica": replica.name,
                    "state": replica.state.value,
                    "received_lsn": replica.received_lsn,
                    "replayed_lsn": replica.replayed_lsn,
                    "lag": replica.lag,
                }
            )

        return result

    def promote_replica(self, replica_name: str) -> Primary:
        """
        Promote a replica only after stopping the current primary.

        A new epoch prevents stale writes from an old primary generation from
        being treated as valid after failover.
        """
        replica = self.replicas[replica_name]

        if replica.state is NodeState.DOWN:
            raise RuntimeError("Cannot promote a down replica")

        if self.primary.state is NodeState.UP:
            raise RuntimeError(
                "Refusing promotion while the current primary is still writable"
            )

        if replica.replayed_lsn == 0:
            raise RuntimeError("Replica has no replayed state to promote")

        new_primary = Primary(replica.name, epoch=self.primary.epoch + 1)
        new_primary.data = deepcopy(replica.data)
        new_primary.next_lsn = replica.replayed_lsn + 1
        new_primary.next_transaction_id = max(
            (change.transaction_id for change in self.primary.wal),
            default=0,
        ) + 1

        new_primary.wal = [
            change
            for change in self.primary.wal
            if change.lsn <= replica.replayed_lsn
        ]

        self.primary = new_primary

        promoted = self.replicas.pop(replica_name)
        promoted.role = NodeRole.PRIMARY

        return new_primary


def print_heading(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def demonstrate_asynchronous_replication() -> None:
    print_heading("Asynchronous replication")

    cluster = ReplicationCluster(
        primary_name="db-primary",
        mode=ReplicationMode.ASYNCHRONOUS,
    )
    cluster.add_replica(Replica("db-replica-a"))
    cluster.add_replica(Replica("db-replica-b"))

    change_a = cluster.commit("SET", "customer:1001", "ACTIVE", auto_replay=False)
    change_b = cluster.commit("SET", "customer:1002", "SUSPENDED", auto_replay=False)

    print("Primary WAL:")
    for change in cluster.primary.wal:
        print(" ", change.describe())

    print("\nBefore replay:")
    print(cluster.status())

    cluster.replicate_pending("db-replica-a")
    print("\nAfter only replica-a catches up:")
    print(cluster.status())

    cluster.replicate_pending("db-replica-b")
    print("\nAfter replica-b catches up:")
    print(cluster.status())

    assert change_a.lsn < change_b.lsn
    assert cluster.replicas["db-replica-a"].data == cluster.primary.data
    assert cluster.replicas["db-replica-b"].data == cluster.primary.data


def demonstrate_synchronous_replication() -> None:
    print_heading("Synchronous replication")

    cluster = ReplicationCluster(
        primary_name="orders-primary",
        mode=ReplicationMode.SYNCHRONOUS,
        synchronous_replicas=1,
    )
    cluster.add_replica(Replica("orders-replica-a"))

    change = cluster.commit("SET", "order:9001", "PAID")
    print(f"Committed: {change.describe()}")
    print("Replica status:", cluster.status())

    cluster.replicas["orders-replica-a"].state = NodeState.DOWN

    try:
        cluster.commit("SET", "order:9002", "PAID")
    except RuntimeError as exc:
        print("Expected synchronous failure:", exc)

    cluster.replicas["orders-replica-a"].state = NodeState.UP
    cluster.replicas["orders-replica-a"].replay()

    # The failed transaction did not leave a committed acknowledgement in a
    # real transactional engine. This simulation still records the primary
    # operation, so production systems must distinguish WAL generation from
    # transaction commit status.
    print("Recovered replica:", cluster.status())


def demonstrate_lag_and_recovery() -> None:
    print_heading("Replication lag and recovery")

    cluster = ReplicationCluster(
        primary_name="analytics-primary",
        mode=ReplicationMode.ASYNCHRONOUS,
    )
    replica = Replica("analytics-replica")
    cluster.add_replica(replica)

    replica.state = NodeState.DOWN

    for index in range(1, 6):
        cluster.commit("SET", f"metric:{index}", str(index * 10), auto_replay=False)

    print("Replica is offline:")
    print(cluster.status())

    replica.state = NodeState.UP
    cluster.replicate_pending("analytics-replica")

    print("Replica recovered and replayed:")
    print(cluster.status())

    consistent, differences = cluster.compare_data("analytics-replica")
    print("Consistent:", consistent)
    print("Differences:", differences)

    assert consistent


def demonstrate_idempotent_replay() -> None:
    print_heading("Idempotent replay")

    cluster = ReplicationCluster(
        primary_name="inventory-primary",
        mode=ReplicationMode.ASYNCHRONOUS,
    )
    replica = Replica("inventory-replica")
    cluster.add_replica(replica)

    change = cluster.commit(
        "SET",
        "sku:ABC",
        "42",
        auto_replay=False,
    )

    replica.receive([change])
    replica.receive([change])

    applied = replica.replay()
    print("Logical changes applied:", applied)
    print("Replica data:", replica.data)

    assert replica.data["sku:ABC"] == "42"


def demonstrate_failover() -> None:
    print_heading("Failover and promotion")

    cluster = ReplicationCluster(
        primary_name="payments-primary",
        mode=ReplicationMode.ASYNCHRONOUS,
    )
    cluster.add_replica(Replica("payments-replica-a"))

    cluster.commit("SET", "payment:1", "AUTHORIZED")
    cluster.commit("SET", "payment:2", "SETTLED")

    replica = cluster.replicas["payments-replica-a"]
    print("Before failure:", cluster.status())

    cluster.primary.state = NodeState.DOWN
    promoted = cluster.promote_replica("payments-replica-a")

    print("Promoted primary:", promoted.name)
    print("New epoch:", promoted.epoch)
    print("Promoted data:", promoted.data)

    promoted_change = cluster.commit("SET", "payment:3", "SETTLED")
    print("Post-failover write:", promoted_change.describe())

    assert promoted.data["payment:3"] == "SETTLED"


def demonstrate_consistency_validation() -> None:
    print_heading("Consistency validation")

    cluster = ReplicationCluster(
        primary_name="catalog-primary",
        mode=ReplicationMode.ASYNCHRONOUS,
    )
    replica = Replica("catalog-replica")
    cluster.add_replica(replica)

    cluster.commit("SET", "product:1", "AVAILABLE")
    cluster.commit("SET", "product:2", "OUT_OF_STOCK")

    ok, differences = cluster.compare_data("catalog-replica")
    print("Before artificial divergence:", ok, differences)

    # Artificial divergence is deliberately introduced to demonstrate that
    # replication health cannot be inferred only from process availability.
    replica.data["product:2"] = "AVAILABLE"

    ok, differences = cluster.compare_data("catalog-replica")
    print("After divergence:", ok)
    print("Differences:", differences)

    assert not ok
    assert "product:2" in differences


def demonstrate_quorum_behavior() -> None:
    print_heading("Synchronous quorum-style acknowledgement")

    cluster = ReplicationCluster(
        primary_name="ledger-primary",
        mode=ReplicationMode.SYNCHRONOUS,
        synchronous_replicas=2,
    )
    cluster.add_replica(Replica("ledger-replica-a"))
    cluster.add_replica(Replica("ledger-replica-b"))
    cluster.add_replica(Replica("ledger-replica-c"))

    change = cluster.commit("SET", "ledger:1", "POSTED")
    print("Commit acknowledged with three healthy replicas:")
    print(change.describe())

    cluster.replicas["ledger-replica-c"].state = NodeState.DOWN

    change = cluster.commit("SET", "ledger:2", "POSTED")
    print("Commit still acknowledged because two replicas are available:")
    print(change.describe())

    cluster.replicas["ledger-replica-b"].state = NodeState.DOWN

    try:
        cluster.commit("SET", "ledger:3", "POSTED")
    except RuntimeError as exc:
        print("Expected quorum failure:", exc)


def main() -> None:
    demonstrate_asynchronous_replication()
    demonstrate_synchronous_replication()
    demonstrate_lag_and_recovery()
    demonstrate_idempotent_replay()
    demonstrate_failover()
    demonstrate_consistency_validation()
    demonstrate_quorum_behavior()

    print_heading("Replication model")
    print(
        "Primary writes create ordered change records. Asynchronous replication "
        "allows the primary to acknowledge without waiting for replica replay. "
        "Synchronous replication waits for configured replica acknowledgements. "
        "Replay position and lag provide observability, while promotion changes "
        "the write authority and epoch after failover."
    )


if __name__ == "__main__":
    main()
