import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Fault Tolerance: Enterprise Failure Detection and Recovery
 *
 * Features:
 * - Enterprise node lifecycle management
 * - Heartbeat monitoring
 * - Failure suspicion and confirmation
 * - Recovery policies
 * - Exponential retry backoff
 * - Replica availability checks
 * - Recovery execution interface
 * - Immutable event records
 * - State-transition validation
 */

public class FaultToleranceEnterprise {

    enum NodeState {
        HEALTHY,
        SUSPECT,
        FAILED,
        RECOVERING,
        DISABLED
    }

    enum RecoveryOutcome {
        SUCCESS,
        FAILURE,
        EXHAUSTED,
        DEFERRED
    }

    enum EventType {
        REGISTERED,
        HEARTBEAT,
        SUSPECT,
        FAILED,
        RECOVERY_STARTED,
        RECOVERY_SUCCESS,
        RECOVERY_FAILURE,
        RECOVERY_DEFERRED,
        RECOVERY_EXHAUSTED,
        DISABLED
    }

    static class FaultToleranceException extends RuntimeException {
        public FaultToleranceException(String message) {
            super(message);
        }
    }

    record RecoveryPolicy(
        long heartbeatTimeoutMillis,
        int failureThreshold,
        int maximumRetries,
        long initialBackoffMillis,
        long maximumBackoffMillis,
        int minimumHealthyReplicas
    ) {
        public RecoveryPolicy {
            if (heartbeatTimeoutMillis <= 0
                    || failureThreshold < 1
                    || maximumRetries < 0
                    || initialBackoffMillis <= 0
                    || maximumBackoffMillis < initialBackoffMillis
                    || minimumHealthyReplicas < 1) {
                throw new IllegalArgumentException(
                    "Invalid recovery policy"
                );
            }
        }

        long backoff(int attempt) {
            long delay = initialBackoffMillis;

            for (int i = 1; i < attempt; i++) {
                if (delay >= maximumBackoffMillis / 2) {
                    return maximumBackoffMillis;
                }

                delay *= 2;
            }

            return Math.min(delay, maximumBackoffMillis);
        }
    }

    record NodeSnapshot(
        String nodeId,
        String hostname,
        NodeState state,
        long lastHeartbeat,
        int missedHeartbeats,
        int recoveryAttempts,
        long nextRecoveryAt
    ) {}

    record ClusterEvent(
        Instant timestamp,
        String nodeId,
        EventType type,
        String details
    ) {}

    interface RecoveryExecutor {
        boolean restart(NodeSnapshot node) throws Exception;
    }

    static class Node {
        private final String nodeId;
        private final String hostname;

        private NodeState state = NodeState.HEALTHY;
        private long lastHeartbeat;
        private int missedHeartbeats;
        private int recoveryAttempts;
        private long nextRecoveryAt;

        Node(String nodeId, String hostname, long timestamp) {
            if (nodeId == null || nodeId.isBlank()
                    || hostname == null || hostname.isBlank()) {
                throw new IllegalArgumentException(
                    "Invalid node identity"
                );
            }

            this.nodeId = nodeId;
            this.hostname = hostname;
            this.lastHeartbeat = timestamp;
        }

        NodeSnapshot snapshot() {
            return new NodeSnapshot(
                nodeId,
                hostname,
                state,
                lastHeartbeat,
                missedHeartbeats,
                recoveryAttempts,
                nextRecoveryAt
            );
        }
    }

    static class FaultToleranceService {

        private final RecoveryPolicy policy;

        private final Map<String, Node> nodes = new HashMap<>();

        private final List<ClusterEvent> events =
            new ArrayList<>();

        private final AtomicBoolean running =
            new AtomicBoolean(true);

        FaultToleranceService(RecoveryPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        private void ensureRunning() {
            if (!running.get()) {
                throw new FaultToleranceException(
                    "Fault-tolerance service is stopped"
                );
            }
        }

        private void log(
            String nodeId,
            EventType type,
            String details
        ) {
            events.add(new ClusterEvent(
                Instant.now(),
                nodeId,
                type,
                details
            ));
        }

        public synchronized void registerNode(
            String nodeId,
            String hostname,
            long now
        ) {
            ensureRunning();

            if (nodes.containsKey(nodeId)) {
                throw new FaultToleranceException(
                    "Duplicate node registration"
                );
            }

            Node node = new Node(nodeId, hostname, now);

            nodes.put(nodeId, node);

            log(nodeId, EventType.REGISTERED, hostname);
        }

        public synchronized void heartbeat(
            String nodeId,
            long timestamp
        ) {
            ensureRunning();

            Node node = requireNode(nodeId);

            if (node.state == NodeState.DISABLED) {
                throw new FaultToleranceException(
                    "Disabled node cannot heartbeat"
                );
            }

            if (timestamp < node.lastHeartbeat) {
                throw new FaultToleranceException(
                    "Stale heartbeat rejected"
                );
            }

            if (timestamp > System.currentTimeMillis() + 60_000) {
                throw new FaultToleranceException(
                    "Heartbeat timestamp is in the future"
                );
            }

            NodeState previous = node.state;

            node.lastHeartbeat = timestamp;
            node.missedHeartbeats = 0;
            node.recoveryAttempts = 0;
            node.nextRecoveryAt = 0;
            node.state = NodeState.HEALTHY;

            log(nodeId, EventType.HEARTBEAT, "Heartbeat received");

            if (previous != NodeState.HEALTHY) {
                log(
                    nodeId,
                    EventType.RECOVERY_SUCCESS,
                    "Node health restored"
                );
            }
        }

        public synchronized void detectFailures(long now) {
            ensureRunning();

            if (now < 0) {
                throw new IllegalArgumentException(
                    "Invalid detection timestamp"
                );
            }

            for (Node node : nodes.values()) {
                if (node.state == NodeState.DISABLED
                        || node.state == NodeState.FAILED
                        || node.state == NodeState.RECOVERING) {
                    continue;
                }

                if (now - node.lastHeartbeat
                        < policy.heartbeatTimeoutMillis()) {
                    continue;
                }

                node.missedHeartbeats++;

                if (node.state == NodeState.HEALTHY) {
                    node.state = NodeState.SUSPECT;

                    log(
                        node.nodeId,
                        EventType.SUSPECT,
                        "Heartbeat timeout detected"
                    );
                }

                if (node.missedHeartbeats
                        >= policy.failureThreshold()) {

                    node.state = NodeState.FAILED;

                    log(
                        node.nodeId,
                        EventType.FAILED,
                        "Failure threshold exceeded"
                    );
                }
            }
        }

        private Node requireNode(String nodeId) {
            Node node = nodes.get(nodeId);

            if (node == null) {
                throw new FaultToleranceException(
                    "Unknown node: " + nodeId
                );
            }

            return node;
        }

        private int healthyReplicaCount(String excludedNode) {
            int count = 0;

            for (Node node : nodes.values()) {
                if (!node.nodeId.equals(excludedNode)
                        && node.state == NodeState.HEALTHY) {
                    count++;
                }
            }

            return count;
        }

        public RecoveryOutcome recover(
            String nodeId,
            long now,
            RecoveryExecutor executor
        ) {
            Objects.requireNonNull(executor);

            NodeSnapshot snapshot;
            int attempt;

            synchronized (this) {
                ensureRunning();

                Node node = requireNode(nodeId);

                if (node.state != NodeState.FAILED) {
                    throw new FaultToleranceException(
                        "Node is not in FAILED state"
                    );
                }

                if (node.recoveryAttempts
                        >= policy.maximumRetries()) {
                    log(
                        nodeId,
                        EventType.RECOVERY_EXHAUSTED,
                        "Retry limit reached"
                    );

                    return RecoveryOutcome.EXHAUSTED;
                }

                if (now < node.nextRecoveryAt) {
                    throw new FaultToleranceException(
                        "Recovery backoff is active"
                    );
                }

                if (healthyReplicaCount(nodeId)
                        < policy.minimumHealthyReplicas()) {

                    log(
                        nodeId,
                        EventType.RECOVERY_DEFERRED,
                        "Insufficient healthy replicas"
                    );

                    return RecoveryOutcome.DEFERRED;
                }

                node.recoveryAttempts++;
                node.state = NodeState.RECOVERING;

                attempt = node.recoveryAttempts;
                snapshot = node.snapshot();

                log(
                    nodeId,
                    EventType.RECOVERY_STARTED,
                    "Attempt " + attempt
                );
            }

            boolean success;

            try {
                success = executor.restart(snapshot);
            } catch (Exception exception) {
                success = false;
            }

            synchronized (this) {
                Node node = requireNode(nodeId);

                // A concurrent heartbeat may already have restored the node.
                if (node.state != NodeState.RECOVERING) {
                    return node.state == NodeState.HEALTHY
                        ? RecoveryOutcome.SUCCESS
                        : RecoveryOutcome.FAILURE;
                }

                if (success) {
                    node.state = NodeState.HEALTHY;
                    node.lastHeartbeat = now;
                    node.missedHeartbeats = 0;
                    node.recoveryAttempts = 0;
                    node.nextRecoveryAt = 0;

                    log(
                        nodeId,
                        EventType.RECOVERY_SUCCESS,
                        "Restart successful"
                    );

                    return RecoveryOutcome.SUCCESS;
                }

                node.state = NodeState.FAILED;

                long delay = policy.backoff(attempt);

                node.nextRecoveryAt = now + delay;

                log(
                    nodeId,
                    EventType.RECOVERY_FAILURE,
                    "Restart failed; retry delay " + delay + "ms"
                );

                return RecoveryOutcome.FAILURE;
            }
        }

        public synchronized void disableNode(String nodeId) {
            ensureRunning();

            Node node = requireNode(nodeId);

            if (node.state == NodeState.RECOVERING) {
                throw new FaultToleranceException(
                    "Cannot disable node during recovery"
                );
            }

            node.state = NodeState.DISABLED;

            log(
                nodeId,
                EventType.DISABLED,
                "Administrative shutdown"
            );
        }

        public synchronized Optional<NodeSnapshot> getNode(
            String nodeId
        ) {
            return Optional.ofNullable(nodes.get(nodeId))
                .map(Node::snapshot);
        }

        public synchronized Map<NodeState, Long> healthReport() {
            Map<NodeState, Long> report =
                new EnumMap<>(NodeState.class);

            for (NodeState state : NodeState.values()) {
                report.put(state, 0L);
            }

            for (Node node : nodes.values()) {
                report.merge(node.state, 1L, Long::sum);
            }

            return Collections.unmodifiableMap(report);
        }

        public synchronized List<ClusterEvent> getEvents() {
            return List.copyOf(events);
        }

        public void shutdown() {
            running.set(false);
        }
    }

    public static void main(String[] args) {

        RecoveryPolicy policy = new RecoveryPolicy(
            5_000,
            2,
            3,
            2_000,
            8_000,
            2
        );

        FaultToleranceService service =
            new FaultToleranceService(policy);

        long base = System.currentTimeMillis();

        service.registerNode("APP-01", "application-01", base);
        service.registerNode("APP-02", "application-02", base);
        service.registerNode("APP-03", "application-03", base);

        service.heartbeat("APP-01", base + 1);
        service.heartbeat("APP-02", base + 1);

        // Two failed observations identify the unavailable node.
        service.detectFailures(base + 6_000);
        service.detectFailures(base + 12_000);

        NodeSnapshot failed = service.getNode("APP-03")
            .orElseThrow();

        if (failed.state() != NodeState.FAILED) {
            throw new AssertionError("Failure detection failed");
        }

        RecoveryOutcome result = service.recover(
            "APP-03",
            base + 12_000,
            node -> true
        );

        if (result != RecoveryOutcome.SUCCESS) {
            throw new AssertionError("Recovery failed");
        }

        Map<NodeState, Long> report = service.healthReport();

        System.out.println("CLUSTER HEALTH");

        report.forEach((state, count) ->
            System.out.println(state + ": " + count)
        );

        if (report.get(NodeState.HEALTHY) != 3L) {
            throw new AssertionError(
                "Expected three healthy nodes"
            );
        }

        System.out.println("\nEVENT HISTORY");

        service.getEvents().forEach(event ->
            System.out.println(
                event.timestamp() + " | "
                    + event.nodeId() + " | "
                    + event.type() + " | "
                    + event.details()
            )
        );

        service.shutdown();

        System.out.println("\nAll enterprise recovery tests passed.");
    }
}
