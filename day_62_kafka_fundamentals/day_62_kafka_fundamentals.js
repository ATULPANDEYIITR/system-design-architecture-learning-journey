'use strict';

/*
 * Kafka Fundamentals: Topics, Partitions, Offsets, and Brokers.
 *
 * This Node.js program models Kafka-style behavior using event-driven
 * processing. It intentionally uses JavaScript's Map, Set, Promise,
 * EventEmitter, and asynchronous processing capabilities.
 */

const { EventEmitter } = require('node:events');
const crypto = require('node:crypto');

class KafkaError extends Error {}
class ValidationError extends KafkaError {}
class BrokerUnavailable extends KafkaError {}
class OffsetOutOfRange extends KafkaError {}

const BrokerState = Object.freeze({
    ONLINE: 'online',
    OFFLINE: 'offline'
});

const RecordStatus = Object.freeze({
    ACCEPTED: 'accepted',
    REJECTED: 'rejected'
});

class Partition {
    constructor(topic, id, replicas, retentionMs = null) {
        if (!topic || id < 0 || replicas.length === 0) {
            throw new ValidationError('Invalid partition configuration');
        }

        this.topic = topic;
        this.id = id;
        this.replicas = [...replicas];
        this.leaderId = replicas[0];
        this.records = [];
        this.retentionMs = retentionMs;
    }

    get nextOffset() {
        return this.records.length;
    }

    append(record) {
        const offset = this.nextOffset;
        this.records.push({ ...record, offset });
        return offset;
    }

    fetch(offset, limit) {
        if (!Number.isInteger(offset) || offset < 0 || offset > this.nextOffset) {
            throw new OffsetOutOfRange(
                `${this.topic}-${this.id}: invalid offset ${offset}`
            );
        }

        if (!Number.isInteger(limit) || limit <= 0) {
            throw new ValidationError('Fetch limit must be positive');
        }

        return this.records.slice(offset, offset + limit);
    }

    expire(now) {
        if (this.retentionMs === null) {
            return 0;
        }

        const cutoff = now - this.retentionMs;
        const originalLength = this.records.length;

        this.records = this.records.filter(
            record => record.timestamp >= cutoff
        );

        return originalLength - this.records.length;
    }
}

class Topic {
    constructor(name, partitionCount, replicationFactor, brokerIds) {
        if (!name.trim()) {
            throw new ValidationError('Topic name cannot be empty');
        }

        if (partitionCount <= 0 || replicationFactor <= 0) {
            throw new ValidationError('Invalid topic dimensions');
        }

        if (replicationFactor > brokerIds.length) {
            throw new ValidationError(
                'Replication factor exceeds broker count'
            );
        }

        this.name = name;
        this.partitions = new Map();

        for (let p = 0; p < partitionCount; p += 1) {
            const replicas = [];

            for (let r = 0; r < replicationFactor; r += 1) {
                replicas.push(
                    brokerIds[(p + r) % brokerIds.length]
                );
            }

            this.partitions.set(
                p,
                new Partition(name, p, replicas)
            );
        }
    }
}

class Consumer {
    constructor(id, groupId) {
        this.id = id;
        this.groupId = groupId;
        this.assignments = new Set();
    }
}

class ConsumerGroup {
    constructor(id) {
        this.id = id;
        this.consumers = new Map();
        this.committedOffsets = new Map();
    }

    addConsumer(consumer) {
        if (this.consumers.has(consumer.id)) {
            throw new ValidationError(
                `Consumer ${consumer.id} already exists`
            );
        }

        this.consumers.set(consumer.id, consumer);
    }
}

class KafkaCluster extends EventEmitter {
    constructor() {
        super();
        this.brokers = new Map();
        this.topics = new Map();
        this.groups = new Map();

        this.on('brokerFailed', event => {
            console.log(
                `[event] broker ${event.brokerId} failed; ` +
                `${event.reassigned} partition leader(s) evaluated`
            );
        });

        this.on('recordProduced', event => {
            console.log(
                `[event] ${event.topic}-${event.partition}@${event.offset} ` +
                `accepted`
            );
        });

        this.on('recordRejected', event => {
            console.log(
                `[event] record rejected: ${event.reason}`
            );
        });
    }

    addBroker(id, host) {
        if (this.brokers.has(id)) {
            throw new ValidationError(`Broker ${id} already exists`);
        }

        this.brokers.set(id, {
            id,
            host,
            state: BrokerState.ONLINE
        });
    }

    createTopic(name, partitions, replicationFactor) {
        if (this.topics.has(name)) {
            throw new ValidationError(`Topic ${name} already exists`);
        }

        const brokerIds = [...this.brokers.keys()].sort((a, b) => a - b);

        this.topics.set(
            name,
            new Topic(
                name,
                partitions,
                replicationFactor,
                brokerIds
            )
        );
    }

    partitionForKey(topic, key) {
        const topicObject = this.topics.get(topic);

        if (!topicObject) {
            throw new ValidationError(`Unknown topic ${topic}`);
        }

        const digest = crypto
            .createHash('sha256')
            .update(key)
            .digest();

        const numericHash = digest.readUInt32BE(0);

        return numericHash % topicObject.partitions.size;
    }

    ensureLeaderAvailable(partition) {
        const broker = this.brokers.get(partition.leaderId);

        if (!broker || broker.state === BrokerState.OFFLINE) {
            throw new BrokerUnavailable(
                `Leader broker ${partition.leaderId} is unavailable`
            );
        }
    }

    async produce(topic, key, value, partitionId = null) {
        try {
            if (!key || typeof value !== 'string') {
                throw new ValidationError(
                    'Key is required and value must be a string'
                );
            }

            const topicObject = this.topics.get(topic);

            if (!topicObject) {
                throw new ValidationError(`Unknown topic ${topic}`);
            }

            const selectedPartition =
                partitionId ??
                this.partitionForKey(topic, key);

            const partition =
                topicObject.partitions.get(selectedPartition);

            if (!partition) {
                throw new ValidationError(
                    `Unknown partition ${selectedPartition}`
                );
            }

            this.ensureLeaderAvailable(partition);

            const record = {
                key,
                value,
                timestamp: Date.now()
            };

            // Promise.resolve() models asynchronous broker processing while
            // keeping the example dependency-free.
            await Promise.resolve();

            const offset = partition.append(record);

            const event = {
                status: RecordStatus.ACCEPTED,
                topic,
                partition: selectedPartition,
                offset
            };

            this.emit('recordProduced', event);

            return event;
        } catch (error) {
            this.emit('recordRejected', {
                reason: error.message
            });
            throw error;
        }
    }

    createGroup(groupId) {
        if (this.groups.has(groupId)) {
            throw new ValidationError(
                `Group ${groupId} already exists`
            );
        }

        this.groups.set(groupId, new ConsumerGroup(groupId));
    }

    addConsumer(groupId, consumerId) {
        const group = this.groups.get(groupId);

        if (!group) {
            throw new ValidationError(`Unknown group ${groupId}`);
        }

        group.addConsumer(
            new Consumer(consumerId, groupId)
        );
    }

    rebalance(groupId, topicNames) {
        const group = this.groups.get(groupId);

        if (!group || group.consumers.size === 0) {
            throw new ValidationError(
                'Consumer group must contain at least one consumer'
            );
        }

        const assignments = [];

        for (const topicName of topicNames) {
            const topic = this.topics.get(topicName);

            if (!topic) {
                throw new ValidationError(
                    `Unknown topic ${topicName}`
                );
            }

            for (const partitionId of topic.partitions.keys()) {
                assignments.push(`${topicName}:${partitionId}`);
            }
        }

        for (const consumer of group.consumers.values()) {
            consumer.assignments.clear();
        }

        const consumers = [...group.consumers.values()];

        assignments.forEach((assignment, index) => {
            consumers[index % consumers.length]
                .assignments
                .add(assignment);
        });

        return [...group.consumers.values()].map(consumer => ({
            consumerId: consumer.id,
            assignments: [...consumer.assignments]
        }));
    }

    async poll(groupId, consumerId, maxRecords = 10) {
        const group = this.groups.get(groupId);

        if (!group) {
            throw new ValidationError(`Unknown group ${groupId}`);
        }

        const consumer = group.consumers.get(consumerId);

        if (!consumer) {
            throw new ValidationError(
                `Unknown consumer ${consumerId}`
            );
        }

        if (maxRecords <= 0) {
            throw new ValidationError(
                'maxRecords must be positive'
            );
        }

        const result = [];

        for (const assignment of consumer.assignments) {
            if (result.length >= maxRecords) {
                break;
            }

            const separator = assignment.lastIndexOf(':');
            const topicName = assignment.slice(0, separator);
            const partitionId = Number(
                assignment.slice(separator + 1)
            );

            const topic = this.topics.get(topicName);
            const partition = topic.partitions.get(partitionId);

            try {
                this.ensureLeaderAvailable(partition);
            } catch {
                continue;
            }

            const groupKey = `${topicName}:${partitionId}`;
            const offset =
                group.committedOffsets.get(groupKey) ?? 0;

            const records = partition.fetch(
                offset,
                maxRecords - result.length
            );

            result.push(
                ...records.map(record => ({
                    topic: topicName,
                    partition: partitionId,
                    ...record
                }))
            );
        }

        await Promise.resolve();
        return result;
    }

    commit(groupId, topicName, partitionId, nextOffset) {
        const group = this.groups.get(groupId);

        if (!group) {
            throw new ValidationError(`Unknown group ${groupId}`);
        }

        const topic = this.topics.get(topicName);

        if (!topic) {
            throw new ValidationError(`Unknown topic ${topicName}`);
        }

        const partition = topic.partitions.get(partitionId);

        if (!partition) {
            throw new ValidationError('Unknown partition');
        }

        if (
            !Number.isInteger(nextOffset) ||
            nextOffset < 0 ||
            nextOffset > partition.nextOffset
        ) {
            throw new OffsetOutOfRange(
                `Cannot commit offset ${nextOffset}`
            );
        }

        group.committedOffsets.set(
            `${topicName}:${partitionId}`,
            nextOffset
        );
    }

    failBroker(brokerId) {
        const broker = this.brokers.get(brokerId);

        if (!broker) {
            throw new ValidationError(
                `Unknown broker ${brokerId}`
            );
        }

        broker.state = BrokerState.OFFLINE;
        let reassigned = 0;

        for (const topic of this.topics.values()) {
            for (const partition of topic.partitions.values()) {
                if (partition.leaderId !== brokerId) {
                    continue;
                }

                const candidate = partition.replicas.find(
                    replicaId =>
                        this.brokers.get(replicaId)?.state ===
                        BrokerState.ONLINE
                );

                if (candidate !== undefined) {
                    partition.leaderId = candidate;
                    reassigned += 1;
                }
            }
        }

        this.emit('brokerFailed', {
            brokerId,
            reassigned
        });
    }

    recoverBroker(brokerId) {
        const broker = this.brokers.get(brokerId);

        if (!broker) {
            throw new ValidationError(
                `Unknown broker ${brokerId}`
            );
        }

        broker.state = BrokerState.ONLINE;
    }

    describe() {
        console.log('\nCluster state');
        console.log('-------------');

        for (const broker of this.brokers.values()) {
            console.log(
                `broker=${broker.id} host=${broker.host} ` +
                `state=${broker.state}`
            );
        }

        for (const topic of this.topics.values()) {
            console.log(`topic=${topic.name}`);

            for (const partition of topic.partitions.values()) {
                console.log(
                    `  partition=${partition.id} ` +
                    `leader=${partition.leaderId} ` +
                    `replicas=[${partition.replicas.join(',')}] ` +
                    `nextOffset=${partition.nextOffset}`
                );
            }
        }
    }
}

async function main() {
    const cluster = new KafkaCluster();

    cluster.addBroker(1, 'broker-1');
    cluster.addBroker(2, 'broker-2');
    cluster.addBroker(3, 'broker-3');

    cluster.createTopic('payments', 3, 2);

    const messages = [
        ['payment-001', 'AUTHORIZED'],
        ['payment-002', 'AUTHORIZED'],
        ['payment-003', 'DECLINED'],
        ['payment-004', 'CAPTURED'],
        ['payment-005', 'REFUNDED']
    ];

    for (const [key, value] of messages) {
        await cluster.produce('payments', key, value);
    }

    cluster.createGroup('payment-workers');
    cluster.addConsumer('payment-workers', 'consumer-a');
    cluster.addConsumer('payment-workers', 'consumer-b');

    console.log('\nConsumer assignment');
    console.log(
        cluster.rebalance(
            'payment-workers',
            ['payments']
        )
    );

    console.log('\nPolling consumer-a');

    const records = await cluster.poll(
        'payment-workers',
        'consumer-a',
        5
    );

    for (const record of records) {
        console.log(
            `${record.topic}-${record.partition}@${record.offset} ` +
            `${record.key}=${record.value}`
        );

        cluster.commit(
            'payment-workers',
            record.topic,
            record.partition,
            record.offset + 1
        );
    }

    console.log('\nBroker failure');
    cluster.failBroker(1);

    await cluster.produce(
        'payments',
        'payment-after-failure',
        'AUTHORIZED'
    );

    cluster.describe();

    console.log('\nValidation failure');

    try {
        await cluster.produce(
            'missing-topic',
            'x',
            'value'
        );
    } catch (error) {
        console.log(
            `${error.constructor.name}: ${error.message}`
        );
    }

    console.log('\nOffset validation failure');

    try {
        cluster.commit(
            'payment-workers',
            'payments',
            0,
            99999
        );
    } catch (error) {
        console.log(
            `${error.constructor.name}: ${error.message}`
        );
    }
}

main().catch(error => {
    console.error(
        `Fatal error: ${error.constructor.name}: ${error.message}`
    );
    process.exitCode = 1;
});
