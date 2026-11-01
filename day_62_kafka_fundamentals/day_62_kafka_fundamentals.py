#!/usr/bin/env python3

"""
Kafka Fundamentals: topics, partitions, offsets, and brokers.

Self-contained simulation of a small Kafka-like cluster. It models:
- Topics and partitions
- Ordered records within partitions
- Partition offsets
- Brokers and partition leadership
- Producers and consumers
- Consumer-group assignment
- Offset commits
- Partition rebalancing
- Broker failure and leader reassignment
- Retention
- Validation and failure handling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import time


class KafkaError(Exception):
    """Base exception for the simulation."""


class ValidationError(KafkaError):
    """Invalid topic, partition, broker, or record operation."""


class BrokerUnavailable(KafkaError):
    """Raised when a broker cannot serve a requested operation."""


class OffsetOutOfRange(KafkaError):
    """Raised when an offset is outside the available log."""


class BrokerState(Enum):
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass(frozen=True)
class Record:
    key: str
    value: str
    timestamp: float


@dataclass
class Partition:
    topic: str
    partition_id: int
    leader_id: int
    replicas: List[int]
    records: List[Record] = field(default_factory=list)
    retention_seconds: Optional[float] = None

    @property
    def next_offset(self) -> int:
        return len(self.records)

    def append(self, record: Record) -> int:
        offset = self.next_offset
        self.records.append(record)
        return offset

    def fetch(self, offset: int, max_records: int = 10) -> List[Tuple[int, Record]]:
        if offset < 0 or offset > self.next_offset:
            raise OffsetOutOfRange(
                f"{self.topic}-{self.partition_id}: offset {offset} "
                f"is outside [0, {self.next_offset}]"
            )

        return list(
            enumerate(
                self.records[offset: offset + max_records],
                start=offset,
            )
        )

    def apply_retention(self, now: float) -> int:
        if self.retention_seconds is None:
            return 0

        cutoff = now - self.retention_seconds
        removed = 0

        while self.records and self.records[0].timestamp < cutoff:
            self.records.pop(0)
            removed += 1

        return removed


@dataclass
class Topic:
    name: str
    partitions: Dict[int, Partition]
    replication_factor: int


@dataclass
class Broker:
    broker_id: int
    host: str
    state: BrokerState = BrokerState.ONLINE


@dataclass
class Consumer:
    consumer_id: str
    group_id: str
    assignments: List[Tuple[str, int]] = field(default_factory=list)


@dataclass
class ConsumerGroup:
    group_id: str
    consumers: Dict[str, Consumer] = field(default_factory=dict)
    committed_offsets: Dict[Tuple[str, int], int] = field(default_factory=dict)


class KafkaCluster:
    def __init__(self) -> None:
        self.brokers: Dict[int, Broker] = {}
        self.topics: Dict[str, Topic] = {}
        self.consumer_groups: Dict[str, ConsumerGroup] = {}

    def add_broker(self, broker_id: int, host: str) -> None:
        if broker_id in self.brokers:
            raise ValidationError(f"Broker {broker_id} already exists.")
        self.brokers[broker_id] = Broker(broker_id, host)

    def create_topic(
        self,
        name: str,
        partition_count: int,
        replication_factor: int,
        retention_seconds: Optional[float] = None,
    ) -> None:
        if not name or not name.strip():
            raise ValidationError("Topic name cannot be empty.")
        if name in self.topics:
            raise ValidationError(f"Topic {name} already exists.")
        if partition_count <= 0:
            raise ValidationError("partition_count must be positive.")
        if replication_factor <= 0:
            raise ValidationError("replication_factor must be positive.")
        if replication_factor > len(self.brokers):
            raise ValidationError(
                "Replication factor cannot exceed the broker count."
            )

        broker_ids = sorted(self.brokers)
        partitions: Dict[int, Partition] = {}

        for partition_id in range(partition_count):
            replicas = [
                broker_ids[(partition_id + replica) % len(broker_ids)]
                for replica in range(replication_factor)
            ]

            partitions[partition_id] = Partition(
                topic=name,
                partition_id=partition_id,
                leader_id=replicas[0],
                replicas=replicas,
                retention_seconds=retention_seconds,
            )

        self.topics[name] = Topic(
            name=name,
            partitions=partitions,
            replication_factor=replication_factor,
        )

    def _validate_leader(self, partition: Partition) -> Broker:
        broker = self.brokers[partition.leader_id]
        if broker.state is BrokerState.OFFLINE:
            raise BrokerUnavailable(
                f"Leader broker {broker.broker_id} is offline."
            )
        return broker

    def _select_partition(self, topic: str, key: str) -> int:
        topic_obj = self.topics[topic]
        return hash(key) % len(topic_obj.partitions)

    def produce(
        self,
        topic: str,
        key: str,
        value: str,
        partition_id: Optional[int] = None,
        timestamp: Optional[float] = None,
    ) -> Tuple[int, int]:
        if topic not in self.topics:
            raise ValidationError(f"Unknown topic: {topic}")
        if not key:
            raise ValidationError("Record key cannot be empty.")
        if not isinstance(value, str):
            raise ValidationError("Record value must be a string.")

        topic_obj = self.topics[topic]

        if partition_id is None:
            partition_id = self._select_partition(topic, key)

        if partition_id not in topic_obj.partitions:
            raise ValidationError(f"Unknown partition {partition_id}.")

        partition = topic_obj.partitions[partition_id]
        self._validate_leader(partition)

        record = Record(
            key=key,
            value=value,
            timestamp=time.time() if timestamp is None else timestamp,
        )

        offset = partition.append(record)

        # The simulation represents successful replication by validating that
        # the replica brokers exist. A real Kafka cluster persists replicas
        # independently and tracks ISR membership.
        for broker_id in partition.replicas:
            if broker_id not in self.brokers:
                raise BrokerUnavailable(
                    f"Replica broker {broker_id} does not exist."
                )

        return partition_id, offset

    def add_consumer(self, group_id: str, consumer_id: str) -> None:
        group = self.consumer_groups.setdefault(
            group_id,
            ConsumerGroup(group_id=group_id),
        )

        if consumer_id in group.consumers:
            raise ValidationError(
                f"Consumer {consumer_id} already belongs to group {group_id}."
            )

        group.consumers[consumer_id] = Consumer(
            consumer_id=consumer_id,
            group_id=group_id,
        )

    def rebalance(self, group_id: str, topics: List[str]) -> None:
        if group_id not in self.consumer_groups:
            raise ValidationError(f"Unknown consumer group {group_id}.")

        group = self.consumer_groups[group_id]

        if not group.consumers:
            raise ValidationError("Cannot assign partitions to an empty group.")

        all_partitions: List[Tuple[str, int]] = []

        for topic_name in topics:
            if topic_name not in self.topics:
                raise ValidationError(f"Unknown topic: {topic_name}")

            all_partitions.extend(
                (topic_name, partition_id)
                for partition_id in self.topics[topic_name].partitions
            )

        consumers = list(group.consumers.values())

        for consumer in consumers:
            consumer.assignments.clear()

        # Simple round-robin assignment. Kafka's actual group coordination
        # algorithms are more sophisticated, but the invariant is the same:
        # one partition is assigned to at most one consumer in a group.
        for index, partition in enumerate(all_partitions):
            consumers[index % len(consumers)].assignments.append(partition)

    def poll(
        self,
        group_id: str,
        consumer_id: str,
        max_records: int = 10,
    ) -> List[Tuple[str, int, int, Record]]:
        if group_id not in self.consumer_groups:
            raise ValidationError(f"Unknown group {group_id}.")

        group = self.consumer_groups[group_id]

        if consumer_id not in group.consumers:
            raise ValidationError(f"Unknown consumer {consumer_id}.")

        if max_records <= 0:
            raise ValidationError("max_records must be positive.")

        consumer = group.consumers[consumer_id]
        result: List[Tuple[str, int, int, Record]] = []

        for topic, partition_id in consumer.assignments:
            partition = self.topics[topic].partitions[partition_id]

            try:
                self._validate_leader(partition)
            except BrokerUnavailable:
                continue

            offset = group.committed_offsets.get((topic, partition_id), 0)

            for record_offset, record in partition.fetch(
                offset,
                max_records=max_records - len(result),
            ):
                result.append(
                    (topic, partition_id, record_offset, record)
                )

                if len(result) >= max_records:
                    return result

        return result

    def commit(
        self,
        group_id: str,
        topic: str,
        partition_id: int,
        offset: int,
    ) -> None:
        if group_id not in self.consumer_groups:
            raise ValidationError(f"Unknown group {group_id}.")

        if topic not in self.topics:
            raise ValidationError(f"Unknown topic {topic}.")

        if partition_id not in self.topics[topic].partitions:
            raise ValidationError(f"Unknown partition {partition_id}.")

        partition = self.topics[topic].partitions[partition_id]

        if offset < 0 or offset > partition.next_offset:
            raise OffsetOutOfRange(
                f"Cannot commit offset {offset}; "
                f"available range ends at {partition.next_offset}."
            )

        self.consumer_groups[group_id].committed_offsets[
            (topic, partition_id)
        ] = offset

    def fail_broker(self, broker_id: int) -> None:
        if broker_id not in self.brokers:
            raise ValidationError(f"Unknown broker {broker_id}.")

        self.brokers[broker_id].state = BrokerState.OFFLINE

        # Elect the first online replica for every affected partition.
        for topic in self.topics.values():
            for partition in topic.partitions.values():
                if partition.leader_id == broker_id:
                    candidates = [
                        replica
                        for replica in partition.replicas
                        if self.brokers[replica].state is BrokerState.ONLINE
                    ]

                    if candidates:
                        partition.leader_id = candidates[0]

    def recover_broker(self, broker_id: int) -> None:
        if broker_id not in self.brokers:
            raise ValidationError(f"Unknown broker {broker_id}.")
        self.brokers[broker_id].state = BrokerState.ONLINE

    def apply_retention(self, now: Optional[float] = None) -> int:
        current_time = time.time() if now is None else now
        removed = 0

        for topic in self.topics.values():
            for partition in topic.partitions.values():
                removed += partition.apply_retention(current_time)

        return removed

    def describe(self) -> None:
        print("\nCluster")
        print("=======")

        for broker in self.brokers.values():
            print(
                f"Broker {broker.broker_id}: "
                f"{broker.host} [{broker.state.value}]"
            )

        print("\nTopics")
        print("======")

        for topic in self.topics.values():
            print(
                f"{topic.name}: "
                f"{len(topic.partitions)} partitions, "
                f"RF={topic.replication_factor}"
            )

            for partition in topic.partitions.values():
                print(
                    f"  partition={partition.partition_id} "
                    f"leader={partition.leader_id} "
                    f"replicas={partition.replicas} "
                    f"next_offset={partition.next_offset}"
                )


def run_demo() -> None:
    cluster = KafkaCluster()

    for broker_id in range(1, 4):
        cluster.add_broker(
            broker_id,
            f"kafka-{broker_id}.internal.example",
        )

    cluster.create_topic(
        "orders",
        partition_count=3,
        replication_factor=2,
        retention_seconds=3600,
    )

    for key, value in [
        ("order-1001", "CREATED"),
        ("order-1002", "CREATED"),
        ("order-1003", "PAID"),
        ("order-1004", "PACKED"),
        ("order-1005", "SHIPPED"),
    ]:
        partition, offset = cluster.produce(
            "orders",
            key,
            value,
        )
        print(
            f"Produced key={key} "
            f"partition={partition} offset={offset}"
        )

    cluster.add_consumer("order-workers", "worker-a")
    cluster.add_consumer("order-workers", "worker-b")
    cluster.rebalance("order-workers", ["orders"])

    print("\nConsumer assignments")
    print("====================")

    for consumer in cluster.consumer_groups[
        "order-workers"
    ].consumers.values():
        print(
            f"{consumer.consumer_id}: "
            f"{consumer.assignments}"
        )

    print("\nPolling")
    print("=======")

    messages = cluster.poll(
        "order-workers",
        "worker-a",
        max_records=3,
    )

    for topic, partition, offset, record in messages:
        print(
            f"{topic}-{partition}@{offset}: "
            f"{record.key} -> {record.value}"
        )

        cluster.commit(
            "order-workers",
            topic,
            partition,
            offset + 1,
        )

    cluster.describe()

    print("\nBroker failure simulation")
    print("=========================")

    cluster.fail_broker(1)

    cluster.describe()

    try:
        cluster.produce(
            "orders",
            "order-after-failure",
            "CREATED",
        )
        print("Production succeeded after leader reassignment.")
    except BrokerUnavailable as exc:
        print(f"Production unavailable: {exc}")

    print("\nRetention simulation")
    print("====================")

    old_timestamp = time.time() - 7200

    partition, offset = cluster.produce(
        "orders",
        "old-order",
        "EXPIRED-CANDIDATE",
        timestamp=old_timestamp,
    )

    print(
        f"Inserted old record at "
        f"{cluster.topics['orders'].partitions[partition].topic}-"
        f"{partition}@{offset}"
    )

    removed = cluster.apply_retention()

    print(f"Records removed by retention: {removed}")

    print("\nValidation checks")
    print("=================")

    try:
        cluster.produce("missing-topic", "x", "value")
    except KafkaError as exc:
        print(f"Expected failure: {exc}")

    try:
        cluster.create_topic("orders", 1, 1)
    except KafkaError as exc:
        print(f"Expected failure: {exc}")

    try:
        cluster.commit(
            "order-workers",
            "orders",
            0,
            999999,
        )
    except KafkaError as exc:
        print(f"Expected failure: {exc}")


if __name__ == "__main__":
    run_demo()
