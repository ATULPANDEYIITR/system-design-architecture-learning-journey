/*
 * SQL vs NoSQL: enterprise order platform governance model.
 *
 * Java 17+.
 *
 * The program uses explicit domain types to show how relational and
 * NoSQL-oriented designs make different trade-offs around:
 * - schema structure
 * - aggregate boundaries
 * - consistency
 * - transactions
 * - concurrency
 * - scaling
 * - workload selection
 */

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class SqlVsNoSql {

    enum DatabaseType {
        SQL,
        DOCUMENT_NOSQL,
        KEY_VALUE_NOSQL
    }

    enum OrderStatus {
        PENDING,
        PAID,
        CANCELLED
    }

    record Customer(
        long id,
        String name,
        String email
    ) {
        public Customer {
            if (id <= 0) {
                throw new IllegalArgumentException(
                    "Customer id must be positive"
                );
            }

            Objects.requireNonNull(name);
            Objects.requireNonNull(email);
        }
    }

    record Product(
        long id,
        String name,
        String category,
        double price
    ) {
        public Product {
            if (id <= 0) {
                throw new IllegalArgumentException(
                    "Product id must be positive"
                );
            }

            if (price < 0) {
                throw new IllegalArgumentException(
                    "Product price cannot be negative"
                );
            }
        }
    }

    record OrderItem(
        long productId,
        int quantity,
        double unitPrice
    ) {
        public OrderItem {
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "Quantity must be positive"
                );
            }

            if (unitPrice < 0) {
                throw new IllegalArgumentException(
                    "Unit price cannot be negative"
                );
            }
        }

        double lineTotal() {
            return quantity * unitPrice;
        }
    }

    static final class RelationalOrder {
        private final long id;
        private final long customerId;
        private final List<OrderItem> items;
        private OrderStatus status;

        RelationalOrder(
            long id,
            long customerId,
            OrderStatus status
        ) {
            this.id = id;
            this.customerId = customerId;
            this.status = Objects.requireNonNull(status);
            this.items = new ArrayList<>();
        }

        void addItem(OrderItem item) {
            items.add(Objects.requireNonNull(item));
        }

        double total() {
            return items.stream()
                .mapToDouble(OrderItem::lineTotal)
                .sum();
        }

        long id() {
            return id;
        }

        long customerId() {
            return customerId;
        }

        OrderStatus status() {
            return status;
        }

        void transitionTo(OrderStatus next) {
            if (status == OrderStatus.CANCELLED) {
                throw new IllegalStateException(
                    "Cancelled orders cannot transition"
                );
            }

            if (
                status == OrderStatus.PAID
                && next == OrderStatus.PENDING
            ) {
                throw new IllegalStateException(
                    "Paid orders cannot return to pending"
                );
            }

            status = next;
        }
    }

    static final class RelationalOrderService {
        private final Map<Long, Customer> customers =
            new HashMap<>();

        private final Map<Long, Product> products =
            new HashMap<>();

        private final Map<Long, RelationalOrder> orders =
            new HashMap<>();

        void addCustomer(Customer customer) {
            if (customers.containsKey(customer.id())) {
                throw new IllegalArgumentException(
                    "Duplicate customer id"
                );
            }

            boolean emailExists = customers.values()
                .stream()
                .anyMatch(
                    existing ->
                        existing.email().equals(
                            customer.email()
                        )
                );

            if (emailExists) {
                throw new IllegalArgumentException(
                    "Customer email must be unique"
                );
            }

            customers.put(customer.id(), customer);
        }

        void addProduct(Product product) {
            if (products.containsKey(product.id())) {
                throw new IllegalArgumentException(
                    "Duplicate product id"
                );
            }

            products.put(product.id(), product);
        }

        void createOrder(
            long orderId,
            long customerId
        ) {
            if (!customers.containsKey(customerId)) {
                throw new IllegalArgumentException(
                    "Customer does not exist"
                );
            }

            if (orders.containsKey(orderId)) {
                throw new IllegalArgumentException(
                    "Order already exists"
                );
            }

            orders.put(
                orderId,
                new RelationalOrder(
                    orderId,
                    customerId,
                    OrderStatus.PENDING
                )
            );
        }

        void addItem(
            long orderId,
            long productId,
            int quantity
        ) {
            RelationalOrder order =
                requireOrder(orderId);

            Product product =
                requireProduct(productId);

            order.addItem(
                new OrderItem(
                    product.id(),
                    quantity,
                    product.price()
                )
            );
        }

        void pay(long orderId) {
            requireOrder(orderId)
                .transitionTo(OrderStatus.PAID);
        }

        private RelationalOrder requireOrder(
            long id
        ) {
            RelationalOrder order = orders.get(id);

            if (order == null) {
                throw new IllegalArgumentException(
                    "Order does not exist"
                );
            }

            return order;
        }

        private Product requireProduct(
            long id
        ) {
            Product product = products.get(id);

            if (product == null) {
                throw new IllegalArgumentException(
                    "Product does not exist"
                );
            }

            return product;
        }

        double total(long orderId) {
            return requireOrder(orderId).total();
        }
    }

    record DocumentOrder(
        String id,
        String customerName,
        OrderStatus status,
        List<Map<String, Object>> items,
        Map<String, String> shipping
    ) {
        DocumentOrder {
            Objects.requireNonNull(id);
            Objects.requireNonNull(customerName);
            Objects.requireNonNull(status);
            Objects.requireNonNull(items);
            Objects.requireNonNull(shipping);

            if (id.isBlank()) {
                throw new IllegalArgumentException(
                    "Document id cannot be blank"
                );
            }
        }

        DocumentOrder withStatus(
            OrderStatus newStatus
        ) {
            return new DocumentOrder(
                id,
                customerName,
                newStatus,
                List.copyOf(items),
                Map.copyOf(shipping)
            );
        }
    }

    static final class DocumentOrderService {
        private final Map<String, DocumentOrder> documents =
            new HashMap<>();

        void insert(DocumentOrder document) {
            if (documents.containsKey(document.id())) {
                throw new IllegalArgumentException(
                    "Duplicate document id"
                );
            }

            documents.put(
                document.id(),
                document
            );
        }

        Optional<DocumentOrder> find(String id) {
            return Optional.ofNullable(
                documents.get(id)
            );
        }

        void pay(String id) {
            DocumentOrder document =
                documents.get(id);

            if (document == null) {
                throw new IllegalArgumentException(
                    "Document not found"
                );
            }

            if (document.status() != OrderStatus.PENDING) {
                throw new IllegalStateException(
                    "Only pending documents can be paid"
                );
            }

            documents.put(
                id,
                document.withStatus(
                    OrderStatus.PAID
                )
            );
        }
    }

    record VersionedValue<T>(
        T value,
        long version
    ) {}

    static final class OptimisticRepository<T> {
        private final Map<String, VersionedValue<T>> data =
            new HashMap<>();

        void create(String key, T value) {
            if (data.containsKey(key)) {
                throw new IllegalArgumentException(
                    "Key already exists"
                );
            }

            data.put(
                key,
                new VersionedValue<>(
                    value,
                    1
                )
            );
        }

        VersionedValue<T> read(String key) {
            VersionedValue<T> value = data.get(key);

            if (value == null) {
                throw new IllegalArgumentException(
                    "Record not found"
                );
            }

            return value;
        }

        void update(
            String key,
            T value,
            long expectedVersion
        ) {
            VersionedValue<T> current =
                read(key);

            if (
                current.version()
                != expectedVersion
            ) {
                throw new IllegalStateException(
                    "Optimistic concurrency conflict"
                );
            }

            data.put(
                key,
                new VersionedValue<>(
                    value,
                    current.version() + 1
                )
            );
        }
    }

    static final class KeyValueSessionStore {
        private final Map<String, String> sessions =
            new HashMap<>();

        void put(
            String key,
            String value
        ) {
            if (key.isBlank()) {
                throw new IllegalArgumentException(
                    "Session key cannot be blank"
                );
            }

            sessions.put(key, value);
        }

        Optional<String> get(String key) {
            return Optional.ofNullable(
                sessions.get(key)
            );
        }
    }

    static DatabaseType selectDatabase(
        boolean relationalQueries,
        boolean multiRecordTransactions,
        boolean flexibleSchema,
        boolean directKeyLookup,
        boolean horizontalScale
    ) {
        if (directKeyLookup) {
            return DatabaseType.KEY_VALUE_NOSQL;
        }

        if (
            relationalQueries
            || multiRecordTransactions
        ) {
            return DatabaseType.SQL;
        }

        if (
            flexibleSchema
            && horizontalScale
        ) {
            return DatabaseType.DOCUMENT_NOSQL;
        }

        if (horizontalScale) {
            return DatabaseType.DOCUMENT_NOSQL;
        }

        return DatabaseType.SQL;
    }

    static void demonstrateRelationalDomain() {
        System.out.println(
            "\n=== ENTERPRISE RELATIONAL DOMAIN ==="
        );

        RelationalOrderService service =
            new RelationalOrderService();

        service.addCustomer(
            new Customer(
                1,
                "Asha Rao",
                "asha@example.com"
            )
        );

        service.addProduct(
            new Product(
                10,
                "Laptop",
                "Computing",
                1200
            )
        );

        service.addProduct(
            new Product(
                11,
                "Keyboard",
                "Accessories",
                80
            )
        );

        service.createOrder(1001, 1);
        service.addItem(1001, 10, 1);
        service.addItem(1001, 11, 2);
        service.pay(1001);

        System.out.printf(
            "Order total: %.2f%n",
            service.total(1001)
        );

        try {
            service.addItem(1001, 999, 1);
        } catch (IllegalArgumentException error) {
            System.out.println(
                "Invalid product rejected: "
                + error.getMessage()
            );
        }
    }

    static void demonstrateDocumentDomain() {
        System.out.println(
            "\n=== DOCUMENT AGGREGATE ==="
        );

        List<Map<String, Object>> items =
            List.of(
                Map.of(
                    "productId",
                    10,
                    "name",
                    "Laptop",
                    "quantity",
                    1,
                    "unitPrice",
                    1200
                )
            );

        DocumentOrder document =
            new DocumentOrder(
                "order-2001",
                "Rohan Mehta",
                OrderStatus.PENDING,
                items,
                Map.of(
                    "country",
                    "IN",
                    "postalCode",
                    "226001"
                )
            );

        DocumentOrderService service =
            new DocumentOrderService();

        service.insert(document);
        service.pay("order-2001");

        System.out.println(
            service.find("order-2001")
                .orElseThrow()
        );
    }

    static void demonstrateConcurrency() {
        System.out.println(
            "\n=== OPTIMISTIC CONCURRENCY ==="
        );

        OptimisticRepository<String> repository =
            new OptimisticRepository<>();

        repository.create(
            "order-3001",
            "PENDING"
        );

        VersionedValue<String> clientA =
            repository.read("order-3001");

        VersionedValue<String> clientB =
            repository.read("order-3001");

        repository.update(
            "order-3001",
            "PAID",
            clientA.version()
        );

        try {
            repository.update(
                "order-3001",
                "CANCELLED",
                clientB.version()
            );
        } catch (IllegalStateException error) {
            System.out.println(
                "Stale update rejected: "
                + error.getMessage()
            );
        }
    }

    static void demonstrateKeyValue() {
        System.out.println(
            "\n=== KEY-VALUE SESSION ==="
        );

        KeyValueSessionStore store =
            new KeyValueSessionStore();

        store.put(
            "session:user:42",
            "{\"userId\":42,\"role\":\"customer\"}"
        );

        System.out.println(
            store.get("session:user:42")
                .orElse("SESSION_NOT_FOUND")
        );
    }

    static void demonstrateSelection() {
        System.out.println(
            "\n=== ARCHITECTURE SELECTION ==="
        );

        DatabaseType ledger =
            selectDatabase(
                true,
                true,
                false,
                false,
                false
            );

        DatabaseType catalog =
            selectDatabase(
                false,
                false,
                true,
                false,
                true
            );

        DatabaseType sessions =
            selectDatabase(
                false,
                false,
                false,
                true,
                true
            );

        System.out.println(
            "Financial ledger: " + ledger
        );

        System.out.println(
            "Flexible catalog: " + catalog
        );

        System.out.println(
            "Session storage: " + sessions
        );
    }

    public static void main(String[] args) {
        try {
            demonstrateRelationalDomain();
            demonstrateDocumentDomain();
            demonstrateConcurrency();
            demonstrateKeyValue();
            demonstrateSelection();
        } catch (RuntimeException error) {
            System.err.println(
                "Application failure: "
                + error.getMessage()
            );

            System.exit(1);
        }
    }
}
