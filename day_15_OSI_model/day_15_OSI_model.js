/*
 * OSI Model: Seven Layers and Their Responsibilities
 * ===================================================
 *
 * Self-contained JavaScript study and demonstration program.
 *
 * The examples progress from basic OSI terminology to:
 *   - Addressing
 *   - Ethernet switching
 *   - IP routing
 *   - TCP and UDP
 *   - Sessions
 *   - Data representation
 *   - HTTP
 *   - Encapsulation
 *   - DNS caching
 *   - MTU
 *   - Error detection
 *   - Security
 *   - Troubleshooting
 *   - An end-to-end packet journey
 *
 * Compatible with modern Node.js.
 */


"use strict";


// -----------------------------------------------------------------------------
// 1. OSI LAYERS
// -----------------------------------------------------------------------------

const OSILayers = Object.freeze({
    PHYSICAL: 1,
    DATA_LINK: 2,
    NETWORK: 3,
    TRANSPORT: 4,
    SESSION: 5,
    PRESENTATION: 6,
    APPLICATION: 7
});

const layerNames = Object.freeze({
    1: "Physical",
    2: "Data Link",
    3: "Network",
    4: "Transport",
    5: "Session",
    6: "Presentation",
    7: "Application"
});

const layerResponsibilities = Object.freeze({
    1: "Raw bit transmission through a physical medium.",
    2: "Frames, MAC addresses and local network delivery.",
    3: "Logical addressing and routing between networks.",
    4: "Process-to-process transport and delivery services.",
    5: "Logical session establishment and session state.",
    6: "Data representation, encoding, compression and encryption-related transformations.",
    7: "Network services used directly by applications."
});


function printLayers() {
    console.log("\n" + "=".repeat(72));
    console.log("OSI MODEL");
    console.log("=".repeat(72));

    for (let layer = 7; layer >= 1; layer--) {
        console.log(
            `Layer ${layer}: ${layerNames[layer].padEnd(14)} | ${layerResponsibilities[layer]}`
        );
    }
}


// -----------------------------------------------------------------------------
// 2. BASIC NETWORK IDENTIFIERS
// -----------------------------------------------------------------------------

function isValidIPv4(address) {
    const parts = address.split(".");

    if (parts.length !== 4) {
        return false;
    }

    return parts.every(part => {
        if (!/^\d+$/.test(part)) {
            return false;
        }

        const value = Number(part);
        return value >= 0 && value <= 255;
    });
}


function isValidMAC(address) {
    return /^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$/.test(address);
}


function addressingDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("ADDRESS VALIDATION");
    console.log("=".repeat(72));

    const ip = "192.168.1.10";
    const mac = "AA:BB:CC:DD:EE:10";

    console.log(`${ip} is IPv4: ${isValidIPv4(ip)}`);
    console.log(`${mac} is MAC: ${isValidMAC(mac)}`);

    console.log(
        "IP addresses are logical Layer 3 identifiers. " +
        "MAC addresses are commonly used for local Layer 2 delivery."
    );
}


// -----------------------------------------------------------------------------
// 3. LAYER 1: PHYSICAL
// -----------------------------------------------------------------------------

function bytesToBits(bytes) {
    return Array.from(bytes)
        .map(byte => byte.toString(2).padStart(8, "0"))
        .join("");
}


function physicalLayerDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("LAYER 1 - PHYSICAL");
    console.log("=".repeat(72));

    const message = Buffer.from("Hi");
    const bits = bytesToBits(message);

    console.log(`Bytes: ${message.toString("hex")}`);
    console.log(`Bits : ${bits}`);
    console.log("Possible media: copper, fiber and radio.");
}


// -----------------------------------------------------------------------------
// 4. LAYER 2: DATA LINK
// -----------------------------------------------------------------------------

class EthernetFrame {
    constructor(sourceMAC, destinationMAC, payload) {
        if (!isValidMAC(sourceMAC) || !isValidMAC(destinationMAC)) {
            throw new Error("Invalid MAC address.");
        }

        this.sourceMAC = sourceMAC;
        this.destinationMAC = destinationMAC;
        this.payload = Buffer.from(payload);
        this.fcs = null;
    }

    calculateIntegrity() {
        /*
         * This is a teaching checksum, not Ethernet's real FCS.
         * Real Ethernet uses CRC-32.
         */
        let value = 0;

        for (const byte of this.payload) {
            value = (value + byte) >>> 0;
            value = ((value << 5) - value) >>> 0;
        }

        return value;
    }

    finalize() {
        this.fcs = this.calculateIntegrity();
    }

    verify() {
        return this.fcs === this.calculateIntegrity();
    }
}


class EthernetSwitch {
    constructor() {
        this.macTable = new Map();
    }

    learn(macAddress, port) {
        if (!isValidMAC(macAddress)) {
            throw new Error("Invalid MAC address.");
        }

        this.macTable.set(macAddress.toUpperCase(), port);
    }

    lookup(macAddress) {
        return this.macTable.get(macAddress.toUpperCase()) ?? null;
    }

    printTable() {
        console.log("Switch forwarding table:");

        for (const [mac, port] of this.macTable) {
            console.log(`  ${mac} -> ${port}`);
        }
    }
}


function dataLinkDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("LAYER 2 - ETHERNET SWITCHING");
    console.log("=".repeat(72));

    const switchDevice = new EthernetSwitch();

    switchDevice.learn("AA:AA:AA:AA:AA:01", "port-1");
    switchDevice.learn("AA:AA:AA:AA:AA:02", "port-2");

    switchDevice.printTable();

    const frame = new EthernetFrame(
        "AA:AA:AA:AA:AA:01",
        "AA:AA:AA:AA:AA:02",
        "Layer 2 payload"
    );

    frame.finalize();

    console.log(`Frame valid: ${frame.verify()}`);
    console.log(
        `Known destination port: ${switchDevice.lookup("AA:AA:AA:AA:AA:02")}`
    );

    console.log(
        `Unknown destination port: ${switchDevice.lookup("AA:AA:AA:AA:AA:99")}`
    );
}


// -----------------------------------------------------------------------------
// 5. LAYER 3: NETWORK
// -----------------------------------------------------------------------------

function ipv4ToInteger(address) {
    if (!isValidIPv4(address)) {
        throw new Error(`Invalid IPv4 address: ${address}`);
    }

    return address
        .split(".")
        .reduce((result, octet) => ((result << 8) | Number(octet)) >>> 0, 0);
}


function prefixMask(prefixLength) {
    if (!Number.isInteger(prefixLength) || prefixLength < 0 || prefixLength > 32) {
        throw new Error("Prefix length must be between 0 and 32.");
    }

    if (prefixLength === 0) {
        return 0;
    }

    return (0xFFFFFFFF << (32 - prefixLength)) >>> 0;
}


function sameSubnet(addressA, addressB, prefixLength) {
    const mask = prefixMask(prefixLength);

    return (
        (ipv4ToInteger(addressA) & mask) >>> 0
    ) === (
        (ipv4ToInteger(addressB) & mask) >>> 0
    );
}


class Router {
    constructor() {
        this.routes = [];
    }

    addRoute(networkAddress, prefixLength, nextHop) {
        this.routes.push({
            networkAddress,
            prefixLength,
            nextHop
        });
    }

    lookup(destination) {
        let bestRoute = null;

        for (const route of this.routes) {
            if (!sameSubnet(route.networkAddress, destination, route.prefixLength)) {
                continue;
            }

            if (
                bestRoute === null ||
                route.prefixLength > bestRoute.prefixLength
            ) {
                bestRoute = route;
            }
        }

        return bestRoute;
    }
}


function routingDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("LAYER 3 - ROUTING");
    console.log("=".repeat(72));

    const router = new Router();

    router.addRoute("10.0.0.0", 8, "router-A");
    router.addRoute("10.10.0.0", 16, "router-B");
    router.addRoute("0.0.0.0", 0, "default-gateway");

    const destinations = [
        "10.10.20.5",
        "10.20.1.8",
        "8.8.8.8"
    ];

    for (const destination of destinations) {
        const route = router.lookup(destination);
        console.log(
            `${destination.padEnd(15)} -> ${route ? route.nextHop : "no route"}`
        );
    }
}


// -----------------------------------------------------------------------------
// 6. ARP
// -----------------------------------------------------------------------------

class ARPTable {
    constructor() {
        this.entries = new Map();
    }

    learn(ipAddress, macAddress) {
        if (!isValidIPv4(ipAddress)) {
            throw new Error("Invalid IPv4 address.");
        }

        if (!isValidMAC(macAddress)) {
            throw new Error("Invalid MAC address.");
        }

        this.entries.set(ipAddress, macAddress);
    }

    resolve(ipAddress) {
        return this.entries.get(ipAddress) ?? null;
    }
}


function arpDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("ARP");
    console.log("=".repeat(72));

    const arp = new ARPTable();

    console.log(
        `Before resolution: ${arp.resolve("192.168.1.20")}`
    );

    arp.learn(
        "192.168.1.20",
        "AA:BB:CC:DD:EE:20"
    );

    console.log(
        `After resolution : ${arp.resolve("192.168.1.20")}`
    );

    console.log(
        "ARP demonstrates the interaction between logical IPv4 addressing " +
        "and local Layer 2 addressing."
    );
}


// -----------------------------------------------------------------------------
// 7. LAYER 4: TRANSPORT
// -----------------------------------------------------------------------------

class TCPSegment {
    constructor({
        sourcePort,
        destinationPort,
        sequenceNumber,
        acknowledgementNumber,
        flags,
        payload = Buffer.alloc(0)
    }) {
        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.sequenceNumber = sequenceNumber;
        this.acknowledgementNumber = acknowledgementNumber;
        this.flags = flags;
        this.payload = Buffer.from(payload);

        this.validate();
    }

    validate() {
        for (const port of [this.sourcePort, this.destinationPort]) {
            if (!Number.isInteger(port) || port < 0 || port > 65535) {
                throw new Error(`Invalid TCP port: ${port}`);
            }
        }
    }
}


class UDPDatagram {
    constructor(sourcePort, destinationPort, payload = Buffer.alloc(0)) {
        if (
            sourcePort < 0 ||
            sourcePort > 65535 ||
            destinationPort < 0 ||
            destinationPort > 65535
        ) {
            throw new Error("Invalid UDP port.");
        }

        this.sourcePort = sourcePort;
        this.destinationPort = destinationPort;
        this.payload = Buffer.from(payload);
    }
}


function tcpHandshakeDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("TCP THREE-WAY HANDSHAKE");
    console.log("=".repeat(72));

    const clientISN = 1000;
    const serverISN = 5000;

    const handshake = [
        new TCPSegment({
            sourcePort: 50000,
            destinationPort: 443,
            sequenceNumber: clientISN,
            acknowledgementNumber: 0,
            flags: "SYN"
        }),

        new TCPSegment({
            sourcePort: 443,
            destinationPort: 50000,
            sequenceNumber: serverISN,
            acknowledgementNumber: clientISN + 1,
            flags: "SYN-ACK"
        }),

        new TCPSegment({
            sourcePort: 50000,
            destinationPort: 443,
            sequenceNumber: clientISN + 1,
            acknowledgementNumber: serverISN + 1,
            flags: "ACK"
        })
    ];

    for (const segment of handshake) {
        console.log(
            `${segment.flags.padEnd(7)} ` +
            `seq=${String(segment.sequenceNumber).padEnd(5)} ` +
            `ack=${segment.acknowledgementNumber}`
        );
    }
}


function transportComparison() {
    console.log("\nTCP and UDP comparison:");

    const comparison = [
        ["Connection", "TCP is connection-oriented", "UDP is connectionless"],
        ["Reliability", "TCP provides reliability mechanisms", "UDP does not guarantee delivery"],
        ["Ordering", "TCP provides ordered byte stream", "UDP does not guarantee ordering"],
        ["Overhead", "Higher", "Lower"],
        ["Common uses", "HTTPS, SSH, file transfer", "DNS, real-time applications"]
    ];

    for (const row of comparison) {
        console.log(`${row[0].padEnd(12)} | ${row[1].padEnd(38)} | ${row[2]}`);
    }
}


// -----------------------------------------------------------------------------
// 8. LAYER 5: SESSION
// -----------------------------------------------------------------------------

class Session {
    constructor(id) {
        this.id = id;
        this.state = "NEW";
    }

    start() {
        if (this.state !== "NEW") {
            throw new Error("Session cannot start from the current state.");
        }

        this.state = "ESTABLISHED";
    }

    pause() {
        if (this.state !== "ESTABLISHED") {
            throw new Error("Only an established session can be paused.");
        }

        this.state = "PAUSED";
    }

    resume() {
        if (this.state !== "PAUSED") {
            throw new Error("Only a paused session can be resumed.");
        }

        this.state = "ESTABLISHED";
    }

    close() {
        this.state = "CLOSED";
    }
}


function sessionDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("LAYER 5 - SESSION");
    console.log("=".repeat(72));

    const session = new Session("session-001");

    console.log(session.state);
    session.start();
    console.log(session.state);
    session.pause();
    console.log(session.state);
    session.resume();
    console.log(session.state);
    session.close();
    console.log(session.state);
}


// -----------------------------------------------------------------------------
// 9. LAYER 6: PRESENTATION
// -----------------------------------------------------------------------------

function presentationDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("LAYER 6 - PRESENTATION");
    console.log("=".repeat(72));

    const text = "OSI model: café";

    const utf8 = Buffer.from(text, "utf8");
    const decoded = utf8.toString("utf8");

    console.log(`Original: ${text}`);
    console.log(`UTF-8 bytes: ${utf8.toString("hex")}`);
    console.log(`Decoded: ${decoded}`);

    /*
     * Base64 is encoding, not encryption.
     * Anyone can decode Base64 without a secret key.
     */
    const base64 = utf8.toString("base64");

    console.log(`Base64: ${base64}`);
    console.log(
        `Decoded Base64: ${Buffer.from(base64, "base64").toString("utf8")}`
    );
}


// -----------------------------------------------------------------------------
// 10. LAYER 7: APPLICATION
// -----------------------------------------------------------------------------

class HTTPRequest {
    constructor(method, path, headers = {}, body = "") {
        this.method = method;
        this.path = path;
        this.headers = headers;
        this.body = body;
    }

    serialize() {
        const requestLine = `${this.method} ${this.path} HTTP/1.1\r\n`;

        const headers = Object.entries(this.headers)
            .map(([key, value]) => `${key}: ${value}\r\n`)
            .join("");

        return `${requestLine}${headers}\r\n${this.body}`;
    }
}


function applicationLayerDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("LAYER 7 - APPLICATION");
    console.log("=".repeat(72));

    const request = new HTTPRequest(
        "GET",
        "/index.html",
        {
            "Host": "example.com",
            "Accept": "text/html"
        }
    );

    console.log(request.serialize());

    console.log(
        "HTTP, DNS, SMTP, FTP and SSH are examples of application-layer protocols."
    );
}


// -----------------------------------------------------------------------------
// 11. ENCAPSULATION
// -----------------------------------------------------------------------------

function encapsulationDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("ENCAPSULATION");
    console.log("=".repeat(72));

    const application = Buffer.from("Hello network");

    // Layer 6: represent the application data as UTF-8.
    const presentation = Buffer.from(application.toString("utf8"), "utf8");

    // Layer 5: add a simplified session identifier.
    const session = Buffer.concat([
        Buffer.from("SID=42|"),
        presentation
    ]);

    // Layer 4: simplified transport header.
    const transportHeader = Buffer.alloc(4);
    transportHeader.writeUInt16BE(51520, 0);
    transportHeader.writeUInt16BE(443, 2);

    const transport = Buffer.concat([
        transportHeader,
        session
    ]);

    // Layer 3: simplified IP metadata.
    const network = Buffer.concat([
        Buffer.from("IP 192.168.1.10 -> 203.0.113.20|"),
        transport
    ]);

    // Layer 2: simplified Ethernet metadata.
    const frame = Buffer.concat([
        Buffer.from("ETH AA:AA:AA:AA:AA:10 -> AA:AA:AA:AA:AA:01|"),
        network
    ]);

    // Layer 1: physical representation.
    const physicalBits = bytesToBits(frame);

    console.log(`Layer 7: ${application.toString()}`);
    console.log(`Layer 6: ${presentation.toString()}`);
    console.log(`Layer 5: ${session.toString()}`);
    console.log(`Layer 4 bytes: ${transport.toString("hex")}`);
    console.log(`Layer 3: ${network.toString().slice(0, 80)}...`);
    console.log(`Layer 2: ${frame.toString().slice(0, 80)}...`);
    console.log(`Layer 1 bits: ${physicalBits.slice(0, 96)}...`);

    return {
        application,
        presentation,
        session,
        transport,
        network,
        frame,
        physicalBits
    };
}


function decapsulationDemo(data) {
    console.log("\n" + "=".repeat(72));
    console.log("DECAPSULATION");
    console.log("=".repeat(72));

    console.log("Receiver processes the representation in the reverse direction:");
    console.log("Bits -> Frame -> Packet -> Segment -> Session -> Presentation -> Application");
    console.log(`Final application data: ${data.application.toString()}`);
}


// -----------------------------------------------------------------------------
// 12. MTU
// -----------------------------------------------------------------------------

function mtuDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("MTU");
    console.log("=".repeat(72));

    const mtu = 1500;
    const payloadBytes = 4200;

    const packets = Math.ceil(payloadBytes / mtu);

    console.log(`MTU: ${mtu} bytes`);
    console.log(`Payload: ${payloadBytes} bytes`);
    console.log(`Minimum simplified chunk count: ${packets}`);

    console.log(
        "Actual IP fragmentation behavior depends on protocol version, " +
        "headers and path MTU conditions."
    );
}


// -----------------------------------------------------------------------------
// 13. DNS CACHE
// -----------------------------------------------------------------------------

class DNSCache {
    constructor() {
        this.records = new Map();
    }

    set(hostname, address, ttlMilliseconds) {
        this.records.set(hostname, {
            address,
            expiresAt: Date.now() + ttlMilliseconds
        });
    }

    get(hostname) {
        const record = this.records.get(hostname);

        if (!record) {
            return null;
        }

        if (Date.now() >= record.expiresAt) {
            this.records.delete(hostname);
            return null;
        }

        return record.address;
    }
}


function dnsDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("DNS CACHE");
    console.log("=".repeat(72));

    const cache = new DNSCache();

    cache.set(
        "example.com",
        "93.184.216.34",
        60_000
    );

    console.log(`example.com -> ${cache.get("example.com")}`);

    console.log(
        "DNS maps names to resource records. Caching reduces lookup latency " +
        "but introduces TTL and stale-data considerations."
    );
}


// -----------------------------------------------------------------------------
// 14. ASYNCHRONOUS NETWORKING
// -----------------------------------------------------------------------------

function delay(milliseconds) {
    return new Promise(resolve => {
        setTimeout(resolve, milliseconds);
    });
}


async function simulatedNetworkRequest() {
    console.log("\nStarting simulated network request...");

    await delay(100);

    return {
        statusCode: 200,
        body: "Application response"
    };
}


async function asynchronousDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("ASYNC APPLICATION-LAYER BEHAVIOR");
    console.log("=".repeat(72));

    try {
        const response = await simulatedNetworkRequest();

        if (response.statusCode < 200 || response.statusCode >= 300) {
            throw new Error(`Unexpected status: ${response.statusCode}`);
        }

        console.log(`Response: ${response.body}`);
    } catch (error) {
        console.error(`Request failed: ${error.message}`);
    }
}


// -----------------------------------------------------------------------------
// 15. ERROR DETECTION
// -----------------------------------------------------------------------------

function simpleChecksum(buffer) {
    let checksum = 0;

    for (const byte of buffer) {
        checksum = (checksum + byte) & 0xFFFF;
    }

    return checksum;
}


function errorDetectionDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("ERROR DETECTION");
    console.log("=".repeat(72));

    const original = Buffer.from("network integrity");
    const corrupted = Buffer.from("network integritY");

    const originalChecksum = simpleChecksum(original);
    const corruptedChecksum = simpleChecksum(corrupted);

    console.log(`Original checksum : ${originalChecksum}`);
    console.log(`Corrupted checksum: ${corruptedChecksum}`);
    console.log(
        `Difference detected: ${originalChecksum !== corruptedChecksum}`
    );

    console.log(
        "Real protocols use more carefully designed integrity mechanisms. " +
        "This example demonstrates the principle only."
    );
}


// -----------------------------------------------------------------------------
// 16. OSI TROUBLESHOOTING
// -----------------------------------------------------------------------------

const troubleshooting = {
    1: [
        "Cable disconnected",
        "Radio interference",
        "Faulty interface",
        "Incorrect physical configuration"
    ],
    2: [
        "Wrong VLAN",
        "Switch port problem",
        "MAC learning problem",
        "Local broadcast-domain issue"
    ],
    3: [
        "Wrong IP address",
        "Wrong subnet",
        "Missing route",
        "Default gateway failure"
    ],
    4: [
        "Blocked port",
        "Service not listening",
        "TCP handshake failure",
        "UDP loss"
    ],
    5: [
        "Session timeout",
        "Session state mismatch",
        "Authentication/session state failure"
    ],
    6: [
        "Encoding mismatch",
        "TLS/certificate issue",
        "Serialization incompatibility"
    ],
    7: [
        "HTTP error",
        "DNS application issue",
        "Invalid API request",
        "Authentication failure"
    ]
};


function troubleshootingDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("TROUBLESHOOTING BY OSI LAYER");
    console.log("=".repeat(72));

    for (let layer = 1; layer <= 7; layer++) {
        console.log(`\nLayer ${layer} - ${layerNames[layer]}`);

        for (const problem of troubleshooting[layer]) {
            console.log(`  - ${problem}`);
        }
    }
}


// -----------------------------------------------------------------------------
// 17. SECURITY
// -----------------------------------------------------------------------------

function securityDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("SECURITY BY LAYER");
    console.log("=".repeat(72));

    const controls = {
        1: "Physical access controls and protected media",
        2: "VLANs, port security and 802.1X",
        3: "ACLs, IPsec and anti-spoofing",
        4: "Firewalls, rate limiting and connection controls",
        5: "Secure session identifiers and expiration",
        6: "TLS, certificate validation and safe representation",
        7: "Authentication, authorization and input validation"
    };

    for (let layer = 1; layer <= 7; layer++) {
        console.log(`Layer ${layer} ${layerNames[layer].padEnd(14)}: ${controls[layer]}`);
    }

    console.log(
        "\nSecurity controls normally operate across multiple layers rather than " +
        "being confined to one OSI layer."
    );
}


// -----------------------------------------------------------------------------
// 18. PACKET JOURNEY
// -----------------------------------------------------------------------------

async function packetJourneyDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("REALISTIC WEB REQUEST JOURNEY");
    console.log("=".repeat(72));

    const steps = [
        ["7 Application", "Browser creates an HTTP request."],
        ["6 Presentation", "Data is represented as bytes and protected by TLS in HTTPS."],
        ["5 Session", "Application/session state is maintained where applicable."],
        ["4 Transport", "TCP uses ports and reliability mechanisms."],
        ["3 Network", "IP determines the destination and routers determine next hops."],
        ["2 Data Link", "Ethernet/Wi-Fi provides local-hop delivery using MAC addresses."],
        ["1 Physical", "The frame is transmitted as physical signals."]
    ];

    for (const [layer, action] of steps) {
        console.log(`${layer.padEnd(18)}: ${action}`);
    }

    await delay(50);

    console.log("\nAt a router:");
    console.log("  Layer 2 framing is removed from the incoming link.");
    console.log("  The Layer 3 destination remains the end destination.");
    console.log("  A new Layer 2 frame is constructed for the next link.");

    console.log("\nAt the server:");
    console.log("  The receiving stack processes the data upward until the application receives it.");
}


// -----------------------------------------------------------------------------
// 19. EDGE CASES
// -----------------------------------------------------------------------------

function edgeCasesDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("EDGE CASES AND IMPORTANT DISTINCTIONS");
    console.log("=".repeat(72));

    const distinctions = [
        "OSI is a conceptual reference model, not a literal implementation requirement.",
        "TCP reliability does not validate application-level business semantics.",
        "UDP can support reliable application protocols when reliability is implemented above it.",
        "TLS has responsibilities that do not map perfectly to one OSI layer.",
        "Switches can operate at Layer 3 when implemented as multilayer switches.",
        "Routers process information beyond a simplistic single-layer abstraction.",
        "Base64 is encoding, not encryption.",
        "An IP address does not directly identify a person.",
        "A port identifies a transport endpoint, not automatically a trustworthy service.",
        "IPv6 routers do not fragment packets in transit."
    ];

    for (const distinction of distinctions) {
        console.log(`- ${distinction}`);
    }
}


// -----------------------------------------------------------------------------
// 20. OSI VS TCP/IP
// -----------------------------------------------------------------------------

function osiVsTcpIpDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("OSI VS TCP/IP");
    console.log("=".repeat(72));

    const mappings = [
        ["OSI Application", "TCP/IP Application"],
        ["OSI Presentation", "TCP/IP Application"],
        ["OSI Session", "TCP/IP Application"],
        ["OSI Transport", "TCP/IP Transport"],
        ["OSI Network", "TCP/IP Internet"],
        ["OSI Data Link", "TCP/IP Link"],
        ["OSI Physical", "TCP/IP Link"]
    ];

    for (const [osi, tcpip] of mappings) {
        console.log(`${osi.padEnd(24)} -> ${tcpip}`);
    }

    console.log(
        "\nThe TCP/IP model is more directly associated with the Internet protocol suite, " +
        "while OSI is highly useful for conceptualization and troubleshooting."
    );
}


// -----------------------------------------------------------------------------
// 21. VALIDATION
// -----------------------------------------------------------------------------

function validationDemo() {
    console.log("\n" + "=".repeat(72));
    console.log("VALIDATION");
    console.log("=".repeat(72));

    const invalidIPs = [
        "999.1.1.1",
        "192.168.1",
        "hello.world"
    ];

    for (const ip of invalidIPs) {
        console.log(`${ip.padEnd(18)} valid IPv4: ${isValidIPv4(ip)}`);
    }

    try {
        new TCPSegment({
            sourcePort: 70000,
            destinationPort: 443,
            sequenceNumber: 1,
            acknowledgementNumber: 0,
            flags: "SYN"
        });
    } catch (error) {
        console.log(`Rejected invalid TCP segment: ${error.message}`);
    }
}


// -----------------------------------------------------------------------------
// 22. MAIN
// -----------------------------------------------------------------------------

async function main() {
    printLayers();

    addressingDemo();
    physicalLayerDemo();
    dataLinkDemo();
    routingDemo();
    arpDemo();

    tcpHandshakeDemo();
    transportComparison();

    sessionDemo();
    presentationDemo();
    applicationLayerDemo();

    const encapsulatedData = encapsulationDemo();
    decapsulationDemo(encapsulatedData);

    mtuDemo();
    dnsDemo();

    await asynchronousDemo();

    errorDetectionDemo();
    troubleshootingDemo();
    securityDemo();

    osiVsTcpIpDemo();
    validationDemo();
    edgeCasesDemo();

    await packetJourneyDemo();

    console.log("\n" + "=".repeat(72));
    console.log("JAVASCRIPT OSI STUDY PROGRAM FINISHED");
    console.log("=".repeat(72));
}


main().catch(error => {
    console.error(`Fatal error: ${error.message}`);
    process.exitCode = 1;
});
