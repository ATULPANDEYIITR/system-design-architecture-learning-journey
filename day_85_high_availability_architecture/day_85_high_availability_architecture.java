import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

/*
 * High Availability Architecture
 *
 * Enterprise infrastructure governance and orchestration model.
 *
 * Features:
 * - Typed infrastructure domain objects
 * - Active-active application services
 * - Database replication requirements
 * - Independent failure domains
 * - Quorum and leader-election rules
 * - Health monitoring
 * - Failover and recovery
 * - Capacity-aware traffic management
 * - Availability policy evaluation
 *
 * Java 17, standard library only.
 */

public class Main {

    enum NodeStatus {
        HEALTHY,
        FAILED,
        MAINTENANCE
    }

    enum ServiceStatus {
        AVAILABLE,
        DEGRADED,
        UNAVAILABLE
    }

    enum FailureSeverity {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    record NodeConfiguration(
        String id,
        String role,
        String zone,
        int capacity
    ) {
        NodeConfiguration {
            Objects.requireNonNull(id);
            Objects.requireNonNull(role);
            Objects.requireNonNull(zone);

            if (id.isBlank() || role.isBlank() || zone.isBlank()) {
                throw new IllegalArgumentException(
                    "Node attributes cannot be blank"
                );
            }

            if (capacity <= 0) {
                throw new IllegalArgumentException(
                    "Capacity must be positive"
                );
            }
        }
    }

    record HealthResult(
        String nodeId,
        boolean healthy,
        Instant checkedAt,
        String message
    ) {}

    record AvailabilityPolicy(
        int minimumHealthyReplicas,
        boolean requireMultipleZones,
        boolean allowMaintenance
    ) {
        AvailabilityPolicy {
            if (minimumHealthyReplicas < 1) {
                throw new IllegalArgumentException(
                    "Minimum replica count must be positive"
                );
            }
        }
    }

    record ServiceAssessment(
        String serviceId,
        ServiceStatus status,
        int healthyReplicas,
        int requiredReplicas,
        Set<String> activeZones
    ) {}

    record FailureReport(
        String resource,
        String failureDomain,
        FailureSeverity severity,
        String description
    ) {}

    static class InfrastructureException extends RuntimeException {
        InfrastructureException(String message) {
            super(message);
        }
    }

    static class InfrastructureNode {
        private final NodeConfiguration configuration;
        private NodeStatus status = NodeStatus.HEALTHY;
        private int activeRequests;
        private long completedRequests;
        private Instant lastHeartbeat = Instant.now();

        InfrastructureNode(NodeConfiguration configuration) {
            this.configuration = configuration;
        }

        String id() {
            return configuration.id();
        }

        String zone() {
            return configuration.zone();
        }

        String role() {
            return configuration.role();
        }

        int capacity() {
            return configuration.capacity();
        }

        int activeRequests() {
            return activeRequests;
        }

        int availableCapacity() {
            if (status != NodeStatus.HEALTHY) return 0;
            return capacity() - activeRequests;
        }

        boolean isHealthy() {
            return status == NodeStatus.HEALTHY;
        }

        HealthResult probe() {
            boolean healthy = isHealthy();

            if (healthy) {
                lastHeartbeat = Instant.now();
            }

            return new HealthResult(
                id(),
                healthy,
                Instant.now(),
                healthy ? "Heartbeat successful" : status.name()
            );
        }

        boolean acquire() {
            if (availableCapacity() <= 0) return false;

            activeRequests++;
            return true;
        }

        void release() {
            if (activeRequests <= 0) {
                throw new InfrastructureException(
                    "Request counter underflow for " + id()
                );
            }

            activeRequests--;
            completedRequests++;
        }

        void fail() {
            status = NodeStatus.FAILED;
            activeRequests = 0;
        }

        void recover() {
            status = NodeStatus.HEALTHY;
            activeRequests = 0;
            lastHeartbeat = Instant.now();
        }

        void maintenance() {
            status = NodeStatus.MAINTENANCE;
            activeRequests = 0;
        }

        long completedRequests() {
            return completedRequests;
        }
    }

    static class ApplicationService {
        private final String id;
        private final List<String> replicaIds;
        private final AvailabilityPolicy policy;

        ApplicationService(
            String id,
            List<String> replicaIds,
            AvailabilityPolicy policy
        ) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Service ID required");
            }

            if (replicaIds == null || replicaIds.isEmpty()) {
                throw new IllegalArgumentException("Replicas required");
            }

            if (new HashSet<>(replicaIds).size() != replicaIds.size()) {
                throw new IllegalArgumentException(
                    "Replica IDs must be unique"
                );
            }

            if (policy.minimumHealthyReplicas() > replicaIds.size()) {
                throw new IllegalArgumentException(
                    "Minimum healthy count exceeds replica count"
                );
            }

            this.id = id;
            this.replicaIds = List.copyOf(replicaIds);
            this.policy = policy;
        }

        String id() {
            return id;
        }

        List<String> replicas() {
            return replicaIds;
        }

        AvailabilityPolicy policy() {
            return policy;
        }
    }

    static class QuorumService {
        private final List<String> memberIds;
        private final int majority;
        private final AtomicLong term = new AtomicLong(0);

        private String leaderId;

        QuorumService(List<String> members) {
            if (members == null ||
                members.size() < 3 ||
                members.size() % 2 == 0 ||
                new HashSet<>(members).size() != members.size()) {
                throw new IllegalArgumentException(
                    "Quorum requires unique odd membership of at least three"
                );
            }

            memberIds = List.copyOf(members);
            majority = members.size() / 2 + 1;
        }

        List<String> members() {
            return memberIds;
        }

        int requiredVotes() {
            return majority;
        }

        int countVotes(Map<String, InfrastructureNode> nodes) {
            return (int) memberIds.stream()
                .filter(nodes::containsKey)
                .filter(id -> nodes.get(id).isHealthy())
                .count();
        }

        boolean hasQuorum(Map<String, InfrastructureNode> nodes) {
            return countVotes(nodes) >= majority;
        }

        synchronized String electLeader(
            Map<String, InfrastructureNode> nodes
        ) {
            List<String> healthy = memberIds.stream()
                .filter(nodes::containsKey)
                .filter(id -> nodes.get(id).isHealthy())
                .sorted()
                .toList();

            if (healthy.size() < majority) {
                leaderId = null;
                return null;
            }

            leaderId = healthy.get(0);
            term.incrementAndGet();

            return leaderId;
        }

        synchronized void invalidateLeader(String failedNode) {
            if (Objects.equals(leaderId, failedNode)) {
                leaderId = null;
            }
        }

        String leader() {
            return leaderId;
        }

        long currentTerm() {
            return term.get();
        }
    }

    static class AvailabilityEvaluator {
        ServiceAssessment evaluate(
            ApplicationService service,
            Map<String, InfrastructureNode> nodes
        ) {
            int healthy = 0;
            Set<String> zones = new HashSet<>();

            for (String id : service.replicas()) {
                InfrastructureNode node = nodes.get(id);

                if (node != null && node.isHealthy()) {
                    healthy++;
                    zones.add(node.zone());
                }
            }

            AvailabilityPolicy policy = service.policy();

            boolean enoughReplicas =
                healthy >= policy.minimumHealthyReplicas();

            boolean enoughZones =
                !policy.requireMultipleZones() || zones.size() >= 2;

            ServiceStatus status;

            if (!enoughReplicas || !enoughZones) {
                status = ServiceStatus.UNAVAILABLE;
            } else if (healthy < service.replicas().size()) {
                status = ServiceStatus.DEGRADED;
            } else {
                status = ServiceStatus.AVAILABLE;
            }

            return new ServiceAssessment(
                service.id(),
                status,
                healthy,
                policy.minimumHealthyReplicas(),
                Set.copyOf(zones)
            );
        }
    }

    static class TrafficManager {
        private final Map<String, InfrastructureNode> nodes;

        TrafficManager(Map<String, InfrastructureNode> nodes) {
            this.nodes = nodes;
        }

        synchronized InfrastructureNode acquire(
            ApplicationService service
        ) {
            return service.replicas().stream()
                .map(nodes::get)
                .filter(Objects::nonNull)
                .filter(InfrastructureNode::isHealthy)
                .filter(node -> node.availableCapacity() > 0)
                .min(
                    Comparator.comparingDouble(
                        node -> (double) node.activeRequests() /
                            node.capacity()
                    ).thenComparing(InfrastructureNode::id)
                )
                .filter(InfrastructureNode::acquire)
                .orElse(null);
        }
    }

    static class RepositoryGovernanceService {
        private final Map<String, InfrastructureNode> nodes =
            new HashMap<>();

        private final Map<String, ApplicationService> services =
            new HashMap<>();

        private final AvailabilityEvaluator evaluator =
            new AvailabilityEvaluator();

        private final TrafficManager trafficManager =
            new TrafficManager(nodes);

        private QuorumService quorum;

        private long totalRequests;
        private long successfulRequests;
        private long failedRequests;

        void registerNode(NodeConfiguration configuration) {
            InfrastructureNode node =
                new InfrastructureNode(configuration);

            if (nodes.putIfAbsent(node.id(), node) != null) {
                throw new InfrastructureException(
                    "Duplicate infrastructure node"
                );
            }
        }

        void registerService(ApplicationService service) {
            if (services.containsKey(service.id())) {
                throw new InfrastructureException("Duplicate service");
            }

            for (String id : service.replicas()) {
                if (!nodes.containsKey(id)) {
                    throw new InfrastructureException(
                        "Unknown replica: " + id
                    );
                }
            }

            services.put(service.id(), service);
        }

        void configureQuorum(QuorumService cluster) {
            for (String id : cluster.members()) {
                if (!nodes.containsKey(id)) {
                    throw new InfrastructureException(
                        "Unknown quorum member: " + id
                    );
                }
            }

            quorum = cluster;
            quorum.electLeader(nodes);
        }

        synchronized InfrastructureNode handleRequest(
            String serviceId
        ) {
            ApplicationService service = services.get(serviceId);

            if (service == null) {
                throw new InfrastructureException("Unknown service");
            }

            totalRequests++;

            ServiceAssessment assessment =
                evaluator.evaluate(service, nodes);

            if (assessment.status() == ServiceStatus.UNAVAILABLE) {
                failedRequests++;
                return null;
            }

            InfrastructureNode selected =
                trafficManager.acquire(service);

            if (selected == null) {
                failedRequests++;
                return null;
            }

            successfulRequests++;
            return selected;
        }

        void completeRequest(InfrastructureNode node) {
            node.release();
        }

        void failNode(String nodeId) {
            InfrastructureNode node = nodes.get(nodeId);

            if (node == null) {
                throw new InfrastructureException("Unknown node");
            }

            node.fail();

            System.out.println("NODE FAILURE: " + nodeId);

            if (quorum != null) {
                quorum.invalidateLeader(nodeId);

                if (quorum.hasQuorum(nodes)) {
                    System.out.println(
                        "NEW LEADER: " + quorum.electLeader(nodes)
                    );
                } else {
                    System.out.println("CRITICAL: QUORUM LOST");
                }
            }

            for (ApplicationService service : services.values()) {
                if (service.replicas().contains(nodeId)) {
                    printAssessment(service.id());
                }
            }
        }

        void recoverNode(String nodeId) {
            InfrastructureNode node = nodes.get(nodeId);

            if (node == null) {
                throw new InfrastructureException("Unknown node");
            }

            node.recover();

            System.out.println("NODE RECOVERED: " + nodeId);

            if (quorum != null &&
                quorum.leader() == null &&
                quorum.hasQuorum(nodes)) {
                System.out.println(
                    "LEADER RESTORED: " + quorum.electLeader(nodes)
                );
            }
        }

        void failAvailabilityZone(String zone) {
            List<String> affected = nodes.values().stream()
                .filter(node -> node.zone().equals(zone))
                .filter(InfrastructureNode::isHealthy)
                .map(InfrastructureNode::id)
                .toList();

            if (affected.isEmpty()) {
                throw new InfrastructureException(
                    "No healthy nodes in failure zone"
                );
            }

            for (String id : affected) {
                failNode(id);
            }
        }

        List<FailureReport> analyzeFailureDomains() {
            List<FailureReport> reports = new ArrayList<>();

            for (ApplicationService service : services.values()) {
                Set<String> zones = new HashSet<>();

                for (String id : service.replicas()) {
                    zones.add(nodes.get(id).zone());
                }

                for (String zone : zones) {
                    long surviving = service.replicas().stream()
                        .map(nodes::get)
                        .filter(node -> !node.zone().equals(zone))
                        .filter(InfrastructureNode::isHealthy)
                        .count();

                    if (surviving <
                        service.policy().minimumHealthyReplicas()) {
                        reports.add(
                            new FailureReport(
                                service.id(),
                                zone,
                                FailureSeverity.CRITICAL,
                                "Zone failure violates minimum replica policy"
                            )
                        );
                    }
                }
            }

            return List.copyOf(reports);
        }

        void printAssessment(String serviceId) {
            ApplicationService service = services.get(serviceId);

            ServiceAssessment assessment =
                evaluator.evaluate(service, nodes);

            System.out.println(
                serviceId + " = " + assessment.status() +
                ", healthy=" + assessment.healthyReplicas() +
                ", minimum=" + assessment.requiredReplicas()
            );
        }

        void report() {
            System.out.println("\n========== ENTERPRISE HA REPORT ==========");

            for (String serviceId : services.keySet()) {
                printAssessment(serviceId);
            }

            if (quorum != null) {
                System.out.println(
                    "Control plane quorum: " + quorum.hasQuorum(nodes)
                );

                System.out.println("Leader: " + quorum.leader());
                System.out.println("Term: " + quorum.currentTerm());
            }

            double successRate = totalRequests == 0
                ? 100.0
                : 100.0 * successfulRequests / totalRequests;

            System.out.println("Total requests: " + totalRequests);
            System.out.println("Successful requests: " + successfulRequests);
            System.out.println("Failed requests: " + failedRequests);
            System.out.printf("Success ratio: %.2f%%%n", successRate);

            System.out.println("\nFailure-domain risks:");

            List<FailureReport> risks = analyzeFailureDomains();

            if (risks.isEmpty()) {
                System.out.println("No modeled critical service risks.");
            }

            for (FailureReport report : risks) {
                System.out.println(
                    report.resource() + " | " +
                    report.failureDomain() + " | " +
                    report.severity() + " | " +
                    report.description()
                );
            }
        }
    }

    public static void main(String[] args) {
        try {
            RepositoryGovernanceService platform =
                new RepositoryGovernanceService();

            List<NodeConfiguration> infrastructure = List.of(
                new NodeConfiguration("app-1", "application", "zone-a", 100),
                new NodeConfiguration("app-2", "application", "zone-b", 100),
                new NodeConfiguration("app-3", "application", "zone-c", 100),

                new NodeConfiguration("db-1", "database", "zone-a", 200),
                new NodeConfiguration("db-2", "database", "zone-b", 200),
                new NodeConfiguration("db-3", "database", "zone-c", 200),

                new NodeConfiguration("control-1", "control", "zone-a", 50),
                new NodeConfiguration("control-2", "control", "zone-b", 50),
                new NodeConfiguration("control-3", "control", "zone-c", 50)
            );

            infrastructure.forEach(platform::registerNode);

            platform.registerService(
                new ApplicationService(
                    "application",
                    List.of("app-1", "app-2", "app-3"),
                    new AvailabilityPolicy(2, true, false)
                )
            );

            platform.registerService(
                new ApplicationService(
                    "database",
                    List.of("db-1", "db-2", "db-3"),
                    new AvailabilityPolicy(2, true, false)
                )
            );

            platform.configureQuorum(
                new QuorumService(
                    List.of("control-1", "control-2", "control-3")
                )
            );

            System.out.println("NORMAL OPERATION");

            for (int i = 0; i < 5; i++) {
                InfrastructureNode node =
                    platform.handleRequest("application");

                if (node != null) {
                    System.out.println("Served by " + node.id());
                    platform.completeRequest(node);
                }
            }

            System.out.println("\nNODE FAILURE");

            platform.failNode("app-1");

            InfrastructureNode failover =
                platform.handleRequest("application");

            if (failover != null) {
                System.out.println(
                    "Failover served by " + failover.id()
                );
                platform.completeRequest(failover);
            }

            System.out.println("\nNODE RECOVERY");
            platform.recoverNode("app-1");

            System.out.println("\nAVAILABILITY ZONE FAILURE");
            platform.failAvailabilityZone("zone-a");

            platform.report();

        } catch (InfrastructureException |
                 IllegalArgumentException exception) {
            System.err.println(
                "Infrastructure operation failed: " +
                exception.getMessage()
            );

            System.exitCode = 1;
        }
    }
}
