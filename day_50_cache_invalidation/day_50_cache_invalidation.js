'use strict';

/*
 * Cache invalidation model for a Node.js runtime.
 *
 * The implementation demonstrates:
 * - cache-aside reads
 * - TTL expiration
 * - explicit invalidation after writes
 * - version-based freshness
 * - event-driven invalidation
 * - stale-while-revalidate
 *
 * No external packages are required.
 */

const { EventEmitter } = require('node:events');
const crypto = require('node:crypto');

class CacheEntry {
    constructor(value, version, expiresAt = null) {
        this.value = value;
        this.version = version;
        this.createdAt = Date.now();
        this.expiresAt = expiresAt;
    }

    isExpired(now = Date.now()) {
        return this.expiresAt !== null && now >= this.expiresAt;
    }
}

class MemoryCache {
    constructor(defaultTtlMs = null) {
        if (defaultTtlMs !== null && (!Number.isFinite(defaultTtlMs) || defaultTtlMs <= 0)) {
            throw new RangeError('defaultTtlMs must be positive');
        }

        this.defaultTtlMs = defaultTtlMs;
        this.entries = new Map();
    }

    set(key, value, options = {}) {
        this.validateKey(key);

        const ttlMs = options.ttlMs ?? this.defaultTtlMs;
        const version = options.version ?? 0;

        if (ttlMs !== null && (!Number.isFinite(ttlMs) || ttlMs <= 0)) {
            throw new RangeError('ttlMs must be positive');
        }

        if (!Number.isInteger(version) || version < 0) {
            throw new RangeError('version must be a non-negative integer');
        }

        const expiresAt = ttlMs === null ? null : Date.now() + ttlMs;
        this.entries.set(key, new CacheEntry(value, version, expiresAt));
    }

    get(key) {
        this.validateKey(key);

        const entry = this.entries.get(key);

        if (!entry) {
            return null;
        }

        if (entry.isExpired()) {
            this.entries.delete(key);
            return null;
        }

        return entry;
    }

    invalidate(key) {
        this.validateKey(key);
        return this.entries.delete(key);
    }

    invalidatePrefix(prefix) {
        if (typeof prefix !== 'string' || prefix.length === 0) {
            throw new TypeError('prefix must not be empty');
        }

        let removed = 0;

        for (const key of this.entries.keys()) {
            if (key.startsWith(prefix)) {
                this.entries.delete(key);
                removed++;
            }
        }

        return removed;
    }

    cleanup() {
        const now = Date.now();
        let removed = 0;

        for (const [key, entry] of this.entries) {
            if (entry.isExpired(now)) {
                this.entries.delete(key);
                removed++;
            }
        }

        return removed;
    }

    validateKey(key) {
        if (typeof key !== 'string' || key.trim().length === 0) {
            throw new TypeError('cache key must be a non-empty string');
        }
    }
}

class ProductStore {
    constructor() {
        this.products = new Map([
            [101, { id: 101, name: 'Keyboard', price: 2400, version: 1 }],
            [102, { id: 102, name: 'Monitor', price: 18500, version: 1 }]
        ]);
    }

    async get(id) {
        await delay(10);

        const product = this.products.get(id);

        if (!product) {
            throw new Error(`Product ${id} not found`);
        }

        return structuredClone(product);
    }

    async updatePrice(id, price) {
        if (!Number.isFinite(price) || price < 0) {
            throw new RangeError('price must be a non-negative finite number');
        }

        const product = this.products.get(id);

        if (!product) {
            throw new Error(`Product ${id} not found`);
        }

        product.price = price;
        product.version++;

        await delay(10);
        return structuredClone(product);
    }
}

class ProductCacheService extends EventEmitter {
    constructor(store) {
        super();
        this.store = store;
        this.cache = new MemoryCache(5000);
        this.refreshing = new Map();

        /*
         * An invalidation event decouples data mutation from cache policy.
         * A real distributed deployment would usually transport this event
         * through a broker rather than an in-process EventEmitter.
         */
        this.on('productChanged', ({ id }) => {
            this.cache.invalidate(`product:${id}`);
        });
    }

    async getProduct(id) {
        this.validateId(id);

        const key = `product:${id}`;
        const cached = this.cache.get(key);

        if (cached) {
            return cached.value;
        }

        const product = await this.store.get(id);

        this.cache.set(key, product, {
            version: product.version
        });

        return product;
    }

    async updatePrice(id, price) {
        this.validateId(id);

        const updated = await this.store.updatePrice(id, price);

        this.emit('productChanged', {
            id,
            version: updated.version
        });

        return updated;
    }

    async getVersionAware(id) {
        this.validateId(id);

        const key = `product:${id}`;
        const cached = this.cache.get(key);
        const current = await this.store.get(id);

        if (!cached || cached.version < current.version) {
            this.cache.set(key, current, {
                version: current.version
            });

            return current;
        }

        return cached.value;
    }

    async staleWhileRevalidate(id) {
        this.validateId(id);

        const key = `product:${id}`;
        const cached = this.cache.get(key);

        if (!cached) {
            return this.getProduct(id);
        }

        /*
         * Return the cached value immediately while only one background
         * refresh is allowed for the same key. This reduces stampedes.
         */
        if (!this.refreshing.has(key)) {
            const refresh = this.store.get(id)
                .then(product => {
                    const current = this.cache.get(key);

                    if (!current || product.version >= current.version) {
                        this.cache.set(key, product, {
                            version: product.version
                        });
                    }

                    return product;
                })
                .finally(() => {
                    this.refreshing.delete(key);
                });

            this.refreshing.set(key, refresh);
        }

        return cached.value;
    }

    validateId(id) {
        if (!Number.isInteger(id) || id <= 0) {
            throw new RangeError('id must be a positive integer');
        }
    }
}

function makeBoundedKey(namespace, value) {
    if (typeof namespace !== 'string' || namespace.length === 0) {
        throw new TypeError('namespace is required');
    }

    if (typeof value !== 'string' || value.length === 0) {
        throw new TypeError('value is required');
    }

    const digest = crypto
        .createHash('sha256')
        .update(value, 'utf8')
        .digest('hex')
        .slice(0, 24);

    return `${namespace}:${digest}`;
}

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
    const store = new ProductStore();
    const service = new ProductCacheService(store);

    console.log('First read:', await service.getProduct(101));
    console.log('Second read:', await service.getProduct(101));

    await service.updatePrice(101, 2600);
    console.log('After write invalidation:', await service.getProduct(101));

    console.log('Version-aware read:', await service.getVersionAware(101));

    const ttlCache = new MemoryCache();
    ttlCache.set('short-lived', 'value', { ttlMs: 50 });
    console.log('Before TTL expiry:', ttlCache.get('short-lived')?.value);

    await delay(70);
    console.log('After TTL expiry:', ttlCache.get('short-lived'));

    console.log(
        'Stale-while-revalidate:',
        await service.staleWhileRevalidate(101)
    );

    console.log(
        'Safe bounded key:',
        makeBoundedKey('customer', 'customer@example.com')
    );

    try {
        await service.updatePrice(999, -20);
    } catch (error) {
        console.error('Expected validation failure:', error.message);
    }
}

main().catch(error => {
    console.error('Fatal error:', error.message);
    process.exitCode = 1;
});
