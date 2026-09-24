/*
 * Web Architecture and REST APIs
 * Resources, Endpoints, HTTP Methods, and Statelessness
 *
 * Self-contained executable study implementation.
 * Runtime: modern Node.js
 */

"use strict";

// ============================================================================
// 1. BASIC TERMINOLOGY
// ============================================================================

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function subsection(title) {
    console.log("\n" + "-".repeat(78));
    console.log(title);
    console.log("-".repeat(78));
}

function fundamentalsDemo() {
    section("1. REST API fundamentals");

    const terms = {
        "Web architecture":
            "The organization of clients, servers, resources, protocols, and intermediaries.",
        "API":
            "A contract through which software components communicate.",
        "REST":
            "An architectural style based on resource identification, a uniform interface, statelessness, cacheability, client-server separation, and layered systems.",
        "Resource":
            "A conceptual entity exposed through an API.",
        "Endpoint":
            "An HTTP-accessible URI pattern combined with an HTTP method.",
        "Representation":
            "A transferable form of a resource, commonly JSON.",
        "Statelessness":
            "Each request contains the information needed for independent processing."
    };

    for (const [term, definition] of Object.entries(terms)) {
        console.log(`${term}: ${definition}`);
    }

    console.log("\nTypical resource-oriented endpoints:");
    [
        "GET    /api/v1/products",
        "GET    /api/v1/products/42",
        "POST   /api/v1/products",
        "PATCH  /api/v1/products/42",
        "DELETE /api/v1/products/42"
    ].forEach(item => console.log("  " + item));
}


// ============================================================================
// 2. RESOURCE REPRESENTATION
// ============================================================================

class Product {
    constructor({ id, name, category, price, stock, active = true }) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
        this.stock = stock;
        this.active = active;
        this.createdAt = new Date().toISOString();
    }

    toJSON() {
        return {
            id: this.id,
            name: this.name,
            category: this.category,
            price: this.price,
            stock: this.stock,
            active: this.active,
            createdAt: this.createdAt
        };
    }
}

function resourceDemo() {
    section("2. Resources and representations");

    const product = new Product({
        id: 101,
        name: "Mechanical Keyboard",
        category: "electronics",
        price: 3499,
        stock: 25
    });

    console.log("Resource:");
    console.log(product);

    console.log("\nJSON representation:");
    console.log(JSON.stringify(product, null, 2));
}


// ============================================================================
// 3. HTTP METHODS
// ============================================================================

function methodDemo() {
    section("3. HTTP methods");

    const methods = [
        ["GET", "Retrieve", true, true],
        ["POST", "Create/process", false, false],
        ["PUT", "Replace", false, true],
        ["PATCH", "Partially modify", false, "Depends on design"],
        ["DELETE", "Delete", false, true],
        ["HEAD", "Retrieve headers", true, true],
        ["OPTIONS", "Discover supported operations", true, true]
    ];

    console.table(
        methods.map(([method, purpose, safe, idempotent]) => ({
            method,
            purpose,
            safe,
            idempotent
        }))
    );

    console.log(
        "\nSafe means the method is not intended to change resource state."
    );
    console.log(
        "Idempotent means repeating the same operation has the same intended effect."
    );
}


// ============================================================================
// 4. REQUEST AND RESPONSE OBJECTS
// ============================================================================

function createRequest(method, path, options = {}) {
    return {
        method,
        path,
        headers: options.headers || {},
        query: options.query || {},
        body: options.body ?? null
    };
}

function createResponse(status, body = null, headers = {}) {
    return {
        status,
        headers,
        body
    };
}

function requestResponseDemo() {
    section("4. HTTP request and response");

    const request = createRequest("GET", "/api/v1/products/101", {
        headers: {
            Accept: "application/json",
            Authorization: "Bearer example-token"
        }
    });

    const response = createResponse(
        200,
        {
            id: 101,
            name: "Mechanical Keyboard",
            price: 3499
        },
        {
            "Content-Type": "application/json",
            "Cache-Control": "max-age=60"
        }
    );

    console.log("Request:");
    console.log(JSON.stringify(request, null, 2));

    console.log("\nResponse:");
    console.log(JSON.stringify(response, null, 2));
}


// ============================================================================
// 5. VALIDATION
// ============================================================================

class ValidationError extends Error {
    constructor(fields) {
        super("Request validation failed");
        this.name = "ValidationError";
        this.fields = fields;
    }
}

function validateProduct(payload) {
    const errors = {};

    if (typeof payload.name !== "string" || payload.name.trim() === "") {
        errors.name = "name must be a non-empty string";
    }

    if (
        typeof payload.price !== "number" ||
        !Number.isFinite(payload.price) ||
        payload.price < 0
    ) {
        errors.price = "price must be a finite non-negative number";
    }

    if (!Number.isInteger(payload.stock) || payload.stock < 0) {
        errors.stock = "stock must be a non-negative integer";
    }

    if (Object.keys(errors).length > 0) {
        throw new ValidationError(errors);
    }
}

function validationDemo() {
    section("5. Validation and structured errors");

    try {
        validateProduct({
            name: "",
            price: -10,
            stock: "many"
        });
    } catch (error) {
        const response = createResponse(
            422,
            {
                error: {
                    code: "VALIDATION_ERROR",
                    message: error.message,
                    fields: error.fields
                }
            },
            {
                "Content-Type": "application/json"
            }
        );

        console.log(JSON.stringify(response, null, 2));
    }
}


// ============================================================================
// 6. IN-MEMORY RESOURCE REPOSITORY
// ============================================================================

class ProductRepository {
    constructor() {
        this.products = new Map();
        this.nextId = 1;
    }

    create(data) {
        const product = new Product({
            id: this.nextId,
            name: data.name,
            category: data.category || "uncategorized",
            price: Number(data.price),
            stock: Number(data.stock)
        });

        this.products.set(this.nextId, product);
        this.nextId += 1;

        return product;
    }

    get(id) {
        return this.products.get(Number(id));
    }

    list() {
        return [...this.products.values()];
    }

    update(id, fields) {
        const product = this.get(id);

        if (!product) {
            return null;
        }

        Object.assign(product, fields);
        return product;
    }

    delete(id) {
        return this.products.delete(Number(id));
    }
}


// ============================================================================
// 7. RESOURCE CONTROLLER
// ============================================================================

class ProductController {
    constructor(repository) {
        this.repository = repository;
    }

    list(query = {}) {
        let products = this.repository.list();

        if (query.category) {
            products = products.filter(
                product =>
                    product.category.toLowerCase() ===
                    String(query.category).toLowerCase()
            );
        }

        if (query.minPrice !== undefined) {
            products = products.filter(
                product => product.price >= Number(query.minPrice)
            );
        }

        if (query.maxPrice !== undefined) {
            products = products.filter(
                product => product.price <= Number(query.maxPrice)
            );
        }

        if (query.sort === "-price") {
            products.sort((a, b) => b.price - a.price);
        } else if (query.sort === "price") {
            products.sort((a, b) => a.price - b.price);
        }

        const page = Math.max(1, Number(query.page || 1));
        const limit = Math.min(100, Math.max(1, Number(query.limit || 10)));

        const start = (page - 1) * limit;
        const pageItems = products.slice(start, start + limit);

        return createResponse(200, {
            data: pageItems,
            pagination: {
                page,
                limit,
                total: products.length,
                pages: products.length
                    ? Math.ceil(products.length / limit)
                    : 0
            }
        });
    }

    get(id) {
        const product = this.repository.get(id);

        if (!product) {
            return createResponse(404, {
                error: {
                    code: "PRODUCT_NOT_FOUND",
                    message: `Product ${id} was not found`
                }
            });
        }

        return createResponse(200, { data: product });
    }

    create(payload) {
        try {
            validateProduct(payload);
        } catch (error) {
            return createResponse(422, {
                error: {
                    code: "VALIDATION_ERROR",
                    fields: error.fields
                }
            });
        }

        const product = this.repository.create(payload);

        return createResponse(
            201,
            { data: product },
            {
                Location: `/api/v1/products/${product.id}`
            }
        );
    }

    patch(id, fields) {
        const allowed = new Set([
            "name",
            "category",
            "price",
            "stock",
            "active"
        ]);

        const unknown = Object.keys(fields).filter(
            field => !allowed.has(field)
        );

        if (unknown.length > 0) {
            return createResponse(400, {
                error: {
                    code: "UNKNOWN_FIELD",
                    fields: unknown
                }
            });
        }

        const product = this.repository.update(id, fields);

        if (!product) {
            return createResponse(404, {
                error: {
                    code: "PRODUCT_NOT_FOUND"
                }
            });
        }

        return createResponse(200, { data: product });
    }

    delete(id) {
        if (!this.repository.delete(id)) {
            return createResponse(404, {
                error: {
                    code: "PRODUCT_NOT_FOUND"
                }
            });
        }

        return createResponse(204);
    }
}

function controllerDemo() {
    section("6. Complete resource controller");

    const repository = new ProductRepository();
    const controller = new ProductController(repository);

    console.log("POST /api/v1/products");
    let response = controller.create({
        name: "Mechanical Keyboard",
        category: "electronics",
        price: 3499,
        stock: 25
    });
    console.log(JSON.stringify(response, null, 2));

    const productId = response.body.data.id;

    console.log("\nGET /api/v1/products");
    response = controller.list({
        category: "electronics",
        sort: "-price",
        page: 1,
        limit: 10
    });
    console.log(JSON.stringify(response, null, 2));

    console.log(`\nPATCH /api/v1/products/${productId}`);
    response = controller.patch(productId, {
        price: 3299,
        stock: 30
    });
    console.log(JSON.stringify(response, null, 2));

    console.log(`\nGET /api/v1/products/${productId}`);
    response = controller.get(productId);
    console.log(JSON.stringify(response, null, 2));

    console.log("\nGET /api/v1/products/9999");
    console.log(
        JSON.stringify(controller.get(9999), null, 2)
    );
}


// ============================================================================
// 8. ROUTING
// ============================================================================

class Router {
    constructor() {
        this.routes = [];
    }

    add(method, pattern, handler) {
        this.routes.push({
            method,
            pattern,
            handler
        });
    }

    dispatch(request) {
        for (const route of this.routes) {
            if (route.method !== request.method) {
                continue;
            }

            const match = request.path.match(route.pattern);

            if (match) {
                return route.handler(request, match.groups || {});
            }
        }

        return createResponse(404, {
            error: {
                code: "ROUTE_NOT_FOUND",
                message: "No matching endpoint"
            }
        });
    }
}

function routingDemo() {
    section("7. Endpoint routing");

    const router = new Router();

    router.add(
        "GET",
        /^\/api\/v1\/products\/(?<id>\d+)$/,
        (request, params) =>
            createResponse(200, {
                resource: "product",
                id: Number(params.id),
                method: request.method
            })
    );

    const request = createRequest(
        "GET",
        "/api/v1/products/42"
    );

    console.log(
        JSON.stringify(router.dispatch(request), null, 2)
    );
}


// ============================================================================
// 9. PUT VERSUS PATCH
// ============================================================================

function putPatchDemo() {
    section("9. PUT versus PATCH");

    const original = {
        id: 7,
        name: "Monitor",
        category: "electronics",
        price: 20000,
        stock: 10
    };

    const putRepresentation = {
        id: original.id,
        name: "4K Monitor",
        category: "electronics",
        price: 22000,
        stock: 8
    };

    const patchRepresentation = {
        ...original,
        price: 21000
    };

    console.log("Original:");
    console.log(original);

    console.log("\nPUT replacement:");
    console.log(putRepresentation);

    console.log("\nPATCH partial update:");
    console.log(patchRepresentation);
}


// ============================================================================
// 10. STATELESSNESS
// ============================================================================

class StatelessApi {
    constructor() {
        this.tokens = new Map([
            ["token-user-1", { userId: 1, role: "customer" }],
            ["token-admin", { userId: 2, role: "admin" }]
        ]);
    }

    authenticate(request) {
        const authorization =
            request.headers?.Authorization ||
            request.headers?.authorization;

        if (!authorization) {
            return null;
        }

        const [scheme, token] = authorization.split(" ");

        if (!scheme || scheme.toLowerCase() !== "bearer") {
            return null;
        }

        return this.tokens.get(token) || null;
    }

    handle(request) {
        const identity = this.authenticate(request);

        if (!identity) {
            return createResponse(
                401,
                {
                    error: {
                        code: "UNAUTHENTICATED",
                        message: "Valid authentication is required"
                    }
                },
                {
                    "WWW-Authenticate": "Bearer"
                }
            );
        }

        return createResponse(200, {
            data: {
                message: "Authenticated request",
                userId: identity.userId,
                role: identity.role
            }
        });
    }
}

function statelessnessDemo() {
    section("10. Statelessness");

    const api = new StatelessApi();

    const requests = [
        createRequest("GET", "/api/v1/account", {
            headers: {
                Authorization: "Bearer token-user-1"
            }
        }),
        createRequest("GET", "/api/v1/account"),
        createRequest("GET", "/api/v1/account", {
            headers: {
                Authorization: "Bearer invalid-token"
            }
        })
    ];

    for (const request of requests) {
        console.log(
            JSON.stringify(api.handle(request), null, 2)
        );
    }

    console.log(
        "\nEach request contains the authentication information required "
        + "to establish the caller identity."
    );
}


// ============================================================================
// 11. IDEMPOTENCY KEYS
// ============================================================================

class PaymentService {
    constructor() {
        this.results = new Map();
        this.nextPaymentId = 1000;
    }

    createPayment(amount, idempotencyKey) {
        if (!idempotencyKey || !idempotencyKey.trim()) {
            throw new Error("idempotency key is required");
        }

        if (this.results.has(idempotencyKey)) {
            return this.results.get(idempotencyKey);
        }

        if (!Number.isFinite(amount) || amount <= 0) {
            throw new Error("amount must be positive");
        }

        const payment = {
            paymentId: this.nextPaymentId++,
            amount,
            status: "accepted"
        };

        this.results.set(idempotencyKey, payment);

        return payment;
    }
}

function idempotencyDemo() {
    section("11. Idempotency keys");

    const service = new PaymentService();

    const key = "checkout-2026-000001";

    const first = service.createPayment(999, key);
    const retry = service.createPayment(999, key);

    console.log("First request:");
    console.log(first);

    console.log("\nRetry:");
    console.log(retry);

    console.log(
        "\nThe same key causes the server to reuse the previous operation result."
    );
}


// ============================================================================
// 12. CONTENT NEGOTIATION
// ============================================================================

function contentNegotiationDemo() {
    section("12. Content negotiation");

    const supported = [
        "application/json",
        "application/problem+json"
    ];

    const acceptHeader = "application/json";

    console.log(`Accept: ${acceptHeader}`);
    console.log(`Supported: ${supported.join(", ")}`);

    if (supported.includes(acceptHeader)) {
        console.log("Selected representation: application/json");
    } else {
        console.log("406 Not Acceptable");
    }

    console.log(
        "\nAccept indicates what the client wants to receive."
    );
    console.log(
        "Content-Type identifies the representation being sent."
    );
}


// ============================================================================
// 13. CACHING AND ETAGS
// ============================================================================

function stableStringify(object) {
    if (object === null || typeof object !== "object") {
        return JSON.stringify(object);
    }

    if (Array.isArray(object)) {
        return `[${object.map(stableStringify).join(",")}]`;
    }

    const keys = Object.keys(object).sort();

    return `{${keys.map(
        key => `${JSON.stringify(key)}:${stableStringify(object[key])}`
    ).join(",")}}`;
}

async function sha256Hex(value) {
    const data = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest("SHA-256", data);

    return [...new Uint8Array(digest)]
        .map(byte => byte.toString(16).padStart(2, "0"))
        .join("");
}

async function cachingDemo() {
    section("13. Caching and conditional requests");

    const representation = {
        id: 101,
        name: "Mechanical Keyboard",
        price: 3499
    };

    const etag = await sha256Hex(
        stableStringify(representation)
    );

    console.log(`ETag: "${etag}"`);
    console.log("Cache-Control: max-age=60");

    const clientEtag = etag;

    if (clientEtag === etag) {
        console.log(
            "304 Not Modified: client cache remains valid."
        );
    } else {
        console.log(
            "200 OK: send current representation."
        );
    }
}


// ============================================================================
// 14. AUTHORIZATION
// ============================================================================

class AuthorizationService {
    constructor() {
        this.permissions = new Map([
            [
                "customer",
                new Set(["GET_PRODUCT"])
            ],
            [
                "admin",
                new Set([
                    "GET_PRODUCT",
                    "CREATE_PRODUCT",
                    "UPDATE_PRODUCT",
                    "DELETE_PRODUCT"
                ])
            ]
        ]);
    }

    can(role, permission) {
        return this.permissions
            .get(role)
            ?.has(permission) ?? false;
    }
}

function authorizationDemo() {
    section("14. Authentication and authorization");

    const service = new AuthorizationService();

    const checks = [
        ["customer", "GET_PRODUCT"],
        ["customer", "DELETE_PRODUCT"],
        ["admin", "DELETE_PRODUCT"]
    ];

    for (const [role, permission] of checks) {
        console.log({
            role,
            permission,
            allowed: service.can(role, permission)
        });
    }

    console.log(
        "\nAuthentication identifies a caller. Authorization determines permissions."
    );
}


// ============================================================================
// 15. RATE LIMITING
// ============================================================================

class FixedWindowRateLimiter {
    constructor(limit, windowMilliseconds) {
        this.limit = limit;
        this.windowMilliseconds = windowMilliseconds;
        this.clients = new Map();
    }

    allow(clientId) {
        const now = Date.now();
        let record = this.clients.get(clientId);

        if (!record || now - record.startedAt >= this.windowMilliseconds) {
            record = {
                startedAt: now,
                count: 0
            };
        }

        if (record.count >= this.limit) {
            this.clients.set(clientId, record);
            return false;
        }

        record.count += 1;
        this.clients.set(clientId, record);

        return true;
    }
}

function rateLimitDemo() {
    section("15. Rate limiting");

    const limiter = new FixedWindowRateLimiter(3, 60_000);

    for (let attempt = 1; attempt <= 5; attempt++) {
        console.log({
            attempt,
            result: limiter.allow("client-1")
                ? "allowed"
                : "429 Too Many Requests"
        });
    }
}


// ============================================================================
// 16. QUERY PARAMETERS AND PAGINATION
// ============================================================================

function queryDemo() {
    section("16. Filtering, sorting, and pagination");

    const products = [
        { id: 1, name: "Keyboard", category: "electronics", price: 3500 },
        { id: 2, name: "Mouse", category: "electronics", price: 1200 },
        { id: 3, name: "Desk", category: "furniture", price: 8000 },
        { id: 4, name: "Monitor", category: "electronics", price: 22000 },
        { id: 5, name: "Chair", category: "furniture", price: 12000 }
    ];

    const url = new URL(
        "https://example.test/api/v1/products?category=electronics&maxPrice=10000&page=1&limit=2&sort=-price"
    );

    let result = products.filter(
        product =>
            product.category === url.searchParams.get("category")
    );

    result = result.filter(
        product =>
            product.price <=
            Number(url.searchParams.get("maxPrice"))
    );

    result.sort((a, b) => b.price - a.price);

    const page = Number(url.searchParams.get("page"));
    const limit = Number(url.searchParams.get("limit"));
    const start = (page - 1) * limit;

    result = result.slice(start, start + limit);

    console.log({
        path: url.pathname,
        query: Object.fromEntries(url.searchParams),
        result
    });
}


// ============================================================================
// 17. ERROR CLASSIFICATION
// ============================================================================

function errorClassificationDemo() {
    section("17. Client and server error classification");

    const examples = [
        [400, "Malformed or invalid request"],
        [401, "Missing or invalid authentication"],
        [403, "Authenticated but not authorized"],
        [404, "Resource does not exist"],
        [409, "Resource state conflict"],
        [422, "Semantically invalid content"],
        [429, "Rate limit exceeded"],
        [500, "Unexpected server-side failure"],
        [503, "Service temporarily unavailable"]
    ];

    for (const [status, description] of examples) {
        console.log(`${status}: ${description}`);
    }
}


// ============================================================================
// 18. SECURITY VALIDATION
// ============================================================================

function securityDemo() {
    section("18. Security considerations");

    const resourceId = "../../private/file";

    if (!/^\d+$/.test(resourceId)) {
        console.log("Rejected unsafe resource identifier.");
    }

    const searchValue = "<script>alert('x')</script>";

    // Treat untrusted input as data. Do not insert it into HTML without
    // context-appropriate output encoding.
    console.log("Untrusted search value:", searchValue);

    console.log("\nImportant controls:");
    console.log("  - TLS");
    console.log("  - authentication");
    console.log("  - authorization");
    console.log("  - input validation");
    console.log("  - rate limiting");
    console.log("  - secure secret storage");
    console.log("  - safe error responses");
    console.log("  - resource ownership checks");
    console.log("  - audit logging");
    console.log("  - dependency and infrastructure hardening");
}


// ============================================================================
// 19. OBSERVABILITY
// ============================================================================

class Metrics {
    constructor() {
        this.endpoints = new Map();
    }

    record(endpoint, latencyMs, success) {
        if (!this.endpoints.has(endpoint)) {
            this.endpoints.set(endpoint, {
                count: 0,
                errors: 0,
                totalLatencyMs: 0
            });
        }

        const metric = this.endpoints.get(endpoint);

        metric.count += 1;
        metric.totalLatencyMs += latencyMs;

        if (!success) {
            metric.errors += 1;
        }
    }

    report() {
        return [...this.endpoints.entries()].map(
            ([endpoint, metric]) => ({
                endpoint,
                requests: metric.count,
                errors: metric.errors,
                averageLatencyMs:
                    metric.totalLatencyMs / metric.count
            })
        );
    }
}

function observabilityDemo() {
    section("19. Observability");

    const metrics = new Metrics();

    metrics.record("/api/v1/products", 12.2, true);
    metrics.record("/api/v1/products", 8.4, true);
    metrics.record("/api/v1/products/101", 4.8, true);
    metrics.record("/api/v1/products/999", 3.1, false);

    console.table(metrics.report());

    console.log(
        "\nProduction APIs commonly expose metrics for traffic, latency, "
        + "errors, saturation, and dependency health."
    );
}


// ============================================================================
// 20. ASYNCHRONOUS HTTP CLIENT EXAMPLE
// ============================================================================

async function simulatedFetch(url, options = {}) {
    // This function models the shape of fetch() without requiring network
    // access. It deliberately returns a deterministic local response.
    await new Promise(resolve => setTimeout(resolve, 10));

    return {
        ok: true,
        status: 200,
        url,
        method: options.method || "GET",
        json: async () => ({
            data: {
                message: "Simulated API response"
            }
        })
    };
}

async function asynchronousClientDemo() {
    section("20. Asynchronous JavaScript API client");

    const response = await simulatedFetch(
        "https://example.test/api/v1/products/101",
        {
            method: "GET",
            headers: {
                Accept: "application/json"
            }
        }
    );

    if (!response.ok) {
        throw new Error(`HTTP request failed with ${response.status}`);
    }

    const payload = await response.json();

    console.log(payload);
}


// ============================================================================
// 21. RETRY POLICY
// ============================================================================

function isRetryableStatus(status) {
    return (
        status === 408 ||
        status === 429 ||
        status === 500 ||
        status === 502 ||
        status === 503 ||
        status === 504
    );
}

async function retryDemo() {
    section("21. Retry behavior");

    const statuses = [503, 503, 200];

    for (let attempt = 0; attempt < statuses.length; attempt++) {
        const status = statuses[attempt];

        console.log(`Attempt ${attempt + 1}: HTTP ${status}`);

        if (status === 200) {
            console.log("Request succeeded.");
            break;
        }

        if (!isRetryableStatus(status)) {
            console.log("Do not automatically retry this status.");
            break;
        }

        const delay = 25 * 2 ** attempt;

        console.log(
            `Retryable failure. Exponential backoff delay: ${delay} ms`
        );

        await new Promise(resolve => setTimeout(resolve, delay));
    }

    console.log(
        "\nRetries should be bounded and should respect idempotence, "
        + "server guidance, rate limits, and business semantics."
    );
}


// ============================================================================
// 22. HYPERMEDIA
// ============================================================================

function hypermediaDemo() {
    section("22. Hypermedia representation");

    const product = {
        id: 101,
        name: "Mechanical Keyboard",
        links: {
            self: {
                href: "/api/v1/products/101"
            },
            reviews: {
                href: "/api/v1/products/101/reviews"
            },
            collection: {
                href: "/api/v1/products"
            }
        }
    };

    console.log(JSON.stringify(product, null, 2));
}


// ============================================================================
// 23. API VERSIONING
// ============================================================================

function versioningDemo() {
    section("23. API versioning");

    console.log("Version 1: /api/v1/products");
    console.log("Version 2: /api/v2/products");

    console.log("\nPossible approaches:");
    console.log("  - URI versioning");
    console.log("  - header versioning");
    console.log("  - media-type versioning");

    console.log(
        "\nThe example uses URI versioning because the version is visible in the resource URL."
    );
}


// ============================================================================
// 24. PUT/PATCH VALIDATION
// ============================================================================

function updateSemanticsDemo() {
    section("24. Update semantics and edge cases");

    const resource = {
        id: 10,
        name: "Laptop",
        price: 70000,
        stock: 5
    };

    const patch = {
        stock: 4
    };

    const updated = {
        ...resource,
        ...patch
    };

    console.log("PATCH preserves unspecified fields:");
    console.log(updated);

    console.log(
        "\nAn API should define whether null means clearing a field, "
        + "omitting a field means preserving it, and which fields are immutable."
    );
}


// ============================================================================
// 25. API TESTING
// ============================================================================

function testingDemo() {
    section("25. Executable API tests");

    const repository = new ProductRepository();
    const controller = new ProductController(repository);

    let response = controller.create({
        name: "Test Product",
        category: "test",
        price: 100,
        stock: 5
    });

    console.assert(response.status === 201);
    console.assert(response.body.data.name === "Test Product");

    const id = response.body.data.id;

    response = controller.get(id);

    console.assert(response.status === 200);
    console.assert(response.body.data.id === id);

    response = controller.patch(id, {
        stock: 3
    });

    console.assert(response.status === 200);
    console.assert(response.body.data.stock === 3);

    response = controller.get(999999);

    console.assert(response.status === 404);

    response = controller.create({
        name: "",
        price: -1,
        stock: -4
    });

    console.assert(response.status === 422);

    console.log("All JavaScript assertions completed.");
}


// ============================================================================
// 26. PERFORMANCE
// ============================================================================

function performanceDemo() {
    section("26. Performance considerations");

    const products = [];

    for (let i = 0; i < 100_000; i++) {
        products.push({
            id: i,
            category: i % 2 === 0 ? "electronics" : "other",
            price: i
        });
    }

    const start = performance.now();

    const result = products.filter(
        product =>
            product.category === "electronics" &&
            product.price < 5000
    );

    const elapsed = performance.now() - start;

    console.log(`Products scanned: ${products.length}`);
    console.log(`Products matched: ${result.length}`);
    console.log(`Elapsed time: ${elapsed.toFixed(3)} ms`);

    console.log(
        "\nArray filtering is O(n). A production API normally pushes suitable "
        + "filtering and sorting into an indexed database query."
    );
}


// ============================================================================
// 27. COMPLETE LIFECYCLE
// ============================================================================

function lifecycleDemo() {
    section("27. REST API request lifecycle");

    const lifecycle = [
        "Client creates HTTP request.",
        "DNS/networking locate the service.",
        "TLS protects the connection when HTTPS is used.",
        "Gateway or load balancer may receive the request.",
        "Authentication identifies the caller.",
        "Authorization checks permissions.",
        "Rate limiting controls abusive traffic.",
        "Validation checks request data.",
        "Routing selects the endpoint.",
        "Application logic processes the resource.",
        "Database or downstream services may be called.",
        "Representation and HTTP status are created.",
        "Cache and other headers are added.",
        "Response is returned to the client.",
        "Logging, metrics, and tracing record the operation."
    ];

    lifecycle.forEach(
        (step, index) => console.log(`${index + 1}. ${step}`)
    );
}


// ============================================================================
// 28. MAIN
// ============================================================================

async function main() {
    fundamentalsDemo();
    resourceDemo();
    methodDemo();
    requestResponseDemo();
    validationDemo();
    controllerDemo();
    routingDemo();
    putPatchDemo();
    statelessnessDemo();
    idempotencyDemo();
    contentNegotiationDemo();
    await cachingDemo();
    authorizationDemo();
    rateLimitDemo();
    queryDemo();
    errorClassificationDemo();
    securityDemo();
    observabilityDemo();
    await asynchronousClientDemo();
    await retryDemo();
    hypermediaDemo();
    versioningDemo();
    updateSemanticsDemo();
    testingDemo();
    performanceDemo();
    lifecycleDemo();
}

main().catch(error => {
    console.error("Application error:", error);
    process.exitCode = 1;
});
