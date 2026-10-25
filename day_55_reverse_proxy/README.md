# Reverse Proxy: Nginx, Proxying, and TLS Termination

## Scope

This project models a production-oriented reverse proxy architecture with particular attention to Nginx-style request routing, upstream proxying, TLS termination, health-aware backend selection, forwarded headers, failure handling, and operational visibility.

A reverse proxy sits between clients and application servers:

Client
  |
  | HTTPS
  v
Reverse Proxy
  |  TLS termination
  |  request validation
  |  routing
  |  load balancing
  |  forwarded headers
  v
Upstream Application Servers
  |
  v
Application Response

The reverse proxy is not the application itself. It provides a controlled entry point between external clients and internal services.

The five implementations use the same architectural ideas while emphasizing different engineering perspectives.

| File | Primary perspective | Main responsibility |
|---|---|---|
| Python | Workflow simulation | Models requests, TLS termination, routing, upstream selection, retries, health, and logging |
| JavaScript | Event-driven proxy model | Combines asynchronous forwarding, rate limiting, policy validation, routing, and access events |
| C++17 | Governance and performance engine | Uses explicit domain objects and STL structures to model routing and merge-like proxy eligibility decisions |
| Java 17 | Enterprise domain model | Separates TLS, routing, upstream services, validation, state, and audit behavior |
| PostgreSQL | Relational operational model | Stores routes, certificates, upstreams, requests, health state, and transactional operational data |

## Reverse Proxy Architecture

A forward proxy represents clients to external services. A reverse proxy represents application infrastructure to clients.

The distinction is important:

| Property | Forward proxy | Reverse proxy |
|---|---|---|
| Primary position | Near clients | Near servers |
| Client awareness | Client configures it | Client normally sees application hostname |
| Typical purpose | Egress control, privacy, filtering | Ingress routing, TLS termination, load balancing |
| Server visibility | External servers see proxy | Clients see proxy |
| Typical Nginx role | Possible but less common | Very common |

A reverse proxy can centralize several concerns:

- TLS termination
- HTTP routing
- upstream load balancing
- request-size limits
- header normalization
- connection management
- rate limiting
- access logging
- health-aware failover
- security policy enforcement

The application servers can therefore concentrate on application behavior instead of independently implementing every edge-facing control.

## Nginx-Style Request Flow

A typical HTTPS request follows this sequence:

1. The client resolves the public hostname.
2. The client opens a TCP connection to the reverse proxy.
3. TLS negotiation occurs with the reverse proxy.
4. The proxy validates the requested hostname and TLS policy.
5. The HTTP request is parsed and validated.
6. A routing rule selects an upstream group.
7. A healthy upstream server is selected.
8. The proxy creates an upstream request.
9. Forwarding headers communicate relevant client and transport information.
10. The upstream generates a response.
11. The proxy returns the response to the client.
12. Access and operational information is recorded.

The Python, JavaScript, C++17, and Java implementations simulate these stages instead of requiring a live network.

## TLS Termination

TLS termination means the reverse proxy is the TLS endpoint for the client connection.

The simplified transport relationship is:

Client
  |
  | TLS
  v
Nginx / Reverse Proxy
  |
  | HTTP or separately protected HTTPS
  v
Application Server

The client certificate and TLS policy are therefore handled at the proxy boundary.

The proxy must validate at least:

- requested hostname
- configured certificate
- supported TLS versions
- certificate validity
- transport security policy

The implementations accept TLS 1.2 and TLS 1.3 and reject unsupported versions.

TLS termination does not automatically mean that traffic between the proxy and application server must be unencrypted. In security-sensitive environments, upstream TLS can be used as well.

This creates two independent transport segments:

Client -> HTTPS -> Proxy

Proxy -> HTTPS -> Upstream

The proxy can also use:

Client -> HTTPS -> Proxy

Proxy -> HTTP -> Upstream

The second arrangement may be acceptable only when the internal network and threat model justify it. Network segmentation does not remove the need to evaluate internal interception risks.

## Proxying

Proxying means the reverse proxy receives the client request and makes a separate request to an upstream server.

The client does not directly establish an application connection to the upstream.

This separation provides several useful properties:

- upstream servers can remain on private addresses
- external clients do not need direct knowledge of backend topology
- multiple application instances can share one public endpoint
- failures can be handled centrally
- routing rules can be changed without changing client URLs

The reverse proxy therefore acts as an application traffic control point.

## Host and Path Routing

The project uses routing rules similar to common Nginx location and virtual-host configurations.

The model is:

| Host | Path | Upstream |
|---|---|---|
| `api.example.com` | `/api/` | API backend |
| `api.example.com` | `/` | Web backend |

Path selection uses longest-prefix matching.

For `/api/users`, both `/` and `/api/` technically match. The longer `/api/` rule is selected.

This is important because routing order and matching semantics directly affect where requests are sent.

The implementations explicitly model longest-prefix selection rather than selecting an arbitrary matching rule.

## Upstream Groups

An upstream group represents a logical pool of application servers.

Example:

API backend
  |
  +-- api-1
  |
  +-- api-2

Web backend
  |
  +-- web-1
  |
  +-- web-2

Each server contains:

- logical name
- network address
- port
- weight
- health state
- request count
- active connection count

A proxy should not normally forward traffic to an upstream known to be unhealthy.

## Load Balancing

The implementations use weighted round-robin behavior.

Suppose the API group contains:

| Server | Weight |
|---|---:|
| `api-1` | 2 |
| `api-2` | 1 |

The logical selection sequence approximates:

`api-1 -> api-1 -> api-2 -> api-1 -> api-1 -> api-2`

Weight does not mean that every short sequence must produce an exact statistical ratio. It defines relative selection frequency over a larger sequence.

Weighted selection is useful when servers have different capacity.

A higher-capacity server can receive a higher weight, while a smaller server receives a lower weight.

## Health-Aware Routing

A reverse proxy must distinguish between:

- configured server
- available server
- healthy server
- draining server
- failed server

The database model includes explicit server states.

| State | Meaning |
|---|---|
| `healthy` | Eligible for normal traffic |
| `unhealthy` | Should not receive normal traffic |
| `draining` | Can be excluded from new traffic during controlled shutdown |

The Python, C++, and Java examples allow a server to become unhealthy and then demonstrate selection of another backend.

Health checking can be implemented through:

- active HTTP health endpoints
- TCP connectivity tests
- application-specific checks
- passive failure observation

A TCP connection succeeding does not necessarily prove that the application is healthy. An application-level health endpoint can provide stronger evidence.

## Forwarded Headers

The upstream application often needs information about the original client connection.

Important headers include:

| Header | Purpose |
|---|---|
| `Host` | Original requested hostname |
| `X-Real-IP` | Original client address |
| `X-Forwarded-For` | Client and proxy address chain |
| `X-Forwarded-Proto` | Original client protocol |

For example:

`X-Forwarded-Proto: https`

allows an application to distinguish a client HTTPS request from an internal HTTP hop.

`X-Forwarded-For` is security-sensitive.

An untrusted external client must not be allowed to arbitrarily inject a trusted proxy chain. Otherwise an application may incorrectly believe that a forged address represents the real client.

The implementations therefore reject client-supplied `X-Forwarded-For` values in the simulation.

In a real Nginx deployment, trusted proxy chains should be explicitly defined and headers should be rewritten according to the actual network topology.

## Request Validation

Edge validation reduces the amount of malformed traffic reaching application servers.

The implementations validate:

- HTTP method
- request path
- path length
- control characters
- request body size
- TLS version
- configured hostname
- forwarded-header behavior
- upstream availability

A request containing carriage-return or line-feed characters in a path is rejected because uncontrolled header or request construction can create request-smuggling or header-injection risks.

Maximum body size is also enforced before forwarding.

This is a resource-control mechanism, not a replacement for application-level validation.

## Retry Behavior

A reverse proxy can retry a request when an upstream transport failure occurs.

The implementations deliberately limit retries to one alternate server.

The workflow is:

Client request
  |
  v
api-1
  |
  X transport failure
  |
  v
api-2
  |
  v
Response

Retries require care.

A retry is relatively safe for many idempotent operations such as `GET`, but retrying a failed `POST` can potentially execute an operation twice if the first request actually reached the application before the connection failed.

Production retry policy should therefore consider:

- HTTP method
- idempotency
- whether the upstream received the request
- timeout type
- connection state
- application semantics
- maximum retry count

Unlimited retries are dangerous because they can amplify an upstream failure.

## Failure Modes

The project models several failure classes.

| Failure | Example response | Meaning |
|---|---:|---|
| Invalid request | 400 | Client request violates proxy validation |
| TLS failure | 495 in the simulation | TLS policy or certificate configuration rejected the connection |
| No healthy upstream | 503 | Proxy cannot obtain a usable backend |
| Upstream transport failure | 503 after retry exhaustion | Backend communication failed |
| Configuration error | Startup/runtime exception | Proxy configuration is invalid |

The exact status used for TLS errors can differ between real deployments. The `495` value is commonly used by Nginx-related configurations but is not a standard HTTP status code.

The database uses the standard 100-599 response range for recorded HTTP responses and stores proxy state separately.

## Access Logging

The proxy is a useful location for request-level operational logging.

The project records information such as:

- timestamp
- client address
- HTTP method
- request path
- response status
- selected upstream
- processing duration

Access logs help investigate:

- high latency
- backend failures
- unexpected routing
- traffic spikes
- repeated client errors
- upstream imbalance

Logs should not blindly contain sensitive information.

Production logging policies should consider:

- authorization headers
- session identifiers
- cookies
- personal information
- request bodies
- authentication tokens
- payment information

Structured logging is preferable when logs are consumed by monitoring systems.

## Python Implementation

The Python file models the reverse proxy as a set of explicit domain objects.

Important components include:

| Component | Responsibility |
|---|---|
| `TLSCertificate` | Represents certificate identity and TLS policy |
| `TLSManager` | Performs simulated TLS termination |
| `Request` | Represents an incoming HTTP request |
| `Response` | Represents the proxy response |
| `UpstreamServer` | Tracks backend state and statistics |
| `LocationRule` | Represents path-to-upstream routing |
| `RoundRobinBalancer` | Performs weighted backend selection |
| `ReverseProxy` | Coordinates validation, routing, TLS, forwarding, retries, and logging |

The implementation uses dataclasses for structured domain state and enums for protocol and server state.

The proxy performs longest-prefix route selection.

It also prevents untrusted clients from supplying an existing forwarded-client chain.

The failure endpoint intentionally simulates an upstream transport error so that retry behavior can be observed without external infrastructure.

## JavaScript Implementation

The JavaScript implementation takes an event-driven approach.

It uses:

- `Map` for upstream pools and rate-limit state
- `Set` for excluded retry candidates
- Promises for asynchronous upstream forwarding
- `async` and `await` for request processing
- Node.js `crypto` for request identifiers
- `process.hrtime.bigint()` for high-resolution duration measurement

The `RateLimiter` provides a simple fixed-window control.

The asynchronous upstream function simulates the fact that a real reverse proxy performs I/O rather than purely CPU-bound computation.

The implementation also records structured access events.

The design deliberately does not depend on Express, Axios, or another third-party package.

## C++17 Implementation

The C++ implementation emphasizes explicit data structures and predictable resource handling.

The primary structures are:

- `Request`
- `Response`
- `UpstreamServer`
- `Route`
- `TLSCertificate`

The `ReverseProxy` class owns routing and upstream groups, while `LoadBalancer` maintains selection state.

The implementation uses:

- `std::vector`
- `std::unordered_map`
- `std::set`
- `std::map`
- exceptions
- references
- scoped resource accounting

Active connections are incremented before forwarding and decremented through both success and exception paths.

This is important because connection counters must remain correct even when an upstream operation fails.

The code uses C++17 `std::optional`-compatible design concepts but does not require external libraries.

## Java 17 Implementation

The Java implementation uses a domain-oriented enterprise structure.

Java records represent immutable value-oriented data:

- `TLSCertificate`
- `Route`
- `Request`
- `ProxyResponse`

Mutable operational entities such as `UpstreamServer` remain classes because health state and connection counters change over time.

The `ReverseProxyService` acts as the orchestration layer.

The implementation separates:

- TLS validation
- route resolution
- upstream selection
- request validation
- forwarding
- audit recording
- health-state changes

Custom exception types distinguish request, TLS, and upstream failures.

This separation makes the design suitable for extension into a larger service where configuration, observability, policy, and transport concerns can be managed independently.

## PostgreSQL Data Model

The PostgreSQL implementation represents both proxy infrastructure and operational workflow.

Core relationships are:

Repositories
  |
  +-- Branches
  |
  +-- Commits
  |
  +-- Pull Requests
  |
  +-- Reviews
  |
  +-- Review Comments
  |
  +-- Conversations
  |
  +-- Status Checks
  |
  +-- Branch Protection

The proxy-specific operational relationship is:

Certificates
  |
  v
Routes
  |
  v
Upstream Groups
  |
  v
Upstream Servers
  |
  v
Proxy Requests

The branch and review tables provide repository-governance context for validating configuration changes before deployment. They are deliberately separate from the runtime proxy path.

## Database Constraints

The schema uses database constraints to reject invalid state.

Examples include:

- unique repository names
- unique branch names within repositories
- foreign keys between related entities
- positive server weights
- valid port ranges
- non-negative connection counters
- valid response status codes
- valid review states
- valid server states
- distinct source and target branches

These rules prevent some classes of invalid data without relying entirely on application code.

## Database Triggers

Two important triggers enforce workflow behavior.

The review validation trigger prevents:

- inactive reviewers from submitting reviews
- reviews against closed pull requests

The approval-staleness trigger marks existing approvals stale when the pull request head commit changes.

This represents an important governance principle:

A review decision applies to a particular version of the proposed change.

If new commits are introduced, the old approval may no longer represent the code currently being evaluated.

## Merge Eligibility Model

The database includes a `merge_eligibility` function.

It evaluates several independent conditions:

1. The pull request exists.
2. The pull request remains open.
3. The pull request is not a draft.
4. Required approvals exist.
5. Active changes-requested reviews do not block the merge.
6. Required conversations are resolved.
7. Required status checks pass.
8. The source and target branches are mergeable.

This is deliberately separate from the reverse proxy runtime path.

A deployment configuration can be technically valid while still being prohibited from production because repository governance conditions were not satisfied.

## Branch Protection and Deployment Safety

Branch protection is a repository governance mechanism.

A protected branch can require:

- pull requests
- approvals
- successful automated checks
- resolved conversations
- linear history
- restrictions on direct pushes
- restrictions on force pushes
- restrictions on branch deletion

The PostgreSQL policy model stores these controls explicitly.

The key distinction is:

A reverse proxy controls runtime traffic.

Branch protection controls how changes reach a repository branch.

The two mechanisms operate at different lifecycle stages but can support the same operational objective: preventing unsafe configuration from reaching production.

## Configuration Change Workflow

A realistic change to an Nginx reverse proxy might follow this sequence:

Developer
  |
  | configuration change
  v
Feature Branch
  |
  | Pull Request
  v
Code Review
  |
  +-- comments
  +-- requested changes
  +-- approvals
  +-- automated validation
  |
  v
Protected Main Branch
  |
  | deployment pipeline
  v
Reverse Proxy Configuration
  |
  v
Production Traffic

This separates proposed configuration from deployed configuration.

The Pull Request is the change workflow.

Code review evaluates the change.

Approvals represent review decisions.

Branch protection enforces repository conditions.

The reverse proxy executes the configuration after deployment.

## Performance Considerations

Reverse proxies are latency-sensitive infrastructure.

Important performance factors include:

- connection reuse
- keep-alive connections
- TLS handshake cost
- upstream connection pooling
- request buffering
- response buffering
- load-balancing algorithm
- DNS resolution behavior
- worker concurrency
- network bandwidth
- logging overhead

The simulation uses in-memory collections, so its computational behavior differs from a real Nginx process.

Longest-prefix routing scans the configured routes in the sample implementations. With a large number of routes, a production routing engine can use more specialized structures.

Weighted round-robin selection creates a temporary weighted representation in the examples. Production implementations can maintain more efficient scheduling state.

## Security Considerations

Important controls include:

- TLS 1.2 or newer
- certificate validation
- secure private-key storage
- request-size limits
- header normalization
- trusted-proxy configuration
- restricted upstream network access
- rate limiting
- protection against header injection
- careful retry policies
- minimal information disclosure
- controlled administrative access
- secure configuration deployment

The proxy should not be treated as the only security boundary.

Application authorization must still occur at the application layer.

A successful TLS handshake proves transport security. It does not prove that the user is authorized to perform the requested operation.

## Failure Handling

A robust reverse proxy should distinguish transport failure from application failure.

For example:

`502 Bad Gateway` commonly indicates that the proxy received an invalid response or encountered a problem communicating with an upstream.

`503 Service Unavailable` commonly indicates that a service is unavailable.

`504 Gateway Timeout` commonly indicates that the upstream did not respond within the configured timeout.

The exact mapping depends on the proxy configuration and failure condition.

Retrying every error is unsafe because application-level errors are not necessarily transient transport failures.

## Configuration and Certificate Lifecycle

TLS certificates require operational lifecycle management.

Important stages include:

- certificate issuance
- installation
- validation
- expiration monitoring
- renewal
- deployment
- rollback

A reverse proxy configuration should be validated before reload.

A safe configuration workflow can be represented as:

Configuration Change
  |
  v
Syntax Validation
  |
  v
Automated Tests
  |
  v
Pull Request Review
  |
  v
Required Approvals
  |
  v
Protected Branch
  |
  v
Deployment
  |
  v
Runtime Health Verification

This reduces the risk of deploying syntactically valid but operationally incorrect proxy configuration.

## Limitations of the Implementations

The implementations are deliberately self-contained simulations.

They do not implement a complete HTTP server, TLS cryptographic stack, TCP connection manager, or production Nginx configuration parser.

They therefore do not model:

- real TLS handshakes
- certificate-chain verification
- HTTP/2 framing
- HTTP/3 and QUIC
- kernel socket behavior
- actual upstream network latency
- real Nginx worker processes
- connection pools
- production DNS behavior
- distributed rate-limit coordination
- full HTTP caching
- WebSocket lifecycle
- streaming request bodies
- production-grade configuration reloads

The purpose of the implementations is to expose the architectural and state-management decisions involved in reverse proxying rather than to replace a production proxy server.

## Cross-Implementation Design Comparison

| Concern | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| TLS policy | `TLSManager` | `TLSManager` | `TLSManager` | `TLSManager` | Certificate table |
| Routing | Longest prefix | Longest prefix | Longest prefix | Longest prefix | `route_request()` |
| Load balancing | Weighted round robin | Weighted round robin | Weighted round robin | Weighted round robin | Upstream state queries |
| Health | Enum state | Server state | Server state | Server state | `server_state` |
| Forwarded headers | Explicit construction | Explicit construction | Explicit validation | Explicit validation | Request records |
| Retry | Limited retry | Async retry | Limited retry | Limited retry | Operational state |
| Security validation | Request validation | Validation and rate limiting | Request validation | Request validation | Constraints and triggers |
| Observability | Access logs | Event records | Statistics | Audit events | Request/reporting tables |
| Persistence | In-memory | In-memory | In-memory | In-memory | Relational database |

## Practical Relationship Between the Components

The complete architecture can be viewed as two connected control planes.

Runtime plane:

Client
  |
  v
TLS Termination
  |
  v
Request Validation
  |
  v
Route Selection
  |
  v
Healthy Upstream Selection
  |
  v
Proxy Request
  |
  v
Application Response

Change-management plane:

Configuration Change
  |
  v
Feature Branch
  |
  v
Pull Request
  |
  v
Code Review
  |
  v
Approvals
  |
  v
Branch Protection
  |
  v
Deployment
  |
  v
Runtime Proxy

The runtime plane determines how traffic is processed.

The change-management plane determines whether a proposed configuration can safely reach the protected production branch.

Keeping these concerns distinct makes the system easier to reason about, test, audit, and operate.
