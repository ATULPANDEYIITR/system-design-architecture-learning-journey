"use strict";

/**
 * Service Communication
 *
 * REST: HTTP request/response and resource-oriented endpoints.
 * gRPC: typed RPC contracts and deadline-aware invocation.
 * Messaging: asynchronous event delivery, retries, acknowledgements,
 * dead-letter handling, and idempotent consumers.
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const http = require("node:http");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

// ============================================================
// 1. Shared Validation
// ============================================================

class ValidationError extends Error {}
class NotFoundError extends Error {}
class UnavailableError extends Error {}

function validateProduct(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) {
        throw new ValidationError("Product must be an object");
    }

    if (typeof data.name !== "string" || !data.name.trim()) {
        throw new ValidationError("Product name is required");
    }

    if (
        typeof data.price !== "number" ||
        !Number.isFinite(data.price) ||
        data.price <= 0
    ) {
        throw new ValidationError("Price must be positive and finite");
    }
}

// ============================================================
// 2. REST Resource Service
// ============================================================

class ProductRepository {
    constructor() {
        this.products = new Map([
            [101, { id: 101, name: "Laptop", price: 75000 }],
            [102, { id: 102, name: "Monitor", price: 18000 }]
        ]);
        this.nextId = 103;
    }

    get(id) {
        const product = this.products.get(id);

        if (!product) {
            throw new NotFoundError("Product not found");
        }

        return { ...product };
    }

    create(data) {
        validateProduct(data);

        const product = Object.freeze({
            id: this.nextId++,
            name: data.name.trim(),
            price: data.price
        });

        this.products.set(product.id, product);
        return { ...product };
    }
}

function sendJson(response, status, body) {
    const encoded = JSON.stringify(body);

    response.writeHead(status, {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": Buffer.byteLength(encoded),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff"
    });

    response.end(encoded);
}

async function readJson(request, maximumBytes = 16384) {
    let size = 0;
    const chunks = [];

    for await (const chunk of request) {
        size += chunk.length;

        if (size > maximumBytes) {
            throw new ValidationError("Request body too large");
        }

        chunks.push(chunk);
    }

    if (size === 0) {
        throw new ValidationError("Request body is required");
    }

    try {
        return JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
        throw new ValidationError("Malformed JSON");
    }
}

function createRestServer(repository) {
    return http.createServer(async (request, response) => {
        try {
            const url = new URL(
                request.url,
                "http://127.0.0.1"
            );

            if (request.method === "GET" && url.pathname === "/health") {
                sendJson(response, 200, { status: "healthy" });
                return;
            }

            if (
                request.method === "GET" &&
                /^\/products\/\d+$/.test(url.pathname)
            ) {
                const id = Number(url.pathname.split("/").pop());

                if (!Number.isSafeInteger(id) || id <= 0) {
                    throw new ValidationError("Invalid product ID");
                }

                sendJson(response, 200, {
                    data: repository.get(id)
                });
                return;
            }

            if (
                request.method === "POST" &&
                url.pathname === "/products"
            ) {
                if (!request.headers["content-type"]?.startsWith(
                    "application/json"
                )) {
                    sendJson(response, 415, {
                        error: "JSON content type required"
                    });
                    return;
                }

                const payload = await readJson(request);
                const product = repository.create(payload);

                sendJson(response, 201, { data: product });
                return;
            }

            sendJson(response, 404, { error: "Endpoint not found" });

        } catch (error) {
            const status =
                error instanceof ValidationError ? 400 :
                error instanceof NotFoundError ? 404 :
                500;

            sendJson(response, status, {
                error: error.message
            });
        }
    });
}

// ============================================================
// 3. Typed gRPC-Style RPC
// ============================================================

const RpcStatus = Object.freeze({
    OK: "OK",
    INVALID_ARGUMENT: "INVALID_ARGUMENT",
    NOT_FOUND: "NOT_FOUND",
    DEADLINE_EXCEEDED: "DEADLINE_EXCEEDED",
    UNAVAILABLE: "UNAVAILABLE",
    INTERNAL: "INTERNAL"
});

class GetProductRequest {
    constructor(productId) {
        if (!Number.isSafeInteger(productId) || productId <= 0) {
            throw new ValidationError("Invalid product ID");
        }

        this.productId = productId;
        Object.freeze(this);
    }
}

class ProductRpcService {
    constructor(repository) {
        this.repository = repository;
    }

    async getProduct(request) {
        try {
            const product = this.repository.get(request.productId);

            return {
                status: RpcStatus.OK,
                payload: product
            };

        } catch (error) {
            if (error instanceof NotFoundError) {
                return {
                    status: RpcStatus.NOT_FOUND,
                    payload: null,
                    message: error.message
                };
            }

            return {
                status: RpcStatus.INTERNAL,
                payload: null,
                message: "RPC processing failed"
            };
        }
    }
}

class RpcClient {
    constructor(service) {
        this.service = service;
    }

    async invoke(request, timeoutMs = 2000) {
        if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
            throw new ValidationError("Invalid RPC deadline");
        }

        let timer;

        try {
            const deadline = new Promise((_, reject) => {
                timer = setTimeout(
                    () => reject(new UnavailableError(
                        "RPC deadline exceeded"
                    )),
                    timeoutMs
                );
            });

            return await Promise.race([
                this.service.getProduct(request),
                deadline
            ]);

        } catch (error) {
            return {
                status: RpcStatus.DEADLINE_EXCEEDED,
                payload: null,
                message: error.message
            };
        } finally {
            clearTimeout(timer);
        }
    }
}

// ============================================================
// 4. Asynchronous Message Broker
// ============================================================

class MessageBroker extends EventEmitter {
    constructor(maxRetries = 3) {
        super();

        if (!Number.isInteger(maxRetries) || maxRetries < 0) {
            throw new ValidationError("Invalid retry count");
        }

        this.maxRetries = maxRetries;
        this.queues = new Map();
        this.handlers = new Map();
        this.deadLetters = [];
        this.processing = new Set();
    }

    subscribe(topic, handler) {
        if (!topic || typeof handler !== "function") {
            throw new ValidationError("Invalid subscription");
        }

        if (!this.handlers.has(topic)) {
            this.handlers.set(topic, []);
        }

        this.handlers.get(topic).push(handler);
    }

    publish(topic, payload, correlationId = crypto.randomUUID()) {
        if (!topic || !payload || typeof payload !== "object") {
            throw new ValidationError("Invalid message");
        }

        const message = {
            id: crypto.randomUUID(),
            topic,
            payload: structuredClone(payload),
            correlationId,
            attempts: 0,
            createdAt: new Date().toISOString()
        };

        if (!this.queues.has(topic)) {
            this.queues.set(topic, []);
        }

        this.queues.get(topic).push(message);

        this.emit("published", message);
        return message.id;
    }

    async consumeOne(topic) {
        const queue = this.queues.get(topic);

        if (!queue || queue.length === 0) {
            return false;
        }

        const handlers = this.handlers.get(topic);

        if (!handlers || handlers.length === 0) {
            return false;
        }

        const message = queue.shift();

        if (this.processing.has(message.id)) {
            return false;
        }

        this.processing.add(message.id);

        try {
            for (const handler of handlers) {
                await handler(message.payload, message);
            }

            this.emit("acknowledged", message);
            return true;

        } catch (error) {
            message.attempts++;

            this.emit("deliveryFailed", {
                message,
                error
            });

            if (message.attempts > this.maxRetries) {
                this.deadLetters.push({
                    ...message,
                    failure: error.message
                });

                this.emit("deadLettered", message);
            } else {
                await new Promise(resolve =>
                    setTimeout(
                        resolve,
                        Math.min(100 * 2 ** (message.attempts - 1), 2000)
                    )
                );

                queue.push(message);
            }

            return false;

        } finally {
            this.processing.delete(message.id);
        }
    }

    async consumeAll(topic, limit = 100) {
        if (!Number.isInteger(limit) || limit < 0) {
            throw new ValidationError("Invalid consumption limit");
        }

        let count = 0;

        while (count < limit) {
            const queue = this.queues.get(topic);

            if (!queue || queue.length === 0) {
                break;
            }

            const result = await this.consumeOne(topic);

            if (result) {
                count++;
            } else if (
                this.deadLetters.some(item => item.topic === topic) ||
                !this.handlers.has(topic)
            ) {
                break;
            }
        }

        return count;
    }
}

// ============================================================
// 5. Idempotent Event Consumer
// ============================================================

class InventoryConsumer {
    constructor() {
        this.processed = new Set();
        this.inventory = new Map();
    }

    async handle(payload) {
        const { eventId, productId, quantity } = payload;

        if (
            typeof eventId !== "string" ||
            !Number.isSafeInteger(productId) ||
            !Number.isInteger(quantity) ||
            quantity <= 0
        ) {
            throw new ValidationError("Invalid inventory event");
        }

        if (this.processed.has(eventId)) {
            return;
        }

        // A database transaction must protect both updates
        // when this logic is moved into a persistent consumer.
        const current = this.inventory.get(productId) || 0;

        this.inventory.set(productId, current + quantity);
        this.processed.add(eventId);
    }
}

// ============================================================
// 6. Transactional Outbox Simulation
// ============================================================

class Outbox {
    constructor() {
        this.events = [];
        this.products = new Map();
    }

    createProduct(product) {
        validateProduct(product);

        const id = this.products.size + 1;
        const event = {
            eventId: crypto.randomUUID(),
            eventType: "ProductCreated",
            payload: {
                productId: id,
                name: product.name.trim(),
                price: product.price
            },
            published: false
        };

        // Both changes occur synchronously in this in-memory
        // example. Production systems require one DB transaction.
        this.products.set(id, event.payload);
        this.events.push(event);

        return event;
    }

    dispatch(broker) {
        let count = 0;

        for (const event of this.events) {
            if (event.published) {
                continue;
            }

            broker.publish(
                "product.events",
                event,
                event.eventId
            );

            event.published = true;
            count++;
        }

        return count;
    }
}

// ============================================================
// 7. Communication Security Policy
// ============================================================

class CommunicationPolicy {
    constructor({
        protocol,
        authenticated,
        encrypted,
        timeoutMs,
        maxPayloadBytes
    }) {
        Object.assign(this, {
            protocol,
            authenticated,
            encrypted,
            timeoutMs,
            maxPayloadBytes
        });
    }

    validate() {
        if (!["REST", "gRPC", "MESSAGING"].includes(this.protocol)) {
            throw new ValidationError("Unsupported protocol");
        }

        if (!this.authenticated || !this.encrypted) {
            throw new Error(
                "Authenticated and encrypted communication required"
            );
        }

        if (
            !Number.isFinite(this.timeoutMs) ||
            this.timeoutMs <= 0 ||
            !Number.isInteger(this.maxPayloadBytes) ||
            this.maxPayloadBytes <= 0
        ) {
            throw new ValidationError("Invalid communication limits");
        }
    }
}

// ============================================================
// 8. Integration Demonstration
// ============================================================

async function main() {
    const repository = new ProductRepository();

    // REST
    console.log("\n--- REST ---");

    const server = createRestServer(repository);

    await new Promise(resolve =>
        server.listen(0, "127.0.0.1", resolve)
    );

    const address = server.address();
    const baseUrl = `http://127.0.0.1:${address.port}`;

    try {
        const response = await fetch(`${baseUrl}/products/101`);
        console.log("REST response:", response.status, await response.json());

        const created = await fetch(`${baseUrl}/products`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: "Keyboard",
                price: 2500
            })
        });

        console.log("Created:", created.status, await created.json());

        const missing = await fetch(`${baseUrl}/products/999`);
        console.log("Missing:", missing.status);

    } finally {
        await new Promise(resolve => server.close(resolve));
    }

    // RPC
    console.log("\n--- gRPC-STYLE RPC ---");

    const rpcService = new ProductRpcService(repository);
    const rpcClient = new RpcClient(rpcService);

    const rpcResult = await rpcClient.invoke(
        new GetProductRequest(101)
    );

    console.log("RPC:", rpcResult);

    // Messaging
    console.log("\n--- MESSAGING ---");

    const broker = new MessageBroker(2);
    const inventory = new InventoryConsumer();

    broker.on("published", message =>
        console.log("Published:", message.id)
    );

    broker.on("acknowledged", message =>
        console.log("Acknowledged:", message.id)
    );

    broker.subscribe(
        "product.events",
        inventory.handle.bind(inventory)
    );

    const eventId = crypto.randomUUID();

    broker.publish("product.events", {
        eventId,
        productId: 101,
        quantity: 5
    });

    await broker.consumeAll("product.events");

    // Duplicate delivery is harmless.
    await inventory.handle({
        eventId,
        productId: 101,
        quantity: 5
    });

    console.log("Inventory:", inventory.inventory.get(101));
    console.log("Processed events:", inventory.processed.size);

    // Outbox
    console.log("\n--- OUTBOX ---");

    const outbox = new Outbox();

    outbox.createProduct({
        name: "Wireless Mouse",
        price: 1500
    });

    console.log("Outbox dispatched:", outbox.dispatch(broker));
    await broker.consumeAll("product.events");

    // Policy
    console.log("\n--- SECURITY POLICY ---");

    const policy = new CommunicationPolicy({
        protocol: "gRPC",
        authenticated: true,
        encrypted: true,
        timeoutMs: 2000,
        maxPayloadBytes: 16384
    });

    policy.validate();
    console.log("Communication policy accepted");

    console.log("\nAll demonstrations completed.");
}

main().catch(error => {
    console.error("Application failure:", error);
    process.exitCode = 1;
});
