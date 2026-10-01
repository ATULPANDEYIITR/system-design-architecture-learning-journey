# Database Normalization: 1NF, 2NF, 3NF, and Denormalization

## Topic Scope

Database normalization is a relational schema-design technique used to organize data around its dependencies and business meaning. The central objective is not simply to create more tables. It is to place each fact where its determining attributes naturally belong while reducing unnecessary duplication and protecting the database from insertion, update, and deletion anomalies.

This case study uses a retail order-management domain containing customers, orders, order lines, products, and product categories.

The design evolves through four distinct stages:

- **1NF** addresses repeating groups and atomic attribute values.
- **2NF** addresses partial dependencies on parts of a composite candidate key.
- **3NF** addresses transitive dependencies involving non-key attributes.
- **Denormalization** deliberately introduces selected duplication when read performance or reporting requirements justify the associated consistency and maintenance costs.

These stages are related, but they solve different dependency problems.

---

## Relational Scenario

The business stores orders placed by customers. An order can contain several products, and each product belongs to one category.

The underlying business relationships can be represented as:

`Customer -> Order -> OrderLine -> Product -> Category`

The important dependencies include:

`OrderID -> CustomerID`

`CustomerID -> CustomerName, CustomerCity`

`ProductID -> ProductName, CategoryID, UnitPrice`

`CategoryID -> CategoryName`

`(OrderID, ProductID) -> Quantity`

The last dependency is important because an order line is identified by the combination of the order and product in this simplified model.

These dependencies provide the basis for deciding where attributes belong.

---

# Unnormalized Data

A poorly designed order relation can place multiple products inside one order row:

`OrderID | CustomerID | CustomerName | ProductIDs | ProductNames | Quantities | UnitPrices`

For example, one row might conceptually contain:

`8001 | C100 | Isha Verma | P100,P200 | Keyboard,Mouse | 2,1 | 1800,700`

The problem is not merely visual complexity. The product-related attributes represent repeating groups. The database must understand positional relationships between separate lists to determine which quantity belongs to which product.

This makes individual product facts difficult to address and validate.

The Python program represents this structure with comma-separated repeating values and explicitly converts those values into separate order-line records.

The JavaScript implementation takes a slightly different representation: a JavaScript array of product objects is embedded inside each order. That is useful for demonstrating the distinction between an application object structure and a normalized relational relation. The array is convenient for application processing but still represents multiple order-line facts inside one order object rather than separate relational tuples.

---

# First Normal Form

## Atomic Values

First Normal Form requires attributes to contain atomic values appropriate to the relation's declared meaning. A relation should not encode an arbitrary collection of independent values inside one attribute.

For the order scenario, one order-line tuple represents one product occurrence:

`OrderID | CustomerID | CustomerName | CustomerCity | ProductID | ProductName | Quantity | UnitPrice`

The original order containing two products becomes two tuples:

`8001 | C100 | Isha Verma | Lucknow | P100 | Keyboard | 2 | 1800`

`8001 | C100 | Isha Verma | Lucknow | P200 | Mouse | 1 | 700`

Customer information is still duplicated. Product information is also still duplicated when a product appears in multiple orders. That does not by itself mean the relation fails 1NF.

1NF has a narrower responsibility: eliminate the repeating-group representation and make each attribute value atomic according to the relation's semantics.

## Why 1NF Is Not Enough

Suppose product `P200` appears in hundreds of orders. Its name and price may be copied into hundreds of rows.

If the product name changes, many rows could require modification. If different rows receive different updates, the database can contain contradictory descriptions of the same product.

Similarly, customer data repeated across orders creates multiple locations where a customer's city can be stored.

These problems lead to dependency analysis rather than being solved merely by making cells atomic.

---

# Second Normal Form

## Composite Keys and Partial Dependencies

2NF becomes especially important when a relation has a composite candidate key.

For the order-line relation, consider:

`(OrderID, ProductID)`

as the candidate key.

The key identifies a product's occurrence within an order.

The following dependencies then exist:

`OrderID -> CustomerID, CustomerName, CustomerCity`

`ProductID -> ProductName, UnitPrice`

`(OrderID, ProductID) -> Quantity`

The first dependency does not require `ProductID`.

The second dependency does not require `OrderID`.

Those are **partial dependencies** because non-key attributes depend on only part of the composite key.

The quantity is different. It describes the particular product line within the particular order, so the complete composite key is relevant.

## 2NF Decomposition

The Python implementation decomposes the 1NF relation into:

**Customers**

`CustomerID`

`CustomerName`

`CustomerCity`

**Products**

`ProductID`

`ProductName`

`UnitPrice`

**OrderLines**

`OrderID`

`ProductID`

`Quantity`

This decomposition places customer facts under the customer identifier, product facts under the product identifier, and order-line facts under the composite order-line identity.

The JavaScript implementation does not merely reproduce those tables. It contains a dependency-analysis engine that identifies the partial dependencies by comparing determinant size with the composite key.

The C++ case study implements an explicit 2NF decomposition using `Customer2NF`, `Product2NF`, and `OrderLine2NF` structures. It also validates repeated customer and product facts before accepting the decomposition.

---

# Third Normal Form

## Transitive Dependencies

Removing partial dependencies does not necessarily produce 3NF.

Consider a product relation containing:

`ProductID`

`ProductName`

`CategoryID`

`CategoryName`

The business rules are:

`ProductID -> ProductName, CategoryID`

and:

`CategoryID -> CategoryName`

Therefore, `ProductID` determines `CategoryName` indirectly:

`ProductID -> CategoryID -> CategoryName`

This is a **transitive dependency**.

`CategoryName` is a property of the category identified by `CategoryID`, not a direct property that should be independently repeated for every product.

## 3NF Decomposition

The relation can be separated into:

**Products**

`ProductID`

`ProductName`

`CategoryID`

and:

**Categories**

`CategoryID`

`CategoryName`

Now the dependencies have a more direct representation:

`ProductID -> ProductName, CategoryID`

`CategoryID -> CategoryName`

The category name is stored once for the category rather than repeatedly for every product.

## Why the Distinction Matters

2NF asks whether a non-key attribute depends on only part of a composite key.

3NF asks whether a non-key attribute depends on another non-key determinant rather than directly on a key.

These are different dependency problems. A schema can remove partial dependencies while still retaining transitive dependencies.

---

# Functional Dependencies

A functional dependency expresses a rule of determination.

If `A -> B`, then for a given valid database state, the same value of `A` must correspond to only one value of `B`.

For example:

`CustomerID -> CustomerName`

means that a particular customer identifier identifies one customer name.

A violation could look like:

`C100 -> Isha Verma`

and elsewhere:

`C100 -> Isha Sharma`

If the business rule says the customer identifier uniquely determines the customer's name, the data violates that dependency.

The Python, JavaScript, and C++ implementations use dependency concepts directly rather than treating normalization as a collection of naming conventions.

---

# Attribute Closure

Attribute closure is a formal method for determining what attributes can be derived from a determinant.

For the dependency set:

`OrderID -> CustomerID`

`CustomerID -> CustomerName`

`ProductID -> ProductName`

`(OrderID, ProductID) -> Quantity`

the closure of:

`{OrderID, ProductID}`

contains:

`OrderID`

`ProductID`

`CustomerID`

`CustomerName`

`ProductName`

`Quantity`

Therefore, the composite determinant can determine every attribute in the relation.

The Python and JavaScript implementations calculate attribute closure programmatically. The C++ implementation provides the same mechanism using `std::set`.

Closure analysis is particularly useful when candidate keys are not obvious from the business description.

---

# Candidate Keys

A candidate key is a minimal set of attributes that functionally determines every attribute in the relation.

For the simplified order-line relation, `(OrderID, ProductID)` is a candidate key because its closure contains the entire relation.

A superkey does not necessarily have to be minimal. For example, adding an unnecessary attribute to a valid candidate key can still produce a superkey, but it is no longer minimal.

Normalization analysis therefore needs to distinguish:

- **Superkey:** determines every attribute.
- **Candidate key:** a minimal superkey.
- **Primary key:** the candidate key selected as the principal identifier.
- **Non-key attribute:** an attribute that is not part of the candidate key being considered.

The code focuses on candidate-key reasoning rather than assuming that every primary key choice automatically explains all functional dependencies.

---

# Data Anomalies

Normalization is strongly connected to three classic anomaly categories.

## Update Anomaly

Suppose `P200` appears in 500 order rows and the product name is stored in every row.

Changing the product name requires changing many records. If some rows are updated and others are not, the database contains inconsistent representations of one product.

With a normalized Products relation, the product description has one authoritative location.

## Insertion Anomaly

In a poorly designed combined order table, product information may only be recordable as part of an order.

If the organization needs to register a new product before anyone orders it, the table's structure may force the system to create an artificial order or leave unrelated order fields empty.

Separating Products from OrderLines removes that dependency between unrelated business events.

## Deletion Anomaly

If the last order containing a product is deleted from a combined relation, product information can disappear at the same time.

A separate Products relation allows the product to remain registered even when it has no current orders.

---

# The Python Implementation

The Python program provides the most extensive normalization simulation.

It begins with an unnormalized order representation and converts repeating product groups into atomic order-line records.

The 1NF transformation validates:

- Repeating-group alignment.
- Positive quantities.
- Non-negative prices.
- Atomic output values.

The 2NF stage uses dictionaries keyed by customer and product identifiers to separate facts that depend only on one component of the composite order-line key.

The program then introduces a product-category example specifically designed to expose a transitive dependency. It calculates attribute closure and separates Products from Categories.

The `FunctionalDependency` class models determinants and dependent attributes. `attribute_closure()` repeatedly applies dependencies until no additional attributes can be derived. `candidate_keys()` searches for minimal superkeys for the small teaching relation.

The Python implementation also includes a simple natural join to demonstrate lossless reconstruction. The join is deliberately small and educational rather than intended to emulate a production database optimizer.

The `NormalizedOrderDatabase` class models primary-key collections and validates foreign-key relationships between customers, products, categories, orders, and order lines.

Finally, the program creates a denormalized sales snapshot. It copies customer, product, category, and price information into reporting rows and then deliberately changes the authoritative product price. The snapshot validator detects the resulting stale value. This demonstrates why denormalization creates a consistency-maintenance obligation.

---

# The JavaScript Implementation

The JavaScript program emphasizes application-level and event-driven modeling.

`NormalizationPipeline` exposes events before and after the 1NF transformation. This demonstrates how normalization work can participate in an application processing pipeline rather than being viewed only as a theoretical schema exercise.

The JavaScript dependency engine implements:

- Functional dependency objects.
- Set-based subset testing.
- Attribute closure.
- Superkey detection.
- Candidate-key discovery.
- Partial-dependency detection.
- Transitive-dependency detection.

The `NormalizedRepository` uses JavaScript `Map` objects to represent primary-key-oriented collections. Validation occurs when records are inserted, so an invalid product cannot reference an unknown category and an order cannot reference an unknown customer or product.

The `SalesMaterializedView` demonstrates controlled denormalization. It builds an expanded read model containing customer name, product name, category name, and unit price. The view can answer a customer-sales query directly without reconstructing those relationships at read time.

When the normalized product price changes, the view detects that its copied price is stale. Rebuilding the view restores consistency.

This makes the JavaScript implementation particularly useful for understanding the relationship between normalized source-of-truth data and derived read models.

---

# The C++ Case Study

The C++ implementation presents normalization as a small technical case study for a transactional retail database.

The initial `RepeatingOrder` structure contains product collections inside an order. `convertTo1NF()` converts each product occurrence into an `AtomicOrderLine`.

The 2NF model uses separate C++ structures for:

`Customer2NF`

`Product2NF`

`OrderLine2NF`

The decomposition verifies that the same customer or product identifier does not appear with contradictory descriptive values.

The 3NF stage introduces `ProductWithCategory`, where:

`ProductID -> CategoryID`

and:

`CategoryID -> CategoryName`

The `decomposeTo3NF()` operation creates separate Product and Category relations.

The program then uses `attributeClosure()` and `isSuperkey()` to reason about the composite order-line key.

The `NormalizedOrderDatabase` class provides a more realistic transactional model. `std::map` provides key-oriented storage, while explicit validation enforces relationships corresponding to primary-key and foreign-key constraints.

The C++ implementation also includes a reconstruction check after the 3NF decomposition. It verifies that product-category information can be recovered without losing the represented facts.

The final reporting projection demonstrates why an operational system may keep normalized transactional data while also maintaining a deliberately denormalized reporting structure.

---

# Lossless Decomposition

A normalization decomposition should not simply remove attributes and accept information loss.

A **lossless decomposition** means that the original relation can be reconstructed from the decomposed relations through appropriate joins without introducing incorrect combinations of rows.

For the product-category example:

`Products(ProductID, ProductName, CategoryID)`

and:

`Categories(CategoryID, CategoryName)`

can be joined through `CategoryID`.

The C++ implementation reconstructs the product-category information and checks that the original facts remain represented.

The Python implementation performs a natural join and compares the reconstructed tuples with the original relation.

Losslessness matters because a decomposition that destroys relationships between facts is not a valid replacement for the original relation.

---

# Dependency Preservation

A decomposition is **dependency-preserving** when the relevant functional dependencies can be enforced by examining the decomposed relations without requiring reconstruction of the entire original relation.

The 3NF product-category decomposition is naturally aligned with the dependencies:

`ProductID -> ProductName, CategoryID`

is enforced within Products.

`CategoryID -> CategoryName`

is enforced within Categories.

This makes those dependencies straightforward to enforce independently.

Losslessness and dependency preservation are separate properties. A design should be evaluated for both rather than assuming that one automatically guarantees the other.

---

# Denormalization

Denormalization intentionally duplicates information.

This is not simply a failure to normalize. It can be a deliberate engineering decision when a workload has characteristics such as:

- Very frequent analytical reads.
- Expensive repeated joins across large relations.
- Reporting queries that repeatedly require the same expanded representation.
- Read latency requirements that justify maintaining derived data.
- Data pipelines where a materialized projection is easier to consume than the transactional schema.

The case study creates a sales snapshot containing:

`OrderID`

`CustomerID`

`CustomerName`

`ProductID`

`ProductName`

`CategoryName`

`Quantity`

`UnitPrice`

The snapshot is convenient for reporting because the relationships have already been resolved.

The cost is duplication.

If the authoritative product price changes from `700` to `750`, an existing snapshot row can still contain `700`. The system must therefore refresh or incrementally update the derived representation.

Denormalization converts some read-time relationship work into write-time or refresh-time consistency work.

---

# Normalized Source and Denormalized Read Model

A useful production architecture can maintain both forms for different purposes.

The normalized transactional model remains authoritative for writes:

`Customers`

`Categories`

`Products`

`Orders`

`OrderLines`

A denormalized reporting model can then be generated from those authoritative relations:

`SalesSnapshot`

The important distinction is ownership of truth.

The normalized tables contain the authoritative business facts.

The denormalized structure contains derived copies optimized for particular reads.

Treating a derived copy as an independent source of truth without synchronization creates the same inconsistency problems that normalization was intended to prevent.

---

# When Denormalization Is Justified

Normalization should generally be the starting point for transactional schema design because it makes dependencies explicit and limits unnecessary duplication.

Denormalization should be based on an identified workload rather than on an assumption that fewer joins are always better.

A measured workload might show that a frequently executed report repeatedly joins the same large relations and that a maintained projection materially improves its response time.

At that point, an engineering team can compare:

`normalized writes + normalized reads`

against:

`normalized writes + derived projection maintenance + simplified reads`

The second architecture may be appropriate when the operational cost of maintaining the projection is lower than the performance cost of repeatedly executing the original query.

A benchmark must use the actual database engine, indexes, cardinalities, concurrency levels, storage characteristics, query plans, and production-like data distribution. The small simulations in these programs demonstrate design trade-offs rather than providing database performance measurements.

---

# Integrity Constraints

Normalization works together with database integrity constraints.

Primary keys protect entity identity.

Foreign keys protect relationships between decomposed relations.

Unique constraints can enforce business rules that correspond to functional dependencies.

Not-null constraints can protect required attributes where the domain requires a value.

Check constraints can enforce domain rules such as positive quantities and non-negative prices.

The in-memory implementations reproduce several of these behaviors explicitly:

`CustomerID` must be unique.

`ProductID` must be unique.

`CategoryID` must exist before a product references it.

`CustomerID` must exist before an order references it.

`ProductID` must exist before an order line references it.

`(OrderID, ProductID)` must not be duplicated within the simplified order-line model.

`Quantity` must be positive.

These are implementation-level manifestations of the same data-integrity concerns that relational databases enforce through schema constraints.

---

# Edge Cases

## Changing a Customer Name

If customer information is stored only in Customers, changing a name requires one authoritative update.

If the name is copied into a denormalized reporting snapshot, the snapshot must be refreshed or incrementally synchronized.

## Changing a Product Category

In the normalized design, changing the category association requires updating the Product relationship.

The category name itself remains owned by Categories.

A denormalized report containing `CategoryName` must be regenerated if the category name changes.

## Duplicate Order Lines

The simplified case study treats `(OrderID, ProductID)` as the order-line key. Two rows containing the same pair represent an identity conflict.

A real commerce system may instead use an explicit `OrderLineID`, especially when the business allows the same product to occur as separate lines for different reasons such as promotions, fulfillment groups, or pricing conditions.

The chosen key must therefore follow the actual business semantics rather than being selected solely because it is convenient for a normalization example.

## Price History

The case study uses a current product price for simplicity. Production order systems often need historical pricing.

An order line may need to store the price actually charged at purchase time even though the current Product price changes later.

That is not automatically an undesirable duplication. The historical charged price represents a different business fact:

`OrderLineID -> ChargedUnitPrice`

while:

`ProductID -> CurrentUnitPrice`

These are different facts with different temporal meanings.

This illustrates why normalization requires understanding business semantics rather than mechanically eliminating every repeated-looking value.

---

# Common Design Mistakes

## Treating 1NF as "No Duplicate Values"

1NF does not mean that a column cannot contain the same value in multiple rows.

A product identifier appearing in many order lines is not inherently a 1NF violation.

The relevant issue is whether each tuple contains atomic values appropriate to the relation.

## Treating 2NF as "Every Table Has a Single-Column Key"

2NF is concerned with partial dependencies on a composite candidate key.

If a relation has no composite candidate key, the specific partial-dependency problem addressed by 2NF does not arise in the same form.

Replacing every composite key merely to avoid discussing 2NF can obscure the actual business identity of the data.

## Treating 3NF as "Never Repeat Any Data"

3NF is about functional dependencies, not a simplistic ban on repeated values.

A repeated value can be legitimate when it represents a different fact or is intentionally stored in a derived structure.

Historical transaction values are a common example.

## Assuming More Tables Always Means Better Design

Excessive decomposition can make queries and application logic more complicated.

Normalization should be driven by dependencies and business rules, not by maximizing the number of relations.

## Denormalizing Without an Ownership Model

A copied attribute needs a clear definition of which representation is authoritative.

Without that rule, different copies can diverge and applications may not know which value should be trusted.

---

# Performance Considerations

Normalization can increase the number of relations that must be joined for a query.

The cost of those joins depends on:

- Index availability.
- Join selectivity.
- Table cardinality.
- Data distribution.
- Query-plan quality.
- Buffer and cache behavior.
- Storage layout.
- Concurrent workload.
- Database engine implementation.

The presence of joins alone is not sufficient evidence that denormalization will improve performance.

Denormalization can reduce repeated join work, but it increases storage duplication and creates synchronization work.

Indexes should be evaluated before introducing denormalized copies. A normalized schema with appropriate indexes can often satisfy a workload efficiently.

The C++ and Python examples intentionally avoid presenting their operation counts as database benchmarks. They illustrate architectural trade-offs rather than replacing measurements from an actual relational database.

---

# Security and Operational Considerations

Normalization is primarily a data-integrity technique, but schema design also affects security and operations.

Separating customer information from order lines can make authorization boundaries easier to reason about. Applications can restrict access to customer data while still allowing operational processes to access order-line information.

Denormalized reporting datasets can accidentally broaden the distribution of sensitive attributes because a single reporting row may contain customer identity, product information, and transaction data together.

A reporting projection should therefore have explicit ownership, access controls, retention rules, and refresh behavior.

Derived data also needs an operational failure strategy. If snapshot refresh fails, the system should be able to determine whether the data is stale, partially refreshed, or fully synchronized.

---

# Practical Relationship Between the Four Designs

The four stages answer different questions.

| Design stage | Primary question | Order-system consequence |
| --- | --- | --- |
| Unnormalized | Are repeating groups being packed into one record? | Multiple products are embedded in an order structure |
| 1NF | Are relation attributes atomic and represented as appropriate tuples? | Each product occurrence becomes an order-line row |
| 2NF | Does a non-key attribute depend on only part of a composite key? | Customer and product facts move away from OrderLines |
| 3NF | Does a non-key attribute depend transitively on another non-key determinant? | CategoryName moves into Categories |
| Denormalization | Is selected duplication justified by a measured workload? | A reporting snapshot copies joined facts for faster reads |

This separation prevents the concepts from being treated as interchangeable.

---

# Implementation Relationship

The three programs intentionally approach the topic from different technical perspectives.

The **Python implementation** emphasizes executable relational reasoning, anomaly detection, closure computation, decomposition, validation, and a normalized in-memory transactional model.

The **JavaScript implementation** emphasizes event-driven transformation, Set-based dependency processing, Map-based repository structures, and a materialized-view pattern suitable for application-facing read models.

The **C++ implementation** treats normalization as a compact database-engineering case study, using explicit domain structures, standard-library associative containers, functional-dependency closure, decomposition checks, and integrity validation.

The implementations share the same business domain so that the normalization concepts remain comparable, but their internal mechanisms are deliberately different rather than being direct language translations of one another.

---

# Production Schema Perspective

A production relational implementation might conceptually use tables such as:

`customers(customer_id, customer_name, city)`

`categories(category_id, category_name)`

`products(product_id, product_name, category_id, current_unit_price)`

`orders(order_id, customer_id, order_timestamp, ...)`

`order_lines(order_id, product_id, quantity, charged_unit_price, ...)`

The exact schema depends on business rules.

For example, if a product can belong to multiple categories, `products.category_id` would not represent that relationship correctly. A separate association relation could be required.

If an order line can contain the same product more than once, `(OrderID, ProductID)` may not be the correct key.

If product prices require historical validity periods, a temporal pricing design may be more appropriate than a single current-price attribute.

These decisions demonstrate why normalization depends on accurate functional dependencies and domain rules.

---

# Core Technical Principle

Normalization is best understood as **dependency-driven placement of facts**.

1NF establishes an appropriate tuple representation and atomic values.

2NF removes facts that depend on only part of a composite key.

3NF removes facts that depend transitively through another determinant.

Denormalization deliberately duplicates selected facts when a specific workload makes that trade-off worthwhile.

The strongest schema designs do not treat normalization as a rigid table-count exercise. They identify the facts represented by each relation, establish the functional dependencies that hold for those facts, select keys that represent real business identity, decompose relations without losing information, preserve important dependencies, and introduce controlled duplication only when its operational cost and consistency behavior are understood.
