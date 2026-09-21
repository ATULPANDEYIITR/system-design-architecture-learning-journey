"use strict";

/*
 * UDP (User Datagram Protocol)
 *
 * This file demonstrates UDP using only Node.js built-in modules.
 *
 * The examples progress from basic datagram communication to application-level
 * reliability, sequence numbers, acknowledgements, retransmission, validation,
 * duplicate handling, concurrency, and performance considerations.
 */

const dgram = require("node:dgram");
const crypto = require("node:crypto");


// =============================================================================
// 1. FUNDAMENTAL CONCEPTS
// =============================================================================

function explainFundamentals() {
    console.log("=".repeat(78));
    console.log("UDP FUNDAMENTALS");
    console.log("=".repeat(78));

    const concepts = {
        UDP: "User Datagram Protocol, a connectionless transport protocol.",
        Datagram: "An independent unit of data delivered to a UDP socket.",
        Connectionless:
            "UDP does not require a transport-layer connection handshake.",
        Reliability:
            "UDP does not guarantee delivery, ordering, duplicate suppression, or retransmission.",
        Port:
            "A 16-bit transport identifier used to select an application endpoint.",
        Checksum:
            "A mechanism for detecting transmission errors, not recovering from them."
    };

    for (const [name, description] of Object.entries(concepts)) {
        console.log(`${name.padEnd(16)} ${description}`);
    }

    console.log("\nUDP provides a minimal transport service.");
    console.log("Applications that need stronger guarantees must implement them");
    console.log("themselves or use a higher-level protocol.");
}


// =============================================================================
// 2. BASIC UDP SOCKET
// =============================================================================

function createUdpSocket() {
    // "udp4" creates an IPv4 UDP socket.
    return dgram.createSocket("udp4");
}

async function basicUdpExchange() {
    console.log("\n" + "=".repeat(78));
    console.log("BASIC UDP REQUEST/RESPONSE");
    console.log("=".repeat(78));

    const server = createUdpSocket();
    const client = createUdpSocket();

    await new Promise((resolve, reject) => {
        server.once("error", reject);

        server.bind(0, "127.0.0.1", () => {
            const address = server.address();

            server.once("message", (message, remote) => {
                console.log(`Server received: ${message.toString()}`);
                console.log(
                    `Client endpoint: ${remote.address}:${remote.port}`
                );

                // send() accepts a Buffer and the destination endpoint.
                server.send(
                    Buffer.from("UDP response"),
                    remote.port,
                    remote.address
                );
            });

            client.once("message", (message) => {
                console.log(`Client received: ${message.toString()}`);
                resolve();
            });

            client.send(
                Buffer.from("Hello UDP server"),
                address.port,
                address.address
            );
        });
    });

    server.close();
    client.close();
}


// =============================================================================
// 3. DATAGRAM BOUNDARIES
// =============================================================================

async function demonstrateDatagramBoundaries() {
    console.log("\n" + "=".repeat(78));
    console.log("DATAGRAM BOUNDARIES");
    console.log("=".repeat(78));

    const sender = createUdpSocket();
    const receiver = createUdpSocket();

    await new Promise((resolve, reject) => {
        receiver.once("error", reject);

        receiver.bind(0, "127.0.0.1", () => {
            const address = receiver.address();

            let count = 0;

            receiver.on("message", (message) => {
                console.log(`Received datagram ${count + 1}: ${message}`);
                count += 1;

                if (count === 2) {
                    resolve();
                }
            });

            sender.send(Buffer.from("ABC"), address.port, address.address);
            sender.send(Buffer.from("DEF"), address.port, address.address);
        });
    });

    sender.close();
    receiver.close();

    console.log(
        "\nUDP preserves datagram boundaries at the application socket API."
    );
}


// =============================================================================
// 4. MESSAGE ENCODING
// =============================================================================

function encodeApplicationMessage(type, requestId, payload) {
    if (!Number.isInteger(type) || type < 0 || type > 255) {
        throw new RangeError("type must fit into one unsigned byte.");
    }

    if (!Number.isInteger(requestId) || requestId < 0 || requestId > 0xffffffff) {
        throw new RangeError("requestId must fit into four bytes.");
    }

    if (!Buffer.isBuffer(payload)) {
        throw new TypeError("payload must be a Buffer.");
    }

    if (payload.length > 65535) {
        throw new RangeError("payload is too large for this example protocol.");
    }

    // Layout:
    // byte 0       = message type
    // bytes 1-4    = request ID
    // bytes 5-6    = payload length
    // remaining    = payload
    const packet = Buffer.alloc(7 + payload.length);

    packet.writeUInt8(type, 0);
    packet.writeUInt32BE(requestId, 1);
    packet.writeUInt16BE(payload.length, 5);
    payload.copy(packet, 7);

    return packet;
}

function decodeApplicationMessage(packet) {
    if (!Buffer.isBuffer(packet) || packet.length < 7) {
        throw new Error("Application packet is too short.");
    }

    const type = packet.readUInt8(0);
    const requestId = packet.readUInt32BE(1);
    const payloadLength = packet.readUInt16BE(5);

    if (packet.length - 7 !== payloadLength) {
        throw new Error("Application payload length does not match header.");
    }

    return {
        type,
        requestId,
        payload: packet.subarray(7)
    };
}

function demonstrateMessageEncoding() {
    console.log("\n" + "=".repeat(78));
    console.log("APPLICATION MESSAGE FORMAT");
    console.log("=".repeat(78));

    const encoded = encodeApplicationMessage(
        1,
        1001,
        Buffer.from("temperature=24.5")
    );

    const decoded = decodeApplicationMessage(encoded);

    console.log("Encoded:", encoded);
    console.log("Type:", decoded.type);
    console.log("Request ID:", decoded.requestId);
    console.log("Payload:", decoded.payload.toString());
}


// =============================================================================
// 5. SEQUENCE NUMBERS
// =============================================================================

function encodeReliablePacket(sequenceNumber, payload) {
    if (!Number.isInteger(sequenceNumber) || sequenceNumber < 0) {
        throw new RangeError("Invalid sequence number.");
    }

    if (!Buffer.isBuffer(payload)) {
        throw new TypeError("Payload must be a Buffer.");
    }

    const packet = Buffer.alloc(4 + payload.length);
    packet.writeUInt32BE(sequenceNumber >>> 0, 0);
    payload.copy(packet, 4);

    return packet;
}

function decodeReliablePacket(packet) {
    if (!Buffer.isBuffer(packet) || packet.length < 4) {
        throw new Error("Reliable packet is too short.");
    }

    return {
        sequenceNumber: packet.readUInt32BE(0),
        payload: packet.subarray(4)
    };
}

function demonstrateSequenceNumbers() {
    console.log("\n" + "=".repeat(78));
    console.log("SEQUENCE NUMBERS");
    console.log("=".repeat(78));

    const packet = encodeReliablePacket(
        42,
        Buffer.from("important data")
    );

    const decoded = decodeReliablePacket(packet);

    console.log("Sequence:", decoded.sequenceNumber);
    console.log("Payload:", decoded.payload.toString());

    console.log(
        "\nSequence numbers allow an application to identify order and duplicates."
    );
}


// =============================================================================
// 6. REQUEST IDENTIFIERS AND IDEMPOTENCY
// =============================================================================

class IdempotentRequestProcessor {
    constructor() {
        this.results = new Map();
    }

    process(requestId, operation) {
        if (!Number.isInteger(requestId) || requestId < 0) {
            throw new RangeError("Invalid request ID.");
        }

        if (this.results.has(requestId)) {
            // A retransmitted request can safely return the previous result.
            return this.results.get(requestId);
        }

        const result = `executed:${operation}`;
        this.results.set(requestId, result);

        return result;
    }
}

function demonstrateIdempotency() {
    console.log("\n" + "=".repeat(78));
    console.log("IDEMPOTENT REQUEST PROCESSING");
    console.log("=".repeat(78));

    const processor = new IdempotentRequestProcessor();

    console.log(processor.process(100, "update-record"));
    console.log(processor.process(100, "update-record"));

    console.log(
        "The duplicate request ID does not execute the operation twice."
    );
}


// =============================================================================
// 7. RETRANSMISSION MODEL
// =============================================================================

class ReliableUdpSender {
    constructor({ timeoutMs = 500, maxRetries = 3 } = {}) {
        if (timeoutMs <= 0) {
            throw new RangeError("timeoutMs must be positive.");
        }

        if (maxRetries < 0) {
            throw new RangeError("maxRetries cannot be negative.");
        }

        this.timeoutMs = timeoutMs;
        this.maxRetries = maxRetries;
        this.nextSequenceNumber = 1;
        this.pending = new Map();
    }

    createPacket(payload) {
        const sequenceNumber = this.nextSequenceNumber++;

        return {
            sequenceNumber,
            payload: Buffer.from(payload)
        };
    }

    markSent(packet) {
        this.pending.set(packet.sequenceNumber, {
            packet,
            sentAt: Date.now(),
            retries: 0
        });
    }

    acknowledge(sequenceNumber) {
        return this.pending.delete(sequenceNumber);
    }

    getRetransmissions() {
        const now = Date.now();
        const retransmissions = [];

        for (const [sequenceNumber, pending] of this.pending) {
            if (now - pending.sentAt < this.timeoutMs) {
                continue;
            }

            if (pending.retries >= this.maxRetries) {
                this.pending.delete(sequenceNumber);
                continue;
            }

            pending.retries += 1;
            pending.sentAt = now;
            retransmissions.push(pending.packet);
        }

        return retransmissions;
    }
}

async function demonstrateRetransmission() {
    console.log("\n" + "=".repeat(78));
    console.log("RETRANSMISSION");
    console.log("=".repeat(78));

    const sender = new ReliableUdpSender({
        timeoutMs: 20,
        maxRetries: 2
    });

    const packet = sender.createPacket("critical data");
    sender.markSent(packet);

    await new Promise((resolve) => setTimeout(resolve, 25));

    const retransmissions = sender.getRetransmissions();

    console.log(
        "Retransmission candidates:",
        retransmissions.map((item) => item.sequenceNumber)
    );

    console.log("Acknowledged:", sender.acknowledge(packet.sequenceNumber));
}


// =============================================================================
// 8. RECEIVER REORDERING
// =============================================================================

class OrderedReceiver {
    constructor() {
        this.nextExpected = 1;
        this.buffer = new Map();
    }

    receive(packet) {
        if (packet.sequenceNumber < this.nextExpected) {
            // Older packet: treat it as a duplicate.
            return [];
        }

        if (!this.buffer.has(packet.sequenceNumber)) {
            this.buffer.set(packet.sequenceNumber, packet.payload);
        }

        const delivered = [];

        while (this.buffer.has(this.nextExpected)) {
            delivered.push(this.buffer.get(this.nextExpected));
            this.buffer.delete(this.nextExpected);
            this.nextExpected += 1;
        }

        return delivered;
    }
}

function demonstrateReordering() {
    console.log("\n" + "=".repeat(78));
    console.log("OUT-OF-ORDER RECEIVING");
    console.log("=".repeat(78));

    const receiver = new OrderedReceiver();

    const packets = [
        { sequenceNumber: 1, payload: Buffer.from("A") },
        { sequenceNumber: 3, payload: Buffer.from("C") },
        { sequenceNumber: 2, payload: Buffer.from("B") }
    ];

    for (const packet of packets) {
        const delivered = receiver.receive(packet);
        console.log(
            `Received ${packet.sequenceNumber}; delivered:`,
            delivered.map((data) => data.toString())
        );
    }
}


// =============================================================================
// 9. TIMEOUTS
// =============================================================================

async function demonstrateTimeout() {
    console.log("\n" + "=".repeat(78));
    console.log("TIMEOUTS");
    console.log("=".repeat(78));

    const socket = createUdpSocket();

    await new Promise((resolve, reject) => {
        socket.once("error", reject);

        socket.bind(0, "127.0.0.1", () => {
            let timedOut = false;

            const timer = setTimeout(() => {
                timedOut = true;
                console.log("No response arrived before the application timeout.");
                resolve();
            }, 50);

            socket.once("message", () => {
                clearTimeout(timer);

                if (!timedOut) {
                    console.log("Response arrived before timeout.");
                    resolve();
                }
            });
        });
    });

    socket.close();
}


// =============================================================================
// 10. CONCURRENT UDP SERVER
// =============================================================================

async function demonstrateConcurrentServer() {
    console.log("\n" + "=".repeat(78));
    console.log("EVENT-DRIVEN UDP SERVER");
    console.log("=".repeat(78));

    const server = createUdpSocket();
    const client = createUdpSocket();

    await new Promise((resolve, reject) => {
        server.once("error", reject);

        server.on("message", (message, remote) => {
            console.log(
                `Server received "${message}" from ${remote.address}:${remote.port}`
            );

            server.send(
                Buffer.from(`echo:${message.toString()}`),
                remote.port,
                remote.address
            );
        });

        client.once("message", (message) => {
            console.log("Client received:", message.toString());
            resolve();
        });

        server.bind(0, "127.0.0.1", () => {
            const address = server.address();

            client.send(
                Buffer.from("event-driven hello"),
                address.port,
                address.address
            );
        });
    });

    server.close();
    client.close();
}


// =============================================================================
// 11. INPUT VALIDATION
// =============================================================================

function validateDatagram(message, maximumSize = 1200) {
    if (!Buffer.isBuffer(message)) {
        throw new TypeError("Expected a Buffer.");
    }

    if (message.length === 0) {
        throw new Error("Empty datagrams are not accepted.");
    }

    if (message.length > maximumSize) {
        throw new Error("Datagram exceeds application size limit.");
    }

    return message;
}

function demonstrateValidation() {
    console.log("\n" + "=".repeat(78));
    console.log("DATAGRAM VALIDATION");
    console.log("=".repeat(78));

    try {
        console.log(
            "Accepted:",
            validateDatagram(Buffer.from("valid message")).toString()
        );
    } catch (error) {
        console.error(error.message);
    }

    try {
        validateDatagram(Buffer.alloc(2000));
    } catch (error) {
        console.log("Rejected large packet:", error.message);
    }
}


// =============================================================================
// 12. CHECKSUM CONCEPT
// =============================================================================

function internetChecksum(buffer) {
    let data = buffer;

    // A checksum word is 16 bits, so an odd byte is padded conceptually.
    if (data.length % 2 === 1) {
        data = Buffer.concat([data, Buffer.from([0])]);
    }

    let sum = 0;

    for (let offset = 0; offset < data.length; offset += 2) {
        sum += (data[offset] << 8) | data[offset + 1];

        // Fold carry bits into the lower 16 bits.
        sum = (sum & 0xffff) + Math.floor(sum / 0x10000);
    }

    return (~sum) & 0xffff;
}

function demonstrateChecksum() {
    console.log("\n" + "=".repeat(78));
    console.log("CHECKSUM");
    console.log("=".repeat(78));

    const original = Buffer.from("UDP integrity");
    const altered = Buffer.from("UDP integrity!");

    console.log(
        "Original checksum:",
        "0x" + internetChecksum(original).toString(16).padStart(4, "0")
    );

    console.log(
        "Altered checksum:",
        "0x" + internetChecksum(altered).toString(16).padStart(4, "0")
    );

    console.log(
        "Checksums help detect accidental corruption; they do not provide authentication."
    );
}


// =============================================================================
// 13. RANDOM REQUEST IDs
// =============================================================================

function createRequestId() {
    // A cryptographically strong random identifier is preferable to a simple
    // timestamp when IDs are security-sensitive or exposed to attackers.
    return crypto.randomBytes(8).toString("hex");
}

function demonstrateRequestId() {
    console.log("\n" + "=".repeat(78));
    console.log("REQUEST IDENTIFIERS");
    console.log("=".repeat(78));

    console.log("Request ID:", createRequestId());
}


// =============================================================================
// 14. PERFORMANCE CONSIDERATIONS
// =============================================================================

function estimateStopAndWaitThroughput(payloadBytes, roundTripSeconds) {
    if (!Number.isFinite(payloadBytes) || payloadBytes < 0) {
        throw new RangeError("payloadBytes must be non-negative.");
    }

    if (!Number.isFinite(roundTripSeconds) || roundTripSeconds <= 0) {
        throw new RangeError("roundTripSeconds must be positive.");
    }

    return payloadBytes * 8 / roundTripSeconds;
}

function demonstratePerformance() {
    console.log("\n" + "=".repeat(78));
    console.log("PERFORMANCE TRADE-OFF");
    console.log("=".repeat(78));

    const payloadBytes = 1200;

    for (const rtt of [0.01, 0.05, 0.1, 0.25]) {
        const bitsPerSecond = estimateStopAndWaitThroughput(
            payloadBytes,
            rtt
        );

        console.log(
            `RTT ${(rtt * 1000).toFixed(0).padStart(4)} ms -> ` +
            `${(bitsPerSecond / 1000).toFixed(2)} kbit/s`
        );
    }

    console.log(
        "\nA sliding window can keep multiple packets in flight and use network capacity more efficiently."
    );
}


// =============================================================================
// 15. UDP SOCKET OPTIONS
// =============================================================================

async function demonstrateSocketOptions() {
    console.log("\n" + "=".repeat(78));
    console.log("UDP SOCKET OPTIONS");
    console.log("=".repeat(78));

    const socket = createUdpSocket();

    try {
        // Broadcast must be explicitly enabled before sending to an IPv4
        // broadcast destination on platforms that enforce this option.
        socket.setBroadcast(true);
        console.log("Broadcast capability enabled.");

        socket.setRecvBufferSize(256 * 1024);
        console.log(
            "Receive buffer size:",
            socket.getRecvBufferSize()
        );

        socket.setSendBufferSize(256 * 1024);
        console.log(
            "Send buffer size:",
            socket.getSendBufferSize()
        );
    } finally {
        socket.close();
    }
}


// =============================================================================
// 16. ERROR HANDLING
// =============================================================================

function demonstrateMalformedPackets() {
    console.log("\n" + "=".repeat(78));
    console.log("MALFORMED PACKET HANDLING");
    console.log("=".repeat(78));

    const malformedPackets = [
        Buffer.alloc(0),
        Buffer.from([1, 2]),
        Buffer.from([1, 0, 0, 0, 1, 0, 10])
    ];

    for (const packet of malformedPackets) {
        try {
            decodeApplicationMessage(packet);
            console.log("Unexpectedly accepted packet.");
        } catch (error) {
            console.log("Rejected malformed packet:", error.message);
        }
    }
}


// =============================================================================
// 17. SIMPLE TESTS
// =============================================================================

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function runTests() {
    console.log("\n" + "=".repeat(78));
    console.log("SELF-TESTS");
    console.log("=".repeat(78));

    const payload = Buffer.from("test");

    const reliable = decodeReliablePacket(
        encodeReliablePacket(123, payload)
    );

    assert(reliable.sequenceNumber === 123, "sequence number mismatch");
    assert(reliable.payload.equals(payload), "payload mismatch");

    const application = decodeApplicationMessage(
        encodeApplicationMessage(2, 500, payload)
    );

    assert(application.type === 2, "application type mismatch");
    assert(application.requestId === 500, "request ID mismatch");
    assert(application.payload.equals(payload), "application payload mismatch");

    const processor = new IdempotentRequestProcessor();

    const first = processor.process(1, "operation");
    const second = processor.process(1, "operation");

    assert(first === second, "duplicate request was executed differently");

    const receiver = new OrderedReceiver();

    assert(
        receiver.receive({
            sequenceNumber: 2,
            payload: Buffer.from("B")
        }).length === 0,
        "out-of-order packet should wait"
    );

    const delivered = receiver.receive({
        sequenceNumber: 1,
        payload: Buffer.from("A")
    });

    assert(delivered.length === 2, "buffered packet was not released");

    console.log("All tests passed.");
}


// =============================================================================
// 18. MAIN
// =============================================================================

async function main() {
    explainFundamentals();

    await basicUdpExchange();
    await demonstrateDatagramBoundaries();

    demonstrateMessageEncoding();
    demonstrateSequenceNumbers();
    demonstrateIdempotency();

    await demonstrateRetransmission();

    demonstrateReordering();

    await demonstrateTimeout();
    await demonstrateConcurrentServer();

    demonstrateValidation();
    demonstrateChecksum();
    demonstrateRequestId();
    demonstratePerformance();

    await demonstrateSocketOptions();

    demonstrateMalformedPackets();
    runTests();

    console.log("\n" + "=".repeat(78));
    console.log("END OF UDP STUDY PROGRAM");
    console.log("=".repeat(78));
}

main().catch((error) => {
    console.error("Program failed:", error);
    process.exitCode = 1;
});
