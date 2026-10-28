import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class CdnArchitectureDemo {

    enum CacheStatus {
        HIT, MISS, REVALIDATED, BYPASS, STALE
    }

    enum MergeEligibility {
        ELIGIBLE, BLOCKED
    }

    record CachePolicy(
            int defaultTtlSeconds,
            int maxTtlSeconds,
            int requiredApprovals,
            boolean cacheAuthenticated
    ) {
        CachePolicy {
            if (defaultTtlSeconds < 0 ||
                maxTtlSeconds < defaultTtlSeconds ||
                requiredApprovals < 0) {
                throw new IllegalArgumentException("Invalid cache policy");
            }
        }
    }

    record Request(
            String method,
            String host,
            String path,
            Map<String, String> query,
            boolean authenticated
    ) {
        Request {
            method = method.toUpperCase();

            if (!Set.of("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE")
                    .contains(method)) {
                throw new IllegalArgumentException("Unsupported HTTP method");
            }

            if (host == null || !host.matches("[A-Za-z0-9.-]+")) {
                throw new IllegalArgumentException("Invalid host");
            }

            if (path == null || !path.startsWith("/")) {
                throw new IllegalArgumentException("Invalid path");
            }

            query = Map.copyOf(query);
        }
    }

    record OriginResponse(
            int status,
            String body,
            String contentType,
            String etag,
            String cacheControl
    ) {}

    record CacheEntry(
            OriginResponse response,
            Instant storedAt,
            Instant expiresAt
    ) {}

    record Review(
            String reviewer,
            boolean approved,
            boolean stale,
            boolean eligible
    ) {}

    record StatusCheck(
            String name,
            boolean required,
            boolean passed
    ) {}

    record BranchProtectionPolicy(
            boolean requirePullRequest,
            int requiredReviews,
            boolean requireStatusChecks,
            boolean restrictDirectPush,
            boolean restrictForcePush,
            boolean restrictDeletion,
            boolean requireResolvedConversations,
            boolean requireLinearHistory
    ) {}

    record PullRequest(
            int number,
            String sourceBranch,
            String targetBranch,
            boolean open,
            boolean draft,
            boolean mergeConflict,
            boolean conversationsResolved,
            List<Review> reviews,
            List<StatusCheck> checks
    ) {}

    static final class OriginServer {
        private final Map<String, OriginResponse> objects = new HashMap<>();
        private int fetchCount;

        void publish(
                String path,
                String body,
                String contentType,
                String cacheControl,
                String etag
        ) {
            objects.put(
                    path,
                    new OriginResponse(
                            200,
                            body,
                            contentType,
                            etag,
                            cacheControl
                    )
            );
        }

        OriginResponse fetch(String path, String ifNoneMatch) {
            fetchCount++;

            OriginResponse response = objects.get(path);

            if (response == null) {
                return new OriginResponse(
                        404,
                        "Not Found",
                        "text/plain",
                        "404",
                        "no-store"
                );
            }

            if (ifNoneMatch != null &&
                ifNoneMatch.equals(response.etag())) {
                return response;
            }

            return response;
        }

        int fetchCount() {
            return fetchCount;
        }
    }

    static final class EdgeCache {
        private final String name;
        private final int capacity;
        private final CachePolicy policy;

        // LinkedHashMap is deliberately used for LRU ordering.
        private final java.util.LinkedHashMap<String, CacheEntry> cache =
                new java.util.LinkedHashMap<>(16, 0.75f, true);

        EdgeCache(String name, int capacity, CachePolicy policy) {
            if (capacity <= 0) {
                throw new IllegalArgumentException(
                        "Edge capacity must be positive"
                );
            }

            this.name = name;
            this.capacity = capacity;
            this.policy = policy;
        }

        private int ttlSeconds(String cacheControl) {
            Matcher matcher = Pattern
                    .compile("max-age=(\\d+)")
                    .matcher(cacheControl);

            int ttl = matcher.find()
                    ? Integer.parseInt(matcher.group(1))
                    : policy.defaultTtlSeconds();

            return Math.min(ttl, policy.maxTtlSeconds());
        }

        private boolean cacheable(OriginResponse response) {
            return !response.cacheControl().contains("no-store")
                    && !response.cacheControl().contains("private");
        }

        CacheEntry get(String key) {
            return cache.get(key);
        }

        void put(String key, OriginResponse response, Instant now) {
            if (!cacheable(response)) {
                return;
            }

            int ttl = ttlSeconds(response.cacheControl());

            cache.put(
                    key,
                    new CacheEntry(
                            response,
                            now,
                            now.plusSeconds(ttl)
                    )
            );

            while (cache.size() > capacity) {
                String oldest = cache.keySet().iterator().next();
                cache.remove(oldest);
            }
        }

        int purgePath(String path) {
            List<String> keys = new ArrayList<>();

            for (String key : cache.keySet()) {
                if (key.contains("|" + path + "|")) {
                    keys.add(key);
                }
            }

            keys.forEach(cache::remove);
            return keys.size();
        }

        String name() {
            return name;
        }

        int size() {
            return cache.size();
        }
    }

    static final class CdnService {
        private static final Set<String> TRACKING_PARAMETERS = Set.of(
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "fbclid"
        );

        private final OriginServer origin;
        private final CachePolicy policy;
        private final Map<String, EdgeCache> edges = new HashMap<>();

        CdnService(OriginServer origin, CachePolicy policy) {
            this.origin = origin;
            this.policy = policy;

            edges.put("blr", new EdgeCache("blr", 2, policy));
            edges.put("fra", new EdgeCache("fra", 2, policy));
            edges.put("iad", new EdgeCache("iad", 2, policy));
        }

        private EdgeCache route(String region) {
            String preferred = switch (region.toLowerCase()) {
                case "india" -> "blr";
                case "europe" -> "fra";
                case "north-america" -> "iad";
                default -> "blr";
            };

            return edges.getOrDefault(preferred, edges.get("blr"));
        }

        private String cacheKey(Request request) {
            List<Map.Entry<String, String>> parameters =
                    new ArrayList<>(request.query().entrySet());

            parameters.removeIf(
                    entry -> TRACKING_PARAMETERS.contains(
                            entry.getKey().toLowerCase()
                    )
            );

            parameters.sort(
                    Map.Entry.comparingByKey()
            );

            String query = parameters.stream()
                    .map(entry -> entry.getKey() + "=" + entry.getValue())
                    .reduce(
                            (a, b) -> a + "&" + b
                    )
                    .orElse("");

            return request.host().toLowerCase()
                    + "|" + request.method()
                    + "|" + request.path()
                    + "|" + query;
        }

        record Result(
                OriginResponse response,
                CacheStatus status,
                String edge
        ) {}

        Result serve(Request request, String region, Instant now) {
            EdgeCache edge = route(region);

            if (!request.method().equals("GET")
                    && !request.method().equals("HEAD")) {
                return new Result(
                        origin.fetch(request.path(), null),
                        CacheStatus.BYPASS,
                        edge.name()
                );
            }

            if (request.authenticated() && !policy.cacheAuthenticated()) {
                return new Result(
                        origin.fetch(request.path(), null),
                        CacheStatus.BYPASS,
                        edge.name()
                );
            }

            String key = cacheKey(request);
            CacheEntry entry = edge.get(key);

            if (entry != null && entry.expiresAt().isAfter(now)) {
                return new Result(
                        entry.response(),
                        CacheStatus.HIT,
                        edge.name()
                );
            }

            if (entry != null) {
                OriginResponse response = origin.fetch(
                        request.path(),
                        entry.response().etag()
                );

                if (response.etag().equals(entry.response().etag())) {
                    edge.put(key, response, now);
                    return new Result(
                            response,
                            CacheStatus.REVALIDATED,
                            edge.name()
                    );
                }

                edge.put(key, response, now);

                return new Result(
                        response,
                        CacheStatus.STALE,
                        edge.name()
                );
            }

            OriginResponse response = origin.fetch(
                    request.path(),
                    null
            );

            edge.put(key, response, now);

            return new Result(
                    response,
                    CacheStatus.MISS,
                    edge.name()
            );
        }

        int purge(String path) {
            return edges.values()
                    .stream()
                    .mapToInt(edge -> edge.purgePath(path))
                    .sum();
        }

        void printCacheState() {
            edges.values().stream()
                    .sorted((a, b) -> a.name().compareTo(b.name()))
                    .forEach(edge ->
                            System.out.printf(
                                    "edge=%s cachedObjects=%d%n",
                                    edge.name(),
                                    edge.size()
                            )
                    );
        }
    }

    static final class MergeEligibilityService {
        private final BranchProtectionPolicy policy;

        MergeEligibilityService(BranchProtectionPolicy policy) {
            this.policy = policy;
        }

        MergeEligibility evaluate(PullRequest pullRequest) {
            if (!pullRequest.open() || pullRequest.draft()) {
                return MergeEligibility.BLOCKED;
            }

            if (pullRequest.sourceBranch().isBlank()
                    || pullRequest.targetBranch().isBlank()) {
                return MergeEligibility.BLOCKED;
            }

            if (pullRequest.mergeConflict()) {
                return MergeEligibility.BLOCKED;
            }

            if (policy.requireResolvedConversations()
                    && !pullRequest.conversationsResolved()) {
                return MergeEligibility.BLOCKED;
            }

            if (policy.requireStatusChecks()) {
                boolean checksPassed = pullRequest.checks()
                        .stream()
                        .filter(StatusCheck::required)
                        .allMatch(StatusCheck::passed);

                if (!checksPassed) {
                    return MergeEligibility.BLOCKED;
                }
            }

            long approvals = pullRequest.reviews()
                    .stream()
                    .filter(Review::eligible)
                    .filter(Review::approved)
                    .filter(review -> !review.stale())
                    .count();

            return approvals >= policy.requiredReviews()
                    ? MergeEligibility.ELIGIBLE
                    : MergeEligibility.BLOCKED;
        }
    }

    public static void main(String[] args) {
        CachePolicy policy = new CachePolicy(
                30,
                300,
                2,
                false
        );

        OriginServer origin = new OriginServer();

        origin.publish(
                "/assets/app.js",
                "release-42",
                "application/javascript",
                "public, max-age=120",
                "etag-app-42"
        );

        origin.publish(
                "/index.html",
                "<html>release-42</html>",
                "text/html",
                "public, max-age=20",
                "etag-index-42"
        );

        CdnService cdn = new CdnService(origin, policy);

        Instant start = Instant.now();

        Request asset = new Request(
                "GET",
                "example.test",
                "/assets/app.js",
                Map.of(),
                false
        );

        CdnService.Result first = cdn.serve(
                asset,
                "india",
                start
        );

        CdnService.Result second = cdn.serve(
                asset,
                "india",
                start.plus(Duration.ofSeconds(10))
        );

        CdnService.Result expired = cdn.serve(
                asset,
                "india",
                start.plus(Duration.ofSeconds(150))
        );

        System.out.printf(
                "First request: %s edge=%s%n",
                first.status(),
                first.edge()
        );

        System.out.printf(
                "Second request: %s edge=%s%n",
                second.status(),
                second.edge()
        );

        System.out.printf(
                "Expired request: %s edge=%s%n",
                expired.status(),
                expired.edge()
        );

        Request authenticated = new Request(
                "GET",
                "example.test",
                "/account",
                Map.of(),
                true
        );

        CdnService.Result privateRequest = cdn.serve(
                authenticated,
                "india",
                start
        );

        System.out.printf(
                "Authenticated request: %s%n",
                privateRequest.status()
        );

        System.out.printf(
                "Origin fetches: %d%n",
                origin.fetchCount()
        );

        System.out.println("Cache state:");
        cdn.printCacheState();

        System.out.printf(
                "Purged asset entries: %d%n",
                cdn.purge("/assets/app.js")
        );

        BranchProtectionPolicy governancePolicy =
                new BranchProtectionPolicy(
                        true,
                        2,
                        true,
                        true,
                        true,
                        true,
                        true,
                        false
                );

        PullRequest pullRequest = new PullRequest(
                42,
                "feature/cache-policy",
                "main",
                true,
                false,
                false,
                true,
                List.of(
                        new Review("reviewer-a", true, false, true),
                        new Review("reviewer-b", true, false, true),
                        new Review("reviewer-c", true, true, true)
                ),
                List.of(
                        new StatusCheck("unit-tests", true, true),
                        new StatusCheck("security-scan", true, true),
                        new StatusCheck("cdn-integration", true, true)
                )
        );

        MergeEligibilityService governance =
                new MergeEligibilityService(governancePolicy);

        System.out.println(
                "Governance decision: "
                        + governance.evaluate(pullRequest)
        );
    }
}
