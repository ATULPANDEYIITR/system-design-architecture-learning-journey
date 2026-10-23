'use strict';

/*
 * Load balancer traffic distribution and health-check model.
 *
 * This implementation uses Node.js standard-library capabilities only.
 * It emphasizes event-driven health probes, asynchronous request simulation,
 * circuit-like backend removal, and policy evaluation.
 */

const { EventEmitter } = require('node:events');

const BackendState = Object.freeze({
    HEALTHY: 'healthy',
    UNHEALTHY: 'unhealthy'
});

const Strategy = Object.freeze({
    ROUND_ROBIN: 'round_robin',
    LEAST_CONNECTIONS: 'least_connections',
    WEIGHTED: 'weighted'
});

class Backend {
    constructor({
        id,
        host,
        port,
        weight = 1,
        maxConnections = 100,
        simulatedHealth = true,
        latencyMs = 25
    }) {
        if (!id || !id.trim()) {
            throw new TypeError('backend id is required');
        }
        if (!Number.isInteger(port) || port < 1 || port > 65535) {
            throw new RangeError('port must be between 1 and 65535');
        }
        if (!Number.isInteger(weight) || weight <= 0) {
            throw new RangeError('weight must be positive');
        }
        if (!Number.isInteger(maxConnections) || maxConnections <= 0) {
            throw new RangeError('maxConnections must be positive');
        }

        this.id = id;
        this.host = host;
        this.port = port;
        this.weight = weight;
        this.maxConnections = maxConnections;
        this.simulatedHealth = simulatedHealth;
        this.latencyMs = latencyMs;

        this.state = BackendState.HEALTHY;
        this.activeConnections = 0;
        this.totalRequests = 0;
        this.failedRequests = 0;
        this.consecutiveFailures = 0;
        this.consecutiveSuccesses = 0;
    }

    get address() {
        return `${this.host}:${this.port}`;
    }

    get capacityAvailable() {
        return this.activeConnections < this.maxConnections;
    }

    get available() {
        return this.state === BackendState.HEALTHY && this.capacityAvailable;
    }
}

class HealthMonitor extends EventEmitter {
    constructor({ failureThreshold = 2, recoveryThreshold = 2 } = {}) {
        super();

        if (failureThreshold <= 0 || recoveryThreshold <= 0) {
            throw new RangeError('health thresholds must be positive');
        }

        this.failureThreshold = failureThreshold;
        this.recoveryThreshold = recoveryThreshold;
    }

    async probe(backend) {
        await new Promise(resolve => setTimeout(resolve, 1));

        if (backend.simulatedHealth) {
            backend.consecutiveFailures = 0;
            backend.consecutiveSuccesses += 1;

            if (
                backend.state === BackendState.UNHEALTHY &&
                backend.consecutiveSuccesses >= this.recoveryThreshold
            ) {
                backend.state = BackendState.HEALTHY;
                this.emit('backendRecovered', backend);
            }

            return {
                backendId: backend.id,
                success: true,
                latencyMs: backend.latencyMs
            };
        }

        backend.consecutiveSuccesses = 0;
        backend.consecutiveFailures += 1;

        if (
            backend.consecutiveFailures >= this.failureThreshold &&
            backend.state !== BackendState.UNHEALTHY
        ) {
            backend.state = BackendState.UNHEALTHY;
            this.emit('backendFailed', backend);
        }

        return {
            backendId: backend.id,
            success: false,
            latencyMs: null
        };
    }

    async probeAll(backends) {
        return Promise.all(backends.map(backend => this.probe(backend)));
    }
}

class LoadBalancer extends EventEmitter {
    constructor(backends, {
        strategy = Strategy.ROUND_ROBIN,
        healthMonitor = new HealthMonitor()
    } = {}) {
        super();

        if (!Array.isArray(backends) || backends.length === 0) {
            throw new Error('at least one backend is required');
        }

        const ids = new Set(backends.map(backend => backend.id));
        if (ids.size !== backends.length) {
            throw new Error('backend IDs must be unique');
        }

        this.backends = backends;
        this.strategy = strategy;
        this.healthMonitor = healthMonitor;
        this.roundRobinIndex = 0;
        this.requestCount = 0;
        this.rejectedRequests = 0;

        this.healthMonitor.on('backendFailed', backend => {
            this.emit('backendUnavailable', {
                backendId: backend.id,
                reason: 'active health checks exceeded failure threshold'
            });
        });

        this.healthMonitor.on('backendRecovered', backend => {
            this.emit('backendAvailable', {
                backendId: backend.id
            });
        });
    }

    availableBackends() {
        return this.backends.filter(backend => backend.available);
    }

    chooseBackend() {
        const available = this.availableBackends();

        if (available.length === 0) {
            this.rejectedRequests += 1;
            throw new Error('no healthy backend has available capacity');
        }

        if (this.strategy === Strategy.LEAST_CONNECTIONS) {
            return [...available].sort((a, b) =>
                a.activeConnections - b.activeConnections ||
                b.weight - a.weight ||
                a.id.localeCompare(b.id)
            )[0];
        }

        if (this.strategy === Strategy.WEIGHTED) {
            const weighted = [];
            for (const backend of available) {
                for (let i = 0; i < backend.weight; i += 1) {
                    weighted.push(backend);
                }
            }

            return weighted[this.requestCount % weighted.length];
        }

        const availableIds = new Set(available.map(backend => backend.id));

        for (let offset = 0; offset < this.backends.length; offset += 1) {
            const index =
                (this.roundRobinIndex + offset) % this.backends.length;

            const backend = this.backends[index];

            if (availableIds.has(backend.id)) {
                this.roundRobinIndex = (index + 1) % this.backends.length;
                return backend;
            }
        }

        throw new Error('round-robin selection failed');
    }

    async route(request) {
        if (!request || typeof request.id !== 'string' || !request.id.trim()) {
            throw new TypeError('request must have a non-empty id');
        }

        this.requestCount += 1;
        const backend = this.chooseBackend();

        backend.activeConnections += 1;
        backend.totalRequests += 1;

        this.emit('requestRouted', {
            requestId: request.id,
            backendId: backend.id
        });

        return backend;
    }

    complete(backend) {
        if (!(backend instanceof Backend)) {
            throw new TypeError('backend must be a Backend instance');
        }

        if (backend.activeConnections <= 0) {
            throw new Error(`backend ${backend.id} has no active connection`);
        }

        backend.activeConnections -= 1;
    }

    recordPassiveFailure(backend) {
        backend.failedRequests += 1;
        backend.consecutiveFailures += 1;
        backend.consecutiveSuccesses = 0;

        if (
            backend.consecutiveFailures >=
            this.healthMonitor.failureThreshold
        ) {
            backend.state = BackendState.UNHEALTHY;
            this.emit('backendUnavailable', {
                backendId: backend.id,
                reason: 'passive request failures'
            });
        }
    }

    snapshot() {
        return this.backends.map(backend => ({
            id: backend.id,
            address: backend.address,
            state: backend.state,
            weight: backend.weight,
            activeConnections: backend.activeConnections,
            totalRequests: backend.totalRequests,
            failedRequests: backend.failedRequests
        }));
    }
}

function printSnapshot(loadBalancer, title) {
    console.log(`\n${title}`);

    for (const row of loadBalancer.snapshot()) {
        console.log(
            `${row.id.padEnd(10)} ` +
            `${row.state.padEnd(10)} ` +
            `connections=${String(row.activeConnections).padEnd(2)} ` +
            `requests=${String(row.totalRequests).padEnd(2)} ` +
            `failures=${row.failedRequests}`
        );
    }
}

async function demonstrate() {
    const backends = [
        new Backend({
            id: 'api-01',
            host: '10.20.0.11',
            port: 8080,
            weight: 1
        }),
        new Backend({
            id: 'api-02',
            host: '10.20.0.12',
            port: 8080,
            weight: 2
        }),
        new Backend({
            id: 'api-03',
            host: '10.20.0.13',
            port: 8080,
            weight: 1
        })
    ];

    const healthMonitor = new HealthMonitor({
        failureThreshold: 2,
        recoveryThreshold: 2
    });

    const loadBalancer = new LoadBalancer(backends, {
        strategy: Strategy.LEAST_CONNECTIONS,
        healthMonitor
    });

    loadBalancer.on('backendUnavailable', event => {
        console.log(
            `EVENT backend unavailable: ${event.backendId} (${event.reason})`
        );
    });

    loadBalancer.on('backendAvailable', event => {
        console.log(`EVENT backend recovered: ${event.backendId}`);
    });

    loadBalancer.on('requestRouted', event => {
        console.log(
            `ROUTE ${event.requestId} -> ${event.backendId}`
        );
    });

    console.log('Initial health checks');
    await healthMonitor.probeAll(backends);

    for (let i = 1; i <= 4; i += 1) {
        const backend = await loadBalancer.route({ id: `request-${i}` });
        loadBalancer.complete(backend);
    }

    printSnapshot(loadBalancer, 'Healthy pool');

    console.log('\nSimulating api-02 failure');
    backends[1].simulatedHealth = false;

    await healthMonitor.probeAll(backends);
    await healthMonitor.probeAll(backends);

    for (let i = 5; i <= 8; i += 1) {
        const backend = await loadBalancer.route({ id: `request-${i}` });
        loadBalancer.complete(backend);
    }

    printSnapshot(loadBalancer, 'After health-check isolation');

    console.log('\nSimulating api-02 recovery');
    backends[1].simulatedHealth = true;

    await healthMonitor.probeAll(backends);
    await healthMonitor.probeAll(backends);

    printSnapshot(loadBalancer, 'Recovered pool');

    console.log('\nCapacity failure demonstration');

    const limitedBackend = new Backend({
        id: 'limited',
        host: '10.30.0.11',
        port: 8080,
        maxConnections: 1
    });

    const limitedBalancer = new LoadBalancer([limitedBackend]);

    const active = await limitedBalancer.route({ id: 'long-request' });

    try {
        await limitedBalancer.route({ id: 'blocked-request' });
    } catch (error) {
        console.log(`EXPECTED FAILURE: ${error.message}`);
    }

    limitedBalancer.complete(active);
}

demonstrate().catch(error => {
    console.error(`Fatal error: ${error.message}`);
    process.exitCode = 1;
});
