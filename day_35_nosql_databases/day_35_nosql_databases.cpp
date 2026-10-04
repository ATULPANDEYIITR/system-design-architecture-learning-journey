#include <algorithm>
#include <chrono>
#include <exception>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace std;

static void heading(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}

// -----------------------------------------------------------------------------
// Key-value database
// -----------------------------------------------------------------------------

class KeyValueStore {
private:
    unordered_map<string, string> values_;

public:
    void put(const string& key, const string& value) {
        if (key.empty()) {
            throw invalid_argument("Key cannot be empty");
        }
        values_[key] = value;
    }

    optional<string> get(const string& key) const {
        auto it = values_.find(key);
        if (it == values_.end()) {
            return nullopt;
        }
        return it->second;
    }

    bool erase(const string& key) {
        return values_.erase(key) > 0;
    }

    long long increment(const string& key, long long amount = 1) {
        long long current = 0;

        auto existing = get(key);

        if (existing.has_value()) {
            try {
                size_t consumed = 0;
                current = stoll(*existing, &consumed);

                if (consumed != existing->size()) {
                    throw invalid_argument("Counter contains non-numeric data");
                }
            } catch (const exception&) {
                throw invalid_argument("Counter value is not an integer");
            }
        }

        current += amount;
        put(key, to_string(current));
        return current;
    }
};

static void demonstrateKeyValue() {
    heading("Key-Value Repository: Session and Rate-Limit State");

    KeyValueStore store;

    store.put(
        "session:u-501",
        R"({"user_id":"u-501","role":"customer","cart_id":"cart-901"})"
    );

    cout << "Session payload:\n"
         << *store.get("session:u-501") << "\n";

    cout << "Rate-limit count: "
         << store.increment("rate-limit:u-501") << "\n";

    cout << "Rate-limit count: "
         << store.increment("rate-limit:u-501", 4) << "\n";

    cout << "Missing key: "
         << (store.get("session:unknown").value_or("NOT_FOUND")) << "\n";
}

// -----------------------------------------------------------------------------
// Document database
// -----------------------------------------------------------------------------

struct ProductDocument {
    string id;
    string name;
    string category;
    double price;
    vector<string> tags;
    unordered_map<string, int> inventory;
};

class DocumentStore {
private:
    unordered_map<string, ProductDocument> documents_;
    unordered_map<string, unordered_set<string>> categoryIndex_;

    static void validate(const ProductDocument& product) {
        if (product.id.empty()) {
            throw invalid_argument("Document ID is required");
        }

        if (product.name.empty()) {
            throw invalid_argument("Product name is required");
        }

        if (product.category.empty()) {
            throw invalid_argument("Category is required");
        }

        if (product.price < 0.0) {
            throw invalid_argument("Price cannot be negative");
        }
    }

public:
    void insert(ProductDocument product) {
        validate(product);

        if (documents_.contains(product.id)) {
            throw invalid_argument("Duplicate document ID: " + product.id);
        }

        categoryIndex_[product.category].insert(product.id);
        documents_.emplace(product.id, move(product));
    }

    optional<ProductDocument> get(const string& id) const {
        auto it = documents_.find(id);

        if (it == documents_.end()) {
            return nullopt;
        }

        return it->second;
    }

    vector<ProductDocument> findByCategory(const string& category) const {
        vector<ProductDocument> result;

        auto indexIt = categoryIndex_.find(category);

        if (indexIt == categoryIndex_.end()) {
            return result;
        }

        for (const string& id : indexIt->second) {
            result.push_back(documents_.at(id));
        }

        return result;
    }

    vector<ProductDocument> findUnderPrice(double maximum) const {
        vector<ProductDocument> result;

        for (const auto& [id, product] : documents_) {
            if (product.price < maximum) {
                result.push_back(product);
            }
        }

        return result;
    }

    void updateInventory(
        const string& productId,
        const string& warehouse,
        int newQuantity
    ) {
        if (newQuantity < 0) {
            throw invalid_argument("Inventory cannot be negative");
        }

        auto it = documents_.find(productId);

        if (it == documents_.end()) {
            throw out_of_range("Unknown product");
        }

        it->second.inventory[warehouse] = newQuantity;
    }
};

static void printProduct(const ProductDocument& product) {
    cout << product.id
         << " | " << product.name
         << " | category=" << product.category
         << " | price=" << fixed << setprecision(2) << product.price
         << "\n";
}

static void demonstrateDocumentStore() {
    heading("Document Repository: Product Catalog");

    DocumentStore store;

    store.insert({
        "p-100",
        "Mechanical Keyboard",
        "electronics",
        89.0,
        {"keyboard", "office"},
        {{"warehouse_a", 20}, {"warehouse_b", 12}}
    });

    store.insert({
        "p-101",
        "Wireless Mouse",
        "electronics",
        39.0,
        {"mouse", "wireless"},
        {{"warehouse_a", 35}, {"warehouse_b", 18}}
    });

    store.insert({
        "p-102",
        "USB-C Dock",
        "electronics",
        129.0,
        {"dock", "usb-c"},
        {{"warehouse_a", 7}, {"warehouse_b", 10}}
    });

    cout << "Category-indexed documents:\n";

    for (const auto& product : store.findByCategory("electronics")) {
        printProduct(product);
    }

    cout << "\nDocuments below $100:\n";

    for (const auto& product : store.findUnderPrice(100.0)) {
        printProduct(product);
    }

    store.updateInventory("p-100", "warehouse_a", 18);

    try {
        store.insert({
            "p-invalid",
            "Invalid Product",
            "electronics",
            -25.0,
            {},
            {}
        });
    } catch (const exception& ex) {
        cout << "\nRejected invalid document: " << ex.what() << "\n";
    }
}

// -----------------------------------------------------------------------------
// Column-family database
// -----------------------------------------------------------------------------

struct WideRow {
    string rowKey;
    unordered_map<string, string> columns;
};

class ColumnFamilyStore {
private:
    unordered_map<string, unordered_map<string, WideRow>> families_;

public:
    void put(
        const string& family,
        const string& rowKey,
        const unordered_map<string, string>& columns
    ) {
        if (family.empty() || rowKey.empty()) {
            throw invalid_argument("Family and row key are required");
        }

        auto& row = families_[family][rowKey];
        row.rowKey = rowKey;

        for (const auto& [column, value] : columns) {
            row.columns[column] = value;
        }
    }

    optional<WideRow> get(
        const string& family,
        const string& rowKey
    ) const {
        auto familyIt = families_.find(family);

        if (familyIt == families_.end()) {
            return nullopt;
        }

        auto rowIt = familyIt->second.find(rowKey);

        if (rowIt == familyIt->second.end()) {
            return nullopt;
        }

        return rowIt->second;
    }

    vector<WideRow> partitionScan(
        const string& family,
        const string& prefix
    ) const {
        vector<WideRow> result;

        auto familyIt = families_.find(family);

        if (familyIt == families_.end()) {
            return result;
        }

        for (const auto& [rowKey, row] : familyIt->second) {
            if (rowKey.rfind(prefix, 0) == 0) {
                result.push_back(row);
            }
        }

        sort(
            result.begin(),
            result.end(),
            [](const WideRow& left, const WideRow& right) {
                return left.rowKey < right.rowKey;
            }
        );

        return result;
    }
};

static void demonstrateColumnFamily() {
    heading("Column-Family Repository: Time-Bucketed Activity");

    ColumnFamilyStore store;

    struct Event {
        string user;
        string time;
        string type;
        string channel;
    };

    vector<Event> events = {
        {"u-501", "00:01:00", "login", "mobile"},
        {"u-501", "00:05:00", "view", "mobile"},
        {"u-501", "00:09:00", "purchase", "web"},
        {"u-502", "00:03:00", "login", "web"}
    };

    for (const auto& event : events) {
        string rowKey =
            event.user + "|2026-10-05|" + event.time;

        store.put(
            "activity_by_user_day",
            rowKey,
            {
                {"event_type", event.type},
                {"channel", event.channel}
            }
        );
    }

    const string partition = "u-501|2026-10-05|";

    cout << "Rows in one logical partition:\n";

    for (const auto& row :
         store.partitionScan("activity_by_user_day", partition)) {
        cout << row.rowKey;

        for (const auto& [column, value] : row.columns) {
            cout << " | " << column << "=" << value;
        }

        cout << "\n";
    }

    cout << "\nThe partition key makes the intended read path explicit.\n";
}

// -----------------------------------------------------------------------------
// Graph database
// -----------------------------------------------------------------------------

struct GraphNode {
    string id;
    string label;
    unordered_map<string, string> properties;
};

struct GraphEdge {
    string source;
    string relationship;
    string target;
};

class GraphStore {
private:
    unordered_map<string, GraphNode> nodes_;
    unordered_map<string, vector<GraphEdge>> outgoing_;

public:
    void addNode(
        const string& id,
        const string& label,
        unordered_map<string, string> properties
    ) {
        if (nodes_.contains(id)) {
            throw invalid_argument("Duplicate graph node: " + id);
        }

        nodes_.emplace(
            id,
            GraphNode{id, label, move(properties)}
        );
    }

    void addEdge(
        const string& source,
        const string& relationship,
        const string& target
    ) {
        if (!nodes_.contains(source) || !nodes_.contains(target)) {
            throw invalid_argument("Graph endpoints must exist");
        }

        outgoing_[source].push_back({
            source,
            relationship,
            target
        });
    }

    vector<string> neighbors(
        const string& node,
        const string& relationship = ""
    ) const {
        vector<string> result;

        auto it = outgoing_.find(node);

        if (it == outgoing_.end()) {
            return result;
        }

        for (const auto& edge : it->second) {
            if (relationship.empty() ||
                edge.relationship == relationship) {
                result.push_back(edge.target);
            }
        }

        return result;
    }

    optional<vector<string>> shortestPath(
        const string& start,
        const string& target
    ) const {
        if (!nodes_.contains(start) || !nodes_.contains(target)) {
            return nullopt;
        }

        queue<string> queue;
        unordered_map<string, string> parent;
        unordered_set<string> visited;

        queue.push(start);
        visited.insert(start);

        while (!queue.empty()) {
            string current = queue.front();
            queue.pop();

            if (current == target) {
                break;
            }

            for (const string& neighbor : neighbors(current)) {
                if (!visited.contains(neighbor)) {
                    visited.insert(neighbor);
                    parent[neighbor] = current;
                    queue.push(neighbor);
                }
            }
        }

        if (!visited.contains(target)) {
            return nullopt;
        }

        vector<string> path;
        string current = target;

        while (true) {
            path.push_back(current);

            if (current == start) {
                break;
            }

            current = parent.at(current);
        }

        reverse(path.begin(), path.end());
        return path;
    }

    vector<string> recommendations(const string& user) const {
        unordered_set<string> purchased(
            neighbors(user, "PURCHASED").begin(),
            neighbors(user, "PURCHASED").end()
        );

        // The temporary-vector iterator construction above would be unsafe
        // because the two calls create different temporaries. Rebuild from a
        // stable vector to make ownership explicit.
        purchased.clear();

        const auto purchasedVector = neighbors(user, "PURCHASED");

        for (const auto& product : purchasedVector) {
            purchased.insert(product);
        }

        unordered_set<string> similarUsers;

        for (const auto& [nodeId, edges] : outgoing_) {
            if (nodeId == user) {
                continue;
            }

            for (const auto& edge : edges) {
                if (edge.relationship == "PURCHASED" &&
                    purchased.contains(edge.target)) {
                    similarUsers.insert(nodeId);
                }
            }
        }

        unordered_set<string> candidates;

        for (const auto& similarUser : similarUsers) {
            for (const auto& product :
                 neighbors(similarUser, "PURCHASED")) {
                if (!purchased.contains(product)) {
                    candidates.insert(product);
                }
            }
        }

        vector<string> result(candidates.begin(), candidates.end());
        sort(result.begin(), result.end());
        return result;
    }
};

static void demonstrateGraph() {
    heading("Graph Repository: Purchase Relationships");

    GraphStore graph;

    graph.addNode("u-501", "User", {{"name", "Asha"}});
    graph.addNode("u-502", "User", {{"name", "Rahul"}});
    graph.addNode("u-503", "User", {{"name", "Meera"}});

    graph.addNode("p-100", "Product", {{"name", "Keyboard"}});
    graph.addNode("p-101", "Product", {{"name", "Mouse"}});
    graph.addNode("p-102", "Product", {{"name", "USB-C Dock"}});

    graph.addEdge("u-501", "PURCHASED", "p-100");
    graph.addEdge("u-501", "PURCHASED", "p-101");
    graph.addEdge("u-502", "PURCHASED", "p-100");
    graph.addEdge("u-502", "PURCHASED", "p-102");
    graph.addEdge("u-503", "PURCHASED", "p-102");

    cout << "Recommendations for u-501:\n";

    for (const auto& product : graph.recommendations("u-501")) {
        cout << "  " << product << "\n";
    }

    cout << "\nShortest path from u-501 to p-102:\n";

    auto path = graph.shortestPath("u-501", "p-102");

    if (path.has_value()) {
        for (size_t i = 0; i < path->size(); ++i) {
            if (i > 0) {
                cout << " -> ";
            }
            cout << (*path)[i];
        }
        cout << "\n";
    }
}

// -----------------------------------------------------------------------------
// Governance and production considerations
// -----------------------------------------------------------------------------

static void demonstrateTradeoffs() {
    heading("Model Selection and Trade-offs");

    struct Decision {
        string workload;
        string model;
        string reason;
    };

    vector<Decision> decisions = {
        {
            "Session and cache lookup",
            "Key-value",
            "The application already knows the exact key."
        },
        {
            "Product catalog with variable attributes",
            "Document",
            "The product is naturally represented as an aggregate."
        },
        {
            "User events by day and time",
            "Column-family",
            "Queries can be aligned with a partition key and clustering order."
        },
        {
            "Fraud relationship traversal",
            "Graph",
            "The relationship path is part of the query."
        }
    };

    for (const auto& decision : decisions) {
        cout << "\nWorkload: " << decision.workload
             << "\nModel: " << decision.model
             << "\nReason: " << decision.reason << "\n";
    }

    cout << "\nProduction constraints include:\n"
         << "  replication and failure recovery\n"
         << "  consistency guarantees and conflict handling\n"
         << "  partition sizing and hotspot prevention\n"
         << "  index and query-cost management\n"
         << "  authentication and authorization\n"
         << "  encryption and secret handling\n"
         << "  backups, observability, and capacity planning\n";
}

// -----------------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------------

int main() {
    try {
        heading("NoSQL Database Technical Case Study");

        demonstrateKeyValue();
        demonstrateDocumentStore();
        demonstrateColumnFamily();
        demonstrateGraph();
        demonstrateTradeoffs();

        heading("Case Study Complete");

        cout << "The four models were implemented around different primary "
                "access patterns rather than treated as interchangeable stores.\n";

        return 0;
    } catch (const exception& ex) {
        cerr << "Fatal error: " << ex.what() << "\n";
        return 1;
    }
}
