import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

public class RedundancyEnterprise {

    enum Architecture {
        ACTIVE_ACTIVE,
        ACTIVE_PASSIVE
    }

    enum Role {
        ACTIVE,
        PASSIVE,
        FAILED,
        RECOVERING
    }

    enum Health {
        HEALTHY,
        DEGRADED,
        DOWN
    }

    enum ReplicationMode {
        SYNCHRONOUS,
        ASYNCHRONOUS
    }

    enum ClusterState {
        NORMAL,
        DEGRADED,
        FAILOVER_IN_PROGRESS,
        FAILOVER_COMPLETED,
        UNAVAILABLE
    }

    record ClusterPolicy(
        Architecture architecture,
        ReplicationMode replicationMode,
        int requiredActiveNodes,
        long maximumReplicationLag,
        boolean automaticFailover,
        boolean allowDegradedWrites
    ) {
        ClusterPolicy {
            Objects.requireNonNull(architecture);
            Objects.requireNonNull(replicationMode);

            if (requiredActiveNodes < 1) {
                throw new IllegalArgumentException(
                    "Required active nodes must be positive"
                );
            }

            if (maximumReplicationLag < 0) {
                throw new IllegalArgumentException(
                    "Replication lag cannot be negative"
                );
            }
        }
    }

    record WriteRecord(
        long sequence,
        String key,
        String value,
        Instant timestamp,
        String originNode
    ) {}

    record OperationResult(
        boolean successful,
        String message,
        String nodeId,
        long sequence
    ) {}

    record FailoverRecord(
        String eventId,
        String failedNode,
        String promotedNode,
        long fencingEpoch,
        Instant timestamp,
        boolean successful
    ) {}

    static class Node {
        private final String id;
        private final String region;
        private final int capacity;

        private Role role;
        private Health health;

        private int currentLoad;
        private long appliedSequence;
        private long replicationLag;

        private long fencingEpoch;

        private final Map<String, String> localData =
            new HashMap<>();

        Node(
            String id,
            String region,
            int capacity,
            Role role
        ) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Invalid node ID");
            }

            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException("Invalid region");
            }

            if (capacity <= 0) {
                throw new IllegalArgumentException(
                    "Node capacity must be positive"
                );
            }

            this.id = id;
            this.region = region;
            this.capacity = capacity;
            this.role = Objects.requireNonNull(role);
            this.health = Health.HEALTHY;
        }

        boolean available() {
            return health != Health.DOWN &&
                currentLoad < capacity;
        }

        void acquire() {
            if (!available()) {
                throw new IllegalStateException(
                    "Node has no available capacity: " + id
                );
            }

            currentLoad++;
        }

        void release() {
            currentLoad = Math.max(0, currentLoad - 1);
        }

        String getId() {
            return id;
        }

        String getRegion() {
            return region;
        }

        Role getRole() {
            return role;
        }

        Health getHealth() {
            return health;
        }

        long getAppliedSequence() {
            return appliedSequence;
        }

        long getReplicationLag() {
            return replicationLag;
        }
    }

    static class FencingService {
        private final AtomicLong epoch = new AtomicLong();
        private String owner;

        synchronized long acquire(String nodeId) {
            owner = nodeId;
            return epoch.incrementAndGet();
        }

        synchronized boolean validate(
            String nodeId,
            long token
        ) {
            return Objects.equals(owner, nodeId) &&
                epoch.get() == token;
        }

        long currentEpoch() {
            return epoch.get();
        }
    }

    static class ClusterException extends RuntimeException {
        ClusterException(String message) {
            super(message);
        }
    }

    static class ReplicationException extends ClusterException {
        ReplicationException(String message) {
            super(message);
        }
    }

    static class AvailabilityException extends ClusterException {
        AvailabilityException(String message) {
            super(message);
        }
    }

    static class GovernanceService {
        private final ClusterPolicy policy;

        private final Map<String, Node> nodes =
            new LinkedHashMap<>();

        private final Map<String, String> committedData =
            new HashMap<>();

        private final List<WriteRecord> writeLog =
            new ArrayList<>();

        private final List<FailoverRecord> failoverHistory =
            new ArrayList<>();

        private final FencingService fencing =
            new FencingService();

        private long sequence;
        private long primaryEpoch;

        private ClusterState state = ClusterState.NORMAL;

        GovernanceService(
            ClusterPolicy policy,
            List<Node> initialNodes
        ) {
            this.policy = Objects.requireNonNull(policy);

            for (Node node : initialNodes) {
                if (nodes.putIfAbsent(node.id, node) != null) {
                    throw new IllegalArgumentException(
                        "Duplicate node ID: " + node.id
                    );
                }
            }

            validateInitialConfiguration();
            initializeArchitecture();
        }

        private void validateInitialConfiguration() {
            if (nodes.size() < 2) {
                throw new IllegalArgumentException(
                    "At least two nodes are required"
                );
            }

            long healthy = nodes.values().stream()
                .filter(node -> node.health == Health.HEALTHY)
                .count();

            if (healthy == 0) {
                throw new AvailabilityException(
                    "No healthy nodes available"
                );
            }

            if (policy.architecture() == Architecture.ACTIVE_ACTIVE &&
                healthy < policy.requiredActiveNodes()) {
                throw new AvailabilityException(
                    "Insufficient active nodes"
                );
            }
        }

        private void initializeArchitecture() {
            List<Node> healthy = nodes.values().stream()
                .filter(node -> node.health == Health.HEALTHY)
                .toList();

            if (policy.architecture() == Architecture.ACTIVE_ACTIVE) {
                healthy.forEach(node -> node.role = Role.ACTIVE);
                primaryEpoch = fencing.acquire("ACTIVE-ACTIVE");
            } else {
                Node primary = healthy.get(0);

                primary.role = Role.ACTIVE;

                healthy.stream()
                    .filter(node -> node != primary)
                    .forEach(node -> node.role = Role.PASSIVE);

                primaryEpoch = fencing.acquire(primary.id);
                primary.fencingEpoch = primaryEpoch;
            }
        }

        private List<Node> activeNodes() {
            return nodes.values().stream()
                .filter(node ->
                    node.role == Role.ACTIVE && node.available()
                )
                .sorted(
                    Comparator.comparingDouble(
                        node -> (double) node.currentLoad / node.capacity
                    )
                )
                .toList();
        }

        private Node selectNode() {
            List<Node> active = activeNodes();

            if (active.isEmpty()) {
                state = ClusterState.UNAVAILABLE;
                throw new AvailabilityException(
                    "No active node available"
                );
            }

            if (policy.architecture() == Architecture.ACTIVE_ACTIVE &&
                active.size() < policy.requiredActiveNodes()) {
                state = ClusterState.DEGRADED;
                throw new AvailabilityException(
                    "Minimum active node count not satisfied"
                );
            }

            return active.get(0);
        }

        public synchronized OperationResult read(String key) {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException(
                    "Read key cannot be empty"
                );
            }

            Node node = selectNode();
            node.acquire();

            try {
                return new OperationResult(
                    true,
                    "Read completed",
                    node.id,
                    node.appliedSequence
                );
            } finally {
                node.release();
            }
        }

        public synchronized OperationResult write(
            String key,
            String value
        ) {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException(
                    "Write key cannot be empty"
                );
            }

            Objects.requireNonNull(value, "Value cannot be null");

            Node source = selectNode();
            source.acquire();

            try {
                if (source.health == Health.DEGRADED &&
                    !policy.allowDegradedWrites()) {
                    throw new ClusterException(
                        "Writes disabled for degraded node"
                    );
                }

                if (policy.architecture() == Architecture.ACTIVE_PASSIVE &&
                    !fencing.validate(
                        source.id,
                        source.fencingEpoch
                    )) {
                    throw new ClusterException(
                        "Stale primary fencing token"
                    );
                }

                List<Node> replicas = nodes.values().stream()
                    .filter(node -> !node.id.equals(source.id))
                    .filter(node -> node.health != Health.DOWN)
                    .filter(node ->
                        policy.architecture() == Architecture.ACTIVE_ACTIVE ||
                        node.role == Role.PASSIVE
                    )
                    .toList();

                if (policy.replicationMode() ==
                    ReplicationMode.SYNCHRONOUS) {
                    if (replicas.isEmpty()) {
                        throw new ReplicationException(
                            "Synchronous replica unavailable"
                        );
                    }

                    for (Node replica : replicas) {
                        if (replica.health != Health.HEALTHY) {
                            throw new ReplicationException(
                                "Replica is not healthy: " + replica.id
                            );
                        }
                    }
                }

                long nextSequence = sequence + 1;

                WriteRecord record = new WriteRecord(
                    nextSequence,
                    key,
                    value,
                    Instant.now(),
                    source.id
                );

                // All synchronous replicas are validated before
                // the committed state is modified.
                if (policy.replicationMode() ==
                    ReplicationMode.SYNCHRONOUS) {
                    for (Node replica : replicas) {
                        replica.localData.put(key, value);
                        replica.appliedSequence = nextSequence;
                        replica.replicationLag = 0;
                    }
                } else {
                    for (Node replica : replicas) {
                        replica.replicationLag++;
                    }
                }

                source.localData.put(key, value);
                source.appliedSequence = nextSequence;

                committedData.put(key, value);
                writeLog.add(record);
                sequence = nextSequence;

                state = ClusterState.NORMAL;

                return new OperationResult(
                    true,
                    "Write committed",
                    source.id,
                    sequence
                );

            } finally {
                source.release();
            }
        }

        public synchronized OperationResult failNode(
            String nodeId
        ) {
            Node failed = nodes.get(nodeId);

            if (failed == null) {
                throw new IllegalArgumentException(
                    "Unknown node: " + nodeId
                );
            }

            if (failed.health == Health.DOWN) {
                return new OperationResult(
                    false,
                    "Node already down",
                    nodeId,
                    sequence
                );
            }

            failed.health = Health.DOWN;
            failed.role = Role.FAILED;
            failed.currentLoad = 0;

            if (policy.architecture() == Architecture.ACTIVE_ACTIVE) {
                long available = activeNodes().size();

                state = available >= policy.requiredActiveNodes()
                    ? ClusterState.NORMAL
                    : ClusterState.UNAVAILABLE;

                return new OperationResult(
                    available >= policy.requiredActiveNodes(),
                    "Active-active availability evaluated",
                    nodeId,
                    sequence
                );
            }

            if (!policy.automaticFailover()) {
                state = ClusterState.UNAVAILABLE;

                return new OperationResult(
                    false,
                    "Automatic failover disabled",
                    nodeId,
                    sequence
                );
            }

            return promoteStandby(nodeId);
        }

        private OperationResult promoteStandby(
            String failedNode
        ) {
            state = ClusterState.FAILOVER_IN_PROGRESS;

            Optional<Node> candidate = nodes.values().stream()
                .filter(node -> node.role == Role.PASSIVE)
                .filter(node -> node.health == Health.HEALTHY)
                .filter(node ->
                    node.replicationLag <= policy.maximumReplicationLag()
                )
                .filter(node ->
                    policy.replicationMode() != ReplicationMode.SYNCHRONOUS ||
                    node.appliedSequence == sequence
                )
                .sorted(
                    Comparator.comparingLong(Node::getAppliedSequence)
                        .reversed()
                )
                .findFirst();

            if (candidate.isEmpty()) {
                state = ClusterState.UNAVAILABLE;

                failoverHistory.add(
                    new FailoverRecord(
                        UUID.randomUUID().toString(),
                        failedNode,
                        null,
                        fencing.currentEpoch(),
                        Instant.now(),
                        false
                    )
                );

                return new OperationResult(
                    false,
                    "No eligible standby",
                    null,
                    sequence
                );
            }

            Node promoted = candidate.get();

            // A new epoch invalidates the old primary's authority.
            primaryEpoch = fencing.acquire(promoted.id);

            promoted.fencingEpoch = primaryEpoch;
            promoted.role = Role.ACTIVE;
            promoted.replicationLag = 0;

            state = ClusterState.FAILOVER_COMPLETED;

            failoverHistory.add(
                new FailoverRecord(
                    UUID.randomUUID().toString(),
                    failedNode,
                    promoted.id,
                    primaryEpoch,
                    Instant.now(),
                    true
                )
            );

            return new OperationResult(
                true,
                "Standby promoted",
                promoted.id,
                sequence
            );
        }

        public synchronized int synchronizeNode(String nodeId) {
            Node node = nodes.get(nodeId);

            if (node == null) {
                throw new IllegalArgumentException("Unknown node");
            }

            if (node.health == Health.DOWN) {
                throw new AvailabilityException(
                    "Failed node cannot be synchronized"
                );
            }

            int applied = 0;

            for (WriteRecord record : writeLog) {
                if (record.sequence() > node.appliedSequence) {
                    node.localData.put(
                        record.key(),
                        record.value()
                    );

                    node.appliedSequence = record.sequence();
                    applied++;
                }
            }

            node.replicationLag = Math.max(
                0,
                sequence - node.appliedSequence
            );

            return applied;
        }

        public synchronized void recoverNode(String nodeId) {
            Node node = nodes.get(nodeId);

            if (node == null) {
                throw new IllegalArgumentException("Unknown node");
            }

            if (node.health != Health.DOWN) {
                throw new ClusterException(
                    "Node is not in failed state"
                );
            }

            node.health = Health.HEALTHY;
            node.role = Role.RECOVERING;

            synchronizeNode(nodeId);

            if (policy.architecture() == Architecture.ACTIVE_ACTIVE) {
                node.role = Role.ACTIVE;
                node.fencingEpoch = fencing.acquire("ACTIVE-ACTIVE");
            } else {
                node.role = Role.PASSIVE;
                node.fencingEpoch = 0;
            }

            if (state == ClusterState.UNAVAILABLE &&
                !activeNodes().isEmpty()) {
                state = ClusterState.NORMAL;
            }
        }

        public synchronized void report() {
            System.out.println("\nENTERPRISE CLUSTER REPORT");
            System.out.println("Architecture: " + policy.architecture());
            System.out.println("Replication: " + policy.replicationMode());
            System.out.println("State: " + state);
            System.out.println("Sequence: " + sequence);
            System.out.println("Fencing epoch: " + fencing.currentEpoch());

            System.out.println("\nNODE INVENTORY");

            for (Node node : nodes.values()) {
                System.out.printf(
                    "%s | %s | %s | %s | sequence=%d | lag=%d%n",
                    node.id,
                    node.region,
                    node.role,
                    node.health,
                    node.appliedSequence,
                    node.replicationLag
                );
            }

            System.out.println("\nFAILOVER HISTORY");

            failoverHistory.forEach(System.out::println);

            Map<Role, Long> roleCounts = nodes.values().stream()
                .collect(Collectors.groupingBy(
                    node -> node.role,
                    Collectors.counting()
                ));

            System.out.println("\nROLE DISTRIBUTION");
            System.out.println(roleCounts);
        }

        public synchronized Optional<String> getValue(String key) {
            return Optional.ofNullable(committedData.get(key));
        }
    }

    private static void activeActiveExample() {
        System.out.println("\n=== ACTIVE-ACTIVE ===");

        ClusterPolicy policy = new ClusterPolicy(
            Architecture.ACTIVE_ACTIVE,
            ReplicationMode.ASYNCHRONOUS,
            2,
            5,
            true,
            false
        );

        List<Node> nodes = List.of(
            new Node("AA-1", "Mumbai", 100, Role.ACTIVE),
            new Node("AA-2", "Pune", 100, Role.ACTIVE),
            new Node("AA-3", "Delhi", 100, Role.ACTIVE)
        );

        GovernanceService service =
            new GovernanceService(policy, nodes);

        System.out.println(service.write("customer:1", "ACTIVE"));
        System.out.println(service.write("customer:2", "PENDING"));

        service.report();

        System.out.println(service.failNode("AA-1"));

        service.report();

        service.recoverNode("AA-1");
        service.report();
    }

    private static void activePassiveExample() {
        System.out.println("\n=== ACTIVE-PASSIVE ===");

        ClusterPolicy policy = new ClusterPolicy(
            Architecture.ACTIVE_PASSIVE,
            ReplicationMode.SYNCHRONOUS,
            1,
            0,
            true,
            false
        );

        List<Node> nodes = List.of(
            new Node("PRIMARY", "Mumbai", 200, Role.ACTIVE),
            new Node("STANDBY-1", "Pune", 200, Role.PASSIVE),
            new Node("STANDBY-2", "Delhi", 150, Role.PASSIVE)
        );

        GovernanceService service =
            new GovernanceService(policy, nodes);

        service.write("inventory:101", "500");
        service.write("inventory:102", "250");

        service.report();

        System.out.println(service.failNode("PRIMARY"));

        service.write("inventory:103", "750");

        service.report();

        service.recoverNode("PRIMARY");

        System.out.println(
            "Recovered value: " +
            service.getValue("inventory:101").orElse("NOT FOUND")
        );

        service.report();
    }

    public static void main(String[] args) {
        try {
            activeActiveExample();
            activePassiveExample();
        } catch (Exception exception) {
            System.err.println(
                "Execution failed: " + exception.getMessage()
            );

            exception.printStackTrace();
        }
    }
}
