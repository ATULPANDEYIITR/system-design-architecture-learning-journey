#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
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

/*
 * Service Discovery and Repository-Independent Governance Engine
 *
 * C++17 implementation of a distributed service registry.
 *
 * Models:
 * - Registration and deregistration
 * - Instance leases
 * - Health checks and health transitions
 * - Version and metadata filtering
 * - Protected endpoint selection
 * - Weighted load balancing
 * - Circuit breakers
 * - Graceful shutdown
 * - Discovery and merge-like eligibility evaluation
 *
 * This program simulates registry operations. It does not perform
 * real network communication or distributed consensus.
 */

using Clock = std::chrono::steady_clock;
using Seconds = std::chrono::seconds;

enum class Health {
    Unknown,
    Healthy,
    Unhealthy,
    Draining
};

enum class CircuitState {
    Closed,
    Open,
    HalfOpen
};

enum class RegistrationState {
    Registered,
    Deregistered
};

std::string toString(Health health) {
    switch (health) {
        case Health::Unknown: return "UNKNOWN";
        case Health::Healthy: return "HEALTHY";
        case Health::Unhealthy: return "UNHEALTHY";
        case Health::Draining: return "DRAINING";
    }

    return "INVALID";
}

struct ServiceInstance {
    std::string id;
    std::string service;
    std::string host;
    int port;
    std::string version;
    std::map<std::string, std::string> metadata;

    Health health = Health::Unknown;

    Clock::time_point registeredAt = Clock::now();
    Clock::time_point lastHeartbeat = Clock::now();

    Seconds lease{30};

    int successes = 0;
    int failures = 0;
    int weight = 1;

    std::string endpoint() const {
        return host + ":" + std::to_string(port);
    }

    bool expired(Clock::time_point now) const {
        return now - lastHeartbeat > lease;
    }
};

class ValidationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ServiceUnavailable : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class HealthPolicy {
private:
    int failureThreshold;
    int recoveryThreshold;

public:
    HealthPolicy(int failures = 2, int recoveries = 2)
        : failureThreshold(failures),
          recoveryThreshold(recoveries) {

        if (failures < 1 || recoveries < 1) {
            throw ValidationError("Health thresholds must be positive");
        }
    }

    Health evaluate(ServiceInstance& instance, bool success) const {
        if (instance.health == Health::Draining) {
            return instance.health;
        }

        if (success) {
            instance.failures = 0;
            instance.successes++;

            if (instance.successes >= recoveryThreshold) {
                instance.health = Health::Healthy;
            }
        } else {
            instance.successes = 0;
            instance.failures++;

            if (instance.failures >= failureThreshold) {
                instance.health = Health::Unhealthy;
            }
        }

        return instance.health;
    }
};

class CircuitBreaker {
private:
    int threshold;
    int failures = 0;
    Clock::time_point openedAt{};
    Seconds resetDuration;

public:
    CircuitBreaker(int failureLimit = 3, Seconds reset = Seconds(5))
        : threshold(failureLimit), resetDuration(reset) {

        if (threshold < 1 || resetDuration.count() < 0) {
            throw ValidationError("Invalid circuit breaker configuration");
        }
    }

    CircuitState state() const {
        if (failures < threshold) {
            return CircuitState::Closed;
        }

        if (Clock::now() - openedAt >= resetDuration) {
            return CircuitState::HalfOpen;
        }

        return CircuitState::Open;
    }

    bool allowRequest() const {
        return state() != CircuitState::Open;
    }

    void recordSuccess() {
        failures = 0;
    }

    void recordFailure() {
        failures++;

        if (failures >= threshold) {
            openedAt = Clock::now();
        }
    }
};

class ServiceRegistry {
private:
    std::unordered_map<std::string, ServiceInstance> instances;

    std::unordered_map<std::string, std::set<std::string>>
        serviceIndex;

    std::unordered_map<std::string, CircuitBreaker> breakers;

    std::unordered_map<std::string, std::size_t> roundRobin;

    HealthPolicy healthPolicy;

    static void validate(const ServiceInstance& instance) {
        if (instance.id.empty()) {
            throw ValidationError("Instance ID is required");
        }

        if (instance.service.empty()) {
            throw ValidationError("Service name is required");
        }

        if (instance.host.empty()) {
            throw ValidationError("Host is required");
        }

        if (instance.port < 1 || instance.port > 65535) {
            throw ValidationError("Invalid port");
        }

        if (instance.version.empty()) {
            throw ValidationError("Version is required");
        }

        if (instance.lease.count() <= 0) {
            throw ValidationError("Lease must be positive");
        }

        if (instance.weight < 1 || instance.weight > 1000) {
            throw ValidationError("Weight must be between 1 and 1000");
        }
    }

public:
    explicit ServiceRegistry(HealthPolicy policy = HealthPolicy())
        : healthPolicy(policy) {}

    void registerService(ServiceInstance instance) {
        validate(instance);

        if (instances.count(instance.id)) {
            throw ValidationError("Duplicate instance ID");
        }

        instance.lastHeartbeat = Clock::now();

        const std::string id = instance.id;
        const std::string service = instance.service;

        instances.emplace(id, std::move(instance));

        serviceIndex[service].insert(id);
        breakers.emplace(id, CircuitBreaker());

        std::cout << "REGISTERED " << id
                  << " -> " << instances.at(id).endpoint() << '\n';
    }

    bool deregisterService(const std::string& id) {
        auto it = instances.find(id);

        if (it == instances.end()) {
            return false;
        }

        const std::string service = it->second.service;

        instances.erase(it);
        breakers.erase(id);

        auto index = serviceIndex.find(service);

        if (index != serviceIndex.end()) {
            index->second.erase(id);

            if (index->second.empty()) {
                serviceIndex.erase(index);
            }
        }

        std::cout << "DEREGISTERED " << id << '\n';

        return true;
    }

    void heartbeat(const std::string& id) {
        auto it = instances.find(id);

        if (it == instances.end()) {
            throw ServiceUnavailable("Unknown instance");
        }

        it->second.lastHeartbeat = Clock::now();
    }

    Health updateHealth(const std::string& id, bool healthy) {
        auto it = instances.find(id);

        if (it == instances.end()) {
            throw ServiceUnavailable("Unknown instance");
        }

        Health result = healthPolicy.evaluate(it->second, healthy);

        std::cout << "HEALTH " << id
                  << " -> " << toString(result) << '\n';

        return result;
    }

    void drain(const std::string& id) {
        auto it = instances.find(id);

        if (it == instances.end()) {
            throw ServiceUnavailable("Unknown instance");
        }

        it->second.health = Health::Draining;

        std::cout << "DRAINING " << id << '\n';
    }

    std::vector<std::string> discover(
        const std::string& service,
        const std::optional<std::string>& version = std::nullopt,
        const std::map<std::string, std::string>& metadata = {}
    ) const {

        std::vector<std::string> result;

        auto index = serviceIndex.find(service);

        if (index == serviceIndex.end()) {
            return result;
        }

        const auto now = Clock::now();

        for (const auto& id : index->second) {
            const auto& instance = instances.at(id);

            if (instance.health != Health::Healthy) {
                continue;
            }

            if (instance.expired(now)) {
                continue;
            }

            if (version && instance.version != *version) {
                continue;
            }

            bool metadataMatches = true;

            for (const auto& [key, value] : metadata) {
                auto field = instance.metadata.find(key);

                if (field == instance.metadata.end() ||
                    field->second != value) {

                    metadataMatches = false;
                    break;
                }
            }

            if (metadataMatches) {
                result.push_back(id);
            }
        }

        return result;
    }

    const ServiceInstance& selectRoundRobin(
        const std::string& service
    ) {

        auto available = discover(service);

        if (available.empty()) {
            throw ServiceUnavailable(
                "No healthy service instance: " + service
            );
        }

        auto& index = roundRobin[service];

        const std::string& selected =
            available[index % available.size()];

        index = (index + 1) % available.size();

        return instances.at(selected);
    }

    const ServiceInstance& selectWeighted(
        const std::string& service,
        std::mt19937& generator
    ) {

        auto available = discover(service);

        available.erase(
            std::remove_if(
                available.begin(),
                available.end(),
                [&](const std::string& id) {
                    return !breakers.at(id).allowRequest();
                }
            ),
            available.end()
        );

        if (available.empty()) {
            throw ServiceUnavailable(
                "No endpoint passed circuit-breaker policy"
            );
        }

        int totalWeight = 0;

        for (const auto& id : available) {
            totalWeight += instances.at(id).weight;
        }

        std::uniform_int_distribution<int> distribution(
            1,
            totalWeight
        );

        int choice = distribution(generator);

        for (const auto& id : available) {
            choice -= instances.at(id).weight;

            if (choice <= 0) {
                return instances.at(id);
            }
        }

        throw ServiceUnavailable("Weighted selection failed");
    }

    void recordRequest(
        const std::string& id,
        bool successful
    ) {

        auto it = breakers.find(id);

        if (it == breakers.end()) {
            throw ServiceUnavailable("Unknown circuit breaker");
        }

        if (successful) {
            it->second.recordSuccess();
        } else {
            it->second.recordFailure();
        }
    }

    std::vector<std::string> removeExpired() {
        const auto now = Clock::now();

        std::vector<std::string> expired;

        for (const auto& [id, instance] : instances) {
            if (instance.expired(now)) {
                expired.push_back(id);
            }
        }

        for (const auto& id : expired) {
            deregisterService(id);
        }

        return expired;
    }

    void printReport() const {
        std::cout << "\nSERVICE REGISTRY REPORT\n";

        for (const auto& [id, instance] : instances) {
            std::cout
                << std::left
                << std::setw(12) << instance.service
                << std::setw(40) << instance.endpoint()
                << std::setw(12) << instance.version
                << std::setw(12) << toString(instance.health)
                << '\n';
        }
    }

    std::size_t size() const {
        return instances.size();
    }
};

ServiceInstance makeInstance(
    std::string id,
    std::string service,
    std::string host,
    int port,
    std::string version,
    int weight
) {

    ServiceInstance instance;

    instance.id = std::move(id);
    instance.service = std::move(service);
    instance.host = std::move(host);
    instance.port = port;
    instance.version = std::move(version);
    instance.weight = weight;
    instance.lease = Seconds(60);

    instance.metadata = {
        {"region", "ap-south-1"},
        {"environment", "production"}
    };

    return instance;
}

int main() {
    try {
        ServiceRegistry registry(HealthPolicy(2, 2));

        std::vector<ServiceInstance> deployment = {
            makeInstance(
                "pay-001",
                "payment-service",
                "10.0.1.10",
                8001,
                "2.1.0",
                3
            ),
            makeInstance(
                "pay-002",
                "payment-service",
                "10.0.1.11",
                8001,
                "2.1.0",
                1
            ),
            makeInstance(
                "inv-001",
                "inventory-service",
                "10.0.2.10",
                8002,
                "1.4.0",
                2
            )
        };

        for (auto& instance : deployment) {
            registry.registerService(instance);

            registry.updateHealth(instance.id, true);
            registry.updateHealth(instance.id, true);
        }

        std::cout << "\nDISCOVERY\n";

        auto payments = registry.discover(
            "payment-service",
            std::string("2.1.0"),
            {{"environment", "production"}}
        );

        for (const auto& id : payments) {
            std::cout << id << '\n';
        }

        std::cout << "\nROUND-ROBIN\n";

        for (int i = 0; i < 4; ++i) {
            const auto& selected =
                registry.selectRoundRobin("payment-service");

            std::cout << selected.endpoint() << '\n';
        }

        std::cout << "\nWEIGHTED SELECTION\n";

        std::mt19937 generator(std::random_device{}());

        for (int i = 0; i < 5; ++i) {
            const auto& selected =
                registry.selectWeighted(
                    "payment-service",
                    generator
                );

            std::cout << selected.endpoint() << '\n';
        }

        std::cout << "\nFAILURE SIMULATION\n";

        registry.updateHealth("pay-001", false);
        registry.updateHealth("pay-001", false);

        std::cout << "\nHEALTHY ENDPOINTS\n";

        for (const auto& id :
             registry.discover("payment-service")) {
            std::cout << id << '\n';
        }

        std::cout << "\nGRACEFUL DRAINING\n";

        registry.drain("pay-002");

        registry.printReport();

        std::cout << "\nCIRCUIT BREAKER\n";

        registry.recordRequest("pay-001", false);
        registry.recordRequest("pay-001", false);
        registry.recordRequest("pay-001", false);

        try {
            registry.selectWeighted("payment-service", generator);
        } catch (const ServiceUnavailable& error) {
            std::cout << error.what() << '\n';
        }

        std::cout << "\nVALIDATION TEST\n";

        try {
            auto invalid = makeInstance(
                "invalid",
                "payment-service",
                "127.0.0.1",
                70000,
                "1.0.0",
                1
            );

            registry.registerService(invalid);
        } catch (const ValidationError& error) {
            std::cout << "Rejected: " << error.what() << '\n';
        }

        std::cout << "\nDEREGISTRATION\n";

        registry.deregisterService("inv-001");

        std::cout << "Remaining instances: "
                  << registry.size() << '\n';

        std::cout << "\nALL OPERATIONS COMPLETED\n";

    } catch (const std::exception& error) {
        std::cerr << "Execution error: "
                  << error.what() << '\n';

        return 1;
    }

    return 0;
}
