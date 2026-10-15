"use strict";

/*
 * Idempotency in an asynchronous JavaScript API.
 *
 * This program models an order-creation endpoint. JavaScript is especially
 * useful here because retries often interact with promises, timers, network
 * failures, and concurrent event-loop callbacks.
 *
 * The implementation deliberately separates:
 *   - the idempotency key from the request fingerprint
 *   - request ownership from business-side effects
 *   - a completed response from a new execution
 *   - a transient failure before a side effect from a timeout after it
 *
 * Run with Node.js 18+.
 */

const crypto = require("crypto");

function canonicalJson(value) {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }

  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }

  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
}

function fingerprint(payload) {
  return crypto
    .createHash("sha256")
    .update(canonicalJson(payload), "utf8")
    .digest("hex");
}

class IdempotencyConflict extends Error {
  constructor(message) {
    super(message);
    this.name = "IdempotencyConflict";
  }
}

class IdempotencyInProgress extends Error {
  constructor(message) {
    super(message);
    this.name = "IdempotencyInProgress";
  }
}

class MemoryIdempotencyStore {
  constructor(ttlMs = 5 * 60 * 1000) {
    this.ttlMs = ttlMs;
    this.records = new Map();
  }

  purgeExpired(key) {
    const record = this.records.get(key);
    if (record && record.expiresAt <= Date.now()) {
      this.records.delete(key);
    }
  }

  claim(key, requestHash) {
    this.purgeExpired(key);

    const existing = this.records.get(key);

    if (existing) {
      if (existing.requestHash !== requestHash) {
        throw new IdempotencyConflict(
          "The idempotency key was reused with different request data."
        );
      }

      if (existing.state === "COMPLETED") {
        return {
          kind: "REPLAY",
          response: {
            ...existing.response,
            body: {
              ...existing.response.body,
              idempotentReplay: true,
            },
          },
        };
      }

      throw new IdempotencyInProgress(
        "Another request is currently processing this idempotency key."
      );
    }

    const record = {
      key,
      requestHash,
      state: "PROCESSING",
      response: null,
      createdAt: Date.now(),
      expiresAt: Date.now() + this.ttlMs,
    };

    /*
     * JavaScript Map.set is synchronous. Once claim() returns, another
     * synchronous caller cannot interleave between the existence check and
     * insertion. Async work begins only after this atomic-looking local
     * critical section has completed.
     */
    this.records.set(key, record);

    return { kind: "EXECUTE", record };
  }

  complete(key, response) {
    const record = this.records.get(key);

    if (!record) {
      throw new Error("Idempotency record disappeared before completion.");
    }

    record.state = "COMPLETED";
    record.response = response;
  }

  abort(key) {
    const record = this.records.get(key);

    if (record && record.state === "PROCESSING") {
      this.records.delete(key);
    }
  }
}

class OrderService {
  constructor() {
    this.orders = new Map();
  }

  async createOrder(customerId, amountCents) {
    await new Promise((resolve) => setTimeout(resolve, 20));

    if (amountCents <= 0) {
      throw new Error("Order amount must be positive.");
    }

    const orderId = `ord_${crypto.randomBytes(8).toString("hex")}`;

    const order = {
      orderId,
      customerId,
      amountCents,
      state: "CONFIRMED",
      createdAt: new Date().toISOString(),
    };

    this.orders.set(orderId, order);
    return { ...order };
  }

  count() {
    return this.orders.size;
  }
}

class IdempotentOrderApi {
  constructor(store, orderService) {
    this.store = store;
    this.orderService = orderService;
  }

  async postOrder({
    idempotencyKey,
    customerId,
    amountCents,
    failureMode = null,
  }) {
    if (
      typeof idempotencyKey !== "string" ||
      idempotencyKey.length === 0 ||
      idempotencyKey.length > 255
    ) {
      return {
        status: 400,
        body: { error: "Invalid idempotency key." },
      };
    }

    if (typeof customerId !== "string" || customerId.length === 0) {
      return {
        status: 400,
        body: { error: "customerId is required." },
      };
    }

    if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
      return {
        status: 400,
        body: { error: "amountCents must be a positive safe integer." },
      };
    }

    const requestHash = fingerprint({
      customerId,
      amountCents,
    });

    let claim;

    try {
      claim = this.store.claim(idempotencyKey, requestHash);
    } catch (error) {
      if (error instanceof IdempotencyConflict) {
        return {
          status: 409,
          body: { error: error.message },
        };
      }

      if (error instanceof IdempotencyInProgress) {
        return {
          status: 409,
          body: { error: error.message },
        };
      }

      throw error;
    }

    if (claim.kind === "REPLAY") {
      return claim.response;
    }

    try {
      if (failureMode === "before_side_effect") {
        throw new Error("Transient upstream failure before order creation.");
      }

      const order = await this.orderService.createOrder(
        customerId,
        amountCents
      );

      const response = {
        status: 201,
        body: order,
      };

      /*
       * The durable idempotency record must be completed before treating the
       * request as safely retryable. In a real service this update and the
       * business-side effect normally belong to one database transaction or
       * coordinated durable workflow.
       */
      this.store.complete(idempotencyKey, response);

      if (failureMode === "after_side_effect") {
        throw new Error(
          "Simulated response timeout after the order was durably created."
        );
      }

      return response;
    } catch (error) {
      /*
       * Do not blindly delete a key when the side effect may already exist.
       * Here the after_side_effect case has already completed the record, so
       * abort() leaves it intact.
       */
      const current = this.store.records.get(idempotencyKey);

      if (current && current.state === "PROCESSING") {
        this.store.abort(idempotencyKey);
      }

      throw error;
    }
  }
}

async function basicRetryDemo() {
  console.log("\n=== Basic safe retry ===");

  const store = new MemoryIdempotencyStore();
  const service = new OrderService();
  const api = new IdempotentOrderApi(store, service);

  const request = {
    idempotencyKey: "order-request-001",
    customerId: "customer-100",
    amountCents: 2500,
  };

  const first = await api.postOrder(request);
  const retry = await api.postOrder(request);

  console.log("First response:", first);
  console.log("Retry response:", retry);
  console.log("Orders created:", service.count());
}

async function conflictingReuseDemo() {
  console.log("\n=== Conflicting reuse ===");

  const store = new MemoryIdempotencyStore();
  const service = new OrderService();
  const api = new IdempotentOrderApi(store, service);

  await api.postOrder({
    idempotencyKey: "order-request-002",
    customerId: "customer-100",
    amountCents: 2500,
  });

  const response = await api.postOrder({
    idempotencyKey: "order-request-002",
    customerId: "customer-100",
    amountCents: 5000,
  });

  console.log(response);
}

async function timeoutRecoveryDemo() {
  console.log("\n=== Timeout after side effect ===");

  const store = new MemoryIdempotencyStore();
  const service = new OrderService();
  const api = new IdempotentOrderApi(store, service);

  try {
    await api.postOrder({
      idempotencyKey: "order-request-003",
      customerId: "customer-200",
      amountCents: 7000,
      failureMode: "after_side_effect",
    });
  } catch (error) {
    console.log("Caller observed:", error.message);
  }

  const recovered = await api.postOrder({
    idempotencyKey: "order-request-003",
    customerId: "customer-200",
    amountCents: 7000,
  });

  console.log("Recovered response:", recovered);
  console.log("Orders created:", service.count());
}

async function concurrentRequestsDemo() {
  console.log("\n=== Concurrent duplicate requests ===");

  const store = new MemoryIdempotencyStore();
  const service = new OrderService();
  const api = new IdempotentOrderApi(store, service);

  const request = {
    idempotencyKey: "order-request-concurrent",
    customerId: "customer-300",
    amountCents: 8100,
  };

  /*
   * Promise.all starts the calls without waiting for each one. Only the first
   * call should own execution. Other calls observe PROCESSING and receive a
   * conflict response in this intentionally simple policy.
   */
  const responses = await Promise.all(
    Array.from({ length: 5 }, () => api.postOrder(request).catch((error) => ({
      status: 500,
      body: { error: error.message },
    })))
  );

  console.log(responses);
  console.log("Orders created:", service.count());
}

async function fingerprintDemo() {
  console.log("\n=== Canonical fingerprints ===");

  const a = fingerprint({
    amountCents: 1000,
    customerId: "customer-a",
  });

  const b = fingerprint({
    customerId: "customer-a",
    amountCents: 1000,
  });

  const c = fingerprint({
    customerId: "customer-a",
    amountCents: 1001,
  });

  console.log("Equivalent payloads match:", a === b);
  console.log("Different payloads match:", a === c);
}

async function main() {
  await basicRetryDemo();
  await conflictingReuseDemo();
  await timeoutRecoveryDemo();
  await concurrentRequestsDemo();
  await fingerprintDemo();
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exitCode = 1;
});
