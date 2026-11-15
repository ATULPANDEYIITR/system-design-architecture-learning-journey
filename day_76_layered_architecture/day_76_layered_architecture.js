"use strict";

/*
 * Layered Architecture: Event-Driven Order Management
 *
 * Presentation:
 *   CLI and request handlers
 *
 * Application:
 *   Command dispatch, use cases, orchestration
 *
 * Domain:
 *   Order aggregates, business rules, domain events
 *
 * Infrastructure:
 *   In-memory persistence, event journal, adapters
 *
 * Runtime: Node.js 18+
 * Execute: node layered-architecture.js
 * Test: node layered-architecture.js --test
 */

const { randomUUID } = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const EventEmitter = require("node:events");

// ============================================================
// DOMAIN LAYER
// ============================================================

class DomainError extends Error {
    constructor(message) {
        super(message);
        this.name = this.constructor.name;
    }
}

class ValidationError extends DomainError {}
class OrderNotFoundError extends DomainError {}
class InvalidStateError extends DomainError {}
class ConcurrencyError extends DomainError {}

const OrderStatus = Object.freeze({
    PENDING: "PENDING",
    CONFIRMED: "CONFIRMED",
    CANCELLED: "CANCELLED"
});

class OrderItem {
    constructor({ productId, name, quantity, unitPrice }) {
        if (typeof productId !== "string" || !productId.trim()) {
            throw new ValidationError("Invalid product ID.");
        }

        if (typeof name !== "string" || !name.trim()) {
            throw new ValidationError("Product name is required.");
        }

        if (!Number.isSafeInteger(quantity) || quantity <= 0) {
            throw new ValidationError("Quantity must be a positive integer.");
        }

        if (
            typeof unitPrice !== "number" ||
            !Number.isFinite(unitPrice) ||
            unitPrice <= 0
        ) {
            throw new ValidationError("Unit price must be positive.");
        }

        this.productId = productId.trim();
        this.name = name.trim();
        this.quantity = quantity;
        this.unitPrice = Math.round(unitPrice * 100) / 100;

        Object.freeze(this);
    }

    get subtotal() {
        return Math.round(
            this.quantity * this.unitPrice * 100
        ) / 100;
    }
}

class Order {
    constructor(customerId, items, id = randomUUID()) {
        if (typeof customerId !== "string" || !customerId.trim()) {
            throw new ValidationError("Customer ID is required.");
        }

        if (!Array.isArray(items) || items.length === 0) {
            throw new ValidationError("Order items are required.");
        }

        const productIds = new Set(items.map(item => item.productId));

        if (productIds.size !== items.length) {
            throw new ValidationError("Duplicate products are prohibited.");
        }

        this.id = id;
        this.customerId = customerId.trim();
        this.items = Object.freeze([...items]);
        this.status = OrderStatus.PENDING;
        this.version = 0;
        this.createdAt = new Date().toISOString();
    }

    get total() {
        const cents = this.items.reduce(
            (sum, item) => sum + Math.round(item.subtotal * 100),
            0
        );

        return cents / 100;
    }

    confirm() {
        if (this.status !== OrderStatus.PENDING) {
            throw new InvalidStateError(
                "Only pending orders can be confirmed."
            );
        }

        this.status = OrderStatus.CONFIRMED;
        this.version++;
    }

    cancel() {
        if (this.status !== OrderStatus.PENDING) {
            throw new InvalidStateError(
                "Only pending orders can be cancelled."
            );
        }

        this.status = OrderStatus.CANCELLED;
        this.version++;
    }

    snapshot() {
        return Object.freeze({
            id: this.id,
            customerId: this.customerId,
            status: this.status,
            version: this.version,
            total: this.total,
            createdAt: this.createdAt,
            items: this.items.map(item => ({
                productId: item.productId,
                name: item.name,
                quantity: item.quantity,
                unitPrice: item.unitPrice
            }))
        });
    }

    static restore(data) {
        const order = new Order(
            data.customerId,
            data.items.map(item => new OrderItem(item)),
            data.id
        );

        order.status = data.status;
        order.version = data.version;
        order.createdAt = data.createdAt;

        return order;
    }
}

// ============================================================
// INFRASTRUCTURE LAYER
// ============================================================

class AsyncMutex {
    constructor() {
        this.tail = Promise.resolve();
    }

    async runExclusive(operation) {
        const previous = this.tail;
        let release;

        this.tail = new Promise(resolve => {
            release = resolve;
        });

        await previous;

        try {
            return await operation();
        } finally {
            release();
        }
    }
}

class InMemoryOrderRepository {
    constructor() {
        this.records = new Map();
        this.mutex = new AsyncMutex();
    }

    async save(order) {
        return this.mutex.runExclusive(async () => {
            const existing = this.records.get(order.id);

            if (existing && order.version < existing.version) {
                throw new ConcurrencyError("Stale order version.");
            }

            this.records.set(order.id, structuredClone(order.snapshot()));
            return order.snapshot();
        });
    }

    async get(id) {
        const record = this.records.get(id);

        if (!record) {
            throw new OrderNotFoundError(`Order ${id} was not found.`);
        }

        return Order.restore(record);
    }

    async list() {
        return Array.from(
            this.records.values(),
            record => structuredClone(record)
        );
    }
}

class FileEventJournal {
    constructor(filePath) {
        this.filePath = filePath;
        this.mutex = new AsyncMutex();
    }

    async append(event) {
        return this.mutex.runExclusive(async () => {
            await fs.mkdir(path.dirname(this.filePath), {
                recursive: true
            });

            const line = JSON.stringify(event) + "\n";

            await fs.appendFile(
                this.filePath,
                line,
                { encoding: "utf8", mode: 0o600 }
            );
        });
    }
}

class OrderEventBus extends EventEmitter {
    publish(event) {
        this.emit(event.type, Object.freeze(event));
        this.emit("*", Object.freeze(event));
    }
}

// ============================================================
// APPLICATION LAYER
// ============================================================

class CreateOrderCommand {
    constructor(payload) {
        if (!payload || typeof payload !== "object") {
            throw new ValidationError("Invalid command payload.");
        }

        this.customerId = payload.customerId;
        this.items = payload.items;
    }
}

class OrderApplicationService {
    constructor(repository, journal, eventBus) {
        this.repository = repository;
        this.journal = journal;
        this.eventBus = eventBus;
    }

    async create(command) {
        if (!(command instanceof CreateOrderCommand)) {
            throw new ValidationError("Expected CreateOrderCommand.");
        }

        const items = command.items.map(
            item => new OrderItem(item)
        );

        const order = new Order(command.customerId, items);

        await this.repository.save(order);

        const event = {
            eventId: randomUUID(),
            type: "ORDER_CREATED",
            aggregateId: order.id,
            aggregateVersion: order.version,
            occurredAt: new Date().toISOString()
        };

        await this.journal.append(event);
        this.eventBus.publish(event);

        return order.snapshot();
    }

    async confirm(id) {
        const order = await this.repository.get(id);

        order.confirm();
        await this.repository.save(order);

        const event = {
            eventId: randomUUID(),
            type: "ORDER_CONFIRMED",
            aggregateId: order.id,
            aggregateVersion: order.version,
            occurredAt: new Date().toISOString()
        };

        await this.journal.append(event);
        this.eventBus.publish(event);

        return order.snapshot();
    }

    async cancel(id) {
        const order = await this.repository.get(id);

        order.cancel();
        await this.repository.save(order);

        const event = {
            eventId: randomUUID(),
            type: "ORDER_CANCELLED",
            aggregateId: order.id,
            aggregateVersion: order.version,
            occurredAt: new Date().toISOString()
        };

        await this.journal.append(event);
        this.eventBus.publish(event);

        return order.snapshot();
    }

    async get(id) {
        return (await this.repository.get(id)).snapshot();
    }

    async list() {
        return this.repository.list();
    }
}

// ============================================================
// PRESENTATION LAYER
// ============================================================

class OrderController {
    constructor(applicationService) {
        this.service = applicationService;
    }

    async handleCreate(request) {
        try {
            const command = new CreateOrderCommand(request.body);
            const result = await this.service.create(command);

            return {
                statusCode: 201,
                body: result
            };
        } catch (error) {
            return this.handleError(error);
        }
    }

    async handleConfirm(orderId) {
        try {
            return {
                statusCode: 200,
                body: await this.service.confirm(orderId)
            };
        } catch (error) {
            return this.handleError(error);
        }
    }

    handleError(error) {
        if (error instanceof ValidationError) {
            return {
                statusCode: 400,
                body: { error: error.message }
            };
        }

        if (error instanceof OrderNotFoundError) {
            return {
                statusCode: 404,
                body: { error: error.message }
            };
        }

        if (
            error instanceof InvalidStateError ||
            error instanceof ConcurrencyError
        ) {
            return {
                statusCode: 409,
                body: { error: error.message }
            };
        }

        return {
            statusCode: 500,
            body: { error: "Internal server error." }
        };
    }
}

// ============================================================
// TESTING
// ============================================================

async function runTests() {
    const repository = new InMemoryOrderRepository();

    const journal = new FileEventJournal(
        path.join(
            process.cwd(),
            "layered-architecture-data",
            "test-events.jsonl"
        )
    );

    const eventBus = new OrderEventBus();
    const service = new OrderApplicationService(
        repository,
        journal,
        eventBus
    );

    let publishedEvents = 0;
    eventBus.on("*", () => publishedEvents++);

    const created = await service.create(
        new CreateOrderCommand({
            customerId: "C-100",
            items: [
                {
                    productId: "P-1",
                    name: "Workstation",
                    quantity: 2,
                    unitPrice: 1000
                }
            ]
        })
    );

    console.assert(created.total === 2000);
    console.assert(created.status === "PENDING");

    const confirmed = await service.confirm(created.id);

    console.assert(confirmed.status === "CONFIRMED");
    console.assert(confirmed.version === 1);

    try {
        await service.cancel(created.id);
        throw new Error("Invalid cancellation was accepted.");
    } catch (error) {
        console.assert(error instanceof InvalidStateError);
    }

    try {
        new OrderItem({
            productId: "P-2",
            name: "Invalid",
            quantity: 0,
            unitPrice: 10
        });

        throw new Error("Invalid quantity was accepted.");
    } catch (error) {
        console.assert(error instanceof ValidationError);
    }

    console.assert((await service.list()).length === 1);
    console.assert(publishedEvents === 2);

    console.log("All JavaScript tests passed.");
}

// ============================================================
// EXECUTION
// ============================================================

async function main() {
    if (process.argv.includes("--test")) {
        await runTests();
        return;
    }

    const repository = new InMemoryOrderRepository();

    const journal = new FileEventJournal(
        path.join(
            process.cwd(),
            "layered-architecture-data",
            "events.jsonl"
        )
    );

    const eventBus = new OrderEventBus();

    eventBus.on("ORDER_CREATED", event => {
        console.log("Event received:", event.type, event.aggregateId);
    });

    const service = new OrderApplicationService(
        repository,
        journal,
        eventBus
    );

    const controller = new OrderController(service);

    const response = await controller.handleCreate({
        body: {
            customerId: "CUSTOMER-200",
            items: [
                {
                    productId: "P-101",
                    name: "Business Laptop",
                    quantity: 2,
                    unitPrice: 75000
                },
                {
                    productId: "P-102",
                    name: "Docking Station",
                    quantity: 1,
                    unitPrice: 8500
                }
            ]
        }
    });

    console.log("Create response:", response);

    if (response.statusCode === 201) {
        const confirmation = await controller.handleConfirm(
            response.body.id
        );

        console.log("Confirmation response:", confirmation);
    }
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
