#include <algorithm>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <functional>
#include <sstream>

using namespace std;

/*
 * Clean Architecture: Dependency Inversion and Boundaries
 *
 * C++17 repository governance and merge-independent application
 * architecture engine for an enterprise order-processing system.
 *
 * Demonstrates:
 * - Domain modeling
 * - Abstract ports
 * - Concrete adapters
 * - Dependency direction validation
 * - Circular dependency detection
 * - Application service orchestration
 * - Merge-style policy evaluation of architecture rules
 * - State transitions
 * - Failure handling
 *
 * Compile:
 * g++ -std=c++17 -Wall -Wextra -pedantic main.cpp -o architecture
 */

// ============================================================
// 1. DOMAIN LAYER
// ============================================================

class DomainError : public runtime_error {
public:
    explicit DomainError(const string& message)
        : runtime_error(message) {}
};

class ApplicationError : public runtime_error {
public:
    explicit ApplicationError(const string& message)
        : runtime_error(message) {}
};

enum class OrderStatus {
    Pending,
    Paid,
    Cancelled
};

string statusName(OrderStatus status) {
    switch (status) {
        case OrderStatus::Pending: return "PENDING";
        case OrderStatus::Paid: return "PAID";
        case OrderStatus::Cancelled: return "CANCELLED";
    }

    return "UNKNOWN";
}

struct Money {
    long long paise;
    string currency;

    Money(long long value, string code = "INR")
        : paise(value), currency(std::move(code)) {

        if (paise < 0) {
            throw DomainError("Money cannot be negative.");
        }

        if (currency.size() != 3) {
            throw DomainError("Invalid currency.");
        }

        transform(
            currency.begin(),
            currency.end(),
            currency.begin(),
            ::toupper
        );
    }

    Money add(const Money& other) const {
        if (currency != other.currency) {
            throw DomainError("Currency mismatch.");
        }

        if (paise > 0 &&
            other.paise > 9223372036854775807LL - paise) {
            throw DomainError("Monetary overflow.");
        }

        return Money(paise + other.paise, currency);
    }

    Money multiply(int quantity) const {
        if (quantity <= 0 || quantity > 1000) {
            throw DomainError("Invalid quantity.");
        }

        if (paise > 9223372036854775807LL / quantity) {
            throw DomainError("Monetary overflow.");
        }

        return Money(paise * quantity, currency);
    }

    string display() const {
        ostringstream output;
        output << currency << " " << paise / 100
               << ".";

        if (paise % 100 < 10) {
            output << "0";
        }

        output << paise % 100;
        return output.str();
    }
};

struct OrderLine {
    string productId;
    int quantity;
    Money unitPrice;

    OrderLine(
        string id,
        int count,
        Money price
    )
        : productId(std::move(id)),
          quantity(count),
          unitPrice(std::move(price)) {

        if (productId.empty()) {
            throw DomainError("Product ID is required.");
        }

        if (quantity <= 0 || quantity > 1000) {
            throw DomainError("Invalid quantity.");
        }
    }

    Money subtotal() const {
        return unitPrice.multiply(quantity);
    }
};

class Order {
private:
    string id;
    string customerId;
    vector<OrderLine> lines;
    OrderStatus status;
    unsigned int version;

public:
    Order(
        string orderId,
        string customer,
        vector<OrderLine> items
    )
        : id(std::move(orderId)),
          customerId(std::move(customer)),
          lines(std::move(items)),
          status(OrderStatus::Pending),
          version(1) {

        if (id.empty() || customerId.empty()) {
            throw DomainError("Order identity is required.");
        }

        if (lines.empty() || lines.size() > 100) {
            throw DomainError("Invalid order line count.");
        }

        total();
    }

    Money total() const {
        Money result(0, lines.front().unitPrice.currency);

        for (const auto& line : lines) {
            result = result.add(line.subtotal());
        }

        return result;
    }

    void markPaid() {
        if (status != OrderStatus::Pending) {
            throw DomainError("Invalid payment transition.");
        }

        status = OrderStatus::Paid;
        ++version;
    }

    void cancel() {
        if (status != OrderStatus::Pending) {
            throw DomainError("Only pending orders can be cancelled.");
        }

        status = OrderStatus::Cancelled;
        ++version;
    }

    const string& getId() const {
        return id;
    }

    const string& getCustomerId() const {
        return customerId;
    }

    OrderStatus getStatus() const {
        return status;
    }

    unsigned int getVersion() const {
        return version;
    }
};

// ============================================================
// 2. APPLICATION PORTS
// ============================================================

class IOrderRepository {
public:
    virtual ~IOrderRepository() = default;

    virtual void save(const Order& order) = 0;

    virtual const Order* findById(
        const string& id
    ) const = 0;
};

class IPaymentGateway {
public:
    virtual ~IPaymentGateway() = default;

    virtual bool charge(
        const string& orderId,
        const Money& amount
    ) = 0;
};

class IEventPublisher {
public:
    virtual ~IEventPublisher() = default;

    virtual void publish(
        const string& event,
        const string& aggregateId
    ) = 0;
};

// ============================================================
// 3. INFRASTRUCTURE ADAPTERS
// ============================================================

class InMemoryOrderRepository : public IOrderRepository {
private:
    map<string, Order> orders;

public:
    void save(const Order& order) override {
        orders.insert_or_assign(order.getId(), order);
    }

    const Order* findById(
        const string& id
    ) const override {

        auto iterator = orders.find(id);

        if (iterator == orders.end()) {
            return nullptr;
        }

        return &iterator->second;
    }

    size_t size() const {
        return orders.size();
    }
};

class SimulatedPaymentGateway : public IPaymentGateway {
private:
    bool successful;
    set<string> processed;

public:
    explicit SimulatedPaymentGateway(bool result)
        : successful(result) {}

    bool charge(
        const string& orderId,
        const Money& amount
    ) override {

        if (processed.count(orderId)) {
            return true;
        }

        if (!successful) {
            return false;
        }

        if (amount.paise <= 0) {
            return false;
        }

        processed.insert(orderId);
        return true;
    }
};

class ConsoleEventPublisher : public IEventPublisher {
public:
    void publish(
        const string& event,
        const string& aggregateId
    ) override {

        cout << "[EVENT] " << event
             << " | Aggregate: " << aggregateId
             << '\n';
    }
};

// ============================================================
// 4. APPLICATION USE CASE
// ============================================================

class PlaceOrderService {
private:
    IOrderRepository& repository;
    IPaymentGateway& payment;
    IEventPublisher& events;

public:
    PlaceOrderService(
        IOrderRepository& repo,
        IPaymentGateway& gateway,
        IEventPublisher& publisher
    )
        : repository(repo),
          payment(gateway),
          events(publisher) {}

    Order execute(
        const string& orderId,
        const string& customerId,
        const vector<OrderLine>& lines
    ) {

        Order order(orderId, customerId, lines);

        // Save the initial aggregate before external interaction.
        repository.save(order);

        try {
            bool paid = payment.charge(
                order.getId(),
                order.total()
            );

            if (!paid) {
                throw ApplicationError("Payment declined.");
            }

            order.markPaid();
            repository.save(order);

            events.publish("OrderPaid", order.getId());

            return order;

        } catch (const exception& error) {

            if (order.getStatus() == OrderStatus::Pending) {
                order.cancel();
                repository.save(order);
            }

            throw ApplicationError(
                string("Order processing failed: ") + error.what()
            );
        }
    }
};

// ============================================================
// 5. ARCHITECTURE GOVERNANCE ENGINE
// ============================================================

enum class Layer {
    Domain,
    Application,
    Adapter,
    Infrastructure
};

string layerName(Layer layer) {
    switch (layer) {
        case Layer::Domain: return "DOMAIN";
        case Layer::Application: return "APPLICATION";
        case Layer::Adapter: return "ADAPTER";
        case Layer::Infrastructure: return "INFRASTRUCTURE";
    }

    return "UNKNOWN";
}

struct Dependency {
    string source;
    string target;
    Layer sourceLayer;
    Layer targetLayer;
};

class ArchitecturePolicy {
private:
    map<Layer, set<Layer>> allowed;

public:
    ArchitecturePolicy() {
        allowed[Layer::Domain] = {};
        allowed[Layer::Application] = {
            Layer::Domain
        };

        allowed[Layer::Adapter] = {
            Layer::Application,
            Layer::Domain
        };

        allowed[Layer::Infrastructure] = {
            Layer::Application,
            Layer::Domain,
            Layer::Adapter
        };
    }

    vector<string> evaluate(
        const vector<Dependency>& dependencies
    ) const {

        vector<string> violations;

        for (const auto& dependency : dependencies) {

            auto iterator = allowed.find(
                dependency.sourceLayer
            );

            if (
                iterator == allowed.end() ||
                !iterator->second.count(dependency.targetLayer)
            ) {

                violations.push_back(
                    dependency.source + " (" +
                    layerName(dependency.sourceLayer) +
                    ") cannot depend on " +
                    dependency.target + " (" +
                    layerName(dependency.targetLayer) + ")"
                );
            }
        }

        return violations;
    }
};

// ============================================================
// 6. CIRCULAR DEPENDENCY DETECTOR
// ============================================================

class DependencyGraph {
private:
    map<string, vector<string>> graph;

    bool detect(
        const string& node,
        set<string>& visited,
        set<string>& active,
        vector<string>& path,
        vector<vector<string>>& cycles
    ) const {

        if (active.count(node)) {
            auto position = find(
                path.begin(),
                path.end(),
                node
            );

            vector<string> cycle(
                position,
                path.end()
            );

            cycle.push_back(node);
            cycles.push_back(cycle);

            return true;
        }

        if (visited.count(node)) {
            return false;
        }

        visited.insert(node);
        active.insert(node);
        path.push_back(node);

        bool found = false;

        auto iterator = graph.find(node);

        if (iterator != graph.end()) {
            for (const auto& neighbor : iterator->second) {
                found = detect(
                    neighbor,
                    visited,
                    active,
                    path,
                    cycles
                ) || found;
            }
        }

        path.pop_back();
        active.erase(node);

        return found;
    }

public:
    void addDependency(
        const string& source,
        const string& target
    ) {
        graph[source].push_back(target);
        graph.try_emplace(target);
    }

    vector<vector<string>> findCycles() const {
        set<string> visited;
        set<string> active;

        vector<string> path;
        vector<vector<string>> cycles;

        for (const auto& entry : graph) {
            detect(
                entry.first,
                visited,
                active,
                path,
                cycles
            );
        }

        return cycles;
    }
};

// ============================================================
// 7. DEMONSTRATION
// ============================================================

void demonstrateArchitecture() {

    ArchitecturePolicy policy;

    vector<Dependency> dependencies = {
        {
            "OrderUseCase",
            "OrderEntity",
            Layer::Application,
            Layer::Domain
        },
        {
            "PostgresAdapter",
            "OrderRepositoryPort",
            Layer::Infrastructure,
            Layer::Application
        },
        {
            "OrderEntity",
            "PostgresAdapter",
            Layer::Domain,
            Layer::Infrastructure
        }
    };

    auto violations = policy.evaluate(dependencies);

    cout << "\nArchitecture validation\n";

    for (const auto& violation : violations) {
        cout << "VIOLATION: " << violation << '\n';
    }

    if (violations.size() != 1) {
        throw runtime_error("Unexpected architecture validation result.");
    }

    DependencyGraph graph;

    graph.addDependency("domain", "application");
    graph.addDependency("application", "adapter");
    graph.addDependency("adapter", "domain");

    auto cycles = graph.findCycles();

    cout << "\nCircular dependency analysis\n";

    for (const auto& cycle : cycles) {
        for (size_t i = 0; i < cycle.size(); ++i) {
            if (i) cout << " -> ";
            cout << cycle[i];
        }

        cout << '\n';
    }
}

void demonstrateOrderProcessing() {

    InMemoryOrderRepository repository;
    SimulatedPaymentGateway payment(true);
    ConsoleEventPublisher events;

    PlaceOrderService service(
        repository,
        payment,
        events
    );

    vector<OrderLine> lines = {
        OrderLine(
            "LAPTOP-001",
            1,
            Money(6500000)
        ),
        OrderLine(
            "MOUSE-001",
            2,
            Money(75000)
        )
    };

    Order order = service.execute(
        "ORDER-1001",
        "CUSTOMER-101",
        lines
    );

    cout << "\nOrder processing\n";
    cout << "Order ID: " << order.getId() << '\n';
    cout << "Customer: " << order.getCustomerId() << '\n';
    cout << "Amount: " << order.total().display() << '\n';
    cout << "Status: " << statusName(order.getStatus()) << '\n';
    cout << "Version: " << order.getVersion() << '\n';

    if (order.getStatus() != OrderStatus::Paid) {
        throw runtime_error("Order should be paid.");
    }
}

void demonstrateFailureHandling() {

    InMemoryOrderRepository repository;
    SimulatedPaymentGateway payment(false);
    ConsoleEventPublisher events;

    PlaceOrderService service(
        repository,
        payment,
        events
    );

    vector<OrderLine> lines = {
        OrderLine(
            "BOOK-001",
            1,
            Money(50000)
        )
    };

    try {
        service.execute(
            "ORDER-FAIL-001",
            "CUSTOMER-102",
            lines
        );

        throw runtime_error("Expected payment failure.");
    } catch (const ApplicationError& error) {

        const Order* order = repository.findById(
            "ORDER-FAIL-001"
        );

        if (
            order == nullptr ||
            order->getStatus() != OrderStatus::Cancelled
        ) {
            throw runtime_error("Failure state was not persisted.");
        }

        cout << "\nFailure handled: "
             << error.what() << '\n';

        cout << "Persisted state: "
             << statusName(order->getStatus()) << '\n';
    }
}

void demonstrateValidation() {

    try {
        Money invalid(-100);
        throw runtime_error("Negative money accepted.");
    } catch (const DomainError&) {
        cout << "\nNegative monetary amount rejected.\n";
    }

    try {
        Money inr(1000, "INR");
        Money usd(1000, "USD");

        inr.add(usd);

        throw runtime_error("Currency mismatch accepted.");
    } catch (const DomainError&) {
        cout << "Currency mismatch rejected.\n";
    }
}

int main() {
    try {
        cout << "CLEAN ARCHITECTURE ENGINE\n";
        cout << "=========================\n";

        demonstrateArchitecture();
        demonstrateValidation();
        demonstrateOrderProcessing();
        demonstrateFailureHandling();

        cout << "\nAll C++17 demonstrations passed.\n";

        return 0;

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}
