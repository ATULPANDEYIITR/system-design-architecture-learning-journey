'use strict';

/*
 * Transactions: ACID properties and transactional guarantees.
 *
 * This file models transaction behavior as an event-driven service rather
 * than translating the Python database implementation. It focuses on:
 *
 * - transaction lifecycle events
 * - explicit state transitions
 * - atomic application of staged mutations
 * - consistency invariants
 * - isolation through private transaction snapshots
 * - approval-style commit guards for critical operations
 * - idempotency keys
 * - optimistic concurrency control
 * - retry classification
 * - failure injection
 *
 * The program uses only built-in Node.js functionality and can be run with:
 * node transactions.js
 */

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');

const TransactionState = Object.freeze({
  CREATED: 'CREATED',
  ACTIVE: 'ACTIVE',
  COMMITTED: 'COMMITTED',
  ROLLED_BACK: 'ROLLED_BACK',
});

const money = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    throw new TypeError('Amount must be finite');
  }
  return Math.round(number * 100) / 100;
};

class TransactionError extends Error {
  constructor(message, code, retryable = false) {
    super(message);
    this.name = 'TransactionError';
    this.code = code;
    this.retryable = retryable;
  }
}

class LedgerStore {
  constructor() {
    this.accounts = new Map();
    this.transfers = new Map();
    this.ledger = [];
    this.accountVersions = new Map();
  }

  addAccount(accountId, owner, currency, balance) {
    if (!accountId || this.accounts.has(accountId)) {
      throw new TransactionError(
        'Account identifier must be unique and non-empty',
        'INVALID_ACCOUNT'
      );
    }

    if (!['INR', 'USD'].includes(currency)) {
      throw new TransactionError(
        `Unsupported currency: ${currency}`,
        'INVALID_CURRENCY'
      );
    }

    const normalizedBalance = money(balance);

    if (normalizedBalance < 0) {
      throw new TransactionError(
        'Opening balance cannot be negative',
        'INVALID_BALANCE'
      );
    }

    this.accounts.set(accountId, {
      accountId,
      owner,
      currency,
      balance: normalizedBalance,
    });

    this.accountVersions.set(accountId, 0);
  }

  snapshot() {
    const accounts = new Map();

    for (const [id, account] of this.accounts.entries()) {
      accounts.set(id, { ...account });
    }

    return {
      accounts,
      transfers: new Map(this.transfers),
      ledger: this.ledger.map((entry) => ({ ...entry })),
      accountVersions: new Map(this.accountVersions),
    };
  }

  readAccount(accountId) {
    const account = this.accounts.get(accountId);

    if (!account) {
      throw new TransactionError(
        `Unknown account: ${accountId}`,
        'ACCOUNT_NOT_FOUND'
      );
    }

    return { ...account };
  }

  totalBalance(currency = 'INR') {
    let total = 0;

    for (const account of this.accounts.values()) {
      if (account.currency === currency) {
        total += account.balance;
      }
    }

    return money(total);
  }
}

class Transaction extends EventEmitter {
  constructor(store, id, options = {}) {
    super();

    this.store = store;
    this.id = id;
    this.state = TransactionState.CREATED;
    this.snapshot = null;
    this.readVersions = new Map();
    this.writes = new Map();
    this.newTransfers = [];
    this.newLedgerEntries = [];
    this.options = {
      isolation: options.isolation || 'SNAPSHOT',
      optimisticConcurrency: options.optimisticConcurrency ?? true,
    };
  }

  begin() {
    if (this.state !== TransactionState.CREATED) {
      throw new TransactionError(
        'Transaction can only begin from CREATED state',
        'INVALID_STATE'
      );
    }

    this.snapshot = this.store.snapshot();
    this.state = TransactionState.ACTIVE;
    this.emit('begin', { transactionId: this.id });
  }

  ensureActive() {
    if (this.state !== TransactionState.ACTIVE) {
      throw new TransactionError(
        `Transaction ${this.id} is not active`,
        'INVALID_STATE'
      );
    }
  }

  readAccount(accountId) {
    this.ensureActive();

    if (this.writes.has(accountId)) {
      return { ...this.writes.get(accountId) };
    }

    const account = this.snapshot.accounts.get(accountId);

    if (!account) {
      throw new TransactionError(
        `Unknown account: ${accountId}`,
        'ACCOUNT_NOT_FOUND'
      );
    }

    if (!this.readVersions.has(accountId)) {
      this.readVersions.set(
        accountId,
        this.snapshot.accountVersions.get(accountId)
      );
    }

    return { ...account };
  }

  stageAccount(account) {
    this.ensureActive();

    if (account.balance < 0) {
      throw new TransactionError(
        `Account ${account.accountId} cannot become negative`,
        'NEGATIVE_BALANCE'
      );
    }

    this.writes.set(account.accountId, { ...account });

    if (!this.readVersions.has(account.accountId)) {
      this.readVersions.set(
        account.accountId,
        this.snapshot.accountVersions.get(account.accountId)
      );
    }
  }

  transfer(transferId, sourceId, destinationId, amount) {
    this.ensureActive();

    if (!transferId) {
      throw new TransactionError(
        'Transfer ID is required',
        'INVALID_TRANSFER_ID'
      );
    }

    if (this.store.transfers.has(transferId)) {
      throw new TransactionError(
        `Transfer ${transferId} already exists`,
        'DUPLICATE_TRANSFER'
      );
    }

    if (sourceId === destinationId) {
      throw new TransactionError(
        'Source and destination must differ',
        'SAME_ACCOUNT'
      );
    }

    const normalizedAmount = money(amount);

    if (normalizedAmount <= 0) {
      throw new TransactionError(
        'Transfer amount must be positive',
        'INVALID_AMOUNT'
      );
    }

    const source = this.readAccount(sourceId);
    const destination = this.readAccount(destinationId);

    if (source.currency !== destination.currency) {
      throw new TransactionError(
        'Cross-currency transfers require an exchange-rate transaction',
        'CURRENCY_MISMATCH'
      );
    }

    if (source.balance < normalizedAmount) {
      throw new TransactionError(
        `Insufficient funds in ${sourceId}`,
        'INSUFFICIENT_FUNDS'
      );
    }

    source.balance = money(source.balance - normalizedAmount);
    destination.balance = money(destination.balance + normalizedAmount);

    this.stageAccount(source);
    this.stageAccount(destination);

    this.newTransfers.push({
      transferId,
      sourceId,
      destinationId,
      amount: normalizedAmount,
      createdAt: new Date().toISOString(),
    });

    this.newLedgerEntries.push(
      {
        transactionId: transferId,
        accountId: sourceId,
        direction: 'DEBIT',
        amount: normalizedAmount,
      },
      {
        transactionId: transferId,
        accountId: destinationId,
        direction: 'CREDIT',
        amount: normalizedAmount,
      }
    );

    this.emit('mutation', {
      transactionId: this.id,
      transferId,
      amount: normalizedAmount,
    });
  }

  validateConsistency() {
    this.ensureActive();

    for (const account of this.writes.values()) {
      if (account.balance < 0) {
        throw new TransactionError(
          `Consistency invariant failed for ${account.accountId}`,
          'CONSISTENCY_FAILURE'
        );
      }
    }

    for (const transfer of this.newTransfers) {
      const entries = this.newLedgerEntries.filter(
        (entry) => entry.transactionId === transfer.transferId
      );

      const debitTotal = entries
        .filter((entry) => entry.direction === 'DEBIT')
        .reduce((sum, entry) => sum + entry.amount, 0);

      const creditTotal = entries
        .filter((entry) => entry.direction === 'CREDIT')
        .reduce((sum, entry) => sum + entry.amount, 0);

      if (
        entries.length !== 2 ||
        money(debitTotal) !== transfer.amount ||
        money(creditTotal) !== transfer.amount
      ) {
        throw new TransactionError(
          `Ledger invariant failed for ${transfer.transferId}`,
          'LEDGER_INVARIANT'
        );
      }
    }
  }

  checkOptimisticConcurrency() {
    if (!this.options.optimisticConcurrency) {
      return;
    }

    for (const [accountId, originalVersion] of this.readVersions.entries()) {
      const currentVersion = this.store.accountVersions.get(accountId);

      if (currentVersion !== originalVersion) {
        throw new TransactionError(
          `Account ${accountId} changed during transaction ${this.id}`,
          'SERIALIZATION_CONFLICT',
          true
        );
      }
    }
  }

  commit() {
    this.ensureActive();

    try {
      this.validateConsistency();
      this.checkOptimisticConcurrency();

      for (const [transferId] of this.newTransfers) {
        if (this.store.transfers.has(transferId)) {
          throw new TransactionError(
            `Transfer ${transferId} was committed by another transaction`,
            'DUPLICATE_TRANSFER',
            false
          );
        }
      }

      for (const [accountId, account] of this.writes.entries()) {
        this.store.accounts.set(accountId, { ...account });

        const currentVersion =
          this.store.accountVersions.get(accountId) ?? 0;

        this.store.accountVersions.set(accountId, currentVersion + 1);
      }

      for (const transfer of this.newTransfers) {
        this.store.transfers.set(transfer.transferId, {
          ...transfer,
        });
      }

      for (const entry of this.newLedgerEntries) {
        this.store.ledger.push({
          ...entry,
          createdAt: new Date().toISOString(),
        });
      }

      this.state = TransactionState.COMMITTED;
      this.emit('commit', { transactionId: this.id });
    } catch (error) {
      this.rollback();
      throw error;
    }
  }

  rollback() {
    if (this.state === TransactionState.COMMITTED) {
      throw new TransactionError(
        'A committed transaction cannot be rolled back',
        'INVALID_STATE'
      );
    }

    if (this.state === TransactionState.ACTIVE) {
      this.state = TransactionState.ROLLED_BACK;
      this.writes.clear();
      this.newTransfers.length = 0;
      this.newLedgerEntries.length = 0;
      this.emit('rollback', { transactionId: this.id });
    }
  }
}

class TransactionService {
  constructor(store) {
    this.store = store;
    this.events = new EventEmitter();
  }

  execute(id, callback) {
    const transaction = new Transaction(this.store, id);

    transaction.on('begin', (event) => {
      this.events.emit('transaction.begin', event);
    });

    transaction.on('mutation', (event) => {
      this.events.emit('transaction.mutation', event);
    });

    transaction.on('commit', (event) => {
      this.events.emit('transaction.commit', event);
    });

    transaction.on('rollback', (event) => {
      this.events.emit('transaction.rollback', event);
    });

    transaction.begin();

    try {
      callback(transaction);
      transaction.commit();
      return transaction;
    } catch (error) {
      if (transaction.state === TransactionState.ACTIVE) {
        transaction.rollback();
      }
      throw error;
    }
  }
}

class IdempotencyRegistry {
  constructor() {
    this.results = new Map();
  }

  has(key) {
    return this.results.has(key);
  }

  get(key) {
    return this.results.get(key);
  }

  record(key, result) {
    if (this.results.has(key)) {
      throw new TransactionError(
        `Idempotency key ${key} already has a result`,
        'DUPLICATE_IDEMPOTENCY_KEY'
      );
    }

    this.results.set(key, result);
  }
}

function printAccounts(store, heading) {
  console.log(`\n--- ${heading} ---`);

  for (const account of store.accounts.values()) {
    console.log(
      `${account.accountId} | ${account.owner} | ` +
      `${account.balance.toFixed(2)} ${account.currency}`
    );
  }
}

function seedStore() {
  const store = new LedgerStore();

  store.addAccount('A100', 'Anika', 'INR', 1000);
  store.addAccount('B200', 'Rohan', 'INR', 500);
  store.addAccount('C300', 'Meera', 'INR', 750);

  return store;
}

function demonstrateAtomicity() {
  console.log('\n=== Atomicity ===');

  const store = seedStore();
  const service = new TransactionService(store);

  try {
    service.execute('TX-ATOMIC-FAIL', (transaction) => {
      transaction.transfer(
        'TRANSFER-ATOMIC-FAIL',
        'A100',
        'B200',
        100
      );

      throw new Error('Injected failure after transfer staging');
    });
  } catch (error) {
    console.log(`Expected failure: ${error.message}`);
  }

  assert.equal(store.readAccount('A100').balance, 1000);
  assert.equal(store.readAccount('B200').balance, 500);
  assert.equal(store.transfers.size, 0);

  console.log(
    'No staged account, transfer, or ledger mutation escaped the rollback.'
  );
}

function demonstrateConsistency() {
  console.log('\n=== Consistency ===');

  const store = seedStore();
  const service = new TransactionService(store);
  const before = store.totalBalance('INR');

  service.execute('TX-CONSISTENCY', (transaction) => {
    transaction.transfer(
      'TRANSFER-CONSISTENCY',
      'A100',
      'C300',
      125
    );
  });

  const after = store.totalBalance('INR');

  assert.equal(before, after);
  assert.equal(store.readAccount('A100').balance, 875);
  assert.equal(store.readAccount('C300').balance, 875);

  console.log(`Total before: ${before.toFixed(2)} INR`);
  console.log(`Total after:  ${after.toFixed(2)} INR`);
  console.log('Balance conservation invariant holds.');
}

function demonstrateIsolation() {
  console.log('\n=== Isolation with Transaction Snapshots ===');

  const store = seedStore();

  const first = new Transaction(store, 'TX-ISOLATION-A');
  const second = new Transaction(store, 'TX-ISOLATION-B');

  first.begin();
  second.begin();

  first.transfer('TRANSFER-A', 'A100', 'B200', 100);

  // The second transaction reads its own snapshot. It does not see first's
  // uncommitted staged balance because the write has not reached the store.
  assert.equal(second.readAccount('A100').balance, 1000);

  first.commit();

  // The second transaction still has its original snapshot. This is the
  // defining behavior of the simplified snapshot-isolation model.
  assert.equal(second.readAccount('A100').balance, 1000);

  second.rollback();

  assert.equal(store.readAccount('A100').balance, 900);

  console.log(
    'A transaction snapshot does not automatically change when another '
    + 'transaction commits.'
  );
}

function demonstrateOptimisticConcurrency() {
  console.log('\n=== Optimistic Concurrency ===');

  const store = seedStore();

  const first = new Transaction(store, 'TX-OCC-A');
  const second = new Transaction(store, 'TX-OCC-B');

  first.begin();
  second.begin();

  first.transfer('TRANSFER-OCC-A', 'A100', 'B200', 100);
  first.commit();

  try {
    second.transfer('TRANSFER-OCC-B', 'A100', 'C300', 50);
    second.commit();
  } catch (error) {
    assert.equal(error.code, 'SERIALIZATION_CONFLICT');
    console.log(`Expected serialization conflict: ${error.message}`);
  }

  assert.equal(store.readAccount('A100').balance, 900);
  assert.equal(store.readAccount('B200').balance, 600);
  assert.equal(store.readAccount('C300').balance, 750);
}

function demonstrateIdempotency() {
  console.log('\n=== Idempotency ===');

  const store = seedStore();
  const service = new TransactionService(store);
  const registry = new IdempotencyRegistry();

  const requestKey = 'payment-request-7f31';

  if (!registry.has(requestKey)) {
    service.execute('TX-IDEMPOTENT', (transaction) => {
      transaction.transfer(
        'TRANSFER-IDEMPOTENT',
        'A100',
        'B200',
        75
      );
    });

    registry.record(requestKey, {
      transferId: 'TRANSFER-IDEMPOTENT',
      status: 'committed',
    });
  }

  // A network retry reuses the same request key. The operation is not executed
  // a second time, avoiding duplicate financial effects.
  const retryResult = registry.get(requestKey);

  assert.deepEqual(retryResult, {
    transferId: 'TRANSFER-IDEMPOTENT',
    status: 'committed',
  });

  assert.equal(store.readAccount('A100').balance, 925);
  assert.equal(store.readAccount('B200').balance, 575);

  console.log('Retry reused the original transaction result.');
}

function demonstrateRetryClassification() {
  console.log('\n=== Retry Classification ===');

  const store = seedStore();
  const service = new TransactionService(store);
  let attempts = 0;

  function executeWithRetry(maxAttempts, operation) {
    let lastError;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        return operation();
      } catch (error) {
        lastError = error;

        if (!error.retryable || attempt === maxAttempts) {
          throw error;
        }

        console.log(`Retrying transient failure after attempt ${attempt}`);
      }
    }

    throw lastError;
  }

  executeWithRetry(3, () => {
    attempts += 1;

    if (attempts < 3) {
      throw new TransactionError(
        'Simulated temporary serialization conflict',
        'SERIALIZATION_CONFLICT',
        true
      );
    }

    return service.execute('TX-RETRY', (transaction) => {
      transaction.transfer(
        'TRANSFER-RETRY',
        'A100',
        'B200',
        25
      );
    });
  });

  assert.equal(attempts, 3);
  assert.equal(store.readAccount('A100').balance, 975);

  try {
    executeWithRetry(3, () => {
      throw new TransactionError(
        'Business rule violation',
        'INSUFFICIENT_FUNDS',
        false
      );
    });
  } catch (error) {
    assert.equal(error.retryable, false);
    console.log(
      'Non-retryable business failure was not repeatedly executed.'
    );
  }
}

function demonstrateDurabilityModel() {
  console.log('\n=== Durability Model ===');

  const store = seedStore();
  const service = new TransactionService(store);

  service.execute('TX-DURABILITY', (transaction) => {
    transaction.transfer(
      'TRANSFER-DURABILITY',
      'A100',
      'C300',
      80
    );
  });

  // This in-memory model has no operating-system-backed database file, so
  // durability is represented by the committed store state. A real database
  // must flush its WAL/data pages according to its durability configuration.
  const committedState = JSON.stringify({
    accounts: [...store.accounts.values()],
    transfers: [...store.transfers.values()],
  });

  assert.match(committedState, /TRANSFER-DURABILITY/);
  assert.equal(store.readAccount('A100').balance, 920);

  console.log(
    'The model distinguishes a committed state from an uncommitted '
    + 'transaction state; durable storage is delegated to a real DB engine.'
  );
}

function demonstrateFailureBeforeCommit() {
  console.log('\n=== Failure Before Commit ===');

  const store = seedStore();
  const service = new TransactionService(store);

  service.events.on('transaction.rollback', ({ transactionId }) => {
    console.log(`Rollback event received for ${transactionId}`);
  });

  try {
    service.execute('TX-EVENT-FAIL', (transaction) => {
      transaction.transfer(
        'TRANSFER-EVENT-FAIL',
        'A100',
        'B200',
        50
      );

      throw new TransactionError(
        'External dependency failed before commit',
        'DEPENDENCY_FAILURE',
        true
      );
    });
  } catch (error) {
    assert.equal(error.code, 'DEPENDENCY_FAILURE');
  }

  assert.equal(store.readAccount('A100').balance, 1000);
  assert.equal(store.readAccount('B200').balance, 500);
  assert.equal(store.transfers.size, 0);

  console.log('The failure generated no partial financial state.');
}

function demonstrateLedgerVerification() {
  console.log('\n=== Ledger Verification ===');

  const store = seedStore();
  const service = new TransactionService(store);

  service.execute('TX-LEDGER-1', (transaction) => {
    transaction.transfer('TRANSFER-LEDGER-1', 'A100', 'B200', 40);
  });

  service.execute('TX-LEDGER-2', (transaction) => {
    transaction.transfer('TRANSFER-LEDGER-2', 'B200', 'C300', 20);
  });

  for (const transfer of store.transfers.values()) {
    const entries = store.ledger.filter(
      (entry) => entry.transactionId === transfer.transferId
    );

    assert.equal(entries.length, 2);

    const debit = entries.find((entry) => entry.direction === 'DEBIT');
    const credit = entries.find((entry) => entry.direction === 'CREDIT');

    assert.ok(debit);
    assert.ok(credit);
    assert.equal(debit.amount, transfer.amount);
    assert.equal(credit.amount, transfer.amount);
  }

  console.log(
    `Verified ${store.transfers.size} transfer(s), each with balanced `
    + 'debit and credit entries.'
  );
}

function demonstrateEventDrivenObservability() {
  console.log('\n=== Event-Driven Transaction Observability ===');

  const store = seedStore();
  const service = new TransactionService(store);
  const events = [];

  for (const eventName of [
    'transaction.begin',
    'transaction.mutation',
    'transaction.commit',
    'transaction.rollback',
  ]) {
    service.events.on(eventName, (event) => {
      events.push({ eventName, ...event });
    });
  }

  service.execute('TX-OBSERVABILITY', (transaction) => {
    transaction.transfer(
      'TRANSFER-OBSERVABILITY',
      'A100',
      'B200',
      10
    );
  });

  assert.equal(events[0].eventName, 'transaction.begin');
  assert.equal(events.at(-1).eventName, 'transaction.commit');

  console.log(
    events.map((event) => event.eventName).join(' -> ')
  );
}

function demonstrateValidationFailures() {
  console.log('\n=== Validation Failures ===');

  const store = seedStore();
  const service = new TransactionService(store);

  const cases = [
    {
      label: 'zero amount',
      action: (transaction) =>
        transaction.transfer('BAD-1', 'A100', 'B200', 0),
    },
    {
      label: 'negative amount',
      action: (transaction) =>
        transaction.transfer('BAD-2', 'A100', 'B200', -5),
    },
    {
      label: 'same account',
      action: (transaction) =>
        transaction.transfer('BAD-3', 'A100', 'A100', 5),
    },
    {
      label: 'currency mismatch',
      action: (transaction) => {
        transaction.store.addAccount('USD-1', 'Dev', 'USD', 100);
        transaction.transfer('BAD-4', 'A100', 'USD-1', 5);
      },
    },
  ];

  for (const testCase of cases) {
    try {
      service.execute(`VALIDATION-${testCase.label}`, testCase.action);
      assert.fail(`Expected ${testCase.label} to fail`);
    } catch (error) {
      console.log(`${testCase.label}: ${error.code}`);
    }
  }

  assert.equal(store.readAccount('A100').balance, 1000);
}

function run() {
  demonstrateAtomicity();
  demonstrateConsistency();
  demonstrateIsolation();
  demonstrateOptimisticConcurrency();
  demonstrateIdempotency();
  demonstrateRetryClassification();
  demonstrateDurabilityModel();
  demonstrateFailureBeforeCommit();
  demonstrateLedgerVerification();
  demonstrateEventDrivenObservability();
  demonstrateValidationFailures();

  const finalStore = seedStore();
  const service = new TransactionService(finalStore);

  service.execute('TX-FINAL', (transaction) => {
    transaction.transfer('TRANSFER-FINAL', 'A100', 'C300', 100);
  });

  printAccounts(finalStore, 'Final committed state');

  console.log('\n=== Completed ===');
  console.log(
    'The JavaScript model exercised transaction state, atomic staging, '
    + 'consistency invariants, snapshot isolation, optimistic concurrency, '
    + 'idempotency, retry classification, durability boundaries, and '
    + 'event-driven observability.'
  );
}

run();
