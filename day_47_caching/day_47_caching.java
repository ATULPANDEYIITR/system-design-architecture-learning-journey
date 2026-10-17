import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

/*
 * Enterprise caching case study:
 *
 * A repository governance platform evaluates whether a change may enter a
 * protected production branch. The answer depends on reviews, approvals,
 * status checks, and branch policy. These inputs are expensive to retrieve,
 * so the service caches immutable evaluation snapshots.
 *
 * The Java design emphasizes explicit domain types, immutable records,
 * validation, service boundaries, and version-aware cache entries.
 */

public class CachingGovernanceDemo {

    enum ReviewState {
        COMMENTED,
        CHANGES_REQUESTED,
        APPROVED,
        DISMISSED
    }

    enum CheckState {
        PENDING,
        PASSED,
        FAILED
    }

    enum MergeState {
        BLOCKED,
        ELIGIBLE
    }

    record Review(
        String reviewer,
        ReviewState state,
        int policyVersion
    ) {
        Review {
            Objects.requireNonNull(reviewer, "reviewer");
            Objects.requireNonNull(state, "state");

            if (reviewer.isBlank()) {
                throw new IllegalArgumentException("reviewer cannot be blank");
            }
        }

        boolean countsAsApproval() {
            return state == ReviewState.APPROVED;
        }
    }

    record StatusCheck(
        String name,
        CheckState state
    ) {
        StatusCheck {
            Objects.requireNonNull(name, "name");
            Objects.requireNonNull(state, "state");
        }

        boolean passed() {
            return state == CheckState.PASSED;
        }
    }

    record BranchProtectionPolicy(
        String branchName,
        int requiredApprovals,
        List<String> requiredChecks,
        boolean requireLinearHistory,
        boolean prohibitDirectPush,
        boolean prohibitForcePush
    ) {
        BranchProtectionPolicy {
            if (branchName == null || branchName.isBlank()) {
                throw new IllegalArgumentException("branch name is required");
            }

            if (requiredApprovals < 0) {
                throw new IllegalArgumentException(
                    "required approvals cannot be negative"
                );
            }

            requiredChecks = List.copyOf(requiredChecks);
        }
    }

    record PullRequest(
        int number,
        String targetBranch,
        int sourceVersion
    ) {
        PullRequest {
            if (number <= 0) {
                throw new IllegalArgumentException(
                    "pull request number must be positive"
                );
            }

            Objects.requireNonNull(targetBranch, "targetBranch");
        }
    }

    record MergeDecision(
        MergeState state,
        List<String> reasons
    ) {
        MergeDecision {
            Objects.requireNonNull(state, "state");
            reasons = List.copyOf(reasons);
        }

        boolean eligible() {
            return state == MergeState.ELIGIBLE;
        }
    }

    record CacheKey(
        int pullRequestNumber,
        int policyVersion,
        int sourceVersion
    ) {}

    record CacheEntry<V>(
        V value,
        Instant expiresAt,
        String tag
    ) {
        boolean expired() {
            return Instant.now().compareTo(expiresAt) >= 0;
        }
    }

    static final class GovernanceCache<V> {
        private final Duration ttl;
        private final ConcurrentMap<CacheKey, CacheEntry<V>> entries =
            new ConcurrentHashMap<>();

        private final AtomicInteger hits = new AtomicInteger();
        private final AtomicInteger misses = new AtomicInteger();
        private final AtomicInteger writes = new AtomicInteger();
        private final AtomicInteger invalidations = new AtomicInteger();

        GovernanceCache(Duration ttl) {
            if (ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("TTL must be positive");
            }
            this.ttl = ttl;
        }

        Optional<V> get(CacheKey key) {
            CacheEntry<V> entry = entries.get(key);

            if (entry == null) {
                misses.incrementAndGet();
                return Optional.empty();
            }

            if (entry.expired()) {
                entries.remove(key, entry);
                misses.incrementAndGet();
                return Optional.empty();
            }

            hits.incrementAndGet();
            return Optional.of(entry.value());
        }

        void put(CacheKey key, V value, String tag) {
            entries.put(
                key,
                new CacheEntry<>(
                    value,
                    Instant.now().plus(ttl),
                    tag
                )
            );
            writes.incrementAndGet();
        }

        void invalidateTag(String tag) {
            int removed = 0;

            for (Map.Entry<CacheKey, CacheEntry<V>> entry : entries.entrySet()) {
                if (entry.getValue().tag().equals(tag)
                    && entries.remove(entry.getKey(), entry.getValue())) {
                    removed++;
                }
            }

            invalidations.addAndGet(removed);
        }

        String statistics() {
            return "hits=" + hits
                + ", misses=" + misses
                + ", writes=" + writes
                + ", invalidations=" + invalidations
                + ", entries=" + entries.size();
        }
    }


    interface GovernanceRepository {
        BranchProtectionPolicy policy();

        List<Review> reviews(int pullRequestNumber);

        List<StatusCheck> checks(int pullRequestNumber);

        PullRequest pullRequest(int number);
    }


    static final class InMemoryGovernanceRepository
        implements GovernanceRepository {

        private final AtomicInteger policyVersion = new AtomicInteger(1);

        private final BranchProtectionPolicy policy =
            new BranchProtectionPolicy(
                "main",
                2,
                List.of("build", "security-scan"),
                true,
                true,
                true
            );

        private final ConcurrentMap<Integer, PullRequest> pullRequests =
            new ConcurrentHashMap<>();

        private final ConcurrentMap<Integer, List<Review>> reviewMap =
            new ConcurrentHashMap<>();

        private final ConcurrentMap<Integer, List<StatusCheck>> checkMap =
            new ConcurrentHashMap<>();

        InMemoryGovernanceRepository() {
            pullRequests.put(
                42,
                new PullRequest(42, "main", 7)
            );

            reviewMap.put(
                42,
                List.of(
                    new Review("alice", ReviewState.APPROVED, 1),
                    new Review("bob", ReviewState.APPROVED, 1),
                    new Review("carol", ReviewState.COMMENTED, 1)
                )
            );

            checkMap.put(
                42,
                List.of(
                    new StatusCheck("build", CheckState.PASSED),
                    new StatusCheck("security-scan", CheckState.PASSED)
                )
            );
        }

        @Override
        public BranchProtectionPolicy policy() {
            simulateLatency();
            return policy;
        }

        @Override
        public List<Review> reviews(int pullRequestNumber) {
            simulateLatency();
            return List.copyOf(
                reviewMap.getOrDefault(pullRequestNumber, List.of())
            );
        }

        @Override
        public List<StatusCheck> checks(int pullRequestNumber) {
            simulateLatency();
            return List.copyOf(
                checkMap.getOrDefault(pullRequestNumber, List.of())
            );
        }

        @Override
        public PullRequest pullRequest(int number) {
            simulateLatency();
            return pullRequests.get(number);
        }

        void dismissApproval(int pullRequestNumber, String reviewer) {
            List<Review> updated = reviewMap.getOrDefault(
                pullRequestNumber,
                List.of()
            ).stream()
             .map(review -> review.reviewer().equals(reviewer)
                 ? new Review(
                     reviewer,
                     ReviewState.DISMISSED,
                     policyVersion.incrementAndGet()
                 )
                 : review)
             .toList();

            reviewMap.put(pullRequestNumber, updated);
        }

        int currentPolicyVersion() {
            return policyVersion.get();
        }

        private static void simulateLatency() {
            try {
                Thread.sleep(15);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "repository read interrupted",
                    error
                );
            }
        }
    }


    static final class MergeEligibilityService {
        private final GovernanceRepository repository;
        private final InMemoryGovernanceRepository mutableRepository;
        private final GovernanceCache<MergeDecision> cache =
            new GovernanceCache<>(Duration.ofSeconds(20));

        MergeEligibilityService(
            InMemoryGovernanceRepository repository
        ) {
            this.repository = repository;
            this.mutableRepository = repository;
        }

        MergeDecision evaluate(int pullRequestNumber) {
            PullRequest pullRequest =
                repository.pullRequest(pullRequestNumber);

            if (pullRequest == null) {
                throw new IllegalArgumentException(
                    "unknown pull request: " + pullRequestNumber
                );
            }

            BranchProtectionPolicy policy = repository.policy();

            CacheKey key = new CacheKey(
                pullRequest.number(),
                mutableRepository.currentPolicyVersion(),
                pullRequest.sourceVersion()
            );

            Optional<MergeDecision> cached = cache.get(key);

            if (cached.isPresent()) {
                return cached.get();
            }

            MergeDecision decision = evaluateAuthoritatively(
                pullRequest,
                policy
            );

            cache.put(
                key,
                decision,
                "pr:" + pullRequest.number()
            );

            return decision;
        }

        private MergeDecision evaluateAuthoritatively(
            PullRequest pullRequest,
            BranchProtectionPolicy policy
        ) {
            List<String> reasons = new ArrayList<>();

            if (!pullRequest.targetBranch().equals(policy.branchName())) {
                reasons.add("target branch is not protected main");
            }

            long approvals = repository.reviews(pullRequest.number())
                .stream()
                .filter(Review::countsAsApproval)
                .count();

            if (approvals < policy.requiredApprovals()) {
                reasons.add(
                    "approval count " + approvals
                    + " is below required "
                    + policy.requiredApprovals()
                );
            }

            List<StatusCheck> checks =
                repository.checks(pullRequest.number());

            for (String required : policy.requiredChecks()) {
                boolean passed = checks.stream()
                    .anyMatch(check ->
                        check.name().equals(required)
                        && check.passed()
                    );

                if (!passed) {
                    reasons.add(
                        "required check is not passing: " + required
                    );
                }
            }

            MergeState state = reasons.isEmpty()
                ? MergeState.ELIGIBLE
                : MergeState.BLOCKED;

            return new MergeDecision(state, reasons);
        }

        void invalidatePullRequest(int number) {
            cache.invalidateTag("pr:" + number);
        }

        String cacheStatistics() {
            return cache.statistics();
        }
    }


    public static void main(String[] args) {
        System.out.println("Enterprise caching and repository governance\n");

        InMemoryGovernanceRepository repository =
            new InMemoryGovernanceRepository();

        MergeEligibilityService service =
            new MergeEligibilityService(repository);

        MergeDecision first = service.evaluate(42);

        System.out.println(
            "First decision: " + first.state()
        );
        System.out.println(
            "Reasons: " + first.reasons()
        );

        MergeDecision second = service.evaluate(42);

        System.out.println(
            "Second decision: " + second.state()
        );
        System.out.println(
            "Cache after repeated read: "
            + service.cacheStatistics()
        );

        /*
         * Approval dismissal is a governance mutation. Leaving the previous
         * approval decision in a cache would allow an obsolete result to be
         * reused. Explicit invalidation makes the mutation visible immediately.
         */
        repository.dismissApproval(42, "bob");
        service.invalidatePullRequest(42);

        MergeDecision afterDismissal = service.evaluate(42);

        System.out.println(
            "After approval dismissal: "
            + afterDismissal.state()
        );
        System.out.println(
            "Reasons: "
            + afterDismissal.reasons()
        );

        System.out.println(
            "Final cache statistics: "
            + service.cacheStatistics()
        );
    }
}
