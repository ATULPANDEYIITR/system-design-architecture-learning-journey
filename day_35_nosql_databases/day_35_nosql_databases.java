import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

/**
 * NoSQL Database Enterprise Case Study.
 *
 * Java-specific design:
 * - records model immutable domain values;
 * - sealed interfaces separate document and graph concepts;
 * - enums model explicit event and relationship types;
 * - services encapsulate business rules;
 * - collections represent indexes and adjacency lists;
 * - checked domain exceptions make invalid states visible.
 */
public class NoSqlDatabaseEnterpriseDemo {

    // -------------------------------------------------------------------------
    // Domain exceptions
    // -------------------------------------------------------------------------

    static class DomainValidationException extends Exception {
        DomainValidationException(String message) {
            super(message);
        }
    }

    // -------------------------------------------------------------------------
    // Key-value service
    // -------------------------------------------------------------------------

    static final class KeyValueService {
        private final Map<String, Object> values = new HashMap<>();
        private final Map<String, Long> expirationEpochMillis = new HashMap<>();

        public void put(String key, Object value, long ttlMillis)
                throws DomainValidationException {

            if (key == null || key.isBlank()) {
                throw new DomainValidationException(
                        "Key must not be blank"
                );
            }

            if (ttlMillis < 0) {
                throw new DomainValidationException(
                        "TTL cannot be negative"
                );
            }

            values.put(key, value);

            if (ttlMillis == 0) {
                expirationEpochMillis.remove(key);
            } else {
                expirationEpochMillis.put(
                        key,
                        System.currentTimeMillis() + ttlMillis
                );
            }
        }

        public Optional<Object> get(String key) {
            if (!values.containsKey(key)) {
                return Optional.empty();
            }

            Long expiresAt = expirationEpochMillis.get(key);

            if (expiresAt != null &&
                    System.currentTimeMillis() >= expiresAt) {
                values.remove(key);
                expirationEpochMillis.remove(key);
                return Optional.empty();
            }

            return Optional.ofNullable(values.get(key));
        }

        public long increment(String key, long amount)
                throws DomainValidationException {

            Object current = get(key).orElse(0L);

            if (!(current instanceof Number number)) {
                throw new DomainValidationException(
                        "Counter key does not contain a numeric value"
                );
            }

            long updated = number.longValue() + amount;
            put(key, updated, 0);
            return updated;
        }

        public boolean compareAndSet(
                String key,
                Object expected,
                Object replacement
        ) throws DomainValidationException {

            Object current = get(key).orElse(null);

            if (!Objects.equals(current, expected)) {
                return false;
            }

            put(key, replacement, 0);
            return true;
        }
    }

    // -------------------------------------------------------------------------
    // Document database
    // -------------------------------------------------------------------------

    enum ProductCategory {
        ELECTRONICS,
        OFFICE,
        SOFTWARE
    }

    record Inventory(Map<String, Integer> quantities) {
        Inventory {
            quantities = Map.copyOf(quantities);

            if (quantities.values().stream().anyMatch(value -> value < 0)) {
                throw new IllegalArgumentException(
                        "Inventory quantities cannot be negative"
                );
            }
        }
    }

    record ProductDocument(
            String id,
            String name,
            ProductCategory category,
            double price,
            List<String> tags,
            Inventory inventory
    ) {
        ProductDocument {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Product ID is required");
            }

            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Product name is required");
            }

            if (price < 0) {
                throw new IllegalArgumentException(
                        "Product price cannot be negative"
                );
            }

            tags = List.copyOf(tags);
        }
    }

    static final class ProductCatalog {
        private final Map<String, ProductDocument> documents =
                new LinkedHashMap<>();

        private final Map<ProductCategory, Set<String>> categoryIndex =
                new HashMap<>();

        public void insert(ProductDocument product)
                throws DomainValidationException {

            if (documents.containsKey(product.id())) {
                throw new DomainValidationException(
                        "Duplicate document ID: " + product.id()
                );
            }

            documents.put(product.id(), product);

            categoryIndex
                    .computeIfAbsent(
                            product.category(),
                            ignored -> new HashSet<>()
                    )
                    .add(product.id());
        }

        public List<ProductDocument> byCategory(
                ProductCategory category
        ) {
            return categoryIndex
                    .getOrDefault(category, Set.of())
                    .stream()
                    .map(documents::get)
                    .filter(Objects::nonNull)
                    .toList();
        }

        public List<ProductDocument> underPrice(double maximum) {
            return documents.values()
                    .stream()
                    .filter(product -> product.price() < maximum)
                    .toList();
        }

        public ProductDocument updateInventory(
                String productId,
                String warehouse,
                int quantity
        ) throws DomainValidationException {

            if (quantity < 0) {
                throw new DomainValidationException(
                        "Inventory cannot be negative"
                );
            }

            ProductDocument current = documents.get(productId);

            if (current == null) {
                throw new DomainValidationException(
                        "Unknown product: " + productId
                );
            }

            Map<String, Integer> updatedQuantities =
                    new HashMap<>(current.inventory().quantities());

            updatedQuantities.put(warehouse, quantity);

            ProductDocument replacement = new ProductDocument(
                    current.id(),
                    current.name(),
                    current.category(),
                    current.price(),
                    current.tags(),
                    new Inventory(updatedQuantities)
            );

            documents.put(productId, replacement);
            return replacement;
        }
    }

    // -------------------------------------------------------------------------
    // Column-family database
    // -------------------------------------------------------------------------

    record ActivityRow(
            String rowKey,
            Map<String, String> columns
    ) {
        ActivityRow {
            columns = Map.copyOf(columns);
        }
    }

    static final class ActivityWideTable {
        private final Map<String, Map<String, ActivityRow>> families =
                new HashMap<>();

        public void upsert(
                String family,
                String rowKey,
                Map<String, String> columns
        ) throws DomainValidationException {

            if (family.isBlank() || rowKey.isBlank()) {
                throw new DomainValidationException(
                        "Family and row key are required"
                );
            }

            Map<String, ActivityRow> rows =
                    families.computeIfAbsent(
                            family,
                            ignored -> new LinkedHashMap<>()
                    );

            ActivityRow current = rows.get(rowKey);

            Map<String, String> merged = new LinkedHashMap<>();

            if (current != null) {
                merged.putAll(current.columns());
            }

            merged.putAll(columns);

            rows.put(
                    rowKey,
                    new ActivityRow(rowKey, merged)
            );
        }

        public List<ActivityRow> byPartition(
                String family,
                String partitionPrefix
        ) {
            Map<String, ActivityRow> rows =
                    families.getOrDefault(family, Map.of());

            return rows.entrySet()
                    .stream()
                    .filter(entry ->
                            entry.getKey().startsWith(partitionPrefix))
                    .sorted(Map.Entry.comparingByKey())
                    .map(Map.Entry::getValue)
                    .toList();
        }
    }

    // -------------------------------------------------------------------------
    // Graph database
    // -------------------------------------------------------------------------

    enum Relationship {
        PURCHASED,
        FOLLOWS,
        VIEWED
    }

    record GraphNode(
            String id,
            String label,
            Map<String, String> properties
    ) {
        GraphNode {
            properties = Map.copyOf(properties);
        }
    }

    record GraphEdge(
            String source,
            Relationship relationship,
            String target
    ) {}

    static final class ProductGraph {
        private final Map<String, GraphNode> nodes =
                new LinkedHashMap<>();

        private final Map<String, List<GraphEdge>> adjacency =
                new HashMap<>();

        public void addNode(
                String id,
                String label,
                Map<String, String> properties
        ) throws DomainValidationException {

            if (nodes.containsKey(id)) {
                throw new DomainValidationException(
                        "Duplicate node: " + id
                );
            }

            nodes.put(
                    id,
                    new GraphNode(id, label, properties)
            );

            adjacency.put(id, new ArrayList<>());
        }

        public void addEdge(
                String source,
                Relationship relationship,
                String target
        ) throws DomainValidationException {

            if (!nodes.containsKey(source) ||
                    !nodes.containsKey(target)) {
                throw new DomainValidationException(
                        "Graph endpoints must exist"
                );
            }

            adjacency
                    .get(source)
                    .add(new GraphEdge(
                            source,
                            relationship,
                            target
                    ));
        }

        public List<String> neighbors(
                String source,
                Relationship relationship
        ) {
            return adjacency
                    .getOrDefault(source, List.of())
                    .stream()
                    .filter(edge -> edge.relationship() == relationship)
                    .map(GraphEdge::target)
                    .toList();
        }

        public Optional<List<String>> shortestPath(
                String source,
                String target
        ) {
            if (!nodes.containsKey(source) ||
                    !nodes.containsKey(target)) {
                return Optional.empty();
            }

            Deque<String> queue = new ArrayDeque<>();
            Map<String, String> parent = new HashMap<>();
            Set<String> visited = new HashSet<>();

            queue.add(source);
            visited.add(source);

            while (!queue.isEmpty()) {
                String current = queue.removeFirst();

                if (current.equals(target)) {
                    break;
                }

                for (GraphEdge edge :
                        adjacency.getOrDefault(current, List.of())) {

                    String next = edge.target();

                    if (visited.add(next)) {
                        parent.put(next, current);
                        queue.addLast(next);
                    }
                }
            }

            if (!visited.contains(target)) {
                return Optional.empty();
            }

            List<String> path = new ArrayList<>();
            String current = target;

            while (current != null) {
                path.add(current);

                if (current.equals(source)) {
                    break;
                }

                current = parent.get(current);
            }

            Collections.reverse(path);
            return Optional.of(path);
        }

        public Set<String> recommendProducts(String userId) {
            Set<String> purchased = new HashSet<>(
                    neighbors(userId, Relationship.PURCHASED)
            );

            Set<String> similarUsers = new HashSet<>();

            for (Map.Entry<String, List<GraphEdge>> entry :
                    adjacency.entrySet()) {

                String candidateUser = entry.getKey();

                if (candidateUser.equals(userId)) {
                    continue;
                }

                boolean sharesPurchase =
                        entry.getValue()
                                .stream()
                                .anyMatch(edge ->
                                        edge.relationship()
                                                == Relationship.PURCHASED
                                                && purchased.contains(
                                                        edge.target()
                                                ));

                if (sharesPurchase) {
                    similarUsers.add(candidateUser);
                }
            }

            Set<String> recommendations = new HashSet<>();

            for (String similarUser : similarUsers) {
                for (String product :
                        neighbors(
                                similarUser,
                                Relationship.PURCHASED
                        )) {
                    if (!purchased.contains(product)) {
                        recommendations.add(product);
                    }
                }
            }

            return recommendations;
        }
    }

    // -------------------------------------------------------------------------
    // Enterprise audit service
    // -------------------------------------------------------------------------

    record AuditEvent(
            String eventId,
            Instant timestamp,
            String eventType,
            Map<String, String> attributes
    ) {
        AuditEvent {
            attributes = Map.copyOf(attributes);
        }
    }

    static final class AuditService {
        private final List<AuditEvent> events = new ArrayList<>();

        public void record(
                String eventType,
                Map<String, String> attributes
        ) {
            events.add(
                    new AuditEvent(
                            UUID.randomUUID().toString(),
                            Instant.now(),
                            eventType,
                            attributes
                    )
            );
        }

        public List<AuditEvent> events() {
            return List.copyOf(events);
        }
    }

    // -------------------------------------------------------------------------
    // Demonstrations
    // -------------------------------------------------------------------------

    private static void heading(String title) {
        System.out.println();
        System.out.println("=".repeat(78));
        System.out.println(title);
        System.out.println("=".repeat(78));
    }

    private static void demonstrateKeyValue()
            throws DomainValidationException {

        heading("Key-Value Store");

        KeyValueService cache = new KeyValueService();

        cache.put(
                "session:u-501",
                Map.of(
                        "role", "customer",
                        "cartId", "cart-901"
                ),
                60_000
        );

        cache.put("login-attempts:u-501", 0L, 0);

        cache.increment("login-attempts:u-501", 1);
        cache.increment("login-attempts:u-501", 2);

        System.out.println(
                "Session: " + cache.get("session:u-501").orElse("MISS")
        );

        System.out.println(
                "Login attempts: "
                        + cache.get("login-attempts:u-501").orElse("MISS")
        );

        boolean changed = cache.compareAndSet(
                "feature:recommendations",
                null,
                Boolean.TRUE
        );

        System.out.println(
                "Conditional feature initialization: " + changed
        );
    }

    private static void demonstrateDocuments()
            throws DomainValidationException {

        heading("Document Store");

        ProductCatalog catalog = new ProductCatalog();

        catalog.insert(
                new ProductDocument(
                        "p-100",
                        "Mechanical Keyboard",
                        ProductCategory.ELECTRONICS,
                        89.0,
                        List.of("keyboard", "office"),
                        new Inventory(
                                Map.of(
                                        "warehouseA", 20,
                                        "warehouseB", 12
                                )
                        )
                )
        );

        catalog.insert(
                new ProductDocument(
                        "p-101",
                        "Wireless Mouse",
                        ProductCategory.ELECTRONICS,
                        39.0,
                        List.of("mouse", "wireless"),
                        new Inventory(
                                Map.of(
                                        "warehouseA", 35,
                                        "warehouseB", 18
                                )
                        )
                )
        );

        catalog.insert(
                new ProductDocument(
                        "p-102",
                        "USB-C Dock",
                        ProductCategory.ELECTRONICS,
                        129.0,
                        List.of("dock", "usb-c"),
                        new Inventory(
                                Map.of(
                                        "warehouseA", 7,
                                        "warehouseB", 10
                                )
                        )
                )
        );

        System.out.println("Electronics:");

        catalog.byCategory(ProductCategory.ELECTRONICS)
                .forEach(System.out::println);

        System.out.println("\nProducts below $100:");

        catalog.underPrice(100)
                .forEach(System.out::println);

        ProductDocument updated =
                catalog.updateInventory(
                        "p-100",
                        "warehouseA",
                        18
                );

        System.out.println("\nUpdated aggregate:");
        System.out.println(updated);

        try {
            catalog.insert(
                    new ProductDocument(
                            "p-invalid",
                            "Invalid",
                            ProductCategory.ELECTRONICS,
                            -5,
                            List.of(),
                            new Inventory(Map.of())
                    )
            );
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Document validation rejected invalid state: "
                            + ex.getMessage()
            );
        }
    }

    private static void demonstrateColumnFamily()
            throws DomainValidationException {

        heading("Column-Family Store");

        ActivityWideTable table = new ActivityWideTable();

        String family = "activity_by_user_day";

        table.upsert(
                family,
                "u-501|2026-10-05|00:01:00",
                Map.of(
                        "eventType", "login",
                        "channel", "mobile"
                )
        );

        table.upsert(
                family,
                "u-501|2026-10-05|00:05:00",
                Map.of(
                        "eventType", "view",
                        "channel", "mobile"
                )
        );

        table.upsert(
                family,
                "u-501|2026-10-05|00:09:00",
                Map.of(
                        "eventType", "purchase",
                        "channel", "web"
                )
        );

        table.upsert(
                family,
                "u-502|2026-10-05|00:03:00",
                Map.of(
                        "eventType", "login",
                        "channel", "web"
                )
        );

        System.out.println(
                "Rows for user u-501 on 2026-10-05:"
        );

        table.byPartition(
                        family,
                        "u-501|2026-10-05|"
                )
                .forEach(System.out::println);
    }

    private static void demonstrateGraph()
            throws DomainValidationException {

        heading("Graph Store");

        ProductGraph graph = new ProductGraph();

        graph.addNode(
                "u-501",
                "User",
                Map.of("name", "Asha")
        );

        graph.addNode(
                "u-502",
                "User",
                Map.of("name", "Rahul")
        );

        graph.addNode(
                "u-503",
                "User",
                Map.of("name", "Meera")
        );

        graph.addNode(
                "p-100",
                "Product",
                Map.of("name", "Keyboard")
        );

        graph.addNode(
                "p-101",
                "Product",
                Map.of("name", "Mouse")
        );

        graph.addNode(
                "p-102",
                "Product",
                Map.of("name", "USB-C Dock")
        );

        graph.addEdge(
                "u-501",
                Relationship.PURCHASED,
                "p-100"
        );

        graph.addEdge(
                "u-501",
                Relationship.PURCHASED,
                "p-101"
        );

        graph.addEdge(
                "u-502",
                Relationship.PURCHASED,
                "p-100"
        );

        graph.addEdge(
                "u-502",
                Relationship.PURCHASED,
                "p-102"
        );

        graph.addEdge(
                "u-503",
                Relationship.PURCHASED,
                "p-102"
        );

        System.out.println(
                "Recommendations: "
                        + graph.recommendProducts("u-501")
        );

        System.out.println(
                "Shortest path: "
                        + graph.shortestPath(
                                "u-501",
                                "p-102"
                        ).orElse(List.of())
        );
    }

    private static void demonstrateAudit() {
        heading("Enterprise Audit Layer");

        AuditService audit = new AuditService();

        audit.record(
                "document.updated",
                Map.of(
                        "documentId", "p-100",
                        "field", "price",
                        "actor", "catalog-service"
                )
        );

        audit.record(
                "cache.invalidated",
                Map.of(
                        "key", "product:p-100",
                        "reason", "catalog-update"
                )
        );

        audit.events().forEach(System.out::println);
    }

    private static void demonstrateModelSelection() {
        heading("Model Selection by Dominant Access Pattern");

        Map<String, String> workloads = new LinkedHashMap<>();

        workloads.put(
                "session token lookup",
                "Key-value: exact key retrieval"
        );

        workloads.put(
                "variable product catalog",
                "Document: aggregate-oriented records"
        );

        workloads.put(
                "high-volume user activity",
                "Column-family: partition-oriented event reads"
        );

        workloads.put(
                "fraud relationship analysis",
                "Graph: multi-hop traversal"
        );

        workloads.forEach(
                (workload, decision) ->
                        System.out.println(workload + " -> " + decision)
        );
    }

    public static void main(String[] args) {
        try {
            heading("NoSQL Database Enterprise Case Study");

            demonstrateKeyValue();
            demonstrateDocuments();
            demonstrateColumnFamily();
            demonstrateGraph();
            demonstrateAudit();
            demonstrateModelSelection();

            heading("Case Study Complete");

            System.out.println(
                    "Each model is treated as a distinct data architecture "
                            + "chosen for its access pattern, data shape, "
                            + "scaling behavior, and consistency requirements."
            );

        } catch (DomainValidationException ex) {
            System.err.println(
                    "Domain validation failure: " + ex.getMessage()
            );
            System.exit(1);
        }
    }
}
