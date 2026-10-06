/*
 * SQL vs NoSQL: repository-scale commerce platform case study.
 *
 * C++17 program demonstrating:
 * - relational normalization
 * - document aggregation
 * - key-value access
 * - transaction-like rollback
 * - optimistic concurrency
 * - partitioning
 * - consistency behavior
 * - workload-oriented database selection
 *
 * Compile:
 *   g++ -std=c++17 -O2 sql_vs_nosql.cpp -o sql_vs_nosql
 */

#include <algorithm>
#include <chrono>
#include <exception>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

struct Customer {
    int id;
    std::string name;
    std::string email;
};

struct Product {
    int id;
    std::string name;
    std::string category;
    double price;
};

struct Order {
    int id;
    int customerId;
    std::string status;
    double total;
};

struct OrderItem {
    int orderId;
    int productId;
    int quantity;
    double unitPrice;
};

class RelationalCommerceStore {
private:
    std::unordered_map<int, Customer> customers;
    std::unordered_map<int, Product> products;
    std::unordered_map<int, Order> orders;
    std::vector<OrderItem> items;

public:
    void addCustomer(Customer customer) {
        if (customer.id <= 0 || customer.email.empty()) {
            throw std::invalid_argument(
                "Customer identifier and email are required"
            );
        }

        if (customers.contains(customer.id)) {
            throw std::runtime_error(
                "Duplicate customer primary key"
            );
        }

        for (const auto& [id, existing] : customers) {
            if (existing.email == customer.email) {
                throw std::runtime_error(
                    "Customer email violates uniqueness"
                );
            }
        }

        customers.emplace(customer.id, std::move(customer));
    }

    void addProduct(Product product) {
        if (product.price < 0.0) {
            throw std::invalid_argument(
                "Product price cannot be negative"
            );
        }

        if (products.contains(product.id)) {
            throw std::runtime_error(
                "Duplicate product primary key"
            );
        }

        products.emplace(product.id, std::move(product));
    }

    void addOrder(Order order) {
        if (!customers.contains(order.customerId)) {
            throw std::runtime_error(
                "Foreign-key violation: customer missing"
            );
        }

        if (orders.contains(order.id)) {
            throw std::runtime_error(
                "Duplicate order primary key"
            );
        }

        order.total = 0.0;
        orders.emplace(order.id, std::move(order));
    }

    void addItem(OrderItem item) {
        if (!orders.contains(item.orderId)) {
            throw std::runtime_error(
                "Foreign-key violation: order missing"
            );
        }

        if (!products.contains(item.productId)) {
            throw std::runtime_error(
                "Foreign-key violation: product missing"
            );
        }

        if (item.quantity <= 0) {
            throw std::invalid_argument(
                "Quantity must be positive"
            );
        }

        items.push_back(item);
        recalculateTotal(item.orderId);
    }

    void recalculateTotal(int orderId) {
        auto& order = orders.at(orderId);

        order.total = 0.0;

        for (const auto& item : items) {
            if (item.orderId == orderId) {
                order.total +=
                    item.quantity * item.unitPrice;
            }
        }
    }

    std::vector<std::string> customerOrderReport(
        int customerId
    ) const {
        std::vector<std::string> report;

        auto customerIt = customers.find(customerId);

        if (customerIt == customers.end()) {
            return report;
        }

        for (const auto& [orderId, order] : orders) {
            if (order.customerId != customerId) {
                continue;
            }

            for (const auto& item : items) {
                if (item.orderId != orderId) {
                    continue;
                }

                const auto& product =
                    products.at(item.productId);

                std::ostringstream row;
                row << customerIt->second.name
                    << " | order=" << orderId
                    << " | product=" << product.name
                    << " | quantity=" << item.quantity
                    << " | line_total="
                    << item.quantity * item.unitPrice;

                report.push_back(row.str());
            }
        }

        return report;
    }

    template <typename Operation>
    void transaction(Operation operation) {
        auto customersBackup = customers;
        auto productsBackup = products;
        auto ordersBackup = orders;
        auto itemsBackup = items;

        try {
            operation();
        } catch (...) {
            customers = std::move(customersBackup);
            products = std::move(productsBackup);
            orders = std::move(ordersBackup);
            items = std::move(itemsBackup);
            throw;
        }
    }

    std::size_t orderCount() const {
        return orders.size();
    }
};

struct DocumentOrder {
    std::string id;
    std::string status;
    std::string customerName;
    std::vector<std::string> products;
    std::optional<std::string> shippingCountry;
};

class DocumentCommerceStore {
private:
    std::unordered_map<std::string, DocumentOrder> orders;

public:
    void insert(DocumentOrder order) {
        if (order.id.empty()) {
            throw std::invalid_argument(
                "Document id cannot be empty"
            );
        }

        if (orders.contains(order.id)) {
            throw std::runtime_error(
                "Duplicate document id"
            );
        }

        orders.emplace(order.id, std::move(order));
    }

    const DocumentOrder& get(
        const std::string& id
    ) const {
        return orders.at(id);
    }

    void updateStatus(
        const std::string& id,
        const std::string& status
    ) {
        auto& order = orders.at(id);

        if (
            order.status == "CANCELLED" &&
            status != "CANCELLED"
        ) {
            throw std::logic_error(
                "Cancelled document cannot be reopened"
            );
        }

        order.status = status;
    }
};

class KeyValueSessionStore {
private:
    std::unordered_map<std::string, std::string> values;

public:
    void put(
        const std::string& key,
        const std::string& value
    ) {
        if (key.empty()) {
            throw std::invalid_argument(
                "Key cannot be empty"
            );
        }

        values[key] = value;
    }

    std::optional<std::string> get(
        const std::string& key
    ) const {
        auto it = values.find(key);

        if (it == values.end()) {
            return std::nullopt;
        }

        return it->second;
    }
};

struct VersionedDocument {
    std::string status;
    int version;
};

class OptimisticConcurrencyStore {
private:
    std::unordered_map<
        std::string,
        VersionedDocument
    > records;

public:
    void create(
        const std::string& key,
        std::string status
    ) {
        if (records.contains(key)) {
            throw std::runtime_error(
                "Record already exists"
            );
        }

        records.emplace(
            key,
            VersionedDocument{std::move(status), 1}
        );
    }

    VersionedDocument read(
        const std::string& key
    ) const {
        return records.at(key);
    }

    void update(
        const std::string& key,
        std::string newStatus,
        int expectedVersion
    ) {
        auto& record = records.at(key);

        if (record.version != expectedVersion) {
            throw std::runtime_error(
                "Optimistic concurrency conflict"
            );
        }

        record.status = std::move(newStatus);
        ++record.version;
    }
};

class EventualConsistencyCluster {
private:
    std::unordered_map<
        std::string,
        std::string
    > primary;

    std::vector<
        std::unordered_map<std::string, std::string>
    > replicas;

public:
    explicit EventualConsistencyCluster(
        std::size_t replicaCount
    )
        : replicas(replicaCount) {}

    void write(
        const std::string& key,
        const std::string& value
    ) {
        primary[key] = value;
    }

    std::optional<std::string> readReplica(
        std::size_t replica,
        const std::string& key
    ) const {
        if (replica >= replicas.size()) {
            throw std::out_of_range(
                "Replica does not exist"
            );
        }

        const auto& node = replicas[replica];

        auto it = node.find(key);

        if (it == node.end()) {
            return std::nullopt;
        }

        return it->second;
    }

    void synchronize() {
        for (auto& replica : replicas) {
            replica = primary;
        }
    }
};

enum class Workload {
    FinancialLedger,
    FlexibleCatalog,
    SessionLookup,
    RelationshipHeavyReporting
};

std::string selectDatabase(Workload workload) {
    switch (workload) {
        case Workload::FinancialLedger:
            return "SQL";

        case Workload::FlexibleCatalog:
            return "Document NoSQL";

        case Workload::SessionLookup:
            return "Key-Value NoSQL";

        case Workload::RelationshipHeavyReporting:
            return "SQL";
    }

    return "Benchmark required";
}

void demonstrateRelationalModel() {
    std::cout << "\n=== RELATIONAL MODEL ===\n";

    RelationalCommerceStore store;

    store.addCustomer({
        1,
        "Asha Rao",
        "asha@example.com"
    });

    store.addProduct({
        10,
        "Laptop",
        "Computing",
        1200.0
    });

    store.addProduct({
        11,
        "Keyboard",
        "Accessories",
        80.0
    });

    store.addOrder({
        1001,
        1,
        "PAID",
        0.0
    });

    store.addItem({
        1001,
        10,
        1,
        1200.0
    });

    store.addItem({
        1001,
        11,
        2,
        80.0
    });

    for (const auto& row :
         store.customerOrderReport(1)) {
        std::cout << row << '\n';
    }
}

void demonstrateConstraints() {
    std::cout << "\n=== RELATIONAL CONSTRAINT FAILURE ===\n";

    RelationalCommerceStore store;

    store.addCustomer({
        1,
        "Asha Rao",
        "asha@example.com"
    });

    try {
        store.addCustomer({
            2,
            "Another Asha",
            "asha@example.com"
        });
    } catch (const std::exception& error) {
        std::cout << "Rejected: "
                  << error.what() << '\n';
    }
}

void demonstrateTransaction() {
    std::cout << "\n=== TRANSACTION ROLLBACK ===\n";

    RelationalCommerceStore store;

    store.addCustomer({
        1,
        "Asha Rao",
        "asha@example.com"
    });

    store.transaction([&]() {
        store.addOrder({
            1001,
            1,
            "PENDING",
            0.0
        });

        store.addProduct({
            10,
            "Laptop",
            "Computing",
            1200.0
        });

        store.addItem({
            1001,
            10,
            1,
            1200.0
        });
    });

    std::cout
        << "Committed order count: "
        << store.orderCount() << '\n';

    try {
        store.transaction([&]() {
            store.addOrder({
                1002,
                1,
                "PENDING",
                0.0
            });

            store.addItem({
                1002,
                999,
                1,
                10.0
            });
        });
    } catch (const std::exception& error) {
        std::cout
            << "Transaction failed and rolled back: "
            << error.what() << '\n';
    }

    std::cout
        << "Order count after rollback: "
        << store.orderCount() << '\n';
}

void demonstrateDocumentModel() {
    std::cout << "\n=== DOCUMENT MODEL ===\n";

    DocumentCommerceStore store;

    store.insert({
        "order-2001",
        "PENDING",
        "Rohan Mehta",
        {"Laptop", "Keyboard"},
        std::string("IN")
    });

    const auto& order = store.get("order-2001");

    std::cout
        << "Document "
        << order.id
        << " contains "
        << order.products.size()
        << " embedded product entries.\n";

    store.updateStatus(
        "order-2001",
        "PAID"
    );

    std::cout
        << "Document status after update: "
        << store.get("order-2001").status
        << '\n';
}

void demonstrateKeyValueModel() {
    std::cout << "\n=== KEY-VALUE MODEL ===\n";

    KeyValueSessionStore store;

    store.put(
        "session:user:42",
        "{\"userId\":42,\"role\":\"customer\"}"
    );

    auto value =
        store.get("session:user:42");

    if (value) {
        std::cout
            << "Direct key lookup: "
            << *value << '\n';
    }
}

void demonstrateConsistency() {
    std::cout << "\n=== EVENTUAL CONSISTENCY ===\n";

    EventualConsistencyCluster cluster(2);

    cluster.write(
        "inventory:laptop",
        "9"
    );

    auto before =
        cluster.readReplica(
            0,
            "inventory:laptop"
        );

    std::cout
        << "Replica before synchronization: "
        << (before ? *before : "STALE/MISSING")
        << '\n';

    cluster.synchronize();

    auto after =
        cluster.readReplica(
            0,
            "inventory:laptop"
        );

    std::cout
        << "Replica after synchronization: "
        << (after ? *after : "MISSING")
        << '\n';
}

void demonstrateOptimisticConcurrency() {
    std::cout
        << "\n=== OPTIMISTIC CONCURRENCY ===\n";

    OptimisticConcurrencyStore store;

    store.create(
        "order-3001",
        "PENDING"
    );

    auto clientA =
        store.read("order-3001");

    auto clientB =
        store.read("order-3001");

    store.update(
        "order-3001",
        "PAID",
        clientA.version
    );

    try {
        store.update(
            "order-3001",
            "CANCELLED",
            clientB.version
        );
    } catch (const std::exception& error) {
        std::cout
            << "Stale update rejected: "
            << error.what()
            << '\n';
    }

    auto finalState =
        store.read("order-3001");

    std::cout
        << "Final status: "
        << finalState.status
        << ", version: "
        << finalState.version
        << '\n';
}

void demonstratePartitioning() {
    std::cout << "\n=== HASH PARTITIONING ===\n";

    constexpr int partitionCount = 4;

    std::map<int, std::vector<int>> partitions;

    for (int orderId = 1000;
         orderId < 1010;
         ++orderId) {
        int partition =
            orderId % partitionCount;

        partitions[partition].push_back(
            orderId
        );
    }

    for (const auto& [partition, ids] :
         partitions) {
        std::cout
            << "Partition "
            << partition
            << ": ";

        for (int id : ids) {
            std::cout << id << ' ';
        }

        std::cout << '\n';
    }

    std::cout
        << "Partitioning can distribute data across "
           "nodes, but the partition key determines "
           "whether requests remain efficiently routable.\n";
}

void demonstrateWorkloadSelection() {
    std::cout
        << "\n=== WORKLOAD-DRIVEN DATABASE SELECTION ===\n";

    std::cout
        << "Financial ledger: "
        << selectDatabase(
            Workload::FinancialLedger
        )
        << '\n';

    std::cout
        << "Flexible catalog: "
        << selectDatabase(
            Workload::FlexibleCatalog
        )
        << '\n';

    std::cout
        << "Session lookup: "
        << selectDatabase(
            Workload::SessionLookup
        )
        << '\n';

    std::cout
        << "Relationship-heavy reporting: "
        << selectDatabase(
            Workload::RelationshipHeavyReporting
        )
        << '\n';
}

int main() {
    try {
        demonstrateRelationalModel();
        demonstrateConstraints();
        demonstrateTransaction();
        demonstrateDocumentModel();
        demonstrateKeyValueModel();
        demonstrateConsistency();
        demonstrateOptimisticConcurrency();
        demonstratePartitioning();
        demonstrateWorkloadSelection();

        std::cout
            << "\nDatabase architecture should be selected "
               "from workload, consistency, transaction, "
               "relationship, scaling, and operational "
               "requirements rather than database fashion.\n";
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
