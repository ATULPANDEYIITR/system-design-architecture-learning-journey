#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

/*
 * Repository-independent case study: a regional infrastructure monitoring
 * platform whose records are replicated between operational data centers.
 *
 * The model demonstrates consistency-aware writes, reads, causal dependencies,
 * deterministic conflict resolution, replica partitions, and recovery.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic consistency_models.cpp -o consistency_models
 */

using VectorClock = std::map<std::string, std::uint64_t>;

enum class ConsistencyModel {
    Strong,
    Eventual,
    Causal
};

struct Operation {
    std::string id;
    std::string key;
    std::string value;
    std::string origin;
    VectorClock version;
    VectorClock dependencies;
    std::uint64_t logical_time;
    bool tombstone = false;
};

struct Replica {
    std::string id;
    bool available = true;
    std::map<std::string, Operation> records;
    VectorClock context;
    std::set<std::string> applied_ids;
};

class ConsistencyError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class AvailabilityError : public ConsistencyError {
public:
    using ConsistencyError::ConsistencyError;
};

class CausalDependencyError : public ConsistencyError {
public:
    using ConsistencyError::ConsistencyError;
};

class OperationConflictError : public ConsistencyError {
public:
    using ConsistencyError::ConsistencyError;
};

static std::uint64_t clock_value(
    const VectorClock& clock,
    const std::string& replica
) {
    const auto it = clock.find(replica);
    return it == clock.end() ? 0 : it->second;
}

static VectorClock merge_clocks(
    const VectorClock& left,
    const VectorClock& right
) {
    VectorClock merged = left;
    for (const auto& [replica, count] : right) {
        merged[replica] = std::max(merged[replica], count);
    }
    return merged;
}

static bool dominates_or_equals(
    const VectorClock& left,
    const VectorClock& right
) {
    for (const auto& [replica, count] : right) {
        if (clock_value(left, replica) < count) {
            return false;
        }
    }
    return true;
}

static bool strictly_dominates(
    const VectorClock& left,
    const VectorClock& right
) {
    return dominates_or_equals(left, right) && left != right;
}

static bool concurrent(
    const VectorClock& left,
    const VectorClock& right
) {
    return !dominates_or_equals(left, right)
        && !dominates_or_equals(right, left);
}

static VectorClock increment_clock(
    VectorClock clock,
    const std::string& replica
) {
    ++clock[replica];
    return clock;
}

class GovernanceDataCenter {
private:
    ConsistencyModel model_;
    std::string leader_;
    std::size_t required_acks_;
    std::map<std::string, Replica> replicas_;
    std::map<std::string, Operation> operation_registry_;
    std::map<std::string, std::uint64_t> sequence_;
    std::vector<Operation> message_queue_;
    std::uint64_t logical_time_ = 0;

    Operation create_operation(
        const std::string& origin,
        const std::string& key,
        const std::string& value,
        const std::string& id,
        const VectorClock& dependencies,
        bool tombstone
    ) {
        if (key.empty() || id.empty()) {
            throw std::invalid_argument("Operation ID and key must be nonempty.");
        }

        auto previous = operation_registry_.find(id);
        if (previous != operation_registry_.end()) {
            const Operation& existing = previous->second;
            if (
                existing.origin == origin &&
                existing.key == key &&
                existing.value == value &&
                existing.dependencies == dependencies &&
                existing.tombstone == tombstone
            ) {
                return existing;
            }
            throw OperationConflictError("Operation identifier was reused.");
        }

        Replica& replica = replicas_.at(origin);
        VectorClock base = merge_clocks(replica.context, dependencies);
        VectorClock version = increment_clock(base, origin);

        Operation operation{
            id,
            key,
            value,
            origin,
            version,
            dependencies,
            ++logical_time_,
            tombstone
        };

        ++sequence_[origin];
        operation_registry_.emplace(id, operation);
        return operation;
    }

    static bool tie_break(const Operation& left, const Operation& right) {
        return std::tie(left.logical_time, left.origin, left.id)
             < std::tie(right.logical_time, right.origin, right.id);
    }

    Operation resolve(
        const std::optional<Operation>& current,
        const Operation& incoming
    ) const {
        if (!current) return incoming;

        if (strictly_dominates(incoming.version, current->version)) {
            return incoming;
        }
        if (strictly_dominates(current->version, incoming.version)) {
            return *current;
        }
        if (concurrent(incoming.version, current->version)) {
            // Deterministic last-writer-wins behavior is easy to implement,
            // but a production system may need to preserve concurrent values.
            return tie_break(*current, incoming) ? incoming : *current;
        }
        return tie_break(*current, incoming) ? incoming : *current;
    }

    bool apply(Replica& replica, const Operation& operation) {
        if (replica.applied_ids.count(operation.id)) return false;

        if (
            model_ == ConsistencyModel::Causal &&
            !dominates_or_equals(replica.context, operation.dependencies)
        ) {
            throw CausalDependencyError(
                "Replica " + replica.id + " lacks a causal prerequisite."
            );
        }

        std::optional<Operation> current;
        const auto found = replica.records.find(operation.key);
        if (found != replica.records.end()) current = found->second;

        replica.records[operation.key] = resolve(current, operation);
        replica.applied_ids.insert(operation.id);
        replica.context = merge_clocks(replica.context, operation.version);
        return true;
    }

public:
    GovernanceDataCenter(
        ConsistencyModel model,
        std::vector<std::string> replica_ids,
        std::string leader,
        std::size_t required_acks
    )
        : model_(model),
          leader_(std::move(leader)),
          required_acks_(required_acks) {
        if (replica_ids.empty()) {
            throw std::invalid_argument("At least one replica is required.");
        }

        for (const auto& id : replica_ids) {
            if (id.empty() || replicas_.count(id)) {
                throw std::invalid_argument("Replica IDs must be unique.");
            }
            replicas_.emplace(id, Replica{id});
        }

        if (!replicas_.count(leader_)) {
            throw std::invalid_argument("Leader is not configured.");
        }
        if (required_acks_ == 0 || required_acks_ > replicas_.size()) {
            throw std::invalid_argument("Invalid acknowledgment requirement.");
        }
    }

    void set_available(const std::string& id, bool available) {
        replicas_.at(id).available = available;
    }

    Operation write(
        const std::string& origin,
        const std::string& key,
        const std::string& value,
        const std::string& id,
        VectorClock dependencies = {},
        bool tombstone = false
    ) {
        Replica& local = replicas_.at(origin);
        if (!local.available) {
            throw AvailabilityError("The requested origin is unavailable.");
        }

        if (model_ == ConsistencyModel::Strong) {
            Replica& leader = replicas_.at(leader_);
            if (!leader.available) {
                throw AvailabilityError("The authoritative leader is unavailable.");
            }

            const auto active_count = std::count_if(
                replicas_.begin(), replicas_.end(),
                [](const auto& item) { return item.second.available; }
            );

            if (static_cast<std::size_t>(active_count) < required_acks_) {
                throw AvailabilityError("Required acknowledgments are unavailable.");
            }

            Operation operation = create_operation(
                leader_, key, value, id, dependencies, tombstone
            );

            // A real linearizable implementation requires consensus and durable
            // commit rules. This deterministic case study models the successful
            // path by applying to all currently available replicas.
            for (auto& [replica_id, replica] : replicas_) {
                (void)replica_id;
                if (replica.available) apply(replica, operation);
            }
            return operation;
        }

        Operation operation = create_operation(
            origin, key, value, id, dependencies, tombstone
        );
        apply(local, operation);
        message_queue_.push_back(operation);
        return operation;
    }

    std::optional<std::string> read(
        const std::string& replica_id,
        const std::string& key,
        const VectorClock& minimum_context = {}
    ) const {
        const Replica& requested = replicas_.at(replica_id);
        if (!requested.available) {
            throw AvailabilityError("Requested replica is unavailable.");
        }

        const Replica* source = &requested;
        if (model_ == ConsistencyModel::Strong) {
            const Replica& leader = replicas_.at(leader_);
            if (!leader.available) {
                throw AvailabilityError("The authoritative leader is unavailable.");
            }
            source = &leader;
        } else if (
            model_ == ConsistencyModel::Causal &&
            !dominates_or_equals(requested.context, minimum_context)
        ) {
            throw CausalDependencyError("Requested causal context is not available.");
        }

        const auto found = source->records.find(key);
        if (found == source->records.end() || found->second.tombstone) {
            return std::nullopt;
        }
        return found->second.value;
    }

    bool deliver(std::size_t index = 0) {
        if (index >= message_queue_.size()) return false;

        Operation operation = message_queue_.at(index);
        message_queue_.erase(message_queue_.begin() + static_cast<long>(index));

        bool deferred = false;
        for (auto& [id, replica] : replicas_) {
            (void)id;
            if (!replica.available || replica.applied_ids.count(operation.id)) {
                continue;
            }
            try {
                apply(replica, operation);
            } catch (const CausalDependencyError&) {
                deferred = true;
            }
        }

        if (deferred) message_queue_.push_back(operation);
        return true;
    }

    std::size_t flush(std::size_t limit = 1000) {
        std::size_t steps = 0;

        while (!message_queue_.empty() && steps < limit) {
            const std::size_t before = message_queue_.size();
            deliver(0);
            ++steps;

            if (message_queue_.size() == before) {
                bool progress = false;

                for (std::size_t i = 1; i < message_queue_.size(); ++i) {
                    const Operation& operation = message_queue_[i];
                    bool prerequisite_available = false;

                    for (const auto& [id, replica] : replicas_) {
                        (void)id;
                        if (
                            replica.available &&
                            dominates_or_equals(
                                replica.context, operation.dependencies
                            )
                        ) {
                            prerequisite_available = true;
                            break;
                        }
                    }

                    if (prerequisite_available) {
                        deliver(i);
                        progress = true;
                        ++steps;
                        break;
                    }
                }

                if (!progress) break;
            }
        }

        return steps;
    }

    void anti_entropy() {
        std::vector<Operation> operations;
        for (const auto& [id, operation] : operation_registry_) {
            (void)id;
            operations.push_back(operation);
        }

        std::sort(
            operations.begin(), operations.end(),
            [](const Operation& left, const Operation& right) {
                return std::tie(left.logical_time, left.id)
                     < std::tie(right.logical_time, right.id);
            }
        );

        bool changed = true;
        std::size_t passes = 0;
        while (changed && passes++ <= operations.size() + 1) {
            changed = false;

            for (const auto& operation : operations) {
                for (auto& [id, replica] : replicas_) {
                    (void)id;
                    if (!replica.available) continue;
                    if (replica.applied_ids.count(operation.id)) continue;

                    try {
                        changed = apply(replica, operation) || changed;
                    } catch (const CausalDependencyError&) {
                        // A later pass may succeed after the prerequisite arrives.
                    }
                }
            }
        }

        message_queue_.erase(
            std::remove_if(
                message_queue_.begin(), message_queue_.end(),
                [this](const Operation& operation) {
                    for (const auto& [id, replica] : replicas_) {
                        (void)id;
                        if (
                            replica.available &&
                            !replica.applied_ids.count(operation.id)
                        ) return false;
                    }
                    return true;
                }
            ),
            message_queue_.end()
        );
    }

    void print_values(const std::string& key) const {
        std::cout << key << " across replicas:\n";
        for (const auto& [id, replica] : replicas_) {
            const auto found = replica.records.find(key);
            std::cout << "  " << id << ": ";

            if (found == replica.records.end() || found->second.tombstone) {
                std::cout << "<absent>";
            } else {
                std::cout << found->second.value;
            }
            std::cout << '\n';
        }
    }
};

static void strong_reading_scenario() {
    std::cout << "\n=== Strong consistency: safety inventory ===\n";

    GovernanceDataCenter store(
        ConsistencyModel::Strong, {"A", "B", "C"}, "A", 2
    );

    store.write("A", "sensor:bridge-22", "operational", "strong-1");
    assert(store.read("B", "sensor:bridge-22") == "operational");

    store.set_available("A", false);
    try {
        (void)store.read("B", "sensor:bridge-22");
        assert(false && "An unavailable leader must reject the read.");
    } catch (const AvailabilityError& error) {
        std::cout << "Read rejected safely: " << error.what() << '\n';
    }
}

static void eventual_reading_scenario() {
    std::cout << "\n=== Eventual consistency: telemetry dashboard ===\n";

    GovernanceDataCenter store(
        ConsistencyModel::Eventual, {"A", "B", "C"}, "A", 1
    );

    store.write("A", "temperature:plant-4", "37.2", "eventual-1");
    assert(store.read("A", "temperature:plant-4") == "37.2");
    assert(!store.read("B", "temperature:plant-4").has_value());

    store.flush();
    assert(store.read("B", "temperature:plant-4") == "37.2");
    store.print_values("temperature:plant-4");

    // A partition permits concurrent updates. The deterministic winner
    // converges, but last-writer-wins does not preserve both values.
    store.write("A", "dashboard:display-mode", "compact", "eventual-2");
    store.write("B", "dashboard:display-mode", "detailed", "eventual-3");
    store.flush();
    store.anti_entropy();
    store.print_values("dashboard:display-mode");
}

static void causal_reading_scenario() {
    std::cout << "\n=== Causal consistency: incident management ===\n";

    GovernanceDataCenter store(
        ConsistencyModel::Causal, {"A", "B", "C"}, "A", 1
    );

    const Operation created = store.write(
        "A", "incident:INC-804", "opened", "causal-1"
    );

    const Operation assigned = store.write(
        "A",
        "incident:INC-804:assignment",
        "network-operations",
        "causal-2",
        created.version
    );

    // Queue order is deliberately changed to deliver the dependent event first.
    store.deliver(1);
    assert(!store.read("B", "incident:INC-804:assignment").has_value());

    store.flush();
    assert(
        store.read(
            "B", "incident:INC-804:assignment", assigned.version
        ) == "network-operations"
    );

    std::cout << "The assignment becomes visible after its causal prerequisite.\n";
}

int main() {
    try {
        strong_reading_scenario();
        eventual_reading_scenario();
        causal_reading_scenario();

        std::cout << "\nAll C++ consistency assertions passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Consistency simulation failed: " << error.what() << '\n';
        return 1;
    }
}
