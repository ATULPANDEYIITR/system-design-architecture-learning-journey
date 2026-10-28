'use strict';

/*
 * CDN architecture simulation for Node.js.
 *
 * Models origin retrieval, edge caching, TTL, cache keys, request routing,
 * conditional revalidation, invalidation, LRU eviction, and policy checks.
 *
 * No third-party packages are required.
 */

const crypto = require('node:crypto');
const EventEmitter = require('node:events');

const CacheStatus = Object.freeze({
  HIT: 'HIT',
  MISS: 'MISS',
  REVALIDATED: 'REVALIDATED',
  BYPASS: 'BYPASS',
  STALE: 'STALE'
});

class ValidationError extends Error {}

class CachePolicy {
  constructor({
    defaultTtlSeconds = 60,
    maxTtlSeconds = 3600,
    queryAllowlist = [],
    cacheAuthenticated = false
  } = {}) {
    if (defaultTtlSeconds < 0 || maxTtlSeconds < defaultTtlSeconds) {
      throw new ValidationError('Invalid TTL policy');
    }

    this.defaultTtlSeconds = defaultTtlSeconds;
    this.maxTtlSeconds = maxTtlSeconds;
    this.queryAllowlist = new Set(queryAllowlist);
    this.cacheAuthenticated = cacheAuthenticated;
  }
}

class Request {
  constructor({
    method = 'GET',
    host,
    path,
    query = {},
    headers = {}
  }) {
    this.method = method.toUpperCase();
    this.host = host;
    this.path = path;
    this.query = { ...query };
    this.headers = { ...headers };

    if (!host || !/^[A-Za-z0-9.-]+$/.test(host)) {
      throw new ValidationError('Invalid host');
    }

    if (!path.startsWith('/')) {
      throw new ValidationError('Path must begin with "/"');
    }

    if (!['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'].includes(this.method)) {
      throw new ValidationError(`Unsupported method: ${this.method}`);
    }
  }
}

class OriginServer {
  constructor(name) {
    this.name = name;
    this.objects = new Map();
    this.fetchCount = 0;
  }

  publish(path, body, contentType, cacheControl = 'public, max-age=60') {
    if (!path.startsWith('/')) {
      throw new ValidationError('Invalid origin path');
    }

    const etag = crypto
      .createHash('sha256')
      .update(body)
      .digest('hex')
      .slice(0, 16);

    this.objects.set(path, {
      status: 200,
      body,
      contentType,
      etag,
      cacheControl,
      generatedAt: Date.now()
    });
  }

  async fetch(path, ifNoneMatch = null) {
    this.fetchCount++;

    // Simulates network latency without requiring a remote server.
    await new Promise(resolve => setTimeout(resolve, 2));

    const response = this.objects.get(path);

    if (!response) {
      return {
        status: 404,
        body: 'Not Found',
        contentType: 'text/plain',
        etag: '404',
        cacheControl: 'no-store'
      };
    }

    if (ifNoneMatch && ifNoneMatch === response.etag) {
      return {
        ...response,
        notModified: true
      };
    }

    return {
      ...response,
      notModified: false
    };
  }
}

class EdgeLocation extends EventEmitter {
  constructor(name, capacity, policy) {
    super();

    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new ValidationError('Edge capacity must be positive');
    }

    this.name = name;
    this.capacity = capacity;
    this.policy = policy;

    // Map insertion order is used as an LRU queue.
    this.cache = new Map();

    this.metrics = {
      requests: 0,
      hits: 0,
      misses: 0,
      stale: 0,
      bypasses: 0,
      revalidations: 0,
      originFetches: 0,
      evictions: 0
    };
  }

  parseMaxAge(cacheControl) {
    const match = cacheControl.match(/(?:^|,\s*)max-age=(\d+)/i);
    return match ? Number(match[1]) : this.policy.defaultTtlSeconds;
  }

  cacheable(response) {
    const directives = response.cacheControl
      .split(',')
      .map(value => value.trim().toLowerCase());

    return !directives.includes('no-store') &&
           !directives.includes('private');
  }

  ttl(response) {
    return Math.min(
      this.parseMaxAge(response.cacheControl),
      this.policy.maxTtlSeconds
    );
  }

  get(key, now) {
    const entry = this.cache.get(key);

    if (!entry) {
      return null;
    }

    // Refresh LRU position.
    this.cache.delete(key);
    entry.lastAccessed = now;
    this.cache.set(key, entry);

    return entry;
  }

  put(key, response, now) {
    if (!this.cacheable(response)) {
      return false;
    }

    const ttl = this.ttl(response);

    this.cache.delete(key);
    this.cache.set(key, {
      key,
      response,
      storedAt: now,
      expiresAt: now + ttl * 1000,
      lastAccessed: now
    });

    while (this.cache.size > this.capacity) {
      const oldestKey = this.cache.keys().next().value;
      this.cache.delete(oldestKey);
      this.metrics.evictions++;
      this.emit('eviction', oldestKey);
    }

    return true;
  }

  invalidate(predicate = () => true) {
    let count = 0;

    for (const [key, entry] of this.cache.entries()) {
      if (predicate(key, entry)) {
        this.cache.delete(key);
        count++;
      }
    }

    return count;
  }
}

class CDN {
  constructor(origin, edges) {
    if (!origin || !edges.length) {
      throw new ValidationError('CDN requires an origin and at least one edge');
    }

    this.origin = origin;
    this.edges = edges;
    this.trackingParameters = new Set([
      'utm_source',
      'utm_medium',
      'utm_campaign',
      'utm_term',
      'utm_content',
      'fbclid'
    ]);
  }

  route(region) {
    const map = {
      india: ['blr', 'bom', 'del'],
      asia: ['sin', 'bom', 'tok'],
      europe: ['fra', 'lon', 'ams'],
      'north-america': ['iad', 'dfw', 'sfo']
    };

    const preferred = map[region.toLowerCase()] || [];

    for (const name of preferred) {
      const edge = this.edges.find(
        candidate => candidate.name.toLowerCase() === name
      );
      if (edge) return edge;
    }

    return this.edges[0];
  }

  cacheKey(request, policy) {
    const parameters = Object.entries(request.query)
      .filter(([name]) => {
        if (this.trackingParameters.has(name.toLowerCase())) {
          return false;
        }

        if (policy.queryAllowlist.size > 0) {
          return policy.queryAllowlist.has(name);
        }

        return true;
      })
      .sort(([a], [b]) => a.localeCompare(b));

    const query = parameters
      .map(([name, value]) =>
        `${encodeURIComponent(name)}=${encodeURIComponent(value)}`
      )
      .join('&');

    return [
      request.host.toLowerCase(),
      request.method,
      request.path,
      query
    ].join('|');
  }

  async request(request, region, now = Date.now()) {
    const edge = this.route(region);
    edge.metrics.requests++;

    if (!['GET', 'HEAD'].includes(request.method)) {
      edge.metrics.bypasses++;
      const response = await this.origin.fetch(request.path);
      return { response, status: CacheStatus.BYPASS, edge: edge.name };
    }

    if (request.headers.authorization && !edge.policy.cacheAuthenticated) {
      edge.metrics.bypasses++;
      const response = await this.origin.fetch(request.path);
      return { response, status: CacheStatus.BYPASS, edge: edge.name };
    }

    const key = this.cacheKey(request, edge.policy);
    const entry = edge.get(key, now);

    if (entry && entry.expiresAt > now) {
      edge.metrics.hits++;
      return {
        response: entry.response,
        status: CacheStatus.HIT,
        edge: edge.name
      };
    }

    if (entry) {
      edge.metrics.stale++;

      const response = await this.origin.fetch(
        request.path,
        entry.response.etag
      );
      edge.metrics.originFetches++;

      if (response.notModified) {
        entry.expiresAt = now + edge.ttl(entry.response) * 1000;
        entry.storedAt = now;
        entry.lastAccessed = now;
        edge.metrics.revalidations++;

        return {
          response: entry.response,
          status: CacheStatus.REVALIDATED,
          edge: edge.name
        };
      }

      edge.put(key, response, now);
      edge.metrics.misses++;

      return {
        response,
        status: CacheStatus.STALE,
        edge: edge.name
      };
    }

    const response = await this.origin.fetch(request.path);
    edge.metrics.originFetches++;
    edge.metrics.misses++;
    edge.put(key, response, now);

    return {
      response,
      status: CacheStatus.MISS,
      edge: edge.name
    };
  }

  purgePath(path) {
    return this.edges.reduce(
      (total, edge) =>
        total + edge.invalidate((key) => key.includes(`|${path}|`)),
      0
    );
  }

  report() {
    return this.edges.map(edge => ({
      edge: edge.name,
      ...edge.metrics,
      cachedObjects: edge.cache.size,
      hitRatio: edge.metrics.requests === 0
        ? 0
        : edge.metrics.hits / edge.metrics.requests
    }));
  }
}

async function main() {
  const policy = new CachePolicy({
    defaultTtlSeconds: 30,
    maxTtlSeconds: 300,
    queryAllowlist: ['version', 'lang']
  });

  const origin = new OriginServer('origin-primary');

  origin.publish(
    '/assets/app.js',
    "console.log('release-42');",
    'application/javascript',
    'public, max-age=120'
  );

  origin.publish(
    '/index.html',
    '<html><body>Release 42</body></html>',
    'text/html',
    'public, max-age=20'
  );

  origin.publish(
    '/account',
    'private account response',
    'text/plain',
    'private, max-age=30'
  );

  const edges = [
    new EdgeLocation('blr', 2, policy),
    new EdgeLocation('fra', 2, policy),
    new EdgeLocation('iad', 2, policy)
  ];

  const cdn = new CDN(origin, edges);
  const start = Date.now();

  const scenarios = [
    [
      new Request({
        host: 'example.test',
        path: '/assets/app.js'
      }),
      'india',
      start
    ],
    [
      new Request({
        host: 'example.test',
        path: '/assets/app.js'
      }),
      'india',
      start + 10_000
    ],
    [
      new Request({
        host: 'example.test',
        path: '/assets/app.js',
        query: { utm_source: 'newsletter' }
      }),
      'india',
      start + 15_000
    ],
    [
      new Request({
        host: 'example.test',
        path: '/index.html'
      }),
      'europe',
      start + 5_000
    ],
    [
      new Request({
        host: 'example.test',
        path: '/account',
        headers: { authorization: 'Bearer secret' }
      }),
      'india',
      start + 20_000
    ]
  ];

  for (const [request, region, timestamp] of scenarios) {
    const result = await cdn.request(request, region, timestamp);
    console.log({
      request: `${request.method} ${request.path}`,
      region,
      edge: result.edge,
      status: result.status,
      httpStatus: result.response.status
    });
  }

  console.log('\nOrigin fetches:', origin.fetchCount);
  console.table(cdn.report());

  const purged = cdn.purgePath('/assets/app.js');
  console.log(`Purged ${purged} cached asset entries.`);

  const afterPurge = await cdn.request(
    new Request({
      host: 'example.test',
      path: '/assets/app.js'
    }),
    'india',
    start + 40_000
  );

  console.log({
    afterPurgeStatus: afterPurge.status,
    edge: afterPurge.edge,
    httpStatus: afterPurge.response.status
  });
}

main().catch(error => {
  console.error('CDN simulation failed:', error.message);
  process.exitCode = 1;
});
