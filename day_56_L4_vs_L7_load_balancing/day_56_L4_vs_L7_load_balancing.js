"use strict";

/*
 * L4 vs L7 Load Balancing
 *
 * This Node.js program models:
 * - L4 TCP-flow routing
 * - L7 HTTP request routing
 * - asynchronous health checks
 * - weighted application routing
 * - session affinity
 * - failure recovery
 * - validation and security boundaries
 *
 * Runtime: Node.js 18+
 */

const crypto = require("node:crypto");

const BackendState = Object.freeze({
    HEALTHY: "healthy",
    UNHEALTHY: "unhealthy"
});

class Backend {
    constructor({ name, address, port, state = BackendState.HEALTHY, weight = 1 }) {
        if (!name || !address || !Number.isInteger(port) || port < 1 || port > 65535) {
            throw new TypeError("Invalid backend definition");
        }

        this.name = name;
        this.address = address;
        this.port = port;
        this.state = state;
        this.weight = weight;
        this.activeConnections = 0;
        this.requestsServed = 0;
    }

    isAvailable() {
        return this.state === BackendState.HEALTHY && this.weight > 0;
    }
}

class L4LoadBalancer {
    constructor(backends) {
        if (!Array.isArray(backends) || backends.length === 0) {
            throw new Error("L4 requires at least one backend");
        }

        this.backends = backends;
        this.flowTable = new Map();
    }

    healthyBackends() {
        return this.backends.filter((backend) => backend.isAvailable());
    }

    flowKey(clientIp, clientPort, destinationIp, destinationPort) {
        return `${clientIp}:${clientPort}->${destinationIp}:${destinationPort}`;
    }

    selectBackend(clientIp, clientPort, destinationIp, destinationPort) {
        const key = this.flowKey(
            clientIp,
            clientPort,
            destinationIp,
            destinationPort
        );

        const existingName = this.flowTable.get(key);

        if (existingName) {
            const existing = this.backends.find(
                (backend) => backend.name === existingName
            );

            if (existing && existing.isAvailable()) {
                return existing;
            }

            this.flowTable.delete(key);
        }

        const candidates = this.healthyBackends();

        if (candidates.length === 0) {
            throw new Error("No healthy L4 backend is available");
        }

        const digest = crypto
            .createHash("sha256")
            .update(key)
            .digest();

        const value = digest.readBigUInt64BE(0);
        const index = Number(value % BigInt(candidates.length));
        const backend = candidates[index];

        this.flowTable.set(key, backend.name);
        backend.activeConnections += 1;

        return backend;
    }

    closeConnection(clientIp, clientPort, destinationIp, destinationPort) {
        const key = this.flowKey(
            clientIp,
            clientPort,
            destinationIp,
            destinationPort
        );

        const backendName = this.flowTable.get(key);

        if (!backendName) {
            return;
        }

        this.flowTable.delete(key);

        const backend = this.backends.find(
            (item) => item.name === backendName
        );

        if (backend) {
            backend.activeConnections = Math.max(
                0,
                backend.activeConnections - 1
            );
        }
    }
}

class L7LoadBalancer {
    constructor(backends) {
        this.backends = backends;
        this.sessionAffinity = new Map();

        this.routes = [
            {
                match: (request) => request.path.startsWith("/api"),
                candidates: ["api-1", "api-2"]
            },
            {
                match: (request) => request.path.startsWith("/static"),
                candidates: ["static-1"]
            },
            {
                match: () => true,
                candidates: ["api-1", "api-2"]
            }
        ];
    }

    backend(name) {
        return this.backends.find((item) => item.name === name);
    }

    validateRequest(request) {
        if (!request || typeof request !== "object") {
            throw new TypeError("Request must be an object");
        }

        if (!["GET", "POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
            throw new Error(`Unsupported HTTP method: ${request.method}`);
        }

        if (
            typeof request.host !== "string" ||
            request.host.length === 0 ||
            request.host.length > 253
        ) {
            throw new Error("Invalid HTTP host");
        }

        if (
            typeof request.path !== "string" ||
            !request.path.startsWith("/") ||
            request.path.length > 4096
        ) {
            throw new Error("Invalid HTTP path");
        }
    }

    routeCandidates(request) {
        const rule = this.routes.find((candidate) => candidate.match(request));

        const candidates = rule.candidates
            .map((name) => this.backend(name))
            .filter((backend) => backend && backend.isAvailable());

        if (candidates.length === 0) {
            throw new Error(`No healthy L7 backend for ${request.path}`);
        }

        return candidates;
    }

    selectLeastConnections(candidates) {
        let selected = candidates[0];

        for (const backend of candidates) {
            if (backend.activeConnections < selected.activeConnections) {
                selected = backend;
            }
        }

        return selected;
    }

    extractSessionId(headers = {}) {
        const cookie = headers.cookie || headers.Cookie || "";

        for (const item of cookie.split(";")) {
            const [name, value] = item.trim().split("=", 2);

            if (name === "SESSION_ID" && value) {
                return value;
            }
        }

        return null;
    }

    async route(request) {
        this.validateRequest(request);

        // Yield to the event loop to model an asynchronous HTTP-processing path.
        await Promise.resolve();

        const candidates = this.routeCandidates(request);
        const sessionId = this.extractSessionId(request.headers);

        let backend;

        if (sessionId) {
            const existingName = this.sessionAffinity.get(sessionId);
            const existing = existingName ? this.backend(existingName) : null;

            if (existing && existing.isAvailable() && candidates.includes(existing)) {
                backend = existing;
            } else {
                backend = this.selectLeastConnections(candidates);
                this.sessionAffinity.set(sessionId, backend.name);
            }
        } else {
            backend = this.selectLeastConnections(candidates);
        }

        backend.requestsServed += 1;
        return backend;
    }
}

async function healthCheck(backends) {
    /*
     * A production implementation would perform an actual TCP or HTTP probe.
     * Promise-based checks make the failure model explicit without requiring
     * external packages.
     */
    return Promise.all(
        backends.map(
            async (backend) => ({
                backend: backend.name,
                healthy: backend.isAvailable()
            })
        )
    );
}

function printBackends(title, backends) {
    console.log(`\n${title}`);

    for (const backend of backends) {
        console.log(
            `${backend.name.padEnd(10)} ` +
            `state=${backend.state.padEnd(10)} ` +
            `connections=${String(backend.activeConnections).padStart(2)} ` +
            `requests=${String(backend.requestsServed).padStart(2)}`
        );
    }
}

async function main() {
    const l4Backends = [
        new Backend({ name: "api-1", address: "10.0.0.11", port: 443 }),
        new Backend({ name: "api-2", address: "10.0.0.12", port: 443 }),
        new Backend({ name: "api-3", address: "10.0.0.13", port: 443 })
    ];

    const l7Backends = [
        new Backend({ name: "api-1", address: "10.0.0.11", port: 8080 }),
        new Backend({ name: "api-2", address: "10.0.0.12", port: 8080 }),
        new Backend({ name: "static-1", address: "10.0.0.21", port: 8080 })
    ];

    console.log("L4 health:", await healthCheck(l4Backends));

    const l4 = new L4LoadBalancer(l4Backends);

    const a = l4.selectBackend(
        "192.168.1.10",
        50001,
        "203.0.113.10",
        443
    );

    const b = l4.selectBackend(
        "192.168.1.11",
        50002,
        "203.0.113.10",
        443
    );

    console.log(`L4 flow A -> ${a.name}`);
    console.log(`L4 flow B -> ${b.name}`);

    a.state = BackendState.UNHEALTHY;

    const recoveredFlow = l4.selectBackend(
        "192.168.1.10",
        50001,
        "203.0.113.10",
        443
    );

    console.log(`L4 failed-flow remap -> ${recoveredFlow.name}`);

    l4.closeConnection(
        "192.168.1.11",
        50002,
        "203.0.113.10",
        443
    );

    printBackends("L4 state", l4Backends);

    console.log("\nL7 health:", await healthCheck(l7Backends));

    const l7 = new L7LoadBalancer(l7Backends);

    const requests = [
        {
            method: "GET",
            host: "api.example.com",
            path: "/api/orders",
            headers: { Cookie: "SESSION_ID=customer-42" }
        },
        {
            method: "GET",
            host: "api.example.com",
            path: "/api/products",
            headers: { Cookie: "SESSION_ID=customer-42" }
        },
        {
            method: "GET",
            host: "cdn.example.com",
            path: "/static/app.js",
            headers: {}
        }
    ];

    for (const request of requests) {
        const backend = await l7.route(request);

        console.log(
            `L7 ${request.method} ${request.host}${request.path} -> ${backend.name}`
        );
    }

    l7Backends[0].state = BackendState.UNHEALTHY;

    const failover = await l7.route({
        method: "GET",
        host: "api.example.com",
        path: "/api/orders",
        headers: { Cookie: "SESSION_ID=customer-42" }
    });

    console.log(`L7 session failover -> ${failover.name}`);

    try {
        await l7.route({
            method: "TRACE",
            host: "api.example.com",
            path: "/api/admin",
            headers: {}
        });
    } catch (error) {
        console.log(`Validation failure handled: ${error.message}`);
    }

    printBackends("L7 state", l7Backends);

    console.log(
        "\nL4 uses transport-flow identity; L7 uses HTTP request semantics. " +
        "L7 enables path, host, header, and cookie routing but requires " +
        "application parsing and therefore a larger processing boundary."
    );
}

main().catch((error) => {
    console.error(`Fatal error: ${error.message}`);
    process.exitCode = 1;
});
