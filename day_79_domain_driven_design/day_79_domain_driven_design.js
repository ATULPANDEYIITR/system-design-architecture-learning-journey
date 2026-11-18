"use strict";

const crypto = require("node:crypto");
const EventEmitter = require("node:events");

// ============================================================
// DOMAIN-DRIVEN DESIGN: EVENT-DRIVEN BOUNDED CONTEXTS
// ============================================================

class DomainError extends Error {}
class ValidationError extends DomainError {}
class NotFoundError extends DomainError {}
class ConcurrencyError extends DomainError {}

const OrderStatus = Object.freeze({
    DRAFT: "DRAFT",
    SUBMITTED: "SUBMITTED",
    CONFIRMED: "CONFIRMED",
    CANCELLED: "CANCELLED"
});

function createId() {
    return crypto.randomUUID();
}

function requireNonEmpty(value, field) {
    if (typeof value !== "string" || !value.trim()) {
        throw new ValidationError(`${field} is required.`);
    }
    return value.trim();
}

function requirePositiveInteger(value, field) {
    if (!Number.isSafeInteger(value) || value <= 0) {
        throw new ValidationError(`${field} must be a positive integer.`);
    }
}

function money(amount, currency = "INR") {
    if (!Number.isSafeInteger(amount) || amount < 0) {
        throw new ValidationError("Money must be a non-negative integer.");
    }

    if (!/^[A-Z]{3}$/.test(currency)) {
        throw new ValidationError("Invalid currency.");
    }

    return Object.freeze({ amount, currency });
}

function addMoney(a, b) {
    if (a.currency !== b.currency) {
        throw new ValidationError("Currency mismatch.");
    }

    return money(a.amount + b.amount, a.currency);
}

function multiplyMoney(value, quantity) {
    requirePositiveInteger(quantity, "Quantity");

    const result = value.amount * quantity;

    if (!Number.isSafeInteger(result)) {
        throw new ValidationError("Money calculation exceeds safe limits.");
    }

    return money(result, value.currency);
}

// ============================================================
// DOMAIN EVENT
// ============================================================

class DomainEvent {
    constructor(aggregateId, type, payload) {
        this.id = createId();
        this.aggregateId = aggregateId;
        this.type = type;
        this.payload = Object.freeze({ ...payload });
        this.occurredAt = new Date().toISOString();
        Object.freeze(this);
    }
}

// ============================================================
// DOMAIN EVENT BUS
// ============================================================

class DomainEventBus extends EventEmitter {
    constructor() {
        super();
        this.setMaxListeners(100);
        this.processedEvents = new Set();
    }

    async publish(event) {
        if (this.processedEvents.has(event.id)) {
            return false;
        }

        // Mark only after successful handler execution.
        try {
            await this.emitAsync(event.type, event);
            this.processedEvents.add(event.id);
            return true;
        } catch (error) {
            throw new DomainError(
                `Event ${event.type} failed: ${error.message}`
            );
        }
    }

    async emitAsync(eventType, event) {
        const handlers = this.listeners(eventType);

        for (const handler of handlers) {
            await handler(event);
        }
    }
}

// ============================================================
// BOUNDED CONTEXT: PRODUCT CATALOG
// ============================================================

class CatalogProduct {
    constructor(name, price) {
        this.id = createId();
        this.name = requireNonEmpty(name, "Product name");
        this.price = money(price.amount, price.currency);
        this.active = true;
        this.version = 0;
    }

    changePrice(newPrice) {
        if (newPrice.currency !== this.price.currency) {
            throw new ValidationError("Currency cannot change implicitly.");
        }

        this.price = money(newPrice.amount, newPrice.currency);
        this.version++;
    }

    deactivate() {
        this.active = false;
        this.version++;
    }

    createSnapshot() {
        if (!this.active) {
            throw new DomainError("Inactive products cannot be purchased.");
        }

        return Object.freeze({
            productId: this.id,
            name: this.name,
            unitPrice: this.price
        });
    }
}

class CatalogContext {
    #products = new Map();

    register(product) {
        if (!(product instanceof CatalogProduct)) {
            throw new ValidationError("Invalid catalog entity.");
        }

        if (this.#products.has(product.id)) {
            throw new DomainError("Duplicate product.");
        }

        this.#products.set(product.id, product);
    }

    getSnapshot(productId) {
        const product = this.#products.get(productId);

        if (!product) {
            throw new NotFoundError("Catalog product not found.");
        }

        return product.createSnapshot();
    }
}

// ============================================================
// BOUNDED CONTEXT: INVENTORY
// ============================================================

class InventoryItem {
    constructor(productId, initialStock) {
        requirePositiveInteger(initialStock, "Initial stock");
        this.productId = productId;
        this.available = initialStock;
        this.reserved = 0;
    }

    reserve(quantity) {
        requirePositiveInteger(quantity, "Reservation quantity");

        if (quantity > this.available) {
            throw new DomainError("Insufficient stock.");
        }

        this.available -= quantity;
        this.reserved += quantity;
    }

    release(quantity) {
        requirePositiveInteger(quantity, "Release quantity");

        if (quantity > this.reserved) {
            throw new DomainError("Cannot release unreserved stock.");
        }

        this.reserved -= quantity;
        this.available += quantity;
    }
}

class InventoryContext {
    #items = new Map();

    addStock(productId, quantity) {
        requirePositiveInteger(quantity, "Stock quantity");

        if (!this.#items.has(productId)) {
            this.#items.set(productId, new InventoryItem(productId, quantity));
        } else {
            this.#items.get(productId).available += quantity;
        }
    }

    reserve(productId, quantity) {
        const item = this.#items.get(productId);

        if (!item) {
            throw new NotFoundError("Inventory item not found.");
        }

        item.reserve(quantity);
    }

    release(productId, quantity) {
        const item = this.#items.get(productId);

        if (!item) {
            throw new NotFoundError("Inventory item not found.");
        }

        item.release(quantity);
    }

    getStock(productId) {
        const item = this.#items.get(productId);

        if (!item) {
            throw new NotFoundError("Inventory item not found.");
        }

        return Object.freeze({
            available: item.available,
            reserved: item.reserved
        });
    }
}

// ============================================================
// BOUNDED CONTEXT: ORDER MANAGEMENT
// ============================================================

class OrderLine {
    constructor(snapshot, quantity) {
        requirePositiveInteger(quantity, "Order quantity");

        this.product = snapshot;
        this.quantity = quantity;
    }

    get subtotal() {
        return multiplyMoney(this.product.unitPrice, this.quantity);
    }
}

class OrderAggregate {
    #lines = new Map();
    #events = [];

    constructor(customerId) {
        this.id = createId();
        this.customerId = requireNonEmpty(customerId, "Customer ID");
        this.status = OrderStatus.DRAFT;
        this.version = 0;
        this.#record("OrderCreated", { customerId });
    }

    get lines() {
        return [...this.#lines.values()];
    }

    get events() {
        return [...this.#events];
    }

    get total() {
        let result = money(0, this.lines[0]?.product.unitPrice.currency ?? "INR");

        for (const line of this.#lines.values()) {
            result = addMoney(result, line.subtotal);
        }

        return result;
    }

    addProduct(snapshot, quantity) {
        if (this.status !== OrderStatus.DRAFT) {
            throw new DomainError("Only draft orders can be changed.");
        }

        requirePositiveInteger(quantity, "Quantity");

        if (this.#lines.size > 0) {
            const currency = this.lines[0].product.unitPrice.currency;

            if (currency !== snapshot.unitPrice.currency) {
                throw new ValidationError("Mixed currencies are prohibited.");
            }
        }

        const existing = this.#lines.get(snapshot.productId);

        if (existing) {
            if (
                existing.product.unitPrice.amount !== snapshot.unitPrice.amount ||
                existing.product.unitPrice.currency !== snapshot.unitPrice.currency
            ) {
                throw new DomainError("Product price snapshot has changed.");
            }

            existing.quantity += quantity;
        } else {
            this.#lines.set(
                snapshot.productId,
                new OrderLine(snapshot, quantity)
            );
        }

        this.version++;
    }

    submit() {
        if (this.status !== OrderStatus.DRAFT) {
            throw new DomainError("Invalid submission transition.");
        }

        if (this.#lines.size === 0) {
            throw new DomainError("Empty orders cannot be submitted.");
        }

        this.status = OrderStatus.SUBMITTED;

        this.#record("OrderSubmitted", {
            orderId: this.id,
            totalAmount: this.total.amount,
            currency: this.total.currency,
            lines: this.lines.map(line => ({
                productId: line.product.productId,
                quantity: line.quantity
            }))
        });
    }

    confirm() {
        if (this.status !== OrderStatus.SUBMITTED) {
            throw new DomainError("Only submitted orders can be confirmed.");
        }

        this.status = OrderStatus.CONFIRMED;
        this.#record("OrderConfirmed", { orderId: this.id });
    }

    cancel() {
        if (![OrderStatus.DRAFT, OrderStatus.SUBMITTED].includes(this.status)) {
            throw new DomainError("Order cannot be cancelled.");
        }

        this.status = OrderStatus.CANCELLED;
        this.#record("OrderCancelled", { orderId: this.id });
    }

    #record(type, payload) {
        this.#events.push(new DomainEvent(this.id, type, payload));
        this.version++;
    }

    clearEvents() {
        this.#events = [];
    }
}

// ============================================================
// BOUNDED CONTEXT: BILLING
// ============================================================

class Invoice {
    constructor(orderId, amount) {
        this.id = createId();
        this.orderId = orderId;
        this.amount = amount;
        this.status = "UNPAID";
    }

    markPaid() {
        if (this.status === "PAID") {
            throw new DomainError("Invoice already paid.");
        }

        this.status = "PAID";
    }
}

class BillingContext {
    #invoices = new Map();

    createInvoice(orderId, amount) {
        if (this.#invoices.has(orderId)) {
            throw new DomainError("Invoice already exists.");
        }

        const invoice = new Invoice(orderId, amount);
        this.#invoices.set(orderId, invoice);
        return invoice;
    }

    getInvoice(orderId) {
        const invoice = this.#invoices.get(orderId);

        if (!invoice) {
            throw new NotFoundError("Invoice not found.");
        }

        return invoice;
    }
}

// ============================================================
// APPLICATION SERVICE: PROCESS MANAGER
// ============================================================

class OrderApplicationService {
    constructor(catalog, inventory, billing, eventBus) {
        this.catalog = catalog;
        this.inventory = inventory;
        this.billing = billing;
        this.eventBus = eventBus;
    }

    async placeOrder(order) {
        if (order.status !== OrderStatus.DRAFT) {
            throw new DomainError("Order must be in draft state.");
        }

        const reservations = [];

        try {
            for (const line of order.lines) {
                this.inventory.reserve(
                    line.product.productId,
                    line.quantity
                );

                reservations.push({
                    productId: line.product.productId,
                    quantity: line.quantity
                });
            }

            order.submit();

            const invoice = this.billing.createInvoice(
                order.id,
                order.total
            );

            for (const event of order.events) {
                await this.eventBus.publish(event);
            }

            order.clearEvents();

            return invoice;
        } catch (error) {
            for (const reservation of reservations.reverse()) {
                this.inventory.release(
                    reservation.productId,
                    reservation.quantity
                );
            }

            throw error;
        }
    }
}

// ============================================================
// REPOSITORY: OPTIMISTIC CONCURRENCY CONTROL
// ============================================================

class OrderRepository {
    #records = new Map();

    save(order, expectedVersion = null) {
        const current = this.#records.get(order.id);

        if (current && expectedVersion !== null &&
            current.version !== expectedVersion) {
            throw new ConcurrencyError("Concurrent modification detected.");
        }

        if (!current && expectedVersion !== null && expectedVersion !== 0) {
            throw new ConcurrencyError("Expected initial version zero.");
        }

        this.#records.set(order.id, {
            version: order.version,
            order
        });
    }

    get(orderId) {
        const record = this.#records.get(orderId);

        if (!record) {
            throw new NotFoundError("Order not found.");
        }

        return record.order;
    }
}

// ============================================================
// ASYNCHRONOUS DEMONSTRATION
// ============================================================

async function main() {
    const catalog = new CatalogContext();
    const inventory = new InventoryContext();
    const billing = new BillingContext();
    const eventBus = new DomainEventBus();
    const repository = new OrderRepository();

    const product = new CatalogProduct(
        "Enterprise Firewall",
        money(75000)
    );

    catalog.register(product);
    inventory.addStock(product.id, 10);

    const order = new OrderAggregate("CUSTOMER-1001");

    order.addProduct(catalog.getSnapshot(product.id), 2);

    repository.save(order, 0);

    eventBus.on("OrderSubmitted", async event => {
        console.log("Integration event received:", event.type);
        console.log("Order:", event.payload.orderId);
    });

    const service = new OrderApplicationService(
        catalog,
        inventory,
        billing,
        eventBus
    );

    const invoice = await service.placeOrder(order);

    console.log("\nORDER");
    console.log("Order ID:", order.id);
    console.log("Status:", order.status);
    console.log("Total:", order.total);
    console.log("Invoice ID:", invoice.id);
    console.log("Inventory:", inventory.getStock(product.id));

    // Catalog changes do not mutate historical order snapshots.
    product.changePrice(money(80000));

    if (order.total.amount !== 150000) {
        throw new Error("Historical order price changed unexpectedly.");
    }

    // Invalid operations are rejected by the aggregate.
    try {
        order.addProduct(catalog.getSnapshot(product.id), 1);
    } catch (error) {
        console.log("Expected domain rejection:", error.message);
    }

    try {
        inventory.reserve(product.id, 100);
    } catch (error) {
        console.log("Expected inventory rejection:", error.message);
    }

    invoice.markPaid();

    console.log("\nInvoice status:", invoice.status);
    console.log("All JavaScript domain checks passed.");
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
