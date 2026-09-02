"""
SOFTWARE DESIGN VS SYSTEM DESIGN
LLD VS HLD, COMPONENT DESIGN, AND ARCHITECTURE DECISIONS

This program is a structured, executable study guide for understanding
software design and system design from foundational concepts to advanced
design reasoning.

The examples are intentionally written in plain Python so that the design
ideas can be understood without depending on external frameworks.

Major areas covered:

1. Software design and system design
2. LLD and HLD
3. Requirements and constraints
4. Abstraction and decomposition
5. Modules, components and services
6. Interfaces and contracts
7. Coupling and cohesion
8. Encapsulation
9. SOLID principles
10. Composition and inheritance
11. Dependency inversion
12. Design patterns
13. Component design
14. API design
15. Data ownership
16. Architecture styles
17. Layered architecture
18. Modular monoliths
19. Microservices
20. Event-driven architecture
21. Scalability
22. Reliability and fault tolerance
23. Caching
24. Queues and asynchronous processing
25. Databases and consistency
26. Transactions
27. Idempotency
28. Observability
29. Security considerations
30. Architecture decisions and trade-offs
31. Architecture Decision Records
32. Complete worked design example
33. LLD implementation of selected components
34. HLD reasoning for the same system
35. Design review questions

The program prints explanations and executes small demonstrations.
"""


# ============================================================
# 1. BASIC UTILITIES
# ============================================================

def title(text):
    print("\n" + "=" * 80)
    print(text.upper())
    print("=" * 80)


def section(text):
    print("\n" + "-" * 80)
    print(text)
    print("-" * 80)


def explain(text):
    print(text)


def bullet(text):
    print("  • " + text)


def example(text):
    print("\nEXAMPLE:")
    print(text)


# ============================================================
# 2. SOFTWARE DESIGN VS SYSTEM DESIGN
# ============================================================

title("1. Software Design vs System Design")

explain("""
Software design and system design are related, but they operate at
different levels of abstraction.

Software design primarily asks:

    How should the software itself be structured?

It deals with classes, modules, interfaces, functions, objects,
dependencies, responsibilities, data structures and implementation
boundaries.

System design asks a broader question:

    How should the complete system behave and operate?

It considers applications, databases, caches, message brokers,
load balancers, networking, storage, external services, users,
deployment, scalability, reliability and operational constraints.

A useful distinction is:

    Software design = internal structure of software.
    System design   = structure and behaviour of the complete system.

The two are not independent.

A poor high-level architecture can make low-level implementation
difficult. A poor low-level design can make a good architecture
hard to maintain.

The important skill is knowing at which level a design decision belongs.
""")

bullet("Software design focuses on code structure and responsibilities.")
bullet("System design focuses on system structure and operational behaviour.")
bullet("LLD normally operates closer to classes and components.")
bullet("HLD normally operates closer to services and infrastructure.")
bullet("HLD defines major boundaries; LLD defines detailed behaviour inside those boundaries.")


# ============================================================
# 3. LLD VS HLD
# ============================================================

title("2. LLD vs HLD")

explain("""
High-Level Design, or HLD, describes the major building blocks of a
system and how those blocks communicate.

Low-Level Design, or LLD, describes the internal structure and behaviour
of individual components.

HLD typically answers:

    What major components exist?
    Which database is used?
    Which service owns which responsibility?
    How do components communicate?
    Where is caching performed?
    Where are queues used?
    How does the system scale?
    What happens when a dependency fails?

LLD typically answers:

    Which classes exist?
    What methods do they expose?
    What interfaces are required?
    Which object owns a particular responsibility?
    How is validation performed?
    How are errors represented?
    How are dependencies injected?
    Which design pattern is appropriate?

Neither level is inherently more important.

HLD without LLD can result in vague architecture diagrams.

LLD without HLD can result in beautifully designed components that
do not fit together into a coherent system.
""")

section("HLD example")

example("""
An e-commerce system may have:

    Client
       |
       v
    API Gateway
       |
       +------ Product Service
       |
       +------ Order Service
       |
       +------ Payment Service
       |
       +------ Inventory Service
       |
       +------ Notification Service

Supporting infrastructure:

    PostgreSQL
    Redis
    Message Broker
    Object Storage
    Monitoring

This is HLD because it describes major system boundaries.
""")

section("LLD example")

example("""
Inside Order Service:

    Order
    OrderItem
    OrderRepository
    PaymentGateway
    InventoryGateway
    OrderService
    OrderValidator
    PricingService

This is LLD because it describes internal software structure.
""")


# ============================================================
# 4. ABSTRACTION LEVELS
# ============================================================

title("3. Abstraction Levels")

explain("""
Design can be understood as a hierarchy.

Level 1: Business requirements

    "A customer should be able to place an order."

Level 2: System responsibilities

    Customer Service
    Order Service
    Payment Service
    Inventory Service

Level 3: Component responsibilities

    OrderController
    OrderService
    OrderRepository
    PaymentClient

Level 4: Object responsibilities

    Order
    OrderItem
    Money
    Address

Level 5: Function-level implementation

    validate_quantity()
    calculate_total()
    reserve_inventory()

Moving downward increases implementation detail.

Moving upward increases architectural scope.

Good designers move between these levels deliberately rather than
mixing them together.
""")


# ============================================================
# 5. REQUIREMENTS BEFORE DESIGN
# ============================================================

title("4. Requirements Before Design")

explain("""
Design should begin with requirements rather than technology.

There are two broad categories.

Functional requirements describe what the system does.

Examples:

    User can create an account.
    User can place an order.
    User can cancel an order.
    User can receive a notification.

Non-functional requirements describe how the system should behave.

Examples:

    Response time below 200 ms for common reads.
    99.9% availability.
    Support 100,000 requests per second.
    Data must survive hardware failures.
    Sensitive information must be encrypted.

Non-functional requirements often determine architecture more strongly
than functional requirements.

The same business function can have completely different architectures
depending on scale, latency, consistency and availability requirements.
""")

requirements = {
    "functional": [
        "Create user",
        "Create order",
        "Process payment",
        "Reserve inventory",
        "Send notification"
    ],
    "non_functional": {
        "latency": "< 200 ms for normal reads",
        "availability": "99.9%",
        "scale": "100,000 requests per second",
        "security": "Encryption for sensitive data",
        "recovery": "Automated backup and recovery"
    }
}

print("\nExample requirements:")
for category, values in requirements.items():
    print(category)
    if isinstance(values, list):
        for value in values:
            bullet(value)
    else:
        for key, value in values.items():
            bullet(f"{key}: {value}")


# ============================================================
# 6. DECOMPOSITION
# ============================================================

title("5. Decomposition")

explain("""
Decomposition means breaking a large problem into smaller parts.

A system can be decomposed by:

    Business capability
    Responsibility
    Data ownership
    Workflow
    Technical concern
    Domain concept

A common mistake is decomposing purely by nouns.

For example:

    User
    Order
    Product
    Payment

Those are domain concepts, but they do not automatically tell us
where responsibilities belong.

A better design asks:

    Who owns this behaviour?
    Who owns this data?
    Who is allowed to modify it?
    Which component should change if this rule changes?

The goal is not to create the maximum number of components.

The goal is to create useful boundaries.
""")


# ============================================================
# 7. MODULES AND COMPONENTS
# ============================================================

title("6. Modules and Components")

explain("""
A module is a logical unit of software organisation.

A component is a larger unit with a defined responsibility and interface.

A component should ideally have:

    A clear purpose
    A stable interface
    Controlled dependencies
    Explicit ownership
    Predictable behaviour

A component becomes difficult to maintain when unrelated responsibilities
accumulate inside it.

For example, an OrderService that performs all of these operations:

    validation
    pricing
    database access
    payment processing
    email delivery
    logging
    inventory management

has too many responsibilities.

The issue is not simply that the class is large.

The deeper issue is that multiple reasons for change are combined.
""")


# ============================================================
# 8. COHESION
# ============================================================

title("7. Cohesion")

explain("""
Cohesion measures how closely related the responsibilities inside a
module or component are.

High cohesion means that the contents of a module strongly belong
together.

Low cohesion means that unrelated responsibilities have been grouped.

Example of high cohesion:

    PaymentService

Responsibilities:

    authorize payment
    capture payment
    refund payment

Example of low cohesion:

    UtilityService

Responsibilities:

    calculate tax
    send email
    resize image
    process payment
    generate reports

High cohesion usually makes software easier to understand, test and
change.
""")


# ============================================================
# 9. COUPLING
# ============================================================

title("8. Coupling")

explain("""
Coupling describes how strongly components depend on one another.

High coupling means changes in one component frequently require changes
in another.

Low coupling means components interact through relatively stable
contracts.

Consider:

    OrderService -> PaymentService implementation

This creates stronger coupling than:

    OrderService -> PaymentGateway interface

The interface acts as a boundary.

The objective is not zero coupling.

A system without relationships between components cannot perform useful
work.

The goal is controlled coupling.
""")


# ============================================================
# 10. ENCAPSULATION
# ============================================================

title("9. Encapsulation")

explain("""
Encapsulation means controlling how internal state and implementation
details are accessed.

An object should protect its invariants.

An invariant is a condition that must remain true.

For an Order:

    total amount cannot be negative
    an order cannot be paid twice
    cancelled orders cannot be shipped

Bad design exposes all internal state and allows arbitrary mutation.

Better design exposes operations that preserve rules.
""")


class Money:
    def __init__(self, amount):
        if amount < 0:
            raise ValueError("Money cannot be negative")
        self._amount = amount

    @property
    def amount(self):
        return self._amount

    def add(self, other):
        return Money(self._amount + other._amount)

    def __repr__(self):
        return f"Money({self._amount})"


money_a = Money(100)
money_b = Money(50)

print("\nMoney example:")
print("A:", money_a)
print("B:", money_b)
print("A + B:", money_a.add(money_b))


# ============================================================
# 11. INTERFACES AND CONTRACTS
# ============================================================

title("10. Interfaces and Contracts")

explain("""
An interface defines what a component promises to provide.

It is a contract between two parts of a system.

The caller should depend on the contract rather than the implementation.

For example:

    PaymentGateway
        authorize()
        capture()
        refund()

Possible implementations:

    StripePaymentGateway
    AdyenPaymentGateway
    MockPaymentGateway

The OrderService does not need to know how every payment provider works.

This separation allows implementations to change without forcing the
business logic to change.
""")

from abc import ABC, abstractmethod


class PaymentGateway(ABC):

    @abstractmethod
    def charge(self, amount):
        pass


class MockPaymentGateway(PaymentGateway):

    def charge(self, amount):
        return {
            "status": "success",
            "amount": amount
        }


gateway = MockPaymentGateway()
print("\nInterface example:")
print(gateway.charge(500))


# ============================================================
# 12. SOLID PRINCIPLES
# ============================================================

title("11. SOLID Principles")

explain("""
SOLID is a collection of object-oriented design principles.

S = Single Responsibility Principle
O = Open/Closed Principle
L = Liskov Substitution Principle
I = Interface Segregation Principle
D = Dependency Inversion Principle

These principles are not laws.

They are tools for reasoning about change and dependency structure.
""")


section("Single Responsibility Principle")

explain("""
A component should have a focused responsibility and a coherent reason
to change.

Consider an Invoice class responsible for:

    invoice calculation
    PDF generation
    email delivery
    database storage

These are separate concerns.

A cleaner design might use:

    Invoice
    InvoiceCalculator
    InvoiceRenderer
    InvoiceRepository
    InvoiceNotifier
""")


section("Open/Closed Principle")

explain("""
Software should generally be open to extension without requiring
constant modification of stable existing logic.

Suppose shipping cost supports:

    Standard
    Express
    International

A large chain of conditional statements becomes increasingly difficult
to maintain.

A strategy abstraction can isolate the variation.
""")


class ShippingStrategy(ABC):

    @abstractmethod
    def calculate(self, weight):
        pass


class StandardShipping(ShippingStrategy):

    def calculate(self, weight):
        return weight * 5


class ExpressShipping(ShippingStrategy):

    def calculate(self, weight):
        return weight * 10


def shipping_cost(strategy, weight):
    return strategy.calculate(weight)


print("\nStrategy example:")
print("Standard:", shipping_cost(StandardShipping(), 10))
print("Express:", shipping_cost(ExpressShipping(), 10))


section("Liskov Substitution Principle")

explain("""
A subtype should behave in a way that remains valid when used where
the parent abstraction is expected.

Inheritance should represent a genuine behavioural relationship.

If a subclass violates assumptions made by callers, inheritance may be
the wrong abstraction.

The key issue is behavioural compatibility, not merely matching method
names.
""")


section("Interface Segregation Principle")

explain("""
Clients should not be forced to depend on methods they do not use.

A giant interface such as:

    Printer
        print()
        scan()
        fax()
        staple()
        email()

can create unnecessary dependencies.

Smaller focused interfaces are often easier to implement and test.
""")


section("Dependency Inversion Principle")

explain("""
High-level business logic should not depend directly on low-level
implementation details.

Both should depend on abstractions.

For example:

    OrderService
          |
          v
    PaymentGateway
          ^
          |
    StripePaymentGateway

OrderService does not directly construct StripePaymentGateway.

This allows payment implementation to change independently.
""")


# ============================================================
# 13. COMPOSITION VS INHERITANCE
# ============================================================

title("12. Composition vs Inheritance")

explain("""
Inheritance creates an "is-a" relationship.

Composition creates a "has-a" or "uses-a" relationship.

Inheritance:

    Car is a Vehicle.

Composition:

    Car has an Engine.

Composition is often preferred when behaviour needs to vary independently.

For example, instead of creating:

    PremiumOrder
    DiscountOrder
    InternationalOrder
    PremiumInternationalOrder

we can compose policies:

    Order
      -> PricingPolicy
      -> ShippingPolicy
      -> DiscountPolicy

This reduces the combinatorial growth of subclasses.
""")


# ============================================================
# 14. IMMUTABILITY
# ============================================================

title("13. Immutability")

explain("""
Immutable objects cannot be changed after creation.

They are useful for values such as:

    Money
    Coordinates
    Dates
    Identifiers
    Configuration values

Immutability reduces the number of places where state can unexpectedly
change.

It is particularly useful in concurrent systems because shared immutable
data is easier to reason about.
""")


from dataclasses import dataclass


@dataclass(frozen=True)
class Coordinate:
    x: float
    y: float


point = Coordinate(10, 20)
print("\nImmutable object:")
print(point)


# ============================================================
# 15. DOMAIN MODELLING
# ============================================================

title("14. Domain Modelling")

explain("""
Domain modelling means identifying concepts and rules from the business
domain and representing them explicitly.

For an e-commerce system:

    Customer
    Product
    Cart
    Order
    Payment
    Shipment
    Address

The important part is not the number of classes.

The important part is capturing business rules.

For example:

    An order may contain multiple items.
    A cancelled order cannot be shipped.
    A payment cannot be captured before authorization.
    Inventory cannot become negative.

Good domain models make important rules visible in the design.
""")


# ============================================================
# 16. ENTITY VS VALUE OBJECT
# ============================================================

title("15. Entity vs Value Object")

explain("""
An entity is usually identified by identity.

Example:

    Customer(id=123)

Even if the customer's name changes, the entity remains the same
customer.

A value object is identified by its value.

Examples:

    Money(500)
    Coordinate(10, 20)
    EmailAddress("person@example.com")

Two Money(500) values represent the same value even if they are separate
Python objects.

This distinction helps determine identity, equality and persistence
behaviour.
""")


# ============================================================
# 17. DESIGN PATTERNS
# ============================================================

title("16. Design Patterns")

explain("""
Design patterns are reusable solutions to recurring design problems.

They are not pieces of code that must be copied.

Important categories include:

Creational:

    Factory
    Abstract Factory
    Builder
    Singleton

Structural:

    Adapter
    Decorator
    Facade
    Composite
    Proxy

Behavioural:

    Strategy
    Observer
    Command
    State
    Chain of Responsibility
    Template Method

Patterns should solve a real problem.

Using patterns merely to make code look sophisticated often makes
systems unnecessarily complicated.
""")


section("Factory Pattern")

explain("""
A factory centralizes object creation when creation rules are complex
or when the concrete implementation should not be exposed to callers.
""")


class Notification(ABC):

    @abstractmethod
    def send(self, message):
        pass


class EmailNotification(Notification):

    def send(self, message):
        return f"Email: {message}"


class SMSNotification(Notification):

    def send(self, message):
        return f"SMS: {message}"


class NotificationFactory:

    @staticmethod
    def create(channel):
        if channel == "email":
            return EmailNotification()
        if channel == "sms":
            return SMSNotification()
        raise ValueError("Unsupported channel")


notification = NotificationFactory.create("email")
print("\nFactory:")
print(notification.send("Order confirmed"))


section("Adapter Pattern")

explain("""
An adapter converts one interface into another interface expected by
the application.

This is particularly useful when integrating external systems.

For example, the application may expect:

    send_sms(phone, message)

while a third-party provider exposes:

    transmit(destination, payload)

The adapter hides the external API shape.
""")


class ExternalSMSProvider:

    def transmit(self, destination, payload):
        return f"External SMS sent to {destination}: {payload}"


class SMSAdapter:

    def __init__(self, provider):
        self.provider = provider

    def send_sms(self, phone, message):
        return self.provider.transmit(phone, message)


sms = SMSAdapter(ExternalSMSProvider())
print("\nAdapter:")
print(sms.send_sms("9999999999", "Hello"))


section("Decorator Pattern")

explain("""
A decorator adds behaviour around another object without modifying its
core implementation.

Typical uses include:

    logging
    caching
    authorization
    metrics
    retry logic
""")


class SimpleOrderService:

    def create_order(self, order):
        return f"Order {order} created"


class LoggingOrderService:

    def __init__(self, service):
        self.service = service

    def create_order(self, order):
        print("LOG: creating order")
        result = self.service.create_order(order)
        print("LOG: order created")
        return result


service = LoggingOrderService(SimpleOrderService())

print("\nDecorator:")
print(service.create_order(101))


# ============================================================
# 18. COMPONENT DESIGN
# ============================================================

title("17. Component Design")

explain("""
Component design begins by defining responsibilities and boundaries.

A useful component definition contains:

    Name
    Responsibility
    Inputs
    Outputs
    Dependencies
    Data ownership
    Failure behaviour
    Performance characteristics
    Security considerations

Example:

    Order Service

Responsibility:
    Manage order lifecycle.

Inputs:
    customer_id
    product_id
    quantity

Outputs:
    order_id
    order_status

Dependencies:
    Inventory
    Payment
    Order database

Failure behaviour:
    Payment failure must not leave an order incorrectly marked as paid.

Data ownership:
    Order state and order items.
""")


# ============================================================
# 19. API DESIGN
# ============================================================

title("18. API Design")

explain("""
An API is a contract between software components.

A good API should make valid operations easy and invalid operations
difficult.

Important API concerns include:

    naming
    request structure
    response structure
    status codes
    validation
    authentication
    authorization
    idempotency
    pagination
    versioning
    error handling
    rate limiting

Example REST endpoints:

    POST   /orders
    GET    /orders/{id}
    POST   /orders/{id}/cancel
    GET    /customers/{id}/orders

The API should expose business capabilities rather than internal
database structure.
""")


# ============================================================
# 20. API IDEMPOTENCY
# ============================================================

title("19. Idempotency")

explain("""
An operation is idempotent when repeating it produces the same intended
result after the first successful execution.

This matters because distributed systems frequently retry operations.

Imagine:

    Client -> Payment Service

The payment succeeds, but the response is lost.

The client retries.

Without protection, the customer could be charged twice.

An idempotency key allows the server to recognize that the second
request represents the same logical operation.
""")


class IdempotencyStore:

    def __init__(self):
        self.results = {}

    def execute(self, key, operation):
        if key in self.results:
            return self.results[key]

        result = operation()
        self.results[key] = result
        return result


store = IdempotencyStore()

counter = {"value": 0}


def payment_operation():
    counter["value"] += 1
    return f"payment-{counter['value']}"


print("\nIdempotency:")
print(store.execute("request-123", payment_operation))
print(store.execute("request-123", payment_operation))
print("Operation count:", counter["value"])


# ============================================================
# 21. HLD COMPONENTS
# ============================================================

title("20. Common HLD Components")

explain("""
Large systems frequently contain combinations of the following:

Client
    Browser, mobile application, desktop application or another service.

Load Balancer
    Distributes incoming traffic.

API Gateway
    Provides a controlled entry point into backend services.

Application Service
    Executes business logic.

Database
    Stores persistent state.

Cache
    Stores frequently accessed data for faster retrieval.

Message Queue
    Temporarily holds work for asynchronous processing.

Message Broker
    Routes messages between producers and consumers.

Object Storage
    Stores large binary objects such as images and documents.

Search Engine
    Provides specialised search capabilities.

CDN
    Delivers static or cacheable content closer to users.

Monitoring System
    Collects metrics.

Logging System
    Collects application and infrastructure logs.

Tracing System
    Tracks requests across distributed components.
""")


# ============================================================
# 22. LAYERED ARCHITECTURE
# ============================================================

title("21. Layered Architecture")

explain("""
A common application architecture is:

    Presentation
        |
    Application
        |
    Domain
        |
    Infrastructure

Presentation handles interaction.

Application coordinates use cases.

Domain contains business rules.

Infrastructure handles external mechanisms such as databases and APIs.

The exact naming varies between organisations.

The key principle is separation of concerns.
""")


# ============================================================
# 23. CLEAN ARCHITECTURE
# ============================================================

title("22. Clean Architecture")

explain("""
Clean Architecture places business rules toward the centre and
technical details toward the outside.

A simplified structure is:

    Frameworks / Drivers
            |
    Interface Adapters
            |
    Application / Use Cases
            |
    Domain

The Dependency Rule states that source-code dependencies should point
toward more stable inner policy.

For example:

    Domain should not need to know whether persistence uses PostgreSQL,
    MongoDB or an in-memory implementation.

This improves testability and allows infrastructure details to change.
""")


# ============================================================
# 24. HEXAGONAL ARCHITECTURE
# ============================================================

title("23. Hexagonal Architecture")

explain("""
Hexagonal Architecture is also known as Ports and Adapters.

The application core communicates through ports.

Adapters connect those ports to the outside world.

For example:

    Core
      |
      +--- PaymentPort
      |
      +--- OrderRepository

Adapters:

    StripePaymentAdapter
    PostgreSQLOrderRepository
    RESTOrderController

This makes external technology replaceable.
""")


# ============================================================
# 25. MODULAR MONOLITH
# ============================================================

title("24. Modular Monolith")

explain("""
A monolith is not automatically badly designed.

A modular monolith can have:

    one deployable application
    strong internal module boundaries
    independent responsibilities
    controlled dependencies
    separate data ownership

For many systems, this can be simpler than immediately adopting
microservices.

The architectural question is not:

    Monolith or microservices?

It is:

    What boundaries and operational properties does the system need?
""")


# ============================================================
# 26. MICROSERVICES
# ============================================================

title("25. Microservices")

explain("""
Microservices divide an application into independently deployable
services.

A service should ideally own a coherent business capability.

Possible services:

    User Service
    Order Service
    Payment Service
    Inventory Service
    Notification Service

Benefits can include:

    independent deployment
    independent scaling
    fault isolation
    team autonomy

Costs include:

    network failures
    distributed transactions
    operational complexity
    service discovery
    monitoring complexity
    versioning
    data consistency challenges

Microservices are an architectural trade-off, not a universal upgrade.
""")


# ============================================================
# 27. EVENT-DRIVEN ARCHITECTURE
# ============================================================

title("26. Event-Driven Architecture")

explain("""
In an event-driven system, components communicate through events.

Example:

    OrderPlaced

Consumers may include:

    Inventory Service
    Notification Service
    Analytics Service

The producer does not necessarily need to know all consumers.

This can reduce direct coupling.

The trade-off is increased complexity around:

    ordering
    duplication
    retries
    eventual consistency
    event schemas
    debugging
    replay
""")


@dataclass
class OrderPlaced:
    order_id: int
    customer_id: int


class EventBus:

    def __init__(self):
        self.handlers = {}

    def subscribe(self, event_type, handler):
        self.handlers.setdefault(event_type, []).append(handler)

    def publish(self, event):
        for handler in self.handlers.get(type(event), []):
            handler(event)


def inventory_handler(event):
    print(f"Inventory processing order {event.order_id}")


def notification_handler(event):
    print(f"Notification processing order {event.order_id}")


bus = EventBus()
bus.subscribe(OrderPlaced, inventory_handler)
bus.subscribe(OrderPlaced, notification_handler)

print("\nEvent-driven example:")
bus.publish(OrderPlaced(1001, 42))


# ============================================================
# 28. SYNCHRONOUS VS ASYNCHRONOUS
# ============================================================

title("27. Synchronous vs Asynchronous Communication")

explain("""
Synchronous communication means the caller waits for a response.

Example:

    Order Service -> Payment Service

The order request may remain blocked until payment responds.

Asynchronous communication allows work to be processed later.

Example:

    Order Service -> Message Queue
                         |
                         v
                  Notification Worker

Asynchronous processing is useful when:

    immediate response is unnecessary
    workload is bursty
    processing is expensive
    temporary downstream failure should not block the caller

It also introduces:

    delayed processing
    retries
    duplicate messages
    eventual consistency
    queue monitoring requirements
""")


# ============================================================
# 29. SCALABILITY
# ============================================================

title("28. Scalability")

explain("""
Scalability describes the ability of a system to handle increasing
workload.

Vertical scaling means increasing resources of one machine.

    More CPU
    More RAM
    Faster storage

Horizontal scaling means adding more machines or instances.

    Server 1
    Server 2
    Server 3

Horizontal scaling generally requires careful handling of:

    shared state
    sessions
    databases
    distributed locks
    caches
    load balancing
""")


# ============================================================
# 30. STATELESS SERVICES
# ============================================================

title("29. Stateless Services")

explain("""
A stateless service does not rely on local process memory to retain
important user session state between requests.

Instead, state may be stored in:

    Database
    Distributed cache
    Token
    External session store

Stateless application instances are easier to scale horizontally because
any instance can process any request.
""")


# ============================================================
# 31. LOAD BALANCING
# ============================================================

title("30. Load Balancing")

explain("""
A load balancer distributes incoming requests across available
application instances.

Common strategies include:

    Round Robin
    Weighted Round Robin
    Least Connections
    Consistent Hashing

A load balancer can also perform health checks.

An unhealthy server should not continue receiving normal traffic.
""")


# ============================================================
# 32. CACHING
# ============================================================

title("31. Caching")

explain("""
Caching stores frequently used data closer to the consumer.

A typical flow:

    Client
      |
      v
    Application
      |
      v
    Cache
      |
      v
    Database

A cache can reduce database load and improve latency.

The difficult part is cache invalidation.

Common strategies include:

    Cache-aside
    Write-through
    Write-behind
    Refresh-ahead

Cache-aside:

    1. Read cache.
    2. If hit, return.
    3. If miss, read database.
    4. Store result in cache.
    5. Return result.
""")


class SimpleCache:

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value


cache = SimpleCache()
cache.set("product:1", {"name": "Laptop", "price": 80000})

print("\nCache example:")
print(cache.get("product:1"))


# ============================================================
# 33. DATABASE DESIGN
# ============================================================

title("32. Database Decisions")

explain("""
Database selection should follow workload and consistency requirements.

Important questions:

    What data is stored?
    How is it queried?
    What consistency is required?
    What is the write volume?
    What is the read volume?
    How large will the data become?
    Are relationships important?
    Are transactions important?

Relational databases are strong when:

    relationships matter
    transactions matter
    constraints matter
    structured querying matters

Document stores may be useful when:

    document-oriented data is dominant
    schema flexibility is important
    access patterns fit the model

Key-value stores are useful for:

    simple lookups
    caching
    high-throughput access

The database should be selected from requirements, not popularity.
""")


# ============================================================
# 34. NORMALIZATION
# ============================================================

title("33. Normalization vs Denormalization")

explain("""
Normalization reduces duplication and improves consistency.

For example, customer information can be stored once and referenced by
orders.

Denormalization intentionally duplicates data to improve read performance
or simplify read paths.

Denormalization creates additional consistency responsibilities.

The decision depends on workload.

Write-heavy transactional systems may prefer stronger normalization.

Read-heavy systems may intentionally duplicate data for efficient access.
""")


# ============================================================
# 35. TRANSACTIONS
# ============================================================

title("34. Transactions")

explain("""
A transaction groups operations that should satisfy a defined atomicity
boundary.

The classic ACID properties are:

    Atomicity
    Consistency
    Isolation
    Durability

Atomicity:
    all operations succeed or the transaction is rolled back.

Consistency:
    defined integrity constraints remain valid.

Isolation:
    concurrent transactions should not interfere in invalid ways.

Durability:
    committed data should survive failures.

The important architectural question is:

    Where should the transaction boundary exist?

A local database transaction is much simpler than a distributed
transaction spanning multiple independent services.
""")


# ============================================================
# 36. DISTRIBUTED TRANSACTIONS
# ============================================================

title("35. Distributed Transactions")

explain("""
Suppose:

    Order Service
          |
          +---- Order Database
          |
          +---- Payment Service
          |
          +---- Inventory Service

A single traditional database transaction cannot easily cover all
three independent systems.

Possible approaches include:

    Saga pattern
    compensating actions
    transactional messaging
    eventual consistency

The system may represent the workflow as:

    Order Created
        |
        v
    Payment Authorized
        |
        v
    Inventory Reserved
        |
        v
    Order Confirmed

If inventory reservation fails, a compensating action may cancel or
reverse the earlier payment authorization.

This is a business workflow, not simply a database transaction.
""")


# ============================================================
# 37. SAGA PATTERN
# ============================================================

title("36. Saga Pattern")

explain("""
A Saga breaks a distributed business transaction into a sequence of
local transactions.

Example:

    Step 1: Create order
    Step 2: Authorize payment
    Step 3: Reserve inventory
    Step 4: Create shipment

Compensating operations may be:

    Cancel order
    Refund payment
    Release inventory
    Cancel shipment

There are two common coordination styles:

    Choreography
    Orchestration

Choreography uses events and distributed reactions.

Orchestration uses a coordinator that explicitly controls the workflow.

Each has different complexity and visibility characteristics.
""")


# ============================================================
# 38. CONSISTENCY
# ============================================================

title("37. Consistency")

explain("""
Consistency means that data satisfies the guarantees defined by the
system.

Strong consistency provides a relatively current view of shared data.

Eventual consistency allows replicas or components to temporarily
disagree while converging later.

Example:

    User changes profile name.

Immediately after the change, one read may show:

    "Atul"

while another replica temporarily shows:

    "Atul Kumar"

If the application can tolerate this delay, eventual consistency may
be acceptable.

The correct consistency model depends on business requirements.
""")


# ============================================================
# 39. CAP THEOREM
# ============================================================

title("38. CAP Theorem")

explain("""
CAP concerns distributed data systems under a network partition.

The three properties are:

    Consistency
    Availability
    Partition tolerance

When a network partition occurs, a distributed system cannot guarantee
both strong consistency and availability simultaneously.

Partition tolerance is usually required in a distributed environment
because network failures are unavoidable.

Therefore the practical decision often becomes:

    During a partition, should the system prefer consistency or
    availability?

This is a system-level trade-off rather than a simple database label.
""")


# ============================================================
# 40. RELIABILITY
# ============================================================

title("39. Reliability")

explain("""
Reliability is the ability of a system to continue providing correct
behaviour over time.

Important techniques include:

    redundancy
    replication
    retries
    timeouts
    circuit breakers
    health checks
    graceful degradation
    backups
    disaster recovery
    rate limiting

Reliability must be designed into component interactions.

A system containing individually reliable components can still be
unreliable if their interactions are poorly designed.
""")


# ============================================================
# 41. TIMEOUTS
# ============================================================

title("40. Timeouts")

explain("""
Every network call should have a meaningful timeout.

Without a timeout:

    Service A
        |
        v
    Service B

If Service B becomes unresponsive, Service A may hold resources
indefinitely.

Those blocked requests can accumulate and eventually affect the entire
system.

Timeouts limit the amount of time one component is willing to wait for
another.
""")


# ============================================================
# 42. RETRIES
# ============================================================

title("41. Retries")

explain("""
Retries can recover from temporary failures.

They must be used carefully.

A retry policy should consider:

    maximum retry count
    backoff
    jitter
    retryable errors
    idempotency

Immediate retries can create a retry storm.

Exponential backoff increases the delay between attempts.

Jitter adds randomness so many clients do not retry simultaneously.
""")


# ============================================================
# 43. CIRCUIT BREAKER
# ============================================================

title("42. Circuit Breaker")

explain("""
A circuit breaker prevents repeated calls to a failing dependency.

States commonly include:

    CLOSED
    OPEN
    HALF_OPEN

Closed:
    normal requests flow.

Open:
    requests fail quickly without calling the dependency.

Half-open:
    a limited number of test requests determine whether recovery has
    occurred.

This prevents one unhealthy dependency from consuming all resources
of its callers.
""")


class CircuitBreaker:

    def __init__(self, failure_limit=3):
        self.failure_limit = failure_limit
        self.failures = 0
        self.open = False

    def call(self, operation):
        if self.open:
            raise RuntimeError("Circuit is open")

        try:
            result = operation()
            self.failures = 0
            return result

        except Exception:
            self.failures += 1

            if self.failures >= self.failure_limit:
                self.open = True

            raise


# ============================================================
# 44. RATE LIMITING
# ============================================================

title("43. Rate Limiting")

explain("""
Rate limiting restricts how frequently a client or identity can perform
an operation.

Common algorithms include:

    Fixed Window
    Sliding Window
    Token Bucket
    Leaky Bucket

Rate limiting protects:

    APIs
    databases
    expensive operations
    downstream dependencies

It can also provide fairness between clients.
""")


# ============================================================
# 45. OBSERVABILITY
# ============================================================

title("44. Observability")

explain("""
Observability helps engineers understand what is happening inside a
system from its external outputs.

Three major signals are:

    Logs
    Metrics
    Traces

Logs:
    detailed events.

Metrics:
    numerical measurements.

Traces:
    request paths across distributed components.

Useful metrics include:

    request rate
    error rate
    latency
    saturation
    queue depth
    database connections
    cache hit ratio

Observability should be considered part of system design, not an
afterthought.
""")


# ============================================================
# 46. SECURITY
# ============================================================

title("45. Security in Design")

explain("""
Security affects both HLD and LLD.

HLD security concerns:

    network boundaries
    authentication architecture
    authorization architecture
    secrets management
    encryption
    service-to-service trust
    data isolation

LLD security concerns:

    input validation
    access checks
    secure defaults
    error handling
    sensitive-data handling

Authentication answers:

    Who are you?

Authorization answers:

    What are you allowed to do?

These are different responsibilities.
""")


# ============================================================
# 47. DEFENCE IN DEPTH
# ============================================================

title("46. Defence in Depth")

explain("""
Security should not rely on one control.

For example:

    Authentication
        +
    Authorization
        +
    Input validation
        +
    Network restrictions
        +
    Encryption
        +
    Auditing
        +
    Monitoring

If one layer fails, other controls still provide protection.

Security boundaries should be explicit in architecture diagrams and
component interfaces.
""")


# ============================================================
# 48. ARCHITECTURE TRADE-OFFS
# ============================================================

title("47. Architecture Trade-offs")

explain("""
Architecture is fundamentally about trade-offs.

Examples:

    Consistency vs availability
    Latency vs durability
    Simplicity vs flexibility
    Cost vs performance
    Centralization vs autonomy
    Strong transactions vs distributed scalability
    Fast development vs long-term maintainability

There is rarely a universally best architecture.

A decision is good when it satisfies the important requirements while
keeping unnecessary complexity under control.
""")


# ============================================================
# 49. DECISION MATRIX
# ============================================================

title("48. Architecture Decision Matrix")

explain("""
A decision matrix makes trade-offs explicit.

Suppose we compare:

    PostgreSQL
    Document Database

Criteria:

    Transactions
    Flexible schema
    Relational queries
    Operational simplicity
""")

decision_matrix = {
    "PostgreSQL": {
        "transactions": 5,
        "flexible_schema": 3,
        "relational_queries": 5,
        "simplicity": 5
    },
    "Document Database": {
        "transactions": 3,
        "flexible_schema": 5,
        "relational_queries": 2,
        "simplicity": 4
    }
}

weights = {
    "transactions": 5,
    "flexible_schema": 2,
    "relational_queries": 5,
    "simplicity": 3
}

for database, scores in decision_matrix.items():
    total = 0
    for criterion, score in scores.items():
        total += score * weights[criterion]
    print(f"{database}: {total}")


# ============================================================
# 50. ARCHITECTURE DECISION RECORD
# ============================================================

title("49. Architecture Decision Records")

explain("""
An Architecture Decision Record, or ADR, documents an important
architecture decision.

A useful ADR contains:

    Title
    Context
    Decision
    Alternatives
    Consequences

Example:

Title:
    Use PostgreSQL for order persistence.

Context:
    Orders require transactional updates and strong relationships
    between customers, orders and order items.

Decision:
    PostgreSQL will be used as the primary order database.

Alternatives:
    Document database
    Key-value store

Consequences:
    Strong transactional support is available.
    Relational querying is straightforward.
    Horizontal write scaling may require additional architecture later.

The important purpose of an ADR is to preserve reasoning, not just
the final answer.
""")


# ============================================================
# 51. ARCHITECTURAL FITNESS
# ============================================================

title("50. Architecture Fitness")

explain("""
An architecture is fit when its structure supports the requirements.

A high-performance architecture may be unsuitable for a small internal
application if its operational complexity is excessive.

A simple monolith may be ideal for a small product.

A distributed architecture may become appropriate when independent
scaling, fault isolation or organisational boundaries justify it.

Architecture should be proportional to the problem.
""")


# ============================================================
# 52. SEPARATION OF CONCERNS
# ============================================================

title("51. Separation of Concerns")

explain("""
Different concerns should be isolated when they change independently.

Common concerns:

    presentation
    business rules
    persistence
    networking
    authentication
    authorization
    logging
    monitoring
    configuration

Separating them reduces the number of reasons one component must change.
""")


# ============================================================
# 53. DEPENDENCY DIRECTION
# ============================================================

title("52. Dependency Direction")

explain("""
Dependency direction is one of the most important design concepts.

Suppose:

    Controller -> Service -> Repository -> Database

The controller knows about the service.

The service knows about an abstraction representing persistence.

The service should not need to know database-specific implementation
details when those details are not part of its business responsibility.

Dependency direction influences:

    testability
    maintainability
    replaceability
    architecture boundaries
""")


# ============================================================
# 54. DEPENDENCY INJECTION
# ============================================================

title("53. Dependency Injection")

explain("""
Dependency injection means supplying dependencies from outside instead
of constructing them internally.

Bad:

    class OrderService:
        def __init__(self):
            self.repository = PostgreSQLRepository()

Better:

    class OrderService:
        def __init__(self, repository):
            self.repository = repository

The second form makes the dependency explicit and easier to replace.
""")


class OrderRepository(ABC):

    @abstractmethod
    def save(self, order):
        pass


class InMemoryOrderRepository(OrderRepository):

    def __init__(self):
        self.orders = {}

    def save(self, order):
        self.orders[order["id"]] = order


class OrderService:

    def __init__(self, repository):
        self.repository = repository

    def create(self, order):
        self.repository.save(order)
        return order


repository = InMemoryOrderRepository()
order_service = OrderService(repository)

print("\nDependency injection:")
print(order_service.create({
    "id": 1,
    "customer_id": 10,
    "amount": 500
}))


# ============================================================
# 55. TESTABILITY
# ============================================================

title("54. Design for Testability")

explain("""
Good architecture makes important behaviour easy to test.

A component is easier to test when:

    dependencies are explicit
    external systems are abstracted
    business logic is separated
    state is controlled
    functions have predictable inputs and outputs

For example, OrderService should not require a real payment provider
just to test order validation.

A fake or mock implementation can be injected.
""")


class FakePaymentGateway(PaymentGateway):

    def __init__(self):
        self.charges = []

    def charge(self, amount):
        self.charges.append(amount)
        return {"status": "success", "amount": amount}


fake_gateway = FakePaymentGateway()

print("\nTestability:")
print(fake_gateway.charge(1000))
print("Charges:", fake_gateway.charges)


# ============================================================
# 56. ERROR HANDLING
# ============================================================

title("55. Error Handling")

explain("""
Errors should be classified according to their meaning.

Possible categories:

    validation error
    authentication error
    authorization error
    not found
    conflict
    dependency failure
    timeout
    internal failure

A component should not expose unnecessary implementation details.

For example, returning:

    PostgreSQL connection refused at host 10.0.0.5

to an external API consumer leaks internal information.

Instead, the API may return a controlled error while detailed technical
information remains in internal logs.
""")


# ============================================================
# 57. DOMAIN ERRORS
# ============================================================

title("56. Domain Errors")

explain("""
Business rules should be represented explicitly.

Examples:

    InsufficientInventory
    InvalidOrderState
    PaymentAlreadyCaptured
    OrderAlreadyCancelled

This is clearer than returning generic values such as:

    False
    None
    -1

A named domain error communicates intent.
""")


class InvalidOrderState(Exception):
    pass


class Order:
    def __init__(self, order_id):
        self.order_id = order_id
        self.status = "CREATED"

    def pay(self):
        if self.status != "CREATED":
            raise InvalidOrderState("Only created orders can be paid")
        self.status = "PAID"

    def cancel(self):
        if self.status == "SHIPPED":
            raise InvalidOrderState("Shipped orders cannot be cancelled")
        self.status = "CANCELLED"


order = Order(500)

print("\nDomain state:")
order.pay()
print(order.status)


# ============================================================
# 58. STATE MACHINES
# ============================================================

title("57. State Machines")

explain("""
State machines are useful when an entity has a defined lifecycle.

Order states may be:

    CREATED
    PAID
    PACKED
    SHIPPED
    DELIVERED
    CANCELLED

Not every transition is valid.

For example:

    CREATED -> PAID
    PAID -> PACKED
    PACKED -> SHIPPED
    SHIPPED -> DELIVERED

But:

    DELIVERED -> CREATED

is invalid.

Explicit state modelling prevents accidental invalid transitions.
""")


# ============================================================
# 59. WORKED SYSTEM: E-COMMERCE
# ============================================================

title("58. Worked System Design: E-Commerce Platform")

explain("""
Consider an e-commerce platform.

Functional requirements:

    browse products
    search products
    add products to cart
    place order
    pay
    reserve inventory
    track order
    receive notifications

Non-functional requirements:

    high availability
    low latency for product browsing
    secure payment processing
    reliable order processing
    scalable read traffic

We can now reason from HLD toward LLD.
""")


# ============================================================
# 60. HLD OF E-COMMERCE
# ============================================================

title("59. E-Commerce HLD")

explain("""
A reasonable high-level structure could be:

                    CLIENTS
                       |
                       v
                 LOAD BALANCER
                       |
                       v
                  API GATEWAY
                       |
        +--------------+--------------+
        |              |              |
        v              v              v
   Product Service  Order Service  User Service
        |              |
        v              v
     Product DB     Order DB
                       |
              +--------+--------+
              |                 |
              v                 v
       Payment Service    Inventory Service
              |                 |
              v                 v
       Payment Provider    Inventory DB

                    |
                    v
               Message Broker
                    |
          +---------+---------+
          |                   |
          v                   v
 Notification Service     Analytics
""")

explain("""
This architecture separates business capabilities.

Product Service owns product information.

Order Service owns order lifecycle.

Payment Service owns payment integration.

Inventory Service owns stock reservation.

Notification Service handles asynchronous notifications.

The message broker prevents notification processing from becoming a
hard synchronous dependency of order creation.
""")


# ============================================================
# 61. WHY NOT ONE GIANT SERVICE?
# ============================================================

title("60. Why Not One Giant Service?")

explain("""
A single application can certainly implement all these capabilities.

The issue is not whether one application can do it.

The issue is how responsibilities evolve.

If payment, inventory, notification and order logic become tightly mixed:

    changes become risky
    testing becomes difficult
    scaling becomes less selective
    ownership becomes unclear

A modular monolith can still solve much of this problem without requiring
separate deployment units.

The boundary should be established before deciding whether physical
service separation is necessary.
""")


# ============================================================
# 62. ORDER COMPONENT LLD
# ============================================================

title("61. Order Service LLD")

explain("""
Inside the Order Service, we can define:

    OrderController
        Handles API requests.

    OrderService
        Coordinates order creation.

    OrderValidator
        Validates business input.

    PricingService
        Calculates prices.

    OrderRepository
        Persists orders.

    InventoryGateway
        Communicates with inventory.

    PaymentGateway
        Communicates with payment.

    Order
        Represents order state.

This is LLD because we are defining internal components.
""")


# ============================================================
# 63. ORDER DOMAIN MODEL
# ============================================================

@dataclass
class OrderItem:
    product_id: int
    quantity: int
    unit_price: Money

    def total(self):
        return Money(self.quantity * self.unit_price.amount)


class DetailedOrder:

    def __init__(self, order_id, customer_id):
        self.id = order_id
        self.customer_id = customer_id
        self.items = []
        self.status = "CREATED"

    def add_item(self, item):
        if item.quantity <= 0:
            raise ValueError("Quantity must be positive")

        self.items.append(item)

    def total(self):
        result = Money(0)

        for item in self.items:
            result = result.add(item.total())

        return result

    def pay(self):
        if self.status != "CREATED":
            raise InvalidOrderState("Order cannot be paid")

        self.status = "PAID"


detailed_order = DetailedOrder(2001, 50)

detailed_order.add_item(
    OrderItem(
        product_id=101,
        quantity=2,
        unit_price=Money(1000)
    )
)

detailed_order.add_item(
    OrderItem(
        product_id=102,
        quantity=1,
        unit_price=Money(500)
    )
)

print("\nDetailed Order:")
print("Order ID:", detailed_order.id)
print("Total:", detailed_order.total())


# ============================================================
# 64. ORDER APPLICATION SERVICE
# ============================================================

title("62. Order Application Service")

explain("""
The application service coordinates the use case.

It should not contain every business rule.

A possible flow is:

    Receive request
        |
        v
    Validate input
        |
        v
    Check inventory
        |
        v
    Create order
        |
        v
    Save order
        |
        v
    Request payment
        |
        v
    Publish event

The exact order depends on business requirements and transactional
boundaries.
""")


class InventoryGateway(ABC):

    @abstractmethod
    def reserve(self, product_id, quantity):
        pass


class FakeInventoryGateway(InventoryGateway):

    def reserve(self, product_id, quantity):
        return True


class OrderApplicationService:

    def __init__(self, repository, inventory):
        self.repository = repository
        self.inventory = inventory

    def create_order(self, order):
        for item in order.items:
            if not self.inventory.reserve(item.product_id, item.quantity):
                raise RuntimeError("Inventory unavailable")

        self.repository.save({
            "id": order.id,
            "customer_id": order.customer_id,
            "total": order.total().amount,
            "status": order.status
        })

        return order


application_service = OrderApplicationService(
    InMemoryOrderRepository(),
    FakeInventoryGateway()
)

print("\nApplication service:")
print(application_service.create_order(detailed_order).id)


# ============================================================
# 65. DATA OWNERSHIP
# ============================================================

title("63. Data Ownership")

explain("""
In a distributed architecture, data ownership should be explicit.

Order Service owns:

    orders
    order items
    order state

Inventory Service owns:

    stock
    reservations

Payment Service owns:

    payment attempts
    payment state
    provider references

A service should not directly modify another service's private database
tables simply because the tables are technically accessible.

That creates hidden coupling.

Instead, communication should occur through explicit contracts.
""")


# ============================================================
# 66. DATABASE PER SERVICE
# ============================================================

title("64. Database Per Service")

explain("""
Database-per-service is a common microservice principle.

It means each service owns its persistence boundary.

This provides:

    ownership
    autonomy
    independent schema evolution
    reduced direct coupling

The trade-off is that cross-service queries become harder.

Instead of:

    SELECT orders JOIN payments JOIN inventory

the architecture may require:

    service calls
    APIs
    events
    read models
    data replication

Distributed architecture shifts complexity rather than eliminating it.
""")


# ============================================================
# 67. READ MODELS
# ============================================================

title("65. Read Models")

explain("""
A read model is a data representation optimized for a particular query.

Suppose a customer dashboard needs:

    order
    payment status
    shipment status
    product names

Instead of performing many service calls for every request, an
architecture may maintain a read-optimized representation.

This is useful in high-read systems.

The cost is additional synchronization and eventual consistency.
""")


# ============================================================
# 68. CQRS
# ============================================================

title("66. CQRS")

explain("""
CQRS means Command Query Responsibility Segregation.

The central idea is to separate:

    Commands = operations that change state.
    Queries   = operations that read state.

This does not necessarily mean two databases.

CQRS becomes useful when read and write models have substantially
different requirements.

Example:

Command model:

    CreateOrder
    CancelOrder
    CapturePayment

Query model:

    CustomerOrderHistory
    SalesDashboard
    OrderTrackingView
""")


# ============================================================
# 69. EVENTUAL CONSISTENCY IN CQRS
# ============================================================

title("67. Eventual Consistency in Read Models")

explain("""
Suppose an order is created.

The command side commits:

    Order #1001 = CREATED

An event is published:

    OrderCreated

The query side processes the event and updates its read model.

For a short period, a query may not show the new order.

This is eventual consistency.

The architecture must decide whether that temporary difference is
acceptable for the business use case.
""")


# ============================================================
# 70. SYSTEM DESIGN CAPACITY THINKING
# ============================================================

title("68. Capacity Thinking")

explain("""
System design should use approximate numbers rather than vague claims.

Suppose:

    10 million users
    10% active during peak
    5 requests per active user per minute

Peak requests:

    10,000,000 × 0.10 × 5
    = 5,000,000 requests/minute

Approximately:

    5,000,000 / 60
    ≈ 83,333 requests/second

This does not automatically tell us the architecture.

It gives us a workload against which architecture decisions can be
evaluated.
""")


# ============================================================
# 71. BACK-OF-THE-ENVELOPE ESTIMATION
# ============================================================

title("69. Back-of-the-Envelope Estimation")

explain("""
Useful estimates include:

    requests per second
    storage per day
    bandwidth
    cache size
    database operations
    peak traffic

Example:

    1 million events/day
    Average event size = 2 KB

Daily raw storage:

    1,000,000 × 2 KB
    = approximately 2 GB/day

For one year:

    approximately 730 GB

Replication, indexes and metadata increase the actual requirement.

Estimation helps identify architectural pressure points early.
""")


# ============================================================
# 72. HOTSPOTS
# ============================================================

title("70. Bottlenecks and Hotspots")

explain("""
A bottleneck is a component that limits overall system throughput.

Common bottlenecks:

    database writes
    database connections
    network bandwidth
    CPU-intensive computation
    external API limits
    lock contention
    queue consumers

Adding more application servers does not solve a database bottleneck
if all servers still depend on the same database.
""")


# ============================================================
# 73. SHARDING
# ============================================================

title("71. Sharding")

explain("""
Sharding distributes data across multiple partitions.

Example:

    users 0-999999       -> shard A
    users 1000000-1999999 -> shard B

A shard key should distribute workload reasonably evenly.

Poor shard keys can create hotspots.

Common approaches include:

    range-based sharding
    hash-based sharding
    directory-based sharding

Sharding increases operational and query complexity, so it should be
introduced when workload justifies it.
""")


# ============================================================
# 74. REPLICATION
# ============================================================

title("72. Replication")

explain("""
Replication maintains multiple copies of data.

It can improve:

    availability
    read capacity
    disaster recovery

But replicas introduce questions about:

    replication lag
    consistency
    failover
    conflict handling

A read replica may not immediately contain the latest write.
""")


# ============================================================
# 75. SINGLE RESPONSIBILITY AT HLD
# ============================================================

title("73. SOLID Thinking at HLD Level")

explain("""
The principles behind good LLD can also influence HLD.

Single Responsibility:

    A service should have a coherent business responsibility.

Dependency Inversion:

    Services should communicate through stable contracts.

Interface Segregation:

    APIs should expose focused capabilities.

Open/Closed:

    Stable contracts should allow implementations to evolve.

Liskov:

    Replacements for dependencies should preserve expected behaviour.

SOLID is therefore useful beyond individual classes when interpreted
as dependency and responsibility principles.
""")


# ============================================================
# 76. ARCHITECTURE BOUNDARIES
# ============================================================

title("74. Architecture Boundaries")

explain("""
A boundary determines where one responsibility ends and another begins.

Useful boundaries can be based on:

    business capability
    ownership
    data
    deployment
    security
    scalability

A good boundary limits the amount of knowledge that must cross it.

If two components constantly exchange internal details, the boundary
may be poorly chosen.
""")


# ============================================================
# 77. STABLE DEPENDENCIES
# ============================================================

title("75. Stable Dependencies")

explain("""
Frequently changing components should not force stable components to
change unnecessarily.

For example:

    Business Rules
          |
          v
    Payment Interface
          |
          v
    Payment Provider Adapter

The payment provider can change without rewriting business rules.

This is a major purpose of abstraction.
""")


# ============================================================
# 78. ACCIDENTAL COMPLEXITY
# ============================================================

title("76. Accidental Complexity")

explain("""
Accidental complexity comes from implementation choices rather than
the underlying problem.

Examples:

    unnecessary microservices
    excessive abstractions
    unnecessary design patterns
    complicated deployment pipelines
    redundant infrastructure
    too many asynchronous workflows

Essential complexity comes from the problem itself.

Good architecture manages essential complexity while avoiding
unnecessary accidental complexity.
""")


# ============================================================
# 79. PREMATURE ABSTRACTION
# ============================================================

title("77. Premature Abstraction")

explain("""
An abstraction is useful when it protects a meaningful boundary.

An abstraction created before the variation or boundary is understood
can make code harder to follow.

For example:

    AbstractUniversalRepositoryFactoryProvider

may add complexity without providing useful flexibility.

Good abstraction usually emerges from real variation, business rules
or architectural boundaries.
""")


# ============================================================
# 80. OVER-ENGINEERING
# ============================================================

title("78. Over-Engineering")

explain("""
Over-engineering occurs when architecture complexity significantly
exceeds the problem's requirements.

A small internal application may not need:

    service mesh
    distributed tracing
    ten microservices
    event sourcing
    multiple databases
    distributed cache

Those technologies can be valuable in appropriate systems.

The question is always:

    What problem does this design decision solve?
""")


# ============================================================
# 81. ARCHITECTURAL EVOLUTION
# ============================================================

title("79. Evolutionary Architecture")

explain("""
Architecture does not need to be perfect on the first day.

A practical progression might be:

    Simple application
        |
    Modular monolith
        |
    Selected independently scalable services
        |
    More distributed architecture where justified

The important part is preserving boundaries so that evolution remains
possible.

A modular design gives future options without paying every distributed
systems cost immediately.
""")


# ============================================================
# 82. HLD DESIGN PROCESS
# ============================================================

title("80. HLD Design Process")

explain("""
A disciplined HLD process can be expressed as:

    1. Understand requirements.
    2. Identify scale.
    3. Identify major use cases.
    4. Identify domain boundaries.
    5. Identify major components.
    6. Define communication.
    7. Choose persistence.
    8. Consider caching.
    9. Consider asynchronous processing.
   10. Consider failure modes.
   11. Consider security.
   12. Consider observability.
   13. Estimate capacity.
   14. Document trade-offs.

The order can change depending on the problem.
""")


# ============================================================
# 83. LLD DESIGN PROCESS
# ============================================================

title("81. LLD Design Process")

explain("""
A disciplined LLD process can be expressed as:

    1. Identify the use case.
    2. Identify domain objects.
    3. Assign responsibilities.
    4. Define invariants.
    5. Define interfaces.
    6. Define dependencies.
    7. Choose composition relationships.
    8. Model state transitions.
    9. Define error behaviour.
   10. Consider concurrency.
   11. Design persistence interaction.
   12. Make the component testable.

LLD should be driven by behaviour rather than class-count targets.
""")


# ============================================================
# 84. HLD AND LLD CONNECTION
# ============================================================

title("82. Connecting HLD and LLD")

explain("""
Consider:

    HLD:
        Order Service

Then LLD expands that boundary:

    OrderController
    OrderApplicationService
    Order
    OrderItem
    PricingService
    OrderRepository
    PaymentGateway
    InventoryGateway

HLD establishes:

    where the component exists

LLD establishes:

    how that component works internally

The two designs should remain consistent.

If HLD says Order Service owns order state but LLD allows five unrelated
components to directly modify order state, the architecture is
internally inconsistent.
""")


# ============================================================
# 85. DESIGN REVIEW
# ============================================================

title("83. Design Review Questions")

questions = [
    "What problem does this component solve?",
    "What responsibility does it own?",
    "What data does it own?",
    "Which components depend on it?",
    "Which dependencies can fail?",
    "What happens when a dependency times out?",
    "Can the operation be retried safely?",
    "Is the operation idempotent?",
    "What consistency does the business require?",
    "Where is the transaction boundary?",
    "Can the component scale independently?",
    "What is the main bottleneck?",
    "What happens during partial failure?",
    "How is the component monitored?",
    "How is access controlled?",
    "Can the implementation be replaced?",
    "Is the abstraction actually useful?",
    "Does the architecture introduce unnecessary complexity?",
    "What assumptions does the design make?",
    "What trade-off was consciously accepted?"
]

for number, question in enumerate(questions, 1):
    print(f"{number:02d}. {question}")


# ============================================================
# 86. COMMON DESIGN MISTAKES
# ============================================================

title("84. Common Design Mistakes")

mistakes = [
    "Starting with technology instead of requirements.",
    "Creating classes based only on nouns.",
    "Making one class responsible for unrelated concerns.",
    "Using inheritance when composition is more appropriate.",
    "Creating abstractions without a real boundary.",
    "Making every component depend directly on every other component.",
    "Allowing business logic to depend on infrastructure details.",
    "Sharing database tables between supposedly independent services.",
    "Using microservices without a clear reason.",
    "Ignoring failure and timeout behaviour.",
    "Ignoring idempotency in retried operations.",
    "Treating caching as free performance.",
    "Assuming replicas are immediately consistent.",
    "Ignoring operational complexity.",
    "Designing for extreme scale without evidence.",
    "Ignoring observability.",
    "Treating security as a separate final step.",
    "Documenting decisions without documenting the reasoning.",
    "Confusing implementation detail with architecture.",
    "Assuming there is one universally correct architecture."
]

for mistake in mistakes:
    bullet(mistake)


# ============================================================
# 87. HLD VS LLD DECISION EXAMPLES
# ============================================================

title("85. HLD vs LLD Decision Examples")

examples = {
    "Choose PostgreSQL for order storage": "HLD",
    "Create OrderRepository interface": "LLD",
    "Use Redis for frequently accessed product data": "HLD",
    "Implement PricingStrategy": "LLD",
    "Introduce a message broker": "HLD",
    "Define Order state transitions": "LLD",
    "Use API Gateway": "HLD",
    "Implement PaymentGateway adapter": "LLD",
    "Shard users by user_id": "HLD",
    "Use dependency injection in OrderService": "LLD",
    "Use asynchronous notifications": "HLD",
    "Create OrderValidator": "LLD"
}

for decision, level in examples.items():
    print(f"{level:5} | {decision}")


# ============================================================
# 88. DESIGNING FOR CHANGE
# ============================================================

title("86. Designing for Change")

explain("""
A major purpose of design is controlling the cost of change.

Suppose payment providers may change.

Bad dependency:

    OrderService -> Stripe SDK everywhere

Better boundary:

    OrderService -> PaymentGateway -> StripeAdapter

Now a provider change is isolated.

The same principle applies to:

    databases
    messaging systems
    external APIs
    storage
    notification providers

The goal is not to make every implementation replaceable.

The goal is to protect important business logic from unstable external
details.
""")


# ============================================================
# 89. DOMAIN LOGIC VS INFRASTRUCTURE
# ============================================================

title("87. Domain Logic vs Infrastructure")

explain("""
Domain logic represents business rules.

Examples:

    Order cannot be shipped before payment.
    Inventory reservation cannot exceed available stock.
    Discount cannot exceed allowed limits.

Infrastructure represents technical mechanisms.

Examples:

    PostgreSQL
    Redis
    Kafka
    HTTP
    SMTP
    cloud storage

Mixing these concerns makes business rules harder to understand and
test.
""")


# ============================================================
# 90. PORTS AND ADAPTERS WORKED EXAMPLE
# ============================================================

title("88. Ports and Adapters Worked Example")

explain("""
Core:

    OrderService
        |
        +---- OrderRepository port
        |
        +---- PaymentGateway port

Adapters:

    PostgreSQLOrderRepository
    InMemoryOrderRepository

    StripePaymentAdapter
    MockPaymentAdapter

This structure lets the same business logic operate with different
technical implementations.
""")


# ============================================================
# 91. CONCURRENCY
# ============================================================

title("89. Concurrency in Design")

explain("""
Concurrency creates problems when multiple operations modify shared
state.

Suppose inventory has:

    1 item available

Two requests arrive simultaneously.

Both read:

    stock = 1

Both attempt to reserve it.

Without proper concurrency control, both may succeed.

Possible solutions include:

    database locking
    atomic updates
    optimistic concurrency
    distributed coordination
    reservation records

The important point is that concurrency is a design concern, not merely
a programming syntax concern.
""")


# ============================================================
# 92. OPTIMISTIC CONCURRENCY
# ============================================================

title("90. Optimistic Concurrency")

explain("""
Optimistic concurrency assumes conflicts are relatively uncommon.

A record may contain:

    version = 10

A client updates:

    WHERE id = 100 AND version = 10

If the update succeeds:

    version becomes 11

If another transaction already changed the record, the condition fails.

This prevents silently overwriting newer data.
""")


# ============================================================
# 93. DISTRIBUTED LOCKS
# ============================================================

title("91. Distributed Locks")

explain("""
A distributed lock coordinates access to shared resources across
multiple processes or machines.

They can be useful, but introduce failure questions:

    What if the lock holder crashes?
    What if the lock expires?
    What if network connectivity is lost?
    What if two clients believe they own the lock?

For many workloads, atomic database operations or idempotent workflows
are preferable to complex distributed locking.
""")


# ============================================================
# 94. BACKPRESSURE
# ============================================================

title("92. Backpressure")

explain("""
Backpressure occurs when producers generate work faster than consumers
can process it.

Example:

    Producer = 10,000 messages/sec
    Consumer = 2,000 messages/sec

The queue grows.

A robust system needs policies for:

    queue limits
    throttling
    scaling consumers
    dropping low-priority work
    retry behaviour

Ignoring backpressure can turn a temporary traffic spike into a
system-wide failure.
""")


# ============================================================
# 95. GRACEFUL DEGRADATION
# ============================================================

title("93. Graceful Degradation")

explain("""
A system does not always need to provide every feature during failure.

Suppose recommendation service fails.

The shopping application may still allow:

    product browsing
    cart operations
    checkout

Recommendations can temporarily disappear.

This is graceful degradation.

It is often better than allowing an optional dependency to bring down
the primary workflow.
""")


# ============================================================
# 96. FAILURE DOMAINS
# ============================================================

title("94. Failure Domains")

explain("""
A failure domain is a group of resources likely to fail together.

Examples:

    process
    machine
    availability zone
    region
    database cluster

High availability often requires placing replicas across independent
failure domains.

Simply running two processes on the same machine does not provide
protection against machine failure.
""")


# ============================================================
# 97. DEPLOYMENT VS ARCHITECTURE
# ============================================================

title("95. Deployment Boundaries vs Logical Boundaries")

explain("""
A logical component does not necessarily need to be independently
deployed.

A modular monolith may contain:

    Order Module
    Payment Module
    Inventory Module

inside one deployable application.

Later, one module can become a separate service if there is a strong
reason.

Therefore:

    logical boundary != deployment boundary

Keeping this distinction clear prevents premature distribution.
""")


# ============================================================
# 98. ARCHITECTURE DIAGRAMS
# ============================================================

title("96. Architecture Diagrams")

explain("""
A useful architecture diagram should communicate:

    components
    responsibilities
    relationships
    communication direction
    data stores
    external dependencies

Different diagrams serve different purposes.

Context diagram:
    system and external actors.

Container or service diagram:
    major deployable or logical units.

Component diagram:
    internal components of a major unit.

Class diagram:
    detailed object relationships.

Sequence diagram:
    runtime interaction over time.

A diagram is valuable when it communicates a decision or relationship
clearly.
""")


# ============================================================
# 99. SEQUENCE THINKING
# ============================================================

title("97. Sequence of a Checkout")

explain("""
A simplified checkout sequence:

    Client
      |
      v
    Order Service
      |
      +----> Inventory Service: reserve
      |
      +----> Payment Service: authorize
      |
      v
    Order DB
      |
      v
    Event Broker
      |
      +----> Notification Service

Important design questions:

    What if inventory succeeds but payment fails?
    What if payment succeeds but the order update fails?
    What if the event is delivered twice?
    What if notification service is unavailable?
    What if the client retries checkout?

These questions reveal the actual complexity of system design.
""")


# ============================================================
# 100. COMPLETE TRADE-OFF ANALYSIS
# ============================================================

title("98. Complete Architecture Trade-off Example")

explain("""
Decision:

    Should checkout call notification synchronously?

Option A:

    Checkout -> Notification Service

Advantages:

    immediate response
    simple flow

Disadvantages:

    notification failure can affect checkout
    higher latency
    stronger coupling

Option B:

    Checkout -> Event Broker -> Notification Service

Advantages:

    checkout is independent of notification availability
    lower synchronous latency
    asynchronous scaling

Disadvantages:

    more infrastructure
    eventual consistency
    duplicate event handling
    monitoring complexity

Decision:

    If notifications are not required for successful checkout,
    asynchronous processing is generally a stronger architectural fit.

The decision is justified by the business requirement rather than by
the popularity of message brokers.
""")


# ============================================================
# 101. LLD DESIGN OF PAYMENT
# ============================================================

title("99. Payment Component LLD")

explain("""
Payment component:

    Payment
        |
        +---- PaymentGateway
        |
        +---- PaymentRepository
        |
        +---- PaymentStateMachine
        |
        +---- IdempotencyStore

Payment states:

    CREATED
    AUTHORIZED
    CAPTURED
    FAILED
    REFUNDED

Important invariants:

    A captured payment cannot be captured again.
    A refunded payment cannot be captured again.
    The same idempotency key must not create multiple charges.
""")


class Payment:

    VALID_TRANSITIONS = {
        "CREATED": {"AUTHORIZED", "FAILED"},
        "AUTHORIZED": {"CAPTURED", "FAILED"},
        "CAPTURED": {"REFUNDED"},
        "FAILED": set(),
        "REFUNDED": set()
    }

    def __init__(self, payment_id, amount):
        self.payment_id = payment_id
        self.amount = amount
        self.status = "CREATED"

    def transition(self, new_status):
        allowed = self.VALID_TRANSITIONS[self.status]

        if new_status not in allowed:
            raise InvalidOrderState(
                f"Invalid transition: {self.status} -> {new_status}"
            )

        self.status = new_status


payment = Payment(1, Money(1000))

print("\nPayment state machine:")
payment.transition("AUTHORIZED")
print(payment.status)

payment.transition("CAPTURED")
print(payment.status)


# ============================================================
# 102. LLD DESIGN OF INVENTORY
# ============================================================

title("100. Inventory Component LLD")

explain("""
Inventory needs to protect a critical invariant:

    reserved quantity must not exceed available quantity.

Possible operations:

    add_stock()
    reserve()
    release()
    available()

The implementation must also account for concurrent requests.

At LLD level, this may involve:

    InventoryItem
    InventoryRepository
    Reservation
    InventoryService

At HLD level, we may need:

    Inventory Service
    Inventory Database
    caching
    replication
    partitioning
""")


class InventoryItem:

    def __init__(self, product_id, quantity):
        self.product_id = product_id
        self.quantity = quantity

    def reserve(self, amount):
        if amount <= 0:
            raise ValueError("Amount must be positive")

        if amount > self.quantity:
            return False

        self.quantity -= amount
        return True


inventory_item = InventoryItem(100, 5)

print("\nInventory:")
print("Reserve 2:", inventory_item.reserve(2))
print("Remaining:", inventory_item.quantity)
print("Reserve 5:", inventory_item.reserve(5))
print("Remaining:", inventory_item.quantity)


# ============================================================
# 103. COMPONENT CONTRACT
# ============================================================

title("101. Component Contract")

explain("""
A strong component contract specifies:

    Preconditions
    Inputs
    Outputs
    Postconditions
    Errors
    Side effects

Example:

    reserve(product_id, quantity)

Preconditions:

    product exists
    quantity > 0

Postconditions:

    available inventory decreases by quantity

Possible errors:

    ProductNotFound
    InsufficientInventory

Side effects:

    persistence update
    reservation event

Explicit contracts reduce ambiguity between components.
""")


# ============================================================
# 104. API VERSIONING
# ============================================================

title("102. API Versioning")

explain("""
APIs evolve.

A breaking change may affect many consumers.

Strategies include:

    URL versioning
    header versioning
    backward-compatible evolution
    explicit schema negotiation

Backward-compatible evolution is often preferable when possible.

Examples:

    adding an optional field
    adding a new endpoint

Potentially breaking:

    removing a field
    changing the meaning of an existing field
    changing required input
""")


# ============================================================
# 105. SCHEMA EVOLUTION
# ============================================================

title("103. Schema Evolution")

explain("""
Database and event schemas also evolve.

A safe migration often involves stages:

    1. Add new field.
    2. Deploy code that understands both forms.
    3. Backfill data.
    4. Start writing the new field.
    5. Stop depending on the old field.
    6. Remove old field later.

This reduces the risk associated with simultaneous code and schema
changes.
""")


# ============================================================
# 106. EVENT SCHEMA EVOLUTION
# ============================================================

title("104. Event Schema Evolution")

explain("""
Events can remain in queues or logs for a long time.

Consumers may process older events after producers have changed.

Therefore event schemas should be designed with compatibility in mind.

Possible techniques:

    optional fields
    explicit versions
    tolerant readers
    schema registries
    backwards-compatible changes
""")


# ============================================================
# 107. LOGICAL VS PHYSICAL ARCHITECTURE
# ============================================================

title("105. Logical vs Physical Architecture")

explain("""
Logical architecture describes conceptual responsibilities.

Physical architecture describes actual deployment.

Logical:

    Order Service
    Payment Service

Physical:

    Kubernetes deployment
    virtual machines
    containers
    availability zones
    databases
    networks

Logical architecture explains what the system is.

Physical architecture explains where and how it runs.
""")


# ============================================================
# 108. ARCHITECTURAL PRINCIPLES
# ============================================================

title("106. Practical Architectural Principles")

principles = [
    "Prefer clear boundaries over arbitrary fragmentation.",
    "Keep business rules independent from unstable infrastructure details.",
    "Make dependencies explicit.",
    "Keep responsibilities coherent.",
    "Prefer composition when behaviour varies independently.",
    "Use abstractions to protect meaningful boundaries.",
    "Design failure behaviour explicitly.",
    "Make retried operations safe when possible.",
    "Treat data ownership as an architectural concern.",
    "Choose consistency according to business requirements.",
    "Use asynchronous processing when immediate completion is unnecessary.",
    "Do not distribute a system without a reason.",
    "Document important trade-offs.",
    "Measure workload before designing for extreme scale.",
    "Treat observability as part of the architecture.",
    "Keep security boundaries explicit."
]

for principle in principles:
    bullet(principle)


# ============================================================
# 109. MINI DESIGN EXERCISE: URL SHORTENER
# ============================================================

title("107. Mini HLD Example: URL Shortener")

explain("""
Functional requirement:

    Convert a long URL into a short URL.
    Redirect short URL to original URL.

HLD:

    Client
      |
      v
    Load Balancer
      |
      v
    URL Service
      |
      +---- Cache
      |
      +---- Database

Write flow:

    long URL
       |
       v
    generate key
       |
       v
    store mapping

Read flow:

    short key
       |
       v
    cache
       |
       +---- hit -> original URL
       |
       +---- miss
              |
              v
           database

The architecture is simple because the requirements are relatively
simple.
""")


# ============================================================
# 110. MINI LLD EXAMPLE: URL SHORTENER
# ============================================================

title("108. Mini LLD Example: URL Shortener")

class URLRepository:

    def __init__(self):
        self.data = {}

    def save(self, key, url):
        self.data[key] = url

    def find(self, key):
        return self.data.get(key)


class URLShortener:

    def __init__(self, repository):
        self.repository = repository
        self.counter = 0

    def shorten(self, url):
        self.counter += 1
        key = str(self.counter)

        self.repository.save(key, url)

        return key

    def resolve(self, key):
        return self.repository.find(key)


url_repository = URLRepository()
shortener = URLShortener(url_repository)

key = shortener.shorten("https://example.com/a/very/long/url")

print("\nURL shortener:")
print("Key:", key)
print("Resolved:", shortener.resolve(key))


# ============================================================
# 111. MINI DESIGN EXERCISE: LIBRARY SYSTEM
# ============================================================

title("109. Mini LLD Example: Library System")

explain("""
Domain:

    Book
    Member
    Loan
    Library

Business rules:

    A book can have only one active loan.
    A member may have a borrowing limit.
    A returned book becomes available.
    A lost book cannot be borrowed.

Potential classes:

    Book
    Member
    Loan
    LibraryService
    BookRepository
    LoanRepository

The domain model captures rules while repositories handle persistence.
""")


class Book:

    def __init__(self, book_id, title):
        self.book_id = book_id
        self.title = title
        self.available = True

    def borrow(self):
        if not self.available:
            raise InvalidOrderState("Book is already borrowed")

        self.available = False

    def return_book(self):
        self.available = True


class LibraryService:

    def borrow_book(self, book):
        book.borrow()
        return "Book borrowed"


book = Book(1, "Software Architecture")

print("\nLibrary:")
print(library_message := LibraryService().borrow_book(book))
print("Available:", book.available)


# ============================================================
# 112. DESIGN QUALITY
# ============================================================

title("110. Evaluating Design Quality")

explain("""
A design can be evaluated through several dimensions.

Correctness:
    Does it satisfy requirements?

Clarity:
    Can engineers understand it?

Cohesion:
    Are responsibilities related?

Coupling:
    Are dependencies controlled?

Changeability:
    Can important requirements evolve safely?

Testability:
    Can behaviour be tested independently?

Scalability:
    Can workload grow?

Reliability:
    Can failures be contained?

Security:
    Are trust boundaries protected?

Operability:
    Can the system be monitored and maintained?

Cost:
    Is the operational and development cost justified?
""")


# ============================================================
# 113. DESIGN IS CONTEXTUAL
# ============================================================

title("111. Context Matters")

explain("""
The same design can be appropriate in one environment and inappropriate
in another.

For a small internal tool:

    simple application
    relational database
    synchronous processing

may be ideal.

For a global high-traffic platform:

    distributed services
    caching
    asynchronous workflows
    replication
    multiple regions

may be justified.

Architecture cannot be judged without knowing:

    scale
    business requirements
    team structure
    operational capability
    reliability requirements
    budget
    expected change
""")


# ============================================================
# 114. FINAL INTEGRATED MODEL
# ============================================================

title("112. Integrated Mental Model")

explain("""
A practical way to connect all the concepts is:

BUSINESS REQUIREMENTS
        |
        v
NON-FUNCTIONAL REQUIREMENTS
        |
        v
SYSTEM BOUNDARIES
        |
        v
HIGH-LEVEL COMPONENTS
        |
        v
COMMUNICATION + DATA OWNERSHIP
        |
        v
FAILURE + SCALE + SECURITY
        |
        v
COMPONENT BOUNDARIES
        |
        v
LOW-LEVEL DESIGN
        |
        v
CLASSES + INTERFACES + OBJECTS
        |
        v
IMPLEMENTATION

The direction can also move upward.

When a low-level design reveals that two components must share internal
state constantly, that may indicate a poor HLD boundary.

When a system-level design creates excessive infrastructure complexity,
the HLD may need simplification.

Design is therefore iterative rather than strictly linear.
""")


# ============================================================
# 115. CONCEPTUAL DISTINCTIONS
# ============================================================

title("113. Important Distinctions")

distinctions = [
    ("HLD", "major system structure", "services, databases, queues"),
    ("LLD", "internal component structure", "classes, interfaces, objects"),
    ("Module", "logical unit of code organisation", "Order module"),
    ("Component", "coherent functional unit with a contract", "Payment component"),
    ("Service", "independently deployable or remotely accessible capability", "Payment Service"),
    ("Entity", "identity-based domain object", "Customer"),
    ("Value Object", "value-based domain object", "Money"),
    ("Coupling", "dependency between parts", "Order depends on Payment"),
    ("Cohesion", "relatedness of responsibilities", "Payment logic together"),
    ("Abstraction", "important behaviour without implementation detail", "PaymentGateway"),
    ("Encapsulation", "protecting internal state and invariants", "Order.pay()"),
    ("Synchronous", "caller waits for result", "HTTP request"),
    ("Asynchronous", "work can continue independently", "message queue"),
    ("Strong Consistency", "reads reflect current committed state", "transactional workflow"),
    ("Eventual Consistency", "state converges over time", "distributed read model"),
    ("Vertical Scaling", "more resources per machine", "more RAM"),
    ("Horizontal Scaling", "more machines", "more application instances"),
    ("Replication", "multiple copies of data", "read replicas"),
    ("Sharding", "partitioning data", "hash by user ID")
]

for term, meaning, example_text in distinctions:
    print(f"{term:22} | {meaning:42} | {example_text}")


# ============================================================
# 116. COMPLETE DESIGN CHECKLIST
# ============================================================

title("114. Complete Design Checklist")

checklist = [
    "Requirements identified",
    "Functional requirements identified",
    "Non-functional requirements identified",
    "Expected workload estimated",
    "Major domain boundaries identified",
    "Component responsibilities defined",
    "Data ownership defined",
    "Communication contracts defined",
    "Failure modes considered",
    "Timeouts considered",
    "Retries considered",
    "Idempotency considered",
    "Consistency requirements defined",
    "Transaction boundaries defined",
    "Caching requirements considered",
    "Asynchronous processing considered",
    "Scalability considered",
    "Security boundaries defined",
    "Observability defined",
    "Deployment boundaries considered",
    "Dependencies reviewed",
    "Coupling reviewed",
    "Cohesion reviewed",
    "Abstractions justified",
    "Testability considered",
    "Architecture trade-offs documented",
    "Important decisions recorded"
]

for item in checklist:
    print("[ ]", item)


# ============================================================
# 117. END OF PROGRAM
# ============================================================

title("End of Software Design vs System Design Study Program")

print("""
The demonstrations above intentionally connect low-level object design
with high-level system architecture.

The central distinction remains:

    LLD explains how a component is internally designed.

    HLD explains how major components form a complete system.

Architecture decisions connect the two levels by determining boundaries,
dependencies, data ownership, communication patterns, scalability,
reliability and operational behaviour.
""")
