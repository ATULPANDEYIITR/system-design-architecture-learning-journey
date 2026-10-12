import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

public class CAPGovernanceSystem {

    enum CAPMode {
        CP,
        AP
    }

    enum NodeStatus {
        ONLINE,
        OFFLINE
    }

    record VersionedValue(long version, String value) {}

    record WriteDecision(
            boolean committed,
            List<String> acknowledgedNodes,
            String reason) {}

    static final class RepositoryPolicy {
        private final String repository;
        private final String branch;
        private final int requiredApprovals;
        private final Set<String> requiredChecks;
        private final boolean directPushAllowed;

        RepositoryPolicy(
                String repository,
                String branch,
                int requiredApprovals,
                Set<String> requiredChecks,
                boolean directPushAllowed) {

            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                        "Approval requirement cannot be negative."
                );
            }

            if (repository.isBlank() || branch.isBlank()) {
                throw new IllegalArgumentException(
                        "Repository and branch are required."
                );
            }

            this.repository = repository;
            this.branch = branch;
            this.requiredApprovals = requiredApprovals;
            this.requiredChecks = Set.copyOf(requiredChecks);
            this.directPushAllowed = directPushAllowed;
        }

        String key() {
            return repository + ":" + branch;
        }

        @Override
        public String toString() {
            return "RepositoryPolicy{" +
                    "repository='" + repository + '\'' +
                    ", branch='" + branch + '\'' +
                    ", requiredApprovals=" + requiredApprovals +
                    ", requiredChecks=" + requiredChecks +
                    ", directPushAllowed=" + directPushAllowed +
                    '}';
        }
    }

    static final class GovernanceNode {
        private final String id;
        private final String region;
        private NodeStatus status = NodeStatus.ONLINE;
        private long logicalClock = 0;
        private final Map<String, VersionedValue> policies = new HashMap<>();

        GovernanceNode(String id, String region) {
            this.id = id;
            this.region = region;
        }

        void write(String key, String value) {
            logicalClock++;
            policies.put(key, new VersionedValue(logicalClock, value));
        }

        Optional<VersionedValue> read(String key) {
            return Optional.ofNullable(policies.get(key));
        }

        String id() {
            return id;
        }

        String region() {
            return region;
        }

        NodeStatus status() {
            return status;
        }

        void setStatus(NodeStatus status) {
            this.status = status;
        }
    }

    static final class NetworkPartition {
        private final List<Set<String>> groups = new ArrayList<>();

        void heal(Set<String> nodeIds) {
            groups.clear();
            groups.add(new HashSet<>(nodeIds));
        }

        void split(Set<String> first, Set<String> second) {
            groups.clear();
            groups.add(new HashSet<>(first));
            groups.add(new HashSet<>(second));
        }

        boolean canCommunicate(String first, String second) {
            return groups.stream()
                    .anyMatch(group ->
                            group.contains(first) &&
                            group.contains(second));
        }
    }

    static final class GovernanceService {
        private final Map<String, GovernanceNode> nodes = new HashMap<>();
        private final NetworkPartition network = new NetworkPartition();
        private final CAPMode mode;

        GovernanceService(CAPMode mode) {
            this.mode = mode;

            addNode(new GovernanceNode("governance-a", "Delhi"));
            addNode(new GovernanceNode("governance-b", "Mumbai"));
            addNode(new GovernanceNode("governance-c", "Bengaluru"));

            network.heal(nodes.keySet());
        }

        private void addNode(GovernanceNode node) {
            nodes.put(node.id(), node);
        }

        private List<GovernanceNode> reachable(String coordinator) {
            if (!nodes.containsKey(coordinator)) {
                throw new IllegalArgumentException(
                        "Unknown coordinator: " + coordinator
                );
            }

            return nodes.values()
                    .stream()
                    .filter(node ->
                            node.status() == NodeStatus.ONLINE &&
                            network.canCommunicate(
                                    coordinator,
                                    node.id()))
                    .toList();
        }

        WriteDecision updatePolicy(
                String coordinator,
                RepositoryPolicy policy) {

            List<GovernanceNode> reachable =
                    reachable(coordinator);

            int quorum = nodes.size() / 2 + 1;

            if (mode == CAPMode.CP &&
                    reachable.size() < quorum) {

                return new WriteDecision(
                        false,
                        List.of(),
                        "CP policy update rejected because " +
                                "a majority cannot be reached."
                );
            }

            List<String> acknowledged = new ArrayList<>();

            for (GovernanceNode node : reachable) {
                node.write(
                        policy.key(),
                        policy.toString()
                );
                acknowledged.add(node.id());
            }

            String reason = mode == CAPMode.CP
                    ? "Policy committed after majority agreement."
                    : "Policy accepted by reachable nodes; " +
                      "divergence may require reconciliation.";

            return new WriteDecision(
                    true,
                    List.copyOf(acknowledged),
                    reason
            );
        }

        Optional<VersionedValue> readPolicy(
                String coordinator,
                String policyKey) {

            List<GovernanceNode> reachable =
                    reachable(coordinator);

            return reachable.stream()
                    .map(node -> node.read(policyKey))
                    .filter(Optional::isPresent)
                    .map(Optional::get)
                    .max((first, second) ->
                            Long.compare(
                                    first.version(),
                                    second.version()));
        }

        Optional<String> reconcile(String policyKey) {
            Optional<VersionedValue> winner =
                    nodes.values()
                            .stream()
                            .map(node -> node.read(policyKey))
                            .filter(Optional::isPresent)
                            .map(Optional::get)
                            .max((first, second) ->
                                    Long.compare(
                                            first.version(),
                                            second.version()));

            if (winner.isEmpty()) {
                return Optional.empty();
            }

            for (GovernanceNode node : nodes.values()) {
                node.policies.put(policyKey, winner.get());
            }

            return Optional.of(winner.get().value());
        }

        void partition(
                Set<String> first,
                Set<String> second) {

            Set<String> combined = new HashSet<>(first);
            combined.addAll(second);

            if (!combined.equals(nodes.keySet())) {
                throw new IllegalArgumentException(
                        "Partition must account for every node."
                );
            }

            network.split(first, second);
        }

        void heal() {
            network.heal(nodes.keySet());
        }

        void printPolicyState(String key) {
            nodes.values()
                    .forEach(node ->
                            System.out.println(
                                    node.id() +
                                    " [" + node.region() + "] -> " +
                                    node.read(key).orElse(null)
                            ));
        }
    }

    private static void demonstrateCP() {
        System.out.println("\n=== CP ENTERPRISE POLICY SERVICE ===");

        GovernanceService service =
                new GovernanceService(CAPMode.CP);

        RepositoryPolicy initialPolicy =
                new RepositoryPolicy(
                        "payments-api",
                        "main",
                        2,
                        Set.of("ci", "security"),
                        false
                );

        System.out.println(
                service.updatePolicy(
                        "governance-a",
                        initialPolicy)
        );

        service.partition(
                Set.of("governance-a"),
                Set.of("governance-b", "governance-c")
        );

        RepositoryPolicy stricterPolicy =
                new RepositoryPolicy(
                        "payments-api",
                        "main",
                        3,
                        Set.of("ci", "security", "license"),
                        false
                );

        System.out.println(
                service.updatePolicy(
                        "governance-a",
                        stricterPolicy)
        );

        /*
         * The service refuses to create a potentially authoritative policy
         * state from an isolated node. This makes availability subordinate
         * to the consistency rule while a partition exists.
         */
    }

    private static void demonstrateAP() {
        System.out.println("\n=== AP ENTERPRISE POLICY SERVICE ===");

        GovernanceService service =
                new GovernanceService(CAPMode.AP);

        RepositoryPolicy baseline =
                new RepositoryPolicy(
                        "inventory-service",
                        "main",
                        1,
                        Set.of("ci"),
                        false
                );

        service.updatePolicy(
                "governance-a",
                baseline
        );

        service.partition(
                Set.of("governance-a"),
                Set.of("governance-b", "governance-c")
        );

        RepositoryPolicy policyA =
                new RepositoryPolicy(
                        "inventory-service",
                        "main",
                        1,
                        Set.of("ci"),
                        false
                );

        RepositoryPolicy policyB =
                new RepositoryPolicy(
                        "inventory-service",
                        "main",
                        2,
                        Set.of("ci", "security"),
                        false
                );

        System.out.println(
                service.updatePolicy(
                        "governance-a",
                        policyA)
        );

        System.out.println(
                service.updatePolicy(
                        "governance-b",
                        policyB)
        );

        String key = baseline.key();

        System.out.println("\nState before healing:");
        service.printPolicyState(key);

        service.heal();

        System.out.println(
                "\nReconciled state: " +
                service.reconcile(key).orElse("NO POLICY")
        );

        System.out.println("\nState after healing:");
        service.printPolicyState(key);
    }

    private static void explainCAPBoundary() {
        System.out.println("\n=== CAP BOUNDARY ===");
        System.out.println(
                "Consistency requires a coherent authoritative state."
        );
        System.out.println(
                "Availability requires a reachable node to continue responding."
        );
        System.out.println(
                "Partition tolerance requires operation despite broken "
                        + "communication between replicas."
        );
        System.out.println(
                "The trade-off becomes visible when the network is partitioned."
        );
    }

    public static void main(String[] args) {
        explainCAPBoundary();
        demonstrateCP();
        demonstrateAP();

        System.out.println(
                "\nEnterprise governance simulation completed."
        );
    }
}
