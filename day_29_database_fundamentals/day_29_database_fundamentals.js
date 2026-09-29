/*
 * Database Fundamentals: Tables, Records, Schemas, and Queries
 *
 * This self-contained JavaScript file demonstrates relational database
 * concepts using an in-memory database implemented by a small educational
 * relational engine. The engine is intentionally implemented with native
 * JavaScript data structures so the file has no npm dependencies.
 *
 * The examples cover:
 *   - schemas
 *   - tables and records
 *   - primary and foreign keys
 *   - constraints
 *   - CRUD operations
 *   - filtering, projection, sorting
 *   - joins
 *   - aggregation
 *   - transactions
 *   - indexes
 *   - normalization
 *   - parameterized-query concepts
 *   - validation and error handling
 *
 * Run with:
 *   node database_fundamentals.js
 */

"use strict";

class DatabaseError extends Error {
    constructor(message) {
        super(message);
        this.name = "DatabaseError";
    }
}

class ConstraintError extends DatabaseError {
    constructor(message) {
        super(message);
        this.name = "ConstraintError";
    }
}

class TransactionError extends DatabaseError {
    constructor(message) {
        super(message);
        this.name = "TransactionError";
    }
}

class Table {
    constructor(name, columns, options = {}) {
        this.name = name;
        this.columns = new Set(columns);
        this.primaryKey = options.primaryKey ?? null;
        this.foreignKeys = options.foreignKeys ?? {};
        this.uniqueColumns = new Set(options.uniqueColumns ?? []);
        this.notNullColumns = new Set(options.notNullColumns ?? []);
        this.checks = options.checks ?? [];
        this.rows = [];
        this.indexes = new Map();
    }

    validateColumns(record) {
        for (const column of Object.keys(record)) {
            if (!this.columns.has(column)) {
                throw new ConstraintError(
                    `Unknown column '${column}' in table '${this.name}'.`
                );
            }
        }

        for (const column of this.notNullColumns) {
            if (!(column in record) || record[column] === null || record[column] === undefined) {
                throw new ConstraintError(
                    `Column '${column}' cannot be NULL.`
                );
            }
        }
    }

    validateUnique(record, ignoreIndex = -1) {
        for (const column of this.uniqueColumns) {
            if (!(column in record)) {
                continue;
            }

            const duplicate = this.rows.some((existingRow, index) => {
                if (index === ignoreIndex) {
                    return false;
                }
                return existingRow[column] === record[column] &&
                    record[column] !== null &&
                    record[column] !== undefined;
            });

            if (duplicate) {
                throw new ConstraintError(
                    `Duplicate value for unique column '${column}'.`
                );
            }
        }

        if (this.primaryKey && record[this.primaryKey] !== undefined) {
            const duplicatePrimaryKey = this.rows.some((existingRow, index) => {
                return index !== ignoreIndex &&
                    existingRow[this.primaryKey] === record[this.primaryKey];
            });

            if (duplicatePrimaryKey) {
                throw new ConstraintError(
                    `Duplicate primary key '${record[this.primaryKey]}'.`
                );
            }
        }
    }

    validateChecks(record) {
        for (const check of this.checks) {
            if (!check.test(record)) {
                throw new ConstraintError(
                    check.message || `CHECK constraint failed on '${this.name}'.`
                );
            }
        }
    }

    insert(record) {
        this.validateColumns(record);
        this.validateUnique(record);
        this.validateChecks(record);

        const normalizedRecord = {};
        for (const column of this.columns) {
            normalizedRecord[column] =
                Object.prototype.hasOwnProperty.call(record, column)
                    ? record[column]
                    : null;
        }

        this.rows.push(normalizedRecord);
        this.rebuildIndexes();
        return { ...normalizedRecord };
    }

    update(predicate, changes) {
        let updated = 0;

        for (let index = 0; index < this.rows.length; index++) {
            if (!predicate(this.rows[index])) {
                continue;
            }

            const candidate = {
                ...this.rows[index],
                ...changes
            };

            this.validateColumns(candidate);
            this.validateUnique(candidate, index);
            this.validateChecks(candidate);

            this.rows[index] = candidate;
            updated++;
        }

        this.rebuildIndexes();
        return updated;
    }

    delete(predicate) {
        const originalLength = this.rows.length;
        this.rows = this.rows.filter(row => !predicate(row));
        this.rebuildIndexes();
        return originalLength - this.rows.length;
    }

    select(options = {}) {
        let result = this.rows.filter(options.where ?? (() => true));

        if (options.orderBy) {
            const { column, direction = "asc" } = options.orderBy;

            result.sort((left, right) => {
                if (left[column] === right[column]) {
                    return 0;
                }

                const comparison = left[column] < right[column] ? -1 : 1;
                return direction === "desc" ? -comparison : comparison;
            });
        }

        if (options.columns) {
            result = result.map(row => {
                const selected = {};
                for (const column of options.columns) {
                    selected[column] = row[column];
                }
                return selected;
            });
        } else {
            result = result.map(row => ({ ...row }));
        }

        if (options.limit !== undefined) {
            result = result.slice(0, options.limit);
        }

        return result;
    }

    createIndex(column) {
        if (!this.columns.has(column)) {
            throw new DatabaseError(
                `Cannot index unknown column '${column}'.`
            );
        }

        this.indexes.set(column, new Map());
        this.rebuildIndexes();
    }

    rebuildIndexes() {
        for (const column of this.indexes.keys()) {
            const index = new Map();

            for (const row of this.rows) {
                const key = row[column];

                if (!index.has(key)) {
                    index.set(key, []);
                }

                index.get(key).push(row);
            }

            this.indexes.set(column, index);
        }
    }

    lookupByIndex(column, value) {
        const index = this.indexes.get(column);

        if (!index) {
            return null;
        }

        return [...(index.get(value) ?? [])].map(row => ({ ...row }));
    }

    clone() {
        const copy = new Table(this.name, [...this.columns], {
            primaryKey: this.primaryKey,
            foreignKeys: { ...this.foreignKeys },
            uniqueColumns: [...this.uniqueColumns],
            notNullColumns: [...this.notNullColumns],
            checks: [...this.checks]
        });

        copy.rows = this.rows.map(row => ({ ...row }));

        for (const column of this.indexes.keys()) {
            copy.createIndex(column);
        }

        return copy;
    }
}

class Database {
    constructor() {
        this.tables = new Map();
        this.inTransaction = false;
        this.transactionSnapshot = null;
    }

    createTable(name, columns, options = {}) {
        if (this.tables.has(name)) {
            throw new DatabaseError(`Table '${name}' already exists.`);
        }

        this.tables.set(
            name,
            new Table(name, columns, options)
        );
    }

    table(name) {
        const table = this.tables.get(name);

        if (!table) {
            throw new DatabaseError(`Table '${name}' does not exist.`);
        }

        return table;
    }

    validateForeignKeys() {
        for (const table of this.tables.values()) {
            for (const row of table.rows) {
                for (const [column, reference] of Object.entries(table.foreignKeys)) {
                    const value = row[column];

                    if (value === null || value === undefined) {
                        continue;
                    }

                    const referencedTable = this.table(reference.table);

                    const exists = referencedTable.rows.some(
                        referencedRow => referencedRow[reference.column] === value
                    );

                    if (!exists) {
                        throw new ConstraintError(
                            `Foreign key ${table.name}.${column} references a missing ` +
                            `${reference.table}.${reference.column}.`
                        );
                    }
                }
            }
        }
    }

    beginTransaction() {
        if (this.inTransaction) {
            throw new TransactionError("A transaction is already active.");
        }

        this.transactionSnapshot = new Map();

        for (const [name, table] of this.tables) {
            this.transactionSnapshot.set(name, table.clone());
        }

        this.inTransaction = true;
    }

    commit() {
        if (!this.inTransaction) {
            throw new TransactionError("No transaction is active.");
        }

        this.validateForeignKeys();
        this.transactionSnapshot = null;
        this.inTransaction = false;
    }

    rollback() {
        if (!this.inTransaction) {
            throw new TransactionError("No transaction is active.");
        }

        this.tables = new Map();

        for (const [name, table] of this.transactionSnapshot) {
            this.tables.set(name, table);
        }

        this.transactionSnapshot = null;
        this.inTransaction = false;
    }

    transaction(callback) {
        this.beginTransaction();

        try {
            const result = callback();
            this.commit();
            return result;
        } catch (error) {
            this.rollback();
            throw error;
        }
    }
}

function printRows(title, rows) {
    console.log(`\n${title}`);

    if (rows.length === 0) {
        console.log("(no rows)");
        return;
    }

    console.table(rows);
}

function section(title) {
    console.log("\n" + "=".repeat(76));
    console.log(title);
    console.log("=".repeat(76));
}

function createSchema(database) {
    section("1. DATABASE SCHEMA");

    database.createTable(
        "departments",
        ["departmentId", "name", "budget"],
        {
            primaryKey: "departmentId",
            uniqueColumns: ["name"],
            notNullColumns: ["departmentId", "name", "budget"],
            checks: [
                {
                    test: row => row.budget >= 0,
                    message: "Department budget cannot be negative."
                }
            ]
        }
    );

    database.createTable(
        "employees",
        [
            "employeeId",
            "departmentId",
            "firstName",
            "lastName",
            "email",
            "salary",
            "active"
        ],
        {
            primaryKey: "employeeId",
            uniqueColumns: ["email"],
            notNullColumns: [
                "employeeId",
                "departmentId",
                "firstName",
                "lastName",
                "email",
                "salary"
            ],
            foreignKeys: {
                departmentId: {
                    table: "departments",
                    column: "departmentId"
                }
            },
            checks: [
                {
                    test: row => row.salary >= 0,
                    message: "Salary cannot be negative."
                },
                {
                    test: row => row.active === 0 || row.active === 1,
                    message: "Active must be 0 or 1."
                }
            ]
        }
    );

    database.createTable(
        "projects",
        ["projectId", "projectName", "budget", "status"],
        {
            primaryKey: "projectId",
            uniqueColumns: ["projectName"],
            notNullColumns: ["projectId", "projectName", "budget", "status"],
            checks: [
                {
                    test: row => row.budget >= 0,
                    message: "Project budget cannot be negative."
                },
                {
                    test: row =>
                        ["planned", "active", "completed"].includes(row.status),
                    message: "Invalid project status."
                }
            ]
        }
    );

    database.createTable(
        "employeeProjects",
        ["employeeId", "projectId", "assignedOn", "role"],
        {
            notNullColumns: [
                "employeeId",
                "projectId",
                "assignedOn",
                "role"
            ],
            foreignKeys: {
                employeeId: {
                    table: "employees",
                    column: "employeeId"
                },
                projectId: {
                    table: "projects",
                    column: "projectId"
                }
            },
            checks: [
                {
                    test: row => row.role.trim().length > 0,
                    message: "Project role cannot be empty."
                }
            ]
        }
    );

    console.log(
        "Schema created with primary keys, foreign keys, unique constraints, " +
        "NOT NULL rules, and CHECK constraints."
    );
}

function insertData(database) {
    section("2. RECORDS");

    const departments = database.table("departments");
    const employees = database.table("employees");
    const projects = database.table("projects");
    const employeeProjects = database.table("employeeProjects");

    [
        [1, "Engineering", 2000000],
        [2, "Finance", 1200000],
        [3, "Operations", 900000],
        [4, "Research", 1500000]
    ].forEach(([departmentId, name, budget]) => {
        departments.insert({ departmentId, name, budget });
    });

    [
        [101, 1, "Asha", "Sharma", "asha@example.com", 120000, 1],
        [102, 1, "Ravi", "Kumar", "ravi@example.com", 95000, 1],
        [103, 2, "Neha", "Singh", "neha@example.com", 110000, 1],
        [104, 2, "Arjun", "Mehta", "arjun@example.com", 85000, 1],
        [105, 3, "Priya", "Verma", "priya@example.com", 78000, 0],
        [106, 4, "Kabir", "Das", "kabir@example.com", 135000, 1]
    ].forEach(
        ([employeeId, departmentId, firstName, lastName, email, salary, active]) => {
            employees.insert({
                employeeId,
                departmentId,
                firstName,
                lastName,
                email,
                salary,
                active
            });
        }
    );

    [
        [201, "Data Platform", 500000, "active"],
        [202, "Risk Engine", 350000, "active"],
        [203, "Automation", 180000, "completed"]
    ].forEach(([projectId, projectName, budget, status]) => {
        projects.insert({
            projectId,
            projectName,
            budget,
            status
        });
    });

    [
        [101, 201, "2025-01-10", "Architect"],
        [102, 201, "2025-02-01", "Developer"],
        [103, 202, "2025-03-15", "Analyst"],
        [106, 202, "2025-03-20", "Researcher"],
        [102, 203, "2024-01-01", "Developer"]
    ].forEach(([employeeId, projectId, assignedOn, role]) => {
        employeeProjects.insert({
            employeeId,
            projectId,
            assignedOn,
            role
        });
    });

    database.validateForeignKeys();

    printRows(
        "Employees:",
        employees.select({
            columns: ["employeeId", "firstName", "lastName", "salary"]
        })
    );
}

function demonstrateQueries(database) {
    section("3. FILTERING, PROJECTION, SORTING, AND LIMITING");

    const employees = database.table("employees");

    const activeEmployees = employees.select({
        where: employee => employee.active === 1,
        columns: ["employeeId", "firstName", "lastName"],
        orderBy: { column: "lastName" }
    });

    printRows("Active employees:", activeEmployees);

    const highEarners = employees.select({
        where: employee => employee.salary >= 100000,
        columns: ["firstName", "lastName", "salary"],
        orderBy: { column: "salary", direction: "desc" },
        limit: 3
    });

    printRows("Top three salaries:", highEarners);

    console.log(
        "\nThis corresponds conceptually to SQL operations such as " +
        "SELECT, WHERE, ORDER BY, and LIMIT."
    );
}

function demonstrateJoins(database) {
    section("4. JOIN-LIKE OPERATIONS");

    const employees = database.table("employees").rows;
    const departments = database.table("departments").rows;
    const projects = database.table("projects").rows;
    const assignments = database.table("employeeProjects").rows;

    const employeeDepartmentRows = employees.map(employee => {
        const department = departments.find(
            item => item.departmentId === employee.departmentId
        );

        return {
            employee: `${employee.firstName} ${employee.lastName}`,
            department: department?.name ?? null,
            salary: employee.salary
        };
    });

    printRows("Employees joined with departments:", employeeDepartmentRows);

    const employeeProjectRows = assignments.map(assignment => {
        const employee = employees.find(
            item => item.employeeId === assignment.employeeId
        );

        const project = projects.find(
            item => item.projectId === assignment.projectId
        );

        return {
            employee: `${employee.firstName} ${employee.lastName}`,
            project: project.projectName,
            role: assignment.role
        };
    });

    printRows("Many-to-many employee/project relationship:", employeeProjectRows);

    console.log(
        "\nA join combines related rows through a shared key. " +
        "The employeeProjects table acts as a junction table."
    );
}

function demonstrateAggregation(database) {
    section("5. AGGREGATION");

    const employees = database.table("employees").rows;

    const totalSalary = employees.reduce(
        (sum, employee) => sum + employee.salary,
        0
    );

    const averageSalary = totalSalary / employees.length;

    const departmentGroups = new Map();

    for (const employee of employees) {
        if (!departmentGroups.has(employee.departmentId)) {
            departmentGroups.set(employee.departmentId, []);
        }

        departmentGroups.get(employee.departmentId).push(employee);
    }

    const departmentStats = [];

    for (const [departmentId, members] of departmentGroups) {
        const payroll = members.reduce(
            (sum, employee) => sum + employee.salary,
            0
        );

        departmentStats.push({
            departmentId,
            employeeCount: members.length,
            averageSalary: Math.round((payroll / members.length) * 100) / 100,
            payroll
        });
    }

    printRows("Company statistics:", [
        {
            employeeCount: employees.length,
            averageSalary,
            totalSalary
        }
    ]);

    printRows("Department statistics:", departmentStats);
}

function demonstrateCrud(database) {
    section("6. CREATE, READ, UPDATE, DELETE");

    const employees = database.table("employees");

    employees.insert({
        employeeId: 107,
        departmentId: 3,
        firstName: "Isha",
        lastName: "Roy",
        email: "isha@example.com",
        salary: 72000,
        active: 1
    });

    console.log("Inserted employee 107.");

    const updated = employees.update(
        employee => employee.employeeId === 107,
        { salary: 75000 }
    );

    console.log(`Updated rows: ${updated}`);

    const deleted = employees.delete(
        employee => employee.employeeId === 107
    );

    console.log(`Deleted rows: ${deleted}`);
}

function demonstrateConstraints(database) {
    section("7. CONSTRAINT VALIDATION");

    const employees = database.table("employees");

    try {
        employees.insert({
            employeeId: 999,
            departmentId: 1,
            firstName: "Duplicate",
            lastName: "Email",
            email: "asha@example.com",
            salary: 50000,
            active: 1
        });
    } catch (error) {
        console.log(`Duplicate email rejected: ${error.message}`);
    }

    try {
        employees.insert({
            employeeId: 998,
            departmentId: 1,
            firstName: "Negative",
            lastName: "Salary",
            email: "negative@example.com",
            salary: -100,
            active: 1
        });
    } catch (error) {
        console.log(`Negative salary rejected: ${error.message}`);
    }

    try {
        employees.insert({
            employeeId: 997,
            departmentId: 999,
            firstName: "Bad",
            lastName: "Department",
            email: "baddepartment@example.com",
            salary: 50000,
            active: 1
        });

        database.validateForeignKeys();
        throw new Error("Invalid foreign key was accepted.");
    } catch (error) {
        console.log(`Foreign-key validation: ${error.message}`);

        /*
         * The failed insert remains in the educational engine until an
         * explicit transaction rollback is used. This illustrates why
         * application operations that must be atomic should be grouped
         * inside transactions.
         */
        employees.delete(
            employee => employee.employeeId === 997
        );
    }
}

function demonstrateTransactions(database) {
    section("8. TRANSACTIONS");

    const accounts = new Table(
        "accounts",
        ["accountId", "owner", "balance"],
        {
            primaryKey: "accountId",
            notNullColumns: ["accountId", "owner", "balance"],
            checks: [
                {
                    test: row => row.balance >= 0,
                    message: "Account balance cannot be negative."
                }
            ]
        }
    );

    database.tables.set("accounts", accounts);

    accounts.insert({
        accountId: 1,
        owner: "Alice",
        balance: 1000
    });

    accounts.insert({
        accountId: 2,
        owner: "Bob",
        balance: 500
    });

    database.transaction(() => {
        const amount = 200;

        const sender = accounts.rows.find(row => row.accountId === 1);

        if (sender.balance < amount) {
            throw new TransactionError("Insufficient funds.");
        }

        accounts.update(
            row => row.accountId === 1,
            { balance: sender.balance - amount }
        );

        accounts.update(
            row => row.accountId === 2,
            {
                balance:
                    accounts.rows.find(row => row.accountId === 2).balance +
                    amount
            }
        );
    });

    printRows("Balances after transaction:", accounts.select());
}

function demonstrateRollback(database) {
    section("9. ROLLBACK ON FAILURE");

    const accounts = database.table("accounts");

    try {
        database.transaction(() => {
            accounts.update(
                row => row.accountId === 1,
                { balance: 700 }
            );

            throw new Error("Simulated downstream failure.");
        });
    } catch (error) {
        console.log(`Transaction rolled back: ${error.message}`);
    }

    printRows("Balances after rollback:", accounts.select());
}

function demonstrateIndexes(database) {
    section("10. INDEXES");

    const employees = database.table("employees");

    employees.createIndex("departmentId");

    const indexedRows = employees.lookupByIndex("departmentId", 1);

    printRows(
        "Indexed lookup for department 1:",
        indexedRows.map(row => ({
            employeeId: row.employeeId,
            firstName: row.firstName,
            salary: row.salary
        }))
    );

    console.log(
        "\nIndexes improve suitable lookups by maintaining an auxiliary " +
        "mapping from a search key to matching rows."
    );

    console.log(
        "Trade-off: indexes consume memory/storage and add maintenance cost " +
        "to writes."
    );
}

function demonstrateParameterizedQueryConcept() {
    section("11. PARAMETERIZED QUERY CONCEPT");

    const userInput = "Asha' OR '1'='1";

    console.log(
        "Untrusted input:",
        userInput
    );

    console.log(
        "\nA real SQL driver should receive:",
        "SELECT ... WHERE name = ?",
        "with the input supplied separately as a parameter."
    );

    console.log(
        "Never build SQL by concatenating untrusted strings into SQL syntax."
    );
}

function demonstrateNormalization() {
    section("12. NORMALIZATION");

    console.log(`
An unnormalized order record might contain:

orderId, customerName, customerEmail, product1, product2, product3

A normalized relational design separates entities:

customers
  customerId, name, email

orders
  orderId, customerId, orderDate

products
  productId, name, price

orderItems
  orderId, productId, quantity

1NF removes repeating groups and promotes atomic values.
2NF removes partial dependencies from composite-key designs.
3NF reduces transitive dependencies between non-key attributes.

Normalization reduces redundancy and update anomalies. Deliberate
denormalization may be appropriate for some read-heavy workloads, but
duplicated data requires consistency management.
`);
}

function demonstrateNull() {
    section("13. NULL");

    const records = [
        { id: 1, score: 90 },
        { id: 2, score: null },
        { id: 3, score: 20 }
    ];

    const missing = records.filter(record => record.score === null);

    printRows("Records with explicitly missing scores:", missing);

    console.log(
        "\nNULL is not the same as zero, false, or an empty string."
    );
}

function demonstrateComplexity() {
    section("14. PERFORMANCE REASONING");

    console.log(`
A simple array scan for equality lookup is approximately O(n).

An indexed lookup can approach O(1) average access in hash-like structures,
or O(log n) in balanced tree structures, depending on the database index.

Sorting is commonly O(n log n).

A join can range from relatively efficient indexed access to expensive
nested-loop or large intermediate-result operations depending on the query
plan, indexes, data distribution, and database engine.

Performance should be measured using realistic data and actual query plans.
Correctness comes before premature optimization.
`);
}

function demonstrateApplicationDesign() {
    section("15. APPLICATION-LAYER DESIGN");

    class EmployeeRepository {
        constructor(database) {
            this.database = database;
        }

        findActiveByDepartment(departmentId) {
            return this.database
                .table("employees")
                .select({
                    where: employee =>
                        employee.departmentId === departmentId &&
                        employee.active === 1,
                    columns: [
                        "employeeId",
                        "firstName",
                        "lastName",
                        "salary"
                    ],
                    orderBy: {
                        column: "lastName"
                    }
                });
        }
    }

    const database = globalDatabase;
    const repository = new EmployeeRepository(database);

    printRows(
        "Repository result:",
        repository.findActiveByDepartment(1)
    );

    console.log(
        "\nA repository can isolate persistence details from higher-level " +
        "application logic. In a production system it would normally call " +
        "a real database driver rather than an educational in-memory engine."
    );
}

const globalDatabase = new Database();

function main() {
    createSchema(globalDatabase);
    insertData(globalDatabase);
    demonstrateQueries(globalDatabase);
    demonstrateJoins(globalDatabase);
    demonstrateAggregation(globalDatabase);
    demonstrateCrud(globalDatabase);
    demonstrateConstraints(globalDatabase);
    demonstrateTransactions(globalDatabase);
    demonstrateRollback(globalDatabase);
    demonstrateIndexes(globalDatabase);
    demonstrateParameterizedQueryConcept();
    demonstrateNormalization();
    demonstrateNull();
    demonstrateComplexity();
    demonstrateApplicationDesign();

    section("16. COMPLETED");
    console.log(
        "Database fundamentals demonstrated through a self-contained " +
        "relational model."
    );
}

main();
