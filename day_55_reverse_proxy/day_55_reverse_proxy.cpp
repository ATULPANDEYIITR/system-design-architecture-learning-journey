#include <algorithm>
#include <chrono>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class Protocol {
    HTTP,
    HTTPS
};

enum class ServerState {
    Healthy,
    Unhealthy
};

enum class ReviewResult {
    Allowed,
    Rejected
};

struct Request {
    std::string clientIp;
    std::string host;
    std::string method;
    std::string path;
    Protocol protocol;
    std::map<std::string, std::string> headers;
    std::string body;
};

struct Response {
    int status;
    std::string body;
    std::string upstream;
};

struct UpstreamServer {
    std::string name;
    std::string address;
    int port;
    int weight;
    ServerState state{ServerState::Healthy};
    std::size_t requests{0};
    std::size_t activeConnections{0};

    bool healthy() const {
        return state == ServerState::Healthy;
    }
};

struct Route {
    std::string prefix;
    std::string upstreamGroup;
};

struct TLSCertificate {
    std::string hostname;
    std::string issuer;
};

class ProxyException : public std::runtime_error {
public:
    explicit ProxyException(const std::string& message)
        : std::runtime_error(message) {}
};

class RequestException : public ProxyException {
public:
    explicit RequestException(const std::string& message)
        : ProxyException(message) {}
};

class TLSError : public ProxyException {
public:
    explicit TLSError(const std::string& message)
        : ProxyException(message) {}
};

class UpstreamException : public ProxyException {
public:
    explicit UpstreamException(const std::string& message)
        : ProxyException(message) {}
};

class TLSManager {
private:
    std::unordered_map<std::string, TLSCertificate> certificates;

public:
    explicit TLSManager(
        const std::vector<TLSCertificate>& configured
    ) {
        for (const auto& certificate : configured) {
            certificates.emplace(
                certificate.hostname,
                certificate
            );
        }
    }

    void terminate(
        const std::string& host,
        const std::string& tlsVersion
    ) const {
        const auto it = certificates.find(host);

        if (it == certificates.end()) {
            throw TLSError(
                "no TLS certificate configured for " + host
            );
        }

        if (tlsVersion != "TLS1.2" &&
            tlsVersion != "TLS1.3") {
            throw TLSError(
                "TLS version is not permitted: " + tlsVersion
            );
        }
    }
};

class LoadBalancer {
private:
    std::unordered_map<std::string, std::size_t> positions;

public:
    UpstreamServer& choose(
        const std::string& group,
        std::vector<UpstreamServer>& servers,
        const std::set<std::string>& excluded
    ) {
        std::vector<std::size_t> weightedIndices;

        for (std::size_t i = 0; i < servers.size(); ++i) {
            if (!servers[i].healthy()) {
                continue;
            }

            if (excluded.contains(servers[i].name)) {
                continue;
            }

            for (int weight = 0;
                 weight < servers[i].weight;
                 ++weight) {
                weightedIndices.push_back(i);
            }
        }

        if (weightedIndices.empty()) {
            throw UpstreamException(
                "no healthy upstream is available in " + group
            );
        }

        std::size_t& position = positions[group];
        const std::size_t selected =
            weightedIndices[position % weightedIndices.size()];

        ++position;
        return servers[selected];
    }
};

class ReverseProxy {
private:
    TLSManager tlsManager;
    std::unordered_map<
        std::string,
        std::vector<UpstreamServer>
    > upstreamGroups;

    std::vector<Route> routes;
    LoadBalancer loadBalancer;

    bool secureForwardedHeaders{true};

    const Route& findRoute(
        const std::string& path
    ) const {
        const Route* selected = nullptr;

        for (const auto& route : routes) {
            if (path.rfind(route.prefix, 0) == 0) {
                if (selected == nullptr ||
                    route.prefix.size() >
                    selected->prefix.size()) {
                    selected = &route;
                }
            }
        }

        if (selected == nullptr) {
            throw RequestException(
                "no matching route for " + path
            );
        }

        return *selected;
    }

    void validate(const Request& request) const {
        if (request.clientIp.empty()) {
            throw RequestException("client IP is required");
        }

        static const std::set<std::string> methods{
            "GET", "POST", "PUT", "PATCH", "DELETE"
        };

        if (!methods.contains(request.method)) {
            throw RequestException(
                "unsupported HTTP method"
            );
        }

        if (request.path.empty() ||
            request.path.front() != '/') {
            throw RequestException("invalid request path");
        }

        if (request.path.size() > 4096) {
            throw RequestException("URI exceeds 4096 characters");
        }

        if (request.path.find('\r') != std::string::npos ||
            request.path.find('\n') != std::string::npos) {
            throw RequestException(
                "CRLF characters are not allowed"
            );
        }

        if (request.body.size() > 1'000'000) {
            throw RequestException(
                "request body exceeds configured limit"
            );
        }

        if (secureForwardedHeaders &&
            request.headers.contains("X-Forwarded-For")) {
            throw RequestException(
                "client cannot inject X-Forwarded-For"
            );
        }
    }

    Response forward(
        UpstreamServer& server,
        const Request& request
    ) {
        if (!server.healthy()) {
            throw UpstreamException(
                "selected upstream is unhealthy"
            );
        }

        ++server.activeConnections;
        ++server.requests;

        try {
            // Transport failure is intentionally modeled for retry testing.
            if (request.path == "/api/failure" &&
                server.name == "api-1") {
                throw UpstreamException(
                    "connection failure at " + server.name
                );
            }

            const std::string forwarded =
                request.clientIp;

            --server.activeConnections;

            return {
                200,
                "response from " + server.name +
                    " path=" + request.path +
                    " forwarded-for=" + forwarded,
                server.name
            };
        } catch (...) {
            --server.activeConnections;
            throw;
        }
    }

public:
    ReverseProxy(
        TLSManager tls,
        std::unordered_map<
            std::string,
            std::vector<UpstreamServer>
        > groups,
        std::vector<Route> configuredRoutes
    )
        : tlsManager(std::move(tls)),
          upstreamGroups(std::move(groups)),
          routes(std::move(configuredRoutes)) {}

    Response handle(const Request& request) {
        validate(request);

        if (request.protocol == Protocol::HTTPS) {
            std::string tlsVersion = "TLS1.3";

            const auto it =
                request.headers.find("X-TLS-Version");

            if (it != request.headers.end()) {
                tlsVersion = it->second;
            }

            // TLS ends at the reverse proxy. The upstream connection
            // can use a separate transport policy.
            tlsManager.terminate(request.host, tlsVersion);
        }

        const Route& route = findRoute(request.path);

        auto groupIt =
            upstreamGroups.find(route.upstreamGroup);

        if (groupIt == upstreamGroups.end()) {
            throw UpstreamException(
                "upstream group does not exist"
            );
        }

        auto& servers = groupIt->second;
        std::set<std::string> excluded;

        // Two attempts provide limited fault tolerance without
        // retrying indefinitely or multiplying application requests.
        for (int attempt = 0; attempt < 2; ++attempt) {
            try {
                UpstreamServer& server =
                    loadBalancer.choose(
                        route.upstreamGroup,
                        servers,
                        excluded
                    );

                excluded.insert(server.name);

                return forward(server, request);
            } catch (const UpstreamException&) {
                if (attempt == 1) {
                    throw;
                }
            }
        }

        throw UpstreamException("proxy retry limit reached");
    }

    void setHealth(
        const std::string& group,
        const std::string& serverName,
        bool healthy
    ) {
        auto groupIt = upstreamGroups.find(group);

        if (groupIt == upstreamGroups.end()) {
            throw std::invalid_argument(
                "unknown upstream group"
            );
        }

        for (auto& server : groupIt->second) {
            if (server.name == serverName) {
                server.state = healthy
                    ? ServerState::Healthy
                    : ServerState::Unhealthy;
                return;
            }
        }

        throw std::invalid_argument(
            "unknown upstream server"
        );
    }

    void printStatistics() const {
        for (const auto& [group, servers] :
             upstreamGroups) {
            std::cout << "\n[" << group << "]\n";

            for (const auto& server : servers) {
                std::cout
                    << server.name
                    << " state="
                    << (server.healthy()
                        ? "healthy"
                        : "unhealthy")
                    << " requests="
                    << server.requests
                    << " active="
                    << server.activeConnections
                    << '\n';
            }
        }
    }
};

void printResponse(
    const std::string& label,
    const Response& response
) {
    std::cout << "\n[" << label << "]\n"
              << "status=" << response.status << '\n'
              << "upstream=" << response.upstream << '\n'
              << "body=" << response.body << '\n';
}

int main() {
    try {
        TLSManager tls({
            {"api.example.com", "Example Internal CA"}
        });

        std::unordered_map<
            std::string,
            std::vector<UpstreamServer>
        > groups{
            {
                "api",
                {
                    {"api-1", "10.0.1.10", 8080, 2},
                    {"api-2", "10.0.1.11", 8080, 1}
                }
            },
            {
                "web",
                {
                    {"web-1", "10.0.2.10", 8080, 1},
                    {"web-2", "10.0.2.11", 8080, 1}
                }
            }
        };

        std::vector<Route> routes{
            {"/api/", "api"},
            {"/", "web"}
        };

        ReverseProxy proxy(
            std::move(tls),
            std::move(groups),
            std::move(routes)
        );

        std::vector<Request> requests{
            {
                "203.0.113.10",
                "api.example.com",
                "GET",
                "/api/users",
                Protocol::HTTPS,
                {{"X-TLS-Version", "TLS1.3"}},
                ""
            },
            {
                "203.0.113.11",
                "api.example.com",
                "GET",
                "/",
                Protocol::HTTPS,
                {{"X-TLS-Version", "TLS1.2"}},
                ""
            },
            {
                "203.0.113.12",
                "api.example.com",
                "GET",
                "/api/failure",
                Protocol::HTTPS,
                {},
                ""
            },
            {
                "203.0.113.13",
                "api.example.com",
                "GET",
                "/api/users",
                Protocol::HTTPS,
                {{"X-Forwarded-For", "198.51.100.5"}},
                ""
            }
        };

        for (std::size_t i = 0;
             i < requests.size();
             ++i) {
            try {
                printResponse(
                    "request-" + std::to_string(i + 1),
                    proxy.handle(requests[i])
                );
            } catch (const TLSError& error) {
                std::cout << "\nTLS failure: "
                          << error.what() << '\n';
            } catch (const RequestException& error) {
                std::cout << "\nRequest rejected: "
                          << error.what() << '\n';
            } catch (const UpstreamException& error) {
                std::cout << "\nUpstream failure: "
                          << error.what() << '\n';
            }
        }

        proxy.setHealth("api", "api-1", false);

        Request fallback{
            "203.0.113.20",
            "api.example.com",
            "GET",
            "/api/orders",
            Protocol::HTTPS,
            {},
            ""
        };

        printResponse(
            "health-fallback",
            proxy.handle(fallback)
        );

        proxy.printStatistics();
    } catch (const std::exception& error) {
        std::cerr
            << "fatal proxy configuration error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
