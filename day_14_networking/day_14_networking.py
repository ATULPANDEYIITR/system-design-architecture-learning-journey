"""
Computer Networks: LAN, WAN, Routers, Switches, Packets
=========================================================

A standalone educational Python script covering computer networking from
absolute beginner concepts through practical and advanced networking ideas.

The examples are intentionally implemented with Python's standard library.
They use simulations where real network infrastructure would otherwise be
required. The goal is to make networking concepts executable and observable
without requiring special hardware or third-party packages.

Topics covered
--------------
1. What a computer network is
2. Network terminology
3. Network types: PAN, LAN, MAN, WAN
4. Network topologies
5. Nodes, hosts, clients, servers and endpoints
6. MAC addresses and Ethernet frames
7. IP addresses and subnets
8. IPv4 and IPv6 concepts
9. Ports and sockets
10. TCP and UDP
11. Packets and encapsulation
12. Switches and MAC-address learning
13. Routers and routing tables
14. Default gateways
15. ARP and neighbor discovery concepts
16. DNS
17. DHCP
18. NAT
19. TTL and hop-by-hop forwarding
20. Routing and longest-prefix matching
21. Broadcast and collision domains
22. Packet fragmentation concepts
23. Network latency, bandwidth and throughput
24. Packet loss and retransmission
25. TCP connection concepts
26. UDP communication concepts
27. Client-server communication
28. Network simulation
29. Subnet calculations
30. Troubleshooting and diagnostics
31. Network security concepts
32. Performance considerations
33. Production design considerations
34. Common mistakes and edge cases
"""

from __future__ import annotations

import ipaddress
import random
import socket
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple


# =============================================================================
# SECTION 1: FUNDAMENTAL NETWORKING TERMINOLOGY
# =============================================================================

def explain_basic_terminology() -> None:
    """
    Demonstrate the basic vocabulary used in computer networking.

    Network:
        A collection of interconnected devices that can exchange data.

    Node:
        A device or logical participant in a network.

    Host:
        A network-connected device that has an IP address.

    Endpoint:
        A communication endpoint, commonly identified by IP address + port.

    Client:
        A system that requests a service.

    Server:
        A system that provides a service.

    Protocol:
        A defined set of communication rules.

    Packet:
        A unit of network-layer data.

    Frame:
        A data-link-layer unit, such as an Ethernet frame.

    MAC address:
        A data-link-layer hardware/interface identifier.

    IP address:
        A logical network-layer address used for routing.
    """
    terms = {
        "Network": "Connected devices that exchange data.",
        "Node": "A participant or device in a network.",
        "Host": "A network-connected device with a network address.",
        "Client": "A system requesting a service.",
        "Server": "A system providing a service.",
        "Protocol": "Rules that define communication.",
        "Packet": "A network-layer unit of data.",
        "Frame": "A data-link-layer unit carrying network-layer data.",
        "MAC address": "A data-link-layer interface identifier.",
        "IP address": "A logical address used for network communication and routing.",
        "Port": "A number identifying a service endpoint on a host.",
    }

    print("\n=== Basic Networking Terminology ===")
    for name, meaning in terms.items():
        print(f"{name:12}: {meaning}")


# =============================================================================
# SECTION 2: NETWORK TYPES
# =============================================================================

class NetworkType(Enum):
    PAN = "Personal Area Network"
    LAN = "Local Area Network"
    MAN = "Metropolitan Area Network"
    WAN = "Wide Area Network"


def demonstrate_network_types() -> None:
    """
    Compare common network classifications.

    PAN:
        Very small personal range, such as Bluetooth devices.

    LAN:
        A local network within a home, office, laboratory or building.

    MAN:
        A metropolitan-scale network connecting multiple local networks.

    WAN:
        A geographically large network. The Internet is the best-known example
        of a global internetwork.
    """
    print("\n=== Network Types ===")

    examples = {
        NetworkType.PAN: "Phone connected to wireless earbuds.",
        NetworkType.LAN: "Computers connected inside an office.",
        NetworkType.MAN: "Multiple campuses connected across a city.",
        NetworkType.WAN: "Branches connected across different countries.",
    }

    for network_type, example in examples.items():
        print(f"{network_type.value:30} -> {example}")


# =============================================================================
# SECTION 3: NETWORK TOPOLOGIES
# =============================================================================

def demonstrate_topologies() -> None:
    """
    Explain common physical/logical network topologies.

    Star:
        Devices connect to a central switch.

    Bus:
        Devices share a common communication medium.

    Ring:
        Devices form a logical/physical ring.

    Mesh:
        Devices have multiple interconnections.

    Tree:
        Hierarchical combination of star-like networks.

    Modern Ethernet LANs commonly use a star or hierarchical star design.
    """
    print("\n=== Network Topologies ===")

    topologies = {
        "Star": "Every endpoint connects to a central switch.",
        "Bus": "Devices share a common communication medium.",
        "Ring": "Devices form a circular communication path.",
        "Mesh": "Devices have multiple interconnections.",
        "Tree": "Hierarchical network built from multiple segments.",
    }

    for topology, description in topologies.items():
        print(f"{topology:8}: {description}")


# =============================================================================
# SECTION 4: MAC ADDRESSES
# =============================================================================

def normalize_mac(mac: str) -> str:
    """Validate and normalize a MAC address."""
    cleaned = mac.replace(":", "").replace("-", "").replace(".", "").lower()

    if len(cleaned) != 12:
        raise ValueError("A MAC address must contain 12 hexadecimal digits.")

    try:
        int(cleaned, 16)
    except ValueError as exc:
        raise ValueError("MAC address contains a non-hexadecimal character.") from exc

    return ":".join(cleaned[index:index + 2] for index in range(0, 12, 2))


def mac_is_broadcast(mac: str) -> bool:
    """Return True when the MAC address is the Ethernet broadcast address."""
    return normalize_mac(mac) == "ff:ff:ff:ff:ff:ff"


def mac_is_multicast(mac: str) -> bool:
    """
    Determine whether a MAC address is multicast.

    Ethernet multicast is identified by the least significant bit of the first
    octet being set.
    """
    normalized = normalize_mac(mac)
    first_octet = int(normalized.split(":")[0], 16)
    return bool(first_octet & 1)


def demonstrate_mac_addresses() -> None:
    print("\n=== MAC Addresses ===")

    addresses = [
        "00:11:22:33:44:55",
        "AA-BB-CC-DD-EE-FF",
        "FF:FF:FF:FF:FF:FF",
    ]

    for address in addresses:
        normalized = normalize_mac(address)
        print(
            f"{address:20} -> {normalized} | "
            f"broadcast={mac_is_broadcast(normalized)} | "
            f"multicast={mac_is_multicast(normalized)}"
        )


# =============================================================================
# SECTION 5: ETHERNET FRAMES
# =============================================================================

@dataclass
class EthernetFrame:
    """
    Simplified Ethernet frame.

    Real Ethernet frames contain additional fields and physical-layer details.
    This model focuses on the concepts relevant to switching.
    """

    source_mac: str
    destination_mac: str
    payload: bytes
    ether_type: int = 0x0800

    def __post_init__(self) -> None:
        self.source_mac = normalize_mac(self.source_mac)
        self.destination_mac = normalize_mac(self.destination_mac)

    def describe(self) -> None:
        print("\nEthernet frame")
        print(f"Source MAC      : {self.source_mac}")
        print(f"Destination MAC : {self.destination_mac}")
        print(f"EtherType       : 0x{self.ether_type:04X}")
        print(f"Payload bytes   : {len(self.payload)}")


# =============================================================================
# SECTION 6: IP ADDRESSES AND SUBNETS
# =============================================================================

def demonstrate_ip_addresses() -> None:
    """
    Demonstrate IPv4/IPv6 parsing and address properties.
    """
    print("\n=== IP Addresses ===")

    addresses = [
        "192.168.1.10",
        "10.0.0.5",
        "172.16.20.30",
        "8.8.8.8",
        "2001:4860:4860::8888",
        "fe80::1",
    ]

    for address_text in addresses:
        address = ipaddress.ip_address(address_text)
        print(
            f"{address_text:25} "
            f"version={address.version} "
            f"private={address.is_private} "
            f"loopback={address.is_loopback} "
            f"multicast={address.is_multicast}"
        )


def demonstrate_subnetting() -> None:
    """
    Demonstrate CIDR notation and subnet membership.

    Example:
        192.168.1.0/24

    The /24 means that the first 24 bits identify the network and the remaining
    8 bits identify hosts within that IPv4 subnet.
    """
    print("\n=== Subnetting ===")

    networks = [
        ipaddress.ip_network("192.168.1.0/24"),
        ipaddress.ip_network("10.10.0.0/16"),
        ipaddress.ip_network("172.16.10.0/28"),
    ]

    for network in networks:
        print(f"\nNetwork       : {network}")
        print(f"Network addr  : {network.network_address}")
        print(f"Broadcast     : {network.broadcast_address}")
        print(f"Prefix length : /{network.prefixlen}")
        print(f"Total addresses: {network.num_addresses}")
        print(f"Usable hosts  : {max(network.num_addresses - 2, 0)}")

        hosts = list(network.hosts())
        if hosts:
            print(f"First host    : {hosts[0]}")
            print(f"Last host     : {hosts[-1]}")


def hosts_in_same_subnet(ip1: str, ip2: str, prefix_length: int) -> bool:
    """
    Determine whether two IPv4 addresses belong to the same CIDR network.
    """
    network1 = ipaddress.ip_network(f"{ip1}/{prefix_length}", strict=False)
    return ipaddress.ip_address(ip2) in network1


def demonstrate_subnet_membership() -> None:
    print("\n=== Subnet Membership ===")

    tests = [
        ("192.168.1.10", "192.168.1.20", 24),
        ("192.168.1.10", "192.168.2.20", 24),
        ("10.0.1.10", "10.0.2.20", 16),
    ]

    for ip1, ip2, prefix in tests:
        result = hosts_in_same_subnet(ip1, ip2, prefix)
        print(f"{ip1} and {ip2} with /{prefix}: same subnet = {result}")


# =============================================================================
# SECTION 7: ROUTING
# =============================================================================

@dataclass
class Route:
    """One simplified routing-table entry."""

    network: ipaddress.IPv4Network
    next_hop: Optional[str]
    interface: str
    metric: int = 1


class RoutingTable:
    """
    Simplified IPv4 routing table.

    Routers commonly choose a route using longest-prefix matching. A more
    specific prefix is preferred over a less specific prefix when both match.
    """

    def __init__(self) -> None:
        self.routes: List[Route] = []

    def add_route(
        self,
        network: str,
        next_hop: Optional[str],
        interface: str,
        metric: int = 1,
    ) -> None:
        self.routes.append(
            Route(
                network=ipaddress.ip_network(network),
                next_hop=next_hop,
                interface=interface,
                metric=metric,
            )
        )

    def lookup(self, destination: str) -> Optional[Route]:
        """
        Perform longest-prefix matching.

        If multiple routes have the same prefix length, the lower metric wins.
        """
        destination_ip = ipaddress.ip_address(destination)

        matches = [
            route
            for route in self.routes
            if destination_ip in route.network
        ]

        if not matches:
            return None

        matches.sort(
            key=lambda route: (route.network.prefixlen, -route.metric),
            reverse=True,
        )

        return matches[0]

    def display(self) -> None:
        print("\nRouting table")
        for route in sorted(
            self.routes,
            key=lambda item: item.network.prefixlen,
            reverse=True,
        ):
            next_hop = route.next_hop or "direct"
            print(
                f"{str(route.network):18} "
                f"via {next_hop:15} "
                f"dev {route.interface:8} "
                f"metric {route.metric}"
            )


def demonstrate_routing() -> None:
    print("\n=== Routing and Longest-Prefix Matching ===")

    table = RoutingTable()

    table.add_route("192.168.1.0/24", None, "LAN")
    table.add_route("10.0.0.0/8", "10.1.1.1", "WAN1")
    table.add_route("0.0.0.0/0", "192.168.1.1", "LAN")
    table.add_route("10.20.0.0/16", "10.2.2.1", "WAN2")

    table.display()

    destinations = [
        "192.168.1.50",
        "10.20.10.5",
        "10.30.10.5",
        "8.8.8.8",
    ]

    print("\nRoute lookups")
    for destination in destinations:
        route = table.lookup(destination)
        if route is None:
            print(f"{destination}: no route")
        else:
            print(
                f"{destination}: "
                f"matched {route.network}, "
                f"next hop={route.next_hop or 'direct'}, "
                f"interface={route.interface}"
            )


# =============================================================================
# SECTION 8: SWITCH SIMULATION
# =============================================================================

@dataclass
class NetworkDevice:
    """A basic simulated network endpoint."""

    name: str
    mac: str
    ip: str

    def __post_init__(self) -> None:
        self.mac = normalize_mac(self.mac)
        self.ip = str(ipaddress.ip_address(self.ip))


class EthernetSwitch:
    """
    Learning Ethernet switch.

    The switch learns source MAC addresses from incoming frames. When a frame
    arrives, it forwards the frame to the learned destination port. Unknown
    unicast traffic is flooded to other ports.

    This is a simplified model. Real switches implement additional features
    such as VLANs, STP, QoS, security controls and hardware forwarding.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.ports: Dict[int, NetworkDevice] = {}
        self.mac_table: Dict[str, int] = {}

    def connect(self, port: int, device: NetworkDevice) -> None:
        self.ports[port] = device

    def receive(self, incoming_port: int, frame: EthernetFrame) -> List[int]:
        """
        Process a frame and return the output ports.

        Source learning occurs before destination lookup.
        """
        self.mac_table[frame.source_mac] = incoming_port

        destination = frame.destination_mac

        if mac_is_broadcast(destination) or mac_is_multicast(destination):
            return [
                port
                for port in self.ports
                if port != incoming_port
            ]

        known_port = self.mac_table.get(destination)

        if known_port is None:
            return [
                port
                for port in self.ports
                if port != incoming_port
            ]

        if known_port == incoming_port:
            return []

        return [known_port]

    def display_mac_table(self) -> None:
        print(f"\nSwitch {self.name} MAC table")
        if not self.mac_table:
            print("(empty)")
            return

        for mac, port in sorted(self.mac_table.items()):
            print(f"{mac} -> port {port}")


def demonstrate_switch() -> None:
    print("\n=== Ethernet Switch Simulation ===")

    switch = EthernetSwitch("SW1")

    pc_a = NetworkDevice("PC-A", "00:00:00:00:00:0A", "192.168.1.10")
    pc_b = NetworkDevice("PC-B", "00:00:00:00:00:0B", "192.168.1.11")
    pc_c = NetworkDevice("PC-C", "00:00:00:00:00:0C", "192.168.1.12")

    switch.connect(1, pc_a)
    switch.connect(2, pc_b)
    switch.connect(3, pc_c)

    first_frame = EthernetFrame(
        source_mac=pc_a.mac,
        destination_mac=pc_b.mac,
        payload=b"Hello",
    )

    output_ports = switch.receive(1, first_frame)
    print(f"First frame output ports: {output_ports}")

    second_frame = EthernetFrame(
        source_mac=pc_b.mac,
        destination_mac=pc_a.mac,
        payload=b"Reply",
    )

    output_ports = switch.receive(2, second_frame)
    print(f"Second frame output ports: {output_ports}")

    broadcast_frame = EthernetFrame(
        source_mac=pc_a.mac,
        destination_mac="FF:FF:FF:FF:FF:FF",
        payload=b"Broadcast",
    )

    output_ports = switch.receive(1, broadcast_frame)
    print(f"Broadcast output ports: {output_ports}")

    switch.display_mac_table()


# =============================================================================
# SECTION 9: PACKETS AND ENCAPSULATION
# =============================================================================

@dataclass
class ApplicationData:
    """Application-layer information."""

    source_process: str
    destination_process: str
    data: bytes


@dataclass
class TransportSegment:
    """
    Simplified TCP/UDP transport-layer segment.

    A real TCP segment contains many additional fields such as sequence number,
    acknowledgement number, flags, window size and checksum.
    """

    protocol: str
    source_port: int
    destination_port: int
    payload: bytes


@dataclass
class IPv4Packet:
    """
    Simplified IPv4 packet.

    The real IPv4 header contains fields including version, IHL, DSCP/ECN,
    total length, identification, flags, fragment offset, TTL, protocol,
    checksum, source address and destination address.
    """

    source_ip: str
    destination_ip: str
    protocol: int
    payload: bytes
    ttl: int = 64

    def forward(self) -> None:
        """Simulate a router decrementing TTL."""
        self.ttl -= 1
        if self.ttl <= 0:
            raise RuntimeError("TTL expired. Router would discard the packet.")


@dataclass
class EncapsulatedMessage:
    """Represent the layered structure of a network message."""

    application: ApplicationData
    transport: TransportSegment
    network: IPv4Packet
    ethernet: EthernetFrame


def build_encapsulated_message() -> EncapsulatedMessage:
    """
    Build a simplified application -> transport -> network -> Ethernet stack.
    """
    application = ApplicationData(
        source_process="web-browser",
        destination_process="web-server",
        data=b"GET /index.html",
    )

    transport = TransportSegment(
        protocol="TCP",
        source_port=53000,
        destination_port=443,
        payload=application.data,
    )

    network = IPv4Packet(
        source_ip="192.168.1.10",
        destination_ip="93.184.216.34",
        protocol=6,
        payload=transport.payload,
    )

    ethernet = EthernetFrame(
        source_mac="00:00:00:00:00:0A",
        destination_mac="00:00:00:00:00:01",
        payload=network.payload,
    )

    return EncapsulatedMessage(
        application=application,
        transport=transport,
        network=network,
        ethernet=ethernet,
    )


def demonstrate_encapsulation() -> None:
    print("\n=== Encapsulation ===")

    message = build_encapsulated_message()

    print(f"Application data : {message.application.data!r}")
    print(
        f"Transport        : {message.transport.protocol} "
        f"{message.transport.source_port} -> "
        f"{message.transport.destination_port}"
    )
    print(
        f"Network          : {message.network.source_ip} -> "
        f"{message.network.destination_ip}"
    )
    print(
        f"Ethernet         : {message.ethernet.source_mac} -> "
        f"{message.ethernet.destination_mac}"
    )

    print(
        "\nConceptual order: "
        "Application data -> Transport segment -> IP packet -> Ethernet frame"
    )


# =============================================================================
# SECTION 10: PORTS AND SOCKETS
# =============================================================================

def demonstrate_ports() -> None:
    """
    Explain well-known, registered and dynamic/private ports.

    TCP and UDP use 16-bit port numbers, giving the range 0 through 65535.

    Common examples:
        22   SSH
        53   DNS
        80   HTTP
        443  HTTPS
    """
    print("\n=== Ports ===")

    services = {
        22: "SSH",
        53: "DNS",
        80: "HTTP",
        443: "HTTPS",
        3306: "MySQL",
        5432: "PostgreSQL",
    }

    for port, service in services.items():
        print(f"{port:5} -> {service}")

    dynamic_port = 53000
    print(f"Dynamic client-side example: {dynamic_port}")


def demonstrate_socket_information() -> None:
    """
    Use Python's standard socket module to show local networking information.

    This does not send network traffic.
    """
    print("\n=== Python Socket Information ===")

    for name, value in [
        ("Hostname", socket.gethostname()),
        ("IPv4 address for hostname", socket.gethostbyname(socket.gethostname())),
    ]:
        print(f"{name}: {value}")

    print("Socket constants:")
    print(f"AF_INET  = {socket.AF_INET}")
    print(f"SOCK_STREAM = {socket.SOCK_STREAM}")
    print(f"SOCK_DGRAM  = {socket.SOCK_DGRAM}")


# =============================================================================
# SECTION 11: TCP VS UDP
# =============================================================================

def compare_tcp_udp() -> None:
    """
    Compare TCP and UDP.

    TCP:
        Connection-oriented transport.
        Reliable ordered byte stream.
        Uses acknowledgements, retransmission and flow/congestion control.

    UDP:
        Connectionless datagram transport.
        Does not guarantee delivery, ordering or retransmission.
        Lower protocol overhead and useful when applications implement their
        own recovery or prioritize latency.
    """
    print("\n=== TCP vs UDP ===")

    comparison = [
        ("Connection", "Connection-oriented", "Connectionless"),
        ("Reliability", "Reliable delivery mechanisms", "No delivery guarantee"),
        ("Ordering", "Ordered byte stream", "No ordering guarantee"),
        ("Retransmission", "Supported", "Not built into UDP"),
        ("Flow control", "Supported", "Not provided by UDP itself"),
        ("Typical uses", "Web, SSH, file transfer", "DNS, streaming, real-time traffic"),
    ]

    print(f"{'Property':18} {'TCP':35} UDP")
    print("-" * 85)

    for property_name, tcp, udp in comparison:
        print(f"{property_name:18} {tcp:35} {udp}")


# =============================================================================
# SECTION 12: TCP STATE MACHINE
# =============================================================================

class TCPState(Enum):
    CLOSED = "CLOSED"
    LISTEN = "LISTEN"
    SYN_SENT = "SYN-SENT"
    SYN_RECEIVED = "SYN-RECEIVED"
    ESTABLISHED = "ESTABLISHED"
    FIN_WAIT_1 = "FIN-WAIT-1"
    FIN_WAIT_2 = "FIN-WAIT-2"
    CLOSE_WAIT = "CLOSE-WAIT"
    LAST_ACK = "LAST-ACK"
    TIME_WAIT = "TIME-WAIT"


class SimulatedTCPConnection:
    """
    Very small educational model of TCP connection establishment and closure.

    It does not implement real TCP and should not be used as a replacement for
    the operating system's TCP stack.
    """

    def __init__(self) -> None:
        self.client_state = TCPState.CLOSED
        self.server_state = TCPState.CLOSED

    def three_way_handshake(self) -> None:
        """
        Demonstrate:

            Client -> SYN
            Server -> SYN-ACK
            Client -> ACK
        """
        print("\nTCP three-way handshake")

        self.server_state = TCPState.LISTEN
        print(f"Server: {self.server_state.value}")

        self.client_state = TCPState.SYN_SENT
        print("Client -> SYN")

        self.server_state = TCPState.SYN_RECEIVED
        print("Server -> SYN-ACK")

        self.client_state = TCPState.ESTABLISHED
        self.server_state = TCPState.ESTABLISHED
        print("Client -> ACK")
        print(f"Client: {self.client_state.value}")
        print(f"Server: {self.server_state.value}")

    def four_step_close(self) -> None:
        """
        Simplified TCP connection termination.

        Real TCP closure involves FIN and ACK exchanges and can result in
        TIME-WAIT on one endpoint.
        """
        print("\nTCP connection closure")

        self.client_state = TCPState.FIN_WAIT_1
        print("Client -> FIN")

        self.server_state = TCPState.CLOSE_WAIT
        print("Server -> ACK")

        self.client_state = TCPState.FIN_WAIT_2
        print("Client: FIN-WAIT-2")

        self.server_state = TCPState.LAST_ACK
        print("Server -> FIN")

        self.client_state = TCPState.TIME_WAIT
        self.server_state = TCPState.CLOSED

        print("Client -> ACK")
        print(f"Client: {self.client_state.value}")
        print(f"Server: {self.server_state.value}")


# =============================================================================
# SECTION 13: ARP
# =============================================================================

class ARPCache:
    """
    Simplified IPv4-to-MAC address cache.

    ARP resolves a local IPv4 address to a MAC address on an Ethernet LAN.

    A host normally needs the MAC address of:
        - the destination host if it is on the local subnet, or
        - the default gateway if the destination is remote.
    """

    def __init__(self) -> None:
        self.entries: Dict[str, str] = {}

    def learn(self, ip: str, mac: str) -> None:
        self.entries[str(ipaddress.ip_address(ip))] = normalize_mac(mac)

    def lookup(self, ip: str) -> Optional[str]:
        return self.entries.get(str(ipaddress.ip_address(ip)))

    def display(self) -> None:
        print("\nARP cache")
        for ip, mac in sorted(self.entries.items()):
            print(f"{ip:15} -> {mac}")


def demonstrate_arp() -> None:
    print("\n=== ARP Simulation ===")

    arp = ARPCache()

    arp.learn("192.168.1.1", "00:00:00:00:00:01")
    arp.learn("192.168.1.20", "00:00:00:00:00:14")

    print(f"MAC for 192.168.1.1: {arp.lookup('192.168.1.1')}")
    print(f"MAC for 192.168.1.99: {arp.lookup('192.168.1.99')}")

    arp.display()


# =============================================================================
# SECTION 14: DNS
# =============================================================================

def demonstrate_dns() -> None:
    """
    Demonstrate DNS conceptually and use Python's resolver where available.

    DNS maps names such as example.com to network addresses.

    DNS can resolve many record types, including:
        A       IPv4 address
        AAAA    IPv6 address
        CNAME   Canonical name
        MX      Mail exchanger
        NS      Name server
        TXT     Text information
    """
    print("\n=== DNS ===")

    domain = "example.com"

    try:
        addresses = socket.getaddrinfo(
            domain,
            80,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )

        unique_addresses = sorted(
            {result[4][0] for result in addresses}
        )

        print(f"{domain} IPv4 addresses:")
        for address in unique_addresses:
            print(f"  {address}")
    except socket.gaierror as exc:
        print(f"DNS lookup failed: {exc}")


# =============================================================================
# SECTION 15: DHCP
# =============================================================================

def explain_dhcp() -> None:
    """
    Demonstrate the conceptual DHCP DORA process.

    DORA:
        Discover
        Offer
        Request
        Acknowledge

    DHCP can provide:
        - IP address
        - subnet mask/prefix
        - default gateway
        - DNS servers
        - lease duration
    """
    print("\n=== DHCP ===")

    steps = [
        ("DISCOVER", "Client broadcasts that it needs network configuration."),
        ("OFFER", "DHCP server offers an address and configuration."),
        ("REQUEST", "Client requests the offered configuration."),
        ("ACK", "Server confirms the lease."),
    ]

    for message, explanation in steps:
        print(f"{message:9}: {explanation}")


# =============================================================================
# SECTION 16: NAT
# =============================================================================

@dataclass
class NATMapping:
    """Simplified source NAT/PAT translation."""

    private_ip: str
    private_port: int
    public_ip: str
    public_port: int
    destination_ip: str
    destination_port: int


class NATTable:
    """
    Simplified Port Address Translation table.

    Home/office routers often translate many private internal endpoints to one
    public IPv4 address by using different source ports.
    """

    def __init__(self, public_ip: str) -> None:
        self.public_ip = public_ip
        self.next_port = 40000
        self.mappings: Dict[Tuple[str, int, str, int], NATMapping] = {}

    def translate_outbound(
        self,
        private_ip: str,
        private_port: int,
        destination_ip: str,
        destination_port: int,
    ) -> NATMapping:
        key = (
            private_ip,
            private_port,
            destination_ip,
            destination_port,
        )

        if key not in self.mappings:
            mapping = NATMapping(
                private_ip=private_ip,
                private_port=private_port,
                public_ip=self.public_ip,
                public_port=self.next_port,
                destination_ip=destination_ip,
                destination_port=destination_port,
            )
            self.mappings[key] = mapping
            self.next_port += 1

        return self.mappings[key]

    def display(self) -> None:
        print("\nNAT table")
        for mapping in self.mappings.values():
            print(
                f"{mapping.private_ip}:{mapping.private_port} "
                f"-> {mapping.public_ip}:{mapping.public_port} "
                f"-> {mapping.destination_ip}:{mapping.destination_port}"
            )


def demonstrate_nat() -> None:
    print("\n=== NAT/PAT Simulation ===")

    nat = NATTable("203.0.113.10")

    nat.translate_outbound(
        "192.168.1.10",
        53000,
        "93.184.216.34",
        443,
    )

    nat.translate_outbound(
        "192.168.1.11",
        53001,
        "93.184.216.34",
        443,
    )

    nat.display()


# =============================================================================
# SECTION 17: PACKET TTL AND HOPS
# =============================================================================

def simulate_packet_hops(
    source: str,
    destination: str,
    routers: int,
    initial_ttl: int = 8,
) -> None:
    """
    Simulate packet traversal through a sequence of routers.

    Every router decrements IPv4 TTL by one. If TTL reaches zero, the packet is
    discarded. This mechanism prevents packets from circulating indefinitely
    because of routing loops.
    """
    print("\n=== TTL and Hop Simulation ===")

    packet = IPv4Packet(
        source_ip=source,
        destination_ip=destination,
        protocol=6,
        payload=b"network data",
        ttl=initial_ttl,
    )

    print(f"Initial TTL: {packet.ttl}")

    for hop in range(1, routers + 1):
        try:
            packet.forward()
        except RuntimeError as exc:
            print(f"Router {hop}: {exc}")
            return

        print(f"Router {hop}: TTL={packet.ttl}")

    print("Packet reached the destination in the simulation.")


# =============================================================================
# SECTION 18: BROADCAST DOMAINS AND COLLISION DOMAINS
# =============================================================================

def explain_network_domains() -> None:
    """
    Explain two important LAN concepts.

    Collision domain:
        The portion of a network where simultaneous transmissions can collide.
        Traditional shared Ethernet hubs created one collision domain.

    Broadcast domain:
        The set of devices that receive a Layer-2 broadcast.

    A Layer-2 switch normally creates a separate collision domain per port
    when operating with full-duplex links. VLANs can divide broadcast domains.
    Routers also separate Layer-2 broadcast domains.
    """
    print("\n=== Collision and Broadcast Domains ===")

    print("Switch:")
    print("  - Each full-duplex switch port normally forms its own collision domain.")
    print("  - A VLAN is commonly used to define a Layer-2 broadcast domain.")

    print("Router:")
    print("  - Separates Layer-2 broadcast domains.")
    print("  - Routes packets between IP networks.")


# =============================================================================
# SECTION 19: BANDWIDTH, THROUGHPUT AND LATENCY
# =============================================================================

def calculate_transfer_time(
    size_megabytes: float,
    bandwidth_megabits_per_second: float,
) -> float:
    """
    Estimate ideal transfer time.

    Conversion:
        1 byte = 8 bits
        1 MB is treated as 1,000,000 bytes for this educational calculation.

    Real transfer time is usually longer because of protocol overhead,
    congestion, latency, packet loss, encryption, CPU limits and storage speed.
    """
    if size_megabytes < 0:
        raise ValueError("Data size cannot be negative.")
    if bandwidth_megabit_per_second <= 0:
        raise ValueError("Bandwidth must be positive.")

    total_megabits = size_megabytes * 8
    return total_megabits / bandwidth_megabit_per_second


def demonstrate_network_performance() -> None:
    print("\n=== Bandwidth, Throughput and Latency ===")

    size_mb = 100
    bandwidth_mbps = 100

    seconds = calculate_transfer_time(size_mb, bandwidth_mbps)

    print(f"Data size          : {size_mb} MB")
    print(f"Theoretical link   : {bandwidth_mbps} Mbps")
    print(f"Ideal transfer time: {seconds:.2f} seconds")

    print("\nImportant distinctions:")
    print("Bandwidth   = maximum capacity of a communication link.")
    print("Throughput  = actual useful data delivered per unit time.")
    print("Latency     = time required for data to travel between endpoints.")
    print("Jitter      = variation in packet delay.")
    print("Packet loss = packets that fail to reach the destination.")


# =============================================================================
# SECTION 20: BANDWIDTH-DELAY PRODUCT
# =============================================================================

def bandwidth_delay_product(
    bandwidth_mbps: float,
    round_trip_time_ms: float,
) -> float:
    """
    Calculate approximate bandwidth-delay product in bytes.

    BDP is useful when reasoning about how much data may be in flight on a path.
    """
    if bandwidth_mbps <= 0:
        raise ValueError("Bandwidth must be positive.")
    if round_trip_time_ms < 0:
        raise ValueError("RTT cannot be negative.")

    bits = bandwidth_mbps * 1_000_000 * (round_trip_time_ms / 1000)
    return bits / 8


def demonstrate_bdp() -> None:
    print("\n=== Bandwidth-Delay Product ===")

    bdp_bytes = bandwidth_delay_product(1000, 50)

    print("Link bandwidth: 1000 Mbps")
    print("Round-trip time: 50 ms")
    print(f"Approximate data in flight: {bdp_bytes / 1_000_000:.2f} MB")


# =============================================================================
# SECTION 21: PACKET LOSS AND RETRANSMISSION
# =============================================================================

@dataclass
class TransmissionResult:
    attempts: int
    delivered: bool
    lost_packets: int


def simulate_reliable_transmission(
    packet_count: int,
    packet_loss_probability: float,
    seed: int = 42,
) -> TransmissionResult:
    """
    Simulate a simple retransmission mechanism.

    This is intentionally simpler than TCP. TCP has sequence numbers,
    acknowledgements, timers, congestion control and sophisticated algorithms.
    """
    if packet_count < 0:
        raise ValueError("Packet count cannot be negative.")

    if not 0 <= packet_loss_probability <= 1:
        raise ValueError("Loss probability must be between 0 and 1.")

    random_generator = random.Random(seed)

    attempts = 0
    lost_packets = 0

    for packet_number in range(packet_count):
        delivered = False

        while not delivered:
            attempts += 1

            if random_generator.random() < packet_loss_probability:
                lost_packets += 1
                print(
                    f"Packet {packet_number + 1}: lost, "
                    f"retransmitting..."
                )
            else:
                delivered = True

    return TransmissionResult(
        attempts=attempts,
        delivered=True,
        lost_packets=lost_packets,
    )


def demonstrate_packet_loss() -> None:
    print("\n=== Packet Loss and Retransmission ===")

    result = simulate_reliable_transmission(
        packet_count=10,
        packet_loss_probability=0.20,
    )

    print(f"Total transmission attempts: {result.attempts}")
    print(f"Lost transmissions: {result.lost_packets}")
    print(f"All packets delivered: {result.delivered}")


# =============================================================================
# SECTION 22: MTU AND FRAGMENTATION CONCEPT
# =============================================================================

def calculate_fragment_count(
    payload_bytes: int,
    mtu: int = 1500,
    ip_header_bytes: int = 20,
) -> int:
    """
    Estimate how many IPv4 packets are needed for a payload.

    Real IPv4 fragmentation has alignment requirements because fragment offsets
    are expressed in units of 8 bytes. Modern applications often try to avoid
    fragmentation through path MTU discovery.
    """
    if payload_bytes < 0:
        raise ValueError("Payload cannot be negative.")
    if mtu <= ip_header_bytes:
        raise ValueError("MTU must be larger than the IP header.")
    if payload_bytes == 0:
        return 0

    payload_per_packet = mtu - ip_header_bytes

    return (payload_bytes + payload_per_packet - 1) // payload_per_packet


def demonstrate_mtu() -> None:
    print("\n=== MTU and Fragmentation ===")

    payload = 4000
    mtu = 1500

    fragments = calculate_fragment_count(payload, mtu)

    print(f"Payload: {payload} bytes")
    print(f"MTU: {mtu} bytes")
    print(f"Estimated packets required: {fragments}")

    print(
        "\nMTU is the maximum Layer-3 packet size supported on a link/path "
        "under the relevant protocol and configuration."
    )


# =============================================================================
# SECTION 23: IP SUBNET DESIGN
# =============================================================================

def subnet_capacity(prefix_length: int) -> Tuple[int, int]:
    """
    Return total IPv4 addresses and traditional usable-host count.

    The traditional IPv4 host calculation reserves network and broadcast
    addresses. /31 and /32 have special uses, so production calculations must
    account for the actual addressing model.
    """
    if not 0 <= prefix_length <= 32:
        raise ValueError("IPv4 prefix must be between 0 and 32.")

    total = 2 ** (32 - prefix_length)

    if prefix_length <= 30:
        usable = total - 2
    elif prefix_length == 31:
        usable = 2
    else:
        usable = 1

    return total, usable


def demonstrate_prefix_capacity() -> None:
    print("\n=== IPv4 Prefix Capacity ===")

    for prefix in [8, 16, 24, 25, 26, 30, 31, 32]:
        total, usable = subnet_capacity(prefix)
        print(
            f"/{prefix:2}: "
            f"total={total:10} "
            f"traditional/special usable={usable:10}"
        )


# =============================================================================
# SECTION 24: ROUTER SIMULATION
# =============================================================================

@dataclass
class SimulatedPacket:
    source_ip: str
    destination_ip: str
    ttl: int
    payload: bytes


class Router:
    """
    Simplified Layer-3 router.

    The router:
        1. Receives an IP packet.
        2. Checks TTL.
        3. Looks up the destination route.
        4. Decrements TTL.
        5. Forwards the packet through the selected interface.

    Real routers also perform many other functions such as ACL filtering,
    NAT, QoS, routing protocol processing, hardware forwarding and telemetry.
    """

    def __init__(self, name: str, routing_table: RoutingTable) -> None:
        self.name = name
        self.routing_table = routing_table

    def forward(self, packet: SimulatedPacket) -> Optional[Route]:
        if packet.ttl <= 1:
            print(
                f"{self.name}: TTL expired. "
                f"Packet to {packet.destination_ip} dropped."
            )
            return None

        route = self.routing_table.lookup(packet.destination_ip)

        if route is None:
            print(
                f"{self.name}: no route to {packet.destination_ip}. "
                f"Packet dropped."
            )
            return None

        packet.ttl -= 1

        print(
            f"{self.name}: forwarding {packet.source_ip} -> "
            f"{packet.destination_ip}, "
            f"TTL={packet.ttl}, "
            f"via {route.interface}"
        )

        return route


def demonstrate_router() -> None:
    print("\n=== Router Simulation ===")

    table = RoutingTable()
    table.add_route("192.168.1.0/24", None, "LAN")
    table.add_route("192.168.2.0/24", "10.0.0.2", "WAN")
    table.add_route("0.0.0.0/0", "10.0.0.1", "WAN")

    router = Router("R1", table)

    packet = SimulatedPacket(
        source_ip="192.168.1.10",
        destination_ip="192.168.2.20",
        ttl=5,
        payload=b"hello router",
    )

    router.forward(packet)


# =============================================================================
# SECTION 25: CLIENT-SERVER COMMUNICATION
# =============================================================================

def create_loopback_server(
    host: str = "127.0.0.1",
    port: int = 0,
) -> Tuple[socket.socket, int]:
    """
    Create a local TCP server socket.

    Port 0 asks the operating system to choose an available ephemeral port.

    The socket is returned in listening state. The caller is responsible for
    closing it.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # SO_REUSEADDR helps avoid some short-lived rebinding problems during
    # development. It does not make a network service secure.
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind((host, port))
    server.listen(1)

    actual_port = server.getsockname()[1]

    return server, actual_port


def demonstrate_local_socket_server() -> None:
    """
    Demonstrate a complete local TCP client/server exchange.

    Only loopback traffic is used, so the example does not expose a service to
    the local network.
    """
    print("\n=== Local TCP Client/Server Example ===")

    server, port = create_loopback_server()

    try:
        server.settimeout(2.0)

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)

        try:
            client.connect(("127.0.0.1", port))

            connection, address = server.accept()

            try:
                connection.settimeout(2.0)

                message = b"Hello from client"
                client.sendall(message)

                received = connection.recv(1024)

                print(f"Server received: {received.decode('utf-8')}")

                response = b"Hello from server"
                connection.sendall(response)

                reply = client.recv(1024)

                print(f"Client received: {reply.decode('utf-8')}")
                print(f"Server peer address: {address}")
            finally:
                connection.close()
        finally:
            client.close()
    finally:
        server.close()


# =============================================================================
# SECTION 26: UDP CONCEPTUAL EXAMPLE
# =============================================================================

def demonstrate_udp_loopback() -> None:
    """
    Demonstrate local UDP datagram exchange.

    UDP does not establish a TCP-style connection. Each datagram is sent
    independently.
    """
    print("\n=== Local UDP Example ===")

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        server.bind(("127.0.0.1", 0))
        server_port = server.getsockname()[1]
        server.settimeout(2.0)

        client.settimeout(2.0)

        client.sendto(
            b"UDP message",
            ("127.0.0.1", server_port),
        )

        received, sender = server.recvfrom(1024)

        print(f"Server received: {received.decode('utf-8')}")
        print(f"Sender: {sender}")

        server.sendto(
            b"UDP reply",
            sender,
        )

        reply, _ = client.recvfrom(1024)

        print(f"Client received: {reply.decode('utf-8')}")
    finally:
        client.close()
        server.close()


# =============================================================================
# SECTION 27: IPV4 HEADER CONCEPTS
# =============================================================================

def demonstrate_ipv4_header_structure() -> None:
    """
    Show important IPv4 header fields.

    This does not construct a production-valid IP packet. It demonstrates the
    conceptual fields found in the IPv4 header.
    """
    print("\n=== IPv4 Header Fields ===")

    fields = [
        ("Version", "IPv4 uses value 4."),
        ("IHL", "Length of the IPv4 header."),
        ("DSCP/ECN", "Traffic classification and congestion notification."),
        ("Total Length", "Entire IPv4 packet size."),
        ("Identification", "Used in fragmentation/reassembly."),
        ("Flags", "Controls fragmentation behavior."),
        ("Fragment Offset", "Position of a fragment."),
        ("TTL", "Limits packet lifetime through routers."),
        ("Protocol", "Identifies the transport/next-layer protocol."),
        ("Header Checksum", "Detects corruption in the IPv4 header."),
        ("Source Address", "Sender IPv4 address."),
        ("Destination Address", "Receiver IPv4 address."),
    ]

    for field_name, purpose in fields:
        print(f"{field_name:20}: {purpose}")


# =============================================================================
# SECTION 28: IPV6
# =============================================================================

def demonstrate_ipv6() -> None:
    """
    Demonstrate IPv6 representation and subnetting.

    IPv6 uses 128-bit addresses and removes the fundamental IPv4 address-space
    limitation. IPv6 uses Neighbor Discovery instead of ARP and does not use
    broadcast in the IPv4 sense.
    """
    print("\n=== IPv6 ===")

    addresses = [
        "2001:db8::1",
        "2001:db8:1234:5678::10",
        "fe80::1234",
        "::1",
    ]

    for address_text in addresses:
        address = ipaddress.ip_address(address_text)
        print(
            f"{address_text:30} -> "
            f"compressed={address.compressed}, "
            f"expanded={address.exploded}"
        )

    network = ipaddress.ip_network("2001:db8:abcd::/48")

    print(f"\nIPv6 example network: {network}")
    print(f"Prefix length: {network.prefixlen}")
    print(f"Address count: {network.num_addresses}")


# =============================================================================
# SECTION 29: OSI MODEL
# =============================================================================

def demonstrate_osi_model() -> None:
    """
    Present the seven-layer OSI reference model.

    The OSI model is primarily a conceptual framework. Real protocol stacks do
    not always map cleanly to exactly one OSI layer.
    """
    print("\n=== OSI Reference Model ===")

    layers = [
        (7, "Application", "HTTP, DNS, SMTP"),
        (6, "Presentation", "Encoding, serialization, encryption concepts"),
        (5, "Session", "Session management concepts"),
        (4, "Transport", "TCP, UDP"),
        (3, "Network", "IP, routing"),
        (2, "Data Link", "Ethernet, MAC, switching"),
        (1, "Physical", "Signals, cables, radio, optical transmission"),
    ]

    for number, name, examples in layers:
        print(f"{number}. {name:14} -> {examples}")


# =============================================================================
# SECTION 30: TCP/IP MODEL
# =============================================================================

def demonstrate_tcp_ip_model() -> None:
    """
    Present the practical TCP/IP model.

    Common representations use four layers:
        Application
        Transport
        Internet
        Link

    Some educational material uses a five-layer model by separating the
    physical layer from the data-link layer.
    """
    print("\n=== TCP/IP Model ===")

    layers = [
        ("Application", "HTTP, DNS, DHCP, SSH"),
        ("Transport", "TCP, UDP"),
        ("Internet", "IPv4, IPv6, ICMP"),
        ("Link", "Ethernet, Wi-Fi"),
    ]

    for name, protocols in layers:
        print(f"{name:12}: {protocols}")


# =============================================================================
# SECTION 31: ICMP AND DIAGNOSTICS
# =============================================================================

def demonstrate_icmp_concepts() -> None:
    """
    Explain ICMP's diagnostic/control role.

    Ping commonly uses ICMP Echo Request and Echo Reply for IPv4/IPv6.

    Traceroute-style diagnostics use TTL/hop-limit behavior and ICMP responses
    to infer the path through routers.
    """
    print("\n=== ICMP and Diagnostics ===")

    examples = {
        "Echo Request": "Used by ping to ask whether a destination responds.",
        "Echo Reply": "Response to an Echo Request.",
        "Time Exceeded": "Can indicate that a packet's TTL/hop limit expired.",
        "Destination Unreachable": "Reports certain forwarding/delivery failures.",
    }

    for message_type, purpose in examples.items():
        print(f"{message_type:22}: {purpose}")


# =============================================================================
# SECTION 32: NETWORK ADDRESS CLASSIFICATION
# =============================================================================

def classify_ipv4_address(address_text: str) -> List[str]:
    """Return useful classifications for an IPv4 address."""
    address = ipaddress.ip_address(address_text)

    classifications = []

    if address.is_private:
        classifications.append("private")
    if address.is_loopback:
        classifications.append("loopback")
    if address.is_link_local:
        classifications.append("link-local")
    if address.is_multicast:
        classifications.append("multicast")
    if address.is_reserved:
        classifications.append("reserved")
    if not classifications:
        classifications.append("globally-routable-or-special")

    return classifications


def demonstrate_address_classification() -> None:
    print("\n=== IPv4 Address Classification ===")

    for address in [
        "127.0.0.1",
        "192.168.1.10",
        "10.0.0.1",
        "169.254.1.20",
        "224.0.0.1",
        "8.8.8.8",
    ]:
        print(f"{address:15}: {', '.join(classify_ipv4_address(address))}")


# =============================================================================
# SECTION 33: ROUTING ALGORITHM CONCEPT
# =============================================================================

@dataclass
class GraphEdge:
    source: str
    destination: str
    cost: float


def dijkstra(
    nodes: Iterable[str],
    edges: Iterable[GraphEdge],
    source: str,
) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
    """
    Compute shortest paths using Dijkstra's algorithm.

    Routing protocols can use different algorithms and mechanisms. This
    implementation is an educational example of graph-based shortest paths.

    Time complexity of this straightforward implementation is O(V^2 + E).
    A priority queue can improve the typical implementation to approximately
    O((V + E) log V).
    """
    node_list = list(nodes)
    adjacency: Dict[str, List[Tuple[str, float]]] = {
        node: [] for node in node_list
    }

    for edge in edges:
        if edge.source not in adjacency or edge.destination not in adjacency:
            raise ValueError("Every edge endpoint must be in nodes.")

        if edge.cost < 0:
            raise ValueError("Dijkstra requires non-negative edge costs.")

        adjacency[edge.source].append((edge.destination, edge.cost))
        adjacency[edge.destination].append((edge.source, edge.cost))

    distances = {node: float("inf") for node in node_list}
    previous: Dict[str, Optional[str]] = {
        node: None for node in node_list
    }

    distances[source] = 0
    unvisited = set(node_list)

    while unvisited:
        current = min(
            unvisited,
            key=lambda node: distances[node],
        )

        if distances[current] == float("inf"):
            break

        unvisited.remove(current)

        for neighbor, cost in adjacency[current]:
            candidate = distances[current] + cost

            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = current

    return distances, previous


def reconstruct_path(
    previous: Dict[str, Optional[str]],
    destination: str,
) -> List[str]:
    """Reconstruct a shortest path from a predecessor map."""
    path = []
    current: Optional[str] = destination

    while current is not None:
        path.append(current)
        current = previous[current]

    path.reverse()
    return path


def demonstrate_dijkstra() -> None:
    print("\n=== Shortest-Path Routing Concept ===")

    nodes = ["A", "B", "C", "D", "E"]

    edges = [
        GraphEdge("A", "B", 2),
        GraphEdge("A", "C", 5),
        GraphEdge("B", "C", 1),
        GraphEdge("B", "D", 4),
        GraphEdge("C", "D", 1),
        GraphEdge("D", "E", 3),
    ]

    distances, previous = dijkstra(nodes, edges, "A")

    for destination in nodes:
        path = reconstruct_path(previous, destination)
        print(
            f"A -> {destination}: "
            f"cost={distances[destination]}, "
            f"path={' -> '.join(path)}"
        )


# =============================================================================
# SECTION 34: VLAN CONCEPT
# =============================================================================

@dataclass
class VLANPort:
    port: int
    vlan_id: int


class VLANTable:
    """
    Simplified VLAN membership table.

    VLANs logically separate Layer-2 broadcast domains on the same physical
    switching infrastructure.
    """

    def __init__(self) -> None:
        self.ports: Dict[int, VLANPort] = {}

    def assign(self, port: int, vlan_id: int) -> None:
        if vlan_id < 1 or vlan_id > 4094:
            raise ValueError("Typical IEEE 802.1Q VLAN IDs are 1 through 4094.")
        self.ports[port] = VLANPort(port, vlan_id)

    def can_forward(self, source_port: int, destination_port: int) -> bool:
        source = self.ports[source_port]
        destination = self.ports[destination_port]
        return source.vlan_id == destination.vlan_id


def demonstrate_vlans() -> None:
    print("\n=== VLAN Concept ===")

    vlan_table = VLANTable()

    vlan_table.assign(1, 10)
    vlan_table.assign(2, 10)
    vlan_table.assign(3, 20)
    vlan_table.assign(4, 20)

    tests = [
        (1, 2),
        (1, 3),
        (3, 4),
    ]

    for source, destination in tests:
        print(
            f"Port {source} -> Port {destination}: "
            f"same VLAN = {vlan_table.can_forward(source, destination)}"
        )

    print(
        "\nVLANs separate Layer-2 broadcast domains. "
        "Communication between VLANs normally requires Layer-3 routing."
    )


# =============================================================================
# SECTION 35: DEFAULT GATEWAY
# =============================================================================

def determine_next_hop(
    source_ip: str,
    destination_ip: str,
    local_network: str,
    gateway_ip: str,
) -> str:
    """
    Decide whether an endpoint sends directly to a local host or to its gateway.
    """
    source = ipaddress.ip_address(source_ip)
    destination = ipaddress.ip_address(destination_ip)
    network = ipaddress.ip_network(local_network)

    if source not in network:
        raise ValueError("Source address is not in the declared local network.")

    if destination in network:
        return "directly to destination host"

    return gateway_ip


def demonstrate_default_gateway() -> None:
    print("\n=== Default Gateway ===")

    source = "192.168.1.10"
    local_network = "192.168.1.0/24"
    gateway = "192.168.1.1"

    for destination in [
        "192.168.1.20",
        "8.8.8.8",
    ]:
        next_hop = determine_next_hop(
            source,
            destination,
            local_network,
            gateway,
        )

        print(
            f"{source} -> {destination}: "
            f"next hop = {next_hop}"
        )


# =============================================================================
# SECTION 36: NETWORK SECURITY
# =============================================================================

def demonstrate_network_security_principles() -> None:
    """
    Present defensive networking principles.

    These examples describe architecture and validation rather than offensive
    techniques.
    """
    print("\n=== Network Security Principles ===")

    principles = [
        (
            "Segmentation",
            "Separate systems into controlled network zones or VLANs."
        ),
        (
            "Least privilege",
            "Allow only required network flows and services."
        ),
        (
            "Encryption",
            "Protect data in transit using protocols such as TLS."
        ),
        (
            "Authentication",
            "Verify users/devices before granting access."
        ),
        (
            "Firewalls",
            "Control traffic according to explicit security policy."
        ),
        (
            "Monitoring",
            "Collect logs, metrics and security telemetry."
        ),
        (
            "Secure management",
            "Use protected administrative protocols and strong credentials."
        ),
        (
            "Patch management",
            "Keep network operating systems and services maintained."
        ),
    ]

    for principle, explanation in principles:
        print(f"{principle:20}: {explanation}")


# =============================================================================
# SECTION 37: FIREWALL RULE SIMULATION
# =============================================================================

@dataclass
class FirewallRule:
    protocol: str
    destination_port: Optional[int]
    action: str


class SimpleFirewall:
    """
    Educational allow/deny firewall model.

    A production firewall uses substantially more context, including source and
    destination addresses, connection state, interfaces, zones, identities,
    application protocols and logging policy.
    """

    def __init__(self, default_action: str = "DENY") -> None:
        self.default_action = default_action
        self.rules: List[FirewallRule] = []

    def add_rule(
        self,
        protocol: str,
        destination_port: Optional[int],
        action: str,
    ) -> None:
        action = action.upper()

        if action not in {"ALLOW", "DENY"}:
            raise ValueError("Action must be ALLOW or DENY.")

        self.rules.append(
            FirewallRule(
                protocol=protocol.upper(),
                destination_port=destination_port,
                action=action,
            )
        )

    def evaluate(
        self,
        protocol: str,
        destination_port: int,
    ) -> str:
        protocol = protocol.upper()

        for rule in self.rules:
            protocol_matches = (
                rule.protocol == protocol or rule.protocol == "ANY"
            )

            port_matches = (
                rule.destination_port is None
                or rule.destination_port == destination_port
            )

            if protocol_matches and port_matches:
                return rule.action

        return self.default_action


def demonstrate_firewall() -> None:
    print("\n=== Firewall Rule Simulation ===")

    firewall = SimpleFirewall(default_action="DENY")

    firewall.add_rule("TCP", 443, "ALLOW")
    firewall.add_rule("TCP", 22, "ALLOW")

    tests = [
        ("TCP", 443),
        ("TCP", 22),
        ("TCP", 23),
        ("UDP", 53),
    ]

    for protocol, port in tests:
        decision = firewall.evaluate(protocol, port)
        print(f"{protocol}/{port}: {decision}")


# =============================================================================
# SECTION 38: NETWORK VALIDATION AND ERROR HANDLING
# =============================================================================

def validate_network_configuration(
    ip_address: str,
    subnet: str,
    gateway: str,
) -> List[str]:
    """
    Validate a basic endpoint network configuration.

    This function illustrates how configuration validation can detect common
    mistakes before a service starts.
    """
    errors: List[str] = []

    try:
        ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return ["Invalid IP address."]

    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return ["Invalid subnet."]

    try:
        gateway_address = ipaddress.ip_address(gateway)
    except ValueError:
        return ["Invalid gateway address."]

    if ip.version != network.version:
        errors.append("IP address and subnet use different IP versions.")

    if gateway_address.version != network.version:
        errors.append("Gateway and subnet use different IP versions.")

    if ip not in network:
        errors.append("IP address does not belong to the declared subnet.")

    if gateway_address not in network:
        errors.append("Gateway does not belong to the declared subnet.")

    if ip == gateway_address:
        errors.append("Host IP and gateway IP must not be identical.")

    return errors


def demonstrate_configuration_validation() -> None:
    print("\n=== Network Configuration Validation ===")

    configurations = [
        ("192.168.1.10", "192.168.1.0/24", "192.168.1.1"),
        ("192.168.2.10", "192.168.1.0/24", "192.168.1.1"),
        ("192.168.1.10", "192.168.1.0/24", "192.168.2.1"),
    ]

    for ip, subnet, gateway in configurations:
        errors = validate_network_configuration(
            ip,
            subnet,
            gateway,
        )

        if errors:
            print(f"{ip} / {subnet} / gateway {gateway}:")
            for error in errors:
                print(f"  ERROR: {error}")
        else:
            print(f"{ip}: configuration valid")


# =============================================================================
# SECTION 39: PACKET HEADER OVERHEAD
# =============================================================================

def estimate_ethernet_ipv4_tcp_overhead(
    application_bytes: int,
) -> Tuple[int, float]:
    """
    Estimate common header overhead for one TCP-over-IPv4-over-Ethernet frame.

    Simplified values:
        Ethernet header = 14 bytes
        IPv4 header    = 20 bytes
        TCP header     = 20 bytes

    Ethernet FCS, preamble, inter-frame gap, TCP/IP options, VLAN tags and
    other physical/link overhead are excluded from this simplified calculation.
    """
    if application_bytes < 0:
        raise ValueError("Application data cannot be negative.")

    overhead = 14 + 20 + 20
    total = application_bytes + overhead

    efficiency = (
        application_bytes / total * 100
        if total
        else 0
    )

    return total, efficiency


def demonstrate_protocol_overhead() -> None:
    print("\n=== Protocol Overhead ===")

    application_bytes = 1000
    total, efficiency = estimate_ethernet_ipv4_tcp_overhead(
        application_bytes
    )

    print(f"Application data: {application_bytes} bytes")
    print(f"Simplified total: {total} bytes")
    print(f"Payload efficiency: {efficiency:.2f}%")


# =============================================================================
# SECTION 40: QUEUING AND CONGESTION CONCEPT
# =============================================================================

@dataclass
class QueueSimulator:
    """
    Simple FIFO packet queue.

    Real network devices use more sophisticated queue management and scheduling,
    including priority queues, weighted scheduling and active queue management.
    """

    capacity: int
    queue: List[int] = field(default_factory=list)
    dropped: int = 0

    def enqueue(self, packet_id: int) -> bool:
        if len(self.queue) >= self.capacity:
            self.dropped += 1
            return False

        self.queue.append(packet_id)
        return True

    def dequeue(self) -> Optional[int]:
        if not self.queue:
            return None

        return self.queue.pop(0)


def demonstrate_queueing() -> None:
    print("\n=== Queueing and Congestion ===")

    queue = QueueSimulator(capacity=3)

    for packet_id in range(1, 6):
        accepted = queue.enqueue(packet_id)
        print(
            f"Packet {packet_id}: "
            f"{'queued' if accepted else 'dropped'}"
        )

    print(f"Queue contents: {queue.queue}")
    print(f"Dropped packets: {queue.dropped}")

    print("\nServing queue:")
    while True:
        packet = queue.dequeue()

        if packet is None:
            break

        print(f"Transmitted packet {packet}")


# =============================================================================
# SECTION 41: ROUTING FAILURE AND REDUNDANCY
# =============================================================================

@dataclass
class RedundantRoute:
    destination: ipaddress.IPv4Network
    next_hop: str
    metric: int
    active: bool = True


def select_best_active_route(
    routes: List[RedundantRoute],
    destination: str,
) -> Optional[RedundantRoute]:
    """
    Select the best active route using prefix specificity followed by metric.
    """
    destination_ip = ipaddress.ip_address(destination)

    candidates = [
        route
        for route in routes
        if route.active and destination_ip in route.destination
    ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda route: (
            route.destination.prefixlen,
            -route.metric,
        ),
        reverse=True,
    )

    return candidates[0]


def demonstrate_route_redundancy() -> None:
    print("\n=== Route Redundancy ===")

    routes = [
        RedundantRoute(
            ipaddress.ip_network("0.0.0.0/0"),
            "ISP-A",
            10,
        ),
        RedundantRoute(
            ipaddress.ip_network("0.0.0.0/0"),
            "ISP-B",
            20,
        ),
    ]

    destination = "8.8.8.8"

    selected = select_best_active_route(routes, destination)

    print(
        f"Initial route to {destination}: "
        f"{selected.next_hop if selected else 'none'}"
    )

    routes[0].active = False

    selected = select_best_active_route(routes, destination)

    print(
        f"After ISP-A failure: "
        f"{selected.next_hop if selected else 'none'}"
    )


# =============================================================================
# SECTION 42: NETWORK TROUBLESHOOTING WORKFLOW
# =============================================================================

def troubleshooting_checklist() -> None:
    """
    Present a structured troubleshooting sequence.

    Troubleshooting should move from simple lower-level causes toward higher
    layers rather than immediately changing many variables at once.
    """
    print("\n=== Network Troubleshooting Workflow ===")

    steps = [
        "1. Confirm physical/link status.",
        "2. Check interface configuration.",
        "3. Verify IP address and subnet.",
        "4. Verify default gateway.",
        "5. Check ARP/neighbor resolution on local networks.",
        "6. Test the local gateway.",
        "7. Check routing tables.",
        "8. Test name resolution separately from IP connectivity.",
        "9. Check transport ports and service availability.",
        "10. Inspect firewall/security policy.",
        "11. Check latency, packet loss and congestion.",
        "12. Review logs and packet captures when necessary.",
    ]

    for step in steps:
        print(step)


def classify_common_failure(symptom: str) -> str:
    """
    Give a basic diagnostic interpretation.

    This is not a complete diagnostic engine. It demonstrates the principle of
    mapping symptoms to likely networking layers.
    """
    normalized = symptom.lower()

    if "no link" in normalized or "cable" in normalized:
        return "Investigate physical/link-layer connectivity."
    if "same subnet" in normalized:
        return "Investigate IP addressing, subnet mask and ARP."
    if "gateway" in normalized:
        return "Investigate default gateway and local routing."
    if "dns" in normalized or "name" in normalized:
        return "Investigate DNS configuration and resolver reachability."
    if "port" in normalized or "connection refused" in normalized:
        return "Investigate transport-layer service availability and firewall rules."
    if "slow" in normalized or "latency" in normalized:
        return "Investigate congestion, path length, bandwidth, queueing and server performance."

    return "Collect more evidence across physical, link, network and transport layers."


def demonstrate_troubleshooting() -> None:
    print("\n=== Troubleshooting Classification ===")

    symptoms = [
        "no link light",
        "wrong gateway",
        "DNS name does not resolve",
        "connection refused on port",
        "network is slow",
    ]

    for symptom in symptoms:
        print(f"{symptom:35} -> {classify_common_failure(symptom)}")


# =============================================================================
# SECTION 43: PACKET FLOW THROUGH A HOME/OFFICE NETWORK
# =============================================================================

def simulate_home_network_packet_flow() -> None:
    """
    Trace a simplified request from a local computer to an Internet server.

    Conceptual path:

        Application
          |
        TCP/UDP
          |
        IP
          |
        Ethernet/Wi-Fi
          |
        Switch/AP
          |
        Router/default gateway
          |
        NAT
          |
        ISP
          |
        Internet routers
          |
        Destination network
          |
        Server

    The real path can contain many additional devices and technologies.
    """
    print("\n=== Packet Flow: LAN to Internet ===")

    steps = [
        "1. Application creates data.",
        "2. Transport layer assigns source/destination ports.",
        "3. IP layer assigns source/destination IP addresses.",
        "4. Host determines whether destination is local or remote.",
        "5. For a remote destination, host sends the frame to the default gateway.",
        "6. ARP or IPv6 Neighbor Discovery resolves the gateway's link-layer address.",
        "7. Ethernet/Wi-Fi carries the local frame.",
        "8. The router removes the local Layer-2 framing and examines the IP packet.",
        "9. The router selects a route.",
        "10. NAT may translate the private source address and port.",
        "11. The packet traverses ISP and Internet routers.",
        "12. The destination network delivers the packet to the server.",
        "13. The response follows a reverse path, subject to routing and state.",
    ]

    for step in steps:
        print(step)


# =============================================================================
# SECTION 44: EDGE CASES
# =============================================================================

def demonstrate_edge_cases() -> None:
    print("\n=== Networking Edge Cases ===")

    edge_cases = [
        (
            "IP address outside subnet",
            "A configured host address may be valid syntactically but invalid for the declared network."
        ),
        (
            "Duplicate IP",
            "Two devices using the same address can cause unpredictable connectivity."
        ),
        (
            "Duplicate MAC learning",
            "A switch may repeatedly relearn a MAC on different ports, indicating movement or a topology problem."
        ),
        (
            "TTL expiration",
            "Routing loops eventually cause packets to be discarded."
        ),
        (
            "MTU mismatch",
            "Packets may fail or experience fragmentation/path-MTU problems."
        ),
        (
            "DNS failure with working IP",
            "Applications using names may fail even though direct IP connectivity works."
        ),
        (
            "Port blocked by firewall",
            "A host can be reachable while a particular service remains inaccessible."
        ),
        (
            "Private IP on the Internet",
            "Private IPv4 addresses are not globally routed and generally require NAT or another translation/tunneling mechanism."
        ),
        (
            "IPv4 /31 and /32",
            "Traditional subnet-host calculations do not apply normally to these prefixes."
        ),
        (
            "IPv6 without broadcast",
            "IPv6 uses multicast and Neighbor Discovery instead of IPv4-style broadcast mechanisms."
        ),
    ]

    for case, explanation in edge_cases:
        print(f"{case:25}: {explanation}")


# =============================================================================
# SECTION 45: PERFORMANCE CONSIDERATIONS
# =============================================================================

def demonstrate_performance_considerations() -> None:
    print("\n=== Performance Considerations ===")

    considerations = [
        "Bandwidth determines how much data can be transmitted over time.",
        "Latency affects responsiveness even when bandwidth is high.",
        "Packet loss can cause retransmission and reduce effective throughput.",
        "Jitter is especially important for real-time audio/video.",
        "Small packets increase per-packet protocol overhead.",
        "Large packets improve efficiency but must respect MTU constraints.",
        "Congestion causes queueing delay and packet drops.",
        "CPU and memory limitations can constrain software network services.",
        "TLS encryption adds computational and protocol overhead but protects data.",
        "High-speed networks require appropriate NICs, switch ports and processing capacity.",
    ]

    for item in considerations:
        print(f"- {item}")


# =============================================================================
# SECTION 46: PRODUCTION NETWORK DESIGN
# =============================================================================

def demonstrate_production_design() -> None:
    print("\n=== Production Network Design Principles ===")

    principles = [
        ("Addressing", "Use a documented IP addressing plan and avoid accidental overlap."),
        ("Segmentation", "Separate users, servers, management and sensitive systems."),
        ("Redundancy", "Avoid single points of failure where availability requirements justify it."),
        ("Routing", "Use appropriate static or dynamic routing based on network scale."),
        ("Security", "Apply least privilege, firewalls, authentication and encryption."),
        ("Monitoring", "Collect interface, routing, service and security telemetry."),
        ("Documentation", "Document topology, addressing, dependencies and ownership."),
        ("Change control", "Test and record changes before production deployment."),
        ("Capacity", "Plan for expected traffic growth and failure scenarios."),
        ("Recovery", "Maintain configuration backups and tested recovery procedures."),
    ]

    for area, practice in principles:
        print(f"{area:15}: {practice}")


# =============================================================================
# SECTION 47: REAL-WORLD APPLICATIONS
# =============================================================================

def demonstrate_real_world_applications() -> None:
    print("\n=== Real-World Networking Applications ===")

    applications = {
        "Home networking": "Wi-Fi access points, switches, routers, DHCP, NAT and DNS.",
        "Enterprise LAN": "Managed switches, VLANs, routing, firewalls and centralized authentication.",
        "Data centers": "High-speed switching, redundant links, load balancing and segmented networks.",
        "Cloud networking": "Virtual networks, subnets, route tables, security groups and gateways.",
        "Web applications": "Clients, DNS, TCP/TLS or modern transports, load balancers and servers.",
        "Video conferencing": "Low latency, jitter management, congestion handling and adaptive media.",
        "IoT": "Large numbers of constrained devices communicating through gateways and wireless networks.",
        "Telecommunications": "Large-scale routing, transport networks, wireless access and service infrastructure.",
    }

    for area, description in applications.items():
        print(f"{area:22}: {description}")


# =============================================================================
# SECTION 48: COMMON MISTAKES
# =============================================================================

def demonstrate_common_mistakes() -> None:
    print("\n=== Common Networking Mistakes ===")

    mistakes = [
        (
            "Confusing MAC and IP addresses",
            "MAC identifies a Layer-2 interface on a local link; IP is a logical Layer-3 address."
        ),
        (
            "Assuming a switch routes between networks",
            "A normal Layer-2 switch forwards frames; Layer-3 switches can also perform routing."
        ),
        (
            "Assuming ping proves an application works",
            "ICMP reachability does not guarantee that a TCP/UDP service is available."
        ),
        (
            "Treating bandwidth as throughput",
            "A link's advertised capacity is not the same as application-level useful throughput."
        ),
        (
            "Ignoring DNS",
            "Name resolution is a separate dependency from basic IP connectivity."
        ),
        (
            "Using any private address anywhere",
            "Private addressing requires an appropriate routing/translation design."
        ),
        (
            "Opening unnecessary ports",
            "Every exposed service increases the attack surface."
        ),
        (
            "Changing multiple settings at once",
            "Troubleshooting becomes harder because the cause of improvement or failure is unclear."
        ),
        (
            "Ignoring MTU",
            "Path MTU problems can cause unusual application-specific connectivity failures."
        ),
        (
            "Skipping documentation",
            "Undocumented networks are difficult to troubleshoot and safely modify."
        ),
    ]

    for mistake, correction in mistakes:
        print(f"{mistake:30}: {correction}")


# =============================================================================
# SECTION 49: TESTS
# =============================================================================

def run_self_tests() -> None:
    """
    Basic assertions verify important educational implementations.
    """
    print("\n=== Self Tests ===")

    assert normalize_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"

    assert mac_is_broadcast("FF:FF:FF:FF:FF:FF")
    assert mac_is_multicast("01:00:5e:00:00:01")

    assert hosts_in_same_subnet(
        "192.168.1.10",
        "192.168.1.20",
        24,
    )

    assert not hosts_in_same_subnet(
        "192.168.1.10",
        "192.168.2.20",
        24,
    )

    route_table = RoutingTable()
    route_table.add_route(
        "0.0.0.0/0",
        "192.168.1.1",
        "default",
    )
    route_table.add_route(
        "10.0.0.0/8",
        "192.168.1.2",
        "specific",
    )

    route = route_table.lookup("10.1.2.3")

    assert route is not None
    assert str(route.network) == "10.0.0.0/8"

    assert calculate_fragment_count(4000, 1500) == 3

    total, usable = subnet_capacity(24)
    assert total == 256
    assert usable == 254

    firewall = SimpleFirewall()
    firewall.add_rule("TCP", 443, "ALLOW")

    assert firewall.evaluate("TCP", 443) == "ALLOW"
    assert firewall.evaluate("TCP", 80) == "DENY"

    errors = validate_network_configuration(
        "192.168.1.10",
        "192.168.1.0/24",
        "192.168.1.1",
    )

    assert errors == []

    print("All self tests passed.")


# =============================================================================
# SECTION 50: STUDY DEMONSTRATION
# =============================================================================

def print_study_questions() -> None:
    """
    Print conceptual questions that can be answered by examining the script.
    """
    print("\n=== Study Questions ===")

    questions = [
        "Why does a device need both a MAC address and an IP address?",
        "When does a host use the default gateway?",
        "How does a switch learn where a MAC address is located?",
        "Why does a switch flood an unknown unicast frame?",
        "Why does a router decrement TTL?",
        "What is the difference between a frame and a packet?",
        "Why is TCP considered reliable while UDP is not?",
        "What happens when a destination is outside the local subnet?",
        "Why can DNS fail while IP connectivity remains functional?",
        "How does NAT allow private IPv4 hosts to share a public address?",
        "Why do VLANs create separate Layer-2 broadcast domains?",
        "How does longest-prefix matching select a route?",
        "Why can high bandwidth still produce poor application performance?",
        "What problems can packet loss and jitter cause?",
        "Why is network segmentation important for security?",
    ]

    for number, question in enumerate(questions, start=1):
        print(f"{number:2}. {question}")


# =============================================================================
# MAIN PROGRAM
# =============================================================================

def main() -> None:
    """
    Run the complete networking study demonstration.

    The demonstrations are independent so the script can also be used as a
    reference file. Local socket examples are deliberately bound to loopback
    only.
    """
    print("=" * 80)
    print("COMPUTER NETWORKS: COMPLETE PYTHON STUDY SCRIPT")
    print("LAN | WAN | ROUTERS | SWITCHES | PACKETS")
    print("=" * 80)

    explain_basic_terminology()
    demonstrate_network_types()
    demonstrate_topologies()
    demonstrate_mac_addresses()

    frame = EthernetFrame(
        source_mac="00:11:22:33:44:55",
        destination_mac="00:11:22:33:44:66",
        payload=b"Example Ethernet payload",
    )
    frame.describe()

    demonstrate_ip_addresses()
    demonstrate_subnetting()
    demonstrate_subnet_membership()

    demonstrate_routing()
    demonstrate_switch()

    demonstrate_encapsulation()
    demonstrate_ports()
    demonstrate_socket_information()
    compare_tcp_udp()

    tcp_connection = SimulatedTCPConnection()
    tcp_connection.three_way_handshake()
    tcp_connection.four_step_close()

    demonstrate_arp()
    demonstrate_dns()
    explain_dhcp()
    demonstrate_nat()

    simulate_packet_hops(
        source="192.168.1.10",
        destination="8.8.8.8",
        routers=5,
        initial_ttl=8,
    )

    explain_network_domains()
    demonstrate_network_performance()
    demonstrate_bdp()
    demonstrate_packet_loss()
    demonstrate_mtu()
    demonstrate_prefix_capacity()

    demonstrate_router()
    demonstrate_local_socket_server()
    demonstrate_udp_loopback()

    demonstrate_ipv4_header_structure()
    demonstrate_ipv6()
    demonstrate_osi_model()
    demonstrate_tcp_ip_model()
    demonstrate_icmp_concepts()
    demonstrate_address_classification()

    demonstrate_dijkstra()
    demonstrate_vlans()
    demonstrate_default_gateway()

    demonstrate_network_security_principles()
    demonstrate_firewall()
    demonstrate_configuration_validation()
    demonstrate_protocol_overhead()
    demonstrate_queueing()
    demonstrate_route_redundancy()

    troubleshooting_checklist()
    demonstrate_troubleshooting()

    simulate_home_network_packet_flow()
    demonstrate_edge_cases()
    demonstrate_performance_considerations()
    demonstrate_production_design()
    demonstrate_real_world_applications()
    demonstrate_common_mistakes()

    run_self_tests()
    print_study_questions()

    print("\n" + "=" * 80)
    print("END OF COMPUTER NETWORKING STUDY SCRIPT")
    print("=" * 80)


if __name__ == "__main__":
    main()
