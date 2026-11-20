#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <queue>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Fault Tolerance: Distributed Repository Service Cluster
 *
 * C++17 governance engine for:
 * - Heartbeat monitoring
 * - Failure detection
 * - Failure classification
 * - Recovery scheduling
 * - Exponential backoff
 * - Replica availability
 * - Event tracking
 */

using namespace std;

enum class NodeState {
    HEALTHY,
    SUSPECT,
    FAILED,
    RECOVERING,
    DISABLED
};

enum class RecoveryResult {
    SUCCESS,
    FAILURE,
    EXHAUSTED,
    DEFERRED
};

string stateName(NodeState state) {
    switch (state) {
        case NodeState::HEALTHY: return "HEALTHY";
        case NodeState::SUSPECT: return "SUSPECT";
        case NodeState::FAILED: return "FAILED";
        case NodeState::RECOVERING: return "RECOVERING";
        case NodeState::DISABLED: return "DISABLED";
    }
    return "UNKNOWN";
}

struct RecoveryPolicy {
    int heartbeatTimeout = 5;
    int failureThreshold = 3;
    int maximumRetries = 3;
    int initialBackoff = 2;
    int maximumBackoff = 16;
    int minimumHealthyReplicas = 2;

    void validate() const {
        if (heartbeatTimeout <= 0 ||
            failureThreshold < 1 ||
            maximumRetries < 0 ||
            initialBackoff <= 0 ||
            maximumBackoff < initialBackoff ||
            minimumHealthyReplicas < 1) {
            throw invalid_argument("Invalid recovery policy");
        }
    }

    int backoff(int attempt) const {
        long long delay = initialBackoff;

        for (int i = 1; i < attempt; ++i) {
            delay = min(
                delay * 2,
                static_cast<long long>(maximumBackoff)
            );
        }

        return static_cast<int>(delay);
    }
};

struct Node {
    string id;
    string hostname;
    NodeState state = NodeState::HEALTHY;
    int lastHeartbeat = 0;
    int missedHeartbeats = 0;
    int recoveryAttempts = 0;
    int nextRecoveryTime = 0;
};

struct Event {
    int timestamp;
    string nodeId;
    string type;
    string description;
};

struct RecoveryTask {
    int executeAt;
    string nodeId;
    int attempt;

    bool operator>(const RecoveryTask& other) const {
        return executeAt > other.executeAt;
    }
};

class FaultToleranceEngine {
private:
    RecoveryPolicy policy;

    map<string, Node> nodes;
    vector<Event> events;

    priority_queue<
        RecoveryTask,
        vector<RecoveryTask>,
        greater<RecoveryTask>
    > recoveryQueue;

    int currentTime = 0;

    void log(
        const string& nodeId,
        const string& type,
        const string& description
    ) {
        events.push_back({
            currentTime,
            nodeId,
            type,
            description
        });
    }

    int healthyReplicas(const string& excluded = "") const {
        int count = 0;

        for (const auto& entry : nodes) {
            if (entry.first != excluded &&
                entry.second.state == NodeState::HEALTHY) {
                ++count;
            }
        }

        return count;
    }

public:
    explicit FaultToleranceEngine(RecoveryPolicy configuration)
        : policy(configuration) {
        policy.validate();
    }

    void registerNode(
        const string& id,
        const string& hostname
    ) {
        if (id.empty() || hostname.empty()) {
            throw invalid_argument("Node identity cannot be empty");
        }

        if (nodes.count(id)) {
            throw runtime_error("Duplicate node registration");
        }

        Node node;
        node.id = id;
        node.hostname = hostname;
        node.lastHeartbeat = currentTime;

        nodes.emplace(id, node);

        log(id, "REGISTERED", hostname);
    }

    void advanceTime(int seconds) {
        if (seconds < 0) {
            throw invalid_argument("Time cannot move backwards");
        }

        currentTime += seconds;
    }

    void heartbeat(const string& id) {
        auto it = nodes.find(id);

        if (it == nodes.end()) {
            throw runtime_error("Unknown node");
        }

        Node& node = it->second;

        if (node.state == NodeState::DISABLED) {
            throw runtime_error("Disabled node cannot heartbeat");
        }

        NodeState previous = node.state;

        node.lastHeartbeat = currentTime;
        node.missedHeartbeats = 0;
        node.state = NodeState::HEALTHY;
        node.recoveryAttempts = 0;
        node.nextRecoveryTime = 0;

        log(id, "HEARTBEAT", "Heartbeat received");

        if (previous != NodeState::HEALTHY) {
            log(id, "RECOVERED", "Node health restored");
        }
    }

    void detectFailures() {
        for (auto& entry : nodes) {
            Node& node = entry.second;

            if (node.state == NodeState::DISABLED ||
                node.state == NodeState::FAILED ||
                node.state == NodeState::RECOVERING) {
                continue;
            }

            int elapsed = currentTime - node.lastHeartbeat;

            if (elapsed < policy.heartbeatTimeout) {
                continue;
            }

            ++node.missedHeartbeats;

            if (node.state == NodeState::HEALTHY) {
                node.state = NodeState::SUSPECT;

                log(
                    node.id,
                    "SUSPECT",
                    "Heartbeat timeout detected"
                );
            }

            if (node.missedHeartbeats >= policy.failureThreshold) {
                node.state = NodeState::FAILED;

                log(
                    node.id,
                    "FAILED",
                    "Consecutive heartbeat failures exceeded threshold"
                );

                scheduleRecovery(node);
            }
        }
    }

    void scheduleRecovery(Node& node) {
        if (node.recoveryAttempts >= policy.maximumRetries) {
            log(
                node.id,
                "RECOVERY_EXHAUSTED",
                "Maximum retry count reached"
            );
            return;
        }

        if (healthyReplicas(node.id) < policy.minimumHealthyReplicas) {
            log(
                node.id,
                "RECOVERY_DEFERRED",
                "Minimum healthy replica requirement not satisfied"
            );
            return;
        }

        int delay = policy.backoff(node.recoveryAttempts + 1);

        node.nextRecoveryTime = currentTime + delay;

        recoveryQueue.push({
            node.nextRecoveryTime,
            node.id,
            node.recoveryAttempts + 1
        });

        log(
            node.id,
            "RECOVERY_SCHEDULED",
            "Retry scheduled after " + to_string(delay) + " seconds"
        );
    }

    RecoveryResult recover(
        const string& id,
        bool restartSuccessful
    ) {
        auto it = nodes.find(id);

        if (it == nodes.end()) {
            throw runtime_error("Unknown node");
        }

        Node& node = it->second;

        if (node.state != NodeState::FAILED) {
            throw runtime_error("Node is not in FAILED state");
        }

        if (node.recoveryAttempts >= policy.maximumRetries) {
            log(id, "RECOVERY_EXHAUSTED", "Retry limit reached");
            return RecoveryResult::EXHAUSTED;
        }

        if (currentTime < node.nextRecoveryTime) {
            throw runtime_error("Recovery backoff is active");
        }

        if (healthyReplicas(id) < policy.minimumHealthyReplicas) {
            log(id, "RECOVERY_DEFERRED", "Insufficient healthy replicas");
            return RecoveryResult::DEFERRED;
        }

        ++node.recoveryAttempts;
        node.state = NodeState::RECOVERING;

        log(
            id,
            "RECOVERY_STARTED",
            "Attempt " + to_string(node.recoveryAttempts)
        );

        if (restartSuccessful) {
            node.state = NodeState::HEALTHY;
            node.missedHeartbeats = 0;
            node.recoveryAttempts = 0;
            node.lastHeartbeat = currentTime;
            node.nextRecoveryTime = 0;

            log(id, "RECOVERY_SUCCESS", "Node restarted successfully");

            return RecoveryResult::SUCCESS;
        }

        node.state = NodeState::FAILED;

        int delay = policy.backoff(node.recoveryAttempts);

        node.nextRecoveryTime = currentTime + delay;

        log(
            id,
            "RECOVERY_FAILURE",
            "Restart unsuccessful; retry delay " + to_string(delay)
        );

        return RecoveryResult::FAILURE;
    }

    void processRecoveryQueue(bool restartSuccessful = true) {
        while (!recoveryQueue.empty()) {
            RecoveryTask task = recoveryQueue.top();

            if (task.executeAt > currentTime) {
                break;
            }

            recoveryQueue.pop();

            auto it = nodes.find(task.nodeId);

            if (it == nodes.end()) {
                continue;
            }

            Node& node = it->second;

            // Ignore outdated scheduled tasks.
            if (node.state != NodeState::FAILED ||
                node.nextRecoveryTime != task.executeAt ||
                node.recoveryAttempts + 1 != task.attempt) {
                continue;
            }

            RecoveryResult result = recover(
                task.nodeId,
                restartSuccessful
            );

            if (result == RecoveryResult::FAILURE) {
                scheduleRecovery(node);
            }
        }
    }

    void disableNode(const string& id) {
        auto it = nodes.find(id);

        if (it == nodes.end()) {
            throw runtime_error("Unknown node");
        }

        it->second.state = NodeState::DISABLED;

        log(id, "DISABLED", "Administrative shutdown");
    }

    void printHealth() const {
        map<NodeState, int> counts;

        for (const auto& entry : nodes) {
            counts[entry.second.state]++;
        }

        cout << "\nCLUSTER HEALTH\n";

        for (const auto& entry : counts) {
            cout << stateName(entry.first)
                 << ": " << entry.second << '\n';
        }

        int healthy = counts[NodeState::HEALTHY];
        double availability = nodes.empty()
            ? 0.0
            : 100.0 * healthy / nodes.size();

        cout << fixed << setprecision(2);
        cout << "Availability: " << availability << "%\n";
        cout << "Total nodes: " << nodes.size() << '\n';
    }

    void printEvents() const {
        cout << "\nEVENT HISTORY\n";

        for (const Event& event : events) {
            cout << "[" << event.timestamp << "] "
                 << event.nodeId << " | "
                 << event.type << " | "
                 << event.description << '\n';
        }
    }

    const Node& getNode(const string& id) const {
        auto it = nodes.find(id);

        if (it == nodes.end()) {
            throw runtime_error("Unknown node");
        }

        return it->second;
    }
};

int main() {
    try {
        RecoveryPolicy policy;

        policy.heartbeatTimeout = 5;
        policy.failureThreshold = 2;
        policy.maximumRetries = 3;
        policy.initialBackoff = 2;
        policy.maximumBackoff = 8;
        policy.minimumHealthyReplicas = 2;

        FaultToleranceEngine cluster(policy);

        cluster.registerNode("NODE-A", "server-a");
        cluster.registerNode("NODE-B", "server-b");
        cluster.registerNode("NODE-C", "server-c");

        cluster.heartbeat("NODE-A");
        cluster.heartbeat("NODE-B");

        // Node C stops sending heartbeats.
        cluster.advanceTime(6);
        cluster.detectFailures();

        if (cluster.getNode("NODE-C").state != NodeState::SUSPECT) {
            throw runtime_error("Suspicion detection failed");
        }

        cluster.advanceTime(6);
        cluster.detectFailures();

        if (cluster.getNode("NODE-C").state != NodeState::FAILED) {
            throw runtime_error("Failure detection failed");
        }

        cluster.printHealth();

        // Process recovery when its backoff period expires.
        cluster.advanceTime(2);
        cluster.processRecoveryQueue(true);

        if (cluster.getNode("NODE-C").state != NodeState::HEALTHY) {
            throw runtime_error("Automatic recovery failed");
        }

        cluster.heartbeat("NODE-C");

        cluster.printHealth();
        cluster.printEvents();

        cout << "\nAll fault-tolerance assertions passed.\n";

        return 0;
    }
    catch (const exception& error) {
        cerr << "Fault-tolerance error: "
             << error.what() << '\n';

        return 1;
    }
}
