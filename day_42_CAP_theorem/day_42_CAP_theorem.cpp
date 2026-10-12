#include <algorithm>
#include <chrono>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

enum class SystemMode {
    CP,
    AP
};

struct VersionedValue {
    long long version{};
    std::string value;
};

struct Replica {
    std::string id;
    std::string region;
    bool online{true};
    std::map<std::string, VersionedValue> records;
    long long logicalClock{0};

    void write(const std::string& key, const std::string& value) {
        ++logicalClock;
        records[key] = {logicalClock, value};
    }

    std::optional<VersionedValue> read(const std::string& key) const {
        auto it = records.find(key);
        if (it == records.end()) {
            return std::nullopt;
        }
        return it->second;
    }
};

struct WriteDecision {
    bool committed;
    std::vector<std::string> acknowledgements;
    std::string reason;
};

class RepositoryGovernanceEngine {
private:
    std::map<std::string, Replica> replicas;
    std::vector<std::set<std::string>> partitions;
    SystemMode mode;

    bool canCommunicate(
        const std::string& first,
        const std::string& second
    ) const {
        return std::any_of(
            partitions.begin(),
            partitions.end(),
            [&](const std::set<std::string>& group) {
                return group.contains(first) && group.contains(second);
            }
        );
    }

    std::vector<Replica*> reachable(const std::string& coordinator) {
        std::vector<Replica*> result;

        for (auto& [id, replica] : replicas) {
            if (replica.online && canCommunicate(coordinator, id)) {
                result.push_back(&replica);
            }
        }

        return result;
    }

public:
    explicit RepositoryGovernanceEngine(SystemMode selectedMode)
        : mode(selectedMode) {
        replicas.emplace(
            "reviewer-a",
            Replica{"reviewer-a", "Delhi"}
        );
        replicas.emplace(
            "reviewer-b",
            Replica{"reviewer-b", "Mumbai"}
        );
        replicas.emplace(
            "reviewer-c",
            Replica{"reviewer-c", "Bengaluru"}
        );

        healPartition();
    }

    void healPartition() {
        std::set<std::string> all;

        for (const auto& [id, _] : replicas) {
            all.insert(id);
        }

        partitions = {all};
    }

    void partition(
        const std::set<std::string>& first,
        const std::set<std::string>& second
    ) {
        std::set<std::string> all;

        for (const auto& [id, _] : replicas) {
            all.insert(id);
        }

        std::set<std::string> supplied = first;
        supplied.insert(second.begin(), second.end());

        if (supplied != all) {
            throw std::invalid_argument(
                "Partition groups must cover the entire cluster."
            );
        }

        partitions = {first, second};
    }

    WriteDecision updateGovernanceState(
        const std::string& coordinator,
        const std::string& policyKey,
        const std::string& policyValue
    ) {
        if (!replicas.contains(coordinator)) {
            return {false, {}, "Unknown coordinator."};
        }

        auto nodes = reachable(coordinator);
        const std::size_t quorum = replicas.size() / 2 + 1;

        if (mode == SystemMode::CP && nodes.size() < quorum) {
            return {
                false,
                {},
                "Governance update rejected because a majority is unreachable."
            };
        }

        std::vector<std::string> acknowledged;

        for (Replica* node : nodes) {
            node->write(policyKey, policyValue);
            acknowledged.push_back(node->id);
        }

        if (mode == SystemMode::CP) {
            return {
                true,
                acknowledged,
                "Policy state committed with majority agreement."
            };
        }

        return {
            true,
            acknowledged,
            "Policy state accepted locally; reconciliation may be required."
        };
    }

    std::optional<VersionedValue> readGovernanceState(
        const std::string& coordinator,
        const std::string& policyKey
    ) {
        auto nodes = reachable(coordinator);

        if (nodes.empty()) {
            return std::nullopt;
        }

        std::optional<VersionedValue> newest;

        for (const Replica* node : nodes) {
            auto record = node->read(policyKey);

            if (!record.has_value()) {
                continue;
            }

            if (!newest.has_value() ||
                record->version > newest->version) {
                newest = record;
            }
        }

        return newest;
    }

    std::optional<std::string> reconcile(
        const std::string& policyKey
    ) {
        std::optional<VersionedValue> winner;

        for (const auto& [_, replica] : replicas) {
            auto record = replica.read(policyKey);

            if (!record.has_value()) {
                continue;
            }

            if (!winner.has_value() ||
                record->version > winner->version) {
                winner = record;
            }
        }

        if (!winner.has_value()) {
            return std::nullopt;
        }

        for (auto& [_, replica] : replicas) {
            replica.records[policyKey] = *winner;
        }

        return winner->value;
    }

    void printState(const std::string& policyKey) const {
        for (const auto& [id, replica] : replicas) {
            std::cout << id
                      << " [" << replica.region << "] ";

            auto record = replica.read(policyKey);

            if (!record.has_value()) {
                std::cout << "NO VALUE\n";
                continue;
            }

            std::cout
                << "version=" << record->version
                << ", value=" << record->value
                << '\n';
        }
    }
};

void demonstrateCPGovernance() {
    std::cout << "\n=== CP GOVERNANCE ENGINE ===\n";

    RepositoryGovernanceEngine engine(SystemMode::CP);

    auto initial = engine.updateGovernanceState(
        "reviewer-a",
        "payments-api:main:approval-policy",
        "required-approvals=2"
    );

    std::cout << initial.reason << '\n';

    engine.partition(
        {"reviewer-a"},
        {"reviewer-b", "reviewer-c"}
    );

    auto rejected = engine.updateGovernanceState(
        "reviewer-a",
        "payments-api:main:approval-policy",
        "required-approvals=3"
    );

    std::cout << rejected.reason << '\n';

    /*
     * The isolated controller does not invent a new authoritative policy.
     * This is the important CP trade-off: correctness is preserved by
     * refusing an operation whose required quorum cannot be reached.
     */
}

void demonstrateAPGovernance() {
    std::cout << "\n=== AP GOVERNANCE ENGINE ===\n";

    RepositoryGovernanceEngine engine(SystemMode::AP);

    engine.updateGovernanceState(
        "reviewer-a",
        "inventory:main:merge-policy",
        "required-checks=ci,security"
    );

    engine.partition(
        {"reviewer-a"},
        {"reviewer-b", "reviewer-c"}
    );

    auto sideA = engine.updateGovernanceState(
        "reviewer-a",
        "inventory:main:merge-policy",
        "required-checks=ci"
    );

    auto sideB = engine.updateGovernanceState(
        "reviewer-b",
        "inventory:main:merge-policy",
        "required-checks=ci,security,license"
    );

    std::cout << "Partition A: " << sideA.reason << '\n';
    std::cout << "Partition B: " << sideB.reason << '\n';

    std::cout << "\nState before reconciliation:\n";
    engine.printState("inventory:main:merge-policy");

    engine.healPartition();

    auto resolved = engine.reconcile(
        "inventory:main:merge-policy"
    );

    std::cout << "\nResolved policy: "
              << (resolved.has_value() ? *resolved : "NONE")
              << '\n';

    std::cout << "\nState after reconciliation:\n";
    engine.printState("inventory:main:merge-policy");
}

void discussSystemBoundary() {
    std::cout << "\n=== SYSTEM BOUNDARY ===\n";

    std::cout
        << "The CAP trade-off applies to distributed data operations "
        << "when a network partition prevents replicas from communicating.\n";

    std::cout
        << "It does not mean that a system can never have consistency, "
        << "availability, and partition tolerance under normal conditions.\n";

    std::cout
        << "The important design question is what the system does when "
        << "communication between replicas fails.\n";
}

int main() {
    const auto start = std::chrono::steady_clock::now();

    try {
        discussSystemBoundary();
        demonstrateCPGovernance();
        demonstrateAPGovernance();

        const auto end = std::chrono::steady_clock::now();
        const auto elapsed =
            std::chrono::duration_cast<std::chrono::microseconds>(
                end - start
            ).count();

        std::cout << "\nCase study completed in "
                  << elapsed
                  << " microseconds.\n";
    }
    catch (const std::exception& error) {
        std::cerr << "Fatal error: "
                  << error.what()
                  << '\n';
        return 1;
    }

    return 0;
}
