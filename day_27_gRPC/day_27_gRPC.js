/*
 * gRPC, RPC, Protocol Buffers, and Service-to-Service Communication
 * ==================================================================
 *
 * This self-contained JavaScript study file demonstrates the application-level
 * ideas behind gRPC without requiring an external npm package or a running
 * gRPC server.
 *
 * The examples progress from:
 *   - RPC fundamentals
 *   - message contracts
 *   - serialization concepts
 *   - unary and streaming RPC shapes
 *   - deadlines
 *   - metadata
 *   - authentication/authorization
 *   - retries and idempotency
 *   - service discovery
 *   - load balancing
 *   - observability
 *   - resilience
 *   - an integrated microservice case study
 *
 * A production gRPC JavaScript implementation would normally use a gRPC
 * runtime and generated code based on .proto service definitions.
 */

"use strict";

console.log("=".repeat(78));
console.log("gRPC / RPC / PROTOCOL BUFFERS / SERVICE-TO-SERVICE COMMUNICATION");
console.log("=".repeat(78));


// ============================================================================
// 1. LOCAL PROCEDURE CALL VERSUS RPC
// ============================================================================

function addNumbers(first, second) {
    return first + second;
}

console.log("\n[1] Local procedure call");
console.log("addNumbers(10, 20) =", addNumbers(10, 20));

/*
 * Local procedure:
 *     application -> function
 *
 * Remote procedure:
 *     application
 *        |
 *        v
 *     generated client stub
 *        |
 *        v
 *     serialization
 *        |
 *        v
 *     network
 *        |
 *        v
 *     server
 *        |
 *        v
 *     service implementation
 *
 * gRPC commonly uses HTTP/2 transport and Protocol Buffers for the
 * service contract and message representation.
 */


// ============================================================================
// 2. PROTOCOL-BUFFER-STYLE MESSAGE MODEL
// ============================================================================

class User {
    constructor(id = 0, name = "", email = "") {
        this.id = id;
        this.name = name;
        this.email = email;
    }
}

/*
 * Conceptual .proto schema:
 *
 * message User {
 *     int32 id = 1;
 *     string name = 2;
 *     string email = 3;
 * }
 *
 * The numbers 1, 2, and 3 are field tags.
 * They are part of the serialized schema contract.
 */

const user = new User(
    101,
    "Atul",
    "atul@example.com"
);

console.log("\n[2] Message contract");
console.log(user);


// ============================================================================
// 3. SIMPLIFIED PROTOBUF VARINT
// ============================================================================

function encodeVarint(value) {
    if (!Number.isSafeInteger(value) || value < 0) {
        throw new Error(
            "This educational encoder accepts non-negative safe integers."
        );
    }

    const bytes = [];

    while (true) {
        let current = value % 128;
        value = Math.floor(value / 128);

        if (value !== 0) {
            current |= 0x80;
        }

        bytes.push(current);

        if (value === 0) {
            return Uint8Array.from(bytes);
        }
    }
}

function concatBytes(...arrays) {
    const totalLength = arrays.reduce(
        (total, array) => total + array.length,
        0
    );

    const output = new Uint8Array(totalLength);
    let offset = 0;

    for (const array of arrays) {
        output.set(array, offset);
        offset += array.length;
    }

    return output;
}

function encodeStringField(fieldNumber, value) {
    const encoder = new TextEncoder();
    const encodedValue = encoder.encode(value);

    // Wire type 2 means length-delimited.
    const key = (fieldNumber << 3) | 2;

    return concatBytes(
        encodeVarint(key),
        encodeVarint(encodedValue.length),
        encodedValue
    );
}

function encodeInt32Field(fieldNumber, value) {
    if (!Number.isInteger(value) || value < 0) {
        throw new Error(
            "This simplified int32 demonstration expects a non-negative integer."
        );
    }

    const key = fieldNumber << 3;
    return concatBytes(
        encodeVarint(key),
        encodeVarint(value)
    );
}

function encodeUser(userObject) {
    const fields = [];

    if (userObject.id !== 0) {
        fields.push(encodeInt32Field(1, userObject.id));
    }

    if (userObject.name !== "") {
        fields.push(encodeStringField(2, userObject.name));
    }

    if (userObject.email !== "") {
        fields.push(encodeStringField(3, userObject.email));
    }

    return concatBytes(...fields);
}

const encodedUser = encodeUser(user);

console.log("\n[3] Simplified protobuf-style encoding");
console.log(
    "Encoded hexadecimal:",
    Array.from(encodedUser)
        .map(byte => byte.toString(16).padStart(2, "0"))
        .join("")
);


// ============================================================================
// 4. RPC STATUS MODEL
// ============================================================================

const RpcStatus = Object.freeze({
    OK: "OK",
    INVALID_ARGUMENT: "INVALID_ARGUMENT",
    NOT_FOUND: "NOT_FOUND",
    DEADLINE_EXCEEDED: "DEADLINE_EXCEEDED",
    UNAVAILABLE: "UNAVAILABLE",
    INTERNAL: "INTERNAL",
    UNAUTHENTICATED: "UNAUTHENTICATED",
    PERMISSION_DENIED: "PERMISSION_DENIED"
});

class RpcError extends Error {
    constructor(code, message) {
        super(message);
        this.name = "RpcError";
        this.code = code;
    }
}


// ============================================================================
// 5. SERVER-SIDE USER SERVICE
// ============================================================================

class UserService {
    constructor() {
        this.users = new Map([
            [1, new User(1, "Ada", "ada@example.com")],
            [2, new User(2, "Grace", "grace@example.com")],
            [3, new User(3, "Alan", "alan@example.com")]
        ]);
    }

    getUser(request) {
        if (!Number.isInteger(request.userId) || request.userId <= 0) {
            throw new RpcError(
                RpcStatus.INVALID_ARGUMENT,
                "userId must be a positive integer."
            );
        }

        const foundUser = this.users.get(request.userId);

        if (!foundUser) {
            throw new RpcError(
                RpcStatus.NOT_FOUND,
                `User ${request.userId} does not exist.`
            );
        }

        return {
            user: foundUser,
            found: true,
            message: "User retrieved successfully."
        };
    }
}

const userService = new UserService();

console.log("\n[4] Server-side service");
console.log(userService.getUser({ userId: 1 }));


// ============================================================================
// 6. CLIENT STUB
// ============================================================================

class UserServiceClient {
    constructor(service) {
        this.service = service;
    }

    getUser(userId) {
        /*
         * A real generated gRPC stub would serialize this request and send it
         * over the network. This example directly invokes the service so the
         * focus remains on the RPC abstraction.
         */
        return this.service.getUser({ userId });
    }
}

const userClient = new UserServiceClient(userService);

console.log("\n[5] Client stub");
console.log(userClient.getUser(2));

try {
    userClient.getUser(999);
} catch (error) {
    console.log(
        "RPC failure:",
        error.code,
        "-",
        error.message
    );
}


// ============================================================================
// 7. METADATA
// ============================================================================

class RpcMetadata {
    constructor(initialValues = {}) {
        this.values = new Map();

        for (const [key, value] of Object.entries(initialValues)) {
            this.set(key, value);
        }
    }

    set(key, value) {
        this.values.set(key.toLowerCase(), String(value));
    }

    get(key) {
        return this.values.get(key.toLowerCase());
    }

    toObject() {
        return Object.fromEntries(this.values);
    }
}

const metadata = new RpcMetadata({
    "x-request-id": crypto.randomUUID(),
    "x-client": "study-client"
});

console.log("\n[6] Metadata");
console.log(metadata.toObject());


// ============================================================================
// 8. INTERCEPTOR
// ============================================================================

async function loggingInterceptor(
    methodName,
    rpcMetadata,
    handler
) {
    const started = performance.now();

    console.log(`  -> ${methodName}`);

    try {
        const result = await handler();

        console.log(
            `  <- ${methodName}: OK ` +
            `(${(performance.now() - started).toFixed(2)} ms)`
        );

        return result;
    } catch (error) {
        console.log(
            `  <- ${methodName}: ${error.code ?? "ERROR"} ` +
            `(${(performance.now() - started).toFixed(2)} ms)`
        );

        throw error;
    }
}

async function demonstrateInterceptor() {
    const result = await loggingInterceptor(
        "UserService/GetUser",
        metadata,
        () => userClient.getUser(1)
    );

    console.log("Interceptor result:", result);
}

await demonstrateInterceptor();


// ============================================================================
// 9. DEADLINES
// ============================================================================

function sleep(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function withDeadline(operation, timeoutMilliseconds) {
    if (timeoutMilliseconds <= 0) {
        throw new RpcError(
            RpcStatus.DEADLINE_EXCEEDED,
            "Deadline has already expired."
        );
    }

    let timer;

    const timeoutPromise = new Promise((_, reject) => {
        timer = setTimeout(() => {
            reject(
                new RpcError(
                    RpcStatus.DEADLINE_EXCEEDED,
                    "Operation exceeded the deadline."
                )
            );
        }, timeoutMilliseconds);
    });

    try {
        return await Promise.race([
            operation(),
            timeoutPromise
        ]);
    } finally {
        clearTimeout(timer);
    }
}

console.log("\n[7] Deadline");

try {
    const result = await withDeadline(
        async () => {
            await sleep(10);
            return "completed before deadline";
        },
        100
    );

    console.log(result);
} catch (error) {
    console.log(error.code, error.message);
}


// ============================================================================
// 10. AUTHENTICATION AND AUTHORIZATION
// ============================================================================

class Identity {
    constructor(subject, roles = []) {
        this.subject = subject;
        this.roles = new Set(roles);
    }
}

function requireRole(identity, requiredRole) {
    if (!identity.roles.has(requiredRole)) {
        throw new RpcError(
            RpcStatus.PERMISSION_DENIED,
            `Required role '${requiredRole}' is missing.`
        );
    }
}

const admin = new Identity(
    "service-admin",
    ["reader", "writer", "admin"]
);

const reader = new Identity(
    "service-reader",
    ["reader"]
);

requireRole(admin, "reader");
console.log("\n[8] Admin authorization succeeded.");

try {
    requireRole(reader, "admin");
} catch (error) {
    console.log(
        "Authorization failure:",
        error.code,
        error.message
    );
}


// ============================================================================
// 11. UNARY RPC
// ============================================================================

function unaryRpc(request) {
    return request * 2;
}

console.log("\n[9] Unary RPC");
console.log("5 ->", unaryRpc(5));


// ============================================================================
// 12. SERVER STREAMING
// ============================================================================

async function* serverStreamingRpc(limit) {
    if (!Number.isInteger(limit) || limit < 0) {
        throw new RpcError(
            RpcStatus.INVALID_ARGUMENT,
            "limit must be a non-negative integer."
        );
    }

    for (let number = 1; number <= limit; number++) {
        await sleep(2);
        yield number * number;
    }
}

console.log("\n[10] Server streaming");

const streamedValues = [];

for await (const value of serverStreamingRpc(5)) {
    streamedValues.push(value);
}

console.log(streamedValues);


// ============================================================================
// 13. CLIENT STREAMING
// ============================================================================

async function clientStreamingRpc(asyncValues) {
    let total = 0;

    for await (const value of asyncValues) {
        if (!Number.isFinite(value)) {
            throw new RpcError(
                RpcStatus.INVALID_ARGUMENT,
                "Stream contained a non-numeric value."
            );
        }

        total += value;
    }

    return total;
}

async function* numberProducer() {
    yield 1;
    yield 2;
    yield 3;
    yield 4;
}

console.log(
    "\n[11] Client streaming:",
    await clientStreamingRpc(numberProducer())
);


// ============================================================================
// 14. BIDIRECTIONAL STREAMING
// ============================================================================

async function* bidirectionalStreamingRpc(asyncValues) {
    for await (const value of asyncValues) {
        if (!Number.isFinite(value)) {
            throw new RpcError(
                RpcStatus.INVALID_ARGUMENT,
                "Stream value must be numeric."
            );
        }

        yield value * 10;
    }
}

console.log("\n[12] Bidirectional streaming");

async function* inputProducer() {
    yield 2;
    yield 4;
    yield 6;
}

const bidirectionalResults = [];

for await (
    const value of bidirectionalStreamingRpc(inputProducer())
) {
    bidirectionalResults.push(value);
}

console.log(bidirectionalResults);


// ============================================================================
// 15. RETRIES AND EXPONENTIAL BACKOFF
// ============================================================================

class TemporaryFailure extends Error {}

async function retryWithExponentialBackoff(
    operation,
    attempts = 4,
    initialDelayMilliseconds = 10
) {
    if (attempts <= 0) {
        throw new Error("attempts must be positive.");
    }

    let delay = initialDelayMilliseconds;

    for (let attempt = 1; attempt <= attempts; attempt++) {
        try {
            return await operation();
        } catch (error) {
            if (!(error instanceof TemporaryFailure)) {
                throw error;
            }

            if (attempt === attempts) {
                throw error;
            }

            const jitter = Math.random() * delay * 0.25;

            await sleep(delay + jitter);
            delay *= 2;
        }
    }

    throw new Error("Unreachable.");
}

let unstableAttempts = 0;

async function unstableOperation() {
    unstableAttempts++;

    if (unstableAttempts < 3) {
        throw new TemporaryFailure(
            "Temporary downstream failure."
        );
    }

    return "success";
}

console.log(
    "\n[13] Retry result:",
    await retryWithExponentialBackoff(unstableOperation)
);

console.log("Attempts:", unstableAttempts);


// ============================================================================
// 16. IDEMPOTENCY
// ============================================================================

class PaymentService {
    constructor() {
        this.processedKeys = new Map();
        this.totalReceived = 0;
    }

    charge(amount, idempotencyKey) {
        if (!Number.isFinite(amount) || amount <= 0) {
            throw new RpcError(
                RpcStatus.INVALID_ARGUMENT,
                "Amount must be positive."
            );
        }

        if (!idempotencyKey) {
            throw new RpcError(
                RpcStatus.INVALID_ARGUMENT,
                "Idempotency key is required."
            );
        }

        if (this.processedKeys.has(idempotencyKey)) {
            return this.processedKeys.get(idempotencyKey);
        }

        this.totalReceived += amount;

        const receipt = `payment-${this.processedKeys.size + 1}`;

        this.processedKeys.set(
            idempotencyKey,
            receipt
        );

        return receipt;
    }
}

const paymentService = new PaymentService();

console.log("\n[14] First payment:");
console.log(paymentService.charge(100, "order-001"));

console.log("[14] Retry payment:");
console.log(paymentService.charge(100, "order-001"));

console.log(
    "Total received:",
    paymentService.totalReceived
);


// ============================================================================
// 17. SERVICE DISCOVERY AND ROUND ROBIN
// ============================================================================

class ServiceInstance {
    constructor(address, healthy = true) {
        this.address = address;
        this.healthy = healthy;
        this.activeRequests = 0;
    }
}

class RoundRobinBalancer {
    constructor(instances) {
        if (instances.length === 0) {
            throw new Error("At least one instance is required.");
        }

        this.instances = instances;
        this.index = 0;
    }

    choose() {
        const healthy = this.instances.filter(
            instance => instance.healthy
        );

        if (healthy.length === 0) {
            throw new RpcError(
                RpcStatus.UNAVAILABLE,
                "No healthy service instances."
            );
        }

        const selected = healthy[
            this.index % healthy.length
        ];

        this.index++;
        selected.activeRequests++;

        return selected;
    }
}

const instances = [
    new ServiceInstance("user-service-1"),
    new ServiceInstance("user-service-2"),
    new ServiceInstance("user-service-3")
];

const balancer = new RoundRobinBalancer(instances);

console.log("\n[15] Load balancing");

for (let index = 0; index < 6; index++) {
    const selected = balancer.choose();

    console.log(selected.address);

    selected.activeRequests--;
}


// ============================================================================
// 18. HEALTH CHECKING
// ============================================================================

const HealthState = Object.freeze({
    SERVING: "SERVING",
    NOT_SERVING: "NOT_SERVING"
});

class HealthService {
    constructor() {
        this.services = new Map();
    }

    setStatus(serviceName, status) {
        this.services.set(serviceName, status);
    }

    check(serviceName) {
        return {
            service: serviceName,
            status: this.services.get(
                serviceName
            ) ?? HealthState.NOT_SERVING
        };
    }
}

const healthService = new HealthService();

healthService.setStatus(
    "user-service",
    HealthState.SERVING
);

console.log("\n[16] Health");
console.log(healthService.check("user-service"));
console.log(healthService.check("unknown-service"));


// ============================================================================
// 19. CACHE WITH TTL
// ============================================================================

class TtlCache {
    constructor(ttlMilliseconds) {
        if (ttlMilliseconds <= 0) {
            throw new Error("TTL must be positive.");
        }

        this.ttlMilliseconds = ttlMilliseconds;
        this.entries = new Map();
    }

    set(key, value) {
        this.entries.set(key, {
            value,
            expiresAt:
                performance.now() +
                this.ttlMilliseconds
        });
    }

    get(key) {
        const entry = this.entries.get(key);

        if (!entry) {
            return undefined;
        }

        if (performance.now() >= entry.expiresAt) {
            this.entries.delete(key);
            return undefined;
        }

        return entry.value;
    }
}

const cache = new TtlCache(1000);

cache.set("user:1", user);

console.log("\n[17] Cached value:");
console.log(cache.get("user:1"));


// ============================================================================
// 20. SERVICE AGGREGATION
// ============================================================================

class Order {
    constructor(orderId, userId, amount, state) {
        this.orderId = orderId;
        this.userId = userId;
        this.amount = amount;
        this.state = state;
    }
}

class OrderService {
    constructor() {
        this.orders = [
            new Order(5001, 1, 2499, "PAID"),
            new Order(5002, 2, 1299, "CREATED"),
            new Order(5003, 1, 5999, "SHIPPED")
        ];
    }

    getOrdersForUser(userId) {
        if (!Number.isInteger(userId) || userId <= 0) {
            throw new RpcError(
                RpcStatus.INVALID_ARGUMENT,
                "userId must be positive."
            );
        }

        return this.orders.filter(
            order => order.userId === userId
        );
    }
}

class DashboardService {
    constructor(userServiceInstance, orderServiceInstance) {
        this.userService = userServiceInstance;
        this.orderService = orderServiceInstance;
    }

    getDashboard(userId) {
        const userResponse = this.userService.getUser({
            userId
        });

        const orders =
            this.orderService.getOrdersForUser(userId);

        const totalValue = orders.reduce(
            (total, order) => total + order.amount,
            0
        );

        return {
            user: userResponse.user,
            orders,
            totalValue
        };
    }
}

const orderService = new OrderService();

const dashboardService = new DashboardService(
    userService,
    orderService
);

console.log("\n[18] Aggregated dashboard");
console.log(
    dashboardService.getDashboard(1)
);


// ============================================================================
// 21. PARALLEL DOWNSTREAM REQUESTS
// ============================================================================

async function getProfile(userId) {
    await sleep(20);

    return {
        userId,
        profile: "profile-data"
    };
}

async function getOrders(userId) {
    await sleep(30);

    return {
        userId,
        orders: 4
    };
}

async function getRecommendations(userId) {
    await sleep(10);

    return {
        userId,
        recommendations: 7
    };
}

async function aggregateDashboardData(userId) {
    /*
     * Promise.all expresses independent downstream work.
     * Sequential awaits would unnecessarily add their latencies.
     *
     * Real systems also need:
     *   - individual deadlines
     *   - cancellation where supported
     *   - partial-failure policy
     *   - concurrency limits
     */
    const [
        profile,
        orders,
        recommendations
    ] = await Promise.all([
        getProfile(userId),
        getOrders(userId),
        getRecommendations(userId)
    ]);

    return {
        profile,
        orders,
        recommendations
    };
}

console.log(
    "\n[19] Parallel aggregation"
);

console.log(
    await aggregateDashboardData(1)
);


// ============================================================================
// 22. BULKHEAD
// ============================================================================

class Bulkhead {
    constructor(maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new Error(
                "maxConcurrent must be positive."
            );
        }

        this.maxConcurrent = maxConcurrent;
        this.active = 0;
        this.waiters = [];
    }

    async execute(operation) {
        if (this.active >= this.maxConcurrent) {
            await new Promise(resolve => {
                this.waiters.push(resolve);
            });
        }

        this.active++;

        try {
            return await operation();
        } finally {
            this.active--;

            const next = this.waiters.shift();

            if (next) {
                next();
            }
        }
    }
}

const bulkhead = new Bulkhead(2);

const bulkheadTasks = [1, 2, 3, 4].map(
    number =>
        bulkhead.execute(
            async () => {
                await sleep(10);
                return `task-${number}`;
            }
        )
);

console.log(
    "\n[20] Bulkhead results:",
    await Promise.all(bulkheadTasks)
);


// ============================================================================
// 23. CIRCUIT BREAKER
// ============================================================================

class CircuitBreaker {
    constructor(failureThreshold = 3) {
        this.failureThreshold = failureThreshold;
        this.failureCount = 0;
        this.state = "CLOSED";
    }

    async execute(operation) {
        if (this.state === "OPEN") {
            throw new RpcError(
                RpcStatus.UNAVAILABLE,
                "Circuit is open."
            );
        }

        try {
            const result = await operation();

            this.failureCount = 0;
            this.state = "CLOSED";

            return result;
        } catch (error) {
            if (error instanceof TemporaryFailure) {
                this.failureCount++;

                if (
                    this.failureCount >=
                    this.failureThreshold
                ) {
                    this.state = "OPEN";
                }
            }

            throw error;
        }
    }
}

const circuitBreaker = new CircuitBreaker(2);

for (let attempt = 1; attempt <= 2; attempt++) {
    try {
        await circuitBreaker.execute(
            async () => {
                throw new TemporaryFailure(
                    "Temporary downstream failure."
                );
            }
        );
    } catch (error) {
        console.log(
            `Circuit failure ${attempt}:`,
            circuitBreaker.state
        );
    }
}

try {
    await circuitBreaker.execute(
        async () => "not executed"
    );
} catch (error) {
    console.log(
        "Circuit open:",
        error.code,
        error.message
    );
}


// ============================================================================
// 24. REQUEST VALIDATION
// ============================================================================

function validateUserId(userId) {
    if (typeof userId !== "number" ||
        !Number.isInteger(userId)) {
        throw new RpcError(
            RpcStatus.INVALID_ARGUMENT,
            "userId must be an integer."
        );
    }

    if (userId <= 0) {
        throw new RpcError(
            RpcStatus.INVALID_ARGUMENT,
            "userId must be greater than zero."
        );
    }

    return userId;
}

console.log("\n[21] Validation");

for (const value of [1, 0, -1, "1", 2.5]) {
    try {
        console.log(
            value,
            "->",
            validateUserId(value)
        );
    } catch (error) {
        console.log(
            value,
            "->",
            error.code
        );
    }
}


// ============================================================================
// 25. MESSAGE SIZE LIMIT
// ============================================================================

function validateMessageSize(bytes, maximumBytes) {
    if (bytes.length > maximumBytes) {
        throw new RpcError(
            RpcStatus.INVALID_ARGUMENT,
            "Message exceeds configured size limit."
        );
    }
}

const smallPayload = new TextEncoder().encode(
    "small message"
);

validateMessageSize(
    smallPayload,
    1024
);

console.log(
    "\n[22] Message size:",
    smallPayload.length,
    "bytes"
);


// ============================================================================
// 26. TRACE CONTEXT
// ============================================================================

class TraceContext {
    constructor(
        traceId,
        spanId,
        parentSpanId = null
    ) {
        this.traceId = traceId;
        this.spanId = spanId;
        this.parentSpanId = parentSpanId;
    }

    createChild() {
        return new TraceContext(
            this.traceId,
            crypto.randomUUID().replaceAll("-", "").slice(0, 16),
            this.spanId
        );
    }
}

const rootTrace = new TraceContext(
    crypto.randomUUID(),
    crypto.randomUUID().replaceAll("-", "").slice(0, 16)
);

const childTrace = rootTrace.createChild();

console.log("\n[23] Trace propagation");
console.log("Root:", rootTrace);
console.log("Child:", childTrace);


// ============================================================================
// 27. REQUEST CONTEXT
// ============================================================================

class RequestContext {
    constructor({
        requestId = crypto.randomUUID(),
        traceContext = null,
        metadata = new RpcMetadata()
    } = {}) {
        this.requestId = requestId;
        this.traceContext = traceContext;
        this.metadata = metadata;
    }

    child() {
        return new RequestContext({
            requestId: this.requestId,
            traceContext: this.traceContext
                ? this.traceContext.createChild()
                : null,
            metadata: this.metadata
        });
    }
}

const requestContext = new RequestContext({
    traceContext: rootTrace,
    metadata
});

console.log("\n[24] Request context");
console.log(requestContext);


// ============================================================================
// 28. HEALTH-AWARE LOAD BALANCING
// ============================================================================

instances[1].healthy = false;

console.log("\n[25] Health-aware balancing");

for (let index = 0; index < 5; index++) {
    const selected = balancer.choose();
    console.log(selected.address);
    selected.activeRequests--;
}


// ============================================================================
// 29. OBSERVABILITY METRICS
// ============================================================================

class RpcMetrics {
    constructor() {
        this.calls = 0;
        this.failures = 0;
        this.totalLatencyMilliseconds = 0;
    }

    get averageLatencyMilliseconds() {
        if (this.calls === 0) {
            return 0;
        }

        return (
            this.totalLatencyMilliseconds /
            this.calls
        );
    }
}

const rpcMetrics = new RpcMetrics();

async function measuredRpc(operation) {
    const started = performance.now();

    rpcMetrics.calls++;

    try {
        return await operation();
    } catch (error) {
        rpcMetrics.failures++;
        throw error;
    } finally {
        rpcMetrics.totalLatencyMilliseconds +=
            performance.now() - started;
    }
}

await measuredRpc(
    async () => userClient.getUser(1)
);

await measuredRpc(
    async () => userClient.getUser(2)
);

console.log("\n[26] RPC metrics");
console.log({
    calls: rpcMetrics.calls,
    failures: rpcMetrics.failures,
    averageLatencyMilliseconds:
        rpcMetrics.averageLatencyMilliseconds
});


// ============================================================================
// 30. STRUCTURED ERROR HANDLING
// ============================================================================

function executeSafely(operation) {
    try {
        return {
            success: true,
            value: operation()
        };
    } catch (error) {
        if (error instanceof RpcError) {
            return {
                success: false,
                code: error.code,
                message: error.message
            };
        }

        return {
            success: false,
            code: RpcStatus.INTERNAL,
            message: "Unexpected server error."
        };
    }
}

console.log(
    "\n[27] Structured error:",
    executeSafely(
        () => userClient.getUser(10000)
    )
);


// ============================================================================
// 31. SERVICE CONTRACT TESTS
// ============================================================================

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function testExistingUser() {
    const response = userService.getUser({
        userId: 1
    });

    assert(
        response.found === true,
        "Existing user should be found."
    );

    assert(
        response.user.id === 1,
        "User ID should be 1."
    );
}

function testMissingUser() {
    try {
        userService.getUser({
            userId: 9999
        });

        throw new Error(
            "Expected NOT_FOUND error."
        );
    } catch (error) {
        assert(
            error.code === RpcStatus.NOT_FOUND,
            "Missing user should return NOT_FOUND."
        );
    }
}

function testInvalidUser() {
    try {
        userService.getUser({
            userId: 0
        });

        throw new Error(
            "Expected INVALID_ARGUMENT."
        );
    } catch (error) {
        assert(
            error.code === RpcStatus.INVALID_ARGUMENT,
            "Invalid ID should return INVALID_ARGUMENT."
        );
    }
}

testExistingUser();
testMissingUser();
testInvalidUser();

console.log(
    "\n[28] Contract tests passed."
);


// ============================================================================
// 32. JSON AS A CONTRAST
// ============================================================================

const jsonRepresentation = JSON.stringify({
    id: 1,
    name: "Ada",
    active: true
});

console.log("\n[29] Text representation");
console.log(jsonRepresentation);

console.log(
    "JSON byte length:",
    new TextEncoder().encode(
        jsonRepresentation
    ).length
);

console.log(
    "Binary protobuf-style byte length:",
    encodeUser(
        new User(
            1,
            "Ada",
            "ada@example.com"
        )
    ).length
);


// ============================================================================
// 33. PROTOBUF SCHEMA EVOLUTION
// ============================================================================

/*
 * Schema evolution example:
 *
 * Original:
 *
 * message User {
 *     int32 id = 1;
 *     string name = 2;
 *     string email = 3;
 * }
 *
 * Later:
 *
 * message User {
 *     int32 id = 1;
 *     string name = 2;
 *     string email = 3;
 *     string department = 4;
 * }
 *
 * Field 4 is newly assigned.
 *
 * A removed field number should not simply be reused for an unrelated
 * meaning. In .proto definitions, removed numbers and names can be reserved.
 *
 * Protobuf also supports:
 *   - repeated
 *   - map
 *   - enum
 *   - oneof
 *   - nested messages
 *   - optional fields
 *   - bytes
 *   - well-known types
 */


// ============================================================================
// 34. ASYNCHRONOUS SERVICE AGGREGATION WITH DEADLINE
// ============================================================================

async function aggregateWithDeadline(userId, timeoutMilliseconds) {
    return withDeadline(
        async () => {
            const results = await Promise.all([
                getProfile(userId),
                getOrders(userId),
                getRecommendations(userId)
            ]);

            return {
                profile: results[0],
                orders: results[1],
                recommendations: results[2]
            };
        },
        timeoutMilliseconds
    );
}

console.log(
    "\n[30] Aggregation with deadline"
);

try {
    console.log(
        await aggregateWithDeadline(1, 100)
    );
} catch (error) {
    console.log(
        error.code,
        error.message
    );
}


// ============================================================================
// 35. PARTIAL FAILURE
// ============================================================================

async function optionalRecommendationService() {
    try {
        await sleep(5);

        return ["item-1", "item-2"];
    } catch {
        return [];
    }
}

async function resilientDashboard(userId) {
    const userResponse = userClient.getUser(userId);

    const [
        orders,
        recommendations
    ] = await Promise.all([
        getOrders(userId),
        optionalRecommendationService()
    ]);

    return {
        user: userResponse.user,
        orders,
        recommendations
    };
}

console.log(
    "\n[31] Resilient dashboard"
);

console.log(
    await resilientDashboard(1)
);


// ============================================================================
// 36. IDEMPOTENT REQUEST IDENTIFIER
// ============================================================================

function createIdempotencyKey() {
    return crypto.randomUUID();
}

const idempotencyKey = createIdempotencyKey();

console.log(
    "\n[32] Idempotency key:",
    idempotencyKey
);


// ============================================================================
// 37. SECURITY: SECRET HANDLING
// ============================================================================

async function sha256Hex(value) {
    /*
     * Web Crypto is available in modern Node.js runtimes and browsers.
     * Secrets should not be printed directly into logs.
     */
    const data = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest(
        "SHA-256",
        data
    );

    return Array.from(new Uint8Array(digest))
        .map(byte => byte.toString(16).padStart(2, "0"))
        .join("");
}

const tokenFingerprint = await sha256Hex(
    "example-secret-token"
);

console.log(
    "\n[33] Secret fingerprint:",
    tokenFingerprint.slice(0, 12)
);


// ============================================================================
// 38. API DESIGN CHECKLIST
// ============================================================================

const apiDesignPrinciples = [
    "Use stable service boundaries.",
    "Define explicit request and response schemas.",
    "Treat protobuf field numbers as persistent identifiers.",
    "Use deadlines for remote calls.",
    "Classify errors using meaningful status semantics.",
    "Retry only transient failures where retrying is safe.",
    "Protect non-idempotent operations with idempotency keys.",
    "Propagate trace and request identifiers.",
    "Authenticate and authorize service boundaries.",
    "Use bounded concurrency.",
    "Use streaming for suitable large or continuous data.",
    "Monitor latency, errors, throughput, and saturation.",
    "Avoid unnecessary synchronous dependency chains."
];

console.log("\n[34] API design principles");

for (const principle of apiDesignPrinciples) {
    console.log("-", principle);
}


// ============================================================================
// 39. PRODUCTION ARCHITECTURE
// ============================================================================

console.log("\n[35] Production architecture");

console.log(`
Client
  |
  | gRPC / HTTP/2
  v
API Gateway / Backend-for-Frontend
  |
  +----------------------+----------------------+
  |                      |                      |
  v                      v                      v
User Service         Order Service       Recommendation Service
  |                      |                      |
  v                      v                      v
User Database        Order Database       Feature/Data Store

Cross-cutting infrastructure:
- TLS or mutual TLS
- authentication
- authorization
- service discovery
- load balancing
- deadlines
- retry policy
- health checks
- metrics
- structured logging
- distributed tracing
- resource limits
`);


// ============================================================================
// 40. FINAL INTEGRATED RPC OPERATION
// ============================================================================

async function integratedRequest(userId) {
    validateUserId(userId);

    const requestId = crypto.randomUUID();

    const trace = new TraceContext(
        crypto.randomUUID(),
        crypto.randomUUID().replaceAll("-", "").slice(0, 16)
    );

    const requestMetadata = new RpcMetadata({
        "x-request-id": requestId,
        "x-trace-id": trace.traceId
    });

    const requestContext = new RequestContext({
        requestId,
        traceContext: trace,
        metadata: requestMetadata
    });

    try {
        const response = await loggingInterceptor(
            "UserService/GetUser",
            requestMetadata,
            () => userClient.getUser(userId)
        );

        return {
            requestId: requestContext.requestId,
            traceId: requestContext.traceContext.traceId,
            status: RpcStatus.OK,
            user: response.user
        };
    } catch (error) {
        return {
            requestId,
            traceId: trace.traceId,
            status: error instanceof RpcError
                ? error.code
                : RpcStatus.INTERNAL,
            error: error.message
        };
    }
}

console.log(
    "\n[36] Integrated request"
);

console.log(
    await integratedRequest(1)
);

console.log(
    await integratedRequest(999)
);

console.log("\nJavaScript study file completed successfully.");
