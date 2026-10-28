#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <list>
#include <optional>
#include <regex>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using Clock = std::chrono::system_clock;
using TimePoint = Clock::time_point;

enum class CacheStatus {
    Hit,
    Miss,
    Revalidated,
    Bypass,
    Stale
};

enum class MergeDecision {
    Eligible,
    Blocked
};

struct OriginResponse {
    int status{};
    std::string body;
    std::string contentType;
    std::string etag;
    std::string cacheControl;
};

struct Request {
    std::string method;
    std::string host;
    std::string path;
    std::string query;
    bool authenticated{false};
};

struct CachePolicy {
    int defaultTtlSeconds{60};
    int maxTtlSeconds{3600};
    bool cacheAuthenticated{false};
};

struct StatusCheck {
    std::string name;
    bool required{true};
    bool passed{false};
};

struct Review {
    std::string reviewer;
    bool approval{false};
    bool stale{false};
};

struct BranchProtection {
    bool requirePullRequest{true};
    int requiredApprovals{2};
    bool requireAllChecks{true};
    bool restrictDirectPush{true};
    bool restrictForcePush{true};
    bool restrictDeletion{true};
    bool requireConversationResolution{true};
    bool requireLinearHistory{false};
};

struct PullRequest {
    int id{};
    std::string sourceBranch;
    std::string targetBranch;
    bool open{true};
    bool draft{false};
    bool conversationsResolved{true};
    bool hasMergeConflict{false};
    std::vector<StatusCheck> checks;
    std::vector<Review> reviews;
};

class OriginServer {
private:
    std::unordered_map<std::string, OriginResponse> objects_;
    std::size_t fetches_{0};

public:
    void publish(
        const std::string& path,
        const std::string& body,
        const std::string& contentType,
        const std::string& cacheControl,
        const std::string& etag
    ) {
        objects_[path] = {
            200,
            body,
            contentType,
            etag,
            cacheControl
        };
    }

    std::pair<OriginResponse, bool> fetch(
        const std::string& path,
        const std::string& ifNoneMatch = ""
    ) {
        ++fetches_;

        auto it = objects_.find(path);
        if (it == objects_.end()) {
            return {
                {404, "Not Found", "text/plain", "404", "no-store"},
                false
            };
        }

        if (!ifNoneMatch.empty() && ifNoneMatch == it->second.etag) {
            return {it->second, true};
        }

        return {it->second, false};
    }

    std::size_t fetchCount() const {
        return fetches_;
    }
};

struct CacheEntry {
    OriginResponse response;
    TimePoint expiresAt;
};

class EdgeCache {
private:
    struct Node {
        std::string key;
        CacheEntry entry;
    };

    std::size_t capacity_;
    std::list<Node> lru_;
    std::unordered_map<std::string, std::list<Node>::iterator> index_;

    int ttlFromHeaders(const std::string& cacheControl, const CachePolicy& policy) {
        std::regex pattern(R"(max-age=(\d+))");
        std::smatch match;

        if (std::regex_search(cacheControl, match, pattern)) {
            int ttl = std::stoi(match[1].str());
            return std::min(ttl, policy.maxTtlSeconds);
        }

        return policy.defaultTtlSeconds;
    }

public:
    explicit EdgeCache(std::size_t capacity)
        : capacity_(capacity) {
        if (capacity == 0) {
            throw std::invalid_argument("edge capacity must be positive");
        }
    }

    bool cacheable(const OriginResponse& response) const {
        return response.cacheControl.find("no-store") == std::string::npos &&
               response.cacheControl.find("private") == std::string::npos;
    }

    std::optional<CacheEntry> get(
        const std::string& key,
        TimePoint now
    ) {
        auto it = index_.find(key);
        if (it == index_.end()) {
            return std::nullopt;
        }

        auto node = it->second;
        CacheEntry result = node->entry;

        lru_.splice(lru_.end(), lru_, node);
        return result;
    }

    void put(
        const std::string& key,
        const OriginResponse& response,
        TimePoint now,
        const CachePolicy& policy
    ) {
        if (!cacheable(response)) {
            return;
        }

        auto existing = index_.find(key);
        if (existing != index_.end()) {
            lru_.erase(existing->second);
            index_.erase(existing);
        }

        int ttl = ttlFromHeaders(response.cacheControl, policy);

        lru_.push_back({
            key,
            {response, now + std::chrono::seconds(ttl)}
        });

        auto iterator = std::prev(lru_.end());
        index_[key] = iterator;

        while (lru_.size() > capacity_) {
            auto oldest = lru_.begin();
            index_.erase(oldest->key);
            lru_.pop_front();
        }
    }

    std::size_t invalidatePath(const std::string& path) {
        std::size_t removed = 0;

        for (auto it = lru_.begin(); it != lru_.end();) {
            if (it->key.find("|" + path + "|") != std::string::npos) {
                index_.erase(it->key);
                it = lru_.erase(it);
                ++removed;
            } else {
                ++it;
            }
        }

        return removed;
    }

    std::size_t size() const {
        return lru_.size();
    }
};

class CDN {
private:
    OriginServer& origin_;
    CachePolicy policy_;
    std::unordered_map<std::string, EdgeCache> edges_;

    EdgeCache& route(const std::string& region) {
        static const std::unordered_map<std::string, std::string> preferred{
            {"india", "blr"},
            {"europe", "fra"},
            {"north-america", "iad"}
        };

        auto preferredIt = preferred.find(region);

        if (preferredIt != preferred.end()) {
            auto edgeIt = edges_.find(preferredIt->second);
            if (edgeIt != edges_.end()) {
                return edgeIt->second;
            }
        }

        return edges_.begin()->second;
    }

    std::string cacheKey(const Request& request) const {
        return request.host + "|" +
               request.method + "|" +
               request.path + "|" +
               request.query;
    }

public:
    CDN(OriginServer& origin, CachePolicy policy)
        : origin_(origin), policy_(std::move(policy)) {
        edges_.emplace("blr", EdgeCache(2));
        edges_.emplace("fra", EdgeCache(2));
        edges_.emplace("iad", EdgeCache(2));
    }

    struct Result {
        OriginResponse response;
        CacheStatus status;
        std::string edge;
    };

    Result request(
        const Request& request,
        const std::string& region,
        TimePoint now
    ) {
        EdgeCache& edge = route(region);
        const std::string key = cacheKey(request);

        if (request.method != "GET" && request.method != "HEAD") {
            auto [response, unused] = origin_.fetch(request.path);
            return {response, CacheStatus::Bypass, "dynamic-origin"};
        }

        if (request.authenticated && !policy_.cacheAuthenticated) {
            auto [response, unused] = origin_.fetch(request.path);
            return {response, CacheStatus::Bypass, "authenticated-origin"};
        }

        auto cached = edge.get(key, now);

        if (cached.has_value() && cached->expiresAt > now) {
            return {cached->response, CacheStatus::Hit, region};
        }

        if (cached.has_value()) {
            auto [response, notModified] =
                origin_.fetch(request.path, cached->response.etag);

            if (notModified) {
                edge.put(key, response, now, policy_);
                return {response, CacheStatus::Revalidated, region};
            }

            edge.put(key, response, now, policy_);
            return {response, CacheStatus::Stale, region};
        }

        auto [response, unused] = origin_.fetch(request.path);
        edge.put(key, response, now, policy_);

        return {response, CacheStatus::Miss, region};
    }

    std::size_t purge(const std::string& path) {
        std::size_t count = 0;

        for (auto& [name, edge] : edges_) {
            count += edge.invalidatePath(path);
        }

        return count;
    }

    void report() const {
        for (const auto& [name, edge] : edges_) {
            std::cout
                << "edge=" << name
                << " cached_objects=" << edge.size()
                << '\n';
        }
    }
};

class GovernanceEngine {
private:
    BranchProtection policy_;

public:
    explicit GovernanceEngine(BranchProtection policy)
        : policy_(std::move(policy)) {}

    MergeDecision evaluate(const PullRequest& pr) const {
        if (!pr.open || pr.draft) {
            return MergeDecision::Blocked;
        }

        if (pr.sourceBranch.empty() || pr.targetBranch.empty()) {
            return MergeDecision::Blocked;
        }

        if (pr.hasMergeConflict) {
            return MergeDecision::Blocked;
        }

        if (policy_.requireConversationResolution &&
            !pr.conversationsResolved) {
            return MergeDecision::Blocked;
        }

        if (policy_.requireAllChecks) {
            for (const auto& check : pr.checks) {
                if (check.required && !check.passed) {
                    return MergeDecision::Blocked;
                }
            }
        }

        int validApprovals = 0;

        for (const auto& review : pr.reviews) {
            if (review.approval && !review.stale) {
                ++validApprovals;
            }
        }

        if (validApprovals < policy_.requiredApprovals) {
            return MergeDecision::Blocked;
        }

        return MergeDecision::Eligible;
    }
};

std::string statusName(CacheStatus status) {
    switch (status) {
        case CacheStatus::Hit: return "HIT";
        case CacheStatus::Miss: return "MISS";
        case CacheStatus::Revalidated: return "REVALIDATED";
        case CacheStatus::Bypass: return "BYPASS";
        case CacheStatus::Stale: return "STALE";
    }

    return "UNKNOWN";
}

int main() {
    try {
        OriginServer origin;

        origin.publish(
            "/assets/app.js",
            "release-42",
            "application/javascript",
            "public, max-age=120",
            "etag-app-42"
        );

        origin.publish(
            "/index.html",
            "<html>release-42</html>",
            "text/html",
            "public, max-age=20",
            "etag-html-42"
        );

        CachePolicy cachePolicy{
            30,
            300,
            false
        };

        CDN cdn(origin, cachePolicy);

        const TimePoint start = Clock::now();

        Request asset{
            "GET",
            "example.test",
            "/assets/app.js",
            "",
            false
        };

        auto first = cdn.request(asset, "india", start);
        auto second = cdn.request(
            asset,
            "india",
            start + std::chrono::seconds(10)
        );

        std::cout
            << "First request: "
            << statusName(first.status)
            << " status=" << first.response.status
            << '\n';

        std::cout
            << "Second request: "
            << statusName(second.status)
            << " status=" << second.response.status
            << '\n';

        auto revalidated = cdn.request(
            asset,
            "india",
            start + std::chrono::seconds(150)
        );

        std::cout
            << "Expired request: "
            << statusName(revalidated.status)
            << " status=" << revalidated.response.status
            << '\n';

        Request authenticated{
            "GET",
            "example.test",
            "/account",
            "",
            true
        };

        auto privateResult = cdn.request(
            authenticated,
            "india",
            start + std::chrono::seconds(5)
        );

        std::cout
            << "Authenticated request: "
            << statusName(privateResult.status)
            << '\n';

        std::cout << "Origin fetches: "
                  << origin.fetchCount()
                  << '\n';

        std::cout << "\nCache state:\n";
        cdn.report();

        std::cout
            << "Purged entries: "
            << cdn.purge("/assets/app.js")
            << '\n';

        BranchProtection protection{
            true,
            2,
            true,
            true,
            true,
            true,
            true,
            false
        };

        PullRequest pullRequest{
            42,
            "feature/cache-policy",
            "main",
            true,
            false,
            true,
            false,
            {
                {"unit-tests", true, true},
                {"security-scan", true, true},
                {"performance-test", true, true}
            },
            {
                {"reviewer-a", true, false},
                {"reviewer-b", true, false},
                {"reviewer-c", true, true}
            }
        };

        GovernanceEngine governance(protection);

        std::cout
            << "Governance merge decision: "
            << (governance.evaluate(pullRequest) ==
                        MergeDecision::Eligible
                    ? "ELIGIBLE"
                    : "BLOCKED")
            << '\n';

    } catch (const std::exception& error) {
        std::cerr << "Failure: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
