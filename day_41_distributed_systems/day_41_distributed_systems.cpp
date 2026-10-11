#include <algorithm>
#include <chrono>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;

// -----------------------------------------------------------------------------
// Repository-style distributed job processing case study
//
// Scenario:
// A payment platform operates three regional processing nodes. Requests can
// arrive at any node. The system replicates state, elects a coordinator,
// evaluates quorum availability, handles retries safely, detects failures,
// and records a causal event sequence.
//
// The example focuses on distributed-system mechanics rather than networking.
// -----------------------------------------------------------------------------

struct Event {
    string id;
    string node;
    string type;
    uint64_t logicalClock;
};

class LamportClock {
private:
    uint64_t value_ = 0;

public:
    uint64_t tick() {
        return ++value_;
    }

    uint64_t receive(uint64_t remote) {
        value_ = max(value_, remote) + 1;
        return value_;
    }

    uint64_t value() const {
        return value_;
    }
};

class DistributedNode {
private:
    string id_;
    bool online_;
    LamportClock clock_;
    vector<Event> events_;

public:
    explicit DistributedNode(string id)
        : id_(move(id)), online_(true) {}

    const string& id() const {
        return id_;
    }

    bool online() const {
        return online_;
    }

    void setOnline(bool value) {
        online_ = value;
    }

    uint64_t localEvent(const string& type) {
        if (!online_) {
            throw runtime_error("Node " + id_ + " is offline");
        }

        uint64_t timestamp = clock_.tick();

        events_.push_back({
            id_ + "-" + to_string(timestamp),
            id_,
            type,
            timestamp
        });

        return timestamp;
    }

    uint64_t receiveEvent(const Event& event) {
        if (!online_) {
            throw runtime_error("Node " + id_ + " cannot receive while offline");
        }

        uint64_t timestamp = clock_.receive(event.logicalClock);

        events_.push_back({
            id_ + "-" + to_string(timestamp),
            id_,
            "RECEIVE:" + event.type,
            timestamp
        });

        return timestamp;
    }

    const vector<Event>& events() const {
        return events_;
    }
};

// -----------------------------------------------------------------------------
// Replicated payment state
// -----------------------------------------------------------------------------

enum class PaymentStatus {
    Pending,
    Authorized,
    Rejected
};

string toString(PaymentStatus status) {
    switch (status) {
        case PaymentStatus::Pending:
            return "PENDING";
        case PaymentStatus::Authorized:
            return "AUTHORIZED";
        case PaymentStatus::Rejected:
            return "REJECTED";
    }

    return "UNKNOWN";
}

struct Payment {
    string paymentId;
    string customerId;
    int amountCents;
    PaymentStatus status;
    uint64_t version;
    string writer;
};

class Replica {
private:
    DistributedNode node_;
    unordered_map<string, Payment> payments_;

public:
    explicit Replica(string id)
        : node_(move(id)) {}

    DistributedNode& node() {
        return node_;
    }

    const DistributedNode& node() const {
        return node_;
    }

    void apply(const Payment& payment) {
        if (!node_.online()) {
            throw runtime_error("Replica is offline");
        }

        auto it = payments_.find(payment.paymentId);

        // Last-version-wins is only the conflict rule for this case study.
        // A real financial system would normally require stronger transactional
        // and consistency guarantees than this simplified mechanism.
        if (it == payments_.end() || payment.version >= it->second.version) {
            payments_[payment.paymentId] = payment;
        }
    }

    optional<Payment> find(const string& paymentId) const {
        if (!node_.online()) {
            return nullopt;
        }

        auto it = payments_.find(paymentId);

        if (it == payments_.end()) {
            return nullopt;
        }

        return it->second;
    }
};

// -----------------------------------------------------------------------------
// Quorum-based governance
// -----------------------------------------------------------------------------

class QuorumReplicatedPaymentStore {
private:
    vector<Replica> replicas_;
    uint64_t version_ = 0;

    size_t quorum() const {
        return replicas_.size() / 2 + 1;
    }

public:
    explicit QuorumReplicatedPaymentStore(vector<string> replicaIds) {
        if (replicaIds.empty()) {
            throw invalid_argument("At least one replica is required");
        }

        set<string> uniqueIds(replicaIds.begin(), replicaIds.end());

        if (uniqueIds.size() != replicaIds.size()) {
            throw invalid_argument("Replica IDs must be unique");
        }

        for (const string& id : replicaIds) {
            replicas_.emplace_back(id);
        }
    }

    Replica& replica(const string& id) {
        for (auto& replica : replicas_) {
            if (replica.node().id() == id) {
                return replica;
            }
        }

        throw out_of_range("Unknown replica: " + id);
    }

    Payment write(
        const string& paymentId,
        const string& customerId,
        int amountCents,
        const string& writer
    ) {
        if (amountCents <= 0) {
            throw invalid_argument("Payment amount must be positive");
        }

        ++version_;

        Payment payment{
            paymentId,
            customerId,
            amountCents,
            PaymentStatus::Authorized,
            version_,
            writer
        };

        size_t acknowledgements = 0;

        for (auto& replica : replicas_) {
            if (!replica.node().online()) {
                continue;
            }

            replica.apply(payment);
            ++acknowledgements;
        }

        if (acknowledgements < quorum()) {
            throw runtime_error(
                "Write quorum unavailable: " +
                to_string(acknowledgements) + "/" +
                to_string(quorum())
            );
        }

        return payment;
    }

    Payment read(const string& paymentId) const {
        vector<Payment> responses;

        for (const auto& replica : replicas_) {
            auto payment = replica.find(paymentId);

            if (payment.has_value()) {
                responses.push_back(*payment);
            }
        }

        if (responses.size() < quorum()) {
            throw runtime_error(
                "Read quorum unavailable: " +
                to_string(responses.size()) + "/" +
                to_string(quorum())
            );
        }

        return *max_element(
            responses.begin(),
            responses.end(),
            [](const Payment& left, const Payment& right) {
                return left.version < right.version;
            }
        );
    }
};

// -----------------------------------------------------------------------------
// Leader election
// -----------------------------------------------------------------------------

class LeaderElection {
private:
    map<int, bool> nodes_;
    optional<int> leader_;

public:
    explicit LeaderElection(initializer_list<int> nodeIds) {
        for (int id : nodeIds) {
            nodes_[id] = true;
        }
    }

    void fail(int nodeId) {
        auto it = nodes_.find(nodeId);

        if (it == nodes_.end()) {
            throw out_of_range("Unknown node");
        }

        it->second = false;

        if (leader_ == nodeId) {
            leader_.reset();
        }
    }

    void recover(int nodeId) {
        auto it = nodes_.find(nodeId);

        if (it == nodes_.end()) {
            throw out_of_range("Unknown node");
        }

        it->second = true;
    }

    int elect() {
        for (auto it = nodes_.rbegin(); it != nodes_.rend(); ++it) {
            if (it->second) {
                leader_ = it->first;
                return it->first;
            }
        }

        throw runtime_error("No live node can become leader");
    }

    optional<int> leader() const {
        return leader_;
    }
};

// -----------------------------------------------------------------------------
// Failure detector
// -----------------------------------------------------------------------------

class FailureDetector {
private:
    chrono::milliseconds timeout_;
    map<string, chrono::steady_clock::time_point> heartbeats_;

public:
    explicit FailureDetector(chrono::milliseconds timeout)
        : timeout_(timeout) {}

    void heartbeat(const string& nodeId) {
        heartbeats_[nodeId] = chrono::steady_clock::now();
    }

    bool suspected(const string& nodeId) const {
        auto it = heartbeats_.find(nodeId);

        if (it == heartbeats_.end()) {
            return true;
        }

        auto elapsed = chrono::duration_cast<chrono::milliseconds>(
            chrono::steady_clock::now() - it->second
        );

        return elapsed > timeout_;
    }
};

// -----------------------------------------------------------------------------
// Idempotency registry
// -----------------------------------------------------------------------------

class IdempotencyRegistry {
private:
    set<string> completed_;

public:
    bool alreadyProcessed(const string& requestId) const {
        return completed_.contains(requestId);
    }

    void markProcessed(const string& requestId) {
        completed_.insert(requestId);
    }
};

// -----------------------------------------------------------------------------
// Distributed transaction-style service
// -----------------------------------------------------------------------------

class PaymentCoordinator {
private:
    LeaderElection election_;
    QuorumReplicatedPaymentStore store_;
    IdempotencyRegistry idempotency_;

public:
    PaymentCoordinator()
        : election_({10, 20, 30}),
          store_({"region-a", "region-b", "region-c"}) {
        election_.elect();
    }

    Payment process(
        const string& requestId,
        const string& customerId,
        int amountCents
    ) {
        if (idempotency_.alreadyProcessed(requestId)) {
            return store_.read(requestId);
        }

        if (!election_.leader().has_value()) {
            election_.elect();
        }

        Payment result = store_.write(
            requestId,
            customerId,
            amountCents,
            "coordinator-" + to_string(*election_.leader())
        );

        idempotency_.markProcessed(requestId);

        return result;
    }

    void failLeader() {
        if (!election_.leader().has_value()) {
            throw runtime_error("No current leader");
        }

        election_.fail(*election_.leader());
        election_.elect();
    }

    int leader() const {
        if (!election_.leader().has_value()) {
            throw runtime_error("No leader");
        }

        return *election_.leader();
    }

    QuorumReplicatedPaymentStore& store() {
        return store_;
    }
};

// -----------------------------------------------------------------------------
// Demonstrations
// -----------------------------------------------------------------------------

void demonstrateLogicalOrdering() {
    cout << "\n=== Logical Ordering ===\n";

    DistributedNode api("api");
    DistributedNode inventory("inventory");

    uint64_t sentClock = api.localEvent("RESERVE_STOCK");

    Event outgoing{
        "api-" + to_string(sentClock),
        api.id(),
        "RESERVE_STOCK",
        sentClock
    };

    uint64_t receivedClock = inventory.receiveEvent(outgoing);

    cout << "API logical timestamp: " << sentClock << '\n';
    cout << "Inventory receive timestamp: " << receivedClock << '\n';
}

void demonstrateFailureDetection() {
    cout << "\n=== Failure Detection ===\n";

    FailureDetector detector(chrono::milliseconds(1000));
    detector.heartbeat("region-a");

    cout << "region-a suspected immediately: "
         << boolalpha << detector.suspected("region-a") << '\n';

    cout << "unknown node suspected: "
         << boolalpha << detector.suspected("region-x") << '\n';
}

void demonstratePaymentSystem() {
    cout << "\n=== Replicated Payment Case Study ===\n";

    PaymentCoordinator coordinator;

    Payment payment = coordinator.process(
        "PAY-9001",
        "CUSTOMER-77",
        125000
    );

    cout << "Leader: " << coordinator.leader() << '\n';
    cout << "Payment: " << payment.paymentId << '\n';
    cout << "Amount: " << payment.amountCents << " cents\n";
    cout << "Status: " << toString(payment.status) << '\n';
    cout << "Version: " << payment.version << '\n';

    Payment retry = coordinator.process(
        "PAY-9001",
        "CUSTOMER-77",
        125000
    );

    cout << "Retry returned version: " << retry.version << '\n';

    coordinator.failLeader();

    cout << "New leader after failover: "
         << coordinator.leader() << '\n';

    Payment second = coordinator.process(
        "PAY-9002",
        "CUSTOMER-88",
        8900
    );

    cout << "Second payment status: "
         << toString(second.status) << '\n';

    coordinator.store().replica("region-c").node().setOnline(false);

    Payment third = coordinator.process(
        "PAY-9003",
        "CUSTOMER-91",
        4500
    );

    cout << "Payment with one replica unavailable: "
         << third.paymentId << '\n';

    coordinator.store().replica("region-b").node().setOnline(false);

    try {
        coordinator.process(
            "PAY-9004",
            "CUSTOMER-99",
            2000
        );
    } catch (const exception& ex) {
        cout << "Expected quorum failure: "
             << ex.what() << '\n';
    }
}

void demonstrateDesignProperties() {
    cout << "\n=== Engineering Properties ===\n";

    cout << "Replication factor: 3\n";
    cout << "Majority quorum: 2\n";
    cout << "A single replica failure can be tolerated for quorum operations.\n";
    cout << "Two unavailable replicas prevent a majority quorum.\n";
    cout << "Request IDs make retries idempotent at the service boundary.\n";
    cout << "Logical clocks establish event ordering without assuming synchronized physical clocks.\n";
    cout << "Leader election identifies a coordinator but does not by itself prevent stale leaders.\n";
    cout << "Failure detection is based on incomplete evidence and therefore requires conservative interpretation.\n";
}

int main() {
    try {
        cout << "Distributed Systems Fundamentals - C++17 Case Study\n";

        demonstrateLogicalOrdering();
        demonstrateFailureDetection();
        demonstratePaymentSystem();
        demonstrateDesignProperties();

        cout << "\nCase study completed successfully.\n";
        return 0;
    } catch (const exception& ex) {
        cerr << "Fatal error: " << ex.what() << '\n';
        return 1;
    }
}
