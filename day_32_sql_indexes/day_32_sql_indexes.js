"use strict";

/*
 * SQL Indexes: B-Tree Indexes and Query Performance
 *
 * This Node.js program models database-oriented index behavior without an
 * external database. It focuses on:
 *   - B-Tree equality and range access
 *   - query-plan selection
 *   - composite index ordering
 *   - covering/index-only access
 *   - asynchronous query events
 *   - index maintenance
 *   - selectivity and logical I/O
 *
 * The implementation uses JavaScript-specific features such as classes,
 * Map/Set, generators, async/await, structured errors, and event-driven
 * execution rather than translating the Python example line by line.
 */

const { EventEmitter } = require("node:events");


class IndexValidationError extends Error {
    constructor(message) {
        super(message);
        this.name = "IndexValidationError";
    }
}


class Order {
    constructor({ orderId, customerId, status, orderDate, totalAmount }) {
        if (!Number.isInteger(orderId) || orderId <= 0) {
            throw new IndexValidationError("orderId must be a positive integer");
        }
        if (!Number.isInteger(customerId) || customerId <= 0) {
            throw new IndexValidationError("customerId must be a positive integer");
        }
        if (!["PAID", "PENDING", "SHIPPED", "CANCELLED"].includes(status)) {
            throw new IndexValidationError(`Unsupported order status: ${status}`);
        }
        if (!Number.isInteger(orderDate) || orderDate < 19000101) {
            throw new IndexValidationError("orderDate must be YYYYMMDD as an integer");
        }
        if (!Number.isFinite(totalAmount) || totalAmount < 0) {
            throw new IndexValidationError("totalAmount must be a non-negative number");
        }

        this.orderId = orderId;
        this.customerId = customerId;
        this.status = status;
        this.orderDate = orderDate;
        this.totalAmount = Number(totalAmount.toFixed(2));
    }
}


class BTreeNode {
    constructor(leaf = true) {
        this.leaf = leaf;
        this.keys = [];
        this.values = [];
        this.children = [];
    }
}


function lowerBound(values, target) {
    let low = 0;
    let high = values.length;

    while (low < high) {
        const middle = Math.floor((low + high) / 2);

        if (values[middle] < target) {
            low = middle + 1;
        } else {
            high = middle;
        }
    }

    return low;
}


function upperBound(values, target) {
    let low = 0;
    let high = values.length;

    while (low < high) {
        const middle = Math.floor((low + high) / 2);

        if (values[middle] <= target) {
            low = middle + 1;
        } else {
            high = middle;
        }
    }

    return low;
}


class BTreeIndex {
    /*
     * This B-Tree is intentionally small and observable. Real database
     * implementations store nodes in fixed-size pages and include additional
     * metadata, concurrency controls, logging, and recovery machinery.
     */
    constructor(name, keySelector, maxKeys = 6) {
        if (maxKeys < 3) {
            throw new IndexValidationError("maxKeys must be at least 3");
        }

        this.name = name;
        this.keySelector = keySelector;
        this.maxKeys = maxKeys;
        this.root = new BTreeNode(true);
        this.orderToKey = new Map();
    }

    insert(order) {
        const key = this.keySelector(order);

        if (this.orderToKey.has(order.orderId)) {
            this.delete(order.orderId);
        }

        this.orderToKey.set(order.orderId, key);

        if (this.root.keys.length >= this.maxKeys) {
            const oldRoot = this.root;
            this.root = new BTreeNode(false);
            this.root.children.push(oldRoot);
            this.splitChild(this.root, 0);
        }

        this.insertNonFull(this.root, key, order.orderId);
    }

    splitChild(parent, childIndex) {
        const child = parent.children[childIndex];
        const middle = Math.floor(child.keys.length / 2);

        const promotedKey = child.keys[middle];
        const promotedValues = child.values[middle];

        const right = new BTreeNode(child.leaf);

        right.keys = child.keys.slice(middle + 1);
        right.values = child.values.slice(middle + 1);

        if (!child.leaf) {
            right.children = child.children.slice(middle + 1);
            child.children = child.children.slice(0, middle + 1);
        }

        child.keys = child.keys.slice(0, middle);
        child.values = child.values.slice(0, middle);

        parent.keys.splice(childIndex, 0, promotedKey);
        parent.values.splice(childIndex, 0, promotedValues);
        parent.children.splice(childIndex + 1, 0, right);
    }

    insertNonFull(node, key, orderId) {
        if (node.leaf) {
            const position = lowerBound(node.keys, key);

            if (position < node.keys.length && node.keys[position] === key) {
                node.values[position].push(orderId);
                return;
            }

            node.keys.splice(position, 0, key);
            node.values.splice(position, 0, [orderId]);
            return;
        }

        let position = upperBound(node.keys, key);
        const child = node.children[position];

        if (child.keys.length >= this.maxKeys) {
            this.splitChild(node, position);

            if (key > node.keys[position]) {
                position += 1;
            } else if (key === node.keys[position]) {
                node.values[position].push(orderId);
                return;
            }
        }

        this.insertNonFull(node.children[position], key, orderId);
    }

    delete(orderId) {
        if (!this.orderToKey.has(orderId)) {
            return false;
        }

        /*
         * Structural B-Tree deletion is intentionally omitted from this model.
         * Rebuilding makes the maintenance consequence visible while avoiding
         * implementation details that would obscure the SQL indexing lesson.
         */
        const remaining = [...this.orderToKey.entries()]
            .filter(([id]) => id !== orderId);

        this.orderToKey.delete(orderId);
        this.root = new BTreeNode(true);

        for (const [id, key] of remaining) {
            if (this.root.keys.length >= this.maxKeys) {
                const oldRoot = this.root;
                this.root = new BTreeNode(false);
                this.root.children.push(oldRoot);
                this.splitChild(this.root, 0);
            }
            this.insertNonFull(this.root, key, id);
        }

        return true;
    }

    equalityLookup(key) {
        let node = this.root;
        let visits = 0;

        while (true) {
            visits += 1;
            const position = lowerBound(node.keys, key);

            if (position < node.keys.length && node.keys[position] === key) {
                return {
                    orderIds: [...node.values[position]],
                    nodeVisits: visits,
                };
            }

            if (node.leaf) {
                return {
                    orderIds: [],
                    nodeVisits: visits,
                };
            }

            node = node.children[position];
        }
    }

    rangeLookup(lower, upper) {
        if (lower > upper) {
            throw new IndexValidationError(
                "The lower range boundary cannot exceed the upper boundary"
            );
        }

        const result = [];
        let nodeVisits = 0;

        const walk = (node) => {
            nodeVisits += 1;

            if (node.leaf) {
                const start = lowerBound(node.keys, lower);
                const end = upperBound(node.keys, upper);

                for (let i = start; i < end; i += 1) {
                    result.push(...node.values[i]);
                }
                return;
            }

            const firstChild = lowerBound(node.keys, lower);
            const lastChild = upperBound(node.keys, upper);

            for (let i = firstChild; i <= lastChild; i += 1) {
                walk(node.children[i]);
            }

            const start = lowerBound(node.keys, lower);
            const end = upperBound(node.keys, upper);

            for (let i = start; i < end; i += 1) {
                result.push(...node.values[i]);
            }
        };

        walk(this.root);

        return {
            orderIds: result,
            nodeVisits,
        };
    }

    height() {
        let height = 1;
        let node = this.root;

        while (!node.leaf) {
            height += 1;
            node = node.children[0];
        }

        return height;
    }

    describe() {
        return {
            name: this.name,
            height: this.height(),
            entries: this.orderToKey.size,
            maxKeys: this.maxKeys,
        };
    }
}


class OrdersTable {
    constructor(rowsPerPage = 10) {
        if (!Number.isInteger(rowsPerPage) || rowsPerPage <= 0) {
            throw new IndexValidationError("rowsPerPage must be positive");
        }

        this.rowsPerPage = rowsPerPage;
        this.pages = [];
        this.rows = new Map();
        this.locations = new Map();
    }

    insert(order) {
        if (this.rows.has(order.orderId)) {
            throw new IndexValidationError(
                `Duplicate order ID: ${order.orderId}`
            );
        }

        if (
            this.pages.length === 0 ||
            this.pages[this.pages.length - 1].length >= this.rowsPerPage
        ) {
            this.pages.push([]);
        }

        const pageId = this.pages.length - 1;
        const slot = this.pages[pageId].length;

        this.pages[pageId].push(order);
        this.rows.set(order.orderId, order);
        this.locations.set(order.orderId, { pageId, slot });
    }

    update(orderId, changes) {
        const oldOrder = this.rows.get(orderId);

        if (!oldOrder) {
            throw new IndexValidationError(
                `Cannot update unknown order ID: ${orderId}`
            );
        }

        const updated = new Order({
            orderId: oldOrder.orderId,
            customerId: changes.customerId ?? oldOrder.customerId,
            status: changes.status ?? oldOrder.status,
            orderDate: changes.orderDate ?? oldOrder.orderDate,
            totalAmount: changes.totalAmount ?? oldOrder.totalAmount,
        });

        const { pageId, slot } = this.locations.get(orderId);
        this.pages[pageId][slot] = updated;
        this.rows.set(orderId, updated);

        return updated;
    }

    fullScan(predicate) {
        let pagesRead = 0;
        const result = [];

        for (const page of this.pages) {
            pagesRead += 1;

            for (const row of page) {
                if (predicate(row)) {
                    result.push(row);
                }
            }
        }

        return { rows: result, pagesRead };
    }

    fetchRows(orderIds) {
        const uniqueIds = [...new Set(orderIds)];
        const pages = new Set();
        const rows = [];

        for (const id of uniqueIds) {
            const location = this.locations.get(id);

            if (!location) {
                continue;
            }

            pages.add(location.pageId);
            rows.push(this.rows.get(id));
        }

        return {
            rows,
            pagesRead: pages.size,
        };
    }

    get rowCount() {
        return this.rows.size;
    }

    get pageCount() {
        return this.pages.length;
    }
}


class CompositeIndex {
    /*
     * The sorted key is [customerId, orderDate]. JavaScript does not compare
     * arrays lexicographically by value, so the index uses a dedicated
     * comparator and binary search.
     */
    constructor(name) {
        this.name = name;
        this.entries = [];
    }

    compareKeys(left, right) {
        if (left[0] !== right[0]) {
            return left[0] - right[0];
        }
        return left[1] - right[1];
    }

    build(rows) {
        this.entries = rows
            .map((row) => ({
                key: [row.customerId, row.orderDate],
                orderId: row.orderId,
            }))
            .sort((a, b) => this.compareKeys(a.key, b.key));
    }

    lowerBound(target) {
        let low = 0;
        let high = this.entries.length;

        while (low < high) {
            const middle = Math.floor((low + high) / 2);

            if (this.compareKeys(this.entries[middle].key, target) < 0) {
                low = middle + 1;
            } else {
                high = middle;
            }
        }

        return low;
    }

    customerDateRange(customerId, startDate, endDate) {
        const start = this.lowerBound([customerId, startDate]);
        const end = this.lowerBound([customerId, endDate + 1]);

        return this.entries
            .slice(start, end)
            .filter((entry) => entry.key[0] === customerId)
            .map((entry) => entry.orderId);
    }

    customerOnly(customerId) {
        const start = this.lowerBound([customerId, 0]);
        const result = [];

        for (let i = start; i < this.entries.length; i += 1) {
            if (this.entries[i].key[0] !== customerId) {
                break;
            }
            result.push(this.entries[i].orderId);
        }

        return result;
    }
}


class CoveringIndex {
    /*
     * This represents index payload that contains both the search key and
     * projected columns. It allows an index-only result for a narrow query.
     */
    constructor() {
        this.entries = new Map();
    }

    build(rows) {
        this.entries.clear();

        for (const row of rows) {
            if (!this.entries.has(row.customerId)) {
                this.entries.set(row.customerId, []);
            }

            this.entries.get(row.customerId).push({
                orderId: row.orderId,
                status: row.status,
                totalAmount: row.totalAmount,
            });
        }
    }

    query(customerId) {
        return this.entries.get(customerId) ?? [];
    }
}


class QueryEngine extends EventEmitter {
    /*
     * EventEmitter makes query execution observable. Production database
     * drivers expose different event and telemetry APIs, but the pattern is
     * useful for illustrating query-start, plan-selection, and query-finished
     * events.
     */
    constructor(table, indexes) {
        super();
        this.table = table;
        this.indexes = indexes;
    }

    async findOrdersByCustomer(customerId) {
        this.emit("queryStarted", {
            operation: "findOrdersByCustomer",
            customerId,
        });

        await Promise.resolve();

        const index = this.indexes.customer;
        const indexResult = index.equalityLookup(customerId);

        if (indexResult.orderIds.length === 0) {
            const result = {
                rows: [],
                accessPath: "Index Seek",
                pageReads: indexResult.nodeVisits,
            };

            this.emit("queryFinished", result);
            return result;
        }

        const indexedRows = this.table.fetchRows(indexResult.orderIds);
        const indexCost = indexResult.nodeVisits + indexedRows.pagesRead;
        const scanCost = this.table.pageCount;

        const result = indexCost < scanCost
            ? {
                rows: indexedRows.rows,
                accessPath: "Index Seek + Table Lookup",
                pageReads: indexCost,
            }
            : {
                rows: this.table.fullScan(
                    (row) => row.customerId === customerId
                ).rows,
                accessPath: "Full Table Scan",
                pageReads: scanCost,
            };

        this.emit("queryFinished", result);
        return result;
    }
}


function seededRandom(seed) {
    let state = seed >>> 0;

    return () => {
        state = (1664525 * state + 1013904223) >>> 0;
        return state / 0x100000000;
    };
}


function randomInteger(random, minimum, maximum) {
    return Math.floor(
        minimum + random() * (maximum - minimum + 1)
    );
}


function createOrders(count) {
    const random = seededRandom(20261002);
    const statuses = ["PAID", "PENDING", "SHIPPED", "CANCELLED"];
    const orders = [];

    for (let orderId = 1; orderId <= count; orderId += 1) {
        const customerId = randomInteger(
            random,
            1,
            Math.max(10, Math.floor(count / 12))
        );

        const year = randomInteger(random, 2024, 2026);
        const month = randomInteger(random, 1, 12);
        const day = randomInteger(random, 1, 28);

        const statusRoll = random();
        let status;

        if (statusRoll < 0.55) {
            status = "PAID";
        } else if (statusRoll < 0.75) {
            status = "PENDING";
        } else if (statusRoll < 0.95) {
            status = "SHIPPED";
        } else {
            status = "CANCELLED";
        }

        const totalAmount = 25 + random() * 2475;

        orders.push(
            new Order({
                orderId,
                customerId,
                status,
                orderDate: year * 10000 + month * 100 + day,
                totalAmount,
            })
        );
    }

    return orders;
}


function buildIndexes(orders) {
    const indexes = {
        customer: new BTreeIndex(
            "idx_orders_customer",
            (row) => row.customerId
        ),
        status: new BTreeIndex(
            "idx_orders_status",
            (row) => row.status
        ),
        orderDate: new BTreeIndex(
            "idx_orders_order_date",
            (row) => row.orderDate
        ),
    };

    for (const order of orders) {
        for (const index of Object.values(indexes)) {
            index.insert(order);
        }
    }

    const composite = new CompositeIndex(
        "idx_orders_customer_order_date"
    );
    composite.build(orders);

    const covering = new CoveringIndex();
    covering.build(orders);

    return { indexes, composite, covering };
}


function calculateSelectivity(orders, property, value) {
    const matches = orders.filter(
        (order) => order[property] === value
    ).length;

    return {
        matches,
        total: orders.length,
        fraction: orders.length === 0 ? 0 : matches / orders.length,
    };
}


async function main() {
    console.log("=".repeat(78));
    console.log("SQL INDEXES: B-TREE INDEXES AND QUERY PERFORMANCE");
    console.log("=".repeat(78));

    const orders = createOrders(300);
    const table = new OrdersTable(10);

    for (const order of orders) {
        table.insert(order);
    }

    const { indexes, composite, covering } = buildIndexes(orders);
    const engine = new QueryEngine(table, indexes);

    engine.on("queryStarted", (event) => {
        console.log(
            `[event] queryStarted operation=${event.operation} ` +
            `customerId=${event.customerId}`
        );
    });

    engine.on("queryFinished", (event) => {
        console.log(
            `[event] queryFinished path=${event.accessPath} ` +
            `pageReads=${event.pageReads}`
        );
    });

    console.log(`Rows: ${table.rowCount}`);
    console.log(`Table pages: ${table.pageCount}`);

    console.log("\nB-Tree structure:");
    for (const index of Object.values(indexes)) {
        console.log(index.describe());
    }

    console.log("\nEquality search:");
    const customerSearch = indexes.customer.equalityLookup(8);
    console.log({
        matchingRows: customerSearch.orderIds.length,
        bTreeNodeVisits: customerSearch.nodeVisits,
    });

    console.log("\nRange search:");
    const dateSearch = indexes.orderDate.rangeLookup(
        20260101,
        20260331
    );
    const rangeRows = table.fetchRows(dateSearch.orderIds);

    console.log({
        matchingRows: rangeRows.rows.length,
        bTreeNodeVisits: dateSearch.nodeVisits,
        tablePagesRead: rangeRows.pagesRead,
    });

    console.log("\nComposite index:");
    const compositeIds = composite.customerDateRange(
        8,
        20250101,
        20251231
    );

    console.log({
        index: composite.name,
        customerAndDateRows: compositeIds.length,
        customerOnlyRows: composite.customerOnly(8).length,
        dateOnlyNote:
            "The second key is not a leading key, so date-only access is not equivalent.",
    });

    console.log("\nCovering index:");
    const covered = covering.query(8);
    console.log({
        rowsReturnedFromIndexPayload: covered.length,
        baseTableLookupRequired: false,
        projectedColumns: ["orderId", "status", "totalAmount"],
    });

    console.log("\nQuery engine:");
    const customerQuery = await engine.findOrdersByCustomer(8);

    console.log({
        returnedRows: customerQuery.rows.length,
        accessPath: customerQuery.accessPath,
        logicalPageReads: customerQuery.pageReads,
    });

    console.log("\nSelectivity:");
    for (const [property, value] of [
        ["status", "PAID"],
        ["status", "CANCELLED"],
        ["customerId", 8],
    ]) {
        const statistics = calculateSelectivity(
            orders,
            property,
            value
        );

        console.log(
            `${property}=${value}: ` +
            `${statistics.matches}/${statistics.total} ` +
            `(${(statistics.fraction * 100).toFixed(2)}%)`
        );
    }

    console.log("\nIndex maintenance:");
    const target = table.rows.get(5);
    const oldKey = target.customerId;

    console.log(
        `Before update: order 5 has customerId=${oldKey}`
    );

    const updated = table.update(5, {
        customerId: 9999,
    });

    /*
     * An UPDATE to an indexed column changes the logical index entry.
     * Removing the old entry and inserting the new key models that
     * maintenance consequence explicitly.
     */
    indexes.customer.delete(5);
    indexes.customer.insert(updated);

    console.log(
        `After update: order 5 has customerId=${updated.customerId}`
    );

    console.log(
        "Old index lookup:",
        indexes.customer.equalityLookup(oldKey).orderIds.includes(5)
    );
    console.log(
        "New index lookup:",
        indexes.customer.equalityLookup(9999).orderIds.includes(5)
    );

    console.log("\nFailure handling:");

    try {
        indexes.orderDate.rangeLookup(20261231, 20260101);
    } catch (error) {
        console.log(`${error.name}: ${error.message}`);
    }

    try {
        table.insert(target);
    } catch (error) {
        console.log(`${error.name}: ${error.message}`);
    }

    console.log("\nPerformance interpretation:");
    console.log(
        "B-Trees provide ordered navigation rather than an unordered scan. " +
        "For selective predicates, the index can reduce the number of " +
        "base-table pages that must be inspected."
    );
    console.log(
        "Low-selectivity predicates can still require many row or page " +
        "lookups, making a sequential scan competitive or preferable."
    );
    console.log(
        "Every indexed column also creates write-maintenance work and " +
        "requires storage. Composite and covering indexes should therefore " +
        "correspond to actual query access patterns."
    );
    console.log(
        "Production decisions require the database engine's EXPLAIN plan, " +
        "statistics, buffer-cache state, data distribution, concurrency, " +
        "and workload rather than this simplified cost model."
    );
}


main().catch((error) => {
    console.error("Fatal execution error:", error);
    process.exitCode = 1;
});
