'use strict';

/**
 * Service Discovery: Event-driven registry and policy engine.
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 *
 * Features:
 * - Event-driven registration and deregistration
 * - Lease-based instance expiration
 * - Health-state management
 * - Metadata and version filtering
 * - Weighted random endpoint selection
 * - Circuit-breaker behavior
 * - Concurrent asynchronous health probes
 * - Discovery caching with invalidation
 * - Graceful draining
 * - Structured event logging
 */

const { EventEmitter } = require('node:events');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs/promises');

const Health = Object.freeze({
    UNKNOWN: 'UNKNOWN',
    HEALTHY: 'HEALTHY',
    UNHEALTHY: 'UNHEALTHY',
    DRAINING: 'DRAINING'
});

class DiscoveryError extends Error {}
class ValidationError extends DiscoveryError {}
class RegistrationError extends DiscoveryError {}
class NoHealthyInstanceError extends DiscoveryError {}

function validateInstance(input) {
    if (!input || typeof input !== 'object') {
        throw new ValidationError('Instance must be an object');
    }

    const required = ['serviceName', 'host', 'port', 'version'];

    for (const field of required) {
        if (
            typeof input[field] !== 'string' &&
            field !== 'port'
        ) {
            throw new ValidationError(`Invalid ${field}`);
        }
    }

    if (!input.serviceName.trim() || !input.host.trim()) {
        throw new ValidationError('Service name and host are required');
    }

    if (!Number.isInteger(input.port) ||
        input.port < 1 ||
        input.port > 65535) {
        throw new ValidationError('Invalid port');
    }

    if (!input.version.trim()) {
        throw new ValidationError('Version is required');
    }

    const leaseMs = input.leaseMs ?? 30000;

    if (!Number.isFinite(leaseMs) || leaseMs <= 0) {
        throw new ValidationError('Lease must be positive');
    }

    return {
        instanceId: input.instanceId ?? randomUUID(),
        serviceName: input.serviceName,
        host: input.host,
        port: input.port,
        version: input.version,
        metadata: Object.freeze({ ...(input.metadata ?? {}) }),
        weight: input.weight ?? 1,
        leaseMs,
        status: Health.UNKNOWN,
        registeredAt: Date.now(),
        lastHeartbeat: Date.now(),
        failures: 0,
        successes: 0,
        generation: 0
    };
}

class CircuitBreaker {
    constructor(threshold = 3, resetAfterMs = 5000) {
        if (threshold < 1 || resetAfterMs < 0) {
            throw new ValidationError('Invalid circuit-breaker settings');
        }

        this.threshold = threshold;
        this.resetAfterMs = resetAfterMs;
        this.failures = 0;
        this.openedAt = null;
    }

    get state() {
        if (this.openedAt === null) return 'CLOSED';

        if (Date.now() - this.openedAt >= this.resetAfterMs) {
            return 'HALF_OPEN';
        }

        return 'OPEN';
    }

    allowRequest() {
        return this.state !== 'OPEN';
    }

    success() {
        this.failures = 0;
        this.openedAt = null;
    }

    failure() {
        this.failures++;

        if (this.failures >= this.threshold) {
            this.openedAt = Date.now();
        }
    }
}

class ServiceRegistry extends EventEmitter {
    #instances = new Map();
    #serviceIndex = new Map();
    #cache = new Map();
    #breakers = new Map();

    constructor({
        failureThreshold = 2,
        recoveryThreshold = 2,
        cacheTtlMs = 1000
    } = {}) {
        super();

        this.failureThreshold = failureThreshold;
        this.recoveryThreshold = recoveryThreshold;
        this.cacheTtlMs = cacheTtlMs;
    }

    #invalidate(serviceName) {
        this.#cache.delete(serviceName);
    }

    register(input) {
        const instance = validateInstance(input);

        if (this.#instances.has(instance.instanceId)) {
            throw new RegistrationError(
                `Duplicate instance ID: ${instance.instanceId}`
            );
        }

        this.#instances.set(instance.instanceId, instance);

        if (!this.#serviceIndex.has(instance.serviceName)) {
            this.#serviceIndex.set(instance.serviceName, new Set());
        }

        this.#serviceIndex.get(instance.serviceName).add(
            instance.instanceId
        );

        this.#breakers.set(
            instance.instanceId,
            new CircuitBreaker()
        );

        this.#invalidate(instance.serviceName);

        this.emit('registered', this.#publicView(instance));

        return this.#publicView(instance);
    }

    #publicView(instance) {
        return Object.freeze({
            instanceId: instance.instanceId,
            serviceName: instance.serviceName,
            host: instance.host,
            port: instance.port,
            endpoint: `${instance.host}:${instance.port}`,
            version: instance.version,
            status: instance.status,
            weight: instance.weight,
            metadata: instance.metadata,
            lastHeartbeat: instance.lastHeartbeat
        });
    }

    deregister(instanceId) {
        const instance = this.#instances.get(instanceId);

        if (!instance) return false;

        this.#instances.delete(instanceId);
        this.#breakers.delete(instanceId);

        const ids = this.#serviceIndex.get(instance.serviceName);

        ids.delete(instanceId);

        if (ids.size === 0) {
            this.#serviceIndex.delete(instance.serviceName);
        }

        this.#invalidate(instance.serviceName);

        this.emit('deregistered', {
            instanceId,
            serviceName: instance.serviceName
        });

        return true;
    }

    heartbeat(instanceId) {
        const instance = this.#instances.get(instanceId);

        if (!instance) {
            throw new RegistrationError('Unknown instance');
        }

        instance.lastHeartbeat = Date.now();

        this.emit('heartbeat', {
            instanceId,
            timestamp: instance.lastHeartbeat
        });
    }

    updateHealth(instanceId, healthy) {
        const instance = this.#instances.get(instanceId);

        if (!instance) {
            throw new RegistrationError('Unknown instance');
        }

        if (typeof healthy !== 'boolean') {
            throw new ValidationError('Health result must be boolean');
        }

        if (instance.status === Health.DRAINING) {
            return instance.status;
        }

        if (healthy) {
            instance.failures = 0;
            instance.successes++;

            if (instance.successes >= this.recoveryThreshold) {
                instance.status = Health.HEALTHY;
            }
        } else {
            instance.successes = 0;
            instance.failures++;

            if (instance.failures >= this.failureThreshold) {
                instance.status = Health.UNHEALTHY;
            }
        }

        this.#invalidate(instance.serviceName);

        this.emit('healthChanged', {
            instanceId,
            status: instance.status
        });

        return instance.status;
    }

    drain(instanceId) {
        const instance = this.#instances.get(instanceId);

        if (!instance) {
            throw new RegistrationError('Unknown instance');
        }

        instance.status = Health.DRAINING;
        this.#invalidate(instance.serviceName);

        this.emit('draining', { instanceId });

        return instance.status;
    }

    expire(now = Date.now()) {
        const expired = [];

        for (const [id, instance] of this.#instances) {
            if (now - instance.lastHeartbeat > instance.leaseMs) {
                expired.push(id);
            }
        }

        for (const id of expired) {
            this.deregister(id);
        }

        return expired;
    }

    discover(serviceName, {
        version,
        metadata = {}
    } = {}) {
        const cached = this.#cache.get(serviceName);

        if (
            cached &&
            cached.expiresAt > Date.now() &&
            cached.version === version &&
            cached.metadataKey === JSON.stringify(metadata)
        ) {
            return cached.instances;
        }

        const ids = this.#serviceIndex.get(serviceName) ?? new Set();

        const instances = [...ids]
            .map(id => this.#instances.get(id))
            .filter(instance =>
                instance.status === Health.HEALTHY &&
                Date.now() - instance.lastHeartbeat <= instance.leaseMs &&
                (version === undefined || instance.version === version) &&
                Object.entries(metadata).every(
                    ([key, value]) => instance.metadata[key] === value
                )
            )
            .map(instance => this.#publicView(instance));

        const result = Object.freeze(instances);

        this.#cache.set(serviceName, {
            expiresAt: Date.now() + this.cacheTtlMs,
            version,
            metadataKey: JSON.stringify(metadata),
            instances: result
        });

        return result;
    }

    select(serviceName) {
        const available = this.discover(serviceName);

        const candidates = available.filter(instance =>
            this.#breakers.get(instance.instanceId)?.allowRequest()
        );

        if (candidates.length === 0) {
            throw new NoHealthyInstanceError(
                `No eligible endpoint for ${serviceName}`
            );
        }

        const totalWeight = candidates.reduce(
            (sum, instance) => sum + instance.weight,
            0
        );

        let choice = Math.random() * totalWeight;

        for (const instance of candidates) {
            choice -= instance.weight;

            if (choice < 0) return instance;
        }

        return candidates[candidates.length - 1];
    }

    recordRequestResult(instanceId, successful) {
        const breaker = this.#breakers.get(instanceId);

        if (!breaker) {
            throw new RegistrationError('Unknown instance');
        }

        if (successful) {
            breaker.success();
        } else {
            breaker.failure();
        }

        this.emit('requestResult', {
            instanceId,
            successful,
            circuitState: breaker.state
        });
    }

    async probeAll(probe, concurrency = 4) {
        if (typeof probe !== 'function') {
            throw new ValidationError('Probe must be a function');
        }

        if (!Number.isInteger(concurrency) || concurrency < 1) {
            throw new ValidationError('Concurrency must be positive');
        }

        const instances = [...this.#instances.values()]
            .filter(instance => instance.status !== Health.DRAINING);

        let cursor = 0;

        const worker = async () => {
            while (true) {
                const index = cursor++;

                if (index >= instances.length) return;

                const instance = instances[index];

                try {
                    const result = await probe(this.#publicView(instance));
                    this.updateHealth(instance.instanceId, Boolean(result));
                } catch {
                    this.updateHealth(instance.instanceId, false);
                }
            }
        };

        await Promise.all(
            Array.from(
                { length: Math.min(concurrency, instances.length) },
                () => worker()
            )
        );
    }

    list() {
        return [...this.#instances.values()].map(instance =>
            this.#publicView(instance)
        );
    }

    async save(filename) {
        const snapshot = {
            savedAt: new Date().toISOString(),
            instances: this.list()
        };

        const temporary = `${filename}.${randomUUID()}.tmp`;

        try {
            await fs.writeFile(
                temporary,
                JSON.stringify(snapshot, null, 2),
                { flag: 'wx', mode: 0o600 }
            );

            await fs.rename(temporary, filename);
        } catch (error) {
            await fs.unlink(temporary).catch(() => {});
            throw error;
        }
    }
}

async function main() {
    const registry = new ServiceRegistry({
        failureThreshold: 2,
        recoveryThreshold: 2,
        cacheTtlMs: 500
    });

    registry.on('registered', event => {
        console.log('REGISTERED:', event.endpoint);
    });

    registry.on('healthChanged', event => {
        console.log('HEALTH:', event.instanceId, event.status);
    });

    registry.on('deregistered', event => {
        console.log('DEREGISTERED:', event.instanceId);
    });

    const instances = [
        registry.register({
            serviceName: 'payment-service',
            host: '10.0.1.10',
            port: 8001,
            version: '2.0.0',
            weight: 3,
            metadata: { region: 'ap-south-1', environment: 'production' }
        }),
        registry.register({
            serviceName: 'payment-service',
            host: '10.0.1.11',
            port: 8001,
            version: '2.0.0',
            weight: 1,
            metadata: { region: 'ap-south-1', environment: 'production' }
        }),
        registry.register({
            serviceName: 'inventory-service',
            host: '10.0.2.10',
            port: 8002,
            version: '1.4.0',
            metadata: { region: 'ap-south-1', environment: 'production' }
        })
    ];

    // A service is discoverable only after satisfying recovery policy.
    for (const instance of instances) {
        registry.updateHealth(instance.instanceId, true);
        registry.updateHealth(instance.instanceId, true);
    }

    console.log('\nDISCOVERY');

    console.log(
        registry.discover('payment-service', {
            version: '2.0.0',
            metadata: { environment: 'production' }
        })
    );

    console.log('\nWEIGHTED SELECTION');

    for (let i = 0; i < 5; i++) {
        console.log(registry.select('payment-service').endpoint);
    }

    console.log('\nASYNC HEALTH PROBES');

    await registry.probeAll(
        async instance => {
            await new Promise(resolve => setTimeout(resolve, 10));
            return instance.port !== 8001;
        },
        2
    );

    console.log('\nFAILURE TRACKING');

    const first = instances[0];

    registry.recordRequestResult(first.instanceId, false);
    registry.recordRequestResult(first.instanceId, false);

    try {
        console.log(registry.select('payment-service'));
    } catch (error) {
        console.log(error.message);
    }

    console.log('\nDRAINING');

    registry.drain(instances[1].instanceId);

    console.log(
        'Remaining healthy endpoints:',
        registry.discover('payment-service').length
    );

    console.log('\nFINAL REGISTRY');

    console.log(JSON.stringify(registry.list(), null, 2));

    // Atomic snapshot persistence.
    await registry.save('./service-registry.json');

    console.log('\nRegistry snapshot saved.');

    // Duplicate IDs must be rejected.
    try {
        registry.register({
            instanceId: instances[0].instanceId,
            serviceName: 'duplicate-service',
            host: '127.0.0.1',
            port: 9000,
            version: '1.0.0'
        });
    } catch (error) {
        console.log('Expected validation failure:', error.message);
    }
}

main().catch(error => {
    console.error('Fatal execution error:', error);
    process.exitCode = 1;
});
