import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Enterprise-oriented CDN governance model.
 *
 * The domain is deliberately separated into content, origin, edges,
 * cache policy, routing, and merge-like eligibility decisions.
 */
public class CdnGovernance {

    enum EdgeState {
        HEALTHY,
        DEGRADED,
        OFFLINE
    }

    enum CacheStatus {
        HIT,
        MISS,
        STALE,
        BYPASS,
        ORIGIN_ERROR
    }

    record Content(
        String path,
        String body,
        String contentType,
        int version,
        int ttlSeconds,
        boolean cacheable
    ) {
        Content {
            if (path == null || !path.startsWith("/")
                    || path.contains("..")
                    || path.length() > 2048) {
                throw new ValidationException("Invalid content path");
            }
            if (ttlSeconds < 0) {
                throw new ValidationException("TTL cannot be negative");
            }
        }
    }

    record CacheEntry(Content content, long storedAt) {
        boolean fresh(long now) {
            return now - storedAt < content.ttlSeconds();
        }
    }

    record RequestResult(
        CacheStatus status,
        String edgeId,
        int latencyMs,
        Integer version,
        String message
    ) {}

    static final class ValidationException extends RuntimeException {
        ValidationException(String message) {
            super(message);
        }
    }

    static final class OriginUnavailableException extends RuntimeException {
        OriginUnavailableException(String message) {
            super(message);
        }
    }

    static final class ContentNotFoundException extends RuntimeException {
        ContentNotFoundException(String message) {
            super(message);
        }
    }

    interface CachePolicy {
        boolean shouldCache(Content content);

        boolean shouldBypass(String path, boolean authenticated);
    }

    static final class StandardCachePolicy implements CachePolicy {
        @Override
        public boolean shouldCache(Content content) {
            return content.cacheable() && content.ttlSeconds() > 0;
        }

        @Override
        public boolean shouldBypass(
            String path,
            boolean authenticated
        ) {
            if (path.startsWith("/private/")) {
                return !authenticated;
            }
            return false;
        }
    }

    static final class OriginService {
        private final Map<String, Content> content = new HashMap<>();
        private boolean available = true;

        Content publish(
            String path,
            String body,
            String contentType,
            int ttlSeconds,
            boolean cacheable
        ) {
            int version = content.containsKey(path)
                ? content.get(path).version() + 1
                : 1;

            Content value = new Content(
                path,
                body,
                contentType,
                version,
                ttlSeconds,
                cacheable
            );

            content.put(path, value);
            return value;
        }

        Content fetch(String path) {
            if (!available) {
                throw new OriginUnavailableException(
                    "Origin service unavailable"
                );
            }

            Content value = content.get(path);
            if (value == null) {
                throw new ContentNotFoundException(
                    "Content not found: " + path
                );
            }

            return value;
        }

        void setAvailable(boolean available) {
            this.available = available;
        }
    }

    static final class EdgeNode {
        private final String id;
        private final String region;
        private final int latencyMs;
        private final int capacity;

        private EdgeState state = EdgeState.HEALTHY;

        // accessOrder=true gives an LRU-style cache.
        private final LinkedHashMap<String, CacheEntry> cache =
            new LinkedHashMap<>(16, 0.75f, true);

        private int hits;
        private int misses;
        private int stale;
        private int evictions;

        EdgeNode(
            String id,
            String region,
            int latencyMs,
            int capacity
        ) {
            if (latencyMs < 0 || capacity <= 0) {
                throw new ValidationException(
                    "Invalid edge capacity or latency"
                );
            }

            this.id = id;
            this.region = region;
            this.latencyMs = latencyMs;
            this.capacity = capacity;
        }

        String id() {
            return id;
        }

        String region() {
            return region;
        }

        int latencyMs() {
            return latencyMs;
        }

        EdgeState state() {
            return state;
        }

        void setState(EdgeState state) {
            this.state = state;
        }

        Optional<Content> lookup(String path, long now) {
            if (state == EdgeState.OFFLINE) {
                return Optional.empty();
            }

            CacheEntry entry = cache.get(path);

            if (entry == null) {
                misses++;
                return Optional.empty();
            }

            if (!entry.fresh(now)) {
                cache.remove(path);
                stale++;
                return Optional.empty();
            }

            hits++;
            return Optional.of(entry.content());
        }

        void put(Content content, long now) {
            if (state == EdgeState.OFFLINE) {
                return;
            }

            cache.put(
                content.path(),
                new CacheEntry(content, now)
            );

            while (cache.size() > capacity) {
                String oldest = cache.keySet().iterator().next();
                cache.remove(oldest);
                evictions++;
            }
        }

        boolean invalidate(String path) {
            return cache.remove(path) != null;
        }

        int hits() {
            return hits;
        }

        int misses() {
            return misses;
        }

        int stale() {
            return stale;
        }

        int evictions() {
            return evictions;
        }
    }

    static final class RoutingPolicy {
        private final Map<String, Map<String, Integer>> distances =
            new HashMap<>();

        void setDistance(
            String a,
            String b,
            int latencyMs
        ) {
            if (latencyMs < 0) {
                throw new ValidationException(
                    "Geographic latency cannot be negative"
                );
            }

            distances
                .computeIfAbsent(a, key -> new HashMap<>())
                .put(b, latencyMs);

            distances
                .computeIfAbsent(b, key -> new HashMap<>())
                .put(a, latencyMs);
        }

        int distance(String a, String b) {
            if (a.equals(b)) {
                return 0;
            }

            return distances
                .getOrDefault(a, Map.of())
                .getOrDefault(b, 100);
        }

        EdgeNode select(
            String clientRegion,
            List<EdgeNode> edges
        ) {
            return edges.stream()
                .filter(edge -> edge.state() != EdgeState.OFFLINE)
                .min(Comparator.comparingInt(
                    edge -> score(clientRegion, edge)
                ))
                .orElseThrow(() ->
                    new IllegalStateException(
                        "No available edge node"
                    )
                );
        }

        private int score(
            String clientRegion,
            EdgeNode edge
        ) {
            int healthPenalty =
                edge.state() == EdgeState.DEGRADED
                    ? 1000
                    : 0;

            return distance(clientRegion, edge.region())
                + edge.latencyMs()
                + healthPenalty;
        }
    }

    static final class CdnService {
        private final OriginService origin;
        private final CachePolicy cachePolicy;
        private final RoutingPolicy routingPolicy;

        private final List<EdgeNode> edges = new ArrayList<>();

        private int requests;
        private int originFetches;
        private int invalidRequests;

        CdnService(
            OriginService origin,
            CachePolicy cachePolicy,
            RoutingPolicy routingPolicy
        ) {
            this.origin = origin;
            this.cachePolicy = cachePolicy;
            this.routingPolicy = routingPolicy;
        }

        void addEdge(EdgeNode edge) {
            edges.add(edge);
        }

        RequestResult request(
            String path,
            String clientRegion,
            long now,
            boolean authenticated
        ) {
            requests++;

            if (!validPath(path)) {
                invalidRequests++;
                return new RequestResult(
                    CacheStatus.BYPASS,
                    "",
                    0,
                    null,
                    "Rejected malformed path"
                );
            }

            if (cachePolicy.shouldBypass(path, authenticated)) {
                if (path.startsWith("/private/")
                        && !authenticated) {
                    return new RequestResult(
                        CacheStatus.BYPASS,
                        "",
                        0,
                        null,
                        "Authentication required"
                    );
                }
            }

            boolean privatePath = path.startsWith("/private/");

            EdgeNode edge;

            try {
                edge = routingPolicy.select(
                    clientRegion,
                    edges
                );
            } catch (RuntimeException ex) {
                return new RequestResult(
                    CacheStatus.ORIGIN_ERROR,
                    "",
                    0,
                    null,
                    ex.getMessage()
                );
            }

            if (!privatePath) {
                Optional<Content> cached =
                    edge.lookup(path, now);

                if (cached.isPresent()) {
                    Content value = cached.get();

                    return new RequestResult(
                        CacheStatus.HIT,
                        edge.id(),
                        routingPolicy.distance(
                            clientRegion,
                            edge.region()
                        ) + edge.latencyMs(),
                        value.version(),
                        "Served from edge cache"
                    );
                }
            }

            try {
                Content content = origin.fetch(path);
                originFetches++;

                if (!privatePath
                        && cachePolicy.shouldCache(content)) {
                    edge.put(content, now);
                }

                return new RequestResult(
                    privatePath
                        ? CacheStatus.BYPASS
                        : CacheStatus.MISS,
                    edge.id(),
                    routingPolicy.distance(
                        clientRegion,
                        edge.region()
                    ) + edge.latencyMs() + 80,
                    content.version(),
                    privatePath
                        ? "Private origin response"
                        : "Origin response cached"
                );
            } catch (
                OriginUnavailableException
                | ContentNotFoundException ex
            ) {
                return new RequestResult(
                    CacheStatus.ORIGIN_ERROR,
                    edge.id(),
                    routingPolicy.distance(
                        clientRegion,
                        edge.region()
                    ) + edge.latencyMs(),
                    null,
                    ex.getMessage()
                );
            }
        }

        int invalidate(String path) {
            int affected = 0;

            for (EdgeNode edge : edges) {
                if (edge.invalidate(path)) {
                    affected++;
                }
            }

            return affected;
        }

        String metrics() {
            int hits = edges.stream()
                .mapToInt(EdgeNode::hits)
                .sum();

            int misses = edges.stream()
                .mapToInt(EdgeNode::misses)
                .sum();

            int stale = edges.stream()
                .mapToInt(EdgeNode::stale)
                .sum();

            int evictions = edges.stream()
                .mapToInt(EdgeNode::evictions)
                .sum();

            double hitRatio =
                requests == 0
                    ? 0.0
                    : (double) hits / requests;

            return String.format(
                "requests=%d hits=%d misses=%d stale=%d " +
                "evictions=%d originFetches=%d invalidRequests=%d " +
                "hitRatio=%.3f",
                requests,
                hits,
                misses,
                stale,
                evictions,
                originFetches,
                invalidRequests,
                hitRatio
            );
        }

        private boolean validPath(String path) {
            return path != null
                && path.startsWith("/")
                && !path.contains("..")
                && path.length() <= 2048;
        }
    }

    public static void main(String[] args) {
        try {
            OriginService origin = new OriginService();

            origin.publish(
                "/static/app.js",
                "console.log('release-1');",
                "application/javascript",
                30,
                true
            );

            origin.publish(
                "/static/logo.svg",
                "<svg>logo</svg>",
                "image/svg+xml",
                60,
                true
            );

            origin.publish(
                "/private/audit.json",
                "{\"classification\":\"internal\"}",
                "application/json",
                60,
                false
            );

            RoutingPolicy routing = new RoutingPolicy();

            routing.setDistance("DEL", "BOM", 18);
            routing.setDistance("DEL", "SIN", 65);
            routing.setDistance("DEL", "LON", 120);
            routing.setDistance("BOM", "SIN", 55);
            routing.setDistance("BOM", "LON", 130);
            routing.setDistance("SIN", "LON", 160);

            CdnService cdn = new CdnService(
                origin,
                new StandardCachePolicy(),
                routing
            );

            EdgeNode delhi =
                new EdgeNode("edge-delhi", "DEL", 8, 2);

            cdn.addEdge(delhi);
            cdn.addEdge(
                new EdgeNode("edge-mumbai", "BOM", 12, 2)
            );
            cdn.addEdge(
                new EdgeNode("edge-singapore", "SIN", 10, 2)
            );
            cdn.addEdge(
                new EdgeNode("edge-london", "LON", 18, 2)
            );

            long t0 = 1_000L;

            RequestResult first =
                cdn.request(
                    "/static/app.js",
                    "DEL",
                    t0,
                    false
                );

            RequestResult second =
                cdn.request(
                    "/static/app.js",
                    "DEL",
                    t0 + 2,
                    false
                );

            RequestResult privateResult =
                cdn.request(
                    "/private/audit.json",
                    "DEL",
                    t0 + 3,
                    true
                );

            System.out.println("first: " + first);
            System.out.println("second: " + second);
            System.out.println("private: " + privateResult);

            if (second.status() != CacheStatus.HIT) {
                throw new IllegalStateException(
                    "Second request should be a cache hit"
                );
            }

            // Degraded edges remain eligible but receive a large routing
            // penalty, allowing another healthy edge to win selection.
            delhi.setState(EdgeState.DEGRADED);

            RequestResult failover =
                cdn.request(
                    "/static/logo.svg",
                    "DEL",
                    t0 + 4,
                    false
                );

            System.out.println("health-aware request: " + failover);

            // New origin version requires explicit invalidation when
            // immediate propagation is required.
            origin.publish(
                "/static/app.js",
                "console.log('release-2');",
                "application/javascript",
                30,
                true
            );

            int invalidated =
                cdn.invalidate("/static/app.js");

            System.out.println(
                "invalidated copies: " + invalidated
            );

            RequestResult refreshed =
                cdn.request(
                    "/static/app.js",
                    "DEL",
                    t0 + 5,
                    false
                );

            System.out.println("refreshed: " + refreshed);

            if (!Integer.valueOf(2).equals(refreshed.version())) {
                throw new IllegalStateException(
                    "Expected origin version 2 after invalidation"
                );
            }

            origin.setAvailable(false);

            RequestResult failure =
                cdn.request(
                    "/unknown.json",
                    "BOM",
                    t0 + 100,
                    false
                );

            System.out.println("origin failure: " + failure);
            System.out.println(cdn.metrics());

        } catch (RuntimeException ex) {
            System.err.println(
                "CDN governance failure: " + ex.getMessage()
            );
            System.exit(1);
        }
    }
}
