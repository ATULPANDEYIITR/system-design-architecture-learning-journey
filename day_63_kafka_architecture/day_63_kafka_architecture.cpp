#include <algorithm>
#include <chrono>
#include <cstdint>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

enum class BrokerState {
    Online,
    Offline
};

enum class ConsumerState {
    Active,
    Inactive
};

struct Message {
    std::string topic;
    int partition{};
    std::int64_t offset{};
    std::string key;
    std::string value;
    std::int64_t timestamp{};
    int leaderBroker{};
};

struct Broker {
    int id{};
    BrokerState state{BrokerState::Online};

    std::map<std::pair<std::string, int>, std::vector<Message>> logs;
};

struct Partition {
    std::string topic;
    int id{};
    std::vector<int> replicas;
    int leaderId{};
    std::int64_t highWatermark{-1};
};

struct Topic {
    std::string name;
    std::vector<Partition> partitions;
    int replicationFactor{};
};

struct Assignment {
    std::string topic;
    int partition{};
    std::int64_t nextOffset{};
};

struct Consumer {
    std::string id;
    std::string groupId;
    std::set<std::string> subscriptions;
    ConsumerState state{ConsumerState::Active};
    std::vector<Assignment> assignments;
    std::vector<Message> processed;
};

class KafkaError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class ConfigurationError : public KafkaError {
public:
    using KafkaError::KafkaError;
};

class BrokerUnavailable : public KafkaError {
public:
    using KafkaError::KafkaError;
};

class OffsetError : public KafkaError {
public:
    using KafkaError::KafkaError;
};

class KafkaGovernanceEngine {
private:
    std::map<int, Broker> brokers_;
    std::map<std::string, Topic> topics_;
    std::map<std::string, Consumer> consumers_;
    std::map<
        std::string,
        std::map<std::pair<std::string, int>, std::int64_t>
    > committedOffsets_;

    int minInSyncReplicas_;

    static std::int64_t nowMillis() {
        return std::chrono::duration_cast<
            std::chrono::milliseconds
        >(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }

    static std::size_t stableHash(const std::string& value) {
        return std::hash<std::string>{}(value);
    }

    Partition& getPartition(
        const std::string& topic,
        int partition
    ) {
        auto topicIt = topics_.find(topic);

        if (topicIt == topics_.end()) {
            throw KafkaError("unknown topic: " + topic);
        }

        if (
            partition < 0 ||
            partition >= static_cast<int>(
                topicIt->second.partitions.size()
            )
        ) {
            throw KafkaError("invalid partition");
        }

        return topicIt->second.partitions[partition];
    }

    const Partition& getPartition(
        const std::string& topic,
        int partition
    ) const {
        auto topicIt = topics_.find(topic);

        if (topicIt == topics_.end()) {
            throw KafkaError("unknown topic: " + topic);
        }

        if (
            partition < 0 ||
            partition >= static_cast<int>(
                topicIt->second.partitions.size()
            )
        ) {
            throw KafkaError("invalid partition");
        }

        return topicIt->second.partitions[partition];
    }

    std::vector<int> onlineReplicas(
        const Partition& partition
    ) const {
        std::vector<int> result;

        for (int brokerId : partition.replicas) {
            if (
                brokers_.at(brokerId).state ==
                BrokerState::Online
            ) {
                result.push_back(brokerId);
            }
        }

        return result;
    }

    int electLeader(Partition& partition) {
        for (int brokerId : partition.replicas) {
            if (
                brokers_.at(brokerId).state ==
                BrokerState::Online
            ) {
                const int previous = partition.leaderId;
                partition.leaderId = brokerId;

                if (previous != brokerId) {
                    std::cout
                        << "Leader change "
                        << partition.topic
                        << "["
                        << partition.id
                        << "]: "
                        << previous
                        << " -> "
                        << brokerId
                        << '\n';
                }

                return brokerId;
            }
        }

        throw BrokerUnavailable(
            "no online replica for " +
            partition.topic
        );
    }

public:
    explicit KafkaGovernanceEngine(
        int brokerCount,
        int minInSyncReplicas
    )
        : minInSyncReplicas_(minInSyncReplicas) {
        if (brokerCount <= 0) {
            throw ConfigurationError(
                "brokerCount must be positive"
            );
        }

        if (
            minInSyncReplicas <= 0 ||
            minInSyncReplicas > brokerCount
        ) {
            throw ConfigurationError(
                "invalid minInSyncReplicas"
            );
        }

        for (int id = 1; id <= brokerCount; ++id) {
            brokers_.emplace(
                id,
                Broker{id, BrokerState::Online, {}}
            );
        }
    }

    void createTopic(
        const std::string& name,
        int partitionCount,
        int replicationFactor
    ) {
        if (name.empty()) {
            throw ConfigurationError(
                "topic name cannot be empty"
            );
        }

        if (topics_.contains(name)) {
            throw ConfigurationError(
                "topic already exists"
            );
        }

        if (partitionCount <= 0) {
            throw ConfigurationError(
                "partitionCount must be positive"
            );
        }

        if (
            replicationFactor <= 0 ||
            replicationFactor > static_cast<int>(
                brokers_.size()
            )
        ) {
            throw ConfigurationError(
                "invalid replication factor"
            );
        }

        Topic topic;
        topic.name = name;
        topic.replicationFactor = replicationFactor;

        for (int p = 0; p < partitionCount; ++p) {
            Partition partition;
            partition.topic = name;
            partition.id = p;

            for (int r = 0; r < replicationFactor; ++r) {
                partition.replicas.push_back(
                    ((p + r) %
                     static_cast<int>(brokers_.size())) +
                    1
                );
            }

            partition.leaderId =
                partition.replicas.front();

            for (int brokerId : partition.replicas) {
                brokers_.at(brokerId)
                    .logs[{name, p}] = {};
            }

            topic.partitions.push_back(
                std::move(partition)
            );
        }

        topics_.emplace(name, std::move(topic));
    }

    Message publish(
        const std::string& topic,
        const std::string& key,
        const std::string& value
    ) {
        if (key.empty()) {
            throw ConfigurationError(
                "message key cannot be empty"
            );
        }

        auto topicIt = topics_.find(topic);
        if (topicIt == topics_.end()) {
            throw KafkaError("unknown topic");
        }

        const int partitionId =
            static_cast<int>(
                stableHash(key) %
                topicIt->second.partitions.size()
            );

        Partition& partition =
            topicIt->second.partitions[partitionId];

        if (
            brokers_.at(partition.leaderId).state ==
            BrokerState::Offline
        ) {
            electLeader(partition);
        }

        const auto inSync = onlineReplicas(partition);

        if (
            static_cast<int>(inSync.size()) <
            minInSyncReplicas_
        ) {
            throw BrokerUnavailable(
                "write rejected because min ISR is not satisfied"
            );
        }

        auto& leaderLog =
            brokers_.at(partition.leaderId)
                .logs.at({topic, partitionId});

        Message message{
            topic,
            partitionId,
            static_cast<std::int64_t>(leaderLog.size()),
            key,
            value,
            nowMillis(),
            partition.leaderId
        };

        for (int brokerId : inSync) {
            brokers_.at(brokerId)
                .logs.at({topic, partitionId})
                .push_back(message);
        }

        partition.highWatermark = message.offset;

        return message;
    }

    void registerConsumer(
        const std::string& consumerId,
        const std::string& groupId,
        std::set<std::string> subscriptions
    ) {
        if (consumers_.contains(consumerId)) {
            throw ConfigurationError(
                "consumer already exists"
            );
        }

        for (const auto& topic : subscriptions) {
            if (!topics_.contains(topic)) {
                throw KafkaError(
                    "unknown subscription: " + topic
                );
            }
        }

        consumers_.emplace(
            consumerId,
            Consumer{
                consumerId,
                groupId,
                std::move(subscriptions),
                ConsumerState::Active,
                {},
                {}
            }
        );

        rebalance(groupId);
    }

    void rebalance(const std::string& groupId) {
        std::vector<Consumer*> members;

        for (auto& [id, consumer] : consumers_) {
            if (
                consumer.groupId == groupId &&
                consumer.state == ConsumerState::Active
            ) {
                consumer.assignments.clear();
                members.push_back(&consumer);
            }
        }

        if (members.empty()) {
            return;
        }

        std::vector<std::pair<std::string, int>> partitions;

        for (const auto& [topicName, topic] : topics_) {
            const bool subscribed = std::any_of(
                members.begin(),
                members.end(),
                [&](const Consumer* consumer) {
                    return consumer->subscriptions.contains(
                        topicName
                    );
                }
            );

            if (!subscribed) {
                continue;
            }

            for (const auto& partition : topic.partitions) {
                partitions.emplace_back(
                    topicName,
                    partition.id
                );
            }
        }

        for (const auto& [topic, partition] : partitions) {
            auto eligible = std::vector<Consumer*>{};

            for (Consumer* consumer : members) {
                if (
                    consumer->subscriptions.contains(topic)
                ) {
                    eligible.push_back(consumer);
                }
            }

            if (eligible.empty()) {
                continue;
            }

            auto target = *std::min_element(
                eligible.begin(),
                eligible.end(),
                [](const Consumer* a, const Consumer* b) {
                    return a->assignments.size() <
                           b->assignments.size();
                }
            );

            const auto offsetIt =
                committedOffsets_[groupId].find(
                    {topic, partition}
                );

            const std::int64_t offset =
                offsetIt == committedOffsets_[groupId].end()
                    ? 0
                    : offsetIt->second;

            target->assignments.push_back(
                Assignment{
                    topic,
                    partition,
                    offset
                }
            );
        }
    }

    void setBrokerState(int brokerId, bool online) {
        auto brokerIt = brokers_.find(brokerId);

        if (brokerIt == brokers_.end()) {
            throw KafkaError("unknown broker");
        }

        brokerIt->second.state =
            online
                ? BrokerState::Online
                : BrokerState::Offline;

        if (!online) {
            for (auto& [topicName, topic] : topics_) {
                for (auto& partition : topic.partitions) {
                    if (
                        partition.leaderId == brokerId
                    ) {
                        electLeader(partition);
                    }
                }
            }
        }

        std::set<std::string> groups;

        for (const auto& [id, consumer] : consumers_) {
            groups.insert(consumer.groupId);
        }

        for (const auto& group : groups) {
            rebalance(group);
        }
    }

    std::vector<Message> poll(
        const std::string& consumerId,
        std::size_t maxRecords
    ) {
        auto consumerIt = consumers_.find(consumerId);

        if (consumerIt == consumers_.end()) {
            throw KafkaError("unknown consumer");
        }

        Consumer& consumer = consumerIt->second;

        if (consumer.state != ConsumerState::Active) {
            throw KafkaError("consumer is inactive");
        }

        std::vector<Message> result;

        for (auto& assignment : consumer.assignments) {
            if (result.size() >= maxRecords) {
                break;
            }

            Partition& partition =
                getPartition(
                    assignment.topic,
                    assignment.partition
                );

            if (
                brokers_.at(partition.leaderId).state ==
                BrokerState::Offline
            ) {
                electLeader(partition);
            }

            const auto& log =
                brokers_.at(partition.leaderId)
                    .logs.at({
                        assignment.topic,
                        assignment.partition
                    });

            while (
                assignment.nextOffset <
                    static_cast<std::int64_t>(log.size()) &&
                result.size() < maxRecords
            ) {
                result.push_back(
                    log[assignment.nextOffset]
                );
                ++assignment.nextOffset;
            }
        }

        return result;
    }

    void commit(
        const std::string& consumerId,
        const std::vector<Message>& messages
    ) {
        auto consumerIt = consumers_.find(consumerId);

        if (consumerIt == consumers_.end()) {
            throw KafkaError("unknown consumer");
        }

        Consumer& consumer = consumerIt->second;

        auto& offsets =
            committedOffsets_[consumer.groupId];

        for (const Message& message : messages) {
            const auto key =
                std::make_pair(
                    message.topic,
                    message.partition
                );

            const std::int64_t next =
                message.offset + 1;

            const auto previous =
                offsets.find(key);

            if (
                previous != offsets.end() &&
                next < previous->second
            ) {
                throw OffsetError(
                    "offset regression detected"
                );
            }

            offsets[key] = next;
        }

        consumer.processed.insert(
            consumer.processed.end(),
            messages.begin(),
            messages.end()
        );
    }

    void consumeAndCommit(
        const std::string& consumerId,
        std::size_t maxRecords
    ) {
        const auto messages =
            poll(consumerId, maxRecords);

        commit(consumerId, messages);

        const auto& consumer =
            consumers_.at(consumerId);

        std::cout
            << consumerId
            << " processed "
            << messages.size()
            << " messages\n";

        for (const auto& message : messages) {
            std::cout
                << "  "
                << message.topic
                << "["
                << message.partition
                << "]@"
                << message.offset
                << " "
                << message.value
                << '\n';
        }
    }

    void stopConsumer(const std::string& consumerId) {
        auto it = consumers_.find(consumerId);

        if (it == consumers_.end()) {
            throw KafkaError("unknown consumer");
        }

        it->second.state = ConsumerState::Inactive;
        it->second.assignments.clear();

        rebalance(it->second.groupId);
    }

    void printClusterState() const {
        std::cout << "\nCluster state\n";

        for (const auto& [id, broker] : brokers_) {
            std::cout
                << "Broker "
                << id
                << ": "
                << (
                    broker.state == BrokerState::Online
                        ? "ONLINE"
                        : "OFFLINE"
                )
                << '\n';
        }

        for (const auto& [name, topic] : topics_) {
            for (const auto& partition : topic.partitions) {
                std::cout
                    << name
                    << "["
                    << partition.id
                    << "] leader="
                    << partition.leaderId
                    << " replicas=";

                for (int brokerId : partition.replicas) {
                    std::cout << brokerId << ' ';
                }

                std::cout
                    << " HWM="
                    << partition.highWatermark
                    << '\n';
            }
        }
    }
};

int main() {
    try {
        KafkaGovernanceEngine cluster(3, 2);

        cluster.createTopic(
            "orders",
            3,
            3
        );

        cluster.registerConsumer(
            "orders-worker-1",
            "order-processing",
            {"orders"}
        );

        cluster.registerConsumer(
            "orders-worker-2",
            "order-processing",
            {"orders"}
        );

        const std::vector<std::pair<std::string, std::string>> orders{
            {"customer-100", R"({"order":"O-100","amount":1250})"},
            {"customer-101", R"({"order":"O-101","amount":850})"},
            {"customer-102", R"({"order":"O-102","amount":2200})"},
            {"customer-100", R"({"order":"O-103","amount":410})"},
            {"customer-103", R"({"order":"O-104","amount":990})"},
            {"customer-104", R"({"order":"O-105","amount":730})"}
        };

        for (const auto& [key, value] : orders) {
            cluster.publish(
                "orders",
                key,
                value
            );
        }

        cluster.printClusterState();

        cluster.consumeAndCommit(
            "orders-worker-1",
            3
        );

        cluster.setBrokerState(1, false);

        try {
            cluster.publish(
                "orders",
                "customer-105",
                R"({"order":"O-106","amount":1500})"
            );
        } catch (const BrokerUnavailable& error) {
            std::cout
                << "Expected write failure: "
                << error.what()
                << '\n';
        }

        cluster.setBrokerState(1, true);

        cluster.publish(
            "orders",
            "customer-105",
            R"({"order":"O-106","amount":1500})"
        );

        cluster.consumeAndCommit(
            "orders-worker-2",
            20
        );

        cluster.stopConsumer(
            "orders-worker-1"
        );

        cluster.printClusterState();
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
