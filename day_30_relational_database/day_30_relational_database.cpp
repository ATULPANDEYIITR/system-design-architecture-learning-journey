/*
    Relational Databases: SQL, Relationships, and Constraints

    C++17 case study:
    A repository governance engine for an order-management database.

    The program models the relational design directly in C++ while focusing
    on database-engineering decisions:

      customers        -> one-to-many -> orders
      customers        -> one-to-one  -> customer_profiles
      orders           -> many-to-many -> products through order_items

    It demonstrates:
      - primary-key uniqueness
      - foreign-key validation
      - composite primary keys
      - NOT NULL-like validation
      - UNIQUE constraints
      - CHECK constraints
      - referential delete restrictions
      - transaction snapshots and rollback
      - JOIN-like relationship traversal
      - aggregation
      - index-like lookup structures
      - historical order pricing
      - domain validation and failure reporting

    Compile:
        g++ -std=c++17 -Wall -Wextra -pedantic relational_database.cpp -o relational_database

    Run:
        ./relational_database
*/

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class ConstraintViolation : public std::runtime_error {
public:
    explicit ConstraintViolation(const std::string& message)
        : std::runtime_error(message) {}
};

class TransactionFailure : public std::runtime_error {
public:
    explicit TransactionFailure(const std::string& message)
        : std::runtime_error(message) {}
};

struct Customer {
    int id;
    std::string name;
    std::string email;
};

struct CustomerProfile {
    int customerId;
    std::string phone;
    std::string city;
    std::string country;
};

struct Product {
    int id;
    std::string sku;
    std::string name;
    std::string category;
    double unitPrice;
    int inventoryQuantity;
};

enum class OrderStatus {
    Pending,
    Paid,
    Shipped,
    Cancelled
};

std::string statusToString(OrderStatus status) {
    switch (status) {
        case OrderStatus::Pending:
            return "PENDING";
        case OrderStatus::Paid:
            return "PAID";
        case OrderStatus::Shipped:
            return "SHIPPED";
        case OrderStatus::Cancelled:
            return "CANCELLED";
    }

    throw std::logic_error("Unknown order status");
}

struct Order {
    int id;
    int customerId;
    OrderStatus status;
};

struct OrderItem {
    int orderId;
    int productId;
    int quantity;

    // The order stores its purchase-time unit price. If the product price
    // changes later, historical order totals remain unchanged.
    double unitPrice;
};

class RelationalDatabase {
private:
    std::unordered_map<int, Customer> customers;
    std::unordered_map<int, CustomerProfile> profiles;
    std::unordered_map<int, Product> products;
    std::unordered_map<int, Order> orders;

    // The pair of IDs acts as a composite primary key for order_items.
    std::map<std::pair<int, int>, OrderItem> orderItems;

    // These maps model useful application-side indexes. A real DBMS may
    // maintain B-tree or hash-based indexes internally.
    std::unordered_map<std::string, int> customerEmailIndex;
    std::unordered_map<std::string, int> productSkuIndex;
    std::unordered_multimap<int, int> ordersByCustomerIndex;
    std::unordered_multimap<int, int> itemsByProductIndex;

    int nextCustomerId = 1;
    int nextProductId = 1;
    int nextOrderId = 1001;

    struct Snapshot {
        std::unordered_map<int, Customer> customers;
        std::unordered_map<int, CustomerProfile> profiles;
        std::unordered_map<int, Product> products;
        std::unordered_map<int, Order> orders;
        std::map<std::pair<int, int>, OrderItem> orderItems;

        std::unordered_map<std::string, int> customerEmailIndex;
        std::unordered_map<std::string, int> productSkuIndex;
        std::unordered_multimap<int, int> ordersByCustomerIndex;
        std::unordered_multimap<int, int> itemsByProductIndex;

        int nextCustomerId;
        int nextProductId;
        int nextOrderId;
    };

    std::optional<Snapshot> transactionSnapshot;

    static void require(bool condition, const std::string& message) {
        if (!condition) {
            throw ConstraintViolation(message);
        }
    }

    Snapshot createSnapshot() const {
        return Snapshot{
            customers,
            profiles,
            products,
            orders,
            orderItems,
            customerEmailIndex,
            productSkuIndex,
            ordersByCustomerIndex,
            itemsByProductIndex,
            nextCustomerId,
            nextProductId,
            nextOrderId
        };
    }

    void restoreSnapshot(const Snapshot& snapshot) {
        customers = snapshot.customers;
        profiles = snapshot.profiles;
        products = snapshot.products;
        orders = snapshot.orders;
        orderItems = snapshot.orderItems;

        customerEmailIndex = snapshot.customerEmailIndex;
        productSkuIndex = snapshot.productSkuIndex;
        ordersByCustomerIndex = snapshot.ordersByCustomerIndex;
        itemsByProductIndex = snapshot.itemsByProductIndex;

        nextCustomerId = snapshot.nextCustomerId;
        nextProductId = snapshot.nextProductId;
        nextOrderId = snapshot.nextOrderId;
    }

public:
    int addCustomer(
        const std::string& name,
        const std::string& email
    ) {
        require(name.size() >= 2, "customer name violates CHECK constraint");
        require(!email.empty(), "customer email violates NOT NULL constraint");

        if (customerEmailIndex.contains(email)) {
            throw ConstraintViolation(
                "customer email violates UNIQUE constraint"
            );
        }

        const int id = nextCustomerId++;

        customers.emplace(
            id,
            Customer{id, name, email}
        );

        customerEmailIndex[email] = id;

        return id;
    }

    void addProfile(
        int customerId,
        const std::string& phone,
        const std::string& city,
        const std::string& country
    ) {
        require(
            customers.contains(customerId),
            "profile.customer_id violates FOREIGN KEY constraint"
        );

        // customerId is both PRIMARY KEY and FOREIGN KEY here, which models
        // a one-to-one relationship.
        require(
            !profiles.contains(customerId),
            "customer profile violates one-to-one uniqueness"
        );

        require(!city.empty(), "profile city violates NOT NULL constraint");

        profiles.emplace(
            customerId,
            CustomerProfile{
                customerId,
                phone,
                city,
                country
            }
        );
    }

    int addProduct(
        const std::string& sku,
        const std::string& name,
        const std::string& category,
        double unitPrice,
        int inventoryQuantity
    ) {
        require(!sku.empty(), "SKU violates NOT NULL constraint");
        require(!name.empty(), "product name violates NOT NULL constraint");
        require(!category.empty(), "category violates NOT NULL constraint");
        require(unitPrice >= 0, "unit_price violates CHECK constraint");
        require(
            inventoryQuantity >= 0,
            "inventory_quantity violates CHECK constraint"
        );

        if (productSkuIndex.contains(sku)) {
            throw ConstraintViolation(
                "product SKU violates UNIQUE constraint"
            );
        }

        const int id = nextProductId++;

        products.emplace(
            id,
            Product{
                id,
                sku,
                name,
                category,
                unitPrice,
                inventoryQuantity
            }
        );

        productSkuIndex[sku] = id;

        return id;
    }

    int addOrder(int customerId, OrderStatus status) {
        require(
            customers.contains(customerId),
            "order.customer_id violates FOREIGN KEY constraint"
        );

        const int id = nextOrderId++;

        orders.emplace(
            id,
            Order{id, customerId, status}
        );

        ordersByCustomerIndex.emplace(customerId, id);

        return id;
    }

    void addOrderItem(int orderId, int productId, int quantity) {
        require(
            orders.contains(orderId),
            "order_items.order_id violates FOREIGN KEY constraint"
        );

        require(
            products.contains(productId),
            "order_items.product_id violates FOREIGN KEY constraint"
        );

        require(
            quantity > 0,
            "quantity violates CHECK constraint"
        );

        const auto key = std::make_pair(orderId, productId);

        if (orderItems.contains(key)) {
            throw ConstraintViolation(
                "(order_id, product_id) violates composite PRIMARY KEY"
            );
        }

        Product& product = products.at(productId);

        require(
            quantity <= product.inventoryQuantity,
            "requested quantity exceeds available inventory"
        );

        OrderItem item{
            orderId,
            productId,
            quantity,
            product.unitPrice
        };

        orderItems.emplace(key, item);
        itemsByProductIndex.emplace(productId, orderId);

        product.inventoryQuantity -= quantity;
    }

    void updateProductPrice(int productId, double newPrice) {
        require(
            products.contains(productId),
            "product does not exist"
        );

        require(
            newPrice >= 0,
            "new product price violates CHECK constraint"
        );

        products.at(productId).unitPrice = newPrice;
    }

    double orderTotal(int orderId) const {
        require(
            orders.contains(orderId),
            "order does not exist"
        );

        double total = 0;

        for (const auto& [key, item] : orderItems) {
            if (item.orderId == orderId) {
                total += item.quantity * item.unitPrice;
            }
        }

        return total;
    }

    std::vector<Order> ordersForCustomer(int customerId) const {
        require(
            customers.contains(customerId),
            "customer does not exist"
        );

        std::vector<Order> result;

        // This is analogous to an indexed lookup on customer_id rather
        // than scanning every order in the table.
        const auto range = ordersByCustomerIndex.equal_range(customerId);

        for (auto it = range.first; it != range.second; ++it) {
            result.push_back(orders.at(it->second));
        }

        return result;
    }

    std::vector<OrderItem> itemsForOrder(int orderId) const {
        require(
            orders.contains(orderId),
            "order does not exist"
        );

        std::vector<OrderItem> result;

        for (const auto& [key, item] : orderItems) {
            if (item.orderId == orderId) {
                result.push_back(item);
            }
        }

        return result;
    }

    void deleteProduct(int productId) {
        require(
            products.contains(productId),
            "product does not exist"
        );

        const auto range = itemsByProductIndex.equal_range(productId);

        if (range.first != range.second) {
            // This models ON DELETE RESTRICT. Existing order history
            // references the product, so deleting it would break integrity.
            throw ConstraintViolation(
                "cannot delete product referenced by order_items"
            );
        }

        const std::string sku = products.at(productId).sku;
        productSkuIndex.erase(sku);
        products.erase(productId);
    }

    void deleteCustomer(int customerId) {
        require(
            customers.contains(customerId),
            "customer does not exist"
        );

        const auto range = ordersByCustomerIndex.equal_range(customerId);

        if (range.first != range.second) {
            // The customer -> orders relationship is protected because
            // deleting the parent would orphan existing business records.
            throw ConstraintViolation(
                "cannot delete customer referenced by orders"
            );
        }

        profiles.erase(customerId);

        const std::string email = customers.at(customerId).email;
        customerEmailIndex.erase(email);
        customers.erase(customerId);
    }

    void beginTransaction() {
        require(
            !transactionSnapshot.has_value(),
            "nested transactions are not supported"
        );

        transactionSnapshot = createSnapshot();
    }

    void commit() {
        require(
            transactionSnapshot.has_value(),
            "no active transaction"
        );

        transactionSnapshot.reset();
    }

    void rollback() {
        require(
            transactionSnapshot.has_value(),
            "no active transaction"
        );

        restoreSnapshot(*transactionSnapshot);
        transactionSnapshot.reset();
    }

    std::string customerName(int customerId) const {
        auto iterator = customers.find(customerId);

        if (iterator == customers.end()) {
            return "<unknown customer>";
        }

        return iterator->second.name;
    }

    std::string productName(int productId) const {
        auto iterator = products.find(productId);

        if (iterator == products.end()) {
            return "<unknown product>";
        }

        return iterator->second.name;
    }

    void printCustomerOrderJoin(int customerId) const {
        std::cout << "\nCustomer -> Orders relationship\n";

        for (const Order& order : ordersForCustomer(customerId)) {
            std::cout
                << "  "
                << customerName(customerId)
                << " -> Order "
                << order.id
                << " -> "
                << statusToString(order.status)
                << '\n';
        }
    }

    void printOrderProductJoin(int orderId) const {
        std::cout << "\nOrder -> Product many-to-many relationship\n";

        for (const OrderItem& item : itemsForOrder(orderId)) {
            std::cout
                << "  Order "
                << item.orderId
                << " -> "
                << productName(item.productId)
                << " | quantity="
                << item.quantity
                << " | purchase_price="
                << std::fixed
                << std::setprecision(2)
                << item.unitPrice
                << '\n';
        }
    }

    void printCategoryRevenue() const {
        std::unordered_map<std::string, double> revenue;

        for (const auto& [key, item] : orderItems) {
            const Order& order = orders.at(item.orderId);

            if (order.status == OrderStatus::Cancelled) {
                continue;
            }

            const Product& product = products.at(item.productId);

            revenue[product.category] +=
                item.quantity * item.unitPrice;
        }

        std::cout << "\nCategory revenue aggregation\n";

        std::vector<std::pair<std::string, double>> sorted(
            revenue.begin(),
            revenue.end()
        );

        std::sort(
            sorted.begin(),
            sorted.end(),
            [](const auto& left, const auto& right) {
                return left.second > right.second;
            }
        );

        for (const auto& [category, value] : sorted) {
            std::cout
                << "  "
                << category
                << ": "
                << std::fixed
                << std::setprecision(2)
                << value
                << '\n';
        }
    }

    int productInventory(int productId) const {
        require(products.contains(productId), "product does not exist");
        return products.at(productId).inventoryQuantity;
    }
};

int main() {
    try {
        RelationalDatabase database;

        std::cout << "=== Relational Database Case Study ===\n";

        const int atul = database.addCustomer(
            "Atul Pandey",
            "atul@example.com"
        );

        const int priya = database.addCustomer(
            "Priya Sharma",
            "priya@example.com"
        );

        database.addProfile(
            atul,
            "+91-9000000001",
            "Lucknow",
            "India"
        );

        database.addProfile(
            priya,
            "+91-9000000002",
            "Delhi",
            "India"
        );

        const int laptop = database.addProduct(
            "LAP-001",
            "Developer Laptop",
            "Computers",
            85000,
            5
        );

        const int monitor = database.addProduct(
            "MON-001",
            "27-inch Monitor",
            "Displays",
            24000,
            8
        );

        const int dock = database.addProduct(
            "DOC-001",
            "USB-C Dock",
            "Accessories",
            9000,
            4
        );

        std::cout << "\n=== Transactional order creation ===\n";

        database.beginTransaction();

        try {
            const int order = database.addOrder(
                atul,
                OrderStatus::Paid
            );

            database.addOrderItem(order, laptop, 1);
            database.addOrderItem(order, monitor, 2);
            database.addOrderItem(order, dock, 1);

            database.commit();

            std::cout
                << "Order "
                << order
                << " committed successfully.\n";

            database.printCustomerOrderJoin(atul);
            database.printOrderProductJoin(order);

            std::cout
                << "Order total: "
                << std::fixed
                << std::setprecision(2)
                << database.orderTotal(order)
                << '\n';
        } catch (...) {
            database.rollback();
            throw;
        }

        std::cout << "\n=== Historical price preservation ===\n";

        const int historicalOrder = database.ordersForCustomer(atul).front().id;
        const double beforePriceChange =
            database.orderTotal(historicalOrder);

        database.updateProductPrice(laptop, 90000);

        const double afterPriceChange =
            database.orderTotal(historicalOrder);

        std::cout
            << "Order total before product price change: "
            << beforePriceChange
            << '\n';

        std::cout
            << "Order total after product price change:  "
            << afterPriceChange
            << '\n';

        std::cout
            << "The historical total is unchanged because order_items "
               "stores purchase-time unit_price.\n";

        database.printCategoryRevenue();

        std::cout << "\n=== Foreign-key failure ===\n";

        try {
            database.addOrder(999999, OrderStatus::Pending);
        } catch (const ConstraintViolation& error) {
            std::cout
                << "Rejected invalid order: "
                << error.what()
                << '\n';
        }

        std::cout << "\n=== Transaction rollback ===\n";

        const int inventoryBefore =
            database.productInventory(monitor);

        database.beginTransaction();

        try {
            const int temporaryOrder = database.addOrder(
                priya,
                OrderStatus::Pending
            );

            database.addOrderItem(
                temporaryOrder,
                monitor,
                1
            );

            // This operation fails because product 999999 does not exist.
            database.addOrderItem(
                temporaryOrder,
                999999,
                1
            );

            database.commit();
        } catch (const ConstraintViolation& error) {
            std::cout
                << "Transaction failed: "
                << error.what()
                << '\n';

            database.rollback();
        }

        const int inventoryAfter =
            database.productInventory(monitor);

        std::cout
            << "Monitor inventory before failed transaction: "
            << inventoryBefore
            << '\n';

        std::cout
            << "Monitor inventory after rollback: "
            << inventoryAfter
            << '\n';

        std::cout << "\n=== Referential deletion restriction ===\n";

        try {
            database.deleteProduct(laptop);
        } catch (const ConstraintViolation& error) {
            std::cout
                << "Product deletion rejected: "
                << error.what()
                << '\n';
        }

        try {
            database.deleteCustomer(atul);
        } catch (const ConstraintViolation& error) {
            std::cout
                << "Customer deletion rejected: "
                << error.what()
                << '\n';
        }

        std::cout << "\n=== Composite-key failure ===\n";

        try {
            const auto atulOrders = database.ordersForCustomer(atul);

            database.addOrderItem(
                atulOrders.front().id,
                monitor,
                1
            );
        } catch (const ConstraintViolation& error) {
            std::cout
                << "Duplicate order item rejected: "
                << error.what()
                << '\n';
        }

        std::cout << "\n=== Relational design properties ===\n";
        std::cout
            << "customers -> orders is one-to-many.\n"
            << "customers -> customer_profiles is one-to-one.\n"
            << "orders -> products is many-to-many through order_items.\n"
            << "Primary keys identify rows; foreign keys preserve references.\n"
            << "CHECK constraints protect domain-specific values.\n"
            << "UNIQUE constraints prevent duplicate business identifiers.\n"
            << "Transactions preserve atomic multi-table operations.\n"
            << "Indexes provide efficient access paths for common predicates.\n";

        std::cout << "\n=== Case study completed ===\n";
    } catch (const std::exception& error) {
        std::cerr
            << "Fatal error: "
            << error.what()
            << '\n';

        return 1;
    }

    return 0;
}
