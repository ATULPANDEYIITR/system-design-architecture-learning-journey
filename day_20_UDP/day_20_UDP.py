"""
UDP (User Datagram Protocol): Connectionless Communication, Speed vs Reliability

A self-contained study program covering UDP from absolute beginner concepts through
advanced implementation considerations.

The examples use only Python's standard library.
"""

from __future__ import annotations

import random
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# =============================================================================
# 1. FUNDAMENTALS
# =============================================================================

def explain_fundamentals() -> None:
    print("=" * 78)
    print("UDP FUNDAMENTALS")
    print("=" * 78)

    concepts = {
        "UDP": (
            "User Datagram Protocol. A transport-layer protocol that sends "
            "independent datagrams without establishing a connection."
        ),
        "Datagram": (
            "A self-contained packet of data containing source/destination "
            "transport information and an application payload."
        ),
        "Connectionless": (
            "UDP does not perform a connection-establishment handshake before "
            "sending application data."
        ),
        "Best effort": (
            "UDP does not guarantee delivery, ordering, duplicate suppression, "
            "or retransmission."
        ),
        "Port": (
            "A 16-bit transport-layer identifier used to deliver data to an "
            "application or service."
        ),
        "Checksum": (
            "UDP includes a checksum for detecting corruption in transit. "
            "Detection is not the same as recovery."
        ),
    }

    for name, description in concepts.items():
        print(f"{name:16}: {description}")

    print("\nThe central design trade-off:")
    print("  TCP -> reliability, ordering, congestion control, connection state")
    print("  UDP -> minimal transport overhead, low latency, application control")


# =============================================================================
# 2. UDP HEADER
# =============================================================================

def demonstrate_udp_header() -> None:
    print("\n" + "=" * 78)
    print("UDP HEADER")
    print("=" * 78)

    print(
        """
A UDP datagram has an 8-byte transport header:

    +-------------------+-------------------+
    | Source Port       | Destination Port  |
    +-------------------+-------------------+
    | Length            | Checksum          |
    +-------------------+-------------------+
    | Payload                               |
    +---------------------------------------+

Each header field is 16 bits.

Source port:
    Identifies the sending application endpoint. It may be zero when the
    application does not require a return port.

Destination port:
    Identifies the receiving service.

Length:
    Total UDP length = UDP header + UDP payload.

Checksum:
    Detects corruption. In IPv4, checksum behavior has historically allowed
    zero as "checksum not generated"; IPv6 requires UDP checksums except where
    specific standards provide an exception.
"""
    )

    source_port = 50000
    destination_port = 53
    payload = b"example"

    udp_length = 8 + len(payload)

    print(f"Source port:      {source_port}")
    print(f"Destination port: {destination_port}")
    print(f"Payload length:   {len(payload)} bytes")
    print(f"UDP length:       {udp_length} bytes")


# =============================================================================
# 3. BASIC UDP SOCKET
# =============================================================================

def basic_udp_server() -> None:
    """
    Create a UDP server socket without actually blocking waiting for external
    network traffic.

    AF_INET selects IPv4.
    SOCK_DGRAM selects UDP datagrams.
    """
    print("\n" + "=" * 78)
    print("BASIC UDP SOCKET")
    print("=" * 78)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Binding to port 0 asks the operating system to select an available port.
    server_socket.bind(("127.0.0.1", 0))

    address = server_socket.getsockname()
    print(f"UDP server bound to {address[0]}:{address[1]}")

    server_socket.close()


def basic_udp_exchange() -> None:
    """
    Run a complete local UDP request/response exchange.

    UDP does not require connect() for normal communication. sendto() supplies
    the destination address for each datagram.
    """
    print("\n" + "=" * 78)
    print("LOCAL UDP REQUEST/RESPONSE")
    print("=" * 78)

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    server.bind(("127.0.0.1", 0))
    server_address = server.getsockname()

    try:
        message = b"Hello UDP server"
        client.sendto(message, server_address)

        received, client_address = server.recvfrom(65535)

        print(f"Server received: {received.decode()}")
        print(f"Client address:   {client_address}")

        response = b"UDP response received"
        server.sendto(response, client_address)

        reply, _ = client.recvfrom(65535)
        print(f"Client received:  {reply.decode()}")
    finally:
        client.close()
        server.close()


# =============================================================================
# 4. DATAGRAM SEMANTICS
# =============================================================================

def demonstrate_datagram_semantics() -> None:
    print("\n" + "=" * 78)
    print("DATAGRAM SEMANTICS")
    print("=" * 78)

    print(
        """
UDP preserves datagram boundaries at the socket API.

If an application performs:

    sendto(b"ABC")
    sendto(b"DEF")

the receiver normally observes two separate datagrams:

    recvfrom(...) -> b"ABC"
    recvfrom(...) -> b"DEF"

This differs from TCP, which exposes a byte stream. TCP does not preserve the
boundaries between individual send() operations.
"""
    )

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    receiver.bind(("127.0.0.1", 0))
    address = receiver.getsockname()

    try:
        sender.sendto(b"ABC", address)
        sender.sendto(b"DEF", address)

        first, _ = receiver.recvfrom(100)
        second, _ = receiver.recvfrom(100)

        print(f"First datagram:  {first}")
        print(f"Second datagram: {second}")
    finally:
        sender.close()
        receiver.close()


# =============================================================================
# 5. PACKET SIZE AND TRUNCATION
# =============================================================================

def demonstrate_receive_buffer() -> None:
    print("\n" + "=" * 78)
    print("RECEIVE BUFFER SIZE")
    print("=" * 78)

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    receiver.bind(("127.0.0.1", 0))
    address = receiver.getsockname()

    try:
        payload = b"0123456789ABCDEFGHIJ"
        sender.sendto(payload, address)

        # A deliberately small receive buffer demonstrates an important edge
        # case: a UDP datagram can be larger than the application's buffer.
        received, _ = receiver.recvfrom(10)

        print(f"Original payload: {payload}")
        print(f"Buffer size:      10 bytes")
        print(f"Received data:    {received}")
        print(
            "A small receive buffer can cause the application-visible data "
            "to be truncated."
        )
    finally:
        sender.close()
        receiver.close()


# =============================================================================
# 6. UDP HAS NO BUILT-IN RELIABILITY
# =============================================================================

def simulate_unreliable_network(
    messages: List[str],
    loss_probability: float = 0.25,
    duplicate_probability: float = 0.10,
    reorder_probability: float = 0.20,
) -> List[str]:
    """
    Simulate network behavior that UDP itself does not correct.

    This function is not a real network implementation. It is a deterministic
    conceptual model of packet loss, duplication, and reordering.
    """
    packets: List[str] = []

    for message in messages:
        if random.random() < loss_probability:
            continue

        packets.append(message)

        if random.random() < duplicate_probability:
            packets.append(message)

    if random.random() < reorder_probability:
        random.shuffle(packets)

    return packets


def demonstrate_unreliability() -> None:
    print("\n" + "=" * 78)
    print("LOSS, DUPLICATION, AND REORDERING")
    print("=" * 78)

    random.seed(42)

    messages = [f"packet-{number}" for number in range(1, 11)]
    received = simulate_unreliable_network(messages)

    print("Sent:")
    print(messages)
    print("\nReceived:")
    print(received)

    missing = [message for message in messages if message not in received]
    duplicates = len(received) - len(set(received))

    print(f"\nMissing messages: {missing}")
    print(f"Duplicate count:  {duplicates}")

    print(
        "\nUDP does not automatically retransmit missing data or reorder "
        "datagrams for the application."
    )


# =============================================================================
# 7. BUILDING RELIABILITY ABOVE UDP
# =============================================================================

@dataclass
class ReliablePacket:
    sequence_number: int
    payload: bytes

    def encode(self) -> bytes:
        """
        Simple application-layer packet format:

            4 bytes sequence number
            payload

        Network byte order ('!') is used so different machine architectures
        agree on the integer representation.
        """
        return struct.pack("!I", self.sequence_number) + self.payload

    @staticmethod
    def decode(data: bytes) -> "ReliablePacket":
        if len(data) < 4:
            raise ValueError("Packet is shorter than its sequence header.")

        sequence_number = struct.unpack("!I", data[:4])[0]
        return ReliablePacket(sequence_number, data[4:])


def demonstrate_sequence_numbers() -> None:
    print("\n" + "=" * 78)
    print("SEQUENCE NUMBERS")
    print("=" * 78)

    packets = [
        ReliablePacket(1, b"first"),
        ReliablePacket(2, b"second"),
        ReliablePacket(3, b"third"),
    ]

    encoded = [packet.encode() for packet in packets]

    for raw_packet in encoded:
        decoded = ReliablePacket.decode(raw_packet)
        print(
            f"Sequence={decoded.sequence_number}, "
            f"payload={decoded.payload.decode()}"
        )

    print(
        "\nSequence numbers let an application detect missing, duplicated, "
        "or out-of-order packets."
    )


# =============================================================================
# 8. ACKNOWLEDGEMENTS AND RETRANSMISSION
# =============================================================================

@dataclass
class PendingPacket:
    packet: ReliablePacket
    sent_at: float
    retries: int = 0


class ReliableUdpSenderModel:
    """
    A conceptual reliable-UDP sender.

    It is intentionally implemented as a model rather than a production
    transport protocol. A production implementation would require careful
    handling of congestion control, retransmission timers, sequence-number
    wraparound, security, MTU constraints, and peer state.
    """

    def __init__(self, timeout: float = 0.5, maximum_retries: int = 3):
        if timeout <= 0:
            raise ValueError("Timeout must be positive.")
        if maximum_retries < 0:
            raise ValueError("Maximum retries cannot be negative.")

        self.timeout = timeout
        self.maximum_retries = maximum_retries
        self.next_sequence = 1
        self.pending: Dict[int, PendingPacket] = {}

    def create_packet(self, payload: bytes) -> ReliablePacket:
        packet = ReliablePacket(self.next_sequence, payload)
        self.next_sequence += 1
        return packet

    def mark_sent(self, packet: ReliablePacket) -> None:
        self.pending[packet.sequence_number] = PendingPacket(
            packet=packet,
            sent_at=time.monotonic(),
        )

    def acknowledge(self, sequence_number: int) -> bool:
        """
        Return True if an outstanding packet was acknowledged.
        """
        return self.pending.pop(sequence_number, None) is not None

    def packets_needing_retransmission(self) -> List[ReliablePacket]:
        now = time.monotonic()
        result: List[ReliablePacket] = []

        for sequence_number, pending_packet in list(self.pending.items()):
            if now - pending_packet.sent_at >= self.timeout:
                if pending_packet.retries >= self.maximum_retries:
                    del self.pending[sequence_number]
                    continue

                pending_packet.retries += 1
                pending_packet.sent_at = now
                result.append(pending_packet.packet)

        return result


def demonstrate_reliability_model() -> None:
    print("\n" + "=" * 78)
    print("RELIABILITY BUILT ABOVE UDP")
    print("=" * 78)

    sender = ReliableUdpSenderModel(timeout=0.01, maximum_retries=2)

    packet = sender.create_packet(b"important-data")
    sender.mark_sent(packet)

    print(f"Created sequence number: {packet.sequence_number}")
    print(f"Outstanding packets: {list(sender.pending)}")

    # Waiting long enough causes the conceptual timer to expire.
    time.sleep(0.015)

    retransmissions = sender.packets_needing_retransmission()
    print(
        "Retransmission candidates:",
        [packet.sequence_number for packet in retransmissions],
    )

    acknowledged = sender.acknowledge(packet.sequence_number)
    print(f"ACK processed: {acknowledged}")
    print(f"Outstanding packets: {list(sender.pending)}")


# =============================================================================
# 9. STOP-AND-WAIT RELIABILITY
# =============================================================================

class StopAndWaitProtocol:
    """
    A small educational model of stop-and-wait ARQ.

    ARQ = Automatic Repeat reQuest.

    The sender sends one packet and waits for an acknowledgement before sending
    the next packet. This is easy to understand but can have poor throughput
    when round-trip latency is high.
    """

    def __init__(self, timeout: float = 1.0):
        self.timeout = timeout
        self.sequence = 0

    def build_data(self, payload: bytes) -> bytes:
        packet = ReliablePacket(self.sequence, payload)
        return packet.encode()

    def receive_ack(self, acknowledged_sequence: int) -> bool:
        if acknowledged_sequence != self.sequence:
            return False

        self.sequence = (self.sequence + 1) % 2
        return True


def demonstrate_stop_and_wait() -> None:
    print("\n" + "=" * 78)
    print("STOP-AND-WAIT ARQ")
    print("=" * 78)

    protocol = StopAndWaitProtocol()

    first = protocol.build_data(b"message-A")
    print("First packet:", ReliablePacket.decode(first))
    print("Wrong ACK accepted:", protocol.receive_ack(7))
    print("Correct ACK accepted:", protocol.receive_ack(0))

    second = protocol.build_data(b"message-B")
    print("Second packet:", ReliablePacket.decode(second))


# =============================================================================
# 10. CHECKSUM CONCEPT
# =============================================================================

def internet_checksum(data: bytes) -> int:
    """
    Educational implementation of the Internet checksum algorithm.

    The real UDP checksum also incorporates a pseudo-header containing IP
    addressing information, protocol number, and UDP length. This function
    demonstrates the underlying one's-complement checksum operation only.
    """
    if len(data) % 2:
        data += b"\x00"

    total = 0

    for index in range(0, len(data), 2):
        word = (data[index] << 8) | data[index + 1]
        total += word

        # Fold carries back into the low 16 bits.
        total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


def demonstrate_checksum() -> None:
    print("\n" + "=" * 78)
    print("CHECKSUM")
    print("=" * 78)

    payload = b"UDP integrity example"
    checksum = internet_checksum(payload)

    print(f"Payload:  {payload}")
    print(f"Checksum: 0x{checksum:04X}")

    altered_payload = b"UDP integrity examples"
    altered_checksum = internet_checksum(altered_payload)

    print(f"Changed checksum: 0x{altered_checksum:04X}")
    print("A checksum can detect many accidental transmission errors.")


# =============================================================================
# 11. UDP CONNECT()
# =============================================================================

def demonstrate_udp_connect() -> None:
    print("\n" + "=" * 78)
    print("UDP connect()")
    print("=" * 78)

    """
    Calling connect() on a UDP socket does NOT create a TCP-style connection.

    It primarily associates a default peer with the socket. The OS can then
    use send()/recv() instead of sendto()/recvfrom(), and incoming datagrams
    from unrelated peers are filtered for that socket.
    """

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        client.connect(("127.0.0.1", 9999))
        print("UDP socket has a configured peer.")
        print("This does not mean a handshake occurred.")
    finally:
        client.close()


# =============================================================================
# 12. TIMEOUTS
# =============================================================================

def demonstrate_timeout() -> None:
    print("\n" + "=" * 78)
    print("UDP TIMEOUTS")
    print("=" * 78)

    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(0.05)

    try:
        start = time.monotonic()

        try:
            receiver.recvfrom(1024)
        except socket.timeout:
            elapsed = time.monotonic() - start
            print(f"No datagram arrived within approximately {elapsed:.3f}s.")
            print(
                "Application-level timeouts are essential when waiting for "
                "responses over an unreliable network."
            )
    finally:
        receiver.close()


# =============================================================================
# 13. CONCURRENT UDP SERVER
# =============================================================================

class ThreadedUdpEchoServer:
    """
    Small concurrent UDP echo server.

    Each received datagram is processed by a worker thread. This is useful for
    illustrating application architecture, but uncontrolled thread creation is
    not appropriate for every production workload.
    """

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.address = self.socket.getsockname()
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _serve(self) -> None:
        while self.running:
            try:
                data, client_address = self.socket.recvfrom(65535)
            except OSError:
                break

            worker = threading.Thread(
                target=self._handle,
                args=(data, client_address),
                daemon=True,
            )
            worker.start()

    def _handle(self, data: bytes, client_address: Tuple[str, int]) -> None:
        try:
            self.socket.sendto(b"echo:" + data, client_address)
        except OSError:
            pass

    def stop(self) -> None:
        self.running = False
        self.socket.close()


def demonstrate_concurrent_server() -> None:
    print("\n" + "=" * 78)
    print("CONCURRENT UDP SERVER")
    print("=" * 78)

    server = ThreadedUdpEchoServer()
    server.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        client.sendto(b"concurrent hello", server.address)
        client.settimeout(1.0)
        response, _ = client.recvfrom(1024)
        print(f"Response: {response.decode()}")
    finally:
        client.close()
        server.stop()


# =============================================================================
# 14. APPLICATION-LEVEL MESSAGE FORMAT
# =============================================================================

@dataclass
class ApplicationMessage:
    """
    A simple length-prefixed application protocol.

    UDP supplies the transport datagram. The application defines the meaning
    of the bytes inside it.
    """

    message_type: int
    request_id: int
    body: bytes

    def encode(self) -> bytes:
        if not 0 <= self.message_type <= 255:
            raise ValueError("message_type must fit in one byte.")

        if not 0 <= self.request_id <= 0xFFFFFFFF:
            raise ValueError("request_id must fit in four bytes.")

        if len(self.body) > 65535:
            raise ValueError("Body is too large for this example protocol.")

        return (
            struct.pack("!BIH", self.message_type, self.request_id, len(self.body))
            + self.body
        )

    @staticmethod
    def decode(data: bytes) -> "ApplicationMessage":
        header_size = 7

        if len(data) < header_size:
            raise ValueError("Application message is too short.")

        message_type, request_id, body_length = struct.unpack(
            "!BIH",
            data[:header_size],
        )

        body = data[header_size:]

        if len(body) != body_length:
            raise ValueError(
                f"Length mismatch: header says {body_length}, "
                f"received {len(body)}."
            )

        return ApplicationMessage(
            message_type=message_type,
            request_id=request_id,
            body=body,
        )


def demonstrate_application_protocol() -> None:
    print("\n" + "=" * 78)
    print("APPLICATION-LEVEL PROTOCOL")
    print("=" * 78)

    message = ApplicationMessage(
        message_type=1,
        request_id=1001,
        body=b"temperature=24.5",
    )

    encoded = message.encode()
    decoded = ApplicationMessage.decode(encoded)

    print(f"Encoded bytes: {encoded}")
    print(f"Message type:  {decoded.message_type}")
    print(f"Request ID:    {decoded.request_id}")
    print(f"Body:          {decoded.body.decode()}")


# =============================================================================
# 15. INPUT VALIDATION AND SECURITY
# =============================================================================

def validate_udp_message(data: bytes, maximum_size: int = 1200) -> bytes:
    """
    Validate application input before parsing or processing it.

    UDP is especially exposed to unsolicited traffic because a server can
    receive datagrams without maintaining a connection handshake.
    """
    if not isinstance(data, bytes):
        raise TypeError("Expected bytes.")

    if len(data) == 0:
        raise ValueError("Empty datagrams are not accepted by this application.")

    if len(data) > maximum_size:
        raise ValueError("Datagram exceeds the application size limit.")

    return data


def demonstrate_security_validation() -> None:
    print("\n" + "=" * 78)
    print("VALIDATION AND SECURITY")
    print("=" * 78)

    valid = b"safe-message"

    try:
        validated = validate_udp_message(valid)
        print(f"Accepted: {validated}")
    except (TypeError, ValueError) as error:
        print(f"Rejected: {error}")

    try:
        validate_udp_message(b"x" * 2000)
    except (TypeError, ValueError) as error:
        print(f"Large packet rejected: {error}")

    print(
        """
UDP-specific security concerns include:
  - spoofed source addresses
  - unsolicited datagrams
  - amplification and reflection attacks
  - malformed application messages
  - packet floods
  - lack of built-in encryption or authentication
  - replay attacks in application protocols

Confidentiality and authentication require mechanisms above UDP, such as a
secure protocol designed for the application.
"""
    )


# =============================================================================
# 16. FRAGMENTATION AND MTU
# =============================================================================

def explain_mtu() -> None:
    print("\n" + "=" * 78)
    print("MTU AND FRAGMENTATION")
    print("=" * 78)

    print(
        """
MTU (Maximum Transmission Unit) is the largest packet size that a network
interface or path can normally carry without fragmentation at that layer.

Large UDP datagrams can become IP fragments. Fragmentation creates additional
failure and processing risks because losing one fragment can make the complete
datagram unusable.

For latency-sensitive protocols, keeping application datagrams reasonably small
is often preferable to relying on IP fragmentation.

The exact safe payload size depends on the network path, IP version, headers,
encapsulation, and application protocol.
"""
    )


# =============================================================================
# 17. TCP VS UDP
# =============================================================================

def compare_tcp_udp() -> None:
    print("\n" + "=" * 78)
    print("TCP VS UDP")
    print("=" * 78)

    comparison = [
        ("Connection setup", "Handshake/state", "No transport handshake"),
        ("Reliability", "Built in", "Application responsibility"),
        ("Ordering", "Guaranteed byte-stream order", "Not guaranteed"),
        ("Duplicates", "Suppressed by TCP", "Possible"),
        ("Congestion control", "Built in", "Not built into UDP"),
        ("Flow control", "Built in", "Not built into UDP"),
        ("Data boundaries", "Byte stream", "Datagram boundaries"),
        ("Retransmission", "Built in", "Not built in"),
        ("Latency", "Can incur transport overhead", "Minimal transport overhead"),
        ("Broadcast", "No general TCP broadcast", "Supports IP broadcast use cases"),
        ("Multicast", "Not used as a TCP feature", "Commonly used with UDP/IP"),
    ]

    print(f"{'Property':<22} {'TCP':<30} UDP")
    print("-" * 78)

    for property_name, tcp_value, udp_value in comparison:
        print(f"{property_name:<22} {tcp_value:<30} {udp_value}")


# =============================================================================
# 18. LATENCY MODEL
# =============================================================================

def estimate_stop_and_wait_throughput(
    payload_bytes: int,
    round_trip_seconds: float,
) -> float:
    """
    Approximate stop-and-wait throughput:

        payload bits / RTT

    This is a simplified educational calculation and excludes protocol
    overhead, processing time, loss, retransmission, and other effects.
    """
    if payload_bytes < 0:
        raise ValueError("payload_bytes cannot be negative.")

    if round_trip_seconds <= 0:
        raise ValueError("round_trip_seconds must be positive.")

    return (payload_bytes * 8) / round_trip_seconds


def demonstrate_latency_tradeoff() -> None:
    print("\n" + "=" * 78)
    print("SPEED VS RELIABILITY TRADE-OFF")
    print("=" * 78)

    payload = 1200

    for rtt in (0.010, 0.050, 0.100, 0.250):
        throughput = estimate_stop_and_wait_throughput(payload, rtt)
        print(
            f"RTT={rtt * 1000:6.0f} ms -> "
            f"stop-and-wait upper approximation={throughput / 1000:8.2f} kbit/s"
        )

    print(
        """
A reliable protocol built on UDP can reduce application-level waiting by using
multiple outstanding packets rather than one packet at a time.

That introduces more complexity: windows, acknowledgements, retransmission
timers, congestion control, buffering, and packet-loss recovery.
"""
    )


# =============================================================================
# 19. SELECTIVE ACKNOWLEDGEMENT MODEL
# =============================================================================

class SelectiveAcknowledgementReceiver:
    """
    Receiver model that stores out-of-order packets and exposes the contiguous
    portion of the sequence space that can be delivered to the application.
    """

    def __init__(self):
        self.next_expected = 1
        self.buffer: Dict[int, bytes] = {}

    def receive(self, packet: ReliablePacket) -> List[bytes]:
        if packet.sequence_number < self.next_expected:
            # Duplicate or stale packet.
            return []

        if packet.sequence_number not in self.buffer:
            self.buffer[packet.sequence_number] = packet.payload

        delivered: List[bytes] = []

        while self.next_expected in self.buffer:
            delivered.append(self.buffer.pop(self.next_expected))
            self.next_expected += 1

        return delivered


def demonstrate_selective_acknowledgement() -> None:
    print("\n" + "=" * 78)
    print("OUT-OF-ORDER BUFFERING")
    print("=" * 78)

    receiver = SelectiveAcknowledgementReceiver()

    packets = [
        ReliablePacket(1, b"A"),
        ReliablePacket(3, b"C"),
        ReliablePacket(2, b"B"),
    ]

    for packet in packets:
        delivered = receiver.receive(packet)
        print(
            f"Received sequence {packet.sequence_number}; "
            f"delivered now={delivered}"
        )

    print(f"Next expected sequence: {receiver.next_expected}")


# =============================================================================
# 20. IDEMPOTENCY
# =============================================================================

class IdempotentRequestProcessor:
    """
    Demonstrates a common UDP application technique.

    If a request can be retransmitted, the server should be able to recognize
    duplicate request IDs and avoid performing a non-idempotent operation twice.
    """

    def __init__(self):
        self.processed: Dict[int, str] = {}

    def process(self, request_id: int, operation: str) -> str:
        if request_id in self.processed:
            return self.processed[request_id]

        result = f"executed:{operation}"
        self.processed[request_id] = result
        return result


def demonstrate_idempotency() -> None:
    print("\n" + "=" * 78)
    print("DUPLICATE REQUEST HANDLING")
    print("=" * 78)

    processor = IdempotentRequestProcessor()

    print(processor.process(101, "charge-account"))
    print(processor.process(101, "charge-account"))

    print(
        "The second request ID produces the stored result instead of executing "
        "the operation again."
    )


# =============================================================================
# 21. BROADCAST AND MULTICAST CONCEPTS
# =============================================================================

def demonstrate_broadcast_configuration() -> None:
    print("\n" + "=" * 78)
    print("BROADCAST CONFIGURATION")
    print("=" * 78)

    socket_object = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        # SO_BROADCAST permits an application to send to an IPv4 broadcast
        # address. Actual delivery depends on the network.
        socket_object.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        print("SO_BROADCAST enabled successfully.")
    finally:
        socket_object.close()

    print(
        """
UDP is commonly associated with broadcast and multicast applications because
these communication models do not map naturally onto one TCP byte-stream
connection.

Examples include service discovery, local network announcements, live media,
and telemetry distribution.
"""
    )


# =============================================================================
# 22. TESTING
# =============================================================================

def test_reliable_packet_round_trip() -> None:
    packet = ReliablePacket(123, b"testing")
    decoded = ReliablePacket.decode(packet.encode())

    assert decoded.sequence_number == 123
    assert decoded.payload == b"testing"


def test_application_message_round_trip() -> None:
    message = ApplicationMessage(2, 9001, b"hello")
    decoded = ApplicationMessage.decode(message.encode())

    assert decoded.message_type == 2
    assert decoded.request_id == 9001
    assert decoded.body == b"hello"


def test_invalid_application_message() -> None:
    try:
        ApplicationMessage.decode(b"\x01\x00\x00\x00\x01\x00")
    except ValueError:
        return

    raise AssertionError("Malformed application message should be rejected.")


def run_tests() -> None:
    print("\n" + "=" * 78)
    print("SELF-TESTS")
    print("=" * 78)

    test_reliable_packet_round_trip()
    test_application_message_round_trip()
    test_invalid_application_message()

    print("All tests passed.")


# =============================================================================
# 23. PRODUCTION DESIGN CHECKLIST
# =============================================================================

def print_production_checklist() -> None:
    print("\n" + "=" * 78)
    print("UDP PRODUCTION DESIGN CHECKLIST")
    print("=" * 78)

    checklist = [
        "Define the application message format.",
        "Validate every received datagram.",
        "Set sensible receive and send buffer limits.",
        "Choose a practical maximum datagram size.",
        "Use sequence numbers when ordering or loss detection matters.",
        "Use request IDs when duplicate detection matters.",
        "Use acknowledgements when delivery confirmation matters.",
        "Use retransmission timers when retransmission matters.",
        "Avoid uncontrolled retransmission storms.",
        "Implement congestion-aware behavior for protocols that require it.",
        "Authenticate sensitive messages.",
        "Encrypt confidential application data.",
        "Protect against replay when messages have security consequences.",
        "Rate-limit expensive operations.",
        "Handle malformed packets without crashing.",
        "Instrument packet loss, latency, jitter, and retransmissions.",
        "Design explicit behavior for peer timeout and restart.",
        "Test loss, duplication, reordering, delay, and corruption.",
    ]

    for item in checklist:
        print(f"[ ] {item}")


# =============================================================================
# 24. MAIN
# =============================================================================

def main() -> None:
    explain_fundamentals()
    demonstrate_udp_header()
    basic_udp_server()
    basic_udp_exchange()
    demonstrate_datagram_semantics()
    demonstrate_receive_buffer()
    demonstrate_unreliability()
    demonstrate_sequence_numbers()
    demonstrate_reliability_model()
    demonstrate_stop_and_wait()
    demonstrate_checksum()
    demonstrate_udp_connect()
    demonstrate_timeout()
    demonstrate_concurrent_server()
    demonstrate_application_protocol()
    demonstrate_security_validation()
    explain_mtu()
    compare_tcp_udp()
    demonstrate_latency_tradeoff()
    demonstrate_selective_acknowledgement()
    demonstrate_idempotency()
    demonstrate_broadcast_configuration()
    run_tests()
    print_production_checklist()

    print("\n" + "=" * 78)
    print("END OF UDP STUDY PROGRAM")
    print("=" * 78)


if __name__ == "__main__":
    main()
