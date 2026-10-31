'use strict';

/*
 * Event-driven Pub/Sub broker.
 *
 * This implementation uses Node.js EventEmitter-style behavior without
 * depending on external packages. Topic routing is represented by Maps,
 * while asynchronous subscribers return Promises so slow consumers do not
 * block the publication loop.
 */

const { randomUUID } = require('crypto');
const { EventEmitter } = require('events');

class PubSubError extends Error {}
class ValidationError extends PubSubError {}
class SubscriptionError extends PubSubError {}

class PubSubBroker extends EventEmitter {
    constructor({ historyLimit = 1000, maxConcurrentDeliveries = 32 } = {}) {
        super();

        if (!Number.isInteger(historyLimit) || historyLimit < 1) {
            throw new ValidationError('historyLimit must be a positive integer');
        }

        if (!Number.isInteger(maxConcurrentDeliveries) ||
            maxConcurrentDeliveries < 1) {
            throw new ValidationError(
                'maxConcurrentDeliveries must be a positive integer'
            );
        }

        this.historyLimit = historyLimit;
        this.maxConcurrentDeliveries = maxConcurrentDeliveries;
        this.topics = new Map();
        this.history = [];
    }

    static validateTopic(topic) {
        if (typeof topic !== 'string' || topic.length === 0) {
            throw new ValidationError('Topic must be a non-empty string');
        }

        if (topic.length > 128) {
            throw new ValidationError('Topic cannot exceed 128 characters');
        }

        if (/\s/.test(topic)) {
            throw new ValidationError('Topic cannot contain whitespace');
        }
    }

    subscribe(topic, subscriberId, handler, {
        maxFailures = 3,
        metadata = {}
    } = {}) {
        PubSubBroker.validateTopic(topic);

        if (typeof subscriberId !== 'string' || subscriberId.trim() === '') {
            throw new ValidationError('subscriberId must be non-empty');
        }

        if (typeof handler !== 'function') {
            throw new ValidationError('handler must be a function');
        }

        if (!Number.isInteger(maxFailures) || maxFailures < 1) {
            throw new ValidationError('maxFailures must be positive');
        }

        if (!this.topics.has(topic)) {
            this.topics.set(topic, new Map());
        }

        const subscribers = this.topics.get(topic);

        if (subscribers.has(subscriberId)) {
            throw new SubscriptionError(
                `Subscriber '${subscriberId}' already exists`
            );
        }

        subscribers.set(subscriberId, {
            id: subscriberId,
            handler,
            maxFailures,
            failures: 0,
            active: true,
            metadata: { ...metadata }
        });

        this.emit('subscribed', { topic, subscriberId });
    }

    unsubscribe(topic, subscriberId) {
        PubSubBroker.validateTopic(topic);

        const subscribers = this.topics.get(topic);
        if (!subscribers || !subscribers.has(subscriberId)) {
            return false;
        }

        subscribers.delete(subscriberId);

        if (subscribers.size === 0) {
            this.topics.delete(topic);
        }

        this.emit('unsubscribed', { topic, subscriberId });
        return true;
    }

    async publish(topic, payload) {
        PubSubBroker.validateTopic(topic);

        if (
            payload === null ||
            typeof payload !== 'object' ||
            Array.isArray(payload)
        ) {
            throw new ValidationError('Payload must be a plain object');
        }

        const event = Object.freeze({
            id: randomUUID(),
            topic,
            payload: structuredClone(payload),
            createdAt: new Date().toISOString()
        });

        this.history.push(event);
        if (this.history.length > this.historyLimit) {
            this.history.shift();
        }

        const subscribers = [
            ...(this.topics.get(topic)?.values() ?? [])
        ];

        /*
         * Promise.allSettled gives each consumer an isolated failure path.
         * A broken subscriber therefore does not cancel delivery to others.
         */
        const results = await this.#deliverWithConcurrency(
            event,
            subscribers
        );

        this.emit('published', {
            eventId: event.id,
            topic,
            deliveryCount: results.length
        });

        return results;
    }

    async #deliverWithConcurrency(event, subscribers) {
        const results = new Array(subscribers.length);
        let cursor = 0;

        const worker = async () => {
            while (true) {
                const index = cursor++;
                if (index >= subscribers.length) {
                    return;
                }

                const subscriber = subscribers[index];

                if (!subscriber.active) {
                    results[index] = {
                        subscriberId: subscriber.id,
                        status: 'skipped'
                    };
                    continue;
                }

                try {
                    await subscriber.handler(event);
                    subscriber.failures = 0;

                    results[index] = {
                        subscriberId: subscriber.id,
                        status: 'delivered'
                    };
                } catch (error) {
                    subscriber.failures += 1;

                    if (subscriber.failures >= subscriber.maxFailures) {
                        subscriber.active = false;
                    }

                    results[index] = {
                        subscriberId: subscriber.id,
                        status: 'failed',
                        error: error instanceof Error
                            ? error.message
                            : String(error)
                    };
                }
            }
        };

        const workerCount = Math.min(
            this.maxConcurrentDeliveries,
            Math.max(1, subscribers.length)
        );

        await Promise.all(
            Array.from({ length: workerCount }, () => worker())
        );

        return results;
    }

    replay(topic, subscriberId) {
        PubSubBroker.validateTopic(topic);

        const subscriber = this.topics.get(topic)?.get(subscriberId);

        if (!subscriber) {
            throw new SubscriptionError(
                `Subscriber '${subscriberId}' is not subscribed`
            );
        }

        return this.history
            .filter(event => event.topic === topic)
            .map(event => subscriber.handler(event));
    }

    statistics() {
        const output = {};

        for (const [topic, subscribers] of this.topics) {
            output[topic] = {
                subscribers: subscribers.size,
                active: [...subscribers.values()]
                    .filter(subscriber => subscriber.active)
                    .length
            };
        }

        return output;
    }
}

async function main() {
    const broker = new PubSubBroker({
        historyLimit: 50,
        maxConcurrentDeliveries: 8
    });

    broker.on('subscribed', event => {
        console.log(`[BROKER] subscribed: ${event.subscriberId}`);
    });

    broker.on('published', event => {
        console.log(
            `[BROKER] published ${event.eventId} to ${event.deliveryCount} consumers`
        );
    });

    broker.subscribe(
        'orders.created',
        'audit-service',
        async event => {
            console.log(
                `[AUDIT] ${event.payload.orderId} ${event.payload.total}`
            );
        }
    );

    broker.subscribe(
        'orders.created',
        'inventory-service',
        async event => {
            if (event.payload.items.length === 0) {
                throw new Error('Order contains no items');
            }

            console.log(
                `[INVENTORY] reserving ${event.payload.items.length} item(s)`
            );
        }
    );

    broker.subscribe(
        'orders.created',
        'notification-service',
        async event => {
            await new Promise(resolve => setTimeout(resolve, 20));
            console.log(
                `[NOTIFY] customer=${event.payload.customerId}`
            );
        }
    );

    const results = await broker.publish('orders.created', {
        orderId: 'ORD-1001',
        customerId: 'CUS-204',
        items: [
            { sku: 'SKU-10', quantity: 2 },
            { sku: 'SKU-11', quantity: 1 }
        ],
        total: 1850
    });

    console.log('\nDelivery results:');
    console.table(results);

    console.log('\nBroker statistics:');
    console.log(JSON.stringify(broker.statistics(), null, 2));

    const replay = broker.replay('orders.created', 'audit-service');
    await Promise.all(replay);

    broker.unsubscribe('orders.created', 'notification-service');

    try {
        await broker.publish('orders created', { orderId: 'BAD' });
    } catch (error) {
        console.log(`\nValidation error: ${error.message}`);
    }
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
