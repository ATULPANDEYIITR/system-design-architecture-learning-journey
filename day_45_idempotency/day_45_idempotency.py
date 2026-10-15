from __future__ import annotations

"""
Idempotency, safe retries, duplicate requests, and idempotent APIs.

This executable module models a payment API whose clients may safely retry
requests after timeouts or transient failures. The central mechanism is an
idempotency key: a client-generated identifier binds repeated attempts to the
same logical operation.

The implementation demonstrates:
- deterministic request fingerprints
- first-request execution
- replay of an already completed operation
- rejection of key reuse with different parameters
- concurrent duplicate requests
- transient failures before and after durable state changes
- an in-memory idempotency store
- a SQLite-backed durable idempotency store
- retry behavior
- response replay
- expiration
- observability and audit information
- limitations of local idempotency stores
- why idempotency does not itself provide exactly-once distributed execution
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(value: Any) -> str:
    """Create stable JSON so equivalent request objects have the same encoding."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_fingerprint(payload: dict[str, Any]) -> str:
    """Bind an idempotency key to the actual request parameters."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    body: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "body": self.body,
        }


@dataclass
class IdempotencyRecord:
    key: str
    fingerprint: str
    status: str
    response: Optional[ApiResponse]
    created_at: datetime
    expires_at: datetime


class IdempotencyConflict(Exception):
    """Raised when a key is reused for a different logical request."""


class IdempotencyInProgress(Exception):
    """Raised when another request currently owns execution for the same key."""


class IdempotencyExpired(Exception):
    """Raised when a key exists but its retention period has expired."""


class InMemoryIdempotencyStore:
    """
    Thread-safe store.

    A real multi-instance API cannot rely on this store because another server
    process will not see the same records. It is useful for understanding the
    state machine and for a single-process service.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.RLock()

    def _remove_expired(self, key: str, now: datetime) -> None:
        record = self._records.get(key)
        if record and record.expires_at <= now:
            del self._records[key]

    def begin(self, key: str, fingerprint: str) -> IdempotencyRecord:
        now = utc_now()

        with self._lock:
            self._remove_expired(key, now)
            existing = self._records.get(key)

            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise IdempotencyConflict(
                        "The idempotency key was already used with different request parameters."
                    )

                if existing.status == "COMPLETED":
                    return existing

                raise IdempotencyInProgress(
                    "The idempotency key is currently being processed."
                )

            record = IdempotencyRecord(
                key=key,
                fingerprint=fingerprint,
                status="PROCESSING",
                response=None,
                created_at=now,
                expires_at=now + self.ttl,
            )
            self._records[key] = record
            return record

    def complete(self, key: str, response: ApiResponse) -> None:
        with self._lock:
            record = self._records.get(key)
            if record is None:
                raise KeyError("Idempotency record no longer exists.")

            record.status = "COMPLETED"
            record.response = response

    def abort(self, key: str) -> None:
        """
        Remove a processing record when no durable side effect occurred.

        This is safe only when the operation definitely failed before creating
        its externally visible effect. If that fact is uncertain, deleting the
        record can permit a duplicate side effect.
        """
        with self._lock:
            record = self._records.get(key)
            if record and record.status == "PROCESSING":
                del self._records[key]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "key": r.key,
                    "status": r.status,
                    "fingerprint": r.fingerprint[:12],
                    "created_at": r.created_at.isoformat(),
                    "expires_at": r.expires_at.isoformat(),
                }
                for r in self._records.values()
            ]


class PaymentLedger:
    """
    Simplified payment ledger.

    The ledger intentionally has its own transaction lock. Idempotency prevents
    the API from intentionally creating a second logical payment, while the
    ledger lock protects its local balance and payment collection.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._payments: dict[str, dict[str, Any]] = {}
        self._balances: dict[str, int] = {}

    def create_payment(self, customer_id: str, amount_cents: int) -> dict[str, Any]:
        if amount_cents <= 0:
            raise ValueError("Payment amount must be positive.")

        with self._lock:
            payment_id = f"pay_{uuid.uuid4().hex[:16]}"
            self._payments[payment_id] = {
                "payment_id": payment_id,
                "customer_id": customer_id,
                "amount_cents": amount_cents,
                "created_at": utc_now().isoformat(),
                "state": "CAPTURED",
            }
            self._balances[customer_id] = (
                self._balances.get(customer_id, 0) + amount_cents
            )
            return dict(self._payments[payment_id])

    def count(self) -> int:
        with self._lock:
            return len(self._payments)

    def all_payments(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._payments.values())


class IdempotentPaymentApi:
    """
    Payment API using the idempotency store.

    The business operation executes only after the key is claimed. A completed
    response is replayed without calling the payment ledger again.
    """

    def __init__(self, store: InMemoryIdempotencyStore, ledger: PaymentLedger) -> None:
        self.store = store
        self.ledger = ledger

    def post_payment(
        self,
        *,
        idempotency_key: str,
        customer_id: str,
        amount_cents: int,
        simulated_failure: Optional[str] = None,
    ) -> ApiResponse:
        if not idempotency_key or len(idempotency_key) > 255:
            return ApiResponse(
                400,
                {"error": "A non-empty idempotency key of at most 255 characters is required."},
            )

        if not customer_id:
            return ApiResponse(400, {"error": "customer_id is required."})

        if amount_cents <= 0:
            return ApiResponse(400, {"error": "amount_cents must be positive."})

        payload = {
            "customer_id": customer_id,
            "amount_cents": amount_cents,
        }
        fingerprint = request_fingerprint(payload)

        try:
            record = self.store.begin(idempotency_key, fingerprint)
        except IdempotencyConflict as exc:
            return ApiResponse(409, {"error": str(exc)})
        except IdempotencyInProgress as exc:
            return ApiResponse(409, {"error": str(exc)})

        if record.status == "COMPLETED":
            assert record.response is not None
            replay = dict(record.response.body)
            replay["idempotent_replay"] = True
            return ApiResponse(record.response.status_code, replay)

        try:
            if simulated_failure == "before_side_effect":
                raise ConnectionError("Transient failure before payment creation.")

            payment = self.ledger.create_payment(customer_id, amount_cents)

            if simulated_failure == "after_side_effect_before_response":
                # The payment already exists. We intentionally do not delete the
                # idempotency record because the side effect is now uncertain to
                # the caller. A retry must recover the stored outcome.
                response = ApiResponse(201, payment)
                self.store.complete(idempotency_key, response)
                raise TimeoutError(
                    "Response delivery failed after the durable side effect."
                )

            response = ApiResponse(201, payment)
            self.store.complete(idempotency_key, response)
            return response

        except TimeoutError:
            # The durable result has already been committed. Re-raise to model
            # a network timeout seen by the client.
            raise
        except Exception:
            self.store.abort(idempotency_key)
            raise


class SQLiteIdempotencyStore:
    """
    Durable store using SQLite.

    PostgreSQL or another transactional database would normally be preferred
    for a multi-instance production API. SQLite is used here because it keeps
    the demonstration executable with the Python standard library.
    """

    def __init__(self, database: str = ":memory:", ttl_seconds: int = 3600) -> None:
        self.connection = sqlite3.connect(
            database,
            check_same_thread=False,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    request_fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('PROCESSING', 'COMPLETED')),
                    status_code INTEGER,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at
                    ON idempotency_keys (expires_at);
                """
            )

    def _delete_expired(self, key: str) -> None:
        now = utc_now().isoformat()
        self.connection.execute(
            """
            DELETE FROM idempotency_keys
            WHERE idempotency_key = ? AND expires_at <= ?
            """,
            (key, now),
        )

    def begin(self, key: str, fingerprint: str) -> Optional[ApiResponse]:
        with self._lock:
            self._delete_expired(key)

            try:
                self.connection.execute(
                    """
                    INSERT INTO idempotency_keys (
                        idempotency_key,
                        request_fingerprint,
                        state,
                        created_at,
                        expires_at
                    )
                    VALUES (?, ?, 'PROCESSING', ?, ?)
                    """,
                    (
                        key,
                        fingerprint,
                        utc_now().isoformat(),
                        (utc_now() + timedelta(seconds=self.ttl_seconds)).isoformat(),
                    ),
                )
                return None
            except sqlite3.IntegrityError:
                row = self.connection.execute(
                    """
                    SELECT *
                    FROM idempotency_keys
                    WHERE idempotency_key = ?
                    """,
                    (key,),
                ).fetchone()

                if row is None:
                    raise RuntimeError("Idempotency record disappeared during lookup.")

                if row["request_fingerprint"] != fingerprint:
                    raise IdempotencyConflict(
                        "The idempotency key is bound to different request parameters."
                    )

                if row["state"] == "PROCESSING":
                    raise IdempotencyInProgress(
                        "The logical operation is still processing."
                    )

                return ApiResponse(
                    row["status_code"],
                    json.loads(row["response_json"]),
                )

    def complete(self, key: str, response: ApiResponse) -> None:
        with self._lock:
            self.connection.execute(
                """
                UPDATE idempotency_keys
                SET state = 'COMPLETED',
                    status_code = ?,
                    response_json = ?
                WHERE idempotency_key = ?
                """,
                (
                    response.status_code,
                    canonical_json(response.body),
                    key,
                ),
            )

    def abort(self, key: str) -> None:
        with self._lock:
            self.connection.execute(
                """
                DELETE FROM idempotency_keys
                WHERE idempotency_key = ? AND state = 'PROCESSING'
                """,
                (key,),
            )

    def purge_expired(self) -> int:
        with self._lock:
            cursor = self.connection.execute(
                """
                DELETE FROM idempotency_keys
                WHERE expires_at <= ?
                """,
                (utc_now().isoformat(),),
            )
            return cursor.rowcount


def run_basic_retry_demo() -> None:
    print("\n=== Basic safe retry ===")

    store = InMemoryIdempotencyStore()
    ledger = PaymentLedger()
    api = IdempotentPaymentApi(store, ledger)

    key = "checkout-attempt-001"

    first = api.post_payment(
        idempotency_key=key,
        customer_id="customer-42",
        amount_cents=2500,
    )
    second = api.post_payment(
        idempotency_key=key,
        customer_id="customer-42",
        amount_cents=2500,
    )

    print("First:", first.as_dict())
    print("Retry:", second.as_dict())
    print("Payments created:", ledger.count())


def run_conflict_demo() -> None:
    print("\n=== Same key, different parameters ===")

    store = InMemoryIdempotencyStore()
    ledger = PaymentLedger()
    api = IdempotentPaymentApi(store, ledger)

    key = "checkout-attempt-002"

    print(
        api.post_payment(
            idempotency_key=key,
            customer_id="customer-42",
            amount_cents=2500,
        ).as_dict()
    )

    print(
        api.post_payment(
            idempotency_key=key,
            customer_id="customer-42",
            amount_cents=9900,
        ).as_dict()
    )

    print("Payments created:", ledger.count())


def run_timeout_demo() -> None:
    print("\n=== Timeout after durable side effect ===")

    store = InMemoryIdempotencyStore()
    ledger = PaymentLedger()
    api = IdempotentPaymentApi(store, ledger)

    key = "checkout-attempt-003"

    try:
        api.post_payment(
            idempotency_key=key,
            customer_id="customer-77",
            amount_cents=5000,
            simulated_failure="after_side_effect_before_response",
        )
    except TimeoutError as exc:
        print("Client observed:", exc)

    retry = api.post_payment(
        idempotency_key=key,
        customer_id="customer-77",
        amount_cents=5000,
    )

    print("Recovered retry:", retry.as_dict())
    print("Payments created:", ledger.count())


def run_concurrency_demo() -> None:
    print("\n=== Concurrent duplicate requests ===")

    store = InMemoryIdempotencyStore()
    ledger = PaymentLedger()
    api = IdempotentPaymentApi(store, ledger)

    key = "checkout-concurrent-001"
    results: list[tuple[int, ApiResponse]] = []
    results_lock = threading.Lock()

    def worker(worker_id: int) -> None:
        try:
            response = api.post_payment(
                idempotency_key=key,
                customer_id="customer-concurrent",
                amount_cents=4200,
            )
        except Exception as exc:
            response = ApiResponse(500, {"error": str(exc)})

        with results_lock:
            results.append((worker_id, response))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    for worker_id, response in sorted(results):
        print(worker_id, response.as_dict())

    print("Payments created:", ledger.count())


def run_sqlite_demo() -> None:
    print("\n=== Durable idempotency record ===")

    store = SQLiteIdempotencyStore()

    payload = {
        "customer_id": "customer-db",
        "amount_cents": 7300,
    }
    fingerprint = request_fingerprint(payload)
    key = "db-operation-001"

    first = store.begin(key, fingerprint)
    print("Initial lookup:", first)

    stored_response = ApiResponse(
        201,
        {
            "payment_id": "pay_persisted_01",
            "customer_id": "customer-db",
            "amount_cents": 7300,
        },
    )
    store.complete(key, stored_response)

    replay = store.begin(key, fingerprint)
    print("Replay from durable store:", replay.as_dict() if replay else None)

    try:
        store.begin(
            key,
            request_fingerprint(
                {
                    "customer_id": "customer-db",
                    "amount_cents": 9999,
                }
            ),
        )
    except IdempotencyConflict as exc:
        print("Conflict:", exc)


def run_fingerprint_demo() -> None:
    print("\n=== Canonical request fingerprint ===")

    first_payload = {
        "amount_cents": 1200,
        "customer_id": "customer-1",
    }
    equivalent_payload = {
        "customer_id": "customer-1",
        "amount_cents": 1200,
    }
    different_payload = {
        "customer_id": "customer-1",
        "amount_cents": 1201,
    }

    print(
        "Equivalent payloads match:",
        request_fingerprint(first_payload) == request_fingerprint(equivalent_payload),
    )
    print(
        "Different payloads match:",
        request_fingerprint(first_payload) == request_fingerprint(different_payload),
    )


def run_expiration_demo() -> None:
    print("\n=== Key expiration ===")

    store = InMemoryIdempotencyStore(ttl_seconds=1)
    ledger = PaymentLedger()
    api = IdempotentPaymentApi(store, ledger)

    key = "short-lived-001"

    print(
        api.post_payment(
            idempotency_key=key,
            customer_id="customer-expire",
            amount_cents=1000,
        ).as_dict()
    )

    time.sleep(1.1)

    print(
        api.post_payment(
            idempotency_key=key,
            customer_id="customer-expire",
            amount_cents=1000,
        ).as_dict()
    )

    print(
        "The second request is a new logical operation because the retention "
        "window has expired."
    )


def main() -> None:
    run_basic_retry_demo()
    run_conflict_demo()
    run_timeout_demo()
    run_concurrency_demo()
    run_sqlite_demo()
    run_fingerprint_demo()
    run_expiration_demo()


if __name__ == "__main__":
    main()
