import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/*
 * Database Partitioning: Enterprise Repository
 *
 * The domain represents an order platform that needs:
 * - horizontal range partitioning for time-local order data
 * - vertical partitioning for customer attributes
 * - list and hash routing for alternative partition strategies
 * - composite partitioning for large-scale access patterns
 *
 * Java-specific design choices:
 * - records provide immutable domain fragments
 * - enums constrain statuses
 * - interfaces isolate partition routing policy
 * - collections model physical partition contents
 * - custom exceptions distinguish routing and integrity failures
 */

public class DatabasePartitioningDemo {

    enum OrderStatus {
        PENDING,
        PAID,
        SHIPPED,
        CANCELLED
    }

    static final class PartitioningException extends RuntimeException {
        PartitioningException(String message) {
            super(message);
        }
    }

    static final class PartitionNotFoundException
            extends PartitioningException {
        PartitionNotFoundException(String message) {
            super(message);
        }
    }

    static final class PartitionIntegrityException
            extends PartitioningException {
        PartitionIntegrityException(String message) {
            super(message);
        }
    }

    record Order(
            long id,
            long customerId,
            LocalDate orderDate,
            String region,
            OrderStatus status,
            double amount) {

        Order {
            if (id <= 0 || customerId <= 0) {
                throw new IllegalArgumentException(
                        "Identifiers must be positive");
            }

            Objects.requireNonNull(orderDate);
            Objects.requireNonNull(region);
            Objects.requireNonNull(status);

            if (amount < 0) {
                throw new IllegalArgumentException(
                        "Order amount cannot be negative");
            }
        }
    }

    record OperationalCustomer(
            long customerId,
            String name,
            String email,
            String phone) {
    }

    record SensitiveCustomer(
            long customerId,
            String address,
            LocalDate dateOfBirth) {
    }

    record FullCustomer(
            OperationalCustomer operational,
            SensitiveCustomer sensitive) {
    }

    interface PartitionRouter<K> {
        String route(K key);
    }

    static final class RangePartition {
        private final String name;
        private final LocalDate start;
        private final LocalDate end;
        private final List<Order> rows = new ArrayList<>();

        RangePartition(
                String name,
                LocalDate start,
                LocalDate end) {

            if (!start.isBefore(end)) {
                throw new IllegalArgumentException(
                        "Range lower bound must precede upper bound");
            }

            this.name = Objects.requireNonNull(name);
            this.start = start;
            this.end = end;
        }

        boolean accepts(LocalDate value) {
            return !value.isBefore(start) && value.isBefore(end);
        }

        void insert(Order order) {
            if (!accepts(order.orderDate())) {
                throw new PartitionIntegrityException(
                        "Order does not belong to " + name);
            }

            rows.add(order);
        }

        String name() {
            return name;
        }

        LocalDate start() {
            return start;
        }

        LocalDate end() {
            return end;
        }

        List<Order> rows() {
            return Collections.unmodifiableList(rows);
        }
    }

    static final class RangePartitionService {

        private final List<RangePartition> partitions;

        RangePartitionService(List<RangePartition> partitions) {
            this.partitions = new ArrayList<>(partitions);
            this.partitions.sort(
                    (left, right) ->
                            left.start().compareTo(right.start()));

            validateNoOverlap();
        }

        private void validateNoOverlap() {
            for (int i = 1; i < partitions.size(); i++) {
                RangePartition previous = partitions.get(i - 1);
                RangePartition current = partitions.get(i);

                if (previous.end().isAfter(current.start())) {
                    throw new PartitionIntegrityException(
                            "Overlapping partitions detected");
                }
            }
        }

        String insert(Order order) {
            return partitions.stream()
                    .filter(partition ->
                            partition.accepts(order.orderDate()))
                    .findFirst()
                    .map(partition -> {
                        partition.insert(order);
                        return partition.name();
                    })
                    .orElseThrow(() ->
                            new PartitionNotFoundException(
                                    "No range partition covers "
                                            + order.orderDate()));
        }

        QueryResult query(
                LocalDate start,
                LocalDate end) {

            if (!start.isBefore(end)) {
                throw new IllegalArgumentException(
                        "Query start must precede query end");
            }

            List<String> scanned = new ArrayList<>();
            List<Order> matches = new ArrayList<>();

            /*
             * Partition pruning occurs before row filtering.
             * A non-overlapping physical partition is not inspected.
             */
            for (RangePartition partition : partitions) {
                boolean overlaps =
                        partition.start().isBefore(end)
                                && start.isBefore(partition.end());

                if (!overlaps) {
                    continue;
                }

                scanned.add(partition.name());

                for (Order order : partition.rows()) {
                    if (!order.orderDate().isBefore(start)
                            && order.orderDate().isBefore(end)) {
                        matches.add(order);
                    }
                }
            }

            return new QueryResult(scanned, matches);
        }
    }

    record QueryResult(
            List<String> scannedPartitions,
            List<Order> rows) {
    }

    static final class RegionPartitionRouter
            implements PartitionRouter<String> {

        private final Map<String, String> partitions;
        private final String defaultPartition;

        RegionPartitionRouter(
                Map<String, String> partitions,
                String defaultPartition) {

            this.partitions = Map.copyOf(partitions);
            this.defaultPartition = defaultPartition;
        }

        @Override
        public String route(String region) {
            return partitions.getOrDefault(
                    region,
                    defaultPartition);
        }
    }

    static final class CustomerHashRouter
            implements PartitionRouter<Long> {

        private final int bucketCount;

        CustomerHashRouter(int bucketCount) {
            if (bucketCount <= 0) {
                throw new IllegalArgumentException(
                        "Bucket count must be positive");
            }

            this.bucketCount = bucketCount;
        }

        @Override
        public String route(Long customerId) {
            int bucket = Math.floorMod(
                    Long.hashCode(customerId),
                    bucketCount);

            return "customer_hash_" + bucket;
        }
    }

    static final class VerticalCustomerRepository {
        private final Map<Long, OperationalCustomer> operational =
                new HashMap<>();

        private final Map<Long, SensitiveCustomer> sensitive =
                new HashMap<>();

        void insert(
                OperationalCustomer operationalCustomer,
                SensitiveCustomer sensitiveCustomer) {

            if (operationalCustomer.customerId()
                    != sensitiveCustomer.customerId()) {
                throw new PartitionIntegrityException(
                        "Vertical fragments must share a customer ID");
            }

            if (operational.containsKey(
                    operationalCustomer.customerId())) {
                throw new PartitionIntegrityException(
                        "Duplicate customer ID");
            }

            operational.put(
                    operationalCustomer.customerId(),
                    operationalCustomer);

            sensitive.put(
                    sensitiveCustomer.customerId(),
                    sensitiveCustomer);
        }

        OperationalCustomer getOperational(long customerId) {
            OperationalCustomer result =
                    operational.get(customerId);

            if (result == null) {
                throw new PartitionNotFoundException(
                        "Customer does not exist");
            }

            return result;
        }

        FullCustomer getFull(long customerId) {
            OperationalCustomer first =
                    getOperational(customerId);

            SensitiveCustomer second =
                    sensitive.get(customerId);

            if (second == null) {
                throw new PartitionIntegrityException(
                        "Missing sensitive vertical fragment");
            }

            return new FullCustomer(first, second);
        }
    }

    static final class CompositePartitionRepository {
        private final CustomerHashRouter hashRouter;
        private final Map<String, List<Order>> partitions =
                new HashMap<>();

        CompositePartitionRepository(int hashBuckets) {
            this.hashRouter =
                    new CustomerHashRouter(hashBuckets);
        }

        private String keyFor(Order order) {
            String month =
                    order.orderDate().toString().substring(0, 7);

            String hashPartition =
                    hashRouter.route(order.customerId());

            return month + ":" + hashPartition;
        }

        String insert(Order order) {
            String key = keyFor(order);

            partitions
                    .computeIfAbsent(key, ignored ->
                            new ArrayList<>())
                    .add(order);

            return key;
        }

        List<Order> findCustomer(
                String month,
                long customerId) {

            String key =
                    month + ":" + hashRouter.route(customerId);

            return partitions
                    .getOrDefault(key, List.of())
                    .stream()
                    .filter(order ->
                            order.customerId() == customerId)
                    .toList();
        }
    }

    private static void horizontalExample() {
        System.out.println(
                "=== Horizontal RANGE Partitioning ===");

        RangePartitionService service =
                new RangePartitionService(
                        List.of(
                                new RangePartition(
                                        "orders_2026_q1",
                                        LocalDate.of(2026, 1, 1),
                                        LocalDate.of(2026, 4, 1)),
                                new RangePartition(
                                        "orders_2026_q2",
                                        LocalDate.of(2026, 4, 1),
                                        LocalDate.of(2026, 7, 1)),
                                new RangePartition(
                                        "orders_2026_q3",
                                        LocalDate.of(2026, 7, 1),
                                        LocalDate.of(2026, 10, 1)),
                                new RangePartition(
                                        "orders_2026_q4",
                                        LocalDate.of(2026, 10, 1),
                                        LocalDate.of(2027, 1, 1))));

        List<Order> orders = List.of(
                new Order(
                        1001,
                        501,
                        LocalDate.of(2026, 2, 15),
                        "NORTH",
                        OrderStatus.PAID,
                        1250.50),
                new Order(
                        1002,
                        502,
                        LocalDate.of(2026, 5, 20),
                        "SOUTH",
                        OrderStatus.SHIPPED,
                        760.00),
                new Order(
                        1003,
                        503,
                        LocalDate.of(2026, 8, 12),
                        "WEST",
                        OrderStatus.PAID,
                        2100.00),
                new Order(
                        1004,
                        504,
                        LocalDate.of(2026, 11, 3),
                        "EAST",
                        OrderStatus.PENDING,
                        450.00));

        for (Order order : orders) {
            System.out.printf(
                    "Order %d -> %s%n",
                    order.id(),
                    service.insert(order));
        }

        QueryResult result =
                service.query(
                        LocalDate.of(2026, 4, 1),
                        LocalDate.of(2026, 10, 1));

        System.out.println(
                "Partitions scanned: "
                        + result.scannedPartitions());

        System.out.println(
                "Matching order IDs: "
                        + result.rows()
                        .stream()
                        .map(Order::id)
                        .toList());
    }

    private static void verticalExample() {
        System.out.println(
                "\n=== Vertical Partitioning ===");

        VerticalCustomerRepository repository =
                new VerticalCustomerRepository();

        repository.insert(
                new OperationalCustomer(
                        501,
                        "Asha Sharma",
                        "asha@example.com",
                        "+91-9000000001"),
                new SensitiveCustomer(
                        501,
                        "Lucknow",
                        LocalDate.of(1992, 3, 14)));

        repository.insert(
                new OperationalCustomer(
                        502,
                        "Rohan Mehta",
                        "rohan@example.com",
                        "+91-9000000002"),
                new SensitiveCustomer(
                        502,
                        "Bengaluru",
                        LocalDate.of(1988, 8, 22)));

        /*
         * The narrow operational lookup avoids loading the sensitive
         * vertical fragment. A full customer request explicitly joins
         * the fragments using the shared primary key.
         */
        System.out.println(
                "Operational: "
                        + repository.getOperational(501));

        System.out.println(
                "Full customer: "
                        + repository.getFull(501));
    }

    private static void routingExamples() {
        System.out.println(
                "\n=== LIST and HASH Partitioning ===");

        RegionPartitionRouter regionRouter =
                new RegionPartitionRouter(
                        Map.of(
                                "NORTH", "orders_north",
                                "SOUTH", "orders_south",
                                "EAST", "orders_east",
                                "WEST", "orders_west"),
                        "orders_other");

        for (String region :
                List.of("NORTH", "WEST", "CENTRAL")) {
            System.out.println(
                    region + " -> "
                            + regionRouter.route(region));
        }

        CustomerHashRouter hashRouter =
                new CustomerHashRouter(4);

        for (long customerId :
                List.of(501L, 502L, 503L, 504L, 505L)) {
            System.out.println(
                    customerId + " -> "
                            + hashRouter.route(customerId));
        }
    }

    private static void compositeExample() {
        System.out.println(
                "\n=== Composite RANGE + HASH Model ===");

        CompositePartitionRepository repository =
                new CompositePartitionRepository(4);

        Order first =
                new Order(
                        3001,
                        701,
                        LocalDate.of(2026, 9, 1),
                        "NORTH",
                        OrderStatus.PAID,
                        100.00);

        Order second =
                new Order(
                        3002,
                        702,
                        LocalDate.of(2026, 9, 4),
                        "NORTH",
                        OrderStatus.PAID,
                        200.00);

        Order third =
                new Order(
                        3003,
                        701,
                        LocalDate.of(2026, 9, 20),
                        "NORTH",
                        OrderStatus.SHIPPED,
                        300.00);

        for (Order order :
                List.of(first, second, third)) {
            System.out.println(
                    "Order "
                            + order.id()
                            + " -> "
                            + repository.insert(order));
        }

        System.out.println(
                "Customer 701 orders: "
                        + repository.findCustomer(
                                "2026-09",
                                701)
                        .stream()
                        .map(Order::id)
                        .toList());
    }

    private static void failureExample() {
        System.out.println(
                "\n=== Partition Boundary Failure ===");

        RangePartitionService service =
                new RangePartitionService(
                        List.of(
                                new RangePartition(
                                        "orders_2026",
                                        LocalDate.of(2026, 1, 1),
                                        LocalDate.of(2027, 1, 1))));

        try {
            service.insert(
                    new Order(
                            9001,
                            900,
                            LocalDate.of(2027, 1, 1),
                            "NORTH",
                            OrderStatus.PENDING,
                            50.00));
        } catch (PartitionNotFoundException exception) {
            System.out.println(
                    "Expected routing failure: "
                            + exception.getMessage());
        }
    }

    public static void main(String[] args) {
        horizontalExample();
        verticalExample();
        routingExamples();
        compositeExample();
        failureExample();

        System.out.println(
                "\nPartitioning model completed successfully.");
    }
}
