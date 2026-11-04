#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class Module {
    USERS,
    CATALOG,
    INVENTORY,
    ORDERS,
    PAYMENTS
};

enum class OrderStatus {
    CREATED,
    PAID,
    REJECTED
};

enum class CheckStatus {
    PASS,
    FAIL
};

enum class MergePolicy {
    ATOMIC_ORDER_PROCESSING,
    ALLOW_PARTIAL_OPERATIONS
};

struct Product {
    int id;
    string name;
    double price;
    int stock;
};

struct User {
    int id;
    string email;
};

struct Order {
    int id;
    int userId;
    int productId;
    int quantity;
    double total;
    OrderStatus status;
};

struct StatusCheck {
    string name;
    CheckStatus status;
};

struct BranchProtection {
    bool protectedBranch = true;
    bool requireReviews = true;
    bool requireBuild = true;
    bool prohibitDirectPush = true;
    bool prohibitForcePush = true;
    bool prohibitDeletion = true;
    bool requireLinearHistory = false;
    int requiredApprovals = 1;
};

struct PullRequest {
    int id;
    string sourceBranch;
    string targetBranch;
    bool open = true;
    bool draft = false;
    bool conversationsResolved = true;
    bool sourceUpToDate = true;
    int approvalCount = 0;
    vector<StatusCheck> checks;
};

struct EligibilityResult {
    bool eligible;
    vector<string> reasons;
};

class MonolithDatabase {
public:
    map<int, User> users;
    map<int, Product> products;
    map<int, Order> orders;
    map<int, double> payments;

    struct Snapshot {
        map<int, Product> products;
        map<int, Order> orders;
        map<int, double> payments;
    };

    Snapshot snapshot() const {
        return {products, orders, payments};
    }

    void restore(const Snapshot& snapshot) {
        products = snapshot.products;
        orders = snapshot.orders;
        payments = snapshot.payments;
    }
};

class InventoryModule {
private:
    MonolithDatabase& database;

public:
    explicit InventoryModule(MonolithDatabase& db) : database(db) {}

    void addProduct(Product product) {
        if (product.id <= 0 || product.name.empty() ||
            !isfinite(product.price) || product.price < 0 ||
            product.stock < 0) {
            throw invalid_argument("Invalid product");
        }

        if (database.products.count(product.id)) {
            throw invalid_argument("Duplicate product");
        }

        database.products.emplace(product.id, move(product));
    }

    double reserve(int productId, int quantity) {
        if (quantity <= 0) {
            throw invalid_argument("Quantity must be positive");
        }

        auto iterator = database.products.find(productId);

        if (iterator == database.products.end()) {
            throw runtime_error("Product not found");
        }

        if (iterator->second.stock < quantity) {
            throw runtime_error("Insufficient stock");
        }

        iterator->second.stock -= quantity;
        return iterator->second.price * quantity;
    }
};

class PaymentModule {
private:
    MonolithDatabase& database;
    bool providerAvailable = true;

public:
    explicit PaymentModule(MonolithDatabase& db) : database(db) {}

    void setProviderAvailable(bool available) {
        providerAvailable = available;
    }

    bool charge(int orderId, double amount) {
        if (!isfinite(amount) || amount <= 0) {
            throw invalid_argument("Invalid payment amount");
        }

        if (database.payments.count(orderId)) {
            return true;
        }

        if (!providerAvailable) {
            throw runtime_error("Payment provider unavailable");
        }

        database.payments[orderId] = amount;
        return true;
    }
};

class OrderModule {
private:
    MonolithDatabase& database;
    InventoryModule& inventory;
    PaymentModule& payments;
    int nextOrderId = 1;

public:
    OrderModule(
        MonolithDatabase& db,
        InventoryModule& inv,
        PaymentModule& pay
    ) : database(db), inventory(inv), payments(pay) {}

    Order create(int userId, int productId, int quantity) {
        if (!database.users.count(userId)) {
            throw runtime_error("Unknown user");
        }

        // Save application state so payment failure cannot consume stock.
        const auto snapshot = database.snapshot();

        try {
            const double total = inventory.reserve(productId, quantity);

            Order order{
                nextOrderId++,
                userId,
                productId,
                quantity,
                total,
                OrderStatus::CREATED
            };

            database.orders[order.id] = order;

            payments.charge(order.id, total);

            order.status = OrderStatus::PAID;
            database.orders[order.id] = order;

            return order;

        } catch (...) {
            database.restore(snapshot);
            throw;
        }
    }
};

class GovernanceEngine {
private:
    BranchProtection policy;

public:
    explicit GovernanceEngine(BranchProtection protection)
        : policy(protection) {
        if (policy.requiredApprovals < 0) {
            throw invalid_argument("Invalid approval requirement");
        }
    }

    EligibilityResult evaluate(const PullRequest& pr) const {
        EligibilityResult result{true, {}};

        auto reject = [&](const string& reason) {
            result.eligible = false;
            result.reasons.push_back(reason);
        };

        if (!pr.open) reject("Pull Request is closed");
        if (pr.draft) reject("Draft Pull Request cannot merge");
        if (pr.sourceBranch.empty() || pr.targetBranch.empty()) {
            reject("Source and target branches are required");
        }
        if (pr.sourceBranch == pr.targetBranch) {
            reject("Source and target branches must differ");
        }
        if (policy.protectedBranch && !pr.sourceUpToDate) {
            reject("Source branch must be synchronized");
        }
        if (policy.requireReviews &&
            pr.approvalCount < policy.requiredApprovals) {
            reject("Required approvals are missing");
        }
        if (!pr.conversationsResolved) {
            reject("Review conversations remain unresolved");
        }

        bool buildFound = false;

        for (const auto& check : pr.checks) {
            if (check.name == "build") {
                buildFound = true;
                if (check.status == CheckStatus::FAIL) {
                    reject("Build check failed");
                }
            }

            if (check.status == CheckStatus::FAIL) {
                reject("A required status check failed: " + check.name);
            }
        }

        if (policy.requireBuild && !buildFound) {
            reject("Required build check is missing");
        }

        return result;
    }

    bool merge(
        PullRequest& pr,
        vector<string>& targetCommits
    ) const {
        const auto eligibility = evaluate(pr);

        if (!eligibility.eligible) {
            cout << "Merge rejected:\n";
            for (const auto& reason : eligibility.reasons) {
                cout << "  - " << reason << '\n';
            }
            return false;
        }

        if (policy.requireLinearHistory) {
            set<string> uniqueCommits(
                targetCommits.begin(),
                targetCommits.end()
            );

            if (uniqueCommits.size() != targetCommits.size()) {
                cout << "Merge rejected: duplicate commit history\n";
                return false;
            }
        }

        targetCommits.push_back("merged-pr-" + to_string(pr.id));
        pr.open = false;

        cout << "Pull Request #" << pr.id << " merged successfully.\n";
        return true;
    }

    bool allowDirectPush(bool isAdministrator) const {
        if (!policy.protectedBranch) return true;
        if (isAdministrator && !policy.prohibitDirectPush) return true;
        return !policy.prohibitDirectPush;
    }

    bool allowForcePush(bool isAdministrator) const {
        if (!policy.protectedBranch) return true;
        if (isAdministrator && !policy.prohibitForcePush) return true;
        return !policy.prohibitForcePush;
    }

    bool allowBranchDeletion(bool isAdministrator) const {
        if (!policy.protectedBranch) return true;
        if (isAdministrator && !policy.prohibitDeletion) return true;
        return !policy.prohibitDeletion;
    }
};

void demonstrateMonolith() {
    cout << "MONOLITH BUSINESS APPLICATION\n";
    cout << "=============================\n";

    MonolithDatabase database;
    InventoryModule inventory(database);
    PaymentModule payments(database);
    OrderModule orders(database, inventory, payments);

    database.users.emplace(
        1,
        User{1, "customer@example.com"}
    );

    inventory.addProduct(
        Product{101, "Enterprise Database Server", 5000.0, 15}
    );

    cout << "\nSuccessful order:\n";

    const Order order = orders.create(1, 101, 3);

    cout << "Order ID: " << order.id << '\n';
    cout << "Total: " << order.total << '\n';
    cout << "Status: "
         << (order.status == OrderStatus::PAID ? "PAID" : "FAILED")
         << '\n';

    cout << "Remaining stock: "
         << database.products.at(101).stock << '\n';

    cout << "\nPayment failure test:\n";

    payments.setProviderAvailable(false);

    try {
        orders.create(1, 101, 2);
    } catch (const exception& error) {
        cout << error.what() << '\n';
    }

    cout << "Stock after rollback: "
         << database.products.at(101).stock << '\n';
}

void demonstrateGovernance() {
    cout << "\nREPOSITORY GOVERNANCE ENGINE\n";
    cout << "============================\n";

    BranchProtection policy;
    policy.requiredApprovals = 2;
    policy.requireReviews = true;
    policy.requireBuild = true;
    policy.prohibitDirectPush = true;
    policy.prohibitForcePush = true;
    policy.prohibitDeletion = true;

    GovernanceEngine engine(policy);

    PullRequest pr{
        42,
        "feature/database-cache",
        "main",
        true,
        false,
        true,
        true,
        1,
        {
            {"build", CheckStatus::PASS},
            {"unit-tests", CheckStatus::PASS},
            {"security-scan", CheckStatus::PASS}
        }
    };

    vector<string> targetCommits = {
        "commit-a1",
        "commit-a2"
    };

    auto initial = engine.evaluate(pr);

    cout << "\nInitial eligibility: "
         << (initial.eligible ? "ELIGIBLE" : "BLOCKED")
         << '\n';

    for (const auto& reason : initial.reasons) {
        cout << "Reason: " << reason << '\n';
    }

    cout << "\nSecond approval recorded.\n";
    pr.approvalCount = 2;

    auto updated = engine.evaluate(pr);

    cout << "Updated eligibility: "
         << (updated.eligible ? "ELIGIBLE" : "BLOCKED")
         << '\n';

    engine.merge(pr, targetCommits);

    cout << "Target branch commit count: "
         << targetCommits.size() << '\n';

    cout << "\nRepository controls:\n";
    cout << "Direct push: "
         << (engine.allowDirectPush(false) ? "Allowed" : "Blocked")
         << '\n';

    cout << "Force push: "
         << (engine.allowForcePush(false) ? "Allowed" : "Blocked")
         << '\n';

    cout << "Branch deletion: "
         << (engine.allowBranchDeletion(false) ? "Allowed" : "Blocked")
         << '\n';
}

int main() {
    try {
        demonstrateMonolith();
        demonstrateGovernance();

        cout << "\nAll scenarios completed.\n";
        return 0;

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}
