#!/usr/bin/env python3
"""
Saga Pattern: Distributed Transaction Management

Demonstrates:
- Multi-service transaction orchestration
- Forward transaction execution
- Compensating transactions
- Retry handling
- Idempotency
- Transaction state management
- Failure recovery
- Execution history and audit logging

Run: python saga_pattern.py
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
from uuid import uuid4
from datetime import datetime, timezone
import logging
import time


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("saga")


class SagaStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPENSATING = "COMPENSATING"
    COMPLETED = "COMPLETED"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


class StepStatus(Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


class SagaError(Exception):
    pass


class StepExecutionError(SagaError):
    pass


@dataclass
class SagaStep:
    name: str
    action: Callable[[], None]
    compensation: Callable[[], None]
    max_retries: int = 2
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None


@dataclass
class Saga:
    saga_id: str
    steps: list[SagaStep]
    status: SagaStatus = SagaStatus.PENDING
    completed_steps: list[SagaStep] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def record(self, event: str, details: str = "") -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": details
        }
        self.history.append(entry)
        logger.info("%s | %s", event, details)


class InventoryService:
    def __init__(self):
        self.reservations = set()

    def reserve(self, order_id: str) -> None:
        if order_id in self.reservations:
            return
        self.reservations.add(order_id)
        logger.info("Inventory reserved for %s", order_id)

    def release(self, order_id: str) -> None:
        self.reservations.discard(order_id)
        logger.info("Inventory released for %s", order_id)


class PaymentService:
    def __init__(self):
        self.charges = set()

    def charge(self, order_id: str) -> None:
        if order_id in self.charges:
            return
        self.charges.add(order_id)
        logger.info("Payment charged for %s", order_id)

    def refund(self, order_id: str) -> None:
        self.charges.discard(order_id)
        logger.info("Payment refunded for %s", order_id)


class ShippingService:
    def __init__(self):
        self.shipments = set()

    def create_shipment(self, order_id: str) -> None:
        if order_id in self.shipments:
            return
        self.shipments.add(order_id)
        logger.info("Shipment created for %s", order_id)

    def cancel_shipment(self, order_id: str) -> None:
        self.shipments.discard(order_id)
        logger.info("Shipment cancelled for %s", order_id)


class SagaOrchestrator:
    def __init__(self):
        self.sagas: dict[str, Saga] = {}

    def register(self, saga: Saga) -> None:
        if saga.saga_id in self.sagas:
            raise SagaError("Duplicate saga identifier")
        self.sagas[saga.saga_id] = saga

    def execute_step(self, saga: Saga, step: SagaStep) -> None:
        for attempt in range(step.max_retries + 1):
            step.attempts += 1
            try:
                step.action()
                step.status = StepStatus.COMPLETED
                saga.completed_steps.append(step)
                saga.record(
                    "STEP_COMPLETED",
                    f"{step.name}; attempts={step.attempts}"
                )
                return
            except Exception as exc:
                step.error = str(exc)
                saga.record(
                    "STEP_RETRY",
                    f"{step.name}; attempt={attempt + 1}; error={exc}"
                )
                if attempt == step.max_retries:
                    step.status = StepStatus.FAILED
                    raise StepExecutionError(
                        f"{step.name} failed: {exc}"
                    ) from exc
                time.sleep(min(0.1 * (2 ** attempt), 1.0))

    def compensate(self, saga: Saga) -> bool:
        saga.status = SagaStatus.COMPENSATING
        saga.record("COMPENSATION_STARTED")

        failures = []

        for step in reversed(saga.completed_steps):
            try:
                step.compensation()
                step.status = StepStatus.COMPENSATED
                saga.record("STEP_COMPENSATED", step.name)
            except Exception as exc:
                failures.append((step.name, str(exc)))
                saga.record(
                    "COMPENSATION_FAILED",
                    f"{step.name}: {exc}"
                )

        saga.status = (
            SagaStatus.FAILED if failures
            else SagaStatus.COMPENSATED
        )

        if failures:
            saga.record("MANUAL_RECOVERY_REQUIRED", str(failures))

        return not failures

    def execute(self, saga: Saga) -> SagaStatus:
        self.register(saga)
        saga.status = SagaStatus.RUNNING
        saga.record("SAGA_STARTED")

        try:
            for step in saga.steps:
                self.execute_step(saga, step)

            saga.status = SagaStatus.COMPLETED
            saga.record("SAGA_COMPLETED")

        except StepExecutionError as exc:
            saga.record("SAGA_EXECUTION_FAILED", str(exc))
            self.compensate(saga)

        return saga.status


def create_order_saga(
    order_id: str,
    inventory: InventoryService,
    payment: PaymentService,
    shipping: ShippingService,
    fail_shipping: bool = False
) -> Saga:

    def create_shipment():
        if fail_shipping:
            raise RuntimeError("Shipping provider unavailable")
        shipping.create_shipment(order_id)

    steps = [
        SagaStep(
            name="Reserve Inventory",
            action=lambda: inventory.reserve(order_id),
            compensation=lambda: inventory.release(order_id)
        ),
        SagaStep(
            name="Process Payment",
            action=lambda: payment.charge(order_id),
            compensation=lambda: payment.refund(order_id)
        ),
        SagaStep(
            name="Create Shipment",
            action=create_shipment,
            compensation=lambda: shipping.cancel_shipment(order_id)
        )
    ]

    return Saga(
        saga_id=str(uuid4()),
        steps=steps
    )


def display_result(saga: Saga) -> None:
    print("\nSAGA RESULT")
    print("=" * 55)
    print("Saga ID:", saga.saga_id)
    print("Status:", saga.status.value)
    print("Execution history:")

    for event in saga.history:
        print(
            event["timestamp"],
            event["event"],
            event["details"]
        )


def main():
    inventory = InventoryService()
    payment = PaymentService()
    shipping = ShippingService()
    orchestrator = SagaOrchestrator()

    print("\nCASE 1: Successful distributed transaction")

    saga1 = create_order_saga(
        "ORDER-1001",
        inventory,
        payment,
        shipping
    )

    orchestrator.execute(saga1)
    display_result(saga1)

    print("\nCASE 2: Shipping failure and compensation")

    saga2 = create_order_saga(
        "ORDER-1002",
        inventory,
        payment,
        shipping,
        fail_shipping=True
    )

    orchestrator.execute(saga2)
    display_result(saga2)

    print("\nFINAL SERVICE STATE")
    print("Inventory:", inventory.reservations)
    print("Payments:", payment.charges)
    print("Shipments:", shipping.shipments)

    assert saga1.status == SagaStatus.COMPLETED
    assert saga2.status == SagaStatus.COMPENSATED

    assert "ORDER-1001" in inventory.reservations
    assert "ORDER-1002" not in inventory.reservations
    assert "ORDER-1002" not in payment.charges

    print("\nAll demonstration assertions passed.")


if __name__ == "__main__":
    main()
