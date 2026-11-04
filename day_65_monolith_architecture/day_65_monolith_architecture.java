import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

/*
 * Monolith Architecture: Enterprise application simulation.
 *
 * Demonstrates:
 * - Enterprise module boundaries
 * - Shared persistence
 * - Transactional business operations
 * - Policy-based scaling decisions
 * - Operational health
 * - Failure handling
 * - Deployment coupling
 */

public class Main {

    enum OrderStatus {
        CREATED,
        PAID,
        FAILED
    }

    enum DeploymentMode {
        SINGLE_INSTANCE,
        HORIZONTAL_CLUSTER,
        VERTICAL_SCALE
    }

    record User(long id, String email) {
        User {
            if (id <= 0 || email == null || !email.matches(
                    "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")) {
                throw new IllegalArgumentException("Invalid user");
            }
        }
    }

    record Product(long id, String name, double price, int stock) {
        Product {
            if (id <= 0 || name == null || name.isBlank()
                    || !Double.isFinite(price) || price < 0
                    || stock < 0) {
                throw new IllegalArgumentException("Invalid product");
            }
        }
    }

    record Payment(String id, String orderId, double amount) {
        Payment {
            Objects.requireNonNull(id);
            Objects.requireNonNull(orderId);

            if (!Double.isFinite(amount) || amount <= 0) {
                throw new IllegalArgumentException("Invalid payment");
            }
        }
    }

    record ApplicationHealth(
            String instanceId,
            boolean healthy,
            int moduleCount,
            String databaseStatus
    ) {}

    record ScalingDecision(
            DeploymentMode mode,
            String reason
    ) {}

    static class BusinessException extends RuntimeException {
        BusinessException(String message) {
            super(message);
        }
    }

    static class ProductState {
        private final long id;
        private final String name;
        private final double price;
        private int stock;

        ProductState(Product product) {
            id = product.id();
            name = product.name();
            price = product.price();
            stock = product.stock();
        }

        ProductState(ProductState other) {
            id = other.id;
            name = other.name;
            price = other.price;
            stock = other.stock;
        }

        Product toProduct() {
            return new Product(id, name, price, stock);
        }
    }

    static class Order {
        private final String id;
        private final long userId;
        private final long productId;
        private final int quantity;
        private final double total;
        private OrderStatus status;

        Order(
                String id,
                long userId,
                long productId,
                int quantity,
                double total
        ) {
            this.id = id;
            this.userId = userId;
            this.productId = productId;
            this.quantity = quantity;
            this.total = total;
            this.status = OrderStatus.CREATED;
        }

        void markPaid() {
            if (status != OrderStatus.CREATED) {
                throw new BusinessException(
                        "Invalid order state transition"
                );
            }
            status = OrderStatus.PAID;
        }

        String id() {
            return id;
        }

        OrderStatus status() {
            return status;
        }

        double total() {
            return total;
        }
    }

    static class SharedDatabase {

        private final Map<Long, User> users = new HashMap<>();
        private final Map<Long, ProductState> products = new HashMap<>();
        private final Map<String, Order> orders = new HashMap<>();
        private final Map<String, Payment> payments = new HashMap<>();

        void registerUser(User user) {
            if (users.putIfAbsent(user.id(), user) != null) {
                throw new BusinessException("Duplicate user");
            }
        }

        void addProduct(Product product) {
            if (products.putIfAbsent(
                    product.id(),
                    new ProductState(product)
            ) != null) {
                throw new BusinessException("Duplicate product");
            }
        }

        Product product(long id) {
            ProductState product = products.get(id);

            if (product == null) {
                throw new BusinessException("Product not found");
            }

            return product.toProduct();
        }

        DatabaseSnapshot snapshot() {
            Map<Long, ProductState> productCopy = products.entrySet()
                    .stream()
                    .collect(Collectors.toMap(
                            Map.Entry::getKey,
                            entry -> new ProductState(entry.getValue())
                    ));

            return new DatabaseSnapshot(
                    productCopy,
                    new HashMap<>(orders),
                    new HashMap<>(payments)
            );
        }

        void restore(DatabaseSnapshot snapshot) {
            products.clear();
            products.putAll(snapshot.products());

            orders.clear();
            orders.putAll(snapshot.orders());

            payments.clear();
            payments.putAll(snapshot.payments());
        }
    }

    record DatabaseSnapshot(
            Map<Long, ProductState> products,
            Map<String, Order> orders,
            Map<String, Payment> payments
    ) {}

    interface ApplicationModule {
        String name();
    }

    static class UserService implements ApplicationModule {
        private final SharedDatabase database;

        UserService(SharedDatabase database) {
            this.database = database;
        }

        @Override
        public String name() {
            return "users";
        }

        void register(long id, String email) {
            database.registerUser(new User(id, email));
        }
    }

    static class InventoryService implements ApplicationModule {
        private final SharedDatabase database;

        InventoryService(SharedDatabase database) {
            this.database = database;
        }

        @Override
        public String name() {
            return "inventory";
        }

        double reserve(long productId, int quantity) {
            if (quantity <= 0) {
                throw new BusinessException("Quantity must be positive");
            }

            ProductState product = database.products.get(productId);

            if (product == null) {
                throw new BusinessException("Product not found");
            }

            if (product.stock < quantity) {
                throw new BusinessException("Insufficient stock");
            }

            product.stock -= quantity;
            return product.price * quantity;
        }
    }

    static class PaymentService implements ApplicationModule {
        private final SharedDatabase database;
        private boolean providerAvailable = true;

        PaymentService(SharedDatabase database) {
            this.database = database;
        }

        @Override
        public String name() {
            return "payments";
        }

        void setProviderAvailable(boolean available) {
            providerAvailable = available;
        }

        Payment charge(String orderId, double amount) {
            if (database.payments.containsKey(orderId)) {
                return database.payments.get(orderId);
            }

            if (!providerAvailable) {
                throw new BusinessException(
                        "Payment provider unavailable"
                );
            }

            Payment payment = new Payment(
                    UUID.randomUUID().toString(),
                    orderId,
                    amount
            );

            database.payments.put(orderId, payment);
            return payment;
        }
    }

    static class OrderService implements ApplicationModule {
        private final SharedDatabase database;
        private final InventoryService inventory;
        private final PaymentService payments;
        private final AtomicLong sequence = new AtomicLong(1);

        OrderService(
                SharedDatabase database,
                InventoryService inventory,
                PaymentService payments
        ) {
            this.database = database;
            this.inventory = inventory;
            this.payments = payments;
        }

        @Override
        public String name() {
            return "orders";
        }

        synchronized Order create(
                long userId,
                long productId,
                int quantity
        ) {
            if (!database.users.containsKey(userId)) {
                throw new BusinessException("Unknown user");
            }

            DatabaseSnapshot snapshot = database.snapshot();

            try {
                String orderId = "ORD-" + sequence.getAndIncrement();

                double total = inventory.reserve(productId, quantity);

                Order order = new Order(
                        orderId,
                        userId,
                        productId,
                        quantity,
                        total
                );

                database.orders.put(orderId, order);

                payments.charge(orderId, total);

                order.markPaid();

                return order;

            } catch (RuntimeException exception) {
                database.restore(snapshot);
                throw exception;
            }
        }
    }

    static class ScalingPolicy {

        ScalingDecision evaluate(
                double cpuPercent,
                double memoryPercent,
                double requestLatencyMs,
                boolean databaseSaturated
        ) {
            if (!Double.isFinite(cpuPercent)
                    || !Double.isFinite(memoryPercent)
                    || !Double.isFinite(requestLatencyMs)
                    || cpuPercent < 0 || cpuPercent > 100
                    || memoryPercent < 0 || memoryPercent > 100
                    || requestLatencyMs < 0) {
                throw new IllegalArgumentException(
                        "Invalid infrastructure metrics"
                );
            }

            if (databaseSaturated) {
                return new ScalingDecision(
                        DeploymentMode.SINGLE_INSTANCE,
                        "Database is saturated; adding application "
                                + "instances may increase contention"
                );
            }

            if (memoryPercent > 85 || cpuPercent > 85) {
                return new ScalingDecision(
                        DeploymentMode.VERTICAL_SCALE,
                        "Increase resources for the complete application"
                );
            }

            if (requestLatencyMs > 500 || cpuPercent > 70) {
                return new ScalingDecision(
                        DeploymentMode.HORIZONTAL_CLUSTER,
                        "Add complete monolith instances behind a load balancer"
                );
            }

            return new ScalingDecision(
                    DeploymentMode.SINGLE_INSTANCE,
                    "Current capacity is sufficient"
            );
        }
    }

    static class MonolithicApplication {

        private final String instanceId;
        private final SharedDatabase database;

        final UserService users;
        final InventoryService inventory;
        final PaymentService payments;
        final OrderService orders;

        MonolithicApplication(
                String instanceId,
                SharedDatabase database
        ) {
            this.instanceId = instanceId;
            this.database = database;

            users = new UserService(database);
            inventory = new InventoryService(database);
            payments = new PaymentService(database);
            orders = new OrderService(
                    database,
                    inventory,
                    payments
            );
        }

        ApplicationHealth health() {
            return new ApplicationHealth(
                    instanceId,
                    database != null,
                    4,
                    "CONNECTED"
            );
        }

        List<String> modules() {
            return List.of(
                    users.name(),
                    inventory.name(),
                    payments.name(),
                    orders.name()
            );
        }
    }

    public static void main(String[] args) {

        System.out.println("MONOLITH ENTERPRISE APPLICATION");
        System.out.println("================================");

        SharedDatabase database = new SharedDatabase();

        MonolithicApplication application =
                new MonolithicApplication("enterprise-app-01", database);

        application.users.register(1001, "customer@example.com");

        application.database.addProduct(
                new Product(501, "Application Server", 3200.00, 25)
        );

        System.out.println("\nModules:");
        application.modules().forEach(System.out::println);

        System.out.println("\nHealth:");
        System.out.println(application.health());

        System.out.println("\nOrder processing:");

        Order order = application.orders.create(1001, 501, 3);

        System.out.println("Order ID: " + order.id());
        System.out.println("Order status: " + order.status());
        System.out.println("Total: " + order.total());

        System.out.println(
                "Remaining stock: "
                        + application.database.product(501).stock()
        );

        System.out.println("\nPayment failure:");

        application.payments.setProviderAvailable(false);

        try {
            application.orders.create(1001, 501, 2);
        } catch (BusinessException exception) {
            System.out.println(exception.getMessage());
        }

        System.out.println(
                "Stock after rollback: "
                        + application.database.product(501).stock()
        );

        System.out.println("\nScaling policy:");

        ScalingPolicy policy = new ScalingPolicy();

        List<ScalingDecision> decisions = List.of(
                policy.evaluate(35, 40, 100, false),
                policy.evaluate(78, 60, 650, false),
                policy.evaluate(90, 92, 800, false),
                policy.evaluate(40, 45, 700, true)
        );

        decisions.forEach(System.out::println);

        System.out.println("\nArchitectural constraints:");
        System.out.println("- Modules share one deployment lifecycle.");
        System.out.println("- Module communication is in-process.");
        System.out.println("- All instances require compatible application releases.");
        System.out.println("- Database contention can limit horizontal scaling.");
        System.out.println("- A process failure affects every module in that process.");
        System.out.println("- Shared database transactions simplify consistency.");

        if (order.status() != OrderStatus.PAID) {
            throw new IllegalStateException("Order verification failed");
        }

        System.out.println("\nEnterprise checks passed.");
    }
}
