"use strict";

/*
 * Database Normalization in JavaScript
 *
 * This program models an order-management system and focuses on a different
 * perspective from the Python implementation:
 *
 * - 1NF is represented through an event-driven transformation of repeating
 *   order-line groups into atomic records.
 * - 2NF is evaluated through dependency rules against a composite key.
 * - 3NF is evaluated through transitive dependency analysis.
 * - Denormalization is represented as a materialized reporting projection.
 * - A policy engine identifies anomalies and determines whether a design
 *   satisfies the declared normalization rules.
 *
 * Run with:
 *   node database-normalization.js
 */

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

function heading(title) {
  console.log(`\n${"=".repeat(76)}`);
  console.log(title);
  console.log("=".repeat(76));
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function printTable(rows, columns = null) {
  if (rows.length === 0) {
    console.log("(no rows)");
    return;
  }

  const selectedColumns = columns || Object.keys(rows[0]);

  const widths = Object.fromEntries(
    selectedColumns.map((column) => [
      column,
      Math.max(
        column.length,
        ...rows.map((row) => String(row[column] ?? "").length)
      ),
    ])
  );

  console.log(
    selectedColumns.map((column) => column.padEnd(widths[column])).join(" | ")
  );

  console.log(
    selectedColumns
      .map((column) => "-".repeat(widths[column]))
      .join("-+-")
  );

  for (const row of rows) {
    console.log(
      selectedColumns
        .map((column) => String(row[column] ?? "").padEnd(widths[column]))
        .join(" | ")
    );
  }
}


// ---------------------------------------------------------------------------
// Functional dependency engine
// ---------------------------------------------------------------------------

class FunctionalDependency {
  constructor(determinant, dependent) {
    this.determinant = new Set(determinant);
    this.dependent = new Set(dependent);
  }

  description() {
    return `${[...this.determinant].sort().join(", ")} -> ${
      [...this.dependent].sort().join(", ")
    }`;
  }
}

function isSubset(subset, set) {
  for (const value of subset) {
    if (!set.has(value)) {
      return false;
    }
  }
  return true;
}

function attributeClosure(attributes, dependencies) {
  const closure = new Set(attributes);

  let changed = true;

  while (changed) {
    changed = false;

    for (const dependency of dependencies) {
      if (!isSubset(dependency.determinant, closure)) {
        continue;
      }

      for (const attribute of dependency.dependent) {
        if (!closure.has(attribute)) {
          closure.add(attribute);
          changed = true;
        }
      }
    }
  }

  return closure;
}

function isSuperkey(attributes, relationAttributes, dependencies) {
  const closure = attributeClosure(attributes, dependencies);
  return isSubset(relationAttributes, closure);
}

function findCandidateKeys(relationAttributes, dependencies) {
  const attributes = [...relationAttributes].sort();
  const keys = [];

  function combinations(start, size, selected) {
    if (selected.length === size) {
      const candidate = new Set(selected);

      if (keys.some((existing) => isSubset(existing, candidate))) {
        return;
      }

      if (isSuperkey(candidate, relationAttributes, dependencies)) {
        keys.push(candidate);
      }

      return;
    }

    for (let index = start; index < attributes.length; index += 1) {
      selected.push(attributes[index]);
      combinations(index + 1, size, selected);
      selected.pop();
    }
  }

  for (let size = 1; size <= attributes.length; size += 1) {
    combinations(0, size, []);
  }

  return keys;
}


// ---------------------------------------------------------------------------
// 1NF transformation
// ---------------------------------------------------------------------------

const unnormalizedOrders = [
  {
    orderId: 7001,
    customerId: "C01",
    customerName: "Neha Singh",
    city: "Lucknow",
    products: [
      { productId: "P01", productName: "Keyboard", quantity: 2, price: 1800 },
      { productId: "P02", productName: "Mouse", quantity: 1, price: 700 },
    ],
  },
  {
    orderId: 7002,
    customerId: "C02",
    customerName: "Arjun Mehta",
    city: "Delhi",
    products: [
      { productId: "P02", productName: "Mouse", quantity: 2, price: 700 },
      { productId: "P03", productName: "Monitor", quantity: 1, price: 12000 },
    ],
  },
];

function validateRepeatingGroupAlignment(order) {
  if (!Array.isArray(order.products)) {
    throw new TypeError(`Order ${order.orderId} has no product collection`);
  }

  for (const product of order.products) {
    if (!product.productId || !product.productName) {
      throw new Error(`Order ${order.orderId} contains an incomplete product`);
    }

    if (!Number.isInteger(product.quantity) || product.quantity <= 0) {
      throw new Error(`Invalid quantity in order ${order.orderId}`);
    }

    if (!Number.isFinite(product.price) || product.price < 0) {
      throw new Error(`Invalid price in order ${order.orderId}`);
    }
  }
}

function toFirstNormalForm(orders) {
  const rows = [];

  for (const order of orders) {
    validateRepeatingGroupAlignment(order);

    for (const product of order.products) {
      rows.push({
        orderId: order.orderId,
        customerId: order.customerId,
        customerName: order.customerName,
        city: order.city,
        productId: product.productId,
        productName: product.productName,
        quantity: product.quantity,
        unitPrice: product.price,
      });
    }
  }

  return rows;
}

function hasCollectionValues(rows) {
  return rows.some((row) =>
    Object.values(row).some((value) => Array.isArray(value) || typeof value === "object")
  );
}


// ---------------------------------------------------------------------------
// 2NF analysis
// ---------------------------------------------------------------------------

function analyzeSecondNormalForm() {
  const attributes = new Set([
    "orderId",
    "productId",
    "customerId",
    "customerName",
    "productName",
    "quantity",
  ]);

  const dependencies = [
    new FunctionalDependency(["orderId"], ["customerId", "customerName"]),
    new FunctionalDependency(["productId"], ["productName"]),
    new FunctionalDependency(["orderId", "productId"], ["quantity"]),
  ];

  const key = new Set(["orderId", "productId"]);

  const partialDependencies = dependencies.filter(
    (dependency) =>
      dependency.determinant.size < key.size &&
      isSubset(dependency.determinant, key)
  );

  return {
    attributes,
    dependencies,
    key,
    partialDependencies,
  };
}


// ---------------------------------------------------------------------------
// 3NF analysis
// ---------------------------------------------------------------------------

function analyzeThirdNormalForm() {
  /*
   * ProductID -> CategoryID
   * CategoryID -> CategoryName
   *
   * CategoryName therefore reaches ProductID through CategoryID.
   * This is the transitive dependency that the decomposition removes.
   */
  const attributes = new Set([
    "productId",
    "productName",
    "categoryId",
    "categoryName",
  ]);

  const dependencies = [
    new FunctionalDependency(["productId"], ["productName", "categoryId"]),
    new FunctionalDependency(["categoryId"], ["categoryName"]),
  ];

  const productClosure = attributeClosure(
    new Set(["productId"]),
    dependencies
  );

  const transitiveDependencyExists =
    productClosure.has("categoryId") &&
    productClosure.has("categoryName") &&
    !dependencies.some(
      (dependency) =>
        dependency.determinant.size === 1 &&
        dependency.determinant.has("productId") &&
        dependency.dependent.has("categoryName")
    );

  return {
    attributes,
    dependencies,
    productClosure,
    transitiveDependencyExists,
  };
}


// ---------------------------------------------------------------------------
// Event-driven normalization workflow
// ---------------------------------------------------------------------------

class NormalizationPipeline {
  constructor() {
    this.handlers = new Map();
  }

  on(eventName, handler) {
    if (!this.handlers.has(eventName)) {
      this.handlers.set(eventName, []);
    }

    this.handlers.get(eventName).push(handler);
  }

  emit(eventName, payload) {
    const handlers = this.handlers.get(eventName) || [];

    for (const handler of handlers) {
      handler(payload);
    }
  }

  normalizeTo1NF(orders) {
    this.emit("before1NF", orders);

    const result = toFirstNormalForm(orders);

    this.emit("after1NF", result);

    return result;
  }
}


// ---------------------------------------------------------------------------
// 3NF repository model
// ---------------------------------------------------------------------------

class NormalizedRepository {
  constructor() {
    this.customers = new Map();
    this.categories = new Map();
    this.products = new Map();
    this.orders = new Map();
  }

  addCustomer(customer) {
    if (this.customers.has(customer.customerId)) {
      throw new Error(`Duplicate customer key: ${customer.customerId}`);
    }

    this.customers.set(customer.customerId, clone(customer));
  }

  addCategory(category) {
    if (this.categories.has(category.categoryId)) {
      throw new Error(`Duplicate category key: ${category.categoryId}`);
    }

    this.categories.set(category.categoryId, clone(category));
  }

  addProduct(product) {
    if (this.products.has(product.productId)) {
      throw new Error(`Duplicate product key: ${product.productId}`);
    }

    if (!this.categories.has(product.categoryId)) {
      throw new Error(
        `Foreign-key violation: category ${product.categoryId} does not exist`
      );
    }

    if (product.price < 0) {
      throw new Error("Product price cannot be negative");
    }

    this.products.set(product.productId, clone(product));
  }

  addOrder(order) {
    if (this.orders.has(order.orderId)) {
      throw new Error(`Duplicate order key: ${order.orderId}`);
    }

    if (!this.customers.has(order.customerId)) {
      throw new Error(
        `Foreign-key violation: customer ${order.customerId} does not exist`
      );
    }

    const lineProducts = new Set();

    for (const line of order.lines) {
      if (line.orderId !== order.orderId) {
        throw new Error("Order-line parent key mismatch");
      }

      if (lineProducts.has(line.productId)) {
        throw new Error(
          `Composite-key violation: product ${line.productId} occurs twice`
        );
      }

      if (!this.products.has(line.productId)) {
        throw new Error(
          `Foreign-key violation: product ${line.productId} does not exist`
        );
      }

      if (!Number.isInteger(line.quantity) || line.quantity <= 0) {
        throw new Error("Order quantity must be a positive integer");
      }

      lineProducts.add(line.productId);
    }

    this.orders.set(order.orderId, clone(order));
  }

  calculateOrderTotal(orderId) {
    const order = this.orders.get(orderId);

    if (!order) {
      throw new Error(`Order ${orderId} does not exist`);
    }

    return order.lines.reduce((total, line) => {
      const product = this.products.get(line.productId);
      return total + product.price * line.quantity;
    }, 0);
  }
}


// ---------------------------------------------------------------------------
// Denormalized materialized view
// ---------------------------------------------------------------------------

class SalesMaterializedView {
  constructor(repository) {
    this.repository = repository;
    this.rows = [];
    this.version = 0;
  }

  rebuild() {
    const nextRows = [];

    for (const order of this.repository.orders.values()) {
      const customer = this.repository.customers.get(order.customerId);

      for (const line of order.lines) {
        const product = this.repository.products.get(line.productId);
        const category = this.repository.categories.get(product.categoryId);

        nextRows.push({
          orderId: order.orderId,
          customerId: customer.customerId,
          customerName: customer.name,
          productId: product.productId,
          productName: product.name,
          categoryName: category.name,
          quantity: line.quantity,
          unitPrice: product.price,
          lineTotal: product.price * line.quantity,
        });
      }
    }

    this.rows = nextRows;
    this.version += 1;
  }

  findCustomerSales(customerId) {
    return this.rows.filter((row) => row.customerId === customerId);
  }

  validateFreshness() {
    const problems = [];

    for (const row of this.rows) {
      const customer = this.repository.customers.get(row.customerId);
      const product = this.repository.products.get(row.productId);
      const category = product
        ? this.repository.categories.get(product.categoryId)
        : null;

      if (!customer) {
        problems.push(`Missing customer ${row.customerId}`);
        continue;
      }

      if (!product) {
        problems.push(`Missing product ${row.productId}`);
        continue;
      }

      if (!category) {
        problems.push(`Missing category for ${row.productId}`);
        continue;
      }

      if (row.customerName !== customer.name) {
        problems.push(`Stale customer name for ${row.customerId}`);
      }

      if (row.productName !== product.name) {
        problems.push(`Stale product name for ${row.productId}`);
      }

      if (row.categoryName !== category.name) {
        problems.push(`Stale category name for ${row.productId}`);
      }

      if (row.unitPrice !== product.price) {
        problems.push(`Stale price for ${row.productId}`);
      }
    }

    return problems;
  }
}


// ---------------------------------------------------------------------------
// Design comparison
// ---------------------------------------------------------------------------

function demonstrateNormalizationPipeline() {
  heading("1NF transformation through an event-driven pipeline");

  const pipeline = new NormalizationPipeline();

  pipeline.on("before1NF", (orders) => {
    console.log(`Input orders: ${orders.length}`);
  });

  pipeline.on("after1NF", (rows) => {
    console.log(`Atomic order-line rows: ${rows.length}`);
  });

  const rows = pipeline.normalizeTo1NF(unnormalizedOrders);

  printTable(rows);

  assert(!hasCollectionValues(rows), "1NF result contains a collection value");

  return rows;
}

function demonstrate2NF() {
  heading("2NF: partial dependencies");

  const analysis = analyzeSecondNormalForm();

  console.log(
    `Composite key: (${[...analysis.key].join(", ")})`
  );

  console.log("Functional dependencies:");
  for (const dependency of analysis.dependencies) {
    console.log(`  ${dependency.description()}`);
  }

  console.log("Partial dependencies detected:");
  for (const dependency of analysis.partialDependencies) {
    console.log(`  ${dependency.description()}`);
  }

  console.log(
    "\nThe dependency OrderID -> customer attributes means those attributes "
    + "do not require the complete composite order-line key. ProductID -> "
    + "product attributes has the same problem from the other side."
  );
}

function demonstrate3NF() {
  heading("3NF: transitive dependency");

  const analysis = analyzeThirdNormalForm();

  console.log("Functional dependencies:");
  for (const dependency of analysis.dependencies) {
    console.log(`  ${dependency.description()}`);
  }

  console.log(
    `\nProductID closure: ${[...analysis.productClosure].sort().join(", ")}`
  );

  console.log(
    `Transitive dependency detected: ${analysis.transitiveDependencyExists}`
  );

  console.log(
    "\nThe 3NF decomposition stores CategoryName with CategoryID rather than "
    + "repeating it inside every product row."
  );
}

function demonstrateCandidateKeys() {
  heading("Candidate-key discovery");

  const relationAttributes = new Set([
    "orderId",
    "productId",
    "customerId",
    "customerName",
    "productName",
    "quantity",
  ]);

  const dependencies = [
    new FunctionalDependency(["orderId"], ["customerId"]),
    new FunctionalDependency(["customerId"], ["customerName"]),
    new FunctionalDependency(["productId"], ["productName"]),
    new FunctionalDependency(["orderId", "productId"], ["quantity"]),
  ];

  const keys = findCandidateKeys(relationAttributes, dependencies);

  for (const key of keys) {
    console.log(`Candidate key: {${[...key].join(", ")}}`);
  }
}


// ---------------------------------------------------------------------------
// Practical denormalization scenario
// ---------------------------------------------------------------------------

function buildRepository() {
  const repository = new NormalizedRepository();

  repository.addCustomer({
    customerId: "C01",
    name: "Neha Singh",
    city: "Lucknow",
  });

  repository.addCustomer({
    customerId: "C02",
    name: "Arjun Mehta",
    city: "Delhi",
  });

  repository.addCategory({
    categoryId: "CAT1",
    name: "Peripherals",
  });

  repository.addCategory({
    categoryId: "CAT2",
    name: "Displays",
  });

  repository.addProduct({
    productId: "P01",
    name: "Keyboard",
    categoryId: "CAT1",
    price: 1800,
  });

  repository.addProduct({
    productId: "P02",
    name: "Mouse",
    categoryId: "CAT1",
    price: 700,
  });

  repository.addProduct({
    productId: "P03",
    name: "Monitor",
    categoryId: "CAT2",
    price: 12000,
  });

  repository.addOrder({
    orderId: 7001,
    customerId: "C01",
    lines: [
      { orderId: 7001, productId: "P01", quantity: 2 },
      { orderId: 7001, productId: "P02", quantity: 1 },
    ],
  });

  repository.addOrder({
    orderId: 7002,
    customerId: "C02",
    lines: [
      { orderId: 7002, productId: "P02", quantity: 2 },
      { orderId: 7002, productId: "P03", quantity: 1 },
    ],
  });

  return repository;
}

function demonstrateDenormalization() {
  heading("Denormalization as a read-optimized projection");

  const repository = buildRepository();
  const view = new SalesMaterializedView(repository);

  view.rebuild();

  console.log("Materialized rows:");
  printTable(view.rows);

  console.log("\nCustomer C01 sales:");
  printTable(view.findCustomerSales("C01"));

  console.log(`\nMaterialized-view version: ${view.version}`);

  repository.products.get("P02").price = 750;

  console.log(
    "\nP02 price changed in the normalized source from 700 to 750."
  );

  const staleProblems = view.validateFreshness();

  console.log("Freshness validation:");
  for (const problem of staleProblems) {
    console.log(`  STALE: ${problem}`);
  }

  view.rebuild();

  console.log(
    `\nView rebuilt. New version: ${view.version}. `
    + `Freshness problems: ${view.validateFreshness().length}`
  );
}


// ---------------------------------------------------------------------------
// Anomaly detection
// ---------------------------------------------------------------------------

function detectFunctionalDependencyViolations(rows, determinant, dependent) {
  const values = new Map();

  for (const row of rows) {
    const determinantValue = row[determinant];

    if (!values.has(determinantValue)) {
      values.set(determinantValue, new Set());
    }

    values.get(determinantValue).add(row[dependent]);
  }

  return [...values.entries()]
    .filter(([, dependentValues]) => dependentValues.size > 1)
    .map(([key, dependentValues]) => ({
      determinantValue: key,
      dependentValues: [...dependentValues],
    }));
}

function demonstrateAnomalies() {
  heading("Functional-dependency violation");

  const inconsistentRows = [
    {
      productId: "P02",
      productName: "Mouse",
    },
    {
      productId: "P02",
      productName: "Wireless Mouse",
    },
  ];

  printTable(inconsistentRows);

  const violations = detectFunctionalDependencyViolations(
    inconsistentRows,
    "productId",
    "productName"
  );

  console.log("\nViolations:");
  printTable(violations);
}


// ---------------------------------------------------------------------------
// Failure cases
// ---------------------------------------------------------------------------

function demonstrateFailureCases() {
  heading("Integrity failures caused by bad decomposition data");

  const repository = new NormalizedRepository();

  repository.addCategory({
    categoryId: "CAT1",
    name: "Peripherals",
  });

  try {
    repository.addProduct({
      productId: "P404",
      name: "Orphan Product",
      categoryId: "CAT404",
      price: 100,
    });
  } catch (error) {
    console.log(`Unknown category rejected: ${error.message}`);
  }

  repository.addCustomer({
    customerId: "C01",
    name: "Neha Singh",
    city: "Lucknow",
  });

  repository.addProduct({
    productId: "P01",
    name: "Keyboard",
    categoryId: "CAT1",
    price: 1800,
  });

  try {
    repository.addOrder({
      orderId: 9001,
      customerId: "C01",
      lines: [
        { orderId: 9001, productId: "P01", quantity: 1 },
        { orderId: 9001, productId: "P01", quantity: 2 },
      ],
    });
  } catch (error) {
    console.log(`Duplicate composite key rejected: ${error.message}`);
  }

  try {
    repository.addOrder({
      orderId: 9002,
      customerId: "C404",
      lines: [],
    });
  } catch (error) {
    console.log(`Unknown customer rejected: ${error.message}`);
  }
}


// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  heading("Database Normalization: 1NF, 2NF, 3NF, Denormalization");

  demonstrateNormalizationPipeline();
  demonstrate2NF();
  demonstrate3NF();
  demonstrateCandidateKeys();
  demonstrateAnomalies();
  demonstrateDenormalization();
  demonstrateFailureCases();

  heading("Design interpretation");

  console.log(
    "1NF makes the relation represent atomic values and one order line per row."
  );

  console.log(
    "2NF removes attributes that depend on only part of a composite key."
  );

  console.log(
    "3NF removes non-key attributes that depend transitively on another non-key attribute."
  );

  console.log(
    "Denormalization intentionally reintroduces selected duplication when a "
    + "measured read workload justifies the consistency and storage trade-off."
  );
}

main();
