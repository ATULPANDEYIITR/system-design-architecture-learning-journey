#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using Clock = std::chrono::steady_clock;

enum class FailureType {
    Transient,
    RateLimited,
    Timeout,
    Permanent
};

enum class CircuitState {
    Closed,
    Open,
    HalfOpen
};

enum class JitterMode {
    None,
    Full,
    Equal
};

struct RetryPolicy {
    int maxAttempts = 5;
    double initialDelay = 0.1;
    double multiplier = 2.0;
    double maxDelay = 5.0;
    double timeout = 2.0;
    double maxElapsed = 15.0;
    JitterMode jitter = JitterMode::Full;

    void validate() const {
        if (maxAttempts < 1 ||
            initialDelay < 0 ||
            multiplier < 1 ||
            maxDelay < 0 ||
            timeout <= 0 ||
            maxElapsed <= 0) {
            throw std::invalid_argument("Invalid retry policy");
        }
    }
};

struct Attempt {
    int number;
    std::string outcome;
    double delay;
    double elapsed;
    std::string error;
};

struct Result {
    bool success = false;
    int attempts = 0;
    double elapsed = 0;
    std::string value;
    std::vector<Attempt> history;
};

class RetryBudget {
private:
    double capacity;
    double tokens;
    double refillRate;
    Clock::time_point updatedAt;

public:
    RetryBudget(double capacity, double refillRate)
        : capacity(capacity),
          tokens(capacity),
          refillRate(refillRate),
          updatedAt(Clock::now()) {
        if (capacity < 1 || refillRate < 0) {
            throw std::invalid_argument("Invalid retry budget");
        }
    }

    bool consume() {
        auto now = Clock::now();

        double elapsed =
            std::chrono::duration<double>(
                now - updatedAt
            ).count();

        tokens = std::min(
            capacity,
            tokens + elapsed * refillRate
        );

        updatedAt = now;

        if (tokens < 1) return false;

        tokens -= 1;
        return true;
    }
};

class CircuitBreaker {
private:
    int threshold;
    int failures = 0;
    int halfOpenLimit;
    int halfOpenCalls = 0;
    double recoveryTimeout;
    Clock::time_point openedAt;

public:
    CircuitState state = CircuitState::Closed;

    CircuitBreaker(
        int threshold = 3,
        double recoveryTimeout = 3.0,
        int halfOpenLimit = 1
    )
        : threshold(threshold),
          halfOpenLimit(halfOpenLimit),
          recoveryTimeout(recoveryTimeout) {
        if (threshold < 1 ||
            recoveryTimeout <= 0 ||
            halfOpenLimit < 1) {
            throw std::invalid_argument(
                "Invalid circuit breaker settings"
            );
        }
    }

    bool allowRequest() {
        if (state == CircuitState::Open) {
            double elapsed =
                std::chrono::duration<double>(
                    Clock::now() - openedAt
                ).count();

            if (elapsed < recoveryTimeout) {
                return false;
            }

            state = CircuitState::HalfOpen;
            halfOpenCalls = 0;
        }

        if (state == CircuitState::HalfOpen) {
            if (halfOpenCalls >= halfOpenLimit) {
                return false;
            }

            ++halfOpenCalls;
        }

        return true;
    }

    void recordSuccess() {
        failures = 0;
        halfOpenCalls = 0;
        state = CircuitState::Closed;
    }

    void recordFailure() {
        ++failures;

        if (state == CircuitState::HalfOpen ||
            failures >= threshold) {
            state = CircuitState::Open;
            openedAt = Clock::now();
            halfOpenCalls = 0;
        }
    }
};

class RetryExecutor {
private:
    RetryPolicy policy;
    RetryBudget& budget;
    CircuitBreaker& breaker;

    std::mt19937 generator;

    double calculateDelay(int retryNumber) {
        double ceiling = std::min(
            policy.maxDelay,
            policy.initialDelay *
                std::pow(policy.multiplier, retryNumber)
        );

        if (policy.jitter == JitterMode::None) {
            return ceiling;
        }

        if (policy.jitter == JitterMode::Full) {
            std::uniform_real_distribution<double> distribution(
                0.0, ceiling
            );

            return distribution(generator);
        }

        std::uniform_real_distribution<double> distribution(
            ceiling / 2.0, ceiling
        );

        return distribution(generator);
    }

public:
    RetryExecutor(
        RetryPolicy policy,
        RetryBudget& budget,
        CircuitBreaker& breaker
    )
        : policy(policy),
          budget(budget),
          breaker(breaker),
          generator(std::random_device{}()) {
        policy.validate();
    }

    template<typename Operation>
    Result execute(Operation operation) {
        auto started = Clock::now();
        Result result;

        for (int attempt = 1;
             attempt <= policy.maxAttempts;
             ++attempt) {

            double elapsed =
                std::chrono::duration<double>(
                    Clock::now() - started
                ).count();

            if (elapsed >= policy.maxElapsed) {
                throw std::runtime_error(
                    "Maximum elapsed time exceeded"
                );
            }

            if (!breaker.allowRequest()) {
                throw std::runtime_error(
                    "Circuit breaker is open"
                );
            }

            auto attemptStarted = Clock::now();

            try {
                std::string value = operation(policy.timeout);

                double duration =
                    std::chrono::duration<double>(
                        Clock::now() - attemptStarted
                    ).count();

                breaker.recordSuccess();

                result.success = true;
                result.attempts = attempt;
                result.value = value;
                result.elapsed =
                    std::chrono::duration<double>(
                        Clock::now() - started
                    ).count();

                result.history.push_back({
                    attempt, "success", 0, duration, ""
                });

                return result;

            } catch (const std::invalid_argument&) {
                breaker.recordSuccess();
                throw;

            } catch (const std::exception& error) {
                breaker.recordFailure();

                double duration =
                    std::chrono::duration<double>(
                        Clock::now() - attemptStarted
                    ).count();

                if (attempt == policy.maxAttempts) {
                    result.history.push_back({
                        attempt, "exhausted", 0,
                        duration, error.what()
                    });

                    throw std::runtime_error(
                        "Retry attempts exhausted"
                    );
                }

                if (!budget.consume()) {
                    throw std::runtime_error(
                        "Retry budget exhausted"
                    );
                }

                double delay = calculateDelay(attempt - 1);

                double remaining =
                    policy.maxElapsed -
                    std::chrono::duration<double>(
                        Clock::now() - started
                    ).count();

                if (delay >= remaining) {
                    throw std::runtime_error(
                        "Insufficient time for retry"
                    );
                }

                result.history.push_back({
                    attempt, "retry", delay,
                    duration, error.what()
                });

                std::this_thread::sleep_for(
                    std::chrono::duration<double>(delay)
                );
            }
        }

        throw std::runtime_error("Execution failed");
    }
};

class SimulatedService {
private:
    int failuresRemaining;
    int calls = 0;

public:
    explicit SimulatedService(int failures)
        : failuresRemaining(failures) {}

    std::string request(double timeout) {
        ++calls;

        if (failuresRemaining > 0) {
            --failuresRemaining;
            throw std::runtime_error(
                "Temporary dependency failure"
            );
        }

        return "HTTP 200: response received";
    }

    int getCalls() const {
        return calls;
    }
};

struct StormResult {
    int totalRetries;
    int maximumConcurrent;
    std::map<int, int> schedule;
};

StormResult simulateRetryStorm(
    int clients,
    int retries,
    double initialDelay,
    double multiplier,
    bool jitter
) {
    if (clients < 1 || retries < 0 ||
        initialDelay < 0 || multiplier < 1) {
        throw std::invalid_argument(
            "Invalid storm simulation parameters"
        );
    }

    std::mt19937 generator(std::random_device{}());
    std::map<int, int> schedule;

    for (int client = 0; client < clients; ++client) {
        double elapsed = 0;

        for (int retry = 0; retry < retries; ++retry) {
            double ceiling = initialDelay *
                std::pow(multiplier, retry);

            double delay = ceiling;

            if (jitter) {
                std::uniform_real_distribution<double> distribution(
                    0.0, ceiling
                );

                delay = distribution(generator);
            }

            elapsed += delay;

            int bucket = static_cast<int>(
                std::round(elapsed * 10)
            );

            schedule[bucket]++;
        }
    }

    int maximum = 0;

    for (const auto& item : schedule) {
        maximum = std::max(maximum, item.second);
    }

    return {
        clients * retries,
        maximum,
        schedule
    };
}

void printStorm(const std::string& name,
                const StormResult& result) {
    std::cout << "\n" << name << "\n";
    std::cout << "Total retries: "
              << result.totalRetries << "\n";
    std::cout << "Maximum simultaneous retries: "
              << result.maximumConcurrent << "\n";
}

int main() {
    try {
        RetryPolicy policy;
        policy.maxAttempts = 4;
        policy.initialDelay = 0.01;
        policy.maxDelay = 0.05;
        policy.maxElapsed = 3.0;

        RetryBudget budget(20, 10);
        CircuitBreaker breaker(5, 1.0);

        RetryExecutor executor(
            policy, budget, breaker
        );

        SimulatedService service(2);

        Result result = executor.execute(
            [&service](double timeout) {
                return service.request(timeout);
            }
        );

        if (!result.success || result.attempts != 3) {
            throw std::runtime_error(
                "Recovery test failed"
            );
        }

        std::cout << "Dependency response: "
                  << result.value << "\n";

        std::cout << "Attempts: "
                  << result.attempts << "\n";

        std::cout << "Elapsed: "
                  << std::fixed
                  << std::setprecision(4)
                  << result.elapsed << " seconds\n";

        std::cout << "\nAttempt history:\n";

        for (const auto& attempt : result.history) {
            std::cout
                << "Attempt " << attempt.number
                << " | " << attempt.outcome
                << " | Delay " << attempt.delay
                << " | " << attempt.error
                << "\n";
        }

        auto synchronized = simulateRetryStorm(
            100, 4, 1.0, 2.0, false
        );

        auto randomized = simulateRetryStorm(
            100, 4, 1.0, 2.0, true
        );

        printStorm("Without jitter", synchronized);
        printStorm("With full jitter", randomized);

        std::cout << "\nAll tests passed.\n";

    } catch (const std::exception& error) {
        std::cerr << "Execution error: "
                  << error.what() << "\n";
        return 1;
    }

    return 0;
}
