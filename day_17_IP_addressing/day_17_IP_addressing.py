#!/usr/bin/env python3
"""
IP Addressing: IPv4, IPv6, Public and Private IP Addresses
============================================================

A self-contained study and demonstration program covering:

- What an IP address is
- IPv4 structure and notation
- Binary representation
- IPv4 address classes and why classful networking is historical
- Network and host portions
- Subnet masks
- CIDR notation
- Network, broadcast, first-host and last-host addresses
- Subnet calculations
- VLSM-style allocation
- Private IPv4 address ranges
- Public IPv4 addresses
- Special IPv4 ranges
- NAT and private addressing
- IPv4 limitations
- IPv6 structure and notation
- IPv6 compression and expansion
- IPv6 prefix lengths
- IPv6 address types
- Global unicast, link-local, unique-local, multicast and loopback
- IPv6 subnetting
- IPv6 interface identifiers
- IPv6 versus IPv4
- Dual stack
- Common mistakes
- Validation
- Practical address planning
- Routing-table concepts
- Longest-prefix matching
- Address allocation simulation
- Security considerations
- Performance and implementation considerations

The program uses only Python's standard library.
"""

from __future__ import annotations

import ipaddress
import itertools
import math
import random
from dataclasses import dataclass
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Section 1: Fundamental concepts
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    """Print a readable section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_ip_address_basics() -> None:
    print_section("1. What is an IP address?")

    print(
        "An Internet Protocol address identifies an interface or endpoint at "
        "the IP layer. It provides an address used by routers and hosts to "
        "deliver packets across interconnected networks."
    )

    print("\nTwo major versions are demonstrated:")
    print("  IPv4: 32-bit address space")
    print("  IPv6: 128-bit address space")

    print("\nExamples:")
    print("  IPv4: 192.168.1.10")
    print("  IPv6: 2001:db8:1234:1::10")

    print("\nImportant distinction:")
    print("  An IP address identifies a network-layer endpoint/address.")
    print("  A MAC address belongs to the data-link layer.")
    print("  A port identifies an application endpoint within a transport protocol.")


# ---------------------------------------------------------------------------
# Section 2: IPv4 fundamentals
# ---------------------------------------------------------------------------

def ipv4_to_binary(address: str) -> str:
    """Convert an IPv4 address to a 32-bit binary string."""
    parsed = ipaddress.IPv4Address(address)
    return f"{int(parsed):032b}"


def binary_to_ipv4(binary: str) -> str:
    """Convert exactly 32 binary bits into dotted-decimal IPv4 notation."""
    if len(binary) != 32 or any(bit not in "01" for bit in binary):
        raise ValueError("IPv4 binary representation must contain exactly 32 bits.")
    return str(ipaddress.IPv4Address(int(binary, 2)))


def demonstrate_ipv4_representation() -> None:
    print_section("2. IPv4 representation")

    address = "192.168.10.25"
    binary = ipv4_to_binary(address)

    print(f"Address: {address}")
    print(f"Binary : {binary}")
    print(f"Round trip: {binary_to_ipv4(binary)}")

    octets = address.split(".")
    print("\nIPv4 contains four octets:")
    for index, octet in enumerate(octets, start=1):
        print(f"  Octet {index}: {octet:>3} -> {int(octet):08b}")

    print(
        "\nEach octet contains 8 bits, so IPv4 contains "
        "4 × 8 = 32 bits."
    )

    print("\nThe 32-bit space contains:")
    print(f"  2^32 = {2**32:,} possible bit patterns.")


# ---------------------------------------------------------------------------
# Section 3: IPv4 masks and CIDR
# ---------------------------------------------------------------------------

def prefix_to_mask(prefix: int) -> str:
    """Return dotted-decimal subnet mask for an IPv4 prefix length."""
    if not 0 <= prefix <= 32:
        raise ValueError("IPv4 prefix length must be between 0 and 32.")
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def mask_to_prefix(mask: str) -> int:
    """Convert a contiguous IPv4 subnet mask to its prefix length."""
    network = ipaddress.IPv4Network(f"0.0.0.0/{mask}")
    if str(network.netmask) != mask:
        raise ValueError(f"{mask} is not a valid contiguous IPv4 subnet mask.")
    return network.prefixlen


def demonstrate_prefix_lengths() -> None:
    print_section("3. IPv4 subnet masks and CIDR")

    examples = [8, 16, 20, 24, 25, 26, 27, 30, 31, 32]

    print("Prefix length -> subnet mask:")
    for prefix in examples:
        print(f"  /{prefix:<2} -> {prefix_to_mask(prefix)}")

    print("\nCIDR notation combines an address and prefix length.")
    print("Example: 192.168.10.0/24")
    print("  Address portion: 192.168.10.0")
    print("  Prefix length   : 24")
    print("  Network bits    : 24")
    print("  Host bits       : 8")

    print("\nFor an ordinary /24 network:")
    print("  Total addresses = 256")
    print("  Traditionally usable host addresses = 254")
    print("  Network address = first address")
    print("  Broadcast address = last address")


# ---------------------------------------------------------------------------
# Section 4: IPv4 subnet calculations
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IPv4SubnetDetails:
    network: str
    netmask: str
    broadcast: str
    first_host: Optional[str]
    last_host: Optional[str]
    total_addresses: int
    usable_hosts: int
    prefix_length: int


def analyze_ipv4_subnet(cidr: str) -> IPv4SubnetDetails:
    """
    Analyze an IPv4 network.

    strict=False allows input such as 192.168.1.77/24 and calculates the
    containing network 192.168.1.0/24.
    """
    network = ipaddress.IPv4Network(cidr, strict=False)
    total = network.num_addresses

    # /31 and /32 have special practical behavior. Python's ipaddress
    # library treats /31 as a two-address point-to-point network and /32
    # as a single host route.
    if network.prefixlen <= 30:
        usable = total - 2
        first_host = str(network.network_address + 1)
        last_host = str(network.broadcast_address - 1)
    elif network.prefixlen == 31:
        usable = 2
        first_host = str(network.network_address)
        last_host = str(network.broadcast_address)
    else:
        usable = 1
        first_host = str(network.network_address)
        last_host = str(network.network_address)

    return IPv4SubnetDetails(
        network=str(network.network_address),
        netmask=str(network.netmask),
        broadcast=str(network.broadcast_address),
        first_host=first_host,
        last_host=last_host,
        total_addresses=total,
        usable_hosts=usable,
        prefix_length=network.prefixlen,
    )


def print_ipv4_subnet_details(cidr: str) -> None:
    details = analyze_ipv4_subnet(cidr)

    print(f"\nCIDR: {cidr}")
    print(f"  Network address : {details.network}/{details.prefix_length}")
    print(f"  Subnet mask     : {details.netmask}")
    print(f"  Broadcast       : {details.broadcast}")
    print(f"  Total addresses : {details.total_addresses}")
    print(f"  Usable hosts    : {details.usable_hosts}")
    print(f"  First host      : {details.first_host}")
    print(f"  Last host       : {details.last_host}")


def demonstrate_subnet_calculation() -> None:
    print_section("4. IPv4 subnet calculation")

    for cidr in (
        "192.168.10.25/24",
        "10.20.30.40/26",
        "172.16.8.15/28",
        "192.0.2.0/31",
        "203.0.113.17/32",
    ):
        print_ipv4_subnet_details(cidr)

    print(
        "\nExample /26 reasoning:"
        "\n  A /26 has 26 network bits and 6 host bits."
        "\n  2^6 = 64 total addresses."
        "\n  Four /26 networks fit inside one /24."
    )


# ---------------------------------------------------------------------------
# Section 5: IPv4 address classification
# ---------------------------------------------------------------------------

def classify_ipv4(address: str) -> list[str]:
    """Return useful classifications for an IPv4 address."""
    ip = ipaddress.IPv4Address(address)
    labels: list[str] = []

    if ip.is_private:
        labels.append("private")
    if ip.is_global:
        labels.append("global/publicly routable")
    if ip.is_loopback:
        labels.append("loopback")
    if ip.is_link_local:
        labels.append("link-local")
    if ip.is_multicast:
        labels.append("multicast")
    if ip.is_unspecified:
        labels.append("unspecified")
    if ip.is_reserved:
        labels.append("reserved")

    return labels or ["ordinary/unclassified special-purpose status"]


def demonstrate_ipv4_address_categories() -> None:
    print_section("5. IPv4 address categories")

    examples = [
        "10.10.10.10",
        "172.16.20.30",
        "192.168.1.100",
        "8.8.8.8",
        "127.0.0.1",
        "169.254.1.20",
        "224.0.0.1",
        "0.0.0.0",
        "255.255.255.255",
    ]

    for address in examples:
        print(f"  {address:<15} -> {', '.join(classify_ipv4(address))}")

    print("\nTraditional private IPv4 ranges:")
    print("  10.0.0.0/8")
    print("  172.16.0.0/12")
    print("  192.168.0.0/16")

    print(
        "\nPrivate addresses are intended for private networks and are not "
        "normally globally routed on the public Internet."
    )

    print("\nCommon special ranges:")
    print("  127.0.0.0/8       Loopback")
    print("  169.254.0.0/16    IPv4 link-local")
    print("  224.0.0.0/4       Multicast")
    print("  0.0.0.0/0         Default-route prefix")
    print("  255.255.255.255   Limited broadcast")


# ---------------------------------------------------------------------------
# Section 6: Historical IPv4 classes
# ---------------------------------------------------------------------------

def demonstrate_historical_ipv4_classes() -> None:
    print_section("6. Historical IPv4 address classes")

    print(
        "Classful addressing divided IPv4 into fixed classes. Modern networks "
        "use CIDR, so these classes are mainly historical knowledge."
    )

    classes = [
        ("A", "1.0.0.0/8", "8", "24"),
        ("B", "128.0.0.0/16", "16", "16"),
        ("C", "192.0.0.0/24", "24", "8"),
        ("D", "224.0.0.0/4", "multicast", "multicast"),
        ("E", "240.0.0.0/4", "experimental/reserved", "experimental/reserved"),
    ]

    for name, range_text, network_bits, host_bits in classes:
        print(
            f"  Class {name}: range example {range_text}, "
            f"network bits={network_bits}, host bits={host_bits}"
        )

    print(
        "\nCIDR replaced rigid class boundaries with arbitrary prefix lengths "
        "such as /19, /22, /27 and /30."
    )


# ---------------------------------------------------------------------------
# Section 7: Host requirements and subnet sizing
# ---------------------------------------------------------------------------

def smallest_ipv4_prefix_for_hosts(required_hosts: int) -> int:
    """
    Calculate the smallest ordinary IPv4 subnet prefix capable of holding
    the requested number of usable host addresses.

    This uses the traditional network/broadcast reservation for prefixes
    <= 30. /31 and /32 are handled separately because they have special use.
    """
    if required_hosts < 1:
        raise ValueError("Required hosts must be positive.")

    for prefix in range(30, -1, -1):
        total = 2 ** (32 - prefix)
        usable = total - 2
        if usable >= required_hosts:
            return prefix

    raise ValueError("Requested host count cannot fit into IPv4.")


def demonstrate_subnet_sizing() -> None:
    print_section("7. Choosing an IPv4 subnet size")

    requirements = [2, 6, 10, 14, 30, 50, 100, 200, 500, 1000]

    for hosts in requirements:
        prefix = smallest_ipv4_prefix_for_hosts(hosts)
        total = 2 ** (32 - prefix)
        usable = total - 2
        print(
            f"  Required hosts={hosts:<4} -> /{prefix:<2} "
            f"total={total:<5} usable={usable}"
        )

    print(
        "\nThe calculation is based on host bits. If h host bits are available, "
        "there are 2^h address combinations. In traditional LAN subnetting, "
        "two addresses are reserved for network and broadcast."
    )


# ---------------------------------------------------------------------------
# Section 8: VLSM-style planning
# ---------------------------------------------------------------------------

@dataclass
class DepartmentRequirement:
    name: str
    hosts: int


def allocate_vlsm(base_network: str,
                   requirements: Iterable[DepartmentRequirement]) -> list[tuple[str, str, int]]:
    """
    Allocate largest requirements first from an IPv4 base network.

    This is a teaching implementation of variable-length subnet masking.
    It does not replace an enterprise IPAM system.
    """
    base = ipaddress.IPv4Network(base_network, strict=True)

    ordered = sorted(requirements, key=lambda item: item.hosts, reverse=True)
    allocated: list[tuple[str, str, int]] = []

    cursor = int(base.network_address)
    end = int(base.broadcast_address) + 1

    for requirement in ordered:
        prefix = smallest_ipv4_prefix_for_hosts(requirement.hosts)
        size = 2 ** (32 - prefix)

        # Align the next network address to the required block size.
        aligned_cursor = ((cursor + size - 1) // size) * size

        if aligned_cursor + size > end:
            raise ValueError(
                f"Base network {base} cannot satisfy requirement "
                f"{requirement.name} ({requirement.hosts} hosts)."
            )

        subnet = ipaddress.IPv4Network(
            f"{ipaddress.IPv4Address(aligned_cursor)}/{prefix}"
        )

        allocated.append((requirement.name, str(subnet), requirement.hosts))
        cursor = int(subnet.broadcast_address) + 1

    return allocated


def demonstrate_vlsm() -> None:
    print_section("8. Variable-length subnet masking")

    requirements = [
        DepartmentRequirement("Engineering", 100),
        DepartmentRequirement("Operations", 50),
        DepartmentRequirement("Security", 25),
        DepartmentRequirement("Management", 10),
        DepartmentRequirement("Point-to-point links", 2),
    ]

    print("Base network: 10.50.0.0/24")
    print("Requirements are allocated from largest to smallest.\n")

    try:
        allocations = allocate_vlsm("10.50.0.0/24", requirements)
        for name, subnet, hosts in allocations:
            details = analyze_ipv4_subnet(subnet)
            print(
                f"  {name:<22} {subnet:<15} "
                f"requested={hosts:<3} usable={details.usable_hosts}"
            )
    except ValueError as error:
        print(f"Allocation error: {error}")

    print(
        "\nVLSM allows different departments to receive different subnet sizes, "
        "reducing address waste compared with giving every department the same "
        "fixed-size subnet."
    )


# ---------------------------------------------------------------------------
# Section 9: Network membership
# ---------------------------------------------------------------------------

def address_belongs_to_network(address: str, network: str) -> bool:
    return ipaddress.IPv4Address(address) in ipaddress.IPv4Network(
        network, strict=False
    )


def demonstrate_membership() -> None:
    print_section("9. Testing whether an address belongs to a subnet")

    network = "192.168.50.0/24"
    candidates = [
        "192.168.50.1",
        "192.168.50.250",
        "192.168.51.1",
        "10.0.0.1",
    ]

    for address in candidates:
        result = address_belongs_to_network(address, network)
        print(f"  {address:<15} in {network}: {result}")


# ---------------------------------------------------------------------------
# Section 10: IPv4 validation and edge cases
# ---------------------------------------------------------------------------

def validate_ipv4_input(value: str) -> tuple[bool, str]:
    """Validate user input without throwing an exception to the caller."""
    try:
        address = ipaddress.IPv4Address(value)
        return True, f"Valid IPv4 address: {address}"
    except ipaddress.AddressValueError as error:
        return False, f"Invalid IPv4 address: {error}"


def demonstrate_ipv4_edge_cases() -> None:
    print_section("10. IPv4 validation and edge cases")

    values = [
        "192.168.1.1",
        "192.168.1.256",
        "192.168.1",
        "01.2.3.4",
        "127.0.0.1",
        "0.0.0.0",
        "255.255.255.255",
        "",
    ]

    for value in values:
        valid, message = validate_ipv4_input(value)
        print(f"  Input={value!r:<20} -> {message}")

    print(
        "\nDo not validate IPv4 addresses by checking only that a string contains "
        "three dots. Each octet has numeric and range constraints."
    )


# ---------------------------------------------------------------------------
# Section 11: IPv4 routing and longest-prefix matching
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Route:
    network: ipaddress.IPv4Network
    next_hop: str


def longest_prefix_match(
    destination: str,
    routes: Iterable[Route],
) -> Optional[Route]:
    """Return the most specific route containing destination."""
    ip = ipaddress.IPv4Address(destination)
    matching = [route for route in routes if ip in route.network]

    if not matching:
        return None

    return max(matching, key=lambda route: route.network.prefixlen)


def demonstrate_longest_prefix_matching() -> None:
    print_section("11. IPv4 routing and longest-prefix matching")

    routes = [
        Route(ipaddress.IPv4Network("0.0.0.0/0"), "Internet gateway"),
        Route(ipaddress.IPv4Network("10.0.0.0/8"), "Router A"),
        Route(ipaddress.IPv4Network("10.20.0.0/16"), "Router B"),
        Route(ipaddress.IPv4Network("10.20.30.0/24"), "Router C"),
        Route(ipaddress.IPv4Network("10.20.30.128/25"), "Router D"),
    ]

    for destination in (
        "8.8.8.8",
        "10.5.6.7",
        "10.20.10.5",
        "10.20.30.10",
        "10.20.30.200",
    ):
        route = longest_prefix_match(destination, routes)
        print(
            f"  Destination {destination:<15} -> "
            f"{route.network if route else 'no route'} -> "
            f"{route.next_hop if route else 'drop'}"
        )

    print(
        "\nThe most specific matching prefix wins. A /25 is more specific "
        "than a /24, which is more specific than /16, /8 or /0."
    )


# ---------------------------------------------------------------------------
# Section 12: NAT and private IPv4
# ---------------------------------------------------------------------------

def demonstrate_nat_concept() -> None:
    print_section("12. Private IPv4 addresses and NAT")

    print("Example private network:")
    print("  Laptop       192.168.1.20")
    print("  Phone        192.168.1.21")
    print("  Server       192.168.1.30")
    print("  Router LAN   192.168.1.1")
    print("  Router WAN   Public address assigned by an ISP")

    print(
        "\nNetwork Address Translation (NAT) can translate traffic between "
        "private internal addresses and an address used on an external network."
    )

    print("\nImportant distinctions:")
    print("  Private does not mean encrypted.")
    print("  NAT does not replace a firewall.")
    print("  NAT does not itself provide application-layer authentication.")
    print("  IPv6 does not inherently require NAT for ordinary global addressing.")

    print(
        "\nPort Address Translation (PAT), commonly called NAT overload, "
        "allows many internal connections to share an external IPv4 address "
        "by differentiating flows using transport-layer ports."
    )


# ---------------------------------------------------------------------------
# Section 13: IPv6 fundamentals
# ---------------------------------------------------------------------------

def expand_ipv6(address: str) -> str:
    """Return fully expanded eight-group IPv6 notation."""
    return ipaddress.IPv6Address(address).exploded


def compress_ipv6(address: str) -> str:
    """Return canonical compressed IPv6 notation."""
    return ipaddress.IPv6Address(address).compressed


def ipv6_binary(address: str) -> str:
    """Return the complete 128-bit binary representation."""
    return f"{int(ipaddress.IPv6Address(address)):0128b}"


def demonstrate_ipv6_representation() -> None:
    print_section("13. IPv6 representation")

    address = "2001:0db8:0000:0000:0000:ff00:0042:8329"

    print(f"Expanded : {expand_ipv6(address)}")
    print(f"Compressed: {compress_ipv6(address)}")
    print(f"Bits     : {ipv6_binary(address)}")

    print(
        "\nIPv6 contains eight groups of 16 bits each, for a total of "
        "8 × 16 = 128 bits."
    )

    print(f"Possible IPv6 bit patterns: 2^128 = {2**128:,}")

    print("\nIPv6 compression rules:")
    print("  1. Leading zeroes in each 16-bit group may be removed.")
    print("  2. One consecutive run of zero groups may be replaced by ::.")
    print("  3. :: can appear at most once in an address.")

    examples = [
        "2001:0db8:0000:0000:0000:0000:0000:0001",
        "2001:0db8:0000:0000:0000:0000:0000:0000",
        "fe80:0000:0000:0000:021c:7eff:fe12:3456",
    ]

    print("\nCompression examples:")
    for example in examples:
        print(f"  {example} -> {compress_ipv6(example)}")


# ---------------------------------------------------------------------------
# Section 14: IPv6 address types
# ---------------------------------------------------------------------------

def classify_ipv6(address: str) -> list[str]:
    ip = ipaddress.IPv6Address(address)
    labels: list[str] = []

    if ip.is_private:
        labels.append("private/unique-local or otherwise non-global")
    if ip.is_global:
        labels.append("global")
    if ip.is_link_local:
        labels.append("link-local")
    if ip.is_loopback:
        labels.append("loopback")
    if ip.is_multicast:
        labels.append("multicast")
    if ip.is_unspecified:
        labels.append("unspecified")

    # IPv4-mapped addresses have a specific representation.
    if ip.ipv4_mapped is not None:
        labels.append("IPv4-mapped IPv6 address")

    return labels or ["ordinary/unclassified special-purpose status"]


def demonstrate_ipv6_categories() -> None:
    print_section("14. IPv6 address categories")

    examples = [
        "2001:db8::1",
        "fe80::1",
        "fc00::1",
        "::1",
        "::",
        "ff02::1",
        "::ffff:192.0.2.1",
    ]

    for address in examples:
        print(f"  {address:<25} -> {', '.join(classify_ipv6(address))}")

    print("\nImportant IPv6 ranges:")
    print("  2000::/3       Global unicast")
    print("  fe80::/10      Link-local unicast")
    print("  fc00::/7       Unique-local addressing")
    print("  ff00::/8       Multicast")
    print("  ::1/128        Loopback")
    print("  ::/128         Unspecified")

    print(
        "\n2001:db8::/32 is reserved for documentation examples. "
        "It should not be treated as an ordinary production Internet prefix."
    )


# ---------------------------------------------------------------------------
# Section 15: IPv6 prefixes and subnets
# ---------------------------------------------------------------------------

def analyze_ipv6_subnet(cidr: str) -> None:
    network = ipaddress.IPv6Network(cidr, strict=False)

    print(f"\nIPv6 network: {network}")
    print(f"  Prefix length : /{network.prefixlen}")
    print(f"  Network       : {network.network_address}")
    print(f"  First address : {network.network_address}")
    print(f"  Last address  : {network[-1]}")
    print(f"  Address count : {network.num_addresses:,}")

    if network.prefixlen <= 64:
        subnet_bits = 64 - network.prefixlen
        print(
            f"  If /64 is the interface-subnet boundary, "
            f"{subnet_bits} bits are available for subnet identifiers."
        )


def demonstrate_ipv6_subnetting() -> None:
    print_section("15. IPv6 subnetting")

    analyze_ipv6_subnet("2001:db8:1234::/48")
    analyze_ipv6_subnet("2001:db8:1234:10::/64")
    analyze_ipv6_subnet("fd12:3456:789a::/48")

    print(
        "\nA common enterprise design is to receive a larger prefix such as "
        "/48 and allocate /64 subnets to individual LANs or VLANs."
    )

    print(
        "\nFor a /48 delegated prefix, the number of /64 subnets is "
        "2^(64-48) = 2^16 = 65,536."
    )


# ---------------------------------------------------------------------------
# Section 16: IPv6 subnet enumeration
# ---------------------------------------------------------------------------

def demonstrate_ipv6_subnet_enumeration() -> None:
    print_section("16. Enumerating IPv6 subnets")

    parent = ipaddress.IPv6Network("2001:db8:1000::/48")
    children = list(itertools.islice(parent.subnets(new_prefix=52), 5))

    print(f"Parent: {parent}")
    print("First five /52 child networks:")
    for child in children:
        print(f"  {child}")

    print(
        "\nSubnet enumeration is mathematically straightforward, but an "
        "application should avoid materializing enormous subnet lists unless "
        "the number of subnets is known to be manageable."
    )


# ---------------------------------------------------------------------------
# Section 17: Dual-stack and transition concepts
# ---------------------------------------------------------------------------

def demonstrate_dual_stack() -> None:
    print_section("17. Dual-stack networking")

    host = {
        "name": "application-server",
        "ipv4": "192.168.10.20",
        "ipv6": "2001:db8:10:20::20",
    }

    print(f"Host: {host['name']}")
    print(f"  IPv4: {host['ipv4']}")
    print(f"  IPv6: {host['ipv6']}")

    print(
        "\nDual stack means a system can operate with IPv4 and IPv6 "
        "simultaneously. Applications and network infrastructure may then "
        "use either protocol according to DNS, routing, configuration and "
        "connectivity."
    )

    print(
        "\nOther transition mechanisms exist, including tunneling and "
        "translation technologies. They have different operational trade-offs "
        "and should not be confused with dual stack."
    )


# ---------------------------------------------------------------------------
# Section 18: DNS and IP addresses
# ---------------------------------------------------------------------------

def demonstrate_dns_relationship() -> None:
    print_section("18. DNS versus IP addressing")

    print("Example:")
    print("  Application name: example.com")
    print("  DNS may return IPv4 and/or IPv6 addresses.")
    print("  IPv4 result uses an A record.")
    print("  IPv6 result uses an AAAA record.")

    print(
        "\nDNS is a naming system. IP addressing is an addressing and routing "
        "mechanism. A DNS name can map to multiple addresses, and an address "
        "can serve multiple names."
    )


# ---------------------------------------------------------------------------
# Section 19: Practical address planner
# ---------------------------------------------------------------------------

@dataclass
class HostAllocation:
    name: str
    address: str
    subnet: str


class IPv4AddressPool:
    """
    Simple educational IPv4 host allocator.

    It reserves network and broadcast addresses for ordinary IPv4 networks.
    """

    def __init__(self, network: str):
        parsed = ipaddress.IPv4Network(network, strict=True)

        if parsed.prefixlen > 30:
            raise ValueError(
                "IPv4AddressPool requires a normal subnet with at least "
                "two reserved addresses."
            )

        self.network = parsed
        self.available = iter(parsed.hosts())
        self.allocations: list[HostAllocation] = []

    def allocate(self, name: str) -> HostAllocation:
        try:
            address = next(self.available)
        except StopIteration as error:
            raise RuntimeError("Address pool is exhausted.") from error

        allocation = HostAllocation(
            name=name,
            address=str(address),
            subnet=str(self.network),
        )
        self.allocations.append(allocation)
        return allocation


def demonstrate_address_pool() -> None:
    print_section("19. Simple IPv4 address allocation")

    pool = IPv4AddressPool("192.168.100.0/29")

    for device in (
        "router",
        "database",
        "application-server",
        "monitoring",
        "developer-laptop",
        "printer",
    ):
        try:
            allocation = pool.allocate(device)
            print(
                f"  {allocation.name:<22} "
                f"{allocation.address:<15} "
                f"{allocation.subnet}"
            )
        except RuntimeError as error:
            print(f"  {device:<22} allocation failed: {error}")

    print("\nThe /29 network contains eight addresses and traditionally six usable hosts.")


# ---------------------------------------------------------------------------
# Section 20: Comparing IPv4 and IPv6 programmatically
# ---------------------------------------------------------------------------

def compare_ip_versions() -> None:
    print_section("20. IPv4 and IPv6 comparison")

    comparison = [
        ("Address size", "32 bits", "128 bits"),
        ("Common notation", "Dotted decimal", "Colon-separated hexadecimal"),
        ("Broadcast", "Supported", "No traditional broadcast; multicast is used"),
        ("Loopback", "127.0.0.0/8", "::1/128"),
        ("Link-local", "169.254.0.0/16", "fe80::/10"),
        ("Private-style space", "RFC1918 ranges", "Unique-local fc00::/7"),
        ("Common subnet boundary", "Varies", "/64 commonly used"),
        ("NAT dependence", "Widely deployed", "Not inherent to IPv6 addressing"),
    ]

    print(f"{'Property':<25} {'IPv4':<35} {'IPv6'}")
    print("-" * 78)
    for property_name, ipv4_value, ipv6_value in comparison:
        print(f"{property_name:<25} {ipv4_value:<35} {ipv6_value}")

    print(
        "\nIPv6 is not simply IPv4 with larger numbers. The protocol and "
        "addressing architecture differ in several important ways."
    )


# ---------------------------------------------------------------------------
# Section 21: Common mistakes
# ---------------------------------------------------------------------------

def demonstrate_common_mistakes() -> None:
    print_section("21. Common IP addressing mistakes")

    mistakes = [
        (
            "Confusing private with secure",
            "Private addressing controls routability, not confidentiality."
        ),
        (
            "Assuming every /24 has 254 usable hosts",
            "/31 and /32 have special semantics, and subnet purpose matters."
        ),
        (
            "Treating IPv6 like dotted-decimal IPv4",
            "IPv6 uses hexadecimal groups and 128-bit addresses."
        ),
        (
            "Using :: twice in IPv6",
            "IPv6 compression can replace only one zero run with ::."
        ),
        (
            "Forgetting prefix length",
            "An address alone does not fully describe subnet membership."
        ),
        (
            "Assuming NAT is a security boundary",
            "Firewall policy and access controls provide security policy."
        ),
        (
            "Using 255.255.255.0 everywhere",
            "CIDR allows subnet sizes to match actual requirements."
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\nMistake: {mistake}")
        print(f"Correction: {correction}")


# ---------------------------------------------------------------------------
# Section 22: Security considerations
# ---------------------------------------------------------------------------

def demonstrate_security() -> None:
    print_section("22. Security considerations")

    print("IP addressing itself is not an authentication mechanism.")

    controls = [
        "Network segmentation",
        "Stateful firewall policies",
        "Access-control lists",
        "Secure routing configuration",
        "Source-address validation",
        "Monitoring and logging",
        "Ingress and egress filtering",
        "IPv6-aware security policies",
        "Least-privilege network access",
    ]

    print("\nRelevant controls include:")
    for control in controls:
        print(f"  - {control}")

    print(
        "\nA security design must account for both IPv4 and IPv6. Enabling "
        "IPv6 without equivalent firewall, routing and monitoring policy can "
        "create an unintended alternate path."
    )

    print(
        "\nIP spoofing is possible because the source address in a packet is "
        "not by itself proof of sender identity. Network controls such as "
        "ingress filtering can reduce spoofing opportunities."
    )


# ---------------------------------------------------------------------------
# Section 23: Performance and implementation considerations
# ---------------------------------------------------------------------------

def demonstrate_performance() -> None:
    print_section("23. Performance and implementation considerations")

    print(
        "Address calculations are integer and bitwise operations internally. "
        "For ordinary individual addresses and prefixes, the computational "
        "cost is extremely small."
    )

    print("\nPotential scaling problems arise from data volume rather than arithmetic:")

    print("  - Enumerating every address in a large IPv6 network is impractical.")
    print("  - Building huge subnet lists consumes memory.")
    print("  - Linear route-table searches become expensive as route counts grow.")
    print("  - Production routers use optimized data structures for prefix lookup.")

    print("\nFor a routing table with N routes:")
    print("  Linear search: approximately O(N) per lookup.")
    print("  Prefix trees/radix structures can provide much better lookup behavior.")


# ---------------------------------------------------------------------------
# Section 24: Testing
# ---------------------------------------------------------------------------

def run_tests() -> None:
    print_section("24. Automated correctness checks")

    assert ipv4_to_binary("192.168.1.1") == "11000000101010000000000100000001"
    assert binary_to_ipv4("11000000101010000000000100000001") == "192.168.1.1"

    assert prefix_to_mask(24) == "255.255.255.0"
    assert mask_to_prefix("255.255.255.0") == 24

    details = analyze_ipv4_subnet("192.168.10.25/24")
    assert details.network == "192.168.10.0"
    assert details.broadcast == "192.168.10.255"
    assert details.usable_hosts == 254

    assert address_belongs_to_network("192.168.10.25", "192.168.10.0/24")
    assert not address_belongs_to_network("192.168.11.25", "192.168.10.0/24")

    assert compress_ipv6("2001:0db8:0000:0000:0000:0000:0000:0001") == "2001:db8::1"
    assert expand_ipv6("::1") == "0000:0000:0000:0000:0000:0000:0000:0001"

    assert ipaddress.IPv4Address("10.1.1.1").is_private
    assert ipaddress.IPv4Address("127.0.0.1").is_loopback
    assert ipaddress.IPv6Address("fe80::1").is_link_local
    assert ipaddress.IPv6Address("::1").is_loopback

    routes = [
        Route(ipaddress.IPv4Network("10.0.0.0/8"), "A"),
        Route(ipaddress.IPv4Network("10.1.0.0/16"), "B"),
        Route(ipaddress.IPv4Network("10.1.2.0/24"), "C"),
    ]
    assert longest_prefix_match("10.1.2.5", routes).next_hop == "C"

    print("All assertions passed.")


# ---------------------------------------------------------------------------
# Section 25: Interactive subnet calculator
# ---------------------------------------------------------------------------

def interactive_subnet_calculator() -> None:
    print_section("25. Interactive IPv4 subnet calculator")

    print(
        "Enter an IPv4 CIDR such as 192.168.1.25/24. "
        "Press Enter without input to skip."
    )

    try:
        value = input("CIDR: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nInteractive input cancelled.")
        return

    if not value:
        print("Skipped.")
        return

    try:
        print_ipv4_subnet_details(value)
    except ValueError as error:
        print(f"Invalid CIDR: {error}")


# ---------------------------------------------------------------------------
# Section 26: Main study sequence
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("IP ADDRESSING STUDY PROGRAM")
    print("IPv4, IPv6, Public and Private IP Addresses")
    print("=" * 78)

    explain_ip_address_basics()
    demonstrate_ipv4_representation()
    demonstrate_prefix_lengths()
    demonstrate_subnet_calculation()
    demonstrate_ipv4_address_categories()
    demonstrate_historical_ipv4_classes()
    demonstrate_subnet_sizing()
    demonstrate_vlsm()
    demonstrate_membership()
    demonstrate_ipv4_edge_cases()
    demonstrate_longest_prefix_matching()
    demonstrate_nat_concept()
    demonstrate_ipv6_representation()
    demonstrate_ipv6_categories()
    demonstrate_ipv6_subnetting()
    demonstrate_ipv6_subnet_enumeration()
    demonstrate_dual_stack()
    demonstrate_dns_relationship()
    demonstrate_address_pool()
    compare_ip_versions()
    demonstrate_common_mistakes()
    demonstrate_security()
    demonstrate_performance()
    run_tests()

    # The interactive portion is deliberately last so that the complete
    # educational demonstration runs before waiting for user input.
    interactive_subnet_calculator()

    print_section("Program complete")
    print(
        "The examples covered IPv4 and IPv6 representation, subnetting, "
        "address classification, routing, allocation, validation, security "
        "and practical implementation considerations."
    )


if __name__ == "__main__":
    main()
