# Web Architecture and REST APIs: Resources, Endpoints, Methods, and Statelessness

## Topic introduction

REST APIs are a common architectural approach for exposing application resources through HTTP. A REST-style API uses resource identifiers, standardized HTTP methods, representations, status codes, headers, and stateless request processing to establish a predictable interface between clients and servers.

The central concepts in this study are:

- Web architecture
- APIs
- REST
- Resources
- Resource representations
- Endpoints
- URI design
- HTTP methods
- HTTP requests and responses
- HTTP status codes
- Statelessness
- Idempotence
- Validation
- Filtering
- Sorting
- Pagination
- Caching
- Conditional requests
- Content negotiation
- Authentication
- Authorization
- Rate limiting
- Routing
- Versioning
- Error handling
- Observability
- Security
- Performance
- Testing
- Production architecture

The three implementations approach the same subject from different technical perspectives. Python emphasizes conceptual modeling and an educational resource service. JavaScript emphasizes application-level API behavior, asynchronous programming, request handling, and browser/server-oriented patterns. C++ presents an industry-style product catalog architecture with repositories, routing, authentication, authorization, rate limiting, validation, and a simulated API gateway.

---

## Web architecture fundamentals

A web application usually involves several cooperating components rather than a single program.

A simplified architecture can contain:

1. A client
2. DNS and networking infrastructure
3. TLS
4. A load balancer or API gateway
5. An API application
6. Authentication and authorization components
7. Business logic
8. A database
9. External services
10. Caching infrastructure
11. Logging, metrics, and tracing systems

A client may be a web browser, mobile application, desktop application, command-line program, another service, or an automated process.

The client sends an HTTP request to a server. The server interprets the request, performs the required operation, and returns an HTTP response.

A typical request contains:

- HTTP method
- Request target or path
- Headers
- Query parameters
- Optional request body

A response commonly contains:

- HTTP status code
- Response headers
- Optional response body

REST does not define a single programming language, database, framework, or deployment model. It is an architectural style whose constraints influence how the interface between client and server is designed.

---

## REST architectural style

REST stands for Representational State Transfer.

Important REST constraints include:

### Client-server separation

The client and server have different responsibilities.

The client is responsible for the user-facing or client-facing interaction. The server manages resources and application-side processing.

This separation allows client and server implementations to evolve independently as long as their interface remains compatible.

### Statelessness

Each request should contain the information required for the server to understand and process that request.

The server should not need to recover an implicit conversational context from a previous request.

For example, a request such as `GET /api/v1/products/101` should contain sufficient information for the server to understand which resource is being requested.

Authentication credentials or an access token may be included in each protected request.

Statelessness does not mean that the server has no data. A server can maintain persistent resource data in a database. It means that the server does not rely on hidden session state to understand the sequence of requests.

### Cacheability

Responses can indicate whether they may be cached.

HTTP headers such as `Cache-Control`, `ETag`, and `Last-Modified` can participate in caching and conditional requests.

Caching can reduce network traffic, computation, and database load, but stale data and invalidation must be considered.

### Uniform interface

REST emphasizes a consistent interface for resource interaction.

The combination of resource identifiers and HTTP semantics provides a common vocabulary:

- `GET` for retrieval
- `POST` for creation or other non-idempotent processing
- `PUT` for replacement
- `PATCH` for partial modification
- `DELETE` for removal

### Layered system

A client does not necessarily communicate directly with the final application server.

There may be layers such as:

- CDN
- reverse proxy
- API gateway
- load balancer
- authentication service
- application service
- database
- external service

Each layer can provide a specific function.

### Code-on-demand

Code-on-demand is an optional REST constraint. It permits servers to transfer executable code to clients.

The practical REST APIs demonstrated in this study do not depend on code-on-demand.

---

## Resources

A resource is a conceptual entity that the API exposes.

Examples include:

- User
- Product
- Order
- Payment
- Article
- Invoice
- Account
- Review
- Shipment

A resource is not necessarily the same thing as a database row.

The resource is an API-level concept. The underlying implementation could use:

- A relational database
- A document database
- An in-memory structure
- A cache
- Several databases
- Multiple downstream services
- A computed result

For example, `/api/v1/products/101` identifies a product resource with identifier `101`.

A collection is a resource representing a group of resources.

Examples:

- `/api/v1/products`
- `/api/v1/users`
- `/api/v1/orders`

An individual resource can be addressed by adding its identifier:

- `/api/v1/products/101`
- `/api/v1/users/7`
- `/api/v1/orders/450`

---

## Resources and representations

The resource itself is an abstract concept. A representation is the form transferred between client and server.

JSON is commonly used because it is compact, widely supported, and easy for many programming languages to process.

A product resource can be represented as:

`{"id":101,"name":"Mechanical Keyboard","price":3499}`

The Python implementation represents products with the `Product` dataclass and converts them into dictionaries.

The JavaScript implementation uses the `Product` class and its `toJSON()` method.

The C++ implementation uses the `Product` structure and a `toJson()` member function.

The three implementations demonstrate the same conceptual distinction:

- Resource: product
- Identifier: `101`
- Representation: JSON document describing that product

---

## Endpoints

An endpoint is commonly understood as a URI and HTTP method combination used to interact with an API.

For a product resource, the API can expose:

- `GET /api/v1/products`
- `GET /api/v1/products/101`
- `POST /api/v1/products`
- `PATCH /api/v1/products/101`
- `DELETE /api/v1/products/101`

The path identifies the resource or resource collection. The HTTP method communicates the requested operation semantics.

This is preferable to designing every operation as a verb embedded in the path.

For example, a resource-oriented approach uses:

`DELETE /api/v1/products/101`

rather than creating a separate operation-oriented path such as:

`POST /api/v1/deleteProduct`

The HTTP protocol already provides standardized method semantics, so resource-oriented API design can use that vocabulary directly.

---

## URI design

A well-designed resource URI should be predictable and consistent.

Common patterns include:

`/api/v1/products`

`/api/v1/products/101`

`/api/v1/products/101/reviews`

`/api/v1/products/101/reviews/7`

Plural nouns are commonly used for collections.

Query parameters are useful for modifying how a collection is retrieved:

`/api/v1/products?category=electronics`

`/api/v1/products?min_price=1000&max_price=5000`

`/api/v1/products?page=2&limit=20`

`/api/v1/products?sort=-price`

Query parameters should not be confused with path identifiers.

The path:

`/api/v1/products/101`

identifies product `101`.

The query:

`/api/v1/products?category=electronics`

requests a filtered representation of the product collection.

---

## HTTP methods

### GET

`GET` retrieves a representation.

Example:

`GET /api/v1/products/101`

Typical successful response:

`200 OK`

A GET request is safe and idempotent according to HTTP semantics.

Safe means the method is not intended to change resource state.

### POST

`POST` submits a representation for processing.

A common use is resource creation:

`POST /api/v1/products`

A successful creation commonly returns:

`201 Created`

POST is generally not idempotent.

Repeating a POST can create multiple resources unless application-level mechanisms such as idempotency keys prevent duplicate processing.

### PUT

`PUT` represents replacement of a resource representation.

Example:

`PUT /api/v1/products/101`

A PUT request is idempotent in HTTP semantics.

A client can repeat the same replacement request and the intended resulting resource state remains the same.

### PATCH

`PATCH` represents partial modification.

Example:

`PATCH /api/v1/products/101`

A body could contain only:

`{"price":3299}`

The server changes the price while preserving unspecified fields.

PATCH idempotence depends on the semantics of the particular patch operation.

### DELETE

`DELETE` requests removal of a resource.

Example:

`DELETE /api/v1/products/101`

A successful deletion can return:

`204 No Content`

DELETE is idempotent in HTTP semantics. Repeating a deletion does not require a different final resource state after the resource has already been removed.

### HEAD

`HEAD` is similar to GET but is used to retrieve response headers without the normal response body.

It can be useful when a client needs metadata without transferring the complete representation.

### OPTIONS

`OPTIONS` can be used to discover communication options supported by a resource or server.

It is also relevant to browser cross-origin request processing.

---

## Safe and idempotent methods

Safe and idempotent are different concepts.

A safe method does not intend to change resource state.

An idempotent method has the property that repeating the same request has the same intended effect on resource state.

For example:

`GET` is safe and idempotent.

`DELETE` is not safe, because it changes state, but it is idempotent.

`POST` is generally neither safe nor idempotent.

A method can be idempotent even though the server may produce logs, metrics, audit records, or other operational side effects.

Idempotence concerns the intended effect of repeating the operation.

---

## PUT versus PATCH

Consider a product:

`{"id":7,"name":"Monitor","category":"electronics","price":20000,"stock":10}`

A complete replacement could be represented by PUT:

`{"id":7,"name":"4K Monitor","category":"electronics","price":22000,"stock":8}`

A partial modification could use PATCH:

`{"price":21000}`

A major implementation question is how omitted fields are treated.

For PATCH, omission commonly means the field should remain unchanged.

For a replacement operation, the representation has broader significance because it describes the new complete state.

An API should document:

- Which fields are required
- Which fields are optional
- Which fields are immutable
- Whether `null` clears a value
- Whether omission preserves a value
- Which update operations are supported

---

## HTTP status codes

Status codes provide standardized high-level information about the result of a request.

Important codes demonstrated by the implementations include:

| Status | Meaning |
|---|---|
| 200 | Successful request |
| 201 | Resource created |
| 202 | Request accepted for processing |
| 204 | Successful response with no content |
| 304 | Cached representation remains valid |
| 400 | Bad request |
| 401 | Authentication required or invalid |
| 403 | Operation not permitted |
| 404 | Resource not found |
| 409 | Resource-state conflict |
| 412 | Conditional request failed |
| 415 | Unsupported media type |
| 422 | Semantically invalid content |
| 429 | Too many requests |
| 500 | Internal server error |
| 502 | Bad gateway |
| 503 | Service unavailable |
| 504 | Gateway timeout |

Status codes should be used consistently. Clients often depend on them to determine whether an operation succeeded, failed because of client input, or failed because of server-side conditions.

---

## HTTP request and response headers

Headers communicate metadata about HTTP messages.

Examples include:

`Content-Type: application/json`

This describes the representation being sent.

`Accept: application/json`

This communicates a representation the client is willing to receive.

`Authorization: Bearer token`

This carries an authentication credential in the example architecture.

`Cache-Control: max-age=60`

This provides caching information.

`ETag: "..."`

This identifies a representation version for conditional requests.

`Location: /api/v1/products/101`

This can identify the newly created resource after a successful creation.

`WWW-Authenticate: Bearer`

This can describe the authentication scheme expected after an authentication failure.

---

## Validation

Validation protects correctness and security.

A product creation request can require:

- A non-empty name
- A valid category
- A non-negative price
- A non-negative integer stock value

The Python implementation raises `ApiValidationError`.

The JavaScript implementation uses `ValidationError`.

The C++ implementation uses `ValidationException`.

All three implementations transform invalid input into a structured API-level error instead of allowing invalid values to enter the resource store.

A validation response can use status `422`.

An API should distinguish syntactic problems from semantic problems where useful.

For example:

- Malformed request structure can result in `400`.
- A validly structured request containing an invalid business value can result in `422`.

Exact status-code policies should be defined consistently for the API.

---

## Structured errors

A structured error representation is more useful than returning an unstructured sentence.

A representative error contains:

- Error code
- Human-readable message
- Field-specific validation information where applicable

For example, conceptually:

`{"error":{"code":"VALIDATION_ERROR","fields":{"price":"price must not be negative"}}}`

Clients can use stable error codes programmatically while users or logs can use the human-readable message.

Production error responses should avoid exposing:

- Stack traces
- Internal file paths
- Database credentials
- SQL statements
- Internal service topology
- Sensitive debugging information

---

## Python implementation

The Python script is designed as a progressive educational implementation.

### Core classes

`Product`

Models an API resource.

`HttpRequest`

Models an HTTP request.

`HttpResponse`

Models an HTTP response.

`ProductRepository`

Separates resource storage from application logic.

`ProductApi`

Provides resource-oriented operations.

`StatelessApi`

Demonstrates stateless authentication processing.

`PaymentService`

Demonstrates application-level idempotency keys.

`Router`

Demonstrates method-plus-path endpoint routing.

`AuthorizationService`

Demonstrates permission checks.

`FixedWindowRateLimiter`

Demonstrates a basic rate-limiting strategy.

`ApiMetrics`

Demonstrates endpoint-level metrics.

### Product lifecycle

The Python service demonstrates:

`POST /api/v1/products`

followed by:

`GET /api/v1/products`

then:

`GET /api/v1/products/{id}`

then:

`PATCH /api/v1/products/{id}`

and finally:

`DELETE /api/v1/products/{id}`

The implementation keeps the data in memory so the architectural concepts can be studied without a database dependency.

### Query processing

The Python implementation supports:

- Category filtering
- Minimum price
- Maximum price
- Page number
- Page size

It calculates the pagination slice with:

`start = (page - 1) * limit`

and:

`end = start + limit`

This is a simple offset-based pagination model.

### Python error handling

Invalid input is converted into an HTTP-style `422` response.

Missing resources result in `404`.

Invalid pagination results in `400`.

This shows how application exceptions can be translated into API-level protocol responses.

---

## JavaScript implementation

The JavaScript implementation emphasizes application-level behavior and asynchronous programming.

### JavaScript resource model

The `Product` class models a resource and implements `toJSON()`.

This demonstrates how JavaScript objects can control their serialized representation.

### Repository and controller

`ProductRepository` stores products in a JavaScript `Map`.

`ProductController` handles:

- Listing
- Filtering
- Sorting
- Pagination
- Retrieval
- Creation
- Partial updates
- Deletion

The separation between repository and controller mirrors the separation between storage and API logic.

### URL and query processing

The JavaScript implementation uses the `URL` and `URLSearchParams` APIs to parse:

`category`

`maxPrice`

`page`

`limit`

`sort`

This demonstrates how application code can convert an HTTP query string into structured filtering and pagination behavior.

### Asynchronous programming

The asynchronous examples use `async` and `await`.

A simulated fetch operation demonstrates the general shape of:

`fetch(url, options)`

followed by:

`await response.json()`

Real browser or Node.js applications can use the Fetch API for HTTP communication.

### Retry behavior

The JavaScript implementation identifies several statuses that can be candidates for retry:

- 408
- 429
- 500
- 502
- 503
- 504

It also demonstrates exponential backoff.

Retries should not be implemented blindly.

A retry policy should consider:

- HTTP method
- Operation idempotence
- Server guidance
- Rate limits
- Request timeout
- Maximum retry count
- Backoff
- Business consequences

A repeated payment request, for example, requires different treatment from a failed GET request.

---

## C++ industry-style case study

The C++ program models a product catalog API.

The system contains:

`Client`

↓

`API Gateway`

↓

`Authentication`

`Authorization`

`Rate Limiting`

↓

`Product API`

↓

`Product Repository`

The implementation does not depend on an external HTTP framework. Instead, it models the important REST concepts directly.

### Product resource

The `Product` structure contains:

- `id`
- `name`
- `category`
- `price`
- `stock`
- `active`
- `createdAt`

Its `toJson()` function produces a JSON representation.

### HTTP request

`HttpRequest` contains:

- Method
- Path
- Headers
- Query parameters
- Body fields

The body is represented using a map for educational simplicity.

A production HTTP server would normally receive raw HTTP data through an HTTP library or framework and perform proper parsing.

### HTTP response

`HttpResponse` contains:

- Status code
- Headers
- Body

The `print()` function provides a readable representation of the simulated response.

---

## C++ repository layer

`ProductRepository` isolates storage operations.

Its operations include:

- `create`
- `get`
- `list`
- `patch`
- `erase`

The example uses `std::map<int, Product>`.

A map provides approximately logarithmic lookup complexity.

The repository is deliberately separated from HTTP logic so that changing the persistence implementation does not require redesigning the API contract.

In a production system, the repository could instead communicate with:

- PostgreSQL
- MySQL
- SQL Server
- MongoDB
- Another persistence layer

The API contract does not need to expose the internal storage technology.

---

## C++ API layer

`ProductApi` translates application-level resource operations into HTTP responses.

Creation validates:

- Name
- Category
- Price
- Stock

A successful creation returns:

`201 Created`

and a `Location` header:

`/api/v1/products/{id}`

Retrieval returns:

`200 OK`

Missing resources return:

`404 Not Found`

Invalid data returns:

`422`

Invalid pagination returns:

`400`

Deletion returns:

`204 No Content`

This demonstrates the relationship between application behavior and HTTP semantics.

---

## C++ API gateway

The `ApiGateway` represents an infrastructure boundary.

It performs:

1. Rate limiting
2. Authentication
3. Authorization
4. Routing to API operations

This demonstrates that REST architecture does not require every responsibility to be implemented inside one controller.

An actual production gateway can also perform:

- TLS termination
- Request routing
- Load balancing
- API key checks
- Token validation
- Request size limits
- Observability
- CORS-related policy
- Traffic shaping

The exact division of responsibilities depends on the deployment architecture.

---

## Authentication and authorization

Authentication and authorization are different concepts.

Authentication asks:

"Who is making the request?"

Authorization asks:

"What is this identity permitted to do?"

The C++ case study uses simulated bearer tokens:

`Bearer token-customer`

`Bearer token-admin`

The admin identity has permissions for creation, update, and deletion.

A customer identity has a restricted permission set.

The tokens are deliberately hard-coded for demonstration. Production applications should not store authentication secrets this way.

Production authentication may involve:

- OAuth 2.0
- OpenID Connect
- Signed tokens
- Session-based mechanisms
- API keys
- Mutual TLS
- Enterprise identity systems

The appropriate mechanism depends on the application and threat model.

---

## Statelessness in the implementations

The Python implementation demonstrates a stateless API by authenticating each request from its supplied bearer credential.

The JavaScript implementation does the same with `StatelessApi`.

The C++ gateway accepts the authorization header as part of each request.

The key distinction is between resource state and conversational server state.

The server can persist:

- Products
- Users
- Orders
- Payments

while still maintaining stateless request processing.

Statelessness therefore does not mean "no database" and does not mean "no state anywhere."

It means that each request contains the necessary application context rather than depending on an implicit server-side conversation.

---

## Idempotency keys

HTTP method idempotence does not solve every duplicate-operation problem.

Consider a payment request:

`POST /api/v1/payments`

If a client sends the request and the network connection fails after the server has processed it, the client may not know whether the payment succeeded.

Blindly sending the POST again could create a duplicate operation.

An idempotency key provides an application-level mechanism:

`Idempotency-Key: checkout-2026-000001`

The server records the result associated with that key.

If the client retries with the same key, the server can return the previously recorded result rather than processing the business operation again.

The Python and JavaScript implementations demonstrate this concept.

Production idempotency systems need to consider:

- Key uniqueness
- Key lifetime
- Request-body consistency
- Concurrent duplicate requests
- Persistence
- Failure recovery
- Response replay
- Storage cleanup

---

## Filtering, sorting, and pagination

Collection endpoints commonly require mechanisms for controlling result sets.

Filtering:

`GET /api/v1/products?category=electronics`

Sorting:

`GET /api/v1/products?sort=-price`

Pagination:

`GET /api/v1/products?page=2&limit=20`

These controls prevent clients from requesting unnecessarily large collections.

### Offset pagination

Offset pagination can be represented as:

`page=2&limit=20`

Its advantages include:

- Simple client implementation
- Easy page-number interfaces
- Straightforward SQL concepts

Its limitations include:

- Large offsets can become expensive
- Results can shift when data changes
- Page numbers can become inconsistent during concurrent inserts or deletions

### Cursor pagination

A cursor-based API can use:

`?cursor=abc123&limit=20`

Cursor pagination can provide more stable traversal over large or changing datasets.

Its trade-offs include:

- More complicated client behavior
- Cursor encoding
- Cursor expiration
- Ordering requirements
- More complicated debugging

The appropriate strategy depends on dataset size and application behavior.

---

## Caching

Caching reduces repeated work.

A response can communicate:

`Cache-Control: max-age=60`

An ETag can identify a representation.

A client can send the previously received ETag in a conditional request.

If the representation has not changed, the server can return:

`304 Not Modified`

without sending the complete representation again.

The JavaScript implementation calculates a SHA-256 digest as an educational representation identifier.

The Python implementation demonstrates the conceptual flow.

Production cache design must consider:

- Cache lifetime
- Cache invalidation
- Private versus shared caching
- Authorization
- Sensitive data
- Varying representations
- Stale content
- Conditional requests

A cache must not accidentally expose one user's private representation to another user.

---

## Content negotiation

Content negotiation allows clients and servers to communicate representation preferences.

The client may send:

`Accept: application/json`

The server may return:

`Content-Type: application/json`

These headers have different purposes.

`Accept` describes what the client is willing to receive.

`Content-Type` describes the media type of the message body being sent.

Possible API media types include:

- `application/json`
- `application/problem+json`

An API can support multiple representations, although many modern APIs standardize on JSON for simplicity.

---

## Versioning

The examples use URI versioning:

`/api/v1/products`

A later incompatible API contract can use:

`/api/v2/products`

Other approaches include:

- Header-based versioning
- Media-type versioning

Versioning should be connected to compatibility requirements rather than added automatically to every change.

Backward-compatible changes can often include:

- Adding optional response fields
- Adding new endpoints
- Adding optional query parameters
- Extending documented enumerations carefully

Potentially breaking changes include:

- Removing fields
- Changing field meaning
- Changing data types
- Changing required request fields
- Changing authentication behavior
- Changing existing semantics

An API lifecycle should define how clients migrate between versions.

---

## Routing

Routing maps an HTTP method and path to application behavior.

For example:

`GET /api/v1/products/42`

can match:

`GET /api/v1/products/{id}`

The Python `Router`, JavaScript `Router`, and C++ `Router` demonstrate this concept using language-specific mechanisms.

A route should not be considered only as a path.

The following are different operations:

`GET /api/v1/products/42`

`PATCH /api/v1/products/42`

`DELETE /api/v1/products/42`

The URI is the same, but the method changes the requested semantics.

---

## Hypermedia

REST can use hypermedia controls in representations.

A product representation could contain:

`"links":{"self":{"href":"/api/v1/products/101"},"reviews":{"href":"/api/v1/products/101/reviews"}}`

This allows the representation to describe related navigational resources.

HATEOAS, Hypermedia as the Engine of Application State, is associated with the broader REST constraint set.

The examples include a small hypermedia representation but do not require a complete HATEOAS framework.

---

## Error handling

Good API error handling should provide enough information for a client to understand the failure without exposing sensitive internal information.

Important categories include:

### Client input errors

Examples:

- Invalid JSON
- Missing required fields
- Invalid field values
- Invalid pagination
- Unsupported media type

### Authentication errors

Examples:

- Missing token
- Invalid token
- Expired credentials

### Authorization errors

The caller is known but does not have permission.

### Resource errors

The requested resource does not exist.

### Conflict errors

The requested operation conflicts with current resource state.

Examples include:

- Duplicate unique identifier
- Version conflict
- Invalid state transition

### Server errors

Unexpected internal failures should be returned using appropriate 5xx status codes.

The client should not receive raw internal exception traces in production.

---

## Edge cases

The implementations explicitly demonstrate several edge cases.

### Missing resource

Request:

`GET /api/v1/products/9999`

Result:

`404 Not Found`

### Empty name

A product with an empty name is rejected.

### Negative price

A negative price is rejected.

### Negative stock

A negative stock quantity is rejected.

### Invalid pagination

Page numbers below one and excessive page sizes are rejected.

### Unknown update field

PATCH requests containing unsupported fields are rejected.

### Missing authentication

Protected POST, PATCH, and DELETE operations require authentication.

### Invalid authentication

An unknown bearer token results in an authentication failure.

### Unauthorized operation

An authenticated identity without the required permission receives a forbidden response.

### Rate limit exceeded

Requests beyond the configured fixed-window limit produce:

`429 Too Many Requests`

---

## Common mistakes

### Treating REST as CRUD only

REST is broader than CRUD.

CRUD is a useful conceptual mapping:

- Create
- Read
- Update
- Delete

REST also involves:

- Resource identification
- Representations
- HTTP semantics
- Statelessness
- Cacheability
- Uniform interface
- Layered architecture

### Using verbs unnecessarily in resource paths

Paths such as:

`/createProduct`

or:

`/deleteProduct`

often duplicate semantics already provided by HTTP methods.

A resource-oriented design can instead use:

`POST /products`

and:

`DELETE /products/{id}`

### Assuming every POST must be non-repeatable

POST is not idempotent by HTTP semantics, but application-level idempotency keys can make particular business operations safely retryable.

### Confusing authentication with authorization

A valid identity does not automatically have permission to perform every operation.

### Treating statelessness as "no state"

Databases and persistent resources can still exist.

Statelessness concerns request processing context.

### Returning HTTP 200 for every result

Clients benefit from meaningful status codes.

A missing resource is different from a successful retrieval.

Invalid input is different from an internal server failure.

### Exposing internal exceptions

Detailed stack traces can reveal sensitive information.

### Ignoring pagination

Large collections can create excessive memory use, network traffic, and response latency.

### Retrying every failure

Retries can amplify failures and duplicate non-idempotent operations.

### Ignoring concurrency

Two clients can modify the same resource simultaneously.

Production systems may require:

- Optimistic concurrency
- Version numbers
- ETags
- Conditional requests
- Database transactions

---

## Security considerations

REST APIs commonly operate across untrusted networks and must treat incoming data as untrusted.

Important controls include:

### TLS

HTTPS protects data in transit and helps prevent interception and modification.

### Authentication

Protected endpoints should verify the caller's identity.

### Authorization

Every sensitive operation should verify permissions.

### Input validation

Inputs should be validated before they reach business logic or persistence systems.

### Resource ownership

An authenticated user should not automatically be permitted to access every resource.

For example:

`GET /api/v1/orders/500`

must not disclose another user's private order merely because the requester has authenticated successfully.

### Rate limiting

Rate limits can reduce:

- Abuse
- Brute-force attempts
- Accidental request storms
- Resource exhaustion

### Secret management

Passwords, tokens, API keys, and cryptographic keys should not be embedded in source code.

### Safe error messages

Errors should be informative without exposing internal implementation details.

### Logging and auditing

Security-sensitive operations may require audit records.

Logs should also avoid storing credentials and unnecessary sensitive personal information.

---

## Performance considerations

API performance is influenced by multiple layers.

Important factors include:

- Network latency
- TLS overhead
- Gateway processing
- Application processing
- Serialization
- Database queries
- Database indexes
- Connection pools
- Cache hit rate
- Downstream services
- Response size
- Concurrency
- CPU usage
- Memory usage

The Python implementation demonstrates an O(n) in-memory filtering operation.

The C++ repository uses `std::map`, providing approximately O(log n) lookup by identifier.

The JavaScript implementation demonstrates O(n) array filtering.

These complexity characteristics are educational models.

A production API should usually push suitable filtering, sorting, pagination, and lookup operations into an appropriately indexed database rather than loading an entire large dataset into application memory.

---

## Observability

A production REST API should be observable.

Useful measurements include:

- Request count
- Error count
- Error rate
- Response latency
- Latency percentiles
- Status-code distribution
- Database latency
- Dependency latency
- Rate-limit events
- Resource utilization

The Python implementation provides `ApiMetrics`.

The JavaScript implementation provides `Metrics`.

These record request counts, errors, and average latency.

Average latency alone is insufficient for many production systems. A small number of extremely slow requests can be hidden by an average.

Percentiles such as p50, p95, and p99 are commonly useful when analyzing latency distributions.

Distributed tracing can also associate work across services using correlation or trace identifiers.

---

## API testing

Testing should cover both successful behavior and failure conditions.

The Python and JavaScript implementations contain executable assertions.

The C++ implementation uses `assertStatus()`.

Important API tests include:

### Resource creation

Verify:

- Valid input creates a resource
- Correct status code is returned
- Location information is correct where applicable
- Representation contains expected fields

### Retrieval

Verify:

- Existing resources return successfully
- Missing resources return `404`

### Update

Verify:

- Valid PATCH changes requested fields
- Unspecified fields remain unchanged
- Invalid fields are rejected

### Deletion

Verify:

- Existing resources can be deleted
- Deleted resources are no longer retrievable

### Authentication

Verify:

- Missing credentials are rejected
- Invalid credentials are rejected
- Valid credentials are accepted

### Authorization

Verify:

- Permitted operations succeed
- Forbidden operations are rejected

### Validation

Verify:

- Missing fields
- Invalid types
- Negative numeric values
- Invalid identifiers
- Invalid pagination

### Rate limiting

Verify that requests beyond the configured limit receive `429`.

---

## Python, JavaScript, and C++ comparison

| Area | Python | JavaScript | C++ |
|---|---|---|---|
| Primary emphasis | Conceptual API modeling | Application and asynchronous behavior | Systems-oriented case study |
| Resource model | Dataclass | Class | Struct |
| Storage | Dictionary | Map | `std::map` |
| Error model | Exceptions | Exceptions | Exceptions |
| Routing | Regex router | Regex router | Regex router |
| Async behavior | Primarily synchronous educational service | `async`/`await` and simulated Fetch API | Synchronous case-study architecture |
| Type system | Dynamic with type hints | Dynamic with modern language features | Static |
| Performance model | Simple and readable | Event-driven runtime | Explicit systems-level control |
| API gateway | Conceptual components | Separate demonstrations | Integrated gateway model |
| Authentication | Bearer token model | Bearer token model | Gateway-integrated bearer token model |
| Authorization | Permission service | Permission service | Gateway permission enforcement |
| Rate limiting | Fixed window | Fixed window | Fixed window |

The languages are useful for different aspects of the topic.

Python provides concise representations of architectural concepts and makes it easy to create complete demonstrations without framework dependencies.

JavaScript naturally connects API concepts with asynchronous application behavior and the Fetch API model used by modern web applications.

C++ makes architectural boundaries, data structures, error handling, ownership of components, and computational complexity more explicit.

None of these implementations should be interpreted as complete production HTTP servers. They model API architecture and behavior without requiring an external web framework.

---

## Implementation considerations

A production REST API generally requires components beyond the educational implementations.

A complete system may include:

- HTTP server
- TLS configuration
- Reverse proxy
- API gateway
- Authentication provider
- Authorization layer
- Database
- Database migrations
- Connection pool
- Cache
- Background workers
- Message broker
- Structured logging
- Metrics
- Distributed tracing
- Secrets management
- Configuration management
- Deployment automation
- Health checks
- Backup and recovery

The architectural concepts remain useful regardless of the specific framework or infrastructure.

---

## Real-world relevance

The resource-oriented model is applicable to many domains.

### E-commerce

Resources:

- Products
- Customers
- Orders
- Payments
- Shipments
- Reviews

Example:

`GET /api/v1/products/101`

### Banking

Resources:

- Accounts
- Transactions
- Beneficiaries
- Statements

Security, authorization, auditing, and idempotency become particularly important.

### Healthcare

Resources can include:

- Patients
- Appointments
- Providers
- Clinical records

Sensitive data requires strong authentication, authorization, encryption, auditing, and privacy controls.

### Education

Resources can include:

- Students
- Courses
- Enrollments
- Assignments
- Results

### Logistics

Resources can include:

- Shipments
- Warehouses
- Vehicles
- Tracking events

### SaaS applications

Resources can include:

- Organizations
- Users
- Projects
- Subscriptions
- Invoices
- Usage records

Across these domains, the same fundamental API vocabulary can be applied:

resource → URI → HTTP method → request → validation → authorization → business operation → representation → status code

---

## Practical architectural distinctions

### Resource versus endpoint

A resource is the conceptual entity.

An endpoint is the interface through which a client interacts with a resource.

### URI versus HTTP method

The URI identifies the target.

The HTTP method communicates the intended interaction semantics.

### Representation versus resource

A resource is the conceptual entity.

A representation is a transferable form of that entity.

### Authentication versus authorization

Authentication establishes identity.

Authorization determines permissions.

### Safe versus idempotent

Safe concerns whether the method is intended to change resource state.

Idempotent concerns the effect of repeating the operation.

### Statelessness versus persistence

Stateless request processing does not prevent persistent databases.

The server can retain resource data while processing every request using the information supplied by that request.

### PUT versus PATCH

PUT represents replacement.

PATCH represents partial modification.

### Filtering versus pagination

Filtering reduces the logical set of matching resources.

Pagination limits the amount of that set returned in a particular response.

### Caching versus persistence

Caching improves retrieval performance and reduces repeated work.

Persistence stores authoritative application data.

A cache is not automatically a replacement for the primary data store.

---

## Production design considerations

A production API should establish a clear contract covering:

- Resource names
- URI structure
- HTTP methods
- Status codes
- Request schemas
- Response schemas
- Error schemas
- Authentication
- Authorization
- Pagination
- Filtering
- Sorting
- Versioning
- Rate limits
- Caching
- Idempotency
- Concurrency
- Observability
- Deprecation behavior

Consistency is important.

If one endpoint uses `page` and `limit` while another uses unrelated pagination semantics without a clear reason, client integration becomes more difficult.

The same principle applies to:

- Naming conventions
- Error structures
- Status-code usage
- Date formats
- Identifier formats
- Authentication requirements
- Pagination behavior

An API is a contract. Changes to that contract should therefore be treated as compatibility-sensitive changes.

---

## Key implementation patterns demonstrated

The Python implementation demonstrates:

- REST terminology
- Resource modeling
- HTTP methods
- Requests and responses
- Status codes
- Validation
- Repository separation
- Collection filtering
- Pagination
- PUT and PATCH semantics
- Stateless authentication
- Idempotency keys
- Caching concepts
- Content negotiation
- Versioning
- Authorization
- Rate limiting
- Routing
- Security validation
- Observability
- Hypermedia
- Testing
- Performance analysis

The JavaScript implementation demonstrates:

- Resource classes
- JSON serialization
- Repository and controller separation
- URL parsing
- Query parameters
- Pagination
- Routing
- Validation
- Stateless authentication
- Authorization
- Idempotency keys
- ETags
- Asynchronous programming
- Fetch-style request processing
- Retry and backoff behavior
- Rate limiting
- Observability
- Performance measurement
- API testing

The C++ implementation demonstrates:

- Resource-oriented architecture
- HTTP method modeling
- Request and response structures
- Input validation
- Repository design
- JSON representation
- Routing
- Authentication
- Authorization
- Rate limiting
- API gateway structure
- Error handling
- Pagination
- Resource lifecycle
- Edge-case handling
- Complexity considerations
- Industry-style layering

---

## Conceptual request lifecycle

A complete request can be understood as a sequence:

1. The client identifies the API resource.
2. The client selects an HTTP method.
3. The client constructs the request.
4. The request travels through network infrastructure.
5. TLS protects the connection where HTTPS is used.
6. A gateway or load balancer may receive the request.
7. Authentication identifies the caller.
8. Authorization checks permissions.
9. Rate limiting evaluates traffic policy.
10. Input validation checks the request.
11. Routing selects the endpoint.
12. Application logic processes the resource.
13. A database or downstream service may be contacted.
14. The API constructs a representation.
15. The API selects an HTTP status code.
16. Response headers communicate metadata.
17. The response is returned to the client.
18. Logging, metrics, and tracing record the operation.

This lifecycle explains why a REST endpoint is more than a function that returns JSON. It is part of a larger protocol and architecture involving resource identity, HTTP semantics, security, state management, reliability, caching, performance, and operational visibility.
