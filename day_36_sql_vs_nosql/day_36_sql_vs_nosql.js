/**
 * SQL vs NoSQL: an event-driven database architecture laboratory.
 *
 * The program uses JavaScript-specific mechanisms to model:
 * - normalized relational records
 * - document aggregates
 * - key-value access
 * - event-driven writes
 * - asynchronous replication
 * - optimistic concurrency
 * - workload-aware database selection
 *
 * Run with:
 *   node sql-vs-nosql.js
 */

"use strict";

const EventEmitter = require("node:events");
const crypto = require("node:crypto");

class RelationalDatabase {
    constructor() {
        this.customers = new Map();
        this.products = new Map();
        this.orders = new Map();
        this.orderItems = [];
    }

    addCustomer(customer) {
        if (!customer.id || !customer.email) {
            throw new Error("Customer id and email are required");
        }

        if (this.customers.has(customer.id)) {
            throw new Error("Duplicate customer primary key");
        }

        for (const existing of this.customers.values()) {
            if (existing.email === customer.email) {
                throw new Error("Customer email violates uniqueness");
            }
        }

        this.customers.set(customer.id, structuredClone(customer));
    }

    addProduct(product) {
        if (product.price < 0) {
            throw new Error("Product price cannot be negative");
        }

        if (this.products.has(product.id)) {
            throw new Error("Duplicate product primary key");
        }

        this.products.set(product.id, structuredClone(product));
    }

    addOrder(order) {
        if (!this.customers.has(order.customerId)) {
            throw new Error("Foreign-key violation: customer does not exist");
        }

        if (this.orders.has(order.id)) {
            throw new Error("Duplicate order primary key");
        }

        this.orders.set(order.id, {
            ...order,
            total: 0
        });
    }

    addOrderItem(item) {
        if (!this.orders.has(item.orderId)) {
            throw new Error("Foreign-key violation: order does not exist");
        }

        if (!this.products.has(item.productId)) {
            throw new Error("Foreign-key violation: product does not exist");
        }

        if (!Number.isInteger(item.quantity) || item.quantity <= 0) {
            throw new Error("Quantity must be a positive integer");
        }

        this.orderItems.push({ ...item });
        this.recalculateTotal(item.orderId);
    }

    recalculateTotal(orderId) {
        const order = this.orders.get(orderId);

        order.total = this.orderItems
            .filter(item => item.orderId === orderId)
            .reduce(
                (sum, item) => sum + item.quantity * item.unitPrice,
                0
            );
    }

    joinOrder(orderId) {
        const order = this.orders.get(orderId);

        if (!order) {
            return null;
        }

        const customer = this.customers.get(order.customerId);

        const items = this.orderItems
            .filter(item => item.orderId === orderId)
            .map(item => {
                const product = this.products.get(item.productId);

                return {
                    product: product.name,
                    category: product.category,
                    quantity: item.quantity,
                    unitPrice: item.unitPrice,
                    lineTotal: item.quantity * item.unitPrice
                };
            });

        return {
            orderId: order.id,
            status: order.status,
            customer: customer.name,
            items,
            total: order.total
        };
    }
}

class DocumentDatabase {
    constructor() {
        this.documents = new Map();
    }

    insert(document) {
        if (!document._id) {
            throw new Error("Document requires _id");
        }

        if (!Array.isArray(document.items)) {
            throw new Error("Order document requires an items array");
        }

        if (this.documents.has(document._id)) {
            throw new Error("Duplicate document identifier");
        }

        this.documents.set(
            document._id,
            structuredClone(document)
        );
    }

    findById(id) {
        const document = this.documents.get(id);
        return document ? structuredClone(document) : null;
    }

    updateStatus(id, status) {
        const document = this.documents.get(id);

        if (!document) {
            throw new Error("Document not found");
        }

        document.status = status;
    }
}

class KeyValueDatabase {
    constructor() {
        this.values = new Map();
    }

    set(key, value) {
        if (typeof key !== "string" || key.length === 0) {
            throw new Error("A non-empty string key is required");
        }

        this.values.set(key, structuredClone(value));
    }

    get(key) {
        const value = this.values.get(key);
        return value === undefined ? undefined : structuredClone(value);
    }
}

class EventDrivenDocumentService extends EventEmitter {
    constructor(database) {
        super();
        this.database = database;

        this.on("order.created", order => {
            console.log(
                `Event received: order.created for ${order._id}`
            );
        });

        this.on("order.paid", order => {
            console.log(
                `Event received: order.paid for ${order._id}`
            );
        });
    }

    createOrder(order) {
        this.database.insert(order);
        this.emit("order.created", order);
    }

    payOrder(id) {
        const order = this.database.findById(id);

        if (!order) {
            throw new Error("Order not found");
        }

        if (order.status !== "PENDING") {
            throw new Error(
                `Cannot pay order in ${order.status} state`
            );
        }

        this.database.updateStatus(id, "PAID");

        const updated = this.database.findById(id);
        this.emit("order.paid", updated);
    }
}

class EventuallyConsistentCluster {
    constructor(replicaCount = 2) {
        this.primary = new Map();
        this.replicas = Array.from(
            { length: replicaCount },
            (_, index) => ({
                name: `replica-${index + 1}`,
                data: new Map(),
                version: 0
            })
        );
        this.version = 0;
    }

    write(key, value) {
        this.version += 1;

        this.primary.set(key, {
            value: structuredClone(value),
            version: this.version
        });

        return this.version;
    }

    readReplica(name, key) {
        const replica = this.replicas.find(
            node => node.name === name
        );

        if (!replica) {
            throw new Error(`Unknown replica: ${name}`);
        }

        const record = replica.data.get(key);

        return record ? structuredClone(record.value) : undefined;
    }

    async synchronize(delayMs = 25) {
        await new Promise(resolve =>
            setTimeout(resolve, delayMs)
        );

        for (const replica of this.replicas) {
            replica.data = new Map(
                [...this.primary.entries()].map(
                    ([key, record]) => [
                        key,
                        structuredClone(record)
                    ]
                )
            );

            replica.version = this.version;
        }
    }
}

class VersionedDocumentRepository {
    constructor() {
        this.records = new Map();
    }

    create(id, value) {
        if (this.records.has(id)) {
            throw new Error("Record already exists");
        }

        this.records.set(id, {
            value: structuredClone(value),
            version: 1
        });
    }

    read(id) {
        const record = this.records.get(id);

        if (!record) {
            throw new Error("Record not found");
        }

        return structuredClone(record);
    }

    update(id, value, expectedVersion) {
        const record = this.records.get(id);

        if (!record) {
            throw new Error("Record not found");
        }

        if (record.version !== expectedVersion) {
            throw new Error(
                "Optimistic concurrency conflict"
            );
        }

        record.value = structuredClone(value);
        record.version += 1;
    }
}

class DatabasePolicyEngine {
    static select({
        relationships,
        transactions,
        flexibleSchema,
        horizontalScale,
        primaryAccessPattern
    }) {
        if (primaryAccessPattern === "key-value") {
            return "Key-Value NoSQL";
        }

        if (transactions && relationships) {
            return "SQL";
        }

        if (
            flexibleSchema &&
            horizontalScale &&
            !transactions
        ) {
            return "Document NoSQL";
        }

        if (relationships) {
            return "SQL";
        }

        if (horizontalScale) {
            return "Workload-specific NoSQL model";
        }

        return "Benchmark SQL and NoSQL against representative traffic";
    }
}

function createRelationalExample() {
    const database = new RelationalDatabase();

    database.addCustomer({
        id: 1,
        name: "Asha Rao",
        email: "asha@example.com"
    });

    database.addProduct({
        id: 10,
        name: "Laptop",
        category: "Computing",
        price: 1200
    });

    database.addProduct({
        id: 11,
        name: "Keyboard",
        category: "Accessories",
        price: 80
    });

    database.addOrder({
        id: 1001,
        customerId: 1,
        status: "PAID"
    });

    database.addOrderItem({
        orderId: 1001,
        productId: 10,
        quantity: 1,
        unitPrice: 1200
    });

    database.addOrderItem({
        orderId: 1001,
        productId: 11,
        quantity: 2,
        unitPrice: 80
    });

    console.log(
        "\nRelational join result:",
        JSON.stringify(
            database.joinOrder(1001),
            null,
            2
        )
    );
}

function createDocumentExample() {
    const database = new DocumentDatabase();

    database.insert({
        _id: "order-1001",
        status: "PENDING",
        customer: {
            id: 1,
            name: "Asha Rao"
        },
        items: [
            {
                productId: 10,
                name: "Laptop",
                quantity: 1,
                unitPrice: 1200
            }
        ],
        shipping: {
            country: "IN",
            postalCode: "226001"
        }
    });

    console.log(
        "\nDocument aggregate:",
        JSON.stringify(
            database.findById("order-1001"),
            null,
            2
        )
    );
}

async function demonstrateEventsAndReplication() {
    const database = new DocumentDatabase();
    const service = new EventDrivenDocumentService(database);

    service.createOrder({
        _id: "order-2001",
        status: "PENDING",
        customer: { id: 2, name: "Rohan Mehta" },
        items: []
    });

    service.payOrder("order-2001");

    const cluster = new EventuallyConsistentCluster();

    cluster.write("inventory:laptop", 9);

    console.log(
        "\nReplica before synchronization:",
        cluster.readReplica(
            "replica-1",
            "inventory:laptop"
        )
    );

    await cluster.synchronize();

    console.log(
        "Replica after synchronization:",
        cluster.readReplica(
            "replica-1",
            "inventory:laptop"
        )
    );
}

function demonstrateOptimisticConcurrency() {
    const repository = new VersionedDocumentRepository();

    repository.create(
        "customer-1",
        {
            name: "Asha",
            tier: "gold"
        }
    );

    const clientA = repository.read("customer-1");
    const clientB = repository.read("customer-1");

    repository.update(
        "customer-1",
        {
            name: "Asha",
            tier: "platinum"
        },
        clientA.version
    );

    try {
        repository.update(
            "customer-1",
            {
                name: "Asha",
                tier: "silver"
            },
            clientB.version
        );
    } catch (error) {
        console.log(
            "\nStale write rejected:",
            error.message
        );
    }
}

function demonstrateKeyValueAccess() {
    const database = new KeyValueDatabase();

    const sessionId = crypto.randomUUID();

    database.set(
        `session:${sessionId}`,
        {
            userId: 1,
            expiresAt:
                Date.now() + 30 * 60 * 1000
        }
    );

    console.log(
        "\nKey-value session:",
        database.get(`session:${sessionId}`)
    );
}

function demonstratePolicySelection() {
    console.log("\nWorkload selection:");

    const workloads = [
        {
            name: "Bank transfer ledger",
            relationships: true,
            transactions: true,
            flexibleSchema: false,
            horizontalScale: false,
            primaryAccessPattern: "relational"
        },
        {
            name: "Flexible product catalog",
            relationships: false,
            transactions: false,
            flexibleSchema: true,
            horizontalScale: true,
            primaryAccessPattern: "document"
        },
        {
            name: "Web session storage",
            relationships: false,
            transactions: false,
            flexibleSchema: false,
            horizontalScale: true,
            primaryAccessPattern: "key-value"
        }
    ];

    for (const workload of workloads) {
        console.log(
            `${workload.name}: ${DatabasePolicyEngine.select(workload)}`
        );
    }
}

async function main() {
    console.log("=== SQL VS NOSQL LABORATORY ===");

    createRelationalExample();
    createDocumentExample();
    await demonstrateEventsAndReplication();
    demonstrateOptimisticConcurrency();
    demonstrateKeyValueAccess();
    demonstratePolicySelection();

    console.log(
        "\nDatabase selection should follow workload characteristics, " +
        "not a universal SQL-or-NoSQL preference."
    );
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
