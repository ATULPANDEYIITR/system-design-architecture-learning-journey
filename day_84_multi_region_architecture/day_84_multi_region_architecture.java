import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/*
 * Multi-Region Enterprise Architecture.
 *
 * Java 17 implementation covering:
 * - Enterprise region inventory
 * - Deployment roles
 * - Regional health
 * - Replication consistency
 * - Failover approval policies
 * - RPO and RTO
 * - Leader epochs
 * - Controlled disaster recovery
 * - Audit history
 */

public class MultiRegionArchitecture {

    enum RegionStatus {
        HEALTHY,
        DEGRADED,
        UNAVAILABLE,
        RECOVERING
    }

    enum DeploymentRole {
        PRIMARY,
        STANDBY,
        DISABLED
    }

    enum Decision {
        APPROVED,
        REJECTED
    }

    enum ArchitectureMode {
        ACTIVE_PASSIVE,
        ACTIVE_ACTIVE
    }

    record RegionMetrics(
        double latencyMs,
        double replicationLagSeconds,
        int capacity,
        int activeLoad
    ) {
        RegionMetrics {
            if (latencyMs < 0 ||
                replicationLagSeconds < 0 ||
                capacity <= 0 ||
                activeLoad < 0 ||
                activeLoad > capacity) {

                throw new IllegalArgumentException(
                    "Invalid regional metrics."
                );
            }
        }

        double freeCapacityRatio() {
            return (double) (capacity - activeLoad) / capacity;
        }
    }

    record FailoverPolicy(
        double maximumLagSeconds,
        double maximumLatencyMs,
        double minimumFreeCapacity,
        boolean requireHealthyRegion,
        boolean requireStandby
    ) {
        FailoverPolicy {
            if (maximumLagSeconds < 0 ||
                maximumLatencyMs <= 0 ||
                minimumFreeCapacity < 0 ||
                minimumFreeCapacity >= 1) {

                throw new IllegalArgumentException(
                    "Invalid failover policy."
                );
            }
        }
    }

    record PolicyResult(
        Decision decision,
        String explanation
    ) {}

    record FailoverAudit(
        String source,
        String target,
        Decision decision,
        String explanation,
        double rpoSeconds,
        double estimatedRtoSeconds,
        long leaderEpoch,
        Instant timestamp
    ) {}

    static class ArchitectureException extends RuntimeException {
        ArchitectureException(String message) {
            super(message);
        }
    }

    static class Region {

        private final String id;
        private final String geography;

        private RegionStatus status;
        private DeploymentRole role;
        private RegionMetrics metrics;

        private long dataVersion;

        Region(
            String id,
            String geography,
            RegionStatus status,
            DeploymentRole role,
            RegionMetrics metrics
        ) {
            this.id = Objects.requireNonNull(id);
            this.geography = Objects.requireNonNull(geography);
            this.status = Objects.requireNonNull(status);
            this.role = Objects.requireNonNull(role);
            this.metrics = Objects.requireNonNull(metrics);

            if (id.isBlank() || geography.isBlank()) {
                throw new IllegalArgumentException(
                    "Region identity cannot be blank."
                );
            }
        }

        String id() {
            return id;
        }

        String geography() {
            return geography;
        }

        RegionStatus status() {
            return status;
        }

        DeploymentRole role() {
            return role;
        }

        RegionMetrics metrics() {
            return metrics;
        }

        long dataVersion() {
            return dataVersion;
        }

        void setStatus(RegionStatus status) {
            this.status = Objects.requireNonNull(status);
        }

        void setRole(DeploymentRole role) {
            this.role = Objects.requireNonNull(role);
        }

        void setMetrics(RegionMetrics metrics) {
            this.metrics = Objects.requireNonNull(metrics);
        }

        void applyWrite() {
            if (status != RegionStatus.HEALTHY) {
                throw new ArchitectureException(
                    "Writes are not permitted in an unhealthy region."
                );
            }

            if (metrics.activeLoad() >= metrics.capacity()) {
                throw new ArchitectureException(
                    "Regional capacity exhausted."
                );
            }

            dataVersion++;
        }

        void synchronize(long version) {
            if (version < dataVersion) {
                throw new ArchitectureException(
                    "Replication cannot move data backwards."
                );
            }

            dataVersion = version;
        }
    }

    interface FailoverEvaluator {
        PolicyResult evaluate(Region region);
    }

    static class DefaultFailoverEvaluator
        implements FailoverEvaluator {

        private final FailoverPolicy policy;

        DefaultFailoverEvaluator(FailoverPolicy policy) {
            this.policy = Objects.requireNonNull(policy);
        }

        @Override
        public PolicyResult evaluate(Region region) {

            if (policy.requireHealthyRegion() &&
                region.status() != RegionStatus.HEALTHY) {

                return rejected("Region is not healthy.");
            }

            if (region.status() == RegionStatus.UNAVAILABLE ||
                region.status() == RegionStatus.RECOVERING) {

                return rejected("Region cannot serve production traffic.");
            }

            if (policy.requireStandby() &&
                region.role() != DeploymentRole.STANDBY) {

                return rejected("Region is not a standby.");
            }

            if (region.metrics().replicationLagSeconds() >
                policy.maximumLagSeconds()) {

                return rejected("RPO policy violated.");
            }

            if (region.metrics().latencyMs() >
                policy.maximumLatencyMs()) {

                return rejected("Latency policy violated.");
            }

            if (region.metrics().freeCapacityRatio() <
                policy.minimumFreeCapacity()) {

                return rejected("Capacity policy violated.");
            }

            return new PolicyResult(
                Decision.APPROVED,
                "All regional policies satisfied."
            );
        }

        private PolicyResult rejected(String explanation) {
            return new PolicyResult(
                Decision.REJECTED,
                explanation
            );
        }
    }

    static class RegionalRegistry {

        private final Map<String, Region> regions =
            new HashMap<>();

        private String primaryRegion;

        void register(Region region) {

            Objects.requireNonNull(region);

            if (regions.containsKey(region.id())) {
                throw new ArchitectureException(
                    "Duplicate regional identifier."
                );
            }

            if (region.role() == DeploymentRole.PRIMARY) {

                if (primaryRegion != null) {
                    throw new ArchitectureException(
                        "Multiple primary regions are not permitted."
                    );
                }

                primaryRegion = region.id();
            }

            regions.put(region.id(), region);
        }

        Region get(String id) {

            Region region = regions.get(id);

            if (region == null) {
                throw new ArchitectureException(
                    "Unknown region: " + id
                );
            }

            return region;
        }

        List<Region> all() {
            return List.copyOf(regions.values());
        }

        String primaryId() {
            if (primaryRegion == null) {
                throw new ArchitectureException(
                    "No primary region configured."
                );
            }

            return primaryRegion;
        }

        void setPrimary(String id) {
            get(id);
            primaryRegion = id;
        }
    }

    static class FailoverService {

        private final RegionalRegistry registry;
        private final FailoverEvaluator evaluator;
        private final ArchitectureMode mode;

        private final List<FailoverAudit> auditLog =
            new ArrayList<>();

        private long leaderEpoch = 1;
        private boolean failoverInProgress;

        FailoverService(
            RegionalRegistry registry,
            FailoverEvaluator evaluator,
            ArchitectureMode mode
        ) {
            this.registry = registry;
            this.evaluator = evaluator;
            this.mode = mode;
        }

        List<Region> eligibleRegions() {

            return registry.all()
                .stream()
                .filter(region ->
                    !region.id().equals(registry.primaryId())
                )
                .filter(region ->
                    evaluator.evaluate(region).decision()
                        == Decision.APPROVED
                )
                .sorted(
                    Comparator.comparingDouble(
                        (Region region) ->
                            region.metrics().replicationLagSeconds()
                    ).thenComparingDouble(
                        region -> region.metrics().latencyMs()
                    )
                )
                .toList();
        }

        FailoverAudit promote(String targetId) {

            if (failoverInProgress) {
                throw new ArchitectureException(
                    "Concurrent failover operation rejected."
                );
            }

            failoverInProgress = true;

            try {

                String sourceId = registry.primaryId();

                if (sourceId.equals(targetId)) {
                    throw new ArchitectureException(
                        "Source and target must differ."
                    );
                }

                Region source = registry.get(sourceId);
                Region target = registry.get(targetId);

                PolicyResult result = evaluator.evaluate(target);

                if (result.decision() == Decision.REJECTED) {

                    FailoverAudit rejected = new FailoverAudit(
                        sourceId,
                        targetId,
                        Decision.REJECTED,
                        result.explanation(),
                        target.metrics().replicationLagSeconds(),
                        0.0,
                        leaderEpoch,
                        Instant.now()
                    );

                    auditLog.add(rejected);

                    return rejected;
                }

                if (mode == ArchitectureMode.ACTIVE_PASSIVE &&
                    target.role() != DeploymentRole.STANDBY) {

                    throw new ArchitectureException(
                        "Active-passive promotion requires standby."
                    );
                }

                if (leaderEpoch == Long.MAX_VALUE) {
                    throw new ArchitectureException(
                        "Leader epoch exhausted."
                    );
                }

                // Production deployments must persist this epoch
                // using a strongly consistent fencing mechanism.
                long nextEpoch = leaderEpoch + 1;

                source.setRole(DeploymentRole.STANDBY);
                target.setRole(DeploymentRole.PRIMARY);

                registry.setPrimary(targetId);
                leaderEpoch = nextEpoch;

                FailoverAudit record = new FailoverAudit(
                    sourceId,
                    targetId,
                    Decision.APPROVED,
                    "Regional promotion completed.",
                    target.metrics().replicationLagSeconds(),
                    2.0,
                    leaderEpoch,
                    Instant.now()
                );

                auditLog.add(record);

                return record;

            } finally {
                failoverInProgress = false;
            }
        }

        void synchronizeReplicas() {

            Region primary = registry.get(registry.primaryId());

            for (Region region : registry.all()) {

                if (region.id().equals(primary.id())) {
                    continue;
                }

                if (region.status() == RegionStatus.HEALTHY) {
                    region.synchronize(primary.dataVersion());
                }
            }
        }

        void recover(String regionId) {

            Region recovered = registry.get(regionId);

            Region primary = registry.get(registry.primaryId());

            recovered.setStatus(RegionStatus.RECOVERING);

            recovered.synchronize(primary.dataVersion());

            recovered.setMetrics(
                new RegionMetrics(
                    recovered.metrics().latencyMs(),
                    0.0,
                    recovered.metrics().capacity(),
                    0
                )
            );

            recovered.setStatus(RegionStatus.HEALTHY);
            recovered.setRole(DeploymentRole.STANDBY);
        }

        FailoverAudit failback(String regionId) {

            Region target = registry.get(regionId);
            Region primary = registry.get(registry.primaryId());

            if (target.dataVersion() != primary.dataVersion()) {
                throw new ArchitectureException(
                    "Failback requires synchronized replicas."
                );
            }

            return promote(regionId);
        }

        long leaderEpoch() {
            return leaderEpoch;
        }

        List<FailoverAudit> auditLog() {
            return List.copyOf(auditLog);
        }
    }

    static void printReport(
        RegionalRegistry registry,
        FailoverService service
    ) {

        System.out.println("\nREGIONAL DEPLOYMENT");

        System.out.println(
            "Primary region: " + registry.primaryId()
        );

        System.out.println(
            "Leader epoch: " + service.leaderEpoch()
        );

        for (Region region : registry.all()) {

            System.out.printf(
                "%-15s %-15s %-12s lag=%5.2f version=%d%n",
                region.id(),
                region.status(),
                region.role(),
                region.metrics().replicationLagSeconds(),
                region.dataVersion()
            );
        }
    }

    public static void main(String[] args) {

        try {

            FailoverPolicy policy = new FailoverPolicy(
                5.0,
                250.0,
                0.20,
                true,
                true
            );

            RegionalRegistry registry = new RegionalRegistry();

            registry.register(new Region(
                "ap-south-1",
                "Mumbai, India",
                RegionStatus.HEALTHY,
                DeploymentRole.PRIMARY,
                new RegionMetrics(30, 0, 1000, 100)
            ));

            registry.register(new Region(
                "ap-south-2",
                "Hyderabad, India",
                RegionStatus.HEALTHY,
                DeploymentRole.STANDBY,
                new RegionMetrics(45, 1, 1200, 100)
            ));

            registry.register(new Region(
                "eu-west-1",
                "Ireland",
                RegionStatus.HEALTHY,
                DeploymentRole.STANDBY,
                new RegionMetrics(130, 2, 1500, 100)
            ));

            FailoverService service = new FailoverService(
                registry,
                new DefaultFailoverEvaluator(policy),
                ArchitectureMode.ACTIVE_PASSIVE
            );

            System.out.println("NORMAL OPERATIONS");

            Region primary = registry.get(registry.primaryId());

            primary.applyWrite();
            primary.applyWrite();

            service.synchronizeReplicas();

            printReport(registry, service);

            System.out.println("\nPRIMARY REGION FAILURE");

            primary.setStatus(RegionStatus.UNAVAILABLE);

            List<Region> eligible = service.eligibleRegions();

            if (eligible.isEmpty()) {
                throw new ArchitectureException(
                    "No eligible standby region."
                );
            }

            for (Region region : eligible) {
                System.out.println(
                    "Eligible: " + region.id()
                );
            }

            FailoverAudit event =
                service.promote(eligible.get(0).id());

            System.out.println(
                "Failover: " + event.decision()
            );

            System.out.println(
                "RPO: " + event.rpoSeconds()
            );

            System.out.println(
                "Estimated RTO: " + event.estimatedRtoSeconds()
            );

            registry.get(registry.primaryId()).applyWrite();

            printReport(registry, service);

            System.out.println("\nDISASTER RECOVERY");

            service.recover("ap-south-1");

            service.synchronizeReplicas();

            FailoverAudit failback =
                service.failback("ap-south-1");

            System.out.println(
                "Failback: " + failback.decision()
            );

            printReport(registry, service);

            System.out.println("\nAUDIT HISTORY");

            service.auditLog().forEach(System.out::println);

            if (!registry.primaryId().equals("ap-south-1")) {
                throw new AssertionError(
                    "Unexpected final primary."
                );
            }

            System.out.println(
                "\nAll enterprise architecture checks passed."
            );

        } catch (RuntimeException exception) {

            System.err.println(
                "Architecture error: " + exception.getMessage()
            );

            System.exit(1);
        }
    }
}
