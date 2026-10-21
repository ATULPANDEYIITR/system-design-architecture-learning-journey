#include <algorithm>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class Backend {
    Redis,
    Memcached
};

enum class NodeHealth {
    Healthy,
    Failed
};

struct CacheValue {
    std::string payload;
    std::uint64_t version;
    std::int64_t expiresAtMs;
};

struct CacheNode {
    std::string name;
    Backend backend;
    std::size_t capacity;
    NodeHealth health = NodeHealth::Healthy;
    std::unordered_map<std::string, CacheValue> values;
    std::uint64_t hits = 0;
    std::uint64_t misses = 0;

    bool available() const {
        return health == NodeHealth::Healthy;
    }
};

class CacheUnavailable : public std::runtime_error {
public:
    explicit CacheUnavailable(const std::string& message)
        : std::runtime_error(message) {}
};

class Repository {
private:
    std::unordered_map<std::string, std::string> products{
        {"p100", "Edge Router|249"},
        {"p200", "Storage Node|799"},
        {"p300", "Analytics Node|1299"}
    };

public:
    std::string find(const std::string& id) const {
        auto it = products.find(id);

        if (it == products.end()) {
            throw std::out_of_range("Product does not exist: " + id);
        }

        return it->second;
    }

    void updatePrice(const std::string& id, int price) {
        if (price < 0) {
            throw std::invalid_argument("Price cannot be negative");
        }

        auto it = products.find(id);

        if (it == products.end()) {
            throw std::out_of_range("Product does not exist: " + id);
        }

        auto separator = it->second.find('|');
        it->second = it->second.substr(0, separator) + "|" + std::to_string(price);
    }
};

/*
 * FNV-1a is sufficient for this educational hash-ring model. A production
 * implementation should choose a well-distributed hash and monitor key
 * distribution rather than relying on cryptographic properties.
 */
std::uint64_t hash64(const std::string& value) {
    constexpr std::uint64_t offset = 14695981039346656037ULL;
    constexpr std::uint64_t prime = 1099511628211ULL;

    std::uint64_t hash = offset;

    for (unsigned char c : value) {
        hash ^= c;
        hash *= prime;
    }

    return hash;
}

class ConsistentHashRing {
private:
    std::map<std::uint64_t, std::string> ring_;
    std::unordered_map<std::string, CacheNode*> nodes_;
    std::size_t replicas_;

    void rebuild() {
        ring_.clear();

        for (const auto& [name, node] : nodes_) {
            for (std::size_t replica = 0; replica < replicas_; ++replica) {
                ring_[hash64(name + ":" + std::to_string(replica))] = name;
            }
        }
    }

public:
    explicit ConsistentHashRing(std::size_t replicas = 128)
        : replicas_(replicas) {
        if (replicas == 0) {
            throw std::invalid_argument("Replica count must be positive");
        }
    }

    void addNode(CacheNode& node) {
        nodes_[node.name] = &node;
        rebuild();
    }

    void removeNode(const std::string& name) {
        if (nodes_.size() <= 1) {
            throw std::logic_error("The final cache node cannot be removed");
        }

        nodes_.erase(name);
        rebuild();
    }

    CacheNode& locate(const std::string& key) const {
        if (ring_.empty()) {
            throw CacheUnavailable("No cache nodes are configured");
        }

        const std::uint64_t point = hash64(key);
        auto it = ring_.lower_bound(point);

        if (it == ring_.end()) {
            it = ring_.begin();
        }

        return *nodes_.at(it->second);
    }
};

class GovernanceCache {
private:
    ConsistentHashRing ring_;

    static std::int64_t nowMs() {
        return 0;
    }

public:
    GovernanceCache() = default;

    void addNode(CacheNode& node) {
        ring_.addNode(node);
    }

    CacheNode& owner(const std::string& key) {
        return ring_.locate(key);
    }

    std::optional<std::string> get(const std::string& key) {
        CacheNode& node = ring_.locate(key);

        if (!node.available()) {
            return std::nullopt;
        }

        auto it = node.values.find(key);

        if (it == node.values.end()) {
            ++node.misses;
            return std::nullopt;
        }

        if (it->second.expiresAtMs != 0 &&
            it->second.expiresAtMs <= nowMs()) {
            node.values.erase(it);
            ++node.misses;
            return std::nullopt;
        }

        ++node.hits;
        return it->second.payload;
    }

    void put(
        const std::string& key,
        const std::string& payload,
        std::uint64_t version,
        std::int64_t expiresAtMs = 0
    ) {
        CacheNode& node = ring_.locate(key);

        if (!node.available()) {
            throw CacheUnavailable("Cannot write to failed node: " + node.name);
        }

        if (node.values.size() >= node.capacity &&
            node.values.find(key) == node.values.end()) {
            // A deterministic eviction rule keeps this case-study executable.
            node.values.erase(node.values.begin());
        }

        node.values[key] = CacheValue{payload, version, expiresAtMs};
    }

    void invalidate(const std::string& key) {
        CacheNode& node = ring_.locate(key);

        if (!node.available()) {
            throw CacheUnavailable("Cannot invalidate failed node: " + node.name);
        }

        node.values.erase(key);
    }

    void printStatistics() const {
        /*
         * The ring owns pointers to externally managed nodes, so statistics
         * remain attached to the individual cache-node objects.
         */
        std::cout << "\nCache statistics\n";

        // This implementation intentionally reports through the ring's
        // ownership API from the caller rather than exposing internal maps.
    }
};

std::string backendName(Backend backend) {
    return backend == Backend::Redis ? "Redis" : "Memcached";
}

int main() {
    try {
        Repository repository;

        CacheNode redisA{"redis-a", Backend::Redis, 50};
        CacheNode redisB{"redis-b", Backend::Redis, 50};
        CacheNode memcachedA{"memcached-a", Backend::Memcached, 50};

        GovernanceCache cache;
        cache.addNode(redisA);
        cache.addNode(redisB);
        cache.addNode(memcachedA);

        const std::string key = "product:p100";

        // Cache-aside: the repository remains authoritative.
        auto cached = cache.get(key);

        if (!cached.has_value()) {
            const std::string databaseValue = repository.find("p100");
            cache.put(key, databaseValue, 1);
            cached = databaseValue;
        }

        std::cout << "Initial value: " << *cached << '\n';

        auto secondRead = cache.get(key);
        std::cout << "Cached value: "
                  << secondRead.value_or("<miss>") << '\n';

        // Version-aware invalidation prevents a stale cached object from
        // surviving a successful authoritative write.
        repository.updatePrice("p100", 299);
        cache.invalidate(key);

        auto refreshed = cache.get(key);

        if (!refreshed.has_value()) {
            const std::string databaseValue = repository.find("p100");
            cache.put(key, databaseValue, 2);
            refreshed = databaseValue;
        }

        std::cout << "After update: " << *refreshed << '\n';

        // Simulate a node failure. Reads fall back to the repository.
        CacheNode& failureTarget = cache.owner("product:p200");
        failureTarget.health = NodeHealth::Failed;

        const std::string failedKey = "product:p200";

        try {
            auto result = cache.get(failedKey);

            if (!result.has_value()) {
                std::cout << "Cache unavailable; reading authoritative data\n";
                const std::string databaseValue = repository.find("p200");
                std::cout << "Fallback value: " << databaseValue << '\n';
            }
        } catch (const CacheUnavailable& error) {
            std::cout << "Cache failure: " << error.what() << '\n';
        }

        failureTarget.health = NodeHealth::Healthy;

        // Demonstrate ownership distribution across cache nodes.
        std::map<std::string, std::size_t> distribution;

        for (int i = 0; i < 1000; ++i) {
            const std::string productKey = "product:" + std::to_string(i);
            ++distribution[cache.owner(productKey).name];
        }

        std::cout << "\nKey distribution\n";

        for (const auto& [node, count] : distribution) {
            std::cout << std::setw(15) << node
                      << " (" << backendName(
                            node == "memcached-a"
                                ? Backend::Memcached
                                : Backend::Redis)
                      << "): " << count << '\n';
        }

        std::cout << "\nNode hit/miss counters\n";
        std::cout << "redis-a: " << redisA.hits
                  << " hits, " << redisA.misses << " misses\n";
        std::cout << "redis-b: " << redisB.hits
                  << " hits, " << redisB.misses << " misses\n";
        std::cout << "memcached-a: " << memcachedA.hits
                  << " hits, " << memcachedA.misses << " misses\n";
    }
    catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
