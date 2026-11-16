"use strict";

/*
 * Clean Architecture: Dependency Inversion and Boundaries
 *
 * Event-driven architecture validation and order processing.
 *
 * Demonstrates:
 * - Dependency boundaries
 * - Ports and adapters
 * - Runtime dependency injection
 * - Event-driven use cases
 * - Asynchronous infrastructure
 * - Policy evaluation
 * - Dependency graph analysis
 * - Request validation
 * - Idempotency
 * - Failure handling
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const { randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");
const fs = require("node:fs/promises");
const path = require("node:path");

// ============================================================
// 1. DOMAIN LAYER
// ============================================================

class DomainError extends Error {}
class ApplicationError extends Error {}
class InfrastructureError extends Error {}

const OrderStatus = Object.freeze({
    PENDING: "PENDING",
    PAID: "PAID",
    CANCELLED: "CANCELLED"
});

class Money {
    constructor(amount, currency = "INR") {
        if (!Number.isFinite(amount) || amount < 0) {
            throw new DomainError("Invalid monetary amount.");
        }

        if (!/^[A-Za-z]{3}$/.test(currency)) {
            throw new DomainError("Invalid currency.");
        }

        this.amount = Math.round((amount + Number.EPSILON) * 100) / 100;
        this.currency = currency.toUpperCase();

        Object.freeze(this);
    }

    add(other) {
        if (this.currency !== other.currency) {
            throw new DomainError("Currency mismatch.");
        }

        return new Money(
            this.amount + other.amount,
            this.currency
        );
    }

    multiply(quantity) {
        if (!Number.isInteger(quantity) || quantity <= 0) {
            throw new DomainError("Invalid quantity.");
        }

        return new Money(
            this.amount * quantity,
            this.currency
        );
    }
}

class OrderLine {
    constructor(productId, quantity, unitPrice) {
        if (typeof productId !== "string" || !productId.trim()) {
            throw new DomainError("Product ID is required.");
        }

        if (!Number.isInteger(quantity) || quantity < 1 || quantity > 1000) {
            throw new DomainError("Quantity must be between 1 and 1000.");
        }

        if (!(unitPrice instanceof Money)) {
            throw new DomainError("Invalid unit price.");
        }

        this.productId = productId;
        this.quantity = quantity;
        this.unitPrice = unitPrice;

        Object.freeze(this);
    }

    get subtotal() {
        return this.unitPrice.multiply(this.quantity);
    }
}

class Order {
    constructor(customerId, lines, id = randomUUID()) {
        if (!customerId || !customerId.trim()) {
            throw new DomainError("Customer ID is required.");
        }

        if (!Array.isArray(lines) || lines.length === 0 || lines.length > 100) {
            throw new DomainError("Order must contain 1 to 100 lines.");
        }

        this.id = id;
        this.customerId = customerId;
        this.lines = Object.freeze([...lines]);
        this.status = OrderStatus.PENDING;
        this.version = 1;

        this.total();
    }

    total() {
        const currency = this.lines[0].unitPrice.currency;
        let result = new Money(0, currency);

        for (const line of this.lines) {
            result = result.add(line.subtotal);
        }

        return result;
    }

    markPaid() {
        if (this.status !== OrderStatus.PENDING) {
            throw new DomainError("Only pending orders can be paid.");
        }

        this.status = OrderStatus.PAID;
        this.version++;
    }

    cancel() {
        if (this.status !== OrderStatus.PENDING) {
            throw new DomainError(
                "Only pending orders can be cancelled."
            );
        }

        this.status = OrderStatus.CANCELLED;
        this.version++;
    }

    toJSON() {
        return {
            id: this.id,
            customerId: this.customerId,
            status: this.status,
            version: this.version,
            lines: this.lines.map(line => ({
                productId: line.productId,
                quantity: line.quantity,
                amount: line.unitPrice.amount,
                currency: line.unitPrice.currency
            }))
        };
    }
}

// ============================================================
// 2. APPLICATION PORTS
// ============================================================

/*
 * JavaScript uses structural contracts.
 * Concrete adapters satisfy these interfaces by implementing
 * the required methods.
 */

function assertPort(object, methods, name) {
    for (const method of methods) {
        if (typeof object?.[method] !== "function") {
            throw new ApplicationError(
                `${name} must implement ${method}().`
            );
        }
    }
}

function validateDependencies(dependencies) {
    assertPort(
        dependencies.orderRepository,
        ["save", "findById"],
        "OrderRepository"
    );

    assertPort(
        dependencies.paymentGateway,
        ["charge"],
        "PaymentGateway"
    );

    assertPort(
        dependencies.eventPublisher,
        ["publish"],
        "EventPublisher"
    );
}

// ============================================================
// 3. INFRASTRUCTURE ADAPTERS
// ============================================================

class InMemoryOrderRepository {
    #orders = new Map();

    async save(order) {
        this.#orders.set(order.id, order);
    }

    async findById(id) {
        return this.#orders.get(id) ?? null;
    }

    async findAll() {
        return [...this.#orders.values()];
    }
}

class JsonOrderRepository {
    constructor(filePath) {
        this.filePath = path.resolve(filePath);
    }

    async #read() {
        try {
            const content = await fs.readFile(
                this.filePath,
                "utf8"
            );

            return JSON.parse(content);
        } catch (error) {
            if (error.code === "ENOENT") {
                return {};
            }

            throw new InfrastructureError(
                "Order storage could not be read."
            );
        }
    }

    async save(order) {
        const records = await this.#read();

        records[order.id] = order.toJSON();

        const temporary = `${this.filePath}.${randomUUID()}.tmp`;

        try {
            await fs.mkdir(path.dirname(this.filePath), {
                recursive: true
            });

            await fs.writeFile(
                temporary,
                JSON.stringify(records, null, 2),
                { encoding: "utf8", flag: "wx" }
            );

            await fs.rename(temporary, this.filePath);
        } catch (error) {
            await fs.rm(temporary, { force: true }).catch(() => {});

            throw new InfrastructureError(
                "Order persistence failed."
            );
        }
    }

    async findById(id) {
        const records = await this.#read();
        const record = records[id];

        if (!record) {
            return null;
        }

        const lines = record.lines.map(item => new OrderLine(
            item.productId,
            item.quantity,
            new Money(item.amount, item.currency)
        ));

        const order = new Order(
            record.customerId,
            lines,
            record.id
        );

        order.status = record.status;
        order.version = record.version;

        return order;
    }
}

class SimulatedPaymentGateway {
    #processed = new Set();

    constructor({ fail = false } = {}) {
        this.fail = fail;
    }

    async charge(orderId, amount) {
        if (this.#processed.has(orderId)) {
            return true;
        }

        if (this.fail) {
            return false;
        }

        if (!(amount instanceof Money)) {
            throw new InfrastructureError(
                "Invalid payment amount."
            );
        }

        this.#processed.add(orderId);

        return true;
    }
}

class EventBus extends EventEmitter {
    async publish(event) {
        this.emit(event.type, Object.freeze({ ...event }));
    }
}

// ============================================================
// 4. APPLICATION USE CASES
// ============================================================

class PlaceOrderUseCase {
    constructor(dependencies) {
        validateDependencies(dependencies);

        this.repository = dependencies.orderRepository;
        this.payment = dependencies.paymentGateway;
        this.events = dependencies.eventPublisher;
    }

    async execute(command) {
        const order = new Order(
            command.customerId,
            command.lines
        );

        await this.repository.save(order);

        try {
            const paid = await this.payment.charge(
                order.id,
                order.total()
            );

            if (!paid) {
                throw new ApplicationError("Payment declined.");
            }

            order.markPaid();

            await this.repository.save(order);

            await this.events.publish({
                type: "OrderPaid",
                orderId: order.id,
                customerId: order.customerId,
                total: order.total().amount,
                currency: order.total().currency
            });

            return order;

        } catch (error) {
            if (order.status === OrderStatus.PENDING) {
                order.cancel();
                await this.repository.save(order);
            }

            if (
                error instanceof ApplicationError ||
                error instanceof DomainError
            ) {
                throw error;
            }

            throw new ApplicationError(
                "Order processing failed."
            );
        }
    }
}

class CancelOrderUseCase {
    constructor(repository) {
        assertPort(repository, ["findById", "save"], "OrderRepository");
        this.repository = repository;
    }

    async execute(orderId) {
        const order = await this.repository.findById(orderId);

        if (!order) {
            throw new ApplicationError("Order not found.");
        }

        order.cancel();

        await this.repository.save(order);

        return order;
    }
}

// ============================================================
// 5. ARCHITECTURE POLICY ENGINE
// ============================================================

const Layers = Object.freeze({
    DOMAIN: "domain",
    APPLICATION: "application",
    ADAPTER: "adapter",
    INFRASTRUCTURE: "infrastructure"
});

const allowedDependencies = Object.freeze({
    domain: [],
    application: ["domain"],
    adapter: ["application", "domain"],
    infrastructure: ["application", "domain", "adapter"]
});

class ArchitecturePolicy {
    evaluate(edges) {
        const violations = [];

        for (const edge of edges) {
            if (!Object.values(Layers).includes(edge.fromLayer)) {
                violations.push(`Unknown source layer: ${edge.fromLayer}`);
                continue;
            }

            if (!Object.values(Layers).includes(edge.toLayer)) {
                violations.push(`Unknown target layer: ${edge.toLayer}`);
                continue;
            }

            if (
                !allowedDependencies[edge.fromLayer].includes(edge.toLayer)
            ) {
                violations.push(
                    `${edge.from} cannot depend on ${edge.to}.`
                );
            }
        }

        return {
            valid: violations.length === 0,
            violations
        };
    }

    detectCycles(graph) {
        const completed = new Set();
        const active = new Set();
        const path = [];
        const cycles = [];

        const visit = node => {
            if (active.has(node)) {
                const start = path.indexOf(node);
                cycles.push([...path.slice(start), node]);
                return;
            }

            if (completed.has(node)) {
                return;
            }

            active.add(node);
            path.push(node);

            for (const next of graph.get(node) ?? []) {
                visit(next);
            }

            path.pop();
            active.delete(node);
            completed.add(node);
        };

        for (const node of graph.keys()) {
            visit(node);
        }

        return cycles;
    }
}

// ============================================================
// 6. EVENT-DRIVEN APPLICATION MONITORING
// ============================================================

class OrderMonitoringAdapter {
    constructor(eventBus) {
        eventBus.on("OrderPaid", event => {
            console.log(
                `[EVENT] Order ${event.orderId} paid: ` +
                `${event.currency} ${event.total}`
            );
        });
    }
}

// ============================================================
// 7. COMPOSITION ROOT
// ============================================================

function buildApplication({ paymentFailure = false } = {}) {
    const repository = new InMemoryOrderRepository();
    const paymentGateway = new SimulatedPaymentGateway({
        fail: paymentFailure
    });

    const eventBus = new EventBus();

    new OrderMonitoringAdapter(eventBus);

    const placeOrder = new PlaceOrderUseCase({
        orderRepository: repository,
        paymentGateway,
        eventPublisher: eventBus
    });

    return {
        placeOrder,
        repository,
        eventBus
    };
}

// ============================================================
// 8. VALIDATION AND EXECUTABLE TESTS
// ============================================================

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

async function main() {
    console.log("CLEAN ARCHITECTURE DEMONSTRATION\n");

    const policy = new ArchitecturePolicy();

    const edges = [
        {
            from: "OrderUseCase",
            to: "Order",
            fromLayer: Layers.APPLICATION,
            toLayer: Layers.DOMAIN
        },
        {
            from: "PostgresAdapter",
            to: "OrderRepository",
            fromLayer: Layers.INFRASTRUCTURE,
            toLayer: Layers.APPLICATION
        },
        {
            from: "Order",
            to: "PostgresAdapter",
            fromLayer: Layers.DOMAIN,
            toLayer: Layers.INFRASTRUCTURE
        }
    ];

    const result = policy.evaluate(edges);

    assert(!result.valid, "Architecture violation should be detected.");

    console.log("Architecture violations:", result.violations);

    const graph = new Map([
        ["domain", ["application"]],
        ["application", ["adapter"]],
        ["adapter", ["domain"]]
    ]);

    console.log("Dependency cycles:", policy.detectCycles(graph));

    const app = buildApplication();

    const lines = [
        new OrderLine(
            "LAPTOP-01",
            1,
            new Money(65000)
        ),
        new OrderLine(
            "MOUSE-01",
            2,
            new Money(750)
        )
    ];

    const order = await app.placeOrder.execute({
        customerId: "CUSTOMER-100",
        lines
    });

    assert(order.status === OrderStatus.PAID, "Order must be paid.");

    assert(
        order.total().amount === 66500,
        "Order total must be correct."
    );

    console.log("\nOrder:", order.toJSON());

    const failedApp = buildApplication({
        paymentFailure: true
    });

    try {
        await failedApp.placeOrder.execute({
            customerId: "CUSTOMER-200",
            lines
        });

        throw new Error("Expected payment failure.");
    } catch (error) {
        assert(
            error instanceof ApplicationError,
            "Payment failure must be an application error."
        );

        const records = await failedApp.repository.findAll();

        assert(
            records[0].status === OrderStatus.CANCELLED,
            "Failed pending order must be cancelled."
        );

        console.log("Payment failure handled:", error.message);
    }

    try {
        new Money(-100);
        throw new Error("Negative money must fail.");
    } catch (error) {
        assert(error instanceof DomainError, "Domain validation failed.");
    }

    console.log("\nAll JavaScript demonstrations passed.");
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
