'use strict';

/*
 * Bulkheads: Event-driven resource isolation.
 *
 * Demonstrates independent service pools, bounded admission,
 * asynchronous execution, circuit breakers, timeouts, and events.
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const { EventEmitter } = require('node:events');

const PoolState = Object.freeze({
    CLOSED: 'CLOSED',
    OPEN: 'OPEN',
    HALF_OPEN: 'HALF_OPEN'
});

class BulkheadError extends Error {
    constructor(message, code) {
        super(message);
        this.name = this.constructor.name;
        this.code = code;
    }
}

class CapacityError extends BulkheadError {}
class CircuitOpenError extends BulkheadError {}
class OperationTimeoutError extends BulkheadError {}
class ServiceError extends BulkheadError {}

class CircuitBreaker {
    constructor({
        failureThreshold = 3,
        recoveryMilliseconds = 2000
    } = {}) {
        if (!Number.isInteger(failureThreshold) ||
            failureThreshold < 1) {
            throw new TypeError('Invalid failure threshold');
        }

        if (recoveryMilliseconds <= 0) {
            throw new TypeError('Invalid recovery interval');
        }

        this.failureThreshold = failureThreshold;
        this.recoveryMilliseconds = recoveryMilliseconds;
        this.state = PoolState.CLOSED;
        this.failures = 0;
        this.openedAt = 0;
        this.probeInProgress = false;
    }

    acquirePermission() {
        if (this.state === PoolState.CLOSED) {
            return true;
        }

        if (this.state === PoolState.OPEN) {
            if (Date.now() - this.openedAt <
                this.recoveryMilliseconds) {
                return false;
            }

            this.state = PoolState.HALF_OPEN;
            this.probeInProgress = false;
        }

        if (this.state === PoolState.HALF_OPEN) {
            if (this.probeInProgress) {
                return false;
            }

            this.probeInProgress = true;
            return true;
        }

        return false;
    }

    success() {
        this.state = PoolState.CLOSED;
        this.failures = 0;
        this.probeInProgress = false;
    }

    failure() {
        this.failures++;
        this.probeInProgress = false;

        if (this.failures >= this.failureThreshold) {
            this.state = PoolState.OPEN;
            this.openedAt = Date.now();
        }
    }

    abandoned() {
        // A rejected request must not leave a half-open probe locked.
        if (this.state === PoolState.HALF_OPEN) {
            this.probeInProgress = false;
        }
    }
}

class ResourcePool extends EventEmitter {
    constructor({
        name,
        concurrency,
        queueLimit,
        timeoutMilliseconds,
        failureThreshold = 3,
        recoveryMilliseconds = 2000
    }) {
        super();

        if (!name || !Number.isInteger(concurrency) ||
            concurrency < 1 ||
            !Number.isInteger(queueLimit) ||
            queueLimit < 0 ||
            timeoutMilliseconds <= 0) {
            throw new TypeError('Invalid resource pool configuration');
        }

        this.name = name;
        this.concurrency = concurrency;
        this.queueLimit = queueLimit;
        this.timeoutMilliseconds = timeoutMilliseconds;

        this.active = 0;
        this.queue = [];
        this.closed = false;

        this.breaker = new CircuitBreaker({
            failureThreshold,
            recoveryMilliseconds
        });

        this.metrics = {
            accepted: 0,
            completed: 0,
            failed: 0,
            timedOut: 0,
            rejected: 0,
            totalLatency: 0
        };
    }

    submit(operation, metadata = {}) {
        if (this.closed) {
            this.metrics.rejected++;
            return Promise.reject(
                new CapacityError('Resource pool is shut down', 'POOL_CLOSED')
            );
        }

        if (typeof operation !== 'function') {
            return Promise.reject(
                new TypeError('Operation must be a function')
            );
        }

        if (!this.breaker.acquirePermission()) {
            this.metrics.rejected++;
            this.emit('rejected', {
                pool: this.name,
                reason: 'CIRCUIT_OPEN',
                metadata
            });

            return Promise.reject(
                new CircuitOpenError(
                    `${this.name}: circuit is open`,
                    'CIRCUIT_OPEN'
                )
            );
        }

        if (this.active < this.concurrency) {
            return this.start(operation, metadata);
        }

        if (this.queue.length >= this.queueLimit) {
            this.breaker.abandoned();
            this.metrics.rejected++;

            this.emit('rejected', {
                pool: this.name,
                reason: 'QUEUE_FULL',
                metadata
            });

            return Promise.reject(
                new CapacityError(
                    `${this.name}: queue capacity exceeded`,
                    'QUEUE_FULL'
                )
            );
        }

        return new Promise((resolve, reject) => {
            const item = {
                operation,
                metadata,
                resolve,
                reject,
                enqueuedAt: Date.now()
            };

            this.queue.push(item);

            this.emit('queued', {
                pool: this.name,
                queueLength: this.queue.length
            });
        });
    }

    async start(operation, metadata = {}, queuedItem = null) {
        this.active++;
        this.metrics.accepted++;

        const started = Date.now();

        this.emit('started', {
            pool: this.name,
            active: this.active,
            metadata
        });

        let timeoutHandle;

        const timeout = new Promise((_, reject) => {
            timeoutHandle = setTimeout(() => {
                reject(
                    new OperationTimeoutError(
                        `${this.name}: execution deadline exceeded`,
                        'TIMEOUT'
                    )
                );
            }, this.timeoutMilliseconds);
        });

        try {
            // Promise.race enforces the deadline from the caller's
            // perspective. The operation itself must support cancellation
            // if its underlying resource needs immediate termination.
            const result = await Promise.race([
                Promise.resolve().then(operation),
                timeout
            ]);

            this.metrics.completed++;
            this.metrics.totalLatency += Date.now() - started;

            this.breaker.success();

            this.emit('completed', {
                pool: this.name,
                duration: Date.now() - started
            });

            if (queuedItem) {
                queuedItem.resolve(result);
            }

            return result;

        } catch (error) {
            this.metrics.failed++;

            if (error instanceof OperationTimeoutError) {
                this.metrics.timedOut++;
            }

            this.breaker.failure();

            this.emit('failed', {
                pool: this.name,
                error: error.message,
                state: this.breaker.state
            });

            if (queuedItem) {
                queuedItem.reject(error);
                return undefined;
            }

            throw error;

        } finally {
            clearTimeout(timeoutHandle);
            this.active--;

            this.dispatch();
        }
    }

    dispatch() {
        while (
            !this.closed &&
            this.active < this.concurrency &&
            this.queue.length > 0
        ) {
            const item = this.queue.shift();

            if (!this.breaker.acquirePermission()) {
                item.reject(
                    new CircuitOpenError(
                        `${this.name}: circuit opened while queued`,
                        'CIRCUIT_OPEN'
                    )
                );
                this.metrics.rejected++;
                continue;
            }

            this.start(
                item.operation,
                item.metadata,
                item
            ).catch(() => {
                // Queued callers receive errors through their own promises.
            });
        }
    }

    shutdown() {
        this.closed = true;

        for (const item of this.queue.splice(0)) {
            item.reject(
                new CapacityError('Pool shut down', 'POOL_CLOSED')
            );
        }

        this.emit('shutdown', { pool: this.name });
    }

    report() {
        return Object.freeze({
            name: this.name,
            state: this.breaker.state,
            active: this.active,
            queued: this.queue.length,
            ...this.metrics,
            averageLatency: this.metrics.completed
                ? this.metrics.totalLatency / this.metrics.completed
                : 0
        });
    }
}

class BulkheadRegistry {
    constructor() {
        this.pools = new Map();
    }

    register(config) {
        if (this.pools.has(config.name)) {
            throw new Error(`Duplicate pool: ${config.name}`);
        }

        const pool = new ResourcePool(config);

        pool.on('failed', event => {
            console.error('[ISOLATED FAILURE]', event);
        });

        pool.on('rejected', event => {
            console.warn('[LOAD SHEDDING]', event);
        });

        this.pools.set(config.name, pool);

        return pool;
    }

    get(name) {
        const pool = this.pools.get(name);

        if (!pool) {
            throw new Error(`Unknown resource pool: ${name}`);
        }

        return pool;
    }

    async execute(name, operation, metadata) {
        return this.get(name).submit(operation, metadata);
    }

    report() {
        return [...this.pools.values()].map(pool => pool.report());
    }
}

function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function simulate() {
    const registry = new BulkheadRegistry();

    const payment = registry.register({
        name: 'payment',
        concurrency: 2,
        queueLimit: 3,
        timeoutMilliseconds: 1000,
        failureThreshold: 3
    });

    const inventory = registry.register({
        name: 'inventory',
        concurrency: 3,
        queueLimit: 4,
        timeoutMilliseconds: 1000,
        failureThreshold: 3
    });

    const notification = registry.register({
        name: 'notification',
        concurrency: 1,
        queueLimit: 2,
        timeoutMilliseconds: 1000,
        failureThreshold: 2,
        recoveryMilliseconds: 500
    });

    const services = {
        payment: async () => {
            await delay(80);
            return 'Payment processed';
        },

        inventory: async () => {
            await delay(120);
            return 'Inventory reserved';
        },

        notification: async () => {
            await delay(40);
            return 'Notification sent';
        }
    };

    console.log('SCENARIO 1: Concurrent independent services');

    const requests = [];

    for (let i = 0; i < 6; i++) {
        requests.push(
            registry.execute('payment', services.payment)
                .catch(error => error.code)
        );
    }

    for (let i = 0; i < 5; i++) {
        requests.push(
            registry.execute('inventory', services.inventory)
                .catch(error => error.code)
        );
    }

    for (let i = 0; i < 4; i++) {
        requests.push(
            registry.execute('notification', services.notification)
                .catch(error => error.code)
        );
    }

    await Promise.all(requests);

    console.log('\nSCENARIO 2: Notification dependency failure');

    for (let i = 0; i < 2; i++) {
        try {
            await notification.submit(async () => {
                throw new ServiceError(
                    'Notification provider unavailable',
                    'DOWNSTREAM_FAILURE'
                );
            });
        } catch (error) {
            console.log(error.code, error.message);
        }
    }

    console.log('\nSCENARIO 3: Isolated services remain available');

    const results = await Promise.all([
        registry.execute('payment', services.payment),
        registry.execute('inventory', services.inventory)
    ]);

    console.log(results);

    console.log('\nSCENARIO 4: Recovery probe');

    await delay(550);

    try {
        console.log(
            await notification.submit(services.notification)
        );
    } catch (error) {
        console.error(error.message);
    }

    console.log('\nSCENARIO 5: Timeout');

    try {
        await payment.submit(() => delay(1500));
    } catch (error) {
        console.error(error.code, error.message);
    }

    console.log('\nRESOURCE REPORT');

    console.table(registry.report());

    // A notification failure cannot directly alter payment capacity.
    console.assert(payment.concurrency === 2);
    console.assert(inventory.concurrency === 3);
    console.assert(notification.concurrency === 1);

    payment.shutdown();
    inventory.shutdown();
    notification.shutdown();
}

simulate().catch(error => {
    console.error('Fatal simulation error:', error);
    process.exitCode = 1;
});
