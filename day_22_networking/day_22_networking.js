/*
 * HTTPS & TLS: Encryption, Certificates, and Secure Communication
 *
 * This file uses Node.js built-in modules to demonstrate:
 * - networking fundamentals
 * - hashing and HMAC
 * - secure randomness
 * - authenticated encryption
 * - key derivation
 * - certificate inspection
 * - hostname verification concepts
 * - TLS client configuration
 * - HTTPS requests
 * - certificate fingerprints
 * - HTTP security headers
 * - TLS failure handling
 *
 * Run with:
 *   node https_tls_study.js
 */

"use strict";

const https = require("https");
const crypto = require("crypto");
const tls = require("tls");
const os = require("os");

// ============================================================================
// 1. Networking and HTTPS fundamentals
// ============================================================================

function networkingFundamentals() {
    console.log("\n=== 1. NETWORKING FUNDAMENTALS ===");

    const layers = [
        ["HTTP", "Application protocol for web requests and responses."],
        ["TLS", "Security protocol providing confidentiality, integrity, and authentication."],
        ["TCP", "Reliable transport protocol commonly used by HTTPS."],
        ["IP", "Network-layer addressing and packet delivery."],
    ];

    for (const [name, description] of layers) {
        console.log(`${name.padEnd(8)} -> ${description}`);
    }

    console.log("\nHTTPS is conceptually HTTP carried through a TLS-protected connection.");
}

// ============================================================================
// 2. Encoding, hashing, and encryption
// ============================================================================

function encodingAndHashing() {
    console.log("\n=== 2. ENCODING AND HASHING ===");

    const message = Buffer.from("Sensitive HTTP request");

    const base64 = message.toString("base64");
    const digest = crypto.createHash("sha256").update(message).digest("hex");

    console.log("Original :", message.toString());
    console.log("Base64   :", base64);
    console.log("SHA-256  :", digest);

    console.log(
        "\nBase64 is encoding, not encryption. " +
        "Anyone can reverse it without a secret."
    );
}

// ============================================================================
// 3. Secure random values
// ============================================================================

function secureRandomness() {
    console.log("\n=== 3. SECURE RANDOMNESS ===");

    const sessionToken = crypto.randomBytes(32).toString("base64url");
    const nonce = crypto.randomBytes(12);

    console.log("Session token:", sessionToken);
    console.log("Nonce:", nonce.toString("hex"));

    /*
     * crypto.randomBytes() obtains cryptographically strong random bytes.
     * Math.random() must not be used to generate passwords, keys, tokens,
     * session identifiers, or cryptographic nonces.
     */
}

// ============================================================================
// 4. HMAC
// ============================================================================

function hmacDemo() {
    console.log("\n=== 4. HMAC ===");

    const secret = Buffer.from("shared-secret");
    const message = Buffer.from("GET /account HTTP/1.1");

    const mac = crypto
        .createHmac("sha256", secret)
        .update(message)
        .digest("hex");

    const changedMac = crypto
        .createHmac("sha256", secret)
        .update("GET /admin HTTP/1.1")
        .digest("hex");

    console.log("Original HMAC:", mac);
    console.log("Changed HMAC :", changedMac);
}

// ============================================================================
// 5. Authenticated encryption using AES-256-GCM
// ============================================================================

function encryptAESGCM(plaintext, key, nonce, additionalData = Buffer.alloc(0)) {
    const cipher = crypto.createCipheriv("aes-256-gcm", key, nonce);

    if (additionalData.length > 0) {
        cipher.setAAD(additionalData);
    }

    const ciphertext = Buffer.concat([
        cipher.update(plaintext),
        cipher.final(),
    ]);

    const authenticationTag = cipher.getAuthTag();

    return {
        ciphertext,
        authenticationTag,
    };
}

function decryptAESGCM(
    ciphertext,
    key,
    nonce,
    authenticationTag,
    additionalData = Buffer.alloc(0)
) {
    const decipher = crypto.createDecipheriv("aes-256-gcm", key, nonce);

    if (additionalData.length > 0) {
        decipher.setAAD(additionalData);
    }

    decipher.setAuthTag(authenticationTag);

    return Buffer.concat([
        decipher.update(ciphertext),
        decipher.final(),
    ]);
}

function authenticatedEncryptionDemo() {
    console.log("\n=== 5. AUTHENTICATED ENCRYPTION ===");

    const key = crypto.randomBytes(32);
    const nonce = crypto.randomBytes(12);
    const aad = Buffer.from("content-type: application/json");
    const plaintext = Buffer.from(
        JSON.stringify({
            user: "alice",
            role: "member",
        })
    );

    const encrypted = encryptAESGCM(plaintext, key, nonce, aad);

    console.log("Ciphertext:", encrypted.ciphertext.toString("hex"));
    console.log("Auth tag  :", encrypted.authenticationTag.toString("hex"));

    const recovered = decryptAESGCM(
        encrypted.ciphertext,
        key,
        nonce,
        encrypted.authenticationTag,
        aad
    );

    console.log("Recovered :", recovered.toString());

    const tampered = Buffer.from(encrypted.ciphertext);
    tampered[0] ^= 0x01;

    try {
        decryptAESGCM(
            tampered,
            key,
            nonce,
            encrypted.authenticationTag,
            aad
        );
    } catch (error) {
        console.log("Tampering rejected:", error.message);
    }
}

// ============================================================================
// 6. HKDF
// ============================================================================

function hkdfDemo() {
    console.log("\n=== 6. HKDF KEY DERIVATION ===");

    const sharedSecret = crypto.randomBytes(32);
    const salt = crypto.randomBytes(32);

    const applicationKey = crypto.hkdfSync(
        "sha256",
        sharedSecret,
        salt,
        Buffer.from("TLS application traffic key"),
        32
    );

    console.log(
        "Derived key:",
        Buffer.from(applicationKey).toString("hex")
    );

    /*
     * TLS 1.3 uses HKDF to derive a sequence of traffic secrets and keys
     * instead of using one static key for an entire connection.
     */
}

// ============================================================================
// 7. Diffie-Hellman demonstration
// ============================================================================

function diffieHellmanDemo() {
    console.log("\n=== 7. DIFFIE-HELLMAN KEY AGREEMENT ===");

    const prime = 23n;
    const generator = 5n;

    const alicePrivate = 6n;
    const bobPrivate = 15n;

    const modPow = (base, exponent, modulus) => {
        let result = 1n;
        let current = base % modulus;
        let power = exponent;

        while (power > 0n) {
            if (power % 2n === 1n) {
                result = (result * current) % modulus;
            }

            current = (current * current) % modulus;
            power /= 2n;
        }

        return result;
    };

    const alicePublic = modPow(generator, alicePrivate, prime);
    const bobPublic = modPow(generator, bobPrivate, prime);

    const aliceShared = modPow(bobPublic, alicePrivate, prime);
    const bobShared = modPow(alicePublic, bobPrivate, prime);

    console.log("Alice public:", alicePublic.toString());
    console.log("Bob public  :", bobPublic.toString());
    console.log("Alice shared:", aliceShared.toString());
    console.log("Bob shared  :", bobShared.toString());
    console.log("Equal:", aliceShared === bobShared);

    console.log(
        "\nThis uses tiny educational numbers. Real TLS uses secure standardized groups."
    );
}

// ============================================================================
// 8. Certificate and hostname concepts
// ============================================================================

function wildcardMatches(pattern, hostname) {
    pattern = pattern.toLowerCase().replace(/\.$/, "");
    hostname = hostname.toLowerCase().replace(/\.$/, "");

    if (pattern === hostname) {
        return true;
    }

    if (!pattern.startsWith("*.")) {
        return false;
    }

    const suffix = pattern.slice(1);

    return (
        hostname.endsWith(suffix) &&
        hostname.split(".").length === pattern.split(".").length
    );
}

function hostnameVerificationDemo() {
    console.log("\n=== 8. HOSTNAME VERIFICATION ===");

    const certificateNames = [
        "example.com",
        "*.secure.example.com",
    ];

    const tests = [
        "example.com",
        "www.example.com",
        "api.secure.example.com",
        "a.b.secure.example.com",
        "evil.example.net",
    ];

    for (const hostname of tests) {
        const valid = certificateNames.some(
            name => wildcardMatches(name, hostname)
        );

        console.log(`${hostname.padEnd(32)} -> ${valid}`);
    }
}

// ============================================================================
// 9. TLS runtime information
// ============================================================================

function runtimeTLSInformation() {
    console.log("\n=== 9. NODE.JS TLS RUNTIME ===");

    console.log("Node.js:", process.version);
    console.log("OpenSSL:", process.versions.openssl);
    console.log("Platform:", os.platform());

    console.log(
        "Default minimum TLS version:",
        tls.DEFAULT_MIN_VERSION
    );

    console.log(
        "Default maximum TLS version:",
        tls.DEFAULT_MAX_VERSION
    );
}

// ============================================================================
// 10. Secure HTTPS request
// ============================================================================

function httpsRequest(hostname = "example.com") {
    console.log("\n=== 10. HTTPS REQUEST ===");

    return new Promise((resolve) => {
        const request = https.request(
            {
                hostname,
                port: 443,
                path: "/",
                method: "GET",

                /*
                 * Node's HTTPS client verifies certificates by default.
                 * rejectUnauthorized should remain true in normal production
                 * client configurations.
                 */
                rejectUnauthorized: true,

                minVersion: "TLSv1.2",

                headers: {
                    "User-Agent": "HTTPS-TLS-study-client/1.0",
                    "Accept": "text/html",
                },
            },
            response => {
                const chunks = [];

                response.on("data", chunk => {
                    chunks.push(chunk);
                });

                response.on("end", () => {
                    const body = Buffer.concat(chunks);

                    console.log("Status:", response.statusCode);
                    console.log(
                        "Negotiated TLS:",
                        response.socket.getProtocol()
                    );
                    console.log(
                        "Cipher:",
                        response.socket.getCipher().name
                    );
                    console.log(
                        "Certificate authorized:",
                        response.socket.authorized
                    );

                    console.log("Security headers:");

                    for (const header of [
                        "strict-transport-security",
                        "content-security-policy",
                        "x-content-type-options",
                    ]) {
                        console.log(
                            `  ${header}:`,
                            response.headers[header] ?? "(missing)"
                        );
                    }

                    console.log(
                        "\nFirst response bytes:",
                        body.toString("utf8", 0, 500)
                    );

                    resolve();
                });
            }
        );

        request.setTimeout(5000, () => {
            request.destroy(new Error("HTTPS request timed out."));
        });

        request.on("error", error => {
            console.log("HTTPS request failed:", error.message);
            resolve();
        });

        request.end();
    });
}

// ============================================================================
// 11. Direct TLS connection and certificate inspection
// ============================================================================

function inspectServerCertificate(hostname = "example.com") {
    console.log("\n=== 11. SERVER CERTIFICATE INSPECTION ===");

    return new Promise(resolve => {
        const socket = tls.connect(
            {
                host: hostname,
                port: 443,
                servername: hostname,
                minVersion: "TLSv1.2",
                rejectUnauthorized: true,
            },
            () => {
                const certificate = socket.getPeerCertificate(true);

                console.log("Connected:", socket.authorized);
                console.log("Authorization error:", socket.authorizationError);
                console.log("Protocol:", socket.getProtocol());
                console.log("Cipher:", socket.getCipher());

                if (certificate && Object.keys(certificate).length > 0) {
                    console.log("Subject:", certificate.subject);
                    console.log("Issuer:", certificate.issuer);
                    console.log("Valid from:", certificate.valid_from);
                    console.log("Valid to:", certificate.valid_to);

                    if (certificate.subjectaltname) {
                        console.log(
                            "Subject Alternative Names:",
                            certificate.subjectaltname
                        );
                    }

                    if (certificate.fingerprint256) {
                        console.log(
                            "SHA-256 fingerprint:",
                            certificate.fingerprint256
                        );
                    }
                }

                socket.end();
                resolve();
            }
        );

        socket.setTimeout(5000);

        socket.on("timeout", () => {
            console.log("TLS inspection timed out.");
            socket.destroy();
            resolve();
        });

        socket.on("error", error => {
            console.log("TLS connection failed:", error.message);
            resolve();
        });
    });
}

// ============================================================================
// 12. Security header analysis
// ============================================================================

function analyzeSecurityHeaders(headers) {
    const normalized = {};

    for (const [key, value] of Object.entries(headers)) {
        normalized[key.toLowerCase()] = String(value);
    }

    const findings = {};

    findings.hsts = normalized["strict-transport-security"]
        ? "Present"
        : "Missing";

    findings.csp = normalized["content-security-policy"]
        ? "Present"
        : "Missing";

    findings.nosniff = normalized["x-content-type-options"]
        ? "Present"
        : "Missing";

    return findings;
}

function securityHeadersDemo() {
    console.log("\n=== 12. SECURITY HEADERS ===");

    const headers = {
        "strict-transport-security":
            "max-age=31536000; includeSubDomains",
        "content-security-policy":
            "default-src 'self'",
        "x-content-type-options":
            "nosniff",
    };

    console.log(analyzeSecurityHeaders(headers));
}

// ============================================================================
// 13. Certificate fingerprint pinning concept
// ============================================================================

function sha256Fingerprint(data) {
    return crypto
        .createHash("sha256")
        .update(data)
        .digest("hex");
}

function certificatePinningDemo() {
    console.log("\n=== 13. PUBLIC-KEY PINNING CONCEPT ===");

    const trustedKey = Buffer.from("server-public-key-v1");
    const expectedPin = sha256Fingerprint(trustedKey);

    const correct = sha256Fingerprint(trustedKey);
    const attacker = sha256Fingerprint(
        Buffer.from("attacker-public-key")
    );

    console.log("Expected pin:", expectedPin);
    console.log("Correct key matches:", crypto.timingSafeEqual(
        Buffer.from(expectedPin, "hex"),
        Buffer.from(correct, "hex")
    ));
    console.log("Attacker key matches:", crypto.timingSafeEqual(
        Buffer.from(expectedPin, "hex"),
        Buffer.from(attacker, "hex")
    ));

    console.log(
        "\nPinning introduces operational risks because legitimate key rotation "
        + "must be coordinated with the pinned value."
    );
}

// ============================================================================
// 14. Replay protection at the application layer
// ============================================================================

function replayProtectionDemo() {
    console.log("\n=== 14. REPLAY PROTECTION ===");

    const seenRequestIds = new Set();
    const requestId = crypto.randomUUID();

    for (let attempt = 1; attempt <= 3; attempt++) {
        if (seenRequestIds.has(requestId)) {
            console.log(`Attempt ${attempt}: rejected as duplicate.`);
        } else {
            seenRequestIds.add(requestId);
            console.log(`Attempt ${attempt}: accepted.`);
        }
    }

    console.log(
        "\nTLS protects the communication channel, but applications may "
        + "still require idempotency or transaction-level replay controls."
    );
}

// ============================================================================
// 15. Failure conditions
// ============================================================================

function commonFailureConditions() {
    console.log("\n=== 15. TLS FAILURE CONDITIONS ===");

    const conditions = [
        "Expired certificate",
        "Hostname mismatch",
        "Unknown certificate authority",
        "Incomplete certificate chain",
        "Revocation or trust failure",
        "Unsupported protocol version",
        "No mutually acceptable cipher",
        "Incorrect server name indication",
        "Private-key mismatch",
        "TLS handshake timeout",
        "Tampered authenticated-encryption data",
    ];

    for (const condition of conditions) {
        console.log(" -", condition);
    }
}

// ============================================================================
// 16. Performance concepts
// ============================================================================

function performanceConsiderations() {
    console.log("\n=== 16. PERFORMANCE ===");

    const considerations = [
        "Public-key operations are relatively expensive.",
        "Symmetric encryption is efficient for bulk application data.",
        "TLS session resumption can reduce repeated handshake cost.",
        "HTTP connection reuse reduces repeated connection establishment.",
        "TLS 1.3 reduces handshake round trips compared with older designs.",
        "Certificate-chain validation consumes computation and network resources.",
        "Hardware acceleration can improve symmetric cryptographic performance.",
    ];

    for (const item of considerations) {
        console.log(" -", item);
    }
}

// ============================================================================
// 17. Secure configuration checklist
// ============================================================================

function productionChecklist() {
    console.log("\n=== 17. PRODUCTION CHECKLIST ===");

    const checklist = [
        "Use HTTPS for sensitive and authenticated traffic.",
        "Prefer TLS 1.3 when compatibility permits.",
        "Retain TLS 1.2 where required by legitimate compatibility needs.",
        "Disable obsolete TLS versions.",
        "Keep certificate chains valid and complete.",
        "Validate certificates and hostnames.",
        "Protect private keys.",
        "Automate certificate renewal.",
        "Monitor expiration and configuration changes.",
        "Use secure, HttpOnly, appropriately scoped cookies.",
        "Use HSTS after validating the deployment.",
        "Do not disable certificate verification to hide errors.",
        "Do not hard-code private keys in source repositories.",
        "Treat TLS authentication and application authorization as separate controls.",
        "Test certificate rotation and failure scenarios.",
    ];

    checklist.forEach((item, index) => {
        console.log(`${String(index + 1).padStart(2, "0")}. ${item}`);
    });
}

// ============================================================================
// 18. Main
// ============================================================================

async function main() {
    console.log("=".repeat(78));
    console.log("HTTPS & TLS: ENCRYPTION, CERTIFICATES, SECURE COMMUNICATION");
    console.log("=".repeat(78));

    networkingFundamentals();
    encodingAndHashing();
    secureRandomness();
    hmacDemo();
    authenticatedEncryptionDemo();
    hkdfDemo();
    diffieHellmanDemo();
    hostnameVerificationDemo();
    runtimeTLSInformation();
    securityHeadersDemo();
    certificatePinningDemo();
    replayProtectionDemo();
    commonFailureConditions();
    performanceConsiderations();
    productionChecklist();

    await httpsRequest("example.com");
    await inspectServerCertificate("example.com");

    console.log("\nStudy program completed.");
}

main().catch(error => {
    console.error("Unexpected failure:", error);
    process.exitCode = 1;
});
