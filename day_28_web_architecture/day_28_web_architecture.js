/*
Web Architecture: Synchronous vs Asynchronous Communication
Blocking, Non-Blocking, and Asynchronous Workflows

Self-contained JavaScript study file.
Compatible with modern Node.js without external packages.

The examples progress through:
- synchronous execution
- blocking behavior
- callbacks
- Promises
- async/await
- concurrency
- timeouts
- retries
- cancellation with AbortController
- event-driven communication
- queues and backpressure
- dependency-aware workflows
- idempotency
- circuit breakers
- observability
- production-oriented design
*/

"use strict";

// ---------------------------------------------------------------------------
// 1. BASIC SYNCHRONOUS EXECUTION
// ---------------------------------------------------------------------------

function heading(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function synchronousTask(name) {
    console.log(`[sync] start ${name}`);
    console.log(`[sync] finish ${name}`);
    return `${name}: completed`;
}

function demonstrateSynchronousExecution() {
    heading("1. Synchronous execution");

    const first = synchronousTask("operation-A");
    const second = synchronousTask("operation-B");

    console.log(first);
    console.log(second);

    // JavaScript executes these statements in order on the current thread.
}


// ---------------------------------------------------------------------------
// 2. BLOCKING CPU WORK
// ---------------------------------------------------------------------------

function blockingCpuWork(iterations) {
    /*
     * This intentionally consumes CPU synchronously.
     * During this function, JavaScript's event loop cannot process ordinary
     * callbacks scheduled on the same thread.
     */
    let total = 0;

    for (let index = 0; index < iterations; index += 1) {
        total += index % 97;
    }

    return total;
}

async function demonstrateBlocking() {
    heading("2. Blocking versus non-blocking execution");

    let timerFired = false;

    setTimeout(() => {
        timerFired = true;
        console.log("Timer callback executed.");
    }, 0);

    console.log("Before blocking CPU work.");
    blockingCpuWork(5_000_000);
    console.log("After blocking CPU work.");
    console.log("Timer fired yet:", timerFired);

    /*
     * A zero-delay timer does not mean "execute immediately".
     * It means the callback can run when the event loop reaches it.
     */
    await new Promise((resolve) => setTimeout(resolve, 10));
    console.log("Timer fired after event-loop progress:", timerFired);
}


// ---------------------------------------------------------------------------
// 3. CALLBACK-BASED ASYNCHRONOUS COMMUNICATION
// ---------------------------------------------------------------------------

function callbackService(name, delay, callback) {
    console.log(`[callback] ${name} requested`);

    setTimeout(() => {
        if (name === "failure") {
            callback(new Error("Simulated service failure"), null);
            return;
        }

        callback(null, `${name}: completed`);
    }, delay);
}

function demonstrateCallbacks() {
    heading("3. Callback-based asynchronous communication");

    return new Promise((resolve) => {
        callbackService("remote-service", 20, (error, result) => {
            if (error) {
                console.error("Callback error:", error.message);
            } else {
                console.log("Callback result:", result);
            }

            resolve();
        });
    });
}


// ---------------------------------------------------------------------------
// 4. PROMISES
// ---------------------------------------------------------------------------

function promiseService(name, delay, shouldFail = false) {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            if (shouldFail) {
                reject(new Error(`${name}: service failure`));
                return;
            }

            resolve(`${name}: success`);
        }, delay);
    });
}

async function demonstratePromises() {
    heading("4. Promises");

    const result = await promiseService("inventory-service", 20);
    console.log(result);

    try {
        await promiseService("payment-service", 10, true);
    } catch (error) {
        console.log("Promise rejection handled:", error.message);
    }
}


// ---------------------------------------------------------------------------
// 5. PROMISE CONCURRENCY
// ---------------------------------------------------------------------------

async function demonstratePromiseConcurrency() {
    heading("5. Concurrent asynchronous operations");

    const start = performance.now();

    const results = await Promise.all([
        promiseService("service-A", 30),
        promiseService("service-B", 20),
        promiseService("service-C", 10),
    ]);

    const elapsed = performance.now() - start;

    console.log("Results:", results);
    console.log(`Elapsed time: ${elapsed.toFixed(2)}ms`);

    /*
     * Promise.all starts the independent operations without waiting for each
     * one to finish before starting the next.
     */
}


// ---------------------------------------------------------------------------
// 6. PROMISE.ALLSETTLED
// ---------------------------------------------------------------------------

async function demonstrateAllSettled() {
    heading("6. Promise.allSettled for partial failures");

    const results = await Promise.allSettled([
        promiseService("healthy-A", 10),
        promiseService("failing-B", 20, true),
        promiseService("healthy-C", 15),
    ]);

    for (const result of results) {
        if (result.status === "fulfilled") {
            console.log("Success:", result.value);
        } else {
            console.log("Failure:", result.reason.message);
        }
    }

    /*
     * allSettled is useful when every independent result matters even if
     * one or more operations fail.
     */
}


// ---------------------------------------------------------------------------
// 7. TIMEOUTS
// ---------------------------------------------------------------------------

function timeoutPromise(milliseconds) {
    return new Promise((_, reject) => {
        setTimeout(() => {
            reject(new Error("Operation timed out"));
        }, milliseconds);
    });
}

async function withTimeout(operationPromise, milliseconds) {
    return Promise.race([
        operationPromise,
        timeoutPromise(milliseconds),
    ]);
}

async function demonstrateTimeouts() {
    heading("7. Timeouts");

    try {
        const result = await withTimeout(
            promiseService("slow-service", 100),
            20,
        );

        console.log(result);
    } catch (error) {
        console.log("Timeout handled:", error.message);
    }

    /*
     * Promise.race stops waiting for the caller's result, but it does not
     * automatically cancel the underlying operation.
     */
}


// ---------------------------------------------------------------------------
// 8. ABORTCONTROLLER FOR CANCELLATION
// ---------------------------------------------------------------------------

function cancellableOperation(signal, delay = 100) {
    return new Promise((resolve, reject) => {
        if (signal.aborted) {
            reject(new Error("Operation was already cancelled"));
            return;
        }

        const timer = setTimeout(() => {
            resolve("Cancellable operation completed.");
        }, delay);

        signal.addEventListener(
            "abort",
            () => {
                clearTimeout(timer);
                reject(new Error("Cancellable operation aborted."));
            },
            { once: true },
        );
    });
}

async function demonstrateCancellation() {
    heading("8. Cancellation with AbortController");

    const controller = new AbortController();

    const operation = cancellableOperation(controller.signal, 100);

    setTimeout(() => controller.abort(), 15);

    try {
        await operation;
    } catch (error) {
        console.log(error.message);
    }
}


// ---------------------------------------------------------------------------
// 9. RETRIES AND EXPONENTIAL BACKOFF
// ---------------------------------------------------------------------------

function sleep(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function retry(operation, options = {}) {
    const {
        attempts = 3,
        baseDelay = 10,
    } = options;

    let lastError;

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
        try {
            return await operation();
        } catch (error) {
            lastError = error;

            if (attempt === attempts) {
                break;
            }

            const exponentialDelay = baseDelay * (2 ** (attempt - 1));
            const jitter = Math.random() * exponentialDelay * 0.25;

            await sleep(exponentialDelay + jitter);
        }
    }

    throw lastError;
}

async function demonstrateRetries() {
    heading("9. Retry with exponential backoff");

    let attempts = 0;

    const result = await retry(async () => {
        attempts += 1;

        if (attempts < 3) {
            throw new Error("Transient failure");
        }

        return "Operation succeeded after retry.";
    });

    console.log(result);
    console.log("Attempts:", attempts);
}


// ---------------------------------------------------------------------------
// 10. EVENT-DRIVEN ARCHITECTURE
// ---------------------------------------------------------------------------

const { EventEmitter } = require("node:events");

async function demonstrateEvents() {
    heading("10. Event-driven communication");

    const bus = new EventEmitter();

    const auditHandler = async (event) => {
        await sleep(10);
        console.log("Audit consumer processed:", event.eventId);
    };

    const notificationHandler = async (event) => {
        await sleep(15);
        console.log("Notification consumer processed:", event.eventId);
    };

    bus.on("order.created", (event) => {
        void auditHandler(event);
    });

    bus.on("order.created", (event) => {
        void notificationHandler(event);
    });

    const event = {
        eventId: "evt-1001",
        orderId: "ORD-2001",
        amount: 2500,
    };

    bus.emit("order.created", event);

    await sleep(25);
    bus.removeAllListeners();
}


// ---------------------------------------------------------------------------
// 11. ASYNCHRONOUS JOB API
// ---------------------------------------------------------------------------

class JobService {
    constructor() {
        this.jobs = new Map();
    }

    submitJob() {
        const jobId = `job-${Date.now()}-${Math.random()
            .toString(16)
            .slice(2)}`;

        const job = {
            jobId,
            status: "queued",
            progress: 0,
            result: null,
        };

        this.jobs.set(jobId, job);
        void this.#run(job);

        return job;
    }

    async #run(job) {
        job.status = "running";

        for (let progress = 0; progress <= 100; progress += 25) {
            await sleep(15);
            job.progress = progress;
        }

        job.status = "completed";
        job.result = "Report generated successfully.";
    }

    getStatus(jobId) {
        const job = this.jobs.get(jobId);

        if (!job) {
            throw new Error("Unknown job ID");
        }

        return { ...job };
    }
}

async function demonstrateLongRunningJob() {
    heading("11. Long-running asynchronous job");

    const service = new JobService();
    const job = service.submitJob();

    console.log("Job accepted:", job.jobId);

    while (true) {
        const status = service.getStatus(job.jobId);

        console.log(
            `status=${status.status}, progress=${status.progress}%`,
        );

        if (status.status === "completed") {
            console.log("Result:", status.result);
            break;
        }

        await sleep(10);
    }
}


// ---------------------------------------------------------------------------
// 12. QUEUE AND BACKPRESSURE
// ---------------------------------------------------------------------------

class AsyncQueue {
    constructor(maxSize = 3) {
        this.maxSize = maxSize;
        this.items = [];
        this.waitingConsumers = [];
        this.waitingProducers = [];
    }

    async put(item) {
        if (this.waitingConsumers.length > 0) {
            const resolve = this.waitingConsumers.shift();
            resolve(item);
            return;
        }

        if (this.items.length < this.maxSize) {
            this.items.push(item);
            return;
        }

        await new Promise((resolve) => {
            this.waitingProducers.push({ item, resolve });
        });
    }

    async get() {
        if (this.items.length > 0) {
            const item = this.items.shift();
            this.#releaseProducer();
            return item;
        }

        return new Promise((resolve) => {
            this.waitingConsumers.push(resolve);
        });
    }

    #releaseProducer() {
        if (this.waitingProducers.length === 0) {
            return;
        }

        const producer = this.waitingProducers.shift();
        this.items.push(producer.item);
        producer.resolve();
    }
}

async function demonstrateQueue() {
    heading("12. Queue-based asynchronous processing");

    const workQueue = new AsyncQueue(2);
    const stopToken = Symbol("STOP");

    async function consumer(name) {
        while (true) {
            const item = await workQueue.get();

            if (item === stopToken) {
                return;
            }

            await sleep(12);
            console.log(`${name} processed ${item}`);
        }
    }

    const consumers = [
        consumer("worker-1"),
        consumer("worker-2"),
    ];

    for (let number = 1; number <= 6; number += 1) {
        await workQueue.put(`item-${number}`);
        console.log(`Produced item-${number}`);
    }

    await Promise.all([
        workQueue.put(stopToken),
        workQueue.put(stopToken),
    ]);

    await Promise.all(consumers);

    console.log(
        "The bounded queue applies backpressure when producers outpace consumers.",
    );
}


// ---------------------------------------------------------------------------
// 13. DEPENDENCY-AWARE WORKFLOW
// ---------------------------------------------------------------------------

class WorkflowEngine {
    constructor(steps) {
        this.steps = new Map(steps.map((step) => [step.name, step]));
        this.completed = new Set();
        this.results = new Map();
    }

    async run() {
        const pending = new Set(this.steps.keys());

        while (pending.size > 0) {
            const ready = [];

            for (const name of pending) {
                const step = this.steps.get(name);

                const dependenciesSatisfied = [...step.dependencies]
                    .every((dependency) => this.completed.has(dependency));

                if (dependenciesSatisfied) {
                    ready.push(step);
                }
            }

            if (ready.length === 0) {
                throw new Error(
                    "Workflow cannot progress: missing dependency or cycle.",
                );
            }

            const results = await Promise.all(
                ready.map(async (step) => {
                    console.log(`Starting ${step.name}`);
                    const result = await step.action();
                    console.log(`Completed ${step.name}`);
                    return result;
                }),
            );

            ready.forEach((step, index) => {
                this.completed.add(step.name);
                this.results.set(step.name, results[index]);
                pending.delete(step.name);
            });
        }

        return Object.fromEntries(this.results);
    }
}

async function demonstrateWorkflowEngine() {
    heading("13. Dependency-aware asynchronous workflow");

    const delayAction = (name, delay) => async () => {
        await sleep(delay);
        return `${name}: OK`;
    };

    const steps = [
        {
            name: "validate",
            dependencies: [],
            action: delayAction("validate", 15),
        },
        {
            name: "authorize",
            dependencies: ["validate"],
            action: delayAction("authorize", 15),
        },
        {
            name: "reserve",
            dependencies: ["authorize"],
            action: delayAction("reserve", 25),
        },
        {
            name: "notify",
            dependencies: ["authorize"],
            action: delayAction("notify", 25),
        },
        {
            name: "charge",
            dependencies: ["reserve"],
            action: delayAction("charge", 15),
        },
    ];

    const engine = new WorkflowEngine(steps);
    const results = await engine.run();

    console.log("Workflow results:", results);
}


// ---------------------------------------------------------------------------
// 14. IDEMPOTENCY
// ---------------------------------------------------------------------------

class PaymentProcessor {
    constructor() {
        this.processedRequests = new Map();
    }

    async charge(idempotencyKey, amount) {
        if (this.processedRequests.has(idempotencyKey)) {
            return this.processedRequests.get(idempotencyKey);
        }

        if (!Number.isFinite(amount) || amount <= 0) {
            throw new Error("Amount must be a positive finite number.");
        }

        await sleep(10);

        const result = {
            idempotencyKey,
            amount,
            status: "accepted",
        };

        this.processedRequests.set(idempotencyKey, result);

        return result;
    }
}

async function demonstrateIdempotency() {
    heading("14. Idempotent state-changing operation");

    const processor = new PaymentProcessor();

    const first = await processor.charge("request-001", 500);
    const retryResult = await processor.charge("request-001", 500);

    console.log("First:", first);
    console.log("Retry:", retryResult);
    console.log("Same stored result:", first === retryResult);
}


// ---------------------------------------------------------------------------
// 15. CIRCUIT BREAKER
// ---------------------------------------------------------------------------

class CircuitBreaker {
    constructor(failureThreshold = 2, recoveryMilliseconds = 50) {
        this.failureThreshold = failureThreshold;
        this.recoveryMilliseconds = recoveryMilliseconds;
        this.failures = 0;
        this.state = "CLOSED";
        this.openedAt = 0;
    }

    canExecute() {
        if (this.state === "CLOSED") {
            return true;
        }

        if (
            this.state === "OPEN" &&
            Date.now() - this.openedAt >= this.recoveryMilliseconds
        ) {
            this.state = "HALF_OPEN";
            return true;
        }

        return this.state === "HALF_OPEN";
    }

    success() {
        this.failures = 0;
        this.state = "CLOSED";
    }

    failure() {
        this.failures += 1;

        if (this.failures >= this.failureThreshold) {
            this.state = "OPEN";
            this.openedAt = Date.now();
        }
    }
}

async function demonstrateCircuitBreaker() {
    heading("15. Circuit breaker");

    const breaker = new CircuitBreaker(2, 30);

    for (let attempt = 1; attempt <= 4; attempt += 1) {
        if (!breaker.canExecute()) {
            console.log(`Attempt ${attempt}: rejected immediately.`);
            continue;
        }

        breaker.failure();
        console.log(
            `Attempt ${attempt}: failure, state=${breaker.state}`,
        );
    }

    await sleep(35);

    if (breaker.canExecute()) {
        console.log("Recovery probe allowed.");
        breaker.success();
        console.log("State:", breaker.state);
    }
}


// ---------------------------------------------------------------------------
// 16. VALIDATION AND SECURITY
// ---------------------------------------------------------------------------

function validateOrder(order) {
    if (!order || typeof order !== "object") {
        throw new TypeError("Order must be an object.");
    }

    if (
        typeof order.customerId !== "string" ||
        order.customerId.trim() === ""
    ) {
        throw new Error("customerId is required.");
    }

    if (!Number.isFinite(order.amount) || order.amount <= 0) {
        throw new Error("amount must be a positive finite number.");
    }

    if (order.amount > 1_000_000) {
        throw new Error("amount exceeds transaction limit.");
    }

    return true;
}

function demonstrateValidation() {
    heading("16. Boundary validation");

    const validOrder = {
        customerId: "CUS-001",
        amount: 2500,
    };

    validateOrder(validOrder);
    console.log("Valid order accepted.");

    const invalidOrders = [
        { customerId: "", amount: 100 },
        { customerId: "CUS-002", amount: 0 },
        { customerId: "CUS-003", amount: 2_000_000 },
    ];

    for (const order of invalidOrders) {
        try {
            validateOrder(order);
        } catch (error) {
            console.log("Rejected:", error.message);
        }
    }

    console.log("Security design should include:");
    console.log("- TLS for network communication");
    console.log("- authentication and authorization");
    console.log("- strict input validation");
    console.log("- rate limiting");
    console.log("- bounded resources");
    console.log("- safe secret handling");
    console.log("- timeouts and cancellation");
    console.log("- idempotency for retryable writes");
});


// ---------------------------------------------------------------------------
// 17. OBSERVABILITY
// ---------------------------------------------------------------------------

async function measuredOperation(name, delay) {
    const startedAt = performance.now();

    try {
        await sleep(delay);

        return {
            operation: name,
            status: "success",
            durationMilliseconds: performance.now() - startedAt,
        };
    } catch (error) {
        return {
            operation: name,
            status: "failure",
            durationMilliseconds: performance.now() - startedAt,
            error: error.message,
        };
    }
}

async function demonstrateObservability() {
    heading("17. Observability");

    const measurements = await Promise.all([
        measuredOperation("database", 15),
        measuredOperation("cache", 8),
        measuredOperation("external-api", 25),
    ]);

    for (const measurement of measurements) {
        console.log(
            `${measurement.operation}: ` +
            `${measurement.durationMilliseconds.toFixed(2)}ms ` +
            `${measurement.status}`,
        );
    }
}


// ---------------------------------------------------------------------------
// 18. PRACTICAL ARCHITECTURE CASE STUDY
// ---------------------------------------------------------------------------

async function placeOrder(order) {
    /*
     * A realistic request can combine synchronous validation with
     * asynchronous I/O.
     *
     * The caller should not confuse "request accepted" with
     * "every downstream side effect has completed".
     */
    validateOrder(order);

    const [inventory, fraudCheck] = await Promise.all([
        promiseService("inventory reservation", 15),
        promiseService("fraud screening", 20),
    ]);

    const payment = await promiseService("payment authorization", 15);

    return {
        orderId: order.orderId,
        inventory,
        fraudCheck,
        payment,
        status: "accepted",
    };
}

async function demonstrateOrderArchitecture() {
    heading("18. Practical order-processing architecture");

    const order = {
        orderId: "ORD-9001",
        customerId: "CUS-9001",
        amount: 4999,
    };

    const result = await placeOrder(order);
    console.log(result);

    /*
     * Independent operations were started concurrently.
     * Payment waited until the first-stage checks completed.
     * This is a dependency-aware workflow rather than indiscriminate
     * parallel execution.
     */
}


// ---------------------------------------------------------------------------
// 19. PERFORMANCE AND DESIGN PRINCIPLES
// ---------------------------------------------------------------------------

function demonstrateDesignPrinciples() {
    heading("19. Performance and architectural principles");

    const principles = [
        ["Synchronous", "Caller waits for completion."],
        ["Blocking", "Current execution cannot progress while waiting."],
        ["Non-blocking", "Caller can continue before completion."],
        ["Asynchronous", "Completion is handled independently of invocation."],
        ["Concurrency", "Multiple operations overlap in time."],
        ["Parallelism", "Multiple computations execute simultaneously."],
        ["Timeout", "Bounds how long a caller waits."],
        ["Retry", "Recovers from selected transient failures."],
        ["Queue", "Decouples producers and consumers."],
        ["Backpressure", "Prevents uncontrolled work accumulation."],
        ["Idempotency", "Makes safe retries possible for state-changing requests."],
        ["Circuit breaker", "Fails fast during repeated downstream failure."],
    ];

    for (const [term, definition] of principles) {
        console.log(`${term.padEnd(18)} ${definition}`);
    }

    console.log("\nImportant trade-offs:");
    console.log("- Async code can improve I/O throughput but increases complexity.");
    console.log("- Too many concurrent operations can exhaust sockets or memory.");
    console.log("- Retries can amplify traffic during an outage.");
    console.log("- Queues improve decoupling but introduce eventual consistency.");
    console.log("- Parallel work is useful only when dependencies permit it.");
}


// ---------------------------------------------------------------------------
// 20. MAIN
// ---------------------------------------------------------------------------

async function main() {
    demonstrateSynchronousExecution();
    await demonstrateBlocking();
    await demonstrateCallbacks();
    await demonstratePromises();
    await demonstratePromiseConcurrency();
    await demonstrateAllSettled();
    await demonstrateTimeouts();
    await demonstrateCancellation();
    await demonstrateRetries();
    await demonstrateEvents();
    await demonstrateLongRunningJob();
    await demonstrateQueue();
    await demonstrateWorkflowEngine();
    await demonstrateIdempotency();
    await demonstrateCircuitBreaker();
    demonstrateValidation();
    await demonstrateObservability();
    await demonstrateOrderArchitecture();
    demonstrateDesignPrinciples();

    heading("21. Completion");
    console.log(
        "The examples covered synchronous, blocking, non-blocking, " +
        "asynchronous, event-driven, queued, and dependency-aware workflows.",
    );
}

main().catch((error) => {
    console.error("Unhandled application error:", error);
    process.exitCode = 1;
});
