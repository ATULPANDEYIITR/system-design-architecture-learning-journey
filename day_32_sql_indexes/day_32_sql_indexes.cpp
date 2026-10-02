#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

/*
 * SQL Indexes: B-Tree Indexes and Query Performance
 *
 * Case study:
 * A commerce database stores orders. A repository-style governance layer is
 * intentionally absent because the subject is SQL indexing rather than source
 * control. The technical system instead models how a database could choose
 * between a table scan and B-Tree access for customer, status, and date
 * predicates.
 *
 * The program demonstrates:
 * - heap-table pages
 * - a balanced B-Tree index
 * - equality and range predicates
 * - composite index ordering
 * - selectivity
 * - estimated logical page I/O
 * - index maintenance after an update
 * - covering/index-only access
 * - validation and failure handling
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic main.cpp -o index_case_study
 */

struct Order {
    int order_id;
    int customer_id;
    std::string status;
    int order_date;
    double total_amount;
};


class IndexError : public std::runtime_error {
public:
    explicit IndexError(const std::string& message)
        : std::runtime_error(message) {}
};


class OrdersTable {
private:
    std::size_t rows_per_page_;
    std::vector<std::vector<Order>> pages_;
    std::unordered_map<int, std::pair<std::size_t, std::size_t>> locations_;
    std::unordered_map<int, Order> rows_;

public:
    explicit OrdersTable(std::size_t rows_per_page)
        : rows_per_page_(rows_per_page) {
        if (rows_per_page_ == 0) {
            throw IndexError("rows_per_page must be greater than zero");
        }
    }

    void insert(const Order& order) {
        if (rows_.contains(order.order_id)) {
            throw IndexError(
                "Duplicate order_id: " + std::to_string(order.order_id)
            );
        }

        if (pages_.empty() ||
            pages_.back().size() >= rows_per_page_) {
            pages_.push_back({});
        }

        const std::size_t page_id = pages_.size() - 1;
        const std::size_t slot = pages_.back().size();

        pages_.back().push_back(order);
        locations_[order.order_id] = {page_id, slot};
        rows_[order.order_id] = order;
    }

    Order update(
        int order_id,
        std::optional<int> customer_id = std::nullopt,
        std::optional<std::string> status = std::nullopt,
        std::optional<int> order_date = std::nullopt,
        std::optional<double> total_amount = std::nullopt
    ) {
        auto iterator = rows_.find(order_id);

        if (iterator == rows_.end()) {
            throw IndexError(
                "Cannot update unknown order_id: " +
                std::to_string(order_id)
            );
        }

        Order updated = iterator->second;

        if (customer_id) {
            updated.customer_id = *customer_id;
        }

        if (status) {
            updated.status = *status;
        }

        if (order_date) {
            updated.order_date = *order_date;
        }

        if (total_amount) {
            updated.total_amount = *total_amount;
        }

        const auto [page_id, slot] = locations_.at(order_id);
        pages_[page_id][slot] = updated;
        rows_[order_id] = updated;

        return updated;
    }

    std::pair<std::vector<Order>, std::size_t> fullScan(
        const std::function<bool(const Order&)>& predicate
    ) const {
        std::vector<Order> result;

        for (const auto& page : pages_) {
            for (const auto& row : page) {
                if (predicate(row)) {
                    result.push_back(row);
                }
            }
        }

        return {result, pages_.size()};
    }

    std::pair<std::vector<Order>, std::size_t> fetchRows(
        const std::vector<int>& order_ids
    ) const {
        std::vector<Order> result;
        std::set<std::size_t> pages_touched;

        std::set<int> unique_ids(
            order_ids.begin(),
            order_ids.end()
        );

        for (int order_id : unique_ids) {
            auto location = locations_.find(order_id);

            if (location == locations_.end()) {
                continue;
            }

            pages_touched.insert(location->second.first);
            result.push_back(rows_.at(order_id));
        }

        return {result, pages_touched.size()};
    }

    const std::unordered_map<int, Order>& rows() const {
        return rows_;
    }

    std::size_t rowCount() const {
        return rows_.size();
    }

    std::size_t pageCount() const {
        return pages_.size();
    }
};


class BTreeIndex {
private:
    struct Node {
        bool leaf = true;
        std::vector<int> keys;
        std::vector<std::vector<int>> values;
        std::vector<Node*> children;

        explicit Node(bool is_leaf = true)
            : leaf(is_leaf) {}
    };

    std::string name_;
    std::size_t max_keys_;
    Node* root_;
    std::unordered_map<int, int> order_to_key_;

    static std::size_t lowerBound(
        const std::vector<int>& values,
        int key
    ) {
        return static_cast<std::size_t>(
            std::lower_bound(values.begin(), values.end(), key)
            - values.begin()
        );
    }

    static std::size_t upperBound(
        const std::vector<int>& values,
        int key
    ) {
        return static_cast<std::size_t>(
            std::upper_bound(values.begin(), values.end(), key)
            - values.begin()
        );
    }

    void destroy(Node* node) {
        if (node == nullptr) {
            return;
        }

        for (Node* child : node->children) {
            destroy(child);
        }

        delete node;
    }

    void splitChild(Node* parent, std::size_t child_index) {
        Node* child = parent->children.at(child_index);
        const std::size_t middle = child->keys.size() / 2;

        const int promoted_key = child->keys.at(middle);
        const std::vector<int> promoted_values =
            child->values.at(middle);

        Node* right = new Node(child->leaf);

        right->keys.assign(
            child->keys.begin() + static_cast<std::ptrdiff_t>(middle + 1),
            child->keys.end()
        );

        right->values.assign(
            child->values.begin() + static_cast<std::ptrdiff_t>(middle + 1),
            child->values.end()
        );

        if (!child->leaf) {
            right->children.assign(
                child->children.begin() +
                    static_cast<std::ptrdiff_t>(middle + 1),
                child->children.end()
            );

            child->children.resize(middle + 1);
        }

        child->keys.resize(middle);
        child->values.resize(middle);

        parent->keys.insert(
            parent->keys.begin() +
                static_cast<std::ptrdiff_t>(child_index),
            promoted_key
        );

        parent->values.insert(
            parent->values.begin() +
                static_cast<std::ptrdiff_t>(child_index),
            promoted_values
        );

        parent->children.insert(
            parent->children.begin() +
                static_cast<std::ptrdiff_t>(child_index + 1),
            right
        );
    }

    void insertNonFull(Node* node, int key, int order_id) {
        if (node->leaf) {
            const std::size_t position =
                lowerBound(node->keys, key);

            if (position < node->keys.size() &&
                node->keys[position] == key) {
                node->values[position].push_back(order_id);
                return;
            }

            node->keys.insert(
                node->keys.begin() +
                    static_cast<std::ptrdiff_t>(position),
                key
            );

            node->values.insert(
                node->values.begin() +
                    static_cast<std::ptrdiff_t>(position),
                {order_id}
            );

            return;
        }

        std::size_t position = upperBound(node->keys, key);

        if (node->children.at(position)->keys.size() >= max_keys_) {
            splitChild(node, position);

            if (key > node->keys.at(position)) {
                ++position;
            } else if (key == node->keys.at(position)) {
                node->values.at(position).push_back(order_id);
                return;
            }
        }

        insertNonFull(
            node->children.at(position),
            key,
            order_id
        );
    }

    std::pair<const Node*, std::size_t> findNode(
        int key,
        std::size_t& visits
    ) const {
        const Node* node = root_;

        while (true) {
            ++visits;

            const std::size_t position =
                lowerBound(node->keys, key);

            if (position < node->keys.size() &&
                node->keys[position] == key) {
                return {node, position};
            }

            if (node->leaf) {
                return {nullptr, 0};
            }

            node = node->children.at(position);
        }
    }

    void rangeWalk(
        const Node* node,
        int lower,
        int upper,
        std::vector<int>& result,
        std::size_t& visits
    ) const {
        ++visits;

        if (node->leaf) {
            const std::size_t begin =
                lowerBound(node->keys, lower);

            const std::size_t end =
                upperBound(node->keys, upper);

            for (std::size_t i = begin; i < end; ++i) {
                result.insert(
                    result.end(),
                    node->values[i].begin(),
                    node->values[i].end()
                );
            }

            return;
        }

        const std::size_t first_child =
            lowerBound(node->keys, lower);

        const std::size_t last_child =
            upperBound(node->keys, upper);

        for (std::size_t i = first_child;
             i <= last_child;
             ++i) {
            rangeWalk(
                node->children.at(i),
                lower,
                upper,
                result,
                visits
            );
        }

        const std::size_t begin =
            lowerBound(node->keys, lower);

        const std::size_t end =
            upperBound(node->keys, upper);

        for (std::size_t i = begin; i < end; ++i) {
            result.insert(
                result.end(),
                node->values[i].begin(),
                node->values[i].end()
            );
        }
    }

public:
    BTreeIndex(
        std::string name,
        std::size_t max_keys
    )
        : name_(std::move(name)),
          max_keys_(max_keys),
          root_(new Node(true)) {
        if (max_keys_ < 3) {
            throw IndexError("A B-Tree node requires at least three keys");
        }
    }

    ~BTreeIndex() {
        destroy(root_);
    }

    BTreeIndex(const BTreeIndex&) = delete;
    BTreeIndex& operator=(const BTreeIndex&) = delete;

    void insert(int order_id, int key) {
        if (order_to_key_.contains(order_id)) {
            erase(order_id);
        }

        order_to_key_[order_id] = key;

        if (root_->keys.size() >= max_keys_) {
            Node* old_root = root_;
            root_ = new Node(false);
            root_->children.push_back(old_root);
            splitChild(root_, 0);
        }

        insertNonFull(root_, key, order_id);
    }

    void erase(int order_id) {
        auto iterator = order_to_key_.find(order_id);

        if (iterator == order_to_key_.end()) {
            return;
        }

        std::vector<std::pair<int, int>> remaining;

        for (const auto& [id, key] : order_to_key_) {
            if (id != order_id) {
                remaining.emplace_back(id, key);
            }
        }

        order_to_key_.erase(iterator);

        destroy(root_);
        root_ = new Node(true);

        for (const auto& [id, key] : remaining) {
            if (root_->keys.size() >= max_keys_) {
                Node* old_root = root_;
                root_ = new Node(false);
                root_->children.push_back(old_root);
                splitChild(root_, 0);
            }

            insertNonFull(root_, key, id);
        }
    }

    std::pair<std::vector<int>, std::size_t> equalityLookup(
        int key
    ) const {
        std::size_t visits = 0;
        auto [node, position] = findNode(key, visits);

        if (node == nullptr) {
            return {{}, visits};
        }

        return {node->values.at(position), visits};
    }

    std::pair<std::vector<int>, std::size_t> rangeLookup(
        int lower,
        int upper
    ) const {
        if (lower > upper) {
            throw IndexError(
                "Range lower bound cannot exceed upper bound"
            );
        }

        std::vector<int> result;
        std::size_t visits = 0;

        rangeWalk(
            root_,
            lower,
            upper,
            result,
            visits
        );

        return {result, visits};
    }

    std::size_t height() const {
        std::size_t height = 1;
        const Node* node = root_;

        while (!node->leaf) {
            ++height;
            node = node->children.front();
        }

        return height;
    }

    std::size_t entryCount() const {
        return order_to_key_.size();
    }

    const std::string& name() const {
        return name_;
    }
};


class CompositeIndex {
private:
    struct Entry {
        std::pair<int, int> key;
        int order_id;
    };

    std::vector<Entry> entries_;

    static bool lessKey(
        const std::pair<int, int>& left,
        const std::pair<int, int>& right
    ) {
        return left < right;
    }

    std::size_t lowerBound(
        const std::pair<int, int>& target
    ) const {
        std::size_t low = 0;
        std::size_t high = entries_.size();

        while (low < high) {
            const std::size_t middle =
                low + (high - low) / 2;

            if (lessKey(entries_[middle].key, target)) {
                low = middle + 1;
            } else {
                high = middle;
            }
        }

        return low;
    }

public:
    void build(const std::vector<Order>& orders) {
        entries_.clear();

        for (const Order& order : orders) {
            entries_.push_back({
                {order.customer_id, order.order_date},
                order.order_id
            });
        }

        std::sort(
            entries_.begin(),
            entries_.end(),
            [](const Entry& left, const Entry& right) {
                return left.key < right.key;
            }
        );
    }

    std::vector<int> customerDateRange(
        int customer_id,
        int start_date,
        int end_date
    ) const {
        const std::size_t begin =
            lowerBound({customer_id, start_date});

        const std::size_t end =
            lowerBound({customer_id, end_date + 1});

        std::vector<int> result;

        for (std::size_t i = begin; i < end; ++i) {
            if (entries_[i].key.first != customer_id) {
                break;
            }

            result.push_back(entries_[i].order_id);
        }

        return result;
    }

    std::vector<int> customerOnly(int customer_id) const {
        const std::size_t begin =
            lowerBound({customer_id, 0});

        std::vector<int> result;

        for (std::size_t i = begin;
             i < entries_.size();
             ++i) {
            if (entries_[i].key.first != customer_id) {
                break;
            }

            result.push_back(entries_[i].order_id);
        }

        return result;
    }
};


struct QueryPlan {
    std::string access_path;
    std::string index_name;
    std::size_t estimated_rows;
    std::size_t estimated_page_reads;
    std::string reason;
};


class QueryPlanner {
private:
    const OrdersTable& table_;
    const BTreeIndex& customer_index_;
    const BTreeIndex& status_index_;

public:
    QueryPlanner(
        const OrdersTable& table,
        const BTreeIndex& customer_index,
        const BTreeIndex& status_index
    )
        : table_(table),
          customer_index_(customer_index),
          status_index_(status_index) {}

    QueryPlan customerEquals(int customer_id) const {
        auto [ids, tree_visits] =
            customer_index_.equalityLookup(customer_id);

        if (ids.empty()) {
            return {
                "Index Seek",
                customer_index_.name(),
                0,
                tree_visits,
                "The B-Tree proves that no matching key exists."
            };
        }

        auto [rows, table_pages] =
            table_.fetchRows(ids);

        const std::size_t index_cost =
            tree_visits + table_pages;

        const std::size_t scan_cost =
            table_.pageCount();

        if (index_cost < scan_cost) {
            return {
                "Index Seek + Table Lookup",
                customer_index_.name(),
                rows.size(),
                index_cost,
                "The selective predicate touches fewer pages through the index."
            };
        }

        return {
            "Full Table Scan",
            "",
            rows.size(),
            scan_cost,
            "The result is broad enough that sequential table access is competitive."
        };
    }

    QueryPlan statusEquals(
        const std::string& status
    ) const {
        /*
         * Status often has low cardinality. An index on a four-value status
         * column may therefore return a substantial portion of the table.
         * The optimizer should compare the resulting table-page work with a
         * sequential scan instead of assuming every index is beneficial.
         */
        std::vector<int> ids;

        if (status == "PAID" ||
            status == "PENDING" ||
            status == "SHIPPED" ||
            status == "CANCELLED") {
            auto result =
                status_index_.equalityLookup(
                    status == "PAID" ? 1 :
                    status == "PENDING" ? 2 :
                    status == "SHIPPED" ? 3 : 4
                );

            ids = std::move(result.first);
        }

        auto [rows, table_pages] =
            table_.fetchRows(ids);

        const std::size_t estimated_index_cost =
            table_pages + 2;

        if (estimated_index_cost < table_.pageCount()) {
            return {
                "Index Seek + Table Lookup",
                status_index_.name(),
                rows.size(),
                estimated_index_cost,
                "This simplified dataset makes the status predicate selective enough."
            };
        }

        return {
            "Full Table Scan",
            "",
            rows.size(),
            table_.pageCount(),
            "Low-cardinality status values can require many base-table pages."
        };
    }
};


class CoveringCustomerIndex {
private:
    struct Entry {
        int order_id;
        std::string status;
        double total_amount;
    };

    std::map<int, std::vector<Entry>> entries_;

public:
    void build(const std::vector<Order>& orders) {
        entries_.clear();

        for (const Order& order : orders) {
            entries_[order.customer_id].push_back({
                order.order_id,
                order.status,
                order.total_amount
            });
        }

        for (auto& [customer_id, values] : entries_) {
            std::sort(
                values.begin(),
                values.end(),
                [](const Entry& left, const Entry& right) {
                    return left.order_id < right.order_id;
                }
            );
        }
    }

    const std::vector<Entry>& query(int customer_id) const {
        static const std::vector<Entry> empty;

        auto iterator = entries_.find(customer_id);

        if (iterator == entries_.end()) {
            return empty;
        }

        return iterator->second;
    }
};


std::vector<Order> makeOrders(std::size_t count) {
    std::vector<Order> orders;
    orders.reserve(count);

    const std::vector<std::string> statuses = {
        "PAID",
        "PENDING",
        "SHIPPED",
        "CANCELLED"
    };

    /*
     * A deterministic generator keeps the case study reproducible. The
     * distribution intentionally makes PAID common and CANCELLED uncommon so
     * selectivity differs among status values.
     */
    unsigned int state = 20261002;

    auto randomUnit = [&]() {
        state = 1664525u * state + 1013904223u;
        return static_cast<double>(state) /
               static_cast<double>(std::numeric_limits<unsigned int>::max());
    };

    auto randomInteger = [&](int low, int high) {
        return low +
            static_cast<int>(
                randomUnit() * static_cast<double>(high - low + 1)
            );
    };

    for (std::size_t i = 0; i < count; ++i) {
        const int order_id =
            static_cast<int>(i + 1);

        const int customer_id =
            randomInteger(
                1,
                static_cast<int>(
                    std::max<std::size_t>(10, count / 15)
                )
            );

        const int year =
            randomInteger(2024, 2026);

        const int month =
            randomInteger(1, 12);

        const int day =
            randomInteger(1, 28);

        const double status_roll =
            randomUnit();

        std::string status;

        if (status_roll < 0.55) {
            status = statuses[0];
        } else if (status_roll < 0.75) {
            status = statuses[1];
        } else if (status_roll < 0.95) {
            status = statuses[2];
        } else {
            status = statuses[3];
        }

        const double amount =
            25.0 + randomUnit() * 2475.0;

        orders.push_back({
            order_id,
            customer_id,
            status,
            year * 10000 + month * 100 + day,
            std::round(amount * 100.0) / 100.0
        });
    }

    return orders;
}


int statusCode(const std::string& status) {
    if (status == "PAID") {
        return 1;
    }
    if (status == "PENDING") {
        return 2;
    }
    if (status == "SHIPPED") {
        return 3;
    }
    if (status == "CANCELLED") {
        return 4;
    }

    throw IndexError(
        "Unknown status: " + status
    );
}


double selectivity(
    const std::vector<Order>& orders,
    const std::string& field,
    const std::string& value
) {
    if (orders.empty()) {
        return 0.0;
    }

    std::size_t matches = 0;

    for (const Order& order : orders) {
        if (field == "status" &&
            order.status == value) {
            ++matches;
        }
    }

    return static_cast<double>(matches) /
           static_cast<double>(orders.size());
}


void printPlan(
    const std::string& label,
    const QueryPlan& plan
) {
    std::cout << label << '\n'
              << "  Access path: "
              << plan.access_path << '\n'
              << "  Index: "
              << (plan.index_name.empty()
                      ? "none"
                      : plan.index_name)
              << '\n'
              << "  Estimated rows: "
              << plan.estimated_rows << '\n'
              << "  Estimated page reads: "
              << plan.estimated_page_reads << '\n'
              << "  Reason: "
              << plan.reason << "\n\n";
}


int main() {
    try {
        std::cout
            << "======================================================================\n"
            << "SQL INDEXES: B-TREE INDEXES AND QUERY PERFORMANCE\n"
            << "======================================================================\n\n";

        const std::vector<Order> orders =
            makeOrders(360);

        OrdersTable table(12);

        for (const Order& order : orders) {
            table.insert(order);
        }

        /*
         * The integer key for status is only an internal modeling convenience.
         * A real SQL index can directly order strings according to the
         * database's collation rules.
         */
        BTreeIndex customer_index(
            "idx_orders_customer_id",
            7
        );

        BTreeIndex status_index(
            "idx_orders_status",
            7
        );

        BTreeIndex date_index(
            "idx_orders_order_date",
            7
        );

        for (const Order& order : orders) {
            customer_index.insert(
                order.order_id,
                order.customer_id
            );

            status_index.insert(
                order.order_id,
                statusCode(order.status)
            );

            date_index.insert(
                order.order_id,
                order.order_date
            );
        }

        std::cout
            << "Table rows: "
            << table.rowCount()
            << "\nTable pages: "
            << table.pageCount()
            << "\n\n";

        std::cout
            << "Customer B-Tree: "
            << customer_index.name()
            << "\n  Entries: "
            << customer_index.entryCount()
            << "\n  Height: "
            << customer_index.height()
            << "\n\n";

        auto [customer_ids, customer_visits] =
            customer_index.equalityLookup(10);

        auto [customer_rows, customer_pages] =
            table.fetchRows(customer_ids);

        std::cout
            << "Customer equality predicate: customer_id = 10\n"
            << "  Matching rows: "
            << customer_rows.size()
            << "\n  B-Tree nodes visited: "
            << customer_visits
            << "\n  Table pages touched: "
            << customer_pages
            << "\n  Approximate logical accesses: "
            << customer_visits + customer_pages
            << "\n\n";

        auto [date_ids, date_visits] =
            date_index.rangeLookup(
                20260101,
                20260331
            );

        auto [date_rows, date_pages] =
            table.fetchRows(date_ids);

        std::cout
            << "Date range predicate: "
            << "20260101 <= order_date <= 20260331\n"
            << "  Matching rows: "
            << date_rows.size()
            << "\n  B-Tree nodes visited: "
            << date_visits
            << "\n  Table pages touched: "
            << date_pages
            << "\n\n";

        /*
         * Composite indexes encode a lexicographic order. The first key
         * groups all rows for a customer; the second key orders that customer's
         * rows by date. This makes customer + date filtering naturally
         * representable as a contiguous range.
         */
        CompositeIndex customer_date_index;

        customer_date_index.build(orders);

        const std::vector<int> customer_date_ids =
            customer_date_index.customerDateRange(
                10,
                20250101,
                20251231
            );

        const std::vector<int> customer_only_ids =
            customer_date_index.customerOnly(10);

        std::cout
            << "Composite index: (customer_id, order_date)\n"
            << "  Customer + date matches: "
            << customer_date_ids.size()
            << "\n"
            << "  Customer-only matches: "
            << customer_only_ids.size()
            << "\n"
            << "  Date-only note: order_date is not the leading key, so "
               "a date-only predicate cannot exploit the same leading range "
               "as efficiently.\n\n";

        CoveringCustomerIndex covering_index;
        covering_index.build(orders);

        const auto& covered_rows =
            covering_index.query(10);

        std::cout
            << "Covering/index-only access for customer_id = 10\n"
            << "  Rows available from index payload: "
            << covered_rows.size()
            << "\n"
            << "  Base-table lookup for projected columns: no\n\n";

        QueryPlanner planner(
            table,
            customer_index,
            status_index
        );

        printPlan(
            "Query-plan decision for customer_id = 10:",
            planner.customerEquals(10)
        );

        /*
         * The status index is intentionally modeled as a low-cardinality
         * index. Whether it wins depends on how many table pages are needed
         * after retrieving the matching index entries.
         */
        printPlan(
            "Query-plan decision for status = PAID:",
            planner.statusEquals("PAID")
        );

        std::cout
            << "Status selectivity:\n";

        for (const std::string& status :
             {"PAID", "PENDING", "SHIPPED", "CANCELLED"}) {
            std::cout
                << "  "
                << status
                << ": "
                << std::fixed
                << std::setprecision(2)
                << selectivity(
                    orders,
                    "status",
                    status
                ) * 100.0
                << "%\n";
        }

        std::cout << "\nIndex maintenance after UPDATE:\n";

        const int target_order_id = 15;
        const Order before =
            table.rows().at(target_order_id);

        auto [old_ids, old_visits] =
            customer_index.equalityLookup(
                before.customer_id
            );

        const bool existed_old =
            std::find(
                old_ids.begin(),
                old_ids.end(),
                target_order_id
            ) != old_ids.end();

        const Order updated =
            table.update(
                target_order_id,
                9999
            );

        /*
         * Updating an indexed key requires corresponding index maintenance.
         * The model removes the old key and inserts the new one.
         */
        customer_index.erase(target_order_id);
        customer_index.insert(
            target_order_id,
            updated.customer_id
        );

        auto [new_ids, new_visits] =
            customer_index.equalityLookup(9999);

        const bool exists_new =
            std::find(
                new_ids.begin(),
                new_ids.end(),
                target_order_id
            ) != new_ids.end();

        std::cout
            << "  Before: customer_id = "
            << before.customer_id
            << "\n"
            << "  Old index contained order: "
            << std::boolalpha
            << existed_old
            << "\n"
            << "  After: customer_id = "
            << updated.customer_id
            << "\n"
            << "  New index contains order: "
            << exists_new
            << "\n\n";

        std::cout
            << "Performance and design constraints:\n"
            << "  B-Tree search is approximately logarithmic in the number "
               "of indexed keys when the tree remains balanced.\n"
            << "  Range predicates benefit from ordered keys because the "
               "engine can navigate to a boundary and process the ordered "
               "range instead of testing every row.\n"
            << "  Selectivity affects whether an index is worthwhile. "
               "Low-cardinality columns can return many rows and cause "
               "many base-table page accesses.\n"
            << "  Composite index column order determines which predicates "
               "form useful leading ranges.\n"
            << "  Covering indexes can remove base-table lookups for narrow "
               "projections, but their payload increases index storage and "
               "write-maintenance cost.\n"
            << "  Every INSERT, DELETE, and indexed-column UPDATE has "
               "additional index maintenance work.\n\n";

        std::cout
            << "Production considerations:\n"
            << "  A real database optimizer considers statistics, "
               "histograms, buffer-cache state, correlation, join costs, "
               "parallelism, visibility, and engine-specific page costs.\n"
            << "  EXPLAIN plans should be validated against real workloads "
               "instead of relying on a theoretical index preference.\n"
            << "  Unused indexes should be identified from workload evidence "
               "because they consume storage and can slow write operations.\n";

        std::cout
            << "\nFailure-condition demonstration:\n";

        try {
            date_index.rangeLookup(
                20261231,
                20260101
            );
        } catch (const IndexError& error) {
            std::cout
                << "  Invalid range rejected: "
                << error.what()
                << '\n';
        }

        try {
            table.insert(
                orders.front()
            );
        } catch (const IndexError& error) {
            std::cout
                << "  Duplicate row rejected: "
                << error.what()
                << '\n';
        }

        return 0;
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }
}
