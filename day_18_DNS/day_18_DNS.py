"""
DNS: Domain Resolution, Recursive DNS, and Caching
==================================================

A self-contained study program that demonstrates DNS concepts from beginner
through advanced level.

The examples intentionally use deterministic, simulated DNS infrastructure so
the file can run without network access or third-party packages.

Topics covered:
- Domain names and DNS terminology
- Labels, zones, records, TTL
- Forward and reverse resolution
- Recursive and iterative resolution
- Root, TLD, and authoritative servers
- Recursive resolvers
- DNS cache behavior
- Positive and negative caching
- CNAME chains
- Delegation
- Glue records
- Round-trip query simulation
- DNS message concepts
- UDP/TCP/DoT/DoH concepts
- DNSSEC concepts
- Cache poisoning considerations
- Timeouts, retries, SERVFAIL, NXDOMAIN
- Split-horizon DNS
- Round-robin records
- Resolution algorithms
- Performance and operational considerations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import ipaddress
import random
import time


# ---------------------------------------------------------------------------
# 1. Fundamental terminology
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


print_section("1. DNS fundamentals")

print(
    """
DNS (Domain Name System) translates human-readable names such as
www.example.com into resource records such as IPv4 addresses.

A domain name is hierarchical:

    www.example.com
    |   |       |
    |   |       +-- top-level domain (TLD)
    |   +---------- second-level domain
    +-------------- host/service label

The trailing dot represents the DNS root:

    www.example.com.

A fully qualified domain name (FQDN) is interpreted relative to the root.
DNS is distributed rather than stored in one global database.
"""
)


# ---------------------------------------------------------------------------
# 2. DNS record model
# ---------------------------------------------------------------------------

class RecordType(str, Enum):
    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    NS = "NS"
    MX = "MX"
    TXT = "TXT"
    SOA = "SOA"
    PTR = "PTR"


@dataclass(frozen=True)
class DNSRecord:
    name: str
    record_type: RecordType
    value: str
    ttl: int = 300

    def __post_init__(self) -> None:
        if self.ttl < 0:
            raise ValueError("TTL cannot be negative")

    def __str__(self) -> str:
        return f"{self.name} {self.ttl} IN {self.record_type.value} {self.value}"


records = [
    DNSRecord("example.com.", RecordType.A, "93.184.216.34", 3600),
    DNSRecord("example.com.", RecordType.AAAA, "2606:2800:220:1:248:1893:25c8:1946", 3600),
    DNSRecord("www.example.com.", RecordType.CNAME, "example.com.", 300),
    DNSRecord("example.com.", RecordType.MX, "10 mail.example.com.", 1800),
    DNSRecord("mail.example.com.", RecordType.A, "192.0.2.25", 300),
    DNSRecord("example.com.", RecordType.TXT, "v=spf1 -all", 3600),
]

for record in records:
    print(record)


# ---------------------------------------------------------------------------
# 3. Basic validation and normalization
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Convert a DNS name to a canonical lowercase FQDN."""
    name = name.strip().lower()
    if not name:
        raise ValueError("DNS name cannot be empty")
    if not name.endswith("."):
        name += "."
    return name


def validate_ipv4(address: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(address), ipaddress.IPv4Address)
    except ValueError:
        return False


def validate_ipv6(address: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(address), ipaddress.IPv6Address)
    except ValueError:
        return False


print("\nNormalization:")
for name in ["WWW.Example.COM", "example.com.", " mail.example.com "]:
    print(name, "->", normalize_name(name))

print("\nAddress validation:")
for address in ["93.184.216.34", "999.1.1.1", "::1", "not-an-ip"]:
    print(
        address,
        "IPv4:", validate_ipv4(address),
        "IPv6:", validate_ipv6(address),
    )


# ---------------------------------------------------------------------------
# 4. DNS zones and authoritative servers
# ---------------------------------------------------------------------------

@dataclass
class DNSZone:
    origin: str
    records: Dict[Tuple[str, RecordType], List[DNSRecord]] = field(default_factory=dict)

    def add_record(self, record: DNSRecord) -> None:
        key = (normalize_name(record.name), record.record_type)
        self.records.setdefault(key, []).append(record)

    def query(self, name: str, record_type: RecordType) -> List[DNSRecord]:
        key = (normalize_name(name), record_type)
        return list(self.records.get(key, []))


example_zone = DNSZone("example.com.")

for record in records:
    example_zone.add_record(record)

print_section("2. Authoritative zone lookup")

for record_type in [RecordType.A, RecordType.AAAA, RecordType.MX, RecordType.TXT]:
    result = example_zone.query("example.com.", record_type)
    print(record_type.value, result)


# ---------------------------------------------------------------------------
# 5. DNS hierarchy
# ---------------------------------------------------------------------------

@dataclass
class AuthoritativeServer:
    name: str
    zones: Dict[str, DNSZone] = field(default_factory=dict)

    def add_zone(self, zone: DNSZone) -> None:
        self.zones[normalize_name(zone.origin)] = zone

    def query(self, name: str, record_type: RecordType) -> List[DNSRecord]:
        name = normalize_name(name)

        for origin, zone in self.zones.items():
            if name == origin or name.endswith("." + origin):
                return zone.query(name, record_type)

        return []


authoritative = AuthoritativeServer("ns1.example.com.")
authoritative.add_zone(example_zone)


# ---------------------------------------------------------------------------
# 6. Simulated root and TLD servers
# ---------------------------------------------------------------------------

@dataclass
class Delegation:
    zone: str
    nameservers: List[str]


root_delegations = {
    "com.": Delegation("com.", ["a.gtld-servers.net.", "b.gtld-servers.net."]),
    "org.": Delegation("org.", ["a0.org.afilias-nst.info."]),
}

tld_delegations = {
    "example.com.": Delegation(
        "example.com.",
        ["ns1.example.com.", "ns2.example.com."]
    )
}


def parent_zone(name: str) -> str:
    labels = normalize_name(name).rstrip(".").split(".")
    if len(labels) <= 1:
        return "."
    return ".".join(labels[1:]) + "."


def get_tld(name: str) -> str:
    labels = normalize_name(name).rstrip(".").split(".")
    if len(labels) < 2:
        return "."
    return labels[-1] + "."


print_section("3. DNS hierarchy")

for name in ["www.example.com.", "mail.example.com.", "example.org."]:
    print(
        f"{name:25} parent={parent_zone(name):20} "
        f"tld={get_tld(name)}"
    )

print(
    """
A normal public lookup can conceptually cross:

    Client
       |
       v
    Recursive resolver
       |
       v
    Root server
       |
       v
    TLD server
       |
       v
    Authoritative server
       |
       v
    Answer

The recursive resolver performs the work on behalf of the client.
"""


# ---------------------------------------------------------------------------
# 7. Recursive versus iterative resolution
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    answer: List[DNSRecord]
    status: str
    trace: List[str] = field(default_factory=list)


class SimulatedDNSInfrastructure:
    """
    Models the logical behavior of DNS without sending real packets.

    A real resolver would communicate with DNS servers using DNS messages.
    This simulation focuses on resolution mechanics.
    """

    def __init__(self) -> None:
        self.authoritative_servers = {
            "ns1.example.com.": authoritative,
            "ns2.example.com.": authoritative,
        }

    def authoritative_lookup(
        self,
        server_name: str,
        name: str,
        record_type: RecordType,
    ) -> QueryResult:
        server = self.authoritative_servers.get(server_name)
        if server is None:
            return QueryResult([], "SERVFAIL", [f"{server_name}: unavailable"])

        answer = server.query(name, record_type)

        if answer:
            return QueryResult(
                answer,
                "NOERROR",
                [f"{server_name}: authoritative answer"]
            )

        # CNAME processing is a normal part of practical DNS resolution.
        cname = server.query(name, RecordType.CNAME)
        if cname and record_type != RecordType.CNAME:
            return QueryResult(
                cname,
                "CNAME",
                [f"{server_name}: CNAME referral"]
            )

        return QueryResult(
            [],
            "NXDOMAIN",
            [f"{server_name}: no matching record"]
        )

    def iterative_resolve(
        self,
        name: str,
        record_type: RecordType,
    ) -> QueryResult:
        name = normalize_name(name)
        trace = ["Resolver starts iterative resolution"]

        tld = get_tld(name)
        if tld not in root_delegations:
            return QueryResult([], "NXDOMAIN", trace + ["Root: no TLD delegation"])

        trace.append(f"Root: referral for {tld}")

        delegation = tld_delegations.get(
            parent_zone(name) if name != parent_zone(name) else name
        )

        if delegation is None:
            # For this educational model, example.com is the only delegated zone.
            return QueryResult([], "NXDOMAIN", trace + ["TLD: no domain delegation"])

        trace.append(
            "TLD: referral to " + ", ".join(delegation.nameservers)
        )

        for nameserver in delegation.nameservers:
            result = self.authoritative_lookup(
                nameserver, name, record_type
            )

            if result.status == "NOERROR":
                return QueryResult(
                    result.answer,
                    "NOERROR",
                    trace + result.trace
                )

            if result.status == "CNAME":
                cname_target = result.answer[0].value
                trace.extend(result.trace)
                trace.append(f"Resolver follows CNAME to {cname_target}")

                target_result = self.iterative_resolve(
                    cname_target, record_type
                )
                return QueryResult(
                    target_result.answer,
                    target_result.status,
                    trace + target_result.trace
                )

        return QueryResult([], "SERVFAIL", trace + ["All authoritative servers failed"])


infrastructure = SimulatedDNSInfrastructure()

print_section("4. Iterative resolution trace")

result = infrastructure.iterative_resolve(
    "www.example.com.",
    RecordType.A,
)

print("Status:", result.status)
print("Answer:", result.answer)
print("Trace:")
for step in result.trace:
    print("  ", step)


# ---------------------------------------------------------------------------
# 8. Recursive resolver and caching
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    records: List[DNSRecord]
    expires_at: float
    status: str

    def remaining_ttl(self, now: float) -> int:
        return max(0, int(self.expires_at - now))


class RecursiveResolver:
    """
    A simplified recursive resolver.

    Important real-world properties:
    - Clients ask for recursive service.
    - The resolver can query upstream DNS servers.
    - Successful records are cached according to TTL.
    - Negative responses can also be cached according to negative TTL rules.
    """

    def __init__(
        self,
        infrastructure: SimulatedDNSInfrastructure,
        clock=time.monotonic,
    ) -> None:
        self.infrastructure = infrastructure
        self.clock = clock
        self.cache: Dict[Tuple[str, RecordType], CacheEntry] = {}

    def query(
        self,
        name: str,
        record_type: RecordType,
    ) -> QueryResult:
        name = normalize_name(name)
        key = (name, record_type)
        now = self.clock()

        cached = self.cache.get(key)

        if cached and cached.expires_at > now:
            remaining = cached.remaining_ttl(now)
            return QueryResult(
                cached.records,
                cached.status,
                [f"Cache hit; remaining TTL={remaining}s"]
            )

        if cached:
            del self.cache[key]

        result = self.infrastructure.iterative_resolve(name, record_type)

        if result.answer:
            ttl = min(record.ttl for record in result.answer)
            self.cache[key] = CacheEntry(
                result.answer,
                now + ttl,
                result.status,
            )
        elif result.status == "NXDOMAIN":
            # Real negative caching uses SOA-derived information.
            # A small fixed TTL is used here solely for demonstration.
            self.cache[key] = CacheEntry([], now + 30, result.status)

        return QueryResult(
            result.answer,
            result.status,
            ["Cache miss"] + result.trace
        )


resolver = RecursiveResolver(infrastructure)

print_section("5. Recursive resolver and positive caching")

first = resolver.query("example.com.", RecordType.A)
print("First query:")
print("Status:", first.status)
print("Answer:", first.answer)
print("Trace:", first.trace)

second = resolver.query("example.com.", RecordType.A)
print("\nSecond query:")
print("Status:", second.status)
print("Answer:", second.answer)
print("Trace:", second.trace)


# ---------------------------------------------------------------------------
# 9. CNAME caching and resolution
# ---------------------------------------------------------------------------

print_section("6. CNAME resolution")

cname_result = resolver.query("www.example.com.", RecordType.A)

print("Query: www.example.com. A")
print("Status:", cname_result.status)
print("Answer:", cname_result.answer)

print(
    """
A CNAME is an alias, not another address.

    www.example.com. CNAME example.com.
    example.com.     A     93.184.216.34

The resolver must continue resolution when the requested type is not CNAME.
"""


# ---------------------------------------------------------------------------
# 10. Negative caching
# ---------------------------------------------------------------------------

print_section("7. NXDOMAIN and negative caching")

missing = resolver.query("does-not-exist.example.com.", RecordType.A)
print("First missing query:", missing.status, missing.trace)

missing_again = resolver.query(
    "does-not-exist.example.com.",
    RecordType.A,
)
print("Second missing query:", missing_again.status, missing_again.trace)

print(
    """
NXDOMAIN means the queried domain name does not exist.

NXDOMAIN differs from:
- NOERROR with an empty answer: the name exists, but the requested type
  may not exist.
- SERVFAIL: the resolver could not successfully complete the lookup.
- REFUSED: a server declined to answer the query.
"""
)


# ---------------------------------------------------------------------------
# 11. TTL simulation with a controllable clock
# ---------------------------------------------------------------------------

print_section("8. TTL behavior")

class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("Cannot move clock backward")
        self.current += seconds


fake_clock = FakeClock()
ttl_resolver = RecursiveResolver(infrastructure, fake_clock)

before = ttl_resolver.query("example.com.", RecordType.A)
print("Initial:", before.trace)

after = ttl_resolver.query("example.com.", RecordType.A)
print("Immediate repeat:", after.trace)

fake_clock.advance(3601)

expired = ttl_resolver.query("example.com.", RecordType.A)
print("After TTL expiration:", expired.trace)

print(
    """
TTL is not merely a cache timeout. It is an operational control.

Long TTL:
- fewer upstream queries
- lower latency
- less authoritative traffic
- slower propagation of changes

Short TTL:
- faster adaptation to changes
- more queries
- greater dependency on authoritative infrastructure
"""


# ---------------------------------------------------------------------------
# 12. Multiple records and round-robin behavior
# ---------------------------------------------------------------------------

print_section("9. Multiple A records")

load_balanced_zone = DNSZone("service.example.")

for address in ["192.0.2.10", "192.0.2.11", "192.0.2.12"]:
    load_balanced_zone.add_record(
        DNSRecord(
            "service.example.",
            RecordType.A,
            address,
            60,
        )
    )

answers = load_balanced_zone.query(
    "service.example.",
    RecordType.A,
)

print("Configured addresses:")
for answer in answers:
    print(" ", answer)

print(
    """
DNS can return multiple addresses. Some systems rotate answer order,
sometimes called DNS round-robin.

This is not equivalent to a full load balancer:
- DNS clients cache answers.
- Client behavior varies.
- Health checking may be absent.
- A failed server can remain cached until TTL expiration.
"""


# ---------------------------------------------------------------------------
# 13. Reverse DNS
# ---------------------------------------------------------------------------

print_section("10. Reverse DNS")

def ipv4_reverse_name(address: str) -> str:
    ip = ipaddress.IPv4Address(address)
    octets = str(ip).split(".")
    return ".".join(reversed(octets)) + ".in-addr.arpa."


def ipv6_reverse_name(address: str) -> str:
    ip = ipaddress.IPv6Address(address)
    hexadecimal = ip.exploded.replace(":", "")
    return ".".join(reversed(hexadecimal)) + ".ip6.arpa."


print(
    "IPv4 reverse:",
    ipv4_reverse_name("192.0.2.25")
)

print(
    "IPv6 reverse:",
    ipv6_reverse_name("2001:db8::1")
)

print(
    """
Forward lookup:

    name -> address

Reverse lookup:

    address -> PTR -> name

Reverse DNS is commonly used for diagnostics, logging, email reputation
checks, and infrastructure administration. It does not prove ownership or
identity by itself.
"""
)


# ---------------------------------------------------------------------------
# 14. DNS message concepts
# ---------------------------------------------------------------------------

print_section("11. DNS message structure")

@dataclass
class DNSHeader:
    transaction_id: int
    recursion_desired: bool
    recursion_available: bool
    authoritative_answer: bool
    response_code: str


@dataclass
class DNSMessage:
    header: DNSHeader
    questions: List[Tuple[str, RecordType]]
    answers: List[DNSRecord]
    authority: List[DNSRecord]
    additional: List[DNSRecord]


query_message = DNSMessage(
    header=DNSHeader(
        transaction_id=0x1234,
        recursion_desired=True,
        recursion_available=False,
        authoritative_answer=False,
        response_code="NOERROR",
    ),
    questions=[("www.example.com.", RecordType.A)],
    answers=[],
    authority=[],
    additional=[],
)

response_message = DNSMessage(
    header=DNSHeader(
        transaction_id=query_message.header.transaction_id,
        recursion_desired=True,
        recursion_available=True,
        authoritative_answer=True,
        response_code="NOERROR",
    ),
    questions=query_message.questions,
    answers=[
        DNSRecord(
            "www.example.com.",
            RecordType.A,
            "93.184.216.34",
            300,
        )
    ],
    authority=[],
    additional=[],
)

print("Query transaction ID:", hex(query_message.header.transaction_id))
print("Recursion desired:", query_message.header.recursion_desired)
print("Response recursion available:", response_message.header.recursion_available)
print("Authoritative answer:", response_message.header.authoritative_answer)
print("Response code:", response_message.header.response_code)

print(
    """
A DNS message conceptually contains:
- Header
- Question section
- Answer section
- Authority section
- Additional section

The actual wire format is compact binary data, not text.
"""


# ---------------------------------------------------------------------------
# 15. UDP, TCP, DoT, and DoH
# ---------------------------------------------------------------------------

print_section("12. DNS transport choices")

transport_comparison = {
    "UDP/53": "Traditional DNS transport; low overhead; common default.",
    "TCP/53": "Reliable transport; required in many situations including
               certain large responses and zone transfers.",
    "DoT/853": "DNS over TLS; encrypts DNS traffic between client and resolver.",
    "DoH/443": "DNS over HTTPS; carries DNS messages through HTTPS.",
}

for transport, description in transport_comparison.items():
    print(f"{transport}: {description.strip()}")

print(
    """
Encryption changes confidentiality properties but does not automatically
make the queried domain trustworthy.

DoT and DoH can hide DNS queries from local network observers, while the
resolver still sees the query unless another privacy mechanism is used.
"""


# ---------------------------------------------------------------------------
# 16. Delegation and glue records
# ---------------------------------------------------------------------------

print_section("13. Delegation and glue")

print(
    """
A parent zone delegates a child zone by publishing NS records.

Example concept:

    example.com. NS ns1.example.com.
    example.com. NS ns2.example.com.

A resolver needs an IP address for the nameserver before it can contact it.

If the nameserver is inside the delegated zone, a circular dependency can
appear:

    Need example.com. answer
        |
        v
    Need ns1.example.com. address
        |
        v
    But ns1.example.com. is inside example.com.

Glue records in the parent zone provide the necessary address information.
"""


# ---------------------------------------------------------------------------
# 17. Split-horizon DNS
# ---------------------------------------------------------------------------

print_section("14. Split-horizon DNS")

class SplitHorizonResolver:
    def __init__(self) -> None:
        self.internal = {
            "portal.example.com.": "10.0.0.20",
        }
        self.external = {
            "portal.example.com.": "203.0.113.20",
        }

    def resolve(self, name: str, internal_client: bool) -> Optional[str]:
        normalized = normalize_name(name)
        table = self.internal if internal_client else self.external
        return table.get(normalized)


split_resolver = SplitHorizonResolver()

print(
    "Internal client:",
    split_resolver.resolve("portal.example.com", True)
)

print(
    "External client:",
    split_resolver.resolve("portal.example.com", False)
)

print(
    """
Split-horizon DNS presents different answers depending on client context.

It can support:
- private internal services
- public service discovery
- internal routing
- controlled exposure

Configuration must be carefully designed because inconsistent views can make
troubleshooting difficult.
"""


# ---------------------------------------------------------------------------
# 18. DNSSEC conceptual model
# ---------------------------------------------------------------------------

print_section("15. DNSSEC")

@dataclass
class SignedDNSRecord:
    record: DNSRecord
    signature: str
    key_tag: int


signed_record = SignedDNSRecord(
    record=DNSRecord(
        "secure.example.",
        RecordType.A,
        "192.0.2.50",
        300,
    ),
    signature="SIMULATED-DNSSEC-SIGNATURE",
    key_tag=12345,
)

print("Record:", signed_record.record)
print("Key tag:", signed_record.key_tag)
print("Signature:", signed_record.signature)

print(
    """
DNSSEC adds authenticity and integrity validation to DNS data.

Important concepts:
- DNSKEY: public keys used by a zone.
- RRSIG: signatures over DNS record sets.
- DS: delegation information stored in the parent zone.
- NSEC/NSEC3: authenticated denial-of-existence mechanisms.
- Chain of trust: validation connects a child zone to a trusted root.

DNSSEC does not encrypt ordinary DNS queries.
It is primarily about validating that DNS data is authentic and unmodified.
"""


# ---------------------------------------------------------------------------
# 19. Cache poisoning and security
# ---------------------------------------------------------------------------

print_section("16. DNS security")

print(
    """
A cache-poisoning attack attempts to cause a recursive resolver to cache
malicious DNS data.

Defensive mechanisms include:
- strong transaction identifiers
- randomized source ports
- bailiwick checking
- careful acceptance of additional records
- DNSSEC validation
- modern resolver software
- controlled recursion access

Open recursive resolvers can be abused for reflection/amplification attacks.
Authoritative and recursive roles should be separated when practical.

DNS security is not only cryptographic. Configuration, access control,
software maintenance, monitoring, and response behavior matter as well.
"""


# ---------------------------------------------------------------------------
# 20. DNS failure modes
# ---------------------------------------------------------------------------

print_section("17. Failure modes")

failure_modes = {
    "NOERROR": "The DNS query completed successfully.",
    "NXDOMAIN": "The queried domain name does not exist.",
    "SERVFAIL": "The server could not successfully complete the query.",
    "REFUSED": "The server refuses to perform the requested operation.",
    "TIMEOUT": "No response arrived within the configured interval.",
}

for code, explanation in failure_modes.items():
    print(f"{code:10} {explanation}")

print(
    """
A useful debugging principle is to identify which layer failed:

    Application
        |
    Local stub resolver
        |
    Recursive resolver
        |
    Network path
        |
    Root/TLD
        |
    Authoritative server
        |
    DNS zone configuration

Commands such as nslookup and dig can expose different parts of this path.
"""


# ---------------------------------------------------------------------------
# 21. Retry and timeout simulation
# ---------------------------------------------------------------------------

print_section("18. Timeout and retry logic")

class UnreliableServer:
    def __init__(self, success_probability: float, seed: int = 7) -> None:
        if not 0 <= success_probability <= 1:
            raise ValueError("Probability must be between 0 and 1")
        self.success_probability = success_probability
        self.random = random.Random(seed)

    def request(self) -> bool:
        return self.random.random() < self.success_probability


def query_with_retries(
    server: UnreliableServer,
    retries: int = 3,
) -> str:
    if retries < 0:
        raise ValueError("Retries cannot be negative")

    for attempt in range(1, retries + 2):
        if server.request():
            return f"Success on attempt {attempt}"
    return f"Failure after {retries + 1} attempts"


unreliable = UnreliableServer(0.45)

print(query_with_retries(unreliable, retries=3))

print(
    """
Resolvers commonly implement retry behavior.

Poor retry design can increase load during outages. Practical resolvers must
balance:
- responsiveness
- reliability
- upstream load
- duplicate traffic
- failover behavior
"""


# ---------------------------------------------------------------------------
# 22. Cache capacity and eviction
# ---------------------------------------------------------------------------

print_section("19. Bounded DNS cache")

class BoundedCache:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("Capacity must be positive")
        self.capacity = capacity
        self.data: Dict[str, str] = {}
        self.order: List[str] = []

    def put(self, key: str, value: str) -> None:
        if key in self.data:
            self.order.remove(key)

        self.data[key] = value
        self.order.append(key)

        if len(self.order) > self.capacity:
            oldest = self.order.pop(0)
            del self.data[oldest]

    def get(self, key: str) -> Optional[str]:
        if key not in self.data:
            return None

        value = self.data[key]
        self.order.remove(key)
        self.order.append(key)
        return value


cache = BoundedCache(2)
cache.put("a.example.", "192.0.2.1")
cache.put("b.example.", "192.0.2.2")
print(cache.data)

cache.get("a.example.")
cache.put("c.example.", "192.0.2.3")
print(cache.data)

print(
    """
Real recursive resolvers maintain substantially more sophisticated caches.

Common implementation concerns:
- memory limits
- expiration
- eviction policy
- negative entries
- RRset consistency
- concurrent queries
- cache prefetching
- stale data policies
"""


# ---------------------------------------------------------------------------
# 23. Complexity considerations
# ---------------------------------------------------------------------------

print_section("20. Performance considerations")

print(
    """
Cache lookup:

    Average hash-table lookup: approximately O(1)

Iterative resolution:

    Often requires multiple network round trips.

The exact number varies because:
- referrals can be cached
- NS records can be cached
- glue can be cached
- final answers can be cached
- CNAME chains can add work
- failures can trigger retries

The dominant cost in many DNS scenarios is network latency rather than CPU.
Caching therefore has a large performance impact.
"""


# ---------------------------------------------------------------------------
# 24. Production design checklist
# ---------------------------------------------------------------------------

print_section("21. Production considerations")

checklist = [
    "Use redundant authoritative nameservers.",
    "Use geographically and topologically appropriate DNS infrastructure.",
    "Protect recursive resolvers from unauthorized public recursion.",
    "Monitor latency, SERVFAIL, NXDOMAIN, and timeout rates.",
    "Choose TTL values according to operational requirements.",
    "Use DNSSEC where its validation and operational requirements are appropriate.",
    "Protect registrar and DNS-provider accounts with strong authentication.",
    "Test changes before deployment.",
    "Keep authoritative zone data consistent.",
    "Plan for provider and nameserver failures.",
    "Document split-horizon and delegated-zone behavior.",
]

for item in checklist:
    print("[ ]", item)


# ---------------------------------------------------------------------------
# 25. Mini end-to-end demonstration
# ---------------------------------------------------------------------------

print_section("22. End-to-end DNS resolution demonstration")

def explain_resolution(
    resolver_instance: RecursiveResolver,
    name: str,
    record_type: RecordType,
) -> None:
    print(f"Client asks resolver: {normalize_name(name)} {record_type.value}")

    result = resolver_instance.query(name, record_type)

    print("Result:", result.status)

    if result.answer:
        for record in result.answer:
            print("Answer:", record)

    print("Resolution path:")
    for event in result.trace:
        print("  -", event)


explain_resolution(
    resolver,
    "www.example.com.",
    RecordType.A,
)

print(
    """
The complete conceptual chain is:

    Browser/application
          |
          v
    Operating-system stub resolver
          |
          v
    Recursive resolver
          |
          +--> cache hit ----------------------+
          |                                     |
          +--> cache miss                      |
                    |                           |
                    v                           |
                  root                         |
                    |                           |
                    v                           |
                  TLD                          |
                    |                           |
                    v                           |
             authoritative                    |
                    |                           |
                    v                           |
                DNS answer                     |
                    |                           |
                    +--> cache according to TTL+
                    |
                    v
                application

The central idea is that DNS combines a hierarchical namespace with
distributed authority, recursive resolution, and caching.
"""
)


# ---------------------------------------------------------------------------
# 26. Self-tests
# ---------------------------------------------------------------------------

print_section("23. Self-tests")

assert normalize_name("Example.COM") == "example.com."
assert validate_ipv4("192.0.2.1")
assert not validate_ipv4("300.0.0.1")
assert validate_ipv6("2001:db8::1")

a_records = example_zone.query("example.com.", RecordType.A)
assert len(a_records) == 1
assert a_records[0].value == "93.184.216.34"

cname_records = example_zone.query(
    "www.example.com.",
    RecordType.CNAME,
)
assert cname_records[0].value == "example.com."

assert resolver.query(
    "example.com.",
    RecordType.A,
).status == "NOERROR"

assert resolver.query(
    "unknown.example.com.",
    RecordType.A,
).status == "NXDOMAIN"

assert ipv4_reverse_name("192.0.2.1") == "1.2.0.192.in-addr.arpa."

print("All self-tests passed.")


# ---------------------------------------------------------------------------
# 27. Practical command references
# ---------------------------------------------------------------------------

print_section("24. Useful DNS diagnostic commands")

commands = [
    "nslookup example.com",
    "nslookup -type=MX example.com",
    "nslookup -type=NS example.com",
    "nslookup -type=TXT example.com",
    "dig example.com A",
    "dig example.com AAAA",
    "dig example.com MX",
    "dig +trace example.com",
    "dig @1.1.1.1 example.com",
    "dig -x 192.0.2.1",
]

for command in commands:
    print(command)

print(
    """
The examples above are command references only. The Python program itself
does not require those commands or an Internet connection.

Key distinctions to retain:

1. Authoritative server:
   Owns or serves authoritative DNS data for a zone.

2. Recursive resolver:
   Finds answers on behalf of clients and commonly caches them.

3. Stub resolver:
   A lightweight client-side component that asks another resolver to do
   recursive work.

4. Iterative query:
   The responding DNS server gives the best information it has, such as a
   referral, and the requester continues.

5. Recursive query:
   The requested resolver is asked to obtain the final result.

6. TTL:
   Indicates how long cached DNS data may be retained.

7. NXDOMAIN:
   The queried name does not exist.

8. CNAME:
   Aliases one DNS name to another canonical name.

9. DNSSEC:
   Provides mechanisms for authenticating DNS data and validating integrity.

10. DoT/DoH:
    Encrypt DNS transport between the client and resolver, with different
    transport characteristics.

DNS is therefore both a naming system and a distributed protocol ecosystem.
Understanding hierarchy, authority, recursion, caching, delegation, failure
modes, and security is essential for diagnosing real network behavior.
"""
)
