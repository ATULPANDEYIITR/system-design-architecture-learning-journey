'use strict';

/*
 * Distributed cache simulation.
 *
 * The implementation focuses on cache-aside behavior, consistent hashing,
 * TTL-based expiration, invalidation, node health, asynchronous loading,
 * and event-driven observability.
 */

const crypto = require('crypto');
const { EventEmitter } = require('events');

class CacheError extends Error {}
class CacheUnavailable extends CacheError {}

class CacheNode extends EventEmitter {
    constructor(name, backend, capacity = 100) {
        super();

        if (!name || !backend) {
            throw new TypeError('Cache node requires a name and backend');
        }

        this.name = name;
        this.backend = backend;
        this.capacity = capacity;
        this.healthy = true;
        this.entries = new Map();
        this.hits = 0;
        this.misses = 0;
    }

    _hashForEviction() {
        let candidate = null;
        let oldest = Infinity;

        for (const [key, entry] of this.entries) {
            const expiry = entry.expiresAt ?? Infinity;
            if (expiry < oldest) {
                oldest = expiry;
                candidate = key;
            }
        }

        return candidate;
    }

    async get(key) {
        if (!this.healthy) {
            throw new CacheUnavailable(`${this.name} is unavailable`);
        }

        const entry = this.entries.get(key);

        if (!entry) {
            this.misses++;
            this.emit('miss', { node: this.name, key });
            return undefined;
        }

        if (entry.expiresAt !== null && Date.now() >= entry.expiresAt) {
            this.entries.delete(key);
            this.misses++;
            this.emit('expired', { node: this.name, key });
            return undefined;
        }

        this.hits++;
        this.emit('hit', { node: this.name, key });
        return entry.value;
    }

    async set(key, value, ttlMs = 30000) {
        if (!this.healthy) {
            throw new CacheUnavailable(`${this.name} is unavailable`);
        }

        if (!Number.isFinite(ttlMs) || ttlMs <= 0) {
            throw new RangeError('TTL must be positive');
        }

        if (this.entries.size >= this.capacity && !this.entries.has(key)) {
            const victim = this._hashForEviction();
            if (victim !== null) {
                this.entries.delete(victim);
            }
        }

        const current = this.entries.get(key);

        this.entries.set(key, {
            value,
            version: (current?.version ?? 0) + 1,
            expiresAt: Date.now() + ttlMs
        });

        this.emit('set', { node: this.name, key });
    }

    async delete(key) {
        if (!this.healthy) {
            throw new CacheUnavailable(`${this.name} is unavailable`);
        }

        this.entries.delete(key);
        this.emit('delete', { node: this.name, key });
    }
}

class ConsistentHashRing {
    constructor(nodes = [], replicas = 64) {
        if (!Number.isInteger(replicas) || replicas < 1) {
            throw new RangeError('replicas must be a positive integer');
        }

        this.replicas = replicas;
        this.nodes = new Map();
        this.points = [];

        for (const node of nodes) {
            this.addNode(node);
        }
    }

    static hash(value) {
        const digest = crypto
            .createHash('sha256')
            .update(value)
            .digest();

        return digest.readBigUInt64BE(0);
    }

    rebuild() {
        this.points = [];

        for (const name of this.nodes.keys()) {
            for (let replica = 0; replica < this.replicas; replica++) {
                this.points.push({
                    point: ConsistentHashRing.hash(`${name}:${replica}`),
                    name
                });
            }
        }

        this.points.sort((a, b) =>
            a.point < b.point ? -1 : a.point > b.point ? 1 : 0
        );
    }

    addNode(node) {
        this.nodes.set(node.name, node);
        this.rebuild();
    }

    removeNode(name) {
        if (this.nodes.size === 1) {
            throw new Error('Cannot remove the last cache node');
        }

        this.nodes.delete(name);
        this.rebuild();
    }

    locate(key) {
        if (this.points.length === 0) {
            throw new CacheUnavailable('No cache nodes exist');
        }

        const target = ConsistentHashRing.hash(key);

        let low = 0;
        let high = this.points.length - 1;

        while (low <= high) {
            const middle = Math.floor((low + high) / 2);

            if (this.points[middle].point >= target) {
                high = middle - 1;
            } else {
                low = middle + 1;
            }
        }

        const index = low < this.points.length ? low : 0;
        return this.nodes.get(this.points[index].name);
    }
}

class DistributedCache {
    constructor(nodes) {
        this.ring = new ConsistentHashRing(nodes);
    }

    async get(key) {
        const node = this.ring.locate(key);

        try {
            return await node.get(key);
        } catch (error) {
            if (error instanceof CacheUnavailable) {
                return undefined;
            }
            throw error;
        }
    }

    async getOrLoad(key, loader, ttlMs = 30000) {
        if (typeof key !== 'string' || key.trim() === '') {
            throw new TypeError('Cache key must be a non-empty string');
        }

        const cached = await this.get(key);
        if (cached !== undefined) {
            return cached;
        }

        const value = await loader();

        if (value === undefined || value === null) {
            throw new Error('Loader returned an invalid cache value');
        }

        const node = this.ring.locate(key);

        try {
            await node.set(key, value, ttlMs);
        } catch (error) {
            if (!(error instanceof CacheUnavailable)) {
                throw error;
            }
        }

        return value;
    }

    async invalidate(key) {
        const node = this.ring.locate(key);

        try {
            await node.delete(key);
        } catch (error) {
            if (!(error instanceof CacheUnavailable)) {
                throw error;
            }
        }
    }

    statistics() {
        return Object.fromEntries(
            [...this.ring.nodes.values()].map(node => [
                node.name,
                {
                    backend: node.backend,
                    hits: node.hits,
                    misses: node.misses,
                    entries: node.entries.size
                }
            ])
        );
    }
}

class ProductRepository {
    constructor() {
        this.products = new Map([
            ['p100', { id: 'p100', name: 'Edge Router', price: 249 }],
            ['p200', { id: 'p200', name: 'Storage Node', price: 799 }]
        ]);
    }

    async findById(id) {
        await new Promise(resolve => setTimeout(resolve, 25));

        const product = this.products.get(id);

        if (!product) {
            throw new Error(`Product ${id} not found`);
        }

        return structuredClone(product);
    }

    async updatePrice(id, price) {
        if (!Number.isFinite(price) || price < 0) {
            throw new RangeError('Price must be a non-negative number');
        }

        const product = this.products.get(id);

        if (!product) {
            throw new Error(`Product ${id} not found`);
        }

        product.price = price;
    }
}

async function main() {
    const repository = new ProductRepository();

    const nodes = [
        new CacheNode('redis-a', 'redis', 20),
        new CacheNode('redis-b', 'redis', 20),
        new CacheNode('memcached-a', 'memcached', 20)
    ];

    for (const node of nodes) {
        node.on('hit', event => {
            console.log(`CACHE HIT ${event.node} ${event.key}`);
        });

        node.on('miss', event => {
            console.log(`CACHE MISS ${event.node} ${event.key}`);
        });
    }

    const cache = new DistributedCache(nodes);

    const key = 'product:p100';

    const first = await cache.getOrLoad(
        key,
        () => repository.findById('p100'),
        2000
    );

    const second = await cache.getOrLoad(
        key,
        () => repository.findById('p100'),
        2000
    );

    console.log('First:', first);
    console.log('Second:', second);

    // Writes update the source of truth first, then invalidate the cached copy.
    await repository.updatePrice('p100', 299);
    await cache.invalidate(key);

    const refreshed = await cache.getOrLoad(
        key,
        () => repository.findById('p100'),
        2000
    );

    console.log('Refreshed:', refreshed);

    // A cache node failure does not prevent authoritative reads.
    const failedNode = cache.ring.locate('product:p200');
    failedNode.healthy = false;

    const fallback = await cache.getOrLoad(
        'product:p200',
        () => repository.findById('p200'),
        2000
    );

    console.log('Fallback:', fallback);

    failedNode.healthy = true;

    // Measure how many keys change ownership after scaling.
    const before = new Map();

    for (let i = 0; i < 100; i++) {
        const keyName = `product:${i}`;
        before.set(keyName, cache.ring.locate(keyName).name);
    }

    cache.ring.addNode(new CacheNode('redis-c', 'redis', 20));

    let remapped = 0;

    for (const [keyName, oldNode] of before) {
        if (cache.ring.locate(keyName).name !== oldNode) {
            remapped++;
        }
    }

    console.log(`Remapped keys: ${remapped}/${before.size}`);
    console.log('Statistics:', cache.statistics());
}

main().catch(error => {
    console.error('Application failure:', error.message);
    process.exitCode = 1;
});
