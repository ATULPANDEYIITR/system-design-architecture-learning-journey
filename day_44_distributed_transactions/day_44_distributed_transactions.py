#!/usr/bin/env python3
"""Distributed transactions, two-phase commit, and distributed coordination.

Run with:
    python distributed_transactions.py

The simulation uses only the Python standard library. It models a coordinator,
multiple resource participants, durable decision records, voting, prepare and
commit phases, timeouts, recovery, idempotent messages, and failure scenarios.

This is an educational in-memory simulator, not a production transaction
manager. Its journal illustrates durable-log semantics but does not survive
process termination.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Callable


class ParticipantState(str, Enum):
    ACTIVE = "ACTIVE"
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


class TransactionState(str, Enum):
    NEW = "NEW"
    PREPARING = "PREPARING"
    COMMIT_DECIDED = "COMMIT_DECIDED"
    ABORT_DECIDED = "ABORT_DECIDED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    IN_DOUBT = "IN_DOUBT"


class ProtocolError(RuntimeError):
    """Raised when a protocol operation violates transaction rules."""


class ParticipantUnavailable(ConnectionError):
    """Raised when a participant cannot respond to the coordinator."""


@dataclass(frozen=True)
class Vote:
    participant_id: str
    transaction_id: str
    yes: bool
    reason: str


@dataclass
class TransactionRecord:
    transaction_id: str
    state: TransactionState = TransactionState.NEW
    participants: list[str] = field(default_factory=list)
    votes: dict[str, bool] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    decision_reason: str | None = None


class DurableJournal:
    """Append-only JSON Lines journal.

    Production implementations need fsync, atomic record framing, corruption
    handling, log rotation, and a clearly defined persistence guarantee.
    This implementation flushes the file but intentionally does not claim
    power-loss durability.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.events: list[dict[str, Any]] = []
        self._lock = RLock()

        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as file:
                    for line in file:
                        if line.strip():
                            self.events.append(json.loads(line))

    def append(self, transaction_id: str, event: str, **details: Any) -> None:
        entry = {
            "transaction_id": transaction_id,
            "event": event,
            "timestamp": time.time(),
            "details": details,
        }
        with self._lock:
            if self.path:
                with self.path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(entry, sort_keys=True) + "\n")
                    file.flush()
            self.events.append(entry)

    def latest_decision(self, transaction_id: str) -> str | None:
        for entry in reversed(self.events):
            if entry["transaction_id"] != transaction_id:
                continue
            event = entry["event"]
            if event in {"GLOBAL_COMMIT", "GLOBAL_ABORT"}:
                return "COMMIT" if event == "GLOBAL_COMMIT" else "ABORT"
        return None

    def has_prepared_record(self, transaction_id: str) -> bool:
        return any(
            entry["transaction_id"] == transaction_id
            and entry["event"] == "PREPARED"
            for entry in self.events
        )


class Participant:
    """A transaction participant with a reservation-based resource model."""

    def __init__(
        self,
        participant_id: str,
        initial_balance: int,
        journal: DurableJournal,
    ) -> None:
        if not participant_id.strip():
            raise ValueError("Participant ID must not be empty")
        if initial_balance < 0:
            raise ValueError("Initial balance cannot be negative")

        self.participant_id = participant_id
        self.balance = initial_balance
        self.journal = journal
        self.states: dict[str, ParticipantState] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self.reserved_delta: dict[str, int] = {}
        self.available = True
        self.fail_prepare: Callable[[str, int], bool] = lambda _tx, _d: False
        self._lock = RLock()

    def _check_available(self) -> None:
        if not self.available:
            raise ParticipantUnavailable(
                f"Participant {self.participant_id} is unavailable"
            )

    def prepare(self, transaction_id: str, delta: int) -> Vote:
        """Reserve a change without exposing it as a committed balance."""
        with self._lock:
            self._check_available()
            previous = self.states.get(transaction_id)

            if previous == ParticipantState.PREPARED:
                if self.reserved_delta[transaction_id] != delta:
                    raise ProtocolError("Conflicting retry for prepared transaction")
                return Vote(self.participant_id, transaction_id, True, "Already prepared")

            if previous == ParticipantState.COMMITTED:
                return Vote(self.participant_id, transaction_id, True, "Already committed")

            if previous == ParticipantState.ABORTED:
                return Vote(self.participant_id, transaction_id, False, "Already aborted")

            if self.fail_prepare(transaction_id, delta):
                self.journal.append(
                    transaction_id, "VOTE_NO", participant=self.participant_id
                )
                return Vote(self.participant_id, transaction_id, False, "Injected failure")

            projected_balance = self.balance + delta
            if projected_balance < 0:
                self.journal.append(
                    transaction_id,
                    "VOTE_NO",
                    participant=self.participant_id,
                    reason="Insufficient funds",
                )
                return Vote(
                    self.participant_id,
                    transaction_id,
                    False,
                    "Insufficient funds",
                )

            # In a database, this reservation would be backed by a durable
            # prepared transaction and locks or equivalent concurrency control.
            self.reserved_delta[transaction_id] = delta
            self.states[transaction_id] = ParticipantState.PREPARED
            self.journal.append(
                transaction_id,
                "PREPARED",
                participant=self.participant_id,
                delta=delta,
                balance=self.balance,
            )
            return Vote(self.participant_id, transaction_id, True, "Prepared")

    def commit(self, transaction_id: str) -> None:
        with self._lock:
            self._check_available()
            state = self.states.get(transaction_id)

            if state == ParticipantState.COMMITTED:
                return
            if state != ParticipantState.PREPARED:
                raise ProtocolError(
                    f"{self.participant_id} cannot commit from state {state}"
                )

            # The coordinator must persist GLOBAL_COMMIT before sending this.
            self.balance += self.reserved_delta.pop(transaction_id)
            self.states[transaction_id] = ParticipantState.COMMITTED
            self.journal.append(
                transaction_id,
                "PARTICIPANT_COMMIT",
                participant=self.participant_id,
                balance=self.balance,
            )

    def abort(self, transaction_id: str) -> None:
        with self._lock:
            self._check_available()
            state = self.states.get(transaction_id)

            if state == ParticipantState.ABORTED:
                return
            if state == ParticipantState.COMMITTED:
                raise ProtocolError("A committed transaction cannot be aborted")
            if state == ParticipantState.PREPARED:
                self.reserved_delta.pop(transaction_id, None)

            self.states[transaction_id] = ParticipantState.ABORTED
            self.journal.append(
                transaction_id, "PARTICIPANT_ABORT", participant=self.participant_id
            )

    def recover_from_decision(self, transaction_id: str, decision: str) -> None:
        """Apply a known global decision after communication is restored."""
        if decision == "COMMIT":
            self.commit(transaction_id)
        elif decision == "ABORT":
            self.abort(transaction_id)
        else:
            raise ProtocolError(f"Unknown global decision: {decision}")


class Coordinator:
    """Coordinates a single atomic transaction using two-phase commit."""

    def __init__(self, journal: DurableJournal) -> None:
        self.journal = journal
        self.records: dict[str, TransactionRecord] = {}
        self.participants: dict[str, Participant] = {}
        self._lock = RLock()

    def register(self, participant: Participant) -> None:
        if participant.participant_id in self.participants:
            raise ValueError("Duplicate participant ID")
        self.participants[participant.participant_id] = participant

    def begin(self, deltas: dict[str, int]) -> str:
        if not deltas:
            raise ValueError("A transaction requires at least one participant")
        if any(participant_id not in self.participants for participant_id in deltas):
            raise ValueError("All participants must be registered")
        if any(not isinstance(delta, int) for delta in deltas.values()):
            raise TypeError("This simulator accepts integer balance changes only")

        transaction_id = str(uuid.uuid4())
        record = TransactionRecord(
            transaction_id=transaction_id,
            participants=list(deltas),
        )

        with self._lock:
            self.records[transaction_id] = record
            self.journal.append(
                transaction_id, "BEGIN", deltas=deltas, participants=record.participants
            )

        try:
            return self._execute(record, deltas)
        except ParticipantUnavailable:
            # A communication failure does not establish a global abort.
            # The coordinator must consult its durable decision record.
            record.state = TransactionState.IN_DOUBT
            self.journal.append(transaction_id, "COORDINATOR_IN_DOUBT")
            return transaction_id

    def _execute(
        self, record: TransactionRecord, deltas: dict[str, int]
    ) -> str:
        record.state = TransactionState.PREPARING
        self.journal.append(record.transaction_id, "PREPARING")

        all_yes = True

        for participant_id, delta in deltas.items():
            try:
                vote = self.participants[participant_id].prepare(
                    record.transaction_id, delta
                )
            except ParticipantUnavailable:
                record.votes[participant_id] = False
                all_yes = False
                break

            record.votes[participant_id] = vote.yes
            self.journal.append(
                record.transaction_id,
                "VOTE",
                participant=participant_id,
                yes=vote.yes,
                reason=vote.reason,
            )

            if not vote.yes:
                all_yes = False
                break

        if all_yes and len(record.votes) == len(deltas):
            # The durable global decision must precede commit messages.
            self.journal.append(record.transaction_id, "GLOBAL_COMMIT")
            record.state = TransactionState.COMMIT_DECIDED

            for participant_id in record.participants:
                self.participants[participant_id].commit(record.transaction_id)

            record.state = TransactionState.COMMITTED
            self.journal.append(record.transaction_id, "TRANSACTION_COMPLETE")
            return record.transaction_id

        self.journal.append(
            record.transaction_id,
            "GLOBAL_ABORT",
            reason="Negative vote, missing vote, or unavailable participant",
        )
        record.state = TransactionState.ABORT_DECIDED

        for participant_id in record.participants:
            participant = self.participants[participant_id]
            try:
                if participant.states.get(record.transaction_id) not in {
                    ParticipantState.COMMITTED,
                    ParticipantState.ABORTED,
                }:
                    participant.abort(record.transaction_id)
            except ParticipantUnavailable:
                # The durable abort decision allows retry after recovery.
                record.state = TransactionState.IN_DOUBT

        if record.state != TransactionState.IN_DOUBT:
            record.state = TransactionState.ABORTED
            self.journal.append(record.transaction_id, "TRANSACTION_COMPLETE")

        return record.transaction_id

    def recover(self, transaction_id: str) -> TransactionState:
        """Retry participant actions using a durable coordinator decision."""
        if transaction_id not in self.records:
            raise KeyError(f"Unknown transaction: {transaction_id}")

        record = self.records[transaction_id]
        decision = self.journal.latest_decision(transaction_id)

        if decision is None:
            record.state = TransactionState.IN_DOUBT
            return record.state

        for participant_id in record.participants:
            participant = self.participants[participant_id]
            participant.recover_from_decision(transaction_id, decision)

        record.state = (
            TransactionState.COMMITTED
            if decision == "COMMIT"
            else TransactionState.ABORTED
        )
        self.journal.append(
            transaction_id, "RECOVERY_COMPLETE", decision=decision
        )
        return record.state


def print_balances(participants: list[Participant]) -> None:
    for participant in participants:
        print(
            f"  {participant.participant_id}: "
            f"balance={participant.balance}, "
            f"states={participant.states}"
        )


def successful_transfer_demo() -> None:
    print("\n=== Successful two-phase commit ===")
    journal = DurableJournal()
    coordinator = Coordinator(journal)
    source = Participant("payments-ledger", 1000, journal)
    destination = Participant("merchant-ledger", 250, journal)
    coordinator.register(source)
    coordinator.register(destination)

    transaction_id = coordinator.begin(
        {"payments-ledger": -175, "merchant-ledger": 175}
    )
    record = coordinator.records[transaction_id]

    assert record.state == TransactionState.COMMITTED
    assert source.balance == 825
    assert destination.balance == 425
    assert source.balance + destination.balance == 1250

    print(f"Transaction: {transaction_id}")
    print(f"State: {record.state.value}")
    print_balances([source, destination])


def rejected_transfer_demo() -> None:
    print("\n=== Negative vote causes global abort ===")
    journal = DurableJournal()
    coordinator = Coordinator(journal)
    source = Participant("wallet-A", 40, journal)
    destination = Participant("wallet-B", 10, journal)
    coordinator.register(source)
    coordinator.register(destination)

    transaction_id = coordinator.begin({"wallet-A": -80, "wallet-B": 80})
    record = coordinator.records[transaction_id]

    assert record.state == TransactionState.ABORTED
    assert source.balance == 40
    assert destination.balance == 10

    print(f"State: {record.state.value}")
    print(f"Votes: {record.votes}")
    print_balances([source, destination])


def recovery_demo() -> None:
    print("\n=== Coordinator decision survives participant outage ===")
    journal = DurableJournal()
    coordinator = Coordinator(journal)
    source = Participant("inventory-reservation", 50, journal)
    destination = Participant("shipment-allocation", 5, journal)
    coordinator.register(source)
    coordinator.register(destination)

    destination.available = False
    transaction_id = coordinator.begin(
        {"inventory-reservation": -3, "shipment-allocation": 3}
    )

    # The first participant may have prepared while the second was unavailable.
    assert journal.latest_decision(transaction_id) == "ABORT"
    destination.available = True

    recovered_state = coordinator.recover(transaction_id)
    assert recovered_state == TransactionState.ABORTED
    assert source.balance == 50
    assert destination.balance == 5

    print(f"Recovered state: {recovered_state.value}")
    print_balances([source, destination])


def idempotency_demo() -> None:
    print("\n=== Duplicate commit messages are idempotent ===")
    journal = DurableJournal()
    participant = Participant("warehouse", 12, journal)
    transaction_id = "tx-idempotency-example"

    vote = participant.prepare(transaction_id, -2)
    assert vote.yes
    participant.commit(transaction_id)
    participant.commit(transaction_id)

    assert participant.balance == 10
    print(f"Balance after repeated commit: {participant.balance}")


def prepared_state_hazard_demo() -> None:
    print("\n=== Prepared participants need a coordinator decision ===")
    journal = DurableJournal()
    participant = Participant("account-service", 100, journal)
    transaction_id = "tx-prepared-example"

    participant.prepare(transaction_id, -10)
    assert participant.states[transaction_id] == ParticipantState.PREPARED

    try:
        participant.abort(transaction_id)
        print("Participant was explicitly instructed to abort.")
    except ProtocolError as error:
        print(f"Protocol error: {error}")

    print(
        "Prepared state requires recovery coordination; a timeout alone "
        "does not prove that committing is safe."
    )


def journal_inspection_demo() -> None:
    print("\n=== Journal event inspection ===")
    journal = DurableJournal()
    coordinator = Coordinator(journal)
    coordinator.register(Participant("orders", 100, journal))
    coordinator.register(Participant("billing", 50, journal))

    transaction_id = coordinator.begin({"orders": -20, "billing": 20})

    for event in journal.events:
        if event["transaction_id"] == transaction_id:
            print(f"{event['event']}: {event['details']}")


def main() -> None:
    successful_transfer_demo()
    rejected_transfer_demo()
    recovery_demo()
    idempotency_demo()
    prepared_state_hazard_demo()
    journal_inspection_demo()

    print("\nAll distributed transaction demonstrations completed.")


if __name__ == "__main__":
    main()
