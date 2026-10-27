'use strict';

/*
 * Content Delivery Network policy and event-driven simulation.
 *
 * The model separates:
 *   - geographic edge selection
 *   - cache state
 *   - origin retrieval
 *   - cache policy
 *   - invalidation
 *   - health state
 *   - asynchronous request handling
 *
 * Node.js standard-library APIs are sufficient.
 */

const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');

const CacheStatus = Object.freeze({
  HIT: 'HIT',
  MISS: 'MISS',
  STALE: 'STALE',
  BYPASS: 'BYPASS',
  ORIGIN_ERROR: 'ORIGIN_ERROR'
});

const EdgeState = Object.freeze({
  HEALTHY: 'HEALTHY',
  DEGRADED: 'DEGRADED',
  OFFLINE: 'OFFLINE'
});

class Content {
  constructor({ path, body, contentType, version, cacheable = true, ttlSeconds = 30 }) {
    if (!path.startsWith('/') || path.includes('..') || path.length > 2048) {
      throw new Error('Invalid content path');
    }
    if (!Number.isInteger(ttlSeconds) || ttlSeconds < 0) {
      throw new Error('TTL must be a non-negative integer');
    }

    this.path = path;
    this.body = body;
    this.contentType = contentType;
    this.version = version;
    this.cacheable = cacheable;
    this.ttlSeconds = ttlSeconds;
    this.etag = crypto
      .createHash('sha256')
      .update(`${version}:${body}`)
      .digest('hex');
  }
}

class OriginServer {
  constructor() {
    this.contents = new Map();
    this.available = true;
  }

  publish(path, body, contentType, options = {}) {
    const previous = this.contents.get(path);
    const version = previous ? previous.version + 1 : 1;

    const content = new Content({
      path,
      body,
      contentType,
      version,
      cacheable: options.cacheable !== false,
      ttlSeconds: options.ttlSeconds ?? 30
    });

    this.contents.set(path, content);
    return content;
  }

  async fetch(path) {
    // Promise-based boundary represents network I/O.
    await new Promise(resolve => setImmediate(resolve));

    if (!this.available) {
      throw new Error('Origin unavailable');
    }

    const content = this.contents.get(path);
    if (!content) {
      const error = new Error(`Content not found: ${path}`);
      error.code = 'NOT_FOUND';
      throw error;
    }

    return content;
  }
}

class EdgeServer {
  constructor(id, region, capacity, latencyMs) {
    if (capacity < 1) throw new Error('Cache capacity must be positive');

    this.id = id;
    this.region = region;
    this.capacity = capacity;
    this.latencyMs = latencyMs;
    this.state = EdgeState.HEALTHY;
    this.cache = new Map();
    this.hits = 0;
    this.misses = 0;
    this.stale = 0;
    this.evictions = 0;
  }

  lookup(path, now) {
    const entry = this.cache.get(path);

    if (!entry) {
      this.misses++;
      return { status: CacheStatus.MISS };
    }

    if (now - entry.storedAt >= entry.content.ttlSeconds * 1000) {
      this.cache.delete(path);
      this.stale++;
      return { status: CacheStatus.STALE };
    }

    // Map insertion order is used as a small LRU implementation.
    this.cache.delete(path);
    this.cache.set(path, entry);
    this.hits++;

    return {
      status: CacheStatus.HIT,
      content: entry.content
    };
  }

  store(content, now) {
    if (!content.cacheable || this.state === EdgeState.OFFLINE) return;

    this.cache.delete(content.path);
    this.cache.set(content.path, {
      content,
      storedAt: now
    });

    while (this.cache.size > this.capacity) {
      const oldestKey = this.cache.keys().next().value;
      this.cache.delete(oldestKey);
      this.evictions++;
    }
  }

  invalidate(path) {
    return this.cache.delete(path);
  }
}

class CDN extends EventEmitter {
  constructor(origin) {
    super();
    this.origin = origin;
    this.edges = new Map();
    this.distances = new Map();
    this.requestCount = 0;
    this.originFetches = 0;
    this.invalidRequests = 0;
  }

  addEdge(edge) {
    this.edges.set(edge.id, edge);
  }

  setDistance(a, b, latencyMs) {
    if (latencyMs < 0) throw new Error('Latency cannot be negative');
    this.distances.set(`${a}:${b}`, latencyMs);
    this.distances.set(`${b}:${a}`, latencyMs);
  }

  distance(a, b) {
    if (a === b) return 0;
    return this.distances.get(`${a}:${b}`) ?? 100;
  }

  chooseEdge(clientRegion) {
    const candidates = [...this.edges.values()]
      .filter(edge => edge.state !== EdgeState.OFFLINE);

    if (candidates.length === 0) {
      throw new Error('No healthy edge is available');
    }

    candidates.sort((a, b) => {
      const score = edge =>
        this.distance(clientRegion, edge.region) +
        edge.latencyMs +
        (edge.state === EdgeState.DEGRADED ? 1000 : 0);

      return score(a) - score(b);
    });

    return candidates[0];
  }

  validatePath(path) {
    return (
      typeof path === 'string' &&
      path.startsWith('/') &&
      !path.includes('..') &&
      !path.includes('\0') &&
      path.length <= 2048
    );
  }

  async request(path, clientRegion, options = {}) {
    this.requestCount++;

    if (!this.validatePath(path)) {
      this.invalidRequests++;
      return {
        status: CacheStatus.BYPASS,
        edge: null,
        latencyMs: 0,
        message: 'Rejected malformed path'
      };
    }

    const privateContent = path.startsWith('/private/');
    if (privateContent && !options.authorization) {
      return {
        status: CacheStatus.BYPASS,
        edge: null,
        latencyMs: 0,
        message: 'Authorization required'
      };
    }

    let edge;
    try {
      edge = this.chooseEdge(clientRegion);
    } catch (error) {
      return {
        status: CacheStatus.ORIGIN_ERROR,
        edge: null,
        latencyMs: 0,
        message: error.message
      };
    }

    if (!privateContent) {
      const lookup = edge.lookup(path, Date.now());

      if (lookup.status === CacheStatus.HIT) {
        const result = {
          status: CacheStatus.HIT,
          edge: edge.id,
          version: lookup.content.version,
          latencyMs: this.distance(clientRegion, edge.region) + edge.latencyMs,
          message: 'Served from edge cache'
        };
        this.emit('cacheHit', result);
        return result;
      }
    }

    try {
      const content = await this.origin.fetch(path);
      this.originFetches++;

      if (!privateContent) {
        edge.store(content, Date.now());
      }

      const result = {
        status: privateContent ? CacheStatus.BYPASS : CacheStatus.MISS,
        edge: edge.id,
        version: content.version,
        latencyMs:
          this.distance(clientRegion, edge.region) +
          edge.latencyMs +
          80,
        message: privateContent
          ? 'Private content fetched without caching'
          : 'Fetched from origin and cached'
      };

      this.emit('originFetch', result);
      return result;
    } catch (error) {
      const result = {
        status: CacheStatus.ORIGIN_ERROR,
        edge: edge.id,
        latencyMs: this.distance(clientRegion, edge.region) + edge.latencyMs,
        message: error.message
      };

      this.emit('originError', result);
      return result;
    }
  }

  invalidate(path) {
    let count = 0;
    for (const edge of this.edges.values()) {
      if (edge.invalidate(path)) count++;
    }
    this.emit('invalidation', { path, edgesAffected: count });
    return count;
  }

  metrics() {
    const values = [...this.edges.values()];
    const hits = values.reduce((sum, e) => sum + e.hits, 0);
    const misses = values.reduce((sum, e) => sum + e.misses, 0);

    return {
      requests: this.requestCount,
      hits,
      misses,
      stale: values.reduce((sum, e) => sum + e.stale, 0),
      evictions: values.reduce((sum, e) => sum + e.evictions, 0),
      originFetches: this.originFetches,
      invalidRequests: this.invalidRequests,
      hitRatio: this.requestCount
        ? Number((hits / this.requestCount).toFixed(3))
        : 0
    };
  }
}

async function main() {
  const origin = new OriginServer();

  origin.publish(
    '/static/app.js',
    'console.log("release-1");',
    'application/javascript',
    { ttlSeconds: 30 }
  );

  origin.publish(
    '/static/logo.svg',
    '<svg>logo</svg>',
    'image/svg+xml',
    { ttlSeconds: 60 }
  );

  origin.publish(
    '/private/audit.json',
    '{"classification":"internal"}',
    'application/json',
    { cacheable: false }
  );

  const cdn = new CDN(origin);

  cdn.addEdge(new EdgeServer('edge-delhi', 'DEL', 2, 8));
  cdn.addEdge(new EdgeServer('edge-mumbai', 'BOM', 2, 12));
  cdn.addEdge(new EdgeServer('edge-singapore', 'SIN', 2, 10));
  cdn.addEdge(new EdgeServer('edge-london', 'LON', 2, 18));

  [
    ['DEL', 'BOM', 18],
    ['DEL', 'SIN', 65],
    ['DEL', 'LON', 120],
    ['BOM', 'SIN', 55],
    ['BOM', 'LON', 130],
    ['SIN', 'LON', 160]
  ].forEach(([a, b, latency]) => cdn.setDistance(a, b, latency));

  cdn.on('cacheHit', event => console.log('EVENT cacheHit:', event));
  cdn.on('originError', event => console.log('EVENT originError:', event));

  const first = await cdn.request('/static/app.js', 'DEL');
  const second = await cdn.request('/static/app.js', 'DEL');
  const image = await cdn.request('/static/logo.svg', 'SIN');
  const privateResponse = await cdn.request('/private/audit.json', 'DEL', {
    authorization: 'internal-token'
  });

  console.log('first:', first);
  console.log('second:', second);
  console.log('image:', image);
  console.log('private:', privateResponse);

  // An unhealthy local edge causes routing to prefer another healthy location.
  cdn.edges.get('edge-delhi').state = EdgeState.DEGRADED;
  const failover = await cdn.request('/static/logo.svg', 'DEL');
  console.log('health-aware routing:', failover);

  // Publish a new version and invalidate cached copies.
  origin.publish(
    '/static/app.js',
    'console.log("release-2");',
    'application/javascript',
    { ttlSeconds: 30 }
  );

  const invalidated = cdn.invalidate('/static/app.js');
  console.log('invalidated copies:', invalidated);

  const refreshed = await cdn.request('/static/app.js', 'DEL');
  console.log('refreshed:', refreshed);

  origin.available = false;
  const originFailure = await cdn.request('/unknown.json', 'BOM');
  console.log('origin failure:', originFailure);

  console.log('metrics:', cdn.metrics());

  if (second.status !== CacheStatus.HIT) {
    throw new Error('Expected second request to be a cache hit');
  }

  if (refreshed.version !== 2) {
    throw new Error('Expected version 2 after invalidation');
  }

  if (privateResponse.status !== CacheStatus.BYPASS) {
    throw new Error('Private content must bypass shared cache');
  }
}

main().catch(error => {
  console.error('Fatal CDN simulation error:', error.message);
  process.exitCode = 1;
});
