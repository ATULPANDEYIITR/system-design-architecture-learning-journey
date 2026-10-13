import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;

/*
 * Consistency Models: Strong, Eventual, and Causal Consistency
 *
 * Compile:
 *   javac ConsistencyModels.java
 *
 * Run:
 *   java ConsistencyModels
 *
 * The domain is an enterprise incident-management service replicated
 * across operational regions.
 */

public class ConsistencyModels {

    enum Model {
        STRONG,
        EVENTUAL,
        CAUSAL
    }

    static class ConsistencyException extends RuntimeException {
        ConsistencyException(String message) {
            super(message);
        }
    }

    static final class AvailabilityException extends ConsistencyException {
        AvailabilityException(String message) {
            super(message);
        }
    }

    static final class MissingDependencyException extends ConsistencyException {
        MissingDependencyException(String message) {
            super(message);
        }
    }

    static final class OperationConflictException extends ConsistencyException {
        OperationConflictException(String message) {
            super(message);
        }
    }

    /**
     * Immutable vector clocks make causal metadata safe to share between
     * operations and client contexts without accidental mutation.
     */
    record VersionVector(Map<String, Long> counters) {
        VersionVector {
            counters = Map.copyOf(new TreeMap<>(counters));
            if (counters.values().stream().anyMatch(value -> value < 0)) {
                throw new IllegalArgumentException("Vector counters cannot be negative.");
            }
        }

        static VersionVector empty() {
            return new VersionVector(Map.of());
        }

        long get(String replica) {
            return counters.getOrDefault(replica, 0L);
        }

        VersionVector merge(VersionVector other) {
            Map<String, Long> merged = new HashMap<>(counters);
            other.counters.forEach(
                (replica, value) -> merged.merge(replica, value, Math::max)
            );
            return new VersionVector(merged);
        }

        VersionVector increment(String replica) {
            Map<String, Long> updated = new HashMap<>(counters);
            updated.put(replica, Math.addExact(get(replica), 1L));
            return new VersionVector(updated);
        }

        boolean dominatesOrEquals(VersionVector other) {
            return other.counters.entrySet().stream().allMatch(
                entry -> get(entry.getKey()) >= entry.getValue()
            );
        }

        boolean strictlyDominates(VersionVector other) {
            return dominatesOrEquals(other) && !equals(other);
        }

        boolean concurrentWith(VersionVector other) {
            return !dominatesOrEquals(other) && !other.dominatesOrEquals(this);
        }
    }

    record Operation(
        String id,
        String key,
        String value,
        String origin,
        VersionVector version,
        VersionVector dependencies,
        long logicalTime,
        boolean tombstone
    ) {
        Operation {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Operation ID is required.");
            }
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException("Key is required.");
            }
            Objects.requireNonNull(origin);
            Objects.requireNonNull(version);
            Objects.requireNonNull(dependencies);
        }
    }

    static final class Replica {
        private final String id;
        private boolean available = true;
        private final Map<String, Operation> records = new HashMap<>();
        private final Set<String> applied = new HashSet<>();
        private VersionVector context = VersionVector.empty();

        Replica(String id) {
            this.id = id;
        }

        Optional<String> read(String key) {
            Operation operation = records.get(key);
            if (operation == null || operation.tombstone()) {
                return Optional.empty();
            }
            return Optional.ofNullable(operation.value());
        }

        boolean hasObserved(VersionVector required) {
            return context.dominatesOrEquals(required);
        }
    }

    static final class ConsistencyService {
        private final Model model;
        private final String leaderId;
        private final int requiredAcknowledgments;
        private final Map<String, Replica> replicas = new LinkedHashMap<>();
        private final Map<String, Operation> registry = new HashMap<>();
        private final Map<String, Long> sequence = new HashMap<>();
        private final List<Operation> queue = new ArrayList<>();
        private long logicalTime;

        ConsistencyService(
            Model model,
            List<String> replicaIds,
            String leaderId,
            int requiredAcknowledgments
        ) {
            this.model = Objects.requireNonNull(model);
            this.leaderId = Objects.requireNonNull(leaderId);

            if (replicaIds.isEmpty() ||
                new HashSet<>(replicaIds).size() != replicaIds.size()) {
                throw new IllegalArgumentException(
                    "Replica identifiers must be unique and nonempty."
                );
            }

            for (String id : replicaIds) {
                replicas.put(id, new Replica(id));
            }

            if (!replicas.containsKey(leaderId)) {
                throw new IllegalArgumentException("Leader is not configured.");
            }
            if (requiredAcknowledgments < 1 ||
                requiredAcknowledgments > replicas.size()) {
                throw new IllegalArgumentException(
                    "Invalid acknowledgment requirement."
                );
            }

            this.requiredAcknowledgments = requiredAcknowledgments;
        }

        private Replica replica(String id) {
            Replica replica = replicas.get(id);
            if (replica == null) {
                throw new IllegalArgumentException("Unknown replica: " + id);
            }
            return replica;
        }

        void setAvailable(String id, boolean available) {
            replica(id).available = available;
        }

        private Operation createOperation(
            String origin,
            String key,
            String value,
            String id,
            VersionVector dependencies,
            boolean tombstone
        ) {
            Operation candidate = new Operation(
                id, key, value, origin, VersionVector.empty(),
                dependencies, 0, tombstone
            );

            Operation previous = registry.get(id);
            if (previous != null) {
                if (
                    previous.key().equals(candidate.key()) &&
                    Objects.equals(previous.value(), candidate.value()) &&
                    previous.origin().equals(candidate.origin()) &&
                    previous.dependencies().equals(candidate.dependencies()) &&
                    previous.tombstone() == candidate.tombstone()
                ) {
                    return previous;
                }
                throw new OperationConflictException(
                    "Operation ID was reused with different content: " + id
                );
            }

            Replica source = replica(origin);
            VersionVector base = source.context.merge(dependencies);
            VersionVector version = base.increment(origin);
            long nextSequence = sequence.getOrDefault(origin, 0L) + 1;
            sequence.put(origin, nextSequence);

            Operation operation = new Operation(
                id, key, value, origin, version, dependencies,
                ++logicalTime, tombstone
            );
            registry.put(id, operation);
            return operation;
        }

        private static boolean tieBreakBefore(
            Operation left,
            Operation right
        ) {
            int timestampComparison = Long.compare(
                left.logicalTime(), right.logicalTime()
            );
            if (timestampComparison != 0) return timestampComparison < 0;

            int originComparison = left.origin().compareTo(right.origin());
            if (originComparison != 0) return originComparison < 0;

            return left.id().compareTo(right.id()) < 0;
        }

        private Operation resolve(
            Operation current,
            Operation incoming
        ) {
            if (current == null) return incoming;

            if (incoming.version().strictlyDominates(current.version())) {
                return incoming;
            }
            if (current.version().strictlyDominates(incoming.version())) {
                return current;
            }

            // Deterministic resolution guarantees a single result for the
            // same set of operations, but can discard concurrent values.
            if (
                incoming.version().concurrentWith(current.version()) ||
                incoming.version().equals(current.version())
            ) {
                return tieBreakBefore(current, incoming) ? incoming : current;
            }

            return current;
        }

        private boolean apply(Replica target, Operation operation) {
            if (target.applied.contains(operation.id())) return false;

            if (
                model == Model.CAUSAL &&
                !target.hasObserved(operation.dependencies())
            ) {
                throw new MissingDependencyException(
                    target.id + " has not observed prerequisites of " +
                    operation.id()
                );
            }

            target.records.put(
                operation.key(),
                resolve(target.records.get(operation.key()), operation)
            );
            target.applied.add(operation.id());
            target.context = target.context.merge(operation.version());
            return true;
        }

        Operation write(
            String origin,
            String key,
            String value,
            String id,
            VersionVector dependencies
        ) {
            Replica source = replica(origin);
            if (!source.available) {
                throw new AvailabilityException("Origin replica is unavailable.");
            }

            if (model == Model.STRONG) {
                Replica leader = replica(leaderId);
                if (!leader.available) {
                    throw new AvailabilityException("Leader is unavailable.");
                }

                long available = replicas.values().stream()
                    .filter(replica -> replica.available)
                    .count();

                if (available < requiredAcknowledgments) {
                    throw new AvailabilityException(
                        "Required acknowledgments cannot be obtained."
                    );
                }

                Operation operation = createOperation(
                    leaderId, key, value, id, dependencies, false
                );

                // The service models successful synchronous replication.
                // Production strong consistency requires consensus and durable
                // commit handling, not merely iterating over an in-memory map.
                for (Replica target : replicas.values()) {
                    if (target.available) apply(target, operation);
                }
                return operation;
            }

            Operation operation = createOperation(
                origin, key, value, id, dependencies, false
            );
            apply(source, operation);
            queue.add(operation);
            return operation;
        }

        void delete(
            String origin,
            String key,
            String id,
            VersionVector dependencies
        ) {
            Replica source = replica(origin);
            if (!source.available) {
                throw new AvailabilityException("Origin replica is unavailable.");
            }

            Operation operation = createOperation(
                origin, key, null, id, dependencies, true
            );
            apply(source, operation);
            queue.add(operation);
        }

        Optional<String> read(
            String replicaId,
            String key,
            VersionVector minimumContext
        ) {
            Replica requested = replica(replicaId);
            if (!requested.available) {
                throw new AvailabilityException("Replica is unavailable.");
            }

            if (model == Model.STRONG) {
                Replica leader = replica(leaderId);
                if (!leader.available) {
                    throw new AvailabilityException("Leader is unavailable.");
                }
                return leader.read(key);
            }

            if (
                model == Model.CAUSAL &&
                !requested.hasObserved(minimumContext)
            ) {
                throw new MissingDependencyException(
                    "Replica has not reached the client's causal context."
                );
            }

            return requested.read(key);
        }

        boolean deliver(int index) {
            if (index < 0 || index >= queue.size()) return false;

            Operation operation = queue.remove(index);
            boolean deferred = false;

            for (Replica target : replicas.values()) {
                if (!target.available || target.applied.contains(operation.id())) {
                    continue;
                }
                try {
                    apply(target, operation);
                } catch (MissingDependencyException error) {
                    deferred = true;
                }
            }

            if (deferred) queue.add(operation);
            return true;
        }

        int flush(int limit) {
            int steps = 0;
            while (!queue.isEmpty() && steps < limit) {
                int previousSize = queue.size();
                deliver(0);
                steps++;

                if (queue.size() == previousSize) {
                    boolean progress = false;
                    for (int i = 1; i < queue.size(); i++) {
                        Operation operation = queue.get(i);
                        boolean prerequisiteExists = replicas.values().stream()
                            .filter(replica -> replica.available)
                            .anyMatch(replica ->
                                replica.hasObserved(operation.dependencies())
                            );

                        if (prerequisiteExists) {
                            deliver(i);
                            progress = true;
                            steps++;
                            break;
                        }
                    }
                    if (!progress) break;
                }
            }
            return steps;
        }

        void antiEntropy() {
            List<Operation> operations = new ArrayList<>(registry.values());
            operations.sort(
                Comparator.comparingLong(Operation::logicalTime)
                    .thenComparing(Operation::id)
            );

            boolean changed = true;
            int passes = 0;

            while (changed && passes++ <= operations.size() + 1) {
                changed = false;
                for (Operation operation : operations) {
                    for (Replica target : replicas.values()) {
                        if (!target.available ||
                            target.applied.contains(operation.id())) {
                            continue;
                        }

                        try {
                            changed |= apply(target, operation);
                        } catch (MissingDependencyException error) {
                            // Another pass can apply this event after its
                            // causal predecessor becomes available.
                        }
                    }
                }
            }

            queue.removeIf(operation -> replicas.values().stream()
                .filter(replica -> replica.available)
                .allMatch(replica -> replica.applied.contains(operation.id()))
            );
        }

        void printValues(String key) {
            System.out.println(key + ":");
            replicas.forEach((id, replica) ->
                System.out.println("  " + id + " = " +
                    replica.read(key).orElse("<absent>"))
            );
        }
    }

    private static void strongConsistencyScenario() {
        System.out.println("\n=== Strong consistency ===");
        ConsistencyService service = new ConsistencyService(
            Model.STRONG, List.of("A", "B", "C"), "A", 2
        );

        service.write(
            "A", "incident:INC-804", "open", "strong-1",
            VersionVector.empty()
        );
        assert service.read(
            "B", "incident:INC-804", VersionVector.empty()
        ).orElseThrow().equals("open");

        service.setAvailable("A", false);
        try {
            service.read("B", "incident:INC-804", VersionVector.empty());
            throw new AssertionError("Unavailable leader should reject the read.");
        } catch (AvailabilityException expected) {
            System.out.println("Unavailable leader correctly rejects the read.");
        }
    }

    private static void eventualConsistencyScenario() {
        System.out.println("\n=== Eventual consistency ===");
        ConsistencyService service = new ConsistencyService(
            Model.EVENTUAL, List.of("A", "B", "C"), "A", 1
        );

        service.write(
            "A", "dashboard:region", "ap-south", "event-1",
            VersionVector.empty()
        );

        assert service.read(
            "A", "dashboard:region", VersionVector.empty()
        ).orElseThrow().equals("ap-south");

        assert service.read(
            "B", "dashboard:region", VersionVector.empty()
        ).isEmpty();

        service.flush(100);
        assert service.read(
            "B", "dashboard:region", VersionVector.empty()
        ).orElseThrow().equals("ap-south");

        service.printValues("dashboard:region");
    }

    private static void causalConsistencyScenario() {
        System.out.println("\n=== Causal consistency ===");
        ConsistencyService service = new ConsistencyService(
            Model.CAUSAL, List.of("A", "B", "C"), "A", 1
        );

        Operation created = service.write(
            "A", "incident:INC-804", "opened", "causal-1",
            VersionVector.empty()
        );

        Operation assigned = service.write(
            "A", "incident:INC-804:assignment", "network-operations",
            "causal-2", created.version()
        );

        service.deliver(1);
        assert service.read(
            "B", "incident:INC-804:assignment", VersionVector.empty()
        ).isEmpty();

        service.flush(100);
        assert service.read(
            "B", "incident:INC-804:assignment", assigned.version()
        ).orElseThrow().equals("network-operations");

        System.out.println("Causal predecessor observed before dependent state.");
        service.printValues("incident:INC-804:assignment");
    }

    public static void main(String[] args) {
        strongConsistencyScenario();
        eventualConsistencyScenario();
        causalConsistencyScenario();
        System.out.println("\nJava consistency scenarios completed.");
    }
}
