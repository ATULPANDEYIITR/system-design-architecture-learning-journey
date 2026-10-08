#include <algorithm>
#include <cstdint>
#include <exception>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * Database Partitioning Case Study
 *
 * Scenario:
 * A multi-region order platform must handle a large order history.
 *
 * The system uses:
 *   - Horizontal RANGE partitioning by order date
 *   - LIST-style routing by region
 *   - HASH routing by customer ID
 *   - Vertical separation of frequently accessed and sensitive customer data
 *   - A composite month + hash design
 *
 * This is a governance-oriented simulation of the decisions a database
 * engine or data-access layer would make. It does not pretend that an
 * in-memory C++ vector is a database partition.
 */

struct Order {
    std::int64_t id;
    std::int64_t customerId;
    std::string orderDate;
    std::string region;
    std::string status;
    double amount;
};

struct CustomerOperational {
    std::int64_t customerId;
    std::string name;
    std::string email;
    std::string phone;
};

struct CustomerSensitive {
    std::int64_t customerId;
    std::string address;
    std::string dateOfBirth;
};

class PartitioningException : public std::runtime_error {
public:
    explicit PartitioningException(const std::string& message)
        : std::runtime_error(message) {}
};

class PartitionRouterException : public PartitioningException {
public:
    explicit PartitionRouterException(const std::string& message)
        : PartitioningException(message) {}
};

class RangePartition {
private:
    std::string name_;
    std::string lowerBound_;
    std::string upperBound_;
    std::vector<Order> rows_;

public:
    RangePartition(
        std::string name,
        std::string lowerBound,
        std::string upperBound)
        : name_(std::move(name)),
          lowerBound_(std::move(lowerBound)),
          upperBound_(std::move(upperBound)) {
        if (lowerBound_ >= upperBound_) {
            throw PartitioningException(
                "Range partition lower bound must precede upper bound");
        }
    }

    bool accepts(const std::string& orderDate) const {
        /*
         * ISO-8601 YYYY-MM-DD strings have lexical ordering equivalent to
         * chronological ordering, making this comparison deterministic.
         */
        return orderDate >= lowerBound_ && orderDate < upperBound_;
    }

    void insert(const Order& order) {
        if (!accepts(order.orderDate)) {
            throw PartitioningException(
                "Order violates partition boundary: " + name_);
        }

        rows_.push_back(order);
    }

    const std::string& name() const {
        return name_;
    }

    const std::vector<Order>& rows() const {
        return rows_;
    }

    const std::string& lowerBound() const {
        return lowerBound_;
    }

    const std::string& upperBound() const {
        return upperBound_;
    }
};

class OrderPartitionEngine {
private:
    std::vector<RangePartition> partitions_;

    void validateNoOverlap() const {
        for (std::size_t i = 1; i < partitions_.size(); ++i) {
            if (partitions_[i - 1].upperBound() >
                partitions_[i].lowerBound()) {
                throw PartitioningException(
                    "Horizontal partitions overlap");
            }
        }
    }

public:
    explicit OrderPartitionEngine(std::vector<RangePartition> partitions)
        : partitions_(std::move(partitions)) {
        std::sort(
            partitions_.begin(),
            partitions_.end(),
            [](const RangePartition& a, const RangePartition& b) {
                return a.lowerBound() < b.lowerBound();
            });

        validateNoOverlap();
    }

    std::string insert(const Order& order) {
        for (auto& partition : partitions_) {
            if (partition.accepts(order.orderDate)) {
                partition.insert(order);
                return partition.name();
            }
        }

        throw PartitionRouterException(
            "No horizontal partition covers " + order.orderDate);
    }

    struct QueryResult {
        std::vector<std::string> scannedPartitions;
        std::vector<Order> rows;
    };

    QueryResult queryDateRange(
        const std::string& start,
        const std::string& end) const {
        if (start >= end) {
            throw std::invalid_argument(
                "Query start must precede query end");
        }

        QueryResult result;

        /*
         * Partition pruning is a major benefit of range partitioning.
         * An interval [P.low, P.high) is relevant to [start, end) only when
         * those intervals overlap.
         */
        for (const auto& partition : partitions_) {
            const bool overlaps =
                partition.lowerBound() < end &&
                start < partition.upperBound();

            if (!overlaps) {
                continue;
            }

            result.scannedPartitions.push_back(partition.name());

            for (const auto& order : partition.rows()) {
                if (order.orderDate >= start &&
                    order.orderDate < end) {
                    result.rows.push_back(order);
                }
            }
        }

        return result;
    }

    void printDistribution() const {
        for (const auto& partition : partitions_) {
            std::cout
                << std::setw(20)
                << partition.name()
                << " rows=" << partition.rows().size()
                << '\n';
        }
    }
};

class RegionRouter {
private:
    std::unordered_map<std::string, std::string> mapping_;
    std::string defaultPartition_;

public:
    RegionRouter(
        std::unordered_map<std::string, std::string> mapping,
        std::string defaultPartition)
        : mapping_(std::move(mapping)),
          defaultPartition_(std::move(defaultPartition)) {}

    std::string route(const std::string& region) const {
        auto iterator = mapping_.find(region);

        if (iterator != mapping_.end()) {
            return iterator->second;
        }

        return defaultPartition_;
    }
};

class HashRouter {
private:
    std::size_t bucketCount_;

public:
    explicit HashRouter(std::size_t bucketCount)
        : bucketCount_(bucketCount) {
        if (bucketCount_ == 0) {
            throw std::invalid_argument(
                "Hash bucket count must be positive");
        }
    }

    std::size_t route(std::int64_t key) const {
        /*
         * std::hash is appropriate for routing within this process.
         * A distributed database must use a stable hashing strategy whose
         * behavior is compatible across nodes and versions.
         */
        return std::hash<std::int64_t>{}(key) % bucketCount_;
    }
};

class VerticalCustomerStore {
private:
    std::unordered_map<std::int64_t, CustomerOperational> operational_;
    std::unordered_map<std::int64_t, CustomerSensitive> sensitive_;

public:
    void insert(
        const CustomerOperational& operational,
        const CustomerSensitive& sensitive) {
        if (operational.customerId != sensitive.customerId) {
            throw PartitioningException(
                "Vertical fragments must share the same primary key");
        }

        if (operational_.contains(operational.customerId)) {
            throw PartitioningException(
                "Duplicate customer identifier");
        }

        operational_[operational.customerId] = operational;
        sensitive_[sensitive.customerId] = sensitive;
    }

    const CustomerOperational& operationalLookup(
        std::int64_t customerId) const {
        auto iterator = operational_.find(customerId);

        if (iterator == operational_.end()) {
            throw PartitionRouterException(
                "Customer does not exist");
        }

        return iterator->second;
    }

    std::pair<CustomerOperational, CustomerSensitive> fullLookup(
        std::int64_t customerId) const {
        const auto& operational = operationalLookup(customerId);

        auto iterator = sensitive_.find(customerId);

        if (iterator == sensitive_.end()) {
            throw PartitioningException(
                "Vertical partition integrity failure");
        }

        return {operational, iterator->second};
    }
};

class CompositePartitionEngine {
private:
    HashRouter hashRouter_;
    std::map<std::string, std::vector<Order>> partitions_;

    static std::string monthOf(const std::string& date) {
        if (date.size() < 7) {
            throw std::invalid_argument("Expected YYYY-MM-DD date");
        }

        return date.substr(0, 7);
    }

public:
    explicit CompositePartitionEngine(std::size_t hashBuckets)
        : hashRouter_(hashBuckets) {}

    std::string insert(const Order& order) {
        const std::size_t bucket =
            hashRouter_.route(order.customerId);

        const std::string key =
            monthOf(order.orderDate) +
            ":bucket:" +
            std::to_string(bucket);

        partitions_[key].push_back(order);
        return key;
    }

    std::vector<Order> findCustomer(
        const std::string& month,
        std::int64_t customerId) const {
        const std::size_t bucket =
            hashRouter_.route(customerId);

        const std::string key =
            month +
            ":bucket:" +
            std::to_string(bucket);

        std::vector<Order> result;

        auto iterator = partitions_.find(key);

        if (iterator == partitions_.end()) {
            return result;
        }

        for (const auto& order : iterator->second) {
            if (order.customerId == customerId) {
                result.push_back(order);
            }
        }

        return result;
    }
};

void printOrderIds(const std::vector<Order>& orders) {
    for (const auto& order : orders) {
        std::cout << order.id << ' ';
    }
    std::cout << '\n';
}

int main() {
    try {
        std::cout << "=== Order Repository Partitioning Engine ===\n\n";

        OrderPartitionEngine orderEngine({
            RangePartition(
                "orders_2026_q1",
                "2026-01-01",
                "2026-04-01"),
            RangePartition(
                "orders_2026_q2",
                "2026-04-01",
                "2026-07-01"),
            RangePartition(
                "orders_2026_q3",
                "2026-07-01",
                "2026-10-01"),
            RangePartition(
                "orders_2026_q4",
                "2026-10-01",
                "2027-01-01")
        });

        const std::vector<Order> orders = {
            {1001, 501, "2026-02-15", "NORTH", "PAID", 1250.50},
            {1002, 502, "2026-05-20", "SOUTH", "SHIPPED", 760.00},
            {1003, 503, "2026-08-12", "WEST", "PAID", 2100.00},
            {1004, 504, "2026-11-03", "EAST", "PENDING", 450.00}
        };

        std::cout << "Horizontal RANGE routing:\n";

        for (const auto& order : orders) {
            std::cout
                << "Order "
                << order.id
                << " -> "
                << orderEngine.insert(order)
                << '\n';
        }

        std::cout << "\nPartition distribution:\n";
        orderEngine.printDistribution();

        const auto query =
            orderEngine.queryDateRange(
                "2026-04-01",
                "2026-10-01");

        std::cout << "\nPruned date-range query:\n";
        std::cout << "Partitions scanned: ";

        for (const auto& partition : query.scannedPartitions) {
            std::cout << partition << ' ';
        }

        std::cout << "\nMatching order IDs: ";
        printOrderIds(query.rows);

        std::cout << "\n=== LIST Routing ===\n";

        RegionRouter regionRouter(
            {
                {"NORTH", "orders_north"},
                {"SOUTH", "orders_south"},
                {"EAST", "orders_east"},
                {"WEST", "orders_west"}
            },
            "orders_other");

        for (const std::string& region :
             {"NORTH", "WEST", "CENTRAL"}) {
            std::cout
                << region
                << " -> "
                << regionRouter.route(region)
                << '\n';
        }

        std::cout << "\n=== HASH Routing ===\n";

        HashRouter hashRouter(4);

        for (const std::int64_t customerId :
             {501, 502, 503, 504, 505, 506}) {
            std::cout
                << "Customer "
                << customerId
                << " -> bucket "
                << hashRouter.route(customerId)
                << '\n';
        }

        std::cout << "\n=== Vertical Partitioning ===\n";

        VerticalCustomerStore customers;

        customers.insert(
            {501, "Asha Sharma", "asha@example.com", "+91-9000000001"},
            {501, "Lucknow", "1992-03-14"});

        customers.insert(
            {502, "Rohan Mehta", "rohan@example.com", "+91-9000000002"},
            {502, "Bengaluru", "1988-08-22"});

        const auto& operational =
            customers.operationalLookup(501);

        std::cout
            << "Narrow operational lookup: "
            << operational.name
            << ", "
            << operational.email
            << '\n';

        const auto full = customers.fullLookup(501);

        std::cout
            << "Joined vertical fragments: "
            << full.first.name
            << ", "
            << full.second.address
            << ", DOB="
            << full.second.dateOfBirth
            << '\n';

        std::cout << "\n=== Composite Partitioning ===\n";

        CompositePartitionEngine composite(4);

        for (const auto& order : orders) {
            std::cout
                << "Order "
                << order.id
                << " -> "
                << composite.insert(order)
                << '\n';
        }

        /*
         * A composite query first derives the month and hash bucket,
         * narrowing the search to one physical fragment before checking
         * the customer identifier.
         */
        const auto customerOrders =
            composite.findCustomer("2026-08", 503);

        std::cout << "Customer 503 orders: ";
        printOrderIds(customerOrders);

        std::cout << "\n=== Boundary Failure ===\n";

        try {
            orderEngine.insert(
                {9001, 900, "2027-01-01", "NORTH", "PENDING", 50.00});
        } catch (const PartitionRouterException& error) {
            std::cout
                << "Expected failure: "
                << error.what()
                << '\n';
        }

        std::cout << "\n=== Architectural Trade-offs ===\n";
        std::cout
            << "Horizontal partitioning reduces the number of rows "
               "eligible for many selective queries.\n";
        std::cout
            << "Vertical partitioning reduces row width and can isolate "
               "columns with different access patterns.\n";
        std::cout
            << "Hash partitioning distributes load but provides weak "
               "locality for range predicates.\n";
        std::cout
            << "Composite partitioning can combine locality and "
               "distribution but increases operational complexity.\n";
    }
    catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
