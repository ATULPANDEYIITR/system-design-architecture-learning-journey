import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public class EventDrivenArchitectureDemo {

    enum EventType {
        ORDER_CREATED,
        PAYMENT_AUTHORIZED,
        ORDER_CONFIRMED,
        ORDER_CANCELLED
    }

    record DomainEvent(
            UUID eventId,
            EventType type,
            String aggregateId,
            Map<String, String> payload,
            String producer,
            Instant occurredAt
    ) {
        DomainEvent {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(type);
            Objects.requireNonNull(payload);
            Objects.requireNonNull(producer);

            if (aggregateId == null || aggregateId.isBlank()) {
                throw new IllegalArgumentException(
                        "aggregateId cannot be empty"
                );
            }

            if (producer.isBlank()) {
                throw new IllegalArgumentException(
                        "producer cannot be empty"
                );
            }

            payload = Map.copyOf(payload);
        }
    }

    record Subscription(
            String consumerName,
            EventType eventType,
            EventHandler handler
    ) {}

    record FailedDelivery(
            DomainEvent event,
            String consumerName,
            String reason
    ) {}

    @FunctionalInterface
    interface EventHandler {
        void handle(DomainEvent event);
    }

    static final class EventBus {
        private final Map<EventType, List<Subscription>> subscriptions =
                new EnumMap<>(EventType.class);

        private final Deque<DomainEvent> queue = new ArrayDeque<>();

        private final Set<String> processedDeliveries =
                new HashSet<>();

        private final List<FailedDelivery> deadLetters =
                new ArrayList<>();

        void subscribe(
                String consumerName,
                EventType eventType,
                EventHandler handler
        ) {
            if (consumerName == null || consumerName.isBlank()) {
                throw new IllegalArgumentException(
                        "consumerName cannot be empty"
                );
            }

            subscriptions
                    .computeIfAbsent(eventType, ignored -> new ArrayList<>())
                    .add(new Subscription(
                            consumerName,
                            eventType,
                            handler
                    ));
        }

        void publish(DomainEvent event) {
            Objects.requireNonNull(event);
            queue.addLast(event);
        }

        void process() {
            while (!queue.isEmpty()) {
                DomainEvent event = queue.removeFirst();

                for (Subscription subscription :
                        subscriptions.getOrDefault(
                                event.type(),
                                List.of()
                        )) {

                    String deliveryKey =
                            event.eventId() + ":" +
                            subscription.consumerName();

                    if (processedDeliveries.contains(deliveryKey)) {
                        continue;
                    }

                    try {
                        subscription.handler().handle(event);
                        processedDeliveries.add(deliveryKey);
                    } catch (RuntimeException exception) {
                        deadLetters.add(
                                new FailedDelivery(
                                        event,
                                        subscription.consumerName(),
                                        exception.getMessage()
                                )
                        );
                    }
                }
            }
        }

        int pendingCount() {
            return queue.size();
        }

        List<FailedDelivery> deadLetters() {
            return List.copyOf(deadLetters);
        }
    }

    record Order(
            String orderId,
            String customerId,
            double amount,
            String status
    ) {}

    static final class OrderService {
        private final EventBus bus;
        private final Map<String, Order> orders = new HashMap<>();

        OrderService(EventBus bus) {
            this.bus = bus;
        }

        String createOrder(String customerId, double amount) {
            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException(
                        "customerId is required"
                );
            }

            if (!Double.isFinite(amount) || amount <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive"
                );
            }

            String orderId = "ORD-" + UUID.randomUUID();

            Order order = new Order(
                    orderId,
                    customerId,
                    Math.round(amount * 100.0) / 100.0,
                    "CREATED"
            );

            orders.put(orderId, order);

            bus.publish(new DomainEvent(
                    UUID.randomUUID(),
                    EventType.ORDER_CREATED,
                    orderId,
                    Map.of(
                            "customerId", customerId,
                            "amount", Double.toString(order.amount())
                    ),
                    "order-service",
                    Instant.now()
            ));

            return orderId;
        }
    }

    static final class PaymentService {
        private final Set<String> authorizedOrders = new HashSet<>();

        PaymentService(EventBus bus) {
            bus.subscribe(
                    "payment-service",
                    EventType.ORDER_CREATED,
                    this::handle
            );
        }

        private void handle(DomainEvent event) {
            String amount = event.payload().get("amount");

            if (amount == null) {
                throw new IllegalArgumentException(
                        "Payment amount is missing"
                );
            }

            double parsedAmount = Double.parseDouble(amount);

            if (!Double.isFinite(parsedAmount) || parsedAmount <= 0) {
                throw new IllegalArgumentException(
                        "Invalid payment amount"
                );
            }

            if (authorizedOrders.add(event.aggregateId())) {
                System.out.printf(
                        "[payment-service] Authorized %s amount=%.2f%n",
                        event.aggregateId(),
                        parsedAmount
                );
            }
        }

        int authorizationCount() {
            return authorizedOrders.size();
        }
    }

    static final class NotificationService {
        private final List<String> messages = new ArrayList<>();

        NotificationService(EventBus bus) {
            bus.subscribe(
                    "notification-service",
                    EventType.ORDER_CREATED,
                    event -> messages.add(
                            "Order created: " + event.aggregateId()
                    )
            );

            bus.subscribe(
                    "notification-service",
                    EventType.ORDER_CONFIRMED,
                    event -> messages.add(
                            "Order confirmed: " + event.aggregateId()
                    )
            );
        }

        int messageCount() {
            return messages.size();
        }
    }

    static final class AnalyticsService {
        private final Map<EventType, Integer> counts =
                new EnumMap<>(EventType.class);

        AnalyticsService(EventBus bus) {
            for (EventType type : EventType.values()) {
                bus.subscribe(
                        "analytics-service",
                        type,
                        event -> counts.merge(
                                event.type(),
                                1,
                                Integer::sum
                        )
                );
            }
        }

        int count(EventType type) {
            return counts.getOrDefault(type, 0);
        }
    }

    public static void main(String[] args) {
        EventBus bus = new EventBus();

        PaymentService paymentService =
                new PaymentService(bus);

        NotificationService notificationService =
                new NotificationService(bus);

        AnalyticsService analyticsService =
                new AnalyticsService(bus);

        OrderService orderService =
                new OrderService(bus);

        String orderId =
                orderService.createOrder(
                        "customer-1001",
                        1499.50
                );

        System.out.println(
                "Pending before processing: " +
                bus.pendingCount()
        );

        bus.process();

        System.out.println(
                "Pending after processing: " +
                bus.pendingCount()
        );

        System.out.println(
                "Payment authorizations: " +
                paymentService.authorizationCount()
        );

        System.out.println(
                "Notifications: " +
                notificationService.messageCount()
        );

        System.out.println(
                "Created events: " +
                analyticsService.count(
                        EventType.ORDER_CREATED
                )
        );

        // A new consumer can be added without changing OrderService.
        List<String> auditLog = new ArrayList<>();

        bus.subscribe(
                "audit-service",
                EventType.ORDER_CREATED,
                event -> auditLog.add(event.eventId().toString())
        );

        orderService.createOrder("customer-1002", 250.00);
        bus.process();

        System.out.println(
                "Audit entries: " + auditLog.size()
        );

        // Explicit failure state is captured as a failed delivery.
        bus.subscribe(
                "unavailable-service",
                EventType.ORDER_CONFIRMED,
                event -> {
                    throw new IllegalStateException(
                            "Downstream service unavailable"
                    );
                }
        );

        bus.publish(new DomainEvent(
                UUID.randomUUID(),
                EventType.ORDER_CONFIRMED,
                orderId,
                Map.of("confirmedBy", "workflow-service"),
                "workflow-service",
                Instant.now()
        ));

        bus.process();

        System.out.println(
                "Dead-lettered deliveries: " +
                bus.deadLetters().size()
        );

        try {
            orderService.createOrder("", 100);
        } catch (IllegalArgumentException exception) {
            System.out.println(
                    "Validation failure: " +
                    exception.getMessage()
            );
        }

        /*
         * Enterprise production considerations:
         *
         * - Store events durably before acknowledging publication.
         * - Use transactional outbox patterns when database changes
         *   and event publication must remain consistent.
         * - Use retry policies and durable dead-letter queues.
         * - Partition by aggregate ID when ordering matters.
         * - Authenticate publishers and authorize consumers.
         * - Minimize sensitive data in event payloads.
         * - Add correlation and causation IDs for distributed tracing.
         * - Monitor consumer lag, queue depth, latency, and failures.
         */
    }
}
