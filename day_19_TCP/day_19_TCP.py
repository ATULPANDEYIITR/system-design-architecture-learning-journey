#!/usr/bin/env python3
"""
TCP: Connections, Handshake, Reliability, and Retransmission

A self-contained study and demonstration program covering:
- TCP terminology and architecture
- Connection establishment
- The three-way handshake
- Sequence and acknowledgment numbers
- Reliable byte-stream delivery
- Checksums
- Retransmission
- Timeout and retransmission timer concepts
- Duplicate data and duplicate ACKs
- Fast retransmission
- Sliding windows
- Flow control
- Congestion-control concepts
- Connection termination
- TIME-WAIT
- TCP state-machine concepts
- Common failure cases
- Security considerations
- A realistic reliable-transfer simulation

The examples use Python's standard library only.
Real socket examples are included as functions and can be run locally.
The main program runs deterministic simulations without requiring a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
import socket
import struct
import time
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. Fundamental terminology
# ---------------------------------------------------------------------------

def explain_fundamentals() -> None:
    print("\n=== TCP FUNDAMENTALS ===")
    concepts = {
        "TCP": "Transmission Control Protocol, a connection-oriented transport protocol.",
        "Endpoint": "An IP address and transport-layer port identifying an application endpoint.",
        "Connection": "A logical transport relationship between two TCP endpoints.",
        "Byte stream": "TCP exposes ordered bytes rather than preserving application message boundaries.",
        "Sequence number": "Identifies the position of transmitted bytes in the TCP byte stream.",
        "ACK": "Acknowledgment indicating the next sequence number the receiver expects.",
        "SYN": "TCP flag used during connection establishment.",
        "ACK flag": "TCP flag indicating that the acknowledgment field is valid.",
        "FIN": "TCP flag used to request orderly shutdown of one direction of a connection.",
        "RST": "TCP flag used to abruptly reset a connection.",
        "Window": "Amount of data a receiver can currently accept, used for flow control.",
        "Retransmission": "Sending data again because delivery was not confirmed in time or loss was inferred.",
    }

    for name, meaning in concepts.items():
        print(f"{name:18} : {meaning}")


# ---------------------------------------------------------------------------
# 2. TCP header model
# ---------------------------------------------------------------------------

@dataclass
class TCPHeader:
    source_port: int
    destination_port: int
    sequence_number: int
    acknowledgment_number: int
    flags: str
    window_size: int
    checksum: int = 0
    urgent_pointer: int = 0

    def describe(self) -> str:
        return (
            f"{self.source_port} -> {self.destination_port}, "
            f"SEQ={self.sequence_number}, ACK={self.acknowledgment_number}, "
            f"FLAGS={self.flags}, WINDOW={self.window_size}, "
            f"CHECKSUM=0x{self.checksum:04x}"
        )


def demonstrate_header() -> None:
    print("\n=== TCP HEADER MODEL ===")
    header = TCPHeader(
        source_port=50000,
        destination_port=443,
        sequence_number=1000,
        acknowledgment_number=2001,
        flags="ACK",
        window_size=65535,
    )
    print(header.describe())


# ---------------------------------------------------------------------------
# 3. Three-way handshake
# ---------------------------------------------------------------------------

@dataclass
class HandshakeSegment:
    sender: str
    receiver: str
    syn: bool = False
    ack: bool = False
    fin: bool = False
    sequence_number: int = 0
    acknowledgment_number: int = 0

    def describe(self) -> str:
        flags = []
        if self.syn:
            flags.append("SYN")
        if self.ack:
            flags.append("ACK")
        if self.fin:
            flags.append("FIN")
        return (
            f"{self.sender} -> {self.receiver}: "
            f"{'+'.join(flags) or 'NONE'} "
            f"SEQ={self.sequence_number} ACK={self.acknowledgment_number}"
        )


def simulate_three_way_handshake(
    client_isn: int = 10000,
    server_isn: int = 50000,
) -> List[HandshakeSegment]:
    """
    SYN and FIN each consume one sequence-number position even though
    they do not carry application data.
    """
    first = HandshakeSegment(
        sender="Client",
        receiver="Server",
        syn=True,
        sequence_number=client_isn,
    )

    second = HandshakeSegment(
        sender="Server",
        receiver="Client",
        syn=True,
        ack=True,
        sequence_number=server_isn,
        acknowledgment_number=client_isn + 1,
    )

    third = HandshakeSegment(
        sender="Client",
        receiver="Server",
        ack=True,
        sequence_number=client_isn + 1,
        acknowledgment_number=server_isn + 1,
    )

    return [first, second, third]


def demonstrate_handshake() -> None:
    print("\n=== THREE-WAY HANDSHAKE ===")
    for segment in simulate_three_way_handshake():
        print(segment.describe())

    print("Meaning:")
    print("1. Client sends SYN with its initial sequence number.")
    print("2. Server sends SYN+ACK acknowledging the client's SYN and announcing its own ISN.")
    print("3. Client sends ACK acknowledging the server's SYN.")
    print("The connection can then carry application data.")


# ---------------------------------------------------------------------------
# 4. Sequence numbers and cumulative acknowledgments
# ---------------------------------------------------------------------------

def demonstrate_sequence_numbers() -> None:
    print("\n=== SEQUENCE NUMBERS AND ACKNOWLEDGMENTS ===")

    start_sequence = 1000
    payload = b"HELLOWORLD"

    print(f"Payload: {payload!r}")
    print(f"Starting sequence number: {start_sequence}")

    for offset, byte in enumerate(payload):
        sequence = start_sequence + offset
        print(f"byte={chr(byte)!r} SEQ={sequence}")

    next_expected = start_sequence + len(payload)
    print(f"Cumulative ACK after all bytes: {next_expected}")
    print(
        "An ACK of the next expected byte allows TCP to acknowledge a contiguous "
        "prefix of the byte stream."
    )


# ---------------------------------------------------------------------------
# 5. Checksum demonstration
# ---------------------------------------------------------------------------

def internet_checksum(data: bytes) -> int:
    """
    Implements the one's-complement Internet checksum calculation used by
    IP-family protocols, including TCP.

    A real TCP checksum also covers a pseudo-header containing source IP,
    destination IP, protocol number, and TCP length. This function demonstrates
    the core one's-complement calculation only.
    """
    if len(data) % 2:
        data += b"\x00"

    total = 0
    for index in range(0, len(data), 2):
        word = (data[index] << 8) | data[index + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)

    return (~total) & 0xFFFF


def demonstrate_checksum() -> None:
    print("\n=== CHECKSUM ===")

    payload = b"TCP reliability"
    checksum = internet_checksum(payload)

    print(f"Data: {payload!r}")
    print(f"Checksum: 0x{checksum:04x}")

    corrupted = bytearray(payload)
    corrupted[0] ^= 0x01

    print(f"Corrupted data: {bytes(corrupted)!r}")
    print(
        "A changed payload produces a different checksum, allowing corrupted "
        "segments to be rejected."
    )


# ---------------------------------------------------------------------------
# 6. Segment model
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    sequence_number: int
    payload: bytes
    acknowledgment_number: Optional[int] = None
    retransmission: bool = False
    delivered: bool = False

    @property
    def end_sequence(self) -> int:
        return self.sequence_number + len(self.payload)

    def __str__(self) -> str:
        return (
            f"SEG(seq={self.sequence_number}, "
            f"len={len(self.payload)}, "
            f"end={self.end_sequence}, "
            f"retransmission={self.retransmission})"
        )


# ---------------------------------------------------------------------------
# 7. Receiver with cumulative ACK behavior
# ---------------------------------------------------------------------------

@dataclass
class TCPReceiver:
    expected_sequence: int
    received_data: bytearray = field(default_factory=bytearray)
    out_of_order: Dict[int, bytes] = field(default_factory=dict)

    def receive(self, segment: Segment) -> int:
        """
        Simplified cumulative-ACK receiver.

        In real TCP, receiver behavior around out-of-order data, SACK,
        duplicate segments, and buffering is more sophisticated.
        """
        if segment.sequence_number < self.expected_sequence:
            # Already received or partially overlapping data.
            return self.expected_sequence

        if segment.sequence_number == self.expected_sequence:
            self.received_data.extend(segment.payload)
            self.expected_sequence += len(segment.payload)

            # Deliver previously buffered contiguous segments.
            while self.expected_sequence in self.out_of_order:
                data = self.out_of_order.pop(self.expected_sequence)
                self.received_data.extend(data)
                self.expected_sequence += len(data)

            return self.expected_sequence

        # Gap detected. Buffer out-of-order data.
        self.out_of_order.setdefault(segment.sequence_number, segment.payload)
        return self.expected_sequence


def demonstrate_receiver() -> None:
    print("\n=== CUMULATIVE ACK AND OUT-OF-ORDER DATA ===")

    receiver = TCPReceiver(expected_sequence=1000)

    segments = [
        Segment(1000, b"ABC"),
        Segment(1006, b"GHI"),
        Segment(1003, b"DEF"),
    ]

    for segment in segments:
        ack = receiver.receive(segment)
        print(f"{segment} -> ACK={ack}")

    print(f"Reconstructed stream: {bytes(receiver.received_data)!r}")


# ---------------------------------------------------------------------------
# 8. Retransmission timer simulation
# ---------------------------------------------------------------------------

@dataclass
class OutstandingSegment:
    segment: Segment
    sent_at: float
    retransmission_count: int = 0


class RetransmissionTimer:
    """
    Educational model of an RTO-based timer.

    Production TCP uses carefully defined RTT measurement and RTO algorithms,
    including smoothing and variance. This class intentionally exposes the
    underlying concept rather than implementing every kernel-specific detail.
    """

    def __init__(self, initial_rto: float = 1.0):
        if initial_rto <= 0:
            raise ValueError("RTO must be positive.")
        self.rto = initial_rto

    def expired(self, sent_at: float, now: float) -> bool:
        return now - sent_at >= self.rto

    def backoff(self) -> None:
        # Exponential backoff is commonly used after retransmission timeout.
        self.rto = min(self.rto * 2, 60.0)


def demonstrate_timeout() -> None:
    print("\n=== RETRANSMISSION TIMEOUT ===")

    timer = RetransmissionTimer(initial_rto=1.0)
    sent_at = 10.0

    for now in [10.4, 10.9, 11.0, 11.2]:
        print(f"time={now:.1f}, expired={timer.expired(sent_at, now)}")

    timer.backoff()
    print(f"RTO after exponential backoff: {timer.rto:.1f}s")


# ---------------------------------------------------------------------------
# 9. RTT and RTO estimation
# ---------------------------------------------------------------------------

@dataclass
class RTTEstimator:
    """
    Simplified RFC-style RTT estimator.

    SRTT = smoothed RTT
    RTTVAR = RTT variation estimate
    RTO = SRTT + 4 * RTTVAR

    The first measurement initializes the estimator.
    """
    srtt: Optional[float] = None
    rttvar: Optional[float] = None
    rto: Optional[float] = None

    def update(self, measured_rtt: float) -> None:
        if measured_rtt <= 0:
            raise ValueError("RTT must be positive.")

        if self.srtt is None:
            self.srtt = measured_rtt
            self.rttvar = measured_rtt / 2
        else:
            assert self.rttvar is not None
            assert self.srtt is not None

            alpha = 1 / 8
            beta = 1 / 4

            self.rttvar = (1 - beta) * self.rttvar + beta * abs(
                self.srtt - measured_rtt
            )
            self.srtt = (1 - alpha) * self.srtt + alpha * measured_rtt

        assert self.rttvar is not None
        assert self.srtt is not None

        self.rto = self.srtt + 4 * self.rttvar


def demonstrate_rtt_estimation() -> None:
    print("\n=== RTT AND RTO ESTIMATION ===")

    estimator = RTTEstimator()

    for sample in [0.100, 0.120, 0.090, 0.200, 0.150]:
        estimator.update(sample)
        print(
            f"sample={sample:.3f}s "
            f"SRTT={estimator.srtt:.3f}s "
            f"RTTVAR={estimator.rttvar:.3f}s "
            f"RTO={estimator.rto:.3f}s"
        )

    print(
        "The timeout should account for both typical latency and latency variation; "
        "an excessively short RTO causes unnecessary retransmissions."
    )


# ---------------------------------------------------------------------------
# 10. Duplicate ACK and fast retransmission simulation
# ---------------------------------------------------------------------------

def simulate_loss_and_duplicate_acks() -> None:
    print("\n=== LOSS, DUPLICATE ACKS, AND FAST RETRANSMISSION ===")

    receiver = TCPReceiver(expected_sequence=1000)

    segments = [
        Segment(1000, b"AAA"),
        Segment(1003, b"BBB"),
        Segment(1006, b"CCC"),
        Segment(1009, b"DDD"),
    ]

    lost_sequence = 1003

    for segment in segments:
        if segment.sequence_number == lost_sequence:
            print(f"Network: LOST {segment}")
            continue

        ack = receiver.receive(segment)
        print(f"Network: delivered {segment} -> receiver ACK={ack}")

    print(
        "Segments arriving beyond the missing byte range cause duplicate ACKs "
        "for the first missing sequence number."
    )
    print(
        "After enough duplicate ACKs, a sender may perform fast retransmission "
        "without waiting for the retransmission timer."
    )


# ---------------------------------------------------------------------------
# 11. Sliding-window model
# ---------------------------------------------------------------------------

@dataclass
class SlidingWindowSender:
    base: int
    next_sequence: int
    window_size: int

    def can_send(self) -> bool:
        return self.next_sequence < self.base + self.window_size

    def send(self) -> int:
        if not self.can_send():
            raise RuntimeError("Send window is full.")

        sequence = self.next_sequence
        self.next_sequence += 1
        return sequence

    def acknowledge(self, acknowledgment: int) -> None:
        if acknowledgment < self.base:
            return

        if acknowledgment > self.next_sequence:
            raise ValueError("ACK cannot exceed the highest sequence sent.")

        self.base = acknowledgment


def demonstrate_sliding_window() -> None:
    print("\n=== SLIDING WINDOW ===")

    sender = SlidingWindowSender(base=1000, next_sequence=1000, window_size=4)

    for _ in range(4):
        print(f"Sent sequence {sender.send()}")

    print(f"Can send more? {sender.can_send()}")

    sender.acknowledge(1002)

    print(f"After ACK=1002, base={sender.base}")
    print(f"Can send more? {sender.can_send()}")
    print(f"New sequence sent: {sender.send()}")


# ---------------------------------------------------------------------------
# 12. Flow control versus congestion control
# ---------------------------------------------------------------------------

def explain_flow_vs_congestion() -> None:
    print("\n=== FLOW CONTROL VS CONGESTION CONTROL ===")
    print("Flow control:")
    print("  Protects the receiver from receiving more data than its buffer can handle.")
    print("  Receiver advertises a receive window (rwnd).")
    print()
    print("Congestion control:")
    print("  Protects the network from excessive traffic.")
    print("  Sender maintains a congestion window (cwnd).")
    print()
    print("Effective sending allowance is conceptually constrained by:")
    print("  min(rwnd, cwnd)")
    print()
    print("Zero-window situations may require persist behavior so a connection can")
    print("discover when the receiver becomes able to accept data again.")


# ---------------------------------------------------------------------------
# 13. Simplified congestion-control model
# ---------------------------------------------------------------------------

class CongestionController:
    """
    Educational Reno-like model.

    It illustrates:
    - slow start
    - congestion avoidance
    - multiplicative decrease after loss
    - fast-recovery concepts at a simplified level

    Real TCP implementations use much more sophisticated algorithms.
    """

    def __init__(self, initial_cwnd: float = 1.0, initial_ssthresh: float = 16.0):
        self.cwnd = initial_cwnd
        self.ssthresh = initial_ssthresh

    def acknowledge(self) -> None:
        if self.cwnd < self.ssthresh:
            self.cwnd += 1
        else:
            self.cwnd += 1 / max(self.cwnd, 1)

    def timeout(self) -> None:
        self.ssthresh = max(self.cwnd / 2, 2)
        self.cwnd = 1

    def triple_duplicate_ack(self) -> None:
        self.ssthresh = max(self.cwnd / 2, 2)
        self.cwnd = self.ssthresh


def demonstrate_congestion_control() -> None:
    print("\n=== CONGESTION CONTROL MODEL ===")

    controller = CongestionController()

    for round_number in range(1, 9):
        controller.acknowledge()
        print(
            f"ACK round={round_number} "
            f"cwnd={controller.cwnd:.2f} "
            f"ssthresh={controller.ssthresh:.2f}"
        )

    controller.triple_duplicate_ack()
    print(
        f"After triple duplicate ACK: "
        f"cwnd={controller.cwnd:.2f}, ssthresh={controller.ssthresh:.2f}"
    )

    controller.timeout()
    print(
        f"After timeout: "
        f"cwnd={controller.cwnd:.2f}, ssthresh={controller.ssthresh:.2f}"
    )


# ---------------------------------------------------------------------------
# 14. TCP state-machine model
# ---------------------------------------------------------------------------

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
    CLOSING = "CLOSING"
    TIME_WAIT = "TIME-WAIT"


def active_open_state_sequence() -> List[TCPState]:
    return [
        TCPState.CLOSED,
        TCPState.SYN_SENT,
        TCPState.ESTABLISHED,
        TCPState.FIN_WAIT_1,
        TCPState.FIN_WAIT_2,
        TCPState.TIME_WAIT,
        TCPState.CLOSED,
    ]


def passive_open_state_sequence() -> List[TCPState]:
    return [
        TCPState.CLOSED,
        TCPState.LISTEN,
        TCPState.SYN_RECEIVED,
        TCPState.ESTABLISHED,
        TCPState.CLOSE_WAIT,
        TCPState.LAST_ACK,
        TCPState.CLOSED,
    ]


def demonstrate_states() -> None:
    print("\n=== TCP STATE MACHINE ===")

    print(
        "Active side:",
        " -> ".join(state.value for state in active_open_state_sequence()),
    )
    print(
        "Passive side:",
        " -> ".join(state.value for state in passive_open_state_sequence()),
    )

    print(
        "TIME-WAIT is important after active close. It helps prevent delayed "
        "old segments from being confused with a later connection and allows "
        "retransmission of the final ACK when required."
    )


# ---------------------------------------------------------------------------
# 15. Connection termination
# ---------------------------------------------------------------------------

def demonstrate_four_way_close() -> None:
    print("\n=== ORDERLY CONNECTION TERMINATION ===")

    events = [
        "Client -> Server: FIN",
        "Server -> Client: ACK",
        "Server -> Client: FIN",
        "Client -> Server: ACK",
    ]

    for event in events:
        print(event)

    print(
        "TCP is full-duplex, so each direction can be closed independently. "
        "This is why a normal shutdown commonly involves four control messages."
    )


# ---------------------------------------------------------------------------
# 16. Retransmission simulation
# ---------------------------------------------------------------------------

class ReliableChannelSimulator:
    """
    Deterministic stop-and-wait reliability simulation.

    This is not TCP itself. It isolates the reliability ideas TCP uses:
    sequence numbering, acknowledgment, loss detection, and retransmission.
    """

    def __init__(
        self,
        data: bytes,
        segment_size: int = 4,
        loss_probability: float = 0.25,
        seed: int = 7,
    ):
        if segment_size <= 0:
            raise ValueError("segment_size must be positive.")
        if not 0 <= loss_probability <= 1:
            raise ValueError("loss_probability must be between 0 and 1.")

        self.data = data
        self.segment_size = segment_size
        self.loss_probability = loss_probability
        self.random = random.Random(seed)
        self.receiver = TCPReceiver(expected_sequence=0)
        self.retransmissions = 0
        self.transmissions = 0

    def run(self) -> bytes:
        print("\n=== RELIABLE TRANSFER SIMULATION ===")

        segments = [
            Segment(start, self.data[start:start + self.segment_size])
            for start in range(0, len(self.data), self.segment_size)
        ]

        for original_segment in segments:
            delivered = False
            attempt = 0

            while not delivered:
                attempt += 1
                self.transmissions += 1

                segment = Segment(
                    sequence_number=original_segment.sequence_number,
                    payload=original_segment.payload,
                    retransmission=attempt > 1,
                )

                if attempt > 1:
                    self.retransmissions += 1

                lost = self.random.random() < self.loss_probability

                if lost:
                    print(f"LOSS       {segment}")
                    continue

                ack = self.receiver.receive(segment)
                print(f"DELIVERED  {segment} -> ACK={ack}")

                if ack >= original_segment.end_sequence:
                    delivered = True

        result = bytes(self.receiver.received_data)

        print(f"Original data: {self.data!r}")
        print(f"Received data: {result!r}")
        print(f"Total transmissions: {self.transmissions}")
        print(f"Retransmissions: {self.retransmissions}")

        if result != self.data:
            raise RuntimeError("Reliability simulation produced incorrect data.")

        return result


# ---------------------------------------------------------------------------
# 17. Real TCP socket server
# ---------------------------------------------------------------------------

def run_tcp_echo_server(
    host: str = "127.0.0.1",
    port: int = 0,
) -> int:
    """
    Creates a real TCP listening socket.

    The OS TCP stack handles the actual SYN/SYN-ACK/ACK handshake,
    retransmission, sequencing, checksums, congestion control, and
    acknowledgment mechanisms. Python's socket API exposes the resulting
    reliable byte stream rather than implementing TCP itself.

    This function accepts one connection and echoes one message.
    It returns the selected port. It is not called automatically because
    it blocks while waiting for a client.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(1)

        selected_port = server.getsockname()[1]
        print(f"TCP server listening on {host}:{selected_port}")

        connection, address = server.accept()

        with connection:
            print(f"Connected by {address}")
            data = connection.recv(4096)

            if data:
                connection.sendall(data)

        return selected_port


# ---------------------------------------------------------------------------
# 18. Real TCP client
# ---------------------------------------------------------------------------

def run_tcp_echo_client(
    host: str,
    port: int,
    message: bytes,
    timeout: float = 5.0,
) -> bytes:
    """
    Connects to a TCP server and sends data.

    sendall() does not mean the peer application has necessarily received
    the bytes at that instant. It means the local socket API accepted all
    bytes for transmission according to its contract.

    TCP itself handles reliable transport below the application layer.
    """
    if not message:
        raise ValueError("message must not be empty.")

    with socket.create_connection((host, port), timeout=timeout) as client:
        client.sendall(message)
        return client.recv(4096)


# ---------------------------------------------------------------------------
# 19. Important socket-level edge cases
# ---------------------------------------------------------------------------

def demonstrate_socket_edge_cases() -> None:
    print("\n=== SOCKET-LEVEL EDGE CASES ===")
    print("1. recv() may return fewer bytes than requested.")
    print("2. TCP does not preserve application message boundaries.")
    print("3. send() may accept only part of a buffer; sendall() handles repeated sends.")
    print("4. recv() returning b'' normally indicates an orderly peer shutdown.")
    print("5. Connection reset can raise ConnectionResetError.")
    print("6. Timeout can raise socket.timeout.")
    print("7. A connection can remain established while an application is idle.")
    print("8. TCP guarantees an ordered byte stream, not application-level semantics.")


# ---------------------------------------------------------------------------
# 20. Application framing over TCP
# ---------------------------------------------------------------------------

def encode_length_prefixed_message(message: bytes) -> bytes:
    """
    TCP is a byte stream. A length prefix provides application-level framing.

    Four bytes store an unsigned network-byte-order length.
    """
    if len(message) > 0xFFFFFFFF:
        raise ValueError("Message is too large for a 32-bit length prefix.")

    return struct.pack("!I", len(message)) + message


def decode_length_prefixed_messages(buffer: bytearray) -> List[bytes]:
    messages: List[bytes] = []

    while len(buffer) >= 4:
        length = struct.unpack("!I", buffer[:4])[0]

        if len(buffer) < 4 + length:
            break

        message = bytes(buffer[4:4 + length])
        del buffer[:4 + length]
        messages.append(message)

    return messages


def demonstrate_framing() -> None:
    print("\n=== APPLICATION FRAMING OVER TCP ===")

    encoded = (
        encode_length_prefixed_message(b"first")
        + encode_length_prefixed_message(b"second")
    )

    # Simulate fragmented network reads.
    receive_buffer = bytearray()
    messages: List[bytes] = []

    for chunk in [encoded[:2], encoded[2:7], encoded[7:]]:
        receive_buffer.extend(chunk)
        messages.extend(decode_length_prefixed_messages(receive_buffer))

    print(f"Decoded messages: {messages}")


# ---------------------------------------------------------------------------
# 21. Nagle's algorithm and latency considerations
# ---------------------------------------------------------------------------

def explain_performance_considerations() -> None:
    print("\n=== PERFORMANCE CONSIDERATIONS ===")
    print("Bandwidth is not the only performance variable.")
    print("Relevant factors include:")
    print("- Round-trip time (RTT)")
    print("- Congestion window")
    print("- Receive window")
    print("- Segment size and MSS")
    print("- TCP/IP header overhead")
    print("- Packet loss")
    print("- Retransmission timeout")
    print("- Delayed acknowledgments")
    print("- Nagle's algorithm")
    print("- Connection setup and teardown costs")
    print("- TLS handshake when TLS is layered over TCP")

    print(
        "\nNagle's algorithm can reduce small-packet overhead by combining small "
        "writes, but latency-sensitive applications sometimes disable it with "
        "TCP_NODELAY when appropriate."
    )


# ---------------------------------------------------------------------------
# 22. Security considerations
# ---------------------------------------------------------------------------

def explain_security() -> None:
    print("\n=== TCP SECURITY CONSIDERATIONS ===")
    print("- TCP provides reliable transport, not encryption.")
    print("- Confidentiality requires a higher-layer mechanism such as TLS.")
    print("- TCP sequence numbers and state are security-sensitive.")
    print("- SYN floods exploit the cost of partially established connections.")
    print("- SYN cookies are one mitigation technique.")
    print("- Blind spoofing and injection are harder when modern sequence-number")
    print("  randomization and appropriate network defenses are used.")
    print("- Firewalls and stateful devices track TCP connection state.")
    print("- Application authentication is still required.")
    print("- Certificate validation is required when using TLS.")
    print("- TCP does not protect an application from malformed application data.")
    print("- Resource limits should be applied to prevent connection exhaustion.")


# ---------------------------------------------------------------------------
# 23. Common mistakes
# ---------------------------------------------------------------------------

def demonstrate_common_mistakes() -> None:
    print("\n=== COMMON TCP MISTAKES ===")

    mistakes = [
        (
            "Assuming one send() equals one recv()",
            "TCP is a byte stream. Use application-level framing."
        ),
        (
            "Assuming recv(4096) always returns 4096 bytes",
            "recv() may return fewer bytes."
        ),
        (
            "Treating ACK as confirmation that the application processed data",
            "ACKs operate at the TCP transport layer."
        ),
        (
            "Assuming TCP is encrypted",
            "TCP provides reliability and transport semantics, not encryption."
        ),
        (
            "Using an arbitrary timeout without considering RTT",
            "Timeouts should account for latency and variation."
        ),
        (
            "Confusing flow control with congestion control",
            "rwnd protects the receiver; cwnd protects the network."
        ),
        (
            "Ignoring partial writes",
            "Use sendall() or explicitly handle the number of bytes sent."
        ),
        (
            "Ignoring orderly EOF",
            "A zero-length recv() generally means the peer closed its sending side."
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\nMistake: {mistake}")
        print(f"Correction: {correction}")


# ---------------------------------------------------------------------------
# 24. Integrated study demonstration
# ---------------------------------------------------------------------------

def run_all_demonstrations() -> None:
    explain_fundamentals()
    demonstrate_header()
    demonstrate_handshake()
    demonstrate_sequence_numbers()
    demonstrate_checksum()
    demonstrate_receiver()
    demonstrate_timeout()
    demonstrate_rtt_estimation()
    simulate_loss_and_duplicate_acks()
    demonstrate_sliding_window()
    explain_flow_vs_congestion()
    demonstrate_congestion_control()
    demonstrate_states()
    demonstrate_four_way_close()

    simulator = ReliableChannelSimulator(
        data=b"TCP reliability survives packet loss.",
        segment_size=6,
        loss_probability=0.30,
        seed=42,
    )
    simulator.run()

    demonstrate_socket_edge_cases()
    demonstrate_framing()
    explain_performance_considerations()
    explain_security()
    demonstrate_common_mistakes()


if __name__ == "__main__":
    run_all_demonstrations()
