"use strict";

/*
 * Transaction Isolation Levels
 *
 * This Node.js-compatible program models transaction visibility and uses
 * event-driven execution to make the distinction between isolation levels
 * concrete.
 *
 * The implementation is intentionally a teaching simulator. Real databases
 * use MVCC, locks, timestamp ordering, serialization validation, predicate
 * locks, or combinations of these mechanisms.
 */

const IsolationLevel = Object.freeze({
  READ_UNCOMMITTED: "READ UNCOMMITTED",
  READ_COMMITTED: "READ COMMITTED",
  REPEATABLE_READ: "REPEATABLE READ",
  SERIALIZABLE: "SERIALIZABLE",
});

class TransactionError extends Error {}

class Account {
  constructor(id, owner, balance) {
    if (!Number.isInteger(id) || id <= 0) {
      throw new TypeError("Account ID must be a positive integer.");
    }
    if (!Number.isFinite(balance) || balance < 0) {
      throw new TypeError("Balance must be a non-negative number.");
    }

    this.id = id;
    this.owner = owner;
    this.balance = balance;
  }

  clone() {
    return new Account(this.id, this.owner, this.balance);
  }
}

class Transaction {
  constructor(id, isolation, snapshotVersion) {
    this.id = id;
    this.isolation = isolation;
    this.snapshotVersion = snapshotVersion;
    this.state = "ACTIVE";
    this.writes = new Map();
    this.readCache = new Map();
    this.readPredicates = [];
  }
}

class TransactionDatabase {
  constructor() {
    this.commitVersion = 0;
    this.nextTransactionId = 1;
    this.accounts = new Map();
    this.uncommitted = new Map();
    this.serialQueue = Promise.resolve();
  }

  seed(accounts) {
    this.commitVersion += 1;

    for (const account of accounts) {
      if (this.accounts.has(account.id)) {
        throw new TransactionError(
          `Duplicate account ${account.id} during initialization.`
        );
      }

      this.accounts.set(account.id, [
        {
          version: this.commitVersion,
          account: account.clone(),
        },
      ]);
    }
  }

  begin(isolation) {
    if (!Object.values(IsolationLevel).includes(isolation)) {
      throw new TransactionError(`Unsupported isolation level: ${isolation}`);
    }

    const transaction = new Transaction(
      this.nextTransactionId++,
      isolation,
      this.commitVersion
    );

    this.uncommitted.set(transaction.id, new Map());

    return transaction;
  }

  assertActive(transaction) {
    if (transaction.state !== "ACTIVE") {
      throw new TransactionError(
        `Transaction ${transaction.id} is ${transaction.state.toLowerCase()}.`
      );
    }
  }

  latestCommitted(id) {
    const versions = this.accounts.get(id);
    if (!versions || versions.length === 0) {
      return null;
    }

    return versions[versions.length - 1].account.clone();
  }

  snapshotValue(id, version) {
    const versions = this.accounts.get(id);

    if (!versions) {
      return null;
    }

    let visible = null;

    for (const item of versions) {
      if (item.version <= version) {
        visible = item.account;
      } else {
        break;
      }
    }

    return visible ? visible.clone() : null;
  }

  uncommittedValue(reader, id) {
    for (const [transactionId, writes] of this.uncommitted.entries()) {
      if (transactionId === reader.id) {
        continue;
      }

      if (writes.has(id)) {
        return writes.get(id).clone();
      }
    }

    return null;
  }

  read(transaction, id) {
    this.assertActive(transaction);

    const ownWrites = this.uncommitted.get(transaction.id);

    if (ownWrites.has(id)) {
      return ownWrites.get(id).clone();
    }

    if (transaction.isolation === IsolationLevel.READ_UNCOMMITTED) {
      const dirty = this.uncommittedValue(transaction, id);
      return dirty || this.latestCommitted(id);
    }

    if (transaction.isolation === IsolationLevel.READ_COMMITTED) {
      return this.latestCommitted(id);
    }

    if (transaction.isolation === IsolationLevel.REPEATABLE_READ) {
      if (!transaction.readCache.has(id)) {
        const value = this.snapshotValue(id, transaction.snapshotVersion);

        if (value) {
          transaction.readCache.set(id, value.clone());
        }

        return value;
      }

      return transaction.readCache.get(id).clone();
    }

    if (transaction.isolation === IsolationLevel.SERIALIZABLE) {
      return this.latestCommitted(id);
    }

    throw new TransactionError("Unknown isolation level.");
  }

  write(transaction, id, balance) {
    this.assertActive(transaction);

    if (!Number.isFinite(balance) || balance < 0) {
      throw new RangeError("Balance must be a non-negative finite number.");
    }

    const existing = this.read(transaction, id);

    if (!existing) {
      throw new TransactionError(`Account ${id} does not exist.`);
    }

    const updated = existing.clone();
    updated.balance = balance;

    this.uncommitted.get(transaction.id).set(id, updated);
    transaction.writes.set(id, updated.clone());
  }

  rangeQuery(transaction, minimum, maximum) {
    this.assertActive(transaction);

    if (minimum > maximum) {
      throw new RangeError("Minimum cannot exceed maximum.");
    }

    transaction.readPredicates.push({ minimum, maximum });

    const accounts =
      transaction.isolation === IsolationLevel.REPEATABLE_READ
        ? this.accountsAtSnapshot(transaction.snapshotVersion)
        : this.currentAccounts();

    return accounts
      .filter(
        (account) =>
          account.balance >= minimum && account.balance <= maximum
      )
      .sort((a, b) => a.id - b.id);
  }

  currentAccounts() {
    return [...this.accounts.values()]
      .map((versions) => versions[versions.length - 1].account.clone())
      .filter(Boolean);
  }

  accountsAtSnapshot(version) {
    const result = [];

    for (const id of this.accounts.keys()) {
      const account = this.snapshotValue(id, version);

      if (account) {
        result.push(account);
      }
    }

    return result;
  }

  insert(transaction, account) {
    this.assertActive(transaction);

    if (!(account instanceof Account)) {
      throw new TypeError("insert requires an Account instance.");
    }

    if (this.accounts.has(account.id)) {
      throw new TransactionError(`Account ${account.id} already exists.`);
    }

    const privateWrites = this.uncommitted.get(transaction.id);

    if (privateWrites.has(account.id)) {
      throw new TransactionError(
        `Transaction already owns account ${account.id}.`
      );
    }

    privateWrites.set(account.id, account.clone());
    transaction.writes.set(account.id, account.clone());
  }

  commit(transaction) {
    this.assertActive(transaction);

    this.commitVersion += 1;

    const privateWrites = this.uncommitted.get(transaction.id);

    for (const [id, account] of privateWrites.entries()) {
      if (!this.accounts.has(id)) {
        this.accounts.set(id, []);
      }

      this.accounts.get(id).push({
        version: this.commitVersion,
        account: account.clone(),
      });
    }

    this.uncommitted.delete(transaction.id);
    transaction.state = "COMMITTED";
  }

  rollback(transaction) {
    this.assertActive(transaction);

    this.uncommitted.delete(transaction.id);
    transaction.state = "ROLLED BACK";
  }
}

/*
 * JavaScript-specific concurrency demonstration.
 *
 * JavaScript runs callbacks on an event loop, but asynchronous operations can
 * interleave transaction steps. A Promise-based scheduler makes the ordering
 * visible without pretending that JavaScript itself provides database
 * isolation.
 */
class StepScheduler {
  constructor() {
    this.queue = [];
  }

  add(label, delay, action) {
    this.queue.push({ label, delay, action });
  }

  async run() {
    for (const step of this.queue) {
      await new Promise((resolve) => setTimeout(resolve, step.delay));

      console.log(`\n[event] ${step.label}`);
      await step.action();
    }
  }
}

function printAccount(account) {
  if (!account) {
    return "missing";
  }

  return `${account.owner}: ${account.balance}`;
}

async function demonstrateDirtyRead() {
  console.log("\n=== Dirty Read / READ UNCOMMITTED ===");

  const db = new TransactionDatabase();
  db.seed([new Account(1, "Asha", 1000)]);

  const writer = db.begin(IsolationLevel.READ_COMMITTED);
  const reader = db.begin(IsolationLevel.READ_UNCOMMITTED);

  const scheduler = new StepScheduler();

  scheduler.add("T1 writes but does not commit", 10, async () => {
    db.write(writer, 1, 250);
  });

  scheduler.add("T2 performs a dirty read", 10, async () => {
    console.log("T2 sees:", printAccount(db.read(reader, 1)));
  });

  scheduler.add("T1 rolls back", 10, async () => {
    db.rollback(writer);
  });

  scheduler.add("T2 reads committed state", 10, async () => {
    console.log("T2 now sees:", printAccount(db.read(reader, 1)));
  });

  await scheduler.run();
  db.rollback(reader);
}

async function demonstrateReadCommitted() {
  console.log("\n=== READ COMMITTED / Non-Repeatable Read ===");

  const db = new TransactionDatabase();
  db.seed([new Account(1, "Asha", 1000)]);

  const reader = db.begin(IsolationLevel.READ_COMMITTED);
  const writer = db.begin(IsolationLevel.READ_COMMITTED);

  console.log("First read:", printAccount(db.read(reader, 1)));

  db.write(writer, 1, 700);
  db.commit(writer);

  console.log("Second read:", printAccount(db.read(reader, 1)));

  db.rollback(reader);
}

async function demonstrateRepeatableRead() {
  console.log("\n=== REPEATABLE READ / Stable Row Observation ===");

  const db = new TransactionDatabase();
  db.seed([new Account(1, "Asha", 1000)]);

  const reader = db.begin(IsolationLevel.REPEATABLE_READ);
  const writer = db.begin(IsolationLevel.READ_COMMITTED);

  console.log("First read:", printAccount(db.read(reader, 1)));

  db.write(writer, 1, 700);
  db.commit(writer);

  console.log("Second read:", printAccount(db.read(reader, 1)));
  console.log(
    "The second read uses the transaction's cached snapshot value."
  );

  db.commit(reader);
}

async function demonstratePhantomRead() {
  console.log("\n=== Phantom Rows ===");

  const db = new TransactionDatabase();

  db.seed([
    new Account(1, "Asha", 1000),
    new Account(2, "Ravi", 4000),
    new Account(3, "Mina", 8000),
  ]);

  const reader = db.begin(IsolationLevel.REPEATABLE_READ);
  const inserter = db.begin(IsolationLevel.READ_COMMITTED);

  const first = db.rangeQuery(reader, 1000, 5000);

  db.insert(inserter, new Account(4, "Noor", 3000));
  db.commit(inserter);

  const second = db.rangeQuery(reader, 1000, 5000);

  console.log("REPEATABLE READ first range:", first.map((a) => a.id));
  console.log("REPEATABLE READ second range:", second.map((a) => a.id));
  console.log(
    "The transaction snapshot keeps old row versions, but this simulator "
      + "does not claim predicate-level serializability."
  );

  db.commit(reader);
}

async function demonstrateSerializable() {
  console.log("\n=== SERIALIZABLE / Serialized Critical Section ===");

  const db = new TransactionDatabase();

  db.seed([
    new Account(1, "Asha", 1000),
    new Account(2, "Ravi", 4000),
  ]);

  /*
   * The simulator represents SERIALIZABLE with a process-level async mutex.
   * A production database can instead use row locks, key-range locks,
   * predicate locks, SSI, or validation plus transaction retries.
   */
  let releaseFirst;

  const firstTransactionStarted = new Promise((resolve) => {
    releaseFirst = resolve;
  });

  let releaseSecond;
  const secondTransactionStarted = new Promise((resolve) => {
    releaseSecond = resolve;
  });

  let firstHeld = true;

  const first = db.begin(IsolationLevel.SERIALIZABLE);
  releaseFirst();

  const secondPromise = (async () => {
    await firstTransactionStarted;

    await new Promise((resolve) => setTimeout(resolve, 20));

    releaseSecond();

    while (firstHeld) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }

    return db.begin(IsolationLevel.SERIALIZABLE);
  })();

  console.log(
    "T1 acquired the conceptual serial execution slot."
  );

  const firstRange = db.rangeQuery(first, 1000, 5000);
  console.log("T1 sees:", firstRange.map((a) => a.id));

  db.commit(first);
  firstHeld = false;

  await secondPromise;

  console.log(
    "T2 can proceed only after T1 releases the serial execution slot."
  );
}

function compareIsolationLevels() {
  console.log("\n=== Isolation Matrix ===");

  const rows = [
    {
      level: IsolationLevel.READ_UNCOMMITTED,
      dirty: "Possible",
      nonRepeatable: "Possible",
      phantom: "Possible",
      tradeoff: "Maximum visibility, minimum consistency",
    },
    {
      level: IsolationLevel.READ_COMMITTED,
      dirty: "Prevented",
      nonRepeatable: "Possible",
      phantom: "Possible",
      tradeoff: "Fresh committed reads with statement-level consistency",
    },
    {
      level: IsolationLevel.REPEATABLE_READ,
      dirty: "Prevented",
      nonRepeatable: "Prevented",
      phantom: "Engine-dependent",
      tradeoff: "Stable transaction observations with reduced concurrency",
    },
    {
      level: IsolationLevel.SERIALIZABLE,
      dirty: "Prevented",
      nonRepeatable: "Prevented",
      phantom: "Prevented",
      tradeoff: "Strongest standard isolation; may block or abort",
    },
  ];

  console.table(rows);
}

function demonstrateValidation() {
  console.log("\n=== Transaction Validation ===");

  const db = new TransactionDatabase();
  db.seed([new Account(1, "Asha", 1000)]);

  const transaction = db.begin(IsolationLevel.READ_COMMITTED);

  try {
    db.write(transaction, 1, -1);
  } catch (error) {
    console.log("Invalid balance rejected:", error.message);
  }

  db.commit(transaction);

  try {
    db.read(transaction, 1);
  } catch (error) {
    console.log("Inactive transaction rejected:", error.message);
  }
}

async function main() {
  console.log("TRANSACTION ISOLATION LEVEL LAB");
  console.log("===============================");

  await demonstrateDirtyRead();
  await demonstrateReadCommitted();
  await demonstrateRepeatableRead();
  await demonstratePhantomRead();
  await demonstrateSerializable();

  compareIsolationLevels();
  demonstrateValidation();

  console.log("\n=== Engineering Implications ===");
  console.log(
    "Isolation level is a correctness/concurrency decision, not merely "
      + "a performance switch."
  );
  console.log(
    "READ COMMITTED can expose changing values across statements."
  );
  console.log(
    "REPEATABLE READ can provide stable row observations while leaving "
      + "predicate behavior dependent on the database implementation."
  );
  console.log(
    "SERIALIZABLE provides serial-equivalent transactional behavior, "
      + "usually at the cost of blocking, aborts, or retries."
  );
}

main().catch((error) => {
  console.error("Fatal transaction simulation error:", error.message);
  process.exitCode = 1;
});
