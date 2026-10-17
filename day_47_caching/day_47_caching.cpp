#include <algorithm>
#include <chrono>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <optional>
#include <shared_mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using Clock = std::chrono::steady_clock;

struct PullRequestLikeResource {
    std::string id;
    std::string repository;
    std::string branch;
    int version;
    std::string payload;
};

/*
 * Technical case study:
 *
 * A repository governance service repeatedly evaluates whether a pull request
 * can be merged. The evaluation combines branch policy, review decisions and
 * status checks. Those inputs are expensive to load from the authoritative
 * repository service, so the governance layer caches immutable snapshots.
 *
 * The important caching problem is not simply "store a value in memory".
 * The system must decide:
 *   - what uniquely identifies an evaluation,
 *   - how long the evaluation remains valid,
 *   - which mutations invalidate it,
 *   - how concurrent misses are handled,
 *   - and whether stale policy information could permit an unsafe merge.
 */

struct CacheStatistics {
    std::size_t hits = 0;
    std::size_t misses = 0;
    std::size_t writes = 0;
    std::size_t evictions = 0;
    std::size_t invalidations = 0;
};

template <typename K, typename V>
class LruCache {
private:
    struct Entry {
        V value;
        Clock::time_point expiresAt;
        std::unordered_set<std::string> tags;
    };

    std::size_t capacity_;
    std::chrono::milliseconds ttl_;
    std::unordered_map<K, Entry> values_;
    std::vector<K> recency_;
    mutable std::shared_mutex mutex_;
    CacheStatistics statistics_;

    void touch(const K& key) {
        recency_.erase(
            std::remove(recency_.begin(), recency_.end(), key),
            recency_.end()
        );
        recency_.push_back(key);
    }

    void evictIfNecessary() {
        while (values_.size() > capacity_) {
            const K& oldest = recency_.front();
            values_.erase(oldest);
            recency_.erase(recency_.begin());
            statistics_.evictions++;
        }
    }

public:
    LruCache(std::size_t capacity, std::chrono::milliseconds ttl)
        : capacity_(capacity), ttl_(ttl) {
        if (capacity == 0) {
            throw std::invalid_argument("cache capacity must be positive");
        }
        if (ttl.count() <= 0) {
            throw std::invalid_argument("cache TTL must be positive");
        }
    }

    std::optional<V> get(const K& key) {
        std::unique_lock lock(mutex_);

        auto it = values_.find(key);

        if (it == values_.end()) {
            statistics_.misses++;
            return std::nullopt;
        }

        if (Clock::now() >= it->second.expiresAt) {
            values_.erase(it);
            recency_.erase(
                std::remove(recency_.begin(), recency_.end(), key),
                recency_.end()
            );
            statistics_.misses++;
            return std::nullopt;
        }

        touch(key);
        statistics_.hits++;
        return it->second.value;
    }

    void put(
        const K& key,
        const V& value,
        std::unordered_set<std::string> tags = {}
    ) {
        std::unique_lock lock(mutex_);

        values_[key] = Entry{
            value,
            Clock::now() + ttl_,
            std::move(tags)
        };

        touch(key);
        statistics_.writes++;
        evictIfNecessary();
    }

    void invalidateTag(const std::string& tag) {
        std::unique_lock lock(mutex_);

        for (auto it = values_.begin(); it != values_.end();) {
            if (it->second.tags.contains(tag)) {
                const K key = it->first;
                it = values_.erase(it);
                recency_.erase(
                    std::remove(recency_.begin(), recency_.end(), key),
                    recency_.end()
                );
                statistics_.invalidations++;
            } else {
                ++it;
            }
        }
    }

    CacheStatistics statistics() const {
        std::shared_lock lock(mutex_);
        return statistics_;
    }
};


struct Review {
    std::string reviewer;
    bool approved;
};

struct StatusCheck {
    std::string name;
    bool passed;
};

struct BranchPolicy {
    std::string branch;
    int requiredApprovals;
    std::vector<std::string> requiredChecks;
    bool requireLinearHistory;
    bool allowForcePush;
    bool allowDirectPush;
};


struct MergeDecision {
    bool eligible;
    std::vector<std::string> reasons;
};


class AuthoritativeGovernanceStore {
private:
    BranchPolicy protectedBranch_{
        "main",
        2,
        {"build", "security-scan"},
        true,
        false,
        false
    };

    std::unordered_map<int, std::vector<Review>> reviews_;
    std::unordered_map<int, std::vector<StatusCheck>> checks_;
    std::unordered_map<int, int> versions_;

public:
    AuthoritativeGovernanceStore() {
        reviews_[101] = {
            {"reviewer-alice", true},
            {"reviewer-bob", true}
        };

        checks_[101] = {
            {"build", true},
            {"security-scan", true}
        };

        versions_[101] = 1;
    }

    BranchPolicy branchPolicy() const {
        std::this_thread::sleep_for(std::chrono::milliseconds(15));
        return protectedBranch_;
    }

    std::vector<Review> reviews(int pullRequest) const {
        std::this_thread::sleep_for(std::chrono::milliseconds(15));

        auto it = reviews_.find(pullRequest);
        return it == reviews_.end()
            ? std::vector<Review>{}
            : it->second;
    }

    std::vector<StatusCheck> checks(int pullRequest) const {
        std::this_thread::sleep_for(std::chrono::milliseconds(15));

        auto it = checks_.find(pullRequest);
        return it == checks_.end()
            ? std::vector<StatusCheck>{}
            : it->second;
    }

    int version(int pullRequest) const {
        return versions_.at(pullRequest);
    }

    void revokeApproval(int pullRequest, const std::string& reviewer) {
        auto& reviews = reviews_[pullRequest];

        for (auto& review : reviews) {
            if (review.reviewer == reviewer) {
                review.approved = false;
            }
        }

        versions_[pullRequest]++;
    }
};


class MergeEligibilityEngine {
private:
    AuthoritativeGovernanceStore& store;

    LruCache<std::string, MergeDecision> cache{
        64,
        std::chrono::seconds(20)
    };

    /*
     * The key contains the pull request identity and version. A version-aware
     * key is stronger than a plain "PR 101" key because a review mutation
     * changes the governance state and therefore the answer.
     */
    std::string makeKey(int pullRequest, int version) const {
        return "merge:" + std::to_string(pullRequest)
            + ":v" + std::to_string(version);
    }

    MergeDecision evaluateAuthoritatively(int pullRequest) {
        BranchPolicy policy = store.branchPolicy();
        auto reviews = store.reviews(pullRequest);
        auto checks = store.checks(pullRequest);

        MergeDecision decision{true, {}};

        if (policy.branch != "main") {
            decision.eligible = false;
            decision.reasons.push_back("target branch is not the protected main branch");
        }

        const auto approvals = std::count_if(
            reviews.begin(),
            reviews.end(),
            [](const Review& review) {
                return review.approved;
            }
        );

        if (approvals < policy.requiredApprovals) {
            decision.eligible = false;
            decision.reasons.push_back("required approvals are not satisfied");
        }

        for (const auto& required : policy.requiredChecks) {
            auto check = std::find_if(
                checks.begin(),
                checks.end(),
                [&](const StatusCheck& candidate) {
                    return candidate.name == required;
                }
            );

            if (check == checks.end() || !check->passed) {
                decision.eligible = false;
                decision.reasons.push_back(
                    "required status check failed or is missing: " + required
                );
            }
        }

        return decision;
    }

public:
    explicit MergeEligibilityEngine(AuthoritativeGovernanceStore& source)
        : store(source) {}

    MergeDecision evaluate(int pullRequest) {
        const int version = store.version(pullRequest);
        const std::string key = makeKey(pullRequest, version);

        if (auto cached = cache.get(key)) {
            return *cached;
        }

        MergeDecision decision = evaluateAuthoritatively(pullRequest);

        cache.put(
            key,
            decision,
            {"pull-request:" + std::to_string(pullRequest)}
        );

        return decision;
    }

    void invalidatePullRequest(int pullRequest) {
        cache.invalidateTag(
            "pull-request:" + std::to_string(pullRequest)
        );
    }

    CacheStatistics statistics() const {
        return cache.statistics();
    }
};


void printDecision(const std::string& label, const MergeDecision& decision) {
    std::cout << label
              << (decision.eligible ? "ELIGIBLE" : "BLOCKED")
              << '\n';

    for (const auto& reason : decision.reasons) {
        std::cout << "  - " << reason << '\n';
    }
}


int main() {
    try {
        std::cout << std::boolalpha;
        std::cout << "Repository governance caching case study\n\n";

        AuthoritativeGovernanceStore store;
        MergeEligibilityEngine engine(store);

        auto first = engine.evaluate(101);
        printDecision("First evaluation: ", first);

        auto second = engine.evaluate(101);
        printDecision("Second evaluation: ", second);

        auto statistics = engine.statistics();

        std::cout << "\nAfter repeated evaluation:\n";
        std::cout << "Cache hits: " << statistics.hits << '\n';
        std::cout << "Cache misses: " << statistics.misses << '\n';
        std::cout << "Cache writes: " << statistics.writes << '\n';

        /*
         * Approval state changes the correctness of the merge decision.
         * Versioning makes the new state naturally address a different cache
         * entry, while explicit invalidation provides immediate cleanup.
         */
        store.revokeApproval(101, "reviewer-bob");
        engine.invalidatePullRequest(101);

        auto afterRevocation = engine.evaluate(101);
        printDecision("After approval revocation: ", afterRevocation);

        /*
         * A cache should never be treated as the authoritative source for a
         * security-sensitive governance decision unless its consistency model
         * is strong enough for the policy. This engine uses versioned state and
         * explicit invalidation because an obsolete approval could otherwise
         * produce an unsafe merge decision.
         */

        auto finalStats = engine.statistics();

        std::cout << "\nFinal cache statistics:\n";
        std::cout << "Hits: " << finalStats.hits << '\n';
        std::cout << "Misses: " << finalStats.misses << '\n';
        std::cout << "Writes: " << finalStats.writes << '\n';
        std::cout << "Invalidations: " << finalStats.invalidations << '\n';

        return afterRevocation.eligible ? 1 : 0;
    }
    catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}
