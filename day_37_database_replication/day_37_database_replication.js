"use strict";

/*
 * Database Replication: primary-replica, synchronous and asynchronous replication.
 *
 * This Node.js program models replication as an event-driven system.
 * JavaScript's EventEmitter is used to make delivery and acknowledgement
 * behavior explicit. The implementation focuses on:
 *
 * - primary write authority
 * - ordered WAL-like records
 * - asynchronous delivery
 * - synchronous acknowledgement
 * - replica replay position
 * - replication lag
 * - failure and recovery
 * - quorum acknowledgement
 * - failover and generation fencing
 * - consistency verification
 */

const { EventEmitter } = require("node:events");

const ReplicationMode = Object.freeze({
    ASYNCHRONOUS: "asynchronous",
    SYNCHRONOUS: "synchronous",
});

const NodeState = Object.freeze({
    UP: "up",
    DOWN: "down",
});

class ReplicationError extends Error {
    constructor(message) {
        super(message);
        this.name = "ReplicationError";
    }
}

class ChangeRecord {
    constructor({ lsn, transactionId, operation, key, value, generation }) {
        this.lsn = lsn;
        this.transactionId = transactionId;
        this.operation = operation;
        this.key = key;
        this.value = value;
        this.generation = generation;
    }
}

class Replica {
    constructor(name) {
        this.name = name;
        this.state = NodeState.UP;
        this.data = new Map();
        this.receivedLsn = 0;
        this.replayedLsn = 0;
        this.pending = new Map();
        this.applied = new Set();
    }

    receive(change) {
        if (this.state === NodeState.DOWN) {
            return false;
        }

        if (change.lsn <= this.receivedLsn && this.applied.has(change.lsn)) {
            return false;
        }

        this.pending.set(change.lsn, change);
        this.receivedLsn = Math.max(this.receivedLsn, change.lsn);
        return true;
    }

    replayOne() {
        if (this.state === NodeState.DOWN) {
            throw new ReplicationError(
                `${this.name} cannot replay while it is down`
            );
        }

        const nextLsn = this.replayedLsn + 1;
        const change = this.pending.get(nextLsn);

        if (!change) {
            return false;
        }

        if (this.applied.has(change.lsn)) {
            this.pending.delete(change.lsn);
            this.replayedLsn = change.lsn;
            return true;
        }

        if (change.operation === "SET") {
            this.data.set(change.key, change.value);
        } else if (change.operation === "DELETE") {
            this.data.delete(change.key);
        } else {
            throw new ReplicationError(
                `Unsupported operation: ${change.operation}`
            );
        }

        this.applied.add(change.lsn);
        this.pending.delete(change.lsn);
        this.replayedLsn = change.lsn;
        return true;
    }

    replayAll() {
        let count = 0;

        while (this.replayOne()) {
            count += 1;
        }

        return count;
    }

    get lag() {
        return Math.max(0, this.receivedLsn - this.replayedLsn);
    }

    snapshot() {
        return Object.fromEntries(this.data.entries());
    }
}

class Primary {
    constructor(name) {
        this.name = name;
        this.state = NodeState.UP;
        this.generation = 1;
        this.data = new Map();
        this.nextLsn = 1;
        this.nextTransactionId = 1;
        this.wal = [];
    }

    write(operation, key, value = undefined) {
        if (this.state === NodeState.DOWN) {
            throw new ReplicationError("Primary is unavailable");
        }

        if (operation === "SET") {
            if (value === undefined || value === null) {
                throw new TypeError("SET requires a non-null value");
            }

            this.data.set(key, value);
        } else if (operation === "DELETE") {
            this.data.delete(key);
        } else {
            throw new TypeError(`Unsupported operation: ${operation}`);
        }

        const change = new ChangeRecord({
            lsn: this.nextLsn++,
            transactionId: this.nextTransactionId++,
            operation,
            key,
            value,
            generation: this.generation,
        });

        this.wal.push(change);
        return change;
    }

    snapshot() {
        return Object.fromEntries(this.data.entries());
    }
}

class ReplicationCluster extends EventEmitter {
    constructor({ primaryName, mode, synchronousReplicaCount = 0 }) {
        super();

        if (!Object.values(ReplicationMode).includes(mode)) {
            throw new TypeError(`Unknown replication mode: ${mode}`);
        }

        if (!Number.isInteger(synchronousReplicaCount) ||
            synchronousReplicaCount < 0) {
            throw new TypeError("Invalid synchronous replica count");
        }

        this.mode = mode;
        this.synchronousReplicaCount = synchronousReplicaCount;
        this.primary = new Primary(primaryName);
        this.replicas = new Map();
    }

    addReplica(replica) {
        if (this.replicas.has(replica.name)) {
            throw new ReplicationError(
                `Replica ${replica.name} already exists`
            );
        }

        if (replica.name === this.primary.name) {
            throw new ReplicationError(
                "Replica cannot have the primary's name"
            );
        }

        this.replicas.set(replica.name, replica);
    }

    getHealthyReplicas() {
        return [...this.replicas.values()]
            .filter((replica) => replica.state === NodeState.UP);
    }

    deliver(change) {
        for (const replica of this.getHealthyReplicas()) {
            if (replica.receive(change)) {
                this.emit("changeDelivered", {
                    replica: replica.name,
                    lsn: change.lsn,
                });
            }
        }
    }

    replayReplica(name) {
        const replica = this.replicas.get(name);

        if (!replica) {
            throw new ReferenceError(`Unknown replica: ${name}`);
        }

        const count = replica.replayAll();

        if (count > 0) {
            this.emit("replay", {
                replica: replica.name,
                replayedLsn: replica.replayedLsn,
                count,
            });
        }

        return count;
    }

    countAcknowledged(change) {
        return this.getHealthyReplicas()
            .filter((replica) => replica.replayedLsn >= change.lsn)
            .length;
    }

    write(operation, key, value, { replayImmediately = true } = {}) {
        const change = this.primary.write(operation, key, value);

        this.emit("primaryWrite", {
            lsn: change.lsn,
            transactionId: change.transactionId,
        });

        this.deliver(change);

        if (replayImmediately) {
            for (const replica of this.getHealthyReplicas()) {
                this.replayReplica(replica.name);
            }
        }

        if (this.mode === ReplicationMode.SYNCHRONOUS) {
            const acknowledgements = this.countAcknowledged(change);

            if (acknowledgements < this.synchronousReplicaCount) {
                throw new ReplicationError(
                    `Synchronous commit ${change.lsn} not acknowledged: ` +
                    `${acknowledgements}/${this.synchronousReplicaCount}`
                );
            }
        }

        this.emit("commitAcknowledged", {
            lsn: change.lsn,
            mode: this.mode,
        });

        return change;
    }

    status() {
        return [...this.replicas.values()].map((replica) => ({
            name: replica.name,
            state: replica.state,
            receivedLsn: replica.receivedLsn,
            replayedLsn: replica.replayedLsn,
            lag: replica.lag,
        }));
    }

    compareReplica(name) {
        const replica = this.replicas.get(name);

        if (!replica) {
            throw new ReferenceError(`Unknown replica: ${name}`);
        }

        const primarySnapshot = this.primary.snapshot();
        const replicaSnapshot = replica.snapshot();
        const keys = new Set([
            ...Object.keys(primarySnapshot),
            ...Object.keys(replicaSnapshot),
        ]);

        const differences = {};

        for (const key of keys) {
            if (primarySnapshot[key] !== replicaSnapshot[key]) {
                differences[key] = {
                    primary: primarySnapshot[key],
                    replica: replicaSnapshot[key],
                };
            }
        }

        return {
            consistent: Object.keys(differences).length === 0,
            differences,
        };
    }

    promote(name) {
        const replica = this.replicas.get(name);

        if (!replica) {
            throw new ReferenceError(`Unknown replica: ${name}`);
        }

        if (this.primary.state !== NodeState.DOWN) {
            throw new ReplicationError(
                "Failover requires the old primary to be fenced or stopped"
            );
        }

        if (replica.state !== NodeState.UP || replica.replayedLsn === 0) {
            throw new ReplicationError(
                "Only a healthy replica with replayed state can be promoted"
            );
        }

        const oldPrimary = this.primary;
        const newPrimary = new Primary(replica.name);

        newPrimary.generation = oldPrimary.generation + 1;
        newPrimary.data = new Map(replica.data);
        newPrimary.nextLsn = replica.replayedLsn + 1;
        newPrimary.nextTransactionId = oldPrimary.nextTransactionId;

        newPrimary.wal = oldPrimary.wal
            .filter((change) => change.lsn <= replica.replayedLsn);

        this.primary = newPrimary;
        this.replicas.delete(name);

        this.emit("promotion", {
            oldPrimary: oldPrimary.name,
            newPrimary: newPrimary.name,
            generation: newPrimary.generation,
        });

        return newPrimary;
    }
}

function heading(text) {
    console.log(`\n${"=".repeat(70)}\n${text}\n${"=".repeat(70)}`);
}

function demonstrateAsynchronousMode() {
    heading("Asynchronous replication");

    const cluster = new ReplicationCluster({
        primaryName: "shop-primary",
        mode: ReplicationMode.ASYNCHRONOUS,
    });

    cluster.addReplica(new Replica("shop-replica-a"));
    cluster.addReplica(new Replica("shop-replica-b"));

    cluster.on("primaryWrite", ({ lsn }) => {
        console.log(`Primary generated WAL record ${lsn}`);
    });

    cluster.on("commitAcknowledged", ({ lsn, mode }) => {
        console.log(`Commit ${lsn} acknowledged in ${mode} mode`);
    });

    cluster.write("SET", "order:501", "PAID", {
        replayImmediately: false,
    });

    console.log("Immediately after primary commit:");
    console.table(cluster.status());

    cluster.replayReplica("shop-replica-a");

    console.log("Only replica-a has replayed the change:");
    console.table(cluster.status());

    cluster.replayReplica("shop-replica-b");
    console.log("Both replicas have caught up:");
    console.table(cluster.status());
}

function demonstrateSynchronousMode() {
    heading("Synchronous replication");

    const cluster = new ReplicationCluster({
        primaryName: "bank-primary",
        mode: ReplicationMode.SYNCHRONOUS,
        synchronousReplicaCount: 1,
    });

    cluster.addReplica(new Replica("bank-replica-a"));

    const change = cluster.write("SET", "transfer:900", "SETTLED");
    console.log(
        `Synchronous commit acknowledged after replica replay, LSN=${change.lsn}`
    );

    cluster.replicas.get("bank-replica-a").state = NodeState.DOWN;

    try {
        cluster.write("SET", "transfer:901", "SETTLED");
    } catch (error) {
        console.log("Expected failure:", error.message);
    }
}

function demonstrateEventDrivenDelivery() {
    heading("Event-driven replication");

    const cluster = new ReplicationCluster({
        primaryName: "event-primary",
        mode: ReplicationMode.ASYNCHRONOUS,
    });

    const replica = new Replica("event-replica");
    cluster.addReplica(replica);

    cluster.on("changeDelivered", (event) => {
        console.log(
            `Change LSN ${event.lsn} delivered to ${event.replica}`
        );
    });

    cluster.on("replay", (event) => {
        console.log(
            `${event.replica} replayed ${event.count} record(s), ` +
            `position=${event.replayedLsn}`
        );
    });

    cluster.write("SET", "cache:user:1", "READY");
}

function demonstrateFailureAndRecovery() {
    heading("Replica failure and recovery");

    const cluster = new ReplicationCluster({
        primaryName: "reporting-primary",
        mode: ReplicationMode.ASYNCHRONOUS,
    });

    const replica = new Replica("reporting-replica");
    cluster.addReplica(replica);

    replica.state = NodeState.DOWN;

    cluster.write("SET", "report:1", "READY", {
        replayImmediately: false,
    });
    cluster.write("SET", "report:2", "READY", {
        replayImmediately: false,
    });

    console.table(cluster.status());

    replica.state = NodeState.UP;

    /*
     * A production replica does not normally need the primary to resend an
     * entire history when it has a durable log position. It requests the
     * missing range. This simulation uses the primary WAL to reconstruct that
     * missing range.
     */
    for (const change of cluster.primary.wal) {
        replica.receive(change);
    }

    cluster.replayReplica(replica.name);

    console.table(cluster.status());
    console.log(cluster.compareReplica(replica.name));
}

function demonstrateQuorumAndFailover() {
    heading("Quorum acknowledgement and failover");

    const cluster = new ReplicationCluster({
        primaryName: "ledger-primary",
        mode: ReplicationMode.SYNCHRONOUS,
        synchronousReplicaCount: 2,
    });

    cluster.addReplica(new Replica("ledger-replica-a"));
    cluster.addReplica(new Replica("ledger-replica-b"));
    cluster.addReplica(new Replica("ledger-replica-c"));

    cluster.write("SET", "ledger:1", "POSTED");
    console.table(cluster.status());

    cluster.replicas.get("ledger-replica-c").state = NodeState.DOWN;
    cluster.write("SET", "ledger:2", "POSTED");

    cluster.replicas.get("ledger-replica-b").state = NodeState.DOWN;

    try {
        cluster.write("SET", "ledger:3", "POSTED");
    } catch (error) {
        console.log("Quorum failure:", error.message);
    }

    const replicaA = cluster.replicas.get("ledger-replica-a");

    cluster.primary.state = NodeState.DOWN;
    const promoted = cluster.promote(replicaA.name);

    console.log(
        `Promoted ${promoted.name}; generation=${promoted.generation}`
    );

    promoted.write("SET", "ledger:4", "POSTED");

    console.log("New primary snapshot:", promoted.snapshot());
}

function demonstrateIdempotency() {
    heading("Idempotent replay");

    const cluster = new ReplicationCluster({
        primaryName: "idempotent-primary",
        mode: ReplicationMode.ASYNCHRONOUS,
    });

    const replica = new Replica("idempotent-replica");
    cluster.addReplica(replica);

    const change = cluster.write(
        "SET",
        "inventory:ABC",
        "37",
        { replayImmediately: false }
    );

    replica.receive(change);
    replica.receive(change);
    replica.replayAll();

    /*
     * The applied-LSN set prevents a duplicated delivery from changing the
     * state twice. This matters when a transport retries a message.
     */
    console.log(replica.snapshot());
}

function main() {
    demonstrateAsynchronousMode();
    demonstrateSynchronousMode();
    demonstrateEventDrivenDelivery();
    demonstrateFailureAndRecovery();
    demonstrateQuorumAndFailover();
    demonstrateIdempotency();
}

main();
