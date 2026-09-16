/*
 * TCP/IP Model: Network Stack and Practical Communication
 * ========================================================
 *
 * Self-contained JavaScript demonstrations using Node.js built-in modules.
 *
 * Topics:
 * - TCP/IP model
 * - Sockets and ports
 * - TCP and UDP
 * - DNS
 * - IPv4 and IPv6
 * - TCP byte-stream semantics
 * - Application-level framing
 * - HTTP
 * - Event-driven networking
 * - Concurrent clients
 * - Timeouts
 * - Validation
 * - Protocol design
 * - Performance
 * - Security
 * - Troubleshooting
 *
 * Run with:
 *     node tcp_ip.js
 */

"use strict";

const net = require("node:net");
const dgram = require("node:dgram");
const dns = require("node:dns");
const crypto = require("node:crypto");
const os = require("node:os");


function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}


function subsection(title) {
    console.log("\n" + "-".repeat(78));
    console.log(title);
    console.log("-".repeat(78));
}


// ============================================================================
// 1. TCP/IP model
// ============================================================================

function demonstrateModel() {
    section("1. TCP/IP model");

    const layers = [
        {
            layer: "Application",
            examples: "HTTP, HTTPS, DNS, SSH, SMTP",
            responsibility: "Application-level communication and data representation"
        },
        {
            layer: "Transport",
            examples: "TCP, UDP",
            responsibility: "Ports and end-to-end transport semantics"
        },
        {
            layer: "Internet",
            examples: "IPv4, IPv6, ICMP",
            responsibility: "Logical addressing and packet forwarding"
        },
        {
            layer: "Link / Network Access",
            examples: "Ethernet, Wi-Fi",
            responsibility: "Local-network frame delivery"
        }
    ];

    console.table(layers);

    console.log(
        "The stack hides lower-level implementation details from higher layers. " +
        "An HTTP application normally does not construct Ethernet frames itself."
    );
}


// ============================================================================
// 2. Encapsulation
// ============================================================================

function demonstrateEncapsulation() {
    section("2. Encapsulation and decapsulation");

    const applicationData = Buffer.from("GET / HTTP/1.1\\r\\n\\r\\n");

    const tcpSegment = Buffer.concat([
        Buffer.from("[TCP HEADER]"),
        applicationData
    ]);

    const ipPacket = Buffer.concat([
        Buffer.from("[IP HEADER]"),
        tcpSegment
    ]);

    const ethernetFrame = Buffer.concat([
        Buffer.from("[ETHERNET HEADER]"),
        ipPacket
    ]);

    console.log("Application:", applicationData.toString());
    console.log("TCP segment:", tcpSegment.toString());
    console.log("IP packet:", ipPacket.toString());
    console.log("Link frame:", ethernetFrame.toString());
}


// ============================================================================
// 3. TCP and UDP comparison
// ============================================================================

function demonstrateTcpUdpComparison() {
    section("3. TCP versus UDP");

    const comparison = [
        ["Connection", "Connection-oriented", "Connectionless"],
        ["Reliability", "Reliable byte stream", "Best-effort datagrams"],
        ["Ordering", "Ordered", "Not guaranteed"],
        ["Message boundaries", "Not preserved", "Preserved"],
        ["Retransmission", "Built into TCP", "Application must handle it"],
        ["Flow control", "Yes", "No TCP-style flow control"],
        ["Congestion control", "Yes", "Not inherent"],
        ["Typical uses", "HTTP, HTTPS, SSH", "DNS, real-time/custom protocols"]
    ];

    console.table(
        comparison.map(([property, tcp, udp]) => ({ property, tcp, udp }))
    );
}


// ============================================================================
// 4. Address and port concepts
// ============================================================================

function demonstrateAddresses() {
    section("4. Addresses and ports");

    console.log("Loopback IPv4:", "127.0.0.1");
    console.log("IPv4 private example:", "192.168.1.20");
    console.log("IPv6 documentation example:", "2001:db8::20");
    console.log("HTTP:", 80);
    console.log("HTTPS:", 443);
    console.log("SSH:", 22);

    console.log(
        "\nAn endpoint can be thought of as an address plus a transport port. " +
        "The transport protocol determines how the port is interpreted."
    );
}


// ============================================================================
// 5. DNS
// ============================================================================

function resolveHostname(hostname) {
    return new Promise((resolve, reject) => {
        dns.lookup(hostname, { all: true }, (error, addresses) => {
            if (error) {
                reject(error);
                return;
            }

            resolve(addresses);
        });
    });
}


async function demonstrateDns() {
    section("5. DNS resolution");

    try {
        const addresses = await resolveHostname("localhost");
        console.table(addresses);
    } catch (error) {
        console.log("DNS lookup failed:", error.code || error.message);
    }

    console.log(
        "DNS allows applications to use names instead of hard-coding " +
        "destination IP addresses."
    );
}


// ============================================================================
// 6. HTTP request structure
// ============================================================================

function demonstrateHttp() {
    section("6. HTTP over TCP");

    const request = [
        "GET / HTTP/1.1",
        "Host: example.test",
        "Connection: close",
        "",
        ""
    ].join("\r\n");

    console.log(request);

    console.log(
        "\nConceptual stack:\n" +
        "HTTP -> TLS when HTTPS is used -> TCP -> IP -> Ethernet/Wi-Fi"
    );
}


// ============================================================================
// 7. TCP framing
// ============================================================================

function encodeLengthPrefixedMessage(message) {
    const payload = Buffer.from(message, "utf8");

    if (payload.length > 10_000_000) {
        throw new RangeError("Message exceeds the protocol size limit.");
    }

    const header = Buffer.alloc(4);
    header.writeUInt32BE(payload.length, 0);

    return Buffer.concat([header, payload]);
}


class LengthPrefixedDecoder {
    constructor(maxPayload = 10_000_000) {
        this.maxPayload = maxPayload;
        this.buffer = Buffer.alloc(0);
    }

    push(chunk) {
        this.buffer = Buffer.concat([this.buffer, chunk]);
        const messages = [];

        while (this.buffer.length >= 4) {
            const length = this.buffer.readUInt32BE(0);

            if (length > this.maxPayload) {
                throw new Error("Peer advertised an excessive payload.");
            }

            if (this.buffer.length < 4 + length) {
                break;
            }

            const payload = this.buffer.subarray(4, 4 + length);
            messages.push(payload.toString("utf8"));

            this.buffer = this.buffer.subarray(4 + length);
        }

        return messages;
    }
}


function demonstrateFraming() {
    section("7. TCP application-level framing");

    const first = encodeLengthPrefixedMessage("first");
    const second = encodeLengthPrefixedMessage("second");

    // TCP gives the application a stream. A decoder therefore may receive
    // arbitrary chunks that contain partial or multiple application messages.
    const decoder = new LengthPrefixedDecoder();

    const combined = Buffer.concat([first, second]);

    const firstChunk = combined.subarray(0, 3);
    const secondChunk = combined.subarray(3);

    console.log("Messages after partial first chunk:", decoder.push(firstChunk));
    console.log("Messages after remaining bytes:", decoder.push(secondChunk));

    console.log(
        "Length-prefix framing creates application message boundaries " +
        "without changing TCP itself."
    );
}


// ============================================================================
// 8. TCP server
// ============================================================================

function startTcpEchoServer() {
    return new Promise((resolve, reject) => {
        const server = net.createServer((socket) => {
            socket.setTimeout(5000);

            socket.on("data", (data) => {
                socket.write(Buffer.concat([
                    Buffer.from("ACK: "),
                    data
                ]));
            });

            socket.on("timeout", () => {
                socket.end();
            });

            socket.on("error", () => {
                // A production server would record structured diagnostics.
            });
        });

        server.once("error", reject);

        // Bind to loopback instead of all network interfaces for this
        // educational demonstration.
        server.listen(0, "127.0.0.1", () => {
            const address = server.address();

            resolve({
                server,
                port: address.port
            });
        });
    });
}


function runTcpClient(port) {
    return new Promise((resolve, reject) => {
        const socket = net.createConnection({
            host: "127.0.0.1",
            port,
            timeout: 3000
        });

        const received = [];

        socket.on("connect", () => {
            socket.write("Hello from Node.js TCP client");
        });

        socket.on("data", (data) => {
            received.push(data);
            socket.end();
        });

        socket.on("timeout", () => {
            socket.destroy(new Error("TCP client timeout."));
        });

        socket.on("error", reject);

        socket.on("close", () => {
            resolve(Buffer.concat(received).toString("utf8"));
        });
    });
}


async function demonstrateTcp() {
    section("8. Practical TCP communication");

    const { server, port } = await startTcpEchoServer();

    try {
        const response = await runTcpClient(port);
        console.log("TCP client received:", response);
    } finally {
        await new Promise((resolve) => server.close(resolve));
    }
}


// ============================================================================
// 9. Concurrent TCP clients
// ============================================================================

function runTcpClientWithMessage(port, message) {
    return new Promise((resolve, reject) => {
        const socket = net.createConnection({
            host: "127.0.0.1",
            port,
            timeout: 3000
        });

        const chunks = [];

        socket.on("connect", () => {
            socket.write(message);
        });

        socket.on("data", (data) => {
            chunks.push(data);
            socket.end();
        });

        socket.on("timeout", () => {
            socket.destroy(new Error("Client timeout."));
        });

        socket.on("error", reject);

        socket.on("close", () => {
            resolve(Buffer.concat(chunks).toString("utf8"));
        });
    });
}


async function demonstrateConcurrentTcp() {
    section("9. Multiple simultaneous TCP connections");

    const { server, port } = await startTcpEchoServer();

    try {
        // Node's event loop allows many I/O operations to be in flight without
        // requiring one operating-system thread per connection.
        const messages = [
            "client-1",
            "client-2",
            "client-3",
            "client-4"
        ];

        const responses = await Promise.all(
            messages.map((message) => runTcpClientWithMessage(port, message))
        );

        console.log(responses);
    } finally {
        await new Promise((resolve) => server.close(resolve));
    }
}


// ============================================================================
// 10. UDP
// ============================================================================

function runUdpDemo() {
    return new Promise((resolve, reject) => {
        const server = dgram.createSocket("udp4");
        const client = dgram.createSocket("udp4");

        server.once("error", (error) => {
            server.close();
            client.close();
            reject(error);
        });

        server.on("message", (message, remoteInfo) => {
            console.log("UDP server received:", message.toString());
            console.log("Remote address:", remoteInfo.address);

            server.send(
                Buffer.from("UDP response"),
                remoteInfo.port,
                remoteInfo.address
            );
        });

        client.on("message", (message) => {
            console.log("UDP client received:", message.toString());
            client.close();
            server.close(resolve);
        });

        server.bind(0, "127.0.0.1", () => {
            const address = server.address();

            client.send(
                Buffer.from("Hello through UDP"),
                address.port,
                "127.0.0.1"
            );
        });
    });
}


async function demonstrateUdp() {
    section("10. Practical UDP communication");

    await runUdpDemo();

    console.log(
        "UDP preserves datagram boundaries, but delivery, ordering, and " +
        "duplicate suppression are not provided by UDP itself."
    );
}


// ============================================================================
// 11. IPv4 header concepts
// ============================================================================

function demonstrateIpv4HeaderFields() {
    section("11. IPv4 packet structure");

    const fields = [
        ["Version", "IPv4 uses version 4"],
        ["IHL", "IPv4 header length"],
        ["DSCP/ECN", "Traffic handling and congestion notification fields"],
        ["Total Length", "Header plus payload length"],
        ["Identification", "Used in fragmentation-related processing"],
        ["Flags", "Fragmentation control"],
        ["Fragment Offset", "Fragment position"],
        ["TTL", "Limits packet lifetime across routers"],
        ["Protocol", "Identifies next protocol such as TCP or UDP"],
        ["Header Checksum", "Detects accidental header corruption"],
        ["Source Address", "Origin IPv4 address"],
        ["Destination Address", "Target IPv4 address"]
    ];

    console.table(
        fields.map(([field, purpose]) => ({ field, purpose }))
    );
}


// ============================================================================
// 12. TCP header concepts
// ============================================================================

function demonstrateTcpHeader() {
    section("12. TCP segment structure");

    const fields = [
        ["Source Port", "Origin application endpoint"],
        ["Destination Port", "Target application endpoint"],
        ["Sequence Number", "Position of transmitted data in the stream"],
        ["Acknowledgment Number", "Next byte expected when ACK is valid"],
        ["Data Offset", "TCP header length"],
        ["Flags", "SYN, ACK, FIN, RST and other control signals"],
        ["Window", "Receiver-advertised flow-control window"],
        ["Checksum", "TCP integrity check"],
        ["Urgent Pointer", "Legacy urgent-data mechanism"],
        ["Options", "Capabilities such as timestamps and negotiated parameters"]
    ];

    console.table(
        fields.map(([field, purpose]) => ({ field, purpose }))
    );

    console.log(
        "TCP sequence and acknowledgment numbers support ordered, reliable " +
        "delivery rather than treating each packet as an independent message."
    );
}


// ============================================================================
// 13. TCP handshake
// ============================================================================

function demonstrateHandshake() {
    section("13. TCP three-way handshake");

    console.log("1. Client -> SYN -> Server");
    console.log("2. Client <- SYN + ACK <- Server");
    console.log("3. Client -> ACK -> Server");

    console.log(
        "\nThe handshake synchronizes initial sequence-number state and " +
        "establishes the transport connection."
    );
}


// ============================================================================
// 14. TCP termination
// ============================================================================

function demonstrateTermination() {
    section("14. TCP connection termination");

    console.log("A simplified graceful shutdown can involve:");
    console.log("1. One side sends FIN.");
    console.log("2. The peer acknowledges the FIN.");
    console.log("3. The peer later sends its own FIN.");
    console.log("4. The original side acknowledges it.");

    console.log(
        "TCP has states such as FIN-WAIT, CLOSE-WAIT, LAST-ACK, and TIME-WAIT."
    );
}


// ============================================================================
// 15. Routing
// ============================================================================

function demonstrateRouting() {
    section("15. Routing");

    const routingExample = [
        {
            destination: "192.168.1.0/24",
            nextHop: "local interface",
            reason: "Most specific local route"
        },
        {
            destination: "10.0.0.0/8",
            nextHop: "internal router",
            reason: "Private network route"
        },
        {
            destination: "0.0.0.0/0",
            nextHop: "default gateway",
            reason: "Fallback route"
        }
    ];

    console.table(routingExample);

    console.log(
        "Routers generally use longest-prefix matching to select the most " +
        "specific route that matches a destination address."
    );
}


// ============================================================================
// 16. ARP
// ============================================================================

function demonstrateArp() {
    section("16. ARP and local network delivery");

    console.log("IPv4 destination: 192.168.1.20");
    console.log("Local host asks: Who has 192.168.1.20?");
    console.log("Target responds with its MAC address.");
    console.log("The sender can then construct the local Ethernet frame.");

    console.log(
        "If the destination is remote, the local host normally resolves " +
        "the MAC address of the next-hop router instead."
    );
}


// ============================================================================
// 17. IPv4 and IPv6
// ============================================================================

function demonstrateIpVersions() {
    section("17. IPv4 and IPv6");

    console.log("IPv4 address length: 32 bits");
    console.log("IPv6 address length: 128 bits");
    console.log("IPv4 example: 192.0.2.10");
    console.log("IPv6 example: 2001:db8::10");

    console.log(
        "Node's networking APIs can use IPv4 and IPv6 depending on the " +
        "address family and operating-system configuration."
    );
}


// ============================================================================
// 18. Application validation
// ============================================================================

function validateUsername(username) {
    if (typeof username !== "string") {
        return false;
    }

    if (username.length === 0 || username.length > 64) {
        return false;
    }

    return /^[A-Za-z0-9_-]+$/.test(username);
}


function demonstrateValidation() {
    section("18. Application-layer validation");

    const values = [
        "alice",
        "alice_123",
        "bad user",
        "",
        "x".repeat(65),
        null
    ];

    for (const value of values) {
        console.log(JSON.stringify(value), "=>", validateUsername(value));
    }

    console.log(
        "TCP provides transport semantics. It does not validate the meaning " +
        "or safety of application data."
    );
}


// ============================================================================
// 19. JSON protocol
// ============================================================================

function demonstrateJsonProtocol() {
    section("19. JSON at the application layer");

    const message = {
        version: 1,
        type: "measurement",
        sender: "sensor-17",
        value: 23.5,
        unit: "C"
    };

    const encoded = Buffer.from(JSON.stringify(message), "utf8");

    console.log("JSON bytes:", encoded);
    console.log("Decoded:", JSON.parse(encoded.toString("utf8")));

    console.log(
        "TCP transports these bytes without understanding their JSON meaning."
    );
}


// ============================================================================
// 20. Cryptographic integrity
// ============================================================================

function demonstrateCryptographicHash() {
    section("20. Transport checksums and cryptographic hashes");

    const payload = Buffer.from("important network message");

    const digest = crypto
        .createHash("sha256")
        .update(payload)
        .digest("hex");

    console.log("SHA-256:", digest);

    console.log(
        "A cryptographic hash is useful for integrity-related applications, " +
        "but a plain hash does not authenticate who created the message."
    );
}


// ============================================================================
// 21. TLS concepts
// ============================================================================

function demonstrateTlsConcepts() {
    section("21. TLS and HTTPS");

    console.log("HTTP over TCP:");
    console.log("HTTP -> TCP -> IP -> Link");

    console.log("\nHTTPS:");
    console.log("HTTP -> TLS -> TCP -> IP -> Link");

    console.log(
        "\nTLS can provide confidentiality, integrity, and server authentication " +
        "when correctly configured and certificate validation is performed."
    );
}


// ============================================================================
// 22. TCP stream semantics
// ============================================================================

function demonstrateStreamSemantics() {
    section("22. TCP is a byte stream");

    console.log("Application sends:");
    console.log("  MESSAGE-A");
    console.log("  MESSAGE-B");
    console.log("  MESSAGE-C");

    console.log("\nThe receiver might observe:");
    console.log("  MESSAGE-");
    console.log("  AMESSAGE-BMES");
    console.log("  SAGE-C");

    console.log(
        "\nThe bytes remain ordered, but send/write calls are not message " +
        "boundaries. Application framing is therefore important."
    );
}


// ============================================================================
// 23. Performance
// ============================================================================

function demonstratePerformance() {
    section("23. Performance considerations");

    const considerations = [
        "Round-trip time",
        "Available bandwidth",
        "Packet loss",
        "Congestion",
        "Socket buffers",
        "Serialization/deserialization",
        "System-call overhead",
        "Concurrent connection count",
        "CPU usage",
        "Memory per connection"
    ];

    for (const item of considerations) {
        console.log("-", item);
    }

    console.log(
        "\nLatency and bandwidth are different properties. Reducing the number " +
        "of sequential round trips can matter more than increasing payload size."
    );
}


// ============================================================================
// 24. Node.js operating-system network information
// ============================================================================

function demonstrateLocalInterfaces() {
    section("24. Local network interfaces");

    const interfaces = os.networkInterfaces();

    for (const [name, addresses] of Object.entries(interfaces)) {
        console.log(`Interface: ${name}`);

        for (const address of addresses || []) {
            console.log(
                `  family=${address.family} address=${address.address} ` +
                `internal=${address.internal}`
            );
        }
    }
}


// ============================================================================
// 25. Failure handling
// ============================================================================

async function demonstrateFailureHandling() {
    section("25. Failure handling");

    try {
        await runTcpClient(1);
    } catch (error) {
        console.log(
            "Handled connection failure:",
            error.code || error.message
        );
    }

    console.log(
        "Network programs should explicitly handle refusal, timeout, reset, " +
        "DNS failure, malformed data, peer disconnects, and resource exhaustion."
    );
}


// ============================================================================
// 26. Mini application protocol
// ============================================================================

class MiniProtocol {
    static VERSION = 1;
    static MAX_PAYLOAD = 1_000_000;

    static encode(type, body) {
        if (typeof type !== "string" || type.length === 0) {
            throw new TypeError("Protocol type must be a non-empty string.");
        }

        const document = {
            version: MiniProtocol.VERSION,
            type,
            body
        };

        const payload = Buffer.from(
            JSON.stringify(document),
            "utf8"
        );

        if (payload.length > MiniProtocol.MAX_PAYLOAD) {
            throw new RangeError("Protocol payload is too large.");
        }

        const length = Buffer.alloc(4);
        length.writeUInt32BE(payload.length, 0);

        return Buffer.concat([length, payload]);
    }

    static decode(packet) {
        if (!Buffer.isBuffer(packet) || packet.length < 4) {
            throw new TypeError("Packet is too short.");
        }

        const declaredLength = packet.readUInt32BE(0);

        if (declaredLength > MiniProtocol.MAX_PAYLOAD) {
            throw new RangeError("Declared payload is too large.");
        }

        if (packet.length !== declaredLength + 4) {
            throw new Error("Framing length does not match packet size.");
        }

        const document = JSON.parse(
            packet.subarray(4).toString("utf8")
        );

        if (document.version !== MiniProtocol.VERSION) {
            throw new Error("Unsupported protocol version.");
        }

        return document;
    }
}


function demonstrateMiniProtocol() {
    section("26. Application protocol design");

    const packet = MiniProtocol.encode(
        "measurement",
        {
            sender: "sensor-17",
            temperature: 21.75,
            unit: "C"
        }
    );

    console.log("Encoded:", packet);
    console.log("Decoded:", MiniProtocol.decode(packet));
}


// ============================================================================
// 27. Security
// ============================================================================

function demonstrateSecurity() {
    section("27. Network security considerations");

    const principles = [
        "Do not trust data merely because TCP delivered it.",
        "Validate all lengths before processing payloads.",
        "Set connection and operation timeouts.",
        "Use TLS for sensitive data in transit.",
        "Validate TLS certificates and hostnames.",
        "Authenticate users at the application layer.",
        "Apply authorization independently of authentication.",
        "Avoid exposing development services on public interfaces.",
        "Limit resource usage per client.",
        "Avoid logging passwords, tokens, or private keys.",
        "Handle malformed protocol messages safely.",
        "Use rate limiting where appropriate."
    ];

    principles.forEach((principle) => console.log("-", principle));
}


// ============================================================================
// 28. Troubleshooting
// ============================================================================

function demonstrateTroubleshooting() {
    section("28. Troubleshooting workflow");

    const steps = [
        "Confirm the application configuration.",
        "Resolve the hostname.",
        "Check the destination IP address.",
        "Inspect routing.",
        "Check whether the target port is listening.",
        "Check local and remote firewall rules.",
        "Check connection refusal versus timeout.",
        "Inspect application protocol messages.",
        "Measure latency and throughput.",
        "Capture packets when deeper diagnosis is necessary."
    ];

    steps.forEach((step, index) => {
        console.log(`${index + 1}. ${step}`);
    });
}


// ============================================================================
// 29. OSI comparison
// ============================================================================

function demonstrateOsiComparison() {
    section("29. TCP/IP and OSI comparison");

    console.table([
        {
            tcpIp: "Application",
            osi: "Application + Presentation + Session"
        },
        {
            tcpIp: "Transport",
            osi: "Transport"
        },
        {
            tcpIp: "Internet",
            osi: "Network"
        },
        {
            tcpIp: "Link",
            osi: "Data Link + Physical"
        }
    ]);

    console.log(
        "The models are abstractions. Protocol boundaries do not always align " +
        "perfectly with theoretical layers."
    );
}


// ============================================================================
// 30. Complete web communication workflow
// ============================================================================

function demonstrateCompleteWorkflow() {
    section("30. Practical web communication workflow");

    const workflow = [
        "Browser parses an HTTPS URL.",
        "DNS resolves the hostname.",
        "The operating system chooses a route.",
        "TCP connects to port 443.",
        "TLS authenticates the server and negotiates cryptographic protection.",
        "HTTP request bytes are generated.",
        "TCP carries the byte stream.",
        "IP routes packets through intermediate networks.",
        "Link-layer protocols deliver each local hop.",
        "The server reverses the process.",
        "The HTTP response returns through the stack.",
        "The browser interprets the response."
    ];

    workflow.forEach((step, index) => {
        console.log(`${index + 1}. ${step}`);
    });
}


// ============================================================================
// 31. Main
// ============================================================================

async function main() {
    demonstrateModel();
    demonstrateEncapsulation();
    demonstrateTcpUdpComparison();
    demonstrateAddresses();
    await demonstrateDns();
    demonstrateHttp();
    demonstrateFraming();
    await demonstrateTcp();
    await demonstrateConcurrentTcp();
    await demonstrateUdp();
    demonstrateIpv4HeaderFields();
    demonstrateTcpHeader();
    demonstrateHandshake();
    demonstrateTermination();
    demonstrateRouting();
    demonstrateArp();
    demonstrateIpVersions();
    demonstrateValidation();
    demonstrateJsonProtocol();
    demonstrateCryptographicHash();
    demonstrateTlsConcepts();
    demonstrateStreamSemantics();
    demonstratePerformance();
    demonstrateLocalInterfaces();
    await demonstrateFailureHandling();
    demonstrateMiniProtocol();
    demonstrateSecurity();
    demonstrateTroubleshooting();
    demonstrateOsiComparison();
    demonstrateCompleteWorkflow();

    section("End of JavaScript TCP/IP demonstration");
    console.log(
        "The program demonstrated application, transport, Internet, and " +
        "link-layer concepts through Node.js networking APIs."
    );
}


main().catch((error) => {
    console.error("Fatal demonstration error:", error);
    process.exitCode = 1;
});
