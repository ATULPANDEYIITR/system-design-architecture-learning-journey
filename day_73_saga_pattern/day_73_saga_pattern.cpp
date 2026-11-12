#include <iostream>
#include <string>
#include <vector>
#include <unordered_set>
#include <unordered_map>
#include <functional>
#include <algorithm>
#include <stdexcept>
#include <chrono>
#include <iomanip>
#include <sstream>

using namespace std;

enum class SagaStatus {
    PENDING,
    RUNNING,
    COMPENSATING,
    COMPLETED,
    COMPENSATED,
    FAILED
};

enum class StepStatus {
    PENDING,
    COMPLETED,
    COMPENSATED,
    FAILED
};

string toString(SagaStatus status) {
    switch (status) {
        case SagaStatus::PENDING: return "PENDING";
        case SagaStatus::RUNNING: return "RUNNING";
        case SagaStatus::COMPENSATING: return "COMPENSATING";
        case SagaStatus::COMPLETED: return "COMPLETED";
        case SagaStatus::COMPENSATED: return "COMPENSATED";
        case SagaStatus::FAILED: return "FAILED";
    }
    return "UNKNOWN";
}

struct Event {
    string name;
    string details;
    string timestamp;
};

string currentTimestamp() {
    using namespace chrono;

    auto now = system_clock::now();
    auto time = system_clock::to_time_t(now);

    stringstream output;
    output << put_time(gmtime(&time), "%Y-%m-%dT%H:%M:%SZ");

    return output.str();
}

class InventoryService {
private:
    unordered_set<string> reservations;

public:
    void reserve(const string& orderId) {
        reservations.insert(orderId);
        cout << "Inventory reserved: " << orderId << '\n';
    }

    void release(const string& orderId) {
        reservations.erase(orderId);
        cout << "Inventory released: " << orderId << '\n';
    }

    bool exists(const string& orderId) const {
        return reservations.count(orderId) > 0;
    }
};

class PaymentService {
private:
    unordered_map<string, double> charges;

public:
    void charge(const string& orderId, double amount) {
        if (amount <= 0 || amount > 1000000) {
            throw invalid_argument("Invalid payment amount");
        }

        charges.emplace(orderId, amount);

        cout << "Payment charged: " << orderId
             << " amount=" << amount << '\n';
    }

    void refund(const string& orderId) {
        charges.erase(orderId);
        cout << "Payment refunded: " << orderId << '\n';
    }

    bool exists(const string& orderId) const {
        return charges.count(orderId) > 0;
    }
};

class ShippingService {
private:
    unordered_set<string> shipments;

public:
    void createShipment(const string& orderId, bool shouldFail) {
        if (shouldFail) {
            throw runtime_error("Shipping provider unavailable");
        }

        shipments.insert(orderId);

        cout << "Shipment created: " << orderId << '\n';
    }

    void cancelShipment(const string& orderId) {
        shipments.erase(orderId);
        cout << "Shipment cancelled: " << orderId << '\n';
    }

    bool exists(const string& orderId) const {
        return shipments.count(orderId) > 0;
    }
};

struct SagaStep {
    string name;
    function<void()> action;
    function<void()> compensation;
    StepStatus status = StepStatus::PENDING;
    int attempts = 0;
};

class Saga {
private:
    string sagaId;
    string orderId;
    SagaStatus status = SagaStatus::PENDING;

    vector<SagaStep> steps;
    vector<size_t> completed;
    vector<Event> history;

    void record(const string& event, const string& details = "") {
        history.push_back({
            event,
            details,
            currentTimestamp()
        });

        cout << "[" << event << "] " << details << '\n';
    }

    void executeStep(size_t index, int maxAttempts) {
        SagaStep& step = steps.at(index);

        for (int attempt = 0; attempt < maxAttempts; ++attempt) {
            step.attempts++;

            try {
                step.action();

                step.status = StepStatus::COMPLETED;
                completed.push_back(index);

                record("STEP_COMPLETED", step.name);
                return;

            } catch (const exception& error) {
                record(
                    "STEP_RETRY",
                    step.name + ": " + error.what()
                );

                if (attempt == maxAttempts - 1) {
                    step.status = StepStatus::FAILED;
                    throw;
                }
            }
        }
    }

    bool compensate() {
        status = SagaStatus::COMPENSATING;

        record("COMPENSATION_STARTED");

        bool success = true;

        for (auto it = completed.rbegin();
             it != completed.rend(); ++it) {

            SagaStep& step = steps.at(*it);

            try {
                step.compensation();
                step.status = StepStatus::COMPENSATED;

                record("STEP_COMPENSATED", step.name);

            } catch (const exception& error) {
                success = false;

                record(
                    "COMPENSATION_FAILED",
                    step.name + ": " + error.what()
                );
            }
        }

        status = success
            ? SagaStatus::COMPENSATED
            : SagaStatus::FAILED;

        return success;
    }

public:
    Saga(
        string id,
        string order,
        vector<SagaStep> sagaSteps
    )
        : sagaId(move(id)),
          orderId(move(order)),
          steps(move(sagaSteps)) {

        if (sagaId.empty() || orderId.empty()) {
            throw invalid_argument("Saga and order IDs are required");
        }

        if (steps.empty()) {
            throw invalid_argument("Saga requires at least one step");
        }
    }

    SagaStatus execute() {
        if (status != SagaStatus::PENDING) {
            throw logic_error("Saga has already been executed");
        }

        status = SagaStatus::RUNNING;
        record("SAGA_STARTED", orderId);

        try {
            for (size_t i = 0; i < steps.size(); ++i) {
                executeStep(i, 3);
            }

            status = SagaStatus::COMPLETED;
            record("SAGA_COMPLETED");

        } catch (const exception& error) {
            record("SAGA_FAILED", error.what());
            compensate();
        }

        return status;
    }

    SagaStatus getStatus() const {
        return status;
    }

    const vector<Event>& getHistory() const {
        return history;
    }
};

vector<SagaStep> createOrderSteps(
    const string& orderId,
    double amount,
    InventoryService& inventory,
    PaymentService& payment,
    ShippingService& shipping,
    bool failShipping
) {
    return {
        {
            "Reserve Inventory",
            [&]() {
                inventory.reserve(orderId);
            },
            [&]() {
                inventory.release(orderId);
            }
        },
        {
            "Charge Payment",
            [&]() {
                payment.charge(orderId, amount);
            },
            [&]() {
                payment.refund(orderId);
            }
        },
        {
            "Create Shipment",
            [&]() {
                shipping.createShipment(orderId, failShipping);
            },
            [&]() {
                shipping.cancelShipment(orderId);
            }
        }
    };
}

int main() {
    try {
        InventoryService inventory;
        PaymentService payment;
        ShippingService shipping;

        cout << "\nCASE 1: Successful Saga\n";

        Saga successful(
            "SAGA-3001",
            "ORDER-3001",
            createOrderSteps(
                "ORDER-3001",
                1500,
                inventory,
                payment,
                shipping,
                false
            )
        );

        cout << "Final status: "
             << toString(successful.execute()) << "\n";

        cout << "\nCASE 2: Shipping Failure\n";

        Saga failed(
            "SAGA-3002",
            "ORDER-3002",
            createOrderSteps(
                "ORDER-3002",
                2500,
                inventory,
                payment,
                shipping,
                true
            )
        );

        cout << "Final status: "
             << toString(failed.execute()) << "\n";

        cout << "\nFINAL STATE\n";

        cout << "Successful inventory reservation: "
             << inventory.exists("ORDER-3001") << '\n';

        cout << "Failed order inventory reservation: "
             << inventory.exists("ORDER-3002") << '\n';

        cout << "Failed order payment: "
             << payment.exists("ORDER-3002") << '\n';

        cout << "Failed order shipment: "
             << shipping.exists("ORDER-3002") << '\n';

        if (failed.getStatus() != SagaStatus::COMPENSATED ||
            inventory.exists("ORDER-3002") ||
            payment.exists("ORDER-3002")) {
            throw runtime_error("Saga verification failed");
        }

        cout << "\nAll assertions passed.\n";

    } catch (const exception& error) {
        cerr << "Application error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
