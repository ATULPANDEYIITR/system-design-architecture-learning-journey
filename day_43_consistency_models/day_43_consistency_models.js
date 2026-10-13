"use strict";

/*
 * Consistency Models: Strong, Eventual, and Causal Consistency
 *
 * Run with:
 *   node consistency-models.js
 *
 * This event-driven simulation emphasizes asynchronous message delivery,
 * per-client causal context, retry safety, and consistency-aware reads.
 */

const assert = require("node:assert/strict");

class ConsistencyError extends Error {}
class UnavailableError extends ConsistencyError {}
class CausalDependencyError extends ConsistencyError {}
class OperationConflictError extends ConsistencyError {}

function normalizeVector(vector = {}) {
  return Object.fromEntries(
    Object.entries(vector)
      .filter(([, count]) => Number.isInteger(count) && count > 0)
      .sort(([left], [right]) => left.localeCompare(right))
  );
}

function vectorGet(vector, replica) {
  return vector[replica] ?? 0;
}

function vectorMerge(left, right) {
  const merged = {};
  for (const replica of new Set([...Object.keys(left), ...Object.keys(right)])) {
    merged[replica] = Math.max(
      vectorGet(left, replica),
      vectorGet(right, replica)
    );
  }
  return normalizeVector(merged);
}

function vectorDominates(left, right) {
  return Object.entries(right).every(
    ([replica, count]) => vectorGet(left, replica) >= count
  );
}

function vectorConcurrent(left, right) {
  return !vectorDominates(left, right) && !vectorDominates(right, left);
}

function vectorIncrement(vector, replica) {
  const result = { ...vector };
  result[replica] = vectorGet(result, replica) + 1;
  return normalizeVector(result);
}

function sameValue(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function sameOperationContent(left, right) {
  return (
    left.id === right.id &&
    left.replicaId === right.replicaId &&
    left.key === right.key &&
    sameValue(left.value, right.value) &&
    sameValue(left.dependencies, right.dependencies) &&
    left.tombstone === right.tombstone
  );
}

class Replica {
  constructor(id) {
    this.id = id;
    this.available = true;
    this.records = new Map();
    this.context = {};
    this.applied = new Set();
  }

  read(key) {
    const record = this.records.get(key);
    return !record || record.tombstone ? null : record.value;
  }

  hasObserved(context) {
    return vectorDominates(this.context, context);
  }
}

class ConsistencyCluster {
  constructor({ model, replicaIds = ["A", "B", "C"], leader = "A" }) {
    if (!["strong", "eventual", "causal"].includes(model)) {
      throw new TypeError(`Unsupported consistency model: ${model}`);
    }
    if (!replicaIds.length || new Set(replicaIds).size !== replicaIds.length) {
      throw new TypeError("Replica identifiers must be unique and nonempty.");
    }
    if (!replicaIds.includes(leader)) {
      throw new TypeError("The leader must belong to the cluster.");
    }

    this.model = model;
    this.leaderId = leader;
    this.replicas = new Map(replicaIds.map(id => [id, new Replica(id)]));
    this.registry = new Map();
    this.queue = [];
    this.sequence = new Map();
    this.clock = 0;
  }

  replica(id) {
    const replica = this.replicas.get(id);
    if (!replica) throw new TypeError(`Unknown replica: ${id}`);
    return replica;
  }

  setAvailability(id, available) {
    this.replica(id).available = Boolean(available);
  }

  createOperation({ replicaId, key, value, id, dependencies = {}, tombstone = false }) {
    if (typeof key !== "string" || key.trim() === "") {
      throw new TypeError("Keys must be nonempty strings.");
    }
    if (typeof id !== "string" || id.trim() === "") {
      throw new TypeError("Operation IDs must be nonempty strings.");
    }

    const replica = this.replica(replicaId);
    const normalizedDependencies = normalizeVector(dependencies);
    const candidate = {
      id,
      replicaId,
      key,
      value,
      dependencies: normalizedDependencies,
      tombstone,
    };

    const previous = this.registry.get(id);
    if (previous) {
      if (sameOperationContent(previous, candidate)) return previous;
      throw new OperationConflictError(`Operation ID ${id} was reused.`);
    }

    const nextSequence = (this.sequence.get(replicaId) ?? 0) + 1;
    this.sequence.set(replicaId, nextSequence);
    const base = vectorMerge(replica.context, normalizedDependencies);

    const operation = Object.freeze({
      ...candidate,
      sequence: nextSequence,
      vector: vectorIncrement(base, replicaId),
      timestamp: ++this.clock,
    });

    this.registry.set(id, operation);
    return operation;
  }

  apply(replica, operation) {
    if (replica.applied.has(operation.id)) return false;

    if (
      this.model === "causal" &&
      !replica.hasObserved(operation.dependencies)
    ) {
      throw new CausalDependencyError(
        `${replica.id} has not observed dependencies of ${operation.id}.`
      );
    }

    const current = replica.records.get(operation.key);
    replica.records.set(
      operation.key,
      this.resolveConflict(current, operation)
    );
    replica.applied.add(operation.id);
    replica.context = vectorMerge(replica.context, operation.vector);
    return true;
  }

  resolveConflict(current, incoming) {
    if (!current) return incoming;

    if (vectorDominates(incoming.vector, current.vector)) {
      if (sameValue(incoming.vector, current.vector)) {
        return this.compareTieBreak(current, incoming) <= 0 ? incoming : current;
      }
      return incoming;
    }

    if (vectorDominates(current.vector, incoming.vector)) return current;

    // A deterministic winner ensures convergence but may discard one
    // concurrent value. This is not an appropriate policy for every domain.
    return this.compareTieBreak(current, incoming) <= 0 ? incoming : current;
  }

  compareTieBreak(left, right) {
    if (left.timestamp !== right.timestamp) {
      return left.timestamp - right.timestamp;
    }
    return `${left.replicaId}:${left.id}`.localeCompare(
      `${right.replicaId}:${right.id}`
    );
  }

  write({ replicaId, key, value, id, dependencies = {}, tombstone = false }) {
    const origin = this.replica(replicaId);
    if (!origin.available) {
      throw new UnavailableError(`Replica ${replicaId} is unavailable.`);
    }

    if (this.model === "strong") {
      const leader = this.replica(this.leaderId);
      if (!leader.available) {
        throw new UnavailableError("The authoritative leader is unavailable.");
      }

      const operation = this.createOperation({
        replicaId: this.leaderId,
        key,
        value,
        id,
        dependencies,
        tombstone,
      });

      // This in-memory simulation applies the operation to every live replica
      // before returning. Real strong consistency needs a consensus protocol.
      for (const replica of this.replicas.values()) {
        if (replica.available) this.apply(replica, operation);
      }
      return operation;
    }

    const operation = this.createOperation({
      replicaId,
      key,
      value,
      id,
      dependencies,
      tombstone,
    });

    this.apply(origin, operation);
    this.queue.push(operation);
    return operation;
  }

  read({ replicaId, key, minimumContext = null }) {
    const replica = this.replica(replicaId);
    if (!replica.available) {
      throw new UnavailableError(`Replica ${replicaId} is unavailable.`);
    }

    if (this.model === "strong") {
      const leader = this.replica(this.leaderId);
      if (!leader.available) {
        throw new UnavailableError("The authoritative leader is unavailable.");
      }
      return leader.read(key);
    }

    if (minimumContext && !replica.hasObserved(minimumContext)) {
      throw new CausalDependencyError(
        `Replica ${replicaId} is behind the requested causal context.`
      );
    }

    return replica.read(key);
  }

  deliver(index = 0) {
    if (!Number.isInteger(index) || index < 0 || index >= this.queue.length) {
      return false;
    }

    const [operation] = this.queue.splice(index, 1);
    let deferred = false;

    for (const replica of this.replicas.values()) {
      if (!replica.available || replica.applied.has(operation.id)) continue;
      try {
        this.apply(replica, operation);
      } catch (error) {
        if (error instanceof CausalDependencyError) {
          deferred = true;
        } else {
          throw error;
        }
      }
    }

    if (deferred) this.queue.push(operation);
    return true;
  }

  async flush({ maxSteps = 1000, yieldEvery = 20 } = {}) {
    let steps = 0;

    while (this.queue.length && steps < maxSteps) {
      const before = this.queue.length;
      this.deliver(0);
      steps++;

      // Yield to the event loop during large simulations rather than blocking
      // other asynchronous tasks with a long synchronous replication loop.
      if (steps % yieldEvery === 0) {
        await new Promise(resolve => setImmediate(resolve));
      }

      if (this.queue.length === before) {
        let progress = false;

        for (let index = 1; index < this.queue.length; index++) {
          const operation = this.queue[index];
          const prerequisiteAvailable = [...this.replicas.values()].some(
            replica =>
              replica.available &&
              replica.hasObserved(operation.dependencies)
          );

          if (prerequisiteAvailable) {
            this.deliver(index);
            progress = true;
            steps++;
            break;
          }
        }

        if (!progress) break;
      }
    }

    return {
      steps,
      pending: this.queue.length,
      converged: this.queue.length === 0,
    };
  }

  async antiEntropy() {
    const operations = [...this.registry.values()].sort(
      (left, right) =>
        left.timestamp - right.timestamp || left.id.localeCompare(right.id)
    );

    let changed = true;
    let passes = 0;

    while (changed && passes < operations.length + 1) {
      changed = false;
      passes++;

      for (const operation of operations) {
        for (const replica of this.replicas.values()) {
          if (!replica.available || replica.applied.has(operation.id)) continue;

          try {
            changed = this.apply(replica, operation) || changed;
          } catch (error) {
            if (!(error instanceof CausalDependencyError)) throw error;
          }
        }
      }
    }

    this.queue = this.queue.filter(operation =>
      [...this.replicas.values()].some(
        replica => replica.available && !replica.applied.has(operation.id)
      )
    );
  }

  snapshot() {
    return Object.fromEntries(
      [...this.replicas.entries()].map(([id, replica]) => [
        id,
        {
          values: Object.fromEntries(
            [...replica.records.entries()].map(([key, operation]) => [
              key,
              operation.tombstone ? null : operation.value,
            ])
          ),
          context: replica.context,
        },
      ])
    );
  }
}

async function demonstrateStrongConsistency() {
  console.log("\n=== Strong consistency ===");
  const cluster = new ConsistencyCluster({ model: "strong" });

  cluster.write({
    replicaId: "A",
    key: "inventory:router-17",
    value: 12,
    id: "strong-1",
  });

  assert.equal(
    cluster.read({ replicaId: "C", key: "inventory:router-17" }),
    12
  );

  cluster.setAvailability("A", false);
  assert.throws(
    () => cluster.read({ replicaId: "B", key: "inventory:router-17" }),
    UnavailableError
  );

  console.log("An unavailable leader prevents authoritative reads.");
}

async function demonstrateEventualConsistency() {
  console.log("\n=== Eventual consistency ===");
  const cluster = new ConsistencyCluster({ model: "eventual" });

  cluster.write({
    replicaId: "A",
    key: "deployment:region",
    value: "ap-south",
    id: "event-1",
  });

  assert.equal(cluster.read({ replicaId: "A", key: "deployment:region" }), "ap-south");
  assert.equal(cluster.read({ replicaId: "B", key: "deployment:region" }), null);

  console.log("Before replication:", cluster.snapshot());
  console.log("Replication:", await cluster.flush());
  assert.equal(cluster.read({ replicaId: "B", key: "deployment:region" }), "ap-south");

  // Concurrent local writes exercise deterministic conflict resolution.
  cluster.write({
    replicaId: "A",
    key: "profile:theme",
    value: "dark",
    id: "event-2",
  });
  cluster.write({
    replicaId: "B",
    key: "profile:theme",
    value: "light",
    id: "event-3",
  });

  await cluster.flush();
  assert.equal(
    cluster.read({ replicaId: "A", key: "profile:theme" }),
    cluster.read({ replicaId: "C", key: "profile:theme" })
  );

  console.log("After conflict resolution:", cluster.snapshot());
}

async function demonstrateCausalConsistency() {
  console.log("\n=== Causal consistency ===");
  const cluster = new ConsistencyCluster({ model: "causal" });

  const created = cluster.write({
    replicaId: "A",
    key: "incident:INC-804",
    value: { state: "opened" },
    id: "causal-1",
  });

  const assigned = cluster.write({
    replicaId: "A",
    key: "incident:INC-804:assignment",
    value: { team: "network-operations" },
    id: "causal-2",
    dependencies: created.vector,
  });

  // Intentionally deliver the assignment before the incident creation.
  cluster.deliver(1);
  assert.equal(cluster.read({ replicaId: "B", key: "incident:INC-804:assignment" }), null);

  await cluster.flush();
  assert.equal(
    cluster.read({ replicaId: "B", key: "incident:INC-804:assignment" }).team,
    "network-operations"
  );

  // A client context prevents a stale replica from satisfying a read.
  cluster.setAvailability("C", false);
  cluster.replicas.get("C").available = true;
  cluster.replicas.get("C").records.clear();
  cluster.replicas.get("C").applied.clear();
  cluster.replicas.get("C").context = {};

  assert.throws(
    () => cluster.read({
      replicaId: "C",
      key: "incident:INC-804",
      minimumContext: assigned.vector,
    }),
    CausalDependencyError
  );

  console.log("Causal dependency:", created.vector);
  console.log("Dependent event:", assigned.vector);
  console.log("Replica B observes the incident before its assignment.");
}

async function demonstrateIdempotencyAndDeletion() {
  console.log("\n=== Idempotency and deletion ===");
  const cluster = new ConsistencyCluster({ model: "eventual" });

  const request = {
    replicaId: "A",
    key: "ticket:105",
    value: "open",
    id: "ticket-write-1",
  };

  const first = cluster.write(request);
  const retry = cluster.write(request);
  assert.equal(first, retry);

  assert.throws(
    () => cluster.write({ ...request, value: "closed" }),
    OperationConflictError
  );

  cluster.write({
    replicaId: "A",
    key: "ticket:105",
    value: null,
    id: "ticket-delete-2",
    dependencies: first.vector,
    tombstone: true,
  });

  await cluster.flush();
  assert.equal(cluster.read({ replicaId: "B", key: "ticket:105" }), null);
  console.log("Deletion replicated using a tombstone.");
}

async function main() {
  await demonstrateStrongConsistency();
  await demonstrateEventualConsistency();
  await demonstrateCausalConsistency();
  await demonstrateIdempotencyAndDeletion();
  console.log("\nAll JavaScript consistency tests passed.");
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
