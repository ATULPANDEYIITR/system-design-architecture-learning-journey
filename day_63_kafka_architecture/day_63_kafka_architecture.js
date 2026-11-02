"use strict";

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const fs = require("node:fs/promises");

const BrokerState = Object.freeze({
    ONLINE: "ONLINE",
    OFFLINE: "OFFLINE",
});

const ConsumerState = Object.freeze({
    ACTIVE: "ACTIVE",
    INACTIVE: "INACTIVE",
});

class KafkaConfigurationError extends Error {}
class BrokerUnavailableError extends Error {}
class OffsetCommitError extends Error {}
class NotFoundError extends Error {}

function assertNonEmpty(value, field) {
    if (typeof value !== "string" || value.trim() === "") {
        throw new KafkaConfigurationError(`${field} must be non-empty`);
    }
}

function stablePartition(key, partitionCount) {
    const digest = crypto
        .createHash("sha256")
        .update(key)
        .digest();

    return digest.readUInt32BE(0) % partitionCount;
}

class Partition {
    constructor(topic, id, replicas) {
        this.topic = topic;
        this.id = id;
        this.replicas = [...replicas];
        this.leaderId = replicas[0];
        this.highWatermark = -1;
    }
}

class KafkaCluster extends EventEmitter {
    constructor({
        brokerCount = 3,
        minInSyncReplicas = 2,
    } = {}) {
        super();

        if (brokerCount < 1) {
            throw new KafkaConfigurationError(
                "brokerCount must be positive"
            );
        }

        if (
            minInSyncReplicas < 1 ||
            minInSyncReplicas > brokerCount
        ) {
            throw new KafkaConfigurationError(
                "invalid minInSyncReplicas"
            );
        }

        this.minInSyncReplicas = minInSyncReplicas;
        this.brokers = new Map();
        this.topics = new Map();
        this.consumers = new Map();
        this.groupOffsets = new Map();

        for (let id = 1; id <= brokerCount; id += 1) {
            this.brokers.set(id, {
                id,
                state: BrokerState.ONLINE,
                logs: new Map(),
            });
        }
    }

    createTopic(name, partitionCount, replicationFactor) {
        assertNonEmpty(name, "topic name");

        if (this.topics.has(name)) {
            throw new KafkaConfigurationError(
                `topic already exists: ${name}`
            );
        }

        if (partitionCount < 1) {
            throw new KafkaConfigurationError(
                "partitionCount must be positive"
            );
        }

        if (
            replicationFactor < 1 ||
            replicationFactor > this.brokers.size
        ) {
            throw new KafkaConfigurationError(
                "invalid replicationFactor"
            );
        }

        const partitions = [];

        for (let partitionId = 0; partitionId < partitionCount; partitionId += 1) {
            const replicas = [];

            for (
                let replicaIndex = 0;
                replicaIndex < replicationFactor;
                replicaIndex += 1
            ) {
                replicas.push(
                    ((partitionId + replicaIndex) % this.brokers.size) + 1
                );
            }

            const partition = new Partition(
                name,
                partitionId,
                replicas
            );

            partitions.push(partition);

            for (const brokerId of replicas) {
                const broker = this.brokers.get(brokerId);
                broker.logs.set(`${name}:${partitionId}`, []);
            }
        }

        this.topics.set(name, {
            name,
            partitions,
            replicationFactor,
        });

        this.emit("topicCreated", {
            topic: name,
            partitions: partitionCount,
        });
    }

    getPartition(topicName, key) {
        const topic = this.topics.get(topicName);

        if (!topic) {
            throw new NotFoundError(
                `unknown topic: ${topicName}`
            );
        }

        return topic.partitions[
            stablePartition(key, topic.partitions.length)
        ];
    }

    getPartitionById(topicName, partitionId) {
        const topic = this.topics.get(topicName);

        if (!topic) {
            throw new NotFoundError(
                `unknown topic: ${topicName}`
            );
        }

        const partition = topic.partitions[partitionId];

        if (!partition) {
            throw new NotFoundError(
                `unknown partition: ${topicName}[${partitionId}]`
            );
        }

        return partition;
    }

    onlineReplicas(partition) {
        return partition.replicas.filter(
            (brokerId) =>
                this.brokers.get(brokerId).state === BrokerState.ONLINE
        );
    }

    electLeader(topicName, partitionId) {
        const partition = this.getPartitionById(
            topicName,
            partitionId
        );

        const candidate = partition.replicas.find(
            (brokerId) =>
                this.brokers.get(brokerId).state === BrokerState.ONLINE
        );

        if (candidate === undefined) {
            throw new BrokerUnavailableError(
                `no online replica for ${topicName}[${partitionId}]`
            );
        }

        const previous = partition.leaderId;
        partition.leaderId = candidate;

        if (previous !== candidate) {
            this.emit("leaderChanged", {
                topic: topicName,
                partition: partitionId,
                previous,
                current: candidate,
            });
        }

        return candidate;
    }

    publish(topicName, key, value) {
        assertNonEmpty(key, "message key");

        if (
            value === null ||
            typeof value !== "object" ||
            Array.isArray(value)
        ) {
            throw new TypeError("message value must be an object");
        }

        const partition = this.getPartition(topicName, key);
        const leader = this.brokers.get(partition.leaderId);

        if (leader.state === BrokerState.OFFLINE) {
            this.electLeader(topicName, partition.id);
        }

        const inSync = this.onlineReplicas(partition);

        if (inSync.length < this.minInSyncReplicas) {
            throw new BrokerUnavailableError(
                `write rejected for ${topicName}[${partition.id}]: ` +
                `${inSync.length} in-sync replicas`
            );
        }

        const leaderBroker = this.brokers.get(partition.leaderId);
        const logKey = `${topicName}:${partition.id}`;
        const leaderLog = leaderBroker.logs.get(logKey);

        const message = Object.freeze({
            id: crypto.randomUUID(),
            topic: topicName,
            partition: partition.id,
            offset: leaderLog.length,
            key,
            value: structuredClone(value),
            timestamp: new Date().toISOString(),
            leaderId: partition.leaderId,
        });

        for (const brokerId of inSync) {
            this.brokers
                .get(brokerId)
                .logs
                .get(logKey)
                .push(message);
        }

        partition.highWatermark = message.offset;

        this.emit("messagePublished", message);

        return message;
    }

    registerConsumer(consumerId, groupId, subscriptions) {
        assertNonEmpty(consumerId, "consumerId");
        assertNonEmpty(groupId, "groupId");

        if (this.consumers.has(consumerId)) {
            throw new KafkaConfigurationError(
                `consumer exists: ${consumerId}`
            );
        }

        const subscriptionSet = new Set(subscriptions);

        for (const topic of subscriptionSet) {
            if (!this.topics.has(topic)) {
                throw new NotFoundError(
                    `unknown subscription: ${topic}`
                );
            }
        }

        const consumer = {
            id: consumerId,
            groupId,
            subscriptions: subscriptionSet,
            state: ConsumerState.ACTIVE,
            assignments: new Map(),
            processed: [],
        };

        this.consumers.set(consumerId, consumer);
        this.rebalanceGroup(groupId);
        this.emit("consumerJoined", consumer);
    }

    rebalanceGroup(groupId) {
        const members = [...this.consumers.values()]
            .filter(
                (consumer) =>
                    consumer.groupId === groupId &&
                    consumer.state === ConsumerState.ACTIVE
            );

        for (const consumer of members) {
            consumer.assignments.clear();
        }

        if (members.length === 0) {
            return;
        }

        const partitions = [];

        const topics = new Set();
        for (const member of members) {
            for (const topic of member.subscriptions) {
                topics.add(topic);
            }
        }

        for (const topicName of [...topics].sort()) {
            const topic = this.topics.get(topicName);

            for (const partition of topic.partitions) {
                partitions.push({
                    topic: topicName,
                    partition: partition.id,
                });
            }
        }

        partitions.sort(
            (a, b) =>
                a.topic.localeCompare(b.topic) ||
                a.partition - b.partition
        );

        for (const tp of partitions) {
            const eligible = members.filter(
                (member) => member.subscriptions.has(tp.topic)
            );

            if (eligible.length === 0) {
                continue;
            }

            const target = eligible.reduce((best, current) => {
                return current.assignments.size < best.assignments.size
                    ? current
                    : best;
            });

            const key = `${tp.topic}:${tp.partition}`;
            const committed =
                this.groupOffsets.get(groupId)?.get(key) ?? 0;

            target.assignments.set(key, {
                topic: tp.topic,
                partition: tp.partition,
                nextOffset: committed,
            });
        }

        this.emit("rebalance", {
            groupId,
            assignments: members.map((member) => ({
                consumerId: member.id,
                partitions: [...member.assignments.keys()],
            })),
        });
    }

    setBrokerState(brokerId, online) {
        const broker = this.brokers.get(brokerId);

        if (!broker) {
            throw new NotFoundError(`unknown broker: ${brokerId}`);
        }

        broker.state = online
            ? BrokerState.ONLINE
            : BrokerState.OFFLINE;

        if (!online) {
            for (const topic of this.topics.values()) {
                for (const partition of topic.partitions) {
                    if (partition.leaderId === brokerId) {
                        this.electLeader(
                            topic.name,
                            partition.id
                        );
                    }
                }
            }
        }

        const groups = new Set(
            [...this.consumers.values()].map(
                (consumer) => consumer.groupId
            )
        );

        for (const groupId of groups) {
            this.rebalanceGroup(groupId);
        }

        this.emit("brokerStateChanged", {
            brokerId,
            state: broker.state,
        });
    }

    async poll(consumerId, maxRecords = 10) {
        const consumer = this.consumers.get(consumerId);

        if (!consumer) {
            throw new NotFoundError(
                `unknown consumer: ${consumerId}`
            );
        }

        if (consumer.state !== ConsumerState.ACTIVE) {
            throw new Error("consumer is inactive");
        }

        if (!Number.isInteger(maxRecords) || maxRecords < 1) {
            throw new RangeError("maxRecords must be positive");
        }

        const result = [];

        for (const assignment of consumer.assignments.values()) {
            if (result.length >= maxRecords) {
                break;
            }

            const partition = this.getPartitionById(
                assignment.topic,
                assignment.partition
            );

            if (
                this.brokers.get(partition.leaderId).state ===
                BrokerState.OFFLINE
            ) {
                this.electLeader(
                    assignment.topic,
                    assignment.partition
                );
            }

            const leader = this.brokers.get(partition.leaderId);
            const log = leader.logs.get(
                `${assignment.topic}:${assignment.partition}`
            );

            while (
                assignment.nextOffset < log.length &&
                result.length < maxRecords
            ) {
                result.push(log[assignment.nextOffset]);
                assignment.nextOffset += 1;
            }
        }

        await new Promise((resolve) => setImmediate(resolve));

        return result;
    }

    commitOffsets(consumerId, messages) {
        const consumer = this.consumers.get(consumerId);

        if (!consumer) {
            throw new NotFoundError(
                `unknown consumer: ${consumerId}`
            );
        }

        if (!this.groupOffsets.has(consumer.groupId)) {
            this.groupOffsets.set(consumer.groupId, new Map());
        }

        const offsets = this.groupOffsets.get(consumer.groupId);

        for (const message of messages) {
            const key = `${message.topic}:${message.partition}`;
            const nextOffset = message.offset + 1;
            const previous = offsets.get(key) ?? 0;

            if (nextOffset < previous) {
                throw new OffsetCommitError(
                    `offset regression for ${key}`
                );
            }

            offsets.set(key, nextOffset);
        }

        for (const message of messages) {
            consumer.processed.push(message);
        }

        this.emit("offsetCommitted", {
            consumerId,
            groupId: consumer.groupId,
            messages: messages.length,
        });
    }

    async consumeAndCommit(consumerId, maxRecords = 10) {
        const messages = await this.poll(
            consumerId,
            maxRecords
        );

        if (messages.length > 0) {
            this.commitOffsets(consumerId, messages);
        }

        return messages;
    }

    stopConsumer(consumerId) {
        const consumer = this.consumers.get(consumerId);

        if (!consumer) {
            throw new NotFoundError(
                `unknown consumer: ${consumerId}`
            );
        }

        consumer.state = ConsumerState.INACTIVE;
        consumer.assignments.clear();
        this.rebalanceGroup(consumer.groupId);
    }

    describe() {
        const topics = {};

        for (const topic of this.topics.values()) {
            topics[topic.name] = topic.partitions.map(
                (partition) => ({
                    partition: partition.id,
                    leader: partition.leaderId,
                    replicas: partition.replicas,
                    highWatermark: partition.highWatermark,
                    onlineReplicas:
                        this.onlineReplicas(partition),
                })
            );
        }

        return {
            brokers: Object.fromEntries(
                [...this.brokers.values()].map((broker) => [
                    broker.id,
                    broker.state,
                ])
            ),
            topics,
            groups: Object.fromEntries(
                [...this.groupOffsets.entries()].map(
                    ([groupId, offsets]) => [
                        groupId,
                        Object.fromEntries(offsets),
                    ]
                )
            ),
        };
    }

    async saveState(fileName) {
        await fs.writeFile(
            fileName,
            JSON.stringify(this.describe(), null, 2),
            "utf8"
        );
    }
}

async function main() {
    const cluster = new KafkaCluster({
        brokerCount: 3,
        minInSyncReplicas: 2,
    });

    cluster.on("leaderChanged", (event) => {
        console.log(
            `Leader change ${event.topic}[${event.partition}]: ` +
            `${event.previous} -> ${event.current}`
        );
    });

    cluster.on("rebalance", (event) => {
        console.log(
            `Rebalance ${event.groupId}:`,
            event.assignments
        );
    });

    cluster.createTopic("orders", 3, 3);

    cluster.registerConsumer(
        "orders-worker-1",
        "order-processing",
        ["orders"]
    );

    cluster.registerConsumer(
        "orders-worker-2",
        "order-processing",
        ["orders"]
    );

    const orders = [
        ["customer-100", { orderId: "O-100", amount: 1250 }],
        ["customer-101", { orderId: "O-101", amount: 850 }],
        ["customer-102", { orderId: "O-102", amount: 2200 }],
        ["customer-100", { orderId: "O-103", amount: 410 }],
        ["customer-103", { orderId: "O-104", amount: 990 }],
        ["customer-104", { orderId: "O-105", amount: 730 }],
    ];

    for (const [key, value] of orders) {
        cluster.publish("orders", key, value);
    }

    console.log(
        "\nInitial state:",
        JSON.stringify(cluster.describe(), null, 2)
    );

    const batch = await cluster.consumeAndCommit(
        "orders-worker-1",
        3
    );

    console.log("\nWorker 1 processed:");
    console.table(
        batch.map((message) => ({
            partition: message.partition,
            offset: message.offset,
            orderId: message.value.orderId,
        }))
    );

    cluster.setBrokerState(1, false);

    try {
        cluster.publish(
            "orders",
            "customer-105",
            { orderId: "O-106", amount: 1500 }
        );
    } catch (error) {
        console.log(
            `Expected failure: ${error.message}`
        );
    }

    cluster.setBrokerState(1, true);

    cluster.publish(
        "orders",
        "customer-105",
        { orderId: "O-106", amount: 1500 }
    );

    const secondBatch = await cluster.consumeAndCommit(
        "orders-worker-2",
        20
    );

    console.log("\nWorker 2 processed:");
    console.table(
        secondBatch.map((message) => ({
            partition: message.partition,
            offset: message.offset,
            orderId: message.value.orderId,
        }))
    );

    cluster.stopConsumer("orders-worker-1");

    await cluster.saveState("kafka_cluster_state.json");

    console.log(
        "\nFinal state:",
        JSON.stringify(cluster.describe(), null, 2)
    );
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
