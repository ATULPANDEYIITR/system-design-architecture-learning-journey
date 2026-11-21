"use strict";

const { randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

const Architecture = Object.freeze({
    ACTIVE_ACTIVE: "active-active",
    ACTIVE_PASSIVE: "active-passive"
});

const State = Object.freeze({
    HEALTHY: "healthy",
    DEGRADED: "degraded",
    DOWN: "down"
});

const Role = Object.freeze({
    ACTIVE: "active",
    PASSIVE: "passive",
    FAILED: "failed",
    RECOVERING: "recovering"
});

const Replication = Object.freeze({
    SYNC: "synchronous",
    ASYNC: "asynchronous"
});

class RedundancyError extends Error {}
class ValidationError extends RedundancyError {}
class AvailabilityError extends RedundancyError {}
class ReplicationError extends RedundancyError {}
class FencingError extends RedundancyError {}

/*
 * A monotonically increasing fencing token prevents an old primary
 * from writing after another node has been promoted.
 */
class FencingAuthority {
    #epoch = 0;
    #owner = null;

    acquire(nodeId) {
        this.#epoch++;
        this.#owner = nodeId;

        return Object.freeze({
            nodeId,
            epoch: this.#epoch
        });
    }

    validate(token) {
        return (
            token !== null &&
            token.nodeId === this.#owner &&
            token.epoch === this.#epoch
        );
    }

    get owner() {
        return this.#owner;
    }

    get epoch() {
        return this.#epoch;
    }
}

class ClusterNode {
    constructor({
        id,
        region,
        capacity,
        role,
        status = State.HEALTHY
    }) {
        if (!id || !region) {
            throw new ValidationError("Node ID and region are required");
        }

        if (!Number.isInteger(capacity) || capacity <= 0) {
            throw new ValidationError("Capacity must be positive");
        }

        this.id = id;
        this.region = region;
        this.capacity = capacity;
        this.role = role;
        this.status = status;
        this.load = 0;
        this.appliedSequence = 0;
        this.replicationLag = 0;
        this.data = new Map();
        this.fencingToken = null;
    }

    get available() {
        return (
            this.status !== State.DOWN &&
            this.load < this.capacity
        );
    }

    acquireLoad() {
        if (!this.available) {
            throw new AvailabilityError(
                `Node ${this.id} has no available capacity`
            );
        }

        this.load++;
    }

    releaseLoad() {
        this.load = Math.max(0, this.load - 1);
    }
}

class ReplicationLog {
    #entries = [];

    append(entry) {
        this.#entries.push(Object.freeze({ ...entry }));
    }

    after(sequence) {
        return this.#entries.filter(
            entry => entry.sequence > sequence
        );
    }

    get latestSequence() {
        return this.#entries.length
            ? this.#entries[this.#entries.length - 1].sequence
            : 0;
    }

    get size() {
        return this.#entries.length;
    }
}

class RedundantCluster extends EventEmitter {
    #nodes = new Map();
    #data = new Map();
    #sequence = 0;
    #log = new ReplicationLog();
    #fencing = new FencingAuthority();
    #operationQueue = Promise.resolve();
    #metrics = {
        requests: 0,
        failures: 0,
        failovers: 0,
        rejectedWrites: 0
    };

    constructor({
        name,
        architecture,
        replication,
        requiredActiveNodes = 1,
        maxLag = 0,
        autoFailover = true
    }, nodes) {
        super();

        if (!name || !Object.values(Architecture).includes(architecture)) {
            throw new ValidationError("Invalid cluster configuration");
        }

        if (!Object.values(Replication).includes(replication)) {
            throw new ValidationError("Invalid replication mode");
        }

        if (!Number.isInteger(requiredActiveNodes) ||
            requiredActiveNodes < 1) {
            throw new ValidationError("Invalid active node requirement");
        }

        if (!Number.isInteger(maxLag) || maxLag < 0) {
            throw new ValidationError("Maximum lag cannot be negative");
        }

        this.name = name;
        this.architecture = architecture;
        this.replication = replication;
        this.requiredActiveNodes = requiredActiveNodes;
        this.maxLag = maxLag;
        this.autoFailover = autoFailover;

        for (const node of nodes) {
            if (this.#nodes.has(node.id)) {
                throw new ValidationError("Duplicate node ID");
            }

            this.#nodes.set(node.id, node);
        }

        if (this.#nodes.size < 2) {
            throw new ValidationError("Two or more nodes are required");
        }

        this.#initialize();
    }

    #initialize() {
        const healthy = [...this.#nodes.values()].filter(
            node => node.status === State.HEALTHY
        );

        if (healthy.length < 1) {
            throw new AvailabilityError("No healthy nodes");
        }

        if (this.architecture === Architecture.ACTIVE_ACTIVE) {
            if (healthy.length < this.requiredActiveNodes) {
                throw new AvailabilityError(
                    "Insufficient active nodes"
                );
            }

            for (const node of healthy) {
                node.role = Role.ACTIVE;
            }

            const token = this.#fencing.acquire("active-active");
            for (const node of healthy) {
                node.fencingToken = token;
            }
        } else {
            const primary = healthy[0];
            primary.role = Role.ACTIVE;

            for (const node of healthy.slice(1)) {
                node.role = Role.PASSIVE;
            }

            primary.fencingToken = this.#fencing.acquire(primary.id);
        }
    }

    get nodes() {
        return [...this.#nodes.values()].map(node => ({
            id: node.id,
            region: node.region,
            role: node.role,
            status: node.status,
            load: node.load,
            capacity: node.capacity,
            appliedSequence: node.appliedSequence,
            replicationLag: node.replicationLag
        }));
    }

    #activeNodes() {
        return [...this.#nodes.values()].filter(
            node => node.role === Role.ACTIVE && node.available
        );
    }

    #selectNode() {
        const active = this.#activeNodes();

        if (active.length < this.requiredActiveNodes &&
            this.architecture === Architecture.ACTIVE_ACTIVE) {
            throw new AvailabilityError(
                "Active node requirement not satisfied"
            );
        }

        if (!active.length) {
            throw new AvailabilityError("No active node available");
        }

        return active.sort((a, b) => {
            const loadA = a.load / a.capacity;
            const loadB = b.load / b.capacity;

            return loadA - loadB ||
                a.replicationLag - b.replicationLag ||
                a.id.localeCompare(b.id);
        })[0];
    }

    async read(key) {
        if (typeof key !== "string" || !key.trim()) {
            throw new ValidationError("Read key is required");
        }

        return this.#serialize(async () => {
            const node = this.#selectNode();
            node.acquireLoad();

            try {
                this.#metrics.requests++;

                return {
                    node: node.id,
                    key,
                    value: this.#data.get(key) ?? null,
                    sequence: node.appliedSequence
                };
            } finally {
                node.releaseLoad();
            }
        });
    }

    async write(key, value) {
        if (typeof key !== "string" || !key.trim()) {
            throw new ValidationError("Write key is required");
        }

        if (typeof value !== "string") {
            throw new ValidationError("Value must be a string");
        }

        return this.#serialize(async () => {
            const node = this.#selectNode();
            node.acquireLoad();

            try {
                const token = node.fencingToken;

                if (this.architecture === Architecture.ACTIVE_PASSIVE &&
                    !this.#fencing.validate(token)) {
                    this.#metrics.rejectedWrites++;
                    throw new FencingError(
                        "Node does not own the current fencing token"
                    );
                }

                const replicas = [...this.#nodes.values()].filter(
                    replica =>
                        replica.id !== node.id &&
                        replica.status !== State.DOWN &&
                        (
                            this.architecture === Architecture.ACTIVE_ACTIVE ||
                            replica.role === Role.PASSIVE
                        )
                );

                if (this.replication === Replication.SYNC &&
                    replicas.length === 0) {
                    throw new ReplicationError(
                        "No replica available for synchronous write"
                    );
                }

                const sequence = ++this.#sequence;

                const entry = {
                    sequence,
                    key,
                    value,
                    timestamp: new Date().toISOString(),
                    origin: node.id
                };

                if (this.replication === Replication.SYNC) {
                    for (const replica of replicas) {
                        if (replica.status !== State.HEALTHY) {
                            throw new ReplicationError(
                                `Replica ${replica.id} is unhealthy`
                            );
                        }
                    }

                    for (const replica of replicas) {
                        replica.data.set(key, value);
                        replica.appliedSequence = sequence;
                        replica.replicationLag = 0;
                    }
                } else {
                    for (const replica of replicas) {
                        replica.replicationLag++;
                    }
                }

                node.data.set(key, value);
                node.appliedSequence = sequence;

                this.#data.set(key, value);
                this.#log.append(entry);
                this.#metrics.requests++;

                const result = {
                    node: node.id,
                    sequence,
                    replicatedTo: replicas.map(r => r.id),
                    acknowledged: true
                };

                this.emit("write", result);

                return result;
            } catch (error) {
                this.#metrics.failures++;
                throw error;
            } finally {
                node.releaseLoad();
            }
        });
    }

    #serialize(operation) {
        const result = this.#operationQueue.then(operation);

        this.#operationQueue = result.catch(() => undefined);

        return result;
    }

    async failNode(nodeId) {
        return this.#serialize(async () => {
            const node = this.#nodes.get(nodeId);

            if (!node) {
                throw new ValidationError("Unknown node");
            }

            if (node.status === State.DOWN) {
                return { changed: false, reason: "Already down" };
            }

            node.status = State.DOWN;
            node.role = Role.FAILED;
            node.load = 0;
            this.#metrics.failovers++;

            this.emit("nodeFailure", { nodeId });

            if (this.architecture === Architecture.ACTIVE_ACTIVE) {
                const available = this.#activeNodes();

                if (available.length < this.requiredActiveNodes) {
                    this.emit("availabilityLost", {
                        available: available.length
                    });

                    return { successful: false };
                }

                return { successful: true, mode: "active-active" };
            }

            if (!this.autoFailover) {
                return { successful: false, reason: "Manual failover required" };
            }

            const candidates = [...this.#nodes.values()]
                .filter(candidate =>
                    candidate.role === Role.PASSIVE &&
                    candidate.status === State.HEALTHY &&
                    candidate.replicationLag <= this.maxLag
                )
                .sort((a, b) =>
                    b.appliedSequence - a.appliedSequence ||
                    b.capacity - a.capacity
                );

            const promoted = candidates[0];

            if (!promoted) {
                this.emit("failoverFailed", { failedNode: nodeId });

                return {
                    successful: false,
                    reason: "No eligible standby"
                };
            }

            // Promotion receives a newer fencing epoch.
            promoted.fencingToken = this.#fencing.acquire(promoted.id);
            promoted.role = Role.ACTIVE;
            promoted.replicationLag = 0;

            this.emit("failoverCompleted", {
                failedNode: nodeId,
                promotedNode: promoted.id,
                epoch: promoted.fencingToken.epoch
            });

            return {
                successful: true,
                promotedNode: promoted.id,
                fencingEpoch: promoted.fencingToken.epoch
            };
        });
    }

    async synchronize(nodeId) {
        return this.#serialize(async () => {
            const node = this.#nodes.get(nodeId);

            if (!node) {
                throw new ValidationError("Unknown node");
            }

            if (node.status === State.DOWN) {
                throw new AvailabilityError("Cannot synchronize failed node");
            }

            const pending = this.#log.after(node.appliedSequence);

            for (const entry of pending) {
                node.data.set(entry.key, entry.value);
                node.appliedSequence = entry.sequence;
            }

            node.replicationLag = Math.max(
                0,
                this.#sequence - node.appliedSequence
            );

            this.emit("replicaSynchronized", {
                nodeId,
                records: pending.length
            });

            return pending.length;
        });
    }

    async recoverNode(nodeId) {
        return this.#serialize(async () => {
            const node = this.#nodes.get(nodeId);

            if (!node) {
                throw new ValidationError("Unknown node");
            }

            if (node.status !== State.DOWN) {
                throw new ValidationError("Node is not down");
            }

            node.status = State.HEALTHY;
            node.role = Role.RECOVERING;

            const pending = this.#log.after(node.appliedSequence);

            for (const entry of pending) {
                node.data.set(entry.key, entry.value);
                node.appliedSequence = entry.sequence;
            }

            node.replicationLag = 0;

            if (this.architecture === Architecture.ACTIVE_ACTIVE) {
                node.role = Role.ACTIVE;
                node.fencingToken = this.#fencing.acquire(
                    "active-active"
                );
            } else {
                node.role = Role.PASSIVE;
                node.fencingToken = null;
            }

            this.emit("nodeRecovered", { nodeId });

            return {
                nodeId,
                role: node.role,
                synchronizedRecords: pending.length
            };
        });
    }

    report() {
        return {
            name: this.name,
            architecture: this.architecture,
            replication: this.replication,
            sequence: this.#sequence,
            fencingEpoch: this.#fencing.epoch,
            nodes: this.nodes,
            metrics: { ...this.#metrics }
        };
    }
}

async function run() {
    const cluster = new RedundantCluster(
        {
            name: "order-processing",
            architecture: Architecture.ACTIVE_PASSIVE,
            replication: Replication.SYNC,
            maxLag: 0,
            autoFailover: true
        },
        [
            new ClusterNode({
                id: "primary",
                region: "Mumbai",
                capacity: 100,
                role: Role.ACTIVE
            }),
            new ClusterNode({
                id: "standby-1",
                region: "Pune",
                capacity: 100,
                role: Role.PASSIVE
            }),
            new ClusterNode({
                id: "standby-2",
                region: "Delhi",
                capacity: 80,
                role: Role.PASSIVE
            })
        ]
    );

    cluster.on("write", event => {
        console.log("WRITE EVENT", event);
    });

    cluster.on("failoverCompleted", event => {
        console.log("FAILOVER EVENT", event);
    });

    console.log("\nInitial state:");
    console.log(JSON.stringify(cluster.report(), null, 2));

    await cluster.write("order:1001", "CONFIRMED");
    await cluster.write("order:1002", "PROCESSING");

    console.log("\nRead:");
    console.log(await cluster.read("order:1001"));

    console.log("\nSimulating primary failure:");
    console.log(await cluster.failNode("primary"));

    console.log("\nWrite after failover:");
    console.log(await cluster.write("order:1003", "CONFIRMED"));

    console.log("\nRecovering original primary:");
    console.log(await cluster.recoverNode("primary"));

    console.log("\nFinal state:");
    console.log(JSON.stringify(cluster.report(), null, 2));
}

run().catch(error => {
    console.error("Cluster execution failed:", error.message);
    process.exitCode = 1;
});
