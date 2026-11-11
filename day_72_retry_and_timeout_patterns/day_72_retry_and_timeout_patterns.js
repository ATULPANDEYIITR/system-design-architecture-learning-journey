"use strict";

/*
 * Retry and Timeout Patterns
 * Event-driven dependency resilience model.
 * Node.js 18+; no external packages.
 */

const { randomUUID } = require("node:crypto");
const { setTimeout: sleep } = require("node:timers/promises");
const fs = require("node:fs/promises");

class PermanentError extends Error {}
class RetryExhausted extends Error {}
class CircuitOpenError extends Error {}
class RequestTimeoutError extends Error {}

const CircuitState = Object.freeze({
    CLOSED: "closed",
    OPEN: "open",
    HALF_OPEN: "half_open"
});

class RetryPolicy {
    constructor({
        maxAttempts = 5,
        initialDelay = 200,
        multiplier = 2,
        maxDelay = 5000,
        jitter = "full",
        timeout = 2000,
        maxElapsed = 15000
    } = {}) {
        if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
            throw new RangeError("Invalid maximum attempts");
        }

        if (
            initialDelay < 0 ||
            maxDelay < 0 ||
            multiplier < 1 ||
            timeout <= 0 ||
            maxElapsed <= 0
        ) {
            throw new RangeError("Invalid retry policy values");
        }

        if (!["none", "full", "equal"].includes(jitter)) {
            throw new TypeError("Invalid jitter strategy");
        }

        Object.assign(this, {
            maxAttempts,
            initialDelay,
            multiplier,
            maxDelay,
            jitter,
            timeout,
            maxElapsed
        });

        Object.freeze(this);
    }

    calculateDelay(retryNumber) {
        const ceiling = Math.min(
            this.maxDelay,
            this.initialDelay * this.multiplier ** retryNumber
        );

        if (this.jitter === "none") return ceiling;

        if (this.jitter === "full") {
            return Math.random() * ceiling;
        }

        return ceiling / 2 + Math.random() * ceiling / 2;
    }
}

class RetryBudget {
    constructor(capacity, refillRate) {
        if (capacity < 1 || refillRate < 0) {
            throw new RangeError("Invalid retry budget");
        }

        this.capacity = capacity;
        this.tokens = capacity;
        this.refillRate = refillRate;
        this.updatedAt = performance.now();
    }

    consume() {
        const now = performance.now();
        const elapsed = (now - this.updatedAt) / 1000;

        this.tokens = Math.min(
            this.capacity,
            this.tokens + elapsed * this.refillRate
        );

        this.updatedAt = now;

        if (this.tokens < 1) return false;

        this.tokens--;
        return true;
    }
}

class CircuitBreaker {
    constructor({
        failureThreshold = 3,
        recoveryTimeout = 3000,
        halfOpenLimit = 1
    } = {}) {
        this.failureThreshold = failureThreshold;
        this.recoveryTimeout = recoveryTimeout;
        this.halfOpenLimit = halfOpenLimit;

        this.state = CircuitState.CLOSED;
        this.failures = 0;
        this.openedAt = 0;
        this.halfOpenCalls = 0;
    }

    acquire() {
        if (this.state === CircuitState.OPEN) {
            if (
                performance.now() - this.openedAt <
                this.recoveryTimeout
            ) {
                throw new CircuitOpenError("Dependency circuit is open");
            }

            this.state = CircuitState.HALF_OPEN;
            this.halfOpenCalls = 0;
        }

        if (this.state === CircuitState.HALF_OPEN) {
            if (this.halfOpenCalls >= this.halfOpenLimit) {
                throw new CircuitOpenError(
                    "Half-open probe capacity reached"
                );
            }

            this.halfOpenCalls++;
        }
    }

    success() {
        this.failures = 0;
        this.state = CircuitState.CLOSED;
        this.halfOpenCalls = 0;
    }

    failure() {
        this.failures++;

        if (
            this.state === CircuitState.HALF_OPEN ||
            this.failures >= this.failureThreshold
        ) {
            this.state = CircuitState.OPEN;
            this.openedAt = performance.now();
            this.halfOpenCalls = 0;
        }
    }
}

function withTimeout(operation, timeoutMs, attempt) {
    const controller = new AbortController();

    let timer;

    const timeoutPromise = new Promise((_, reject) => {
        timer = setTimeout(() => {
            controller.abort();
            reject(
                new RequestTimeoutError(
                    `Attempt ${attempt} exceeded ${timeoutMs} ms`
                )
            );
        }, timeoutMs);
    });

    return Promise.race([
        Promise.resolve().then(() =>
            operation({
                signal: controller.signal,
                attempt
            })
        ),
        timeoutPromise
    ]).finally(() => clearTimeout(timer));
}

class RetryExecutor {
    constructor(policy, { budget = null, breaker = null } = {}) {
        this.policy = policy;
        this.budget = budget;
        this.breaker = breaker;
    }

    async execute(operation, {
        retryable = error =>
            error instanceof Error &&
            [
                "ECONNRESET",
                "ECONNREFUSED",
                "ETIMEDOUT"
            ].includes(error.code) ||
            error instanceof RequestTimeoutError ||
            error instanceof TypeError
    } = {}) {
        if (typeof operation !== "function") {
            throw new TypeError("Operation must be a function");
        }

        const started = performance.now();
        const history = [];

        for (
            let attempt = 1;
            attempt <= this.policy.maxAttempts;
            attempt++
        ) {
            if (
                performance.now() - started >=
                this.policy.maxElapsed
            ) {
                throw new RetryExhausted(
                    "Maximum elapsed time exceeded"
                );
            }

            if (this.breaker) this.breaker.acquire();

            const attemptStarted = performance.now();

            try {
                const value = await withTimeout(
                    operation,
                    this.policy.timeout,
                    attempt
                );

                this.breaker?.success();

                history.push({
                    attempt,
                    outcome: "success",
                    elapsed: performance.now() - attemptStarted
                });

                return {
                    requestId: randomUUID(),
                    success: true,
                    value,
                    attempts: attempt,
                    elapsed: performance.now() - started,
                    history
                };
            } catch (error) {
                if (error instanceof PermanentError) {
                    throw error;
                }

                if (!retryable(error)) {
                    throw error;
                }

                this.breaker?.failure();

                if (attempt === this.policy.maxAttempts) {
                    throw new RetryExhausted(
                        `Failed after ${attempt} attempts: ${error.message}`
                    );
                }

                if (this.budget && !this.budget.consume()) {
                    throw new RetryExhausted(
                        "Shared retry budget exhausted"
                    );
                }

                const delay = this.policy.calculateDelay(attempt - 1);

                const remaining =
                    this.policy.maxElapsed -
                    (performance.now() - started);

                if (delay >= remaining) {
                    throw new RetryExhausted(
                        "Insufficient time remaining for retry"
                    );
                }

                history.push({
                    attempt,
                    outcome: "retry",
                    delay,
                    error: error.message
                });

                await sleep(delay);
            }
        }

        throw new RetryExhausted("Execution terminated");
    }
}

class DependencyService {
    constructor(failuresBeforeSuccess) {
        this.remainingFailures = failuresBeforeSuccess;
        this.calls = 0;
    }

    async request({ signal, attempt }) {
        this.calls++;

        if (signal.aborted) {
            throw new RequestTimeoutError("Request cancelled");
        }

        if (this.remainingFailures > 0) {
            this.remainingFailures--;

            const error = new Error(
                `Temporary failure at attempt ${attempt}`
            );

            error.code = "ECONNRESET";
            throw error;
        }

        return {
            status: "ok",
            calls: this.calls,
            timestamp: new Date().toISOString()
        };
    }
}

function simulateRetryStorm({
    clients = 100,
    retries = 4,
    initialDelay = 1000,
    multiplier = 2,
    jitter = false
} = {}) {
    const events = new Map();

    for (let client = 0; client < clients; client++) {
        let elapsed = 0;

        for (let retry = 0; retry < retries; retry++) {
            const ceiling = initialDelay * multiplier ** retry;

            const delay = jitter
                ? Math.random() * ceiling
                : ceiling;

            elapsed += delay;

            const bucket = Math.round(elapsed / 100) * 100;

            events.set(
                bucket,
                (events.get(bucket) || 0) + 1
            );
        }
    }

    return {
        totalRetries: clients * retries,
        maximumConcurrentRetries: Math.max(...events.values()),
        schedule: Object.fromEntries(
            [...events.entries()].sort((a, b) => a[0] - b[0])
        )
    };
}

async function runTests() {
    const policy = new RetryPolicy({
        maxAttempts: 4,
        initialDelay: 10,
        maxDelay: 50,
        timeout: 1000,
        maxElapsed: 5000,
        jitter: "full"
    });

    const service = new DependencyService(2);

    const executor = new RetryExecutor(policy, {
        budget: new RetryBudget(20, 10),
        breaker: new CircuitBreaker()
    });

    const result = await executor.execute(
        service.request.bind(service)
    );

    if (!result.success || result.attempts !== 3) {
        throw new Error("Recovery test failed");
    }

    // Permanent errors must never enter the retry loop.
    try {
        await executor.execute(async () => {
            throw new PermanentError("Authentication rejected");
        });

        throw new Error("Permanent failure test failed");
    } catch (error) {
        if (!(error instanceof PermanentError)) throw error;
    }

    // Timeout handling.
    try {
        await executor.execute(
            () => new Promise(resolve => setTimeout(resolve, 2000)),
        );

        throw new Error("Timeout test failed");
    } catch (error) {
        if (!(error instanceof RetryExhausted)) throw error;
    }

    const synchronized = simulateRetryStorm({ jitter: false });
    const randomized = simulateRetryStorm({ jitter: true });

    console.log("All tests passed.");
    console.log("Successful execution:", result);
    console.log("Synchronized retry peak:",
        synchronized.maximumConcurrentRetries);
    console.log("Jittered retry peak:",
        randomized.maximumConcurrentRetries);

    await fs.writeFile(
        "retry_metrics.json",
        JSON.stringify({
            result,
            synchronized,
            randomized
        }, null, 2),
        "utf8"
    );
}

runTests().catch(error => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});
