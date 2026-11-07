import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.stream.Collectors;

/**
 * Service Communication: REST, gRPC, and Messaging.
 *
 * Enterprise scenario:
 * An order-management service coordinates inventory and payment
 * services using resource-oriented HTTP, typed RPC, and events.
 *
 * Java 17, standard library only.
 */
public class ServiceCommunication {

    // ========================================================
    // 1. Domain Exceptions and Enumerations
    // ========================================================

    static class ValidationException extends RuntimeException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class ResourceNotFoundException extends RuntimeException {
        ResourceNotFoundException(String message) {
            super(message);
        }
    }

    static class CommunicationException extends RuntimeException {
        CommunicationException(String message) {
            super(message);
        }
    }

    enum Protocol {
        REST,
        GRPC,
        MESSAGING
    }

    enum RpcStatus {
        OK,
        INVALID_ARGUMENT,
        NOT_FOUND,
        UNAVAILABLE,
        INTERNAL
    }

    enum OrderStatus {
        CREATED,
        INVENTORY_RESERVED,
        PAYMENT_PENDING,
        CONFIRMED,
        FAILED
    }

    enum MessageStatus {
        PENDING,
        ACKNOWLEDGED,
        DEAD_LETTERED
    }

    // ========================================================
    // 2. Immutable Domain Records
    // ========================================================

    record Product(int id, String name, double price) {
        Product {
            if (id <= 0) {
                throw new ValidationException("Invalid product ID");
            }

            if (name == null || name.isBlank() || name.length() > 120) {
                throw new ValidationException("Invalid product name");
            }

            if (!Double.isFinite(price) || price <= 0) {
                throw new ValidationException("Invalid product price");
            }
        }
    }

    record HttpResponse(int statusCode, Map<String, Object> body) {
        HttpResponse {
            body = Collections.unmodifiableMap(
                new HashMap<>(body)
            );
        }
    }

    record GetProductRequest(int productId) {
        GetProductRequest {
            if (productId <= 0) {
                throw new ValidationException("Invalid product ID");
            }
        }
    }

    record RpcResponse(
        RpcStatus status,
        Optional<Product> product,
        String message
    ) {}

    record Message(
        String id,
        String topic,
        String eventType,
        Map<String, Object> payload,
        String correlationId,
        Instant createdAt,
        int attempts
    ) {
        Message {
            if (id == null || id.isBlank() ||
                topic == null || topic.isBlank()) {
                throw new ValidationException("Invalid message identity");
            }

            payload = Collections.unmodifiableMap(
                new HashMap<>(payload)
            );

            Objects.requireNonNull(createdAt);
        }

        Message withAttempts(int value) {
            return new Message(
                id,
                topic,
                eventType,
                payload,
                correlationId,
                createdAt,
                value
            );
        }
    }

    record Delivery(
        Message message,
        MessageStatus status,
        String failure
    ) {}

    // ========================================================
    // 3. Product Repository
    // ========================================================

    interface ProductStore {
        Optional<Product> findById(int id);

        Product save(String name, double price);
    }

    static class InMemoryProductStore implements ProductStore {

        private final Map<Integer, Product> products =
            new HashMap<>();

        private final AtomicInteger sequence =
            new AtomicInteger(102);

        InMemoryProductStore() {
            products.put(
                101,
                new Product(101, "Laptop", 75000)
            );

            products.put(
                102,
                new Product(102, "Monitor", 18000)
            );
        }

        @Override
        public synchronized Optional<Product> findById(int id) {
            return Optional.ofNullable(products.get(id));
        }

        @Override
        public synchronized Product save(String name, double price) {
            int id = sequence.incrementAndGet();

            Product product = new Product(id, name, price);

            products.put(id, product);
            return product;
        }
    }

    // ========================================================
    // 4. REST Resource Controller
    // ========================================================

    static class ProductRestController {

        private final ProductStore store;

        ProductRestController(ProductStore store) {
            this.store = Objects.requireNonNull(store);
        }

        HttpResponse getProduct(int id) {
            if (id <= 0) {
                return new HttpResponse(
                    400,
                    Map.of("error", "Invalid product ID")
                );
            }

            Optional<Product> product = store.findById(id);

            if (product.isEmpty()) {
                return new HttpResponse(
                    404,
                    Map.of("error", "Product not found")
                );
            }

            Product value = product.get();

            return new HttpResponse(
                200,
                Map.of(
                    "id", value.id(),
                    "name", value.name(),
                    "price", value.price()
                )
            );
        }

        HttpResponse createProduct(String name, double price) {
            try {
                Product product = store.save(name, price);

                return new HttpResponse(
                    201,
                    Map.of(
                        "id", product.id(),
                        "name", product.name(),
                        "price", product.price()
                    )
                );

            } catch (ValidationException exception) {
                return new HttpResponse(
                    400,
                    Map.of("error", exception.getMessage())
                );
            }
        }
    }

    // ========================================================
    // 5. Typed RPC Service
    // ========================================================

    interface ProductRpc {
        RpcResponse getProduct(GetProductRequest request);
    }

    static class ProductRpcImplementation implements ProductRpc {

        private final ProductStore store;

        ProductRpcImplementation(ProductStore store) {
            this.store = store;
        }

        @Override
        public RpcResponse getProduct(GetProductRequest request) {
            return store.findById(request.productId())
                .map(product -> new RpcResponse(
                    RpcStatus.OK,
                    Optional.of(product),
                    "Request completed"
                ))
                .orElseGet(() -> new RpcResponse(
                    RpcStatus.NOT_FOUND,
                    Optional.empty(),
                    "Product not found"
                ));
        }
    }

    static class RpcClient {

        private final ProductRpc service;

        RpcClient(ProductRpc service) {
            this.service = service;
        }

        CompletableFuture<RpcResponse> invoke(
            GetProductRequest request,
            long timeout,
            TimeUnit unit
        ) {
            if (timeout <= 0) {
                throw new ValidationException("Invalid RPC timeout");
            }

            return CompletableFuture
                .supplyAsync(() -> service.getProduct(request))
                .orTimeout(timeout, unit)
                .exceptionally(error -> {
                    Throwable cause = error.getCause();

                    if (cause instanceof TimeoutException ||
                        error instanceof TimeoutException) {
                        return new RpcResponse(
                            RpcStatus.UNAVAILABLE,
                            Optional.empty(),
                            "RPC deadline exceeded"
                        );
                    }

                    return new RpcResponse(
                        RpcStatus.INTERNAL,
                        Optional.empty(),
                        "RPC invocation failed"
                    );
                });
        }
    }

    // ========================================================
    // 6. Asynchronous Messaging Broker
    // ========================================================

    static class MessageBroker {

        private final Map<String, Deque<Message>> queues =
            new HashMap<>();

        private final Map<String, List<Consumer<Message>>> handlers =
            new HashMap<>();

        private final Set<String> acknowledged =
            new HashSet<>();

        private final List<Delivery> deadLetters =
            new ArrayList<>();

        private final int maxRetries;

        MessageBroker(int maxRetries) {
            if (maxRetries < 0) {
                throw new ValidationException("Invalid retry count");
            }

            this.maxRetries = maxRetries;
        }

        synchronized void subscribe(
            String topic,
            Consumer<Message> handler
        ) {
            if (topic == null || topic.isBlank()) {
                throw new ValidationException("Invalid topic");
            }

            handlers.computeIfAbsent(
                topic,
                ignored -> new ArrayList<>()
            ).add(Objects.requireNonNull(handler));
        }

        synchronized String publish(
            String topic,
            String eventType,
            Map<String, Object> payload,
            String correlationId
        ) {
            if (topic == null || topic.isBlank() ||
                eventType == null || eventType.isBlank()) {
                throw new ValidationException("Invalid event");
            }

            String id = UUID.randomUUID().toString();

            Message message = new Message(
                id,
                topic,
                eventType,
                payload,
                correlationId,
                Instant.now(),
                0
            );

            queues.computeIfAbsent(
                topic,
                ignored -> new ArrayDeque<>()
            ).addLast(message);

            return id;
        }

        boolean consumeOne(String topic) {
            Message message;
            List<Consumer<Message>> consumers;

            synchronized (this) {
                Deque<Message> queue = queues.get(topic);

                if (queue == null || queue.isEmpty()) {
                    return false;
                }

                consumers = handlers.get(topic);

                if (consumers == null || consumers.isEmpty()) {
                    return false;
                }

                message = queue.removeFirst();

                if (acknowledged.contains(message.id())) {
                    return true;
                }

                consumers = List.copyOf(consumers);
            }

            try {
                for (Consumer<Message> consumer : consumers) {
                    consumer.accept(message);
                }

                synchronized (this) {
                    acknowledged.add(message.id());
                }

                System.out.println("ACK: " + message.id());
                return true;

            } catch (RuntimeException exception) {
                int attempts = message.attempts() + 1;
                Message retried = message.withAttempts(attempts);

                synchronized (this) {
                    if (attempts > maxRetries) {
                        deadLetters.add(new Delivery(
                            retried,
                            MessageStatus.DEAD_LETTERED,
                            exception.getMessage()
                        ));
                    } else {
                        queues.get(topic).addLast(retried);
                    }
                }

                System.err.println(
                    "Message failure: " + exception.getMessage()
                );

                return false;
            }
        }

        int consumeAll(String topic, int limit) {
            if (limit < 0) {
                throw new ValidationException("Invalid limit");
            }

            int count = 0;

            while (count < limit) {
                synchronized (this) {
                    Deque<Message> queue = queues.get(topic);

                    if (queue == null || queue.isEmpty()) {
                        break;
                    }
                }

                if (consumeOne(topic)) {
                    count++;
                } else {
                    break;
                }
            }

            return count;
        }

        synchronized List<Delivery> deadLetterSnapshot() {
            return List.copyOf(deadLetters);
        }
    }

    // ========================================================
    // 7. Idempotent Inventory Consumer
    // ========================================================

    static class InventoryConsumer {

        private final Set<String> processedEvents =
            new HashSet<>();

        private final Map<Integer, Integer> inventory =
            new HashMap<>();

        synchronized void handle(Message message) {
            int productId = (int) message.payload()
                .get("productId");

            int quantity = (int) message.payload()
                .get("quantity");

            if (productId <= 0 || quantity <= 0) {
                throw new ValidationException(
                    "Invalid inventory event"
                );
            }

            if (processedEvents.contains(message.id())) {
                return;
            }

            // Persist both changes atomically in production.
            inventory.merge(productId, quantity, Integer::sum);
            processedEvents.add(message.id());
        }

        synchronized int getQuantity(int productId) {
            return inventory.getOrDefault(productId, 0);
        }
    }

    // ========================================================
    // 8. Transactional Outbox
    // ========================================================

    record OutboxEvent(
        String id,
        String eventType,
        Map<String, Object> payload,
        boolean published
    ) {}

    static class TransactionalOutbox {

        private final List<OutboxEvent> events =
            new ArrayList<>();

        private final Map<Integer, Product> products =
            new HashMap<>();

        synchronized String createProduct(
            int id,
            String name,
            double price
        ) {
            if (products.containsKey(id)) {
                throw new ValidationException("Duplicate product");
            }

            Product product = new Product(id, name, price);
            String eventId = UUID.randomUUID().toString();

            products.put(id, product);

            events.add(new OutboxEvent(
                eventId,
                "ProductCreated",
                Map.of(
                    "productId", id,
                    "name", name,
                    "price", price
                ),
                false
            ));

            return eventId;
        }

        synchronized int dispatch(MessageBroker broker) {
            int count = 0;

            for (int i = 0; i < events.size(); i++) {
                OutboxEvent event = events.get(i);

                if (event.published()) {
                    continue;
                }

                broker.publish(
                    "product.events",
                    event.eventType(),
                    event.payload(),
                    event.id()
                );

                events.set(i, new OutboxEvent(
                    event.id(),
                    event.eventType(),
                    event.payload(),
                    true
                ));

                count++;
            }

            return count;
        }
    }

    // ========================================================
    // 9. Communication Policy
    // ========================================================

    record CommunicationPolicy(
        Protocol protocol,
        boolean authenticated,
        boolean encrypted,
        long timeoutMillis,
        int maxPayloadBytes
    ) {
        void validate() {
            if (!authenticated || !encrypted) {
                throw new SecurityException(
                    "Authenticated encryption required"
                );
            }

            if (timeoutMillis <= 0 || maxPayloadBytes <= 0) {
                throw new ValidationException(
                    "Invalid communication limits"
                );
            }
        }
    }

    // ========================================================
    // 10. Integration Demonstration
    // ========================================================

    public static void main(String[] args) {

        ProductStore store = new InMemoryProductStore();

        System.out.println("=== SERVICE COMMUNICATION ===");

        // REST
        System.out.println("\n--- REST ---");

        ProductRestController rest =
            new ProductRestController(store);

        HttpResponse getResponse = rest.getProduct(101);

        System.out.println(
            "GET: " + getResponse.statusCode() +
            " " + getResponse.body()
        );

        HttpResponse postResponse = rest.createProduct(
            "Keyboard",
            2500
        );

        System.out.println(
            "POST: " + postResponse.statusCode()
        );

        HttpResponse missing = rest.getProduct(999);

        System.out.println(
            "Missing: " + missing.statusCode()
        );

        // gRPC-style typed invocation
        System.out.println("\n--- gRPC ---");

        ProductRpcImplementation rpcService =
            new ProductRpcImplementation(store);

        RpcClient rpcClient = new RpcClient(rpcService);

        RpcResponse rpc = rpcClient.invoke(
            new GetProductRequest(101),
            2,
            TimeUnit.SECONDS
        ).join();

        System.out.println(
            "RPC: " + rpc.status() +
            " " + rpc.product()
        );

        // Messaging
        System.out.println("\n--- MESSAGING ---");

        MessageBroker broker = new MessageBroker(2);
        InventoryConsumer inventory = new InventoryConsumer();

        broker.subscribe(
            "inventory.events",
            inventory::handle
        );

        broker.publish(
            "inventory.events",
            "StockReserved",
            Map.of(
                "productId", 101,
                "quantity", 5
            ),
            "order-5001"
        );

        System.out.println(
            "Consumed: " +
            broker.consumeAll("inventory.events", 10)
        );

        System.out.println(
            "Inventory: " + inventory.getQuantity(101)
        );

        // Transactional outbox
        System.out.println("\n--- OUTBOX ---");

        TransactionalOutbox outbox =
            new TransactionalOutbox();

        outbox.createProduct(
            201,
            "Wireless Mouse",
            1500
        );

        System.out.println(
            "Dispatched: " + outbox.dispatch(broker)
        );

        // Failure handling
        MessageBroker failingBroker = new MessageBroker(1);

        failingBroker.subscribe(
            "payments",
            message -> {
                throw new CommunicationException(
                    "Payment service unavailable"
                );
            }
        );

        failingBroker.publish(
            "payments",
            "PaymentRequested",
            Map.of("orderId", 5001),
            "order-5001"
        );

        failingBroker.consumeOne("payments");
        failingBroker.consumeOne("payments");

        System.out.println(
            "Dead letters: " +
            failingBroker.deadLetterSnapshot().size()
        );

        // Security policy
        System.out.println("\n--- SECURITY ---");

        CommunicationPolicy policy =
            new CommunicationPolicy(
                Protocol.GRPC,
                true,
                true,
                2000,
                16384
            );

        policy.validate();

        System.out.println("Communication policy accepted");

        System.out.println(
            "\nAll Java 17 demonstrations completed."
        );
    }
}
