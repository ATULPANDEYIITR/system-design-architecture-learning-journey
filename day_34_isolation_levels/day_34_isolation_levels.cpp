#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

enum class IsolationLevel {
    ReadUncommitted,
    ReadCommitted,
    RepeatableRead,
    Serializable
};

std::string toString(IsolationLevel level) {
    switch (level) {
        case IsolationLevel::ReadUncommitted:
            return "READ UNCOMMITTED";
        case IsolationLevel::ReadCommitted:
            return "READ COMMITTED";
        case IsolationLevel::RepeatableRead:
            return "REPEATABLE READ";
        case IsolationLevel::Serializable:
            return "SERIALIZABLE";
    }
    return "UNKNOWN";
}

struct Account {
    int id;
    std::string owner;
    long long balance;
};

struct Version {
    long long commitVersion;
    Account account;
};

struct Transaction {
    int id;
    IsolationLevel isolation;
    long long snapshotVersion;
    bool active = true;

    // Writes are private until commit. This models the separation between
    // transaction-local state and durable committed state.
    std::map<int, Account> writes;

    // REPEATABLE READ remembers the first visible version of a row.
    std::map<int, Account> readCache;

    std::vector<std::pair<long long, long long>> predicates;
};

class TransactionError : public std::runtime_error {
public:
    explicit TransactionError(const std::string& message)
        : std::runtime_error(message) {}
};

class GovernanceDatabase {
private:
    long long commitVersion_ = 0;
    int nextTransactionId_ = 1;

    std::map<int, std::vector<Version>> history_;

    // Every active transaction has a private write set.
    std::map<int, std::map<int, Account>> privateWrites_;

    /*
     * SERIALIZABLE is represented by a single ownership token in this
     * case study. A real database can use row locks, key-range locks,
     * predicate locks, SSI, or optimistic validation instead.
     */
    std::optional<int> serialOwner_;

public:
    void seed(const std::vector<Account>& accounts) {
        ++commitVersion_;

        for (const auto& account : accounts) {
            if (history_.contains(account.id)) {
                throw TransactionError("Duplicate account during seed.");
            }

            history_[account.id].push_back({commitVersion_, account});
        }
    }

    Transaction begin(IsolationLevel isolation) {
        if (isolation == IsolationLevel::Serializable) {
            if (serialOwner_.has_value()) {
                throw TransactionError(
                    "SERIALIZABLE transaction cannot start while another "
                    "serial transaction owns the execution token."
                );
            }
        }

        Transaction transaction{
            nextTransactionId_++,
            isolation,
            commitVersion_
        };

        privateWrites_[transaction.id] = {};

        if (isolation == IsolationLevel::Serializable) {
            serialOwner_ = transaction.id;
        }

        return transaction;
    }

private:
    void requireActive(const Transaction& transaction) const {
        if (!transaction.active) {
            throw TransactionError(
                "Transaction " + std::to_string(transaction.id) +
                " is no longer active."
            );
        }
    }

    std::optional<Account> latestCommitted(int accountId) const {
        auto it = history_.find(accountId);

        if (it == history_.end() || it->second.empty()) {
            return std::nullopt;
        }

        return it->second.back().account;
    }

    std::optional<Account> snapshotValue(
        int accountId,
        long long snapshotVersion
    ) const {
        auto it = history_.find(accountId);

        if (it == history_.end()) {
            return std::nullopt;
        }

        std::optional<Account> visible;

        for (const auto& version : it->second) {
            if (version.commitVersion <= snapshotVersion) {
                visible = version.account;
            } else {
                break;
            }
        }

        return visible;
    }

    std::optional<Account> dirtyValue(
        const Transaction& reader,
        int accountId
    ) const {
        for (const auto& [transactionId, writes] : privateWrites_) {
            if (transactionId == reader.id) {
                continue;
            }

            auto it = writes.find(accountId);

            if (it != writes.end()) {
                return it->second;
            }
        }

        return std::nullopt;
    }

public:
    std::optional<Account> read(
        Transaction& transaction,
        int accountId
    ) {
        requireActive(transaction);

        auto ownWrite = privateWrites_[transaction.id].find(accountId);

        if (ownWrite != privateWrites_[transaction.id].end()) {
            return ownWrite->second;
        }

        switch (transaction.isolation) {
            case IsolationLevel::ReadUncommitted: {
                auto dirty = dirtyValue(transaction, accountId);

                if (dirty.has_value()) {
                    return dirty;
                }

                return latestCommitted(accountId);
            }

            case IsolationLevel::ReadCommitted:
                /*
                 * READ COMMITTED resolves each statement against the
                 * currently committed version. A later statement may
                 * therefore observe a newer commit.
                 */
                return latestCommitted(accountId);

            case IsolationLevel::RepeatableRead: {
                /*
                 * The first read establishes the row's visible version
                 * for this transaction. Subsequent reads use that cached
                 * observation.
                 */
                auto cached = transaction.readCache.find(accountId);

                if (cached != transaction.readCache.end()) {
                    return cached->second;
                }

                auto snapshot = snapshotValue(
                    accountId,
                    transaction.snapshotVersion
                );

                if (snapshot.has_value()) {
                    transaction.readCache[accountId] = snapshot.value();
                }

                return snapshot;
            }

            case IsolationLevel::Serializable:
                /*
                 * The serial ownership token means no concurrent
                 * SERIALIZABLE transaction can interleave with this one.
                 */
                return latestCommitted(accountId);
        }

        throw TransactionError("Unsupported isolation level.");
    }

    void write(
        Transaction& transaction,
        int accountId,
        long long newBalance
    ) {
        requireActive(transaction);

        if (newBalance < 0) {
            throw TransactionError(
                "A financial account cannot have a negative balance."
            );
        }

        auto current = read(transaction, accountId);

        if (!current.has_value()) {
            throw TransactionError(
                "Account " + std::to_string(accountId) +
                " does not exist."
            );
        }

        Account updated = current.value();
        updated.balance = newBalance;

        privateWrites_[transaction.id][accountId] = updated;
        transaction.writes[accountId] = updated;
    }

    void insert(
        Transaction& transaction,
        const Account& account
    ) {
        requireActive(transaction);

        if (account.balance < 0) {
            throw TransactionError(
                "New account cannot have a negative balance."
            );
        }

        if (history_.contains(account.id)) {
            throw TransactionError(
                "Account ID " + std::to_string(account.id) +
                " already exists."
            );
        }

        privateWrites_[transaction.id][account.id] = account;
        transaction.writes[account.id] = account;
    }

    std::vector<Account> rangeQuery(
        Transaction& transaction,
        long long minimum,
        long long maximum
    ) {
        requireActive(transaction);

        if (minimum > maximum) {
            throw TransactionError(
                "Range minimum cannot exceed range maximum."
            );
        }

        transaction.predicates.emplace_back(minimum, maximum);

        std::vector<Account> result;

        for (const auto& [id, versions] : history_) {
            std::optional<Account> visible;

            if (transaction.isolation == IsolationLevel::RepeatableRead) {
                visible = snapshotValue(
                    id,
                    transaction.snapshotVersion
                );
            } else {
                visible = latestCommitted(id);
            }

            if (visible.has_value() &&
                visible->balance >= minimum &&
                visible->balance <= maximum) {
                result.push_back(visible.value());
            }
        }

        std::sort(
            result.begin(),
            result.end(),
            [](const Account& a, const Account& b) {
                return a.id < b.id;
            }
        );

        return result;
    }

    void commit(Transaction& transaction) {
        requireActive(transaction);

        ++commitVersion_;

        for (const auto& [accountId, account] :
             privateWrites_[transaction.id]) {
            history_[accountId].push_back({
                commitVersion_,
                account
            });
        }

        privateWrites_.erase(transaction.id);
        transaction.active = false;

        if (serialOwner_.has_value() &&
            serialOwner_.value() == transaction.id) {
            serialOwner_.reset();
        }
    }

    void rollback(Transaction& transaction) {
        requireActive(transaction);

        privateWrites_.erase(transaction.id);
        transaction.active = false;

        if (serialOwner_.has_value() &&
            serialOwner_.value() == transaction.id) {
            serialOwner_.reset();
        }
    }

    std::vector<Account> currentAccounts() const {
        std::vector<Account> result;

        for (const auto& [id, versions] : history_) {
            if (!versions.empty()) {
                result.push_back(versions.back().account);
            }
        }

        return result;
    }
};

void printAccounts(const std::vector<Account>& accounts) {
    for (const auto& account : accounts) {
        std::cout
            << "  account=" << std::setw(2) << account.id
            << " owner=" << std::setw(10) << account.owner
            << " balance=" << account.balance
            << '\n';
    }
}

void demonstrateDirtyRead() {
    std::cout << "\n=== Dirty Read ===\n";

    GovernanceDatabase db;
    db.seed({{1, "Asha", 1000}});

    auto writer = db.begin(IsolationLevel::ReadCommitted);
    auto reader = db.begin(IsolationLevel::ReadUncommitted);

    db.write(writer, 1, 250);

    auto dirty = db.read(reader, 1);

    std::cout
        << "READ UNCOMMITTED observes balance before writer commits: "
        << dirty->balance
        << '\n';

    db.rollback(writer);

    auto durable = db.read(reader, 1);

    std::cout
        << "After rollback, committed balance: "
        << durable->balance
        << '\n';

    db.rollback(reader);
}

void demonstrateNonRepeatableRead() {
    std::cout << "\n=== Non-Repeatable Read ===\n";

    GovernanceDatabase db;
    db.seed({{1, "Asha", 1000}});

    auto reader = db.begin(IsolationLevel::ReadCommitted);
    auto writer = db.begin(IsolationLevel::ReadCommitted);

    const auto first = db.read(reader, 1);

    db.write(writer, 1, 700);
    db.commit(writer);

    const auto second = db.read(reader, 1);

    std::cout
        << "First READ COMMITTED result: "
        << first->balance
        << '\n';

    std::cout
        << "Second READ COMMITTED result: "
        << second->balance
        << '\n';

    db.rollback(reader);
}

void demonstrateRepeatableRead() {
    std::cout << "\n=== Repeatable Read ===\n";

    GovernanceDatabase db;
    db.seed({{1, "Asha", 1000}});

    auto reader = db.begin(IsolationLevel::RepeatableRead);
    auto writer = db.begin(IsolationLevel::ReadCommitted);

    const auto first = db.read(reader, 1);

    db.write(writer, 1, 700);
    db.commit(writer);

    const auto second = db.read(reader, 1);

    std::cout
        << "First REPEATABLE READ result: "
        << first->balance
        << '\n';

    std::cout
        << "Second REPEATABLE READ result: "
        << second->balance
        << '\n';

    std::cout
        << "The transaction continues to use its original visible "
           "row version.\n";

    db.commit(reader);
}

void demonstratePhantomRead() {
    std::cout << "\n=== Phantom Read ===\n";

    GovernanceDatabase db;

    db.seed({
        {1, "Asha", 1000},
        {2, "Ravi", 4000},
        {3, "Mina", 8000}
    });

    auto reader = db.begin(IsolationLevel::RepeatableRead);
    auto inserter = db.begin(IsolationLevel::ReadCommitted);

    const auto first = db.rangeQuery(reader, 1000, 5000);

    db.insert(inserter, {4, "Noor", 3000});
    db.commit(inserter);

    const auto second = db.rangeQuery(reader, 1000, 5000);

    std::cout << "First range row IDs: ";
    for (const auto& account : first) {
        std::cout << account.id << ' ';
    }

    std::cout << "\nSecond range row IDs: ";
    for (const auto& account : second) {
        std::cout << account.id << ' ';
    }

    std::cout
        << "\nThe case study distinguishes stable row versions from "
           "predicate-level protection.\n";

    db.commit(reader);
}

void demonstrateSerializable() {
    std::cout << "\n=== Serializable Governance ===\n";

    GovernanceDatabase db;

    db.seed({
        {1, "Asha", 1000},
        {2, "Ravi", 4000}
    });

    auto first = db.begin(IsolationLevel::Serializable);

    try {
        auto second = db.begin(IsolationLevel::Serializable);
        db.rollback(second);
    } catch (const TransactionError& error) {
        std::cout
            << "Second SERIALIZABLE transaction rejected while the "
               "first owns the serial execution token: "
            << error.what()
            << '\n';
    }

    const auto firstRange = db.rangeQuery(first, 1000, 5000);

    std::cout
        << "First serial transaction observes "
        << firstRange.size()
        << " qualifying accounts.\n";

    db.commit(first);

    auto second = db.begin(IsolationLevel::Serializable);

    std::cout
        << "Second SERIALIZABLE transaction can now begin after "
           "the first transaction commits.\n";

    db.commit(second);
}

void demonstrateWriteSkew() {
    std::cout << "\n=== Write Skew Business Invariant ===\n";

    GovernanceDatabase db;

    /*
     * Balance 1 means "available" and balance 0 means "unavailable".
     * The business invariant is that at least one doctor must remain
     * available. Two independently committed decisions can violate that
     * invariant when transactions do not serialize their observations.
     */
    db.seed({
        {1, "Doctor-A", 1},
        {2, "Doctor-B", 1}
    });

    auto first = db.begin(IsolationLevel::RepeatableRead);
    auto second = db.begin(IsolationLevel::RepeatableRead);

    const auto firstView = db.rangeQuery(first, 1, 1);
    const auto secondView = db.rangeQuery(second, 1, 1);

    std::cout
        << "T1 sees available doctors: "
        << firstView.size()
        << '\n';

    std::cout
        << "T2 sees available doctors: "
        << secondView.size()
        << '\n';

    db.write(first, 1, 0);
    db.write(second, 2, 0);

    db.commit(first);
    db.commit(second);

    const auto finalState = db.currentAccounts();

    std::size_t available = 0;

    for (const auto& account : finalState) {
        if (account.balance == 1) {
            ++available;
        }
    }

    std::cout
        << "Available doctors after both commits: "
        << available
        << '\n';

    std::cout
        << "This illustrates why application-level invariants can "
           "require stronger conflict control than stable individual reads.\n";
}

void compareLevels() {
    std::cout << "\n=== Isolation Characteristics ===\n";

    struct Row {
        IsolationLevel level;
        std::string dirty;
        std::string nonRepeatable;
        std::string phantom;
        std::string tradeoff;
    };

    const std::vector<Row> rows = {
        {
            IsolationLevel::ReadUncommitted,
            "Possible",
            "Possible",
            "Possible",
            "Weakest visibility guarantees"
        },
        {
            IsolationLevel::ReadCommitted,
            "Prevented",
            "Possible",
            "Possible",
            "Fresh committed statement reads"
        },
        {
            IsolationLevel::RepeatableRead,
            "Prevented",
            "Prevented",
            "Engine-dependent",
            "Stable transaction observations"
        },
        {
            IsolationLevel::Serializable,
            "Prevented",
            "Prevented",
            "Prevented",
            "Serial-equivalent execution"
        }
    };

    std::cout
        << std::left
        << std::setw(21) << "Level"
        << std::setw(12) << "Dirty"
        << std::setw(18) << "Non-repeatable"
        << std::setw(18) << "Phantom"
        << "Trade-off"
        << '\n';

    std::cout << std::string(95, '-') << '\n';

    for (const auto& row : rows) {
        std::cout
            << std::setw(21) << toString(row.level)
            << std::setw(12) << row.dirty
            << std::setw(18) << row.nonRepeatable
            << std::setw(18) << row.phantom
            << row.tradeoff
            << '\n';
    }
}

void demonstrateValidation() {
    std::cout << "\n=== Validation and Transaction Failure ===\n";

    GovernanceDatabase db;
    db.seed({{1, "Asha", 1000}});

    auto transaction = db.begin(IsolationLevel::ReadCommitted);

    try {
        db.write(transaction, 1, -100);
    } catch (const TransactionError& error) {
        std::cout
            << "Invalid write rejected: "
            << error.what()
            << '\n';
    }

    db.commit(transaction);

    try {
        db.read(transaction, 1);
    } catch (const TransactionError& error) {
        std::cout
            << "Operation on completed transaction rejected: "
            << error.what()
            << '\n';
    }
}

int main() {
    try {
        std::cout << "TRANSACTION ISOLATION LEVEL CASE STUDY\n";
        std::cout << "=====================================\n";

        demonstrateDirtyRead();
        demonstrateNonRepeatableRead();
        demonstrateRepeatableRead();
        demonstratePhantomRead();
        demonstrateSerializable();
        demonstrateWriteSkew();
        compareLevels();
        demonstrateValidation();

        GovernanceDatabase finalDatabase;

        finalDatabase.seed({
            {1, "Asha", 1250},
            {2, "Ravi", 3200},
            {3, "Mina", 9100}
        });

        std::cout << "\n=== Final Database State ===\n";
        printAccounts(finalDatabase.currentAccounts());

        std::cout
            << "\nC++17 case study completed successfully.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal database simulation error: "
            << error.what()
            << '\n';

        return 1;
    }
}
