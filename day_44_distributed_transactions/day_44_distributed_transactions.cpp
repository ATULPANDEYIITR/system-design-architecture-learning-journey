#include <algorithm>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

enum class ParticipantState {
    Active,
    Prepared,
    Committed,
    Aborted
};

enum class TransactionState {
    New,
    Preparing,
    CommitDecided,
    AbortDecided,
    Committed,
    Aborted,
    InDoubt
};

enum class Decision {
    Commit,
    Abort
};

std::string to_string(ParticipantState state) {
    switch (state) {
        case ParticipantState::Active: return "ACTIVE";
        case ParticipantState::Prepared: return "PREPARED";
        case ParticipantState::Committed: return "COMMITTED";
        case ParticipantState::Aborted: return "ABORTED";
    }
    throw std::logic_error("Invalid participant state");
}

std::string to_string(TransactionState state) {
    switch (state) {
        case TransactionState::New: return "NEW";
        case TransactionState::Preparing: return "PREPARING";
        case TransactionState::CommitDecided: return "COMMIT_DECIDED";
        case TransactionState::AbortDecided: return "ABORT_DECIDED";
        case TransactionState::Committed: return "COMMITTED";
        case TransactionState::Aborted: return "ABORTED";
        case TransactionState::InDoubt: return "IN_DOUBT";
    }
    throw std::logic_error("Invalid transaction state");
}

struct Vote {
    std::string participant;
    bool yes;
    std::string reason;
};

struct JournalRecord {
    std::string transaction_id;
    std::string event;
    std::string participant;
    std::string detail;
};

class Journal {
private:
    std::vector<JournalRecord> records_;

public:
    void append(
        const std::string& transaction_id,
        const std::string& event,
        const std::string& participant = "",
        const std::string& detail = ""
    ) {
        records_.push_back({transaction_id, event, participant, detail});
    }

    std::optional<Decision> decision(const std::string& transaction_id) const {
        for (auto it = records_.rbegin(); it != records_.rend(); ++it) {
            if (it->transaction_id != transaction_id) continue;
            if (it->event == "GLOBAL_COMMIT") return Decision::Commit;
            if (it->event == "GLOBAL_ABORT") return Decision::Abort;
        }
        return std::nullopt;
    }

    void print(const std::string& transaction_id) const {
        for (const auto& record : records_) {
            if (record.transaction_id != transaction_id) continue;
            std::cout << record.event;
            if (!record.participant.empty()) {
                std::cout << " participant=" << record.participant;
            }
            if (!record.detail.empty()) {
                std::cout << " detail=" << record.detail;
            }
            std::cout << '\n';
        }
    }
};

class Participant {
private:
    std::string id_;
    std::int64_t balance_;
    Journal& journal_;
    bool available_ = true;

    std::map<std::string, ParticipantState> states_;
    std::map<std::string, std::int64_t> reservations_;
    std::map<std::string, std::string> operation_ids_;

    void require_available() const {
        if (!available_) {
            throw std::runtime_error("Participant unavailable: " + id_);
        }
    }

public:
    Participant(std::string id, std::int64_t balance, Journal& journal)
        : id_(std::move(id)), balance_(balance), journal_(journal) {
        if (id_.empty()) throw std::invalid_argument("Participant ID is empty");
        if (balance_ < 0) throw std::invalid_argument("Negative opening balance");
    }

    const std::string& id() const {
        return id_;
    }

    std::int64_t balance() const {
        return balance_;
    }

    void set_available(bool value) {
        available_ = value;
    }

    ParticipantState state(const std::string& transaction_id) const {
        const auto it = states_.find(transaction_id);
        return it == states_.end() ? ParticipantState::Active : it->second;
    }

    Vote prepare(
        const std::string& transaction_id,
        const std::string& operation_id,
        std::int64_t delta
    ) {
        require_available();

        const auto existing = states_.find(transaction_id);
        if (existing != states_.end()) {
            if (existing->second == ParticipantState::Prepared) {
                if (operation_ids_.at(transaction_id) != operation_id) {
                    throw std::logic_error("Conflicting transaction retry");
                }
                return {id_, true, "Already prepared"};
            }
            if (existing->second == ParticipantState::Committed) {
                return {id_, true, "Already committed"};
            }
            if (existing->second == ParticipantState::Aborted) {
                return {id_, false, "Already aborted"};
            }
        }

        // Check overflow before adding an untrusted or externally supplied delta.
        if ((delta > 0 &&
             balance_ > std::numeric_limits<std::int64_t>::max() - delta) ||
            (delta < 0 &&
             balance_ < std::numeric_limits<std::int64_t>::min() - delta)) {
            journal_.append(transaction_id, "VOTE_NO", id_, "Integer overflow");
            return {id_, false, "Integer overflow"};
        }

        const std::int64_t projected = balance_ + delta;
        if (projected < 0) {
            journal_.append(transaction_id, "VOTE_NO", id_, "Insufficient funds");
            return {id_, false, "Insufficient funds"};
        }

        // A real participant must durably persist PREPARED before voting YES.
        reservations_[transaction_id] = delta;
        operation_ids_[transaction_id] = operation_id;
        states_[transaction_id] = ParticipantState::Prepared;
        journal_.append(transaction_id, "PREPARED", id_, std::to_string(delta));

        return {id_, true, "Prepared"};
    }

    void commit(const std::string& transaction_id) {
        require_available();

        const auto current = state(transaction_id);
        if (current == ParticipantState::Committed) return;
        if (current != ParticipantState::Prepared) {
            throw std::logic_error("Commit requires PREPARED state");
        }

        // The caller must have read a durable global COMMIT decision.
        balance_ += reservations_.at(transaction_id);
        reservations_.erase(transaction_id);
        states_[transaction_id] = ParticipantState::Committed;
        journal_.append(
            transaction_id, "PARTICIPANT_COMMIT", id_, std::to_string(balance_)
        );
    }

    void abort(const std::string& transaction_id) {
        require_available();

        const auto current = state(transaction_id);
        if (current == ParticipantState::Aborted) return;
        if (current == ParticipantState::Committed) {
            throw std::logic_error("Cannot abort committed work");
        }

        reservations_.erase(transaction_id);
        states_[transaction_id] = ParticipantState::Aborted;
        journal_.append(transaction_id, "PARTICIPANT_ABORT", id_);
    }

    void apply_decision(const std::string& transaction_id, Decision decision) {
        if (decision == Decision::Commit) {
            commit(transaction_id);
        } else {
            abort(transaction_id);
        }
    }
};

struct Transaction {
    std::string id;
    std::string operation_id;
    TransactionState state = TransactionState::New;
    std::vector<std::string> participant_ids;
    std::map<std::string, bool> votes;
    std::optional<Decision> decision;
};

class GovernanceEngine {
private:
    Journal journal_;
    std::map<std::string, Participant*> participants_;
    std::map<std::string, Transaction> transactions_;
    std::uint64_t sequence_ = 0;

    std::string next_id(const std::string& prefix) {
        return prefix + "-" + std::to_string(++sequence_);
    }

public:
    void register_participant(Participant& participant) {
        if (participants_.count(participant.id())) {
            throw std::invalid_argument("Duplicate participant");
        }
        participants_[participant.id()] = &participant;
    }

    TransactionState execute(
        const std::map<std::string, std::int64_t>& deltas
    ) {
        if (deltas.empty()) throw std::invalid_argument("No participants");

        for (const auto& [id, delta] : deltas) {
            (void)delta;
            if (!participants_.count(id)) {
                throw std::invalid_argument("Unknown participant: " + id);
            }
        }

        Transaction tx;
        tx.id = next_id("transaction");
        tx.operation_id = next_id("operation");

        for (const auto& [id, delta] : deltas) {
            (void)delta;
            tx.participant_ids.push_back(id);
        }

        transactions_[tx.id] = tx;
        journal_.append(tx.id, "BEGIN", "", tx.operation_id);
        transactions_[tx.id].state = TransactionState::Preparing;
        journal_.append(tx.id, "PREPARING");

        bool all_yes = true;

        for (const auto& [id, delta] : deltas) {
            try {
                Vote vote = participants_.at(id)->prepare(
                    tx.id, tx.operation_id, delta
                );
                transactions_[tx.id].votes[id] = vote.yes;
                journal_.append(
                    tx.id, "VOTE", id, vote.yes ? "YES" : "NO: " + vote.reason
                );

                if (!vote.yes) {
                    all_yes = false;
                    break;
                }
            } catch (const std::exception& error) {
                transactions_[tx.id].votes[id] = false;
                journal_.append(tx.id, "VOTE_UNAVAILABLE", id, error.what());
                all_yes = false;
                break;
            }
        }

        Transaction& active = transactions_.at(tx.id);

        if (all_yes && active.votes.size() == deltas.size()) {
            // The global decision is recorded before any participant commits.
            journal_.append(tx.id, "GLOBAL_COMMIT");
            active.decision = Decision::Commit;
            active.state = TransactionState::CommitDecided;
        } else {
            journal_.append(tx.id, "GLOBAL_ABORT", "", "Vote failed");
            active.decision = Decision::Abort;
            active.state = TransactionState::AbortDecided;
        }

        bool delivery_failed = false;
        for (const auto& participant_id : active.participant_ids) {
            try {
                participants_.at(participant_id)->apply_decision(
                    tx.id, *active.decision
                );
            } catch (const std::exception& error) {
                journal_.append(
                    tx.id, "DECISION_DELIVERY_FAILED", participant_id, error.what()
                );
                delivery_failed = true;
            }
        }

        if (delivery_failed) {
            active.state = TransactionState::InDoubt;
        } else {
            active.state = *active.decision == Decision::Commit
                ? TransactionState::Committed
                : TransactionState::Aborted;
            journal_.append(tx.id, "TRANSACTION_COMPLETE");
        }

        return active.state;
    }

    TransactionState recover(const std::string& transaction_id) {
        auto tx_it = transactions_.find(transaction_id);
        if (tx_it == transactions_.end()) {
            throw std::invalid_argument("Unknown transaction");
        }

        const auto global_decision = journal_.decision(transaction_id);
        if (!global_decision) {
            tx_it->second.state = TransactionState::InDoubt;
            return tx_it->second.state;
        }

        for (const auto& participant_id : tx_it->second.participant_ids) {
            participants_.at(participant_id)->apply_decision(
                transaction_id, *global_decision
            );
        }

        tx_it->second.decision = global_decision;
        tx_it->second.state = *global_decision == Decision::Commit
            ? TransactionState::Committed
            : TransactionState::Aborted;

        journal_.append(transaction_id, "RECOVERY_COMPLETE");
        return tx_it->second.state;
    }

    const Transaction& transaction(const std::string& id) const {
        return transactions_.at(id);
    }

    void print_journal(const std::string& id) const {
        journal_.print(id);
    }
};

void print_account(const Participant& participant) {
    std::cout << participant.id()
              << " balance=" << participant.balance() << '\n';
}

void successful_settlement_case() {
    std::cout << "\n=== Marketplace settlement ===\n";

    GovernanceEngine engine;
    Participant buyer("buyer-account", 800, *new Journal());
    // Keep one shared journal for every participant in a real deployment.
    // The engine uses its own decision journal; participant journals would
    // normally be independently durable and correlated by transaction ID.

    Journal shared;
    Participant buyer_account("buyer", 800, shared);
    Participant seller_account("seller", 200, shared);
    Participant platform_fee("platform", 0, shared);

    GovernanceEngine settlement;
    settlement.register_participant(buyer_account);
    settlement.register_participant(seller_account);
    settlement.register_participant(platform_fee);

    const auto state = settlement.execute({
        {"buyer", -120},
        {"seller", 110},
        {"platform", 10}
    });

    std::cout << "Transaction state: " << to_string(state) << '\n';
    print_account(buyer_account);
    print_account(seller_account);
    print_account(platform_fee);

    if (state != TransactionState::Committed ||
        buyer_account.balance() + seller_account.balance() +
            platform_fee.balance() != 1000) {
        throw std::runtime_error("Settlement invariant failed");
    }

    (void)engine;
    (void)buyer;
}

void insufficient_funds_case() {
    std::cout << "\n=== Insufficient funds ===\n";

    Journal journal;
    GovernanceEngine engine;
    Participant account("customer", 30, journal);
    Participant merchant("merchant", 0, journal);

    engine.register_participant(account);
    engine.register_participant(merchant);

    const auto state = engine.execute({
        {"customer", -70},
        {"merchant", 70}
    });

    std::cout << "Transaction state: " << to_string(state) << '\n';
    print_account(account);
    print_account(merchant);

    if (state != TransactionState::Aborted ||
        account.balance() != 30 || merchant.balance() != 0) {
        throw std::runtime_error("Abort invariant failed");
    }
}

void recovery_case() {
    std::cout << "\n=== Recovery from unavailable participant ===\n";

    Journal journal;
    GovernanceEngine engine;
    Participant inventory("inventory", 60, journal);
    Participant dispatch("dispatch", 0, journal);

    engine.register_participant(inventory);
    engine.register_participant(dispatch);
    dispatch.set_available(false);

    const auto state = engine.execute({
        {"inventory", -4},
        {"dispatch", 4}
    });

    std::cout << "Initial state: " << to_string(state) << '\n';
    dispatch.set_available(true);

    // In this scenario the coordinator has recorded ABORT. Recovery retries
    // delivery instead of guessing from the participant's current balance.
    const auto recovered = engine.recover("transaction-1");
    std::cout << "Recovered state: " << to_string(recovered) << '\n';
    print_account(inventory);
    print_account(dispatch);

    if (recovered != TransactionState::Aborted ||
        inventory.balance() != 60 || dispatch.balance() != 0) {
        throw std::runtime_error("Recovery invariant failed");
    }
}

int main() {
    try {
        successful_settlement_case();
        insufficient_funds_case();
        recovery_case();
        std::cout << "\nAll governance-engine checks passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Failure: " << error.what() << '\n';
        return 1;
    }
}
