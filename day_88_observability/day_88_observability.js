"use strict";

/*
 * Observability, Structured Logging and Centralized Logging
 *
 * Node.js implementation emphasizing:
 * - Event-driven log ingestion
 * - AsyncLocalStorage context propagation
 * - Structured JSON events
 * - Centralized asynchronous processing
 * - Backpressure and bounded buffering
 * - Sensitive-field redaction
 * - Deduplication
 * - Policy-based alert evaluation
 * - Graceful shutdown
 */

const { EventEmitter } = require("node:events");
const { AsyncLocalStorage } = require("node:async_hooks");
const { randomUUID } = require("node:crypto");
const fs = require("node:fs/promises");

const SEVERITY = Object.freeze({
    DEBUG: 10,
    INFO: 20,
    WARN: 30,
    ERROR: 40,
    FATAL: 50
});

const SEVERITY_NAMES = Object.freeze({
    10: "DEBUG",
    20: "INFO",
    30: "WARN",
    40: "ERROR",
    50: "FATAL"
});

class ValidationError extends Error {
    constructor(message) {
        super(message);
        this.name = "ValidationError";
    }
}

class IngestionError extends Error {
    constructor(message) {
        super(message);
        this.name = "IngestionError";
    }
}

// ---------------------------------------------------------
// 1. Context propagation across asynchronous operations
// ---------------------------------------------------------

class ObservabilityContext {
    constructor() {
        this.storage = new AsyncLocalStorage();
    }

    run(context, callback) {
        return this.storage.run(
            Object.freeze({ ...context }),
            callback
        );
    }

    current() {
        return this.storage.getStore() || {};
    }
}

// ---------------------------------------------------------
// 2. Sensitive information handling
// ---------------------------------------------------------

class RedactionPolicy {
    constructor() {
        this.sensitiveKeys = new Set([
            "password",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "authorization",
            "api_key",
            "credit_card"
        ]);
    }

    sanitize(value, key = "", depth = 0) {
        if (depth > 12) {
            return "[MAX_DEPTH]";
        }

        if (this.sensitiveKeys.has(key.toLowerCase())) {
            return "[REDACTED]";
        }

        if (value === null || value === undefined) {
            return value === undefined ? null : value;
        }

        if (Array.isArray(value)) {
            return value.map(item =>
                this.sanitize(item, "", depth + 1)
            );
        }

        if (typeof value === "object") {
            const result = {};

            for (const [childKey, childValue] of Object.entries(value)) {
                result[childKey] = this.sanitize(
                    childValue,
                    childKey,
                    depth + 1
                );
            }

            return result;
        }

        if (typeof value === "string") {
            return value.replace(
                /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
                "[REDACTED_EMAIL]"
            );
        }

        return value;
    }
}

// ---------------------------------------------------------
// 3. Structured event factory
// ---------------------------------------------------------

class EventFactory {
    constructor(service, environment, version) {
        if (!service || !environment || !version) {
            throw new ValidationError(
                "Service, environment and version are required"
            );
        }

        this.service = service;
        this.environment = environment;
        this.version = version;
        this.redactor = new RedactionPolicy();
    }

    create(level, name, message, attributes = {}, context = {}) {
        if (!Object.hasOwn(SEVERITY, level)) {
            throw new ValidationError("Invalid log severity");
        }

        if (!name || typeof name !== "string") {
            throw new ValidationError("Event name is required");
        }

        if (typeof message !== "string") {
            throw new ValidationError("Message must be a string");
        }

        const safeAttributes = this.redactor.sanitize(attributes);

        return Object.freeze({
            timestamp: new Date().toISOString(),
            severity: level,
            severity_number: SEVERITY[level],
            service: this.service,
            environment: this.environment,
            version: this.version,
            event_name: name,
            message: this.redactor.sanitize(message),
            trace_id: context.traceId || randomUUID(),
            correlation_id: context.correlationId || randomUUID(),
            request_id: context.requestId || randomUUID(),
            attributes: safeAttributes
        });
    }
}

// ---------------------------------------------------------
// 4. Centralized event pipeline
// ---------------------------------------------------------

class CentralLogPipeline extends EventEmitter {
    constructor(options = {}) {
        super();

        this.maximumBuffer = options.maximumBuffer || 1000;
        this.maximumStored = options.maximumStored || 10000;

        if (
            !Number.isInteger(this.maximumBuffer) ||
            this.maximumBuffer <= 0 ||
            !Number.isInteger(this.maximumStored) ||
            this.maximumStored <= 0
        ) {
            throw new ValidationError("Invalid pipeline capacity");
        }

        this.queue = [];
        this.records = [];
        this.seenIds = new Set();
        this.processing = false;
        this.closed = false;
        this.dropped = 0;
    }

    publish(event) {
        if (this.closed) {
            throw new IngestionError("Pipeline is closed");
        }

        if (this.queue.length >= this.maximumBuffer) {
            this.dropped++;
            this.emit("backpressure", {
                queueSize: this.queue.length,
                dropped: this.dropped
            });

            throw new IngestionError("Log buffer capacity exceeded");
        }

        const id = [
            event.trace_id,
            event.request_id,
            event.event_name,
            event.timestamp
        ].join(":");

        if (this.seenIds.has(id)) {
            return false;
        }

        this.seenIds.add(id);

        this.queue.push({
            id,
            event
        });

        this.emit("accepted", event);

        return true;
    }

    async flush() {
        if (this.processing) {
            return;
        }

        this.processing = true;

        try {
            while (this.queue.length > 0) {
                const item = this.queue.shift();

                // Simulate an asynchronous transport boundary.
                await Promise.resolve();

                this.records.push(item.event);

                if (this.records.length > this.maximumStored) {
                    this.records.shift();
                }

                this.emit("ingested", item.event);
            }
        } finally {
            this.processing = false;
        }
    }

    query(filters = {}) {
        return this.records.filter(event => {
            if (
                filters.service &&
                event.service !== filters.service
            ) {
                return false;
            }

            if (
                filters.minimumSeverity &&
                event.severity_number <
                    SEVERITY[filters.minimumSeverity]
            ) {
                return false;
            }

            if (
                filters.traceId &&
                event.trace_id !== filters.traceId
            ) {
                return false;
            }

            if (
                filters.eventName &&
                event.event_name !== filters.eventName
            ) {
                return false;
            }

            return true;
        });
    }

    async exportFile(path) {
        if (typeof path !== "string" || !path.trim()) {
            throw new ValidationError("Export path is required");
        }

        await this.flush();

        const content = this.records
            .map(event => JSON.stringify(event))
            .join("\n");

        await fs.writeFile(path, content, {
            encoding: "utf8",
            mode: 0o600
        });
    }

    async close() {
        if (this.closed) {
            return;
        }

        await this.flush();
        this.closed = true;
        this.emit("closed");
    }
}

// ---------------------------------------------------------
// 5. Instrumented application
// ---------------------------------------------------------

class PaymentApplication {
    constructor(pipeline, contextStorage) {
        this.pipeline = pipeline;
        this.contextStorage = contextStorage;

        this.factory = new EventFactory(
            "payment-api",
            "production",
            "3.2.0"
        );
    }

    log(level, name, message, attributes = {}) {
        const context = this.contextStorage.current();

        const event = this.factory.create(
            level,
            name,
            message,
            attributes,
            context
        );

        this.pipeline.publish(event);
    }

    async processPayment(amount, options = {}) {
        const started = process.hrtime.bigint();

        this.log(
            "INFO",
            "payment.started",
            "Payment request received",
            { amount }
        );

        try {
            if (!Number.isFinite(amount) || amount <= 0) {
                throw new ValidationError(
                    "Amount must be a positive finite number"
                );
            }

            await Promise.resolve();

            if (options.simulateFailure) {
                throw new Error("Payment gateway unavailable");
            }

            const payment = {
                id: randomUUID(),
                amount,
                status: "COMPLETED"
            };

            const durationMs = Number(
                process.hrtime.bigint() - started
            ) / 1e6;

            this.log(
                "INFO",
                "payment.completed",
                "Payment completed",
                {
                    paymentId: payment.id,
                    durationMs: Number(durationMs.toFixed(3))
                }
            );

            return payment;
        } catch (error) {
            this.log(
                "ERROR",
                "payment.failed",
                "Payment processing failed",
                {
                    errorType: error.name,
                    errorMessage: error.message
                }
            );

            throw error;
        }
    }
}

// ---------------------------------------------------------
// 6. Metrics and alert policies
// ---------------------------------------------------------

class OperationalAnalytics {
    constructor(pipeline) {
        this.pipeline = pipeline;
    }

    summarize(service) {
        const events = this.pipeline.query({ service });

        const distribution = new Map();

        let errors = 0;

        for (const event of events) {
            distribution.set(
                event.event_name,
                (distribution.get(event.event_name) || 0) + 1
            );

            if (event.severity_number >= SEVERITY.ERROR) {
                errors++;
            }
        }

        return {
            service,
            totalEvents: events.length,
            errors,
            errorRate: events.length
                ? Number((errors / events.length).toFixed(4))
                : 0,
            distribution: Object.fromEntries(distribution)
        };
    }
}

class AlertPolicy {
    constructor(name, service, threshold, minimumEvents) {
        if (
            !Number.isFinite(threshold) ||
            threshold < 0 ||
            threshold > 1
        ) {
            throw new ValidationError("Invalid alert threshold");
        }

        if (!Number.isInteger(minimumEvents) || minimumEvents <= 0) {
            throw new ValidationError("Invalid minimum event count");
        }

        this.name = name;
        this.service = service;
        this.threshold = threshold;
        this.minimumEvents = minimumEvents;
    }

    evaluate(analytics) {
        const result = analytics.summarize(this.service);

        const firing =
            result.totalEvents >= this.minimumEvents &&
            result.errorRate >= this.threshold;

        return {
            rule: this.name,
            ...result,
            status: firing ? "FIRING" : "NORMAL"
        };
    }
}

// ---------------------------------------------------------
// 7. End-to-end execution
// ---------------------------------------------------------

async function main() {
    const contextStorage = new ObservabilityContext();

    const pipeline = new CentralLogPipeline({
        maximumBuffer: 100,
        maximumStored: 5000
    });

    pipeline.on("backpressure", event => {
        process.stderr.write(
            `Backpressure detected: ${JSON.stringify(event)}\n`
        );
    });

    pipeline.on("ingested", event => {
        if (event.severity_number >= SEVERITY.ERROR) {
            process.stderr.write(
                `ERROR EVENT: ${JSON.stringify(event)}\n`
            );
        }
    });

    const application = new PaymentApplication(
        pipeline,
        contextStorage
    );

    const context = {
        traceId: randomUUID(),
        correlationId: "order-2026-1001",
        requestId: randomUUID()
    };

    await contextStorage.run(context, async () => {
        await application.processPayment(1500);

        try {
            await application.processPayment(
                700,
                { simulateFailure: true }
            );
        } catch {
            // The failure is recorded by the application.
        }

        try {
            await application.processPayment(0);
        } catch {
            // Validation failure is recorded.
        }

        application.log(
            "WARN",
            "authentication.failure",
            "Invalid login for analyst@example.com",
            {
                username: "analyst",
                password: "sample-secret",
                access_token: "private-token"
            }
        );
    });

    // Process buffered events before reporting.
    await pipeline.flush();

    const analytics = new OperationalAnalytics(pipeline);

    console.log("\nCENTRALIZED LOG REPORT");

    console.log(
        JSON.stringify(
            analytics.summarize("payment-api"),
            null,
            2
        )
    );

    const alert = new AlertPolicy(
        "payment-failure-rate",
        "payment-api",
        0.25,
        3
    );

    console.log("\nALERT EVALUATION");

    console.log(
        JSON.stringify(alert.evaluate(analytics), null, 2)
    );

    console.log("\nTRACE SEARCH");

    const correlated = pipeline.query({
        traceId: context.traceId
    });

    console.log(`Trace events: ${correlated.length}`);

    const securityEvents = pipeline.query({
        eventName: "authentication.failure"
    });

    if (securityEvents.length !== 1) {
        throw new Error("Security event ingestion failed");
    }

    const securityEvent = securityEvents[0];

    if (
        securityEvent.attributes.password !== "[REDACTED]" ||
        securityEvent.attributes.access_token !== "[REDACTED]"
    ) {
        throw new Error("Sensitive-data redaction failed");
    }

    if (securityEvent.trace_id !== context.traceId) {
        throw new Error("Trace context propagation failed");
    }

    console.log("\nValidation successful.");

    await pipeline.close();
}

main().catch(error => {
    process.stderr.write(
        `Fatal execution error: ${error.stack || error.message}\n`
    );

    process.exitCode = 1;
});
