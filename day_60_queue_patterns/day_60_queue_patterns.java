import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class QueuePatternsDemo {

    enum MessageState {
        READY,
        IN_FLIGHT,
        ACKNOWLEDGED,
        DEAD_LETTERED
    }

    enum Settlement {
        ACKNOWLEDGED,
        REQUEUED,
        DEAD_LETTERED,
        EXPIRED
    }

    record QueuePolicy(
        int capacity,
        int maximumAttempts,
        Duration visibilityTimeout
    ) {
        QueuePolicy {
            if (capacity < 1) {
                throw new IllegalArgumentException(
                    "Capacity must be at least one."
                );
            }

            if (maximumAttempts < 1) {
                throw new IllegalArgumentException(
                    "Maximum attempts must be at least one."
                );
            }

            Objects.requireNonNull(visibilityTimeout);

            if (
                visibilityTimeout.isZero() ||
                visibilityTimeout.isNegative()
            ) {
                throw new IllegalArgumentException(
                    "Visibility timeout must be positive."
                );
            }
        }
    }

    record Delivery(
        String messageId,
        String payload,
        String consumerId,
        String receipt,
        int attempt,
        long leaseDeadlineNanos
    ) {}

    record DeadLetter(
        String messageId,
        String payload,
        int attempts,
        String reason
    ) {}

    record QueueMetrics(
        int ready,
        int inFlight,
        int acknowledged,
        int deadLettered
    ) {
        int outstanding() {
            return ready + inFlight;
        }
    }

    static class QueueException extends RuntimeException {
        QueueException(String message) {
            super(message);
        }
    }

    static class QueueFullException extends QueueException {
        QueueFullException(String message) {
            super(message);
        }
    }

    static class InvalidDeliveryException extends QueueException {
        InvalidDeliveryException(String message) {
            super(message);
        }
    }

    static class StaleDeliveryException extends InvalidDeliveryException {
        StaleDeliveryException(String message) {
            super(message);
        }
    }

    static final class MessageRecord {
        private final String id;
        private final String payload;
        private final long createdAtNanos;

        private MessageState state = MessageState.READY;
        private int attempts;
        private String consumerId;
        private String receipt;
        private long leaseDeadlineNanos;
        private String lastError;

        MessageRecord(String id, String payload) {
            this.id = id;
            this.payload = payload;
            this.createdAtNanos = System.nanoTime();
        }
    }

    /**
     * A thread-safe point-to-point queue.
     *
     * The queue stores one logical message and creates a new receipt for
     * each delivery attempt. Consumers must use the current receipt to settle.
     */
    static final class QueueService implements AutoCloseable {
        private final QueuePolicy policy;

        private final ReentrantLock lock = new ReentrantLock();
        private final Condition changed = lock.newCondition();

        private final Map<String, MessageRecord> messages =
            new LinkedHashMap<>();

        private final ArrayDeque<String> ready = new ArrayDeque<>();
        private final List<DeadLetter> deadLetters = new ArrayList<>();

        private boolean closed;
        private long receiptSequence;

        QueueService(QueuePolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        void publish(String messageId, String payload) {
            if (
                messageId == null ||
                messageId.isBlank() ||
                payload == null ||
                payload.isBlank()
            ) {
                throw new IllegalArgumentException(
                    "Message identifier and payload are required."
                );
            }

            if (payload.length() > 1_000_000) {
                throw new IllegalArgumentException(
                    "Payload exceeds the configured size limit."
                );
            }

            lock.lock();

            try {
                if (closed) {
                    throw new QueueException("Queue is closed.");
                }

                recoverExpiredLocked(System.nanoTime());

                if (messages.containsKey(messageId)) {
                    throw new QueueException(
                        "Duplicate message identifier: " + messageId
                    );
                }

                if (outstandingLocked() >= policy.capacity()) {
                    throw new QueueFullException("Queue capacity reached.");
                }

                MessageRecord message = new MessageRecord(
                    messageId,
                    payload
                );

                messages.put(messageId, message);
                ready.addLast(messageId);
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }

        Optional<Delivery> receive(
            String consumerId,
            Duration maximumWait
        ) throws InterruptedException {
            if (consumerId == null || consumerId.isBlank()) {
                throw new IllegalArgumentException(
                    "Consumer identifier is required."
                );
            }

            Objects.requireNonNull(maximumWait);

            if (maximumWait.isNegative()) {
                throw new IllegalArgumentException(
                    "Maximum wait cannot be negative."
                );
            }

            long remaining = maximumWait.toNanos();

            lock.lockInterruptibly();

            try {
                while (true) {
                    long now = System.nanoTime();
                    recoverExpiredLocked(now);

                    while (!ready.isEmpty()) {
                        String id = ready.removeFirst();
                        MessageRecord message = messages.get(id);

                        if (
                            message == null ||
                            message.state != MessageState.READY
                        ) {
                            continue;
                        }

                        message.state = MessageState.IN_FLIGHT;
                        message.attempts++;
                        message.consumerId = consumerId;
                        message.receipt = nextReceipt(message.id);
                        message.leaseDeadlineNanos =
                            now + policy.visibilityTimeout().toNanos();

                        return Optional.of(
                            new Delivery(
                                message.id,
                                message.payload,
                                consumerId,
                                message.receipt,
                                message.attempts,
                                message.leaseDeadlineNanos
                            )
                        );
                    }

                    if (closed && outstandingLocked() == 0) {
                        return Optional.empty();
                    }

                    if (remaining <= 0) {
                        return Optional.empty();
                    }

                    long waitTime = Math.min(
                        remaining,
                        timeUntilNextLease(now)
                    );

                    long beforeWait = System.nanoTime();
                    changed.awaitNanos(Math.max(1L, waitTime));
                    long elapsed = System.nanoTime() - beforeWait;

                    remaining = Math.max(0L, remaining - elapsed);
                }
            } finally {
                lock.unlock();
            }
        }

        private String nextReceipt(String messageId) {
            return messageId + ":" + UUID.randomUUID() + ":"
                + (++receiptSequence);
        }

        private long timeUntilNextLease(long now) {
            long next = Long.MAX_VALUE;

            for (MessageRecord message : messages.values()) {
                if (
                    message.state == MessageState.IN_FLIGHT &&
                    message.leaseDeadlineNanos < next
                ) {
                    next = message.leaseDeadlineNanos;
                }
            }

            if (next == Long.MAX_VALUE) {
                return Duration.ofMillis(100).toNanos();
            }

            return Math.max(1L, next - now);
        }

        private int outstandingLocked() {
            int count = 0;

            for (MessageRecord message : messages.values()) {
                if (
                    message.state == MessageState.READY ||
                    message.state == MessageState.IN_FLIGHT
                ) {
                    count++;
                }
            }

            return count;
        }

        private MessageRecord activeMessageLocked(Delivery delivery) {
            Objects.requireNonNull(delivery);

            MessageRecord message = messages.get(delivery.messageId());

            if (message == null) {
                throw new InvalidDeliveryException("Unknown message.");
            }

            if (message.state == MessageState.ACKNOWLEDGED) {
                throw new InvalidDeliveryException(
                    "Message is already acknowledged."
                );
            }

            if (message.state != MessageState.IN_FLIGHT) {
                throw new StaleDeliveryException(
                    "Message is not in flight."
                );
            }

            if (
                !Objects.equals(message.receipt, delivery.receipt()) ||
                !Objects.equals(message.consumerId, delivery.consumerId())
            ) {
                throw new StaleDeliveryException(
                    "Receipt does not match the active delivery."
                );
            }

            if (System.nanoTime() >= message.leaseDeadlineNanos) {
                recoverExpiredLocked(System.nanoTime());
                throw new StaleDeliveryException(
                    "Delivery lease has expired."
                );
            }

            return message;
        }

        void acknowledge(Delivery delivery) {
            lock.lock();

            try {
                MessageRecord message = activeMessageLocked(delivery);

                message.state = MessageState.ACKNOWLEDGED;
                clearLease(message);

                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }

        Settlement reject(
            Delivery delivery,
            boolean requeue,
            String reason
        ) {
            lock.lock();

            try {
                MessageRecord message = activeMessageLocked(delivery);

                message.lastError = (
                    reason == null || reason.isBlank()
                ) ? "Consumer rejected the message." : reason;

                clearLease(message);

                if (requeue && message.attempts < policy.maximumAttempts()) {
                    message.state = MessageState.READY;
                    ready.addLast(message.id);
                    changed.signalAll();
                    return Settlement.REQUEUED;
                }

                message.state = MessageState.DEAD_LETTERED;
                deadLetters.add(
                    new DeadLetter(
                        message.id,
                        message.payload,
                        message.attempts,
                        message.lastError
                    )
                );

                changed.signalAll();
                return Settlement.DEAD_LETTERED;
            } finally {
                lock.unlock();
            }
        }

        private void clearLease(MessageRecord message) {
            message.consumerId = null;
            message.receipt = null;
            message.leaseDeadlineNanos = 0;
        }

        /**
         * Recovers abandoned deliveries. A message is redelivered until
         * its maximum delivery-attempt count has been reached.
         */
        private void recoverExpiredLocked(long now) {
            for (MessageRecord message : messages.values()) {
                if (
                    message.state != MessageState.IN_FLIGHT ||
                    message.leaseDeadlineNanos > now
                ) {
                    continue;
                }

                clearLease(message);
                message.lastError = "Visibility timeout expired.";

                if (message.attempts >= policy.maximumAttempts()) {
                    message.state = MessageState.DEAD_LETTERED;

                    deadLetters.add(
                        new DeadLetter(
                            message.id,
                            message.payload,
                            message.attempts,
                            message.lastError
                        )
                    );
                } else {
                    message.state = MessageState.READY;
                    ready.addLast(message.id);
                }
            }

            changed.signalAll();
        }

        QueueMetrics metrics() {
            lock.lock();

            try {
                int readyCount = 0;
                int inFlightCount = 0;
                int acknowledgedCount = 0;
                int deadCount = 0;

                for (MessageRecord message : messages.values()) {
                    switch (message.state) {
                        case READY -> readyCount++;
                        case IN_FLIGHT -> inFlightCount++;
                        case ACKNOWLEDGED -> acknowledgedCount++;
                        case DEAD_LETTERED -> deadCount++;
                    }
                }

                return new QueueMetrics(
                    readyCount,
                    inFlightCount,
                    acknowledgedCount,
                    deadCount
                );
            } finally {
                lock.unlock();
            }
        }

        List<DeadLetter> deadLetterMessages() {
            lock.lock();

            try {
                return List.copyOf(deadLetters);
            } finally {
                lock.unlock();
            }
        }

        @Override
        public void close() {
            lock.lock();

            try {
                closed = true;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    @FunctionalInterface
    interface MessageHandler {
        void process(Delivery delivery) throws Exception;
    }

    /**
     * A worker repeatedly pulls one message at a time from the shared queue.
     * No worker owns a permanent partition of the message set.
     */
    static final class ConsumerWorker implements Runnable {
        private final QueueService queue;
        private final String consumerId;
        private final MessageHandler handler;

        ConsumerWorker(
            QueueService queue,
            String consumerId,
            MessageHandler handler
        ) {
            this.queue = Objects.requireNonNull(queue);
            this.consumerId = Objects.requireNonNull(consumerId);
            this.handler = Objects.requireNonNull(handler);
        }

        @Override
        public void run() {
            while (!Thread.currentThread().isInterrupted()) {
                Optional<Delivery> received;

                try {
                    received = queue.receive(
                        consumerId,
                        Duration.ofSeconds(2)
                    );
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    return;
                } catch (RuntimeException exception) {
                    System.err.println(
                        consumerId + " receive error: " + exception.getMessage()
                    );
                    return;
                }

                if (received.isEmpty()) {
                    return;
                }

                Delivery delivery = received.get();

                try {
                    handler.process(delivery);
                    queue.acknowledge(delivery);
                } catch (Exception exception) {
                    Settlement settlement = queue.reject(
                        delivery,
                        true,
                        exception.getMessage()
                    );

                    System.out.println(
                        consumerId + " rejected " + delivery.messageId()
                            + " on attempt " + delivery.attempt()
                            + "; settlement=" + settlement
                    );
                }
            }
        }
    }

    static final class IdempotencyRegistry {
        private final Set<String> completed =
            ConcurrentHashMap.newKeySet();

        boolean recordIfNew(String messageId) {
            return completed.add(messageId);
        }
    }

    static void runDemonstration() throws InterruptedException {
        QueuePolicy policy = new QueuePolicy(
            20,
            3,
            Duration.ofSeconds(5)
        );

        QueueService queue = new QueueService(policy);
        IdempotencyRegistry idempotency = new IdempotencyRegistry();

        queue.publish("shipment-101", "DELIVER:SHIP-101");
        queue.publish("shipment-102", "DELIVER:SHIP-102");
        queue.publish("shipment-103", "DELIVER:SHIP-103");
        queue.publish("shipment-104", "DELIVER:SHIP-104");
        queue.publish("shipment-105", "POISON");
        queue.publish("shipment-106", "DELIVER:SHIP-106");

        MessageHandler handler = delivery -> {
            if (delivery.payload().equals("POISON")) {
                throw new IllegalArgumentException(
                    "Shipment failed destination validation."
                );
            }

            if (idempotency.recordIfNew(delivery.messageId())) {
                System.out.println(
                    delivery.consumerId()
                        + " processed " + delivery.messageId()
                        + " on attempt " + delivery.attempt()
                );
            } else {
                System.out.println(
                    delivery.consumerId()
                        + " skipped duplicate operation for "
                        + delivery.messageId()
                );
            }

            // Represents bounded downstream processing time.
            Thread.sleep(10);
        };

        ExecutorService executor = Executors.newFixedThreadPool(3);

        try {
            for (int index = 1; index <= 3; index++) {
                executor.submit(
                    new ConsumerWorker(
                        queue,
                        "worker-" + index,
                        handler
                    )
                );
            }

            queue.close();

            executor.shutdown();

            if (!executor.awaitTermination(15, TimeUnit.SECONDS)) {
                executor.shutdownNow();

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Consumer workers did not terminate."
                    );
                }
            }
        } finally {
            queue.close();
            if (!executor.isTerminated()) {
                executor.shutdownNow();
            }
        }

        QueueMetrics metrics = queue.metrics();

        System.out.println("\nQueue metrics");
        System.out.println("Ready:         " + metrics.ready());
        System.out.println("In flight:     " + metrics.inFlight());
        System.out.println("Acknowledged:  " + metrics.acknowledged());
        System.out.println("Dead-lettered: " + metrics.deadLettered());

        System.out.println("\nDead-letter messages");
        for (DeadLetter deadLetter : queue.deadLetterMessages()) {
            System.out.println(deadLetter);
        }

        if (metrics.ready() != 0 || metrics.inFlight() != 0) {
            throw new IllegalStateException("Queue did not drain.");
        }
    }

    static void runAssertions() throws InterruptedException {
        QueueService queue = new QueueService(
            new QueuePolicy(
                1,
                2,
                Duration.ofMillis(40)
            )
        );

        queue.publish("test-1", "RECONCILE");

        try {
            queue.publish("test-2", "OVERFLOW");
            throw new IllegalStateException(
                "Capacity restriction failed."
            );
        } catch (QueueFullException expected) {
            // Expected capacity failure.
        }

        Delivery first = queue.receive(
            "worker-old",
            Duration.ofSeconds(1)
        ).orElseThrow();

        Thread.sleep(70);

        Delivery second = queue.receive(
            "worker-new",
            Duration.ofSeconds(1)
        ).orElseThrow();

        if (second.attempt() != 2) {
            throw new IllegalStateException(
                "Visibility-timeout recovery failed."
            );
        }

        try {
            queue.acknowledge(first);
            throw new IllegalStateException(
                "Stale receipt was incorrectly accepted."
            );
        } catch (StaleDeliveryException expected) {
            // The previous receipt cannot settle the new delivery.
        }

        Settlement settlement = queue.reject(
            second,
            true,
            "Repeated processing failure."
        );

        if (settlement != Settlement.DEAD_LETTERED) {
            throw new IllegalStateException(
                "Maximum-attempt policy failed."
            );
        }

        QueueMetrics metrics = queue.metrics();

        if (metrics.deadLettered() != 1) {
            throw new IllegalStateException(
                "Expected one dead-letter message."
            );
        }

        queue.close();
    }

    public static void main(String[] args) {
        try {
            runAssertions();
            runDemonstration();
        } catch (Exception exception) {
            System.err.println(
                "Queue demonstration failed: " + exception.getMessage()
            );
            exception.printStackTrace();
            System.exit(1);
        }
    }
}
