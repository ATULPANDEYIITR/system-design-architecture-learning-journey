/*
 * Layered Architecture: Enterprise Order Management
 *
 * Presentation Layer:
 *   ConsoleController
 *
 * Application Layer:
 *   OrderApplicationService
 *
 * Domain Layer:
 *   Order, OrderItem, OrderStatus, business exceptions
 *
 * Infrastructure Layer:
 *   Repository interfaces and adapters
 *
 * Compile:
 *   javac --release 17 LayeredArchitecture.java
 *
 * Execute:
 *   java LayeredArchitecture
 */

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Predicate;
import java.util.stream.Collectors;

// ============================================================
// DOMAIN LAYER
// ============================================================

enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}

class DomainException extends RuntimeException {
    DomainException(String message) {
        super(message);
    }
}

class ValidationException extends DomainException {
    ValidationException(String message) {
        super(message);
    }
}

class OrderNotFoundException extends DomainException {
    OrderNotFoundException(String message) {
        super(message);
    }
}

class InvalidStateException extends DomainException {
    InvalidStateException(String message) {
        super(message);
    }
}

record OrderItem(
    String productId,
    String name,
    int quantity,
    BigDecimal unitPrice
) {
    OrderItem {
        if (productId == null || productId.isBlank()) {
            throw new ValidationException("Product ID is required.");
        }

        if (name == null || name.isBlank()) {
            throw new ValidationException("Product name is required.");
        }

        if (quantity <= 0) {
            throw new ValidationException("Quantity must be positive.");
        }

        if (unitPrice == null || unitPrice.signum() <= 0) {
            throw new ValidationException("Unit price must be positive.");
        }

        unitPrice = unitPrice.setScale(2, RoundingMode.HALF_UP);
    }

    BigDecimal subtotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity))
            .setScale(2, RoundingMode.HALF_UP);
    }
}

final class Order {
    private final String id;
    private final String customerId;
    private final List<OrderItem> items;
    private final Instant createdAt;

    private OrderStatus status;
    private long version;

    Order(String customerId, List<OrderItem> items) {
        if (customerId == null || customerId.isBlank()) {
            throw new ValidationException("Customer ID is required.");
        }

        if (items == null || items.isEmpty()) {
            throw new ValidationException("At least one item is required.");
        }

        Set<String> productIds = new HashSet<>();

        for (OrderItem item : items) {
            Objects.requireNonNull(item, "Order item cannot be null.");

            if (!productIds.add(item.productId())) {
                throw new ValidationException("Duplicate product.");
            }
        }

        this.id = UUID.randomUUID().toString();
        this.customerId = customerId.trim();
        this.items = List.copyOf(items);
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

    List<OrderItem> items() {
        return items;
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

    BigDecimal total() {
        return items.stream()
            .map(OrderItem::subtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add)
            .setScale(2, RoundingMode.HALF_UP);
    }

    void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new InvalidStateException(
                "Only pending orders can be confirmed."
            );
        }

        status = OrderStatus.CONFIRMED;
        version++;
    }

    void cancel() {
        if (status != OrderStatus.PENDING) {
            throw new InvalidStateException(
                "Only pending orders can be cancelled."
            );
        }

        status = OrderStatus.CANCELLED;
        version++;
    }

    OrderSnapshot snapshot() {
        return new OrderSnapshot(
            id,
            customerId,
            status,
            total(),
            version,
            createdAt,
            items
        );
    }
}

record OrderSnapshot(
    String id,
    String customerId,
    OrderStatus status,
    BigDecimal total,
    long version,
    Instant createdAt,
    List<OrderItem> items
) {
    OrderSnapshot {
        items = List.copyOf(items);
    }
}

// ============================================================
// APPLICATION LAYER
// ============================================================

interface UseCase<I, O> {
    O execute(I input);
}

record CreateOrderCommand(
    String customerId,
    List<OrderItem> items
) {
    CreateOrderCommand {
        if (items == null) {
            throw new ValidationException("Items are required.");
        }

        items = List.copyOf(items);
    }
}

interface OrderRepository {
    void save(Order order);

    Optional<OrderSnapshot> findById(String id);

    List<OrderSnapshot> findAll();
}

interface AuditPort {
    void record(String event, String aggregateId);
}

final class OrderApplicationService {

    private final OrderRepository repository;
    private final AuditPort audit;

    OrderApplicationService(
        OrderRepository repository,
        AuditPort audit
    ) {
        this.repository = Objects.requireNonNull(repository);
        this.audit = Objects.requireNonNull(audit);
    }

    public OrderSnapshot createOrder(CreateOrderCommand command) {
        Objects.requireNonNull(command);

        Order order = new Order(
            command.customerId(),
            command.items()
        );

        repository.save(order);
        audit.record("ORDER_CREATED", order.id());

        return order.snapshot();
    }

    public OrderSnapshot confirmOrder(String id) {
        Order order = loadAggregate(id);

        order.confirm();
        repository.save(order);

        audit.record("ORDER_CONFIRMED", id);

        return order.snapshot();
    }

    public OrderSnapshot cancelOrder(String id) {
        Order order = loadAggregate(id);

        order.cancel();
        repository.save(order);

        audit.record("ORDER_CANCELLED", id);

        return order.snapshot();
    }

    public OrderSnapshot getOrder(String id) {
        return repository.findById(id)
            .orElseThrow(() ->
                new OrderNotFoundException("Order not found: " + id)
            );
    }

    public List<OrderSnapshot> listOrders(
        Predicate<OrderSnapshot> filter
    ) {
        Objects.requireNonNull(filter);

        return repository.findAll().stream()
            .filter(filter)
            .toList();
    }

    private Order loadAggregate(String id) {
        OrderSnapshot snapshot = getOrder(id);

        Order order = new Order(
            snapshot.customerId(),
            snapshot.items()
        );

        // The in-memory adapter supports aggregate reconstruction
        // through a separate persistence mechanism.
        return RepositoryRehydrator.rehydrate(snapshot);
    }
}

// ============================================================
// DOMAIN REHYDRATION
// ============================================================

final class RepositoryRehydrator {

    private RepositoryRehydrator() {}

    static Order rehydrate(OrderSnapshot snapshot) {
        return OrderStateFactory.restore(snapshot);
    }
}

/*
 * Persistence restoration is kept separate from public domain
 * construction. The factory represents the trusted repository boundary.
 */
final class OrderStateFactory {

    private OrderStateFactory() {}

    static Order restore(OrderSnapshot snapshot) {
        Order order = new Order(
            snapshot.customerId(),
            snapshot.items()
        );

        order.restoreState(
            snapshot.id(),
            snapshot.status(),
            snapshot.version(),
            snapshot.createdAt()
        );

        return order;
    }
}

// Package-private restoration method remains inaccessible to
// external callers in a multi-package production deployment.
final class OrderRestorationAccess {

    private OrderRestorationAccess() {}
}

// ============================================================
// INFRASTRUCTURE LAYER
// ============================================================

final class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, OrderSnapshot> storage =
        new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        storage.compute(order.id(), (id, existing) -> {
            if (
                existing != null &&
                order.version() < existing.version()
            ) {
                throw new InvalidStateException("Stale aggregate version.");
            }

            return order.snapshot();
        });
    }

    @Override
    public Optional<OrderSnapshot> findById(String id) {
        return Optional.ofNullable(storage.get(id));
    }

    @Override
    public List<OrderSnapshot> findAll() {
        return List.copyOf(storage.values());
    }
}

final class FileAuditAdapter implements AuditPort {

    private final Path path;

    FileAuditAdapter(Path path) {
        this.path = path;
    }

    @Override
    public synchronized void record(
        String event,
        String aggregateId
    ) {
        String line = String.format(
            "%s | %s | %s%n",
            Instant.now(),
            event,
            aggregateId
        );

        try {
            Path parent = path.toAbsolutePath().getParent();

            if (parent != null) {
                Files.createDirectories(parent);
            }

            Files.writeString(
                path,
                line,
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            );
        } catch (IOException exception) {
            throw new IllegalStateException(
                "Audit persistence failed.",
                exception
            );
        }
    }
}

// ============================================================
// PRESENTATION LAYER
// ============================================================

final class ConsoleController {

    private final OrderApplicationService service;

    ConsoleController(OrderApplicationService service) {
        this.service = service;
    }

    void run() {
        List<OrderItem> items = List.of(
            new OrderItem(
                "PROD-100",
                "Enterprise Laptop",
                2,
                new BigDecimal("75000.00")
            ),
            new OrderItem(
                "PROD-101",
                "Wireless Mouse",
                3,
                new BigDecimal("1200.00")
            )
        );

        CreateOrderCommand command = new CreateOrderCommand(
            "CUSTOMER-500",
            items
        );

        OrderSnapshot created = service.createOrder(command);

        display(created);

        OrderSnapshot confirmed =
            service.confirmOrder(created.id());

        System.out.println("\nAfter confirmation:");
        display(confirmed);

        List<OrderSnapshot> confirmedOrders =
            service.listOrders(
                order -> order.status() == OrderStatus.CONFIRMED
            );

        System.out.println(
            "\nConfirmed orders: " + confirmedOrders.size()
        );
    }

    private void display(OrderSnapshot order) {
        System.out.println("\nOrder ID: " + order.id());
        System.out.println("Customer: " + order.customerId());
        System.out.println("Status: " + order.status());
        System.out.println("Total: " + order.total());
        System.out.println("Version: " + order.version());
    }
}

// ============================================================
// TESTING AND APPLICATION ENTRY POINT
// ============================================================

public class LayeredArchitecture {

    private static void testInvalidTransitions(
        OrderApplicationService service,
        String orderId
    ) {
        try {
            service.cancelOrder(orderId);
            throw new AssertionError("Invalid cancellation succeeded.");
        } catch (InvalidStateException expected) {
            System.out.println("Invalid transition rejected.");
        }
    }

    private static void runTests() {
        OrderRepository repository = new InMemoryOrderRepository();
        AuditPort audit = (event, id) -> {};

        OrderApplicationService service =
            new OrderApplicationService(repository, audit);

        OrderSnapshot created = service.createOrder(
            new CreateOrderCommand(
                "TEST-CUSTOMER",
                List.of(
                    new OrderItem(
                        "P1",
                        "Server",
                        2,
                        new BigDecimal("1000.00")
                    )
                )
            )
        );

        if (!created.total().equals(new BigDecimal("2000.00"))) {
            throw new AssertionError("Incorrect order total.");
        }

        OrderSnapshot confirmed =
            service.confirmOrder(created.id());

        if (confirmed.status() != OrderStatus.CONFIRMED) {
            throw new AssertionError("Confirmation failed.");
        }

        testInvalidTransitions(service, created.id());

        try {
            service.getOrder("UNKNOWN");
            throw new AssertionError("Unknown order was retrieved.");
        } catch (OrderNotFoundException expected) {
            // Expected failure.
        }

        System.out.println("All Java 17 tests passed.");
    }

    public static void main(String[] args) {
        try {
            if (
                args.length > 0 &&
                args[0].equals("--test")
            ) {
                runTests();
                return;
            }

            OrderRepository repository =
                new InMemoryOrderRepository();

            AuditPort audit =
                new FileAuditAdapter(
                    Path.of("layered-data", "audit.log")
                );

            OrderApplicationService service =
                new OrderApplicationService(repository, audit);

            ConsoleController controller =
                new ConsoleController(service);

            controller.run();

        } catch (DomainException exception) {
            System.err.println(
                "Business operation failed: " + exception.getMessage()
            );

            System.exit(1);

        } catch (Exception exception) {
            System.err.println(
                "Application failure: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}
