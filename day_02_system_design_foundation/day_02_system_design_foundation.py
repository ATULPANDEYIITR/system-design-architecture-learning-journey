"""
SOFTWARE DESIGN FOUNDATIONS
===========================

A practical and academic study program covering software design from
basic concepts to advanced design reasoning.

The program uses:
- Explanations
- Small examples
- Comparisons
- Design problems
- Refactoring examples
- Object-oriented design
- SOLID principles
- Design patterns
- Architectural concepts
- Exercises and demonstrations

The examples intentionally use plain Python so that the focus remains
on software design rather than framework-specific syntax.
"""


# ============================================================================
# 1. INTRODUCTION TO SOFTWARE DESIGN
# ============================================================================

def section(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def explain(text):
    print("\n" + text)


section("1. WHAT SOFTWARE DESIGN ACTUALLY MEANS")

explain("""
Software design is the process of deciding how software should be
structured so that it can satisfy its requirements while remaining
understandable, maintainable, testable, extensible, and reliable.

Programming primarily answers:

    "How do I implement this behavior?"

Software design asks broader questions:

    "Where should this behavior live?"
    "Which component should be responsible for it?"
    "How should components communicate?"
    "What should depend on what?"
    "What should happen when requirements change?"
    "Which details should be hidden?"
    "How can the system be tested?"
    "How can one part change without breaking unrelated parts?"

A program can be syntactically correct and still be poorly designed.

Good software design is therefore not simply about writing more code,
using more classes, or applying more design patterns.

It is about making the important decisions about structure and
responsibility explicit.
""")


# ============================================================================
# 2. REQUIREMENTS AND DESIGN
# ============================================================================

section("2. REQUIREMENTS ARE THE STARTING POINT OF DESIGN")

explain("""
Software design should begin with understanding what the software is
supposed to accomplish.

Requirements normally contain two broad categories.

Functional requirements:
    What the system should do.

Examples:
    - A customer can place an order.
    - A user can reset a password.
    - An administrator can generate a report.

Non-functional requirements:
    Qualities or constraints of the system.

Examples:
    - The system should respond quickly.
    - The system should be secure.
    - The system should support many users.
    - The system should be easy to maintain.
    - The system should tolerate component failure.

Design decisions are strongly influenced by non-functional requirements.

For example:

    A small internal tool
and
    A globally distributed payment system

may implement similar business concepts, but their designs will be
very different because their reliability, scalability, security,
availability, and operational requirements differ.
""")


def calculate_order_total(items):
    total = 0

    for item in items:
        total += item["price"] * item["quantity"]

    return total


items = [
    {"name": "Book", "price": 500, "quantity": 2},
    {"name": "Pen", "price": 50, "quantity": 3},
]

print("\nExample requirement implemented directly:")
print("Order total:", calculate_order_total(items))


explain("""
The function above works, but design questions immediately appear.

What if the system introduces:
    - discounts?
    - taxes?
    - coupons?
    - regional pricing?
    - multiple currencies?
    - loyalty points?
    - different payment methods?

The first implementation is not necessarily wrong.

The important design question is whether its structure will continue
to work as the system changes.
""")


# ============================================================================
# 3. COMPLEXITY
# ============================================================================

section("3. SOFTWARE COMPLEXITY")

explain("""
Software complexity is one of the central problems software design
attempts to control.

There are two useful forms of complexity.

Essential complexity:
    Complexity that comes from the actual problem domain.

Accidental complexity:
    Complexity introduced by the implementation.

For example, calculating tax rules for several countries may genuinely
be complicated.

A system with ten unnecessary layers, duplicated logic, unclear
dependencies, and inconsistent naming introduces accidental complexity.

Good design does not remove essential complexity.

It attempts to prevent accidental complexity from spreading.

A useful design objective is:

    Keep complexity local.

If one business rule changes, ideally only a small and clearly defined
part of the system should need modification.
""")


# ============================================================================
# 4. ABSTRACTION
# ============================================================================

section("4. ABSTRACTION")

explain("""
Abstraction means exposing the important characteristics of something
while hiding unnecessary implementation details.

Consider a payment operation.

A caller may need to know:

    payment.process(amount)

The caller generally does not need to know:

    - how an HTTP request is constructed
    - how authentication tokens are attached
    - how retries are implemented
    - how a response is parsed
    - how logging works
    - how the provider's API changes internally

Abstraction reduces the amount of information that a component must
understand.
""")


class PaymentProcessor:
    def process(self, amount):
        raise NotImplementedError


class SimplePaymentProcessor(PaymentProcessor):
    def process(self, amount):
        return f"Payment of {amount} processed."


processor = SimplePaymentProcessor()

print(processor.process(1000))


explain("""
The abstraction is useful because code using PaymentProcessor can focus
on the concept of processing a payment rather than the provider's
implementation details.

Abstraction should not mean hiding everything.

A good abstraction exposes the concepts required by its clients.

A bad abstraction may hide important behavior, making the system harder
to understand or debug.
""")


# ============================================================================
# 5. ENCAPSULATION
# ============================================================================

section("5. ENCAPSULATION")

explain("""
Encapsulation means keeping data and the operations that control that
data together while protecting internal representation from arbitrary
external manipulation.

Consider a bank account.

A weak design allows callers to modify the balance directly:

    account.balance = -500000

A stronger design controls balance changes through operations that
enforce business rules.

The goal is not merely to make attributes private.

The deeper purpose is to protect invariants.

An invariant is a condition that should remain true for a valid object.
""")


class BankAccount:

    def __init__(self, opening_balance=0):
        if opening_balance < 0:
            raise ValueError("Opening balance cannot be negative")

        self._balance = opening_balance

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("Deposit must be positive")

        self._balance += amount

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("Withdrawal must be positive")

        if amount > self._balance:
            raise ValueError("Insufficient balance")

        self._balance -= amount

    @property
    def balance(self):
        return self._balance


account = BankAccount(1000)
account.deposit(500)
account.withdraw(200)

print("Account balance:", account.balance)


# ============================================================================
# 6. MODULARITY
# ============================================================================

section("6. MODULARITY")

explain("""
Modularity means dividing a software system into meaningful units.

A module may be:

    - a function
    - a class
    - a package
    - a service
    - a subsystem
    - a library

The objective is not to maximize the number of modules.

The objective is to create boundaries that make the system easier to
understand and change.

A useful module has a clear purpose.

For example:

    authentication
    payments
    inventory
    reporting
    notifications

These concepts may interact, but they should not become one giant
undifferentiated block.
""")


# ============================================================================
# 7. SEPARATION OF CONCERNS
# ============================================================================

section("7. SEPARATION OF CONCERNS")

explain("""
A concern is a responsibility or aspect of behavior.

Examples:

    - business rules
    - database access
    - authentication
    - logging
    - presentation
    - validation
    - communication with external systems

Separation of concerns means that unrelated responsibilities should not
be unnecessarily mixed.

Consider this poor example.
""")


def register_user_bad(name, email):
    print("Validating user")

    if "@" not in email:
        raise ValueError("Invalid email")

    print("Saving user to database")
    print("Sending welcome email")
    print("Writing audit log")

    return {"name": name, "email": email}


explain("""
This function is doing several things:

    1. validation
    2. persistence
    3. notification
    4. logging

It may work initially, but every responsibility becomes coupled to
the same function.

A cleaner design separates responsibilities.
""")


class UserValidator:

    def validate(self, name, email):
        if not name:
            raise ValueError("Name is required")

        if "@" not in email:
            raise ValueError("Invalid email")


class UserRepository:

    def save(self, user):
        print("User saved:", user)


class EmailService:

    def send_welcome_email(self, email):
        print("Welcome email sent to:", email)


class AuditLogger:

    def log(self, message):
        print("AUDIT:", message)


class UserRegistrationService:

    def __init__(self, validator, repository, email_service, logger):
        self.validator = validator
        self.repository = repository
        self.email_service = email_service
        self.logger = logger

    def register(self, name, email):
        self.validator.validate(name, email)

        user = {
            "name": name,
            "email": email
        }

        self.repository.save(user)
        self.email_service.send_welcome_email(email)
        self.logger.log(f"Registered user {email}")

        return user


registration = UserRegistrationService(
    UserValidator(),
    UserRepository(),
    EmailService(),
    AuditLogger()
)

registration.register("Alice", "alice@example.com")


# ============================================================================
# 8. COHESION
# ============================================================================

section("8. COHESION")

explain("""
Cohesion describes how closely related the responsibilities inside a
module are.

High cohesion means that a component has a focused purpose.

Low cohesion means that unrelated responsibilities have been placed
together.

Example of high cohesion:

    InvoiceCalculator
        - calculate subtotal
        - calculate tax
        - calculate total

Example of low cohesion:

    UtilityManager
        - calculate invoice
        - send email
        - resize image
        - connect to database
        - validate passwords
        - generate reports

High cohesion usually improves readability and maintainability.

A practical question is:

    "Can I describe what this component does in one clear sentence?"

If the answer requires a long list of unrelated responsibilities,
the component may have low cohesion.
""")


# ============================================================================
# 9. COUPLING
# ============================================================================

section("9. COUPLING")

explain("""
Coupling describes how strongly one component depends on another.

High coupling means that changes in one component can easily force
changes elsewhere.

Low coupling means components can change more independently.

Consider:

    OrderService directly creates MySQLRepository.

This creates a concrete dependency.

A more flexible design can depend on an abstraction.

The important relationship is:

    High cohesion
    Low unnecessary coupling

This is one of the most important recurring ideas in software design.
""")


# ============================================================================
# 10. INFORMATION HIDING
# ============================================================================

section("10. INFORMATION HIDING")

explain("""
Information hiding means that a component hides design decisions that
other components do not need to know.

Suppose an application stores data in PostgreSQL.

The business layer should ideally not need to know:

    - SQL query construction
    - connection pooling
    - cursor management
    - database driver details

If those details leak everywhere, changing the database becomes
expensive.

The boundary should expose meaningful operations instead.
""")


class ProductRepository:

    def save(self, product):
        print("Saving product:", product)

    def find_by_id(self, product_id):
        print("Loading product:", product_id)
        return {
            "id": product_id,
            "name": "Example Product"
        }


repository = ProductRepository()
print(repository.find_by_id(101))


# ============================================================================
# 11. INTERFACES
# ============================================================================

section("11. INTERFACES AND CONTRACTS")

explain("""
An interface describes what a component promises to provide without
requiring clients to know how that behavior is implemented.

In Python, interfaces can be represented through abstract base classes,
protocols, or simply stable method contracts.

A contract may specify:

    - available operations
    - accepted inputs
    - returned outputs
    - error behavior
    - side effects
    - invariants

An interface is therefore more than a method name.

It represents an agreement between components.
""")


from abc import ABC, abstractmethod


class NotificationSender(ABC):

    @abstractmethod
    def send(self, recipient, message):
        pass


class EmailNotificationSender(NotificationSender):

    def send(self, recipient, message):
        print(f"EMAIL -> {recipient}: {message}")


class SMSNotificationSender(NotificationSender):

    def send(self, recipient, message):
        print(f"SMS -> {recipient}: {message}")


def notify_user(sender, recipient, message):
    sender.send(recipient, message)


notify_user(
    EmailNotificationSender(),
    "alice@example.com",
    "Your order has shipped."
)

notify_user(
    SMSNotificationSender(),
    "+911234567890",
    "Your order has shipped."
)


# ============================================================================
# 12. DEPENDENCY DIRECTION
# ============================================================================

section("12. DEPENDENCY DIRECTION")

explain("""
Dependencies create a directed graph.

If:

    A -> B

then A depends on B.

In poorly designed systems, high-level business logic often depends
directly on low-level implementation details.

For example:

    OrderService -> PostgreSQLDriver
    OrderService -> StripeClient
    OrderService -> SMTPClient

This means business logic is aware of infrastructure details.

A stronger arrangement is:

    OrderService -> abstractions <- infrastructure

The business rule defines what it needs.

Infrastructure provides implementations of those needs.

This idea is closely connected to dependency inversion.
""")


# ============================================================================
# 13. DEPENDENCY INJECTION
# ============================================================================

section("13. DEPENDENCY INJECTION")

explain("""
Dependency injection means that an object receives the dependencies it
needs instead of constructing those dependencies internally.

Bad:

    class OrderService:
        def __init__(self):
            self.repository = PostgreSQLRepository()

Better:

    class OrderService:
        def __init__(self, repository):
            self.repository = repository

The second design makes the dependency explicit and replaceable.

It also makes testing easier because a fake or mock implementation can
be supplied.
""")


class InMemoryOrderRepository:

    def __init__(self):
        self.orders = []

    def save(self, order):
        self.orders.append(order)

    def find_all(self):
        return self.orders


class OrderService:

    def __init__(self, repository):
        self.repository = repository

    def create_order(self, customer, amount):
        order = {
            "customer": customer,
            "amount": amount
        }

        self.repository.save(order)

        return order


repo = InMemoryOrderRepository()
service = OrderService(repo)

service.create_order("Alice", 2500)

print(repo.find_all())


# ============================================================================
# 14. SOLID PRINCIPLES
# ============================================================================

section("14. SOLID PRINCIPLES")

explain("""
SOLID is a group of five object-oriented design principles.

S = Single Responsibility Principle
O = Open/Closed Principle
L = Liskov Substitution Principle
I = Interface Segregation Principle
D = Dependency Inversion Principle

These principles are not laws.

They are design heuristics used to reason about responsibility,
dependencies, change, and substitutability.
""")


# ============================================================================
# 15. SINGLE RESPONSIBILITY PRINCIPLE
# ============================================================================

section("15. SINGLE RESPONSIBILITY PRINCIPLE")

explain("""
The Single Responsibility Principle states that a class should have
one reason to change.

The important phrase is:

    reason to change

It does not simply mean:

    "A class must contain only one method."

For example, a report generator might have multiple operations that
belong to report generation.

The problem begins when the same class changes because of unrelated
concerns such as:

    - database schema changes
    - PDF formatting changes
    - business rule changes
    - email provider changes

Those represent different reasons to change.
""")


class ReportGenerator:

    def generate_data(self):
        return ["Alice", "Bob", "Charlie"]

    def format_report(self, data):
        return "\n".join(data)


class ReportRepository:

    def save(self, report):
        print("Report saved")


class ReportEmailService:

    def send(self, report, email):
        print("Report sent to", email)


# ============================================================================
# 16. OPEN/CLOSED PRINCIPLE
# ============================================================================

section("16. OPEN/CLOSED PRINCIPLE")

explain("""
The Open/Closed Principle states that software entities should be open
for extension but closed for modification.

The idea is not that code should literally never be changed.

The idea is that new behavior should often be introduced by adding new
implementations rather than repeatedly modifying stable logic.

For example, a payment system can define a PaymentMethod abstraction.
New payment methods can implement that abstraction.
""")


class PaymentMethod(ABC):

    @abstractmethod
    def pay(self, amount):
        pass


class CreditCardPayment(PaymentMethod):

    def pay(self, amount):
        return f"Credit card payment: {amount}"


class UpiPayment(PaymentMethod):

    def pay(self, amount):
        return f"UPI payment: {amount}"


class CashPayment(PaymentMethod):

    def pay(self, amount):
        return f"Cash payment: {amount}"


def checkout(payment_method, amount):
    return payment_method.pay(amount)


print(checkout(CreditCardPayment(), 1000))
print(checkout(UpiPayment(), 1500))
print(checkout(CashPayment(), 700))


# ============================================================================
# 17. LISKOV SUBSTITUTION PRINCIPLE
# ============================================================================

section("17. LISKOV SUBSTITUTION PRINCIPLE")

explain("""
The Liskov Substitution Principle concerns substitutability.

If B is a subtype of A, code expecting A should generally be able to
work correctly when given B.

Inheritance is therefore not simply about sharing code.

It represents a behavioral relationship.

A subtype that violates the expectations of its parent abstraction is
often a sign that the inheritance hierarchy is wrong.

For example, if a base class promises that withdraw() always works
under certain conditions, a subclass should not unexpectedly break
that contract.

Subtyping must preserve behavioral expectations.
""")


class Bird:

    def fly(self):
        return "Flying"


class Sparrow(Bird):

    pass


sparrow = Sparrow()
print(sparrow.fly())


explain("""
A classic design problem appears when a general Bird abstraction assumes
that every bird can fly.

A penguin is biologically a bird but does not satisfy the behavioral
contract of a flying bird.

The better design is to separate concepts such as:

    Bird
    FlyingBird

rather than forcing every Bird to implement flying behavior.
""")


class Animal:
    pass


class FlyingAnimal(Animal):

    def fly(self):
        return "Flying"


class Penguin(Animal):

    def swim(self):
        return "Swimming"


class Eagle(FlyingAnimal):

    pass


print(Eagle().fly())
print(Penguin().swim())


# ============================================================================
# 18. INTERFACE SEGREGATION PRINCIPLE
# ============================================================================

section("18. INTERFACE SEGREGATION PRINCIPLE")

explain("""
The Interface Segregation Principle says that clients should not be
forced to depend on methods they do not need.

A large interface can create unnecessary coupling.

Instead of:

    Machine
        print()
        scan()
        fax()
        staple()
        bind()

A simple printer should not be forced to implement scanning, faxing,
stapling, and binding.

Smaller focused interfaces are often easier to implement and use.
""")


class Printer:

    def print_document(self, document):
        print("Printing:", document)


class Scanner:

    def scan_document(self):
        return "Scanned document"


class Fax:

    def fax_document(self, document):
        print("Faxing:", document)


class MultiFunctionPrinter(Printer, Scanner, Fax):
    pass


mfp = MultiFunctionPrinter()

mfp.print_document("Report")
print(mfp.scan_document())
mfp.fax_document("Report")


# ============================================================================
# 19. DEPENDENCY INVERSION PRINCIPLE
# ============================================================================

section("19. DEPENDENCY INVERSION PRINCIPLE")

explain("""
The Dependency Inversion Principle has two important ideas:

1. High-level modules should not depend directly on low-level modules.
2. Both should depend on abstractions.

The second idea also means abstractions should represent concepts
important to the application rather than merely mirroring technical
details.

For example:

    Business logic
        |
        v
    PaymentGateway abstraction
        ^
        |
    Stripe implementation

The business logic does not need to know that Stripe exists.

This makes infrastructure replaceable.
""")


class PaymentGateway(ABC):

    @abstractmethod
    def charge(self, amount):
        pass


class StripeGateway(PaymentGateway):

    def charge(self, amount):
        print("Charging through Stripe:", amount)


class MockGateway(PaymentGateway):

    def charge(self, amount):
        print("Mock payment:", amount)


class CheckoutService:

    def __init__(self, gateway):
        self.gateway = gateway

    def checkout(self, amount):
        self.gateway.charge(amount)


checkout_service = CheckoutService(StripeGateway())
checkout_service.checkout(500)

checkout_service = CheckoutService(MockGateway())
checkout_service.checkout(500)


# ============================================================================
# 20. COMPOSITION OVER INHERITANCE
# ============================================================================

section("20. COMPOSITION OVER INHERITANCE")

explain("""
Composition means building an object using other objects.

Inheritance creates an "is-a" relationship.

Composition creates a "has-a" relationship.

Inheritance:

    Car is a Vehicle.

Composition:

    Car has an Engine.

Inheritance can be useful when there is a genuine behavioral subtype
relationship.

Composition is often more flexible because individual behaviors can be
replaced independently.
""")


class Engine:

    def start(self):
        return "Engine started"


class ElectricEngine:

    def start(self):
        return "Electric engine started"


class Car:

    def __init__(self, engine):
        self.engine = engine

    def start(self):
        return self.engine.start()


car1 = Car(Engine())
car2 = Car(ElectricEngine())

print(car1.start())
print(car2.start())


# ============================================================================
# 21. POLYMORPHISM
# ============================================================================

section("21. POLYMORPHISM")

explain("""
Polymorphism means that different objects can respond to the same
operation according to their own implementation.

The caller uses a common contract.

The implementation varies.

This allows systems to be extended without changing the code that
uses the abstraction.
""")


class Shape:

    def area(self):
        raise NotImplementedError


class Rectangle(Shape):

    def __init__(self, width, height):
        self.width = width
        self.height = height

    def area(self):
        return self.width * self.height


class Circle(Shape):

    def __init__(self, radius):
        self.radius = radius

    def area(self):
        import math
        return math.pi * self.radius ** 2


def total_area(shapes):
    return sum(shape.area() for shape in shapes)


shapes = [
    Rectangle(10, 5),
    Circle(3)
]

print("Total area:", total_area(shapes))


# ============================================================================
# 22. DESIGN BY CONTRACT
# ============================================================================

section("22. DESIGN BY CONTRACT")

explain("""
Design by Contract describes software behavior using:

    Preconditions
    Postconditions
    Invariants

Precondition:
    What must be true before an operation executes.

Postcondition:
    What should be true after successful execution.

Invariant:
    What should remain true throughout the valid lifetime of an object.

Example:

    withdraw(amount)

Precondition:
    amount > 0
    amount <= balance

Postcondition:
    balance has decreased by amount

Invariant:
    balance >= 0
""")


class ContractAccount:

    def __init__(self, balance):
        if balance < 0:
            raise ValueError("Invalid initial balance")

        self.balance = balance

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("Amount must be positive")

        if amount > self.balance:
            raise ValueError("Insufficient funds")

        old_balance = self.balance

        self.balance -= amount

        assert self.balance == old_balance - amount
        assert self.balance >= 0


account = ContractAccount(1000)
account.withdraw(300)

print("Balance:", account.balance)


# ============================================================================
# 23. IMMUTABILITY
# ============================================================================

section("23. IMMUTABILITY")

explain("""
An immutable object does not change its state after creation.

Immutability can reduce the number of possible states a program can
enter.

Mutable object:

    state can change over time.

Immutable object:

    state remains fixed.

Immutability is especially useful when objects are shared between
components, because one component cannot unexpectedly modify an object
being used elsewhere.
""")


from dataclasses import dataclass


@dataclass(frozen=True)
class Money:

    amount: float
    currency: str


money = Money(100, "INR")

print(money)

# The following would raise an exception:
# money.amount = 500


# ============================================================================
# 24. VALUE OBJECTS
# ============================================================================

section("24. VALUE OBJECTS")

explain("""
A value object is defined by its value rather than by a unique identity.

Examples:

    - Money
    - DateRange
    - Coordinates
    - EmailAddress
    - Temperature
    - Percentage

Two Money objects containing the same amount and currency may be
considered equal even if they are different Python objects.

Value objects often work well when immutable.
""")


money_a = Money(500, "INR")
money_b = Money(500, "INR")

print("Same value:", money_a == money_b)


# ============================================================================
# 25. ENTITY OBJECTS
# ============================================================================

section("25. ENTITIES")

explain("""
An entity is generally identified by identity rather than only by its
current values.

For example:

    User ID = 101

A user's name may change.

The identity remains the same.

This distinction between entities and value objects is important in
domain-oriented design.
""")


@dataclass
class User:

    user_id: int
    name: str


user = User(101, "Alice")

print("User identity:", user.user_id)


# ============================================================================
# 26. PURE FUNCTIONS
# ============================================================================

section("26. PURE FUNCTIONS")

explain("""
A pure function has two useful properties:

1. The same input produces the same output.
2. It does not produce observable side effects.

Pure functions are easy to test and reason about.

Example:

    add_tax(price, rate)

depends only on its inputs.

An impure function might read global state, modify a database, send an
email, or access the current time.
""")


def calculate_tax(price, rate):
    return price * rate


print("Tax:", calculate_tax(1000, 0.18))


# ============================================================================
# 27. SIDE EFFECTS
# ============================================================================

section("27. SIDE EFFECTS")

explain("""
A side effect is an observable interaction outside the local calculation.

Examples:

    - writing to a database
    - modifying a file
    - sending an email
    - changing global state
    - logging
    - making a network request

Side effects are not inherently bad.

Real applications need them.

The design concern is controlling where they occur.

A common design strategy is:

    pure business logic
            +
    isolated side effects

This makes the system easier to test and reason about.
""")


# ============================================================================
# 28. COMMAND AND QUERY SEPARATION
# ============================================================================

section("28. COMMAND AND QUERY SEPARATION")

explain("""
Command Query Separation, often abbreviated CQS, distinguishes between:

Command:
    Performs an action or changes state.

Query:
    Returns information without changing state.

Example:

    account.withdraw(100)

is a command.

    account.get_balance()

is a query.

Keeping these concepts distinct makes APIs easier to understand.

A function that secretly changes state while appearing to merely return
information is harder to reason about.
""")


# ============================================================================
# 29. PURE DOMAIN LOGIC AND INFRASTRUCTURE
# ============================================================================

section("29. DOMAIN LOGIC VERSUS INFRASTRUCTURE")

explain("""
Business rules are different from infrastructure mechanisms.

Domain logic may say:

    "A customer receives a 10 percent discount."

Infrastructure may say:

    "The customer record is stored in PostgreSQL."

Domain logic:

    "An invoice must not be finalized without payment."

Infrastructure:

    "The payment provider is accessed through HTTPS."

Keeping these concepts separate allows business rules to remain stable
while technical implementations change.
""")


class DiscountPolicy:

    def discount(self, amount):
        if amount >= 10000:
            return amount * 0.10

        return 0


policy = DiscountPolicy()

print("Discount:", policy.discount(15000))


# ============================================================================
# 30. REFACTORING
# ============================================================================

section("30. REFACTORING")

explain("""
Refactoring means changing the internal structure of software without
changing its externally intended behavior.

Typical refactorings include:

    - extracting a function
    - extracting a class
    - renaming variables
    - removing duplication
    - simplifying conditionals
    - replacing inheritance with composition
    - introducing an abstraction
    - moving responsibilities

Refactoring is not the same as adding new functionality.

A useful development cycle is:

    make behavior work
        ->
    verify behavior
        ->
    improve structure

Tests provide confidence that behavior has not unintentionally changed.
""")


# ============================================================================
# 31. CODE SMELLS
# ============================================================================

section("31. COMMON CODE SMELLS")

explain("""
Code smells are signs that the structure of code may have problems.

Common examples include:

    Long Method
    Large Class
    Duplicate Code
    Long Parameter List
    Feature Envy
    Primitive Obsession
    Shotgun Surgery
    Divergent Change
    God Object
    Deeply Nested Conditionals
    Excessive Coupling

A smell is not automatically a bug.

It is a signal that deserves investigation.

For example:

    Long Method

may indicate that multiple responsibilities should be extracted.

    Shotgun Surgery

means one conceptual change requires modifications across many
different locations.

    God Object

means one component has accumulated too many responsibilities.
""")


# ============================================================================
# 32. DUPLICATION
# ============================================================================

section("32. DUPLICATION AND DRY")

explain("""
DRY means:

    Don't Repeat Yourself.

The deeper idea is not simply to avoid identical lines of code.

It is to avoid having the same knowledge represented independently in
multiple places.

If a business rule exists in five locations, changing the rule requires
finding all five locations.

Duplication therefore increases the risk of inconsistency.

At the same time, premature abstraction can be harmful.

Two pieces of code that look similar today may represent different
concepts and may legitimately evolve differently.

The goal is to remove meaningful duplication, not every repeated line.
""")


# ============================================================================
# 33. KISS
# ============================================================================

section("33. KISS")

explain("""
KISS is commonly understood as:

    Keep It Simple.

Simple design is generally preferable when it satisfies the actual
requirements.

A solution with:

    2 classes
    3 functions

may be better than a solution with:

    20 classes
    8 interfaces
    4 factories
    3 adapters

if both solve the same problem and the larger design provides no real
benefit.

Complexity should be justified by a requirement or meaningful design
constraint.
""")


# ============================================================================
# 34. YAGNI
# ============================================================================

section("34. YAGNI")

explain("""
YAGNI means:

    You Aren't Gonna Need It.

The principle warns against implementing speculative functionality
before it is actually required.

For example, creating an abstraction for twelve hypothetical database
providers when the system currently has one database may increase
complexity without providing value.

Design for known requirements and likely change.

Do not design every imaginable future feature into the present system.
""")


# ============================================================================
# 35. OVERENGINEERING
# ============================================================================

section("35. OVERENGINEERING")

explain("""
Overengineering occurs when a solution contains complexity that is not
justified by the problem.

Examples:

    - excessive abstraction
    - unnecessary microservices
    - unnecessary design patterns
    - excessive configuration
    - too many layers
    - generic frameworks for simple problems

Underengineering is also possible.

A system can become difficult to maintain because it has no meaningful
boundaries.

Good design is therefore a balance.

The correct amount of structure depends on:

    complexity
    team size
    expected change
    reliability requirements
    performance requirements
    security requirements
    operational constraints
""")


# ============================================================================
# 36. DESIGN PATTERNS
# ============================================================================

section("36. DESIGN PATTERNS")

explain("""
A design pattern is a reusable way of structuring a recurring design
problem.

Patterns are not libraries.

A pattern is not code that must always be copied.

Patterns describe relationships among responsibilities and objects.

Common categories:

Creational:
    Factory
    Abstract Factory
    Builder
    Prototype
    Singleton

Structural:
    Adapter
    Decorator
    Facade
    Composite
    Proxy

Behavioral:
    Strategy
    Observer
    Command
    State
    Template Method
    Chain of Responsibility
""")


# ============================================================================
# 37. STRATEGY PATTERN
# ============================================================================

section("37. STRATEGY PATTERN")

explain("""
Strategy encapsulates interchangeable algorithms behind a common
interface.

It is useful when a behavior can vary independently from the object
using that behavior.
""")


class PricingStrategy(ABC):

    @abstractmethod
    def calculate(self, amount):
        pass


class RegularPricing(PricingStrategy):

    def calculate(self, amount):
        return amount


class PremiumPricing(PricingStrategy):

    def calculate(self, amount):
        return amount * 0.90


class DiscountPricing(PricingStrategy):

    def calculate(self, amount):
        return amount * 0.80


class Cart:

    def __init__(self, pricing_strategy):
        self.pricing_strategy = pricing_strategy

    def total(self, amount):
        return self.pricing_strategy.calculate(amount)


print(Cart(RegularPricing()).total(1000))
print(Cart(PremiumPricing()).total(1000))
print(Cart(DiscountPricing()).total(1000))


# ============================================================================
# 38. FACTORY PATTERN
# ============================================================================

section("38. FACTORY PATTERN")

explain("""
A factory centralizes object creation.

Factories become useful when:

    - construction is complicated
    - the concrete type depends on configuration
    - callers should not know implementation details
    - creation rules change independently
""")


class NotificationFactory:

    @staticmethod
    def create(notification_type):

        if notification_type == "email":
            return EmailNotificationSender()

        if notification_type == "sms":
            return SMSNotificationSender()

        raise ValueError("Unsupported notification type")


sender = NotificationFactory.create("email")
sender.send("alice@example.com", "Hello")


# ============================================================================
# 39. ADAPTER PATTERN
# ============================================================================

section("39. ADAPTER PATTERN")

explain("""
An Adapter allows an incompatible interface to work with a system
expecting another interface.

Imagine the application expects:

    send(message)

but an external library provides:

    deliver(payload)

The adapter translates between the two interfaces.
""")


class ExternalEmailProvider:

    def deliver(self, payload):
        print("External provider:", payload)


class EmailAdapter(NotificationSender):

    def __init__(self, provider):
        self.provider = provider

    def send(self, recipient, message):
        payload = {
            "to": recipient,
            "message": message
        }

        self.provider.deliver(payload)


adapter = EmailAdapter(ExternalEmailProvider())

adapter.send(
    "alice@example.com",
    "Adapter example"
)


# ============================================================================
# 40. DECORATOR PATTERN
# ============================================================================

section("40. DECORATOR PATTERN")

explain("""
Decorator adds behavior around an existing object without changing the
object's class.

It is useful for optional behavior such as:

    - logging
    - caching
    - authorization
    - metrics
    - retries
""")


class BasicService:

    def execute(self):
        print("Service executed")


class LoggingDecorator:

    def __init__(self, wrapped):
        self.wrapped = wrapped

    def execute(self):
        print("Before execution")
        self.wrapped.execute()
        print("After execution")


service = LoggingDecorator(BasicService())

service.execute()


# ============================================================================
# 41. FACADE PATTERN
# ============================================================================

section("41. FACADE PATTERN")

explain("""
A Facade provides a simpler interface over a complex subsystem.

For example, placing an order might involve:

    inventory
    payment
    shipping
    notification

The caller may prefer:

    order_facade.place_order(...)

rather than interacting with every subsystem directly.
""")


class Inventory:

    def reserve(self, item):
        print("Inventory reserved:", item)


class Payment:

    def charge(self, amount):
        print("Payment charged:", amount)


class Shipping:

    def schedule(self, item):
        print("Shipping scheduled:", item)


class OrderFacade:

    def __init__(self):
        self.inventory = Inventory()
        self.payment = Payment()
        self.shipping = Shipping()

    def place_order(self, item, amount):
        self.inventory.reserve(item)
        self.payment.charge(amount)
        self.shipping.schedule(item)


facade = OrderFacade()

facade.place_order("Laptop", 70000)


# ============================================================================
# 42. OBSERVER PATTERN
# ============================================================================

section("42. OBSERVER PATTERN")

explain("""
Observer establishes a relationship where one object publishes an event
and other objects react to it.

This can reduce direct coupling between the event producer and its
consumers.

Example:

    Order placed
        |
        +--> email service
        +--> analytics
        +--> inventory
        +--> notification system

The publisher does not necessarily need detailed knowledge of every
consumer.
""")


class EventPublisher:

    def __init__(self):
        self.listeners = []

    def subscribe(self, listener):
        self.listeners.append(listener)

    def publish(self, event):
        for listener in self.listeners:
            listener(event)


def email_listener(event):
    print("Email listener received:", event)


def analytics_listener(event):
    print("Analytics listener received:", event)


publisher = EventPublisher()

publisher.subscribe(email_listener)
publisher.subscribe(analytics_listener)

publisher.publish("ORDER_CREATED")


# ============================================================================
# 43. STATE PATTERN
# ============================================================================

section("43. STATE PATTERN")

explain("""
The State pattern is useful when an object's behavior changes according
to its current state.

Example order states:

    CREATED
    PAID
    SHIPPED
    DELIVERED
    CANCELLED

Instead of creating a giant conditional structure, behavior can be
associated with state objects.

The pattern is especially useful when state-dependent behavior becomes
large and complicated.
""")


class OrderState(ABC):

    @abstractmethod
    def next(self):
        pass


class CreatedState(OrderState):

    def next(self):
        return PaidState()


class PaidState(OrderState):

    def next(self):
        return ShippedState()


class ShippedState(OrderState):

    def next(self):
        return DeliveredState()


class DeliveredState(OrderState):

    def next(self):
        return self


class Order:

    def __init__(self):
        self.state = CreatedState()

    def advance(self):
        self.state = self.state.next()


order = Order()

for _ in range(4):
    print("State:", type(order.state).__name__)
    order.advance()


# ============================================================================
# 44. COMMAND PATTERN
# ============================================================================

section("44. COMMAND PATTERN")

explain("""
Command represents an operation as an object.

This can enable:

    - queues
    - retries
    - logging
    - undo
    - scheduling
    - delayed execution

Instead of directly performing:

    receiver.operation()

the application can create:

    Command(receiver)

and execute it later.
""")


class Light:

    def turn_on(self):
        print("Light ON")

    def turn_off(self):
        print("Light OFF")


class TurnOnCommand:

    def __init__(self, light):
        self.light = light

    def execute(self):
        self.light.turn_on()


command = TurnOnCommand(Light())
command.execute()


# ============================================================================
# 45. ARCHITECTURAL DESIGN
# ============================================================================

section("45. SOFTWARE ARCHITECTURE")

explain("""
Software design and software architecture are closely related.

A useful distinction is:

Software design:
    Detailed organization of components and responsibilities.

Software architecture:
    High-level organization of the system, its major boundaries,
    dependencies, communication mechanisms, and important constraints.

Architecture answers questions such as:

    - What are the major subsystems?
    - Where are the boundaries?
    - How do systems communicate?
    - Where does data live?
    - Which components can depend on which?
    - How is failure handled?
    - What determines scalability?
""")


# ============================================================================
# 46. LAYERED ARCHITECTURE
# ============================================================================

section("46. LAYERED ARCHITECTURE")

explain("""
A common architecture divides an application into layers.

A typical arrangement is:

    Presentation
        |
        v
    Application / Service
        |
        v
    Domain
        |
        v
    Infrastructure

Presentation handles interaction.

Application coordinates use cases.

Domain contains business concepts and rules.

Infrastructure handles technical mechanisms such as databases,
external APIs, files, messaging, and network communication.

The exact number of layers is not fixed.
""")


class OrderDomain:

    def calculate_total(self, price, quantity):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        return price * quantity


class OrderApplicationService:

    def __init__(self, domain):
        self.domain = domain

    def create_order(self, price, quantity):
        return self.domain.calculate_total(price, quantity)


domain = OrderDomain()
application_service = OrderApplicationService(domain)

print(
    "Order total:",
    application_service.create_order(500, 3)
)


# ============================================================================
# 47. HEXAGONAL ARCHITECTURE
# ============================================================================

section("47. HEXAGONAL ARCHITECTURE")

explain("""
Hexagonal Architecture is also called Ports and Adapters.

The central idea is to keep application and domain logic independent
from external systems.

A port describes what the application needs.

An adapter connects a concrete technology to that port.

Examples:

    Application
        |
        +--> Payment Port
        |       ^
        |       |
        |   Stripe Adapter
        |
        +--> Repository Port
                ^
                |
            PostgreSQL Adapter

The important direction is toward the application core.

External technologies remain replaceable.
""")


# ============================================================================
# 48. CLEAN ARCHITECTURE
# ============================================================================

section("48. CLEAN ARCHITECTURE")

explain("""
Clean Architecture emphasizes dependency direction.

A conceptual arrangement is:

    Entities
       ^
    Use Cases
       ^
    Interface Adapters
       ^
    Frameworks / Drivers

The central idea is that business rules should not be tightly coupled
to frameworks, databases, user interfaces, or external services.

The outer layers depend on inner concepts.

The inner business rules should not depend on the details of the outer
world.
""")


# ============================================================================
# 49. DOMAIN-DRIVEN DESIGN CONCEPTS
# ============================================================================

section("49. DOMAIN-DRIVEN DESIGN FOUNDATIONS")

explain("""
Domain-Driven Design, or DDD, focuses on modeling complex business
domains.

Important concepts include:

    Entity
    Value Object
    Aggregate
    Aggregate Root
    Repository
    Domain Service
    Domain Event
    Bounded Context
    Ubiquitous Language

Ubiquitous Language means that developers and domain experts use
consistent terminology.

A Bounded Context defines a boundary within which a model has a
particular meaning.

For example, "Customer" in a sales system may not have exactly the same
meaning as "Customer" in a support system.

DDD is most useful when the domain itself is complex.
""")


# ============================================================================
# 50. AGGREGATES
# ============================================================================

section("50. AGGREGATES")

explain("""
An aggregate is a consistency boundary around related domain objects.

One object acts as the Aggregate Root.

External code normally interacts through the root rather than directly
modifying every internal object.

For example:

    Order
      |
      +-- OrderItem
      +-- OrderItem
      +-- OrderItem

The Order may be the aggregate root.

Rules involving the consistency of the order can therefore be enforced
through Order.
""")


class OrderItem:

    def __init__(self, product, quantity):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        self.product = product
        self.quantity = quantity


class AggregateOrder:

    def __init__(self):
        self._items = []

    def add_item(self, product, quantity):
        self._items.append(
            OrderItem(product, quantity)
        )

    @property
    def items(self):
        return tuple(self._items)


order = AggregateOrder()

order.add_item("Keyboard", 2)
order.add_item("Mouse", 1)

print("Order items:", order.items)


# ============================================================================
# 51. EVENTS
# ============================================================================

section("51. DOMAIN EVENTS")

explain("""
A domain event represents something meaningful that has happened in the
business domain.

Examples:

    OrderPlaced
    PaymentReceived
    AccountCreated
    ShipmentDispatched

Events are expressed as facts.

An event is normally written in past tense because it represents
something that already happened.

Events can allow other parts of the system to react without the
original component directly invoking every consumer.
""")


@dataclass(frozen=True)
class OrderPlaced:

    order_id: int
    amount: float


event = OrderPlaced(101, 5000)

print("Event:", event)


# ============================================================================
# 52. DATABASE DESIGN AS A DESIGN CONCERN
# ============================================================================

section("52. DATA AND OBJECT DESIGN")

explain("""
Software design must account for data ownership and persistence.

Questions include:

    - Which component owns the data?
    - Who is allowed to modify it?
    - What consistency is required?
    - What happens when data is unavailable?
    - Which operations need transactions?
    - What data should be cached?
    - What data should be immutable?
    - Which fields are derived?

A common design mistake is allowing database structure to dictate every
business object.

Database models and domain models may overlap, but they do not have to
be identical.
""")


# ============================================================================
# 53. TRANSACTIONS
# ============================================================================

section("53. TRANSACTIONAL THINKING")

explain("""
A transaction groups operations that must satisfy a consistency rule.

For example, transferring money may involve:

    subtract from account A
    add to account B

If only the first operation succeeds, the system becomes inconsistent.

The design must therefore consider:

    atomicity
    consistency
    isolation
    durability

These concepts are commonly associated with ACID transactions.

Software design must identify where transactional boundaries belong.
""")


# ============================================================================
# 54. CONCURRENCY
# ============================================================================

section("54. CONCURRENCY AND SHARED STATE")

explain("""
Concurrency introduces another class of design problems.

When multiple operations occur at the same time, shared mutable state
can produce:

    race conditions
    lost updates
    inconsistent reads
    deadlocks

A design that is correct for one sequential execution may fail under
concurrent execution.

Useful strategies include:

    - immutability
    - synchronization
    - transactional boundaries
    - optimistic locking
    - pessimistic locking
    - message passing
    - reducing shared mutable state
""")


# ============================================================================
# 55. ERROR HANDLING
# ============================================================================

section("55. ERROR HANDLING AS A DESIGN CONCERN")

explain("""
Errors should be designed rather than added randomly through the code.

Different failures have different meanings.

Examples:

Validation error:
    Input does not satisfy a business rule.

Not found:
    Requested resource does not exist.

Authentication failure:
    Identity cannot be verified.

Authorization failure:
    The caller is not permitted to perform the operation.

Infrastructure failure:
    Database, network, or external service failed.

Programming error:
    The software violated an assumption.

These should not necessarily be represented using the same mechanism.
""")


class InsufficientFundsError(Exception):
    pass


class DesignedAccount:

    def __init__(self, balance):
        self.balance = balance

    def withdraw(self, amount):

        if amount > self.balance:
            raise InsufficientFundsError(
                "Account does not contain enough money."
            )

        self.balance -= amount


account = DesignedAccount(1000)

try:
    account.withdraw(1500)
except InsufficientFundsError as error:
    print("Business error:", error)


# ============================================================================
# 56. LOGGING
# ============================================================================

section("56. LOGGING")

explain("""
Logging is an operational concern.

Good logging provides useful context:

    - what happened
    - when it happened
    - which operation was involved
    - which request or transaction was involved
    - whether the operation succeeded or failed

Logging should not be scattered blindly throughout every business
function.

It is often useful to establish boundaries where operational information
is recorded consistently.
""")


def process_payment(amount):
    print(f"[INFO] Starting payment: {amount}")

    if amount <= 0:
        print("[ERROR] Invalid payment amount")
        raise ValueError("Invalid amount")

    print("[INFO] Payment completed")


process_payment(1000)


# ============================================================================
# 57. TESTABILITY
# ============================================================================

section("57. DESIGN FOR TESTABILITY")

explain("""
Testability is an important property of good design.

A component is easier to test when:

    - dependencies are explicit
    - side effects are isolated
    - responsibilities are focused
    - behavior has clear inputs and outputs
    - external systems can be replaced

Dependency injection helps because a test can provide a fake dependency.
""")


class FakePaymentGateway:

    def __init__(self):
        self.charges = []

    def charge(self, amount):
        self.charges.append(amount)


gateway = FakePaymentGateway()

service = CheckoutService(gateway)

service.checkout(2500)

assert gateway.charges == [2500]

print("Test passed")


# ============================================================================
# 58. MOCKS, STUBS, AND FAKES
# ============================================================================

section("58. TEST DOUBLES")

explain("""
A test double is a replacement for a real dependency during testing.

Stub:
    Provides predetermined responses.

Fake:
    Provides a simplified working implementation.

Mock:
    Usually verifies that particular interactions occurred.

Spy:
    Records calls so they can be inspected.

The distinction is useful because tests should verify meaningful
behavior rather than implementation details unnecessarily.
""")


# ============================================================================
# 59. API DESIGN
# ============================================================================

section("59. API DESIGN")

explain("""
An API is a contract between software components.

A good API should make valid usage easy and invalid usage difficult.

Important API design concerns include:

    naming
    consistency
    input validation
    output structure
    error semantics
    versioning
    compatibility
    idempotency
    documentation

An API should expose concepts at the right level.

Too low-level:
    callers must understand implementation details.

Too high-level:
    callers may lack required control.
""")


# ============================================================================
# 60. IDEMPOTENCY
# ============================================================================

section("60. IDEMPOTENCY")

explain("""
An operation is idempotent when repeating it produces the same intended
result as performing it once.

For example:

    setting an account status to ACTIVE

can be idempotent.

A payment operation may not naturally be idempotent because repeating
it could charge the customer twice.

Distributed systems often use idempotency keys to prevent accidental
duplicate operations.
""")


def set_status(current_status, new_status):
    return new_status


status = "ACTIVE"

status = set_status(status, "ACTIVE")
status = set_status(status, "ACTIVE")

print("Status:", status)


# ============================================================================
# 61. BACKWARD COMPATIBILITY
# ============================================================================

section("61. BACKWARD COMPATIBILITY")

explain("""
When software is consumed by other systems, changing an interface can
break existing clients.

Backward compatibility means that existing consumers continue to work
after a change.

Compatibility matters for:

    APIs
    libraries
    database schemas
    message formats
    configuration
    file formats

Design decisions should consider whether consumers are internal,
external, controlled, or unknown.
""")


# ============================================================================
# 62. VERSIONING
# ============================================================================

section("62. VERSIONING")

explain("""
Versioning provides a controlled way to evolve contracts.

Examples include:

    API versioning
    library versioning
    schema versioning
    protocol versioning

A version should represent meaningful compatibility boundaries rather
than arbitrary changes.

The central design problem is:

    How can the system evolve without unexpectedly breaking consumers?
""")


# ============================================================================
# 63. SCALABILITY
# ============================================================================

section("63. SCALABILITY")

explain("""
Scalability concerns how system capacity changes as demand increases.

Vertical scaling:
    Increase resources of an existing machine.

Horizontal scaling:
    Add more machines or instances.

Software design affects scalability through:

    - state management
    - database access
    - caching
    - concurrency
    - communication patterns
    - workload distribution

A stateless service is often easier to scale horizontally because any
instance can handle a request.
""")


# ============================================================================
# 64. CACHING
# ============================================================================

section("64. CACHING")

explain("""
Caching stores previously computed or retrieved information so that
future requests can be served more quickly.

Caching introduces design questions:

    - What should be cached?
    - For how long?
    - When does cached data become invalid?
    - What happens when the cache is unavailable?
    - Can stale data be accepted?
    - Who owns cache invalidation?

Caching is powerful but introduces consistency and operational
complexity.

The cache should generally be treated as an optimization rather than
the sole source of truth unless the architecture explicitly defines it
otherwise.
""")


# ============================================================================
# 65. SYNCHRONOUS AND ASYNCHRONOUS COMMUNICATION
# ============================================================================

section("65. SYNCHRONOUS VERSUS ASYNCHRONOUS DESIGN")

explain("""
Synchronous communication means the caller waits for a response.

Asynchronous communication allows the producer and consumer to operate
more independently.

Synchronous:

    request
      |
      v
    service
      |
      v
    response

Asynchronous:

    producer
       |
       v
    message
       |
       v
    queue
       |
       v
    consumer

Asynchronous designs can improve resilience and decoupling, but they
also introduce:

    - eventual consistency
    - message ordering concerns
    - duplicate delivery
    - retry behavior
    - monitoring complexity
""")


# ============================================================================
# 66. DISTRIBUTED SYSTEM DESIGN
# ============================================================================

section("66. DISTRIBUTED SYSTEM DESIGN")

explain("""
When components run on different machines, assumptions about local
execution no longer hold.

Networks can:

    fail
    delay
    duplicate messages
    reorder messages
    disconnect temporarily

A distributed system must therefore account for partial failure.

Important design concerns include:

    timeouts
    retries
    idempotency
    circuit breakers
    backpressure
    message ordering
    consistency
    service discovery
    observability

A remote call is fundamentally different from a local function call
because it can fail independently of the caller.
""")


# ============================================================================
# 67. RETRIES
# ============================================================================

section("67. RETRY DESIGN")

explain("""
Retries are useful when failures are temporary.

But retrying blindly can make an outage worse.

For example:

    service A calls service B
    B becomes overloaded
    A retries repeatedly
    B receives even more requests
    overload increases

Good retry design considers:

    exponential backoff
    maximum attempts
    jitter
    idempotency
    timeout limits

Not every error should be retried.

A validation error is normally not fixed by trying the same request
again.
""")


# ============================================================================
# 68. TIMEOUTS
# ============================================================================

section("68. TIMEOUTS")

explain("""
A network request without a sensible timeout can wait indefinitely.

Timeouts define how long a caller is willing to wait.

Timeout design should reflect:

    expected latency
    business requirements
    dependency behavior
    retry strategy

Timeouts prevent one slow dependency from consuming resources
indefinitely.
""")


# ============================================================================
# 69. CIRCUIT BREAKER CONCEPT
# ============================================================================

section("69. CIRCUIT BREAKER")

explain("""
A circuit breaker protects a system from repeatedly calling a failing
dependency.

Typical states:

    CLOSED
        Normal operation.

    OPEN
        Calls are blocked because failures have exceeded a threshold.

    HALF_OPEN
        A limited test is performed to determine whether recovery has
        occurred.

The pattern prevents cascading failures and allows unhealthy
dependencies time to recover.
""")


# ============================================================================
# 70. OBSERVABILITY
# ============================================================================

section("70. OBSERVABILITY")

explain("""
Observability describes the ability to understand the internal state of
a system from its external outputs.

Three commonly discussed signals are:

    Logs
    Metrics
    Traces

Logs:
    Detailed events.

Metrics:
    Numerical measurements over time.

Traces:
    Follow a request through multiple components.

Good architecture considers observability early because distributed
systems can be extremely difficult to diagnose without sufficient
operational information.
""")


# ============================================================================
# 71. SECURITY BY DESIGN
# ============================================================================

section("71. SECURITY BY DESIGN")

explain("""
Security should be treated as a design property rather than a final
layer added after implementation.

Design questions include:

    - Who is the user?
    - What are they allowed to do?
    - Which data can they access?
    - What happens if input is malicious?
    - Where are secrets stored?
    - Which operations require authentication?
    - Which operations require authorization?
    - What data should be encrypted?
    - What actions need auditing?

Important principles include:

    least privilege
    defense in depth
    secure defaults
    input validation
    explicit authorization
    minimal data exposure
""")


# ============================================================================
# 72. FAIL FAST
# ============================================================================

section("72. FAIL FAST")

explain("""
Fail-fast design detects invalid conditions as early as possible.

For example:

    invalid input
        ->
    reject immediately

rather than allowing invalid data to move through several layers and
fail much later.

Fail-fast behavior reduces the distance between the cause and the
failure.
""")


# ============================================================================
# 73. DEFENSIVE DESIGN
# ============================================================================

section("73. DEFENSIVE DESIGN")

explain("""
Defensive design assumes that dependencies, inputs, and external
systems may behave unexpectedly.

This does not mean adding random checks everywhere.

It means identifying meaningful boundaries and validating assumptions
at those boundaries.

Examples:

    validate external input
    verify dependency responses
    enforce invariants
    handle expected failures
    protect against invalid state
""")


# ============================================================================
# 74. CONFIGURATION VERSUS CODE
# ============================================================================

section("74. CONFIGURATION AND DESIGN")

explain("""
Configuration allows behavior to vary without modifying source code.

Examples:

    database URL
    timeout
    feature flags
    logging level
    external service endpoints

But not every decision belongs in configuration.

Excessive configuration can make behavior difficult to understand.

A useful distinction is:

    Stable business rule -> code

    Environment-specific value -> configuration

    Operational tuning -> configuration when appropriate
""")


# ============================================================================
# 75. FEATURE FLAGS
# ============================================================================

section("75. FEATURE FLAGS")

explain("""
Feature flags separate deployment from feature activation.

A feature can exist in the deployed software but remain disabled.

This can support:

    gradual rollout
    testing
    emergency rollback
    experimentation

But feature flags also create temporary states and increase complexity.

A flag should have clear ownership and lifecycle.
""")


# ============================================================================
# 76. DESIGN TRADE-OFFS
# ============================================================================

section("76. DESIGN IS ABOUT TRADE-OFFS")

explain("""
There is rarely a universally perfect architecture.

Design decisions involve trade-offs.

Examples:

    simplicity vs flexibility
    consistency vs availability
    performance vs readability
    abstraction vs directness
    reuse vs independence
    centralization vs distribution
    speed of development vs long-term maintainability

A design decision should therefore be evaluated in context.

The important question is not:

    "Is this pattern good?"

The better question is:

    "What problem does this solve, and what cost does it introduce?"
""")


# ============================================================================
# 77. REVERSIBILITY OF DESIGN DECISIONS
# ============================================================================

section("77. REVERSIBLE AND IRREVERSIBLE DECISIONS")

explain("""
Some design decisions are easy to change later.

Others are expensive.

Examples of potentially expensive decisions:

    database technology
    data ownership
    public API contracts
    distributed service boundaries
    message formats
    authentication architecture

A useful design approach is to spend more reasoning effort on decisions
that are expensive to reverse.

Cheap decisions can often remain simple until more information becomes
available.
""")


# ============================================================================
# 78. BOUNDARIES
# ============================================================================

section("78. BOUNDARIES")

explain("""
A software boundary separates one responsibility, subsystem, or
abstraction from another.

A boundary may exist between:

    UI and application logic
    application and domain logic
    domain and infrastructure
    service and service
    application and external API
    business logic and persistence

Good boundaries control dependency flow.

They also reduce the amount of knowledge that must be shared between
components.
""")


# ============================================================================
# 79. STABLE DEPENDENCIES
# ============================================================================

section("79. STABLE DEPENDENCIES")

explain("""
Some components change frequently.

Others are stable.

A useful design goal is to avoid making stable business rules depend
unnecessarily on unstable implementation details.

For example:

    business rules
        should not be forced to change
        merely because
    database access technology changed.

Dependency direction therefore has architectural consequences.
""")


# ============================================================================
# 80. CHANGE-CENTERED DESIGN
# ============================================================================

section("80. DESIGNING AROUND CHANGE")

explain("""
One of the strongest ways to evaluate software design is to ask:

    "What happens when this requirement changes?"

Examples:

    What if the payment provider changes?

    What if the database changes?

    What if a new notification channel is added?

    What if tax rules change?

    What if the API response changes?

    What if the system needs to support ten times the traffic?

    What if a new business rule is introduced?

A design is strong when predictable changes are localized instead of
forcing unrelated parts of the system to change.
""")


# ============================================================================
# 81. STABILITY AND INSTABILITY
# ============================================================================

section("81. STABILITY")

explain("""
A component that many other components depend on is difficult to change.

A component with many dependencies but few dependents may be easier to
change.

This leads to an important architectural concern:

    Who depends on whom?

Dependency graphs are therefore useful tools for understanding software
architecture.

A healthy dependency structure tends to prevent low-level implementation
details from controlling high-level business rules.
""")


# ============================================================================
# 82. CYCLIC DEPENDENCIES
# ============================================================================

section("82. CYCLIC DEPENDENCIES")

explain("""
A cyclic dependency occurs when:

    A depends on B
    B depends on A

or indirectly:

    A -> B -> C -> A

Cycles make systems harder to understand and change.

They can cause:

    - difficult testing
    - difficult deployment
    - unclear ownership
    - tightly coupled modules

Breaking cycles often requires:

    - extracting an abstraction
    - moving responsibility
    - introducing an intermediary
    - changing dependency direction
""")


# ============================================================================
# 83. DOMAIN MODEL EXAMPLE
# ============================================================================

section("83. A SMALL DOMAIN MODEL")

explain("""
The following example combines several principles:

    - encapsulation
    - value objects
    - validation
    - domain behavior
    - clear responsibility
""")


@dataclass(frozen=True)
class ProductPrice:

    amount: float
    currency: str

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Price cannot be negative")


class ShoppingCart:

    def __init__(self):
        self._items = []

    def add(self, product, price, quantity):

        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        self._items.append({
            "product": product,
            "price": price,
            "quantity": quantity
        })

    def total(self):

        return sum(
            item["price"].amount * item["quantity"]
            for item in self._items
        )

    @property
    def items(self):
        return tuple(self._items)


cart = ShoppingCart()

cart.add(
    "Keyboard",
    ProductPrice(2000, "INR"),
    2
)

cart.add(
    "Mouse",
    ProductPrice(1000, "INR"),
    1
)

print("Cart total:", cart.total())


# ============================================================================
# 84. DESIGNING A USE CASE
# ============================================================================

section("84. USE CASE ORIENTED DESIGN")

explain("""
A use case represents a meaningful operation from the perspective of
the system's purpose.

Examples:

    Register User
    Place Order
    Cancel Order
    Transfer Money
    Generate Invoice
    Reset Password

A use-case service should coordinate the work without becoming a giant
collection of unrelated business rules.

A useful mental model is:

    input
      ->
    validate
      ->
    execute business rules
      ->
    persist state
      ->
    publish relevant outcome
      ->
    output
""")


class RegisterUserUseCase:

    def __init__(self, validator, repository):
        self.validator = validator
        self.repository = repository

    def execute(self, name, email):

        self.validator.validate(name, email)

        user = {
            "name": name,
            "email": email
        }

        self.repository.save(user)

        return user


# ============================================================================
# 85. DEPENDENCY GRAPH THINKING
# ============================================================================

section("85. THINKING IN DEPENDENCY GRAPHS")

explain("""
Instead of seeing software only as a collection of files, think of it as
a dependency graph.

Example:

    Controller
        |
        v
    Application Service
        |
        v
    Domain Model
        |
        v
    Repository Interface
        ^
        |
    Database Adapter

This perspective makes architecture easier to reason about.

Whenever a dependency is introduced, ask:

    Why does this dependency exist?

    Can it change?

    Who owns the contract?

    Is the dependency pointing in the right direction?

    Does the dependency create unnecessary coupling?
""")


# ============================================================================
# 86. DESIGN REVIEW QUESTIONS
# ============================================================================

section("86. SOFTWARE DESIGN REVIEW QUESTIONS")

explain("""
When reviewing a design, ask:

1. What is each component responsible for?

2. Does each component have a focused purpose?

3. Which components depend on this component?

4. Are dependencies explicit?

5. Are implementation details leaking across boundaries?

6. Can business logic be tested independently?

7. What happens when an external dependency fails?

8. What happens when requirements change?

9. Are interfaces smaller than necessary?

10. Is inheritance actually representing a behavioral subtype?

11. Would composition be simpler?

12. Is an abstraction solving a real problem?

13. Is there unnecessary duplication?

14. Are there cyclic dependencies?

15. Where are transactions defined?

16. Who owns mutable state?

17. Which operations can be retried safely?

18. Which operations must be idempotent?

19. What are the security boundaries?

20. What assumptions does each component make?
""")


# ============================================================================
# 87. DESIGNING BEFORE CODING
# ============================================================================

section("87. DESIGN BEFORE IMPLEMENTATION")

explain("""
Design does not require creating enormous diagrams before writing code.

A practical design process can be:

    1. Understand requirements.
    2. Identify important domain concepts.
    3. Identify major responsibilities.
    4. Identify boundaries.
    5. Identify dependencies.
    6. Define important interfaces.
    7. Identify likely changes.
    8. Implement a simple version.
    9. Test behavior.
    10. Refactor as knowledge improves.

Design is iterative because understanding of the problem improves during
implementation.
""")


# ============================================================================
# 88. BIG BALL OF MUD
# ============================================================================

section("88. THE BIG BALL OF MUD")

explain("""
A Big Ball of Mud is a system without clear structural boundaries.

Typical symptoms include:

    - everything can call everything
    - shared global state
    - duplicated business logic
    - database queries scattered everywhere
    - unclear ownership
    - giant utility modules
    - circular dependencies
    - inconsistent abstractions

Such systems become difficult to change because the consequences of a
modification are difficult to predict.

The solution is not automatically "more classes."

The solution is meaningful boundaries and controlled dependencies.
""")


# ============================================================================
# 89. GOD OBJECT
# ============================================================================

section("89. GOD OBJECT")

explain("""
A God Object knows too much and does too much.

For example:

    ApplicationManager

might contain:

    authentication
    payments
    reporting
    database operations
    notifications
    configuration
    user management

This creates high coupling and low cohesion.

The usual design question is:

    Which responsibilities naturally belong together?

Responsibilities can then be separated around meaningful concepts.
""")


# ============================================================================
# 90. SHOTGUN SURGERY
# ============================================================================

section("90. SHOTGUN SURGERY")

explain("""
Shotgun Surgery occurs when one conceptual change requires small edits
in many unrelated places.

For example, adding a new tax rule might require changes in:

    OrderService
    InvoiceService
    CheckoutController
    PaymentService
    ReportService
    DatabaseHelper

This suggests that the tax concept is not represented in one coherent
location.

A better design may centralize the relevant business rule behind a
clear abstraction.
""")


# ============================================================================
# 91. PRIMITIVE OBSESSION
# ============================================================================

section("91. PRIMITIVE OBSESSION")

explain("""
Primitive obsession occurs when domain concepts are represented only
using generic primitive values even though they have meaningful rules.

For example:

    email = "alice@example.com"

may eventually require:

    validation
    normalization
    comparison rules

A dedicated EmailAddress value object can make the concept explicit.

Likewise:

    Money
    Percentage
    PhoneNumber
    ProductId

may deserve meaningful types when the domain requires them.
""")


@dataclass(frozen=True)
class EmailAddress:

    value: str

    def __post_init__(self):
        if "@" not in self.value:
            raise ValueError("Invalid email address")


email = EmailAddress("alice@example.com")

print("Email:", email.value)


# ============================================================================
# 92. LAW OF DEMETER
# ============================================================================

section("92. LAW OF DEMETER")

explain("""
The Law of Demeter is commonly summarized as:

    Talk to your immediate friends.

It discourages excessive navigation through object graphs.

Fragile:

    order.customer.address.city.name

This exposes knowledge about the internal structure of several objects.

A better design may provide an operation representing the required
concept directly.

The goal is to reduce knowledge of unrelated internal structure.
""")


# ============================================================================
# 93. TELL, DON'T ASK
# ============================================================================

section("93. TELL, DON'T ASK")

explain("""
Tell, Don't Ask suggests that objects should be given commands to
perform meaningful behavior rather than having their internal state
extracted and manipulated externally.

Instead of:

    if account.balance >= amount:
        account.balance -= amount

prefer:

    account.withdraw(amount)

The object owns the rule governing its own state.

This reinforces encapsulation.
""")


# ============================================================================
# 94. ANEMIC DOMAIN MODEL
# ============================================================================

section("94. ANEMIC DOMAIN MODEL")

explain("""
An anemic domain model stores data in objects while keeping most business
logic elsewhere.

For simple applications this can be perfectly acceptable.

For complex domains, it can cause business rules to become scattered
across services.

A richer domain model places meaningful behavior near the data and
invariants it governs.

The correct approach depends on domain complexity.

Not every application needs a sophisticated domain model.
""")


# ============================================================================
# 95. SERVICE OBJECTS
# ============================================================================

section("95. SERVICE OBJECTS")

explain("""
A service object can represent an operation that does not naturally
belong to a single entity or value object.

Examples:

    CurrencyConversionService
    FraudDetectionService
    ShippingRateService

Services should not become dumping grounds for every piece of business
logic.

A useful service has a clear responsibility.
""")


# ============================================================================
# 96. DEPENDENCY INVERSION EXERCISE
# ============================================================================

section("96. DESIGN EXERCISE: PAYMENT")

explain("""
Suppose a checkout system currently contains:

    CheckoutService
        |
        +--> Stripe
        +--> PostgreSQL
        +--> Email

Ask:

    Which parts represent business concepts?

    Which parts represent infrastructure?

    Which dependencies are likely to change?

    Which interfaces should be owned by the application?

A possible design is:

    CheckoutService
        |
        +--> PaymentGateway
        +--> OrderRepository
        +--> NotificationSender

Then:

    StripePaymentGateway
    PostgreSQLOrderRepository
    EmailNotificationSender

implement the required contracts.

This makes the business use case independent from specific technologies.
""")


# ============================================================================
# 97. SMALL DESIGN SIMULATION
# ============================================================================

section("97. SMALL END-TO-END DESIGN")

explain("""
The following miniature example combines:

    abstraction
    dependency injection
    domain behavior
    repository abstraction
    notification abstraction
    application service
""")


class OrderRepository(ABC):

    @abstractmethod
    def save(self, order):
        pass


class NotificationService(ABC):

    @abstractmethod
    def notify(self, message):
        pass


class MemoryOrderRepository(OrderRepository):

    def __init__(self):
        self.orders = []

    def save(self, order):
        self.orders.append(order)


class ConsoleNotificationService(NotificationService):

    def notify(self, message):
        print("NOTIFICATION:", message)


class PlaceOrderService:

    def __init__(self, repository, notification):
        self.repository = repository
        self.notification = notification

    def execute(self, customer, amount):

        if not customer:
            raise ValueError("Customer is required")

        if amount <= 0:
            raise ValueError("Amount must be positive")

        order = {
            "customer": customer,
            "amount": amount,
            "status": "CREATED"
        }

        self.repository.save(order)

        self.notification.notify(
            f"Order created for {customer}"
        )

        return order


repository = MemoryOrderRepository()
notification = ConsoleNotificationService()

place_order = PlaceOrderService(
    repository,
    notification
)

created_order = place_order.execute(
    "Alice",
    5000
)

print("Created:", created_order)


# ============================================================================
# 98. WHY THIS DESIGN IS DIFFERENT
# ============================================================================

section("98. REASONING ABOUT THE DESIGN")

explain("""
The PlaceOrderService does not know:

    - which database is used
    - which email provider is used
    - how notification delivery works

It knows only the contracts it requires.

The repository owns persistence behavior.

The notification implementation owns notification behavior.

The application service coordinates the use case.

This produces:

    focused responsibilities
    explicit dependencies
    replaceable infrastructure
    easier testing
    clearer boundaries
""")


# ============================================================================
# 99. REFACTORING DECISION FRAMEWORK
# ============================================================================

section("99. WHEN TO REFACTOR")

explain("""
Refactoring is especially useful when you notice:

    repeated logic
    unclear ownership
    excessive conditional logic
    large methods
    large classes
    hidden dependencies
    difficult tests
    frequent unrelated changes
    circular dependencies

Do not refactor only because code looks different from an ideal
textbook example.

Refactor when the structure creates a meaningful cost.
""")


# ============================================================================
# 100. DESIGN MATURITY
# ============================================================================

section("100. DESIGN MATURITY")

explain("""
Software design maturity involves moving from syntax-level thinking
toward system-level reasoning.

Beginner-level thinking:

    "Does this code run?"

Stronger thinking:

    "Is this code understandable?"

More advanced thinking:

    "What is this component responsible for?"

Architectural thinking:

    "How does this dependency affect the system?"

System-level thinking:

    "What happens when the environment, scale, requirements, or
     dependencies change?"

Design expertise is largely the ability to anticipate consequences
without unnecessarily complicating the present system.
""")


# ============================================================================
# 101. FINAL DESIGN MODEL
# ============================================================================

section("101. SOFTWARE DESIGN FOUNDATIONS: CORE MODEL")

explain("""
The central ideas covered in this program can be connected as follows.

REQUIREMENTS
    |
    v
DOMAIN CONCEPTS
    |
    v
RESPONSIBILITIES
    |
    v
BOUNDARIES
    |
    v
ABSTRACTIONS
    |
    v
DEPENDENCIES
    |
    v
IMPLEMENTATIONS
    |
    v
TESTING
    |
    v
REFACTORING

The most important recurring relationships are:

    High cohesion
        -> focused responsibilities

    Low unnecessary coupling
        -> easier independent change

    Encapsulation
        -> protected invariants

    Abstraction
        -> controlled knowledge

    Dependency inversion
        -> stable business logic

    Composition
        -> replaceable behavior

    Explicit interfaces
        -> clearer contracts

    Separation of concerns
        -> localized change

    Testability
        -> confidence in behavior

    Simplicity
        -> lower accidental complexity

Software design is therefore fundamentally about structure,
responsibility, dependency, change, and trade-offs.
""")


# ============================================================================
# 102. INTERACTIVE REVIEW
# ============================================================================

section("102. INTERACTIVE KNOWLEDGE CHECK")

questions = [
    (
        "What is the difference between cohesion and coupling?",
        "Cohesion concerns how closely related the responsibilities inside "
        "a component are. Coupling concerns how strongly components depend "
        "on each other."
    ),
    (
        "What does encapsulation protect?",
        "Encapsulation protects internal representation and, importantly, "
        "the invariants governing valid state."
    ),
    (
        "What is dependency injection?",
        "Dependency injection means providing an object's dependencies "
        "from outside instead of having the object construct them itself."
    ),
    (
        "What is the purpose of an abstraction?",
        "An abstraction exposes the concepts a client needs while hiding "
        "unnecessary implementation details."
    ),
    (
        "Why is composition often preferred over inheritance?",
        "Composition allows behavior to be assembled and replaced without "
        "requiring a rigid inheritance hierarchy."
    ),
    (
        "What does the Single Responsibility Principle actually focus on?",
        "It focuses on having a single reason to change rather than "
        "limiting a class to one method."
    ),
    (
        "What does the Open/Closed Principle encourage?",
        "It encourages designs where new behavior can often be added "
        "without repeatedly modifying stable existing logic."
    ),
    (
        "What does Liskov Substitution concern?",
        "It concerns whether a subtype can be substituted for its parent "
        "without violating expected behavior."
    ),
    (
        "What is an interface?",
        "An interface is a contract describing behavior that clients can "
        "rely upon without requiring knowledge of implementation details."
    ),
    (
        "Why are boundaries important?",
        "Boundaries control responsibility and dependency flow and reduce "
        "the amount of knowledge shared between components."
    ),
]


for index, (question, answer) in enumerate(questions, start=1):

    print(f"\nQuestion {index}: {question}")
    print(f"Answer: {answer}")


# ============================================================================
# 103. DESIGN TERMINOLOGY REFERENCE
# ============================================================================

section("103. DESIGN TERMINOLOGY")

terms = {
    "Abstraction":
        "Expose essential behavior while hiding unnecessary detail.",

    "Encapsulation":
        "Protect state and the rules governing that state.",

    "Cohesion":
        "How strongly related the responsibilities within a component are.",

    "Coupling":
        "How strongly components depend on each other.",

    "Modularity":
        "Dividing software into meaningful, manageable units.",

    "Polymorphism":
        "Allowing different implementations to satisfy a common contract.",

    "Composition":
        "Building behavior from collaborating objects.",

    "Dependency Injection":
        "Providing dependencies from outside a component.",

    "Interface":
        "A contract between components.",

    "Invariant":
        "A condition that must remain true for valid state.",

    "Refactoring":
        "Improving internal structure without intentionally changing behavior.",

    "Idempotency":
        "Repeated execution produces the same intended result as one execution.",

    "Aggregate":
        "A consistency boundary around related domain objects.",

    "Domain Event":
        "A representation of something meaningful that happened in the domain.",

    "Architecture":
        "The high-level organization and dependency structure of a system.",

    "Design Pattern":
        "A reusable structure for a recurring design problem.",

    "Technical Debt":
        "The future cost created by choosing a shortcut or imperfect structure.",

    "Scalability":
        "The ability of a system to handle increasing workload.",

    "Observability":
        "The ability to understand system behavior from external outputs.",
}


for term, definition in terms.items():
    print(f"\n{term}")
    print("  " + definition)


# ============================================================================
# 104. PRACTICAL DESIGN CHECKLIST
# ============================================================================

section("104. PRACTICAL SOFTWARE DESIGN CHECKLIST")

checklist = [
    "Requirements are understood.",
    "Major domain concepts are identified.",
    "Responsibilities are clearly assigned.",
    "Components have meaningful boundaries.",
    "Cohesion is reasonably high.",
    "Unnecessary coupling is minimized.",
    "Dependencies are explicit.",
    "Implementation details do not leak unnecessarily.",
    "Business rules are distinguishable from infrastructure.",
    "Important invariants are protected.",
    "Interfaces represent meaningful contracts.",
    "Inheritance represents genuine behavioral relationships.",
    "Composition is considered where appropriate.",
    "External dependencies can be replaced when necessary.",
    "Error conditions are intentionally designed.",
    "Side effects occur at controlled boundaries.",
    "Important operations are testable.",
    "Data ownership is clear.",
    "Transaction boundaries are understood.",
    "Concurrency risks are considered where relevant.",
    "Security boundaries are explicit.",
    "Failure behavior is considered.",
    "Retry behavior is intentional.",
    "Timeouts are defined for remote operations.",
    "Idempotency is considered for repeatable operations.",
    "Architecture reflects actual requirements.",
    "Patterns are used because they solve actual problems.",
    "Abstractions are justified by real variation or boundaries.",
    "Complexity is proportional to the problem.",
    "Likely changes can be localized.",
]


for number, item in enumerate(checklist, start=1):
    print(f"{number:02d}. [ ] {item}")


# ============================================================================
# 105. COMPLETION
# ============================================================================

section("SOFTWARE DESIGN FOUNDATIONS PROGRAM COMPLETE")

print("""
The program has covered software design from fundamental concepts
through object-oriented principles, SOLID, design patterns, domain
modeling, architectural boundaries, testing, distributed-system
concerns, security, scalability, observability, and design trade-offs.

The examples above are intentionally small.

Their purpose is to make the structural decisions visible:

    who owns a responsibility,
    who depends on whom,
    what should be hidden,
    what should be exposed,
    where behavior belongs,
    where state is controlled,
    how implementations can vary,
    and how a system can evolve without unnecessary structural damage.
""")
