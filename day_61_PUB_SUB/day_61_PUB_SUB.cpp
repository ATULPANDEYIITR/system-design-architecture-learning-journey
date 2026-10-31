#include <algorithm>
#include <chrono>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

enum class DeliveryState {
    Delivered,
    Failed,
    Skipped
};

enum class ReviewState {
    Active,
    Suspended
};

struct Event {
    std::string id;
    std::string topic;
    std::string payload;
    std::chrono::system_clock::time_point createdAt;
};

struct DeliveryResult {
    std::string subscriberId;
    DeliveryState state;
    std::string error;
};

struct Subscriber {
    std::string id;
    std::function<void(const Event&)> handler;
    std::size_t maxFailures{3};
    std::size_t failures{0};
    ReviewState state{ReviewState::Active};
};

class PubSubError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ValidationError : public PubSubError {
public:
    using PubSubError::PubSubError;
};

class Broker {
private:
    std::unordered_map<std::string, std::map<std::string, Subscriber>> topics;
    std::deque<Event> history;
    std::size_t historyLimit;
    unsigned long long sequence{0};

    static void validateTopic(const std::string& topic) {
        if (topic.empty()) {
            throw ValidationError("Topic cannot be empty");
        }

        if (topic.size() > 128) {
            throw ValidationError("Topic exceeds 128 characters");
        }

        if (std::any_of(topic.begin(), topic.end(),
                        [](unsigned char c) { return std::isspace(c); })) {
            throw ValidationError("Topic cannot contain whitespace");
        }
    }

    std::string makeEventId() {
        std::ostringstream output;
        output << "EVT-" << std::setw(8) << std::setfill('0') << ++sequence;
        return output.str();
    }

public:
    explicit Broker(std::size_t historyLimit = 1000)
        : historyLimit(historyLimit) {
        if (historyLimit == 0) {
            throw ValidationError("historyLimit must be positive");
        }
    }

    void subscribe(
        const std::string& topic,
        const std::string& subscriberId,
        std::function<void(const Event&)> handler,
        std::size_t maxFailures = 3
    ) {
        validateTopic(topic);

        if (subscriberId.empty()) {
            throw ValidationError("Subscriber ID cannot be empty");
        }

        if (!handler) {
            throw ValidationError("Subscriber handler is required");
        }

        if (maxFailures == 0) {
            throw ValidationError("maxFailures must be positive");
        }

        auto& subscribers = topics[topic];

        if (subscribers.contains(subscriberId)) {
            throw ValidationError(
                "Subscriber is already registered for the topic"
            );
        }

        subscribers.emplace(
            subscriberId,
            Subscriber{
                subscriberId,
                std::move(handler),
                maxFailures,
                0,
                ReviewState::Active
            }
        );
    }

    bool unsubscribe(
        const std::string& topic,
        const std::string& subscriberId
    ) {
        validateTopic(topic);

        auto topicIt = topics.find(topic);
        if (topicIt == topics.end()) {
            return false;
        }

        bool removed = topicIt->second.erase(subscriberId) > 0;

        if (topicIt->second.empty()) {
            topics.erase(topicIt);
        }

        return removed;
    }

    std::vector<DeliveryResult> publish(
        const std::string& topic,
        const std::string& payload
    ) {
        validateTopic(topic);

        if (payload.empty()) {
            throw ValidationError("Event payload cannot be empty");
        }

        Event event{
            makeEventId(),
            topic,
            payload,
            std::chrono::system_clock::now()
        };

        history.push_back(event);
        if (history.size() > historyLimit) {
            history.pop_front();
        }

        std::vector<DeliveryResult> results;

        auto topicIt = topics.find(topic);
        if (topicIt == topics.end()) {
            return results;
        }

        /*
         * Subscriber callbacks are executed without a global broker lock.
         * A production broker would normally place delivery on a durable
         * queue so slow consumers do not block the publishing process.
         */
        for (auto& [id, subscriber] : topicIt->second) {
            if (subscriber.state == ReviewState::Suspended) {
                results.push_back({
                    id,
                    DeliveryState::Skipped,
                    "Subscriber suspended after repeated failures"
                });
                continue;
            }

            try {
                subscriber.handler(event);
                subscriber.failures = 0;

                results.push_back({
                    id,
                    DeliveryState::Delivered,
                    ""
                });
            } catch (const std::exception& error) {
                ++subscriber.failures;

                if (subscriber.failures >= subscriber.maxFailures) {
                    subscriber.state = ReviewState::Suspended;
                }

                results.push_back({
                    id,
                    DeliveryState::Failed,
                    error.what()
                });
            }
        }

        return results;
    }

    std::vector<Event> retainedEvents(const std::string& topic) const {
        validateTopic(topic);

        std::vector<Event> result;

        std::copy_if(
            history.begin(),
            history.end(),
            std::back_inserter(result),
            [&topic](const Event& event) {
                return event.topic == topic;
            }
        );

        return result;
    }

    std::map<std::string, std::size_t> topicSubscriberCounts() const {
        std::map<std::string, std::size_t> counts;

        for (const auto& [topic, subscribers] : topics) {
            counts[topic] = subscribers.size();
        }

        return counts;
    }
};

static std::string stateToString(DeliveryState state) {
    switch (state) {
        case DeliveryState::Delivered:
            return "delivered";
        case DeliveryState::Failed:
            return "failed";
        case DeliveryState::Skipped:
            return "skipped";
    }

    return "unknown";
}

int main() {
    try {
        Broker broker(100);

        broker.subscribe(
            "security.alert",
            "soc-dashboard",
            [](const Event& event) {
                std::cout << "[SOC] " << event.id
                          << " payload=" << event.payload << '\n';
            }
        );

        broker.subscribe(
            "security.alert",
            "incident-database",
            [](const Event& event) {
                std::cout << "[DATABASE] storing " << event.id << '\n';
            }
        );

        broker.subscribe(
            "security.alert",
            "notification-gateway",
            [](const Event& event) {
                if (event.payload.find("severity=critical") !=
                    std::string::npos) {
                    throw std::runtime_error(
                        "Notification gateway rate limit"
                    );
                }

                std::cout << "[NOTIFY] sent " << event.id << '\n';
            },
            2
        );

        auto first = broker.publish(
            "security.alert",
            "incident=INC-1001 severity=high source=firewall"
        );

        std::cout << "\nFirst delivery:\n";
        for (const auto& result : first) {
            std::cout << result.subscriberId
                      << " -> " << stateToString(result.state)
                      << (result.error.empty()
                          ? ""
                          : " (" + result.error + ")")
                      << '\n';
        }

        auto critical = broker.publish(
            "security.alert",
            "incident=INC-1002 severity=critical source=ids"
        );

        std::cout << "\nCritical delivery:\n";
        for (const auto& result : critical) {
            std::cout << result.subscriberId
                      << " -> " << stateToString(result.state)
                      << (result.error.empty()
                          ? ""
                          : " (" + result.error + ")")
                      << '\n';
        }

        auto secondCritical = broker.publish(
            "security.alert",
            "incident=INC-1003 severity=critical source=endpoint"
        );

        std::cout << "\nAfter repeated failure:\n";
        for (const auto& result : secondCritical) {
            std::cout << result.subscriberId
                      << " -> " << stateToString(result.state)
                      << (result.error.empty()
                          ? ""
                          : " (" + result.error + ")")
                      << '\n';
        }

        std::cout << "\nRetained events: "
                  << broker.retainedEvents("security.alert").size()
                  << '\n';

        std::cout << "\nSubscriber counts:\n";
        for (const auto& [topic, count] : broker.topicSubscriberCounts()) {
            std::cout << topic << ": " << count << '\n';
        }

        if (!broker.unsubscribe("security.alert", "incident-database")) {
            throw ValidationError("Expected subscriber was not found");
        }

        try {
            broker.publish("security alert", "invalid");
        } catch (const ValidationError& error) {
            std::cout << "\nValidation rejected: "
                      << error.what() << '\n';
        }
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
