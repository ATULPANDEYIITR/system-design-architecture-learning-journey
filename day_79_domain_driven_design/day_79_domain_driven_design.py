from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from threading import RLock
from typing import Any
from uuid import UUID, uuid4
import json


# ============================================================
# DOMAIN-DRIVEN DESIGN: BOUNDED CONTEXTS, AGGREGATES, ENTITIES
# ============================================================

class DomainError(Exception):
    """Base exception for domain-related failures."""


class ValidationError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ConcurrencyError(DomainError):
    pass


class ContextType(Enum):
    CATALOG = "catalog"
    ORDER = "order"
    INVENTORY = "inventory"
    BILLING = "billing"


class OrderStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class StockStatus(Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"


# ============================================================
# SHARED KERNEL: IDENTIFIERS AND VALUE OBJECTS
# ============================================================

@dataclass(frozen=True)
class ProductId:
    value: UUID

    @classmethod
    def new(cls) -> ProductId:
        return cls(uuid4())


@dataclass(frozen=True)
class OrderId:
    value: UUID

    @classmethod
    def new(cls) -> OrderId:
        return cls(uuid4())


@dataclass(frozen=True)
class CustomerId:
    value: UUID

    @classmethod
    def new(cls) -> CustomerId:
        return cls(uuid4())


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "INR"

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise ValidationError("Money must be finite.")
        if self.amount < 0:
            raise ValidationError("Money cannot be negative.")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValidationError("Currency must be a three-letter code.")
        object.__setattr__(self, "currency", self.currency.upper())

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, quantity: int) -> Money:
        if not isinstance(quantity, int) or isinstance(quantity, bool):
            raise ValidationError("Quantity must be an integer.")
        if quantity < 0:
            raise ValidationError("Quantity cannot be negative.")
        return Money(self.amount * quantity, self.currency)

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValidationError("Currency mismatch.")


@dataclass(frozen=True)
class ProductSnapshot:
    product_id: ProductId
    name: str
    unit_price: Money


# ============================================================
# DOMAIN EVENTS
# ============================================================

@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID
    aggregate_id: UUID
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]

    @classmethod
    def create(
        cls,
        aggregate_id: UUID,
        event_type: str,
        payload: dict[str, Any]
    ) -> DomainEvent:
        return cls(
            uuid4(),
            aggregate_id,
            event_type,
            datetime.now(timezone.utc),
            payload
        )


# ============================================================
# AGGREGATE ROOT BASE CLASS
# ============================================================

class AggregateRoot:
    def __init__(self) -> None:
        self._version = 0
        self._events: list[DomainEvent] = []

    @property
    def version(self) -> int:
        return self._version

    @property
    def domain_events(self) -> tuple[DomainEvent, ...]:
        return tuple(self._events)

    def _raise_event(
        self,
        event_type: str,
        payload: dict[str, Any]
    ) -> None:
        self._events.append(
            DomainEvent.create(self.id.value, event_type, payload)
        )
        self._version += 1

    def clear_events(self) -> None:
        self._events.clear()


# ============================================================
# BOUNDED CONTEXT 1: PRODUCT CATALOG
# ============================================================

@dataclass
class Product:
    """Product entity belonging exclusively to Catalog Context."""

    id: ProductId
    name: str
    price: Money
    active: bool = True
    version: int = 0

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError("Product name is required.")

    def change_price(self, new_price: Money) -> None:
        if new_price.currency != self.price.currency:
            raise ValidationError("Currency cannot change implicitly.")
        self.price = new_price
        self.version += 1

    def deactivate(self) -> None:
        self.active = False
        self.version += 1

    def snapshot(self) -> ProductSnapshot:
        if not self.active:
            raise DomainError("Inactive products cannot be purchased.")
        return ProductSnapshot(self.id, self.name, self.price)


class CatalogContext:
    def __init__(self) -> None:
        self._products: dict[ProductId, Product] = {}
        self._lock = RLock()

    def register_product(self, product: Product) -> None:
        with self._lock:
            if product.id in self._products:
                raise DomainError("Product already exists.")
            self._products[product.id] = product

    def get_product(self, product_id: ProductId) -> Product:
        with self._lock:
            product = self._products.get(product_id)
            if product is None:
                raise NotFoundError("Product not found.")
            return product

    def get_snapshot(self, product_id: ProductId) -> ProductSnapshot:
        return self.get_product(product_id).snapshot()


# ============================================================
# BOUNDED CONTEXT 2: INVENTORY
# ============================================================

@dataclass
class InventoryItem:
    """Inventory entity with independently managed stock."""

    product_id: ProductId
    available_quantity: int
    reserved_quantity: int = 0

    def __post_init__(self) -> None:
        if self.available_quantity < 0 or self.reserved_quantity < 0:
            raise ValidationError("Stock cannot be negative.")

    def reserve(self, quantity: int) -> None:
        if quantity <= 0:
            raise ValidationError("Reservation must be positive.")
        if quantity > self.available_quantity:
            raise DomainError("Insufficient available inventory.")
        self.available_quantity -= quantity
        self.reserved_quantity += quantity

    def release(self, quantity: int) -> None:
        if quantity <= 0 or quantity > self.reserved_quantity:
            raise DomainError("Invalid inventory release.")
        self.reserved_quantity -= quantity
        self.available_quantity += quantity


class InventoryContext:
    def __init__(self) -> None:
        self._items: dict[ProductId, InventoryItem] = {}
        self._lock = RLock()

    def add_stock(self, product_id: ProductId, quantity: int) -> None:
        if quantity <= 0:
            raise ValidationError("Stock quantity must be positive.")

        with self._lock:
            if product_id in self._items:
                self._items[product_id].available_quantity += quantity
            else:
                self._items[product_id] = InventoryItem(
                    product_id, quantity
                )

    def reserve(
        self,
        product_id: ProductId,
        quantity: int
    ) -> None:
        with self._lock:
            item = self._items.get(product_id)
            if item is None:
                raise NotFoundError("Inventory item not found.")
            item.reserve(quantity)

    def release(
        self,
        product_id: ProductId,
        quantity: int
    ) -> None:
        with self._lock:
            item = self._items.get(product_id)
            if item is None:
                raise NotFoundError("Inventory item not found.")
            item.release(quantity)

    def get_item(self, product_id: ProductId) -> InventoryItem:
        with self._lock:
            item = self._items.get(product_id)
            if item is None:
                raise NotFoundError("Inventory item not found.")
            return item


# ============================================================
# BOUNDED CONTEXT 3: ORDER MANAGEMENT
# ============================================================

@dataclass
class OrderLine:
    """Child entity: its lifecycle belongs to the Order aggregate."""

    product: ProductSnapshot
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValidationError("Order quantity must be positive.")

    @property
    def subtotal(self) -> Money:
        return self.product.unit_price * self.quantity


class Order(AggregateRoot):
    """Order aggregate root controlling its internal entities."""

    def __init__(self, customer_id: CustomerId) -> None:
        super().__init__()
        self.id = OrderId.new()
        self.customer_id = customer_id
        self.status = OrderStatus.DRAFT
        self._lines: dict[ProductId, OrderLine] = {}
        self.created_at = datetime.now(timezone.utc)
        self._raise_event(
            "OrderCreated",
            {"customer_id": str(customer_id.value)}
        )

    @property
    def lines(self) -> tuple[OrderLine, ...]:
        return tuple(self._lines.values())

    @property
    def total(self) -> Money:
        if not self._lines:
            return Money(Decimal("0"), "INR")

        currency = self.lines[0].product.unit_price.currency
        result = Money(Decimal("0"), currency)

        for line in self._lines.values():
            result = result + line.subtotal

        return result

    def add_product(
        self,
        snapshot: ProductSnapshot,
        quantity: int
    ) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainError("Only draft orders can be modified.")

        if quantity <= 0:
            raise ValidationError("Quantity must be positive.")

        existing = self._lines.get(snapshot.product_id)

        if existing:
            if existing.product.unit_price != snapshot.unit_price:
                raise DomainError(
                    "Price changed. Refresh the product snapshot."
                )
            existing.quantity += quantity
        else:
            if self._lines:
                current_currency = self.lines[0].product.unit_price.currency
                if current_currency != snapshot.unit_price.currency:
                    raise ValidationError(
                        "An order cannot mix currencies."
                    )
            self._lines[snapshot.product_id] = OrderLine(
                snapshot, quantity
            )

        self._version += 1

    def submit(self) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainError("Order is not in draft state.")
        if not self._lines:
            raise DomainError("An empty order cannot be submitted.")

        self.status = OrderStatus.SUBMITTED
        self._raise_event(
            "OrderSubmitted",
            {
                "order_id": str(self.id.value),
                "total": str(self.total.amount),
                "currency": self.total.currency,
                "items": [
                    {
                        "product_id": str(line.product.product_id.value),
                        "quantity": line.quantity
                    }
                    for line in self.lines
                ]
            }
        )

    def confirm(self) -> None:
        if self.status != OrderStatus.SUBMITTED:
            raise DomainError("Only submitted orders can be confirmed.")
        self.status = OrderStatus.CONFIRMED
        self._raise_event("OrderConfirmed", {})

    def cancel(self) -> None:
        if self.status not in (
            OrderStatus.DRAFT,
            OrderStatus.SUBMITTED
        ):
            raise DomainError("This order cannot be cancelled.")

        self.status = OrderStatus.CANCELLED
        self._raise_event("OrderCancelled", {})


class OrderContext:
    def __init__(self) -> None:
        self._orders: dict[OrderId, Order] = {}
        self._lock = RLock()

    def create_order(self, customer_id: CustomerId) -> Order:
        order = Order(customer_id)
        with self._lock:
            self._orders[order.id] = order
        return order

    def get_order(self, order_id: OrderId) -> Order:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise NotFoundError("Order not found.")
            return order


# ============================================================
# BOUNDED CONTEXT 4: BILLING
# ============================================================

@dataclass
class Invoice:
    invoice_id: UUID
    order_id: OrderId
    amount: Money
    paid: bool = False

    def mark_paid(self) -> None:
        if self.paid:
            raise DomainError("Invoice has already been paid.")
        self.paid = True


class BillingContext:
    def __init__(self) -> None:
        self._invoices: dict[OrderId, Invoice] = {}
        self._lock = RLock()

    def create_invoice(
        self,
        order_id: OrderId,
        amount: Money
    ) -> Invoice:
        with self._lock:
            if order_id in self._invoices:
                raise DomainError("Invoice already exists.")

            invoice = Invoice(uuid4(), order_id, amount)
            self._invoices[order_id] = invoice
            return invoice

    def get_invoice(self, order_id: OrderId) -> Invoice:
        with self._lock:
            invoice = self._invoices.get(order_id)
            if invoice is None:
                raise NotFoundError("Invoice not found.")
            return invoice


# ============================================================
# APPLICATION LAYER: USE CASE COORDINATION
# ============================================================

class EventBus:
    """In-process event dispatcher; production systems need persistence."""

    def __init__(self) -> None:
        self._handlers: dict[str, list] = {}

    def subscribe(self, event_type: str, handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(event.event_type, []):
            handler(event)


class OrderApplicationService:
    def __init__(
        self,
        catalog: CatalogContext,
        inventory: InventoryContext,
        orders: OrderContext,
        billing: BillingContext,
        event_bus: EventBus
    ) -> None:
        self.catalog = catalog
        self.inventory = inventory
        self.orders = orders
        self.billing = billing
        self.event_bus = event_bus

    def place_order(self, order: Order) -> Invoice:
        if order.status != OrderStatus.DRAFT:
            raise DomainError("Order must be a draft.")

        reserved: list[tuple[ProductId, int]] = []

        try:
            # Reserve all inventory before submitting the order.
            for line in order.lines:
                product_id = line.product.product_id
                self.inventory.reserve(product_id, line.quantity)
                reserved.append((product_id, line.quantity))

            order.submit()

            invoice = self.billing.create_invoice(
                order.id,
                order.total
            )

            # Publish only events generated by the successful operation.
            for event in order.domain_events:
                self.event_bus.publish(event)

            order.clear_events()
            return invoice

        except Exception:
            # Compensating action for reservations already completed.
            for product_id, quantity in reversed(reserved):
                self.inventory.release(product_id, quantity)
            raise


# ============================================================
# REPOSITORY PATTERN AND OPTIMISTIC CONCURRENCY
# ============================================================

class OrderRepository:
    def __init__(self) -> None:
        self._storage: dict[OrderId, Order] = {}
        self._versions: dict[OrderId, int] = {}
        self._lock = RLock()

    def save(
        self,
        order: Order,
        expected_version: int | None = None
    ) -> None:
        with self._lock:
            current = self._versions.get(order.id, 0)

            if expected_version is not None and current != expected_version:
                raise ConcurrencyError(
                    f"Version conflict: expected {expected_version}, "
                    f"found {current}."
                )

            self._storage[order.id] = order
            self._versions[order.id] = order.version

    def get(self, order_id: OrderId) -> Order:
        with self._lock:
            order = self._storage.get(order_id)
            if order is None:
                raise NotFoundError("Order not found.")
            return order


# ============================================================
# DEMONSTRATION AND VALIDATION
# ============================================================

def run_demonstration() -> None:
    catalog = CatalogContext()
    inventory = InventoryContext()
    orders = OrderContext()
    billing = BillingContext()
    event_bus = EventBus()

    repository = OrderRepository()

    product = Product(
        ProductId.new(),
        "Enterprise Security Appliance",
        Money(Decimal("45000.00"))
    )

    catalog.register_product(product)
    inventory.add_stock(product.id, 20)

    customer_id = CustomerId.new()
    order = orders.create_order(customer_id)

    snapshot = catalog.get_snapshot(product.id)
    order.add_product(snapshot, 2)

    repository.save(order, expected_version=0)

    print("BOUNDED CONTEXTS")
    print("Catalog:", product.name)
    print("Inventory:", inventory.get_item(product.id).available_quantity)
    print("Order:", order.id.value)
    print("Aggregate version:", order.version)
    print("Order total:", order.total.amount)

    service = OrderApplicationService(
        catalog,
        inventory,
        orders,
        billing,
        event_bus
    )

    invoice = service.place_order(order)

    print("\nORDER PROCESSING")
    print("Status:", order.status.value)
    print("Invoice:", invoice.invoice_id)
    print("Invoice amount:", invoice.amount.amount)
    print(
        "Available stock:",
        inventory.get_item(product.id).available_quantity
    )

    # Entity identity remains stable even when entity attributes change.
    original_id = product.id
    product.change_price(Money(Decimal("47000.00")))
    assert product.id == original_id

    # Existing order snapshots retain the original purchase price.
    assert order.total.amount == Decimal("90000.00")

    # Aggregate invariants reject invalid state transitions.
    try:
        order.submit()
    except DomainError as exc:
        print("\nExpected validation:", exc)

    try:
        inventory.reserve(product.id, 100)
    except DomainError as exc:
        print("Expected stock failure:", exc)

    # Independent contexts communicate through identifiers and events.
    print("\nDOMAIN EVENTS")
    for event in order.domain_events:
        print(event.event_type, event.aggregate_id)

    print("\nVALIDATION")
    assert order.status == OrderStatus.SUBMITTED
    assert invoice.amount.amount == Decimal("90000.00")
    assert inventory.get_item(product.id).reserved_quantity == 2

    print("All demonstration assertions passed.")


if __name__ == "__main__":
    run_demonstration()
