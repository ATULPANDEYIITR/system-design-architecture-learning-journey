import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

/**
 * Bulkheads: Enterprise resource isolation and failure containment.
 *
 * Java 17
 * No third-party dependencies.
 */
public class BulkheadEnterprise {

    enum CircuitState {
        CLOSED,
        OPEN,
        HALF_OPEN
    }

    enum RequestState {
        QUEUED,
        RUNNING,
        COMPLETED,
        FAILED,
        REJECTED
    }

    enum FailureType {
        DOWNSTREAM_FAILURE,
        TIMEOUT,
        CAPACITY_EXCEEDED,
        CIRCUIT_OPEN
    }

    record PoolPolicy(
        String name,
        int concurrencyLimit,
        int queueLimit,
        int failureThreshold,
        Duration recoveryInterval,
        Duration executionTimeout
    ) {
        PoolPolicy {
            Objects.requireNonNull(name);
            Objects.requireNonNull(recoveryInterval);
            Objects.requireNonNull(executionTimeout);

            if (name.isBlank() ||
                concurrencyLimit < 1 ||
                queueLimit < 0 ||
                failureThreshold < 1 ||
                recoveryInterval.isNegative() ||
                recoveryInterval.isZero() ||
                executionTimeout.isNegative() ||
                executionTimeout.isZero()) {
                throw new IllegalArgumentException(
                    "Invalid resource pool policy"
                );
            }
        }
    }

    record Request(
        int id,
        String operation,
        boolean shouldFail,
        Instant submittedAt
    ) {
        Request {
            if (id <= 0 || operation == null || operation.isBlank()) {
                throw new IllegalArgumentException("Invalid request");
            }

            Objects.requireNonNull(submittedAt);
        }
    }

    record ExecutionResult(
        int requestId,
        RequestState state,
        String message,
        Duration duration
    ) {}

    record PoolSnapshot(
        String name,
        CircuitState circuitState,
        int active,
        int queued,
        long accepted,
        long completed,
        long failed,
        long rejected,
        double averageLatencyMilliseconds
    ) {}

    static class BulkheadException extends RuntimeException {
        private final FailureType type;

        BulkheadException(FailureType type, String message) {
            super(message);
            this.type = type;
        }

        FailureType type() {
            return type;
        }
    }

    /**
     * Circuit breaker controls requests to an unhealthy dependency.
     * It does not allocate resource capacity itself.
     */
    static final class CircuitBreaker {

        private final int threshold;
        private final Duration recoveryInterval;

        private CircuitState state = CircuitState.CLOSED;
        private int failures;
        private Instant openedAt;
        private boolean probeInProgress;

        CircuitBreaker(PoolPolicy policy) {
            this.threshold = policy.failureThreshold();
            this.recoveryInterval = policy.recoveryInterval();
        }

        synchronized boolean acquirePermission() {
            if (state == CircuitState.CLOSED) {
                return true;
            }

            if (state == CircuitState.OPEN) {
                if (Duration.between(
                    openedAt,
                    Instant.now()
                ).compareTo(recoveryInterval) < 0) {
                    return false;
                }

                state = CircuitState.HALF_OPEN;
                probeInProgress = false;
            }

            if (state == CircuitState.HALF_OPEN) {
                if (probeInProgress) {
                    return false;
                }

                probeInProgress = true;
                return true;
            }

            return false;
        }

        synchronized void recordSuccess() {
            failures = 0;
            state = CircuitState.CLOSED;
            probeInProgress = false;
        }

        synchronized void recordFailure() {
            failures++;
            probeInProgress = false;

            if (failures >= threshold) {
                state = CircuitState.OPEN;
                openedAt = Instant.now();
            }
        }

        synchronized void abandonProbe() {
            if (state == CircuitState.HALF_OPEN) {
                probeInProgress = false;
            }
        }

        synchronized CircuitState state() {
            return state;
        }
    }

    /**
     * One isolated execution domain with a bounded queue.
     *
     * All state transitions are synchronized so concurrent callers
     * cannot exceed the configured capacity.
     */
    static final class ResourcePool {

        private final PoolPolicy policy;
        private final CircuitBreaker breaker;
        private final Queue<Request> queue = new ArrayDeque<>();
        private final Map<Integer, RequestState> requestStates =
            new HashMap<>();

        private int active;
        private long accepted;
        private long completed;
        private long failed;
        private long rejected;
        private long totalLatencyNanos;

        ResourcePool(PoolPolicy policy) {
            this.policy = policy;
            this.breaker = new CircuitBreaker(policy);
        }

        synchronized RequestState submit(Request request) {
            if (requestStates.containsKey(request.id())) {
                throw new IllegalArgumentException(
                    "Duplicate request ID"
                );
            }

            if (!breaker.acquirePermission()) {
                rejected++;
                requestStates.put(request.id(), RequestState.REJECTED);
                return RequestState.REJECTED;
            }

            if (active < policy.concurrencyLimit()) {
                requestStates.put(request.id(), RequestState.RUNNING);
                return execute(request);
            }

            if (queue.size() >= policy.queueLimit()) {
                breaker.abandonProbe();
                rejected++;
                requestStates.put(request.id(), RequestState.REJECTED);
                return RequestState.REJECTED;
            }

            queue.add(request);
            requestStates.put(request.id(), RequestState.QUEUED);

            return RequestState.QUEUED;
        }

        private RequestState execute(Request request) {
            active++;
            accepted++;

            long started = System.nanoTime();

            try {
                // The sample represents a bounded synchronous service call.
                // Real I/O must use cancellable futures or client deadlines.
                if (request.shouldFail()) {
                    throw new BulkheadException(
                        FailureType.DOWNSTREAM_FAILURE,
                        "Downstream service failed"
                    );
                }

                completed++;
                breaker.recordSuccess();

                requestStates.put(
                    request.id(),
                    RequestState.COMPLETED
                );

                return RequestState.COMPLETED;

            } catch (BulkheadException exception) {
                failed++;
                breaker.recordFailure();

                requestStates.put(
                    request.id(),
                    RequestState.FAILED
                );

                return RequestState.FAILED;

            } finally {
                totalLatencyNanos += System.nanoTime() - started;
                active--;
                drainQueue();
            }
        }

        private void drainQueue() {
            while (
                active < policy.concurrencyLimit() &&
                !queue.isEmpty()
            ) {
                Request request = queue.remove();

                if (!breaker.acquirePermission()) {
                    rejected++;
                    requestStates.put(
                        request.id(),
                        RequestState.REJECTED
                    );
                    continue;
                }

                requestStates.put(
                    request.id(),
                    RequestState.RUNNING
                );

                execute(request);
            }
        }

        synchronized PoolSnapshot snapshot() {
            double average = completed == 0
                ? 0.0
                : totalLatencyNanos / 1_000_000.0 / completed;

            return new PoolSnapshot(
                policy.name(),
                breaker.state(),
                active,
                queue.size(),
                accepted,
                completed,
                failed,
                rejected,
                average
            );
        }

        synchronized RequestState stateOf(int requestId) {
            return requestStates.get(requestId);
        }

        PoolPolicy policy() {
            return policy;
        }
    }

    /**
     * Repository-like enterprise registry for independent service pools.
     */
    static final class ResourceRegistry {

        private final Map<String, ResourcePool> pools =
            new HashMap<>();

        synchronized void register(PoolPolicy policy) {
            if (pools.containsKey(policy.name())) {
                throw new IllegalArgumentException(
                    "Duplicate pool: " + policy.name()
                );
            }

            pools.put(policy.name(), new ResourcePool(policy));
        }

        synchronized ResourcePool get(String name) {
            ResourcePool pool = pools.get(name);

            if (pool == null) {
                throw new IllegalArgumentException(
                    "Unknown pool: " + name
                );
            }

            return pool;
        }

        List<PoolSnapshot> snapshots() {
            List<PoolSnapshot> results = new ArrayList<>();

            synchronized (this) {
                for (ResourcePool pool : pools.values()) {
                    results.add(pool.snapshot());
                }
            }

            return Collections.unmodifiableList(results);
        }
    }

    static final class RequestFactory {

        private final AtomicInteger sequence = new AtomicInteger();

        Request create(String operation, boolean fail) {
            return new Request(
                sequence.incrementAndGet(),
                operation,
                fail,
                Instant.now()
            );
        }
    }

    static void printReport(ResourceRegistry registry) {
        System.out.println("\nENTERPRISE RESOURCE REPORT");
        System.out.println(
            "--------------------------------------------------------------"
        );

        for (PoolSnapshot snapshot : registry.snapshots()) {
            System.out.printf(
                "%-15s state=%-10s active=%d queued=%d " +
                "accepted=%d completed=%d failed=%d rejected=%d " +
                "avgLatency=%.4fms%n",
                snapshot.name(),
                snapshot.circuitState(),
                snapshot.active(),
                snapshot.queued(),
                snapshot.accepted(),
                snapshot.completed(),
                snapshot.failed(),
                snapshot.rejected(),
                snapshot.averageLatencyMilliseconds()
            );
        }
    }

    static void verifyIsolation(ResourceRegistry registry) {
        for (PoolSnapshot snapshot : registry.snapshots()) {
            PoolPolicy policy = registry.get(snapshot.name()).policy();

            if (snapshot.active() > policy.concurrencyLimit()) {
                throw new IllegalStateException(
                    "Concurrency limit violated: " + snapshot.name()
                );
            }

            if (snapshot.queued() > policy.queueLimit()) {
                throw new IllegalStateException(
                    "Queue limit violated: " + snapshot.name()
                );
            }
        }
    }

    public static void main(String[] args) {

        ResourceRegistry registry = new ResourceRegistry();
        RequestFactory factory = new RequestFactory();

        registry.register(new PoolPolicy(
            "payment",
            2,
            3,
            3,
            Duration.ofSeconds(2),
            Duration.ofSeconds(1)
        ));

        registry.register(new PoolPolicy(
            "inventory",
            3,
            4,
            3,
            Duration.ofSeconds(2),
            Duration.ofSeconds(1)
        ));

        registry.register(new PoolPolicy(
            "notification",
            1,
            2,
            2,
            Duration.ofSeconds(2),
            Duration.ofSeconds(1)
        ));

        ResourcePool payments = registry.get("payment");
        ResourcePool inventory = registry.get("inventory");
        ResourcePool notifications = registry.get("notification");

        System.out.println("SCENARIO 1: Normal workload");

        for (int i = 0; i < 6; i++) {
            payments.submit(factory.create("process-payment", false));
        }

        for (int i = 0; i < 5; i++) {
            inventory.submit(factory.create("reserve-stock", false));
        }

        for (int i = 0; i < 4; i++) {
            notifications.submit(factory.create("send-message", false));
        }

        System.out.println("\nSCENARIO 2: Dependency failures");

        notifications.submit(
            factory.create("provider-unavailable", true)
        );

        notifications.submit(
            factory.create("provider-timeout", true)
        );

        System.out.println("\nSCENARIO 3: Independent service availability");

        Request paymentRequest = factory.create(
            "critical-payment",
            false
        );

        Request inventoryRequest = factory.create(
            "critical-reservation",
            false
        );

        payments.submit(paymentRequest);
        inventory.submit(inventoryRequest);

        System.out.println(
            "Payment state: " + payments.snapshot().circuitState()
        );

        System.out.println(
            "Inventory state: " + inventory.snapshot().circuitState()
        );

        System.out.println(
            "Notification state: " +
            notifications.snapshot().circuitState()
        );

        System.out.println("\nSCENARIO 4: Configuration validation");

        try {
            registry.register(new PoolPolicy(
                "invalid",
                0,
                2,
                3,
                Duration.ofSeconds(2),
                Duration.ofSeconds(1)
            ));
        } catch (IllegalArgumentException exception) {
            System.out.println(
                "Rejected policy: " + exception.getMessage()
            );
        }

        System.out.println("\nSCENARIO 5: Duplicate registration");

        try {
            registry.register(new PoolPolicy(
                "payment",
                1,
                1,
                2,
                Duration.ofSeconds(2),
                Duration.ofSeconds(1)
            ));
        } catch (IllegalArgumentException exception) {
            System.out.println(exception.getMessage());
        }

        printReport(registry);
        verifyIsolation(registry);

        System.out.println("\nEnterprise isolation invariants verified.");
    }
}
