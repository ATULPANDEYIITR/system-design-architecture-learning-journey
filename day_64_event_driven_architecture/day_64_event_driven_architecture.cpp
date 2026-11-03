#include <algorithm>
#include <chrono>
#include <exception>
#include <functional>
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
    OrderCreated,
    PaymentAuthorized,
    OrderConfirmed,
    OrderCancelled
};

std::string toString(EventType type) {
    switch (type) {
        case EventType::OrderCreated:
            return "order.created";
        case EventType::PaymentAuthorized:
            return "payment.authorized";
        case EventType::OrderConfirmed:
            return "order.confirmed";
        case EventType::OrderCancelled:
            return "order.cancelled";
    }
    throw std::invalid_argument("Unknown event type");
}

struct Event {
    std::string id;
    EventType type;
    std::string aggregateId;
    std::map<std::string, std::string> payload;
    std::string producer;
    std::chrono::system_clock::time_point occurredAt;
};

struct Order {
    std::string id;
    std::string customerId;
    double amount;
    std::string status;
};

class EventBus {
public:
    using Handler = std::function<void(const Event&)>;

    void subscribe(
        EventType type,
        const std::string& consumer,
        Handler handler
    ) {
        if (consumer.empty()) {
            throw std::invalid_argument("Consumer name cannot be empty");
        }

        subscriptions[type].push_back(
            Subscription{consumer, std::move(handler)}
        );
    }

    void publish(Event event) {
        if (event.id.empty() || event.aggregateId.empty()) {
            throw std::invalid_argument("Event identity is required");
        }

        queue.push_back(std::move(event));
    }

    void process() {
        while (!queue.empty()) {
            Event event = std::move(queue.front());
            queue.erase(queue.begin());

            auto it = subscriptions.find(event.type);
            if (it == subscriptions.end()) {
                continue;
            }

            for (const auto& subscription : it->second) {
                const std::string key =
                    event.id + ":" + subscription.consumer;

                if (processedDeliveries.contains(key)) {
                    continue;
                }

                try {
                    subscription.handler(event);
                    processedDeliveries.insert(key);
                } catch (const std::exception& ex) {
                    deadLetters.push_back(
                        Failure{event.id, subscription.consumer, ex.what()}
                    );
                }
            }
        }
    }

    std::size_t pending() const {
        return queue.size();
    }

    struct Failure {
        std::string eventId;
        std::string consumer;
        std::string reason;
    };

    const std::vector<Failure>& getDeadLetters() const {
        return deadLetters;
    }

private:
    struct Subscription {
        std::string consumer;
        Handler handler;
    };

    std::map<EventType, std::vector<Subscription>> subscriptions;
    std::vector<Event> queue;
    std::set<std::string> processedDeliveries;
    std::vector<Failure> deadLetters;
};

class OrderService {
public:
    explicit OrderService(EventBus& bus) : bus(bus) {}

    std::string createOrder(
        const std::string& customerId,
        double amount
    ) {
        if (customerId.empty()) {
            throw std::invalid_argument("Customer ID cannot be empty");
        }

        if (!std::isfinite(amount) || amount <= 0.0) {
            throw std::invalid_argument("Amount must be positive");
        }

        const std::string id =
            "ORD-" + std::to_string(nextId++);

        orders[id] = Order{
            id,
            customerId,
            amount,
            "CREATED"
        };

        Event event{
            "EVT-" + std::to_string(nextEventId++),
            EventType::OrderCreated,
            id,
            {
                {"customer_id", customerId},
                {"amount", std::to_string(amount)}
            },
            "order-service",
            std::chrono::system_clock::now()
        };

        bus.publish(std::move(event));
        return id;
    }

private:
    EventBus& bus;
    std::map<std::string, Order> orders;
    int nextId = 1001;
    int nextEventId = 1;
};

class PaymentConsumer {
public:
    explicit PaymentConsumer(EventBus& bus) {
        bus.subscribe(
            EventType::OrderCreated,
            "payment-service",
            [this](const Event& event) {
                process(event);
            }
        );
    }

    std::size_t authorizationCount() const {
        return authorized.size();
    }

private:
    void process(const Event& event) {
        const auto amountIt = event.payload.find("amount");

        if (amountIt == event.payload.end()) {
            throw std::runtime_error("Missing payment amount");
        }

        authorized.insert(event.aggregateId);

        std::cout
            << "[payment-service] authorized "
            << event.aggregateId
            << " amount=" << amountIt->second
            << '\n';
    }

    std::set<std::string> authorized;
};

class NotificationConsumer {
public:
    explicit NotificationConsumer(EventBus& bus) {
        bus.subscribe(
            EventType::OrderCreated,
            "notification-service",
            [this](const Event& event) {
                messages.push_back(
                    "Created: " + event.aggregateId
                );
            }
        );

        bus.subscribe(
            EventType::OrderConfirmed,
            "notification-service",
            [this](const Event& event) {
                messages.push_back(
                    "Confirmed: " + event.aggregateId
                );
            }
        );
    }

    std::size_t count() const {
        return messages.size();
    }

private:
    std::vector<std::string> messages;
};

class AnalyticsConsumer {
public:
    explicit AnalyticsConsumer(EventBus& bus) {
        for (EventType type : {
            EventType::OrderCreated,
            EventType::PaymentAuthorized,
            EventType::OrderConfirmed,
            EventType::OrderCancelled
        }) {
            bus.subscribe(
                type,
                "analytics-service",
                [this](const Event& event) {
                    ++counts[event.type];
                }
            );
        }
    }

    int count(EventType type) const {
        auto it = counts.find(type);
        return it == counts.end() ? 0 : it->second;
    }

private:
    std::map<EventType, int> counts;
};

int main() {
    try {
        EventBus bus;

        PaymentConsumer payment(bus);
        NotificationConsumer notifications(bus);
        AnalyticsConsumer analytics(bus);

        OrderService orders(bus);

        const std::string orderId =
            orders.createOrder("customer-1001", 1499.50);

        std::cout
            << "Pending before processing: "
            << bus.pending() << '\n';

        bus.process();

        std::cout
            << "Pending after processing: "
            << bus.pending() << '\n';

        std::cout
            << "Payment authorizations: "
            << payment.authorizationCount() << '\n';

        std::cout
            << "Notifications: "
            << notifications.count() << '\n';

        std::cout
            << "Created events: "
            << analytics.count(EventType::OrderCreated)
            << '\n';

        // Adding an audit consumer does not require changing the producer.
        std::vector<std::string> auditLog;

        bus.subscribe(
            EventType::OrderCreated,
            "audit-service",
            [&auditLog](const Event& event) {
                auditLog.push_back(event.id);
            }
        );

        orders.createOrder("customer-1002", 250.0);
        bus.process();

        std::cout
            << "Audit records: "
            << auditLog.size() << '\n';

        // Failure case: malformed event is isolated from other consumers.
        bus.subscribe(
            EventType::OrderConfirmed,
            "failing-service",
            [](const Event&) {
                throw std::runtime_error(
                    "Downstream service unavailable"
                );
            }
        );

        Event confirmed{
            "EVT-CONFIRM-1",
            EventType::OrderConfirmed,
            orderId,
            {{"confirmed_by", "workflow-service"}},
            "workflow-service",
            std::chrono::system_clock::now()
        };

        bus.publish(confirmed);
        bus.process();

        std::cout
            << "Dead-lettered deliveries: "
            << bus.getDeadLetters().size() << '\n';

        // Production considerations:
        // 1. Persist events before acknowledging publication.
        // 2. Use broker partitions for scalable consumer throughput.
        // 3. Preserve per-aggregate ordering when required.
        // 4. Use retry limits and durable dead-letter queues.
        // 5. Authenticate producers and consumers.
        // 6. Do not place credentials or unnecessary sensitive data in events.
        // 7. Monitor event lag, processing latency, and failure rates.

    } catch (const std::exception& ex) {
        std::cerr << "Fatal error: " << ex.what() << '\n';
        return 1;
    }

    return 0;
}
