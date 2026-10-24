import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class LoadBalancingAlgorithms {

    enum Algorithm {
        ROUND_ROBIN,
        WEIGHTED_ROUND_ROBIN,
        LEAST_CONNECTIONS
    }

    enum BackendState {
        HEALTHY,
        UNHEALTHY
    }

    record BackendSnapshot(
            String name,
            int weight,
            BackendState state,
            int activeConnections,
            int totalRequests,
            int completedRequests,
            int failedRequests) {
    }

    static final class Backend {
        private final String name;
        private final int weight;
        private BackendState state = BackendState.HEALTHY;
        private int activeConnections;
        private int totalRequests;
        private int completedRequests;
        private int failedRequests;

        Backend(String name, int weight) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Backend name is required");
            }
            if (weight <= 0) {
                throw new IllegalArgumentException(
                        "Backend weight must be positive");
            }

            this.name = name;
            this.weight = weight;
        }

        String name() {
            return name;
        }

        int weight() {
            return weight;
        }

        BackendState state() {
            return state;
        }

        int activeConnections() {
            return activeConnections;
        }

        void setState(BackendState newState) {
            this.state = Objects.requireNonNull(newState);
        }

        void startRequest() {
            if (state != BackendState.HEALTHY) {
                throw new IllegalStateException(
                        "Cannot dispatch to unhealthy backend: " + name);
            }

            activeConnections++;
            totalRequests++;
        }

        void finishRequest(boolean success) {
            if (activeConnections <= 0) {
                throw new IllegalStateException(
                        "No active request exists on " + name);
            }

            activeConnections--;

            if (success) {
                completedRequests++;
            } else {
                failedRequests++;
            }
        }

        BackendSnapshot snapshot() {
            return new BackendSnapshot(
                    name,
                    weight,
                    state,
                    activeConnections,
                    totalRequests,
                    completedRequests,
                    failedRequests);
        }
    }

    interface SelectionPolicy {
        Backend select(List<Backend> healthyBackends);
    }

    static final class RoundRobinPolicy implements SelectionPolicy {
        private int index;

        @Override
        public Backend select(List<Backend> healthyBackends) {
            if (healthyBackends.isEmpty()) {
                throw new IllegalStateException(
                        "No healthy backend is available");
            }

            Backend selected =
                    healthyBackends.get(index % healthyBackends.size());
            index++;
            return selected;
        }
    }

    static final class WeightedRoundRobinPolicy
            implements SelectionPolicy {

        private List<Backend> schedule = List.of();
        private int index;

        void rebuild(List<Backend> backends) {
            List<Backend> next = new ArrayList<>();

            for (Backend backend : backends) {
                for (int i = 0; i < backend.weight(); i++) {
                    next.add(backend);
                }
            }

            schedule = List.copyOf(next);
            index = 0;
        }

        @Override
        public Backend select(List<Backend> healthyBackends) {
            if (healthyBackends.isEmpty()) {
                throw new IllegalStateException(
                        "No healthy backend is available");
            }

            Set<String> healthyNames = new HashSet<>();
            for (Backend backend : healthyBackends) {
                healthyNames.add(backend.name());
            }

            for (int attempts = 0; attempts < schedule.size(); attempts++) {
                Backend candidate = schedule.get(index % schedule.size());
                index++;

                if (healthyNames.contains(candidate.name())) {
                    return candidate;
                }
            }

            throw new IllegalStateException(
                    "Weighted schedule contains no healthy backend");
        }
    }

    static final class LeastConnectionsPolicy
            implements SelectionPolicy {

        @Override
        public Backend select(List<Backend> healthyBackends) {
            if (healthyBackends.isEmpty()) {
                throw new IllegalStateException(
                        "No healthy backend is available");
            }

            return healthyBackends.stream()
                    .min(Comparator
                            .comparingInt(Backend::activeConnections)
                            .thenComparing(
                                    Comparator.comparingInt(
                                            Backend::weight).reversed())
                            .thenComparing(Backend::name))
                    .orElseThrow();
        }
    }

    static final class LoadBalancer {
        private final List<Backend> backends;
        private final Algorithm algorithm;
        private final Map<Algorithm, SelectionPolicy> policies =
                new EnumMap<>(Algorithm.class);

        LoadBalancer(List<Backend> backends, Algorithm algorithm) {
            if (backends == null || backends.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one backend is required");
            }

            Set<String> names = new HashSet<>();
            for (Backend backend : backends) {
                if (!names.add(backend.name())) {
                    throw new IllegalArgumentException(
                            "Backend names must be unique");
                }
            }

            this.backends = new ArrayList<>(backends);
            this.algorithm = Objects.requireNonNull(algorithm);

            policies.put(
                    Algorithm.ROUND_ROBIN,
                    new RoundRobinPolicy());

            WeightedRoundRobinPolicy weighted =
                    new WeightedRoundRobinPolicy();
            weighted.rebuild(this.backends);

            policies.put(
                    Algorithm.WEIGHTED_ROUND_ROBIN,
                    weighted);

            policies.put(
                    Algorithm.LEAST_CONNECTIONS,
                    new LeastConnectionsPolicy());
        }

        Backend dispatch(int requestId) {
            if (requestId <= 0) {
                throw new IllegalArgumentException(
                        "Request ID must be positive");
            }

            List<Backend> healthy = backends.stream()
                    .filter(b -> b.state() == BackendState.HEALTHY)
                    .toList();

            Backend selected = policies.get(algorithm).select(healthy);
            selected.startRequest();
            return selected;
        }

        void complete(String backendName, boolean success) {
            find(backendName).finishRequest(success);
        }

        void setHealth(String backendName, boolean healthy) {
            Backend backend = find(backendName);
            backend.setState(
                    healthy
                            ? BackendState.HEALTHY
                            : BackendState.UNHEALTHY);

            SelectionPolicy policy =
                    policies.get(Algorithm.WEIGHTED_ROUND_ROBIN);

            ((WeightedRoundRobinPolicy) policy).rebuild(backends);
        }

        Backend find(String backendName) {
            return backends.stream()
                    .filter(b -> b.name().equals(backendName))
                    .findFirst()
                    .orElseThrow(() -> new IllegalArgumentException(
                            "Unknown backend: " + backendName));
        }

        List<BackendSnapshot> snapshots() {
            return backends.stream()
                    .map(Backend::snapshot)
                    .toList();
        }
    }

    static Map<String, Integer> simulate(
            Algorithm algorithm,
            int[] weights,
            int requests) {

        List<Backend> backends = List.of(
                new Backend("server-a", weights[0]),
                new Backend("server-b", weights[1]),
                new Backend("server-c", weights[2]));

        LoadBalancer balancer = new LoadBalancer(backends, algorithm);

        for (int requestId = 1; requestId <= requests; requestId++) {
            Backend backend = balancer.dispatch(requestId);
            balancer.complete(backend.name(), true);
        }

        Map<String, Integer> result = new HashMap<>();

        for (BackendSnapshot snapshot : balancer.snapshots()) {
            result.put(snapshot.name(), snapshot.totalRequests());
        }

        return result;
    }

    static void runLeastConnectionsScenario() {
        LoadBalancer balancer = new LoadBalancer(
                List.of(
                        new Backend("api-a", 1),
                        new Backend("api-b", 2),
                        new Backend("api-c", 3)),
                Algorithm.LEAST_CONNECTIONS);

        List<String> active = new ArrayList<>();

        for (int requestId = 1; requestId <= 9; requestId++) {
            Backend backend = balancer.dispatch(requestId);
            active.add(backend.name());

            if (requestId % 3 == 0) {
                balancer.complete(active.remove(0), true);
            }
        }

        System.out.println("\nLeast-connections state:");
        printSnapshots(balancer.snapshots());
    }

    static void runFailureScenario() {
        LoadBalancer balancer = new LoadBalancer(
                List.of(
                        new Backend("primary", 3),
                        new Backend("backup", 1)),
                Algorithm.WEIGHTED_ROUND_ROBIN);

        for (int requestId = 1; requestId <= 8; requestId++) {
            Backend backend = balancer.dispatch(requestId);
            balancer.complete(backend.name(), true);
        }

        balancer.setHealth("primary", false);

        for (int requestId = 9; requestId <= 12; requestId++) {
            Backend backend = balancer.dispatch(requestId);
            balancer.complete(backend.name(), true);
        }

        System.out.println("\nAfter primary failure:");
        printSnapshots(balancer.snapshots());
    }

    static void runAsyncScenario() {
        LoadBalancer balancer = new LoadBalancer(
                List.of(
                        new Backend("async-a", 1),
                        new Backend("async-b", 2),
                        new Backend("async-c", 3)),
                Algorithm.LEAST_CONNECTIONS);

        List<CompletableFuture<Void>> futures = new ArrayList<>();

        for (int requestId = 1; requestId <= 12; requestId++) {
            Backend backend = balancer.dispatch(requestId);
            long delay = 20L + ((requestId * 17L) % 50L);

            CompletableFuture<Void> future =
                    CompletableFuture.runAsync(
                            () -> {
                                try {
                                    TimeUnit.MILLISECONDS.sleep(delay);
                                    balancer.complete(
                                            backend.name(), true);
                                } catch (InterruptedException error) {
                                    Thread.currentThread().interrupt();
                                    balancer.complete(
                                            backend.name(), false);
                                }
                            });

            futures.add(future);
        }

        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture[0])).join();

        System.out.println("\nAsynchronous least-connections state:");
        printSnapshots(balancer.snapshots());
    }

    static void printSnapshots(List<BackendSnapshot> snapshots) {
        for (BackendSnapshot snapshot : snapshots) {
            System.out.printf(
                    "%s weight=%d state=%s active=%d total=%d completed=%d failed=%d%n",
                    snapshot.name(),
                    snapshot.weight(),
                    snapshot.state(),
                    snapshot.activeConnections(),
                    snapshot.totalRequests(),
                    snapshot.completedRequests(),
                    snapshot.failedRequests());
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> roundRobin =
                simulate(
                        Algorithm.ROUND_ROBIN,
                        new int[]{1, 1, 1},
                        60);

        Map<String, Integer> weighted =
                simulate(
                        Algorithm.WEIGHTED_ROUND_ROBIN,
                        new int[]{1, 2, 3},
                        60);

        if (roundRobin.get("server-a") != 20
                || roundRobin.get("server-b") != 20
                || roundRobin.get("server-c") != 20) {
            throw new AssertionError(
                    "Round-robin distribution is incorrect");
        }

        if (weighted.get("server-a") != 10
                || weighted.get("server-b") != 20
                || weighted.get("server-c") != 30) {
            throw new AssertionError(
                    "Weighted distribution is incorrect");
        }

        System.out.println("Round-robin: " + roundRobin);
        System.out.println("Weighted round-robin: " + weighted);

        runLeastConnectionsScenario();
        runFailureScenario();
        runAsyncScenario();
    }
}
