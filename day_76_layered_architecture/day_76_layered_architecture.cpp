/*
 * Layered Architecture: Repository Governance and Order Processing
 *
 * Presentation Layer:
 *   Command input and formatted output
 *
 * Application Layer:
 *   Use-case orchestration and eligibility evaluation
 *
 * Domain Layer:
 *   Order aggregates, policies, invariants, state transitions
 *
 * Infrastructure Layer:
 *   Repository implementation and audit persistence
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic layered.cpp -o layered
 *
 * Execute:
 *   ./layered
 */

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

// ============================================================
// DOMAIN LAYER
// ============================================================

namespace Domain {

enum class OrderStatus {
    Pending,
    Confirmed,
    Cancelled
};

enum class CheckStatus {
    Pending,
    Passed,
    Failed
};

enum class MergeStrategy {
    MergeCommit,
    Squash,
    Rebase
};

class DomainError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ValidationError : public DomainError {
public:
    using DomainError::DomainError;
};

class StateError : public DomainError {
public:
    using DomainError::DomainError;
};

struct OrderItem {
    std::string productId;
    std::string name;
    int quantity;
    std::int64_t unitPriceCents;

    OrderItem(
        std::string id,
        std::string product,
        int count,
        std::int64_t price
    ) : productId(std::move(id)),
        name(std::move(product)),
        quantity(count),
        unitPriceCents(price) {

        if (productId.empty() || name.empty()) {
            throw ValidationError("Product fields cannot be empty.");
        }

        if (quantity <= 0 || unitPriceCents <= 0) {
            throw ValidationError("Invalid item quantity or price.");
        }
    }

    std::int64_t subtotal() const {
        if (unitPriceCents >
            INT64_MAX / quantity) {
            throw ValidationError("Item subtotal overflow.");
        }

        return unitPriceCents * quantity;
    }
};

class Order {
private:
    std::string id_;
    std::string customerId_;
    std::vector<OrderItem> items_;
    OrderStatus status_;
    std::uint64_t version_;

public:
    Order(
        std::string id,
        std::string customerId,
        std::vector<OrderItem> items
    ) :
        id_(std::move(id)),
        customerId_(std::move(customerId)),
        items_(std::move(items)),
        status_(OrderStatus::Pending),
        version_(0) {

        if (id_.empty() || customerId_.empty() || items_.empty()) {
            throw ValidationError("Invalid order aggregate.");
        }

        std::set<std::string> productIds;

        for (const auto& item : items_) {
            if (!productIds.insert(item.productId).second) {
                throw ValidationError("Duplicate products are prohibited.");
            }
        }
    }

    const std::string& id() const {
        return id_;
    }

    const std::string& customerId() const {
        return customerId_;
    }

    OrderStatus status() const {
        return status_;
    }

    std::uint64_t version() const {
        return version_;
    }

    const std::vector<OrderItem>& items() const {
        return items_;
    }

    std::int64_t total() const {
        std::int64_t result = 0;

        for (const auto& item : items_) {
            const auto amount = item.subtotal();

            if (result > INT64_MAX - amount) {
                throw ValidationError("Order total overflow.");
            }

            result += amount;
        }

        return result;
    }

    void confirm() {
        if (status_ != OrderStatus::Pending) {
            throw StateError("Only pending orders can be confirmed.");
        }

        status_ = OrderStatus::Confirmed;
        ++version_;
    }

    void cancel() {
        if (status_ != OrderStatus::Pending) {
            throw StateError("Only pending orders can be cancelled.");
        }

        status_ = OrderStatus::Cancelled;
        ++version_;
    }
};

// Repository governance is another domain model demonstrating
// separation of policy from application orchestration.

enum class ReviewState {
    Pending,
    Approved,
    ChangesRequested,
    Dismissed
};

struct Review {
    std::string reviewer;
    ReviewState state;
    bool eligible;
    bool stale;
};

struct PullRequest {
    int id;
    std::string sourceBranch;
    std::string targetBranch;
    bool draft = false;
    bool open = true;
    bool conversationsResolved = false;
    bool conflicts = false;
    bool baseSynchronized = true;
    std::vector<Review> reviews;
    std::map<std::string, CheckStatus> checks;
};

struct BranchProtection {
    std::string branch;
    int requiredApprovals = 1;
    bool requireChecks = true;
    bool requireResolvedConversations = true;
    bool restrictDirectPush = true;
    bool restrictForcePush = true;
    bool restrictDeletion = true;
    bool requireLinearHistory = false;
    bool allowAdministratorBypass = false;
    std::set<std::string> requiredChecks;
};

struct EligibilityResult {
    bool eligible = false;
    std::vector<std::string> reasons;
};

class MergePolicy {
public:
    static EligibilityResult evaluate(
        const PullRequest& pr,
        const BranchProtection& policy
    ) {
        EligibilityResult result;

        if (!pr.open) {
            result.reasons.push_back("Pull Request is closed.");
        }

        if (pr.draft) {
            result.reasons.push_back("Draft Pull Requests cannot merge.");
        }

        if (pr.targetBranch != policy.branch) {
            result.reasons.push_back("Target branch policy mismatch.");
        }

        if (pr.sourceBranch == pr.targetBranch) {
            result.reasons.push_back("Source and target must differ.");
        }

        if (pr.conflicts) {
            result.reasons.push_back("Merge conflicts exist.");
        }

        if (!pr.baseSynchronized) {
            result.reasons.push_back("Source branch is outdated.");
        }

        if (
            policy.requireResolvedConversations &&
            !pr.conversationsResolved
        ) {
            result.reasons.push_back(
                "Review conversations remain unresolved."
            );
        }

        int approvals = 0;

        for (const auto& review : pr.reviews) {
            if (!review.eligible || review.stale) {
                continue;
            }

            if (review.state == ReviewState::ChangesRequested) {
                result.reasons.push_back(
                    "An eligible reviewer requested changes."
                );
            }

            if (review.state == ReviewState::Approved) {
                ++approvals;
            }
        }

        if (approvals < policy.requiredApprovals) {
            result.reasons.push_back("Insufficient valid approvals.");
        }

        if (policy.requireChecks) {
            for (const auto& required : policy.requiredChecks) {
                auto it = pr.checks.find(required);

                if (it == pr.checks.end()) {
                    result.reasons.push_back(
                        "Missing required check: " + required
                    );
                } else if (it->second != CheckStatus::Passed) {
                    result.reasons.push_back(
                        "Required check not passed: " + required
                    );
                }
            }
        }

        result.eligible = result.reasons.empty();

        return result;
    }
};

} // namespace Domain

// ============================================================
// INFRASTRUCTURE LAYER
// ============================================================

namespace Infrastructure {

class OrderRepository {
public:
    virtual ~OrderRepository() = default;

    virtual void save(const Domain::Order& order) = 0;

    virtual std::optional<Domain::Order> find(
        const std::string& id
    ) const = 0;
};

class InMemoryOrderRepository final : public OrderRepository {
private:
    std::map<std::string, Domain::Order> orders_;

public:
    void save(const Domain::Order& order) override {
        auto existing = orders_.find(order.id());

        if (
            existing != orders_.end() &&
            order.version() < existing->second.version()
        ) {
            throw Domain::StateError("Stale aggregate version.");
        }

        orders_.insert_or_assign(order.id(), order);
    }

    std::optional<Domain::Order> find(
        const std::string& id
    ) const override {
        auto it = orders_.find(id);

        if (it == orders_.end()) {
            return std::nullopt;
        }

        return it->second;
    }
};

class AuditLogger {
private:
    std::string filePath_;

public:
    explicit AuditLogger(std::string filePath)
        : filePath_(std::move(filePath)) {}

    void record(const std::string& event) const {
        std::ofstream file(filePath_, std::ios::app);

        if (!file) {
            throw std::runtime_error("Unable to open audit file.");
        }

        file << event << '\n';

        if (!file) {
            throw std::runtime_error("Audit write failed.");
        }
    }
};

} // namespace Infrastructure

// ============================================================
// APPLICATION LAYER
// ============================================================

namespace Application {

class OrderService {
private:
    Infrastructure::OrderRepository& repository_;
    const Infrastructure::AuditLogger& audit_;

public:
    OrderService(
        Infrastructure::OrderRepository& repository,
        const Infrastructure::AuditLogger& audit
    ) : repository_(repository), audit_(audit) {}

    void create(const Domain::Order& order) {
        if (repository_.find(order.id())) {
            throw Domain::StateError("Order already exists.");
        }

        repository_.save(order);
        audit_.record("ORDER_CREATED " + order.id());
    }

    void confirm(const std::string& id) {
        auto optionalOrder = repository_.find(id);

        if (!optionalOrder) {
            throw Domain::ValidationError("Order not found.");
        }

        auto order = *optionalOrder;
        order.confirm();

        repository_.save(order);
        audit_.record("ORDER_CONFIRMED " + id);
    }

    void cancel(const std::string& id) {
        auto optionalOrder = repository_.find(id);

        if (!optionalOrder) {
            throw Domain::ValidationError("Order not found.");
        }

        auto order = *optionalOrder;
        order.cancel();

        repository_.save(order);
        audit_.record("ORDER_CANCELLED " + id);
    }

    Domain::EligibilityResult evaluatePullRequest(
        const Domain::PullRequest& pr,
        const Domain::BranchProtection& protection
    ) const {
        return Domain::MergePolicy::evaluate(pr, protection);
    }
};

} // namespace Application

// ============================================================
// PRESENTATION LAYER
// ============================================================

namespace Presentation {

class Console {
public:
    static std::string formatMoney(std::int64_t cents) {
        std::ostringstream output;

        output << "$"
               << cents / 100
               << "."
               << std::setw(2)
               << std::setfill('0')
               << cents % 100;

        return output.str();
    }

    static void displayEligibility(
        const Domain::EligibilityResult& result
    ) {
        std::cout
            << "\nMerge eligibility: "
            << (result.eligible ? "ELIGIBLE" : "BLOCKED")
            << '\n';

        for (const auto& reason : result.reasons) {
            std::cout << " - " << reason << '\n';
        }
    }

    static void displayOrder(const Domain::Order& order) {
        std::cout << "\nOrder ID: " << order.id()
                  << "\nCustomer: " << order.customerId()
                  << "\nTotal: " << formatMoney(order.total())
                  << "\nVersion: " << order.version()
                  << '\n';
    }
};

} // namespace Presentation

// ============================================================
// TESTING AND EXECUTION
// ============================================================

void testOrderWorkflow() {
    Infrastructure::InMemoryOrderRepository repository;
    Infrastructure::AuditLogger audit("layered-audit.log");

    Application::OrderService service(repository, audit);

    Domain::Order order(
        "ORDER-001",
        "CUSTOMER-001",
        {
            Domain::OrderItem("P1", "Laptop", 2, 7500000),
            Domain::OrderItem("P2", "Mouse", 3, 120000)
        }
    );

    service.create(order);

    auto stored = repository.find("ORDER-001");

    if (!stored || stored->total() != 7860000) {
        throw std::runtime_error("Order persistence test failed.");
    }

    service.confirm("ORDER-001");

    auto confirmed = repository.find("ORDER-001");

    if (
        !confirmed ||
        confirmed->status() != Domain::OrderStatus::Confirmed
    ) {
        throw std::runtime_error("Confirmation test failed.");
    }

    try {
        service.cancel("ORDER-001");
        throw std::runtime_error("Invalid cancellation was accepted.");
    } catch (const Domain::StateError&) {
        // Expected state-transition rejection.
    }
}

void testGovernanceEngine() {
    Infrastructure::InMemoryOrderRepository repository;
    Infrastructure::AuditLogger audit("layered-audit.log");
    Application::OrderService service(repository, audit);

    Domain::BranchProtection protection;

    protection.branch = "main";
    protection.requiredApprovals = 2;
    protection.requiredChecks = {
        "build",
        "unit-tests",
        "security-scan"
    };

    Domain::PullRequest pr;

    pr.id = 101;
    pr.sourceBranch = "feature/order-api";
    pr.targetBranch = "main";
    pr.conversationsResolved = true;
    pr.baseSynchronized = true;

    pr.reviews = {
        {"reviewer-a", Domain::ReviewState::Approved, true, false},
        {"reviewer-b", Domain::ReviewState::Approved, true, false}
    };

    pr.checks = {
        {"build", Domain::CheckStatus::Passed},
        {"unit-tests", Domain::CheckStatus::Passed},
        {"security-scan", Domain::CheckStatus::Passed}
    };

    auto eligible = service.evaluatePullRequest(pr, protection);

    if (!eligible.eligible) {
        throw std::runtime_error("Valid Pull Request was rejected.");
    }

    pr.checks["security-scan"] = Domain::CheckStatus::Failed;

    auto blocked = service.evaluatePullRequest(pr, protection);

    if (blocked.eligible) {
        throw std::runtime_error("Failed security check was accepted.");
    }

    Presentation::displayEligibility(blocked);
}

int main() {
    try {
        testOrderWorkflow();
        testGovernanceEngine();

        std::cout << "\nOrder workflow tests passed.\n";
        std::cout << "Governance tests passed.\n";

        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Application error: "
                  << error.what() << '\n';

        return 1;
    }
}
