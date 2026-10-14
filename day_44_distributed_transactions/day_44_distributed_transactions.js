"use strict";

/*
 * Distributed transaction coordination with JavaScript.
 *
 * This implementation emphasizes asynchronous messaging, deadlines,
 * retryable commands, explicit participant states, and the distinction
 * between a missing response and a negative vote.
 *
 * Run using Node.js 18 or later:
 *     node distributed-transactions.js
 *
 * This is an in-memory simulation, not a durable distributed transaction
 * service. A real deployment needs persistent decision logs, transport
 * authentication, fencing, durable participant state, and recovery workers.
 */

const { randomUUID } = require("node:crypto");

const ParticipantState = Object.freeze({
  ACTIVE: "ACTIVE",
  PREPARED: "PREPARED",
  COMMITTED: "COMMITTED",
  ABORTED: "ABORTED",
});

const TransactionState = Object.freeze({
  NEW: "NEW",
  PREPARING: "PREPARING",
  COMMIT_DECIDED: "COMMIT_DECIDED",
  ABORT_DECIDED: "ABORT_DECIDED",
  COMMITTED: "COMMITTED",
  ABORTED: "ABORTED",
  IN_DOUBT: "IN_DOUBT",
});

class ProtocolError extends Error {}
class ParticipantUnavailable extends Error {}

class EventJournal {
  constructor() {
    this.events = [];
  }

  append(transactionId, event, details = {}) {
    this.events.push(
      Object.freeze({
        transactionId,
        event,
        timestamp: new Date().toISOString(),
        details: structuredClone(details),
      }),
    );
  }

  decision(transactionId) {
    for (let index = this.events.length - 1; index >= 0; index -= 1) {
      const entry = this.events[index];
      if (entry.transactionId !== transactionId) continue;
      if (entry.event === "GLOBAL_COMMIT") return "COMMIT";
      if (entry.event === "GLOBAL_ABORT") return "ABORT";
    }
    return null;
  }
}

class Participant {
  constructor(id, balance, journal) {
    if (!id.trim()) throw new TypeError("Participant ID is required");
    if (!Number.isSafeInteger(balance) || balance < 0) {
      throw new RangeError("Balance must be a non-negative safe integer");
    }

    this.id = id;
    this.balance = balance;
    this.journal = journal;
    this.available = true;
    this.states = new Map();
    this.reservations = new Map();
    this.operationIds = new Map();
    this.rejectPrepare = () => false;
  }

  assertAvailable() {
    if (!this.available) {
      throw new ParticipantUnavailable(`${this.id} is unavailable`);
    }
  }

  async prepare(transactionId, operationId, delta) {
    this.assertAvailable();

    if (!Number.isSafeInteger(delta)) {
      throw new TypeError("Transaction deltas must be safe integers");
    }

    const state = this.states.get(transactionId);
    if (state === ParticipantState.PREPARED) {
      if (this.operationIds.get(transactionId) !== operationId) {
        throw new ProtocolError("Transaction retry has a different operation ID");
      }
      return { participantId: this.id, yes: true, reason: "Already prepared" };
    }

    if (state === ParticipantState.COMMITTED) {
      return { participantId: this.id, yes: true, reason: "Already committed" };
    }

    if (state === ParticipantState.ABORTED) {
      return { participantId: this.id, yes: false, reason: "Already aborted" };
    }

    if (this.rejectPrepare(delta)) {
      this.journal.append(transactionId, "VOTE_NO", { participantId: this.id });
      return { participantId: this.id, yes: false, reason: "Policy rejection" };
    }

    if (!Number.isSafeInteger(this.balance + delta) || this.balance + delta < 0) {
      this.journal.append(transactionId, "VOTE_NO", {
        participantId: this.id,
        reason: "Insufficient funds or numeric overflow",
      });
      return {
        participantId: this.id,
        yes: false,
        reason: "Insufficient funds or numeric overflow",
      };
    }

    this.reservations.set(transactionId, delta);
    this.operationIds.set(transactionId, operationId);
    this.states.set(transactionId, ParticipantState.PREPARED);

    this.journal.append(transactionId, "PREPARED", {
      participantId: this.id,
      operationId,
      delta,
    });

    return { participantId: this.id, yes: true, reason: "Prepared" };
  }

  async commit(transactionId) {
    this.assertAvailable();

    const state = this.states.get(transactionId);
    if (state === ParticipantState.COMMITTED) return;
    if (state !== ParticipantState.PREPARED) {
      throw new ProtocolError(`${this.id} cannot commit from ${state}`);
    }

    // Commit only after the coordinator has durably recorded GLOBAL_COMMIT.
    const delta = this.reservations.get(transactionId);
    this.balance += delta;
    this.reservations.delete(transactionId);
    this.states.set(transactionId, ParticipantState.COMMITTED);

    this.journal.append(transactionId, "PARTICIPANT_COMMIT", {
      participantId: this.id,
      balance: this.balance,
    });
  }

  async abort(transactionId) {
    this.assertAvailable();

    const state = this.states.get(transactionId);
    if (state === ParticipantState.ABORTED) return;
    if (state === ParticipantState.COMMITTED) {
      throw new ProtocolError("Committed work cannot be rolled back by 2PC abort");
    }

    this.reservations.delete(transactionId);
    this.states.set(transactionId, ParticipantState.ABORTED);
    this.journal.append(transactionId, "PARTICIPANT_ABORT", {
      participantId: this.id,
    });
  }

  async applyDecision(transactionId, decision) {
    if (decision === "COMMIT") return this.commit(transactionId);
    if (decision === "ABORT") return this.abort(transactionId);
    throw new ProtocolError(`Unknown global decision: ${decision}`);
  }
}

class Coordinator {
  constructor(journal, options = {}) {
    this.journal = journal;
    this.participants = new Map();
    this.transactions = new Map();
    this.timeoutMs = options.timeoutMs ?? 500;
    this.maxRetries = options.maxRetries ?? 2;

    if (!Number.isInteger(this.timeoutMs) || this.timeoutMs <= 0) {
      throw new RangeError("timeoutMs must be a positive integer");
    }
    if (!Number.isInteger(this.maxRetries) || this.maxRetries < 0) {
      throw new RangeError("maxRetries cannot be negative");
    }
  }

  register(participant) {
    if (this.participants.has(participant.id)) {
      throw new Error(`Duplicate participant: ${participant.id}`);
    }
    this.participants.set(participant.id, participant);
  }

  async sendWithDeadline(action) {
    // Promise.race bounds waiting time but does not cancel the underlying
    // operation. Production transports need real cancellation and fencing.
    let timer;
    try {
      return await Promise.race([
        action(),
        new Promise((_, reject) => {
          timer = setTimeout(
            () => reject(new ParticipantUnavailable("Request deadline exceeded")),
            this.timeoutMs,
          );
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  }

  async callParticipant(action) {
    let lastError;

    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      try {
        return await this.sendWithDeadline(action);
      } catch (error) {
        lastError = error;
        if (!(error instanceof ParticipantUnavailable)) throw error;
      }
    }

    throw lastError;
  }

  async execute(deltas) {
    const entries = Object.entries(deltas);
    if (entries.length === 0) {
      throw new TypeError("A distributed transaction requires participants");
    }

    for (const [id, delta] of entries) {
      if (!this.participants.has(id)) throw new Error(`Unknown participant: ${id}`);
      if (!Number.isSafeInteger(delta)) {
        throw new TypeError(`Invalid integer delta for ${id}`);
      }
    }

    const transactionId = randomUUID();
    const operationId = randomUUID();
    const transaction = {
      transactionId,
      operationId,
      state: TransactionState.NEW,
      participants: entries.map(([id]) => id),
      votes: new Map(),
      decision: null,
    };

    this.transactions.set(transactionId, transaction);
    this.journal.append(transactionId, "BEGIN", {
      operationId,
      deltas: Object.fromEntries(entries),
    });

    transaction.state = TransactionState.PREPARING;
    this.journal.append(transactionId, "PREPARING");

    let allYes = true;

    // The vote phase collects each participant's promise before deciding.
    for (const [id, delta] of entries) {
      try {
        const vote = await this.callParticipant(() =>
          this.participants.get(id).prepare(transactionId, operationId, delta),
        );
        transaction.votes.set(id, vote.yes);
        this.journal.append(transactionId, "VOTE", {
          participantId: id,
          yes: vote.yes,
          reason: vote.reason,
        });

        if (!vote.yes) {
          allYes = false;
          break;
        }
      } catch (error) {
        transaction.votes.set(id, false);
        allYes = false;
        this.journal.append(transactionId, "VOTE_UNAVAILABLE", {
          participantId: id,
          error: error.message,
        });
        break;
      }
    }

    if (allYes && transaction.votes.size === entries.length) {
      // This decision record must be durable before commit messages are sent.
      this.journal.append(transactionId, "GLOBAL_COMMIT");
      transaction.decision = "COMMIT";
      transaction.state = TransactionState.COMMIT_DECIDED;
    } else {
      this.journal.append(transactionId, "GLOBAL_ABORT", {
        reason: "Negative vote or missing response",
      });
      transaction.decision = "ABORT";
      transaction.state = TransactionState.ABORT_DECIDED;
    }

    let deliveryFailure = false;

    for (const id of transaction.participants) {
      try {
        await this.callParticipant(() =>
          this.participants.get(id).applyDecision(
            transactionId,
            transaction.decision,
          ),
        );
      } catch (error) {
        deliveryFailure = true;
        this.journal.append(transactionId, "DECISION_DELIVERY_FAILED", {
          participantId: id,
          decision: transaction.decision,
          error: error.message,
        });
      }
    }

    if (deliveryFailure) {
      transaction.state = TransactionState.IN_DOUBT;
    } else {
      transaction.state =
        transaction.decision === "COMMIT"
          ? TransactionState.COMMITTED
          : TransactionState.ABORTED;
      this.journal.append(transactionId, "TRANSACTION_COMPLETE", {
        state: transaction.state,
      });
    }

    return transaction;
  }

  async recover(transactionId) {
    const transaction = this.transactions.get(transactionId);
    if (!transaction) throw new Error(`Unknown transaction ${transactionId}`);

    const decision = this.journal.decision(transactionId);
    if (!decision) {
      transaction.state = TransactionState.IN_DOUBT;
      return transaction.state;
    }

    for (const participantId of transaction.participants) {
      const participant = this.participants.get(participantId);
      await this.callParticipant(() => participant.applyDecision(transactionId, decision));
    }

    transaction.state =
      decision === "COMMIT"
        ? TransactionState.COMMITTED
        : TransactionState.ABORTED;

    this.journal.append(transactionId, "RECOVERY_COMPLETE", { decision });
    return transaction.state;
  }
}

async function successfulTransfer() {
  console.log("\n=== Asynchronous transfer ===");

  const journal = new EventJournal();
  const coordinator = new Coordinator(journal);
  const accounts = new Participant("accounts", 1000, journal);
  const settlement = new Participant("settlement", 400, journal);

  coordinator.register(accounts);
  coordinator.register(settlement);

  const transaction = await coordinator.execute({
    accounts: -125,
    settlement: 125,
  });

  console.log({
    state: transaction.state,
    accountsBalance: accounts.balance,
    settlementBalance: settlement.balance,
  });

  if (transaction.state !== TransactionState.COMMITTED) {
    throw new Error("Expected a committed transfer");
  }
  if (accounts.balance + settlement.balance !== 1400) {
    throw new Error("Balance conservation violated");
  }
}

async function negativeVote() {
  console.log("\n=== Negative vote ===");

  const journal = new EventJournal();
  const coordinator = new Coordinator(journal);
  const account = new Participant("customer-account", 25, journal);
  const merchant = new Participant("merchant-account", 0, journal);

  coordinator.register(account);
  coordinator.register(merchant);

  const transaction = await coordinator.execute({
    "customer-account": -60,
    "merchant-account": 60,
  });

  console.log({
    state: transaction.state,
    accountBalance: account.balance,
    merchantBalance: merchant.balance,
  });

  if (transaction.state !== TransactionState.ABORTED) {
    throw new Error("Insufficient funds must abort the transaction");
  }
}

async function participantRecovery() {
  console.log("\n=== Recovery after an abort decision ===");

  const journal = new EventJournal();
  const coordinator = new Coordinator(journal, { timeoutMs: 50, maxRetries: 0 });
  const inventory = new Participant("inventory", 20, journal);
  const dispatch = new Participant("dispatch", 0, journal);

  coordinator.register(inventory);
  coordinator.register(dispatch);
  dispatch.available = false;

  const transaction = await coordinator.execute({
    inventory: -2,
    dispatch: 2,
  });

  if (transaction.state !== TransactionState.IN_DOUBT) {
    throw new Error("Expected incomplete decision delivery");
  }

  dispatch.available = true;
  const recovered = await coordinator.recover(transaction.transactionId);

  console.log({
    recovered,
    inventoryBalance: inventory.balance,
    dispatchBalance: dispatch.balance,
  });

  if (recovered !== TransactionState.ABORTED) {
    throw new Error("Recovery must apply the recorded abort decision");
  }
}

async function run() {
  await successfulTransfer();
  await negativeVote();
  await participantRecovery();

  console.log("\n=== Journal overview ===");
  const journal = new EventJournal();
  const coordinator = new Coordinator(journal);
  coordinator.register(new Participant("orders", 100, journal));
  coordinator.register(new Participant("billing", 50, journal));

  const transaction = await coordinator.execute({ orders: -15, billing: 15 });
  console.log(
    journal.events
      .filter((event) => event.transactionId === transaction.transactionId)
      .map((event) => event.event),
  );
}

run().catch((error) => {
  console.error("Distributed transaction simulation failed:", error.message);
  process.exitCode = 1;
});
