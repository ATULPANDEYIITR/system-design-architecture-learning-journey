#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <random>
#include <shared_mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

/*
 * Repository-independent cache governance engine.
 *
 * The engine models three operational failure patterns:
 *
 * 1. Penetration:
 *    invalid or nonexistent keys repeatedly reach the origin.
 *
 * 2. Stampede:
 *    one hot key expires and many callers simultaneously request it.
 *
 * 3. Avalanche:
 *    many independent keys expire in a correlated time window.
 *
 * The implementation demonstrates:
 * - negative caching
 * - key admission validation
 * - per-key single-flight refresh
 * - randomized TTLs
 * - stale-while-revalidate
 *
 * The design deliberately separates cache policy from the backend.
 */

struct CacheValue {
    std::string payload;
};

struct Metrics {
    std::uint64_t hits = 0;
    std::uint64_t misses = 0;
    std::uint64_t backendReads = 0;
    std::uint64_t negativeHits = 0;
    std::uint64_t rejectedPenetration = 0;
    std::uint64_t singleFlightWaiters = 0;
    std::uint64_t refreshes = 0;
    std::uint64_t failures = 0;
    std::uint64_t staleServed = 0;
};

struct Entry {
    std::optional<CacheValue> value;
    std::chrono::steady_clock::time_point expiresAt;
};

class OriginStore {
public:
    void put(const std::string& key, const std::string& value) {
        std::unique_lock lock(mutex_);
        records_[key] = CacheValue{value};
    }

    std::optional<CacheValue> read(const std::string& key) {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        std::shared_lock lock(mutex_);

        auto it = records_.find(key);
        if (it == records_.end()) {
            return std::nullopt;
        }
        return it->second;
    }

private:
    std::unordered_map<std::string, CacheValue> records_;
    mutable std::shared_mutex mutex_;
};

class CacheFailureEngine {
public:
    using Loader = std::function<std::optional<CacheValue>(const std::string&)>;

    CacheFailureEngine(
        Loader loader,
        std::chrono::milliseconds ttl,
        std::chrono::milliseconds negativeTtl,
        double jitterRatio,
        std::chrono::milliseconds staleGrace
    )
        : loader_(std::move(loader)),
          ttl_(ttl),
          negativeTtl_(negativeTtl),
          jitterRatio_(jitterRatio),
          staleGrace_(staleGrace),
          generator_(std::random_device{}()) {

        if (ttl_.count() <= 0 || negativeTtl_.count() <= 0) {
            throw std::invalid_argument("TTLs must be positive");
        }
        if (jitterRatio_ < 0.0 || jitterRatio_ > 1.0) {
            throw std::invalid_argument("jitter ratio must be between 0 and 1");
        }
    }

    std::optional<CacheValue> get(const std::string& key) {
        if (!validKey(key)) {
            std::lock_guard lock(metricsMutex_);
            metrics_.rejectedPenetration++;
            return std::nullopt;
        }

        {
            std::lock_guard lock(cacheMutex_);
            auto it = entries_.find(key);

            if (it != entries_.end()) {
                const auto now = std::chrono::steady_clock::now();

                if (it->second.expiresAt > now) {
                    recordHit(it->second.value);
                    return it->second.value;
                }

                // Stale data is usable for a short period. This protects the
                // origin from synchronized expiration bursts.
                if (it->second.expiresAt + staleGrace_ > now) {
                    recordStale();
                    return it->second.value;
                }
            }
        }

        recordMiss();

        // Single-flight state is protected separately from the cache so that
        // backend refreshes for unrelated keys can execute concurrently.
        std::shared_ptr<RefreshState> state;

        {
            std::lock_guard lock(inFlightMutex_);
            auto it = inFlight_.find(key);

            if (it != inFlight_.end()) {
                state = it->second;
                recordWaiter();
            } else {
                state = std::make_shared<RefreshState>();
                inFlight_[key] = state;
            }
        }

        if (state->owner) {
            // Only the first caller performs the origin read.
            std::optional<CacheValue> result;

            try {
                {
                    std::lock_guard lock(metricsMutex_);
                    metrics_.backendReads++;
                }

                result = loader_(key);

                const auto baseTtl =
                    result.has_value() ? ttl_ : negativeTtl_;

                const auto expiration =
                    std::chrono::steady_clock::now() +
                    randomizedTtl(baseTtl);

                {
                    std::lock_guard lock(cacheMutex_);
                    entries_[key] = Entry{result, expiration};
                }

                {
                    std::lock_guard lock(metricsMutex_);
                    metrics_.refreshes++;
                }

                {
                    std::lock_guard lock(state->mutex);
                    state->result = result;
                    state->completed = true;
                }
            } catch (...) {
                {
                    std::lock_guard lock(metricsMutex_);
                    metrics_.failures++;
                }

                {
                    std::lock_guard lock(state->mutex);
                    state->error = std::current_exception();
                    state->completed = true;
                }
            }

            state->condition.notify_all();

            {
                std::lock_guard lock(inFlightMutex_);
                inFlight_.erase(key);
            }

            if (state->error) {
                std::rethrow_exception(state->error);
            }

            return state->result;
        }

        std::unique_lock lock(state->mutex);
        state->condition.wait(lock, [&state] {
            return state->completed;
        });

        if (state->error) {
            std::rethrow_exception(state->error);
        }

        return state->result;
    }

    Metrics metrics() const {
        std::lock_guard lock(metricsMutex_);
        return metrics_;
    }

    void invalidate(const std::string& key) {
        std::lock_guard lock(cacheMutex_);
        entries_.erase(key);
    }

private:
    struct RefreshState {
        // A newly created state belongs to its first caller.
        bool owner = true;
        bool completed = false;
        std::optional<CacheValue> result;
        std::exception_ptr error;
        std::mutex mutex;
        std::condition_variable condition;
    };

    bool validKey(const std::string& key) const {
        if (key.empty() || key.size() > 100) {
            return false;
        }

        for (char c : key) {
            if (!(std::isalnum(static_cast<unsigned char>(c)) ||
                  c == ':' || c == '-' || c == '_')) {
                return false;
            }
        }

        return true;
    }

    std::chrono::milliseconds randomizedTtl(
        std::chrono::milliseconds base
    ) {
        const double baseValue = static_cast<double>(base.count());
        const double delta = baseValue * jitterRatio_;

        std::uniform_real_distribution<double> distribution(
            baseValue - delta,
            baseValue + delta
        );

        return std::chrono::milliseconds(
            static_cast<long long>(std::max(1.0, distribution(generator_)))
        );
    }

    void recordHit(const std::optional<CacheValue>& value) {
        std::lock_guard lock(metricsMutex_);
        metrics_.hits++;
        if (!value.has_value()) {
            metrics_.negativeHits++;
        }
    }

    void recordMiss() {
        std::lock_guard lock(metricsMutex_);
        metrics_.misses++;
    }

    void recordWaiter() {
        std::lock_guard lock(metricsMutex_);
        metrics_.singleFlightWaiters++;
    }

    void recordStale() {
        std::lock_guard lock(metricsMutex_);
        metrics_.hits++;
        metrics_.staleServed++;
    }

    Loader loader_;
    std::chrono::milliseconds ttl_;
    std::chrono::milliseconds negativeTtl_;
    double jitterRatio_;
    std::chrono::milliseconds staleGrace_;

    mutable std::mutex cacheMutex_;
    std::unordered_map<std::string, Entry> entries_;

    mutable std::mutex inFlightMutex_;
    std::unordered_map<std::string, std::shared_ptr<RefreshState>> inFlight_;

    mutable std::mutex metricsMutex_;
    Metrics metrics_;

    std::mt19937 generator_;
};

int main() {
    OriginStore origin;

    origin.put("product:100", "Keyboard");
    origin.put("product:101", "Mouse");
    origin.put("config:homepage", "version=42");

    CacheFailureEngine cache(
        [&origin](const std::string& key) {
            return origin.read(key);
        },
        std::chrono::milliseconds(100),
        std::chrono::milliseconds(50),
        0.20,
        std::chrono::milliseconds(150)
    );

    // Penetration: a nonexistent key is loaded once and then represented by
    // a negative cache entry.
    for (int i = 0; i < 100; ++i) {
        cache.get("product:404");
    }

    // Penetration admission control rejects malformed/untrusted keys before
    // the origin is touched.
    for (int i = 0; i < 100; ++i) {
        cache.get("../secret");
    }

    // Stampede: expire the hot entry, then issue concurrent requests.
    cache.get("product:100");
    std::this_thread::sleep_for(std::chrono::milliseconds(120));

    std::vector<std::thread> workers;
    workers.reserve(50);

    for (int i = 0; i < 50; ++i) {
        workers.emplace_back([&cache] {
            cache.get("product:100");
        });
    }

    for (auto& worker : workers) {
        worker.join();
    }

    // Avalanche mitigation: independent keys use randomized expiration.
    for (int i = 0; i < 100; ++i) {
        origin.put("item:" + std::to_string(i), "payload");
        cache.get("item:" + std::to_string(i));
    }

    const Metrics m = cache.metrics();

    const auto requests = m.hits + m.misses;
    const double hitRate =
        requests == 0
            ? 0.0
            : static_cast<double>(m.hits) /
              static_cast<double>(requests);

    std::cout << std::fixed << std::setprecision(3);
    std::cout << "CACHE FAILURE ENGINE\n";
    std::cout << "hits: " << m.hits << '\n';
    std::cout << "misses: " << m.misses << '\n';
    std::cout << "backend reads: " << m.backendReads << '\n';
    std::cout << "negative hits: " << m.negativeHits << '\n';
    std::cout << "rejected penetration: "
              << m.rejectedPenetration << '\n';
    std::cout << "single-flight waiters: "
              << m.singleFlightWaiters << '\n';
    std::cout << "refreshes: " << m.refreshes << '\n';
    std::cout << "stale served: " << m.staleServed << '\n';
    std::cout << "failures: " << m.failures << '\n';
    std::cout << "hit rate: " << hitRate << '\n';

    return 0;
}
