# DNS: Domain resolution, recursive DNS, and caching

## Introduction

The Domain Name System (DNS) is the distributed naming system used to map domain names to structured resource records. A common example is the translation of `www.example.com` into an IPv4 address through an `A` record.

DNS is not a single database. It is a hierarchy of cooperating systems that includes root servers, top-level-domain servers, authoritative nameservers, recursive resolvers, and client-side stub resolvers.

Three ideas are central to understanding DNS:

- **Domain resolution** determines the DNS data associated with a name.
- **Recursive DNS** allows a resolver to perform the resolution process on behalf of a client.
- **Caching** allows previously obtained DNS data to be reused until its TTL expires.

The three implementations in this repository model these concepts differently:

- The Python implementation provides a broad educational model of DNS concepts, hierarchy, records, recursion, caching, security, transport, DNSSEC, reverse DNS, and operational concerns.
- The JavaScript implementation emphasizes asynchronous resolution, application-level behavior, promises, cache management, and event-driven programming.
- The C++ implementation develops a larger technical case study for a distributed application using zones, authoritative servers, recursive resolution, TTL-aware caching, retries, CNAME handling, multiple addresses, and application-level hostname resolution.

The implementations use simulated DNS infrastructure rather than depending on external DNS servers. This makes their behavior deterministic and suitable for studying the resolution process.

## DNS terminology

### Domain name

A domain name is a hierarchical sequence of labels.

For example:

`www.example.com.`

contains:

- `www` as a host or service label
- `example` as a second-level domain
- `com` as the top-level domain
- `.` as the DNS root

DNS names are case-insensitive in normal DNS comparison.

### Label

A label is one component between dots in a domain name.

In `api.example.com.`, the labels are:

`api`, `example`, `com`

The root is represented by the final dot.

### Fully qualified domain name

A fully qualified domain name (FQDN) specifies a complete DNS name relative to the root.

`www.example.com.` explicitly includes the root terminator.

Applications often accept `www.example.com` without the final dot and treat it as equivalent to the FQDN.

### Zone

A DNS zone is an administratively managed portion of the DNS namespace.

A zone can contain resource records and delegation information. A zone is not necessarily identical to an entire domain because a domain can contain delegated child zones.

### Nameserver

A nameserver is a server that provides DNS information.

The important operational distinction is between:

- authoritative nameservers, which serve authoritative zone data
- recursive resolvers, which obtain answers for clients

### Authoritative server

An authoritative server is responsible for authoritative DNS data for one or more zones.

If an authoritative server serves `example.com.`, it can provide records such as:

`example.com. A 93.184.216.34`

The Python `AuthoritativeServer`, JavaScript `AuthoritativeServer`, and C++ `AuthoritativeServer` classes model this role.

### Recursive resolver

A recursive resolver receives a client request and obtains the answer on the client's behalf.

A simplified resolution process is:

Client → recursive resolver → root → TLD → authoritative server → recursive resolver → client

The resolver normally caches successful results so that later clients do not need to repeat the entire process.

### Stub resolver

A stub resolver is the client-side DNS component that sends DNS queries to a configured recursive resolver.

A typical application does not directly contact root or TLD servers.

## Resource records

DNS data is represented as resource records.

A simplified record has:

`name TTL IN type value`

For example:

`example.com. 3600 IN A 93.184.216.34`

The implementations represent records with structures or classes containing:

- name
- record type
- value
- TTL

## Important DNS record types

### A

An `A` record maps a name to an IPv4 address.

Example:

`api.example.com. A 192.0.2.10`

### AAAA

An `AAAA` record maps a name to an IPv6 address.

Example:

`api.example.com. AAAA 2001:db8::10`

### CNAME

A `CNAME` record creates an alias to another DNS name.

Example:

`www.example.com. CNAME example.com.`

A CNAME does not directly contain an IP address. The resolver must resolve the target name when the requested record type requires it.

This distinction is demonstrated explicitly in all three implementations.

### NS

An `NS` record identifies authoritative nameservers for a zone.

Example:

`example.com. NS ns1.example.com.`

### MX

An `MX` record identifies mail exchangers.

The value contains a preference and hostname.

Example:

`example.com. MX 10 mail.example.com.`

### TXT

A `TXT` record stores textual data. It is widely used for domain-related configuration and verification mechanisms.

### SOA

The `SOA` record describes authoritative zone information such as the primary nameserver, serial number, and timing parameters.

SOA information is especially important for zone administration and negative caching.

### PTR

A `PTR` record is commonly used for reverse DNS.

Instead of:

`name → address`

the lookup becomes:

`address → name`

## DNS hierarchy

DNS has a hierarchical delegation model.

A simplified public resolution sequence is:

Client  
→ Recursive resolver  
→ Root server  
→ TLD server  
→ Authoritative nameserver

The root zone delegates responsibility for top-level domains such as `.com`.

The `.com` TLD infrastructure can then delegate a domain such as `example.com`.

The authoritative infrastructure for `example.com` can then provide records such as `www.example.com`.

This hierarchy distributes responsibility instead of requiring every DNS server to contain every DNS record.

## Root servers

The root zone sits at the top of the DNS hierarchy.

A recursive resolver can query a root server when it does not have enough cached information to continue resolution.

The root generally does not provide the final address for an ordinary hostname. It provides information that allows the resolver to continue, such as a referral toward the appropriate TLD infrastructure.

The Python and C++ simulations explicitly model this conceptual referral.

## TLD servers

Top-level-domain servers are authoritative for their respective TLD zones.

For example, `.com` nameservers contain delegation information for domains beneath `.com`.

A resolver can therefore move from:

`www.example.com.`

to:

`com.`

and then to:

`example.com.`

## Authoritative resolution

After obtaining the delegation for a domain, the recursive resolver can contact the domain's authoritative nameserver.

For a query such as:

`example.com. A`

the authoritative server can return:

`example.com. A 93.184.216.34`

The answer is authoritative because it comes from the DNS infrastructure responsible for that zone.

## Recursive versus iterative queries

These terms describe different resolution behaviors.

### Recursive query

A client can ask a recursive resolver to obtain the final answer.

Conceptually:

`Client → Resolver: resolve example.com A`

The resolver performs the work required to obtain the result.

### Iterative query

An iterative interaction allows the responding server to return the best information it has.

For example, a root server may indicate the appropriate TLD servers rather than resolving the complete hostname.

The resolver then contacts those servers and continues.

Conceptually:

`Resolver → Root`

`Root → TLD referral`

`Resolver → TLD`

`TLD → Authoritative referral`

`Resolver → Authoritative`

`Authoritative → final answer`

The Python `iterative_resolve`, JavaScript `iterativeResolve`, and C++ `DNSHierarchy::iterativeResolve` methods model this process.

## Recursive resolver architecture

A recursive resolver commonly performs these steps:

- normalize the requested name
- check its local cache
- return a valid cached result when available
- determine where to continue resolution if the cache misses
- query root or another appropriate upstream source
- follow referrals
- contact authoritative servers
- follow CNAME chains when necessary
- validate the result according to its configured security policy
- cache appropriate data
- return the result to the client

Real recursive resolvers contain substantially more mechanisms than the educational implementations.

## DNS caching

Caching is one of the most important performance characteristics of DNS.

Suppose a resolver obtains:

`example.com. A 93.184.216.34`

with a TTL of `3600`.

The resolver can generally retain the result for up to 3600 seconds, subject to DNS implementation and operational policies.

A later client asking for the same record can receive the cached result without the resolver repeating the entire hierarchy traversal.

### Cache hit

A cache hit occurs when a valid cached entry is available.

The Python and JavaScript examples explicitly report cache hits.

The C++ resolver records cache-hit statistics.

### Cache miss

A cache miss occurs when no usable cached entry exists.

The resolver must obtain the required information from upstream DNS infrastructure.

### TTL

TTL means Time To Live.

TTL determines how long DNS data can be cached.

Longer TTL values can reduce DNS traffic and improve cache efficiency, but changes can remain cached for longer.

Shorter TTL values allow changes to be observed more quickly but can increase DNS query volume.

TTL is therefore an operational trade-off rather than simply a performance setting.

## Positive caching

Positive caching stores successful DNS records.

For example:

`api.example.com. A 192.0.2.10`

can be cached according to its TTL.

The Python implementation uses `CacheEntry`.

The JavaScript implementation stores cache entries in a `Map`.

The C++ implementation uses an `unordered_map` keyed by a DNS query key.

## Negative caching

DNS can also cache negative results.

`NXDOMAIN` indicates that the queried DNS name does not exist.

Without negative caching, an application repeatedly requesting a nonexistent name could cause repeated upstream queries.

The examples therefore cache NXDOMAIN responses for a short simulated period.

Real DNS negative caching is more precise and is associated with authoritative SOA information and DNS protocol rules.

## NXDOMAIN versus empty answers

These cases should not be confused.

### NXDOMAIN

The queried name does not exist.

### NOERROR with no requested record

The name can exist even when the requested record type is not present.

For example, a name might have an `A` record but no `AAAA` record.

### SERVFAIL

The resolver or server could not successfully complete the operation.

Possible causes include upstream failures, validation failures, communication problems, or other resolver-side conditions.

### REFUSED

A server has declined to perform the requested operation.

### TIMEOUT

No response arrived within the relevant timeout period.

A timeout is often an operational/network condition rather than a DNS data statement.

## CNAME resolution

Consider:

`www.example.com. CNAME example.com.`

and:

`example.com. A 93.184.216.34`

An application asking for `www.example.com A` cannot simply treat the CNAME itself as an IPv4 address.

The resolver follows the alias:

`www.example.com.`

→ `example.com.`

→ `93.184.216.34`

The implementations demonstrate this process.

CNAME chains can contain multiple aliases. Long or problematic chains increase resolution work and can create operational problems.

## Multiple records

A name can have multiple records of a particular type.

For example:

`api.example.com. A 192.0.2.10`

`api.example.com. A 192.0.2.11`

A client can receive both addresses.

DNS response ordering and client selection behavior can vary. A simple round-robin mechanism can rotate addresses, but DNS round-robin is not equivalent to a health-aware load balancer.

Important limitations include:

- cached responses
- client-side address selection
- lack of guaranteed health checking
- failure persistence until caches expire
- resolver-specific behavior

## DNS zones and delegation

A zone represents an administrative boundary.

A parent zone can delegate a child zone by publishing NS information.

For example:

`example.com. NS ns1.example.com.`

`example.com. NS ns2.example.com.`

This means that authoritative responsibility can be delegated.

The recursive resolver follows these delegations until it reaches an authoritative source.

## Glue records

A delegated nameserver can sometimes exist inside the very zone it serves.

For example:

`example.com. NS ns1.example.com.`

The resolver needs an address for `ns1.example.com.` before it can query that nameserver.

This creates a circular dependency.

Glue records published by the parent provide the address needed to reach the delegated nameserver.

Glue is therefore related to delegation and reachability rather than ordinary application records.

## Reverse DNS

Forward DNS normally performs:

`name → address`

Reverse DNS performs:

`address → name`

IPv4 reverse DNS uses the `in-addr.arpa` namespace.

For example:

`192.0.2.25`

maps to the reverse lookup name:

`25.2.0.192.in-addr.arpa.`

IPv6 reverse DNS uses `ip6.arpa` and represents the address as reversed hexadecimal nibbles.

Reverse DNS is commonly relevant to:

- network diagnostics
- logging
- infrastructure management
- mail-server reputation checks
- operational troubleshooting

A PTR result alone should not be treated as cryptographic proof of identity.

## DNS message structure

DNS communication uses structured messages.

A conceptual DNS message contains:

- header
- question section
- answer section
- authority section
- additional section

The header includes fields such as:

- transaction ID
- recursion desired
- recursion available
- authoritative answer
- response code

The Python and JavaScript implementations model these structures as objects.

Actual DNS wire messages use a compact binary representation and include protocol-specific encoding details.

## DNS transport

Traditional DNS commonly uses UDP port 53.

TCP port 53 is also part of DNS and is important for cases where TCP is required, including certain large responses and DNS zone transfers.

Modern encrypted DNS transports include:

### DNS over TLS

DNS over TLS, commonly called DoT, carries DNS traffic through TLS, normally using port 853.

It protects the communication between the client and resolver from observers that would otherwise see the DNS messages.

### DNS over HTTPS

DNS over HTTPS, commonly called DoH, transports DNS messages through HTTPS, normally using port 443.

DoH can make DNS traffic resemble other HTTPS traffic.

### DNSSEC versus DoT and DoH

These mechanisms solve different problems.

DNSSEC provides mechanisms for authenticating DNS data and validating its integrity.

DoT and DoH protect the transport channel between DNS endpoints.

Therefore:

`DNSSEC ≠ encryption`

and:

`DoT/DoH ≠ DNS data authentication`

They can be used for different parts of a broader DNS security design.

## DNSSEC

DNS Security Extensions provide cryptographic mechanisms for validating DNS data.

Important DNSSEC concepts include:

### DNSKEY

Contains public key material associated with a zone.

### RRSIG

Contains a digital signature over DNS resource-record data.

### DS

Delegation Signer information connects a child zone's cryptographic identity to its parent.

### NSEC and NSEC3

Support authenticated denial of existence.

### Chain of trust

DNSSEC validation follows a chain from a configured trust anchor through parent and child zones.

The Python implementation uses a simplified signed-record model to illustrate the concepts.

The simulation does not implement actual DNSSEC cryptography.

## DNS security

DNS infrastructure has several security concerns.

### Cache poisoning

A cache-poisoning attack attempts to cause a recursive resolver to store false DNS information.

Important defensive mechanisms include:

- transaction-ID randomization
- source-port randomization
- bailiwick checking
- careful handling of additional records
- DNSSEC validation
- current resolver software
- monitoring
- restricted recursion

### Open recursion

A publicly accessible recursive resolver can be abused by unauthorized users.

Recursive infrastructure should therefore be deliberately configured rather than accidentally exposed.

### DNS amplification

Some DNS responses can be substantially larger than their requests.

Attackers can abuse exposed DNS infrastructure as part of reflection or amplification attacks.

Appropriate network and resolver controls are therefore important.

### DNS-provider account security

Compromise of an authoritative DNS provider or registrar account can allow an attacker to alter DNS records.

DNS security therefore extends beyond DNS packets to operational account protection.

## Split-horizon DNS

Split-horizon DNS provides different answers depending on the requesting context.

For example:

Internal client:

`portal.example.com. → 10.0.0.20`

External client:

`portal.example.com. → 203.0.113.20`

This can support internal services while maintaining separate public records.

The approach can make troubleshooting more difficult because two clients can receive different results for the same hostname.

## DNS failures and debugging

DNS problems should be analyzed layer by layer.

A useful conceptual path is:

Application

→ operating-system stub resolver

→ recursive resolver

→ network path

→ root/TLD infrastructure

→ authoritative server

→ zone configuration

Useful diagnostic questions include:

- Does the hostname normalize correctly?
- Is the configured recursive resolver reachable?
- Is the response cached?
- Has the cache entry expired?
- Does the domain exist?
- Is the requested record type present?
- Is there a CNAME?
- Is the CNAME target resolvable?
- Are authoritative nameservers reachable?
- Is delegation correct?
- Are DNSSEC validation failures occurring?
- Is the resolver returning NXDOMAIN, SERVFAIL, REFUSED, or a timeout?

## Python implementation

The Python program is a broad conceptual study implementation.

### Record representation

`DNSRecord` models:

- name
- record type
- value
- TTL

`RecordType` provides common DNS record types.

### Zone representation

`DNSZone` stores records indexed by name and record type.

This demonstrates the idea of resource-record sets without implementing the DNS wire protocol.

### Authoritative server

`AuthoritativeServer` associates zones with authoritative DNS infrastructure.

Its lookup behavior demonstrates the distinction between authoritative data and recursive resolution.

### DNS hierarchy

`SimulatedDNSInfrastructure` represents:

- root delegation
- TLD delegation
- authoritative servers

The implementation follows referrals to reach the authoritative source.

### Recursive resolver

`RecursiveResolver` provides client-facing recursive resolution.

Its cache contains `CacheEntry` objects with expiration times.

It demonstrates:

- cache hits
- cache misses
- TTL expiration
- positive caching
- negative caching
- CNAME processing

### Controlled time

`FakeClock` allows TTL behavior to be demonstrated deterministically without waiting for real time to pass.

This is an important testing technique because time-dependent code is difficult to test reliably if it depends directly on wall-clock time.

### Security model

The Python program also explains:

- cache poisoning
- DNSSEC
- DoT
- DoH
- restricted recursion
- authoritative/recursive separation

The security portions are conceptual rather than full cryptographic or network implementations.

## JavaScript implementation

The JavaScript implementation emphasizes asynchronous application behavior.

### JavaScript DNS records

DNS records are represented as objects created by `createRecord`.

`Object.freeze` is used for record objects so that example record data cannot be accidentally modified after creation.

### Maps

`DNSZone` uses JavaScript `Map` objects to index records.

This provides a convenient model for application-level key/value lookup.

### Asynchronous resolution

`SimulatedDNSInfrastructure.authoritativeQuery` is asynchronous.

The artificial delay represents network latency.

The resolver therefore uses:

`async`

and:

`await`

to model real network-oriented programming.

### Recursive resolver

`RecursiveResolver` performs:

- cache lookup
- expiration checking
- upstream iterative resolution
- TTL-based insertion
- negative caching

### CNAME

The asynchronous resolver follows CNAME targets recursively.

This shows how DNS resolution can involve multiple dependent asynchronous operations.

### Retry behavior

`withRetries` demonstrates retrying failed asynchronous operations.

The example uses increasing delay intervals to illustrate exponential backoff.

Production systems often add jitter so that many clients do not retry simultaneously.

### Application client

`DNSApplicationClient` demonstrates a common real application pattern:

`hostname → resolver → addresses → connection target`

The application does not need to know how root, TLD, or authoritative resolution works.

## C++ case study

The C++ implementation models a distributed application called through the example domain:

`acme.test.`

The simulated infrastructure contains:

`api.acme.test.`

`www.acme.test.`

`mail.acme.test.`

### Problem being solved

The application needs to translate service names into network addresses efficiently while accounting for:

- hierarchical DNS resolution
- authoritative data
- aliases
- caching
- TTL
- failures
- retries
- multiple addresses

### Major components

`DNSRecord`

Represents a DNS resource record.

`DNSZone`

Stores authoritative records.

`AuthoritativeServer`

Serves authoritative zones.

`DNSHierarchy`

Models root, TLD, and authoritative resolution.

`RecursiveResolver`

Provides recursive client-facing resolution and caching.

`RetryPolicy`

Models failure recovery.

`RoundRobinSelector`

Demonstrates application selection among multiple addresses.

`ApplicationClient`

Represents an application consuming DNS resolution.

### Query key

The C++ resolver uses a query key containing:

- normalized DNS name
- record type

The key is hashed for efficient cache lookup.

This is an important implementation detail because DNS cache entries are associated with a particular query name and type.

### Cache expiration

Each cache entry stores an expiration time.

A lookup compares the current time against that expiration.

Expired entries are removed before they can be returned.

### Cache complexity

With an appropriate hash table, cache lookup is approximately O(1) on average.

The complete DNS resolution process is different.

A cache miss can require several network round trips:

`client → resolver`

`resolver → root`

`resolver → TLD`

`resolver → authoritative`

The exact number depends on cached delegation data, referrals, CNAME chains, failures, and resolver behavior.

### Multiple authoritative servers

The case study uses two authoritative nameservers.

Redundancy is important because a resolver should not depend on a single authoritative endpoint.

Real DNS deployments should consider network diversity and operational independence rather than merely placing multiple server names on the same infrastructure.

### CNAME handling

The C++ hierarchy detects a CNAME response and recursively resolves its target.

This represents the logical relationship:

`www.acme.test.`

→ `acme.test.`

→ `198.51.100.10`

### Negative caching

A missing hostname receives an `NXDOMAIN` result.

The resolver stores the negative result for a short simulated interval.

The implementation comment explicitly distinguishes this simplified model from production DNS, where negative caching duration is derived from authoritative SOA information.

### Retry policy

The C++ case study models temporary failures such as timeouts.

A retry policy attempts the operation more than once.

Retries must be designed carefully because aggressive retry behavior can increase upstream load during an outage.

## DNS caching and performance

Caching usually has a greater effect on perceived DNS latency than local computation.

A cache hit can avoid several network operations.

A cache miss can require communication with multiple layers of the DNS hierarchy.

Factors affecting DNS performance include:

- cache hit rate
- TTL values
- network round-trip time
- packet loss
- resolver location
- authoritative server location
- number of CNAME links
- DNSSEC validation
- retries
- connection and transport behavior
- resolver implementation

### Cache capacity

A production recursive resolver must manage finite memory.

Possible concerns include:

- maximum cache size
- expiration
- eviction
- negative entries
- large numbers of unique names
- RRset consistency
- concurrent queries

The Python implementation demonstrates a bounded cache concept.

The JavaScript implementation demonstrates an LRU cache using `Map` insertion order.

## TTL trade-offs

A TTL represents a compromise between caching efficiency and change propagation.

A longer TTL can provide:

- fewer upstream queries
- greater cache reuse
- lower resolver traffic
- lower authoritative-server load

A longer TTL can also mean:

- slower visibility of DNS changes
- longer persistence of stale information after changes

A shorter TTL can provide:

- faster adaptation to changes
- greater operational flexibility

At the same time, shorter TTL values can result in:

- more queries
- greater dependency on DNS infrastructure
- increased resolver and authoritative traffic

TTL selection should therefore be based on operational requirements rather than a universal value.

## Caching and stale information

A resolver should not normally return a record beyond its allowed cache lifetime merely because the record remains convenient to use.

Operational systems can implement special stale-data behavior under defined circumstances, but this requires careful consideration because stale DNS data can cause traffic to be directed toward outdated infrastructure.

## Edge cases

### Empty hostname

An empty hostname is invalid for the examples and is rejected.

### Missing hostname

A nonexistent name results in `NXDOMAIN`.

### Unsupported record type

The JavaScript implementation validates requested record types when records are created.

### Expired cache entry

An expired cache entry is removed before a new upstream lookup.

### CNAME target failure

If the CNAME target cannot be resolved, the final lookup does not become a valid address merely because the alias itself existed.

### Multiple A records

The resolver can return more than one address.

Applications must decide how to select among them.

### Authoritative server failure

The simulated infrastructure can move to another authoritative server when one is unavailable.

### Retry exhaustion

If repeated attempts fail, the resolver can ultimately return a failure status.

## Common mistakes

### Treating DNS as a simple hostname-to-IP dictionary

DNS is hierarchical and contains many record types.

### Assuming every query reaches an authoritative server

Resolvers commonly satisfy queries from cache.

### Confusing recursive and authoritative DNS

A recursive resolver obtains information for clients. An authoritative server serves authoritative zone data.

### Treating CNAME as an IP address

CNAME contains another DNS name.

### Ignoring TTL

DNS changes can remain cached according to TTL.

### Treating NXDOMAIN as SERVFAIL

These indicate different conditions.

### Assuming multiple A records are a load balancer

DNS can return multiple addresses, but it does not automatically provide full health-aware load balancing.

### Assuming encrypted DNS proves authenticity

DoT and DoH protect transport. DNSSEC addresses authenticity and integrity of DNS data.

### Exposing recursive DNS without access control

Open recursion can create security and abuse risks.

### Using excessive retries

Retries can increase traffic precisely when upstream infrastructure is already experiencing problems.

## Implementation considerations

A production DNS implementation must address issues that are intentionally simplified here.

These include:

- DNS packet parsing and serialization
- name compression
- UDP handling
- TCP fallback
- EDNS
- DNS message size limits
- retransmission
- server selection
- concurrent requests
- request coalescing
- cache eviction
- negative caching rules
- DNSSEC validation
- malformed packet handling
- resource limits
- abuse controls
- logging
- metrics
- configuration reloads
- zone transfers
- authoritative update mechanisms

The examples model the architecture rather than implementing the full DNS protocol stack.

## Security considerations

A production resolver should consider:

- cache poisoning
- unauthorized recursion
- reflection and amplification
- DNSSEC validation
- malformed input
- excessive query rates
- resource exhaustion
- compromised DNS-provider credentials
- incorrect delegation
- malicious or unexpected CNAME chains
- monitoring and incident response

Security should be implemented at multiple layers rather than relying on one DNS feature.

## Python, JavaScript, and C++ comparison

| Aspect | Python | JavaScript | C++ |
|---|---|---|---|
| Primary emphasis | Broad conceptual model | Async application behavior | Systems-oriented case study |
| DNS records | Classes and dataclasses | Objects and classes | Structs and classes |
| Cache | TTL-aware dictionary | `Map`-based cache | `unordered_map` |
| Async behavior | Primarily conceptual | Explicit `async`/`await` | Synchronous simulation |
| Time testing | Fake clock | Fake clock | `steady_clock` |
| Error handling | Exceptions and status objects | Exceptions and rejected promises | Exceptions and status objects |
| CNAME | Recursive target lookup | Async recursive target lookup | Recursive target lookup |
| Application layer | Demonstrative | Strong emphasis | Explicit application client |
| Performance discussion | Conceptual | Event-driven concerns | Complexity and data structures |
| Systems concerns | Broad overview | Application runtime | Memory, hashing, architecture |

## Practical applications

DNS resolution and caching are relevant to:

- web browsers
- API clients
- cloud services
- microservices
- service discovery
- email infrastructure
- content delivery networks
- enterprise networks
- security monitoring
- observability platforms
- distributed systems
- containerized applications
- load distribution
- infrastructure automation

A modern distributed application can perform thousands or millions of hostname lookups, making resolver behavior and caching operationally significant.

## Real-world resolution example

Suppose an application requests:

`api.example.com.`

The conceptual process is:

`Application`

→ `Stub resolver`

→ `Recursive resolver`

The recursive resolver checks its cache.

If the answer is cached and valid:

`Cache → Application`

If the answer is not cached:

`Recursive resolver → Root`

The root provides a referral toward the relevant TLD.

Then:

`Recursive resolver → TLD`

The TLD provides delegation information for the domain.

Then:

`Recursive resolver → Authoritative server`

The authoritative server provides the requested record.

The resolver stores the answer according to its TTL and returns it to the client.

A subsequent request can often be satisfied directly from the resolver cache.

## Diagnostic command concepts

Common DNS diagnostic commands include:

`nslookup example.com`

`nslookup -type=MX example.com`

`nslookup -type=NS example.com`

`nslookup -type=TXT example.com`

`dig example.com A`

`dig example.com AAAA`

`dig example.com MX`

`dig +trace example.com`

`dig @1.1.1.1 example.com`

`dig -x 192.0.2.1`

The exact command syntax and available options depend on the installed DNS diagnostic utility.

The purpose of these tools is to inspect different stages and properties of DNS resolution rather than merely checking whether a browser can reach a website.

## Design principles demonstrated

The implementations illustrate several general engineering principles.

### Separation of responsibility

The authoritative server, recursive resolver, cache, and application client have different responsibilities.

### Explicit state

Cache entries explicitly track expiration and result status.

### Deterministic testing

Fake clocks and simulated infrastructure make difficult timing and network behavior testable.

### Failure-aware design

The examples distinguish successful resolution, nonexistent names, server failures, refusal, and timeouts.

### Layered architecture

The application does not need to understand root or TLD resolution.

Each component can provide an abstraction to the component above it.

### Data-oriented indexing

DNS caches are naturally indexed by query name and record type.

### Controlled retries

Retries are bounded instead of continuing indefinitely.

## Production relevance

A reliable DNS architecture requires more than resolving names.

Operational decisions include:

- authoritative redundancy
- resolver redundancy
- appropriate TTLs
- DNSSEC policy
- transport security
- monitoring
- alerting
- access control
- failure handling
- delegation management
- cache behavior
- provider security
- capacity planning

The core architectural distinction remains:

**Authoritative DNS serves DNS data for zones. Recursive DNS obtains DNS data for clients. Caching reduces the amount of repeated recursive work.**

These three concepts form the foundation for understanding how domain resolution operates in distributed networks.
