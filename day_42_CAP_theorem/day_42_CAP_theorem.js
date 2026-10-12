"use strict";

/*
 * CAP theorem workflow simulator.
 *
 * This implementation focuses on JavaScript's event-driven model. A
 * distributed cluster is represented as asynchronous nodes. Network
 * partitions are simulated by selectively rejecting messages between
 * nodes. The implementation shows why asynchronous availability decisions
 * can produce divergent replica state during a partition.
 */

class Replica {
    constructor(id, region) {
        this.id = id;
        this.region = region;
        this.online = true;
        this.data = new Map();
        this.version = 0;
    }

    write(key, value) {
        this.version += 1;
        this.data.set(key, {
            version: this.version,
            value
        });
    }

    read(key) {
        return this.data.get(key) ?? null;
    }
}

class PartitionNetwork {
    constructor(replicas) {
        this.replicas = new Map(replicas.map(replica => [replica.id, replica]));
        this.groups = [new Set(this.replicas.keys())];
    }

    partition(groups) {
        const expected = new Set(this.replicas.keys());
        const actual = new Set(groups.flatMap(group => [...group]));

        if (expected.size !== actual.size) {
            throw new Error("Partition groups must contain every replica exactly once.");
        }

        for (const id of expected) {
            if (!actual.has(id)) {
                throw new Error(`Replica ${id} is missing from the partition.`);
            }
        }

        this.groups = groups.map(group => new Set(group));
    }

    heal() {
        this.groups = [new Set(this.replicas.keys())];
    }

    reachable(fromId) {
        const group = this.groups.find(candidate => candidate.has(fromId));

        if (!group) {
            return [];
        }

        return [...group]
            .map(id => this.replicas.get(id))
            .filter(replica => replica.online);
    }

    canCommunicate(first, second) {
        return this.groups.some(
            group => group.has(first) && group.has(second)
        );
    }
}

class CAPCluster {
    constructor(replicas, mode) {
        if (!["CP", "AP"].includes(mode)) {
            throw new Error("Mode must be CP or AP.");
        }

        this.replicas = replicas;
        this.network = new PartitionNetwork(replicas);
        this.mode = mode;
    }

    async networkDelay() {
        await new Promise(resolve => setTimeout(resolve, 5));
    }

    async write(coordinatorId, key, value) {
        if (!key) {
            throw new Error("A write requires a non-empty key.");
        }

        const reachable = this.network.reachable(coordinatorId);
        const quorum = Math.floor(this.replicas.length / 2) + 1;

        if (this.mode === "CP" && reachable.length < quorum) {
            return {
                committed: false,
                acknowledged: [],
                reason: `Quorum unavailable: ${reachable.length}/${quorum}`
            };
        }

        await this.networkDelay();

        const targets = this.mode === "CP"
            ? reachable
            : reachable.slice(0, Math.max(1, reachable.length));

        for (const replica of targets) {
            replica.write(key, value);
        }

        return {
            committed: true,
            acknowledged: targets.map(replica => replica.id),
            reason: this.mode === "CP"
                ? "Majority quorum satisfied."
                : "Accepted by currently reachable replicas."
        };
    }

    async read(coordinatorId, key) {
        const reachable = this.network.reachable(coordinatorId);

        if (reachable.length === 0) {
            return {
                available: false,
                value: null,
                consistent: false
            };
        }

        await this.networkDelay();

        const records = reachable
            .map(replica => ({
                id: replica.id,
                record: replica.read(key)
            }))
            .filter(entry => entry.record !== null);

        if (records.length === 0) {
            return {
                available: true,
                value: null,
                consistent: true
            };
        }

        const versions = new Set(
            records.map(entry => entry.record.version)
        );

        const newest = records.reduce(
            (current, candidate) =>
                candidate.record.version > current.record.version
                    ? candidate
                    : current
        );

        return {
            available: true,
            value: newest.record.value,
            consistent: versions.size === 1,
            sources: records.map(entry => entry.id)
        };
    }

    reconcile(key) {
        const records = this.replicas
            .map(replica => ({
                replica,
                record: replica.read(key)
            }))
            .filter(entry => entry.record !== null);

        if (records.length === 0) {
            return null;
        }

        const winner = records.reduce(
            (current, candidate) =>
                candidate.record.version > current.record.version
                    ? candidate
                    : current
        );

        for (const replica of this.replicas) {
            replica.data.set(key, {
                version: winner.record.version,
                value: winner.record.value
            });
        }

        return winner.record.value;
    }

    snapshot() {
        return this.replicas.map(replica => ({
            id: replica.id,
            region: replica.region,
            online: replica.online,
            data: Object.fromEntries(replica.data)
        }));
    }
}

async function demonstrateCP() {
    console.log("\n=== CP BEHAVIOR ===");

    const cluster = new CAPCluster(
        [
            new Replica("r1", "Delhi"),
            new Replica("r2", "Mumbai"),
            new Replica("r3", "Bengaluru")
        ],
        "CP"
    );

    console.log(
        await cluster.write("r1", "payment:100", "approved")
    );

    cluster.network.partition([
        new Set(["r1"]),
        new Set(["r2", "r3"])
    ]);

    console.log(
        await cluster.write("r1", "payment:100", "reversed")
    );

    console.log(
        "A CP coordinator isolated from the majority rejects the write."
    );
}

async function demonstrateAP() {
    console.log("\n=== AP BEHAVIOR ===");

    const cluster = new CAPCluster(
        [
            new Replica("r1", "Delhi"),
            new Replica("r2", "Mumbai"),
            new Replica("r3", "Bengaluru")
        ],
        "AP"
    );

    await cluster.write("r1", "inventory:sku-77", "stock=10");

    cluster.network.partition([
        new Set(["r1"]),
        new Set(["r2", "r3"])
    ]);

    const firstPartitionWrite =
        await cluster.write("r1", "inventory:sku-77", "stock=8");

    const secondPartitionWrite =
        await cluster.write("r2", "inventory:sku-77", "stock=5");

    console.log("Partition A:", firstPartitionWrite);
    console.log("Partition B:", secondPartitionWrite);
    console.table(cluster.snapshot());

    cluster.network.heal();

    const resolved = cluster.reconcile("inventory:sku-77");

    console.log("Reconciled value:", resolved);
    console.table(cluster.snapshot());
}

async function demonstrateEventDrivenPolicyEvaluation() {
    console.log("\n=== EVENT-DRIVEN POLICY DECISION ===");

    const events = [
        { type: "partition_detected", affected: ["r1"] },
        { type: "write_request", coordinator: "r1" },
        { type: "quorum_unavailable" },
        { type: "partition_healed" }
    ];

    const handlers = {
        partition_detected: event =>
            `Partition detected affecting ${event.affected.join(", ")}`,
        write_request: event =>
            `Write routed through ${event.coordinator}`,
        quorum_unavailable: () =>
            "Consistency policy prevents a quorum-dependent operation.",
        partition_healed: () =>
            "Connectivity restored; reconciliation can proceed."
    };

    for (const event of events) {
        const handler = handlers[event.type];

        if (!handler) {
            console.warn(`Unhandled event type: ${event.type}`);
            continue;
        }

        console.log(handler(event));
        await new Promise(resolve => setTimeout(resolve, 2));
    }
}

function demonstrateDesignRules() {
    console.log("\n=== DESIGN RULES ===");
    console.log(
        "Consistency concerns whether replicas expose one coherent logical state."
    );
    console.log(
        "Availability concerns whether a reachable node continues responding."
    );
    console.log(
        "Partition tolerance concerns surviving communication loss between replicas."
    );
    console.log(
        "During a partition, CP commonly rejects operations that cannot satisfy"
        + " its consistency protocol, while AP commonly accepts reachable operations"
        + " and resolves divergence later."
    );
}

async function main() {
    demonstrateDesignRules();
    await demonstrateCP();
    await demonstrateAP();
    await demonstrateEventDrivenPolicyEvaluation();

    console.log("\nSimulation finished.");
}

main().catch(error => {
    console.error("Simulation failed:", error.message);
    process.exitCode = 1;
});
