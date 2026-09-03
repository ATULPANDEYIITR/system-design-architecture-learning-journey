"""
================================================================================
SYSTEM DESIGN FOUNDATIONS
FUNCTIONAL REQUIREMENTS
Features, User Actions, System Behavior, and Use Cases
================================================================================

PURPOSE
-------
This script is a comprehensive learning guide to Functional Requirements in
System Design.

It starts from the absolute basics and gradually moves toward advanced
requirements engineering concepts used in real-world software systems.

TOPICS COVERED
--------------
1. What is System Design?
2. What are Requirements?
3. Functional vs Non-Functional Requirements
4. What are Functional Requirements?
5. Features
6. User Actions
7. System Behavior
8. Use Cases
9. Actors
10. Preconditions
11. Triggers
12. Main Success Scenarios
13. Alternative Flows
14. Exception Flows
15. Inputs and Outputs
16. Business Rules
17. State Changes
18. CRUD
19. APIs and Functional Requirements
20. Requirements Traceability
21. Acceptance Criteria
22. User Stories
23. Use Case Modeling
24. Functional Requirement Quality
25. Requirement Ambiguity
26. Requirement Prioritization
27. MVP vs Advanced Features
28. Functional Requirements for Distributed Systems
29. Functional Requirements for Event-Driven Systems
30. Functional Requirements for AI Systems
31. Functional Requirements for Payment Systems
32. Functional Requirements for Social Media
33. Functional Requirements for E-Commerce
34. Functional Requirements for Ride-Hailing
35. Functional Requirements for Data Platforms
36. Turning Requirements into System Design
37. Advanced Requirement Analysis
38. Common Interview Questions
39. Practical System Design Example
40. Final Checklist

IMPORTANT
---------
This file is intentionally educational. It uses Python data structures and
functions to demonstrate how system-design requirements can be represented,
validated, analyzed, prioritized, and transformed into design artifacts.

================================================================================
"""


# ==============================================================================
# 1. WHAT IS SYSTEM DESIGN?
# ==============================================================================

"""
System design is the process of defining how a software system should work.

A system design describes things such as:

    User
      |
      v
    Client
      |
      v
    API
      |
      v
    Application Server
      |
      +-----------> Database
      |
      +-----------> Cache
      |
      +-----------> Message Queue
      |
      +-----------> External Services

System design answers questions such as:

    - What should the system do?
    - Who will use it?
    - What features are required?
    - What happens when a user performs an action?
    - What data must be stored?
    - Which services communicate with each other?
    - How does the system behave during failures?
    - How should the system scale?

Before designing databases, APIs, queues, caches, or microservices,
we need to understand WHAT the system is supposed to do.

That is where requirements come in.
"""


# ==============================================================================
# 2. WHAT IS A REQUIREMENT?
# ==============================================================================

"""
A requirement is a statement describing something the system must provide,
perform, support, enforce, or achieve.

Example:

    "The system shall allow users to create an account."

This tells us WHAT the system must do.

Another example:

    "The system shall allow users to reset their password using email
     verification."

This is also a requirement.

Requirements generally fall into two major categories:

    1. Functional Requirements
    2. Non-Functional Requirements


Functional Requirement:
    Describes WHAT the system does.

Non-Functional Requirement:
    Describes HOW WELL the system performs or behaves.

Example:

Functional:
    "Users can upload a profile picture."

Non-functional:
    "The profile picture upload must complete within 3 seconds
     for 95% of requests."

Remember:

    Functional = WHAT

    Non-functional = HOW WELL / UNDER WHAT QUALITY CONSTRAINTS
"""


# ==============================================================================
# 3. FUNCTIONAL REQUIREMENTS
# ==============================================================================

"""
A Functional Requirement describes a capability or behavior that the system
must provide.

Examples:

    - User registration
    - User login
    - Password reset
    - Product search
    - Product filtering
    - Add item to cart
    - Checkout
    - Payment
    - Order cancellation
    - Notification
    - File upload
    - Report generation

A functional requirement usually answers:

    WHO?
    DOES WHAT?
    WITH WHAT INPUT?
    UNDER WHAT CONDITIONS?
    WHAT DOES THE SYSTEM DO?
    WHAT IS THE RESULT?

Example:

    A customer searches for a product.

    WHO?
        Customer

    ACTION?
        Search

    INPUT?
        Search keyword

    SYSTEM BEHAVIOR?
        System searches product catalog.

    OUTPUT?
        Matching products are returned.

This simple decomposition is extremely important in system design.
"""


# ==============================================================================
# 4. FEATURES
# ==============================================================================

"""
A feature is a user-visible capability provided by a system.

Example: E-commerce application

Features:

    - Registration
    - Login
    - Product browsing
    - Search
    - Filtering
    - Cart
    - Checkout
    - Payment
    - Order tracking
    - Reviews
    - Notifications

A feature can contain multiple functional requirements.

For example:

    FEATURE:
        Checkout

    Functional Requirements:
        1. User can review cart.
        2. User can select address.
        3. User can select payment method.
        4. System calculates total.
        5. System validates payment.
        6. System creates order.
        7. System sends confirmation.

Therefore:

    Feature
        |
        +-- Functional Requirement
        +-- Functional Requirement
        +-- Functional Requirement
"""


# ==============================================================================
# 5. USER ACTIONS
# ==============================================================================

"""
A user action is something an actor intentionally does.

Examples:

    - Click login
    - Enter password
    - Search product
    - Upload file
    - Create order
    - Cancel order
    - Send message
    - Follow user
    - Like post
    - Submit form

A user action normally triggers system behavior.

Example:

    USER ACTION
        |
        v
    "Click Login"
        |
        v
    SYSTEM BEHAVIOR
        |
        +--> Validate credentials
        |
        +--> Create session
        |
        +--> Return authentication token
        |
        v
    RESULT
        |
        v
    User is authenticated
"""


# ==============================================================================
# 6. SYSTEM BEHAVIOR
# ==============================================================================

"""
System behavior describes what the system does in response to actions,
events, conditions, or failures.

Example:

User Action:
    User submits login form.

System Behavior:

    1. Receive username and password.
    2. Validate input.
    3. Find account.
    4. Compare password.
    5. Check account status.
    6. Generate authentication token.
    7. Record login event.
    8. Return success response.

Possible failure behavior:

    - Invalid username
    - Invalid password
    - Account locked
    - Account disabled
    - Rate limit exceeded
    - Database unavailable

Good system design does not only describe successful behavior.

It also describes failure behavior.
"""


# ==============================================================================
# 7. USE CASES
# ==============================================================================

"""
A Use Case describes how an actor interacts with a system to accomplish a goal.

Example:

    Use Case:
        Place an Order

    Actor:
        Customer

    Goal:
        Purchase products.

    Trigger:
        Customer clicks "Place Order".

    Preconditions:
        - Customer is authenticated.
        - Cart contains at least one product.
        - Delivery address exists.

    Main Flow:
        1. Customer reviews cart.
        2. System calculates total.
        3. Customer selects address.
        4. Customer selects payment method.
        5. System processes payment.
        6. System creates order.
        7. System displays confirmation.

    Alternative Flow:
        Payment fails.

    System Response:
        - Order is not confirmed.
        - User is informed.
        - User can retry payment.

Use cases are extremely useful because they convert vague requirements
into understandable interactions.
"""


# ==============================================================================
# 8. ACTORS
# ==============================================================================

"""
An actor is something external that interacts with the system.

Actors can be:

    Human:
        Customer
        Admin
        Employee
        Driver

    External System:
        Payment Gateway
        Email Provider
        SMS Provider
        Banking System

    Automated Actor:
        Scheduled Job
        Monitoring System
        Event Processor
        AI Agent

Example:

    E-commerce System

    Actors:

        Customer
        Admin
        Payment Gateway
        Shipping Provider
        Notification Service
"""


# ==============================================================================
# 9. REQUIREMENT OBJECT MODEL
# ==============================================================================

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Callable, Any


class Priority(Enum):
    """
    Requirement priority.
    """

    MUST_HAVE = "Must Have"
    SHOULD_HAVE = "Should Have"
    COULD_HAVE = "Could Have"
    WON_T_HAVE = "Won't Have"


@dataclass
class FunctionalRequirement:
    """
    Represents a functional requirement.
    """

    requirement_id: str
    title: str
    description: str
    actor: str
    trigger: str
    inputs: List[str]
    outputs: List[str]
    priority: Priority
    acceptance_criteria: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    business_rules: List[str] = field(default_factory=list)

    def display(self):
        print("=" * 80)
        print(f"Requirement ID : {self.requirement_id}")
        print(f"Title          : {self.title}")
        print(f"Actor          : {self.actor}")
        print(f"Trigger        : {self.trigger}")
        print(f"Priority       : {self.priority.value}")
        print(f"Description    : {self.description}")

        print("\nInputs:")
        for item in self.inputs:
            print(f"  - {item}")

        print("\nOutputs:")
        for item in self.outputs:
            print(f"  - {item}")

        print("\nAcceptance Criteria:")
        for item in self.acceptance_criteria:
            print(f"  - {item}")

        print("\nBusiness Rules:")
        for item in self.business_rules:
            print(f"  - {item}")

        print("\nDependencies:")
        for item in self.dependencies:
            print(f"  - {item}")


# ==============================================================================
# 10. EXAMPLE FUNCTIONAL REQUIREMENT
# ==============================================================================

login_requirement = FunctionalRequirement(
    requirement_id="FR-001",
    title="User Login",
    description="The system shall allow registered users to authenticate.",
    actor="Customer",
    trigger="Customer submits login credentials.",
    inputs=[
        "Email address",
        "Password"
    ],
    outputs=[
        "Authentication token",
        "User session"
    ],
    priority=Priority.MUST_HAVE,
    acceptance_criteria=[
        "Valid credentials authenticate the user.",
        "Invalid credentials return an error.",
        "Locked accounts cannot authenticate.",
        "Authentication events are logged."
    ],
    business_rules=[
        "Email must belong to an existing account.",
        "Password must match the stored password hash.",
        "Locked accounts cannot log in."
    ]
)

login_requirement.display()


# ==============================================================================
# 11. PRECONDITIONS
# ==============================================================================

"""
A precondition is something that must be true before a use case can begin.

Example:

Use Case:
    Withdraw Money

Preconditions:

    - Customer has an active bank account.
    - Customer is authenticated.
    - ATM is operational.

If a precondition is not satisfied, the system may reject the operation.

Preconditions help system designers identify validation requirements.
"""


# ==============================================================================
# 12. POSTCONDITIONS
# ==============================================================================

"""
A postcondition describes what should be true after a successful operation.

Example:

Use Case:
    Create Account

Postconditions:

    - User account exists.
    - User identity is stored.
    - Account has a unique identifier.
    - Verification status is recorded.
    - Registration event is logged.

Precondition:
    User does not already have an account.

Postcondition:
    User account exists.
"""


# ==============================================================================
# 13. TRIGGERS
# ==============================================================================

"""
A trigger starts a use case or causes system behavior.

Types of triggers:

1. User Trigger

    User clicks "Submit".

2. Time Trigger

    Every day at midnight.

3. Event Trigger

    PaymentCompleted event occurs.

4. External Trigger

    Payment gateway sends webhook.

5. System Trigger

    Queue contains a new message.

Example:

    Trigger:
        Payment gateway sends successful payment event.

    System:
        Receives webhook
            ->
        validates event
            ->
        updates payment
            ->
        confirms order
            ->
        sends notification
"""


# ==============================================================================
# 14. MAIN SUCCESS SCENARIO
# ==============================================================================

"""
The Main Success Scenario is the normal path through a use case.

Example:

Use Case:
    User Registration

Main Flow:

    1. User opens registration page.
    2. User enters name.
    3. User enters email.
    4. User enters password.
    5. System validates fields.
    6. System checks whether email exists.
    7. System creates account.
    8. System sends verification email.
    9. System displays confirmation.

This is sometimes called the happy path.
"""


# ==============================================================================
# 15. ALTERNATIVE FLOWS
# ==============================================================================

"""
An alternative flow is a valid variation of the normal workflow.

Example:

Normal:

    User pays using credit card.

Alternative:

    User pays using UPI.

Both are valid business paths.

Another alternative:

    User has multiple addresses and selects one.

Alternative flows are not necessarily errors.
"""


# ==============================================================================
# 16. EXCEPTION FLOWS
# ==============================================================================

"""
Exception flows describe failures or abnormal situations.

Examples:

    - Payment declined
    - Database unavailable
    - Invalid input
    - User not authorized
    - Network timeout
    - External API failure
    - Duplicate request
    - Resource unavailable

Example:

    Payment Request
        |
        v
    Payment Gateway
        |
        +---- SUCCESS ----> Confirm Order
        |
        +---- FAILURE ----> Show Payment Error
        |
        +---- TIMEOUT ----> Retry / Pending State
"""


# ==============================================================================
# 17. INPUTS AND OUTPUTS
# ==============================================================================

"""
Every functional requirement should clearly identify its inputs and outputs.

Example:

Feature:
    Product Search

Inputs:

    - Search keyword
    - Category
    - Price range
    - Page number
    - Sort order

Outputs:

    - Matching products
    - Total result count
    - Pagination information

This naturally leads toward API design.

Example API:

    GET /products?query=laptop&category=electronics

Response:

    {
        "products": [...],
        "total": 125,
        "page": 1
    }

Requirements should come BEFORE API design.

Do not start with:

    "I need a REST endpoint."

Start with:

    "The customer must be able to search products."

Then derive the API.
"""


# ==============================================================================
# 18. BUSINESS RULES
# ==============================================================================

"""
Business rules define constraints or decisions imposed by the business.

Examples:

    - A customer cannot purchase more than 10 units.
    - Orders above ₹50,000 require additional verification.
    - Only admins can delete users.
    - Refunds are allowed within 7 days.
    - A coupon can be used only once per customer.
    - Employees cannot approve their own expenses.

Business rules are different from system behavior.

Business Rule:

    "A coupon can only be used once."

System Behavior:

    System checks whether the customer has already used the coupon.

The rule defines WHAT must be enforced.

The behavior defines HOW the system responds.
"""


# ==============================================================================
# 19. CRUD
# ==============================================================================

"""
Many functional requirements map to CRUD operations.

CRUD means:

    C = Create
    R = Read
    U = Update
    D = Delete

Example:

User Management:

    Create User
    Read User
    Update User
    Delete User

Product Management:

    Create Product
    Read Product
    Update Product
    Delete Product

Not every feature is simple CRUD.

Examples of complex operations:

    Checkout
    Payment
    Fraud Detection
    Recommendation
    Authentication
    Order Fulfillment

These involve workflows, state transitions, business rules, and external
dependencies.
"""


# ==============================================================================
# 20. USER STORIES
# ==============================================================================

"""
A User Story is a lightweight way of expressing a functional requirement.

Typical format:

    As a <type of user>,
    I want <capability>,
    so that <benefit>.

Example:

    As a customer,
    I want to search products,
    so that I can quickly find what I need.

Another:

    As an administrator,
    I want to deactivate accounts,
    so that unauthorized users cannot access the system.

User stories describe user value.

Functional requirements provide more detailed system behavior.
"""


# ==============================================================================
# 21. ACCEPTANCE CRITERIA
# ==============================================================================

"""
Acceptance criteria define conditions that must be satisfied for a
requirement to be considered complete.

Example:

Requirement:

    User Login

Acceptance Criteria:

    1. Valid credentials result in successful login.
    2. Invalid credentials produce an error.
    3. Locked users cannot log in.
    4. Authentication tokens expire according to policy.
    5. Login attempts are logged.

Acceptance criteria make requirements testable.
"""


# ==============================================================================
# 22. GIVEN-WHEN-THEN
# ==============================================================================

"""
A common way to write acceptance criteria is:

    GIVEN
        some initial condition

    WHEN
        the user/system performs an action

    THEN
        the system produces a result

Example:

    GIVEN
        the user has a valid account

    WHEN
        the user enters valid credentials

    THEN
        the system authenticates the user

Another:

    GIVEN
        the user's account is locked

    WHEN
        the user attempts to log in

    THEN
        the system rejects authentication
"""


# ==============================================================================
# 23. USE CASE DATA MODEL
# ==============================================================================

@dataclass
class UseCase:
    name: str
    actor: str
    goal: str
    trigger: str
    preconditions: List[str]
    main_flow: List[str]
    alternative_flows: List[str]
    exception_flows: List[str]
    postconditions: List[str]

    def print_use_case(self):
        print("\n" + "=" * 80)
        print(f"USE CASE: {self.name}")
        print("=" * 80)

        print(f"Actor: {self.actor}")
        print(f"Goal: {self.goal}")
        print(f"Trigger: {self.trigger}")

        print("\nPreconditions:")
        for item in self.preconditions:
            print(f"  {item}")

        print("\nMain Flow:")
        for i, item in enumerate(self.main_flow, start=1):
            print(f"  {i}. {item}")

        print("\nAlternative Flows:")
        for item in self.alternative_flows:
            print(f"  - {item}")

        print("\nException Flows:")
        for item in self.exception_flows:
            print(f"  - {item}")

        print("\nPostconditions:")
        for item in self.postconditions:
            print(f"  - {item}")


place_order = UseCase(
    name="Place Order",
    actor="Customer",
    goal="Purchase products",
    trigger="Customer selects Place Order",
    preconditions=[
        "Customer is authenticated",
        "Cart contains at least one item",
        "Delivery address is available"
    ],
    main_flow=[
        "System validates cart",
        "System calculates total",
        "Customer selects address",
        "Customer selects payment method",
        "System processes payment",
        "System creates order",
        "System sends confirmation"
    ],
    alternative_flows=[
        "Customer changes delivery address",
        "Customer chooses another payment method"
    ],
    exception_flows=[
        "Payment declined",
        "Product becomes unavailable",
        "Payment gateway times out",
        "Inventory reservation fails"
    ],
    postconditions=[
        "Order is created",
        "Inventory is updated",
        "Payment status is recorded",
        "Customer receives confirmation"
    ]
)

place_order.print_use_case()


# ==============================================================================
# 24. REQUIREMENT QUALITY
# ==============================================================================

"""
A high-quality functional requirement should be:

    Clear
    Complete
    Consistent
    Testable
    Feasible
    Necessary
    Traceable
    Unambiguous
    Prioritized

BAD:

    "The system should quickly show products."

Problems:

    - What does quickly mean?
    - Which products?
    - Which users?
    - How many products?
    - What happens when there are no products?

BETTER:

    "The system shall return products matching the user's search criteria."

EVEN BETTER:

    "The system shall return products matching the supplied search criteria,
     including keyword, category, price range, and availability filters."


For measurable performance requirements, the timing constraint belongs in
non-functional requirements rather than the functional requirement itself.
"""


# ==============================================================================
# 25. REQUIREMENT AMBIGUITY
# ==============================================================================

"""
Ambiguous words should be avoided.

Examples:

    fast
    easy
    simple
    user-friendly
    efficient
    secure
    appropriate
    soon
    large
    small
    optimized

Instead, define measurable behavior.

Bad:

    "The system should respond quickly."

Better functional statement:

    "The system shall return search results when the user submits a search."

Separate NFR:

    "95% of search requests shall receive a response within 500 ms."

This distinction is important in professional system design.
"""


# ==============================================================================
# 26. REQUIREMENT PRIORITIZATION
# ==============================================================================

"""
Not every requirement has equal importance.

A common prioritization model is MoSCoW:

    M = Must Have
    S = Should Have
    C = Could Have
    W = Won't Have for this release

Example:

    Must Have:
        Registration
        Login
        Checkout
        Payment

    Should Have:
        Order history
        Email notifications

    Could Have:
        Product recommendations
        Wishlist

    Won't Have:
        Advanced social features in MVP
"""


# ==============================================================================
# 27. MVP
# ==============================================================================

"""
MVP = Minimum Viable Product.

An MVP contains the smallest set of capabilities necessary to deliver
meaningful user value.

Example:

Food Delivery MVP:

    Must Have:
        User registration
        Restaurant discovery
        Menu viewing
        Cart
        Order placement
        Payment
        Order status

    Could Have:
        Loyalty points
        AI recommendations
        Social sharing
        Voice ordering

System design becomes easier when requirements are prioritized.
"""


# ==============================================================================
# 28. REQUIREMENTS DEPENDENCIES
# ==============================================================================

"""
Requirements often depend on other requirements.

Example:

    FR-001 User Registration
        |
        v
    FR-002 User Login
        |
        v
    FR-003 Add Address
        |
        v
    FR-004 Checkout

You cannot properly implement checkout if users cannot identify themselves
or provide required delivery information.

Dependency analysis prevents incorrect implementation order.
"""


# ==============================================================================
# 29. REQUIREMENT TRACEABILITY
# ==============================================================================

"""
Traceability means being able to follow a requirement throughout the
software development lifecycle.

Example:

Requirement
    |
    v
User Story
    |
    v
Use Case
    |
    v
API
    |
    v
Service
    |
    v
Database
    |
    v
Test Case
    |
    v
Production Feature

Example:

FR-001
    ->
US-001
    ->
UC-001
    ->
POST /orders
    ->
OrderService
    ->
orders table
    ->
TC-001
"""


@dataclass
class TraceabilityRecord:
    requirement_id: str
    user_story_id: str
    use_case_id: str
    api: str
    service: str
    database_entities: List[str]
    test_cases: List[str]


trace = TraceabilityRecord(
    requirement_id="FR-ORDER-001",
    user_story_id="US-ORDER-001",
    use_case_id="UC-ORDER-001",
    api="POST /orders",
    service="OrderService",
    database_entities=["orders", "order_items", "payments"],
    test_cases=["TC-ORDER-001", "TC-ORDER-002"]
)

print("\nTRACEABILITY")
print(trace)


# ==============================================================================
# 30. REQUIREMENTS AND API DESIGN
# ==============================================================================

"""
Functional requirements often become API capabilities.

Example:

Requirement:
    Customer can create an order.

Potential API:

    POST /orders

Requirement:
    Customer can retrieve an order.

Potential API:

    GET /orders/{order_id}

Requirement:
    Customer can cancel an order.

Potential API:

    POST /orders/{order_id}/cancel

Requirement:
    Admin can update order status.

Potential API:

    PATCH /orders/{order_id}/status

Important:

Do not assume every functional requirement must map to exactly one endpoint.

One requirement can require multiple APIs.

One API can support multiple user journeys.
"""


# ==============================================================================
# 31. FUNCTIONAL REQUIREMENTS AND DATABASE DESIGN
# ==============================================================================

"""
Requirements determine what information must exist.

Example:

Requirement:

    "Customer can place an order containing multiple products."

This implies data such as:

    Customer
    Order
    OrderItem
    Product
    Payment

Possible relationships:

    Customer
        |
        | 1-to-many
        v
    Order
        |
        | 1-to-many
        v
    OrderItem
        |
        | many-to-one
        v
    Product

Functional requirements therefore influence data modeling.
"""


# ==============================================================================
# 32. STATE TRANSITIONS
# ==============================================================================

"""
Many systems contain entities with states.

Example:

Order:

    CREATED
       |
       v
    PAYMENT_PENDING
       |
       v
    PAID
       |
       v
    CONFIRMED
       |
       v
    SHIPPED
       |
       v
    DELIVERED

Possible failure:

    PAYMENT_PENDING
          |
          v
       FAILED

Possible cancellation:

    CREATED
       |
       v
    CANCELLED

Functional requirements should define valid transitions.

Example:

    "A customer can cancel an order before shipment."

This implies:

    CREATED -> CANCELLED
    PAID -> CANCELLED

But perhaps:

    SHIPPED -> CANCELLED

is not allowed.

State modeling is one of the most important advanced techniques in
functional requirement analysis.
"""


class OrderState(Enum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


VALID_ORDER_TRANSITIONS = {
    OrderState.CREATED: {
        OrderState.PAYMENT_PENDING,
        OrderState.CANCELLED
    },
    OrderState.PAYMENT_PENDING: {
        OrderState.PAID,
        OrderState.CANCELLED
    },
    OrderState.PAID: {
        OrderState.CONFIRMED,
        OrderState.CANCELLED
    },
    OrderState.CONFIRMED: {
        OrderState.SHIPPED
    },
    OrderState.SHIPPED: {
        OrderState.DELIVERED
    },
    OrderState.DELIVERED: set(),
    OrderState.CANCELLED: set()
}


def can_transition(current_state, next_state):
    """
    Check whether an order state transition is allowed.
    """
    return next_state in VALID_ORDER_TRANSITIONS.get(current_state, set())


print("\nSTATE TRANSITION EXAMPLES")

print(
    "CREATED -> PAYMENT_PENDING:",
    can_transition(
        OrderState.CREATED,
        OrderState.PAYMENT_PENDING
    )
)

print(
    "SHIPPED -> CANCELLED:",
    can_transition(
        OrderState.SHIPPED,
        OrderState.CANCELLED
    )
)


# ==============================================================================
# 33. FUNCTIONAL REQUIREMENTS FOR DISTRIBUTED SYSTEMS
# ==============================================================================

"""
In distributed systems, functional requirements become more complex.

Example:

    User places order.

Potential architecture:

    Client
       |
       v
    API Gateway
       |
       v
    Order Service
       |
       +----> Inventory Service
       |
       +----> Payment Service
       |
       +----> Order Database
       |
       +----> Message Broker
                    |
                    +----> Notification Service
                    |
                    +----> Analytics Service

Functional requirements must describe interactions across services.

Example:

    "When payment succeeds, the system shall confirm the order."

This introduces distributed-system behavior:

    Payment Service
          |
          | PaymentSucceeded event
          v
    Message Broker
          |
          v
    Order Service
          |
          v
    Order = CONFIRMED
"""


# ==============================================================================
# 34. SYNCHRONOUS VS ASYNCHRONOUS BEHAVIOR
# ==============================================================================

"""
Functional requirements can involve synchronous or asynchronous behavior.

Synchronous:

    User sends request
        ->
    System processes request
        ->
    System returns result immediately

Example:

    GET /products

Asynchronous:

    User performs action
        ->
    System accepts request
        ->
    Event is generated
        ->
    Background service processes event
        ->
    User receives notification later

Example:

    Video Upload

    User uploads video
        ->
    System stores video
        ->
    Processing job created
        ->
    Worker processes video
        ->
    Thumbnail generated
        ->
    User notified

Requirements must clearly state whether immediate or eventual behavior
is expected.
"""


# ==============================================================================
# 35. IDEMPOTENCY
# ==============================================================================

"""
Idempotency becomes important when operations may be retried.

Example:

    Customer clicks "Pay".

Network timeout occurs.

Customer clicks again.

Without idempotency:

    Payment could be charged twice.

With idempotency:

    The client sends:

        Idempotency-Key: ABC123

The server records the operation.

If the same request arrives again:

    ABC123 already exists.

The system returns the original result instead of processing
the payment twice.

Functional requirement:

    "The system shall ensure that retrying the same payment request does not
     create duplicate charges."

This is a functional behavior.
"""


# ==============================================================================
# 36. PAGINATION
# ==============================================================================

"""
Large collections require pagination.

Requirement:

    "The system shall allow users to browse products in pages."

Possible API:

    GET /products?page=1&page_size=20

Functional behavior:

    - Return at most 20 products.
    - Return page metadata.
    - Handle invalid page numbers.
    - Handle empty result sets.

Possible output:

    {
        "items": [...],
        "page": 1,
        "page_size": 20,
        "total": 500
    }
"""


# ==============================================================================
# 37. SEARCH REQUIREMENTS
# ==============================================================================

"""
Search functionality can be decomposed into:

    Keyword search
    Filters
    Sorting
    Pagination
    Fuzzy matching
    Autocomplete
    Search history
    Suggestions

Basic requirement:

    "Users can search products by keyword."

Advanced requirements:

    "Users can filter products by category."

    "Users can sort results by price."

    "Users can search using partial product names."

    "The system can suggest search terms."

Each requirement influences architecture.
"""


# ==============================================================================
# 38. AUTHORIZATION REQUIREMENTS
# ==============================================================================

"""
Authentication answers:

    "Who are you?"

Authorization answers:

    "What are you allowed to do?"

Example:

    Customer:
        View own orders
        Cancel eligible orders

    Admin:
        View all orders
        Modify order status
        Manage products

Functional requirement:

    "Only administrators shall be able to deactivate user accounts."

This leads to:

    Authentication
        +
    Authorization
        +
    Permission model
"""


# ==============================================================================
# 39. ROLE-BASED ACCESS CONTROL
# ==============================================================================

"""
RBAC = Role-Based Access Control.

Example:

    Roles:

        CUSTOMER
        SUPPORT_AGENT
        ADMIN

Permissions:

        VIEW_ORDER
        CANCEL_ORDER
        REFUND_ORDER
        MANAGE_USERS

Mapping:

    CUSTOMER
        -> VIEW_ORDER
        -> CANCEL_ORDER

    SUPPORT_AGENT
        -> VIEW_ORDER
        -> REFUND_ORDER

    ADMIN
        -> VIEW_ORDER
        -> CANCEL_ORDER
        -> REFUND_ORDER
        -> MANAGE_USERS
"""


# ==============================================================================
# 40. FUNCTIONAL REQUIREMENTS FOR E-COMMERCE
# ==============================================================================

ecommerce_requirements = [
    "User can register.",
    "User can log in.",
    "User can browse products.",
    "User can search products.",
    "User can filter products.",
    "User can add products to cart.",
    "User can update cart quantity.",
    "User can remove products from cart.",
    "User can provide delivery address.",
    "User can place an order.",
    "System can process payment.",
    "System can create an order.",
    "User can view order status.",
    "User can cancel eligible orders.",
    "System can issue refunds.",
    "Admin can manage products."
]

print("\nE-COMMERCE FUNCTIONAL REQUIREMENTS")
for requirement in ecommerce_requirements:
    print("-", requirement)


# ==============================================================================
# 41. FUNCTIONAL REQUIREMENTS FOR SOCIAL MEDIA
# ==============================================================================

"""
Example:

Feature:
    Post Creation

Functional Requirements:

    - User can create a post.
    - User can attach an image.
    - User can edit a post.
    - User can delete a post.
    - User can view a post.
    - User can like a post.
    - User can comment.
    - User can share a post.

Advanced behavior:

    - Feed ranking
    - Privacy controls
    - Content moderation
    - Notification generation
    - Mention handling
    - Hashtag indexing
"""


# ==============================================================================
# 42. FUNCTIONAL REQUIREMENTS FOR RIDE-HAILING
# ==============================================================================

"""
Actors:

    Passenger
    Driver
    Payment Provider
    Map Provider
    Notification Service

Functional requirements:

    Passenger:
        - Request ride.
        - Select pickup location.
        - Select destination.
        - Cancel ride.
        - View driver location.
        - Pay fare.
        - Rate driver.

    Driver:
        - Go online.
        - Accept ride.
        - Reject ride.
        - Start trip.
        - End trip.
        - View earnings.

    System:
        - Match driver and passenger.
        - Calculate fare.
        - Track ride state.
        - Process payment.
        - Notify passenger.
"""


# ==============================================================================
# 43. FUNCTIONAL REQUIREMENTS FOR PAYMENT SYSTEMS
# ==============================================================================

"""
Payment systems require extremely precise functional requirements.

Example:

    User initiates payment.

System must:

    1. Validate order.
    2. Validate amount.
    3. Generate payment request.
    4. Contact payment provider.
    5. Process result.
    6. Update payment status.
    7. Update order state.
    8. Record transaction.
    9. Prevent duplicate payment.
    10. Handle retries.
    11. Handle webhook events.
    12. Handle reconciliation.

Possible states:

    INITIATED
    PROCESSING
    SUCCESS
    FAILED
    REFUNDED
    PARTIALLY_REFUNDED
    DISPUTED

The functional requirements should define legal state transitions.
"""


# ==============================================================================
# 44. FUNCTIONAL REQUIREMENTS FOR FILE UPLOAD
# ==============================================================================

"""
Requirement:

    "Users can upload documents."

Functional decomposition:

    1. User selects file.
    2. Client sends file.
    3. Server validates file metadata.
    4. Server validates file type.
    5. Server validates authorization.
    6. File is stored.
    7. Metadata is recorded.
    8. Processing job is created.
    9. User receives upload status.

Possible exceptions:

    - File too large.
    - Unsupported type.
    - Storage unavailable.
    - Duplicate file.
    - Processing failure.
"""


# ==============================================================================
# 45. FUNCTIONAL REQUIREMENTS FOR AI SYSTEMS
# ==============================================================================

"""
AI systems introduce additional functional requirements.

Example:

    AI Customer Support Assistant

Functional requirements:

    - User can submit a question.
    - System can retrieve relevant knowledge.
    - System can generate an answer.
    - System can cite retrieved documents.
    - User can provide feedback.
    - System can escalate to a human.
    - System can preserve conversation context.
    - System can refuse unsupported requests.

RAG system:

    User Question
         |
         v
    Query Processing
         |
         v
    Retrieval
         |
         v
    Relevant Documents
         |
         v
    Context Construction
         |
         v
    LLM
         |
         v
    Answer
         |
         v
    User

Functional requirements should specify what happens at every major stage.
"""


# ==============================================================================
# 46. HUMAN-IN-THE-LOOP
# ==============================================================================

"""
For high-impact AI systems:

    AI Recommendation
          |
          v
    Confidence Check
          |
       /     \
      /       \
 High         Low
  |            |
  v            v
Automatic    Human Review
Decision        |
                v
            Final Decision

Functional requirement:

    "If the model confidence is below the configured threshold, the system
     shall route the case to a human reviewer."

This is a functional requirement because it specifies system behavior.
"""


# ==============================================================================
# 47. EVENT-DRIVEN FUNCTIONAL REQUIREMENTS
# ==============================================================================

"""
Event-driven systems use events to trigger behavior.

Example:

    OrderCreated
         |
         v
    Inventory Service
         |
         v
    InventoryReserved
         |
         v
    Payment Service
         |
         v
    PaymentCompleted
         |
         v
    Order Service
         |
         v
    OrderConfirmed

Requirement:

    "When an order is created, the system shall attempt to reserve
     inventory."

Another:

    "When payment succeeds, the system shall publish PaymentCompleted."

Functional requirements therefore describe:

    Event
      ->
    Consumer
      ->
    Action
      ->
    Result
"""


# ==============================================================================
# 48. REQUIREMENTS AND MICROSERVICES
# ==============================================================================

"""
Functional requirements can help identify service boundaries.

Example:

    User Management
        |
        v
    User Service

    Orders
        |
        v
    Order Service

    Payments
        |
        v
    Payment Service

    Notifications
        |
        v
    Notification Service

But do NOT create a microservice for every requirement.

Service boundaries should consider:

    - Business capability
    - Data ownership
    - Transaction boundaries
    - Team ownership
    - Scalability
    - Deployment independence
    - Failure isolation
"""


# ==============================================================================
# 49. REQUIREMENT VALIDATION
# ==============================================================================

def validate_requirement(requirement: FunctionalRequirement):
    """
    Basic automated validation of requirement quality.
    """

    problems = []

    if not requirement.requirement_id:
        problems.append("Missing requirement ID.")

    if not requirement.title:
        problems.append("Missing title.")

    if not requirement.description:
        problems.append("Missing description.")

    if not requirement.actor:
        problems.append("Missing actor.")

    if not requirement.trigger:
        problems.append("Missing trigger.")

    if not requirement.inputs:
        problems.append("No inputs defined.")

    if not requirement.outputs:
        problems.append("No outputs defined.")

    if not requirement.acceptance_criteria:
        problems.append("Acceptance criteria are missing.")

    return problems


validation_result = validate_requirement(login_requirement)

print("\nREQUIREMENT VALIDATION")

if validation_result:
    for problem in validation_result:
        print("PROBLEM:", problem)
else:
    print("Requirement passed basic validation.")


# ==============================================================================
# 50. FUNCTIONAL REQUIREMENT TEMPLATE
# ==============================================================================

def requirement_template():
    """
    Generic template for writing a functional requirement.
    """

    return {
        "id": "FR-XXX",
        "feature": "Feature Name",
        "title": "Requirement Title",
        "actor": "Actor",
        "goal": "What the actor wants to accomplish",
        "trigger": "Event that starts the behavior",
        "preconditions": [],
        "inputs": [],
        "main_flow": [],
        "alternative_flows": [],
        "exception_flows": [],
        "business_rules": [],
        "outputs": [],
        "postconditions": [],
        "acceptance_criteria": [],
        "dependencies": [],
        "priority": "Must Have"
    }


print("\nGENERIC REQUIREMENT TEMPLATE")
print(requirement_template())


# ==============================================================================
# 51. FUNCTIONAL REQUIREMENTS VS NON-FUNCTIONAL REQUIREMENTS
# ==============================================================================

"""
Functional:

    "User can upload a document."

Non-functional:

    "The upload service should support 10,000 concurrent uploads."

Functional:

    "System sends an email after successful registration."

Non-functional:

    "95% of registration emails should be initiated within 2 seconds."

Functional:

    "Admin can generate a monthly report."

Non-functional:

    "The monthly report should be generated within 30 seconds."

The two categories work together.
"""


# ==============================================================================
# 52. REQUIREMENT PRIORITY SCORING
# ==============================================================================

def requirement_score(
    business_value,
    user_impact,
    urgency,
    implementation_effort
):
    """
    A simple illustrative prioritization score.

    Higher value + higher impact + higher urgency increase priority.
    Higher effort reduces priority.

    This is not a universal industry formula.
    It is simply a learning model.
    """

    return (
        business_value
        + user_impact
        + urgency
        - implementation_effort
    )


score = requirement_score(
    business_value=10,
    user_impact=9,
    urgency=8,
    implementation_effort=4
)

print("\nREQUIREMENT PRIORITY SCORE:", score)


# ==============================================================================
# 53. REQUIREMENT COVERAGE
# ==============================================================================

"""
A strong requirements document should cover:

    Actors
    Features
    User actions
    Inputs
    Outputs
    Preconditions
    Main flows
    Alternative flows
    Exception flows
    Business rules
    State transitions
    Permissions
    Dependencies
    Acceptance criteria

Missing any of these can create ambiguity during implementation.
"""


# ==============================================================================
# 54. REQUIREMENT DECOMPOSITION
# ==============================================================================

"""
Large requirement:

    "Users can buy products."

This is too broad.

Break it down:

    1. User can browse products.
    2. User can search products.
    3. User can view product details.
    4. User can add products to cart.
    5. User can modify cart.
    6. User can provide shipping information.
    7. User can select payment method.
    8. User can submit order.
    9. System validates inventory.
    10. System processes payment.
    11. System creates order.
    12. System sends confirmation.

Requirement decomposition is one of the most important system-design skills.
"""


# ==============================================================================
# 55. FROM BUSINESS REQUIREMENT TO SYSTEM DESIGN
# ==============================================================================

"""
Consider:

    BUSINESS GOAL
        |
        v
    USER NEED
        |
        v
    FEATURE
        |
        v
    FUNCTIONAL REQUIREMENTS
        |
        v
    USE CASES
        |
        v
    USER STORIES
        |
        v
    ACCEPTANCE CRITERIA
        |
        v
    API CONTRACTS
        |
        v
    SERVICE DESIGN
        |
        v
    DATA MODEL
        |
        v
    INFRASTRUCTURE
        |
        v
    TESTS
        |
        v
    PRODUCTION SYSTEM

This is the bridge between product thinking and system design.
"""


# ==============================================================================
# 56. COMPLETE EXAMPLE: FOOD DELIVERY SYSTEM
# ==============================================================================

food_delivery_use_case = UseCase(
    name="Order Food",
    actor="Customer",
    goal="Order food from a restaurant",
    trigger="Customer clicks Order Now",
    preconditions=[
        "Customer is authenticated",
        "Restaurant is accepting orders",
        "Selected items are available",
        "Delivery location is serviceable"
    ],
    main_flow=[
        "Customer selects restaurant",
        "Customer selects food items",
        "System calculates subtotal",
        "System calculates taxes and delivery fee",
        "Customer confirms delivery address",
        "Customer selects payment method",
        "System creates payment request",
        "Payment succeeds",
        "System creates order",
        "Restaurant receives order",
        "Customer receives confirmation"
    ],
    alternative_flows=[
        "Customer changes quantity",
        "Customer applies a valid coupon",
        "Customer selects another payment method"
    ],
    exception_flows=[
        "Restaurant becomes unavailable",
        "Food item becomes unavailable",
        "Payment fails",
        "Payment times out",
        "Delivery location is unsupported"
    ],
    postconditions=[
        "Order is created if payment succeeds",
        "Restaurant is notified",
        "Customer receives order confirmation"
    ]
)

food_delivery_use_case.print_use_case()


# ==============================================================================
# 57. ADVANCED REQUIREMENT QUESTIONS
# ==============================================================================

"""
When analyzing a requirement, ask:

WHO?
    Who performs the action?

WHAT?
    What capability is needed?

WHY?
    What business/user problem does it solve?

WHEN?
    What triggers the behavior?

WHERE?
    Which component or context is involved?

INPUT?
    What information is provided?

OUTPUT?
    What result is produced?

PRECONDITION?
    What must already be true?

POSTCONDITION?
    What becomes true after success?

ALTERNATIVE?
    What valid variations exist?

EXCEPTION?
    What can fail?

STATE?
    What state changes?

PERMISSION?
    Who is allowed?

DEPENDENCY?
    What other component is required?

IDEMPOTENCY?
    What happens if the request is repeated?

CONSISTENCY?
    What must remain synchronized?

OBSERVABILITY?
    What must be logged or tracked?

AUDIT?
    What actions need a history?

This checklist turns vague product descriptions into engineering-ready
requirements.
"""


# ==============================================================================
# 58. COMMON REQUIREMENT MISTAKES
# ==============================================================================

"""
Mistake 1:
    Designing technology before understanding requirements.

Mistake 2:
    Writing vague requirements.

Mistake 3:
    Ignoring failure scenarios.

Mistake 4:
    Ignoring authorization.

Mistake 5:
    Ignoring state transitions.

Mistake 6:
    Treating every requirement as CRUD.

Mistake 7:
    Not identifying external systems.

Mistake 8:
    Not defining acceptance criteria.

Mistake 9:
    Mixing functional and non-functional requirements.

Mistake 10:
    Making requirements too broad.

Mistake 11:
    Creating implementation details too early.

Mistake 12:
    Forgetting edge cases.

Mistake 13:
    Ignoring retries and duplicate requests.

Mistake 14:
    Ignoring asynchronous workflows.

Mistake 15:
    Not connecting requirements to tests.
"""


# ==============================================================================
# 59. SYSTEM DESIGN INTERVIEW APPROACH
# ==============================================================================

"""
In a system design interview, start with requirements.

DO NOT immediately say:

    "Let's use Kafka, Redis, PostgreSQL and microservices."

Instead:

STEP 1:
    Clarify the problem.

STEP 2:
    Identify users and actors.

STEP 3:
    Identify core functional requirements.

STEP 4:
    Identify non-functional requirements.

STEP 5:
    Define scope.

STEP 6:
    Estimate scale.

STEP 7:
    Identify major workflows.

STEP 8:
    Design APIs.

STEP 9:
    Design data model.

STEP 10:
    Design high-level architecture.

STEP 11:
    Discuss bottlenecks.

STEP 12:
    Discuss failures and edge cases.

STEP 13:
    Discuss scaling.

STEP 14:
    Discuss trade-offs.

Functional requirements are therefore the foundation of the entire design.
"""


# ==============================================================================
# 60. INTERVIEW EXAMPLE: DESIGN A URL SHORTENER
# ==============================================================================

"""
Functional Requirements:

    1. User can submit a long URL.
    2. System generates a short URL.
    3. User can access the short URL.
    4. System redirects the user to the original URL.
    5. System can optionally track click statistics.

Actors:

    User

Main Flow:

    User submits long URL
        ->
    System validates URL
        ->
    System generates unique short code
        ->
    System stores mapping
        ->
    System returns short URL

Redirect Flow:

    User visits short URL
        ->
    System extracts short code
        ->
    System finds original URL
        ->
    System redirects user

Functional requirements lead naturally to:

    API
    Database
    Cache
    Redirect service
    Analytics
"""


# ==============================================================================
# 61. EDGE CASES
# ==============================================================================

"""
For every major feature, ask:

    What if input is empty?
    What if input is invalid?
    What if resource does not exist?
    What if the user is unauthorized?
    What if the request is repeated?
    What if two users perform the operation simultaneously?
    What if the external service fails?
    What if the database is unavailable?
    What if the operation partially succeeds?
    What if the user retries?
    What if the request arrives out of order?

These questions uncover hidden functional requirements.
"""


# ==============================================================================
# 62. CONCURRENCY
# ==============================================================================

"""
Example:

Product inventory:

    Stock = 1

Two users simultaneously purchase the product.

User A:
    sees stock = 1

User B:
    sees stock = 1

Both attempt purchase.

Functional requirement:

    "The system shall prevent inventory from becoming negative."

This functional requirement leads to technical mechanisms such as:

    database transactions
    row-level locking
    optimistic concurrency control
    atomic updates
    inventory reservation

Notice the progression:

    Requirement
        ->
    Behavior
        ->
    Technical design
"""


# ==============================================================================
# 63. EVENTUAL CONSISTENCY
# ==============================================================================

"""
Some systems do not require every component to update simultaneously.

Example:

    Order Service:
        Order = CONFIRMED

    Notification Service:
        Email not yet sent

The business requirement may be:

    "After successful order creation, the system shall initiate
     a confirmation notification."

This does NOT necessarily mean:

    "The email must be delivered before the API response."

That distinction allows asynchronous architecture.
"""


# ==============================================================================
# 64. AUDIT REQUIREMENTS
# ==============================================================================

"""
Some operations need an audit trail.

Example:

    Admin changes employee permissions.

Functional requirement:

    "The system shall record who changed the permission, what changed,
     and when the change occurred."

Audit record:

    actor
    action
    resource
    old_value
    new_value
    timestamp
    reason

This is particularly important in financial, government, healthcare,
security, and enterprise systems.
"""


# ==============================================================================
# 65. NOTIFICATION REQUIREMENTS
# ==============================================================================

"""
Notification feature:

    User performs event
        |
        v
    Business event
        |
        +----> Email
        |
        +----> SMS
        |
        +----> Push notification

Functional requirements:

    - User can configure notification preferences.
    - System sends notification after specified events.
    - System records notification status.
    - Failed notifications can be retried.
    - Duplicate notifications should be avoided.
"""


# ==============================================================================
# 66. REQUIREMENTS FOR REPORTING SYSTEMS
# ==============================================================================

"""
Example:

    Admin generates monthly sales report.

Functional requirements:

    - Admin can select date range.
    - Admin can select region.
    - Admin can select product category.
    - System generates report.
    - User can download report.
    - System records report generation request.

Possible outputs:

    CSV
    Excel
    PDF
    Dashboard

Advanced behavior:

    Large reports may be generated asynchronously.
"""


# ==============================================================================
# 67. REQUIREMENTS FOR DATA PLATFORMS
# ==============================================================================

"""
Example:

    Data analyst uploads CSV.

Functional requirements:

    1. User can upload file.
    2. System validates schema.
    3. System detects invalid records.
    4. System stores raw data.
    5. System transforms data.
    6. System loads curated data.
    7. User can view ingestion status.
    8. User can download validation errors.

This requirement analysis naturally leads to:

    Object Storage
    Metadata Database
    Processing Engine
    Queue
    Data Warehouse
    Monitoring
"""


# ==============================================================================
# 68. FUNCTIONAL REQUIREMENTS AND OBSERVABILITY
# ==============================================================================

"""
Some system behaviors must be observable.

Example:

    "System shall notify the operations team when payment processing fails."

This may require:

    logs
    metrics
    events
    alerts
    dashboards

Observability itself may contain functional requirements.

Example:

    "The system shall record every failed payment attempt with
     transaction ID and failure reason."
"""


# ==============================================================================
# 69. REQUIREMENTS MATRIX
# ==============================================================================

requirements_matrix = [
    {
        "id": "FR-001",
        "feature": "Registration",
        "actor": "Customer",
        "action": "Create account",
        "behavior": "Validate data and create account",
        "result": "Account created"
    },
    {
        "id": "FR-002",
        "feature": "Authentication",
        "actor": "Customer",
        "action": "Login",
        "behavior": "Validate credentials",
        "result": "Authenticated session"
    },
    {
        "id": "FR-003",
        "feature": "Search",
        "actor": "Customer",
        "action": "Search products",
        "behavior": "Search catalog",
        "result": "Matching products"
    },
    {
        "id": "FR-004",
        "feature": "Checkout",
        "actor": "Customer",
        "action": "Place order",
        "behavior": "Validate cart and process order",
        "result": "Order created"
    }
]

print("\nREQUIREMENTS MATRIX")

for requirement in requirements_matrix:
    print(
        requirement["id"],
        "|",
        requirement["feature"],
        "|",
        requirement["actor"],
        "|",
        requirement["action"],
        "|",
        requirement["behavior"],
        "|",
        requirement["result"]
    )


# ==============================================================================
# 70. FUNCTIONAL REQUIREMENT CHECKLIST
# ==============================================================================

FUNCTIONAL_REQUIREMENT_CHECKLIST = [
    "Requirement has a unique ID",
    "Requirement has a clear title",
    "Actor is identified",
    "User goal is identified",
    "Trigger is identified",
    "Inputs are identified",
    "Outputs are identified",
    "Preconditions are defined",
    "Main success flow is defined",
    "Alternative flows are defined",
    "Exception flows are defined",
    "Business rules are defined",
    "Authorization is defined",
    "State transitions are defined",
    "Dependencies are identified",
    "Acceptance criteria are testable",
    "Priority is assigned",
    "Requirement is traceable",
    "Edge cases are considered",
    "Duplicate/retry behavior is considered"
]

print("\nFUNCTIONAL REQUIREMENT CHECKLIST")

for item in FUNCTIONAL_REQUIREMENT_CHECKLIST:
    print("[ ]", item)


# ==============================================================================
# 71. FINAL MENTAL MODEL
# ==============================================================================

"""
The most important mental model is:

                    BUSINESS GOAL
                         |
                         v
                    USER NEED
                         |
                         v
                      FEATURE
                         |
                         v
                FUNCTIONAL REQUIREMENT
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       USER ACTION   SYSTEM BEHAVIOR   RESULT
                         |
               +---------+---------+
               |         |         |
               v         v         v
            SUCCESS   ALTERNATIVE  EXCEPTION
               |
               v
          STATE CHANGE
               |
               v
          DATA / API / EVENT
               |
               v
        SYSTEM ARCHITECTURE
               |
               v
             TESTS

The critical principle is:

    REQUIREMENTS DESCRIBE WHAT THE SYSTEM MUST DO.

    SYSTEM DESIGN DESCRIBES HOW THE SYSTEM WILL DO IT.

A strong system designer understands the first before designing the second.
"""


# ==============================================================================
# 72. FINAL SUMMARY
# ==============================================================================

"""
KEY TAKEAWAYS
-------------

1. System design begins with understanding the problem.

2. Requirements describe what the system needs to accomplish.

3. Functional requirements describe system capabilities and behaviors.

4. Features are user-visible capabilities.

5. User actions initiate system interactions.

6. System behavior describes how the system responds.

7. Use cases describe actor-system interactions around a goal.

8. Preconditions define what must be true before an operation.

9. Triggers start workflows.

10. Main flows describe successful execution.

11. Alternative flows describe valid variations.

12. Exception flows describe failures and abnormal situations.

13. Business rules define constraints and decisions.

14. Acceptance criteria make requirements testable.

15. User stories describe user value.

16. CRUD covers many basic operations but not all workflows.

17. State machines are essential for complex entities.

18. Functional requirements influence APIs.

19. Functional requirements influence databases.

20. Functional requirements influence service boundaries.

21. Functional requirements influence event-driven architecture.

22. Distributed systems require explicit failure and retry behavior.

23. Idempotency prevents duplicate effects during retries.

24. Authorization requirements define who can perform operations.

25. Audit requirements define what actions must be recorded.

26. AI systems require requirements for retrieval, generation,
    confidence, escalation, feedback, and human review.

27. Good requirements are clear, complete, testable, feasible,
    traceable, and unambiguous.

28. Always identify edge cases and failure paths.

29. Do not begin system design by choosing technologies.

30. Begin with:

        WHO?
        WHAT?
        WHY?
        WHEN?
        INPUT?
        OUTPUT?
        PRECONDITION?
        POSTCONDITION?
        SUCCESS?
        ALTERNATIVE?
        FAILURE?
        STATE?
        PERMISSION?
        DEPENDENCY?

The ultimate goal of functional requirement analysis is to transform
a vague business problem into precise, testable system behavior.

That behavior becomes the foundation for APIs, databases, services,
events, workflows, infrastructure, and tests.

================================================================================
END OF LEARNING SCRIPT
================================================================================
"""


# ==============================================================================
# 73. OPTIONAL SELF-TEST
# ==============================================================================

def self_test():
    """
    Simple knowledge-check questions.
    """

    questions = [
        (
            "What does a functional requirement describe?",
            "What the system should do."
        ),
        (
            "What is a feature?",
            "A user-visible capability of a system."
        ),
        (
            "What is a use case?",
            "An interaction between an actor and a system to achieve a goal."
        ),
        (
            "What is a precondition?",
            "A condition that must be true before an operation starts."
        ),
        (
            "What is an alternative flow?",
            "A valid variation of the main workflow."
        ),
        (
            "What is an exception flow?",
            "Behavior for errors or abnormal conditions."
        ),
        (
            "What is an acceptance criterion?",
            "A condition used to determine whether a requirement is satisfied."
        ),
        (
            "What is idempotency?",
            "The property that repeating an operation does not create unintended"
            " additional effects."
        )
    ]

    print("\nSELF TEST")
    print("=" * 80)

    for question, answer in questions:
        print(f"\nQ: {question}")
        print(f"A: {answer}")


self_test()


# ==============================================================================
# END
# ==============================================================================
