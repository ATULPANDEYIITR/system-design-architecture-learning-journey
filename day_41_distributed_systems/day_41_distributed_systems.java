import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * Distributed Systems Fundamentals
 *
 * Enterprise-oriented model of a replicated order-processing platform.
 *
 * The design uses explicit domain types for:
 * - node health
 * - leader state
 * - replicated records
 * - quorum requirements
 * - idempotent commands
 * - failure detection
 * - merge and read eligibility
 *
 * Java 17+ standard library only.
 */
public class DistributedSystemsFundamentals {

    // ---------------------------------------------------------------------
    // Domain state
    // ---------------------------------------------------------------------

    enum NodeState {
        ONLINE,
        OFFLINE
    }

    enum OrderStatus {
        PENDING,
        CONFIRMED,
        CANCELLED
    }

    record Order(
            String orderId,
            String customerId,
            long amountCents,
            OrderStatus status,
            long version,
            String writer
    ) {
        Order {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }

            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("customerId is required");
            }

            if (amountCents <= 0) {
                throw new IllegalArgumentException("amountCents must be positive");
            }

            if (version <= 0) {
                throw new IllegalArgumentException("version must be positive");
            }
        }
    }

    // ---------------------------------------------------------------------
    // Logical clock
    // ---------------------------------------------------------------------

    static final class LogicalClock {
        private long value;

        long tick() {
            return ++value;
        }

        long receive(long remoteClock) {
            value = Math.max(value, remoteClock) + 1;
            return value;
        }

        long value() {
            return value;
        }
    }

    // ---------------------------------------------------------------------
    // Cluster node
    // ---------------------------------------------------------------------

    static final class ClusterNode {
        private final String id;
        private final LogicalClock clock = new LogicalClock();
        private NodeState state = NodeState.ONLINE;

        ClusterNode(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Node ID is required");
            }

            this.id = id;
        }

        String id() {
            return id;
        }

        NodeState state() {
            return state;
        }

        void setState(NodeState state) {
            this.state = state;
        }

        long localEvent() {
            ensureOnline();
            return clock.tick();
        }

        long receiveEvent(long remoteClock) {
            ensureOnline();
            return clock.receive(remoteClock);
        }

        private void ensureOnline() {
            if (state != NodeState.ONLINE) {
                throw new IllegalStateException(
                        "Node " + id + " is offline"
                );
            }
        }
    }

    // ---------------------------------------------------------------------
    // Replicated order storage
    // ---------------------------------------------------------------------

    static final class OrderReplica {
        private final ClusterNode node;
        private final Map<String, Order> orders = new HashMap<>();

        OrderReplica(String nodeId) {
            this.node = new ClusterNode(nodeId);
        }

        ClusterNode node() {
            return node;
        }

        void put(Order order) {
            if (node.state() != NodeState.ONLINE) {
                throw new IllegalStateException(
                        "Replica " + node.id() + " is offline"
                );
            }

            orders.merge(
                    order.orderId(),
                    order,
                    (existing, incoming) ->
                            incoming.version() >= existing.version()
                                    ? incoming
                                    : existing
            );
        }

        Optional<Order> get(String orderId) {
            if (node.state() != NodeState.ONLINE) {
                return Optional.empty();
            }

            return Optional.ofNullable(orders.get(orderId));
        }
    }

    // ---------------------------------------------------------------------
    // Explicit quorum policy
    // ---------------------------------------------------------------------

    record QuorumPolicy(int replicationFactor, int writeQuorum, int readQuorum) {

        QuorumPolicy {
            if (replicationFactor <= 0) {
                throw new IllegalArgumentException(
                        "Replication factor must be positive"
                );
            }

            if (writeQuorum < 1 || writeQuorum > replicationFactor) {
                throw new IllegalArgumentException(
                        "Invalid write quorum"
                );
            }

            if (readQuorum < 1 || readQuorum > replicationFactor) {
                throw new IllegalArgumentException(
                        "Invalid read quorum"
                );
            }
        }

        boolean canCompleteRead(int responses) {
            return responses >= readQuorum;
        }

        boolean canCompleteWrite(int acknowledgements) {
            return acknowledgements >= writeQuorum;
        }
    }

    // ---------------------------------------------------------------------
    // Failure detector
    // ---------------------------------------------------------------------

    static final class FailureDetector {
        private final Duration timeout;
        private final Map<String, Instant> lastHeartbeat = new HashMap<>();

        FailureDetector(Duration timeout) {
            if (timeout.isNegative() || timeout.isZero()) {
                throw new IllegalArgumentException(
                        "Heartbeat timeout must be positive"
                );
            }

            this.timeout = timeout;
        }

        void heartbeat(String nodeId, Instant timestamp) {
            lastHeartbeat.put(nodeId, timestamp);
        }

        boolean suspected(String nodeId, Instant now) {
            Instant last = lastHeartbeat.get(nodeId);

            if (last == null) {
                return true;
            }

            return Duration.between(last, now).compareTo(timeout) > 0;
        }
    }

    // ---------------------------------------------------------------------
    // Leader election
    // ---------------------------------------------------------------------

    static final class LeaderService {
        private final Map<String, ClusterNode> nodes = new HashMap<>();
        private String leader;

        LeaderService(List<String> nodeIds) {
            if (nodeIds.isEmpty()) {
                throw new IllegalArgumentException("Cluster cannot be empty");
            }

            for (String nodeId : nodeIds) {
                nodes.put(nodeId, new ClusterNode(nodeId));
            }
        }

        String elect() {
            return nodes.values()
                    .stream()
                    .filter(node -> node.state() == NodeState.ONLINE)
                    .map(ClusterNode::id)
                    .max(Comparator.naturalOrder())
                    .map(id -> {
                        leader = id;
                        return id;
                    })
                    .orElseThrow(() ->
                            new IllegalStateException(
                                    "No online node can become leader"
                            ));
        }

        void failLeader() {
            if (leader == null) {
                throw new IllegalStateException("No current leader");
            }

            nodes.get(leader).setState(NodeState.OFFLINE);
            leader = null;
        }

        String currentLeader() {
            if (leader == null) {
                throw new IllegalStateException("Leader is not elected");
            }

            return leader;
        }

        ClusterNode node(String nodeId) {
            ClusterNode node = nodes.get(nodeId);

            if (node == null) {
                throw new IllegalArgumentException(
                        "Unknown node: " + nodeId
                );
            }

            return node;
        }
    }

    // ---------------------------------------------------------------------
    // Idempotency policy
    // ---------------------------------------------------------------------

    static final class IdempotencyService {
        private final Set<String> completedRequests = new HashSet<>();

        boolean isCompleted(String requestId) {
            return completedRequests.contains(requestId);
        }

        void markCompleted(String requestId) {
            completedRequests.add(requestId);
        }
    }

    // ---------------------------------------------------------------------
    // Enterprise order service
    // ---------------------------------------------------------------------

    static final class DistributedOrderService {
        private final LeaderService leaders;
        private final List<OrderReplica> replicas;
        private final QuorumPolicy quorumPolicy;
        private final IdempotencyService idempotency;
        private long version;

        DistributedOrderService() {
            this.leaders = new LeaderService(
                    List.of("node-a", "node-b", "node-c")
            );

            this.replicas = new ArrayList<>(
                    List.of(
                            new OrderReplica("replica-a"),
                            new OrderReplica("replica-b"),
                            new OrderReplica("replica-c")
                    )
            );

            this.quorumPolicy = new QuorumPolicy(3, 2, 2);
            this.idempotency = new IdempotencyService();
            this.version = 0;

            leaders.elect();
        }

        Order submit(
                String requestId,
                String customerId,
                long amountCents
        ) {
            validateRequest(requestId, customerId, amountCents);

            if (idempotency.isCompleted(requestId)) {
                return read(requestId);
            }

            String leader = leaders.currentLeader();

            version++;

            Order order = new Order(
                    requestId,
                    customerId,
                    amountCents,
                    OrderStatus.CONFIRMED,
                    version,
                    leader
            );

            int acknowledgements = 0;

            for (OrderReplica replica : replicas) {
                if (replica.node().state() != NodeState.ONLINE) {
                    continue;
                }

                replica.put(order);
                acknowledgements++;
            }

            if (!quorumPolicy.canCompleteWrite(acknowledgements)) {
                throw new IllegalStateException(
                        "Write quorum unavailable: "
                                + acknowledgements
                                + "/"
                                + quorumPolicy.writeQuorum()
                );
            }

            idempotency.markCompleted(requestId);
            return order;
        }

        Order read(String orderId) {
            List<Order> responses = replicas.stream()
                    .map(replica -> replica.get(orderId))
                    .flatMap(Optional::stream)
                    .toList();

            if (!quorumPolicy.canCompleteRead(responses.size())) {
                throw new IllegalStateException(
                        "Read quorum unavailable: "
                                + responses.size()
                                + "/"
                                + quorumPolicy.readQuorum()
                );
            }

            return responses.stream()
                    .max(Comparator.comparingLong(Order::version))
                    .orElseThrow();
        }

        void failLeaderAndReelect() {
            leaders.failLeader();
            leaders.elect();
        }

        void setReplicaState(String replicaId, NodeState state) {
            replicas.stream()
                    .filter(replica ->
                            replica.node().id().equals(replicaId))
                    .findFirst()
                    .orElseThrow(() ->
                            new IllegalArgumentException(
                                    "Unknown replica: " + replicaId
                            ))
                    .node()
                    .setState(state);
        }

        String leader() {
            return leaders.currentLeader();
        }

        private void validateRequest(
                String requestId,
                String customerId,
                long amountCents
        ) {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException(
                        "requestId is required"
                );
            }

            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException(
                        "customerId is required"
                );
            }

            if (amountCents <= 0) {
                throw new IllegalArgumentException(
                        "amountCents must be positive"
                );
            }
        }
    }

    // ---------------------------------------------------------------------
    // Demonstration
    // ---------------------------------------------------------------------

    public static void main(String[] args) {
        System.out.println(
                "Distributed Systems Fundamentals - Java 17"
        );

        demonstrateLogicalClock();
        demonstrateFailureDetection();
        demonstrateEnterpriseService();
    }

    private static void demonstrateLogicalClock() {
        System.out.println("\n=== Logical Clock ===");

        ClusterNode producer = new ClusterNode("producer");
        ClusterNode consumer = new ClusterNode("consumer");

        long producedAt = producer.localEvent();
        long consumedAt = consumer.receiveEvent(producedAt);

        System.out.println(
                "Producer event clock: " + producedAt
        );

        System.out.println(
                "Consumer receive clock: " + consumedAt
        );
    }

    private static void demonstrateFailureDetection() {
        System.out.println("\n=== Failure Detection ===");

        FailureDetector detector = new FailureDetector(
                Duration.ofSeconds(5)
        );

        Instant heartbeat = Instant.parse(
                "2026-10-11T02:00:00Z"
        );

        detector.heartbeat("node-a", heartbeat);

        System.out.println(
                "Node suspected after 3 seconds: "
                        + detector.suspected(
                                "node-a",
                                heartbeat.plusSeconds(3)
                        )
        );

        System.out.println(
                "Node suspected after 7 seconds: "
                        + detector.suspected(
                                "node-a",
                                heartbeat.plusSeconds(7)
                        )
        );
    }

    private static void demonstrateEnterpriseService() {
        System.out.println("\n=== Enterprise Distributed Order Service ===");

        DistributedOrderService service =
                new DistributedOrderService();

        Order first = service.submit(
                "ORD-1001",
                "CUSTOMER-42",
                250000
        );

        System.out.println("Leader: " + service.leader());
        System.out.println("Order status: " + first.status());
        System.out.println("Version: " + first.version());

        Order retry = service.submit(
                "ORD-1001",
                "CUSTOMER-42",
                250000
        );

        System.out.println(
                "Idempotent retry version: " + retry.version()
        );

        service.failLeaderAndReelect();

        System.out.println(
                "Leader after failover: " + service.leader()
        );

        Order second = service.submit(
                "ORD-1002",
                "CUSTOMER-88",
                7500
        );

        System.out.println(
                "Second order writer: " + second.writer()
        );

        service.setReplicaState(
                "replica-c",
                NodeState.OFFLINE
        );

        Order third = service.submit(
                "ORD-1003",
                "CUSTOMER-91",
                8800
        );

        System.out.println(
                "Order after one replica failure: "
                        + third.orderId()
        );

        service.setReplicaState(
                "replica-b",
                NodeState.OFFLINE
        );

        try {
            service.submit(
                    "ORD-1004",
                    "CUSTOMER-99",
                    1200
            );
        } catch (IllegalStateException ex) {
            System.out.println(
                    "Expected quorum failure: "
                            + ex.getMessage()
            );
        }
    }
}
