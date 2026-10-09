"use strict";

/*
 * Event-driven database sharding model for Node.js 18+.
 *
 * The implementation emphasizes JavaScript-specific asynchronous routing,
 * shard lifecycle events, Promise-based scatter-gather queries, and safe
 * handling of concurrent requests. Data remains in memory.
 */

const { createHash } = require("node:crypto");
const { EventEmitter } = require("node:events");
const assert = require("node:assert/strict");

class ShardingError extends Error {}
class InvalidShardKey extends ShardingError {}
class ShardUnavailable extends ShardingError {}
class DuplicateRecord extends ShardingError {}
class RecordNotFound extends ShardingError {}

function stableHash(value) {
  // Cryptographic hashing provides stable placement across Node.js processes.
  return createHash("sha256").update(String(value), "utf8").digest("hex");
}

function validateKey(key) {
  if (typeof key !== "string" || key.trim().length === 0) {
    throw new InvalidShardKey("The shard key must be a non-empty string.");
  }
  return key;
}

class VirtualShardRouter {
  constructor(shardIds, virtualNodes = 128) {
    if (!Number.isInteger(virtualNodes) || virtualNodes < 1) {
      throw new RangeError("virtualNodes must be a positive integer.");
    }
    this.virtualNodes = virtualNodes;
    this.rebuild(shardIds);
  }

  rebuild(shardIds) {
    const uniqueIds = [...new Set(shardIds)].sort();

    if (uniqueIds.some((id) => typeof id !== "string" || !id.trim())) {
      throw new TypeError("Every shard identifier must be a non-empty string.");
    }

    this.ring = [];
    for (const shardId of uniqueIds) {
      for (let index = 0; index < this.virtualNodes; index += 1) {
        const position = stableHash(`${shardId}:virtual:${index}`);
        this.ring.push({ position, shardId });
      }
    }

    this.ring.sort((left, right) =>
      left.position.localeCompare(right.position)
    );
  }

  route(key) {
    validateKey(key);
    if (this.ring.length === 0) {
      throw new ShardingError("No shards are registered.");
    }

    const position = stableHash(key);

    // Binary search avoids scanning every virtual node for each lookup.
    let low = 0;
    let high = this.ring.length;

    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (this.ring[middle].position < position) {
        low = middle + 1;
      } else {
        high = middle;
      }
    }

    return this.ring[low === this.ring.length ? 0 : low].shardId;
  }
}

class InMemoryShard {
  constructor(id) {
    this.id = id;
    this.records = new Map();
    this.available = true;
    this.version = 0;
  }

  assertAvailable() {
    if (!this.available) {
      throw new ShardUnavailable(`Shard ${this.id} is unavailable.`);
    }
  }

  put(key, record) {
    this.assertAvailable();
    this.records.set(key, structuredClone(record));
    this.version += 1;
  }

  get(key) {
    this.assertAvailable();
    const record = this.records.get(key);
    return record === undefined ? null : structuredClone(record);
  }

  delete(key) {
    this.assertAvailable();
    const removed = this.records.delete(key);
    if (removed) this.version += 1;
    return removed;
  }
}

class ShardedOrderService extends EventEmitter {
  constructor(shardCount = 4) {
    super();

    if (!Number.isInteger(shardCount) || shardCount < 1) {
      throw new RangeError("shardCount must be a positive integer.");
    }

    this.shards = new Map();
    for (let index = 0; index < shardCount; index += 1) {
      const id = `shard-${String(index).padStart(2, "0")}`;
      this.shards.set(id, new InMemoryShard(id));
    }

    this.router = new VirtualShardRouter([...this.shards.keys()]);
    this.customerLocations = new Map();
    this.orderLocations = new Map();
    this.operationSequence = 0;
  }

  recordEvent(type, detail) {
    this.emit("audit", {
      sequence: ++this.operationSequence,
      timestamp: new Date().toISOString(),
      type,
      ...detail,
    });
  }

  createCustomer(customer) {
    if (!customer || typeof customer !== "object") {
      throw new TypeError("A customer object is required.");
    }

    const { customerId, region, email } = customer;
    validateKey(customerId);

    if (typeof email !== "string" || !email.includes("@")) {
      throw new TypeError("A valid customer email is required.");
    }

    if (this.customerLocations.has(customerId)) {
      throw new DuplicateRecord(`Customer ${customerId} already exists.`);
    }

    const shardId = this.router.route(customerId);
    const shard = this.shards.get(shardId);

    shard.put(`customer:${customerId}`, {
      type: "customer",
      customerId,
      region,
      email,
    });

    this.customerLocations.set(customerId, shardId);
    this.recordEvent("customer.created", { customerId, shardId });
    return shardId;
  }

  getCustomer(customerId) {
    validateKey(customerId);
    const shardId = this.customerLocations.get(customerId);
    if (!shardId) throw new RecordNotFound(`Unknown customer ${customerId}.`);

    const customer = this.shards.get(shardId).get(`customer:${customerId}`);
    if (!customer) throw new RecordNotFound(`Customer ${customerId} is missing.`);
    return customer;
  }

  createOrder(order) {
    if (!order || typeof order !== "object") {
      throw new TypeError("An order object is required.");
    }

    const { orderId, customerId, amountCents, createdAt, status = "pending" } =
      order;

    validateKey(orderId);
    validateKey(customerId);

    if (!Number.isSafeInteger(amountCents) || amountCents < 0) {
      throw new RangeError("amountCents must be a non-negative safe integer.");
    }

    if (this.orderLocations.has(orderId)) {
      throw new DuplicateRecord(`Order ${orderId} already exists.`);
    }

    // The customer is checked before the write so an orphan order is rejected.
    this.getCustomer(customerId);
    const shardId = this.customerLocations.get(customerId);

    this.shards.get(shardId).put(`order:${orderId}`, {
      type: "order",
      orderId,
      customerId,
      amountCents,
      createdAt,
      status,
    });

    this.orderLocations.set(orderId, shardId);
    this.recordEvent("order.created", { orderId, customerId, shardId });
    return shardId;
  }

  getOrder(orderId) {
    validateKey(orderId);
    const shardId = this.orderLocations.get(orderId);
    if (!shardId) throw new RecordNotFound(`Unknown order ${orderId}.`);

    const order = this.shards.get(shardId).get(`order:${orderId}`);
    if (!order) throw new RecordNotFound(`Order ${orderId} is missing.`);
    return order;
  }

  ordersForCustomer(customerId) {
    validateKey(customerId);
    const shardId = this.customerLocations.get(customerId);
    if (!shardId) return [];

    const shard = this.shards.get(shardId);
    shard.assertAvailable();

    return [...shard.records.entries()]
      .filter(
        ([key, record]) =>
          key.startsWith("order:") && record.customerId === customerId
      )
      .map(([, record]) => structuredClone(record))
      .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
  }

  async allOrders({ concurrency = 4, timeoutMs = 2000 } = {}) {
    if (!Number.isInteger(concurrency) || concurrency < 1) {
      throw new RangeError("concurrency must be positive.");
    }
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      throw new RangeError("timeoutMs must be positive.");
    }

    const shardList = [...this.shards.values()];
    const results = [];
    let nextIndex = 0;

    // Workers bound the number of simultaneous shard requests.
    async function worker() {
      while (true) {
        const index = nextIndex++;
        if (index >= shardList.length) return;

        const shard = shardList[index];

        // A timeout prevents waiting indefinitely for a remote shard.
        const operation = new Promise((resolve, reject) => {
          queueMicrotask(() => {
            try {
              shard.assertAvailable();
              resolve(
                [...shard.records.entries()]
                  .filter(([key]) => key.startsWith("order:"))
                  .map(([, record]) => structuredClone(record))
              );
            } catch (error) {
              reject(error);
            }
          });
        });

        let timer;
        try {
          const records = await Promise.race([
            operation,
            new Promise((_, reject) => {
              timer = setTimeout(
                () => reject(new ShardUnavailable(`Timeout on ${shard.id}`)),
                timeoutMs
              );
            }),
          ]);
          results.push(...records);
        } finally {
          clearTimeout(timer);
        }
      }
    }

    await Promise.all(
      Array.from(
        { length: Math.min(concurrency, shardList.length) },
        () => worker()
      )
    );

    return results.sort((a, b) => a.orderId.localeCompare(b.orderId));
  }

  async revenueByCustomer() {
    const orders = await this.allOrders();
    const revenue = new Map();

    for (const order of orders) {
      revenue.set(
        order.customerId,
        (revenue.get(order.customerId) || 0) + order.amountCents
      );
    }

    return Object.fromEntries([...revenue.entries()].sort());
  }

  addShard(shardId) {
    validateKey(shardId);
    if (this.shards.has(shardId)) {
      throw new DuplicateRecord(`Shard ${shardId} already exists.`);
    }

    this.shards.set(shardId, new InMemoryShard(shardId));
    this.router.rebuild([...this.shards.keys()]);
    this.recordEvent("shard.registered", { shardId });
  }

  healthReport() {
    return [...this.shards.values()].map((shard) => ({
      shardId: shard.id,
      available: shard.available,
      recordCount: shard.records.size,
      version: shard.version,
    }));
  }

  validateLocations() {
    const errors = [];

    for (const [customerId, shardId] of this.customerLocations) {
      const shard = this.shards.get(shardId);
      if (!shard || !shard.records.has(`customer:${customerId}`)) {
        errors.push(`Customer ${customerId} has inconsistent location metadata.`);
      }
    }

    for (const [orderId, shardId] of this.orderLocations) {
      const shard = this.shards.get(shardId);
      if (!shard || !shard.records.has(`order:${orderId}`)) {
        errors.push(`Order ${orderId} has inconsistent location metadata.`);
      }
    }

    return errors;
  }
}

async function main() {
  const service = new ShardedOrderService(4);
  const auditEvents = [];

  service.on("audit", (event) => auditEvents.push(event));

  const customers = [
    { customerId: "cust-100", region: "north", email: "a@example.test" },
    { customerId: "cust-200", region: "south", email: "b@example.test" },
    { customerId: "cust-300", region: "west", email: "c@example.test" },
  ];

  for (const customer of customers) service.createCustomer(customer);

  const orders = [
    {
      orderId: "ord-001",
      customerId: "cust-100",
      amountCents: 1299,
      createdAt: "2026-10-01T09:00:00Z",
    },
    {
      orderId: "ord-002",
      customerId: "cust-100",
      amountCents: 4599,
      createdAt: "2026-10-02T11:30:00Z",
    },
    {
      orderId: "ord-003",
      customerId: "cust-200",
      amountCents: 899,
      createdAt: "2026-10-03T15:15:00Z",
    },
  ];

  for (const order of orders) service.createOrder(order);

  console.log("CUSTOMER-LOCAL QUERY");
  console.log(service.ordersForCustomer("cust-100"));

  console.log("\nASYNC SCATTER-GATHER");
  console.log(await service.allOrders({ concurrency: 2, timeoutMs: 1000 }));

  console.log("\nREVENUE BY CUSTOMER");
  console.log(await service.revenueByCustomer());

  console.log("\nSHARD HEALTH");
  console.log(service.healthReport());

  console.log("\nAUDIT EVENTS");
  console.log(`Recorded ${auditEvents.length} domain events.`);

  console.log("\nFAILURE HANDLING");
  try {
    service.createOrder({
      orderId: "ord-004",
      customerId: "cust-missing",
      amountCents: 100,
      createdAt: "2026-10-06T00:00:00Z",
    });
  } catch (error) {
    console.log(`${error.name}: ${error.message}`);
  }

  const shard = service.shards.values().next().value;
  shard.available = false;

  try {
    await service.allOrders();
  } catch (error) {
    console.log(`Scatter-gather rejected: ${error.message}`);
  } finally {
    shard.available = true;
  }

  console.log("\nMETADATA VALIDATION");
  console.log(service.validateLocations());

  assert.equal(service.ordersForCustomer("cust-100").length, 2);
  assert.equal((await service.allOrders()).length, 3);
  assert.equal(service.validateLocations().length, 0);

  assert.throws(
    () => service.createCustomer({
      customerId: "cust-100",
      region: "north",
      email: "duplicate@example.test",
    }),
    DuplicateRecord
  );

  assert.throws(
    () => service.createOrder({
      orderId: "ord-invalid",
      customerId: "cust-100",
      amountCents: -1,
      createdAt: "2026-10-06T00:00:00Z",
    }),
    RangeError
  );

  console.log("\nAll assertions passed.");
}

main().catch((error) => {
  console.error("Execution failed:", error);
  process.exitCode = 1;
});
