"use strict";

/*
 * Caching in JavaScript:
 * This program models a read-heavy catalog service where an in-memory cache
 * reduces repeated database work. It focuses on JavaScript-specific concerns:
 * Map insertion order, promises, event-loop behavior, asynchronous refresh,
 * request coalescing, deterministic keys, and object mutability.
 */

class TTLCache {
    constructor({ maxEntries = 100, defaultTtlMs = 30_000 } = {}) {
        if (!Number.isInteger(maxEntries) || maxEntries <= 0) {
            throw new TypeError("maxEntries must be a positive integer");
        }

        if (defaultTtlMs !== null && defaultTtlMs <= 0) {
            throw new TypeError("defaultTtlMs must be positive or null");
        }

        this.maxEntries = maxEntries;
        this.defaultTtlMs = defaultTtlMs;
        this.entries = new Map();
        this.stats = {
            hits: 0,
            misses: 0,
            writes: 0,
            evictions: 0,
            expirations: 0,
            invalidations: 0
        };
    }

    _expiry(ttlMs) {
        const ttl = ttlMs === undefined ? this.defaultTtlMs : ttlMs;
        return ttl === null ? null : Date.now() + ttl;
    }

    get(key) {
        const entry = this.entries.get(key);

        if (!entry) {
            this.stats.misses++;
            return undefined;
        }

        if (entry.expiresAt !== null && Date.now() >= entry.expiresAt) {
            this.entries.delete(key);
            this.stats.misses++;
            this.stats.expirations++;
            return undefined;
        }

        // Map.delete followed by Map.set moves the entry to the newest
        // position, which gives us an LRU-like ordering.
        this.entries.delete(key);
        this.entries.set(key, entry);

        this.stats.hits++;
        return entry.value;
    }

    set(key, value, { ttlMs, tags = [] } = {}) {
        if (typeof key !== "string" || key.length === 0) {
            throw new TypeError("cache key must be a non-empty string");
        }

        this.entries.delete(key);
        this.entries.set(key, {
            value,
            createdAt: Date.now(),
            expiresAt: this._expiry(ttlMs),
            tags: new Set(tags)
        });

        this.stats.writes++;

        while (this.entries.size > this.maxEntries) {
            const oldestKey = this.entries.keys().next().value;
            this.entries.delete(oldestKey);
            this.stats.evictions++;
        }
    }

    delete(key) {
        return this.entries.delete(key);
    }

    invalidateTag(tag) {
        let removed = 0;

        for (const [key, entry] of this.entries) {
            if (entry.tags.has(tag)) {
                this.entries.delete(key);
                removed++;
            }
        }

        this.stats.invalidations += removed;
        return removed;
    }

    clear() {
        this.entries.clear();
    }

    snapshot() {
        const requests = this.stats.hits + this.stats.misses;

        return {
            entries: this.entries.size,
            ...this.stats,
            hitRate: requests === 0 ? 0 : this.stats.hits / requests
        };
    }
}


class CatalogRepository {
    constructor() {
        this.products = new Map([
            ["P100", { id: "P100", name: "Network Router", price: 129.99, version: 1 }],
            ["P200", { id: "P200", name: "Security Gateway", price: 349.50, version: 1 }],
            ["P300", { id: "P300", name: "Cloud Monitoring Sensor", price: 89.00, version: 1 }]
        ]);

        this.readCount = 0;
    }

    async findById(id) {
        this.readCount++;

        // Simulates I/O. JavaScript does not block the process while the
        // Promise is waiting, allowing other event-loop work to continue.
        await new Promise(resolve => setTimeout(resolve, 20));

        const product = this.products.get(id);
        return product ? structuredClone(product) : null;
    }

    async updatePrice(id, price) {
        if (!Number.isFinite(price) || price <= 0) {
            throw new RangeError("price must be positive and finite");
        }

        const product = this.products.get(id);

        if (!product) {
            throw new Error(`Unknown product: ${id}`);
        }

        product.price = price;
        product.version++;
        return structuredClone(product);
    }
}


function canonicalKey(namespace, operation, parameters) {
    const normalized = Object.keys(parameters)
        .sort()
        .map(key => `${key}=${JSON.stringify(parameters[key])}`)
        .join("&");

    return `${namespace}:${operation}:${normalized}`;
}


class CachedCatalogService {
    constructor(repository, cache) {
        this.repository = repository;
        this.cache = cache;

        // Promise coalescing prevents several simultaneous cache misses from
        // launching duplicate repository requests for the same key.
        this.inFlight = new Map();
    }

    async getProduct(id) {
        const key = `product:${id}`;
        const cached = this.cache.get(key);

        if (cached !== undefined) {
            return structuredClone(cached);
        }

        if (this.inFlight.has(key)) {
            return structuredClone(await this.inFlight.get(key));
        }

        const request = this.repository.findById(id)
            .then(product => {
                if (product) {
                    this.cache.set(key, product, {
                        ttlMs: 30_000,
                        tags: [`product:${id}`, "catalog"]
                    });
                }
                return product;
            })
            .finally(() => {
                this.inFlight.delete(key);
            });

        this.inFlight.set(key, request);

        return structuredClone(await request);
    }

    async changePrice(id, price) {
        const updated = await this.repository.updatePrice(id, price);

        // Mutation and invalidation are coupled so that subsequent reads
        // cannot silently return the previous price indefinitely.
        this.cache.invalidateTag(`product:${id}`);

        return updated;
    }
}


async function demonstrateReadCaching() {
    console.log("\n=== Read caching ===");

    const repository = new CatalogRepository();
    const cache = new TTLCache({
        maxEntries: 16,
        defaultTtlMs: 60_000
    });

    const service = new CachedCatalogService(repository, cache);

    const first = await service.getProduct("P100");
    const second = await service.getProduct("P100");

    console.log("First:", first);
    console.log("Second:", second);
    console.log("Repository reads:", repository.readCount);
    console.log("Cache:", cache.snapshot());

    if (repository.readCount !== 1) {
        throw new Error("Expected the second read to come from cache");
    }
}


async function demonstrateConcurrentMisses() {
    console.log("\n=== Concurrent miss coalescing ===");

    const repository = new CatalogRepository();
    const cache = new TTLCache({ maxEntries: 8 });
    const service = new CachedCatalogService(repository, cache);

    const results = await Promise.all([
        service.getProduct("P200"),
        service.getProduct("P200"),
        service.getProduct("P200"),
        service.getProduct("P200")
    ]);

    console.log("Returned versions:", results.map(product => product.version));
    console.log("Repository reads:", repository.readCount);

    if (repository.readCount !== 1) {
        throw new Error("Promise coalescing failed");
    }
}


async function demonstrateInvalidation() {
    console.log("\n=== Mutation and invalidation ===");

    const repository = new CatalogRepository();
    const cache = new TTLCache({ maxEntries: 8 });
    const service = new CachedCatalogService(repository, cache);

    const oldValue = await service.getProduct("P200");

    await service.changePrice("P200", 399.00);

    const newValue = await service.getProduct("P200");

    console.log("Old price:", oldValue.price);
    console.log("New price:", newValue.price);

    if (oldValue.price === newValue.price) {
        throw new Error("Cache invalidation did not occur");
    }
}


async function demonstrateStaleWhileRevalidate() {
    console.log("\n=== Stale-while-revalidate policy ===");

    const repository = new CatalogRepository();
    const cache = new TTLCache({ maxEntries: 8 });

    const key = "catalog:featured";
    const staleWindowMs = 2_000;

    async function loadFeaturedCatalog() {
        const cached = cache.get(key);

        if (cached !== undefined) {
            return cached;
        }

        const fresh = await repository.findById("P300");

        cache.set(key, fresh, {
            ttlMs: 1_000,
            tags: ["featured"]
        });

        return fresh;
    }

    const first = await loadFeaturedCatalog();

    // In a production stale-while-revalidate cache, stale metadata would be
    // retained separately from hard-expiration metadata. This example models
    // the policy decision without hiding expiration behind a fake "fresh" hit.
    console.log("Initial featured value:", first);
    console.log("Stale window policy:", `${staleWindowMs} ms`);
}


function demonstrateMutableObjectRisk() {
    console.log("\n=== Mutable object risk ===");

    const cache = new TTLCache({ maxEntries: 4 });
    const product = {
        id: "P100",
        name: "Network Router",
        price: 129.99
    };

    cache.set("product:P100", product);

    const cachedReference = cache.get("product:P100");
    cachedReference.price = 0;

    const affected = cache.get("product:P100");

    console.log("Mutated cached value:", affected);

    // Application code should avoid exposing mutable shared references. A
    // defensive clone, immutable object, or serialization boundary can prevent
    // accidental mutation from one caller affecting later callers.
    cache.set("product:P100", structuredClone(product));
}


function demonstrateNegativeCaching() {
    console.log("\n=== Negative caching ===");

    const cache = new TTLCache({ maxEntries: 8 });
    const NOT_FOUND = Symbol("NOT_FOUND");

    cache.set("product:P404", NOT_FOUND, {
        ttlMs: 5_000,
        tags: ["negative"]
    });

    const result = cache.get("product:P404");

    console.log(
        "Cached absence prevents repeated lookup:",
        result === NOT_FOUND
    );
}


function demonstrateKeyDesign() {
    console.log("\n=== Cache key design ===");

    const a = canonicalKey(
        "search",
        "products",
        { region: "eu", limit: 20, active: true }
    );

    const b = canonicalKey(
        "search",
        "products",
        { active: true, limit: 20, region: "eu" }
    );

    console.log("Key A:", a);
    console.log("Key B:", b);
    console.log("Stable key:", a === b);

    if (a !== b) {
        throw new Error("Canonical key generation is inconsistent");
    }
}


async function demonstrateWhyCachingMatters() {
    console.log("\n=== Workload comparison ===");

    const repository = new CatalogRepository();
    const cache = new TTLCache({ maxEntries: 16 });
    const service = new CachedCatalogService(repository, cache);

    const requestIds = [
        "P100", "P100", "P100",
        "P200", "P200",
        "P300", "P300",
        "P100", "P200"
    ];

    for (const id of requestIds) {
        await service.getProduct(id);
    }

    console.log("Requests:", requestIds.length);
    console.log("Repository reads:", repository.readCount);
    console.log("Cache statistics:", cache.snapshot());
}


async function main() {
    console.log("Caching: performance through controlled reuse");

    demonstrateMutableObjectRisk();
    demonstrateNegativeCaching();
    demonstrateKeyDesign();

    await demonstrateReadCaching();
    await demonstrateConcurrentMisses();
    await demonstrateInvalidation();
    await demonstrateStaleWhileRevalidate();
    await demonstrateWhyCachingMatters();

    console.log("\nCaching is useful when the cost of regeneration is materially");
    console.log("greater than the cost of lookup and the freshness policy is acceptable.");
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
