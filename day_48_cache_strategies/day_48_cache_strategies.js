'use strict';

/*
 * Cache strategies implemented as an event-driven Node.js service model.
 *
 * The three strategies intentionally have different responsibilities:
 * cache-aside exposes cache population to the application service,
 * read-through lets the cache abstraction load missing data, and
 * write-through updates the persistent store and cache in one write path.
 */

class CacheMiss extends Error {
    constructor(message) {
        super(message);
        this.name = 'CacheMiss';
    }
}

class MemoryCache {
    constructor(name) {
        this.name = name;
        this.entries = new Map();
        this.metrics = {
            hits: 0,
            misses: 0,
            writes: 0,
            deletes: 0
        };
    }

    get(key) {
        const entry = this.entries.get(key);

        if (!entry) {
            this.metrics.misses++;
            return undefined;
        }

        if (entry.expiresAt !== null && Date.now() >= entry.expiresAt) {
            this.entries.delete(key);
            this.metrics.misses++;
            return undefined;
        }

        this.metrics.hits++;
        return entry.value;
    }

    set(key, value, ttlMs = null) {
        const expiresAt = ttlMs === null ? null : Date.now() + ttlMs;

        this.entries.set(key, {
            value,
            expiresAt
        });

        this.metrics.writes++;
    }

    delete(key) {
        if (this.entries.delete(key)) {
            this.metrics.deletes++;
        }
    }

    stats() {
        return {
            name: this.name,
            ...this.metrics,
            size: this.entries.size
        };
    }
}

class ProductRepository {
    constructor() {
        this.products = new Map([
            [101, {
                id: 101,
                name: 'Mechanical Keyboard',
                price: 89.99,
                stock: 42,
                version: 1
            }],
            [102, {
                id: 102,
                name: 'USB-C Dock',
                price: 129.50,
                stock: 17,
                version: 1
            }],
            [103, {
                id: 103,
                name: 'Noise-Cancelling Headphones',
                price: 199.00,
                stock: 9,
                version: 1
            }]
        ]);

        this.reads = 0;
        this.writes = 0;
    }

    async get(id) {
        this.reads++;
        await delay(8);

        const product = this.products.get(id);
        return product ? structuredClone(product) : null;
    }

    async save(product) {
        if (!Number.isInteger(product.id)) {
            throw new TypeError('Product ID must be an integer');
        }

        if (!Number.isFinite(product.price) || product.price < 0) {
            throw new RangeError('Product price must be non-negative');
        }

        if (!Number.isInteger(product.stock) || product.stock < 0) {
            throw new RangeError('Product stock must be a non-negative integer');
        }

        const current = this.products.get(product.id);
        const nextVersion = current ? current.version + 1 : 1;

        await delay(8);

        this.products.set(product.id, {
            ...structuredClone(product),
            version: nextVersion
        });

        this.writes++;
        return structuredClone(this.products.get(product.id));
    }
}

function delay(milliseconds) {
    return new Promise(resolve => setTimeout(resolve, milliseconds));
}

class CacheAsideService {
    constructor({ cache, repository, ttlMs = 30000 }) {
        this.cache = cache;
        this.repository = repository;
        this.ttlMs = ttlMs;
    }

    async getProduct(id) {
        const cached = this.cache.get(id);

        if (cached !== undefined) {
            return cached;
        }

        const product = await this.repository.get(id);

        if (product !== null) {
            this.cache.set(id, product, this.ttlMs);
        }

        return product;
    }

    async updateProduct(product) {
        const persisted = await this.repository.save(product);

        // Invalidating rather than blindly updating the cache prevents this
        // application service from assuming that every persistence layer
        // mutation has identical serialization semantics.
        this.cache.delete(product.id);

        return persisted;
    }
}

class ReadThroughCache {
    constructor({ cache, loader, ttlMs = 30000 }) {
        this.cache = cache;
        this.loader = loader;
        this.ttlMs = ttlMs;
    }

    async get(key) {
        const cached = this.cache.get(key);

        if (cached !== undefined) {
            return cached;
        }

        const value = await this.loader(key);

        if (value !== null && value !== undefined) {
            this.cache.set(key, value, this.ttlMs);
        }

        return value;
    }
}

class WriteThroughService {
    constructor({ cache, repository, ttlMs = 30000 }) {
        this.cache = cache;
        this.repository = repository;
        this.ttlMs = ttlMs;
    }

    async write(product) {
        // Persist first. If the database rejects the mutation, the cache is
        // not changed and cannot advertise a state that was never persisted.
        const persisted = await this.repository.save(product);
        this.cache.set(product.id, persisted, this.ttlMs);
        return persisted;
    }

    get(id) {
        return this.cache.get(id);
    }
}

class EventBus {
    constructor() {
        this.listeners = new Map();
    }

    on(eventName, listener) {
        if (!this.listeners.has(eventName)) {
            this.listeners.set(eventName, []);
        }

        this.listeners.get(eventName).push(listener);
    }

    emit(eventName, payload) {
        const listeners = this.listeners.get(eventName) ?? [];

        for (const listener of listeners) {
            listener(payload);
        }
    }
}

class ObservableReadThroughCache extends ReadThroughCache {
    constructor(options) {
        super(options);
        this.events = options.events;
    }

    async get(key) {
        const cached = this.cache.get(key);

        if (cached !== undefined) {
            this.events.emit('cache.hit', { key });
            return cached;
        }

        this.events.emit('cache.miss', { key });

        const value = await this.loader(key);

        if (value !== null && value !== undefined) {
            this.cache.set(key, value, this.ttlMs);
            this.events.emit('cache.populate', { key });
        }

        return value;
    }
}

async function demonstrateCacheAside() {
    console.log('\n=== Cache-aside ===');

    const repository = new ProductRepository();
    const cache = new MemoryCache('cache-aside');

    const service = new CacheAsideService({
        cache,
        repository,
        ttlMs: 1000
    });

    console.log('First read:', await service.getProduct(101));
    console.log('Second read:', await service.getProduct(101));

    await service.updateProduct({
        id: 101,
        name: 'Mechanical Keyboard',
        price: 94.99,
        stock: 40
    });

    console.log('Read after invalidation:', await service.getProduct(101));
    console.log('Cache metrics:', cache.stats());
    console.log('Repository reads:', repository.reads);
}

async function demonstrateReadThrough() {
    console.log('\n=== Read-through ===');

    const repository = new ProductRepository();
    const cache = new MemoryCache('read-through');

    const cacheLayer = new ReadThroughCache({
        cache,
        loader: id => repository.get(id),
        ttlMs: 1000
    });

    console.log('First read:', await cacheLayer.get(102));
    console.log('Second read:', await cacheLayer.get(102));
    console.log('Missing key:', await cacheLayer.get(999));

    console.log('Cache metrics:', cache.stats());
    console.log('Repository reads:', repository.reads);
}

async function demonstrateWriteThrough() {
    console.log('\n=== Write-through ===');

    const repository = new ProductRepository();
    const cache = new MemoryCache('write-through');

    const service = new WriteThroughService({
        cache,
        repository,
        ttlMs: 1000
    });

    const updated = await service.write({
        id: 103,
        name: 'Noise-Cancelling Headphones',
        price: 184.00,
        stock: 8
    });

    console.log('Persisted:', updated);
    console.log('Immediate cached read:', service.get(103));
    console.log('Repository writes:', repository.writes);
}

async function demonstrateEvents() {
    console.log('\n=== Event-driven cache observation ===');

    const repository = new ProductRepository();
    const cache = new MemoryCache('observable');
    const events = new EventBus();

    events.on('cache.hit', ({ key }) => {
        console.log(`cache.hit -> ${key}`);
    });

    events.on('cache.miss', ({ key }) => {
        console.log(`cache.miss -> ${key}`);
    });

    events.on('cache.populate', ({ key }) => {
        console.log(`cache.populate -> ${key}`);
    });

    const service = new ObservableReadThroughCache({
        cache,
        loader: id => repository.get(id),
        ttlMs: 1000,
        events
    });

    await service.get(101);
    await service.get(101);
}

async function demonstrateStampedeProtection() {
    console.log('\n=== Concurrent miss protection ===');

    const repository = new ProductRepository();
    const cache = new MemoryCache('stampede');

    const inFlight = new Map();

    async function protectedRead(id) {
        const cached = cache.get(id);

        if (cached !== undefined) {
            return cached;
        }

        if (inFlight.has(id)) {
            return inFlight.get(id);
        }

        const promise = repository.get(id)
            .then(product => {
                if (product !== null) {
                    cache.set(id, product, 1000);
                }
                return product;
            })
            .finally(() => {
                inFlight.delete(id);
            });

        inFlight.set(id, promise);
        return promise;
    }

    const results = await Promise.all([
        protectedRead(102),
        protectedRead(102),
        protectedRead(102),
        protectedRead(102)
    ]);

    console.log('Concurrent results:', results.length);
    console.log('Repository reads:', repository.reads);
    console.log(
        'One source read is expected because concurrent misses share one promise.'
    );
}

async function demonstrateTtl() {
    console.log('\n=== TTL ===');

    const cache = new MemoryCache('ttl');

    cache.set('token:42', 'active', 30);

    console.log('Immediately:', cache.get('token:42'));

    await delay(50);

    console.log('After expiration:', cache.get('token:42'));
    console.log('Metrics:', cache.stats());
}

async function demonstrateWriteFailure() {
    console.log('\n=== Write failure ===');

    const repository = new ProductRepository();
    const cache = new MemoryCache('write-failure');

    const service = new WriteThroughService({
        cache,
        repository
    });

    await service.write({
        id: 101,
        name: 'Mechanical Keyboard',
        price: 95,
        stock: 39
    });

    try {
        await service.write({
            id: 101,
            name: 'Mechanical Keyboard',
            price: -20,
            stock: 39
        });
    } catch (error) {
        console.log('Rejected:', error.message);
    }

    console.log('Cache remains:', service.get(101));
}

async function runAssertions() {
    const repository = new ProductRepository();
    const cache = new MemoryCache('assertions');

    const service = new CacheAsideService({
        cache,
        repository
    });

    const first = await service.getProduct(101);
    const second = await service.getProduct(101);

    if (first === null || second === null) {
        throw new Error('Existing product should be readable');
    }

    if (repository.reads !== 1) {
        throw new Error('Second cache-aside read should avoid source access');
    }

    await service.updateProduct({
        id: 101,
        name: 'Mechanical Keyboard',
        price: 97,
        stock: 37
    });

    const refreshed = await service.getProduct(101);

    if (refreshed.price !== 97) {
        throw new Error('Invalidation should expose the persisted value');
    }

    console.log('\nAll JavaScript assertions passed.');
}

async function main() {
    console.log('CACHE STRATEGIES');

    await demonstrateCacheAside();
    await demonstrateReadThrough();
    await demonstrateWriteThrough();
    await demonstrateEvents();
    await demonstrateStampedeProtection();
    await demonstrateTtl();
    await demonstrateWriteFailure();
    await runAssertions();
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exitCode = 1;
});
