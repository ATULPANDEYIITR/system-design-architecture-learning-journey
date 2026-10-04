'use strict';

/*
 * NoSQL Database Laboratory
 *
 * This Node.js program uses JavaScript-specific features such as Maps,
 * objects, Sets, async iterators, event emitters, validation, and immutable
 * snapshots to model four NoSQL database families:
 *
 *   key-value
 *   document
 *   column-family
 *   graph
 *
 * The implementations are deliberately different from one another because
 * each model solves a different access-pattern problem.
 */

const { EventEmitter } = require('node:events');

function heading(title) {
  console.log(`\n${'='.repeat(78)}\n${title}\n${'='.repeat(78)}`);
}

function printJson(value) {
  console.log(JSON.stringify(value, null, 2));
}

// ---------------------------------------------------------------------------
// Key-value database
// ---------------------------------------------------------------------------

class KeyValueStore {
  constructor() {
    this.values = new Map();
    this.expiry = new Map();
  }

  set(key, value, ttlMilliseconds = null) {
    if (typeof key !== 'string' || key.length === 0) {
      throw new TypeError('Key must be a non-empty string');
    }

    this.values.set(key, value);

    if (ttlMilliseconds === null) {
      this.expiry.delete(key);
      return;
    }

    if (!Number.isFinite(ttlMilliseconds) || ttlMilliseconds <= 0) {
      this.delete(key);
      return;
    }

    this.expiry.set(key, Date.now() + ttlMilliseconds);
  }

  get(key, defaultValue = undefined) {
    if (!this.values.has(key)) {
      return defaultValue;
    }

    const expiresAt = this.expiry.get(key);

    if (expiresAt !== undefined && Date.now() >= expiresAt) {
      this.delete(key);
      return defaultValue;
    }

    return this.values.get(key);
  }

  delete(key) {
    const existed = this.values.delete(key);
    this.expiry.delete(key);
    return existed;
  }

  increment(key, amount = 1) {
    const current = this.get(key, 0);

    if (!Number.isInteger(current)) {
      throw new TypeError('Counter value must be an integer');
    }

    const updated = current + amount;
    this.set(key, updated);
    return updated;
  }

  compareAndSet(key, expectedValue, newValue) {
    const currentValue = this.get(key);

    if (currentValue !== expectedValue) {
      return false;
    }

    this.set(key, newValue);
    return true;
  }
}

function demonstrateKeyValue() {
  heading('Key-Value Model');

  const store = new KeyValueStore();

  store.set(
    'session:u-501',
    Object.freeze({
      userId: 'u-501',
      role: 'customer',
      cartId: 'cart-901'
    }),
    60_000
  );

  store.set('rate-limit:u-501', 0);

  console.log('Session:', store.get('session:u-501'));

  for (let attempt = 0; attempt < 3; attempt += 1) {
    store.increment('rate-limit:u-501');
  }

  console.log('Request counter:', store.get('rate-limit:u-501'));

  const changed = store.compareAndSet(
    'session:feature:recommendations',
    undefined,
    true
  );

  console.log('Feature flag created by conditional write:', changed);
}

// ---------------------------------------------------------------------------
// Document database
// ---------------------------------------------------------------------------

class DocumentStore {
  constructor() {
    this.documents = new Map();
    this.categoryIndex = new Map();
  }

  validate(document) {
    const required = ['id', 'name', 'category', 'price', 'tags'];

    for (const field of required) {
      if (!(field in document)) {
        throw new Error(`Missing required field: ${field}`);
      }
    }

    if (!Number.isFinite(document.price) || document.price < 0) {
      throw new Error('price must be a non-negative number');
    }

    if (!Array.isArray(document.tags)) {
      throw new Error('tags must be an array');
    }
  }

  clone(document) {
    return structuredClone(document);
  }

  insert(document) {
    this.validate(document);

    if (this.documents.has(document.id)) {
      throw new Error(`Document ${document.id} already exists`);
    }

    this.documents.set(document.id, this.clone(document));

    if (!this.categoryIndex.has(document.category)) {
      this.categoryIndex.set(document.category, new Set());
    }

    this.categoryIndex.get(document.category).add(document.id);
  }

  findByCategory(category) {
    const ids = this.categoryIndex.get(category) ?? new Set();

    return [...ids]
      .map(id => this.documents.get(id))
      .filter(Boolean)
      .map(document => this.clone(document));
  }

  find(predicate) {
    return [...this.documents.values()]
      .filter(predicate)
      .map(document => this.clone(document));
  }

  updateNested(documentId, path, value) {
    const document = this.documents.get(documentId);

    if (!document) {
      throw new Error(`Unknown document: ${documentId}`);
    }

    let target = document;

    for (let index = 0; index < path.length - 1; index += 1) {
      const property = path[index];

      if (
        target[property] === null ||
        typeof target[property] !== 'object' ||
        Array.isArray(target[property])
      ) {
        throw new Error(`Cannot traverse field: ${property}`);
      }

      target = target[property];
    }

    target[path[path.length - 1]] = value;
    this.validate(document);
  }
}

function demonstrateDocumentDatabase() {
  heading('Document Model');

  const store = new DocumentStore();

  const products = [
    {
      id: 'p-100',
      name: 'Mechanical Keyboard',
      category: 'electronics',
      price: 89,
      tags: ['keyboard', 'office'],
      inventory: { warehouseA: 20, warehouseB: 12 }
    },
    {
      id: 'p-101',
      name: 'Wireless Mouse',
      category: 'electronics',
      price: 39,
      tags: ['mouse', 'wireless'],
      inventory: { warehouseA: 35, warehouseB: 18 }
    },
    {
      id: 'p-102',
      name: 'USB-C Dock',
      category: 'electronics',
      price: 129,
      tags: ['usb-c', 'dock'],
      inventory: { warehouseA: 7, warehouseB: 10 }
    }
  ];

  products.forEach(product => store.insert(product));

  console.log('Indexed category query:');
  printJson(store.findByCategory('electronics'));

  console.log('Price query:');
  printJson(store.find(product => product.price < 100));

  store.updateNested('p-100', ['inventory', 'warehouseA'], 18);

  console.log('Nested update:');
  printJson(store.find(document => document.id === 'p-100'));

  try {
    store.insert({
      id: 'invalid',
      name: 'Invalid',
      category: 'electronics',
      price: -20,
      tags: []
    });
  } catch (error) {
    console.log(`Validation rejected document: ${error.message}`);
  }
}

// ---------------------------------------------------------------------------
// Column-family model
// ---------------------------------------------------------------------------

class ColumnFamilyStore {
  constructor() {
    this.families = new Map();
  }

  put(family, rowKey, columns) {
    if (!family || !rowKey) {
      throw new Error('Family and row key are required');
    }

    if (!this.families.has(family)) {
      this.families.set(family, new Map());
    }

    const rows = this.families.get(family);
    const current = rows.get(rowKey) ?? {};

    rows.set(rowKey, {
      ...current,
      ...columns
    });
  }

  get(family, rowKey, selectedColumns = null) {
    const row = this.families.get(family)?.get(rowKey);

    if (!row) {
      return null;
    }

    if (selectedColumns === null) {
      return { rowKey, columns: { ...row } };
    }

    const columns = {};

    for (const column of selectedColumns) {
      if (column in row) {
        columns[column] = row[column];
      }
    }

    return { rowKey, columns };
  }

  queryPartition(family, partitionPrefix) {
    const rows = this.families.get(family) ?? new Map();

    return [...rows.entries()]
      .filter(([rowKey]) => rowKey.startsWith(partitionPrefix))
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([rowKey, columns]) => ({
        rowKey,
        columns: { ...columns }
      }));
  }
}

async function* streamPartition(store, family, prefix) {
  const rows = store.queryPartition(family, prefix);

  for (const row of rows) {
    // Yielding asynchronously models a streaming consumer rather than
    // materializing an arbitrarily large partition in application memory.
    await Promise.resolve();
    yield row;
  }
}

async function demonstrateColumnFamily() {
  heading('Column-Family Model');

  const store = new ColumnFamilyStore();

  const events = [
    ['u-501', '00:01:00', 'login', 'mobile'],
    ['u-501', '00:05:00', 'view', 'mobile'],
    ['u-501', '00:09:00', 'purchase', 'web'],
    ['u-502', '00:03:00', 'login', 'web']
  ];

  for (const [userId, clock, eventType, channel] of events) {
    const rowKey = `${userId}|2026-10-05|${clock}`;

    store.put('activity_by_user_day', rowKey, {
      eventType,
      channel,
      receivedAt: new Date().toISOString()
    });
  }

  console.log('Partition stream:');

  for await (const row of streamPartition(
    store,
    'activity_by_user_day',
    'u-501|2026-10-05|'
  )) {
    printJson(row);
  }

  console.log('Projected columns from one row:');

  printJson(
    store.get(
      'activity_by_user_day',
      'u-501|2026-10-05|00:05:00',
      ['eventType', 'channel']
    )
  );
}

// ---------------------------------------------------------------------------
// Graph model
// ---------------------------------------------------------------------------

class GraphStore {
  constructor() {
    this.nodes = new Map();
    this.edges = new Map();
  }

  addNode(id, label, properties = {}) {
    if (this.nodes.has(id)) {
      throw new Error(`Duplicate node: ${id}`);
    }

    this.nodes.set(id, {
      id,
      label,
      properties: structuredClone(properties)
    });

    this.edges.set(id, []);
  }

  addEdge(source, relationship, target, properties = {}) {
    if (!this.nodes.has(source) || !this.nodes.has(target)) {
      throw new Error('Both graph endpoints must exist');
    }

    this.edges.get(source).push({
      source,
      relationship,
      target,
      properties: structuredClone(properties)
    });
  }

  neighbors(nodeId, relationship = null) {
    return (this.edges.get(nodeId) ?? [])
      .filter(edge => relationship === null || edge.relationship === relationship)
      .map(edge => edge.target);
  }

  shortestPath(start, target) {
    if (!this.nodes.has(start) || !this.nodes.has(target)) {
      return null;
    }

    const queue = [start];
    const parent = new Map([[start, null]]);

    for (const current of queue) {
      if (current === target) {
        break;
      }

      for (const neighbor of this.neighbors(current)) {
        if (!parent.has(neighbor)) {
          parent.set(neighbor, current);
          queue.push(neighbor);
        }
      }
    }

    if (!parent.has(target)) {
      return null;
    }

    const path = [];
    let current = target;

    while (current !== null) {
      path.push(current);
      current = parent.get(current);
    }

    return path.reverse();
  }

  recommendProducts(userId) {
    const purchased = new Set(
      this.neighbors(userId, 'PURCHASED')
    );

    const similarUsers = new Set();

    for (const [nodeId, edges] of this.edges) {
      if (nodeId === userId) {
        continue;
      }

      if (
        edges.some(
          edge =>
            edge.relationship === 'PURCHASED' &&
            purchased.has(edge.target)
        )
      ) {
        similarUsers.add(nodeId);
      }
    }

    const recommendations = new Set();

    for (const otherUser of similarUsers) {
      for (const product of this.neighbors(otherUser, 'PURCHASED')) {
        if (!purchased.has(product)) {
          recommendations.add(product);
        }
      }
    }

    return [...recommendations].sort();
  }
}

function demonstrateGraph() {
  heading('Graph Model');

  const graph = new GraphStore();

  graph.addNode('u-501', 'User', { name: 'Asha' });
  graph.addNode('u-502', 'User', { name: 'Rahul' });
  graph.addNode('u-503', 'User', { name: 'Meera' });

  graph.addNode('p-100', 'Product', { name: 'Keyboard' });
  graph.addNode('p-101', 'Product', { name: 'Mouse' });
  graph.addNode('p-102', 'Product', { name: 'USB-C Dock' });

  graph.addEdge('u-501', 'PURCHASED', 'p-100');
  graph.addEdge('u-501', 'PURCHASED', 'p-101');
  graph.addEdge('u-502', 'PURCHASED', 'p-100');
  graph.addEdge('u-502', 'PURCHASED', 'p-102');
  graph.addEdge('u-503', 'PURCHASED', 'p-102');

  console.log('Shared-purchase recommendations:');
  printJson(graph.recommendProducts('u-501'));

  console.log('Shortest relationship path:');
  printJson(graph.shortestPath('u-501', 'p-102'));
}

// ---------------------------------------------------------------------------
// Event-driven NoSQL workflow
// ---------------------------------------------------------------------------

class NoSqlWorkflow extends EventEmitter {
  constructor() {
    super();
    this.auditLog = [];
  }

  record(eventType, payload) {
    const event = {
      id: crypto.randomUUID(),
      eventType,
      timestamp: new Date().toISOString(),
      payload: structuredClone(payload)
    };

    this.auditLog.push(event);
    this.emit(eventType, event);
  }
}

/*
 * Node's crypto module is loaded here instead of adding an npm dependency.
 * require() is valid because this file intentionally uses CommonJS.
 */
const crypto = require('node:crypto');

async function demonstrateEventDrivenBehavior() {
  heading('Event-Driven Application Behavior');

  const workflow = new NoSqlWorkflow();

  workflow.on('documentUpdated', event => {
    console.log(
      `Audit listener received ${event.eventType} for ${event.payload.id}`
    );
  });

  workflow.on('cacheInvalidation', event => {
    console.log(
      `Cache invalidation requested for ${event.payload.key}`
    );
  });

  workflow.record('documentUpdated', {
    id: 'p-100',
    changedField: 'price',
    newValue: 84
  });

  workflow.record('cacheInvalidation', {
    key: 'product:p-100'
  });

  console.log(`Audit events retained: ${workflow.auditLog.length}`);
}

// ---------------------------------------------------------------------------
// Security and operational checks
// ---------------------------------------------------------------------------

function demonstrateOperationalRules() {
  heading('Operational and Security Rules');

  const unsafeKey = 'session:u-501\nAuthorization: forged';

  if (/[\r\n]/.test(unsafeKey)) {
    console.log('Rejected key containing control characters.');
  }

  const allowedDocumentFields = new Set([
    'id',
    'name',
    'category',
    'price',
    'tags',
    'inventory'
  ]);

  const incoming = {
    id: 'p-100',
    price: 80,
    '$where': 'malicious expression'
  };

  const sanitized = Object.fromEntries(
    Object.entries(incoming).filter(([key]) =>
      allowedDocumentFields.has(key)
    )
  );

  console.log('Allow-listed document fields:');
  printJson(sanitized);

  console.log(
    'Production systems must still enforce authentication, authorization, '
    'TLS, encryption at rest, audit logging, secret management, backups, '
    'replication, rate limits, and monitoring at the database/service layer.'
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  heading('NoSQL Database Laboratory');

  demonstrateKeyValue();
  demonstrateDocumentDatabase();
  await demonstrateColumnFamily();
  demonstrateGraph();
  await demonstrateEventDrivenBehavior();
  demonstrateOperationalRules();

  heading('Model Selection');

  const decisions = {
    'session token lookup': 'key-value',
    'shopping cart state': 'key-value',
    'variable product catalog': 'document',
    'content records with nested metadata': 'document',
    'large event partitions': 'column-family',
    'high-volume user activity by time bucket': 'column-family',
    'social relationship traversal': 'graph',
    'fraud relationship analysis': 'graph'
  };

  for (const [workload, model] of Object.entries(decisions)) {
    console.log(`${workload.padEnd(46)} -> ${model}`);
  }
}

main().catch(error => {
  console.error('Application failure:', error);
  process.exitCode = 1;
});
