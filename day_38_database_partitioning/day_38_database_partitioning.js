"use strict";

/*
 * Database Partitioning: Horizontal and Vertical Partitioning
 *
 * This Node.js program models partition routing and query behavior without
 * external dependencies. It deliberately uses JavaScript-specific features:
 * Maps for partition storage, immutable object creation, event-driven
 * partition events, asynchronous query simulation, and policy validation.
 *
 * The model covers:
 * - Horizontal range partitioning
 * - List partitioning
 * - Hash partitioning
 * - Vertical partitioning
 * - Composite partitioning
 * - Partition pruning
 * - Boundary validation
 * - Asynchronous operational behavior
 * - Error handling and observability
 */

const crypto = require("crypto");
const { EventEmitter } = require("events");

class PartitioningError extends Error {}
class PartitionNotFoundError extends PartitioningError {}
class PartitionConstraintError extends PartitioningError {}

function parseDate(value) {
  const result = new Date(`${value}T00:00:00Z`);

  if (Number.isNaN(result.getTime())) {
    throw new TypeError(`Invalid date: ${value}`);
  }

  return result;
}

function dateKey(value) {
  return value.toISOString().slice(0, 10);
}

function createOrder({
  orderId,
  customerId,
  orderDate,
  region,
  status,
  amount,
}) {
  if (!Number.isInteger(orderId) || orderId <= 0) {
    throw new TypeError("orderId must be a positive integer");
  }

  if (!Number.isInteger(customerId) || customerId <= 0) {
    throw new TypeError("customerId must be a positive integer");
  }

  if (!Number.isFinite(amount) || amount < 0) {
    throw new TypeError("amount must be a non-negative number");
  }

  const allowedStatuses = new Set([
    "PENDING",
    "PAID",
    "SHIPPED",
    "CANCELLED",
  ]);

  if (!allowedStatuses.has(status)) {
    throw new TypeError(`Unsupported order status: ${status}`);
  }

  return Object.freeze({
    orderId,
    customerId,
    orderDate: parseDate(orderDate),
    region,
    status,
    amount,
  });
}

class RangePartition {
  constructor(name, start, end) {
    this.name = name;
    this.start = parseDate(start);
    this.end = parseDate(end);
    this.rows = [];

    if (this.start >= this.end) {
      throw new PartitionConstraintError(
        `Invalid interval for ${name}: lower bound must precede upper bound`
      );
    }
  }

  accepts(value) {
    return value >= this.start && value < this.end;
  }

  insert(order) {
    if (!this.accepts(order.orderDate)) {
      throw new PartitionConstraintError(
        `Order ${order.orderId} violates ${this.name} boundary`
      );
    }

    this.rows.push(order);
  }
}

class HorizontalPartitionStore extends EventEmitter {
  constructor(partitions) {
    super();
    this.partitions = partitions;
    this.validateNoOverlap();
  }

  validateNoOverlap() {
    const ordered = [...this.partitions].sort(
      (a, b) => a.start.getTime() - b.start.getTime()
    );

    for (let index = 1; index < ordered.length; index += 1) {
      if (ordered[index - 1].end > ordered[index].start) {
        throw new PartitionConstraintError(
          `Overlapping partitions: ${ordered[index - 1].name} and ${ordered[index].name}`
        );
      }
    }
  }

  route(order) {
    const partition = this.partitions.find((candidate) =>
      candidate.accepts(order.orderDate)
    );

    if (!partition) {
      throw new PartitionNotFoundError(
        `No partition covers ${dateKey(order.orderDate)}`
      );
    }

    return partition;
  }

  insert(order) {
    const partition = this.route(order);
    partition.insert(order);

    this.emit("rowInserted", {
      orderId: order.orderId,
      partition: partition.name,
    });

    return partition.name;
  }

  queryDateRange(startValue, endValue) {
    const start = parseDate(startValue);
    const end = parseDate(endValue);

    if (start >= end) {
      throw new RangeError("Query start must precede query end");
    }

    /*
     * Partition pruning:
     * A partition whose interval does not overlap the requested interval
     * cannot contain a matching row, so it is never scanned.
     */
    const selected = this.partitions.filter(
      (partition) => partition.start < end && start < partition.end
    );

    const rows = selected.flatMap((partition) =>
      partition.rows.filter(
        (order) => order.orderDate >= start && order.orderDate < end
      )
    );

    return {
      partitionsScanned: selected.map((partition) => partition.name),
      rows,
    };
  }
}

class ListPartitionRouter {
  constructor(mapping, defaultPartition = null) {
    this.mapping = new Map(Object.entries(mapping));
    this.defaultPartition = defaultPartition;
  }

  route(value) {
    if (this.mapping.has(value)) {
      return this.mapping.get(value);
    }

    if (this.defaultPartition !== null) {
      return this.defaultPartition;
    }

    throw new PartitionNotFoundError(
      `No LIST partition exists for ${value}`
    );
  }
}

class HashPartitionRouter {
  constructor(bucketCount) {
    if (!Number.isInteger(bucketCount) || bucketCount < 1) {
      throw new RangeError("bucketCount must be a positive integer");
    }

    this.bucketCount = bucketCount;
  }

  route(key) {
    const digest = crypto
      .createHash("sha256")
      .update(String(key))
      .digest();

    /*
     * Using four bytes avoids JavaScript's signed 32-bit bitwise behavior
     * for the final modulo calculation.
     */
    const numericHash = digest.readUInt32BE(0);
    return numericHash % this.bucketCount;
  }
}

class VerticalCustomerStore {
  constructor() {
    this.operational = new Map();
    this.sensitive = new Map();
  }

  insert(customer) {
    if (!Number.isInteger(customer.customerId)) {
      throw new TypeError("customerId must be an integer");
    }

    if (this.operational.has(customer.customerId)) {
      throw new PartitionConstraintError(
        `Duplicate customer ${customer.customerId}`
      );
    }

    /*
     * Operational attributes are intentionally kept separate from
     * infrequently accessed sensitive attributes.
     */
    this.operational.set(
      customer.customerId,
      Object.freeze({
        customerId: customer.customerId,
        name: customer.name,
        email: customer.email,
        phone: customer.phone,
      })
    );

    this.sensitive.set(
      customer.customerId,
      Object.freeze({
        customerId: customer.customerId,
        address: customer.address,
        dateOfBirth: customer.dateOfBirth,
      })
    );
  }

  getOperational(customerId) {
    const row = this.operational.get(customerId);

    if (!row) {
      throw new PartitionNotFoundError(`Customer ${customerId} not found`);
    }

    return row;
  }

  getFull(customerId) {
    const operational = this.getOperational(customerId);
    const sensitive = this.sensitive.get(customerId);

    if (!sensitive) {
      throw new PartitionConstraintError(
        `Vertical partition integrity failure for customer ${customerId}`
      );
    }

    return {
      ...operational,
      ...sensitive,
    };
  }
}

class CompositePartitionStore {
  constructor(hashBuckets) {
    this.hashRouter = new HashPartitionRouter(hashBuckets);
    this.partitions = new Map();
  }

  keyFor(order) {
    const bucket = this.hashRouter.route(order.customerId);
    const month = order.orderDate.toISOString().slice(0, 7);
    return `${month}:bucket:${bucket}`;
  }

  insert(order) {
    const key = this.keyFor(order);

    if (!this.partitions.has(key)) {
      this.partitions.set(key, []);
    }

    this.partitions.get(key).push(order);
    return key;
  }

  findCustomerOrders(yearMonth, customerId) {
    const bucket = this.hashRouter.route(customerId);
    const key = `${yearMonth}:bucket:${bucket}`;

    return (this.partitions.get(key) || []).filter(
      (order) => order.customerId === customerId
    );
  }
}

async function asynchronousPartitionQuery(store, start, end) {
  /*
   * A Promise models an asynchronous database call. A real driver would
   * perform network I/O here; the important partitioning behavior remains
   * the same: only eligible partitions are considered.
   */
  await new Promise((resolve) => setImmediate(resolve));
  return store.queryDateRange(start, end);
}

async function run() {
  console.log("=== Horizontal RANGE Partitioning ===");

  const store = new HorizontalPartitionStore([
    new RangePartition("orders_2026_q1", "2026-01-01", "2026-04-01"),
    new RangePartition("orders_2026_q2", "2026-04-01", "2026-07-01"),
    new RangePartition("orders_2026_q3", "2026-07-01", "2026-10-01"),
    new RangePartition("orders_2026_q4", "2026-10-01", "2027-01-01"),
  ]);

  store.on("rowInserted", (event) => {
    console.log(
      `Audit event: order ${event.orderId} inserted into ${event.partition}`
    );
  });

  const orders = [
    createOrder({
      orderId: 1001,
      customerId: 501,
      orderDate: "2026-02-15",
      region: "NORTH",
      status: "PAID",
      amount: 1250.5,
    }),
    createOrder({
      orderId: 1002,
      customerId: 502,
      orderDate: "2026-05-20",
      region: "SOUTH",
      status: "SHIPPED",
      amount: 760,
    }),
    createOrder({
      orderId: 1003,
      customerId: 503,
      orderDate: "2026-08-12",
      region: "WEST",
      status: "PAID",
      amount: 2100,
    }),
    createOrder({
      orderId: 1004,
      customerId: 504,
      orderDate: "2026-11-03",
      region: "EAST",
      status: "PENDING",
      amount: 450,
    }),
  ];

  for (const order of orders) {
    store.insert(order);
  }

  const result = await asynchronousPartitionQuery(
    store,
    "2026-04-01",
    "2026-10-01"
  );

  console.log(
    "Pruned query scanned:",
    result.partitionsScanned
  );
  console.log(
    "Returned orders:",
    result.rows.map((order) => order.orderId)
  );

  console.log("\n=== LIST Partitioning ===");

  const regionRouter = new ListPartitionRouter(
    {
      NORTH: "orders_north",
      SOUTH: "orders_south",
      EAST: "orders_east",
      WEST: "orders_west",
    },
    "orders_other"
  );

  for (const region of ["NORTH", "WEST", "CENTRAL"]) {
    console.log(`${region} -> ${regionRouter.route(region)}`);
  }

  console.log("\n=== HASH Partitioning ===");

  const hashRouter = new HashPartitionRouter(4);

  for (const customerId of [501, 502, 503, 504, 505, 506]) {
    console.log(
      `Customer ${customerId} -> bucket ${hashRouter.route(customerId)}`
    );
  }

  console.log("\n=== Vertical Partitioning ===");

  const customers = new VerticalCustomerStore();

  customers.insert({
    customerId: 501,
    name: "Asha Sharma",
    email: "asha@example.com",
    phone: "+91-9000000001",
    address: "Lucknow",
    dateOfBirth: "1992-03-14",
  });

  customers.insert({
    customerId: 502,
    name: "Rohan Mehta",
    email: "rohan@example.com",
    phone: "+91-9000000002",
    address: "Bengaluru",
    dateOfBirth: "1988-08-22",
  });

  console.log("Narrow operational read:", customers.getOperational(501));
  console.log("Full logical row:", customers.getFull(501));

  console.log("\n=== Composite RANGE + HASH ===");

  const composite = new CompositePartitionStore(4);

  for (const order of orders) {
    console.log(
      `Order ${order.orderId} -> ${composite.insert(order)}`
    );
  }

  console.log(
    "Customer 503 orders:",
    composite
      .findCustomerOrders("2026-08", 503)
      .map((order) => order.orderId)
  );

  console.log("\n=== Boundary Failure ===");

  try {
    store.insert(
      createOrder({
        orderId: 9001,
        customerId: 900,
        orderDate: "2027-01-01",
        region: "NORTH",
        status: "PENDING",
        amount: 50,
      })
    );
  } catch (error) {
    console.log(
      `Expected routing failure: ${error.message}`
    );
  }

  console.log("\n=== Design Considerations ===");
  console.log(
    "Range partitioning provides strong locality for time-bounded queries."
  );
  console.log(
    "List partitioning follows explicit business categories."
  );
  console.log(
    "Hash partitioning distributes rows without requiring meaningful ranges."
  );
  console.log(
    "Vertical partitioning narrows the row shape and can isolate sensitive attributes."
  );
  console.log(
    "Composite partitioning combines dimensions when one partition key is insufficient."
  );
}

run().catch((error) => {
  console.error("Partitioning demonstration failed:", error);
  process.exitCode = 1;
});
