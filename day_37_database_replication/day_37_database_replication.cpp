#include <algorithm>
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
#include <vector>

/*
 * Database Replication Governance and Merge-Eligibility Case Study
 *
 * Scenario:
 * A financial platform runs a primary database and several replicas.
 * The primary accepts writes. Replicas receive ordered log records and
 * replay them. The governance engine decides whether a write can be
 * acknowledged under asynchronous, synchronous, or quorum-based rules.
 *
 * The program is deliberately implemented as a C++ systems-style case study:
 * strongly typed domain objects, ordered log processing, explicit state,
 * failure handling, and consistency validation.
 *
 * This is a replication model, not a replacement for a database's WAL engine.
 */

enum class ReplicationMode {
    Asynchronous,
    Synchronous
};

enum class NodeState {
    Up,
    Down
};

enum class Operation {
    Set,
    Delete
};

struct ChangeRecord {
    std::uint64_t lsn{};
    std::uint64_t transactionId{};
    Operation operation{};
    std::string key;
    std::string value;
    std::uint64_t generation{};
};

class ReplicationException : public std::runtime_error {
public:
    explicit ReplicationException(const std::string& message)
        : std::runtime_error(message) {}
};

class Replica {
private:
    std::string name_;
    NodeState state_{NodeState::Up};
    std::map<std::string, std::string> data_;
    std::map<std::uint64_t, ChangeRecord> pending_;
    std::set<std::uint64_t> applied_;
    std::uint64_t receivedLsn_{0};
    std::uint64_t replayedLsn_{0};

public:
    explicit Replica(std::string name)
        : name_(std::move(name)) {}

    const std::string& name() const {
        return name_;
    }

    NodeState state() const {
        return state_;
    }

    void setState(NodeState state) {
        state_ = state;
    }

    std::uint64_t receivedLsn() const {
        return receivedLsn_;
    }

    std::uint64_t replayedLsn() const {
        return replayedLsn_;
    }

    std::uint64_t lag() const {
        return receivedLsn_ >= replayedLsn_
            ? receivedLsn_ - replayedLsn_
            : 0;
    }

    const std::map<std::string, std::string>& data() const {
        return data_;
    }

    void receive(const ChangeRecord& change) {
        if (state_ == NodeState::Down) {
            return;
        }

        if (applied_.contains(change.lsn)) {
            return;
        }

        pending_.insert_or_assign(change.lsn, change);
        receivedLsn_ = std::max(receivedLsn_, change.lsn);
    }

    bool replayNext() {
        if (state_ == NodeState::Down) {
            throw ReplicationException(
                name_ + " cannot replay while down"
            );
        }

        const std::uint64_t nextLsn = replayedLsn_ + 1;
        auto iterator = pending_.find(nextLsn);

        if (iterator == pending_.end()) {
            return false;
        }

        const ChangeRecord& change = iterator->second;

        if (change.operation == Operation::Set) {
            data_[change.key] = change.value;
        } else {
            data_.erase(change.key);
        }

        applied_.insert(change.lsn);
        replayedLsn_ = change.lsn;
        pending_.erase(iterator);

        return true;
    }

    std::size_t replayAll() {
        std::size_t appliedCount = 0;

        while (replayNext()) {
            ++appliedCount;
        }

        return appliedCount;
    }
};

class Primary {
private:
    std::string name_;
    NodeState state_{NodeState::Up};
    std::uint64_t nextLsn_{1};
    std::uint64_t nextTransactionId_{1};
    std::uint64_t generation_{1};
    std::map<std::string, std::string> data_;
    std::vector<ChangeRecord> wal_;

public:
    explicit Primary(std::string name)
        : name_(std::move(name)) {}

    const std::string& name() const {
        return name_;
    }

    NodeState state() const {
        return state_;
    }

    void setState(NodeState state) {
        state_ = state;
    }

    std::uint64_t generation() const {
        return generation_;
    }

    void setGeneration(std::uint64_t generation) {
        generation_ = generation;
    }

    const std::map<std::string, std::string>& data() const {
        return data_;
    }

    const std::vector<ChangeRecord>& wal() const {
        return wal_;
    }

    void restoreData(const std::map<std::string, std::string>& data) {
        data_ = data;
    }

    void restoreLsn(std::uint64_t lsn) {
        nextLsn_ = lsn + 1;
    }

    ChangeRecord write(
        Operation operation,
        const std::string& key,
        const std::string& value = ""
    ) {
        if (state_ == NodeState::Down) {
            throw ReplicationException("Primary is unavailable");
        }

        if (key.empty()) {
            throw std::invalid_argument("A database key cannot be empty");
        }

        if (operation == Operation::Set) {
            if (value.empty()) {
                throw std::invalid_argument(
                    "SET requires a non-empty value"
                );
            }
            data_[key] = value;
        } else {
            data_.erase(key);
        }

        ChangeRecord change{
            nextLsn_++,
            nextTransactionId_++,
            operation,
            key,
            value,
            generation_
        };

        wal_.push_back(change);
        return change;
    }

    void restoreWal(const std::vector<ChangeRecord>& wal) {
        wal_ = wal;
    }
};

class ReplicationCluster {
private:
    Primary primary_;
    ReplicationMode mode_;
    std::size_t requiredAcknowledgements_;
    std::map<std::string, Replica> replicas_;

    std::vector<Replica*> healthyReplicas() {
        std::vector<Replica*> result;

        for (auto& [name, replica] : replicas_) {
            if (replica.state() == NodeState::Up) {
                result.push_back(&replica);
            }
        }

        return result;
    }

    std::size_t acknowledged(
        std::uint64_t lsn
    ) const {
        std::size_t count = 0;

        for (const auto& [name, replica] : replicas_) {
            if (replica.state() == NodeState::Up &&
                replica.replayedLsn() >= lsn) {
                ++count;
            }
        }

        return count;
    }

public:
    ReplicationCluster(
        std::string primaryName,
        ReplicationMode mode,
        std::size_t requiredAcknowledgements
    )
        : primary_(std::move(primaryName)),
          mode_(mode),
          requiredAcknowledgements_(requiredAcknowledgements) {}

    Primary& primary() {
        return primary_;
    }

    const Primary& primary() const {
        return primary_;
    }

    Replica& addReplica(const std::string& name) {
        if (name == primary_.name()) {
            throw std::invalid_argument(
                "Replica name cannot equal primary name"
            );
        }

        auto [iterator, inserted] =
            replicas_.emplace(name, Replica(name));

        if (!inserted) {
            throw std::invalid_argument("Duplicate replica: " + name);
        }

        return iterator->second;
    }

    Replica& replica(const std::string& name) {
        auto iterator = replicas_.find(name);

        if (iterator == replicas_.end()) {
            throw std::out_of_range("Unknown replica: " + name);
        }

        return iterator->second;
    }

    ChangeRecord commit(
        Operation operation,
        const std::string& key,
        const std::string& value = "",
        bool replayImmediately = true
    ) {
        ChangeRecord change = primary_.write(operation, key, value);

        /*
         * Every healthy replica receives the same ordered record. The primary
         * does not send a later LSN while an earlier record is missing from a
         * replica's replay stream.
         */
        for (Replica* replica : healthyReplicas()) {
            replica->receive(change);
        }

        if (replayImmediately) {
            for (Replica* replica : healthyReplicas()) {
                replica->replayAll();
            }
        }

        if (mode_ == ReplicationMode::Synchronous) {
            const std::size_t count = acknowledged(change.lsn);

            if (count < requiredAcknowledgements_) {
                std::ostringstream message;
                message
                    << "Synchronous acknowledgement failed for LSN "
                    << change.lsn
                    << ": required=" << requiredAcknowledgements_
                    << ", acknowledged=" << count;

                throw ReplicationException(message.str());
            }
        }

        return change;
    }

    bool isConsistent(const Replica& replica) const {
        return primary_.data() == replica.data();
    }

    void showStatus() const {
        std::cout
            << std::left
            << std::setw(22) << "Replica"
            << std::setw(12) << "State"
            << std::setw(12) << "Received"
            << std::setw(12) << "Replayed"
            << std::setw(10) << "Lag"
            << '\n';

        for (const auto& [name, replica] : replicas_) {
            std::cout
                << std::setw(22) << name
                << std::setw(12)
                << (replica.state() == NodeState::Up ? "up" : "down")
                << std::setw(12) << replica.receivedLsn()
                << std::setw(12) << replica.replayedLsn()
                << std::setw(10) << replica.lag()
                << '\n';
        }
    }

    void promote(const std::string& replicaName) {
        Replica& candidate = replica(replicaName);

        /*
         * Fencing the old primary before promotion is critical. Without it,
         * both nodes could accept writes and create a split-brain system.
         */
        if (primary_.state() != NodeState::Down) {
            throw ReplicationException(
                "Cannot promote while old primary remains writable"
            );
        }

        if (candidate.state() != NodeState::Up ||
            candidate.replayedLsn() == 0) {
            throw ReplicationException(
                "Promotion requires a healthy replica with replayed state"
            );
        }

        const std::uint64_t newGeneration =
            primary_.generation() + 1;

        const std::string oldPrimaryName = primary_.name();

        Primary replacement(candidate.name());
        replacement.setGeneration(newGeneration);
        replacement.restoreData(candidate.data());
        replacement.restoreLsn(candidate.replayedLsn());

        std::vector<ChangeRecord> recoveredWal;

        for (const auto& change : primary_.wal()) {
            if (change.lsn <= candidate.replayedLsn()) {
                recoveredWal.push_back(change);
            }
        }

        replacement.restoreWal(recoveredWal);
        primary_ = std::move(replacement);

        replicas_.erase(replicaName);

        std::cout
            << "Promoted " << replicaName
            << " after fencing " << oldPrimaryName
            << "; generation=" << newGeneration
            << '\n';
    }
};

void printHeading(const std::string& title) {
    std::cout
        << "\n"
        << std::string(72, '=')
        << "\n"
        << title
        << "\n"
        << std::string(72, '=')
        << "\n";
}

void asynchronousCaseStudy() {
    printHeading("Asynchronous primary-replica case");

    ReplicationCluster cluster(
        "orders-primary",
        ReplicationMode::Asynchronous,
        0
    );

    cluster.addReplica("orders-replica-a");
    cluster.addReplica("orders-replica-b");

    cluster.commit(
        Operation::Set,
        "order:1001",
        "PAID",
        false
    );

    cluster.commit(
        Operation::Set,
        "order:1002",
        "SHIPPED",
        false
    );

    std::cout << "Both replicas have received no replayed state yet:\n";
    cluster.showStatus();

    cluster.replica("orders-replica-a").replayAll();

    std::cout << "\nReplica-a catches up:\n";
    cluster.showStatus();

    cluster.replica("orders-replica-b").replayAll();

    std::cout << "\nReplica-b catches up:\n";
    cluster.showStatus();

    if (!cluster.isConsistent(cluster.replica("orders-replica-a")) ||
        !cluster.isConsistent(cluster.replica("orders-replica-b"))) {
        throw ReplicationException(
            "Expected replicas to become consistent"
        );
    }
}

void synchronousCaseStudy() {
    printHeading("Synchronous replication case");

    ReplicationCluster cluster(
        "payments-primary",
        ReplicationMode::Synchronous,
        1
    );

    cluster.addReplica("payments-replica-a");

    const ChangeRecord change = cluster.commit(
        Operation::Set,
        "payment:1",
        "SETTLED"
    );

    std::cout
        << "Synchronous commit acknowledged at LSN "
        << change.lsn << '\n';

    cluster.replica("payments-replica-a").setState(NodeState::Down);

    try {
        cluster.commit(
            Operation::Set,
            "payment:2",
            "SETTLED"
        );
    } catch (const std::exception& error) {
        std::cout
            << "Expected synchronous failure: "
            << error.what()
            << '\n';
    }
}

void lagAndRecoveryCaseStudy() {
    printHeading("Lag, outage, and catch-up");

    ReplicationCluster cluster(
        "analytics-primary",
        ReplicationMode::Asynchronous,
        0
    );

    cluster.addReplica("analytics-replica");

    cluster.replica("analytics-replica").setState(NodeState::Down);

    for (int i = 1; i <= 5; ++i) {
        cluster.commit(
            Operation::Set,
            "metric:" + std::to_string(i),
            std::to_string(i * 100),
            false
        );
    }

    cluster.showStatus();

    Replica& replica = cluster.replica("analytics-replica");
    replica.setState(NodeState::Up);

    /*
     * The replica resumes from its last replay position. In a real database,
     * the transport layer would request only the missing WAL/binlog range.
     */
    for (const auto& change : cluster.primary().wal()) {
        replica.receive(change);
    }

    replica.replayAll();

    std::cout << "\nAfter recovery:\n";
    cluster.showStatus();

    if (!cluster.isConsistent(replica)) {
        throw ReplicationException(
            "Replica failed consistency check after recovery"
        );
    }
}

void failoverCaseStudy() {
    printHeading("Failover and split-brain prevention");

    ReplicationCluster cluster(
        "ledger-primary",
        ReplicationMode::Asynchronous,
        0
    );

    cluster.addReplica("ledger-replica-a");

    cluster.commit(
        Operation::Set,
        "ledger:1",
        "POSTED"
    );

    cluster.commit(
        Operation::Set,
        "ledger:2",
        "POSTED"
    );

    Replica& candidate = cluster.replica("ledger-replica-a");

    cluster.primary().setState(NodeState::Down);

    cluster.promote("ledger-replica-a");

    /*
     * The new generation is a fencing mechanism at the logical model level.
     * Production systems combine this with leases, consensus, or an external
     * fencing mechanism so an isolated old primary cannot continue writing.
     */
    const ChangeRecord change = cluster.commit(
        Operation::Set,
        "ledger:3",
        "POSTED"
    );

    std::cout
        << "Post-failover write uses LSN "
        << change.lsn
        << " and generation "
        << change.generation
        << '\n';

    (void)candidate;
}

void mainCaseStudy() {
    asynchronousCaseStudy();
    synchronousCaseStudy();
    lagAndRecoveryCaseStudy();
    failoverCaseStudy();

    printHeading("Operational interpretation");

    std::cout
        << "Asynchronous replication minimizes primary write latency but can "
           "expose recent committed data to loss if the primary fails before "
           "a replica receives and replays the corresponding log records.\n"
        << "Synchronous replication waits for configured replica "
           "acknowledgements and therefore couples write availability to "
           "replica health and network latency.\n"
        << "Replication lag must be monitored independently from node "
           "availability because an online replica can still be materially "
           "behind the primary.\n"
        << "Failover requires fencing or otherwise preventing the old primary "
           "from accepting writes; promotion without fencing creates the "
           "conditions for split brain.\n";
}

int main() {
    try {
        mainCaseStudy();
        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal replication simulation error: "
            << error.what()
            << '\n';
        return 1;
    }
}
