import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.Set;
import java.util.TreeSet;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/*
 * Enterprise repository-independent database sharding model.
 *
 * This Java 17 program models a tenant-aware order service. Immutable domain
 * records, explicit routing policies, a shard directory, and a migration
 * service keep storage placement separate from business operations.
 *
 * The in-memory store is for demonstrating semantics, not durability or
 * distributed consensus.
 */
public class DatabaseShardingDemo {

    public enum RoutingPolicy {
        HASH,
        RANGE
    }

    public static class ShardingException extends RuntimeException {
        public ShardingException(String message) {
            super(message);
        }
    }

    public static final class Customer {
        private final String customerId;
        private final String region;
        private final String email;

        public Customer(String customerId, String region, String email) {
            this.customerId = requireText(customerId, "customerId");
            this.region = requireText(region, "region");
            this.email = requireText(email, "email");

            if (!email.contains("@")) {
                throw new IllegalArgumentException("Invalid email format");
            }
        }

        public String customerId() {
            return customerId;
        }

        public String region() {
            return region;
        }

        public String email() {
            return email;
        }

        @Override
        public String toString() {
            return "Customer[" + customerId + ", region=" + region + "]";
        }
    }

    public static final class Order {
        private final String orderId;
        private final String customerId;
        private final long amountCents;
        private final Instant createdAt;
        private final String status;

        public Order(
                String orderId,
                String customerId,
                long amountCents,
                Instant createdAt,
                String status) {
            this.orderId = requireText(orderId, "orderId");
            this.customerId = requireText(customerId, "customerId");

            if (amountCents < 0) {
                throw new IllegalArgumentException(
                        "amountCents cannot be negative");
            }

            this.amountCents = amountCents;
            this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
            this.status = requireText(status, "status");
        }

        public String orderId() {
            return orderId;
        }

        public String customerId() {
            return customerId;
        }

        public long amountCents() {
            return amountCents;
        }

        public Instant createdAt() {
            return createdAt;
        }

        public String status() {
            return status;
        }

        @Override
        public String toString() {
            return "Order[" + orderId + ", customer=" + customerId
                    + ", amountCents=" + amountCents + "]";
        }
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " cannot be blank");
        }
        return value;
    }

    public interface ShardRouter {
        String route(String key);
    }

    public static final class HashRouter implements ShardRouter {
        private final NavigableMap<Long, String> ring = new TreeMap<>();
        private final int virtualNodes;

        public HashRouter(Set<String> shardIds, int virtualNodes) {
            if (virtualNodes < 1) {
                throw new IllegalArgumentException(
                        "virtualNodes must be positive");
            }
            this.virtualNodes = virtualNodes;
            rebuild(shardIds);
        }

        public void rebuild(Set<String> shardIds) {
            ring.clear();

            for (String shardId : new TreeSet<>(shardIds)) {
                requireText(shardId, "shardId");

                for (int index = 0; index < virtualNodes; index++) {
                    String nodeKey = shardId + ":virtual:" + index;
                    long position = hash64(nodeKey);

                    // Resolve rare hash collisions deterministically.
                    while (ring.containsKey(position)) {
                        position++;
                    }
                    ring.put(position, shardId);
                }
            }
        }

        @Override
        public String route(String key) {
            requireText(key, "shardKey");

            if (ring.isEmpty()) {
                throw new ShardingException("No shards are available");
            }

            long position = hash64(key);
            Map.Entry<Long, String> entry = ring.ceilingEntry(position);

            return entry == null
                    ? ring.firstEntry().getValue()
                    : entry.getValue();
        }

        private static long hash64(String value) {
            try {
                byte[] digest = MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));

                long result = 0;
                for (int index = 0; index < 8; index++) {
                    result = (result << 8) | (digest[index] & 0xffL);
                }
                return result;
            } catch (NoSuchAlgorithmException exception) {
                throw new IllegalStateException(
                        "SHA-256 is unavailable", exception);
            }
        }
    }

    public static final class RangeRouter implements ShardRouter {
        public record Range(long startInclusive, long endExclusive,
                            String shardId) {
            public Range {
                if (startInclusive >= endExclusive) {
                    throw new IllegalArgumentException(
                            "Range start must precede range end");
                }
                requireText(shardId, "shardId");
            }
        }

        private final List<Range> ranges;

        public RangeRouter(List<Range> configuredRanges) {
            List<Range> sorted = new ArrayList<>(configuredRanges);
            sorted.sort(Comparator.comparingLong(Range::startInclusive));

            for (int index = 1; index < sorted.size(); index++) {
                Range previous = sorted.get(index - 1);
                Range current = sorted.get(index);

                if (current.startInclusive() < previous.endExclusive()) {
                    throw new IllegalArgumentException(
                            "Configured ranges overlap");
                }
            }

            this.ranges = List.copyOf(sorted);
        }

        @Override
        public String route(String key) {
            requireText(key, "shardKey");

            final long value;
            try {
                value = Long.parseLong(key);
            } catch (NumberFormatException exception) {
                throw new IllegalArgumentException(
                        "Range routing requires an integer key", exception);
            }

            return ranges.stream()
                    .filter(range -> value >= range.startInclusive()
                            && value < range.endExclusive())
                    .map(Range::shardId)
                    .findFirst()
                    .orElseThrow(() -> new ShardingException(
                            "No range contains key " + value));
        }
    }

    public static final class Shard {
        private final String shardId;
        private final Map<String, Customer> customers = new HashMap<>();
        private final Map<String, Order> orders = new HashMap<>();
        private boolean available = true;
        private long version;

        public Shard(String shardId) {
            this.shardId = requireText(shardId, "shardId");
        }

        public String shardId() {
            return shardId;
        }

        public boolean available() {
            return available;
        }

        public void setAvailable(boolean available) {
            this.available = available;
        }

        public long version() {
            return version;
        }

        private void ensureAvailable() {
            if (!available) {
                throw new ShardingException(
                        "Shard " + shardId + " is unavailable");
            }
        }

        private void addCustomer(Customer customer) {
            ensureAvailable();
            if (customers.putIfAbsent(customer.customerId(), customer) != null) {
                throw new ShardingException("Duplicate customer");
            }
            version++;
        }

        private void addOrder(Order order) {
            ensureAvailable();
            if (orders.putIfAbsent(order.orderId(), order) != null) {
                throw new ShardingException("Duplicate order");
            }
            version++;
        }
    }

    public static final class ShardDirectory {
        private final Map<String, Shard> shards = new LinkedHashMap<>();
        private final Map<String, String> customerOwners = new HashMap<>();
        private final Map<String, String> orderOwners = new HashMap<>();
        private HashRouter router;
        private long epoch = 1;

        public ShardDirectory(List<String> shardIds) {
            if (shardIds.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one shard is required");
            }

            for (String id : shardIds) {
                if (shards.putIfAbsent(id, new Shard(id)) != null) {
                    throw new IllegalArgumentException(
                            "Duplicate shard identifier: " + id);
                }
            }

            router = new HashRouter(shards.keySet(), 128);
        }

        public synchronized String route(String key) {
            return router.route(key);
        }

        public synchronized Shard shard(String shardId) {
            Shard shard = shards.get(shardId);
            if (shard == null) {
                throw new ShardingException("Unknown shard " + shardId);
            }
            return shard;
        }

        public synchronized void addShard(String shardId) {
            requireText(shardId, "shardId");

            if (shards.containsKey(shardId)) {
                throw new ShardingException("Shard already exists");
            }

            shards.put(shardId, new Shard(shardId));
            router.rebuild(shards.keySet());
            epoch++;
        }

        public synchronized long epoch() {
            return epoch;
        }

        public synchronized List<Shard> allShards() {
            return List.copyOf(shards.values());
        }

        public synchronized void registerCustomer(
                String customerId, String shardId) {
            customerOwners.put(customerId, shardId);
        }

        public synchronized void registerOrder(
                String orderId, String shardId) {
            orderOwners.put(orderId, shardId);
        }

        public synchronized String customerOwner(String customerId) {
            return customerOwners.get(customerId);
        }

        public synchronized String orderOwner(String orderId) {
            return orderOwners.get(orderId);
        }

        public synchronized void updateCustomerOwner(
                String customerId, String shardId) {
            customerOwners.put(customerId, shardId);
            epoch++;
        }

        public synchronized void updateOrderOwner(
                String orderId, String shardId) {
            orderOwners.put(orderId, shardId);
        }

        public synchronized Set<String> shardIds() {
            return Collections.unmodifiableSet(shards.keySet());
        }
    }

    public static final class OrderService {
        private final ShardDirectory directory;

        public OrderService(ShardDirectory directory) {
            this.directory = directory;
        }

        public synchronized String createCustomer(Customer customer) {
            if (directory.customerOwner(customer.customerId()) != null) {
                throw new ShardingException("Customer already exists");
            }

            String shardId = directory.route(customer.customerId());
            directory.shard(shardId).addCustomer(customer);
            directory.registerCustomer(customer.customerId(), shardId);
            return shardId;
        }

        public synchronized String createOrder(Order order) {
            if (directory.orderOwner(order.orderId()) != null) {
                throw new ShardingException("Order already exists");
            }

            String shardId = directory.customerOwner(order.customerId());
            if (shardId == null) {
                throw new ShardingException("Unknown customer");
            }

            Shard shard = directory.shard(shardId);
            shard.ensureAvailable();

            if (!shard.customers.containsKey(order.customerId())) {
                throw new ShardingException(
                        "Customer directory is inconsistent");
            }

            shard.addOrder(order);
            directory.registerOrder(order.orderId(), shardId);
            return shardId;
        }

        public synchronized List<Order> ordersForCustomer(String customerId) {
            String shardId = directory.customerOwner(customerId);
            if (shardId == null) {
                return List.of();
            }

            Shard shard = directory.shard(shardId);
            shard.ensureAvailable();

            return shard.orders.values().stream()
                    .filter(order -> order.customerId().equals(customerId))
                    .sorted(Comparator.comparing(Order::createdAt))
                    .toList();
        }

        public synchronized Optional<Order> getOrder(String orderId) {
            String shardId = directory.orderOwner(orderId);
            if (shardId == null) {
                return Optional.empty();
            }

            Shard shard = directory.shard(shardId);
            shard.ensureAvailable();
            return Optional.ofNullable(shard.orders.get(orderId));
        }

        public synchronized Map<String, Long> revenueByCustomer() {
            Map<String, Long> totals = new TreeMap<>();

            for (Shard shard : directory.allShards()) {
                shard.ensureAvailable();

                for (Order order : shard.orders.values()) {
                    totals.merge(
                            order.customerId(),
                            order.amountCents(),
                            Math::addExact);
                }
            }

            return totals;
        }

        public synchronized int migrateCustomer(
                String customerId, String targetShardId) {
            String sourceShardId = directory.customerOwner(customerId);

            if (sourceShardId == null) {
                throw new ShardingException("Unknown customer");
            }
            if (sourceShardId.equals(targetShardId)) {
                return 0;
            }

            Shard source = directory.shard(sourceShardId);
            Shard target = directory.shard(targetShardId);
            source.ensureAvailable();
            target.ensureAvailable();

            Customer customer = source.customers.get(customerId);
            if (customer == null || target.customers.containsKey(customerId)) {
                throw new ShardingException(
                        "Migration preconditions are not satisfied");
            }

            List<Order> movingOrders = source.orders.values().stream()
                    .filter(order -> order.customerId().equals(customerId))
                    .toList();

            for (Order order : movingOrders) {
                if (target.orders.containsKey(order.orderId())) {
                    throw new ShardingException(
                            "Target already contains " + order.orderId());
                }
            }

            // Stage destination records before switching directory ownership.
            target.customers.put(customerId, customer);
            for (Order order : movingOrders) {
                target.orders.put(order.orderId(), order);
            }

            directory.updateCustomerOwner(customerId, targetShardId);
            for (Order order : movingOrders) {
                directory.updateOrderOwner(order.orderId(), targetShardId);
            }

            source.customers.remove(customerId);
            for (Order order : movingOrders) {
                source.orders.remove(order.orderId());
            }

            source.version++;
            target.version++;
            return movingOrders.size() + 1;
        }

        public synchronized List<String> validateDirectory() {
            List<String> errors = new ArrayList<>();

            for (Shard shard : directory.allShards()) {
                for (String customerId : shard.customers.keySet()) {
                    if (!shard.shardId().equals(
                            directory.customerOwner(customerId))) {
                        errors.add("Incorrect owner for customer " + customerId);
                    }
                }

                for (String orderId : shard.orders.keySet()) {
                    if (!shard.shardId().equals(
                            directory.orderOwner(orderId))) {
                        errors.add("Incorrect owner for order " + orderId);
                    }
                }
            }

            return errors;
        }
    }

    public static void main(String[] args) {
        ShardDirectory directory = new ShardDirectory(
                List.of("orders-east", "orders-central", "orders-west"));
        OrderService service = new OrderService(directory);

        List<Customer> customers = List.of(
                new Customer("cust-100", "north", "a@example.test"),
                new Customer("cust-200", "south", "b@example.test"),
                new Customer("cust-300", "west", "c@example.test"));

        System.out.println("CUSTOMER PLACEMENT");
        for (Customer customer : customers) {
            System.out.println(customer.customerId() + " -> "
                    + service.createCustomer(customer));
        }

        service.createOrder(new Order(
                "ord-001", "cust-100", 1299,
                Instant.parse("2026-10-01T09:00:00Z"), "pending"));
        service.createOrder(new Order(
                "ord-002", "cust-100", 4599,
                Instant.parse("2026-10-02T11:30:00Z"), "paid"));
        service.createOrder(new Order(
                "ord-003", "cust-200", 899,
                Instant.parse("2026-10-03T15:15:00Z"), "paid"));

        System.out.println("\nCUSTOMER-LOCAL QUERY");
        service.ordersForCustomer("cust-100").forEach(System.out::println);

        System.out.println("\nCROSS-SHARD REVENUE");
        System.out.println(service.revenueByCustomer());

        System.out.println("\nDIRECTORY EPOCH");
        System.out.println(directory.epoch());

        System.out.println("\nMIGRATION");
        String target = directory.shardIds().stream()
                .filter(id -> !id.equals(directory.customerOwner("cust-100")))
                .findFirst()
                .orElseThrow();

        System.out.println("Moved records: "
                + service.migrateCustomer("cust-100", target));
        System.out.println("Orders after migration: "
                + service.ordersForCustomer("cust-100").size());

        System.out.println("\nFAILURE HANDLING");
        directory.shard("orders-east").setAvailable(false);
        try {
            service.revenueByCustomer();
        } catch (ShardingException exception) {
            System.out.println("Aggregation rejected: " + exception.getMessage());
        } finally {
            directory.shard("orders-east").setAvailable(true);
        }

        System.out.println("\nVALIDATION");
        List<String> errors = service.validateDirectory();
        if (errors.isEmpty()) {
            System.out.println("Directory ownership matches stored records.");
        } else {
            errors.forEach(System.out::println);
        }

        System.out.println("\nINVALID WRITE");
        try {
            service.createOrder(new Order(
                    "ord-invalid", "cust-missing", -1,
                    Instant.now(), "pending"));
        } catch (IllegalArgumentException | ShardingException exception) {
            System.out.println("Write rejected: " + exception.getMessage());
        }
    }
}
