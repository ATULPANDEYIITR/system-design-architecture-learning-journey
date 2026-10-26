# L4 vs L7 Load Balancing

## Scope

This project models two different load-balancing boundaries:

- **L4 load balancing** operates at the transport layer and distributes network flows, typically TCP or UDP flows.
- **L7 load balancing** operates at the application layer and can inspect HTTP requests, hosts, paths, headers, cookies, methods, and other application metadata.

The implementations deliberately keep these mechanisms distinct.

```text
Client
  |
  +----------------------+
  |                      |
  v                      v
L4 Load Balancer       L7 Load Balancer
  |                      |
TCP flow identity       HTTP request semantics
  |                      |
  v                      v
Backend pool           Application routes
  |                      |
  +----------+-----------+
             |
             v
          Services
```

The central engineering distinction is the unit being balanced.

At L4, the load balancer generally chooses a backend for a transport flow. Packets belonging to that flow continue to use that backend while the flow remains valid.

At L7, the load balancer can make a routing decision for an individual HTTP request. It can therefore distinguish `/api/orders` from `/static/app.js`, route different hostnames to different services, and use cookies or headers for application-aware policies.

## Layer Boundary

| Characteristic | L4 | L7 |
|---|---|---|
| Primary protocol view | TCP/UDP | HTTP and application protocols |
| Main routing unit | Connection or flow | Request |
| HTTP parsing | Not required | Required |
| Path-based routing | No | Yes |
| Host-based routing | No | Yes |
| Header-based routing | No | Yes |
| Cookie/session routing | No application awareness | Yes |
| TLS termination | Usually pass-through or optionally terminated elsewhere | Commonly terminated |
| Processing overhead | Lower | Higher |
| Application visibility | Limited | High |
| Typical use | High-throughput transport distribution | API, web, microservice routing |

The distinction is not simply a performance comparison. L4 and L7 provide different information to the routing decision.

## L4 Load Balancing

The Python, C++17, Java 17, and PostgreSQL implementations model L4 using TCP flow identity.

A flow is identified using a tuple similar to:

```text
source IP
source port
destination IP
destination port
```

The Python implementation represents the tuple explicitly and uses deterministic hashing to select a backend. The selected backend is stored in a flow table.

The important property is flow consistency:

```text
TCP Flow A
     |
     v
  L4 Hash
     |
     +----> Backend 2
               |
               +---- packets
               +---- packets
               +---- packets
```

A later packet does not become a new routing decision merely because its payload differs. The transport flow remains associated with its selected backend.

### L4 Failure Handling

The implementation removes an existing flow mapping when the selected backend becomes unhealthy. A subsequent selection can then choose another healthy backend.

This models a practical failure boundary:

```text
Existing flow
     |
     v
Backend unhealthy
     |
     v
Flow mapping invalidated
     |
     v
New backend selection
```

Real systems must account for the fact that moving an existing TCP connection is not equivalent to transparently moving an HTTP request. A failed TCP connection normally requires connection recovery at the client or an upper-layer mechanism.

### L4 Performance Characteristics

L4 does not need to parse HTTP semantics. This can reduce per-request processing work and allows a load balancer to operate efficiently on large numbers of connections.

Important trade-offs include:

- Flow hashing can create uneven distribution when a small number of connections carry very different amounts of traffic.
- A single long-lived TCP connection can remain on one backend even when another backend has spare capacity.
- L4 cannot naturally distinguish `/api/orders` from `/api/products`.
- Application-specific routing requires a higher-layer component.

## L7 Load Balancing

L7 routing uses application information.

The implementations include routes such as:

```text
api.example.com + /api/*
        |
        +----> api-1
        |
        +----> api-2

cdn.example.com + /static/*
        |
        +----> static-1
```

The L7 models validate:

- HTTP method
- hostname
- path format
- path length
- session cookie structure

The request is then matched against application-level routing policies.

### Request-Level Routing

Unlike a basic L4 flow table, an L7 balancer can independently evaluate HTTP requests.

For example:

```text
GET /api/orders
        |
        v
     /api rule
        |
        +----> API backend

GET /static/app.js
        |
        v
   /static rule
        |
        +----> Static backend
```

This allows one externally visible service endpoint to represent multiple internal services.

## Session Affinity

The Python, JavaScript, C++, and Java implementations include session-affinity behavior.

A cookie such as:

```text
SESSION_ID=customer-42
```

can associate subsequent HTTP requests with a particular backend.

The logical flow is:

```text
First request
    |
    v
No existing affinity
    |
    v
Select backend
    |
    v
Store session -> backend

Later request
    |
    v
Find session mapping
    |
    +---- backend healthy ----> reuse
    |
    +---- backend failed -----> select replacement
```

Session affinity is an application-level concept. It is therefore naturally represented by an L7 model rather than an L4-only model.

Affinity also creates a trade-off. If sessions become strongly concentrated on one backend, request distribution can become uneven. Stateless application design can reduce the need for this mechanism.

## Health Checks

Health status is represented explicitly in all major implementations.

A backend can be:

- `healthy`
- `unhealthy`

A healthy backend can receive traffic. An unhealthy backend is removed from normal candidate selection.

The PostgreSQL model stores health checks independently:

```text
Load Balancer
     |
     +---- Backend
             |
             +---- Health Check
                     |
                     +---- passing
                     +---- failing
```

This separation is important because backend health and traffic history are different concepts.

A backend may have served thousands of requests historically while currently being unavailable.

## Python Implementation

The Python implementation is a self-contained simulation of both routing models.

### L4

`L4LoadBalancer` maintains:

- backend state
- flow mappings
- active connection counts
- deterministic flow selection

The flow table preserves transport-level affinity.

### L7

`L7LoadBalancer` maintains:

- path-based route rules
- backend health
- session affinity
- application request counts

It uses least-connections selection among eligible application backends.

### Validation

The Python implementation rejects:

- unsupported HTTP methods
- invalid hosts
- malformed paths
- oversized paths

This represents an important L7 security boundary because application parsing introduces input that must be validated before policy evaluation.

## JavaScript Implementation

The JavaScript implementation uses Node.js standard-library functionality.

Its L4 implementation uses:

- `Map` for flow state
- `crypto` hashing for deterministic flow selection
- explicit connection lifecycle management

Its L7 implementation uses:

- asynchronous functions
- Promises
- route predicates
- `Map` for session affinity
- application-level request validation

The asynchronous health-check function represents the structure used by real network services where health probes and backend operations are naturally asynchronous.

The implementation does not require third-party npm packages.

## C++17 Implementation

The C++17 implementation presents the problem as a governance-style routing engine.

The main domain types are:

- `Backend`
- `TcpFlow`
- `HttpRequest`
- `L4LoadBalancer`
- `L7LoadBalancer`

The L4 engine uses STL containers and hashing for flow selection.

The L7 engine uses:

- route candidate construction
- session extraction
- least-connections selection
- explicit exception handling

The C++ implementation also demonstrates how the two routing strategies can share a backend domain model while maintaining different selection logic.

## Java 17 Implementation

The Java implementation uses explicit enterprise domain types.

Important types include:

| Type | Responsibility |
|---|---|
| `Backend` | Backend lifecycle and counters |
| `BackendId` | Strongly typed backend identity |
| `BackendAddress` | Validated network endpoint |
| `TcpFlow` | L4 flow identity |
| `HttpRequest` | Validated L7 request |
| `RoutePolicy` | Application routing contract |
| `PathRoutePolicy` | Path-based policy |
| `L4FlowBalancer` | Transport-layer selection |
| `L7ApplicationBalancer` | Application-layer selection |

Java records are used for immutable value objects such as backend addresses and HTTP requests.

The `RoutePolicy` interface separates policy definition from routing execution. This is useful when an enterprise implementation later needs additional policies such as:

```text
HostPolicy
PathPolicy
HeaderPolicy
CookiePolicy
WeightedPolicy
GeographicPolicy
```

The implementation keeps policy evaluation explicit instead of embedding every rule into one routing method.

## PostgreSQL Model

The PostgreSQL implementation represents the infrastructure relationally.

The main relationships are:

```text
Repository
    |
    +---- Load Balancer
             |
             +---- Backend
             |
             +---- HTTP Route
             |
             +---- TCP Flow
             |
             +---- HTTP Request
             |
             +---- Health Check
```

The database uses separate records for transport flows and HTTP requests because they represent different routing units.

### Important Tables

| Table | Purpose |
|---|---|
| `load_balancers` | Identifies L4 or L7 balancing instances |
| `backends` | Stores backend endpoints and runtime state |
| `http_routes` | Stores application routing rules |
| `tcp_flows` | Stores transport-flow assignments |
| `http_requests` | Stores application-level routing decisions |
| `health_checks` | Stores backend health observations |
| `repositories` | Provides the surrounding enterprise resource |
| `branches` | Provides repository state for governance context |
| `branch_protection_policies` | Stores repository protection configuration |

The repository governance tables are retained as infrastructure context, but the load-balancing model is independent of code-review mechanics.

## Database Constraints

The PostgreSQL schema enforces several rules directly in the database.

Examples include:

- backend ports must be between 1 and 65535
- active connections cannot be negative
- request paths must begin with `/`
- HTTP paths have a maximum length
- session identifiers have a bounded size
- L4 load balancers use TCP
- L7 load balancers use HTTP
- backend identities are unique within a load balancer

This reduces dependence on application-side validation alone.

## Database Triggers

Two important runtime controls are implemented with PostgreSQL triggers.

The first prevents new traffic records from being assigned to an unhealthy backend.

The second maintains backend connection counters when TCP flows are created or closed.

A third trigger increments request counters when an HTTP routing record is inserted.

This produces a relational representation of operational state:

```text
TCP flow inserted
       |
       v
active_connections + 1

TCP flow closed
       |
       v
active_connections - 1

HTTP request inserted
       |
       v
requests_served + 1
```

## L4 and L7 Failure Modes

### L4 failure cases

A transport-level balancer can encounter:

- backend failure during an active connection
- uneven connection distribution
- long-lived connection concentration
- flow-hash imbalance
- connection exhaustion
- stale flow mappings

The important limitation is that L4 does not inherently understand the application request inside the flow.

### L7 failure cases

An application-level balancer can encounter:

- malformed HTTP requests
- invalid routing rules
- unhealthy application servers
- stale session affinity
- overloaded application backends
- excessive header or path processing
- TLS termination overhead
- incorrect application-level health checks

L7 provides more routing information but also has a larger processing and security boundary.

## Security Considerations

Load balancing is part of the network security architecture, not only a traffic-distribution mechanism.

### L4 controls

Useful controls include:

- source and destination validation
- connection limits
- SYN-flood protection
- ACLs
- rate controls
- backend isolation
- transport-level health checks

### L7 controls

L7 introduces additional controls:

- HTTP method allowlists
- host validation
- URL normalization
- path-length limits
- header-size limits
- cookie validation
- request-size limits
- authentication-aware routing where appropriate
- application-layer rate limiting

The example implementations deliberately reject unsupported HTTP methods and malformed paths before routing.

## TLS Placement

TLS placement changes what an L7 load balancer can inspect.

A common architecture is:

```text
Client
  |
 HTTPS
  |
  v
L7 Load Balancer
  |
 TLS termination
  |
 HTTP or re-encrypted HTTPS
  |
  v
Application Servers
```

If TLS remains opaque through an L4 load balancer:

```text
Client
  |
 encrypted TCP
  |
  v
L4 Load Balancer
  |
 encrypted TCP
  |
  v
Application Server
```

The second design preserves end-to-end application encryption through the load balancer but prevents the L4 component from using HTTP semantics.

## Performance Trade-Offs

| Concern | L4 | L7 |
|---|---|---|
| Packet/flow processing | Lower semantic overhead | Higher |
| HTTP parsing | None | Required |
| Routing flexibility | Low | High |
| Connection scale | Strong use case | Depends on implementation |
| Request-aware balancing | No | Yes |
| Session affinity | Transport-based only | Application-aware |
| Observability | Network-oriented | Request-oriented |

The correct choice depends on the required routing information, not simply on choosing the supposedly faster layer.

L4 is appropriate when the system primarily needs efficient transport distribution.

L7 is appropriate when routing decisions depend on application semantics.

## Choosing Between L4 and L7

A transport-oriented design is appropriate when:

- applications should receive end-to-end encrypted connections
- the load balancer should remain protocol-agnostic
- extremely high connection throughput is important
- routing can be based on network-level identity
- application parsing is unnecessary

An application-oriented design is appropriate when:

- `/api`, `/static`, and `/admin` need different destinations
- multiple hostnames share an endpoint
- HTTP headers influence routing
- cookies provide session affinity
- application-level health checks are required
- request-level observability is important

Hybrid architectures are common:

```text
Internet
   |
   v
L4 / TCP entry point
   |
   +---- TLS pass-through service
   |
   +---- L7 HTTP gateway
             |
             +---- API service
             +---- Web service
             +---- Static service
```

## Failure and Recovery Model

The implementations follow the same core rule:

```text
Receive traffic
      |
      v
Identify eligible backends
      |
      v
Remove unhealthy backends
      |
      v
Apply layer-specific routing policy
      |
      v
Select backend
      |
      v
Record routing state
      |
      v
Monitor backend health
      |
      +---- healthy ------> continue
      |
      +---- unhealthy ----> invalidate applicable state
                              |
                              v
                         select replacement
```

At L4, the replacement concerns a transport-flow mapping.

At L7, the replacement can concern an individual request or an application session.

## Practical Architectural Distinction

The four concepts in this project should not be collapsed into one generic idea of load balancing.

The core boundary is:

```text
L4
Transport flow
    |
    v
Connection-oriented decision
    |
    v
Backend

L7
HTTP request
    |
    v
Application policy evaluation
    |
    v
Backend
```

L4 answers:

> Which backend should receive this transport flow?

L7 answers:

> Which backend should receive this application request?

That distinction affects routing flexibility, observability, state management, failure recovery, performance, and security boundaries.

## Implemented Learning Artifacts

| File | Technical focus |
|---|---|
| Python | Stateful L4 flow hashing and L7 HTTP routing with validation and session affinity |
| JavaScript | Event-driven routing, asynchronous health checks, Maps, hashing, and application policies |
| C++17 | STL-based transport and application routing engines with explicit failure handling |
| Java 17 | Enterprise domain modeling, immutable records, route-policy interfaces, and service-oriented routing |
| PostgreSQL | Relational backend state, routes, flows, requests, health checks, constraints, triggers, indexes, and transactional routing records |

The five implementations express the same architectural distinction from different engineering perspectives rather than mechanically reproducing identical source code.
