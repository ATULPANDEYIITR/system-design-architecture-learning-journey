"use strict";

/*
 * Monolith Architecture: Event-driven application model.
 *
 * Demonstrates:
 * - Module boundaries inside one deployment
 * - Event-driven internal communication
 * - Shared state and transaction-like rollback
 * - Request processing
 * - Performance measurements
 * - Scaling and deployment constraints
 * - Failure handling and idempotency
 */

const { performance } = require("node:perf_hooks");
const { randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

class DomainError extends Error {
    constructor(message, code) {
        super(message);
        this.name = "DomainError";
        this.code = code;
    }
}

const OrderState = Object.freeze({
    CREATED: "CREATED",
    PAID: "PAID",
    FAILED: "FAILED"
});

class Metrics {
    constructor() {
        this.requests = 0;
        this.failures = 0;
        this.latencies = [];
        this.moduleCalls = new Map();
    }

    increment(moduleName) {
        this.moduleCalls.set(
            moduleName,
            (this.moduleCalls.get(moduleName) || 0) + 1
        );
    }

    record(duration, failed) {
        this.requests++;
        this.failures += failed ? 1 : 0;
        this.latencies.push(duration);
    }

    report() {
        const sorted = [...this.latencies].sort((a, b) => a - b);
        const average = sorted.length
            ? sorted.reduce((sum, value) => sum + value, 0) / sorted.length
            : 0;

        const percentile = (p) => {
            if (!sorted.length) return 0;
            return sorted[Math.min(
                sorted.length - 1,
                Math.ceil(p * sorted.length) - 1
            )];
        };

        return {
            requests: this.requests,
            failures: this.failures,
            failureRate: this.requests
                ? this.failures / this.requests
                : 0,
            averageMs: Number(average.toFixed(3)),
            p95Ms: Number(percentile(0.95).toFixed(3)),
            moduleCalls: Object.fromEntries(this.moduleCalls)
        };
    }
}

class SharedDatabase {
    constructor() {
        this.users = new Map();
        this.products = new Map();
        this.orders = new Map();
        this.payments = new Map();
    }

    snapshot() {
        return {
            products: new Map(
                [...this.products].map(([id, product]) => [
                    id,
                    { ...product }
                ])
            ),
            orders: new Map(
                [...this.orders].map(([id, order]) => [
                    id,
                    { ...order }
                ])
            ),
            payments: new Map(
                [...this.payments].map(([id, payment]) => [
                    id,
                    { ...payment }
                ])
            )
        };
    }

    restore(snapshot) {
        this.products = snapshot.products;
        this.orders = snapshot.orders;
        this.payments = snapshot.payments;
    }
}

class EventBus extends EventEmitter {
    publish(eventName, payload) {
        this.emit(eventName, Object.freeze({ ...payload }));
    }
}

class UserModule {
    constructor(database) {
        this.database = database;
    }

    register(id, email) {
        if (!Number.isSafeInteger(id) || id <= 0) {
            throw new DomainError("Invalid user ID", "INVALID_USER");
        }

        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            throw new DomainError("Invalid email", "INVALID_EMAIL");
        }

        if (this.database.users.has(id)) {
            throw new DomainError("User already exists", "DUPLICATE_USER");
        }

        this.database.users.set(id, { id, email });
    }
}

class InventoryModule {
    constructor(database, events) {
        this.database = database;
        this.events = events;
    }

    addProduct(id, name, price, stock) {
        if (
            !Number.isSafeInteger(id) ||
            id <= 0 ||
            !name.trim() ||
            !Number.isFinite(price) ||
            price < 0 ||
            !Number.isSafeInteger(stock) ||
            stock < 0
        ) {
            throw new DomainError("Invalid product", "INVALID_PRODUCT");
        }

        if (this.database.products.has(id)) {
            throw new DomainError("Product already exists", "DUPLICATE_PRODUCT");
        }

        this.database.products.set(id, {
            id,
            name,
            price,
            stock
        });
    }

    reserve(productId, quantity) {
        if (!Number.isSafeInteger(quantity) || quantity <= 0) {
            throw new DomainError("Invalid quantity", "INVALID_QUANTITY");
        }

        const product = this.database.products.get(productId);

        if (!product) {
            throw new DomainError("Product not found", "PRODUCT_NOT_FOUND");
        }

        if (product.stock < quantity) {
            throw new DomainError("Insufficient stock", "OUT_OF_STOCK");
        }

        product.stock -= quantity;

        this.events.publish("inventory.reserved", {
            productId,
            quantity,
            remaining: product.stock
        });

        return product.price * quantity;
    }
}

class PaymentModule {
    constructor(database, events) {
        this.database = database;
        this.events = events;
        this.failureMode = false;
    }

    async charge(orderId, amount) {
        if (!Number.isFinite(amount) || amount <= 0) {
            throw new DomainError("Invalid amount", "INVALID_AMOUNT");
        }

        if (this.database.payments.has(orderId)) {
            return this.database.payments.get(orderId);
        }

        // Simulate an external payment dependency failure.
        await Promise.resolve();

        if (this.failureMode) {
            throw new DomainError(
                "Payment provider unavailable",
                "PAYMENT_UNAVAILABLE"
            );
        }

        const payment = Object.freeze({
            id: randomUUID(),
            orderId,
            amount,
            status: "COMPLETED"
        });

        this.database.payments.set(orderId, payment);

        this.events.publish("payment.completed", {
            orderId,
            amount
        });

        return payment;
    }
}

class OrderModule {
    constructor(database, inventory, payments, metrics, events) {
        this.database = database;
        this.inventory = inventory;
        this.payments = payments;
        this.metrics = metrics;
        this.events = events;
        this.idempotencyKeys = new Map();
    }

    async create(userId, productId, quantity, idempotencyKey) {
        const start = performance.now();
        let failed = true;

        try {
            if (!idempotencyKey || typeof idempotencyKey !== "string") {
                throw new DomainError(
                    "Idempotency key required",
                    "INVALID_IDEMPOTENCY_KEY"
                );
            }

            if (this.idempotencyKeys.has(idempotencyKey)) {
                return this.idempotencyKeys.get(idempotencyKey);
            }

            if (!this.database.users.has(userId)) {
                throw new DomainError("Unknown user", "USER_NOT_FOUND");
            }

            const snapshot = this.database.snapshot();

            try {
                this.metrics.increment("inventory");
                const total = this.inventory.reserve(productId, quantity);

                const order = {
                    id: randomUUID(),
                    userId,
                    productId,
                    quantity,
                    total,
                    status: OrderState.CREATED
                };

                this.database.orders.set(order.id, order);

                this.metrics.increment("payments");
                await this.payments.charge(order.id, total);

                order.status = OrderState.PAID;

                const result = Object.freeze({ ...order });
                this.idempotencyKeys.set(idempotencyKey, result);

                this.events.publish("order.paid", {
                    orderId: order.id,
                    total
                });

                failed = false;
                return result;

            } catch (error) {
                this.database.restore(snapshot);
                throw error;
            }

        } finally {
            this.metrics.record(performance.now() - start, failed);
        }
    }
}

class MonolithicApplication {
    constructor(instanceId, database = new SharedDatabase()) {
        this.instanceId = instanceId;
        this.database = database;
        this.events = new EventBus();
        this.metrics = new Metrics();

        this.users = new UserModule(database);
        this.inventory = new InventoryModule(database, this.events);
        this.payments = new PaymentModule(database, this.events);
        this.orders = new OrderModule(
            database,
            this.inventory,
            this.payments,
            this.metrics,
            this.events
        );

        this.events.on("order.paid", (event) => {
            process.stdout.write(
                `[${this.instanceId}] Order paid: ${event.orderId}\n`
            );
        });
    }

    health() {
        return {
            instance: this.instanceId,
            status: "healthy",
            moduleCount: 4,
            databaseConnected: Boolean(this.database)
        };
    }
}

class MonolithDeployment {
    constructor(instanceCount = 1) {
        if (!Number.isSafeInteger(instanceCount) || instanceCount < 1) {
            throw new DomainError(
                "At least one instance is required",
                "INVALID_INSTANCE_COUNT"
            );
        }

        this.database = new SharedDatabase();
        this.instances = Array.from(
            { length: instanceCount },
            (_, index) => new MonolithicApplication(
                `monolith-${index + 1}`,
                this.database
            )
        );

        this.nextInstance = 0;
    }

    selectInstance() {
        const instance = this.instances[
            this.nextInstance % this.instances.length
        ];

        this.nextInstance++;
        return instance;
    }

    scaleOut(count) {
        if (!Number.isSafeInteger(count) || count <= 0) {
            throw new DomainError("Invalid scale-out count", "INVALID_SCALE");
        }

        const start = this.instances.length;

        for (let index = 0; index < count; index++) {
            this.instances.push(
                new MonolithicApplication(
                    `monolith-${start + index + 1}`,
                    this.database
                )
            );
        }
    }
}

async function main() {
    console.log("MONOLITH ARCHITECTURE");
    console.log("=====================");

    const deployment = new MonolithDeployment(1);
    const application = deployment.selectInstance();

    application.users.register(1, "admin@example.com");

    application.inventory.addProduct(
        100,
        "Database Server",
        2500,
        20
    );

    application.events.on("inventory.reserved", (event) => {
        console.log("Inventory event:", event);
    });

    const order = await application.orders.create(
        1,
        100,
        2,
        "request-1001"
    );

    console.log("Created order:", order);

    // Repeated request returns the previous result.
    const repeated = await application.orders.create(
        1,
        100,
        2,
        "request-1001"
    );

    console.log("Idempotent request:", repeated.id === order.id);

    // Failed payment restores application state.
    application.payments.failureMode = true;

    try {
        await application.orders.create(
            1,
            100,
            1,
            "request-1002"
        );
    } catch (error) {
        console.log("Expected failure:", error.code);
    }

    console.log(
        "Inventory after rollback:",
        application.database.products.get(100).stock
    );

    console.log("Metrics:", application.metrics.report());

    deployment.scaleOut(2);

    console.log("Instances after scale-out:", deployment.instances.length);

    console.log(
        "Shared database:",
        deployment.instances.every(
            instance => instance.database === deployment.database
        )
    );

    console.log("Health:", application.health());

    console.log("\nArchitecture tradeoffs:");
    console.log("- Simple deployment and in-process communication.");
    console.log("- Shared transactions and centralized data ownership.");
    console.log("- Complete application instances required for scale-out.");
    console.log("- Shared resources can create contention.");
    console.log("- A process-wide failure can affect every module.");
    console.log("- Independent module deployment is not supported.");
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
