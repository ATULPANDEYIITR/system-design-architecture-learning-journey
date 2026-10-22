"use strict";

/*
 * Cache Failure Patterns
 *
 * This Node.js implementation focuses on event-driven cache access:
 * - stampede prevention through per-key promise deduplication
 * - penetration protection through negative caching and key validation
 * - avalanche mitigation through TTL jitter and stale-while-revalidate
 *
 * No external packages are required.
 */

class CacheError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "CacheError";
    this.code = code;
  }
}

class AsyncCache {
  constructor({
    loader,
    ttlMs = 10_000,
    negativeTtlMs = 3_000,
    jitterRatio = 0.1,
    staleGraceMs = 2_000,
    keyPattern = /^[a-zA-Z0-9:_-]{1,100}$/,
  }) {
    if (typeof loader !== "function") {
      throw new TypeError("loader must be a function");
    }
    if (ttlMs <= 0 || negativeTtlMs <= 0) {
      throw new RangeError("TTLs must be positive");
    }
    if (jitterRatio < 0 || jitterRatio > 1) {
      throw new RangeError("jitterRatio must be between 0 and 1");
    }

    this.loader = loader;
    this.ttlMs = ttlMs;
    this.negativeTtlMs = negativeTtlMs;
    this.jitterRatio = jitterRatio;
    this.staleGraceMs = staleGraceMs;
    this.keyPattern = keyPattern;

    this.entries = new Map();
    this.inFlight = new Map();

    this.metrics = {
      hits: 0,
      misses: 0,
      backendReads: 0,
      negativeHits: 0,
      rejectedPenetration: 0,
      deduplicatedRequests: 0,
      refreshes: 0,
      failures: 0,
      staleServed: 0,
    };
  }

  validateKey(key) {
    if (typeof key !== "string" || !this.keyPattern.test(key)) {
      this.metrics.rejectedPenetration++;
      return false;
    }
    return true;
  }

  randomizedTtl(base) {
    const delta = base * this.jitterRatio;
    return Math.max(1, base + (Math.random() * 2 - 1) * delta);
  }

  readEntry(key) {
    const entry = this.entries.get(key);
    if (!entry) return null;

    const now = Date.now();

    if (entry.expiresAt > now) {
      return { state: "fresh", entry };
    }

    if (entry.expiresAt + this.staleGraceMs > now) {
      return { state: "stale", entry };
    }

    this.entries.delete(key);
    return null;
  }

  async get(key) {
    if (!this.validateKey(key)) {
      return null;
    }

    const cached = this.readEntry(key);

    if (cached?.state === "fresh") {
      this.metrics.hits++;
      if (cached.entry.value === null) this.metrics.negativeHits++;
      return cached.entry.value;
    }

    if (cached?.state === "stale") {
      this.metrics.staleServed++;
      this.metrics.hits++;

      // Refresh asynchronously. The caller receives the stale value instead
      // of becoming part of an expiration burst.
      this.refresh(key).catch(() => {});
      return cached.entry.value;
    }

    this.metrics.misses++;

    // A Promise stored per key acts as an event-loop-friendly single-flight
    // mechanism. All concurrent callers await the same backend operation.
    if (this.inFlight.has(key)) {
      this.metrics.deduplicatedRequests++;
      return this.inFlight.get(key);
    }

    const operation = this.refresh(key);
    this.inFlight.set(key, operation);

    try {
      return await operation;
    } finally {
      this.inFlight.delete(key);
    }
  }

  async refresh(key) {
    this.metrics.backendReads++;

    try {
      const value = await this.loader(key);
      const ttl = value === null ? this.negativeTtlMs : this.ttlMs;

      this.entries.set(key, {
        value,
        expiresAt: Date.now() + this.randomizedTtl(ttl),
      });

      this.metrics.refreshes++;
      return value;
    } catch (error) {
      this.metrics.failures++;
      throw new CacheError(
        `Backend read failed for ${key}: ${error.message}`,
        "BACKEND_FAILURE"
      );
    }
  }

  invalidate(key) {
    this.entries.delete(key);
  }

  clear() {
    this.entries.clear();
  }

  snapshot() {
    const requests = this.metrics.hits + this.metrics.misses;
    return {
      ...this.metrics,
      hitRate: requests === 0 ? 0 : this.metrics.hits / requests,
    };
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  const records = new Map([
    ["product:100", { name: "Keyboard", price: 49 }],
    ["product:101", { name: "Mouse", price: 29 }],
  ]);

  let backendReads = 0;

  const backend = async (key) => {
    backendReads++;
    await sleep(15);
    return records.has(key) ? records.get(key) : null;
  };

  const cache = new AsyncCache({
    loader: backend,
    ttlMs: 200,
    negativeTtlMs: 100,
    jitterRatio: 0.2,
    staleGraceMs: 300,
  });

  // Cache penetration: the missing object is negative-cached.
  await Promise.all(
    Array.from({ length: 50 }, () => cache.get("product:404"))
  );

  // Invalid keys are rejected before the backend.
  await Promise.all(
    Array.from({ length: 50 }, () => cache.get("../../database"))
  );

  // Cache stampede: many callers arrive after expiry. The in-flight Promise
  // ensures that only one backend refresh is active for the key.
  await cache.get("product:100");
  await sleep(230);

  await Promise.all(
    Array.from({ length: 100 }, () => cache.get("product:100"))
  );

  // Avalanche mitigation: different keys receive jittered expiration times.
  for (let i = 0; i < 100; i++) {
    records.set(`item:${i}`, { id: i });
    await cache.get(`item:${i}`);
  }

  console.log("CACHE FAILURE PATTERN MODEL");
  console.log("backend reads:", backendReads);
  console.table(cache.snapshot());

  // Explicit invalidation is preferable when a write changes the source of
  // truth and stale data is no longer acceptable.
  records.set("product:100", { name: "Keyboard Pro", price: 59 });
  cache.invalidate("product:100");

  const refreshed = await cache.get("product:100");
  console.log("after invalidation:", refreshed);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
