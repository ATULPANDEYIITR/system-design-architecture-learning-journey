"use strict";

/*
 * Distributed Systems Fundamentals
 *
 * This Node.js program focuses on event-driven distributed behavior:
 * message delivery, asynchronous delays, retries, failure detection,
 * leader election, replicated state, quorum evaluation, and distributed
 * tracing. It deliberately models the network instead of requiring external
 * services so the file can execute without npm dependencies.
 */

const crypto = require("crypto");

function section(title) {
    console.log(`\n${"=".repeat(76)}\n${title}\n${"=".repeat(76)}`);
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function stableHash(value) {
    return crypto.createHash("sha256").update(value).digest("hex");
}


// ---------------------------------------------------------------------------
// Asynchronous message bus
// ---------------------------------------------------------------------------

class MessageBus {
    constructor() {
        this.handlers = new Map();
        this.blockedLinks = new Set();
        this.sequence = 0;
    }

    register(nodeId, handler) {
        this.handlers.set(nodeId, handler);
    }

    block(left, right) {
        this.blockedLinks.add(`${left}->${right}`);
    }

    unblock(left, right) {
        this.blockedLinks.delete(`${left}->${right}`);
    }

    async send(sender, receiver, type, payload, delayMs = 5) {
        if (this.blockedLinks.has(`${sender}->${receiver}`)) {
            throw new Error(`Network path ${sender}->${receiver} is unavailable`);
        }

        const handler = this.handlers.get(receiver);
        if (!handler) {
            throw new Error(`Receiver ${receiver} is not registered`);
        }

        this.sequence += 1;

        await sleep(delayMs);

        return handler({
            id: `${sender}-${this.sequence}`,
            sender,
            receiver,
            type,
            payload,
            deliveredAt: Date.now()
        });
    }
}


// ---------------------------------------------------------------------------
// Event-driven distributed nodes
// ---------------------------------------------------------------------------

class DistributedNode {
    constructor(id, bus) {
        this.id = id;
        this.bus = bus;
        this.online = true;
        this.clock = 0;

        bus.register(id, message => this.receive(message));
    }

    tick() {
        this.clock += 1;
        return this.clock;
    }

    async send(receiver, type, payload) {
        if (!this.online) {
            throw new Error(`${this.id} is offline`);
        }

        const timestamp = this.tick();

        return this.bus.send(
            this.id,
            receiver,
            type,
            {
                ...payload,
                logicalClock: timestamp
            }
        );
    }

    receive(message) {
        if (!this.online) {
            throw new Error(`${this.id} is offline`);
        }

        this.clock = Math.max(
            this.clock,
            Number(message.payload.logicalClock || 0)
        ) + 1;

        return {
            accepted: true,
            receiverClock: this.clock,
            messageId: message.id
        };
    }
}

async function demonstrateAsyncMessaging() {
    section("Asynchronous Message Delivery");

    const bus = new MessageBus();
    const api = new DistributedNode("api", bus);
    const inventory = new DistributedNode("inventory", bus);

    const result = await api.send(
        "inventory",
        "RESERVE",
        {
            orderId: "ORD-204",
            sku: "SERVER-RACK-42U",
            quantity: 3
        }
    );

    console.log("Delivery result:", result);
    console.log("API logical clock:", api.clock);
    console.log("Inventory logical clock:", inventory.clock);
}


// ---------------------------------------------------------------------------
// Event-driven retry with exponential backoff
// ---------------------------------------------------------------------------

async function retry(operation, options = {}) {
    const {
        attempts = 4,
        baseDelayMs = 10,
        shouldRetry = () => true
    } = options;

    let lastError;

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
        try {
            return await operation(attempt);
        } catch (error) {
            lastError = error;

            if (attempt === attempts || !shouldRetry(error)) {
                break;
            }

            const delay = baseDelayMs * 2 ** (attempt - 1);
            await sleep(delay);
        }
    }

    throw lastError;
}

async function demonstrateRetry() {
    section("Retries and Backoff");

    let failures = 0;

    const result = await retry(
        async attempt => {
            failures += 1;

            if (attempt < 3) {
                throw new Error("Temporary network failure");
            }

            return "operation completed";
        },
        {
            attempts: 4,
            baseDelayMs: 5
        }
    );

    console.log("Result:", result);
    console.log("Attempts used:", failures);
}


// ---------------------------------------------------------------------------
// Idempotency keys
// ---------------------------------------------------------------------------

class IdempotentCommandProcessor {
    constructor() {
        this.completed = new Map();
        this.balance = 5000;
    }

    execute(command) {
        const { idempotencyKey, amount } = command;

        if (!idempotencyKey || typeof idempotencyKey !== "string") {
            throw new Error("A valid idempotency key is required");
        }

        if (!Number.isFinite(amount) || amount <= 0) {
            throw new Error("Amount must be a positive finite number");
        }

        if (this.completed.has(idempotencyKey)) {
            return {
                replayed: true,
                result: this.completed.get(idempotencyKey)
            };
        }

        if (amount > this.balance) {
            throw new Error("Insufficient balance");
        }

        this.balance -= amount;

        const result = {
            transactionId: `txn-${this.completed.size + 1}`,
            amount,
            remainingBalance: this.balance
        };

        this.completed.set(idempotencyKey, result);

        return {
            replayed: false,
            result
        };
    }
}

function demonstrateIdempotency() {
    section("Idempotent Command Processing");

    const processor = new IdempotentCommandProcessor();

    const first = processor.execute({
        idempotencyKey: "checkout-001",
        amount: 1200
    });

    const retryResult = processor.execute({
        idempotencyKey: "checkout-001",
        amount: 1200
    });

    console.log("First command:", first);
    console.log("Retry:", retryResult);
}


// ---------------------------------------------------------------------------
// Replicated state and quorum evaluation
// ---------------------------------------------------------------------------

class ReplicaNode {
    constructor(id) {
        this.id = id;
        this.online = true;
        this.version = 0;
        this.data = new Map();
    }

    write(key, value, version) {
        if (!this.online) {
            throw new Error(`${this.id} unavailable`);
        }

        const current = this.data.get(key);

        if (!current || version >= current.version) {
            this.data.set(key, { value, version });
            this.version = Math.max(this.version, version);
        }
    }

    read(key) {
        if (!this.online) {
            throw new Error(`${this.id} unavailable`);
        }

        return this.data.get(key) || null;
    }
}

class QuorumReplicatedStore {
    constructor(ids) {
        if (!Array.isArray(ids) || ids.length === 0) {
            throw new Error("At least one replica is required");
        }

        this.replicas = ids.map(id => new ReplicaNode(id));
        this.version = 0;
    }

    get quorum() {
        return Math.floor(this.replicas.length / 2) + 1;
    }

    setAvailability(id, online) {
        const replica = this.replicas.find(item => item.id === id);

        if (!replica) {
            throw new Error(`Unknown replica: ${id}`);
        }

        replica.online = online;
    }

    write(key, value) {
        this.version += 1;
        let acknowledgements = 0;

        for (const replica of this.replicas) {
            if (!replica.online) {
                continue;
            }

            replica.write(key, value, this.version);
            acknowledgements += 1;
        }

        if (acknowledgements < this.quorum) {
            throw new Error(
                `Write quorum unavailable: ${acknowledgements}/${this.quorum}`
            );
        }

        return {
            key,
            version: this.version,
            acknowledgements
        };
    }

    read(key) {
        const responses = [];

        for (const replica of this.replicas) {
            if (!replica.online) {
                continue;
            }

            const result = replica.read(key);

            if (result) {
                responses.push(result);
            }
        }

        if (responses.length < this.quorum) {
            throw new Error(
                `Read quorum unavailable: ${responses.length}/${this.quorum}`
            );
        }

        return responses.reduce(
            (latest, current) =>
                current.version > latest.version ? current : latest
        );
    }
}

function demonstrateQuorumStore() {
    section("Replication and Quorums");

    const store = new QuorumReplicatedStore(["r1", "r2", "r3"]);

    console.log(
        "Write:",
        store.write("service:inventory", { available: 48 })
    );

    console.log("Read:", store.read("service:inventory"));

    store.setAvailability("r3", false);
    console.log("Read with one replica down:", store.read("service:inventory"));

    store.setAvailability("r2", false);

    try {
        store.write("service:inventory", { available: 47 });
    } catch (error) {
        console.log("Expected failure:", error.message);
    }
}


// ---------------------------------------------------------------------------
// Leader election and failure detection
// ---------------------------------------------------------------------------

class ElectionCluster {
    constructor(nodeIds) {
        this.nodes = new Map(nodeIds.map(id => [id, true]));
        this.leader = null;
    }

    fail(id) {
        if (!this.nodes.has(id)) {
            throw new Error(`Unknown node ${id}`);
        }

        this.nodes.set(id, false);

        if (this.leader === id) {
            this.leader = null;
        }
    }

    recover(id) {
        if (!this.nodes.has(id)) {
            throw new Error(`Unknown node ${id}`);
        }

        this.nodes.set(id, true);
    }

    elect() {
        const liveNodes = [...this.nodes.entries()]
            .filter(([, online]) => online)
            .map(([id]) => id)
            .sort();

        if (liveNodes.length === 0) {
            throw new Error("No live node can become leader");
        }

        this.leader = liveNodes[liveNodes.length - 1];
        return this.leader;
    }
}

class HeartbeatMonitor {
    constructor(timeoutMs) {
        this.timeoutMs = timeoutMs;
        this.lastHeartbeat = new Map();
    }

    heartbeat(nodeId, timestamp) {
        this.lastHeartbeat.set(nodeId, timestamp);
    }

    suspected(nodeId, now) {
        const last = this.lastHeartbeat.get(nodeId);

        if (last === undefined) {
            return true;
        }

        return now - last > this.timeoutMs;
    }
}

function demonstrateElectionAndFailureDetection() {
    section("Leader Election and Failure Detection");

    const cluster = new ElectionCluster(["node-a", "node-b", "node-c"]);
    console.log("Initial leader:", cluster.elect());

    cluster.fail("node-c");
    console.log("Leader after failure:", cluster.elect());

    const monitor = new HeartbeatMonitor(5000);

    monitor.heartbeat("node-a", 10000);

    console.log(
        "node-a suspected at 14000:",
        monitor.suspected("node-a", 14000)
    );

    console.log(
        "node-a suspected at 16001:",
        monitor.suspected("node-a", 16001)
    );
}


// ---------------------------------------------------------------------------
// Consistent hashing
// ---------------------------------------------------------------------------

class HashRing {
    constructor(nodes, replicasPerNode = 16) {
        if (!nodes.length) {
            throw new Error("Hash ring needs at least one node");
        }

        this.replicasPerNode = replicasPerNode;
        this.tokens = new Map();

        for (const node of nodes) {
            this.add(node);
        }
    }

    add(node) {
        for (let index = 0; index < this.replicasPerNode; index += 1) {
            const token = stableHash(`${node}:${index}`);
            this.tokens.set(token, node);
        }
    }

    remove(node) {
        for (const [token, owner] of this.tokens.entries()) {
            if (owner === node) {
                this.tokens.delete(token);
            }
        }

        if (this.tokens.size === 0) {
            throw new Error("Cannot remove the final hash-ring node");
        }
    }

    locate(key) {
        const token = stableHash(key);
        const ordered = [...this.tokens.keys()].sort();

        const selected = ordered.find(candidate => candidate >= token);

        return this.tokens.get(selected ?? ordered[0]);
    }
}

function demonstrateHashRing() {
    section("Consistent Hashing");

    const ring = new HashRing(["cache-a", "cache-b", "cache-c"]);

    for (const key of [
        "customer:101",
        "customer:102",
        "order:901",
        "order:902"
    ]) {
        console.log(`${key.padEnd(16)} -> ${ring.locate(key)}`);
    }

    ring.add("cache-d");

    console.log("After adding cache-d:");

    for (const key of [
        "customer:101",
        "customer:102",
        "order:901",
        "order:902"
    ]) {
        console.log(`${key.padEnd(16)} -> ${ring.locate(key)}`);
    }
}


// ---------------------------------------------------------------------------
// Distributed tracing
// ---------------------------------------------------------------------------

class TraceCollector {
    constructor() {
        this.spans = [];
        this.sequence = 0;
    }

    startSpan({ traceId, service, operation, parentSpanId = null }) {
        this.sequence += 1;

        const span = {
            spanId: `span-${this.sequence}`,
            traceId,
            parentSpanId,
            service,
            operation,
            startedAt: Date.now()
        };

        this.spans.push(span);

        return span;
    }

    finishSpan(span, durationMs) {
        span.durationMs = durationMs;
        span.finishedAt = span.startedAt + durationMs;
        return span;
    }
}

function demonstrateTracing() {
    section("Distributed Tracing");

    const tracer = new TraceCollector();
    const traceId = "trace-88a";

    const gateway = tracer.startSpan({
        traceId,
        service: "gateway",
        operation: "POST /orders"
    });

    const orders = tracer.startSpan({
        traceId,
        service: "order-service",
        operation: "create-order",
        parentSpanId: gateway.spanId
    });

    const inventory = tracer.startSpan({
        traceId,
        service: "inventory-service",
        operation: "reserve",
        parentSpanId: orders.spanId
    });

    tracer.finishSpan(gateway, 31);
    tracer.finishSpan(orders, 23);
    tracer.finishSpan(inventory, 9);

    for (const span of tracer.spans) {
        console.log(
            `${span.service.padEnd(20)} ` +
            `${span.operation.padEnd(18)} ` +
            `parent=${String(span.parentSpanId).padEnd(8)} ` +
            `${span.durationMs}ms`
        );
    }
}


// ---------------------------------------------------------------------------
// Eventual consistency and conflict resolution
// ---------------------------------------------------------------------------

class LastWriteWinsRegister {
    constructor() {
        this.value = null;
        this.timestamp = -1;
        this.writer = null;
    }

    apply(value, timestamp, writer) {
        if (
            timestamp > this.timestamp ||
            (timestamp === this.timestamp && writer > this.writer)
        ) {
            this.value = value;
            this.timestamp = timestamp;
            this.writer = writer;
        }
    }

    state() {
        return {
            value: this.value,
            timestamp: this.timestamp,
            writer: this.writer
        };
    }
}

function demonstrateConflictResolution() {
    section("Eventual Consistency and Conflict Resolution");

    const register = new LastWriteWinsRegister();

    register.apply("v1", 100, "region-a");
    register.apply("v2", 99, "region-b");
    register.apply("v3", 101, "region-b");

    console.log("Resolved state:", register.state());

    console.log(
        "The example uses a deterministic last-write-wins rule. "
        + "Production systems must choose conflict semantics that match the domain."
    );
}


// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
    console.log("Distributed Systems Fundamentals");
    console.log("Node.js event-driven simulations");

    await demonstrateAsyncMessaging();
    await demonstrateRetry();
    demonstrateIdempotency();
    demonstrateQuorumStore();
    demonstrateElectionAndFailureDetection();
    demonstrateHashRing();
    demonstrateTracing();
    demonstrateConflictResolution();

    section("Distributed-System Engineering Boundaries");
    console.log(
        "Network calls can be delayed, duplicated, reordered, or lost."
    );
    console.log(
        "A process can fail after accepting work but before replying."
    );
    console.log(
        "Retries therefore require timeout handling and safe operation semantics."
    );
    console.log(
        "Replication improves availability but requires explicit consistency rules."
    );
    console.log(
        "Quorums provide a coordination mechanism but do not automatically solve every consistency problem."
    );
    console.log(
        "Leader election requires careful handling of stale leaders and split-brain risk."
    );
}

main().catch(error => {
    console.error("Fatal simulation error:", error.message);
    process.exitCode = 1;
});
