#include <algorithm>
#include <cassert>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Transactional Governance Engine
 *
 * This C++17 case study models a financial transaction coordinator for a
 * payment service. The central problem is not simply changing balances:
 * several dependent state changes must satisfy invariants as one atomic
 * unit.
 *
 * The implementation demonstrates:
 * - transaction lifecycle
 * - atomic staging and commit
 * - rollback
 * - consistency invariants
 * - optimistic concurrency control
 * - idempotency keys
 * - balanced double-entry ledger records
 * - validation and business-rule failures
 * - retry classification
 * - audit events
 *
 * The Store represents the durable database boundary. Transaction objects
 * operate on private staged state and publish that state only during commit.
 */

enum class TransactionState {
    Created,
    Active,
    Committed,
    RolledBack
};

enum class ErrorCode {
    InvalidState,
    AccountNotFound,
    InvalidAmount,
    SameAccount,
    CurrencyMismatch,
    InsufficientFunds,
    DuplicateTransfer,
    NegativeBalance,
    ConsistencyFailure,
    SerializationConflict,
    RetryableDependencyFailure
};

struct TransactionError : public std::runtime_error {
    ErrorCode code;
    bool retryable;

    TransactionError(
        const std::string& message,
        ErrorCode error_code,
        bool can_retry = false
    )
        : std::runtime_error(message),
          code(error_code),
          retryable(can_retry) {}
};

struct Account {
    std::string id;
    std::string owner;
    std::string currency;
    long long balance_cents;
    long long version;
};

struct Transfer {
    std::string id;
    std::string source;
    std::string destination;
    long long amount_cents;
};

struct LedgerEntry {
    std::string transfer_id;
    std::string account_id;
    std::string direction;
    long long amount_cents;
};

struct AuditEvent {
    std::string transaction_id;
    std::string event;
    std::string detail;
};

class Store {
public:
    void addAccount(
        const std::string& id,
        const std::string& owner,
        const std::string& currency,
        long long balance_cents
    ) {
        if (id.empty()) {
            throw TransactionError(
                "Account ID cannot be empty",
                ErrorCode::AccountNotFound
            );
        }

        if (accounts_.contains(id)) {
            throw std::invalid_argument("Duplicate account ID: " + id);
        }

        if (currency != "INR" && currency != "USD") {
            throw std::invalid_argument("Unsupported currency: " + currency);
        }

        if (balance_cents < 0) {
            throw std::invalid_argument("Opening balance cannot be negative");
        }

        accounts_.emplace(
            id,
            Account{id, owner, currency, balance_cents, 0}
        );
    }

    Account getAccount(const std::string& id) const {
        auto it = accounts_.find(id);

        if (it == accounts_.end()) {
            throw TransactionError(
                "Unknown account: " + id,
                ErrorCode::AccountNotFound
            );
        }

        return it->second;
    }

    long long totalBalance(const std::string& currency) const {
        long long total = 0;

        for (const auto& [id, account] : accounts_) {
            if (account.currency == currency) {
                total += account.balance_cents;
            }
        }

        return total;
    }

    bool hasTransfer(const std::string& transfer_id) const {
        return transfers_.contains(transfer_id);
    }

    const std::map<std::string, Account>& accounts() const {
        return accounts_;
    }

    const std::map<std::string, Transfer>& transfers() const {
        return transfers_;
    }

    const std::vector<LedgerEntry>& ledger() const {
        return ledger_;
    }

    void applyAccount(const Account& account) {
        auto it = accounts_.find(account.id);

        if (it == accounts_.end()) {
            throw TransactionError(
                "Cannot update missing account",
                ErrorCode::AccountNotFound
            );
        }

        it->second = account;
    }

    void incrementVersion(const std::string& account_id) {
        auto it = accounts_.find(account_id);

        if (it == accounts_.end()) {
            throw TransactionError(
                "Cannot version missing account",
                ErrorCode::AccountNotFound
            );
        }

        ++it->second.version;
    }

    long long currentVersion(const std::string& account_id) const {
        return getAccount(account_id).version;
    }

    void addTransfer(const Transfer& transfer) {
        auto [it, inserted] = transfers_.emplace(
            transfer.id,
            transfer
        );

        if (!inserted) {
            throw TransactionError(
                "Duplicate transfer: " + transfer.id,
                ErrorCode::DuplicateTransfer
            );
        }
    }

    void addLedgerEntry(const LedgerEntry& entry) {
        ledger_.push_back(entry);
    }

    void addAuditEvent(const AuditEvent& event) {
        audit_.push_back(event);
    }

    const std::vector<AuditEvent>& audit() const {
        return audit_;
    }

private:
    std::map<std::string, Account> accounts_;
    std::map<std::string, Transfer> transfers_;
    std::vector<LedgerEntry> ledger_;
    std::vector<AuditEvent> audit_;
};

class Transaction {
public:
    Transaction(Store& store, std::string id)
        : store_(store),
          id_(std::move(id)),
          state_(TransactionState::Created) {}

    void begin() {
        if (state_ != TransactionState::Created) {
            throw TransactionError(
                "Transaction cannot begin from its current state",
                ErrorCode::InvalidState
            );
        }

        state_ = TransactionState::Active;
        store_.addAuditEvent(
            {id_, "BEGIN", "Transaction became active"}
        );
    }

    Account read(const std::string& account_id) {
        ensureActive();

        auto staged = staged_accounts_.find(account_id);

        if (staged != staged_accounts_.end()) {
            return staged->second;
        }

        Account account = store_.getAccount(account_id);

        if (!original_versions_.contains(account_id)) {
            original_versions_[account_id] = account.version;
        }

        return account;
    }

    void transfer(
        const std::string& transfer_id,
        const std::string& source_id,
        const std::string& destination_id,
        long long amount_cents
    ) {
        ensureActive();

        if (transfer_id.empty()) {
            throw TransactionError(
                "Transfer ID cannot be empty",
                ErrorCode::DuplicateTransfer
            );
        }

        if (store_.hasTransfer(transfer_id)) {
            throw TransactionError(
                "Transfer already exists: " + transfer_id,
                ErrorCode::DuplicateTransfer
            );
        }

        if (source_id == destination_id) {
            throw TransactionError(
                "Source and destination must differ",
                ErrorCode::SameAccount
            );
        }

        if (amount_cents <= 0) {
            throw TransactionError(
                "Transfer amount must be positive",
                ErrorCode::InvalidAmount
            );
        }

        Account source = read(source_id);
        Account destination = read(destination_id);

        if (source.currency != destination.currency) {
            throw TransactionError(
                "Currency mismatch",
                ErrorCode::CurrencyMismatch
            );
        }

        if (source.balance_cents < amount_cents) {
            throw TransactionError(
                "Insufficient funds",
                ErrorCode::InsufficientFunds
            );
        }

        source.balance_cents -= amount_cents;
        destination.balance_cents += amount_cents;

        if (source.balance_cents < 0 || destination.balance_cents < 0) {
            throw TransactionError(
                "Negative balance would violate consistency",
                ErrorCode::NegativeBalance
            );
        }

        stage(source);
        stage(destination);

        pending_transfers_.push_back(
            Transfer{
                transfer_id,
                source_id,
                destination_id,
                amount_cents
            }
        );

        pending_ledger_.push_back(
            LedgerEntry{
                transfer_id,
                source_id,
                "DEBIT",
                amount_cents
            }
        );

        pending_ledger_.push_back(
            LedgerEntry{
                transfer_id,
                destination_id,
                "CREDIT",
                amount_cents
            }
        );

        store_.addAuditEvent(
            {
                id_,
                "STAGE_TRANSFER",
                "Transfer " + transfer_id + " staged"
            }
        );
    }

    void validateConsistency() const {
        ensureActive();

        for (const auto& [account_id, account] : staged_accounts_) {
            if (account.balance_cents < 0) {
                throw TransactionError(
                    "Negative balance for account " + account_id,
                    ErrorCode.ConsistencyFailure
                );
            }
        }

        for (const auto& transfer : pending_transfers_) {
            long long debit_total = 0;
            long long credit_total = 0;
            int debit_count = 0;
            int credit_count = 0;

            for (const auto& entry : pending_ledger_) {
                if (entry.transfer_id != transfer.id) {
                    continue;
                }

                if (entry.direction == "DEBIT") {
                    ++debit_count;
                    debit_total += entry.amount_cents;
                } else if (entry.direction == "CREDIT") {
                    ++credit_count;
                    credit_total += entry.amount_cents;
                }
            }

            if (
                debit_count != 1 ||
                credit_count != 1 ||
                debit_total != transfer.amount_cents ||
                credit_total != transfer.amount_cents
            ) {
                throw TransactionError(
                    "Double-entry ledger invariant failed",
                    ErrorCode.ConsistencyFailure
                );
            }
        }
    }

    void validateConcurrency() const {
        ensureActive();

        for (const auto& [account_id, original_version] : original_versions_) {
            const long long current = store_.currentVersion(account_id);

            if (current != original_version) {
                throw TransactionError(
                    "Optimistic concurrency conflict on " + account_id,
                    ErrorCode::SerializationConflict,
                    true
                );
            }
        }
    }

    void commit() {
        ensureActive();

        try {
            validateConsistency();
            validateConcurrency();

            for (const auto& transfer : pending_transfers_) {
                if (store_.hasTransfer(transfer.id)) {
                    throw TransactionError(
                        "Transfer was inserted by another transaction",
                        ErrorCode::DuplicateTransfer
                    );
                }
            }

            /*
             * The Store is updated only after every validation succeeds.
             * If a real database backed this class, this boundary corresponds
             * to the database transaction's commit operation.
             */
            for (const auto& [account_id, account] : staged_accounts_) {
                store_.applyAccount(account);
                store_.incrementVersion(account_id);
            }

            for (const auto& transfer : pending_transfers_) {
                store_.addTransfer(transfer);
            }

            for (const auto& entry : pending_ledger_) {
                store_.addLedgerEntry(entry);
            }

            state_ = TransactionState::Committed;

            store_.addAuditEvent(
                {id_, "COMMIT", "All staged mutations became visible"}
            );
        } catch (...) {
            rollback();
            throw;
        }
    }

    void rollback() {
        if (state_ == TransactionState::Committed) {
            throw TransactionError(
                "Committed transaction cannot be rolled back",
                ErrorCode::InvalidState
            );
        }

        if (state_ == TransactionState::Active) {
            staged_accounts_.clear();
            original_versions_.clear();
            pending_transfers_.clear();
            pending_ledger_.clear();

            state_ = TransactionState::RolledBack;

            store_.addAuditEvent(
                {id_, "ROLLBACK", "Staged mutations discarded"}
            );
        }
    }

    TransactionState state() const {
        return state_;
    }

private:
    void ensureActive() const {
        if (state_ != TransactionState::Active) {
            throw TransactionError(
                "Transaction is not active",
                ErrorCode::InvalidState
            );
        }
    }

    void stage(const Account& account) {
        if (account.balance_cents < 0) {
            throw TransactionError(
                "Cannot stage negative account balance",
                ErrorCode::NegativeBalance
            );
        }

        if (!original_versions_.contains(account.id)) {
            original_versions_[account.id] = account.version;
        }

        staged_accounts_[account.id] = account;
    }

    Store& store_;
    std::string id_;
    TransactionState state_;

    std::map<std::string, Account> staged_accounts_;
    std::map<std::string, long long> original_versions_;
    std::vector<Transfer> pending_transfers_;
    std::vector<LedgerEntry> pending_ledger_;
};

class IdempotencyRegistry {
public:
    bool contains(const std::string& key) const {
        return results_.contains(key);
    }

    std::string get(const std::string& key) const {
        auto it = results_.find(key);

        if (it == results_.end()) {
            throw std::out_of_range("Idempotency key not found");
        }

        return it->second;
    }

    void record(
        const std::string& key,
        const std::string& result
    ) {
        if (key.empty()) {
            throw std::invalid_argument("Idempotency key cannot be empty");
        }

        if (contains(key)) {
            throw TransactionError(
                "Idempotency key already recorded",
                ErrorCode::DuplicateTransfer
            );
        }

        results_[key] = result;
    }

private:
    std::unordered_map<std::string, std::string> results_;
};

class PaymentService {
public:
    explicit PaymentService(Store& store)
        : store_(store) {}

    void executeTransfer(
        const std::string& transaction_id,
        const std::string& transfer_id,
        const std::string& source,
        const std::string& destination,
        long long amount_cents
    ) {
        Transaction transaction(store_, transaction_id);
        transaction.begin();

        try {
            transaction.transfer(
                transfer_id,
                source,
                destination,
                amount_cents
            );

            transaction.commit();
        } catch (...) {
            if (transaction.state() == TransactionState::Active) {
                transaction.rollback();
            }

            throw;
        }
    }

private:
    Store& store_;
};

void printAccounts(const Store& store, const std::string& title) {
    std::cout << "\n--- " << title << " ---\n";

    for (const auto& [id, account] : store.accounts()) {
        std::cout
            << std::left
            << std::setw(8) << id
            << std::setw(10) << account.owner
            << std::right
            << std::fixed
            << std::setprecision(2)
            << static_cast<double>(account.balance_cents) / 100.0
            << " " << account.currency
            << " version=" << account.version
            << '\n';
    }
}

Store createSeedStore() {
    Store store;

    store.addAccount("A100", "Anika", "INR", 100000);
    store.addAccount("B200", "Rohan", "INR", 50000);
    store.addAccount("C300", "Meera", "INR", 75000);

    return store;
}

void demonstrateAtomicity() {
    std::cout << "\n=== Atomicity ===\n";

    Store store = createSeedStore();
    PaymentService service(store);

    const long long before_a = store.getAccount("A100").balance_cents;
    const long long before_b = store.getAccount("B200").balance_cents;

    try {
        Transaction transaction(store, "TX-ATOMIC-FAIL");
        transaction.begin();

        transaction.transfer(
            "TRANSFER-ATOMIC-FAIL",
            "A100",
            "B200",
            10000
        );

        // The failure occurs after both balance changes have been staged but
        // before commit. A rollback therefore removes the entire operation.
        throw std::runtime_error("Simulated application failure");
    } catch (const std::runtime_error& error) {
        std::cout << "Expected failure: " << error.what() << '\n';
    }

    assert(store.getAccount("A100").balance_cents == before_a);
    assert(store.getAccount("B200").balance_cents == before_b);
    assert(store.transfers().empty());

    std::cout
        << "No partial transfer escaped because staged state was never committed.\n";
}

void demonstrateConsistency() {
    std::cout << "\n=== Consistency ===\n";

    Store store = createSeedStore();
    PaymentService service(store);

    const long long before = store.totalBalance("INR");

    service.executeTransfer(
        "TX-CONSISTENCY",
        "TRANSFER-CONSISTENCY",
        "A100",
        "C300",
        12500
    );

    const long long after = store.totalBalance("INR");

    assert(before == after);
    assert(store.getAccount("A100").balance_cents == 87500);
    assert(store.getAccount("C300").balance_cents == 87500);

    std::cout
        << "Conservation invariant preserved: "
        << before << " cents before and "
        << after << " cents after.\n";
}

void demonstrateConstraintFailure() {
    std::cout << "\n=== Consistency Constraint Failure ===\n";

    Store store = createSeedStore();
    Transaction transaction(store, "TX-CONSTRAINT");
    transaction.begin();

    try {
        transaction.transfer(
            "TRANSFER-CONSTRAINT",
            "A100",
            "B200",
            200000
        );

        transaction.commit();
        assert(false);
    } catch (const TransactionError& error) {
        assert(error.code == ErrorCode::InsufficientFunds);
        std::cout
            << "Invalid transaction rejected: "
            << error.what() << '\n';

        if (transaction.state() == TransactionState::Active) {
            transaction.rollback();
        }
    }

    assert(store.getAccount("A100").balance_cents == 100000);
    assert(store.getAccount("B200").balance_cents == 50000);
}

void demonstrateIsolationAndOptimisticConcurrency() {
    std::cout << "\n=== Isolation and Optimistic Concurrency ===\n";

    Store store = createSeedStore();

    Transaction first(store, "TX-OCC-A");
    Transaction second(store, "TX-OCC-B");

    first.begin();
    second.begin();

    /*
     * Both transactions initially record version zero for A100. The first
     * transaction commits and increments A100's version. The second
     * transaction still has a stale version, so its commit is rejected.
     */
    first.transfer(
        "TRANSFER-OCC-A",
        "A100",
        "B200",
        10000
    );
    first.commit();

    try {
        second.transfer(
            "TRANSFER-OCC-B",
            "A100",
            "C300",
            5000
        );
        second.commit();
        assert(false);
    } catch (const TransactionError& error) {
        assert(error.code == ErrorCode::SerializationConflict);
        assert(error.retryable);

        std::cout
            << "Expected optimistic concurrency conflict: "
            << error.what() << '\n';

        if (second.state() == TransactionState::Active) {
            second.rollback();
        }
    }

    assert(store.getAccount("A100").balance_cents == 90000);
    assert(store.getAccount("B200").balance_cents == 60000);
    assert(store.getAccount("C300").balance_cents == 75000);
}

void demonstrateIdempotency() {
    std::cout << "\n=== Idempotency ===\n";

    Store store = createSeedStore();
    PaymentService service(store);
    IdempotencyRegistry registry;

    const std::string request_key = "payment-req-9e31";

    if (!registry.contains(request_key)) {
        service.executeTransfer(
            "TX-IDEMPOTENT",
            "TRANSFER-IDEMPOTENT",
            "A100",
            "B200",
            7500
        );

        registry.record(
            request_key,
            "TRANSFER-IDEMPOTENT:COMMITTED"
        );
    }

    /*
     * A retry caused by a lost response does not repeat the financial
     * mutation. The request key maps to the already committed result.
     */
    const std::string retry_result = registry.get(request_key);

    assert(retry_result == "TRANSFER-IDEMPOTENT:COMMITTED");
    assert(store.getAccount("A100").balance_cents == 92500);
    assert(store.getAccount("B200").balance_cents == 57500);

    std::cout
        << "Retry returned the original result: "
        << retry_result << '\n';
}

void demonstrateLedgerIntegrity() {
    std::cout << "\n=== Double-Entry Ledger Integrity ===\n";

    Store store = createSeedStore();
    PaymentService service(store);

    service.executeTransfer(
        "TX-LEDGER-1",
        "TRANSFER-LEDGER-1",
        "A100",
        "B200",
        4000
    );

    service.executeTransfer(
        "TX-LEDGER-2",
        "TRANSFER-LEDGER-2",
        "B200",
        "C300",
        2000
    );

    for (const auto& [transfer_id, transfer] : store.transfers()) {
        int debit_count = 0;
        int credit_count = 0;
        long long debit_total = 0;
        long long credit_total = 0;

        for (const auto& entry : store.ledger()) {
            if (entry.transfer_id != transfer_id) {
                continue;
            }

            if (entry.direction == "DEBIT") {
                ++debit_count;
                debit_total += entry.amount_cents;
            }

            if (entry.direction == "CREDIT") {
                ++credit_count;
                credit_total += entry.amount_cents;
            }
        }

        assert(debit_count == 1);
        assert(credit_count == 1);
        assert(debit_total == transfer.amount_cents);
        assert(credit_total == transfer.amount_cents);
    }

    std::cout
        << "Every committed transfer has exactly one balanced debit "
        << "and one matching credit.\n";
}

void demonstrateRetryClassification() {
    std::cout << "\n=== Retry Classification ===\n";

    Store store = createSeedStore();
    PaymentService service(store);

    int attempts = 0;
    bool committed = false;

    while (!committed && attempts < 3) {
        ++attempts;

        try {
            /*
             * The first two attempts simulate a transient serialization
             * conflict. Real systems should retry only errors known to be
             * safe to retry, and the operation should be idempotent.
             */
            if (attempts < 3) {
                throw TransactionError(
                    "Temporary serialization conflict",
                    ErrorCode::RetryableDependencyFailure,
                    true
                );
            }

            service.executeTransfer(
                "TX-RETRY",
                "TRANSFER-RETRY",
                "A100",
                "B200",
                2500
            );

            committed = true;
        } catch (const TransactionError& error) {
            if (!error.retryable || attempts >= 3) {
                throw;
            }

            std::cout
                << "Retryable failure on attempt "
                << attempts << ": "
                << error.what() << '\n';
        }
    }

    assert(committed);
    assert(attempts == 3);
    assert(store.getAccount("A100").balance_cents == 97500);

    std::cout << "Transaction committed after a bounded retry sequence.\n";
}

void demonstrateBusinessValidation() {
    std::cout << "\n=== Business Validation ===\n";

    Store store = createSeedStore();
    PaymentService service(store);

    struct InvalidCase {
        std::string name;
        std::string source;
        std::string destination;
        long long amount;
    };

    const std::vector<InvalidCase> cases = {
        {"negative amount", "A100", "B200", -100},
        {"zero amount", "A100", "B200", 0},
        {"same account", "A100", "A100", 100},
        {"insufficient funds", "A100", "B200", 999999},
    };

    for (const auto& test : cases) {
        try {
            service.executeTransfer(
                "TX-VALIDATION-" + test.name,
                "TRANSFER-" + test.name,
                test.source,
                test.destination,
                test.amount
            );

            assert(false);
        } catch (const TransactionError& error) {
            std::cout
                << test.name
                << ": rejected with code "
                << static_cast<int>(error.code)
                << '\n';
        }
    }

    assert(store.getAccount("A100").balance_cents == 100000);
    assert(store.getAccount("B200").balance_cents == 50000);
}

void demonstrateAuditTrail() {
    std::cout << "\n=== Transaction Audit Trail ===\n";

    Store store = createSeedStore();
    PaymentService service(store);

    service.executeTransfer(
        "TX-AUDIT",
        "TRANSFER-AUDIT",
        "A100",
        "C300",
        1000
    );

    const auto& events = store.audit();

    assert(events.size() >= 3);

    bool saw_begin = false;
    bool saw_stage = false;
    bool saw_commit = false;

    for (const auto& event : events) {
        if (event.transaction_id != "TX-AUDIT") {
            continue;
        }

        if (event.event == "BEGIN") {
            saw_begin = true;
        }

        if (event.event == "STAGE_TRANSFER") {
            saw_stage = true;
        }

        if (event.event == "COMMIT") {
            saw_commit = true;
        }
    }

    assert(saw_begin);
    assert(saw_stage);
    assert(saw_commit);

    std::cout
        << "Audit trail captured transaction lifecycle events.\n";
}

void demonstrateAtomicTransactionBoundary() {
    std::cout << "\n=== Atomic Transaction Boundary ===\n";

    Store store = createSeedStore();

    Transaction transaction(store, "TX-BOUNDARY");
    transaction.begin();

    try {
        transaction.transfer(
            "TRANSFER-BOUNDARY",
            "A100",
            "B200",
            5000
        );

        /*
         * In a real service this could represent a failure from another
         * required operation, such as a ledger publisher or fraud decision.
         * The important property is that the payment is not committed alone.
         */
        throw TransactionError(
            "Required downstream operation failed",
            ErrorCode::RetryableDependencyFailure,
            true
        );
    } catch (const TransactionError& error) {
        std::cout
            << "Boundary failure: "
            << error.what() << '\n';

        if (transaction.state() == TransactionState::Active) {
            transaction.rollback();
        }
    }

    assert(store.getAccount("A100").balance_cents == 100000);
    assert(store.getAccount("B200").balance_cents == 50000);
    assert(store.transfers().empty());

    std::cout
        << "The dependent financial operation remained uncommitted.\n";
}

int main() {
    try {
        demonstrateAtomicity();
        demonstrateConsistency();
        demonstrateConstraintFailure();
        demonstrateIsolationAndOptimisticConcurrency();
        demonstrateIdempotency();
        demonstrateLedgerIntegrity();
        demonstrateRetryClassification();
        demonstrateBusinessValidation();
        demonstrateAuditTrail();
        demonstrateAtomicTransactionBoundary();

        Store final_store = createSeedStore();
        PaymentService final_service(final_store);

        final_service.executeTransfer(
            "TX-FINAL",
            "TRANSFER-FINAL",
            "A100",
            "C300",
            10000
        );

        printAccounts(final_store, "Final Committed State");

        std::cout
            << "\n=== Case Study Complete ===\n"
            << "The payment engine demonstrated atomicity, consistency, "
            << "isolation, durability boundaries, optimistic concurrency, "
            << "idempotency, balanced ledger invariants, validation, "
            << "rollback, retry classification, and transaction "
            << "observability.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}
