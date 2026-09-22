/*
 * HTTPS & TLS: Industry-Style Secure API Gateway Case Study
 *
 * Standard: C++17
 *
 * This case study models the security responsibilities of an HTTPS API
 * gateway without implementing TLS itself. Real TLS implementations should
 * use mature protocol libraries rather than custom cryptographic code.
 *
 * The program demonstrates:
 *   - HTTP request validation
 *   - certificate metadata
 *   - certificate-chain modeling
 *   - hostname verification
 *   - session establishment
 *   - authenticated application messages
 *   - replay protection
 *   - authorization
 *   - rate limiting
 *   - audit logging
 *   - security headers
 *   - failure handling
 *   - complexity and architectural trade-offs
 */

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;

// ============================================================================
// Utility functions
// ============================================================================

string toLower(string value) {
    transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](unsigned char c) {
            return static_cast<char>(tolower(c));
        }
    );

    return value;
}

string trim(const string& value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == string::npos) {
        return "";
    }

    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

string join(const vector<string>& values, const string& delimiter) {
    ostringstream output;

    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            output << delimiter;
        }

        output << values[i];
    }

    return output.str();
}

// ============================================================================
// HTTP request model
// ============================================================================

struct HttpRequest {
    string method;
    string path;
    string host;
    map<string, string> headers;
    string body;
};

struct HttpResponse {
    int statusCode;
    map<string, string> headers;
    string body;
};

string getHeader(const HttpRequest& request, const string& name) {
    const string target = toLower(name);

    for (const auto& [key, value] : request.headers) {
        if (toLower(key) == target) {
            return value;
        }
    }

    return "";
}

// ============================================================================
// Certificate representation
// ============================================================================

struct Certificate {
    string subject;
    string issuer;
    vector<string> subjectAlternativeNames;
    bool isCertificateAuthority;
    bool expired;
    bool revoked;
    string publicKeyFingerprint;
};

class CertificateValidator {
public:
    bool verifyHostname(
        const Certificate& certificate,
        const string& hostname
    ) const {
        const string normalizedHostname = toLower(hostname);

        for (const string& name : certificate.subjectAlternativeNames) {
            if (matchesDNSName(toLower(name), normalizedHostname)) {
                return true;
            }
        }

        return false;
    }

    bool verifyChain(
        const Certificate& leaf,
        const vector<Certificate>& intermediates,
        const set<string>& trustedRoots
    ) const {
        if (leaf.expired) {
            return false;
        }

        if (leaf.revoked) {
            return false;
        }

        const Certificate* current = &leaf;
        set<string> visited;

        while (true) {
            if (visited.count(current->subject)) {
                return false;
            }

            visited.insert(current->subject);

            if (trustedRoots.count(current->issuer)) {
                return true;
            }

            auto issuer = find_if(
                intermediates.begin(),
                intermediates.end(),
                [&](const Certificate& candidate) {
                    return candidate.subject == current->issuer;
                }
            );

            if (issuer == intermediates.end()) {
                return false;
            }

            if (!issuer->isCertificateAuthority) {
                return false;
            }

            if (issuer->expired || issuer->revoked) {
                return false;
            }

            current = &(*issuer);
        }
    }

private:
    bool matchesDNSName(
        const string& pattern,
        const string& hostname
    ) const {
        if (pattern == hostname) {
            return true;
        }

        /*
         * Simplified wildcard rule:
         * *.example.com matches api.example.com but not
         * a.b.example.com.
         */
        if (pattern.rfind("*.", 0) != 0) {
            return false;
        }

        const string suffix = pattern.substr(1);

        if (hostname.size() <= suffix.size()) {
            return false;
        }

        if (hostname.compare(
                hostname.size() - suffix.size(),
                suffix.size(),
                suffix
            ) != 0) {
            return false;
        }

        return count(hostname.begin(), hostname.end(), '.') ==
               count(pattern.begin(), pattern.end(), '.');
    }
};

// ============================================================================
// TLS session model
// ============================================================================

enum class TLSVersion {
    TLS12,
    TLS13
};

string toString(TLSVersion version) {
    switch (version) {
        case TLSVersion::TLS12:
            return "TLS 1.2";
        case TLSVersion::TLS13:
            return "TLS 1.3";
    }

    return "Unknown";
}

struct TLSParameters {
    TLSVersion version;
    string cipherSuite;
    bool certificateVerified;
    bool hostnameVerified;
    bool forwardSecrecy;
};

class TLSSession {
public:
    explicit TLSSession(TLSParameters parameters)
        : parameters_(move(parameters)),
          established_(false) {}

    bool establish() {
        if (!parameters_.certificateVerified) {
            return false;
        }

        if (!parameters_.hostnameVerified) {
            return false;
        }

        established_ = true;
        return true;
    }

    bool isEstablished() const {
        return established_;
    }

    const TLSParameters& parameters() const {
        return parameters_;
    }

private:
    TLSParameters parameters_;
    bool established_;
};

// ============================================================================
// Application authentication
// ============================================================================

struct User {
    string id;
    string role;
    bool active;
};

class AuthorizationService {
public:
    bool canReadAccount(const User& user) const {
        return user.active &&
               (user.role == "customer" ||
                user.role == "support" ||
                user.role == "admin");
    }

    bool canReadAuditLog(const User& user) const {
        return user.active &&
               (user.role == "security" ||
                user.role == "admin");
    }
};

// ============================================================================
// Replay protection
// ============================================================================

class ReplayProtection {
public:
    explicit ReplayProtection(size_t maximumEntries)
        : maximumEntries_(maximumEntries) {}

    bool accept(const string& requestId) {
        if (requestId.empty()) {
            return false;
        }

        if (seen_.count(requestId)) {
            return false;
        }

        if (seen_.size() >= maximumEntries_) {
            /*
             * A production implementation would normally use expiration
             * timestamps or a bounded cache rather than simply rejecting
             * everything when the set reaches capacity.
             */
            return false;
        }

        seen_.insert(requestId);
        return true;
    }

    size_t size() const {
        return seen_.size();
    }

private:
    size_t maximumEntries_;
    set<string> seen_;
};

// ============================================================================
// Rate limiting
// ============================================================================

class RateLimiter {
public:
    RateLimiter(size_t maximumRequests, long long windowSeconds)
        : maximumRequests_(maximumRequests),
          windowSeconds_(windowSeconds) {}

    bool allow(const string& clientId, long long currentTime) {
        auto& requests = requestTimes_[clientId];

        while (!requests.empty() &&
               currentTime - requests.front() >= windowSeconds_) {
            requests.erase(requests.begin());
        }

        if (requests.size() >= maximumRequests_) {
            return false;
        }

        requests.push_back(currentTime);
        return true;
    }

private:
    size_t maximumRequests_;
    long long windowSeconds_;
    unordered_map<string, vector<long long>> requestTimes_;
};

// ============================================================================
// Audit logging
// ============================================================================

struct AuditEvent {
    string requestId;
    string userId;
    string action;
    string result;
};

class AuditLogger {
public:
    void record(
        const string& requestId,
        const string& userId,
        const string& action,
        const string& result
    ) {
        events_.push_back({
            requestId,
            userId,
            action,
            result
        });
    }

    void print() const {
        cout << "\n=== AUDIT LOG ===\n";

        for (const auto& event : events_) {
            cout
                << "request=" << event.requestId
                << " user=" << event.userId
                << " action=" << event.action
                << " result=" << event.result
                << '\n';
        }
    }

private:
    vector<AuditEvent> events_;
};

// ============================================================================
// Secure gateway
// ============================================================================

class SecureApiGateway {
public:
    SecureApiGateway()
        : validator_(),
          replayProtection_(1000),
          rateLimiter_(5, 60) {}

    bool establishTLS(
        const Certificate& leaf,
        const vector<Certificate>& intermediates,
        const set<string>& trustedRoots,
        const string& hostname
    ) {
        cout << "\n=== TLS HANDSHAKE ===\n";

        const bool hostnameValid =
            validator_.verifyHostname(leaf, hostname);

        const bool chainValid =
            validator_.verifyChain(
                leaf,
                intermediates,
                trustedRoots
            );

        cout << "Certificate chain valid: "
             << boolalpha << chainValid << '\n';

        cout << "Hostname valid: "
             << boolalpha << hostnameValid << '\n';

        TLSParameters parameters{
            TLSVersion::TLS13,
            "TLS_AES_128_GCM_SHA256",
            chainValid,
            hostnameValid,
            true
        };

        tlsSession_.emplace(parameters);

        if (!tlsSession_->establish()) {
            cout << "TLS session rejected.\n";
            return false;
        }

        cout << "TLS session established.\n";
        cout << "Protocol: "
             << toString(parameters.version) << '\n';
        cout << "Cipher: "
             << parameters.cipherSuite << '\n';
        cout << "Forward secrecy: "
             << boolalpha << parameters.forwardSecrecy << '\n';

        return true;
    }

    HttpResponse handleRequest(
        const HttpRequest& request,
        const User& user,
        long long currentTime
    ) {
        HttpResponse response{
            500,
            {},
            "Internal error"
        };

        applySecurityHeaders(response);

        const string requestId =
            getHeader(request, "X-Request-ID");

        if (!tlsSession_.has_value() ||
            !tlsSession_->isEstablished()) {
            response.statusCode = 400;
            response.body = "Secure TLS session required";
            return response;
        }

        if (request.method.empty() ||
            request.path.empty() ||
            request.host.empty()) {
            response.statusCode = 400;
            response.body = "Malformed request";
            return response;
        }

        if (!replayProtection_.accept(requestId)) {
            response.statusCode = 409;
            response.body = "Duplicate or invalid request identifier";

            audit_.record(
                requestId,
                user.id,
                request.path,
                "replay-rejected"
            );

            return response;
        }

        if (!rateLimiter_.allow(user.id, currentTime)) {
            response.statusCode = 429;
            response.body = "Rate limit exceeded";

            audit_.record(
                requestId,
                user.id,
                request.path,
                "rate-limited"
            );

            return response;
        }

        if (!user.active) {
            response.statusCode = 401;
            response.body = "Inactive user";

            audit_.record(
                requestId,
                user.id,
                request.path,
                "authentication-rejected"
            );

            return response;
        }

        if (request.path == "/api/account") {
            if (!authorization_.canReadAccount(user)) {
                response.statusCode = 403;
                response.body = "Insufficient permissions";

                audit_.record(
                    requestId,
                    user.id,
                    request.path,
                    "authorization-denied"
                );

                return response;
            }

            response.statusCode = 200;
            response.body =
                "{\"user\":\"" + user.id +
                "\",\"role\":\"" + user.role + "\"}";

            audit_.record(
                requestId,
                user.id,
                request.path,
                "success"
            );

            return response;
        }

        if (request.path == "/api/audit") {
            if (!authorization_.canReadAuditLog(user)) {
                response.statusCode = 403;
                response.body = "Security role required";

                audit_.record(
                    requestId,
                    user.id,
                    request.path,
                    "authorization-denied"
                );

                return response;
            }

            response.statusCode = 200;
            response.body = "Audit access granted";

            audit_.record(
                requestId,
                user.id,
                request.path,
                "success"
            );

            return response;
        }

        response.statusCode = 404;
        response.body = "Resource not found";

        audit_.record(
            requestId,
            user.id,
            request.path,
            "not-found"
        );

        return response;
    }

    void printAuditLog() const {
        audit_.print();
    }

private:
    void applySecurityHeaders(HttpResponse& response) const {
        response.headers["Strict-Transport-Security"] =
            "max-age=31536000; includeSubDomains";

        response.headers["Content-Security-Policy"] =
            "default-src 'self'";

        response.headers["X-Content-Type-Options"] =
            "nosniff";

        response.headers["Referrer-Policy"] =
            "strict-origin-when-cross-origin";

        response.headers["Cache-Control"] =
            "no-store";
    }

    CertificateValidator validator_;
    optional<TLSSession> tlsSession_;
    AuthorizationService authorization_;
    ReplayProtection replayProtection_;
    RateLimiter rateLimiter_;
    AuditLogger audit_;
};

// ============================================================================
// Complexity discussion
// ============================================================================

void printComplexityAnalysis() {
    cout << "\n=== COMPLEXITY AND DESIGN ANALYSIS ===\n";

    cout
        << "Certificate hostname search: O(n) for n certificate names.\n"
        << "Certificate-chain lookup: O(c * i) in this educational model,\n"
        << "  where c is chain depth and i is the number of intermediates.\n"
        << "Replay lookup: O(log n) using std::set.\n"
        << "Rate-limit cleanup: amortized dependent on retained timestamps.\n"
        << "Authorization checks: O(1) for the modeled role rules.\n\n";

    cout
        << "A production gateway would typically use optimized certificate\n"
        << "stores, bounded caches, efficient concurrent structures, and a\n"
        << "mature TLS library rather than implementing cryptographic protocols\n"
        << "inside application code.\n";
}

// ============================================================================
// Demonstration helpers
// ============================================================================

void printResponse(
    const string& label,
    const HttpResponse& response
) {
    cout << "\n[" << label << "]\n";
    cout << "HTTP status: " << response.statusCode << '\n';
    cout << "Body: " << response.body << '\n';

    cout << "Security headers:\n";

    for (const auto& [key, value] : response.headers) {
        cout << "  " << key << ": " << value << '\n';
    }
}

// ============================================================================
// Main case study
// ============================================================================

int main() {
    cout << "============================================================\n";
    cout << "HTTPS & TLS SECURE API GATEWAY CASE STUDY\n";
    cout << "============================================================\n";

    /*
     * Scenario:
     *
     * A company operates api.example.test. Clients connect over HTTPS.
     * The gateway validates the server certificate during TLS establishment,
     * then applies application-level authentication, authorization, replay
     * protection, rate limiting, and auditing.
     */

    Certificate root{
        "Example Root CA",
        "Example Root CA",
        {},
        true,
        false,
        false,
        "root-key-fingerprint"
    };

    Certificate intermediate{
        "Example Intermediate CA",
        root.subject,
        {},
        true,
        false,
        false,
        "intermediate-key-fingerprint"
    };

    Certificate server{
        "CN=api.example.test",
        intermediate.subject,
        {
            "api.example.test",
            "*.services.example.test"
        },
        false,
        false,
        false,
        "server-key-fingerprint"
    };

    vector<Certificate> intermediates{
        intermediate
    };

    set<string> trustedRoots{
        root.subject
    };

    SecureApiGateway gateway;

    if (!gateway.establishTLS(
            server,
            intermediates,
            trustedRoots,
            "api.example.test")) {
        cerr << "Cannot start secure gateway session.\n";
        return 1;
    }

    User customer{
        "alice",
        "customer",
        true
    };

    User securityAnalyst{
        "bob",
        "security",
        true
    };

    User inactiveUser{
        "charlie",
        "customer",
        false
    };

    HttpRequest accountRequest{
        "GET",
        "/api/account",
        "api.example.test",
        {
            {"Host", "api.example.test"},
            {"X-Request-ID", "request-001"}
        },
        ""
    };

    HttpResponse accountResponse =
        gateway.handleRequest(
            accountRequest,
            customer,
            1000
        );

    printResponse(
        "Customer account request",
        accountResponse
    );

    /*
     * Reusing the same request ID demonstrates application-level replay
     * detection. TLS itself is not an application transaction database.
     */
    HttpResponse replayResponse =
        gateway.handleRequest(
            accountRequest,
            customer,
            1001
        );

    printResponse(
        "Replay attempt",
        replayResponse
    );

    HttpRequest auditRequest{
        "GET",
        "/api/audit",
        "api.example.test",
        {
            {"Host", "api.example.test"},
            {"X-Request-ID", "request-002"}
        },
        ""
    };

    HttpResponse deniedAuditResponse =
        gateway.handleRequest(
            auditRequest,
            customer,
            1002
        );

    printResponse(
        "Customer audit request",
        deniedAuditResponse
    );

    HttpRequest authorizedAuditRequest{
        "GET",
        "/api/audit",
        "api.example.test",
        {
            {"Host", "api.example.test"},
            {"X-Request-ID", "request-003"}
        },
        ""
    };

    HttpResponse authorizedAuditResponse =
        gateway.handleRequest(
            authorizedAuditRequest,
            securityAnalyst,
            1003
        );

    printResponse(
        "Security analyst audit request",
        authorizedAuditResponse
    );

    HttpRequest inactiveRequest{
        "GET",
        "/api/account",
        "api.example.test",
        {
            {"Host", "api.example.test"},
            {"X-Request-ID", "request-004"}
        },
        ""
    };

    HttpResponse inactiveResponse =
        gateway.handleRequest(
            inactiveRequest,
            inactiveUser,
            1004
        );

    printResponse(
        "Inactive user request",
        inactiveResponse
    );

    /*
     * The following requests demonstrate rate limiting. The configured limit
     * is five requests per minute per user.
     */
    cout << "\n=== RATE LIMIT TEST ===\n";

    for (int i = 0; i < 7; ++i) {
        HttpRequest rateRequest{
            "GET",
            "/api/account",
            "api.example.test",
            {
                {"Host", "api.example.test"},
                {
                    "X-Request-ID",
                    "rate-" + to_string(i)
                }
            },
            ""
        };

        HttpResponse response =
            gateway.handleRequest(
                rateRequest,
                securityAnalyst,
                2000
            );

        cout
            << "Request " << i + 1
            << " -> HTTP "
            << response.statusCode
            << '\n';
    }

    gateway.printAuditLog();

    printComplexityAnalysis();

    cout << "\n=== IMPORTANT SECURITY BOUNDARIES ===\n";

    vector<string> boundaries{
        "TLS authenticates the peer and protects the transport.",
        "Certificate validation establishes trust in a public key.",
        "Hostname validation connects the certificate identity to the requested host.",
        "Authenticated encryption detects modifications to protected TLS records.",
        "Application authentication identifies the user or client.",
        "Application authorization decides what that identity may access.",
        "Replay protection handles application transaction duplication.",
        "Rate limiting controls resource consumption.",
        "Audit logging supports investigation and operational accountability."
    };

    for (const string& boundary : boundaries) {
        cout << " - " << boundary << '\n';
    }

    cout << "\n=== PRODUCTION DESIGN TRADE-OFFS ===\n";

    cout
        << "1. TLS library vs custom TLS: use a mature library in production.\n"
        << "2. TLS 1.3 vs compatibility: TLS 1.3 is modern, while TLS 1.2 may\n"
        << "   remain necessary for legacy clients.\n"
        << "3. Certificate pinning vs operational flexibility: pinning can narrow\n"
        << "   trust but complicates certificate and key rotation.\n"
        << "4. Strict security vs availability: aggressive controls can reject\n"
        << "   legitimate traffic when configuration and rotation are incorrect.\n"
        << "5. Logging vs privacy: security logs should avoid unnecessary secrets\n"
        << "   and sensitive personal information.\n";

    cout << "\nCase study completed.\n";

    return 0;
}
