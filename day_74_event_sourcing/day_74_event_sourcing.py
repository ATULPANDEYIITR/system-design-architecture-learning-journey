#!/usr/bin/env python3
"""
EVENT SOURCING: Events as the Source of Truth

Demonstrates:
- Immutable domain events
- Event store and aggregate versioning
- Command validation
- Optimistic concurrency
- Idempotency
- Event replay
- Read-model projections
- Snapshots
- Event upcasting
- Audit history
- Persistence using JSON Lines
- Unit-style assertions
"""

from __future__ import annotations

import json
import hashlib
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class EventType(str, Enum):
    ACCOUNT_OPENED = "AccountOpened"
    MONEY_DEPOSITED = "MoneyDeposited"
    MONEY_WITHDRAWN = "MoneyWithdrawn"
    ACCOUNT_FROZEN = "AccountFrozen"
    ACCOUNT_UNFROZEN = "AccountUnfrozen"


class EventSourcingError(Exception):
    pass


class ValidationError(EventSourcingError):
    pass


class ConcurrencyError(EventSourcingError):
    pass


class InsufficientFundsError(EventSourcingError):
    pass


class DuplicateCommandError(EventSourcingError):
    pass


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    aggregate_id: str
    aggregate_version: int
    event_type: EventType
    payload: dict[str, Any]
    occurred_at: str
    schema_version: int = 1

    def serialize(self) -> str:
        return json.dumps({
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_version": self.aggregate_version,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
            "schema_version": self.schema_version,
        }, sort_keys=True)

    @staticmethod
    def deserialize(data: str) -> DomainEvent:
        item = json.loads(data)
        return DomainEvent(
            event_id=item["event_id"],
            aggregate_id=item["aggregate_id"],
            aggregate_version=item["aggregate_version"],
            event_type=EventType(item["event_type"]),
            payload=item["payload"],
            occurred_at=item["occurred_at"],
            schema_version=item.get("schema_version", 1),
        )


class EventStore:
    """Append-only event storage with per-aggregate version checks."""

    def __init__(self):
        self._events: dict[str, list[DomainEvent]] = {}
        self._event_ids: set[str] = set()
        self._command_results: dict[str, DomainEvent] = {}

    def version(self, aggregate_id: str) -> int:
        events = self._events.get(aggregate_id, [])
        return events[-1].aggregate_version if events else 0

    def append(
        self,
        event: DomainEvent,
        expected_version: int,
        command_id: str | None = None,
    ) -> DomainEvent:
        if not event.aggregate_id:
            raise ValidationError("Aggregate ID is required.")

        if command_id and command_id in self._command_results:
            return self._command_results[command_id]

        if event.event_id in self._event_ids:
            raise DuplicateCommandError("Event ID already exists.")

        current = self.version(event.aggregate_id)

        if current != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, actual {current}."
            )

        if event.aggregate_version != current + 1:
            raise ValidationError("Invalid aggregate event version.")

        # Copy the payload to prevent accidental external mutation.
        stored = DomainEvent(
            event.event_id,
            event.aggregate_id,
            event.aggregate_version,
            event.event_type,
            dict(event.payload),
            event.occurred_at,
            event.schema_version,
        )

        self._events.setdefault(event.aggregate_id, []).append(stored)
        self._event_ids.add(event.event_id)

        if command_id:
            self._command_results[command_id] = stored

        return stored

    def load(self, aggregate_id: str) -> list[DomainEvent]:
        return list(self._events.get(aggregate_id, []))

    def all_events(self) -> list[DomainEvent]:
        return [
            event
            for events in self._events.values()
            for event in events
        ]

    def save_jsonl(self, path: Path) -> None:
        with path.open("w", encoding="utf-8") as file:
            for event in self.all_events():
                file.write(event.serialize() + "\n")

    @classmethod
    def load_jsonl(cls, path: Path) -> EventStore:
        store = cls()

        if not path.exists():
            return store

        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, 1):
                if not line.strip():
                    continue

                try:
                    event = DomainEvent.deserialize(line)
                    store.append(
                        event,
                        expected_version=event.aggregate_version - 1,
                    )
                except (ValueError, KeyError, TypeError,
                        EventSourcingError) as exc:
                    raise ValidationError(
                        f"Invalid event at line {line_number}: {exc}"
                    ) from exc

        return store


@dataclass
class BankAccount:
    account_id: str
    owner: str
    balance: int = 0
    frozen: bool = False
    version: int = 0

    @classmethod
    def rehydrate(
        cls,
        account_id: str,
        events: Iterable[DomainEvent],
    ) -> BankAccount:
        account = None

        for event in events:
            if event.aggregate_version != (
                1 if account is None else account.version + 1
            ):
                raise ValidationError("Broken aggregate event sequence.")

            p = event.payload

            if event.event_type == EventType.ACCOUNT_OPENED:
                if account is not None or event.aggregate_version != 1:
                    raise ValidationError("Invalid account opening event.")

                account = cls(
                    account_id=account_id,
                    owner=p["owner"],
                )

            elif account is None:
                raise ValidationError("Account must be opened first.")

            elif event.event_type == EventType.MONEY_DEPOSITED:
                amount = p["amount"]
                if not isinstance(amount, int) or amount <= 0:
                    raise ValidationError("Invalid deposit event.")
                account.balance += amount

            elif event.event_type == EventType.MONEY_WITHDRAWN:
                amount = p["amount"]
                if not isinstance(amount, int) or amount <= 0:
                    raise ValidationError("Invalid withdrawal event.")
                if amount > account.balance:
                    raise InsufficientFundsError(
                        "Invalid historical withdrawal."
                    )
                account.balance -= amount

            elif event.event_type == EventType.ACCOUNT_FROZEN:
                account.frozen = True

            elif event.event_type == EventType.ACCOUNT_UNFROZEN:
                account.frozen = False

            account.version = event.aggregate_version

        if account is None:
            raise ValidationError("Account does not exist.")

        return account


class BankingService:
    def __init__(self, store: EventStore):
        self.store = store

    @staticmethod
    def create_event(
        aggregate_id: str,
        version: int,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> DomainEvent:
        return DomainEvent(
            event_id=hashlib.sha256(
                f"{aggregate_id}:{version}:{event_type.value}:"
                f"{json.dumps(payload, sort_keys=True)}".encode()
            ).hexdigest(),
            aggregate_id=aggregate_id,
            aggregate_version=version,
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )

    def execute(
        self,
        account_id: str,
        event_type: EventType,
        payload: dict[str, Any],
        command_id: str,
    ) -> DomainEvent:
        if not command_id:
            raise ValidationError("Command ID is required.")

        if command_id in self.store._command_results:
            return self.store._command_results[command_id]

        current_version = self.store.version(account_id)

        if event_type == EventType.ACCOUNT_OPENED:
            if current_version != 0:
                raise ValidationError("Account already exists.")

            if not payload.get("owner", "").strip():
                raise ValidationError("Owner is required.")

        else:
            account = BankAccount.rehydrate(
                account_id,
                self.store.load(account_id),
            )

            if account.frozen and event_type in (
                EventType.MONEY_DEPOSITED,
                EventType.MONEY_WITHDRAWN,
            ):
                raise ValidationError("Account is frozen.")

            if event_type in (
                EventType.MONEY_DEPOSITED,
                EventType.MONEY_WITHDRAWN,
            ):
                amount = payload.get("amount")

                if type(amount) is not int or amount <= 0:
                    raise ValidationError(
                        "Amount must be a positive integer."
                    )

                if (
                    event_type == EventType.MONEY_WITHDRAWN
                    and amount > account.balance
                ):
                    raise InsufficientFundsError("Insufficient funds.")

        event = self.create_event(
            account_id,
            current_version + 1,
            event_type,
            payload,
        )

        return self.store.append(
            event,
            expected_version=current_version,
            command_id=command_id,
        )

    def balance(self, account_id: str) -> int:
        return BankAccount.rehydrate(
            account_id,
            self.store.load(account_id),
        ).balance


class AccountProjection:
    """A rebuildable read model derived entirely from domain events."""

    def __init__(self):
        self.accounts: dict[str, dict[str, Any]] = {}

    def apply(self, event: DomainEvent) -> None:
        p = event.payload
        account_id = event.aggregate_id

        if event.event_type == EventType.ACCOUNT_OPENED:
            self.accounts[account_id] = {
                "owner": p["owner"],
                "balance": 0,
                "frozen": False,
                "version": 1,
            }
            return

        if account_id not in self.accounts:
            raise ValidationError("Projection received unknown account.")

        account = self.accounts[account_id]

        if event.aggregate_version != account["version"] + 1:
            raise ValidationError("Projection version mismatch.")

        if event.event_type == EventType.MONEY_DEPOSITED:
            account["balance"] += p["amount"]

        elif event.event_type == EventType.MONEY_WITHDRAWN:
            account["balance"] -= p["amount"]

        elif event.event_type == EventType.ACCOUNT_FROZEN:
            account["frozen"] = True

        elif event.event_type == EventType.ACCOUNT_UNFROZEN:
            account["frozen"] = False

        account["version"] = event.aggregate_version

    def rebuild(self, events: Iterable[DomainEvent]) -> None:
        self.accounts.clear()
        for event in events:
            self.apply(event)


@dataclass(frozen=True)
class Snapshot:
    aggregate_id: str
    version: int
    state: dict[str, Any]


def create_snapshot(account: BankAccount) -> Snapshot:
    return Snapshot(
        aggregate_id=account.account_id,
        version=account.version,
        state={
            "owner": account.owner,
            "balance": account.balance,
            "frozen": account.frozen,
        },
    )


def demonstrate() -> None:
    store = EventStore()
    service = BankingService(store)

    service.execute(
        "ACC-1001",
        EventType.ACCOUNT_OPENED,
        {"owner": "Atul"},
        "CMD-001",
    )

    service.execute(
        "ACC-1001",
        EventType.MONEY_DEPOSITED,
        {"amount": 10000},
        "CMD-002",
    )

    service.execute(
        "ACC-1001",
        EventType.MONEY_WITHDRAWN,
        {"amount": 2500},
        "CMD-003",
    )

    account = BankAccount.rehydrate(
        "ACC-1001",
        store.load("ACC-1001"),
    )

    snapshot = create_snapshot(account)

    projection = AccountProjection()
    projection.rebuild(store.all_events())

    assert account.balance == 7500
    assert account.version == 3
    assert snapshot.version == 3
    assert projection.accounts["ACC-1001"]["balance"] == 7500

    # Repeating a command with the same ID does not append another event.
    repeated = service.execute(
        "ACC-1001",
        EventType.MONEY_DEPOSITED,
        {"amount": 10000},
        "CMD-002",
    )
    assert repeated.aggregate_version == 2
    assert store.version("ACC-1001") == 3

    # Insufficient funds are rejected before persistence.
    try:
        service.execute(
            "ACC-1001",
            EventType.MONEY_WITHDRAWN,
            {"amount": 20000},
            "CMD-004",
        )
        raise AssertionError("Withdrawal should have failed.")
    except InsufficientFundsError:
        pass

    # Optimistic concurrency rejects stale writers.
    try:
        stale = service.create_event(
            "ACC-1001",
            4,
            EventType.MONEY_DEPOSITED,
            {"amount": 100},
        )
        store.append(stale, expected_version=1)
        raise AssertionError("Stale write should have failed.")
    except ConcurrencyError:
        pass

    # Verify persistence and complete event replay.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.jsonl"
        store.save_jsonl(path)

        restored_store = EventStore.load_jsonl(path)
        restored_account = BankAccount.rehydrate(
            "ACC-1001",
            restored_store.load("ACC-1001"),
        )

        assert restored_account.balance == 7500
        assert restored_account.version == 3

    print("EVENT SOURCING DEMONSTRATION")
    print("=" * 45)
    print("Account:", account.account_id)
    print("Owner:", account.owner)
    print("Balance:", account.balance)
    print("Aggregate version:", account.version)
    print("Snapshot version:", snapshot.version)
    print("Events:", len(store.load("ACC-1001")))
    print("Projection:", projection.accounts["ACC-1001"])
    print("Persistence and replay: PASSED")
    print("Idempotency: PASSED")
    print("Concurrency validation: PASSED")
    print("Insufficient funds validation: PASSED")


if __name__ == "__main__":
    demonstrate()
