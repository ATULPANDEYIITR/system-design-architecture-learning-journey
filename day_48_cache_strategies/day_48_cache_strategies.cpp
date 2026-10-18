#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using Clock = std::chrono::steady_clock;

struct Product {
    int id;
    std::string name;
    double price;
    int stock;
    std::uint64_t version;
};

class Repository {
private:
    std::unordered_map<int, Product> products_;
    std::size_t reads_ = 0;
    std::size_t writes_ = 0;

public:
    Repository() {
        products_.emplace(
            101,
            Product{101, "Mechanical Keyboard", 89.99, 42, 1}
        );
        products_.emplace(
            102,
            Product{102, "USB-C Dock", 129.50, 17, 1}
        );
        products_.emplace(
            103,
            Product{103, "Noise-Cancelling Headphones", 199.00, 9, 1}
        );
    }

    std::optional<Product> find(int id) {
        ++reads_;

        auto it = products_.find(id);
        if (it == products_.end()) {
            return std::nullopt;
        }

        return it->second;
    }

    Product save(Product product) {
        if (product.price < 0.0) {
            throw std::invalid_argument("price cannot be negative");
        }

        if (product.stock < 0) {
            throw std::invalid_argument("stock cannot be negative");
        }

        auto it = products_.find(product.id);

        if (it == products_.end()) {
            product.version = 1;
        } else {
            product.version = it->second.version + 1;
        }

        products_[product.id] = product;
        ++writes_;

        return product;
    }

    std::size_t reads() const {
        return reads_;
    }

    std::size_t writes() const {
        return writes_;
    }
};

class TtlCache {
private:
    struct Entry {
        Product product;
        std::optional<Clock::time_point> expiresAt;
    };

    std::unordered_map<int, Entry> entries_;
    std::size_t hits_ = 0;
    std::size_t misses_ = 0;
    std::size_t writes_ = 0;

public:
    std::optional<Product> get(int key) {
        auto it = entries_.find(key);

        if (it == entries_.end()) {
            ++misses_;
            return std::nullopt;
        }

        if (
            it->second.expiresAt.has_value() &&
            Clock::now() >= it->second.expiresAt.value()
        ) {
            entries_.erase(it);
            ++misses_;
            return std::nullopt;
        }

        ++hits_;
        return it->second.product;
    }

    void put(
        int key,
        const Product& product,
        std::chrono::milliseconds ttl
    ) {
        entries_[key] = Entry{
            product,
            Clock::now() + ttl
        };
        ++writes_;
    }

    void erase(int key) {
        entries_.erase(key);
    }

    std::size_t hits() const {
        return hits_;
    }

    std::size_t misses() const {
        return misses_;
    }

    std::size_t writes() const {
        return writes_;
    }
};

class CacheAsideService {
private:
    Repository& repository_;
    TtlCache& cache_;
    std::chrono::milliseconds ttl_;

public:
    CacheAsideService(
        Repository& repository,
        TtlCache& cache,
        std::chrono::milliseconds ttl
    )
        : repository_(repository),
          cache_(cache),
          ttl_(ttl) {}

    std::optional<Product> getProduct(int id) {
        auto cached = cache_.get(id);

        if (cached.has_value()) {
            return cached;
        }

        auto source = repository_.find(id);

        if (source.has_value()) {
            cache_.put(id, source.value(), ttl_);
        }

        return source;
    }

    Product updateProduct(Product product) {
        Product persisted = repository_.save(product);

        // Invalidation is deliberately separate from persistence. If save()
        // throws, this statement is never reached and the old cache entry
        // remains available rather than being removed for a failed write.
        cache_.erase(product.id);

        return persisted;
    }
};

class ReadThroughCache {
private:
    Repository& repository_;
    TtlCache& cache_;
    std::chrono::milliseconds ttl_;

public:
    ReadThroughCache(
        Repository& repository,
        TtlCache& cache,
        std::chrono::milliseconds ttl
    )
        : repository_(repository),
          cache_(cache),
          ttl_(ttl) {}

    std::optional<Product> get(int id) {
        auto cached = cache_.get(id);

        if (cached.has_value()) {
            return cached;
        }

        auto source = repository_.find(id);

        if (source.has_value()) {
            cache_.put(id, source.value(), ttl_);
        }

        return source;
    }
};

class WriteThroughService {
private:
    Repository& repository_;
    TtlCache& cache_;
    std::chrono::milliseconds ttl_;

public:
    WriteThroughService(
        Repository& repository,
        TtlCache& cache,
        std::chrono::milliseconds ttl
    )
        : repository_(repository),
          cache_(cache),
          ttl_(ttl) {}

    Product write(Product product) {
        // The persistent write is authoritative. Cache mutation follows only
        // after successful validation and persistence.
        Product persisted = repository_.save(product);
        cache_.put(persisted.id, persisted, ttl_);
        return persisted;
    }

    std::optional<Product> get(int id) {
        return cache_.get(id);
    }
};

void printProduct(
    const std::string& label,
    const std::optional<Product>& product
) {
    std::cout << label << ": ";

    if (!product.has_value()) {
        std::cout << "NOT FOUND\n";
        return;
    }

    std::cout
        << product->name
        << " | price=$"
        << std::fixed
        << std::setprecision(2)
        << product->price
        << " | stock="
        << product->stock
        << " | version="
        << product->version
        << '\n';
}

void demonstrateCacheAside() {
    std::cout << "\n=== Cache-aside ===\n";

    Repository repository;
    TtlCache cache;

    CacheAsideService service(
        repository,
        cache,
        std::chrono::seconds(30)
    );

    printProduct("First read", service.getProduct(101));
    printProduct("Second read", service.getProduct(101));

    service.updateProduct(
        Product{
            101,
            "Mechanical Keyboard",
            94.99,
            40,
            0
        }
    );

    printProduct("Read after invalidation", service.getProduct(101));

    std::cout
        << "Repository reads="
        << repository.reads()
        << ", writes="
        << repository.writes()
        << '\n';
}

void demonstrateReadThrough() {
    std::cout << "\n=== Read-through ===\n";

    Repository repository;
    TtlCache cache;

    ReadThroughCache readThrough(
        repository,
        cache,
        std::chrono::seconds(30)
    );

    printProduct("First read", readThrough.get(102));
    printProduct("Second read", readThrough.get(102));
    printProduct("Missing product", readThrough.get(999));

    std::cout
        << "Repository reads="
        << repository.reads()
        << '\n';
}

void demonstrateWriteThrough() {
    std::cout << "\n=== Write-through ===\n";

    Repository repository;
    TtlCache cache;

    WriteThroughService service(
        repository,
        cache,
        std::chrono::seconds(30)
    );

    Product persisted = service.write(
        Product{
            103,
            "Noise-Cancelling Headphones",
            184.00,
            8,
            0
        }
    );

    printProduct("Persisted value", persisted);
    printProduct("Immediate cached read", service.get(103));

    auto source = repository.find(103);
    printProduct("Source value", source);
}

void demonstrateExpiration() {
    std::cout << "\n=== Expiration ===\n";

    TtlCache cache;

    Product product{
        501,
        "Temporary Catalog Entry",
        15.00,
        4,
        1
    };

    cache.put(
        product.id,
        product,
        std::chrono::milliseconds(30)
    );

    printProduct("Immediately available", cache.get(product.id));

    std::this_thread::sleep_for(std::chrono::milliseconds(50));

    printProduct("After TTL", cache.get(product.id));
}

void demonstrateFailureSafety() {
    std::cout << "\n=== Failed write ===\n";

    Repository repository;
    TtlCache cache;

    WriteThroughService service(
        repository,
        cache,
        std::chrono::seconds(30)
    );

    service.write(
        Product{
            101,
            "Mechanical Keyboard",
            95.00,
            39,
            0
        }
    );

    try {
        service.write(
            Product{
                101,
                "Mechanical Keyboard",
                -50.00,
                39,
                0
            }
        );
    } catch (const std::exception& error) {
        std::cout << "Rejected write: " << error.what() << '\n';
    }

    printProduct("Last valid cached state", service.get(101));
}

void demonstrateStaleData() {
    std::cout << "\n=== External source mutation ===\n";

    Repository repository;
    TtlCache cache;

    ReadThroughCache service(
        repository,
        cache,
        std::chrono::seconds(30)
    );

    printProduct("Initial read", service.get(102));

    // Another service changes the source without informing this cache.
    repository.save(
        Product{
            102,
            "USB-C Dock",
            139.50,
            16,
            0
        }
    );

    printProduct(
        "Read before invalidation",
        service.get(102)
    );

    // Explicit invalidation restores consistency immediately.
    cache.erase(102);

    printProduct(
        "Read after invalidation",
        service.get(102)
    );
}

void printStrategyProperties() {
    std::cout << "\n=== Strategy properties ===\n";

    std::cout
        << "Cache-aside: application controls miss loading and invalidation.\n"
        << "Read-through: cache abstraction owns the source lookup on misses.\n"
        << "Write-through: successful source writes immediately update cache.\n"
        << "TTL: bounds how long an entry can remain readable without refresh.\n";
}

int main() {
    std::cout << "REPOSITORY GOVERNANCE IS NOT PART OF THIS CASE STUDY\n";
    std::cout << "CASE STUDY: PRODUCT CATALOG CACHE STRATEGIES\n";

    demonstrateCacheAside();
    demonstrateReadThrough();
    demonstrateWriteThrough();
    demonstrateExpiration();
    demonstrateFailureSafety();
    demonstrateStaleData();
    printStrategyProperties();

    std::cout << "\nComplexity notes:\n";
    std::cout
        << "The unordered_map cache provides expected O(1) lookup and update.\n"
        << "A cache hit avoids the source-store latency entirely.\n"
        << "A cache miss adds cache lookup overhead before the source lookup.\n"
        << "TTL expiration trades freshness against source-store traffic.\n";

    return 0;
}
