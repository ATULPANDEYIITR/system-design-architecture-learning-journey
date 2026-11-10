import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicLong;

/*
 * Circuit Breaker Enterprise Failure Management
 *
 * Java 17
 *
 * Components:
 * - Explicit circuit states
 * - Validated immutable configuration
 * - Thread-safe state management
 * - Half-open probe admission
 * - Failure isolation
 * - Fallback policies
 * - Dependency registry
 * - Service-specific degradation
 * - Operational metrics
 * - State transition auditing
 * - Automated validation
 */

public class CircuitBreakerEnterprise {

    enum CircuitState {
        CLOSED,
        OPEN,
        HALF_OPEN
    }

    enum ServiceStatus {
        SUCCESS,
        DEGRADED,
        PENDING,
        UNAVAILABLE
    }

    enum FailureCategory {
        NETWORK,
        TIMEOUT,
        DEPENDENCY,
        INTERNAL
    }

    record CircuitConfig(
        int failureThreshold,
        Duration recoveryTimeout,
        int halfOpenMaxCalls,
        int historyLimit
    ) {
        CircuitConfig {
            if (failureThreshold < 1) {
                throw new IllegalArgumentException(
                    "Failure threshold must be positive."
                );
            }

            Objects.requireNonNull(recoveryTimeout);

            if (
                recoveryTimeout.isZero() ||
                recoveryTimeout.isNegative()
            ) {
                throw new IllegalArgumentException(
                    "Recovery timeout must be positive."
                );
            }

            if (halfOpenMaxCalls < 1 || historyLimit < 1) {
                throw new IllegalArgumentException(
                    "Probe limit and history size must be positive."
                );
            }
        }
    }

    record CircuitEvent(
        Instant timestamp,
        String event,
        CircuitState state,
        String details
    ) {}

    record ServiceResponse(
        ServiceStatus status,
        String message,
        String source
    ) {}

    record DependencyHealth(
        String dependency,
        CircuitState state,
        long successes,
        long failures,
        long rejected
    ) {}

    static class CircuitOpenException extends RuntimeException {
        CircuitOpenException(String dependency) {
            super("Circuit is OPEN: " + dependency);
        }
    }

    static class DependencyException extends RuntimeException {
        private final FailureCategory category;

        DependencyException(
            String message,
            FailureCategory category
        ) {
            super(message);
            this.category = category;
        }

        FailureCategory getCategory() {
            return category;
        }
    }

    interface FallbackPolicy<T> {
        T recover(Exception cause);
    }

    static final class CircuitMetrics {
        private final AtomicLong totalCalls = new AtomicLong();
        private final AtomicLong successes = new AtomicLong();
        private final AtomicLong failures = new AtomicLong();
        private final AtomicLong rejected = new AtomicLong();
        private final AtomicLong fallbacks = new AtomicLong();
        private final AtomicLong transitions = new AtomicLong();

        Map<String, Long> snapshot() {
            Map<String, Long> values = new HashMap<>();

            values.put("totalCalls", totalCalls.get());
            values.put("successes", successes.get());
            values.put("failures", failures.get());
            values.put("rejected", rejected.get());
            values.put("fallbacks", fallbacks.get());
            values.put("transitions", transitions.get());

            return Collections.unmodifiableMap(values);
        }
    }

    static final class CircuitBreaker {

        private final String dependencyName;
        private final CircuitConfig config;

        private CircuitState state = CircuitState.CLOSED;

        private int consecutiveFailures;
        private int halfOpenInflight;

        private long openedAtNanos;

        private final CircuitMetrics metrics = new CircuitMetrics();

        private final Deque<CircuitEvent> history =
            new ArrayDeque<>();

        CircuitBreaker(
            String dependencyName,
            CircuitConfig config
        ) {
            if (
                dependencyName == null ||
                dependencyName.isBlank()
            ) {
                throw new IllegalArgumentException(
                    "Dependency name cannot be empty."
                );
            }

            this.dependencyName = dependencyName;
            this.config = Objects.requireNonNull(config);

            record("INITIALIZED", "Circuit created.");
        }

        private void record(String event, String details) {
            history.addLast(
                new CircuitEvent(
                    Instant.now(),
                    event,
                    state,
                    details
                )
            );

            while (history.size() > config.historyLimit()) {
                history.removeFirst();
            }
        }

        private void transition(
            CircuitState next,
            String reason
        ) {
            if (state == next) {
                return;
            }

            CircuitState previous = state;

            state = next;

            metrics.transitions.incrementAndGet();

            record(
                "STATE_TRANSITION",
                previous + " -> " + next + ": " + reason
            );
        }

        private void refreshState() {
            if (state != CircuitState.OPEN) {
                return;
            }

            long elapsed =
                System.nanoTime() - openedAtNanos;

            if (
                elapsed >=
                config.recoveryTimeout().toNanos()
            ) {
                halfOpenInflight = 0;

                transition(
                    CircuitState.HALF_OPEN,
                    "Recovery timeout elapsed."
                );
            }
        }

        private void open(String reason) {
            openedAtNanos = System.nanoTime();
            halfOpenInflight = 0;

            transition(CircuitState.OPEN, reason);
        }

        private synchronized CircuitState acquirePermission() {
            refreshState();

            if (state == CircuitState.OPEN) {
                metrics.rejected.incrementAndGet();

                record(
                    "CALL_REJECTED",
                    "Dependency request rejected."
                );

                throw new CircuitOpenException(dependencyName);
            }

            CircuitState admittedState = state;

            if (state == CircuitState.HALF_OPEN) {
                if (
                    halfOpenInflight >=
                    config.halfOpenMaxCalls()
                ) {
                    metrics.rejected.incrementAndGet();

                    throw new CircuitOpenException(
                        dependencyName
                    );
                }

                halfOpenInflight++;
            }

            metrics.totalCalls.incrementAndGet();

            return admittedState;
        }

        private synchronized void onSuccess(
            CircuitState admittedState
        ) {
            metrics.successes.incrementAndGet();

            if (admittedState == CircuitState.HALF_OPEN) {
                halfOpenInflight--;
                consecutiveFailures = 0;

                transition(
                    CircuitState.CLOSED,
                    "Recovery probe succeeded."
                );
            } else if (state == CircuitState.CLOSED) {
                consecutiveFailures = 0;
            }

            record(
                "CALL_SUCCESS",
                "Dependency operation succeeded."
            );
        }

        private synchronized void onFailure(
            CircuitState admittedState,
            Exception error
        ) {
            metrics.failures.incrementAndGet();

            if (admittedState == CircuitState.HALF_OPEN) {
                halfOpenInflight--;

                open("Recovery probe failed.");

            } else if (
                admittedState == CircuitState.CLOSED &&
                state == CircuitState.CLOSED
            ) {
                consecutiveFailures++;

                if (
                    consecutiveFailures >=
                    config.failureThreshold()
                ) {
                    open("Failure threshold reached.");
                }
            }

            record(
                "CALL_FAILURE",
                error.getClass().getSimpleName() +
                ": " + error.getMessage()
            );
        }

        public <T> T execute(
            Callable<T> operation,
            FallbackPolicy<T> fallback
        ) throws Exception {

            Objects.requireNonNull(operation);

            CircuitState admittedState;

            try {
                admittedState = acquirePermission();
            } catch (CircuitOpenException error) {
                if (fallback == null) {
                    throw error;
                }

                metrics.fallbacks.incrementAndGet();

                return fallback.recover(error);
            }

            try {
                T result = operation.call();

                onSuccess(admittedState);

                return result;

            } catch (Exception error) {
                onFailure(admittedState, error);

                if (fallback == null) {
                    throw error;
                }

                metrics.fallbacks.incrementAndGet();

                return fallback.recover(error);
            }
        }

        public synchronized CircuitState getState() {
            refreshState();
            return state;
        }

        public synchronized int getConsecutiveFailures() {
            return consecutiveFailures;
        }

        public Map<String, Long> getMetrics() {
            return metrics.snapshot();
        }

        public synchronized List<CircuitEvent> getHistory() {
            return List.copyOf(history);
        }

        public String getDependencyName() {
            return dependencyName;
        }
    }

    static final class DependencyRegistry {

        private final Map<String, CircuitBreaker> breakers =
            new HashMap<>();

        public synchronized CircuitBreaker register(
            String name,
            CircuitConfig config
        ) {
            if (breakers.containsKey(name)) {
                throw new IllegalArgumentException(
                    "Dependency already registered: " + name
                );
            }

            CircuitBreaker breaker =
                new CircuitBreaker(name, config);

            breakers.put(name, breaker);

            return breaker;
        }

        public synchronized CircuitBreaker get(String name) {
            CircuitBreaker breaker = breakers.get(name);

            if (breaker == null) {
                throw new IllegalArgumentException(
                    "Unknown dependency: " + name
                );
            }

            return breaker;
        }

        public synchronized List<DependencyHealth> healthReport() {
            List<DependencyHealth> report = new ArrayList<>();

            for (CircuitBreaker breaker : breakers.values()) {
                Map<String, Long> metrics = breaker.getMetrics();

                report.add(
                    new DependencyHealth(
                        breaker.getDependencyName(),
                        breaker.getState(),
                        metrics.get("successes"),
                        metrics.get("failures"),
                        metrics.get("rejected")
                    )
                );
            }

            return List.copyOf(report);
        }
    }

    static final class PaymentService {

        private final CircuitBreaker breaker;

        private boolean providerAvailable = true;

        PaymentService(DependencyRegistry registry) {
            breaker = registry.register(
                "payment-provider",
                new CircuitConfig(
                    3,
                    Duration.ofMillis(200),
                    1,
                    100
                )
            );
        }

        public void setProviderAvailable(boolean available) {
            providerAvailable = available;
        }

        public ServiceResponse processPayment(double amount)
            throws Exception {

            if (!Double.isFinite(amount) || amount <= 0) {
                throw new IllegalArgumentException(
                    "Payment amount must be positive and finite."
                );
            }

            return breaker.execute(
                () -> {
                    if (!providerAvailable) {
                        throw new DependencyException(
                            "Payment provider unavailable.",
                            FailureCategory.NETWORK
                        );
                    }

                    return new ServiceResponse(
                        ServiceStatus.SUCCESS,
                        "Payment completed.",
                        "REMOTE"
                    );
                },
                error -> new ServiceResponse(
                    ServiceStatus.PENDING,
                    "Payment stored for reconciliation.",
                    "LOCAL_QUEUE"
                )
            );
        }
    }

    static final class RecommendationService {

        private final CircuitBreaker breaker;

        private final List<String> cachedRecommendations =
            List.of(
                "Popular products",
                "Recently viewed products",
                "Frequently purchased products"
            );

        private boolean available = true;

        RecommendationService(DependencyRegistry registry) {
            breaker = registry.register(
                "recommendation-engine",
                new CircuitConfig(
                    2,
                    Duration.ofMillis(300),
                    1,
                    100
                )
            );
        }

        public void setAvailable(boolean available) {
            this.available = available;
        }

        public List<String> getRecommendations()
            throws Exception {

            return breaker.execute(
                () -> {
                    if (!available) {
                        throw new DependencyException(
                            "Recommendation engine unavailable.",
                            FailureCategory.DEPENDENCY
                        );
                    }

                    return List.of(
                        "Personalized product A",
                        "Personalized product B"
                    );
                },
                error -> cachedRecommendations
            );
        }
    }

    private static void runTests() throws Exception {

        CircuitBreaker breaker = new CircuitBreaker(
            "test-service",
            new CircuitConfig(
                2,
                Duration.ofMillis(30),
                1,
                50
            )
        );

        Callable<String> failure = () -> {
            throw new DependencyException(
                "Simulated outage.",
                FailureCategory.NETWORK
            );
        };

        FallbackPolicy<String> fallback =
            error -> "SAFE_FALLBACK";

        assert breaker.execute(failure, fallback)
            .equals("SAFE_FALLBACK");

        assert breaker.execute(failure, fallback)
            .equals("SAFE_FALLBACK");

        assert breaker.getState() == CircuitState.OPEN;

        assert breaker.execute(
            () -> "REMOTE",
            fallback
        ).equals("SAFE_FALLBACK");

        Thread.sleep(40);

        assert breaker.execute(
            () -> "RECOVERED",
            fallback
        ).equals("RECOVERED");

        assert breaker.getState() == CircuitState.CLOSED;

        try {
            new CircuitConfig(
                0,
                Duration.ofSeconds(1),
                1,
                10
            );

            throw new AssertionError(
                "Invalid configuration accepted."
            );

        } catch (IllegalArgumentException expected) {
            // Expected validation failure.
        }

        System.out.println("All Java 17 tests passed.");
    }

    public static void main(String[] args) {
        try {
            DependencyRegistry registry =
                new DependencyRegistry();

            PaymentService payments =
                new PaymentService(registry);

            RecommendationService recommendations =
                new RecommendationService(registry);

            payments.setProviderAvailable(false);

            System.out.println(
                "CIRCUIT BREAKER ENTERPRISE DEMONSTRATION"
            );

            for (double amount : new double[]{
                500, 750, 1000, 1500
            }) {
                System.out.println(
                    payments.processPayment(amount)
                );
            }

            recommendations.setAvailable(false);

            System.out.println(
                "\nRecommendation degradation:"
            );

            System.out.println(
                recommendations.getRecommendations()
            );

            System.out.println("\nDependency health report:");

            for (DependencyHealth health :
                registry.healthReport()) {

                System.out.println(health);
            }

            runTests();

        } catch (Exception error) {
            System.err.println(
                "Application failure: " +
                error.getMessage()
            );

            error.printStackTrace();

            System.exit(1);
        }
    }
}
