#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

/*
 * Circuit Breaker Governance and Failure Isolation Engine
 *
 * C++17
 *
 * Implements:
 * - Circuit state transitions
 * - Consecutive failure thresholds
 * - Recovery timeout
 * - Half-open probe admission
 * - Dependency-specific isolation
 * - Graceful fallback responses
 * - Health metrics
 * - State transition history
 * - Input validation
 * - Deterministic recovery tests
 */

using Clock = std::chrono::steady_clock;

enum class CircuitState {
    CLOSED,
    OPEN,
    HALF_OPEN
};

enum class DependencyType {
    PAYMENT,
    INVENTORY,
    RECOMMENDATION
};

std::string toString(CircuitState state) {
    switch (state) {
        case CircuitState::CLOSED:
            return "CLOSED";
        case CircuitState::OPEN:
            return "OPEN";
        case CircuitState::HALF_OPEN:
            return "HALF_OPEN";
    }

    throw std::logic_error("Unknown circuit state.");
}

struct CircuitConfig {
    int failureThreshold = 3;
    std::chrono::milliseconds recoveryTimeout{1000};
    int halfOpenMaxCalls = 1;

    void validate() const {
        if (failureThreshold < 1) {
            throw std::invalid_argument(
                "Failure threshold must be positive."
            );
        }

        if (recoveryTimeout.count() <= 0) {
            throw std::invalid_argument(
                "Recovery timeout must be positive."
            );
        }

        if (halfOpenMaxCalls < 1) {
            throw std::invalid_argument(
                "Half-open call limit must be positive."
            );
        }
    }
};

struct CircuitMetrics {
    unsigned long totalCalls = 0;
    unsigned long successes = 0;
    unsigned long failures = 0;
    unsigned long rejected = 0;
    unsigned long fallbacks = 0;
    unsigned long transitions = 0;
};

struct CircuitEvent {
    std::string event;
    std::string details;
    CircuitState state;
};

class CircuitOpenException : public std::runtime_error {
public:
    explicit CircuitOpenException(const std::string& name)
        : std::runtime_error(
            "Circuit is OPEN for dependency: " + name
        ) {}
};

class CircuitBreaker {
private:
    std::string name;
    CircuitConfig config;

    CircuitState state = CircuitState::CLOSED;

    int failureCount = 0;
    int halfOpenInflight = 0;

    std::optional<Clock::time_point> openedAt;

    CircuitMetrics metrics;
    std::vector<CircuitEvent> history;

    void record(
        const std::string& event,
        const std::string& details
    ) {
        history.push_back({
            event,
            details,
            state
        });

        if (history.size() > 100) {
            history.erase(history.begin());
        }
    }

    void transition(
        CircuitState next,
        const std::string& reason
    ) {
        if (state == next) {
            return;
        }

        CircuitState previous = state;
        state = next;

        metrics.transitions++;

        record(
            "STATE_TRANSITION",
            toString(previous) + " -> " +
            toString(next) + ": " + reason
        );
    }

    void refreshState() {
        if (state != CircuitState::OPEN || !openedAt) {
            return;
        }

        auto elapsed = std::chrono::duration_cast<
            std::chrono::milliseconds
        >(Clock::now() - *openedAt);

        if (elapsed >= config.recoveryTimeout) {
            halfOpenInflight = 0;

            transition(
                CircuitState::HALF_OPEN,
                "Recovery timeout elapsed."
            );
        }
    }

    void open(const std::string& reason) {
        openedAt = Clock::now();
        halfOpenInflight = 0;

        transition(CircuitState::OPEN, reason);
    }

public:
    explicit CircuitBreaker(
        std::string dependencyName,
        CircuitConfig breakerConfig = {}
    )
        : name(std::move(dependencyName)),
          config(breakerConfig) {

        if (name.empty()) {
            throw std::invalid_argument(
                "Dependency name cannot be empty."
            );
        }

        config.validate();

        record("INITIALIZED", "Circuit created.");
    }

    CircuitState getState() {
        refreshState();
        return state;
    }

    const CircuitMetrics& getMetrics() const {
        return metrics;
    }

    const std::vector<CircuitEvent>& getHistory() const {
        return history;
    }

    CircuitState acquirePermission() {
        refreshState();

        if (state == CircuitState::OPEN) {
            metrics.rejected++;

            record(
                "CALL_REJECTED",
                "Dependency request rejected."
            );

            throw CircuitOpenException(name);
        }

        CircuitState admittedState = state;

        if (state == CircuitState::HALF_OPEN) {
            if (
                halfOpenInflight >=
                config.halfOpenMaxCalls
            ) {
                metrics.rejected++;

                throw CircuitOpenException(name);
            }

            halfOpenInflight++;
        }

        metrics.totalCalls++;

        return admittedState;
    }

    void onSuccess(CircuitState admittedState) {
        metrics.successes++;

        if (admittedState == CircuitState::HALF_OPEN) {
            halfOpenInflight--;
            failureCount = 0;
            openedAt.reset();

            transition(
                CircuitState::CLOSED,
                "Recovery probe succeeded."
            );
        } else if (state == CircuitState::CLOSED) {
            failureCount = 0;
        }

        record("CALL_SUCCESS", "Dependency succeeded.");
    }

    void onFailure(
        CircuitState admittedState,
        const std::string& reason
    ) {
        metrics.failures++;

        if (admittedState == CircuitState::HALF_OPEN) {
            halfOpenInflight--;

            open("Recovery probe failed.");
        } else if (
            admittedState == CircuitState::CLOSED &&
            state == CircuitState::CLOSED
        ) {
            failureCount++;

            if (failureCount >= config.failureThreshold) {
                open("Failure threshold reached.");
            }
        }

        record("CALL_FAILURE", reason);
    }

    template <typename Operation, typename Fallback>
    auto execute(
        Operation operation,
        Fallback fallback
    ) -> decltype(operation()) {

        CircuitState admittedState;

        try {
            admittedState = acquirePermission();
        } catch (const CircuitOpenException&) {
            metrics.fallbacks++;
            return fallback();
        }

        try {
            auto result = operation();

            onSuccess(admittedState);

            return result;

        } catch (const std::exception& error) {
            onFailure(admittedState, error.what());

            metrics.fallbacks++;

            return fallback();
        }
    }

    void printReport() {
        std::cout
            << "\nDependency: " << name
            << "\nState: " << toString(getState())
            << "\nTotal calls: " << metrics.totalCalls
            << "\nSuccesses: " << metrics.successes
            << "\nFailures: " << metrics.failures
            << "\nRejected: " << metrics.rejected
            << "\nFallbacks: " << metrics.fallbacks
            << "\nTransitions: " << metrics.transitions
            << "\n";

        std::cout << "Event history:\n";

        for (const auto& event : history) {
            std::cout
                << "  [" << toString(event.state) << "] "
                << event.event << ": "
                << event.details << '\n';
        }
    }
};

struct ServiceResponse {
    std::string status;
    std::string message;
    std::string source;
};

class PaymentService {
private:
    CircuitBreaker breaker;
    bool providerAvailable = true;

public:
    PaymentService()
        : breaker(
            "payment-provider",
            CircuitConfig{
                3,
                std::chrono::milliseconds(100),
                1
            }
        ) {}

    void setProviderAvailability(bool available) {
        providerAvailable = available;
    }

    ServiceResponse processPayment(double amount) {
        if (!std::isfinite(amount) || amount <= 0) {
            throw std::invalid_argument(
                "Payment amount must be positive and finite."
            );
        }

        return breaker.execute(
            [&]() -> ServiceResponse {
                if (!providerAvailable) {
                    throw std::runtime_error(
                        "Payment provider unavailable."
                    );
                }

                return {
                    "PROCESSED",
                    "Payment completed.",
                    "REMOTE"
                };
            },
            [&]() -> ServiceResponse {
                return {
                    "PENDING",
                    "Payment stored for reconciliation.",
                    "LOCAL_QUEUE"
                };
            }
        );
    }

    CircuitBreaker& getBreaker() {
        return breaker;
    }
};

class InventoryService {
private:
    CircuitBreaker breaker;

    bool remoteAvailable = true;

    std::map<std::string, int> localCache{
        {"SKU-101", 25},
        {"SKU-102", 8},
        {"SKU-103", 0}
    };

public:
    InventoryService()
        : breaker(
            "inventory-service",
            CircuitConfig{
                2,
                std::chrono::milliseconds(100),
                1
            }
        ) {}

    void setAvailability(bool available) {
        remoteAvailable = available;
    }

    ServiceResponse getInventory(
        const std::string& sku
    ) {
        if (sku.empty()) {
            throw std::invalid_argument(
                "SKU cannot be empty."
            );
        }

        return breaker.execute(
            [&]() -> ServiceResponse {
                if (!remoteAvailable) {
                    throw std::runtime_error(
                        "Inventory service unavailable."
                    );
                }

                auto it = localCache.find(sku);

                if (it == localCache.end()) {
                    throw std::out_of_range(
                        "Unknown inventory SKU."
                    );
                }

                return {
                    "AVAILABLE",
                    "Quantity: " + std::to_string(it->second),
                    "REMOTE"
                };
            },
            [&]() -> ServiceResponse {
                auto it = localCache.find(sku);

                if (it == localCache.end()) {
                    return {
                        "UNAVAILABLE",
                        "No local inventory snapshot.",
                        "NONE"
                    };
                }

                return {
                    "DEGRADED",
                    "Cached quantity: " +
                    std::to_string(it->second),
                    "LOCAL_CACHE"
                };
            }
        );
    }

    CircuitBreaker& getBreaker() {
        return breaker;
    }
};

void runTests() {
    CircuitBreaker breaker(
        "test-service",
        CircuitConfig{
            2,
            std::chrono::milliseconds(30),
            1
        }
    );

    auto operation = []() -> std::string {
        throw std::runtime_error("Simulated failure.");
    };

    auto fallback = []() -> std::string {
        return "SAFE_FALLBACK";
    };

    assert(
        breaker.execute(operation, fallback) ==
        "SAFE_FALLBACK"
    );

    assert(
        breaker.execute(operation, fallback) ==
        "SAFE_FALLBACK"
    );

    assert(breaker.getState() == CircuitState::OPEN);

    std::string rejectedResult = breaker.execute(
        []() -> std::string {
            return "REMOTE";
        },
        fallback
    );

    assert(rejectedResult == "SAFE_FALLBACK");

    std::this_thread::sleep_for(
        std::chrono::milliseconds(40)
    );

    std::string recovered = breaker.execute(
        []() -> std::string {
            return "RECOVERED";
        },
        fallback
    );

    assert(recovered == "RECOVERED");
    assert(breaker.getState() == CircuitState::CLOSED);

    try {
        CircuitConfig invalid{0, std::chrono::milliseconds(10), 1};
        invalid.validate();
        assert(false);
    } catch (const std::invalid_argument&) {
        // Expected validation failure.
    }

    std::cout << "\nAll C++17 tests passed.\n";
}

int main() {
    try {
        std::cout
            << "CIRCUIT BREAKER: FAILURE ISOLATION\n"
            << "==================================\n";

        PaymentService payments;
        payments.setProviderAvailability(false);

        for (double amount : {500.0, 750.0, 1000.0, 1500.0}) {
            ServiceResponse response =
                payments.processPayment(amount);

            std::cout
                << "\nPayment: " << amount
                << "\nStatus: " << response.status
                << "\nSource: " << response.source
                << "\nMessage: " << response.message
                << '\n';
        }

        payments.getBreaker().printReport();

        InventoryService inventory;
        inventory.setAvailability(false);

        std::cout << "\nInventory degradation:\n";

        for (const auto& sku : {
            "SKU-101",
            "SKU-102",
            "SKU-999"
        }) {
            ServiceResponse response =
                inventory.getInventory(sku);

            std::cout
                << sku << ": "
                << response.status << " | "
                << response.message << '\n';
        }

        inventory.getBreaker().printReport();

        runTests();

    } catch (const std::exception& error) {
        std::cerr
            << "Application error: "
            << error.what() << '\n';

        return 1;
    }

    return 0;
}
