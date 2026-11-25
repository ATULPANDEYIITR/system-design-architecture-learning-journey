"use strict";

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");

const ComponentState = Object.freeze({
    HEALTHY: "HEALTHY",
    DEGRADED: "DEGRADED",
    FAILED: "FAILED",
    RECOVERING: "RECOVERING"
});

const DependencyType = Object.freeze({
    REQUIRED: "REQUIRED",
    OPTIONAL: "OPTIONAL"
});

const CircuitState = Object.freeze({
    CLOSED: "CLOSED",
    OPEN: "OPEN",
    HALF_OPEN: "HALF_OPEN"
});

class ServiceError extends Error {
    constructor(message, service, cause) {
        super(message, { cause });
        this.name = "ServiceError";
        this.service = service;
    }
}

class Dependency {
    constructor({
        name,
        type,
        timeoutMs = 1000,
        fallback = null,
        operation
    }) {
        if (!name || typeof operation !== "function") {
            throw new TypeError("Dependency requires a name and operation");
        }

        if (!Object.values(DependencyType).includes(type)) {
            throw new TypeError("Invalid dependency type");
        }

        if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
            throw new RangeError("Timeout must be positive");
        }

        this.name = name;
        this.type = type;
        this.timeoutMs = timeoutMs;
        this.fallback = fallback;
        this.operation = operation;

        this.state = ComponentState.HEALTHY;
        this.circuit = CircuitState.CLOSED;
        this.failures = 0;
        this.recoveries = 0;
        this.openedAt = null;
    }
}

class CircuitBreaker {
    constructor({
        threshold = 3,
        resetTimeoutMs = 5000
    } = {}) {
        if (threshold < 1 || resetTimeoutMs <= 0) {
            throw new RangeError("Invalid circuit breaker settings");
        }

        this.threshold = threshold;
        this.resetTimeoutMs = resetTimeoutMs;
    }

    canExecute(dependency) {
        if (dependency.circuit === CircuitState.CLOSED) {
            return true;
        }

        if (dependency.circuit === CircuitState.OPEN) {
            const elapsed = Date.now() - dependency.openedAt;

            if (elapsed >= this.resetTimeoutMs) {
                dependency.circuit = CircuitState.HALF_OPEN;
                dependency.state = ComponentState.RECOVERING;
                return true;
            }

            return false;
        }

        return true;
    }

    success(dependency) {
        dependency.failures = 0;
        dependency.recoveries++;
        dependency.circuit = CircuitState.CLOSED;
        dependency.state = ComponentState.HEALTHY;
        dependency.openedAt = null;
    }

    failure(dependency) {
        dependency.failures++;

        if (
            dependency.circuit === CircuitState.HALF_OPEN ||
            dependency.failures >= this.threshold
        ) {
            dependency.circuit = CircuitState.OPEN;
            dependency.state = ComponentState.FAILED;
            dependency.openedAt = Date.now();
        } else {
            dependency.state = ComponentState.DEGRADED;
        }
    }
}

class ResilienceController extends EventEmitter {
    constructor(options = {}) {
        super();

        this.dependencies = new Map();
        this.breaker = new CircuitBreaker(options);
        this.activeRequests = 0;
    }

    register(config) {
        const dependency = new Dependency(config);

        if (this.dependencies.has(dependency.name)) {
            throw new Error(`Duplicate dependency: ${dependency.name}`);
        }

        this.dependencies.set(dependency.name, dependency);
        this.emit("dependency:registered", {
            name: dependency.name
        });
    }

    async execute(name) {
        const dependency = this.dependencies.get(name);

        if (!dependency) {
            throw new ServiceError("Unknown dependency", name);
        }

        if (!this.breaker.canExecute(dependency)) {
            return this.handleFailure(
                dependency,
                new Error("Circuit breaker is open")
            );
        }

        this.activeRequests++;

        let timeout;

        try {
            // A timeout prevents a slow dependency from blocking the request.
            const timeoutPromise = new Promise((_, reject) => {
                timeout = setTimeout(
                    () => reject(new Error("Dependency timeout")),
                    dependency.timeoutMs
                );
            });

            const result = await Promise.race([
                Promise.resolve().then(() => dependency.operation()),
                timeoutPromise
            ]);

            this.breaker.success(dependency);

            this.emit("dependency:healthy", {
                name,
                timestamp: new Date().toISOString()
            });

            return {
                value: result,
                degraded: false,
                source: "primary"
            };

        } catch (error) {
            return this.handleFailure(dependency, error);

        } finally {
            clearTimeout(timeout);
            this.activeRequests--;
        }
    }

    handleFailure(dependency, error) {
        this.breaker.failure(dependency);

        this.emit("dependency:failed", {
            name: dependency.name,
            error: error.message,
            circuit: dependency.circuit
        });

        if (dependency.type === DependencyType.REQUIRED) {
            throw new ServiceError(
                `${dependency.name} is unavailable`,
                dependency.name,
                error
            );
        }

        this.emit("dependency:fallback", {
            name: dependency.name
        });

        return {
            value: dependency.fallback,
            degraded: true,
            source: "fallback",
            error: error.message
        };
    }

    health() {
        return {
            activeRequests: this.activeRequests,
            components: [...this.dependencies.values()].map(item => ({
                name: item.name,
                type: item.type,
                state: item.state,
                circuit: item.circuit,
                failures: item.failures,
                recoveries: item.recoveries
            }))
        };
    }

    systemState() {
        const components = [...this.dependencies.values()];

        if (
            components.some(
                item =>
                    item.type === DependencyType.REQUIRED &&
                    item.state === ComponentState.FAILED
            )
        ) {
            return "UNAVAILABLE";
        }

        if (
            components.some(
                item =>
                    item.state !== ComponentState.HEALTHY
            )
        ) {
            return "DEGRADED";
        }

        return "HEALTHY";
    }
}

class CommerceApplication {
    constructor() {
        this.controller = new ResilienceController({
            threshold: 2,
            resetTimeoutMs: 100
        });

        this.controller.register({
            name: "catalog",
            type: DependencyType.REQUIRED,
            timeoutMs: 500,
            operation: async () => ({
                id: "P-100",
                name: "Enterprise Laptop"
            })
        });

        this.controller.register({
            name: "inventory",
            type: DependencyType.REQUIRED,
            timeoutMs: 500,
            operation: async () => ({
                available: 18
            })
        });

        this.controller.register({
            name: "recommendations",
            type: DependencyType.OPTIONAL,
            fallback: [],
            operation: async () => [
                "Laptop Stand",
                "Wireless Mouse"
            ]
        });

        this.controller.register({
            name: "customer_profile",
            type: DependencyType.OPTIONAL,
            fallback: {
                personalization: false,
                mode: "generic"
            },
            operation: async () => ({
                personalization: true,
                mode: "customer-specific"
            })
        });

        this.controller.register({
            name: "analytics",
            type: DependencyType.OPTIONAL,
            fallback: {
                queued: false
            },
            operation: async () => ({
                recorded: true
            })
        });
    }

    async browse() {
        // Required capabilities execute independently from optional ones.
        const [catalog, inventory] = await Promise.all([
            this.controller.execute("catalog"),
            this.controller.execute("inventory")
        ]);

        const optionalResults = await Promise.all(
            [
                "recommendations",
                "customer_profile",
                "analytics"
            ].map(name => this.controller.execute(name))
        );

        const optionalNames = [
            "recommendations",
            "customer_profile",
            "analytics"
        ];

        const optional = Object.fromEntries(
            optionalNames.map((name, index) => [
                name,
                optionalResults[index]
            ])
        );

        const degradedFeatures = Object.entries(optional)
            .filter(([, result]) => result.degraded)
            .map(([name]) => name);

        return {
            requestId: crypto.randomUUID(),
            state: this.controller.systemState(),
            product: catalog.value,
            inventory: inventory.value,
            optional,
            degradedFeatures,
            timestamp: new Date().toISOString()
        };
    }
}

async function main() {
    const application = new CommerceApplication();

    application.controller.on("dependency:failed", event => {
        console.log("FAILURE EVENT:", event);
    });

    application.controller.on("dependency:fallback", event => {
        console.log("FALLBACK EVENT:", event);
    });

    console.log("\nSCENARIO 1: Normal operation");

    const normal = await application.browse();
    console.log(JSON.stringify(normal, null, 2));

    // Simulate an optional dependency failure.
    const recommendation = application.controller.dependencies.get(
        "recommendations"
    );

    recommendation.operation = async () => {
        throw new Error("Recommendation database unavailable");
    };

    console.log("\nSCENARIO 2: Optional dependency failure");

    const degraded = await application.browse();
    console.log(JSON.stringify(degraded, null, 2));

    if (
        degraded.state !== "DEGRADED" ||
        degraded.degradedFeatures.length !== 1
    ) {
        throw new Error("Degraded-mode validation failed");
    }

    // Required dependencies cannot silently use optional fallbacks.
    const inventory = application.controller.dependencies.get("inventory");

    inventory.operation = async () => {
        throw new Error("Inventory database unavailable");
    };

    console.log("\nSCENARIO 3: Required dependency failure");

    try {
        await application.browse();
    } catch (error) {
        console.log("Request rejected:", error.message);
    }

    console.log("\nHEALTH REPORT");
    const report = application.controller.health();
    console.log(JSON.stringify(report, null, 2));

    await fs.writeFile(
        "resilience-health.json",
        JSON.stringify(report, null, 2),
        { encoding: "utf8", mode: 0o600 }
    );

    console.log("\nSystem state:", application.controller.systemState());
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
