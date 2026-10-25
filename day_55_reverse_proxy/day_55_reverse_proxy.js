#!/usr/bin/env node
'use strict';

/*
 * Reverse Proxy Policy and Routing Simulation
 *
 * Models:
 * - TLS termination
 * - host/path routing
 * - upstream pools
 * - weighted selection
 * - forwarded headers
 * - health state
 * - retries
 * - rate limiting
 * - security validation
 * - event-driven access logging
 *
 * No third-party npm packages are required.
 */

const crypto = require('node:crypto');

class ProxyError extends Error {}
class BadRequestError extends ProxyError {}
class TLSError extends ProxyError {}
class UpstreamError extends ProxyError {}

const Protocol = Object.freeze({
  HTTP: 'http',
  HTTPS: 'https'
});

const State = Object.freeze({
  HEALTHY: 'healthy',
  UNHEALTHY: 'unhealthy'
});

class RateLimiter {
  constructor(limit, windowMs) {
    this.limit = limit;
    this.windowMs = windowMs;
    this.buckets = new Map();
  }

  allow(clientIp) {
    const now = Date.now();
    const existing = this.buckets.get(clientIp);

    if (!existing || now - existing.startedAt >= this.windowMs) {
      this.buckets.set(clientIp, {
        startedAt: now,
        count: 1
      });
      return true;
    }

    if (existing.count >= this.limit) {
      return false;
    }

    existing.count += 1;
    return true;
  }
}

class TLSManager {
  constructor(certificates) {
    this.certificates = new Map(
      certificates.map(cert => [cert.hostname, cert])
    );
  }

  terminate(host, version) {
    const certificate = this.certificates.get(host);

    if (!certificate) {
      throw new TLSError(`no certificate configured for ${host}`);
    }

    if (!['TLS1.2', 'TLS1.3'].includes(version)) {
      throw new TLSError(`TLS version ${version} is rejected`);
    }

    return {
      terminated: true,
      certificate: certificate.hostname,
      tlsVersion: version
    };
  }
}

class UpstreamServer {
  constructor(name, host, port, weight = 1) {
    this.name = name;
    this.host = host;
    this.port = port;
    this.weight = weight;
    this.state = State.HEALTHY;
    this.requests = 0;
    this.active = 0;
  }

  isHealthy() {
    return this.state === State.HEALTHY;
  }

  setHealth(healthy) {
    this.state = healthy ? State.HEALTHY : State.UNHEALTHY;
  }
}

class WeightedRoundRobin {
  constructor() {
    this.position = new Map();
  }

  choose(poolName, servers, excluded = new Set()) {
    const weighted = [];

    for (const server of servers) {
      if (server.isHealthy() && !excluded.has(server.name)) {
        for (let i = 0; i < server.weight; i += 1) {
          weighted.push(server);
        }
      }
    }

    if (weighted.length === 0) {
      throw new UpstreamError(`no healthy server in ${poolName}`);
    }

    const current = this.position.get(poolName) || 0;
    const selected = weighted[current % weighted.length];
    this.position.set(poolName, current + 1);

    return selected;
  }
}

class ReverseProxy {
  constructor(config) {
    this.routes = config.routes;
    this.pools = config.pools;
    this.tls = config.tls;
    this.events = [];
    this.balancer = new WeightedRoundRobin();
    this.rateLimiter = new RateLimiter(10, 60_000);
    this.maxBodyBytes = 1_000_000;
  }

  route(path) {
    const candidates = this.routes
      .filter(route => path.startsWith(route.prefix))
      .sort((a, b) => b.prefix.length - a.prefix.length);

    if (candidates.length === 0) {
      throw new BadRequestError(`no route matches ${path}`);
    }

    return candidates[0];
  }

  validateRequest(request) {
    if (!request.clientIp || !request.clientIp.includes('.')) {
      throw new BadRequestError('invalid client IP');
    }

    if (!/^(GET|POST|PUT|PATCH|DELETE)$/.test(request.method)) {
      throw new BadRequestError('unsupported HTTP method');
    }

    if (!request.path.startsWith('/')) {
      throw new BadRequestError('invalid request path');
    }

    if (/[\r\n]/.test(request.path)) {
      throw new BadRequestError('CRLF characters are not allowed');
    }

    const bodyBytes = Buffer.byteLength(request.body || '', 'utf8');

    if (bodyBytes > this.maxBodyBytes) {
      throw new BadRequestError('request body is too large');
    }

    if (request.headers['x-forwarded-for']) {
      throw new BadRequestError(
        'client cannot inject X-Forwarded-For'
      );
    }

    if (!this.rateLimiter.allow(request.clientIp)) {
      throw new BadRequestError('rate limit exceeded');
    }
  }

  buildHeaders(request) {
    return {
      host: request.host,
      'x-real-ip': request.clientIp,
      'x-forwarded-for': request.clientIp,
      'x-forwarded-proto': request.protocol
    };
  }

  async sendToUpstream(server, request, headers) {
    server.active += 1;

    try {
      server.requests += 1;

      // Simulated transport failure.
      if (request.path === '/api/failure' && server.name === 'api-1') {
        throw new UpstreamError(
          `connection failed to ${server.name}`
        );
      }

      // Simulated application processing delay.
      await new Promise(resolve => setTimeout(resolve, 5));

      return {
        status: 200,
        headers: {
          'content-type': 'application/json',
          'x-upstream-server': server.name
        },
        body: JSON.stringify({
          requestId: crypto.randomUUID(),
          upstream: server.name,
          path: request.path,
          forwardedFor: headers['x-forwarded-for']
        })
      };
    } finally {
      server.active -= 1;
    }
  }

  async handle(request) {
    const started = process.hrtime.bigint();

    let response;

    try {
      this.validateRequest(request);

      if (request.protocol === Protocol.HTTPS) {
        this.tls.terminate(
          request.host,
          request.headers['x-tls-version'] || 'TLS1.3'
        );
      }

      const route = this.route(request.path);
      const pool = this.pools.get(route.pool);

      if (!pool) {
        throw new UpstreamError(`unknown upstream pool ${route.pool}`);
      }

      const headers = this.buildHeaders(request);
      const excluded = new Set();

      for (let attempt = 0; attempt < 2; attempt += 1) {
        const server = this.balancer.choose(
          route.pool,
          pool,
          excluded
        );

        excluded.add(server.name);

        try {
          response = await this.sendToUpstream(
            server,
            request,
            headers
          );
          break;
        } catch (error) {
          if (!(error instanceof UpstreamError)) {
            throw error;
          }

          if (attempt === 1) {
            throw error;
          }
        }
      }

      return response;
    } catch (error) {
      if (error instanceof TLSError) {
        response = {
          status: 495,
          body: error.message,
          headers: {}
        };
      } else if (error instanceof BadRequestError) {
        response = {
          status: 400,
          body: error.message,
          headers: {}
        };
      } else if (error instanceof UpstreamError) {
        response = {
          status: 503,
          body: error.message,
          headers: {}
        };
      } else {
        response = {
          status: 500,
          body: 'internal proxy error',
          headers: {}
        };
      }

      return response;
    } finally {
      const durationMs =
        Number(process.hrtime.bigint() - started) / 1_000_000;

      this.events.push({
        event: 'access',
        timestamp: new Date().toISOString(),
        status: response?.status ?? 500,
        path: request.path,
        clientIp: request.clientIp,
        durationMs: Number(durationMs.toFixed(3))
      });
    }
  }
}

async function main() {
  const tls = new TLSManager([
    {
      hostname: 'api.example.com',
      issuer: 'Example CA'
    }
  ]);

  const apiPool = [
    new UpstreamServer('api-1', '10.0.1.10', 8080, 2),
    new UpstreamServer('api-2', '10.0.1.11', 8080, 1)
  ];

  const webPool = [
    new UpstreamServer('web-1', '10.0.2.10', 8080),
    new UpstreamServer('web-2', '10.0.2.11', 8080)
  ];

  const proxy = new ReverseProxy({
    tls,
    pools: new Map([
      ['api', apiPool],
      ['web', webPool]
    ]),
    routes: [
      { prefix: '/api/', pool: 'api' },
      { prefix: '/', pool: 'web' }
    ]
  });

  const requests = [
    {
      clientIp: '203.0.113.10',
      host: 'api.example.com',
      method: 'GET',
      path: '/api/users',
      protocol: Protocol.HTTPS,
      headers: { 'x-tls-version': 'TLS1.3' }
    },
    {
      clientIp: '203.0.113.11',
      host: 'api.example.com',
      method: 'GET',
      path: '/dashboard',
      protocol: Protocol.HTTPS,
      headers: { 'x-tls-version': 'TLS1.2' }
    },
    {
      clientIp: '203.0.113.12',
      host: 'api.example.com',
      method: 'GET',
      path: '/api/failure',
      protocol: Protocol.HTTPS,
      headers: {}
    },
    {
      clientIp: '203.0.113.13',
      host: 'api.example.com',
      method: 'GET',
      path: '/api/users',
      protocol: Protocol.HTTPS,
      headers: {
        'x-forwarded-for': '198.51.100.10'
      }
    }
  ];

  for (const request of requests) {
    const response = await proxy.handle(request);
    console.log(
      JSON.stringify(
        {
          path: request.path,
          status: response.status,
          body: response.body
        },
        null,
        2
      )
    );
  }

  apiPool[0].setHealth(false);

  const fallback = await proxy.handle({
    clientIp: '203.0.113.14',
    host: 'api.example.com',
    method: 'GET',
    path: '/api/orders',
    protocol: Protocol.HTTPS,
    headers: {}
  });

  console.log('\nFallback:', fallback);

  console.log('\nServer statistics:');
  for (const [poolName, servers] of proxy.pools) {
    console.log(poolName);

    for (const server of servers) {
      console.log({
        server: server.name,
        state: server.state,
        requests: server.requests,
        active: server.active
      });
    }
  }

  console.log('\nAccess events:');
  console.table(proxy.events);
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
