# API Design: Versioning, Pagination, Filtering, and Error Handling

## 1. Topic Introduction

API design is the discipline of defining how software systems expose functionality and data to other software.

An HTTP API establishes a contract between clients and servers. The contract determines:

- Which resources exist
- Which URLs identify those resources
- Which HTTP methods operate on them
- What request data clients may provide
- What response data servers return
- Which HTTP status codes represent different outcomes
- How errors are represented
- How large collections are retrieved
- How clients filter and sort data
- How the API evolves without unnecessarily breaking existing consumers
- How invalid, duplicated, delayed, or retried requests are handled

This study uses a Product Catalog API as its central example. The three implementations approach the subject differently:

- Python provides a broad educational implementation with a repository, service layer, filtering, pagination, versioning, validation, errors, idempotency, and executable tests.
- JavaScript emphasizes asynchronous application behavior, query-string processing, Promise-based operations, serialization, retries, and API-style controller behavior.
- C++ presents a more strongly structured technical case study with explicit domain types, repository and service layers, algorithms, complexity analysis, cursor pagination, and structured API responses.

---

## 2. Fundamental API Concepts

### 2.1 API

An Application Programming Interface defines how one software component interacts with another.

An API does not necessarily mean HTTP. APIs can exist between:

- Functions
- Classes
- Libraries
- Operating-system components
- Applications
- Microservices
- Web clients and servers
- Databases and applications

This topic concentrates on HTTP-based application APIs.

### 2.2 Client

The client initiates a request.

Examples include:

- Web applications
- Mobile applications
- Command-line programs
- Backend services
- Automated integrations
- Data-processing systems

### 2.3 Server

The server receives requests, applies business rules, accesses data, and returns responses.

### 2.4 Resource

A resource represents a domain object or collection.

Examples:

- `/products`
- `/products/42`
- `/customers`
- `/orders/1001`

A resource-oriented API generally uses nouns rather than verbs in resource paths.

### 2.5 Endpoint

An endpoint is a callable API operation identified by a method and URI.

For example:

`GET /api/v1/products`

and:

`GET /api/v1/products/42`

represent different operations even though both use the `products` resource.

### 2.6 Representation

A resource may have different representations.

JSON is common because it maps naturally to objects, arrays, strings, numbers, booleans, and null values.

A representation is not necessarily the resource itself. It is a serialized view of the resource.

---

## 3. HTTP Methods

### GET

Used to retrieve information.

Examples:

`GET /api/v1/products`

`GET /api/v1/products/42`

GET should normally be safe and should not cause an unintended state-changing operation.

### POST

Commonly used to create a new resource.

Example:

`POST /api/v1/products`

A successful creation commonly returns HTTP `201 Created`.

### PUT

Normally represents replacement of a resource.

For example:

`PUT /api/v1/products/42`

The client generally supplies the complete representation required by the replacement operation.

### PATCH

Used for partial modification.

Example:

`PATCH /api/v1/products/42`

PATCH semantics should be explicitly documented because different APIs may support different patch formats and rules.

### DELETE

Used to remove a resource.

Example:

`DELETE /api/v1/products/42`

A successful DELETE may return `204 No Content` when no response representation is necessary.

---

## 4. HTTP Status Codes

Status codes communicate the broad result of an HTTP request.

### Successful responses

| Status | Meaning | Typical API use |
|---|---|---|
| 200 | OK | Successful retrieval or operation |
| 201 | Created | Resource successfully created |
| 204 | No Content | Successful operation without response body |

### Client-side errors

| Status | Meaning | Typical API use |
|---|---|---|
| 400 | Bad Request | Malformed or invalid request |
| 401 | Unauthorized | Authentication required or invalid |
| 403 | Forbidden | Authentication exists but permission is insufficient |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Current state conflicts with request |
| 412 | Precondition Failed | Conditional request failed |
| 422 | Unprocessable Content | Request is syntactically valid but semantically invalid |
| 429 | Too Many Requests | Rate limit exceeded |

### Server-side errors

| Status | Meaning | Typical API use |
|---|---|---|
| 500 | Internal Server Error | Unexpected server failure |
| 503 | Service Unavailable | Temporary inability to serve the request |

An API should not return `200 OK` for every situation and put the real failure only inside the JSON body. HTTP status codes are part of the API contract.

---

## 5. API Resource Structure

A predictable resource structure makes APIs easier to consume.

A product collection can be represented as:

`/api/v1/products`

A particular product can be represented as:

`/api/v1/products/42`

Nested resources may be appropriate when there is a strong relationship:

`/api/v1/products/42/reviews`

The resource structure should represent domain relationships rather than implementation details.

---

## 6. API Versioning

API versioning controls incompatible changes to an API contract.

Suppose version 1 returns:

`price: 1499.99`

A later design might need:

`pricing: { amount: 1499.99, currency: "USD" }`

If an existing client expects `price` to be a number, simply replacing the field can break that client.

Versioning provides a controlled mechanism for such changes.

---

## 7. URL-Based Versioning

The Python, JavaScript, and C++ implementations use the conceptual form:

`/api/v1/products`

and:

`/api/v2/products`

Advantages:

- Easy to understand
- Easy to test
- Easy to route
- Easy to observe in logs
- Explicit to consumers

Trade-off:

- The version becomes part of the resource URL.

---

## 8. Header-Based Versioning

Another approach uses a request header.

A client could provide:

`API-Version: 2`

The URL can then remain:

`/api/products`

Advantages:

- Cleaner URLs
- Version selection can be handled through request metadata

Trade-offs:

- Less visible to casual users
- More complicated to test manually
- Routing and caching infrastructure must correctly account for version headers

---

## 9. Media-Type Versioning

A server can use content negotiation.

For example, a client could request a vendor-specific media type through the `Accept` header.

This approach can make the representation version part of content negotiation rather than the resource URL.

It requires careful documentation and correct handling of caches and intermediaries.

---

## 10. When Should an API Be Versioned?

Not every change requires a new major API version.

Potentially compatible changes include:

- Adding a new endpoint
- Adding optional response metadata
- Adding an optional request property when existing requests remain valid

Potentially breaking changes include:

- Removing a response field
- Renaming a response field
- Changing a field's type
- Changing the meaning of an existing field
- Making an optional request field mandatory
- Changing status-code behavior relied upon by clients

The key question is whether existing valid clients can continue to operate correctly.

---

## 11. Python Implementation

The Python implementation models the API using several layers.

### Product

The `Product` dataclass represents the domain object.

It contains:

- `product_id`
- `name`
- `category`
- `price`
- `stock`
- `active`
- `created_at`

Validation occurs when products are created.

### Repository

`ProductRepository` provides persistence-like operations:

- `list`
- `get`
- `create`
- `replace`
- `delete`

The implementation stores products in memory.

This abstraction separates storage concerns from API logic.

A production implementation could replace the repository with a database-backed implementation.

### Service

`ProductService` contains application and business logic.

The service performs:

- Product lookup
- Validation
- Filtering
- Sorting
- Pagination
- Product creation

This keeps the controller from becoming a collection of business rules.

### Controller

`ProductAPI` acts like an HTTP controller.

It produces:

- Status codes
- Headers
- Response bodies

The implementation remains independent of a web framework so that the underlying API concepts are visible.

---

## 12. Python API Errors

The Python implementation defines `APIError` and `APIException`.

A structured error contains:

- Error code
- Human-readable message
- HTTP status
- Optional details
- Request ID

An example conceptual response is:

`{"error":{"code":"PRODUCT_NOT_FOUND","message":"The requested product does not exist","request_id":"..."}}`

Machine-readable error codes are important because clients should not have to parse human-readable messages to determine what happened.

---

## 13. Error Code Design

A useful error code should be stable and meaningful.

Examples from the implementation include:

- `PRODUCT_NOT_FOUND`
- `INVALID_PRODUCT_ID`
- `INVALID_PAGE`
- `INVALID_PAGE_SIZE`
- `INVALID_PRICE_RANGE`
- `INVALID_SORT_FIELD`
- `UNSUPPORTED_API_VERSION`
- `PRODUCT_ALREADY_EXISTS`
- `INVALID_CURSOR`
- `VALIDATION_ERROR`

An error message can change for clarity without necessarily requiring client logic to change if the machine-readable code remains stable.

---

## 14. Request IDs

The implementations include a request ID in API responses.

A request ID is useful for tracing an individual request through:

- API logs
- Application logs
- Database operations
- Distributed services
- Monitoring systems
- Support investigations

A client can report the request ID when an operation fails.

Request IDs should not be used as authentication credentials.

---

## 15. Pagination

Pagination prevents an API from returning an uncontrolled number of records.

Suppose an API contains one million products.

Returning all one million records in a single response can cause:

- Large memory consumption
- Long response times
- High network traffic
- Expensive serialization
- Client-side performance problems
- Database pressure

Pagination divides the collection into manageable pieces.

---

## 16. Offset Pagination

Offset pagination commonly uses:

- `page`
- `page_size`

For example:

`GET /api/v1/products?page=3&page_size=20`

The offset is:

`offset = (page - 1) × page_size`

For page 3 with 20 records per page:

`offset = (3 - 1) × 20 = 40`

The server retrieves records beginning at position 40.

### Advantages

- Simple
- Familiar
- Easy to display in traditional interfaces
- Easy to jump to a numbered page

### Disadvantages

Large offsets may become expensive.

If the database has to locate a very large offset, it may process many records that are ultimately discarded.

Offset pagination can also behave unexpectedly when records are inserted or deleted while a client is moving through pages.

---

## 17. Cursor Pagination

Cursor pagination identifies a position rather than a page number.

A response may conceptually contain:

`next_cursor`

The client sends that cursor when requesting the next page.

The cursor should be treated as an opaque token.

Clients should not depend on its internal structure.

The implementations use product IDs for educational purposes.

Production cursor designs often use a stable ordering such as:

`(created_at, id)`

This is useful because timestamps alone may not be unique.

---

## 18. Cursor Stability

A cursor must be associated with a deterministic ordering.

For example, sorting only by price can be ambiguous because multiple products can have the same price.

A stronger ordering can be:

`ORDER BY price, id`

The first field provides the primary order.

The ID provides a deterministic tie-breaker.

Stable ordering is critical for avoiding duplicates and omissions while traversing pages.

---

## 19. Filtering

Filtering allows clients to request only records matching specific criteria.

Examples include:

`category=electronics`

`min_price=100`

`max_price=500`

`min_stock=10`

`active=true`

`search=monitor`

A filtered endpoint reduces unnecessary data transfer and allows clients to perform more precise queries.

---

## 20. Combining Filters

Multiple filters can be combined.

For example:

`category=electronics`

`min_price=50`

`max_price=500`

`min_stock=10`

The result contains products satisfying all supplied conditions.

The implementation validates the range before applying it.

A request such as:

`min_price=500&max_price=100`

is invalid because the lower bound exceeds the upper bound.

---

## 21. Filtering and Database Design

The demonstration implementations filter in application memory because the goal is to make the logic visible.

Production systems normally push filtering into the database when the dataset is large.

For example, a relational database may use indexed columns for:

- Category
- Price
- Stock
- Creation time
- Status

A query can then avoid loading unrelated records into application memory.

---

## 22. Sorting

Sorting allows clients to specify the ordering of results.

Examples:

`sort_by=price`

`sort_by=name`

`sort_by=created_at`

An API should not allow arbitrary client-controlled database expressions.

The implementations use an allow-list of supported fields.

This prevents clients from injecting unexpected expressions into a database query.

---

## 23. Sort Direction

A common API convention is:

`order=asc`

or:

`order=desc`

The server should validate the supplied value.

An invalid sort field should produce a structured client error rather than being passed directly into database logic.

---

## 24. Pagination Limits

An API should enforce a maximum page size.

The implementations use a maximum of 100.

Without a maximum, a client could request:

`page_size=100000000`

Such a request could consume excessive:

- Memory
- CPU
- Database resources
- Network bandwidth
- Serialization time

Pagination limits are therefore both performance and availability controls.

---

## 25. JavaScript Implementation

The JavaScript implementation emphasizes behavior that is particularly relevant to application and web development.

### Asynchronous repository

`ProductRepository` methods are asynchronous.

Although the example uses in-memory storage, the asynchronous structure resembles real database calls.

Real database operations are commonly asynchronous because they involve I/O.

### Promise-based error handling

The API methods use `async` and `await`.

Errors are caught by the controller and converted into API responses.

This is important because asynchronous exceptions must be handled consistently.

---

## 26. JavaScript URL Query Parsing

The implementation uses the standard `URL` and `URLSearchParams` APIs.

For example:

`/api/v2/products?page=1&pageSize=3&category=electronics`

can be parsed into structured values.

This demonstrates an important distinction:

The URL query string is textual input.

The application must convert and validate those values before using them.

For example:

`page=abc`

cannot safely become a numeric page number.

---

## 27. JavaScript Serialization

The `Product` class provides:

- `toV1()`
- `toV2()`

This makes representation changes explicit.

Version 1 exposes a direct `price` property.

Version 2 groups pricing and inventory information.

This illustrates how the same domain object can have multiple external representations.

The internal model does not necessarily need to have the same shape as the public API representation.

---

## 28. JavaScript Retry Behavior

The `retryOperation` function demonstrates exponential backoff.

A simplified delay sequence might be:

- Attempt 1: short delay
- Attempt 2: approximately twice the delay
- Attempt 3: approximately four times the original delay

The implementation also adds jitter.

Jitter prevents many clients from retrying at exactly the same moment after a shared failure.

Retries should generally be restricted to operations that are safe to retry.

A non-idempotent operation should not automatically be repeated merely because a network timeout occurred.

---

## 29. Idempotency

Idempotency concerns the effect of repeating an operation.

For example, a client sends:

`POST /api/v2/products`

The server creates the product.

The response is lost because of a network failure.

The client does not know whether creation succeeded.

If the client sends the same request again, the server could create a duplicate.

An idempotency key provides a way to identify the logical operation.

Example:

`Idempotency-Key: create-001`

The server stores the result associated with the key.

A retry using the same key can return the original result instead of creating another resource.

---

## 30. Idempotency Requirements

A production implementation should consider:

- Key uniqueness
- Key expiration
- Client identity
- Request payload consistency
- Storage durability
- Concurrent requests using the same key
- What happens after server restarts
- Whether the original response is retained

Simply storing an in-memory key is insufficient for a distributed production system.

The examples use memory to demonstrate the concept.

---

## 31. HTTP Safety and Idempotency

These concepts are related but different.

A safe operation does not intentionally change server state.

GET is normally safe.

An idempotent operation can be repeated without changing the final intended state after the first successful execution.

PUT and DELETE are generally defined as idempotent in HTTP semantics, while POST is not inherently idempotent.

Application-level idempotency mechanisms can make selected POST operations safe to retry.

---

## 32. C++ Case Study

The C++ implementation models a Product Catalog API as an industry-style layered system.

Its architecture contains:

1. Domain model
2. Validation
3. Repository
4. Filtering
5. Sorting
6. Pagination
7. Service
8. Error model
9. API controller
10. Idempotency store
11. Response serialization
12. Executable tests

This separation demonstrates how a larger application can avoid putting every responsibility into one function.

---

## 33. C++ Domain Model

The `Product` structure contains:

- ID
- Name
- Category
- Price
- Stock
- Active state
- Creation timestamp

The implementation uses explicit C++ types.

This provides stronger compile-time structure than dynamically shaped objects.

---

## 34. C++ Repository

`ProductRepository` stores products using an `unordered_map`.

The key is the product ID.

An average hash-table lookup is approximately O(1), although worst-case behavior depends on hashing and table state.

The repository hides the storage structure from the service layer.

A production implementation could replace the in-memory repository with a database adapter.

---

## 35. C++ Service Layer

`ProductService` provides application-level operations.

It performs:

- Product retrieval
- Filtering
- Sorting
- Pagination
- Validation-related coordination

This keeps HTTP response formatting outside the business layer.

The service can therefore be tested independently of HTTP transport.

---

## 36. C++ API Controller

`ProductAPI` converts application outcomes into HTTP-style responses.

The response contains:

- Status
- Headers
- Body

This resembles the responsibility of a controller in a web framework.

The implementation deliberately does not require an HTTP framework so that the underlying architecture remains visible.

---

## 37. C++ Versioned Representations

The C++ implementation uses an `APIVersion` enumeration.

Supported versions include:

- `V1`
- `V2`

The `serializeProduct` function chooses the public representation based on the requested version.

This demonstrates a valuable architectural distinction:

Domain model:

The internal representation of a product.

API representation:

The representation exposed to external consumers.

They do not have to be identical.

---

## 38. C++ Filtering Algorithm

The filter process evaluates each product against the supplied criteria.

For `n` products, an in-memory filter pass is O(n).

Each product may be checked against:

- Category
- Minimum price
- Maximum price
- Minimum stock
- Active state
- Search term

Production systems with large datasets should normally translate these conditions into database queries rather than loading all records first.

---

## 39. C++ Sorting Algorithm

The C++ implementation uses `std::sort`.

Typical complexity is O(n log n).

The API restricts the sort field to known values:

- ID
- Name
- Category
- Price
- Stock

The allow-list is important because arbitrary client input should never become arbitrary database or expression syntax.

---

## 40. Offset Pagination Complexity

The demonstration performs filtering and sorting before slicing a page.

Therefore the complete operation can involve:

- O(n) filtering
- O(n log n) sorting
- O(1) vector slicing after the ordering is established

The dominant term is typically O(n log n) in the demonstration.

A production database can optimize this considerably through indexes and query planning.

---

## 41. Cursor Pagination Complexity

The C++ demonstration sorts the in-memory collection before locating the cursor.

That means its educational implementation is not equivalent to an indexed production cursor.

In a database with an appropriate index, a cursor query can approach:

O(log n + k)

where:

- `n` is the number of indexed records
- `k` is the number of records returned

The exact complexity depends on the database, index, ordering, and query plan.

---

## 42. Stable Ordering

Pagination requires deterministic ordering.

Suppose two products have the same price.

Sorting only by price leaves their relative ordering potentially ambiguous.

A robust API can use:

`price, id`

The price is the primary ordering key.

The ID is the deterministic tie-breaker.

This reduces the risk of duplicated or missing records across pages.

---

## 43. Error Handling Architecture

The implementations use a structured error model instead of returning raw programming-language exceptions to clients.

Internal exception:

A programming or infrastructure detail.

API error:

A stable public contract.

These should not be treated as identical.

For example, a database exception might contain:

- Connection information
- SQL details
- Internal table names
- Stack traces

Such information should generally not be exposed to clients.

Instead, the API can return a controlled error such as:

`INTERNAL_SERVER_ERROR`

while logging the internal failure securely.

---

## 44. Validation

Validation should occur before unsafe or invalid values reach deeper layers.

Examples:

- Page must be positive.
- Page size must be within the allowed maximum.
- Price cannot be negative.
- Stock cannot be negative.
- Required fields must exist.
- Sort fields must belong to an allow-list.
- API versions must be supported.
- Cursor values must be valid.
- Range boundaries must be logically consistent.

Validation should not be treated as a substitute for authorization.

A syntactically valid request can still be unauthorized.

---

## 45. Authentication and Authorization

Authentication answers:

Who is the caller?

Authorization answers:

What is that caller allowed to do?

These are different concerns.

For example, a user may be authenticated but still not have permission to:

- Delete a product
- Change inventory
- Access administrative data
- View private pricing information

The API examples focus on design rather than implementing a complete authentication system.

Production APIs should integrate authentication and authorization explicitly.

---

## 46. Security Considerations

Important API security practices include:

- Use HTTPS.
- Authenticate protected endpoints.
- Authorize every protected resource.
- Validate all client-controlled input.
- Restrict pagination sizes.
- Allow-list sort and filter fields.
- Use parameterized database queries.
- Do not expose secrets in responses.
- Do not expose stack traces to external clients.
- Apply rate limiting.
- Log security events appropriately.
- Avoid logging credentials or sensitive tokens.
- Use an appropriate CORS policy for browser applications.
- Treat uploaded and user-supplied content as untrusted.

---

## 47. Rate Limiting

Rate limiting controls how frequently a client can make requests.

It can protect against:

- Accidental request storms
- Abusive clients
- Resource exhaustion
- Poorly implemented retry loops
- Certain denial-of-service scenarios

A rate-limited response commonly uses HTTP `429 Too Many Requests`.

A production API may also provide retry metadata indicating when the client should attempt another request.

---

## 48. Caching

Caching can improve API performance.

HTTP caching mechanisms include headers such as:

- `Cache-Control`
- `ETag`
- `Last-Modified`
- `If-None-Match`
- `If-Modified-Since`

An ETag can represent a version of a resource.

A client can ask whether its cached representation is still current.

If nothing changed, the server may return `304 Not Modified`.

Caching rules must be compatible with the sensitivity and freshness requirements of the data.

---

## 49. Conditional Requests

Conditional requests help prevent unnecessary transfers and can support concurrency control.

For example:

A client retrieves a product and receives an ETag.

The client later sends an update with:

`If-Match: <etag>`

If the resource has changed since the client retrieved it, the server can reject the update.

This protects against lost updates.

---

## 50. Optimistic Concurrency

Consider two clients:

1. Client A reads product version 10.
2. Client B reads product version 10.
3. Client A updates the product, producing version 11.
4. Client B attempts to update using version 10.

Without concurrency control, Client B could overwrite Client A's changes.

With an appropriate precondition, the server can reject Client B's stale update.

This is an important production consideration for mutable resources.

---

## 51. Common API Mistakes

### Returning HTTP 200 for failures

A client must inspect every response body to determine whether the request actually succeeded.

Use appropriate HTTP status codes.

### Unlimited page size

This allows clients to request unreasonably large result sets.

Use a maximum.

### Arbitrary sorting

Do not allow unrestricted client strings to become database expressions.

Use an allow-list.

### Inconsistent errors

Different endpoints should not return completely unrelated error structures for similar failures.

### Leaking internal exceptions

Internal database or application details should not become public API errors.

### Unstable pagination

Pagination should use deterministic ordering.

### Unplanned breaking changes

Changing a field's type or meaning can break clients even when the endpoint URL remains unchanged.

### Excessive versioning

Creating a new version for every minor change increases operational and maintenance complexity.

---

## 52. API Documentation as a Contract

Documentation should specify:

- Endpoint
- HTTP method
- Authentication requirements
- Request parameters
- Request body
- Response structure
- Status codes
- Error codes
- Pagination behavior
- Filtering rules
- Sorting rules
- Version policy
- Rate limits where relevant
- Idempotency behavior where relevant

Documentation should describe actual behavior rather than an idealized behavior that the implementation does not follow.

---

## 53. Backward Compatibility

Backward compatibility means existing valid clients can continue functioning after a change.

Compatibility is not limited to JSON field names.

Potentially breaking changes include:

- Removing fields
- Renaming fields
- Changing types
- Changing meanings
- Changing required fields
- Changing authentication behavior
- Changing error codes relied upon by clients
- Changing pagination semantics
- Changing ordering guarantees

A compatibility review should consider all of these.

---

## 54. Error Contract Stability

Suppose an API originally returns:

`PRODUCT_NOT_FOUND`

A client may use that code to display a specific message or recovery action.

Changing it randomly to:

`MISSING_PRODUCT`

may break client logic even if both messages mean the same thing.

Stable error codes therefore function as part of the public API contract.

Human-readable messages should remain understandable but should not normally be the primary machine-readable identifier.

---

## 55. Filtering Versus Search

Filtering and search are related but different.

Filtering commonly applies structured constraints:

`category=electronics`

`min_price=100`

Search commonly applies text-oriented matching:

`search=wireless mouse`

Search can require different infrastructure for large datasets, including specialized indexes.

The appropriate implementation depends on:

- Dataset size
- Search complexity
- Language requirements
- Ranking requirements
- Latency expectations
- Update frequency

---

## 56. Pagination and Mutable Data

Suppose a client retrieves page 1.

Between that request and page 2:

- A new product is inserted.
- A product is deleted.
- A product's sort value changes.

Offset pagination may then produce:

- Duplicate records
- Missing records
- Records appearing on different pages

Cursor pagination can reduce some of these problems when based on a stable ordering, but it does not automatically solve every consistency issue.

For highly consistent workflows, the API may need stronger snapshot or transaction semantics.

---

## 57. API Performance

Performance should be evaluated across the entire request path.

Relevant components include:

- Network latency
- Authentication
- Application processing
- Database query time
- Serialization
- Response compression
- Client processing

Important design techniques include:

- Appropriate indexes
- Pagination
- Maximum page sizes
- Query filtering
- Response field selection
- Caching
- Efficient serialization
- Connection pooling
- Rate limiting
- Avoiding unnecessary downstream calls

---

## 58. N+1 Query Problem

An API may first retrieve a list of products and then make one database query per product to retrieve related information.

For `n` products, this can produce approximately `n + 1` database operations.

This can cause severe performance problems.

Possible solutions include:

- Joins
- Batch queries
- Preloading
- Data-loader-style batching
- Carefully designed aggregate queries

The correct solution depends on the data model and access pattern.

---

## 59. Response Size

Large response objects consume:

- Network bandwidth
- Server memory
- Serialization CPU
- Client memory
- Client parsing CPU

Pagination controls collection size.

Field selection can control representation size.

For example, an API might allow a client to request only:

`id,name,price`

instead of returning every available field.

Such features require careful validation and documentation.

---

## 60. API Observability

Production APIs should provide enough information to diagnose failures.

Useful telemetry includes:

- Request ID
- Trace ID
- HTTP method
- Route
- Status code
- Latency
- Database duration
- Error code
- Rate-limit events
- Authentication failures

Logs should avoid sensitive information.

Observability data should be structured so it can be searched and aggregated.

---

## 61. Python, JavaScript, and C++ Comparison

| Area | Python | JavaScript | C++ |
|---|---|---|---|
| Main emphasis | Broad educational API implementation | Async and application behavior | Structured technical case study |
| Data modeling | Dataclass | Class | Struct |
| Errors | Custom exceptions | Error subclasses | Explicit exception structures |
| Pagination | Offset and cursor | Offset and cursor | Offset and cursor |
| Versioning | v1/v2 serializers | v1/v2 serializers | Explicit enum |
| Filtering | Dataclass filter | Object options | Typed filter structure |
| Async behavior | Synchronous demonstration | Async/Await | Synchronous standard-library model |
| Repository | In-memory dictionary | Map | Unordered map |
| Testing | Executable assertions | Async test functions | Explicit test function |
| Complexity focus | Conceptual | Application behavior | Explicit algorithm analysis |

---

## 62. Why Python Is Useful Here

Python makes architectural concepts concise.

The implementation demonstrates:

- Dataclasses
- Exceptions
- Dictionaries
- Type hints
- Repository abstraction
- Service abstraction
- Filtering
- Pagination
- Serialization
- Executable tests

Python's concise syntax makes it useful for expressing API behavior without requiring extensive infrastructure code.

---

## 63. Why JavaScript Is Useful Here

JavaScript is particularly relevant to HTTP API consumers and web applications.

The implementation demonstrates:

- `async` and `await`
- Promise-based operations
- URL parsing
- Query parameters
- Object serialization
- Client-side-style validation
- Retry behavior
- Idempotency
- Asynchronous repositories

The same concepts can be adapted to server-side JavaScript runtimes and browser applications.

---

## 64. Why C++ Is Useful Here

C++ makes data representation and algorithmic behavior explicit.

The case study demonstrates:

- Strongly typed domain structures
- Enumerated API versions
- Repository architecture
- Explicit sorting algorithms
- Pagination algorithms
- Complexity considerations
- Memory-oriented data structures
- Exception handling
- Standard-library abstractions

This makes C++ useful when API implementation is part of a performance-sensitive or systems-oriented application.

---

## 65. Edge Cases Covered

The implementations explicitly consider:

- Missing resources
- Invalid resource IDs
- Unsupported API versions
- Invalid page numbers
- Excessive page sizes
- Invalid page limits
- Invalid cursors
- Negative prices
- Negative stock
- Invalid price ranges
- Unsupported sort fields
- Missing required fields
- Duplicate resource IDs
- Empty search terms
- Empty collections
- Last cursor page
- Idempotent retries
- Transient server failures
- Unexpected internal errors

---

## 66. Production Considerations

The examples intentionally use in-memory data.

A production implementation would normally add:

- Real HTTP server infrastructure
- Database persistence
- Database transactions
- Connection pooling
- Authentication
- Authorization
- HTTPS
- Rate limiting
- Distributed idempotency storage
- Structured logging
- Distributed tracing
- Metrics
- Health checks
- Deployment configuration
- Secret management
- API documentation
- Automated integration testing
- Contract testing
- Database indexes
- Cache infrastructure where appropriate

These are architectural extensions rather than replacements for the API design principles demonstrated here.

---

## 67. Important Design Distinctions

### API model versus database model

The database schema is an implementation detail.

The API model is a public contract.

They should not be assumed to be identical.

### Validation versus authorization

Validation determines whether input is acceptable.

Authorization determines whether the caller is allowed to perform the requested action.

### Pagination versus filtering

Filtering determines which records qualify.

Pagination determines how many qualifying records are returned in a response.

### Versioning versus deployment version

An API version is a public contract identifier.

An internal application deployment version can change many times without changing the public API version.

### Error message versus error code

The message is intended for human understanding.

The code is intended to provide stable machine-readable behavior.

---

## 68. Practical API Design Checklist

### Resource design

- Use stable resource names.
- Prefer nouns for resource paths.
- Keep individual resources addressable.
- Define relationships clearly.

### HTTP semantics

- Use methods consistently.
- Return appropriate status codes.
- Define idempotency expectations.
- Define safe and retryable operations.

### Versioning

- Identify breaking changes.
- Define a versioning strategy.
- Preserve existing clients where practical.
- Avoid unnecessary versions.

### Pagination

- Define default page sizes.
- Define maximum page sizes.
- Use deterministic ordering.
- Choose offset or cursor pagination based on data characteristics.

### Filtering

- Document supported filters.
- Validate ranges.
- Use allow-lists.
- Push large-data filtering into the database where practical.

### Sorting

- Allow-list sortable fields.
- Define ascending and descending behavior.
- Provide deterministic tie-breaking.

### Errors

- Use meaningful HTTP status codes.
- Define stable error codes.
- Avoid leaking internal details.
- Include request IDs where useful.

### Security

- Authenticate protected operations.
- Authorize resources and actions.
- Validate input.
- Use HTTPS.
- Protect database queries.
- Apply rate limits.
- Avoid exposing secrets.

### Performance

- Use indexes appropriately.
- Avoid unbounded queries.
- Control response size.
- Measure database latency.
- Consider caching.
- Avoid N+1 queries.

### Operations

- Log structured events.
- Include request and trace identifiers.
- Monitor latency and error rates.
- Test failure conditions.
- Document compatibility expectations.

---

## 69. Core Technical Principles Demonstrated

The implementations collectively demonstrate several principles that remain important regardless of programming language:

1. An API is a contract, not merely a collection of URLs.
2. HTTP status codes are part of that contract.
3. Public representations should be deliberately designed.
4. Internal domain models do not have to equal external representations.
5. Pagination protects both clients and servers.
6. Filtering reduces unnecessary data processing and transfer.
7. Sorting should use controlled fields.
8. Cursor pagination requires deterministic ordering.
9. Breaking changes require deliberate compatibility management.
10. Error responses should be structured and stable.
11. Validation must cover client-controlled input.
12. Retries require careful consideration of idempotency.
13. Authentication and authorization solve different problems.
14. Performance decisions depend on dataset size and access patterns.
15. Production API design includes observability, security, reliability, and operational behavior in addition to endpoint syntax.
