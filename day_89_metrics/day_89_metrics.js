"use strict";

/*
 * Metrics engineering system.
 * Counters, gauges, histograms, event-driven instrumentation,
 * rolling-window SLIs, asynchronous collection and export.
 *
 * Runtime: Node.js 18+
 */

const { EventEmitter } = require("node:events");
const fs = require("node:fs/promises");

class MetricsError extends Error {}

class ValidationError extends MetricsError {}

function validateMetricName(name) {
    if (
        typeof name !== "string" ||
        !/^[a-zA-Z_:][a-zA-Z0-9_:]*$/.test(name)
    ) {
        throw new ValidationError(`Invalid metric name: ${name}`);
    }
}

function validateLabels(labels = {}) {
    if (
        labels === null ||
        typeof labels !== "object" ||
        Array.isArray(labels)
    ) {
        throw new ValidationError("Labels must be an object.");
    }

    const entries = Object.entries(labels);

    if (entries.length > 10) {
        throw new ValidationError("Too many labels.");
    }

    for (const [key, value] of entries) {
        validateMetricName(key);

        if (typeof value !== "string" || value.length > 128) {
            throw new ValidationError("Invalid label value.");
        }
    }

    return JSON.stringify(
        entries.sort(([a], [b]) => a.localeCompare(b))
    );
}

function finiteNumber(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        throw new ValidationError("A finite number is required.");
    }
}

class Metric {
    constructor(name, description, labelNames = []) {
        validateMetricName(name);

        if (!Array.isArray(labelNames)) {
            throw new ValidationError("Label names must be an array.");
        }

        this.name = name;
        this.description = description;
        this.labelNames = [...new Set(labelNames)];

        if (this.labelNames.length !== labelNames.length) {
            throw new ValidationError("Duplicate label names.");
        }

        for (const label of this.labelNames) {
            validateMetricName(label);
        }
    }

    labelKey(labels = {}) {
        if (
            Object.keys(labels).sort().join(",") !==
            [...this.labelNames].sort().join(",")
        ) {
            throw new ValidationError(
                `Incorrect labels for ${this.name}`
            );
        }

        return validateLabels(labels);
    }
}

class Counter extends Metric {
    constructor(name, description, labelNames = []) {
        super(name, description, labelNames);
        this.values = new Map();
    }

    inc(amount = 1, labels = {}) {
        finiteNumber(amount);

        if (amount <= 0) {
            throw new ValidationError(
                "Counter increments must be positive."
            );
        }

        const key = this.labelKey(labels);
        const next = (this.values.get(key) || 0) + amount;

        this.values.set(key, next);
        return next;
    }

    get(labels = {}) {
        return this.values.get(this.labelKey(labels)) || 0;
    }

    snapshot() {
        return Object.fromEntries(this.values);
    }
}

class Gauge extends Metric {
    constructor(name, description, labelNames = []) {
        super(name, description, labelNames);
        this.values = new Map();
    }

    set(value, labels = {}) {
        finiteNumber(value);
        const key = this.labelKey(labels);
        this.values.set(key, value);
        return value;
    }

    inc(amount = 1, labels = {}) {
        finiteNumber(amount);
        const key = this.labelKey(labels);
        return this.set(
            (this.values.get(key) || 0) + amount,
            labels
        );
    }

    dec(amount = 1, labels = {}) {
        finiteNumber(amount);
        return this.inc(-amount, labels);
    }

    get(labels = {}) {
        return this.values.get(this.labelKey(labels)) || 0;
    }

    snapshot() {
        return Object.fromEntries(this.values);
    }
}

class Histogram extends Metric {
    constructor(name, description, buckets, labelNames = []) {
        super(name, description, labelNames);

        if (
            !Array.isArray(buckets) ||
            buckets.length === 0 ||
            buckets.some(
                (v, i) =>
                    !Number.isFinite(v) ||
                    v <= 0 ||
                    (i > 0 && v <= buckets[i - 1])
            )
        ) {
            throw new ValidationError(
                "Histogram buckets must be positive and sorted."
            );
        }

        this.buckets = [...buckets];
        this.series = new Map();
    }

    observe(value, labels = {}) {
        finiteNumber(value);

        if (value < 0) {
            throw new ValidationError(
                "Negative observations are not supported."
            );
        }

        const key = this.labelKey(labels);

        if (!this.series.has(key)) {
            this.series.set(key, {
                count: 0,
                sum: 0,
                buckets: this.buckets.map(() => 0),
                values: []
            });
        }

        const series = this.series.get(key);

        series.count++;
        series.sum += value;

        // Cumulative bucket counters support threshold queries.
        this.buckets.forEach((bound, index) => {
            if (value <= bound) {
                series.buckets[index]++;
            }
        });

        // Retain bounded samples for local percentile estimation.
        series.values.push(value);

        if (series.values.length > 10000) {
            series.values.shift();
        }
    }

    snapshot(labels = {}) {
        const key = this.labelKey(labels);
        const series = this.series.get(key);

        if (!series) {
            return {
                count: 0,
                sum: 0,
                buckets: {}
            };
        }

        return {
            count: series.count,
            sum: series.sum,
            buckets: Object.fromEntries(
                this.buckets.map((bound, index) => [
                    bound,
                    series.buckets[index]
                ])
            ),
            infinity: series.count
        };
    }

    percentile(quantile, labels = {}) {
        if (quantile < 0 || quantile > 1) {
            throw new ValidationError("Invalid quantile.");
        }

        const series = this.series.get(this.labelKey(labels));

        if (!series || series.values.length === 0) {
            return null;
        }

        const sorted = [...series.values].sort((a, b) => a - b);
        const index = Math.max(
            0,
            Math.ceil(quantile * sorted.length) - 1
        );

        return sorted[index];
    }
}

class Registry {
    constructor() {
        this.metrics = new Map();
    }

    register(metric) {
        if (!(metric instanceof Metric)) {
            throw new ValidationError("Invalid metric instance.");
        }

        if (this.metrics.has(metric.name)) {
            throw new ValidationError(
                `Duplicate metric: ${metric.name}`
            );
        }

        this.metrics.set(metric.name, metric);
        return metric;
    }

    get(name) {
        const metric = this.metrics.get(name);

        if (!metric) {
            throw new MetricsError(`Metric not found: ${name}`);
        }

        return metric;
    }

    snapshot() {
        return Object.fromEntries(
            [...this.metrics].map(([name, metric]) => [
                name,
                metric.snapshot()
            ])
        );
    }

    async exportJSON(filename) {
        const content = JSON.stringify(this.snapshot(), null, 2);
        const temporary = `${filename}.tmp`;

        await fs.writeFile(temporary, content, {
            encoding: "utf8",
            mode: 0o600
        });

        await fs.rename(temporary, filename);
    }
}

class SLIWindow {
    constructor(name, target, windowMilliseconds) {
        if (target < 0 || target > 1) {
            throw new ValidationError("Invalid SLI target.");
        }

        if (!Number.isFinite(windowMilliseconds) ||
            windowMilliseconds <= 0) {
            throw new ValidationError("Invalid window.");
        }

        this.name = name;
        this.target = target;
        this.windowMilliseconds = windowMilliseconds;
        this.events = [];
    }

    record(good, timestamp = Date.now()) {
        if (
            typeof good !== "boolean" ||
            !Number.isFinite(timestamp)
        ) {
            throw new ValidationError("Invalid SLI event.");
        }

        this.events.push({
            good,
            timestamp
        });

        this.prune(timestamp);
    }

    prune(now = Date.now()) {
        const cutoff = now - this.windowMilliseconds;

        // Retain only events inside the configured evaluation window.
        let firstValid = 0;

        while (
            firstValid < this.events.length &&
            this.events[firstValid].timestamp < cutoff
        ) {
            firstValid++;
        }

        if (firstValid > 0) {
            this.events.splice(0, firstValid);
        }
    }

    evaluate(now = Date.now()) {
        this.prune(now);

        const total = this.events.length;
        const good = this.events.filter(e => e.good).length;

        const value = total === 0 ? null : good / total;

        return {
            name: this.name,
            good,
            total,
            value,
            target: this.target,
            passed: value === null ? null : value >= this.target
        };
    }
}

class ServiceInstrumentation extends EventEmitter {
    constructor() {
        super();

        this.registry = new Registry();

        this.requests = this.registry.register(
            new Counter(
                "http_requests_total",
                "Total HTTP requests.",
                ["method", "status"]
            )
        );

        this.active = this.registry.register(
            new Gauge(
                "http_active_requests",
                "Active HTTP requests."
            )
        );

        this.latency = this.registry.register(
            new Histogram(
                "http_request_duration_seconds",
                "Request duration in seconds.",
                [0.05, 0.1, 0.25, 0.5, 1, 2, 5],
                ["method"]
            )
        );

        this.availability = new SLIWindow(
            "availability",
            0.999,
            60 * 60 * 1000
        );

        this.on("request.completed", event => {
            this.requests.inc(1, {
                method: event.method,
                status: String(event.status)
            });

            this.latency.observe(
                event.duration,
                { method: event.method }
            );

            this.availability.record(
                event.status < 500,
                event.timestamp
            );
        });
    }

    async instrument(method, operation) {
        if (
            !["GET", "POST", "PUT", "DELETE", "PATCH"]
                .includes(method)
        ) {
            throw new ValidationError("Unsupported method.");
        }

        if (typeof operation !== "function") {
            throw new ValidationError("Operation must be callable.");
        }

        this.active.inc();

        const start = process.hrtime.bigint();
        let status = 500;

        try {
            const result = await operation();
            status = result?.status ?? 200;
            return result;
        } catch (error) {
            this.emit("request.failed", {
                method,
                error: error.message
            });

            throw error;
        } finally {
            const elapsed =
                Number(process.hrtime.bigint() - start) / 1e9;

            this.active.dec();

            this.emit("request.completed", {
                method,
                status,
                duration: elapsed,
                timestamp: Date.now()
            });
        }
    }
}

async function main() {
    const service = new ServiceInstrumentation();

    service.on("request.failed", event => {
        console.error("Request failure:", event);
    });

    await service.instrument("GET", async () => {
        await new Promise(resolve => setTimeout(resolve, 20));
        return { status: 200, body: "OK" };
    });

    await service.instrument("POST", async () => {
        return { status: 201 };
    });

    try {
        await service.instrument("GET", async () => {
            throw new Error("Database unavailable");
        });
    } catch {
        // Failure is recorded while the original exception propagates.
    }

    console.log("METRIC SNAPSHOT");
    console.log(
        JSON.stringify(service.registry.snapshot(), null, 2)
    );

    console.log(
        "AVAILABILITY SLI",
        service.availability.evaluate()
    );

    console.log(
        "GET P95",
        service.latency.percentile(
            0.95,
            { method: "GET" }
        )
    );

    await service.registry.exportJSON("metrics_snapshot.json");
}

if (require.main === module) {
    main().catch(error => {
        console.error("Fatal metrics error:", error);
        process.exitCode = 1;
    });
}

module.exports = {
    Counter,
    Gauge,
    Histogram,
    Registry,
    SLIWindow,
    ServiceInstrumentation,
    ValidationError
};
