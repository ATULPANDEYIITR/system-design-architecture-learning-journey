# Software Design Foundations

## Introduction

Software design is the process of deciding how software should be organized so that it can satisfy its requirements while remaining understandable, maintainable, testable, extensible, and reliable.

The Python program associated with this topic explains software design from fundamental concepts through more advanced design principles and architectural ideas. The focus is not only on writing code that works, but on understanding why code should be organized in a particular way.

Software design is concerned with questions such as:

- Where should a responsibility live?
- Which component should own a piece of behavior?
- How should components communicate?
- Which details should remain hidden?
- Which dependencies should be allowed?
- How can one part of a system change without breaking unrelated parts?
- How should failures be handled?
- How can business logic be tested independently?
- How should software respond to increasing complexity and changing requirements?

A program can be technically correct and still be poorly designed. Good design is concerned with the structure behind the code.

---

## Requirements and Software Design

Software design begins with understanding requirements.

Functional requirements describe what the system must do. Examples include registering a user, placing an order, generating an invoice, processing a payment, or sending a notification.

Non-functional requirements describe qualities and constraints such as performance, scalability, reliability, security, maintainability, and availability.

These requirements influence design decisions.

A small internal application and a large financial platform may perform similar business operations, but their designs can be very different because their reliability, security, scalability, and operational requirements are different.

Design therefore cannot be separated completely from the problem being solved.

---

## Software Complexity

Complexity is one of the main reasons software design matters.

Some complexity is unavoidable because the real-world problem itself is complicated. This is often called essential complexity.

Other complexity is introduced by poor implementation decisions. This can be called accidental complexity.

Examples of accidental complexity include:

- unnecessary layers
- duplicated business logic
- unclear dependencies
- excessive configuration
- tightly coupled components
- inconsistent abstractions
- giant classes
- unclear ownership of data and behavior

Good design does not remove genuine complexity from the problem. It prevents unnecessary complexity from spreading throughout the system.

One useful design goal is to keep complexity local.

If one business rule changes, a well-structured system should ideally require changes in a limited and understandable part of the codebase.

---

## Abstraction

Abstraction means exposing the important concepts or behavior while hiding implementation details that clients do not need to understand.

For example, a payment system may expose an operation for processing a payment. The code using that operation should not necessarily need to understand HTTP requests, authentication tokens, provider-specific response formats, retries, or connection details.

Abstraction reduces the amount of knowledge required by each component.

A good abstraction exposes what the client actually needs.

A poor abstraction may hide important information and make the system more difficult to understand.

Abstraction is therefore not about hiding everything. It is about controlling what information crosses a boundary.

---

## Encapsulation

Encapsulation means keeping data and the operations that control that data together while protecting the internal representation from uncontrolled modification.

A major purpose of encapsulation is protecting invariants.

An invariant is a condition that must remain true for an object to remain valid.

For example, a bank account may have the invariant that its balance cannot become negative. Instead of allowing any part of the program to modify the balance directly, the account can expose operations such as deposit and withdrawal that enforce the rules.

Encapsulation therefore provides more than simple access control. It protects the correctness of an object's state.

---

## Modularity

Modularity means dividing software into meaningful units.

A module can be a function, class, package, library, subsystem, or service.

The purpose of modularity is not to create as many components as possible. The purpose is to create meaningful boundaries that make software easier to understand, test, change, and maintain.

Typical areas of a system may include:

- authentication
- payments
- inventory
- reporting
- notifications
- user management

These areas may communicate with one another, but they do not necessarily need to share all of their internal details.

---

## Separation of Concerns

Separation of concerns means keeping different responsibilities from becoming unnecessarily mixed together.

A single operation can involve several concerns, such as:

- validation
- business logic
- persistence
- notification
- logging
- presentation

When all of these responsibilities are placed inside one function or class, the component becomes difficult to maintain.

Separating these concerns allows each part to have a clearer purpose.

For example, user registration can be divided into:

- user validation
- user persistence
- email notification
- audit logging
- registration orchestration

This structure makes individual responsibilities easier to understand and change.

---

## Cohesion

Cohesion describes how closely related the responsibilities inside a component are.

High cohesion means that the component has a focused purpose.

Low cohesion means that unrelated responsibilities have been placed together.

A component responsible for calculating invoice totals has relatively high cohesion if all of its responsibilities concern invoice calculation.

A general utility class that calculates invoices, sends emails, connects to databases, processes images, and validates passwords has low cohesion.

A useful practical question is:

> Can the responsibility of this component be described clearly in one sentence?

If the answer requires a long list of unrelated tasks, the component may need to be reconsidered.

---

## Coupling

Coupling describes how strongly one component depends on another.

High coupling means that a change in one component can easily require changes in other components.

Low coupling allows components to evolve more independently.

The goal is not to eliminate all coupling. Software components must communicate.

The goal is to avoid unnecessary coupling.

A common design objective is:

- high cohesion
- low unnecessary coupling

These two concepts are among the most important foundations of maintainable software.

---

## Information Hiding

Information hiding means that a component hides design decisions that other parts of the system do not need to know.

For example, a business service should ideally not need to understand the details of SQL queries, database connections, database drivers, or connection pooling.

Those details can remain inside a persistence component.

Information hiding reduces the amount of knowledge that must spread across the system.

It also makes implementation changes less disruptive.

---

## Interfaces and Contracts

An interface represents a contract between components.

The contract defines the behavior that a client can rely upon without requiring knowledge of how the behavior is implemented.

An interface can describe:

- available operations
- accepted inputs
- returned outputs
- error behavior
- expected side effects
- important invariants

An interface is therefore more than a collection of method names.

It is an agreement about behavior.

Clear contracts allow different implementations to be substituted while keeping client code stable.

---

## Dependency Direction

Software can be viewed as a dependency graph.

If component A depends on component B, a relationship exists from A to B.

Poor architecture often occurs when important business rules depend directly on technical implementation details.

For example, business logic directly depending on a particular database driver or payment provider creates unnecessary coupling.

A stronger design can place an abstraction between the business logic and infrastructure.

The business logic depends on the concept it needs, while infrastructure provides a concrete implementation.

This creates more controlled dependency direction.

---

## Dependency Injection

Dependency injection means that an object receives the dependencies it needs rather than constructing those dependencies internally.

A tightly coupled class might create its own database repository.

A more flexible class can receive a repository through its constructor.

This provides several advantages:

- dependencies are explicit
- implementations can be replaced
- testing becomes easier
- coupling is reduced
- configuration becomes more flexible

Dependency injection is not limited to large frameworks. It can be implemented directly through normal Python constructors.

---

# SOLID Principles

SOLID is a collection of five object-oriented design principles:

1. Single Responsibility Principle
2. Open/Closed Principle
3. Liskov Substitution Principle
4. Interface Segregation Principle
5. Dependency Inversion Principle

These principles are design heuristics rather than absolute laws.

They help reason about responsibility, dependencies, extensibility, and substitutability.

---

## Single Responsibility Principle

The Single Responsibility Principle states that a class should have one reason to change.

The important concept is not that a class can have only one method.

The important concept is responsibility.

A class that changes because of database changes, business-rule changes, email changes, and report-format changes has several independent reasons to change.

Separating these responsibilities can make changes more localized.

---

## Open/Closed Principle

The Open/Closed Principle states that software entities should be open for extension but closed for modification.

The practical idea is that stable logic should not need to be repeatedly rewritten every time a new variation is introduced.

For example, a payment system can define a payment method abstraction.

Credit card, UPI, and cash payments can implement that abstraction.

A new payment method can then be introduced without changing the core checkout algorithm unnecessarily.

The principle encourages controlled extensibility.

---

## Liskov Substitution Principle

The Liskov Substitution Principle concerns behavioral substitutability.

If one type is considered a subtype of another, code expecting the parent abstraction should be able to work with the subtype without violating expected behavior.

Inheritance is therefore not merely a mechanism for sharing code.

It represents a behavioral relationship.

A subclass that violates the expectations established by its parent is a sign that the inheritance hierarchy may be inappropriate.

This is why forcing every bird into a flying hierarchy can be problematic when some birds do not fly.

The important question is whether the subtype genuinely satisfies the behavior promised by the abstraction.

---

## Interface Segregation Principle

The Interface Segregation Principle states that clients should not be forced to depend on methods they do not need.

Large interfaces can force simple components to implement irrelevant behavior.

Instead of one giant interface containing printing, scanning, faxing, stapling, and binding, smaller focused interfaces can represent those capabilities separately.

This makes implementations simpler and reduces unnecessary coupling.

---

## Dependency Inversion Principle

The Dependency Inversion Principle states that high-level modules should not depend directly on low-level implementation details.

Both should depend on abstractions.

For example:

```text
Checkout Service
       |
       v
Payment Gateway
       ^
       |
Stripe Implementation
