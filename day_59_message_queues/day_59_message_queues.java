import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

public class MessageQueueEnterpriseDemo {

    enum MessageState {
        READY,
        IN_FLIGHT,
        ACKNOWLEDGED,
        DEAD_LETTERED
    }

    enum ReviewResult {
        ACKNOWLEDGE,
        RETRY,
        REJECT
    }

    record Message(
        String id,
        String payload,
        String producer,
        Map<String, String> headers,
        Instant createdAt,
        int attempts,
        MessageState state
    ) {
        Message {
            Objects.requireNonNull(id);
            Objects.requireNonNull(payload);
            Objects.requireNonNull(producer);
            Objects.requireNonNull(headers);
            Objects.requireNonNull(createdAt);
            Objects.requireNonNull(state);
        }

        Message withDeliveryAttempt() {
            return new Message(
                id,
                payload,
                producer,
                headers,
                createdAt,
                attempts + 1,
                MessageState.IN_FLIGHT
            );
        }

        Message withState(MessageState newState) {
            return new Message(
                id,
                payload,
                producer,
                headers,
                createdAt,
                attempts,
                newState
            );
        }
    }

    record QueuePolicy(
        String name,
        boolean durable,
        int maxAttempts
    ) {
        QueuePolicy {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Queue name is required"
                );
            }

            if (maxAttempts < 1) {
                throw new IllegalArgumentException(
                    "maxAttempts must be positive"
                );
            }
        }
    }

    static final class Queue {
        private final QueuePolicy policy;
        private final Deque<String> ready = new ArrayDeque<>();
        private final Deque<String> deadLetters = new ArrayDeque<>();

        Queue(QueuePolicy policy) {
            this.policy = policy;
        }

        QueuePolicy policy() {
            return policy;
        }
    }

    record Consumer(
        String id,
        String queueName,
        int prefetch
    ) {
        Consumer {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                    "Consumer ID is required"
                );
            }

            if (prefetch < 1) {
                throw new IllegalArgumentException(
                    "Prefetch must be positive"
                );
            }
        }
    }

    static final class MessageQueueException extends RuntimeException {
        MessageQueueException(String message) {
            super(message);
        }
    }

    static final class MessageBroker {
        private final Map<String, Queue> queues = new HashMap<>();
        private final Map<String, Message> messages = new HashMap<>();
        private final Map<String, Consumer> consumers = new HashMap<>();
        private final Map<String, Set<String>> inFlight =
            new HashMap<>();

        void declareQueue(QueuePolicy policy) {
            Queue existing = queues.get(policy.name());

            if (existing != null) {
                if (!existing.policy().equals(policy)) {
                    throw new MessageQueueException(
                        "Queue policy conflicts with existing queue"
                    );
                }
                return;
            }

            queues.put(policy.name(), new Queue(policy));
        }

        String publish(
            String queueName,
            String payload,
            String producer,
            Map<String, String> headers
        ) {
            Queue queue = requireQueue(queueName);

            if (payload == null || payload.isBlank()) {
                throw new IllegalArgumentException(
                    "Message payload cannot be empty"
                );
            }

            if (producer == null || producer.isBlank()) {
                throw new IllegalArgumentException(
                    "Producer is required"
                );
            }

            String id = UUID.randomUUID().toString();

            Message message = new Message(
                id,
                payload,
                producer,
                Map.copyOf(headers),
                Instant.now(),
                0,
                MessageState.READY
            );

            messages.put(id, message);
            queue.ready.addLast(id);

            return id;
        }

        void registerConsumer(Consumer consumer) {
            if (consumers.containsKey(consumer.id())) {
                throw new MessageQueueException(
                    "Consumer already exists"
                );
            }

            requireQueue(consumer.queueName());
            consumers.put(consumer.id(), consumer);
            inFlight.put(consumer.id(), new HashSet<>());
        }

        private Queue requireQueue(String name) {
            Queue queue = queues.get(name);

            if (queue == null) {
                throw new MessageQueueException(
                    "Queue not found: " + name
                );
            }

            return queue;
        }

        private Consumer requireConsumer(String id) {
            Consumer consumer = consumers.get(id);

            if (consumer == null) {
                throw new MessageQueueException(
                    "Consumer not found: " + id
                );
            }

            return consumer;
        }

        Message deliver(String consumerId) {
            Consumer consumer = requireConsumer(consumerId);
            Queue queue = requireQueue(consumer.queueName());
            Set<String> owned = inFlight.get(consumerId);

            if (owned.size() >= consumer.prefetch()) {
                return null;
            }

            while (!queue.ready.isEmpty()) {
                String id = queue.ready.removeFirst();
                Message message = messages.get(id);

                if (message == null ||
                    message.state() != MessageState.READY) {
                    continue;
                }

                Message delivered = message.withDeliveryAttempt();
                messages.put(id, delivered);
                owned.add(id);

                return delivered;
            }

            return null;
        }

        void settle(
            String consumerId,
            String messageId,
            ReviewResult result
        ) {
            Consumer consumer = requireConsumer(consumerId);
            Queue queue = requireQueue(consumer.queueName());
            Set<String> owned = inFlight.get(consumerId);

            if (!owned.remove(messageId)) {
                throw new MessageQueueException(
                    "Message is not owned by consumer"
                );
            }

            Message message = messages.get(messageId);

            if (message == null) {
                throw new MessageQueueException(
                    "Message not found"
                );
            }

            switch (result) {
                case ACKNOWLEDGE -> {
                    messages.put(
                        messageId,
                        message.withState(
                            MessageState.ACKNOWLEDGED
                        )
                    );
                }

                case RETRY -> {
                    if (message.attempts()
                        >= queue.policy().maxAttempts()) {

                        messages.put(
                            messageId,
                            message.withState(
                                MessageState.DEAD_LETTERED
                            )
                        );

                        queue.deadLetters.addLast(messageId);
                    } else {
                        messages.put(
                            messageId,
                            message.withState(
                                MessageState.READY
                            )
                        );

                        queue.ready.addLast(messageId);
                    }
                }

                case REJECT -> {
                    messages.put(
                        messageId,
                        message.withState(
                            MessageState.DEAD_LETTERED
                        )
                    );

                    queue.deadLetters.addLast(messageId);
                }
            }
        }

        int process(
            String consumerId,
            Function<Message, ReviewResult> handler
        ) {
            Consumer consumer = requireConsumer(consumerId);
            int processed = 0;

            while (inFlight.get(consumerId).size()
                < consumer.prefetch()) {

                Message message = deliver(consumerId);

                if (message == null) {
                    break;
                }

                ReviewResult result;

                try {
                    result = handler.apply(message);
                } catch (RuntimeException exception) {
                    System.err.println(
                        "Consumer failure for "
                        + message.id()
                        + ": "
                        + exception.getMessage()
                    );
                    result = ReviewResult.RETRY;
                }

                settle(
                    consumerId,
                    message.id(),
                    result
                );

                processed++;
            }

            return processed;
        }

        String report(String queueName) {
            Queue queue = requireQueue(queueName);

            long acknowledged = messages.values()
                .stream()
                .filter(m ->
                    m.state() == MessageState.ACKNOWLEDGED
                )
                .count();

            long inFlightCount = messages.values()
                .stream()
                .filter(m ->
                    m.state() == MessageState.IN_FLIGHT
                )
                .count();

            return String.format(
                "ready=%d, inFlight=%d, acknowledged=%d, deadLettered=%d",
                queue.ready.size(),
                inFlightCount,
                acknowledged,
                queue.deadLetters.size()
            );
        }

        List<Message> messagesForState(MessageState state) {
            return messages.values()
                .stream()
                .filter(m -> m.state() == state)
                .collect(Collectors.toList());
        }
    }

    static Function<Message, ReviewResult> paymentHandler() {
        Set<String> processed = new HashSet<>();
        Set<String> failing = Set.of("PAY-FAIL");

        return message -> {
            String paymentId =
                message.headers().get("paymentId");

            if (paymentId == null || paymentId.isBlank()) {
                return ReviewResult.REJECT;
            }

            if (processed.contains(paymentId)) {
                return ReviewResult.ACKNOWLEDGE;
            }

            if (failing.contains(paymentId)) {
                System.out.println(
                    "Temporary failure: "
                    + paymentId
                    + ", attempt="
                    + message.attempts()
                );
                return ReviewResult.RETRY;
            }

            processed.add(paymentId);

            System.out.println(
                "Processed payment: " + paymentId
            );

            return ReviewResult.ACKNOWLEDGE;
        };
    }

    public static void main(String[] args) {
        MessageBroker broker = new MessageBroker();

        broker.declareQueue(
            new QueuePolicy(
                "payments",
                true,
                3
            )
        );

        broker.publish(
            "payments",
            "Authorize card",
            "checkout-service",
            Map.of(
                "paymentId", "PAY-1001",
                "eventType", "payment.created"
            )
        );

        broker.publish(
            "payments",
            "Capture card",
            "checkout-service",
            Map.of(
                "paymentId", "PAY-1002",
                "eventType", "payment.created"
            )
        );

        broker.publish(
            "payments",
            "Capture card",
            "checkout-service",
            Map.of(
                "paymentId", "PAY-FAIL",
                "eventType", "payment.created"
            )
        );

        broker.registerConsumer(
            new Consumer(
                "payment-worker",
                "payments",
                2
            )
        );

        System.out.println(
            "Initial: " + broker.report("payments")
        );

        Function<Message, ReviewResult> handler =
            paymentHandler();

        for (int cycle = 1; cycle <= 5; cycle++) {
            int count = broker.process(
                "payment-worker",
                handler
            );

            System.out.println(
                "Cycle "
                + cycle
                + ": processed="
                + count
                + ", "
                + broker.report("payments")
            );

            if (count == 0) {
                break;
            }
        }

        try {
            broker.publish(
                "missing",
                "invalid",
                "producer",
                Map.of()
            );
        } catch (MessageQueueException exception) {
            System.out.println(
                "Validation: " + exception.getMessage()
            );
        }

        long deadLettered =
            broker.messagesForState(
                MessageState.DEAD_LETTERED
            ).size();

        long acknowledged =
            broker.messagesForState(
                MessageState.ACKNOWLEDGED
            ).size();

        if (deadLettered != 1 || acknowledged != 2) {
            throw new IllegalStateException(
                "Unexpected final queue state"
            );
        }

        System.out.println(
            "Enterprise message queue workflow completed."
        );
    }
}
