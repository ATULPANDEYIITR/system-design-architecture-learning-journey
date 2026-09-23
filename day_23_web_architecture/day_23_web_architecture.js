/*
 * Web Architecture, Client-Server Architecture, and the Browser
 * Request-Response Lifecycle
 *
 * This file uses standard JavaScript APIs and Node.js built-ins.
 *
 * Run:
 *     node web_architecture.js
 *
 * It demonstrates:
 * - URL anatomy
 * - HTTP requests and responses
 * - routing
 * - methods and status codes
 * - query parameters
 * - JSON
 * - validation
 * - cookies and sessions
 * - middleware
 * - caching
 * - asynchronous execution
 * - a real local HTTP server
 * - browser-side Fetch concepts
 * - CORS
 * - concurrency considerations
 * - security and performance principles
 */

"use strict";

const http = require("node:http");
const crypto = require("node:crypto");
const { URL } = require("node:url");

// ============================================================================
// 1. BASIC ARCHITECTURE
// ============================================================================

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function explainArchitecture() {
    section("1. Web architecture fundamentals");

    const components = {
        Browser: "Client software that creates requests, receives responses, and renders resources.",
        Server: "Software that accepts requests and produces responses.",
        HTTP: "Application-layer protocol used to transfer web messages.",
        URL: "Address that identifies a network resource or endpoint.",
        DNS: "Name-resolution system mapping domain names to network addresses.",
        TLS: "Cryptographic protocol used by HTTPS to protect communication.",
        Database: "Persistent storage commonly accessed by application servers.",
    };

    for (const [name, description] of Object.entries(components)) {
        console.log(`${name.padEnd(12)} -> ${description}`);
    }

    console.log(
        "\nTypical path:\n" +
        "Browser -> DNS -> TCP/TLS -> HTTP -> Server -> Application -> " +
        "Database/Services -> HTTP response -> Browser"
    );
}

// ============================================================================
// 2. URL ANATOMY
// ============================================================================

function demonstrateURL() {
    section("2. URL anatomy");

    const address =
        "https://example.com:443/products?id=42&category=books#details";

    const url = new URL(address);

    console.log("Original :", address);
    console.log("Protocol :", url.protocol);
    console.log("Hostname :", url.hostname);
    console.log("Port     :", url.port || "(default)");
    console.log("Pathname :", url.pathname);
    console.log("Search   :", url.search);
    console.log("Fragment :", url.hash);

    console.log("\nQuery parameters:");
    for (const [key, value] of url.searchParams) {
        console.log(`  ${key} = ${value}`);
    }

    console.log(
        "\nThe fragment is normally used by the browser and is not included " +
        "in the HTTP request target sent to the server."
    );
}

// ============================================================================
// 3. HTTP REQUEST AND RESPONSE STRUCTURE
// ============================================================================

function demonstrateHTTPMessages() {
    section("3. HTTP request and response structure");

    const request = {
        method: "GET",
        target: "/products?id=42",
        headers: {
            Host: "shop.example",
            Accept: "application/json",
            "User-Agent": "StudyBrowser/1.0",
        },
        body: null,
    };

    const response = {
        status: 200,
        headers: {
            "Content-Type": "application/json",
            "Cache-Control": "max-age=60",
        },
        body: {
            id: 42,
            name: "Example Product",
        },
    };

    console.log("REQUEST");
    console.log(request);

    console.log("\nRESPONSE");
    console.log(response);
}

// ============================================================================
// 4. METHODS AND STATUS CODES
// ============================================================================

function demonstrateMethodsAndStatusCodes() {
    section("4. HTTP methods and status codes");

    const methods = {
        GET: "Retrieve a representation.",
        POST: "Submit data or request processing.",
        PUT: "Create or replace a representation at a target URI.",
        PATCH: "Partially modify a resource.",
        DELETE: "Request removal of a resource.",
        HEAD: "Retrieve headers without the normal response body.",
        OPTIONS: "Discover supported communication options.",
    };

    console.log("Methods:");
    for (const [method, meaning] of Object.entries(methods)) {
        console.log(`${method.padEnd(8)} ${meaning}`);
    }

    const statuses = {
        200: "OK",
        201: "Created",
        204: "No Content",
        301: "Moved Permanently",
        304: "Not Modified",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Content",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    };

    console.log("\nCommon status codes:");
    for (const [code, meaning] of Object.entries(statuses)) {
        console.log(`${code}: ${meaning}`);
    }
}

// ============================================================================
// 5. ROUTER
// ============================================================================

class Router {
    constructor() {
        this.routes = [];
    }

    get(path, handler) {
        this.routes.push({ method: "GET", path, handler });
    }

    post(path, handler) {
        this.routes.push({ method: "POST", path, handler });
    }

    match(method, pathname) {
        return this.routes.find(
            (route) => route.method === method && route.path === pathname
        );
    }
}

function demonstrateRouting() {
    section("5. Application routing");

    const router = new Router();

    router.get("/", () => ({
        status: 200,
        body: { message: "Home page" },
    }));

    router.get("/health", () => ({
        status: 200,
        body: { status: "healthy" },
    }));

    router.post("/users", () => ({
        status: 201,
        body: { message: "User creation handler" },
    }));

    const requests = [
        ["GET", "/"],
        ["GET", "/health"],
        ["POST", "/users"],
        ["GET", "/missing"],
    ];

    for (const [method, path] of requests) {
        const route = router.match(method, path);

        if (!route) {
            console.log(`${method} ${path} -> 404 Not Found`);
            continue;
        }

        console.log(`${method} ${path} ->`, route.handler());
    }
}

// ============================================================================
// 6. QUERY PARAMETERS
// ============================================================================

function searchProducts(searchURL) {
    const url = new URL(searchURL);
    const query = url.searchParams.get("q");

    if (!query || query.trim() === "") {
        return {
            status: 400,
            body: { error: "q is required" },
        };
    }

    return {
        status: 200,
        body: {
            query,
            results: [
                { id: 1, title: `Result for ${query}` },
                { id: 2, title: `Another result for ${query}` },
            ],
        },
    };
}

function demonstrateQueryParameters() {
    section("6. Query parameters");

    for (const address of [
        "http://localhost/search?q=browser",
        "http://localhost/search",
        "http://localhost/search?q=",
    ]) {
        const result = searchProducts(address);
        console.log(address);
        console.log(result);
    }
}

// ============================================================================
// 7. VALIDATING JSON
// ============================================================================

function createUserFromJSON(rawBody) {
    let payload;

    try {
        payload = JSON.parse(rawBody);
    } catch {
        return {
            status: 400,
            body: { error: "Invalid JSON" },
        };
    }

    if (
        payload === null ||
        typeof payload !== "object" ||
        Array.isArray(payload)
    ) {
        return {
            status: 422,
            body: { error: "JSON object required" },
        };
    }

    if (
        typeof payload.name !== "string" ||
        payload.name.trim().length === 0
    ) {
        return {
            status: 422,
            body: { error: "name must be a non-empty string" },
        };
    }

    if (
        typeof payload.email !== "string" ||
        !payload.email.includes("@")
    ) {
        return {
            status: 422,
            body: { error: "email is invalid" },
        };
    }

    return {
        status: 201,
        body: {
            id: crypto.randomInt(100000, 999999),
            name: payload.name.trim(),
            email: payload.email.trim().toLowerCase(),
        },
    };
}

function demonstrateJSONValidation() {
    section("7. JSON parsing and validation");

    const examples = [
        '{"name":"Atul","email":"atul@example.com"}',
        '{"name":"","email":"bad"}',
        '{"name":"Atul"',
        '["not","an","object"]',
    ];

    for (const example of examples) {
        console.log(`Input: ${example}`);
        console.log(createUserFromJSON(example));
        console.log();
    }
}

// ============================================================================
// 8. COOKIES AND SESSION IDENTIFIERS
// ============================================================================

class SessionStore {
    constructor() {
        this.sessions = new Map();
    }

    create(userId) {
        const sessionId = crypto.randomBytes(32).toString("base64url");

        this.sessions.set(sessionId, {
            userId,
            createdAt: Date.now(),
        });

        return sessionId;
    }

    get(sessionId) {
        return this.sessions.get(sessionId);
    }

    delete(sessionId) {
        this.sessions.delete(sessionId);
    }
}

function demonstrateSessions() {
    section("8. Cookies and sessions");

    const sessions = new SessionStore();
    const sessionId = sessions.create(42);

    console.log("Session identifier:", sessionId);
    console.log("Server-side state:", sessions.get(sessionId));

    const setCookie =
        `session_id=${sessionId}; Path=/; HttpOnly; Secure; SameSite=Lax`;

    console.log("Example Set-Cookie:", setCookie);

    console.log(
        "\nThe browser stores the cookie and may send the identifier on later " +
        "requests. The server uses it to locate session state."
    );
}

// ============================================================================
// 9. MIDDLEWARE
// ============================================================================

function loggingMiddleware(handler) {
    return async function wrappedHandler(request) {
        const start = performance.now();

        try {
            return await handler(request);
        } finally {
            const elapsed = performance.now() - start;
            console.log(
                `[middleware] ${request.method} ${request.url} ` +
                `completed in ${elapsed.toFixed(2)} ms`
            );
        }
    };
}

function securityHeadersMiddleware(handler) {
    return async function wrappedHandler(request) {
        const response = await handler(request);

        response.headers = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            ...response.headers,
        };

        return response;
    };
}

async function demonstrateMiddleware() {
    section("9. Middleware");

    let handler = async () => ({
        status: 200,
        headers: {
            "Content-Type": "text/plain",
        },
        body: "Middleware demonstration",
    });

    handler = securityHeadersMiddleware(handler);
    handler = loggingMiddleware(handler);

    const response = await handler({
        method: "GET",
        url: "/middleware",
    });

    console.log(response);
}

// ============================================================================
// 10. CACHE AND ETAG
// ============================================================================

class MemoryCache {
    constructor() {
        this.entries = new Map();
    }

    set(key, value, ttlMilliseconds) {
        this.entries.set(key, {
            value,
            expiresAt: Date.now() + ttlMilliseconds,
        });
    }

    get(key) {
        const entry = this.entries.get(key);

        if (!entry) {
            return null;
        }

        if (Date.now() >= entry.expiresAt) {
            this.entries.delete(key);
            return null;
        }

        return entry.value;
    }
}

function createETag(content) {
    return `"${crypto
        .createHash("sha256")
        .update(content)
        .digest("hex")}"`;
}

function demonstrateCaching() {
    section("10. Caching and validators");

    const cache = new MemoryCache();
    const content = "Version 1 of a document";
    const etag = createETag(content);

    cache.set("/document", content, 1000);

    console.log("Cached value:", cache.get("/document"));
    console.log("Generated ETag:", etag);

    const clientETag = etag;

    if (clientETag === etag) {
        console.log(
            "If-None-Match matches: server can return 304 Not Modified."
        );
    }

    console.log(
        "\nCaching can reduce network traffic and server processing, " +
        "but cached data requires suitable freshness and invalidation rules."
    );
}

// ============================================================================
// 11. ASYNCHRONOUS PROGRAMMING
// ============================================================================

function fakeDatabaseLookup() {
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve({
                id: 42,
                name: "Example User",
            });
        }, 25);
    });
}

async function handleAsyncRequest() {
    const user = await fakeDatabaseLookup();

    return {
        status: 200,
        body: user,
    };
}

async function demonstrateAsyncLifecycle() {
    section("11. Asynchronous request processing");

    console.log("Request received.");
    const response = await handleAsyncRequest();
    console.log("Database-backed result:", response);
    console.log("Response can now be serialized and sent.");
}

// ============================================================================
// 12. CORS
// ============================================================================

function demonstrateCORS() {
    section("12. CORS");

    const corsHeaders = {
        "Access-Control-Allow-Origin": "https://app.example.com",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    };

    console.log(corsHeaders);

    console.log(
        "\nCORS controls which browser-origin contexts may access responses " +
        "under the browser's cross-origin security model. It is not a substitute " +
        "for authentication or authorization."
    );
}

// ============================================================================
// 13. BROWSER FETCH EXAMPLE
// ============================================================================

function demonstrateBrowserFetchConcept() {
    section("13. Browser-side Fetch API");

    console.log(
        "In a browser, a request can be initiated conceptually as:"
    );

    console.log(
        "fetch('/api/products') -> Promise<Response> -> response.json()"
    );

    console.log(
        "\nFetch is asynchronous because the browser cannot block the entire " +
        "page while waiting for network I/O."
    );

    console.log(
        "This Node.js study file does not execute browser DOM APIs because " +
        "DOM and browser rendering belong to the browser environment."
    );
}

// ============================================================================
// 14. REAL LOCAL HTTP SERVER
// ============================================================================

function createLocalServer() {
    const server = http.createServer(async (request, response) => {
        const url = new URL(
            request.url,
            `http://${request.headers.host || "localhost"}`
        );

        response.setHeader("Content-Type", "application/json; charset=utf-8");
        response.setHeader("X-Content-Type-Options", "nosniff");

        if (request.method === "GET" && url.pathname === "/") {
            response.writeHead(200);
            response.end(
                JSON.stringify({
                    message: "Local web server is running",
                    method: request.method,
                    path: url.pathname,
                })
            );
            return;
        }

        if (request.method === "GET" && url.pathname === "/hello") {
            const name = url.searchParams.get("name") || "browser";

            response.writeHead(200);
            response.end(
                JSON.stringify({
                    message: `Hello, ${name}`,
                    query: Object.fromEntries(url.searchParams),
                })
            );
            return;
        }

        if (request.method === "POST" && url.pathname === "/echo") {
            let body = "";
            let tooLarge = false;

            request.on("data", (chunk) => {
                body += chunk;

                if (Buffer.byteLength(body, "utf8") > 1_000_000) {
                    tooLarge = true;
                    request.destroy();
                }
            });

            request.on("end", () => {
                if (tooLarge) {
                    return;
                }

                try {
                    const payload = JSON.parse(body);

                    response.writeHead(200);
                    response.end(
                        JSON.stringify({
                            received: payload,
                        })
                    );
                } catch {
                    response.writeHead(400);
                    response.end(
                        JSON.stringify({
                            error: "Expected valid JSON",
                        })
                    );
                }
            });

            return;
        }

        response.writeHead(404);
        response.end(
            JSON.stringify({
                error: "Resource not found",
                path: url.pathname,
            })
        );
    });

    return server;
}

async function demonstrateRealServer() {
    section("14. Real local HTTP server");

    const server = createLocalServer();

    await new Promise((resolve) => {
        server.listen(0, "127.0.0.1", resolve);
    });

    const address = server.address();

    console.log(
        `Server listening at http://${address.address}:${address.port}`
    );

    try {
        await new Promise((resolve, reject) => {
            const request = http.request(
                {
                    hostname: "127.0.0.1",
                    port: address.port,
                    path: "/hello?name=Atul",
                    method: "GET",
                    headers: {
                        Accept: "application/json",
                    },
                },
                (response) => {
                    let body = "";

                    response.on("data", (chunk) => {
                        body += chunk;
                    });

                    response.on("end", () => {
                        console.log(
                            `GET status: ${response.statusCode} ${response.statusMessage}`
                        );
                        console.log(`GET body: ${body}`);
                        resolve();
                    });
                }
            );

            request.on("error", reject);
            request.end();
        });

        await new Promise((resolve, reject) => {
            const request = http.request(
                {
                    hostname: "127.0.0.1",
                    port: address.port,
                    path: "/echo",
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                },
                (response) => {
                    let body = "";

                    response.on("data", (chunk) => {
                        body += chunk;
                    });

                    response.on("end", () => {
                        console.log(
                            `POST status: ${response.statusCode} ${response.statusMessage}`
                        );
                        console.log(`POST body: ${body}`);
                        resolve();
                    });
                }
            );

            request.on("error", reject);

            request.write(
                JSON.stringify({
                    topic: "web architecture",
                    source: "JavaScript",
                })
            );

            request.end();
        });
    } finally {
        await new Promise((resolve) => server.close(resolve));
    }

    console.log("Server stopped.");
}

// ============================================================================
// 15. REQUEST LIFECYCLE MODEL
// ============================================================================

function demonstrateLifecycle() {
    section("15. End-to-end request lifecycle");

    const stages = [
        "1. User activates a link or enters a URL.",
        "2. Browser parses the URL.",
        "3. Browser determines whether a cached response can be reused.",
        "4. Browser resolves the hostname through DNS when necessary.",
        "5. Browser establishes or reuses a transport connection.",
        "6. HTTPS performs or reuses TLS state.",
        "7. Browser constructs the HTTP request.",
        "8. Request travels through network infrastructure.",
        "9. Web server or reverse proxy accepts the request.",
        "10. Routing selects application logic.",
        "11. Authentication and authorization may run.",
        "12. Application validates input.",
        "13. Application may access databases, caches, or external services.",
        "14. Application constructs an HTTP response.",
        "15. Server sends status, headers, and response body.",
        "16. Browser receives and interprets the response.",
        "17. Browser may request additional CSS, JavaScript, fonts, and images.",
        "18. Browser builds and updates the document and rendering structures.",
        "19. Layout, painting, and compositing produce the visible page.",
    ];

    for (const stage of stages) {
        console.log(stage);
    }
}

// ============================================================================
// 16. CONCURRENCY AND EVENT LOOP
// ============================================================================

async function demonstrateEventLoop() {
    section("16. JavaScript event loop and I/O");

    console.log("Synchronous: start");

    const first = fakeDatabaseLookup();

    Promise.resolve().then(() => {
        console.log("Microtask: Promise callback");
    });

    setTimeout(() => {
        console.log("Timer callback");
    }, 0);

    console.log("Synchronous: end");

    await first;

    console.log(
        "The event loop allows JavaScript to coordinate asynchronous " +
        "operations without requiring the main execution thread to block " +
        "while network or timer operations are pending."
    );
}

// ============================================================================
// 17. SECURITY
// ============================================================================

function demonstrateSecurity() {
    section("17. Security considerations");

    const principles = [
        "Use HTTPS for sensitive communication.",
        "Validate untrusted input on the server.",
        "Authenticate before protected operations.",
        "Authorize every protected resource.",
        "Use parameterized database queries.",
        "Escape or encode output according to its destination.",
        "Protect state-changing operations against CSRF where applicable.",
        "Use secure cookie attributes for sensitive session cookies.",
        "Limit request body sizes and expensive operations.",
        "Avoid exposing internal errors and secrets.",
        "Apply rate limiting to appropriate public endpoints.",
        "Keep dependencies and server software patched.",
    ];

    for (const principle of principles) {
        console.log(`- ${principle}`);
    }
}

// ============================================================================
// 18. PERFORMANCE
// ============================================================================

async function demonstratePerformance() {
    section("18. Performance considerations");

    const start = performance.now();

    await Promise.all([
        fakeDatabaseLookup(),
        fakeDatabaseLookup(),
        fakeDatabaseLookup(),
    ]);

    const parallelTime = performance.now() - start;

    console.log(
        `Three independent simulated operations in parallel: ${parallelTime.toFixed(2)} ms`
    );

    console.log(
        "\nIndependent I/O can often be started concurrently. Sequentially " +
        "waiting for each unrelated operation would increase total latency."
    );

    console.log(
        "\nCommon sources of web latency include DNS, connection establishment, " +
        "TLS, network distance, server computation, database queries, external " +
        "API calls, large payloads, and browser rendering."
    );
}

// ============================================================================
// 19. PRODUCTION ARCHITECTURE
// ============================================================================

function demonstrateProductionArchitecture() {
    section("19. Production architecture");

    const layers = [
        "Browser",
        "DNS",
        "CDN / edge network",
        "Load balancer or reverse proxy",
        "Application servers",
        "Authentication and authorization",
        "Application services",
        "Cache",
        "Database",
        "Message broker and workers",
        "Object storage",
        "Logging, metrics, and tracing",
    ];

    layers.forEach((layer, index) => {
        console.log(`${String(index + 1).padStart(2, "0")}. ${layer}`);
    });

    console.log(
        "\nThe browser still communicates through request-response boundaries " +
        "even when many internal services participate in producing the response."
    );
}

// ============================================================================
// 20. END-TO-END PRODUCT CASE STUDY
// ============================================================================

class ProductService {
    constructor() {
        this.products = new Map([
            [1, { id: 1, name: "Keyboard", price: 2499, stock: 20 }],
            [2, { id: 2, name: "Monitor", price: 15999, stock: 8 }],
            [3, { id: 3, name: "Mouse", price: 999, stock: 50 }],
        ]);
    }

    findProduct(id) {
        return this.products.get(id) || null;
    }

    reserveStock(id, quantity) {
        const product = this.findProduct(id);

        if (!product || !Number.isInteger(quantity) || quantity <= 0) {
            return false;
        }

        if (product.stock < quantity) {
            return false;
        }

        product.stock -= quantity;
        return true;
    }
}

function productEndpoint(productService, requestURL) {
    const url = new URL(requestURL, "http://localhost");
    const match = url.pathname.match(/^\/products\/([^/]+)$/);

    if (!match) {
        return {
            status: 404,
            body: { error: "Invalid product route" },
        };
    }

    const id = Number(match[1]);

    if (!Number.isInteger(id)) {
        return {
            status: 400,
            body: { error: "Product ID must be numeric" },
        };
    }

    const product = productService.findProduct(id);

    if (!product) {
        return {
            status: 404,
            body: { error: "Product not found" },
        };
    }

    return {
        status: 200,
        body: product,
    };
}

function demonstrateCaseStudy() {
    section("20. End-to-end product service case study");

    const service = new ProductService();

    for (const path of [
        "/products/1",
        "/products/999",
        "/products/abc",
    ]) {
        console.log(`Client request: GET ${path}`);
        console.log("Server response:", productEndpoint(service, path));
        console.log();
    }

    console.log("Reserve stock:", service.reserveStock(1, 3));
    console.log("Updated product:", service.findProduct(1));

    console.log(
        "Reserve excessive stock:",
        service.reserveStock(1, 1000)
    );
}

// ============================================================================
// 21. MAIN
// ============================================================================

async function main() {
    explainArchitecture();
    demonstrateURL();
    demonstrateHTTPMessages();
    demonstrateMethodsAndStatusCodes();
    demonstrateRouting();
    demonstrateQueryParameters();
    demonstrateJSONValidation();
    demonstrateSessions();
    await demonstrateMiddleware();
    demonstrateCaching();
    await demonstrateAsyncLifecycle();
    demonstrateCORS();
    demonstrateBrowserFetchConcept();
    await demonstrateRealServer();
    demonstrateLifecycle();
    await demonstrateEventLoop();
    demonstrateSecurity();
    await demonstratePerformance();
    demonstrateProductionArchitecture();
    demonstrateCaseStudy();

    section("Study program completed");

    console.log(
        "The examples covered the browser, HTTP, server routing, application " +
        "processing, state, caching, asynchronous execution, security, " +
        "performance, and production architecture."
    );
}

main().catch((error) => {
    console.error("Fatal error:", error);
    process.exitCode = 1;
});
