# IP addressing: IPv4, IPv6, public and private IP

## Topic introduction

IP addressing is the network-layer mechanism used to identify endpoints and networks in Internet Protocol communication. An IP address is used by networked systems and routers to determine where packets originate, where they should be delivered, and which network path should be used.

This study covers two major versions of Internet Protocol addressing:

- IPv4, which uses 32-bit addresses
- IPv6, which uses 128-bit addresses

It also examines public and private addressing, CIDR notation, subnetting, route aggregation, special-purpose addresses, NAT, IPv6 address types, routing decisions, address allocation, validation, security considerations, and dual-stack application design.

The three implementations approach the subject differently:

- Python uses the standard `ipaddress` module to provide precise address and network calculations.
- JavaScript implements address parsing and CIDR operations explicitly, making the underlying algorithms visible.
- C++ develops an enterprise-style case study with address classes, routing tables, allocation, access-control rules, IPv6 parsing, and automated tests.

The examples use documentation addresses where an Internet-facing example is required. Documentation ranges are preferable to copying addresses belonging to real infrastructure.

## Fundamental concepts

### What is an IP address?

An IP address is a numerical address used at the network layer. It belongs to an address family and is interpreted together with a prefix or subnet configuration.

An address can be associated with a network interface rather than being treated as a permanent identity for an entire physical device. One machine can have several interfaces and several IP addresses. A single interface can also have multiple addresses, particularly in IPv6 and dual-stack environments.

For example, an IPv4 address can be written as:

`192.168.1.25`

An IPv6 address can be written as:

`2001:db8:1234:5678::25`

The two addresses belong to different address families.

### IPv4

IPv4 uses 32 bits. It is normally represented as four decimal octets separated by periods.

Each octet contains eight bits and can represent values from 0 through 255.

For example:

`192.168.1.25`

can be represented in binary as four groups of eight bits.

The total number of possible IPv4 bit patterns is:

`2^32 = 4,294,967,296`

This is the theoretical address space. It does not mean that every address is available for assignment to ordinary hosts. Various ranges have special purposes, and subnetting determines which addresses belong to particular networks.

### IPv6

IPv6 uses 128 bits.

A fully expanded address contains eight 16-bit hexadecimal groups:

`2001:0db8:0000:0000:0000:ff00:0042:8329`

Leading zeros within each group can be removed:

`2001:db8:0:0:0:ff00:42:8329`

One consecutive sequence of zero groups can be compressed using `::`:

`2001:db8::ff00:42:8329`

The `::` notation may appear only once in an IPv6 address because the number of omitted zero groups would otherwise be ambiguous.

The theoretical IPv6 address space contains:

`2^128`

addresses.

The size of this space fundamentally changes how networks are designed. IPv6 subnet planning generally focuses on hierarchical prefixes and routing architecture rather than conserving individual host addresses.

## Terminology

### Address

The numerical value identifying an IP endpoint within an address family.

### Network

A collection of addresses represented by a prefix. For example, `192.168.1.0/24` describes an IPv4 network.

### Prefix length

The number following the slash in CIDR notation. It specifies how many leading bits belong to the network prefix.

### CIDR

Classless Inter-Domain Routing. CIDR represents networks with explicit prefix lengths instead of relying on the historical IPv4 class system.

### Subnet

A smaller network created by dividing a larger network into multiple prefixes.

### Host portion

The bits remaining after the network prefix. In conventional IPv4 subnetting, these bits determine individual addresses inside the subnet.

### Network address

For a conventional IPv4 subnet, the address in which all host bits are zero.

### Broadcast address

For a conventional IPv4 subnet, the address in which all host bits are one. IPv6 does not use IPv4-style broadcast.

### Public address

An address intended for global Internet routing or other globally reachable addressing contexts. Whether an address is actually reachable depends on routing, filtering, NAT, firewall policy, provider configuration, and the service itself.

### Private address

An address from a range intended for private network use. For IPv4, the commonly recognized private ranges are the RFC 1918 ranges:

`10.0.0.0/8`

`172.16.0.0/12`

`192.168.0.0/16`

Private does not mean confidential or inherently secure.

### NAT

Network Address Translation changes address information as packets cross a translation device.

### PAT

Port Address Translation is a common NAT technique that allows multiple internal connections to share a public IPv4 address by distinguishing flows with transport-layer ports.

### Loopback

An address used by a host to communicate with itself.

IPv4 loopback includes `127.0.0.0/8`, with `127.0.0.1` being the most familiar example.

IPv6 loopback is `::1/128`.

### Link-local

An address intended for communication on the local link.

IPv4 link-local space is `169.254.0.0/16`.

IPv6 link-local addresses are in `fe80::/10`.

### Multicast

A mechanism for one-to-many communication.

IPv4 multicast uses `224.0.0.0/4`.

IPv6 multicast uses `ff00::/8`.

### Dual stack

A system that operates with IPv4 and IPv6 simultaneously.

## CIDR notation

CIDR represents an address and prefix length together.

Examples include:

`192.168.1.0/24`

`10.0.0.0/8`

`172.16.0.0/12`

`2001:db8::/32`

`2001:db8:1234::/48`

The prefix length determines the network boundary.

For IPv4:

`/24` leaves 8 host bits.

The total number of addresses is:

`2^8 = 256`

For a conventional IPv4 subnet, 254 addresses are normally considered usable host addresses because the network and broadcast addresses have special roles.

A `/26` leaves six host bits:

`2^6 = 64`

addresses exist in the prefix, with 62 conventional usable host addresses.

These conventional calculations should not be blindly applied to every IPv4 networking context. Point-to-point links, special-purpose prefixes, infrastructure systems, and operating-system behavior can have different operational rules.

For IPv6:

`/64` leaves 64 bits after the prefix.

That means a `/64` contains:

`2^64`

addresses.

The enormous IPv6 address space means that IPv6 subnet planning generally does not use the same address-conservation mindset that is common with IPv4.

## Historical IPv4 address classes

IPv4 originally used a classful addressing model.

Historically:

- Class A covered first-octet values 1 through 126.
- Class B covered 128 through 191.
- Class C covered 192 through 223.
- Class D covered 224 through 239 and was used for multicast.
- Class E covered 240 through 255 for experimental or reserved purposes.

Classful addressing is historically important but is not the normal basis for modern network planning.

Modern networks use CIDR. An address should therefore not be interpreted as a Class A, B, or C network simply because of its first octet.

The Python implementation demonstrates the historical classes for educational purposes while using CIDR for actual subnet calculations.

## IPv4 subnetting

Subnetting divides a larger network into smaller networks.

Suppose the starting network is:

`192.168.10.0/24`

Changing the prefix to `/26` allocates two additional bits to the network portion.

The resulting networks are:

`192.168.10.0/26`

`192.168.10.64/26`

`192.168.10.128/26`

`192.168.10.192/26`

Each contains 64 addresses.

This is useful when different departments, services, security zones, or physical locations require separate networks.

Subnetting can support:

- address organization
- routing hierarchy
- broadcast-domain separation in IPv4
- security policy boundaries
- fault isolation
- capacity planning
- network administration

Subnetting alone does not provide security. A subnet becomes a meaningful security boundary only when routing, filtering, authentication, or other controls enforce the intended policy.

## Route aggregation

Route aggregation combines compatible network prefixes into a larger summarized prefix.

For example, four aligned networks:

`192.168.0.0/24`

`192.168.1.0/24`

`192.168.2.0/24`

`192.168.3.0/24`

can be represented by:

`192.168.0.0/22`

when the networks are correctly aligned and contiguous.

Aggregation reduces the number of routes that routers need to maintain and can make routing systems more scalable.

Aggregation must preserve the required address boundaries. Arbitrary networks cannot always be represented accurately by one larger prefix without also covering addresses that were not part of the original collection.

The Python and JavaScript implementations demonstrate route collapsing and aggregation concepts. The C++ implementation uses hierarchical routes and longest-prefix matching.

## Longest-prefix matching

When multiple routes match a destination, routers normally select the most specific matching prefix.

Consider:

`0.0.0.0/0`

`10.0.0.0/8`

`10.20.0.0/16`

`10.20.30.0/24`

For destination:

`10.20.30.50`

all four prefixes can match, but `/24` is the longest matching prefix.

The conceptual process is:

1. Examine the destination address.
2. Identify routes whose prefixes contain the destination.
3. Select the matching route with the longest prefix.
4. Forward the packet according to that route.

The C++ case study models this behavior through the `RoutingTable` class. The Python and JavaScript implementations also contain explicit longest-prefix lookup functions.

A simple linear scan is easy to understand but is not the normal high-performance implementation for large production routing tables. Real systems use optimized data structures, specialized forwarding mechanisms, and sometimes hardware-assisted lookup.

## Public and private IPv4 addressing

The RFC 1918 private IPv4 ranges are:

`10.0.0.0/8`

`172.16.0.0/12`

`192.168.0.0/16`

These ranges are commonly used for internal networks.

A typical home network might contain:

`192.168.1.0/24`

with a router such as:

`192.168.1.1`

and internal clients such as:

`192.168.1.25`

A private address can communicate within its private network and with other connected private networks when appropriate routing exists.

A private address is not equivalent to a secret address. Other systems within the relevant network may be able to communicate with it.

### Public IPv4 addresses

Public IPv4 addresses can be used for Internet-facing services or other globally routed purposes.

A public address does not necessarily mean that the host is reachable from every Internet location. Firewalls, ACLs, provider routing, service configuration, NAT, and other controls can prevent reachability.

Similarly, a public address is not automatically malicious or unsafe.

## NAT and PAT

IPv4 address exhaustion contributed to the widespread use of Network Address Translation.

A simplified outbound flow might look like:

Private endpoint:

`192.168.1.25:51500`

Translated endpoint:

`203.0.113.50:40001`

Destination:

`93.184.216.34:443`

The NAT device maintains a mapping between the internal flow and the external representation.

PAT is particularly common in consumer and enterprise networks because multiple private devices can share one public IPv4 address.

NAT terminology includes:

- SNAT, source address translation
- DNAT, destination address translation
- PAT, port address translation

NAT is not the same as a firewall. NAT changes address information and can maintain state, while a firewall makes explicit traffic-control decisions according to security policy.

## Important IPv4 special ranges

Several IPv4 ranges have special purposes.

### Loopback

`127.0.0.0/8`

The most familiar address is:

`127.0.0.1`

Traffic sent to loopback is intended for the local host and does not normally leave through the physical network.

### Link-local

`169.254.0.0/16`

IPv4 hosts can use link-local addressing when ordinary address configuration is unavailable in suitable circumstances.

### Carrier-grade NAT space

`100.64.0.0/10`

This shared address space is commonly associated with Carrier-Grade NAT deployments.

It should not be confused with RFC 1918 private space.

### Documentation ranges

`192.0.2.0/24`

`198.51.100.0/24`

`203.0.113.0/24`

These ranges are intended for documentation and examples.

The implementations use these ranges when an Internet-style example is required so that real infrastructure addresses are not accidentally presented as part of the design.

### Multicast

IPv4 multicast uses:

`224.0.0.0/4`

It supports one-to-many communication rather than ordinary unicast delivery.

## IPv6 notation

IPv6 addresses contain eight 16-bit hexadecimal groups in their fully expanded representation.

For example:

`2001:0db8:0000:0000:0000:ff00:0042:8329`

Leading zeroes in individual groups may be omitted:

`2001:db8:0:0:0:ff00:42:8329`

A consecutive sequence of zero groups may be compressed:

`2001:db8::ff00:42:8329`

The JavaScript and C++ implementations explicitly implement IPv6 parsing and compression to expose the underlying representation.

The Python implementation uses the standard library, which handles IPv6 parsing and canonical representations.

## IPv6 address categories

### Unspecified

`::/128`

The unspecified address represents the absence of a configured address in contexts where the protocol permits it.

### Loopback

`::1/128`

IPv6 loopback is the counterpart to IPv4 loopback.

### Link-local

`fe80::/10`

Link-local IPv6 addresses are intended for communication on the local link.

They are important for IPv6 neighbor discovery and local-link operation.

### Unique local addresses

`fc00::/7`

Unique local address space provides IPv6 addressing intended for local communication.

It is conceptually useful to compare it with private IPv4 addressing, but the two mechanisms should not be treated as exact technical equivalents.

### Multicast

`ff00::/8`

IPv6 uses multicast extensively.

IPv6 does not use IPv4-style broadcast.

Functions that require one-to-many delivery can use multicast instead.

### Global unicast

IPv6 global unicast addresses are generally associated with globally routable addressing.

The commonly recognized global-unicast range begins within `2000::/3`, although address assignment and actual reachability depend on operational routing and allocation policies.

## IPv6 subnetting

An IPv6 organization might receive a `/48` prefix:

`2001:db8:1234::/48`

It can then create `/64` LAN prefixes such as:

`2001:db8:1234:0001::/64`

`2001:db8:1234:0002::/64`

`2001:db8:1234:0003::/64`

A `/48` contains:

`2^(64 - 48) = 65,536`

different `/64` prefixes.

A `/64` contains:

`2^64`

individual addresses.

The large address space makes hierarchical allocation practical.

The C++ implementation demonstrates this design using `IPv6Address` objects and explicit prefix matching.

## IPv6 configuration

IPv6 supports multiple configuration mechanisms.

### Static configuration

An administrator explicitly configures an address and prefix.

### SLAAC

Stateless Address Autoconfiguration allows hosts to form addresses using information advertised by routers.

Router Advertisements provide important network configuration information, including prefix information.

### DHCPv6

DHCPv6 can provide address and configuration information.

SLAAC and DHCPv6 are not necessarily mutually exclusive. IPv6 network behavior depends on the router-advertisement flags and the deployment design.

The Python implementation demonstrates the basic mathematical concept of combining a prefix with an interface identifier.

## IPv4 versus IPv6

| Property | IPv4 | IPv6 |
|---|---|---|
| Address size | 32 bits | 128 bits |
| Common notation | Dotted decimal | Colon-separated hexadecimal |
| Example | `192.168.1.25` | `2001:db8::25` |
| Broadcast | Supported | Not used |
| Multicast | `224.0.0.0/4` | `ff00::/8` |
| Loopback | `127.0.0.0/8` | `::1/128` |
| Link-local | `169.254.0.0/16` | `fe80::/10` |
| Private/local addressing | RFC 1918 | ULA `fc00::/7` |
| Common LAN prefix | `/24` is common in many IPv4 environments | `/64` is common in IPv6 LAN design |
| NAT | Widely deployed | Not fundamental to IPv6 addressing |

The differences are architectural rather than merely syntactic.

IPv6 is not simply IPv4 with more address values. It also changes aspects of header design, multicast usage, fragmentation behavior, address configuration, neighbor discovery, and subnet planning.

## IPv4 packet header concepts

An IPv4 header contains fields including:

- Version
- IHL
- DSCP and ECN
- Total Length
- Identification
- Flags
- Fragment Offset
- TTL
- Protocol
- Header Checksum
- Source Address
- Destination Address
- Options

The source and destination fields contain the 32-bit IPv4 addresses.

TTL, or Time To Live, limits the number of router hops through which a packet can pass before it is discarded.

The Protocol field identifies the next-layer protocol, such as TCP or UDP.

IPv4 permits fragmentation under specified conditions. Modern network engineering generally aims to avoid unnecessary fragmentation through suitable MTU and packet-size management.

The Python implementation demonstrates the 32-bit representation of an IPv4 address.

## IPv6 packet header concepts

The IPv6 base header contains:

- Version
- Traffic Class
- Flow Label
- Payload Length
- Next Header
- Hop Limit
- Source Address
- Destination Address

IPv6 uses extension headers for optional functionality.

The `Next Header` field identifies either an extension header or an upper-layer protocol.

`Hop Limit` performs a role similar to IPv4 TTL.

A major difference concerns fragmentation. IPv6 routers do not fragment packets in transit. Fragmentation is handled by the sending endpoint when the protocol conditions require it.

## Python implementation

The Python program uses the standard-library `ipaddress` module.

This module provides robust parsing and network calculations without requiring an external dependency.

The implementation demonstrates:

- IPv4 parsing
- IPv6 parsing
- IPv4 integer representation
- IPv6 integer representation
- binary IPv4 representation
- CIDR prefix handling
- subnet generation
- network and broadcast calculation
- address classification
- private address detection
- special-purpose ranges
- route aggregation
- longest-prefix matching
- network membership
- address allocation
- DNS resolution
- dual-stack modeling
- security considerations
- capacity planning
- error handling

### Why the Python implementation uses `ipaddress`

IP address syntax has many details that are easy to mishandle with ordinary string operations.

For example, validating IPv4 by checking whether a string contains three periods is insufficient.

The standard `ipaddress` implementation correctly handles numeric boundaries and IPv6 syntax.

For educational demonstrations, explicit algorithms are also included where they clarify the concept.

### Python address validation

The function `validate_ip_address` attempts to parse an address and returns either an address object or `None`.

The program tests valid and invalid examples, including malformed IPv4 and IPv6 strings.

### Python network calculation

The function `calculate_network_details` accepts an address and prefix and reports:

- network
- netmask
- hostmask
- prefix length
- total addresses
- first address
- last address

For conventional IPv4 networks it also demonstrates the traditional first and last usable host addresses.

### Python address allocation

The `IPv4Pool` class models a small address allocator.

It demonstrates:

- free address tracking
- allocation
- release
- reuse
- exhaustion handling
- allocation state

It is intentionally not a DHCP implementation. Real DHCP systems have leases, timers, client identifiers, conflict detection, persistence, authorization, and many additional protocol behaviors.

## JavaScript implementation

The JavaScript implementation takes a different approach.

Node.js does not provide a built-in equivalent of Python's `ipaddress` module with the same API, so the program implements important calculations directly.

This makes several internal mechanisms visible.

### IPv4 parsing

`parseIPv4`:

- splits the address into four components
- verifies numeric syntax
- checks the 0 through 255 range
- returns the four octets

`ipv4ToInteger` converts the four octets into a 32-bit numeric representation.

`integerToIPv4` performs the reverse operation.

### IPv4 CIDR calculations

The JavaScript file includes:

- `ipv4MaskFromPrefix`
- `ipv4NetworkAddress`
- `ipv4BroadcastAddress`
- `ipv4Contains`

These functions show how the prefix length becomes a bit mask and how a network address can be calculated using a bitwise AND operation.

### IPv6 arithmetic

JavaScript's normal `Number` type cannot safely represent every integer in the 128-bit IPv6 space.

The implementation therefore uses `BigInt`.

`ipv6ToBigInt` converts an IPv6 address into a 128-bit integer.

`bigIntToIPv6` converts it back into textual form.

This is an important implementation distinction between IPv4 and IPv6.

### IPv6 compression

The `compressIPv6` function searches for the longest consecutive run of zero groups and replaces it with `::` when appropriate.

This illustrates why IPv6 string formatting requires more than simply removing leading zeroes.

### DNS

The Node.js implementation uses the built-in `dns` module to perform a lookup for `example.com`.

The result can contain IPv4 and IPv6 addresses.

DNS and IP addressing solve different problems:

- DNS maps names to resource records.
- IP addresses are used by the network layer for packet delivery.

A hostname should therefore not be treated as if it were itself an IP address.

### Browser considerations

JavaScript behaves differently in browsers and on servers.

Node.js has operating-system networking APIs such as the `dns` module.

Browser JavaScript operates under browser security and privacy boundaries. Web applications normally work with hostnames, URLs, and application-level network APIs rather than unrestricted access to local interface configuration.

## C++ enterprise case study

### Problem being modeled

The C++ program models a simplified enterprise network.

The organization has:

- internal IPv4 networks
- public-facing addressing examples
- departmental subnets
- a routing table
- address allocation
- access-control rules
- IPv6 prefixes
- dual-stack design requirements

The goal is to demonstrate how IP addressing concepts become components of a larger networking system.

### `IPv4Address`

The `IPv4Address` class stores an address as a 32-bit unsigned integer.

This provides efficient comparison and bitwise network calculations.

It supports:

- parsing dotted-decimal text
- integer conversion
- dotted-decimal output
- binary output
- comparison

For example:

`192.168.1.25`

is stored as one 32-bit value.

### `IPv4Network`

The `IPv4Network` class represents a CIDR network.

It calculates:

- network address
- prefix length
- mask
- broadcast address
- total addresses
- conventional usable addresses
- network membership

The network address is calculated conceptually as:

`address AND subnet mask`

The broadcast address is calculated using the inverse of the mask for the host bits.

### `RoutingTable`

The `RoutingTable` class contains a collection of `Route` objects.

Each route contains:

- a network
- a next-hop address
- an interface name

The routing table implements longest-prefix matching.

For example, if both `/8` and `/24` routes match a destination, the `/24` route is selected because it is more specific.

The implementation uses a linear scan because that keeps the algorithm readable. A production routing implementation would require more specialized data structures and forwarding mechanisms.

### `AddressAllocator`

The `AddressAllocator` class models a basic IPv4 address pool.

It maintains:

- a network
- free addresses
- allocated addresses
- device-to-address mappings

It supports allocation and release.

This demonstrates the relationship between subnet capacity and resource management.

The class is intentionally simplified. A real DHCP service must handle lease expiration, persistent state, client identification, address conflicts, reservations, retransmission behavior, and protocol-specific message handling.

### `AccessController`

The `AccessController` demonstrates how address prefixes can participate in policy evaluation.

Rules include:

- source network
- service
- allow or deny decision
- description

The program intentionally uses longest-prefix matching so that a specific subnet can override a broader rule.

For example, a broad internal rule may allow database access while a more-specific laboratory subnet rule denies it.

This demonstrates an important principle:

A more-specific policy can have precedence over a broad policy when the policy system is explicitly designed that way.

Actual firewall behavior depends on the particular product, protocol, rule ordering, state model, and configuration.

### IPv6 class

The `IPv6Address` class stores eight 16-bit groups.

It demonstrates:

- IPv6 parsing
- expanded representation
- compressed representation
- prefix matching
- loopback detection
- unspecified-address detection
- link-local detection
- unique-local detection
- multicast detection

The implementation does not attempt to reproduce every production IPv6 parser feature. In particular, the educational parser explicitly rejects IPv4-embedded IPv6 notation.

## IPv6 compression algorithm

The C++ implementation searches for the longest consecutive sequence of zero groups.

For example:

`2001:0db8:0000:0000:0000:0000:0000:0001`

can be represented as:

`2001:db8::1`

A single zero group is normally not compressed because `::` is intended to replace a sequence of zero groups and should be used according to canonical IPv6 formatting rules.

When more than one zero sequence has the same length, canonical formatting selects the appropriate first longest sequence.

## Address validation

Validation is important because malformed input can otherwise propagate into:

- routing decisions
- firewall rules
- logs
- configuration
- database records
- APIs
- access-control systems

The implementations reject examples such as:

`192.168.1.999`

`192.168.1`

`192.168.one.1`

`2001:db8:::1`

and other malformed forms.

Application code should use a standards-aware parser rather than a simple regular expression whenever correctness matters.

Regular expressions can help with preliminary syntax checks, but IP parsing involves numerical bounds and IPv6-specific structure that a complete parser must handle.

## Edge cases

### `0.0.0.0`

The meaning depends on context.

It can represent an unspecified IPv4 address or be used as a wildcard address when a service binds to all local IPv4 interfaces.

It should not automatically be treated as a normal host address.

### `255.255.255.255`

This is the IPv4 limited broadcast address.

It has a special role and should not be treated as an ordinary unicast host address.

### `::`

This is the IPv6 unspecified address.

### `::1`

This is IPv6 loopback.

### `127.0.0.1`

This is the most familiar IPv4 loopback address.

### `169.254.x.x`

This belongs to IPv4 link-local space.

### `fe80::`

Addresses in the IPv6 link-local range require local-link scope and can have special interface-selection considerations in real operating systems.

## Important distinctions

### IP address versus MAC address

An IP address operates at the network layer.

A MAC address is associated with link-layer communication.

They solve different problems and should not be treated as interchangeable identifiers.

### Private versus public

Private and public describe address-space and routing usage.

They do not directly describe whether a system is trustworthy, secure, encrypted, or physically isolated.

### NAT versus firewall

NAT translates address information.

A firewall enforces traffic policy.

A device can perform both functions, but the functions remain conceptually distinct.

### DNS versus IP

DNS maps names to resource records.

IP addresses are used by the IP layer.

DNS is not a replacement for IP addressing.

### IPv4 classes versus CIDR

Class A, B, and C addressing is historical.

CIDR is the modern method for representing IPv4 prefixes.

### IPv4 broadcast versus IPv6 multicast

IPv4 supports broadcast.

IPv6 does not use broadcast. Multicast is used for many one-to-many communication requirements.

### IPv4 fragmentation versus IPv6 fragmentation

IPv4 allows routers to fragment packets under appropriate conditions.

IPv6 routers do not fragment packets in transit. Fragmentation is handled by the sending endpoint.

## Performance considerations

Address arithmetic is normally inexpensive.

The performance challenge appears when a system must search large numbers of prefixes repeatedly.

A simple longest-prefix algorithm can scan every route:

`O(R)`

where `R` is the number of routes.

That is adequate for educational code and small data sets.

Production routing systems use specialized structures such as:

- radix trees
- Patricia tries
- prefix tries
- optimized routing tables
- hardware forwarding tables

These structures reduce the work required for repeated prefix lookup.

Address allocation also has performance implications. A simple vector-based allocator may require linear removal or search operations. Production allocation systems use more sophisticated structures, persistent state, lease tracking, and conflict management.

## Security considerations

IP addresses should not be treated as identities by themselves.

An internal private address does not prove that a request is trustworthy.

A public address does not prove that a request is malicious.

Important security considerations include:

- validating address input
- validating prefix lengths
- separating IPv4 and IPv6 policy
- checking dual-stack firewall behavior
- avoiding stale IP allowlists
- avoiding accidental exposure through IPv6
- treating NAT separately from firewall enforcement
- using appropriate logging
- controlling management networks
- avoiding real production addresses in documentation and test data
- considering address changes when designing authentication and authorization

### IPv6 security

A security architecture that was created only for IPv4 may not automatically protect IPv6.

Dual-stack deployments therefore require:

- IPv4 firewall policy
- IPv6 firewall policy
- IPv4 routing validation
- IPv6 routing validation
- IPv4 monitoring
- IPv6 monitoring
- application testing on both families

Disabling or ignoring IPv6 is not equivalent to securing it.

## Implementation considerations

### Python

Python provides high-level standard-library support for IP addressing.

This makes it appropriate for:

- network planning scripts
- configuration validation
- automation
- address inventory
- testing
- network analysis

The `ipaddress` module reduces the risk of implementing parsing rules incorrectly.

### JavaScript

JavaScript is useful when address information is part of:

- web applications
- dashboards
- configuration interfaces
- network-management interfaces
- server-side Node.js applications

The JavaScript implementation demonstrates why `BigInt` is necessary when representing the full 128-bit IPv6 address space.

### C++

C++ is useful when networking software requires:

- explicit memory representation
- high performance
- low-level control
- custom packet-processing systems
- routing infrastructure
- embedded systems
- network appliances

The C++ case study uses integer representations and explicit bit operations to make the relationship between prefixes and addresses clear.

## Common mistakes

### Assuming every `192.168.x.x` address is the same network

`192.168.1.1` and `192.168.2.1` belong to different `/24` networks, even though both are private addresses.

The prefix determines the network boundary.

### Assuming private means secure

Private addressing is not a substitute for authentication, encryption, segmentation, or firewall controls.

### Assuming public means reachable

A public address can still be blocked by a firewall, routing policy, provider configuration, or service configuration.

### Using classful assumptions

Modern subnetting should be based on CIDR prefixes rather than historical A/B/C classes.

### Treating IPv6 as merely a longer IPv4 string

IPv6 introduces different notation, address categories, multicast behavior, configuration mechanisms, header behavior, and fragmentation rules.

### Assuming `/24` always means 254 usable hosts

That is the conventional calculation for an ordinary IPv4 `/24`, not a universal rule for every context.

### Forgetting IPv6

A system that supports IPv6 can have network paths that are different from its IPv4 paths.

### Using ordinary numeric JavaScript values for all IPv6 arithmetic

The JavaScript `Number` type cannot exactly represent every 128-bit integer. The implementation uses `BigInt` for IPv6 numerical operations.

### Using simple string comparison for network membership

IP addresses are numerical structures with prefix semantics. String comparison does not correctly implement CIDR membership.

### Treating IP addresses as permanent identities

Addresses can change, especially with dynamic allocation, mobility, provider changes, privacy mechanisms, and different network configurations.

## Practical applications

IP addressing knowledge is used in:

- enterprise LAN design
- data-center networks
- cloud networking
- Internet service providers
- home networks
- VPNs
- firewalls
- routers
- load balancers
- application servers
- network monitoring
- security engineering
- infrastructure automation
- DNS architecture
- container networking
- Kubernetes networking
- service discovery
- network access control
- incident investigation
- network capacity planning

The same principles appear across these environments, although the specific implementation and management systems differ.

## Example enterprise design

A hypothetical organization can allocate:

`10.50.0.0/16`

for internal IPv4 addressing.

The organization can then divide it into departmental networks.

For example:

- Engineering: a suitable subnet based on host capacity
- Finance: a smaller subnet
- Operations: a larger subnet
- Research: a larger subnet

A separate IPv6 allocation can use a documentation prefix for educational modeling:

`2001:db8:1234::/48`

The organization can then assign `/64` prefixes to individual LANs.

A routing hierarchy can include:

`0.0.0.0/0`

for the default route,

`10.0.0.0/8`

for a broad internal range,

`10.20.0.0/16`

for a more-specific region,

and:

`10.20.30.0/24`

for a specific server network.

The longest-prefix rule determines which route applies to a destination.

## Testing strategy

The three implementations include testable operations such as:

- valid IPv4 parsing
- invalid IPv4 rejection
- IPv4 integer conversion
- network calculation
- broadcast calculation
- IPv4 network membership
- IPv6 expansion
- IPv6 compression
- IPv6 prefix matching
- loopback classification
- link-local classification
- private address classification
- longest-prefix routing

A robust production implementation should expand this with:

- boundary-value tests
- malformed-input tests
- regression tests
- randomized tests
- property-based tests
- interoperability tests
- dual-stack tests
- configuration validation tests
- performance benchmarks

## Design principles demonstrated by the case study

### Represent addresses numerically when performing calculations

IPv4 can naturally be represented by a 32-bit unsigned integer.

IPv6 requires a 128-bit representation. The JavaScript implementation uses `BigInt`, while the C++ implementation represents IPv6 as eight 16-bit groups.

### Separate parsing from policy

Parsing answers whether an address is structurally valid.

Classification determines what kind of address it is.

Routing determines where traffic should go.

Security policy determines whether traffic should be permitted.

These are related but separate responsibilities.

### Make prefix length explicit

A raw address such as `192.168.1.25` does not completely describe its network membership.

`192.168.1.25/24` supplies the network boundary.

### Prefer hierarchical addressing

Hierarchical prefixes allow organizations to divide networks according to departments, locations, services, or other architectural boundaries.

This can also make route aggregation possible.

### Design for both address families when required

Applications, firewalls, monitoring systems, databases, APIs, and logging systems should not assume that all addresses are IPv4 if the environment supports IPv6.

## Limitations of these implementations

These programs are educational implementations rather than production routing stacks or DHCP servers.

They intentionally omit many protocol and operating-system details.

The Python implementation delegates parsing and classification to the standard library.

The JavaScript implementation implements a useful subset of IPv4 and IPv6 functionality directly and explicitly leaves some advanced IPv6 textual forms outside its parser.

The C++ implementation focuses on address representation, routing, allocation, policy evaluation, and IPv6 prefix handling rather than implementing complete IP, TCP, UDP, DHCP, ICMP, Neighbor Discovery, or routing protocols.

A production networking system would require significantly more functionality, including protocol state machines, concurrency, packet I/O, timers, persistence, error recovery, operating-system integration, security controls, observability, and interoperability testing.

## Files and their roles

### Python file

The Python program is the broadest educational reference.

It uses `ipaddress` for accurate address operations and demonstrates concepts ranging from beginner-level representation to network planning, routing, address allocation, validation, security, and performance.

### JavaScript file

The JavaScript program emphasizes explicit implementation.

It demonstrates how IPv4 masks, IPv4 integer conversion, IPv6 compression, IPv6 `BigInt` arithmetic, CIDR membership, routing lookup, DNS resolution, and dual-stack data structures can be implemented in a JavaScript environment.

### C++ file

The C++ program presents the subject as a technical enterprise case study.

Its principal components are:

- `IPv4Address`
- `IPv4Network`
- `IPv6Address`
- `RoutingTable`
- `AddressAllocator`
- `AccessController`

Together these classes model address storage, network boundaries, routing decisions, address assignment, and address-based policy evaluation.

## Complexity considerations

For an IPv4 address, parsing contains a fixed maximum of four octets, so its computational work is effectively constant with respect to the address length.

IPv6 parsing contains a fixed maximum of eight 16-bit groups in the representation modeled by these programs, so it is also effectively constant-sized.

The simple longest-prefix routing algorithm scans every route, giving:

`O(R)`

lookup complexity for `R` routes.

A production routing implementation can use prefix-specific data structures to reduce lookup work.

The educational address allocator can also use linear structures. Production allocators normally require more sophisticated management because address pools can contain very large numbers of addresses and must support leases, reservations, persistence, and concurrent clients.

## Real-world relevance

IP addressing is one of the foundational concepts behind computer networking.

Understanding the distinction between an address and a network prefix makes it possible to reason about:

- why two machines can communicate directly
- why a router is required between different networks
- how subnet boundaries are calculated
- why private IPv4 addresses commonly appear inside organizations
- how NAT permits shared public IPv4 addressing
- why IPv6 does not require the same address-conservation techniques
- how routers choose among overlapping prefixes
- why IPv6 must be included in security policy
- how network administrators plan address hierarchies
- how software should validate and store IP addresses

The Python, JavaScript, and C++ implementations expose the same underlying addressing principles at different abstraction levels: Python emphasizes reliable high-level network manipulation, JavaScript makes the algorithms visible in an application-oriented environment, and C++ models the mechanisms as components of a larger network system.
