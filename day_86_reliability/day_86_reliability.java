import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public class GracefulDegradationEnterprise {

    enum ServiceState {
        HEALTHY,
        DEGRADED,
        FAILED,
        RECOVERING
    }

    enum DependencyType {
        REQUIRED,
        OPTIONAL
    }

    enum CircuitState {
        CLOSED,
        OPEN,
        HALF_OPEN
    }

    enum OperationMode {
        FULL,
        DEGRADED,
        UNAVAILABLE
    }

    enum CheckStatus {
        PASSED,
        FAILED,
        PENDING
    }

    static class ServiceException extends RuntimeException {
        ServiceException(String message) {
            super(message);
        }

        ServiceException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    record ServiceResult<T>(
        T value,
        boolean degraded,
        String source,
        String error
    ) {}

    record HealthSnapshot(
        String name,
        DependencyType type,
        ServiceState state,
        CircuitState circuit,
        int failures,
        int recoveries
    ) {}

    record StatusCheck(
        String name,
        CheckStatus status
    ) {
        StatusCheck {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Check name required");
            }
            Objects.requireNonNull(status);
        }
    }

    record Review(
        String reviewer,
        boolean eligible,
        boolean dismissed,
        boolean stale,
        boolean approved
    ) {
        Review {
            if (reviewer == null || reviewer.isBlank()) {
                throw new IllegalArgumentException("Reviewer required");
            }
        }

        boolean countsAsApproval() {
            return eligible && !dismissed && !stale && approved;
        }
    }

    record BranchProtectionPolicy(
        int requiredApprovals,
        Set<String> requiredChecks,
        boolean requireResolvedConversations,
        boolean requireLinearHistory,
        boolean allowForcePush,
        boolean allowDeletion,
        boolean administratorBypass
    ) {
        BranchProtectionPolicy {
            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                    "Required approvals cannot be negative"
                );
            }

            requiredChecks = Set.copyOf(requiredChecks);
        }
    }

    record PullRequest(
        long id,
        String sourceBranch,
        String targetBranch,
        String headCommit,
        String baseCommit,
        boolean open,
        boolean draft,
        boolean conflicts,
        boolean conversationsResolved,
        boolean linearHistory,
        List<Review> reviews,
        Map<String, StatusCheck> checks
    ) {
        PullRequest {
            if (id <= 0) {
                throw new IllegalArgumentException("Invalid PR identifier");
            }

            if (
                sourceBranch == null ||
                sourceBranch.isBlank() ||
                targetBranch == null ||
                targetBranch.isBlank()
            ) {
                throw new IllegalArgumentException("Branch names required");
            }

            if (sourceBranch.equals(targetBranch)) {
                throw new IllegalArgumentException(
                    "Source and target branches must differ"
                );
            }

            if (headCommit == null || baseCommit == null) {
                throw new IllegalArgumentException("Commit identifiers required");
            }

            reviews = List.copyOf(reviews);
            checks = Map.copyOf(checks);
        }
    }

    record MergeDecision(
        boolean eligible,
        List<String> blockers,
        List<String> warnings
    ) {
        MergeDecision {
            blockers = List.copyOf(blockers);
            warnings = List.copyOf(warnings);
        }
    }

    static class CircuitBreaker {
        private final int threshold;
        private final Duration recoveryTimeout;
        private final AtomicInteger failures = new AtomicInteger();

        private volatile CircuitState state = CircuitState.CLOSED;
        private volatile Instant openedAt;

        CircuitBreaker(int threshold, Duration recoveryTimeout) {
            if (
                threshold < 1 ||
                recoveryTimeout == null ||
                recoveryTimeout.isNegative() ||
                recoveryTimeout.isZero()
            ) {
                throw new IllegalArgumentException(
                    "Invalid circuit breaker configuration"
                );
            }

            this.threshold = threshold;
            this.recoveryTimeout = recoveryTimeout;
        }

        synchronized boolean allowRequest() {
            if (state == CircuitState.CLOSED) {
                return true;
            }

            if (state == CircuitState.OPEN) {
                if (
                    openedAt != null &&
                    Duration.between(openedAt, Instant.now())
                        .compareTo(recoveryTimeout) >= 0
                ) {
                    state = CircuitState.HALF_OPEN;
                    return true;
                }

                return false;
            }

            return true;
        }

        synchronized void success() {
            failures.set(0);
            state = CircuitState.CLOSED;
            openedAt = null;
        }

        synchronized void failure() {
            int count = failures.incrementAndGet();

            if (
                state == CircuitState.HALF_OPEN ||
                count >= threshold
            ) {
                state = CircuitState.OPEN;
                openedAt = Instant.now();
            }
        }

        CircuitState state() {
            return state;
        }

        int failureCount() {
            return failures.get();
        }
    }

    static class ManagedService<T> {
        private final String name;
        private final DependencyType type;
        private final Supplier<T> operation;
        private final Supplier<T> fallback;
        private final CircuitBreaker breaker;

        private volatile ServiceState state = ServiceState.HEALTHY;
        private int recoveries;

        ManagedService(
            String name,
            DependencyType type,
            Supplier<T> operation,
            Supplier<T> fallback
        ) {
            this.name = Objects.requireNonNull(name);
            this.type = Objects.requireNonNull(type);
            this.operation = Objects.requireNonNull(operation);
            this.fallback = fallback;

            if (
                type == DependencyType.OPTIONAL &&
                fallback == null
            ) {
                throw new IllegalArgumentException(
                    "Optional service requires a fallback"
                );
            }

            this.breaker = new CircuitBreaker(
                2,
                Duration.ofMillis(200)
            );
        }

        synchronized ServiceResult<T> execute() {
            if (!breaker.allowRequest()) {
                return failure(
                    new ServiceException("Circuit breaker is open")
                );
            }

            try {
                T value = operation.get();

                if (value == null) {
                    throw new ServiceException(
                        "Dependency returned null"
                    );
                }

                breaker.success();
                state = ServiceState.HEALTHY;
                recoveries++;

                return new ServiceResult<>(
                    value,
                    false,
                    "PRIMARY",
                    null
                );

            } catch (RuntimeException error) {
                breaker.failure();
                return failure(error);
            }
        }

        private ServiceResult<T> failure(RuntimeException error) {
            if (type == DependencyType.REQUIRED) {
                state = ServiceState.FAILED;

                throw new ServiceException(
                    name + " is unavailable",
                    error
                );
            }

            state = ServiceState.DEGRADED;

            return new ServiceResult<>(
                fallback.get(),
                true,
                "FALLBACK",
                error.getMessage()
            );
        }

        HealthSnapshot health() {
            return new HealthSnapshot(
                name,
                type,
                state,
                breaker.state(),
                breaker.failureCount(),
                recoveries
            );
        }
    }

    static class RepositoryGovernanceService {

        private final BranchProtectionPolicy policy;

        RepositoryGovernanceService(BranchProtectionPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        MergeDecision evaluate(PullRequest pr) {
            List<String> blockers = new ArrayList<>();
            List<String> warnings = new ArrayList<>();

            if (!pr.open()) {
                blockers.add("Pull Request is closed");
            }

            if (pr.draft()) {
                blockers.add("Draft Pull Request cannot be merged");
            }

            if (pr.conflicts()) {
                blockers.add("Merge conflicts must be resolved");
            }

            if (
                policy.requireLinearHistory() &&
                !pr.linearHistory()
            ) {
                blockers.add("Linear history requirement not satisfied");
            }

            if (
                policy.requireResolvedConversations() &&
                !pr.conversationsResolved()
            ) {
                blockers.add("Unresolved review conversations exist");
            }

            // Unique reviewer identities prevent duplicate approvals.
            Set<String> eligibleApprovers = pr.reviews()
                .stream()
                .filter(Review::countsAsApproval)
                .map(Review::reviewer)
                .collect(Collectors.toSet());

            if (eligibleApprovers.size() < policy.requiredApprovals()) {
                blockers.add(
                    "Insufficient approvals: " +
                    eligibleApprovers.size() + "/" +
                    policy.requiredApprovals()
                );
            }

            for (String required : policy.requiredChecks()) {
                StatusCheck check = pr.checks().get(required);

                if (check == null) {
                    blockers.add("Missing check: " + required);
                } else if (check.status() != CheckStatus.PASSED) {
                    blockers.add("Check not passed: " + required);
                }
            }

            return new MergeDecision(
                blockers.isEmpty(),
                blockers,
                warnings
            );
        }
    }

    static class EnterpriseApplication {
        private final Map<String, ManagedService<?>> services =
            new ConcurrentHashMap<>();

        void register(ManagedService<?> service) {
            // Registration is atomic and duplicate names are rejected.
            ManagedService<?> previous = services.putIfAbsent(
                service.name,
                service
            );

            if (previous != null) {
                throw new IllegalArgumentException(
                    "Duplicate service registration"
                );
            }
        }

        OperationMode evaluateSystemMode() {
            List<HealthSnapshot> health = services.values()
                .stream()
                .map(ManagedService::health)
                .toList();

            if (health.stream().anyMatch(
                item ->
                    item.type() == DependencyType.REQUIRED &&
                    item.state() == ServiceState.FAILED
            )) {
                return OperationMode.UNAVAILABLE;
            }

            if (health.stream().anyMatch(
                item -> item.state() != ServiceState.HEALTHY
            )) {
                return OperationMode.DEGRADED;
            }

            return OperationMode.FULL;
        }

        List<HealthSnapshot> healthReport() {
            return services.values()
                .stream()
                .map(ManagedService::health)
                .toList();
        }
    }

    public static void main(String[] args) {
        EnterpriseApplication application = new EnterpriseApplication();

        ManagedService<Map<String, String>> catalog =
            new ManagedService<>(
                "catalog",
                DependencyType.REQUIRED,
                () -> Map.of(
                    "id", "P-100",
                    "name", "Enterprise Laptop"
                ),
                null
            );

        ManagedService<Integer> inventory =
            new ManagedService<>(
                "inventory",
                DependencyType.REQUIRED,
                () -> 25,
                null
            );

        AtomicInteger recommendationAttempts = new AtomicInteger();

        ManagedService<List<String>> recommendations =
            new ManagedService<>(
                "recommendations",
                DependencyType.OPTIONAL,
                () -> {
                    if (recommendationAttempts.incrementAndGet() <= 2) {
                        throw new ServiceException(
                            "Recommendation service timeout"
                        );
                    }

                    return List.of("USB Hub", "Laptop Stand");
                },
                List::of
            );

        application.register(catalog);
        application.register(inventory);
        application.register(recommendations);

        System.out.println("SCENARIO 1: Full functionality");

        ServiceResult<Map<String, String>> product = catalog.execute();
        ServiceResult<Integer> stock = inventory.execute();

        System.out.println("Product: " + product.value());
        System.out.println("Inventory: " + stock.value());

        System.out.println("\nSCENARIO 2: Optional dependency failure");

        ServiceResult<List<String>> first = recommendations.execute();
        System.out.println("Recommendations: " + first.value());
        System.out.println("Fallback used: " + first.degraded());

        ServiceResult<List<String>> second = recommendations.execute();
        System.out.println("Recommendations: " + second.value());
        System.out.println("Fallback used: " + second.degraded());

        System.out.println(
            "System mode: " + application.evaluateSystemMode()
        );

        System.out.println("\nSCENARIO 3: Repository merge governance");

        BranchProtectionPolicy policy = new BranchProtectionPolicy(
            2,
            Set.of("build", "unit-tests", "security-scan"),
            true,
            true,
            false,
            false,
            false
        );

        RepositoryGovernanceService governance =
            new RepositoryGovernanceService(policy);

        List<Review> reviews = List.of(
            new Review("reviewer-1", true, false, false, true),
            new Review("reviewer-2", true, false, false, true),
            new Review("external-user", false, false, false, true),
            new Review("reviewer-3", true, true, false, true),
            new Review("reviewer-4", true, false, true, true)
        );

        Map<String, StatusCheck> checks = new HashMap<>();
        checks.put(
            "build",
            new StatusCheck("build", CheckStatus.PASSED)
        );
        checks.put(
            "unit-tests",
            new StatusCheck("unit-tests", CheckStatus.PASSED)
        );
        checks.put(
            "security-scan",
            new StatusCheck("security-scan", CheckStatus.PASSED)
        );

        PullRequest pr = new PullRequest(
            104,
            "feature/payment-retry",
            "main",
            "a8f12d7",
            "c3109ab",
            true,
            false,
            false,
            true,
            true,
            reviews,
            checks
        );

        MergeDecision decision = governance.evaluate(pr);

        System.out.println("Merge eligible: " + decision.eligible());
        decision.blockers().forEach(
            blocker -> System.out.println("BLOCKER: " + blocker)
        );

        if (!decision.eligible()) {
            throw new IllegalStateException(
                "Expected Pull Request to be eligible"
            );
        }

        System.out.println("\nSCENARIO 4: Missing security check");

        Map<String, StatusCheck> failedChecks = new HashMap<>(checks);
        failedChecks.remove("security-scan");

        PullRequest unsafePr = new PullRequest(
            105,
            "feature/payment-retry",
            "main",
            "f821ab3",
            "c3109ab",
            true,
            false,
            false,
            true,
            true,
            reviews,
            failedChecks
        );

        MergeDecision blocked = governance.evaluate(unsafePr);

        System.out.println("Merge eligible: " + blocked.eligible());
        blocked.blockers().forEach(
            blocker -> System.out.println("BLOCKER: " + blocker)
        );

        if (blocked.eligible()) {
            throw new IllegalStateException(
                "Missing security check was incorrectly accepted"
            );
        }

        System.out.println("\nHEALTH REPORT");

        application.healthReport().forEach(System.out::println);

        System.out.println("\nEnterprise resilience assertions passed.");
    }
}
