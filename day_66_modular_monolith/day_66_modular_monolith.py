"""
Modular Monolith: Module Boundaries, Architecture, and Migration Strategy

A runnable order-management application demonstrating:
- Explicit module boundaries
- Domain ownership
- Application services
- Dependency control
- Domain events
- Transaction management
- Cross-module communication
- Architecture validation
- Strangler migration strategy
- Failure handling
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from collections import defaultdict
from typing import Callable
from uuid import uuid4


# ============================================================
# SHARED KERNEL
# ============================================================

class DomainError(Exception):
    """Base exception for domain-level failures."""


class ValidationError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class InsufficientStockError(DomainError):
    pass


class PaymentError(DomainError):
    pass


class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    occurred_at: datetime
    payload: dict


class EventBus:
    """In-process event dispatcher.

    Subscribers receive events synchronously. Production systems
    should use a transactional outbox for reliable publication.
    """

    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable):
        if not callable(handler):
            raise ValidationError("Event handler must be callable.")
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent):
        for handler in tuple(self._handlers[event.event_type]):
            handler(event)


# ============================================================
# INVENTORY MODULE
# Owns stock quantities and stock reservations.
# ============================================================

@dataclass
class Product:
    product_id: str
    name: str
    unit_price: Decimal
    available_quantity: int

    def __post_init__(self):
        if not self.product_id or not self.name.strip():
            raise ValidationError("Product ID and name are required.")
        if self.unit_price <= 0:
            raise ValidationError("Product price must be positive.")
        if self.available_quantity < 0:
            raise ValidationError("Stock cannot be negative.")


@dataclass
class StockReservation:
    reservation_id: str
    product_id: str
    quantity: int
    active: bool = True


class InventoryModule:

    def __init__(self):
        self.products = {}
        self.reservations = {}

    def add_product(self, product: Product):
        if product.product_id in self.products:
            raise ValidationError("Duplicate product.")
        self.products[product.product_id] = product

    def get_product(self, product_id: str) -> Product:
        product = self.products.get(product_id)
        if product is None:
            raise NotFoundError(f"Product {product_id} not found.")
        return product

    def reserve(self, product_id: str, quantity: int):
        if quantity <= 0:
            raise ValidationError("Reservation quantity must be positive.")

        product = self.get_product(product_id)

        if product.available_quantity < quantity:
            raise InsufficientStockError(
                f"Insufficient stock for {product.name}."
            )

        product.available_quantity -= quantity

        reservation = StockReservation(
            reservation_id=str(uuid4()),
            product_id=product_id,
            quantity=quantity
        )

        self.reservations[reservation.reservation_id] = reservation
        return reservation

    def release(self, reservation_id: str):
        reservation = self.reservations.get(reservation_id)

        if reservation is None:
            raise NotFoundError("Reservation not found.")

        if not reservation.active:
            return

        product = self.get_product(reservation.product_id)
        product.available_quantity += reservation.quantity
        reservation.active = False

    def commit_reservation(self, reservation_id: str):
        reservation = self.reservations.get(reservation_id)

        if reservation is None or not reservation.active:
            raise ValidationError("Invalid active reservation.")

        reservation.active = False


# ============================================================
# PAYMENT MODULE
# Owns payment records and payment state.
# ============================================================

class PaymentStatus(Enum):
    AUTHORIZED = "authorized"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class Payment:
    payment_id: str
    order_id: str
    amount: Decimal
    status: PaymentStatus


class PaymentModule:

    def __init__(self):
        self.payments = {}

    def authorize(self, order_id: str, amount: Decimal):
        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")

        payment = Payment(
            payment_id=str(uuid4()),
            order_id=order_id,
            amount=amount,
            status=PaymentStatus.AUTHORIZED
        )

        self.payments[payment.payment_id] = payment
        return payment

    def refund(self, payment_id: str):
        payment = self.payments.get(payment_id)

        if payment is None:
            raise NotFoundError("Payment not found.")

        if payment.status != PaymentStatus.AUTHORIZED:
            raise PaymentError("Payment cannot be refunded.")

        payment.status = PaymentStatus.REFUNDED


# ============================================================
# ORDER MODULE
# Owns order creation and order lifecycle.
# ============================================================

@dataclass
class Order:
    order_id: str
    customer_id: str
    product_id: str
    quantity: int
    total_amount: Decimal
    reservation_id: str
    payment_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class OrderModule:

    def __init__(self, inventory, payments, event_bus):
        self.inventory = inventory
        self.payments = payments
        self.event_bus = event_bus
        self.orders = {}

    def create_order(self, customer_id: str, product_id: str, quantity: int):
        if not customer_id.strip():
            raise ValidationError("Customer ID is required.")

        if quantity <= 0:
            raise ValidationError("Quantity must be positive.")

        product = self.inventory.get_product(product_id)
        total = product.unit_price * quantity

        # Preserve inventory state if payment authorization fails.
        reservation = self.inventory.reserve(product_id, quantity)

        order = Order(
            order_id=str(uuid4()),
            customer_id=customer_id,
            product_id=product_id,
            quantity=quantity,
            total_amount=total,
            reservation_id=reservation.reservation_id
        )

        try:
            payment = self.payments.authorize(order.order_id, total)
            order.payment_id = payment.payment_id
            order.status = OrderStatus.CONFIRMED

            self.inventory.commit_reservation(reservation.reservation_id)
            self.orders[order.order_id] = order

            self.event_bus.publish(
                DomainEvent(
                    event_id=str(uuid4()),
                    event_type="OrderConfirmed",
                    aggregate_id=order.order_id,
                    occurred_at=datetime.now(timezone.utc),
                    payload={
                        "order_id": order.order_id,
                        "customer_id": customer_id,
                        "amount": str(total)
                    }
                )
            )

            return order

        except Exception:
            self.inventory.release(reservation.reservation_id)
            raise

    def cancel_order(self, order_id: str):
        order = self.orders.get(order_id)

        if order is None:
            raise NotFoundError("Order not found.")

        if order.status == OrderStatus.CANCELLED:
            return order

        if order.status != OrderStatus.CONFIRMED:
            raise ValidationError("Order cannot be cancelled.")

        self.payments.refund(order.payment_id)
        order.status = OrderStatus.CANCELLED

        self.event_bus.publish(
            DomainEvent(
                event_id=str(uuid4()),
                event_type="OrderCancelled",
                aggregate_id=order.order_id,
                occurred_at=datetime.now(timezone.utc),
                payload={"order_id": order.order_id}
            )
        )

        return order


# ============================================================
# NOTIFICATION MODULE
# Reacts to events without accessing order internals.
# ============================================================

class NotificationModule:

    def __init__(self, event_bus):
        self.messages = []

        event_bus.subscribe(
            "OrderConfirmed",
            self.handle_order_confirmed
        )

        event_bus.subscribe(
            "OrderCancelled",
            self.handle_order_cancelled
        )

    def handle_order_confirmed(self, event):
        self.messages.append({
            "type": "confirmation",
            "order_id": event.aggregate_id,
            "message": "Order successfully confirmed."
        })

    def handle_order_cancelled(self, event):
        self.messages.append({
            "type": "cancellation",
            "order_id": event.aggregate_id,
            "message": "Order successfully cancelled."
        })


# ============================================================
# MODULAR MONOLITH APPLICATION
# ============================================================

class ModularMonolith:

    def __init__(self):
        self.event_bus = EventBus()
        self.inventory = InventoryModule()
        self.payments = PaymentModule()

        self.notifications = NotificationModule(self.event_bus)

        self.orders = OrderModule(
            self.inventory,
            self.payments,
            self.event_bus
        )


# ============================================================
# ARCHITECTURE GOVERNANCE
# ============================================================

class ArchitectureValidator:

    ALLOWED_DEPENDENCIES = {
        "orders": {"inventory", "payments", "shared"},
        "inventory": {"shared"},
        "payments": {"shared"},
        "notifications": {"shared"},
    }

    @classmethod
    def validate(cls, dependencies):
        violations = []

        for source, targets in dependencies.items():
            allowed = cls.ALLOWED_DEPENDENCIES.get(source, set())

            for target in targets:
                if target not in allowed:
                    violations.append(
                        f"{source} cannot depend on {target}"
                    )

        return violations


# ============================================================
# MIGRATION STRATEGY
# ============================================================

class MigrationStage(Enum):
    MONOLITH = "monolith"
    BOUNDARIES_DEFINED = "boundaries_defined"
    MODULE_ISOLATED = "module_isolated"
    API_STABILIZED = "api_stabilized"
    EXTERNALIZED = "externalized"


@dataclass
class ModuleMigration:
    module_name: str
    stage: MigrationStage = MigrationStage.MONOLITH
    external_endpoint: str | None = None

    TRANSITIONS = {
        MigrationStage.MONOLITH: MigrationStage.BOUNDARIES_DEFINED,
        MigrationStage.BOUNDARIES_DEFINED: MigrationStage.MODULE_ISOLATED,
        MigrationStage.MODULE_ISOLATED: MigrationStage.API_STABILIZED,
        MigrationStage.API_STABILIZED: MigrationStage.EXTERNALIZED,
    }

    def advance(self, endpoint=None):
        next_stage = self.TRANSITIONS.get(self.stage)

        if next_stage is None:
            raise ValidationError("Module has completed migration.")

        if next_stage == MigrationStage.EXTERNALIZED:
            if not endpoint or not endpoint.startswith("https://"):
                raise ValidationError(
                    "Externalized modules require an HTTPS endpoint."
                )
            self.external_endpoint = endpoint

        self.stage = next_stage


# ============================================================
# EXECUTABLE DEMONSTRATION
# ============================================================

def main():
    app = ModularMonolith()

    app.inventory.add_product(
        Product(
            product_id="P100",
            name="Enterprise Laptop",
            unit_price=Decimal("75000.00"),
            available_quantity=10
        )
    )

    order = app.orders.create_order(
        customer_id="C100",
        product_id="P100",
        quantity=2
    )

    print("ORDER CREATED")
    print("Order ID:", order.order_id)
    print("Amount:", order.total_amount)
    print("Status:", order.status.value)

    print("\nINVENTORY")
    print(
        "Available quantity:",
        app.inventory.get_product("P100").available_quantity
    )

    print("\nNOTIFICATIONS")
    for message in app.notifications.messages:
        print(message)

    app.orders.cancel_order(order.order_id)

    print("\nAFTER CANCELLATION")
    print("Order status:", order.status.value)
    print("Payment status:",
          app.payments.payments[order.payment_id].status.value)

    print("\nARCHITECTURE VALIDATION")
    dependencies = {
        "orders": {"inventory", "payments", "shared"},
        "inventory": {"shared"},
        "payments": {"shared"},
        "notifications": {"shared"},
    }

    violations = ArchitectureValidator.validate(dependencies)
    assert not violations
    print("All module dependencies are valid.")

    invalid_dependencies = {
        "inventory": {"orders"}
    }

    assert ArchitectureValidator.validate(invalid_dependencies)

    print("\nMIGRATION")
    migration = ModuleMigration("notifications")

    migration.advance()
    migration.advance()
    migration.advance()
    migration.advance("https://notifications.example.com")

    print("Module:", migration.module_name)
    print("Stage:", migration.stage.value)
    print("Endpoint:", migration.external_endpoint)

    # Edge-case validation.
    try:
        app.orders.create_order("C101", "P100", 100)
    except InsufficientStockError as error:
        print("\nEXPECTED FAILURE:", error)

    assert app.inventory.get_product("P100").available_quantity == 8

    print("\nAll demonstrations completed.")


if __name__ == "__main__":
    main()
