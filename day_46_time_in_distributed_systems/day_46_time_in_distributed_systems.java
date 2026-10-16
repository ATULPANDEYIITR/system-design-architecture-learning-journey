import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

public class DistributedTimeEnterpriseModel {

    enum EventType {
        REQUEST_CREATED,
        MESSAGE_SENT,
        MESSAGE_RECEIVED,
        REVIEW_RECORDED,
        DECISION_RECORDED
    }

    enum Causality {
        BEFORE,
        AFTER,
        EQUAL,
        CONCURRENT
    }

    record PhysicalTimestamp(
        Instant observedAt,
        long offsetMillis,
        double driftPpm
    ) {
        PhysicalTimestamp {
            Objects.requireNonNull(observedAt, "observedAt");
        }
    }

    record LogicalTimestamp(String nodeId, long value) {
        LogicalTimestamp {
            if (value <= 0) {
                throw new IllegalArgumentException(
                    "Logical timestamp must be positive"
                );
            }
            Objects.requireNonNull(nodeId, "nodeId");
        }
    }

    record VectorTimestamp(Map<String, Long> values) {
        VectorTimestamp {
            Objects.requireNonNull(values, "values");

            TreeMap<String, Long> copy = new TreeMap<>();

            for (Map.Entry<String, Long> entry : values.entrySet()) {
                if (entry.getValue() == null || entry.getValue() < 0) {
                    throw new IllegalArgumentException(
                        "Vector values must be non-negative"
                    );
                }

                copy.put(entry.getKey(), entry.getValue());
            }

            values = Collections.unmodifiableMap(copy);
        }
    }

    record DistributedEvent(
        String eventId,
        String nodeId,
        EventType type,
        PhysicalTimestamp physical,
        LogicalTimestamp logical,
        VectorTimestamp vector,
        String payload
    ) {
        DistributedEvent {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(nodeId);
            Objects.requireNonNull(type);
            Objects.requireNonNull(physical);
            Objects.requireNonNull(logical);
            Objects.requireNonNull(vector);
            Objects.requireNonNull(payload);
        }
    }

    static final class LamportClock {
        private final String nodeId;
        private long value;

        LamportClock(String nodeId) {
            this.nodeId = Objects.requireNonNull(nodeId);
        }

        synchronized long local() {
            return ++value;
        }

        synchronized long send() {
            return ++value;
        }

        synchronized long receive(long remoteValue) {
            if (remoteValue < 0) {
                throw new IllegalArgumentException(
                    "Remote Lamport timestamp cannot be negative"
                );
            }

            value = Math.max(value, remoteValue) + 1;
            return value;
        }
    }

    static final class VectorClock {
        private final String nodeId;
        private final Map<String, Long> values;

        VectorClock(String nodeId, Set<String> nodes) {
            if (!nodes.contains(nodeId)) {
                throw new IllegalArgumentException(
                    "Node must belong to the vector clock membership"
                );
            }

            this.nodeId = nodeId;
            this.values = new TreeMap<>();

            for (String node : nodes) {
                this.values.put(node, 0L);
            }
        }

        synchronized VectorTimestamp local() {
            values.compute(
                nodeId,
                (ignored, current) -> current + 1
            );

            return snapshot();
        }

        synchronized VectorTimestamp send() {
            return local();
        }

        synchronized VectorTimestamp receive(VectorTimestamp remote) {
            if (!values.keySet().equals(remote.values().keySet())) {
                throw new IllegalArgumentException(
                    "Vector dimensions must match"
                );
            }

            for (Map.Entry<String, Long> entry :
                    remote.values().entrySet()) {

                values.put(
                    entry.getKey(),
                    Math.max(
                        values.get(entry.getKey()),
                        entry.getValue()
                    )
                );
            }

            values.compute(
                nodeId,
                (ignored, current) -> current + 1
            );

            return snapshot();
        }

        private VectorTimestamp snapshot() {
            return new VectorTimestamp(new TreeMap<>(values));
        }
    }

    static final class Node {
        private final String nodeId;
        private final long clockOffsetMillis;
        private final double driftPpm;
        private final LamportClock lamport;
        private final VectorClock vector;

        Node(
            String nodeId,
            long clockOffsetMillis,
            double driftPpm,
            Set<String> cluster
        ) {
            this.nodeId = nodeId;
            this.clockOffsetMillis = clockOffsetMillis;
            this.driftPpm = driftPpm;
            this.lamport = new LamportClock(nodeId);
            this.vector = new VectorClock(nodeId, cluster);
        }

        PhysicalTimestamp physical(Instant reference) {
            long epochMillis = reference.toEpochMilli();

            long driftMillis = Math.round(
                epochMillis * driftPpm / 1_000_000.0
            );

            return new PhysicalTimestamp(
                reference.plusMillis(
                    clockOffsetMillis + driftMillis
                ),
                clockOffsetMillis,
                driftPpm
            );
        }

        DistributedEvent local(
            String eventId,
            EventType type,
            Instant reference,
            String payload
        ) {
            return new DistributedEvent(
                eventId,
                nodeId,
                type,
                physical(reference),
                new LogicalTimestamp(nodeId, lamport.local()),
                vector.local(),
                payload
            );
        }

        DistributedEvent send(
            String eventId,
            Instant reference,
            String payload
        ) {
            return new DistributedEvent(
                eventId,
                nodeId,
                EventType.MESSAGE_SENT,
                physical(reference),
                new LogicalTimestamp(nodeId, lamport.send()),
                vector.send(),
                payload
            );
        }

        DistributedEvent receive(
            String eventId,
            Instant reference,
            DistributedEvent message,
            String payload
        ) {
            return new DistributedEvent(
                eventId,
                nodeId,
                EventType.MESSAGE_RECEIVED,
                physical(reference),
                new LogicalTimestamp(
                    nodeId,
                    lamport.receive(
                        message.logical().value()
                    )
                ),
                vector.receive(message.vector()),
                payload
            );
        }
    }

    static Causality compare(
        VectorTimestamp left,
        VectorTimestamp right
    ) {
        if (!left.values().keySet().equals(
            right.values().keySet()
        )) {
            throw new IllegalArgumentException(
                "Vector dimensions differ"
            );
        }

        boolean leftLessOrEqual = true;
        boolean rightLessOrEqual = true;
        boolean leftStrict = false;
        boolean rightStrict = false;

        for (String node : left.values().keySet()) {
            long l = left.values().get(node);
            long r = right.values().get(node);

            if (l > r) {
                leftLessOrEqual = false;
                rightStrict = true;
            }

            if (r > l) {
                rightLessOrEqual = false;
                leftStrict = true;
            }
        }

        if (leftLessOrEqual && rightLessOrEqual) {
            return Causality.EQUAL;
        }

        if (leftLessOrEqual && leftStrict) {
            return Causality.BEFORE;
        }

        if (rightLessOrEqual && rightStrict) {
            return Causality.AFTER;
        }

        return Causality.CONCURRENT;
    }

    static final class EventStore {
        private final List<DistributedEvent> events =
            new ArrayList<>();

        void append(DistributedEvent event) {
            if (event.logical().value() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid logical timestamp"
                );
            }

            events.add(event);
        }

        List<DistributedEvent> byPhysicalTime() {
            return events.stream()
                .sorted(
                    Comparator.comparing(
                        event -> event.physical().observedAt()
                    )
                )
                .toList();
        }

        List<DistributedEvent> immutableSnapshot() {
            return List.copyOf(events);
        }
    }

    static void printEvent(DistributedEvent event) {
        System.out.printf(
            "%s %-10s %-20s physical=%s L=%d V=%s%n",
            event.eventId(),
            event.nodeId(),
            event.type(),
            event.physical().observedAt(),
            event.logical().value(),
            event.vector().values()
        );
    }

    static void demonstrateEnterpriseWorkflow() {
        System.out.println("=== Enterprise Distributed Timeline ===");

        Set<String> cluster = Set.of(
            "gateway",
            "workflow",
            "audit"
        );

        Node gateway = new Node(
            "gateway",
            120,
            10,
            cluster
        );

        Node workflow = new Node(
            "workflow",
            -65,
            -6,
            cluster
        );

        Node audit = new Node(
            "audit",
            35,
            20,
            cluster
        );

        Instant base = Instant.parse(
            "2026-10-16T05:30:00Z"
        );

        EventStore store = new EventStore();

        DistributedEvent request = gateway.local(
            "evt-001",
            EventType.REQUEST_CREATED,
            base,
            "request=REQ-1001"
        );

        DistributedEvent requestMessage = gateway.send(
            "evt-002",
            base.plusMillis(5),
            "workflow=START"
        );

        DistributedEvent workflowReceived = workflow.receive(
            "evt-003",
            base.plusMillis(12),
            requestMessage,
            "state=PROCESSING"
        );

        DistributedEvent workflowDecision = workflow.local(
            "evt-004",
            EventType.REVIEW_RECORDED,
            base.plusMillis(20),
            "decision=APPROVED"
        );

        DistributedEvent auditMessage = workflow.send(
            "evt-005",
            base.plusMillis(25),
            "audit=RECORD"
        );

        DistributedEvent auditReceived = audit.receive(
            "evt-006",
            base.plusMillis(30),
            auditMessage,
            "recorded=true"
        );

        DistributedEvent independentAudit = audit.local(
            "evt-007",
            EventType.DECISION_RECORDED,
            base.plusMillis(35),
            "retention=enabled"
        );

        for (DistributedEvent event : List.of(
            request,
            requestMessage,
            workflowReceived,
            workflowDecision,
            auditMessage,
            auditReceived,
            independentAudit
        )) {
            store.append(event);
        }

        for (DistributedEvent event : store.immutableSnapshot()) {
            printEvent(event);
        }

        System.out.println(
            "evt-002 -> evt-003: " +
            compare(
                requestMessage.vector(),
                workflowReceived.vector()
            )
        );

        System.out.println(
            "evt-005 -> evt-006: " +
            compare(
                auditMessage.vector(),
                auditReceived.vector()
            )
        );

        System.out.println(
            "evt-004 vs evt-007: " +
            compare(
                workflowDecision.vector(),
                independentAudit.vector()
            )
        );

        System.out.println(
            "Physical-order view:"
        );

        for (DistributedEvent event : store.byPhysicalTime()) {
            printEvent(event);
        }

        Duration observedSeparation = Duration.between(
            request.physical().observedAt(),
            auditReceived.physical().observedAt()
        );

        System.out.println(
            "Observed physical separation: " +
            observedSeparation.toMillis() +
            " ms"
        );
    }

    static void demonstrateClockSkew() {
        System.out.println("\n=== Clock Skew ===");

        Instant reference = Instant.parse(
            "2026-10-16T05:30:10Z"
        );

        Node fast = new Node(
            "fast-node",
            150,
            25,
            Set.of("fast-node", "slow-node")
        );

        Node slow = new Node(
            "slow-node",
            -100,
            -20,
            Set.of("fast-node", "slow-node")
        );

        Instant fastReading =
            fast.physical(reference).observedAt();

        Instant slowReading =
            slow.physical(reference).observedAt();

        System.out.println(
            "fast-node: " + fastReading
        );

        System.out.println(
            "slow-node: " + slowReading
        );

        System.out.println(
            "Observed skew: " +
            Math.abs(
                Duration.between(
                    slowReading,
                    fastReading
                ).toMillis()
            ) +
            " ms"
        );
    }

    static void demonstrateValidation() {
        System.out.println("\n=== Validation ===");

        try {
            new LamportClock("node")
                .receive(-1);
        } catch (IllegalArgumentException exception) {
            System.out.println(
                "Rejected invalid Lamport timestamp: " +
                exception.getMessage()
            );
        }

        try {
            VectorTimestamp left =
                new VectorTimestamp(
                    Map.of("a", 1L)
                );

            VectorTimestamp right =
                new VectorTimestamp(
                    Map.of("a", 1L, "b", 2L)
                );

            compare(left, right);
        } catch (IllegalArgumentException exception) {
            System.out.println(
                "Rejected incompatible vector dimensions: " +
                exception.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        demonstrateClockSkew();
        demonstrateEnterpriseWorkflow();
        demonstrateValidation();

        System.out.println("\n=== Production Design ===");
        System.out.println(
            "Store UTC physical timestamps for operational evidence."
        );
        System.out.println(
            "Store logical metadata when event ordering affects correctness."
        );
        System.out.println(
            "Use vector clocks only when concurrency detection justifies "
            + "their additional metadata and state cost."
        );
        System.out.println(
            "Treat clock synchronization as an uncertainty-management "
            + "mechanism, not as proof that all nodes share identical time."
        );
    }
}
