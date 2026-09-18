/*
DNS: Domain Resolution, Recursive DNS, and Caching
==================================================

This file complements the Python study implementation by emphasizing
JavaScript data modeling, asynchronous resolution, event-driven behavior,
cache promises, validation, and application-level DNS workflows.

The program uses a deterministic simulated DNS infrastructure and therefore
does not require external npm packages or Internet access.
*/

"use strict";

// ---------------------------------------------------------------------------
// 1. Basic DNS terminology represented as JavaScript data
// ---------------------------------------------------------------------------

console.log("\n=== 1. DNS fundamentals ===");

const recordTypes = Object.freeze({
    A: "A",
    AAAA: "AAAA",
    CNAME: "CNAME",
    NS: "NS",
    MX: "MX",
    TXT: "TXT",
    SOA: "SOA",
    PTR: "PTR"
});

function normalizeName(name) {
    if (typeof name !== "string") {
        throw new TypeError("DNS name must be a string");
    }

    const normalized = name.trim().toLowerCase();

    if (normalized.length === 0) {
        throw new Error("DNS name cannot be empty");
    }

    return normalized.endsWith(".") ? normalized : `${normalized}.`;
}

function createRecord(name, type, value, ttl = 300) {
    if (!Object.values(recordTypes).includes(type)) {
        throw new Error(`Unsupported record type: ${type}`);
    }

    if (!Number.isInteger(ttl) || ttl < 0) {
        throw new Error("TTL must be a non-negative integer");
    }

    return Object.freeze({
        name: normalizeName(name),
        type,
        value,
        ttl
    });
}

const exampleRecords = [
    createRecord("example.com", recordTypes.A, "93.184.216.34", 3600),
    createRecord(
        "example.com",
        recordTypes.AAAA,
        "2606:2800:220:1:248:1893:25c8:1946",
        3600
    ),
    createRecord(
        "www.example.com",
        recordTypes.CNAME,
        "example.com.",
        300
    ),
    createRecord(
        "example.com",
        recordTypes.MX,
        "10 mail.example.com.",
        1800
    ),
    createRecord(
        "mail.example.com",
        recordTypes.A,
        "192.0.2.25",
        300
    )
];

for (const record of exampleRecords) {
    console.log(
        `${record.name} ${record.ttl} IN ${record.type} ${record.value}`
    );
}


// ---------------------------------------------------------------------------
// 2. DNS zone model
// ---------------------------------------------------------------------------

class DNSZone {
    constructor(origin) {
        this.origin = normalizeName(origin);
        this.records = new Map();
    }

    key(name, type) {
        return `${normalizeName(name)}|${type}`;
    }

    addRecord(record) {
        if (!record || !record.name || !record.type) {
            throw new Error("Invalid DNS record");
        }

        const key = this.key(record.name, record.type);

        if (!this.records.has(key)) {
            this.records.set(key, []);
        }

        this.records.get(key).push(record);
    }

    query(name, type) {
        const key = this.key(name, type);
        return [...(this.records.get(key) || [])];
    }
}

const exampleZone = new DNSZone("example.com");

for (const record of exampleRecords) {
    exampleZone.addRecord(record);
}

console.log("\nA record:");
console.log(exampleZone.query("example.com", recordTypes.A));


// ---------------------------------------------------------------------------
// 3. Authoritative server
// ---------------------------------------------------------------------------

class AuthoritativeServer {
    constructor(name) {
        this.name = normalizeName(name);
        this.zones = new Map();
    }

    addZone(zone) {
        this.zones.set(zone.origin, zone);
    }

    findZone(name) {
        const normalized = normalizeName(name);

        for (const [origin, zone] of this.zones) {
            if (
                normalized === origin ||
                normalized.endsWith(`.${origin}`)
            ) {
                return zone;
            }
        }

        return null;
    }

    query(name, type) {
        const zone = this.findZone(name);

        if (!zone) {
            return {
                status: "REFUSED",
                answers: []
            };
        }

        const answers = zone.query(name, type);

        if (answers.length > 0) {
            return {
                status: "NOERROR",
                answers
            };
        }

        const aliases = zone.query(name, recordTypes.CNAME);

        if (aliases.length > 0 && type !== recordTypes.CNAME) {
            return {
                status: "CNAME",
                answers: aliases
            };
        }

        return {
            status: "NXDOMAIN",
            answers: []
        };
    }
}

const authoritativeServer = new AuthoritativeServer("ns1.example.com");
authoritativeServer.addZone(exampleZone);


// ---------------------------------------------------------------------------
// 4. Root and TLD hierarchy
// ---------------------------------------------------------------------------

const rootDelegations = new Map([
    [
        "com.",
        [
            "a.gtld-servers.net.",
            "b.gtld-servers.net."
        ]
    ],
    [
        "org.",
        [
            "a0.org.afilias-nst.info."
        ]
    ]
]);

const tldDelegations = new Map([
    [
        "example.com.",
        [
            "ns1.example.com.",
            "ns2.example.com."
        ]
    ]
]);

function getTld(name) {
    const labels = normalizeName(name)
        .slice(0, -1)
        .split(".");

    if (labels.length < 2) {
        return ".";
    }

    return `${labels[labels.length - 1]}.`;
}

function getZoneCandidate(name) {
    const labels = normalizeName(name)
        .slice(0, -1)
        .split(".");

    if (labels.length < 2) {
        return normalizeName(name);
    }

    return `${labels.slice(-2).join(".")}.`;
}

console.log("\n=== 2. Hierarchy ===");
console.log(getTld("www.example.com"));
console.log(getZoneCandidate("www.example.com"));


// ---------------------------------------------------------------------------
// 5. Asynchronous iterative resolver
// ---------------------------------------------------------------------------

function delay(milliseconds) {
    return new Promise(resolve => {
        setTimeout(resolve, milliseconds);
    });
}

class SimulatedDNSInfrastructure {
    constructor(authoritative) {
        this.servers = new Map([
            ["ns1.example.com.", authoritative],
            ["ns2.example.com.", authoritative]
        ]);
    }

    async authoritativeQuery(serverName, name, type) {
        // A real implementation would transmit a DNS message here.
        // The artificial delay represents network round-trip latency.
        await delay(5);

        const server = this.servers.get(normalizeName(serverName));

        if (!server) {
            return {
                status: "SERVFAIL",
                answers: [],
                trace: [`${serverName}: unavailable`]
            };
        }

        const result = server.query(name, type);

        return {
            ...result,
            trace: [`${serverName}: ${result.status}`]
        };
    }

    async iterativeResolve(name, type) {
        const normalized = normalizeName(name);
        const trace = ["Resolver begins iterative resolution"];

        const tld = getTld(normalized);

        if (!rootDelegations.has(tld)) {
            return {
                status: "NXDOMAIN",
                answers: [],
                trace: [...trace, `Root: no delegation for ${tld}`]
            };
        }

        trace.push(`Root: referral for ${tld}`);

        const zone = getZoneCandidate(normalized);
        const nameservers = tldDelegations.get(zone);

        if (!nameservers) {
            return {
                status: "NXDOMAIN",
                answers: [],
                trace: [...trace, `TLD: no delegation for ${zone}`]
            };
        }

        trace.push(`TLD: referral to ${nameservers.join(", ")}`);

        for (const nameserver of nameservers) {
            const result = await this.authoritativeQuery(
                nameserver,
                normalized,
                type
            );

            trace.push(...result.trace);

            if (result.status === "NOERROR") {
                return {
                    status: "NOERROR",
                    answers: result.answers,
                    trace
                };
            }

            if (result.status === "CNAME") {
                const target = result.answers[0].value;

                trace.push(`Following CNAME to ${target}`);

                const targetResult = await this.iterativeResolve(
                    target,
                    type
                );

                return {
                    status: targetResult.status,
                    answers: targetResult.answers,
                    trace: [
                        ...trace,
                        ...targetResult.trace
                    ]
                };
            }
        }

        return {
            status: "SERVFAIL",
            answers: [],
            trace: [
                ...trace,
                "All authoritative servers failed"
            ]
        };
    }
}


// ---------------------------------------------------------------------------
// 6. Recursive resolver with TTL-aware cache
// ---------------------------------------------------------------------------

class RecursiveResolver {
    constructor(infrastructure, clock = () => Date.now()) {
        this.infrastructure = infrastructure;
        this.clock = clock;
        this.cache = new Map();
    }

    cacheKey(name, type) {
        return `${normalizeName(name)}|${type}`;
    }

    getCached(key) {
        const entry = this.cache.get(key);

        if (!entry) {
            return null;
        }

        if (entry.expiresAt <= this.clock()) {
            this.cache.delete(key);
            return null;
        }

        return entry;
    }

    async query(name, type) {
        const normalized = normalizeName(name);
        const key = this.cacheKey(normalized, type);

        const cached = this.getCached(key);

        if (cached) {
            const remaining = Math.max(
                0,
                Math.floor((cached.expiresAt - this.clock()) / 1000)
            );

            return {
                status: cached.status,
                answers: cached.answers,
                trace: [`Cache hit; remaining TTL=${remaining}s`]
            };
        }

        const result = await this.infrastructure.iterativeResolve(
            normalized,
            type
        );

        if (result.answers.length > 0) {
            const ttl = Math.min(
                ...result.answers.map(record => record.ttl)
            );

            this.cache.set(key, {
                status: result.status,
                answers: result.answers,
                expiresAt: this.clock() + ttl * 1000
            });
        } else if (result.status === "NXDOMAIN") {
            // Real negative caching is derived from authoritative SOA data.
            this.cache.set(key, {
                status: "NXDOMAIN",
                answers: [],
                expiresAt: this.clock() + 30_000
            });
        }

        return {
            status: result.status,
            answers: result.answers,
            trace: ["Cache miss", ...result.trace]
        };
    }
}


// ---------------------------------------------------------------------------
// 7. Demonstrate cache behavior
// ---------------------------------------------------------------------------

async function demonstrateCaching() {
    console.log("\n=== 3. Recursive resolution and caching ===");

    const infrastructure = new SimulatedDNSInfrastructure(
        authoritativeServer
    );

    const resolver = new RecursiveResolver(infrastructure);

    const first = await resolver.query(
        "example.com",
        recordTypes.A
    );

    console.log("First query:");
    console.log(first);

    const second = await resolver.query(
        "example.com",
        recordTypes.A
    );

    console.log("\nSecond query:");
    console.log(second);
}


// ---------------------------------------------------------------------------
// 8. CNAME resolution
// ---------------------------------------------------------------------------

async function demonstrateCNAME() {
    console.log("\n=== 4. CNAME resolution ===");

    const infrastructure = new SimulatedDNSInfrastructure(
        authoritativeServer
    );

    const resolver = new RecursiveResolver(infrastructure);

    const result = await resolver.query(
        "www.example.com",
        recordTypes.A
    );

    console.log(result);

    /*
    The requested type is A, but the authoritative server first returns:

        www.example.com. CNAME example.com.

    The resolver then resolves the target:

        example.com. A 93.184.216.34
    */
}


// ---------------------------------------------------------------------------
// 9. Negative caching
// ---------------------------------------------------------------------------

async function demonstrateNegativeCaching() {
    console.log("\n=== 5. Negative caching ===");

    const infrastructure = new SimulatedDNSInfrastructure(
        authoritativeServer
    );

    const resolver = new RecursiveResolver(infrastructure);

    const first = await resolver.query(
        "missing.example.com",
        recordTypes.A
    );

    const second = await resolver.query(
        "missing.example.com",
        recordTypes.A
    );

    console.log("First:", first);
    console.log("Second:", second);
}


// ---------------------------------------------------------------------------
// 10. Controlled clock for TTL testing
// ---------------------------------------------------------------------------

class FakeClock {
    constructor() {
        this.currentMilliseconds = 0;
    }

    now() {
        return this.currentMilliseconds;
    }

    advance(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            throw new Error("Time increment must be non-negative");
        }

        this.currentMilliseconds += seconds * 1000;
    }
}

async function demonstrateTTL() {
    console.log("\n=== 6. TTL expiration ===");

    const clock = new FakeClock();

    const infrastructure = new SimulatedDNSInfrastructure(
        authoritativeServer
    );

    const resolver = new RecursiveResolver(
        infrastructure,
        () => clock.now()
    );

    const first = await resolver.query(
        "example.com",
        recordTypes.A
    );

    console.log("First:", first.trace);

    const cached = await resolver.query(
        "example.com",
        recordTypes.A
    );

    console.log("Cached:", cached.trace);

    clock.advance(3601);

    const expired = await resolver.query(
        "example.com",
        recordTypes.A
    );

    console.log("After expiration:", expired.trace);
}


// ---------------------------------------------------------------------------
// 11. DNS records as resource-record sets
// ---------------------------------------------------------------------------

class RRSet {
    constructor(name, type) {
        this.name = normalizeName(name);
        this.type = type;
        this.records = [];
    }

    add(record) {
        if (
            normalizeName(record.name) !== this.name ||
            record.type !== this.type
        ) {
            throw new Error("Record does not belong to this RRset");
        }

        this.records.push(record);
    }

    values() {
        return this.records.map(record => record.value);
    }
}

const addresses = new RRSet(
    "api.example.com",
    recordTypes.A
);

addresses.add(
    createRecord("api.example.com", recordTypes.A, "192.0.2.10", 60)
);

addresses.add(
    createRecord("api.example.com", recordTypes.A, "192.0.2.11", 60)
);

addresses.add(
    createRecord("api.example.com", recordTypes.A, "192.0.2.12", 60)
);

console.log("\n=== 7. RRset ===");
console.log(addresses.values());


// ---------------------------------------------------------------------------
// 12. Simple DNS round-robin simulation
// ---------------------------------------------------------------------------

class RoundRobinPool {
    constructor(values) {
        if (!Array.isArray(values) || values.length === 0) {
            throw new Error("Round-robin pool requires values");
        }

        this.values = [...values];
        this.index = 0;
    }

    next() {
        const value = this.values[this.index];

        this.index = (
            this.index + 1
        ) % this.values.length;

        return value;
    }
}

const pool = new RoundRobinPool(addresses.values());

console.log("\nRound-robin sequence:");

for (let i = 0; i < 6; i++) {
    console.log(pool.next());
}


// ---------------------------------------------------------------------------
// 13. Forward and reverse naming
// ---------------------------------------------------------------------------

function reverseIPv4Name(address) {
    const parts = address.split(".");

    if (
        parts.length !== 4 ||
        parts.some(part => !/^\d+$/.test(part))
    ) {
        throw new Error("Invalid IPv4 address");
    }

    const numbers = parts.map(Number);

    if (numbers.some(number => number < 0 || number > 255)) {
        throw new Error("Invalid IPv4 address");
    }

    return `${numbers.reverse().join(".")}.in-addr.arpa.`;
}

console.log("\n=== 8. Reverse DNS ===");
console.log(reverseIPv4Name("192.0.2.25"));


// ---------------------------------------------------------------------------
// 14. DNS error classification
// ---------------------------------------------------------------------------

const dnsStatusDescriptions = Object.freeze({
    NOERROR: "Successful response",
    NXDOMAIN: "Name does not exist",
    SERVFAIL: "Server could not complete the query",
    REFUSED: "Server refused the operation",
    TIMEOUT: "No response before timeout"
});

function explainStatus(status) {
    return dnsStatusDescriptions[status] || "Unknown status";
}

console.log("\n=== 9. Status codes ===");

for (const status of Object.keys(dnsStatusDescriptions)) {
    console.log(
        `${status}: ${explainStatus(status)}`
    );
}


// ---------------------------------------------------------------------------
// 15. Retry policy
// ---------------------------------------------------------------------------

async function withRetries(operation, retryCount = 3) {
    if (!Number.isInteger(retryCount) || retryCount < 0) {
        throw new Error("retryCount must be non-negative");
    }

    let lastError;

    for (let attempt = 0; attempt <= retryCount; attempt++) {
        try {
            return await operation(attempt + 1);
        } catch (error) {
            lastError = error;

            if (attempt === retryCount) {
                break;
            }

            // Exponential backoff is represented by increasing delays.
            // Production systems usually apply jitter as well.
            await delay(5 * 2 ** attempt);
        }
    }

    throw lastError;
}

async function demonstrateRetries() {
    console.log("\n=== 10. Retry behavior ===");

    let attempts = 0;

    try {
        const result = await withRetries(async attempt => {
            attempts++;

            if (attempt < 3) {
                throw new Error("Simulated timeout");
            }

            return `Succeeded on attempt ${attempt}`;
        }, 4);

        console.log(result);
        console.log("Attempts:", attempts);
    } catch (error) {
        console.error("Final failure:", error.message);
    }
}


// ---------------------------------------------------------------------------
// 16. DNS message model
// ---------------------------------------------------------------------------

class DNSHeader {
    constructor({
        transactionId,
        recursionDesired = false,
        recursionAvailable = false,
        authoritativeAnswer = false,
        responseCode = "NOERROR"
    }) {
        this.transactionId = transactionId;
        this.recursionDesired = recursionDesired;
        this.recursionAvailable = recursionAvailable;
        this.authoritativeAnswer = authoritativeAnswer;
        this.responseCode = responseCode;
    }
}

class DNSMessage {
    constructor({
        header,
        questions = [],
        answers = [],
        authority = [],
        additional = []
    }) {
        this.header = header;
        this.questions = questions;
        this.answers = answers;
        this.authority = authority;
        this.additional = additional;
    }
}

const dnsQuery = new DNSMessage({
    header: new DNSHeader({
        transactionId: 0x1234,
        recursionDesired: true
    }),
    questions: [
        {
            name: normalizeName("www.example.com"),
            type: recordTypes.A
        }
    ]
});

const dnsResponse = new DNSMessage({
    header: new DNSHeader({
        transactionId: dnsQuery.header.transactionId,
        recursionDesired: true,
        recursionAvailable: true,
        authoritativeAnswer: true
    }),
    questions: dnsQuery.questions,
    answers: [
        createRecord(
            "www.example.com",
            recordTypes.A,
            "93.184.216.34",
            300
        )
    ]
});

console.log("\n=== 11. DNS message ===");
console.log("Query:", dnsQuery);
console.log("Response:", dnsResponse);


// ---------------------------------------------------------------------------
// 17. Split-horizon DNS
// ---------------------------------------------------------------------------

class SplitHorizonDNS {
    constructor() {
        this.internalRecords = new Map([
            ["portal.example.com.", "10.0.0.20"]
        ]);

        this.externalRecords = new Map([
            ["portal.example.com.", "203.0.113.20"]
        ]);
    }

    resolve(name, internalClient) {
        const normalized = normalizeName(name);

        const table = internalClient
            ? this.internalRecords
            : this.externalRecords;

        return table.get(normalized) || null;
    }
}

const splitDNS = new SplitHorizonDNS();

console.log("\n=== 12. Split-horizon DNS ===");
console.log(
    "Internal:",
    splitDNS.resolve("portal.example.com", true)
);
console.log(
    "External:",
    splitDNS.resolve("portal.example.com", false)
);


// ---------------------------------------------------------------------------
// 18. Security concepts
// ---------------------------------------------------------------------------

console.log("\n=== 13. DNS security concepts ===");

const securityControls = [
    "Randomized DNS transaction identifiers",
    "Randomized source ports",
    "Bailiwick checking",
    "DNSSEC validation",
    "Restricted recursive access",
    "Redundant authoritative servers",
    "Secure DNS-provider account access",
    "Monitoring of abnormal query patterns"
];

for (const control of securityControls) {
    console.log("-", control);
}

/*
DNSSEC is about authentication and integrity of DNS data.

DoT and DoH are about protecting DNS transport between endpoints.

These solve different problems:

    DNSSEC -> "Is this DNS data authentic?"
    DoT/DoH -> "Can someone observing this connection read the DNS traffic?"

Neither concept should be treated as a replacement for the other.
*/


// ---------------------------------------------------------------------------
// 19. Performance model
// ---------------------------------------------------------------------------

function estimateLookupLatency({
    cacheHit,
    rootLatency = 15,
    tldLatency = 20,
    authoritativeLatency = 25,
    localProcessing = 1
}) {
    if (cacheHit) {
        return localProcessing;
    }

    return (
        localProcessing +
        rootLatency +
        tldLatency +
        authoritativeLatency
    );
}

console.log("\n=== 14. Latency model ===");

console.log(
    "Cache hit:",
    estimateLookupLatency({ cacheHit: true }),
    "ms"
);

console.log(
    "Cache miss:",
    estimateLookupLatency({ cacheHit: false }),
    "ms"
);

/*
This is a simplified educational model.

Real latency depends on:
- resolver cache state
- network topology
- packet loss
- server selection
- RTT
- connection reuse
- transport protocol
- DNSSEC validation work
- CNAME chains
- retries
*/


// ---------------------------------------------------------------------------
// 20. Bounded cache with LRU behavior
// ---------------------------------------------------------------------------

class LRUCache {
    constructor(capacity) {
        if (!Number.isInteger(capacity) || capacity <= 0) {
            throw new Error("Capacity must be positive");
        }

        this.capacity = capacity;
        this.data = new Map();
    }

    get(key) {
        if (!this.data.has(key)) {
            return undefined;
        }

        const value = this.data.get(key);

        // Map insertion order makes this simple LRU implementation possible.
        this.data.delete(key);
        this.data.set(key, value);

        return value;
    }

    set(key, value) {
        if (this.data.has(key)) {
            this.data.delete(key);
        }

        this.data.set(key, value);

        if (this.data.size > this.capacity) {
            const oldestKey = this.data.keys().next().value;
            this.data.delete(oldestKey);
        }
    }

    keys() {
        return [...this.data.keys()];
    }
}

const lru = new LRUCache(2);

lru.set("a.example.", "192.0.2.1");
lru.set("b.example.", "192.0.2.2");

console.log("\n=== 15. Cache eviction ===");
console.log(lru.keys());

lru.get("a.example.");
lru.set("c.example.", "192.0.2.3");

console.log(lru.keys());


// ---------------------------------------------------------------------------
// 21. DNS architecture case study
// ---------------------------------------------------------------------------

class DNSApplicationClient {
    constructor(resolver) {
        this.resolver = resolver;
    }

    async connectToHost(hostname) {
        const result = await this.resolver.query(
            hostname,
            recordTypes.A
        );

        if (result.status !== "NOERROR") {
            throw new Error(
                `DNS resolution failed: ${result.status}`
            );
        }

        if (result.answers.length === 0) {
            throw new Error("DNS returned no addresses");
        }

        return {
            hostname: normalizeName(hostname),
            addresses: result.answers.map(record => record.value)
        };
    }
}

async function demonstrateApplicationLayer() {
    console.log("\n=== 16. Application-level DNS use ===");

    const infrastructure = new SimulatedDNSInfrastructure(
        authoritativeServer
    );

    const resolver = new RecursiveResolver(infrastructure);

    const client = new DNSApplicationClient(resolver);

    const destination = await client.connectToHost(
        "example.com"
    );

    console.log(destination);
}


// ---------------------------------------------------------------------------
// 22. Tests
// ---------------------------------------------------------------------------

async function runTests() {
    console.log("\n=== 17. Self-tests ===");

    console.assert(
        normalizeName("Example.COM") === "example.com.",
        "Normalization failed"
    );

    console.assert(
        exampleZone.query(
            "example.com",
            recordTypes.A
        )[0].value === "93.184.216.34",
        "A lookup failed"
    );

    console.assert(
        exampleZone.query(
            "www.example.com",
            recordTypes.CNAME
        )[0].value === "example.com.",
        "CNAME lookup failed"
    );

    const infrastructure = new SimulatedDNSInfrastructure(
        authoritativeServer
    );

    const resolver = new RecursiveResolver(infrastructure);

    const answer = await resolver.query(
        "www.example.com",
        recordTypes.A
    );

    console.assert(
        answer.status === "NOERROR",
        "CNAME resolution failed"
    );

    console.assert(
        answer.answers[0].value === "93.184.216.34",
        "Final CNAME target failed"
    );

    const missing = await resolver.query(
        "unknown.example.com",
        recordTypes.A
    );

    console.assert(
        missing.status === "NXDOMAIN",
        "NXDOMAIN test failed"
    );

    console.assert(
        reverseIPv4Name("192.0.2.1") ===
        "1.2.0.192.in-addr.arpa.",
        "Reverse DNS failed"
    );

    console.log("All tests passed.");
}


// ---------------------------------------------------------------------------
// 23. Run the complete asynchronous demonstration
// ---------------------------------------------------------------------------

async function main() {
    await demonstrateCaching();
    await demonstrateCNAME();
    await demonstrateNegativeCaching();
    await demonstrateTTL();
    await demonstrateRetries();
    await demonstrateApplicationLayer();
    await runTests();

    console.log("\n=== 18. Key distinctions ===");
    console.log("Authoritative DNS: serves authoritative zone data.");
    console.log("Recursive DNS: obtains answers on behalf of clients.");
    console.log("Iterative DNS: server returns the best information it has.");
    console.log("TTL: controls how long cached DNS data can be retained.");
    console.log("NXDOMAIN: queried name does not exist.");
    console.log("CNAME: aliases one name to another.");
    console.log("DNSSEC: authenticates DNS data.");
    console.log("DoT/DoH: protect DNS transport.");
}

main().catch(error => {
    console.error("Program failed:", error);
    process.exitCode = 1;
});
