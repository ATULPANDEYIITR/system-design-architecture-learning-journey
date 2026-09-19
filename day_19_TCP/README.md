# TCP: Connections, Handshake, Reliability, and Retransmission

## Introduction

Transmission Control Protocol (TCP) is a transport-layer protocol designed to provide reliable, ordered, connection-oriented communication between applications. TCP operates above IP and below application protocols such as HTTP, HTTPS, SSH, SMTP, and many database protocols.

TCP presents applications with a continuous byte stream. The application writes bytes to a socket, and TCP divides those bytes into segments for transmission. The receiving TCP implementation reconstructs the ordered byte stream before exposing it to the receiving application.

The central reliability mechanisms demonstrated in this repository are sequence numbers, acknowledgments, retransmission, timers, receive windows, congestion windows, duplicate acknowledgments, and connection state management.

The three implementations intentionally emphasize different aspects:

- Python provides detailed educational models of TCP mechanisms and a real socket interface.
- JavaScript demonstrates TCP through Node.js's event-driven networking model.
- C++ develops an industry-style reliable-transfer case study using explicit data structures, state models, validation, buffering, and performance considerations.

The simulations model TCP concepts for learning. They are not replacements for the operating system's production TCP implementation.

## TCP at the transport layer

A typical communication stack can be viewed as:

Application  
↓  
TCP  
↓  
IP  
↓  
Link/network technology

An application normally does not manipulate TCP sequence numbers or retransmission timers directly. The operating system's TCP implementation performs these operations.

For example, an HTTPS application normally uses:

Application protocol: HTTP  
Security: TLS  
Transport: TCP  
Network: IP

TCP is responsible for transport semantics. TLS provides cryptographic protection above TCP.

## Fundamental terminology

### Endpoint

An endpoint is identified by an IP address and a transport-layer port.

A TCP connection is commonly described by four values:

`source IP + source port + destination IP + destination port`

The complete connection state also includes protocol state, sequence-number state, windows, timers, and other information.

### Port

A port identifies an application endpoint within a host.

Well-known services commonly use ports such as 80 for HTTP and 443 for HTTPS, although applications can use arbitrary available ports.

### Segment

TCP transfers information in segments. A segment contains a TCP header and, when applicable, application data.

Important TCP header fields include:

- Source port
- Destination port
- Sequence number
- Acknowledgment number
- Data offset
- Flags
- Receive window
- Checksum
- Urgent pointer
- Optional TCP options

### Sequence number

TCP treats application data as an ordered sequence of bytes.

If a segment begins at sequence number `1000` and contains 500 bytes, its data occupies sequence space from `1000` through `1499`.

The next byte has sequence number `1500`.

SYN and FIN consume one sequence-number position even though they do not contain ordinary application data.

### Acknowledgment number

TCP acknowledgments normally use cumulative semantics.

An acknowledgment number identifies the next sequence number the receiver expects.

If the receiver has successfully received bytes through sequence number `1499`, it can send:

`ACK = 1500`

This means that the receiver has received the contiguous byte stream through the byte immediately preceding 1500.

### SYN

SYN means synchronize. It is used during connection establishment to synchronize sequence-number state.

### ACK

ACK indicates that the acknowledgment field is valid and is used to confirm received sequence space.

### FIN

FIN requests orderly shutdown of one direction of a TCP connection.

TCP is full-duplex, so the two directions can be closed independently.

### RST

RST resets a TCP connection abruptly. It is associated with situations where a connection cannot or should not continue normally.

## Connection establishment

TCP normally establishes a connection through a three-way handshake.

The basic sequence is:

`Client -> Server: SYN`

`Server -> Client: SYN + ACK`

`Client -> Server: ACK`

The first SYN communicates the client's initial sequence number.

The SYN+ACK acknowledges the client's SYN and communicates the server's initial sequence number.

The final ACK acknowledges the server's SYN.

### Why three messages?

Both endpoints need to establish synchronized sequence-number state and confirm that the other endpoint can communicate in both directions.

A simplified example is:

`Client SYN SEQ=10000`

`Server SYN+ACK SEQ=50000 ACK=10001`

`Client ACK SEQ=10001 ACK=50001`

The Python, JavaScript, and C++ implementations model this process explicitly.

## Initial sequence numbers

TCP uses initial sequence numbers when establishing a connection. Modern TCP implementations use mechanisms designed to make sequence-number prediction difficult.

The exact generation algorithm is an implementation and protocol-detail concern rather than an application concern.

Applications should not assume that TCP sequence numbers begin at zero or follow a predictable fixed pattern.

## TCP state machine

TCP maintains connection state.

Important states include:

- `CLOSED`
- `LISTEN`
- `SYN-SENT`
- `SYN-RECEIVED`
- `ESTABLISHED`
- `FIN-WAIT-1`
- `FIN-WAIT-2`
- `CLOSE-WAIT`
- `LAST-ACK`
- `TIME-WAIT`

A server normally enters `LISTEN` and waits for connection attempts.

A client performing an active open commonly enters `SYN-SENT`.

After successful establishment, both sides enter `ESTABLISHED`.

The Python and C++ implementations represent important TCP states explicitly.

## Reliable byte-stream delivery

TCP reliability has several related properties.

### Ordered delivery

If application data is transmitted as:

`A B C D`

the receiving application receives the corresponding byte sequence in order.

TCP does not normally expose data to the application in an arbitrary order simply because network packets arrived out of order.

### Duplicate suppression

The network may duplicate packets or a sender may retransmit data that the receiver has already received.

TCP uses sequence numbers to identify duplicate or already acknowledged data.

### Loss recovery

IP networks do not guarantee delivery.

A TCP segment can be lost because of congestion, transmission errors, routing changes, queue overflow, or other network conditions.

TCP detects loss using mechanisms including retransmission timers and duplicate acknowledgments.

## Retransmission

Retransmission means sending data again after TCP determines that the previous transmission was not successfully acknowledged.

A simplified process is:

1. Sender transmits segment.
2. Sender starts or associates the segment with a retransmission timer.
3. Receiver receives the segment.
4. Receiver sends an acknowledgment.
5. Sender receives the acknowledgment and considers the data acknowledged.

If the expected acknowledgment does not arrive within the relevant retransmission interval, TCP may retransmit.

Retransmission is one of the fundamental mechanisms that converts an unreliable packet-delivery environment into a reliable transport abstraction.

## Retransmission timeout

A retransmission timeout must balance two competing risks.

If the timeout is too short, the sender can retransmit data unnecessarily when the network is simply slow.

If the timeout is too long, genuine packet loss can cause excessive recovery delay.

TCP therefore uses measured round-trip behavior to estimate appropriate retransmission timing.

The educational RTT estimator in the three implementations uses the conceptual relationships:

`SRTT = smoothed round-trip time`

`RTTVAR = estimated RTT variation`

`RTO = SRTT + 4 × RTTVAR`

Production TCP implementations apply protocol-specific rules, limits, timer behavior, and additional details.

## RTT measurement

RTT means round-trip time.

Conceptually:

`RTT = time acknowledgment is received - time segment was transmitted`

RTT varies because of:

- Network distance
- Queueing
- Routing changes
- Congestion
- Wireless conditions
- Server processing behavior
- Network scheduling

A single RTT sample should therefore not automatically become a permanent timeout value.

The Python, JavaScript, and C++ examples show smoothed RTT estimation.

## Exponential backoff

After a retransmission timeout, repeatedly retransmitting at the same interval can increase congestion.

A simplified educational model therefore doubles the timeout after successive timeout events:

`1 s -> 2 s -> 4 s -> 8 s`

Production TCP behavior contains additional rules and limits.

The important concept is that repeated timeout events should not cause increasingly aggressive retransmission behavior.

## Duplicate acknowledgments

Suppose a receiver has received:

`1000-1099`

but segment `1100-1199` is lost.

If segment beginning at `1200` arrives, the receiver cannot acknowledge the missing range as though the byte stream were complete.

It can continue acknowledging the first missing sequence number.

Repeated acknowledgments for the same sequence position are called duplicate ACKs.

Duplicate ACK patterns can provide evidence that a segment was lost even before the retransmission timer expires.

## Fast retransmission

A sender can use multiple duplicate ACKs as a signal of probable loss.

Fast retransmission allows a sender to retransmit suspected missing data without necessarily waiting for the full retransmission timeout.

This is particularly useful because waiting for an RTO can be much slower than reacting to several duplicate ACKs.

The exact duplicate-ACK threshold and recovery behavior depend on TCP algorithms and implementation details.

## Selective acknowledgment

Selective Acknowledgment (SACK) extends TCP's ability to communicate which blocks of data have already arrived.

Without selective information, cumulative ACKs primarily identify the next missing sequence position.

With SACK information, the receiver can communicate additional received ranges.

This can make loss recovery more efficient when several segments are missing or arrive out of order.

The simulations in this repository primarily use cumulative acknowledgment behavior to make the fundamental mechanism clear.

## Sliding windows

TCP does not normally operate as a pure stop-and-wait protocol.

A sender can have multiple segments outstanding before receiving acknowledgments for all of them.

This is represented by a transmission window.

For example, if the current send base is 1000 and the effective window permits four units of outstanding data, the sender can transmit multiple segments before waiting for every individual acknowledgment.

When acknowledgments advance the window, additional data can be transmitted.

The Python, JavaScript, and C++ implementations contain simplified sliding-window models.

## Flow control

Flow control protects the receiver.

The receiver has finite memory for buffering incoming data. It advertises a receive window, commonly referred to as `rwnd`.

Conceptually:

`rwnd = amount of additional data the receiver can accept`

A sender should not overwhelm the receiver's advertised capacity.

A receiver can advertise a very small window or even a zero window when it cannot currently accept additional data.

## Congestion control

Congestion control protects the network rather than the receiving application.

A network path can contain routers, switches, queues, links, and other traffic sources.

Sending faster than the path can handle can cause queue growth and packet loss.

TCP therefore maintains congestion-control state.

A common conceptual variable is the congestion window:

`cwnd`

A simplified effective sending limitation can be expressed as:

`effective window = min(rwnd, cwnd)`

The receiver window addresses receiver capacity.

The congestion window addresses network capacity.

These mechanisms solve different problems.

## Slow start

Slow start increases the congestion window rapidly when a connection begins or when congestion recovery requires a substantial reduction.

The name can be misleading because the growth can be rapid.

The C++ and Python implementations include simplified educational congestion-control models.

## Congestion avoidance

After reaching an appropriate threshold, TCP congestion-control algorithms generally increase the congestion window more conservatively.

A simplified model uses approximately additive growth rather than the more rapid initial growth associated with slow start.

Actual TCP algorithms vary significantly.

## Timeout versus duplicate-ACK loss signals

A timeout is generally a stronger congestion signal than a few duplicate ACKs.

A simplified distinction is:

- Duplicate ACK signal: probable isolated loss, enabling faster recovery.
- Retransmission timeout: acknowledgment did not arrive within the estimated interval.

TCP congestion-control behavior reacts to these conditions according to the selected congestion-control algorithm.

## TCP checksum

TCP includes a checksum for detecting corruption.

The checksum calculation is based on one's-complement arithmetic.

A real TCP checksum includes a pseudo-header containing information from the IP layer as well as the TCP header and data.

The Python implementation demonstrates the core Internet checksum calculation.

A checksum is an integrity-detection mechanism. It is not cryptographic authentication.

An attacker capable of modifying traffic may require stronger security mechanisms.

## TCP does not provide encryption

TCP provides reliable transport semantics but does not inherently provide confidentiality.

For secure application communication, encryption and authentication are normally provided by a higher-layer protocol such as TLS.

For example:

`HTTP over TCP`

provides transport reliability but no encryption.

`HTTPS = HTTP over TLS over TCP`

adds cryptographic protection.

## Connection termination

TCP is full-duplex.

Each direction has an independent stream, so orderly shutdown commonly involves a sequence resembling:

`FIN -> ACK -> FIN -> ACK`

A side sending FIN indicates that it will not send additional application data in that direction.

It can still receive data from the peer until the peer also closes its direction.

## TIME-WAIT

The endpoint performing the active close can enter `TIME-WAIT`.

TIME-WAIT has important protocol purposes.

It allows delayed segments from the old connection to expire before the same connection-identifying information is reused.

It also allows retransmission of the final acknowledgment when necessary.

TIME-WAIT therefore has protocol significance and should not simply be regarded as an unnecessary delay.

## TCP byte-stream semantics

One of the most important application-level TCP concepts is that TCP is a byte stream.

Suppose an application performs:

`send("HELLO")`

followed by:

`send("WORLD")`

The receiver is not guaranteed to observe two corresponding `recv()` operations.

It could receive:

`HELLOWORLD`

or:

`HEL`

then:

`LOWOR`

then:

`LD`

or another segmentation.

The application protocol must therefore define message boundaries when messages have discrete meanings.

## Application framing

The implementations use a four-byte length prefix.

Conceptually:

`[4-byte length][payload]`

For example:

`[length=5][HELLO]`

The receiver accumulates bytes until the complete frame is available.

This pattern handles arbitrary TCP read boundaries.

Other framing approaches include:

- Delimiter-based messages
- Fixed-size records
- Length-prefixed records
- Structured serialization formats
- Request-response protocols

The correct framing approach depends on the application protocol.

## Python implementation

The Python script begins with fundamental TCP terminology and progressively builds educational models.

### Header representation

`TCPHeader` represents important fields such as:

- Source port
- Destination port
- Sequence number
- Acknowledgment number
- Flags
- Window size
- Checksum

The class is deliberately simplified. A production TCP header contains additional fields and options.

### Handshake model

`simulate_three_way_handshake()` creates the three conceptual handshake segments.

It demonstrates why the acknowledgment numbers advance by one for SYN.

### Sequence numbers

`demonstrate_sequence_numbers()` assigns consecutive sequence numbers to individual bytes.

This makes the distinction between application data length and TCP sequence space explicit.

### Checksum

`internet_checksum()` demonstrates the underlying one's-complement calculation.

The script also modifies a byte to demonstrate that corruption changes the checksum.

### Receiver

`TCPReceiver` models cumulative acknowledgments and out-of-order buffering.

If a later segment arrives before an earlier missing segment, the receiver buffers the later data and continues acknowledging the first missing position.

### RTT estimator

`RTTEstimator` models:

`SRTT`

`RTTVAR`

`RTO`

This demonstrates why retransmission timing should respond to measured network behavior.

### Sliding window

`SlidingWindowSender` models a sender that can have multiple sequence positions outstanding.

The send base advances when acknowledgments arrive.

### Congestion control

`CongestionController` presents a simplified model of slow start, congestion avoidance, duplicate-ACK response, and timeout response.

It is intentionally not a complete production TCP congestion-control implementation.

### Real TCP sockets

The functions `run_tcp_echo_server()` and `run_tcp_echo_client()` use Python's standard `socket` library.

The operating system performs the actual TCP protocol work.

The Python application therefore demonstrates the distinction between:

`TCP implementation`

and:

`application-level socket API`

## JavaScript implementation

The JavaScript implementation emphasizes Node.js networking and asynchronous event handling.

### Node.js TCP server

`net.createServer()` creates a TCP server.

The operating system handles:

- Three-way handshake
- TCP sequencing
- Acknowledgment
- Retransmission
- Flow control
- Congestion control
- Connection state

Node.js exposes the resulting stream through events.

### Event-driven behavior

Important events include:

- `connect`
- `data`
- `end`
- `error`

This illustrates why JavaScript is useful for demonstrating event-driven network programming.

### TCP stream handling

The JavaScript code explicitly demonstrates that a `data` event does not represent a guaranteed application message boundary.

The framing functions accumulate bytes and extract complete messages.

### Error handling

The real TCP client handles:

- Timeout
- Connection error
- Socket closure

Production systems should also establish limits for buffers, idle connections, request sizes, and concurrent clients.

## C++ case study

The C++ program models a reliable file-transfer system.

The scenario is:

A sender must transfer a byte sequence through a network that may lose segments.

The system must detect missing acknowledgments and retransmit until the receiver reconstructs the complete original data.

### Architecture

The case study separates major concerns into classes:

- `TcpHandshake`
- `TcpReceiver`
- `RttEstimator`
- `CongestionController`
- `SlidingWindowSender`
- `ReliableFileTransfer`

This organization demonstrates modular design rather than placing all behavior inside `main()`.

### Receiver buffering

`TcpReceiver` uses `std::map` to buffer out-of-order segments.

A segment that begins at the expected sequence number is delivered immediately.

A segment that begins later is buffered.

When the missing segment arrives, contiguous buffered segments can be released.

### Reliable transfer

`ReliableFileTransfer` divides the data into segments.

The simulation randomly loses some segments.

A lost segment is retransmitted.

The transfer continues until the receiver acknowledges the entire segment.

The program finally verifies:

`received data == original data`

This creates a clear reliability invariant.

### Why this is not a TCP implementation

The case study intentionally simplifies TCP.

It does not implement every production TCP mechanism, option, timer, congestion-control algorithm, or operating-system integration.

A real TCP stack must deal with:

- Sequence-number wrapping
- Simultaneous opens
- Simultaneous closes
- Retransmission queues
- SACK
- Window scaling
- Timestamps
- Path MTU behavior
- Receive-buffer management
- Congestion-control algorithms
- Delayed acknowledgments
- Connection state transitions
- Security-related state validation
- Network-interface integration

The case study isolates the most important reliability mechanisms so their relationships are visible.

## Important distinctions

| Concept | Primary purpose |
|---|---|
| Sequence number | Identifies byte position |
| ACK | Communicates received sequence space |
| Retransmission | Recovers from suspected loss |
| RTO | Detects loss when acknowledgments do not arrive in time |
| Duplicate ACK | Provides an early loss signal |
| Receive window | Protects receiver capacity |
| Congestion window | Controls network load |
| Checksum | Detects accidental corruption |
| SYN | Establishes sequence-number state |
| FIN | Performs orderly shutdown |
| RST | Aborts or resets connection state |
| TIME-WAIT | Protects connection reuse and final-ACK reliability |
| TLS | Provides cryptographic protection above TCP |
| Application framing | Restores message boundaries above a byte stream |

## TCP versus UDP

TCP and UDP solve different transport problems.

| Property | TCP | UDP |
|---|---|---|
| Connection-oriented | Yes | No |
| Ordered byte stream | Yes | No |
| Built-in retransmission | Yes | No |
| Cumulative acknowledgment | Yes | No |
| Flow control | Yes | No |
| Congestion-control behavior | Yes | Not provided by UDP itself |
| Message boundaries | Not preserved | Preserved |
| Connection handshake | Yes | No TCP-style handshake |
| Typical abstraction | Reliable stream | Datagram delivery |

UDP can be appropriate when an application needs datagrams, very low protocol overhead, or application-specific reliability and timing behavior.

TCP is appropriate when an application benefits from a reliable ordered byte stream.

## Common mistakes

### Assuming send and receive operations correspond one-to-one

A TCP write does not define an application message boundary.

The receiver must use framing.

### Assuming recv returns the requested number of bytes

A receive call may return fewer bytes than requested.

Applications that require a complete frame must continue reading until the complete frame is available.

### Assuming TCP guarantees application processing

An acknowledgment is a transport-layer event.

It does not mean that the receiving application has completed business processing.

### Assuming TCP is encrypted

TCP does not provide encryption.

TLS or another cryptographic protocol is required when confidentiality and authentication are needed.

### Confusing flow control and congestion control

Receive-window control protects the receiver.

Congestion control protects the network.

### Using arbitrary retransmission timeouts

A fixed timeout that ignores network latency and variation can create unnecessary retransmissions or slow loss recovery.

### Ignoring partial writes

Low-level socket APIs can return fewer bytes than an application attempted to send.

Python's `sendall()` and Node.js stream handling simplify common cases, but developers must still understand the underlying behavior.

### Ignoring connection closure

An orderly TCP shutdown must be distinguished from a reset, timeout, or other failure.

## Edge cases

Important TCP edge cases include:

- Segment loss
- Duplicate segments
- Out-of-order segments
- Duplicate acknowledgments
- Retransmission timeout
- Zero receive window
- Very small receive window
- Simultaneous connection attempts
- Simultaneous close
- Half-closed connections
- Connection reset
- Delayed packets
- Delayed acknowledgments
- Long-lived idle connections
- Rapid connection reuse
- TIME-WAIT accumulation
- Sequence-number wraparound
- Large receive buffers
- Very high-latency paths
- Congested paths
- Network path changes

A production implementation must account for these conditions rather than assuming an ideal network.

## Exceptions and failure handling

At the application level, TCP failures can appear as:

- Connection refused
- Connection reset
- Timeout
- Broken pipe
- End-of-stream
- Local resource exhaustion
- Address or port errors

The precise error representation depends on the programming language and operating system.

The Python implementation demonstrates exception-oriented socket handling concepts.

The JavaScript implementation uses promise rejection and socket error events.

The C++ case study uses exceptions for invalid configuration and violated reliability invariants.

## Performance considerations

TCP performance depends on multiple variables rather than a single bandwidth value.

Important factors include:

- RTT
- Bandwidth
- Packet loss
- Congestion window
- Receive window
- Maximum Segment Size
- Network path characteristics
- Buffer sizes
- Retransmission rate
- Delayed acknowledgments
- Connection setup cost
- Application write patterns

### Bandwidth-delay product

The bandwidth-delay product approximates the amount of data that can be in flight on a path:

`BDP = bandwidth × RTT`

High-bandwidth, high-latency paths can require substantial amounts of outstanding data to fully utilize the available capacity.

### Small writes

Applications that repeatedly write tiny chunks can create inefficient traffic patterns.

Nagle's algorithm can combine small writes under suitable circumstances.

Latency-sensitive applications sometimes use `TCP_NODELAY`, but disabling Nagle's algorithm should be based on workload requirements rather than used automatically.

### Retransmission cost

Retransmissions consume additional bandwidth and can increase latency.

High retransmission rates may indicate:

- Network congestion
- Weak wireless conditions
- Faulty links
- Overly aggressive timing
- Routing problems
- Other network instability

## Security considerations

TCP does not authenticate application identities and does not encrypt application payloads.

Security-sensitive applications should consider:

- TLS
- Certificate validation
- Application authentication
- Authorization
- Connection limits
- Idle-connection timeouts
- Maximum message sizes
- Maximum frame sizes
- Rate limiting
- Resource accounting
- Firewall policy

### SYN floods

TCP connection establishment requires server-side resources.

An attacker can send many SYN packets and attempt to exhaust those resources.

SYN cookies and other infrastructure-level techniques can reduce exposure to SYN-flood attacks.

### Frame-length validation

Length-prefixed application protocols must validate lengths before allocating memory.

The C++ and JavaScript implementations enforce maximum frame sizes.

A malicious peer could otherwise advertise an extremely large frame length and cause excessive memory allocation.

## Implementation considerations

### Python

Python provides concise data structures and makes protocol modeling easy to inspect.

The standard `socket` module provides access to real TCP sockets.

The educational classes should not be confused with Python's actual TCP implementation, which resides below the socket API.

### JavaScript

Node.js exposes TCP through the `net` module.

The event-driven architecture is useful for servers handling many concurrent network connections without creating a dedicated blocking application thread for every connection.

The application must still handle stream buffering and backpressure appropriately.

### C++

C++ provides explicit control over data structures, memory ownership, performance, and system-level integration.

The C++ case study uses standard-library containers such as `std::map` and `std::vector` while maintaining explicit protocol state.

## Production considerations

A production TCP application should not attempt to manually implement TCP inside the application when the operating system already provides a mature TCP stack.

Instead, application developers generally need to design:

- Connection lifecycle management
- Application framing
- Request and response semantics
- Timeouts
- Retries at the correct protocol layer
- Authentication
- Authorization
- TLS configuration
- Buffer limits
- Concurrency limits
- Logging
- Metrics
- Graceful shutdown
- Error recovery
- Backpressure
- Resource cleanup

The transport layer should be treated as a reliable byte-stream service rather than as a message queue.

## Real-world applications

TCP is widely used by application protocols that require reliable ordered transport.

Examples include:

- HTTP
- HTTPS
- SSH
- SMTP
- IMAP
- POP3
- FTP
- Many database protocols
- Many internal service-to-service protocols

The application chooses TCP when reliable ordered delivery is valuable.

## Practical relationship between the three implementations

The Python implementation emphasizes protocol concepts and simulations.

The JavaScript implementation emphasizes how a real application consumes TCP through an asynchronous socket API.

The C++ implementation emphasizes architecture, state, data structures, reliability invariants, validation, and performance considerations.

Together they show three different levels of understanding:

`Protocol mechanism`

`Application socket behavior`

`Systems-oriented implementation design`

The operating system remains responsible for the actual production TCP protocol machinery when these programs use normal TCP sockets.

## Key protocol relationships

The most important relationships can be expressed as:

`SYN -> connection establishment`

`SEQ -> byte identification`

`ACK -> received sequence confirmation`

`RTO -> timeout-based loss detection`

`Duplicate ACKs -> early loss indication`

`Retransmission -> loss recovery`

`rwnd -> receiver protection`

`cwnd -> network congestion control`

`FIN -> orderly shutdown`

`TIME-WAIT -> safe connection termination and reuse`

`TLS -> cryptographic protection above TCP`

`Application framing -> message boundaries above TCP`

These mechanisms work together to make TCP substantially more than a simple packet-forwarding protocol.
