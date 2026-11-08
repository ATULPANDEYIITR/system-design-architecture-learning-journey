"use strict";

/**
 * API Gateway
 *
 * Node.js implementation of:
 * - Declarative route registration
 * - Asynchronous upstream dispatch
 * - Bearer-token authentication
 * - Scope-based authorization
 * - Token-bucket rate limiting
 * - Middleware execution
 * - Circuit-breaker protection
 * - Request auditing
 * - Policy validation and testing
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");

// -------------------------------------------------------
// HTTP response utilities
// -------------------------------------------------------

class GatewayError extends Error {
    constructor(statusCode, message, code) {
        super(message);
        this.statusCode = statusCode;
        this.code = code;
    }
}

function createResponse(statusCode, body, headers = {}) {
    return {
        statusCode,
        body,
        headers: {
            "content-type": "application/json",
            ...headers
        }
    };
}

// -------------------------------------------------------
// Client registry
// -------------------------------------------------------

class ClientRegistry {
    #clients = new Map();

    register(client) {
        if (!client.id || !client.token) {
            throw new Error("Client ID and token are required");
        }

        if (this.#clients.has(client.token)) {
            throw new Error("Duplicate client token");
        }

        this.#clients.set(client.token, Object.freeze({
            id: client.id,
            token: client.token,
            scopes: new Set(client.scopes),
            enabled: client.enabled !== false
        }));
    }

    authenticate(headers) {
        const authorization = headers.authorization || "";

        if (!authorization.startsWith("Bearer ")) {
            throw new GatewayError(
                401,
                "Bearer token required",
                "UNAUTHENTICATED"
            );
        }

        const token = authorization.slice(7).trim();
        const client = this.#clients.get(token);

        if (!client || !client.enabled) {
            throw new GatewayError(
                401,
                "Invalid or disabled credentials",
                "INVALID_TOKEN"
            );
        }

        return client;
    }

    authorize(client, scope) {
        if (!client.scopes.has(scope)) {
            throw new GatewayError(
                403,
                "Insufficient permissions",
                "FORBIDDEN"
            );
        }
    }
}

// -------------------------------------------------------
// Route registry
// -------------------------------------------------------

class RouteRegistry {
    #routes = [];

    register({
        id,
        method,
        path,
        service,
        scope,
        rateLimit = 5,
        burstCapacity = 10
    }) {
        if (!id || !service || !scope) {
            throw new Error("Incomplete route configuration");
        }

        if (!["GET", "POST", "PUT", "PATCH", "DELETE"].includes(method)) {
            throw new Error("Unsupported HTTP method");
        }

        if (!path.startsWith("/")) {
            throw new Error("Route must start with /");
        }

        if (
            !Number.isInteger(rateLimit) ||
            !Number.isInteger(burstCapacity) ||
            rateLimit <= 0 ||
            burstCapacity <= 0
        ) {
            throw new Error("Invalid rate-limit configuration");
        }

        if (this.#routes.some(route =>
            route.id === id ||
            (route.method === method && route.path === path)
        )) {
            throw new Error("Duplicate route");
        }

        // Convert named path segments into regular expressions.
        const parameterNames = [];

        const escaped = path.replace(
            /[.*+?^${}()|[\]\\]/g,
            "\\$&"
        );

        const expression = escaped.replace(
            /\\\{([a-zA-Z_][a-zA-Z0-9_]*)\\\}/g,
            (_, name) => {
                parameterNames.push(name);
                return "([^/]+)";
            }
        );

        const pattern = new RegExp(`^${expression}$`);

        this.#routes.push({
            id,
            method,
            path,
            service,
            scope,
            rateLimit,
            burstCapacity,
            pattern,
            parameterNames,
            specificity: path.split("/").length * 100 +
                path.replace(/\{[^}]+\}/g, "").length
        });

        this.#routes.sort(
            (a, b) => b.specificity - a.specificity
        );
    }

    resolve(method, path) {
        for (const route of this.#routes) {
            if (route.method !== method) {
                continue;
            }

            const match = path.match(route.pattern);

            if (!match) {
                continue;
            }

            const parameters = {};

            route.parameterNames.forEach((name, index) => {
                parameters[name] = decodeURIComponent(match[index + 1]);
            });

            return { route, parameters };
        }

        return null;
    }
}

// -------------------------------------------------------
// Token bucket rate limiter
// -------------------------------------------------------

class TokenBucket {
    constructor(rate, capacity) {
        if (rate <= 0 || capacity <= 0) {
            throw new Error("Invalid bucket parameters");
        }

        this.rate = rate;
        this.capacity = capacity;
        this.tokens = capacity;
        this.lastRefill = Date.now();
    }

    consume(now = Date.now()) {
        const elapsed = Math.max(0, now - this.lastRefill);

        this.tokens = Math.min(
            this.capacity,
            this.tokens + elapsed * this.rate / 1000
        );

        this.lastRefill = Math.max(this.lastRefill, now);

        if (this.tokens < 1) {
            const retryAfter = Math.ceil(
                (1 - this.tokens) / this.rate
            );

            return {
                allowed: false,
                remaining: 0,
                retryAfter
            };
        }

        this.tokens -= 1;

        return {
            allowed: true,
            remaining: Math.floor(this.tokens),
            retryAfter: 0
        };
    }
}

class RateLimiter {
    #buckets = new Map();

    allow(clientId, route) {
        const key = `${clientId}:${route.id}`;

        let bucket = this.#buckets.get(key);

        if (!bucket) {
            bucket = new TokenBucket(
                route.rateLimit,
                route.burstCapacity
            );

            this.#buckets.set(key, bucket);
        }

        return bucket.consume();
    }
}

// -------------------------------------------------------
// Circuit breaker
// -------------------------------------------------------

class CircuitBreaker {
    constructor({
        failureThreshold = 3,
        resetTimeout = 5000
    } = {}) {
        this.failureThreshold = failureThreshold;
        this.resetTimeout = resetTimeout;
        this.failures = 0;
        this.state = "CLOSED";
        this.openedAt = 0;
    }

    canExecute(now = Date.now()) {
        if (this.state === "OPEN") {
            if (now - this.openedAt >= this.resetTimeout) {
                this.state = "HALF_OPEN";
                return true;
            }

            return false;
        }

        return true;
    }

    success() {
        this.failures = 0;
        this.state = "CLOSED";
    }

    failure(now = Date.now()) {
        this.failures++;

        if (
            this.state === "HALF_OPEN" ||
            this.failures >= this.failureThreshold
        ) {
            this.state = "OPEN";
            this.openedAt = now;
        }
    }
}

// -------------------------------------------------------
// Upstream service registry
// -------------------------------------------------------

class UpstreamRegistry {
    #services = new Map();
    #breakers = new Map();

    register(name, handler, breakerOptions = {}) {
        if (this.#services.has(name)) {
            throw new Error(`Duplicate service: ${name}`);
        }

        this.#services.set(name, handler);

        this.#breakers.set(
            name,
            new CircuitBreaker(breakerOptions)
        );
    }

    async forward(name, request, parameters) {
        const handler = this.#services.get(name);
        const breaker = this.#breakers.get(name);

        if (!handler) {
            throw new GatewayError(
                502,
                "Upstream service not registered",
                "UPSTREAM_NOT_FOUND"
            );
        }

        if (!breaker.canExecute()) {
            throw new GatewayError(
                503,
                "Upstream circuit is open",
                "CIRCUIT_OPEN"
            );
        }

        try {
            const result = await handler(request, parameters);

            if (
                !result ||
                !Number.isInteger(result.statusCode) ||
                !result.body
            ) {
                throw new Error("Invalid upstream response");
            }

            if (result.statusCode >= 500) {
                breaker.failure();
            } else {
                breaker.success();
            }

            return result;

        } catch (error) {
            breaker.failure();
            throw error;
        }
    }
}

// -------------------------------------------------------
// Middleware pipeline
// -------------------------------------------------------

class MiddlewarePipeline {
    #middleware = [];

    use(handler) {
        if (typeof handler !== "function") {
            throw new TypeError("Middleware must be a function");
        }

        this.#middleware.push(handler);
    }

    async execute(context, finalHandler) {
        let index = -1;

        const dispatch = async position => {
            if (position <= index) {
                throw new Error("Middleware called next more than once");
            }

            index = position;

            if (position === this.#middleware.length) {
                return finalHandler(context);
            }

            const middleware = this.#middleware[position];

            return middleware(context, () => dispatch(position + 1));
        };

        return dispatch(0);
    }
}

// -------------------------------------------------------
// Audit subsystem
// -------------------------------------------------------

class AuditLog {
    #records = [];

    add(record) {
        this.#records.push(Object.freeze({
            ...record,
            timestamp: new Date().toISOString()
        }));
    }

    statistics() {
        const counts = new Map();

        for (const record of this.#records) {
            counts.set(
                record.statusCode,
                (counts.get(record.statusCode) || 0) + 1
            );
        }

        return Object.fromEntries(counts);
    }

    async export(filename) {
        await fs.writeFile(
            filename,
            JSON.stringify(this.#records, null, 2),
            { encoding: "utf8", mode: 0o600 }
        );
    }

    get records() {
        return [...this.#records];
    }
}

// -------------------------------------------------------
// API Gateway
// -------------------------------------------------------

class APIGateway {
    constructor({
        clients,
        routes,
        upstreams
    }) {
        this.clients = clients;
        this.routes = routes;
        this.upstreams = upstreams;
        this.limiter = new RateLimiter();
        this.pipeline = new MiddlewarePipeline();
        this.audit = new AuditLog();

        this.pipeline.use(async (context, next) => {
            context.requestId = crypto.randomUUID();
            return next();
        });

        this.pipeline.use(async (context, next) => {
            const client = this.clients.authenticate(
                context.request.headers
            );

            context.client = client;

            return next();
        });
    }

    async handle(request) {
        const context = {
            request,
            requestId: null,
            client: null,
            route: null
        };

        let statusCode = 500;

        try {
            const response = await this.pipeline.execute(
                context,
                async ctx => {

                    const { method, path } = ctx.request;

                    if (
                        !["GET", "POST", "PUT", "PATCH", "DELETE"]
                            .includes(method)
                    ) {
                        throw new GatewayError(
                            400,
                            "Unsupported HTTP method",
                            "INVALID_METHOD"
                        );
                    }

                    if (
                        typeof path !== "string" ||
                        !path.startsWith("/") ||
                        path.length > 2048 ||
                        path.split("/").includes("..")
                    ) {
                        throw new GatewayError(
                            400,
                            "Invalid request path",
                            "INVALID_PATH"
                        );
                    }

                    const match = this.routes.resolve(method, path);

                    if (!match) {
                        throw new GatewayError(
                            404,
                            "Route not found",
                            "NOT_FOUND"
                        );
                    }

                    ctx.route = match.route;

                    this.clients.authorize(
                        ctx.client,
                        match.route.scope
                    );

                    const rate = this.limiter.allow(
                        ctx.client.id,
                        match.route
                    );

                    if (!rate.allowed) {
                        const error = new GatewayError(
                            429,
                            "Rate limit exceeded",
                            "RATE_LIMITED"
                        );

                        error.retryAfter = rate.retryAfter;
                        throw error;
                    }

                    const upstreamResponse =
                        await this.upstreams.forward(
                            match.route.service,
                            ctx.request,
                            match.parameters
                        );

                    return createResponse(
                        upstreamResponse.statusCode,
                        upstreamResponse.body,
                        {
                            "x-request-id": ctx.requestId,
                            "x-ratelimit-remaining":
                                String(rate.remaining),
                            ...upstreamResponse.headers
                        }
                    );
                }
            );

            statusCode = response.statusCode;
            return response;

        } catch (error) {
            statusCode = error.statusCode || 502;

            return createResponse(
                statusCode,
                {
                    requestId: context.requestId,
                    error: error.code || "GATEWAY_ERROR",
                    message: error.statusCode
                        ? error.message
                        : "Upstream or gateway failure"
                },
                {
                    "x-request-id": context.requestId || ""
                }
            );

        } finally {
            this.audit.add({
                requestId: context.requestId,
                clientId: context.client?.id || "anonymous",
                method: request.method,
                path: request.path,
                statusCode
            });
        }
    }
}

// -------------------------------------------------------
// Example services
// -------------------------------------------------------

async function userService(request, parameters) {
    return createResponse(200, {
        service: "user-service",
        userId: parameters.userId,
        name: "Example User"
    });
}

async function orderService(request) {
    if (
        typeof request.body?.amount !== "number" ||
        !Number.isFinite(request.body.amount) ||
        request.body.amount <= 0
    ) {
        return createResponse(400, {
            error: "A positive order amount is required"
        });
    }

    return createResponse(201, {
        service: "order-service",
        orderId: crypto.randomUUID(),
        amount: request.body.amount,
        status: "CREATED"
    });
}

// -------------------------------------------------------
// Application configuration
// -------------------------------------------------------

function buildGateway() {
    const clients = new ClientRegistry();

    clients.register({
        id: "client-001",
        token: "demo-user-token",
        scopes: ["users:read", "orders:create"]
    });

    clients.register({
        id: "client-002",
        token: "demo-admin-token",
        scopes: [
            "users:read",
            "users:delete",
            "orders:create"
        ]
    });

    const routes = new RouteRegistry();

    routes.register({
        id: "get-user",
        method: "GET",
        path: "/api/v1/users/{userId}",
        service: "users",
        scope: "users:read",
        rateLimit: 3,
        burstCapacity: 5
    });

    routes.register({
        id: "create-order",
        method: "POST",
        path: "/api/v1/orders",
        service: "orders",
        scope: "orders:create",
        rateLimit: 5,
        burstCapacity: 10
    });

    const upstreams = new UpstreamRegistry();

    upstreams.register("users", userService);

    upstreams.register("orders", orderService, {
        failureThreshold: 3,
        resetTimeout: 5000
    });

    return new APIGateway({
        clients,
        routes,
        upstreams
    });
}

// -------------------------------------------------------
// Automated tests
// -------------------------------------------------------

async function runTests() {
    const gateway = buildGateway();

    const request = (method, path, token, body = {}) => ({
        method,
        path,
        headers: token
            ? { authorization: `Bearer ${token}` }
            : {},
        body
    });

    let response;

    response = await gateway.handle(
        request(
            "GET",
            "/api/v1/users/101",
            "demo-user-token"
        )
    );

    console.assert(response.statusCode === 200);

    response = await gateway.handle(
        request("GET", "/api/v1/users/101")
    );

    console.assert(response.statusCode === 401);

    response = await gateway.handle(
        request(
            "POST",
            "/api/v1/orders",
            "demo-user-token",
            { amount: 2500 }
        )
    );

    console.assert(response.statusCode === 201);

    response = await gateway.handle(
        request(
            "POST",
            "/api/v1/orders",
            "demo-user-token",
            { amount: -10 }
        )
    );

    console.assert(response.statusCode === 400);

    response = await gateway.handle(
        request(
            "GET",
            "/api/v1/unknown",
            "demo-user-token"
        )
    );

    console.assert(response.statusCode === 404);

    response = await gateway.handle(
        request(
            "DELETE",
            "/api/v1/users/101",
            "demo-user-token"
        )
    );

    console.assert(response.statusCode === 404);

    // Independent rate-limiter test.
    const bucket = new TokenBucket(1, 2);

    console.assert(bucket.consume(1000).allowed);
    console.assert(bucket.consume(1000).allowed);
    console.assert(!bucket.consume(1000).allowed);
    console.assert(bucket.consume(2000).allowed);

    // Circuit breaker state transitions.
    const breaker = new CircuitBreaker({
        failureThreshold: 2,
        resetTimeout: 100
    });

    breaker.failure(1000);
    breaker.failure(1000);

    console.assert(breaker.state === "OPEN");
    console.assert(!breaker.canExecute(1050));
    console.assert(breaker.canExecute(1100));

    breaker.success();

    console.assert(breaker.state === "CLOSED");

    await gateway.audit.export("gateway_audit.json");

    console.log("All JavaScript gateway tests passed.");
    console.log("Audit statistics:", gateway.audit.statistics());
}

// -------------------------------------------------------
// Main
// -------------------------------------------------------

if (require.main === module) {
    runTests().catch(error => {
        console.error("Gateway test failure:", error);
        process.exitCode = 1;
    });
}

module.exports = {
    APIGateway,
    ClientRegistry,
    RouteRegistry,
    RateLimiter,
    TokenBucket,
    CircuitBreaker,
    UpstreamRegistry,
    buildGateway
};
