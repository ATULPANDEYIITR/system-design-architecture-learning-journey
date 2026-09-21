# HTTP: Requests, Responses, Methods, and Status Codes

## Introduction

HTTP, or Hypertext Transfer Protocol, is an application-layer protocol used for communication between clients and servers. It provides the semantics that allow a client to request a resource or operation and a server to return a response describing the result.

A typical exchange contains two messages:

1. An HTTP request from the client to the server.
2. An HTTP response from the server to the client.

A request can contain a method, target, headers, and an optional body. A response contains a status code, headers, and an optional body.

For example, a client may request `/api/users/42` using `GET`. The server can return status `200 OK` with a JSON representation of user 42.

HTTP is not limited to browsers. Web applications, mobile applications, command-line tools, Python programs, JavaScript programs, C++ applications, reverse proxies, API gateways, and distributed services can all communicate using HTTP.

## Fundamental HTTP model

The basic communication model is:

Client → Request → Server

Client ← Response ← Server

The client does not normally send an instruction such as "run this Python function." Instead, it communicates through standardized HTTP semantics.

A request contains four important conceptual components:

- Method
- Target
- Headers
- Optional body

A response contains:

- Status code
- Headers
- Optional body

The method communicates the intended operation. The target identifies the resource or endpoint. Headers provide metadata and control information. The body carries representation data when appropriate.

## HTTP methods

The Python and JavaScript implementations explicitly demonstrate common HTTP methods.

### GET

`GET` requests a representation of a resource.

Examples:

`GET /api/users`

`GET /api/users/42`

A GET request normally does not require a body.

GET is considered safe and idempotent under HTTP semantics.

### POST

`POST` submits data to a target resource and commonly causes server-side processing.

A common API pattern is:

`POST /api/users`

The body can contain:

`{"name":"Ada","email":"ada@example.com"}`

The server may create a new user and return `201 Created`.

POST is not inherently idempotent. Sending the same POST twice may create two resources.

### PUT

`PUT` is used for creation or complete replacement at a known target URI.

Example:

`PUT /api/users/42`

The request can contain the complete representation of user 42.

PUT is idempotent in its intended semantics. Repeating the same replacement should produce the same intended server state.

### PATCH

`PATCH` performs a partial modification.

Example:

`PATCH /api/users/42`

The body might contain only:

`{"name":"Ada Lovelace"}`

Unlike PUT, PATCH does not inherently mean that the complete resource representation is being supplied.

Whether a particular PATCH operation is idempotent depends on the operation being performed.

### DELETE

`DELETE` requests removal of a resource.

Example:

`DELETE /api/users/42`

The C++ and JavaScript implementations return `204 No Content` after successful deletion.

DELETE is defined as idempotent even though repeating the request can produce a different response. The important distinction is that repeating the operation does not keep producing additional deletions after the resource is already absent.

### HEAD

`HEAD` has semantics similar to GET but normally does not return the response body.

It is useful when a client needs metadata such as headers without downloading the representation.

### OPTIONS

`OPTIONS` allows a client to discover communication options supported by a target.

The examples return an `Allow` header describing supported methods.

### TRACE and CONNECT

TRACE is a diagnostic loop-back method and is commonly disabled because of security considerations.

CONNECT is used to establish a tunnel, commonly through an HTTP proxy. It is important to distinguish this from ordinary REST API operations.

## Safe and idempotent methods

Two important HTTP concepts are safety and idempotency.

A safe method is intended to have read-only semantics from the perspective of the requested resource.

An idempotent method is one where repeating the same request has the same intended effect on server state.

The common classification is:

| Method | Safe | Idempotent |
|---|---|---|
| GET | Yes | Yes |
| HEAD | Yes | Yes |
| OPTIONS | Yes | Yes |
| PUT | No | Yes |
| DELETE | No | Yes |
| POST | No | No |
| PATCH | No | Depends on operation |

Idempotency does not mean that every response will be byte-for-byte identical.

For example, a repeated GET may return a different timestamp while still being idempotent with respect to the intended resource state.

## HTTP status codes

HTTP status codes communicate the result of processing a request.

The first digit identifies the broad category.

| Class | Meaning |
|---|---|
| 1xx | Informational |
| 2xx | Successful |
| 3xx | Redirection |
| 4xx | Client error |
| 5xx | Server error |

### 2xx successful responses

`200 OK` means the request was successfully processed.

`201 Created` indicates that a new resource was created. A creation response can also include a `Location` header identifying the created resource.

`202 Accepted` means the request has been accepted for processing but processing may not have completed.

`204 No Content` indicates successful processing with no response body.

`206 Partial Content` is used for partial representations, such as range-based retrieval.

### 3xx redirection

`301 Moved Permanently` indicates a permanent redirect.

`302 Found` is commonly used for temporary redirection.

`304 Not Modified` is particularly important for conditional caching. It tells a client that its cached representation can still be used.

`307 Temporary Redirect` and `308 Permanent Redirect` preserve the request method during redirection, unlike historical redirect behavior associated with some older status codes.

### 4xx client errors

`400 Bad Request` indicates that the server cannot process the request because it is malformed or otherwise invalid at the request level.

`401 Unauthorized` is commonly used when authentication is required or authentication credentials are invalid. The name can be confusing because the actual problem is generally authentication rather than authorization.

`403 Forbidden` commonly indicates that the server understood the request but refuses to authorize the requested operation.

`404 Not Found` means that the requested resource was not found.

`405 Method Not Allowed` indicates that the method is not supported for the target resource.

`409 Conflict` commonly represents a conflict between the request and the current state of the resource.

`413 Content Too Large` indicates that the request content exceeds a server-defined limit.

`415 Unsupported Media Type` indicates that the representation format is not supported.

`422 Unprocessable Content` is commonly used when the request is syntactically acceptable but its content fails application-level validation.

`429 Too Many Requests` commonly represents rate limiting.

### 5xx server errors

`500 Internal Server Error` represents a server-side failure.

`502 Bad Gateway` is commonly generated by a gateway or reverse proxy when an upstream service returns an invalid response or otherwise fails in an expected way.

`503 Service Unavailable` indicates temporary inability to handle the request and is commonly used during overload or maintenance.

`504 Gateway Timeout` indicates that a gateway did not receive an appropriate response from an upstream service within its timeout period.

## Python implementation

The Python script uses only the standard library.

The `HttpRequest` class models an HTTP request with:

- `method`
- `target`
- `headers`
- `body`

The `HttpResponse` class models:

- `status_code`
- `reason`
- `headers`
- `body`

The `header()` method demonstrates case-insensitive HTTP header lookup.

The script uses `urllib.parse` to examine URL components and query parameters.

It demonstrates:

- URL schemes
- hostnames
- ports
- paths
- query strings
- fragments
- URL encoding
- JSON serialization
- content types

## Python HTTP server

The Python implementation contains a working local HTTP server based on `http.server`.

The `LearningRequestHandler` implements:

- GET
- POST
- PUT
- PATCH
- DELETE
- HEAD
- OPTIONS

The server provides routes such as:

`GET /api/users`

`GET /api/users/42`

`POST /api/users`

`PUT /api/users/42`

`PATCH /api/users/42`

`DELETE /api/users/42`

The implementation validates `Content-Type`, request body size, JSON syntax, user names, and email values.

The server demonstrates the difference between a malformed request and an application-level validation failure.

For example, malformed JSON produces a `400` response, while syntactically valid JSON containing an invalid email can produce `422`.

## Python HTTP client

The Python script uses `urllib.request.Request` and `urllib.request.urlopen` to make real HTTP requests to the local server.

The client demonstrates:

- setting HTTP methods
- setting request headers
- serializing JSON
- reading response headers
- reading response bodies
- handling `HTTPError`
- handling `URLError`
- setting timeouts

The `SimpleApiClient` wraps these operations into a reusable interface.

This illustrates an important distinction:

An HTTP response such as `404` is not the same type of failure as a network timeout.

A server can successfully receive and process an HTTP request and intentionally return `404`. A timeout may mean that no HTTP response was received at all.

## JavaScript implementation

The JavaScript implementation uses Node.js built-in modules.

It demonstrates two different client styles.

The first is based on Node's lower-level `http.request()` API. This exposes details such as:

- request options
- HTTP method
- headers
- request body
- response events
- timeouts
- network errors

The second uses the modern asynchronous `fetch()` API.

### Asynchronous behavior

`fetch()` returns a Promise.

The JavaScript program uses `async` and `await` to make asynchronous HTTP code easier to read.

An important detail is that `fetch()` does not normally reject merely because the server returned a `4xx` or `5xx` response.

Application code must inspect:

`response.status`

or:

`response.ok`

This distinction is important when writing robust JavaScript HTTP clients.

## JavaScript local server

The Node.js implementation creates a real local HTTP server using the built-in `http` module.

The server routes requests based on:

- HTTP method
- URL pathname
- query parameters
- resource identifier

It maintains users in a `Map`.

The implementation demonstrates:

- GET collection retrieval
- GET individual resource retrieval
- POST resource creation
- PUT replacement
- PATCH partial modification
- DELETE
- HEAD
- OPTIONS
- 404 handling
- 415 handling
- 422 validation
- 204 responses

The server also limits request body size to prevent an uncontrolled request from consuming excessive memory.

## URL handling

The Python implementation uses `urllib.parse`.

The JavaScript implementation uses the `URL` and `URLSearchParams` classes.

A URL can contain several components:

`https://example.com:8443/products/42?category=books&page=2#details`

Its conceptual components are:

- scheme: `https`
- host: `example.com`
- port: `8443`
- path: `/products/42`
- query: `category=books&page=2`
- fragment: `#details`

Query parameters and path parameters serve different purposes.

A path such as `/users/42` commonly identifies a specific resource.

A query string such as `/users?page=2&limit=20` commonly modifies retrieval behavior.

Fragments are normally handled by the user agent and are not sent to the server as part of the HTTP request target.

## Content-Type and Accept

`Content-Type` describes the media type of the representation contained in the request or response.

For a JSON request:

`Content-Type: application/json`

`Accept` expresses the response media types the client is prepared to receive.

For example:

`Accept: application/json`

These headers should not be treated as interchangeable.

A request can contain JSON while asking the server for a JSON response.

## JSON

JSON is widely used by HTTP APIs because it provides a language-independent representation format.

The Python implementation uses `json.dumps()` and `json.loads()`.

The JavaScript implementation uses `JSON.stringify()` and `JSON.parse()`.

The C++ implementation intentionally uses a small educational parser for selected string fields rather than an external JSON library.

This is an important engineering distinction. A production C++ application should use a mature JSON implementation when it needs complete JSON support rather than relying on the simplified parser used for this case study.

## C++ case study

The C++ program models a small user-management API.

The system stores users with:

- ID
- name
- email

The API supports:

`GET /api/users`

`GET /api/users/{id}`

`POST /api/users`

`PUT /api/users/{id}`

`PATCH /api/users/{id}`

`DELETE /api/users/{id}`

`OPTIONS /api/users`

The implementation uses standard C++17 facilities.

## C++ architecture

The major components are:

### `StatusCode`

The `StatusCode` enumeration represents important HTTP status codes.

Using an enum makes status values explicit rather than scattering numeric literals throughout the application.

### `HttpMethod`

The `HttpMethod` enumeration represents supported methods.

The `parseMethod()` function converts textual method names into the enumeration.

### `HttpRequest`

`HttpRequest` contains:

- method
- target
- headers
- body

The `getHeader()` function performs case-insensitive header lookup.

### `HttpResponse`

`HttpResponse` contains:

- status
- headers
- body

Its `print()` method produces a human-readable representation of the response.

### `User`

`User` is the domain model.

The `UserApi` class owns the user data and handles application-level HTTP semantics.

### `RateLimiter`

The `RateLimiter` class demonstrates a simple fixed-window request limit.

### `SecurityContext`

The security model separates authentication from authorization.

This demonstrates an important application-security principle: knowing who a caller is and determining what that caller may do are different decisions.

## C++ routing

The `UserApi::handle()` function processes requests based on method and target.

The implementation first applies general request constraints, such as maximum body size.

It then handles collection routes, creation, individual resources, replacement, partial modification, deletion, HEAD, and OPTIONS.

This resembles the responsibility of an application-level request handler behind a real HTTP server.

The program does not implement a complete HTTP network stack.

A production architecture would normally use a dedicated HTTP server or framework to handle:

- TCP connections
- TLS
- HTTP parsing
- HTTP/1.1 framing
- HTTP/2 framing
- HTTP/3 and QUIC
- connection management
- streaming
- protocol errors

The application layer would then receive structured requests and produce structured responses.

## PUT versus PATCH in the case study

The C++ example demonstrates the difference between replacement and partial modification.

A PUT request supplies the complete representation:

`{"name":"Ada Updated","email":"ada.updated@example.com"}`

A PATCH request can supply only the field being changed:

`{"name":"Ada Lovelace"}`

The distinction matters because clients and servers must agree on the semantics of an operation.

A partial update should not accidentally erase fields that were not supplied.

## Request validation

HTTP requests contain untrusted input.

The examples validate:

- request body size
- Content-Type
- required fields
- empty names
- email structure
- resource identifiers
- supported routes
- supported methods

Validation should occur before dangerous or expensive processing.

A production API should also validate:

- authorization
- content encoding
- pagination limits
- numeric ranges
- string lengths
- allowed fields
- nested object structures
- business constraints

## Error handling

HTTP error handling has multiple layers.

A request can fail before an HTTP response exists.

Examples include:

- DNS failure
- connection refusal
- TLS failure
- timeout
- local resource exhaustion

A request can also successfully reach a server and receive an HTTP error response.

Examples include:

- 400
- 401
- 403
- 404
- 409
- 422
- 429
- 500
- 503

These cases should not be treated as identical.

A client that cannot establish a connection cannot interpret a server-generated `404` because no HTTP response was received.

## Retries

The Python, JavaScript, and C++ implementations discuss retry behavior.

Common retry candidates include:

- 408
- 429
- 500
- 502
- 503
- 504

The exact retry policy depends on the application.

A retry mechanism should consider:

- method semantics
- idempotency
- attempt count
- timeout type
- server response
- `Retry-After`
- exponential backoff
- jitter
- application state

A simple retry loop can make an outage worse by generating more traffic against an already overloaded service.

This is sometimes called a retry storm.

## Idempotency keys

POST is not inherently idempotent.

Consider a payment or order creation endpoint:

`POST /orders`

If the client sends the request, the server processes it, but the response is lost because of a network failure, the client may not know whether the order was created.

Blindly sending the POST again could create a duplicate order.

A common application-level solution is an idempotency key.

The client sends a unique logical-operation identifier. The server records the result associated with that identifier and can return the same logical result when the client retries.

Idempotency keys are an application design mechanism. They are not the same thing as the HTTP definition of an idempotent method.

## Caching

HTTP caching can reduce:

- latency
- bandwidth
- server processing
- database load

The examples demonstrate `Cache-Control`, `ETag`, and `If-None-Match`.

A server can provide:

`Cache-Control: public, max-age=60`

and:

`ETag: "resource-version"`

A client can later send:

`If-None-Match: "resource-version"`

If the representation has not changed, the server can return:

`304 Not Modified`

The client can then reuse its cached representation.

Caching must be configured carefully for private, personalized, authenticated, and security-sensitive data.

## ETags and concurrency

ETags can also participate in optimistic concurrency control.

A client can retrieve a representation and receive an ETag.

Later, it can send a conditional modification using `If-Match`.

The server can reject the modification if the resource changed since the client retrieved it.

This prevents one client from silently overwriting another client's changes.

The relevant status code is commonly `412 Precondition Failed`.

## Authentication and authorization

Authentication and authorization are different.

Authentication asks:

"Who is the caller?"

Authorization asks:

"Is this caller allowed to perform this operation?"

The C++ case study models these decisions using `SecurityContext`.

An unauthenticated caller can receive `401 Unauthorized`.

An authenticated caller without the required permission can receive `403 Forbidden`.

A caller with the required permission can proceed.

HTTP status codes communicate these decisions but do not implement authentication or authorization themselves.

## HTTPS and TLS

HTTPS is HTTP transported through TLS.

TLS provides:

- encryption
- integrity protection
- server authentication

Sensitive applications should not send credentials or tokens over unencrypted HTTP.

Application security also requires protection against problems such as:

- cross-site request forgery
- cross-site scripting
- insecure CORS policies
- request smuggling
- header injection
- cache poisoning
- excessive request sizes
- excessive request rates
- information leakage through error messages

Security must be considered at the transport, HTTP, application, identity, and data layers.

## Headers

Headers provide metadata and control information.

Important request headers include:

`Host`

Identifies the target host in HTTP/1.1-style requests.

`Accept`

Communicates acceptable response representations.

`Content-Type`

Describes the representation in the request or response body.

`Authorization`

Carries authentication credentials or access tokens according to the authentication scheme.

`If-None-Match`

Supports conditional retrieval using an ETag.

`If-Match`

Supports conditional modification and optimistic concurrency.

Important response headers include:

`Content-Type`

Describes the response representation.

`Content-Length`

Indicates the body length where applicable.

`Location`

Can identify a newly created resource or redirect target.

`Cache-Control`

Controls caching behavior.

`ETag`

Provides a representation validator.

`Allow`

Describes methods supported by a resource, particularly in OPTIONS responses.

`Retry-After`

Can tell clients how long to wait before trying again.

`WWW-Authenticate`

Communicates an authentication challenge in relevant 401 responses.

## Status code selection

Status codes should communicate meaningful protocol-level outcomes.

For example:

A malformed request can produce `400`.

Missing authentication can produce `401`.

Insufficient permission can produce `403`.

A missing resource can produce `404`.

A method unsupported by the resource can produce `405`.

A state conflict can produce `409`.

Invalid application-level content can produce `422`.

A rate limit can produce `429`.

An unexpected server failure can produce `500`.

Choosing status codes consistently makes APIs easier for clients, monitoring systems, proxies, and developers to understand.

## Redirects

Redirects use 3xx status codes.

Some redirect codes can alter historical request behavior in clients, while `307` and `308` explicitly preserve the method and request body semantics during the redirect.

API clients should not assume every redirect is equivalent to every other redirect.

Redirect behavior can be especially important for POST, PUT, and other methods with request bodies.

## Performance considerations

HTTP performance depends on more than server computation.

Potential contributors to latency include:

- DNS resolution
- connection establishment
- TLS negotiation
- request transmission
- server processing
- database queries
- upstream service calls
- response serialization
- response transmission

The Python, JavaScript, and C++ examples model these concerns conceptually.

Common performance mechanisms include:

- persistent connections
- connection pooling
- HTTP/2 multiplexing
- HTTP/3
- compression
- caching
- pagination
- smaller representations
- efficient serialization
- sensible timeouts

A client should avoid both infinite timeouts and excessively aggressive timeouts.

## HTTP/1.0, HTTP/1.1, HTTP/2, and HTTP/3

The core semantics of HTTP remain recognizable across versions.

### HTTP/1.0

HTTP/1.0 provided an early standardized model for HTTP communication.

### HTTP/1.1

HTTP/1.1 introduced and standardized important capabilities including persistent connections and richer request/response behavior.

### HTTP/2

HTTP/2 uses binary framing and supports multiplexing multiple streams over a connection.

The application still uses concepts such as methods, URLs, headers, and status codes.

### HTTP/3

HTTP/3 carries HTTP semantics over QUIC, which uses UDP as its underlying transport.

HTTP/3 changes transport and framing behavior rather than replacing concepts such as GET, POST, status codes, headers, and resource representations.

## Query parameters

Query parameters are commonly used for:

- filtering
- sorting
- searching
- pagination
- feature selection

Examples:

`/users?role=admin`

`/products?category=books&sort=price`

`/orders?page=2&limit=50`

Query parameters are untrusted input and must be validated.

Applications should impose reasonable limits on pagination and filtering to prevent unexpectedly expensive operations.

## Path parameters

Path parameters commonly identify resources.

Examples:

`/users/42`

`/orders/1001/items/7`

A server should validate identifiers rather than assuming that every path segment contains a valid integer or expected identifier.

The Python, JavaScript, and C++ implementations explicitly validate user IDs.

## HTTP and REST

HTTP is a protocol.

REST is an architectural style.

They should not be treated as synonyms.

An HTTP API can use GET, POST, PUT, PATCH, DELETE, status codes, headers, and JSON without necessarily satisfying every constraint associated with REST.

The examples use resource-oriented API patterns because these provide a practical way to demonstrate HTTP methods and response semantics.

## Edge cases

Important edge cases include:

- empty bodies
- malformed JSON
- missing Content-Type
- unsupported Content-Type
- oversized bodies
- invalid URL encoding
- invalid identifiers
- missing resources
- unsupported methods
- duplicate requests
- stale caches
- expired authentication
- insufficient authorization
- rate-limit exhaustion
- upstream timeouts
- connection failures
- partial network failures

Production systems should treat every external request as potentially malformed or hostile.

## Common mistakes

### Treating all errors as HTTP errors

A DNS failure or timeout may occur before an HTTP response exists.

### Treating 401 and 403 as identical

401 generally concerns authentication, while 403 commonly concerns authorization.

### Retrying every request

Blind retries can duplicate side effects and increase system load.

### Assuming POST is idempotent

POST is not inherently idempotent.

### Using PUT for every update

PUT generally represents replacement semantics, while PATCH is intended for partial modification.

### Ignoring status codes

An HTTP client should inspect the response status rather than assuming that receiving an HTTP response means the operation succeeded.

### Treating `fetch()` rejection as the only error mechanism

JavaScript Fetch-based clients must inspect `response.ok` or `response.status` because HTTP 4xx and 5xx responses normally still resolve the fetch Promise.

### Trusting Content-Type without validation

A server should validate the media type before interpreting the body.

### Accepting unlimited request bodies

Large untrusted bodies can consume excessive memory or processing resources.

### Exposing sensitive errors

Internal stack traces, database details, tokens, and infrastructure information should not be returned to untrusted clients.

### Putting secrets in URLs

URLs can appear in logs, browser history, monitoring systems, analytics systems, and other infrastructure. Sensitive credentials should normally use appropriate authentication mechanisms instead.

## Limitations of the implementations

The implementations are educational models rather than complete production HTTP stacks.

The Python and JavaScript servers use standard runtime HTTP facilities and therefore rely on those runtimes for low-level protocol processing.

The C++ implementation intentionally models the application layer rather than implementing a complete HTTP server.

The C++ program does not implement:

- TCP
- TLS
- complete HTTP/1.1 parsing
- chunked transfer encoding
- HTTP/2 framing
- HTTP/3
- QUIC
- streaming bodies
- complete JSON syntax
- persistent storage
- distributed transactions

The C++ JSON parsing logic is deliberately small and should not be used as a substitute for a complete JSON parser in production.

## Performance considerations in the C++ case study

The C++ user store uses `unordered_map<int, User>`.

Expected average complexity is:

| Operation | Expected complexity |
|---|---|
| Lookup by ID | O(1) |
| Insert by ID | O(1) |
| Delete by ID | O(1) |
| List all users | O(n) |

These are expected average-case properties of a hash table and not absolute guarantees.

A production database-backed API introduces additional costs, including:

- network communication with the database
- query execution
- indexes
- locking
- transaction processing
- serialization
- connection pooling

## Production architecture

A larger HTTP service commonly separates responsibilities into layers:

Client

→ Network/TLS

→ HTTP server

→ Request parsing

→ Routing

→ Authentication

→ Authorization

→ Validation

→ Application/service logic

→ Database or external services

→ Response construction

→ HTTP server

→ Client

This separation makes individual responsibilities easier to test and maintain.

Reverse proxies and API gateways can also provide:

- TLS termination
- load balancing
- rate limiting
- request filtering
- caching
- observability
- routing
- service discovery

## Observability

Production HTTP services should record appropriate operational information.

Useful measurements include:

- request count
- status-code distribution
- latency
- request size
- response size
- timeout count
- retry count
- upstream failures
- rate-limit events
- cache hit/miss behavior

Logging should avoid exposing secrets, access tokens, passwords, or unnecessary personal data.

A useful metric such as the rate of `5xx` responses can indicate server-side reliability problems.

A useful metric such as the rate of `429` responses can indicate rate limiting or unusually high traffic.

## Python, JavaScript, and C++ comparison

| Aspect | Python | JavaScript | C++ |
|---|---|---|---|
| HTTP server example | Yes | Yes | Application-layer case study |
| HTTP client | `urllib` | `http.request` and `fetch` | Modeled application |
| JSON support | Standard library | Native JSON APIs | Educational parser |
| Async model | Threaded local server | Promise and async/await | Synchronous case study |
| URL handling | `urllib.parse` | `URL`, `URLSearchParams` | Custom parser |
| Validation | Functions and classes | Functions and server routes | Classes and service layer |
| Status handling | Explicit mapping | Explicit mapping | Enum |
| Retry discussion | Yes | Yes | Yes |
| Caching | Conceptual | ETag demonstration | ETag implementation |
| Security | Conceptual | Conceptual | Authentication/authorization model |
| Performance | Conceptual | Conceptual | Complexity analysis |

Python is useful for demonstrating HTTP concepts with concise standard-library code.

JavaScript is useful for showing asynchronous application behavior and the Fetch programming model, as well as server-side HTTP handling through Node.js.

C++ is useful for illustrating explicit data structures, typed models, service-layer design, resource management, and algorithmic complexity.

## Practical API lifecycle

A typical request lifecycle can be understood as:

1. The client constructs a URL.
2. The client chooses an HTTP method.
3. The client adds appropriate headers.
4. The client serializes an optional body.
5. The request is transmitted.
6. The server parses and validates it.
7. Authentication is checked.
8. Authorization is checked.
9. Routing selects the appropriate operation.
10. Application logic executes.
11. The server constructs a status code and response.
12. Response headers are added.
13. The response body is serialized.
14. The response is transmitted.
15. The client interprets the status code, headers, and representation.

Understanding this sequence provides the foundation for working with web APIs, microservices, reverse proxies, web applications, mobile backends, and distributed systems.

## Important distinctions

### Request versus response

A request is sent by the client to the server.

A response is sent by the server to the client.

### Method versus status code

The method describes the intended operation.

The status code describes the result of processing.

### Content-Type versus Accept

Content-Type describes the representation being sent.

Accept describes representations the client can receive.

### Authentication versus authorization

Authentication identifies the caller.

Authorization determines permitted actions.

### Network failure versus HTTP failure

A network failure may prevent an HTTP response from existing.

An HTTP failure means an HTTP response was successfully received with an error status.

### PUT versus PATCH

PUT represents replacement semantics.

PATCH represents partial modification.

### Safe versus idempotent

Safe means the operation is intended to be read-only.

Idempotent means repeating the same request has the same intended effect on server state.

These concepts overlap for some methods but are not synonyms.

## Real-world relevance

HTTP is foundational to modern application infrastructure.

It is used by:

- web browsers
- mobile applications
- public APIs
- internal microservices
- payment systems
- authentication services
- cloud services
- software update systems
- monitoring systems
- API gateways
- reverse proxies
- content delivery systems

A strong understanding of requests, responses, methods, headers, status codes, caching, authentication, retries, and failure behavior is therefore useful across application development and distributed-system engineering.

The three implementations collectively demonstrate HTTP from three complementary perspectives: Python provides a concise educational client/server environment, JavaScript demonstrates asynchronous and event-driven HTTP behavior, and C++ models the structure of a more explicitly designed application service with typed data structures, validation, rate limiting, security decisions, caching concepts, and complexity analysis.
