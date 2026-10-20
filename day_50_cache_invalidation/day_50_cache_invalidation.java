import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public class CacheInvalidationDemo {

    enum InvalidationStrategy {
        EXPLICIT,
        TTL,
        VERSION,
        WRITE_THROUGH,
        WRITE_INVALIDATE,
        STALE_WHILE_REVALIDATE
    }

    record Product(
        int id,
        String name,
        double price,
        long version
    ) {
        Product {
            if (id <= 0) {
                throw new IllegalArgumentException("id must be positive");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            if (!Double.isFinite(price) || price < 0) {
                throw new IllegalArgumentException("invalid price");
            }
            if (version < 1) {
                throw new IllegalArgumentException("version must be positive");
            }
        }

        Product withPrice(double newPrice) {
            return new Product(id, name, newPrice, version + 1);
        }
    }

    record CacheEntry<T>(
        T value,
        long version,
        long expiresAtNanos
    ) {
        boolean expired(long nowNanos) {
            return expiresAtNanos != Long.MAX_VALUE
                    && nowNanos >= expiresAtNanos;
        }
    }

    interface Repository<T> {
        T find(int id);

        T update(int id, T value);
    }

    static final class ProductRepository implements Repository<Product> {
        private final Map<Integer, Product> products = new HashMap<>();

        ProductRepository() {
            products.put(101, new Product(101, "Keyboard", 2400.0, 1));
            products.put(102, new Product(102, "Monitor", 18500.0, 1));
        }

        @Override
        public synchronized Product find(int id) {
            Product product = products.get(id);

            if (product == null) {
                throw new IllegalArgumentException(
                    "Product " + id + " not found"
                );
            }

            return product;
        }

        @Override
        public synchronized Product update(int id, Product value) {
            Objects.requireNonNull(value, "value");

            if (!products.containsKey(id)) {
                throw new IllegalArgumentException(
                    "Product " + id + " not found"
                );
            }

            products.put(id, value);
            return value;
        }

        synchronized Product updatePrice(int id, double price) {
            if (!Double.isFinite(price) || price < 0) {
                throw new IllegalArgumentException(
                    "price must be a non-negative finite number"
                );
            }

            Product current = find(id);
            return update(id, current.withPrice(price));
        }
    }

    static final class VersionedCache<T> {
        private final Map<String, CacheEntry<T>> entries =
            new ConcurrentHashMap<>();

        void put(
            String key,
            T value,
            long version,
            Duration ttl
        ) {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(value, "value");

            if (key.isBlank()) {
                throw new IllegalArgumentException("key is blank");
            }

            if (version < 0) {
                throw new IllegalArgumentException(
                    "version cannot be negative"
                );
            }

            long expiresAt = ttl == null
                ? Long.MAX_VALUE
                : System.nanoTime() + validateTtl(ttl);

            entries.compute(key, (ignored, current) -> {
                if (current == null || version >= current.version()) {
                    return new CacheEntry<>(value, version, expiresAt);
                }

                // An older representation must never overwrite a newer one.
                return current;
            });
        }

        Optional<CacheEntry<T>> get(String key) {
            CacheEntry<T> entry = entries.get(key);

            if (entry == null) {
                return Optional.empty();
            }

            if (entry.expired(System.nanoTime())) {
                entries.remove(key, entry);
                return Optional.empty();
            }

            return Optional.of(entry);
        }

        void invalidate(String key) {
            entries.remove(key);
        }

        void invalidatePrefix(String prefix) {
            entries.keySet().removeIf(key -> key.startsWith(prefix));
        }

        private long validateTtl(Duration ttl) {
            if (ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException(
                    "TTL must be positive"
                );
            }

            return ttl.toNanos();
        }
    }

    static final class ProductService {
        private final ProductRepository repository;
        private final VersionedCache<Product> cache;

        ProductService(
            ProductRepository repository,
            VersionedCache<Product> cache
        ) {
            this.repository = repository;
            this.cache = cache;
        }

        Product find(int id) {
            String key = key(id);

            Optional<CacheEntry<Product>> cached = cache.get(key);

            if (cached.isPresent()) {
                return cached.get().value();
            }

            Product product = repository.find(id);

            cache.put(
                key,
                product,
                product.version(),
                Duration.ofSeconds(5)
            );

            return product;
        }

        Product updatePrice(int id, double price) {
            Product updated = repository.updatePrice(id, price);

            /*
             * The write succeeded in the authoritative store. Removing the
             * old representation is safer than guessing which fields changed.
             */
            cache.invalidate(key(id));

            return updated;
        }

        Product findVersionAware(int id) {
            String key = key(id);
            Product current = repository.find(id);

            Optional<CacheEntry<Product>> cached = cache.get(key);

            if (cached.isEmpty()
                || cached.get().version() < current.version()) {

                cache.put(
                    key,
                    current,
                    current.version(),
                    Duration.ofSeconds(5)
                );

                return current;
            }

            return cached.get().value();
        }

        private static String key(int id) {
            if (id <= 0) {
                throw new IllegalArgumentException(
                    "id must be positive"
                );
            }

            return "product:" + id;
        }
    }

    public static void main(String[] args)
        throws InterruptedException {

        ProductRepository repository = new ProductRepository();
        VersionedCache<Product> cache = new VersionedCache<>();
        ProductService service = new ProductService(repository, cache);

        System.out.println("First read: " + service.find(101));
        System.out.println("Cached read: " + service.find(101));

        Product updated = service.updatePrice(101, 2600.0);
        System.out.println("Updated: " + updated);

        System.out.println(
            "After explicit invalidation: " + service.find(101)
        );

        System.out.println(
            "Version-aware read: " + service.findVersionAware(101)
        );

        try {
            service.updatePrice(101, -10);
        } catch (IllegalArgumentException error) {
            System.out.println(
                "Expected validation failure: " + error.getMessage()
            );
        }

        cache.invalidatePrefix("product:");
        System.out.println("Product cache namespace invalidated.");

        Product temporary = repository.find(102);

        cache.put(
            "product:temporary",
            temporary,
            temporary.version(),
            Duration.ofMillis(50)
        );

        System.out.println(
            "Before TTL expiry: "
                + cache.get("product:temporary").isPresent()
        );

        Thread.sleep(70);

        System.out.println(
            "After TTL expiry: "
                + cache.get("product:temporary").isPresent()
        );
    }
}
