#include <algorithm>
#include <chrono>
#include <cstdint>
#include <deque>
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
#include <unordered_set>
#include <utility>
#include <vector>

using namespace std;

// ============================================================
// Service Communication: C++17
//
// Scenario: An order-processing platform communicates with
// inventory and payment services through REST-style resources,
// typed RPC contracts, and asynchronous event messaging.
//
// No external libraries are required.
// ============================================================

enum class Protocol {
    REST,
    GRPC,
    MESSAGING
};

enum class RpcStatus {
    OK,
    INVALID_ARGUMENT,
    NOT_FOUND,
    UNAVAILABLE,
    INTERNAL
};

enum class DeliveryStatus {
    PENDING,
    ACKNOWLEDGED,
    DEAD_LETTERED
};

enum class OrderStatus {
    CREATED,
    INVENTORY_RESERVED,
    PAYMENT_PENDING,
    CONFIRMED,
    FAILED
};

struct Product {
    int id;
    string name;
    double price;
};

struct RpcResult {
    RpcStatus status;
    optional<Product> product;
    string message;
};

struct Order {
    int id;
    int productId;
    int quantity;
    OrderStatus status;
};

struct Message {
    string id;
    string topic;
    string eventType;
    string payload;
    int attempts = 0;
    DeliveryStatus status = DeliveryStatus::PENDING;
};

// ============================================================
// 1. REST-Style Resource Layer
// ============================================================

class ProductRepository {
private:
    unordered_map<int, Product> products;
    int nextId = 103;

public:
    ProductRepository() {
        products.emplace(101, Product{101, "Laptop", 75000.0});
        products.emplace(102, Product{102, "Monitor", 18000.0});
    }

    optional<Product> find(int id) const {
        auto it = products.find(id);

        if (it == products.end()) {
            return nullopt;
        }

        return it->second;
    }

    Product create(const string& name, double price) {
        if (name.empty() || name.size() > 120) {
            throw invalid_argument("Invalid product name");
        }

        if (price <= 0 || price > 1000000000.0) {
            throw invalid_argument("Invalid product price");
        }

        Product product{nextId++, name, price};
        products.emplace(product.id, product);

        return product;
    }
};

struct HttpResponse {
    int statusCode;
    string contentType;
    string body;
};

class RestApi {
private:
    ProductRepository& repository;

public:
    explicit RestApi(ProductRepository& repository)
        : repository(repository) {}

    HttpResponse getProduct(int id) const {
        if (id <= 0) {
            return {
                400,
                "application/json",
                R"({"error":"Invalid product ID"})"
            };
        }

        auto product = repository.find(id);

        if (!product) {
            return {
                404,
                "application/json",
                R"({"error":"Product not found"})"
            };
        }

        return {
            200,
            "application/json",
            "{\"id\":" + to_string(product->id) +
            ",\"name\":\"" + product->name +
            "\",\"price\":" + to_string(product->price) + "}"
        };
    }

    HttpResponse createProduct(
        const string& name,
        double price
    ) {
        try {
            Product product = repository.create(name, price);

            return {
                201,
                "application/json",
                "{\"id\":" + to_string(product.id) +
                ",\"name\":\"" + product.name + "\"}"
            };

        } catch (const invalid_argument& error) {
            return {
                400,
                "application/json",
                "{\"error\":\"" + string(error.what()) + "\"}"
            };
        }
    }
};

// ============================================================
// 2. Strongly Typed RPC Service
// ============================================================

struct GetProductRequest {
    int productId;
};

class ProductRpcService {
private:
    const ProductRepository& repository;

public:
    explicit ProductRpcService(
        const ProductRepository& repository
    ) : repository(repository) {}

    RpcResult getProduct(
        const GetProductRequest& request
    ) const {
        if (request.productId <= 0) {
            return {
                RpcStatus::INVALID_ARGUMENT,
                nullopt,
                "Product ID must be positive"
            };
        }

        auto product = repository.find(request.productId);

        if (!product) {
            return {
                RpcStatus::NOT_FOUND,
                nullopt,
                "Product not found"
            };
        }

        return {
            RpcStatus::OK,
            product,
            "Request completed"
        };
    }
};

class RpcClient {
private:
    const ProductRpcService& service;

public:
    explicit RpcClient(const ProductRpcService& service)
        : service(service) {}

    RpcResult getProduct(int id) const {
        // A real client also enforces a transport deadline.
        return service.getProduct(GetProductRequest{id});
    }
};

// ============================================================
// 3. Asynchronous Messaging
// ============================================================

class MessageBroker {
private:
    unordered_map<string, deque<Message>> queues;
    unordered_map<string, vector<string>> subscriptions;
    unordered_set<string> acknowledgedIds;
    vector<Message> deadLetters;
    int maxRetries;

public:
    explicit MessageBroker(int maxRetries = 3)
        : maxRetries(maxRetries) {
        if (maxRetries < 0) {
            throw invalid_argument("Invalid retry limit");
        }
    }

    void subscribe(
        const string& topic,
        const string& consumer
    ) {
        if (topic.empty() || consumer.empty()) {
            throw invalid_argument("Invalid subscription");
        }

        auto& subscribers = subscriptions[topic];

        if (find(
            subscribers.begin(),
            subscribers.end(),
            consumer
        ) == subscribers.end()) {
            subscribers.push_back(consumer);
        }
    }

    void publish(Message message) {
        if (message.id.empty() || message.topic.empty()) {
            throw invalid_argument("Invalid message");
        }

        if (message.payload.size() > 65536) {
            throw invalid_argument("Message exceeds payload limit");
        }

        queues[message.topic].push_back(move(message));
    }

    bool consumeOne(
        const string& topic,
        const function<void(const Message&)>& handler
    ) {
        auto queueIt = queues.find(topic);

        if (queueIt == queues.end() || queueIt->second.empty()) {
            return false;
        }

        Message message = move(queueIt->second.front());
        queueIt->second.pop_front();

        if (acknowledgedIds.count(message.id)) {
            return true;
        }

        try {
            handler(message);

            acknowledgedIds.insert(message.id);
            message.status = DeliveryStatus::ACKNOWLEDGED;

            cout << "ACK: " << message.id << '\n';
            return true;

        } catch (const exception& error) {
            ++message.attempts;

            cerr << "Delivery failed: "
                 << error.what() << '\n';

            if (message.attempts > maxRetries) {
                message.status = DeliveryStatus::DEAD_LETTERED;
                deadLetters.push_back(move(message));
            } else {
                queues[topic].push_back(move(message));
            }

            return false;
        }
    }

    size_t deadLetterCount() const {
        return deadLetters.size();
    }

    size_t pendingCount(const string& topic) const {
        auto it = queues.find(topic);

        return it == queues.end() ? 0 : it->second.size();
    }
};

// ============================================================
// 4. Idempotent Event Consumer
// ============================================================

class InventoryConsumer {
private:
    unordered_set<string> processedEvents;
    unordered_map<int, int> inventory;

public:
    void process(
        const Message& message,
        int productId,
        int quantity
    ) {
        if (productId <= 0 || quantity <= 0) {
            throw invalid_argument("Invalid inventory event");
        }

        if (message.id.empty()) {
            throw invalid_argument("Missing event ID");
        }

        if (processedEvents.count(message.id)) {
            cout << "Duplicate ignored: "
                 << message.id << '\n';
            return;
        }

        // In production, the inventory update and event ID
        // insertion must share one database transaction.
        inventory[productId] += quantity;
        processedEvents.insert(message.id);
    }

    int quantityFor(int productId) const {
        auto it = inventory.find(productId);
        return it == inventory.end() ? 0 : it->second;
    }
};

// ============================================================
// 5. Order Orchestration
// ============================================================

class OrderService {
private:
    unordered_map<int, Order> orders;
    int nextOrderId = 5001;

public:
    Order createOrder(int productId, int quantity) {
        if (productId <= 0 || quantity <= 0 || quantity > 1000) {
            throw invalid_argument("Invalid order parameters");
        }

        Order order{
            nextOrderId++,
            productId,
            quantity,
            OrderStatus::CREATED
        };

        orders.emplace(order.id, order);
        return order;
    }

    void transition(int orderId, OrderStatus next) {
        auto it = orders.find(orderId);

        if (it == orders.end()) {
            throw runtime_error("Order not found");
        }

        const OrderStatus current = it->second.status;

        bool allowed =
            (current == OrderStatus::CREATED &&
             next == OrderStatus::INVENTORY_RESERVED) ||
            (current == OrderStatus::INVENTORY_RESERVED &&
             next == OrderStatus::PAYMENT_PENDING) ||
            (current == OrderStatus::PAYMENT_PENDING &&
             next == OrderStatus::CONFIRMED) ||
            (current != OrderStatus::CONFIRMED &&
             next == OrderStatus::FAILED);

        if (!allowed) {
            throw logic_error("Invalid order state transition");
        }

        it->second.status = next;
    }
};

// ============================================================
// 6. Communication Security Policy
// ============================================================

struct CommunicationPolicy {
    Protocol protocol;
    bool authenticated;
    bool encrypted;
    int timeoutMilliseconds;
    size_t maximumPayloadBytes;

    void validate() const {
        if (!authenticated || !encrypted) {
            throw runtime_error(
                "Authenticated encryption is required"
            );
        }

        if (timeoutMilliseconds <= 0) {
            throw invalid_argument("Invalid timeout");
        }

        if (maximumPayloadBytes == 0) {
            throw invalid_argument("Invalid payload limit");
        }
    }
};

// ============================================================
// 7. Demonstration
// ============================================================

string rpcStatusName(RpcStatus status) {
    switch (status) {
        case RpcStatus::OK: return "OK";
        case RpcStatus::INVALID_ARGUMENT: return "INVALID_ARGUMENT";
        case RpcStatus::NOT_FOUND: return "NOT_FOUND";
        case RpcStatus::UNAVAILABLE: return "UNAVAILABLE";
        case RpcStatus::INTERNAL: return "INTERNAL";
    }

    return "UNKNOWN";
}

int main() {
    try {
        cout << "=== SERVICE COMMUNICATION ===\n";

        ProductRepository repository;

        // REST
        cout << "\n--- REST ---\n";

        RestApi rest(repository);

        HttpResponse response = rest.getProduct(101);

        cout << "GET status: "
             << response.statusCode << '\n';
        cout << response.body << '\n';

        HttpResponse created = rest.createProduct(
            "Keyboard",
            2500.0
        );

        cout << "POST status: "
             << created.statusCode << '\n';

        HttpResponse missing = rest.getProduct(999);

        cout << "Missing resource: "
             << missing.statusCode << '\n';

        // RPC
        cout << "\n--- gRPC-STYLE RPC ---\n";

        ProductRpcService rpcService(repository);
        RpcClient rpcClient(rpcService);

        RpcResult rpc = rpcClient.getProduct(101);

        cout << "RPC status: "
             << rpcStatusName(rpc.status) << '\n';

        if (rpc.product) {
            cout << "Product: "
                 << rpc.product->name << '\n';
        }

        RpcResult invalidRpc = rpcClient.getProduct(-1);

        cout << "Invalid RPC: "
             << rpcStatusName(invalidRpc.status) << '\n';

        // Messaging
        cout << "\n--- MESSAGING ---\n";

        MessageBroker broker(2);
        InventoryConsumer consumer;

        broker.subscribe("inventory.events", "inventory-service");

        Message event{
            "event-1001",
            "inventory.events",
            "StockReserved",
            "{\"productId\":101,\"quantity\":5}"
        };

        broker.publish(event);

        auto handler = [&consumer](const Message& message) {
            consumer.process(message, 101, 5);
        };

        broker.consumeOne("inventory.events", handler);

        cout << "Inventory quantity: "
             << consumer.quantityFor(101) << '\n';

        // Duplicate delivery.
        consumer.process(event, 101, 5);

        if (consumer.quantityFor(101) != 5) {
            throw runtime_error("Idempotency failure");
        }

        // Dead-letter handling.
        MessageBroker failingBroker(1);

        failingBroker.subscribe("payments", "payment-service");

        failingBroker.publish({
            "payment-5001",
            "payments",
            "PaymentRequested",
            "{\"orderId\":5001}"
        });

        auto failingHandler = [](const Message&) {
            throw runtime_error("Payment service unavailable");
        };

        failingBroker.consumeOne("payments", failingHandler);
        failingBroker.consumeOne("payments", failingHandler);

        cout << "Dead letters: "
             << failingBroker.deadLetterCount() << '\n';

        // Order workflow.
        cout << "\n--- ORDER WORKFLOW ---\n";

        OrderService orderService;
        Order order = orderService.createOrder(101, 2);

        orderService.transition(
            order.id,
            OrderStatus::INVENTORY_RESERVED
        );

        orderService.transition(
            order.id,
            OrderStatus::PAYMENT_PENDING
        );

        orderService.transition(
            order.id,
            OrderStatus::CONFIRMED
        );

        cout << "Order confirmed: "
             << order.id << '\n';

        // Security.
        cout << "\n--- SECURITY ---\n";

        CommunicationPolicy policy{
            Protocol::GRPC,
            true,
            true,
            2000,
            16384
        };

        policy.validate();

        cout << "Communication policy accepted\n";

        cout << "\nAll C++17 demonstrations completed.\n";

    } catch (const exception& error) {
        cerr << "Application error: "
             << error.what() << '\n';

        return 1;
    }

    return 0;
}
