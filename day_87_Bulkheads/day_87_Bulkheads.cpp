#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;
using Clock = chrono::steady_clock;

enum class CircuitState {
    CLOSED,
    OPEN,
    HALF_OPEN
};

enum class RequestStatus {
    ACCEPTED,
    COMPLETED,
    REJECTED,
    FAILED
};

string toString(CircuitState state) {
    switch (state) {
        case CircuitState::CLOSED: return "CLOSED";
        case CircuitState::OPEN: return "OPEN";
        case CircuitState::HALF_OPEN: return "HALF_OPEN";
    }
    return "UNKNOWN";
}

struct PoolConfig {
    string name;
    size_t maxConcurrent;
    size_t maxQueue;
    int failureThreshold;
    int recoverySeconds;
};

struct Metrics {
    size_t accepted = 0;
    size_t completed = 0;
    size_t failed = 0;
    size_t rejected = 0;
    size_t active = 0;
    size_t peakActive = 0;
};

struct Request {
    int id;
    string operation;
    bool shouldFail = false;
};

class CircuitBreaker {
private:
    CircuitState state = CircuitState::CLOSED;
    int failures = 0;
    int threshold;
    int recoverySeconds;
    Clock::time_point openedAt;
    bool probeInProgress = false;

public:
    CircuitBreaker(int threshold, int recoverySeconds)
        : threshold(threshold),
          recoverySeconds(recoverySeconds) {
        if (threshold < 1 || recoverySeconds < 1) {
            throw invalid_argument("Invalid circuit breaker configuration");
        }
    }

    bool allowRequest() {
        if (state == CircuitState::CLOSED) {
            return true;
        }

        if (state == CircuitState::OPEN) {
            auto elapsed = chrono::duration_cast<chrono::seconds>(
                Clock::now() - openedAt
            ).count();

            if (elapsed < recoverySeconds) {
                return false;
            }

            state = CircuitState::HALF_OPEN;
            probeInProgress = false;
        }

        if (state == CircuitState::HALF_OPEN) {
            if (probeInProgress) {
                return false;
            }

            probeInProgress = true;
            return true;
        }

        return false;
    }

    void success() {
        failures = 0;
        probeInProgress = false;
        state = CircuitState::CLOSED;
    }

    void failure() {
        failures++;
        probeInProgress = false;

        if (failures >= threshold) {
            state = CircuitState::OPEN;
            openedAt = Clock::now();
        }
    }

    void abandon() {
        if (state == CircuitState::HALF_OPEN) {
            probeInProgress = false;
        }
    }

    CircuitState getState() const {
        return state;
    }

    int getFailures() const {
        return failures;
    }
};

class BulkheadPool {
private:
    PoolConfig config;
    CircuitBreaker breaker;
    queue<Request> waiting;
    Metrics metrics;
    set<int> processedIds;

public:
    explicit BulkheadPool(PoolConfig configuration)
        : config(move(configuration)),
          breaker(
              config.failureThreshold,
              config.recoverySeconds
          ) {

        if (config.name.empty() ||
            config.maxConcurrent == 0 ||
            config.failureThreshold == 0 ||
            config.recoverySeconds == 0) {
            throw invalid_argument("Invalid bulkhead pool configuration");
        }
    }

    RequestStatus submit(const Request& request) {
        if (request.id <= 0 || request.operation.empty()) {
            throw invalid_argument("Invalid request");
        }

        if (processedIds.count(request.id)) {
            throw invalid_argument("Duplicate request identifier");
        }

        if (!breaker.allowRequest()) {
            metrics.rejected++;
            return RequestStatus::REJECTED;
        }

        if (metrics.active >= config.maxConcurrent) {
            if (waiting.size() >= config.maxQueue) {
                breaker.abandon();
                metrics.rejected++;
                return RequestStatus::REJECTED;
            }

            waiting.push(request);
            return RequestStatus::ACCEPTED;
        }

        return execute(request);
    }

    RequestStatus execute(const Request& request) {
        if (metrics.active >= config.maxConcurrent) {
            throw logic_error("Concurrency invariant violated");
        }

        metrics.active++;
        metrics.accepted++;

        metrics.peakActive = max(
            metrics.peakActive,
            metrics.active
        );

        RequestStatus result;

        if (request.shouldFail) {
            metrics.failed++;
            breaker.failure();
            result = RequestStatus::FAILED;
        } else {
            metrics.completed++;
            breaker.success();
            result = RequestStatus::COMPLETED;
        }

        processedIds.insert(request.id);
        metrics.active--;

        processQueue();

        return result;
    }

    void processQueue() {
        while (
            metrics.active < config.maxConcurrent &&
            !waiting.empty()
        ) {
            Request request = waiting.front();
            waiting.pop();

            if (!breaker.allowRequest()) {
                metrics.rejected++;
                continue;
            }

            execute(request);
        }
    }

    void report() const {
        cout << left << setw(15) << config.name
             << " state=" << setw(10)
             << toString(breaker.getState())
             << " accepted=" << metrics.accepted
             << " completed=" << metrics.completed
             << " failed=" << metrics.failed
             << " rejected=" << metrics.rejected
             << " queued=" << waiting.size()
             << " active=" << metrics.active
             << " peak=" << metrics.peakActive
             << '\n';
    }

    const Metrics& getMetrics() const {
        return metrics;
    }

    const PoolConfig& getConfig() const {
        return config;
    }

    CircuitState getCircuitState() const {
        return breaker.getState();
    }
};

class GovernanceEngine {
private:
    map<string, BulkheadPool> pools;
    int nextId = 1;

public:
    void registerPool(const PoolConfig& config) {
        if (pools.count(config.name)) {
            throw invalid_argument("Duplicate pool name");
        }

        pools.emplace(config.name, BulkheadPool(config));
    }

    RequestStatus submit(
        const string& poolName,
        const string& operation,
        bool failure = false
    ) {
        auto it = pools.find(poolName);

        if (it == pools.end()) {
            throw invalid_argument("Unknown resource pool");
        }

        Request request{
            nextId++,
            operation,
            failure
        };

        return it->second.submit(request);
    }

    void report() const {
        cout << "\nBULKHEAD GOVERNANCE REPORT\n";
        cout << string(85, '-') << '\n';

        for (const auto& entry : pools) {
            entry.second.report();
        }
    }

    bool isolationInvariant() const {
        for (const auto& entry : pools) {
            const auto& metrics = entry.second.getMetrics();
            const auto& config = entry.second.getConfig();

            if (metrics.active > config.maxConcurrent) {
                return false;
            }
        }

        return true;
    }

    CircuitState state(const string& name) const {
        auto it = pools.find(name);

        if (it == pools.end()) {
            throw invalid_argument("Unknown resource pool");
        }

        return it->second.getCircuitState();
    }
};

int main() {
    try {
        GovernanceEngine engine;

        engine.registerPool({
            "payment", 2, 3, 3, 5
        });

        engine.registerPool({
            "inventory", 3, 4, 3, 5
        });

        engine.registerPool({
            "notification", 1, 2, 2, 5
        });

        cout << "SCENARIO 1: Normal workload\n";

        for (int i = 0; i < 6; ++i) {
            engine.submit("payment", "process-payment");
        }

        for (int i = 0; i < 5; ++i) {
            engine.submit("inventory", "reserve-stock");
        }

        for (int i = 0; i < 4; ++i) {
            engine.submit("notification", "send-message");
        }

        cout << "\nSCENARIO 2: Notification failures\n";

        engine.submit(
            "notification",
            "provider-timeout",
            true
        );

        engine.submit(
            "notification",
            "provider-unavailable",
            true
        );

        cout << "\nSCENARIO 3: Circuit isolation\n";

        cout << "Notification state: "
             << toString(engine.state("notification"))
             << '\n';

        engine.submit("payment", "critical-payment");
        engine.submit("inventory", "critical-reservation");

        cout << "\nSCENARIO 4: Invalid pool\n";

        try {
            engine.submit("unknown", "invalid-operation");
        } catch (const invalid_argument& error) {
            cout << "Validation: " << error.what() << '\n';
        }

        cout << "\nSCENARIO 5: Capacity configuration validation\n";

        try {
            engine.registerPool({
                "invalid", 0, 2, 3, 5
            });
        } catch (const invalid_argument& error) {
            cout << "Configuration: " << error.what() << '\n';
        }

        engine.report();

        if (!engine.isolationInvariant()) {
            throw logic_error("Resource isolation invariant failed");
        }

        cout << "\nIsolation invariants verified.\n";

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
