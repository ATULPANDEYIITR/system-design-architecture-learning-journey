/*
DNS: Domain Resolution, Recursive DNS, and Caching
==================================================

C++17 case study: a production-oriented conceptual DNS resolver for a
distributed web application.

Scenario
--------
A company operates:

    api.acme.test
    www.acme.test
    mail.acme.test

The application must resolve hostnames efficiently while handling:

- authoritative records
- CNAME aliases
- recursive resolution
- caching
- TTL expiration
- NXDOMAIN
- SERVFAIL
- retries
- multiple addresses
- validation
- statistics
- concurrent application requests

This is a simulation rather than a wire-compatible DNS implementation.
It deliberately models the architecture and algorithms without requiring
external networking libraries.

Compile:
    g++ -std=c++17 -O2 -Wall -Wextra -pedantic dns_case_study.cpp -o dns_case_study
*/

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using Clock = std::chrono::steady_clock;


// ---------------------------------------------------------------------------
// 1. DNS record types and status codes
// ---------------------------------------------------------------------------

enum class RecordType {
    A,
    AAAA,
    CNAME,
    NS,
    MX,
    TXT,
    SOA,
    PTR
};

enum class DNSStatus {
    NOERROR,
    NXDOMAIN,
    SERVFAIL,
    REFUSED,
    TIMEOUT
};

std::string toString(RecordType type) {
    switch (type) {
        case RecordType::A: return "A";
        case RecordType::AAAA: return "AAAA";
        case RecordType::CNAME: return "CNAME";
        case RecordType::NS: return "NS";
        case RecordType::MX: return "MX";
        case RecordType::TXT: return "TXT";
        case RecordType::SOA: return "SOA";
        case RecordType::PTR: return "PTR";
    }

    throw std::logic_error("Unknown record type");
}

std::string toString(DNSStatus status) {
    switch (status) {
        case DNSStatus::NOERROR: return "NOERROR";
        case DNSStatus::NXDOMAIN: return "NXDOMAIN";
        case DNSStatus::SERVFAIL: return "SERVFAIL";
        case DNSStatus::REFUSED: return "REFUSED";
        case DNSStatus::TIMEOUT: return "TIMEOUT";
    }

    throw std::logic_error("Unknown DNS status");
}


// ---------------------------------------------------------------------------
// 2. DNS record representation
// ---------------------------------------------------------------------------

struct DNSRecord {
    std::string name;
    RecordType type;
    std::string value;
    std::uint32_t ttl;

    DNSRecord(
        std::string recordName,
        RecordType recordType,
        std::string recordValue,
        std::uint32_t recordTTL
    )
        : name(std::move(recordName)),
          type(recordType),
          value(std::move(recordValue)),
          ttl(recordTTL) {}
};

std::ostream& operator<<(std::ostream& output, const DNSRecord& record) {
    output
        << record.name
        << " "
        << record.ttl
        << " IN "
        << toString(record.type)
        << " "
        << record.value;

    return output;
}


// ---------------------------------------------------------------------------
// 3. DNS utility functions
// ---------------------------------------------------------------------------

std::string normalizeName(std::string name) {
    if (name.empty()) {
        throw std::invalid_argument("DNS name cannot be empty");
    }

    std::transform(
        name.begin(),
        name.end(),
        name.begin(),
        [](unsigned char character) {
            return static_cast<char>(std::tolower(character));
        }
    );

    while (!name.empty() && std::isspace(
        static_cast<unsigned char>(name.back())
    )) {
        name.pop_back();
    }

    std::size_t firstNonSpace = 0;

    while (
        firstNonSpace < name.size() &&
        std::isspace(static_cast<unsigned char>(name[firstNonSpace]))
    ) {
        ++firstNonSpace;
    }

    name = name.substr(firstNonSpace);

    if (name.empty()) {
        throw std::invalid_argument("DNS name cannot be whitespace");
    }

    if (name.back() != '.') {
        name.push_back('.');
    }

    return name;
}

std::string tldOf(const std::string& name) {
    const std::string normalized = normalizeName(name);

    std::string withoutRoot = normalized.substr(
        0,
        normalized.size() - 1
    );

    const std::size_t position = withoutRoot.rfind('.');

    if (position == std::string::npos) {
        return ".";
    }

    return withoutRoot.substr(position + 1) + ".";
}

std::string secondLevelZone(const std::string& name) {
    const std::string normalized = normalizeName(name);

    std::string withoutRoot = normalized.substr(
        0,
        normalized.size() - 1
    );

    const std::size_t lastDot = withoutRoot.rfind('.');

    if (lastDot == std::string::npos) {
        return normalized;
    }

    const std::size_t secondLastDot =
        withoutRoot.rfind('.', lastDot - 1);

    if (secondLastDot == std::string::npos) {
        return normalized;
    }

    return withoutRoot.substr(secondLastDot + 1) + ".";
}


// ---------------------------------------------------------------------------
// 4. DNS query key
// ---------------------------------------------------------------------------

struct QueryKey {
    std::string name;
    RecordType type;

    bool operator==(const QueryKey& other) const {
        return name == other.name && type == other.type;
    }
};

struct QueryKeyHash {
    std::size_t operator()(const QueryKey& key) const {
        const std::size_t first =
            std::hash<std::string>{}(key.name);

        const std::size_t second =
            std::hash<int>{}(static_cast<int>(key.type));

        return first ^ (
            second +
            0x9e3779b9 +
            (first << 6) +
            (first >> 2)
        );
    }
};


// ---------------------------------------------------------------------------
// 5. Query result
// ---------------------------------------------------------------------------

struct QueryResult {
    DNSStatus status;
    std::vector<DNSRecord> answers;
    std::vector<std::string> trace;
};


// ---------------------------------------------------------------------------
// 6. Authoritative DNS zone
// ---------------------------------------------------------------------------

class DNSZone {
private:
    std::string origin_;

    std::unordered_map<QueryKey, std::vector<DNSRecord>, QueryKeyHash>
        records_;

public:
    explicit DNSZone(std::string origin)
        : origin_(normalizeName(std::move(origin))) {}

    const std::string& origin() const {
        return origin_;
    }

    void addRecord(const DNSRecord& record) {
        const QueryKey key{
            normalizeName(record.name),
            record.type
        };

        records_[key].push_back(record);
    }

    std::vector<DNSRecord> query(
        const std::string& name,
        RecordType type
    ) const {
        const QueryKey key{
            normalizeName(name),
            type
        };

        const auto iterator = records_.find(key);

        if (iterator == records_.end()) {
            return {};
        }

        return iterator->second;
    }
};


// ---------------------------------------------------------------------------
// 7. Authoritative nameserver
// ---------------------------------------------------------------------------

class AuthoritativeServer {
private:
    std::string name_;

    std::unordered_map<std::string, DNSZone> zones_;

public:
    explicit AuthoritativeServer(std::string name)
        : name_(normalizeName(std::move(name))) {}

    const std::string& name() const {
        return name_;
    }

    void addZone(DNSZone zone) {
        zones_.emplace(zone.origin(), std::move(zone));
    }

    const DNSZone* findZone(const std::string& name) const {
        const std::string normalized = normalizeName(name);

        for (const auto& [origin, zone] : zones_) {
            if (
                normalized == origin ||
                (
                    normalized.size() > origin.size() &&
                    normalized.ends_with(origin)
                )
            ) {
                return &zone;
            }
        }

        return nullptr;
    }

    QueryResult query(
        const std::string& name,
        RecordType type
    ) const {
        const DNSZone* zone = findZone(name);

        if (zone == nullptr) {
            return {
                DNSStatus::REFUSED,
                {},
                {name_ + ": zone unavailable"}
            };
        }

        auto answers = zone->query(name, type);

        if (!answers.empty()) {
            return {
                DNSStatus::NOERROR,
                answers,
                {name_ + ": authoritative answer"}
            };
        }

        // A CNAME can answer the name even when the requested type is A,
        // AAAA, MX, and so on. The resolver can then follow the target.
        if (type != RecordType::CNAME) {
            auto aliases = zone->query(name, RecordType::CNAME);

            if (!aliases.empty()) {
                return {
                    DNSStatus::NOERROR,
                    aliases,
                    {name_ + ": CNAME encountered"}
                };
            }
        }

        return {
            DNSStatus::NXDOMAIN,
            {},
            {name_ + ": name not found"}
        };
    }
};


// ---------------------------------------------------------------------------
// 8. Simulated DNS hierarchy
// ---------------------------------------------------------------------------

class DNSHierarchy {
private:
    std::unordered_map<std::string, std::vector<std::string>>
        rootDelegations_;

    std::unordered_map<std::string, std::vector<std::string>>
        tldDelegations_;

    std::unordered_map<std::string, std::shared_ptr<AuthoritativeServer>>
        authoritativeServers_;

public:
    void addRootDelegation(
        const std::string& tld,
        std::vector<std::string> nameservers
    ) {
        rootDelegations_[normalizeName(tld)] = std::move(nameservers);
    }

    void addTLDDelegation(
        const std::string& zone,
        std::vector<std::string> nameservers
    ) {
        tldDelegations_[normalizeName(zone)] = std::move(nameservers);
    }

    void addAuthoritativeServer(
        std::shared_ptr<AuthoritativeServer> server
    ) {
        authoritativeServers_[server->name()] = std::move(server);
    }

    QueryResult iterativeResolve(
        const std::string& queryName,
        RecordType type
    ) const {
        const std::string name = normalizeName(queryName);

        std::vector<std::string> trace{
            "Resolver begins iterative resolution"
        };

        const std::string tld = tldOf(name);

        if (!rootDelegations_.contains(tld)) {
            trace.push_back("Root: no TLD delegation");
            return {
                DNSStatus::NXDOMAIN,
                {},
                trace
            };
        }

        trace.push_back(
            "Root: referral for " + tld
        );

        const std::string zone = secondLevelZone(name);

        auto delegationIterator = tldDelegations_.find(zone);

        if (delegationIterator == tldDelegations_.end()) {
            trace.push_back(
                "TLD: no delegation for " + zone
            );

            return {
                DNSStatus::NXDOMAIN,
                {},
                trace
            };
        }

        const auto& nameservers = delegationIterator->second;

        trace.push_back(
            "TLD: referral to " +
            std::to_string(nameservers.size()) +
            " authoritative server(s)"
        );

        for (const auto& nameserver : nameservers) {
            auto serverIterator =
                authoritativeServers_.find(
                    normalizeName(nameserver)
                );

            if (serverIterator == authoritativeServers_.end()) {
                trace.push_back(
                    nameserver + ": unavailable"
                );
                continue;
            }

            QueryResult result =
                serverIterator->second->query(name, type);

            trace.insert(
                trace.end(),
                result.trace.begin(),
                result.trace.end()
            );

            if (result.status == DNSStatus::NOERROR) {
                // If the authoritative response is a CNAME, follow it.
                if (
                    result.answers.size() == 1 &&
                    result.answers[0].type == RecordType::CNAME &&
                    type != RecordType::CNAME
                ) {
                    const std::string target =
                        result.answers[0].value;

                    trace.push_back(
                        "Resolver follows CNAME to " + target
                    );

                    QueryResult targetResult =
                        iterativeResolve(target, type);

                    trace.insert(
                        trace.end(),
                        targetResult.trace.begin(),
                        targetResult.trace.end()
                    );

                    return {
                        targetResult.status,
                        targetResult.answers,
                        trace
                    };
                }

                return {
                    result.status,
                    result.answers,
                    trace
                };
            }
        }

        trace.push_back(
            "No authoritative server produced a successful answer"
        );

        return {
            DNSStatus::SERVFAIL,
            {},
            trace
        };
    }
};


// ---------------------------------------------------------------------------
// 9. Cache entry
// ---------------------------------------------------------------------------

struct CacheEntry {
    DNSStatus status;
    std::vector<DNSRecord> records;
    Clock::time_point expiresAt;

    bool expired(Clock::time_point now) const {
        return now >= expiresAt;
    }
};


// ---------------------------------------------------------------------------
// 10. Recursive resolver
// ---------------------------------------------------------------------------

class RecursiveResolver {
private:
    const DNSHierarchy& hierarchy_;

    std::unordered_map<QueryKey, CacheEntry, QueryKeyHash>
        cache_;

    std::size_t cacheHits_ = 0;
    std::size_t cacheMisses_ = 0;
    std::size_t upstreamQueries_ = 0;

public:
    explicit RecursiveResolver(const DNSHierarchy& hierarchy)
        : hierarchy_(hierarchy) {}

    QueryResult query(
        const std::string& queryName,
        RecordType type
    ) {
        const std::string name = normalizeName(queryName);

        const QueryKey key{name, type};

        const auto now = Clock::now();

        auto cacheIterator = cache_.find(key);

        if (
            cacheIterator != cache_.end() &&
            !cacheIterator->second.expired(now)
        ) {
            ++cacheHits_;

            const auto remaining =
                std::chrono::duration_cast<std::chrono::seconds>(
                    cacheIterator->second.expiresAt - now
                ).count();

            return {
                cacheIterator->second.status,
                cacheIterator->second.records,
                {
                    "Cache hit; remaining TTL=" +
                    std::to_string(remaining) +
                    "s"
                }
            };
        }

        if (cacheIterator != cache_.end()) {
            cache_.erase(cacheIterator);
        }

        ++cacheMisses_;
        ++upstreamQueries_;

        QueryResult result =
            hierarchy_.iterativeResolve(name, type);

        if (!result.answers.empty()) {
            std::uint32_t minimumTTL =
                result.answers.front().ttl;

            for (const auto& record : result.answers) {
                minimumTTL =
                    std::min(minimumTTL, record.ttl);
            }

            cache_[key] = CacheEntry{
                result.status,
                result.answers,
                now + std::chrono::seconds(minimumTTL)
            };
        } else if (result.status == DNSStatus::NXDOMAIN) {
            // A real resolver derives negative-cache duration from SOA data.
            cache_[key] = CacheEntry{
                DNSStatus::NXDOMAIN,
                {},
                now + std::chrono::seconds(30)
            };
        }

        result.trace.insert(
            result.trace.begin(),
            "Cache miss"
        );

        return result;
    }

    void printStatistics() const {
        std::cout
            << "Cache hits: " << cacheHits_ << '\n'
            << "Cache misses: " << cacheMisses_ << '\n'
            << "Upstream queries: " << upstreamQueries_ << '\n';
    }
};


// ---------------------------------------------------------------------------
// 11. Round-robin address selection
// ---------------------------------------------------------------------------

class RoundRobinSelector {
private:
    std::vector<std::string> addresses_;
    std::size_t index_ = 0;

public:
    explicit RoundRobinSelector(
        std::vector<std::string> addresses
    )
        : addresses_(std::move(addresses)) {
        if (addresses_.empty()) {
            throw std::invalid_argument(
                "At least one address is required"
            );
        }
    }

    const std::string& next() {
        const std::string& selected =
            addresses_[index_];

        index_ = (index_ + 1) % addresses_.size();

        return selected;
    }
};


// ---------------------------------------------------------------------------
// 12. Simulated retry policy
// ---------------------------------------------------------------------------

class RetryPolicy {
private:
    std::size_t maximumRetries_;

public:
    explicit RetryPolicy(std::size_t maximumRetries)
        : maximumRetries_(maximumRetries) {}

    template <typename Operation>
    QueryResult execute(Operation operation) const {
        QueryResult last{
            DNSStatus::SERVFAIL,
            {},
            {}
        };

        for (
            std::size_t attempt = 0;
            attempt <= maximumRetries_;
            ++attempt
        ) {
            last = operation(attempt + 1);

            if (
                last.status != DNSStatus::TIMEOUT &&
                last.status != DNSStatus::SERVFAIL
            ) {
                return last;
            }

            last.trace.push_back(
                "Retry policy: attempt " +
                std::to_string(attempt + 1)
            );
        }

        return last;
    }
};


// ---------------------------------------------------------------------------
// 13. DNS application client
// ---------------------------------------------------------------------------

class ApplicationClient {
private:
    RecursiveResolver& resolver_;

public:
    explicit ApplicationClient(RecursiveResolver& resolver)
        : resolver_(resolver) {}

    std::vector<std::string> resolveHost(
        const std::string& hostname
    ) {
        QueryResult result =
            resolver_.query(hostname, RecordType::A);

        if (result.status != DNSStatus::NOERROR) {
            throw std::runtime_error(
                "Application DNS failure: " +
                toString(result.status)
            );
        }

        if (result.answers.empty()) {
            throw std::runtime_error(
                "DNS returned no usable addresses"
            );
        }

        std::vector<std::string> addresses;

        for (const auto& record : result.answers) {
            if (record.type == RecordType::A) {
                addresses.push_back(record.value);
            }
        }

        if (addresses.empty()) {
            throw std::runtime_error(
                "No A records in successful DNS response"
            );
        }

        return addresses;
    }
};


// ---------------------------------------------------------------------------
// 14. Demonstration helpers
// ---------------------------------------------------------------------------

void printResult(
    const std::string& label,
    const QueryResult& result
) {
    std::cout << '\n'
              << label << '\n'
              << "Status: "
              << toString(result.status)
              << '\n';

    for (const auto& record : result.answers) {
        std::cout << "Answer: "
                  << record
                  << '\n';
    }

    std::cout << "Trace:\n";

    for (const auto& item : result.trace) {
        std::cout << "  - "
                  << item
                  << '\n';
    }
}


// ---------------------------------------------------------------------------
// 15. Build realistic test infrastructure
// ---------------------------------------------------------------------------

DNSHierarchy buildInfrastructure() {
    DNSZone acmeZone("acme.test.");

    acmeZone.addRecord(
        DNSRecord(
            "acme.test.",
            RecordType.A,
            "198.51.100.10",
            3600
        )
    );

    acmeZone.addRecord(
        DNSRecord(
            "www.acme.test.",
            RecordType.CNAME,
            "acme.test.",
            300
        )
    );

    acmeZone.addRecord(
        DNSRecord(
            "api.acme.test.",
            RecordType.A,
            "198.51.100.20",
            60
        )
    );

    acmeZone.addRecord(
        DNSRecord(
            "api.acme.test.",
            RecordType.A,
            "198.51.100.21",
            60
        )
    );

    acmeZone.addRecord(
        DNSRecord(
            "mail.acme.test.",
            RecordType.A,
            "198.51.100.30",
            300
        )
    );

    acmeZone.addRecord(
        DNSRecord(
            "acme.test.",
            RecordType.MX,
            "10 mail.acme.test.",
            1800
        )
    );

    auto server1 =
        std::make_shared<AuthoritativeServer>(
            "ns1.acme.test."
        );

    server1->addZone(acmeZone);

    auto server2 =
        std::make_shared<AuthoritativeServer>(
            "ns2.acme.test."
        );

    // The second server receives the same zone data in this simulation.
    DNSZone replica("acme.test.");

    replica.addRecord(
        DNSRecord(
            "acme.test.",
            RecordType.A,
            "198.51.100.10",
            3600
        )
    );

    replica.addRecord(
        DNSRecord(
            "www.acme.test.",
            RecordType.CNAME,
            "acme.test.",
            300
        )
    );

    replica.addRecord(
        DNSRecord(
            "api.acme.test.",
            RecordType.A,
            "198.51.100.20",
            60
        )
    );

    replica.addRecord(
        DNSRecord(
            "api.acme.test.",
            RecordType.A,
            "198.51.100.21",
            60
        )
    );

    replica.addRecord(
        DNSRecord(
            "mail.acme.test.",
            RecordType.A,
            "198.51.100.30",
            300
        )
    );

    replica.addRecord(
        DNSRecord(
            "acme.test.",
            RecordType.MX,
            "10 mail.acme.test.",
            1800
        )
    );

    server2->addZone(replica);

    DNSHierarchy hierarchy;

    hierarchy.addRootDelegation(
        "test.",
        {
            "a.test-root.example.",
            "b.test-root.example."
        }
    );

    hierarchy.addTLDDelegation(
        "acme.test.",
        {
            "ns1.acme.test.",
            "ns2.acme.test."
        }
    );

    hierarchy.addAuthoritativeServer(server1);
    hierarchy.addAuthoritativeServer(server2);

    return hierarchy;
}


// ---------------------------------------------------------------------------
// 16. Unit-test-like assertions
// ---------------------------------------------------------------------------

void require(
    bool condition,
    const std::string& message
) {
    if (!condition) {
        throw std::runtime_error(
            "TEST FAILURE: " + message
        );
    }
}

void runTests() {
    require(
        normalizeName("Example.COM") == "example.com.",
        "DNS normalization"
    );

    require(
        tldOf("www.acme.test.") == "test.",
        "TLD extraction"
    );

    require(
        secondLevelZone("www.acme.test.") == "acme.test.",
        "Zone extraction"
    );

    DNSHierarchy hierarchy = buildInfrastructure();

    QueryResult result =
        hierarchy.iterativeResolve(
            "api.acme.test.",
            RecordType.A
        );

    require(
        result.status == DNSStatus::NOERROR,
        "A lookup"
    );

    require(
        result.answers.size() == 2,
        "Multiple A records"
    );

    QueryResult cnameResult =
        hierarchy.iterativeResolve(
            "www.acme.test.",
            RecordType.A
        );

    require(
        cnameResult.status == DNSStatus::NOERROR,
        "CNAME lookup"
    );

    require(
        !cnameResult.answers.empty(),
        "CNAME target answer"
    );

    require(
        cnameResult.answers.front().value ==
        "198.51.100.10",
        "CNAME target value"
    );

    QueryResult missing =
        hierarchy.iterativeResolve(
            "missing.acme.test.",
            RecordType.A
        );

    require(
        missing.status == DNSStatus::NXDOMAIN,
        "NXDOMAIN behavior"
    );

    std::cout
        << "\nAll C++ tests passed.\n";
}


// ---------------------------------------------------------------------------
// 17. Main technical case study
// ---------------------------------------------------------------------------

int main() {
    try {
        std::cout
            << "============================================================\n"
            << "DNS recursive resolution and caching case study\n"
            << "============================================================\n";

        DNSHierarchy hierarchy =
            buildInfrastructure();

        RecursiveResolver resolver(hierarchy);

        // ---------------------------------------------------------------
        // Initial resolution
        // ---------------------------------------------------------------

        QueryResult first =
            resolver.query(
                "api.acme.test.",
                RecordType::A
            );

        printResult(
            "1. First API lookup",
            first
        );

        // ---------------------------------------------------------------
        // Cached resolution
        // ---------------------------------------------------------------

        QueryResult second =
            resolver.query(
                "api.acme.test.",
                RecordType::A
            );

        printResult(
            "2. Repeated API lookup",
            second
        );

        // ---------------------------------------------------------------
        // CNAME
        // ---------------------------------------------------------------

        QueryResult website =
            resolver.query(
                "www.acme.test.",
                RecordType::A
            );

        printResult(
            "3. Website CNAME lookup",
            website
        );

        // ---------------------------------------------------------------
        // MX
        // ---------------------------------------------------------------

        QueryResult mail =
            resolver.query(
                "acme.test.",
                RecordType::MX
            );

        printResult(
            "4. Mail exchanger lookup",
            mail
        );

        // ---------------------------------------------------------------
        // Negative caching
        // ---------------------------------------------------------------

        QueryResult missing =
            resolver.query(
                "does-not-exist.acme.test.",
                RecordType::A
            );

        printResult(
            "5. Missing hostname",
            missing
        );

        QueryResult missingAgain =
            resolver.query(
                "does-not-exist.acme.test.",
                RecordType::A
            );

        printResult(
            "6. Repeated missing hostname",
            missingAgain
        );

        // ---------------------------------------------------------------
        // Round-robin application selection
        // ---------------------------------------------------------------

        std::vector<std::string> addresses;

        for (const auto& record : first.answers) {
            if (record.type == RecordType::A) {
                addresses.push_back(record.value);
            }
        }

        RoundRobinSelector selector(addresses);

        std::cout
            << "\n7. Application address selection\n";

        for (int attempt = 1; attempt <= 6; ++attempt) {
            std::cout
                << "Request "
                << attempt
                << " -> "
                << selector.next()
                << '\n';
        }

        // ---------------------------------------------------------------
        // Application client
        // ---------------------------------------------------------------

        ApplicationClient application(
            resolver
        );

        std::cout
            << "\n8. Application client resolution\n";

        const auto resolved =
            application.resolveHost(
                "api.acme.test."
            );

        for (const auto& address : resolved) {
            std::cout
                << "Usable address: "
                << address
                << '\n';
        }

        // ---------------------------------------------------------------
        // Statistics
        // ---------------------------------------------------------------

        std::cout
            << "\n9. Resolver statistics\n";

        resolver.printStatistics();

        // ---------------------------------------------------------------
        // Complexity and architectural notes
        // ---------------------------------------------------------------

        std::cout
            << "\n10. Engineering analysis\n"
            << "Cache lookup is approximately O(1) on average with a hash table.\n"
            << "Cache misses may require several network round trips.\n"
            << "CNAME chains increase resolution work.\n"
            << "Multiple authoritative servers improve resilience.\n"
            << "TTL controls cache lifetime and change propagation speed.\n"
            << "Negative caching reduces repeated failed upstream lookups.\n"
            << "Unrestricted recursion can create security and abuse risks.\n"
            << "DNSSEC validates authenticity and integrity but does not encrypt DNS transport.\n"
            << "DoT and DoH protect DNS transport but solve a different problem from DNSSEC.\n";

        // ---------------------------------------------------------------
        // Failure-condition demonstration
        // ---------------------------------------------------------------

        RetryPolicy retryPolicy(2);

        int simulatedAttempts = 0;

        QueryResult retryResult =
            retryPolicy.execute(
                [&](std::size_t attempt) {
                    ++simulatedAttempts;

                    if (attempt < 3) {
                        return QueryResult{
                            DNSStatus::TIMEOUT,
                            {},
                            {
                                "Simulated authoritative timeout"
                            }
                        };
                    }

                    return hierarchy.iterativeResolve(
                        "api.acme.test.",
                        RecordType::A
                    );
                }
            );

        printResult(
            "11. Timeout and retry demonstration",
            retryResult
        );

        std::cout
            << "Attempts made: "
            << simulatedAttempts
            << '\n';

        // ---------------------------------------------------------------
        // Tests
        // ---------------------------------------------------------------

        runTests();

        std::cout
            << "\nCase study completed successfully.\n";

        return 0;
    }
    catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}
