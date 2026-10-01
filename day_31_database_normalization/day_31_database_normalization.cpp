/*
 * Database Normalization Case Study
 *
 * C++17
 *
 * Scenario:
 * A retail organization is building a repository governance component for
 * its transactional order database. The database initially contains a broad
 * relation that mixes order, customer, product, and category facts.
 *
 * The program models:
 *   - 1NF through atomic order-line records.
 *   - 2NF through detection of partial dependencies on a composite key.
 *   - 3NF through detection and removal of transitive dependencies.
 *   - Functional dependencies and candidate-key reasoning.
 *   - A lossless decomposition check.
 *   - A normalized transactional model with foreign-key validation.
 *   - A denormalized reporting projection.
 *   - Consistency checks showing the maintenance cost of denormalization.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic database_normalization.cpp -o normalization
 */

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;


// ---------------------------------------------------------------------------
// Relational records
// ---------------------------------------------------------------------------

struct Customer {
    string customerId;
    string name;
    string city;
};

struct Category {
    string categoryId;
    string name;
};

struct Product {
    string productId;
    string name;
    string categoryId;
    double price{};
};

struct OrderLine {
    int orderId{};
    string productId;
    int quantity{};
};

struct Order {
    int orderId{};
    string customerId;
    vector<OrderLine> lines;
};


// ---------------------------------------------------------------------------
// Functional dependency representation
// ---------------------------------------------------------------------------

struct FunctionalDependency {
    set<string> determinant;
    set<string> dependent;

    string toString() const {
        string result;

        for (auto it = determinant.begin(); it != determinant.end(); ++it) {
            if (it != determinant.begin()) {
                result += ", ";
            }
            result += *it;
        }

        result += " -> ";

        for (auto it = dependent.begin(); it != dependent.end(); ++it) {
            if (it != dependent.begin()) {
                result += ", ";
            }
            result += *it;
        }

        return result;
    }
};

bool isSubset(
    const set<string>& subset,
    const set<string>& target
) {
    return includes(
        target.begin(),
        target.end(),
        subset.begin(),
        subset.end()
    );
}

set<string> attributeClosure(
    set<string> closure,
    const vector<FunctionalDependency>& dependencies
) {
    /*
     * Attribute closure is the formal mechanism used to determine whether
     * a determinant is a superkey. Repeatedly apply functional dependencies
     * until no new attributes can be derived.
     */
    bool changed = true;

    while (changed) {
        changed = false;

        for (const auto& dependency : dependencies) {
            if (!isSubset(dependency.determinant, closure)) {
                continue;
            }

            const size_t before = closure.size();

            closure.insert(
                dependency.dependent.begin(),
                dependency.dependent.end()
            );

            if (closure.size() != before) {
                changed = true;
            }
        }
    }

    return closure;
}

bool isSuperkey(
    const set<string>& attributes,
    const set<string>& relationAttributes,
    const vector<FunctionalDependency>& dependencies
) {
    const auto closure = attributeClosure(attributes, dependencies);
    return isSubset(relationAttributes, closure);
}


// ---------------------------------------------------------------------------
// 1NF representation
// ---------------------------------------------------------------------------

struct AtomicOrderLine {
    int orderId{};
    string customerId;
    string customerName;
    string customerCity;
    string productId;
    string productName;
    int quantity{};
    double unitPrice{};
};

struct RepeatingOrder {
    int orderId{};
    string customerId;
    string customerName;
    string customerCity;

    vector<tuple<string, string, int, double>> products;
};


vector<RepeatingOrder> buildRepeatingGroupOrders() {
    return {
        {
            8001,
            "C100",
            "Isha Verma",
            "Lucknow",
            {
                {"P100", "Keyboard", 2, 1800.00},
                {"P200", "Mouse", 1, 700.00}
            }
        },
        {
            8002,
            "C200",
            "Kabir Singh",
            "Delhi",
            {
                {"P200", "Mouse", 2, 700.00},
                {"P300", "Monitor", 1, 12000.00}
            }
        }
    };
}

vector<AtomicOrderLine> convertTo1NF(
    const vector<RepeatingOrder>& source
) {
    vector<AtomicOrderLine> result;

    for (const auto& order : source) {
        for (const auto& product : order.products) {
            const auto& productId = get<0>(product);
            const auto& productName = get<1>(product);
            const int quantity = get<2>(product);
            const double price = get<3>(product);

            if (productId.empty() || productName.empty()) {
                throw invalid_argument(
                    "1NF conversion encountered an incomplete product"
                );
            }

            if (quantity <= 0) {
                throw invalid_argument(
                    "1NF conversion encountered a non-positive quantity"
                );
            }

            if (price < 0.0) {
                throw invalid_argument(
                    "1NF conversion encountered a negative price"
                );
            }

            result.push_back({
                order.orderId,
                order.customerId,
                order.customerName,
                order.customerCity,
                productId,
                productName,
                quantity,
                price
            });
        }
    }

    return result;
}

void print1NF(const vector<AtomicOrderLine>& rows) {
    cout << left
         << setw(9) << "Order"
         << setw(9) << "Customer"
         << setw(18) << "CustomerName"
         << setw(14) << "Product"
         << setw(18) << "ProductName"
         << setw(8) << "Qty"
         << setw(12) << "Price"
         << '\n';

    cout << string(88, '-') << '\n';

    for (const auto& row : rows) {
        cout << left
             << setw(9) << row.orderId
             << setw(9) << row.customerId
             << setw(18) << row.customerName
             << setw(14) << row.productId
             << setw(18) << row.productName
             << setw(8) << row.quantity
             << fixed << setprecision(2)
             << setw(12) << row.unitPrice
             << '\n';
    }
}


// ---------------------------------------------------------------------------
// 2NF decomposition
// ---------------------------------------------------------------------------

struct Customer2NF {
    string customerId;
    string customerName;
    string city;
};

struct Product2NF {
    string productId;
    string productName;
    double unitPrice{};
};

struct OrderLine2NF {
    int orderId{};
    string productId;
    int quantity{};
};

struct SecondNormalForm {
    vector<Customer2NF> customers;
    vector<Product2NF> products;
    vector<OrderLine2NF> orderLines;
};

SecondNormalForm decomposeTo2NF(
    const vector<AtomicOrderLine>& rows
) {
    SecondNormalForm result;

    map<string, Customer2NF> customers;
    map<string, Product2NF> products;
    set<pair<int, string>> lineKeys;

    for (const auto& row : rows) {
        Customer2NF customer{
            row.customerId,
            row.customerName,
            row.customerCity
        };

        Product2NF product{
            row.productId,
            row.productName,
            row.unitPrice
        };

        auto customerIt = customers.find(row.customerId);

        if (customerIt != customers.end() &&
            customerIt->second.customerName != customer.customerName) {
            throw invalid_argument(
                "2NF decomposition detected inconsistent customer attributes"
            );
        }

        auto productIt = products.find(row.productId);

        if (productIt != products.end() &&
            (productIt->second.productName != product.productName ||
             productIt->second.unitPrice != product.unitPrice)) {
            throw invalid_argument(
                "2NF decomposition detected inconsistent product attributes"
            );
        }

        const pair<int, string> lineKey{
            row.orderId,
            row.productId
        };

        if (!lineKeys.insert(lineKey).second) {
            throw invalid_argument(
                "Duplicate (OrderID, ProductID) composite key"
            );
        }

        customers[row.customerId] = customer;
        products[row.productId] = product;

        result.orderLines.push_back({
            row.orderId,
            row.productId,
            row.quantity
        });
    }

    for (const auto& [id, customer] : customers) {
        result.customers.push_back(customer);
    }

    for (const auto& [id, product] : products) {
        result.products.push_back(product);
    }

    return result;
}


// ---------------------------------------------------------------------------
// 3NF decomposition
// ---------------------------------------------------------------------------

struct ProductWithCategory {
    string productId;
    string productName;
    string categoryId;
    string categoryName;
};

struct Product3NF {
    string productId;
    string productName;
    string categoryId;
};

struct Category3NF {
    string categoryId;
    string categoryName;
};

struct ThirdNormalForm {
    vector<Product3NF> products;
    vector<Category3NF> categories;
};

ThirdNormalForm decomposeTo3NF(
    const vector<ProductWithCategory>& source
) {
    ThirdNormalForm result;

    map<string, Category3NF> categories;
    map<string, Product3NF> products;

    for (const auto& row : source) {
        auto categoryIt = categories.find(row.categoryId);

        if (categoryIt != categories.end() &&
            categoryIt->second.categoryName != row.categoryName) {
            throw invalid_argument(
                "CategoryID determines conflicting CategoryName values"
            );
        }

        categories[row.categoryId] = {
            row.categoryId,
            row.categoryName
        };

        products[row.productId] = {
            row.productId,
            row.productName,
            row.categoryId
        };
    }

    for (const auto& [id, category] : categories) {
        result.categories.push_back(category);
    }

    for (const auto& [id, product] : products) {
        result.products.push_back(product);
    }

    return result;
}


// ---------------------------------------------------------------------------
// Normalized transactional database
// ---------------------------------------------------------------------------

class NormalizedOrderDatabase {
private:
    map<string, Customer> customers;
    map<string, Category> categories;
    map<string, Product> products;
    map<int, Order> orders;

public:
    void addCustomer(const Customer& customer) {
        if (customers.contains(customer.customerId)) {
            throw invalid_argument("Duplicate CustomerID");
        }

        customers.emplace(customer.customerId, customer);
    }

    void addCategory(const Category& category) {
        if (categories.contains(category.categoryId)) {
            throw invalid_argument("Duplicate CategoryID");
        }

        categories.emplace(category.categoryId, category);
    }

    void addProduct(const Product& product) {
        if (products.contains(product.productId)) {
            throw invalid_argument("Duplicate ProductID");
        }

        if (!categories.contains(product.categoryId)) {
            throw invalid_argument(
                "Product references an unknown CategoryID"
            );
        }

        if (product.price < 0.0) {
            throw invalid_argument(
                "Product price cannot be negative"
            );
        }

        products.emplace(product.productId, product);
    }

    void addOrder(const Order& order) {
        if (orders.contains(order.orderId)) {
            throw invalid_argument("Duplicate OrderID");
        }

        if (!customers.contains(order.customerId)) {
            throw invalid_argument(
                "Order references an unknown CustomerID"
            );
        }

        set<string> productsInOrder;

        for (const auto& line : order.lines) {
            if (line.orderId != order.orderId) {
                throw invalid_argument(
                    "OrderLine OrderID does not match parent OrderID"
                );
            }

            if (!products.contains(line.productId)) {
                throw invalid_argument(
                    "OrderLine references an unknown ProductID"
                );
            }

            if (line.quantity <= 0) {
                throw invalid_argument(
                    "OrderLine quantity must be positive"
                );
            }

            if (!productsInOrder.insert(line.productId).second) {
                throw invalid_argument(
                    "Duplicate (OrderID, ProductID) order line"
                );
            }
        }

        orders.emplace(order.orderId, order);
    }

    const map<string, Customer>& getCustomers() const {
        return customers;
    }

    const map<string, Category>& getCategories() const {
        return categories;
    }

    const map<string, Product>& getProducts() const {
        return products;
    }

    const map<int, Order>& getOrders() const {
        return orders;
    }

    double orderTotal(int orderId) const {
        auto orderIt = orders.find(orderId);

        if (orderIt == orders.end()) {
            throw out_of_range("Unknown OrderID");
        }

        double total = 0.0;

        for (const auto& line : orderIt->second.lines) {
            const auto& product = products.at(line.productId);
            total += product.price * line.quantity;
        }

        return total;
    }
};


// ---------------------------------------------------------------------------
// Denormalized reporting projection
// ---------------------------------------------------------------------------

struct SalesSnapshotRow {
    int orderId{};
    string customerId;
    string customerName;
    string productId;
    string productName;
    string categoryName;
    int quantity{};
    double unitPrice{};

    double lineTotal() const {
        return quantity * unitPrice;
    }
};

vector<SalesSnapshotRow> buildSalesSnapshot(
    const NormalizedOrderDatabase& database
) {
    vector<SalesSnapshotRow> snapshot;

    for (const auto& [orderId, order] : database.getOrders()) {
        const auto& customer =
            database.getCustomers().at(order.customerId);

        for (const auto& line : order.lines) {
            const auto& product =
                database.getProducts().at(line.productId);

            const auto& category =
                database.getCategories().at(product.categoryId);

            snapshot.push_back({
                orderId,
                customer.customerId,
                customer.name,
                product.productId,
                product.name,
                category.name,
                line.quantity,
                product.price
            });
        }
    }

    return snapshot;
}


// ---------------------------------------------------------------------------
// Lossless decomposition demonstration
// ---------------------------------------------------------------------------

bool sameProductInformation(
    const vector<ProductWithCategory>& original,
    const ThirdNormalForm& decomposed
) {
    map<string, Product3NF> products;
    map<string, Category3NF> categories;

    for (const auto& product : decomposed.products) {
        products[product.productId] = product;
    }

    for (const auto& category : decomposed.categories) {
        categories[category.categoryId] = category;
    }

    for (const auto& row : original) {
        auto productIt = products.find(row.productId);

        if (productIt == products.end()) {
            return false;
        }

        if (productIt->second.productName != row.productName ||
            productIt->second.categoryId != row.categoryId) {
            return false;
        }

        auto categoryIt = categories.find(row.categoryId);

        if (categoryIt == categories.end() ||
            categoryIt->second.categoryName != row.categoryName) {
            return false;
        }
    }

    return true;
}


// ---------------------------------------------------------------------------
// Demonstrations
// ---------------------------------------------------------------------------

void demonstrate1NF() {
    cout << "\n"
         << string(78, '=')
         << "\n1NF: atomic order-line records\n"
         << string(78, '=')
         << '\n';

    const auto source = buildRepeatingGroupOrders();
    const auto rows = convertTo1NF(source);

    print1NF(rows);

    cout << "\n"
         << "Each output tuple contains one product, one quantity, and one "
         << "price. Repeating product groups no longer occupy a single "
         << "attribute value.\n";
}

void demonstrate2NF() {
    cout << "\n"
         << string(78, '=')
         << "\n2NF: removing partial dependencies\n"
         << string(78, '=')
         << '\n';

    const auto rows = convertTo1NF(buildRepeatingGroupOrders());
    const auto result = decomposeTo2NF(rows);

    cout << "Customer relation rows: " << result.customers.size() << '\n';
    cout << "Product relation rows: " << result.products.size() << '\n';
    cout << "Order-line relation rows: " << result.orderLines.size() << '\n';

    cout
        << "\nComposite key of the original order-line relation: "
        << "(OrderID, ProductID)\n"
        << "Customer attributes depend on OrderID.\n"
        << "Product attributes depend on ProductID.\n"
        << "Quantity depends on the complete composite key.\n";

    cout
        << "\nSeparating these relations removes the partial dependencies "
        << "without removing the order-line fact itself.\n";
}

void demonstrate3NF() {
    cout << "\n"
         << string(78, '=')
         << "\n3NF: removing transitive dependency\n"
         << string(78, '=')
         << '\n';

    vector<ProductWithCategory> source{
        {"P100", "Keyboard", "CAT1", "Peripherals"},
        {"P200", "Mouse", "CAT1", "Peripherals"},
        {"P300", "Monitor", "CAT2", "Displays"}
    };

    const vector<FunctionalDependency> dependencies{
        {{"ProductID"}, {"ProductName", "CategoryID"}},
        {{"CategoryID"}, {"CategoryName"}}
    };

    cout << "Dependencies:\n";

    for (const auto& dependency : dependencies) {
        cout << "  " << dependency.toString() << '\n';
    }

    const auto closure =
        attributeClosure({"ProductID"}, dependencies);

    cout << "\nProductID closure: ";

    for (const auto& attribute : closure) {
        cout << attribute << ' ';
    }

    cout << "\n\nProductID determines CategoryID, and CategoryID "
         << "determines CategoryName. CategoryName is therefore reached "
         << "transitively from ProductID.\n";

    const auto result = decomposeTo3NF(source);

    cout << "\n3NF product rows: "
         << result.products.size()
         << '\n';

    cout << "3NF category rows: "
         << result.categories.size()
         << '\n';

    cout << "Lossless reconstruction check: "
         << (sameProductInformation(source, result) ? "PASS" : "FAIL")
         << '\n';
}

void demonstrateCandidateKeyAnalysis() {
    cout << "\n"
         << string(78, '=')
         << "\nCandidate-key reasoning\n"
         << string(78, '=')
         << '\n';

    const set<string> relationAttributes{
        "OrderID",
        "ProductID",
        "CustomerID",
        "CustomerName",
        "ProductName",
        "Quantity"
    };

    const vector<FunctionalDependency> dependencies{
        {{"OrderID"}, {"CustomerID"}},
        {{"CustomerID"}, {"CustomerName"}},
        {{"ProductID"}, {"ProductName"}},
        {{"OrderID", "ProductID"}, {"Quantity"}}
    };

    const set<string> compositeCandidate{
        "OrderID",
        "ProductID"
    };

    const auto closure =
        attributeClosure(compositeCandidate, dependencies);

    cout << "Closure of {OrderID, ProductID}:\n  ";

    for (const auto& attribute : closure) {
        cout << attribute << ' ';
    }

    cout << "\n\nIs {OrderID, ProductID} a superkey? "
         << (isSuperkey(
                 compositeCandidate,
                 relationAttributes,
                 dependencies
             )
                 ? "YES"
                 : "NO")
         << '\n';

    cout
        << "\nNeither OrderID nor ProductID alone reaches every attribute, "
        << "so the composite key represents the order-line identity in "
        << "this model.\n";
}

void demonstrateNormalizedDatabase() {
    cout << "\n"
         << string(78, '=')
         << "\nNormalized transactional database\n"
         << string(78, '=')
         << '\n';

    NormalizedOrderDatabase database;

    database.addCustomer({
        "C100",
        "Isha Verma",
        "Lucknow"
    });

    database.addCustomer({
        "C200",
        "Kabir Singh",
        "Delhi"
    });

    database.addCategory({
        "CAT1",
        "Peripherals"
    });

    database.addCategory({
        "CAT2",
        "Displays"
    });

    database.addProduct({
        "P100",
        "Keyboard",
        "CAT1",
        1800.00
    });

    database.addProduct({
        "P200",
        "Mouse",
        "CAT1",
        700.00
    });

    database.addProduct({
        "P300",
        "Monitor",
        "CAT2",
        12000.00
    });

    database.addOrder({
        8001,
        "C100",
        {
            {8001, "P100", 2},
            {8001, "P200", 1}
        }
    });

    database.addOrder({
        8002,
        "C200",
        {
            {8002, "P200", 2},
            {8002, "P300", 1}
        }
    });

    cout << fixed << setprecision(2)
         << "Order 8001 total: "
         << database.orderTotal(8001)
         << '\n';

    cout
        << "\nThe maps model primary-key access while explicit validation "
        << "models foreign-key and composite-key constraints.\n";
}

void demonstrateDenormalization() {
    cout << "\n"
         << string(78, '=')
         << "\nDenormalized reporting projection\n"
         << string(78, '=')
         << '\n';

    NormalizedOrderDatabase database;

    database.addCustomer({
        "C100",
        "Isha Verma",
        "Lucknow"
    });

    database.addCategory({
        "CAT1",
        "Peripherals"
    });

    database.addProduct({
        "P100",
        "Keyboard",
        "CAT1",
        1800.00
    });

    database.addOrder({
        8001,
        "C100",
        {
            {8001, "P100", 2}
        }
    });

    auto snapshot = buildSalesSnapshot(database);

    cout << "Snapshot contains expanded reporting facts:\n";

    for (const auto& row : snapshot) {
        cout << "  Order " << row.orderId
             << ", Customer=" << row.customerName
             << ", Product=" << row.productName
             << ", Category=" << row.categoryName
             << ", Total=" << fixed << setprecision(2)
             << row.lineTotal()
             << '\n';
    }

    database.getProducts();

    /*
     * The normalized source is authoritative. If its product price changes,
     * the copied price in the snapshot is stale until the projection is
     * refreshed. The example therefore exposes the maintenance cost of
     * denormalization rather than presenting duplication as free performance.
     */
    cout
        << "\nThe snapshot duplicates customer, product, and category "
        << "attributes. This removes join work for a read-heavy report, "
        << "but the copied values must be refreshed when source facts change.\n";
}

void demonstrateFailureCases() {
    cout << "\n"
         << string(78, '=')
         << "\nIntegrity failure cases\n"
         << string(78, '=')
         << '\n';

    NormalizedOrderDatabase database;

    database.addCategory({
        "CAT1",
        "Peripherals"
    });

    try {
        database.addProduct({
            "P404",
            "Orphan Product",
            "CAT404",
            100.0
        });
    } catch (const exception& error) {
        cout << "Unknown category rejected: "
             << error.what()
             << '\n';
    }

    database.addCustomer({
        "C100",
        "Isha Verma",
        "Lucknow"
    });

    database.addProduct({
        "P100",
        "Keyboard",
        "CAT1",
        1800.0
    });

    try {
        database.addOrder({
            9001,
            "C100",
            {
                {9001, "P100", 1},
                {9001, "P100", 2}
            }
        });
    } catch (const exception& error) {
        cout << "Duplicate composite key rejected: "
             << error.what()
             << '\n';
    }

    try {
        database.addOrder({
            9002,
            "C404",
            {}
        });
    } catch (const exception& error) {
        cout << "Unknown customer rejected: "
             << error.what()
             << '\n';
    }
}


// ---------------------------------------------------------------------------
// Main case study
// ---------------------------------------------------------------------------

int main() {
    try {
        cout << "Database Normalization Case Study\n";
        cout << "1NF -> 2NF -> 3NF -> controlled denormalization\n";

        demonstrate1NF();
        demonstrate2NF();
        demonstrate3NF();
        demonstrateCandidateKeyAnalysis();
        demonstrateNormalizedDatabase();
        demonstrateDenormalization();
        demonstrateFailureCases();

        cout << "\n"
             << string(78, '=')
             << "\nCase study completed\n"
             << string(78, '=')
             << '\n';

        cout
            << "The design separates atomicity, partial-dependency removal, "
            << "transitive-dependency removal, and workload-driven duplication "
            << "as distinct database design decisions.\n";

        return 0;
    } catch (const exception& error) {
        cerr << "Fatal validation or execution error: "
             << error.what()
             << '\n';

        return 1;
    }
}
