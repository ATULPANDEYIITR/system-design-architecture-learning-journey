import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class CacheStrategies {

    record Product(
        int id,
        String name,
        double price,
        int stock,
        long version
    ) {
        Product {
            if (id <= 0) {
                throw new IllegalArgumentException("id must be positive");
            }
            if (!Double.isFinite(price) || price < 0) {
                throw new IllegalArgumentException(
                    "price must be finite and non-negative"
                );
            }
            if (stock < 0) {
                throw new IllegalArgumentException(
                    "stock cannot be negative"
                );
            }
        }

        Product withPriceAndStock(double newPrice, int newStock) {
            return new Product(
                id,
                name,
                newPrice,
                newStock,
                version
            );
        }
    }

    enum StrategyType {
        CACHE_ASIDE,
        READ_THROUGH,
        WRITE_THROUGH
    }

    static final class CacheEntry<T> {
        private final T value;
        private final Instant expiresAt;

        CacheEntry(T value, Instant expiresAt) {
            this.value = value;
            this.expiresAt = expiresAt;
        }

        boolean expired(Instant now) {
            return expiresAt != null && !now.isBefore(expiresAt);
        }

        T value() {
            return value;
        }
    }

    static final class ProductRepository {
        private final Map<Integer, Product> products = new HashMap<>();
        private long reads;
        private long writes;

        ProductRepository() {
            products.put(
                101,
                new Product(
                    101,
                    "Mechanical Keyboard",
                    89.99,
                    42,
                    1
                )
            );
            products.put(
                102,
                new Product(
                    102,
                    "USB-C Dock",
                    129.50,
                    17,
                    1
                )
            );
            products.put(
                103,
                new Product(
                    103,
                    "Noise-Cancelling Headphones",
                    199.00,
                    9,
                    1
                )
            );
        }

        Optional<Product> find(int id) {
            reads++;
            return Optional.ofNullable(products.get(id));
        }

        Product save(Product product) {
            Product existing = products.get(product.id());

            long nextVersion =
                existing == null ? 1 : existing.version() + 1;

            Product persisted = new Product(
                product.id(),
                product.name(),
                product.price(),
                product.stock(),
                nextVersion
            );

            products.put(persisted.id(), persisted);
            writes++;

            return persisted;
        }
    }

    static final class ProductCache {
        private final Map<Integer, CacheEntry<Product>> entries =
            new HashMap<>();

        private long hits;
        private long misses;
        private long writes;

        Optional<Product> get(int key) {
            CacheEntry<Product> entry = entries.get(key);

            if (entry == null) {
                misses++;
                return Optional.empty();
            }

            if (entry.expired(Instant.now())) {
                entries.remove(key);
                misses++;
                return Optional.empty();
            }

            hits++;
            return Optional.of(entry.value());
        }

        void put(
            int key,
            Product product,
            Duration ttl
        ) {
            Instant expiration =
                ttl == null ? null : Instant.now().plus(ttl);

            entries.put(
                key,
                new CacheEntry<>(product, expiration)
            );

            writes++;
        }

        void invalidate(int key) {
            entries.remove(key);
        }

        String metrics() {
            return "hits=" + hits
                + ", misses=" + misses
                + ", writes=" + writes
                + ", entries=" + entries.size();
        }
    }

    interface ProductReader {
        Optional<Product> get(int productId);
    }

    interface ProductWriter {
        Product write(Product product);
    }

    static final class CacheAsideService
        implements ProductReader, ProductWriter {

        private final ProductRepository repository;
        private final ProductCache cache;
        private final Duration ttl;

        CacheAsideService(
            ProductRepository repository,
            ProductCache cache,
            Duration ttl
        ) {
            this.repository = repository;
            this.cache = cache;
            this.ttl = ttl;
        }

        @Override
        public Optional<Product> get(int productId) {
            Optional<Product> cached = cache.get(productId);

            if (cached.isPresent()) {
                return cached;
            }

            Optional<Product> source =
                repository.find(productId);

            source.ifPresent(
                product -> cache.put(productId, product, ttl)
            );

            return source;
        }

        @Override
        public Product write(Product product) {
            Product persisted = repository.save(product);

            // Invalidation is part of the application-level cache-aside
            // policy. The following read reconstructs the cache entry.
            cache.invalidate(product.id());

            return persisted;
        }
    }

    static final class ReadThroughService
        implements ProductReader {

        private final ProductRepository repository;
        private final ProductCache cache;
        private final Duration ttl;

        ReadThroughService(
            ProductRepository repository,
            ProductCache cache,
            Duration ttl
        ) {
            this.repository = repository;
            this.cache = cache;
            this.ttl = ttl;
        }

        @Override
        public Optional<Product> get(int productId) {
            Optional<Product> cached = cache.get(productId);

            if (cached.isPresent()) {
                return cached;
            }

            Optional<Product> source =
                repository.find(productId);

            source.ifPresent(
                product -> cache.put(productId, product, ttl)
            );

            return source;
        }
    }

    static final class WriteThroughService
        implements ProductReader, ProductWriter {

        private final ProductRepository repository;
        private final ProductCache cache;
        private final Duration ttl;

        WriteThroughService(
            ProductRepository repository,
            ProductCache cache,
            Duration ttl
        ) {
            this.repository = repository;
            this.cache = cache;
            this.ttl = ttl;
        }

        @Override
        public Product write(Product product) {
            // Persistence remains authoritative. The cache is changed only
            // after repository validation and successful persistence.
            Product persisted = repository.save(product);
            cache.put(persisted.id(), persisted, ttl);
            return persisted;
        }

        @Override
        public Optional<Product> get(int productId) {
            return cache.get(productId);
        }
    }

    static final class CachePolicy {
        private final StrategyType strategy;
        private final Duration ttl;
        private final boolean cacheMissingValues;

        CachePolicy(
            StrategyType strategy,
            Duration ttl,
            boolean cacheMissingValues
        ) {
            if (ttl != null && ttl.isNegative()) {
                throw new IllegalArgumentException(
                    "TTL cannot be negative"
                );
            }

            this.strategy = strategy;
            this.ttl = ttl;
            this.cacheMissingValues = cacheMissingValues;
        }

        StrategyType strategy() {
            return strategy;
        }

        Duration ttl() {
            return ttl;
        }

        boolean cacheMissingValues() {
            return cacheMissingValues;
        }
    }

    static void printProduct(
        String label,
        Optional<Product> product
    ) {
        if (product.isEmpty()) {
            System.out.println(label + ": NOT FOUND");
            return;
        }

        Product p = product.get();

        System.out.printf(
            "%s: %s | price=%.2f | stock=%d | version=%d%n",
            label,
            p.name(),
            p.price(),
            p.stock(),
            p.version()
        );
    }

    static void demonstrateCacheAside() {
        System.out.println("\n=== Cache-aside ===");

        ProductRepository repository =
            new ProductRepository();

        ProductCache cache = new ProductCache();

        CacheAsideService service =
            new CacheAsideService(
                repository,
                cache,
                Duration.ofSeconds(30)
            );

        printProduct("First read", service.get(101));
        printProduct("Second read", service.get(101));

        service.write(
            new Product(
                101,
                "Mechanical Keyboard",
                94.99,
                40,
                0
            )
        );

        printProduct("Read after invalidation", service.get(101));

        System.out.println("Cache: " + cache.metrics());
        System.out.println(
            "Repository reads: " + repository.reads
        );
    }

    static void demonstrateReadThrough() {
        System.out.println("\n=== Read-through ===");

        ProductRepository repository =
            new ProductRepository();

        ProductCache cache = new ProductCache();

        ReadThroughService service =
            new ReadThroughService(
                repository,
                cache,
                Duration.ofSeconds(30)
            );

        printProduct("First read", service.get(102));
        printProduct("Second read", service.get(102));
        printProduct("Unknown product", service.get(999));

        System.out.println("Cache: " + cache.metrics());
        System.out.println(
            "Repository reads: " + repository.reads
        );
    }

    static void demonstrateWriteThrough() {
        System.out.println("\n=== Write-through ===");

        ProductRepository repository =
            new ProductRepository();

        ProductCache cache = new ProductCache();

        WriteThroughService service =
            new WriteThroughService(
                repository,
                cache,
                Duration.ofSeconds(30)
            );

        Product persisted = service.write(
            new Product(
                103,
                "Noise-Cancelling Headphones",
                184.00,
                8,
                0
            )
        );

        printProduct(
            "Persisted product",
            Optional.of(persisted)
        );

        printProduct(
            "Immediate cache read",
            service.get(103)
        );

        System.out.println("Cache: " + cache.metrics());
    }

    static void demonstrateTtl() throws InterruptedException {
        System.out.println("\n=== TTL expiration ===");

        ProductCache cache = new ProductCache();

        cache.put(
            700,
            new Product(
                700,
                "Short-Lived Catalog Entry",
                15.00,
                4,
                1
            ),
            Duration.ofMillis(40)
        );

        printProduct(
            "Immediately",
            cache.get(700)
        );

        Thread.sleep(60);

        printProduct(
            "After expiration",
            cache.get(700)
        );
    }

    static void demonstrateFailureHandling() {
        System.out.println("\n=== Write validation ===");

        ProductRepository repository =
            new ProductRepository();

        ProductCache cache = new ProductCache();

        WriteThroughService service =
            new WriteThroughService(
                repository,
                cache,
                Duration.ofSeconds(30)
            );

        service.write(
            new Product(
                101,
                "Mechanical Keyboard",
                95.00,
                39,
                0
            )
        );

        try {
            service.write(
                new Product(
                    101,
                    "Mechanical Keyboard",
                    -1.00,
                    39,
                    0
                )
            );
        } catch (IllegalArgumentException error) {
            System.out.println(
                "Invalid write rejected: "
                    + error.getMessage()
            );
        }

        printProduct(
            "Last valid cached state",
            service.get(101)
        );
    }

    static void comparePolicies() {
        System.out.println("\n=== Policy distinctions ===");

        CachePolicy cacheAside = new CachePolicy(
            StrategyType.CACHE_ASIDE,
            Duration.ofSeconds(30),
            false
        );

        CachePolicy readThrough = new CachePolicy(
            StrategyType.READ_THROUGH,
            Duration.ofSeconds(30),
            false
        );

        CachePolicy writeThrough = new CachePolicy(
            StrategyType.WRITE_THROUGH,
            Duration.ofSeconds(30),
            false
        );

        System.out.println(
            cacheAside.strategy()
                + ": application owns cache population."
        );

        System.out.println(
            readThrough.strategy()
                + ": cache layer owns miss loading."
        );

        System.out.println(
            writeThrough.strategy()
                + ": successful writes update source and cache."
        );

        System.out.println(
            "Negative-value caching enabled for read-through: "
                + readThrough.cacheMissingValues()
        );
    }

    static void runAssertions() {
        ProductRepository repository =
            new ProductRepository();

        ProductCache cache = new ProductCache();

        CacheAsideService service =
            new CacheAsideService(
                repository,
                cache,
                Duration.ofSeconds(30)
            );

        if (service.get(101).isEmpty()) {
            throw new AssertionError(
                "Known product must be returned"
            );
        }

        if (service.get(101).isEmpty()) {
            throw new AssertionError(
                "Cached product must remain readable"
            );
        }

        if (repository.reads != 1) {
            throw new AssertionError(
                "Cache hit should avoid second source read"
            );
        }

        service.write(
            new Product(
                101,
                "Mechanical Keyboard",
                99.00,
                38,
                0
            )
        );

        Product refreshed =
            service.get(101).orElseThrow();

        if (refreshed.price() != 99.00) {
            throw new AssertionError(
                "Invalidation must reveal persisted value"
            );
        }

        System.out.println(
            "\nAll Java assertions passed."
        );
    }

    public static void main(String[] args)
        throws InterruptedException {

        System.out.println(
            "CACHE STRATEGIES: CACHE-ASIDE, READ-THROUGH, WRITE-THROUGH"
        );

        demonstrateCacheAside();
        demonstrateReadThrough();
        demonstrateWriteThrough();
        demonstrateTtl();
        demonstrateFailureHandling();
        comparePolicies();
        runAssertions();
    }
}
