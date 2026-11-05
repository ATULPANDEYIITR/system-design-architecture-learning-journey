#include <algorithm>
#include <cstdint>
#include <exception>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;

// ============================================================
// DOMAIN ERRORS
// ============================================================

class DomainError : public runtime_error {
public:
    explicit DomainError(const string& message)
        : runtime_error(message) {}
};

class ValidationError : public DomainError {
public:
    using DomainError::DomainError;
};

class NotFoundError : public DomainError {
public:
    using DomainError::DomainError;
};

class InsufficientStockError : public DomainError {
public:
    using DomainError::DomainError;
};

// ============================================================
// SHARED DOMAIN TYPES
// ============================================================

enum class OrderStatus {
    Pending,
    Confirmed,
    Cancelled
};

enum class PaymentStatus {
    Authorized,
    Refunded
};

string toString(OrderStatus status) {
    switch (status) {
        case OrderStatus::Pending: return "PENDING";
        case OrderStatus::Confirmed: return "CONFIRMED";
        case OrderStatus::Cancelled: return "CANCELLED";
    }

    throw ValidationError("Unknown order status.");
}

string toString(PaymentStatus status) {
    switch (status) {
        case PaymentStatus::Authorized: return "AUTHORIZED";
        case PaymentStatus::Refunded: return "REFUNDED";
    }

    throw ValidationError("Unknown payment status.");
}

void validateId(const string& id, const string& field) {
    if (id.empty() || id.find_first_not_of(" \t\n") == string::npos) {
        throw ValidationError(field + " is required.");
    }
}

// ============================================================
// INVENTORY MODULE
// ============================================================

struct Product {
    string id;
    string name;
    int64_t priceInCents;
    int stock;
};

struct Reservation {
    string id;
    string productId;
    int quantity;
    bool active;
};

class InventoryModule {
private:
    unordered_map<string, Product> products;
    unordered_map<string, Reservation> reservations;
    uint64_t nextReservationId = 1;

public:
    void addProduct(const Product& product) {
        validateId(product.id, "Product ID");
        validateId(product.name, "Product name");

        if (product.priceInCents <= 0 || product.stock < 0) {
            throw ValidationError("Invalid product price or stock.");
        }

        if (products.count(product.id)) {
            throw ValidationError("Duplicate product.");
        }

        products.emplace(product.id, product);
    }

    const Product& getProduct(const string& id) const {
        auto it = products.find(id);

        if (it == products.end()) {
            throw NotFoundError("Product not found.");
        }

        return it->second;
    }

    string reserve(const string& productId, int quantity) {
        if (quantity <= 0) {
            throw ValidationError("Quantity must be positive.");
        }

        auto it = products.find(productId);

        if (it == products.end()) {
            throw NotFoundError("Product not found.");
        }

        if (it->second.stock < quantity) {
            throw InsufficientStockError("Insufficient stock.");
        }

        it->second.stock -= quantity;

        string reservationId =
            "RES-" + to_string(nextReservationId++);

        reservations.emplace(
            reservationId,
            Reservation{
                reservationId,
                productId,
                quantity,
                true
            }
        );

        return reservationId;
    }

    void release(const string& reservationId) {
        auto it = reservations.find(reservationId);

        if (it == reservations.end()) {
            throw NotFoundError("Reservation not found.");
        }

        if (!it->second.active) {
            return;
        }

        products.at(it->second.productId).stock +=
            it->second.quantity;

        it->second.active = false;
    }

    void commit(const string& reservationId) {
        auto it = reservations.find(reservationId);

        if (it == reservations.end() || !it->second.active) {
            throw ValidationError("Active reservation required.");
        }

        it->second.active = false;
    }

    int availableStock(const string& productId) const {
        return getProduct(productId).stock;
    }
};

// ============================================================
// PAYMENT MODULE
// ============================================================

struct Payment {
    string id;
    string orderId;
    int64_t amountInCents;
    PaymentStatus status;
};

class PaymentModule {
private:
    map<string, Payment> payments;
    uint64_t nextPaymentId = 1;

public:
    string authorize(const string& orderId, int64_t amount) {
        validateId(orderId, "Order ID");

        if (amount <= 0) {
            throw ValidationError("Payment amount must be positive.");
        }

        string id = "PAY-" + to_string(nextPaymentId++);

        payments.emplace(
            id,
            Payment{
                id,
                orderId,
                amount,
                PaymentStatus::Authorized
            }
        );

        return id;
    }

    void refund(const string& paymentId) {
        auto it = payments.find(paymentId);

        if (it == payments.end()) {
            throw NotFoundError("Payment not found.");
        }

        if (it->second.status != PaymentStatus::Authorized) {
            throw ValidationError("Payment cannot be refunded.");
        }

        it->second.status = PaymentStatus::Refunded;
    }

    const Payment& getPayment(const string& id) const {
        auto it = payments.find(id);

        if (it == payments.end()) {
            throw NotFoundError("Payment not found.");
        }

        return it->second;
    }
};

// ============================================================
// ORDER MODULE
// ============================================================

struct Order {
    string id;
    string customerId;
    string productId;
    string reservationId;
    string paymentId;
    int quantity;
    int64_t totalInCents;
    OrderStatus status;
};

class OrderModule {
private:
    InventoryModule& inventory;
    PaymentModule& payments;

    unordered_map<string, Order> orders;
    uint64_t nextOrderId = 1;

public:
    OrderModule(
        InventoryModule& inventoryModule,
        PaymentModule& paymentModule
    )
        : inventory(inventoryModule),
          payments(paymentModule) {}

    const Order& createOrder(
        const string& customerId,
        const string& productId,
        int quantity
    ) {
        validateId(customerId, "Customer ID");
        validateId(productId, "Product ID");

        if (quantity <= 0) {
            throw ValidationError("Quantity must be positive.");
        }

        const Product& product = inventory.getProduct(productId);

        if (product.priceInCents >
            INT64_MAX / quantity) {
            throw ValidationError("Order amount overflow.");
        }

        int64_t total = product.priceInCents * quantity;

        string orderId = "ORD-" + to_string(nextOrderId++);
        string reservationId = inventory.reserve(productId, quantity);

        try {
            string paymentId = payments.authorize(orderId, total);

            Order order{
                orderId,
                customerId,
                productId,
                reservationId,
                paymentId,
                quantity,
                total,
                OrderStatus::Confirmed
            };

            orders.emplace(orderId, order);
            inventory.commit(reservationId);

            cout << "DOMAIN EVENT: OrderConfirmed "
                 << orderId << '\n';

            return orders.at(orderId);

        } catch (...) {
            inventory.release(reservationId);
            throw;
        }
    }

    void cancelOrder(const string& orderId) {
        auto it = orders.find(orderId);

        if (it == orders.end()) {
            throw NotFoundError("Order not found.");
        }

        if (it->second.status == OrderStatus::Cancelled) {
            return;
        }

        if (it->second.status != OrderStatus::Confirmed) {
            throw ValidationError("Order cannot be cancelled.");
        }

        // Refund before changing the order state.
        payments.refund(it->second.paymentId);

        it->second.status = OrderStatus::Cancelled;

        cout << "DOMAIN EVENT: OrderCancelled "
             << orderId << '\n';
    }

    const Order& getOrder(const string& orderId) const {
        auto it = orders.find(orderId);

        if (it == orders.end()) {
            throw NotFoundError("Order not found.");
        }

        return it->second;
    }
};

// ============================================================
// MODULE DEPENDENCY GOVERNANCE
// ============================================================

class DependencyRegistry {
private:
    map<string, set<string>> allowed = {
        {"orders", {"inventory", "payments", "shared"}},
        {"inventory", {"shared"}},
        {"payments", {"shared"}},
        {"notifications", {"shared"}}
    };

public:
    vector<string> validate(
        const map<string, vector<string>>& dependencies
    ) const {
        vector<string> violations;

        for (const auto& [source, targets] : dependencies) {
            auto it = allowed.find(source);

            if (it == allowed.end()) {
                violations.push_back(
                    "Unknown module: " + source
                );
                continue;
            }

            for (const string& target : targets) {
                if (!it->second.count(target)) {
                    violations.push_back(
                        source + " -> " + target
                    );
                }
            }
        }

        return violations;
    }
};

// ============================================================
// MIGRATION CONTROL
// ============================================================

enum class MigrationStage {
    Monolith,
    BoundariesDefined,
    ModuleIsolated,
    ContractStable,
    Externalized
};

class ModuleMigration {
private:
    string moduleName;
    MigrationStage stage = MigrationStage::Monolith;
    string endpoint;

public:
    explicit ModuleMigration(string name)
        : moduleName(std::move(name)) {
        validateId(moduleName, "Module name");
    }

    void advance(const string& newEndpoint = "") {
        switch (stage) {
            case MigrationStage::Monolith:
                stage = MigrationStage::BoundariesDefined;
                break;

            case MigrationStage::BoundariesDefined:
                stage = MigrationStage::ModuleIsolated;
                break;

            case MigrationStage::ModuleIsolated:
                stage = MigrationStage::ContractStable;
                break;

            case MigrationStage::ContractStable:
                if (newEndpoint.rfind("https://", 0) != 0) {
                    throw ValidationError(
                        "External migration requires HTTPS."
                    );
                }

                endpoint = newEndpoint;
                stage = MigrationStage::Externalized;
                break;

            case MigrationStage::Externalized:
                throw ValidationError(
                    "Module is already externalized."
                );
        }
    }

    string getStage() const {
        switch (stage) {
            case MigrationStage::Monolith: return "MONOLITH";
            case MigrationStage::BoundariesDefined:
                return "BOUNDARIES_DEFINED";
            case MigrationStage::ModuleIsolated:
                return "MODULE_ISOLATED";
            case MigrationStage::ContractStable:
                return "CONTRACT_STABLE";
            case MigrationStage::Externalized:
                return "EXTERNALIZED";
        }

        return "UNKNOWN";
    }

    const string& getEndpoint() const {
        return endpoint;
    }

    const string& getModuleName() const {
        return moduleName;
    }
};

// ============================================================
// APPLICATION COMPOSITION ROOT
// ============================================================

class Application {
public:
    InventoryModule inventory;
    PaymentModule payments;
    OrderModule orders;

    Application()
        : orders(inventory, payments) {}
};

// ============================================================
// MAIN
// ============================================================

int main() {
    try {
        Application app;

        app.inventory.addProduct({
            "LAPTOP-01",
            "Enterprise Laptop",
            7500000,
            20
        });

        cout << "MODULAR MONOLITH ORDER WORKFLOW\n\n";

        const Order& order = app.orders.createOrder(
            "CUSTOMER-01",
            "LAPTOP-01",
            3
        );

        cout << "\nORDER DETAILS\n";
        cout << "Order ID: " << order.id << '\n';
        cout << "Amount: " << order.totalInCents << " cents\n";
        cout << "Status: " << toString(order.status) << '\n';

        cout << "Remaining stock: "
             << app.inventory.availableStock("LAPTOP-01")
             << '\n';

        cout << "\nPAYMENT\n";
        cout << "Payment ID: " << order.paymentId << '\n';
        cout << "Payment status: "
             << toString(
                 app.payments.getPayment(order.paymentId).status
             ) << '\n';

        app.orders.cancelOrder(order.id);

        cout << "\nAFTER CANCELLATION\n";
        cout << "Order status: "
             << toString(app.orders.getOrder(order.id).status)
             << '\n';

        cout << "Payment status: "
             << toString(
                 app.payments.getPayment(order.paymentId).status
             ) << '\n';

        // Validate architectural dependency rules.
        DependencyRegistry registry;

        map<string, vector<string>> validDependencies = {
            {"orders", {"inventory", "payments", "shared"}},
            {"inventory", {"shared"}},
            {"payments", {"shared"}}
        };

        auto violations = registry.validate(validDependencies);

        if (!violations.empty()) {
            throw DomainError("Valid architecture was rejected.");
        }

        cout << "\nARCHITECTURE VALIDATION: PASSED\n";

        map<string, vector<string>> invalidDependencies = {
            {"inventory", {"orders"}}
        };

        violations = registry.validate(invalidDependencies);

        cout << "Invalid dependency count: "
             << violations.size() << '\n';

        for (const auto& violation : violations) {
            cout << violation << '\n';
        }

        // Demonstrate controlled module extraction.
        ModuleMigration migration("notifications");

        migration.advance();
        migration.advance();
        migration.advance();
        migration.advance("https://notifications.example.com");

        cout << "\nMIGRATION\n";
        cout << "Module: " << migration.getModuleName() << '\n';
        cout << "Stage: " << migration.getStage() << '\n';
        cout << "Endpoint: " << migration.getEndpoint() << '\n';

        // Edge case: stock must not become negative.
        try {
            app.orders.createOrder(
                "CUSTOMER-02",
                "LAPTOP-01",
                100
            );
        } catch (const InsufficientStockError& error) {
            cout << "\nEXPECTED FAILURE: "
                 << error.what() << '\n';
        }

        cout << "Final stock: "
             << app.inventory.availableStock("LAPTOP-01")
             << '\n';

        cout << "\nExecution completed.\n";

    } catch (const exception& error) {
        cerr << "APPLICATION ERROR: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
