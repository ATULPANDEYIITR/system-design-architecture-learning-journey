# IP addressing: IPv4, IPv6, public and private IP

## Introduction

IP addressing is the addressing system used by the Internet Protocol layer to identify network-layer endpoints and determine how packets can be delivered between networks.

The two major Internet Protocol versions are IPv4 and IPv6.

IPv4 uses 32-bit addresses and represents them commonly as four decimal octets, such as `192.168.1.10`.

IPv6 uses 128-bit addresses and represents them as hexadecimal groups separated by colons, such as `2001:db8:1234::10`.

IP addressing involves more than memorizing address formats. A practical understanding requires knowledge of network prefixes, subnet masks, CIDR notation, host capacity, routing, private addressing, public addressing, special-purpose addresses, IPv6 address types, address allocation, and the relationship between addressing and network security.

The three implementations in this repository approach the subject differently:

- The Python program is a broad educational implementation using the standard `ipaddress` library for reliable address calculations.
- The JavaScript program implements important IPv4 and IPv6 operations directly, demonstrating integer manipulation, validation, `BigInt`, classes, error handling, and application-level logic.
- The C++ program develops an industry-style network planning case study with custom IPv4 and IPv6 representations, CIDR calculations, VLSM allocation, route selection, validation, and automated tests.

## Fundamental terminology

### IP address

An IP address is a value used by the Internet Protocol layer to identify an address associated with an interface or endpoint.

An address has meaning together with a prefix or subnet context. For example, `192.168.10.25/24` indicates that the first 24 bits identify the network prefix while the remaining 8 bits belong to the host portion.

An address by itself does not necessarily tell the complete network structure.

### IPv4

IPv4 is the fourth version of the Internet Protocol. Its addresses contain 32 bits.

A common representation is dotted decimal:

`192.168.10.25`

The four decimal values are octets. Each octet contains 8 bits.

The theoretical IPv4 address space contains:

`2^32 = 4,294,967,296`

possible 32-bit values.

This number is much smaller than the number of addresses available in IPv6.

### IPv6

IPv6 uses 128-bit addresses.

A conventional expanded IPv6 address contains eight groups of four hexadecimal digits:

`2001:0db8:0000:0000:0000:0000:0000:0001`

The same address can normally be written in compressed form:

`2001:db8::1`

The theoretical IPv6 address space contains `2^128` possible values.

### Network prefix

The network prefix identifies the portion of an IP address associated with a particular network or routing boundary.

For example:

`192.168.10.0/24`

The `/24` means that 24 of the 32 IPv4 bits form the prefix.

### Host portion

The bits remaining after the network prefix are available for host addressing.

For an IPv4 `/24`:

- Total bits: 32
- Network bits: 24
- Host bits: 8
- Total address combinations: `2^8 = 256`

For an ordinary LAN subnet, the network address and broadcast address are traditionally reserved, leaving 254 usable host addresses.

### CIDR

CIDR stands for Classless Inter-Domain Routing.

CIDR represents an address together with a prefix length:

`192.168.10.0/24`

CIDR replaced the rigid class-based allocation model that historically divided IPv4 into Classes A, B and C.

Modern networks can use prefixes such as `/19`, `/22`, `/27`, `/29` and `/30`, depending on addressing requirements.

## IPv4 representation

The Python implementation demonstrates conversion between dotted-decimal IPv4 and binary representation.

For example:

`192.168.1.1`

can be represented as:

`11000000 10101000 00000001 00000001`

The four octets are:

- `192` = `11000000`
- `168` = `10101000`
- `1` = `00000001`
- `1` = `00000001`

The JavaScript implementation performs the same conversion using unsigned 32-bit integer operations.

This demonstrates an important implementation issue in JavaScript: ordinary bitwise operators operate on signed 32-bit integers. The unsigned right-shift operator and `>>> 0` conversion are therefore important when working with the complete IPv4 range.

The C++ implementation stores an IPv4 address in `std::uint32_t`, which directly represents the 32-bit address value.

## IPv4 subnet masks

A subnet mask indicates which IPv4 bits belong to the network prefix.

Common examples include:

| CIDR | Subnet mask |
|---|---|
| `/8` | `255.0.0.0` |
| `/16` | `255.255.0.0` |
| `/20` | `255.255.240.0` |
| `/24` | `255.255.255.0` |
| `/25` | `255.255.255.128` |
| `/26` | `255.255.255.192` |
| `/27` | `255.255.255.224` |
| `/28` | `255.255.255.240` |
| `/30` | `255.255.255.252` |
| `/32` | `255.255.255.255` |

A prefix length is generally easier to reason about than the dotted-decimal mask because it directly specifies the number of network bits.

## IPv4 subnet calculation

Consider:

`192.168.10.25/24`

The `/24` mask is:

`255.255.255.0`

The containing network is:

`192.168.10.0/24`

The broadcast address is:

`192.168.10.255`

The traditional usable host range is:

`192.168.10.1` through `192.168.10.254`

The Python program calculates these values using the standard `ipaddress.IPv4Network` implementation.

The JavaScript program performs the calculation by converting the address and mask into 32-bit integers and applying a bitwise AND operation.

The C++ program implements the same mechanism explicitly using `std::uint32_t`.

The fundamental operation is:

`network = address AND subnet-mask`

The broadcast address can be obtained by setting all host bits to one.

## Host capacity

The number of host bits determines the number of address combinations.

If `h` bits are available for hosts:

`2^h`

addresses are possible.

For a conventional IPv4 subnet with a network address and broadcast address:

`usable hosts = 2^h - 2`

Examples:

| Prefix | Host bits | Total addresses | Traditional usable hosts |
|---|---:|---:|---:|
| `/24` | 8 | 256 | 254 |
| `/25` | 7 | 128 | 126 |
| `/26` | 6 | 64 | 62 |
| `/27` | 5 | 32 | 30 |
| `/28` | 4 | 16 | 14 |
| `/29` | 3 | 8 | 6 |
| `/30` | 2 | 4 | 2 |

The formula is useful for planning but should not be applied blindly to `/31` and `/32`.

A `/31` is commonly used for point-to-point IPv4 links and has two addresses available for the two endpoints.

A `/32` identifies a single IPv4 address and is commonly used for host routes, loopback addresses, and other specific routing purposes.

## IPv4 address classes

Traditional IPv4 classful addressing used Classes A, B and C for fixed network and host boundaries.

The historical structure included:

- Class A
- Class B
- Class C
- Class D for multicast
- Class E for experimental or reserved purposes

Classful addressing is no longer the normal basis for modern network design.

CIDR allows arbitrary prefix lengths and therefore provides much more flexible address allocation.

Understanding the historical classes remains useful because older documentation and educational material may still refer to them.

## Private IPv4 addresses

The traditional private IPv4 ranges are:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

These ranges are widely used for internal networks.

Example:

`192.168.1.20`

could be the address of a laptop on a home or corporate LAN.

Private addressing is not the same as security.

A private address does not automatically mean:

- encrypted communication
- authenticated communication
- authorization
- malware protection
- firewall protection
- isolation from every other internal host

Security must be implemented through appropriate network controls and application controls.

## Public IPv4 addresses

A public or globally routable IPv4 address is an address intended to be reachable through the global Internet routing system, subject to routing policy and security controls.

An ordinary example used in documentation is often preferable to using a real organization's production address.

The Python program uses standard library classification facilities where appropriate. The JavaScript and C++ implementations demonstrate explicit classification of important private and special-purpose ranges.

The term "public IP" should not be interpreted as "every device using this address is directly accessible from the Internet." Firewalls, NAT, routing policy, cloud security groups, load balancers and other controls can affect reachability.

## Special IPv4 addresses

Several IPv4 ranges and values have special purposes.

### Loopback

The loopback range is:

`127.0.0.0/8`

A common loopback address is:

`127.0.0.1`

Traffic directed to loopback remains within the local host.

### Link-local

IPv4 link-local addresses use:

`169.254.0.0/16`

They can be used for local-link communication when normal address configuration is unavailable or unsuitable.

### Multicast

IPv4 multicast uses:

`224.0.0.0/4`

Multicast is different from unicast addressing because traffic can be delivered to multiple interested receivers.

### Limited broadcast

`255.255.255.255` is the IPv4 limited broadcast address.

Broadcast has important differences from unicast and multicast and does not have a direct equivalent in IPv6.

### Unspecified address

`0.0.0.0` can represent an unspecified address in appropriate contexts.

It is also associated with the IPv4 default route when written as:

`0.0.0.0/0`

The exact meaning depends on context.

## VLSM

VLSM stands for Variable Length Subnet Masking.

VLSM allows different portions of an address space to be divided into different subnet sizes.

Consider an organization with:

- Engineering: 100 hosts
- Security Operations: 50 hosts
- Databases: 25 hosts
- Management: 10 hosts
- Router links: 2 hosts

Giving every department the same `/24` network would waste a large amount of address space.

VLSM allows the requirements to be matched to appropriate subnet sizes.

A typical sizing process is:

1. Determine the required number of usable addresses.
2. Determine the number of host bits needed.
3. Select the smallest suitable prefix.
4. Align the subnet to its valid boundary.
5. Allocate the subnet.
6. Continue with the next requirement.

The implementations sort requirements from largest to smallest before allocation. This reduces fragmentation in the simple sequential allocator used by the examples.

Production IP address management requires additional considerations such as reserved ranges, VLAN design, routing summarization, DHCP, static allocations, overlapping requests, documentation, ownership, and change control.

## Subnet membership

An address belongs to a network when its network-prefix bits match the network prefix.

For IPv4, the basic calculation is:

`address AND mask`

compared with:

`network AND mask`

For example, an address such as `192.168.10.25` belongs to `192.168.10.0/24`, while `192.168.11.25` does not.

The Python implementation delegates the operation to the standard library.

The JavaScript implementation calculates membership using 32-bit operations.

The C++ implementation performs the operation directly on `std::uint32_t`.

## Longest-prefix matching

Routers can have multiple routes that match a destination.

For example:

- `10.0.0.0/8`
- `10.20.0.0/16`
- `10.20.30.0/24`
- `10.20.30.128/25`

A destination such as `10.20.30.200` belongs to all four networks.

The routing decision uses the most specific matching prefix.

The `/25` route is more specific than `/24`, which is more specific than `/16`, which is more specific than `/8`.

This is called longest-prefix matching.

The C++ case study implements a route table and searches for the route with the greatest prefix length among the matching routes.

The simple implementation has linear lookup behavior, approximately `O(N)` for `N` routes.

Real routing systems use highly optimized data structures and hardware-assisted mechanisms to handle large route tables efficiently.

## NAT and private IPv4

IPv4 networks frequently use private addresses internally and Network Address Translation at an edge.

A simple architecture might contain:

- Client: `192.168.1.20`
- Database: `192.168.1.30`
- Router LAN: `192.168.1.1`
- Router WAN: public IPv4 address

Port Address Translation, commonly called NAT overload, allows multiple internal connections to share an external IPv4 address while maintaining separate transport-layer flows.

NAT and firewalling are separate concepts.

NAT changes address or port information according to translation rules.

A firewall enforces traffic policy.

NAT should therefore not be treated as a replacement for authentication, authorization, encryption, or a properly designed firewall.

## IPv4 limitations

The fundamental limitation of IPv4 addressing is the size of its address space.

There are only 32 address bits.

The original Internet design has evolved through multiple mechanisms to extend the practical usefulness of IPv4, including:

- subnetting
- CIDR
- address allocation policies
- private addressing
- NAT
- DHCP
- address reclamation
- route aggregation

These mechanisms improve operational efficiency but do not change the fundamental size of the IPv4 address space.

## IPv6 representation

IPv6 contains 128 bits.

The expanded form contains eight 16-bit hexadecimal groups.

Example:

`2001:0db8:0000:0000:0000:0000:0000:0001`

IPv6 supports zero compression.

The same address can be represented as:

`2001:db8::1`

There are two important formatting rules.

First, leading zeroes inside a hexadecimal group may be removed.

For example:

`0db8` becomes `db8`.

Second, one consecutive sequence of zero groups can be replaced with `::`.

For example:

`2001:db8:0:0:0:0:0:1`

becomes:

`2001:db8::1`

The `::` notation can occur only once because otherwise the number of omitted zero groups would be ambiguous.

The C++ and JavaScript implementations explicitly parse and compress IPv6 addresses to demonstrate the underlying mechanics.

## IPv6 address types

Important IPv6 address categories include:

| Range | Purpose |
|---|---|
| `2000::/3` | Global unicast range |
| `fe80::/10` | Link-local unicast |
| `fc00::/7` | Unique-local addressing |
| `ff00::/8` | Multicast |
| `::1/128` | Loopback |
| `::/128` | Unspecified |

IPv6 does not use traditional broadcast addressing.

Multicast provides mechanisms for sending traffic to groups of receivers.

### Link-local addresses

Link-local addresses use:

`fe80::/10`

They are associated with communication on a local link and are important to IPv6 operation.

A link-local address is not equivalent to a global Internet address.

### Unique-local addresses

Unique-local IPv6 addressing uses:

`fc00::/7`

These addresses are intended for private-style internal addressing.

They should not be treated as a direct replacement for every IPv4 private-network design because IPv6 architecture and routing behavior differ.

### Multicast

IPv6 multicast uses:

`ff00::/8`

Multicast replaces several uses for which IPv4 networks historically relied on broadcast.

### Loopback

IPv6 loopback is:

`::1`

It serves a purpose analogous to IPv4 `127.0.0.1`.

### Unspecified

IPv6 unspecified address:

`::`

This represents the absence of a specified address in contexts where that semantic is defined.

## IPv6 prefix lengths

IPv6 prefixes use the same general CIDR-style notation:

`2001:db8:1234::/48`

A common network design assigns `/64` prefixes to individual IPv6 subnets.

A `/48` can be divided into:

`2^(64 - 48) = 2^16 = 65,536`

distinct `/64` subnets.

This is one reason IPv6 subnet planning should not be approached as though IPv6 were simply a larger version of IPv4.

The number of addresses inside an IPv6 `/64` is:

`2^64`

which is vastly larger than a conventional IPv4 subnet.

The JavaScript implementation uses `BigInt` for IPv6 address-count calculations because JavaScript's ordinary `Number` type cannot represent every integer exactly at this magnitude.

## IPv6 interface addressing

A `/64` subnet contains 64 prefix bits and 64 remaining bits.

The remaining portion can be used by address-configuration mechanisms to form interface addresses.

IPv6 address formation can involve mechanisms such as:

- manual configuration
- DHCPv6
- SLAAC
- privacy-related interface addressing mechanisms

The exact mechanism depends on the network design and operating-system configuration.

## Documentation addresses

The following IPv4 ranges are commonly used in technical documentation:

- `192.0.2.0/24`
- `198.51.100.0/24`
- `203.0.113.0/24`

IPv6 documentation uses:

`2001:db8::/32`

These addresses are useful in examples because documentation should avoid accidentally exposing or implying dependence on real production addresses.

The implementations use documentation addresses when demonstrating public-style address structures.

## IPv4 versus IPv6

| Property | IPv4 | IPv6 |
|---|---|---|
| Address size | 32 bits | 128 bits |
| Common notation | Dotted decimal | Hexadecimal colon notation |
| Address space | `2^32` | `2^128` |
| Broadcast | Supported | No traditional broadcast |
| Multicast | `224.0.0.0/4` | `ff00::/8` |
| Loopback | `127.0.0.1` within `127.0.0.0/8` | `::1` |
| Link-local | `169.254.0.0/16` | `fe80::/10` |
| Private-style addressing | RFC1918 ranges | Unique-local `fc00::/7` |
| Common LAN prefix | Depends on design | `/64` is common |
| NAT | Very widely deployed | Not an inherent requirement |
| Address representation | 4 decimal octets | 8 hexadecimal groups |

IPv6 should not be viewed simply as "IPv4 with more addresses."

The addressing architecture, special address behavior, multicast model, configuration mechanisms, neighbor discovery mechanisms, packet structure, and operational practices differ.

## Dual stack

Dual stack means a host or network operates with IPv4 and IPv6 simultaneously.

For example, a server could have:

- IPv4: `192.168.10.20`
- IPv6: `2001:db8:10:20::20`

DNS can provide both:

- an A record for IPv4
- an AAAA record for IPv6

A dual-stack deployment requires operational support for both protocols.

This includes:

- routing
- firewalls
- monitoring
- logging
- access controls
- DNS
- application configuration
- troubleshooting

A common operational mistake is to secure IPv4 while overlooking IPv6 connectivity.

## DNS and IP addressing

DNS is a naming system.

IP addressing provides network-layer addressing.

For example:

`application.example`

could resolve to one or more IPv4 and IPv6 addresses.

An A record represents an IPv4 address.

An AAAA record represents an IPv6 address.

DNS does not itself perform packet forwarding.

A DNS name can map to multiple addresses, and multiple names can refer to the same address.

## Python implementation

The Python program is the broadest educational implementation.

It uses the standard-library `ipaddress` module for robust parsing and address calculations.

Important demonstrations include:

- `IPv4Address`
- `IPv4Network`
- `IPv6Address`
- `IPv6Network`
- binary conversion
- CIDR analysis
- subnet sizing
- VLSM-style allocation
- network membership
- address classification
- longest-prefix routing
- address-pool allocation
- IPv6 compression and expansion
- dual-stack architecture
- automated assertions

The Python implementation deliberately uses functions and dataclasses to make the individual networking operations easy to inspect.

The `IPv4SubnetDetails` dataclass groups related results such as:

- network address
- subnet mask
- broadcast address
- first host
- last host
- total addresses
- usable hosts
- prefix length

This is useful because a subnet calculation produces a group of logically related values rather than one isolated number.

## JavaScript implementation

The JavaScript implementation emphasizes how IP addressing can be implemented at the application level without an external package.

IPv4 addresses are converted to unsigned 32-bit integers.

This makes operations such as:

`address AND mask`

natural to implement.

The implementation also demonstrates an important JavaScript distinction.

Bitwise operators work on 32-bit integer representations, while `Number` itself is a floating-point type based on IEEE 754.

For IPv4 this can be managed with unsigned 32-bit conversion.

For IPv6, 128-bit values exceed the exact integer range of ordinary JavaScript numbers.

The implementation therefore uses `BigInt` for IPv6 calculations.

The JavaScript implementation also includes:

- input validation
- CIDR parsing
- subnet calculation
- IPv4 classification
- VLSM allocation
- longest-prefix matching
- IPv6 parsing
- IPv6 expansion
- IPv6 compression
- IPv6 prefix membership
- IPv6 address-count calculations
- an IPv4 address-pool class
- automated tests

This makes JavaScript particularly useful for demonstrating how network-addressing functionality can be embedded into browser-side or server-side applications.

## C++ case study

The C++ implementation models an organization designing an internal network.

The fictional organization has an internal base network:

`10.50.0.0/24`

Its requirements include:

- Engineering
- Security Operations
- Databases
- Application Servers
- Management
- Router Links

The program uses VLSM-style allocation to assign different subnet sizes according to the requested host counts.

### IPv4Address class

The `IPv4Address` class stores the address as a `std::uint32_t`.

It provides:

- parsing
- string conversion
- binary representation
- access to the integer representation
- equality comparison

Using a fixed-width unsigned integer makes the relationship between IPv4 and its 32-bit representation explicit.

### IPv4Network class

The `IPv4Network` class stores:

- prefix length
- subnet mask
- network address
- broadcast address

It provides methods for:

- CIDR parsing
- network calculation
- broadcast calculation
- subnet membership
- host capacity
- first-host calculation
- last-host calculation

The network address is calculated with a bitwise AND between the address and the subnet mask.

### VLSMAllocator

`VLSMAllocator` receives a base network and a set of requirements.

Requirements are sorted by host count in descending order.

Each requirement receives the smallest suitable subnet.

The allocator also aligns each subnet to the correct block boundary.

This is important because an arbitrary address cannot be treated as the start of a subnet for every prefix length.

### Route table

The case study creates routes such as:

- `0.0.0.0/0`
- `10.0.0.0/8`
- `10.20.0.0/16`
- `10.20.30.0/24`
- `10.20.30.128/25`

The program then determines which route should be selected for different destinations.

The algorithm chooses the matching route with the largest prefix length.

### IPv6Address class

The C++ IPv6 implementation stores eight 16-bit groups.

It supports:

- compressed input
- expanded input
- validation
- expanded output
- compressed output
- prefix membership

The class demonstrates why IPv6 requires a larger representation than IPv4 and why address formatting requires careful handling of hexadecimal groups and zero compression.

## Address allocation design

A production IP address management system would generally require much more than the educational allocator.

Typical requirements include:

- persistent storage
- authentication
- authorization
- address ownership
- subnet ownership
- reservations
- DHCP integration
- DNS integration
- VLAN mapping
- overlapping-address detection
- IPv4 and IPv6 support
- audit logging
- change history
- concurrency control
- API access
- role-based access control
- backup and recovery
- monitoring
- reconciliation with network devices

The C++ case study intentionally focuses on the core address-management mathematics and algorithms rather than implementing an entire enterprise IPAM platform.

## Edge cases

### `/31
