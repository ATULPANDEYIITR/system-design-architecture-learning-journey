"use strict";

/*
 * Cache eviction in Node.js.
 *
 * The implementation deliberately exposes mechanisms that are natural in
 * JavaScript: Map preserves insertion order, EventEmitter represents the
 * event-driven lifecycle, and async functions model an origin-data lookup.
 *
 * The policies are kept separate because LRU, LFU, FIFO, and TTL answer
 * different questions about which cached value should disappear.
 */

const { EventEmitter } = require("node:events");

const Policy = Object.freeze({
  LRU: "LRU",
  LFU: "LFU",
  FIFO: "FIFO",
  TTL: "TTL"
});

class CacheEntry {
  constructor(key, value, sequence, ttlMs = null) {
    this.key = key;
    this.value = value;
    this.sequence = sequence;
    this.insertedAt = Date.now();
    this.lastAccess = this.insertedAt;
    this.frequency = 1;
    this.expiresAt = ttlMs === null ? null : this.insertedAt + ttlMs;
  }

  isExpired(now = Date.now()) {
    return this.expiresAt !== null && now >= this.expiresAt;
  }
}

class EventedCache extends EventEmitter {
  constructor({ capacity, policy = Policy.LRU, defaultTtlMs = null } = {}) {
    super();

    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new RangeError("capacity must be a positive integer");
    }

    if (!Object.values(Policy).includes(policy)) {
      throw new Error(`Unknown policy: ${policy}`);
    }

    if (policy === Policy.TTL && (!Number.isFinite(defaultTtlMs) || defaultTtlMs <= 0)) {
      throw new RangeError("TTL caches require a positive defaultTtlMs");
    }

    this.capacity = capacity;
    this.policy = policy;
    this.defaultTtlMs = defaultTtlMs;
    this.entries = new Map();
    this.sequence = 0;
    this.hits = 0;
    this.misses = 0;
    this.evictions = 0;
  }

  purgeExpired() {
    const now = Date.now();

    for (const [key, entry] of this.entries) {
      if (entry.isExpired(now)) {
        this.entries.delete(key);
        this.evictions++;
        this.emit("expire", { key });
      }
    }
  }

  get(key) {
    this.purgeExpired();

    const entry = this.entries.get(key);

    if (!entry) {
      this.misses++;
      this.emit("miss", { key });
      return undefined;
    }

    entry.lastAccess = Date.now();
    entry.frequency++;
    this.hits++;
    this.emit("hit", { key });

    // Re-inserting into a Map changes insertion order. We do this only for
    // LRU because insertion order then becomes a useful recency structure.
    if (this.policy === Policy.LRU) {
      this.entries.delete(key);
      this.entries.set(key, entry);
    }

    return entry.value;
  }

  set(key, value, ttlMs = this.defaultTtlMs) {
    if (typeof key !== "string" || key.length === 0) {
      throw new TypeError("cache keys must be non-empty strings");
    }

    if (ttlMs !== null && (!Number.isFinite(ttlMs) || ttlMs <= 0)) {
      throw new RangeError("ttlMs must be positive");
    }

    this.purgeExpired();

    const existing = this.entries.get(key);

    if (existing) {
      existing.value = value;
      existing.lastAccess = Date.now();
      existing.frequency++;
      existing.expiresAt = ttlMs === null ? null : Date.now() + ttlMs;

      if (this.policy === Policy.LRU) {
        this.entries.delete(key);
        this.entries.set(key, existing);
      }

      this.emit("update", { key });
      return;
    }

    const entry = new CacheEntry(
      key,
      value,
      ++this.sequence,
      ttlMs
    );

    this.entries.set(key, entry);
    this.emit("set", { key });

    if (this.entries.size > this.capacity) {
      this.evict();
    }
  }

  selectVictim() {
    const entries = [...this.entries.values()];

    if (entries.length === 0) {
      return null;
    }

    if (this.policy === Policy.LRU) {
      return entries[0];
    }

    if (this.policy === Policy.FIFO) {
      return entries.reduce((oldest, entry) =>
        entry.sequence < oldest.sequence ? entry : oldest
      );
    }

    if (this.policy === Policy.LFU) {
      return entries.reduce((victim, entry) => {
        if (entry.frequency < victim.frequency) return entry;
        if (
          entry.frequency === victim.frequency &&
          entry.lastAccess < victim.lastAccess
        ) {
          return entry;
        }
        return victim;
      });
    }

    // TTL is expiration-oriented. The entry nearest to expiration has the
    // least remaining lifetime and is the safest capacity victim.
    return entries.reduce((victim, entry) => {
      const victimExpiry = victim.expiresAt ?? Infinity;
      const entryExpiry = entry.expiresAt ?? Infinity;
      return entryExpiry < victimExpiry ? entry : victim;
    });
  }

  evict() {
    this.purgeExpired();

    const victim = this.selectVictim();

    if (!victim) return;

    this.entries.delete(victim.key);
    this.evictions++;
    this.emit("evict", {
      key: victim.key,
      policy: this.policy
    });
  }

  delete(key) {
    const deleted = this.entries.delete(key);

    if (deleted) {
      this.emit("delete", { key });
    }

    return deleted;
  }

  size() {
    this.purgeExpired();
    return this.entries.size;
  }

  stats() {
    const requests = this.hits + this.misses;

    return {
      policy: this.policy,
      capacity: this.capacity,
      size: this.size(),
      hits: this.hits,
      misses: this.misses,
      hitRate: requests === 0 ? 0 : this.hits / requests,
      evictions: this.evictions
    };
  }
}

function demonstratePolicy(policy) {
  const cache = new EventedCache({
    capacity: 3,
    policy,
    defaultTtlMs: policy === Policy.TTL ? 5000 : null
  });

  cache.on("evict", event => {
    console.log(`[${policy}] evicted ${event.key}`);
  });

  cache.on("expire", event => {
    console.log(`[${policy}] expired ${event.key}`);
  });

  cache.set("document:1", "architecture");
  cache.set("document:2", "database");
  cache.set("document:3", "security");

  cache.get("document:1");
  cache.get("document:1");
  cache.get("document:2");

  cache.set("document:4", "operations");

  console.log(`${policy} ->`, cache.stats());
}

async function originLookup(productId) {
  // The asynchronous boundary represents a database or HTTP request.
  await new Promise(resolve => setTimeout(resolve, 10));
  return {
    id: productId,
    name: `Product ${productId}`,
    loadedAt: new Date().toISOString()
  };
}

class CachedProductService {
  constructor(cache) {
    this.cache = cache;
  }

  async getProduct(productId) {
    const key = `product:${productId}`;
    const cached = this.cache.get(key);

    if (cached !== undefined) {
      return { source: "cache", product: cached };
    }

    const product = await originLookup(productId);
    this.cache.set(key, product);
    return { source: "origin", product };
  }
}

async function demonstrateAsyncWorkload() {
  const cache = new EventedCache({
    capacity: 2,
    policy: Policy.LRU
  });

  const service = new CachedProductService(cache);

  console.log(await service.getProduct(10));
  console.log(await service.getProduct(10));
  console.log(await service.getProduct(20));
  console.log(await service.getProduct(30));
  console.log(cache.stats());
}

function demonstratePolicyDifferences() {
  for (const policy of [Policy.LRU, Policy.LFU, Policy.FIFO]) {
    demonstratePolicy(policy);
  }
}

async function main() {
  demonstratePolicyDifferences();
  await demonstrateAsyncWorkload();
}

main().catch(error => {
  console.error("Cache demonstration failed:", error.message);
  process.exitCode = 1;
});
