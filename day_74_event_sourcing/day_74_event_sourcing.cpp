#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

enum class EventType {
    AccountOpened,
    MoneyDeposited,
    MoneyWithdrawn,
    AccountFrozen,
    AccountUnfrozen
};

std::string eventName(EventType type) {
    switch (type) {
        case EventType::AccountOpened: return "AccountOpened";
        case EventType::MoneyDeposited: return "MoneyDeposited";
        case EventType::MoneyWithdrawn: return "MoneyWithdrawn";
        case EventType::AccountFrozen: return "AccountFrozen";
        case EventType::AccountUnfrozen: return "AccountUnfrozen";
    }
    throw std::invalid_argument("Unknown event type.");
}

struct Event {
    std::string id;
    std::string aggregateId;
    std::uint64_t version;
    EventType type;
    std::int64_t amount = 0;
    std::string owner;
};

class DomainError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ConcurrencyError : public DomainError {
public:
    using DomainError::DomainError;
};

class ValidationError : public DomainError {
public:
    using DomainError::DomainError;
};

class InsufficientFundsError : public DomainError {
public:
    using DomainError::DomainError;
};

class EventStore {
private:
    std::unordered_map<std::string, std::vector<Event>> streams_;
    std::set<std::string> eventIds_;
    std::unordered_map<std::string, std::string> commandResults_;

public:
    std::uint64_t version(const std::string& id) const {
        auto it = streams_.find(id);

        if (it == streams_.end()) {
            return 0;
        }

        return it->second.size();
    }

    const std::vector<Event>& load(const std::string& id) const {
        static const std::vector<Event> empty;

        auto it = streams_.find(id);
        return it == streams_.end() ? empty : it->second;
    }

    void append(
        const Event& event,
        std::uint64_t expectedVersion,
        const std::string& commandId
    ) {
        if (event.aggregateId.empty() || event.id.empty() ||
            commandId.empty()) {
            throw ValidationError("Identifiers cannot be empty.");
        }

        auto previous = commandResults_.find(commandId);

        if (previous != commandResults_.end()) {
            if (previous->second != event.id) {
                throw ValidationError(
                    "Command ID reused with different event."
                );
            }
            return;
        }

        if (eventIds_.count(event.id)) {
            throw ValidationError("Duplicate event ID.");
        }

        const auto current = version(event.aggregateId);

        if (current != expectedVersion) {
            throw ConcurrencyError("Optimistic concurrency conflict.");
        }

        if (event.version != current + 1) {
            throw ValidationError("Invalid event sequence.");
        }

        streams_[event.aggregateId].push_back(event);
        eventIds_.insert(event.id);
        commandResults_[commandId] = event.id;
    }

    std::vector<Event> allEvents() const {
        std::vector<Event> result;

        for (const auto& [id, events] : streams_) {
            result.insert(result.end(), events.begin(), events.end());
        }

        std::sort(result.begin(), result.end(),
            [](const Event& a, const Event& b) {
                if (a.aggregateId != b.aggregateId) {
                    return a.aggregateId < b.aggregateId;
                }
                return a.version < b.version;
            });

        return result;
    }
};

class Account {
private:
    std::string id_;
    std::string owner_;
    std::int64_t balance_ = 0;
    bool frozen_ = false;
    std::uint64_t version_ = 0;

public:
    explicit Account(std::string id) : id_(std::move(id)) {}

    void apply(const Event& event) {
        if (event.aggregateId != id_) {
            throw ValidationError("Aggregate identity mismatch.");
        }

        if (event.version != version_ + 1) {
            throw ValidationError("Event sequence mismatch.");
        }

        switch (event.type) {
            case EventType::AccountOpened:
                if (version_ != 0 || event.owner.empty()) {
                    throw ValidationError("Invalid opening event.");
                }
                owner_ = event.owner;
                break;

            case EventType::MoneyDeposited:
                if (frozen_ || event.amount <= 0) {
                    throw ValidationError("Invalid deposit.");
                }
                if (balance_ >
                    INT64_MAX - event.amount) {
                    throw ValidationError("Balance overflow.");
                }
                balance_ += event.amount;
                break;

            case EventType::MoneyWithdrawn:
                if (frozen_ || event.amount <= 0) {
                    throw ValidationError("Invalid withdrawal.");
                }
                if (event.amount > balance_) {
                    throw InsufficientFundsError("Insufficient funds.");
                }
                balance_ -= event.amount;
                break;

            case EventType::AccountFrozen:
                frozen_ = true;
                break;

            case EventType::AccountUnfrozen:
                frozen_ = false;
                break;
        }

        version_ = event.version;
    }

    static Account rehydrate(
        const std::string& id,
        const std::vector<Event>& events
    ) {
        Account account(id);

        for (const auto& event : events) {
            account.apply(event);
        }

        if (account.version_ == 0) {
            throw ValidationError("Account does not exist.");
        }

        return account;
    }

    const std::string& id() const { return id_; }
    const std::string& owner() const { return owner_; }
    std::int64_t balance() const { return balance_; }
    bool frozen() const { return frozen_; }
    std::uint64_t version() const { return version_; }
};

class AccountService {
private:
    EventStore& store_;
    std::uint64_t eventCounter_ = 0;

    Event create(
        const std::string& accountId,
        EventType type,
        std::int64_t amount,
        const std::string& owner
    ) {
        const auto nextVersion = store_.version(accountId) + 1;

        return Event{
            "EVT-" + std::to_string(++eventCounter_),
            accountId,
            nextVersion,
            type,
            amount,
            owner
        };
    }

public:
    explicit AccountService(EventStore& store) : store_(store) {}

    void open(const std::string& id, const std::string& owner) {
        if (owner.empty() || store_.version(id) != 0) {
            throw ValidationError("Invalid account creation.");
        }

        auto event = create(
            id, EventType::AccountOpened, 0, owner
        );

        store_.append(event, 0, "OPEN-" + id);
    }

    void deposit(
        const std::string& id,
        std::int64_t amount,
        const std::string& command
    ) {
        if (amount <= 0) {
            throw ValidationError("Deposit must be positive.");
        }

        auto account = Account::rehydrate(id, store_.load(id));

        if (account.frozen()) {
            throw ValidationError("Account is frozen.");
        }

        if (account.balance() > INT64_MAX - amount) {
            throw ValidationError("Balance overflow.");
        }

        auto event = create(
            id, EventType::MoneyDeposited, amount, ""
        );

        store_.append(event, account.version(), command);
    }

    void withdraw(
        const std::string& id,
        std::int64_t amount,
        const std::string& command
    ) {
        if (amount <= 0) {
            throw ValidationError("Withdrawal must be positive.");
        }

        auto account = Account::rehydrate(id, store_.load(id));

        if (account.frozen()) {
            throw ValidationError("Account is frozen.");
        }

        if (amount > account.balance()) {
            throw InsufficientFundsError("Insufficient funds.");
        }

        auto event = create(
            id, EventType::MoneyWithdrawn, amount, ""
        );

        store_.append(event, account.version(), command);
    }

    void freeze(const std::string& id, bool frozen) {
        auto account = Account::rehydrate(id, store_.load(id));

        if (account.frozen() == frozen) {
            throw ValidationError("Account already in requested state.");
        }

        auto type = frozen
            ? EventType::AccountFrozen
            : EventType::AccountUnfrozen;

        auto event = create(id, type, 0, "");

        store_.append(
            event,
            account.version(),
            "STATE-" + id + "-" + std::to_string(event.version)
        );
    }
};

struct AccountReadModel {
    std::string owner;
    std::int64_t balance = 0;
    bool frozen = false;
    std::uint64_t version = 0;
};

class Projection {
private:
    std::map<std::string, AccountReadModel> accounts_;

public:
    void apply(const Event& event) {
        if (event.type == EventType::AccountOpened) {
            if (accounts_.count(event.aggregateId)) {
                throw ValidationError("Duplicate projection account.");
            }

            accounts_[event.aggregateId] = {
                event.owner, 0, false, 1
            };
            return;
        }

        auto it = accounts_.find(event.aggregateId);

        if (it == accounts_.end()) {
            throw ValidationError("Unknown projection aggregate.");
        }

        auto& account = it->second;

        if (event.version != account.version + 1) {
            throw ValidationError("Projection sequence mismatch.");
        }

        switch (event.type) {
            case EventType::MoneyDeposited:
                account.balance += event.amount;
                break;

            case EventType::MoneyWithdrawn:
                account.balance -= event.amount;
                break;

            case EventType::AccountFrozen:
                account.frozen = true;
                break;

            case EventType::AccountUnfrozen:
                account.frozen = false;
                break;

            default:
                throw ValidationError("Unexpected projection event.");
        }

        account.version = event.version;
    }

    void rebuild(const std::vector<Event>& events) {
        accounts_.clear();

        for (const auto& event : events) {
            apply(event);
        }
    }

    const AccountReadModel& get(const std::string& id) const {
        auto it = accounts_.find(id);

        if (it == accounts_.end()) {
            throw ValidationError("Projection record not found.");
        }

        return it->second;
    }
};

int main() {
    try {
        EventStore store;
        AccountService service(store);

        service.open("ACC-3001", "Atul");
        service.deposit("ACC-3001", 20000, "CMD-001");
        service.withdraw("ACC-3001", 5000, "CMD-002");
        service.freeze("ACC-3001", true);

        // Frozen accounts cannot accept financial commands.
        try {
            service.deposit("ACC-3001", 1000, "CMD-003");
            throw std::runtime_error("Freeze validation failed.");
        } catch (const ValidationError&) {
            std::cout << "Frozen account validation: PASSED\n";
        }

        service.freeze("ACC-3001", false);
        service.deposit("ACC-3001", 2500, "CMD-004");

        auto account = Account::rehydrate(
            "ACC-3001",
            store.load("ACC-3001")
        );

        Projection projection;
        projection.rebuild(store.allEvents());

        const auto& readModel = projection.get("ACC-3001");

        if (account.balance() != 17500 ||
            readModel.balance != 17500) {
            throw std::runtime_error("Balance assertion failed.");
        }

        // Historical events are independent of the current projection.
        std::cout << "\nEVENT SOURCING GOVERNANCE ENGINE\n";
        std::cout << "--------------------------------\n";
        std::cout << "Account: " << account.id() << '\n';
        std::cout << "Owner: " << account.owner() << '\n';
        std::cout << "Balance: " << account.balance() << '\n';
        std::cout << "Version: " << account.version() << '\n';
        std::cout << "Frozen: "
                  << std::boolalpha << account.frozen() << '\n';

        std::cout << "\nEVENT HISTORY\n";

        for (const auto& event : store.load("ACC-3001")) {
            std::cout << std::setw(2) << event.version
                      << " | " << eventName(event.type)
                      << " | " << event.id << '\n';
        }

        std::cout << "\nProjection balance: "
                  << readModel.balance << '\n';
        std::cout << "Projection version: "
                  << readModel.version << '\n';
        std::cout << "Event replay: PASSED\n";
        std::cout << "State transition validation: PASSED\n";
        std::cout << "Balance consistency: PASSED\n";

        // Demonstrate stale writer rejection.
        try {
            Event stale{
                "EVT-STALE",
                "ACC-3001",
                2,
                EventType::MoneyDeposited,
                100,
                ""
            };

            store.append(stale, 1, "CMD-STALE");
            throw std::runtime_error("Concurrency test failed.");
        } catch (const ConcurrencyError&) {
            std::cout << "Optimistic concurrency: PASSED\n";
        }

    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
