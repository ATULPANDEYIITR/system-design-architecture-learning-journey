#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using Clock = std::chrono::steady_clock;

struct Product {
    int id;
    std::string name;
    double price;
    std::uint64_t version;
};

struct CacheEntry {
    Product product;
    Clock::time_point expiresAt;
    bool hasExpiry;
};

class ProductRepository {
private:
    std::unordered_map<int, Product> products{
        {101, {101, "Keyboard", 2400.0, 1}},
        {102, {102, "Monitor", 18500.0, 1}}
    };

public:
    Product get(int id) const {
        auto it = products.find(id);

        if (it == products.end()) {
            throw std::out_of_range("product not found");
        }

        return it->second;
    }

    Product updatePrice(int id, double price) {
        if (price < 0.0) {
            throw std::invalid_argument("price cannot be negative");
        }

        auto it = products.find(id);

        if (it == products.end()) {
            throw std::out_of_range("product not found");
        }

        it->second.price = price;
        ++it->second.version;

        return it->second;
    }
};

class GovernanceCache {
private:
    std::unordered_map<std::string, CacheEntry> entries;

public:
    void put(
        const std::string& key,
        const Product& product,
        std::optional<std::chrono::milliseconds> ttl = std::nullopt
    ) {
        if (key.empty()) {
            throw std::invalid_argument("cache key cannot be empty");
        }

        CacheEntry entry{
            product,
            Clock::time_point{},
            false
        };

        if (ttl.has_value()) {
            if (ttl->count() <= 0) {
                throw std::invalid_argument("TTL must be positive");
            }

            entry.hasExpiry = true;
            entry.expiresAt = Clock::now() + *ttl;
        }

        entries[key] = entry;
    }

    std::optional<Product> get(const std::string& key) {
        auto it = entries.find(key);

        if (it == entries.end()) {
            return std::nullopt;
        }

        if (it->second.hasExpiry &&
            Clock::now() >= it->second.expiresAt) {
            entries.erase(it);
            return std::nullopt;
        }

        return it->second.product;
    }

    void invalidate(const std::string& key) {
        entries.erase(key);
    }

    std::size_t invalidatePrefix(const std::string& prefix) {
        if (prefix.empty()) {
            throw std::invalid_argument("prefix cannot be empty");
        }

        std::size_t removed = 0;

        for (auto it = entries.begin(); it != entries.end();) {
            if (it->first.rfind(prefix, 0) == 0) {
                it = entries.erase(it);
                ++removed;
            } else {
                ++it;
            }
        }

        return removed;
    }

    std::size_t removeExpired() {
        const auto now = Clock::now();
        std::size_t removed = 0;

        for (auto it = entries.begin(); it != entries.end();) {
            if (it->second.hasExpiry && now >= it->second.expiresAt) {
                it = entries.erase(it);
                ++removed;
            } else {
                ++it;
            }
        }

        return removed;
    }
};

class MergeEligibilityEngine {
private:
    ProductRepository& repository;
    GovernanceCache& cache;

public:
    MergeEligibilityEngine(
        ProductRepository& repository,
        GovernanceCache& cache
    )
        : repository(repository), cache(cache) {}

    Product getProduct(int id) {
        const std::string key = "product:" + std::to_string(id);

        if (auto cached = cache.get(key); cached.has_value()) {
            return *cached;
        }

        Product current = repository.get(id);
        cache.put(key, current, std::chrono::milliseconds(5000));

        return current;
    }

    Product updatePrice(int id, double price) {
        Product updated = repository.updatePrice(id, price);

        // The old cache entry is now known to be stale.
        cache.invalidate("product:" + std::to_string(id));

        return updated;
    }

    Product getVersionAware(int id) {
        const std::string key = "product:" + std::to_string(id);
        auto cached = cache.get(key);
        Product authoritative = repository.get(id);

        if (!cached.has_value() ||
            cached->version < authoritative.version) {
            cache.put(key, authoritative);
            return authoritative;
        }

        return *cached;
    }
};

void printProduct(const std::string& label, const Product& product) {
    std::cout << label
              << " id=" << product.id
              << ", name=" << product.name
              << ", price=" << product.price
              << ", version=" << product.version
              << '\n';
}

int main() {
    try {
        ProductRepository repository;
        GovernanceCache cache;
        MergeEligibilityEngine service(repository, cache);

        Product first = service.getProduct(101);
        Product second = service.getProduct(101);

        printProduct("First read", first);
        printProduct("Cached read", second);

        Product updated = service.updatePrice(101, 2600.0);
        printProduct("Authoritative update", updated);

        Product refreshed = service.getProduct(101);
        printProduct("Read after invalidation", refreshed);

        Product versionChecked = service.getVersionAware(101);
        printProduct("Version-aware read", versionChecked);

        GovernanceCache ttlCache;
        ttlCache.put(
            "temporary",
            refreshed,
            std::chrono::milliseconds(50)
        );

        if (auto value = ttlCache.get("temporary")) {
            printProduct("TTL value", *value);
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(60));

        if (!ttlCache.get("temporary")) {
            std::cout << "TTL entry expired and was removed\n";
        }

        try {
            service.updatePrice(101, -1.0);
        } catch (const std::exception& error) {
            std::cout << "Expected validation failure: "
                      << error.what() << '\n';
        }

        cache.invalidatePrefix("product:");
        std::cout << "Cache namespace invalidated\n";
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
