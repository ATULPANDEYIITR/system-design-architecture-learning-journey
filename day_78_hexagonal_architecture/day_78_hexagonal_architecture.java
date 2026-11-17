import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/*
 * Hexagonal Architecture: Ports and Adapters
 *
 * Enterprise-oriented order processing application.
 *
 * Java 17 features:
 * - Records
 * - Interfaces
 * - Enums
 * - Immutable domain values
 * - Generic repository ports
 * - Service-layer orchestration
 * - Dependency injection
 * - State transitions
 * - Policy validation
 * - Compensation and error handling
 *
 * Compile:
 * javac HexagonalArchitecture.java
 *
 * Run:
 * java HexagonalArchitecture
 */

public class HexagonalArchitecture {

    // ========================================================
    // ERRORS
    // ========================================================

    static class DomainException extends RuntimeException {
        DomainException(String message) {
            super(message);
        }
    }

    static class ApplicationException extends RuntimeException {
        ApplicationException(String message) {
            super(message);
        }

        ApplicationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static class InfrastructureException extends RuntimeException {
        InfrastructureException(String message) {
            super(message);
        }
    }

    // ========================================================
    // DOMAIN
    // ========================================================

    enum OrderStatus {
        PENDING,
        CONFIRMED,
        CANCELLED
    }

    record Money(BigDecimal amount, String currency) {

        Money {
            Objects.requireNonNull(amount);
            Objects.requireNonNull(currency);

            amount = amount.setScale(2, RoundingMode.HALF_UP);

            if (amount.signum() <= 0) {
                throw new DomainException(
                    "Amount must be positive"
                );
            }

            if (!currency.matches("[A-Z]{3}")) {
                throw new DomainException(
                    "Invalid currency"
                );
            }
        }

        Money add(Money other) {
            if (!currency.equals(other.currency)) {
                throw new DomainException(
                    "Currency mismatch"
                );
            }

            return new Money(
                amount.add(other.amount),
                currency
            );
        }

        Money multiply(int quantity) {
            if (quantity <= 0) {
                throw new DomainException(
                    "Quantity must be positive"
                );
            }

            return new Money(
                amount.multiply(BigDecimal.valueOf(quantity)),
                currency
            );
        }
    }

    record OrderLine(
        String productId,
        int quantity,
        Money unitPrice
    ) {

        OrderLine {
            Objects.requireNonNull(productId);
            Objects.requireNonNull(unitPrice);

            if (productId.isBlank()) {
                throw new DomainException(
                    "Product ID is required"
                );
            }

            if (quantity <= 0) {
                throw new DomainException(
                    "Quantity must be positive"
                );
            }
        }

        Money subtotal() {
            return unitPrice.multiply(quantity);
        }
    }

    record OrderCreatedEvent(
        String eventId,
        String orderId,
        String customerId,
        Money amount,
        Instant occurredAt
    ) {}

    static final class Order {

        private final String id;
        private final String customerId;
        private final List<OrderLine> lines;
        private final Instant createdAt;

        private OrderStatus status;
        private long version;

        Order(
            String customerId,
            List<OrderLine> lines
        ) {
            if (customerId == null || customerId.isBlank()) {
                throw new DomainException(
                    "Customer ID is required"
                );
            }

            if (lines == null || lines.isEmpty()) {
                throw new DomainException(
                    "Order must contain items"
                );
            }

            String currency = lines.get(0).unitPrice().currency();

            if (lines.stream().anyMatch(
                line -> !line.unitPrice().currency().equals(currency)
            )) {
                throw new DomainException(
                    "Mixed order currencies are not supported"
                );
            }

            this.id = UUID.randomUUID().toString();
            this.customerId = customerId;
            this.lines = List.copyOf(lines);
            this.createdAt = Instant.now();
            this.status = OrderStatus.PENDING;
            this.version = 0;
        }

        String id() {
            return id;
        }

        String customerId() {
            return customerId;
        }

        List<OrderLine> lines() {
            return lines;
        }

        OrderStatus status() {
            return status;
        }

        long version() {
            return version;
        }

        Instant createdAt() {
            return createdAt;
        }

        Money total() {
            return lines.stream()
                .map(OrderLine::subtotal)
                .reduce(
                    new Money(
                        BigDecimal.ZERO,
                        lines.get(0).unitPrice().currency()
                    ) {
                        // Zero is an internal aggregation identity.
                    },
                    Money::add
                );
        }

        void confirm() {
            transition(
                OrderStatus.PENDING,
                OrderStatus.CONFIRMED
            );
        }

        void cancel() {
            transition(
                OrderStatus.PENDING,
                OrderStatus.CANCELLED
            );
        }

        private void transition(
            OrderStatus expected,
            OrderStatus next
        ) {
            if (status != expected) {
                throw new DomainException(
                    "Invalid order state transition"
                );
            }

            status = next;
            version++;
        }
    }

    // ========================================================
    // GENERIC PORTS
    // ========================================================

    interface RepositoryPort<T, ID> {

        void save(T entity);

        Optional<T> findById(ID id);
    }

    interface OrderRepositoryPort
        extends RepositoryPort<Order, String> {}

    interface InventoryPort {

        boolean reserve(
            String productId,
            int quantity
        );

        void release(
            String productId,
            int quantity
        );
    }

    interface PaymentPort {

        String charge(
            String customerId,
            Money amount,
            String idempotencyKey
        );

        void refund(String paymentId);
    }

    interface EventPublisherPort {

        void publish(OrderCreatedEvent event);
    }

    // ========================================================
    // PRIMARY INPUT PORT
    // ========================================================

    interface PlaceOrderPort {

        OrderResult placeOrder(OrderCommand command);
    }

    record OrderCommand(
        String customerId,
        List<OrderLine> lines
    ) {

        OrderCommand {
            if (customerId == null || customerId.isBlank()) {
                throw new ApplicationException(
                    "Customer ID is required"
                );
            }

            if (lines == null || lines.isEmpty()) {
                throw new ApplicationException(
                    "Order lines are required"
                );
            }

            lines = List.copyOf(lines);
        }
    }

    record OrderResult(
        String orderId,
        OrderStatus status,
        Money total,
        long version
    ) {}

    // ========================================================
    // APPLICATION POLICY
    // ========================================================

    record OrderPolicy(
        int maximumLines,
        int maximumQuantityPerLine,
        BigDecimal maximumOrderAmount
    ) {

        OrderPolicy {
            if (maximumLines <= 0 ||
                maximumQuantityPerLine <= 0 ||
                maximumOrderAmount.signum() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid order policy"
                );
            }
        }

        void validate(OrderCommand command) {
            if (command.lines().size() > maximumLines) {
                throw new ApplicationException(
                    "Order contains too many lines"
                );
            }

            for (OrderLine line : command.lines()) {
                if (line.quantity() > maximumQuantityPerLine) {
                    throw new ApplicationException(
                        "Line quantity exceeds policy"
                    );
                }
            }

            BigDecimal total = command.lines().stream()
                .map(line -> line.subtotal().amount())
                .reduce(BigDecimal.ZERO, BigDecimal::add);

            if (total.compareTo(maximumOrderAmount) > 0) {
                throw new ApplicationException(
                    "Order exceeds maximum permitted value"
                );
            }
        }
    }

    // ========================================================
    // APPLICATION SERVICE
    // ========================================================

    static final class PlaceOrderService
        implements PlaceOrderPort {

        private final OrderRepositoryPort repository;
        private final InventoryPort inventory;
        private final PaymentPort payment;
        private final EventPublisherPort events;
        private final OrderPolicy policy;

        PlaceOrderService(
            OrderRepositoryPort repository,
            InventoryPort inventory,
            PaymentPort payment,
            EventPublisherPort events,
            OrderPolicy policy
        ) {
            this.repository = Objects.requireNonNull(repository);
            this.inventory = Objects.requireNonNull(inventory);
            this.payment = Objects.requireNonNull(payment);
            this.events = Objects.requireNonNull(events);
            this.policy = Objects.requireNonNull(policy);
        }

        @Override
        public OrderResult placeOrder(OrderCommand command) {
            policy.validate(command);

            Order order = new Order(
                command.customerId(),
                command.lines()
            );

            List<OrderLine> reserved = new ArrayList<>();
            String paymentId = null;

            try {
                for (OrderLine line : order.lines()) {
                    if (!inventory.reserve(
                        line.productId(),
                        line.quantity()
                    )) {
                        throw new ApplicationException(
                            "Inventory unavailable: " +
                            line.productId()
                        );
                    }

                    reserved.add(line);
                }

                paymentId = payment.charge(
                    order.customerId(),
                    order.total(),
                    order.id()
                );

                order.confirm();

                repository.save(order);

                events.publish(
                    new OrderCreatedEvent(
                        UUID.randomUUID().toString(),
                        order.id(),
                        order.customerId(),
                        order.total(),
                        Instant.now()
                    )
                );

                return new OrderResult(
                    order.id(),
                    order.status(),
                    order.total(),
                    order.version()
                );

            } catch (Exception exception) {

                if (paymentId != null) {
                    try {
                        payment.refund(paymentId);
                    } catch (Exception refundFailure) {
                        exception.addSuppressed(refundFailure);
                    }
                }

                Collections.reverse(reserved);

                for (OrderLine line : reserved) {
                    try {
                        inventory.release(
                            line.productId(),
                            line.quantity()
                        );
                    } catch (Exception releaseFailure) {
                        exception.addSuppressed(releaseFailure);
                    }
                }

                throw new ApplicationException(
                    "Order processing failed",
                    exception
                );
            }
        }
    }

    // ========================================================
    // SECONDARY ADAPTER: REPOSITORY
    // ========================================================

    static final class MemoryOrderRepository
        implements OrderRepositoryPort {

        private final Map<String, Order> records =
            new ConcurrentHashMap<>();

        @Override
        public void save(Order order) {
            records.compute(order.id(), (id, existing) -> {
                if (existing != null &&
                    order.version() <= existing.version()) {
                    throw new ApplicationException(
                        "Stale order version"
                    );
                }

                return order;
            });
        }

        @Override
        public Optional<Order> findById(String id) {
            return Optional.ofNullable(records.get(id));
        }
    }

    // ========================================================
    // SECONDARY ADAPTER: INVENTORY
    // ========================================================

    static final class MemoryInventoryAdapter
        implements InventoryPort {

        private final Map<String, Integer> stock =
            new ConcurrentHashMap<>();

        MemoryInventoryAdapter(Map<String, Integer> initialStock) {
            initialStock.forEach((product, quantity) -> {
                if (product == null || product.isBlank() ||
                    quantity == null || quantity < 0) {
                    throw new IllegalArgumentException(
                        "Invalid initial inventory"
                    );
                }

                stock.put(product, quantity);
            });
        }

        @Override
        public boolean reserve(String productId, int quantity) {
            if (quantity <= 0) {
                throw new DomainException(
                    "Invalid reservation quantity"
                );
            }

            final boolean[] success = {false};

            stock.compute(productId, (key, available) -> {
                if (available == null || available < quantity) {
                    return available;
                }

                success[0] = true;
                return available - quantity;
            });

            return success[0];
        }

        @Override
        public void release(String productId, int quantity) {
            if (quantity <= 0) {
                throw new DomainException(
                    "Invalid release quantity"
                );
            }

            stock.merge(
                productId,
                quantity,
                Math::addExact
            );
        }

        int available(String productId) {
            return stock.getOrDefault(productId, 0);
        }
    }

    // ========================================================
    // SECONDARY ADAPTER: PAYMENT
    // ========================================================

    static final class MemoryPaymentAdapter
        implements PaymentPort {

        private final Map<String, String> paymentStates =
            new ConcurrentHashMap<>();

        private final Map<String, String> idempotencyKeys =
            new ConcurrentHashMap<>();

        @Override
        public String charge(
            String customerId,
            Money amount,
            String idempotencyKey
        ) {
            Objects.requireNonNull(amount);

            if (customerId == null || customerId.isBlank() ||
                idempotencyKey == null || idempotencyKey.isBlank()) {
                throw new ApplicationException(
                    "Invalid payment request"
                );
            }

            return idempotencyKeys.computeIfAbsent(
                idempotencyKey,
                key -> {
                    String paymentId = UUID.randomUUID().toString();
                    paymentStates.put(paymentId, "CHARGED");
                    return paymentId;
                }
            );
        }

        @Override
        public void refund(String paymentId) {
            String current = paymentStates.get(paymentId);

            if (!"CHARGED".equals(current)) {
                throw new ApplicationException(
                    "Payment cannot be refunded"
                );
            }

            paymentStates.replace(
                paymentId,
                "CHARGED",
                "REFUNDED"
            );
        }
    }

    // ========================================================
    // SECONDARY ADAPTER: EVENTS
    // ========================================================

    static final class MemoryEventAdapter
        implements EventPublisherPort {

        private final List<OrderCreatedEvent> history =
            Collections.synchronizedList(new ArrayList<>());

        @Override
        public void publish(OrderCreatedEvent event) {
            history.add(Objects.requireNonNull(event));
        }

        int count() {
            return history.size();
        }
    }

    // ========================================================
    // PRIMARY ADAPTER
    // ========================================================

    static final class ConsoleOrderAdapter {

        private final PlaceOrderPort useCase;

        ConsoleOrderAdapter(PlaceOrderPort useCase) {
            this.useCase = useCase;
        }

        OrderResult submit() {
            return useCase.placeOrder(
                new OrderCommand(
                    "CUSTOMER-4001",
                    List.of(
                        new OrderLine(
                            "DATABASE-SERVER",
                            1,
                            new Money(
                                new BigDecimal("95000.00"),
                                "INR"
                            )
                        ),
                        new OrderLine(
                            "NETWORK-CABLE",
                            5,
                            new Money(
                                new BigDecimal("250.00"),
                                "INR"
                            )
                        )
                    )
                )
            );
        }
    }

    // ========================================================
    // TESTING
    // ========================================================

    static void runTests() {
        MemoryOrderRepository repository =
            new MemoryOrderRepository();

        MemoryInventoryAdapter inventory =
            new MemoryInventoryAdapter(
                Map.of("P1", 5)
            );

        MemoryPaymentAdapter payment =
            new MemoryPaymentAdapter();

        MemoryEventAdapter events =
            new MemoryEventAdapter();

        PlaceOrderService service =
            new PlaceOrderService(
                repository,
                inventory,
                payment,
                events,
                new OrderPolicy(
                    10,
                    20,
                    new BigDecimal("1000000.00")
                )
            );

        OrderCommand command = new OrderCommand(
            "TEST-CUSTOMER",
            List.of(
                new OrderLine(
                    "P1",
                    2,
                    new Money(
                        new BigDecimal("100.00"),
                        "INR"
                    )
                )
            )
        );

        OrderResult result = service.placeOrder(command);

        if (result.status() != OrderStatus.CONFIRMED ||
            inventory.available("P1") != 3 ||
            events.count() != 1 ||
            repository.findById(result.orderId()).isEmpty()) {
            throw new AssertionError(
                "Successful order test failed"
            );
        }

        try {
            service.placeOrder(
                new OrderCommand(
                    "FAILURE-CUSTOMER",
                    List.of(
                        new OrderLine(
                            "P1",
                            50,
                            new Money(
                                new BigDecimal("100.00"),
                                "INR"
                            )
                        )
                    )
                )
            );

            throw new AssertionError(
                "Expected inventory failure"
            );

        } catch (ApplicationException expected) {
            if (inventory.available("P1") != 3) {
                throw new AssertionError(
                    "Inventory consistency failure"
                );
            }
        }

        try {
            new OrderLine(
                "P1",
                0,
                new Money(new BigDecimal("10.00"), "INR")
            );

            throw new AssertionError(
                "Expected quantity validation"
            );

        } catch (DomainException expected) {
            // Expected.
        }

        System.out.println("Java 17 tests passed.");
    }

    // ========================================================
    // COMPOSITION ROOT
    // ========================================================

    public static void main(String[] args) {

        try {
            MemoryOrderRepository repository =
                new MemoryOrderRepository();

            MemoryInventoryAdapter inventory =
                new MemoryInventoryAdapter(
                    Map.of(
                        "DATABASE-SERVER", 10,
                        "NETWORK-CABLE", 100
                    )
                );

            MemoryPaymentAdapter payment =
                new MemoryPaymentAdapter();

            MemoryEventAdapter events =
                new MemoryEventAdapter();

            OrderPolicy policy = new OrderPolicy(
                20,
                100,
                new BigDecimal("5000000.00")
            );

            PlaceOrderService service =
                new PlaceOrderService(
                    repository,
                    inventory,
                    payment,
                    events,
                    policy
                );

            ConsoleOrderAdapter console =
                new ConsoleOrderAdapter(service);

            OrderResult result = console.submit();

            System.out.println("\nENTERPRISE HEXAGONAL APPLICATION");
            System.out.println("--------------------------------");
            System.out.println("Order ID: " + result.orderId());
            System.out.println("Status: " + result.status());
            System.out.println("Amount: " + result.total().amount());
            System.out.println("Currency: " + result.total().currency());
            System.out.println("Version: " + result.version());
            System.out.println("Published events: " + events.count());

            runTests();

        } catch (Exception exception) {
            System.err.println(
                "Application failure: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}
