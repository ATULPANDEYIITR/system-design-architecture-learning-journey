#include <algorithm>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

enum class BackendState {
    Healthy,
    Unhealthy
};

enum class RoutingStrategy {
    RoundRobin,
    WeightedRoundRobin,
    LeastConnections
};

struct HealthResult {
    std::string backendId;
    bool success;
    std::string detail;
};

class Backend {
public:
    Backend(
        std::string id,
        std::string host,
        int port,
        int weight = 1,
        int maxConnections = 100
    )
        : id_(std::move(id)),
          host_(std::move(host)),
          port_(port),
          weight_(weight),
          maxConnections_(maxConnections) {
        if (id_.empty()) {
            throw std::invalid_argument("backend ID cannot be empty");
        }
        if (port_ < 1 || port_ > 65535) {
            throw std::invalid_argument("invalid backend port");
        }
        if (weight_ <= 0 || maxConnections_ <= 0) {
            throw std::invalid_argument(
                "weight and max connections must be positive"
            );
        }
    }

    const std::string& id() const { return id_; }

    int weight() const { return weight_; }

    int activeConnections() const { return activeConnections_; }

    int totalRequests() const { return totalRequests_; }

    int healthFailures() const { return healthFailures_; }

    BackendState state() const { return state_; }

    bool simulatedHealth() const { return simulatedHealth_; }

    void setSimulatedHealth(bool healthy) {
        simulatedHealth_ = healthy;
    }

    bool canReceive() const {
        return state_ == BackendState::Healthy &&
               activeConnections_ < maxConnections_;
    }

    void openConnection() {
        if (!canReceive()) {
            throw std::runtime_error(
                "backend cannot accept another connection"
            );
        }

        ++activeConnections_;
        ++totalRequests_;
    }

    void closeConnection() {
        if (activeConnections_ <= 0) {
            throw std::runtime_error(
                "backend has no active connection"
            );
        }

        --activeConnections_;
    }

    void applyHealthResult(bool success, int failureThreshold) {
        if (success) {
            consecutiveFailures_ = 0;
            ++consecutiveSuccesses_;
        } else {
            consecutiveSuccesses_ = 0;
            ++consecutiveFailures_;
            ++healthFailures_;
        }

        if (
            state_ == BackendState::Healthy &&
            consecutiveFailures_ >= failureThreshold
        ) {
            state_ = BackendState::Unhealthy;
        }
    }

    void recoverIfReady(int recoveryThreshold) {
        if (
            state_ == BackendState::Unhealthy &&
            consecutiveSuccesses_ >= recoveryThreshold
        ) {
            state_ = BackendState::Healthy;
            consecutiveFailures_ = 0;
        }
    }

    std::string stateName() const {
        return state_ == BackendState::Healthy
            ? "healthy"
            : "unhealthy";
    }

private:
    std::string id_;
    std::string host_;
    int port_;
    int weight_;
    int maxConnections_;

    BackendState state_{BackendState::Healthy};
    bool simulatedHealth_{true};

    int activeConnections_{0};
    int totalRequests_{0};
    int healthFailures_{0};
    int consecutiveFailures_{0};
    int consecutiveSuccesses_{0};
};

class HealthChecker {
public:
    HealthChecker(int failureThreshold, int recoveryThreshold)
        : failureThreshold_(failureThreshold),
          recoveryThreshold_(recoveryThreshold) {
        if (failureThreshold_ <= 0 || recoveryThreshold_ <= 0) {
            throw std::invalid_argument(
                "health thresholds must be positive"
            );
        }
    }

    HealthResult check(Backend& backend) const {
        if (backend.simulatedHealth()) {
            backend.applyHealthResult(true, failureThreshold_);
            backend.recoverIfReady(recoveryThreshold_);

            return {
                backend.id(),
                true,
                "health probe succeeded"
            };
        }

        backend.applyHealthResult(false, failureThreshold_);

        return {
            backend.id(),
            false,
            "health probe failed"
        };
    }

private:
    int failureThreshold_;
    int recoveryThreshold_;
};

class LoadBalancer {
public:
    LoadBalancer(
        std::vector<Backend> backends,
        RoutingStrategy strategy,
        HealthChecker healthChecker
    )
        : backends_(std::move(backends)),
          strategy_(strategy),
          healthChecker_(std::move(healthChecker)) {
        if (backends_.empty()) {
            throw std::invalid_argument(
                "at least one backend is required"
            );
        }

        validateUniqueIds();
    }

    void runHealthChecks() {
        for (Backend& backend : backends_) {
            const HealthResult result = healthChecker_.check(backend);

            std::cout
                << "health " << std::setw(8) << std::left
                << result.backendId
                << " -> "
                << (result.success ? "PASS" : "FAIL")
                << '\n';
        }
    }

    Backend& routeRequest(const std::string& requestId) {
        if (requestId.empty()) {
            throw std::invalid_argument(
                "request ID cannot be empty"
            );
        }

        Backend* selected = selectBackend();

        if (selected == nullptr) {
            throw std::runtime_error(
                "no healthy backend with available capacity"
            );
        }

        selected->openConnection();

        std::cout
            << "route " << std::setw(14) << std::left
            << requestId
            << " -> " << selected->id()
            << '\n';

        return *selected;
    }

    void completeRequest(Backend& backend) {
        backend.closeConnection();
    }

    void printState(const std::string& title) const {
        std::cout << "\n" << title << "\n";

        for (const Backend& backend : backends_) {
            std::cout
                << std::setw(10) << std::left << backend.id()
                << " state=" << std::setw(9) << backend.stateName()
                << " weight=" << backend.weight()
                << " connections=" << backend.activeConnections()
                << " requests=" << backend.totalRequests()
                << " health_failures=" << backend.healthFailures()
                << '\n';
        }
    }

    Backend& backendAt(std::size_t index) {
        if (index >= backends_.size()) {
            throw std::out_of_range("backend index out of range");
        }

        return backends_[index];
    }

private:
    std::vector<Backend> backends_;
    RoutingStrategy strategy_;
    HealthChecker healthChecker_;
    std::size_t roundRobinIndex_{0};
    std::size_t requestCount_{0};

    void validateUniqueIds() const {
        std::map<std::string, int> counts;

        for (const Backend& backend : backends_) {
            ++counts[backend.id()];
        }

        for (const auto& [id, count] : counts) {
            if (count > 1) {
                throw std::invalid_argument(
                    "duplicate backend ID: " + id
                );
            }
        }
    }

    std::vector<Backend*> availableBackends() {
        std::vector<Backend*> result;

        for (Backend& backend : backends_) {
            if (backend.canReceive()) {
                result.push_back(&backend);
            }
        }

        return result;
    }

    Backend* selectBackend() {
        auto candidates = availableBackends();

        if (candidates.empty()) {
            return nullptr;
        }

        if (strategy_ == RoutingStrategy::LeastConnections) {
            return *std::min_element(
                candidates.begin(),
                candidates.end(),
                [](const Backend* left, const Backend* right) {
                    if (
                        left->activeConnections() !=
                        right->activeConnections()
                    ) {
                        return left->activeConnections() <
                               right->activeConnections();
                    }

                    if (left->weight() != right->weight()) {
                        return left->weight() > right->weight();
                    }

                    return left->id() < right->id();
                }
            );
        }

        if (strategy_ == RoutingStrategy::WeightedRoundRobin) {
            std::vector<Backend*> weighted;

            for (Backend* backend : candidates) {
                for (int i = 0; i < backend->weight(); ++i) {
                    weighted.push_back(backend);
                }
            }

            if (weighted.empty()) {
                return nullptr;
            }

            return weighted[requestCount_++ % weighted.size()];
        }

        const std::size_t candidateCount = candidates.size();

        for (std::size_t offset = 0; offset < backends_.size(); ++offset) {
            const std::size_t index =
                (roundRobinIndex_ + offset) % backends_.size();

            Backend& backend = backends_[index];

            if (backend.canReceive()) {
                roundRobinIndex_ = (index + 1) % backends_.size();
                ++requestCount_;
                return &backend;
            }
        }

        return nullptr;
    }
};

int main() {
    try {
        std::vector<Backend> backends{
            Backend("node-a", "10.0.0.11", 8080, 1, 4),
            Backend("node-b", "10.0.0.12", 8080, 2, 4),
            Backend("node-c", "10.0.0.13", 8080, 1, 4)
        };

        HealthChecker healthChecker(2, 2);

        LoadBalancer loadBalancer(
            std::move(backends),
            RoutingStrategy::LeastConnections,
            healthChecker
        );

        std::cout << "Initial health state\n";
        loadBalancer.runHealthChecks();

        std::vector<Backend*> activeConnections;

        for (int i = 1; i <= 6; ++i) {
            Backend& backend =
                loadBalancer.routeRequest(
                    "request-" + std::to_string(i)
                );

            if (i % 2 == 0) {
                loadBalancer.completeRequest(backend);
            } else {
                activeConnections.push_back(&backend);
            }
        }

        loadBalancer.printState("Least-connections distribution");

        std::cout << "\nSimulating node-b failure\n";

        Backend& failingBackend = loadBalancer.backendAt(1);
        failingBackend.setSimulatedHealth(false);

        loadBalancer.runHealthChecks();
        loadBalancer.runHealthChecks();

        loadBalancer.printState("After health isolation");

        for (int i = 7; i <= 10; ++i) {
            Backend& backend =
                loadBalancer.routeRequest(
                    "failover-" + std::to_string(i)
                );

            loadBalancer.completeRequest(backend);
        }

        std::cout << "\nSimulating node-b recovery\n";

        failingBackend.setSimulatedHealth(true);

        loadBalancer.runHealthChecks();
        loadBalancer.runHealthChecks();

        loadBalancer.printState("Recovered backend pool");

        for (Backend* backend : activeConnections) {
            if (backend->activeConnections() > 0) {
                loadBalancer.completeRequest(*backend);
            }
        }

        loadBalancer.printState("Connections released");

        std::cout << "\nCapacity failure case\n";

        std::vector<Backend> limitedPool{
            Backend("limited", "10.0.1.11", 8080, 1, 1)
        };

        LoadBalancer limitedBalancer(
            std::move(limitedPool),
            RoutingStrategy::RoundRobin,
            HealthChecker(2, 2)
        );

        Backend& active =
            limitedBalancer.routeRequest("long-running-request");

        try {
            limitedBalancer.routeRequest("blocked-request");
        } catch (const std::exception& error) {
            std::cout
                << "Expected routing failure: "
                << error.what()
                << '\n';
        }

        limitedBalancer.completeRequest(active);
    }
    catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
