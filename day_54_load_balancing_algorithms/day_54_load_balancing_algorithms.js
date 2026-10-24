'use strict';

/*
 * Load balancing model using three distinct policies:
 *
 * 1. Round robin
 * 2. Weighted round robin
 * 3. Least connections
 *
 * The implementation uses JavaScript-specific event-driven behavior:
 * request dispatch emits events, while asynchronous request completion
 * changes the connection state used by least-connections selection.
 */

const { EventEmitter } = require('node:events');
const assert = require('node:assert/strict');

const Algorithm = Object.freeze({
    ROUND_ROBIN: 'round-robin',
    WEIGHTED_ROUND_ROBIN: 'weighted-round-robin',
    LEAST_CONNECTIONS: 'least-connections'
});

class Backend {
    constructor(name, weight = 1) {
        if (typeof name !== 'string' || name.trim() === '') {
            throw new TypeError('Backend name must be a non-empty string');
        }
        if (!Number.isInteger(weight) || weight <= 0) {
            throw new RangeError('Backend weight must be a positive integer');
        }

        this.name = name;
        this.weight = weight;
        this.healthy = true;
        this.activeConnections = 0;
        this.totalRequests = 0;
        this.completedRequests = 0;
        this.failedRequests = 0;
    }

    start() {
        if (!this.healthy) {
            throw new Error(`Backend ${this.name} is unhealthy`);
        }

        this.activeConnections += 1;
        this.totalRequests += 1;
    }

    finish(success = true) {
        if (this.activeConnections <= 0) {
            throw new Error(`Backend ${this.name} has no active connection`);
        }

        this.activeConnections -= 1;

        if (success) {
            this.completedRequests += 1;
        } else {
            this.failedRequests += 1;
        }
    }
}

class LoadBalancer extends EventEmitter {
    constructor(backends, algorithm) {
        super();

        if (!Array.isArray(backends) || backends.length === 0) {
            throw new Error('At least one backend is required');
        }

        const names = new Set(backends.map((backend) => backend.name));
        if (names.size !== backends.length) {
            throw new Error('Backend names must be unique');
        }

        if (!Object.values(Algorithm).includes(algorithm)) {
            throw new Error(`Unsupported algorithm: ${algorithm}`);
        }

        this.backends = backends;
        this.algorithm = algorithm;
        this.roundRobinIndex = 0;
        this.weightedSequence = [];
        this.weightedIndex = 0;

        this.rebuildWeightedSequence();
    }

    healthyBackends() {
        return this.backends.filter((backend) => backend.healthy);
    }

    rebuildWeightedSequence() {
        this.weightedSequence = [];

        for (const backend of this.backends) {
            for (let i = 0; i < backend.weight; i += 1) {
                this.weightedSequence.push(backend);
            }
        }

        this.weightedIndex = 0;
    }

    setHealth(name, healthy) {
        const backend = this.getBackend(name);
        backend.healthy = Boolean(healthy);
        this.rebuildWeightedSequence();

        this.emit('healthChanged', {
            backend: backend.name,
            healthy: backend.healthy
        });
    }

    getBackend(name) {
        const backend = this.backends.find((item) => item.name === name);

        if (!backend) {
            throw new Error(`Unknown backend: ${name}`);
        }

        return backend;
    }

    selectBackend() {
        const healthy = this.healthyBackends();

        if (healthy.length === 0) {
            throw new Error('No healthy backend is available');
        }

        if (this.algorithm === Algorithm.ROUND_ROBIN) {
            const backend = healthy[this.roundRobinIndex % healthy.length];
            this.roundRobinIndex += 1;
            return backend;
        }

        if (this.algorithm === Algorithm.WEIGHTED_ROUND_ROBIN) {
            const healthyNames = new Set(healthy.map((backend) => backend.name));
            const available = this.weightedSequence.filter(
                (backend) => healthyNames.has(backend.name)
            );

            if (available.length === 0) {
                throw new Error('Weighted schedule contains no healthy backend');
            }

            const backend = available[this.weightedIndex % available.length];
            this.weightedIndex += 1;
            return backend;
        }

        return healthy.reduce((best, current) => {
            if (current.activeConnections < best.activeConnections) {
                return current;
            }

            if (
                current.activeConnections === best.activeConnections &&
                current.weight > best.weight
            ) {
                return current;
            }

            return best;
        });
    }

    dispatch(requestId) {
        if (!Number.isInteger(requestId) || requestId <= 0) {
            throw new RangeError('Request ID must be a positive integer');
        }

        const backend = this.selectBackend();
        backend.start();

        this.emit('requestAssigned', {
            requestId,
            backend: backend.name
        });

        return backend;
    }

    complete(name, success = true) {
        const backend = this.getBackend(name);
        backend.finish(success);

        this.emit('requestCompleted', {
            backend: backend.name,
            success
        });
    }

    statistics() {
        return this.backends.map((backend) => ({
            name: backend.name,
            weight: backend.weight,
            healthy: backend.healthy,
            activeConnections: backend.activeConnections,
            totalRequests: backend.totalRequests,
            completedRequests: backend.completedRequests,
            failedRequests: backend.failedRequests
        }));
    }
}

function countDistribution(algorithm, weights, requestCount) {
    const balancer = new LoadBalancer(
        [
            new Backend('server-a', weights[0]),
            new Backend('server-b', weights[1]),
            new Backend('server-c', weights[2])
        ],
        algorithm
    );

    for (let requestId = 1; requestId <= requestCount; requestId += 1) {
        const backend = balancer.dispatch(requestId);
        balancer.complete(backend.name);
    }

    return Object.fromEntries(
        balancer.statistics().map((item) => [item.name, item.totalRequests])
    );
}

async function asynchronousSimulation() {
    const balancer = new LoadBalancer(
        [
            new Backend('api-a', 1),
            new Backend('api-b', 2),
            new Backend('api-c', 3)
        ],
        Algorithm.LEAST_CONNECTIONS
    );

    balancer.on('requestAssigned', (event) => {
        console.log(`Request ${event.requestId} -> ${event.backend}`);
    });

    balancer.on('healthChanged', (event) => {
        console.log(
            `Health change: ${event.backend} = ${event.healthy ? 'healthy' : 'unhealthy'}`
        );
    });

    const pending = [];

    for (let requestId = 1; requestId <= 12; requestId += 1) {
        const backend = balancer.dispatch(requestId);

        const delay = 20 + ((requestId * 17) % 50);

        pending.push(
            new Promise((resolve) => {
                setTimeout(() => {
                    balancer.complete(backend.name, true);
                    resolve();
                }, delay);
            })
        );
    }

    await Promise.all(pending);

    return balancer.statistics();
}

async function main() {
    const roundRobin = countDistribution(
        Algorithm.ROUND_ROBIN,
        [1, 1, 1],
        60
    );

    const weighted = countDistribution(
        Algorithm.WEIGHTED_ROUND_ROBIN,
        [1, 2, 3],
        60
    );

    assert.deepEqual(roundRobin, {
        'server-a': 20,
        'server-b': 20,
        'server-c': 20
    });

    assert.deepEqual(weighted, {
        'server-a': 10,
        'server-b': 20,
        'server-c': 30
    });

    console.log('Round robin:', roundRobin);
    console.log('Weighted round robin:', weighted);

    const failureBalancer = new LoadBalancer(
        [new Backend('primary', 2), new Backend('backup', 1)],
        Algorithm.WEIGHTED_ROUND_ROBIN
    );

    for (let i = 1; i <= 6; i += 1) {
        const backend = failureBalancer.dispatch(i);
        failureBalancer.complete(backend.name);
    }

    failureBalancer.setHealth('primary', false);

    for (let i = 7; i <= 9; i += 1) {
        const backend = failureBalancer.dispatch(i);
        failureBalancer.complete(backend.name);
    }

    console.log('After primary failure:', failureBalancer.statistics());

    console.log('Asynchronous least-connections simulation:');
    console.log(await asynchronousSimulation());
}

main().catch((error) => {
    console.error(`Load-balancer simulation failed: ${error.message}`);
    process.exitCode = 1;
});
