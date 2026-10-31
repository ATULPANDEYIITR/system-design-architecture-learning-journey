import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PubSubEnterpriseDemo {

    enum DeliveryState {
        DELIVERED,
        FAILED,
        SKIPPED
    }

    enum SubscriberState {
        ACTIVE,
        SUSPENDED
    }

    record Event(
        String id,
        String topic,
        Map<String, String> attributes,
        Instant createdAt
    ) {
        Event {
            Objects.requireNonNull(id);
            Objects.requireNonNull(topic);
            Objects.requireNonNull(attributes);
            Objects.requireNonNull(createdAt);
            attributes = Collections.unmodifiableMap(
                new HashMap<>(attributes)
            );
        }
    }

    record DeliveryResult(
        String subscriberId,
        DeliveryState state,
        String error
    ) {}

    record SubscriberPolicy(
        int maxFailures
    ) {
        SubscriberPolicy {
            if (maxFailures < 1) {
                throw new IllegalArgumentException(
                    "maxFailures must be positive"
                );
            }
        }
    }

    @FunctionalInterface
    interface EventHandler {
        void handle(Event event) throws Exception;
    }

    static final class Subscription {
        private final String id;
        private final EventHandler handler;
        private final SubscriberPolicy policy;

        private int failures;
        private SubscriberState state = SubscriberState.ACTIVE;

        Subscription(
            String id,
            EventHandler handler,
            SubscriberPolicy policy
        ) {
            this.id = requireText(id, "subscriber ID");
            this.handler = Objects.requireNonNull(handler);
            this.policy = Objects.requireNonNull(policy);
        }

        String id() {
            return id;
        }

        SubscriberState state() {
            return state;
        }

        synchronized DeliveryResult deliver(Event event) {
            if (state == SubscriberState.SUSPENDED) {
                return new DeliveryResult(
                    id,
                    DeliveryState.SKIPPED,
                    "Subscriber is suspended"
                );
            }

            try {
                handler.handle(event);
                failures = 0;

                return new DeliveryResult(
                    id,
                    DeliveryState.DELIVERED,
                    ""
                );
            } catch (Exception exception) {
                failures++;

                if (failures >= policy.maxFailures()) {
                    state = SubscriberState.SUSPENDED;
                }

                return new DeliveryResult(
                    id,
                    DeliveryState.FAILED,
                    exception.getMessage()
                );
            }
        }
    }

    static final class PubSubBroker implements AutoCloseable {
        private final Map<String, Map<String, Subscription>> subscriptions =
            new HashMap<>();

        private final Deque<Event> history = new ArrayDeque<>();
        private final int historyLimit;
        private final ExecutorService executor;

        PubSubBroker(int historyLimit, int workerCount) {
            if (historyLimit < 1) {
                throw new IllegalArgumentException(
                    "historyLimit must be positive"
                );
            }

            if (workerCount < 1) {
                throw new IllegalArgumentException(
                    "workerCount must be positive"
                );
            }

            this.historyLimit = historyLimit;
            this.executor = Executors.newFixedThreadPool(workerCount);
        }

        synchronized void subscribe(
            String topic,
            String subscriberId,
            EventHandler handler,
            SubscriberPolicy policy
        ) {
            validateTopic(topic);

            Map<String, Subscription> topicSubscriptions =
                subscriptions.computeIfAbsent(
                    topic,
                    ignored -> new HashMap<>()
                );

            if (topicSubscriptions.containsKey(subscriberId)) {
                throw new IllegalStateException(
                    "Subscriber already exists for topic"
                );
            }

            Subscription subscription =
                new Subscription(subscriberId, handler, policy);

            topicSubscriptions.put(subscriberId, subscription);
        }

        synchronized boolean unsubscribe(
            String topic,
            String subscriberId
        ) {
            validateTopic(topic);

            Map<String, Subscription> topicSubscriptions =
                subscriptions.get(topic);

            if (topicSubscriptions == null) {
                return false;
            }

            boolean removed = topicSubscriptions.remove(subscriberId) != null;

            if (topicSubscriptions.isEmpty()) {
                subscriptions.remove(topic);
            }

            return removed;
        }

        CompletableFuture<List<DeliveryResult>> publish(
            String topic,
            Map<String, String> attributes
        ) {
            validateTopic(topic);

            if (attributes == null || attributes.isEmpty()) {
                throw new IllegalArgumentException(
                    "Event attributes cannot be empty"
                );
            }

            Event event = new Event(
                UUID.randomUUID().toString(),
                topic,
                attributes,
                Instant.now()
            );

            List<Subscription> consumers;

            synchronized (this) {
                history.addLast(event);

                while (history.size() > historyLimit) {
                    history.removeFirst();
                }

                consumers = new ArrayList<>(
                    subscriptions
                        .getOrDefault(topic, Map.of())
                        .values()
                );
            }

            /*
             * Routing state is copied while synchronized. Handlers execute
             * outside that lock, preventing application code from blocking
             * unrelated subscriptions.
             */
            List<CompletableFuture<DeliveryResult>> deliveries =
                consumers.stream()
                    .map(subscription ->
                        CompletableFuture.supplyAsync(
                            () -> subscription.deliver(event),
                            executor
                        )
                    )
                    .toList();

            CompletableFuture<Void> all =
                CompletableFuture.allOf(
                    deliveries.toArray(new CompletableFuture[0])
                );

            return all.thenApply(ignored ->
                deliveries.stream()
                    .map(CompletableFuture::join)
                    .toList()
            );
        }

        synchronized List<Event> history(String topic) {
            validateTopic(topic);

            return history.stream()
                .filter(event -> event.topic().equals(topic))
                .toList();
        }

        synchronized Map<String, Integer> statistics() {
            Map<String, Integer> result = new HashMap<>();

            subscriptions.forEach(
                (topic, consumers) ->
                    result.put(topic, consumers.size())
            );

            return result;
        }

        private static void validateTopic(String topic) {
            requireText(topic, "topic");

            if (topic.length() > 128) {
                throw new IllegalArgumentException(
                    "Topic exceeds 128 characters"
                );
            }

            if (topic.chars().anyMatch(Character::isWhitespace)) {
                throw new IllegalArgumentException(
                    "Topic cannot contain whitespace"
                );
            }
        }

        private static String requireText(String value, String field) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                    field + " cannot be blank"
                );
            }

            return value;
        }

        @Override
        public void close() {
            executor.shutdown();
        }
    }

    public static void main(String[] args) {
        try (PubSubBroker broker = new PubSubBroker(100, 4)) {
            SubscriberPolicy normalPolicy = new SubscriberPolicy(3);
            SubscriberPolicy fragilePolicy = new SubscriberPolicy(2);

            broker.subscribe(
                "payment.completed",
                "ledger-service",
                event -> System.out.println(
                    "[LEDGER] " + event.attributes()
                ),
                normalPolicy
            );

            broker.subscribe(
                "payment.completed",
                "fraud-service",
                event -> {
                    String amount = event.attributes().get("amount");

                    if (Double.parseDouble(amount) > 10000) {
                        throw new IllegalStateException(
                            "Fraud service requires manual review"
                        );
                    }

                    System.out.println("[FRAUD] approved for screening");
                },
                fragilePolicy
            );

            broker.subscribe(
                "payment.completed",
                "notification-service",
                event -> System.out.println(
                    "[NOTIFICATION] customer="
                        + event.attributes().get("customerId")
                ),
                normalPolicy
            );

            Map<String, String> payment = Map.of(
                "paymentId", "PAY-1001",
                "customerId", "CUS-90",
                "amount", "4500",
                "currency", "INR"
            );

            List<DeliveryResult> results =
                broker.publish("payment.completed", payment).join();

            System.out.println("Delivery results:");
            results.forEach(System.out::println);

            Map<String, String> highValuePayment = Map.of(
                "paymentId", "PAY-1002",
                "customerId", "CUS-91",
                "amount", "15000",
                "currency", "INR"
            );

            for (int attempt = 1; attempt <= 2; attempt++) {
                List<DeliveryResult> failedAttempt =
                    broker.publish(
                        "payment.completed",
                        highValuePayment
                    ).join();

                System.out.println(
                    "High-value attempt " + attempt + ":"
                );
                failedAttempt.forEach(System.out::println);
            }

            System.out.println(
                "History size: "
                    + broker.history("payment.completed").size()
            );

            System.out.println(
                "Statistics: " + broker.statistics()
            );

            if (!broker.unsubscribe(
                "payment.completed",
                "notification-service"
            )) {
                throw new IllegalStateException(
                    "Expected subscription was not removed"
                );
            }

            try {
                broker.publish(
                    "payment completed",
                    payment
                ).join();
            } catch (IllegalArgumentException exception) {
                System.out.println(
                    "Validation rejected: "
                        + exception.getMessage()
                );
            } catch (CompletionException exception) {
                System.out.println(
                    "Publication failed: "
                        + exception.getCause()
                );
            }
        }
    }
}
