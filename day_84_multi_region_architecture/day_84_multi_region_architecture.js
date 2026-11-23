"use strict";

/*
 * Multi-Region Architecture
 * Event-driven regional health monitoring and failover controller.
 *
 * Runtime: Node.js 18+
 *
 * Engineering focus:
 * - Asynchronous health events
 * - Circuit breakers
 * - Regional traffic routing
 * - Leader epochs and fencing
 * - Replication monitoring
 * - Failover coordination
 * - Recovery and controlled failback
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");


const RegionState = Object.freeze({
    HEALTHY: "HEALTHY",
    DEGRADED: "DEGRADED",
    DOWN: "DOWN",
    RECOVERING: "RECOVERING"
});

const RegionRole = Object.freeze({
    PRIMARY: "PRIMARY",
    SECONDARY: "SECONDARY",
    DISABLED: "DISABLED"
});


class ArchitectureError extends Error {
    constructor(message) {
        super(message);
        this.name = "ArchitectureError";
    }
}


class Region {

    constructor({
        id,
        location,
        capacity,
        latencyMs = 30,
        replicationLagMs = 0,
        role = RegionRole.SECONDARY
    }) {
        if (!id || !location) {
            throw new ArchitectureError(
                "Region ID and location are required."
            );
        }

        if (!Number.isInteger(capacity) || capacity <= 0) {
            throw new ArchitectureError(
                "Capacity must be a positive integer."
            );
        }

        this.id = id;
        this.location = location;
        this.capacity = capacity;
        this.latencyMs = latencyMs;
        this.replicationLagMs = replicationLagMs;
        this.role = role;
        this.state = RegionState.HEALTHY;
        this.load = 0;
        this.dataVersion = 0;
        this.lastHeartbeat = Date.now();
    }

    updateMetrics({
        state = this.state,
        latencyMs = this.latencyMs,
        replicationLagMs = this.replicationLagMs
    }) {
        if (!Object.values(RegionState).includes(state)) {
            throw new ArchitectureError("Invalid region state.");
        }

        if (
            !Number.isFinite(latencyMs) ||
            latencyMs < 0 ||
            !Number.isFinite(replicationLagMs) ||
            replicationLagMs < 0
        ) {
            throw new ArchitectureError("Invalid regional metrics.");
        }

        this.state = state;
        this.latencyMs = latencyMs;
        this.replicationLagMs = replicationLagMs;
        this.lastHeartbeat = Date.now();
    }

    get availableCapacity() {
        return this.capacity - this.load;
    }
}


class CircuitBreaker {

    constructor({
        failureThreshold = 3,
        resetTimeoutMs = 10000
    } = {}) {
        this.failureThreshold = failureThreshold;
        this.resetTimeoutMs = resetTimeoutMs;
        this.failures = 0;
        this.openedAt = null;
    }

    recordFailure() {
        this.failures++;

        if (this.failures >= this.failureThreshold) {
            this.openedAt = Date.now();
        }
    }

    recordSuccess() {
        this.failures = 0;
        this.openedAt = null;
    }

    canAttempt() {
        if (this.openedAt === null) {
            return true;
        }

        return Date.now() - this.openedAt >= this.resetTimeoutMs;
    }
}


class RegionHealthMonitor extends EventEmitter {

    constructor() {
        super();
        this.monitoredRegions = new Map();
    }

    register(region) {
        if (this.monitoredRegions.has(region.id)) {
            throw new ArchitectureError(
                "Region already monitored."
            );
        }

        this.monitoredRegions.set(region.id, region);
    }

    publishHealth(regionId, metrics) {
        const region = this.monitoredRegions.get(regionId);

        if (!region) {
            throw new ArchitectureError("Unknown region.");
        }

        const previousState = region.state;

        region.updateMetrics(metrics);

        this.emit("health", {
            regionId,
            previousState,
            currentState: region.state,
            timestamp: Date.now()
        });

        if (region.state === RegionState.DOWN) {
            this.emit("regionalFailure", {
                regionId,
                timestamp: Date.now()
            });
        }
    }
}


class MultiRegionController extends EventEmitter {

    constructor({
        maximumReplicationLagMs = 5000,
        maximumLatencyMs = 250,
        minimumFreeCapacity = 0.20
    } = {}) {

        super();

        this.regions = new Map();
        this.primaryRegionId = null;

        this.maximumReplicationLagMs = maximumReplicationLagMs;
        this.maximumLatencyMs = maximumLatencyMs;
        this.minimumFreeCapacity = minimumFreeCapacity;

        this.leaderEpoch = 1;
        this.failoverInProgress = false;

        this.breakers = new Map();
        this.idempotencyKeys = new Map();

        this.healthMonitor = new RegionHealthMonitor();

        this.healthMonitor.on(
            "regionalFailure",
            event => {
                this.emit("regionalFailure", event);
            }
        );

        this.healthMonitor.on(
            "health",
            event => {
                this.emit("healthChanged", event);
            }
        );
    }

    register(region) {
        if (this.regions.has(region.id)) {
            throw new ArchitectureError(
                "Duplicate regional identifier."
            );
        }

        if (region.role === RegionRole.PRIMARY) {
            if (this.primaryRegionId !== null) {
                throw new ArchitectureError(
                    "Multiple primaries are not allowed."
                );
            }

            this.primaryRegionId = region.id;
        }

        this.regions.set(region.id, region);

        this.healthMonitor.register(region);

        this.breakers.set(
            region.id,
            new CircuitBreaker()
        );
    }

    getRegion(id) {
        const region = this.regions.get(id);

        if (!region) {
            throw new ArchitectureError(
                `Unknown region: ${id}`
            );
        }

        return region;
    }

    evaluateEligibility(region) {

        if (region.state !== RegionState.HEALTHY) {
            return {
                eligible: false,
                reason: "Region is not healthy."
            };
        }

        if (region.latencyMs > this.maximumLatencyMs) {
            return {
                eligible: false,
                reason: "Latency threshold exceeded."
            };
        }

        if (
            region.replicationLagMs >
            this.maximumReplicationLagMs
        ) {
            return {
                eligible: false,
                reason: "Replication lag exceeds RPO."
            };
        }

        const freeRatio =
            region.availableCapacity / region.capacity;

        if (freeRatio < this.minimumFreeCapacity) {
            return {
                eligible: false,
                reason: "Insufficient spare capacity."
            };
        }

        return {
            eligible: true,
            reason: "All policies satisfied."
        };
    }

    rankCandidates() {

        return [...this.regions.values()]
            .filter(region => region.id !== this.primaryRegionId)
            .filter(region => {
                return this.evaluateEligibility(region).eligible;
            })
            .sort((a, b) => {
                const scoreA =
                    a.replicationLagMs * 10 + a.latencyMs;

                const scoreB =
                    b.replicationLagMs * 10 + b.latencyMs;

                return scoreA - scoreB;
            });
    }

    async promote(targetId) {

        if (this.failoverInProgress) {
            throw new ArchitectureError(
                "Another failover is already running."
            );
        }

        this.failoverInProgress = true;

        try {
            const target = this.getRegion(targetId);

            const evaluation =
                this.evaluateEligibility(target);

            if (!evaluation.eligible) {
                throw new ArchitectureError(
                    evaluation.reason
                );
            }

            const previousPrimary =
                this.getRegion(this.primaryRegionId);

            const oldEpoch = this.leaderEpoch;

            /*
             * In production, acquire a distributed fencing lease
             * before promoting. The epoch must be stored in a
             * strongly consistent coordination system.
             */
            const nextEpoch = oldEpoch + 1;

            if (nextEpoch <= oldEpoch) {
                throw new ArchitectureError(
                    "Leader epoch validation failed."
                );
            }

            // Promotion changes the simulated routing authority.
            previousPrimary.role = RegionRole.SECONDARY;

            target.role = RegionRole.PRIMARY;

            this.primaryRegionId = target.id;
            this.leaderEpoch = nextEpoch;

            const event = {
                eventId: crypto.randomUUID(),
                previousPrimary: previousPrimary.id,
                newPrimary: target.id,
                leaderEpoch: this.leaderEpoch,
                rpoMs: target.replicationLagMs,
                timestamp: new Date().toISOString()
            };

            this.emit("failoverCompleted", event);

            return event;

        } finally {
            this.failoverInProgress = false;
        }
    }

    async route({
        requestId,
        operation = "READ"
    }) {

        if (!requestId || typeof requestId !== "string") {
            throw new ArchitectureError(
                "A valid request ID is required."
            );
        }

        if (!["READ", "WRITE"].includes(operation)) {
            throw new ArchitectureError(
                "Unsupported operation."
            );
        }

        const existing = this.idempotencyKeys.get(requestId);

        if (existing) {
            return existing;
        }

        const region = this.getRegion(this.primaryRegionId);

        const breaker = this.breakers.get(region.id);

        if (!breaker.canAttempt()) {
            throw new ArchitectureError(
                "Regional circuit breaker is open."
            );
        }

        if (region.state !== RegionState.HEALTHY) {
            breaker.recordFailure();

            throw new ArchitectureError(
                "Primary region is unavailable."
            );
        }

        if (region.availableCapacity <= 0) {
            breaker.recordFailure();

            throw new ArchitectureError(
                "Regional capacity exhausted."
            );
        }

        const epoch = this.leaderEpoch;

        // Simulate an asynchronous regional request.
        await Promise.resolve();

        // Reject work if leadership changed during processing.
        if (epoch !== this.leaderEpoch) {
            throw new ArchitectureError(
                "Stale leader epoch. Retry against the new primary."
            );
        }

        if (region.state !== RegionState.HEALTHY) {
            breaker.recordFailure();

            throw new ArchitectureError(
                "Regional failure during request processing."
            );
        }

        region.load++;

        if (operation === "WRITE") {
            region.dataVersion++;
        }

        const result = Object.freeze({
            requestId,
            region: region.id,
            operation,
            dataVersion: region.dataVersion,
            leaderEpoch: epoch,
            processedAt: new Date().toISOString()
        });

        this.idempotencyKeys.set(requestId, result);

        breaker.recordSuccess();

        this.emit("requestProcessed", result);

        return result;
    }

    async synchronizeStandbyRegions() {

        const primary = this.getRegion(this.primaryRegionId);

        for (const region of this.regions.values()) {

            if (region.id === primary.id) {
                continue;
            }

            if (region.state !== RegionState.HEALTHY) {
                continue;
            }

            // Demonstrates successful replication only.
            region.dataVersion = primary.dataVersion;
            region.replicationLagMs = 0;
        }

        this.emit("replicationCompleted", {
            source: primary.id,
            dataVersion: primary.dataVersion
        });
    }

    async recoverRegion(regionId) {

        const region = this.getRegion(regionId);

        region.state = RegionState.RECOVERING;

        const primary = this.getRegion(this.primaryRegionId);

        region.dataVersion = primary.dataVersion;
        region.replicationLagMs = 0;
        region.load = 0;
        region.state = RegionState.HEALTHY;

        // Recovery does not automatically restore primary authority.
        region.role = RegionRole.SECONDARY;

        this.emit("regionRecovered", {
            regionId,
            dataVersion: region.dataVersion
        });
    }

    async failback(regionId) {

        const target = this.getRegion(regionId);
        const primary = this.getRegion(this.primaryRegionId);

        if (target.dataVersion !== primary.dataVersion) {
            throw new ArchitectureError(
                "Failback requires synchronized data."
            );
        }

        return this.promote(regionId);
    }

    snapshot() {
        return {
            primaryRegion: this.primaryRegionId,
            leaderEpoch: this.leaderEpoch,
            regions: [...this.regions.values()].map(region => ({
                id: region.id,
                state: region.state,
                role: region.role,
                latencyMs: region.latencyMs,
                replicationLagMs: region.replicationLagMs,
                load: region.load,
                capacity: region.capacity,
                dataVersion: region.dataVersion
            }))
        };
    }
}


async function main() {

    const controller = new MultiRegionController({
        maximumReplicationLagMs: 5000,
        maximumLatencyMs: 250,
        minimumFreeCapacity: 0.20
    });

    const regions = [
        new Region({
            id: "ap-south-1",
            location: "Mumbai",
            capacity: 1000,
            role: RegionRole.PRIMARY
        }),

        new Region({
            id: "ap-south-2",
            location: "Hyderabad",
            capacity: 1000,
            latencyMs: 45
        }),

        new Region({
            id: "eu-west-1",
            location: "Ireland",
            capacity: 1200,
            latencyMs: 120
        })
    ];

    for (const region of regions) {
        controller.register(region);
    }

    controller.on("regionalFailure", event => {
        console.log("Regional failure:", event.regionId);
    });

    controller.on("failoverCompleted", event => {
        console.log("Failover event:", event);
    });

    controller.on("requestProcessed", event => {
        console.log(
            `Processed ${event.requestId} in ${event.region}`
        );
    });

    console.log("\nINITIAL STATE");
    console.log(JSON.stringify(controller.snapshot(), null, 2));

    console.log("\nNORMAL TRAFFIC");

    await controller.route({
        requestId: "ORDER-1001",
        operation: "WRITE"
    });

    await controller.synchronizeStandbyRegions();

    console.log("\nSIMULATED REGIONAL OUTAGE");

    controller.healthMonitor.publishHealth(
        "ap-south-1",
        {
            state: RegionState.DOWN
        }
    );

    const candidates = controller.rankCandidates();

    if (candidates.length === 0) {
        throw new ArchitectureError(
            "No eligible failover destination."
        );
    }

    await controller.promote(candidates[0].id);

    console.log("\nTRAFFIC AFTER FAILOVER");

    await controller.route({
        requestId: "ORDER-1002",
        operation: "WRITE"
    });

    console.log("\nREGIONAL RECOVERY");

    await controller.recoverRegion("ap-south-1");

    await controller.synchronizeStandbyRegions();

    await controller.failback("ap-south-1");

    console.log("\nFINAL STATE");

    console.log(
        JSON.stringify(controller.snapshot(), null, 2)
    );

    // Verify idempotency.
    const first = await controller.route({
        requestId: "ORDER-1003",
        operation: "READ"
    });

    const duplicate = await controller.route({
        requestId: "ORDER-1003",
        operation: "READ"
    });

    if (first !== duplicate) {
        throw new ArchitectureError(
            "Idempotency validation failed."
        );
    }

    console.log("\nAll event-driven workflow checks passed.");
}


main().catch(error => {
    console.error("Architecture failure:", error.message);
    process.exitCode = 1;
});
