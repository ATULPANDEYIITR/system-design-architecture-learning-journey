"use strict";

/*
 * Circuit Breaker
 * Failure Isolation and Graceful Degradation
 *
 * Node.js 18+
 *
 * Features:
 * - Asynchronous dependency execution
 * - CLOSED / OPEN / HALF_OPEN state machine
 * - Failure threshold and recovery timeout
 * - Concurrent half-open probe control
 * - Promise-based fallbacks
 * - EventEmitter-based state notifications
 * - Rolling operational metrics
 * - Timeout protection
 * - Dependency isolation
 * - Input validation
 */

const { EventEmitter } = require("node:events");
const { performance } = require("node:perf_hooks");
const assert = require("node:assert/strict");

const State = Object.freeze({
    CLOSED: "CLOSED",
    OPEN: "OPEN",
    HALF_OPEN: "HALF_OPEN"
});

class CircuitOpenError extends Error {
    constructor(service, message = "Circuit is open") {
        super(`${service}: ${message}`);
        this.name = "CircuitOpenError";
    }
}

class CircuitConfigurationError extends Error {
    constructor(message) {
        super(message);
        this.name = "CircuitConfigurationError";
    }
}

class AsyncCircuitBreaker extends EventEmitter {
    constructor({
        name,
        failureThreshold = 3,
        recoveryTimeoutMs = 2000,
        halfOpenMaxCalls = 1,
        historyLimit = 100
    }) {
        super();

        if (typeof name !== "string" || !name.trim()) {
            throw new CircuitConfigurationError(
                "A service name is required."
            );
        }

        for (const [key, value] of Object.entries({
            failureThreshold,
            recoveryTimeoutMs,
            halfOpenMaxCalls,
            historyLimit
        })) {
            if (!Number.isInteger(value) || value < 1) {
                throw new CircuitConfigurationError(
                    `${key} must be a positive integer.`
                );
            }
        }

        this.name = name;
        this.failureThreshold = failureThreshold;
        this.recoveryTimeoutMs = recoveryTimeoutMs;
        this.halfOpenMaxCalls = halfOpenMaxCalls;
        this.historyLimit = historyLimit;

        this.state = State.CLOSED;
        this.failureCount = 0;
        this.openedAt = null;
        this.halfOpenInflight = 0;

        this.metrics = {
            totalCalls: 0,
            successes: 0,
            failures: 0,
            rejected: 0,
            fallbacks: 0,
            transitions: 0,
            totalLatencyMs: 0
        };

        this.history = [];
    }

    record(event, details = {}) {
        const entry = Object.freeze({
            timestamp: new Date().toISOString(),
            event,
            state: this.state,
            ...details
        });

        this.history.push(entry);

        if (this.history.length > this.historyLimit) {
            this.history.shift();
        }

        this.emit("circuit-event", entry);
    }

    transition(nextState, reason) {
        if (this.state === nextState) {
            return;
        }

        const previous = this.state;
        this.state = nextState;
        this.metrics.transitions++;

        this.record("STATE_TRANSITION", {
            previous,
            next: nextState,
            reason
        });
    }

    refreshState() {
        if (this.state !== State.OPEN) {
            return;
        }

        const elapsed = performance.now() - this.openedAt;

        if (elapsed >= this.recoveryTimeoutMs) {
            this.halfOpenInflight = 0;

            this.transition(
                State.HALF_OPEN,
                "Recovery timeout elapsed."
            );
        }
    }

    acquirePermission() {
        this.refreshState();

        if (this.state === State.OPEN) {
            this.metrics.rejected++;

            throw new CircuitOpenError(this.name);
        }

        const admittedState = this.state;

        if (admittedState === State.HALF_OPEN) {
            if (this.halfOpenInflight >= this.halfOpenMaxCalls) {
                this.metrics.rejected++;

                throw new CircuitOpenError(
                    this.name,
                    "Recovery probe capacity exhausted."
                );
            }

            this.halfOpenInflight++;
        }

        this.metrics.totalCalls++;

        return admittedState;
    }

    onSuccess(admittedState, elapsed) {
        this.metrics.successes++;
        this.metrics.totalLatencyMs += elapsed;

        if (admittedState === State.HALF_OPEN) {
            this.halfOpenInflight--;
            this.failureCount = 0;
            this.openedAt = null;

            this.transition(
                State.CLOSED,
                "Recovery probe succeeded."
            );
        } else if (this.state === State.CLOSED) {
            this.failureCount = 0;
        }

        this.record("CALL_SUCCESS", {
            latencyMs: Number(elapsed.toFixed(2))
        });
    }

    onFailure(admittedState, error, elapsed) {
        this.metrics.failures++;
        this.metrics.totalLatencyMs += elapsed;

        if (admittedState === State.HALF_OPEN) {
            this.halfOpenInflight--;
            this.open("Recovery probe failed.");
        } else if (
            admittedState === State.CLOSED &&
            this.state === State.CLOSED
        ) {
            this.failureCount++;

            if (this.failureCount >= this.failureThreshold) {
                this.open("Failure threshold reached.");
            }
        }

        this.record("CALL_FAILURE", {
            error: error.message,
            errorType: error.name,
            latencyMs: Number(elapsed.toFixed(2))
        });
    }

    open(reason) {
        this.openedAt = performance.now();
        this.halfOpenInflight = 0;

        this.transition(State.OPEN, reason);
    }

    async execute(operation, {
        fallback = null,
        timeoutMs = 5000
    } = {}) {
        if (typeof operation !== "function") {
            throw new TypeError("Operation must be a function.");
        }

        if (
            !Number.isFinite(timeoutMs) ||
            timeoutMs <= 0
        ) {
            throw new RangeError(
                "Timeout must be a positive finite number."
            );
        }

        const useFallback = async error => {
            if (typeof fallback !== "function") {
                throw error;
            }

            this.metrics.fallbacks++;

            this.record("FALLBACK_EXECUTED", {
                reason: error.message
            });

            return fallback(error);
        };

        let admittedState;

        try {
            admittedState = this.acquirePermission();
        } catch (error) {
            if (error instanceof CircuitOpenError) {
                return useFallback(error);
            }

            throw error;
        }

        const startedAt = performance.now();

        let timeoutHandle;

        const timeoutPromise = new Promise((_, reject) => {
            timeoutHandle = setTimeout(() => {
                reject(
                    new Error(
                        `Dependency timeout after ${timeoutMs} ms.`
                    )
                );
            }, timeoutMs);
        });

        try {
            const operationPromise = Promise.resolve().then(
                () => operation()
            );

            const result = await Promise.race([
                operationPromise,
                timeoutPromise
            ]);

            clearTimeout(timeoutHandle);

            this.onSuccess(
                admittedState,
                performance.now() - startedAt
            );

            return result;

        } catch (error) {
            clearTimeout(timeoutHandle);

            this.onFailure(
                admittedState,
                error,
                performance.now() - startedAt
            );

            return useFallback(error);
        }
    }

    snapshot() {
        const completed =
            this.metrics.successes + this.metrics.failures;

        return Object.freeze({
            name: this.name,
            state: this.state,
            failureCount: this.failureCount,
            metrics: Object.freeze({
                ...this.metrics,
                successRate: completed === 0
                    ? 0
                    : Number(
                        (
                            this.metrics.successes /
                            completed
                        ).toFixed(4)
                    )
            }),
            history: Object.freeze([...this.history])
        });
    }
}

class DependencyRegistry {
    constructor() {
        this.breakers = new Map();
    }

    register(name, config) {
        if (this.breakers.has(name)) {
            throw new Error(`Dependency already registered: ${name}`);
        }

        const breaker = new AsyncCircuitBreaker({
            name,
            ...config
        });

        this.breakers.set(name, breaker);

        return breaker;
    }

    get(name) {
        const breaker = this.breakers.get(name);

        if (!breaker) {
            throw new Error(`Unknown dependency: ${name}`);
        }

        return breaker;
    }

    healthReport() {
        return Array.from(this.breakers.values()).map(
            breaker => ({
                name: breaker.name,
                state: breaker.state,
                failures: breaker.metrics.failures,
                rejected: breaker.metrics.rejected
            })
        );
    }
}

class InventoryService {
    constructor() {
        this.cache = new Map([
            ["SKU-101", { quantity: 25 }],
            ["SKU-102", { quantity: 8 }]
        ]);

        this.breaker = new AsyncCircuitBreaker({
            name: "inventory-service",
            failureThreshold: 2,
            recoveryTimeoutMs: 1000,
            halfOpenMaxCalls: 1
        });

        this.remoteAvailable = true;
    }

    async getInventory(sku) {
        if (typeof sku !== "string" || !sku.trim()) {
            throw new TypeError("SKU must be a non-empty string.");
        }

        return this.breaker.execute(
            async () => {
                if (!this.remoteAvailable) {
                    throw new Error("Inventory API unavailable.");
                }

                const inventory = this.cache.get(sku);

                if (!inventory) {
                    throw new Error("Inventory item not found.");
                }

                return {
                    sku,
                    quantity: inventory.quantity,
                    source: "REMOTE"
                };
            },
            {
                fallback: () => {
                    const cached = this.cache.get(sku);

                    if (!cached) {
                        return {
                            sku,
                            status: "UNAVAILABLE"
                        };
                    }

                    return {
                        sku,
                        quantity: cached.quantity,
                        source: "CACHE",
                        stale: true
                    };
                },
                timeoutMs: 500
            }
        );
    }
}

async function runTests() {
    const breaker = new AsyncCircuitBreaker({
        name: "test-service",
        failureThreshold: 2,
        recoveryTimeoutMs: 30
    });

    const failure = async () => {
        throw new Error("Simulated failure");
    };

    await assert.rejects(
        breaker.execute(failure),
        /Simulated failure/
    );

    await assert.rejects(
        breaker.execute(failure),
        /Simulated failure/
    );

    assert.equal(breaker.state, State.OPEN);

    const fallbackResult = await breaker.execute(
        async () => "remote",
        { fallback: () => "cached" }
    );

    assert.equal(fallbackResult, "cached");

    await new Promise(resolve => setTimeout(resolve, 40));

    const recovered = await breaker.execute(
        async () => "healthy"
    );

    assert.equal(recovered, "healthy");
    assert.equal(breaker.state, State.CLOSED);

    assert.throws(
        () => new AsyncCircuitBreaker({
            name: "invalid",
            failureThreshold: 0
        }),
        CircuitConfigurationError
    );

    console.log("All JavaScript tests passed.");
}

async function main() {
    const registry = new DependencyRegistry();

    const paymentBreaker = registry.register(
        "payment-provider",
        {
            failureThreshold: 3,
            recoveryTimeoutMs: 1500
        }
    );

    paymentBreaker.on("circuit-event", event => {
        if (event.event === "STATE_TRANSITION") {
            console.log("Circuit event:", event);
        }
    });

    let paymentProviderAvailable = false;

    for (let i = 1; i <= 4; i++) {
        const payment = await paymentBreaker.execute(
            async () => {
                if (!paymentProviderAvailable) {
                    throw new Error("Payment provider offline.");
                }

                return {
                    status: "PROCESSED",
                    transactionId: `TX-${i}`
                };
            },
            {
                fallback: () => ({
                    status: "PENDING",
                    transactionId: `TX-${i}`,
                    message: "Queued for reconciliation."
                }),
                timeoutMs: 300
            }
        );

        console.log("Payment result:", payment);
    }

    console.log("\nDependency health:");
    console.log(registry.healthReport());

    const inventory = new InventoryService();
    inventory.remoteAvailable = false;

    console.log(
        "\nInventory degraded response:",
        await inventory.getInventory("SKU-101")
    );

    await runTests();
}

if (require.main === module) {
    main().catch(error => {
        console.error("Application failure:", error);
        process.exitCode = 1;
    });
}

module.exports = {
    State,
    CircuitOpenError,
    CircuitConfigurationError,
    AsyncCircuitBreaker,
    DependencyRegistry
};
