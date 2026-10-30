"use strict";

const { EventEmitter } = require("node:events");
const { randomUUID } = require("node:crypto");

const MessageState = Object.freeze({
    READY: "READY",
    IN_FLIGHT: "IN_FLIGHT",
    ACKNOWLEDGED: "ACKNOWLEDGED",
    DEAD_LETTERED: "DEAD_LETTERED"
});

class QueueError extends Error {}
class QueueFullError extends QueueError {}
class InvalidDeliveryError extends QueueError {}
class StaleDeliveryError extends InvalidDeliveryError {}
class QueueClosedError extends QueueError {}

class PointToPointQueue extends EventEmitter {
    constructor({
        name,
        capacity = 1000,
        maxAttempts = 3,
        visibilityTimeoutMs = 30000,
        clock = () => Date.now()
    }) {
        super();

        if (typeof name !== "string" || name.trim() === "") {
            throw new TypeError("Queue name must be a non-empty string.");
        }

        if (!Number.isInteger(capacity) || capacity < 1) {
            throw new RangeError("Capacity must be a positive integer.");
        }

        if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
            throw new RangeError("maxAttempts must be at least one.");
        }

        if (!Number.isFinite(visibilityTimeoutMs) || visibilityTimeoutMs <= 0) {
            throw new RangeError("Visibility timeout must be positive.");
        }

        this.name = name;
        this.capacity = capacity;
        this.maxAttempts = maxAttempts;
        this.visibilityTimeoutMs = visibilityTimeoutMs;
        this.clock = clock;

        this.messages = new Map();
        this.ready = [];
        this.deadLetters = [];
        this.closed = false;
    }

    validatePayload(payload) {
        if (
            payload === null ||
            typeof payload !== "object" ||
            Array.isArray(payload)
        ) {
            throw new TypeError("Payload must be a JSON object.");
        }

        let serialized;

        try {
            serialized = JSON.stringify(payload);
        } catch (error) {
            throw new TypeError(`Invalid JSON payload: ${error.message}`);
        }

        if (serialized === undefined) {
            throw new TypeError("Payload cannot be serialized.");
        }

        if (Buffer.byteLength(serialized, "utf8") > 1024 * 1024) {
            throw new RangeError("Payload exceeds the 1 MiB limit.");
        }

        return JSON.parse(serialized);
    }

    get outstandingCount() {
        let count = 0;

        for (const message of this.messages.values()) {
            if (
                message.state === MessageState.READY ||
                message.state === MessageState.IN_FLIGHT
            ) {
                count += 1;
            }
        }

        return count;
    }

    publish(payload, { id = randomUUID(), deduplicationKey = null } = {}) {
        if (this.closed) {
            throw new QueueClosedError("Queue is closed.");
        }

        if (typeof id !== "string" || id.trim() === "") {
            throw new TypeError("Message identifier cannot be empty.");
        }

        if (this.messages.has(id)) {
            throw new QueueError(`Duplicate message identifier: ${id}`);
        }

        if (this.outstandingCount >= this.capacity) {
            throw new QueueFullError(`Queue ${this.name} is full.`);
        }

        const message = {
            id,
            payload: this.validatePayload(payload),
            deduplicationKey,
            state: MessageState.READY,
            attempts: 0,
            consumerId: null,
            receipt: null,
            leaseDeadline: null,
            lastError: null,
            createdAt: this.clock()
        };

        this.messages.set(id, message);
        this.ready.push(id);

        this.emit("published", {
            queue: this.name,
            messageId: id
        });

        return id;
    }

    recoverExpiredDeliveries(now = this.clock()) {
        for (const message of this.messages.values()) {
            if (
                message.state !== MessageState.IN_FLIGHT ||
                message.leaseDeadline > now
            ) {
                continue;
            }

            message.consumerId = null;
            message.receipt = null;
            message.leaseDeadline = null;
            message.lastError = "Visibility timeout expired.";

            if (message.attempts >= this.maxAttempts) {
                message.state = MessageState.DEAD_LETTERED;
                this.deadLetters.push(message.id);

                this.emit("dead-lettered", {
                    queue: this.name,
                    messageId: message.id,
                    reason: message.lastError
                });
            } else {
                message.state = MessageState.READY;
                this.ready.push(message.id);

                this.emit("requeued", {
                    queue: this.name,
                    messageId: message.id,
                    reason: message.lastError
                });
            }
        }
    }

    receive(consumerId) {
        if (typeof consumerId !== "string" || consumerId.trim() === "") {
            throw new TypeError("Consumer identifier cannot be empty.");
        }

        this.recoverExpiredDeliveries();

        while (this.ready.length > 0) {
            const id = this.ready.shift();
            const message = this.messages.get(id);

            if (!message || message.state !== MessageState.READY) {
                continue;
            }

            message.state = MessageState.IN_FLIGHT;
            message.attempts += 1;
            message.consumerId = consumerId;
            message.receipt = randomUUID();
            message.leaseDeadline =
                this.clock() + this.visibilityTimeoutMs;

            const delivery = Object.freeze({
                messageId: message.id,
                payload: structuredClone(message.payload),
                consumerId,
                receipt: message.receipt,
                attempt: message.attempts,
                leaseDeadline: message.leaseDeadline
            });

            this.emit("delivered", {
                queue: this.name,
                messageId: message.id,
                consumerId,
                attempt: message.attempts
            });

            return delivery;
        }

        return null;
    }

    getActiveMessage(delivery) {
        if (!delivery || typeof delivery !== "object") {
            throw new InvalidDeliveryError("A delivery object is required.");
        }

        const message = this.messages.get(delivery.messageId);

        if (!message) {
            throw new InvalidDeliveryError("Unknown message.");
        }

        if (message.state === MessageState.ACKNOWLEDGED) {
            throw new InvalidDeliveryError("Message is already acknowledged.");
        }

        if (message.state !== MessageState.IN_FLIGHT) {
            throw new StaleDeliveryError("Message is not in flight.");
        }

        if (
            message.receipt !== delivery.receipt ||
            message.consumerId !== delivery.consumerId
        ) {
            throw new StaleDeliveryError(
                "Receipt does not identify the active delivery."
            );
        }

        if (this.clock() >= message.leaseDeadline) {
            this.recoverExpiredDeliveries();
            throw new StaleDeliveryError("Delivery lease has expired.");
        }

        return message;
    }

    acknowledge(delivery) {
        const message = this.getActiveMessage(delivery);

        message.state = MessageState.ACKNOWLEDGED;
        message.consumerId = null;
        message.receipt = null;
        message.leaseDeadline = null;

        this.emit("acknowledged", {
            queue: this.name,
            messageId: message.id,
            consumerId: delivery.consumerId
        });

        return true;
    }

    reject(delivery, {
        requeue = true,
        reason = "Consumer rejected the message."
    } = {}) {
        const message = this.getActiveMessage(delivery);

        message.consumerId = null;
        message.receipt = null;
        message.leaseDeadline = null;
        message.lastError = String(reason);

        if (requeue && message.attempts < this.maxAttempts) {
            message.state = MessageState.READY;
            this.ready.push(message.id);

            this.emit("requeued", {
                queue: this.name,
                messageId: message.id,
                reason: message.lastError
            });
        } else {
            message.state = MessageState.DEAD_LETTERED;
            this.deadLetters.push(message.id);

            this.emit("dead-lettered", {
                queue: this.name,
                messageId: message.id,
                reason: message.lastError
            });
        }

        return message.state;
    }

    statistics() {
        const result = {
            ready: 0,
            inFlight: 0,
            acknowledged: 0,
            deadLettered: 0
        };

        for (const message of this.messages.values()) {
            switch (message.state) {
                case MessageState.READY:
                    result.ready += 1;
                    break;
                case MessageState.IN_FLIGHT:
                    result.inFlight += 1;
                    break;
                case MessageState.ACKNOWLEDGED:
                    result.acknowledged += 1;
                    break;
                case MessageState.DEAD_LETTERED:
                    result.deadLettered += 1;
                    break;
                default:
                    throw new QueueError("Unexpected message state.");
            }
        }

        return Object.freeze(result);
    }

    getDeadLetterMessages() {
        return this.deadLetters.map(id => {
            const message = this.messages.get(id);

            return {
                messageId: id,
                payload: structuredClone(message.payload),
                attempts: message.attempts,
                lastError: message.lastError
            };
        });
    }

    close() {
        this.closed = true;
        this.emit("closed", { queue: this.name });
    }
}

class IdempotencyRegistry {
    constructor() {
        this.completed = new Set();
    }

    has(messageId) {
        return this.completed.has(messageId);
    }

    record(messageId) {
        this.completed.add(messageId);
    }
}

class CompetingConsumer {
    constructor(queue, consumerId, handler, registry) {
        if (!(queue instanceof PointToPointQueue)) {
            throw new TypeError("A PointToPointQueue is required.");
        }

        if (typeof handler !== "function") {
            throw new TypeError("Handler must be a function.");
        }

        this.queue = queue;
        this.consumerId = consumerId;
        this.handler = handler;
        this.registry = registry;
    }

    async run({ maxDeliveries = 100 } = {}) {
        let handled = 0;

        while (handled < maxDeliveries) {
            const delivery = this.queue.receive(this.consumerId);

            if (!delivery) {
                break;
            }

            handled += 1;

            try {
                if (!this.registry.has(delivery.messageId)) {
                    await this.handler(delivery.payload, delivery);
                    this.registry.record(delivery.messageId);
                }

                this.queue.acknowledge(delivery);
            } catch (error) {
                this.queue.reject(delivery, {
                    requeue: true,
                    reason: error.message
                });
            }
        }

        return handled;
    }
}

function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function runDemonstration() {
    const queue = new PointToPointQueue({
        name: "payment-events",
        capacity: 20,
        maxAttempts: 3,
        visibilityTimeoutMs: 5000
    });

    const registry = new IdempotencyRegistry();

    const eventLog = [
        "published",
        "delivered",
        "acknowledged",
        "requeued",
        "dead-lettered"
    ];

    for (const eventName of eventLog) {
        queue.on(eventName, event => {
            console.log(`[${eventName}]`, event);
        });
    }

    queue.publish(
        { paymentId: "PAY-101", amount: 4200 },
        { id: "payment-1" }
    );

    queue.publish(
        { paymentId: "PAY-102", amount: 1700 },
        { id: "payment-2" }
    );

    queue.publish(
        { paymentId: "PAY-103", amount: 8300 },
        { id: "payment-3" }
    );

    queue.publish(
        { paymentId: "PAY-104", amount: 2500 },
        { id: "payment-4" }
    );

    queue.publish(
        { paymentId: "PAY-105", amount: 9900, invalid: true },
        { id: "poison-payment" }
    );

    const handler = async (payload, delivery) => {
        // Yield control so independent consumers can process concurrently.
        await delay(payload.amount % 7 + 5);

        if (payload.invalid) {
            throw new Error("Payment validation rejected the event.");
        }

        console.log(
            `${delivery.consumerId} completed ${payload.paymentId}`
        );
    };

    const consumers = [
        new CompetingConsumer(queue, "worker-A", handler, registry),
        new CompetingConsumer(queue, "worker-B", handler, registry),
        new CompetingConsumer(queue, "worker-C", handler, registry)
    ];

    // Each worker pulls from the same queue. A message is assigned to
    // one worker at a time, not broadcast to every worker.
    await Promise.all(
        consumers.map(consumer =>
            consumer.run({ maxDeliveries: 20 })
        )
    );

    console.log("\nFinal statistics");
    console.log(queue.statistics());

    console.log("\nDead-letter messages");
    console.log(queue.getDeadLetterMessages());

    queue.close();
}

async function runAssertions() {
    let currentTime = 1000;

    const queue = new PointToPointQueue({
        name: "lease-test",
        capacity: 1,
        maxAttempts: 2,
        visibilityTimeoutMs: 100,
        clock: () => currentTime
    });

    queue.publish({ job: "reconcile" }, { id: "job-1" });

    try {
        queue.publish({ job: "overflow" }, { id: "job-2" });
        throw new Error("Capacity validation failed.");
    } catch (error) {
        if (!(error instanceof QueueFullError)) {
            throw error;
        }
    }

    const first = queue.receive("worker-1");

    if (!first || first.attempt !== 1) {
        throw new Error("First delivery failed.");
    }

    currentTime += 150;

    const second = queue.receive("worker-2");

    if (!second || second.attempt !== 2) {
        throw new Error("Visibility-timeout recovery failed.");
    }

    try {
        queue.acknowledge(first);
        throw new Error("A stale receipt was accepted.");
    } catch (error) {
        if (!(error instanceof StaleDeliveryError)) {
            throw error;
        }
    }

    queue.reject(second, {
        requeue: true,
        reason: "Second attempt failed."
    });

    if (queue.statistics().deadLettered !== 1) {
        throw new Error("Dead-letter transition failed.");
    }
}

if (require.main === module) {
    runAssertions()
        .then(runDemonstration)
        .catch(error => {
            console.error("Queue demonstration failed:", error);
            process.exitCode = 1;
        });
}

module.exports = {
    PointToPointQueue,
    CompetingConsumer,
    IdempotencyRegistry,
    MessageState,
    QueueError,
    QueueFullError,
    InvalidDeliveryError,
    StaleDeliveryError
};
