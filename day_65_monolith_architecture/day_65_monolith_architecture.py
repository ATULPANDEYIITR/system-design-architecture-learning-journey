#!/usr/bin/env python3
"""
Monolith Architecture: Executable Architecture Simulation

Demonstrates:
- Single deployable application
- Internal modules and shared database
- Module-to-module communication
- Request processing and transactions
- Horizontal and vertical scaling
- Performance monitoring
- Failure propagation
- Advantages and architectural limitations
"""

from __future__ import annotations

import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModuleName(Enum):
    USERS = "users"
    INVENTORY = "inventory"
    ORDERS = "orders"
    PAYMENTS = "payments"


class OrderStatus(Enum):
    CREATED = "created"
    PAID = "paid"
    FAILED = "failed"


class ArchitectureError(Exception):
    pass


class ValidationError(ArchitectureError):
    pass


class InsufficientStockError(ArchitectureError):
    pass


@dataclass
class Product:
    product_id: int
    name: str
    price: float
    stock: int

    def __post_init__(self):
        if self.product_id <= 0 or self.price < 0 or self.stock < 0:
            raise ValidationError("Invalid product information")


@dataclass
class Order:
    order_id: str
    user_id: int
    product_id: int
    quantity: int
    total: float
    status: OrderStatus = OrderStatus.CREATED


@dataclass
class ApplicationMetrics:
    requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    module_calls: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    response_times: list[float] = field(default_factory=list)

    def record(self, duration: float, success: bool):
        self.requests += 1
        self.successful_requests += int(success)
        self.failed_requests += int(not success)
        self.response_times.append(duration)

    def report(self) -> dict[str, Any]:
        average = (
            statistics.mean(self.response_times)
            if self.response_times else 0
        )
        return {
            "requests": self.requests,
            "successful": self.successful_requests,
            "failed": self.failed_requests,
            "success_rate": round(
                self.successful_requests / self.requests * 100, 2
            ) if self.requests else 0,
            "average_response_ms": round(average * 1000, 3),
            "module_calls": dict(self.module_calls),
        }


class MonolithDatabase:
    """One logical database shared by application modules."""

    def __init__(self):
        self.users = {}
        self.products = {}
        self.orders = {}
        self.payments = {}

    def snapshot(self):
        return (
            {k: v.copy() for k, v in self.products.items()},
            {k: v for k, v in self.orders.items()},
            self.payments.copy(),
        )

    def restore(self, snapshot):
        self.products, self.orders, self.payments = snapshot


class UserModule:

    def __init__(self, database):
        self.database = database

    def register(self, user_id: int, email: str):
        if user_id <= 0 or "@" not in email:
            raise ValidationError("Invalid user registration")
        if user_id in self.database.users:
            raise ValidationError("User already exists")
        self.database.users[user_id] = email


class InventoryModule:

    def __init__(self, database):
        self.database = database

    def add_product(self, product: Product):
        if product.product_id in self.database.products:
            raise ValidationError("Product already exists")
        self.database.products[product.product_id] = product

    def reserve(self, product_id: int, quantity: int):
        if quantity <= 0:
            raise ValidationError("Quantity must be positive")

        product = self.database.products.get(product_id)

        if product is None:
            raise ValidationError("Product does not exist")

        if product.stock < quantity:
            raise InsufficientStockError("Insufficient inventory")

        product.stock -= quantity
        return product.price * quantity


class PaymentModule:

    def __init__(self, database):
        self.database = database

    def charge(self, order_id: str, amount: float):
        if amount <= 0:
            raise ValidationError("Invalid payment amount")

        # An order ID acts as an idempotency key.
        if order_id in self.database.payments:
            return self.database.payments[order_id]

        payment_id = str(uuid.uuid4())

        self.database.payments[order_id] = {
            "payment_id": payment_id,
            "amount": amount,
            "status": "completed",
        }

        return self.database.payments[order_id]


class OrderModule:

    def __init__(self, database, inventory, payments, metrics):
        self.database = database
        self.inventory = inventory
        self.payments = payments
        self.metrics = metrics

    def create_order(self, user_id: int, product_id: int, quantity: int):
        start = time.perf_counter()
        success = False
        snapshot = self.database.snapshot()

        try:
            if user_id not in self.database.users:
                raise ValidationError("Unknown user")

            self.metrics.module_calls[ModuleName.INVENTORY.value] += 1
            total = self.inventory.reserve(product_id, quantity)

            order_id = str(uuid.uuid4())

            order = Order(
                order_id=order_id,
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
                total=total,
            )

            self.database.orders[order_id] = order

            self.metrics.module_calls[ModuleName.PAYMENTS.value] += 1
            self.payments.charge(order_id, total)

            order.status = OrderStatus.PAID
            success = True

            return order

        except Exception:
            # In-memory rollback illustrates atomic application behavior.
            self.database.restore(snapshot)
            raise

        finally:
            self.metrics.record(
                time.perf_counter() - start,
                success
            )


class MonolithicApplication:

    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        self.database = MonolithDatabase()
        self.metrics = ApplicationMetrics()

        self.users = UserModule(self.database)
        self.inventory = InventoryModule(self.database)
        self.payments = PaymentModule(self.database)
        self.orders = OrderModule(
            self.database,
            self.inventory,
            self.payments,
            self.metrics,
        )

    def health_check(self):
        return {
            "instance": self.instance_id,
            "status": "healthy",
            "modules": [module.value for module in ModuleName],
            "database": "connected",
        }


class MonolithCluster:
    """Multiple application instances sharing one database."""

    def __init__(self, instances: int = 1):
        if instances < 1:
            raise ValidationError("At least one instance is required")

        self.database = MonolithDatabase()
        self.instances = [
            MonolithicApplication(f"instance-{i + 1}")
            for i in range(instances)
        ]

        # All application instances share the logical database.
        for instance in self.instances:
            instance.database = self.database
            instance.users.database = self.database
            instance.inventory.database = self.database
            instance.payments.database = self.database
            instance.orders.database = self.database

    def scale_out(self, additional_instances: int):
        if additional_instances <= 0:
            raise ValidationError("Additional instances must be positive")

        start = len(self.instances)

        for i in range(additional_instances):
            instance = MonolithicApplication(
                f"instance-{start + i + 1}"
            )
            instance.database = self.database
            instance.users.database = self.database
            instance.inventory.database = self.database
            instance.payments.database = self.database
            instance.orders.database = self.database
            self.instances.append(instance)


def demonstrate():
    print("MONOLITH ARCHITECTURE SIMULATION")
    print("=" * 50)

    application = MonolithicApplication("production-instance-1")

    application.users.register(101, "customer@example.com")

    application.inventory.add_product(
        Product(1, "Enterprise Server", 1250.00, 10)
    )

    print("\nApplication health:")
    print(application.health_check())

    print("\nSuccessful order:")
    order = application.orders.create_order(101, 1, 2)
    print(order)

    print("\nInventory after order:")
    print(application.database.products[1].stock)

    print("\nFailed order:")
    try:
        application.orders.create_order(101, 1, 100)
    except ArchitectureError as error:
        print(type(error).__name__, str(error))

    print("\nInventory after failed transaction:")
    print(application.database.products[1].stock)

    print("\nInvalid request:")
    try:
        application.orders.create_order(999, 1, 1)
    except ArchitectureError as error:
        print(type(error).__name__, str(error))

    print("\nApplication metrics:")
    print(application.metrics.report())

    print("\nHorizontal scaling:")
    cluster = MonolithCluster(instances=1)
    cluster.scale_out(2)
    print("Application instances:", len(cluster.instances))
    print("Shared database:", all(
        instance.database is cluster.database
        for instance in cluster.instances
    ))

    print("\nArchitectural characteristics:")
    characteristics = {
        "Deployment": "Single application deployment",
        "Communication": "In-process module calls",
        "Database": "Shared logical database",
        "Vertical scaling": "Increase CPU and memory",
        "Horizontal scaling": "Run multiple complete instances",
        "Independent module deployment": False,
        "Failure isolation": "Limited",
        "Operational complexity": "Generally lower initially",
    }

    for key, value in characteristics.items():
        print(f"{key}: {value}")

    assert application.database.products[1].stock == 8
    assert len(application.database.orders) == 1
    assert application.database.orders[order.order_id].status == OrderStatus.PAID
    assert len(cluster.instances) == 3

    print("\nAll architecture checks passed.")


if __name__ == "__main__":
    demonstrate()
