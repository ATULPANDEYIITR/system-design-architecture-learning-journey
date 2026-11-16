import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/*
 * Clean Architecture: Dependency Inversion and Boundaries
 *
 * Enterprise-oriented order-management architecture.
 *
 * Demonstrates:
 * - Domain entities and value objects
 * - Application input and output ports
 * - Repository and payment interfaces
 * - Dependency injection
 * - Immutable records
 * - Application services
 * - Policy-driven architecture validation
 * - Dependency cycle detection
 * - State transitions
 * - Exception translation
 * - Thread-safe in-memory infrastructure
 *
 * Java 17
 *
 * Compile:
 * javac CleanArchitectureDemo.java
 *
 * Run:
 * java CleanArchitectureDemo
 */

public class CleanArchitectureDemo {

    // ========================================================
    // 1. DOMAIN LAYER
    // ========================================================

    enum OrderStatus {
        PENDING,
        PAID,
        CANCELLED
    }

    static class DomainException extends RuntimeException {
        DomainException(String message) {
            super(message);
        }
    }

    static class ApplicationException extends RuntimeException {
        ApplicationException(String message) {
            super(message);
        }
    }

    static class InfrastructureException extends RuntimeException {
        InfrastructureException(String message) {
            super(message);
        }
    }

    record Money(BigDecimal amount, String currency) {

        Money {
            Objects.requireNonNull(amount, "Amount is required.");
            Objects.requireNonNull(currency, "Currency is required.");

            amount = amount.setScale(2, RoundingMode.HALF_UP);
            currency = currency.toUpperCase(Locale.ROOT);

            if (amount.signum() < 0) {
                throw new DomainException("Money cannot be negative.");
            }

            if (!currency.matches("[A-Z]{3}")) {
                throw new DomainException("Invalid currency.");
            }
        }

        Money add(Money other) {
            if (!currency.equals(other.currency)) {
                throw new DomainException("Currency mismatch.");
            }

            return new Money(
                amount.add(other.amount),
                currency
            );
        }

        Money multiply(int quantity) {
            if (quantity <= 0 || quantity > 1000) {
                throw new DomainException("Invalid quantity.");
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
            if (productId == null || productId.isBlank()) {
                throw new DomainException("Product ID is required.");
            }

            Objects.requireNonNull(unitPrice);

            if (quantity <= 0 || quantity > 1000) {
                throw new DomainException("Invalid quantity.");
            }
        }

        Money subtotal() {
            return unitPrice.multiply(quantity);
        }
    }

    static final class Order {

        private final String id;
        private final String customerId;
        private final List<OrderLine> lines;

        private OrderStatus status;
        private long version;

        Order(
            String id,
            String customerId,
            List<OrderLine> lines
        ) {

            if (id == null || id.isBlank()) {
                throw new DomainException("Order ID is required.");
            }

            if (customerId == null || customerId.isBlank()) {
                throw new DomainException("Customer ID is required.");
            }

            if (lines == null || lines.isEmpty() || lines.size() > 100) {
                throw new DomainException("Invalid order lines.");
            }

            this.id = id;
            this.customerId = customerId;
            this.lines = List.copyOf(lines);
            this.status = OrderStatus.PENDING;
            this.version = 1;

            total();
        }

        Money total() {
            String currency = lines.get(0).unitPrice().currency();

            Money total = new Money(
                BigDecimal.ZERO,
                currency
            );

            for (OrderLine line : lines) {
                total = total.add(line.subtotal());
            }

            return total;
        }

        void markPaid() {
            requireStatus(OrderStatus.PENDING);

            status = OrderStatus.PAID;
            version++;
        }

        void cancel() {
            requireStatus(OrderStatus.PENDING);

            status = OrderStatus.CANCELLED;
            version++;
        }

        private void requireStatus(OrderStatus expected) {
            if (status != expected) {
                throw new DomainException(
                    "Invalid order state transition: " +
                    status + " -> requested operation"
                );
            }
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
    }

    // ========================================================
    // 2. APPLICATION PORTS
    // ========================================================

    interface OrderRepository {
        void save(Order order);

        Optional<Order> findById(String id);
    }

    interface PaymentGateway {
        boolean charge(String orderId, Money amount);
    }

    interface EventPublisher {
        void publish(DomainEvent event);
    }

    interface PlaceOrderInputPort {
        Order execute(PlaceOrderCommand command);
    }

    // ========================================================
    // 3. APPLICATION COMMANDS AND EVENTS
    // ========================================================

    record PlaceOrderCommand(
        String customerId,
        List<OrderLine> lines
    ) {

        PlaceOrderCommand {
            if (customerId == null || customerId.isBlank()) {
                throw new ApplicationException(
                    "Customer ID is required."
                );
            }

            lines = List.copyOf(lines);
        }
    }

    record DomainEvent(
        String eventType,
        String aggregateId,
        String description
    ) {}

    // ========================================================
    // 4. APPLICATION SERVICE
    // ========================================================

    static final class PlaceOrderService
        implements PlaceOrderInputPort {

        private final OrderRepository repository;
        private final PaymentGateway paymentGateway;
        private final EventPublisher eventPublisher;

        PlaceOrderService(
            OrderRepository repository,
            PaymentGateway paymentGateway,
            EventPublisher eventPublisher
        ) {

            this.repository = Objects.requireNonNull(repository);
            this.paymentGateway = Objects.requireNonNull(paymentGateway);
            this.eventPublisher = Objects.requireNonNull(eventPublisher);
        }

        @Override
        public Order execute(PlaceOrderCommand command) {

            Order order = new Order(
                UUID.randomUUID().toString(),
                command.customerId(),
                command.lines()
            );

            repository.save(order);

            try {
                boolean paid = paymentGateway.charge(
                    order.id(),
                    order.total()
                );

                if (!paid) {
                    throw new ApplicationException("Payment declined.");
                }

                order.markPaid();
                repository.save(order);

                eventPublisher.publish(
                    new DomainEvent(
                        "ORDER_PAID",
                        order.id(),
                        "Order payment completed."
                    )
                );

                return order;

            } catch (RuntimeException error) {

                if (order.status() == OrderStatus.PENDING) {
                    order.cancel();
                    repository.save(order);
                }

                if (
                    error instanceof DomainException ||
                    error instanceof ApplicationException
                ) {
                    throw error;
                }

                throw new ApplicationException(
                    "Order processing failed."
                );
            }
        }
    }

    // ========================================================
    // 5. CANCELLATION SERVICE
    // ========================================================

    static final class CancelOrderService {

        private final OrderRepository repository;

        CancelOrderService(OrderRepository repository) {
            this.repository = repository;
        }

        Order execute(String orderId) {

            Order order = repository.findById(orderId)
                .orElseThrow(() ->
                    new ApplicationException("Order not found.")
                );

            order.cancel();
            repository.save(order);

            return order;
        }
    }

    // ========================================================
    // 6. INFRASTRUCTURE ADAPTERS
    // ========================================================

    static final class InMemoryOrderRepository
        implements OrderRepository {

        private final Map<String, Order> orders =
            new ConcurrentHashMap<>();

        @Override
        public void save(Order order) {
            orders.put(order.id(), order);
        }

        @Override
        public Optional<Order> findById(String id) {
            return Optional.ofNullable(orders.get(id));
        }

        int count() {
            return orders.size();
        }
    }

    static final class SimulatedPaymentGateway
        implements PaymentGateway {

        private final boolean successful;

        private final Set<String> processed =
            ConcurrentHashMap.newKeySet();

        SimulatedPaymentGateway(boolean successful) {
            this.successful = successful;
        }

        @Override
        public boolean charge(String orderId, Money amount) {

            if (processed.contains(orderId)) {
                return true;
            }

            if (!successful) {
                return false;
            }

            if (amount.amount().signum() <= 0) {
                return false;
            }

            processed.add(orderId);

            return true;
        }
    }

    static final class ConsoleEventPublisher
        implements EventPublisher {

        @Override
        public void publish(DomainEvent event) {
            System.out.println(
                "[EVENT] " + event.eventType() +
                " | " + event.aggregateId() +
                " | " + event.description()
            );
        }
    }

    // ========================================================
    // 7. ARCHITECTURE POLICY MODEL
    // ========================================================

    enum Layer {
        DOMAIN,
        APPLICATION,
        ADAPTER,
        INFRASTRUCTURE
    }

    record Dependency(
        String source,
        String target,
        Layer sourceLayer,
        Layer targetLayer
    ) {}

    record ArchitectureReport(
        List<String> violations
    ) {

        ArchitectureReport {
            violations = List.copyOf(violations);
        }

        boolean isValid() {
            return violations.isEmpty();
        }
    }

    static final class ArchitecturePolicy {

        private final Map<Layer, Set<Layer>> allowed =
            new EnumMap<>(Layer.class);

        ArchitecturePolicy() {

            allowed.put(
                Layer.DOMAIN,
                Set.of()
            );

            allowed.put(
                Layer.APPLICATION,
                Set.of(Layer.DOMAIN)
            );

            allowed.put(
                Layer.ADAPTER,
                Set.of(
                    Layer.APPLICATION,
                    Layer.DOMAIN
                )
            );

            allowed.put(
                Layer.INFRASTRUCTURE,
                Set.of(
                    Layer.APPLICATION,
                    Layer.DOMAIN,
                    Layer.ADAPTER
                )
            );
        }

        ArchitectureReport evaluate(
            List<Dependency> dependencies
        ) {

            List<String> violations = new ArrayList<>();

            for (Dependency dependency : dependencies) {

                Set<Layer> permitted = allowed.get(
                    dependency.sourceLayer()
                );

                if (
                    permitted == null ||
                    !permitted.contains(dependency.targetLayer())
                ) {

                    violations.add(
                        dependency.source() +
                        " cannot depend on " +
                        dependency.target()
                    );
                }
            }

            return new ArchitectureReport(violations);
        }
    }

    // ========================================================
    // 8. DEPENDENCY CYCLE DETECTION
    // ========================================================

    static final class DependencyGraph {

        private final Map<String, Set<String>> graph =
            new LinkedHashMap<>();

        void addDependency(String source, String target) {
            graph.computeIfAbsent(
                source,
                ignored -> new LinkedHashSet<>()
            ).add(target);

            graph.computeIfAbsent(
                target,
                ignored -> new LinkedHashSet<>()
            );
        }

        List<List<String>> findCycles() {

            Set<String> completed = new HashSet<>();
            Set<String> active = new HashSet<>();

            Deque<String> path = new ArrayDeque<>();

            List<List<String>> cycles = new ArrayList<>();

            for (String node : graph.keySet()) {
                visit(
                    node,
                    completed,
                    active,
                    path,
                    cycles
                );
            }

            return cycles;
        }

        private void visit(
            String node,
            Set<String> completed,
            Set<String> active,
            Deque<String> path,
            List<List<String>> cycles
        ) {

            if (active.contains(node)) {

                List<String> cycle = new ArrayList<>();
                boolean capture = false;

                for (String item : path) {
                    if (item.equals(node)) {
                        capture = true;
                    }

                    if (capture) {
                        cycle.add(item);
                    }
                }

                cycle.add(node);
                cycles.add(cycle);

                return;
            }

            if (completed.contains(node)) {
                return;
            }

            active.add(node);
            path.addLast(node);

            for (String neighbor : graph.getOrDefault(
                node,
                Set.of()
            )) {
                visit(
                    neighbor,
                    completed,
                    active,
                    path,
                    cycles
                );
            }

            path.removeLast();
            active.remove(node);
            completed.add(node);
        }
    }

    // ========================================================
    // 9. ENTERPRISE COMPOSITION ROOT
    // ========================================================

    static final class ApplicationConfiguration {

        private final OrderRepository repository;
        private final PaymentGateway paymentGateway;
        private final EventPublisher publisher;

        ApplicationConfiguration() {

            this.repository = new InMemoryOrderRepository();

            this.paymentGateway =
                new SimulatedPaymentGateway(true);

            this.publisher =
                new ConsoleEventPublisher();
        }

        PlaceOrderInputPort placeOrderService() {
            return new PlaceOrderService(
                repository,
                paymentGateway,
                publisher
            );
        }

        OrderRepository repository() {
            return repository;
        }
    }

    // ========================================================
    // 10. EXECUTABLE VALIDATION
    // ========================================================

    static void require(
        boolean condition,
        String message
    ) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    static List<OrderLine> sampleLines() {

        return List.of(
            new OrderLine(
                "LAPTOP-001",
                1,
                new Money(
                    new BigDecimal("65000.00"),
                    "INR"
                )
            ),
            new OrderLine(
                "MOUSE-001",
                2,
                new Money(
                    new BigDecimal("750.00"),
                    "INR"
                )
            )
        );
    }

    static void demonstrateArchitecture() {

        ArchitecturePolicy policy =
            new ArchitecturePolicy();

        List<Dependency> dependencies = List.of(
            new Dependency(
                "PlaceOrderService",
                "Order",
                Layer.APPLICATION,
                Layer.DOMAIN
            ),
            new Dependency(
                "DatabaseAdapter",
                "OrderRepository",
                Layer.INFRASTRUCTURE,
                Layer.APPLICATION
            ),
            new Dependency(
                "Order",
                "DatabaseAdapter",
                Layer.DOMAIN,
                Layer.INFRASTRUCTURE
            )
        );

        ArchitectureReport report =
            policy.evaluate(dependencies);

        require(
            !report.isValid(),
            "Invalid dependency was not detected."
        );

        System.out.println("\nArchitecture violations:");

        report.violations().forEach(
            violation -> System.out.println(violation)
        );

        DependencyGraph graph = new DependencyGraph();

        graph.addDependency("domain", "application");
        graph.addDependency("application", "adapter");
        graph.addDependency("adapter", "domain");

        System.out.println("\nDependency cycles:");

        graph.findCycles().forEach(
            cycle -> System.out.println(
                String.join(" -> ", cycle)
            )
        );
    }

    static void demonstrateOrderWorkflow() {

        ApplicationConfiguration configuration =
            new ApplicationConfiguration();

        PlaceOrderInputPort service =
            configuration.placeOrderService();

        Order order = service.execute(
            new PlaceOrderCommand(
                "CUSTOMER-100",
                sampleLines()
            )
        );

        require(
            order.status() == OrderStatus.PAID,
            "Order should be paid."
        );

        require(
            order.total().amount().compareTo(
                new BigDecimal("66500.00")
            ) == 0,
            "Incorrect order total."
        );

        System.out.println("\nSuccessful order:");
        System.out.println("ID: " + order.id());
        System.out.println("Customer: " + order.customerId());
        System.out.println("Amount: " + order.total());
        System.out.println("Status: " + order.status());
        System.out.println("Version: " + order.version());

        CancelOrderService cancel =
            new CancelOrderService(configuration.repository());

        try {
            cancel.execute(order.id());
            throw new IllegalStateException(
                "Paid order should not be cancelled."
            );
        } catch (DomainException expected) {
            System.out.println(
                "Paid order cancellation rejected correctly."
            );
        }
    }

    static void demonstrateFailureWorkflow() {

        OrderRepository repository =
            new InMemoryOrderRepository();

        PaymentGateway payment =
            new SimulatedPaymentGateway(false);

        EventPublisher publisher =
            new ConsoleEventPublisher();

        PlaceOrderInputPort service =
            new PlaceOrderService(
                repository,
                payment,
                publisher
            );

        try {
            service.execute(
                new PlaceOrderCommand(
                    "CUSTOMER-200",
                    sampleLines()
                )
            );

            throw new IllegalStateException(
                "Expected payment failure."
            );

        } catch (ApplicationException expected) {

            System.out.println(
                "\nPayment failure handled: " +
                expected.getMessage()
            );

            if (repository instanceof InMemoryOrderRepository memory) {
                require(
                    memory.count() == 1,
                    "Failed order should remain recorded."
                );
            }
        }
    }

    static void demonstrateDomainValidation() {

        try {
            new Money(
                new BigDecimal("-100"),
                "INR"
            );

            throw new IllegalStateException(
                "Negative amount should fail."
            );

        } catch (DomainException expected) {
            System.out.println(
                "\nNegative amount rejected."
            );
        }

        try {
            new OrderLine(
                "INVALID",
                0,
                new Money(
                    BigDecimal.TEN,
                    "INR"
                )
            );

            throw new IllegalStateException(
                "Zero quantity should fail."
            );

        } catch (DomainException expected) {
            System.out.println(
                "Invalid quantity rejected."
            );
        }
    }

    public static void main(String[] args) {

        System.out.println(
            "CLEAN ARCHITECTURE ENTERPRISE MODEL"
        );

        demonstrateArchitecture();
        demonstrateDomainValidation();
        demonstrateOrderWorkflow();
        demonstrateFailureWorkflow();

        System.out.println(
            "\nAll Java 17 demonstrations passed."
        );
    }
}
