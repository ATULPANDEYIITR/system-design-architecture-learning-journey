"use strict";

/*
 * Consistent hashing in Node.js.
 *
 * This implementation uses SHA-256 from the Node.js standard library and
 * represents ring positions as BigInt values. It demonstrates:
 * - physical nodes and virtual nodes
 * - clockwise ownership
 * - binary-search lookup
 * - topology changes
 * - event-driven membership changes
 * - weighted virtual-node capacity
 * - reviewable routing diagnostics
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

const RING_SIZE = 1n << 64n;

function stableHash(value) {
  const digest = crypto.createHash("sha256").update(value, "utf8").digest();
  return digest.readBigUInt64BE(0);
}

function validateKey(key) {
  if (typeof key !== "string" || key.length === 0) {
    throw new TypeError("routing key must be a non-empty string");
  }
}

class HashRing {
  constructor() {
    this.entries = [];
    this.nodes = new Map();
  }

  addNode(nodeId, virtualNodes = 128) {
    if (typeof nodeId !== "string" || nodeId.trim() === "") {
      throw new TypeError("nodeId must be a non-empty string");
    }

    if (!Number.isInteger(virtualNodes) || virtualNodes < 1) {
      throw new RangeError("virtualNodes must be a positive integer");
    }

    if (this.nodes.has(nodeId)) {
      throw new Error(`node already exists: ${nodeId}`);
    }

    const created = [];
    const occupied = new Set(this.entries.map((entry) => entry.position.toString()));

    for (let replica = 0; replica < virtualNodes; replica += 1) {
      const position = stableHash(`${nodeId}#vn:${replica}`);
      const key = position.toString();

      if (occupied.has(key)) {
        throw new Error(`hash collision while adding ${nodeId}`);
      }

      occupied.add(key);
      created.push({
        position,
        nodeId,
        replica
      });
    }

    this.entries.push(...created);
    this.entries.sort((a, b) => {
      if (a.position < b.position) return -1;
      if (a.position > b.position) return 1;
      return 0;
    });

    this.nodes.set(nodeId, virtualNodes);
  }

  removeNode(nodeId) {
    if (!this.nodes.has(nodeId)) {
      throw new Error(`node does not exist: ${nodeId}`);
    }

    this.entries = this.entries.filter((entry) => entry.nodeId !== nodeId);
    this.nodes.delete(nodeId);
  }

  findOwner(hashValue) {
    if (this.entries.length === 0) {
      throw new Error("cannot route without ring members");
    }

    let low = 0;
    let high = this.entries.length;

    // Binary search finds the first virtual node clockwise from the key.
    while (low < high) {
      const middle = Math.floor((low + high) / 2);

      if (this.entries[middle].position >= hashValue) {
        high = middle;
      } else {
        low = middle + 1;
      }
    }

    const index = low === this.entries.length ? 0 : low;
    return this.entries[index].nodeId;
  }

  ownerForKey(key) {
    validateKey(key);
    return this.findOwner(stableHash(key));
  }

  snapshot() {
    return this.entries.map((entry) => ({
      position: entry.position.toString(),
      nodeId: entry.nodeId,
      replica: entry.replica
    }));
  }

  distribution(keys) {
    const result = new Map();

    for (const nodeId of this.nodes.keys()) {
      result.set(nodeId, 0);
    }

    for (const key of keys) {
      const owner = this.ownerForKey(key);
      result.set(owner, result.get(owner) + 1);
    }

    return Object.fromEntries(result);
  }
}

class ObservableHashRing extends EventEmitter {
  constructor() {
    super();
    this.ring = new HashRing();
  }

  addNode(nodeId, virtualNodes = 128) {
    this.ring.addNode(nodeId, virtualNodes);
    this.emit("membershipChanged", {
      operation: "added",
      nodeId,
      virtualNodes
    });
  }

  removeNode(nodeId) {
    this.ring.removeNode(nodeId);
    this.emit("membershipChanged", {
      operation: "removed",
      nodeId
    });
  }

  ownerForKey(key) {
    return this.ring.ownerForKey(key);
  }
}

function buildKeys(prefix, count) {
  return Array.from(
    { length: count },
    (_, index) => `${prefix}:${index}`
  );
}

function movedKeys(before, after) {
  if (before.length !== after.length) {
    throw new Error("ownership arrays must have equal lengths");
  }

  let moved = 0;

  for (let index = 0; index < before.length; index += 1) {
    if (before[index] !== after[index]) {
      moved += 1;
    }
  }

  return moved;
}

async function simulateAsyncRouting(ring, keys) {
  // Promise scheduling models an asynchronous request path without adding
  // external networking dependencies.
  const results = await Promise.all(
    keys.map(async (key) => ({
      key,
      owner: ring.ownerForKey(key)
    }))
  );

  return results;
}

function printDistribution(distribution) {
  for (const [node, count] of Object.entries(distribution)) {
    console.log(`${node.padEnd(15)} ${String(count).padStart(7)}`);
  }
}

async function main() {
  console.log("=== Event-driven membership ===");

  const ring = new ObservableHashRing();

  ring.on("membershipChanged", (event) => {
    console.log(
      `membership ${event.operation}: ${event.nodeId}` +
      (event.virtualNodes ? ` (${event.virtualNodes} virtual nodes)` : "")
    );
  });

  ring.addNode("api-a", 128);
  ring.addNode("api-b", 128);
  ring.addNode("api-c", 128);

  console.log("\n=== Routing ===");

  for (const key of [
    "tenant:india:001",
    "tenant:india:002",
    "session:91ab",
    "cache:product:500"
  ]) {
    console.log(`${key.padEnd(25)} -> ${ring.ownerForKey(key)}`);
  }

  console.log("\n=== Virtual-node distribution ===");

  const keys = buildKeys("tenant", 100000);
  printDistribution(ring.ring.distribution(keys));

  console.log("\n=== Addition and movement ===");

  const before = keys.map((key) => ring.ownerForKey(key));

  ring.addNode("api-d", 128);

  const after = keys.map((key) => ring.ownerForKey(key));
  const moved = movedKeys(before, after);

  console.log(`Moved keys: ${moved}/${keys.length}`);
  console.log(`Movement ratio: ${(moved / keys.length * 100).toFixed(2)}%`);

  console.log("\n=== Asynchronous routing ===");

  const routed = await simulateAsyncRouting(ring, keys.slice(0, 5));
  console.table(routed);

  console.log("\n=== Removal ===");

  ring.removeNode("api-b");
  console.log("Distribution after api-b removal:");
  printDistribution(ring.ring.distribution(keys));

  console.log("\n=== Ring diagnostics ===");

  for (const entry of ring.ring.snapshot().slice(0, 8)) {
    console.log(
      `position=${entry.position} node=${entry.nodeId} replica=${entry.replica}`
    );
  }

  console.log("\n=== Weighted capacity ===");

  const weighted = new HashRing();
  weighted.addNode("small", 64);
  weighted.addNode("medium", 128);
  weighted.addNode("large", 256);

  printDistribution(weighted.distribution(keys));

  console.log("\n=== Failure handling ===");

  try {
    weighted.ownerForKey("");
  } catch (error) {
    console.log(`Invalid key rejected: ${error.message}`);
  }

  try {
    weighted.addNode("small", 64);
  } catch (error) {
    console.log(`Duplicate node rejected: ${error.message}`);
  }
}

main().catch((error) => {
  console.error(`Fatal error: ${error.message}`);
  process.exitCode = 1;
});
