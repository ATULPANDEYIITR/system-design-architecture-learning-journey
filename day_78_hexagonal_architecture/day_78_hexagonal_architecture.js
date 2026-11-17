"use strict";

/*
 * Hexagonal Architecture: Ports and Adapters
 *
 * Demonstrates an event-driven order application with:
 * - Input ports and secondary ports
 * - Domain entities
 * - Application use cases
 * - Primary HTTP-like and CLI adapters
 * - Secondary persistence, inventory and payment adapters
 * - Dependency injection
 * - Policy evaluation
 * - Asynchronous processing
 * - Error handling and compensation
 *
 * Runtime: Node.js 18+
 */

const { randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

// ============================================================
// ERRORS
// ============================================================

class DomainError extends Error {}
class PortContractError extends Error {}
class ApplicationError extends Error {}
class ConcurrencyError extends Error {}

// ============================================================
// DOMAIN
// ============================================================

const OrderStatus = Object.freeze({
    PENDING: "PENDING",
    CONFIRMED: "CONFIRMED",
    CANCELLED: "CANCELLED"
});

class Money {
    constructor(minorUnits, currency = "INR") {
        if (!Number.isSafeInteger(minorUnits) || minorUnits <= 0) {
            throw new DomainError("Money must be a positive integer amount");
        }

        if (!/^[A-Z]{3}$/.test(currency)) {
            throw new DomainError("Invalid currency");
        }

        this.minorUnits = minorUnits;
        this.currency = currency;
        Object.freeze(this);
    }

    multiply(quantity) {
        if (!Number.isSafeInteger(quantity) || quantity <= 0) {
            throw new DomainError("Invalid quantity");
        }

        const result = this.minorUnits * quantity;

        if (!Number.isSafeInteger(result)) {
            throw new DomainError("Money overflow");
        }

        return new Money(result, this.currency);
    }

    toString() {
        return `${this.currency} ${(this.minorUnits / 100).toFixed(2)}`;
    }
}

class OrderLine {
    constructor(productId, quantity, unitPrice) {
        if (typeof productId !== "string" || !productId.trim()) {
            throw new DomainError("Product ID is required");
        }

        if (!Number.isSafeInteger(quantity) || quantity <= 0) {
            throw new DomainError("Quantity must be positive");
        }

        if (!(unitPrice instanceof Money)) {
            throw new DomainError("Unit price must be Money");
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
    constructor(customerId, lines) {
        if (!customerId?.trim()) {
            throw new DomainError("Customer ID is required");
        }

        if (!Array.isArray(lines) || lines.length === 0) {
            throw new DomainError("Order requires at least one line");
        }

        const currency = lines[0].unitPrice.currency;

        if (lines.some(line => line.unitPrice.currency !== currency)) {
            throw new DomainError("Mixed currencies are not supported");
        }

        this.id = randomUUID();
        this.customerId = customerId;
        this.lines = Object.freeze([...lines]);
        this.currency = currency;
        this.status = OrderStatus.PENDING;
        this.version = 0;
        this.createdAt = new Date().toISOString();
    }

    get totalMinorUnits() {
        return this.lines.reduce(
            (total, line) => total + line.subtotal.minorUnits,
            0
        );
    }

    confirm() {
        this.#transition(OrderStatus.PENDING, OrderStatus.CONFIRMED);
    }

    cancel() {
        this.#transition(OrderStatus.PENDING, OrderStatus.CANCELLED);
    }

    #transition(expected, next) {
        if (this.status !== expected) {
            throw new DomainError(
                `Cannot transition ${this.status} to ${next}`
            );
        }

        this.status = next;
        this.version++;
    }

    snapshot() {
        return Object.freeze({
            id: this.id,
            customerId: this.customerId,
            status: this.status,
            version: this.version,
            currency: this.currency,
            totalMinorUnits: this.totalMinorUnits,
            createdAt: this.createdAt
        });
    }
}

// ============================================================
// PORT CONTRACTS
// ============================================================

/*
 * JavaScript uses structural contracts.
 * These functions verify required capabilities at composition time.
 */

function requireMethods(object, methods, name) {
    if (!object) {
        throw new PortContractError(`${name} is missing`);
    }

    for (const method of methods) {
        if (typeof object[method] !== "function") {
            throw new PortContractError(
                `${name} must implement ${method}()`
            );
        }
    }
}

function validatePorts(ports) {
    requireMethods(
        ports.orders,
        ["save", "findById"],
        "OrderRepositoryPort"
    );

    requireMethods(
        ports.inventory,
        ["reserve", "release"],
        "InventoryPort"
    );

    requireMethods(
        ports.payments,
        ["charge", "refund"],
        "PaymentPort"
    );

    requireMethods(
        ports.events,
        ["publish"],
        "EventPublisherPort"
    );
}

// ============================================================
// SECONDARY ADAPTERS
// ============================================================

class MemoryOrderRepository {
    #records = new Map();
    #mutex = Promise.resolve();

    async #exclusive(operation) {
        const previous = this.#mutex;
        let release;

        this.#mutex = new Promise(resolve => {
            release = resolve;
        });

        await previous;

        try {
            return await operation();
        } finally {
            release();
        }
    }

    async save(order) {
        return this.#exclusive(async () => {
            const current = this.#records.get(order.id);

            if (current && order.version <= current.version) {
                throw new ConcurrencyError("Stale order version");
            }

            this.#records.set(order.id, order.snapshot());
        });
    }

    async findById(id) {
        return this.#records.get(id) ?? null;
    }
}

class MemoryInventoryAdapter {
    #stock = new Map();
    #mutex = Promise.resolve();

    constructor(initialStock) {
        for (const [productId, quantity] of Object.entries(initialStock)) {
            if (!Number.isSafeInteger(quantity) || quantity < 0) {
                throw new DomainError("Invalid inventory quantity");
            }

            this.#stock.set(productId, quantity);
        }
    }

    async #exclusive(operation) {
        const previous = this.#mutex;
        let release;

        this.#mutex = new Promise(resolve => {
            release = resolve;
        });

        await previous;

        try {
            return await operation();
        } finally {
            release();
        }
    }

    async reserve(productId, quantity) {
        return this.#exclusive(async () => {
            const available = this.#stock.get(productId) ?? 0;

            if (!Number.isSafeInteger(quantity) || quantity <= 0) {
                throw new DomainError("Invalid reservation quantity");
            }

            if (available < quantity) {
                return false;
            }

            this.#stock.set(productId, available - quantity);
            return true;
        });
    }

    async release(productId, quantity) {
        return this.#exclusive(async () => {
            if (!Number.isSafeInteger(quantity) || quantity <= 0) {
                throw new DomainError("Invalid release quantity");
            }

            this.#stock.set(
                productId,
                (this.#stock.get(productId) ?? 0) + quantity
            );
        });
    }

    async available(productId) {
        return this.#stock.get(productId) ?? 0;
    }
}

class MemoryPaymentAdapter {
    #payments = new Map();
    #idempotency = new Map();

    async charge(customerId, amountMinorUnits, key) {
        if (!customerId || !Number.isSafeInteger(amountMinorUnits) ||
            amountMinorUnits <= 0 || !key) {
            throw new DomainError("Invalid payment request");
        }

        if (this.#idempotency.has(key)) {
            return this.#idempotency.get(key);
        }

        const paymentId = randomUUID();

        this.#payments.set(paymentId, {
            customerId,
            amountMinorUnits,
            status: "CHARGED"
        });

        this.#idempotency.set(key, paymentId);

        return paymentId;
    }

    async refund(paymentId) {
        const payment = this.#payments.get(paymentId);

        if (!payment || payment.status !== "CHARGED") {
            throw new ApplicationError("Payment cannot be refunded");
        }

        payment.status = "REFUNDED";
    }

    async status(paymentId) {
        return this.#payments.get(paymentId)?.status ?? null;
    }
}

class MemoryEventAdapter {
    constructor() {
        this.emitter = new EventEmitter();
        this.history = [];
    }

    async publish(event) {
        const immutableEvent = Object.freeze({ ...event });

        this.history.push(immutableEvent);
        this.emitter.emit(event.type, immutableEvent);
    }
}

// ============================================================
// APPLICATION SERVICE
// ============================================================

class PlaceOrderUseCase {
    constructor(ports) {
        validatePorts(ports);
        this.ports = ports;
    }

    async execute(command) {
        if (!command || !Array.isArray(command.lines)) {
            throw new ApplicationError("Invalid order command");
        }

        const lines = command.lines.map(line => new OrderLine(
            line.productId,
            line.quantity,
            new Money(line.unitPriceMinorUnits, line.currency ?? "INR")
        ));

        const order = new Order(command.customerId, lines);
        const reservations = [];
        let paymentId = null;

        try {
            for (const line of order.lines) {
                const reserved = await this.ports.inventory.reserve(
                    line.productId,
                    line.quantity
                );

                if (!reserved) {
                    throw new ApplicationError(
                        `Insufficient inventory for ${line.productId}`
                    );
                }

                reservations.push(line);
            }

            paymentId = await this.ports.payments.charge(
                order.customerId,
                order.totalMinorUnits,
                order.id
            );

            order.confirm();

            await this.ports.orders.save(order);

            await this.ports.events.publish({
                id: randomUUID(),
                type: "OrderConfirmed",
                aggregateId: order.id,
                paymentId,
                amountMinorUnits: order.totalMinorUnits,
                occurredAt: new Date().toISOString()
            });

            return order.snapshot();

        } catch (error) {
            // Compensate in reverse order.
            if (paymentId) {
                try {
                    await this.ports.payments.refund(paymentId);
                } catch (refundError) {
                    error.refundError = refundError.message;
                }
            }

            for (const line of reservations.reverse()) {
                try {
                    await this.ports.inventory.release(
                        line.productId,
                        line.quantity
                    );
                } catch (releaseError) {
                    error.inventoryCompensationError =
                        releaseError.message;
                }
            }

            throw new ApplicationError(
                `Order use case failed: ${error.message}`,
                { cause: error }
            );
        }
    }
}

// ============================================================
// PRIMARY ADAPTERS
// ============================================================

class ConsoleAdapter {
    constructor(placeOrder) {
        this.placeOrder = placeOrder;
    }

    async handle() {
        return this.placeOrder.execute({
            customerId: "CUSTOMER-2001",
            lines: [
                {
                    productId: "SERVER-001",
                    quantity: 2,
                    unitPriceMinorUnits: 4500000,
                    currency: "INR"
                },
                {
                    productId: "CABLE-001",
                    quantity: 3,
                    unitPriceMinorUnits: 15000,
                    currency: "INR"
                }
            ]
        });
    }
}

/*
 * An HTTP adapter maps transport requests to application commands.
 * It deliberately does not implement domain or persistence rules.
 */
class HttpOrderAdapter {
    constructor(placeOrder) {
        this.placeOrder = placeOrder;
    }

    async postOrder(request) {
        if (!request || !request.body) {
            return {
                status: 400,
                body: { error: "Request body required" }
            };
        }

        try {
            const result = await this.placeOrder.execute(request.body);

            return {
                status: 201,
                body: result
            };

        } catch (error) {
            return {
                status: 422,
                body: {
                    error: error.message
                }
            };
        }
    }
}

// ============================================================
// COMPOSITION ROOT
// ============================================================

function createApplication() {
    const ports = {
        orders: new MemoryOrderRepository(),
        inventory: new MemoryInventoryAdapter({
            "SERVER-001": 10,
            "CABLE-001": 100
        }),
        payments: new MemoryPaymentAdapter(),
        events: new MemoryEventAdapter()
    };

    const useCase = new PlaceOrderUseCase(ports);

    return {
        ports,
        useCase,
        consoleAdapter: new ConsoleAdapter(useCase),
        httpAdapter: new HttpOrderAdapter(useCase)
    };
}

// ============================================================
// TESTS
// ============================================================

async function runTests() {
    const application = createApplication();

    const order = await application.useCase.execute({
        customerId: "TEST-CUSTOMER",
        lines: [
            {
                productId: "SERVER-001",
                quantity: 1,
                unitPriceMinorUnits: 100000,
                currency: "INR"
            }
        ]
    });

    if (order.status !== OrderStatus.CONFIRMED) {
        throw new Error("Confirmation test failed");
    }

    if (order.totalMinorUnits !== 100000) {
        throw new Error("Amount calculation failed");
    }

    const stored = await application.ports.orders.findById(order.id);

    if (!stored || stored.version !== 1) {
        throw new Error("Persistence test failed");
    }

    const before = await application.ports.inventory.available(
        "SERVER-001"
    );

    try {
        await application.useCase.execute({
            customerId: "TEST-FAILURE",
            lines: [
                {
                    productId: "SERVER-001",
                    quantity: 1000,
                    unitPriceMinorUnits: 100,
                    currency: "INR"
                }
            ]
        });

        throw new Error("Expected inventory failure");
    } catch (error) {
        if (!(error instanceof ApplicationError)) {
            throw error;
        }
    }

    const after = await application.ports.inventory.available(
        "SERVER-001"
    );

    if (before !== after) {
        throw new Error("Inventory consistency test failed");
    }

    // Invalid quantity must be rejected.
    try {
        new OrderLine("P1", 0, new Money(100));
        throw new Error("Expected domain validation failure");
    } catch (error) {
        if (!(error instanceof DomainError)) {
            throw error;
        }
    }

    console.log("JavaScript tests passed.");
}

// ============================================================
// ENTRY POINT
// ============================================================

async function main() {
    const application = createApplication();

    application.ports.events.emitter.on(
        "OrderConfirmed",
        event => {
            console.log("Domain integration event:", event.type);
        }
    );

    try {
        const order = await application.consoleAdapter.handle();

        console.log("\nHEXAGONAL ARCHITECTURE");
        console.log("----------------------");
        console.log("Order:", order.id);
        console.log("Customer:", order.customerId);
        console.log("Status:", order.status);
        console.log("Total:", new Money(
            order.totalMinorUnits,
            order.currency
        ).toString());
        console.log("Version:", order.version);

        const response = await application.httpAdapter.postOrder({
            body: {
                customerId: "HTTP-CUSTOMER",
                lines: [
                    {
                        productId: "SERVER-001",
                        quantity: 1,
                        unitPriceMinorUnits: 200000,
                        currency: "INR"
                    }
                ]
            }
        });

        console.log("HTTP adapter status:", response.status);

    } catch (error) {
        console.error("Application failure:", error.message);
    }

    await runTests();
}

main().catch(error => {
    console.error("Fatal execution error:", error);
    process.exitCode = 1;
});
