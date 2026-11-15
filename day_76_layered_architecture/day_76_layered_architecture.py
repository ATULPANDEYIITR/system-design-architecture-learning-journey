"""
Layered Architecture Demonstration
Layers: Presentation, Application, Domain, Infrastructure

Execution:
    python layered_architecture.py

The application implements an order-management workflow with:
- Presentation: CLI interface and request validation
- Application: use-case orchestration and transaction boundaries
- Domain: business entities, rules, and domain exceptions
- Infrastructure: repositories, persistence, and audit logging

Uses only the Python standard library.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Protocol
from uuid import uuid4


# ============================================================
# DOMAIN LAYER
# ============================================================

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class DomainError(Exception):
    """Base exception for business-rule violations."""


class ValidationError(DomainError):
    pass


class OrderNotFoundError(DomainError):
    pass


class InvalidOrderStateError(DomainError):
    pass


@dataclass(frozen=True)
class OrderItem:
    product_id: str
    name: str
    quantity: int
    unit_price: Decimal

    def __post_init__(self):
        if not self.product_id.strip():
            raise ValidationError("Product ID cannot be empty.")
        if not self.name.strip():
            raise ValidationError("Product name cannot be empty.")
        if self.quantity <= 0:
            raise ValidationError("Quantity must be positive.")
        if not self.unit_price.is_finite() or self.unit_price <= 0:
            raise ValidationError("Unit price must be positive and finite.")

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class Order:
    customer_id: str
    items: list[OrderItem]
    order_id: str = field(default_factory=lambda: str(uuid4()))
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    version: int = 0

    def __post_init__(self):
        self.customer_id = self.customer_id.strip()

        if not self.customer_id:
            raise ValidationError("Customer ID is required.")

        if not self.items:
            raise ValidationError("An order must contain at least one item.")

        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValidationError("Duplicate products are not allowed.")

    @property
    def total(self) -> Decimal:
        return sum(
            (item.subtotal for item in self.items),
            Decimal("0.00")
        ).quantize(Decimal("0.01"))

    def confirm(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise InvalidOrderStateError(
                "Only pending orders can be confirmed."
            )
        self.status = OrderStatus.CONFIRMED
        self.version += 1

    def cancel(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise InvalidOrderStateError(
                "Only pending orders can be cancelled."
            )
        self.status = OrderStatus.CANCELLED
        self.version += 1


# ============================================================
# APPLICATION LAYER
# ============================================================

class OrderRepository(Protocol):
    def save(self, order: Order) -> None:
        ...

    def get(self, order_id: str) -> Order:
        ...

    def all(self) -> list[Order]:
        ...


class AuditRepository(Protocol):
    def record(self, event: dict) -> None:
        ...


@dataclass(frozen=True)
class CreateOrderCommand:
    customer_id: str
    items: list[dict]


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    customer_id: str
    status: str
    total: str
    version: int


class OrderApplicationService:
    """
    Coordinates domain operations and infrastructure interfaces.

    Business rules remain inside domain objects. The application
    service controls the workflow without implementing persistence.
    """

    def __init__(
        self,
        orders: OrderRepository,
        audit: AuditRepository
    ):
        self.orders = orders
        self.audit = audit

    @staticmethod
    def _to_result(order: Order) -> OrderResult:
        return OrderResult(
            order_id=order.order_id,
            customer_id=order.customer_id,
            status=order.status.value,
            total=str(order.total),
            version=order.version
        )

    def create_order(self, command: CreateOrderCommand) -> OrderResult:
        if not isinstance(command, CreateOrderCommand):
            raise ValidationError("Invalid create-order command.")

        items = []

        for raw in command.items:
            try:
                price = Decimal(str(raw["unit_price"]))

                if not price.is_finite():
                    raise ValidationError("Price must be finite.")

                items.append(
                    OrderItem(
                        product_id=str(raw["product_id"]),
                        name=str(raw["name"]),
                        quantity=int(raw["quantity"]),
                        unit_price=price
                    )
                )
            except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
                raise ValidationError(
                    f"Invalid order item: {exc}"
                ) from exc

        order = Order(
            customer_id=command.customer_id,
            items=items
        )

        self.orders.save(order)

        self.audit.record({
            "event": "ORDER_CREATED",
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return self._to_result(order)

    def confirm_order(self, order_id: str) -> OrderResult:
        order = self.orders.get(order_id)

        order.confirm()
        self.orders.save(order)

        self.audit.record({
            "event": "ORDER_CONFIRMED",
            "order_id": order.order_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return self._to_result(order)

    def cancel_order(self, order_id: str) -> OrderResult:
        order = self.orders.get(order_id)

        order.cancel()
        self.orders.save(order)

        self.audit.record({
            "event": "ORDER_CANCELLED",
            "order_id": order.order_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return self._to_result(order)

    def get_order(self, order_id: str) -> OrderResult:
        return self._to_result(self.orders.get(order_id))

    def list_orders(self) -> list[OrderResult]:
        return [
            self._to_result(order)
            for order in self.orders.all()
        ]


# ============================================================
# INFRASTRUCTURE LAYER
# ============================================================

class JsonOrderRepository:
    """
    File-backed repository.

    A lock protects concurrent operations within this process.
    Writes use atomic replacement to avoid partially written files.
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock = threading.RLock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.file_path.exists():
            self._write({})

    @staticmethod
    def _serialize(order: Order) -> dict:
        return {
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "status": order.status.value,
            "created_at": order.created_at.isoformat(),
            "version": order.version,
            "items": [
                {
                    "product_id": item.product_id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price)
                }
                for item in order.items
            ]
        }

    @staticmethod
    def _deserialize(data: dict) -> Order:
        return Order(
            order_id=data["order_id"],
            customer_id=data["customer_id"],
            status=OrderStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            version=data["version"],
            items=[
                OrderItem(
                    product_id=item["product_id"],
                    name=item["name"],
                    quantity=item["quantity"],
                    unit_price=Decimal(item["unit_price"])
                )
                for item in data["items"]
            ]
        )

    def _read(self) -> dict:
        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                raise ValueError("Repository root must be an object.")

            return data

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Order repository contains invalid JSON."
            ) from exc

    def _write(self, data: dict) -> None:
        temporary = self.file_path.with_suffix(".tmp")

        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
                file.flush()

            temporary.replace(self.file_path)

        finally:
            if temporary.exists():
                temporary.unlink()

    def save(self, order: Order) -> None:
        with self.lock:
            data = self._read()
            existing = data.get(order.order_id)

            # Prevent lost updates from stale aggregate versions.
            if existing is not None:
                stored_version = existing["version"]

                if order.version < stored_version:
                    raise RuntimeError("Stale order version.")

            data[order.order_id] = self._serialize(order)
            self._write(data)

    def get(self, order_id: str) -> Order:
        with self.lock:
            data = self._read()

            if order_id not in data:
                raise OrderNotFoundError(
                    f"Order {order_id} does not exist."
                )

            return self._deserialize(data[order_id])

    def all(self) -> list[Order]:
        with self.lock:
            data = self._read()

            return [
                self._deserialize(record)
                for record in data.values()
            ]


class JsonAuditRepository:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock = threading.Lock()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: dict) -> None:
        # Append-only audit events preserve the sequence of operations.
        with self.lock:
            with self.file_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event) + "\n")


class LoggingConfiguration:
    @staticmethod
    def configure() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s"
        )


# ============================================================
# PRESENTATION LAYER
# ============================================================

class OrderCLI:
    """
    Presentation depends on the application service rather than
    accessing repositories or domain persistence directly.
    """

    def __init__(self, service: OrderApplicationService):
        self.service = service

    def create_sample(self) -> None:
        command = CreateOrderCommand(
            customer_id="CUSTOMER-1001",
            items=[
                {
                    "product_id": "PROD-101",
                    "name": "Enterprise Laptop",
                    "quantity": 2,
                    "unit_price": "75000.00"
                },
                {
                    "product_id": "PROD-102",
                    "name": "Wireless Mouse",
                    "quantity": 3,
                    "unit_price": "1200.00"
                }
            ]
        )

        result = self.service.create_order(command)
        print("Created:", asdict(result))

        confirmed = self.service.confirm_order(result.order_id)
        print("Confirmed:", asdict(confirmed))

    def display_orders(self) -> None:
        for result in self.service.list_orders():
            print(asdict(result))

    def run(self) -> None:
        print("\nLAYERED ORDER MANAGEMENT SYSTEM")

        while True:
            print("\n1. Create sample order")
            print("2. List orders")
            print("3. Exit")

            choice = input("Select: ").strip()

            try:
                if choice == "1":
                    self.create_sample()
                elif choice == "2":
                    self.display_orders()
                elif choice == "3":
                    break
                else:
                    print("Invalid selection.")

            except (DomainError, RuntimeError, OSError) as exc:
                logging.exception("Operation failed")
                print("Error:", exc)


# ============================================================
# VALIDATION AND EXECUTABLE TESTS
# ============================================================

def run_tests() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        orders = JsonOrderRepository(root / "orders.json")
        audit = JsonAuditRepository(root / "audit.jsonl")
        service = OrderApplicationService(orders, audit)

        command = CreateOrderCommand(
            customer_id="TEST-CUSTOMER",
            items=[
                {
                    "product_id": "P1",
                    "name": "Server",
                    "quantity": 2,
                    "unit_price": "1000.00"
                }
            ]
        )

        result = service.create_order(command)

        assert result.status == "PENDING"
        assert result.total == "2000.00"

        confirmed = service.confirm_order(result.order_id)
        assert confirmed.status == "CONFIRMED"

        try:
            service.cancel_order(result.order_id)
            raise AssertionError("Confirmed order was cancelled.")
        except InvalidOrderStateError:
            pass

        try:
            service.get_order("MISSING")
            raise AssertionError("Missing order was retrieved.")
        except OrderNotFoundError:
            pass

        assert len(service.list_orders()) == 1

        # Verify persistence survives repository reconstruction.
        reopened = JsonOrderRepository(root / "orders.json")
        persisted = reopened.get(result.order_id)

        assert persisted.status == OrderStatus.CONFIRMED
        assert persisted.total == Decimal("2000.00")

        print("All tests passed.")


def main() -> None:
    LoggingConfiguration.configure()

    if "--test" in sys.argv:
        run_tests()
        return

    directory = Path("layered_architecture_data")

    orders = JsonOrderRepository(directory / "orders.json")
    audit = JsonAuditRepository(directory / "audit.jsonl")

    service = OrderApplicationService(orders, audit)
    presentation = OrderCLI(service)

    presentation.run()


if __name__ == "__main__":
    main()
