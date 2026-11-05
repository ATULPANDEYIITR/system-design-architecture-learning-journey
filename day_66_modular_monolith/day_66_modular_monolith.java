import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

// ============================================================
// MODULAR MONOLITH: ENTERPRISE ORDER MANAGEMENT
//
// Java 17
//
// Architecture:
//   shared
//   inventory
//   payments
//   orders
//   notifications
//   migration
//
// Each module owns its domain state and exposes explicit
// application-level operations.
// ============================================================

public class ModularMonolith {

    // ========================================================
    // SHARED KERNEL
    // ========================================================

    static class DomainException extends RuntimeException {
        DomainException(String message) {
            super(message);
        }
    }

    static class ValidationException extends DomainException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class NotFoundException extends DomainException {
        NotFoundException(String message) {
            super(message);
        }
    }

    static class InsufficientStockException extends DomainException {
        InsufficientStockException(String message) {
            super(message);
        }
    }

    enum OrderStatus {
        PENDING,
        CONFIRMED,
        CANCELLED
    }

    enum PaymentStatus {
        AUTHORIZED,
        REFUNDED
    }

    record DomainEvent(
        UUID eventId,
        String eventType,
        String aggregateId,
        Map<String, String> payload,
        java.time.Instant occurredAt
    ) {
        DomainEvent {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(eventType);
            Objects.requireNonNull(aggregateId);
            payload = Map.copyOf(payload);
            Objects.requireNonNull(occurredAt);
        }

        static DomainEvent create(
            String eventType,
            String aggregateId,
            Map<String, String> payload
        ) {
            return new DomainEvent(
                UUID.randomUUID(),
                eventType,
                aggregateId,
                payload,
                java.time.Instant.now()
            );
        }
    }

    // ========================================================
    // DOMAIN EVENT DISPATCHER
    // ========================================================

    static class EventDispatcher {

        private final Map<String, List<java.util.function.Consumer<DomainEvent>>>
            subscribers = new ConcurrentHashMap<>();

        void subscribe(
            String eventType,
            java.util.function.Consumer<DomainEvent> handler
        ) {
            subscribers.computeIfAbsent(
                eventType,
                key -> new java.util.concurrent.CopyOnWriteArrayList<>()
            ).add(handler);
        }

        void publish(DomainEvent event) {
            List<java.util.function.Consumer<DomainEvent>> handlers =
                subscribers.getOrDefault(
                    event.eventType(),
                    List.of()
                );

            for (var handler : handlers) {
                handler.accept(event);
            }
        }
    }

    // ========================================================
    // INVENTORY MODULE
    // ========================================================

    static class InventoryModule {

        record Product(
            String id,
            String name,
            long priceInCents,
            int stock
        ) {
            Product {
                if (id == null || id.isBlank()) {
                    throw new ValidationException("Product ID required.");
                }

                if (name == null || name.isBlank()) {
                    throw new ValidationException("Product name required.");
                }

                if (priceInCents <= 0 || stock < 0) {
                    throw new ValidationException("Invalid product data.");
                }
            }
        }

        record Reservation(
            UUID id,
            String productId,
            int quantity
        ) {}

        private static class ProductState {
            private final String id;
            private final String name;
            private final long priceInCents;
            private int stock;

            ProductState(Product product) {
                this.id = product.id();
                this.name = product.name();
                this.priceInCents = product.priceInCents();
                this.stock = product.stock();
            }

            Product snapshot() {
                return new Product(
                    id,
                    name,
                    priceInCents,
                    stock
                );
            }
        }

        private final Map<String, ProductState> products =
            new HashMap<>();

        private final Map<UUID, Reservation> reservations =
            new HashMap<>();

        private final Set<UUID> committedReservations =
            new HashSet<>();

        void addProduct(Product product) {
            if (products.containsKey(product.id())) {
                throw new ValidationException("Duplicate product.");
            }

            products.put(product.id(), new ProductState(product));
        }

        Product getProduct(String productId) {
            ProductState product = products.get(productId);

            if (product == null) {
                throw new NotFoundException("Product not found.");
            }

            return product.snapshot();
        }

        synchronized Reservation reserve(
            String productId,
            int quantity
        ) {
            if (quantity <= 0) {
                throw new ValidationException(
                    "Quantity must be positive."
                );
            }

            ProductState product = products.get(productId);

            if (product == null) {
                throw new NotFoundException("Product not found.");
            }

            if (product.stock < quantity) {
                throw new InsufficientStockException(
                    "Insufficient inventory."
                );
            }

            product.stock -= quantity;

            Reservation reservation = new Reservation(
                UUID.randomUUID(),
                productId,
                quantity
            );

            reservations.put(reservation.id(), reservation);

            return reservation;
        }

        synchronized void release(UUID reservationId) {
            Reservation reservation = reservations.get(reservationId);

            if (reservation == null) {
                throw new NotFoundException("Reservation not found.");
            }

            if (committedReservations.contains(reservationId)) {
                throw new DomainException(
                    "Committed reservation cannot be released."
                );
            }

            if (reservations.remove(reservationId) != null) {
                products.get(reservation.productId()).stock +=
                    reservation.quantity();
            }
        }

        synchronized void commit(UUID reservationId) {
            if (!reservations.containsKey(reservationId)) {
                throw new DomainException("Active reservation required.");
            }

            committedReservations.add(reservationId);
        }

        int availableStock(String productId) {
            return getProduct(productId).stock();
        }
    }

    // ========================================================
    // PAYMENT MODULE
    // ========================================================

    static class PaymentModule {

        record Payment(
            UUID id,
            String orderId,
            long amountInCents,
            PaymentStatus status
        ) {}

        private final Map<UUID, Payment> payments = new HashMap<>();

        synchronized Payment authorize(
            String orderId,
            long amountInCents
        ) {
            if (orderId == null || orderId.isBlank()) {
                throw new ValidationException("Order ID required.");
            }

            if (amountInCents <= 0) {
                throw new ValidationException("Invalid payment amount.");
            }

            Payment payment = new Payment(
                UUID.randomUUID(),
                orderId,
                amountInCents,
                PaymentStatus.AUTHORIZED
            );

            payments.put(payment.id(), payment);

            return payment;
        }

        synchronized Payment refund(UUID paymentId) {
            Payment payment = payments.get(paymentId);

            if (payment == null) {
                throw new NotFoundException("Payment not found.");
            }

            if (payment.status() != PaymentStatus.AUTHORIZED) {
                throw new DomainException("Payment cannot be refunded.");
            }

            Payment refunded = new Payment(
                payment.id(),
                payment.orderId(),
                payment.amountInCents(),
                PaymentStatus.REFUNDED
            );

            payments.put(paymentId, refunded);

            return refunded;
        }

        Payment getPayment(UUID paymentId) {
            Payment payment = payments.get(paymentId);

            if (payment == null) {
                throw new NotFoundException("Payment not found.");
            }

            return payment;
        }
    }

    // ========================================================
    // ORDER MODULE
    // ========================================================

    static class OrderModule {

        record Order(
            UUID id,
            String customerId,
            String productId,
            int quantity,
            long totalInCents,
            UUID reservationId,
            UUID paymentId,
            OrderStatus status
        ) {}

        private final InventoryModule inventory;
        private final PaymentModule payments;
        private final EventDispatcher events;

        private final Map<UUID, Order> orders = new HashMap<>();

        OrderModule(
            InventoryModule inventory,
            PaymentModule payments,
            EventDispatcher events
        ) {
            this.inventory = inventory;
            this.payments = payments;
            this.events = events;
        }

        synchronized Order createOrder(
            String customerId,
            String productId,
            int quantity
        ) {
            if (customerId == null || customerId.isBlank()) {
                throw new ValidationException("Customer ID required.");
            }

            if (quantity <= 0) {
                throw new ValidationException("Invalid quantity.");
            }

            InventoryModule.Product product =
                inventory.getProduct(productId);

            long total;

            try {
                total = Math.multiplyExact(
                    product.priceInCents(),
                    (long) quantity
                );
            } catch (ArithmeticException error) {
                throw new ValidationException("Order amount overflow.");
            }

            UUID orderId = UUID.randomUUID();

            InventoryModule.Reservation reservation =
                inventory.reserve(productId, quantity);

            PaymentModule.Payment payment = null;

            try {
                payment = payments.authorize(
                    orderId.toString(),
                    total
                );

                Order order = new Order(
                    orderId,
                    customerId,
                    productId,
                    quantity,
                    total,
                    reservation.id(),
                    payment.id(),
                    OrderStatus.CONFIRMED
                );

                inventory.commit(reservation.id());
                orders.put(order.id(), order);

                events.publish(
                    DomainEvent.create(
                        "ORDER_CONFIRMED",
                        orderId.toString(),
                        Map.of(
                            "customerId", customerId,
                            "amountInCents", Long.toString(total)
                        )
                    )
                );

                return order;

            } catch (RuntimeException error) {
                if (payment != null) {
                    try {
                        payments.refund(payment.id());
                    } catch (RuntimeException compensationError) {
                        error.addSuppressed(compensationError);
                    }
                }

                try {
                    inventory.release(reservation.id());
                } catch (RuntimeException compensationError) {
                    error.addSuppressed(compensationError);
                }

                throw error;
            }
        }

        synchronized Order cancelOrder(UUID orderId) {
            Order order = orders.get(orderId);

            if (order == null) {
                throw new NotFoundException("Order not found.");
            }

            if (order.status() == OrderStatus.CANCELLED) {
                return order;
            }

            if (order.status() != OrderStatus.CONFIRMED) {
                throw new DomainException("Invalid cancellation state.");
            }

            payments.refund(order.paymentId());

            Order cancelled = new Order(
                order.id(),
                order.customerId(),
                order.productId(),
                order.quantity(),
                order.totalInCents(),
                order.reservationId(),
                order.paymentId(),
                OrderStatus.CANCELLED
            );

            orders.put(orderId, cancelled);

            events.publish(
                DomainEvent.create(
                    "ORDER_CANCELLED",
                    orderId.toString(),
                    Map.of("orderId", orderId.toString())
                )
            );

            return cancelled;
        }

        Order getOrder(UUID id) {
            Order order = orders.get(id);

            if (order == null) {
                throw new NotFoundException("Order not found.");
            }

            return order;
        }
    }

    // ========================================================
    // NOTIFICATION MODULE
    // ========================================================

    static class NotificationModule {

        private final List<String> deliveredMessages =
            new ArrayList<>();

        NotificationModule(EventDispatcher events) {
            events.subscribe(
                "ORDER_CONFIRMED",
                event -> deliveredMessages.add(
                    "Confirmed: " + event.aggregateId()
                )
            );

            events.subscribe(
                "ORDER_CANCELLED",
                event -> deliveredMessages.add(
                    "Cancelled: " + event.aggregateId()
                )
            );
        }

        List<String> messages() {
            return List.copyOf(deliveredMessages);
        }
    }

    // ========================================================
    // ARCHITECTURE POLICY
    // ========================================================

    static class ArchitecturePolicy {

        private final Map<String, Set<String>> allowed =
            Map.of(
                "orders", Set.of("inventory", "payments", "shared"),
                "inventory", Set.of("shared"),
                "payments", Set.of("shared"),
                "notifications", Set.of("shared")
            );

        List<String> validate(
            Map<String, Set<String>> dependencies
        ) {
            List<String> violations = new ArrayList<>();

            dependencies.forEach((source, targets) -> {
                Set<String> permitted = allowed.get(source);

                if (permitted == null) {
                    violations.add("Unknown module: " + source);
                    return;
                }

                targets.stream()
                    .filter(target -> !permitted.contains(target))
                    .forEach(target ->
                        violations.add(source + " -> " + target)
                    );
            });

            return List.copyOf(violations);
        }
    }

    // ========================================================
    // MIGRATION GOVERNANCE
    // ========================================================

    enum MigrationStage {
        MONOLITH,
        BOUNDARIES_DEFINED,
        MODULE_ISOLATED,
        CONTRACT_STABLE,
        EXTERNALIZED
    }

    static class ModuleMigration {

        private final String moduleName;

        private MigrationStage stage = MigrationStage.MONOLITH;

        private String endpoint;

        private static final Map<MigrationStage, MigrationStage>
            TRANSITIONS = Map.of(
                MigrationStage.MONOLITH,
                MigrationStage.BOUNDARIES_DEFINED,

                MigrationStage.BOUNDARIES_DEFINED,
                MigrationStage.MODULE_ISOLATED,

                MigrationStage.MODULE_ISOLATED,
                MigrationStage.CONTRACT_STABLE,

                MigrationStage.CONTRACT_STABLE,
                MigrationStage.EXTERNALIZED
            );

        ModuleMigration(String moduleName) {
            if (moduleName == null || moduleName.isBlank()) {
                throw new ValidationException("Module name required.");
            }

            this.moduleName = moduleName;
        }

        void advance(String newEndpoint) {
            MigrationStage next = TRANSITIONS.get(stage);

            if (next == null) {
                throw new DomainException("Migration already completed.");
            }

            if (next == MigrationStage.EXTERNALIZED) {
                if (newEndpoint == null ||
                    !newEndpoint.startsWith("https://")) {
                    throw new ValidationException(
                        "HTTPS endpoint required."
                    );
                }

                endpoint = newEndpoint;
            }

            stage = next;
        }

        MigrationStage stage() {
            return stage;
        }

        String endpoint() {
            return endpoint;
        }

        String moduleName() {
            return moduleName;
        }
    }

    // ========================================================
    // APPLICATION COMPOSITION ROOT
    // ========================================================

    static class Application {

        final EventDispatcher events = new EventDispatcher();

        final InventoryModule inventory = new InventoryModule();

        final PaymentModule payments = new PaymentModule();

        final OrderModule orders = new OrderModule(
            inventory,
            payments,
            events
        );

        final NotificationModule notifications =
            new NotificationModule(events);
    }

    // ========================================================
    // EXECUTABLE DEMONSTRATION
    // ========================================================

    public static void main(String[] args) {

        Application app = new Application();

        app.inventory.addProduct(
            new InventoryModule.Product(
                "LAPTOP-01",
                "Enterprise Laptop",
                7500000L,
                15
            )
        );

        System.out.println("MODULAR MONOLITH");

        OrderModule.Order order = app.orders.createOrder(
            "CUSTOMER-100",
            "LAPTOP-01",
            2
        );

        System.out.println("\nORDER");
        System.out.println("ID: " + order.id());
        System.out.println("Amount: " + order.totalInCents());
        System.out.println("Status: " + order.status());

        System.out.println("\nINVENTORY");
        System.out.println(
            "Available stock: " +
            app.inventory.availableStock("LAPTOP-01")
        );

        System.out.println("\nPAYMENT");
        System.out.println(
            app.payments.getPayment(order.paymentId())
        );

        System.out.println("\nNOTIFICATIONS");
        app.notifications.messages().forEach(System.out::println);

        OrderModule.Order cancelled =
            app.orders.cancelOrder(order.id());

        System.out.println("\nCANCELLATION");
        System.out.println(cancelled.status());

        System.out.println(
            app.payments.getPayment(order.paymentId()).status()
        );

        // Dependency architecture validation.
        ArchitecturePolicy policy = new ArchitecturePolicy();

        Map<String, Set<String>> dependencies = Map.of(
            "orders", Set.of("inventory", "payments", "shared"),
            "inventory", Set.of("shared"),
            "payments", Set.of("shared"),
            "notifications", Set.of("shared")
        );

        List<String> violations = policy.validate(dependencies);

        if (!violations.isEmpty()) {
            throw new DomainException(
                "Unexpected architecture violations."
            );
        }

        System.out.println("\nARCHITECTURE: VALID");

        List<String> invalid = policy.validate(
            Map.of("inventory", Set.of("orders"))
        );

        System.out.println("Invalid dependencies: " + invalid);

        // Module extraction lifecycle.
        ModuleMigration migration =
            new ModuleMigration("notifications");

        migration.advance(null);
        migration.advance(null);
        migration.advance(null);
        migration.advance("https://notifications.example.com");

        System.out.println("\nMIGRATION");
        System.out.println("Module: " + migration.moduleName());
        System.out.println("Stage: " + migration.stage());
        System.out.println("Endpoint: " + migration.endpoint());

        // Insufficient stock must not create an order.
        try {
            app.orders.createOrder(
                "CUSTOMER-200",
                "LAPTOP-01",
                100
            );
        } catch (InsufficientStockException error) {
            System.out.println(
                "\nEXPECTED FAILURE: " + error.getMessage()
            );
        }

        System.out.println(
            "Final stock: " +
            app.inventory.availableStock("LAPTOP-01")
        );

        System.out.println("\nExecution completed.");
    }
}
