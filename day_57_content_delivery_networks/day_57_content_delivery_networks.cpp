#include <algorithm>
#include <chrono>
#include <cstddef>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

enum class EdgeState {
    Healthy,
    Degraded,
    Offline
};

enum class ReviewLikeStatus {
    Hit,
    Miss,
    Stale,
    Bypass,
    OriginError
};

struct Content {
    std::string path;
    std::string body;
    std::string contentType;
    int version;
    int ttlSeconds;
    bool cacheable;

    void validate() const {
        if (path.empty() || path.front() != '/' ||
            path.find("..") != std::string::npos ||
            path.size() > 2048) {
            throw std::invalid_argument("Invalid content path");
        }

        if (ttlSeconds < 0) {
            throw std::invalid_argument("Negative TTL");
        }
    }
};

struct CacheEntry {
    Content content;
    long long storedAt;
};

struct RequestResult {
    ReviewLikeStatus status;
    std::string edgeId;
    int latencyMs;
    std::optional<int> version;
    std::string message;
};

class OriginServer {
private:
    std::unordered_map<std::string, Content> contents_;
    bool available_{true};

public:
    Content publish(
        const std::string& path,
        const std::string& body,
        const std::string& contentType,
        int ttlSeconds,
        bool cacheable = true
    ) {
        Content content{
            path,
            body,
            contentType,
            1,
            ttlSeconds,
            cacheable
        };

        auto existing = contents_.find(path);
        if (existing != contents_.end()) {
            content.version = existing->second.version + 1;
        }

        content.validate();
        contents_[path] = content;
        return content;
    }

    Content fetch(const std::string& path) const {
        if (!available_) {
            throw std::runtime_error("Origin server unavailable");
        }

        auto it = contents_.find(path);
        if (it == contents_.end()) {
            throw std::out_of_range("Content not found: " + path);
        }

        return it->second;
    }

    void setAvailable(bool available) {
        available_ = available;
    }
};

class EdgeServer {
private:
    std::string id_;
    std::string region_;
    std::size_t capacity_;
    int latencyMs_;
    EdgeState state_{EdgeState::Healthy};
    std::unordered_map<std::string, CacheEntry> cache_;

    std::size_t hits_{0};
    std::size_t misses_{0};
    std::size_t stale_{0};
    std::size_t evictions_{0};

public:
    EdgeServer(
        std::string id,
        std::string region,
        std::size_t capacity,
        int latencyMs
    )
        : id_(std::move(id)),
          region_(std::move(region)),
          capacity_(capacity),
          latencyMs_(latencyMs) {
        if (capacity_ == 0) {
            throw std::invalid_argument("Edge capacity cannot be zero");
        }
        if (latencyMs_ < 0) {
            throw std::invalid_argument("Negative edge latency");
        }
    }

    const std::string& id() const { return id_; }
    const std::string& region() const { return region_; }
    int latencyMs() const { return latencyMs_; }
    EdgeState state() const { return state_; }

    void setState(EdgeState state) {
        state_ = state;
    }

    std::optional<Content> lookup(
        const std::string& path,
        long long now
    ) {
        if (state_ == EdgeState::Offline) {
            return std::nullopt;
        }

        auto it = cache_.find(path);
        if (it == cache_.end()) {
            ++misses_;
            return std::nullopt;
        }

        const auto age = now - it->second.storedAt;
        if (age >= it->second.content.ttlSeconds) {
            cache_.erase(it);
            ++stale_;
            return std::nullopt;
        }

        ++hits_;
        return it->second.content;
    }

    void store(const Content& content, long long now) {
        if (!content.cacheable || state_ == EdgeState::Offline) {
            return;
        }

        cache_[content.path] = CacheEntry{content, now};

        if (cache_.size() > capacity_) {
            // A compact deterministic eviction policy is sufficient for this
            // governance simulation. Production CDNs commonly use LRU variants.
            auto victim = cache_.begin();
            cache_.erase(victim);
            ++evictions_;
        }
    }

    bool invalidate(const std::string& path) {
        return cache_.erase(path) > 0;
    }

    std::size_t hits() const { return hits_; }
    std::size_t misses() const { return misses_; }
    std::size_t stale() const { return stale_; }
    std::size_t evictions() const { return evictions_; }
};

class CdnGovernanceEngine {
private:
    OriginServer& origin_;
    std::vector<EdgeServer> edges_;
    std::map<std::pair<std::string, std::string>, int> distances_;

    std::size_t requests_{0};
    std::size_t originFetches_{0};
    std::size_t invalidRequests_{0};

    int distance(
        const std::string& from,
        const std::string& to
    ) const {
        if (from == to) {
            return 0;
        }

        auto it = distances_.find({from, to});
        return it == distances_.end() ? 100 : it->second;
    }

    EdgeServer* chooseEdge(const std::string& clientRegion) {
        EdgeServer* best = nullptr;
        int bestScore = 0;

        for (auto& edge : edges_) {
            if (edge.state() == EdgeState::Offline) {
                continue;
            }

            const int healthPenalty =
                edge.state() == EdgeState::Degraded ? 1000 : 0;

            const int score =
                distance(clientRegion, edge.region()) +
                edge.latencyMs() +
                healthPenalty;

            if (best == nullptr || score < bestScore) {
                best = &edge;
                bestScore = score;
            }
        }

        return best;
    }

    static bool validPath(const std::string& path) {
        return !path.empty() &&
               path.front() == '/' &&
               path.find("..") == std::string::npos &&
               path.find('\0') == std::string::npos &&
               path.size() <= 2048;
    }

public:
    explicit CdnGovernanceEngine(OriginServer& origin)
        : origin_(origin) {}

    void addEdge(EdgeServer edge) {
        edges_.push_back(std::move(edge));
    }

    void setDistance(
        const std::string& a,
        const std::string& b,
        int latencyMs
    ) {
        if (latencyMs < 0) {
            throw std::invalid_argument("Negative geographic latency");
        }

        distances_[{a, b}] = latencyMs;
        distances_[{b, a}] = latencyMs;
    }

    RequestResult request(
        const std::string& path,
        const std::string& clientRegion,
        long long now,
        bool authorized = false
    ) {
        ++requests_;

        if (!validPath(path)) {
            ++invalidRequests_;
            return {
                ReviewLikeStatus::Bypass,
                "",
                0,
                std::nullopt,
                "Rejected malformed request path"
            };
        }

        const bool privatePath =
            path.rfind("/private/", 0) == 0;

        if (privatePath && !authorized) {
            return {
                ReviewLikeStatus::Bypass,
                "",
                0,
                std::nullopt,
                "Authorization required"
            };
        }

        EdgeServer* edge = chooseEdge(clientRegion);

        if (edge == nullptr) {
            return {
                ReviewLikeStatus::OriginError,
                "",
                0,
                std::nullopt,
                "No available edge server"
            };
        }

        if (!privatePath) {
            auto cached = edge->lookup(path, now);

            if (cached.has_value()) {
                return {
                    ReviewLikeStatus::Hit,
                    edge->id(),
                    distance(clientRegion, edge->region()) +
                        edge->latencyMs(),
                    cached->version,
                    "Served from edge cache"
                };
            }
        }

        try {
            Content content = origin_.fetch(path);
            ++originFetches_;

            if (!privatePath) {
                edge->store(content, now);
            }

            return {
                privatePath
                    ? ReviewLikeStatus::Bypass
                    : ReviewLikeStatus::Miss,
                edge->id(),
                distance(clientRegion, edge->region()) +
                    edge->latencyMs() + 80,
                content.version,
                privatePath
                    ? "Private origin response"
                    : "Origin response cached at edge"
            };
        } catch (const std::exception& ex) {
            return {
                ReviewLikeStatus::OriginError,
                edge->id(),
                distance(clientRegion, edge->region()) +
                    edge->latencyMs(),
                std::nullopt,
                ex.what()
            };
        }
    }

    std::size_t invalidate(const std::string& path) {
        std::size_t affected = 0;

        for (auto& edge : edges_) {
            if (edge.invalidate(path)) {
                ++affected;
            }
        }

        return affected;
    }

    void printMetrics() const {
        std::size_t hits = 0;
        std::size_t misses = 0;
        std::size_t stale = 0;
        std::size_t evictions = 0;

        for (const auto& edge : edges_) {
            hits += edge.hits();
            misses += edge.misses();
            stale += edge.stale();
            evictions += edge.evictions();
        }

        const double hitRatio =
            requests_ == 0
                ? 0.0
                : static_cast<double>(hits) / requests_;

        std::cout
            << "requests=" << requests_
            << " hits=" << hits
            << " misses=" << misses
            << " stale=" << stale
            << " evictions=" << evictions
            << " origin_fetches=" << originFetches_
            << " invalid_requests=" << invalidRequests_
            << " hit_ratio=" << hitRatio
            << '\n';
    }
};

static const char* statusName(ReviewLikeStatus status) {
    switch (status) {
        case ReviewLikeStatus::Hit: return "HIT";
        case ReviewLikeStatus::Miss: return "MISS";
        case ReviewLikeStatus::Stale: return "STALE";
        case ReviewLikeStatus::Bypass: return "BYPASS";
        case ReviewLikeStatus::OriginError: return "ORIGIN_ERROR";
    }
    return "UNKNOWN";
}

int main() {
    try {
        OriginServer origin;

        origin.publish(
            "/static/app.js",
            "console.log('release-1');",
            "application/javascript",
            30
        );

        origin.publish(
            "/static/logo.svg",
            "<svg>logo</svg>",
            "image/svg+xml",
            60
        );

        origin.publish(
            "/private/audit.json",
            "{\"classification\":\"internal\"}",
            "application/json",
            60,
            false
        );

        CdnGovernanceEngine cdn(origin);

        cdn.addEdge(
            EdgeServer("edge-delhi", "DEL", 2, 8)
        );
        cdn.addEdge(
            EdgeServer("edge-mumbai", "BOM", 2, 12)
        );
        cdn.addEdge(
            EdgeServer("edge-singapore", "SIN", 2, 10)
        );
        cdn.addEdge(
            EdgeServer("edge-london", "LON", 2, 18)
        );

        cdn.setDistance("DEL", "BOM", 18);
        cdn.setDistance("DEL", "SIN", 65);
        cdn.setDistance("DEL", "LON", 120);
        cdn.setDistance("BOM", "SIN", 55);
        cdn.setDistance("BOM", "LON", 130);
        cdn.setDistance("SIN", "LON", 160);

        const t0 = 1000;

        auto first =
            cdn.request("/static/app.js", "DEL", t0);

        auto second =
            cdn.request("/static/app.js", "DEL", t0 + 2);

        auto image =
            cdn.request("/static/logo.svg", "SIN", t0 + 3);

        auto privateResponse =
            cdn.request(
                "/private/audit.json",
                "DEL",
                t0 + 4,
                true
            );

        std::cout
            << "first=" << statusName(first.status)
            << " version="
            << (first.version ? std::to_string(*first.version) : "none")
            << '\n';

        std::cout
            << "second=" << statusName(second.status)
            << " version="
            << (second.version ? std::to_string(*second.version) : "none")
            << '\n';

        std::cout
            << "image=" << statusName(image.status)
            << '\n';

        std::cout
            << "private=" << statusName(privateResponse.status)
            << '\n';

        if (second.status != ReviewLikeStatus::Hit) {
            throw std::runtime_error(
                "Expected second request to be a cache hit"
            );
        }

        // Update origin content. Existing edge copies remain version 1 until
        // expiration or explicit invalidation.
        origin.publish(
            "/static/app.js",
            "console.log('release-2');",
            "application/javascript",
            30
        );

        const auto invalidated =
            cdn.invalidate("/static/app.js");

        std::cout
            << "invalidated_copies=" << invalidated
            << '\n';

        const auto refreshed =
            cdn.request("/static/app.js", "DEL", t0 + 5);

        std::cout
            << "refreshed=" << statusName(refreshed.status)
            << " version="
            << (refreshed.version
                ? std::to_string(*refreshed.version)
                : "none")
            << '\n';

        // Origin failure is handled as a request result rather than a process
        // failure, allowing an edge layer to apply a higher-level fallback.
        origin.setAvailable(false);

        const auto failure =
            cdn.request("/unknown.json", "BOM", t0 + 100);

        std::cout
            << "failure=" << statusName(failure.status)
            << " message=" << failure.message
            << '\n';

        cdn.printMetrics();

        if (!refreshed.version || *refreshed.version != 2) {
            throw std::runtime_error(
                "Cache invalidation did not expose version 2"
            );
        }

        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "CDN engine failure: " << ex.what() << '\n';
        return 1;
    }
}
