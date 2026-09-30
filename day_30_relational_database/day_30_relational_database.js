/**
 * Relational Databases: SQL, Relationships, and Constraints
 *
 * This Node.js program models relational database behavior through an
 * event-driven repository service. It uses JavaScript objects to represent
 * rows, explicit relationship maps to represent foreign keys, and a policy
 * layer that validates relational constraints before mutations.
 *
 * It complements the SQL-focused Python implementation by emphasizing:
 * - JavaScript event-driven database-service behavior
 * - asynchronous operations
 * - repository boundaries
 * - transaction-like staging and rollback
 * - relationship traversal
 * - application-side validation before persistence
 * - parameter-style query construction
 *
 * Run with:
 *     node relational-database.js
 */

"use strict";

const { EventEmitter } = require("node:events");

class ConstraintError extends Error {
    constructor(message) {
        super(message);
        this.name = "ConstraintError";
    }
}

class TransactionError extends Error {
    constructor(message) {
        super(message);
        this.name = "TransactionError";
    }
}

function clone(value) {
    return structuredClone(value);
}

function normalizeEmail(email) {
    return email.trim().toLowerCase();
}

function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

class RelationalStore extends EventEmitter {
    constructor() {
        super();

        this.tables = {
            customers: new Map(),
            profiles: new Map(),
            products: new Map(),
            orders: new Map(),
            orderItems: new Map()
        };

        this.sequences = {
            customerId: 1,
            orderId: 1001
        };

        this.inTransaction = false;
        this.transactionBackup = null;
    }

    async execute(operation) {
        // A Promise boundary models the asynchronous behavior normally found
        // between Node.js application code and a real database driver.
        await new Promise(resolve => setImmediate(resolve));
        return operation();
    }

    assertForeignKey(condition, message) {
        if (!condition) {
            throw new ConstraintError(message);
        }
    }

    assertUnique(table, field, value, ignoredId = null) {
        for (const row of table.values()) {
            if (row[field] === value && row.id !== ignoredId) {
                throw new ConstraintError(
                    `UNIQUE constraint failed: ${field}=${value}`
                );
            }
        }
    }

    createCustomer({ name, email }) {
        if (!name || name.trim().length < 2) {
            throw new ConstraintError("Customer name must contain at least two characters");
        }

        const normalizedEmail = normalizeEmail(email);

        if (!validateEmail(normalizedEmail)) {
            throw new ConstraintError("Customer email is invalid");
        }

        this.assertUnique(
            this.tables.customers,
            "email",
            normalizedEmail
        );

        const id = this.sequences.customerId++;

        const customer = {
            id,
            name: name.trim(),
            email: normalizedEmail,
            createdAt: new Date().toISOString()
        };

        this.tables.customers.set(id, customer);
        this.emit("customer.created", clone(customer));

        return clone(customer);
    }

    createProfile(customerId, { phone, city, country = "India" }) {
        this.assertForeignKey(
            this.tables.customers.has(customerId),
            `Customer ${customerId} does not exist`
        );

        if (!city || !city.trim()) {
            throw new ConstraintError("City is required");
        }

        if (this.tables.profiles.has(customerId)) {
            throw new ConstraintError(
                "One-to-one relationship violated: customer already has a profile"
            );
        }

        const profile = {
            customerId,
            phone: phone?.trim() ?? null,
            city: city.trim(),
            country: country.trim()
        };

        this.tables.profiles.set(customerId, profile);
        this.emit("profile.created", clone(profile));

        return clone(profile);
    }

    createProduct({ sku, name, category, unitPrice, inventoryQuantity }) {
        if (!sku || !name || !category) {
            throw new ConstraintError(
                "SKU, name, and category are required"
            );
        }

        if (!Number.isFinite(unitPrice) || unitPrice < 0) {
            throw new ConstraintError("Unit price must be a non-negative number");
        }

        if (
            !Number.isInteger(inventoryQuantity) ||
            inventoryQuantity < 0
        ) {
            throw new ConstraintError(
                "Inventory quantity must be a non-negative integer"
            );
        }

        this.assertUnique(this.tables.products, "sku", sku);

        const product = {
            id: this.tables.products.size + 1,
            sku,
            name,
            category,
            unitPrice,
            inventoryQuantity
        };

        this.tables.products.set(product.id, product);
        this.emit("product.created", clone(product));

        return clone(product);
    }

    createOrder(customerId, status = "PENDING") {
        this.assertForeignKey(
            this.tables.customers.has(customerId),
            `Customer ${customerId} does not exist`
        );

        const validStatuses = new Set([
            "PENDING",
            "PAID",
            "SHIPPED",
            "CANCELLED"
        ]);

        if (!validStatuses.has(status)) {
            throw new ConstraintError(`Unsupported order status: ${status}`);
        }

        const id = this.sequences.orderId++;

        const order = {
            id,
            customerId,
            status,
            createdAt: new Date().toISOString()
        };

        this.tables.orders.set(id, order);
        this.emit("order.created", clone(order));

        return clone(order);
    }

    addOrderItem(orderId, productId, quantity) {
        this.assertForeignKey(
            this.tables.orders.has(orderId),
            `Order ${orderId} does not exist`
        );

        this.assertForeignKey(
            this.tables.products.has(productId),
            `Product ${productId} does not exist`
        );

        if (!Number.isInteger(quantity) || quantity <= 0) {
            throw new ConstraintError(
                "Order item quantity must be a positive integer"
            );
        }

        const key = `${orderId}:${productId}`;

        if (this.tables.orderItems.has(key)) {
            throw new ConstraintError(
                "Composite primary key violated: product already exists in this order"
            );
        }

        const product = this.tables.products.get(productId);

        if (quantity > product.inventoryQuantity) {
            throw new ConstraintError(
                `Insufficient inventory for product ${productId}`
            );
        }

        const item = {
            key,
            orderId,
            productId,
            quantity,
            unitPrice: product.unitPrice
        };

        this.tables.orderItems.set(key, item);

        // Inventory belongs to the product row, while quantity belongs to
        // the order/product relationship. Keeping these responsibilities
        // separate mirrors normalized relational design.
        product.inventoryQuantity -= quantity;

        this.emit("order-item.created", clone(item));

        return clone(item);
    }

    async transaction(callback) {
        if (this.inTransaction) {
            throw new TransactionError("Nested transactions are not supported");
        }

        this.inTransaction = true;
        this.transactionBackup = clone({
            tables: Object.fromEntries(
                Object.entries(this.tables).map(([name, table]) => [
                    name,
                    [...table.entries()]
                ])
            ),
            sequences: this.sequences
        });

        try {
            const result = await callback();
            this.inTransaction = false;
            this.transactionBackup = null;
            this.emit("transaction.committed");
            return result;
        } catch (error) {
            const backup = this.transactionBackup;

            for (const [name, entries] of Object.entries(backup.tables)) {
                this.tables[name] = new Map(entries);
            }

            this.sequences = backup.sequences;
            this.inTransaction = false;
            this.transactionBackup = null;

            this.emit("transaction.rolledBack", {
                reason: error.message
            });

            throw error;
        }
    }

    async createCompleteOrder(customerId, requestedItems) {
        return this.transaction(async () => {
            const order = this.createOrder(customerId, "PENDING");

            for (const requestedItem of requestedItems) {
                this.addOrderItem(
                    order.id,
                    requestedItem.productId,
                    requestedItem.quantity
                );
            }

            if (this.getOrderItems(order.id).length === 0) {
                throw new ConstraintError(
                    "An order must contain at least one item"
                );
            }

            return order;
        });
    }

    getOrderItems(orderId) {
        return [...this.tables.orderItems.values()]
            .filter(item => item.orderId === orderId)
            .map(clone);
    }

    getOrderDetails(orderId) {
        const order = this.tables.orders.get(orderId);

        if (!order) {
            return null;
        }

        const customer = this.tables.customers.get(order.customerId);

        const items = this.getOrderItems(orderId).map(item => {
            const product = this.tables.products.get(item.productId);

            return {
                productId: item.productId,
                productName: product.name,
                sku: product.sku,
                quantity: item.quantity,
                unitPrice: item.unitPrice,
                lineTotal: item.quantity * item.unitPrice
            };
        });

        const total = items.reduce(
            (sum, item) => sum + item.lineTotal,
            0
        );

        return {
            order: clone(order),
            customer: clone(customer),
            items,
            total
        };
    }

    customerReport() {
        return [...this.tables.customers.values()].map(customer => {
            const customerOrders = [...this.tables.orders.values()]
                .filter(
                    order =>
                        order.customerId === customer.id &&
                        order.status !== "CANCELLED"
                );

            const lifetimeValue = customerOrders.reduce((sum, order) => {
                const details = this.getOrderDetails(order.id);
                return sum + (details?.total ?? 0);
            }, 0);

            return {
                customerId: customer.id,
                name: customer.name,
                orderCount: customerOrders.length,
                lifetimeValue
            };
        });
    }

    deleteCustomer(customerId) {
        const customer = this.tables.customers.get(customerId);

        if (!customer) {
            throw new ConstraintError("Customer does not exist");
        }

        const hasOrders = [...this.tables.orders.values()].some(
            order => order.customerId === customerId
        );

        // This models ON DELETE RESTRICT for customers -> orders.
        if (hasOrders) {
            throw new ConstraintError(
                "Customer cannot be deleted while orders reference the customer"
            );
        }

        this.tables.profiles.delete(customerId);
        this.tables.customers.delete(customerId);

        this.emit("customer.deleted", { customerId });
    }
}

function registerEventLogging(store) {
    const events = [
        "customer.created",
        "profile.created",
        "product.created",
        "order.created",
        "order-item.created",
        "transaction.committed",
        "transaction.rolledBack",
        "customer.deleted"
    ];

    for (const eventName of events) {
        store.on(eventName, payload => {
            console.log(`[event] ${eventName}`, payload ?? "");
        });
    }
}

async function buildStore() {
    const store = new RelationalStore();

    registerEventLogging(store);

    const atul = store.createCustomer({
        name: "Atul Pandey",
        email: "ATUL@EXAMPLE.COM"
    });

    const priya = store.createCustomer({
        name: "Priya Sharma",
        email: "priya@example.com"
    });

    store.createProfile(atul.id, {
        phone: "+91-9000000001",
        city: "Lucknow"
    });

    store.createProfile(priya.id, {
        phone: "+91-9000000002",
        city: "Delhi"
    });

    const laptop = store.createProduct({
        sku: "LAP-001",
        name: "Developer Laptop",
        category: "Computers",
        unitPrice: 85000,
        inventoryQuantity: 5
    });

    const monitor = store.createProduct({
        sku: "MON-001",
        name: "27-inch Monitor",
        category: "Displays",
        unitPrice: 24000,
        inventoryQuantity: 8
    });

    const dock = store.createProduct({
        sku: "DOC-001",
        name: "USB-C Dock",
        category: "Accessories",
        unitPrice: 9000,
        inventoryQuantity: 4
    });

    console.log("\n=== Creating a complete relational order ===");

    const order = await store.createCompleteOrder(atul.id, [
        { productId: laptop.id, quantity: 1 },
        { productId: monitor.id, quantity: 2 },
        { productId: dock.id, quantity: 1 }
    ]);

    console.log("\nOrder details:");
    console.dir(store.getOrderDetails(order.id), { depth: null });

    console.log("\nCustomer report:");
    console.table(store.customerReport());

    console.log("\n=== Demonstrating rollback ===");

    const inventoryBefore = store.tables.products.get(laptop.id)
        .inventoryQuantity;

    try {
        await store.createCompleteOrder(priya.id, [
            { productId: laptop.id, quantity: 1 },
            { productId: 9999, quantity: 1 }
        ]);
    } catch (error) {
        console.log(
            `Expected transaction failure: ${error.name}: ${error.message}`
        );
    }

    const inventoryAfter = store.tables.products.get(laptop.id)
        .inventoryQuantity;

    console.log({
        inventoryBefore,
        inventoryAfter,
        rollbackPreservedInventory: inventoryBefore === inventoryAfter
    });

    console.log("\n=== Constraint failure examples ===");

    try {
        store.createCustomer({
            name: "Duplicate",
            email: "atul@example.com"
        });
    } catch (error) {
        console.log(`${error.name}: ${error.message}`);
    }

    try {
        store.createProduct({
            sku: "MON-001",
            name: "Duplicate Monitor",
            category: "Displays",
            unitPrice: 100,
            inventoryQuantity: 1
        });
    } catch (error) {
        console.log(`${error.name}: ${error.message}`);
    }

    try {
        store.createProfile(atul.id, {
            city: "Mumbai"
        });
    } catch (error) {
        console.log(`${error.name}: ${error.message}`);
    }

    console.log("\n=== Referential relationship inspection ===");

    for (const customer of store.tables.customers.values()) {
        const orders = [...store.tables.orders.values()]
            .filter(orderRow => orderRow.customerId === customer.id);

        console.log({
            customer: customer.name,
            profileExists: store.tables.profiles.has(customer.id),
            orderIds: orders.map(orderRow => orderRow.id)
        });
    }

    console.log("\n=== Delete restriction ===");

    try {
        store.deleteCustomer(atul.id);
    } catch (error) {
        console.log(`${error.name}: ${error.message}`);
    }

    console.log("\n=== Completed JavaScript relational model ===");
}

buildStore().catch(error => {
    console.error("Fatal database-model error:", error);
    process.exitCode = 1;
});
