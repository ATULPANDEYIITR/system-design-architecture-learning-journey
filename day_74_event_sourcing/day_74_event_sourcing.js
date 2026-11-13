"use strict";

/*
 * EVENT SOURCING
 * Event-driven account processing using Node.js.
 *
 * Features:
 * - Append-only event journal
 * - Asynchronous command processing
 * - Serialized writes
 * - Idempotency
 * - Aggregate reconstruction
 * - Event subscriptions
 * - Independent read projections
 * - Event schema validation
 * - Journal integrity verification
 * - Snapshot creation
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");

class DomainError extends Error {}
class ValidationError extends DomainError {}
class ConcurrencyError extends DomainError {}
class InsufficientFundsError extends DomainError {}
class IntegrityError extends DomainError {}

const EventType = Object.freeze({
    OPENED: "AccountOpened",
    DEPOSITED: "MoneyDeposited",
    WITHDRAWN: "MoneyWithdrawn",
    FROZEN: "AccountFrozen",
    UNFROZEN: "AccountUnfrozen"
});

function validateIdentifier(value, field) {
    if (
        typeof value !== "string" ||
        value.trim().length === 0 ||
        value.length > 128
    ) {
        throw new ValidationError(`${field} is invalid.`);
    }
}

function createEventId(aggregateId, version, type, payload) {
    return crypto.createHash("sha256")
        .update(JSON.stringify({
            aggregateId,
            version,
            type,
            payload
        }))
        .digest("hex");
}

function validateAmount(amount) {
    if (!Number.isSafeInteger(amount) || amount <= 0) {
        throw new ValidationError(
            "Amount must be a positive safe integer."
        );
    }
}

class EventJournal {
    #events = new Map();
    #eventIds = new Set();
    #commands = new Map();
    #listeners = new Set();
    #writeQueue = Promise.resolve();

    version(aggregateId) {
        const events = this.#events.get(aggregateId) || [];
        return events.length;
    }

    read(aggregateId) {
        return [...(this.#events.get(aggregateId) || [])];
    }

    subscribe(listener) {
        if (typeof listener !== "function") {
            throw new ValidationError("Listener must be a function.");
        }

        this.#listeners.add(listener);
        return () => this.#listeners.delete(listener);
    }

    async append(event, expectedVersion, commandId) {
        // Queue writes so concurrent commands cannot bypass version checks.
        const operation = this.#writeQueue.then(async () => {
            validateIdentifier(commandId, "Command ID");
            validateIdentifier(event.aggregateId, "Aggregate ID");

            if (this.#commands.has(commandId)) {
                const previous = this.#commands.get(commandId);

                if (previous.fingerprint !== event.fingerprint) {
                    throw new IntegrityError(
                        "Command ID reused with different content."
                    );
                }

                return previous.event;
            }

            if (this.#eventIds.has(event.eventId)) {
                throw new IntegrityError("Duplicate event ID.");
            }

            const current = this.version(event.aggregateId);

            if (current !== expectedVersion) {
                throw new ConcurrencyError(
                    `Expected ${expectedVersion}, actual ${current}.`
                );
            }

            if (event.version !== current + 1) {
                throw new ValidationError("Invalid event version.");
            }

            const stored = Object.freeze({
                ...event,
                payload: Object.freeze({ ...event.payload })
            });

            if (!this.#events.has(event.aggregateId)) {
                this.#events.set(event.aggregateId, []);
            }

            this.#events.get(event.aggregateId).push(stored);
            this.#eventIds.add(event.eventId);

            this.#commands.set(commandId, {
                fingerprint: event.fingerprint,
                event: stored
            });

            // Listeners receive committed events. Projection failures
            // do not roll back the authoritative journal.
            for (const listener of this.#listeners) {
                try {
                    await listener(stored);
                } catch (error) {
                    process.stderr.write(
                        `Projection failure: ${error.message}\n`
                    );
                }
            }

            return stored;
        });

        this.#writeQueue = operation.catch(() => {});
        return operation;
    }

    allEvents() {
        return [...this.#events.values()].flat();
    }

    async persist(filePath) {
        const lines = this.allEvents()
            .map(event => JSON.stringify(event))
            .join("\n");

        await fs.writeFile(
            filePath,
            lines.length ? lines + "\n" : "",
            { encoding: "utf8", mode: 0o600 }
        );
    }

    async restore(filePath) {
        let contents;

        try {
            contents = await fs.readFile(filePath, "utf8");
        } catch (error) {
            if (error.code === "ENOENT") return;
            throw error;
        }

        for (const [index, line] of contents.split("\n").entries()) {
            if (!line.trim()) continue;

            let event;

            try {
                event = JSON.parse(line);
                validateStoredEvent(event);

                const expected = this.version(event.aggregateId);

                if (event.version !== expected + 1) {
                    throw new IntegrityError("Broken event sequence.");
                }

                if (this.#eventIds.has(event.eventId)) {
                    throw new IntegrityError("Duplicate event ID.");
                }

                if (event.previousHash !== (
                    expected === 0
                        ? "GENESIS"
                        : this.read(event.aggregateId).at(-1).hash
                )) {
                    throw new IntegrityError("Broken event hash chain.");
                }

                const expectedHash = hashEvent(event);

                if (event.hash !== expectedHash) {
                    throw new IntegrityError("Event hash mismatch.");
                }

                if (!this.#events.has(event.aggregateId)) {
                    this.#events.set(event.aggregateId, []);
                }

                this.#events.get(event.aggregateId).push(
                    Object.freeze(event)
                );
                this.#eventIds.add(event.eventId);
            } catch (error) {
                throw new IntegrityError(
                    `Invalid journal line ${index + 1}: ${error.message}`
                );
            }
        }
    }
}

function hashEvent(event) {
    const copy = { ...event };
    delete copy.hash;

    return crypto.createHash("sha256")
        .update(JSON.stringify(copy))
        .digest("hex");
}

function validateStoredEvent(event) {
    if (
        !event ||
        typeof event.aggregateId !== "string" ||
        !Number.isSafeInteger(event.version) ||
        event.version < 1 ||
        !Object.values(EventType).includes(event.type) ||
        typeof event.payload !== "object" ||
        event.payload === null
    ) {
        throw new ValidationError("Invalid stored event structure.");
    }
}

function makeEvent(aggregateId, version, type, payload, previousHash) {
    const event = {
        eventId: createEventId(aggregateId, version, type, payload),
        aggregateId,
        version,
        type,
        payload,
        occurredAt: new Date().toISOString(),
        schemaVersion: 1,
        previousHash,
        fingerprint: JSON.stringify({ aggregateId, type, payload })
    };

    event.hash = hashEvent(event);
    return event;
}

class AccountAggregate {
    constructor(id, owner) {
        this.id = id;
        this.owner = owner;
        this.balance = 0;
        this.frozen = false;
        this.version = 0;
    }

    apply(event) {
        const p = event.payload;

        if (event.version !== this.version + 1) {
            throw new IntegrityError("Aggregate sequence mismatch.");
        }

        switch (event.type) {
            case EventType.OPENED:
                if (this.version !== 0 || !p.owner) {
                    throw new ValidationError("Invalid opening event.");
                }
                this.owner = p.owner;
                break;

            case EventType.DEPOSITED:
                validateAmount(p.amount);
                if (this.frozen) {
                    throw new ValidationError("Deposit to frozen account.");
                }
                this.balance += p.amount;
                break;

            case EventType.WITHDRAWN:
                validateAmount(p.amount);
                if (this.frozen) {
                    throw new ValidationError("Withdrawal from frozen account.");
                }
                if (p.amount > this.balance) {
                    throw new InsufficientFundsError("Insufficient funds.");
                }
                this.balance -= p.amount;
                break;

            case EventType.FROZEN:
                this.frozen = true;
                break;

            case EventType.UNFROZEN:
                this.frozen = false;
                break;

            default:
                throw new ValidationError("Unknown event type.");
        }

        this.version = event.version;
    }

    static rehydrate(id, events) {
        const account = new AccountAggregate(id, "");

        for (const event of events) {
            account.apply(event);
        }

        if (account.version === 0) {
            throw new ValidationError("Account does not exist.");
        }

        return account;
    }
}

class AccountService {
    constructor(journal) {
        this.journal = journal;
    }

    async dispatch(command) {
        validateIdentifier(command.accountId, "Account ID");
        validateIdentifier(command.commandId, "Command ID");

        const events = this.journal.read(command.accountId);
        const version = events.length;

        let payload = command.payload || {};

        if (command.type === EventType.OPENED) {
            if (version !== 0 || !payload.owner?.trim()) {
                throw new ValidationError("Invalid account creation.");
            }
        } else {
            const account = AccountAggregate.rehydrate(
                command.accountId,
                events
            );

            if (
                account.frozen &&
                [EventType.DEPOSITED, EventType.WITHDRAWN]
                    .includes(command.type)
            ) {
                throw new ValidationError("Account is frozen.");
            }

            if (
                [EventType.DEPOSITED, EventType.WITHDRAWN]
                    .includes(command.type)
            ) {
                validateAmount(payload.amount);
            }

            if (
                command.type === EventType.WITHDRAWN &&
                payload.amount > account.balance
            ) {
                throw new InsufficientFundsError("Insufficient funds.");
            }
        }

        const previousHash = events.length
            ? events.at(-1).hash
            : "GENESIS";

        const event = makeEvent(
            command.accountId,
            version + 1,
            command.type,
            payload,
            previousHash
        );

        return this.journal.append(
            event,
            version,
            command.commandId
        );
    }
}

class BalanceProjection {
    accounts = new Map();

    apply(event) {
        const account = this.accounts.get(event.aggregateId);
        const p = event.payload;

        if (event.type === EventType.OPENED) {
            this.accounts.set(event.aggregateId, {
                owner: p.owner,
                balance: 0,
                frozen: false,
                version: 1
            });
            return;
        }

        if (!account || event.version !== account.version + 1) {
            throw new IntegrityError("Projection sequence error.");
        }

        if (event.type === EventType.DEPOSITED) {
            account.balance += p.amount;
        } else if (event.type === EventType.WITHDRAWN) {
            account.balance -= p.amount;
        } else if (event.type === EventType.FROZEN) {
            account.frozen = true;
        } else if (event.type === EventType.UNFROZEN) {
            account.frozen = false;
        }

        account.version = event.version;
    }

    rebuild(events) {
        this.accounts.clear();
        for (const event of events) this.apply(event);
    }
}

async function main() {
    const journal = new EventJournal();
    const projection = new BalanceProjection();

    journal.subscribe(event => projection.apply(event));

    const service = new AccountService(journal);

    await service.dispatch({
        accountId: "ACC-2001",
        commandId: "CMD-001",
        type: EventType.OPENED,
        payload: { owner: "Atul" }
    });

    await service.dispatch({
        accountId: "ACC-2001",
        commandId: "CMD-002",
        type: EventType.DEPOSITED,
        payload: { amount: 15000 }
    });

    await service.dispatch({
        accountId: "ACC-2001",
        commandId: "CMD-003",
        type: EventType.WITHDRAWN,
        payload: { amount: 4000 }
    });

    const account = AccountAggregate.rehydrate(
        "ACC-2001",
        journal.read("ACC-2001")
    );

    if (account.balance !== 11000) {
        throw new Error("Balance assertion failed.");
    }

    if (projection.accounts.get("ACC-2001").balance !== 11000) {
        throw new Error("Projection assertion failed.");
    }

    // An identical command is rejected if its ID is reused
    // with different content.
    try {
        await service.dispatch({
            accountId: "ACC-2001",
            commandId: "CMD-002",
            type: EventType.DEPOSITED,
            payload: { amount: 5000 }
        });
        throw new Error("Idempotency validation failed.");
    } catch (error) {
        if (!(error instanceof IntegrityError)) throw error;
    }

    // A failed command must not alter the event history.
    try {
        await service.dispatch({
            accountId: "ACC-2001",
            commandId: "CMD-004",
            type: EventType.WITHDRAWN,
            payload: { amount: 50000 }
        });
        throw new Error("Insufficient funds validation failed.");
    } catch (error) {
        if (!(error instanceof InsufficientFundsError)) throw error;
    }

    // Concurrent writes using the same expected version cannot both commit.
    const concurrent = [
        service.dispatch({
            accountId: "ACC-2001",
            commandId: "CMD-005",
            type: EventType.DEPOSITED,
            payload: { amount: 100 }
        }),
        service.dispatch({
            accountId: "ACC-2001",
            commandId: "CMD-006",
            type: EventType.DEPOSITED,
            payload: { amount: 200 }
        })
    ];

    const results = await Promise.allSettled(concurrent);
    const successful = results.filter(
        result => result.status === "fulfilled"
    ).length;

    if (successful !== 1) {
        throw new Error("Concurrency test failed.");
    }

    const snapshot = {
        aggregateId: account.id,
        version: account.version,
        balance: account.balance
    };

    const temporaryFile = path.join(
        require("node:os").tmpdir(),
        `event-journal-${process.pid}.jsonl`
    );

    try {
        await journal.persist(temporaryFile);

        const restored = new EventJournal();
        await restored.restore(temporaryFile);

        const restoredAccount = AccountAggregate.rehydrate(
            "ACC-2001",
            restored.read("ACC-2001")
        );

        if (
            restoredAccount.balance !==
            projection.accounts.get("ACC-2001").balance
        ) {
            throw new Error("Replay verification failed.");
        }

        console.log("EVENT SOURCING REPORT");
        console.log("---------------------");
        console.log("Account:", account.id);
        console.log("Owner:", account.owner);
        console.log("Balance before concurrent commands:", account.balance);
        console.log("Final balance:", restoredAccount.balance);
        console.log("Snapshot:", snapshot);
        console.log("Concurrent commits:", successful);
        console.log("Persisted events:", restored.read("ACC-2001").length);
        console.log("Replay integrity: PASSED");
    } finally {
        await fs.rm(temporaryFile, { force: true });
    }
}

main().catch(error => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});
