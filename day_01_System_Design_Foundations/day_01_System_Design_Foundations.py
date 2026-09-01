```python
# ============================================================
# SYSTEM DESIGN FOUNDATIONS
# ============================================================
# Beginner to Advanced Conceptual Introduction
# ============================================================
#
# PURPOSE:
# This program explains the foundations of System Design to a
# complete beginner using:
#
# 1. Simple language
# 2. Real-world analogies
# 3. Software examples
# 4. Practical examples
# 5. Design questions
# 6. Mini exercises
# 7. Architecture thinking
# 8. Component thinking
# 9. Interface thinking
# 10. Constraint and trade-off thinking
#
# CORE TOPICS:
#
# - What is System Design?
# - What is a Software System?
# - What is Software Architecture?
# - What are Components?
# - What are Interfaces?
# - What are Constraints?
# - Functional Requirements
# - Non-Functional Requirements
# - Scalability
# - Reliability
# - Availability
# - Performance
# - Maintainability
# - Security
# - Cost
# - Trade-offs
#
# ============================================================


print("=" * 80)
print("SYSTEM DESIGN FOUNDATIONS")
print("=" * 80)

print()
print("Welcome to System Design.")
print()
print("This program assumes that you are a complete beginner.")
print("You do not need previous system design knowledge.")
print("We will begin with everyday examples.")
print("Then we will connect those examples to software.")
print()
print("=" * 80)


# ============================================================
# SECTION 1
# WHAT IS SYSTEM DESIGN?
# ============================================================

print()
print("=" * 80)
print("1. WHAT IS SYSTEM DESIGN?")
print("=" * 80)

print()
print("Let us begin with the simplest possible question.")
print()
print("What does the phrase 'System Design' mean?")
print()

print("""
System Design is the process of deciding how different parts
of a software system should be organized and how those parts
should work together.
""")

print("""
In very simple words:

System Design means:

    "How should we build this software system?"

It is not only about writing code.

It is about deciding:

    - What parts should exist?
    - What should each part do?
    - How should the parts communicate?
    - Where should data be stored?
    - How should users interact with the system?
    - What happens when something fails?
    - How should the system handle more users?
    - How secure should the system be?
    - How much should the system cost?
""")

print()
print("Think about building a house.")

print("""
If someone says:

    "Build me a house."

You do not immediately start putting bricks together.

First you think about:

    - How many rooms?
    - Where should the kitchen be?
    - Where should the bathroom be?
    - Where should the doors be?
    - Where should the windows be?
    - How much land is available?
    - How much money is available?
    - How many people will live there?
    - Where will electricity come from?
    - Where will water come from?
    - What happens during heavy rain?
""")

print("""
This planning process is similar to System Design.
""")

print()
print("A software system also needs planning.")

print("""
Suppose we want to build an online shopping application.

We need to think about:

    Customer
        |
        v
    Website
        |
        v
    Application
        |
        +------> Product Database
        |
        +------> Order System
        |
        +------> Payment System
        |
        +------> Notification System
""")

print("""
That overall structure is part of system design.
""")

# ============================================================
# SECTION 2
# WHY DO WE NEED SYSTEM DESIGN?
# ============================================================

print()
print("=" * 80)
print("2. WHY DO WE NEED SYSTEM DESIGN?")
print("=" * 80)

print()
print("Imagine writing a very small Python program.")

print("""
name = "Atul"
print(name)
""")

print("""
This program is extremely simple.

There may be only a few lines of code.

You can understand almost everything by looking at the file.
""")

print()
print("Now imagine building Amazon-like software.")

print("""
Millions of users may:

    - Search products
    - View products
    - Add products to carts
    - Place orders
    - Make payments
    - Track deliveries
    - Leave reviews
    - Receive notifications
""")

print("""
Such a system cannot reasonably be treated as one tiny piece
of code.
""")

print("""
It contains many different responsibilities.

For example:

    User Management
    Product Management
    Search
    Shopping Cart
    Orders
    Payments
    Inventory
    Delivery
    Notifications
    Reviews
    Recommendations
    Authentication
    Analytics
""")

print("""
If everything is mixed together, the system becomes extremely
difficult to understand and maintain.
""")

print("""
System Design gives us a structured way to organize this
complexity.
""")

# ============================================================
# SECTION 3
# SYSTEM DESIGN IS NOT JUST DIAGRAMS
# ============================================================

print()
print("=" * 80)
print("3. SYSTEM DESIGN IS NOT JUST DRAWING DIAGRAMS")
print("=" * 80)

print("""
Beginners often think:

    System Design = Boxes + Arrows
""")

print("""
That is only one part of system design.
""")

print("""
A diagram can show:

    User
      |
      v
    Server
      |
      v
    Database
""")

print("""
But a good system designer must ask:

    Why is there a server?
    Why is there a database?
    Why are they separate?
    What happens if the database fails?
    What happens if 1 million users arrive?
    What happens if the server becomes overloaded?
    How does the user authenticate?
    How is sensitive information protected?
    How quickly should requests be answered?
    How much will the architecture cost?
""")

print("""
Therefore:

    System Design = Structure + Decisions + Trade-offs
""")

# ============================================================
# SECTION 4
# WHAT IS A SYSTEM?
# ============================================================

print()
print("=" * 80)
print("4. WHAT IS A SYSTEM?")
print("=" * 80)

print("""
Before understanding System Design, we should understand
what a "system" actually means.
""")

print("""
A system is a collection of parts that work together to
achieve a particular purpose.
""")

print()
print("Examples from everyday life:")

examples = [
    "Human body",
    "Traffic system",
    "Banking system",
    "Railway system",
    "Hospital system",
    "Electricity system",
    "Education system",
    "Postal system",
    "Airline system",
    "Government service system",
]

for number, example in enumerate(examples, 1):
    print(number, ".", example)

print("""
Each of these systems contains multiple parts.

The parts interact with each other.

The behavior of the overall system depends on those interactions.
""")

# ============================================================
# SECTION 5
# SOFTWARE SYSTEM
# ============================================================

print()
print("=" * 80)
print("5. WHAT IS A SOFTWARE SYSTEM?")
print("=" * 80)

print("""
A software system is a collection of software components,
data, interfaces, infrastructure, and operational mechanisms
that work together to provide some capability.
""")

print("""
For example, consider a food delivery application.
""")

print("""
A customer might:

    1. Open the application.
    2. Log in.
    3. Search for restaurants.
    4. Select food.
    5. Add food to a cart.
    6. Place an order.
    7. Pay.
    8. Track the delivery.
""")

print("""
Behind the scenes, many components may be involved.
""")

print("""
Possible components:

    Mobile Application
    API Server
    Authentication Service
    Restaurant Service
    Menu Service
    Cart Service
    Order Service
    Payment Service
    Delivery Service
    Notification Service
    Database
    Cache
    Message Queue
""")

print("""
The customer sees one application.

The engineer sees a complete system.
""")

# ============================================================
# SECTION 6
# REAL-WORLD ANALOGY
# ============================================================

print()
print("=" * 80)
print("6. SYSTEM DESIGN USING A RESTAURANT ANALOGY")
print("=" * 80)

print("""
Let us understand software using a restaurant.
""")

print("""
Customer
    |
    v
Reception
    |
    v
Waiter
    |
    v
Kitchen
    |
    v
Food
""")

print("""
Now map this to software.
""")

print("""
Customer
    =
User

Reception
    =
Entry/interface

Waiter
    =
API

Kitchen
    =
Business logic

Pantry
    =
Storage

Chef
    =
Processing component

Restaurant manager
    =
System administration

Restaurant rules
    =
Constraints
""")

print("""
This analogy is useful because it demonstrates an important
system-design principle:

    Different parts have different responsibilities.
""")

# ============================================================
# SECTION 7
# RESPONSIBILITY
# ============================================================

print()
print("=" * 80)
print("7. WHAT IS RESPONSIBILITY?")
print("=" * 80)

print("""
Every component should have a reason to exist.
""")

print("""
Suppose we have a component called:

    Payment Service
""")

print("""
Its responsibility might be:

    - Create payment requests
    - Validate payment information
    - Communicate with a payment provider
    - Record payment status
""")

print("""
It should generally NOT be responsible for unrelated tasks
such as:

    - Managing restaurant menus
    - Generating product recommendations
    - Managing employee attendance
""")

print("""
Why?

Because mixing unrelated responsibilities makes software
harder to understand and change.
""")

# ============================================================
# SECTION 8
# SOFTWARE ARCHITECTURE
# ============================================================

print()
print("=" * 80)
print("8. WHAT IS SOFTWARE ARCHITECTURE?")
print("=" * 80)

print("""
Software Architecture is the high-level structure of a
software system.
""")

print("""
Architecture describes important decisions such as:

    - Major components
    - Component boundaries
    - Communication patterns
    - Data ownership
    - Deployment structure
    - Dependency relationships
    - Reliability strategy
    - Scaling strategy
""")

print("""
Think about architecture like the blueprint of a building.
""")

print("""
A blueprint can tell you:

    - Where rooms are
    - Where doors are
    - Where stairs are
    - Where plumbing goes
    - Where electricity goes
""")

print("""
Similarly, software architecture tells engineers:

    - Where major functionality lives
    - Which component talks to which
    - Where data lives
    - Which dependencies exist
""")

# ============================================================
# SECTION 9
# ARCHITECTURE VS CODE
# ============================================================

print()
print("=" * 80)
print("9. ARCHITECTURE VS CODE")
print("=" * 80)

print("""
Code answers questions such as:

    "How exactly is this function implemented?"
""")

print("""
Architecture answers questions such as:

    "Where should this functionality live?"
""")

print("""
For example:

Code:

    def calculate_total(price, tax):
        return price + tax
""")

print("""
Architecture:

    Customer Application
            |
            v
       Order Service
            |
            v
       Payment Service
            |
            v
        Database
""")

print("""
The code is implementation.

The architecture is the larger structure around that code.
""")

# ============================================================
# SECTION 10
# COMPONENTS
# ============================================================

print()
print("=" * 80)
print("10. WHAT IS A COMPONENT?")
print("=" * 80)

print("""
A component is a meaningful part of a software system that
performs a specific responsibility.
""")

components = [
    "Web Server",
    "Application Server",
    "Database",
    "Cache",
    "Message Queue",
    "Authentication Service",
    "Payment Service",
    "Search Service",
    "Notification Service",
    "File Storage",
]

for number, component in enumerate(components, 1):
    print(f"{number}. {component}")

print("""
A component can be very small or very large.

For example:

    A Python function can be considered a small software unit.

A larger system component might be:

    Payment Service

And that payment service may internally contain:

    - Controllers
    - Business logic
    - Database access
    - Validation
    - Logging
    - Error handling
""")

# ============================================================
# SECTION 11
# COMPONENT INPUTS AND OUTPUTS
# ============================================================

print()
print("=" * 80)
print("11. COMPONENT INPUTS AND OUTPUTS")
print("=" * 80)

print("""
Every useful component usually has:

    Input
    Processing
    Output
""")

print("""
Example:

    User
      |
      | username/password
      v
    Authentication Service
      |
      | authentication result
      v
    User
""")

print("""
Input:

    username
    password

Processing:

    validate credentials
    check stored information

Output:

    success
    failure
    authentication token
""")

# ============================================================
# SECTION 12
# COMPONENT DEPENDENCIES
# ============================================================

print()
print("=" * 80)
print("12. COMPONENT DEPENDENCIES")
print("=" * 80)

print("""
A dependency exists when one component requires another
component to perform its work.
""")

print("""
Example:

    Order Service
          |
          v
    Payment Service
""")

print("""
The Order Service may depend on Payment Service because
an order cannot be confirmed until payment succeeds.
""")

print("""
Another example:

    Application
        |
        v
    Database
""")

print("""
The application may depend on the database for persistent data.
""")

print("""
Dependencies are important because failures can travel through
dependency chains.
""")

# ============================================================
# SECTION 13
# WHAT HAPPENS WHEN A COMPONENT FAILS?
# ============================================================

print()
print("=" * 80)
print("13. FAILURE THINKING")
print("=" * 80)

print("""
System designers must think about failure.
""")

failure_examples = [
    "Database becomes unavailable.",
    "Network becomes slow.",
    "Application server crashes.",
    "External API stops responding.",
    "Disk becomes full.",
    "Traffic suddenly increases.",
    "Invalid user input arrives.",
    "A service returns an unexpected response.",
]

for number, failure in enumerate(failure_examples, 1):
    print(f"{number}. {failure}")

print("""
A beginner may ask:

    "What should happen when everything works?"

A system designer also asks:

    "What happens when something does NOT work?"
""")

# ============================================================
# SECTION 14
# INTERFACES
# ============================================================

print()
print("=" * 80)
print("14. WHAT IS AN INTERFACE?")
print("=" * 80)

print("""
An interface is an agreed way for two parts of a system to
communicate.
""")

print("""
Imagine ordering food.

The customer does not walk into the kitchen and personally
operate the stove.

The customer communicates through a defined process.
""")

print("""
Software works similarly.

One component should not need to know every internal detail
of another component.
""")

print("""
Instead, it uses an interface.
""")

# ============================================================
# SECTION 15
# API AS AN INTERFACE
# ============================================================

print()
print("=" * 80)
print("15. API AS AN INTERFACE")
print("=" * 80)

print("""
An API is one common form of software interface.
""")

print("""
Suppose an application wants product information.

It might send:

    GET /products/101
""")

print("""
The product service might return:

    {
        "id": 101,
        "name": "Laptop",
        "price": 75000
    }
""")

print("""
The client does not need to know:

    - Which database is used.
    - Which programming language is used.
    - Which internal classes exist.
    - How the database query is implemented.
""")

print("""
It only needs to understand the interface contract.
""")

# ============================================================
# SECTION 16
# INTERFACE CONTRACT
# ============================================================

print()
print("=" * 80)
print("16. WHAT IS AN INTERFACE CONTRACT?")
print("=" * 80)

print("""
An interface contract specifies how communication should work.
""")

print("""
It may define:

    - Endpoint
    - Request method
    - Required fields
    - Optional fields
    - Data types
    - Response structure
    - Error responses
    - Authentication requirements
""")

print("""
For example:

    POST /orders
""")

print("""
Request:

    customer_id
    product_id
    quantity
""")

print("""
Response:

    order_id
    status
    created_at
""")

print("""
If the contract is clear, two teams can work more independently.
""")

# ============================================================
# SECTION 17
# WHY INTERFACES MATTER
# ============================================================

print()
print("=" * 80)
print("17. WHY INTERFACES MATTER")
print("=" * 80)

print("""
Imagine a restaurant where every customer is allowed to enter
the kitchen and change the cooking process.

Chaos would follow.
""")

print("""
Software can experience similar problems when components know
too much about each other's internal implementation.
""")

print("""
A clean interface creates a boundary.
""")

print("""
Inside the boundary:

    implementation can change.

Outside the boundary:

    the contract remains stable.
""")

# ============================================================
# SECTION 18
# CONSTRAINTS
# ============================================================

print()
print("=" * 80)
print("18. WHAT IS A CONSTRAINT?")
print("=" * 80)

print("""
A constraint is something that limits the choices available
to the system designer.
""")

print("""
Imagine building a house.

You may have:

    Limited money
    Limited land
    Limited construction time
    Local building rules
    Limited workers
""")

print("""
These are constraints.
""")

print("""
Software has constraints too.
""")

constraints = [
    "Budget",
    "Traffic",
    "Latency",
    "Availability",
    "Storage",
    "Network capacity",
    "Security",
    "Privacy",
    "Legal requirements",
    "Team size",
    "Operational capability",
    "Existing infrastructure",
]

for number, constraint in enumerate(constraints, 1):
    print(f"{number}. {constraint}")

# ============================================================
# SECTION 19
# BUDGET AS A CONSTRAINT
# ============================================================

print()
print("=" * 80)
print("19. BUDGET AS A CONSTRAINT")
print("=" * 80)

print("""
Suppose two architectures can solve the same problem.

Architecture A costs:

    $100 per month

Architecture B costs:

    $10,000 per month
""")

print("""
If both provide the required functionality and the organization
has a small budget, Architecture A may be the better choice.
""")

print("""
The more expensive architecture is not automatically better.
""")

print("""
This teaches an important system-design lesson:

    Engineering decisions must consider business reality.
""")

# ============================================================
# SECTION 20
# SCALE AS A CONSTRAINT
# ============================================================

print()
print("=" * 80)
print("20. SCALE")
print("=" * 80)

print("""
A system designed for 100 users may be very different from a
system designed for 100 million users.
""")

print("""
Consider a small internal application.

Users:

    50 employees
""")

print("""
A simple application and database may be sufficient.
""")

print("""
Now consider:

    100 million users
""")

print("""
The design may need to consider:

    - Multiple application servers
    - Load balancing
    - Caching
    - Database scaling
    - Replication
    - Asynchronous processing
    - Rate limiting
    - Monitoring
    - Fault tolerance
""")

# ============================================================
# SECTION 21
# FUNCTIONAL REQUIREMENTS
# ============================================================

print()
print("=" * 80)
print("21. FUNCTIONAL REQUIREMENTS")
print("=" * 80)

print("""
Functional requirements describe what the system should do.
""")

print("""
For an online bookstore:

    - User can register.
    - User can log in.
    - User can search books.
    - User can view book details.
    - User can add books to a cart.
    - User can place an order.
    - User can pay.
    - User can track an order.
""")

print("""
These are functional requirements because they describe
system behavior.
""")

# ============================================================
# SECTION 22
# NON-FUNCTIONAL REQUIREMENTS
# ============================================================

print()
print("=" * 80)
print("22. NON-FUNCTIONAL REQUIREMENTS")
print("=" * 80)

print("""
Non-functional requirements describe qualities and operational
expectations of the system.
""")

print("""
Examples:

    - Response should be fast.
    - System should be reliable.
    - System should be secure.
    - System should support many users.
    - System should be maintainable.
    - System should be available.
""")

print("""
Compare:

Functional:

    "User can upload a photo."

Non-functional:

    "The upload service should remain responsive during high
     traffic."
""")

# ============================================================
# SECTION 23
# PERFORMANCE
# ============================================================

print()
print("=" * 80)
print("23. PERFORMANCE")
print("=" * 80)

print("""
Performance describes how efficiently a system responds and
processes work.
""")

print("""
Important performance concepts include:

    Latency
    Throughput
    Response time
    Processing time
""")

print("""
Latency is the time taken for an operation or request to receive
a response.
""")

print("""
For example:

    Request sent at 10:00:00.000
    Response received at 10:00:00.200
""")

print("""
Approximate latency:

    200 milliseconds
""")

# ============================================================
# SECTION 24
# THROUGHPUT
# ============================================================

print()
print("=" * 80)
print("24. THROUGHPUT")
print("=" * 80)

print("""
Throughput describes how much work a system can process during
a period of time.
""")

print("""
For example:

    1,000 requests per second
""")

print("""
This is different from latency.
""")

print("""
Latency asks:

    "How long did this request take?"
""")

print("""
Throughput asks:

    "How much work can the system handle?"
""")

# ============================================================
# SECTION 25
# AVAILABILITY
# ============================================================

print()
print("=" * 80)
print("25. AVAILABILITY")
print("=" * 80)

print("""
Availability describes how often a system is operational and
accessible when users need it.
""")

print("""
A system that is available most of the time is more useful than
one that frequently becomes unavailable.
""")

print("""
For example:

    An online banking system should not frequently disappear.
""")

print("""
Availability becomes especially important for:

    - Banking
    - Payments
    - Healthcare
    - Communication
    - Emergency services
    - Large online platforms
""")

# ============================================================
# SECTION 26
# RELIABILITY
# ============================================================

print()
print("=" * 80)
print("26. RELIABILITY")
print("=" * 80)

print("""
Reliability means the system continues to behave correctly
and consistently over time.
""")

print("""
A system can be temporarily reachable but still unreliable.
""")

print("""
For example:

    A payment service that sometimes charges a customer twice
    is not reliable even if the website is online.
""")

print("""
Reliability therefore includes correctness, consistency,
failure handling, and predictable behavior.
""")

# ============================================================
# SECTION 27
# SCALABILITY
# ============================================================

print()
print("=" * 80)
print("27. SCALABILITY")
print("=" * 80)

print("""
Scalability is the ability of a system to handle increasing
workload.
""")

print("""
Imagine:

    Monday:
        1,000 users

    Friday:
        100,000 users
""")

print("""
The system needs to cope with the increased demand.
""")

print("""
Two broad approaches are:

    Vertical Scaling
    Horizontal Scaling
""")

# ============================================================
# SECTION 28
# VERTICAL SCALING
# ============================================================

print()
print("=" * 80)
print("28. VERTICAL SCALING")
print("=" * 80)

print("""
Vertical scaling means increasing the resources of an existing
machine.
""")

print("""
For example:

    4 GB RAM
        ->
    16 GB RAM
""")

print("""
Or:

    2 CPU cores
        ->
    16 CPU cores
""")

print("""
Advantages:

    - Simple concept
    - Often easy to implement
    - May require fewer machines
""")

print("""
Disadvantages:

    - Hardware has limits
    - Large machines can become expensive
    - One machine may remain a major failure point
""")

# ============================================================
# SECTION 29
# HORIZONTAL SCALING
# ============================================================

print()
print("=" * 80)
print("29. HORIZONTAL SCALING")
print("=" * 80)

print("""
Horizontal scaling means adding more machines or instances.
""")

print("""
Instead of:

    Server
""")

print("""
we may have:

    Server 1
    Server 2
    Server 3
    Server 4
""")

print("""
A load balancer can distribute requests across them.
""")

print("""
This can allow the system to process more requests and improve
resilience.
""")

# ============================================================
# SECTION 30
# TRADE-OFFS
# ============================================================

print()
print("=" * 80)
print("30. WHAT IS A TRADE-OFF?")
print("=" * 80)

print("""
A trade-off occurs when improving one property creates a cost
or disadvantage somewhere else.
""")

print("""
Example:

    More redundancy
        ->
    Better fault tolerance

But:

    More redundancy
        ->
    Higher infrastructure cost
""")

print("""
Another example:

    More caching
        ->
    Faster reads

But:

    More caching
        ->
    More complexity around stale data
""")

print("""
System design is full of trade-offs.
""")

# ============================================================
# SECTION 31
# SIMPLICITY
# ============================================================

print()
print("=" * 80)
print("31. SIMPLICITY IS A DESIGN FEATURE")
print("=" * 80)

print("""
Beginners often believe that a sophisticated system must use
many technologies.
""")

print("""
That is incorrect.
""")

print("""
If a simple architecture satisfies the requirements, it can be
the better design.
""")

print("""
For example:

    Client
       |
       v
    Application
       |
       v
    Database
""")

print("""
may be completely appropriate for a small application.
""")

print("""
There is no requirement that every system must use:

    - Microservices
    - Kubernetes
    - Multiple databases
    - Event streaming
    - Distributed caches
""")

print("""
Technology should solve a requirement.
It should not exist merely because it is fashionable.
""")

# ============================================================
# SECTION 32
# MODULAR MONOLITH
# ============================================================

print()
print("=" * 80)
print("32. MODULAR MONOLITH")
print("=" * 80)

print("""
A monolith is an application deployed as one main unit.
""")

print("""
A modular monolith can still contain clear internal boundaries.
""")

print("""
For example:

    Application
        |
        +-- Users Module
        |
        +-- Orders Module
        |
        +-- Payments Module
        |
        +-- Products Module
""")

print("""
This can provide architectural organization without immediately
creating many independently deployed services.
""")

# ============================================================
# SECTION 33
# MICROSERVICES
# ============================================================

print()
print("=" * 80)
print("33. MICROSERVICES")
print("=" * 80)

print("""
Microservices architecture separates functionality into
independently deployable services.
""")

print("""
Example:

    User Service
    Order Service
    Payment Service
    Product Service
    Notification Service
""")

print("""
Each service can potentially be developed, deployed, and scaled
independently.
""")

print("""
But microservices introduce additional complexity:

    - Network communication
    - Service discovery
    - Deployment management
    - Distributed debugging
    - Monitoring
    - Data consistency
    - Failure handling
""")

print("""
Therefore:

    Microservices are a tool, not a mandatory destination.
""")

# ============================================================
# SECTION 34
# LAYERED ARCHITECTURE
# ============================================================

print()
print("=" * 80)
print("34. LAYERED ARCHITECTURE")
print("=" * 80)

print("""
A common architectural approach is to divide an application
into layers.
""")

print("""
Example:

    Presentation Layer
            |
            v
    Business Logic Layer
            |
            v
    Data Access Layer
            |
            v
    Database
""")

print("""
Presentation handles interaction.

Business logic handles rules.

Data access handles communication with storage.
""")

print("""
The separation makes responsibilities easier to understand.
""")

# ============================================================
# SECTION 35
# EVENT-DRIVEN THINKING
# ============================================================

print()
print("=" * 80)
print("35. EVENT-DRIVEN ARCHITECTURE")
print("=" * 80)

print("""
An event represents something that happened.
""")

print("""
Example:

    OrderPlaced
""")

print("""
Other components may react to this event.
""")

print("""
For example:

    Order Service
          |
          v
      OrderPlaced
          |
          +------> Notification Service
          |
          +------> Inventory Service
          |
          +------> Analytics Service
""")

print("""
This can reduce direct coupling between components.
""")

# ============================================================
# SECTION 36
# SYNCHRONOUS COMMUNICATION
# ============================================================

print()
print("=" * 80)
print("36. SYNCHRONOUS COMMUNICATION")
print("=" * 80)

print("""
Synchronous communication means the caller waits for a response.
""")

print("""
Example:

    Application
         |
         | request
         v
    Payment Service
         |
         | response
         v
    Application
""")

print("""
The application waits for the payment service to respond.
""")

# ============================================================
# SECTION 37
# ASYNCHRONOUS COMMUNICATION
# ============================================================

print()
print("=" * 80)
print("37. ASYNCHRONOUS COMMUNICATION")
print("=" * 80)

print("""
Asynchronous communication allows work to be sent for later
processing.
""")

print("""
Example:

    Application
         |
         v
      Queue
         |
         v
    Notification Worker
""")

print("""
The application may place a message into the queue and continue
without waiting for the notification to be completed.
""")

print("""
This can improve resilience and allow work to be processed
independently.
""")

# ============================================================
# SECTION 38
# DATABASE AS A COMPONENT
# ============================================================

print()
print("=" * 80)
print("38. DATABASE")
print("=" * 80)

print("""
A database provides persistent storage for application data.
""")

print("""
For an online store, the database may contain:

    Users
    Products
    Orders
    Payments
    Inventory
""")

print("""
Persistence means information can survive beyond the lifetime
of an individual application process.
""")

# ============================================================
# SECTION 39
# CACHE
# ============================================================

print()
print("=" * 80)
print("39. CACHE")
print("=" * 80)

print("""
A cache stores frequently accessed information so that it can
be retrieved faster.
""")

print("""
Imagine a library.

If a librarian repeatedly needs the same book, keeping that book
near the desk can reduce retrieval time.
""")

print("""
A cache performs a similar role in software.
""")

print("""
Possible flow:

    User
      |
      v
    Application
      |
      v
    Cache
      |
      | cache miss
      v
    Database
""")

# ============================================================
# SECTION 40
# DESIGN THINKING CHECKLIST
# ============================================================

print()
print("=" * 80)
print("40. BEGINNER SYSTEM DESIGN CHECKLIST")
print("=" * 80)

checklist = [
    "Understand the problem",
    "Identify users",
    "Identify functional requirements",
    "Identify non-functional requirements",
    "Estimate scale",
    "Identify major components",
    "Assign responsibilities",
    "Define interfaces",
    "Identify dependencies",
    "Identify data",
    "Think about failures",
    "Think about scalability",
    "Think about security",
    "Think about observability",
    "Identify constraints",
    "Identify trade-offs",
    "Prefer appropriate simplicity",
]

for number, item in enumerate(checklist, 1):
    print(f"{number}. {item}")

# ============================================================
# SECTION 41
# PRACTICAL EXERCISE
# ============================================================

print()
print("=" * 80)
print("41. PRACTICAL EXERCISE: DESIGN AN ONLINE BOOKSTORE")
print("=" * 80)

print("""
Your task:

Design a basic online bookstore.
""")

print("""
First identify the users.
""")

users = [
    "Customer",
    "Administrator",
]

for user in users:
    print("-", user)

print()
print("Now identify functionality.")

features = [
    "Register",
    "Login",
    "Search books",
    "View book",
    "Add book to cart",
    "Place order",
    "Make payment",
    "View order history",
]

for feature in features:
    print("-", feature)

print()
print("Now identify possible components.")

bookstore_components = [
    "Client Application",
    "API",
    "Authentication Component",
    "Catalog Component",
    "Cart Component",
    "Order Component",
    "Payment Component",
    "Database",
]

for component in bookstore_components:
    print("-", component)

print()
print("Now identify constraints.")

bookstore_constraints = [
    "Limited initial budget",
    "Security",
    "Reasonable response time",
    "Data correctness",
    "Potential growth",
]

for constraint in bookstore_constraints:
    print("-", constraint)

# ============================================================
# SECTION 42
# THINK LIKE A SYSTEM DESIGNER
# ============================================================

print()
print("=" * 80)
print("42. THINK LIKE A SYSTEM DESIGNER")
print("=" * 80)

print("""
When given a system-design problem, do not immediately start
naming technologies.
""")

print("""
Instead ask:

    1. What problem am I solving?
    2. Who uses the system?
    3. What does the user need?
    4. What are the important requirements?
    5. How much traffic exists?
    6. What data exists?
    7. Which components are needed?
    8. How do they communicate?
    9. What can fail?
    10. What constraints exist?
""")

print("""
Only after understanding these questions should technology
choices become important.
""")

# ============================================================
# SECTION 43
# FINAL RECAP
# ============================================================

print()
print("=" * 80)
print("43. FINAL RECAP")
print("=" * 80)

recap = {
    "System Design":
        "Planning how software components work together.",

    "Software Architecture":
        "The high-level structure and important decisions of a system.",

    "Component":
        "A meaningful part of a system with a responsibility.",

    "Interface":
        "An agreed mechanism through which components communicate.",

    "Constraint":
        "A limitation that affects design choices.",

    "Functional Requirement":
        "What the system should do.",

    "Non-Functional Requirement":
        "How well the system should operate.",

    "Scalability":
        "Ability to handle increasing workload.",

    "Reliability":
        "Ability to behave correctly and consistently.",

    "Availability":
        "Ability to remain accessible when required.",

    "Performance":
        "How efficiently the system responds and processes work.",

    "Trade-off":
        "A decision where improving one property may create a cost elsewhere.",
}

for concept, explanation in recap.items():
    print()
    print(concept)
    print("-" * len(concept))
    print(explanation)

print()
print("=" * 80)
print("END OF FOUNDATIONS")
print("=" * 80)
```

