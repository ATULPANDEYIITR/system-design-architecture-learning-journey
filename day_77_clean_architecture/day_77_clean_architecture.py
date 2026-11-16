"""
Clean Architecture: Dependency Inversion and Boundaries

A self-contained order-processing application demonstrating:
- Domain entities and business rules
- Application use cases
- Input and output ports
- Dependency inversion
- Repository and payment abstractions
- Infrastructure adapters
- Dependency graph validation
- Circular dependency detection
- Transaction-like failure handling
- Unit-style assertions
- JSON persistence
- Composition-root dependency injection

Run:
    python clean_architecture.py

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Protocol, Optional
from uuid import uuid4


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

logger = logging.getLogger("clean_architecture")


# ============================================================
# 1. DOMAIN LAYER
# ============================================================

class DomainError(Exception):
    """Base exception for domain rule violations."""


class ApplicationError(Exception):
    """Application-level operation failure."""


class InfrastructureError(Exception):
    """External infrastructure failure."""


class OrderStatus(Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "INR"

    def __post_init__(self):
        if not self.amount.is_finite():
            raise DomainError("Money amount must be finite.")

        if self.amount < Decimal("0"):
            raise DomainError("Money cannot be negative.")

        if len(self.currency) != 3 or not self.currency.isalpha():
            raise DomainError("Currency must be a three-letter code.")

        object.__setattr__(self, "currency", self.currency.upper())

    def add(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def multiply(self, quantity: int) -> Money:
        if quantity <= 0:
            raise DomainError("Quantity must be positive.")

        return Money(self.amount * quantity, self.currency)

    def _check_currency(self, other: Money):
        if self.currency != other.currency:
            raise DomainError("Currency mismatch.")


@dataclass(frozen=True)
class OrderLine:
    product_id: str
    quantity: int
    unit_price: Money

    def __post_init__(self):
        if not self.product_id.strip():
            raise DomainError("Product ID cannot be empty.")

        if self.quantity <= 0 or self.quantity > 1000:
            raise DomainError("Quantity must be between 1 and 1000.")

    @property
    def subtotal(self) -> Money:
        return self.unit_price.multiply(self.quantity)


@dataclass
class Order:
    order_id: str
    customer_id: str
    lines: list[OrderLine]
    status: OrderStatus = OrderStatus.PENDING
    version: int = 1

    def __post_init__(self):
        if not self.order_id.strip():
            raise DomainError("Order ID is required.")

        if not self.customer_id.strip():
            raise DomainError("Customer ID is required.")

        if not self.lines:
            raise DomainError("An order must contain at least one item.")

        if len(self.lines) > 100:
            raise DomainError("An order cannot contain more than 100 lines.")

        self.total()

    def total(self) -> Money:
        currency = self.lines[0].unit_price.currency
        result = Money(Decimal("0"), currency)

        for line in self.lines:
            result = result.add(line.subtotal)

        return result

    def mark_paid(self):
        if self.status != OrderStatus.PENDING:
            raise DomainError("Only pending orders can be paid.")

        self.status = OrderStatus.PAID
        self.version += 1

    def cancel(self):
        if self.status == OrderStatus.PAID:
            raise DomainError("Paid orders cannot be cancelled directly.")

        if self.status == OrderStatus.CANCELLED:
            raise DomainError("Order is already cancelled.")

        self.status = OrderStatus.CANCELLED
        self.version += 1


# ============================================================
# 2. APPLICATION PORTS
# ============================================================

class OrderRepository(Protocol):
    """Output port for order persistence."""

    def save(self, order: Order) -> None:
        ...

    def get(self, order_id: str) -> Optional[Order]:
        ...


class PaymentGateway(Protocol):
    """Output port for external payment processing."""

    def charge(self, order_id: str, amount: Money) -> bool:
        ...


class OrderCreatedPublisher(Protocol):
    """Output port for publishing application events."""

    def publish(self, event: dict) -> None:
        ...


class OrderInputPort(Protocol):
    """Input boundary for order creation."""

    def execute(
        self,
        customer_id: str,
        lines: list[OrderLine]
    ) -> Order:
        ...


# ============================================================
# 3. APPLICATION LAYER
# ============================================================

@dataclass
class PlaceOrder:
    """
    Coordinates the order workflow.

    This use case depends on abstractions rather than concrete
    database, payment, or messaging implementations.
    """

    repository: OrderRepository
    payment_gateway: PaymentGateway
    event_publisher: OrderCreatedPublisher

    def execute(
        self,
        customer_id: str,
        lines: list[OrderLine]
    ) -> Order:

        if not customer_id.strip():
            raise ApplicationError("Customer ID is required.")

        order = Order(
            order_id=str(uuid4()),
            customer_id=customer_id,
            lines=lines
        )

        # Persist the pending order before external payment.
        self.repository.save(order)

        try:
            successful = self.payment_gateway.charge(
                order.order_id,
                order.total()
            )

            if not successful:
                raise ApplicationError("Payment was declined.")

            order.mark_paid()
            self.repository.save(order)

            self.event_publisher.publish({
                "event": "OrderPaid",
                "order_id": order.order_id,
                "amount": str(order.total().amount),
                "currency": order.total().currency
            })

            return order

        except Exception as exc:
            logger.exception("Order processing failed.")

            # Preserve a cancelled state for a pending order.
            # A real distributed payment workflow requires an
            # idempotent payment API and compensation mechanism.
            if order.status == OrderStatus.PENDING:
                order.cancel()
                self.repository.save(order)

            if isinstance(exc, ApplicationError):
                raise

            raise ApplicationError(
                "Order processing could not be completed."
            ) from exc


@dataclass
class CancelOrder:
    repository: OrderRepository

    def execute(self, order_id: str) -> Order:
        order = self.repository.get(order_id)

        if order is None:
            raise ApplicationError("Order does not exist.")

        order.cancel()
        self.repository.save(order)

        return order


# ============================================================
# 4. INFRASTRUCTURE ADAPTERS
# ============================================================

class InMemoryOrderRepository:
    """Adapter implementing the repository output port."""

    def __init__(self):
        self._orders: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def all(self) -> list[Order]:
        return list(self._orders.values())


class FileOrderRepository:
    """
    JSON-backed adapter.

    Uses atomic replacement to avoid exposing partially written
    JSON files during normal process execution.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, order: Order) -> None:
        existing = self._read_all()

        existing[order.order_id] = {
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "status": order.status.value,
            "version": order.version,
            "lines": [
                {
                    "product_id": line.product_id,
                    "quantity": line.quantity,
                    "unit_price": str(line.unit_price.amount),
                    "currency": line.unit_price.currency
                }
                for line in order.lines
            ]
        }

        temporary = self.path.with_suffix(".tmp")

        try:
            temporary.write_text(
                json.dumps(existing, indent=2),
                encoding="utf-8"
            )
            temporary.replace(self.path)
        except OSError as exc:
            raise InfrastructureError(
                "Could not persist order."
            ) from exc

    def get(self, order_id: str) -> Optional[Order]:
        record = self._read_all().get(order_id)

        if record is None:
            return None

        lines = [
            OrderLine(
                product_id=item["product_id"],
                quantity=item["quantity"],
                unit_price=Money(
                    Decimal(item["unit_price"]),
                    item["currency"]
                )
            )
            for item in record["lines"]
        ]

        return Order(
            order_id=record["order_id"],
            customer_id=record["customer_id"],
            lines=lines,
            status=OrderStatus(record["status"]),
            version=record["version"]
        )

    def _read_all(self) -> dict:
        if not self.path.exists():
            return {}

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InfrastructureError(
                "Order storage is unavailable or corrupted."
            ) from exc


class SimulatedPaymentGateway:
    """Demonstration adapter for a payment provider."""

    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.processed: set[str] = set()

    def charge(self, order_id: str, amount: Money) -> bool:
        if order_id in self.processed:
            return True

        if not self.should_succeed:
            return False

        self.processed.add(order_id)
        logger.info(
            "Payment authorized: %s %s",
            amount.amount,
            amount.currency
        )

        return True


class ConsoleEventPublisher:
    def publish(self, event: dict) -> None:
        logger.info("Application event: %s", event)


# ============================================================
# 5. ARCHITECTURAL DEPENDENCY VALIDATION
# ============================================================

class Layer(Enum):
    DOMAIN = "domain"
    APPLICATION = "application"
    ADAPTER = "adapter"
    INFRASTRUCTURE = "infrastructure"


ALLOWED_DEPENDENCIES = {
    Layer.DOMAIN: set(),
    Layer.APPLICATION: {Layer.DOMAIN},
    Layer.ADAPTER: {Layer.APPLICATION, Layer.DOMAIN},
    Layer.INFRASTRUCTURE: {
        Layer.APPLICATION,
        Layer.DOMAIN,
        Layer.ADAPTER
    }
}


@dataclass
class Dependency:
    source: str
    target: str
    source_layer: Layer
    target_layer: Layer


class ArchitectureValidator:

    @staticmethod
    def validate(
        dependencies: list[Dependency]
    ) -> list[str]:

        violations = []

        for dependency in dependencies:
            allowed = ALLOWED_DEPENDENCIES[
                dependency.source_layer
            ]

            if dependency.target_layer not in allowed:
                violations.append(
                    f"{dependency.source} ({dependency.source_layer.value}) "
                    f"must not depend on {dependency.target} "
                    f"({dependency.target_layer.value})"
                )

        return violations

    @staticmethod
    def detect_cycles(
        graph: dict[str, list[str]]
    ) -> list[list[str]]:

        visited = set()
        active = set()
        stack = []
        cycles = []

        def visit(node: str):
            if node in active:
                index = stack.index(node)
                cycles.append(stack[index:] + [node])
                return

            if node in visited:
                return

            visited.add(node)
            active.add(node)
            stack.append(node)

            for neighbor in graph.get(node, []):
                visit(neighbor)

            stack.pop()
            active.remove(node)

        for node in graph:
            visit(node)

        return cycles


# ============================================================
# 6. TESTING AND DEMONSTRATION
# ============================================================

def demonstrate_domain_rules():
    try:
        Money(Decimal("-10"))
        raise AssertionError("Negative money should be rejected.")
    except DomainError:
        pass

    try:
        Money(Decimal("10")).add(
            Money(Decimal("5"), "USD")
        )
        raise AssertionError("Currency mismatch should fail.")
    except DomainError:
        pass

    try:
        OrderLine(
            product_id="ITEM-1",
            quantity=0,
            unit_price=Money(Decimal("100"))
        )
        raise AssertionError("Zero quantity should fail.")
    except DomainError:
        pass


def demonstrate_architecture():
    dependencies = [
        Dependency(
            "application.use_cases",
            "domain.entities",
            Layer.APPLICATION,
            Layer.DOMAIN
        ),
        Dependency(
            "infrastructure.database",
            "application.ports",
            Layer.INFRASTRUCTURE,
            Layer.APPLICATION
        ),
        Dependency(
            "domain.entities",
            "infrastructure.database",
            Layer.DOMAIN,
            Layer.INFRASTRUCTURE
        )
    ]

    violations = ArchitectureValidator.validate(dependencies)

    assert len(violations) == 1

    for violation in violations:
        print("Architecture violation:", violation)

    graph = {
        "domain": ["application"],
        "application": ["adapter"],
        "adapter": ["domain"]
    }

    cycles = ArchitectureValidator.detect_cycles(graph)

    assert len(cycles) == 1

    print("Circular dependency:", cycles[0])


def demonstrate_order_workflow():
    repository = InMemoryOrderRepository()
    payment = SimulatedPaymentGateway()
    publisher = ConsoleEventPublisher()

    place_order = PlaceOrder(
        repository=repository,
        payment_gateway=payment,
        event_publisher=publisher
    )

    lines = [
        OrderLine(
            "LAPTOP-001",
            1,
            Money(Decimal("65000.00"))
        ),
        OrderLine(
            "MOUSE-001",
            2,
            Money(Decimal("750.00"))
        )
    ]

    order = place_order.execute("CUSTOMER-100", lines)

    assert order.status == OrderStatus.PAID
    assert order.total().amount == Decimal("66500.00")

    print("\nSuccessful order")
    print("Order ID:", order.order_id)
    print("Customer:", order.customer_id)
    print("Total:", order.total())
    print("Status:", order.status.value)

    cancel_order = CancelOrder(repository)

    try:
        cancel_order.execute(order.order_id)
        raise AssertionError("Paid order cancellation must fail.")
    except DomainError:
        print("Paid order cancellation correctly rejected.")

    failed_repository = InMemoryOrderRepository()

    failed_use_case = PlaceOrder(
        repository=failed_repository,
        payment_gateway=SimulatedPaymentGateway(False),
        event_publisher=publisher
    )

    try:
        failed_use_case.execute("CUSTOMER-200", lines)
    except ApplicationError:
        failed_orders = failed_repository.all()

        assert len(failed_orders) == 1
        assert failed_orders[0].status == OrderStatus.CANCELLED

        print("Payment failure handled correctly.")


def demonstrate_file_persistence():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "orders.json"

        repository = FileOrderRepository(path)

        order = Order(
            order_id="ORDER-PERSIST-001",
            customer_id="CUSTOMER-300",
            lines=[
                OrderLine(
                    "BOOK-001",
                    2,
                    Money(Decimal("450"))
                )
            ]
        )

        repository.save(order)

        restored = repository.get("ORDER-PERSIST-001")

        assert restored is not None
        assert restored.total().amount == Decimal("900")

        print("File persistence verified.")


def main():
    print("=" * 65)
    print("CLEAN ARCHITECTURE AND DEPENDENCY INVERSION")
    print("=" * 65)

    demonstrate_domain_rules()
    demonstrate_architecture()
    demonstrate_order_workflow()
    demonstrate_file_persistence()

    print("\nAll demonstrations completed successfully.")


if __name__ == "__main__":
    main()
