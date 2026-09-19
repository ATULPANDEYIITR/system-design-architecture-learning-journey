"use strict";

/*
 * TCP: Connections, Handshake, Reliability, and Retransmission
 *
 * This file complements the Python study program by emphasizing JavaScript's
 * event-driven programming model and Node.js TCP socket API.
 *
 * Run:
 *   node tcp-study.js
 *
 * The program uses only Node.js built-in modules.
 */

const net = require("net");

// -----------------------------------------------------------------------------
// 1. TCP concepts represented as JavaScript data
// -----------------------------------------------------------------------------

function showFundamentals() {
    console.log("\n=== TCP FUNDAMENTALS ===");

    const concepts = {
        TCP: "Connection-oriented transport protocol providing an ordered byte stream.",
        SYN: "Synchronizes sequence numbers during connection establishment.",
        ACK: "Acknowledges received sequence space.",
        FIN: "Requests orderly closure of one direction.",
        RST: "Immediately resets a connection.",
        sequenceNumber: "Identifies a position in the TCP byte stream.",
        receiveWindow: "Advertised amount of receive capacity.",
        retransmission: "Resending data when delivery is not successfully confirmed.",
        RTT: "Round-trip time between transmission and acknowledgment.",
        RTO: "Retransmission timeout derived from RTT behavior.",
    };

    for (const [name, meaning] of Object.entries(concepts)) {
        console.log(`${name}: ${meaning}`);
    }
}

// -----------------------------------------------------------------------------
// 2. Three-way handshake model
// -----------------------------------------------------------------------------

function simulateHandshake(clientIsn = 10000, serverIsn = 50000) {
    console.log("\n=== THREE-WAY HANDSHAKE ===");

    const messages = [
        {
            sender: "Client",
            receiver: "Server",
            flags: ["SYN"],
            sequence: clientIsn,
            acknowledgment: 0,
        },
        {
            sender: "Server",
            receiver: "Client",
            flags: ["SYN", "ACK"],
            sequence: serverIsn,
            acknowledgment: clientIsn + 1,
        },
        {
            sender: "Client",
            receiver: "Server",
            flags: ["ACK"],
            sequence: clientIsn + 1,
            acknowledgment: serverIsn + 1,
        },
    ];

    for (const message of messages) {
        console.log(
            `${message.sender} -> ${message.receiver} ` +
            `${message.flags.join("+")} ` +
            `SEQ=${message.sequence} ` +
            `ACK=${message.acknowledgment}`
        );
    }
}

// -----------------------------------------------------------------------------
// 3. Byte-stream behavior
// -----------------------------------------------------------------------------

function demonstrateByteStream() {
    console.log("\n=== TCP BYTE STREAM ===");

    const applicationMessages = [
        Buffer.from("HELLO"),
        Buffer.from("WORLD"),
    ];

    const combined = Buffer.concat(applicationMessages);

    console.log(`Application writes: ${applicationMessages.map(b => b.toString())}`);
    console.log(`TCP stream: ${combined.toString()}`);
    console.log(
        "TCP does not retain the application's original message boundaries. " +
        "An application protocol must define framing."
    );
}

// -----------------------------------------------------------------------------
// 4. Length-prefixed application framing
// -----------------------------------------------------------------------------

function encodeMessage(message) {
    const payload = Buffer.from(message, "utf8");

    if (payload.length > 0xffffffff) {
        throw new RangeError("Message is too large.");
    }

    const header = Buffer.alloc(4);
    header.writeUInt32BE(payload.length, 0);

    return Buffer.concat([header, payload]);
}

function decodeMessages(buffer) {
    const messages = [];
    let offset = 0;

    while (buffer.length - offset >= 4) {
        const messageLength = buffer.readUInt32BE(offset);

        if (messageLength > 100 * 1024 * 1024) {
            throw new Error("Application frame exceeds configured limit.");
        }

        if (buffer.length - offset < 4 + messageLength) {
            break;
        }

        const start = offset + 4;
        const end = start + messageLength;

        messages.push(buffer.subarray(start, end).toString("utf8"));
        offset = end;
    }

    return {
        messages,
        remaining: buffer.subarray(offset),
    };
}

function demonstrateFraming() {
    console.log("\n=== LENGTH-PREFIXED FRAMING ===");

    const wireData = Buffer.concat([
        encodeMessage("first"),
        encodeMessage("second"),
        encodeMessage("third"),
    ]);

    // Simulate TCP delivering arbitrary chunks.
    const chunks = [
        wireData.subarray(0, 3),
        wireData.subarray(3, 9),
        wireData.subarray(9),
    ];

    let receiveBuffer = Buffer.alloc(0);
    const messages = [];

    for (const chunk of chunks) {
        receiveBuffer = Buffer.concat([receiveBuffer, chunk]);

        const result = decodeMessages(receiveBuffer);
        messages.push(...result.messages);
        receiveBuffer = result.remaining;
    }

    console.log("Decoded messages:", messages);
}

// -----------------------------------------------------------------------------
// 5. Simplified RTT/RTO estimator
// -----------------------------------------------------------------------------

class RttEstimator {
    constructor() {
        this.srtt = null;
        this.rttvar = null;
        this.rto = null;
    }

    update(measuredRtt) {
        if (!Number.isFinite(measuredRtt) || measuredRtt <= 0) {
            throw new RangeError("RTT must be a positive finite number.");
        }

        if (this.srtt === null) {
            this.srtt = measuredRtt;
            this.rttvar = measuredRtt / 2;
        } else {
            const alpha = 1 / 8;
            const beta = 1 / 4;

            this.rttvar =
                (1 - beta) * this.rttvar +
                beta * Math.abs(this.srtt - measuredRtt);

            this.srtt =
                (1 - alpha) * this.srtt +
                alpha * measuredRtt;
        }

        this.rto = this.srtt + 4 * this.rttvar;
    }
}

function demonstrateRttEstimation() {
    console.log("\n=== RTT AND RTO ===");

    const estimator = new RttEstimator();

    for (const sample of [0.10, 0.12, 0.09, 0.20, 0.15]) {
        estimator.update(sample);

        console.log(
            `sample=${sample.toFixed(3)}s ` +
            `SRTT=${estimator.srtt.toFixed(3)}s ` +
            `RTTVAR=${estimator.rttvar.toFixed(3)}s ` +
            `RTO=${estimator.rto.toFixed(3)}s`
        );
    }
}

// -----------------------------------------------------------------------------
// 6. Reliability simulation
// -----------------------------------------------------------------------------

class ReliableTransferSimulator {
    constructor(data, segmentSize = 4, lossProbability = 0.25, seed = 7) {
        if (!Buffer.isBuffer(data)) {
            throw new TypeError("data must be a Buffer.");
        }

        if (!Number.isInteger(segmentSize) || segmentSize <= 0) {
            throw new RangeError("segmentSize must be positive.");
        }

        if (lossProbability < 0 || lossProbability > 1) {
            throw new RangeError("lossProbability must be between 0 and 1.");
        }

        this.data = data;
        this.segmentSize = segmentSize;
        this.lossProbability = lossProbability;
        this.state = seed >>> 0;
        this.retransmissions = 0;
        this.transmissions = 0;
        this.received = Buffer.alloc(0);
    }

    random() {
        // Small deterministic pseudo-random generator for reproducible output.
        this.state = (1664525 * this.state + 1013904223) >>> 0;
        return this.state / 0x100000000;
    }

    run() {
        console.log("\n=== RELIABLE TRANSFER SIMULATION ===");

        for (
            let sequence = 0;
            sequence < this.data.length;
            sequence += this.segmentSize
        ) {
            const payload = this.data.subarray(
                sequence,
                Math.min(sequence + this.segmentSize, this.data.length)
            );

            let delivered = false;
            let attempts = 0;

            while (!delivered) {
                attempts++;
                this.transmissions++;

                const retransmission = attempts > 1;

                if (retransmission) {
                    this.retransmissions++;
                }

                if (this.random() < this.lossProbability) {
                    console.log(
                        `LOSS seq=${sequence} len=${payload.length} ` +
                        `attempt=${attempts}`
                    );
                    continue;
                }

                // In this stop-and-wait demonstration, the receiver receives
                // the expected segment and acknowledges its next sequence.
                this.received = Buffer.concat([this.received, payload]);

                const acknowledgment = sequence + payload.length;

                console.log(
                    `DELIVERED seq=${sequence} len=${payload.length} ` +
                    `ACK=${acknowledgment} retransmission=${retransmission}`
                );

                delivered = true;
            }
        }

        console.log(`Original: ${this.data.toString()}`);
        console.log(`Received: ${this.received.toString()}`);
        console.log(`Transmissions: ${this.transmissions}`);
        console.log(`Retransmissions: ${this.retransmissions}`);

        if (!this.received.equals(this.data)) {
            throw new Error("Reliability simulation failed.");
        }
    }
}

// -----------------------------------------------------------------------------
// 7. Sliding-window model
// -----------------------------------------------------------------------------

class SlidingWindow {
    constructor(base, windowSize) {
        if (!Number.isInteger(windowSize) || windowSize <= 0) {
            throw new RangeError("windowSize must be positive.");
        }

        this.base = base;
        this.nextSequence = base;
        this.windowSize = windowSize;
    }

    canSend() {
        return this.nextSequence < this.base + this.windowSize;
    }

    send() {
        if (!this.canSend()) {
            throw new Error("Send window is full.");
        }

        return this.nextSequence++;
    }

    acknowledge(acknowledgment) {
        if (acknowledgment < this.base) {
            return;
        }

        if (acknowledgment > this.nextSequence) {
            throw new Error("Invalid ACK.");
        }

        this.base = acknowledgment;
    }
}

function demonstrateSlidingWindow() {
    console.log("\n=== SLIDING WINDOW ===");

    const window = new SlidingWindow(1000, 4);

    while (window.canSend()) {
        console.log(`Sent sequence=${window.send()}`);
    }

    console.log(`Window available? ${window.canSend()}`);

    window.acknowledge(1002);

    console.log(`New base=${window.base}`);
    console.log(`Window available? ${window.canSend()}`);
    console.log(`New sequence=${window.send()}`);
}

// -----------------------------------------------------------------------------
// 8. Real Node.js TCP server
// -----------------------------------------------------------------------------

function createEchoServer(host = "127.0.0.1", port = 0) {
    return new Promise((resolve, reject) => {
        const server = net.createServer((socket) => {
            console.log(
                `Server accepted connection from ${socket.remoteAddress}:` +
                `${socket.remotePort}`
            );

            socket.on("data", (chunk) => {
                console.log(`Server received ${chunk.length} bytes.`);
                socket.write(chunk);
            });

            socket.on("end", () => {
                console.log("Client performed orderly shutdown.");
                server.close();
            });

            socket.on("error", (error) => {
                console.error("Server socket error:", error.message);
            });
        });

        server.once("error", reject);

        server.listen(port, host, () => {
            const address = server.address();

            if (typeof address === "object" && address !== null) {
                resolve({
                    server,
                    host,
                    port: address.port,
                });
            } else {
                reject(new Error("Unable to determine server address."));
            }
        });
    });
}

// -----------------------------------------------------------------------------
// 9. Real Node.js TCP client
// -----------------------------------------------------------------------------

function runEchoClient(host, port, message, timeoutMs = 5000) {
    return new Promise((resolve, reject) => {
        const socket = net.createConnection({ host, port });

        const received = [];

        const timer = setTimeout(() => {
            socket.destroy();
            reject(new Error("TCP client timed out."));
        }, timeoutMs);

        socket.on("connect", () => {
            console.log("Client connected.");
            socket.write(message);
        });

        socket.on("data", (chunk) => {
            received.push(chunk);
            socket.end();
        });

        socket.on("end", () => {
            clearTimeout(timer);
            resolve(Buffer.concat(received));
        });

        socket.on("error", (error) => {
            clearTimeout(timer);
            reject(error);
        });
    });
}

// -----------------------------------------------------------------------------
// 10. Real socket demonstration
// -----------------------------------------------------------------------------

async function demonstrateRealTcp() {
    console.log("\n=== REAL NODE.JS TCP CONNECTION ===");

    const { server, host, port } = await createEchoServer();

    try {
        const response = await runEchoClient(
            host,
            port,
            Buffer.from("Hello over TCP")
        );

        console.log(`Client received: ${response.toString()}`);
    } finally {
        server.close();
    }
}

// -----------------------------------------------------------------------------
// 11. TCP performance and security
// -----------------------------------------------------------------------------

function showPerformanceAndSecurity() {
    console.log("\n=== PERFORMANCE ===");
    console.log("- RTT influences interactive latency.");
    console.log("- MSS controls useful TCP payload size.");
    console.log("- cwnd limits traffic according to congestion state.");
    console.log("- rwnd limits traffic according to receiver capacity.");
    console.log("- Retransmission consumes bandwidth and increases latency.");
    console.log("- Nagle's algorithm can combine small writes.");
    console.log("- TCP_NODELAY can reduce latency for some small-message workloads.");
    console.log("- Connection setup adds handshake latency.");

    console.log("\n=== SECURITY ===");
    console.log("- TCP itself does not encrypt application data.");
    console.log("- TLS provides confidentiality and authentication above TCP.");
    console.log("- SYN floods target the connection-establishment path.");
    console.log("- Connection limits and SYN-cookie techniques can mitigate resource exhaustion.");
    console.log("- Application authentication remains necessary.");
    console.log("- Input validation is required after reliable delivery.");
}

// -----------------------------------------------------------------------------
// 12. Main program
// -----------------------------------------------------------------------------

async function main() {
    showFundamentals();
    simulateHandshake();
    demonstrateByteStream();
    demonstrateFraming();
    demonstrateRttEstimation();

    const simulator = new ReliableTransferSimulator(
        Buffer.from("TCP survives controlled packet loss."),
        6,
        0.30,
        42
    );

    simulator.run();
    demonstrateSlidingWindow();
    showPerformanceAndSecurity();

    // The real socket demonstration creates an actual local TCP connection.
    await demonstrateRealTcp();
}

if (require.main === module) {
    main().catch((error) => {
        console.error("Program failed:", error.message);
        process.exitCode = 1;
    });
}
