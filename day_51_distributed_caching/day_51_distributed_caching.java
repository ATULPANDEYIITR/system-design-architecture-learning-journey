import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;

public class DistributedCacheGovernance {

    enum Backend {
        REDIS,
        MEMCACHED
    }

    enum NodeState {
        HEALTHY,
        FAILED,
        DRAINING
    }

    enum CachePolicy {
        CACHE_ASIDE,
        WRITE_THROUGH
    }

    record Product(String id, String name, int price) {
        Product {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(name, "name");

            if (id.isBlank() || name.isBlank()) {
                throw new IllegalArgumentException("Product fields cannot be blank");
            }

            if (price < 0) {
                throw new IllegalArgumentException("Price cannot be negative");
            }
        }
    }

    record CacheRecord<T>(
            T value,
            long version,
            Instant expiresAt
    ) {
        boolean expired(Instant now) {
            return !now.isBefore(expiresAt);
        }
    }

    static final class CacheUnavailableException extends RuntimeException {
        CacheUnavailableException(String message) {
            super(message);
        }
    }

    static final class ProductRepository {
        private final Map<String, Product> products = new HashMap<>();

        ProductRepository() {
            products.put("p100", new Product("p100", "Edge Router", 249));
            products.put("p200", new Product("p200", "Storage Node", 799));
        }

        synchronized Product find(String id) {
            Product product = products.get(id);

            if (product == null) {
                throw new IllegalArgumentException(
                    "Product does not exist: " + id
                );
            }

            return product;
        }

        synchronized Product updatePrice(String id, int price) {
            Product current = find(id);
            Product updated = new Product(id, current.name(), price);
            products.put(id, updated);
            return updated;
        }
    }

    static final class CacheNode {
        private final String name;
        private final Backend backend;
        private final int capacity;
        private NodeState state = NodeState.HEALTHY;

        private final Map<String, CacheRecord<Product>> entries =
            new HashMap<>();

        private long hits;
        private long misses;

        CacheNode(String name, Backend backend, int capacity) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Node name is required");
            }
            if (capacity <= 0) {
                throw new IllegalArgumentException("Capacity must be positive");
            }

            this.name = name;
            this.backend = backend;
            this.capacity = capacity;
        }

        String name() {
            return name;
        }

        Backend backend() {
            return backend;
        }

        NodeState state() {
            return state;
        }

        void changeState(NodeState newState) {
            this.state = Objects.requireNonNull(newState);
        }

        synchronized Optional<Product> get(String key, Instant now) {
            requireReadable();

            CacheRecord<Product> record = entries.get(key);

            if (record == null) {
                misses++;
                return Optional.empty();
            }

            if (record.expired(now)) {
                entries.remove(key);
                misses++;
                return Optional.empty();
            }

            hits++;
            return Optional.of(record.value());
        }

        synchronized void put(
            String key,
            Product value,
            long version,
            Duration ttl
        ) {
            requireWritable();

            if (ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("TTL must be positive");
            }

            if (entries.size() >= capacity && !entries.containsKey(key)) {
                String victim = entries.keySet()
                    .stream()
                    .min(Comparator.naturalOrder())
                    .orElseThrow();

                entries.remove(victim);
            }

            entries.put(
                key,
                new CacheRecord<>(
                    value,
                    version,
                    Instant.now().plus(ttl)
                )
            );
        }

        synchronized void invalidate(String key) {
            requireWritable();
            entries.remove(key);
        }

        synchronized long hits() {
            return hits;
        }

        synchronized long misses() {
            return misses;
        }

        private void requireReadable() {
            if (state != NodeState.HEALTHY) {
                throw new CacheUnavailableException(
                    "Node cannot serve reads: " + name
                );
            }
        }

        private void requireWritable() {
            if (state != NodeState.HEALTHY) {
                throw new CacheUnavailableException(
                    "Node cannot accept writes: " + name
                );
            }
        }
    }

    static final class ConsistentHashRing {
        private final int replicas;
        private final TreeMap<Long, CacheNode> ring = new TreeMap<>();

        ConsistentHashRing(int replicas) {
            if (replicas <= 0) {
                throw new IllegalArgumentException(
                    "Replica count must be positive"
                );
            }

            this.replicas = replicas;
        }

        synchronized void add(CacheNode node) {
            for (int replica = 0; replica < replicas; replica++) {
                ring.put(
                    hash(node.name() + ":" + replica),
                    node
                );
            }
        }

        synchronized CacheNode locate(String key) {
            if (ring.isEmpty()) {
                throw new CacheUnavailableException(
                    "No cache nodes configured"
                );
            }

            long hash = hash(key);
            Map.Entry<Long, CacheNode> entry = ring.ceilingEntry(hash);

            return entry != null
                ? entry.getValue()
                : ring.firstEntry().getValue();
        }

        private static long hash(String value) {
            long hash = 1125899906842597L;

            for (char character : value.toCharArray()) {
                hash = 31 * hash + character;
            }

            return hash & Long.MAX_VALUE;
        }
    }

    static final class CacheService {
        private final ConsistentHashRing ring;
        private final CachePolicy policy;

        CacheService(ConsistentHashRing ring, CachePolicy policy) {
            this.ring = Objects.requireNonNull(ring);
            this.policy = Objects.requireNonNull(policy);
        }

        Product getOrLoad(
            String key,
            java.util.function.Supplier<Product> loader,
            Duration ttl
        ) {
            CacheNode node = ring.locate(key);

            try {
                Optional<Product> cached =
                    node.get(key, Instant.now());

                if (cached.isPresent()) {
                    return cached.get();
                }
            } catch (CacheUnavailableException ignored) {
                // Cache availability must not become source-of-truth failure.
            }

            Product value = loader.get();

            try {
                node.put(key, value, 1, ttl);
            } catch (CacheUnavailableException ignored) {
                // The authoritative repository result remains valid.
            }

            return value;
        }

        void invalidate(String key) {
            CacheNode node = ring.locate(key);

            try {
                node.invalidate(key);
            } catch (CacheUnavailableException ignored) {
                // A failed cache is allowed to recover without blocking writes.
            }
        }

        CachePolicy policy() {
            return policy;
        }
    }

    static final class MergeLikeWorkflow {
        /*
         * This service models a cache write policy explicitly. A production
         * system should choose one policy based on consistency requirements
         * instead of mixing policies accidentally.
         */
        private final ProductRepository repository;
        private final CacheService cache;
        private long version;

        MergeLikeWorkflow(
            ProductRepository repository,
            CacheService cache
        ) {
            this.repository = repository;
            this.cache = cache;
        }

        Product updateProduct(
            String id,
            int price,
            Duration ttl
        ) {
            Product updated = repository.updatePrice(id, price);
            version++;

            cache.invalidate("product:" + id);

            return updated;
        }

        long version() {
            return version;
        }
    }

    public static void main(String[] args) {
        ProductRepository repository = new ProductRepository();

        CacheNode redisA =
            new CacheNode("redis-a", Backend.REDIS, 100);

        CacheNode redisB =
            new CacheNode("redis-b", Backend.REDIS, 100);

        CacheNode memcachedA =
            new CacheNode("memcached-a", Backend.MEMCACHED, 100);

        ConsistentHashRing ring = new ConsistentHashRing(128);
        ring.add(redisA);
        ring.add(redisB);
        ring.add(memcachedA);

        CacheService cache = new CacheService(
            ring,
            CachePolicy.CACHE_ASIDE
        );

        Product first = cache.getOrLoad(
            "product:p100",
            () -> repository.find("p100"),
            Duration.ofSeconds(30)
        );

        Product second = cache.getOrLoad(
            "product:p100",
            () -> repository.find("p100"),
            Duration.ofSeconds(30)
        );

        System.out.println("First request: " + first);
        System.out.println("Second request: " + second);
        System.out.println("Policy: " + cache.policy());

        MergeLikeWorkflow workflow =
            new MergeLikeWorkflow(repository, cache);

        Product updated = workflow.updateProduct(
            "p100",
            299,
            Duration.ofSeconds(30)
        );

        System.out.println("Updated source of truth: " + updated);

        Product refreshed = cache.getOrLoad(
            "product:p100",
            () -> repository.find("p100"),
            Duration.ofSeconds(30)
        );

        System.out.println("Refreshed cache value: " + refreshed);

        CacheNode failedNode = ring.locate("product:p200");
        failedNode.changeState(NodeState.FAILED);

        Product failureFallback = cache.getOrLoad(
            "product:p200",
            () -> repository.find("p200"),
            Duration.ofSeconds(30)
        );

        System.out.println("Failure fallback: " + failureFallback);

        failedNode.changeState(NodeState.HEALTHY);

        List<CacheNode> nodes =
            List.of(redisA, redisB, memcachedA);

        Map<String, Integer> distribution = new HashMap<>();

        for (int i = 0; i < 1000; i++) {
            CacheNode owner =
                ring.locate("product:" + i);

            distribution.merge(
                owner.name(),
                1,
                Integer::sum
            );
        }

        System.out.println("\nKey distribution:");

        List<String> nodeNames =
            new ArrayList<>(distribution.keySet());

        Collections.sort(nodeNames);

        for (String name : nodeNames) {
            System.out.println(
                name + ": " + distribution.get(name)
            );
        }

        System.out.println("\nNode statistics:");

        for (CacheNode node : nodes) {
            System.out.println(
                node.name()
                    + " ["
                    + node.backend()
                    + "] hits="
                    + node.hits()
                    + ", misses="
                    + node.misses()
            );
        }

        System.out.println(
            "Application update version: "
                + workflow.version()
        );
    }
}
