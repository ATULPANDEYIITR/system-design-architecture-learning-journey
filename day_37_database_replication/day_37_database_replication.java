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

/*
 * Enterprise Database Replication Model
 *
 * This Java 17 program models a repository-like financial data platform with
 * a primary database and multiple replicas. It emphasizes explicit domain
 * types, state transitions, validation, synchronous acknowledgement rules,
 * asynchronous replay, failure recovery, lag monitoring, and failover.
 *
 * Java records are used for immutable change metadata. The mutable database
 * state remains inside explicit domain classes.
 */

public class DatabaseReplicationDemo {

    enum ReplicationMode {
        ASYNCHRONOUS,
        SYNCHRONOUS
    }

    enum NodeState {
        UP,
        DOWN
    }

    enum Operation {
        SET,
        DELETE
    }

    record Change(
        long lsn,
        long transactionId,
        Operation operation,
        String key,
        String value,
        long generation,
        Instant createdAt
    ) {
        Change {
            if (lsn <= 0) {
                throw new IllegalArgumentException("LSN must be positive");
            }
            Objects.requireNonNull(operation);
            Objects.requireNonNull(key);
            Objects.requireNonNull(createdAt);
        }
    }

    static class ReplicationException extends RuntimeException {
        ReplicationException(String message) {
            super(message);
        }
    }

    static final class Replica {
        private final String name;
        private NodeState state = NodeState.UP;
        private final Map<String, String> data = new HashMap<>();
        private final Deque<Change> pending = new ArrayDeque<>();
        private final Set<Long> appliedLsns = new HashSet<>();

        private long receivedLsn;
        private long replayedLsn;

        Replica(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Replica name is required");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        NodeState state() {
            return state;
        }

        void setState(NodeState state) {
            this.state = Objects.requireNonNull(state);
        }

        long receivedLsn() {
            return receivedLsn;
        }

        long replayedLsn() {
            return replayedLsn;
        }

        long lag() {
            return Math.max(0, receivedLsn - replayedLsn);
        }

        Map<String, String> snapshot() {
            return Map.copyOf(data);
        }

        void receive(Change change) {
            if (state == NodeState.DOWN) {
                return;
            }

            if (appliedLsns.contains(change.lsn())) {
                return;
            }

            pending.addLast(change);
            receivedLsn = Math.max(receivedLsn, change.lsn());
        }

        int replayAll() {
            if (state == NodeState.DOWN) {
                throw new ReplicationException(
                    name + " cannot replay while down"
                );
            }

            int applied = 0;

            while (!pending.isEmpty()) {
                Change change = pending.peekFirst();

                /*
                 * Ordered replay is essential. A replica should not apply a
                 * later transaction while an earlier log record is missing.
                 */
                if (change.lsn() != replayedLsn + 1) {
                    break;
                }

                pending.removeFirst();

                if (appliedLsns.contains(change.lsn())) {
                    replayedLsn = change.lsn();
                    continue;
                }

                if (change.operation() == Operation.SET) {
                    data.put(change.key(), change.value());
                } else {
                    data.remove(change.key());
                }

                appliedLsns.add(change.lsn());
                replayedLsn = change.lsn();
                applied++;
            }

            return applied;
        }
    }

    static final class Primary {
        private final String name;
        private NodeState state = NodeState.UP;
        private long nextLsn = 1;
        private long nextTransactionId = 1;
        private long generation = 1;

        private final Map<String, String> data = new HashMap<>();
        private final List<Change> wal = new ArrayList<>();

        Primary(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Primary name is required");
            }
            this.name = name;
        }

        String name() {
            return name;
        }

        NodeState state() {
            return state;
        }

        void setState(NodeState state) {
            this.state = Objects.requireNonNull(state);
        }

        long generation() {
            return generation;
        }

        Change write(
            Operation operation,
            String key,
            String value
        ) {
            if (state == NodeState.DOWN) {
                throw new ReplicationException("Primary is unavailable");
            }

            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException(
                    "Database key cannot be blank"
                );
            }

            if (operation == Operation.SET &&
                (value == null || value.isBlank())) {
                throw new IllegalArgumentException(
                    "SET requires a value"
                );
            }

            if (operation == Operation.SET) {
                data.put(key, value);
            } else {
                data.remove(key);
            }

            Change change = new Change(
                nextLsn++,
                nextTransactionId++,
                operation,
                key,
                value,
                generation,
                Instant.now()
            );

            wal.add(change);
            return change;
        }

        Map<String, String> snapshot() {
            return Map.copyOf(data);
        }

        List<Change> wal() {
            return List.copyOf(wal);
        }
    }

    interface AcknowledgementPolicy {
        boolean acknowledged(
            ReplicationCluster cluster,
            Change change
        );
    }

    static final class SynchronousAcknowledgementPolicy
        implements AcknowledgementPolicy {

        private final int requiredReplicas;

        SynchronousAcknowledgementPolicy(int requiredReplicas) {
            if (requiredReplicas < 1) {
                throw new IllegalArgumentException(
                    "Synchronous mode requires at least one replica"
                );
            }
            this.requiredReplicas = requiredReplicas;
        }

        @Override
        public boolean acknowledged(
            ReplicationCluster cluster,
            Change change
        ) {
            return cluster.countReplayedReplicas(change.lsn())
                >= requiredReplicas;
        }
    }

    static final class ReplicationCluster {
        private Primary primary;
        private final ReplicationMode mode;
        private final AcknowledgementPolicy acknowledgementPolicy;
        private final Map<String, Replica> replicas = new HashMap<>();

        ReplicationCluster(
            String primaryName,
            ReplicationMode mode,
            AcknowledgementPolicy acknowledgementPolicy
        ) {
            this.primary = new Primary(primaryName);
            this.mode = Objects.requireNonNull(mode);
            this.acknowledgementPolicy = acknowledgementPolicy;
        }

        Primary primary() {
            return primary;
        }

        void addReplica(Replica replica) {
            if (replicas.containsKey(replica.name())) {
                throw new IllegalArgumentException(
                    "Duplicate replica: " + replica.name()
                );
            }

            if (replica.name().equals(primary.name())) {
                throw new IllegalArgumentException(
                    "Replica name conflicts with primary"
                );
            }

            replicas.put(replica.name(), replica);
        }

        Replica replica(String name) {
            Replica replica = replicas.get(name);

            if (replica == null) {
                throw new IllegalArgumentException(
                    "Unknown replica: " + name
                );
            }

            return replica;
        }

        List<Replica> healthyReplicas() {
            return replicas.values()
                .stream()
                .filter(r -> r.state() == NodeState.UP)
                .toList();
        }

        int countReplayedReplicas(long lsn) {
            return (int) healthyReplicas()
                .stream()
                .filter(r -> r.replayedLsn() >= lsn)
                .count();
        }

        Change commit(
            Operation operation,
            String key,
            String value,
            boolean replayImmediately
        ) {
            Change change = primary.write(operation, key, value);

            for (Replica replica : healthyReplicas()) {
                replica.receive(change);
            }

            if (replayImmediately) {
                for (Replica replica : healthyReplicas()) {
                    replica.replayAll();
                }
            }

            if (mode == ReplicationMode.SYNCHRONOUS &&
                !acknowledgementPolicy.acknowledged(this, change)) {
                throw new ReplicationException(
                    "Synchronous acknowledgement failed for LSN "
                    + change.lsn()
                );
            }

            return change;
        }

        boolean consistentWithPrimary(Replica replica) {
            return primary.snapshot().equals(replica.snapshot());
        }

        void recoverReplicaFromWal(String replicaName) {
            Replica replica = replica(replicaName);

            if (replica.state() == NodeState.DOWN) {
                throw new ReplicationException(
                    "Replica must be up before replay"
                );
            }

            /*
             * A production system would normally stream only records after
             * the replica's durable replay position. This loop demonstrates
             * that same missing-range concept using the in-memory WAL.
             */
            for (Change change : primary.wal()) {
                if (change.lsn() > replica.replayedLsn()) {
                    replica.receive(change);
                }
            }

            replica.replayAll();
        }

        void promote(String replicaName) {
            Replica candidate = replica(replicaName);

            /*
             * The old primary must be fenced first. Promotion while it is
             * still writable would create two independent write authorities.
             */
            if (primary.state() != NodeState.DOWN) {
                throw new ReplicationException(
                    "Old primary must be fenced before promotion"
                );
            }

            if (candidate.state() != NodeState.UP ||
                candidate.replayedLsn() == 0) {
                throw new ReplicationException(
                    "Candidate is not promotable"
                );
            }

            Primary replacement = new Primary(candidate.name());

            /*
             * The replacement begins with the replica's durable state.
             * Its generation advances to identify a new primary authority.
             */
            try {
                var generationField =
                    Primary.class.getDeclaredField("generation");
                generationField.setAccessible(true);
                generationField.setLong(
                    replacement,
                    primary.generation() + 1
                );
            } catch (ReflectiveOperationException error) {
                throw new ReplicationException(
                    "Unable to establish failover generation"
                );
            }

            for (Map.Entry<String, String> entry :
                candidate.snapshot().entrySet()) {
                replacement.write(
                    Operation.SET,
                    entry.getKey(),
                    entry.getValue()
                );
            }

            primary = replacement;
            replicas.remove(replicaName);
        }

        void printStatus() {
            System.out.printf(
                "%-22s %-10s %-10s %-10s %-8s%n",
                "Replica",
                "State",
                "Received",
                "Replayed",
                "Lag"
            );

            replicas.values()
                .stream()
                .sorted((a, b) -> a.name().compareTo(b.name()))
                .forEach(replica -> System.out.printf(
                    "%-22s %-10s %-10d %-10d %-8d%n",
                    replica.name(),
                    replica.state(),
                    replica.receivedLsn(),
                    replica.replayedLsn(),
                    replica.lag()
                ));
        }
    }

    static void printHeading(String heading) {
        System.out.println();
        System.out.println("=".repeat(72));
        System.out.println(heading);
        System.out.println("=".repeat(72));
    }

    static void asynchronousScenario() {
        printHeading("Asynchronous primary-replica scenario");

        ReplicationCluster cluster = new ReplicationCluster(
            "customer-primary",
            ReplicationMode.ASYNCHRONOUS,
            (c, change) -> true
        );

        cluster.addReplica(new Replica("customer-replica-a"));
        cluster.addReplica(new Replica("customer-replica-b"));

        cluster.commit(
            Operation.SET,
            "customer:1001",
            "ACTIVE",
            false
        );

        cluster.commit(
            Operation.SET,
            "customer:1002",
            "SUSPENDED",
            false
        );

        cluster.printStatus();

        cluster.replica("customer-replica-a").replayAll();

        System.out.println("\nReplica-a caught up:");
        cluster.printStatus();

        cluster.replica("customer-replica-b").replayAll();

        System.out.println("\nBoth replicas caught up:");
        cluster.printStatus();
    }

    static void synchronousScenario() {
        printHeading("Synchronous acknowledgement scenario");

        ReplicationCluster cluster = new ReplicationCluster(
            "billing-primary",
            ReplicationMode.SYNCHRONOUS,
            new SynchronousAcknowledgementPolicy(1)
        );

        cluster.addReplica(new Replica("billing-replica"));

        Change committed = cluster.commit(
            Operation.SET,
            "invoice:1",
            "PAID",
            true
        );

        System.out.println(
            "Acknowledged LSN: " + committed.lsn()
        );

        cluster.replica("billing-replica").setState(NodeState.DOWN);

        try {
            cluster.commit(
                Operation.SET,
                "invoice:2",
                "PAID",
                true
            );
        } catch (ReplicationException error) {
            System.out.println(
                "Expected synchronous failure: "
                + error.getMessage()
            );
        }
    }

    static void lagScenario() {
        printHeading("Replica lag and recovery");

        ReplicationCluster cluster = new ReplicationCluster(
            "warehouse-primary",
            ReplicationMode.ASYNCHRONOUS,
            (c, change) -> true
        );

        cluster.addReplica(new Replica("warehouse-replica"));
        Replica replica = cluster.replica("warehouse-replica");

        replica.setState(NodeState.DOWN);

        for (int i = 1; i <= 4; i++) {
            cluster.commit(
                Operation.SET,
                "stock:" + i,
                String.valueOf(i * 50),
                false
            );
        }

        System.out.println("During outage:");
        cluster.printStatus();

        replica.setState(NodeState.UP);
        cluster.recoverReplicaFromWal(replica.name());

        System.out.println("\nAfter recovery:");
        cluster.printStatus();

        if (!cluster.consistentWithPrimary(replica)) {
            throw new ReplicationException(
                "Replica is inconsistent after recovery"
            );
        }
    }

    static void failoverScenario() {
        printHeading("Failover and primary fencing");

        ReplicationCluster cluster = new ReplicationCluster(
            "ledger-primary",
            ReplicationMode.ASYNCHRONOUS,
            (c, change) -> true
        );

        cluster.addReplica(new Replica("ledger-replica"));

        cluster.commit(
            Operation.SET,
            "ledger:100",
            "POSTED",
            true
        );

        cluster.commit(
            Operation.SET,
            "ledger:101",
            "POSTED",
            true
        );

        /*
         * Stopping the primary models an external fencing action. In a real
         * deployment this may involve a database service manager, consensus
         * system, lease expiration, or infrastructure-level fencing.
         */
        cluster.primary().setState(NodeState.DOWN);

        cluster.promote("ledger-replica");

        cluster.commit(
            Operation.SET,
            "ledger:102",
            "POSTED",
            true
        );

        System.out.println(
            "New primary: " + cluster.primary().name()
        );
    }

    public static void main(String[] args) {
        try {
            asynchronousScenario();
            synchronousScenario();
            lagScenario();
            failoverScenario();

            printHeading("Enterprise interpretation");
            System.out.println(
                "Asynchronous replication separates primary commit latency "
                + "from replica replay latency. Synchronous replication adds "
                + "a replica acknowledgement requirement to the commit path. "
                + "Lag monitoring measures the distance between received and "
                + "replayed positions. Failover requires fencing the old "
                + "primary before promotion to prevent split brain."
            );
        } catch (RuntimeException error) {
            System.err.println(
                "Replication system failure: " + error.getMessage()
            );
            System.exit(1);
        }
    }
}
