from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("kafka-simulation")


class BrokerState(Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class ConsumerState(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True)
class Message:
    topic: str
    partition: int
    offset: int
    key: str
    value: dict
    timestamp: float
    leader_broker: int

    @property
    def message_id(self) -> str:
        raw = f"{self.topic}:{self.partition}:{self.offset}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Broker:
    broker_id: int
    state: BrokerState = BrokerState.ONLINE
    logs: Dict[Tuple[str, int], List[Message]] = field(default_factory=dict)


@dataclass
class Partition:
    topic: str
    partition_id: int
    replicas: List[int]
    leader_id: int
    high_watermark: int = -1

    def online_replicas(self, brokers: Dict[int, Broker]) -> List[int]:
        return [
            broker_id
            for broker_id in self.replicas
            if brokers[broker_id].state == BrokerState.ONLINE
        ]


@dataclass
class Topic:
    name: str
    partitions: List[Partition]
    replication_factor: int


@dataclass
class Consumer:
    consumer_id: str
    group_id: str
    subscriptions: Set[str]
    state: ConsumerState = ConsumerState.ACTIVE
    assignments: Dict[Tuple[str, int], int] = field(default_factory=dict)
    processed: List[Message] = field(default_factory=list)


class KafkaConfigurationError(ValueError):
    pass


class NotFoundError(KeyError):
    pass


class BrokerUnavailableError(RuntimeError):
    pass


class OffsetCommitError(RuntimeError):
    pass


class KafkaCluster:
    """
    Small in-memory Kafka-like cluster.

    It models:
    - topics and partitions
    - leaders and replicas
    - append-only partition logs
    - replication
    - consumer groups
    - partition assignment
    - committed offsets
    - leader failover
    - minimum in-sync replica enforcement
    """

    def __init__(
        self,
        broker_count: int = 3,
        min_insync_replicas: int = 2,
    ) -> None:
        if broker_count < 1:
            raise KafkaConfigurationError("broker_count must be positive")
        if not 1 <= min_insync_replicas <= broker_count:
            raise KafkaConfigurationError(
                "min_insync_replicas must be between 1 and broker_count"
            )

        self.brokers: Dict[int, Broker] = {
            broker_id: Broker(broker_id)
            for broker_id in range(1, broker_count + 1)
        }
        self.topics: Dict[str, Topic] = {}
        self.consumers: Dict[str, Consumer] = {}
        self.group_offsets: Dict[str, Dict[Tuple[str, int], int]] = defaultdict(dict)
        self.min_insync_replicas = min_insync_replicas
        self._lock = threading.RLock()

    def create_topic(
        self,
        name: str,
        partitions: int,
        replication_factor: int,
    ) -> None:
        with self._lock:
            if not name.strip():
                raise KafkaConfigurationError("topic name cannot be empty")
            if name in self.topics:
                raise KafkaConfigurationError(f"topic already exists: {name}")
            if partitions <= 0:
                raise KafkaConfigurationError("partitions must be positive")
            if not 1 <= replication_factor <= len(self.brokers):
                raise KafkaConfigurationError(
                    "replication_factor exceeds broker capacity"
                )

            partition_objects: List[Partition] = []

            for partition_id in range(partitions):
                replicas = [
                    ((partition_id + replica_index) % len(self.brokers)) + 1
                    for replica_index in range(replication_factor)
                ]
                leader_id = replicas[0]

                partition = Partition(
                    topic=name,
                    partition_id=partition_id,
                    replicas=replicas,
                    leader_id=leader_id,
                )
                partition_objects.append(partition)

                for broker_id in replicas:
                    self.brokers[broker_id].logs[(name, partition_id)] = []

            self.topics[name] = Topic(
                name=name,
                partitions=partition_objects,
                replication_factor=replication_factor,
            )

    def _partition_for_key(self, topic: str, key: str) -> Partition:
        if topic not in self.topics:
            raise NotFoundError(f"unknown topic: {topic}")

        topic_obj = self.topics[topic]
        digest = int(hashlib.sha256(key.encode()).hexdigest(), 16)
        return topic_obj.partitions[digest % len(topic_obj.partitions)]

    def _next_offset(self, partition: Partition) -> int:
        leader_log = self.brokers[partition.leader_id].logs[
            (partition.topic, partition.partition_id)
        ]
        return len(leader_log)

    def publish(
        self,
        topic: str,
        key: str,
        value: dict,
    ) -> Message:
        with self._lock:
            if not isinstance(value, dict):
                raise TypeError("message value must be a dictionary")

            partition = self._partition_for_key(topic, key)

            if self.brokers[partition.leader_id].state != BrokerState.ONLINE:
                self.elect_leader(partition.topic, partition.partition_id)

            leader_id = partition.leader_id
            online_replicas = partition.online_replicas(self.brokers)

            if len(online_replicas) < self.min_insync_replicas:
                raise BrokerUnavailableError(
                    f"cannot publish {topic}[{partition.partition_id}]: "
                    f"only {len(online_replicas)} in-sync replicas"
                )

            offset = self._next_offset(partition)

            message = Message(
                topic=topic,
                partition=partition.partition_id,
                offset=offset,
                key=key,
                value=value,
                timestamp=time.time(),
                leader_broker=leader_id,
            )

            for broker_id in online_replicas:
                self.brokers[broker_id].logs[
                    (topic, partition.partition_id)
                ].append(message)

            partition.high_watermark = offset
            return message

    def elect_leader(self, topic: str, partition_id: int) -> int:
        with self._lock:
            partition = self._get_partition(topic, partition_id)

            candidates = [
                broker_id
                for broker_id in partition.replicas
                if self.brokers[broker_id].state == BrokerState.ONLINE
            ]

            if not candidates:
                raise BrokerUnavailableError(
                    f"no online replica for {topic}[{partition_id}]"
                )

            old_leader = partition.leader_id
            partition.leader_id = candidates[0]

            if old_leader != partition.leader_id:
                LOGGER.warning(
                    "leader changed for %s[%d]: %d -> %d",
                    topic,
                    partition_id,
                    old_leader,
                    partition.leader_id,
                )

            return partition.leader_id

    def set_broker_state(self, broker_id: int, online: bool) -> None:
        with self._lock:
            if broker_id not in self.brokers:
                raise NotFoundError(f"unknown broker: {broker_id}")

            broker = self.brokers[broker_id]
            broker.state = BrokerState.ONLINE if online else BrokerState.OFFLINE

            if not online:
                for topic in self.topics.values():
                    for partition in topic.partitions:
                        if partition.leader_id == broker_id:
                            self.elect_leader(
                                partition.topic,
                                partition.partition_id,
                            )

            self.rebalance_all_groups()

    def _get_partition(self, topic: str, partition_id: int) -> Partition:
        if topic not in self.topics:
            raise NotFoundError(f"unknown topic: {topic}")

        topic_obj = self.topics[topic]

        if not 0 <= partition_id < len(topic_obj.partitions):
            raise NotFoundError(
                f"unknown partition: {topic}[{partition_id}]"
            )

        return topic_obj.partitions[partition_id]

    def register_consumer(
        self,
        consumer_id: str,
        group_id: str,
        subscriptions: Iterable[str],
    ) -> None:
        with self._lock:
            if consumer_id in self.consumers:
                raise KafkaConfigurationError(
                    f"consumer already exists: {consumer_id}"
                )

            subscriptions = set(subscriptions)

            if not subscriptions:
                raise KafkaConfigurationError(
                    "consumer must subscribe to at least one topic"
                )

            unknown = subscriptions - self.topics.keys()
            if unknown:
                raise NotFoundError(
                    f"unknown subscriptions: {sorted(unknown)}"
                )

            self.consumers[consumer_id] = Consumer(
                consumer_id=consumer_id,
                group_id=group_id,
                subscriptions=subscriptions,
            )

            self.rebalance_group(group_id)

    def rebalance_all_groups(self) -> None:
        group_ids = {
            consumer.group_id
            for consumer in self.consumers.values()
            if consumer.state == ConsumerState.ACTIVE
        }

        for group_id in group_ids:
            self.rebalance_group(group_id)

    def rebalance_group(self, group_id: str) -> None:
        with self._lock:
            members = [
                consumer
                for consumer in self.consumers.values()
                if consumer.group_id == group_id
                and consumer.state == ConsumerState.ACTIVE
            ]

            for consumer in members:
                consumer.assignments.clear()

            if not members:
                return

            assignments: List[Tuple[str, int]] = []

            subscribed_topics = set().union(
                *(consumer.subscriptions for consumer in members)
            )

            for topic_name in sorted(subscribed_topics):
                topic = self.topics[topic_name]

                for partition in topic.partitions:
                    assignments.append(
                        (topic_name, partition.partition_id)
                    )

            assignments.sort()

            for index, tp in enumerate(assignments):
                consumer = members[index % len(members)]

                if tp[0] in consumer.subscriptions:
                    consumer.assignments[tp] = self.group_offsets[
                        group_id
                    ].get(tp, 0)

            # A subscription mismatch can leave partitions unassigned.
            # Assign those partitions only to members subscribed to them.
            for tp in assignments:
                if any(tp in member.assignments for member in members):
                    continue

                eligible = [
                    member
                    for member in members
                    if tp[0] in member.subscriptions
                ]

                if eligible:
                    target = min(
                        eligible,
                        key=lambda member: len(member.assignments),
                    )
                    target.assignments[tp] = self.group_offsets[
                        group_id
                    ].get(tp, 0)

    def stop_consumer(self, consumer_id: str) -> None:
        with self._lock:
            consumer = self._get_consumer(consumer_id)
            consumer.state = ConsumerState.INACTIVE
            consumer.assignments.clear()
            self.rebalance_group(consumer.group_id)

    def start_consumer(self, consumer_id: str) -> None:
        with self._lock:
            consumer = self._get_consumer(consumer_id)
            consumer.state = ConsumerState.ACTIVE
            self.rebalance_group(consumer.group_id)

    def poll(
        self,
        consumer_id: str,
        max_records: int = 10,
    ) -> List[Message]:
        with self._lock:
            if max_records <= 0:
                raise ValueError("max_records must be positive")

            consumer = self._get_consumer(consumer_id)

            if consumer.state != ConsumerState.ACTIVE:
                raise RuntimeError("consumer is inactive")

            messages: List[Message] = []

            for tp, current_offset in sorted(
                consumer.assignments.items()
            ):
                if len(messages) >= max_records:
                    break

                topic_name, partition_id = tp
                partition = self._get_partition(
                    topic_name,
                    partition_id,
                )

                leader_id = partition.leader_id

                if self.brokers[leader_id].state != BrokerState.ONLINE:
                    self.elect_leader(topic_name, partition_id)
                    leader_id = partition.leader_id

                log = self.brokers[leader_id].logs[tp]

                while (
                    current_offset < len(log)
                    and len(messages) < max_records
                ):
                    messages.append(log[current_offset])
                    current_offset += 1

                consumer.assignments[tp] = current_offset

            return messages

    def commit_offsets(
        self,
        consumer_id: str,
        offsets: Dict[Tuple[str, int], int],
    ) -> None:
        with self._lock:
            consumer = self._get_consumer(consumer_id)

            for tp, offset in offsets.items():
                if tp not in consumer.assignments:
                    raise OffsetCommitError(
                        f"{consumer_id} does not own {tp}"
                    )

                if offset < 0:
                    raise OffsetCommitError("offset cannot be negative")

                previous = self.group_offsets[
                    consumer.group_id
                ].get(tp, 0)

                if offset < previous:
                    raise OffsetCommitError(
                        f"offset regression for {tp}: "
                        f"{previous} -> {offset}"
                    )

                self.group_offsets[consumer.group_id][tp] = offset

    def consume_and_commit(
        self,
        consumer_id: str,
        max_records: int = 10,
    ) -> List[Message]:
        messages = self.poll(consumer_id, max_records)

        if not messages:
            return []

        consumer = self._get_consumer(consumer_id)

        offsets: Dict[Tuple[str, int], int] = {}
        for message in messages:
            tp = (message.topic, message.partition)
            offsets[tp] = message.offset + 1

        self.commit_offsets(consumer_id, offsets)
        consumer.processed.extend(messages)
        return messages

    def describe(self) -> dict:
        with self._lock:
            return {
                "brokers": {
                    broker_id: broker.state.value
                    for broker_id, broker in self.brokers.items()
                },
                "topics": {
                    topic.name: [
                        {
                            "partition": p.partition_id,
                            "leader": p.leader_id,
                            "replicas": p.replicas,
                            "high_watermark": p.high_watermark,
                            "online_replicas": p.online_replicas(
                                self.brokers
                            ),
                        }
                        for p in topic.partitions
                    ]
                    for topic in self.topics.values()
                },
                "groups": {
                    group_id: offsets
                    for group_id, offsets in self.group_offsets.items()
                },
            }

    def export_state(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.describe(), indent=2, default=str),
            encoding="utf-8",
        )

    def _get_consumer(self, consumer_id: str) -> Consumer:
        if consumer_id not in self.consumers:
            raise NotFoundError(f"unknown consumer: {consumer_id}")
        return self.consumers[consumer_id]


def run_demo() -> None:
    cluster = KafkaCluster(
        broker_count=3,
        min_insync_replicas=2,
    )

    cluster.create_topic(
        name="orders",
        partitions=3,
        replication_factor=3,
    )

    cluster.register_consumer(
        consumer_id="orders-worker-1",
        group_id="order-processing",
        subscriptions={"orders"},
    )
    cluster.register_consumer(
        consumer_id="orders-worker-2",
        group_id="order-processing",
        subscriptions={"orders"},
    )

    orders = [
        ("customer-100", {"order_id": "O-100", "amount": 1250}),
        ("customer-101", {"order_id": "O-101", "amount": 850}),
        ("customer-102", {"order_id": "O-102", "amount": 2200}),
        ("customer-100", {"order_id": "O-103", "amount": 410}),
        ("customer-103", {"order_id": "O-104", "amount": 990}),
        ("customer-104", {"order_id": "O-105", "amount": 730}),
    ]

    for key, value in orders:
        cluster.publish("orders", key, value)

    print("INITIAL CLUSTER")
    print(json.dumps(cluster.describe(), indent=2))

    first_batch = cluster.consume_and_commit(
        "orders-worker-1",
        max_records=3,
    )

    print("\nWORKER 1 CONSUMED")
    for message in first_batch:
        print(
            message.topic,
            message.partition,
            message.offset,
            message.value,
        )

    cluster.set_broker_state(1, online=False)

    print("\nAFTER BROKER 1 FAILURE")
    print(json.dumps(cluster.describe(), indent=2))

    try:
        cluster.publish(
            "orders",
            "customer-105",
            {"order_id": "O-106", "amount": 1500},
        )
    except BrokerUnavailableError as exc:
        print("Publish failure:", exc)

    cluster.set_broker_state(1, online=True)

    message = cluster.publish(
        "orders",
        "customer-105",
        {"order_id": "O-106", "amount": 1500},
    )

    print("\nRECOVERED PUBLISH")
    print(message)

    second_batch = cluster.consume_and_commit(
        "orders-worker-2",
        max_records=10,
    )

    print("\nWORKER 2 CONSUMED")
    for item in second_batch:
        print(
            item.topic,
            item.partition,
            item.offset,
            item.value,
        )

    cluster.stop_consumer("orders-worker-1")

    print("\nAFTER CONSUMER FAILURE")
    print(json.dumps(cluster.describe(), indent=2))

    cluster.export_state(Path("kafka_cluster_state.json"))
    print("\nState exported to kafka_cluster_state.json")


if __name__ == "__main__":
    run_demo()
