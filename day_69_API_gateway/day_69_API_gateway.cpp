#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * API Gateway: Routing, Authentication and Rate Limiting
 *
 * C++17 implementation of a gateway policy engine.
 *
 * Features:
 * - Route registration and path parameter extraction
 * - API client authentication
 * - Scope-based authorization
 * - Token-bucket rate limiting
 * - Upstream service dispatch
 * - Per-client request accounting
 * - Request validation
 * - Structured gateway responses
 */

using namespace std;

// -------------------------------------------------------
// Domain types
// -------------------------------------------------------

enum class HTTPMethod {
    GET,
    POST,
    PUT,
    PATCH,
    DELETE
};

enum class GatewayStatus {
    Success,
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    RateLimited,
    BadGateway
};

string toString(HTTPMethod method) {
    switch (method) {
        case HTTPMethod::GET: return "GET";
        case HTTPMethod::POST: return "POST";
        case HTTPMethod::PUT: return "PUT";
        case HTTPMethod::PATCH: return "PATCH";
        case HTTPMethod::DELETE: return "DELETE";
    }

    return "UNKNOWN";
}

struct Request {
    HTTPMethod method;
    string path;
    string bearerToken;
    string body;
    string requestId;
};

struct Response {
    int statusCode;
    string message;
    map<string, string> headers;
};

struct Client {
    string id;
    string token;
    set<string> scopes;
    bool enabled = true;
};

struct Route {
    string id;
    HTTPMethod method;
    string pathPattern;
    string upstream;
    string requiredScope;
    int requestsPerSecond;
    int burstCapacity;
};

// -------------------------------------------------------
// Gateway exceptions
// -------------------------------------------------------

class GatewayException : public runtime_error {
public:
    int statusCode;

    GatewayException(int status, const string& message)
        : runtime_error(message), statusCode(status) {}
};

// -------------------------------------------------------
// Authentication
// -------------------------------------------------------

class Authenticator {
private:
    unordered_map<string, Client> clients;

public:
    void registerClient(const Client& client) {

        if (client.id.empty() || client.token.empty()) {
            throw invalid_argument("Client identity is required");
        }

        if (clients.count(client.token)) {
            throw invalid_argument("Duplicate client token");
        }

        clients.emplace(client.token, client);
    }

    const Client& authenticate(const string& token) const {

        auto it = clients.find(token);

        if (token.empty() || it == clients.end() ||
            !it->second.enabled) {
            throw GatewayException(
                401,
                "Invalid or disabled credentials"
            );
        }

        return it->second;
    }

    static void authorize(
        const Client& client,
        const string& requiredScope
    ) {

        if (!client.scopes.count(requiredScope)) {
            throw GatewayException(
                403,
                "Insufficient authorization scope"
            );
        }
    }
};

// -------------------------------------------------------
// Path routing
// -------------------------------------------------------

struct RouteMatch {
    const Route* route;
    unordered_map<string, string> parameters;
};

class Router {
private:
    vector<Route> routes;

    static vector<string> split(const string& path) {

        vector<string> result;
        stringstream stream(path);
        string segment;

        while (getline(stream, segment, '/')) {
            if (!segment.empty()) {
                result.push_back(segment);
            }
        }

        return result;
    }

    static bool matchPath(
        const string& pattern,
        const string& actual,
        unordered_map<string, string>& parameters
    ) {

        auto expected = split(pattern);
        auto received = split(actual);

        if (expected.size() != received.size()) {
            return false;
        }

        for (size_t i = 0; i < expected.size(); ++i) {

            const string& segment = expected[i];

            if (
                segment.size() >= 3 &&
                segment.front() == '{' &&
                segment.back() == '}'
            ) {
                string key = segment.substr(
                    1,
                    segment.size() - 2
                );

                if (key.empty() || key.find('/') != string::npos) {
                    return false;
                }

                parameters[key] = received[i];

            } else if (segment != received[i]) {
                return false;
            }
        }

        return true;
    }

public:
    void registerRoute(const Route& route) {

        if (route.id.empty() ||
            route.pathPattern.empty() ||
            route.pathPattern.front() != '/') {
            throw invalid_argument("Invalid route definition");
        }

        if (route.requestsPerSecond <= 0 ||
            route.burstCapacity <= 0) {
            throw invalid_argument("Invalid rate-limit settings");
        }

        for (const auto& existing : routes) {
            if (existing.id == route.id ||
                (existing.method == route.method &&
                 existing.pathPattern == route.pathPattern)) {
                throw invalid_argument("Duplicate route");
            }
        }

        routes.push_back(route);

        // Static routes are evaluated before parameterized routes.
        stable_sort(
            routes.begin(),
            routes.end(),
            [](const Route& a, const Route& b) {

                auto countParameters = [](const string& path) {
                    return count(
                        path.begin(),
                        path.end(),
                        '{'
                    );
                };

                return countParameters(a.pathPattern) <
                       countParameters(b.pathPattern);
            }
        );
    }

    optional<RouteMatch> resolve(
        HTTPMethod method,
        const string& path
    ) const {

        for (const auto& route : routes) {

            if (route.method != method) {
                continue;
            }

            unordered_map<string, string> parameters;

            if (matchPath(
                route.pathPattern,
                path,
                parameters
            )) {
                return RouteMatch{
                    &route,
                    move(parameters)
                };
            }
        }

        return nullopt;
    }
};

// -------------------------------------------------------
// Token bucket
// -------------------------------------------------------

class TokenBucket {
private:
    double tokens;
    double refillRate;
    double capacity;

    chrono::steady_clock::time_point lastRefill;

public:
    TokenBucket(double rate, double burst)
        : tokens(burst),
          refillRate(rate),
          capacity(burst),
          lastRefill(chrono::steady_clock::now()) {

        if (rate <= 0 || burst <= 0) {
            throw invalid_argument("Invalid bucket configuration");
        }
    }

    bool consume() {

        auto now = chrono::steady_clock::now();

        double elapsed =
            chrono::duration<double>(
                now - lastRefill
            ).count();

        tokens = min(
            capacity,
            tokens + elapsed * refillRate
        );

        lastRefill = now;

        if (tokens < 1.0) {
            return false;
        }

        tokens -= 1.0;
        return true;
    }

    int remaining() const {
        return static_cast<int>(tokens);
    }
};

// -------------------------------------------------------
// Rate limiter
// -------------------------------------------------------

class RateLimiter {
private:
    unordered_map<
        string,
        unique_ptr<TokenBucket>
    > buckets;

public:
    bool allow(const Client& client, const Route& route) {

        string key = client.id + ":" + route.id;

        auto it = buckets.find(key);

        if (it == buckets.end()) {

            auto bucket = make_unique<TokenBucket>(
                route.requestsPerSecond,
                route.burstCapacity
            );

            it = buckets.emplace(
                key,
                move(bucket)
            ).first;
        }

        return it->second->consume();
    }
};

// -------------------------------------------------------
// Upstream services
// -------------------------------------------------------

class UpstreamService {
public:
    virtual ~UpstreamService() = default;

    virtual Response handle(
        const Request& request,
        const unordered_map<string, string>& parameters
    ) = 0;
};

class UserService : public UpstreamService {
public:
    Response handle(
        const Request& request,
        const unordered_map<string, string>& parameters
    ) override {

        auto it = parameters.find("userId");

        if (it == parameters.end()) {
            return {400, "Missing user ID", {}};
        }

        return {
            200,
            "User service: retrieved user " + it->second,
            {}
        };
    }
};

class OrderService : public UpstreamService {
public:
    Response handle(
        const Request& request,
        const unordered_map<string, string>&
    ) override {

        if (request.method != HTTPMethod::POST) {
            return {405, "Method not supported", {}};
        }

        if (request.body.empty()) {
            return {400, "Order body is required", {}};
        }

        return {
            201,
            "Order created: " + request.body,
            {}
        };
    }
};

// -------------------------------------------------------
// Service registry
// -------------------------------------------------------

class UpstreamRegistry {
private:
    unordered_map<
        string,
        unique_ptr<UpstreamService>
    > services;

public:
    void registerService(
        const string& name,
        unique_ptr<UpstreamService> service
    ) {

        if (name.empty() || !service) {
            throw invalid_argument("Invalid upstream service");
        }

        if (services.count(name)) {
            throw invalid_argument("Duplicate upstream service");
        }

        services.emplace(name, move(service));
    }

    Response forward(
        const string& name,
        const Request& request,
        const unordered_map<string, string>& parameters
    ) {

        auto it = services.find(name);

        if (it == services.end()) {
            throw GatewayException(
                502,
                "Upstream service unavailable"
            );
        }

        return it->second->handle(request, parameters);
    }
};

// -------------------------------------------------------
// Gateway audit
// -------------------------------------------------------

struct AuditRecord {
    string requestId;
    string clientId;
    string method;
    string path;
    int statusCode;
};

class AuditLogger {
private:
    vector<AuditRecord> records;

public:
    void add(const AuditRecord& record) {
        records.push_back(record);
    }

    void print() const {

        cout << "\nREQUEST AUDIT\n";

        for (const auto& record : records) {
            cout
                << record.requestId << " | "
                << record.clientId << " | "
                << record.method << " | "
                << record.path << " | "
                << record.statusCode << '\n';
        }
    }

    map<int, int> statusCounts() const {

        map<int, int> counts;

        for (const auto& record : records) {
            counts[record.statusCode]++;
        }

        return counts;
    }
};

// -------------------------------------------------------
// API Gateway
// -------------------------------------------------------

class APIGateway {
private:
    Authenticator authenticator;
    Router router;
    RateLimiter limiter;
    UpstreamRegistry upstreams;
    AuditLogger audit;

    int process(const Request& request) {

        if (request.path.empty() ||
            request.path.front() != '/' ||
            request.path.size() > 2048 ||
            request.path.find("..") != string::npos) {
            throw GatewayException(
                400,
                "Invalid request path"
            );
        }

        auto match = router.resolve(
            request.method,
            request.path
        );

        if (!match) {
            throw GatewayException(
                404,
                "Route not found"
            );
        }

        const Route& route = *match->route;

        const Client& client = authenticator.authenticate(
            request.bearerToken
        );

        Authenticator::authorize(
            client,
            route.requiredScope
        );

        if (!limiter.allow(client, route)) {
            throw GatewayException(
                429,
                "Rate limit exceeded"
            );
        }

        Response response = upstreams.forward(
            route.upstream,
            request,
            match->parameters
        );

        return response.statusCode;
    }

public:
    void configure() {

        authenticator.registerClient({
            "client-001",
            "demo-user-token",
            {"users:read", "orders:create"},
            true
        });

        authenticator.registerClient({
            "client-002",
            "demo-admin-token",
            {"users:read", "users:delete", "orders:create"},
            true
        });

        router.registerRoute({
            "get-user",
            HTTPMethod::GET,
            "/api/v1/users/{userId}",
            "users",
            "users:read",
            3,
            5
        });

        router.registerRoute({
            "create-order",
            HTTPMethod::POST,
            "/api/v1/orders",
            "orders",
            "orders:create",
            5,
            10
        });

        upstreams.registerService(
            "users",
            make_unique<UserService>()
        );

        upstreams.registerService(
            "orders",
            make_unique<OrderService>()
        );
    }

    Response handle(Request request) {

        if (request.requestId.empty()) {
            request.requestId = "req-" +
                to_string(
                    chrono::steady_clock::now()
                        .time_since_epoch()
                        .count()
                );
        }

        int status = 500;
        string clientId = "anonymous";

        try {

            if (!request.bearerToken.empty()) {
                clientId = request.bearerToken == "demo-user-token"
                    ? "client-001"
                    : request.bearerToken == "demo-admin-token"
                        ? "client-002"
                        : "unknown";
            }

            status = process(request);

            return {
                status,
                status == 201
                    ? "Request processed successfully"
                    : "Request completed successfully",
                {
                    {"X-Request-ID", request.requestId}
                }
            };

        } catch (const GatewayException& error) {

            status = error.statusCode;

            return {
                status,
                error.what(),
                {
                    {"X-Request-ID", request.requestId}
                }
            };

        } catch (const exception& error) {

            status = 502;

            return {
                status,
                "Gateway failure: " + string(error.what()),
                {
                    {"X-Request-ID", request.requestId}
                }
            };

        } finallyAudit:
            audit.add({
                request.requestId,
                clientId,
                toString(request.method),
                request.path,
                status
            });

        return {
            status,
            "Gateway processing completed",
            {}
        };
    }

    void report() const {
        audit.print();

        cout << "\nSTATUS COUNTS\n";

        for (const auto& [status, count] : audit.statusCounts()) {
            cout << status << ": " << count << '\n';
        }
    }
};

// -------------------------------------------------------
// Demonstration
// -------------------------------------------------------

int main() {

    try {

        APIGateway gateway;
        gateway.configure();

        vector<Request> requests = {
            {
                HTTPMethod::GET,
                "/api/v1/users/101",
                "demo-user-token",
                "",
                "req-001"
            },
            {
                HTTPMethod::POST,
                "/api/v1/orders",
                "demo-user-token",
                "amount=2500",
                "req-002"
            },
            {
                HTTPMethod::GET,
                "/api/v1/users/102",
                "",
                "",
                "req-003"
            },
            {
                HTTPMethod::GET,
                "/api/v1/unknown",
                "demo-user-token",
                "",
                "req-004"
            },
            {
                HTTPMethod::GET,
                "/api/v1/users/103",
                "invalid-token",
                "",
                "req-005"
            }
        };

        cout << "API GATEWAY DEMONSTRATION\n\n";

        for (auto& request : requests) {

            Response response = gateway.handle(request);

            cout
                << request.method == HTTPMethod::GET
                    ? "GET "
                    : toString(request.method) + " ";

            cout
                << request.path
                << " -> HTTP "
                << response.statusCode
                << " | "
                << response.message
                << '\n';
        }

        gateway.report();

        cout << "\nGateway demonstration completed.\n";

        return 0;

    } catch (const exception& error) {

        cerr << "Fatal error: " << error.what() << '\n';

        return 1;
    }
}
