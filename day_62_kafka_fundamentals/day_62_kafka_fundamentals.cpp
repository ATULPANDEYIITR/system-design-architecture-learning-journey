#include <algorithm>
#include <chrono>
#include <cstdint>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using Offset = std::int64_t;
using BrokerId = int;

enum class BrokerState {
    Online,
    Offline
};

enum class CheckState {
    Passed,
    Failed,
    Pending
};

struct Record {
    std::string key;
    std::string value;
    std::int64_t timestamp;
    Offset offset;
};

struct StatusCheck {
    std::string name;
    CheckState state;
};

class KafkaException : public std::runtime_error {
public:
    explicit KafkaException(const std::string& message)
        : std::runtime_error(message) {}
};

class ValidationError : public KafkaException {
public:
    explicit ValidationError(const std::string& message)
        : KafkaException(message) {}
};

class BrokerUnavailable : public KafkaException {
public:
    explicit BrokerUnavailable(const std::string& message)
        : KafkaException(message) {}
};

class OffsetError : public KafkaException {
public:
    explicit OffsetError(const std::string& message)
        : KafkaException(message) {}
};

struct Broker {
    BrokerId id;
    std::string host;
    BrokerState state = BrokerState::Online;
};

class Partition {
private:
    std::string topic_;
    int id_;
    BrokerId leader_;
    std::vector<BrokerId> replicas_;
    std::vector<Record> records_;

public:
    Partition(
        std::string topic,
        int id,
        BrokerId leader,
        std::vector<BrokerId> replicas
    )
        : topic_(std::move(topic)),
          id_(id),
          leader_(leader),
          replicas_(std::move(replicas)) {}

    const std::string& topic() const {
        return topic_;
    }

    int id() const {
        return id_;
    }

    BrokerId leader() const {
        return leader_;
    }

    void setLeader(BrokerId broker) {
        leader_ = broker;
    }

    const std::vector<BrokerId>& replicas() const {
        return replicas_;
    }

    Offset nextOffset() const {
        return static_cast<Offset>(records_.size());
    }

    Offset append(
        const std::string& key,
        const std::string& value,
        std::int64_t timestamp
    ) {
        Offset offset = nextOffset();

        records_.push_back(
            Record{
                key,
                value,
                timestamp,
                offset
            }
        );

        return offset;
    }

    std::vector<Record> fetch(
        Offset offset,
        std::size_t maximum
    ) const {
        if (offset < 0 || offset > nextOffset()) {
            throw OffsetError(
                "Offset " + std::to_string(offset) +
                " is outside partition " +
                topic_ + "-" + std::to_string(id_)
            );
        }

        const auto begin =
            records_.begin() + offset;

        const auto end =
            records_.begin() +
            std::min<Offset>(
                nextOffset(),
                offset + static_cast<Offset>(maximum)
            );

        return {begin, end};
    }
};

struct Topic {
    std::string name;
    std::map<int, Partition> partitions;
    int replicationFactor;
};

struct Consumer {
    std::string id;
    std::set<std::pair<std::string, int>> assignments;
};

struct ConsumerGroup {
    std::string id;
    std::map<std::string, Consumer> consumers;
    std::map<std::pair<std::string, int>, Offset> committedOffsets;
};

class MergeEligibilityEngine {
private:
    std::map<BrokerId, Broker> brokers_;
    std::map<std::string, Topic> topics_;
    std::map<std::string, ConsumerGroup> groups_;

    static std::int64_t nowMillis() {
        return std::chrono::duration_cast<
            std::chrono::milliseconds
        >(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
    }

    void requireTopic(const std::string& topic) const {
        if (!topics_.contains(topic)) {
            throw ValidationError(
                "Unknown topic: " + topic
            );
        }
    }

    void requireLeaderOnline(
        const Partition& partition
    ) const {
        const auto it = brokers_.find(partition.leader());

        if (
            it == brokers_.end() ||
            it->second.state == BrokerState::Offline
        ) {
            throw BrokerUnavailable(
                "Leader broker " +
                std::to_string(partition.leader()) +
                " is unavailable"
            );
        }
    }

public:
    void addBroker(
        BrokerId id,
        const std::string& host
    ) {
        if (brokers_.contains(id)) {
            throw ValidationError(
                "Broker already exists: " +
                std::to_string(id)
            );
        }

        brokers_.emplace(
            id,
            Broker{id, host, BrokerState::Online}
        );
    }

    void createTopic(
        const std::string& name,
        int partitionCount,
        int replicationFactor
    ) {
        if (topics_.contains(name)) {
            throw ValidationError(
                "Topic already exists: " + name
            );
        }

        if (partitionCount <= 0) {
            throw ValidationError(
                "Partition count must be positive"
            );
        }

        if (
            replicationFactor <= 0 ||
            replicationFactor >
                static_cast<int>(brokers_.size())
        ) {
            throw ValidationError(
                "Invalid replication factor"
            );
        }

        std::vector<BrokerId> ids;

        for (const auto& [id, broker] : brokers_) {
            ids.push_back(id);
        }

        Topic topic{
            name,
            {},
            replicationFactor
        };

        for (int p = 0; p < partitionCount; ++p) {
            std::vector<BrokerId> replicas;

            for (int r = 0; r < replicationFactor; ++r) {
                replicas.push_back(
                    ids[(p + r) % ids.size()]
                );
            }

            topic.partitions.emplace(
                p,
                Partition(
                    name,
                    p,
                    replicas.front(),
                    replicas
                )
            );
        }

        topics_.emplace(name, std::move(topic));
    }

    int partitionForKey(
        const std::string& topic,
        const std::string& key
    ) const {
        requireTopic(topic);

        const auto& partitions =
            topics_.at(topic).partitions;

        std::hash<std::string> hasher;
        return static_cast<int>(
            hasher(key) % partitions.size()
        );
    }

    Offset produce(
        const std::string& topic,
        const std::string& key,
        const std::string& value,
        std::optional<int> requestedPartition = std::nullopt
    ) {
        requireTopic(topic);

        if (key.empty()) {
            throw ValidationError(
                "Record key cannot be empty"
            );
        }

        const int partitionId =
            requestedPartition.value_or(
                partitionForKey(topic, key)
            );

        auto& partition =
            topics_.at(topic).partitions.at(partitionId);

        requireLeaderOnline(partition);

        const Offset offset =
            partition.append(
                key,
                value,
                nowMillis()
            );

        // The simulation validates that every replica exists.
        // A production Kafka cluster also tracks replica state,
        // ISR membership, acknowledgements, and durability.
        for (BrokerId replica : partition.replicas()) {
            if (!brokers_.contains(replica)) {
                throw BrokerUnavailable(
                    "Missing replica broker " +
                    std::to_string(replica)
                );
            }
        }

        return offset;
    }

    void createConsumerGroup(
        const std::string& groupId
    ) {
        if (groups_.contains(groupId)) {
            throw ValidationError(
                "Consumer group already exists"
            );
        }

        groups_.emplace(
            groupId,
            ConsumerGroup{groupId, {}, {}}
        );
    }

    void addConsumer(
        const std::string& groupId,
        const std::string& consumerId
    ) {
        if (!groups_.contains(groupId)) {
            throw ValidationError(
                "Unknown consumer group"
            );
        }

        auto& group = groups_.at(groupId);

        if (group.consumers.contains(consumerId)) {
            throw ValidationError(
                "Consumer already exists"
            );
        }

        group.consumers.emplace(
            consumerId,
            Consumer{consumerId, {}}
        );
    }

    void rebalance(
        const std::string& groupId,
        const std::string& topic
    ) {
        if (!groups_.contains(groupId)) {
            throw ValidationError(
                "Unknown consumer group"
            );
        }

        requireTopic(topic);

        auto& group = groups_.at(groupId);

        if (group.consumers.empty()) {
            throw ValidationError(
                "Cannot rebalance an empty consumer group"
            );
        }

        for (auto& [id, consumer] : group.consumers) {
            consumer.assignments.clear();
        }

        std::vector<std::string> consumerIds;

        for (const auto& [id, consumer] : group.consumers) {
            consumerIds.push_back(id);
        }

        std::size_t index = 0;

        for (const auto& [partitionId, partition] :
             topics_.at(topic).partitions) {
            auto& consumer =
                group.consumers.at(
                    consumerIds[index % consumerIds.size()]
                );

            consumer.assignments.insert(
                {topic, partitionId}
            );

            ++index;
        }
    }

    std::vector<Record> poll(
        const std::string& groupId,
        const std::string& consumerId,
        std::size_t maximum
    ) {
        if (!groups_.contains(groupId)) {
            throw ValidationError(
                "Unknown consumer group"
            );
        }

        auto& group = groups_.at(groupId);

        if (!group.consumers.contains(consumerId)) {
            throw ValidationError(
                "Unknown consumer"
            );
        }

        const auto& consumer =
            group.consumers.at(consumerId);

        std::vector<Record> result;

        for (const auto& [topic, partitionId] :
             consumer.assignments) {
            if (result.size() >= maximum) {
                break;
            }

            const auto& partition =
                topics_.at(topic).partitions.at(partitionId);

            try {
                requireLeaderOnline(partition);
            } catch (const BrokerUnavailable&) {
                continue;
            }

            const auto key =
                std::make_pair(topic, partitionId);

            const Offset offset =
                group.committedOffsets.contains(key)
                    ? group.committedOffsets.at(key)
                    : 0;

            auto records =
                partition.fetch(
                    offset,
                    maximum - result.size()
                );

            result.insert(
                result.end(),
                records.begin(),
                records.end()
            );
        }

        return result;
    }

    void commit(
        const std::string& groupId,
        const std::string& topic,
        int partitionId,
        Offset nextOffset
    ) {
        if (!groups_.contains(groupId)) {
            throw ValidationError(
                "Unknown consumer group"
            );
        }

        requireTopic(topic);

        const auto& partition =
            topics_.at(topic).partitions.at(partitionId);

        if (
            nextOffset < 0 ||
            nextOffset > partition.nextOffset()
        ) {
            throw OffsetError(
                "Invalid committed offset"
            );
        }

        groups_.at(groupId).committedOffsets[
            {topic, partitionId}
        ] = nextOffset;
    }

    void failBroker(BrokerId brokerId) {
        if (!brokers_.contains(brokerId)) {
            throw ValidationError(
                "Unknown broker"
            );
        }

        brokers_.at(brokerId).state =
            BrokerState::Offline;

        for (auto& [topicName, topic] : topics_) {
            for (auto& [partitionId, partition] :
                 topic.partitions) {
                if (partition.leader() != brokerId) {
                    continue;
                }

                const auto& replicas =
                    partition.replicas();

                auto candidate =
                    std::find_if(
                        replicas.begin(),
                        replicas.end(),
                        [this](BrokerId id) {
                            return brokers_.at(id).state ==
                                   BrokerState::Online;
                        }
                    );

                if (candidate != replicas.end()) {
                    partition.setLeader(*candidate);
                }
            }
        }
    }

    void recoverBroker(BrokerId brokerId) {
        if (!brokers_.contains(brokerId)) {
            throw ValidationError(
                "Unknown broker"
            );
        }

        brokers_.at(brokerId).state =
            BrokerState::Online;
    }

    void describe() const {
        std::cout << "\nCluster\n";
        std::cout << "=======\n";

        for (const auto& [id, broker] : brokers_) {
            std::cout
                << "broker=" << id
                << " host=" << broker.host
                << " state="
                << (
                    broker.state == BrokerState::Online
                        ? "online"
                        : "offline"
                )
                << '\n';
        }

        std::cout << "\nTopics\n";
        std::cout << "======\n";

        for (const auto& [name, topic] : topics_) {
            std::cout
                << name
                << " partitions="
                << topic.partitions.size()
                << " replicationFactor="
                << topic.replicationFactor
                << '\n';

            for (const auto& [id, partition] :
                 topic.partitions) {
                std::cout
                    << "  partition=" << id
                    << " leader=" << partition.leader()
                    << " replicas=";

                for (BrokerId broker : partition.replicas()) {
                    std::cout << broker << ' ';
                }

                std::cout
                    << "nextOffset="
                    << partition.nextOffset()
                    << '\n';
            }
        }
    }
};

int main() {
    try {
        MergeEligibilityEngine cluster;

        cluster.addBroker(1, "broker-1.internal");
        cluster.addBroker(2, "broker-2.internal");
        cluster.addBroker(3, "broker-3.internal");

        cluster.createTopic(
            "orders",
            4,
            2
        );

        const std::vector<std::pair<std::string, std::string>>
            messages{
                {"order-1001", "CREATED"},
                {"order-1002", "PAID"},
                {"order-1003", "PACKED"},
                {"order-1004", "SHIPPED"},
                {"order-1005", "DELIVERED"},
                {"order-1006", "RETURNED"}
            };

        std::cout << "Producing records\n";
        std::cout << "=================\n";

        for (const auto& [key, value] : messages) {
            const Offset offset =
                cluster.produce(
                    "orders",
                    key,
                    value
                );

            std::cout
                << key
                << " -> offset "
                << offset
                << '\n';
        }

        cluster.createConsumerGroup(
            "order-processors"
        );

        cluster.addConsumer(
            "order-processors",
            "worker-1"
        );

        cluster.addConsumer(
            "order-processors",
            "worker-2"
        );

        cluster.rebalance(
            "order-processors",
            "orders"
        );

        std::cout << "\nPolling worker-1\n";
        std::cout << "================\n";

        const auto records =
            cluster.poll(
                "order-processors",
                "worker-1",
                4
            );

        for (const auto& record : records) {
            std::cout
                << record.key
                << " -> "
                << record.value
                << " @"
                << record.offset
                << '\n';
        }

        for (const auto& record : records) {
            cluster.commit(
                "order-processors",
                "orders",
                static_cast<int>(
                    cluster
                        .partitionForKey(
                            "orders",
                            record.key
                        )
                ),
                record.offset + 1
            );
        }

        cluster.describe();

        std::cout << "\nBroker failure\n";
        std::cout << "==============\n";

        cluster.failBroker(1);

        cluster.describe();

        const Offset recoveredProduction =
            cluster.produce(
                "orders",
                "order-after-failure",
                "CREATED"
            );

        std::cout
            << "Produced after leader reassignment at "
            << recoveredProduction
            << '\n';

        std::cout << "\nFailure handling\n";
        std::cout << "================\n";

        try {
            cluster.produce(
                "orders",
                "",
                "INVALID"
            );
        } catch (const KafkaException& error) {
            std::cout
                << "Expected validation failure: "
                << error.what()
                << '\n';
        }

        try {
            cluster.commit(
                "order-processors",
                "orders",
                0,
                999999
            );
        } catch (const KafkaException& error) {
            std::cout
                << "Expected offset failure: "
                << error.what()
                << '\n';
        }

        cluster.recoverBroker(1);

        std::cout
            << "\nBroker 1 recovered successfully.\n";

    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
