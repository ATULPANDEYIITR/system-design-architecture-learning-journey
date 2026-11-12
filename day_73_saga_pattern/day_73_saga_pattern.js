"use strict";

/*
 * Saga Pattern: Event-Driven Distributed Transaction Management
 *
 * Node.js 18+
 *
 * Demonstrates:
 * - Event-driven orchestration
 * - Asynchronous service execution
 * - Forward actions and compensations
 * - Retry policies
 * - Idempotency
 * - Transaction state transitions
 * - Execution event history
 */

const { randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

const SagaStatus = Object.freeze({
    PENDING: "PENDING",
    RUNNING: "RUNNING",
    COMPENSATING: "COMPENSATING",
    COMPLETED: "COMPLETED",
    COMPENSATED: "COMPENSATED",
    FAILED: "FAILED"
});

const StepStatus = Object.freeze({
    PENDING: "PENDING",
    COMPLETED: "COMPLETED",
    COMPENSATED: "COMPENSATED",
    FAILED: "FAILED"
});

class SagaError extends Error {}

class RetryPolicy {
    constructor(maxAttempts = 3, initialDelay = 50) {
        if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
            throw new TypeError("maxAttempts must be positive");
        }

        this.maxAttempts = maxAttempts;
        this.initialDelay = initialDelay;
    }

    async execute(operation) {
        let lastError;

        for (let attempt = 1; attempt <= this.maxAttempts; attempt++) {
            try {
                return await operation();
            } catch (error) {
                lastError = error;

                if (attempt === this.maxAttempts) {
                    break;
                }

                const delay = Math.min(
                    this.initialDelay * 2 ** (attempt - 1),
                    1000
                );

                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }

        throw lastError;
    }
}

class IdempotentService {
    constructor(name) {
        this.name = name;
        this.completedOperations = new Map();
    }

    async perform(key, operation) {
        if (this.completedOperations.has(key)) {
            return this.completedOperations.get(key);
        }

        const result = await operation();

        this.completedOperations.set(key, result);

        return result;
    }
}

class InventoryService extends IdempotentService {
    constructor() {
        super("Inventory");
        this.reservations = new Set();
    }

    async reserve(orderId) {
        return this.perform(`${orderId}:reserve`, async () => {
            this.reservations.add(orderId);
            return { orderId, reserved: true };
        });
    }

    async release(orderId) {
        this.reservations.delete(orderId);
        this.completedOperations.delete(`${orderId}:reserve`);
    }
}

class PaymentService extends IdempotentService {
    constructor() {
        super("Payment");
        this.charges = new Map();
    }

    async charge(orderId, amount) {
        return this.perform(`${orderId}:charge`, async () => {
            if (!Number.isFinite(amount) || amount <= 0) {
                throw new SagaError("Invalid payment amount");
            }

            this.charges.set(orderId, amount);

            return { orderId, amount, charged: true };
        });
    }

    async refund(orderId) {
        this.charges.delete(orderId);
        this.completedOperations.delete(`${orderId}:charge`);
    }
}

class ShippingService extends IdempotentService {
    constructor() {
        super("Shipping");
        this.shipments = new Set();
    }

    async create(orderId, shouldFail = false) {
        return this.perform(`${orderId}:shipment`, async () => {
            if (shouldFail) {
                throw new SagaError("Shipping service unavailable");
            }

            this.shipments.add(orderId);

            return { orderId, shipmentCreated: true };
        });
    }

    async cancel(orderId) {
        this.shipments.delete(orderId);
        this.completedOperations.delete(`${orderId}:shipment`);
    }
}

class SagaStep {
    constructor(name, action, compensation, retryPolicy) {
        this.name = name;
        this.action = action;
        this.compensation = compensation;
        this.retryPolicy = retryPolicy;
        this.status = StepStatus.PENDING;
        this.error = null;
    }
}

class Saga extends EventEmitter {
    constructor(orderId, steps) {
        super();

        this.id = randomUUID();
        this.orderId = orderId;
        this.steps = steps;
        this.status = SagaStatus.PENDING;
        this.completedSteps = [];
        this.history = [];
    }

    record(event, details = {}) {
        const entry = {
            timestamp: new Date().toISOString(),
            sagaId: this.id,
            event,
            details
        };

        this.history.push(entry);
        this.emit("saga-event", entry);
    }
}

class SagaOrchestrator {
    async execute(saga) {
        if (saga.status !== SagaStatus.PENDING) {
            throw new SagaError("Saga can only be executed once");
        }

        saga.status = SagaStatus.RUNNING;
        saga.record("SAGA_STARTED", {
            orderId: saga.orderId
        });

        try {
            for (const step of saga.steps) {
                saga.record("STEP_STARTED", {
                    step: step.name
                });

                try {
                    await step.retryPolicy.execute(step.action);

                    step.status = StepStatus.COMPLETED;
                    saga.completedSteps.push(step);

                    saga.record("STEP_COMPLETED", {
                        step: step.name
                    });
                } catch (error) {
                    step.status = StepStatus.FAILED;
                    step.error = error.message;

                    saga.record("STEP_FAILED", {
                        step: step.name,
                        error: error.message
                    });

                    throw error;
                }
            }

            saga.status = SagaStatus.COMPLETED;
            saga.record("SAGA_COMPLETED");

        } catch (error) {
            saga.record("COMPENSATION_TRIGGERED", {
                reason: error.message
            });

            await this.compensate(saga);
        }

        return saga.status;
    }

    async compensate(saga) {
        saga.status = SagaStatus.COMPENSATING;

        const failures = [];

        for (const step of [...saga.completedSteps].reverse()) {
            try {
                await step.compensation();

                step.status = StepStatus.COMPENSATED;

                saga.record("STEP_COMPENSATED", {
                    step: step.name
                });
            } catch (error) {
                failures.push({
                    step: step.name,
                    error: error.message
                });

                saga.record("COMPENSATION_FAILED", {
                    step: step.name,
                    error: error.message
                });
            }
        }

        saga.status = failures.length
            ? SagaStatus.FAILED
            : SagaStatus.COMPENSATED;

        if (failures.length) {
            saga.record("MANUAL_RECOVERY_REQUIRED", {
                failures
            });
        } else {
            saga.record("SAGA_COMPENSATED");
        }
    }
}

function buildOrderSaga({
    orderId,
    amount,
    inventory,
    payment,
    shipping,
    failShipping = false
}) {
    if (!orderId || typeof orderId !== "string") {
        throw new TypeError("Valid order ID required");
    }

    if (!Number.isFinite(amount) || amount <= 0) {
        throw new TypeError("Amount must be positive");
    }

    const retry = new RetryPolicy(2, 50);

    return new Saga(orderId, [
        new SagaStep(
            "Reserve Inventory",
            () => inventory.reserve(orderId),
            () => inventory.release(orderId),
            retry
        ),

        new SagaStep(
            "Charge Payment",
            () => payment.charge(orderId, amount),
            () => payment.refund(orderId),
            retry
        ),

        new SagaStep(
            "Create Shipment",
            () => shipping.create(orderId, failShipping),
            () => shipping.cancel(orderId),
            retry
        )
    ]);
}

async function main() {
    const inventory = new InventoryService();
    const payment = new PaymentService();
    const shipping = new ShippingService();

    const orchestrator = new SagaOrchestrator();

    const scenarios = [
        {
            orderId: "ORDER-2001",
            amount: 1250,
            failShipping: false
        },
        {
            orderId: "ORDER-2002",
            amount: 2400,
            failShipping: true
        }
    ];

    for (const scenario of scenarios) {
        const saga = buildOrderSaga({
            ...scenario,
            inventory,
            payment,
            shipping
        });

        saga.on("saga-event", event => {
            console.log(
                `[${event.event}]`,
                JSON.stringify(event.details)
            );
        });

        const result = await orchestrator.execute(saga);

        console.log("Order:", saga.orderId);
        console.log("Saga status:", result);
        console.log("History entries:", saga.history.length);
        console.log("--------------------------------");
    }

    console.log("Final inventory:", [...inventory.reservations]);
    console.log("Final payments:", [...payment.charges.entries()]);
    console.log("Final shipments:", [...shipping.shipments]);

    if (!inventory.reservations.has("ORDER-2002")) {
        console.log("Failed order inventory successfully released.");
    }

    if (payment.charges.has("ORDER-2002")) {
        throw new Error("Compensation assertion failed");
    }

    if (shipping.shipments.has("ORDER-2002")) {
        throw new Error("Unexpected shipment exists");
    }
}

main().catch(error => {
    console.error("Application failure:", error);
    process.exitCode = 1;
});
