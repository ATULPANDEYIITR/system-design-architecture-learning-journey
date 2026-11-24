"use strict";

/*
 * High Availability Architecture
 * Event-driven monitoring, quorum election, request routing,
 * circuit breakers, failover and recovery.
 *
 * Runtime: Node.js 18+
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

const NodeStatus = Object.freeze({
    HEALTHY: "HEALTHY",
    FAILED: "FAILED",
    MAINTENANCE: "MAINTENANCE"
});

const CircuitState = Object.freeze({
    CLOSED: "CLOSED",
    OPEN: "OPEN",
    HALF_OPEN: "HALF_OPEN"
});

class HAError extends Error {}

class InfrastructureNode {
    constructor({ id, zone, capacity, role }) {
        if (!id || !zone || !role) {
            throw new HAError("Node identity, zone and role are required");
        }

        if (!Number.isInteger(capacity) || capacity <= 0) {
            throw new HAError("Capacity must be a positive integer");
        }

        this.id = id;
        this.zone = zone;
        this.capacity = capacity;
        this.role = role;
        this.status = NodeStatus.HEALTHY;
        this.activeRequests = 0;
        this.completedRequests = 0;
        this.lastHeartbeat = Date.now();
        this.heartbeatFailures = 0;
    }

    get availableCapacity() {
        if (this.status !== NodeStatus.HEALTHY) return 0;
        return this.capacity - this.activeRequests;
    }

    heartbeat() {
        if (this.status !== NodeStatus.HEALTHY) {
            this.heartbeatFailures++;
            return false;
        }

        this.lastHeartbeat = Date.now();
        this.heartbeatFailures = 0;
        return true;
    }

    acquire() {
        if (this.availableCapacity <= 0) return false;
        this.activeRequests++;
        return true;
    }

    release() {
        if (this.activeRequests <= 0) {
            throw new HAError("Request counter underflow");
        }

        this.activeRequests--;
        this.completedRequests++;
    }

    fail() {
        this.status = NodeStatus.FAILED;
        this.activeRequests = 0;
    }

    recover() {
        this.status = NodeStatus.HEALTHY;
        this.activeRequests = 0;
        this.heartbeat();
    }
}

class CircuitBreaker {
    constructor({ failureThreshold = 3, resetTimeoutMs = 5000 } = {}) {
        if (failureThreshold < 1 || resetTimeoutMs < 1) {
            throw new HAError("Invalid circuit breaker configuration");
        }

        this.failureThreshold = failureThreshold;
        this.resetTimeoutMs = resetTimeoutMs;
        this.failureCount = 0;
        this.state = CircuitState.CLOSED;
        this.openedAt = 0;
    }

    canExecute(now = Date.now()) {
        if (this.state === CircuitState.OPEN) {
            if (now - this.openedAt < this.resetTimeoutMs) {
                return false;
            }

            this.state = CircuitState.HALF_OPEN;
            return true;
        }

        return true;
    }

    success() {
        this.failureCount = 0;
        this.state = CircuitState.CLOSED;
    }

    failure(now = Date.now()) {
        this.failureCount++;

        if (
            this.state === CircuitState.HALF_OPEN ||
            this.failureCount >= this.failureThreshold
        ) {
            this.state = CircuitState.OPEN;
            this.openedAt = now;
        }
    }
}

class QuorumManager {
    constructor(memberIds) {
        if (
            !Array.isArray(memberIds) ||
            memberIds.length < 3 ||
            memberIds.length % 2 === 0 ||
            new Set(memberIds).size !== memberIds.length
        ) {
            throw new HAError("Quorum requires unique, odd membership of at least three");
        }

        this.memberIds = [...memberIds];
        this.term = 0;
        this.leaderId = null;
        this.requiredVotes = Math.floor(memberIds.length / 2) + 1;
    }

    elect(nodes) {
        const votes = this.memberIds.filter(id => {
            const node = nodes.get(id);
            return node && node.status === NodeStatus.HEALTHY;
        });

        if (votes.length < this.requiredVotes) {
            this.leaderId = null;
            return null;
        }

        // Term numbers fence off decisions from previous leadership terms.
        this.term++;
        this.leaderId = votes.sort()[0];

        return {
            leaderId: this.leaderId,
            term: this.term,
            votes: votes.length
        };
    }

    hasQuorum(nodes) {
        const votes = this.memberIds.filter(id => {
            const node = nodes.get(id);
            return node && node.status === NodeStatus.HEALTHY;
        }).length;

        return votes >= this.requiredVotes;
    }
}

class AvailabilityPlatform extends EventEmitter {
    constructor() {
        super();

        this.nodes = new Map();
        this.services = new Map();
        this.quorum = null;
        this.circuits = new Map();
        this.metrics = {
            total: 0,
            successful: 0,
            failed: 0,
            failovers: 0
        };
    }

    addNode(config) {
        const node = new InfrastructureNode(config);

        if (this.nodes.has(node.id)) {
            throw new HAError(`Duplicate node ${node.id}`);
        }

        this.nodes.set(node.id, node);
        this.emit("node:registered", node.id);
        return node;
    }

    addService({ id, replicas, minimumHealthy = 1 }) {
        if (!id || this.services.has(id)) {
            throw new HAError("Invalid or duplicate service");
        }

        if (!Array.isArray(replicas) || replicas.length === 0) {
            throw new HAError("Service requires replicas");
        }

        if (new Set(replicas).size !== replicas.length) {
            throw new HAError("Duplicate service replica");
        }

        if (
            !Number.isInteger(minimumHealthy) ||
            minimumHealthy < 1 ||
            minimumHealthy > replicas.length
        ) {
            throw new HAError("Invalid minimum replica count");
        }

        for (const id of replicas) {
            if (!this.nodes.has(id)) {
                throw new HAError(`Unknown node: ${id}`);
            }
        }

        this.services.set(id, {
            id,
            replicas: [...replicas],
            minimumHealthy
        });

        this.circuits.set(id, new CircuitBreaker());
    }

    configureQuorum(memberIds) {
        for (const id of memberIds) {
            if (!this.nodes.has(id)) {
                throw new HAError(`Unknown quorum member: ${id}`);
            }
        }

        this.quorum = new QuorumManager(memberIds);
        return this.quorum.elect(this.nodes);
    }

    healthyReplicas(serviceId) {
        const service = this.services.get(serviceId);

        if (!service) {
            throw new HAError(`Unknown service: ${serviceId}`);
        }

        return service.replicas
            .map(id => this.nodes.get(id))
            .filter(node => node.status === NodeStatus.HEALTHY);
    }

    serviceAvailable(serviceId) {
        const service = this.services.get(serviceId);

        return this.healthyReplicas(serviceId).length >=
            service.minimumHealthy;
    }

    async execute(serviceId, operation = async node => node.id) {
        const service = this.services.get(serviceId);

        if (!service) {
            throw new HAError("Unknown service");
        }

        this.metrics.total++;

        const circuit = this.circuits.get(serviceId);

        if (!circuit.canExecute()) {
            this.metrics.failed++;
            this.emit("request:rejected", {
                serviceId,
                reason: "Circuit breaker open"
            });
            return null;
        }

        const candidates = this.healthyReplicas(serviceId)
            .filter(node => node.availableCapacity > 0)
            .sort((a, b) => {
                const utilizationA = a.activeRequests / a.capacity;
                const utilizationB = b.activeRequests / b.capacity;

                return utilizationA - utilizationB ||
                    a.id.localeCompare(b.id);
            });

        for (const node of candidates) {
            if (!node.acquire()) continue;

            try {
                const result = await operation(node);

                circuit.success();
                this.metrics.successful++;

                this.emit("request:completed", {
                    serviceId,
                    nodeId: node.id
                });

                return result;
            } catch (error) {
                circuit.failure();
                this.emit("request:failed", {
                    serviceId,
                    nodeId: node.id,
                    error: error.message
                });

                // Retry another replica only for this failed attempt.
            } finally {
                node.release();
            }
        }

        this.metrics.failed++;

        if (candidates.length === 0) {
            circuit.failure();
        }

        this.emit("service:unavailable", serviceId);
        return null;
    }

    failNode(nodeId) {
        const node = this.nodes.get(nodeId);

        if (!node) throw new HAError("Unknown node");
        if (node.status === NodeStatus.FAILED) return;

        node.fail();

        this.emit("node:failed", nodeId);

        for (const [serviceId, service] of this.services) {
            if (!service.replicas.includes(nodeId)) continue;

            this.metrics.failovers++;

            this.emit("service:failover", {
                serviceId,
                available: this.serviceAvailable(serviceId)
            });
        }

        if (this.quorum) {
            const previousLeader = this.quorum.leaderId;

            if (this.quorum.hasQuorum(this.nodes)) {
                const election = this.quorum.elect(this.nodes);

                if (previousLeader !== election.leaderId) {
                    this.emit("leader:changed", election);
                }
            } else {
                this.quorum.leaderId = null;
                this.emit("quorum:lost");
            }
        }
    }

    recoverNode(nodeId) {
        const node = this.nodes.get(nodeId);

        if (!node) throw new HAError("Unknown node");

        node.recover();
        this.emit("node:recovered", nodeId);

        if (this.quorum && !this.quorum.hasQuorum(this.nodes)) {
            this.quorum.elect(this.nodes);
        }
    }

    simulateZoneFailure(zone) {
        const affected = [...this.nodes.values()].filter(
            node => node.zone === zone &&
                node.status === NodeStatus.HEALTHY
        );

        if (affected.length === 0) {
            throw new HAError("No healthy nodes in the specified zone");
        }

        for (const node of affected) {
            this.failNode(node.id);
        }
    }

    analyzeFailureDomains() {
        const risks = [];

        for (const service of this.services.values()) {
            const zones = new Set(
                service.replicas.map(id => this.nodes.get(id).zone)
            );

            for (const zone of zones) {
                const surviving = service.replicas.filter(id => {
                    const node = this.nodes.get(id);

                    return node.zone !== zone &&
                        node.status === NodeStatus.HEALTHY;
                }).length;

                if (surviving < service.minimumHealthy) {
                    risks.push({
                        service: service.id,
                        failureDomain: zone,
                        surviving,
                        required: service.minimumHealthy
                    });
                }
            }
        }

        return risks;
    }

    report() {
        const serviceReport = {};

        for (const serviceId of this.services.keys()) {
            serviceReport[serviceId] = {
                healthyReplicas: this.healthyReplicas(serviceId).length,
                available: this.serviceAvailable(serviceId)
            };
        }

        return {
            services: serviceReport,
            quorum: this.quorum
                ? this.quorum.hasQuorum(this.nodes)
                : null,
            leader: this.quorum?.leaderId ?? null,
            term: this.quorum?.term ?? null,
            metrics: { ...this.metrics },
            failureDomainRisks: this.analyzeFailureDomains()
        };
    }
}

async function main() {
    const platform = new AvailabilityPlatform();

    for (const [id, zone, role, capacity] of [
        ["app-1", "zone-a", "application", 100],
        ["app-2", "zone-b", "application", 100],
        ["app-3", "zone-c", "application", 100],
        ["db-1", "zone-a", "database", 200],
        ["db-2", "zone-b", "database", 200],
        ["db-3", "zone-c", "database", 200],
        ["control-1", "zone-a", "control", 50],
        ["control-2", "zone-b", "control", 50],
        ["control-3", "zone-c", "control", 50]
    ]) {
        platform.addNode({ id, zone, role, capacity });
    }

    platform.addService({
        id: "application",
        replicas: ["app-1", "app-2", "app-3"],
        minimumHealthy: 2
    });

    platform.addService({
        id: "database",
        replicas: ["db-1", "db-2", "db-3"],
        minimumHealthy: 2
    });

    platform.on("node:failed", id => {
        console.log(`NODE FAILURE: ${id}`);
    });

    platform.on("service:failover", event => {
        console.log("SERVICE FAILOVER:", event);
    });

    platform.on("leader:changed", event => {
        console.log("LEADER ELECTED:", event);
    });

    platform.on("quorum:lost", () => {
        console.error("CRITICAL: Control-plane quorum lost");
    });

    platform.on("request:failed", event => {
        console.error("Replica operation failed:", event);
    });

    platform.configureQuorum([
        "control-1",
        "control-2",
        "control-3"
    ]);

    console.log("\nInitial requests");

    for (let i = 0; i < 5; i++) {
        const result = await platform.execute(
            "application",
            async node => ({
                requestId: crypto.randomUUID(),
                servedBy: node.id
            })
        );

        console.log(result);
    }

    console.log("\nSimulating application-node failure");
    platform.failNode("app-1");

    await platform.execute("application");

    console.log("\nRecovering failed node");
    platform.recoverNode("app-1");

    console.log("\nSimulating zone failure");
    platform.simulateZoneFailure("zone-a");

    console.log("\nFinal infrastructure report");
    console.log(JSON.stringify(platform.report(), null, 2));

    if (!platform.quorum.hasQuorum(platform.nodes)) {
        console.error("Control plane is unavailable");
        process.exitCode = 1;
    }
}

main().catch(error => {
    console.error("Platform execution failed:", error.message);
    process.exitCode = 1;
});
