"use strict";

const { randomUUID } = require("crypto");
const { EventEmitter } = require("events");

class QueueError extends Error {}
class QueueNotFoundError extends QueueError {}
class ConsumerError extends QueueError {}

const MessageState = Object.freeze({
  READY: "ready",
  IN_FLIGHT: "in_flight",
  ACKED: "acked",
  DEAD_LETTERED: "dead_lettered"
});

class MessageBroker extends EventEmitter {
  constructor() {
    super();
    this.queues = new Map();
    this.messages = new Map();
    this.consumers = new Map();
  }

  declareQueue(name, { durable = true, maxAttempts = 3 } = {}) {
    if (!name || !name.trim()) {
      throw new TypeError("Queue name cannot be empty");
    }
    if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
      throw new TypeError("maxAttempts must be a positive integer");
    }

    if (this.queues.has(name)) {
      const existing = this.queues.get(name);
      if (existing.durable !== durable) {
        throw new QueueError("Existing queue has different durability");
      }
      return;
    }

    this.queues.set(name, {
      name,
      durable,
      maxAttempts,
      ready: [],
      deadLetters: []
    });

    this.emit("queue.declared", { name, durable, maxAttempts });
  }

  publish(queueName, payload, producerId, headers = {}) {
    const queue = this.queues.get(queueName);
    if (!queue) {
      throw new QueueNotFoundError(`Queue does not exist: ${queueName}`);
    }
    if (typeof payload !== "string" || payload.length === 0) {
      throw new TypeError("Payload must be a non-empty string");
    }
    if (!producerId) {
      throw new TypeError("producerId is required");
    }

    const message = {
      id: randomUUID(),
      payload,
      producerId,
      headers: { ...headers },
      createdAt: new Date().toISOString(),
      attempts: 0,
      state: MessageState.READY
    };

    this.messages.set(message.id, message);
    queue.ready.push(message.id);

    this.emit("message.published", {
      messageId: message.id,
      queue: queueName
    });

    return message.id;
  }

  registerConsumer({ id, queueName, prefetch = 1, handler }) {
    if (!id || this.consumers.has(id)) {
      throw new ConsumerError("Consumer ID must be unique");
    }

    if (!this.queues.has(queueName)) {
      throw new QueueNotFoundError(queueName);
    }

    if (!Number.isInteger(prefetch) || prefetch < 1) {
      throw new TypeError("prefetch must be a positive integer");
    }

    if (typeof handler !== "function") {
      throw new TypeError("handler must be a function");
    }

    this.consumers.set(id, {
      id,
      queueName,
      prefetch,
      handler,
      inFlight: new Set()
    });

    this.emit("consumer.registered", { id, queueName });
  }

  receive(consumerId) {
    const consumer = this.consumers.get(consumerId);
    if (!consumer) {
      throw new ConsumerError(`Unknown consumer: ${consumerId}`);
    }

    if (consumer.inFlight.size >= consumer.prefetch) {
      return null;
    }

    const queue = this.queues.get(consumer.queueName);

    while (queue.ready.length > 0) {
      const messageId = queue.ready.shift();
      const message = this.messages.get(messageId);

      if (!message || message.state !== MessageState.READY) {
        continue;
      }

      message.attempts += 1;
      message.state = MessageState.IN_FLIGHT;
      consumer.inFlight.add(messageId);

      this.emit("message.delivered", {
        consumerId,
        messageId,
        attempt: message.attempts
      });

      return message;
    }

    return null;
  }

  acknowledge(consumerId, messageId) {
    const consumer = this.consumers.get(consumerId);
    const message = this.messages.get(messageId);

    if (!consumer || !message || !consumer.inFlight.has(messageId)) {
      throw new ConsumerError("Invalid acknowledgement");
    }

    message.state = MessageState.ACKED;
    consumer.inFlight.delete(messageId);

    this.emit("message.acknowledged", {
      consumerId,
      messageId
    });
  }

  reject(consumerId, messageId) {
    const consumer = this.consumers.get(consumerId);
    const message = this.messages.get(messageId);

    if (!consumer || !message || !consumer.inFlight.has(messageId)) {
      throw new ConsumerError("Invalid rejection");
    }

    const queue = this.queues.get(consumer.queueName);
    consumer.inFlight.delete(messageId);

    if (message.attempts >= queue.maxAttempts) {
      message.state = MessageState.DEAD_LETTERED;
      queue.deadLetters.push(messageId);

      this.emit("message.deadLettered", {
        consumerId,
        messageId
      });
      return;
    }

    message.state = MessageState.READY;
    queue.ready.push(messageId);

    this.emit("message.requeued", {
      consumerId,
      messageId,
      nextAttempt: message.attempts + 1
    });
  }

  async drain(consumerId) {
    const consumer = this.consumers.get(consumerId);
    if (!consumer) {
      throw new ConsumerError(`Unknown consumer: ${consumerId}`);
    }

    let processed = 0;

    while (consumer.inFlight.size < consumer.prefetch) {
      const message = this.receive(consumerId);
      if (!message) {
        break;
      }

      try {
        const result = await consumer.handler(message);

        if (result === true) {
          this.acknowledge(consumerId, message.id);
        } else {
          this.reject(consumerId, message.id);
        }
      } catch (error) {
        this.emit("consumer.error", {
          consumerId,
          messageId: message.id,
          error: error.message
        });
        this.reject(consumerId, message.id);
      }

      processed += 1;
    }

    return processed;
  }

  stats(queueName) {
    const queue = this.queues.get(queueName);
    if (!queue) {
      throw new QueueNotFoundError(queueName);
    }

    let inFlight = 0;
    let acknowledged = 0;

    for (const message of this.messages.values()) {
      if (message.state === MessageState.IN_FLIGHT) inFlight += 1;
      if (message.state === MessageState.ACKED) acknowledged += 1;
    }

    return {
      ready: queue.ready.length,
      inFlight,
      acknowledged,
      deadLettered: queue.deadLetters.length
    };
  }
}

function createOrderHandler() {
  const completedOrders = new Set();
  const permanentlyFailingOrders = new Set(["ORD-3003"]);

  return async (message) => {
    const orderId = message.headers.orderId;

    if (!orderId) {
      console.error(`[INVALID] ${message.id}: missing orderId`);
      return false;
    }

    if (completedOrders.has(orderId)) {
      console.log(`[IDEMPOTENT] ${orderId}`);
      return true;
    }

    await new Promise((resolve) => setTimeout(resolve, 10));

    if (permanentlyFailingOrders.has(orderId)) {
      console.log(
        `[FAILURE] ${orderId}, attempt=${message.attempts}`
      );
      return false;
    }

    completedOrders.add(orderId);
    console.log(`[PROCESSED] ${orderId}: ${message.payload}`);
    return true;
  };
}

async function main() {
  const broker = new MessageBroker();

  broker.on("message.published", (event) => {
    console.log(`[EVENT] published ${event.messageId}`);
  });

  broker.on("message.deadLettered", (event) => {
    console.log(`[EVENT] dead-lettered ${event.messageId}`);
  });

  broker.on("consumer.error", (event) => {
    console.error(
      `[EVENT] consumer error ${event.consumerId}: ${event.error}`
    );
  });

  broker.declareQueue("orders", {
    durable: true,
    maxAttempts: 3
  });

  broker.publish(
    "orders",
    "Reserve inventory",
    "checkout-service",
    { orderId: "ORD-3001", type: "order.created" }
  );

  broker.publish(
    "orders",
    "Charge payment",
    "checkout-service",
    { orderId: "ORD-3002", type: "order.created" }
  );

  broker.publish(
    "orders",
    "Generate shipping label",
    "checkout-service",
    { orderId: "ORD-3003", type: "order.created" }
  );

  broker.registerConsumer({
    id: "worker-1",
    queueName: "orders",
    prefetch: 2,
    handler: createOrderHandler()
  });

  console.log("Initial:", broker.stats("orders"));

  for (let cycle = 1; cycle <= 5; cycle += 1) {
    const count = await broker.drain("worker-1");

    console.log(
      `Cycle ${cycle}: processed=${count}`,
      broker.stats("orders")
    );

    if (count === 0) {
      break;
    }
  }

  try {
    broker.publish("missing-queue", "bad", "producer");
  } catch (error) {
    console.log(`[VALIDATION] ${error.message}`);
  }

  const finalStats = broker.stats("orders");

  if (finalStats.deadLettered !== 1) {
    throw new Error("Expected one dead-lettered message");
  }

  if (finalStats.acknowledged !== 2) {
    throw new Error("Expected two acknowledged messages");
  }

  console.log("Final:", finalStats);
}

main().catch((error) => {
  console.error("Fatal broker simulation error:", error);
  process.exitCode = 1;
});
