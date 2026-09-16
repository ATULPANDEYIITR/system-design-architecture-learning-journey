"""
TCP/IP Model: Network Stack and Practical Communication
========================================================

A self-contained study and demonstration program covering the TCP/IP networking
model from beginner concepts through practical and advanced communication.

The program intentionally uses the Python standard library so that most examples
can be executed without third-party dependencies.

Major topics demonstrated:
- Network communication fundamentals
- TCP/IP model and its layers
- Encapsulation and decapsulation
- Application protocols
- Sockets and ports
- IPv4 addressing and subnetting
- DNS
- TCP
- UDP
- Connection establishment and termination
- Reliability, ordering, retransmission, and flow control
- HTTP
- TLS concepts
- Routing and default gateways
- ARP concepts
- Network byte order
- IPv4 packet construction and checksum calculation
- UDP datagrams
- TCP segment structure
- CIDR and subnet calculations
- DNS resolution
- Client/server communication
- Concurrent TCP servers
- Timeouts
- Framing application data over TCP
- Protocol design
- Security considerations
- Diagnostics
- Performance considerations
- Common errors and edge cases

The demonstrations use loopback addresses such as 127.0.0.1 so that they do
not require access to external network hosts.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import ipaddress
import json
import socket
import struct
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional


# ============================================================================
# Utility functions
# ============================================================================

def section(title: str) -> None:
    """Print a readable section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    """Print a smaller heading."""
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def explain(label: str, value: object) -> None:
    """Print a compact label/value pair."""
    print(f"{label}: {value}")


# ============================================================================
# 1. Fundamental networking concepts
# ============================================================================

class ProtocolLayer(Enum):
    """The four-layer TCP/IP model used by this tutorial."""

    APPLICATION = "Application"
    TRANSPORT = "Transport"
    INTERNET = "Internet"
    LINK = "Link / Network Access"


@dataclass(frozen=True)
class NetworkEndpoint:
    """An IP address and transport port identifying a socket endpoint."""

    address: str
    port: int

    def __post_init__(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ValueError("TCP/UDP ports must be between 0 and 65535.")


def demonstrate_basic_concepts() -> None:
    section("1. Networking fundamentals")

    explain("Host", "A device participating in network communication")
    explain("IP address", "Logical address used by the Internet layer")
    explain("MAC address", "Link-layer hardware/network interface identifier")
    explain("Port", "16-bit transport-layer identifier for an application endpoint")
    explain("Socket", "Operating-system communication endpoint")
    explain("Protocol", "Rules defining how communicating systems exchange data")

    endpoint = NetworkEndpoint("127.0.0.1", 8080)
    explain("Example endpoint", endpoint)

    print("\nA complete endpoint is commonly represented as:")
    print("    IP address + transport protocol + port")
    print("    127.0.0.1 + TCP + 8080")


# ============================================================================
# 2. TCP/IP model
# ============================================================================

def demonstrate_tcp_ip_model() -> None:
    section("2. TCP/IP model")

    layers = [
        (
            ProtocolLayer.APPLICATION,
            "HTTP, HTTPS, DNS, DHCP, SSH, SMTP, FTP and application protocols",
        ),
        (
            ProtocolLayer.TRANSPORT,
            "TCP and UDP; ports, segmentation/datagrams, reliability where applicable",
        ),
        (
            ProtocolLayer.INTERNET,
            "IP, routing, addressing, packet forwarding, ICMP",
        ),
        (
            ProtocolLayer.LINK,
            "Ethernet, Wi-Fi, ARP-related local-network operation, frames",
        ),
    ]

    for number, (layer, purpose) in enumerate(layers, start=1):
        print(f"{number}. {layer.value}")
        print(f"   {purpose}")

    print(
        "\nThe TCP/IP model is commonly presented with four layers. "
        "Some educational models separate the Link layer into Data Link "
        "and Physical layers, producing a five-layer teaching model."
    )


# ============================================================================
# 3. Encapsulation and decapsulation
# ============================================================================

@dataclass
class ApplicationData:
    payload: bytes


@dataclass
class TransportSegment:
    header: bytes
    payload: bytes


@dataclass
class InternetPacket:
    header: bytes
    payload: bytes


@dataclass
class LinkFrame:
    header: bytes
    payload: bytes


def demonstrate_encapsulation() -> None:
    section("3. Encapsulation and decapsulation")

    application = ApplicationData(b"GET / HTTP/1.1\r\n\r\n")

    # In real networking, operating-system protocol implementations create
    # transport, IP, and link-layer headers. Here we use illustrative bytes.
    transport = TransportSegment(
        header=b"[TCP HEADER]",
        payload=application.payload,
    )

    internet = InternetPacket(
        header=b"[IP HEADER]",
        payload=transport.header + transport.payload,
    )

    frame = LinkFrame(
        header=b"[ETHERNET HEADER]",
        payload=internet.header + internet.payload,
    )

    explain("Application payload", application.payload)
    explain("Transport payload", transport.payload)
    explain("Internet payload", internet.payload)
    explain("Link-layer payload", frame.payload)

    print("\nConceptual transmission:")
    print("Application data")
    print("  -> TCP segment")
    print("      -> IP packet")
    print("          -> Ethernet/Wi-Fi frame")

    print("\nConceptual reception:")
    print("Frame")
    print("  -> remove link header")
    print("      -> remove IP header")
    print("          -> remove transport header")
    print("              -> deliver application data")


# ============================================================================
# 4. IPv4 addressing
# ============================================================================

def demonstrate_ipv4_addressing() -> None:
    section("4. IPv4 addressing")

    addresses = [
        "127.0.0.1",
        "192.168.1.10",
        "10.20.30.40",
        "8.8.8.8",
    ]

    for text in addresses:
        address = ipaddress.IPv4Address(text)
        print(f"{text:15} integer={int(address):12} loopback={address.is_loopback}")

    print("\nSpecial examples:")
    print("127.0.0.1 is loopback.")
    print("Private IPv4 ranges include 10.0.0.0/8.")
    print("Private IPv4 ranges include 172.16.0.0/12.")
    print("Private IPv4 ranges include 192.168.0.0/16.")


# ============================================================================
# 5. CIDR and subnetting
# ============================================================================

def analyze_subnet(network_text: str) -> None:
    """Display useful subnet information for an IPv4 network."""
    network = ipaddress.ip_network(network_text, strict=False)

    print(f"\nNetwork: {network}")
    print(f"Network address: {network.network_address}")
    print(f"Broadcast address: {network.broadcast_address}")
    print(f"Prefix length: /{network.prefixlen}")
    print(f"Netmask: {network.netmask}")
    print(f"Hostmask: {network.hostmask}")
    print(f"Total addresses: {network.num_addresses}")

    if network.num_addresses > 2:
        print(f"Usable host addresses: {network.num_addresses - 2}")
        hosts = list(network.hosts())
        print(f"First usable: {hosts[0]}")
        print(f"Last usable: {hosts[-1]}")
    else:
        print("This subnet does not have the conventional two-host exclusion.")


def demonstrate_subnetting() -> None:
    section("5. CIDR and subnetting")

    analyze_subnet("192.168.1.0/24")
    analyze_subnet("10.0.0.0/30")

    print("\nCIDR /24 means 24 bits identify the network and 8 bits remain for hosts.")
    print("CIDR notation allows flexible allocation compared with old class-based schemes.")

    network = ipaddress.ip_network("192.168.10.0/24")
    address = ipaddress.ip_address("192.168.10.55")
    print(
        f"\nDoes {address} belong to {network}? "
        f"{address in network}"
    )


# ============================================================================
# 6. TCP and UDP comparison
# ============================================================================

def demonstrate_tcp_udp_comparison() -> None:
    section("6. TCP versus UDP")

    comparison = [
        ("Connection", "Connection-oriented", "Connectionless"),
        ("Reliability", "Reliable byte stream", "Best-effort datagrams"),
        ("Ordering", "Maintains byte-stream order", "No ordering guarantee"),
        ("Retransmission", "Handled by TCP", "Not provided by UDP itself"),
        ("Flow control", "Yes", "No TCP-style flow control"),
        ("Congestion control", "Yes", "Not inherently"),
        ("Message boundaries", "Not preserved", "Datagram boundaries preserved"),
        ("Typical uses", "HTTP, HTTPS, SSH, databases", "DNS, streaming, custom protocols"),
    ]

    print(f"{'Property':20} {'TCP':35} {'UDP':35}")
    print("-" * 92)
    for row in comparison:
        print(f"{row[0]:20} {row[1]:35} {row[2]:35}")


# ============================================================================
# 7. Network byte order
# ============================================================================

def demonstrate_byte_order() -> None:
    section("7. Network byte order")

    value = 8080

    # Network protocols generally encode multi-byte integers in big-endian
    # network byte order.
    packed = struct.pack("!H", value)
    unpacked = struct.unpack("!H", packed)[0]

    print(f"Original port: {value}")
    print(f"Network-order bytes: {packed.hex()}")
    print(f"Decoded port: {unpacked}")

    print("\nThe ! format character tells struct to use network byte order.")


# ============================================================================
# 8. IPv4 checksum
# ============================================================================

def internet_checksum(data: bytes) -> int:
    """
    Calculate the Internet checksum used by several Internet protocols.

    The algorithm treats the input as 16-bit words, adds them using one's
    complement arithmetic, folds carries, and returns the one's complement.
    """
    if len(data) % 2:
        data += b"\x00"

    total = 0

    for offset in range(0, len(data), 2):
        word = (data[offset] << 8) | data[offset + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)

    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


def demonstrate_checksum() -> None:
    section("8. Internet checksum")

    payload = b"TCP/IP educational payload"
    checksum = internet_checksum(payload)

    print(f"Payload: {payload!r}")
    print(f"Checksum: 0x{checksum:04x}")

    # A checksum is useful for detecting accidental corruption, but it is not
    # a cryptographic integrity mechanism.
    print(
        "\nImportant distinction: a checksum can detect many accidental "
        "transmission errors but should not be treated as authentication."
    )


# ============================================================================
# 9. TCP connection lifecycle
# ============================================================================

def demonstrate_tcp_state_machine() -> None:
    section("9. TCP connection lifecycle")

    states = [
        "CLOSED",
        "LISTEN",
        "SYN-SENT",
        "SYN-RECEIVED",
        "ESTABLISHED",
        "FIN-WAIT-1",
        "FIN-WAIT-2",
        "CLOSE-WAIT",
        "LAST-ACK",
        "TIME-WAIT",
    ]

    print("Important TCP states:")
    for state in states:
        print(f"  {state}")

    print(
        "\nTypical three-way handshake:\n"
        "Client -> SYN -> Server\n"
        "Client <- SYN+ACK <- Server\n"
        "Client -> ACK -> Server\n"
        "Both sides can now exchange application data."
    )

    print(
        "\nA TCP connection is a bidirectional byte stream. "
        "The application must define its own message framing."
    )


# ============================================================================
# 10. TCP socket server
# ============================================================================

class TcpEchoServer:
    """
    Small TCP echo server using the Python socket API.

    The server is deliberately restricted to loopback so that this educational
    demonstration does not unintentionally expose a service on a LAN.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None

    def start(self) -> int:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        actual_port = self.server_socket.getsockname()[1]

        print(f"TCP echo server listening on {self.host}:{actual_port}")
        return actual_port

    def serve_one(self) -> None:
        if self.server_socket is None:
            raise RuntimeError("Server has not been started.")

        connection, address = self.server_socket.accept()

        with connection:
            connection.settimeout(3.0)
            data = connection.recv(4096)

            if data:
                connection.sendall(data)

            print(f"Server handled TCP connection from {address}")

    def close(self) -> None:
        if self.server_socket is not None:
            self.server_socket.close()
            self.server_socket = None


def demonstrate_tcp_socket() -> None:
    section("10. Practical TCP communication")

    server = TcpEchoServer()
    port = server.start()

    server_thread = threading.Thread(target=server.serve_one, daemon=True)
    server_thread.start()

    time.sleep(0.05)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.settimeout(3.0)
        client.connect(("127.0.0.1", port))

        message = b"Hello from a TCP client"
        client.sendall(message)

        response = client.recv(4096)

        print(f"Client sent:     {message!r}")
        print(f"Client received: {response!r}")
    finally:
        client.close()

    server_thread.join(timeout=2.0)
    server.close()


# ============================================================================
# 11. TCP message framing
# ============================================================================

def send_framed_message(sock: socket.socket, payload: bytes) -> None:
    """
    Send a length-prefixed application message.

    TCP preserves byte order but does not preserve application message
    boundaries. A four-byte length prefix provides explicit framing.
    """
    if len(payload) > 10_000_000:
        raise ValueError("Message is too large.")

    header = struct.pack("!I", len(payload))
    sock.sendall(header + payload)


def receive_exact(sock: socket.socket, size: int) -> bytes:
    """Receive exactly size bytes or raise ConnectionError."""
    chunks = []
    remaining = size

    while remaining:
        chunk = sock.recv(remaining)

        if not chunk:
            raise ConnectionError("Peer closed the connection prematurely.")

        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def receive_framed_message(sock: socket.socket) -> bytes:
    """Receive one length-prefixed application message."""
    header = receive_exact(sock, 4)
    payload_length = struct.unpack("!I", header)[0]

    if payload_length > 10_000_000:
        raise ValueError("Peer advertised an unreasonably large message.")

    return receive_exact(sock, payload_length)


def demonstrate_tcp_framing() -> None:
    section("11. TCP message framing")

    server_socket, client_socket = socket.socketpair()

    try:
        message = b"This is one complete application-level message."

        send_framed_message(client_socket, message)
        received = receive_framed_message(server_socket)

        print(f"Original message: {message!r}")
        print(f"Received message: {received!r}")
        print(
            "\nThe framing layer is necessary because one send() call does not "
            "guarantee one recv() call will return exactly the same boundary."
        )
    finally:
        server_socket.close()
        client_socket.close()


# ============================================================================
# 12. UDP communication
# ============================================================================

def demonstrate_udp() -> None:
    section("12. Practical UDP communication")

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(2.0)

    try:
        message = b"UDP datagram"

        client.sendto(message, ("127.0.0.1", port))
        received, address = server.recvfrom(4096)

        print(f"UDP server address: {address}")
        print(f"Received datagram: {received!r}")

        server.sendto(b"UDP response", address)
        response, _ = client.recvfrom(4096)

        print(f"Client received: {response!r}")
    finally:
        client.close()
        server.close()


# ============================================================================
# 13. DNS
# ============================================================================

def demonstrate_dns() -> None:
    section("13. DNS resolution")

    hostname = "localhost"

    try:
        addresses = socket.getaddrinfo(
            hostname,
            80,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )

        unique_addresses = sorted({entry[4][0] for entry in addresses})

        print(f"Hostname: {hostname}")
        print(f"Resolved IPv4 addresses: {unique_addresses}")
    except socket.gaierror as error:
        print(f"DNS/name resolution failed: {error}")

    print(
        "\nDNS maps names to records such as A records for IPv4 and AAAA "
        "records for IPv6. Applications generally avoid hard-coding IP "
        "addresses when a stable hostname is available."
    )


# ============================================================================
# 14. HTTP over TCP
# ============================================================================

def demonstrate_http_request_format() -> None:
    section("14. HTTP as an application-layer protocol")

    request = (
        "GET / HTTP/1.1\r\n"
        "Host: example.test\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    print(request)

    print(
        "Conceptual stack:\n"
        "HTTP application message\n"
        "        ↓\n"
        "TCP byte stream\n"
        "        ↓\n"
        "IP packet\n"
        "        ↓\n"
        "Ethernet/Wi-Fi frame"
    )


# ============================================================================
# 15. IPv4 packet construction
# ============================================================================

def build_ipv4_header(
    source: str,
    destination: str,
    payload_length: int,
    protocol: int = 17,
    identification: int = 1,
    ttl: int = 64,
) -> bytes:
    """
    Build a valid basic IPv4 header.

    protocol=6 means TCP.
    protocol=17 means UDP.
    """
    source_ip = ipaddress.IPv4Address(source)
    destination_ip = ipaddress.IPv4Address(destination)

    version = 4
    ihl = 5
    version_and_ihl = (version << 4) | ihl
    dscp_ecn = 0

    total_length = 20 + payload_length
    flags_and_fragment_offset = 0

    checksum_placeholder = 0

    header = struct.pack(
        "!BBHHHBBH4s4s",
        version_and_ihl,
        dscp_ecn,
        total_length,
        identification,
        flags_and_fragment_offset,
        ttl,
        protocol,
        checksum_placeholder,
        source_ip.packed,
        destination_ip.packed,
    )

    checksum = internet_checksum(header)

    return struct.pack(
        "!BBHHHBBH4s4s",
        version_and_ihl,
        dscp_ecn,
        total_length,
        identification,
        flags_and_fragment_offset,
        ttl,
        protocol,
        checksum,
        source_ip.packed,
        destination_ip.packed,
    )


def parse_ipv4_header(header: bytes) -> dict[str, object]:
    """Parse the basic fields of a 20-byte IPv4 header."""
    if len(header) < 20:
        raise ValueError("An IPv4 header must contain at least 20 bytes.")

    fields = struct.unpack("!BBHHHBBH4s4s", header[:20])

    version_and_ihl = fields[0]
    version = version_and_ihl >> 4
    ihl = version_and_ihl & 0x0F

    return {
        "version": version,
        "header_length_bytes": ihl * 4,
        "total_length": fields[2],
        "identification": fields[3],
        "ttl": fields[5],
        "protocol": fields[6],
        "checksum": f"0x{fields[7]:04x}",
        "source": str(ipaddress.IPv4Address(fields[8])),
        "destination": str(ipaddress.IPv4Address(fields[9])),
    }


def demonstrate_ipv4_packet_structure() -> None:
    section("15. Constructing and parsing an IPv4 header")

    payload = b"hello"
    header = build_ipv4_header(
        "127.0.0.1",
        "127.0.0.1",
        payload_length=len(payload),
        protocol=17,
    )

    print(f"Header bytes: {header.hex()}")
    print(json.dumps(parse_ipv4_header(header), indent=2))


# ============================================================================
# 16. TCP segment conceptual construction
# ============================================================================

def build_tcp_header(
    source_port: int,
    destination_port: int,
    sequence_number: int,
    acknowledgment_number: int,
    flags: int,
    window_size: int = 65535,
) -> bytes:
    """
    Build a basic 20-byte TCP header without options.

    TCP flags:
    FIN=0x01, SYN=0x02, RST=0x04, PSH=0x08,
    ACK=0x10, URG=0x20, ECE=0x40, CWR=0x80.
    """
    if not 0 <= source_port <= 65535:
        raise ValueError("Invalid source port.")

    if not 0 <= destination_port <= 65535:
        raise ValueError("Invalid destination port.")

    data_offset = 5
    offset_and_reserved = data_offset << 4

    return struct.pack(
        "!HHIIBBHHH",
        source_port,
        destination_port,
        sequence_number,
        acknowledgment_number,
        offset_and_reserved,
        flags,
        window_size,
        0,
        0,
    )


def demonstrate_tcp_header() -> None:
    section("16. TCP segment structure")

    syn_flag = 0x02

    header = build_tcp_header(
        source_port=50000,
        destination_port=443,
        sequence_number=1000,
        acknowledgment_number=0,
        flags=syn_flag,
    )

    print(f"TCP header length: {len(header)} bytes")
    print(f"TCP header: {header.hex()}")

    print(
        "\nA real TCP segment also involves a checksum calculated using a "
        "pseudo-header containing IP addresses, the TCP protocol number, "
        "and the TCP length."
    )


# ============================================================================
# 17. Routing concepts
# ============================================================================

def demonstrate_routing() -> None:
    section("17. Routing and default gateways")

    routes = [
        ("127.0.0.0/8", "local loopback"),
        ("192.168.1.0/24", "local LAN"),
        ("0.0.0.0/0", "default route"),
    ]

    for destination, meaning in routes:
        print(f"{destination:18} -> {meaning}")

    print(
        "\nA router examines the destination IP address and chooses a route. "
        "The longest-prefix-match principle selects the most specific "
        "matching route in typical IP routing tables."
    )


# ============================================================================
# 18. ARP concepts
# ============================================================================

def demonstrate_arp_concept() -> None:
    section("18. ARP and local delivery")

    print("Example:")
    print("Host A wants to send an IPv4 packet to 192.168.1.20.")
    print("If Host A needs the destination MAC address, it can use ARP on IPv4 LANs.")
    print("ARP request: Who has 192.168.1.20?")
    print("ARP response: 192.168.1.20 is at aa:bb:cc:dd:ee:ff")

    print(
        "\nFor traffic destined outside the local subnet, a host normally "
        "sends the frame to the MAC address of the next-hop router rather "
        "than the remote host's MAC address."
    )


# ============================================================================
# 19. Socket address families
# ============================================================================

def demonstrate_ipv4_and_ipv6() -> None:
    section("19. IPv4 and IPv6")

    ipv4 = ipaddress.ip_address("192.0.2.10")
    ipv6 = ipaddress.ip_address("2001:db8::10")

    print(f"IPv4: {ipv4}")
    print(f"IPv6: {ipv6}")

    print(
        "\nIPv6 uses 128-bit addresses. IPv4 uses 32-bit addresses. "
        "Python's socket library supports both through different address "
        "families such as AF_INET and AF_INET6."
    )


# ============================================================================
# 20. Concurrent TCP server
# ============================================================================

class ThreadedTcpServer:
    """
    Small concurrent TCP server.

    This demonstrates one common application architecture: one listening socket
    accepts connections, and worker threads process independent clients.

    Production systems may instead use asynchronous I/O, worker processes,
    event loops, a reverse proxy, or a dedicated application server.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self._server_socket: Optional[socket.socket] = None
        self._stop = threading.Event()

    def start(self) -> int:
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(16)
        self._server_socket.settimeout(0.2)
        return self._server_socket.getsockname()[1]

    def _handle_client(self, connection: socket.socket) -> None:
        with connection:
            connection.settimeout(3.0)

            try:
                while True:
                    data = connection.recv(4096)

                    if not data:
                        break

                    connection.sendall(b"ACK:" + data)
            except (socket.timeout, ConnectionError, OSError):
                pass

    def serve(self) -> None:
        if self._server_socket is None:
            raise RuntimeError("Server has not been started.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            while not self._stop.is_set():
                try:
                    connection, _ = self._server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                executor.submit(self._handle_client, connection)

    def stop(self) -> None:
        self._stop.set()

        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None


def demonstrate_concurrent_server() -> None:
    section("20. Concurrent TCP communication")

    server = ThreadedTcpServer()
    port = server.start()

    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()

    time.sleep(0.05)

    def client_task(number: int) -> bytes:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            client.settimeout(2.0)
            client.connect(("127.0.0.1", port))
            client.sendall(f"client-{number}".encode())
            return client.recv(4096)
        finally:
            client.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(client_task, range(4)))

    for response in responses:
        print(response.decode())

    server.stop()
    thread.join(timeout=1.0)


# ============================================================================
# 21. Timeouts and defensive networking
# ============================================================================

def demonstrate_timeouts() -> None:
    section("21. Timeouts and failure handling")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.settimeout(0.5)

        # Port 1 on loopback is normally not an application server. The
        # result is intentionally treated as a demonstration of failure
        # handling rather than relying on one exact operating-system error.
        try:
            sock.connect(("127.0.0.1", 1))
        except (socket.timeout, ConnectionRefusedError, OSError) as error:
            print(f"Connection attempt handled safely: {type(error).__name__}")
    finally:
        sock.close()

    print(
        "\nProduction network code should assume that peers disappear, "
        "packets are delayed, DNS can fail, connections can time out, "
        "addresses can change, and input can be malicious."
    )


# ============================================================================
# 22. Application protocol validation
# ============================================================================

MAX_USERNAME_LENGTH = 64


def validate_username(username: str) -> bool:
    """
    Example application-layer validation.

    Validation belongs at the application boundary even when the underlying
    TCP connection is reliable.
    """
    if not username:
        return False

    if len(username) > MAX_USERNAME_LENGTH:
        return False

    return all(character.isalnum() or character in "_-" for character in username)


def demonstrate_application_validation() -> None:
    section("22. Application-layer validation")

    examples = [
        "alice",
        "alice_123",
        "bad user",
        "",
        "x" * 65,
    ]

    for username in examples:
        print(f"{username!r:70} -> {validate_username(username)}")


# ============================================================================
# 23. Serialization
# ============================================================================

def demonstrate_json_protocol() -> None:
    section("23. Structured application data")

    message = {
        "version": 1,
        "type": "measurement",
        "device_id": "sensor-17",
        "value": 23.5,
        "unit": "C",
    }

    encoded = json.dumps(message).encode("utf-8")

    print(f"JSON bytes: {encoded!r}")
    print(f"Decoded object: {json.loads(encoded.decode('utf-8'))}")

    print(
        "\nJSON is an application-layer representation. TCP does not understand "
        "the JSON structure; TCP only transports bytes."
    )


# ============================================================================
# 24. Cryptographic integrity versus transport checksums
# ============================================================================

def demonstrate_integrity_distinction() -> None:
    section("24. Checksums versus cryptographic integrity")

    payload = b"important application message"

    checksum = internet_checksum(payload)
    digest = hashlib.sha256(payload).hexdigest()

    print(f"Internet checksum: 0x{checksum:04x}")
    print(f"SHA-256 digest:    {digest}")

    print(
        "\nA checksum is designed for error detection. A cryptographic hash "
        "provides a much stronger integrity primitive but does not itself "
        "authenticate a sender. TLS uses cryptographic mechanisms to provide "
        "confidentiality, integrity, and peer authentication under its trust model."
    )


# ============================================================================
# 25. TLS conceptual demonstration
# ============================================================================

def demonstrate_tls_concept() -> None:
    section("25. TLS and HTTPS")

    print("HTTP:")
    print("    application data -> TCP -> IP -> link")

    print("\nHTTPS:")
    print("    HTTP application data -> TLS -> TCP -> IP -> link")

    print(
        "\nTLS is not a replacement for TCP. It is a security protocol layered "
        "between an application protocol such as HTTP and a transport such as TCP."
    )

    print(
        "\nModern secure deployments must validate certificates and hostnames. "
        "Disabling certificate verification removes important security guarantees."
    )


# ============================================================================
# 26. Port classification
# ============================================================================

def demonstrate_ports() -> None:
    section("26. Ports")

    examples = {
        22: "SSH",
        53: "DNS",
        80: "HTTP",
        443: "HTTPS",
        3306: "Common MySQL port",
        5432: "Common PostgreSQL port",
    }

    for port, service in examples.items():
        print(f"{port:5} -> {service}")

    print(
        "\nA port number alone does not force an application to use a particular "
        "protocol. It is a convention. A server can technically listen on many "
        "different ports if the operating system permits it."
    )


# ============================================================================
# 27. TCP behavior and application semantics
# ============================================================================

def demonstrate_tcp_stream_semantics() -> None:
    section("27. TCP byte-stream semantics")

    print(
        "Suppose an application sends three logical messages:\n"
        "    MESSAGE-A\n"
        "    MESSAGE-B\n"
        "    MESSAGE-C\n"
    )

    print(
        "TCP may deliver bytes to recv() in chunks such as:\n"
        "    MESSAGE-\n"
        "    AMESSAGE-BMES\n"
        "    SAGE-C\n"
    )

    print(
        "\nThe bytes are reliable and ordered, but application boundaries "
        "are not preserved. Length prefixes, delimiters, fixed-size records, "
        "or self-describing formats can solve this problem."
    )


# ============================================================================
# 28. Nagle, buffering, and latency concepts
# ============================================================================

def demonstrate_performance_concepts() -> None:
    section("28. Performance considerations")

    print("Important variables:")
    print("  - Round-trip time (RTT)")
    print("  - Bandwidth")
    print("  - Packet loss")
    print("  - Congestion")
    print("  - Socket buffer sizes")
    print("  - Serialization cost")
    print("  - System-call overhead")
    print("  - Number of concurrent connections")

    print(
        "\nBandwidth measures capacity. Latency measures delay. A connection "
        "can have very high bandwidth and still feel slow when each operation "
        "requires many sequential round trips."
    )

    print(
        "\nFor latency-sensitive TCP applications, buffering behavior and "
        "algorithms such as Nagle's algorithm can matter. Applications should "
        "measure real workloads rather than assuming that one optimization "
        "is always appropriate."
    )


# ============================================================================
# 29. Security checklist
# ============================================================================

def demonstrate_security_principles() -> None:
    section("29. Network security principles")

    principles = [
        "Do not trust data merely because it arrived through TCP.",
        "Validate message sizes before allocating large buffers.",
        "Use timeouts to limit indefinitely blocked operations.",
        "Use TLS for sensitive application data in transit.",
        "Validate TLS certificates and hostnames.",
        "Authenticate users and services at the application layer.",
        "Use least privilege for network services.",
        "Do not expose development servers unnecessarily.",
        "Log security-relevant failures without leaking secrets.",
        "Rate-limit externally reachable services where appropriate.",
        "Treat deserialization and parsers as security-sensitive components.",
    ]

    for item in principles:
        print(f"- {item}")


# ============================================================================
# 30. Troubleshooting methodology
# ============================================================================

def demonstrate_troubleshooting() -> None:
    section("30. Network troubleshooting methodology")

    steps = [
        ("1", "Check the application configuration."),
        ("2", "Check whether the destination hostname resolves."),
        ("3", "Check IP reachability and routing."),
        ("4", "Check whether the destination port is listening."),
        ("5", "Check firewall and security policy."),
        ("6", "Check the transport behavior: timeout, reset, refusal."),
        ("7", "Inspect application protocol messages."),
        ("8", "Use packet captures when appropriate."),
        ("9", "Measure latency, loss, throughput, and connection counts."),
    ]

    for number, description in steps:
        print(f"{number}. {description}")

    print(
        "\nUseful command-line tools on many systems include ping, traceroute/"
        "tracert, nslookup/dig, ip/ipconfig, ss/netstat, curl, and packet "
        "capture tools. Their availability and exact syntax depend on the OS."
    )


# ============================================================================
# 31. OSI comparison
# ============================================================================

def demonstrate_osi_comparison() -> None:
    section("31. TCP/IP model versus OSI model")

    comparison = [
        ("TCP/IP Application", "OSI Application + Presentation + Session"),
        ("TCP/IP Transport", "OSI Transport"),
        ("TCP/IP Internet", "OSI Network"),
        ("TCP/IP Link", "OSI Data Link + Physical"),
    ]

    print(f"{'TCP/IP':30} {'Approximate OSI correspondence':45}")
    print("-" * 78)

    for tcp_ip, osi in comparison:
        print(f"{tcp_ip:30} {osi:45}")

    print(
        "\nThe models are conceptual frameworks. Real protocols do not always "
        "fit perfectly into a single theoretical layer."
    )


# ============================================================================
# 32. End-to-end practical workflow
# ============================================================================

def demonstrate_complete_workflow() -> None:
    section("32. Complete practical communication workflow")

    workflow = [
        "1. User enters https://example.test.",
        "2. Application parses the URL.",
        "3. DNS resolution obtains an IP address.",
        "4. The host determines whether the destination is local or remote.",
        "5. A route is selected.",
        "6. TCP establishes a connection to port 443.",
        "7. TLS negotiates security parameters and authenticates the server.",
        "8. HTTP request bytes are generated.",
        "9. TCP transports the bytes reliably as a byte stream.",
        "10. IP forwards packets across networks using routers.",
        "11. Link-layer protocols deliver frames over each local hop.",
        "12. The remote host reverses the process.",
        "13. HTTP response data returns through the stack.",
        "14. The browser interprets the response and renders the resource.",
    ]

    for item in workflow:
        print(item)


# ============================================================================
# 33. Edge cases
# ============================================================================

def demonstrate_edge_cases() -> None:
    section("33. Important edge cases")

    cases = [
        "DNS name does not resolve.",
        "DNS returns multiple addresses.",
        "TCP connection is refused.",
        "TCP connection times out.",
        "Peer closes the connection unexpectedly.",
        "recv() returns fewer bytes than expected.",
        "Peer advertises an excessively large application message.",
        "Application receives malformed input.",
        "IPv4 packet is fragmented.",
        "Network path has a smaller MTU.",
        "TCP connection is reset.",
        "Temporary network congestion increases latency.",
        "Server reaches its connection or file-descriptor limits.",
        "TLS certificate validation fails.",
        "IPv4 connectivity exists while IPv6 connectivity fails, or vice versa.",
    ]

    for case in cases:
        print(f"- {case}")


# ============================================================================
# 34. Small protocol implementation
# ============================================================================

class MiniProtocol:
    """
    A tiny application protocol demonstrating:

    [4-byte length][UTF-8 JSON payload]

    The protocol has explicit framing and a version field.
    """

    VERSION = 1
    MAX_PAYLOAD = 1_000_000

    @classmethod
    def encode(cls, message_type: str, body: dict) -> bytes:
        if not validate_username(body.get("sender", "system")):
            raise ValueError("Invalid sender.")

        document = {
            "version": cls.VERSION,
            "type": message_type,
            "body": body,
        }

        payload = json.dumps(
            document,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        if len(payload) > cls.MAX_PAYLOAD:
            raise ValueError("Payload exceeds protocol limit.")

        return struct.pack("!I", len(payload)) + payload

    @classmethod
    def decode(cls, packet: bytes) -> dict:
        if len(packet) < 4:
            raise ValueError("Packet is shorter than its framing header.")

        declared_length = struct.unpack("!I", packet[:4])[0]

        if declared_length > cls.MAX_PAYLOAD:
            raise ValueError("Declared payload is too large.")

        if len(packet) != declared_length + 4:
            raise ValueError("Packet length does not match framing header.")

        document = json.loads(packet[4:].decode("utf-8"))

        if document.get("version") != cls.VERSION:
            raise ValueError("Unsupported protocol version.")

        return document


def demonstrate_mini_protocol() -> None:
    section("34. Designing an application protocol")

    packet = MiniProtocol.encode(
        "measurement",
        {
            "sender": "sensor_17",
            "temperature": 21.75,
            "unit": "C",
        },
    )

    decoded = MiniProtocol.decode(packet)

    print(f"Encoded packet: {packet!r}")
    print(f"Decoded message: {json.dumps(decoded, indent=2)}")


# ============================================================================
# 35. Performance measurement
# ============================================================================

def demonstrate_local_performance() -> None:
    section("35. Simple local performance measurement")

    server, client = socket.socketpair()

    payload = b"x" * 1024
    repetitions = 1000

    start = time.perf_counter()

    try:
        for _ in range(repetitions):
            client.sendall(payload)
            received = receive_exact(server, len(payload))

            if received != payload:
                raise RuntimeError("Payload mismatch.")
    finally:
        server.close()
        client.close()

    elapsed = time.perf_counter() - start
    total_bytes = len(payload) * repetitions

    print(f"Messages: {repetitions}")
    print(f"Total payload bytes: {total_bytes}")
    print(f"Elapsed seconds: {elapsed:.6f}")
    print(f"Payload throughput: {total_bytes / elapsed / 1024:.2f} KiB/s")

    print(
        "\nThis is only a local benchmark. It does not represent Internet "
        "throughput because it excludes real routing, physical links, "
        "congestion, Internet RTT, and packet loss."
    )


# ============================================================================
# 36. Practical design rules
# ============================================================================

def demonstrate_design_rules() -> None:
    section("36. Practical network application design rules")

    rules = [
        "Define the application protocol before implementing the transport layer.",
        "Choose TCP when reliable ordered byte-stream delivery is appropriate.",
        "Choose UDP only when the application can tolerate or implement missing semantics.",
        "Use explicit framing for structured messages over TCP.",
        "Validate every externally supplied length and field.",
        "Set reasonable timeouts.",
        "Handle partial reads and writes correctly.",
        "Close sockets deterministically.",
        "Avoid blocking indefinitely on untrusted peers.",
        "Separate transport logic from business logic.",
        "Instrument connection counts, latency, errors, and throughput.",
        "Use TLS for confidential or authenticated communication.",
        "Design for DNS failures, address changes, retries, and partial failures.",
        "Test malformed packets and unexpected connection termination.",
    ]

    for rule in rules:
        print(f"- {rule}")


# ============================================================================
# 37. Main program
# ============================================================================

def main() -> None:
    """Run the complete educational demonstration suite."""
    demonstrate_basic_concepts()
    demonstrate_tcp_ip_model()
    demonstrate_encapsulation()
    demonstrate_ipv4_addressing()
    demonstrate_subnetting()
    demonstrate_tcp_udp_comparison()
    demonstrate_byte_order()
    demonstrate_checksum()
    demonstrate_tcp_state_machine()
    demonstrate_tcp_socket()
    demonstrate_tcp_framing()
    demonstrate_udp()
    demonstrate_dns()
    demonstrate_http_request_format()
    demonstrate_ipv4_packet_structure()
    demonstrate_tcp_header()
    demonstrate_routing()
    demonstrate_arp_concept()
    demonstrate_ipv4_and_ipv6()
    demonstrate_concurrent_server()
    demonstrate_timeouts()
    demonstrate_application_validation()
    demonstrate_json_protocol()
    demonstrate_integrity_distinction()
    demonstrate_tls_concept()
    demonstrate_ports()
    demonstrate_tcp_stream_semantics()
    demonstrate_performance_concepts()
    demonstrate_security_principles()
    demonstrate_troubleshooting()
    demonstrate_osi_comparison()
    demonstrate_complete_workflow()
    demonstrate_edge_cases()
    demonstrate_mini_protocol()
    demonstrate_local_performance()
    demonstrate_design_rules()

    section("End of TCP/IP study program")
    print(
        "The examples covered the TCP/IP stack from application data through "
        "transport, Internet, and link-layer concepts, including practical "
        "socket communication and protocol construction."
    )


if __name__ == "__main__":
    main()
