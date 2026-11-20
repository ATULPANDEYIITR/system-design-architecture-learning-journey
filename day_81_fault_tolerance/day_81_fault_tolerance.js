"use strict";

/**
 * Fault Tolerance: Event-driven Failure Detection and Recovery
 *
 * Node.js implementation featuring:
 * - Asynchronous heartbeat processing
 * - EventEmitter-based monitoring
 * - Failure suspicion and confirmation
 * - Recovery scheduling with exponential backoff
 * - Recovery circuit breaker
 * - Replica availability assessment
 * - Graceful shutdown
 * - JSON event persistence
 */

const { EventEmitter } = require("node:events");
const fs = require("node:fs/promises");

const State = Object.freeze({
    HEALTHY: "HEALTHY",
    SUSPECT: "SUSPECT",
    FAILED: "FAILED",
    RECOVERING: "RECOVERING",
    DISABLED: "DISABLED"
});

class FaultToleranceError extends Error {
    constructor(message) {
        super(message);
        this.name = "FaultToleranceError";
    }
}

class RecoveryPolicy {
    constructor({
        timeoutMs = 5000,
        failureThreshold = 3,
        maxRetries = 3,
        initialBackoffMs = 1000,
        maxBackoffMs = 10000,
        minimumHealthyReplicas = 2
    } = {}) {
        if (
            !Number.isFinite(timeoutMs) ||
            timeoutMs <= 0 ||
            !Number.isInteger(failureThreshold) ||
            failureThreshold < 1 ||
            !Number.isInteger(maxRetries) ||
            maxRetries < 0 ||
            !Number.isFinite(initialBackoffMs) ||
            initialBackoffMs <= 0 ||
            maxBackoffMs < initialBackoffMs ||
            !Number.isInteger(minimumHealthyReplicas) ||
            minimumHealthyReplicas < 1
        ) {
            throw new RangeError("Invalid recovery policy");
        }

        Object.assign(this, {
            timeoutMs,
            failureThreshold,
            maxRetries,
            initialBackoffMs,
            maxBackoffMs,
            minimumHealthyReplicas
        });

        Object.freeze(this);
    }

    backoff(attempt) {
        return Math.min(
            this.initialBackoffMs * (2 ** (attempt - 1)),
            this.maxBackoffMs
        );
    }
}

class CircuitBreaker {
    constructor({ failureLimit = 3, resetTimeoutMs = 5000 } = {}) {
        this.failureLimit = failureLimit;
        this.resetTimeoutMs = resetTimeoutMs;
        this.failures = 0;
        this.openedAt = null;
    }

    canExecute(now = Date.now()) {
        if (this.openedAt === null) return true;

        if (now - this.openedAt >= this.resetTimeoutMs) {
            // Permit a trial recovery after the cooldown period.
            this.openedAt = null;
            this.failures = 0;
            return true;
        }

        return false;
    }

    recordSuccess() {
        this.failures = 0;
        this.openedAt = null;
    }

    recordFailure(now = Date.now()) {
        this.failures++;

        if (this.failures >= this.failureLimit) {
            this.openedAt = now;
        }
    }
}

class ClusterMonitor extends EventEmitter {
    constructor(policy) {
        super();

        this.policy = policy;
        this.nodes = new Map();
        this.events = [];
        this.closed = false;
        this.recoveryLocks = new Set();

        this.breakers = new Map();
    }

    log(nodeId, type, details) {
        const event = Object.freeze({
            timestamp: new Date().toISOString(),
            nodeId,
            type,
            details
        });

        this.events.push(event);
        this.emit("cluster-event", event);
    }

    registerNode(nodeId, hostname) {
        if (this.closed) {
            throw new FaultToleranceError("Monitor is closed");
        }

        if (
            typeof nodeId !== "string" ||
            !nodeId.trim() ||
            typeof hostname !== "string" ||
            !hostname.trim()
        ) {
            throw new TypeError("Invalid node identity");
        }

        if (this.nodes.has(nodeId)) {
            throw new FaultToleranceError("Duplicate node");
        }

        this.nodes.set(nodeId, {
            nodeId,
            hostname,
            state: State.HEALTHY,
            lastHeartbeat: Date.now(),
            missedHeartbeats: 0,
            recoveryAttempts: 0,
            nextRecoveryAt: 0
        });

        this.breakers.set(nodeId, new CircuitBreaker());

        this.log(nodeId, "REGISTERED", hostname);
    }

    async heartbeat(nodeId, timestamp = Date.now()) {
        if (this.closed) {
            throw new FaultToleranceError("Monitor is closed");
        }

        const node = this.nodes.get(nodeId);

        if (!node) {
            throw new FaultToleranceError("Unknown node");
        }

        if (node.state === State.DISABLED) {
            throw new FaultToleranceError("Node is disabled");
        }

        if (!Number.isFinite(timestamp) || timestamp > Date.now() + 60000) {
            throw new RangeError("Invalid heartbeat timestamp");
        }

        if (timestamp < node.lastHeartbeat) {
            throw new FaultToleranceError("Stale heartbeat");
        }

        const previousState = node.state;

        node.lastHeartbeat = timestamp;
        node.missedHeartbeats = 0;
        node.state = State.HEALTHY;
        node.recoveryAttempts = 0;
        node.nextRecoveryAt = 0;

        this.breakers.get(nodeId).recordSuccess();

        this.log(nodeId, "HEARTBEAT", "Heartbeat received");

        if (previousState !== State.HEALTHY) {
            this.log(nodeId, "RECOVERED", previousState);
        }

        return Object.freeze({ nodeId, state: node.state });
    }

    detectFailures(now = Date.now()) {
        if (this.closed) return;

        for (const node of this.nodes.values()) {
            if (
                node.state === State.DISABLED ||
                node.state === State.RECOVERING
            ) {
                continue;
            }

            if (now - node.lastHeartbeat < this.policy.timeoutMs) {
                continue;
            }

            node.missedHeartbeats++;

            if (node.state === State.HEALTHY) {
                node.state = State.SUSPECT;
                this.log(node.nodeId, "SUSPECT", "Heartbeat timeout");
            }

            if (
                node.missedHeartbeats >= this.policy.failureThreshold &&
                node.state === State.SUSPECT
            ) {
                node.state = State.FAILED;
                this.log(
                    node.nodeId,
                    "FAILED",
                    "Failure threshold exceeded"
                );
            }
        }
    }

    healthyReplicaCount(excludingNode = null) {
        let count = 0;

        for (const node of this.nodes.values()) {
            if (
                node.nodeId !== excludingNode &&
                node.state === State.HEALTHY
            ) {
                count++;
            }
        }

        return count;
    }

    async recover(nodeId, restartOperation) {
        const node = this.nodes.get(nodeId);

        if (!node) {
            throw new FaultToleranceError("Unknown node");
        }

        if (node.state !== State.FAILED) {
            throw new FaultToleranceError("Node is not failed");
        }

        if (this.recoveryLocks.has(nodeId)) {
            throw new FaultToleranceError("Recovery already in progress");
        }

        const breaker = this.breakers.get(nodeId);

        if (!breaker.canExecute()) {
            throw new FaultToleranceError("Recovery circuit breaker is open");
        }

        if (node.recoveryAttempts >= this.policy.maxRetries) {
            this.log(nodeId, "RECOVERY_EXHAUSTED", "Retry limit reached");
            return false;
        }

        if (
            this.healthyReplicaCount(nodeId) <
            this.policy.minimumHealthyReplicas
        ) {
            this.log(
                nodeId,
                "RECOVERY_DEFERRED",
                "Insufficient healthy replicas"
            );

            return false;
        }

        if (Date.now() < node.nextRecoveryAt) {
            throw new FaultToleranceError("Recovery backoff is active");
        }

        if (typeof restartOperation !== "function") {
            throw new TypeError("Restart operation must be a function");
        }

        this.recoveryLocks.add(nodeId);

        node.state = State.RECOVERING;
        node.recoveryAttempts++;

        this.log(
            nodeId,
            "RECOVERY_STARTED",
            `Attempt ${node.recoveryAttempts}`
        );

        try {
            const result = await restartOperation(node);

            if (result !== true) {
                throw new FaultToleranceError("Restart operation unsuccessful");
            }

            node.state = State.HEALTHY;
            node.missedHeartbeats = 0;
            node.recoveryAttempts = 0;
            node.lastHeartbeat = Date.now();

            breaker.recordSuccess();

            this.log(nodeId, "RECOVERY_SUCCESS", "Node restarted");
            return true;
        } catch (error) {
            node.state = State.FAILED;

            const delay = this.policy.backoff(node.recoveryAttempts);

            node.nextRecoveryAt = Date.now() + delay;

            breaker.recordFailure();

            this.log(
                nodeId,
                "RECOVERY_FAILURE",
                `${error.message}; retry delay ${delay}ms`
            );

            return false;
        } finally {
            this.recoveryLocks.delete(nodeId);
        }
    }

    disableNode(nodeId) {
        const node = this.nodes.get(nodeId);

        if (!node) {
            throw new FaultToleranceError("Unknown node");
        }

        if (this.recoveryLocks.has(nodeId)) {
            throw new FaultToleranceError("Cannot disable during recovery");
        }

        node.state = State.DISABLED;

        this.log(nodeId, "DISABLED", "Administrative action");
    }

    getHealthReport() {
        const report = {
            total: this.nodes.size,
            healthy: 0,
            suspect: 0,
            failed: 0,
            recovering: 0,
            disabled: 0
        };

        for (const node of this.nodes.values()) {
            switch (node.state) {
                case State.HEALTHY:
                    report.healthy++;
                    break;
                case State.SUSPECT:
                    report.suspect++;
                    break;
                case State.FAILED:
                    report.failed++;
                    break;
                case State.RECOVERING:
                    report.recovering++;
                    break;
                case State.DISABLED:
                    report.disabled++;
                    break;
            }
        }

        report.availabilityPercent = report.total
            ? Number((report.healthy / report.total * 100).toFixed(2))
            : 0;

        report.serviceAvailable =
            report.healthy >= this.policy.minimumHealthyReplicas;

        return report;
    }

    async exportEvents(filename = "cluster-events.json") {
        const data = JSON.stringify(this.events, null, 2);
        await fs.writeFile(filename, data, {
            encoding: "utf8",
            mode: 0o600
        });
    }

    shutdown() {
        this.closed = true;
        this.removeAllListeners();
    }
}

async function main() {
    const policy = new RecoveryPolicy({
        timeoutMs: 1000,
        failureThreshold: 2,
        maxRetries: 3,
        initialBackoffMs: 100,
        maxBackoffMs: 1000,
        minimumHealthyReplicas: 2
    });

    const cluster = new ClusterMonitor(policy);

    cluster.on("cluster-event", event => {
        console.log(
            `[${event.type}] ${event.nodeId}: ${event.details}`
        );
    });

    cluster.registerNode("API-01", "api-server-01");
    cluster.registerNode("API-02", "api-server-02");
    cluster.registerNode("API-03", "api-server-03");

    const node = cluster.nodes.get("API-03");

    // Simulate two consecutive failed heartbeat observations.
    cluster.detectFailures(node.lastHeartbeat + 2000);
    cluster.detectFailures(node.lastHeartbeat + 3000);

    if (node.state !== State.FAILED) {
        throw new Error("Failure detection test failed");
    }

    // Restart operation is asynchronous and can fail.
    const recovered = await cluster.recover(
        "API-03",
        async () => {
            await new Promise(resolve => setTimeout(resolve, 20));
            return true;
        }
    );

    if (!recovered) {
        throw new Error("Recovery test failed");
    }

    await cluster.heartbeat("API-03");

    const report = cluster.getHealthReport();

    console.log("\nCluster health:");
    console.log(JSON.stringify(report, null, 2));

    if (report.healthy !== 3) {
        throw new Error("Cluster health assertion failed");
    }

    await cluster.exportEvents();

    cluster.shutdown();

    console.log("\nAll fault-tolerance tests passed.");
}

main().catch(error => {
    console.error("Cluster simulation failed:", error.message);
    process.exitCode = 1;
});
