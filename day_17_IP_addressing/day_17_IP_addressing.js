"use strict";

/*
 * IP Addressing: IPv4, IPv6, Public and Private IP Addresses
 * ============================================================
 *
 * This self-contained JavaScript file demonstrates:
 *
 * - IPv4 structure and binary representation
 * - IPv4 validation
 * - CIDR and subnet masks
 * - Network/broadcast/host calculations
 * - Private/public/special IPv4 addresses
 * - Longest-prefix route matching
 * - VLSM-style allocation
 * - IPv6 parsing, expansion and compression
 * - IPv6 address categories
 * - IPv6 prefix and subnet concepts
 * - Dual-stack design
 * - Validation and error handling
 * - Address-pool allocation
 * - Performance and security considerations
 *
 * No npm packages are required.
 *
 * Run with:
 *   node ip-addressing.js
 */

// ---------------------------------------------------------------------------
// 1. General utilities
// ---------------------------------------------------------------------------

function printSection(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function isInteger(value) {
    return Number.isInteger(value);
}


// ---------------------------------------------------------------------------
// 2. IPv4 parsing and representation
// ---------------------------------------------------------------------------

function parseIPv4(address) {
    if (typeof address !== "string") {
        throw new TypeError("IPv4 address must be a string.");
    }

    const parts = address.split(".");

    if (parts.length !== 4) {
        throw new Error("IPv4 address must contain exactly four octets.");
    }

    const octets = parts.map((part) => {
        if (!/^\d+$/.test(part)) {
            throw new Error(`Invalid IPv4 octet: ${part}`);
        }

        const value = Number(part);

        if (value < 0 || value > 255) {
            throw new Error(`IPv4 octet out of range: ${part}`);
        }

        return value;
    });

    return octets;
}

function ipv4ToUint32(address) {
    const [a, b, c, d] = parseIPv4(address);

    // JavaScript bitwise operations operate on signed 32-bit integers.
    // >>> 0 converts the result back to an unsigned 32-bit representation.
    return (
        (((a << 24) >>> 0) |
            (b << 16) |
            (c << 8) |
            d) >>>
        0
    );
}

function uint32ToIPv4(value) {
    if (!isInteger(value) || value < 0 || value > 0xffffffff) {
        throw new RangeError("Value must be an unsigned 32-bit integer.");
    }

    return [
        (value >>> 24) & 255,
        (value >>> 16) & 255,
        (value >>> 8) & 255,
        value & 255,
    ].join(".");
}

function ipv4ToBinary(address) {
    return ipv4ToUint32(address).toString(2).padStart(32, "0");
}

function binaryToIPv4(binary) {
    if (!/^[01]{32}$/.test(binary)) {
        throw new Error("Binary IPv4 form must contain exactly 32 bits.");
    }

    return uint32ToIPv4(Number.parseInt(binary, 2));
}

function demonstrateIPv4Representation() {
    printSection("1. IPv4 representation");

    const address = "192.168.10.25";
    const binary = ipv4ToBinary(address);

    console.log(`Address: ${address}`);
    console.log(`Binary : ${binary}`);
    console.log(`Round trip: ${binaryToIPv4(binary)}`);

    console.log("\nOctets:");
    parseIPv4(address).forEach((octet, index) => {
        console.log(
            `  Octet ${index + 1}: ${String(octet).padStart(3)} -> ${octet
                .toString(2)
                .padStart(8, "0")}`
        );
    });

    console.log("\nIPv4 = 32 bits = 4 octets × 8 bits.");
}


// ---------------------------------------------------------------------------
// 3. CIDR and subnet masks
// ---------------------------------------------------------------------------

function prefixToMask(prefix) {
    if (!isInteger(prefix) || prefix < 0 || prefix > 32) {
        throw new RangeError("IPv4 prefix must be between 0 and 32.");
    }

    if (prefix === 0) {
        return "0.0.0.0";
    }

    const mask = (0xffffffff << (32 - prefix)) >>> 0;
    return uint32ToIPv4(mask);
}

function parseCIDR(cidr) {
    const match = /^(.+)\/(\d+)$/.exec(cidr);

    if (!match) {
        throw new Error(`Invalid CIDR notation: ${cidr}`);
    }

    const address = match[1];
    const prefix = Number(match[2]);

    if (prefix < 0 || prefix > 32) {
        throw new Error("IPv4 prefix must be between 0 and 32.");
    }

    return {
        address,
        prefix,
        value: ipv4ToUint32(address),
    };
}

function subnetDetails(cidr) {
    const { prefix, value } = parseCIDR(cidr);

    const mask = prefixToMask(prefix);
    const maskValue = ipv4ToUint32(mask);
    const networkValue = (value & maskValue) >>> 0;

    const hostBits = 32 - prefix;
    const totalAddresses = 2 ** hostBits;
    const broadcastValue = (networkValue + totalAddresses - 1) >>> 0;

    let usableHosts;

    if (prefix <= 30) {
        usableHosts = totalAddresses - 2;
    } else if (prefix === 31) {
        usableHosts = 2;
    } else {
        usableHosts = 1;
    }

    return {
        cidr: `${uint32ToIPv4(networkValue)}/${prefix}`,
        prefix,
        mask,
        network: uint32ToIPv4(networkValue),
        broadcast: uint32ToIPv4(broadcastValue),
        firstHost:
            prefix <= 30
                ? uint32ToIPv4(networkValue + 1)
                : uint32ToIPv4(networkValue),
        lastHost:
            prefix <= 30
                ? uint32ToIPv4(broadcastValue - 1)
                : uint32ToIPv4(broadcastValue),
        totalAddresses,
        usableHosts,
    };
}

function demonstrateCIDR() {
    printSection("2. CIDR and IPv4 subnet calculation");

    const examples = [
        "192.168.10.25/24",
        "10.20.30.40/26",
        "172.16.8.15/28",
        "192.0.2.0/31",
        "203.0.113.17/32",
    ];

    for (const cidr of examples) {
        const result = subnetDetails(cidr);

        console.log(`\nCIDR: ${cidr}`);
        console.log(`  Network       : ${result.cidr}`);
        console.log(`  Mask          : ${result.mask}`);
        console.log(`  Broadcast     : ${result.broadcast}`);
        console.log(`  Total         : ${result.totalAddresses}`);
        console.log(`  Usable hosts  : ${result.usableHosts}`);
        console.log(`  First host    : ${result.firstHost}`);
        console.log(`  Last host     : ${result.lastHost}`);
    }
}


// ---------------------------------------------------------------------------
// 4. IPv4 classification
// ---------------------------------------------------------------------------

function ipv4InCIDR(address, cidr) {
    const { prefix, value } = parseCIDR(cidr);

    const mask =
        prefix === 0 ? 0 : ((0xffffffff << (32 - prefix)) >>> 0);

    return (ipv4ToUint32(address) & mask) === (value & mask);
}

function classifyIPv4(address) {
    const value = ipv4ToUint32(address);
    const labels = [];

    if (ipv4InCIDR(address, "10.0.0.0/8")) {
        labels.push("private");
    }

    if (ipv4InCIDR(address, "172.16.0.0/12")) {
        labels.push("private");
    }

    if (ipv4InCIDR(address, "192.168.0.0/16")) {
        labels.push("private");
    }

    if (ipv4InCIDR(address, "127.0.0.0/8")) {
        labels.push("loopback");
    }

    if (ipv4InCIDR(address, "169.254.0.0/16")) {
        labels.push("link-local");
    }

    if (ipv4InCIDR(address, "224.0.0.0/4")) {
        labels.push("multicast");
    }

    if (address === "0.0.0.0") {
        labels.push("unspecified");
    }

    if (address === "255.255.255.255") {
        labels.push("limited broadcast");
    }

    // The ordinary global/public classification is deliberately based on
    // exclusion of common special ranges for this educational example.
    if (labels.length === 0) {
        labels.push("ordinary/global-address candidate");
    }

    return labels;
}

function demonstrateIPv4Categories() {
    printSection("3. IPv4 address categories");

    const examples = [
        "10.10.10.10",
        "172.16.20.30",
        "192.168.1.100",
        "8.8.8.8",
        "127.0.0.1",
        "169.254.1.20",
        "224.0.0.1",
        "0.0.0.0",
        "255.255.255.255",
    ];

    for (const address of examples) {
        console.log(
            `  ${address.padEnd(15)} -> ${classifyIPv4(address).join(", ")}`
        );
    }

    console.log("\nRFC1918 private ranges:");
    console.log("  10.0.0.0/8");
    console.log("  172.16.0.0/12");
    console.log("  192.168.0.0/16");
}


// ---------------------------------------------------------------------------
// 5. Host sizing
// ---------------------------------------------------------------------------

function smallestPrefixForHosts(requiredHosts) {
    if (!isInteger(requiredHosts) || requiredHosts < 1) {
        throw new RangeError("Host requirement must be a positive integer.");
    }

    for (let prefix = 30; prefix >= 0; prefix--) {
        const total = 2 ** (32 - prefix);
        const usable = total - 2;

        if (usable >= requiredHosts) {
            return prefix;
        }
    }

    throw new Error("Requirement cannot fit into an IPv4 subnet.");
}

function demonstrateHostSizing() {
    printSection("4. IPv4 host-capacity calculations");

    for (const hosts of [2, 6, 10, 14, 30, 50, 100, 200, 500, 1000]) {
        const prefix = smallestPrefixForHosts(hosts);
        const total = 2 ** (32 - prefix);

        console.log(
            `  ${String(hosts).padStart(4)} hosts -> /${String(prefix).padEnd(
                2
            )} -> ${total - 2} traditional usable hosts`
        );
    }
}


// ---------------------------------------------------------------------------
// 6. VLSM allocator
// ---------------------------------------------------------------------------

function allocateVLSM(baseCIDR, requirements) {
    const base = subnetDetails(baseCIDR);

    const baseStart = ipv4ToUint32(base.network);
    const baseEnd = ipv4ToUint32(base.broadcast);

    const sorted = [...requirements].sort((a, b) => b.hosts - a.hosts);

    let cursor = baseStart;
    const allocations = [];

    for (const requirement of sorted) {
        const prefix = smallestPrefixForHosts(requirement.hosts);
        const size = 2 ** (32 - prefix);

        // Align cursor to the boundary required by the subnet size.
        const aligned = Math.ceil(cursor / size) * size;

        if (aligned + size - 1 > baseEnd) {
            throw new Error(
                `Insufficient space for ${requirement.name} (${requirement.hosts} hosts).`
            );
        }

        const subnet = subnetDetails(`${uint32ToIPv4(aligned)}/${prefix}`);

        allocations.push({
            name: requirement.name,
            requestedHosts: requirement.hosts,
            subnet: subnet.cidr,
            usableHosts: subnet.usableHosts,
        });

        cursor = aligned + size;
    }

    return allocations;
}

function demonstrateVLSM() {
    printSection("5. VLSM-style IPv4 allocation");

    const requirements = [
        { name: "Engineering", hosts: 100 },
        { name: "Operations", hosts: 50 },
        { name: "Security", hosts: 25 },
        { name: "Management", hosts: 10 },
        { name: "Point-to-point", hosts: 2 },
    ];

    try {
        const allocations = allocateVLSM("10.50.0.0/24", requirements);

        for (const allocation of allocations) {
            console.log(
                `  ${allocation.name.padEnd(20)} ` +
                `${allocation.subnet.padEnd(16)} ` +
                `requested=${String(allocation.requestedHosts).padEnd(4)} ` +
                `usable=${allocation.usableHosts}`
            );
        }
    } catch (error) {
        console.log(`Allocation failed: ${error.message}`);
    }
}


// ---------------------------------------------------------------------------
// 7. Longest-prefix routing
// ---------------------------------------------------------------------------

function longestPrefixMatch(destination, routes) {
    const matchingRoutes = routes.filter((route) =>
        ipv4InCIDR(destination, route.network)
    );

    if (matchingRoutes.length === 0) {
        return null;
    }

    return matchingRoutes.reduce((best, current) => {
        const bestPrefix = Number(best.network.split("/")[1]);
        const currentPrefix = Number(current.network.split("/")[1]);

        return currentPrefix > bestPrefix ? current : best;
    });
}

function demonstrateRouting() {
    printSection("6. Longest-prefix route matching");

    const routes = [
        { network: "0.0.0.0/0", nextHop: "Internet gateway" },
        { network: "10.0.0.0/8", nextHop: "Router A" },
        { network: "10.20.0.0/16", nextHop: "Router B" },
        { network: "10.20.30.0/24", nextHop: "Router C" },
        { network: "10.20.30.128/25", nextHop: "Router D" },
    ];

    for (const destination of [
        "8.8.8.8",
        "10.5.6.7",
        "10.20.10.5",
        "10.20.30.10",
        "10.20.30.200",
    ]) {
        const route = longestPrefixMatch(destination, routes);

        console.log(
            `  ${destination.padEnd(15)} -> ` +
            `${route ? route.network : "no route"} -> ` +
            `${route ? route.nextHop : "drop"}`
        );
    }

    console.log(
        "\nA /25 is more specific than /24, /16, /8 and /0."
    );
}


// ---------------------------------------------------------------------------
// 8. IPv6 parsing and formatting
// ---------------------------------------------------------------------------

function parseIPv6(address) {
    if (typeof address !== "string" || address.length === 0) {
        throw new Error("IPv6 address must be a non-empty string.");
    }

    if (address.includes(".")) {
        throw new Error(
            "This educational parser expects pure hexadecimal IPv6 notation."
        );
    }

    const doubleColonCount = (address.match(/::/g) || []).length;

    if (doubleColonCount > 1) {
        throw new Error("An IPv6 address may contain :: at most once.");
    }

    let groups;

    if (address.includes("::")) {
        const [left, right] = address.split("::");
        const leftGroups = left ? left.split(":") : [];
        const rightGroups = right ? right.split(":") : [];

        if (
            leftGroups.some((group) => !/^[0-9a-fA-F]{1,4}$/.test(group)) ||
            rightGroups.some((group) => !/^[0-9a-fA-F]{1,4}$/.test(group))
        ) {
            throw new Error("Invalid hexadecimal IPv6 group.");
        }

        const missing = 8 - (leftGroups.length + rightGroups.length);

        if (missing <= 0) {
            throw new Error(
                ":: must replace at least one complete zero group."
            );
        }

        groups = [
            ...leftGroups,
            ...Array(missing).fill("0"),
            ...rightGroups,
        ];
    } else {
        groups = address.split(":");

        if (groups.length !== 8) {
            throw new Error(
                "An uncompressed IPv6 address must contain eight groups."
            );
        }

        if (groups.some((group) => !/^[0-9a-fA-F]{1,4}$/.test(group))) {
            throw new Error("Invalid hexadecimal IPv6 group.");
        }
    }

    return groups.map((group) => Number.parseInt(group, 16));
}

function expandIPv6(address) {
    return parseIPv6(address)
        .map((group) => group.toString(16).padStart(4, "0"))
        .join(":");
}

function compressIPv6(address) {
    const groups = parseIPv6(address);

    let bestStart = -1;
    let bestLength = 0;
    let currentStart = -1;

    for (let i = 0; i <= groups.length; i++) {
        if (i < groups.length && groups[i] === 0) {
            if (currentStart === -1) {
                currentStart = i;
            }
        } else if (currentStart !== -1) {
            const currentLength = i - currentStart;

            if (currentLength > bestLength) {
                bestStart = currentStart;
                bestLength = currentLength;
            }

            currentStart = -1;
        }
    }

    // RFC-style canonical compression does not replace a single zero group
    // with :: when ordinary omission is sufficient.
    if (bestLength < 2) {
        bestStart = -1;
    }

    const groupsAsHex = groups.map((group) => group.toString(16));

    if (bestStart === -1) {
        return groupsAsHex.join(":");
    }

    const left = groupsAsHex.slice(0, bestStart).join(":");
    const right = groupsAsHex
        .slice(bestStart + bestLength)
        .join(":");

    if (!left && !right) {
        return "::";
    }

    if (!left) {
        return `::${right}`;
    }

    if (!right) {
        return `${left}::`;
    }

    return `${left}::${right}`;
}

function demonstrateIPv6Representation() {
    printSection("7. IPv6 representation");

    const examples = [
        "2001:0db8:0000:0000:0000:ff00:0042:8329",
        "2001:db8::1",
        "fe80::021c:7eff:fe12:3456",
    ];

    for (const address of examples) {
        console.log(`\nInput    : ${address}`);
        console.log(`Expanded : ${expandIPv6(address)}`);
        console.log(`Compressed: ${compressIPv6(address)}`);
    }

    console.log("\nIPv6 = 128 bits = eight groups × 16 bits.");
}


// ---------------------------------------------------------------------------
// 9. IPv6 classification
// ---------------------------------------------------------------------------

function ipv6BigInt(address) {
    const groups = parseIPv6(address);
    let value = 0n;

    for (const group of groups) {
        value = (value << 16n) | BigInt(group);
    }

    return value;
}

function ipv6InCIDR(address, cidr) {
    const match = /^(.+)\/(\d+)$/.exec(cidr);

    if (!match) {
        throw new Error(`Invalid IPv6 CIDR: ${cidr}`);
    }

    const prefix = Number(match[2]);

    if (prefix < 0 || prefix > 128) {
        throw new Error("IPv6 prefix must be between 0 and 128.");
    }

    const value = ipv6BigInt(address);
    const networkValue = ipv6BigInt(match[1]);

    const mask =
        prefix === 0
            ? 0n
            : ((2n ** 128n - 1n) << BigInt(128 - prefix)) &
              (2n ** 128n - 1n);

    return (value & mask) === (networkValue & mask);
}

function classifyIPv6(address) {
    const labels = [];

    if (ipv6InCIDR(address, "fe80::/10")) {
        labels.push("link-local");
    }

    if (ipv6InCIDR(address, "fc00::/7")) {
        labels.push("unique-local");
    }

    if (ipv6InCIDR(address, "ff00::/8")) {
        labels.push("multicast");
    }

    if (ipv6InCIDR(address, "::1/128")) {
        labels.push("loopback");
    }

    if (address === "::") {
        labels.push("unspecified");
    }

    if (ipv6InCIDR(address, "2000::/3")) {
        labels.push("global-unicast-range");
    }

    return labels.length ? labels : ["ordinary/special-purpose classification not listed"];
}

function demonstrateIPv6Categories() {
    printSection("8. IPv6 address categories");

    const examples = [
        "2001:db8::1",
        "fe80::1",
        "fc00::1",
        "::1",
        "::",
        "ff02::1",
    ];

    for (const address of examples) {
        console.log(
            `  ${address.padEnd(20)} -> ${classifyIPv6(address).join(", ")}`
        );
    }

    console.log("\nImportant ranges:");
    console.log("  2000::/3  Global unicast range");
    console.log("  fe80::/10 Link-local");
    console.log("  fc00::/7  Unique-local");
    console.log("  ff00::/8  Multicast");
    console.log("  ::1/128   Loopback");
    console.log("  ::/128    Unspecified");
}


// ---------------------------------------------------------------------------
// 10. IPv6 prefix mathematics
// ---------------------------------------------------------------------------

function ipv6AddressCount(prefix) {
    if (!isInteger(prefix) || prefix < 0 || prefix > 128) {
        throw new RangeError("IPv6 prefix must be between 0 and 128.");
    }

    return 2n ** BigInt(128 - prefix);
}

function demonstrateIPv6PrefixMath() {
    printSection("9. IPv6 prefix mathematics");

    for (const prefix of [32, 48, 56, 64, 80, 128]) {
        console.log(
            `  /${String(prefix).padEnd(3)} -> ${ipv6AddressCount(
                prefix
            ).toString()} addresses`
        );
    }

    console.log(
        "\nA /48 contains 2^80 addresses. A /64 contains 2^64 addresses."
    );

    console.log(
        "A /48 can be subdivided into 65,536 independent /64 networks."
    );
}


// ---------------------------------------------------------------------------
// 11. IPv6 subnet enumeration without materializing huge collections
// ---------------------------------------------------------------------------

function incrementIPv6Prefix(prefixAddress, parentPrefix, childPrefix, index) {
    if (childPrefix < parentPrefix || childPrefix > 128) {
        throw new RangeError("Invalid parent/child prefix relationship.");
    }

    const parentValue = ipv6BigInt(prefixAddress);
    const additionalBits = childPrefix - parentPrefix;
    const maxChildren = 2n ** BigInt(additionalBits);

    if (BigInt(index) < 0n || BigInt(index) >= maxChildren) {
        throw new RangeError("Child subnet index is outside the prefix.");
    }

    const shifted = BigInt(index) << BigInt(128 - childPrefix);
    const result = parentValue | shifted;

    const groups = [];

    for (let i = 0; i < 8; i++) {
        const shift = BigInt((7 - i) * 16);
        groups.push(Number((result >> shift) & 0xffffn));
    }

    return (
        groups
            .map((group) => group.toString(16).padStart(4, "0"))
            .join(":")
    );
}

function demonstrateIPv6SubnetGeneration() {
    printSection("10. IPv6 subnet generation");

    const parent = "2001:db8:1000::";
    const parentPrefix = 48;
    const childPrefix = 52;

    console.log(`Parent: ${compressIPv6(parent)}/${parentPrefix}`);
    console.log(`Child prefix: /${childPrefix}`);

    for (let index = 0; index < 5; index++) {
        const child = incrementIPv6Prefix(
            parent,
            parentPrefix,
            childPrefix,
            index
        );

        console.log(`  ${compressIPv6(child)}/${childPrefix}`);
    }

    console.log(
        "\nThe implementation generates only requested subnets instead of "
        "creating an array containing every possible IPv6 address."
    );
}


// ---------------------------------------------------------------------------
// 12. Address pool
// ---------------------------------------------------------------------------

class IPv4AddressPool {
    constructor(cidr) {
        const details = subnetDetails(cidr);

        if (details.prefix > 30) {
            throw new Error("This pool requires a conventional LAN subnet.");
        }

        this.details = details;
        this.nextValue = ipv4ToUint32(details.firstHost);
        this.lastValue = ipv4ToUint32(details.lastHost);
        this.allocations = new Map();
    }

    allocate(name) {
        if (this.allocations.has(name)) {
            throw new Error(`Device name already allocated: ${name}`);
        }

        if (this.nextValue > this.lastValue) {
            throw new Error("Address pool exhausted.");
        }

        const address = uint32ToIPv4(this.nextValue);
        this.nextValue += 1;

        const allocation = {
            name,
            address,
            subnet: this.details.cidr,
        };

        this.allocations.set(name, allocation);
        return allocation;
    }
}

function demonstrateAddressPool() {
    printSection("11. IPv4 address-pool allocation");

    const pool = new IPv4AddressPool("192.168.100.0/29");

    const devices = [
        "router",
        "database",
        "application-server",
        "monitoring",
        "developer-laptop",
        "printer",
        "extra-device",
    ];

    for (const device of devices) {
        try {
            const allocation = pool.allocate(device);
            console.log(
                `  ${device.padEnd(22)} -> ${allocation.address}`
            );
        } catch (error) {
            console.log(
                `  ${device.padEnd(22)} -> FAILED: ${error.message}`
            );
        }
    }
}


// ---------------------------------------------------------------------------
// 13. Validation and edge cases
// ---------------------------------------------------------------------------

function demonstrateValidation() {
    printSection("12. Validation and edge cases");

    const ipv4Inputs = [
        "192.168.1.1",
        "192.168.1.256",
        "192.168.1",
        "hello",
        "",
        "0.0.0.0",
        "255.255.255.255",
    ];

    for (const input of ipv4Inputs) {
        try {
            parseIPv4(input);
            console.log(`  IPv4 ${JSON.stringify(input)} -> valid`);
        } catch (error) {
            console.log(
                `  IPv4 ${JSON.stringify(input)} -> invalid: ${error.message}`
            );
        }
    }

    const ipv6Inputs = [
        "::1",
        "2001:db8::1",
        "2001:db8:0:0:0:0:0:1",
        "2001:db8::1::2",
        "2001:db8:0:0:0:0:0",
        "gggg::1",
    ];

    for (const input of ipv6Inputs) {
        try {
            parseIPv6(input);
            console.log(`  IPv6 ${JSON.stringify(input)} -> valid`);
        } catch (error) {
            console.log(
                `  IPv6 ${JSON.stringify(input)} -> invalid: ${error.message}`
            );
        }
    }
}


// ---------------------------------------------------------------------------
// 14. DNS, NAT and dual-stack concepts
// ---------------------------------------------------------------------------

function demonstrateArchitecture() {
    printSection("13. DNS, NAT and dual-stack architecture");

    console.log("DNS:");
    console.log("  A records can return IPv4 addresses.");
    console.log("  AAAA records can return IPv6 addresses.");
    console.log("  DNS provides naming; it does not perform packet routing.");

    console.log("\nExample host:");
    console.log("  Name : application.example");
    console.log("  A    : 192.168.10.20");
    console.log("  AAAA : 2001:db8:10:20::20");

    console.log("\nPrivate IPv4 + NAT:");
    console.log("  Laptop       192.168.1.20");
    console.log("  Router LAN   192.168.1.1");
    console.log("  Router WAN   public IPv4");
    console.log("  Multiple private hosts may share the external IPv4 using PAT.");

    console.log("\nDual stack:");
    console.log("  A system can simultaneously have IPv4 and IPv6 connectivity.");
    console.log("  Security policy must account for both protocols.");
}


// ---------------------------------------------------------------------------
// 15. Security and performance
// ---------------------------------------------------------------------------

function demonstrateSecurityAndPerformance() {
    printSection("14. Security and performance");

    console.log("Security considerations:");
    [
        "Private IP addresses are not equivalent to encryption.",
        "NAT is not a substitute for firewall policy.",
        "IPv4 and IPv6 should both receive explicit security controls.",
        "Ingress and egress filtering can reduce spoofing opportunities.",
        "Network segmentation limits unnecessary reachability.",
        "Logging should preserve enough addressing context for incident analysis.",
    ].forEach((item) => console.log(`  - ${item}`));

    console.log("\nPerformance considerations:");
    [
        "IPv4 address arithmetic fits naturally in 32-bit integers.",
        "IPv6 arithmetic requires 128-bit-capable representations.",
        "JavaScript BigInt is useful for IPv6 calculations.",
        "Huge IPv6 address spaces should not be enumerated unnecessarily.",
        "Large routing tables benefit from optimized prefix lookup structures.",
    ].forEach((item) => console.log(`  - ${item}`));
}


// ---------------------------------------------------------------------------
// 16. Automated tests
// ---------------------------------------------------------------------------

function runTests() {
    printSection("15. Automated tests");

    assert(
        ipv4ToBinary("192.168.1.1") ===
            "11000000101010000000000100000001",
        "IPv4 binary conversion"
    );

    assert(
        binaryToIPv4("11000000101010000000000100000001") ===
            "192.168.1.1",
        "Binary-to-IPv4 conversion"
    );

    assert(
        prefixToMask(24) === "255.255.255.0",
        "Prefix-to-mask conversion"
    );

    const subnet = subnetDetails("192.168.10.25/24");

    assert(subnet.network === "192.168.10.0", "Network calculation");
    assert(subnet.broadcast === "192.168.10.255", "Broadcast calculation");
    assert(subnet.usableHosts === 254, "Usable host calculation");

    assert(
        ipv4InCIDR("192.168.10.20", "192.168.10.0/24"),
        "IPv4 membership"
    );

    assert(
        !ipv4InCIDR("192.168.11.20", "192.168.10.0/24"),
        "IPv4 non-membership"
    );

    assert(
        compressIPv6("2001:0db8:0000:0000:0000:0000:0000:0001") ===
            "2001:db8::1",
        "IPv6 compression"
    );

    assert(
        expandIPv6("::1") ===
            "0000:0000:0000:0000:0000:0000:0000:0001",
        "IPv6 expansion"
    );

    assert(
        ipv6InCIDR("fe80::1", "fe80::/10"),
        "IPv6 link-local membership"
    );

    assert(
        ipv6AddressCount(64) === 18446744073709551616n,
        "IPv6 /64 size"
    );

    const routes = [
        { network: "10.0.0.0/8", nextHop: "A" },
        { network: "10.1.0.0/16", nextHop: "B" },
        { network: "10.1.2.0/24", nextHop: "C" },
    ];

    assert(
        longestPrefixMatch("10.1.2.5", routes).nextHop === "C",
        "Longest-prefix matching"
    );

    console.log("All tests passed.");
}


// ---------------------------------------------------------------------------
// 17. Main execution
// ---------------------------------------------------------------------------

function main() {
    console.log("=".repeat(78));
    console.log("IP ADDRESSING STUDY PROGRAM");
    console.log("IPv4, IPv6, Public and Private IP Addresses");
    console.log("=".repeat(78));

    demonstrateIPv4Representation();
    demonstrateCIDR();
    demonstrateIPv4Categories();
    demonstrateHostSizing();
    demonstrateVLSM();
    demonstrateRouting();
    demonstrateIPv6Representation();
    demonstrateIPv6Categories();
    demonstrateIPv6PrefixMath();
    demonstrateIPv6SubnetGeneration();
    demonstrateAddressPool();
    demonstrateValidation();
    demonstrateArchitecture();
    demonstrateSecurityAndPerformance();
    runTests();

    printSection("Program complete");
    console.log(
        "The program demonstrated address representation, subnetting, " +
        "classification, routing, IPv6 prefix mathematics, allocation, " +
        "validation and security considerations."
    );
}

main();
