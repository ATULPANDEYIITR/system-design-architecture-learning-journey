'use strict';

/*
 * Distributed time is represented here using three different mechanisms:
 *
 * Physical timestamps:
 *   Useful for human-readable event time, observability, retention, and audit.
 *
 * Lamport timestamps:
 *   Useful for causal ordering without requiring synchronized wall clocks.
 *
 * Vector timestamps:
 *   Useful when the system must distinguish causal ordering from concurrency.
 *
 * This program uses Node.js standard APIs only.
 */

const fs = require('node:fs');

class LamportClock {
    constructor(nodeId) {
        this.nodeId = nodeId;
        this.value = 0;
    }

    local() {
        this.value += 1;
        return this.value;
    }

    send() {
        this.value += 1;
        return this.value;
    }

    receive(remoteTimestamp) {
        if (!Number.isInteger(remoteTimestamp) || remoteTimestamp < 0) {
            throw new TypeError('A Lamport timestamp must be a non-negative integer');
        }

        this.value = Math.max(this.value, remoteTimestamp) + 1;
        return this.value;
    }
}

class VectorClock {
    constructor(nodeId, nodeIds) {
        if (!nodeIds.includes(nodeId)) {
            throw new Error(`Node ${nodeId} is absent from the vector dimension`);
        }

        this.nodeId = nodeId;
        this.clock = Object.fromEntries(
            [...new Set(nodeIds)].sort().map((id) => [id, 0])
        );
    }

    local() {
        this.clock[this.nodeId] += 1;
        return this.snapshot();
    }

    send() {
        return this.local();
    }

    receive(remoteClock) {
        const localNodes = Object.keys(this.clock).sort();
        const remoteNodes = Object.keys(remoteClock).sort();

        if (JSON.stringify(localNodes) !== JSON.stringify(remoteNodes)) {
            throw new Error('Vector clocks must have identical dimensions');
        }

        for (const node of localNodes) {
            if (!Number.isInteger(remoteClock[node]) || remoteClock[node] < 0) {
                throw new TypeError(`Invalid vector value for ${node}`);
            }

            this.clock[node] = Math.max(this.clock[node], remoteClock[node]);
        }

        this.clock[this.nodeId] += 1;
        return this.snapshot();
    }

    snapshot() {
        return { ...this.clock };
    }
}

function compareVectors(left, right) {
    const leftNodes = Object.keys(left).sort();
    const rightNodes = Object.keys(right).sort();

    if (JSON.stringify(leftNodes) !== JSON.stringify(rightNodes)) {
        throw new Error('Cannot compare vector clocks with different dimensions');
    }

    let leftLessOrEqual = true;
    let rightLessOrEqual = true;
    let leftStrictlyLess = false;
    let rightStrictlyLess = false;

    for (const node of leftNodes) {
        if (left[node] > right[node]) {
            leftLessOrEqual = false;
            rightStrictlyLess = true;
        }

        if (right[node] > left[node]) {
            rightLessOrEqual = false;
            leftStrictlyLess = true;
        }
    }

    if (leftLessOrEqual && rightLessOrEqual) {
        return 'EQUAL';
    }

    if (leftLessOrEqual && leftStrictlyLess) {
        return 'BEFORE';
    }

    if (rightLessOrEqual && rightStrictlyLess) {
        return 'AFTER';
    }

    return 'CONCURRENT';
}

class DistributedEvent {
    constructor({
        id,
        nodeId,
        type,
        wallClock,
        lamport,
        vector,
        payload = {}
    }) {
        if (!id || !nodeId || !type) {
            throw new Error('An event requires an id, nodeId, and type');
        }

        if (!(wallClock instanceof Date) || Number.isNaN(wallClock.getTime())) {
            throw new Error('Event wallClock must be a valid Date');
        }

        this.id = id;
        this.nodeId = nodeId;
        this.type = type;
        this.wallClock = wallClock;
        this.lamport = lamport;
        this.vector = { ...vector };
        this.payload = { ...payload };
    }

    toJSON() {
        return {
            id: this.id,
            nodeId: this.nodeId,
            type: this.type,
            wallClock: this.wallClock.toISOString(),
            lamport: this.lamport,
            vector: this.vector,
            payload: this.payload
        };
    }
}

class ServiceNode {
    constructor(nodeId, clockOffsetMs, driftPpm, nodeIds) {
        this.nodeId = nodeId;
        this.clockOffsetMs = clockOffsetMs;
        this.driftPpm = driftPpm;
        this.lamport = new LamportClock(nodeId);
        this.vector = new VectorClock(nodeId, nodeIds);
        this.events = [];
    }

    wallClock(referenceMs) {
        // Drift is modeled as a fractional rate error over Unix elapsed time.
        const driftMs = referenceMs * this.driftPpm / 1_000_000;
        return new Date(referenceMs + this.clockOffsetMs + driftMs);
    }

    localEvent(id, type, referenceMs, payload = {}) {
        const event = new DistributedEvent({
            id,
            nodeId: this.nodeId,
            type,
            wallClock: this.wallClock(referenceMs),
            lamport: this.lamport.local(),
            vector: this.vector.local(),
            payload
        });

        this.events.push(event);
        return event;
    }

    send(id, destination, referenceMs, payload = {}) {
        const event = new DistributedEvent({
            id,
            nodeId: this.nodeId,
            type: `SEND->${destination}`,
            wallClock: this.wallClock(referenceMs),
            lamport: this.lamport.send(),
            vector: this.vector.send(),
            payload
        });

        this.events.push(event);
        return event;
    }

    receive(id, senderEvent, referenceMs, payload = {}) {
        const event = new DistributedEvent({
            id,
            nodeId: this.nodeId,
            type: `RECEIVE<-${senderEvent.nodeId}`,
            wallClock: this.wallClock(referenceMs),
            lamport: this.lamport.receive(senderEvent.lamport),
            vector: this.vector.receive(senderEvent.vector),
            payload
        });

        this.events.push(event);
        return event;
    }
}

class EventBus {
    constructor() {
        this.handlers = new Map();
    }

    subscribe(eventType, handler) {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, []);
        }

        this.handlers.get(eventType).push(handler);
    }

    publish(event) {
        const handlers = this.handlers.get(event.type) ?? [];

        for (const handler of handlers) {
            handler(event);
        }
    }
}

function demonstratePhysicalClockSkew() {
    console.log('\n=== Physical Clock Skew ===');

    const reference = Date.UTC(2026, 9, 16, 5, 30, 0);

    const nodes = [
        new ServiceNode('orders', 120, 8, ['orders', 'inventory', 'payments']),
        new ServiceNode('inventory', -75, -12, ['orders', 'inventory', 'payments']),
        new ServiceNode('payments', 45, 18, ['orders', 'inventory', 'payments'])
    ];

    for (const node of nodes) {
        console.log(
            node.nodeId,
            node.wallClock(reference).toISOString(),
            `offset=${node.clockOffsetMs}ms`,
            `drift=${node.driftPpm}ppm`
        );
    }

    const timestamps = nodes.map((node) => node.wallClock(reference).getTime());
    console.log(`Observed spread: ${Math.max(...timestamps) - Math.min(...timestamps)}ms`);
}

function demonstrateEventDrivenProcessing() {
    console.log('\n=== Event-Driven Distributed Workflow ===');

    const nodes = ['orders', 'inventory', 'payments'];
    const orders = new ServiceNode('orders', 35, 10, nodes);
    const inventory = new ServiceNode('inventory', -25, -4, nodes);
    const payments = new ServiceNode('payments', 60, 15, nodes);

    const base = Date.UTC(2026, 9, 16, 5, 30, 10);
    const bus = new EventBus();

    bus.subscribe('PAYMENT_AUTHORIZED', (event) => {
        console.log(
            `payment handler observed ${event.id} with Lamport=${event.lamport}`
        );
    });

    const order = orders.localEvent(
        'evt-001',
        'ORDER_CREATED',
        base,
        { orderId: 'ORD-1001' }
    );

    const inventoryMessage = orders.send(
        'evt-002',
        'inventory',
        base + 4,
        { sku: 'SKU-9', quantity: 1 }
    );

    const inventoryReceived = inventory.receive(
        'evt-003',
        inventoryMessage,
        base + 8,
        { accepted: true }
    );

    const paymentMessage = orders.send(
        'evt-004',
        'payments',
        base + 10,
        { amount: 125.00, currency: 'USD' }
    );

    const paymentReceived = payments.receive(
        'evt-005',
        paymentMessage,
        base + 15,
        { accepted: true }
    );

    const paymentAuthorized = payments.localEvent(
        'evt-006',
        'PAYMENT_AUTHORIZED',
        base + 20,
        { authorizationId: 'AUTH-77' }
    );

    bus.publish(paymentAuthorized);

    const inventoryReserved = inventory.localEvent(
        'evt-007',
        'INVENTORY_RESERVED',
        base + 25,
        { sku: 'SKU-9' }
    );

    const events = [
        order,
        inventoryMessage,
        inventoryReceived,
        paymentMessage,
        paymentReceived,
        paymentAuthorized,
        inventoryReserved
    ];

    for (const event of events) {
        console.log(
            `${event.id} ${event.nodeId} ${event.type} ` +
            `wall=${event.wallClock.toISOString()} ` +
            `L=${event.lamport} V=${JSON.stringify(event.vector)}`
        );
    }

    console.log(
        'evt-002 -> evt-003:',
        compareVectors(inventoryMessage.vector, inventoryReceived.vector)
    );

    console.log(
        'evt-006 vs evt-007:',
        compareVectors(paymentAuthorized.vector, inventoryReserved.vector)
    );

    return events;
}

function estimateOffset(nodeSamples, referenceSamples) {
    if (
        !Array.isArray(nodeSamples) ||
        !Array.isArray(referenceSamples) ||
        nodeSamples.length !== referenceSamples.length ||
        nodeSamples.length === 0
    ) {
        throw new Error('Synchronization samples must be equal-length non-empty arrays');
    }

    const offsets = nodeSamples.map((sample, index) => sample - referenceSamples[index]);
    const mean = offsets.reduce((sum, value) => sum + value, 0) / offsets.length;

    const sorted = [...offsets].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 === 0
        ? (sorted[middle - 1] + sorted[middle]) / 2
        : sorted[middle];

    return {
        offsets,
        mean,
        median,
        minimum: Math.min(...offsets),
        maximum: Math.max(...offsets)
    };
}

function demonstrateSynchronization() {
    console.log('\n=== Clock Offset Estimation ===');

    const reference = [100000, 101000, 102000, 103000];
    const node = [100075, 101082, 102077, 103080];

    const result = estimateOffset(node, reference);

    console.log(`mean offset: ${result.mean.toFixed(2)}ms`);
    console.log(`median offset: ${result.median.toFixed(2)}ms`);
    console.log(`range: ${result.minimum}ms to ${result.maximum}ms`);
}

function demonstrateFailureHandling() {
    console.log('\n=== Validation and Failure Handling ===');

    try {
        new LamportClock('a').receive(-3);
    } catch (error) {
        console.log('Rejected invalid Lamport value:', error.message);
    }

    try {
        compareVectors({ a: 1 }, { a: 1, b: 2 });
    } catch (error) {
        console.log('Rejected incompatible vectors:', error.message);
    }

    try {
        new VectorClock('a', ['b']);
    } catch (error) {
        console.log('Rejected missing vector dimension:', error.message);
    }
}

function persistEvents(events) {
    const serialized = JSON.stringify(
        events.map((event) => event.toJSON()),
        null,
        2
    );

    fs.writeFileSync('distributed-events.json', serialized, 'utf8');
    console.log(`Persisted ${events.length} events to distributed-events.json`);
}

function main() {
    demonstratePhysicalClockSkew();
    const events = demonstrateEventDrivenProcessing();
    demonstrateSynchronization();
    demonstrateFailureHandling();
    persistEvents(events);

    console.log('\n=== Operational Model ===');
    console.log(
        'Wall-clock timestamps answer approximately when an event occurred according to a clock.'
    );
    console.log(
        'Lamport timestamps answer whether a causal ordering can be established without wall-clock synchronization.'
    );
    console.log(
        'Vector clocks additionally identify concurrent events when neither event causally precedes the other.'
    );
    console.log(
        'Clock synchronization improves timestamp usefulness but cannot make physical timestamps equivalent to causal clocks.'
    );
}

main();
