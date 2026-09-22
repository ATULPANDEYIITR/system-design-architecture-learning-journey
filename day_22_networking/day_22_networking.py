"""
HTTPS & TLS: Encryption, Certificates, and Secure Communication

A self-contained study program that progresses from networking and cryptography
fundamentals to TLS 1.3 concepts, certificate validation, hostname verification,
key exchange, authenticated encryption, replay considerations, certificate
pinning, HTTP security headers, and a small educational HTTPS-like simulation.

The cryptographic demonstrations use Python's standard library where practical.
The TLS simulation intentionally models the protocol concepts without attempting
to implement production TLS itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
import socket
import ssl
import string
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ============================================================================
# 1. Networking fundamentals
# ============================================================================

def explain_networking_fundamentals() -> None:
    print("\n=== 1. NETWORKING FUNDAMENTALS ===")
    concepts = {
        "IP address": "Identifies a network interface at the IP layer.",
        "TCP": "Provides ordered, reliable, connection-oriented byte delivery.",
        "HTTP": "Application protocol used to exchange web requests and responses.",
        "HTTPS": "HTTP carried inside a TLS-protected connection.",
        "TLS": "Protocol providing confidentiality, integrity, authentication, and key establishment.",
        "Certificate": "Signed data binding an identity, commonly a DNS name, to a public key.",
        "Cipher suite": "A collection of cryptographic algorithms and protocol choices.",
    }
    for name, description in concepts.items():
        print(f"{name:16} -> {description}")

    print("\nTypical HTTPS layering:")
    print("Application: HTTP")
    print("Security:    TLS")
    print("Transport:   TCP")
    print("Network:     IP")


# ============================================================================
# 2. Encoding is not encryption
# ============================================================================

def demonstrate_encoding_vs_encryption() -> None:
    print("\n=== 2. ENCODING VS ENCRYPTION VS HASHING ===")

    message = b"Sensitive HTTP request"

    encoded = base64.b64encode(message)
    digest = hashlib.sha256(message).hexdigest()

    print("Original :", message)
    print("Base64   :", encoded)
    print("SHA-256  :", digest)

    print("\nBase64 can be decoded by anyone:")
    print(base64.b64decode(encoded))

    print("\nA hash is designed to be one-way:")
    print("SHA-256 output length:", len(digest), "hex characters")

    print(
        "\nEncryption differs because encryption uses a secret key and is "
        "designed to allow authorized decryption."
    )


# ============================================================================
# 3. Cryptographic building blocks
# ============================================================================

def demonstrate_randomness() -> None:
    print("\n=== 3. SECURE RANDOMNESS ===")
    token = secrets.token_urlsafe(32)
    nonce = secrets.token_bytes(12)

    print("Secure random token:", token)
    print("12-byte nonce:", nonce.hex())

    # secrets uses the operating system's cryptographically secure randomness.
    # random.random() should not be used for session secrets, tokens, or keys.


def demonstrate_hash_and_hmac() -> None:
    print("\n=== 4. HASHING AND HMAC ===")
    message = b"GET /account HTTP/1.1"
    secret = b"demo-shared-secret"

    digest = hashlib.sha256(message).hexdigest()
    mac = hmac.new(secret, message, hashlib.sha256).hexdigest()

    print("SHA-256:", digest)
    print("HMAC-SHA256:", mac)

    changed_message = b"GET /admin HTTP/1.1"
    changed_mac = hmac.new(secret, changed_message, hashlib.sha256).hexdigest()

    print("Changed-message HMAC:", changed_mac)
    print("MACs equal:", hmac.compare_digest(mac, changed_mac))

    # HMAC provides message authentication when both parties share a secret.
    # Modern TLS normally uses authenticated encryption rather than exposing
    # HMAC as a separate application-level primitive.


# ============================================================================
# 5. Symmetric encryption concepts
# ============================================================================

def xor_demo(data: bytes, key: bytes) -> bytes:
    """Educational XOR demonstration, NOT secure encryption."""
    return bytes(value ^ key[index % len(key)] for index, value in enumerate(data))


def demonstrate_symmetric_concept() -> None:
    print("\n=== 5. SYMMETRIC ENCRYPTION CONCEPT ===")
    plaintext = b"private HTTP payload"
    key = b"demo-key"

    ciphertext = xor_demo(plaintext, key)
    recovered = xor_demo(ciphertext, key)

    print("Plaintext :", plaintext)
    print("Ciphertext:", ciphertext.hex())
    print("Recovered :", recovered)

    print(
        "\nThis XOR construction is intentionally educational. "
        "Real HTTPS does not use this function."
    )


# ============================================================================
# 6. Authenticated encryption model
# ============================================================================

@dataclass
class ToyAEAD:
    """
    Educational authenticated-encryption model.

    This is NOT a replacement for AES-GCM or ChaCha20-Poly1305.
    It demonstrates the conceptual sequence:
        plaintext -> confidentiality -> authentication tag
        ciphertext + tag -> verification -> plaintext
    """

    key: bytes

    def encrypt(self, plaintext: bytes, nonce: bytes, associated_data: bytes = b"") -> Tuple[bytes, bytes]:
        stream = self._keystream(nonce, len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(
            self.key,
            associated_data + nonce + ciphertext,
            hashlib.sha256,
        ).digest()[:16]
        return ciphertext, tag

    def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        tag: bytes,
        associated_data: bytes = b"",
    ) -> bytes:
        expected = hmac.new(
            self.key,
            associated_data + nonce + ciphertext,
            hashlib.sha256,
        ).digest()[:16]

        if not hmac.compare_digest(tag, expected):
            raise ValueError("Authentication failed: ciphertext or metadata was modified.")

        stream = self._keystream(nonce, len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, stream))

    def _keystream(self, nonce: bytes, length: int) -> bytes:
        output = bytearray()
        counter = 0

        while len(output) < length:
            block = hmac.new(
                self.key,
                nonce + counter.to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()
            output.extend(block)
            counter += 1

        return bytes(output[:length])


def demonstrate_authenticated_encryption() -> None:
    print("\n=== 6. AUTHENTICATED ENCRYPTION ===")

    key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    aad = b"content-type: application/json"
    plaintext = b'{"user":"alice","role":"member"}'

    cipher = ToyAEAD(key)
    ciphertext, tag = cipher.encrypt(plaintext, nonce, aad)

    print("Ciphertext:", ciphertext.hex())
    print("Tag:", tag.hex())

    recovered = cipher.decrypt(ciphertext, nonce, tag, aad)
    print("Recovered:", recovered)

    tampered = bytearray(ciphertext)
    tampered[0] ^= 1

    try:
        cipher.decrypt(bytes(tampered), nonce, tag, aad)
    except ValueError as exc:
        print("Tampering detected:", exc)


# ============================================================================
# 7. Key exchange concept
# ============================================================================

@dataclass
class DHParameters:
    # Small values make the demonstration understandable.
    # Real TLS uses standardized secure groups with very large parameters.
    prime: int
    generator: int


def modexp(base: int, exponent: int, modulus: int) -> int:
    return pow(base, exponent, modulus)


def demonstrate_diffie_hellman() -> None:
    print("\n=== 7. DIFFIE-HELLMAN KEY AGREEMENT ===")

    params = DHParameters(prime=23, generator=5)

    alice_private = 6
    bob_private = 15

    alice_public = modexp(params.generator, alice_private, params.prime)
    bob_public = modexp(params.generator, bob_private, params.prime)

    alice_shared = modexp(bob_public, alice_private, params.prime)
    bob_shared = modexp(alice_public, bob_private, params.prime)

    print("Alice public value:", alice_public)
    print("Bob public value  :", bob_public)
    print("Alice shared value:", alice_shared)
    print("Bob shared value  :", bob_shared)
    print("Keys agree:", alice_shared == bob_shared)

    print(
        "\nTLS uses ephemeral Diffie-Hellman variants such as ECDHE in "
        "modern deployments. Ephemeral keys support forward secrecy."
    )


# ============================================================================
# 8. HKDF-style key derivation demonstration
# ============================================================================

def hkdf_extract(salt: bytes, input_key_material: bytes) -> bytes:
    if not salt:
        salt = b"\x00" * hashlib.sha256().digest_size
    return hmac.new(salt, input_key_material, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    output = bytearray()
    previous = b""

    for counter in range(1, 256):
        previous = hmac.new(
            prk,
            previous + info + bytes([counter]),
            hashlib.sha256,
        ).digest()
        output.extend(previous)

        if len(output) >= length:
            return bytes(output[:length])

    raise ValueError("Requested HKDF output is too long.")


def demonstrate_key_derivation() -> None:
    print("\n=== 8. KEY DERIVATION ===")

    shared_secret = b"example-ephemeral-shared-secret"
    salt = secrets.token_bytes(32)

    pseudorandom_key = hkdf_extract(salt, shared_secret)
    application_key = hkdf_expand(
        pseudorandom_key,
        b"TLS application traffic key",
        32,
    )

    print("Derived application key:", application_key.hex())

    # TLS 1.3 heavily relies on HKDF to derive separate traffic secrets and
    # keys from the evolving handshake secret.


# ============================================================================
# 9. Certificates
# ============================================================================

@dataclass(frozen=True)
class CertificateRecord:
    subject: str
    issuer: str
    public_key_fingerprint: str
    dns_names: Tuple[str, ...]
    is_ca: bool
    signature_algorithm: str


def fingerprint_public_key(public_key_material: bytes) -> str:
    return hashlib.sha256(public_key_material).hexdigest()


def demonstrate_certificate_structure() -> None:
    print("\n=== 9. DIGITAL CERTIFICATES ===")

    public_key = b"server-public-key-material"
    certificate = CertificateRecord(
        subject="CN=www.example.test",
        issuer="Example Intermediate CA",
        public_key_fingerprint=fingerprint_public_key(public_key),
        dns_names=("www.example.test", "example.test"),
        is_ca=False,
        signature_algorithm="RSA-PSS-SHA256",
    )

    print("Subject:", certificate.subject)
    print("Issuer :", certificate.issuer)
    print("DNS names:", certificate.dns_names)
    print("CA certificate:", certificate.is_ca)
    print("Public-key fingerprint:", certificate.public_key_fingerprint)

    print(
        "\nA certificate does not make encryption secret by itself. "
        "It binds identity information to a public key through a CA signature."
    )


# ============================================================================
# 10. Hostname verification
# ============================================================================

def dns_name_matches(pattern: str, hostname: str) -> bool:
    pattern = pattern.lower().rstrip(".")
    hostname = hostname.lower().rstrip(".")

    if pattern == hostname:
        return True

    # Simplified wildcard handling:
    # *.example.com can match www.example.com but not a.b.example.com.
    if pattern.startswith("*."):
        suffix = pattern[1:]
        if hostname.endswith(suffix):
            return hostname.count(".") == pattern.count(".")

    return False


def verify_hostname(hostname: str, dns_names: Sequence[str]) -> bool:
    return any(dns_name_matches(name, hostname) for name in dns_names)


def demonstrate_hostname_verification() -> None:
    print("\n=== 10. HOSTNAME VERIFICATION ===")

    names = ("example.com", "*.secure.example.com")

    tests = (
        "example.com",
        "www.example.com",
        "api.secure.example.com",
        "a.b.secure.example.com",
        "evil.example.net",
    )

    for hostname in tests:
        print(f"{hostname:30} -> {verify_hostname(hostname, names)}")


# ============================================================================
# 11. Certificate chain concepts
# ============================================================================

@dataclass
class SimulatedCertificate:
    name: str
    issuer: str
    is_ca: bool


def validate_certificate_chain(
    leaf: SimulatedCertificate,
    intermediates: Sequence[SimulatedCertificate],
    trusted_roots: Sequence[str],
) -> Tuple[bool, str]:
    certificates = {certificate.name: certificate for certificate in intermediates}
    current = leaf
    visited = set()

    while True:
        if current.name in visited:
            return False, "Certificate chain contains a cycle."

        visited.add(current.name)

        if current.issuer in trusted_roots:
            return True, f"Chain terminates at trusted root: {current.issuer}"

        issuer = certificates.get(current.issuer)
        if issuer is None:
            return False, f"Missing issuer certificate: {current.issuer}"

        if not issuer.is_ca:
            return False, f"Issuer is not marked as a CA: {issuer.name}"

        current = issuer


def demonstrate_certificate_chain() -> None:
    print("\n=== 11. CERTIFICATE CHAIN ===")

    root = "Example Root CA"
    intermediate = SimulatedCertificate(
        name="Example Intermediate CA",
        issuer=root,
        is_ca=True,
    )
    leaf = SimulatedCertificate(
        name="www.example.test",
        issuer=intermediate.name,
        is_ca=False,
    )

    valid, reason = validate_certificate_chain(
        leaf,
        [intermediate],
        [root],
    )

    print("Valid:", valid)
    print("Reason:", reason)

    missing, reason = validate_certificate_chain(
        leaf,
        [],
        [root],
    )

    print("Without intermediate:", missing)
    print("Reason:", reason)


# ============================================================================
# 12. TLS handshake simulation
# ============================================================================

@dataclass
class HandshakeTranscript:
    client_random: bytes
    server_random: bytes
    client_key_share: bytes
    server_key_share: bytes
    negotiated_protocol: str = "TLS 1.3"
    negotiated_cipher: str = "TLS_AES_128_GCM_SHA256"
    events: List[str] = field(default_factory=list)

    def record(self, message: str) -> None:
        self.events.append(message)


def simulate_tls_handshake() -> HandshakeTranscript:
    transcript = HandshakeTranscript(
        client_random=secrets.token_bytes(32),
        server_random=secrets.token_bytes(32),
        client_key_share=secrets.token_bytes(32),
        server_key_share=secrets.token_bytes(32),
    )

    transcript.record("ClientHello: supported TLS versions and cipher suites sent.")
    transcript.record("ServerHello: TLS 1.3 and an AEAD cipher selected.")
    transcript.record("Server sends certificate chain.")
    transcript.record("Client validates certificate chain and hostname.")
    transcript.record("Ephemeral key shares establish shared secret.")
    transcript.record("Handshake traffic keys are derived.")
    transcript.record("Finished messages authenticate the handshake transcript.")
    transcript.record("Application traffic keys are activated.")

    return transcript


def demonstrate_tls_handshake() -> None:
    print("\n=== 12. TLS 1.3 HANDSHAKE MODEL ===")

    transcript = simulate_tls_handshake()

    print("Protocol:", transcript.negotiated_protocol)
    print("Cipher:", transcript.negotiated_cipher)

    for index, event in enumerate(transcript.events, 1):
        print(f"{index:02}. {event}")

    print(
        "\nThis is a conceptual simulation, not a wire-compatible TLS implementation."
    )


# ============================================================================
# 13. Real TLS information from the Python runtime
# ============================================================================

def inspect_local_tls_capabilities() -> None:
    print("\n=== 13. LOCAL TLS RUNTIME INFORMATION ===")
    print("OpenSSL:", ssl.OPENSSL_VERSION)
    print("Default TLS versions:", ssl.TLSVersion.TLSv1_2, "to", ssl.TLSVersion.MAXIMUM_SUPPORTED)

    context = ssl.create_default_context()
    print("Certificate verification enabled:", context.verify_mode == ssl.CERT_REQUIRED)
    print("Hostname verification enabled:", context.check_hostname)

    cipher_names = context.get_ciphers()
    print("Number of configured cipher options:", len(cipher_names))

    for cipher in cipher_names[:5]:
        print(
            f"  {cipher['name']} | protocol={cipher['protocol']} | "
            f"bits={cipher['alg_bits']}"
        )


# ============================================================================
# 14. Secure HTTPS client configuration
# ============================================================================

def create_secure_https_context() -> ssl.SSLContext:
    """
    Create a client TLS context with certificate validation and hostname
    checking enabled.

    The system trust store is used. Applications should normally rely on a
    maintained operating-system or platform trust store rather than disabling
    verification.
    """
    context = ssl.create_default_context()

    # TLS 1.2 is retained as a compatibility floor here. A deployment may
    # choose TLS 1.3 only when its compatibility requirements permit it.
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    return context


def demonstrate_secure_context() -> None:
    print("\n=== 14. SECURE HTTPS CLIENT CONTEXT ===")

    context = create_secure_https_context()

    print("Minimum TLS version:", context.minimum_version.name)
    print("Certificate verification:", context.verify_mode.name)
    print("Hostname verification:", context.check_hostname)


# ============================================================================
# 15. HTTPS request mechanics
# ============================================================================

def https_request_example(host: str = "example.com") -> None:
    """
    Perform a small HTTPS request using Python's standard library.

    Network availability varies by environment. Errors are caught so that the
    study program remains executable when outbound networking is unavailable.
    """
    print("\n=== 15. HTTPS REQUEST ===")

    context = create_secure_https_context()

    try:
        with socket.create_connection((host, 443), timeout=5) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=host) as tls_socket:
                print("TLS version:", tls_socket.version())
                print("Cipher:", tls_socket.cipher())

                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    f"Connection: close\r\n"
                    f"User-Agent: TLS-study-client/1.0\r\n"
                    f"\r\n"
                )

                tls_socket.sendall(request.encode("ascii"))

                response = bytearray()
                while len(response) < 4096:
                    chunk = tls_socket.recv(1024)
                    if not chunk:
                        break
                    response.extend(chunk)

                print("First response bytes:")
                print(bytes(response[:1000]).decode("iso-8859-1", errors="replace"))

    except (OSError, ssl.SSLError) as exc:
        print("HTTPS connection could not be completed:", exc)


# ============================================================================
# 16. Security headers
# ============================================================================

def analyze_security_headers(headers: Dict[str, str]) -> Dict[str, str]:
    normalized = {key.lower(): value.strip() for key, value in headers.items()}
    findings = {}

    if "strict-transport-security" not in normalized:
        findings["HSTS"] = "Missing: browser enforcement of HTTPS may be weaker."
    else:
        findings["HSTS"] = "Present."

    if "content-security-policy" not in normalized:
        findings["CSP"] = "Missing: browser-side content restrictions are not declared."
    else:
        findings["CSP"] = "Present."

    if "x-content-type-options" not in normalized:
        findings["Content-Type"] = "Missing nosniff protection."
    else:
        findings["Content-Type"] = "Present."

    return findings


def demonstrate_security_headers() -> None:
    print("\n=== 16. HTTP SECURITY HEADERS ===")

    headers = {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "X-Content-Type-Options": "nosniff",
    }

    for name, finding in analyze_security_headers(headers).items():
        print(f"{name:18}: {finding}")


# ============================================================================
# 17. TLS attack and failure simulations
# ============================================================================

def demonstrate_tampering_detection() -> None:
    print("\n=== 17. TAMPERING DETECTION ===")

    key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    message = b"transfer=100"

    cipher = ToyAEAD(key)
    encrypted, tag = cipher.encrypt(message, nonce)

    tampered_tag = bytearray(tag)
    tampered_tag[-1] ^= 0x80

    try:
        cipher.decrypt(encrypted, nonce, bytes(tampered_tag))
    except ValueError:
        print("Modified authentication tag was rejected.")

    try:
        cipher.decrypt(encrypted + b"x", nonce, tag)
    except ValueError:
        print("Modified ciphertext was rejected.")


def demonstrate_replay_concept() -> None:
    print("\n=== 18. REPLAY CONSIDERATIONS ===")

    request_id = secrets.token_hex(8)
    seen = set()

    for attempt in range(1, 4):
        if request_id in seen:
            print(f"Attempt {attempt}: rejected as duplicate.")
        else:
            seen.add(request_id)
            print(f"Attempt {attempt}: accepted by application replay check.")

    print(
        "\nTLS protects the transport channel, but applications may still need "
        "idempotency keys, timestamps, sequence numbers, or transaction IDs."
    )


def demonstrate_common_misconfigurations() -> None:
    print("\n=== 19. COMMON TLS MISCONFIGURATIONS ===")

    bad_practices = [
        "Disabling certificate verification.",
        "Disabling hostname verification.",
        "Accepting expired certificates.",
        "Trusting arbitrary self-signed certificates.",
        "Using obsolete TLS versions without a compatibility requirement.",
        "Ignoring certificate expiry and rotation.",
        "Logging plaintext secrets or session tokens.",
        "Reusing cryptographic nonces incorrectly.",
        "Hard-coding private keys in source code.",
        "Assuming TLS replaces application authorization.",
    ]

    for item in bad_practices:
        print(" -", item)


# ============================================================================
# 20. Certificate pinning concepts
# ============================================================================

def verify_pinned_key(public_key: bytes, expected_sha256: str) -> bool:
    actual = fingerprint_public_key(public_key)
    return hmac.compare_digest(actual, expected_sha256.lower())


def demonstrate_pinning() -> None:
    print("\n=== 20. CERTIFICATE / PUBLIC-KEY PINNING CONCEPT ===")

    trusted_public_key = b"server-key-v1"
    pin = fingerprint_public_key(trusted_public_key)

    print("Pin:", pin)
    print("Correct key:", verify_pinned_key(trusted_public_key, pin))
    print("Different key:", verify_pinned_key(b"attacker-key", pin))

    print(
        "\nPinning can reduce dependence on the general trust store, but careless "
        "pinning can make legitimate certificate rotation fail."
    )


# ============================================================================
# 21. TLS version comparison
# ============================================================================

def compare_tls_versions() -> None:
    print("\n=== 21. TLS VERSION COMPARISON ===")

    rows = [
        ("SSL 2.0/3.0", "Obsolete", "Do not use"),
        ("TLS 1.0", "Obsolete", "Do not use"),
        ("TLS 1.1", "Obsolete", "Do not use"),
        ("TLS 1.2", "Widely deployed", "Use where compatibility requires it"),
        ("TLS 1.3", "Modern", "Preferred modern protocol version"),
    ]

    for version, status, practical_note in rows:
        print(f"{version:12} | {status:18} | {practical_note}")


# ============================================================================
# 22. Performance considerations
# ============================================================================

def estimate_message_overhead(message_sizes: Iterable[int]) -> None:
    print("\n=== 22. PERFORMANCE AND OVERHEAD ===")

    for size in message_sizes:
        # This is a conceptual estimate rather than a packet-level calculation.
        record_overhead = 22
        percentage = record_overhead / size * 100 if size else float("inf")
        print(
            f"Payload={size:6} bytes | conceptual overhead={record_overhead:2} "
            f"bytes | ratio={percentage:8.2f}%"
        )

    print(
        "\nModern TLS uses symmetric cryptography for application data because "
        "symmetric operations are much cheaper than public-key operations."
    )


# ============================================================================
# 23. Production checklist
# ============================================================================

def production_checklist() -> None:
    print("\n=== 23. PRODUCTION HTTPS CHECKLIST ===")

    checklist = [
        "Use HTTPS for authenticated and sensitive traffic.",
        "Use TLS 1.2 or TLS 1.3 according to compatibility requirements.",
        "Prefer TLS 1.3 where supported.",
        "Keep certificate chains complete and valid.",
        "Use a trusted certificate authority for public services.",
        "Validate certificate expiration and hostname.",
        "Protect private keys with appropriate access controls.",
        "Automate certificate renewal where practical.",
        "Use secure cookies for browser sessions.",
        "Use HSTS when the deployment is ready for strict HTTPS enforcement.",
        "Do not mix sensitive HTTPS pages with insecure HTTP resources.",
        "Do not disable certificate verification to fix connection errors.",
        "Monitor certificate and TLS configuration changes.",
        "Separate transport authentication from application authorization.",
        "Test failure paths, expiry, rotation, and revoked or invalid certificates.",
    ]

    for index, item in enumerate(checklist, 1):
        print(f"{index:02}. {item}")


# ============================================================================
# 24. Knowledge checks
# ============================================================================

def knowledge_checks() -> None:
    print("\n=== 24. KNOWLEDGE CHECKS ===")

    questions = [
        (
            "Why is HTTPS different from HTTP?",
            "HTTPS protects HTTP traffic using TLS."
        ),
        (
            "Why is a certificate important?",
            "It binds an identity to a public key through a trusted signature chain."
        ),
        (
            "Why use symmetric encryption for application data?",
            "It is efficient for large amounts of data."
        ),
        (
            "What does hostname verification protect against?",
            "It helps ensure the certificate is valid for the server name being contacted."
        ),
        (
            "Does TLS provide application authorization?",
            "No. Authorization remains an application-level responsibility."
        ),
        (
            "Does encryption alone guarantee integrity?",
            "Not necessarily. Authenticated encryption provides confidentiality and integrity."
        ),
    ]

    for question, answer in questions:
        print("\nQuestion:", question)
        print("Answer  :", answer)


# ============================================================================
# 25. Main study sequence
# ============================================================================

def main() -> None:
    print("=" * 78)
    print("HTTPS & TLS: ENCRYPTION, CERTIFICATES, SECURE COMMUNICATION")
    print("=" * 78)

    explain_networking_fundamentals()
    demonstrate_encoding_vs_encryption()
    demonstrate_randomness()
    demonstrate_hash_and_hmac()
    demonstrate_symmetric_concept()
    demonstrate_authenticated_encryption()
    demonstrate_diffie_hellman()
    demonstrate_key_derivation()
    demonstrate_certificate_structure()
    demonstrate_hostname_verification()
    demonstrate_certificate_chain()
    demonstrate_tls_handshake()
    inspect_local_tls_capabilities()
    demonstrate_secure_context()
    demonstrate_security_headers()
    demonstrate_tampering_detection()
    demonstrate_replay_concept()
    demonstrate_common_misconfigurations()
    demonstrate_pinning()
    compare_tls_versions()
    estimate_message_overhead([64, 512, 4096, 65536])
    production_checklist()
    knowledge_checks()

    print("\n=== OPTIONAL LIVE HTTPS TEST ===")
    print("The following test contacts example.com when outbound networking is available.")
    https_request_example()

    print("\nStudy program completed.")


if __name__ == "__main__":
    main()
