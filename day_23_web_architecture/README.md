# Web Architecture, Client-Server Architecture, and the Browser Request-Response Lifecycle

## Introduction

Web architecture describes how browsers, servers, networks, application software, databases, caches, and other services cooperate to deliver a web application.

The most important conceptual boundary is the client-server relationship. A browser normally acts as the client. It requests resources or asks an application to perform an operation. A server receives the request, determines what should happen, performs application processing, and returns an HTTP response.

A simple web interaction can therefore be represented as:

`Browser → Network → Server → Application → Data/Services → Server → Browser`

Modern systems can be considerably more complicated. A browser request may pass through DNS, a CDN, a reverse proxy, a load balancer, an authentication system, several application services, caches, databases, message queues, and external APIs. The fundamental request-response model still provides the basis for understanding the complete system.

The three implementations in this study approach the subject differently:

- The Python program builds individual web concepts and includes a real local HTTP server.
- The JavaScript program emphasizes application-level web behavior, asynchronous execution, Fetch concepts, event-loop behavior, and a Node.js HTTP server.
- The C++ program develops a more structured industry-style application server case study involving routing, authentication, authorization, sessions, caching, rate limiting, concurrency, and performance.

---

## Fundamental concepts

### Client

A client is software that initiates communication with a server.

For ordinary websites, the browser is the primary client. Other clients can include:

- Mobile applications
- Desktop applications
- Command-line HTTP clients
- Automated services
- Monitoring systems
- Other backend services

The client is responsible for creating a request and processing the response according to the application's requirements.

### Server

A server is a program or collection of programs that receives requests and provides services or resources.

A server may:

- Serve HTML
- Serve CSS and JavaScript
- Return images
- Expose an API
- Authenticate users
- Validate input
- Execute business rules
- Query databases
- Access caches
- Call external services
- Create background jobs
- Return errors

The term "server" can refer to software, a physical or virtual machine, or a logical role in an architecture. These meanings should not be confused.

### Client-server architecture

Client-server architecture separates responsibilities between a requester and a service provider.

A browser generally does not directly access a server's database. Instead, the browser sends a request to an application endpoint. The server decides what information can be returned and what operations can be performed.

For example:

`Browser → GET /api/products/42`

The server may:

1. Parse the request.
2. Authenticate the user if required.
3. Check authorization.
4. Validate the requested product identifier.
5. Query a database or cache.
6. Apply business rules.
7. Serialize the result.
8. Return an HTTP response.

This separation provides an important security boundary. Client-side code cannot be trusted simply because it is part of the application's interface.

---

## Web architecture

A modern web architecture can contain several layers.

### Browser

The browser handles:

- URL processing
- HTTP communication
- HTML parsing
- CSS processing
- JavaScript execution
- DOM manipulation
- rendering
- browser security policies
- cookies
- caching
- storage
- user interaction

A browser is therefore much more than an HTTP client.

### DNS

DNS, or Domain Name System, translates names such as `example.com` into network addresses.

Conceptually:

`example.com → IP address`

DNS resolution may be avoided on a particular request when an appropriate result is already cached.

### Transport

HTTP communication requires a transport mechanism.

Traditional HTTP/1.1 commonly operates over TCP. HTTPS adds TLS to protect the communication channel.

The conceptual sequence for HTTPS over TCP is:

`DNS → TCP connection → TLS negotiation → HTTP communication`

Modern HTTP versions can also use different underlying transport technologies, so this sequence should be understood as a common model rather than a universal rule for every modern HTTP deployment.

### TLS

TLS provides cryptographic protection for HTTPS.

Important properties include:

- Confidentiality
- Integrity
- Server authentication through certificates

HTTPS protects the communication channel, but it does not automatically make the application secure. An application can still contain authentication, authorization, injection, validation, or logic vulnerabilities while using HTTPS.

### Web server and reverse proxy

A web server or reverse proxy can receive incoming traffic before it reaches application code.

Typical responsibilities include:

- TLS termination
- Static file serving
- Request forwarding
- Compression
- Routing
- Connection management
- Access logging
- Rate limiting
- Security headers
- Load balancing

Examples of architectures include:

`Browser → Reverse Proxy → Application`

or:

`Browser → CDN → Load Balancer → Application Servers`

### Application server

The application layer implements business behavior.

For an e-commerce system, this might include:

- Product lookup
- Inventory management
- Authentication
- Orders
- Payments
- Customer accounts

For a financial application, it might include:

- Portfolio calculation
- Order validation
- Risk rules
- Account permissions
- Transaction processing

---

## URL anatomy

A URL can contain several components.

Consider:

`https://example.com:443/products?id=42#details`

The components are:

- `https` is the scheme.
- `example.com` is the hostname.
- `443` is the explicit port.
- `/products` is the path.
- `id=42` is a query parameter.
- `#details` is a fragment.

The Python, JavaScript, and C++ implementations demonstrate URL parsing at different levels.

The fragment deserves special attention. It is normally interpreted by the browser and is not included in the HTTP request target sent to the server.

---

## HTTP

HTTP is the primary application-layer protocol used by the Web.

An HTTP request conceptually contains:

- Method
- Request target
- Headers
- Optional body

An HTTP response conceptually contains:

- Status code
- Reason phrase or status description
- Headers
- Optional body

For example, a request can conceptually look like:

`GET /products/42 HTTP/1.1`

with headers such as:

`Host: example.com`

`Accept: application/json`

The response may contain:

`HTTP/1.1 200 OK`

and:

`Content-Type: application/json`

followed by a representation of the requested resource.

---

## HTTP methods

### GET

GET is normally used to retrieve a representation.

A properly designed GET operation should not intentionally create a business-side state change simply because it was requested.

Example:

`GET /api/products/42`

### POST

POST submits data for processing.

It can be used to:

- Create a resource
- Submit a form
- Trigger an operation
- Start a server-side process

Example:

`POST /api/orders`

### PUT

PUT is commonly used to create or replace a representation at a known target URI.

### PATCH

PATCH represents partial modification.

For example, an application might update only a user's display name instead of replacing the entire user object.

### DELETE

DELETE requests removal of a resource.

### HEAD

HEAD is similar to GET in its semantics but normally does not return the representation body.

It can be useful when a client needs metadata such as content length or cache-related information.

### OPTIONS

OPTIONS allows a client to discover communication options supported by a resource or server.

It is also important in browser CORS behavior.

---

## HTTP status codes

HTTP status codes are grouped into five broad classes.

### 1xx

Informational responses.

### 2xx

Successful processing.

Common examples:

- `200 OK`
- `201 Created`
- `204 No Content`

### 3xx

Redirection or cache-related signaling.

Common examples:

- `301 Moved Permanently`
- `302 Found`
- `304 Not Modified`

### 4xx

The request cannot be successfully processed because of a client-side or request-related condition.

Examples:

- `400 Bad Request`
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`
- `409 Conflict`
- `422 Unprocessable Content`
- `429 Too Many Requests`

`401` and `403` have different meanings. A `401` response is associated with missing or invalid authentication credentials. A `403` indicates that the server understood the request but refuses the operation for authorization reasons.

### 5xx

The server encountered a condition preventing successful processing.

Examples:

- `500 Internal Server Error`
- `502 Bad Gateway`
- `503 Service Unavailable`
- `504 Gateway Timeout`

A `502` often indicates a gateway or proxy received an invalid response from an upstream server, while `504` indicates that an upstream operation did not complete within the applicable timeout.

---

## Headers

HTTP headers carry metadata about a request or response.

Common request headers include:

- `Host`
- `Accept`
- `Content-Type`
- `Authorization`
- `Cookie`
- `User-Agent`
- `If-None-Match`

Common response headers include:

- `Content-Type`
- `Content-Length`
- `Cache-Control`
- `Set-Cookie`
- `ETag`
- `Location`
- `Access-Control-Allow-Origin`

Headers are part of the protocol rather than application data itself.

---

## Request body

A request body carries data submitted by the client.

For example, an application may send JSON:

`{"name":"Atul","email":"atul@example.com"}`

The `Content-Type` header tells the server how the body should be interpreted.

For JSON:

`Content-Type: application/json`

A server should not blindly trust the body. Parsing and validation are separate operations.

Parsing answers:

"Can I interpret these bytes as JSON?"

Validation answers:

"Does this JSON contain acceptable data for this operation?"

---

## Query parameters

Query parameters are commonly used to modify or describe a request.

Example:

`/search?q=browser&page=2`

The path identifies the resource or endpoint, while query parameters can specify filtering, sorting, pagination, search terms, or other request options.

Applications should validate query values before using them.

---

## Routing

Routing maps a request to application logic.

Conceptually:

`GET /products/42`

can be mapped to:

`getProduct(42)`

The Python implementation uses a small router. The JavaScript implementation creates a simple route table. The C++ implementation develops explicit application routing for a product API.

Real frameworks provide substantially more sophisticated routing mechanisms, including:

- Path parameters
- Route groups
- Middleware
- HTTP method matching
- Content negotiation
- Authentication hooks
- Versioned APIs

---

## The request-response lifecycle

A browser interaction can involve many steps.

### Step 1: User interaction

The user enters a URL, selects a link, submits a form, or JavaScript starts a network operation.

### Step 2: URL parsing

The browser identifies:

- Scheme
- Host
- Port
- Path
- Query
- Fragment

### Step 3: Cache evaluation

The browser can determine whether an existing cached representation can be used.

### Step 4: DNS

If necessary, the browser or operating system resolves the hostname.

### Step 5: Connection establishment

The client establishes or reuses a network connection.

### Step 6: TLS

For HTTPS, cryptographic negotiation takes place if an appropriate secure connection is not already available.

### Step 7: HTTP request construction

The browser creates the request method, target, headers, and optional body.

### Step 8: Network transmission

The request travels through the network.

Infrastructure can include:

- Routers
- Firewalls
- Proxies
- CDNs
- Load balancers

### Step 9: Server acceptance

A server or reverse proxy accepts the connection and parses the HTTP message.

### Step 10: Routing

The request is mapped to application logic.

### Step 11: Authentication

The server may determine who the requester is.

### Step 12: Authorization

The server determines whether the authenticated identity is permitted to perform the operation.

### Step 13: Validation

Input is checked for correct structure, type, size, and business constraints.

### Step 14: Application processing

Business logic executes.

### Step 15: Data access

The application may access:

- Database
- Cache
- File system
- Object storage
- Message queue
- External API

### Step 16: Response generation

The server produces:

- Status code
- Headers
- Response body

### Step 17: Network transmission

The response travels back to the browser.

### Step 18: Browser processing

The browser interprets the response according to its content type and context.

### Step 19: Additional resource requests

HTML may cause additional requests for:

- CSS
- JavaScript
- Images
- Fonts
- Video
- Other resources

### Step 20: Rendering

The browser parses content and performs layout, painting, and compositing.

The user sees the resulting interface.

---

## Python implementation

The Python implementation is organized as a progression from protocol concepts to an actual local HTTP server.

### HTTP message classes

`HTTPRequest` models:

- Method
- Target
- Headers
- Body

`HTTPResponse` models:

- Status
- Reason
- Headers
- Body

These classes make the abstract structure of HTTP explicit.

### URL parsing

`parse_url()` uses Python's standard `urllib.parse` facilities.

The demonstration separates the URL into:

- Scheme
- Hostname
- Port
- Path
- Query
- Fragment

This illustrates that a URL is structured data rather than simply a string.

### Routing

`MiniApplication` contains a list of routes.

A route consists of:

- HTTP method
- Path
- Handler

The request is matched against these attributes.

The example intentionally returns `404 Not Found` when no matching route exists.

### Query parameters

The search demonstration uses `urllib.parse.parse_qs()`.

The code distinguishes between:

- Missing parameter
- Empty parameter
- Valid parameter

This distinction is important because applications should not assume that a parameter is present merely because a route was reached.

### JSON validation

The user creation demonstration performs several levels of validation:

1. Content type check
2. JSON parsing
3. Object-type check
4. Required field validation
5. Basic email validation
6. Normalization

It returns different status codes for different failures.

### Sessions

`SessionStore` demonstrates server-side session state.

The browser may receive a cookie containing a session identifier. The actual user state can remain on the server.

The demonstration also shows security-related cookie attributes:

`HttpOnly`

`Secure`

`SameSite=Lax`

These attributes do not solve every session-security problem, but they provide important browser controls.

### Password processing

The example uses `pbkdf2_hmac()` to demonstrate password-derived storage.

The important concept is that an ordinary password should not be stored directly.

The example also explicitly distinguishes password-specific hashing from ordinary general-purpose hashing. Production systems should use a dedicated password hashing approach with appropriate configuration.

### Caching

`SimpleCache` stores responses for a limited period.

Caching can reduce:

- Network traffic
- CPU usage
- Database load
- Response latency

Caching also introduces problems such as:

- Stale data
- Cache invalidation
- Incorrect sharing of private data
- Memory consumption

The correct cache policy depends on the resource.

### ETags

The Python implementation creates an ETag from content.

A browser can later send:

`If-None-Match`

If the representation has not changed, the server can return:

`304 Not Modified`

without sending the representation body again.

### Middleware

Middleware demonstrates a common application architecture.

A request can pass through several layers:

`Logging → Security Headers → Application`

Middleware is useful for concerns that apply across many endpoints.

Common middleware responsibilities include:

- Authentication
- Logging
- Request IDs
- Compression
- CORS
- Security headers
- Metrics
- Error handling

### CORS

Cross-Origin Resource Sharing is a browser security mechanism controlling cross-origin access to responses.

An origin is determined by:

- Scheme
- Host
- Port

For example, different subdomains represent different origins.

CORS should not be confused with authentication. A CORS policy does not prove that a user is authorized to access a resource.

### Real HTTP server

The Python implementation uses `http.server.ThreadingHTTPServer`.

It demonstrates an actual local request-response boundary.

A request is sent through `http.client.HTTPConnection`, reaches the server, is routed by the handler, and produces a response.

The server also demonstrates:

- GET
- POST
- JSON
- Request-size validation
- Status codes
- Response headers
- Error responses

This is intentionally educational. A production web application would normally use a production-grade server architecture and framework appropriate to its requirements.

---

## JavaScript implementation

The JavaScript implementation emphasizes behavior particularly relevant to web applications and Node.js.

### URL API

The standard `URL` class provides structured access to URL components.

`URLSearchParams` makes query parameter handling explicit.

This is particularly useful in browser and server-side JavaScript.

### Routing

The JavaScript `Router` class provides a simple mapping between:

`method + path`

and a handler function.

Real application frameworks extend this concept with path parameters, middleware, content negotiation, and more advanced matching.

### JSON

JavaScript has native JSON support through:

- `JSON.parse()`
- `JSON.stringify()`

The implementation demonstrates that parsing can fail and that valid JSON can still contain semantically invalid application data.

### Sessions

`SessionStore` uses a JavaScript `Map` to associate random session identifiers with user information.

A production system would normally need:

- Expiration
- Revocation
- Secure persistence or distributed storage
- Session rotation
- Appropriate cookie configuration
- Protection against session fixation and theft

### Middleware

The JavaScript middleware examples use higher-order functions.

A middleware function receives a handler and returns another handler.

This is an important JavaScript pattern because functions can be passed around as values.

### Asynchronous processing

The implementation uses:

- Promises
- `async`
- `await`
- `setTimeout()`

The simulated database operation returns a Promise.

The application can begin an asynchronous operation without blocking the JavaScript execution flow while waiting for the timer or I/O operation.

### Event loop

JavaScript uses an event-driven execution model.

The example demonstrates the interaction between:

- Synchronous code
- Promise microtasks
- Timer callbacks

Understanding this behavior is important when building server-side JavaScript applications because a handler may initiate network or database operations and resume when those operations complete.

### Fetch

The file describes the browser Fetch API because Fetch is a fundamental browser mechanism for making HTTP requests.

A common conceptual sequence is:

`fetch() → Promise<Response> → response.json()`

The Node.js study program deliberately does not pretend that browser APIs and server APIs are identical. DOM APIs, browser rendering, browser security enforcement, and Node.js server APIs belong to different execution environments.

### Node.js HTTP server

The JavaScript implementation creates a real local HTTP server using Node's built-in `http` module.

It demonstrates:

- Request parsing
- URL parsing
- GET handling
- POST handling
- JSON processing
- Status codes
- Response headers
- Request-size protection
- Error handling

---

## C++ case study

The C++ implementation develops a miniature e-commerce API server model.

The case study represents a request such as:

`GET /api/products/1`

and processes it through several architectural layers.

### Problem being modeled

The system provides product information and a stock-reservation operation.

The server must:

1. Receive an HTTP-style request.
2. Apply rate limiting.
3. Route the request.
4. Parse resource identifiers.
5. Retrieve product data.
6. Use caching when appropriate.
7. Authenticate protected operations.
8. Authorize the requested operation.
9. Validate input.
10. Apply business logic.
11. Produce an HTTP-style response.

This is substantially closer to an industry application architecture than a collection of isolated language demonstrations.

### Product repository

`ProductRepository` owns the product data.

The repository provides:

- `findById()`
- `reserve()`

The application service does not need to know how product data is physically stored.

In a production application, the repository could be backed by a database rather than an in-memory container.

### Product service

`ProductService` represents application-level business behavior.

It delegates persistence-oriented operations to the repository.

Separating these responsibilities reduces coupling between business logic and storage implementation.

### Session store

`SessionStore` maps session identifiers to users.

A mutex protects the shared map because multiple threads can access it.

The example generates random session identifiers rather than predictable sequential identifiers.

### Response cache

`ResponseCache` stores HTTP responses with an expiration time.

The product endpoint first checks the cache.

A cache hit can avoid repeated application processing.

The response includes:

`X-Cache: HIT`

to make the demonstration observable.

The implementation also demonstrates an ETag-like value based on product state.

### Rate limiter

`RateLimiter` limits requests per client within a time window.

Rate limiting can protect applications against:

- Accidental request floods
- Resource exhaustion
- Some forms of automated abuse

A real production limiter may use distributed state rather than an in-process map when many application instances exist.

### Authentication

The case study accepts a demonstration bearer token.

Authentication answers:

"Who is making the request?"

The example maps the demonstration credential to a user.

Real authentication systems require stronger credential handling, token lifecycle management, secure storage, expiration, revocation where appropriate, and careful transport security.

### Authorization

Authorization answers:

"Is this identity allowed to perform this operation?"

The code explicitly separates authentication from authorization.

This distinction is fundamental.

A user can be authenticated while still being forbidden from performing a particular action.

### Product routing

The application recognizes routes such as:

`/api/health`

`/api/products/1`

`/api/products/reserve`

The product ID is extracted from the URL path.

Invalid values produce a `400 Bad Request` response.

Unknown products produce `404 Not Found`.

This demonstrates that routing errors and resource-not-found conditions are different application states.

### Stock reservation

The stock reservation endpoint accepts a simple educational body:

`product_id,quantity`

The application validates:

- Product ID
- Quantity
- Authentication
- Authorization
- Stock availability

If the quantity exceeds available inventory, the application returns a conflict response.

A real application would also need transactional database behavior to prevent race conditions when multiple clients attempt to reserve the same inventory simultaneously.

---

## Architectural layers in the C++ case study

The complete case study can be viewed as:

`Client`

↓

`HTTP request`

↓

`Rate limiter`

↓

`Router`

↓

`Authentication`

↓

`Authorization`

↓

`Application service`

↓

`Repository`

↓

`Cache / persistent data`

↓

`HTTP response`

This separation demonstrates an important principle: a request is not equivalent to a single function call in a mature application. It may pass through multiple policies and components.

---

## Cookies and sessions

Cookies are pieces of state that browsers can store and send with subsequent requests according to browser rules.

A session architecture commonly looks like:

`Browser cookie → Session ID → Server-side session state`

The cookie might contain:

`session_id=abc123`

while the server stores:

`abc123 → user 42`

A session cookie should normally use appropriate security attributes.

### HttpOnly

`HttpOnly` prevents ordinary JavaScript from reading the cookie through the standard cookie API.

It helps reduce some consequences of client-side script compromise.

### Secure

`Secure` tells the browser to send the cookie only over secure connections under the applicable cookie rules.

### SameSite

`SameSite` controls aspects of cross-site cookie sending.

Its correct configuration depends on the application's authentication and cross-site requirements.

---

## Authentication versus authorization

These terms should remain separate.

### Authentication

Authentication establishes an identity.

Examples include:

- Password login
- Passkeys
- Client certificates
- OAuth-based identity flows
- Access tokens

### Authorization

Authorization determines permitted actions.

For example:

A user can be authenticated as account `42` but still be forbidden from accessing an administrative endpoint.

A useful conceptual sequence is:

`Authentication → Identity → Authorization → Permission decision`

---

## Caching

Caching stores reusable information closer to the requester or processing layer.

Possible caches include:

- Browser cache
- Reverse proxy cache
- CDN cache
- Application cache
- Database cache

Caching can improve latency and reduce backend load.

Caching also creates consistency questions.

If a product changes from:

`stock = 20`

to:

`stock = 5`

a cached response showing `20` may become stale.

Therefore cache design must consider:

- TTL
- Validation
- Invalidation
- Privacy
- Resource mutability
- Cache key construction

---

## ETags and conditional requests

An ETag identifies a particular representation version.

A response might contain:

`ETag: "abc123"`

A later request can contain:

`If-None-Match: "abc123"`

If the server determines that the representation has not changed, it can return:

`304 Not Modified`

This allows the client to reuse its cached representation.

ETags are validators. They are not the same thing as cache storage itself.

---

## Middleware

Middleware provides reusable processing around application handlers.

A conceptual pipeline is:

`Request → Logging → Authentication → Validation → Handler → Response`

Each layer can perform a specific cross-cutting responsibility.

Examples:

- Logging
- Metrics
- Authentication
- Authorization
- CORS
- Compression
- Security headers
- Request IDs
- Error handling

Middleware must be designed carefully because ordering can change behavior.

For example, authentication middleware must run before an endpoint that requires an authenticated identity.

---

## Browser security model

Browsers enforce security rules that do not necessarily apply to arbitrary backend programs.

Important browser security mechanisms include:

- Same-origin policy
- CORS
- Cookie restrictions
- Mixed-content restrictions
- Content security mechanisms
- Permission policies
- Sandboxing mechanisms

This explains why a browser JavaScript program may receive a security-related error when a backend program making a similar HTTP request does not.

The server should still implement authentication and authorization independently of browser controls.

---

## Same-origin policy and CORS

An origin is defined by:

`scheme + host + port`

For example:

`https://app.example.com`

and:

`https://api.example.com`

have different origins because the hosts differ.

CORS allows a server to explicitly communicate which origins may access responses through browser cross-origin mechanisms.

CORS is not:

- Authentication
- Authorization
- Encryption
- A general API security system

A server should never treat a permissive or restrictive CORS configuration as a substitute for access control.

---

## Browser rendering

After receiving HTML, the browser does considerably more than display text.

The browser processes:

- HTML
- CSS
- JavaScript
- Images
- Fonts
- Other resources

It constructs internal representations and performs stages such as:

- Parsing
- Style calculation
- Layout
- Painting
- Compositing

JavaScript can modify document state after the initial response.

This is why the browser should be considered an application runtime rather than simply an HTTP terminal.

---

## Server-side rendering and client-side rendering

### Server-side rendering

The server generates HTML that is sent to the browser.

Conceptually:

`Request → Server → HTML → Browser`

Advantages can include:

- HTML generated close to the data
- Useful initial document content
- Reduced requirement for client-side rendering for some applications

### Client-side rendering

The browser receives application JavaScript and may construct or update the interface dynamically.

Conceptually:

`Request → Browser → JavaScript application → API requests → UI`

Advantages can include highly interactive client-side interfaces.

The two approaches can also be combined.

The appropriate approach depends on application requirements, performance goals, accessibility requirements, data behavior, and development architecture.

---

## Asynchronous web programming

Network operations are inherently variable in duration.

A request may wait for:

- DNS
- Network transmission
- Server processing
- Database queries
- External services

JavaScript uses Promises and `async`/`await` to express asynchronous operations.

Python applications can use threads, asynchronous programming, processes, or framework-specific execution models.

C++ applications can use threads, asynchronous APIs, event loops, or other concurrency models.

The fundamental objective is to prevent slow independent work from unnecessarily blocking unrelated work.

---

## Concurrency

A web server may handle many requests around the same time.

Potential approaches include:

- Multiple processes
- Multiple threads
- Event loops
- Asynchronous I/O
- Worker pools
- Distributed application instances

Concurrency creates shared-state concerns.

The C++ implementation demonstrates mutex-protected shared structures for:

- Sessions
- Cache
- Rate limiter

Without appropriate synchronization, concurrent access can cause data races and undefined behavior.

---

## Performance considerations

Web performance depends on multiple stages.

Important contributors include:

- DNS latency
- Connection establishment
- TLS negotiation
- Network distance
- Request size
- Response size
- Server computation
- Database queries
- Cache behavior
- External API latency
- Browser parsing
- JavaScript execution
- Rendering

Improving one stage does not automatically solve all performance problems.

### Common strategies

Useful architectural strategies can include:

- Appropriate caching
- Database indexing
- Efficient queries
- Response compression
- CDN distribution
- Connection reuse
- Pagination
- Batching
- Asynchronous processing
- Background jobs
- Horizontal scaling

Optimization should be based on measurements rather than assumptions.

---

## Complexity considerations

The C++ implementation compares vector membership with unordered-set membership.

A linear search through a vector has approximately:

`O(n)`

membership complexity for arbitrary values.

An `unordered_set` has approximately:

`O(1)`

average membership complexity.

These are not equivalent data structures.

A hash-based structure can require more memory and has hashing and collision behavior. A vector can provide better locality and lower overhead for some workloads.

The appropriate structure depends on the workload rather than complexity notation alone.

---

## Security considerations

Web applications process untrusted data.

Important security practices include:

### Input validation

Validate:

- Types
- Lengths
- Formats
- Ranges
- Allowed values

Validation should occur on the server even when client-side validation exists.

### Authentication

Credentials and authentication tokens should be protected.

### Authorization

Every protected operation should be checked against server-side permissions.

Do not rely on hiding a button in a browser interface as authorization.

### Injection prevention

Database queries should use parameterized interfaces rather than concatenating untrusted input into SQL.

Similar principles apply to:

- Shell commands
- HTML
- JavaScript
- File paths
- Template languages

### Cross-site scripting

Applications should correctly encode or sanitize content according to the output context.

### Cross-site request forgery

State-changing operations using browser credentials may require CSRF protections depending on the authentication design.

### Session security

Sensitive session cookies should use appropriate cookie security attributes.

Sessions should also have sensible expiration and invalidation behavior.

### Request limits

Servers should limit:

- Request body size
- Upload size
- Processing time
- Expensive operations
- Request frequency

### Error disclosure

Detailed internal errors are useful during development but should not normally be exposed to arbitrary users in production.

---

## Common mistakes

### Treating the browser as trusted

The browser is controlled by the user.

Client-side validation improves user experience but does not replace server-side validation.

### Confusing authentication with authorization

Knowing who the user is does not automatically mean that the user is allowed to perform every operation.

### Treating HTTP status codes as interchangeable

`400`, `401`, `403`, `404`, `409`, and `422` communicate different conditions.

### Sending sensitive data over HTTP

Sensitive traffic should use HTTPS.

### Storing plaintext passwords

Passwords should not be stored as ordinary readable strings.

### Creating unrestricted CORS policies

CORS should reflect actual application requirements.

### Ignoring cache privacy

Private user-specific responses should not accidentally become shared cache entries.

### Trusting URL parameters

A value such as `/users/42` does not prove that the requester is permitted to access user 42.

### Forgetting request-size limits

Large or intentionally malformed requests can consume server resources.

### Ignoring concurrency

Shared in-memory state can become unsafe when several requests execute simultaneously.

### Assuming low latency

A request can be delayed by any dependency in the chain.

### Treating a local development server as a production architecture

A small local server is useful for learning, but production systems require appropriate deployment, security, observability, scaling, failure handling, and operational controls.

---

## Error handling

Good web applications distinguish different failure categories.

### Client or input errors

Examples:

- Invalid JSON
- Missing parameter
- Invalid identifier
- Unsupported content type

These can produce `4xx` responses.

### Authentication errors

An absent or invalid authentication credential may produce `401`.

### Authorization errors

An authenticated identity without sufficient permission may receive `403`.

### Resource errors

A requested object that does not exist commonly results in `404`.

### Conflict errors

Business-state conflicts can result in `409`.

For example, an inventory reservation may fail because another transaction consumed the available stock.

### Server failures

Unexpected application failures can produce `500`.

Infrastructure failures can produce other `5xx` responses such as `502`, `503`, or `504`.

---

## Production architecture

A larger application may look conceptually like:

`Browser`

↓

`DNS`

↓

`CDN`

↓

`Load Balancer / Reverse Proxy`

↓

`Application Servers`

↓

`Cache`

↓

`Database`

and may also connect to:

`Message Queue → Background Workers`

`Object Storage`

`External APIs`

`Monitoring / Logging / Tracing`

The browser does not need to know how these internal components are arranged. It generally communicates through stable HTTP interfaces.

---

## Monoliths and distributed services

A monolithic application places much of the application logic into one primary deployable system.

Advantages can include:

- Simpler deployment
- Easier local development
- Straightforward function calls between components

A distributed service architecture divides responsibilities among separate services.

Advantages can include:

- Independent deployment
- Independent scaling
- Stronger ownership boundaries

Costs can include:

- Network failures
- Distributed tracing requirements
- Service discovery
- More complex deployment
- Data consistency challenges
- More operational components

Neither architecture is universally appropriate. The correct design depends on system requirements.

---

## Reverse proxies and load balancers

A reverse proxy receives requests on behalf of application servers.

It can perform:

- TLS termination
- Routing
- Static file serving
- Compression
- Access control
- Request limits
- Load balancing

A load balancer distributes requests among multiple application instances.

For example:

`Client → Load Balancer → Application A`

or:

`Client → Load Balancer → Application B`

This allows applications to scale horizontally.

---

## Database interaction

A typical request can involve:

`HTTP request → Application → Database query → Application → HTTP response`

Database performance can dominate total request latency.

Important considerations include:

- Indexes
- Query complexity
- Transactions
- Connection pooling
- Lock contention
- Data modeling
- Pagination
- Caching

The application should not expose database credentials or direct database access to untrusted clients.

---

## External services

Applications frequently depend on external services.

For example:

`Application → Payment API`

or:

`Application → Email service`

or:

`Application → Identity provider`

External dependencies introduce additional failure modes:

- Timeouts
- Rate limits
- Invalid responses
- Network failures
- Service outages
- Version changes

Production applications should establish appropriate timeouts, retries where safe, failure handling, and observability.

Retries require care because repeating a state-changing operation can create duplicate effects unless the operation is designed to be safely repeatable.

---

## Idempotency

An operation is idempotent when repeating it produces the same intended final effect.

HTTP method semantics include distinctions related to idempotency.

This concept is especially important for distributed systems.

For example, a payment request should not accidentally charge a customer twice simply because a network timeout caused the client to retry.

Applications can use an idempotency key to associate repeated requests with one logical operation.

---

## Observability

A production web application should provide mechanisms for understanding what happened during requests.

Important observability categories include:

### Logs

Record significant events.

### Metrics

Measure quantities such as:

- Request count
- Error count
- Latency
- CPU utilization
- Memory usage

### Traces

Follow a request across multiple components.

For a distributed application:

`Browser request → Proxy → Service A → Service B → Database`

tracing can help identify which component consumed time.

---

## Practical distinction between browser and server JavaScript

JavaScript can run in both browsers and servers, but the environments are different.

Browser JavaScript can access APIs such as:

- DOM
- `window`
- `document`
- Fetch
- Browser storage

Node.js can access server-side facilities such as:

- TCP and HTTP servers
- File system
- Process information
- Operating-system interfaces

The JavaScript implementation deliberately uses Node.js for the server examples and describes browser Fetch separately.

This distinction prevents a common beginner mistake: assuming that all JavaScript APIs are available in every JavaScript runtime.

---

## Python, JavaScript, and C++ comparison

| Aspect | Python | JavaScript | C++ |
|---|---|---|---|
| Primary demonstration | Web concepts and local HTTP server | Asynchronous web behavior and Node.js | Industry-style application architecture |
| HTTP server | Standard library | Node.js `http` module | Architectural simulation |
| URL processing | `urllib.parse` | `URL` | Custom parsing |
| JSON | `json` | `JSON.parse` and `JSON.stringify` | Modeled application responses |
| Concurrency | Threads | Event loop and asynchronous operations | Threads and mutexes |
| Middleware | Function composition | Higher-order functions | Layered application design |
| Caching | In-memory cache | In-memory cache | Thread-safe response cache |
| Authentication | Password/session concepts | Session model | Bearer-token case study |
| Rate limiting | Discussed | Discussed | Implemented |
| Business case study | Product handler | Product service | Complete product API architecture |
| Systems-level detail | Moderate | Moderate | High |

The languages therefore complement one another rather than merely implementing identical examples.

---

## Edge cases demonstrated

The implementations intentionally handle cases such as:

- Missing query parameters
- Empty query parameters
- Invalid JSON
- JSON arrays where objects are required
- Missing required fields
- Invalid product identifiers
- Missing products
- Unsupported content types
- Invalid authorization
- Excessive quantities
- Insufficient inventory
- Cache expiration
- Conditional requests
- Unknown routes
- Request body size limits
- Rate limiting
- Concurrent access to shared state

These cases demonstrate that web programming is not simply the successful path from request to response.

---

## Implementation considerations

### Separation of concerns

The C++ case study separates:

- Repository
- Service
- Session store
- Cache
- Rate limiter
- Authentication
- Authorization
- Router
- Application

This makes individual responsibilities easier to reason about.

### Validation near trust boundaries

The request boundary is a natural place to validate input.

The application should not assume that data received from a browser is safe merely because the browser normally produces it.

### Thread safety

Shared mutable state requires synchronization when multiple threads can access it concurrently.

The C++ example uses mutexes for this purpose.

### Cache consistency

A cache should not be treated as an automatically correct copy of the primary data.

The application must define appropriate freshness behavior.

### Resource limits

Request size and rate limits help prevent uncontrolled resource consumption.

### Error boundaries

Internal implementation details should be separated from external error messages.

---

## Running the implementations

### Python

Save the Python code as `web_architecture.py` and run:

`python web_architecture.py`

The program uses the Python standard library.

The local server demonstration starts a temporary server on the loopback interface and shuts it down automatically.

### JavaScript

Save the JavaScript code as `web_architecture.js` and run:

`node web_architecture.js`

The implementation uses Node.js built-in modules and does not require external npm packages.

### C++

Save the C++ program as `web_architecture.cpp`.

Compile it with a modern compiler supporting C++17:

`g++ -std=c++17 -O2 -pthread web_architecture.cpp -o web_architecture`

Then run the resulting executable.

The C++ program is an architectural case study rather than a full HTTP protocol implementation. Its purpose is to demonstrate how the internal processing layers of a server can be structured.

---

## Key relationships

Several concepts should be understood together.

### Browser and HTTP

The browser uses HTTP to communicate with web servers, but browser behavior includes many responsibilities beyond HTTP.

### HTTP and application logic

HTTP provides the communication structure. Application code gives the request business meaning.

### Routing and resources

Routing determines which application operation corresponds to a request target.

### Authentication and authorization

Authentication establishes identity. Authorization determines permissions.

### Caching and performance

Caching can reduce repeated work but introduces freshness and invalidation concerns.

### Concurrency and shared state

Concurrent requests improve throughput but require careful management of shared mutable state.

### HTTPS and application security

HTTPS protects the communication channel. Application security still requires validation, authentication, authorization, safe data handling, and appropriate error controls.

### Browser rendering and server responses

The server can return HTML, JSON, CSS, JavaScript, images, or other representations. The browser interprets those representations according to their types and context and may initiate additional requests.

---

## Real-world relevance

The concepts demonstrated here appear in systems such as:

- E-commerce platforms
- Banking applications
- Trading platforms
- Social networks
- Enterprise portals
- Learning management systems
- SaaS applications
- Mobile application backends
- Public APIs
- Government services
- Healthcare applications
- Content platforms
- Cloud applications

A small request such as:

`GET /api/products/42`

can represent a complete chain involving networking, security, routing, business logic, data access, caching, serialization, and browser processing.

Understanding that chain provides the foundation for understanding larger technologies such as web frameworks, REST APIs, reverse proxies, CDNs, load balancers, databases, distributed systems, and cloud architectures.
