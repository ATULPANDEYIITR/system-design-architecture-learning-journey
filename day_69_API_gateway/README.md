# API Gateway: Routing, Authentication and Rate Limiting

## 1. Project Description

This project implements an API Gateway model across Python, JavaScript, C++17, Java 17 and PostgreSQL.

An API Gateway is an entry point through which client applications access backend services. It receives requests, evaluates gateway policies, identifies the destination service and forwards authorized requests.

The implementations focus on three primary responsibilities:

- **Routing:** Mapping incoming HTTP requests to appropriate backend services.
- **Authentication:** Establishing the identity of an API consumer.
- **Rate limiting:** Controlling request frequency to protect backend resources.

Additional mechanisms include scope-based authorization, upstream service management, request auditing, failure handling and circuit breakers.

## 2. API Gateway Architecture

The implemented architecture separates client-facing request processing from backend service execution.

### Request processing flow

    Client Application
           |
           v
       API Gateway
           |
           v
     Request Validation
           |
           v
      Route Resolution
           |
           v
      Authentication
           |
           v
      Authorization
           |
           v
      Rate Limiting
           |
           v
      Upstream Dispatch
           |
           v
      Backend Service
           |
           v
      Gateway Response
           |
           v
       Audit Logging

Each stage performs a distinct responsibility. A request rejected during authentication or rate limiting does not proceed to backend execution.

## 3. Routing

Routing determines which backend service receives an incoming request.

A route is generally defined by:

- HTTP method
- Request path
- Destination service
- Required authorization scope
- Route priority
- Rate-limit policy

### 3.1 HTTP method routing

The implementations support:

| Method | Typical purpose |
|---|---|
| GET | Retrieve information |
| POST | Create resources |
| PUT | Replace resources |
| PATCH | Partially update resources |
| DELETE | Remove resources |

The gateway matches both the HTTP method and the request path. A valid path with an unsupported method does not automatically identify a valid route.

### 3.2 Static and parameterized routes

A static route identifies a fixed endpoint.

Example: `/api/v1/orders`

A parameterized route accepts variable path segments.

Example: `/api/v1/users/{userId}`

For an incoming request to `/api/v1/users/101`, the router extracts:

| Parameter | Value |
|---|---|
| userId | 101 |

The extracted parameters are passed to the upstream service.

The implementations prioritize more specific routes when multiple route patterns could match.

### 3.3 Route registration

A route must have a valid method, path, destination service and authorization requirement.

Duplicate route definitions are rejected.

Route configuration also includes rate-limit settings. Keeping routing configuration separate from request processing makes it easier to manage large API collections.

### 3.4 Upstream service dispatch

The upstream service registry maps service identifiers to backend handlers.

The example services are:

| Service | Responsibility |
|---|---|
| User Service | Retrieve user information |
| Order Service | Create orders |

The gateway forwards the original request and extracted path parameters to the selected handler.

A missing upstream service produces a gateway failure rather than silently accepting the request.

## 4. Authentication

Authentication verifies the identity of the requesting application.

The examples use bearer-token authentication.

A client sends an HTTP authorization header containing a bearer token.

The gateway extracts the token and checks whether it belongs to an active registered client.

### 4.1 Credential validation

A valid credential must satisfy the following conditions:

- The authorization header exists.
- The authentication scheme is Bearer.
- The token is present.
- The token is registered.
- The client is enabled.
- The credential has not expired or been revoked where credential lifecycle management is implemented.

The PostgreSQL implementation stores SHA-256-style hexadecimal token hashes rather than plaintext credentials. In a production system, credential verification must use a suitable cryptographic implementation and secure secret-management practices.

### 4.2 Authentication outcomes

| Condition | HTTP status |
|---|---:|
| Missing token | 401 |
| Invalid token | 401 |
| Disabled client | 401 |
| Revoked credential | 401 |
| Expired credential | 401 |
| Valid identity | Authentication succeeds |

Authentication establishes who is making the request. It does not independently determine which operations that identity may perform.

## 5. Authorization and Scopes

Authorization determines whether an authenticated client can access a particular operation.

The implementations use scope-based access control.

A scope represents a specific permission.

Examples:

| Scope | Permission |
|---|---|
| `users:read` | Retrieve user records |
| `users:delete` | Delete user records |
| `orders:create` | Create orders |
| `orders:read` | Retrieve order records |

Each route specifies a required scope.

The gateway compares the client's assigned scopes against the route requirement.

For example, a client with `users:read` cannot automatically access a DELETE endpoint requiring `users:delete`.

### Authentication versus authorization

| Authentication | Authorization |
|---|---|
| Identifies the client | Evaluates permissions |
| Validates credentials | Checks required scopes |
| Occurs before authorization | Follows authentication |
| Failure normally produces 401 | Failure normally produces 403 |

This separation prevents an authenticated identity from receiving unrestricted access to backend services.

## 6. Rate Limiting

Rate limiting controls the number of requests a client can make within a defined period.

It protects backend systems against excessive traffic, accidental request loops and abusive usage.

The implementations use the token-bucket algorithm.

### 6.1 Token-bucket mechanism

A token bucket maintains:

- Current token balance
- Maximum bucket capacity
- Token refill rate
- Last refill timestamp

Each accepted request consumes one token.

Tokens are replenished continuously according to the configured refill rate.

The balance cannot exceed the maximum capacity.

### 6.2 Example

Consider a route with:

| Parameter | Value |
|---|---:|
| Refill rate | 3 tokens per second |
| Burst capacity | 5 tokens |
| Request cost | 1 token |

Initially, the bucket contains five tokens.

Five immediate requests can be accepted. A sixth request is rejected until sufficient tokens have been replenished.

After one second, approximately three additional tokens become available, subject to the capacity limit.

### 6.3 Rate-limiting algorithms

| Algorithm | Mechanism | Main consideration |
|---|---|---|
| Fixed window | Counts requests in fixed time intervals | Boundary bursts |
| Sliding window | Evaluates requests over a moving interval | Higher tracking cost |
| Token bucket | Replenishes tokens continuously | Allows controlled bursts |
| Leaky bucket | Processes requests at a controlled output rate | Smooths traffic |

The token-bucket algorithm is selected because it supports both a sustained request rate and short bursts.

### 6.4 Rate-limit responses

When the token balance is insufficient, the gateway returns HTTP 429.

Relevant response headers include:

- `X-RateLimit-Remaining`
- `Retry-After`

Rate limits are configured separately for each client and route.

This prevents one client from consuming the entire allowance assigned to another client.

### 6.5 Per-client versus global limits

A per-client limit controls the traffic of an individual consumer.

A global limit controls aggregate traffic reaching a route or service.

Both may be required in a production environment.

The implementations primarily demonstrate per-client, per-route rate limiting.

## 7. Upstream Service Protection

A gateway must handle backend service failures without allowing repeated failures to consume unlimited resources.

The JavaScript and Java implementations include circuit-breaker models.

### 7.1 Circuit-breaker states

| State | Behavior |
|---|---|
| CLOSED | Requests are allowed |
| OPEN | Requests are rejected temporarily |
| HALF_OPEN | A limited recovery attempt is permitted |

When consecutive upstream failures reach the configured threshold, the circuit breaker opens.

After the reset interval, it permits a recovery attempt.

A successful request closes the circuit. Another failure reopens it.

### 7.2 Gateway failure responses

| Failure | HTTP status |
|---|---:|
| Invalid request | 400 |
| Authentication failure | 401 |
| Authorization failure | 403 |
| Unknown route | 404 |
| Unsupported method | 405 |
| Rate limit exceeded | 429 |
| Upstream failure | 502 |
| Upstream unavailable | 503 |
| Unexpected gateway error | 500 |

A gateway should distinguish client errors from upstream failures to support accurate monitoring and troubleshooting.

## 8. Implementation Design

The five implementations use different programming models to represent the same gateway responsibilities.

### 8.1 Python

The Python implementation uses dataclasses, enums, dictionaries, lists and classes.

Major components:

| Component | Responsibility |
|---|---|
| `Request` | Request representation and validation |
| `Response` | HTTP response representation |
| `APIClient` | Client identity and scopes |
| `Authenticator` | Token verification and authorization |
| `Router` | Route registration and matching |
| `TokenBucketRateLimiter` | Request-rate enforcement |
| `UpstreamServiceRegistry` | Backend dispatch |
| `AuditLogger` | Request history |
| `APIGateway` | Request orchestration |

The script uses Python's standard library and exports audit records to JSON.

It also tests authentication failures, authorization failures, invalid methods, route resolution, rate limiting and successful upstream operations.

### 8.2 JavaScript

The JavaScript implementation uses Node.js and event-driven asynchronous programming.

Its main components include:

- `ClientRegistry`
- `RouteRegistry`
- `TokenBucket`
- `RateLimiter`
- `CircuitBreaker`
- `UpstreamRegistry`
- `MiddlewarePipeline`
- `AuditLog`
- `APIGateway`

The middleware pipeline separates reusable request-processing stages from final route execution.

Asynchronous upstream handlers use promises, allowing the gateway to support I/O operations without blocking the event loop.

The circuit breaker provides a separate failure-control mechanism for each upstream service.

Audit information is exported as JSON.

### 8.3 C++17

The C++ implementation uses explicit domain types and polymorphism.

Its major components include:

- `Request` and `Response` structures
- `Client` and `Route` domain models
- `Authenticator`
- `Router`
- `TokenBucket`
- `RateLimiter`
- `UpstreamService`
- `UserService`
- `OrderService`
- `UpstreamRegistry`
- `AuditLogger`
- `APIGateway`

The upstream service interface allows multiple backend implementations to be registered without changing the routing engine.

`unique_ptr` manages service ownership, while STL containers store route definitions, clients and rate-limit states.

The router extracts path parameters and passes them to the selected service.

The program uses only standard C++17 facilities.

### 8.4 Java 17

The Java implementation models an enterprise-oriented gateway.

It uses:

- Records for immutable request and response models
- Enums for controlled state values
- Interfaces for upstream service contracts
- Concurrent collections for shared registries
- Synchronized token buckets
- Service classes for gateway responsibilities
- Custom exceptions for structured failure handling

The client registry, router, rate limiter and upstream registry are separate services.

The circuit breaker manages upstream failure states independently of client authentication and route authorization.

The audit service provides request-level reporting.

### 8.5 PostgreSQL

The PostgreSQL implementation models the gateway's persistent configuration and operational records.

Its schema includes:

| Table | Purpose |
|---|---|
| `api_clients` | Registered API consumers |
| `api_credentials` | Credential hashes and lifecycle |
| `api_scopes` | Authorization permissions |
| `client_scopes` | Client permission assignments |
| `upstream_services` | Backend service configuration |
| `api_routes` | HTTP route definitions |
| `rate_limit_policies` | Rate-limit configuration |
| `rate_limit_buckets` | Runtime token balances |
| `gateway_requests` | Request audit records |
| `rate_limit_events` | Rate-limit decisions |

Database integrity is enforced through primary keys, foreign keys, unique constraints, check constraints and triggers.

The token-consumption function uses row-level locking to serialize updates to a particular client-route bucket.

The database therefore provides a basis for coordinated rate-limit state management.

## 9. PostgreSQL Workflow

The SQL implementation demonstrates the following sequence.

    Register API Client
           |
           v
    Create Credential
           |
           v
    Assign Scopes
           |
           v
    Register Upstream Service
           |
           v
    Register API Route
           |
           v
    Configure Rate Limit
           |
           v
    Record Incoming Request
           |
           v
    Validate Client
           |
           v
    Evaluate Permissions
           |
           v
    Consume Rate-Limit Token
           |
           v
    Record Gateway Decision

The database includes functions for authentication, authorization, rate-limit consumption and request eligibility evaluation.

Reporting views provide route-level performance information and request statistics.

## 10. Important Design Distinctions

### 10.1 Routing versus authentication

Routing identifies the destination service.

Authentication verifies the requesting identity.

A valid route does not imply that the client has valid credentials.

### 10.2 Authentication versus authorization

Authentication establishes identity.

Authorization evaluates the permissions associated with that identity.

Both are required for protected operations.

### 10.3 Authorization versus rate limiting

Authorization determines whether an operation is permitted.

Rate limiting determines whether the client can execute another request within its traffic allowance.

A client can be authorized and still receive HTTP 429.

### 10.4 Rate limiting versus circuit breaking

Rate limiting controls incoming traffic.

Circuit breaking controls calls to an unhealthy upstream service.

They protect different parts of the gateway architecture.

### 10.5 Gateway versus reverse proxy

A reverse proxy forwards requests between clients and backend services.

An API Gateway generally adds API-specific capabilities such as authentication, authorization, rate limiting, routing policies and request auditing.

An API Gateway can be implemented using reverse-proxy functionality.

## 11. Validation and Edge Cases

The implementations address important failure conditions.

| Scenario | Expected behavior |
|---|---|
| Missing authentication token | Reject with 401 |
| Unknown token | Reject with 401 |
| Disabled client | Reject with 401 |
| Missing permission | Reject with 403 |
| Unknown route | Return 404 |
| Invalid HTTP method | Reject with 400 |
| Duplicate route | Reject during registration |
| Invalid rate policy | Reject configuration |
| Exhausted token bucket | Return 429 |
| Missing upstream | Return gateway error |
| Invalid order amount | Reject order |
| Upstream circuit open | Reject forwarding |
| Invalid request path | Reject request |
| Revoked database credential | Reject authentication |

Production implementations should also validate request content types, maximum payload sizes, query parameters, header sizes and upstream response formats.

## 12. Security Considerations

An API Gateway is a security boundary, but it should not be the only security control in a distributed application.

Important controls include:

- Use HTTPS and modern TLS configurations.
- Store secrets in a secure credential-management system.
- Never log bearer tokens or API secrets.
- Store credential hashes rather than plaintext credentials.
- Enforce expiration and revocation.
- Apply least-privilege scopes.
- Validate request paths and payloads.
- Prevent path traversal and request smuggling.
- Restrict permitted upstream destinations.
- Apply connection and response timeouts.
- Limit request body sizes.
- Sanitize audit information.
- Protect administrative route configuration.
- Use network segmentation between gateway and backend services.

The demonstration tokens are test credentials, not production secrets.

The Python, JavaScript, C++17 and Java implementations use in-memory client and rate-limit state. Such state is not automatically shared across gateway instances.

A distributed deployment requires coordinated credential validation and rate-limit storage, or another explicitly designed consistency mechanism.

## 13. Performance Considerations

### Route resolution

The route registries use ordered collections and route matching.

For `R` registered routes, a straightforward linear lookup has worst-case complexity of approximately:

`O(R × P)`

where `P` represents the cost of matching a path pattern.

Large deployments can use prefix trees, compiled routing tables or other indexed matching structures.

### Authentication

Hash-map lookups provide average constant-time access to registered clients.

Database-backed credential verification requires suitable indexes and careful caching policies.

### Rate limiting

A token bucket requires constant-time state updates per request.

The principal concern in distributed deployments is synchronization of shared bucket state.

### Audit logging

Writing audit records synchronously for every request can increase latency.

Production systems may use buffered or asynchronous logging, provided that reliability and security requirements are maintained.

### Upstream calls

Connection pooling, bounded concurrency, timeouts and circuit breakers help prevent backend failures from exhausting gateway resources.

## 14. Production Limitations

The implementations are educational gateway models rather than complete production gateway servers.

| Capability | Implementation status |
|---|---|
| Route registration | Implemented |
| Parameterized routing | Implemented |
| Bearer authentication | Implemented |
| Scope-based authorization | Implemented |
| Token-bucket rate limiting | Implemented |
| Request auditing | Implemented |
| Upstream dispatch | Implemented |
| Circuit-breaker model | Implemented in JavaScript and Java |
| Persistent configuration | PostgreSQL |
| Distributed rate limiting | Requires shared runtime coordination |
| Real HTTP listener | Not implemented |
| TLS termination | Not implemented |
| Distributed tracing | Not implemented |
| Production secret management | Requires deployment integration |
| Full upstream retry management | Not implemented |

The examples intentionally separate gateway policy evaluation from network transport.

A real deployment must integrate the routing and policy logic with an HTTP server, transport security, backend connection management and operational monitoring.

## 15. Execution and Verification

### Python

Run the script using Python 3.10 or later.

The script executes its built-in assertions and writes `gateway_audit.json`.

### JavaScript

Run the file using Node.js 18 or later.

The script executes asynchronous gateway tests and writes `gateway_audit.json`.

### C++17

Compile with a C++17-compatible compiler.

The program demonstrates routing, authentication, authorization, service dispatch and request auditing.

### Java 17

Compile and execute the `APIGateway` class using Java 17.

The program demonstrates enterprise service boundaries, policy evaluation and audit reporting.

### PostgreSQL

Execute the SQL script in a dedicated PostgreSQL database.

It creates the `api_gateway` schema, inserts representative data, defines database functions and triggers, executes sample transactions and runs reporting queries.

The scripts and programs are designed to provide independent implementations of the same API Gateway concepts, with language-specific engineering decisions and different levels of runtime and persistence support.
