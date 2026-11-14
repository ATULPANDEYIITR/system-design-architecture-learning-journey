"use strict";

/*
 * CQRS: Command Query Responsibility Segregation
 *
 * Event-driven implementation using:
 * - Separate command and query services
 * - Immutable domain events
 * - Aggregate version checks
 * - Idempotent command processing
 * - Asynchronous projections
 * - Event subscriptions
 * - Projection checkpoints
 * - Failure isolation and replay
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const EventEmitter = require("node:events");

// ============================================================
// 1. ERRORS
// ============================================================

class CQRSException extends Error {}
class ValidationError extends CQRSException {}
class NotFoundError extends CQRSException {}
class ConcurrencyError extends CQRSException {}
class InsufficientFundsError extends CQRSException {}
class DuplicateCommandError extends CQRSException {}
class ProjectionError extends CQRSException {}

// ============================================================
// 2. DOMAIN ENUMERATIONS
// ============================================================

const CommandType = Object.freeze({
    CREATE_ACCOUNT: "CREATE_ACCOUNT",
    DEPOSIT: "DEPOSIT",
    WITHDRAW: "WITHDRAW",
});

const EventType = Object.freeze({
    ACCOUNT_CREATED: "ACCOUNT_CREATED",
    MONEY_DEPOSITED: "MONEY_DEPOSITED",
    MONEY_WITHDRAWN: "MONEY_WITHDRAWN",
});

// ============================================================
// 3. VALIDATION
// ============================================================

function validateIdentifier(value, field) {
    if (
        typeof value !== "string" ||
        value.trim().length === 0 ||
        value.length > 100
    ) {
        throw new ValidationError(`Invalid ${field}.`);
    }
}

function validateAmount(amount) {
    if (
        typeof amount !== "number" ||
        !Number.isFinite(amount) ||
        amount <= 0 ||
        Math.round(amount * 100) !== amount * 100
    ) {
        throw new ValidationError(
            "Amount must be a positive monetary value with at most two decimals."
        );
    }
}

function roundMoney(value) {
    return Math.round((value + Number.EPSILON) * 100) / 100;
}

// ============================================================
// 4. COMMAND OBJECT
// ============================================================

class Command {
    constructor(type, accountId, payload = {}, expectedVersion = null) {
        if (!Object.values(CommandType).includes(type)) {
            throw new ValidationError("Unknown command type.");
        }

        validateIdentifier(accountId, "account identifier");

        this.id = crypto.randomUUID();
        this.type = type;
        this.accountId = accountId;
        this.payload = Object.freeze({ ...payload });
        this.expectedVersion = expectedVersion;

        Object.freeze(this);
    }
}

// ============================================================
// 5. DOMAIN EVENT
// ============================================================

class DomainEvent {
    constructor(type, aggregateId, version, payload) {
        if (!Object.values(EventType).includes(type)) {
            throw new ValidationError("Unknown event type.");
        }

        this.id = crypto.randomUUID();
        this.type = type;
        this.aggregateId = aggregateId;
        this.version = version;
        this.payload = Object.freeze({ ...payload });
        this.occurredAt = new Date().toISOString();

        Object.freeze(this);
    }
}

// ============================================================
// 6. WRITE MODEL
// ============================================================

class AccountAggregate {
    constructor(id, owner, balance = 0, version = 0) {
        this.id = id;
        this.owner = owner;
        this.balance = balance;
        this.version = version;
    }

    deposit(amount) {
        validateAmount(amount);

        const event = new DomainEvent(
            EventType.MONEY_DEPOSITED,
            this.id,
            this.version + 1,
            { amount }
        );

        this.apply(event);
        return event;
    }

    withdraw(amount) {
        validateAmount(amount);

        if (amount > this.balance) {
            throw new InsufficientFundsError(
                "Insufficient account balance."
            );
        }

        const event = new DomainEvent(
            EventType.MONEY_WITHDRAWN,
            this.id,
            this.version + 1,
            { amount }
        );

        this.apply(event);
        return event;
    }

    apply(event) {
        if (event.aggregateId !== this.id) {
            throw new ValidationError("Aggregate mismatch.");
        }

        if (event.version !== this.version + 1) {
            throw new ConcurrencyError("Invalid aggregate event sequence.");
        }

        switch (event.type) {
            case EventType.MONEY_DEPOSITED:
                this.balance = roundMoney(
                    this.balance + event.payload.amount
                );
                break;

            case EventType.MONEY_WITHDRAWN:
                if (event.payload.amount > this.balance) {
                    throw new InsufficientFundsError(
                        "Historical withdrawal violates account balance."
                    );
                }

                this.balance = roundMoney(
                    this.balance - event.payload.amount
                );
                break;

            default:
                throw new ValidationError("Unsupported aggregate event.");
        }

        this.version = event.version;
    }
}

// ============================================================
// 7. EVENT STORE
// ============================================================

class EventStore {
    constructor() {
        this.streams = new Map();
        this.eventIds = new Set();
    }

    append(aggregateId, expectedVersion, events) {
        if (!Array.isArray(events) || events.length === 0) {
            throw new ValidationError("Event batch cannot be empty.");
        }

        const stream = this.streams.get(aggregateId) || [];
        const actualVersion = stream.length;

        if (actualVersion !== expectedVersion) {
            throw new ConcurrencyError(
                `Expected ${expectedVersion}, received ${actualVersion}.`
            );
        }

        let nextVersion = actualVersion;

        // Validate the complete batch before modifying the stream.
        for (const event of events) {
            nextVersion++;

            if (
                event.aggregateId !== aggregateId ||
                event.version !== nextVersion ||
                this.eventIds.has(event.id)
            ) {
                throw new ValidationError("Invalid or duplicate event.");
            }
        }

        stream.push(...events);
        this.streams.set(aggregateId, stream);

        for (const event of events) {
            this.eventIds.add(event.id);
        }
    }

    read(aggregateId) {
        return [...(this.streams.get(aggregateId) || [])];
    }

    readAll() {
        return [...this.streams.values()]
            .flat()
            .sort((a, b) =>
                a.aggregateId.localeCompare(b.aggregateId) ||
                a.version - b.version
            );
    }

    version(aggregateId) {
        return (this.streams.get(aggregateId) || []).length;
    }
}

// ============================================================
// 8. COMMAND IDEMPOTENCY
// ============================================================

class IdempotencyRegistry {
    constructor() {
        this.results = new Map();
    }

    get(commandId) {
        return this.results.get(commandId);
    }

    has(commandId) {
        return this.results.has(commandId);
    }

    save(commandId, result) {
        this.results.set(commandId, result);
    }
}

// ============================================================
// 9. ASYNCHRONOUS MUTUAL EXCLUSION
// ============================================================

class KeyedMutex {
    constructor() {
        this.queues = new Map();
    }

    async run(key, operation) {
        const previous = this.queues.get(key) || Promise.resolve();

        let release;

        const current = new Promise(resolve => {
            release = resolve;
        });

        this.queues.set(key, current);

        await previous;

        try {
            return await operation();
        } finally {
            release();

            if (this.queues.get(key) === current) {
                this.queues.delete(key);
            }
        }
    }
}

// ============================================================
// 10. COMMAND SERVICE
// ============================================================

class CommandService {
    constructor(eventStore, registry, eventBus) {
        this.eventStore = eventStore;
        this.registry = registry;
        this.eventBus = eventBus;

        this.aggregates = new Map();
        this.mutex = new KeyedMutex();
    }

    async createAccount(accountId, owner, commandId = crypto.randomUUID()) {
        validateIdentifier(accountId, "account ID");
        validateIdentifier(owner, "owner");

        return this.mutex.run(accountId, async () => {
            if (this.registry.has(commandId)) {
                return this.registry.get(commandId);
            }

            if (this.aggregates.has(accountId)) {
                throw new ValidationError("Account already exists.");
            }

            const event = new DomainEvent(
                EventType.ACCOUNT_CREATED,
                accountId,
                1,
                { owner }
            );

            this.eventStore.append(accountId, 0, [event]);

            this.aggregates.set(
                accountId,
                new AccountAggregate(accountId, owner, 0, 1)
            );

            this.registry.save(commandId, [event]);

            await this.eventBus.publish(event);

            return [event];
        });
    }

    async execute(command) {
        return this.mutex.run(command.accountId, async () => {
            if (this.registry.has(command.id)) {
                return this.registry.get(command.id);
            }

            const aggregate = this.aggregates.get(command.accountId);

            if (!aggregate) {
                throw new NotFoundError("Account does not exist.");
            }

            const currentVersion = this.eventStore.version(
                command.accountId
            );

            if (aggregate.version !== currentVersion) {
                throw new ConcurrencyError("Write model version mismatch.");
            }

            if (
                command.expectedVersion !== null &&
                command.expectedVersion !== currentVersion
            ) {
                throw new ConcurrencyError("Stale command version.");
            }

            let event;

            switch (command.type) {
                case CommandType.DEPOSIT:
                    event = aggregate.deposit(command.payload.amount);
                    break;

                case CommandType.WITHDRAW:
                    event = aggregate.withdraw(command.payload.amount);
                    break;

                default:
                    throw new ValidationError("Unsupported command.");
            }

            try {
                this.eventStore.append(
                    command.accountId,
                    currentVersion,
                    [event]
                );
            } catch (error) {
                // Restore the aggregate if persistence fails.
                aggregate.version--;
                if (event.type === EventType.MONEY_DEPOSITED) {
                    aggregate.balance = roundMoney(
                        aggregate.balance - event.payload.amount
                    );
                } else {
                    aggregate.balance = roundMoney(
                        aggregate.balance + event.payload.amount
                    );
                }
                throw error;
            }

            const result = [event];

            this.registry.save(command.id, result);

            await this.eventBus.publish(event);

            return result;
        });
    }

    async deposit(accountId, amount, expectedVersion = null) {
        return this.execute(
            new Command(
                CommandType.DEPOSIT,
                accountId,
                { amount },
                expectedVersion
            )
        );
    }

    async withdraw(accountId, amount, expectedVersion = null) {
        return this.execute(
            new Command(
                CommandType.WITHDRAW,
                accountId,
                { amount },
                expectedVersion
            )
        );
    }
}

// ============================================================
// 11. EVENT BUS
// ============================================================

class AsyncEventBus extends EventEmitter {
    async publish(event) {
        const listeners = this.listeners(event.type);

        const outcomes = await Promise.allSettled(
            listeners.map(listener =>
                Promise.resolve().then(() => listener(event))
            )
        );

        const failures = outcomes.filter(
            outcome => outcome.status === "rejected"
        );

        if (failures.length > 0) {
            throw new ProjectionError(
                `${failures.length} event subscriber(s) failed.`
            );
        }
    }
}

// ============================================================
// 12. READ MODEL
// ============================================================

class AccountReadModel {
    constructor() {
        this.accounts = new Map();
        this.processedEvents = new Set();
        this.checkpoints = new Map();
    }

    project(event) {
        if (this.processedEvents.has(event.id)) {
            return;
        }

        const current = this.accounts.get(event.aggregateId);

        if (event.type === EventType.ACCOUNT_CREATED) {
            if (current) {
                throw new ProjectionError("Duplicate account creation.");
            }

            this.accounts.set(event.aggregateId, {
                accountId: event.aggregateId,
                owner: event.payload.owner,
                balance: 0,
                version: event.version,
                transactionCount: 0,
                lastUpdated: event.occurredAt
            });
        } else {
            if (!current) {
                throw new ProjectionError("Account projection missing.");
            }

            if (event.version !== current.version + 1) {
                throw new ProjectionError("Projection version gap.");
            }

            if (event.type === EventType.MONEY_DEPOSITED) {
                current.balance = roundMoney(
                    current.balance + event.payload.amount
                );
            } else if (event.type === EventType.MONEY_WITHDRAWN) {
                current.balance = roundMoney(
                    current.balance - event.payload.amount
                );
            }

            current.version = event.version;
            current.transactionCount++;
            current.lastUpdated = event.occurredAt;
        }

        this.processedEvents.add(event.id);
        this.checkpoints.set(
            event.aggregateId,
            event.version
        );
    }

    getAccount(accountId) {
        const account = this.accounts.get(accountId);

        if (!account) {
            throw new NotFoundError("Read model account not found.");
        }

        return Object.freeze({ ...account });
    }

    getReport() {
        const records = [...this.accounts.values()].map(
            account => ({ ...account })
        );

        return {
            accountCount: records.length,
            totalBalance: roundMoney(
                records.reduce((sum, account) => sum + account.balance, 0)
            ),
            accounts: records
        };
    }
}

// ============================================================
// 13. QUERY SERVICE
// ============================================================

class QueryService {
    constructor(readModel) {
        this.readModel = readModel;
    }

    accountDetails(accountId) {
        return this.readModel.getAccount(accountId);
    }

    financialReport() {
        return this.readModel.getReport();
    }
}

// ============================================================
// 14. PROJECTION REBUILD
// ============================================================

async function rebuildProjection(eventStore, readModel) {
    readModel.accounts.clear();
    readModel.processedEvents.clear();
    readModel.checkpoints.clear();

    for (const event of eventStore.readAll()) {
        readModel.project(event);
    }
}

// ============================================================
// 15. EVENT FILE STORAGE
// ============================================================

async function saveEvents(eventStore, filePath) {
    const lines = eventStore.readAll().map(event =>
        JSON.stringify(event)
    );

    await fs.writeFile(
        filePath,
        lines.join("\n") + (lines.length ? "\n" : ""),
        { encoding: "utf8", mode: 0o600 }
    );
}

async function loadEvents(filePath) {
    const content = await fs.readFile(filePath, "utf8");

    if (!content.trim()) {
        return [];
    }

    return content
        .split(/\r?\n/)
        .filter(Boolean)
        .map((line, index) => {
            try {
                return JSON.parse(line);
            } catch {
                throw new ValidationError(
                    `Invalid event at line ${index + 1}.`
                );
            }
        });
}

// ============================================================
// 16. APPLICATION COMPOSITION
// ============================================================

class BankingApplication {
    constructor() {
        this.eventStore = new EventStore();
        this.registry = new IdempotencyRegistry();
        this.eventBus = new AsyncEventBus();
        this.readModel = new AccountReadModel();

        this.commandService = new CommandService(
            this.eventStore,
            this.registry,
            this.eventBus
        );

        this.queryService = new QueryService(this.readModel);

        this.eventBus.on(
            EventType.ACCOUNT_CREATED,
            event => this.readModel.project(event)
        );

        this.eventBus.on(
            EventType.MONEY_DEPOSITED,
            event => this.readModel.project(event)
        );

        this.eventBus.on(
            EventType.MONEY_WITHDRAWN,
            event => this.readModel.project(event)
        );
    }
}

// ============================================================
// 17. EXECUTABLE TESTS
// ============================================================

async function main() {
    const app = new BankingApplication();

    await app.commandService.createAccount("ACC-2001", "Ananya");
    await app.commandService.createAccount("ACC-2002", "Rahul");

    await app.commandService.deposit("ACC-2001", 10000, 1);
    await app.commandService.deposit("ACC-2001", 2500, 2);
    await app.commandService.withdraw("ACC-2001", 1500, 3);

    await app.commandService.deposit("ACC-2002", 5000, 1);

    console.log("ACCOUNT QUERY");
    console.log(app.queryService.accountDetails("ACC-2001"));

    console.log("\nFINANCIAL REPORT");
    console.log(app.queryService.financialReport());

    // Duplicate event delivery is harmless.
    const event = app.eventStore.read("ACC-2001")[1];
    const before = app.queryService.accountDetails("ACC-2001").balance;

    app.readModel.project(event);

    console.assert(
        app.queryService.accountDetails("ACC-2001").balance === before,
        "Duplicate event changed read model."
    );

    // Insufficient balance.
    try {
        await app.commandService.withdraw("ACC-2001", 999999);
        throw new Error("Insufficient funds test failed.");
    } catch (error) {
        if (!(error instanceof InsufficientFundsError)) {
            throw error;
        }
        console.log("\nInsufficient funds rejected.");
    }

    // Stale version.
    try {
        await app.commandService.deposit("ACC-2001", 100, 1);
        throw new Error("Concurrency test failed.");
    } catch (error) {
        if (!(error instanceof ConcurrencyError)) {
            throw error;
        }
        console.log("Stale command rejected.");
    }

    // Invalid amount.
    try {
        await app.commandService.deposit("ACC-2001", -10);
        throw new Error("Validation test failed.");
    } catch (error) {
        if (!(error instanceof ValidationError)) {
            throw error;
        }
        console.log("Invalid amount rejected.");
    }

    // Rebuild must preserve the read-side results.
    const original = app.queryService.financialReport().totalBalance;

    await rebuildProjection(app.eventStore, app.readModel);

    const rebuilt = app.queryService.financialReport().totalBalance;

    console.assert(original === rebuilt, "Projection rebuild mismatch.");

    // Persistent demonstration.
    await saveEvents(app.eventStore, "cqrs-events.jsonl");

    const recovered = await loadEvents("cqrs-events.jsonl");

    console.log("\nEvents persisted:", recovered.length);
    console.log("Projection rebuild verified.");
    console.log("All CQRS tests passed.");
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
