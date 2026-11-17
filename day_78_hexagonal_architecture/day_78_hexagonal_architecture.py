#!/usr/bin/env python3
"""
Hexagonal Architecture: Ports and Adapters

A self-contained order-processing application demonstrating:
- Domain entities and business rules
- Input and output ports
- Primary and secondary adapters
- Dependency inversion
- Application services and use cases
- Dependency injection
- Transaction boundaries
- Repository abstractions
- Event publishing
- Error handling
- Unit-style assertions

Run:
    python hexagonal_architecture.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from threading import RLock
from typing import Callable
from uuid import uuid4


# ============================================================
# DOMAIN LAYER
# ============================================================

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class DomainError(Exception):
    """Raised when a domain invariant is violated."""


class ApplicationError(Exception):
    """Raised when an application operation cannot complete."""


@dataclass(frozen=True)
class OrderItem:
    product_id: str
    quantity: int
    unit_price: Decimal

    def __post_init__(self):
        if not self.product_id.strip():
            raise DomainError("Product ID cannot be empty")
        if self.quantity <= 0:
            raise DomainError("Quantity must be positive")
        if self.unit_price <= Decimal("0"):
            raise DomainError("Unit price must be positive")

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    version: int = 0

    def __post_init__(self):
        if not self.order_id or not self.customer_id:
            raise DomainError("Order and customer IDs are required")
        if not self.items:
            raise DomainError("An order must contain at least one item")

    @property
    def total(self) -> Decimal:
        return sum(
            (item.subtotal for item in self.items),
            Decimal("0.00")
        )

    def confirm(self):
        if self.status != OrderStatus.PENDING:
            raise DomainError("Only pending orders can be confirmed")
        self.status = OrderStatus.CONFIRMED
        self.version += 1

    def cancel(self):
        if self.status != OrderStatus.PENDING:
            raise DomainError("Only pending orders can be cancelled")
        self.status = OrderStatus.CANCELLED
        self.version += 1


# ============================================================
# PORTS
# ============================================================

# Primary ports: operations exposed to external actors.

class PlaceOrderPort(ABC):

    @abstractmethod
    def place_order(
        self,
        customer_id: str,
        items: list[OrderItem]
    ) -> Order:
        pass


# Secondary ports: capabilities required by the application.

class OrderRepositoryPort(ABC):

    @abstractmethod
    def save(self, order: Order) -> None:
        pass

    @abstractmethod
    def get_by_id(self, order_id: str) -> Order | None:
        pass


class InventoryPort(ABC):

    @abstractmethod
    def reserve(
        self,
        product_id: str,
        quantity: int
    ) -> bool:
        pass

    @abstractmethod
    def release(
        self,
        product_id: str,
        quantity: int
    ) -> None:
        pass


class PaymentPort(ABC):

    @abstractmethod
    def charge(
        self,
        customer_id: str,
        amount: Decimal,
        idempotency_key: str
    ) -> str:
        pass

    @abstractmethod
    def refund(self, payment_id: str) -> None:
        pass


class EventPublisherPort(ABC):

    @abstractmethod
    def publish(self, event: dict) -> None:
        pass


# ============================================================
# APPLICATION LAYER
# ============================================================

class PlaceOrderService(PlaceOrderPort):
    """
    Coordinates the use case.

    The service depends on abstractions, not infrastructure.
    Inventory and payment reservations are compensated if a
    later operation fails. A production system should use
    durable transactions or a transactional outbox.
    """

    def __init__(
        self,
        repository: OrderRepositoryPort,
        inventory: InventoryPort,
        payment: PaymentPort,
        publisher: EventPublisherPort
    ):
        self.repository = repository
        self.inventory = inventory
        self.payment = payment
        self.publisher = publisher

    def place_order(
        self,
        customer_id: str,
        items: list[OrderItem]
    ) -> Order:

        if not customer_id.strip():
            raise ApplicationError("Customer ID is required")

        if not items:
            raise ApplicationError("Order items are required")

        order = Order(
            order_id=str(uuid4()),
            customer_id=customer_id,
            items=items
        )

        reserved: list[OrderItem] = []
        payment_id: str | None = None

        try:
            # Reserve inventory before accepting payment.
            for item in items:
                if not self.inventory.reserve(
                    item.product_id,
                    item.quantity
                ):
                    raise ApplicationError(
                        f"Insufficient inventory: {item.product_id}"
                    )
                reserved.append(item)

            payment_id = self.payment.charge(
                customer_id,
                order.total,
                order.order_id
            )

            order.confirm()
            self.repository.save(order)

            self.publisher.publish({
                "event_id": str(uuid4()),
                "event_type": "OrderConfirmed",
                "order_id": order.order_id,
                "payment_id": payment_id,
                "amount": str(order.total),
                "occurred_at": datetime.now(
                    timezone.utc
                ).isoformat()
            })

            return order

        except Exception as exc:
            # Compensation is best-effort. Production systems
            # must persist compensation operations for recovery.
            if payment_id is not None:
                try:
                    self.payment.refund(payment_id)
                except Exception:
                    pass

            for item in reversed(reserved):
                try:
                    self.inventory.release(
                        item.product_id,
                        item.quantity
                    )
                except Exception:
                    pass

            raise ApplicationError(
                f"Order processing failed: {exc}"
            ) from exc


# ============================================================
# SECONDARY ADAPTERS
# ============================================================

class InMemoryOrderRepository(OrderRepositoryPort):

    def __init__(self):
        self._orders: dict[str, Order] = {}
        self._lock = RLock()

    def save(self, order: Order) -> None:
        with self._lock:
            existing = self._orders.get(order.order_id)

            if existing and order.version <= existing.version:
                raise ApplicationError(
                    "Order version must increase"
                )

            self._orders[order.order_id] = order

    def get_by_id(self, order_id: str) -> Order | None:
        with self._lock:
            return self._orders.get(order_id)


class InMemoryInventoryAdapter(InventoryPort):

    def __init__(self, stock: dict[str, int]):
        self._stock = dict(stock)
        self._lock = RLock()

        if any(quantity < 0 for quantity in self._stock.values()):
            raise ValueError("Stock cannot be negative")

    def reserve(self, product_id: str, quantity: int) -> bool:
        with self._lock:
            available = self._stock.get(product_id, 0)

            if quantity <= 0 or available < quantity:
                return False

            self._stock[product_id] = available - quantity
            return True

    def release(self, product_id: str, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("Release quantity must be positive")

        with self._lock:
            self._stock[product_id] = (
                self._stock.get(product_id, 0) + quantity
            )

    def available(self, product_id: str) -> int:
        with self._lock:
            return self._stock.get(product_id, 0)


class InMemoryPaymentAdapter(PaymentPort):

    def __init__(self):
        self._payments: dict[str, str] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = RLock()

    def charge(
        self,
        customer_id: str,
        amount: Decimal,
        idempotency_key: str
    ) -> str:

        if amount <= Decimal("0"):
            raise ValueError("Payment amount must be positive")

        with self._lock:
            if idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]

            payment_id = str(uuid4())
            self._payments[payment_id] = "charged"
            self._idempotency[idempotency_key] = payment_id
            return payment_id

    def refund(self, payment_id: str) -> None:
        with self._lock:
            if self._payments.get(payment_id) != "charged":
                raise ApplicationError(
                    "Payment cannot be refunded"
                )

            self._payments[payment_id] = "refunded"


class InMemoryEventPublisher(EventPublisherPort):

    def __init__(self):
        self.events: list[dict] = []

    def publish(self, event: dict) -> None:
        self.events.append(dict(event))


# ============================================================
# PRIMARY ADAPTER
# ============================================================

class ConsoleOrderAdapter:
    """
    Console adapter invokes the application's input port.
    It does not contain order-processing business rules.
    """

    def __init__(self, use_case: PlaceOrderPort):
        self.use_case = use_case

    def submit(self):
        items = [
            OrderItem(
                product_id="LAPTOP-001",
                quantity=1,
                unit_price=Decimal("75000.00")
            ),
            OrderItem(
                product_id="MOUSE-001",
                quantity=2,
                unit_price=Decimal("1200.00")
            )
        ]

        return self.use_case.place_order(
            customer_id="CUSTOMER-1001",
            items=items
        )


# ============================================================
# COMPOSITION ROOT
# ============================================================

def build_application() -> tuple[
    ConsoleOrderAdapter,
    InMemoryInventoryAdapter,
    InMemoryOrderRepository,
    InMemoryEventPublisher
]:

    repository = InMemoryOrderRepository()

    inventory = InMemoryInventoryAdapter({
        "LAPTOP-001": 10,
        "MOUSE-001": 50
    })

    payment = InMemoryPaymentAdapter()
    publisher = InMemoryEventPublisher()

    service = PlaceOrderService(
        repository=repository,
        inventory=inventory,
        payment=payment,
        publisher=publisher
    )

    console_adapter = ConsoleOrderAdapter(service)

    return (
        console_adapter,
        inventory,
        repository,
        publisher
    )


# ============================================================
# EXECUTION AND TESTING
# ============================================================

def run_tests():
    inventory = InMemoryInventoryAdapter({"P1": 5})
    repository = InMemoryOrderRepository()
    payment = InMemoryPaymentAdapter()
    publisher = InMemoryEventPublisher()

    service = PlaceOrderService(
        repository,
        inventory,
        payment,
        publisher
    )

    item = OrderItem(
        product_id="P1",
        quantity=2,
        unit_price=Decimal("100.00")
    )

    order = service.place_order("C1", [item])

    assert order.status == OrderStatus.CONFIRMED
    assert order.total == Decimal("200.00")
    assert inventory.available("P1") == 3
    assert repository.get_by_id(order.order_id) is order
    assert len(publisher.events) == 1

    # Insufficient stock must not produce a confirmed order.
    try:
        service.place_order(
            "C2",
            [
                OrderItem(
                    "P1",
                    10,
                    Decimal("50.00")
                )
            ]
        )
        raise AssertionError("Expected inventory failure")
    except ApplicationError:
        pass

    assert inventory.available("P1") == 3

    # Domain invariants.
    try:
        OrderItem("P1", 0, Decimal("100"))
        raise AssertionError("Expected validation failure")
    except DomainError:
        pass

    # A confirmed order cannot be cancelled through the
    # pending-only domain transition.
    try:
        order.cancel()
        raise AssertionError("Expected invalid state transition")
    except DomainError:
        pass

    print("All tests passed.")


def main():
    adapter, inventory, repository, publisher = build_application()

    try:
        order = adapter.submit()

        print("\nHEXAGONAL ORDER PROCESSING")
        print("-" * 45)
        print(f"Order ID: {order.order_id}")
        print(f"Customer: {order.customer_id}")
        print(f"Status: {order.status.value}")
        print(f"Total: {order.total}")
        print(f"Version: {order.version}")
        print(f"Events published: {len(publisher.events)}")
        print(
            "Remaining laptop inventory:",
            inventory.available("LAPTOP-001")
        )

    except ApplicationError as error:
        print(f"Application error: {error}")

    run_tests()


if __name__ == "__main__":
    main()
