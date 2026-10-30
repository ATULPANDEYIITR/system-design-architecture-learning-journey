#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <exception>
#include <functional>
#include <iostream>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using Clock = std::chrono::steady_clock;

enum class MessageState {
    Ready,
    InFlight,
    Acknowledged,
    DeadLettered
};

struct Delivery {
    std::string messageId;
    std::string payload;
    std::string consumerId;
    std::string receipt;
    int attempt;
};

struct QueueMetrics {
    std::size_t ready = 0;
    std::size_t inFlight = 0;
    std::size_t acknowledged = 0;
    std::size_t deadLettered = 0;
};

class QueueError : public std::runtime_error {
public:
    explicit QueueError(const std::string& message)
        : std::runtime_error(message) {}
};

class QueueFullError : public QueueError {
public:
    explicit QueueFullError(const std::string& message)
        : QueueError(message) {}
};

class InvalidDeliveryError : public QueueError {
public:
    explicit InvalidDeliveryError(const std::string& message)
        : QueueError(message) {}
};

class StaleDeliveryError : public InvalidDeliveryError {
public:
    explicit StaleDeliveryError(const std::string& message)
        : InvalidDeliveryError(message) {}
};

class WorkQueue {
private:
    struct Message {
        std::string id;
        std::string payload;
        MessageState state = MessageState::Ready;
        int attempts = 0;
        std::string consumerId;
        std::string receipt;
        Clock::time_point leaseDeadline{};
        std::string lastError;
    };

    const std::size_t capacity_;
    const int maxAttempts_;
    const std::chrono::milliseconds visibilityTimeout_;

    mutable std::mutex mutex_;
    std::condition_variable changed_;
    std::unordered_map<std::string, Message> messages_;
    std::deque<std::string> ready_;
    std::size_t outstanding_ = 0;
    std::size_t receiptSequence_ = 0;
    bool closed_ = false;

    static std::string stateName(MessageState state) {
        switch (state) {
            case MessageState::Ready:
                return "READY";
            case MessageState::InFlight:
                return "IN_FLIGHT";
            case MessageState::Acknowledged:
                return "ACKNOWLEDGED";
            case MessageState::DeadLettered:
                return "DEAD_LETTERED";
        }
        return "UNKNOWN";
    }

    void clearLease(Message& message) {
        message.consumerId.clear();
        message.receipt.clear();
        message.leaseDeadline = Clock::time_point{};
    }

    void expireLeasesLocked(Clock::time_point now) {
        for (auto& [id, message] : messages_) {
            if (
                message.state != MessageState::InFlight ||
                message.leaseDeadline > now
            ) {
                continue;
            }

            clearLease(message);
            message.lastError = "Visibility timeout expired.";

            if (message.attempts >= maxAttempts_) {
                message.state = MessageState::DeadLettered;
                --outstanding_;
            } else {
                message.state = MessageState::Ready;
                ready_.push_back(id);
            }
        }

        changed_.notify_all();
    }

    Message& activeMessageLocked(const Delivery& delivery) {
        auto iterator = messages_.find(delivery.messageId);

        if (iterator == messages_.end()) {
            throw InvalidDeliveryError("Unknown message.");
        }

        Message& message = iterator->second;

        if (message.state == MessageState::Acknowledged) {
            throw InvalidDeliveryError("Message is already acknowledged.");
        }

        if (message.state != MessageState::InFlight) {
            throw StaleDeliveryError("Message is not in flight.");
        }

        if (
            message.receipt != delivery.receipt ||
            message.consumerId != delivery.consumerId
        ) {
            throw StaleDeliveryError(
                "Receipt does not match the active delivery."
            );
        }

        if (Clock::now() >= message.leaseDeadline) {
            expireLeasesLocked(Clock::now());
            throw StaleDeliveryError("Delivery lease has expired.");
        }

        return message;
    }

public:
    WorkQueue(
        std::size_t capacity,
        int maxAttempts,
        std::chrono::milliseconds visibilityTimeout
    )
        : capacity_(capacity),
          maxAttempts_(maxAttempts),
          visibilityTimeout_(visibilityTimeout) {
        if (capacity_ == 0) {
            throw std::invalid_argument("Capacity must be positive.");
        }

        if (maxAttempts_ < 1) {
            throw std::invalid_argument("Maximum attempts must be positive.");
        }

        if (visibilityTimeout_.count() <= 0) {
            throw std::invalid_argument(
                "Visibility timeout must be positive."
            );
        }
    }

    WorkQueue(const WorkQueue&) = delete;
    WorkQueue& operator=(const WorkQueue&) = delete;

    bool publish(const std::string& id, const std::string& payload) {
        if (id.empty() || payload.empty()) {
            throw std::invalid_argument(
                "Message identifier and payload cannot be empty."
            );
        }

        std::lock_guard<std::mutex> guard(mutex_);

        if (closed_) {
            throw QueueError("Cannot publish to a closed queue.");
        }

        if (messages_.find(id) != messages_.end()) {
            throw QueueError("Duplicate message identifier: " + id);
        }

        if (outstanding_ >= capacity_) {
            return false;
        }

        Message message;
        message.id = id;
        message.payload = payload;

        messages_.emplace(id, std::move(message));
        ready_.push_back(id);
        ++outstanding_;

        changed_.notify_one();
        return true;
    }

    std::optional<Delivery> receive(
        const std::string& consumerId
    ) {
        if (consumerId.empty()) {
            throw std::invalid_argument(
                "Consumer identifier cannot be empty."
            );
        }

        std::unique_lock<std::mutex> lock(mutex_);

        while (true) {
            auto now = Clock::now();
            expireLeasesLocked(now);

            while (!ready_.empty()) {
                const std::string id = ready_.front();
                ready_.pop_front();

                auto iterator = messages_.find(id);

                if (
                    iterator == messages_.end() ||
                    iterator->second.state != MessageState::Ready
                ) {
                    continue;
                }

                Message& message = iterator->second;

                message.state = MessageState::InFlight;
                ++message.attempts;
                message.consumerId = consumerId;

                // The receipt changes on every delivery attempt. A stale
                // worker therefore cannot settle a newer delivery.
                message.receipt =
                    message.id + ":" +
                    std::to_string(message.attempts) + ":" +
                    std::to_string(++receiptSequence_);

                message.leaseDeadline = now + visibilityTimeout_;

                return Delivery{
                    message.id,
                    message.payload,
                    consumerId,
                    message.receipt,
                    message.attempts
                };
            }

            // The queue stops accepting new work after close(), but waits
            // while outstanding deliveries may still expire and be retried.
            if (closed_ && outstanding_ == 0) {
                return std::nullopt;
            }

            auto wakeAt = Clock::now() + std::chrono::milliseconds(100);

            for (const auto& [id, message] : messages_) {
                if (
                    message.state == MessageState::InFlight &&
                    message.leaseDeadline < wakeAt
                ) {
                    wakeAt = message.leaseDeadline;
                }
            }

            changed_.wait_until(lock, wakeAt);
        }
    }

    void acknowledge(const Delivery& delivery) {
        std::lock_guard<std::mutex> guard(mutex_);

        Message& message = activeMessageLocked(delivery);

        message.state = MessageState::Acknowledged;
        clearLease(message);
        --outstanding_;

        changed_.notify_all();
    }

    MessageState reject(
        const Delivery& delivery,
        bool requeue,
        const std::string& reason
    ) {
        std::lock_guard<std::mutex> guard(mutex_);

        Message& message = activeMessageLocked(delivery);

        clearLease(message);
        message.lastError = reason;

        if (requeue && message.attempts < maxAttempts_) {
            message.state = MessageState::Ready;
            ready_.push_back(message.id);
        } else {
            message.state = MessageState::DeadLettered;
            --outstanding_;
        }

        changed_.notify_all();
        return message.state;
    }

    QueueMetrics metrics() const {
        std::lock_guard<std::mutex> guard(mutex_);
        QueueMetrics result;

        for (const auto& [id, message] : messages_) {
            switch (message.state) {
                case MessageState::Ready:
                    ++result.ready;
                    break;
                case MessageState::InFlight:
                    ++result.inFlight;
                    break;
                case MessageState::Acknowledged:
                    ++result.acknowledged;
                    break;
                case MessageState::DeadLettered:
                    ++result.deadLettered;
                    break;
            }
        }

        return result;
    }

    std::vector<std::pair<std::string, std::string>>
    deadLetters() const {
        std::lock_guard<std::mutex> guard(mutex_);
        std::vector<std::pair<std::string, std::string>> result;

        for (const auto& [id, message] : messages_) {
            if (message.state == MessageState::DeadLettered) {
                result.emplace_back(id, message.lastError);
            }
        }

        return result;
    }

    void close() {
        std::lock_guard<std::mutex> guard(mutex_);
        closed_ = true;
        changed_.notify_all();
    }
};

class IdempotencyLedger {
private:
    std::mutex mutex_;
    std::unordered_set<std::string> completed_;

public:
    bool recordIfNew(const std::string& messageId) {
        std::lock_guard<std::mutex> guard(mutex_);
        return completed_.insert(messageId).second;
    }
};

void runConsumer(
    WorkQueue& queue,
    const std::string& consumerId,
    IdempotencyLedger& ledger,
    std::mutex& outputMutex
) {
    while (true) {
        std::optional<Delivery> delivery;

        try {
            delivery = queue.receive(consumerId);
        } catch (const std::exception& error) {
            std::lock_guard<std::mutex> outputGuard(outputMutex);
            std::cerr << consumerId << " receive error: "
                      << error.what() << '\n';
            return;
        }

        if (!delivery.has_value()) {
            return;
        }

        try {
            // The poison event intentionally fails every attempt.
            if (delivery->payload == "POISON") {
                throw std::runtime_error(
                    "Business validation rejected the message."
                );
            }

            if (ledger.recordIfNew(delivery->messageId)) {
                std::lock_guard<std::mutex> outputGuard(outputMutex);
                std::cout << consumerId
                          << " processed " << delivery->messageId
                          << " on attempt " << delivery->attempt
                          << '\n';
            } else {
                std::lock_guard<std::mutex> outputGuard(outputMutex);
                std::cout << consumerId
                          << " skipped duplicate business operation for "
                          << delivery->messageId << '\n';
            }

            queue.acknowledge(*delivery);
        } catch (const std::exception& error) {
            MessageState state = queue.reject(
                *delivery,
                true,
                error.what()
            );

            std::lock_guard<std::mutex> outputGuard(outputMutex);
            std::cout << consumerId
                      << " rejected " << delivery->messageId
                      << " on attempt " << delivery->attempt
                      << "; state=" << stateName(state)
                      << "; reason=" << error.what()
                      << '\n';
        }
    }
}

void testVisibilityTimeout() {
    WorkQueue queue(
        2,
        3,
        std::chrono::milliseconds(30)
    );

    if (!queue.publish("lease-task", "NORMAL")) {
        throw std::runtime_error("Test publication failed.");
    }

    auto first = queue.receive("worker-old");

    if (!first || first->attempt != 1) {
        throw std::runtime_error("First test delivery failed.");
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    auto second = queue.receive("worker-new");

    if (!second || second->attempt != 2) {
        throw std::runtime_error("Lease recovery failed.");
    }

    try {
        queue.acknowledge(*first);
        throw std::runtime_error("Stale receipt was incorrectly accepted.");
    } catch (const StaleDeliveryError&) {
        // Expected: the first receipt no longer owns the message.
    }

    queue.acknowledge(*second);
    queue.close();
}

int main() {
    try {
        testVisibilityTimeout();

        constexpr int maximumAttempts = 3;
        WorkQueue queue(
            6,
            maximumAttempts,
            std::chrono::seconds(2)
        );

        const std::vector<std::pair<std::string, std::string>> workload = {
            {"order-101", "PAYLOAD-A"},
            {"order-102", "PAYLOAD-B"},
            {"order-103", "POISON"},
            {"order-104", "PAYLOAD-D"},
            {"order-105", "PAYLOAD-E"},
            {"order-106", "PAYLOAD-F"}
        };

        for (const auto& [id, payload] : workload) {
            if (!queue.publish(id, payload)) {
                throw QueueFullError("Unexpected queue capacity failure.");
            }
        }

        // A bounded queue refuses additional work rather than silently
        // discarding messages or consuming unbounded memory.
        if (queue.publish("overflow", "EXTRA")) {
            throw std::runtime_error("Capacity restriction was not enforced.");
        }

        queue.close();

        IdempotencyLedger ledger;
        std::mutex outputMutex;

        std::vector<std::thread> workers;

        for (int index = 1; index <= 3; ++index) {
            workers.emplace_back(
                runConsumer,
                std::ref(queue),
                "consumer-" + std::to_string(index),
                std::ref(ledger),
                std::ref(outputMutex)
            );
        }

        // The workers compete for the same ready queue. Locking ensures
        // each delivery is assigned to one consumer at a time.
        for (auto& worker : workers) {
            worker.join();
        }

        QueueMetrics metrics = queue.metrics();

        std::cout << "\nQueue metrics\n";
        std::cout << "Ready:         " << metrics.ready << '\n';
        std::cout << "In flight:     " << metrics.inFlight << '\n';
        std::cout << "Acknowledged:  " << metrics.acknowledged << '\n';
        std::cout << "Dead-lettered: " << metrics.deadLettered << '\n';

        std::cout << "\nDead-letter messages\n";

        for (const auto& [id, reason] : queue.deadLetters()) {
            std::cout << id << ": " << reason << '\n';
        }

        if (metrics.inFlight != 0 || metrics.ready != 0) {
            throw std::runtime_error("Queue did not drain completely.");
        }

        if (metrics.deadLettered != 1) {
            throw std::runtime_error("Poison-message handling failed.");
        }

        std::cout << "\nAll queue checks passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}
