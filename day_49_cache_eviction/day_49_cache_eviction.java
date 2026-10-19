import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class CacheEvictionEnterpriseDemo {

    enum Policy {
        LRU, LFU, FIFO, TTL
    }

    enum EntryState {
        ACTIVE, EXPIRED
    }

    record CacheKey(String service, String resource) {
        public CacheKey {
            if (service == null || service.isBlank()) {
                throw new IllegalArgumentException("service is required");
            }
            if (resource == null || resource.isBlank()) {
                throw new IllegalArgumentException("resource is required");
            }
        }
    }

    static final class CacheEntry<V> {
        private final CacheKey key;
        private V value;
        private final Instant insertedAt;
        private Instant lastAccess;
        private Instant expiresAt;
        private long frequency;
        private final long sequence;

        CacheEntry(
                CacheKey key,
                V value,
                Instant now,
                Instant expiresAt,
                long sequence
        ) {
            this.key = key;
            this.value = value;
            this.insertedAt = now;
            this.lastAccess = now;
            this.expiresAt = expiresAt;
            this.frequency = 1;
            this.sequence = sequence;
        }

        boolean isExpired(Instant now) {
            return expiresAt != null && !now.isBefore(expiresAt);
        }

        void touch(Instant now) {
            lastAccess = now;
            frequency++;
        }

        EntryState state(Instant now) {
            return isExpired(now) ? EntryState.EXPIRED : EntryState.ACTIVE;
        }
    }

    static final class CachePolicy {
        private final Policy policy;
        private final int capacity;
        private final Duration defaultTtl;

        CachePolicy(Policy policy, int capacity, Duration defaultTtl) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            if (policy == Policy.TTL &&
                    (defaultTtl == null || defaultTtl.isZero() || defaultTtl.isNegative())) {
                throw new IllegalArgumentException("TTL policy requires positive TTL");
            }

            this.policy = policy;
            this.capacity = capacity;
            this.defaultTtl = defaultTtl;
        }
    }

    static final class CacheService<V> {
        private final CachePolicy configuration;
        private final Map<CacheKey, CacheEntry<V>> entries = new HashMap<>();
        private long sequence;
        private long hits;
        private long misses;
        private long evictions;

        CacheService(CachePolicy configuration) {
            this.configuration = configuration;
        }

        private Instant now() {
            return Instant.now();
        }

        private void removeExpired(Instant current) {
            List<CacheKey> expired = entries.values().stream()
                    .filter(entry -> entry.isExpired(current))
                    .map(entry -> entry.key)
                    .toList();

            expired.forEach(key -> {
                entries.remove(key);
                evictions++;
            });
        }

        public Optional<V> get(CacheKey key) {
            Instant current = now();
            removeExpired(current);

            CacheEntry<V> entry = entries.get(key);

            if (entry == null) {
                misses++;
                return Optional.empty();
            }

            entry.touch(current);
            hits++;
            return Optional.of(entry.value);
        }

        public void put(CacheKey key, V value) {
            put(key, value, configuration.defaultTtl);
        }

        public void put(CacheKey key, V value, Duration ttl) {
            if (value == null) {
                throw new IllegalArgumentException("null values are not supported");
            }

            if (ttl != null && (ttl.isZero() || ttl.isNegative())) {
                throw new IllegalArgumentException("TTL must be positive");
            }

            Instant current = now();
            removeExpired(current);

            CacheEntry<V> existing = entries.get(key);

            if (existing != null) {
                existing.value = value;
                existing.touch(current);
                existing.expiresAt = ttl == null ? null : current.plus(ttl);
                return;
            }

            CacheEntry<V> entry = new CacheEntry<>(
                    key,
                    value,
                    current,
                    ttl == null ? null : current.plus(ttl),
                    ++sequence
            );

            entries.put(key, entry);

            if (entries.size() > configuration.capacity) {
                evict();
            }
        }

        private CacheEntry<V> chooseVictim() {
            Comparator<CacheEntry<V>> comparator;

            switch (configuration.policy) {
                case LRU:
                    comparator = Comparator
                            .comparing((CacheEntry<V> e) -> e.lastAccess)
                            .thenComparingLong(e -> e.sequence);
                    break;

                case LFU:
                    comparator = Comparator
                            .comparingLong((CacheEntry<V> e) -> e.frequency)
                            .thenComparing(e -> e.lastAccess)
                            .thenComparingLong(e -> e.sequence);
                    break;

                case FIFO:
                    comparator = Comparator.comparingLong(e -> e.sequence);
                    break;

                case TTL:
                    comparator = Comparator.comparing(
                            e -> e.expiresAt == null
                                    ? Instant.MAX
                                    : e.expiresAt
                    );
                    break;

                default:
                    throw new IllegalStateException("Unsupported policy");
            }

            return entries.values().stream()
                    .min(comparator)
                    .orElseThrow();
        }

        private void evict() {
            CacheEntry<V> victim = chooseVictim();
            entries.remove(victim.key);
            evictions++;
        }

        public Map<String, Object> metrics() {
            long requests = hits + misses;
            double hitRate = requests == 0 ? 0.0 : (double) hits / requests;

            Map<String, Object> result = new HashMap<>();
            result.put("policy", configuration.policy);
            result.put("capacity", configuration.capacity);
            result.put("size", entries.size());
            result.put("hits", hits);
            result.put("misses", misses);
            result.put("hitRate", hitRate);
            result.put("evictions", evictions);
            return result;
        }

        public List<CacheKey> activeKeys() {
            Instant current = now();
            removeExpired(current);
            return new ArrayList<>(entries.keySet());
        }
    }

    static final class GovernanceConfiguration {
        private final Map<Policy, Integer> capacities =
                new EnumMap<>(Policy.class);

        GovernanceConfiguration() {
            capacities.put(Policy.LRU, 3);
            capacities.put(Policy.LFU, 3);
            capacities.put(Policy.FIFO, 3);
            capacities.put(Policy.TTL, 3);
        }

        int capacityFor(Policy policy) {
            return capacities.get(policy);
        }
    }

    static void demonstrateEnterpriseWorkload() {
        GovernanceConfiguration configuration = new GovernanceConfiguration();

        for (Policy policy : Policy.values()) {
            Duration ttl = policy == Policy.TTL
                    ? Duration.ofSeconds(30)
                    : null;

            CacheService<String> cache = new CacheService<>(
                    new CachePolicy(
                            policy,
                            configuration.capacityFor(policy),
                            ttl
                    )
            );

            cache.put(new CacheKey("catalog", "customer-profile"), "profile-v1");
            cache.put(new CacheKey("catalog", "pricing"), "pricing-v7");
            cache.put(new CacheKey("catalog", "inventory"), "inventory-v4");

            // Repeated reads represent a hot enterprise resource.
            cache.get(new CacheKey("catalog", "pricing"));
            cache.get(new CacheKey("catalog", "pricing"));
            cache.get(new CacheKey("catalog", "customer-profile"));

            cache.put(new CacheKey("catalog", "shipping"), "shipping-v3");

            System.out.println(policy + " -> " + cache.metrics());
        }
    }

    static void demonstrateInvalidConfiguration() {
        try {
            new CachePolicy(Policy.TTL, 2, Duration.ZERO);
        } catch (IllegalArgumentException exception) {
            System.out.println("Rejected invalid TTL policy: "
                    + exception.getMessage());
        }

        try {
            new CacheKey("", "pricing");
        } catch (IllegalArgumentException exception) {
            System.out.println("Rejected invalid cache key: "
                    + exception.getMessage());
        }
    }

    public static void main(String[] args) {
        demonstrateEnterpriseWorkload();
        demonstrateInvalidConfiguration();

        /*
         * Enterprise design decision:
         * cache policy is configuration, while eviction behavior is owned by
         * CacheService. This keeps policy selection separate from business
         * resource identity and makes the same service usable for different
         * resource classes.
         */
    }
}
