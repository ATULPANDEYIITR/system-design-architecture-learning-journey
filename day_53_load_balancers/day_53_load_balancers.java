import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class LoadBalancerGovernance {

    enum BackendState {
        HEALTHY,
        UNHEALTHY
    }

    enum RoutingStrategy {
        ROUND_ROBIN,
        WEIGHTED_ROUND_ROBIN,
        LEAST_CONNECTIONS
    }

    enum FailureReason {
        HEALTH_CHECK_FAILURE,
        CAPACITY_EXHAUSTED,
        NO_HEALTHY_BACKEND
    }

    record HealthCheckResult(
        String backendId,
        boolean successful,
        String detail
    ) {}

    static final class Backend {
        private final String id;
        private final String host;
        private final int port;
        private final int weight;
        private final int maxConnections;

        private BackendState state = BackendState.HEALTHY;
        private boolean simulatedHealth = true;

        private int activeConnections;
        private int totalRequests;
        private int healthFailures;
        private int consecutiveFailures;
        private int consecutiveSuccesses;

        Backend(
            String id,
            String host,
            int port,
            int weight,
            int maxConnections
        ) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                    "backend ID is required"
                );
            }

            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException(
                    "port must be between 1 and 65535"
                );
            }

            if (weight <= 0 || maxConnections <= 0) {
                throw new IllegalArgumentException(
                    "weight and maxConnections must be positive"
                );
            }

            this.id = id;
            this.host = host;
            this.port = port;
            this.weight = weight;
            this.maxConnections = maxConnections;
        }

        String id() {
            return id;
        }

        int weight() {
            return weight;
        }

        int activeConnections() {
            return activeConnections;
        }

        int totalRequests() {
            return totalRequests;
        }

        int healthFailures() {
            return healthFailures;
        }

        BackendState state() {
            return state;
        }

        void setSimulatedHealth(boolean simulatedHealth) {
            this.simulatedHealth = simulatedHealth;
        }

        boolean canReceive() {
            return state == BackendState.HEALTHY
                && activeConnections < maxConnections;
        }

        void openConnection() {
            if (!canReceive()) {
                throw new IllegalStateException(
                    "backend cannot accept another connection"
                );
            }

            activeConnections++;
            totalRequests++;
        }

        void closeConnection() {
            if (activeConnections <= 0) {
                throw new IllegalStateException(
                    "backend has no active connection"
                );
            }

            activeConnections--;
        }

        HealthCheckResult check(
            int failureThreshold,
            int recoveryThreshold
        ) {
            if (simulatedHealth) {
                consecutiveFailures = 0;
                consecutiveSuccesses++;

                if (
                    state == BackendState.UNHEALTHY &&
                    consecutiveSuccesses >= recoveryThreshold
                ) {
                    state = BackendState.HEALTHY;
                    consecutiveFailures = 0;
                }

                return new HealthCheckResult(
                    id,
                    true,
                    "health probe succeeded"
                );
            }

            consecutiveSuccesses = 0;
            consecutiveFailures++;
            healthFailures++;

            if (consecutiveFailures >= failureThreshold) {
                state = BackendState.UNHEALTHY;
            }

            return new HealthCheckResult(
                id,
                false,
                "health probe failed"
            );
        }

        String endpoint() {
            return host + ":" + port;
        }
    }

    record BranchPolicy(
        int requiredHealthyChecks,
        int recoveryChecks,
        boolean directPushAllowed,
        boolean forcePushAllowed
    ) {
        BranchPolicy {
            if (requiredHealthyChecks <= 0 || recoveryChecks <= 0) {
                throw new IllegalArgumentException(
                    "health thresholds must be positive"
                );
            }
        }
    }

    static final class HealthService {
        private final BranchPolicy policy;

        HealthService(BranchPolicy policy) {
            this.policy = policy;
        }

        List<HealthCheckResult> checkAll(
            List<Backend> backends
        ) {
            List<HealthCheckResult> results = new ArrayList<>();

            for (Backend backend : backends) {
                results.add(
                    backend.check(
                        policy.requiredHealthyChecks(),
                        policy.recoveryChecks()
                    )
                );
            }

            return List.copyOf(results);
        }
    }

    static final class MergeEligibility {
        private final boolean eligible;
        private final List<String> reasons;

        private MergeEligibility(
            boolean eligible,
            List<String> reasons
        ) {
            this.eligible = eligible;
            this.reasons = List.copyOf(reasons);
        }

        static MergeEligibility evaluate(
            List<Backend> backends,
            int minimumHealthyBackends
        ) {
            List<String> reasons = new ArrayList<>();

            long healthyCount = backends.stream()
                .filter(backend -> backend.state() == BackendState.HEALTHY)
                .count();

            if (healthyCount < minimumHealthyBackends) {
                reasons.add(
                    "insufficient healthy service capacity"
                );
            }

            boolean allCapacityAvailable = backends.stream()
                .anyMatch(Backend::canReceive);

            if (!allCapacityAvailable) {
                reasons.add(
                    "no backend has routing capacity"
                );
            }

            return new MergeEligibility(
                reasons.isEmpty(),
                reasons
            );
        }

        boolean eligible() {
            return eligible;
        }

        List<String> reasons() {
            return reasons;
        }
    }

    static final class LoadBalancer {
        private final List<Backend> backends;
        private final RoutingStrategy strategy;
        private int roundRobinIndex;
        private long requestSequence;

        LoadBalancer(
            List<Backend> backends,
            RoutingStrategy strategy
        ) {
            if (backends == null || backends.isEmpty()) {
                throw new IllegalArgumentException(
                    "at least one backend is required"
                );
            }

            Set<String> ids = new HashSet<>();
            for (Backend backend : backends) {
                if (!ids.add(backend.id())) {
                    throw new IllegalArgumentException(
                        "duplicate backend ID: " + backend.id()
                    );
                }
            }

            this.backends = new ArrayList<>(backends);
            this.strategy = strategy;
        }

        Backend route(String requestId) {
            if (requestId == null || requestId.isBlank()) {
                throw new IllegalArgumentException(
                    "request ID cannot be empty"
                );
            }

            Backend selected = selectBackend();

            if (selected == null) {
                throw new IllegalStateException(
                    FailureReason.NO_HEALTHY_BACKEND.name()
                );
            }

            selected.openConnection();

            System.out.printf(
                "route %-16s -> %s%n",
                requestId,
                selected.id()
            );

            requestSequence++;
            return selected;
        }

        void complete(Backend backend) {
            backend.closeConnection();
        }

        private Backend selectBackend() {
            List<Backend> candidates = backends.stream()
                .filter(Backend::canReceive)
                .toList();

            if (candidates.isEmpty()) {
                return null;
            }

            if (strategy == RoutingStrategy.LEAST_CONNECTIONS) {
                return candidates.stream()
                    .min(
                        Comparator
                            .comparingInt(Backend::activeConnections)
                            .thenComparing(
                                Comparator.comparingInt(
                                    Backend::weight
                                ).reversed()
                            )
                            .thenComparing(Backend::id)
                    )
                    .orElse(null);
            }

            if (strategy == RoutingStrategy.WEIGHTED_ROUND_ROBIN) {
                List<Backend> weighted = new ArrayList<>();

                for (Backend backend : candidates) {
                    for (int i = 0; i < backend.weight(); i++) {
                        weighted.add(backend);
                    }
                }

                return weighted.get(
                    (int) (requestSequence % weighted.size())
                );
            }

            Set<String> candidateIds = candidates.stream()
                .map(Backend::id)
                .collect(java.util.stream.Collectors.toSet());

            for (int offset = 0; offset < backends.size(); offset++) {
                int index =
                    (roundRobinIndex + offset) % backends.size();

                Backend candidate = backends.get(index);

                if (candidateIds.contains(candidate.id())) {
                    roundRobinIndex =
                        (index + 1) % backends.size();

                    return candidate;
                }
            }

            return null;
        }

        void printState(String title) {
            System.out.println("\n" + title);

            for (Backend backend : backends) {
                System.out.printf(
                    "%-10s endpoint=%-18s state=%-9s " +
                    "connections=%d requests=%d healthFailures=%d%n",
                    backend.id(),
                    backend.endpoint(),
                    backend.state(),
                    backend.activeConnections(),
                    backend.totalRequests(),
                    backend.healthFailures()
                );
            }
        }

        List<Backend> backends() {
            return List.copyOf(backends);
        }
    }

    public static void main(String[] args) {
        BranchPolicy servicePolicy = new BranchPolicy(
            2,
            2,
            false,
            false
        );

        HealthService healthService =
            new HealthService(servicePolicy);

        List<Backend> backends = List.of(
            new Backend(
                "service-a",
                "10.50.0.11",
                8080,
                1,
                4
            ),
            new Backend(
                "service-b",
                "10.50.0.12",
                8080,
                2,
                4
            ),
            new Backend(
                "service-c",
                "10.50.0.13",
                8080,
                1,
                4
            )
        );

        LoadBalancer loadBalancer =
            new LoadBalancer(
                backends,
                RoutingStrategy.LEAST_CONNECTIONS
            );

        System.out.println("Initial service health");

        for (HealthCheckResult result :
            healthService.checkAll(backends)) {
            System.out.printf(
                "%s -> %s (%s)%n",
                result.backendId(),
                result.successful() ? "PASS" : "FAIL",
                result.detail()
            );
        }

        List<Backend> heldConnections = new ArrayList<>();

        for (int i = 1; i <= 6; i++) {
            Backend backend =
                loadBalancer.route("request-" + i);

            if (i % 2 == 0) {
                loadBalancer.complete(backend);
            } else {
                heldConnections.add(backend);
            }
        }

        loadBalancer.printState(
            "Least-connections service distribution"
        );

        Backend failing = backends.get(1);
        failing.setSimulatedHealth(false);

        System.out.println("\nService-b health failure");

        healthService.checkAll(backends);
        healthService.checkAll(backends);

        loadBalancer.printState(
            "Service pool after health isolation"
        );

        for (int i = 7; i <= 10; i++) {
            Backend backend =
                loadBalancer.route("failover-" + i);

            loadBalancer.complete(backend);
        }

        failing.setSimulatedHealth(true);

        System.out.println("\nService-b recovery");

        healthService.checkAll(backends);
        healthService.checkAll(backends);

        loadBalancer.printState(
            "Recovered service pool"
        );

        for (Backend backend : heldConnections) {
            if (backend.activeConnections() > 0) {
                loadBalancer.complete(backend);
            }
        }

        MergeEligibility eligibility =
            MergeEligibility.evaluate(
                loadBalancer.backends(),
                2
            );

        System.out.println(
            "\nCapacity policy eligibility: " +
            eligibility.eligible()
        );

        if (!eligibility.eligible()) {
            eligibility.reasons()
                .forEach(reason ->
                    System.out.println("blocked: " + reason)
                );
        }

        System.out.println(
            "\nPolicy flags: " +
            EnumSet.of(
                FailureReason.HEALTH_CHECK_FAILURE,
                FailureReason.CAPACITY_EXHAUSTED
            )
        );
    }
}
