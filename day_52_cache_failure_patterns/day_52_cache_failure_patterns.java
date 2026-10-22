import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Pattern;

/**
 * Enterprise-oriented cache failure management model.
 *
 * The domain intentionally separates:
 * - cache access and refresh coordination
 * - negative caching for penetration
 * - reviewable refresh ownership for stampede control
 * - randomized expiration and stale serving for avalanche protection
 *
 * Java 17 records provide immutable domain values while ConcurrentHashMap
 * provides safe concurrent access without a global application lock.
 */
public class CacheFailurePatterns {

    enum FailurePattern {
        STAMPEDE,
        PENETRATION,
        AVALANCHE
    }

    enum CacheState {
        HIT,
        NEGATIVE_HIT,
        MISS,
        STALE
    }

    record Product(String id, String name, double price) {
        Product {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            if (price < 0) {
                throw new IllegalArgumentException("price cannot be negative");
            }
        }
    }

    record CacheEntry<T>(
        T value,
        long expiresAtNanos,
        boolean negative
    ) {
        boolean fresh(long now) {
            return expiresAtNanos > now;
        }

        boolean stale(long now, long staleGraceNanos) {
            return expiresAtNanos <= now
                && expiresAtNanos + staleGraceNanos > now;
        }
    }

    record CachePolicy(
        Duration ttl,
        Duration negativeTtl,
        Duration staleGrace,
        double jitterRatio,
        boolean rejectUnknownKeys
    ) {
        CachePolicy {
            Objects.requireNonNull(ttl);
            Objects.requireNonNull(negativeTtl);
            Objects.requireNonNull(staleGrace);

            if (ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("ttl must be positive");
            }
            if (negativeTtl.isZero() || negativeTtl.isNegative()) {
                throw new IllegalArgumentException(
                    "negativeTtl must be positive"
                );
            }
            if (staleGrace.isNegative()) {
                throw new IllegalArgumentException(
                    "staleGrace cannot be negative"
                );
            }
            if (jitterRatio < 0 || jitterRatio > 1) {
                throw new IllegalArgumentException(
                    "jitterRatio must be between 0 and 1"
                );
            }
        }
    }

    record CacheMetrics(
        long hits,
        long misses,
        long backendReads,
        long negativeHits,
        long rejectedPenetration,
        long deduplicatedRefreshes,
        long staleServed,
        long failures
    ) {
    }

    interface Repository<K, V> {
        Optional<V> find(K key);
    }

    static final class InMemoryProductRepository
        implements Repository<String, Product> {

        private final Map<String, Product> products =
            new ConcurrentHashMap<>();

        void save(Product product) {
            products.put(product.id(), product);
        }

        @Override
        public Optional<Product> find(String key) {
            return Optional.ofNullable(products.get(key));
        }
    }

    static final class CacheService<K, V> {
        private final Repository<K, V> repository;
        private final CachePolicy policy;
        private final Set<K> allowedKeys;

        private final Map<K, CacheEntry<V>> entries =
            new ConcurrentHashMap<>();

        /*
         * The future map is the Java equivalent of single-flight:
         * concurrent requests for one key share the same refresh Future.
         */
        private final Map<K, CompletableFuture<Optional<V>>> refreshes =
            new ConcurrentHashMap<>();

        private final AtomicLong hits = new AtomicLong();
        private final AtomicLong misses = new AtomicLong();
        private final AtomicLong backendReads = new AtomicLong();
        private final AtomicLong negativeHits = new AtomicLong();
        private final AtomicLong rejectedPenetration = new AtomicLong();
        private final AtomicLong deduplicatedRefreshes =
            new AtomicLong();
        private final AtomicLong staleServed = new AtomicLong();
        private final AtomicLong failures = new AtomicLong();

        CacheService(
            Repository<K, V> repository,
            CachePolicy policy,
            Set<K> allowedKeys
        ) {
            this.repository = Objects.requireNonNull(repository);
            this.policy = Objects.requireNonNull(policy);
            this.allowedKeys = Set.copyOf(allowedKeys);
        }

        Optional<V> get(K key) {
            validateKey(key);

            long now = System.nanoTime();
            CacheEntry<V> entry = entries.get(key);

            if (entry != null && entry.fresh(now)) {
                hits.incrementAndGet();

                if (entry.negative()) {
                    negativeHits.incrementAndGet();
                }

                return Optional.ofNullable(entry.value());
            }

            if (entry != null &&
                entry.stale(now, policy.staleGrace().toNanos())) {

                hits.incrementAndGet();
                staleServed.incrementAndGet();

                refreshAsync(key);

                return Optional.ofNullable(entry.value());
            }

            misses.incrementAndGet();
            return refreshAsync(key).join();
        }

        private void validateKey(K key) {
            if (key == null) {
                rejectedPenetration.incrementAndGet();
                throw new IllegalArgumentException("key is required");
            }

            if (policy.rejectUnknownKeys() &&
                !allowedKeys.contains(key)) {
                rejectedPenetration.incrementAndGet();
                throw new IllegalArgumentException(
                    "key rejected by admission policy"
                );
            }
        }

        private CompletableFuture<Optional<V>> refreshAsync(K key) {
            CompletableFuture<Optional<V>> existing = refreshes.get(key);

            if (existing != null) {
                deduplicatedRefreshes.incrementAndGet();
                return existing;
            }

            CompletableFuture<Optional<V>> created =
                CompletableFuture.supplyAsync(() -> load(key));

            CompletableFuture<Optional<V>> selected =
                refreshes.putIfAbsent(key, created);

            if (selected != null) {
                deduplicatedRefreshes.incrementAndGet();
                return selected;
            }

            created.whenComplete((ignored, failure) ->
                refreshes.remove(key, created)
            );

            return created;
        }

        private Optional<V> load(K key) {
            backendReads.incrementAndGet();

            try {
                Optional<V> value = repository.find(key);

                Duration baseTtl = value.isPresent()
                    ? policy.ttl()
                    : policy.negativeTtl();

                long ttlNanos = randomizedNanos(baseTtl);

                entries.put(
                    key,
                    new CacheEntry<>(
                        value.orElse(null),
                        System.nanoTime() + ttlNanos,
                        value.isEmpty()
                    )
                );

                return value;
            } catch (RuntimeException exception) {
                failures.incrementAndGet();
                throw exception;
            }
        }

        private long randomizedNanos(Duration duration) {
            long base = duration.toNanos();
            long delta = (long) (base * policy.jitterRatio());

            if (delta == 0) {
                return base;
            }

            long minimum = Math.max(1, base - delta);
            long maximum = Math.max(minimum, base + delta);

            return ThreadLocalRandom.current()
                .nextLong(minimum, maximum + 1);
        }

        void invalidate(K key) {
            entries.remove(key);
        }

        CacheMetrics metrics() {
            return new CacheMetrics(
                hits.get(),
                misses.get(),
                backendReads.get(),
                negativeHits.get(),
                rejectedPenetration.get(),
                deduplicatedRefreshes.get(),
                staleServed.get(),
                failures.get()
            );
        }
    }

    private static void penetrationScenario(
        CacheService<String, Product> cache
    ) {
        for (int i = 0; i < 100; i++) {
            cache.get("product:404");
        }
    }

    private static void stampedeScenario(
        CacheService<String, Product> cache
    ) throws InterruptedException {
        cache.get("product:100");

        Thread.sleep(550);

        List<Thread> workers = new ArrayList<>();

        for (int i = 0; i < 50; i++) {
            Thread worker = new Thread(
                () -> cache.get("product:100")
            );
            workers.add(worker);
            worker.start();
        }

        for (Thread worker : workers) {
            worker.join();
        }
    }

    private static void avalancheScenario(
        CacheService<String, Product> cache,
        InMemoryProductRepository repository
    ) {
        for (int i = 0; i < 100; i++) {
            String key = "product:" + (1000 + i);

            repository.save(
                new Product(
                    key,
                    "Generated Product " + i,
                    10.0 + i
                )
            );

            cache.get(key);
        }
    }

    public static void main(String[] args)
        throws InterruptedException {

        InMemoryProductRepository repository =
            new InMemoryProductRepository();

        repository.save(
            new Product("product:100", "Keyboard", 49.0)
        );

        repository.save(
            new Product("product:101", "Mouse", 29.0)
        );

        Set<String> allowedKeys = ConcurrentHashMap.newKeySet();
        allowedKeys.add("product:100");
        allowedKeys.add("product:101");
        allowedKeys.add("product:404");

        for (int i = 0; i < 100; i++) {
            allowedKeys.add("product:" + (1000 + i));
        }

        CachePolicy policy = new CachePolicy(
            Duration.ofMillis(500),
            Duration.ofMillis(200),
            Duration.ofMillis(700),
            0.20,
            true
        );

        CacheService<String, Product> cache =
            new CacheService<>(
                repository,
                policy,
                allowedKeys
            );

        penetrationScenario(cache);

        try {
            cache.get("../../../secret");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                "penetration admission rejected an invalid key"
            );
        }

        stampedeScenario(cache);
        avalancheScenario(cache, repository);

        CacheMetrics metrics = cache.metrics();

        long totalRequests = metrics.hits() + metrics.misses();
        double hitRate = totalRequests == 0
            ? 0
            : (double) metrics.hits() / totalRequests;

        System.out.println("CACHE FAILURE GOVERNANCE");
        System.out.println("hits: " + metrics.hits());
        System.out.println("misses: " + metrics.misses());
        System.out.println(
            "backend reads: " + metrics.backendReads()
        );
        System.out.println(
            "negative hits: " + metrics.negativeHits()
        );
        System.out.println(
            "rejected penetration: " +
            metrics.rejectedPenetration()
        );
        System.out.println(
            "deduplicated refreshes: " +
            metrics.deduplicatedRefreshes()
        );
        System.out.println(
            "stale served: " + metrics.staleServed()
        );
        System.out.println("failures: " + metrics.failures());
        System.out.printf(
            "hit rate: %.3f%n",
            hitRate
        );

        // A source-of-truth update explicitly invalidates the cached value.
        repository.save(
            new Product("product:100", "Keyboard Pro", 59.0)
        );
        cache.invalidate("product:100");

        Optional<Product> refreshed = cache.get("product:100");
        System.out.println(
            "refreshed product: " + refreshed.orElseThrow()
        );
    }
}
