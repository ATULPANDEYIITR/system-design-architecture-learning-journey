#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

class LamportClock {
private:
    string nodeId;
    long long value{0};

public:
    explicit LamportClock(string id) : nodeId(std::move(id)) {}

    long long localEvent() {
        return ++value;
    }

    long long send() {
        return ++value;
    }

    long long receive(long long remoteTimestamp) {
        if (remoteTimestamp < 0) {
            throw invalid_argument("Lamport timestamp cannot be negative");
        }

        value = max(value, remoteTimestamp) + 1;
        return value;
    }

    long long current() const {
        return value;
    }
};

class VectorClock {
private:
    string nodeId;
    map<string, long long> clock;

public:
    VectorClock(string id, const set<string>& nodes)
        : nodeId(std::move(id)) {
        if (!nodes.contains(nodeId)) {
            throw invalid_argument("Node must belong to vector clock membership");
        }

        for (const auto& node : nodes) {
            clock[node] = 0;
        }
    }

    map<string, long long> localEvent() {
        ++clock[nodeId];
        return clock;
    }

    map<string, long long> send() {
        return localEvent();
    }

    map<string, long long> receive(
        const map<string, long long>& remote) {

        if (remote.size() != clock.size()) {
            throw invalid_argument("Vector clock dimensions differ");
        }

        for (const auto& [node, value] : remote) {
            if (!clock.contains(node)) {
                throw invalid_argument("Unknown node in remote vector");
            }

            if (value < 0) {
                throw invalid_argument("Vector clock value cannot be negative");
            }

            clock[node] = max(clock[node], value);
        }

        ++clock[nodeId];
        return clock;
    }

    const map<string, long long>& snapshot() const {
        return clock;
    }
};

enum class Causality {
    Before,
    After,
    Equal,
    Concurrent
};

Causality compareVectors(
    const map<string, long long>& left,
    const map<string, long long>& right) {

    if (left.size() != right.size()) {
        throw invalid_argument("Cannot compare vectors of different dimensions");
    }

    bool leftLeq = true;
    bool rightLeq = true;
    bool leftStrict = false;
    bool rightStrict = false;

    for (const auto& [node, leftValue] : left) {
        auto rightIt = right.find(node);

        if (rightIt == right.end()) {
            throw invalid_argument("Vector node membership differs");
        }

        const long long rightValue = rightIt->second;

        if (leftValue > rightValue) {
            leftLeq = false;
            rightStrict = true;
        }

        if (rightValue > leftValue) {
            rightLeq = false;
            leftStrict = true;
        }
    }

    if (leftLeq && rightLeq) {
        return Causality::Equal;
    }

    if (leftLeq && leftStrict) {
        return Causality::Before;
    }

    if (rightLeq && rightStrict) {
        return Causality::After;
    }

    return Causality::Concurrent;
}

string causalityName(Causality relation) {
    switch (relation) {
        case Causality::Before:
            return "BEFORE";
        case Causality::After:
            return "AFTER";
        case Causality::Equal:
            return "EQUAL";
        case Causality::Concurrent:
            return "CONCURRENT";
    }

    return "UNKNOWN";
}

struct PhysicalClock {
    string nodeId;
    double offsetMilliseconds;
    double driftPpm;

    double read(double referenceMilliseconds) const {
        const double driftMilliseconds =
            referenceMilliseconds * driftPpm / 1'000'000.0;

        return referenceMilliseconds +
               offsetMilliseconds +
               driftMilliseconds;
    }
};

struct Event {
    string id;
    string nodeId;
    string type;
    double physicalMilliseconds;
    long long lamport;
    map<string, long long> vector;
    string payload;
};

class RepositoryGovernanceTimeline {
private:
    set<string> nodeIds;
    map<string, LamportClock> lamportClocks;
    map<string, VectorClock> vectorClocks;
    map<string, PhysicalClock> physicalClocks;
    vector<Event> events;

public:
    explicit RepositoryGovernanceTimeline(set<string> nodes)
        : nodeIds(std::move(nodes)) {

        if (nodeIds.empty()) {
            throw invalid_argument("At least one node is required");
        }

        for (const auto& node : nodeIds) {
            lamportClocks.emplace(node, LamportClock(node));
            vectorClocks.emplace(node, VectorClock(node, nodeIds));

            physicalClocks.emplace(
                node,
                PhysicalClock{node, 0.0, 0.0}
            );
        }
    }

    void configurePhysicalClock(
        const string& node,
        double offsetMilliseconds,
        double driftPpm) {

        if (!physicalClocks.contains(node)) {
            throw invalid_argument("Unknown node");
        }

        physicalClocks[node] = PhysicalClock{
            node,
            offsetMilliseconds,
            driftPpm
        };
    }

    Event localEvent(
        const string& id,
        const string& node,
        const string& type,
        double referenceMilliseconds,
        const string& payload) {

        if (!nodeIds.contains(node)) {
            throw invalid_argument("Unknown event node");
        }

        Event event{
            id,
            node,
            type,
            physicalClocks[node].read(referenceMilliseconds),
            lamportClocks[node].localEvent(),
            vectorClocks[node].localEvent(),
            payload
        };

        events.push_back(event);
        return event;
    }

    Event sendEvent(
        const string& id,
        const string& node,
        const string& destination,
        double referenceMilliseconds,
        const string& payload) {

        if (!nodeIds.contains(node) || !nodeIds.contains(destination)) {
            throw invalid_argument("Unknown sender or destination");
        }

        Event event{
            id,
            node,
            "SEND->" + destination,
            physicalClocks[node].read(referenceMilliseconds),
            lamportClocks[node].send(),
            vectorClocks[node].send(),
            payload
        };

        events.push_back(event);
        return event;
    }

    Event receiveEvent(
        const string& id,
        const string& node,
        const Event& message,
        double referenceMilliseconds,
        const string& payload) {

        if (!nodeIds.contains(node)) {
            throw invalid_argument("Unknown receiver");
        }

        Event event{
            id,
            node,
            "RECEIVE<-" + message.nodeId,
            physicalClocks[node].read(referenceMilliseconds),
            lamportClocks[node].receive(message.lamport),
            vectorClocks[node].receive(message.vector),
            payload
        };

        events.push_back(event);
        return event;
    }

    const vector<Event>& getEvents() const {
        return events;
    }
};

void printVector(const map<string, long long>& vector) {
    cout << "{";

    bool first = true;
    for (const auto& [node, value] : vector) {
        if (!first) {
            cout << ", ";
        }

        cout << node << ":" << value;
        first = false;
    }

    cout << "}";
}

void printEvent(const Event& event) {
    cout << left
         << setw(9) << event.id
         << setw(12) << event.nodeId
         << setw(25) << event.type
         << "physical=" << fixed << setprecision(3)
         << event.physicalMilliseconds
         << "ms "
         << "L=" << event.lamport
         << " V=";

    printVector(event.vector);
    cout << '\n';
}

void demonstrateClockSkew() {
    cout << "\n=== Physical Clock Skew ===\n";

    const double reference = 1'000'000.0;

    vector<PhysicalClock> clocks{
        {"api-a", 180.0, 10.0},
        {"api-b", -95.0, -8.0},
        {"api-c", 40.0, 35.0}
    };

    vector<double> readings;

    for (const auto& clock : clocks) {
        const double reading = clock.read(reference);
        readings.push_back(reading);

        cout << clock.nodeId
             << " reads "
             << fixed << setprecision(3)
             << reading
             << " ms\n";
    }

    const auto [minimum, maximum] =
        minmax_element(readings.begin(), readings.end());

    cout << "Observed spread: "
         << (*maximum - *minimum)
         << " ms\n";

    cout << "A physical timestamp includes clock offset and drift, "
         << "so timestamp order is not automatically causal order.\n";
}

void demonstrateGovernanceTimeline() {
    cout << "\n=== Distributed Service Timeline ===\n";

    RepositoryGovernanceTimeline system(
        {"api", "review", "merge"}
    );

    system.configurePhysicalClock("api", 70.0, 12.0);
    system.configurePhysicalClock("review", -40.0, -5.0);
    system.configurePhysicalClock("merge", 25.0, 20.0);

    const double base = 2'000'000.0;

    const Event request = system.localEvent(
        "evt-001",
        "api",
        "REQUEST_CREATED",
        base,
        "operation=create"
    );

    const Event reviewMessage = system.sendEvent(
        "evt-002",
        "api",
        "review",
        base + 5.0,
        "review-request"
    );

    const Event reviewReceived = system.receiveEvent(
        "evt-003",
        "review",
        reviewMessage,
        base + 12.0,
        "reviewer=alice"
    );

    const Event approvalMessage = system.sendEvent(
        "evt-004",
        "review",
        "merge",
        base + 20.0,
        "approval"
    );

    const Event mergeReceived = system.receiveEvent(
        "evt-005",
        "merge",
        approvalMessage,
        base + 30.0,
        "approval-recorded"
    );

    const Event independentReview = system.localEvent(
        "evt-006",
        "review",
        "COMMENT_ADDED",
        base + 35.0,
        "clarify-timeout"
    );

    const Event mergeDecision = system.localEvent(
        "evt-007",
        "merge",
        "MERGE_DECISION",
        base + 40.0,
        "eligible=true"
    );

    for (const auto& event : system.getEvents()) {
        printEvent(event);
    }

    cout << "\nCausality relationships:\n";

    cout << "evt-002 -> evt-003: "
         << causalityName(
                compareVectors(
                    reviewMessage.vector,
                    reviewReceived.vector))
         << '\n';

    cout << "evt-004 -> evt-005: "
         << causalityName(
                compareVectors(
                    approvalMessage.vector,
                    mergeReceived.vector))
         << '\n';

    cout << "evt-006 vs evt-007: "
         << causalityName(
                compareVectors(
                    independentReview.vector,
                    mergeDecision.vector))
         << '\n';

    cout << "The final comparison can expose concurrency that "
         << "a scalar Lamport clock alone cannot identify.\n";

    (void)request;
}

void demonstrateOffsetEstimation() {
    cout << "\n=== Clock Offset Estimation ===\n";

    const vector<double> reference{
        10'000.0,
        20'000.0,
        30'000.0,
        40'000.0
    };

    const vector<double> observed{
        10'075.0,
        20'082.0,
        30'077.0,
        40'080.0
    };

    if (reference.size() != observed.size() || reference.empty()) {
        throw runtime_error("Invalid synchronization sample set");
    }

    double totalOffset = 0.0;

    for (size_t i = 0; i < reference.size(); ++i) {
        totalOffset += observed[i] - reference[i];
    }

    const double meanOffset =
        totalOffset / static_cast<double>(reference.size());

    cout << "Estimated mean offset: "
         << fixed << setprecision(3)
         << meanOffset
         << " ms\n";

    cout << "Offset estimation can improve wall-clock agreement, "
         << "but it does not remove message-delay uncertainty.\n";
}

void demonstrateFailures() {
    cout << "\n=== Failure Conditions ===\n";

    try {
        LamportClock clock("service-a");
        clock.receive(-1);
    } catch (const exception& error) {
        cout << "Rejected invalid Lamport timestamp: "
             << error.what() << '\n';
    }

    try {
        set<string> nodes{"a", "b"};
        VectorClock clock("a", nodes);

        clock.receive({{"a", 1}});
    } catch (const exception& error) {
        cout << "Rejected invalid vector: "
             << error.what() << '\n';
    }
}

int main() {
    try {
        demonstrateClockSkew();
        demonstrateGovernanceTimeline();
        demonstrateOffsetEstimation();
        demonstrateFailures();

        cout << "\n=== Design Implications ===\n";
        cout << "Physical time is valuable for operational observation, "
             << "but its accuracy depends on clock synchronization.\n";
        cout << "Lamport clocks provide a compact causal ordering relation.\n";
        cout << "Vector clocks preserve enough causal history to distinguish "
             << "concurrency.\n";
        cout << "A production system commonly stores physical timestamps "
             << "alongside logical metadata rather than choosing only one.\n";
    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
