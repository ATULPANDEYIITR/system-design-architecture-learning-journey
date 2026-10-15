#include <algorithm>
#include <chrono>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

/*
 * Repository-independent case study:
 *
 * A high-volume order service receives requests from clients that retry after
 * network timeouts. The service needs a deterministic merge-like decision:
 * execute a logical operation once, remember its result, and return that same
 * result for subsequent attempts carrying the same idempotency key.
 *
 * This C++ program focuses on the concurrency and state-machine perspective.
 * It models a reservation engine rather than translating the Python or
 * JavaScript payment/order examples.
 *
 * C++17 is sufficient.
 */

enum class OperationState {
    PROCESSING,
    COMPLETED
};

struct OperationResult {
    int statusCode;
    std::string reservationId;
    std::string customerId;
    int seats;
    bool replayed;
};

struct OperationRecord {
    std::string fingerprint;
    OperationState state;
    std::optional<OperationResult> result;
};

class IdempotencyConflict : public std::runtime_error {
public:
    explicit IdempotencyConflict(const std::string& message)
        : std::runtime_error(message) {}
};

class OperationInProgress : public std::runtime_error {
public:
    explicit OperationInProgress(const std::string& message)
        : std::runtime_error(message) {}
};

class ReservationService {
private:
    std::mutex mutex_;
    std::unordered_map<std::string, int> reservedSeats_;
    std::uint64_t nextReservationNumber_ = 1000;

public:
    OperationResult reserve(
        const std::string& customerId,
        const std::string& eventId,
        int seats
    ) {
        if (customerId.empty()) {
            throw std::invalid_argument("customerId cannot be empty");
        }

        if (eventId.empty()) {
            throw std::invalid_argument("eventId cannot be empty");
        }

        if (seats <= 0 || seats > 20) {
            throw std::invalid_argument(
                "seats must be between 1 and 20"
            );
        }

        std::lock_guard<std::mutex> lock(mutex_);

        int& current = reservedSeats_[eventId];

        if (current + seats > 100) {
            throw std::runtime_error(
                "reservation would exceed event capacity"
            );
        }

        current += seats;

        std::ostringstream id;
        id << "res-" << nextReservationNumber_++;

        return OperationResult{
            201,
            id.str(),
            customerId,
            seats,
            false
        };
    }

    int reservedFor(const std::string& eventId) const {
        auto* mutableThis = const_cast<ReservationService*>(this);
        std::lock_guard<std::mutex> lock(mutableThis->mutex_);

        auto iterator = mutableThis->reservedSeats_.find(eventId);
        return iterator == mutableThis->reservedSeats_.end()
            ? 0
            : iterator->second;
    }
};

class GovernanceEngine {
private:
    std::mutex mutex_;
    std::map<std::string, OperationRecord> records_;

public:
    /*
     * The fingerprint is intentionally supplied by the API layer. The
     * idempotency engine does not need to understand every business field; it
     * only needs to know whether the same key represents the same request.
     */
    std::optional<OperationResult> begin(
        const std::string& key,
        const std::string& fingerprint
    ) {
        if (key.empty()) {
            throw std::invalid_argument("idempotency key cannot be empty");
        }

        std::lock_guard<std::mutex> lock(mutex_);

        auto iterator = records_.find(key);

        if (iterator == records_.end()) {
            records_.emplace(
                key,
                OperationRecord{
                    fingerprint,
                    OperationState::PROCESSING,
                    std::nullopt
                }
            );

            return std::nullopt;
        }

        OperationRecord& record = iterator->second;

        if (record.fingerprint != fingerprint) {
            throw IdempotencyConflict(
                "same idempotency key used for a different reservation"
            );
        }

        if (record.state == OperationState::PROCESSING) {
            throw OperationInProgress(
                "logical reservation is already being processed"
            );
        }

        OperationResult replay = *record.result;
        replay.replayed = true;
        return replay;
    }

    void complete(
        const std::string& key,
        const OperationResult& result
    ) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto iterator = records_.find(key);

        if (iterator == records_.end()) {
            throw std::logic_error(
                "cannot complete a missing idempotency record"
            );
        }

        iterator->second.state = OperationState::COMPLETED;
        iterator->second.result = result;
    }

    void abandonOnlyWhenNoSideEffectOccurred(
        const std::string& key
    ) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto iterator = records_.find(key);

        if (iterator != records_.end() &&
            iterator->second.state == OperationState::PROCESSING) {
            records_.erase(iterator);
        }
    }

    std::size_t recordCount() const {
        auto* mutableThis = const_cast<GovernanceEngine*>(this);
        std::lock_guard<std::mutex> lock(mutableThis->mutex_);
        return mutableThis->records_.size();
    }
};

class ReservationApi {
private:
    GovernanceEngine& idempotency_;
    ReservationService& reservations_;

public:
    ReservationApi(
        GovernanceEngine& idempotency,
        ReservationService& reservations
    )
        : idempotency_(idempotency),
          reservations_(reservations) {}

    OperationResult postReservation(
        const std::string& key,
        const std::string& customerId,
        const std::string& eventId,
        int seats,
        bool simulateTimeoutAfterSideEffect = false
    ) {
        const std::string fingerprint =
            customerId + "|" + eventId + "|" + std::to_string(seats);

        auto existing = idempotency_.begin(key, fingerprint);

        if (existing.has_value()) {
            return *existing;
        }

        try {
            OperationResult result =
                reservations_.reserve(customerId, eventId, seats);

            /*
             * Completion is recorded before the operation is considered
             * safely retryable. In a production implementation the business
             * mutation and idempotency record should share a transaction or
             * equivalent durable consistency mechanism.
             */
            idempotency_.complete(key, result);

            if (simulateTimeoutAfterSideEffect) {
                /*
                 * The client sees an exception even though the durable result
                 * is recorded. Retrying the same key therefore replays it.
                 */
                throw std::runtime_error(
                    "network timeout after reservation was committed"
                );
            }

            return result;
        }
        catch (...) {
            /*
             * If complete() already ran, the record is COMPLETED and this
             * function deliberately does not remove it. Removing a completed
             * record could permit a duplicate reservation.
             */
            idempotency_.abandonOnlyWhenNoSideEffectOccurred(key);
            throw;
        }
    }
};

void printResult(const std::string& label, const OperationResult& result) {
    std::cout
        << label
        << ": status=" << result.statusCode
        << ", reservation=" << result.reservationId
        << ", customer=" << result.customerId
        << ", seats=" << result.seats
        << ", replayed=" << std::boolalpha << result.replayed
        << '\n';
}

void basicRetryCase() {
    std::cout << "\n=== Safe retry ===\n";

    GovernanceEngine engine;
    ReservationService reservations;
    ReservationApi api(engine, reservations);

    const std::string key = "reservation-001";

    OperationResult first =
        api.postReservation(key, "cust-10", "concert-2026", 2);

    OperationResult retry =
        api.postReservation(key, "cust-10", "concert-2026", 2);

    printResult("First", first);
    printResult("Retry", retry);

    std::cout
        << "Seats reserved for event: "
        << reservations.reservedFor("concert-2026")
        << '\n';
}

void conflictCase() {
    std::cout << "\n=== Key conflict ===\n";

    GovernanceEngine engine;
    ReservationService reservations;
    ReservationApi api(engine, reservations);

    const std::string key = "reservation-002";

    api.postReservation(key, "cust-20", "concert-2026", 3);

    try {
        api.postReservation(key, "cust-20", "concert-2026", 4);
    }
    catch (const IdempotencyConflict& error) {
        std::cout << "Rejected safely: " << error.what() << '\n';
    }

    std::cout
        << "Seats reserved: "
        << reservations.reservedFor("concert-2026")
        << '\n';
}

void timeoutRecoveryCase() {
    std::cout << "\n=== Timeout after durable side effect ===\n";

    GovernanceEngine engine;
    ReservationService reservations;
    ReservationApi api(engine, reservations);

    const std::string key = "reservation-003";

    try {
        api.postReservation(
            key,
            "cust-30",
            "concert-2026",
            5,
            true
        );
    }
    catch (const std::runtime_error& error) {
        std::cout << "Caller observed: " << error.what() << '\n';
    }

    OperationResult recovered =
        api.postReservation(
            key,
            "cust-30",
            "concert-2026",
            5
        );

    printResult("Recovered", recovered);

    std::cout
        << "Seats reserved: "
        << reservations.reservedFor("concert-2026")
        << '\n';
}

void concurrentCase() {
    std::cout << "\n=== Concurrent duplicate attempts ===\n";

    GovernanceEngine engine;
    ReservationService reservations;
    ReservationApi api(engine, reservations);

    const std::string key = "reservation-concurrent";

    std::mutex outputMutex;
    std::vector<std::thread> workers;

    for (int i = 0; i < 8; ++i) {
        workers.emplace_back([&, i]() {
            try {
                OperationResult result =
                    api.postReservation(
                        key,
                        "cust-concurrent",
                        "concert-2026",
                        1
                    );

                std::lock_guard<std::mutex> lock(outputMutex);
                std::cout
                    << "worker " << i
                    << " received " << result.reservationId
                    << " replayed=" << std::boolalpha
                    << result.replayed
                    << '\n';
            }
            catch (const OperationInProgress& error) {
                std::lock_guard<std::mutex> lock(outputMutex);
                std::cout
                    << "worker " << i
                    << " rejected while another request owned the key: "
                    << error.what()
                    << '\n';
            }
            catch (const std::exception& error) {
                std::lock_guard<std::mutex> lock(outputMutex);
                std::cout
                    << "worker " << i
                    << " failed: " << error.what()
                    << '\n';
            }
        });
    }

    for (auto& worker : workers) {
        worker.join();
    }

    std::cout
        << "Total event seats reserved: "
        << reservations.reservedFor("concert-2026")
        << '\n';
}

void explainDesignConstraints() {
    std::cout << "\n=== Engineering constraints ===\n";

    std::cout
        << "An idempotency key identifies a logical operation, not merely "
           "an HTTP packet.\n";

    std::cout
        << "The request fingerprint prevents accidental key reuse with "
           "different business parameters.\n";

    std::cout
        << "A completed response can be replayed without executing the "
           "business operation again.\n";

    std::cout
        << "An in-memory implementation does not provide cross-process "
           "durability and therefore is not sufficient by itself for a "
           "distributed production API.\n";

    std::cout
        << "Idempotency reduces duplicate logical execution but does not "
           "magically create distributed exactly-once semantics.\n";
}

int main() {
    try {
        basicRetryCase();
        conflictCase();
        timeoutRecoveryCase();
        concurrentCase();
        explainDesignConstraints();
    }
    catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
