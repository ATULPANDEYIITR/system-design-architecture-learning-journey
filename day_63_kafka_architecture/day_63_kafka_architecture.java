import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

public class KafkaArchitectureDemo {

    enum BrokerState {
        ONLINE,
        OFFLINE
    }

    enum ConsumerState {
        ACTIVE,
        INACTIVE
    }

    enum DeliveryState {
        AVAILABLE,
        PROCESSED
    }

    record Message(
        String topic,
        int partition,
        long offset,
        String key,
        String value,
        Instant timestamp,
        int leaderBroker
    ) {}

    record PartitionKey(
        String topic,
        int partition
    ) {}

    record Assignment(
        String topic,
        int partition,
        long nextOffset
    ) {}

    record BrokerSnapshot(
        int id,
        BrokerState state
    ) {}

    static final class KafkaException extends RuntimeException {
        KafkaException(String message) {
            super(message);
        }
    }

    static final class ConfigurationException
            extends KafkaException {
        ConfigurationException(String message) {
            super(message);
        }
    }

    static final class BrokerUnavailableException
            extends KafkaException {
        BrokerUnavailableException(String message) {
            super(message);
        }
    }

    static final class OffsetException
            extends KafkaException {
        OffsetException(String message) {
            super(message);
        }
    }

    static final class Broker {
        private final int id;
        private BrokerState state;
        private final Map<PartitionKey, List<Message>> logs =
                new HashMap<>();

        Broker(int id) {
            this.id = id;
            this.state = BrokerState.ONLINE;
        }

        int id() {
            return id;
        }

        BrokerState state() {
            return state;
        }

        void setState(BrokerState state) {
            this.state = state;
        }

        List<Message> log(PartitionKey key) {
            return logs.computeIfAbsent(
                key,
                ignored -> new ArrayList<>()
            );
        }
    }

    static final class Partition {
        private final String topic;
        private final int id;
        private final List<Integer> replicas;
        private int leaderBroker;
        private long highWatermark = -1;

        Partition(
            String topic,
            int id,
            List<Integer> replicas
        ) {
            this.topic = topic;
            this.id = id;
            this.replicas = List.copyOf(replicas);
            this.leaderBroker = replicas.get(0);
        }

        String topic() {
            return topic;
        }

        int id() {
            return id;
        }

        List<Integer> replicas() {
            return replicas;
        }

        int leaderBroker() {
            return leaderBroker;
        }

        void setLeaderBroker(int brokerId) {
            this.leaderBroker = brokerId;
        }

        long highWatermark() {
            return highWatermark;
        }

        void setHighWatermark(long value) {
            highWatermark = value;
        }
    }

    static final class Topic {
        private final String name;
        private final List<Partition> partitions;

        Topic(String name, List<Partition> partitions) {
            this.name = name;
            this.partitions = List.copyOf(partitions);
        }

        String name() {
            return name;
        }

        List<Partition> partitions() {
            return partitions;
        }
    }

    static final class Consumer {
        private final String id;
        private final String groupId;
        private final Set<String> subscriptions;
        private ConsumerState state = ConsumerState.ACTIVE;
        private final List<Assignment> assignments =
                new ArrayList<>();
        private final List<Message> processed =
                new ArrayList<>();

        Consumer(
            String id,
            String groupId,
            Set<String> subscriptions
        ) {
            this.id = id;
            this.groupId = groupId;
            this.subscriptions = Set.copyOf(subscriptions);
        }

        String id() {
            return id;
        }

        String groupId() {
            return groupId;
        }

        Set<String> subscriptions() {
            return subscriptions;
        }

        ConsumerState state() {
            return state;
        }

        void setState(ConsumerState state) {
            this.state = state;
        }

        List<Assignment> assignments() {
            return assignments;
        }

        List<Message> processed() {
            return processed;
        }
    }

    interface ReplicationPolicy {
        boolean mayAcceptWrite(
            int inSyncReplicaCount,
            int minimumInSyncReplicas
        );
    }

    static final class MinimumInSyncReplicaPolicy
            implements ReplicationPolicy {

        @Override
        public boolean mayAcceptWrite(
            int inSyncReplicaCount,
            int minimumInSyncReplicas
        ) {
            return inSyncReplicaCount >=
                    minimumInSyncReplicas;
        }
    }

    static final class KafkaCluster {
        private final Map<Integer, Broker> brokers =
                new HashMap<>();

        private final Map<String, Topic> topics =
                new HashMap<>();

        private final Map<String, Consumer> consumers =
                new HashMap<>();

        private final Map<String, Map<PartitionKey, Long>>
                committedOffsets = new HashMap<>();

        private final ReplicationPolicy replicationPolicy;
        private final int minimumInSyncReplicas;

        KafkaCluster(
            int brokerCount,
            int minimumInSyncReplicas
        ) {
            if (brokerCount < 1) {
                throw new ConfigurationException(
                    "brokerCount must be positive"
                );
            }

            if (
                minimumInSyncReplicas < 1 ||
                minimumInSyncReplicas > brokerCount
            ) {
                throw new ConfigurationException(
                    "invalid minimumInSyncReplicas"
                );
            }

            this.minimumInSyncReplicas =
                    minimumInSyncReplicas;

            this.replicationPolicy =
                    new MinimumInSyncReplicaPolicy();

            for (int id = 1; id <= brokerCount; id++) {
                brokers.put(id, new Broker(id));
            }
        }

        void createTopic(
            String name,
            int partitionCount,
            int replicationFactor
        ) {
            Objects.requireNonNull(name);

            if (name.isBlank()) {
                throw new ConfigurationException(
                    "topic name cannot be blank"
                );
            }

            if (topics.containsKey(name)) {
                throw new ConfigurationException(
                    "topic already exists"
                );
            }

            if (partitionCount < 1) {
                throw new ConfigurationException(
                    "partitionCount must be positive"
                );
            }

            if (
                replicationFactor < 1 ||
                replicationFactor > brokers.size()
            ) {
                throw new ConfigurationException(
                    "invalid replication factor"
                );
            }

            List<Partition> partitions =
                    new ArrayList<>();

            for (int p = 0; p < partitionCount; p++) {
                List<Integer> replicas =
                        new ArrayList<>();

                for (int r = 0; r < replicationFactor; r++) {
                    replicas.add(
                        ((p + r) % brokers.size()) + 1
                    );
                }

                Partition partition =
                        new Partition(
                            name,
                            p,
                            replicas
                        );

                partitions.add(partition);

                PartitionKey key =
                        new PartitionKey(name, p);

                for (int brokerId : replicas) {
                    brokers.get(brokerId).log(key);
                }
            }

            topics.put(
                name,
                new Topic(name, partitions)
            );
        }

        private Partition partitionFor(
            String topic,
            String key
        ) {
            Topic topicObject = topic(topic);

            int hash = Math.floorMod(
                key.hashCode(),
                topicObject.partitions().size()
            );

            return topicObject.partitions().get(hash);
        }

        private Topic topic(String name) {
            Topic topic = topics.get(name);

            if (topic == null) {
                throw new KafkaException(
                    "unknown topic: " + name
                );
            }

            return topic;
        }

        private Partition partition(
            String topic,
            int partitionId
        ) {
            Topic topicObject = topic(topic);

            if (
                partitionId < 0 ||
                partitionId >= topicObject.partitions().size()
            ) {
                throw new KafkaException(
                    "invalid partition"
                );
            }

            return topicObject.partitions()
                    .get(partitionId);
        }

        private List<Integer> onlineReplicas(
            Partition partition
        ) {
            return partition.replicas()
                .stream()
                .filter(
                    brokerId ->
                        brokers.get(brokerId).state() ==
                        BrokerState.ONLINE
                )
                .toList();
        }

        private int electLeader(Partition partition) {
            Optional<Integer> candidate =
                    partition.replicas()
                        .stream()
                        .filter(
                            brokerId ->
                                brokers.get(brokerId)
                                    .state() ==
                                BrokerState.ONLINE
                        )
                        .findFirst();

            if (candidate.isEmpty()) {
                throw new BrokerUnavailableException(
                    "no online replica for " +
                    partition.topic() +
                    "[" +
                    partition.id() +
                    "]"
                );
            }

            int previous = partition.leaderBroker();
            int selected = candidate.get();

            partition.setLeaderBroker(selected);

            if (previous != selected) {
                System.out.println(
                    "Leader changed: " +
                    partition.topic() +
                    "[" +
                    partition.id() +
                    "] " +
                    previous +
                    " -> " +
                    selected
                );
            }

            return selected;
        }

        Message publish(
            String topic,
            String key,
            String value
        ) {
            if (key == null || key.isBlank()) {
                throw new ConfigurationException(
                    "message key cannot be blank"
                );
            }

            Partition partition =
                    partitionFor(topic, key);

            Broker leader =
                    brokers.get(partition.leaderBroker());

            if (leader.state() == BrokerState.OFFLINE) {
                electLeader(partition);
                leader =
                    brokers.get(partition.leaderBroker());
            }

            List<Integer> inSync =
                    onlineReplicas(partition);

            if (
                !replicationPolicy.mayAcceptWrite(
                    inSync.size(),
                    minimumInSyncReplicas
                )
            ) {
                throw new BrokerUnavailableException(
                    "minimum ISR requirement is not satisfied"
                );
            }

            PartitionKey partitionKey =
                    new PartitionKey(
                        topic,
                        partition.id()
                    );

            List<Message> leaderLog =
                    leader.log(partitionKey);

            Message message =
                    new Message(
                        topic,
                        partition.id(),
                        leaderLog.size(),
                        key,
                        value,
                        Instant.now(),
                        partition.leaderBroker()
                    );

            for (int brokerId : inSync) {
                brokers.get(brokerId)
                    .log(partitionKey)
                    .add(message);
            }

            partition.setHighWatermark(
                message.offset()
            );

            return message;
        }

        void registerConsumer(
            String consumerId,
            String groupId,
            Set<String> subscriptions
        ) {
            if (consumers.containsKey(consumerId)) {
                throw new ConfigurationException(
                    "consumer already exists"
                );
            }

            for (String subscription : subscriptions) {
                topic(subscription);
            }

            consumers.put(
                consumerId,
                new Consumer(
                    consumerId,
                    groupId,
                    subscriptions
                )
            );

            rebalance(groupId);
        }

        void rebalance(String groupId) {
            List<Consumer> members =
                    consumers.values()
                        .stream()
                        .filter(
                            consumer ->
                                consumer.groupId()
                                    .equals(groupId) &&
                                consumer.state() ==
                                    ConsumerState.ACTIVE
                        )
                        .toList();

            for (Consumer member : members) {
                member.assignments().clear();
            }

            if (members.isEmpty()) {
                return;
            }

            List<Partition> availablePartitions =
                    topics.values()
                        .stream()
                        .sorted(
                            Comparator.comparing(Topic::name)
                        )
                        .flatMap(
                            topic ->
                                topic.partitions().stream()
                        )
                        .filter(
                            partition ->
                                members.stream().anyMatch(
                                    member ->
                                        member.subscriptions()
                                            .contains(
                                                partition.topic()
                                            )
                                )
                        )
                        .toList();

            for (Partition partition :
                    availablePartitions) {

                List<Consumer> eligible =
                        members.stream()
                            .filter(
                                member ->
                                    member.subscriptions()
                                        .contains(
                                            partition.topic()
                                        )
                            )
                            .sorted(
                                Comparator.comparingInt(
                                    member ->
                                        member.assignments()
                                            .size()
                                )
                            )
                            .toList();

                if (eligible.isEmpty()) {
                    continue;
                }

                Consumer target = eligible.get(0);

                PartitionKey key =
                        new PartitionKey(
                            partition.topic(),
                            partition.id()
                        );

                long offset =
                        committedOffsets
                            .getOrDefault(
                                groupId,
                                Collections.emptyMap()
                            )
                            .getOrDefault(key, 0L);

                target.assignments().add(
                    new Assignment(
                        partition.topic(),
                        partition.id(),
                        offset
                    )
                );
            }
        }

        void setBrokerState(
            int brokerId,
            BrokerState state
        ) {
            Broker broker = brokers.get(brokerId);

            if (broker == null) {
                throw new KafkaException(
                    "unknown broker"
                );
            }

            broker.setState(state);

            if (state == BrokerState.OFFLINE) {
                for (Topic topic : topics.values()) {
                    for (Partition partition :
                            topic.partitions()) {
                        if (
                            partition.leaderBroker() ==
                            brokerId
                        ) {
                            electLeader(partition);
                        }
                    }
                }
            }

            consumers.values()
                .stream()
                .map(Consumer::groupId)
                .distinct()
                .forEach(this::rebalance);
        }

        List<Message> poll(
            String consumerId,
            int maxRecords
        ) {
            Consumer consumer =
                    consumers.get(consumerId);

            if (consumer == null) {
                throw new KafkaException(
                    "unknown consumer"
                );
            }

            if (
                consumer.state() !=
                ConsumerState.ACTIVE
            ) {
                throw new KafkaException(
                    "consumer is inactive"
                );
            }

            if (maxRecords < 1) {
                throw new ConfigurationException(
                    "maxRecords must be positive"
                );
            }

            List<Message> messages =
                    new ArrayList<>();

            for (
                int index = 0;
                index < consumer.assignments().size() &&
                messages.size() < maxRecords;
                index++
            ) {
                Assignment assignment =
                        consumer.assignments().get(index);

                Partition partition =
                        partition(
                            assignment.topic(),
                            assignment.partition()
                        );

                if (
                    brokers.get(
                        partition.leaderBroker()
                    ).state() ==
                    BrokerState.OFFLINE
                ) {
                    electLeader(partition);
                }

                PartitionKey key =
                        new PartitionKey(
                            assignment.topic(),
                            assignment.partition()
                        );

                List<Message> log =
                        brokers.get(
                            partition.leaderBroker()
                        ).log(key);

                long next = assignment.nextOffset();

                while (
                    next < log.size() &&
                    messages.size() < maxRecords
                ) {
                    messages.add(
                        log.get((int) next)
                    );
                    next++;
                }

                consumer.assignments().set(
                    index,
                    new Assignment(
                        assignment.topic(),
                        assignment.partition(),
                        next
                    )
                );
            }

            return messages;
        }

        void commit(
            String consumerId,
            List<Message> messages
        ) {
            Consumer consumer =
                    consumers.get(consumerId);

            if (consumer == null) {
                throw new KafkaException(
                    "unknown consumer"
                );
            }

            Map<PartitionKey, Long> offsets =
                    committedOffsets.computeIfAbsent(
                        consumer.groupId(),
                        ignored -> new HashMap<>()
                    );

            for (Message message : messages) {
                PartitionKey key =
                        new PartitionKey(
                            message.topic(),
                            message.partition()
                        );

                long nextOffset =
                        message.offset() + 1;

                long previous =
                        offsets.getOrDefault(key, 0L);

                if (nextOffset < previous) {
                    throw new OffsetException(
                        "offset regression"
                    );
                }

                offsets.put(key, nextOffset);
            }

            consumer.processed().addAll(messages);
        }

        List<Message> consumeAndCommit(
            String consumerId,
            int maxRecords
        ) {
            List<Message> messages =
                    poll(consumerId, maxRecords);

            commit(consumerId, messages);

            return messages;
        }

        void stopConsumer(String consumerId) {
            Consumer consumer =
                    consumers.get(consumerId);

            if (consumer == null) {
                throw new KafkaException(
                    "unknown consumer"
                );
            }

            consumer.setState(
                ConsumerState.INACTIVE
            );

            consumer.assignments().clear();

            rebalance(consumer.groupId());
        }

        void printState() {
            System.out.println("\nCluster state");

            brokers.values()
                .stream()
                .map(
                    broker ->
                        new BrokerSnapshot(
                            broker.id(),
                            broker.state()
                        )
                )
                .forEach(
                    snapshot ->
                        System.out.println(
                            "Broker " +
                            snapshot.id() +
                            " " +
                            snapshot.state()
                        )
                );

            topics.values()
                .stream()
                .flatMap(
                    topic ->
                        topic.partitions().stream()
                )
                .forEach(
                    partition ->
                        System.out.println(
                            partition.topic() +
                            "[" +
                            partition.id() +
                            "] leader=" +
                            partition.leaderBroker() +
                            " replicas=" +
                            partition.replicas() +
                            " HWM=" +
                            partition.highWatermark()
                        )
                );
        }
    }

    public static void main(String[] args) {
        KafkaCluster cluster =
                new KafkaCluster(3, 2);

        cluster.createTopic(
            "orders",
            3,
            3
        );

        cluster.registerConsumer(
            "orders-worker-1",
            "order-processing",
            Set.of("orders")
        );

        cluster.registerConsumer(
            "orders-worker-2",
            "order-processing",
            Set.of("orders")
        );

        String[][] orders = {
            {"customer-100", "{\"order\":\"O-100\",\"amount\":1250}"},
            {"customer-101", "{\"order\":\"O-101\",\"amount\":850}"},
            {"customer-102", "{\"order\":\"O-102\",\"amount\":2200}"},
            {"customer-100", "{\"order\":\"O-103\",\"amount\":410}"},
            {"customer-103", "{\"order\":\"O-104\",\"amount\":990}"},
            {"customer-104", "{\"order\":\"O-105\",\"amount\":730}"}
        };

        for (String[] order : orders) {
            cluster.publish(
                "orders",
                order[0],
                order[1]
            );
        }

        cluster.printState();

        List<Message> firstBatch =
                cluster.consumeAndCommit(
                    "orders-worker-1",
                    3
                );

        System.out.println(
            "\nWorker 1 processed: " +
            firstBatch.size()
        );

        cluster.setBrokerState(
            1,
            BrokerState.OFFLINE
        );

        try {
            cluster.publish(
                "orders",
                "customer-105",
                "{\"order\":\"O-106\",\"amount\":1500}"
            );
        } catch (
            BrokerUnavailableException error
        ) {
            System.out.println(
                "Expected failure: " +
                error.getMessage()
            );
        }

        cluster.setBrokerState(
            1,
            BrokerState.ONLINE
        );

        cluster.publish(
            "orders",
            "customer-105",
            "{\"order\":\"O-106\",\"amount\":1500}"
        );

        List<Message> secondBatch =
                cluster.consumeAndCommit(
                    "orders-worker-2",
                    20
                );

        System.out.println(
            "Worker 2 processed: " +
            secondBatch.size()
        );

        cluster.stopConsumer(
            "orders-worker-1"
        );

        cluster.printState();
    }
}
