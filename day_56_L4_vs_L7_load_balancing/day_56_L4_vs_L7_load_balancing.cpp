#include <algorithm>
#include <cstdint>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class BackendState {
    Healthy,
    Unhealthy
};

enum class ReviewProtocol {
    L4,
    L7
};

struct Backend {
    std::string name;
    std::string address;
    std::uint16_t port;
    BackendState state{BackendState::Healthy};
    std::size_t activeConnections{0};
    std::size_t requestsServed{0};
    int weight{1};

    bool available() const {
        return state == BackendState::Healthy && weight > 0;
    }
};

struct TcpFlow {
    std::string sourceIp;
    std::uint16_t sourcePort;
    std::string destinationIp;
    std::uint16_t destinationPort;

    std::string key() const {
        return sourceIp + ":" + std::to_string(sourcePort) +
               "->" + destinationIp + ":" +
               std::to_string(destinationPort);
    }
};

struct HttpRequest {
    std::string method;
    std::string host;
    std::string path;
    std::unordered_map<std::string, std::string> headers;
};

struct MergeDecision {
    bool eligible;
    std::string backend;
    std::string reason;
};

class L4LoadBalancer {
private:
    std::vector<Backend> backends;
    std::unordered_map<std::string, std::string> flowTable;

    std::vector<std::reference_wrapper<Backend>> healthyBackends() {
        std::vector<std::reference_wrapper<Backend>> result;

        for (Backend& backend : backends) {
            if (backend.available()) {
                result.emplace_back(backend);
            }
        }

        return result;
    }

    Backend& findBackend(const std::string& name) {
        for (Backend& backend : backends) {
            if (backend.name == name) {
                return backend;
            }
        }

        throw std::runtime_error("Backend not found: " + name);
    }

public:
    explicit L4LoadBalancer(std::vector<Backend> servers)
        : backends(std::move(servers)) {
        if (backends.empty()) {
            throw std::invalid_argument("L4 requires at least one backend");
        }
    }

    Backend& select(const TcpFlow& flow) {
        const std::string key = flow.key();

        auto existing = flowTable.find(key);

        if (existing != flowTable.end()) {
            Backend& backend = findBackend(existing->second);

            if (backend.available()) {
                return backend;
            }

            flowTable.erase(existing);
        }

        auto candidates = healthyBackends();

        if (candidates.empty()) {
            throw std::runtime_error("No healthy L4 backend exists");
        }

        // std::hash is sufficient for this deterministic simulation.
        // Production systems may use a carefully selected flow-hash algorithm
        // with collision and distribution characteristics appropriate to scale.
        const std::size_t hashValue = std::hash<std::string>{}(key);
        Backend& selected = candidates[hashValue % candidates.size()].get();

        flowTable[key] = selected.name;
        ++selected.activeConnections;

        return selected;
    }

    void close(const TcpFlow& flow) {
        const std::string key = flow.key();
        auto existing = flowTable.find(key);

        if (existing == flowTable.end()) {
            return;
        }

        Backend& backend = findBackend(existing->second);
        backend.activeConnections =
            backend.activeConnections > 0
                ? backend.activeConnections - 1
                : 0;

        flowTable.erase(existing);
    }

    const std::vector<Backend>& state() const {
        return backends;
    }
};

class L7LoadBalancer {
private:
    std::vector<Backend> backends;
    std::unordered_map<std::string, std::string> sessions;

    Backend& find(const std::string& name) {
        for (Backend& backend : backends) {
            if (backend.name == name) {
                return backend;
            }
        }

        throw std::runtime_error("Backend not found: " + name);
    }

    std::vector<std::reference_wrapper<Backend>>
    candidatesFor(const HttpRequest& request) {
        std::vector<std::reference_wrapper<Backend>> candidates;

        auto addIfHealthy = [&](const std::string& name) {
            Backend& backend = find(name);
            if (backend.available()) {
                candidates.emplace_back(backend);
            }
        };

        if (request.path.rfind("/api", 0) == 0) {
            addIfHealthy("api-1");
            addIfHealthy("api-2");
        } else if (request.path.rfind("/static", 0) == 0) {
            addIfHealthy("static-1");
        } else {
            for (Backend& backend : backends) {
                if (backend.available()) {
                    candidates.emplace_back(backend);
                }
            }
        }

        return candidates;
    }

    static void validate(const HttpRequest& request) {
        const std::vector<std::string> methods{
            "GET", "POST", "PUT", "PATCH", "DELETE"
        };

        if (std::find(
                methods.begin(),
                methods.end(),
                request.method) == methods.end()) {
            throw std::invalid_argument("Unsupported HTTP method");
        }

        if (request.host.empty() || request.host.size() > 253) {
            throw std::invalid_argument("Invalid HTTP host");
        }

        if (request.path.empty() || request.path.front() != '/') {
            throw std::invalid_argument("Invalid HTTP path");
        }

        if (request.path.size() > 4096) {
            throw std::invalid_argument("HTTP path exceeds limit");
        }
    }

    static std::optional<std::string>
    sessionId(const HttpRequest& request) {
        auto it = request.headers.find("Cookie");

        if (it == request.headers.end()) {
            return std::nullopt;
        }

        std::stringstream stream(it->second);
        std::string token;

        while (std::getline(stream, token, ';')) {
            const std::string prefix = "SESSION_ID=";

            while (!token.empty() && token.front() == ' ') {
                token.erase(token.begin());
            }

            if (token.rfind(prefix, 0) == 0) {
                const std::string value = token.substr(prefix.size());

                if (!value.empty() && value.size() <= 128) {
                    return value;
                }
            }
        }

        return std::nullopt;
    }

    static Backend&
    leastConnections(
        std::vector<std::reference_wrapper<Backend>>& candidates) {
        if (candidates.empty()) {
            throw std::runtime_error("No healthy L7 backend exists");
        }

        return std::min_element(
                   candidates.begin(),
                   candidates.end(),
                   [](const auto& a, const auto& b) {
                       return a.get().activeConnections <
                              b.get().activeConnections;
                   })
            ->get();
    }

public:
    explicit L7LoadBalancer(std::vector<Backend> servers)
        : backends(std::move(servers)) {
        if (backends.empty()) {
            throw std::invalid_argument("L7 requires at least one backend");
        }
    }

    Backend& route(const HttpRequest& request) {
        validate(request);

        auto candidates = candidatesFor(request);

        if (candidates.empty()) {
            throw std::runtime_error(
                "No healthy backend satisfies the application route");
        }

        const auto session = sessionId(request);

        if (session) {
            auto existing = sessions.find(*session);

            if (existing != sessions.end()) {
                Backend& sticky = find(existing->second);

                const bool stillEligible = sticky.available() &&
                    std::any_of(
                        candidates.begin(),
                        candidates.end(),
                        [&](const auto& item) {
                            return item.get().name == sticky.name;
                        });

                if (stillEligible) {
                    ++sticky.requestsServed;
                    return sticky;
                }
            }

            Backend& selected = leastConnections(candidates);
            sessions[*session] = selected.name;
            ++selected.requestsServed;
            return selected;
        }

        Backend& selected = leastConnections(candidates);
        ++selected.requestsServed;
        return selected;
    }

    const std::vector<Backend>& state() const {
        return backends;
    }
};

static void printState(
    const std::string& title,
    const std::vector<Backend>& backends) {

    std::cout << "\n" << title << "\n";

    for (const Backend& backend : backends) {
        std::cout
            << std::left << std::setw(10) << backend.name
            << " state="
            << (backend.state == BackendState::Healthy
                    ? "healthy"
                    : "unhealthy")
            << " connections=" << backend.activeConnections
            << " requests=" << backend.requestsServed
            << '\n';
    }
}

int main() {
    try {
        std::vector<Backend> l4Servers{
            {"api-1", "10.0.0.11", 443},
            {"api-2", "10.0.0.12", 443},
            {"api-3", "10.0.0.13", 443}
        };

        L4LoadBalancer l4(std::move(l4Servers));

        TcpFlow flowA{
            "192.168.1.10", 50001,
            "203.0.113.10", 443
        };

        TcpFlow flowB{
            "192.168.1.11", 50002,
            "203.0.113.10", 443
        };

        Backend& backendA = l4.select(flowA);
        Backend& backendB = l4.select(flowB);

        std::cout << "L4 flow A -> " << backendA.name << '\n';
        std::cout << "L4 flow B -> " << backendB.name << '\n';

        backendA.state = BackendState::Unhealthy;

        Backend& remapped = l4.select(flowA);
        std::cout << "L4 failed-flow remap -> "
                  << remapped.name << '\n';

        l4.close(flowB);

        printState("L4 state", l4.state());

        std::vector<Backend> l7Servers{
            {"api-1", "10.0.0.11", 8080},
            {"api-2", "10.0.0.12", 8080},
            {"static-1", "10.0.0.21", 8080}
        };

        L7LoadBalancer l7(std::move(l7Servers));

        HttpRequest orderRequest{
            "GET",
            "api.example.com",
            "/api/orders",
            {{"Cookie", "SESSION_ID=customer-42"}}
        };

        HttpRequest productRequest{
            "GET",
            "api.example.com",
            "/api/products",
            {{"Cookie", "SESSION_ID=customer-42"}}
        };

        HttpRequest staticRequest{
            "GET",
            "cdn.example.com",
            "/static/app.js",
            {}
        };

        std::cout
            << "\nL7 order -> "
            << l7.route(orderRequest).name << '\n';

        std::cout
            << "L7 product -> "
            << l7.route(productRequest).name << '\n';

        std::cout
            << "L7 static -> "
            << l7.route(staticRequest).name << '\n';

        // Application-aware routing can move a session when its selected
        // backend becomes unhealthy.
        HttpRequest adminRequest{
            "GET",
            "api.example.com",
            "/api/admin",
            {{"Cookie", "SESSION_ID=customer-42"}}
        };

        l7.route(adminRequest).state; // Request is valid before failure.

        std::cout << "L7 session backend before failure -> "
                  << l7.route(adminRequest).name << '\n';

        // The example deliberately demonstrates a backend failure by using
        // a separate request after determining the current routing result.
        Backend& failedBackend = l7.route(adminRequest);
        failedBackend.state = BackendState::Unhealthy;

        std::cout << "L7 session backend after failure -> "
                  << l7.route(adminRequest).name << '\n';

        try {
            HttpRequest invalid{
                "TRACE",
                "api.example.com",
                "/api/admin",
                {}
            };

            l7.route(invalid);
        } catch (const std::exception& ex) {
            std::cout << "Validation failure: "
                      << ex.what() << '\n';
        }

        printState("L7 state", l7.state());

        std::cout
            << "\nArchitecture distinction:\n"
            << "L4 makes decisions using transport-flow identity.\n"
            << "L7 makes decisions using application-level request data.\n"
            << "L4 generally provides lower protocol-processing overhead.\n"
            << "L7 provides richer routing at the cost of parsing and "
               "application-aware state.\n";

        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "Fatal error: " << ex.what() << '\n';
        return 1;
    }
}
