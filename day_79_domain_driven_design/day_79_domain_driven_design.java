import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import java.util.stream.Collectors;

// ============================================================
// DOMAIN-DRIVEN DESIGN: ENTERPRISE DOMAIN MODEL
// ============================================================

public class DomainDrivenDesign {

    // --------------------------------------------------------
    // DOMAIN EXCEPTIONS
    // --------------------------------------------------------

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

    static class ConcurrencyException extends DomainException {
        ConcurrencyException(String message) {
            super(message);
        }
    }

    // --------------------------------------------------------
    // VALUE OBJECTS
    // --------------------------------------------------------

    record Money(BigDecimal amount, String currency) {

        Money {
            Objects.requireNonNull(amount);
            Objects.requireNonNull(currency);

            amount = amount.setScale(2, RoundingMode.HALF_UP);
            currency = currency.toUpperCase();

            if (amount.signum() < 0) {
                throw new ValidationException("Negative money is invalid.");
            }

            if (!currency.matches("[A-Z]{3}")) {
                throw new ValidationException("Invalid currency.");
            }
        }

        Money add(Money other) {
            if (!currency.equals(other.currency)) {
                throw new ValidationException("Currency mismatch.");
            }

            return new Money(amount.add(other.amount), currency);
        }

        Money multiply(int quantity) {
            if (quantity <= 0) {
                throw new ValidationException("Quantity must be positive.");
            }

            return new Money(
                amount.multiply(BigDecimal.valueOf(quantity)),
                currency
            );
        }

        static Money zero(String currency) {
            return new Money(BigDecimal.ZERO, currency);
        }
    }

    record ProductSnapshot(
        UUID productId,
        String name,
        Money unitPrice
    ) {
        ProductSnapshot {
            Objects.requireNonNull(productId);
            Objects.requireNonNull(unitPrice);

            if (name == null || name.isBlank()) {
                throw new ValidationException("Product name is required.");
            }
        }
    }

    // --------------------------------------------------------
    // DOMAIN EVENTS
    // --------------------------------------------------------

    record DomainEvent(
        UUID eventId,
        UUID aggregateId,
        String eventType,
        Instant occurredAt,
        Map<String, String> payload
    ) {
        DomainEvent {
            payload = Map.copyOf(payload);
        }

        static DomainEvent create(
            UUID aggregateId,
            String type,
            Map<String, String> payload
        ) {
            return new DomainEvent(
                UUID.randomUUID(),
                aggregateId,
                type,
                Instant.now(),
                payload
            );
        }
    }

    // --------------------------------------------------------
    // AGGREGATE ROOT
    // --------------------------------------------------------

    abstract static class AggregateRoot {

        private long version;
        private final List<DomainEvent> events = new ArrayList<>();

        public long version() {
            return version;
        }

        public List<DomainEvent> events() {
            return Collections.unmodifiableList(events);
        }

        protected void recordEvent(
            UUID aggregateId,
            String eventType,
            Map<String, String> payload
        ) {
            events.add(
                DomainEvent.create(aggregateId, eventType, payload)
            );
            version++;
        }

        public void clearEvents() {
            events.clear();
        }
    }

    // ========================================================
    // BOUNDED CONTEXT 1: CATALOG
    // ========================================================

    static final class CatalogProduct {

        private final UUID id;
        private final String name;
        private Money price;
        private boolean active = true;
        private long version;

        CatalogProduct(String name, Money price) {
            this.id = UUID.randomUUID();

            if (name == null || name.isBlank()) {
                throw new ValidationException("Product name is required.");
            }

            this.name = name.trim();
            this.price = Objects.requireNonNull(price);
        }

        UUID id() {
            return id;
        }

        String name() {
            return name;
        }

        Money price() {
            return price;
        }

        void changePrice(Money newPrice) {
            if (!price.currency().equals(newPrice.currency())) {
                throw new ValidationException(
                    "Currency cannot change implicitly."
                );
            }

            price = newPrice;
            version++;
        }

        void deactivate() {
            active = false;
            version++;
        }

        ProductSnapshot snapshot() {
            if (!active) {
                throw new DomainException(
                    "Inactive products cannot be purchased."
                );
            }

            return new ProductSnapshot(id, name, price);
        }
    }

    static final class CatalogContext {

        private final Map<UUID, CatalogProduct> products =
            new ConcurrentHashMap<>();

        void register(CatalogProduct product) {
            if (products.putIfAbsent(product.id(), product) != null) {
                throw new DomainException("Duplicate product.");
            }
        }

        ProductSnapshot snapshot(UUID id) {
            CatalogProduct product = products.get(id);

            if (product == null) {
                throw new NotFoundException("Catalog product not found.");
            }

            return product.snapshot();
        }

        CatalogProduct get(UUID id) {
            CatalogProduct product = products.get(id);

            if (product == null) {
                throw new NotFoundException("Product not found.");
            }

            return product;
        }
    }

    // ========================================================
    // BOUNDED CONTEXT 2: INVENTORY
    // ========================================================

    static final class InventoryItem {

        private final UUID productId;
        private int available;
        private int reserved;

        InventoryItem(UUID productId, int available) {
            if (available < 0) {
                throw new ValidationException("Stock cannot be negative.");
            }

            this.productId = productId;
            this.available = available;
        }

        synchronized void reserve(int quantity) {
            if (quantity <= 0 || quantity > available) {
                throw new DomainException("Insufficient stock.");
            }

            available -= quantity;
            reserved += quantity;
        }

        synchronized void release(int quantity) {
            if (quantity <= 0 || quantity > reserved) {
                throw new DomainException("Invalid release quantity.");
            }

            reserved -= quantity;
            available += quantity;
        }

        synchronized void addStock(int quantity) {
            if (quantity <= 0) {
                throw new ValidationException("Invalid stock quantity.");
            }

            available = Math.addExact(available, quantity);
        }

        synchronized int available() {
            return available;
        }

        synchronized int reserved() {
            return reserved;
        }
    }

    static final class InventoryContext {

        private final Map<UUID, InventoryItem> items =
            new ConcurrentHashMap<>();

        void addStock(UUID productId, int quantity) {
            if (quantity <= 0) {
                throw new ValidationException("Stock must be positive.");
            }

            items.compute(productId, (id, existing) -> {
                if (existing == null) {
                    return new InventoryItem(id, quantity);
                }

                existing.addStock(quantity);
                return existing;
            });
        }

        void reserve(UUID productId, int quantity) {
            InventoryItem item = items.get(productId);

            if (item == null) {
                throw new NotFoundException("Inventory item not found.");
            }

            item.reserve(quantity);
        }

        void release(UUID productId, int quantity) {
            InventoryItem item = items.get(productId);

            if (item == null) {
                throw new NotFoundException("Inventory item not found.");
            }

            item.release(quantity);
        }

        InventoryItem get(UUID productId) {
            InventoryItem item = items.get(productId);

            if (item == null) {
                throw new NotFoundException("Inventory item not found.");
            }

            return item;
        }
    }

    // ========================================================
    // BOUNDED CONTEXT 3: ORDER MANAGEMENT
    // ========================================================

    enum OrderStatus {
        DRAFT,
        SUBMITTED,
        CONFIRMED,
        CANCELLED
    }

    record OrderLine(
        ProductSnapshot product,
        int quantity
    ) {

        OrderLine {
            Objects.requireNonNull(product);

            if (quantity <= 0) {
                throw new ValidationException(
                    "Order quantity must be positive."
                );
            }
        }

        Money subtotal() {
            return product.unitPrice().multiply(quantity);
        }
    }

    static final class OrderAggregate extends AggregateRoot {

        private final UUID id;
        private final UUID customerId;
        private final Map<UUID, OrderLine> lines = new LinkedHashMap<>();
        private OrderStatus status = OrderStatus.DRAFT;

        OrderAggregate(UUID customerId) {
            this.id = UUID.randomUUID();
            this.customerId = Objects.requireNonNull(customerId);

            recordEvent(
                id,
                "OrderCreated",
                Map.of("customerId", customerId.toString())
            );
        }

        UUID id() {
            return id;
        }

        OrderStatus status() {
            return status;
        }

        List<OrderLine> lines() {
            return List.copyOf(lines.values());
        }

        Money total() {
            if (lines.isEmpty()) {
                return Money.zero("INR");
            }

            return lines.values().stream()
                .map(OrderLine::subtotal)
                .reduce(Money::add)
                .orElseThrow();
        }

        void addProduct(ProductSnapshot snapshot, int quantity) {
            if (status != OrderStatus.DRAFT) {
                throw new DomainException(
                    "Only draft orders can be modified."
                );
            }

            if (quantity <= 0) {
                throw new ValidationException(
                    "Quantity must be positive."
                );
            }

            if (!lines.isEmpty()) {
                String currency = lines.values().iterator().next()
                    .product().unitPrice().currency();

                if (!currency.equals(snapshot.unitPrice().currency())) {
                    throw new ValidationException(
                        "Mixed currencies are prohibited."
                    );
                }
            }

            lines.compute(snapshot.productId(), (id, existing) -> {
                if (existing == null) {
                    return new OrderLine(snapshot, quantity);
                }

                if (!existing.product().unitPrice()
                    .equals(snapshot.unitPrice())) {
                    throw new DomainException(
                        "Product price snapshot changed."
                    );
                }

                return new OrderLine(
                    snapshot,
                    Math.addExact(existing.quantity(), quantity)
                );
            });
        }

        void submit() {
            if (status != OrderStatus.DRAFT || lines.isEmpty()) {
                throw new DomainException("Order cannot be submitted.");
            }

            status = OrderStatus.SUBMITTED;

            recordEvent(
                id,
                "OrderSubmitted",
                Map.of(
                    "orderId", id.toString(),
                    "amount", total().amount().toPlainString(),
                    "currency", total().currency(),
                    "lineCount", Integer.toString(lines.size())
                )
            );
        }

        void confirm() {
            if (status != OrderStatus.SUBMITTED) {
                throw new DomainException(
                    "Only submitted orders can be confirmed."
                );
            }

            status = OrderStatus.CONFIRMED;

            recordEvent(
                id,
                "OrderConfirmed",
                Map.of("orderId", id.toString())
            );
        }

        void cancel() {
            if (status != OrderStatus.DRAFT &&
                status != OrderStatus.SUBMITTED) {
                throw new DomainException("Order cannot be cancelled.");
            }

            status = OrderStatus.CANCELLED;

            recordEvent(
                id,
                "OrderCancelled",
                Map.of("orderId", id.toString())
            );
        }
    }

    // ========================================================
    // BOUNDED CONTEXT 4: BILLING
    // ========================================================

    static final class Invoice {

        private final UUID id;
        private final UUID orderId;
        private final Money amount;
        private boolean paid;

        Invoice(UUID orderId, Money amount) {
            this.id = UUID.randomUUID();
            this.orderId = orderId;
            this.amount = amount;
        }

        void markPaid() {
            if (paid) {
                throw new DomainException("Invoice already paid.");
            }

            paid = true;
        }

        UUID id() {
            return id;
        }

        Money amount() {
            return amount;
        }

        boolean paid() {
            return paid;
        }
    }

    static final class BillingContext {

        private final Map<UUID, Invoice> invoices =
            new ConcurrentHashMap<>();

        Invoice createInvoice(OrderAggregate order) {
            if (order.status() != OrderStatus.SUBMITTED) {
                throw new DomainException(
                    "Billing requires a submitted order."
                );
            }

            Invoice invoice = new Invoice(order.id(), order.total());

            if (invoices.putIfAbsent(order.id(), invoice) != null) {
                throw new DomainException("Invoice already exists.");
            }

            return invoice;
        }

        Invoice getInvoice(UUID orderId) {
            Invoice invoice = invoices.get(orderId);

            if (invoice == null) {
                throw new NotFoundException("Invoice not found.");
            }

            return invoice;
        }
    }

    // ========================================================
    // DOMAIN EVENT DISPATCHER
    // ========================================================

    static final class DomainEventDispatcher {

        private final Map<String, List<Consumer<DomainEvent>>> handlers =
            new ConcurrentHashMap<>();

        private final java.util.Set<UUID> processed =
            ConcurrentHashMap.newKeySet();

        void subscribe(
            String eventType,
            Consumer<DomainEvent> handler
        ) {
            handlers.computeIfAbsent(
                eventType,
                key -> new ArrayList<>()
            ).add(handler);
        }

        void publish(DomainEvent event) {
            if (processed.contains(event.eventId())) {
                return;
            }

            List<Consumer<DomainEvent>> subscribers =
                handlers.getOrDefault(event.eventType(), List.of());

            for (Consumer<DomainEvent> handler : subscribers) {
                handler.accept(event);
            }

            processed.add(event.eventId());
        }
    }

    // ========================================================
    // REPOSITORY WITH OPTIMISTIC VERSION CHECKING
    // ========================================================

    interface Repository<T, ID> {
        void save(T entity, long expectedVersion);
        Optional<T> findById(ID id);
    }

    static final class OrderRepository
        implements Repository<OrderAggregate, UUID> {

        private record StoredOrder(
            OrderAggregate order,
            long version
        ) {}

        private final Map<UUID, StoredOrder> storage =
            new ConcurrentHashMap<>();

        @Override
        public synchronized void save(
            OrderAggregate order,
            long expectedVersion
        ) {
            StoredOrder existing = storage.get(order.id());

            long currentVersion =
                existing == null ? 0 : existing.version();

            if (currentVersion != expectedVersion) {
                throw new ConcurrencyException(
                    "Expected version " + expectedVersion +
                    ", found " + currentVersion
                );
            }

            storage.put(
                order.id(),
                new StoredOrder(order, order.version())
            );
        }

        @Override
        public Optional<OrderAggregate> findById(UUID id) {
            return Optional.ofNullable(storage.get(id))
                .map(StoredOrder::order);
        }
    }

    // ========================================================
    // APPLICATION SERVICE
    // ========================================================

    static final class OrderApplicationService {

        private final InventoryContext inventory;
        private final BillingContext billing;
        private final DomainEventDispatcher dispatcher;

        OrderApplicationService(
            InventoryContext inventory,
            BillingContext billing,
            DomainEventDispatcher dispatcher
        ) {
            this.inventory = inventory;
            this.billing = billing;
            this.dispatcher = dispatcher;
        }

        Invoice placeOrder(OrderAggregate order) {
            if (order.status() != OrderStatus.DRAFT) {
                throw new DomainException("Order must be a draft.");
            }

            List<OrderLine> reserved = new ArrayList<>();

            try {
                for (OrderLine line : order.lines()) {
                    inventory.reserve(
                        line.product().productId(),
                        line.quantity()
                    );

                    reserved.add(line);
                }

                order.submit();

                Invoice invoice = billing.createInvoice(order);

                for (DomainEvent event : order.events()) {
                    dispatcher.publish(event);
                }

                order.clearEvents();

                return invoice;

            } catch (RuntimeException exception) {
                for (int i = reserved.size() - 1; i >= 0; i--) {
                    OrderLine line = reserved.get(i);

                    inventory.release(
                        line.product().productId(),
                        line.quantity()
                    );
                }

                throw exception;
            }
        }
    }

    // ========================================================
    // EXECUTABLE ENTERPRISE SCENARIO
    // ========================================================

    public static void main(String[] args) {

        CatalogContext catalog = new CatalogContext();
        InventoryContext inventory = new InventoryContext();
        BillingContext billing = new BillingContext();

        OrderRepository repository = new OrderRepository();
        DomainEventDispatcher dispatcher =
            new DomainEventDispatcher();

        CatalogProduct product = new CatalogProduct(
            "Enterprise Database Server",
            new Money(new BigDecimal("125000.00"), "INR")
        );

        catalog.register(product);
        inventory.addStock(product.id(), 12);

        UUID customerId = UUID.randomUUID();

        OrderAggregate order = new OrderAggregate(customerId);

        ProductSnapshot snapshot = catalog.snapshot(product.id());

        order.addProduct(snapshot, 2);

        repository.save(order, 0);

        dispatcher.subscribe(
            "OrderSubmitted",
            event -> System.out.println(
                "Event received: " + event.eventType() +
                " | Aggregate: " + event.aggregateId()
            )
        );

        OrderApplicationService service =
            new OrderApplicationService(
                inventory,
                billing,
                dispatcher
            );

        Invoice invoice = service.placeOrder(order);

        System.out.println("\nENTERPRISE ORDER");
        System.out.println("Order ID: " + order.id());
        System.out.println("Customer ID: " + customerId);
        System.out.println("Status: " + order.status());
        System.out.println("Order total: " + order.total());
        System.out.println("Invoice ID: " + invoice.id());
        System.out.println("Invoice amount: " + invoice.amount());

        InventoryItem item = inventory.get(product.id());

        System.out.println("Available stock: " + item.available());
        System.out.println("Reserved stock: " + item.reserved());

        // Catalog updates do not change existing order snapshots.
        product.changePrice(
            new Money(new BigDecimal("130000.00"), "INR")
        );

        if (!order.total().amount().equals(
            new BigDecimal("250000.00")
        )) {
            throw new AssertionError("Historical price was modified.");
        }

        // The aggregate prevents invalid state transitions.
        try {
            order.submit();
        } catch (DomainException exception) {
            System.out.println(
                "Expected rejection: " + exception.getMessage()
            );
        }

        try {
            inventory.reserve(product.id(), 100);
        } catch (DomainException exception) {
            System.out.println(
                "Expected stock failure: " + exception.getMessage()
            );
        }

        invoice.markPaid();

        System.out.println("Invoice paid: " + invoice.paid());

        System.out.println("\nVALIDATION");

        if (order.status() != OrderStatus.SUBMITTED ||
            item.reserved() != 2 ||
            !invoice.paid()) {
            throw new AssertionError("Domain validation failed.");
        }

        System.out.println("All Java 17 checks passed.");
    }
}
