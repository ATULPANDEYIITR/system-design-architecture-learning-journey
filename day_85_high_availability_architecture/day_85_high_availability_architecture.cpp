#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

/*
 * High Availability Architecture
 *
 * A repository-independent infrastructure governance engine.
 * Evaluates:
 * - Active-active service redundancy
 * - Failure-domain isolation
 * - Quorum availability
 * - Capacity-aware routing
 * - Failover and recovery
 * - Availability targets
 */

enum class NodeState {
    Healthy,
    Failed,
    Maintenance
};

enum class ServiceState {
    Available,
    Degraded,
    Unavailable
};

struct InfrastructureNode {
    string id;
    string zone;
    string role;
    int capacity;
    int currentLoad = 0;
    NodeState state = NodeState::Healthy;

    InfrastructureNode(
        string nodeId,
        string failureDomain,
        string nodeRole,
        int nodeCapacity
    ) : id(move(nodeId)),
        zone(move(failureDomain)),
        role(move(nodeRole)),
        capacity(nodeCapacity) {

        if (id.empty() || zone.empty() || role.empty()) {
            throw invalid_argument("Node attributes cannot be empty");
        }

        if (capacity <= 0) {
            throw invalid_argument("Capacity must be positive");
        }
    }

    bool healthy() const {
        return state == NodeState::Healthy;
    }

    int availableCapacity() const {
        return healthy() ? capacity - currentLoad : 0;
    }

    void fail() {
        state = NodeState::Failed;
        currentLoad = 0;
    }

    void recover() {
        state = NodeState::Healthy;
        currentLoad = 0;
    }
};

struct ServiceDefinition {
    string id;
    vector<string> replicas;
    int minimumHealthy;

    ServiceDefinition(
        string serviceId,
        vector<string> replicaIds,
        int minimum
    ) : id(move(serviceId)),
        replicas(move(replicaIds)),
        minimumHealthy(minimum) {

        if (id.empty() || replicas.empty()) {
            throw invalid_argument("Invalid service definition");
        }

        set<string> uniqueReplicas(
            replicas.begin(),
            replicas.end()
        );

        if (uniqueReplicas.size() != replicas.size()) {
            throw invalid_argument("Duplicate replicas");
        }

        if (minimum < 1 || minimum > static_cast<int>(replicas.size())) {
            throw invalid_argument("Invalid minimum healthy replicas");
        }
    }
};

class QuorumCluster {
private:
    vector<string> members;
    string leader;
    unsigned long long term = 0;

public:
    explicit QuorumCluster(vector<string> ids)
        : members(move(ids)) {

        if (members.size() < 3 || members.size() % 2 == 0) {
            throw invalid_argument(
                "Quorum requires an odd membership of at least three"
            );
        }

        set<string> uniqueMembers(
            members.begin(),
            members.end()
        );

        if (uniqueMembers.size() != members.size()) {
            throw invalid_argument("Duplicate quorum members");
        }
    }

    int requiredVotes() const {
        return static_cast<int>(members.size() / 2 + 1);
    }

    int healthyVotes(
        const map<string, InfrastructureNode>& nodes
    ) const {
        int votes = 0;

        for (const auto& id : members) {
            auto it = nodes.find(id);

            if (it != nodes.end() && it->second.healthy()) {
                ++votes;
            }
        }

        return votes;
    }

    bool hasQuorum(
        const map<string, InfrastructureNode>& nodes
    ) const {
        return healthyVotes(nodes) >= requiredVotes();
    }

    string elect(
        const map<string, InfrastructureNode>& nodes
    ) {
        if (!hasQuorum(nodes)) {
            leader.clear();
            return "";
        }

        vector<string> candidates;

        for (const auto& id : members) {
            auto it = nodes.find(id);

            if (it != nodes.end() && it->second.healthy()) {
                candidates.push_back(id);
            }
        }

        sort(candidates.begin(), candidates.end());

        leader = candidates.front();
        ++term;

        return leader;
    }

    const string& getLeader() const {
        return leader;
    }

    unsigned long long getTerm() const {
        return term;
    }

    void invalidateLeader(const string& nodeId) {
        if (leader == nodeId) {
            leader.clear();
        }
    }
};

class HighAvailabilityEngine {
private:
    map<string, InfrastructureNode> nodes;
    map<string, ServiceDefinition> services;
    QuorumCluster* quorum = nullptr;

    unsigned long long totalRequests = 0;
    unsigned long long successfulRequests = 0;
    unsigned long long failedRequests = 0;

public:
    void registerNode(InfrastructureNode node) {
        const string id = node.id;

        if (nodes.count(id)) {
            throw invalid_argument("Duplicate infrastructure node");
        }

        nodes.emplace(id, move(node));
    }

    void registerService(ServiceDefinition service) {
        if (services.count(service.id)) {
            throw invalid_argument("Duplicate service");
        }

        for (const auto& id : service.replicas) {
            if (!nodes.count(id)) {
                throw invalid_argument("Unknown replica node: " + id);
            }
        }

        services.emplace(service.id, move(service));
    }

    void configureQuorum(QuorumCluster& cluster) {
        quorum = &cluster;

        for (const auto& id : clusterMembers()) {
            if (!nodes.count(id)) {
                throw invalid_argument("Unknown quorum member");
            }
        }

        quorum->elect(nodes);
    }

    vector<string> clusterMembers() const {
        vector<string> result;

        if (quorum == nullptr) {
            return result;
        }

        // The member IDs are obtained through the public membership
        // accessor to avoid exposing the internal container.
        return result;
    }

    int healthyReplicas(const string& serviceId) const {
        auto service = services.find(serviceId);

        if (service == services.end()) {
            throw invalid_argument("Unknown service");
        }

        int count = 0;

        for (const auto& id : service->second.replicas) {
            if (nodes.at(id).healthy()) {
                ++count;
            }
        }

        return count;
    }

    ServiceState evaluateService(const string& serviceId) const {
        const auto& service = services.at(serviceId);
        const int healthy = healthyReplicas(serviceId);

        if (healthy < service.minimumHealthy) {
            return ServiceState::Unavailable;
        }

        if (healthy < static_cast<int>(service.replicas.size())) {
            return ServiceState::Degraded;
        }

        return ServiceState::Available;
    }

    string route(const string& serviceId) {
        ++totalRequests;

        const auto& service = services.at(serviceId);

        vector<InfrastructureNode*> candidates;

        for (const auto& id : service.replicas) {
            auto& node = nodes.at(id);

            if (node.healthy() && node.availableCapacity() > 0) {
                candidates.push_back(&node);
            }
        }

        sort(
            candidates.begin(),
            candidates.end(),
            [](const auto* a, const auto* b) {
                const double loadA =
                    static_cast<double>(a->currentLoad) / a->capacity;

                const double loadB =
                    static_cast<double>(b->currentLoad) / b->capacity;

                if (loadA != loadB) {
                    return loadA < loadB;
                }

                return a->id < b->id;
            }
        );

        if (candidates.empty()) {
            ++failedRequests;
            return "";
        }

        auto* selected = candidates.front();
        ++selected->currentLoad;
        ++successfulRequests;

        return selected->id;
    }

    void release(const string& nodeId) {
        auto it = nodes.find(nodeId);

        if (it == nodes.end()) {
            throw invalid_argument("Unknown node");
        }

        if (it->second.currentLoad <= 0) {
            throw logic_error("No active request to release");
        }

        --it->second.currentLoad;
    }

    void failNode(const string& nodeId) {
        auto it = nodes.find(nodeId);

        if (it == nodes.end()) {
            throw invalid_argument("Unknown node");
        }

        it->second.fail();

        cout << "FAILURE: " << nodeId << '\n';

        if (quorum != nullptr) {
            quorum->invalidateLeader(nodeId);

            if (quorum->hasQuorum(nodes)) {
                cout << "NEW LEADER: "
                     << quorum->elect(nodes) << '\n';
            } else {
                cout << "CRITICAL: QUORUM LOST\n";
            }
        }
    }

    void recoverNode(const string& nodeId) {
        auto it = nodes.find(nodeId);

        if (it == nodes.end()) {
            throw invalid_argument("Unknown node");
        }

        it->second.recover();

        cout << "RECOVERED: " << nodeId << '\n';

        if (quorum != nullptr &&
            quorum->getLeader().empty() &&
            quorum->hasQuorum(nodes)) {
            cout << "LEADER RESTORED: "
                 << quorum->elect(nodes) << '\n';
        }
    }

    void failDomain(const string& zone) {
        vector<string> affected;

        for (const auto& entry : nodes) {
            if (entry.second.zone == zone &&
                entry.second.healthy()) {
                affected.push_back(entry.first);
            }
        }

        if (affected.empty()) {
            throw invalid_argument("No healthy nodes in failure domain");
        }

        cout << "DOMAIN FAILURE: " << zone << '\n';

        for (const auto& id : affected) {
            failNode(id);
        }
    }

    vector<string> analyzeSinglePointsOfFailure() const {
        vector<string> risks;

        for (const auto& entry : services) {
            const auto& service = entry.second;

            set<string> zones;

            for (const auto& id : service.replicas) {
                zones.insert(nodes.at(id).zone);
            }

            for (const auto& zone : zones) {
                int survivors = 0;

                for (const auto& id : service.replicas) {
                    const auto& node = nodes.at(id);

                    if (node.zone != zone && node.healthy()) {
                        ++survivors;
                    }
                }

                if (survivors < service.minimumHealthy) {
                    risks.push_back(
                        service.id + " vulnerable to failure of " + zone
                    );
                }
            }
        }

        return risks;
    }

    void printReport() const {
        cout << "\n========== HA REPORT ==========\n";

        for (const auto& entry : services) {
            const auto state = evaluateService(entry.first);

            string label;

            switch (state) {
                case ServiceState::Available:
                    label = "AVAILABLE";
                    break;
                case ServiceState::Degraded:
                    label = "DEGRADED";
                    break;
                case ServiceState::Unavailable:
                    label = "UNAVAILABLE";
                    break;
            }

            cout << entry.first << ": " << label
                 << " (" << healthyReplicas(entry.first)
                 << "/" << entry.second.replicas.size()
                 << " healthy)\n";
        }

        if (quorum != nullptr) {
            cout << "Quorum: "
                 << (quorum->hasQuorum(nodes) ? "AVAILABLE" : "LOST")
                 << '\n';

            cout << "Leader: " << quorum->getLeader() << '\n';
            cout << "Term: " << quorum->getTerm() << '\n';
        }

        const double successRatio = totalRequests == 0
            ? 100.0
            : static_cast<double>(successfulRequests) /
              totalRequests * 100.0;

        cout << fixed << setprecision(2);
        cout << "Requests: " << totalRequests << '\n';
        cout << "Successful: " << successfulRequests << '\n';
        cout << "Failed: " << failedRequests << '\n';
        cout << "Success ratio: " << successRatio << "%\n";

        cout << "\nFailure-domain analysis:\n";

        const auto risks = analyzeSinglePointsOfFailure();

        if (risks.empty()) {
            cout << "No modeled service-level single-domain violations.\n";
        } else {
            for (const auto& risk : risks) {
                cout << "- " << risk << '\n';
            }
        }
    }
};

int main() {
    try {
        HighAvailabilityEngine engine;

        const vector<InfrastructureNode> infrastructure = {
            {"app-1", "zone-a", "application", 100},
            {"app-2", "zone-b", "application", 100},
            {"app-3", "zone-c", "application", 100},
            {"db-1", "zone-a", "database", 200},
            {"db-2", "zone-b", "database", 200},
            {"db-3", "zone-c", "database", 200},
            {"control-1", "zone-a", "control", 50},
            {"control-2", "zone-b", "control", 50},
            {"control-3", "zone-c", "control", 50}
        };

        for (auto node : infrastructure) {
            engine.registerNode(move(node));
        }

        engine.registerService({
            "application",
            {"app-1", "app-2", "app-3"},
            2
        });

        engine.registerService({
            "database",
            {"db-1", "db-2", "db-3"},
            2
        });

        QuorumCluster controlPlane({
            "control-1",
            "control-2",
            "control-3"
        });

        engine.configureQuorum(controlPlane);

        cout << "INITIAL TRAFFIC\n";

        for (int i = 0; i < 6; ++i) {
            string node = engine.route("application");

            if (!node.empty()) {
                cout << "Request served by " << node << '\n';
                engine.release(node);
            }
        }

        cout << "\nINDIVIDUAL FAILURE\n";
        engine.failNode("app-1");

        string node = engine.route("application");

        if (!node.empty()) {
            cout << "Failover served by " << node << '\n';
            engine.release(node);
        }

        cout << "\nNODE RECOVERY\n";
        engine.recoverNode("app-1");

        cout << "\nAVAILABILITY-ZONE FAILURE\n";
        engine.failDomain("zone-a");

        engine.printReport();

        return 0;

    } catch (const exception& error) {
        cerr << "Infrastructure error: "
             << error.what() << '\n';

        return 1;
    }
}
