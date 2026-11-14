#include <algorithm>
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

/*
 * CQRS repository for a financial transaction platform.
 *
 * Architecture:
 * Command -> Aggregate -> Event Store
 *                         |
 *                         v
 *                    Event Processor
 *                         |
 *                         v
 *                    Read Projection
 *                         |
 *                         v
 *                    Query Service
 *
 * C++17, standard library only.
 */

namespace cqrs {

// ============================================================
// 1. EXCEPTIONS
// ============================================================

class DomainError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ValidationError : public DomainError {
public:
    using DomainError::DomainError;
};

class NotFoundError : public DomainError {
public:
    using DomainError::DomainError;
};

class ConcurrencyError : public DomainError {
public:
    using DomainError::DomainError;
};

class InsufficientFundsError : public DomainError {
public:
    using DomainError::DomainError;
};

class ProjectionError : public DomainError {
public:
    using DomainError::DomainError;
};

// ============================================================
// 2. DOMAIN TYPES
// ============================================================

enum class CommandType {
    CreateAccount,
    Deposit,
    Withdraw
};

enum class EventType {
    AccountCreated,
    MoneyDeposited,
    MoneyWithdrawn
};

enum class AccountStatus {
    Active,
    Suspended,
    Closed
};

std::string toString(EventType type) {
    switch (type) {
        case EventType::AccountCreated:
            return "ACCOUNT_CREATED";
        case EventType::MoneyDeposited:
            return "MONEY_DEPOSITED";
        case EventType::MoneyWithdrawn:
            return "MONEY_WITHDRAWN";
    }

    throw ValidationError("Unknown event type.");
}

// ============================================================
// 3. MONEY VALIDATION
// ============================================================

class Money {
private:
    long long cents_;

public:
    explicit Money(long long cents = 0) : cents_(cents) {
        if (cents < 0) {
            throw ValidationError("Money cannot be negative.");
        }
    }

    static Money fromDouble(double value) {
        if (!std::isfinite(value) || value <= 0) {
            throw ValidationError("Amount must be positive and finite.");
        }

        double scaled = value * 100.0;

        if (std::abs(scaled - std::round(scaled)) > 1e-7) {
            throw ValidationError("Maximum two decimal places allowed.");
        }

        return Money(static_cast<long long>(std::llround(scaled)));
    }

    long long cents() const {
        return cents_;
    }

    double value() const {
        return static_cast<double>(cents_) / 100.0;
    }

    Money operator+(const Money& other) const {
        if (other.cents_ >
            std::numeric_limits<long long>::max() - cents_) {
            throw DomainError("Money overflow.");
        }

        return Money(cents_ + other.cents_);
    }

    Money operator-(const Money& other) const {
        if (other.cents_ > cents_) {
            throw InsufficientFundsError("Insufficient balance.");
        }

        return Money(cents_ - other.cents_);
    }

    bool operator<(const Money& other) const {
        return cents_ < other.cents_;
    }
};

std::ostream& operator<<(std::ostream& out, const Money& money) {
    out << std::fixed << std::setprecision(2) << money.value();
    return out;
}

// ============================================================
// 4. COMMAND
// ============================================================

struct Command {
    std::string id;
    CommandType type;
    std::string accountId;
    std::string owner;
    Money amount;
    std::optional<int> expectedVersion;
};

// ============================================================
// 5. DOMAIN EVENT
// ============================================================

struct DomainEvent {
    std::string id;
    EventType type;
    std::string aggregateId;
    int version;
    Money amount;
    std::string owner;
    std::string timestamp;
};

// ============================================================
// 6. WRITE MODEL
// ============================================================

class AccountAggregate {
private:
    std::string id_;
    std::string owner_;
    Money balance_;
    int version_;
    AccountStatus status_;

public:
    AccountAggregate(
        std::string id,
        std::string owner,
        Money balance = Money(),
        int version = 0
    )
        : id_(std::move(id)),
          owner_(std::move(owner)),
          balance_(balance),
          version_(version),
          status_(AccountStatus::Active) {

        if (id_.empty() || owner_.empty()) {
            throw ValidationError("Account identity is required.");
        }
    }

    DomainEvent deposit(
        const Money& amount,
        const std::string& eventId,
        const std::string& timestamp
    ) {
        if (status_ != AccountStatus::Active) {
            throw DomainError("Account is not active.");
        }

        balance_ = balance_ + amount;
        ++version_;

        return {
            eventId,
            EventType::MoneyDeposited,
            id_,
            version_,
            amount,
            "",
            timestamp
        };
    }

    DomainEvent withdraw(
        const Money& amount,
        const std::string& eventId,
        const std::string& timestamp
    ) {
        if (status_ != AccountStatus::Active) {
            throw DomainError("Account is not active.");
        }

        balance_ = balance_ - amount;
        ++version_;

        return {
            eventId,
            EventType::MoneyWithdrawn,
            id_,
            version_,
            amount,
            "",
            timestamp
        };
    }

    void rollbackDeposit(const Money& amount) {
        balance_ = balance_ - amount;
        --version_;
    }

    void rollbackWithdrawal(const Money& amount) {
        balance_ = balance_ + amount;
        --version_;
    }

    const std::string& id() const {
        return id_;
    }

    const std::string& owner() const {
        return owner_;
    }

    Money balance() const {
        return balance_;
    }

    int version() const {
        return version_;
    }
};

// ============================================================
// 7. EVENT STORE
// ============================================================

class EventStore {
private:
    std::map<std::string, std::vector<DomainEvent>> streams_;
    std::set<std::string> eventIds_;

public:
    void append(
        const std::string& aggregateId,
        int expectedVersion,
        const std::vector<DomainEvent>& events
    ) {
        if (events.empty()) {
            throw ValidationError("Empty event batch.");
        }

        auto& stream = streams_[aggregateId];

        if (static_cast<int>(stream.size()) != expectedVersion) {
            throw ConcurrencyError("Optimistic concurrency conflict.");
        }

        int nextVersion = expectedVersion;

        // Validate before changing the event stream.
        std::set<std::string> batchIds;

        for (const auto& event : events) {
            ++nextVersion;

            if (
                event.aggregateId != aggregateId ||
                event.version != nextVersion ||
                eventIds_.count(event.id) ||
                !batchIds.insert(event.id).second
            ) {
                throw ValidationError("Invalid event batch.");
            }
        }

        for (const auto& event : events) {
            stream.push_back(event);
            eventIds_.insert(event.id);
        }
    }

    std::vector<DomainEvent> read(
        const std::string& aggregateId
    ) const {
        auto it = streams_.find(aggregateId);

        if (it == streams_.end()) {
            return {};
        }

        return it->second;
    }

    std::vector<DomainEvent> readAll() const {
        std::vector<DomainEvent> result;

        for (const auto& [id, stream] : streams_) {
            result.insert(
                result.end(),
                stream.begin(),
                stream.end()
            );
        }

        return result;
    }

    int version(const std::string& aggregateId) const {
        auto it = streams_.find(aggregateId);

        return it == streams_.end()
            ? 0
            : static_cast<int>(it->second.size());
    }
};

// ============================================================
// 8. READ MODEL
// ============================================================

struct AccountReadModel {
    std::string accountId;
    std::string owner;
    Money balance;
    int version = 0;
    int transactionCount = 0;
    std::string lastUpdated;
};

class AccountProjection {
private:
    std::map<std::string, AccountReadModel> accounts_;
    std::set<std::string> processedEvents_;

public:
    void apply(const DomainEvent& event) {
        if (processedEvents_.count(event.id)) {
            return;
        }

        auto it = accounts_.find(event.aggregateId);

        if (event.type == EventType::AccountCreated) {
            if (it != accounts_.end()) {
                throw ProjectionError("Duplicate account projection.");
            }

            accounts_.emplace(
                event.aggregateId,
                AccountReadModel{
                    event.aggregateId,
                    event.owner,
                    Money(),
                    event.version,
                    0,
                    event.timestamp
                }
            );

        } else {
            if (it == accounts_.end()) {
                throw ProjectionError("Missing account projection.");
            }

            auto& account = it->second;

            if (event.version != account.version + 1) {
                throw ProjectionError("Projection version gap.");
            }

            if (event.type == EventType::MoneyDeposited) {
                account.balance = account.balance + event.amount;
            } else if (event.type == EventType::MoneyWithdrawn) {
                account.balance = account.balance - event.amount;
            }

            account.version = event.version;
            ++account.transactionCount;
            account.lastUpdated = event.timestamp;
        }

        processedEvents_.insert(event.id);
    }

    void rebuild(const std::vector<DomainEvent>& events) {
        accounts_.clear();
        processedEvents_.clear();

        auto ordered = events;

        std::sort(
            ordered.begin(),
            ordered.end(),
            [](const DomainEvent& a, const DomainEvent& b) {
                if (a.aggregateId != b.aggregateId) {
                    return a.aggregateId < b.aggregateId;
                }

                return a.version < b.version;
            }
        );

        for (const auto& event : ordered) {
            apply(event);
        }
    }

    AccountReadModel get(const std::string& id) const {
        auto it = accounts_.find(id);

        if (it == accounts_.end()) {
            throw NotFoundError("Read model not found.");
        }

        return it->second;
    }

    double totalBalance() const {
        long long total = 0;

        for (const auto& [id, account] : accounts_) {
            if (
                account.balance.cents() >
                std::numeric_limits<long long>::max() - total
            ) {
                throw DomainError("Aggregate balance overflow.");
            }

            total += account.balance.cents();
        }

        return static_cast<double>(total) / 100.0;
    }

    const std::map<std::string, AccountReadModel>& accounts() const {
        return accounts_;
    }
};

// ============================================================
// 9. IDEMPOTENCY REGISTRY
// ============================================================

class IdempotencyRegistry {
private:
    std::map<std::string, std::vector<DomainEvent>> results_;

public:
    bool contains(const std::string& id) const {
        return results_.count(id) > 0;
    }

    const std::vector<DomainEvent>& get(
        const std::string& id
    ) const {
        return results_.at(id);
    }

    void save(
        const std::string& id,
        const std::vector<DomainEvent>& result
    ) {
        results_.emplace(id, result);
    }
};

// ============================================================
// 10. COMMAND HANDLER
// ============================================================

class CommandHandler {
private:
    EventStore& eventStore_;
    IdempotencyRegistry& registry_;

    std::map<std::string, AccountAggregate> aggregates_;

    int eventCounter_ = 0;

    std::string nextEventId() {
        return "EVT-" + std::to_string(++eventCounter_);
    }

    std::string timestamp() const {
        return "2026-11-14T12:00:00Z";
    }

public:
    CommandHandler(
        EventStore& eventStore,
        IdempotencyRegistry& registry
    )
        : eventStore_(eventStore),
          registry_(registry) {}

    DomainEvent createAccount(
        const std::string& commandId,
        const std::string& accountId,
        const std::string& owner
    ) {
        if (registry_.contains(commandId)) {
            return registry_.get(commandId).front();
        }

        if (accountId.empty() || owner.empty()) {
            throw ValidationError("Invalid account details.");
        }

        if (aggregates_.count(accountId)) {
            throw ValidationError("Account already exists.");
        }

        DomainEvent event{
            nextEventId(),
            EventType::AccountCreated,
            accountId,
            1,
            Money(),
            owner,
            timestamp()
        };

        eventStore_.append(accountId, 0, {event});

        aggregates_.emplace(
            accountId,
            AccountAggregate(accountId, owner, Money(), 1)
        );

        registry_.save(commandId, {event});

        return event;
    }

    std::vector<DomainEvent> execute(const Command& command) {
        if (registry_.contains(command.id)) {
            return registry_.get(command.id);
        }

        auto it = aggregates_.find(command.accountId);

        if (it == aggregates_.end()) {
            throw NotFoundError("Account not found.");
        }

        auto& aggregate = it->second;

        int currentVersion = eventStore_.version(command.accountId);

        if (aggregate.version() != currentVersion) {
            throw ConcurrencyError("Aggregate and event stream differ.");
        }

        if (
            command.expectedVersion &&
            *command.expectedVersion != currentVersion
        ) {
            throw ConcurrencyError("Stale command rejected.");
        }

        DomainEvent event;

        if (command.type == CommandType::Deposit) {
            event = aggregate.deposit(
                command.amount,
                nextEventId(),
                timestamp()
            );

        } else if (command.type == CommandType::Withdraw) {
            event = aggregate.withdraw(
                command.amount,
                nextEventId(),
                timestamp()
            );

        } else {
            throw ValidationError("Unsupported command.");
        }

        try {
            eventStore_.append(
                command.accountId,
                currentVersion,
                {event}
            );
        } catch (...) {
            if (event.type == EventType::MoneyDeposited) {
                aggregate.rollbackDeposit(event.amount);
            } else {
                aggregate.rollbackWithdrawal(event.amount);
            }

            throw;
        }

        std::vector<DomainEvent> result{event};

        registry_.save(command.id, result);

        return result;
    }

    AccountAggregate getWriteState(const std::string& id) const {
        auto it = aggregates_.find(id);

        if (it == aggregates_.end()) {
            throw NotFoundError("Account does not exist.");
        }

        return it->second;
    }
};

// ============================================================
// 11. QUERY SERVICE
// ============================================================

class QueryService {
private:
    const AccountProjection& projection_;

public:
    explicit QueryService(const AccountProjection& projection)
        : projection_(projection) {}

    AccountReadModel accountDetails(const std::string& id) const {
        return projection_.get(id);
    }

    double totalBalance() const {
        return projection_.totalBalance();
    }
};

// ============================================================
// 12. APPLICATION
// ============================================================

class BankingApplication {
private:
    EventStore eventStore_;
    IdempotencyRegistry registry_;
    CommandHandler commandHandler_;
    AccountProjection projection_;

public:
    BankingApplication()
        : commandHandler_(eventStore_, registry_) {}

    CommandHandler& commands() {
        return commandHandler_;
    }

    EventStore& events() {
        return eventStore_;
    }

    AccountProjection& projection() {
        return projection_;
    }

    QueryService queries() const {
        return QueryService(projection_);
    }

    void synchronize() {
        projection_.rebuild(eventStore_.readAll());
    }
};

} // namespace cqrs

// ============================================================
// 13. EXECUTABLE SCENARIO
// ============================================================

int main() {
    using namespace cqrs;

    try {
        BankingApplication application;

        auto& commands = application.commands();

        commands.createAccount(
            "CMD-001",
            "ACC-3001",
            "Ishita"
        );

        commands.createAccount(
            "CMD-002",
            "ACC-3002",
            "Kabir"
        );

        Command deposit1{
            "CMD-003",
            CommandType::Deposit,
            "ACC-3001",
            "",
            Money::fromDouble(15000.00),
            1
        };

        Command deposit2{
            "CMD-004",
            CommandType::Deposit,
            "ACC-3001",
            "",
            Money::fromDouble(5000.00),
            2
        };

        Command withdrawal{
            "CMD-005",
            CommandType::Withdraw,
            "ACC-3001",
            "",
            Money::fromDouble(3000.00),
            3
        };

        Command secondAccountDeposit{
            "CMD-006",
            CommandType::Deposit,
            "ACC-3002",
            "",
            Money::fromDouble(8000.00),
            1
        };

        commands.execute(deposit1);
        commands.execute(deposit2);
        commands.execute(withdrawal);
        commands.execute(secondAccountDeposit);

        // Read-side synchronization is a separate operation.
        application.synchronize();

        auto queries = application.queries();

        auto first = queries.accountDetails("ACC-3001");
        auto second = queries.accountDetails("ACC-3002");

        std::cout << "CQRS ACCOUNT REPORT\n\n";

        for (const auto& [id, account] :
             application.projection().accounts()) {

            std::cout
                << "Account: " << id
                << "\nOwner: " << account.owner
                << "\nBalance: " << account.balance
                << "\nVersion: " << account.version
                << "\nTransactions: " << account.transactionCount
                << "\n\n";
        }

        std::cout
            << "Total balance: "
            << queries.totalBalance()
            << "\n";

        if (first.balance.value() != 17000.00) {
            throw DomainError("First account balance mismatch.");
        }

        if (second.balance.value() != 8000.00) {
            throw DomainError("Second account balance mismatch.");
        }

        // Duplicate command does not append a second event.
        std::size_t before =
            application.events().read("ACC-3001").size();

        commands.execute(deposit1);

        std::size_t after =
            application.events().read("ACC-3001").size();

        if (before != after) {
            throw DomainError("Idempotency validation failed.");
        }

        // Stale version.
        try {
            Command stale{
                "CMD-007",
                CommandType::Deposit,
                "ACC-3001",
                "",
                Money::fromDouble(100.00),
                1
            };

            commands.execute(stale);
            throw DomainError("Stale command should have failed.");
        } catch (const ConcurrencyError&) {
            std::cout << "Stale command rejected.\n";
        }

        // Insufficient funds.
        try {
            Command invalidWithdrawal{
                "CMD-008",
                CommandType::Withdraw,
                "ACC-3001",
                "",
                Money::fromDouble(999999.00),
                4
            };

            commands.execute(invalidWithdrawal);
            throw DomainError("Withdrawal should have failed.");
        } catch (const InsufficientFundsError&) {
            std::cout << "Insufficient funds rejected.\n";
        }

        // Projection replay.
        double originalTotal = queries.totalBalance();

        application.synchronize();

        double rebuiltTotal =
            application.queries().totalBalance();

        if (originalTotal != rebuiltTotal) {
            throw ProjectionError("Projection rebuild mismatch.");
        }

        std::cout << "Projection rebuild verified.\n";
        std::cout << "All CQRS tests passed.\n";

    } catch (const std::exception& error) {
        std::cerr << "Application error: "
                  << error.what() << '\n';

        return 1;
    }

    return 0;
}
