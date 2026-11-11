import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.time.Duration;

/*
 * Retry and Timeout Patterns
 * Enterprise dependency resilience engine.
 * Java 17, standard library only.
 */

public class RetryResilience {

    enum CircuitState {
        CLOSED, OPEN, HALF_OPEN
    }

    enum JitterMode {
        NONE, FULL, EQUAL
    }

    static class PermanentFailureException extends RuntimeException {
        PermanentFailureException(String message) {
            super(message);
        }
    }

    static class RetryExhaustedException extends RuntimeException {
        RetryExhaustedException(String message) {
            super(message);
        }
    }

    static class CircuitOpenException extends RuntimeException {
        CircuitOpenException(String message) {
            super(message);
        }
    }

    record RetryPolicy(
        int maxAttempts,
        Duration initialDelay,
        double multiplier,
        Duration maxDelay,
        Duration timeout,
        Duration maxElapsed,
        JitterMode jitter
    ) {
        RetryPolicy {
            Objects.requireNonNull(initialDelay);
            Objects.requireNonNull(maxDelay);
            Objects.requireNonNull(timeout);
            Objects.requireNonNull(maxElapsed);
            Objects.requireNonNull(jitter);

            if (maxAttempts < 1 ||
                initialDelay.isNegative() ||
                maxDelay.isNegative() ||
                multiplier < 1 ||
                timeout.isZero() ||
                timeout.isNegative() ||
                maxElapsed.isZero() ||
                maxElapsed.isNegative()) {
                throw new IllegalArgumentException(
                    "Invalid retry policy"
                );
            }
        }

        long calculateDelay(int retryNumber) {
            double ceiling = Math.min(
                maxDelay.toNanos(),
                initialDelay.toNanos() *
                    Math.pow(multiplier, retryNumber)
            );

            return switch (jitter) {
                case NONE -> (long) ceiling;
                case FULL -> ThreadLocalRandom.current()
                    .nextLong(Math.max(1, (long) ceiling + 1));
                case EQUAL -> {
                    long lower = (long) (ceiling / 2);
                    long upper = Math.max(lower + 1, (long) ceiling + 1);
                    yield ThreadLocalRandom.current()
                        .nextLong(lower, upper);
                }
            };
        }
    }

    record AttemptRecord(
        int attempt,
        String outcome,
        long delayNanos,
        String error
    ) {}

    record ExecutionResult<T>(
        boolean success,
        T value,
        int attempts,
        long elapsedNanos,
        List<AttemptRecord> history
    ) {}

    @FunctionalInterface
    interface RemoteOperation<T> {
        T execute() throws Exception;
    }

    static class RetryBudget {
        private final double capacity;
        private final double refillRate;

        private double tokens;
        private long lastUpdated;

        RetryBudget(double capacity, double refillRate) {
            if (capacity < 1 || refillRate < 0) {
                throw new IllegalArgumentException(
                    "Invalid retry budget"
                );
            }

            this.capacity = capacity;
            this.tokens = capacity;
            this.refillRate = refillRate;
            this.lastUpdated = System.nanoTime();
        }

        synchronized boolean consume() {
            long now = System.nanoTime();

            double elapsed =
                (now - lastUpdated) / 1_000_000_000.0;

            tokens = Math.min(
                capacity,
                tokens + elapsed * refillRate
            );

            lastUpdated = now;

            if (tokens < 1) return false;

            tokens--;
            return true;
        }
    }

    static class CircuitBreaker {
        private final int failureThreshold;
        private final long recoveryNanos;
        private final int halfOpenLimit;

        private int failures;
        private int halfOpenCalls;
        private long openedAt;

        private CircuitState state = CircuitState.CLOSED;

        CircuitBreaker(
            int failureThreshold,
            Duration recoveryTimeout,
            int halfOpenLimit
        ) {
            if (failureThreshold < 1 ||
                recoveryTimeout.isNegative() ||
                recoveryTimeout.isZero() ||
                halfOpenLimit < 1) {
                throw new IllegalArgumentException(
                    "Invalid circuit breaker configuration"
                );
            }

            this.failureThreshold = failureThreshold;
            this.recoveryNanos = recoveryTimeout.toNanos();
            this.halfOpenLimit = halfOpenLimit;
        }

        synchronized void acquire() {
            if (state == CircuitState.OPEN) {
                if (System.nanoTime() - openedAt < recoveryNanos) {
                    throw new CircuitOpenException(
                        "Dependency circuit is open"
                    );
                }

                state = CircuitState.HALF_OPEN;
                halfOpenCalls = 0;
            }

            if (state == CircuitState.HALF_OPEN) {
                if (halfOpenCalls >= halfOpenLimit) {
                    throw new CircuitOpenException(
                        "Half-open probe limit reached"
                    );
                }

                halfOpenCalls++;
            }
        }

        synchronized void success() {
            failures = 0;
            halfOpenCalls = 0;
            state = CircuitState.CLOSED;
        }

        synchronized void failure() {
            failures++;

            if (state == CircuitState.HALF_OPEN ||
                failures >= failureThreshold) {
                state = CircuitState.OPEN;
                openedAt = System.nanoTime();
                halfOpenCalls = 0;
            }
        }

        synchronized CircuitState getState() {
            return state;
        }
    }

    static class RetryExecutor {
        private final RetryPolicy policy;
        private final RetryBudget budget;
        private final CircuitBreaker breaker;

        RetryExecutor(
            RetryPolicy policy,
            RetryBudget budget,
            CircuitBreaker breaker
        ) {
            this.policy = Objects.requireNonNull(policy);
            this.budget = budget;
            this.breaker = breaker;
        }

        <T> ExecutionResult<T> execute(
            RemoteOperation<T> operation
        ) {
            long started = System.nanoTime();

            List<AttemptRecord> history = new ArrayList<>();

            for (int attempt = 1;
                 attempt <= policy.maxAttempts();
                 attempt++) {

                if (System.nanoTime() - started >=
                    policy.maxElapsed().toNanos()) {
                    throw new RetryExhaustedException(
                        "Maximum elapsed time exceeded"
                    );
                }

                if (breaker != null) {
                    breaker.acquire();
                }

                ExecutorService pool =
                    Executors.newSingleThreadExecutor();

                Future<T> future = pool.submit(() -> operation.execute());

                try {
                    T value = future.get(
                        policy.timeout().toNanos(),
                        TimeUnit.NANOSECONDS
                    );

                    if (breaker != null) breaker.success();

                    history.add(new AttemptRecord(
                        attempt, "success", 0, null
                    ));

                    return new ExecutionResult<>(
                        true,
                        value,
                        attempt,
                        System.nanoTime() - started,
                        List.copyOf(history)
                    );

                } catch (TimeoutException error) {
                    future.cancel(true);
                    pool.shutdownNow();

                    if (breaker != null) breaker.failure();

                    if (attempt == policy.maxAttempts()) {
                        throw new RetryExhaustedException(
                            "Request timed out after maximum attempts"
                        );
                    }

                    history.add(new AttemptRecord(
                        attempt,
                        "timeout",
                        0,
                        error.getMessage()
                    ));

                    waitBeforeRetry(attempt, started);

                } catch (ExecutionException error) {
                    pool.shutdownNow();

                    Throwable cause = error.getCause();

                    if (cause instanceof PermanentFailureException) {
                        if (breaker != null) breaker.success();
                        throw (PermanentFailureException) cause;
                    }

                    if (breaker != null) breaker.failure();

                    if (attempt == policy.maxAttempts()) {
                        throw new RetryExhaustedException(
                            "Retry attempts exhausted: " +
                            cause.getMessage()
                        );
                    }

                    history.add(new AttemptRecord(
                        attempt,
                        "retry",
                        0,
                        cause.getMessage()
                    ));

                    waitBeforeRetry(attempt, started);

                } catch (InterruptedException error) {
                    future.cancel(true);
                    pool.shutdownNow();

                    Thread.currentThread().interrupt();

                    throw new RetryExhaustedException(
                        "Execution interrupted"
                    );

                } finally {
                    pool.shutdownNow();
                }
            }

            throw new RetryExhaustedException(
                "Execution terminated"
            );
        }

        private void waitBeforeRetry(
            int attempt,
            long started
        ) {
            if (budget != null && !budget.consume()) {
                throw new RetryExhaustedException(
                    "Shared retry budget exhausted"
                );
            }

            long delay = policy.calculateDelay(attempt - 1);

            long remaining =
                policy.maxElapsed().toNanos() -
                (System.nanoTime() - started);

            if (delay >= remaining) {
                throw new RetryExhaustedException(
                    "Insufficient time for another attempt"
                );
            }

            try {
                TimeUnit.NANOSECONDS.sleep(delay);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();

                throw new RetryExhaustedException(
                    "Retry interrupted"
                );
            }
        }
    }

    static class PaymentGateway {
        private final AtomicInteger failuresRemaining;
        private final AtomicInteger calls = new AtomicInteger();

        PaymentGateway(int failures) {
            failuresRemaining = new AtomicInteger(failures);
        }

        String charge() {
            calls.incrementAndGet();

            if (failuresRemaining.getAndUpdate(
                value -> Math.max(0, value - 1)
            ) > 0) {
                throw new RuntimeException(
                    "Payment gateway temporarily unavailable"
                );
            }

            return "PAYMENT_APPROVED";
        }

        int calls() {
            return calls.get();
        }
    }

    record StormMetrics(
        int totalRetries,
        int maximumConcurrentRetries,
        Map<Long, Integer> schedule
    ) {}

    static StormMetrics simulateRetryStorm(
        int clients,
        int retries,
        long initialDelay,
        double multiplier,
        boolean jitter
    ) {
        Map<Long, Integer> schedule = new TreeMap<>();

        for (int client = 0; client < clients; client++) {
            double elapsed = 0;

            for (int retry = 0; retry < retries; retry++) {
                double ceiling =
                    initialDelay * Math.pow(multiplier, retry);

                double delay = jitter
                    ? ThreadLocalRandom.current().nextDouble(ceiling)
                    : ceiling;

                elapsed += delay;

                long bucket = Math.round(elapsed / 100.0);

                schedule.merge(bucket, 1, Integer::sum);
            }
        }

        int maximum = schedule.values().stream()
            .mapToInt(Integer::intValue)
            .max()
            .orElse(0);

        return new StormMetrics(
            clients * retries,
            maximum,
            Map.copyOf(schedule)
        );
    }

    public static void main(String[] args) {
        RetryPolicy policy = new RetryPolicy(
            4,
            Duration.ofMillis(10),
            2,
            Duration.ofMillis(50),
            Duration.ofSeconds(2),
            Duration.ofSeconds(5),
            JitterMode.FULL
        );

        RetryBudget budget = new RetryBudget(20, 10);

        CircuitBreaker breaker = new CircuitBreaker(
            5,
            Duration.ofSeconds(1),
            1
        );

        PaymentGateway gateway = new PaymentGateway(2);

        RetryExecutor executor = new RetryExecutor(
            policy, budget, breaker
        );

        ExecutionResult<String> result =
            executor.execute(gateway::charge);

        if (!result.success() || result.attempts() != 3) {
            throw new AssertionError("Recovery test failed");
        }

        System.out.println("Payment: " + result.value());
        System.out.println("Attempts: " + result.attempts());
        System.out.println("Gateway calls: " + gateway.calls());

        result.history().forEach(System.out::println);

        StormMetrics synchronizedStorm =
            simulateRetryStorm(100, 4, 1000, 2, false);

        StormMetrics jitteredStorm =
            simulateRetryStorm(100, 4, 1000, 2, true);

        System.out.println(
            "Synchronized retry peak: " +
            synchronizedStorm.maximumConcurrentRetries()
        );

        System.out.println(
            "Jittered retry peak: " +
            jitteredStorm.maximumConcurrentRetries()
        );

        System.out.println("All tests passed.");
    }
}
