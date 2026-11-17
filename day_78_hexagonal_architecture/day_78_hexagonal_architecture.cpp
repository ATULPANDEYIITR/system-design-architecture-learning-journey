#include <algorithm>
#include <cassert>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Hexagonal Architecture: Ports and Adapters
 *
 * C++17 implementation of an inventory and payment order system.
 *
 * Architectural layers:
 * Domain -> Application -> Ports <- Adapters
 *
 * The composition root wires concrete adapters into the
 * application service.
 */

namespace hexagonal {

// ============================================================
// DOMAIN
// ============================================================

enum class OrderStatus {
    Pending,
    Confirmed,
    Cancelled
};

class DomainError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ApplicationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class Money {
private:
    std::int64_t minorUnits_;

public:
    explicit Money(std::int64_t minorUnits)
        : minorUnits_(minorUnits) {
        if (minorUnits <= 0) {
            throw DomainError("Amount must be positive");
        }
    }

    std::int64_t minorUnits() const {
        return minorUnits_;
    }

    Money multiply(int quantity) const {
        if (quantity <= 0) {
            throw DomainError("Quantity must be positive");
        }

        if (minorUnits_ >
            INT64_MAX / quantity) {
            throw DomainError("Money multiplication overflow");
        }

        return Money(minorUnits_ * quantity);
    }
};

struct OrderItem {
    std::string productId;
    int quantity;
    Money unitPrice;

    OrderItem(
        std::string product,
        int count,
        Money price
    )
        : productId(std::move(product)),
          quantity(count),
          unitPrice(price) {

        if (productId.empty()) {
            throw DomainError("Product ID is required");
        }

        if (quantity <= 0) {
            throw DomainError("Quantity must be positive");
        }
    }

    std::int64_t subtotal() const {
        return unitPrice.multiply(quantity).minorUnits();
    }
};

class Order {
private:
    std::string id_;
    std::string customerId_;
    std::vector<OrderItem> items_;
    OrderStatus status_;
    unsigned int version_;

public:
    Order(
        std::string id,
        std::string customer,
        std::vector<OrderItem> items
    )
        : id_(std::move(id)),
          customerId_(std::move(customer)),
          items_(std::move(items)),
          status_(OrderStatus::Pending),
          version_(0) {

        if (id_.empty() || customerId_.empty()) {
            throw DomainError("Order identifiers are required");
        }

        if (items_.empty()) {
            throw DomainError("Order must have items");
        }
    }

    const std::string& id() const {
        return id_;
    }

    const std::string& customerId() const {
        return customerId_;
    }

    const std::vector<OrderItem>& items() const {
        return items_;
    }

    OrderStatus status() const {
        return status_;
    }

    unsigned int version() const {
        return version_;
    }

    std::int64_t total() const {
        std::int64_t result = 0;

        for (const auto& item : items_) {
            const auto amount = item.subtotal();

            if (result > INT64_MAX - amount) {
                throw DomainError("Order total overflow");
            }

            result += amount;
        }

        return result;
    }

    void confirm() {
        if (status_ != OrderStatus::Pending) {
            throw DomainError("Invalid confirmation transition");
        }

        status_ = OrderStatus::Confirmed;
        ++version_;
    }

    void cancel() {
        if (status_ != OrderStatus::Pending) {
            throw DomainError("Invalid cancellation transition");
        }

        status_ = OrderStatus::Cancelled;
        ++version_;
    }
};

// ============================================================
// PORTS
// ============================================================

// Secondary port: persistence.

class OrderRepositoryPort {
public:
    virtual ~OrderRepositoryPort() = default;

    virtual void save(const Order& order) = 0;

    virtual std::optional<Order> findById(
        const std::string& id
    ) const = 0;
};

// Secondary port: inventory.

class InventoryPort {
public:
    virtual ~InventoryPort() = default;

    virtual bool reserve(
        const std::string& product,
        int quantity
    ) = 0;

    virtual void release(
        const std::string& product,
        int quantity
    ) = 0;
};

// Secondary port: payment.

class PaymentPort {
public:
    virtual ~PaymentPort() = default;

    virtual std::string charge(
        const std::string& customer,
        std::int64_t amount,
        const std::string& idempotencyKey
    ) = 0;

    virtual void refund(const std::string& paymentId) = 0;
};

// Secondary port: integration events.

class EventPublisherPort {
public:
    virtual ~EventPublisherPort() = default;

    virtual void publish(
        const std::string& eventType,
        const std::string& aggregateId
    ) = 0;
};

// Primary port.

class PlaceOrderPort {
public:
    virtual ~PlaceOrderPort() = default;

    virtual std::string execute(
        const std::string& customer,
        const std::vector<OrderItem>& items
    ) = 0;
};

// ============================================================
// APPLICATION SERVICE
// ============================================================

class PlaceOrderService : public PlaceOrderPort {
private:
    OrderRepositoryPort& repository_;
    InventoryPort& inventory_;
    PaymentPort& payment_;
    EventPublisherPort& events_;

    std::vector<std::string> makeCompensation(
        const std::vector<OrderItem>& items
    ) {
        std::vector<std::string> failures;

        for (auto it = items.rbegin(); it != items.rend(); ++it) {
            try {
                inventory_.release(
                    it->productId,
                    it->quantity
                );
            } catch (const std::exception& error) {
                failures.push_back(error.what());
            }
        }

        return failures;
    }

public:
    PlaceOrderService(
        OrderRepositoryPort& repository,
        InventoryPort& inventory,
        PaymentPort& payment,
        EventPublisherPort& events
    )
        : repository_(repository),
          inventory_(inventory),
          payment_(payment),
          events_(events) {}

    std::string execute(
        const std::string& customer,
        const std::vector<OrderItem>& items
    ) override {

        if (customer.empty() || items.empty()) {
            throw ApplicationError("Invalid order command");
        }

        static unsigned long long sequence = 0;

        const std::string orderId =
            "ORD-" + std::to_string(++sequence);

        Order order(orderId, customer, items);

        std::vector<OrderItem> reserved;
        std::optional<std::string> paymentId;

        try {
            // Reserve every line before charging.
            for (const auto& item : items) {
                if (!inventory_.reserve(
                    item.productId,
                    item.quantity
                )) {
                    throw ApplicationError(
                        "Inventory unavailable for " + item.productId
                    );
                }

                reserved.push_back(item);
            }

            paymentId = payment_.charge(
                customer,
                order.total(),
                order.id()
            );

            order.confirm();

            repository_.save(order);

            events_.publish("OrderConfirmed", order.id());

            return order.id();

        } catch (const std::exception& error) {
            std::vector<std::string> compensationFailures;

            if (paymentId.has_value()) {
                try {
                    payment_.refund(*paymentId);
                } catch (const std::exception& refundError) {
                    compensationFailures.push_back(
                        refundError.what()
                    );
                }
            }

            // Release only successfully reserved lines.
            for (auto it = reserved.rbegin();
                 it != reserved.rend(); ++it) {
                try {
                    inventory_.release(
                        it->productId,
                        it->quantity
                    );
                } catch (const std::exception& releaseError) {
                    compensationFailures.push_back(
                        releaseError.what()
                    );
                }
            }

            std::string message =
                "Order failed: " + std::string(error.what());

            if (!compensationFailures.empty()) {
                message += "; compensation requires recovery";
            }

            throw ApplicationError(message);
        }
    }
};

// ============================================================
// SECONDARY ADAPTERS
// ============================================================

class MemoryOrderRepository : public OrderRepositoryPort {
private:
    std::unordered_map<std::string, Order> orders_;

public:
    void save(const Order& order) override {
        auto existing = orders_.find(order.id());

        if (existing != orders_.end() &&
            order.version() <= existing->second.version()) {
            throw ApplicationError("Stale order version");
        }

        orders_.insert_or_assign(order.id(), order);
    }

    std::optional<Order> findById(
        const std::string& id
    ) const override {

        auto it = orders_.find(id);

        if (it == orders_.end()) {
            return std::nullopt;
        }

        return it->second;
    }
};

class MemoryInventoryAdapter : public InventoryPort {
private:
    std::unordered_map<std::string, int> stock_;

public:
    explicit MemoryInventoryAdapter(
        std::unordered_map<std::string, int> initialStock
    )
        : stock_(std::move(initialStock)) {

        for (const auto& [product, quantity] : stock_) {
            if (quantity < 0) {
                throw DomainError("Negative initial inventory");
            }
        }
    }

    bool reserve(
        const std::string& product,
        int quantity
    ) override {

        if (quantity <= 0) {
            throw DomainError("Invalid reservation quantity");
        }

        auto it = stock_.find(product);

        if (it == stock_.end() || it->second < quantity) {
            return false;
        }

        it->second -= quantity;
        return true;
    }

    void release(
        const std::string& product,
        int quantity
    ) override {

        if (quantity <= 0) {
            throw DomainError("Invalid release quantity");
        }

        auto& available = stock_[product];

        if (available > INT_MAX - quantity) {
            throw DomainError("Inventory overflow");
        }

        available += quantity;
    }

    int available(const std::string& product) const {
        auto it = stock_.find(product);

        return it == stock_.end() ? 0 : it->second;
    }
};

class MemoryPaymentAdapter : public PaymentPort {
private:
    std::unordered_map<std::string, std::string> payments_;
    std::unordered_map<std::string, std::string> idempotency_;

    unsigned long long sequence_ = 0;

public:
    std::string charge(
        const std::string& customer,
        std::int64_t amount,
        const std::string& key
    ) override {

        if (customer.empty() || amount <= 0 || key.empty()) {
            throw ApplicationError("Invalid payment request");
        }

        auto existing = idempotency_.find(key);

        if (existing != idempotency_.end()) {
            return existing->second;
        }

        const std::string paymentId =
            "PAY-" + std::to_string(++sequence_);

        payments_[paymentId] = "CHARGED";
        idempotency_[key] = paymentId;

        return paymentId;
    }

    void refund(const std::string& paymentId) override {
        auto it = payments_.find(paymentId);

        if (it == payments_.end() || it->second != "CHARGED") {
            throw ApplicationError("Payment cannot be refunded");
        }

        it->second = "REFUNDED";
    }
};

class MemoryEventAdapter : public EventPublisherPort {
private:
    std::vector<std::pair<std::string, std::string>> history_;

public:
    void publish(
        const std::string& eventType,
        const std::string& aggregateId
    ) override {

        if (eventType.empty() || aggregateId.empty()) {
            throw ApplicationError("Invalid event");
        }

        history_.emplace_back(eventType, aggregateId);
    }

    std::size_t eventCount() const {
        return history_.size();
    }
};

// ============================================================
// PRIMARY ADAPTER
// ============================================================

class ConsoleAdapter {
private:
    PlaceOrderPort& useCase_;

public:
    explicit ConsoleAdapter(PlaceOrderPort& useCase)
        : useCase_(useCase) {}

    std::string submit() {
        std::vector<OrderItem> items;

        items.emplace_back(
            "WORKSTATION-001",
            1,
            Money(8500000)
        );

        items.emplace_back(
            "KEYBOARD-001",
            2,
            Money(450000)
        );

        return useCase_.execute(
            "CUSTOMER-3001",
            items
        );
    }
};

// ============================================================
// TESTING
// ============================================================

void runTests() {
    MemoryOrderRepository repository;

    MemoryInventoryAdapter inventory({
        {"P1", 5}
    });

    MemoryPaymentAdapter payment;
    MemoryEventAdapter events;

    PlaceOrderService service(
        repository,
        inventory,
        payment,
        events
    );

    std::vector<OrderItem> items{
        OrderItem("P1", 2, Money(10000))
    };

    const std::string id = service.execute("C1", items);

    auto stored = repository.findById(id);

    assert(stored.has_value());
    assert(stored->status() == OrderStatus::Confirmed);
    assert(stored->total() == 20000);
    assert(inventory.available("P1") == 3);
    assert(events.eventCount() == 1);

    // Failed reservation must not change stock.
    try {
        service.execute(
            "C2",
            {
                OrderItem("P1", 20, Money(10000))
            }
        );

        throw std::runtime_error("Expected failure");

    } catch (const ApplicationError&) {
        assert(inventory.available("P1") == 3);
    }

    // Invalid domain quantity.
    try {
        OrderItem("P1", 0, Money(10000));
        throw std::runtime_error("Expected domain failure");
    } catch (const DomainError&) {
        // Expected.
    }

    std::cout << "C++17 tests passed.\n";
}

// ============================================================
// COMPOSITION ROOT AND MAIN
// ============================================================

} // namespace hexagonal

int main() {
    using namespace hexagonal;

    try {
        MemoryOrderRepository repository;

        MemoryInventoryAdapter inventory({
            {"WORKSTATION-001", 10},
            {"KEYBOARD-001", 50}
        });

        MemoryPaymentAdapter payment;
        MemoryEventAdapter events;

        // Infrastructure is instantiated only at the boundary.
        PlaceOrderService service(
            repository,
            inventory,
            payment,
            events
        );

        ConsoleAdapter console(service);

        const std::string orderId = console.submit();

        std::cout << "\nHEXAGONAL ORDER APPLICATION\n";
        std::cout << "---------------------------\n";
        std::cout << "Order ID: " << orderId << '\n';
        std::cout << "Remaining workstations: "
                  << inventory.available("WORKSTATION-001") << '\n';
        std::cout << "Events published: "
                  << events.eventCount() << '\n';

        runTests();

    } catch (const std::exception& error) {
        std::cerr << "Application failure: "
                  << error.what() << '\n';

        return 1;
    }

    return 0;
}
