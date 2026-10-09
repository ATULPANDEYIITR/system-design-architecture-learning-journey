#include <algorithm>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Repository-independent case study: a multi-tenant order platform.
 *
 * The C++ program models a shard-aware storage gateway with deterministic
 * hashing, customer co-location, metadata lookup, range routing, and a
 * guarded shard-migration operation. It intentionally uses an injected
 * stable hash function interface; std::hash is not a portable persistent
 * placement contract across all implementations or versions.
 */

class ShardingError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct Customer {
    std::string id;
    std::string region;
};

struct Order {
    std::string id;
    std::string customerId;
    std::int64_t amountCents;
    std::string createdAt;
};

struct Shard {
    std::string id;
    bool available = true;
    std::uint64_t version = 0;
    std::map<std::string, Customer> customers;
    std::map<std::string, Order> orders;

    void requireAvailable() const {
        if (!available) {
            throw ShardingError("Shard " + id + " is unavailable");
        }
    }
};

class StableHasher {
public:
    virtual ~StableHasher() = default;
    virtual std::uint64_t hash(const std::string& value) const = 0;
};

/*
 * FNV-1a is used here for a compact deterministic placement demonstration.
 * Production routing should use a well-reviewed hash and explicit versioning.
 */
class Fnv1aHasher final : public StableHasher {
public:
    std::uint64_t hash(const std::string& value) const override {
        std::uint64_t result = 14695981039346656037ULL;
        for (unsigned char character : value) {
            result ^= character;
            result *= 1099511628211ULL;
        }
        return result;
    }
};

class ConsistentHashRouter {
private:
    struct Node {
        std::uint64_t position;
        std::string shardId;
    };

    std::vector<Node> ring_;
    const StableHasher& hasher_;
    std::size_t virtualNodes_;

public:
    ConsistentHashRouter(const StableHasher& hasher,
                         std::size_t virtualNodes = 128)
        : hasher_(hasher), virtualNodes_(virtualNodes) {
        if (virtualNodes_ == 0) {
            throw std::invalid_argument("virtualNodes must be positive");
        }
    }

    void rebuild(const std::set<std::string>& shardIds) {
        ring_.clear();

        for (const auto& shardId : shardIds) {
            if (shardId.empty()) {
                throw std::invalid_argument("Empty shard identifier");
            }

            for (std::size_t index = 0; index < virtualNodes_; ++index) {
                const std::string nodeKey =
                    shardId + ":virtual:" + std::to_string(index);
                ring_.push_back({hasher_.hash(nodeKey), shardId});
            }
        }

        std::sort(ring_.begin(), ring_.end(),
                  [](const Node& left, const Node& right) {
                      if (left.position != right.position) {
                          return left.position < right.position;
                      }
                      return left.shardId < right.shardId;
                  });
    }

    std::string route(const std::string& key) const {
        if (key.empty()) {
            throw std::invalid_argument("Shard key cannot be empty");
        }
        if (ring_.empty()) {
            throw ShardingError("No shards are registered");
        }

        const std::uint64_t position = hasher_.hash(key);
        const auto iterator = std::lower_bound(
            ring_.begin(), ring_.end(), position,
            [](const Node& node, std::uint64_t target) {
                return node.position < target;
            });

        return iterator == ring_.end() ? ring_.front().shardId
                                       : iterator->shardId;
    }
};

class RangeRouter {
private:
    struct Range {
        std::int64_t start;
        std::int64_t end;
        std::string shardId;
    };

    std::vector<Range> ranges_;

public:
    void addRange(std::int64_t start,
                  std::int64_t end,
                  std::string shardId) {
        if (start >= end || shardId.empty()) {
            throw std::invalid_argument("Invalid shard range");
        }

        for (const auto& existing : ranges_) {
            if (start < existing.end && existing.start < end) {
                throw std::invalid_argument("Shard ranges overlap");
            }
        }

        ranges_.push_back({start, end, std::move(shardId)});
        std::sort(ranges_.begin(), ranges_.end(),
                  [](const Range& left, const Range& right) {
                      return left.start < right.start;
                  });
    }

    std::string route(std::int64_t key) const {
        const auto iterator = std::find_if(
            ranges_.begin(), ranges_.end(),
            [key](const Range& range) {
                return range.start <= key && key < range.end;
            });

        if (iterator == ranges_.end()) {
            throw ShardingError("No range owns the requested key");
        }

        return iterator->shardId;
    }
};

class OrderStorageGateway {
private:
    const StableHasher& hasher_;
    ConsistentHashRouter router_;
    std::map<std::string, Shard> shards_;
    std::unordered_map<std::string, std::string> customerLocations_;
    std::unordered_map<std::string, std::string> orderLocations_;

    std::string routeCustomer(const std::string& customerId) const {
        return router_.route(customerId);
    }

    Shard& requireShard(const std::string& shardId) {
        auto iterator = shards_.find(shardId);
        if (iterator == shards_.end()) {
            throw ShardingError("Unknown shard " + shardId);
        }
        iterator->second.requireAvailable();
        return iterator->second;
    }

    const Shard& requireShard(const std::string& shardId) const {
        auto iterator = shards_.find(shardId);
        if (iterator == shards_.end()) {
            throw ShardingError("Unknown shard " + shardId);
        }
        iterator->second.requireAvailable();
        return iterator->second;
    }

public:
    OrderStorageGateway(const StableHasher& hasher,
                        const std::vector<std::string>& shardIds)
        : hasher_(hasher), router_(hasher_) {
        if (shardIds.empty()) {
            throw std::invalid_argument("At least one shard is required");
        }

        std::set<std::string> uniqueIds;
        for (const auto& id : shardIds) {
            if (id.empty() || !uniqueIds.insert(id).second) {
                throw std::invalid_argument(
                    "Shard IDs must be non-empty and unique");
            }
            shards_.emplace(id, Shard{id});
        }

        router_.rebuild(uniqueIds);
    }

    std::string createCustomer(const Customer& customer) {
        if (customer.id.empty()) {
            throw std::invalid_argument("Customer ID cannot be empty");
        }
        if (customerLocations_.count(customer.id)) {
            throw ShardingError("Duplicate customer " + customer.id);
        }

        const std::string shardId = routeCustomer(customer.id);
        Shard& shard = requireShard(shardId);
        shard.customers.emplace(customer.id, customer);
        ++shard.version;
        customerLocations_[customer.id] = shardId;

        return shardId;
    }

    std::string createOrder(const Order& order) {
        if (order.id.empty() || order.customerId.empty()) {
            throw std::invalid_argument("Order and customer IDs are required");
        }
        if (order.amountCents < 0) {
            throw std::invalid_argument("Order amount cannot be negative");
        }
        if (orderLocations_.count(order.id)) {
            throw ShardingError("Duplicate order " + order.id);
        }

        const auto customerLocation =
            customerLocations_.find(order.customerId);

        if (customerLocation == customerLocations_.end()) {
            throw ShardingError("Order references an unknown customer");
        }

        // The customer directory ensures writes use the current owner.
        const std::string shardId = customerLocation->second;
        Shard& shard = requireShard(shardId);

        if (!shard.customers.count(order.customerId)) {
            throw ShardingError("Customer metadata disagrees with storage");
        }

        shard.orders.emplace(order.id, order);
        ++shard.version;
        orderLocations_[order.id] = shardId;

        return shardId;
    }

    std::optional<Order> getOrder(const std::string& orderId) const {
        const auto location = orderLocations_.find(orderId);
        if (location == orderLocations_.end()) {
            return std::nullopt;
        }

        const Shard& shard = requireShard(location->second);
        const auto record = shard.orders.find(orderId);
        if (record == shard.orders.end()) {
            throw ShardingError("Order index points to missing storage");
        }

        return record->second;
    }

    std::vector<Order> ordersForCustomer(
        const std::string& customerId) const {
        const auto location = customerLocations_.find(customerId);
        if (location == customerLocations_.end()) {
            return {};
        }

        const Shard& shard = requireShard(location->second);
        std::vector<Order> result;

        for (const auto& entry : shard.orders) {
            if (entry.second.customerId == customerId) {
                result.push_back(entry.second);
            }
        }

        std::sort(result.begin(), result.end(),
                  [](const Order& left, const Order& right) {
                      return left.createdAt < right.createdAt;
                  });
        return result;
    }

    std::map<std::string, std::int64_t> scatterGatherRevenue() const {
        std::map<std::string, std::int64_t> totals;

        // A full aggregation touches every shard and therefore has a larger
        // latency and failure surface than a single-customer query.
        for (const auto& entry : shards_) {
            entry.second.requireAvailable();

            for (const auto& orderEntry : entry.second.orders) {
                const Order& order = orderEntry.second;
                totals[order.customerId] += order.amountCents;
            }
        }

        return totals;
    }

    void setAvailability(const std::string& shardId, bool available) {
        auto iterator = shards_.find(shardId);
        if (iterator == shards_.end()) {
            throw ShardingError("Unknown shard " + shardId);
        }
        iterator->second.available = available;
    }

    std::map<std::string, std::size_t> orderCounts() const {
        std::map<std::string, std::size_t> result;
        for (const auto& entry : shards_) {
            result[entry.first] = entry.second.orders.size();
        }
        return result;
    }

    /*
     * This controlled migration moves one customer and its orders together.
     * A production implementation must also fence concurrent writes,
     * replicate the migration log, persist the directory update, and recover
     * safely after partial failures.
     */
    std::size_t migrateCustomer(const std::string& customerId,
                                const std::string& targetShardId) {
        const auto location = customerLocations_.find(customerId);
        if (location == customerLocations_.end()) {
            throw ShardingError("Cannot migrate an unknown customer");
        }

        const std::string sourceShardId = location->second;
        if (sourceShardId == targetShardId) {
            return 0;
        }

        Shard& source = requireShard(sourceShardId);
        Shard& target = requireShard(targetShardId);

        if (target.customers.count(customerId)) {
            throw ShardingError("Target already contains the customer");
        }

        auto customerIterator = source.customers.find(customerId);
        if (customerIterator == source.customers.end()) {
            throw ShardingError("Customer record is missing at source");
        }

        std::vector<Order> movingOrders;
        for (const auto& entry : source.orders) {
            if (entry.second.customerId == customerId) {
                if (target.orders.count(entry.first)) {
                    throw ShardingError("Target already contains an order");
                }
                movingOrders.push_back(entry.second);
            }
        }

        const Customer customerCopy = customerIterator->second;

        target.customers.emplace(customerId, customerCopy);
        for (const auto& order : movingOrders) {
            target.orders.emplace(order.id, order);
        }

        // Verify every destination record before switching directory entries.
        if (!target.customers.count(customerId)) {
            throw ShardingError("Customer copy verification failed");
        }
        for (const auto& order : movingOrders) {
            if (!target.orders.count(order.id)) {
                throw ShardingError("Order copy verification failed");
            }
        }

        customerLocations_[customerId] = targetShardId;
        for (const auto& order : movingOrders) {
            orderLocations_[order.id] = targetShardId;
        }

        source.customers.erase(customerId);
        for (const auto& order : movingOrders) {
            source.orders.erase(order.id);
        }

        ++source.version;
        ++target.version;
        return movingOrders.size() + 1;
    }

    std::vector<std::string> validateDirectory() const {
        std::vector<std::string> errors;

        for (const auto& entry : customerLocations_) {
            auto shard = shards_.find(entry.second);
            if (shard == shards_.end() ||
                !shard->second.customers.count(entry.first)) {
                errors.push_back("Invalid customer location: " + entry.first);
            }
        }

        for (const auto& entry : orderLocations_) {
            auto shard = shards_.find(entry.second);
            if (shard == shards_.end() ||
                !shard->second.orders.count(entry.first)) {
                errors.push_back("Invalid order location: " + entry.first);
            }
        }

        return errors;
    }

    std::vector<std::string> shardIds() const {
        std::vector<std::string> result;
        for (const auto& entry : shards_) {
            result.push_back(entry.first);
        }
        return result;
    }
};

int main() {
    try {
        Fnv1aHasher hasher;

        OrderStorageGateway database(
            hasher, {"orders-east", "orders-central", "orders-west"});

        const std::vector<Customer> customers = {
            {"cust-100", "north"},
            {"cust-200", "south"},
            {"cust-300", "west"},
            {"cust-400", "east"}
        };

        std::cout << "CUSTOMER PLACEMENT\n";
        for (const auto& customer : customers) {
            std::cout << customer.id << " -> "
                      << database.createCustomer(customer) << '\n';
        }

        const std::vector<Order> orders = {
            {"ord-001", "cust-100", 1299, "2026-10-01T09:00:00Z"},
            {"ord-002", "cust-100", 4599, "2026-10-02T11:30:00Z"},
            {"ord-003", "cust-200", 899, "2026-10-03T15:15:00Z"},
            {"ord-004", "cust-300", 2599, "2026-10-04T10:20:00Z"}
        };

        for (const auto& order : orders) {
            database.createOrder(order);
        }

        std::cout << "\nCUSTOMER-LOCAL QUERY\n";
        for (const auto& order : database.ordersForCustomer("cust-100")) {
            std::cout << order.id << " amount="
                      << order.amountCents << " cents\n";
        }

        std::cout << "\nSCATTER-GATHER REVENUE\n";
        for (const auto& entry : database.scatterGatherRevenue()) {
            std::cout << entry.first << ": "
                      << entry.second << " cents\n";
        }

        std::cout << "\nSHARD ORDER COUNTS\n";
        for (const auto& entry : database.orderCounts()) {
            std::cout << entry.first << ": " << entry.second << '\n';
        }

        std::cout << "\nCONTROLLED CUSTOMER MIGRATION\n";
        const auto source = database.shardIds().front();
        const auto target = database.shardIds().back();

        if (source != target) {
            try {
                const auto moved =
                    database.migrateCustomer("cust-100", target);
                std::cout << "Moved records: " << moved << '\n';
                std::cout << "Remaining orders for cust-100: "
                          << database.ordersForCustomer("cust-100").size()
                          << '\n';
            } catch (const ShardingError& error) {
                std::cout << "Migration rejected: " << error.what() << '\n';
            }
        }

        std::cout << "\nFAILURE HANDLING\n";
        const auto shardIds = database.shardIds();
        database.setAvailability(shardIds.front(), false);

        try {
            database.scatterGatherRevenue();
        } catch (const ShardingError& error) {
            std::cout << "Aggregate failed safely: "
                      << error.what() << '\n';
        }

        database.setAvailability(shardIds.front(), true);

        std::cout << "\nDIRECTORY VALIDATION\n";
        const auto errors = database.validateDirectory();
        if (errors.empty()) {
            std::cout << "All location entries match stored records.\n";
        } else {
            for (const auto& error : errors) {
                std::cout << error << '\n';
            }
        }

        std::cout << "\nRANGE ROUTING\n";
        RangeRouter rangeRouter;
        rangeRouter.addRange(0, 1000, "orders-000");
        rangeRouter.addRange(1000, 2000, "orders-001");
        rangeRouter.addRange(2000, 3000, "orders-002");

        for (std::int64_t key : {0, 999, 1000, 1999, 2000, 2999}) {
            std::cout << key << " -> "
                      << rangeRouter.route(key) << '\n';
        }

        try {
            rangeRouter.route(3000);
        } catch (const ShardingError& error) {
            std::cout << "Boundary rejected: " << error.what() << '\n';
        }

        std::cout << "\nAll case-study operations completed.\n";
    } catch (const std::exception& error) {
        std::cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
