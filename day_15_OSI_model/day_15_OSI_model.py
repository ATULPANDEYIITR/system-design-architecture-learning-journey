"""
OSI Model: Seven Layers and Their Responsibilities
===================================================

A self-contained study and demonstration program for learning the OSI
(Open Systems Interconnection) model from beginner to advanced level.

The program covers:
    Layer 7 - Application
    Layer 6 - Presentation
    Layer 5 - Session
    Layer 4 - Transport
    Layer 3 - Network
    Layer 2 - Data Link
    Layer 1 - Physical

It also demonstrates:
    - Encapsulation and decapsulation
    - PDUs at different layers
    - MAC addresses and IP addresses
    - TCP and UDP concepts
    - Ports
    - Routing
    - Switching
    - ARP
    - DNS
    - HTTP
    - TLS placement
    - Ethernet framing
    - Physical transmission
    - MTU and fragmentation concepts
    - Error detection
    - Network troubleshooting
    - Security considerations
    - Performance and design trade-offs

The examples use only Python's standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import hashlib
import ipaddress
import struct
import time
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. OSI FUNDAMENTALS
# ---------------------------------------------------------------------------

class OSILayer(IntEnum):
    """Numerical ordering of the seven OSI layers."""

    PHYSICAL = 1
    DATA_LINK = 2
    NETWORK = 3
    TRANSPORT = 4
    SESSION = 5
    PRESENTATION = 6
    APPLICATION = 7


LAYER_NAMES = {
    OSILayer.PHYSICAL: "Physical",
    OSILayer.DATA_LINK: "Data Link",
    OSILayer.NETWORK: "Network",
    OSILayer.TRANSPORT: "Transport",
    OSILayer.SESSION: "Session",
    OSILayer.PRESENTATION: "Presentation",
    OSILayer.APPLICATION: "Application",
}

LAYER_RESPONSIBILITIES = {
    OSILayer.PHYSICAL: "Transmits raw bits over a physical medium.",
    OSILayer.DATA_LINK: "Provides frames, MAC addressing and local delivery.",
    OSILayer.NETWORK: "Provides logical addressing and routing between networks.",
    OSILayer.TRANSPORT: "Provides process-to-process delivery and transport services.",
    OSILayer.SESSION: "Manages logical communication sessions.",
    OSILayer.PRESENTATION: "Handles representation, encoding, compression and encryption.",
    OSILayer.APPLICATION: "Provides network services directly used by applications.",
}


def print_osi_layers() -> None:
    """Display all seven layers from Layer 7 down to Layer 1."""

    print("\n" + "=" * 72)
    print("OSI MODEL: SEVEN LAYERS")
    print("=" * 72)

    for layer in reversed(list(OSILayer)):
        print(
            f"Layer {layer.value}: {LAYER_NAMES[layer]:<14} | "
            f"{LAYER_RESPONSIBILITIES[layer]}"
        )


# ---------------------------------------------------------------------------
# 2. TERMINOLOGY
# ---------------------------------------------------------------------------

PDU_NAMES = {
    OSILayer.PHYSICAL: "Bits",
    OSILayer.DATA_LINK: "Frame",
    OSILayer.NETWORK: "Packet",
    OSILayer.TRANSPORT: "Segment / Datagram",
    OSILayer.SESSION: "Data",
    OSILayer.PRESENTATION: "Data",
    OSILayer.APPLICATION: "Data",
}


def explain_pdu_names() -> None:
    """Explain the common protocol data unit terminology."""

    print("\n" + "=" * 72)
    print("PROTOCOL DATA UNITS")
    print("=" * 72)

    for layer in reversed(list(OSILayer)):
        print(
            f"Layer {layer.value} {LAYER_NAMES[layer]:<14}: "
            f"{PDU_NAMES[layer]}"
        )

    print(
        "\nImportant distinction:\n"
        "The exact terminology can vary by protocol. 'Packet' is commonly "
        "associated with Layer 3, 'frame' with Layer 2, and 'segment' with "
        "TCP at Layer 4. UDP commonly uses 'datagram'."
    )


# ---------------------------------------------------------------------------
# 3. ADDRESS TYPES
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MACAddress:
    """Simple representation of a 48-bit Ethernet MAC address."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.lower().replace("-", ":")
        parts = normalized.split(":")

        if len(parts) != 6 or any(len(part) != 2 for part in parts):
            raise ValueError(f"Invalid MAC address: {self.value}")

        try:
            [int(part, 16) for part in parts]
        except ValueError as exc:
            raise ValueError(f"Invalid MAC address: {self.value}") from exc

        object.__setattr__(self, "value", ":".join(parts))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class IPAddress:
    """Representation of an IPv4 address using Python's standard library."""

    value: str

    def __post_init__(self) -> None:
        try:
            ipaddress.IPv4Address(self.value)
        except ipaddress.AddressValueError as exc:
            raise ValueError(f"Invalid IPv4 address: {self.value}") from exc

    def __str__(self) -> str:
        return self.value


def demonstrate_addressing() -> None:
    print("\n" + "=" * 72)
    print("ADDRESSING")
    print("=" * 72)

    mac = MACAddress("AA:BB:CC:DD:EE:01")
    source_ip = IPAddress("192.168.1.10")
    destination_ip = IPAddress("8.8.8.8")

    print(f"MAC address : {mac} -> Layer 2 local-network identity")
    print(f"Source IP   : {source_ip} -> Layer 3 logical address")
    print(f"Target IP   : {destination_ip} -> Layer 3 remote destination")

    print(
        "\nMAC addresses normally matter for delivery on the local Layer 2 "
        "network. IP addresses enable communication across multiple networks."
    )


# ---------------------------------------------------------------------------
# 4. LAYER 1: PHYSICAL
# ---------------------------------------------------------------------------

@dataclass
class PhysicalSignal:
    """A simplified representation of transmitted physical bits."""

    bits: str
    medium: str

    def transmit(self) -> None:
        if any(bit not in "01" for bit in self.bits):
            raise ValueError("Physical representation must contain only 0 and 1.")

        print(f"Medium: {self.medium}")
        print(f"Transmitted bits: {self.bits}")


def physical_layer_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 1 - PHYSICAL")
    print("=" * 72)

    signal = PhysicalSignal("0100100001101001", "Ethernet copper cable")
    signal.transmit()

    print(
        "\nLayer 1 concerns signals, voltages, light pulses, radio waves, "
        "connectors, frequencies, bit timing and physical media."
    )


# ---------------------------------------------------------------------------
# 5. LAYER 2: DATA LINK
# ---------------------------------------------------------------------------

@dataclass
class EthernetFrame:
    """Simplified Ethernet frame."""

    source_mac: MACAddress
    destination_mac: MACAddress
    payload: bytes
    ether_type: int = 0x0800
    fcs: Optional[int] = None

    def calculate_fcs(self) -> int:
        """
        A teaching-oriented integrity value.

        Real Ethernet uses CRC-32 rather than SHA-256. SHA-256 is used here
        only to create a deterministic integrity demonstration without
        pretending it is the actual Ethernet FCS algorithm.
        """
        header = (
            self.destination_mac.value.encode()
            + self.source_mac.value.encode()
            + struct.pack("!H", self.ether_type)
        )
        digest = hashlib.sha256(header + self.payload).digest()
        return int.from_bytes(digest[:4], "big")

    def finalize(self) -> None:
        self.fcs = self.calculate_fcs()

    def verify(self) -> bool:
        return self.fcs == self.calculate_fcs()


def data_link_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 2 - DATA LINK")
    print("=" * 72)

    frame = EthernetFrame(
        source_mac=MACAddress("AA:BB:CC:DD:EE:01"),
        destination_mac=MACAddress("AA:BB:CC:DD:EE:02"),
        payload=b"Hello Layer 2",
    )

    frame.finalize()

    print(f"Source MAC      : {frame.source_mac}")
    print(f"Destination MAC : {frame.destination_mac}")
    print(f"Payload         : {frame.payload!r}")
    print(f"Integrity value : {frame.fcs}")
    print(f"Frame valid     : {frame.verify()}")

    # Demonstrate detection of corruption.
    frame.payload = b"Corrupted payload"
    print(f"After corruption: {frame.verify()}")


# ---------------------------------------------------------------------------
# 6. ETHERNET SWITCHING
# ---------------------------------------------------------------------------

@dataclass
class Switch:
    """
    Simplified Ethernet switch.

    A switch learns which MAC address is reachable through which port.
    This approximates the forwarding database behavior of a real switch.
    """

    mac_table: Dict[MACAddress, str] = field(default_factory=dict)

    def learn(self, source_mac: MACAddress, ingress_port: str) -> None:
        self.mac_table[source_mac] = ingress_port

    def forwarding_port(self, destination_mac: MACAddress) -> Optional[str]:
        return self.mac_table.get(destination_mac)

    def show_table(self) -> None:
        print("\nSwitch MAC address table:")
        for mac, port in self.mac_table.items():
            print(f"  {mac} -> {port}")


def switch_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 2 SWITCHING")
    print("=" * 72)

    switch = Switch()

    host_a = MACAddress("AA:AA:AA:AA:AA:01")
    host_b = MACAddress("AA:AA:AA:AA:AA:02")
    host_c = MACAddress("AA:AA:AA:AA:AA:03")

    switch.learn(host_a, "port-1")
    switch.learn(host_b, "port-2")

    switch.show_table()

    print(f"\nKnown destination {host_b}: {switch.forwarding_port(host_b)}")
    print(f"Unknown destination {host_c}: {switch.forwarding_port(host_c)}")

    print(
        "\nIf a switch does not know a destination MAC, it can flood the frame "
        "within the relevant broadcast domain, subject to VLAN and filtering rules."
    )


# ---------------------------------------------------------------------------
# 7. LAYER 3: NETWORK
# ---------------------------------------------------------------------------

@dataclass
class IPv4Packet:
    """Simplified IPv4 packet."""

    source_ip: IPAddress
    destination_ip: IPAddress
    payload: bytes
    ttl: int = 64
    protocol: int = 6  # 6 represents TCP.

    def route(self, destination_network: ipaddress.IPv4Network) -> bool:
        """Return whether the destination IP belongs to a network."""
        return ipaddress.IPv4Address(
            self.destination_ip.value
        ) in destination_network

    def decrement_ttl(self) -> None:
        self.ttl -= 1
        if self.ttl <= 0:
            raise RuntimeError("TTL expired. Packet must be discarded.")


@dataclass
class Router:
    """Very small routing-table demonstration."""

    routes: List[Tuple[ipaddress.IPv4Network, str]] = field(default_factory=list)

    def add_route(self, network: str, next_hop: str) -> None:
        self.routes.append((ipaddress.IPv4Network(network), next_hop))

    def lookup(self, destination: str) -> Optional[str]:
        destination_ip = ipaddress.IPv4Address(destination)

        matching_routes = [
            (network, next_hop)
            for network, next_hop in self.routes
            if destination_ip in network
        ]

        if not matching_routes:
            return None

        # Longest-prefix match: the most specific route wins.
        matching_routes.sort(key=lambda item: item[0].prefixlen, reverse=True)
        return matching_routes[0][1]


def network_layer_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 3 - NETWORK")
    print("=" * 72)

    router = Router()
    router.add_route("10.0.0.0/8", "router-A")
    router.add_route("10.10.0.0/16", "router-B")
    router.add_route("0.0.0.0/0", "default-gateway")

    destinations = ["10.10.20.5", "10.20.1.8", "8.8.8.8"]

    for destination in destinations:
        print(f"{destination:<15} -> {router.lookup(destination)}")

    packet = IPv4Packet(
        source_ip=IPAddress("192.168.1.10"),
        destination_ip=IPAddress("8.8.8.8"),
        payload=b"network data",
    )

    print(f"\nInitial TTL: {packet.ttl}")
    packet.decrement_ttl()
    print(f"TTL after one router hop: {packet.ttl}")


# ---------------------------------------------------------------------------
# 8. SUBNETTING
# ---------------------------------------------------------------------------

def subnetting_demo() -> None:
    print("\n" + "=" * 72)
    print("IP SUBNETTING")
    print("=" * 72)

    network = ipaddress.ip_network("192.168.10.0/24")

    print(f"Network: {network}")
    print(f"Network address: {network.network_address}")
    print(f"Broadcast address: {network.broadcast_address}")
    print(f"Prefix length: {network.prefixlen}")
    print(f"Number of addresses: {network.num_addresses}")

    subnets = list(network.subnets(new_prefix=26))

    print("\n/24 divided into /26 networks:")
    for subnet in subnets:
        print(f"  {subnet}")

    print(
        "\nSubnetting allows an organization to divide an address space into "
        "smaller logical networks, improving address management and segmentation."
    )


# ---------------------------------------------------------------------------
# 9. ARP
# ---------------------------------------------------------------------------

@dataclass
class ARPTable:
    """Simplified IPv4-to-MAC mapping."""

    entries: Dict[str, MACAddress] = field(default_factory=dict)

    def resolve(self, ip: str) -> Optional[MACAddress]:
        return self.entries.get(ip)

    def learn(self, ip: str, mac: MACAddress) -> None:
        self.entries[ip] = mac


def arp_demo() -> None:
    print("\n" + "=" * 72)
    print("ARP: ADDRESS RESOLUTION")
    print("=" * 72)

    arp = ARPTable()

    target_ip = "192.168.1.20"
    target_mac = MACAddress("AA:BB:CC:DD:EE:20")

    print(f"Before learning: {arp.resolve(target_ip)}")
    arp.learn(target_ip, target_mac)
    print(f"After learning : {arp.resolve(target_ip)}")

    print(
        "\nARP is used on IPv4 local networks to discover the Layer 2 MAC "
        "address associated with a Layer 3 IPv4 address."
    )


# ---------------------------------------------------------------------------
# 10. LAYER 4: TRANSPORT
# ---------------------------------------------------------------------------

@dataclass
class TCPSegment:
    """Simplified TCP segment."""

    source_port: int
    destination_port: int
    sequence_number: int
    acknowledgement_number: int
    flags: str
    payload: bytes = b""

    def validate_ports(self) -> None:
        if not (0 <= self.source_port <= 65535):
            raise ValueError("Invalid source port.")
        if not (0 <= self.destination_port <= 65535):
            raise ValueError("Invalid destination port.")


@dataclass
class UDPDatagram:
    """Simplified UDP datagram."""

    source_port: int
    destination_port: int
    payload: bytes = b""

    def validate(self) -> None:
        for port in (self.source_port, self.destination_port):
            if not (0 <= port <= 65535):
                raise ValueError("Invalid UDP port.")


def tcp_handshake_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 4 - TCP THREE-WAY HANDSHAKE")
    print("=" * 72)

    client_isn = 1000
    server_isn = 5000

    syn = TCPSegment(49152, 443, client_isn, 0, "SYN")
    syn_ack = TCPSegment(
        443,
        49152,
        server_isn,
        client_isn + 1,
        "SYN-ACK",
    )
    ack = TCPSegment(
        49152,
        443,
        client_isn + 1,
        server_isn + 1,
        "ACK",
    )

    for segment in (syn, syn_ack, ack):
        segment.validate_ports()
        print(
            f"{segment.flags:<7} "
            f"seq={segment.sequence_number:<5} "
            f"ack={segment.acknowledgement_number}"
        )

    print(
        "\nTCP provides connection-oriented communication, sequencing, "
        "acknowledgements, retransmission and flow/congestion control."
    )


def tcp_vs_udp_demo() -> None:
    print("\n" + "=" * 72)
    print("TCP VS UDP")
    print("=" * 72)

    comparison = [
        ("Connection", "Connection-oriented", "Connectionless"),
        ("Reliability", "Reliable byte stream", "No delivery guarantee"),
        ("Ordering", "Maintains ordered byte stream", "No ordering guarantee"),
        ("Overhead", "Higher", "Lower"),
        ("Typical uses", "Web, SSH, file transfer", "DNS, streaming, real-time traffic"),
    ]

    for characteristic, tcp, udp in comparison:
        print(f"{characteristic:<15} | TCP: {tcp:<28} | UDP: {udp}")


# ---------------------------------------------------------------------------
# 11. PORTS AND SOCKET IDENTIFICATION
# ---------------------------------------------------------------------------

def port_demo() -> None:
    print("\n" + "=" * 72)
    print("PORTS")
    print("=" * 72)

    connections = [
        ("192.168.1.10", 51520, "142.250.72.14", 443, "HTTPS"),
        ("192.168.1.10", 51521, "8.8.8.8", 53, "DNS"),
    ]

    for source_ip, source_port, destination_ip, destination_port, service in connections:
        print(
            f"{source_ip}:{source_port} -> "
            f"{destination_ip}:{destination_port} ({service})"
        )

    print(
        "\nAn IP address identifies a host/interface at Layer 3. A port identifies "
        "a transport-layer endpoint associated with a process or service."
    )


# ---------------------------------------------------------------------------
# 12. LAYER 5: SESSION
# ---------------------------------------------------------------------------

@dataclass
class Session:
    """A simplified session lifecycle."""

    session_id: str
    state: str = "NEW"

    def start(self) -> None:
        if self.state != "NEW":
            raise RuntimeError("Session cannot be started from its current state.")
        self.state = "ESTABLISHED"

    def pause(self) -> None:
        if self.state != "ESTABLISHED":
            raise RuntimeError("Only an established session can be paused.")
        self.state = "PAUSED"

    def resume(self) -> None:
        if self.state != "PAUSED":
            raise RuntimeError("Only a paused session can be resumed.")
        self.state = "ESTABLISHED"

    def close(self) -> None:
        if self.state == "CLOSED":
            return
        self.state = "CLOSED"


def session_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 5 - SESSION")
    print("=" * 72)

    session = Session("session-001")
    print(session.state)

    session.start()
    print(session.state)

    session.pause()
    print(session.state)

    session.resume()
    print(session.state)

    session.close()
    print(session.state)

    print(
        "\nThe OSI Session layer conceptually manages dialog/session state. "
        "Modern protocols often combine session responsibilities with other layers."
    )


# ---------------------------------------------------------------------------
# 13. LAYER 6: PRESENTATION
# ---------------------------------------------------------------------------

def presentation_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 6 - PRESENTATION")
    print("=" * 72)

    text = "OSI model: café"

    encoded = text.encode("utf-8")
    decoded = encoded.decode("utf-8")

    print(f"Original : {text}")
    print(f"UTF-8    : {encoded}")
    print(f"Decoded  : {decoded}")

    # Base64 is an encoding mechanism, not encryption.
    import base64

    encoded_base64 = base64.b64encode(encoded)
    decoded_base64 = base64.b64decode(encoded_base64).decode("utf-8")

    print(f"Base64   : {encoded_base64.decode()}")
    print(f"Decoded  : {decoded_base64}")

    print(
        "\nPresentation responsibilities include data representation, encoding, "
        "serialization, compression and encryption-related transformations. "
        "The OSI model is conceptual, so real protocols do not always map "
        "cleanly to exactly one presentation-layer protocol."
    )


# ---------------------------------------------------------------------------
# 14. LAYER 7: APPLICATION
# ---------------------------------------------------------------------------

@dataclass
class HTTPRequest:
    """Simplified HTTP request."""

    method: str
    path: str
    headers: Dict[str, str]
    body: bytes = b""

    def serialize(self) -> bytes:
        request_line = f"{self.method} {self.path} HTTP/1.1\r\n"
        header_text = "".join(f"{key}: {value}\r\n" for key, value in self.headers.items())
        return (request_line + header_text + "\r\n").encode() + self.body


def application_layer_demo() -> None:
    print("\n" + "=" * 72)
    print("LAYER 7 - APPLICATION")
    print("=" * 72)

    request = HTTPRequest(
        method="GET",
        path="/index.html",
        headers={
            "Host": "example.com",
            "Accept": "text/html",
        },
    )

    print(request.serialize().decode())

    print(
        "HTTP provides application-level semantics for web communication. "
        "Other Layer 7 protocols include DNS, SMTP, FTP and SSH."
    )


# ---------------------------------------------------------------------------
# 15. ENCAPSULATION
# ---------------------------------------------------------------------------

@dataclass
class EncapsulatedData:
    """Stores the simulated protocol data unit at each layer."""

    application_data: bytes
    presentation_data: bytes = b""
    session_data: bytes = b""
    transport_data: bytes = b""
    network_data: bytes = b""
    data_link_data: bytes = b""
    physical_bits: str = ""


def simulate_encapsulation() -> EncapsulatedData:
    print("\n" + "=" * 72)
    print("ENCAPSULATION")
    print("=" * 72)

    data = EncapsulatedData(application_data=b"Hello, network!")

    print(f"Layer 7 Application data: {data.application_data!r}")

    # Presentation representation.
    data.presentation_data = b"UTF8|" + data.application_data
    print(f"Layer 6 Presentation   : {data.presentation_data!r}")

    # Session identifier.
    data.session_data = b"SESSION=42|" + data.presentation_data
    print(f"Layer 5 Session         : {data.session_data!r}")

    # Simplified TCP header.
    tcp_header = struct.pack("!HH", 51520, 443)
    data.transport_data = tcp_header + data.session_data
    print(f"Layer 4 Transport bytes: {data.transport_data!r}")

    # Simplified IP header.
    ip_header = b"IP:SRC=192.168.1.10,DST=93.184.216.34|"
    data.network_data = ip_header + data.transport_data
    print(f"Layer 3 Network bytes  : {data.network_data!r}")

    # Simplified Ethernet header.
    ethernet_header = b"ETH:SRC=AA:AA:AA:AA:AA:01,DST=BB:BB:BB:BB:BB:02|"
    data.data_link_data = ethernet_header + data.network_data
    print(f"Layer 2 Frame bytes    : {data.data_link_data!r}")

    # Convert every byte into eight physical bits.
    data.physical_bits = "".join(f"{byte:08b}" for byte in data.data_link_data)
    print(f"Layer 1 Bits           : {data.physical_bits[:96]}...")

    return data


def demonstrate_decapsulation(data: EncapsulatedData) -> None:
    print("\n" + "=" * 72)
    print("DECAPSULATION")
    print("=" * 72)

    print("Receiver processes the data in the reverse conceptual direction:")
    print("Bits -> Frame -> Packet -> Segment/Datagram -> Session -> Presentation -> Application")
    print(f"Final application payload: {data.application_data!r}")


# ---------------------------------------------------------------------------
# 16. MTU AND PACKET SIZE
# ---------------------------------------------------------------------------

def mtu_demo() -> None:
    print("\n" + "=" * 72)
    print("MTU AND PACKET SIZE")
    print("=" * 72)

    mtu = 1500
    payload_size = 4200

    full_packets = payload_size // mtu
    remainder = payload_size % mtu

    number_of_chunks = full_packets + (1 if remainder else 0)

    print(f"MTU: {mtu} bytes")
    print(f"Payload: {payload_size} bytes")
    print(f"Required chunks at this simplified level: {number_of_chunks}")

    print(
        "\nReal IP fragmentation behavior depends on IP version, headers, "
        "DF/MF flags, path MTU discovery and the protocol implementation. "
        "IPv6 routers do not fragment packets in transit."
    )


# ---------------------------------------------------------------------------
# 17. DNS CONCEPT
# ---------------------------------------------------------------------------

class DNSCache:
    """Small DNS cache demonstration."""

    def __init__(self) -> None:
        self.records: Dict[str, Tuple[str, float]] = {}

    def put(self, hostname: str, address: str, ttl_seconds: float) -> None:
        self.records[hostname] = (address, time.time() + ttl_seconds)

    def get(self, hostname: str) -> Optional[str]:
        record = self.records.get(hostname)

        if record is None:
            return None

        address, expiration = record

        if time.time() >= expiration:
            del self.records[hostname]
            return None

        return address


def dns_demo() -> None:
    print("\n" + "=" * 72)
    print("DNS")
    print("=" * 72)

    cache = DNSCache()

    cache.put("example.com", "93.184.216.34", ttl_seconds=60)

    print(f"example.com -> {cache.get('example.com')}")
    print(
        "\nDNS translates domain names into resource records such as IP addresses. "
        "Caching reduces repeated lookup cost but introduces TTL and staleness considerations."
    )


# ---------------------------------------------------------------------------
# 18. CHECKSUM AND ERROR DETECTION CONCEPT
# ---------------------------------------------------------------------------

def internet_checksum(data: bytes) -> int:
    """
    Teaching implementation of a 16-bit one's-complement checksum.

    It illustrates the principle used by Internet checksum mechanisms.
    """
    if len(data) % 2:
        data += b"\x00"

    total = 0

    for index in range(0, len(data), 2):
        word = (data[index] << 8) + data[index + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


def checksum_demo() -> None:
    print("\n" + "=" * 72)
    print("ERROR DETECTION")
    print("=" * 72)

    message = b"network integrity"
    checksum = internet_checksum(message)

    print(f"Data     : {message!r}")
    print(f"Checksum : 0x{checksum:04X}")

    corrupted = b"network integritY"
    corrupted_checksum = internet_checksum(corrupted)

    print(f"Corrupt  : {corrupted!r}")
    print(f"Checksum : 0x{corrupted_checksum:04X}")
    print(f"Detected : {checksum != corrupted_checksum}")


# ---------------------------------------------------------------------------
# 19. TROUBLESHOOTING BY OSI LAYER
# ---------------------------------------------------------------------------

TROUBLESHOOTING_EXAMPLES = {
    1: [
        "Cable disconnected",
        "Bad transceiver",
        "Wireless radio disabled",
        "Signal interference",
        "Incorrect speed/duplex configuration",
    ],
    2: [
        "Wrong VLAN",
        "MAC learning issue",
        "Switch port disabled",
        "Broadcast-domain problem",
        "ARP-related local-network issue",
    ],
    3: [
        "Wrong IP address",
        "Incorrect subnet mask",
        "Missing route",
        "Default gateway failure",
        "Routing loop",
    ],
    4: [
        "Blocked TCP/UDP port",
        "Service not listening",
        "TCP connection failure",
        "UDP loss",
        "Firewall policy",
    ],
    5: [
        "Expired session",
        "Authentication/session state failure",
        "Session timeout",
    ],
    6: [
        "Encoding mismatch",
        "Certificate/TLS problem",
        "Compression/serialization mismatch",
    ],
    7: [
        "DNS application error",
        "HTTP 404/500",
        "Invalid API request",
        "Application authentication failure",
    ],
}


def troubleshooting_demo() -> None:
    print("\n" + "=" * 72)
    print("OSI-BASED TROUBLESHOOTING")
    print("=" * 72)

    for layer in range(1, 8):
        print(f"\nLayer {layer} - {LAYER_NAMES[OSILayer(layer)]}")
        for problem in TROUBLESHOOTING_EXAMPLES[layer]:
            print(f"  - {problem}")

    print(
        "\nA practical troubleshooting workflow often starts with physical "
        "connectivity and moves upward, but engineers may begin at any layer "
        "when symptoms strongly indicate a particular fault domain."
    )


# ---------------------------------------------------------------------------
# 20. SECURITY BY LAYER
# ---------------------------------------------------------------------------

def security_by_layer_demo() -> None:
    print("\n" + "=" * 72)
    print("SECURITY CONSIDERATIONS BY OSI LAYER")
    print("=" * 72)

    security_controls = {
        1: "Physical access controls, shielding, secure cabling, radio security.",
        2: "VLAN segmentation, port security, MAC filtering, 802.1X.",
        3: "Routing controls, ACLs, IPsec, anti-spoofing and network segmentation.",
        4: "Stateful firewalls, port restrictions, rate limiting, SYN protection.",
        5: "Session expiration, secure session identifiers, reauthentication.",
        6: "TLS-related protection, safe encoding, certificate validation.",
        7: "Authentication, authorization, input validation, secure API design.",
    }

    for layer, control in security_controls.items():
        print(f"Layer {layer} {LAYER_NAMES[OSILayer(layer)]:<14}: {control}")

    print(
        "\nSecurity mechanisms often span multiple layers. For example, a modern "
        "web application may use Ethernet/VLAN controls, IP routing and ACLs, "
        "TCP controls, TLS, HTTP authentication and application authorization."
    )


# ---------------------------------------------------------------------------
# 21. PERFORMANCE CONSIDERATIONS
# ---------------------------------------------------------------------------

def performance_demo() -> None:
    print("\n" + "=" * 72)
    print("PERFORMANCE CONSIDERATIONS")
    print("=" * 72)

    factors = [
        ("Layer 1", "Signal quality, bandwidth, propagation and physical medium"),
        ("Layer 2", "Frame overhead, switching capacity, broadcast domains"),
        ("Layer 3", "Routing hops, packet processing, MTU and congestion"),
        ("Layer 4", "Retransmissions, congestion control, connection setup"),
        ("Layer 5", "Session establishment and state management"),
        ("Layer 6", "Encryption, compression and serialization cost"),
        ("Layer 7", "Application processing, database calls and payload size"),
    ]

    for layer, factor in factors:
        print(f"{layer:<10}: {factor}")

    print(
        "\nLatency is cumulative. A slow application can exist even when the "
        "physical link is fast, because application processing, transport "
        "behavior, routing, encryption and remote service latency all contribute."
    )


# ---------------------------------------------------------------------------
# 22. REAL-WORLD PROTOCOL MAPPING
# ---------------------------------------------------------------------------

def protocol_mapping_demo() -> None:
    print("\n" + "=" * 72)
    print("COMMON PROTOCOL AND TECHNOLOGY MAPPING")
    print("=" * 72)

    mapping = {
        7: ["HTTP", "DNS", "SMTP", "FTP", "SSH"],
        6: ["TLS-related representation/encryption functions", "JSON", "UTF-8"],
        5: ["Session concepts implemented by application protocols/frameworks"],
        4: ["TCP", "UDP", "SCTP"],
        3: ["IPv4", "IPv6", "ICMP", "IPsec"],
        2: ["Ethernet", "802.11 Wi-Fi", "ARP-related local resolution"],
        1: ["Copper", "Fiber", "Radio", "Connectors", "Physical signaling"],
    }

    for layer in range(7, 0, -1):
        print(f"Layer {layer} {LAYER_NAMES[OSILayer(layer)]:<14}:")
        print("  " + ", ".join(mapping[layer]))

    print(
        "\nThe mapping is approximate. The Internet protocol suite does not "
        "implement the OSI model as seven rigid independent layers."
    )


# ---------------------------------------------------------------------------
# 23. OSI VS TCP/IP
# ---------------------------------------------------------------------------

def osi_vs_tcp_ip_demo() -> None:
    print("\n" + "=" * 72)
    print("OSI MODEL VS TCP/IP MODEL")
    print("=" * 72)

    rows = [
        ("OSI 7 Application", "TCP/IP Application"),
        ("OSI 6 Presentation", "TCP/IP Application"),
        ("OSI 5 Session", "TCP/IP Application"),
        ("OSI 4 Transport", "TCP/IP Transport"),
        ("OSI 3 Network", "TCP/IP Internet"),
        ("OSI 2 Data Link", "TCP/IP Link / Network Access"),
        ("OSI 1 Physical", "TCP/IP Link / Network Access"),
    ]

    for osi, tcp_ip in rows:
        print(f"{osi:<25} -> {tcp_ip}")

    print(
        "\nOSI is particularly useful as a conceptual and troubleshooting framework. "
        "The TCP/IP model is more closely aligned with the architecture of the "
        "Internet protocol suite."
    )


# ---------------------------------------------------------------------------
# 24. ADVANCED CONCEPT: PACKET JOURNEY
# ---------------------------------------------------------------------------

@dataclass
class Host:
    name: str
    ip: IPAddress
    mac: MACAddress


def packet_journey_demo() -> None:
    print("\n" + "=" * 72)
    print("END-TO-END PACKET JOURNEY")
    print("=" * 72)

    client = Host(
        "Client",
        IPAddress("192.168.1.10"),
        MACAddress("AA:AA:AA:AA:AA:10"),
    )

    gateway = Host(
        "Gateway",
        IPAddress("192.168.1.1"),
        MACAddress("AA:AA:AA:AA:AA:01"),
    )

    server = Host(
        "Server",
        IPAddress("203.0.113.10"),
        MACAddress("BB:BB:BB:BB:BB:10"),
    )

    print(f"Application: {client.name} creates an HTTP request.")
    print("Presentation: request data is represented/encoded.")
    print("Session: application/session state is maintained.")
    print("Transport: TCP assigns source/destination ports and reliability state.")
    print(f"Network: {client.ip} -> {server.ip}")
    print(f"Data Link: {client.mac} -> gateway MAC {gateway.mac}")
    print("Physical: frame becomes electrical/optical/radio signals.")

    print("\nAt the router:")
    print(f"  Destination IP remains {server.ip}.")
    print("  Layer 2 framing is removed and rebuilt for the next link.")
    print("  Layer 3 routing determines the next hop.")

    print("\nAt the server:")
    print("  Physical signals -> frame -> packet -> TCP segment -> application data.")
    print(f"  Final destination: {server.name} ({server.ip})")


# ---------------------------------------------------------------------------
# 25. EDGE CASES AND COMMON MISTAKES
# ---------------------------------------------------------------------------

def edge_cases_demo() -> None:
    print("\n" + "=" * 72)
    print("EDGE CASES AND COMMON MISTAKES")
    print("=" * 72)

    print(
        """
1. OSI is a reference model, not a requirement that every protocol implement
   exactly seven separate software modules.

2. TLS does not always fit neatly into a single OSI layer. It commonly sits
   between application protocols and transport protocols and is often described
   as having Layer 6-like responsibilities.

3. ARP is often described as Layer 2/Layer 3 adjacent because it resolves an
   IPv4 address to a MAC address. The strict seven-layer classification is not
   universally agreed upon.

4. Switches primarily operate at Layer 2, but multilayer switches can also
   perform Layer 3 routing.

5. Routers primarily operate at Layer 3, but real network devices inspect and
   process information from several layers.

6. TCP reliability does not mean the application automatically receives correct
   business-level data. Application validation is still required.

7. UDP does not mean "unreliable application." An application can implement its
   own sequencing, acknowledgements and recovery over UDP.

8. IP addresses identify logical network interfaces, not necessarily people or
   physical machines.

9. A port number does not by itself guarantee that a particular service is safe
   or actually running.

10. Encryption and encoding are different. Base64 encodes data; it does not
    provide confidentiality.
"""
    )


# ---------------------------------------------------------------------------
# 26. VALIDATION AND FAILURE HANDLING
# ---------------------------------------------------------------------------

def validation_demo() -> None:
    print("\n" + "=" * 72)
    print("VALIDATION AND FAILURE CONDITIONS")
    print("=" * 72)

    invalid_values = [
        ("MAC", "GG:11:22:33:44:55"),
        ("IP", "999.1.1.1"),
    ]

    for kind, value in invalid_values:
        try:
            if kind == "MAC":
                MACAddress(value)
            else:
                IPAddress(value)
        except ValueError as error:
            print(f"Rejected invalid {kind} {value!r}: {error}")

    try:
        TCPSegment(
            source_port=70000,
            destination_port=443,
            sequence_number=1,
            acknowledgement_number=0,
            flags="SYN",
        ).validate_ports()
    except ValueError as error:
        print(f"Rejected invalid TCP port: {error}")


# ---------------------------------------------------------------------------
# 27. SMALL END-TO-END SIMULATION
# ---------------------------------------------------------------------------

def end_to_end_simulation() -> None:
    print("\n" + "=" * 72)
    print("END-TO-END SIMULATION")
    print("=" * 72)

    application_message = b"GET / HTTP/1.1"

    # Layer 7
    application = application_message

    # Layer 6
    presentation = application.decode("ascii").encode("utf-8")

    # Layer 5
    session = b"SID=100|" + presentation

    # Layer 4
    transport = TCPSegment(
        source_port=52000,
        destination_port=443,
        sequence_number=10,
        acknowledgement_number=20,
        flags="ACK",
        payload=session,
    )

    # Layer 3
    network = IPv4Packet(
        source_ip=IPAddress("192.168.1.10"),
        destination_ip=IPAddress("203.0.113.20"),
        payload=transport.payload,
    )

    # Layer 2
    frame = EthernetFrame(
        source_mac=MACAddress("AA:AA:AA:AA:AA:10"),
        destination_mac=MACAddress("AA:AA:AA:AA:AA:01"),
        payload=network.payload,
    )
    frame.finalize()

    # Layer 1
    physical = "".join(f"{byte:08b}" for byte in frame.payload)

    print(f"Layer 7 application bytes: {application!r}")
    print(f"Layer 6 representation    : {presentation!r}")
    print(f"Layer 5 session data       : {session!r}")
    print(
        f"Layer 4 TCP                : "
        f"{transport.source_port} -> {transport.destination_port}, "
        f"{transport.flags}"
    )
    print(f"Layer 3 IP                 : {network.source_ip} -> {network.destination_ip}")
    print(f"Layer 2 Ethernet           : {frame.source_mac} -> {frame.destination_mac}")
    print(f"Layer 1 physical bits      : {physical[:80]}...")

    print("\nSimulation complete.")


# ---------------------------------------------------------------------------
# 28. STUDY CHECKPOINTS
# ---------------------------------------------------------------------------

def knowledge_check() -> None:
    print("\n" + "=" * 72)
    print("KNOWLEDGE CHECK")
    print("=" * 72)

    questions = [
        "Which layer is responsible for routing?",
        "Which layer uses MAC addresses?",
        "Which transport protocol provides a connection-oriented byte stream?",
        "What is the common PDU name at Layer 2?",
        "What is the common PDU name at Layer 3?",
        "Which layer deals with physical signals?",
        "Why is the OSI model useful even though the Internet does not strictly implement seven layers?",
    ]

    answers = [
        "Layer 3, Network.",
        "Layer 2, Data Link.",
        "TCP.",
        "Frame.",
        "Packet.",
        "Layer 1, Physical.",
        "It provides a structured framework for understanding, designing and troubleshooting networking systems.",
    ]

    for question, answer in zip(questions, answers):
        print(f"\nQ: {question}")
        print(f"A: {answer}")


# ---------------------------------------------------------------------------
# 29. MAIN PROGRAM
# ---------------------------------------------------------------------------

def main() -> None:
    print_osi_layers()
    explain_pdu_names()
    demonstrate_addressing()

    physical_layer_demo()
    data_link_demo()
    switch_demo()

    network_layer_demo()
    subnetting_demo()
    arp_demo()

    tcp_handshake_demo()
    tcp_vs_udp_demo()
    port_demo()

    session_demo()
    presentation_demo()
    application_layer_demo()

    encapsulated = simulate_encapsulation()
    demonstrate_decapsulation(encapsulated)

    mtu_demo()
    dns_demo()
    checksum_demo()

    troubleshooting_demo()
    security_by_layer_demo()
    performance_demo()

    protocol_mapping_demo()
    osi_vs_tcp_ip_demo()
    packet_journey_demo()

    edge_cases_demo()
    validation_demo()
    end_to_end_simulation()
    knowledge_check()

    print("\n" + "=" * 72)
    print("OSI MODEL STUDY PROGRAM FINISHED")
    print("=" * 72)


if __name__ == "__main__":
    main()
