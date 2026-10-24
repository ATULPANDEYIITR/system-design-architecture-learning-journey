#include <algorithm>
#include <cassert>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

enum class Algorithm {
    RoundRobin,
    WeightedRoundRobin,
    LeastConnections
};

struct Backend {
    std::string name;
    int weight{1};
    bool healthy{true};
    int activeConnections{0};
    int totalRequests{0};
    int completedRequests{0};
    int failedRequests{0};

    Backend(std::string backendName, int backendWeight = 1)
        : name(std::move(backendName)), weight(backendWeight) {
        if (name.empty()) {
            throw std::invalid_argument("Backend name cannot be empty");
        }
        if (weight <= 0) {
            throw std::invalid_argument("Backend weight must be positive");
        }
    }

    void startRequest() {
        if (!healthy) {
            throw std::runtime_error("Cannot dispatch to unhealthy backend");
        }
        ++activeConnections;
        ++totalRequests;
    }

    void finishRequest(bool success) {
        if (activeConnections <= 0) {
            throw std::logic_error("No active request exists on backend");
        }

        --activeConnections;

        if (success) {
            ++completedRequests;
        } else {
            ++failedRequests;
        }
    }
};

class MergeEligibilityStyleLoadBalancer {
private:
    std::vector<Backend> backends;
    Algorithm algorithm;
    std::size_t roundRobinIndex{0};
    std::size_t weightedIndex{0};
    std::vector<std::size_t> weightedSchedule;

    std::vector<std::size_t> healthyIndexes() const {
        std::vector<std::size_t> result;

        for (std::size_t i = 0; i < backends.size(); ++i) {
            if (backends[i].healthy) {
                result.push_back(i);
            }
        }

        return result;
    }

    void rebuildWeightedSchedule() {
        weightedSchedule.clear();

        for (std::size_t i = 0; i < backends.size(); ++i) {
            for (int count = 0; count < backends[i].weight; ++count) {
                weightedSchedule.push_back(i);
            }
        }

        weightedIndex = 0;
    }

    std::size_t selectRoundRobin() {
        const auto healthy = healthyIndexes();

        if (healthy.empty()) {
            throw std::runtime_error("No healthy backends available");
        }

        const std::size_t selected =
            healthy[roundRobinIndex % healthy.size()];

        ++roundRobinIndex;
        return selected;
    }

    std::size_t selectWeightedRoundRobin() {
        const auto healthy = healthyIndexes();

        if (healthy.empty()) {
            throw std::runtime_error("No healthy backends available");
        }

        for (std::size_t attempts = 0; attempts < weightedSchedule.size();
             ++attempts) {
            const std::size_t index =
                weightedSchedule[weightedIndex % weightedSchedule.size()];

            ++weightedIndex;

            if (backends[index].healthy) {
                return index;
            }
        }

        throw std::runtime_error("Weighted schedule has no healthy backend");
    }

    std::size_t selectLeastConnections() const {
        const auto healthy = healthyIndexes();

        if (healthy.empty()) {
            throw std::runtime_error("No healthy backends available");
        }

        return *std::min_element(
            healthy.begin(),
            healthy.end(),
            [this](std::size_t left, std::size_t right) {
                const Backend& a = backends[left];
                const Backend& b = backends[right];

                if (a.activeConnections != b.activeConnections) {
                    return a.activeConnections < b.activeConnections;
                }

                if (a.weight != b.weight) {
                    return a.weight > b.weight;
                }

                return a.name < b.name;
            });
    }

public:
    MergeEligibilityStyleLoadBalancer(
        std::vector<Backend> initialBackends,
        Algorithm selectedAlgorithm)
        : backends(std::move(initialBackends)),
          algorithm(selectedAlgorithm) {
        if (backends.empty()) {
            throw std::invalid_argument("At least one backend is required");
        }

        std::map<std::string, int> names;
        for (const auto& backend : backends) {
            ++names[backend.name];
        }

        for (const auto& [name, count] : names) {
            if (count != 1) {
                throw std::invalid_argument(
                    "Backend names must be unique: " + name);
            }
        }

        rebuildWeightedSchedule();
    }

    void setHealth(const std::string& name, bool healthy) {
        Backend& backend = getBackend(name);
        backend.healthy = healthy;
        rebuildWeightedSchedule();

        // Existing connections may drain. New traffic does not use
        // unhealthy backends.
    }

    Backend& getBackend(const std::string& name) {
        for (auto& backend : backends) {
            if (backend.name == name) {
                return backend;
            }
        }

        throw std::out_of_range("Unknown backend: " + name);
    }

    const Backend& getBackend(const std::string& name) const {
        for (const auto& backend : backends) {
            if (backend.name == name) {
                return backend;
            }
        }

        throw std::out_of_range("Unknown backend: " + name);
    }

    std::size_t selectBackend() {
        switch (algorithm) {
            case Algorithm::RoundRobin:
                return selectRoundRobin();

            case Algorithm::WeightedRoundRobin:
                return selectWeightedRoundRobin();

            case Algorithm::LeastConnections:
                return selectLeastConnections();
        }

        throw std::logic_error("Unknown load-balancing algorithm");
    }

    std::string dispatch(int requestId) {
        if (requestId <= 0) {
            throw std::invalid_argument("Request ID must be positive");
        }

        const std::size_t index = selectBackend();
        backends[index].startRequest();

        return backends[index].name;
    }

    void complete(const std::string& backendName, bool success = true) {
        getBackend(backendName).finishRequest(success);
    }

    void printStatistics() const {
        for (const auto& backend : backends) {
            std::cout
                << backend.name
                << " weight=" << backend.weight
                << " healthy=" << std::boolalpha << backend.healthy
                << " active=" << backend.activeConnections
                << " total=" << backend.totalRequests
                << " completed=" << backend.completedRequests
                << " failed=" << backend.failedRequests
                << '\n';
        }
    }

    std::map<std::string, int> requestDistribution() const {
        std::map<std::string, int> result;

        for (const auto& backend : backends) {
            result[backend.name] = backend.totalRequests;
        }

        return result;
    }
};

std::map<std::string, int> simulate(
    Algorithm algorithm,
    const std::vector<int>& weights,
    int requestCount) {

    if (weights.size() != 3) {
        throw std::invalid_argument("This simulation requires three backends");
    }

    MergeEligibilityStyleLoadBalancer balancer(
        {
            Backend("server-a", weights[0]),
            Backend("server-b", weights[1]),
            Backend("server-c", weights[2])
        },
        algorithm
    );

    for (int requestId = 1; requestId <= requestCount; ++requestId) {
        const std::string backend = balancer.dispatch(requestId);
        balancer.complete(backend);
    }

    return balancer.requestDistribution();
}

void demonstrateLeastConnections() {
    MergeEligibilityStyleLoadBalancer balancer(
        {
            Backend("api-a", 1),
            Backend("api-b", 2),
            Backend("api-c", 3)
        },
        Algorithm::LeastConnections
    );

    std::vector<std::string> activeRequests;

    for (int requestId = 1; requestId <= 9; ++requestId) {
        activeRequests.push_back(balancer.dispatch(requestId));

        if (requestId % 3 == 0) {
            balancer.complete(activeRequests.front());
            activeRequests.erase(activeRequests.begin());
        }
    }

    std::cout << "\nLeast-connections state:\n";
    balancer.printStatistics();
}

void demonstrateFailure() {
    MergeEligibilityStyleLoadBalancer balancer(
        {
            Backend("primary", 3),
            Backend("secondary", 1)
        },
        Algorithm::WeightedRoundRobin
    );

    for (int requestId = 1; requestId <= 8; ++requestId) {
        const std::string backend = balancer.dispatch(requestId);
        balancer.complete(backend);
    }

    balancer.setHealth("primary", false);

    for (int requestId = 9; requestId <= 12; ++requestId) {
        const std::string backend = balancer.dispatch(requestId);
        balancer.complete(backend);
    }

    std::cout << "\nAfter primary failure:\n";
    balancer.printStatistics();
}

int main() {
    try {
        const auto roundRobin =
            simulate(Algorithm::RoundRobin, {1, 1, 1}, 60);

        const auto weighted =
            simulate(Algorithm::WeightedRoundRobin, {1, 2, 3}, 60);

        assert(roundRobin.at("server-a") == 20);
        assert(roundRobin.at("server-b") == 20);
        assert(roundRobin.at("server-c") == 20);

        assert(weighted.at("server-a") == 10);
        assert(weighted.at("server-b") == 20);
        assert(weighted.at("server-c") == 30);

        std::cout << "Round-robin distribution:\n";
        for (const auto& [name, count] : roundRobin) {
            std::cout << "  " << name << ": " << count << '\n';
        }

        std::cout << "\nWeighted round-robin distribution:\n";
        for (const auto& [name, count] : weighted) {
            std::cout << "  " << name << ": " << count << '\n';
        }

        demonstrateLeastConnections();
        demonstrateFailure();

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Load-balancer failure: "
                  << error.what() << '\n';
        return 1;
    }
}
