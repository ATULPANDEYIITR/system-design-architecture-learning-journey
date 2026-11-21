#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class Architecture {
    ACTIVE_ACTIVE,
    ACTIVE_PASSIVE
};

enum class NodeRole {
    ACTIVE,
    PASSIVE,
    FAILED,
    RECOVERING
};

enum class NodeStatus {
    HEALTHY,
    DEGRADED,
    DOWN
};

enum class ReplicationMode {
    SYNCHRONOUS,
    ASYNCHRONOUS
};

enum class FailoverResult {
    NOT_REQUIRED,
    SUCCESS,
    REJECTED,
    NO_STANDBY
};

string toString(Architecture value) {
    return value == Architecture::ACTIVE_ACTIVE
        ? "ACTIVE-ACTIVE"
        : "ACTIVE-PASSIVE";
}

string toString(NodeRole value) {
    switch (value) {
        case NodeRole::ACTIVE: return "ACTIVE";
        case NodeRole::PASSIVE: return "PASSIVE";
        case NodeRole::FAILED: return "FAILED";
        case NodeRole::RECOVERING: return "RECOVERING";
    }
    return "UNKNOWN";
}

string toString(NodeStatus value) {
    switch (value) {
        case NodeStatus::HEALTHY: return "HEALTHY";
        case NodeStatus::DEGRADED: return "DEGRADED";
        case NodeStatus::DOWN: return "DOWN";
    }
    return "UNKNOWN";
}

struct WriteRecord {
    uint64_t sequence;
    string key;
    string value;
};

struct Node {
    string id;
    string region;
    size_t capacity;
    size_t currentLoad = 0;

    NodeRole role;
    NodeStatus status = NodeStatus::HEALTHY;

    uint64_t appliedSequence = 0;
    uint64_t replicationLag = 0;

    map<string, string> data;

    bool available() const {
        return status != NodeStatus::DOWN &&
               currentLoad < capacity;
    }
};

struct GovernancePolicy {
    Architecture architecture;
    ReplicationMode replication;

    size_t requiredActiveNodes = 1;
    uint64_t maximumLag = 0;

    bool automaticFailover = true;
    bool allowDegradedWrites = false;
};

class ClusterException : public runtime_error {
public:
    explicit ClusterException(const string& message)
        : runtime_error(message) {}
};

class FencingAuthority {
private:
    uint64_t epoch = 0;
    string owner;

public:
    uint64_t acquire(const string& nodeId) {
        ++epoch;
        owner = nodeId;
        return epoch;
    }

    bool validate(
        const string& nodeId,
        uint64_t token
    ) const {
        return nodeId == owner && token == epoch;
    }

    uint64_t currentEpoch() const {
        return epoch;
    }
};

class RedundancyEngine {
private:
    GovernancePolicy policy;

    map<string, Node> nodes;
    map<string, string> data;
    vector<WriteRecord> writeLog;

    FencingAuthority fencing;

    uint64_t sequence = 0;
    uint64_t primaryToken = 0;

    size_t successfulWrites = 0;
    size_t failedWrites = 0;
    size_t failoverCount = 0;

    vector<Node*> activeNodes() {
        vector<Node*> result;

        for (auto& [id, node] : nodes) {
            if (node.role == NodeRole::ACTIVE &&
                node.available()) {
                result.push_back(&node);
            }
        }

        return result;
    }

    vector<Node*> standbyNodes() {
        vector<Node*> result;

        for (auto& [id, node] : nodes) {
            if (node.role == NodeRole::PASSIVE &&
                node.status == NodeStatus::HEALTHY) {
                result.push_back(&node);
            }
        }

        return result;
    }

    void validateConfiguration() const {
        if (policy.requiredActiveNodes == 0) {
            throw ClusterException(
                "Required active node count must be positive"
            );
        }

        if (nodes.size() < 2) {
            throw ClusterException(
                "At least two nodes are required"
            );
        }

        size_t healthy = 0;

        for (const auto& [id, node] : nodes) {
            if (node.capacity == 0) {
                throw ClusterException(
                    "Node capacity must be positive"
                );
            }

            if (node.id.empty()) {
                throw ClusterException("Empty node ID");
            }

            if (node.status == NodeStatus::HEALTHY) {
                ++healthy;
            }
        }

        if (healthy == 0) {
            throw ClusterException("No healthy node");
        }
    }

    void initializeRoles() {
        if (policy.architecture == Architecture::ACTIVE_ACTIVE) {
            size_t activeCount = 0;

            for (auto& [id, node] : nodes) {
                if (node.status == NodeStatus::HEALTHY) {
                    node.role = NodeRole::ACTIVE;
                    ++activeCount;
                }
            }

            if (activeCount < policy.requiredActiveNodes) {
                throw ClusterException(
                    "Insufficient active nodes"
                );
            }

            primaryToken = fencing.acquire("ACTIVE-ACTIVE");
        } else {
            Node* primary = nullptr;

            for (auto& [id, node] : nodes) {
                if (node.status != NodeStatus::HEALTHY) {
                    node.role = NodeRole::FAILED;
                    continue;
                }

                if (primary == nullptr) {
                    primary = &node;
                    primary->role = NodeRole::ACTIVE;
                } else {
                    node.role = NodeRole::PASSIVE;
                }
            }

            primaryToken = fencing.acquire(primary->id);
        }
    }

    Node& selectNode() {
        auto active = activeNodes();

        if (active.empty()) {
            throw ClusterException("No active node available");
        }

        if (policy.architecture == Architecture::ACTIVE_ACTIVE &&
            active.size() < policy.requiredActiveNodes) {
            throw ClusterException(
                "Active-active availability requirement violated"
            );
        }

        sort(
            active.begin(),
            active.end(),
            [](const Node* a, const Node* b) {
                double loadA =
                    static_cast<double>(a->currentLoad) / a->capacity;

                double loadB =
                    static_cast<double>(b->currentLoad) / b->capacity;

                if (loadA != loadB) {
                    return loadA < loadB;
                }

                if (a->replicationLag != b->replicationLag) {
                    return a->replicationLag < b->replicationLag;
                }

                return a->id < b->id;
            }
        );

        return *active.front();
    }

    void replicateSynchronously(
        Node& source,
        const WriteRecord& record
    ) {
        vector<Node*> replicas;

        for (auto& [id, node] : nodes) {
            if (id == source.id ||
                node.status == NodeStatus::DOWN) {
                continue;
            }

            if (policy.architecture == Architecture::ACTIVE_PASSIVE &&
                node.role != NodeRole::PASSIVE) {
                continue;
            }

            if (node.status != NodeStatus::HEALTHY) {
                throw ClusterException(
                    "Synchronous replica is not healthy"
                );
            }

            replicas.push_back(&node);
        }

        if (replicas.empty()) {
            throw ClusterException(
                "No synchronous replica available"
            );
        }

        for (Node* replica : replicas) {
            replica->data[record.key] = record.value;
            replica->appliedSequence = record.sequence;
            replica->replicationLag = 0;
        }
    }

    void replicateAsynchronously(
        Node& source
    ) {
        for (auto& [id, node] : nodes) {
            if (id == source.id ||
                node.status == NodeStatus::DOWN) {
                continue;
            }

            if (policy.architecture == Architecture::ACTIVE_PASSIVE &&
                node.role != NodeRole::PASSIVE) {
                continue;
            }

            ++node.replicationLag;
        }
    }

public:
    explicit RedundancyEngine(
        GovernancePolicy configuration,
        vector<Node> initialNodes
    ) : policy(configuration) {

        for (auto& node : initialNodes) {
            if (nodes.find(node.id) != nodes.end()) {
                throw ClusterException("Duplicate node ID");
            }

            nodes.emplace(node.id, move(node));
        }

        validateConfiguration();
        initializeRoles();
    }

    bool write(
        const string& key,
        const string& value
    ) {
        if (key.empty()) {
            throw ClusterException("Write key cannot be empty");
        }

        try {
            Node& source = selectNode();

            if (policy.architecture == Architecture::ACTIVE_PASSIVE &&
                !fencing.validate(source.id, primaryToken)) {
                throw ClusterException(
                    "Fencing token rejected stale primary"
                );
            }

            if (source.status == NodeStatus::DEGRADED &&
                !policy.allowDegradedWrites) {
                throw ClusterException(
                    "Writes disabled on degraded node"
                );
            }

            ++source.currentLoad;

            try {
                WriteRecord record{
                    sequence + 1,
                    key,
                    value
                };

                if (policy.replication == ReplicationMode::SYNCHRONOUS) {
                    replicateSynchronously(source, record);
                }

                data[key] = value;
                source.data[key] = value;
                source.appliedSequence = record.sequence;

                if (policy.replication == ReplicationMode::ASYNCHRONOUS) {
                    replicateAsynchronously(source);
                }

                sequence = record.sequence;
                writeLog.push_back(record);
                ++successfulWrites;

                --source.currentLoad;
                return true;

            } catch (...) {
                --source.currentLoad;
                throw;
            }

        } catch (const exception& error) {
            ++failedWrites;
            cerr << "WRITE REJECTED: " << error.what() << '\n';
            return false;
        }
    }

    optional<string> read(const string& key) {
        Node& node = selectNode();

        if (node.status == NodeStatus::DOWN) {
            throw ClusterException("Cannot read from failed node");
        }

        ++node.currentLoad;

        auto iterator = data.find(key);

        optional<string> result;

        if (iterator != data.end()) {
            result = iterator->second;
        }

        --node.currentLoad;

        return result;
    }

    FailoverResult failNode(const string& nodeId) {
        auto iterator = nodes.find(nodeId);

        if (iterator == nodes.end()) {
            throw ClusterException("Unknown node");
        }

        Node& failed = iterator->second;

        if (failed.status == NodeStatus::DOWN) {
            return FailoverResult::REJECTED;
        }

        failed.status = NodeStatus::DOWN;
        failed.role = NodeRole::FAILED;
        failed.currentLoad = 0;

        if (policy.architecture == Architecture::ACTIVE_ACTIVE) {
            auto active = activeNodes();

            return active.size() >= policy.requiredActiveNodes
                ? FailoverResult::NOT_REQUIRED
                : FailoverResult::REJECTED;
        }

        if (!policy.automaticFailover) {
            return FailoverResult::REJECTED;
        }

        auto candidates = standbyNodes();

        if (candidates.empty()) {
            return FailoverResult::NO_STANDBY;
        }

        sort(
            candidates.begin(),
            candidates.end(),
            [](const Node* a, const Node* b) {
                if (a->appliedSequence != b->appliedSequence) {
                    return a->appliedSequence > b->appliedSequence;
                }

                return a->capacity > b->capacity;
            }
        );

        Node* candidate = candidates.front();

        if (candidate->replicationLag > policy.maximumLag) {
            return FailoverResult::REJECTED;
        }

        if (policy.replication == ReplicationMode::SYNCHRONOUS &&
            candidate->appliedSequence != sequence) {
            return FailoverResult::REJECTED;
        }

        primaryToken = fencing.acquire(candidate->id);
        candidate->role = NodeRole::ACTIVE;
        candidate->replicationLag = 0;

        ++failoverCount;

        return FailoverResult::SUCCESS;
    }

    size_t synchronizeNode(const string& nodeId) {
        auto iterator = nodes.find(nodeId);

        if (iterator == nodes.end()) {
            throw ClusterException("Unknown node");
        }

        Node& node = iterator->second;

        if (node.status == NodeStatus::DOWN) {
            throw ClusterException(
                "Cannot synchronize a failed node"
            );
        }

        size_t applied = 0;

        for (const auto& record : writeLog) {
            if (record.sequence > node.appliedSequence) {
                node.data[record.key] = record.value;
                node.appliedSequence = record.sequence;
                ++applied;
            }
        }

        node.replicationLag = sequence - node.appliedSequence;

        return applied;
    }

    void recoverNode(const string& nodeId) {
        auto iterator = nodes.find(nodeId);

        if (iterator == nodes.end()) {
            throw ClusterException("Unknown node");
        }

        Node& node = iterator->second;

        if (node.status != NodeStatus::DOWN) {
            throw ClusterException("Node is not failed");
        }

        node.status = NodeStatus::HEALTHY;
        node.role = NodeRole::RECOVERING;

        synchronizeNode(nodeId);

        if (policy.architecture == Architecture::ACTIVE_ACTIVE) {
            node.role = NodeRole::ACTIVE;
        } else {
            node.role = NodeRole::PASSIVE;
        }
    }

    void printReport() const {
        cout << "\nCLUSTER REPORT\n";
        cout << "Architecture: "
             << toString(policy.architecture) << '\n';

        cout << "Sequence: " << sequence << '\n';
        cout << "Fencing epoch: "
             << fencing.currentEpoch() << '\n';

        cout << "\nNODES\n";

        for (const auto& [id, node] : nodes) {
            cout << id
                 << " | " << node.region
                 << " | " << toString(node.role)
                 << " | " << toString(node.status)
                 << " | capacity=" << node.capacity
                 << " | load=" << node.currentLoad
                 << " | applied=" << node.appliedSequence
                 << " | lag=" << node.replicationLag
                 << '\n';
        }

        cout << "\nMETRICS\n";
        cout << "Successful writes: " << successfulWrites << '\n';
        cout << "Failed writes: " << failedWrites << '\n';
        cout << "Failovers: " << failoverCount << '\n';
    }
};

int main() {
    try {
        cout << "ACTIVE-ACTIVE GOVERNANCE ENGINE\n";

        GovernancePolicy activeActivePolicy{
            Architecture::ACTIVE_ACTIVE,
            ReplicationMode::ASYNCHRONOUS,
            2,
            5,
            true,
            false
        };

        vector<Node> activeActiveNodes{
            {"AA-1", "Mumbai", 100, 0, 0,
             NodeRole::ACTIVE},
            {"AA-2", "Pune", 100, 0, 0,
             NodeRole::ACTIVE},
            {"AA-3", "Delhi", 100, 0, 0,
             NodeRole::ACTIVE}
        };

        RedundancyEngine activeActive(
            activeActivePolicy,
            activeActiveNodes
        );

        activeActive.write("account:101", "ACTIVE");
        activeActive.write("account:102", "PENDING");

        activeActive.printReport();

        cout << "\nFailing AA-1\n";

        auto aaResult = activeActive.failNode("AA-1");

        cout << "Failover result: "
             << static_cast<int>(aaResult) << '\n';

        activeActive.printReport();

        cout << "\nACTIVE-PASSIVE GOVERNANCE ENGINE\n";

        GovernancePolicy activePassivePolicy{
            Architecture::ACTIVE_PASSIVE,
            ReplicationMode::SYNCHRONOUS,
            1,
            0,
            true,
            false
        };

        vector<Node> activePassiveNodes{
            {"AP-PRIMARY", "Mumbai", 200, 0, 0,
             NodeRole::ACTIVE},
            {"AP-STANDBY-1", "Pune", 200, 0, 0,
             NodeRole::PASSIVE},
            {"AP-STANDBY-2", "Delhi", 150, 0, 0,
             NodeRole::PASSIVE}
        };

        RedundancyEngine activePassive(
            activePassivePolicy,
            activePassiveNodes
        );

        activePassive.write("inventory:001", "500");
        activePassive.write("inventory:002", "250");

        activePassive.printReport();

        cout << "\nFailing primary\n";

        auto apResult = activePassive.failNode("AP-PRIMARY");

        cout << "Failover result: "
             << static_cast<int>(apResult) << '\n';

        activePassive.write("inventory:003", "750");

        activePassive.printReport();

        cout << "\nRecovering original primary\n";

        activePassive.recoverNode("AP-PRIMARY");
        activePassive.printReport();

        auto result = activePassive.read("inventory:001");

        cout << "\nRecovered data: "
             << result.value_or("NOT FOUND") << '\n';

    } catch (const exception& error) {
        cerr << "FATAL ERROR: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
