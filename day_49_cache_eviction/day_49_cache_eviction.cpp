#include <algorithm>
#include <chrono>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class EvictionPolicy {
    LRU,
    LFU,
    FIFO,
    TTL
};

std::string policyName(EvictionPolicy policy) {
    switch (policy) {
        case EvictionPolicy::LRU: return "LRU";
        case EvictionPolicy::LFU: return "LFU";
        case EvictionPolicy::FIFO: return "FIFO";
        case EvictionPolicy::TTL: return "TTL";
    }
    return "UNKNOWN";
}

struct CacheEntry {
    std::string key;
    std::string value;
    long long insertedAt;
    long long lastAccess;
    long long expiresAt;
    std::size_t frequency;
    std::size_t sequence;

    bool hasExpiry() const {
        return expiresAt >= 0;
    }

    bool expired(long long now) const {
        return hasExpiry() && now >= expiresAt;
    }
};

/*
 * Case study:
 * A configuration service caches repository build metadata. A bounded cache
 * prevents repeated configuration reads from the backing store while an
 * eviction engine decides which stale item can be removed.
 *
 * This implementation uses an unordered_map for average O(1) key lookup.
 * Selecting a victim scans the bounded cache, giving O(C) eviction cost,
 * where C is the configured capacity. For large production caches, an LRU
 * list/map or policy-specific priority structure can reduce that overhead.
 */
class RepositoryMetadataCache {
private:
    std::unordered_map<std::string, CacheEntry> entries;
    std::size_t capacity;
    EvictionPolicy policy;
    std::size_t sequence = 0;
    long long clock = 0;

    CacheEntry* selectVictim() {
        if (entries.empty()) {
            return nullptr;
        }

        auto victim = entries.begin();

        for (auto it = std::next(entries.begin()); it != entries.end(); ++it) {
            const CacheEntry& a = it->second;
            const CacheEntry& b = victim->second;

            bool better = false;

            switch (policy) {
                case EvictionPolicy::LRU:
                    better =
                        a.lastAccess < b.lastAccess ||
                        (a.lastAccess == b.lastAccess && a.sequence < b.sequence);
                    break;

                case EvictionPolicy::LFU:
                    better =
                        a.frequency < b.frequency ||
                        (a.frequency == b.frequency &&
                         a.lastAccess < b.lastAccess);
                    break;

                case EvictionPolicy::FIFO:
                    better = a.sequence < b.sequence;
                    break;

                case EvictionPolicy::TTL: {
                    const long long aExpiry =
                        a.hasExpiry() ? a.expiresAt : std::numeric_limits<long long>::max();
                    const long long bExpiry =
                        b.hasExpiry() ? b.expiresAt : std::numeric_limits<long long>::max();
                    better = aExpiry < bExpiry;
                    break;
                }
            }

            if (better) {
                victim = it;
            }
        }

        return &victim->second;
    }

    void removeExpired() {
        for (auto it = entries.begin(); it != entries.end();) {
            if (it->second.expired(clock)) {
                it = entries.erase(it);
            } else {
                ++it;
            }
        }
    }

public:
    RepositoryMetadataCache(
        std::size_t capacity,
        EvictionPolicy policy
    ) : capacity(capacity), policy(policy) {
        if (capacity == 0) {
            throw std::invalid_argument("cache capacity must be positive");
        }
    }

    void advanceTime(long long seconds) {
        if (seconds < 0) {
            throw std::invalid_argument("clock cannot move backward");
        }

        clock += seconds;
        removeExpired();
    }

    void put(
        const std::string& key,
        const std::string& value,
        std::optional<long long> ttl = std::nullopt
    ) {
        if (key.empty()) {
            throw std::invalid_argument("cache key cannot be empty");
        }

        if (ttl.has_value() && *ttl <= 0) {
            throw std::invalid_argument("TTL must be positive");
        }

        removeExpired();

        auto found = entries.find(key);

        if (found != entries.end()) {
            found->second.value = value;
            found->second.lastAccess = clock;
            found->second.frequency++;
            found->second.expiresAt =
                ttl.has_value() ? clock + *ttl : -1;
            return;
        }

        CacheEntry entry{
            key,
            value,
            clock,
            clock,
            ttl.has_value() ? clock + *ttl : -1,
            1,
            ++sequence
        };

        entries.emplace(key, std::move(entry));

        if (entries.size() > capacity) {
            CacheEntry* victim = selectVictim();

            if (victim != nullptr) {
                entries.erase(victim->key);
            }
        }
    }

    std::optional<std::string> get(const std::string& key) {
        removeExpired();

        auto found = entries.find(key);

        if (found == entries.end()) {
            return std::nullopt;
        }

        found->second.lastAccess = clock;
        found->second.frequency++;

        return found->second.value;
    }

    bool erase(const std::string& key) {
        return entries.erase(key) > 0;
    }

    std::vector<std::string> keys() {
        removeExpired();

        std::vector<std::string> result;
        result.reserve(entries.size());

        for (const auto& [key, entry] : entries) {
            result.push_back(key);
        }

        std::sort(result.begin(), result.end());
        return result;
    }

    std::size_t size() {
        removeExpired();
        return entries.size();
    }
};

void printCache(
    RepositoryMetadataCache& cache,
    const std::string& label
) {
    std::cout << label << ": ";

    for (const auto& key : cache.keys()) {
        std::cout << key << " ";
    }

    std::cout << "\n";
}

void runPolicyScenario(EvictionPolicy policy) {
    RepositoryMetadataCache cache(3, policy);

    cache.put("repo:api", "build-config-api");
    cache.put("repo:web", "build-config-web");
    cache.put("repo:worker", "build-config-worker");

    /*
     * This access pattern makes the policies diverge:
     * LRU observes recent access, LFU observes repeated access, while FIFO
     * ignores both and retains the original insertion ordering.
     */
    cache.get("repo:api");
    cache.get("repo:api");
    cache.get("repo:web");

    cache.put("repo:billing", "build-config-billing");

    printCache(cache, policyName(policy));
}

void runTtlScenario() {
    RepositoryMetadataCache cache(3, EvictionPolicy::TTL);

    cache.put("token:A", "credential-metadata", 5);
    cache.put("token:B", "credential-metadata", 10);
    cache.put("token:C", "credential-metadata", 20);

    cache.advanceTime(6);

    printCache(cache, "TTL after expiration");

    if (!cache.get("token:A").has_value()) {
        std::cout << "token:A is unavailable after its TTL.\n";
    }
}

void runFailureCases() {
    try {
        RepositoryMetadataCache invalid(0, EvictionPolicy::LRU);
    } catch (const std::invalid_argument& error) {
        std::cout << "Rejected invalid cache: " << error.what() << "\n";
    }

    RepositoryMetadataCache cache(2, EvictionPolicy::LRU);

    try {
        cache.put("", "invalid");
    } catch (const std::invalid_argument& error) {
        std::cout << "Rejected invalid key: " << error.what() << "\n";
    }

    try {
        cache.put("bad-ttl", "value", 0);
    } catch (const std::invalid_argument& error) {
        std::cout << "Rejected invalid TTL: " << error.what() << "\n";
    }
}

int main() {
    std::cout << "Repository build-metadata cache\n";
    std::cout << "==============================\n";

    runPolicyScenario(EvictionPolicy::LRU);
    runPolicyScenario(EvictionPolicy::LFU);
    runPolicyScenario(EvictionPolicy::FIFO);
    runTtlScenario();
    runFailureCases();

    /*
     * Security design: a cache should not silently become the authoritative
     * source for secrets, authorization decisions, or mutable policy data.
     * TTL limits exposure, but authorization-sensitive data may require
     * explicit invalidation whenever the source-of-truth changes.
     */
    return 0;
}
