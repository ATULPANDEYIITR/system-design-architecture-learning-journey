#include <algorithm>
#include <chrono>
#include <exception>
#include <iostream>
#include <optional>
#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

enum class MessageState {
    Ready,
    InFlight,
    Acknowledged,
    DeadLettered
};

enum class DeliveryResult {
    Acknowledge,
    Retry,
    Reject
};

struct Message {
    std::string id;
    std::string payload;
    std::string producer;
    std::unordered_map<std::string, std::string> headers;
    MessageState state{MessageState::Ready};
    unsigned attempts{0};
};

struct QueueDefinition {
    std::string name;
    bool durable{true};
    unsigned maxAttempts{3};
    std::queue<std::string> ready;
    std::vector<std::string> deadLetters;
};

struct Consumer {
    std::string id;
    std::string queue;
    std::size_t prefetch{1};
    std::unordered_set<std::string> inFlight;
};

class Broker {
private:
    std::unordered_map<std::string, QueueDefinition> queues_;
    std::unordered_map<std::string, Message> messages_;
    std::unordered_map<std::string, Consumer> consumers_;
    unsigned long long sequence_{0};

    std::string nextMessageId() {
        return "msg-" + std::to_string(++sequence_);
    }

    QueueDefinition& requireQueue(const std::string& name) {
        auto it = queues_.find(name);
        if (it == queues_.end()) {
            throw std::runtime_error("Queue not found: " + name);
        }
        return it->second;
    }

    Consumer& requireConsumer(const std::string& id) {
        auto it = consumers_.find(id);
        if (it == consumers_.end()) {
            throw std::runtime_error("Consumer not found: " + id);
        }
        return it->second;
    }

public:
    void declareQueue(
        const std::string& name,
        bool durable,
        unsigned maxAttempts
    ) {
        if (name.empty()) {
            throw std::invalid_argument("Queue name cannot be empty");
        }

        if (maxAttempts == 0) {
            throw std::invalid_argument("maxAttempts must be positive");
        }

        auto existing = queues_.find(name);

        if (existing != queues_.end()) {
            if (existing->second.durable != durable) {
                throw std::runtime_error("Queue durability conflict");
            }
            return;
        }

        queues_.emplace(
            name,
            QueueDefinition{name, durable, maxAttempts}
        );
    }

    std::string publish(
        const std::string& queueName,
        const std::string& payload,
        const std::string& producer,
        std::unordered_map<std::string, std::string> headers
    ) {
        QueueDefinition& queue = requireQueue(queueName);

        if (payload.empty()) {
            throw std::invalid_argument("Payload cannot be empty");
        }

        if (producer.empty()) {
            throw std::invalid_argument("Producer cannot be empty");
        }

        const std::string id = nextMessageId();

        Message message;
        message.id = id;
        message.payload = payload;
        message.producer = producer;
        message.headers = std::move(headers);

        messages_.emplace(id, std::move(message));
        queue.ready.push(id);

        return id;
    }

    void registerConsumer(
        const std::string& id,
        const std::string& queueName,
        std::size_t prefetch
    ) {
        if (consumers_.contains(id)) {
            throw std::runtime_error("Consumer already exists");
        }

        requireQueue(queueName);

        if (prefetch == 0) {
            throw std::invalid_argument("Prefetch must be positive");
        }

        consumers_.emplace(
            id,
            Consumer{id, queueName, prefetch, {}}
        );
    }

    std::optional<std::string> deliver(const std::string& consumerId) {
        Consumer& consumer = requireConsumer(consumerId);
        QueueDefinition& queue = requireQueue(consumer.queue);

        if (consumer.inFlight.size() >= consumer.prefetch) {
            return std::nullopt;
        }

        while (!queue.ready.empty()) {
            const std::string messageId = queue.ready.front();
            queue.ready.pop();

            auto messageIt = messages_.find(messageId);
            if (messageIt == messages_.end()) {
                continue;
            }

            Message& message = messageIt->second;

            if (message.state != MessageState::Ready) {
                continue;
            }

            ++message.attempts;
            message.state = MessageState::InFlight;
            consumer.inFlight.insert(messageId);

            return messageId;
        }

        return std::nullopt;
    }

    void complete(
        const std::string& consumerId,
        const std::string& messageId,
        DeliveryResult result
    ) {
        Consumer& consumer = requireConsumer(consumerId);
        QueueDefinition& queue = requireQueue(consumer.queue);

        auto messageIt = messages_.find(messageId);
        if (messageIt == messages_.end()) {
            throw std::runtime_error("Message not found");
        }

        Message& message = messageIt->second;

        if (!consumer.inFlight.contains(messageId)) {
            throw std::runtime_error(
                "Consumer does not own the in-flight message"
            );
        }

        consumer.inFlight.erase(messageId);

        switch (result) {
            case DeliveryResult::Acknowledge:
                message.state = MessageState::Acknowledged;
                break;

            case DeliveryResult::Retry:
                if (message.attempts >= queue.maxAttempts) {
                    message.state = MessageState::DeadLettered;
                    queue.deadLetters.push_back(messageId);
                } else {
                    message.state = MessageState::Ready;
                    queue.ready.push(messageId);
                }
                break;

            case DeliveryResult::Reject:
                message.state = MessageState::DeadLettered;
                queue.deadLetters.push_back(messageId);
                break;
        }
    }

    std::size_t process(
        const std::string& consumerId,
        const std::function<DeliveryResult(const Message&)>& handler
    ) {
        Consumer& consumer = requireConsumer(consumerId);
        std::size_t processed = 0;

        while (consumer.inFlight.size() < consumer.prefetch) {
            const auto messageId = deliver(consumerId);

            if (!messageId.has_value()) {
                break;
            }

            const Message& message = messages_.at(*messageId);
            DeliveryResult result = DeliveryResult::Retry;

            try {
                result = handler(message);
            } catch (const std::exception& ex) {
                std::cerr
                    << "[handler-error] "
                    << message.id
                    << ": "
                    << ex.what()
                    << '\n';
                result = DeliveryResult::Retry;
            }

            complete(consumerId, *messageId, result);
            ++processed;
        }

        return processed;
    }

    void printStats(const std::string& queueName) const {
        const auto queueIt = queues_.find(queueName);

        if (queueIt == queues_.end()) {
            throw std::runtime_error("Queue not found");
        }

        const QueueDefinition& queue = queueIt->second;

        std::size_t acknowledged = 0;
        std::size_t inFlight = 0;

        for (const auto& [id, message] : messages_) {
            if (message.state == MessageState::Acknowledged) {
                ++acknowledged;
            }
            if (message.state == MessageState::InFlight) {
                ++inFlight;
            }
        }

        std::cout
            << "ready=" << queue.ready.size()
            << " in_flight=" << inFlight
            << " acknowledged=" << acknowledged
            << " dead_lettered=" << queue.deadLetters.size()
            << '\n';
    }

    const Message& message(const std::string& id) const {
        return messages_.at(id);
    }
};

int main() {
    try {
        Broker broker;

        broker.declareQueue("payments", true, 3);

        broker.publish(
            "payments",
            "Authorize payment",
            "checkout-service",
            {{"payment_id", "PAY-1001"}}
        );

        broker.publish(
            "payments",
            "Capture payment",
            "checkout-service",
            {{"payment_id", "PAY-1002"}}
        );

        broker.publish(
            "payments",
            "Capture payment",
            "checkout-service",
            {{"payment_id", "PAY-FAIL"}}
        );

        broker.registerConsumer(
            "payment-worker",
            "payments",
            2
        );

        broker.printStats("payments");

        const auto handler =
            [](const Message& message) -> DeliveryResult {
                const auto it = message.headers.find("payment_id");

                if (it == message.headers.end()) {
                    return DeliveryResult::Reject;
                }

                const std::string& paymentId = it->second;

                if (paymentId == "PAY-FAIL") {
                    std::cout
                        << "Transient payment failure: "
                        << paymentId
                        << " attempt="
                        << message.attempts
                        << '\n';
                    return DeliveryResult::Retry;
                }

                std::cout
                    << "Processed payment: "
                    << paymentId
                    << '\n';

                return DeliveryResult::Acknowledge;
            };

        for (int cycle = 1; cycle <= 5; ++cycle) {
            const std::size_t processed =
                broker.process("payment-worker", handler);

            std::cout
                << "cycle="
                << cycle
                << " processed="
                << processed
                << '\n';

            broker.printStats("payments");

            if (processed == 0) {
                break;
            }
        }

        broker.publish(
            "payments",
            "Invalid message",
            "bad-producer",
            {}
        );

        broker.process(
            "payment-worker",
            [](const Message& message) {
                if (!message.headers.contains("payment_id")) {
                    std::cout
                        << "Rejected message without payment_id\n";
                    return DeliveryResult::Reject;
                }
                return DeliveryResult::Acknowledge;
            }
        );

        broker.printStats("payments");

        std::cout
            << "Message queue simulation completed.\n";

    } catch (const std::exception& ex) {
        std::cerr
            << "Fatal error: "
            << ex.what()
            << '\n';
        return 1;
    }

    return 0;
}
