/*
 * HTTP: Requests, Responses, Methods, and Status Codes
 * =====================================================
 *
 * Self-contained JavaScript study program using Node.js built-in APIs.
 *
 * Run:
 *     node http_learning.js
 *
 * No external npm packages are required.
 *
 * The program demonstrates HTTP concepts through:
 *   - request and response structures
 *   - HTTP methods
 *   - status codes
 *   - URL and query-string handling
 *   - JSON payloads
 *   - a real local HTTP server
 *   - a practical HTTP client
 *   - validation and error handling
 *   - retries and idempotency
 *   - caching concepts
 *   - security considerations
 *   - performance considerations
 */

"use strict";

const http = require("node:http");
const { URL } = require("node:url");
const crypto = require("node:crypto");


// ============================================================================
// 1. HTTP FUNDAMENTALS
// ============================================================================

function explainHttpBasics() {
    console.log("\n" + "=".repeat(78));
    console.log("1. HTTP FUNDAMENTALS");
    console.log("=".repeat(78));

    console.log(`
HTTP is an application-layer protocol used for communication between clients
and servers.

A client sends a request:

    method + target + headers + optional body

A server sends a response:

    status code + headers + optional body

For example:

    GET /api/users/42 HTTP/1.1
    Host: example.com
    Accept: application/json

The server may respond:

    HTTP/1.1 200 OK
    Content-Type: application/json

    {"id":42,"name":"Ada"}

HTTP semantics are independent of JavaScript. A browser, Python application,
mobile application, or C++ program can use the same HTTP protocol.
`);
}


// ============================================================================
// 2. METHODS
// ============================================================================

const HTTP_METHODS = {
    GET: "Retrieve a representation.",
    POST: "Submit data or request processing.",
    PUT: "Create or replace a representation at a known target.",
    PATCH: "Partially modify a resource.",
    DELETE: "Delete a resource.",
    HEAD: "Retrieve response metadata without the normal response body.",
    OPTIONS: "Discover communication options.",
    TRACE: "Diagnostic loop-back method; commonly disabled.",
    CONNECT: "Create a tunnel, commonly through a proxy."
};

function demonstrateMethods() {
    console.log("\n" + "=".repeat(78));
    console.log("2. HTTP METHODS");
    console.log("=".repeat(78));

    for (const [method, description] of Object.entries(HTTP_METHODS)) {
        console.log(`${method.padEnd(8)} ${description}`);
    }

    console.log(`
Safe methods are intended to have read-only semantics.

GET, HEAD, PUT, DELETE, OPTIONS, and TRACE are defined as idempotent where
repeating the same request has the same intended effect on server state.

POST is not inherently idempotent. Repeating a POST can create duplicate
resources or repeat an operation.

PATCH can be idempotent or non-idempotent depending on the operation.

A useful resource-oriented API might expose:

    GET    /users/42
    POST   /users
    PUT    /users/42
    PATCH  /users/42
    DELETE /users/42
`);
}


// ============================================================================
// 3. STATUS CODES
// ============================================================================

const STATUS_CODES = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    206: "Partial Content",
    301: "Moved Permanently",
    302: "Found",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    412: "Precondition Failed",
    413: "Content Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout"
};

function classifyStatus(code) {
    if (code >= 100 && code <= 199) return "1xx Informational";
    if (code >= 200 && code <= 299) return "2xx Successful";
    if (code >= 300 && code <= 399) return "3xx Redirection";
    if (code >= 400 && code <= 499) return "4xx Client Error";
    if (code >= 500 && code <= 599) return "5xx Server Error";
    return "Unknown";
}

function demonstrateStatusCodes() {
    console.log("\n" + "=".repeat(78));
    console.log("3. STATUS CODES");
    console.log("=".repeat(78));

    for (const [code, phrase] of Object.entries(STATUS_CODES)) {
        console.log(
            `${code}: ${phrase.padEnd(25)} -> ${classifyStatus(Number(code))}`
        );
    }

    console.log(`
Status classes:

1xx  Informational
2xx  Successful
3xx  Redirection
4xx  Client error
5xx  Server error

401 generally concerns authentication. 403 commonly indicates that the
server understood the request but refuses authorization.

404 means the requested resource was not found.

405 means the method is not allowed for the target.

409 commonly represents a conflict with current resource state.

422 is frequently used for validly structured requests whose content fails
application-level validation.

429 commonly represents rate limiting.

500 represents a server-side failure.

502 and 504 are commonly associated with gateways or reverse proxies and
upstream failures.
`);
}


// ============================================================================
// 4. URL AND QUERY PARAMETERS
// ============================================================================

function demonstrateUrls() {
    console.log("\n" + "=".repeat(78));
    console.log("4. URLS AND QUERY PARAMETERS");
    console.log("=".repeat(78));

    const url = new URL(
        "https://example.com:8443/products/42?category=books&sort=price&page=2#details"
    );

    console.log(`Protocol:  ${url.protocol}`);
    console.log(`Hostname:  ${url.hostname}`);
    console.log(`Port:      ${url.port}`);
    console.log(`Path:      ${url.pathname}`);
    console.log(`Query:     ${url.search}`);
    console.log(`Fragment:  ${url.hash}`);

    console.log("\nQuery parameters:");

    for (const [key, value] of url.searchParams.entries()) {
        console.log(`  ${key} = ${value}`);
    }

    const generated = new URL("https://example.com/search");
    generated.searchParams.set("query", "machine learning");
    generated.searchParams.set("page", "2");

    console.log(`\nGenerated URL: ${generated}`);

    console.log(`
Path parameters identify a resource:

    /users/42

Query parameters generally modify a retrieval operation:

    /users?role=admin&page=2

A URL fragment such as #details is generally processed by the user agent and
is not sent as part of the HTTP request target to the server.
`);
}


// ============================================================================
// 5. REQUEST AND RESPONSE OBJECTS
// ============================================================================

class HttpRequest {
    constructor(method, target, headers = {}, body = "") {
        this.method = method;
        this.target = target;
        this.headers = headers;
        this.body = body;
    }

    getHeader(name) {
        const wanted = name.toLowerCase();

        const entry = Object.entries(this.headers)
            .find(([key]) => key.toLowerCase() === wanted);

        return entry ? entry[1] : undefined;
    }
}

class HttpResponse {
    constructor(statusCode, headers = {}, body = "") {
        this.statusCode = statusCode;
        this.headers = headers;
        this.body = body;
    }
}

function demonstrateMessageObjects() {
    console.log("\n" + "=".repeat(78));
    console.log("5. HTTP MESSAGE OBJECTS");
    console.log("=".repeat(78));

    const request = new HttpRequest(
        "POST",
        "/api/users",
        {
            Host: "localhost:3000",
            "Content-Type": "application/json",
            Accept: "application/json"
        },
        JSON.stringify({
            name: "Ada",
            email: "ada@example.com"
        })
    );

    const response = new HttpResponse(
        201,
        {
            "Content-Type": "application/json",
            Location: "/api/users/101"
        },
        JSON.stringify({
            id: 101,
            name: "Ada"
        })
    );

    console.log("Request:", request);
    console.log("Accept:", request.getHeader("accept"));
    console.log("Response:", response);
}


// ============================================================================
// 6. JSON VALIDATION
// ============================================================================

function parseJsonBody(body) {
    try {
        return {
            success: true,
            value: JSON.parse(body)
        };
    } catch (error) {
        return {
            success: false,
            error: "Invalid JSON"
        };
    }
}

function validateUserPayload(payload) {
    const errors = [];

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        errors.push("Body must be a JSON object.");
        return errors;
    }

    if (
        typeof payload.name !== "string" ||
        payload.name.trim().length === 0
    ) {
        errors.push("name must be a non-empty string.");
    }

    if (
        typeof payload.email !== "string" ||
        !payload.email.includes("@")
    ) {
        errors.push("email must contain @.");
    }

    return errors;
}

function demonstrateValidation() {
    console.log("\n" + "=".repeat(78));
    console.log("6. JSON AND VALIDATION");
    console.log("=".repeat(78));

    const examples = [
        '{"name":"Ada","email":"ada@example.com"}',
        '{"name":"","email":"bad"}',
        "{not valid json}"
    ];

    for (const body of examples) {
        const parsed = parseJsonBody(body);

        if (!parsed.success) {
            console.log(`Body: ${body}`);
            console.log("Error:", parsed.error);
            continue;
        }

        console.log(`Body: ${body}`);
        console.log("Validation:", validateUserPayload(parsed.value));
    }

    console.log(`
Content-Type tells the receiver how the representation should be interpreted.

For JSON APIs:

    Content-Type: application/json

Accept tells the server which response representation the client prefers:

    Accept: application/json

These headers serve different purposes.
`);
}


// ============================================================================
// 7. LOCAL HTTP SERVER
// ============================================================================

const users = new Map([
    [1, { id: 1, name: "Ada", email: "ada@example.com" }],
    [2, { id: 2, name: "Alan", email: "alan@example.com" }],
    [3, { id: 3, name: "Grace", email: "grace@example.com" }]
]);

function sendJson(response, statusCode, payload, extraHeaders = {}) {
    const body = JSON.stringify(payload, null, 2);

    response.writeHead(statusCode, {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": Buffer.byteLength(body),
        ...extraHeaders
    });

    response.end(body);
}

function readRequestBody(request, maximumBytes = 1_000_000) {
    return new Promise((resolve, reject) => {
        const chunks = [];
        let totalBytes = 0;

        request.on("data", chunk => {
            totalBytes += chunk.length;

            if (totalBytes > maximumBytes) {
                reject(new Error("Request body too large."));
                request.destroy();
                return;
            }

            chunks.push(chunk);
        });

        request.on("end", () => {
            resolve(Buffer.concat(chunks).toString("utf8"));
        });

        request.on("error", reject);
    });
}

function createLearningServer() {
    return http.createServer(async (request, response) => {
        const url = new URL(
            request.url,
            `http://${request.headers.host || "localhost"}`
        );

        const method = request.method;
        const path = url.pathname;

        try {
            if (method === "GET" && path === "/") {
                sendJson(response, 200, {
                    message: "HTTP learning server",
                    method,
                    path
                });
                return;
            }

            if (method === "GET" && path === "/api/users") {
                const requestedName = url.searchParams.get("name");

                let result = [...users.values()];

                if (requestedName) {
                    result = result.filter(
                        user =>
                            user.name.toLowerCase() ===
                            requestedName.toLowerCase()
                    );
                }

                sendJson(response, 200, { users: result });
                return;
            }

            if (path.startsWith("/api/users/")) {
                const idText = path.split("/").pop();
                const id = Number(idText);

                if (!Number.isInteger(id) || id <= 0) {
                    sendJson(response, 400, {
                        error: "Invalid user ID"
                    });
                    return;
                }

                if (method === "GET") {
                    const user = users.get(id);

                    if (!user) {
                        sendJson(response, 404, {
                            error: "User not found"
                        });
                        return;
                    }

                    sendJson(response, 200, user);
                    return;
                }

                if (method === "PUT") {
                    const body = await readRequestBody();
                    const parsed = parseJsonBody(body);

                    if (!parsed.success) {
                        sendJson(response, 400, {
                            error: parsed.error
                        });
                        return;
                    }

                    const errors = validateUserPayload(parsed.value);

                    if (errors.length > 0) {
                        sendJson(response, 422, { errors });
                        return;
                    }

                    const updatedUser = {
                        id,
                        name: parsed.value.name.trim(),
                        email: parsed.value.email.trim()
                    };

                    users.set(id, updatedUser);
                    sendJson(response, 200, updatedUser);
                    return;
                }

                if (method === "PATCH") {
                    const body = await readRequestBody();
                    const parsed = parseJsonBody(body);

                    if (!parsed.success) {
                        sendJson(response, 400, {
                            error: parsed.error
                        });
                        return;
                    }

                    const existing = users.get(id);

                    if (!existing) {
                        sendJson(response, 404, {
                            error: "User not found"
                        });
                        return;
                    }

                    const allowedFields = ["name", "email"];
                    const invalidField = Object.keys(parsed.value)
                        .find(key => !allowedFields.includes(key));

                    if (invalidField) {
                        sendJson(response, 422, {
                            error: `Unsupported field: ${invalidField}`
                        });
                        return;
                    }

                    const updated = {
                        ...existing,
                        ...parsed.value
                    };

                    users.set(id, updated);
                    sendJson(response, 200, updated);
                    return;
                }

                if (method === "DELETE") {
                    const existed = users.delete(id);

                    if (!existed) {
                        sendJson(response, 404, {
                            error: "User not found"
                        });
                        return;
                    }

                    response.writeHead(204);
                    response.end();
                    return;
                }
            }

            if (method === "POST" && path === "/api/users") {
                if (request.headers["content-type"]?.split(";")[0] !==
                    "application/json") {
                    sendJson(response, 415, {
                        error: "Expected application/json"
                    });
                    return;
                }

                const body = await readRequestBody();
                const parsed = parseJsonBody(body);

                if (!parsed.success) {
                    sendJson(response, 400, {
                        error: parsed.error
                    });
                    return;
                }

                const errors = validateUserPayload(parsed.value);

                if (errors.length > 0) {
                    sendJson(response, 422, { errors });
                    return;
                }

                const id = Math.max(...users.keys()) + 1;

                const user = {
                    id,
                    name: parsed.value.name.trim(),
                    email: parsed.value.email.trim()
                };

                users.set(id, user);

                sendJson(
                    response,
                    201,
                    user,
                    { Location: `/api/users/${id}` }
                );

                return;
            }

            if (method === "HEAD" && path === "/") {
                response.writeHead(200, {
                    "Content-Type": "application/json",
                    "Content-Length": "0"
                });
                response.end();
                return;
            }

            if (method === "OPTIONS") {
                response.writeHead(204, {
                    Allow: "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS"
                });
                response.end();
                return;
            }

            sendJson(response, 404, {
                error: "Route not found"
            });
        } catch (error) {
            console.error("Server error:", error);

            if (!response.headersSent) {
                sendJson(response, 500, {
                    error: "Internal server error"
                });
            } else {
                response.end();
            }
        }
    });
}


// ============================================================================
// 8. HTTP CLIENT
// ============================================================================

function httpRequest(urlString, options = {}, body = null) {
    return new Promise((resolve, reject) => {
        const url = new URL(urlString);

        const requestOptions = {
            protocol: url.protocol,
            hostname: url.hostname,
            port: url.port,
            path: `${url.pathname}${url.search}`,
            method: options.method || "GET",
            headers: {
                Accept: "application/json",
                "User-Agent": "Node-HTTP-Learning-Client/1.0",
                ...(options.headers || {})
            },
            timeout: options.timeout || 3000
        };

        const request = http.request(requestOptions, response => {
            const chunks = [];

            response.on("data", chunk => chunks.push(chunk));

            response.on("end", () => {
                const rawBody = Buffer.concat(chunks).toString("utf8");

                let parsedBody = rawBody;

                if (
                    response.headers["content-type"]?.includes(
                        "application/json"
                    ) &&
                    rawBody.length > 0
                ) {
                    try {
                        parsedBody = JSON.parse(rawBody);
                    } catch {
                        parsedBody = rawBody;
                    }
                }

                resolve({
                    statusCode: response.statusCode,
                    headers: response.headers,
                    body: parsedBody
                });
            });
        });

        request.on("timeout", () => {
            request.destroy(new Error("HTTP request timed out."));
        });

        request.on("error", reject);

        if (body !== null) {
            request.write(body);
        }

        request.end();
    });
}

async function demonstrateRealHttpRequests() {
    console.log("\n" + "=".repeat(78));
    console.log("8. REAL LOCAL HTTP REQUESTS");
    console.log("=".repeat(78));

    const server = createLearningServer();

    await new Promise(resolve => {
        server.listen(0, "127.0.0.1", resolve);
    });

    const port = server.address().port;
    const baseUrl = `http://127.0.0.1:${port}`;

    console.log(`Local server: ${baseUrl}`);

    try {
        let result = await httpRequest(`${baseUrl}/api/users`);

        console.log("\nGET /api/users");
        console.log(result);

        result = await httpRequest(
            `${baseUrl}/api/users`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                }
            },
            JSON.stringify({
                name: "Katherine",
                email: "katherine@example.com"
            })
        );

        console.log("\nPOST /api/users");
        console.log(result);

        result = await httpRequest(
            `${baseUrl}/api/users/1`,
            {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json"
                }
            },
            JSON.stringify({
                name: "Ada Updated"
            })
        );

        console.log("\nPATCH /api/users/1");
        console.log(result);

        result = await httpRequest(
            `${baseUrl}/api/users/999999`
        );

        console.log("\nGET missing resource");
        console.log(result);
    } finally {
        await new Promise(resolve => server.close(resolve));
        console.log("\nLocal server stopped.");
    }
}


// ============================================================================
// 9. RETRIES AND IDEMPOTENCY
// ============================================================================

function isRetryableStatus(statusCode) {
    return [408, 429, 500, 502, 503, 504].includes(statusCode);
}

function isIdempotentMethod(method) {
    return ["GET", "HEAD", "PUT", "DELETE", "OPTIONS"].includes(
        method.toUpperCase()
    );
}

function shouldRetry(method, statusCode, attempt, maxAttempts) {
    if (attempt >= maxAttempts) return false;

    if (!isRetryableStatus(statusCode)) return false;

    /*
     * POST is excluded here because blindly retrying it may create duplicate
     * resources. A real API can make selected POST operations retryable with
     * an idempotency key.
     */
    return isIdempotentMethod(method);
}

function calculateBackoff(attempt, baseDelay = 200, maximum = 5000) {
    const exponential = Math.min(
        maximum,
        baseDelay * (2 ** (attempt - 1))
    );

    // Jitter reduces synchronized retry bursts when many clients fail at once.
    return Math.floor(exponential * (0.5 + Math.random()));
}

function demonstrateRetries() {
    console.log("\n" + "=".repeat(78));
    console.log("9. RETRIES AND IDEMPOTENCY");
    console.log("=".repeat(78));

    const scenarios = [
        ["GET", 503],
        ["POST", 503],
        ["PUT", 503],
        ["GET", 404],
        ["DELETE", 429]
    ];

    for (const [method, status] of scenarios) {
        console.log(
            `${method} ${status} -> retry=${shouldRetry(
                method,
                status,
                1,
                3
            )}`
        );
    }

    console.log(
        `Example backoff for attempt 3: ${calculateBackoff(3)} ms`
    );

    console.log(`
A robust retry policy considers method semantics, status codes, timeouts,
attempt count, exponential backoff, jitter, Retry-After, and idempotency.

Retrying a failed POST without application-level protection can duplicate
side effects.
`);
}


// ============================================================================
// 10. CACHING AND ETAG
// ============================================================================

function demonstrateCaching() {
    console.log("\n" + "=".repeat(78));
    console.log("10. CACHING AND CONDITIONAL REQUESTS");
    console.log("=".repeat(78));

    const representation = JSON.stringify({
        id: 42,
        name: "Ada"
    });

    const etag = `"${crypto
        .createHash("sha256")
        .update(representation)
        .digest("hex")
        .slice(0, 16)}"`;

    console.log("Representation:", representation);
    console.log("Generated ETag:", etag);

    console.log(`
A response might contain:

    Cache-Control: public, max-age=60
    ETag: ${etag}

A later request may contain:

    If-None-Match: ${etag}

If the representation has not changed, the server can return 304 Not Modified
without retransmitting the complete body.

Caching can improve latency and reduce bandwidth and server load, but private
or security-sensitive content requires careful cache policy.
`);
}


// ============================================================================
// 11. SECURITY
// ============================================================================

function demonstrateSecurity() {
    console.log("\n" + "=".repeat(78));
    console.log("11. HTTP SECURITY");
    console.log("=".repeat(78));

    console.log(`
HTTPS means HTTP semantics are transported through TLS.

Security-relevant HTTP/application concerns include:

    - unencrypted HTTP
    - authentication failures
    - authorization failures
    - insecure CORS policies
    - CSRF
    - XSS in HTML responses
    - request smuggling
    - header injection
    - cache poisoning
    - oversized request bodies
    - rate-limit abuse
    - sensitive data in URLs
    - overly detailed error responses

Do not put access tokens or passwords into query strings when an appropriate
header or request body can be used.

Validate untrusted input and impose reasonable request size limits.

Authentication identifies a caller. Authorization determines what that caller
is allowed to do. HTTP status codes communicate the result but do not replace
the application's authorization checks.
`);
}


// ============================================================================
// 12. PERFORMANCE
// ============================================================================

function demonstratePerformance() {
    console.log("\n" + "=".repeat(78));
    console.log("12. PERFORMANCE");
    console.log("=".repeat(78));

    const stages = {
        dnsLookupMs: 5,
        connectionAndTlsMs: 30,
        serverProcessingMs: 20,
        responseTransferMs: 15
    };

    const total = Object.values(stages)
        .reduce((sum, value) => sum + value, 0);

    console.table(stages);
    console.log(`Approximate total: ${total} ms`);

    console.log(`
Important performance mechanisms include:

    - persistent connections
    - connection pooling
    - HTTP/2 multiplexing
    - HTTP/3 over QUIC
    - compression
    - caching
    - pagination
    - efficient serialization
    - appropriate timeouts
    - reducing unnecessary payload data

A production HTTP client should avoid both unlimited waiting and excessively
aggressive timeouts.
`);
}


// ============================================================================
// 13. HTTP VERSIONS
// ============================================================================

function demonstrateHttpVersions() {
    console.log("\n" + "=".repeat(78));
    console.log("13. HTTP VERSIONS");
    console.log("=".repeat(78));

    const versions = {
        "HTTP/1.0":
            "Early HTTP with simpler connection behavior.",
        "HTTP/1.1":
            "Persistent connections and standardized request/response behavior.",
        "HTTP/2":
            "Binary framing and multiplexed streams.",
        "HTTP/3":
            "HTTP semantics transported using QUIC."
    };

    console.table(versions);

    console.log(`
HTTP versions change transport and framing mechanisms while retaining core
HTTP concepts such as methods, status codes, headers, URLs, and
representations.
`);
}


// ============================================================================
// 14. ASYNCHRONOUS FETCH-STYLE CLIENT
// ============================================================================

async function demonstrateFetchStyleClient(baseUrl) {
    console.log("\n" + "=".repeat(78));
    console.log("14. ASYNCHRONOUS HTTP CLIENT");
    console.log("=".repeat(78));

    /*
     * Modern Node.js versions provide global fetch(). The API is based on the
     * browser Fetch API and returns a Promise because network operations are
     * asynchronous.
     */

    const response = await fetch(`${baseUrl}/api/users`);

    console.log("Status:", response.status);
    console.log("Content-Type:", response.headers.get("content-type"));

    const data = await response.json();

    console.log("JSON:", data);

    /*
     * fetch() does not reject merely because the server returned 404 or 500.
     * Application code must inspect response.ok/status explicitly.
     */
    const missing = await fetch(`${baseUrl}/api/users/999999`);

    console.log("Missing resource status:", missing.status);
    console.log("missing.ok:", missing.ok);
}


// ============================================================================
// 15. TESTS
// ============================================================================

function runTests() {
    console.log("\n" + "=".repeat(78));
    console.log("15. BASIC TESTS");
    console.log("=".repeat(78));

    console.assert(
        classifyStatus(200) === "2xx Successful",
        "200 classification failed"
    );

    console.assert(
        classifyStatus(404) === "4xx Client Error",
        "404 classification failed"
    );

    console.assert(
        classifyStatus(503) === "5xx Server Error",
        "503 classification failed"
    );

    console.assert(
        isIdempotentMethod("GET"),
        "GET should be idempotent"
    );

    console.assert(
        !isIdempotentMethod("POST"),
        "POST should not be treated as idempotent"
    );

    console.assert(
        shouldRetry("GET", 503, 1, 3),
        "GET 503 should be retryable"
    );

    console.assert(
        !shouldRetry("POST", 503, 1, 3),
        "POST 503 should not be blindly retried"
    );

    console.assert(
        validateUserPayload({
            name: "Ada",
            email: "ada@example.com"
        }).length === 0,
        "Valid payload failed"
    );

    console.log("All assertions completed.");
}


// ============================================================================
// 16. MAIN
// ============================================================================

async function main() {
    console.log("=".repeat(78));
    console.log("HTTP LEARNING LAB");
    console.log("Requests, Responses, Methods, and Status Codes");
    console.log("=".repeat(78));

    explainHttpBasics();
    demonstrateMethods();
    demonstrateStatusCodes();
    demonstrateUrls();
    demonstrateMessageObjects();
    demonstrateValidation();
    await demonstrateRealHttpRequests();
    demonstrateRetries();
    demonstrateCaching();
    demonstrateSecurity();
    demonstratePerformance();
    demonstrateHttpVersions();

    const server = createLearningServer();

    await new Promise(resolve => {
        server.listen(0, "127.0.0.1", resolve);
    });

    try {
        const port = server.address().port;
        await demonstrateFetchStyleClient(
            `http://127.0.0.1:${port}`
        );
    } finally {
        await new Promise(resolve => server.close(resolve));
    }

    runTests();

    console.log("\n" + "=".repeat(78));
    console.log("HTTP learning program completed.");
    console.log("=".repeat(78));
}

main().catch(error => {
    console.error("Fatal error:", error);
    process.exitCode = 1;
});
