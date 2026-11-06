"use strict";

/*
 * Microservices Architecture
 * Event-driven service boundaries, asynchronous communication,
 * independent deployment, compatibility validation and resilience.
 */

const { randomUUID } = require("node:crypto");
const { EventEmitter } = require("node:events");

class DomainError extends Error {
    constructor(message, code = "DOMAIN_ERROR") {
        super(message);
        this.name = "DomainError";
        this.code = code;
    }
}

const ServiceState = Object.freeze({
    REGISTERED: "registered",
    DEPLOYING: "deploying",
    HEALTHY: "healthy",
    DEGRADED: "degraded",
    UNAVAILABLE: "unavailable"
});

function validateName(name) {
    if (
        typeof name !== "string" ||
        !/^[a-z][a-z0-9-]{1,48}$/.test(name)
    ) {
        throw new DomainError(`Invalid service name: ${name}`);
    }

    return name;
}

function parseVersion(version) {
    if (
        typeof version !== "string" ||
        !/^\d+\.\d+\.\d+$/.test(version)
    ) {
        throw new DomainError(`Invalid version: ${version}`);
    }

    return version.split(".").map(Number);
}

function compareVersions(left, right) {
    const a = parseVersion(left);
    const b = parseVersion(right);

    for (let i = 0; i < 3; i++) {
        if (a[i] !== b[i]) {
            return a[i] - b[i];
        }
    }

    return 0;
}

class ServiceContract {
    constructor({
        name,
        version,
        apiVersion,
        endpoints,
        backwardCompatible = true
    }) {
        this.name = validateName(name);
        this.version = version;
        this.apiVersion = apiVersion;
        this.endpoints = Object.freeze([...endpoints]);
        this.backwardCompatible = backwardCompatible;

        parseVersion(version);

        if (!Number.isInteger(apiVersion) || apiVersion < 1) {
            throw new DomainError("Invalid API version.");
        }

        if (
            this.endpoints.length === 0 ||
            this.endpoints.some(
                endpoint =>
                    typeof endpoint !== "string" ||
                    !endpoint.startsWith("/")
            )
        ) {
            throw new DomainError("Invalid endpoint definition.");
        }

        if (new Set(this.endpoints).size !== this.endpoints.length) {
            throw new DomainError("Duplicate endpoints.");
        }

        Object.freeze(this);
    }
}

class Microservice {
    constructor({
        name,
        description,
        contract,
        dependencies = [],
        instances = 1
    }) {
        this.name = validateName(name);
        this.description = description;
        this.contract = contract;
        this.dependencies = new Set(dependencies);
        this.instances = instances;
        this.state = ServiceState.REGISTERED;
        this.deploymentCount = 0;

        if (contract.name !== name) {
            throw new DomainError("Contract identity mismatch.");
        }

        if (!description.trim()) {
            throw new DomainError("Description is required.");
        }

        if (!Number.isInteger(instances) || instances < 1) {
            throw new DomainError("Invalid instance count.");
        }
    }
}

class ServiceRegistry {
    #services = new Map();

    register(service) {
        if (this.#services.has(service.name)) {
            throw new DomainError(
                `Service already exists: ${service.name}`
            );
        }

        this.#services.set(service.name, service);
    }

    get(name) {
        const service = this.#services.get(name);

        if (!service) {
            throw new DomainError(
                `Unknown service: ${name}`,
                "SERVICE_NOT_FOUND"
            );
        }

        return service;
    }

    validateDependencies(name) {
        const service = this.get(name);

        for (const dependency of service.dependencies) {
            if (!this.#services.has(dependency)) {
                throw new DomainError(
                    `${name} requires missing service ${dependency}`,
                    "MISSING_DEPENDENCY"
                );
            }
        }

        this.deploymentOrder();
    }

    deploymentOrder() {
        const visited = new Set();
        const active = new Set();
        const result = [];

        const visit = name => {
            if (active.has(name)) {
                throw new DomainError(
                    `Circular dependency: ${name}`,
                    "CIRCULAR_DEPENDENCY"
                );
            }

            if (visited.has(name)) return;

            active.add(name);

            const service = this.get(name);

            for (const dependency of service.dependencies) {
                visit(dependency);
            }

            active.delete(name);
            visited.add(name);
            result.push(name);
        };

        for (const name of this.#services.keys()) {
            visit(name);
        }

        return result;
    }

    consumers(name) {
        this.get(name);

        return [...this.#services.values()]
            .filter(service => service.dependencies.has(name))
            .map(service => service.name);
    }

    inventory() {
        return [...this.#services.values()].map(service => ({
            name: service.name,
            version: service.contract.version,
            apiVersion: service.contract.apiVersion,
            state: service.state,
            instances: service.instances,
            dependencies: [...service.dependencies],
            deploymentCount: service.deploymentCount
        }));
    }
}

class ContractPolicy {
    static validate(oldContract, newContract) {
        if (oldContract.name !== newContract.name) {
            throw new DomainError("Service identity changed.");
        }

        if (
            newContract.apiVersion < oldContract.apiVersion
        ) {
            throw new DomainError("API version downgrade rejected.");
        }

        const removed = oldContract.endpoints.filter(
            endpoint => !newContract.endpoints.includes(endpoint)
        );

        if (
            removed.length &&
            newContract.apiVersion <= oldContract.apiVersion
        ) {
            throw new DomainError(
                `Breaking changes require an API version increase: ${
                    removed.join(", ")
                }`
            );
        }

        if (
            removed.length &&
            newContract.backwardCompatible
        ) {
            throw new DomainError(
                "Breaking contract cannot be backward compatible."
            );
        }
    }
}

class DeploymentManager extends EventEmitter {
    #registry;
    #history = new Map();

    constructor(registry) {
        super();
        this.#registry = registry;
    }

    async deploy(name, newContract, healthCheck) {
        const service = this.#registry.get(name);

        this.#registry.validateDependencies(name);
        ContractPolicy.validate(service.contract, newContract);

        const previousContract = service.contract;

        const record = {
            id: randomUUID(),
            service: name,
            previousVersion: previousContract.version,
            targetVersion: newContract.version,
            state: "pending",
            timestamp: new Date().toISOString()
        };

        service.state = ServiceState.DEPLOYING;

        this.emit("deployment.started", record);

        try {
            if (typeof healthCheck !== "function") {
                throw new DomainError("Health check is required.");
            }

            // Health validation occurs before replacing the active contract.
            const healthy = await healthCheck({
                service: name,
                version: newContract.version
            });

            if (healthy !== true) {
                throw new DomainError(
                    "New deployment failed its health check."
                );
            }

            service.contract = newContract;
            service.deploymentCount++;
            service.state = ServiceState.HEALTHY;

            record.state = "success";
            record.finishedAt = new Date().toISOString();

            this.#history.set(record.id, {
                record,
                previousContract,
                deployedContract: newContract
            });

            this.emit("deployment.succeeded", record);

        } catch (error) {
            service.contract = previousContract;
            service.state = ServiceState.HEALTHY;

            record.state = "rolled_back";
            record.error = error.message;
            record.finishedAt = new Date().toISOString();

            this.#history.set(record.id, {
                record,
                previousContract,
                deployedContract: null
            });

            this.emit("deployment.failed", record);
        }

        return Object.freeze({ ...record });
    }

    rollback(name, deploymentId) {
        const service = this.#registry.get(name);
        const deployment = this.#history.get(deploymentId);

        if (
            !deployment ||
            deployment.record.service !== name ||
            deployment.record.state !== "success"
        ) {
            throw new DomainError("Invalid rollback target.");
        }

        service.contract = deployment.previousContract;
        service.state = ServiceState.HEALTHY;

        const record = {
            id: randomUUID(),
            service: name,
            targetVersion: service.contract.version,
            state: "success",
            operation: "rollback",
            timestamp: new Date().toISOString()
        };

        this.emit("deployment.rolled_back", record);
        return record;
    }

    history() {
        return [...this.#history.values()].map(
            item => ({ ...item.record })
        );
    }
}

class EventEnvelope {
    constructor(type, source, payload) {
        if (!type || !source || !payload ||
            typeof payload !== "object" ||
            Array.isArray(payload)) {
            throw new DomainError("Invalid event envelope.");
        }

        this.id = randomUUID();
        this.type = type;
        this.source = source;
        this.payload = structuredClone(payload);
        this.timestamp = new Date().toISOString();
    }
}

class EventBroker extends EventEmitter {
    #handlers = new Map();
    #processed = new Map();
    #deadLetters = [];

    subscribe(type, consumer, handler) {
        if (typeof handler !== "function") {
            throw new DomainError("Invalid event handler.");
        }

        if (!this.#handlers.has(type)) {
            this.#handlers.set(type, new Map());
        }

        const subscribers = this.#handlers.get(type);

        if (subscribers.has(consumer)) {
            throw new DomainError("Duplicate consumer subscription.");
        }

        subscribers.set(consumer, handler);
    }

    async publish(event) {
        const subscribers = this.#handlers.get(event.type);

        if (!subscribers) return [];

        const results = await Promise.allSettled(
            [...subscribers.entries()].map(
                async ([consumer, handler]) => {
                    const key = `${event.id}:${consumer}`;

                    // Idempotency is tracked per event and consumer.
                    if (this.#processed.has(key)) {
                        return {
                            consumer,
                            status: "duplicate"
                        };
                    }

                    await handler(
                        structuredClone(event.payload),
                        event
                    );

                    this.#processed.set(key, true);

                    return {
                        consumer,
                        status: "processed"
                    };
                }
            )
        );

        results.forEach((result, index) => {
            if (result.status === "rejected") {
                const consumer = [
                    ...subscribers.keys()
                ][index];

                this.#deadLetters.push({
                    eventId: event.id,
                    consumer,
                    error: result.reason.message
                });
            }
        });

        this.emit("event.published", {
            eventId: event.id,
            type: event.type
        });

        return results;
    }

    deadLetters() {
        return structuredClone(this.#deadLetters);
    }
}

class CircuitBreaker {
    constructor({
        failureThreshold = 3,
        resetTimeoutMs = 5000
    } = {}) {
        if (failureThreshold < 1 || resetTimeoutMs < 1) {
            throw new DomainError("Invalid circuit breaker policy.");
        }

        this.failureThreshold = failureThreshold;
        this.resetTimeoutMs = resetTimeoutMs;
        this.failures = 0;
        this.state = "closed";
        this.openedAt = 0;
    }

    async execute(operation) {
        if (this.state === "open") {
            if (Date.now() - this.openedAt < this.resetTimeoutMs) {
                throw new DomainError(
                    "Circuit is open.",
                    "CIRCUIT_OPEN"
                );
            }

            this.state = "half_open";
        }

        try {
            const result = await operation();

            this.failures = 0;
            this.state = "closed";

            return result;

        } catch (error) {
            this.failures++;

            if (
                this.state === "half_open" ||
                this.failures >= this.failureThreshold
            ) {
                this.state = "open";
                this.openedAt = Date.now();
            }

            throw error;
        }
    }
}

async function main() {
    console.log("MICROSERVICES ARCHITECTURE");
    console.log("=".repeat(55));

    const registry = new ServiceRegistry();

    const payment = new Microservice({
        name: "payment-service",
        description: "Payment processing capability.",
        contract: new ServiceContract({
            name: "payment-service",
            version: "1.0.0",
            apiVersion: 1,
            endpoints: ["/payments", "/payments/{id}"]
        })
    });

    const inventory = new Microservice({
        name: "inventory-service",
        description: "Inventory management capability.",
        contract: new ServiceContract({
            name: "inventory-service",
            version: "1.0.0",
            apiVersion: 1,
            endpoints: ["/inventory", "/inventory/{id}"]
        })
    });

    const orders = new Microservice({
        name: "order-service",
        description: "Order lifecycle management.",
        contract: new ServiceContract({
            name: "order-service",
            version: "1.0.0",
            apiVersion: 1,
            endpoints: ["/orders", "/orders/{id}"]
        }),
        dependencies: [
            "payment-service",
            "inventory-service"
        ]
    });

    [payment, inventory, orders].forEach(
        service => registry.register(service)
    );

    console.log("\nDependency order:");
    console.log(registry.deploymentOrder().join(" -> "));

    console.log("\nService inventory:");
    console.table(registry.inventory());

    const manager = new DeploymentManager(registry);

    manager.on("deployment.succeeded", record => {
        console.log(
            `Deployment succeeded: ${record.service} ${record.targetVersion}`
        );
    });

    const updatedPayment = new ServiceContract({
        name: "payment-service",
        version: "1.1.0",
        apiVersion: 1,
        endpoints: [
            "/payments",
            "/payments/{id}",
            "/payments/{id}/status"
        ]
    });

    console.log("\nIndependent deployment:");

    const successfulDeployment = await manager.deploy(
        "payment-service",
        updatedPayment,
        async () => true
    );

    console.log(successfulDeployment);

    console.log("\nFailed deployment:");

    const failedDeployment = await manager.deploy(
        "inventory-service",
        new ServiceContract({
            name: "inventory-service",
            version: "1.1.0",
            apiVersion: 1,
            endpoints: ["/inventory", "/inventory/{id}"]
        }),
        async () => false
    );

    console.log(failedDeployment);

    console.log("\nEvent-driven communication:");

    const broker = new EventBroker();
    const receivedOrders = [];

    broker.subscribe(
        "order.created",
        "inventory-consumer",
        async payload => {
            receivedOrders.push(payload.orderId);
            console.log(
                "Inventory processing:",
                payload.orderId
            );
        }
    );

    broker.subscribe(
        "order.created",
        "notification-consumer",
        async payload => {
            console.log(
                "Notification requested:",
                payload.orderId
            );
        }
    );

    const event = new EventEnvelope(
        "order.created",
        "order-service",
        { orderId: "ORD-2001" }
    );

    await broker.publish(event);
    await broker.publish(event);

    if (receivedOrders.length !== 1) {
        throw new Error("Idempotency validation failed.");
    }

    console.log("\nCircuit breaker:");

    const breaker = new CircuitBreaker({
        failureThreshold: 2,
        resetTimeoutMs: 100
    });

    for (let i = 0; i < 3; i++) {
        try {
            await breaker.execute(async () => {
                throw new Error("Payment service unavailable.");
            });
        } catch (error) {
            console.log(
                `Attempt ${i + 1}: ${error.message}; state=${breaker.state}`
            );
        }
    }

    console.log("\nConsumer services:");
    console.log(registry.consumers("payment-service"));

    console.log("\nFinal inventory:");
    console.table(registry.inventory());

    console.log("\nDead-letter records:");
    console.log(broker.deadLetters());
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
