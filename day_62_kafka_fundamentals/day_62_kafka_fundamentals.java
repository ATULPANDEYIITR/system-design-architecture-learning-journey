import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

/**
 * Kafka Fundamentals:
 * topics, partitions, offsets, brokers, consumer groups,
 * replication, leader failover, and merge-style eligibility
 * represented through explicit enterprise domain services.
 */
public class KafkaFundamentals {

    enum BrokerState {
        ONLINE,
        OFFLINE
    }

    enum RecordState {
        ACCEPTED,
        REJECTED
    }

    enum ConsumerState {
        ACTIVE,
        REBALANCING
    }

    record Broker(
        int id,
        String hostname,
        BrokerState state
    ) {
        Broker {
            if (id <= 0 || hostname == null || hostname.isBlank()) {
                throw new IllegalArgumentException(
                    "Invalid broker definition"
                );
            }
        }
    }

    record Message(
        String key,
        String value,
        long offset,
        Instant timestamp
    ) {
        Message {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException(
                    "Message key is required"
                );
            }

            Objects.requireNonNull(value);
            Objects.requireNonNull(timestamp);

            if (offset < 0) {
                throw new IllegalArgumentException(
                    "Offset cannot be negative"
                );
            }
        }
    }

    record PartitionId(
        String topic,
        int number
    ) {
        PartitionId {
            if (topic == null || topic.isBlank() || number < 0) {
                throw new IllegalArgumentException(
                    "Invalid partition identifier"
                );
            }
        }

        @Override
        public String toString() {
            return topic + "-" + number;
        }
    }

    record ConsumerAssignment(
        String consumerId,
        Set<PartitionId> partitions
    ) {}

    static final class KafkaDomainException
        extends RuntimeException {

        KafkaDomainException(String message) {
            super(message);
        }
    }

    static final class OffsetException
        extends KafkaDomainException {

        OffsetException(String message) {
            super(message);
        }
    }

    static final class BrokerException
        extends KafkaDomainException {

        BrokerException(String message) {
            super(message);
        }
    }

    static final class PartitionLog {

        private final PartitionId id;
        private final List<Integer> replicas;
        private int leaderId;
        private final List<Message> messages =
            new ArrayList<>();

        PartitionLog(
            PartitionId id,
            List<Integer> replicas
        ) {
            if (replicas == null || replicas.isEmpty()) {
                throw new IllegalArgumentException(
                    "A partition needs replicas"
                );
            }

            this.id = id;
            this.replicas =
                List.copyOf(replicas);
            this.leaderId = replicas.get(0);
        }

        PartitionId id() {
            return id;
        }

        List<Integer> replicas() {
            return replicas;
        }

        int leaderId() {
            return leaderId;
        }

        void electLeader(int brokerId) {
            if (!replicas.contains(brokerId)) {
                throw new KafkaDomainException(
                    "Broker is not a partition replica"
                );
            }

            leaderId = brokerId;
        }

        long nextOffset() {
            return messages.size();
        }

        long append(
            String key,
            String value
        ) {
            long offset = nextOffset();

            messages.add(
                new Message(
                    key,
                    value,
                    offset,
                    Instant.now()
                )
            );

            return offset;
        }

        List<Message> read(
            long offset,
            int maximum
        ) {
            if (offset < 0 || offset > nextOffset()) {
                throw new OffsetException(
                    "Offset " + offset +
                    " is outside " + id
                );
            }

            if (maximum <= 0) {
                throw new IllegalArgumentException(
                    "Maximum records must be positive"
                );
            }

            int start = Math.toIntExact(offset);

            int end = Math.min(
                messages.size(),
                start + maximum
            );

            return List.copyOf(
                messages.subList(start, end)
            );
        }
    }

    static final class Topic {

        private final String name;
        private final Map<Integer, PartitionLog>
            partitions = new TreeMap<>();

        Topic(
            String name,
            int partitionCount,
            int replicationFactor,
            List<Integer> brokerIds
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Topic name is required"
                );
            }

            if (partitionCount <= 0) {
                throw new IllegalArgumentException(
                    "Partition count must be positive"
                );
            }

            if (
                replicationFactor <= 0 ||
                replicationFactor > brokerIds.size()
            ) {
                throw new IllegalArgumentException(
                    "Invalid replication factor"
                );
            }

            this.name = name;

            for (int p = 0; p < partitionCount; p++) {
                List<Integer> replicas =
                    new ArrayList<>();

                for (int r = 0; r < replicationFactor; r++) {
                    replicas.add(
                        brokerIds.get(
                            (p + r) % brokerIds.size()
                        )
                    );
                }

                partitions.put(
                    p,
                    new PartitionLog(
                        new PartitionId(name, p),
                        replicas
                    )
                );
            }
        }

        String name() {
            return name;
        }

        Map<Integer, PartitionLog> partitions() {
            return Collections.unmodifiableMap(
                partitions
            );
        }
    }

    static final class Consumer {

        private final String id;
        private ConsumerState state =
            ConsumerState.ACTIVE;

        private final Set<PartitionId> assignments =
            new java.util.LinkedHashSet<>();

        Consumer(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                    "Consumer ID is required"
                );
            }

            this.id = id;
        }

        String id() {
            return id;
        }

        ConsumerState state() {
            return state;
        }

        Set<PartitionId> assignments() {
            return Collections.unmodifiableSet(
                assignments
            );
        }

        void setState(ConsumerState state) {
            this.state = state;
        }
    }

    static final class ConsumerGroup {

        private final String id;
        private final Map<String, Consumer> consumers =
            new LinkedHashMap<>();

        private final Map<PartitionId, Long>
            committedOffsets = new HashMap<>();

        ConsumerGroup(String id) {
            this.id = id;
        }

        void addConsumer(Consumer consumer) {
            if (consumers.containsKey(consumer.id())) {
                throw new KafkaDomainException(
                    "Consumer already exists"
                );
            }

            consumers.put(
                consumer.id(),
                consumer
            );
        }

        Map<String, Consumer> consumers() {
            return Collections.unmodifiableMap(
                consumers
            );
        }

        long committedOffset(PartitionId id) {
            return committedOffsets.getOrDefault(
                id,
                0L
            );
        }

        void commit(
            PartitionId id,
            long nextOffset
        ) {
            committedOffsets.put(
                id,
                nextOffset
            );
        }
    }

    interface PartitionStrategy {
        int choose(
            String key,
            int partitionCount
        );
    }

    static final class StableHashPartitionStrategy
        implements PartitionStrategy {

        @Override
        public int choose(
            String key,
            int partitionCount
        ) {
            return Math.floorMod(
                key.hashCode(),
                partitionCount
            );
        }
    }

    static final class KafkaService {

        private final Map<Integer, Broker> brokers =
            new TreeMap<>();

        private final Map<String, Topic> topics =
            new LinkedHashMap<>();

        private final Map<String, ConsumerGroup>
            groups = new LinkedHashMap<>();

        private final PartitionStrategy strategy =
            new StableHashPartitionStrategy();

        void registerBroker(
            int id,
            String hostname
        ) {
            if (brokers.containsKey(id)) {
                throw new KafkaDomainException(
                    "Broker already exists"
                );
            }

            brokers.put(
                id,
                new Broker(
                    id,
                    hostname,
                    BrokerState.ONLINE
                )
            );
        }

        void createTopic(
            String name,
            int partitions,
            int replicationFactor
        ) {
            if (topics.containsKey(name)) {
                throw new KafkaDomainException(
                    "Topic already exists"
                );
            }

            List<Integer> brokerIds =
                new ArrayList<>(brokers.keySet());

            topics.put(
                name,
                new Topic(
                    name,
                    partitions,
                    replicationFactor,
                    brokerIds
                )
            );
        }

        private void requireLeaderOnline(
            PartitionLog partition
        ) {
            Broker broker =
                brokers.get(
                    partition.leaderId()
                );

            if (
                broker == null ||
                broker.state() == BrokerState.OFFLINE
            ) {
                throw new BrokerException(
                    "Partition leader is unavailable: " +
                    partition.id()
                );
            }
        }

        long publish(
            String topicName,
            String key,
            String value
        ) {
            Topic topic = topics.get(topicName);

            if (topic == null) {
                throw new KafkaDomainException(
                    "Unknown topic"
                );
            }

            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException(
                    "Message key is required"
                );
            }

            int partitionNumber =
                strategy.choose(
                    key,
                    topic.partitions().size()
                );

            PartitionLog partition =
                topic.partitions().get(
                    partitionNumber
                );

            requireLeaderOnline(partition);

            return partition.append(
                key,
                value
            );
        }

        void createGroup(String groupId) {
            if (groups.containsKey(groupId)) {
                throw new KafkaDomainException(
                    "Consumer group already exists"
                );
            }

            groups.put(
                groupId,
                new ConsumerGroup(groupId)
            );
        }

        void addConsumer(
            String groupId,
            String consumerId
        ) {
            ConsumerGroup group =
                requireGroup(groupId);

            group.addConsumer(
                new Consumer(consumerId)
            );
        }

        private ConsumerGroup requireGroup(
            String groupId
        ) {
            ConsumerGroup group =
                groups.get(groupId);

            if (group == null) {
                throw new KafkaDomainException(
                    "Unknown consumer group"
                );
            }

            return group;
        }

        void rebalance(
            String groupId,
            String topicName
        ) {
            ConsumerGroup group =
                requireGroup(groupId);

            Topic topic = topics.get(topicName);

            if (topic == null) {
                throw new KafkaDomainException(
                    "Unknown topic"
                );
            }

            if (group.consumers().isEmpty()) {
                throw new KafkaDomainException(
                    "No consumers available"
                );
            }

            List<Consumer> consumers =
                new ArrayList<>(
                    group.consumers().values()
                );

            consumers.forEach(
                consumer -> {
                    consumer.setState(
                        ConsumerState.REBALANCING
                    );
                    consumer.assignments.clear();
                }
            );

            int index = 0;

            for (PartitionLog partition :
                topic.partitions().values()) {

                consumers.get(
                    index % consumers.size()
                ).assignments.add(
                    partition.id()
                );

                index++;
            }

            consumers.forEach(
                consumer -> consumer.setState(
                    ConsumerState.ACTIVE
                )
            );
        }

        List<Message> poll(
            String groupId,
            String consumerId,
            int maximum
        ) {
            ConsumerGroup group =
                requireGroup(groupId);

            Consumer consumer =
                group.consumers().get(
                    consumerId
                );

            if (consumer == null) {
                throw new KafkaDomainException(
                    "Unknown consumer"
                );
            }

            if (maximum <= 0) {
                throw new IllegalArgumentException(
                    "Maximum must be positive"
                );
            }

            List<Message> result =
                new ArrayList<>();

            for (PartitionId id :
                consumer.assignments()) {

                if (result.size() >= maximum) {
                    break;
                }

                Topic topic =
                    topics.get(id.topic());

                PartitionLog partition =
                    topic.partitions().get(
                        id.number()
                    );

                try {
                    requireLeaderOnline(partition);
                } catch (BrokerException error) {
                    continue;
                }

                long offset =
                    group.committedOffset(id);

                List<Message> messages =
                    partition.read(
                        offset,
                        maximum - result.size()
                    );

                result.addAll(messages);
            }

            return result;
        }

        void commit(
            String groupId,
            PartitionId partitionId,
            long nextOffset
        ) {
            ConsumerGroup group =
                requireGroup(groupId);

            Topic topic =
                topics.get(partitionId.topic());

            if (topic == null) {
                throw new KafkaDomainException(
                    "Unknown topic"
                );
            }

            PartitionLog partition =
                topic.partitions().get(
                    partitionId.number()
                );

            if (
                nextOffset < 0 ||
                nextOffset > partition.nextOffset()
            ) {
                throw new OffsetException(
                    "Invalid commit offset"
                );
            }

            group.commit(
                partitionId,
                nextOffset
            );
        }

        void failBroker(int brokerId) {
            Broker broker =
                brokers.get(brokerId);

            if (broker == null) {
                throw new KafkaDomainException(
                    "Unknown broker"
                );
            }

            brokers.put(
                brokerId,
                new Broker(
                    broker.id(),
                    broker.hostname(),
                    BrokerState.OFFLINE
                )
            );

            for (Topic topic : topics.values()) {
                for (PartitionLog partition :
                    topic.partitions().values()) {

                    if (partition.leaderId() != brokerId) {
                        continue;
                    }

                    Integer replacement =
                        partition.replicas()
                            .stream()
                            .filter(
                                id -> brokers.get(id)
                                    .state() ==
                                    BrokerState.ONLINE
                            )
                            .findFirst()
                            .orElse(null);

                    if (replacement != null) {
                        partition.electLeader(
                            replacement
                        );
                    }
                }
            }
        }

        void recoverBroker(int brokerId) {
            Broker broker =
                brokers.get(brokerId);

            if (broker == null) {
                throw new KafkaDomainException(
                    "Unknown broker"
                );
            }

            brokers.put(
                brokerId,
                new Broker(
                    broker.id(),
                    broker.hostname(),
                    BrokerState.ONLINE
                )
            );
        }

        void printReport() {
            System.out.println("\nBroker Report");
            System.out.println("=============");

            brokers.values()
                .forEach(
                    broker ->
                        System.out.printf(
                            "broker=%d host=%s state=%s%n",
                            broker.id(),
                            broker.hostname(),
                            broker.state()
                        )
                );

            System.out.println("\nTopic Report");
            System.out.println("============");

            topics.values().forEach(topic -> {
                System.out.println(
                    "topic=" + topic.name()
                );

                topic.partitions()
                    .values()
                    .forEach(partition ->
                        System.out.printf(
                            "  %s leader=%d replicas=%s nextOffset=%d%n",
                            partition.id(),
                            partition.leaderId(),
                            partition.replicas(),
                            partition.nextOffset()
                        )
                    );
            });
        }
    }

    public static void main(String[] args) {

        KafkaService kafka = new KafkaService();

        kafka.registerBroker(
            1,
            "kafka-1.internal"
        );

        kafka.registerBroker(
            2,
            "kafka-2.internal"
        );

        kafka.registerBroker(
            3,
            "kafka-3.internal"
        );

        kafka.createTopic(
            "audit-events",
            4,
            2
        );

        List<String[]> events = List.of(
            new String[]{"user-100", "LOGIN"},
            new String[]{"user-101", "LOGIN"},
            new String[]{"user-100", "LOGOUT"},
            new String[]{"user-102", "PASSWORD_CHANGE"},
            new String[]{"user-103", "LOGIN"},
            new String[]{"user-101", "LOGOUT"}
        );

        System.out.println("Publishing records");
        System.out.println("==================");

        events.forEach(
            event -> {
                long offset =
                    kafka.publish(
                        "audit-events",
                        event[0],
                        event[1]
                    );

                System.out.printf(
                    "%s -> %s @ offset %d%n",
                    event[0],
                    event[1],
                    offset
                );
            }
        );

        kafka.createGroup(
            "security-consumers"
        );

        kafka.addConsumer(
            "security-consumers",
            "consumer-a"
        );

        kafka.addConsumer(
            "security-consumers",
            "consumer-b"
        );

        kafka.rebalance(
            "security-consumers",
            "audit-events"
        );

        System.out.println("\nConsumer records");
        System.out.println("================");

        List<Message> messages =
            kafka.poll(
                "security-consumers",
                "consumer-a",
                5
            );

        messages.forEach(
            message ->
                System.out.printf(
                    "%s=%s @%d%n",
                    message.key(),
                    message.value(),
                    message.offset()
                )
        );

        Map<String, Long> offsets =
            messages.stream()
                .collect(
                    Collectors.toMap(
                        Message::key,
                        message -> message.offset() + 1,
                        Math::max
                    )
                );

        offsets.forEach(
            (key, offset) ->
                System.out.printf(
                    "processed key=%s nextOffset=%d%n",
                    key,
                    offset
                )
        );

        System.out.println(
            "\nSimulating broker failure"
        );

        kafka.failBroker(1);

        kafka.publish(
            "audit-events",
            "user-104",
            "LOGIN_AFTER_FAILOVER"
        );

        kafka.printReport();

        System.out.println(
            "\nValidation and failure handling"
        );
        System.out.println(
            "==============================="
        );

        try {
            kafka.publish(
                "missing-topic",
                "x",
                "INVALID"
            );
        } catch (KafkaDomainException error) {
            System.out.println(
                "Expected failure: " +
                error.getMessage()
            );
        }

        try {
            kafka.commit(
                "security-consumers",
                new PartitionId(
                    "audit-events",
                    0
                ),
                999999
            );
        } catch (KafkaDomainException error) {
            System.out.println(
                "Expected offset failure: " +
                error.getMessage()
            );
        }

        kafka.recoverBroker(1);

        System.out.println(
            "\nBroker 1 is online again."
        );
    }
}
