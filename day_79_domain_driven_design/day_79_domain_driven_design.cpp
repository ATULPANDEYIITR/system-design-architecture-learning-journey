#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

// ============================================================
// DOMAIN-DRIVEN DESIGN: C++17 DOMAIN MODEL
// ============================================================

using Id = std::string;

class DomainError : public std::runtime_error {
public:
    explicit DomainError(const std::string& message)
        : std::runtime_error(message) {}
};

class ValidationError : public DomainError {
public:
    explicit ValidationError(const std::string& message)
        : DomainError(message) {}
};

class NotFoundError : public DomainError {
public:
    explicit NotFoundError(const std::string& message)
        : DomainError(message) {}
};

class ConcurrencyError : public DomainError {
public:
    explicit ConcurrencyError(const std::string& message)
        : DomainError(message) {}
};

// ============================================================
// VALUE OBJECTS
// ============================================================

struct Money {
    std::int64_t paise;
    std::string currency;

    Money(std::int64_t value, std::string code = "INR")
        : paise(value), currency(std::move(code)) {
        if (paise < 0) {
            throw ValidationError("Money cannot be negative.");
        }

        if (currency.size() != 3 ||
            !std::all_of(currency.begin(), currency.end(),
                [](unsigned char c) { return c >= 'A' && c <= 'Z'; })) {
            throw ValidationError("Invalid currency code.");
        }
    }

    Money operator+(const Money& other) const {
        if (currency != other.currency) {
            throw ValidationError("Currency mismatch.");
        }

        if (paise > INT64_MAX - other.paise) {
            throw ValidationError("Money overflow.");
        }

        return Money(paise + other.paise, currency);
    }

    Money multiply(int quantity) const {
        if (quantity <= 0) {
            throw ValidationError("Quantity must be positive.");
        }

        if (paise > INT64_MAX / quantity) {
            throw ValidationError("Money multiplication overflow.");
        }

        return Money(paise * quantity, currency);
    }
};

struct ProductSnapshot {
    Id productId;
    std::string name;
    Money price;
};

// ============================================================
// DOMAIN EVENTS
// ============================================================

struct DomainEvent {
    Id aggregateId;
    std::string type;
    std::uint64_t sequence;
    std::string description;
};

// ============================================================
// BOUNDED CONTEXT: PRODUCT CATALOG
// ============================================================

class Product {
private:
    Id id_;
    std::string name_;
    Money price_;
    bool active_ = true;
    std::uint64_t version_ = 0;

public:
    Product(Id id, std::string name, Money price)
        : id_(std::move(id)),
          name_(std::move(name)),
          price_(std::move(price)) {
        if (id_.empty() || name_.empty()) {
            throw ValidationError("Product identity and name are required.");
        }
    }

    const Id& id() const { return id_; }
    const std::string& name() const { return name_; }
    const Money& price() const { return price_; }
    std::uint64_t version() const { return version_; }

    void changePrice(const Money& newPrice) {
        if (newPrice.currency != price_.currency) {
            throw ValidationError("Currency cannot change implicitly.");
        }

        price_ = newPrice;
        ++version_;
    }

    void deactivate() {
        active_ = false;
        ++version_;
    }

    ProductSnapshot snapshot() const {
        if (!active_) {
            throw DomainError("Inactive product cannot be purchased.");
        }

        return {id_, name_, price_};
    }
};

class CatalogContext {
private:
    std::map<Id, Product> products_;

public:
    void registerProduct(Product product) {
        auto result = products_.emplace(product.id(), std::move(product));

        if (!result.second) {
            throw DomainError("Product already exists.");
        }
    }

    ProductSnapshot getSnapshot(const Id& id) const {
        auto it = products_.find(id);

        if (it == products_.end()) {
            throw NotFoundError("Product not found.");
        }

        return it->second.snapshot();
    }

    Product& getProduct(const Id& id) {
        auto it = products_.find(id);

        if (it == products_.end()) {
            throw NotFoundError("Product not found.");
        }

        return it->second;
    }
};

// ============================================================
// BOUNDED CONTEXT: INVENTORY
// ============================================================

class InventoryItem {
private:
    Id productId_;
    int available_;
    int reserved_ = 0;

public:
    InventoryItem(Id id, int stock)
        : productId_(std::move(id)), available_(stock) {
        if (stock < 0) {
            throw ValidationError("Stock cannot be negative.");
        }
    }

    void reserve(int quantity) {
        if (quantity <= 0 || quantity > available_) {
            throw DomainError("Invalid or insufficient stock.");
        }

        available_ -= quantity;
        reserved_ += quantity;
    }

    void release(int quantity) {
        if (quantity <= 0 || quantity > reserved_) {
            throw DomainError("Invalid stock release.");
        }

        reserved_ -= quantity;
        available_ += quantity;
    }

    void addStock(int quantity) {
        if (quantity <= 0 || available_ > INT32_MAX - quantity) {
            throw ValidationError("Invalid stock increase.");
        }

        available_ += quantity;
    }

    int available() const { return available_; }
    int reserved() const { return reserved_; }
};

class InventoryContext {
private:
    std::map<Id, InventoryItem> items_;

public:
    void addStock(const Id& productId, int quantity) {
        if (quantity <= 0) {
            throw ValidationError("Stock increase must be positive.");
        }

        auto it = items_.find(productId);

        if (it == items_.end()) {
            items_.emplace(
                std::piecewise_construct,
                std::forward_as_tuple(productId),
                std::forward_as_tuple(productId, quantity)
            );
        } else {
            it->second.addStock(quantity);
        }
    }

    void reserve(const Id& id, int quantity) {
        auto it = items_.find(id);

        if (it == items_.end()) {
            throw NotFoundError("Inventory record not found.");
        }

        it->second.reserve(quantity);
    }

    void release(const Id& id, int quantity) {
        auto it = items_.find(id);

        if (it == items_.end()) {
            throw NotFoundError("Inventory record not found.");
        }

        it->second.release(quantity);
    }

    const InventoryItem& get(const Id& id) const {
        auto it = items_.find(id);

        if (it == items_.end()) {
            throw NotFoundError("Inventory record not found.");
        }

        return it->second;
    }
};

// ============================================================
// BOUNDED CONTEXT: ORDER MANAGEMENT
// ============================================================

enum class OrderStatus {
    Draft,
    Submitted,
    Confirmed,
    Cancelled
};

std::string toString(OrderStatus status) {
    switch (status) {
        case OrderStatus::Draft: return "DRAFT";
        case OrderStatus::Submitted: return "SUBMITTED";
        case OrderStatus::Confirmed: return "CONFIRMED";
        case OrderStatus::Cancelled: return "CANCELLED";
    }

    throw DomainError("Unknown order state.");
}

struct OrderLine {
    ProductSnapshot product;
    int quantity;

    OrderLine(ProductSnapshot snapshot, int count)
        : product(std::move(snapshot)), quantity(count) {
        if (quantity <= 0) {
            throw ValidationError("Order quantity must be positive.");
        }
    }

    Money subtotal() const {
        return product.price.multiply(quantity);
    }
};

class Order {
private:
    Id id_;
    Id customerId_;
    OrderStatus status_ = OrderStatus::Draft;
    std::map<Id, OrderLine> lines_;
    std::vector<DomainEvent> events_;
    std::uint64_t version_ = 0;

    void recordEvent(
        const std::string& type,
        const std::string& description
    ) {
        events_.push_back({
            id_, type, ++version_, description
        });
    }

public:
    Order(Id id, Id customerId)
        : id_(std::move(id)),
          customerId_(std::move(customerId)) {
        if (id_.empty() || customerId_.empty()) {
            throw ValidationError("Order identifiers are required.");
        }

        recordEvent("OrderCreated", customerId_);
    }

    const Id& id() const { return id_; }
    const Id& customerId() const { return customerId_; }
    OrderStatus status() const { return status_; }
    std::uint64_t version() const { return version_; }

    const std::map<Id, OrderLine>& lines() const {
        return lines_;
    }

    const std::vector<DomainEvent>& events() const {
        return events_;
    }

    Money total() const {
        if (lines_.empty()) {
            return Money(0);
        }

        auto it = lines_.begin();
        Money result = it->second.subtotal();

        for (++it; it != lines_.end(); ++it) {
            result = result + it->second.subtotal();
        }

        return result;
    }

    void addProduct(const ProductSnapshot& product, int quantity) {
        if (status_ != OrderStatus::Draft) {
            throw DomainError("Only draft orders can be modified.");
        }

        if (quantity <= 0) {
            throw ValidationError("Quantity must be positive.");
        }

        if (!lines_.empty() &&
            lines_.begin()->second.product.price.currency !=
                product.price.currency) {
            throw ValidationError("Mixed currencies are prohibited.");
        }

        auto it = lines_.find(product.productId);

        if (it != lines_.end()) {
            if (it->second.product.price.paise != product.price.paise) {
                throw DomainError("Price snapshot has changed.");
            }

            if (it->second.quantity > INT32_MAX - quantity) {
                throw ValidationError("Order quantity overflow.");
            }

            it->second.quantity += quantity;
        } else {
            lines_.emplace(
                product.productId,
                OrderLine(product, quantity)
            );
        }

        ++version_;
    }

    void submit() {
        if (status_ != OrderStatus::Draft || lines_.empty()) {
            throw DomainError("Order cannot be submitted.");
        }

        status_ = OrderStatus::Submitted;
        recordEvent("OrderSubmitted", id_);
    }

    void confirm() {
        if (status_ != OrderStatus::Submitted) {
            throw DomainError("Only submitted orders can be confirmed.");
        }

        status_ = OrderStatus::Confirmed;
        recordEvent("OrderConfirmed", id_);
    }

    void cancel() {
        if (status_ != OrderStatus::Draft &&
            status_ != OrderStatus::Submitted) {
            throw DomainError("Order cannot be cancelled.");
        }

        status_ = OrderStatus::Cancelled;
        recordEvent("OrderCancelled", id_);
    }
};

// ============================================================
// BOUNDED CONTEXT: BILLING
// ============================================================

class Invoice {
private:
    Id id_;
    Id orderId_;
    Money amount_;
    bool paid_ = false;

public:
    Invoice(Id id, Id orderId, Money amount)
        : id_(std::move(id)),
          orderId_(std::move(orderId)),
          amount_(std::move(amount)) {}

    void pay() {
        if (paid_) {
            throw DomainError("Invoice already paid.");
        }

        paid_ = true;
    }

    const Money& amount() const { return amount_; }
    bool paid() const { return paid_; }
};

class BillingContext {
private:
    std::map<Id, Invoice> invoices_;

public:
    void createInvoice(const Order& order) {
        if (order.status() != OrderStatus::Submitted) {
            throw DomainError("Billing requires a submitted order.");
        }

        if (invoices_.count(order.id())) {
            throw DomainError("Invoice already exists.");
        }

        invoices_.emplace(
            std::piecewise_construct,
            std::forward_as_tuple(order.id()),
            std::forward_as_tuple(
                "INV-" + order.id(),
                order.id(),
                order.total()
            )
        );
    }

    const Invoice& getInvoice(const Id& orderId) const {
        auto it = invoices_.find(orderId);

        if (it == invoices_.end()) {
            throw NotFoundError("Invoice not found.");
        }

        return it->second;
    }
};

// ============================================================
// REPOSITORY: VERSIONED AGGREGATE STORAGE
// ============================================================

class OrderRepository {
private:
    struct StoredOrder {
        Order order;
        std::uint64_t version;

        StoredOrder(Order value)
            : order(std::move(value)), version(order.version()) {}
    };

    std::map<Id, StoredOrder> storage_;

public:
    void save(Order order, std::optional<std::uint64_t> expectedVersion) {
        auto it = storage_.find(order.id());

        if (it == storage_.end()) {
            if (expectedVersion && *expectedVersion != 0) {
                throw ConcurrencyError("Unexpected initial version.");
            }

            storage_.emplace(
                std::piecewise_construct,
                std::forward_as_tuple(order.id()),
                std::forward_as_tuple(std::move(order))
            );
            return;
        }

        if (!expectedVersion || it->second.version != *expectedVersion) {
            throw ConcurrencyError("Concurrent modification detected.");
        }

        it->second.version = order.version();
        it->second.order = std::move(order);
    }

    const Order& get(const Id& id) const {
        auto it = storage_.find(id);

        if (it == storage_.end()) {
            throw NotFoundError("Order not found.");
        }

        return it->second.order;
    }
};

// ============================================================
// APPLICATION SERVICE: CROSS-CONTEXT COORDINATION
// ============================================================

class OrderApplicationService {
private:
    InventoryContext& inventory_;
    BillingContext& billing_;

public:
    OrderApplicationService(
        InventoryContext& inventory,
        BillingContext& billing
    ) : inventory_(inventory), billing_(billing) {}

    void placeOrder(Order& order) {
        if (order.status() != OrderStatus::Draft) {
            throw DomainError("Order must be a draft.");
        }

        std::vector<std::pair<Id, int>> reserved;

        try {
            for (const auto& entry : order.lines()) {
                const auto& line = entry.second;

                inventory_.reserve(
                    line.product.productId,
                    line.quantity
                );

                reserved.emplace_back(
                    line.product.productId,
                    line.quantity
                );
            }

            order.submit();
            billing_.createInvoice(order);

        } catch (...) {
            // Compensating operations for completed reservations.
            for (auto it = reserved.rbegin(); it != reserved.rend(); ++it) {
                inventory_.release(it->first, it->second);
            }

            throw;
        }
    }
};

// ============================================================
// DEMONSTRATION
// ============================================================

int main() {
    try {
        CatalogContext catalog;
        InventoryContext inventory;
        BillingContext billing;
        OrderRepository repository;

        Product product(
            "PROD-001",
            "Enterprise Network Appliance",
            Money(12500000)
        );

        catalog.registerProduct(std::move(product));

        inventory.addStock("PROD-001", 15);

        Order order("ORD-1001", "CUST-5001");

        ProductSnapshot snapshot =
            catalog.getSnapshot("PROD-001");

        order.addProduct(snapshot, 2);

        repository.save(order, 0);

        std::cout << "DOMAIN-DRIVEN DESIGN DEMONSTRATION\n";
        std::cout << "Product: " << snapshot.name << '\n';
        std::cout << "Order: " << order.id() << '\n';
        std::cout << "Initial status: "
                  << toString(order.status()) << '\n';

        std::cout << "Order amount: INR "
                  << std::fixed << std::setprecision(2)
                  << static_cast<double>(order.total().paise) / 100.0
                  << '\n';

        OrderApplicationService service(inventory, billing);
        service.placeOrder(order);

        const Invoice& invoice = billing.getInvoice(order.id());

        std::cout << "\nPROCESSED ORDER\n";
        std::cout << "Status: " << toString(order.status()) << '\n';
        std::cout << "Invoice amount: INR "
                  << static_cast<double>(invoice.amount().paise) / 100.0
                  << '\n';

        const auto& stock = inventory.get("PROD-001");

        std::cout << "Available stock: " << stock.available() << '\n';
        std::cout << "Reserved stock: " << stock.reserved() << '\n';

        std::cout << "\nDOMAIN EVENTS\n";

        for (const auto& event : order.events()) {
            std::cout << event.sequence << " | "
                      << event.type << " | "
                      << event.description << '\n';
        }

        // Historical order snapshots remain independent of Catalog.
        catalog.getProduct("PROD-001").changePrice(Money(13000000));

        if (order.total().paise != 25000000) {
            throw DomainError("Historical price changed unexpectedly.");
        }

        try {
            order.addProduct(snapshot, 1);
        } catch (const DomainError& error) {
            std::cout << "\nExpected state rejection: "
                      << error.what() << '\n';
        }

        try {
            inventory.reserve("PROD-001", 100);
        } catch (const DomainError& error) {
            std::cout << "Expected inventory rejection: "
                      << error.what() << '\n';
        }

        std::cout << "\nAll C++17 assertions passed.\n";

    } catch (const std::exception& error) {
        std::cerr << "Application failure: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}
