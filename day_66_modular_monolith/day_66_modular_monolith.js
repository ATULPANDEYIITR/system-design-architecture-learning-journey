"use strict";

/*
 * Modular Monolith: Event-Driven Order Processing
 *
 * Demonstrates:
 * - Bounded contexts
 * - Encapsulated module state
 * - Explicit module interfaces
 * - Asynchronous application services
 * - Domain event dispatch
 * - Dependency policies
 * - Idempotent operations
 * - Migration through an anti-corruption layer
 *
 * Runtime: Node.js 18+
 */

const { randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

// ==========================================================
// SHARED KERNEL
// ==========================================================

class DomainError extends Error {
    constructor(message, code = "DOMAIN_ERROR") {
        super(message);
        this.name = this.constructor.name;
        this.code = code;
    }
}

class ValidationError extends DomainError {}
class NotFoundError extends DomainError {}
class InsufficientStockError extends DomainError {}
class PaymentError extends DomainError {}

function validateIdentifier(value, field) {
    if (typeof value !== "string" || value.trim().length === 0) {
        throw new ValidationError(`${field} is required.`);
    }
}

function validateQuantity(quantity) {
    if (!Number.isSafeInteger(quantity) || quantity <= 0) {
        throw new ValidationError(
            "Quantity must be a positive safe integer."
        );
    }
}

// Use integer minor currency units to avoid floating-point
// errors in monetary calculations.
function validateMoney(amount) {
    if (!Number.isSafeInteger(amount) || amount <= 0) {
        throw new ValidationError(
            "Amount must be positive integer minor units."
        );
    }
}

// ==========================================================
// EVENT INFRASTRUCTURE
// ==========================================================

class DomainEventPublisher {

    constructor() {
        this.emitter = new EventEmitter();
        this.emitter.setMaxListeners(100);
    }

    subscribe(eventType, handler) {
        if (typeof handler !== "function") {
            throw new ValidationError("Invalid event handler.");
        }

        this.emitter.on(eventType, handler);

        return () => this.emitter.off(eventType, handler);
    }

    async publish(event) {
        const listeners = this.emitter.listeners(event.type);

        // Await all listeners so failures are visible to the caller.
        const results = await Promise.allSettled(
            listeners.map(handler => Promise.resolve().then(
                () => handler(Object.freeze({ ...event }))
            ))
        );

        const failures = results.filter(
            result => result.status === "rejected"
        );

        if (failures.length > 0) {
            throw new DomainError(
                `${failures.length} event handler(s) failed.`
            );
        }
    }
}

function createEvent(type, aggregateId, payload) {
    return Object.freeze({
        eventId: randomUUID(),
        type,
        aggregateId,
        occurredAt: new Date().toISOString(),
        payload: Object.freeze({ ...payload })
    });
}

// ==========================================================
// INVENTORY MODULE
// ==========================================================

class InventoryModule {

    #products = new Map();
    #reservations = new Map();

    addProduct({ id, name, priceInCents, stock }) {
        validateIdentifier(id, "Product ID");
        validateIdentifier(name, "Product name");
        validateMoney(priceInCents);

        if (!Number.isSafeInteger(stock) || stock < 0) {
            throw new ValidationError("Invalid stock quantity.");
        }

        if (this.#products.has(id)) {
            throw new ValidationError("Product already exists.");
        }

        this.#products.set(id, {
            id,
            name,
            priceInCents,
            stock
        });
    }

    getProduct(id) {
        const product = this.#products.get(id);

        if (!product) {
            throw new NotFoundError("Product not found.");
        }

        return Object.freeze({ ...product });
    }

    reserve(productId, quantity) {
        validateQuantity(quantity);

        const product = this.#products.get(productId);

        if (!product) {
            throw new NotFoundError("Product not found.");
        }

        if (product.stock < quantity) {
            throw new InsufficientStockError(
                "Insufficient inventory."
            );
        }

        product.stock -= quantity;

        const reservation = {
            id: randomUUID(),
            productId,
            quantity,
            state: "ACTIVE"
        };

        this.#reservations.set(reservation.id, reservation);

        return Object.freeze({ ...reservation });
    }

    release(reservationId) {
        const reservation = this.#reservations.get(reservationId);

        if (!reservation) {
            throw new NotFoundError("Reservation not found.");
        }

        if (reservation.state === "RELEASED") {
            return;
        }

        if (reservation.state !== "ACTIVE") {
            throw new DomainError("Reservation is already committed.");
        }

        this.#products.get(reservation.productId).stock +=
            reservation.quantity;

        reservation.state = "RELEASED";
    }

    commit(reservationId) {
        const reservation = this.#reservations.get(reservationId);

        if (!reservation || reservation.state !== "ACTIVE") {
            throw new DomainError("Active reservation required.");
        }

        reservation.state = "COMMITTED";
    }
}

// ==========================================================
// PAYMENT MODULE
// ==========================================================

class PaymentModule {

    #payments = new Map();

    async authorize(orderId, amountInCents) {
        validateIdentifier(orderId, "Order ID");
        validateMoney(amountInCents);

        // A real payment adapter would call an external provider.
        const payment = {
            id: randomUUID(),
            orderId,
            amountInCents,
            status: "AUTHORIZED"
        };

        this.#payments.set(payment.id, payment);

        return Object.freeze({ ...payment });
    }

    async refund(paymentId) {
        const payment = this.#payments.get(paymentId);

        if (!payment) {
            throw new NotFoundError("Payment not found.");
        }

        if (payment.status !== "AUTHORIZED") {
            throw new PaymentError("Payment cannot be refunded.");
        }

        payment.status = "REFUNDED";

        return Object.freeze({ ...payment });
    }

    getPayment(paymentId) {
        const payment = this.#payments.get(paymentId);

        if (!payment) {
            throw new NotFoundError("Payment not found.");
        }

        return Object.freeze({ ...payment });
    }
}

// ==========================================================
// ORDER MODULE
// ==========================================================

class OrderModule {

    #orders = new Map();
    #idempotencyKeys = new Map();

    constructor(inventory, payments, eventPublisher) {
        this.inventory = inventory;
        this.payments = payments;
        this.events = eventPublisher;
    }

    async createOrder({
        customerId,
        productId,
        quantity,
        idempotencyKey
    }) {
        validateIdentifier(customerId, "Customer ID");
        validateIdentifier(productId, "Product ID");
        validateQuantity(quantity);
        validateIdentifier(idempotencyKey, "Idempotency key");

        const requestFingerprint = JSON.stringify({
            customerId,
            productId,
            quantity
        });

        const existing = this.#idempotencyKeys.get(idempotencyKey);

        if (existing) {
            if (existing.fingerprint !== requestFingerprint) {
                throw new ValidationError(
                    "Idempotency key reused with different input."
                );
            }

            return Object.freeze({ ...existing.order });
        }

        const product = this.inventory.getProduct(productId);

        const amountInCents = product.priceInCents * quantity;

        if (!Number.isSafeInteger(amountInCents)) {
            throw new ValidationError("Order amount exceeds safe limits.");
        }

        const orderId = randomUUID();
        const reservation = this.inventory.reserve(productId, quantity);

        let payment;

        try {
            payment = await this.payments.authorize(
                orderId,
                amountInCents
            );

            this.inventory.commit(reservation.id);

            const order = {
                id: orderId,
                customerId,
                productId,
                quantity,
                amountInCents,
                reservationId: reservation.id,
                paymentId: payment.id,
                status: "CONFIRMED"
            };

            this.#orders.set(order.id, order);

            this.#idempotencyKeys.set(idempotencyKey, {
                fingerprint: requestFingerprint,
                order
            });

            // Event publication occurs after in-memory state changes.
            // Production systems require a transactional outbox.
            try {
                await this.events.publish(
                    createEvent("order.confirmed", order.id, {
                        customerId,
                        amountInCents
                    })
                );
            } catch (error) {
                // The order is already committed. Do not compensate
                // inventory or payment because a notification failed.
                console.error(
                    "Post-commit event delivery failed:",
                    error.message
                );
            }

            return Object.freeze({ ...order });

        } catch (error) {
            // Compensation is required when payment authorization
            // or the pre-commit workflow fails.
            if (payment) {
                try {
                    await this.payments.refund(payment.id);
                } catch (refundError) {
                    console.error(
                        "Payment compensation failed:",
                        refundError.message
                    );
                }
            }

            // A committed reservation cannot be released. This
            // workflow commits inventory only after authorization.
            try {
                this.inventory.release(reservation.id);
            } catch (releaseError) {
                if (releaseError.code !== "DOMAIN_ERROR") {
                    console.error(releaseError);
                }
            }

            throw error;
        }
    }

    getOrder(orderId) {
        const order = this.#orders.get(orderId);

        if (!order) {
            throw new NotFoundError("Order not found.");
        }

        return Object.freeze({ ...order });
    }
}

// ==========================================================
// NOTIFICATION MODULE
// ==========================================================

class NotificationModule {

    constructor(events) {
        this.messages = [];

        events.subscribe("order.confirmed", async event => {
            this.messages.push({
                orderId: event.aggregateId,
                message: "Order confirmation notification.",
                deliveredAt: new Date().toISOString()
            });
        });
    }
}

// ==========================================================
// MODULE DEPENDENCY POLICY
// ==========================================================

class ModuleDependencyPolicy {

    constructor() {
        this.allowed = new Map([
            ["orders", new Set(["inventory", "payments", "shared"])],
            ["inventory", new Set(["shared"])],
            ["payments", new Set(["shared"])],
            ["notifications", new Set(["shared"])]
        ]);
    }

    validate(dependencies) {
        const violations = [];

        for (const [source, targets] of Object.entries(dependencies)) {
            const allowedTargets = this.allowed.get(source);

            if (!allowedTargets) {
                violations.push(`Unknown module: ${source}`);
                continue;
            }

            for (const target of targets) {
                if (!allowedTargets.has(target)) {
                    violations.push(`${source} -> ${target}`);
                }
            }
        }

        return violations;
    }
}

// ==========================================================
// STRANGLER MIGRATION ADAPTER
// ==========================================================

class OrderGateway {

    constructor(localOrderModule, remoteOrderClient = null) {
        this.local = localOrderModule;
        this.remote = remoteOrderClient;
        this.mode = "LOCAL";
    }

    useRemote(client) {
        if (!client || typeof client.createOrder !== "function") {
            throw new ValidationError("Invalid remote order client.");
        }

        this.remote = client;
        this.mode = "REMOTE";
    }

    async createOrder(command) {
        if (this.mode === "REMOTE") {
            return this.remote.createOrder(command);
        }

        return this.local.createOrder(command);
    }
}

// ==========================================================
// APPLICATION COMPOSITION ROOT
// ==========================================================

class Application {

    constructor() {
        this.events = new DomainEventPublisher();

        this.inventory = new InventoryModule();
        this.payments = new PaymentModule();

        this.orders = new OrderModule(
            this.inventory,
            this.payments,
            this.events
        );

        this.notifications = new NotificationModule(this.events);

        this.orderGateway = new OrderGateway(this.orders);
    }

    configure() {
        this.inventory.addProduct({
            id: "LAPTOP-01",
            name: "Business Laptop",
            priceInCents: 7500000,
            stock: 10
        });
    }
}

// ==========================================================
// EXECUTION
// ==========================================================

async function main() {
    const app = new Application();

    app.configure();

    const order = await app.orderGateway.createOrder({
        customerId: "CUSTOMER-100",
        productId: "LAPTOP-01",
        quantity: 2,
        idempotencyKey: "checkout-2026-001"
    });

    console.log("ORDER:", order);
    console.log("PRODUCT:", app.inventory.getProduct("LAPTOP-01"));
    console.log("PAYMENT:", app.payments.getPayment(order.paymentId));

    console.log(
        "NOTIFICATIONS:",
        app.notifications.messages
    );

    // Repeating the same request does not create another order.
    const repeated = await app.orderGateway.createOrder({
        customerId: "CUSTOMER-100",
        productId: "LAPTOP-01",
        quantity: 2,
        idempotencyKey: "checkout-2026-001"
    });

    console.log("IDEMPOTENT:", repeated.id === order.id);

    const policy = new ModuleDependencyPolicy();

    const violations = policy.validate({
        orders: ["inventory", "payments", "shared"],
        inventory: ["shared"],
        payments: ["shared"],
        notifications: ["shared"]
    });

    console.log("DEPENDENCY VIOLATIONS:", violations);

    if (violations.length !== 0) {
        throw new Error("Architecture policy violation.");
    }

    const invalid = policy.validate({
        inventory: ["orders"]
    });

    console.log("INVALID DEPENDENCIES:", invalid);

    try {
        await app.orders.createOrder({
            customerId: "CUSTOMER-200",
            productId: "LAPTOP-01",
            quantity: 100,
            idempotencyKey: "checkout-invalid"
        });
    } catch (error) {
        console.log("EXPECTED FAILURE:", error.message);
    }

    console.log(
        "REMAINING STOCK:",
        app.inventory.getProduct("LAPTOP-01").stock
    );

    console.log("Execution completed.");
}

main().catch(error => {
    console.error("Application failure:", error);
    process.exitCode = 1;
});
